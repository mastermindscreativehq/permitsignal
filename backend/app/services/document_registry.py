from __future__ import annotations

"""
PermitSignal document discovery registry.

Purpose
-------
Track which government documents (identified by a stable document URL)
have already been discovered/ingested, so the live discovery layer
(backend.app.services.discovery_orchestrator) does not repeatedly
re-download and re-run the full pipeline against a document it has
already processed.

This is intentionally NOT a new database: it is a small JSON manifest
under data/state/, the same convention already used for the pipeline's
other generated artifacts (data/output/permitsignal_opportunities.json).
Downstream duplicate prevention for lead records continues to rely
entirely on the existing lead_repository.upsert_leads() application_number
upsert -- this module only prevents redundant document-level
discovery/ingestion work; it is never a second source of truth for lead
identity.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


REGISTRY_PATH = Path("data/state/document_registry.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_registry(path: Path | str = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    """
    Load the registry, or return {} if it does not exist yet or is
    corrupt. A missing/corrupt registry must never raise -- discovery
    should degrade to "nothing known yet", not fail the run.
    """
    path = Path(path)

    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def save_registry(
    registry: dict[str, dict[str, Any]],
    path: Path | str = REGISTRY_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def is_known(
    document_url: str,
    registry: dict[str, dict[str, Any]],
) -> bool:
    return document_url in registry


def filter_new_records(
    records: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
    url_key: str = "url",
) -> list[dict[str, Any]]:
    """
    Return only the records whose document URL is not already present in
    the registry. Records with no URL are dropped -- there is no stable
    identifier to track them by.
    """
    return [
        record
        for record in records
        if record.get(url_key) and record[url_key] not in registry
    ]


def record_discovered(
    registry: dict[str, dict[str, Any]],
    record: dict[str, Any],
    url_key: str = "url",
) -> dict[str, Any]:
    """
    Register a newly discovered document as "discovered" (not yet
    ingested). Does not overwrite an existing entry -- a document already
    known keeps its prior status/history.
    """
    url = record.get(url_key)

    if not url:
        raise ValueError("record has no document URL to register.")

    if url in registry:
        return registry[url]

    entry = {
        "source": record.get("source"),
        "title": record.get("title"),
        "document_url": url,
        "document_date": record.get("date"),
        "record_type": record.get("record_type"),
        "status": "discovered",
        "discovered_at": _now(),
        "processed_at": None,
        "error": None,
    }

    registry[url] = entry

    return entry


def record_processed(
    registry: dict[str, dict[str, Any]],
    document_url: str,
    status: str,
    **metadata: Any,
) -> dict[str, Any]:
    """
    Update a document's registry entry after an ingestion attempt.

    status is typically "ingested" or "error". Any additional metadata
    (pdf_path, applications, opportunities, supabase_sync, error) is
    merged into the entry verbatim -- nothing here is fabricated, only
    what the caller actually observed.
    """
    entry = registry.setdefault(
        document_url,
        {
            "document_url": document_url,
            "discovered_at": _now(),
        },
    )

    entry["status"] = status
    entry["processed_at"] = _now()
    entry.update(metadata)

    return entry


__all__ = [
    "REGISTRY_PATH",
    "load_registry",
    "save_registry",
    "is_known",
    "filter_new_records",
    "record_discovered",
    "record_processed",
]
