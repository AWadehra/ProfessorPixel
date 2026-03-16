"""Storyboard generation module.

Calls Gemini 2.0 Flash via Vertex AI to decompose a user's topic into a structured
JSON storyboard for an educational video.
"""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

_client = None


def _get_client() -> genai.Client:
    """Lazily initialize the Vertex AI genai client."""
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    return _client


SYSTEM_PROMPT = """\
You are an expert educational video planner. Given a topic, you decompose it \
into a storyboard of 8-10 scenes for a short educational video.

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
"scenes" array.
"""


def generate_storyboard(topic: str) -> dict:
    """Generate a structured storyboard for an educational video on the given topic.

    Args:
        topic: The educational topic to create a storyboard for.

    Returns:
        A dict with "title" (str) and "scenes" (list of scene dicts).

    Raises:
        ValueError: If the topic is empty or the API response cannot be parsed.
        RuntimeError: If the Gemini API call fails.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    client = _get_client()

    user_prompt = (
        f"Create a detailed storyboard for an educational video about: {topic}\n\n"
        "Return 8-10 scenes. Each scene must have: scene_number, "
        "duration_seconds (always 8), veo_prompt, narration, and visual_description. Make sure the output is a valid JSON object."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    try:
        storyboard = json.loads(response.text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"Failed to parse storyboard JSON from Gemini response: {exc}"
        ) from exc

    if "title" not in storyboard or "scenes" not in storyboard:
        raise ValueError(
            "Gemini response is missing required keys ('title' and/or 'scenes')."
        )

    return storyboard
