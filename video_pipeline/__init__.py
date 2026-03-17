"""
EduVid AI - Video Pipeline Orchestrator

Coordinates storyboard generation, video generation, TTS narration,
and final video assembly.
"""

import logging
import os
import random
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from dotenv import load_dotenv

from .assembler import assemble_video
from .storyboard import generate_storyboard
from .tts import generate_all_narrations
from .video_gen import generate_all_videos

logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file if present


@dataclass
class PipelineResult:
    video_path: str
    total_scenes: int
    succeeded_scenes: int
    failed_scene_numbers: list[int] = field(default_factory=list)


def run_pipeline(
    topic: str,
    output_dir: str | None = None,
    progress_callback=None,
    num_scenes: int = 8,
    voice_name: str | None = None,
    style: str = "cinematic",
    speaking_rate: float | None = None,
    cleanup_intermediates: bool = True,
    storyboard: dict | None = None,
) -> PipelineResult:
    """
    Full pipeline: topic -> storyboard -> parallel video+TTS -> assembly -> final .mp4

    Args:
        topic: The educational topic to generate a video about.
        output_dir: Directory for intermediate and final files (auto-created if None).
        progress_callback: Optional callable(progress_float, description_str).
        num_scenes: Number of scenes to generate (default 8).
        voice_name: TTS voice name (None for default).
        style: Visual style preset (cinematic/documentary/whiteboard/animated/sci-fi).
        speaking_rate: TTS speaking rate (None for default from config).
        cleanup_intermediates: Remove video/audio dirs after assembly.
        storyboard: Pre-built storyboard dict to skip phase 1.

    Returns:
        PipelineResult with video path and scene success info.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="eduvid_")

    os.makedirs(output_dir, exist_ok=True)
    video_dir = os.path.join(output_dir, "videos")
    audio_dir = os.path.join(output_dir, "audio")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # Phase 1: Generate or use provided storyboard
    _update_progress(progress_callback, 0.0, "Generating storyboard...")
    if storyboard is not None:
        logger.info("Phase 1: Using provided storyboard")
        scenes = storyboard["scenes"]
        title = storyboard["title"]
    else:
        logger.info("Phase 1: Generating storyboard for topic: %s", topic)
        storyboard = generate_storyboard(topic, num_scenes=num_scenes, style=style)
        scenes = storyboard["scenes"]
        title = storyboard["title"]
    logger.info("Storyboard: '%s' with %d scenes", title, len(scenes))

    # Generate a consistent seed for all Veo scenes
    veo_seed = random.randint(0, 2**31)
    logger.info("Using Veo seed: %d for visual consistency", veo_seed)

    # Phase 2 & 3: Generate videos and TTS in parallel with scene-level progress
    _update_progress(progress_callback, 0.10, "Generating video clips and narration...")
    logger.info("Phase 2 & 3: Generating videos and narrations in parallel")

    total_assets = len(scenes) * 2
    completed_count = 0
    progress_lock = threading.Lock()

    def _on_asset_complete():
        nonlocal completed_count
        with progress_lock:
            completed_count += 1
            progress_value = 0.10 + (0.65 * completed_count / total_assets)
            _update_progress(
                progress_callback,
                progress_value,
                f"Generated {completed_count}/{total_assets} assets...",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        video_future = executor.submit(
            generate_all_videos, scenes, video_dir, _on_asset_complete, veo_seed
        )
        audio_future = executor.submit(
            generate_all_narrations, scenes, audio_dir, voice_name, _on_asset_complete, speaking_rate
        )

        video_paths = video_future.result()
        audio_paths = audio_future.result()

    # Filter out failed scenes (partial success)
    assembly_scenes = []
    failed_scene_numbers = []
    for i, scene in enumerate(scenes):
        v_path = video_paths[i] if i < len(video_paths) else None
        a_path = audio_paths[i] if i < len(audio_paths) else None
        if v_path is not None and a_path is not None:
            assembly_scenes.append({
                "scene_number": scene["scene_number"],
                "video_path": v_path,
                "audio_path": a_path,
                "narration": scene["narration"],
            })
        else:
            failed_scene_numbers.append(scene["scene_number"])
            logger.warning(
                "Skipping scene %d: video=%s, audio=%s",
                scene["scene_number"],
                "OK" if v_path else "FAILED",
                "OK" if a_path else "FAILED",
            )

    if not assembly_scenes:
        raise RuntimeError("All scenes failed to generate. Cannot assemble video.")

    succeeded = len(assembly_scenes)
    total = len(scenes)
    if succeeded < total:
        logger.warning("Assembling with %d/%d scenes (some failed)", succeeded, total)

    # Phase 4: Assemble final video
    _update_progress(progress_callback, 0.80, "Assembling final video...")
    logger.info("Phase 4: Assembling final video")
    output_path = os.path.join(output_dir, "final_video.mp4")
    result_path = assemble_video(assembly_scenes, title, output_path)

    # Cleanup intermediate files
    if cleanup_intermediates:
        _cleanup_intermediates(video_dir, audio_dir)

    _update_progress(progress_callback, 1.0, "Done!")
    logger.info("Pipeline complete: %s", result_path)

    return PipelineResult(
        video_path=result_path,
        total_scenes=total,
        succeeded_scenes=succeeded,
        failed_scene_numbers=failed_scene_numbers,
    )


def _cleanup_intermediates(video_dir: str, audio_dir: str):
    """Remove intermediate video and audio directories."""
    for d in [video_dir, audio_dir]:
        try:
            shutil.rmtree(d)
            logger.info("Cleaned up %s", d)
        except Exception:
            logger.warning("Failed to clean up %s", d, exc_info=True)


def _update_progress(callback, progress: float, description: str):
    """Helper to safely call progress callback."""
    if callback is not None:
        try:
            callback(progress, desc=description)
        except Exception:
            pass
