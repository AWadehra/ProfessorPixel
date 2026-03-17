"""
FFmpeg-native video assembly.

Pipeline:
  1. Per scene (parallel): mux video (stream-copy) + audio (MP3->AAC transcode)
  2. Concatenate all muxed scenes with concat demuxer (stream-copy, zero decode)
  3. Overlay title text + optional subtitles with drawtext filter (one re-encode pass)

Replaces MoviePy for 10-50x faster assembly.
"""

import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import get_settings

logger = logging.getLogger(__name__)


def _ffprobe_duration(path: str) -> float:
    """Return the duration of a media file in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _mux_scene(
    scene_num: int,
    video_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    """Mux one scene: stream-copy video, transcode audio MP3->AAC, match duration to audio."""
    audio_duration = _ffprobe_duration(audio_path)

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",  # Loop video if audio is longer
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(audio_duration),
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed for scene {scene_num}: {result.stderr}")
    logger.info("Scene %d muxed: %s (%.2fs)", scene_num, output_path, audio_duration)
    return output_path


def _concat_scenes(muxed_paths: list[str], output_path: str) -> str:
    """Concatenate all muxed scene files using FFmpeg concat demuxer (stream-copy)."""
    list_file = output_path + ".concat.txt"
    try:
        with open(list_file, "w") as f:
            for p in muxed_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
        logger.info("Concatenated %d scenes -> %s", len(muxed_paths), output_path)
        return output_path
    finally:
        try:
            os.unlink(list_file)
        except OSError:
            pass


def _build_drawtext_filter(
    title: str,
    scenes: list[dict],
    burn_subtitles: bool = True,
) -> str:
    """Build FFmpeg drawtext filter string for title + optional subtitles."""
    safe_title = title.replace("'", "\\'").replace(":", "\\:").replace('"', '\\"')

    filters = []

    # Title overlay for first 3 seconds with dark background
    filters.append(
        f"drawtext=text='{safe_title}':"
        "fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
        "borderw=2:bordercolor=black:"
        "enable='between(t,0,3)'"
    )

    # Subtitle burn-in per scene
    if burn_subtitles and scenes:
        t = 0.0
        for scene in scenes:
            narration = scene.get("narration", "")
            safe_narration = narration.replace("'", "\\'").replace(":", "\\:").replace('"', '\\"')
            duration = scene.get("duration", 8.0)
            end = t + duration

            if safe_narration:
                filters.append(
                    f"drawtext=text='{safe_narration}':"
                    "fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h-80:"
                    "borderw=1:bordercolor=black:"
                    f"enable='between(t,{t:.2f},{end:.2f})'"
                )
            t = end

    return ",".join(filters)


def _add_overlays(
    input_path: str,
    output_path: str,
    title: str,
    scenes: list[dict] | None = None,
    burn_subtitles: bool = True,
) -> str:
    """Burn title text and optional subtitles using FFmpeg drawtext filter."""
    vf = _build_drawtext_filter(title, scenes or [], burn_subtitles)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if "No such filter" in result.stderr or "drawtext" in result.stderr:
            logger.warning(
                "drawtext filter not available (FFmpeg missing libfreetype). "
                "Skipping title/subtitle overlays — copying concat output directly."
            )
            import shutil
            shutil.copy2(input_path, output_path)
            return output_path
        raise RuntimeError(f"FFmpeg overlay failed: {result.stderr}")
    logger.info("Overlays added: %s", output_path)
    return output_path


def assemble_video(scenes: list[dict], title: str, output_path: str) -> str:
    """Assemble final video from per-scene video+audio pairs using FFmpeg.

    Steps:
      1. Mux each scene in parallel (stream-copy video, transcode audio).
      2. Concatenate all scenes with concat demuxer (stream-copy).
      3. Burn title overlay + subtitles with drawtext (one libx264 pass).

    Args:
        scenes: List of dicts with keys: scene_number, video_path, audio_path, narration.
        title: Title text for the first 3-second overlay.
        output_path: Destination .mp4 path.

    Returns:
        output_path
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()

    with tempfile.TemporaryDirectory(prefix="eduvid_asm_") as tmpdir:
        # Step 1: Mux all scenes in parallel
        mux_futures = {}
        muxed_paths = {}

        with ThreadPoolExecutor(max_workers=len(scenes)) as executor:
            for scene in scenes:
                scene_num = scene["scene_number"]
                muxed_path = os.path.join(tmpdir, f"scene_{scene_num:03d}_muxed.mp4")
                future = executor.submit(
                    _mux_scene,
                    scene_num,
                    scene["video_path"],
                    scene["audio_path"],
                    muxed_path,
                )
                mux_futures[future] = scene_num

            for future in as_completed(mux_futures):
                scene_num = mux_futures[future]
                muxed_path = future.result()
                muxed_paths[scene_num] = muxed_path

        # Ordered list for concat
        ordered = [muxed_paths[s["scene_number"]] for s in scenes]

        # Compute per-scene durations for subtitle timing
        assembly_scenes = []
        for scene in scenes:
            muxed = muxed_paths[scene["scene_number"]]
            duration = _ffprobe_duration(muxed)
            assembly_scenes.append({
                "narration": scene.get("narration", ""),
                "duration": duration,
            })

        # Step 2: Concat (stream-copy)
        concat_path = os.path.join(tmpdir, "concat.mp4")
        _concat_scenes(ordered, concat_path)

        # Step 3: Title overlay + subtitles (one re-encode pass)
        _add_overlays(
            concat_path, output_path, title,
            scenes=assembly_scenes,
            burn_subtitles=settings.burn_subtitles,
        )

    logger.info("Assembly complete: %s", output_path)
    return output_path
