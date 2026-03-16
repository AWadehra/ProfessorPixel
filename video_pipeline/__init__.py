"""
EduVid AI - Video Pipeline Orchestrator

Coordinates storyboard generation, video generation, TTS narration,
and final video assembly.
"""

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from .storyboard import generate_storyboard
from .tts import generate_all_narrations
from .video_gen import generate_all_videos
from .assembler import assemble_video

load_dotenv()
logger = logging.getLogger(__name__)


def run_pipeline(topic: str, output_dir: str | None = None, progress_callback=None) -> str:
    """
    Full pipeline: topic -> storyboard -> parallel video+TTS -> assembly -> final .mp4

    Args:
        topic: The educational topic to generate a video about
        output_dir: Directory for intermediate and final files (auto-created if None)
        progress_callback: Optional callable(progress_float, description_str)

    Returns:
        Path to the final assembled .mp4 video
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="eduvid_")

    os.makedirs(output_dir, exist_ok=True)
    video_dir = os.path.join(output_dir, "videos")
    audio_dir = os.path.join(output_dir, "audio")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # Phase 1: Generate storyboard
    _update_progress(progress_callback, 0.0, "Generating storyboard...")
    logger.info("Phase 1: Generating storyboard for topic: %s", topic)
    storyboard = generate_storyboard(topic)
    scenes = storyboard["scenes"]
    title = storyboard["title"]
    logger.info("Storyboard generated: '%s' with %d scenes", title, len(scenes))

    # Phase 2 & 3: Generate videos and TTS in parallel
    _update_progress(progress_callback, 0.15, "Generating video clips and narration...")
    logger.info("Phase 2 & 3: Generating videos and narrations in parallel")

    with ThreadPoolExecutor(max_workers=2) as executor:
        video_future = executor.submit(generate_all_videos, scenes, video_dir)
        audio_future = executor.submit(generate_all_narrations, scenes, audio_dir)

        video_paths = video_future.result()
        audio_paths = audio_future.result()

    logger.info("Generated %d video clips and %d audio files", len(video_paths), len(audio_paths))

    # Prepare scene data for assembly
    assembly_scenes = []
    for i, scene in enumerate(scenes):
        assembly_scenes.append({
            "scene_number": scene["scene_number"],
            "video_path": video_paths[i],
            "audio_path": audio_paths[i],
            "narration": scene["narration"],
        })

    # Phase 4: Assemble final video
    _update_progress(progress_callback, 0.75, "Assembling final video...")
    logger.info("Phase 4: Assembling final video")
    output_path = os.path.join(output_dir, "final_video.mp4")
    result_path = assemble_video(assembly_scenes, title, output_path)

    _update_progress(progress_callback, 1.0, "Done!")
    logger.info("Pipeline complete: %s", result_path)
    return result_path


def _update_progress(callback, progress: float, description: str):
    """Helper to safely call progress callback."""
    if callback is not None:
        try:
            callback(progress, desc=description)
        except Exception:
            # Progress reporting is non-critical
            pass
