# ProfessorPixel — Comprehensive Improvement Roadmap

## Current State

ProfessorPixel (EduVid AI) generates 1-2 minute educational videos from a text topic using:
**Gemini 2.5 Flash** (storyboard) → **Veo 2** (8s video clips, parallel) → **Google Cloud TTS** (narration, parallel) → **MoviePy** (assembly) → **Gradio UI**

### Current Pipeline Timing (7 scenes)
| Phase | Time | Bottleneck Level |
|-------|------|-----------------|
| Storyboard (Gemini) | ~18s (0s cached) | Low |
| TTS narration (parallel) | ~2s | None |
| Veo 2 video gen (parallel) | ~60s | API floor — cannot reduce |
| GCS download | ~10s | Low |
| MoviePy assembly + render | ~2 min | **Critical** |
| **Total** | **~3.5 min** | |

### Known Bugs Found During Analysis
1. **`confirm_btn` ignores cached storyboard** — preview flow is cosmetic; clicking "Confirm & Generate" re-generates from scratch instead of using the previewed storyboard
2. **`_cached_storyboard` is shared global state** — race condition in multi-user deployment
3. **Narration exceeds 8 seconds** — prompt says "1-2 sentences in 8s" but Neural2 voices at ~150 WPM produce 8-12s audio, causing video looping
4. **Scene ordering mismatch risk** — `tts.py` returns paths sorted by scene_number, `video_gen.py` returns in submission order; could mismatch if scene numbers are non-contiguous
5. **Output directory overwrites** — every run writes to `output/final_video.mp4`, destroying previous results

---

## Priority 1: Assembly Performance (2 min → 5 seconds)

**Impact: Eliminates the biggest controllable bottleneck. Total pipeline time drops from ~3.5 min to ~1.5 min.**

### Replace MoviePy with direct FFmpeg subprocess calls

MoviePy decodes every frame into Python numpy arrays, composites in Python, then re-encodes. For 1529 frames at 1080p, this is catastrophically slow. FFmpeg can do the same job with zero-decode stream-copy.

**New assembly pipeline:**

```
Step 1: Per scene (parallel) — mux video + audio
        FFmpeg stream-copies H.264 video, transcodes only MP3→AAC audio
        Time: ~0.1s per scene

Step 2: Concatenate all muxed scenes
        FFmpeg concat demuxer with stream-copy — zero frame decoding
        Time: ~2-3s regardless of duration

Step 3: Title overlay
        FFmpeg drawtext filter — single re-encode pass
        Time: ~5-8s with libx264 fast preset, ~2s with h264_videotoolbox (macOS)
```

**Key details:**
- `ffmpeg -stream_loop -1 -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -t {audio_duration} scene_muxed.mp4`
- Concat demuxer requires all inputs share codec/resolution/fps — guaranteed since all come from same Veo API call
- Drop the `-0.5` crossfade padding (forces full re-encode); use hard cuts or FFmpeg `xfade` filter later
- Use `h264_videotoolbox` on macOS for GPU-accelerated title overlay encoding (4-8x faster than libx264)

**Also remove the 720p→1080p upscale.** Veo 2 outputs 720p natively. The current `resized((1920, 1080))` upscales every frame through Python with no quality benefit. Output at native 720p or upscale in FFmpeg's SIMD-optimized `scale` filter.

**Files to modify:** `video_pipeline/assembler.py` (full rewrite), `pyproject.toml` (moviepy becomes optional)

---

## Priority 2: Narration Timing Fix (Prompt Engineering)

**Impact: Fixes audio/video duration drift. Scenes become consistent length.**

### Problem
The storyboard prompt says "1-2 sentences that can be comfortably spoken aloud in 8 seconds" but Neural2 voices speak at ~150 WPM. Two sentences regularly produce 25-35 words = 10-14 seconds. Logs confirm 8-12s audio durations.

### Fix (2 lines)
Replace rule 4 in `_build_system_prompt`:
```
4. The "narration" for each scene MUST be 20 words or fewer (approximately
   8 seconds of speech). That is a hard limit. Prefer one punchy sentence.
```

### Complementary fix: SSML with speaking rate control
Switch TTS from plain text to SSML with `<prosody rate="0.90">` to gain 10% timing control:
```python
synthesis_input = texttospeech.SynthesisInput(
    ssml=f'<speak><prosody rate="0.90">{escaped_text}</prosody></speak>'
)
```
Expose as a slider in the UI (range 0.7-1.3, default 0.9).

**Files to modify:** `video_pipeline/storyboard.py`, `video_pipeline/tts.py`, `app.py`

---

## Priority 3: Style Presets

**Impact: Transforms from a one-look tool to a versatile video creator.**

### Add style selection
Define presets that control the Veo prompt suffix and visual direction:

| Preset | Veo Prompt Suffix | Visual Direction |
|--------|------------------|-----------------|
| Cinematic | "educational video style, cinematic" | Film-quality, shallow DOF, warm grade |
| Documentary | "documentary style, natural lighting, 4K" | Handheld, desaturated, realistic |
| Whiteboard | "whiteboard animation, clean white background" | Black ink drawings, diagrams |
| Animated | "2D cartoon animation, flat design, bright colors" | Vivid, playful, flat design |
| Sci-Fi | "futuristic sci-fi, neon holographic, dark cinematic" | Neon, holograms, dark environment |

Add `style: StylePreset` parameter through `generate_storyboard` → `_build_system_prompt`. Add `gr.Dropdown` in UI.

**Files to modify:** `video_pipeline/models.py`, `video_pipeline/storyboard.py`, `app.py`

---

## Priority 4: Imagen 3 + Ken Burns Fallback

**Impact: Eliminates hard failures when Veo quota is exhausted. Reduces cost from ~$32 to ~$0.50 per video.**

The original `plan.md` describes this but it was never implemented. When Veo 2 fails (timeout, quota, error), fall back to:
1. Generate a still image with Imagen 3 (`imagen-3.0-generate-002`, $0.04/image)
2. Apply Ken Burns pan/zoom effect to create an 8-second video clip
3. Continue pipeline normally

```python
# In generate_scene_video's except block:
except (TimeoutError, RuntimeError) as e:
    logger.warning("Veo failed for %s, falling back to Imagen 3 + Ken Burns", scene_id)
    return generate_scene_image_fallback(scene, output_dir)
```

Ken Burns implementation:
```python
def _ken_burns(image_path, duration=8.0, zoom_factor=1.08):
    # Slowly zoom into image over duration
    # Crop from center, scaling from 100% to 108% over 8 seconds
    # Output as VideoClip at 24fps
```

**Files to create:** `video_pipeline/image_gen.py`
**Files to modify:** `video_pipeline/video_gen.py`, `video_pipeline/assembler.py`

---

## Priority 5: Few-Shot Prompting for Better Veo Prompts

**Impact: Significantly improves Veo visual output quality with minimal code change.**

Add a concrete example scene in the user prompt so Gemini learns the expected level of visual specificity:

```python
FEW_SHOT_EXAMPLE = """
Example of a high-quality scene:
{
  "scene_number": 1,
  "veo_prompt": "Extreme close-up of a gleaming red apple resting motionless on a polished
   oak table inside a sunlit university laboratory. Camera slowly pushes in. Warm golden
   afternoon light through tall windows. Shallow depth of field, 35mm cinematic,
   educational video style.",
  "narration": "An object at rest stays at rest until an outside force acts.",
  "visual_description": "Still apple on a table — inertia visualised"
}
Use this level of visual specificity for every scene.
"""
```

**Files to modify:** `video_pipeline/storyboard.py`

---

## Priority 6: Veo Seed for Visual Consistency

**Impact: Scenes share consistent visual style (lighting, color palette) across the video.**

Generate one random seed per pipeline run and pass it to every `GenerateVideosConfig`:

```python
config=types.GenerateVideosConfig(
    aspect_ratio="16:9",
    number_of_videos=1,
    duration_seconds=8,
    output_gcs_uri=output_gcs_uri,
    seed=seed,  # Same seed for all scenes in a batch
),
```

**Files to modify:** `video_pipeline/video_gen.py`, `video_pipeline/__init__.py`

---

## Priority 7: UI/UX Overhaul

### 7A. Fix the Storyboard Preview Bug
`confirm_btn.click` calls `generate_video` which re-generates the storyboard, ignoring the preview. Fix: accept an optional pre-built storyboard dict in `run_pipeline` and skip phase 1 if provided.

### 7B. Editable Storyboard Table
Replace `gr.Code(language="json")` with `gr.Dataframe` — users can edit scene prompts, narrations, and reorder scenes before committing to the expensive Veo generation ($10-32 per run).

### 7C. Unique Output Directories
```python
run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
output_path = run_pipeline(topic, output_dir=f"output/{run_id}", ...)
```
Prevents file overwrites and enables history.

### 7D. Video History Gallery
JSON index file (`output/history.json`) tracking `{run_id, topic, title, timestamp, path}`. New `gr.Tab("History")` with gallery of previous generations.

### 7E. Custom CSS Polish
```python
CUSTOM_CSS = """
.gradio-container { max-width: 1200px; margin: 0 auto; }
#header-md h1 { background: linear-gradient(135deg, #667eea, #764ba2);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
#generate-btn { background: linear-gradient(135deg, #667eea, #764ba2) !important; }
"""
```

### 7F. Dark/Light Mode Toggle
```python
toggle_btn.click(fn=None, js="() => { document.body.classList.toggle('dark'); }")
```

### 7G. Partial Failure Warnings
```python
if result.failed_scene_numbers:
    gr.Warning(f"Scenes {result.failed_scene_numbers} failed and were skipped.")
```

### 7H. Multi-Language Support
Add language selector → passes language to storyboard prompt (narration in target language, veo_prompt stays English) + maps to appropriate TTS voice.

### 7I. Keyboard Shortcuts
Shift+Enter → Preview Storyboard, Ctrl+G → Generate Video, Escape → Focus topic input.

**Files to modify:** `app.py`, `main.py`, `video_pipeline/__init__.py`

---

## Priority 8: Video Quality Enhancements

### 8A. Dedicated Title Card + Outro
Replace the overlaid title (competes with scene 1 visually) with a standalone dark-background title card prepended to the clip list. Add "Thanks for watching!" outro card.

### 8B. Subtitle/Caption Burn-In
Burn narration text as subtitles in each scene — accessibility improvement. The text is already available in the scene dict at assembly time.

```python
subtitle = TextClip(text=scene["narration"], font_size=32, color="white",
    stroke_color="black", stroke_width=1, method="caption",
    size=(width - 160, None)).with_position(("center", height - 100))
```

### 8C. Proper Crossfade Transitions
If keeping MoviePy: use `vfx.CrossFadeIn` / `vfx.CrossFadeOut` for actual alpha-blended transitions.
If using FFmpeg: use `xfade` filter for GPU-accelerated crossfades.

### 8D. Scene Number Lower-Thirds
Overlay "Scene 1 — [visual description]" text in the bottom-left for the first 2.5 seconds of each scene.

### 8E. Background Music
Layer low-volume (8%) ambient music under narration. Add `ambient_music_path` to config. Mix with `CompositeAudioClip` or FFmpeg `amix` filter.

### 8F. Color Grading
Apply a consistent warm color grade per-clip to unify Veo's variable output:
```python
video = video.with_effects([vfx.MultiplyColor(factor=(1.05, 0.98, 0.90))])
```

**Files to modify:** `video_pipeline/assembler.py`, `video_pipeline/config.py`

---

## Priority 9: Architecture & Deployment

### 9A. FastAPI SSE Endpoint (Future React Migration Path)
Mount FastAPI alongside Gradio. Expose `/api/generate` as a Server-Sent Events stream. This enables building a richer React/Next.js frontend later without abandoning Gradio now.

```python
app = FastAPI()
app.mount("/ui", gr.mount_gradio_app(app, demo, path="/ui"))

@app.get("/api/generate")
async def generate_stream(topic: str, num_scenes: int = 8):
    return StreamingResponse(run_pipeline_streaming(...), media_type="text/event-stream")
```

### 9B. Generator-Based Streaming Pipeline
Convert `run_pipeline` to a generator that `yield`s structured events (storyboard_ready, scene_complete, done). Gradio natively supports generators for incremental UI updates.

### 9C. Per-Scene Regeneration
Keep intermediate files alive (`cleanup_intermediates=False`). Track scene state in `gr.State`. Add "Regenerate" button per scene. Pre-render 10 hidden scene containers (Gradio's max) and show/hide dynamically.

### 9D. VTT Chapter File
Write a WebVTT chapter file alongside the final video. Each chapter = one scene with the narration as the label. Expose as `gr.File` download.

### 9E. Cloud Run Deployment
```yaml
# cloud-run-service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
spec:
  template:
    spec:
      containers:
        - image: gcr.io/PROJECT/professorpixel
          ports: [{containerPort: 7860}]
          resources:
            limits: {memory: 4Gi, cpu: "2"}
```

### 9F. Monitoring & Observability
- Structured JSON logging (conditional on `LOG_FORMAT=json` env var)
- Per-pipeline metrics: total time, cost estimate, scenes succeeded/failed
- GCS storage usage tracking

---

## Priority 10: Cost Optimization

| Optimization | Current Cost | After | Savings |
|-------------|-------------|-------|---------|
| Imagen 3 fallback when Veo fails | $32/video (wasted) | $0.50/video | 98% on failures |
| Storyboard caching (already done) | $0.002/call | $0 on repeat | 100% on repeats |
| Veo Fast mode (when available) | $32/video | $10/video | 69% |
| Fewer scenes (configurable, done) | 8 scenes default | 3-10 user choice | Up to 62% |
| GCS cleanup (already done) | Storage accumulates | Auto-deleted | Storage costs |

---

## Implementation Phases

### Phase A: Quick Wins (1-2 hours)
- [ ] Fix narration word budget (20 words max) — `storyboard.py` (2 lines)
- [ ] Fix confirm button storyboard bypass bug — `app.py` (10 lines)
- [ ] Fix shared `_cached_storyboard` → `gr.State` — `app.py` (15 lines)
- [ ] Unique output directories per run — `app.py` (5 lines)
- [ ] Reduce Veo poll interval 10s → 5s — `video_gen.py` (1 line)
- [ ] Few-shot example in storyboard prompt — `storyboard.py` (10 lines)
- [ ] Dark mode toggle — `app.py` (5 lines JS)

### Phase B: Assembly Rewrite (half day)
- [ ] Replace MoviePy assembler with FFmpeg subprocess calls
- [ ] Per-scene mux (stream-copy video + transcode audio)
- [ ] Concat demuxer (zero-decode concatenation)
- [ ] FFmpeg drawtext title overlay
- [ ] macOS VideoToolbox acceleration
- [ ] Remove 720p→1080p upscale (output native resolution)

### Phase C: AI Quality (half day)
- [ ] Style presets (cinematic/documentary/whiteboard/animated/sci-fi)
- [ ] SSML + speaking rate control in TTS
- [ ] Veo seed for visual consistency
- [ ] Imagen 3 + Ken Burns fallback
- [ ] Storyboard model config (Flash/Pro toggle)

### Phase D: Video Polish (half day)
- [ ] Dedicated title card + outro card
- [ ] Subtitle/caption burn-in
- [ ] Scene number lower-thirds
- [ ] Proper crossfade transitions (FFmpeg xfade)
- [ ] Optional background music

### Phase E: UX & Architecture (1-2 days)
- [ ] Editable storyboard table (`gr.Dataframe`)
- [ ] Multi-language support
- [ ] Video history gallery
- [ ] Custom CSS polish
- [ ] Partial failure `gr.Warning`
- [ ] FastAPI SSE endpoint
- [ ] Generator-based streaming pipeline
- [ ] Per-scene regeneration UI
- [ ] Quality/format download presets

---

## Expected Results After All Phases

| Metric | Before | After |
|--------|--------|-------|
| Total generation time | ~3.5 min | ~1.5 min |
| Assembly time | ~2 min | ~5-10 sec |
| Cost per video | $10-32 | $0.50-10 (with fallback/fast mode) |
| Failure rate | 100% pipeline failure on any scene error | Partial success + Imagen fallback |
| Narration accuracy | 8-12s drift per scene | Consistent ~8s |
| Style options | 1 (cinematic only) | 5 presets |
| Languages | English only | 5+ languages |
| UI controls | Topic + Generate | Topic, scenes, voice, style, language, speed, preview, history |
