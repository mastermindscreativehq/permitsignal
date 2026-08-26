from __future__ import annotations

"""
PermitSignal Source Registry — configuration-driven government source management.

Purpose
-------
Store and retrieve government source configurations that drive the
multi-source ingestion pipeline.  Adding a new government source is
inserting a row in the ``government_sources`` table (or the JSON
fallback) — no new code is required for standard PDF or HTML-agenda
sources.

Each source record describes:
- Geography: state, city, county
- Agency identity: name, URL
- Content type: source_type (pdf_direct, html_agenda, platform_*)
- Adapter selection: which adapter handles discovery/download
- Runtime state: active flag, last ingestion metadata

Storage
-------
Supabase ``government_sources`` table (migration 0010) is the primary
store.  A JSON fallback at ``data/state/government_sources.json``
allows the system to operate without Supabase (e.g. local development,
CI).

Design Principles
-----------------
- ADDITIVE ONLY: never modifies the existing pipeline_orchestrator,
  document_downloader, or document_registry contracts.
- Configuration-driven: adding a new government source = inserting a
  row.  No new Python modules for standard source types.
- Backward-compatible: the existing Provo Planning Commission source is
  seeded in migration 0010 and discovered identically to today.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

DEFAULT_TABLE = "government_sources"
FALLBACK_PATH = Path("data/state/government_sources.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================================================================
# Supabase connectivity (mirrors lead_repository pattern)
# =========================================================================


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY"))


def get_client():
    if not is_configured():
        raise RuntimeError(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY."
        )
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def get_table_name() -> str:
    return os.getenv("SUPABASE_GOVERNMENT_SOURCES_TABLE", DEFAULT_TABLE)


# =========================================================================
# JSON fallback (offline / no-Supabase mode)
# =========================================================================


def _load_fallback() -> list[dict[str, Any]]:
    if not FALLBACK_PATH.exists():
        return []
    try:
        data = json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_fallback(sources: list[dict[str, Any]]) -> None:
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_PATH.write_text(
        json.dumps(sources, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# =========================================================================
# CRUD operations
# =========================================================================


def list_sources(
    active_only: bool = False,
    state: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return all government sources, optionally filtered by active status
    and state.
    """
    if is_configured():
        try:
            client = get_client()
            table = get_table_name()
            query = client.table(table).select("*")
            if active_only:
                query = query.eq("active", True)
            if state:
                query = query.eq("state", state)
            resp = query.order("source_key").execute()
            return resp.data or []
        except Exception:
            pass

    # Fallback
    sources = _load_fallback()
    if active_only:
        sources = [s for s in sources if s.get("active", True)]
    if state:
        sources = [s for s in sources if s.get("state") == state]
    return sources


def get_source(source_key: str) -> Optional[dict[str, Any]]:
    """Retrieve a single source by its unique key."""
    if is_configured():
        try:
            client = get_client()
            table = get_table_name()
            resp = (
                client.table(table)
                .select("*")
                .eq("source_key", source_key)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]
        except Exception:
            pass

    for s in _load_fallback():
        if s.get("source_key") == source_key:
            return s
    return None


def upsert_source(source: dict[str, Any]) -> dict[str, Any]:
    """
    Insert or update a government source.  The ``source_key`` field is
    the unique identifier.  ``updated_at`` is set automatically.
    """
    source_key = source.get("source_key")
    if not source_key:
        raise ValueError("source_key is required")

    source["updated_at"] = _now()

    if "created_at" not in source:
        existing = get_source(source_key)
        if existing:
            source["created_at"] = existing.get("created_at", _now())
        else:
            source["created_at"] = _now()

    if is_configured():
        try:
            client = get_client()
            table = get_table_name()
            client.table(table).upsert(source, on_conflict="source_key").execute()
            return source
        except Exception:
            pass

    # Fallback
    sources = _load_fallback()
    merged = False
    for i, s in enumerate(sources):
        if s.get("source_key") == source_key:
            sources[i] = source
            merged = True
            break
    if not merged:
        sources.append(source)
    _save_fallback(sources)
    return source


def update_ingestion_metadata(
    source_key: str,
    metadata: dict[str, Any],
) -> None:
    """Update the ingestion metadata and last_ingested_at for a source."""
    now = _now()
    patch = {
        "ingestion_metadata": metadata,
        "last_ingested_at": now,
        "updated_at": now,
    }

    if is_configured():
        try:
            client = get_client()
            table = get_table_name()
            client.table(table).update(patch).eq("source_key", source_key).execute()
            return
        except Exception:
            pass

    # Fallback
    sources = _load_fallback()
    for s in sources:
        if s.get("source_key") == source_key:
            s.update(patch)
            break
    _save_fallback(sources)


def deactivate_source(source_key: str) -> bool:
    """Set a source to inactive. Returns True if found."""
    if is_configured():
        try:
            client = get_client()
            table = get_table_name()
            resp = (
                client.table(table)
                .update({"active": False, "updated_at": _now()})
                .eq("source_key", source_key)
                .execute()
            )
            return bool(resp.data)
        except Exception:
            pass

    sources = _load_fallback()
    for s in sources:
        if s.get("source_key") == source_key:
            s["active"] = False
            s["updated_at"] = _now()
            _save_fallback(sources)
            return True
    return False


__all__ = [
    "is_configured",
    "list_sources",
    "get_source",
    "upsert_source",
    "update_ingestion_metadata",
    "deactivate_source",
    "FALLBACK_PATH",
]
