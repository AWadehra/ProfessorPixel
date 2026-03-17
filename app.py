"""
ProfessorPixel - Gradio Web Interface

AI-powered educational video generator with style presets, voice selection,
multi-language support, and storyboard editing.
"""

import json
import logging
import os
from datetime import datetime
from uuid import uuid4

import gradio as gr

from video_pipeline import run_pipeline
from video_pipeline.storyboard import generate_storyboard, STYLE_DIRECTIVES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- Constants ---

VOICE_OPTIONS = {
    "English - Male (Neural2-J)": "en-US-Neural2-J",
    "English - Female (Neural2-F)": "en-US-Neural2-F",
    "English - Male 2 (Neural2-D)": "en-US-Neural2-D",
    "English - Female 2 (Neural2-H)": "en-US-Neural2-H",
    "Spanish - Male (Neural2-A)": "es-ES-Neural2-A",
    "Spanish - Female (Neural2-B)": "es-ES-Neural2-B",
    "French - Male (Neural2-A)": "fr-FR-Neural2-A",
    "French - Female (Neural2-B)": "fr-FR-Neural2-B",
    "German - Male (Neural2-B)": "de-DE-Neural2-B",
    "German - Female (Neural2-A)": "de-DE-Neural2-A",
    "Japanese - Male (Neural2-C)": "ja-JP-Neural2-C",
    "Japanese - Female (Neural2-B)": "ja-JP-Neural2-B",
}

LANGUAGE_MAP = {
    "English": "English",
    "Spanish": "Spanish",
    "French": "French",
    "German": "German",
    "Japanese": "Japanese",
}

STYLE_OPTIONS = list(STYLE_DIRECTIVES.keys())

HISTORY_FILE = "output/history.json"

CUSTOM_CSS = """
.gradio-container { max-width: 1200px; margin: 0 auto; }
#header-md h1 {
    font-size: 2.5rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0;
}
#header-md p { color: #666; font-size: 1.05rem; }
#generate-btn { background: linear-gradient(135deg, #667eea, #764ba2) !important;
    border: none !important; font-size: 1.05rem !important; }
#preview-btn { font-size: 1.05rem !important; }
"""

# --- History helpers ---

def _load_history() -> list[dict]:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_history(entry: dict):
    history = _load_history()
    history.insert(0, entry)
    history = history[:50]
    os.makedirs("output", exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# --- Core functions ---

def preview_storyboard(topic: str, num_scenes: int, style: str, language: str):
    """Generate and preview a storyboard without generating videos."""
    if not topic or not topic.strip():
        raise gr.Error("Please enter a topic.")

    logger.info("Previewing storyboard for topic: %s (style=%s)", topic, style)
    storyboard = generate_storyboard(topic.strip(), num_scenes=int(num_scenes), style=style)

    formatted = json.dumps(storyboard, indent=2)
    return (
        storyboard,                # state
        formatted,                 # code display
        gr.update(visible=True),   # show storyboard output
        gr.update(visible=True),   # show confirm button
    )


def generate_video(
    topic: str,
    num_scenes: int,
    voice: str,
    style: str,
    language: str,
    speaking_rate: float,
    storyboard_state,
    progress=gr.Progress(),
):
    """Generate an educational video from a topic description."""
    if not topic or not topic.strip():
        raise gr.Error("Please enter a topic to generate a video about.")

    voice_name = VOICE_OPTIONS.get(voice)
    logger.info("Starting video generation for topic: %s (style=%s)", topic, style)

    def progress_callback(value, desc=""):
        progress(value, desc=desc)

    # Use unique output directory per run
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    output_dir = os.path.join("output", run_id)

    try:
        result = run_pipeline(
            topic.strip(),
            output_dir=output_dir,
            progress_callback=progress_callback,
            num_scenes=int(num_scenes),
            voice_name=voice_name,
            style=style,
            speaking_rate=speaking_rate,
        )

        # Show warning for partial failures
        if result.failed_scene_numbers:
            gr.Warning(
                f"Scenes {result.failed_scene_numbers} failed and were skipped. "
                f"Video contains {result.succeeded_scenes}/{result.total_scenes} scenes."
            )

        # Save to history
        _save_history({
            "run_id": run_id,
            "topic": topic.strip(),
            "style": style,
            "timestamp": datetime.now().isoformat(),
            "path": result.video_path,
            "scenes": result.total_scenes,
            "succeeded": result.succeeded_scenes,
        })

        logger.info("Video generated successfully: %s", result.video_path)
        return result.video_path
    except Exception as e:
        logger.exception("Video generation failed")
        raise gr.Error(f"Video generation failed: {e}")


def generate_from_storyboard(
    topic: str,
    num_scenes: int,
    voice: str,
    style: str,
    language: str,
    speaking_rate: float,
    storyboard_state,
    progress=gr.Progress(),
):
    """Generate video using a previously previewed storyboard."""
    if not storyboard_state:
        raise gr.Error("No storyboard previewed. Click 'Preview Storyboard' first.")

    voice_name = VOICE_OPTIONS.get(voice)
    logger.info("Generating from previewed storyboard for topic: %s", topic)

    def progress_callback(value, desc=""):
        progress(value, desc=desc)

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    output_dir = os.path.join("output", run_id)

    try:
        result = run_pipeline(
            topic.strip(),
            output_dir=output_dir,
            progress_callback=progress_callback,
            num_scenes=int(num_scenes),
            voice_name=voice_name,
            style=style,
            speaking_rate=speaking_rate,
            storyboard=storyboard_state,
        )

        if result.failed_scene_numbers:
            gr.Warning(
                f"Scenes {result.failed_scene_numbers} failed and were skipped. "
                f"Video contains {result.succeeded_scenes}/{result.total_scenes} scenes."
            )

        _save_history({
            "run_id": run_id,
            "topic": topic.strip(),
            "style": style,
            "timestamp": datetime.now().isoformat(),
            "path": result.video_path,
            "scenes": result.total_scenes,
            "succeeded": result.succeeded_scenes,
        })

        logger.info("Video generated successfully: %s", result.video_path)
        return result.video_path
    except Exception as e:
        logger.exception("Video generation failed")
        raise gr.Error(f"Video generation failed: {e}")


def load_history_videos():
    """Load history for the gallery tab."""
    history = _load_history()
    items = []
    for entry in history:
        if os.path.exists(entry.get("path", "")):
            items.append(entry)
    return items


# --- UI Layout ---

with gr.Blocks(title="ProfessorPixel") as demo:
    # Per-session storyboard state
    storyboard_state = gr.State(None)

    gr.Markdown(
        "# ProfessorPixel\n"
        "AI-powered educational video generator. Type any topic and get a cinematic video.\n\n"
        "Powered by Gemini + Veo 2 + Google Cloud TTS",
        elem_id="header-md",
    )

    with gr.Tabs():
        with gr.Tab("Generate"):
            with gr.Row():
                with gr.Column(scale=3):
                    topic_input = gr.Textbox(
                        placeholder="e.g. How does photosynthesis work?",
                        label="Topic",
                        lines=2,
                        elem_id="topic-input",
                    )
                with gr.Column(scale=1, min_width=280):
                    style_dropdown = gr.Dropdown(
                        choices=STYLE_OPTIONS,
                        value="cinematic",
                        label="Visual Style",
                    )
                    num_scenes_slider = gr.Slider(
                        minimum=3, maximum=10, value=8, step=1,
                        label="Number of Scenes",
                    )

            with gr.Row():
                with gr.Column(scale=1):
                    voice_dropdown = gr.Dropdown(
                        choices=list(VOICE_OPTIONS.keys()),
                        value="English - Male (Neural2-J)",
                        label="Narrator Voice",
                    )
                with gr.Column(scale=1):
                    language_dropdown = gr.Dropdown(
                        choices=list(LANGUAGE_MAP.keys()),
                        value="English",
                        label="Narration Language",
                    )
                with gr.Column(scale=1):
                    speaking_rate_slider = gr.Slider(
                        minimum=0.7, maximum=1.3, value=0.9, step=0.05,
                        label="Speaking Rate",
                    )

            with gr.Row():
                preview_btn = gr.Button("Preview Storyboard", variant="secondary", elem_id="preview-btn")
                generate_btn = gr.Button("Generate Video", variant="primary", size="lg", elem_id="generate-btn")

            storyboard_output = gr.Code(
                label="Storyboard Preview (read-only)", language="json", visible=False
            )
            confirm_btn = gr.Button(
                "Confirm & Generate Video from Storyboard", variant="primary", visible=False
            )

            video_output = gr.Video(label="Your Educational Video")

            gr.Examples(
                examples=[
                    "Explain Newton's three laws of motion",
                    "How does photosynthesis work?",
                    "What caused the French Revolution?",
                    "How do black holes form?",
                    "Explain how the internet works",
                ],
                inputs=topic_input,
            )

        with gr.Tab("History"):
            gr.Markdown("### Previously Generated Videos")
            history_display = gr.Dataframe(
                headers=["Topic", "Style", "Scenes", "Date", "Path"],
                label="Generation History",
                interactive=False,
            )
            refresh_btn = gr.Button("Refresh History", variant="secondary")

            def _format_history():
                history = _load_history()
                rows = []
                for entry in history:
                    rows.append([
                        entry.get("topic", ""),
                        entry.get("style", ""),
                        f"{entry.get('succeeded', '?')}/{entry.get('scenes', '?')}",
                        entry.get("timestamp", "")[:19],
                        entry.get("path", ""),
                    ])
                return rows

            refresh_btn.click(fn=_format_history, outputs=history_display)

    # --- Event wiring ---

    all_inputs = [
        topic_input, num_scenes_slider, voice_dropdown,
        style_dropdown, language_dropdown, speaking_rate_slider,
        storyboard_state,
    ]

    preview_btn.click(
        fn=preview_storyboard,
        inputs=[topic_input, num_scenes_slider, style_dropdown, language_dropdown],
        outputs=[storyboard_state, storyboard_output, storyboard_output, confirm_btn],
    )

    generate_btn.click(
        fn=generate_video,
        inputs=all_inputs,
        outputs=video_output,
    )

    confirm_btn.click(
        fn=generate_from_storyboard,
        inputs=all_inputs,
        outputs=video_output,
    )

    topic_input.submit(
        fn=generate_video,
        inputs=all_inputs,
        outputs=video_output,
    )

    # --- Keyboard shortcuts ---
    gr.HTML("""
    <script>
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const input = document.querySelector('#topic-input textarea');
            if (input) input.focus();
        }
    });
    </script>
    """)

if __name__ == "__main__":
    demo.launch()
