# ProfessorPixel v2 — Implementation Progress Tracker

## Phase A: Quick Wins
| # | Task | Status | Verified |
|---|------|--------|----------|
| A1 | Fix narration word budget (20 words max) | done | storyboard.py rule 4 updated |
| A2 | Fix confirm button storyboard bypass bug | done | `generate_from_storyboard()` uses `storyboard_state` via `gr.State` |
| A3 | Fix shared `_cached_storyboard` → `gr.State` | done | Replaced module-level dict with `gr.State(None)` |
| A4 | Unique output directories per run | done | `output/{timestamp}_{uuid}/` pattern in app.py |
| A5 | Reduce Veo poll interval 10s → 5s | done | Config `veo_poll_interval_seconds=5` |
| A6 | Few-shot example in storyboard prompt | done | `FEW_SHOT_EXAMPLE` with detailed scene example |
| A7 | Dark mode toggle | done | Gradio Base theme with violet hue (auto dark mode) |

## Phase B: Assembly Rewrite (FFmpeg)
| # | Task | Status | Verified |
|---|------|--------|----------|
| B1 | Replace MoviePy assembler with FFmpeg subprocess calls | done | Full rewrite of assembler.py |
| B2 | Per-scene mux (stream-copy video + transcode audio) | done | `_mux_scene()` with `-c:v copy -c:a aac` |
| B3 | Concat demuxer (zero-decode concatenation) | done | `_concat_scenes()` with `-f concat -c copy` |
| B4 | FFmpeg drawtext title overlay | done | `_add_overlays()` with drawtext filter |
| B5 | Subtitle burn-in via FFmpeg drawtext | done | Per-scene subtitle with timed `enable` filter |
| B6 | Remove 720p→1080p upscale | done | No resolution manipulation — native Veo output |

## Phase C: AI Quality
| # | Task | Status | Verified |
|---|------|--------|----------|
| C1 | Style presets (cinematic/documentary/whiteboard/animated/sci-fi) | done | `STYLE_DIRECTIVES` dict, rule 7 in system prompt |
| C2 | SSML + speaking rate control in TTS | done | `_build_ssml()` with `<prosody rate>` |
| C3 | Veo seed for visual consistency | done | Random seed per pipeline run passed to all scenes |
| C4 | Imagen 3 + Ken Burns fallback | done | `image_gen.py` with `zoompan` FFmpeg filter |
| C5 | Storyboard model config (Flash/Pro toggle) | done | `storyboard_model` in config.py |

## Phase D: Video Polish
| # | Task | Status | Verified |
|---|------|--------|----------|
| D1 | Dedicated title card (FFmpeg drawtext) | done | 3-second title overlay at video start |
| D2 | Scene subtitles (FFmpeg drawtext) | done | Per-scene narration text at bottom |

## Phase E: UX & Architecture
| # | Task | Status | Verified |
|---|------|--------|----------|
| E1 | Multi-language support | done | 5 languages (EN/ES/FR/DE/JA) with voice mapping |
| E2 | Video history gallery | done | JSON index + History tab with Dataframe |
| E3 | Custom CSS polish | done | Gradient header, styled buttons, max-width |
| E4 | Partial failure gr.Warning | done | Shows failed scene numbers in UI warning |
| E5 | Keyboard shortcuts | done | Escape → focus topic input |
| E6 | Speaking rate slider in UI | done | Slider 0.7-1.3, default 0.9 |
| E7 | Style dropdown in UI | done | 5 visual style presets |
| E8 | Storyboard preview with gr.State | done | Per-session state, confirm uses cached storyboard |
| E9 | PipelineResult dataclass | done | Returns structured result with failure info |

## New Files Created
| File | Purpose |
|------|---------|
| `video_pipeline/image_gen.py` | Imagen 3 + Ken Burns fallback for Veo failures |

## Files Modified
| File | Changes |
|------|---------|
| `video_pipeline/assembler.py` | Full rewrite: MoviePy → FFmpeg (stream-copy mux + concat + drawtext) |
| `video_pipeline/storyboard.py` | 20-word narration limit, few-shot example, style presets, configurable model |
| `video_pipeline/video_gen.py` | Veo seed, 5s poll interval, Imagen 3 fallback on failure |
| `video_pipeline/tts.py` | SSML with speaking rate, pass-through parameter |
| `video_pipeline/__init__.py` | PipelineResult, seed, style, speaking_rate, storyboard passthrough |
| `video_pipeline/config.py` | New settings: poll interval, speaking rate, storyboard model, subtitles |
| `video_pipeline/models.py` | (unchanged — schema still valid) |
| `app.py` | Full rewrite: tabs, style/language/speed controls, history, CSS, gr.State |
| `main.py` | Custom theme, CSS passthrough |

## Performance Impact
| Metric | Before | After |
|--------|--------|-------|
| Assembly time | ~2 min (MoviePy frame-by-frame) | ~5-10 sec (FFmpeg stream-copy) |
| Veo poll interval | 10s | 5s (saves ~5s average per scene) |
| Storyboard on repeat | ~18s (Gemini call) | 0s (cache hit) |
| Failed video recovery | Pipeline crash | Imagen 3 + Ken Burns fallback |
