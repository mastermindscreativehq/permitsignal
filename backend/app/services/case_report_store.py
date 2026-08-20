"""
PermitSignal Case Report Store
===============================

Purpose
-------
Persist generated case-report PDFs as versioned artifacts in Supabase.
Each generation produces one record (metadata + base64-encoded PDF).
The source lead table is NEVER mutated.

This follows the exact same Supabase storage pattern as
backend.app.services.matrix_engine (Pattern B in the codebase):
- Reuses lead_repository.get_client() / is_configured()
- INSERT (not upsert) with auto-incrementing version
- Fetch/list by application_number

Public API
----------
is_configured() -> bool
generate_and_store(lead, generated_by="api") -> dict
fetch_report(application_number, version) -> Optional[dict]
fetch_reports(application_number, limit=20) -> list[dict]
get_pdf_bytes(report) -> Optional[bytes]
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.services import case_report_generator
from backend.app.services.lead_repository import get_client, is_configured as _repo_is_configured

logger = logging.getLogger(__name__)

_CASE_REPORTS_TABLE = "case_reports"


def is_configured() -> bool:
    """True only when Supabase is configured."""
    return _repo_is_configured()


def _get_client() -> Any:
    """Get a Supabase client. Raises if not configured."""
    if not _repo_is_configured():
        raise RuntimeError(
            "Supabase is not configured. Case report storage requires "
            "SUPABASE_URL and SUPABASE_KEY."
        )
    return get_client()


def _get_next_version(application_number: str) -> int:
    """Determine the next version number for an application. Returns 1 if none exist or table is missing."""
    try:
        client = _get_client()
        response = (
            client.table(_CASE_REPORTS_TABLE)
            .select("version")
            .eq("application_number", application_number)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return 1
        return (rows[0].get("version") or 0) + 1
    except Exception as exc:
        logger.warning(
            "Could not query case_reports table for version (table may not exist): %s", exc
        )
        return 1


def generate_and_store(
    lead: dict,
    generated_by: str = "api",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Generate a case-report PDF for a lead, persist it to Supabase,
    and return the stored record (without the base64 payload to keep
    the response lightweight; use fetch_report() to retrieve it).

    If Supabase is not configured, the PDF is still generated and
    returned as bytes, but storage is skipped and a warning is logged.
    """
    application_number = lead.get("application_number", "UNKNOWN")

    pdf_bytes = case_report_generator.generate_case_report_pdf(lead)

    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    file_size_bytes = len(pdf_bytes)

    # Count pages from the PDF bytes
    page_count = 0
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import LETTER
        # Lightweight page count: count "Page" markers in the raw bytes
        # This is a heuristic; for absolute accuracy we could use PyMuPDF,
        # but reportlab's own output doesn't easily expose page count
        # without re-parsing. The metadata in the PDF footer says "Page X of Y".
        # For storage purposes, we parse it from the generated text.
        page_count = _count_pdf_pages(pdf_bytes)
    except Exception:
        page_count = 0

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    version = _get_next_version(application_number) if is_configured() else 1

    record = {
        "application_number": application_number,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "pdf_base64": pdf_base64,
        "page_count": page_count,
        "file_size_bytes": file_size_bytes,
        "checksum": checksum,
        "metadata": metadata or {},
    }

    if not is_configured():
        logger.warning(
            "Supabase not configured; case report for %s generated but not stored.",
            application_number,
        )
        return record

    try:
        client = _get_client()
        response = client.table(_CASE_REPORTS_TABLE).insert(record).execute()
        stored = response.data[0] if response.data else record
        return stored
    except Exception as exc:
        logger.error(
            "Failed to store case report for %s: %s",
            application_number,
            exc,
        )
        return record


def fetch_report(
    application_number: str,
    version: int,
) -> Optional[dict]:
    """Retrieve a specific case report by application_number and version. Returns None if not found or table is missing."""
    try:
        client = _get_client()
        response = (
            client.table(_CASE_REPORTS_TABLE)
            .select("*")
            .eq("application_number", application_number)
            .eq("version", version)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning(
            "Could not query case_reports table (table may not exist): %s", exc
        )
        return None


def fetch_reports(
    application_number: str,
    limit: int = 20,
) -> list[dict]:
    """
    Retrieve case report history for an application, newest first.
    Returns metadata only (pdf_base64 excluded) to keep responses light.
    Returns [] if table does not exist.
    """
    try:
        client = _get_client()
        response = (
            client.table(_CASE_REPORTS_TABLE)
            .select("id, application_number, version, generated_at, generated_by, page_count, file_size_bytes, checksum, metadata")
            .eq("application_number", application_number)
            .order("version", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.warning(
            "Could not query case_reports table (table may not exist): %s", exc
        )
        return []


def get_pdf_bytes(report: dict) -> Optional[bytes]:
    """Extract PDF bytes from a stored report record (base64-decoded)."""
    pdf_base64 = report.get("pdf_base64")
    if not pdf_base64:
        return None
    try:
        return base64.b64decode(pdf_base64)
    except Exception:
        return None


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF by scanning for the /Type /Page pattern."""
    count = 0
    # Simple heuristic: count occurrences of "/Type /Page" or "/Type/Page"
    # that are NOT "/Type /Pages" (the parent tree node).
    # This works reliably for ReportLab-generated PDFs.
    content = pdf_bytes
    idx = 0
    while True:
        pos = content.find(b"/Type", idx)
        if pos == -1:
            break
        # Look ahead for /Page (not /Pages)
        rest = content[pos:pos + 30]
        if rest.startswith(b"/Type /Page\n") or rest.startswith(b"/Type /Page\r") or rest.startswith(b"/Type /Page "):
            count += 1
        elif rest.startswith(b"/Type/Page\n") or rest.startswith(b"/Type/Page\r") or rest.startswith(b"/Type/Page "):
            count += 1
        idx = pos + 10
    return max(count, 0)


__all__ = [
    "is_configured",
    "generate_and_store",
    "fetch_report",
    "fetch_reports",
    "get_pdf_bytes",
]
