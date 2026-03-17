"""Google Cloud Text-to-Speech narration generation for video scenes."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.cloud import texttospeech
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings

logger = logging.getLogger(__name__)

_tts_client = None


def _get_tts_client() -> texttospeech.TextToSpeechClient:
    """Lazily initialize the TTS client."""
    global _tts_client
    if _tts_client is None:
        _tts_client = texttospeech.TextToSpeechClient()
    return _tts_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def _synthesize(client, synthesis_input, voice, audio_config):
    return client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )


def generate_narration(
    text: str,
    output_path: str,
    voice_name: str | None = None,
    on_complete: callable = None,
) -> str:
    """Synthesize speech from text and write the audio to output_path.

    Args:
        text: The narration text to synthesize.
        output_path: File path where the MP3 audio will be saved.
        voice_name: TTS voice name (e.g. "en-US-Neural2-J"). Uses default if None.
        on_complete: Optional callback invoked on success.

    Returns:
        The output_path that was written to.

    Raises:
        RuntimeError: If speech synthesis or file writing fails.
    """
    if voice_name is None:
        voice_name = get_settings().default_voice

    try:
        client = _get_tts_client()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_name[:5],  # e.g. "en-US"
            name=voice_name,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        logger.info("Synthesizing narration for: %.80s...", text)

        response = _synthesize(client, synthesis_input, voice, audio_config)

        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        logger.info("Narration saved to %s", output_path)

        if on_complete:
            on_complete()

        return output_path

    except Exception as e:
        logger.error("Failed to generate narration for text '%.50s...': %s", text, e)
        raise RuntimeError(
            f"Speech synthesis failed for text '{text[:50]}...': {e}"
        ) from e


def generate_all_narrations(
    scenes: list,
    output_dir: str,
    voice_name: str | None = None,
    on_scene_complete: callable = None,
) -> list[str | None]:
    """Generate narration audio for every scene in parallel.

    Args:
        scenes: List of scene dicts with ``scene_number`` and ``narration`` keys.
        output_dir: Directory where audio files will be written.
        voice_name: TTS voice name. Uses default if None.
        on_scene_complete: Optional callback invoked per scene completion.

    Returns:
        List of audio file paths (or None for failures) in scene order.
    """
    os.makedirs(output_dir, exist_ok=True)

    logger.info(
        "Generating narrations for %d scene(s) in %s", len(scenes), output_dir
    )

    tasks: dict[int, tuple[str, str]] = {}
    for scene in scenes:
        scene_number: int = scene["scene_number"]
        narration_text: str = scene["narration"]
        filename = f"scene_{scene_number:03d}_audio.mp3"
        path = os.path.join(output_dir, filename)
        tasks[scene_number] = (narration_text, path)

    results: dict[int, str | None] = {}

    with ThreadPoolExecutor() as executor:
        future_to_scene = {
            executor.submit(
                generate_narration, text, path, voice_name, on_scene_complete
            ): scene_num
            for scene_num, (text, path) in tasks.items()
        }

        for future in as_completed(future_to_scene):
            scene_num = future_to_scene[future]
            try:
                audio_path = future.result()
                results[scene_num] = audio_path
                logger.info("Scene %d narration complete.", scene_num)
            except Exception as e:
                logger.error("Scene %d narration failed: %s", scene_num, e)
                results[scene_num] = None

    audio_paths = [results[num] for num in sorted(results)]
    succeeded = sum(1 for p in audio_paths if p is not None)
    logger.info("%d/%d narration(s) generated successfully.", succeeded, len(audio_paths))
    return audio_paths
