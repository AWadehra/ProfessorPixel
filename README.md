# ProfessorPixel

AI-powered educational video generator that transforms any topic into a polished 1-2 minute video. Type a subject, get a video — powered entirely by Google Cloud AI.

Built for the **Google Hackathon 2026**.

## How It Works

```
User types a topic (e.g. "How does photosynthesis work?")
        |
        v
[Gemini 2.5 Flash] -- generates a structured storyboard (8-10 scenes)
        |
        v
  Parallel execution:
  |-- [Veo 2]              -- generates 8-second video clips per scene
  |-- [Google Cloud TTS]   -- generates narration audio per scene
        |
        v
[FFmpeg Assembler] -- muxes audio+video, concatenates, adds title & subtitles
        |
        v
  Final 1-2 min MP4 video served in a Gradio web UI
```

## Features

- **5 Visual Styles** — Cinematic, Documentary, Whiteboard, Animated, Sci-Fi
- **12 Neural Voices** — English, Spanish, French, German, Japanese (male & female)
- **Adjustable Speaking Rate** — 0.7x to 1.3x via SSML prosody control
- **Scene Continuity** — Gemini creates overlapping visual bridges between scenes (like RAG chunking) for seamless flow
- **Storyboard Preview** — Review and tweak the plan before committing to video generation
- **Storyboard Caching** — Repeat topics return instantly without API calls
- **Imagen 3 Fallback** — If Veo fails, automatically falls back to Imagen 3 + Ken Burns zoom effect (~98% cost savings on retries)
- **FFmpeg Assembly** — 10-50x faster than MoviePy via stream-copy + single re-encode
- **Burned-In Subtitles** — Narration text overlaid on each scene via FFmpeg drawtext
- **Generation History** — Browse and replay past videos from the History tab
- **Partial Success Handling** — Failed scenes are skipped; the video still assembles from what succeeded

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Storyboard | Gemini 2.5 Flash | Decomposes topic into scene-by-scene JSON |
| Video | Veo 2 (Vertex AI) | Generates 8-sec cinematic clips per scene |
| Fallback | Imagen 3 + Ken Burns | Static image with zoom effect if Veo fails |
| Narration | Google Cloud TTS (Neural2) | Natural-sounding speech per scene |
| Assembly | FFmpeg | Mux, concat, title overlay, subtitle burn-in |
| Config | Pydantic Settings | Validated environment-based configuration |
| UI | Gradio 4.0 | Web interface with tabs, controls, progress |
| Retry | Tenacity | Exponential backoff on API failures |

## Project Structure

```
.
├── main.py                          # Entry point — launches Gradio
├── app.py                           # Gradio UI (Generate + History tabs)
├── video_pipeline/
│   ├── __init__.py                  # Pipeline orchestrator (run_pipeline)
│   ├── config.py                    # Pydantic settings (env vars)
│   ├── models.py                    # Pydantic schemas (Scene, Storyboard)
│   ├── storyboard.py                # Gemini storyboard generation + caching
│   ├── video_gen.py                 # Veo 2 video generation + GCS download
│   ├── image_gen.py                 # Imagen 3 fallback + Ken Burns effect
│   ├── tts.py                       # Google Cloud TTS narration
│   └── assembler.py                 # FFmpeg 3-stage assembly pipeline
├── plan.md                          # Original architecture design
├── Dockerfile                       # Container for Cloud Run deployment
├── pyproject.toml                   # Dependencies (uv)
└── .env.example                     # Required environment variables
```

## Setup

### Prerequisites

- Python 3.11-3.13
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- FFmpeg installed and on PATH
- A Google Cloud project with these APIs enabled:
  - Vertex AI API
  - Cloud Text-to-Speech API
  - Cloud Storage API

### 1. Clone and install

```bash
git clone https://github.com/YOUR-USERNAME/professor-pixel.git
cd professor-pixel
uv sync
```

### 2. Google Cloud credentials

Create a service account with these roles:
- `Vertex AI User`
- `Storage Admin`
- `Cloud Text-to-Speech Agent`

Download the JSON key and place it in the project root.

### 3. Create a GCS bucket

```bash
gcloud storage buckets create gs://your-bucket-name --location=us-central1
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GCS_BUCKET_NAME=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=./your-service-account.json
```

### 5. Run

```bash
uv run python main.py
```

Open **http://localhost:7860** in your browser.

## Docker

```bash
docker build -t professorpixel .
docker run -p 7860:7860 --env-file .env professorpixel
```

## Performance

| Stage | Time | Notes |
|-------|------|-------|
| Storyboard (Gemini) | ~18s | 0s on cache hit |
| TTS narration | ~2s | All scenes in parallel |
| Veo 2 video generation | ~60s | All scenes in parallel (API floor) |
| FFmpeg assembly | ~5-10s | Stream-copy + single re-encode |
| **Total** | **~1.5 min** | |

## Cost per Video

| Component | Cost |
|-----------|------|
| Veo 2 (8 clips x 8s) | ~$10-32 |
| Imagen 3 fallback (per scene) | ~$0.04 |
| Google TTS (Neural2) | ~$0.02 |
| Gemini 2.5 Flash (storyboard) | ~$0.001 |

## License

MIT
