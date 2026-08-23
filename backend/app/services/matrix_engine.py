"""
PermitSignal Profile Matrix Engine

Purpose
-------
The Matrix Engine is the conversational intelligence layer that generates
content for individual applicant/profile contexts. It:

1. Builds a structured profile context from an existing lead record.
2. Detects the user's intent and retrieves only relevant context.
3. Supports multi-turn conversation history.
4. Sends context + conversation + instruction to an LLM provider.
5. Returns the generated output WITHOUT mutating the source lead.
6. Stores generated outputs as versioned artifacts in Supabase.

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
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Matrix system prompt (conversational)
# ---------------------------------------------------------------------------

MATRIX_SYSTEM_PROMPT = """\
You are PROFILE MATRIX — a conversational intelligence assistant attached to
ONE specific applicant/profile within the PermitSignal government planning and
permit intelligence system.

You have access to the complete profile context for this applicant. You use
it as needed to fulfill the user's requests. You are NOT a report generator.
You are a conversational assistant that follows instructions precisely.

CORE RULES:
- Follow the user's instruction exactly. Do what they ask, nothing more.
- If they ask for an email, write an email. Nothing else.
- If they ask for a summary, write a summary. Nothing else.
- If they ask a question, answer it directly. Nothing else.
- If they ask for a table, return a table. Nothing else.
- Never append unsolicited sections, intelligence dumps, or extra analysis.
- Never add "Case Intelligence", "Application Information", "Next Steps",
  "Supporting Intelligence", "Evidence", "Opportunity Analysis", "Pricing",
  "Sources", or any other section unless the user explicitly requested it.
- Use ONLY the supplied profile context. Do not invent missing source data.
- If a field is unavailable, acknowledge it rather than fabricating a value.
- Never confuse information belonging to another profile.
- Preserve names, addresses, case numbers, organisations, dates, and
  terminology exactly when supplied.
- Write like an exceptionally capable senior professional.
- Be intelligent, persuasive, natural, clear, authoritative, and specific.
- Every sentence should have a purpose.

CONTEXT USAGE:
- Profile intelligence is your context, not your output format.
- Retrieve only the information needed for the current request.
- The user's instruction determines what you produce.
- If the user asks about the applicant, use applicant data.
- If the user asks about pricing, use pricing data.
- If the user asks about friction, use friction data.
- Do not inject data the user did not ask about.

OUTPUT FORMAT:
- Return ONLY what the user requested.
- If they asked for an email, the response IS the email.
- If they asked for a paragraph, the response IS the paragraph.
- If they asked for a list, the response IS the list.
- Do not wrap output in markdown fences unless the user asked for code.
- Do not add preamble like "Here is the generated content:".
- Do not add postscript like "Let me know if you need anything else."
- Just produce the requested output.

CONVERSATION:
- Maintain context from earlier in the conversation.
- If the user says "make it shorter", modify the previous response.
- If the user says "more professional", adjust the tone.
- If the user says "give me options", provide alternatives.
- Build on previous exchanges naturally.

SAFETY:
- PermitSignal-generated simulations must not be represented as actual
  government-issued communications, payment instructions, invoices,
  approvals, or official records.
- Fictional scenarios and communications must be clearly fictional.
- Never present fictional payment information as real.
- Do not pollute ordinary responses with unnecessary safety warnings.
- Apply safety boundaries only when generating fictional government
  communications or payment-related content.
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

_FIELD_GROUPS: list[tuple[str, list[str]]] = [
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

# ---------------------------------------------------------------------------
# Context relevance filtering
# ---------------------------------------------------------------------------

# Maps task keywords to the field group names that are most relevant.
_TASK_CONTEXT_MAP: dict[tuple[str, ...], list[str]] = {
    ("email", "mail", "outreach", "message", "contact", "write", "draft"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Government Staff", "Contact Intelligence", "Outreach",
        "Timing / Events", "Source",
    ],
    ("summary", "summarize", "overview", "brief", "recap"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Timing / Events", "Opportunity", "Source",
    ],
    ("question", "who", "what", "when", "where", "how", "tell me",
     "explain", "describe", "about"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Property Owner", "Government Staff", "Contact Intelligence",
        "Timing / Events", "Opportunity", "Source",
    ],
    ("price", "pricing", "cost", "fee", "charge", "spend", "budget",
     "payment", "value", "economic", "financial"): [
        "Applicant", "Case / Application", "Pricing",
        "Economic Intelligence", "Property",
    ],
    ("friction", "conflict", "issue", "problem", "denial", "denied",
     "opposition", "objection", "history"): [
        "Applicant", "Case / Application", "Friction / History",
        "Property", "Property Owner", "Source",
    ],
    ("approval", "approved", "approve", "decision", "ruling", "vote",
     "hearing", "permit"): [
        "Applicant", "Case / Application", "Approval Action",
        "Timing / Events", "Government Staff", "Source",
    ],
    ("opportunity", "lead", "priority", "score", "urgent", "actionable",
     "timeline"): [
        "Applicant", "Case / Application", "Opportunity",
        "Timing / Events", "Commercial Intelligence", "Source",
    ],
    ("scenario", "fictional", "simulate", "roleplay", "creative",
     "story", "creative"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Property Owner", "Contact Intelligence", "Timing / Events",
    ],
    ("table", "list", "bullet", "format", "structure", "json",
     "organize"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Timing / Events", "Opportunity", "Source",
    ],
    ("investigation", "investigate", "research", "deep dive", "profile",
     "background"): [
        "Applicant", "Organisation", "Case / Application", "Property",
        "Property Owner", "Contact Intelligence", "Investigation",
        "Deep Intelligence", "Source",
    ],
    ("commercial", "business", "sales", "outreach strategy",
     "qualification", "lead qualification"): [
        "Applicant", "Organisation", "Commercial Intelligence",
        "Contact Intelligence", "Opportunity", "Outreach", "Source",
    ],
    ("everything", "all", "full", "complete", "entire", "comprehensive"): [
        gname for gname, _ in _FIELD_GROUPS
    ],
}

# Always include these groups regardless of task — they provide essential
# grounding context for any request.
_ALWAYS_INCLUDE: list[str] = [
    "Applicant",
    "Case / Application",
    "Property",
]


def _detect_relevant_groups(instruction: str) -> list[str]:
    """
    Analyse the user instruction and return the field group names
    that are relevant to the requested task. Always includes the
    core applicant/case/property groups for grounding.
    """
    lower = instruction.lower()
    relevant: set[str] = set(_ALWAYS_INCLUDE)

    for keywords, groups in _TASK_CONTEXT_MAP.items():
        for kw in keywords:
            if kw in lower:
                relevant.update(groups)
                break

    return list(relevant)


def build_filtered_context(lead: dict[str, Any], instruction: str) -> str:
    """
    Build a structured text representation of the lead record,
    filtered to only include groups relevant to the user's instruction.
    Only includes fields with non-None values. Never mutates the lead dict.
    """
    relevant_groups = _detect_relevant_groups(instruction)

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PROFILE CONTEXT")
    lines.append("=" * 60)

    for group_name, fields in _FIELD_GROUPS:
        if group_name not in relevant_groups:
            continue

        group_lines: list[str] = []
        for field in fields:
            value = lead.get(field)
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            if isinstance(value, dict) and len(value) == 0:
                continue
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


def build_profile_context(lead: dict[str, Any]) -> str:
    """
    Build a structured text representation of the FULL lead record
    for use as LLM context. Only includes fields with non-None values.
    Never mutates the lead dict.

    Used for legacy single-instruction mode and for "tell me everything"
    type requests where full context is appropriate.
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
            if isinstance(value, list) and len(value) == 0:
                continue
            if isinstance(value, dict) and len(value) == 0:
                continue
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
        "ollama": "qwen2.5-coder:7b",
    }
    return os.getenv("MATRIX_MODEL_NAME", defaults.get(provider, "gpt-4o"))


def _call_openai(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Call OpenAI API."""
    import time

    import httpx

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = _get_model_name()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    # Bounded connect/overall timeouts. Only transient transport failures
    # (connect timeout, reset, stalled connection) are retried, with short
    # capped backoff; deterministic HTTP errors are never retried.
    timeout = httpx.Timeout(120.0, connect=10.0)
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_completion_tokens": 4096,
                },
                timeout=timeout,
            )
            break
        except httpx.TransportError:
            if attempt == max_attempts:
                raise
            time.sleep(min(2 ** (attempt - 1), 4))

    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_anthropic(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Call Anthropic API."""
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    model = _get_model_name()

    messages: list[dict[str, Any]] = []
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

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
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.7,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]


def _call_openrouter(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Call OpenRouter API."""
    import httpx

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    model = _get_model_name()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_ollama(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Call a local Ollama instance."""
    import httpx

    base_url = os.getenv("MATRIX_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = _get_model_name()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = httpx.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4096,
            },
        },
        timeout=300.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"]


def _call_passthrough(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """
    Fallback when no LLM provider is configured.
    Returns a clean user-facing message — never dumps profile context.
    """
    return (
        "Matrix AI is currently unavailable. "
        "Please check the local AI service configuration.\n\n"
        "Set MATRIX_LLM_PROVIDER in your .env file. "
        "Supported providers: openai, anthropic, openrouter, ollama, passthrough"
    )


_PROVIDERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "openrouter": _call_openrouter,
    "ollama": _call_ollama,
    "passthrough": _call_passthrough,
}


def generate_with_llm(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """
    Route to the configured LLM provider and return the generated text.
    Falls back to passthrough if the provider is not recognised.
    """
    provider = _get_provider()
    fn = _PROVIDERS.get(provider, _call_passthrough)

    try:
        return fn(system_prompt, user_message, history=history)
    except Exception as exc:
        logger.warning("LLM provider '%s' failed: %s", provider, exc)
        return (
            "Matrix AI is currently unavailable. "
            f"The {provider} provider returned an error. "
            "Please check your local AI service and MATRIX_LLM_PROVIDER configuration."
        )


# ---------------------------------------------------------------------------
# Matrix generation — conversational (main entry point)
# ---------------------------------------------------------------------------

def execute_matrix_chat(
    lead: dict[str, Any],
    messages: list[dict[str, str]],
) -> str:
    """
    Execute a conversational Matrix interaction against a lead profile.

    1. Detects the relevant context from the latest user message.
    2. Builds filtered profile context (only relevant groups).
    3. Formats the conversation history for the LLM.
    4. Calls the configured LLM with system prompt + context + history.
    5. Returns the generated assistant message.

    The lead dict is NEVER mutated.
    """
    if not messages:
        return ""

    latest_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            latest_user_msg = msg.get("content", "")
            break

    profile_context = build_filtered_context(lead, latest_user_msg)

    formatted_history: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            formatted_history.append({"role": "assistant", "content": content})
        elif role == "user":
            formatted_history.append({"role": "user", "content": content})

    if formatted_history and formatted_history[-1].get("role") == "user":
        last_user = formatted_history.pop()
        context_user_msg = (
            f"{profile_context}\n\n"
            f"--- USER MESSAGE ---\n"
            f"{last_user['content']}"
        )
    else:
        context_user_msg = (
            f"{profile_context}\n\n"
            f"--- USER MESSAGE ---\n"
            f"{latest_user_msg}"
        )

    return generate_with_llm(
        MATRIX_SYSTEM_PROMPT,
        context_user_msg,
        history=formatted_history if formatted_history else None,
    )


# ---------------------------------------------------------------------------
# Matrix generation — legacy single-instruction mode
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
    "build_filtered_context",
    "execute_matrix_chat",
    "execute_matrix_instruction",
    "store_output",
    "fetch_outputs",
    "fetch_output_by_version",
    "get_next_version",
    "save_draft",
    "save_final",
    "MATRIX_SYSTEM_PROMPT",
]
