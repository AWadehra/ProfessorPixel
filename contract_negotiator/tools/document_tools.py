"""Document AI OCR and GCS upload with async support, client pooling, and caching."""

import asyncio
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from google.cloud import documentai_v1 as documentai
from google.cloud import storage

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ["DOCAI_LOCATION"]
PROCESSOR_ID = os.environ["DOCAI_PROCESSOR_ID"]
BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]

# Module-level pooled clients — instantiated once, reused
_storage_client: storage.Client | None = None
_docai_client: documentai.DocumentProcessorServiceClient | None = None
_executor = ThreadPoolExecutor(max_workers=4)

# In-process OCR cache: sha256(content) -> extracted text
_ocr_cache: dict[str, str] = {}
_MAX_OCR_CACHE = 50


def _get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=PROJECT_ID)
    return _storage_client


def _get_docai_client() -> documentai.DocumentProcessorServiceClient:
    global _docai_client
    if _docai_client is None:
        _docai_client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{LOCATION}-documentai.googleapis.com"}
        )
    return _docai_client


def _upload_to_gcs_sync(file_content: bytes, filename: str) -> str:
    """Sync GCS upload with UUID prefix to prevent collisions."""
    client = _get_storage_client()
    bucket = client.bucket(BUCKET_NAME)
    unique_key = f"uploads/{uuid.uuid4().hex}/{filename}"
    blob = bucket.blob(unique_key)
    blob.upload_from_string(file_content)
    return f"gs://{BUCKET_NAME}/{unique_key}"


def _extract_text_sync(image_content: bytes, mime_type: str) -> str:
    """Sync Document AI call."""
    client = _get_docai_client()
    resource_name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
    request = documentai.ProcessRequest(name=resource_name, raw_document=raw_document)
    result = client.process_document(request=request)
    return result.document.text


async def process_contract_file(file_content: bytes, filename: str) -> str:
    """Upload to GCS and OCR concurrently. Returns extracted text.

    OCR results are cached by content hash to skip duplicate Document AI calls.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        mime_type = "application/pdf"
    elif lower.endswith(".jpg") or lower.endswith(".jpeg"):
        mime_type = "image/jpeg"
    elif lower.endswith(".tiff") or lower.endswith(".tif"):
        mime_type = "image/tiff"
    else:
        mime_type = "image/png"

    # Check cache first
    content_hash = hashlib.sha256(file_content).hexdigest()
    if content_hash in _ocr_cache:
        # Fire-and-forget GCS upload for record-keeping
        loop = asyncio.get_running_loop()
        loop.run_in_executor(_executor, _upload_to_gcs_sync, file_content, filename)
        return _ocr_cache[content_hash]

    loop = asyncio.get_running_loop()

    # Run GCS upload and Document AI OCR concurrently
    gcs_task = loop.run_in_executor(_executor, _upload_to_gcs_sync, file_content, filename)
    ocr_task = loop.run_in_executor(_executor, _extract_text_sync, file_content, mime_type)

    text, _ = await asyncio.gather(ocr_task, gcs_task)

    # Cache with eviction
    if len(_ocr_cache) >= _MAX_OCR_CACHE:
        oldest_key = next(iter(_ocr_cache))
        del _ocr_cache[oldest_key]
    _ocr_cache[content_hash] = text

    return text
