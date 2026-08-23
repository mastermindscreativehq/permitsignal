"""
Entity Intelligence Repository (Supabase persistence).

Persists the normalized output of the deep case research engine into the
tables created by supabase/migrations/0008_add_entity_intelligence.sql:

    entities, case_entities, relationships, sources, evidence,
    entity_matches, research_runs

Design principles (mirroring lead_repository):
- Entirely ADDITIVE: nothing here mutates the leads table or the JSON
  artifact; the lead's own ``case_intelligence`` JSONB blob remains the
  always-produced artifact.
- Opt-in and degrading: when Supabase is not configured the caller can
  skip persistence; genuine network/PostgREST errors propagate so the
  caller records them instead of pretending the sync succeeded.
- Deterministic keys (entity_key/evidence_id/match_id/source_id) make
  every write an idempotent upsert, so repeated research runs refresh
  intelligence instead of duplicating it.

The migration must be applied once via the Supabase SQL editor or
``supabase db push`` before this module can succeed -- exactly like
0001_create_leads_table.sql, this module does not run DDL itself.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY"))


def get_client() -> Any:
    if not is_configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set to use "
            "entity_repository. See supabase/migrations/"
            "0008_add_entity_intelligence.sql for the required schema."
        )
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (list, dict, str, int, float, bool)):
        return value
    return str(value)


# =========================================================================
# Row builders (pure functions -- unit-testable without any client)
# =========================================================================

def entity_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entity in record.get("entities", []):
        claims = entity.get("claims", [])
        attributes = {
            k: v for k, v in (entity.get("attributes") or {}).items()
        }
        attributes["case_roles"] = entity.get("case_roles", [])
        attributes["research_status"] = entity.get("research_status")
        if claims:
            attributes["claims"] = claims
        rows.append({
            "entity_key": entity.get("entity_key"),
            "entity_type": entity.get("entity_type"),
            "canonical_name": entity.get("canonical_name"),
            "attributes": _json_safe(attributes),
            "match_status": entity.get("match_status"),
            "match_confidence": entity.get("match_confidence"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def case_entity_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    app = record.get("application_number")
    rows = []
    for entity in record.get("entities", []):
        for role in entity.get("case_roles", []):
            rows.append({
                "application_number": app,
                "entity_key": entity.get("entity_key"),
                "case_role": role,
                "confidence": entity.get("match_confidence"),
                "sources": [
                    s.get("url") for s in entity.get("sources", []) if s.get("url")
                ],
            })
    return rows


def relationship_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rel in record.get("relationships", []):
        rows.append({
            "subject_entity_key": rel.get("subject_entity_key"),
            "predicate": rel.get("predicate"),
            "object_entity_key": rel.get("object_entity_key"),
            "application_number": rel.get("application_number") or "",
            "confidence": rel.get("confidence"),
            "sources": rel.get("sources", []),
            "evidence_ids": rel.get("evidence_ids", []),
        })
    return rows


def source_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for src in record.get("sources", []):
        rows.append({
            "source_id": src.get("source_id"),
            "url": src.get("url"),
            "domain": src.get("domain"),
            "title": src.get("title"),
            "source_type": src.get("source_type"),
            "hierarchy_rank": src.get("hierarchy_rank"),
            "discovery_method": src.get("discovery_method"),
        })
    return rows


def evidence_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for ev in record.get("evidence", []):
        rows.append({
            "evidence_id": ev.get("evidence_id"),
            "application_number": ev.get("application_number"),
            "subject_type": ev.get("subject_type"),
            "subject_key": ev.get("subject_key"),
            "claim": ev.get("claim"),
            "value": ev.get("value"),
            "source_id": ev.get("source_id"),
            "source_url": ev.get("url"),
            "source_domain": ev.get("domain"),
            "source_title": ev.get("title"),
            "source_type": ev.get("source_type"),
            "hierarchy_rank": ev.get("hierarchy_rank"),
            "discovery_method": ev.get("discovery_method"),
            "evidence_text": ev.get("evidence_text"),
            "discovered_at": ev.get("discovered_at"),
            "confidence": ev.get("confidence"),
            "verification_status": ev.get("verification_status") or "unverified",
        })
    return rows


def match_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entity in record.get("entities", []):
        for m in entity.get("matches", []):
            if not m.get("candidate_url"):
                continue
            rows.append({
                "match_id": m.get("match_id"),
                "entity_key": m.get("entity_key"),
                "candidate_kind": m.get("candidate_kind"),
                "candidate_name": m.get("candidate_name"),
                "candidate_url": m.get("candidate_url"),
                "match_status": m.get("match_status"),
                "match_confidence": m.get("match_confidence"),
                "match_reasons": m.get("match_reasons", []),
                "matched_signals": m.get("matched_signals", []),
                "conflicting_signals": m.get("conflicting_signals", []),
                "source_url": m.get("source_url"),
            })
    return rows


# =========================================================================
# Persistence entry point
# =========================================================================

def persist_case_intelligence(
    record: dict[str, Any],
    client: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Upsert one research run's normalized output into Supabase.

    Raises on genuine errors (caller records them); returns per-table row
    counts when the sync succeeds.
    """
    if not record.get("application_number"):
        return {"status": "skipped", "reason": "missing_application_number"}

    client = client or get_client()

    try:
        return _persist_with_client(record, client)
    except RuntimeError:
        raise
    except Exception as exc:
        message = str(exc)
        if "Could not find the table" in message or "PGRST205" in message:
            raise RuntimeError(
                "Entity intelligence schema is not applied yet. Run "
                "supabase/migrations/0008_add_entity_intelligence.sql "
                "in the Supabase SQL editor (or `supabase db push`) first."
            ) from exc
        raise


def _persist_with_client(record: dict[str, Any], client: Any) -> dict[str, Any]:
    counts: dict[str, int] = {}

    def _upsert(table: str, rows: list[dict], conflict: Optional[str] = None) -> None:
        if not rows:
            counts[table] = 0
            return
        query = client.table(table).upsert(
            [_json_safe_row(r) for r in rows],
            on_conflict=conflict,
        ) if conflict else client.table(table).upsert([_json_safe_row(r) for r in rows])
        query.execute()
        counts[table] = len(rows)

    _upsert("entities", entity_rows(record), conflict="entity_key")
    # NOTE: entity-intelligence source registry is "entity_sources" --
    # public.sources already exists as the document/collector registry.
    _upsert("entity_sources", source_rows(record), conflict="source_id")
    _upsert("case_entities", case_entity_rows(record),
            conflict="application_number,entity_key,case_role")
    _upsert("relationships", relationship_rows(record),
            conflict="subject_entity_key,predicate,object_entity_key,application_number")
    _upsert("evidence", evidence_rows(record), conflict="evidence_id")
    _upsert("entity_matches", match_rows(record), conflict="match_id")

    run = record.get("research_run", {})
    run_payload = {
        "application_number": record.get("application_number"),
        "status": run.get("status", "completed"),
        "depth_reached": run.get("depth_reached", 0),
        "queries_executed": run.get("queries_executed", 0),
        "pages_fetched": run.get("pages_fetched", 0),
        "entities_discovered": run.get("entities_discovered", 0),
        "evidence_collected": run.get("evidence_collected", 0),
        "errors": run.get("errors", []),
        "params": run.get("params", {}),
    }
    if run.get("completed_at"):
        run_payload["completed_at"] = run["completed_at"]
    client.table("research_runs").insert(_json_safe_row(run_payload)).execute()
    counts["research_runs"] = 1

    return {"status": "synced", **counts}


def fetch_case_intelligence_summary(
    application_number: str,
    client: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Read back the persisted normalized intelligence for one case:
    latest research run, linked entities, and claim counts. Returns {}
    when nothing is stored or Supabase is not configured.
    """
    if not is_configured():
        return {}

    client = client or get_client()
    summary: dict[str, Any] = {"application_number": application_number}

    runs = (
        client.table("research_runs")
        .select("*")
        .eq("application_number", application_number)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if runs.data:
        summary["latest_research_run"] = runs.data[0]

    links = (
        client.table("case_entities")
        .select("entity_key, case_role, confidence")
        .eq("application_number", application_number)
        .execute()
    )
    entity_keys = [row["entity_key"] for row in links.data or []]
    summary["case_entities"] = links.data or []

    if entity_keys:
        entities = (
            client.table("entities")
            .select("entity_key, entity_type, canonical_name, match_status, match_confidence")
            .in_("entity_key", entity_keys)
            .execute()
        )
        summary["entities"] = entities.data or []

    evidence_count = (
        client.table("evidence")
        .select("evidence_id", count="exact")
        .eq("application_number", application_number)
        .execute()
    )
    summary["evidence_total"] = getattr(evidence_count, "count", None)

    return summary


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


__all__ = [
    "is_configured",
    "get_client",
    "persist_case_intelligence",
    "fetch_case_intelligence_summary",
    "entity_rows",
    "case_entity_rows",
    "relationship_rows",
    "source_rows",
    "evidence_rows",
    "match_rows",
]
