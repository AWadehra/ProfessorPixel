"""Google Sheets export with async support."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from googleapiclient.discovery import build
from google.auth import default

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

_sheets_service = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_sheets_service():
    global _sheets_service
    if _sheets_service is None:
        creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        _sheets_service = build("sheets", "v4", credentials=creds)
    return _sheets_service


def _create_sheet_sync(analysis_data: dict) -> str:
    """Create a Google Sheet with the risk matrix. Returns the sheet URL."""
    service = _get_sheets_service()

    # Parse data
    clauses = analysis_data.get("clauses", {})
    buyer = analysis_data.get("buyer_analysis", {})
    seller = analysis_data.get("seller_analysis", {})
    report = analysis_data.get("final_report", {})

    clause_list = clauses.get("clauses", []) if isinstance(clauses, dict) else []
    buyer_risks = {r["clause_number"]: r for r in (buyer.get("clause_risks", []) if isinstance(buyer, dict) else [])}
    seller_risks = {r["clause_number"]: r for r in (seller.get("clause_risks", []) if isinstance(seller, dict) else [])}
    risk_items = report.get("risk_items", []) if isinstance(report, dict) else []
    risk_map = {r["clause_number"]: r for r in risk_items}

    contract_type = clauses.get("contract_type", "Unknown") if isinstance(clauses, dict) else "Unknown"
    fairness_score = report.get("overall_fairness_score", "N/A") if isinstance(report, dict) else "N/A"
    recommendation = report.get("recommendation", "N/A") if isinstance(report, dict) else "N/A"

    # Create spreadsheet
    spreadsheet = service.spreadsheets().create(
        body={
            "properties": {"title": f"Contract Analysis — {contract_type}"},
            "sheets": [
                {"properties": {"title": "Risk Matrix", "index": 0}},
                {"properties": {"title": "Summary", "index": 1}},
            ],
        }
    ).execute()

    spreadsheet_id = spreadsheet["spreadsheetId"]

    # Build Risk Matrix data
    matrix_rows = [
        ["Clause #", "Title", "Category", "Buyer Risk", "Buyer Concern", "Seller Risk", "Seller Concern", "Mediator Recommendation", "Priority"],
    ]

    for clause in clause_list:
        num = clause.get("number", 0)
        br = buyer_risks.get(num, {})
        sr = seller_risks.get(num, {})
        ri = risk_map.get(num, {})

        matrix_rows.append([
            num,
            clause.get("title", ""),
            clause.get("category", ""),
            br.get("risk_level", "none").upper(),
            br.get("concern", "No concerns"),
            sr.get("risk_level", "none").upper(),
            sr.get("concern", "No concerns"),
            ri.get("mediator_recommendation", "N/A"),
            ri.get("priority", "N/A"),
        ])

    # Build Summary data
    summary_rows = [
        ["Contract Analysis Summary"],
        [],
        ["Contract Type", contract_type],
        ["Fairness Score", f"{fairness_score} / 10"],
        ["Recommendation", recommendation],
        [],
        ["Executive Summary"],
        [report.get("executive_summary", "N/A") if isinstance(report, dict) else "N/A"],
        [],
        ["Missing Protections — Buyer"],
    ]

    for mp in (report.get("missing_protections_buyer", []) if isinstance(report, dict) else []):
        summary_rows.append([f"• {mp}"])

    summary_rows.append([])
    summary_rows.append(["Missing Protections — Seller"])

    for mp in (report.get("missing_protections_seller", []) if isinstance(report, dict) else []):
        summary_rows.append([f"• {mp}"])

    # Write data — delete sheet on failure to avoid orphans
    try:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": [
                    {"range": "Risk Matrix!A1", "values": matrix_rows},
                    {"range": "Summary!A1", "values": summary_rows},
                ],
            },
        ).execute()
    except Exception:
        try:
            from googleapiclient.discovery import build as _build
            drive = _build("drive", "v3", credentials=default(scopes=["https://www.googleapis.com/auth/drive"])[0])
            drive.files().delete(fileId=spreadsheet_id).execute()
        except Exception:
            pass
        raise

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


async def export_to_sheets(analysis_data: dict) -> str:
    """Async wrapper: create Google Sheet with analysis results. Returns URL."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _create_sheet_sync, analysis_data)
