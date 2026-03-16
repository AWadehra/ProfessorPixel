"""Video generation module using Veo 2 via the google-genai SDK (Vertex AI)."""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from uuid import uuid4

from dotenv import load_dotenv
from google import genai
from google.cloud import storage
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
BUCKET = os.environ.get("GCS_BUCKET_NAME")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def  _get_client() -> genai.Client:
    """Lazily initialize the Vertex AI genai client."""
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    return _client


def _download_from_gcs(gcs_uri: str, local_path: str) -> str:
    """Download a file from GCS to a local path.

    Args:
        gcs_uri: The GCS URI (gs://bucket/path/to/file).
        local_path: The local file path to save to.

    Returns:
        The local file path.
    """
    parsed = urlparse(gcs_uri)
    bucket_name = parsed.netloc
    blob_path = parsed.path.lstrip("/")

    storage_client = storage.Client()
    bucket_obj = storage_client.bucket(bucket_name)
    blob = bucket_obj.blob(blob_path)

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    logger.info("Downloaded %s to %s", gcs_uri, local_path)
    return local_path


def generate_scene_video(scene: dict, video_id: str, output_dir: str) -> str:
    """Generate a video for a single scene using Veo models.

    Args:
        scene: A dict containing 'scene_number' and 'veo_prompt'.
        output_dir: Directory to save the generated video.

    Returns:
        The local file path of the downloaded video.
    """
    scene_number = scene["scene_number"]
    scene_id = f"scene_{scene_number:03d}"
    prompt = scene["veo_prompt"]
    

    output_gcs_uri = f"gs://{BUCKET}/video_{video_id}/{scene_id}/"
    local_path = os.path.join(output_dir, f"{scene_id}.mp4")

    os.makedirs(output_dir, exist_ok=True)

    logger.info("Generating video for %s with prompt: %s", scene_id, prompt)

    try:
        operation = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=8,
                output_gcs_uri=output_gcs_uri,
            ),
        )

        # Poll until the operation completes
        while not operation.done:
            logger.info("Waiting for %s video generation to complete...", scene_id)
            time.sleep(10)
            operation = client.operations.get(operation)

        logger.info("Video generation complete for %s", scene_id)

        # Find the generated video in GCS and download it
        storage_client = storage.Client()
        bucket_obj = storage_client.bucket(BUCKET)
        blobs = list(bucket_obj.list_blobs(prefix=f"video_{video_id}/{scene_id}/"))

        video_blob = None
        for blob in blobs:
            if blob.name.endswith(".mp4"):
                video_blob = blob
                break

        if video_blob is None:
            raise RuntimeError(
                f"No .mp4 file found in gs://{BUCKET}/video_{video_id}/{scene_id}/ after generation"
            )

        # We don't need the full prefix, because it is included in the video_blob.name
        gcs_video_uri = f"gs://{BUCKET}/{video_blob.name}"
        _download_from_gcs(gcs_video_uri, local_path)

        return local_path

    except Exception:
        logger.exception("Failed to generate video for %s", scene_id)
        raise


def generate_all_videos(scenes: list, output_dir: str) -> list[str]:
    """Generate videos for all scenes in parallel.

    Args:
        scenes: A list of scene dicts, each with 'scene_number' and 'veo_prompt'.
        output_dir: Directory to save the generated videos.

    Returns:
        A list of local file paths in scene order.
    """
    os.makedirs(output_dir, exist_ok=True)

    async def _run_parallel() -> list[str]:
        loop = asyncio.get_event_loop()
        video_id: str = str(uuid4())
        with ThreadPoolExecutor() as executor:
            futures = [
                loop.run_in_executor(
                    executor, generate_scene_video, scene, video_id, output_dir
                )
                for scene in scenes
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        paths: list[str] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Scene %d failed: %s", scenes[i]["scene_number"], result
                )
                raise result
            paths.append(result)

        return paths

    return asyncio.run(_run_parallel())
