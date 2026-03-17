"""Video generation module using Veo 2 via the google-genai SDK (Vertex AI)."""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from uuid import uuid4

from google import genai
from google.cloud import storage
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings

logger = logging.getLogger(__name__)

import threading

_thread_local = threading.local()


def _get_client() -> genai.Client:
    """Get a thread-local Vertex AI genai client (httpx is not thread-safe)."""
    client = getattr(_thread_local, "genai_client", None)
    if client is None:
        settings = get_settings()
        client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
        _thread_local.genai_client = client
    return client


_storage_client = None


def _get_storage_client() -> storage.Client:
    """Lazily initialize the GCS storage client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def _download_from_gcs(gcs_uri: str, local_path: str) -> str:
    """Download a file from GCS to a local path."""
    parsed = urlparse(gcs_uri)
    bucket_name = parsed.netloc
    blob_path = parsed.path.lstrip("/")

    sc = _get_storage_client()
    bucket_obj = sc.bucket(bucket_name)
    blob = bucket_obj.blob(blob_path)

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    logger.info("Downloaded %s to %s", gcs_uri, local_path)
    return local_path


def _cleanup_gcs_blobs(blobs: list) -> None:
    """Delete GCS blobs after successful download (best-effort)."""
    for blob in blobs:
        try:
            blob.delete()
        except Exception:
            logger.warning("Failed to clean up GCS blob %s", blob.name, exc_info=True)


def generate_scene_video(
    scene: dict,
    video_id: str,
    output_dir: str,
    on_complete: callable = None,
) -> str:
    """Generate a video for a single scene using Veo models.

    Args:
        scene: A dict containing 'scene_number' and 'veo_prompt'.
        video_id: Unique ID for this generation batch.
        output_dir: Directory to save the generated video.
        on_complete: Optional callback invoked when scene completes.

    Returns:
        The local file path of the downloaded video.
    """
    settings = get_settings()
    bucket = settings.gcs_bucket_name
    scene_number = scene["scene_number"]
    scene_id = f"scene_{scene_number:03d}"
    prompt = scene["veo_prompt"]

    output_gcs_uri = f"gs://{bucket}/video_{video_id}/{scene_id}/"
    local_path = os.path.join(output_dir, f"{scene_id}.mp4")

    os.makedirs(output_dir, exist_ok=True)

    logger.info("Generating video for %s with prompt: %s", scene_id, prompt)

    try:
        operation = _get_client().models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=8,
                output_gcs_uri=output_gcs_uri,
            ),
        )

        # Poll until the operation completes (with timeout)
        max_poll_seconds = settings.veo_poll_timeout_seconds
        poll_start = time.time()
        while not operation.done:
            if time.time() - poll_start > max_poll_seconds:
                raise TimeoutError(
                    f"Veo video generation for {scene_id} timed out after {max_poll_seconds}s"
                )
            logger.info("Waiting for %s video generation to complete...", scene_id)
            time.sleep(10)
            operation = _get_client().operations.get(operation)

        logger.info("Video generation complete for %s", scene_id)

        # Find the generated video in GCS and download it
        sc = _get_storage_client()
        bucket_obj = sc.bucket(bucket)
        blobs = list(bucket_obj.list_blobs(prefix=f"video_{video_id}/{scene_id}/"))

        video_blob = None
        for blob in blobs:
            if blob.name.endswith(".mp4"):
                video_blob = blob
                break

        if video_blob is None:
            raise RuntimeError(
                f"No .mp4 file found in gs://{bucket}/video_{video_id}/{scene_id}/ after generation"
            )

        gcs_video_uri = f"gs://{bucket}/{video_blob.name}"
        _download_from_gcs(gcs_video_uri, local_path)

        # Clean up GCS blobs after successful download
        _cleanup_gcs_blobs(blobs)

        if on_complete:
            on_complete()

        return local_path

    except Exception:
        logger.exception("Failed to generate video for %s", scene_id)
        raise


def generate_all_videos(
    scenes: list,
    output_dir: str,
    on_scene_complete: callable = None,
) -> list[str | None]:
    """Generate videos for all scenes in parallel.

    Args:
        scenes: A list of scene dicts, each with 'scene_number' and 'veo_prompt'.
        output_dir: Directory to save the generated videos.
        on_scene_complete: Optional callback invoked per scene completion.

    Returns:
        A list of local file paths (or None for failed scenes) in scene order.
    """
    os.makedirs(output_dir, exist_ok=True)

    async def _run_parallel() -> list[str | None]:
        loop = asyncio.get_event_loop()
        video_id: str = str(uuid4())
        with ThreadPoolExecutor() as executor:
            futures = [
                loop.run_in_executor(
                    executor,
                    generate_scene_video,
                    scene,
                    video_id,
                    output_dir,
                    on_scene_complete,
                )
                for scene in scenes
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        paths: list[str | None] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Scene %d failed: %s", scenes[i]["scene_number"], result
                )
                paths.append(None)
            else:
                paths.append(result)

        return paths

    return asyncio.run(_run_parallel())
