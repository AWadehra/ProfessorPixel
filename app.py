"""
EduVid AI - Gradio Web Interface

Chat-style UI where users describe a topic and get an educational video.
"""

import json
import logging

import gradio as gr

from video_pipeline import run_pipeline
from video_pipeline.storyboard import generate_storyboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

VOICE_OPTIONS = {
    "Male (Neural2-J)": "en-US-Neural2-J",
    "Female (Neural2-F)": "en-US-Neural2-F",
    "Male 2 (Neural2-D)": "en-US-Neural2-D",
    "Female 2 (Neural2-H)": "en-US-Neural2-H",
}

# Module-level storyboard cache for the preview flow
_cached_storyboard = {"topic": None, "data": None}


def preview_storyboard(topic: str, num_scenes: int):
    """Generate and preview a storyboard without generating videos."""
    if not topic or not topic.strip():
        raise gr.Error("Please enter a topic.")

    logger.info("Previewing storyboard for topic: %s", topic)
    storyboard = generate_storyboard(topic.strip(), num_scenes=int(num_scenes))

    _cached_storyboard["topic"] = topic.strip()
    _cached_storyboard["data"] = storyboard

    formatted = json.dumps(storyboard, indent=2)
    return (
        formatted,
        gr.update(visible=True),  # show storyboard output
        gr.update(visible=True),  # show confirm button
    )


def generate_video(topic: str, num_scenes: int, voice: str, progress=gr.Progress()):
    """Generate an educational video from a topic description."""
    if not topic or not topic.strip():
        raise gr.Error("Please enter a topic to generate a video about.")

    voice_name = VOICE_OPTIONS.get(voice)
    logger.info("Starting video generation for topic: %s", topic)

    def progress_callback(value, desc=""):
        progress(value, desc=desc)

    try:
        output_path = run_pipeline(
            topic.strip(),
            output_dir="output",
            progress_callback=progress_callback,
            num_scenes=int(num_scenes),
            voice_name=voice_name,
        )
        logger.info("Video generated successfully: %s", output_path)
        return output_path
    except Exception as e:
        logger.exception("Video generation failed")
        raise gr.Error(f"Video generation failed: {e}")


with gr.Blocks(title="EduVid AI") as demo:
    gr.Markdown(
        "# EduVid AI\n"
        "Type any topic and get a 1-2 minute educational video.\n\n"
        "Powered by Gemini + Veo 2 + Google Cloud TTS"
    )

    with gr.Row():
        with gr.Column(scale=3):
            topic_input = gr.Textbox(
                placeholder="e.g. How does photosynthesis work?",
                label="Topic",
                lines=2,
            )
        with gr.Column(scale=1):
            num_scenes_slider = gr.Slider(
                minimum=3, maximum=10, value=8, step=1,
                label="Number of Scenes",
            )
            voice_dropdown = gr.Dropdown(
                choices=list(VOICE_OPTIONS.keys()),
                value="Male (Neural2-J)",
                label="Narrator Voice",
            )

    with gr.Row():
        preview_btn = gr.Button("Preview Storyboard", variant="secondary")
        generate_btn = gr.Button("Generate Video", variant="primary", size="lg")

    storyboard_output = gr.Code(
        label="Storyboard Preview", language="json", visible=False
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

    # Preview storyboard
    preview_btn.click(
        fn=preview_storyboard,
        inputs=[topic_input, num_scenes_slider],
        outputs=[storyboard_output, storyboard_output, confirm_btn],
    )

    # Generate video directly
    generate_btn.click(
        fn=generate_video,
        inputs=[topic_input, num_scenes_slider, voice_dropdown],
        outputs=video_output,
    )

    # Generate from previewed storyboard
    confirm_btn.click(
        fn=generate_video,
        inputs=[topic_input, num_scenes_slider, voice_dropdown],
        outputs=video_output,
    )

    # Enter key triggers generation
    topic_input.submit(
        fn=generate_video,
        inputs=[topic_input, num_scenes_slider, voice_dropdown],
        outputs=video_output,
    )

if __name__ == "__main__":
    demo.launch()
