"""Imagen 3 still-image generation with Ken Burns effect as Veo fallback."""

import logging
import os
import subprocess

from google import genai
from google.genai import types

from .config import get_settings

logger = logging.getLogger(__name__)


def _get_imagen_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )


def generate_scene_image_fallback(scene: dict, output_dir: str) -> str:
    """Generate a Ken Burns video from an Imagen 3 still when Veo fails.

    Args:
        scene: Scene dict with 'scene_number' and 'veo_prompt'.
        output_dir: Directory to save the generated video.

    Returns:
        Path to the generated MP4 video.
    """
    scene_number = scene["scene_number"]
    scene_id = f"scene_{scene_number:03d}"
    image_path = os.path.join(output_dir, f"{scene_id}.png")
    video_path = os.path.join(output_dir, f"{scene_id}.mp4")

    os.makedirs(output_dir, exist_ok=True)

    logger.info("Generating Imagen 3 fallback for %s", scene_id)

    # Generate still image with Imagen 3
    client = _get_imagen_client()
    response = client.models.generate_images(
        model="imagen-3.0-generate-002",
        prompt=scene["veo_prompt"],
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",
        ),
    )

    image_bytes = response.generated_images[0].image.image_bytes
    with open(image_path, "wb") as f:
        f.write(image_bytes)
    logger.info("Imagen 3 image saved to %s", image_path)

    # Apply Ken Burns zoom effect using FFmpeg
    _ken_burns_ffmpeg(image_path, video_path, duration=8.0, zoom_factor=1.08)

    # Clean up intermediate image
    try:
        os.unlink(image_path)
    except OSError:
        pass

    logger.info("Ken Burns fallback video created: %s", video_path)
    return video_path


def _ken_burns_ffmpeg(
    image_path: str,
    output_path: str,
    duration: float = 8.0,
    zoom_factor: float = 1.08,
) -> None:
    """Apply Ken Burns pan/zoom effect to a still image using FFmpeg.

    Slowly zooms in from 100% to zoom_factor over duration seconds.
    """
    # zoompan filter: zoom from 1.0 to zoom_factor over duration
    # z='1+0.001*on' gives slow zoom per frame
    # d=total frames, s=output size, fps=24
    total_frames = int(duration * 24)
    zoom_per_frame = (zoom_factor - 1.0) / total_frames

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", (
            f"zoompan=z='1+{zoom_per_frame}*on':"
            f"d={total_frames}:"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "s=1280x720:"
            "fps=24"
        ),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",  # no audio
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Ken Burns FFmpeg failed: {result.stderr}")
