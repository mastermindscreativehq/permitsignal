"""
PermitSignal Lead Intelligence Repository (Supabase persistence)

Purpose
-------
Persist canonical lead/opportunity records to Supabase so lead status
(NO_CONTACT -> CONTACTABLE, etc.) and contact evidence can be tracked
across repeated pipeline runs, instead of being recomputed from scratch
every time.

Design principle: this module is entirely ADDITIVE to the existing
pipeline.

- data/output/permitsignal_opportunities.json remains the pipeline's
  primary, always-produced artifact. Nothing here changes its shape.
- Supabase persistence is opt-in (run_pipeline(sync_to_supabase=True) or
  the --sync-supabase CLI flag) and never raises out of the pipeline: a
  missing configuration or a genuine Supabase/network failure degrades to
  a recorded status in metadata["supabase_sync"], never a crashed run.
- Every lead is upserted keyed on application_number, so re-running the
  pipeline against the same packet updates existing rows instead of
  duplicating them.

Schema
------
See supabase/migrations/0001_create_leads_table.sql for the table
definition. That file must be applied once (via the Supabase SQL editor
or `supabase db push`) before sync_to_supabase=True can succeed --
this module does not attempt to run DDL itself.

Environment
-----------
SUPABASE_URL=...
SUPABASE_KEY=...              (a key with insert/update grants on the
                                "leads" table -- service role recommended
                                for server-side pipeline runs)
SUPABASE_LEADS_TABLE=leads    (optional override)

These are loaded from the project's .env file (via python-dotenv) as soon
as this module is imported, in addition to whatever is already present in
the process environment. Variables already set in the environment take
precedence over .env -- see load_dotenv()'s default override=False.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

# Populate os.environ from the project's .env file, if present, so
# is_configured()/get_client() see SUPABASE_URL/SUPABASE_KEY without every
# caller having to load it themselves. Safe no-op when .env is absent, and
# never overrides variables the environment already provides.
load_dotenv()


DEFAULT_TABLE = "leads"

# Columns promoted out of the raw lead dict for indexing/filtering in
# Postgres. Every field on the lead -- including anything not listed
# here -- is also preserved verbatim in the JSONB "record" column, so
# nothing is ever lost even as the lead schema evolves.
_COLUMNS = (
    "application_number",
    "applicant_name",
    "normalized_applicant_name",
    "company_name",
    "company_website",
    "company_domain",
    "application_type",
    "project_address",
    "neighborhood",
    "status",
    "description",
    "parcel_number",
    "acreage",
    "zoning",
    "owner_name",
    "owner_entity",
    "owner_type",
    "owner_contact_name",
    "owner_contact_email",
    "owner_contact_phone",
    "owner_website",
    "owner_source",
    "owner_confidence",
    "applicant_entity",
    "applicant_contact_name",
    "applicant_contact_email",
    "applicant_contact_phone",
    "applicant_source",
    "applicant_confidence",
    "parties",
    "friction_score",
    "friction_signals",
    "friction_events",
    "next_project_date",
    "next_project_event",
    "next_project_time",
    "has_future_opportunity",
    "days_until_event",
    "urgency",
    "priority",
    "priority_score",
    "is_actionable",
    "opportunity_reason",
    "approval_status",
    "approval_action",
    "approval_action_type",
    "approval_confidence",
    "approval_basis",
    "approval_relevant_date",
    "approval_source",
    "approval_source_type",
    "approval_evidence",
    "approval_reason",
    "contact_name",
    "contact_role",
    "applicant_email",
    "applicant_phone",
    "contact_email",
    "contact_phone",
    "linkedin_url",
    "email_source",
    "phone_source",
    "company_source",
    "contact_source",
    "email_confidence",
    "phone_confidence",
    "contact_confidence",
    "contact_is_public",
    "contact_is_verified",
    "identity_status",
    "enrichment_status",
    "enrichment_method",
    "lead_status",
    "is_contactable",
    "contactability_level",
    "commercial_readiness",
    "recommended_commercial_action",
    "commercial_action_reason",
    "outreach_status",
    "outreach_qualification_status",
    "outreach_channel",
    "outreach_contact_type",
    "outreach_contact_reason",
    "outreach_message_subject",
    "outreach_message_body",
    "follow_up_required",
    "follow_up_reason",
    "last_outreach_at",
    "outreach_events",
    "source",
    "source_url",
    "source_key",
    "municipality",
    "state",
    "staff_contact_name",
    "staff_contact_email",
    "staff_contact_phone",
    # Address Intelligence (migration 0009)
    "address_geocoded_lat",
    "address_geocoded_lng",
    "address_geocoded_city",
    "address_geocoded_state",
    "address_geocoded_postal",
    "address_geocoded_county",
    "address_geocoded_full",
    "address_geocoding_source",
    "address_geocoding_confidence",
    "address_geocoding_method",
    "address_geocoding_evidence",
    "address_geocoded_at",
    "address_parcel_id_verified",
    "address_parcel_source",
    "address_source_address",
    "address_enrichment_status",
)


def is_configured() -> bool:
    """
    True only when both SUPABASE_URL and SUPABASE_KEY are present in the
    process environment. Callers should check this before attempting a
    sync if they want to avoid the RuntimeError raised by get_client().
    """
    return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY"))


def get_table_name() -> str:
    return os.getenv("SUPABASE_LEADS_TABLE", DEFAULT_TABLE)


def get_client() -> Any:
    """
    Lazily construct a Supabase client.

    Raises RuntimeError with a clear message when SUPABASE_URL/
    SUPABASE_KEY are not configured, rather than a confusing import or
    attribute error deep in the supabase-py client.
    """
    if not is_configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set to use "
            "lead_repository. See supabase/migrations/"
            "0001_create_leads_table.sql for the required schema."
        )

    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )


def _json_safe(value: Any) -> Any:
    """
    Supabase's REST layer serializes every row to JSON. Pass through
    values that are already JSON-safe; stringify anything else (e.g. a
    date object) rather than letting the client fail on serialization.
    """
    if value is None or isinstance(value, (list, dict, str, int, float, bool)):
        return value

    return str(value)


def _jsonb_array_column(value: Any) -> list[Any]:
    """
    Coerce a "jsonb not null default '[]'::jsonb" COLUMN (friction_signals,
    parties) to [] when no evidence exists, instead of an explicit SQL NULL.

    A Postgres column default only applies when the column is omitted from
    the payload entirely, not when it is explicitly sent as null.
    lead_to_row() always includes every column in _COLUMNS, so a lead with
    no evidence for one of these columns (Opportunity's own
    field(default_factory=list) already treats this case as []) would
    otherwise send an explicit null and violate the constraint.

    This does not fabricate evidence: [] already is the canonical "none"
    representation used by Opportunity, not an invented one. Only the
    promoted column is normalized here -- the raw value (even if it were
    None) is preserved untouched in the "record" JSONB blob below.
    """
    if value is None:
        return []

    return _json_safe(value)


def lead_to_row(lead: dict[str, Any]) -> dict[str, Any]:
    """
    Map a canonical lead/opportunity dict to a Supabase row.

    Never fabricates a value: any field absent from the lead becomes an
    explicit None column. The full lead dict is preserved verbatim in the
    "record" JSONB column, so nothing is lost even for fields not
    promoted to their own column above.
    """
    row: dict[str, Any] = {
        column: _json_safe(lead.get(column)) for column in _COLUMNS
    }

    row["friction_signals"] = _jsonb_array_column(
        lead.get("friction_signals")
    )
    row["parties"] = _jsonb_array_column(
        lead.get("parties")
    )
    row["outreach_events"] = _jsonb_array_column(
        lead.get("outreach_events")
    )

    row["record"] = {key: _json_safe(value) for key, value in lead.items()}
    row["updated_at"] = datetime.now(timezone.utc).isoformat()

    return row


def upsert_leads(
    leads: list[dict[str, Any]],
    client: Optional[Any] = None,
    table: Optional[str] = None,
) -> dict[str, Any]:
    """
    Upsert canonical lead records into Supabase, keyed on
    application_number.

    Records missing application_number are skipped (never assigned a
    fabricated key) and counted in the returned status.

    This does NOT swallow genuine Supabase/network errors -- it lets them
    propagate so the caller (pipeline_orchestrator._persist_leads) can
    record the failure explicitly rather than pretending the sync
    succeeded.
    """
    if not leads:
        return {"status": "skipped", "reason": "no_leads", "rows": 0}

    rows = [
        lead_to_row(lead) for lead in leads if lead.get("application_number")
    ]

    skipped = len(leads) - len(rows)

    if not rows:
        return {
            "status": "skipped",
            "reason": "no_application_number",
            "rows": 0,
            "skipped": skipped,
        }

    table = table or get_table_name()
    client = client or get_client()

    client.table(table).upsert(rows, on_conflict="application_number").execute()

    result: dict[str, Any] = {"status": "synced", "rows": len(rows)}

    if skipped:
        result["skipped"] = skipped

    return result


def fetch_lead(
    application_number: str,
    client: Optional[Any] = None,
    table: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    Retrieve one canonical lead/opportunity record from Supabase by its
    application_number (Phase 4 API retrieval boundary).

    Returns the full canonical lead dict -- the same shape produced by
    pipeline_orchestrator and verbatim-preserved in the "record" JSONB
    column by lead_to_row() above -- or None when Supabase is not
    configured or no row matches. Never fabricates a partial record: a
    row with no "record" payload is treated as not found.

    Genuine Supabase/network errors propagate, exactly like upsert_leads(),
    so the API layer decides how to degrade (e.g. fall back to the JSON
    artifact) rather than this module silently hiding a real failure.
    """
    if not is_configured():
        return None

    table = table or get_table_name()
    client = client or get_client()

    response = (
        client.table(table)
        .select("record")
        .eq("application_number", application_number)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0].get("record")


def fetch_leads(
    client: Optional[Any] = None,
    table: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Retrieve every canonical lead/opportunity record from Supabase
    (Phase 4 API retrieval boundary).

    Returns [] when Supabase is not configured or the table has no rows --
    never raises for a missing configuration, mirroring is_configured()'s
    role elsewhere in this module. Genuine Supabase/network errors
    propagate, exactly like upsert_leads()/fetch_lead() above.
    """
    if not is_configured():
        return []

    table = table or get_table_name()
    client = client or get_client()

    query = client.table(table).select("record")

    if limit:
        query = query.limit(limit)

    response = query.execute()

    return [row["record"] for row in (response.data or []) if row.get("record")]


__all__ = [
    "DEFAULT_TABLE",
    "is_configured",
    "get_table_name",
    "get_client",
    "lead_to_row",
    "upsert_leads",
    "fetch_lead",
    "fetch_leads",
]
