"""
PermitSignal Profile Matrix Engine

Purpose
-------
The Matrix Engine is the intelligence layer that generates content for
individual applicant/profile contexts. It:

1. Builds a structured profile context from an existing lead record.
2. Sends the context + user instruction to an LLM provider.
3. Returns the generated output WITHOUT mutating the source lead.
4. Stores generated outputs as versioned artifacts in Supabase.

Architecture Principle
----------------------
SOURCE DATA (the lead record) is read-only from the Matrix's perspective.
GENERATED DATA (Matrix outputs) lives in a separate table
(matrix_outputs) and is linked by application_number.
No Matrix operation ever writes to the leads table.

Environment
-----------
MATRIX_LLM_PROVIDER=openai|anthropic|openrouter|passthrough
MATRIX_MODEL_NAME=gpt-4o (or claude-sonnet-4-20250514, etc.)

Provider-specific keys:
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
  OPENROUTER_API_KEY=...

When no provider is configured, falls back to "passthrough" mode
(echoes the instruction + context without LLM generation).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Matrix system prompt
# ---------------------------------------------------------------------------

MATRIX_SYSTEM_PROMPT = """\
You are PROFILE MATRIX — the private intelligence, reasoning, writing, and
creative-generation engine attached to ONE specific applicant/profile.

You operate within the PermitSignal government planning/permit intelligence
system. Your job is to understand the complete profile context supplied and
then execute the user's instruction with exceptional intelligence, precision,
contextual awareness, professional writing ability, and natural human reasoning.

CORE RULES:
- Use ONLY the supplied profile context. Do not invent missing source data.
- If a field is unavailable, acknowledge it rather than fabricating a value.
- Never confuse information belonging to another profile.
- Preserve names, addresses, case numbers, organisations, dates, and
  terminology exactly when supplied.
- Write like an exceptionally capable senior professional.
- Be intelligent, persuasive, natural, clear, authoritative, and specific.
- Every sentence should have a purpose.
- Do not add content the user did not request.
- Do not explain your reasoning unless asked.

OUTPUT FORMAT:
Return your generated content directly. Do not wrap it in markdown fences.
Do not add preamble like "Here is the generated content:".
Just produce the requested output.
"""

# ---------------------------------------------------------------------------
# Profile context builder
# ---------------------------------------------------------------------------

# Fields to extract from the lead record for Matrix context.
# Organised by category for clarity. Only non-None values are included.

_APPLICANT_FIELDS = [
    "applicant_name",
    "normalized_applicant_name",
    "applicant_email",
    "applicant_phone",
    "applicant_entity",
    "applicant_contact_name",
    "applicant_contact_email",
    "applicant_contact_phone",
    "applicant_source",
    "applicant_confidence",
]

_ORGANISATION_FIELDS = [
    "company_name",
    "company_website",
    "company_domain",
    "company_source",
]

_CASE_FIELDS = [
    "application_number",
    "application_type",
    "status",
    "description",
    "project_description",
    "neighborhood",
]

_PROPERTY_FIELDS = [
    "project_address",
    "parcel_number",
    "acreage",
    "zoning",
]

_OWNER_FIELDS = [
    "owner_name",
    "owner_entity",
    "owner_type",
    "owner_contact_name",
    "owner_contact_email",
    "owner_contact_phone",
    "owner_website",
    "owner_source",
    "owner_confidence",
]

_PARTIES_FIELDS = [
    "parties",
]

_STAFF_FIELDS = [
    "staff_contact_name",
    "staff_contact_email",
    "staff_contact_phone",
]

_CONTACT_INTEL_FIELDS = [
    "contact_name",
    "contact_role",
    "contact_email",
    "contact_phone",
    "linkedin_url",
    "email_source",
    "phone_source",
    "contact_source",
    "email_confidence",
    "phone_confidence",
    "contact_confidence",
    "contact_is_public",
    "contact_is_verified",
    "identity_status",
    "enrichment_status",
    "enrichment_method",
]

_FRICTION_FIELDS = [
    "friction_score",
    "friction_signals",
    "friction_events",
    "events",
]

_TIMING_FIELDS = [
    "next_project_date",
    "next_project_event",
    "next_project_time",
    "has_future_opportunity",
    "days_until_event",
    "urgency",
    "future_project_dates",
    "historical_project_dates",
]

_OPPORTUNITY_FIELDS = [
    "priority",
    "priority_score",
    "is_actionable",
    "opportunity_reason",
    "lead_status",
    "is_contactable",
]

_APPROVAL_FIELDS = [
    "approval_status",
    "approval_action",
    "approval_action_type",
    "approval_confidence",
    "approval_basis",
    "approval_relevant_date",
    "approval_source",
    "approval_evidence",
    "approval_reason",
]

_COMMERCIAL_FIELDS = [
    "contactability_level",
    "commercial_readiness",
    "recommended_commercial_action",
    "commercial_action_reason",
]

_OUTREACH_FIELDS = [
    "outreach_status",
    "outreach_qualification_status",
    "outreach_channel",
    "outreach_message_subject",
    "follow_up_required",
    "follow_up_reason",
]

_ECONOMIC_FIELDS = [
    "estimated_value_low",
    "estimated_value_high",
    "estimated_value_mid",
    "estimated_value_confidence",
    "public_funding_status",
    "public_spend_low",
    "public_spend_high",
    "public_spend_mid",
]

_PRICING_FIELDS = [
    "pricing",
]

_INTELLIGENCE_FIELDS = [
    "approval_intelligence",
]

_PREDICTIONS_FIELDS = [
    "predictions",
]

_INVESTIGATION_FIELDS = [
    "investigation",
]

_SOURCE_FIELDS = [
    "source",
    "source_url",
    "municipality",
    "state",
]

_FIELD_GROUPS = [
    ("Applicant", _APPLICANT_FIELDS),
    ("Organisation", _ORGANISATION_FIELDS),
    ("Case / Application", _CASE_FIELDS),
    ("Property", _PROPERTY_FIELDS),
    ("Property Owner", _OWNER_FIELDS),
    ("Parties", _PARTIES_FIELDS),
    ("Government Staff", _STAFF_FIELDS),
    ("Contact Intelligence", _CONTACT_INTEL_FIELDS),
    ("Friction / History", _FRICTION_FIELDS),
    ("Timing / Events", _TIMING_FIELDS),
    ("Opportunity", _OPPORTUNITY_FIELDS),
    ("Approval Action", _APPROVAL_FIELDS),
    ("Commercial Intelligence", _COMMERCIAL_FIELDS),
    ("Outreach", _OUTREACH_FIELDS),
    ("Economic Intelligence", _ECONOMIC_FIELDS),
    ("Pricing", _PRICING_FIELDS),
    ("Deep Intelligence", _INTELLIGENCE_FIELDS),
    ("Predictions", _PREDICTIONS_FIELDS),
    ("Investigation", _INVESTIGATION_FIELDS),
    ("Source", _SOURCE_FIELDS),
]


def build_profile_context(lead: dict[str, Any]) -> str:
    """
    Build a structured text representation of the lead record
    for use as LLM context. Only includes fields with non-None values.
    Never mutates the lead dict.
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PROFILE CONTEXT")
    lines.append("=" * 60)

    for group_name, fields in _FIELD_GROUPS:
        group_lines: list[str] = []
        for field in fields:
            value = lead.get(field)
            if value is None:
                continue
            # Skip empty collections
            if isinstance(value, list) and len(value) == 0:
                continue
            if isinstance(value, dict) and len(value) == 0:
                continue
            # Format the value
            if isinstance(value, (list, dict)):
                formatted = json.dumps(value, indent=2, default=str)
            elif isinstance(value, bool):
                formatted = str(value)
            elif isinstance(value, (int, float)):
                formatted = str(value)
            else:
                formatted = str(value)
            group_lines.append(f"  {field}: {formatted}")

        if group_lines:
            lines.append(f"\n--- {group_name} ---")
            lines.extend(group_lines)

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Provider abstraction
# ---------------------------------------------------------------------------

def _get_provider() -> str:
    """Returns the configured LLM provider name."""
    return os.getenv("MATRIX_LLM_PROVIDER", "passthrough").lower()


def _get_model_name() -> str:
    """Returns the model name for the configured provider."""
    provider = _get_provider()
    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "openrouter": "openai/gpt-4o",
    }
    return os.getenv("MATRIX_MODEL_NAME", defaults.get(provider, "gpt-4o"))


def _call_openai(system_prompt: str, user_message: str) -> str:
    """Call OpenAI API."""
    import httpx

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = _get_model_name()
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_anthropic(system_prompt: str, user_message: str) -> str:
    """Call Anthropic API."""
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    model = _get_model_name()
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 4096,
            "temperature": 0.7,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]


def _call_openrouter(system_prompt: str, user_message: str) -> str:
    """Call OpenRouter API."""
    import httpx

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    model = _get_model_name()
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_passthrough(system_prompt: str, user_message: str) -> str:
    """
    Fallback passthrough mode: returns the instruction + context summary
    without LLM generation. Useful for testing the full pipeline without
    an LLM API key.
    """
    return (
        f"[MATRIX PASSTHROUGH MODE — No LLM provider configured]\n\n"
        f"Instruction received:\n{user_message}\n\n"
        f"To enable LLM generation, set MATRIX_LLM_PROVIDER and the "
        f"corresponding API key in your .env file.\n\n"
        f"Supported providers: openai, anthropic, openrouter, passthrough"
    )


_PROVIDERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "openrouter": _call_openrouter,
    "passthrough": _call_passthrough,
}


def generate_with_llm(system_prompt: str, user_message: str) -> str:
    """
    Route to the configured LLM provider and return the generated text.
    Falls back to passthrough if the provider is not recognised.
    """
    provider = _get_provider()
    fn = _PROVIDERS.get(provider, _call_passthrough)

    try:
        return fn(system_prompt, user_message)
    except Exception as exc:
        logger.warning("LLM provider '%s' failed: %s", provider, exc)
        return (
            f"[MATRIX GENERATION ERROR]\n\n"
            f"Provider: {provider}\n"
            f"Error: {exc}\n\n"
            f"Please check your MATRIX_LLM_PROVIDER and API key configuration."
        )


# ---------------------------------------------------------------------------
# Matrix generation (main entry point)
# ---------------------------------------------------------------------------

def execute_matrix_instruction(
    lead: dict[str, Any],
    instruction: str,
    previous_output: Optional[str] = None,
) -> str:
    """
    Execute a Matrix instruction against a lead profile context.

    1. Builds the profile context from the lead (read-only).
    2. Constructs the user message with context + instruction.
    3. Calls the configured LLM.
    4. Returns the generated output.

    The lead dict is NEVER mutated.
    """
    profile_context = build_profile_context(lead)

    user_message_parts = [profile_context]

    if previous_output:
        user_message_parts.append(
            "\n--- PREVIOUS MATRIX OUTPUT (for revision/continuation) ---\n"
            f"{previous_output}\n"
            "--- END PREVIOUS OUTPUT ---"
        )

    user_message_parts.append(f"\n--- USER INSTRUCTION ---\n{instruction}")
    user_message = "\n".join(user_message_parts)

    return generate_with_llm(MATRIX_SYSTEM_PROMPT, user_message)


# ---------------------------------------------------------------------------
# Matrix output storage (Supabase)
# ---------------------------------------------------------------------------

_MATRIX_TABLE = "matrix_outputs"


def _get_client() -> Any:
    """Get a Supabase client. Raises if not configured."""
    from backend.app.services.lead_repository import get_client, is_configured

    if not is_configured():
        raise RuntimeError(
            "Supabase is not configured. Matrix output storage requires "
            "SUPABASE_URL and SUPABASE_KEY."
        )
    return get_client()


def store_output(
    application_number: str,
    instruction: str,
    output: str,
    version: int,
    is_draft: bool = False,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Store a Matrix output in Supabase.
    Returns the stored record.
    """
    client = _get_client()

    row = {
        "application_number": application_number,
        "instruction": instruction,
        "output": output,
        "version": version,
        "is_draft": is_draft,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    response = client.table(_MATRIX_TABLE).insert(row).execute()
    return response.data[0] if response.data else row


def fetch_outputs(
    application_number: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Retrieve Matrix output history for an application, newest first.
    """
    client = _get_client()

    response = (
        client.table(_MATRIX_TABLE)
        .select("*")
        .eq("application_number", application_number)
        .order("version", desc=True)
        .limit(limit)
        .execute()
    )

    return response.data or []


def fetch_output_by_version(
    application_number: str,
    version: int,
) -> Optional[dict[str, Any]]:
    """
    Retrieve a specific Matrix output by version number.
    """
    client = _get_client()

    response = (
        client.table(_MATRIX_TABLE)
        .select("*")
        .eq("application_number", application_number)
        .eq("version", version)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def get_next_version(application_number: str) -> int:
    """
    Determine the next version number for an application.
    Returns 1 if no outputs exist yet.
    """
    client = _get_client()

    response = (
        client.table(_MATRIX_TABLE)
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


def save_draft(
    application_number: str,
    instruction: str,
    output: str,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Save a Matrix output as a draft (is_draft=True).
    """
    version = get_next_version(application_number)
    return store_output(
        application_number=application_number,
        instruction=instruction,
        output=output,
        version=version,
        is_draft=True,
        metadata=metadata,
    )


def save_final(
    application_number: str,
    instruction: str,
    output: str,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Save a Matrix output as a final version (is_draft=False).
    """
    version = get_next_version(application_number)
    return store_output(
        application_number=application_number,
        instruction=instruction,
        output=output,
        version=version,
        is_draft=False,
        metadata=metadata,
    )


__all__ = [
    "build_profile_context",
    "execute_matrix_instruction",
    "store_output",
    "fetch_outputs",
    "fetch_output_by_version",
    "get_next_version",
    "save_draft",
    "save_final",
    "MATRIX_SYSTEM_PROMPT",
]
