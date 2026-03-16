"""
EduVid AI - Gradio Web Interface

Chat-style UI where users describe a topic and get an educational video.
"""

import logging

import gradio as gr

from video_pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def generate_video(topic: str, progress=gr.Progress()):
    """Generate an educational video from a topic description."""
    if not topic or not topic.strip():
        raise gr.Error("Please enter a topic to generate a video about.")

    logger.info("Starting video generation for topic: %s", topic)

    def progress_callback(value, desc=""):
        progress(value, desc=desc)

    try:
        output_path = run_pipeline(topic.strip(), output_dir="output", progress_callback=progress_callback)
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
            generate_btn = gr.Button("Generate Video", variant="primary", size="lg")

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

    generate_btn.click(
        fn=generate_video,
        inputs=topic_input,
        outputs=video_output,
    )

    topic_input.submit(
        fn=generate_video,
        inputs=topic_input,
        outputs=video_output,
    )

if __name__ == "__main__":
    demo.launch()
