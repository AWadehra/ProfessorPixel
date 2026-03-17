"""ProfessorPixel - Entry point."""

import gradio as gr

from app import demo, CUSTOM_CSS


def main():
    theme = gr.themes.Base(
        primary_hue=gr.themes.colors.violet,
        secondary_hue=gr.themes.colors.purple,
        neutral_hue=gr.themes.colors.gray,
    )
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=theme, css=CUSTOM_CSS)


if __name__ == "__main__":
    main()
