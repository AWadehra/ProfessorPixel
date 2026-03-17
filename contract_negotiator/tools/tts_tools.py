"""Text-to-Speech with async support, client pooling, and caching."""

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor

from google.cloud import texttospeech

# Pooled client — one connection, reused for all TTS calls
_tts_client: texttospeech.TextToSpeechClient | None = None
_executor = ThreadPoolExecutor(max_workers=2)

# Cache: (text_hash, voice_name) -> mp3 bytes
_tts_cache: dict[tuple[str, str], bytes] = {}
_MAX_CACHE_ENTRIES = 200


def _get_tts_client() -> texttospeech.TextToSpeechClient:
    global _tts_client
    if _tts_client is None:
        _tts_client = texttospeech.TextToSpeechClient()
    return _tts_client


def _synthesize_sync(text: str, voice_name: str, speaking_rate: float) -> bytes:
    """Sync TTS synthesis — called from thread pool only."""
    client = _get_tts_client()
    if len(text) > 5000:
        text = text[:4997] + "..."

    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
        ),
    )
    return response.audio_content


# Predefined voice profiles for each agent
VOICES = {
    "BuyerLawyer": ("en-US-Neural2-D", 1.05),
    "BuyerRebuttal": ("en-US-Neural2-D", 1.05),
    "SellerLawyer": ("en-US-Neural2-C", 1.05),
    "SellerRebuttal": ("en-US-Neural2-C", 1.05),
    "Mediator": ("en-US-Neural2-A", 1.0),
}

VALID_AGENT_NAMES = frozenset(VOICES.keys())


async def agent_speak(text: str, agent_name: str) -> bytes:
    """Async TTS with in-process cache. Runs synthesis in thread pool."""
    if agent_name not in VOICES:
        raise ValueError(f"Unknown agent '{agent_name}'")

    voice_name, rate = VOICES[agent_name]

    cache_key = (hashlib.sha256(text.encode()).hexdigest(), voice_name)
    if cache_key in _tts_cache:
        return _tts_cache[cache_key]

    loop = asyncio.get_running_loop()
    audio_bytes = await loop.run_in_executor(
        _executor, _synthesize_sync, text, voice_name, rate
    )

    # Evict oldest entry if cache is full
    if len(_tts_cache) >= _MAX_CACHE_ENTRIES:
        oldest_key = next(iter(_tts_cache))
        del _tts_cache[oldest_key]

    _tts_cache[cache_key] = audio_bytes
    return audio_bytes
