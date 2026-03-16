"""Assemble the final educational video from individual scene clips and audio using MoviePy."""

import logging
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

logger = logging.getLogger(__name__)


def assemble_video(scenes: list[dict], title: str, output_path: str) -> str:
    """Assemble a full educational video from individual scene clips and audio.

    Args:
        scenes: List of scene dicts, each with keys:
            video_path, audio_path, narration, scene_number.
        title: Title text to overlay on the first 3 seconds.
        output_path: Destination file path for the rendered video.

    Returns:
        The output_path of the written video file.
    """
    clips: list = []
    loaded_resources: list = []

    try:
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        for scene in scenes:
            scene_num = scene["scene_number"]
            logger.info("Processing scene %s: %s", scene_num, scene["video_path"])

            video = VideoFileClip(scene["video_path"])
            audio = AudioFileClip(scene["audio_path"])
            loaded_resources.extend([video, audio])

            audio_duration = audio.duration
            video_duration = video.duration

            logger.info(
                "Scene %s — video duration: %.2fs, audio duration: %.2fs",
                scene_num,
                video_duration,
                audio_duration,
            )

            clip = video.with_audio(audio)
            loaded_resources.append(clip)
            clips.append(clip)

            logger.info("Scene %s processed successfully.", scene_num)

        if not clips:
            raise ValueError("No scenes provided — cannot assemble video.")

        # Concatenate clips with a short crossfade
        logger.info("Concatenating %d scene clips...", len(clips))
        final = concatenate_videoclips(clips, method="compose", padding=-0.5)
        loaded_resources.append(final)

        # Title overlay on the first 3 seconds
        logger.info("Adding title overlay: %s", title)
        title_clip = TextClip(
            text=title,
            font_size=60,
            color="white",
            duration=3,
        ).with_position("center")
        loaded_resources.append(title_clip)

        final = CompositeVideoClip([final, title_clip.with_start(0)])
        loaded_resources.append(final)

        # Render
        logger.info("Writing final video to %s", output_path)
        final.write_videofile(output_path, fps=24, codec="libx264")
        logger.info("Video assembled successfully: %s", output_path)

        return output_path

    except Exception:
        logger.exception("Failed to assemble video.")
        raise

    finally:
        # Release all loaded resources
        for resource in loaded_resources:
            try:
                resource.close()
            except Exception:
                logger.debug("Error closing resource %s", resource, exc_info=True)
