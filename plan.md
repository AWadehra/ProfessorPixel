# AI Educational Video Generator — Hackathon Plan

## Context
Build a chat interface where users describe a topic they want to learn, and the system generates a 1–2 minute educational video. The core challenge is that Veo 2 only generates 8-second clips — we solve this by having Gemini decompose the topic into a storyboard of 8–10 scenes, generating each scene as a Veo clip in parallel, generating TTS narration for each, then stitching everything together with MoviePy.

**Stack:** Gemini (storyboard + script) → Veo 2 via Vertex AI (video clips) → Google Cloud TTS (narration) → MoviePy (assembly) → Gradio (demo UI). They mentioned "Stitch" as their UI — Gradio is the Python-native fallback if Stitch can't serve the output video directly.

---

## System Architecture

```
User types topic (e.g. "explain Newton's laws")
        ↓
[1] Gemini 2.0 Flash: generate storyboard JSON
        ↓
[2] For each scene (parallel):
    ├── Veo 2 (Vertex AI): generate 8-sec video clip
    └── Google Cloud TTS: generate narration .mp3
        ↓
[3] MoviePy: overlay audio on each clip, stitch with crossfade
        ↓
Output: 1–2 min .mp4 video displayed in Gradio UI
```

---

## Critical Files to Create/Modify

| File | Purpose |
|------|---------|
| `main.py` | App entry point (currently hello world) |
| `app.py` | Gradio UI — chat input, progress display, video output |
| `video_pipeline/storyboard.py` | Gemini call → structured JSON storyboard |
| `video_pipeline/video_gen.py` | Veo 2 via Vertex AI, async polling |
| `video_pipeline/tts.py` | Google Cloud TTS narration per scene |
| `video_pipeline/assembler.py` | MoviePy: overlay audio, stitch clips |
| `video_pipeline/__init__.py` | Pipeline orchestrator |
| `pyproject.toml` | Add all dependencies |
| `.env` | API keys (not committed) |

---

## Phase 1: Storyboard Generation (`video_pipeline/storyboard.py`)

Call Gemini 2.0 Flash with a structured prompt to decompose the user's topic into scenes.

**Input:** `"Explain Newton's three laws of motion"`

**Output JSON schema:**
```json
{
  "title": "Newton's Three Laws of Motion",
  "scenes": [
    {
      "scene_number": 1,
      "duration_seconds": 8,
      "veo_prompt": "A slow-motion close-up of a tennis ball resting perfectly still on a table in a sunlit gym, cinematic, educational",
      "narration": "Newton's First Law states that an object at rest stays at rest — unless acted on by an external force.",
      "visual_description": "Still object to illustrate inertia"
    },
    ...
  ]
}
```

**Key prompt engineering rules for Veo:**
- Prompts must be visual, cinematic descriptions (not abstract concepts)
- Include: subject, action, environment, lighting, style
- Add "educational video style" or "cinematic" to each prompt
- Keep prompts consistent in visual style across all scenes (same lighting, similar aesthetic)
- 8–10 scenes = 64–80 seconds total, within 1–2 min target

**Gemini model:** `gemini-2.0-flash` (fast, cheap, JSON output)

---

## Phase 2: Video Generation (`video_pipeline/video_gen.py`)

**Veo 2 via Vertex AI (google-genai SDK):**
```python
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")

# Async: submit and poll
operation = client.models.generate_videos(
    model="veo-2.0-generate-001",
    prompt=scene["veo_prompt"],
    generate_videos_config=types.GenerateVideosConfig(
        aspect_ratio="16:9",
        number_of_videos=1,
        duration_seconds=8,
        output_gcs_uri=f"gs://{BUCKET}/{scene_id}/"
    ),
)
# Poll until done, download .mp4 from GCS
```

**Important details:**
- Veo 2 requires a GCS output bucket — need `google-cloud-storage` to download results
- Generation takes 30–90 seconds per clip; run all scenes in parallel with `asyncio.gather`
- Use `seed` parameter for visual consistency across scenes (same seed = similar style)
- Model: `veo-2.0-generate-001` (available on Vertex AI us-central1)
- Cost: ~$0.50/sec × 8 sec/clip × 8 clips = ~$32/video (use Veo 2 Fast or credits)

**Fallback if Veo quota is hit:** Use a static image per scene (Gemini Imagen 3) + pan/zoom effect via MoviePy ("Ken Burns effect") to simulate video.

---

## Phase 3: TTS Narration (`video_pipeline/tts.py`)

**Google Cloud TTS:**
```python
from google.cloud import texttospeech

client = texttospeech.TextToSpeechClient()
response = client.synthesize_speech(
    input=texttospeech.SynthesisInput(text=scene["narration"]),
    voice=texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-J",  # Natural male voice
        ssml_gender=texttospeech.SsmlVoiceGender.MALE
    ),
    audio_config=texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    ),
)
```

- Run TTS for all scenes in parallel with video generation (independent tasks)
- Save to `temp/scene_{n}_audio.mp3`
- Note actual audio duration — clip/pad video to match narration length

---

## Phase 4: Video Assembly (`video_pipeline/assembler.py`)

**MoviePy pipeline:**
```python
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip

def assemble_video(scenes, output_path):
    clips = []
    for scene in scenes:
        video = VideoFileClip(scene["video_path"])
        audio = AudioFileClip(scene["audio_path"])

        # Match video duration to audio (loop or trim video)
        audio_duration = audio.duration
        video = video.loop(duration=audio_duration) if audio_duration > video.duration \
                else video.subclipped(0, audio_duration)

        clip = video.with_audio(audio)
        clips.append(clip)

    # Crossfade transitions between clips
    final = concatenate_videoclips(clips, method="compose", padding=-0.5)

    # Add title overlay on first 3 seconds
    title = TextClip(storyboard["title"], font_size=60, color="white")
    title = title.with_position("center").with_duration(3)
    final = CompositeVideoClip([final, title.with_start(0)])

    final.write_videofile(output_path, fps=24, codec="libx264")
```

---

## Phase 5: Gradio UI (`app.py`)

```python
import gradio as gr

def generate_video(topic: str, progress=gr.Progress()):
    progress(0, desc="Generating storyboard...")
    storyboard = generate_storyboard(topic)

    progress(0.2, desc="Generating video clips and narration...")
    # Parallel generation

    progress(0.8, desc="Assembling final video...")
    output_path = assemble(storyboard)

    return output_path

with gr.Blocks(title="EduVid AI") as demo:
    gr.Markdown("# EduVid AI\nType any topic and get a 1–2 minute educational video")
    with gr.Row():
        topic_input = gr.Textbox(placeholder="e.g. How does photosynthesis work?")
        generate_btn = gr.Button("Generate Video", variant="primary")
    video_output = gr.Video(label="Your Educational Video")
    generate_btn.click(generate_video, inputs=topic_input, outputs=video_output)

demo.launch()
```

---

## Dependencies to add to `pyproject.toml`

```toml
dependencies = [
    "google-generativeai>=0.8.0",
    "google-cloud-aiplatform>=1.70.0",
    "google-cloud-texttospeech>=2.16.0",
    "google-cloud-storage>=2.14.0",
    "google-genai>=0.8.0",
    "moviepy>=2.0.0",
    "gradio>=4.0.0",
    "python-dotenv>=1.0.0",
]
```

---

## Environment Variables (`.env`)

```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GCS_BUCKET_NAME=your-bucket-for-veo-output
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

---

## Cost Estimates

| Component | Cost per video |
|-----------|---------------|
| Veo 2 (8 clips × 8 sec × $0.50) | ~$32 |
| Veo 2 Fast (8 clips × 8 sec × $0.15) | ~$10 |
| Google TTS (Neural2, ~500 chars/scene) | ~$0.02 |
| Gemini 2.0 Flash (storyboard) | ~$0.001 |
| **Total (budget)** | **~$10–32/video** |

**For hackathon demo:** Use Google Cloud free credits ($300). Pre-generate 2–3 demo videos to avoid live API costs during judging.

---

## Fallback Strategy (if Veo quota/cost is an issue)

Replace Phase 2 with **Imagen 3 + Ken Burns effect**:
- Gemini generates image prompt per scene
- Imagen 3 generates a still image ($0.04/image)
- MoviePy applies pan/zoom animation to simulate video
- Total cost: ~$0.50 per video (vs $32 with Veo)

---

## Implementation Order

1. `pyproject.toml` — add dependencies
2. `video_pipeline/storyboard.py` — Gemini storyboard (test first, cheapest)
3. `video_pipeline/tts.py` — TTS narration (easy, test independently)
4. `video_pipeline/assembler.py` — MoviePy stitching (test with static clips)
5. `video_pipeline/video_gen.py` — Veo 2 integration (most complex, test last)
6. `video_pipeline/__init__.py` — orchestrator with asyncio.gather
7. `app.py` — Gradio UI
8. `main.py` — update entry point

---

## Verification

1. Run `uv run python -c "from video_pipeline.storyboard import generate_storyboard; print(generate_storyboard('gravity'))"` — verify Gemini returns valid JSON
2. Run `uv run python -c "from video_pipeline.tts import generate_narration; generate_narration('Hello world', 'test.mp3')"` — verify TTS saves audio
3. Run `uv run python -c "from video_pipeline.assembler import test_stitch"` — verify MoviePy can concatenate test clips
4. Run `uv run python app.py` — open Gradio at localhost:7860, enter a topic, verify full pipeline produces a downloadable video
5. Test with 3 representative topics: simple science concept, math concept, historical event
