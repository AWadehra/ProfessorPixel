"""Cloud Translation API with async support and client pooling."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from google.cloud import translate_v2 as translate

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

_translate_client: translate.Client | None = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_client() -> translate.Client:
    global _translate_client
    if _translate_client is None:
        _translate_client = translate.Client()
    return _translate_client


def _detect_language_sync(text: str) -> dict:
    """Detect the language of the text."""
    client = _get_client()
    # Use first 500 chars for detection (faster, same accuracy)
    result = client.detect_language(text[:500])
    return {
        "language": result["language"],
        "confidence": result.get("confidence", 0),
    }


def _translate_sync(text: str, target: str = "en", source: str | None = None) -> str:
    """Translate text to target language."""
    client = _get_client()
    # Cloud Translation has a 100K char limit per request
    if len(text) > 100_000:
        text = text[:100_000]
    result = client.translate(text, target_language=target, source_language=source)
    return result["translatedText"]


async def detect_language(text: str) -> dict:
    """Async language detection. Returns {language: 'es', confidence: 0.98}."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _detect_language_sync, text)


async def translate_text(text: str, target: str = "en", source: str | None = None) -> str:
    """Async translation. Returns translated text."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _translate_sync, text, target, source)
