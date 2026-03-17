"""Custom FastAPI server for Contract Negotiator with Document AI, TTS, and streaming."""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any other imports that read env vars
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from google.genai import types

from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode

from contract_negotiator.agent import root_agent
from contract_negotiator.tools.document_tools import process_contract_file
from contract_negotiator.tools.tts_tools import agent_speak, VALID_AGENT_NAMES
from contract_negotiator.tools.dlp_tools import scan_for_pii
from contract_negotiator.tools.sheets_tools import export_to_sheets
from contract_negotiator.tools.translate_tools import detect_language, translate_text
from contract_negotiator.tools.firestore_tools import save_analysis, list_analyses

# ── Logging (routes to Cloud Logging in production) ──
try:
    import google.cloud.logging as cloud_logging
    cloud_client = cloud_logging.Client()
    cloud_client.setup_logging()
    logging.info("Cloud Logging integration active")
except Exception:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
logger = logging.getLogger("contract_negotiator.server")

# ── Environment ──
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "TRUE"))

MAX_CONTRACT_CHARS = int(os.environ.get("MAX_CONTRACT_CHARS", 50_000))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))

# ── Session store with TTL tracking ──
session_service = InMemorySessionService()
_session_timestamps: dict[str, float] = {}
SESSION_TTL_SECONDS = 3600  # 1 hour


async def _cleanup_stale_sessions():
    """Periodically evict sessions older than SESSION_TTL_SECONDS."""
    while True:
        await asyncio.sleep(300)
        now = time.monotonic()
        expired = [sid for sid, ts in _session_timestamps.items()
                   if now - ts > SESSION_TTL_SECONDS]
        for sid in expired:
            try:
                await session_service.delete_session(
                    app_name="contract_negotiator",
                    user_id="web_user",
                    session_id=sid,
                )
            except Exception:
                pass
            _session_timestamps.pop(sid, None)
        if expired:
            logger.info("Evicted %d stale sessions", len(expired))


@asynccontextmanager
async def lifespan(app_instance):
    cleanup_task = asyncio.create_task(_cleanup_stale_sessions())
    yield
    cleanup_task.cancel()


app = FastAPI(title="Contract Negotiator", lifespan=lifespan)

# ── CORS ──
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

# ── Rate limiting ──
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── ADK setup ──
adk_app = App(name="contract_negotiator", root_agent=root_agent)
runner = Runner(app=adk_app, session_service=session_service, auto_create_session=True)


# ── Request models with validation ──
class AnalyzeRequest(BaseModel):
    contract_text: str
    session_id: str | None = None

    @field_validator("contract_text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 50:
            raise ValueError("Contract text is too short (minimum 50 characters)")
        if len(stripped) > MAX_CONTRACT_CHARS:
            raise ValueError(f"Contract text exceeds maximum length of {MAX_CONTRACT_CHARS} characters")
        return stripped

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[0-9a-f\-]{36}", v):
            raise ValueError("Invalid session_id format")
        return v


class TTSRequest(BaseModel):
    text: str
    agent_name: str

    @field_validator("text")
    @classmethod
    def validate_tts_text(cls, v: str) -> str:
        if len(v) > 5000:
            return v[:5000]
        return v

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        if v not in VALID_AGENT_NAMES:
            raise ValueError(f"Unknown agent name '{v}'")
        return v


# ── Global exception handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── File upload validation ──
ALLOWED_MIME_MAP = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


@app.post("/api/upload")
@limiter.limit("10/minute;50/hour")
async def upload_contract(request: Request, file: UploadFile = File(...)):
    """Upload a contract image/PDF, OCR it with Document AI, return extracted text."""
    # Validate file type
    raw_name = file.filename or ""
    suffix = Path(raw_name).suffix.lower()
    if suffix not in ALLOWED_MIME_MAP:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_MIME_MAP)}",
        )

    # Sanitize filename
    safe_name = re.sub(r"[^\w.\-]", "_", Path(raw_name).name)[:128]

    # Enforce size limit
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    logger.info("upload filename=%s size=%d", safe_name, len(content))

    try:
        text = await process_contract_file(content, safe_name)
    except Exception:
        logger.exception("Document AI processing failed for %s", safe_name)
        raise HTTPException(status_code=500, detail="Document processing failed")

    return {"text": text, "filename": safe_name}


@app.post("/api/detect-language")
@limiter.limit("20/minute")
async def detect_lang(request: Request, req: AnalyzeRequest):
    """Detect language of contract text and translate to English if needed."""
    try:
        detection = await detect_language(req.contract_text)
        lang = detection["language"]
        confidence = detection.get("confidence", 0)

        result = {
            "language": lang,
            "confidence": confidence,
            "is_english": lang == "en",
        }

        if lang != "en" and confidence > 0.5:
            translated = await translate_text(req.contract_text, target="en", source=lang)
            result["translated_text"] = translated
            result["original_language_name"] = _LANG_NAMES.get(lang, lang)

        return result
    except Exception:
        logger.exception("Language detection failed")
        raise HTTPException(status_code=500, detail="Language detection failed")


# Common language names for display
_LANG_NAMES = {
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "ru": "Russian", "hi": "Hindi",
    "pl": "Polish", "tr": "Turkish", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "cs": "Czech", "ro": "Romanian",
}


@app.post("/api/scan-pii")
@limiter.limit("10/minute")
async def scan_pii(request: Request, req: AnalyzeRequest):
    """Scan contract text for PII using Cloud DLP."""
    try:
        result = await scan_for_pii(req.contract_text)
        return result
    except Exception:
        logger.exception("DLP scan failed")
        raise HTTPException(status_code=500, detail="PII scan failed")


@app.post("/api/analyze")
@limiter.limit("5/minute;20/hour")
async def analyze_contract(request: Request, req: AnalyzeRequest):
    """Start agent pipeline and stream events via SSE."""
    session_id = req.session_id or str(uuid.uuid4())
    user_id = "web_user"

    await session_service.create_session(
        app_name="contract_negotiator",
        user_id=user_id,
        session_id=session_id,
        state={"debate_round": 1},
    )
    _session_timestamps[session_id] = time.monotonic()

    user_message = types.Content(
        parts=[types.Part(text=req.contract_text)],
        role="user",
    )
    run_config = RunConfig(streaming_mode=StreamingMode.SSE)

    async def event_generator():
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_message,
                run_config=run_config,
            ):
                event_data = {
                    "author": event.author,
                    "content": None,
                    "state_delta": {},
                    "is_final": event.is_final_response() if hasattr(event, "is_final_response") else False,
                    "partial": getattr(event, "partial", False),
                }

                if event.content and event.content.parts:
                    text_parts = [
                        part.text
                        for part in event.content.parts
                        if hasattr(part, "text") and part.text
                    ]
                    if text_parts:
                        event_data["content"] = "\n".join(text_parts)

                # Only serialize state_delta when non-empty
                if event.actions and event.actions.state_delta:
                    event_data["state_delta"] = {
                        k: str(v)[:2000] for k, v in event.actions.state_delta.items()
                    }

                yield f"data: {json.dumps(event_data)}\n\n"

            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

        except asyncio.CancelledError:
            logger.info("Client disconnected, cancelling pipeline for session=%s", session_id)
            return
        except Exception:
            logger.exception("Streaming pipeline failed for session=%s", session_id)
            yield f"data: {json.dumps({'error': 'Analysis pipeline encountered an error. Please try again.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/tts")
@limiter.limit("30/minute")
async def text_to_speech(request: Request, req: TTSRequest):
    """Convert agent text to speech with agent-specific voice."""
    try:
        audio_bytes = await agent_speak(req.text, req.agent_name)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio": audio_b64}
    except Exception:
        logger.exception("TTS synthesis failed for agent=%s", req.agent_name)
        raise HTTPException(status_code=500, detail="Speech synthesis failed")


# ── Heatmap endpoint — returns structured clause + risk data ──
_HEATMAP_STATE_KEYS = frozenset(["clauses", "buyer_analysis", "seller_analysis", "final_report", "redlined_contract"])


@app.get("/api/session/{session_id}/heatmap")
async def get_heatmap_data(session_id: str):
    """Return structured clause and risk data for the heatmap view."""
    if not re.fullmatch(r"[0-9a-f\-]{36}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await session_service.get_session(
        app_name="contract_negotiator",
        user_id="web_user",
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Extract structured data from session state
    heatmap = {}
    for key in _HEATMAP_STATE_KEYS:
        val = session.state.get(key)
        if val is not None:
            # output_schema means values are already dicts/Pydantic-serialized
            if isinstance(val, str):
                try:
                    heatmap[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    heatmap[key] = val
            else:
                heatmap[key] = val
    return heatmap


@app.post("/api/session/{session_id}/save")
async def save_session(session_id: str):
    """Save analysis results to Firestore for history."""
    if not re.fullmatch(r"[0-9a-f\-]{36}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await session_service.get_session(
        app_name="contract_negotiator",
        user_id="web_user",
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    analysis_data = {}
    for key in _HEATMAP_STATE_KEYS:
        val = session.state.get(key)
        if val is not None:
            if isinstance(val, str):
                try:
                    analysis_data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    analysis_data[key] = val
            else:
                analysis_data[key] = val

    try:
        doc_id = await save_analysis(session_id, analysis_data)
        return {"saved": True, "id": doc_id}
    except Exception:
        logger.exception("Firestore save failed")
        raise HTTPException(status_code=500, detail="Failed to save analysis")


@app.get("/api/history")
async def get_history():
    """List recent contract analyses from Firestore."""
    try:
        analyses = await list_analyses(limit=20)
        return {"analyses": analyses}
    except Exception:
        logger.exception("Firestore list failed")
        raise HTTPException(status_code=500, detail="Failed to load history")


@app.post("/api/session/{session_id}/export-sheets")
@limiter.limit("3/minute")
async def export_sheets(request: Request, session_id: str):
    """Export analysis results to a Google Sheet."""
    if not re.fullmatch(r"[0-9a-f\-]{36}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await session_service.get_session(
        app_name="contract_negotiator",
        user_id="web_user",
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    analysis_data = {}
    for key in _HEATMAP_STATE_KEYS:
        val = session.state.get(key)
        if val is not None:
            if isinstance(val, str):
                try:
                    analysis_data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    analysis_data[key] = val
            else:
                analysis_data[key] = val

    try:
        url = await export_to_sheets(analysis_data)
        return {"url": url}
    except Exception:
        logger.exception("Sheets export failed")
        raise HTTPException(status_code=500, detail="Failed to create Google Sheet")


@app.post("/api/session/{session_id}/store-gcs")
async def store_to_gcs(session_id: str):
    """Store analysis output as JSON in GCS for later review."""
    if not re.fullmatch(r"[0-9a-f\-]{36}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await session_service.get_session(
        app_name="contract_negotiator",
        user_id="web_user",
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    analysis_data = {}
    for key in _HEATMAP_STATE_KEYS:
        val = session.state.get(key)
        if val is not None:
            if isinstance(val, str):
                try:
                    analysis_data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    analysis_data[key] = val
            else:
                analysis_data[key] = val

    try:
        from contract_negotiator.tools.document_tools import _get_storage_client, BUCKET_NAME
        client = _get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"outputs/{session_id}/analysis.json")
        blob.upload_from_string(
            json.dumps(analysis_data, indent=2, default=str),
            content_type="application/json",
        )
        gcs_uri = f"gs://{BUCKET_NAME}/outputs/{session_id}/analysis.json"
        logger.info("Stored analysis to %s", gcs_uri)
        return {"stored": True, "gcs_uri": gcs_uri}
    except Exception:
        logger.exception("GCS storage failed for session=%s", session_id)
        raise HTTPException(status_code=500, detail="Failed to store to GCS")


# Safe subset of state keys the frontend legitimately needs
_ALLOWED_STATE_KEYS = frozenset(["debate_round", "debate_terminated_early"])


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get non-sensitive session metadata."""
    if not re.fullmatch(r"[0-9a-f\-]{36}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await session_service.get_session(
        app_name="contract_negotiator",
        user_id="web_user",
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    safe_state = {k: v for k, v in session.state.items() if k in _ALLOWED_STATE_KEYS}
    return {"state": safe_state}


@app.get("/health")
async def health_check():
    """Liveness probe for load balancers and uptime monitors."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
    }


# Serve static frontend — MUST be last route registered
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
