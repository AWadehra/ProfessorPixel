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


FEW_SHOT_EXAMPLE = """\

Here is an example of a high-quality scene for reference:
{
  "scene_number": 1,
  "duration_seconds": 8,
  "veo_prompt": "Extreme close-up of a gleaming red apple resting motionless on a polished oak table inside a sunlit university laboratory. Camera slowly pushes in. Warm golden afternoon light through tall windows. Shallow depth of field, 35mm cinematic, educational video style.",
  "narration": "An object at rest stays at rest until an outside force acts on it.",
  "visual_description": "Still apple on a table — inertia visualised"
}
Use this level of visual specificity for every scene.
"""

STYLE_DIRECTIVES = {
    "cinematic": (
        "Visual style: cinematic, film-quality, shallow depth of field, warm color grade. "
        'Append "educational video style, cinematic" to every veo_prompt.'
    ),
    "documentary": (
        "Visual style: documentary, natural lighting, handheld feel, desaturated realism. "
        'Append "documentary style, natural lighting, 4K" to every veo_prompt.'
    ),
    "whiteboard": (
        "Visual style: whiteboard animation on a white background, black marker lines drawing diagrams. "
        'Append "whiteboard animation, clean white background, black ink drawing" to every veo_prompt.'
    ),
    "animated": (
        "Visual style: bright 2D cartoon animation, flat design, vivid saturated colors. "
        'Append "2D cartoon animation, flat design, bright colors" to every veo_prompt.'
    ),
    "sci-fi": (
        "Visual style: futuristic sci-fi aesthetic, neon lighting, holographic displays, dark environment. "
        'Append "futuristic sci-fi, neon holographic, dark cinematic" to every veo_prompt.'
    ),
}


def _build_system_prompt(num_scenes: int, style: str = "cinematic") -> str:
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
4. The "narration" for each scene MUST be 20 words or fewer — that is a \
hard limit (approximately 8 seconds of speech). Prefer a single punchy sentence.
5. The "visual_description" is a short plain-English summary of what the \
viewer sees on screen.
6. Return a JSON object with a "title" (a compelling video title) and a \
"scenes" array.
7. SCENE CONTINUITY (critical): Each scene must share a visual bridge with \
its neighbors — like overlapping chunks. The ending visual of scene N must \
match the opening visual of scene N+1: same subject, environment, or camera \
angle. For example, if scene 2 ends on "camera slowly zooms out from a prism \
splitting white light into a rainbow", scene 3 should open with "starting \
from a wide shot of a prism refracting light, the camera pans to reveal..." \
This creates seamless flow between clips even without video transitions.
8. {STYLE_DIRECTIVES.get(style, STYLE_DIRECTIVES["cinematic"])}\
"""


def _cache_key(topic: str, num_scenes: int, style: str = "cinematic") -> str:
    raw = f"{topic.strip().lower()}:{num_scenes}:{style}"
    return hashlib.sha256(raw.encode()).hexdigest()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def _call_gemini(client: genai.Client, user_prompt: str, system_prompt: str, model: str = "gemini-2.5-flash") -> str:
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    return response.text


def generate_storyboard(topic: str, num_scenes: int = 8, style: str = "cinematic", use_cache: bool = True) -> dict:
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
    key = _cache_key(topic, num_scenes, style)
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    if use_cache and os.path.exists(cache_path):
        logger.info("Storyboard cache hit for topic: %s", topic)
        with open(cache_path) as f:
            return json.load(f)

    client = _get_client()
    settings = get_settings()
    system_prompt = _build_system_prompt(num_scenes, style=style)

    user_prompt = (
        f"Create a detailed storyboard for an educational video about: {topic}\n\n"
        + FEW_SHOT_EXAMPLE
        + f"\nReturn exactly {num_scenes} scenes. Each scene must have: scene_number, "
        "duration_seconds (always 8), veo_prompt, narration, and visual_description. "
        "Make sure the output is a valid JSON object."
    )

    try:
        raw_text = _call_gemini(client, user_prompt, system_prompt, model=settings.storyboard_model)
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
