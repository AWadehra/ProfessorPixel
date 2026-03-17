"""Storyboard generation module.

Calls Gemini 2.5 Flash via Vertex AI to decompose a user's topic into a structured
JSON storyboard for an educational video.
"""

import hashlib
import json
import logging
import os
import tempfile

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings
from .models import Storyboard

logger = logging.getLogger(__name__)

_client = None

CACHE_DIR = os.path.join(tempfile.gettempdir(), "eduvid_storyboard_cache")


def _get_client() -> genai.Client:
    """Lazily initialize the Vertex AI genai client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return _client


def _build_system_prompt(num_scenes: int) -> str:
    return f"""\
You are an expert educational video planner. Given a topic, you decompose it \
into a storyboard of {num_scenes} scenes for a short educational video.

Rules:
1. Each scene lasts exactly 8 seconds (duration_seconds = 8).
2. The "veo_prompt" for each scene MUST be a vivid, visual, cinematic \
description suitable for an AI video generator. It must include the \
subject, action, environment, lighting, and style. Never use abstract \
or vague language. Always append "educational video style, cinematic" \
to every veo_prompt.
3. Keep the visual style consistent across all scenes (same color palette, \
lighting mood, and cinematographic approach).
4. The "narration" for each scene must be concise: 1-2 sentences that can \
be comfortably spoken aloud in 8 seconds.
5. The "visual_description" is a short plain-English summary of what the \
viewer sees on screen.
6. Return a JSON object with a "title" (a compelling video title) and a \
"scenes" array.\
"""


def _cache_key(topic: str, num_scenes: int) -> str:
    raw = f"{topic.strip().lower()}:{num_scenes}"
    return hashlib.sha256(raw.encode()).hexdigest()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def _call_gemini(client: genai.Client, user_prompt: str, system_prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    return response.text


def generate_storyboard(topic: str, num_scenes: int = 8, use_cache: bool = True) -> dict:
    """Generate a structured storyboard for an educational video on the given topic.

    Args:
        topic: The educational topic to create a storyboard for.
        num_scenes: Number of scenes to generate (default 8).
        use_cache: Whether to use cached storyboards for repeated topics.

    Returns:
        A dict with "title" (str) and "scenes" (list of scene dicts).

    Raises:
        ValueError: If the topic is empty or the API response cannot be parsed.
        RuntimeError: If the Gemini API call fails.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    # Check cache
    key = _cache_key(topic, num_scenes)
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    if use_cache and os.path.exists(cache_path):
        logger.info("Storyboard cache hit for topic: %s", topic)
        with open(cache_path) as f:
            return json.load(f)

    client = _get_client()
    system_prompt = _build_system_prompt(num_scenes)

    user_prompt = (
        f"Create a detailed storyboard for an educational video about: {topic}\n\n"
        f"Return exactly {num_scenes} scenes. Each scene must have: scene_number, "
        "duration_seconds (always 8), veo_prompt, narration, and visual_description. "
        "Make sure the output is a valid JSON object."
    )

    try:
        raw_text = _call_gemini(client, user_prompt, system_prompt)
    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    try:
        storyboard_data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"Failed to parse storyboard JSON from Gemini response: {exc}"
        ) from exc

    # Validate with Pydantic
    validated = Storyboard.model_validate(storyboard_data)
    result = validated.model_dump()

    # Save to cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(result, f)
    logger.info("Storyboard cached for topic: %s", topic)

    return result
