"""EduVid AI - Entry point."""

import gradio as gr

from app import demo


def main():
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft())


if __name__ == "__main__":
    main()
