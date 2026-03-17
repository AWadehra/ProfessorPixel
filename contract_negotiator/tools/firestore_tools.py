"""Firestore persistence for analysis history."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from google.cloud import firestore

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
COLLECTION = "contract_analyses"

_fs_client: firestore.Client | None = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_client() -> firestore.Client:
    global _fs_client
    if _fs_client is None:
        _fs_client = firestore.Client(project=PROJECT_ID)
    return _fs_client


def _save_sync(session_id: str, data: dict) -> str:
    """Save analysis results to Firestore."""
    client = _get_client()
    doc_ref = client.collection(COLLECTION).document(session_id)

    report = data.get("final_report", {})
    clauses = data.get("clauses", {})

    doc = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
        "contract_type": clauses.get("contract_type", "unknown") if isinstance(clauses, dict) else "unknown",
        "parties": clauses.get("parties", []) if isinstance(clauses, dict) else [],
        "fairness_score": report.get("overall_fairness_score") if isinstance(report, dict) else None,
        "recommendation": report.get("recommendation", "") if isinstance(report, dict) else "",
        "executive_summary": report.get("executive_summary", "") if isinstance(report, dict) else "",
        "clause_count": len(clauses.get("clauses", [])) if isinstance(clauses, dict) else 0,
        "risk_item_count": len(report.get("risk_items", [])) if isinstance(report, dict) else 0,
    }

    doc_ref.set(doc)
    return session_id


def _list_sync(limit: int = 20) -> list[dict]:
    """List recent analyses."""
    client = _get_client()
    docs = (
        client.collection(COLLECTION)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    results = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        # Convert Firestore timestamp
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        results.append(d)

    return results


async def save_analysis(session_id: str, data: dict) -> str:
    """Async save analysis to Firestore."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _save_sync, session_id, data)


async def list_analyses(limit: int = 20) -> list[dict]:
    """Async list recent analyses."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _list_sync, limit)
