"""Google Cloud Text-to-Speech narration generation for video scenes."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from google.cloud import texttospeech

load_dotenv()

logger = logging.getLogger(__name__)


def generate_narration(text: str, output_path: str) -> str:
    """Synthesize speech from text and write the audio to output_path.

    Args:
        text: The narration text to synthesize.
        output_path: File path where the MP3 audio will be saved.

    Returns:
        The output_path that was written to.

    Raises:
        RuntimeError: If speech synthesis or file writing fails.
    """
    try:
        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-J",
            ssml_gender=texttospeech.SsmlVoiceGender.MALE,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        logger.info("Synthesizing narration for: %.80s...", text)

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        logger.info("Narration saved to %s", output_path)
        return output_path

    except Exception as e:
        logger.error("Failed to generate narration for text '%.50s...': %s", text, e)
        raise RuntimeError(
            f"Speech synthesis failed for text '{text[:50]}...': {e}"
        ) from e


def generate_all_narrations(scenes: list, output_dir: str) -> list[str]:
    """Generate narration audio for every scene in parallel.

    Args:
        scenes: List of scene dicts, each containing at least
            ``scene_number`` (int) and ``narration`` (str) keys.
        output_dir: Directory where audio files will be written.

    Returns:
        List of audio file paths in scene order.

    Raises:
        RuntimeError: If any individual narration generation fails.
    """
    os.makedirs(output_dir, exist_ok=True)

    logger.info(
        "Generating narrations for %d scene(s) in %s", len(scenes), output_dir
    )

    # Build a mapping of scene_number -> (text, output_path) so we can
    # preserve ordering after parallel execution.
    tasks: dict[int, tuple[str, str]] = {}
    for scene in scenes:
        scene_number: int = scene["scene_number"]
        narration_text: str = scene["narration"]
        filename = f"scene_{scene_number:03d}_audio.mp3"
        path = os.path.join(output_dir, filename)
        tasks[scene_number] = (narration_text, path)

    results: dict[int, str] = {}

    with ThreadPoolExecutor() as executor:
        future_to_scene = {
            executor.submit(generate_narration, text, path): scene_num
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
                raise

    # Return paths sorted by scene number.
    audio_paths = [results[num] for num in sorted(results)]
    logger.info("All %d narration(s) generated successfully.", len(audio_paths))
    return audio_paths
