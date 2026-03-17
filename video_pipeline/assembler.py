"""Assemble the final educational video from individual scene clips and audio using MoviePy."""

import logging
from pathlib import Path

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

logger = logging.getLogger(__name__)

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


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
                "Scene %s — video: %.2fs, audio: %.2fs",
                scene_num,
                video_duration,
                audio_duration,
            )

            # Normalize resolution
            if video.w != TARGET_WIDTH or video.h != TARGET_HEIGHT:
                video = video.resized((TARGET_WIDTH, TARGET_HEIGHT))
                loaded_resources.append(video)

            # Sync video duration to match audio
            if audio_duration > video_duration:
                video = video.loop(duration=audio_duration)
            else:
                video = video.subclipped(0, audio_duration)
            loaded_resources.append(video)

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

        # Title overlay with semi-transparent background for readability
        logger.info("Adding title overlay: %s", title)
        bg_strip = ColorClip(
            size=(TARGET_WIDTH, 120), color=(0, 0, 0)
        ).with_opacity(0.6).with_duration(3).with_position(("center", "center"))
        loaded_resources.append(bg_strip)

        title_clip = TextClip(
            text=title,
            font_size=48,
            color="white",
            stroke_color="black",
            stroke_width=2,
            duration=3,
        ).with_position("center")
        loaded_resources.append(title_clip)

        final = CompositeVideoClip([final, bg_strip.with_start(0), title_clip.with_start(0)])
        loaded_resources.append(final)

        # Render
        logger.info("Writing final video to %s", output_path)
        final.write_videofile(
            output_path, fps=24, codec="libx264",
            audio_codec="aac", audio_bitrate="192k",
        )
        logger.info("Video assembled successfully: %s", output_path)

        return output_path

    except Exception:
        logger.exception("Failed to assemble video.")
        raise

    finally:
        for resource in loaded_resources:
            try:
                resource.close()
            except Exception:
                logger.debug("Error closing resource %s", resource, exc_info=True)
