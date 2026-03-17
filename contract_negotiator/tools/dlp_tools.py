"""Cloud DLP PII detection with async support and client pooling."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import google.cloud.dlp_v2 as dlp

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

_dlp_client: dlp.DlpServiceClient | None = None
_executor = ThreadPoolExecutor(max_workers=2)

# Info types to detect in contracts
_INFO_TYPES = [
    "PERSON_NAME",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "STREET_ADDRESS",
    "DATE_OF_BIRTH",
    "CREDIT_CARD_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "US_EMPLOYER_IDENTIFICATION_NUMBER",
    "IBAN_CODE",
]


def _get_dlp_client() -> dlp.DlpServiceClient:
    global _dlp_client
    if _dlp_client is None:
        _dlp_client = dlp.DlpServiceClient()
    return _dlp_client


def _scan_sync(text: str) -> list[dict]:
    """Synchronous DLP scan — runs in thread pool."""
    client = _get_dlp_client()

    # Truncate to DLP limit (500KB). Use 125K chars to stay safe for multi-byte text.
    if len(text.encode("utf-8")) > 500_000:
        text = text[:125_000]

    item = dlp.ContentItem(value=text)
    inspect_config = dlp.InspectConfig(
        info_types=[dlp.InfoType(name=t) for t in _INFO_TYPES],
        min_likelihood=dlp.Likelihood.POSSIBLE,
        limits=dlp.InspectConfig.FindingLimits(max_findings_per_request=50),
        include_quote=True,
    )

    response = client.inspect_content(
        request={
            "parent": f"projects/{PROJECT_ID}/locations/global",
            "item": item,
            "inspect_config": inspect_config,
        }
    )

    findings = []
    for finding in response.result.findings:
        findings.append({
            "type": finding.info_type.name,
            "quote": finding.quote[:100] if finding.quote else "",
            "likelihood": dlp.Likelihood(finding.likelihood).name,
        })

    return findings


async def scan_for_pii(text: str) -> dict:
    """Scan contract text for PII using Cloud DLP.

    Returns:
        dict with:
          - pii_found: bool
          - count: int
          - findings: list of {type, quote, likelihood}
          - summary: str (human-readable)
    """
    loop = asyncio.get_running_loop()
    findings = await loop.run_in_executor(_executor, _scan_sync, text)

    # Group by type
    by_type: dict[str, int] = {}
    for f in findings:
        label = f["type"].replace("_", " ").title()
        by_type[label] = by_type.get(label, 0) + 1

    summary_parts = [f"{count} {label}" for label, count in sorted(by_type.items())]
    summary = ", ".join(summary_parts) if summary_parts else "No PII detected"

    return {
        "pii_found": len(findings) > 0,
        "count": len(findings),
        "findings": findings,
        "summary": summary,
    }
