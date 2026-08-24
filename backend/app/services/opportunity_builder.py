"""
PERMITSIGNAL OPPORTUNITY BUILDER
================================

Production service that combines the outputs of:

    Application Extractor
    Friction Analyzer
    Applicant Enrichment
    Project Date Extractor

into one canonical PermitSignal opportunity record.

This module deliberately has no database, HTTP, n8n, or AI dependency.
It is the deterministic intelligence layer that should sit immediately
before persistence and workflow delivery.

Canonical flow:

    government document
          |
          v
    application
          |
          +---- friction analysis
          |
          +---- applicant enrichment
          |
          +---- project dates
          |
          v
    Opportunity
          |
          v
    Supabase / FastAPI / n8n

The builder is intentionally defensive. Existing upstream dictionaries may
use slightly different field names, so normalization happens here rather
than forcing every upstream service to be rewritten at once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional
import re


# ============================================================================
# CONSTANTS
# ============================================================================

PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
PRIORITY_ARCHIVED = "ARCHIVED"

URGENCY_URGENT = "URGENT"
URGENCY_SOON = "SOON"
URGENCY_UPCOMING = "UPCOMING"
URGENCY_HISTORICAL = "HISTORICAL"
URGENCY_UNKNOWN = "UNKNOWN"

DEFAULT_HIGH_FRICTION = 70
DEFAULT_MEDIUM_FRICTION = 20

# These are deliberately broad. The friction analyzer remains the authority
# for the actual friction score; this list is used only when a score is absent
# and signals are available.
CRITICAL_SIGNALS = {
    "denied",
    "recommended_denial",
    "staff_concern",
    "appeal",
}

HIGH_VALUE_TYPES = {
    "zone map amendment",
    "rezone",
    "rezoning",
    "concept plan",
    "project plan",
    "site plan",
    "conditional use",
    "conditional use permit",
    "variance",
    "development agreement",
    "subdivision",
    "special exception",
    "ordinance text amendment",
}


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class Opportunity:
    # Identity
    opportunity_id: Optional[str] = None
    application_number: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    applicant_phone: Optional[str] = None

    # Project
    application_type: Optional[str] = None
    project_address: Optional[str] = None
    neighborhood: Optional[str] = None
    description: Optional[str] = None

    # Full property address intelligence (see application_extractor.
    # extract_property_address() / extract_staff_report_address()).
    # project_address keeps its historical street-level contract;
    # these carry the most complete evidence-backed form plus its
    # components and provenance. Components absent from the source
    # stay None -- never fabricated.
    property_address_full: Optional[str] = None
    property_address_components: Optional[dict[str, Any]] = None
    property_address_completeness: Optional[str] = None
    property_address_source: Optional[str] = None
    property_address_confidence: Optional[str] = None
    property_address_evidence: Optional[str] = None

    # Property (parcel/zoning/area -- populated only when the source
    # document explicitly labels them; see application_extractor.
    # extract_property_details()).
    parcel_number: Optional[str] = None
    acreage: Optional[str] = None
    zoning: Optional[str] = None

    # Property Owner / Principal -- the primary commercially relevant
    # party, distinct from the Applicant of Record/Agent below. Populated
    # only when the source document explicitly labels ownership (e.g. a
    # "Property Owner" / "Owner Contact" routing table). Never inferred
    # from the applicant. See DEVELOPMENT_RULES.md / CLAUDE.md section 6.
    owner_name: Optional[str] = None
    owner_entity: Optional[str] = None
    owner_type: Optional[str] = None
    owner_contact_name: Optional[str] = None
    owner_contact_email: Optional[str] = None
    owner_contact_phone: Optional[str] = None
    owner_website: Optional[str] = None
    owner_source: Optional[str] = None
    owner_confidence: Optional[str] = None

    # Applicant of Record / Agent -- the entity submitting on the owner's
    # behalf (e.g. a design firm), distinct from applicant_name/email/phone
    # above, which remain the person the government record names as
    # "requesting" the application. Only populated when the source
    # document explicitly labels an applicant-of-record separate from that
    # requesting individual.
    applicant_entity: Optional[str] = None
    applicant_contact_name: Optional[str] = None
    applicant_contact_email: Optional[str] = None
    applicant_contact_phone: Optional[str] = None
    applicant_source: Optional[str] = None
    applicant_confidence: Optional[str] = None

    # Engineer / Architect / other licensed professionals. Each entry:
    # {party_name, party_role, party_company, party_contact_email,
    #  party_contact_phone, party_source, party_confidence}.
    parties: list[dict[str, Any]] = field(default_factory=list)

    # Government contact
    staff_contact: Optional[str] = None
    staff_email: Optional[str] = None
    staff_phone: Optional[str] = None

    # Friction
    friction_score: int = 0
    friction_signals: list[str] = field(default_factory=list)
    friction_events: list[dict[str, Any]] = field(default_factory=list)
    historical_evidence: list[dict[str, Any]] = field(default_factory=list)

    # Project timing
    next_project_date: Optional[str] = None
    next_project_event: Optional[str] = None
    next_project_time: Optional[str] = None
    has_future_opportunity: bool = False
    days_until_event: Optional[int] = None
    urgency: str = URGENCY_UNKNOWN

    # Lead qualification
    priority: str = PRIORITY_ARCHIVED
    priority_score: int = 0
    is_actionable: bool = False
    opportunity_reason: Optional[str] = None

    # Provenance
    source: Optional[str] = None
    source_url: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None

    # Metadata
    created_at: Optional[str] = None
    builder_version: str = "1.0.0"

    # Contact intelligence (populated by applicant_identity /
    # applicant_enrichment during pipeline stage 6). Declared here with
    # explicit None/False defaults so every opportunity carries the full
    # schema even when no evidence exists yet -- see DATA_MODEL.md section
    # 15 (Null Semantics). NOTE: enrichment_status is deliberately NOT a
    # field here -- pipeline_orchestrator._enrich_applicants() relies on
    # dict.setdefault("enrichment_status", "disabled") to report the
    # disabled state, and pre-seeding that key would silently defeat it.
    normalized_applicant_name: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_domain: Optional[str] = None

    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    email_source: Optional[str] = None
    phone_source: Optional[str] = None
    company_source: Optional[str] = None
    contact_source: Optional[str] = None
    email_confidence: Optional[Any] = None
    phone_confidence: Optional[Any] = None
    contact_confidence: Optional[Any] = None
    contact_is_public: Optional[bool] = None
    contact_is_verified: Optional[bool] = None

    identity_status: Optional[str] = None
    enrichment_method: Optional[str] = None

    # Lead intelligence (see qualify_lead()). Additive classification only
    # -- never used as a sort key and never overrides priority/priority_score.
    lead_status: str = "NEW"
    is_contactable: bool = False

    # Approval-Action Intelligence (Phase 3, populated by
    # backend.app.services.approval_action_intelligence during pipeline
    # stage 6, after applicant/owner enrichment). Declared here with
    # explicit None defaults for the same reason as the contact-intelligence
    # fields above -- every opportunity carries the full schema even when no
    # evidence exists yet. approval_basis distinguishes confirmed_requirement
    # / evidence_backed_recommendation / inferred_next_step / unknown; never
    # presents an inferred action as a confirmed government requirement.
    approval_status: Optional[str] = None
    approval_action: Optional[str] = None
    approval_action_type: Optional[str] = None
    approval_confidence: Optional[str] = None
    approval_basis: Optional[str] = None
    approval_relevant_date: Optional[str] = None
    approval_source: Optional[str] = None
    approval_source_type: Optional[str] = None
    approval_evidence: Optional[str] = None
    approval_reason: Optional[str] = None

    # Commercial Lead Intelligence (Phase 6, populated by
    # backend.app.services.commercial_lead_intelligence during pipeline
    # stage 6, after lead qualification). Declared here with explicit None
    # defaults for the same reason as the approval-action fields above --
    # every opportunity carries the full schema even when no evidence
    # exists yet. This layer never fabricates a decision-maker, contact, or
    # business reason -- it only re-labels lead_status/is_contactable and
    # approval_action, which are themselves already evidence-backed.
    contactability_level: Optional[str] = None
    commercial_readiness: Optional[str] = None
    recommended_commercial_action: Optional[str] = None
    commercial_action_reason: Optional[str] = None

    # Outreach / Commercial Lifecycle (Phase 8, populated by
    # backend.app.services.outreach_intelligence after commercial lead
    # intelligence). outreach_status also serves as the commercial/revenue
    # status (see that module's docstring): READY_FOR_OUTREACH is the point
    # a qualified lead becomes sellable; OPPORTUNITY/WON/LOST track the
    # resulting deal outcome -- no separate monetization field is
    # introduced. outreach_contact_type/outreach_contact_reason only
    # record WHICH already-computed party (owner/applicant/
    # applicant_of_record/company/none) is the appropriate outreach target
    # and why -- they never duplicate the underlying contact fields
    # themselves.
    outreach_status: str = "NEW"
    outreach_qualification_status: Optional[str] = None
    outreach_channel: Optional[str] = None
    outreach_contact_type: Optional[str] = None
    outreach_contact_reason: Optional[str] = None
    outreach_message_subject: Optional[str] = None
    outreach_message_body: Optional[str] = None
    follow_up_required: bool = False
    follow_up_reason: Optional[str] = None
    last_outreach_at: Optional[str] = None
    outreach_events: list[dict[str, Any]] = field(default_factory=list)

    # Economic Intelligence (Phase 9, populated by
    # backend.app.services.economic_intelligence after approval-action
    # intelligence). Declared here with explicit None defaults for the same
    # reason as the phase fields above. estimated_value_* is the project's
    # own economic scale (an ESTIMATE unless source_type is
    # disclosed_document_value); public_spend_* is a SEPARATE figure for
    # whether government money is actually expected to be spent -- a
    # private developer's project can have a large estimated_value and
    # public_spend of exactly 0. Never fabricated: absent evidence leaves
    # these fields None/"insufficient_evidence" rather than guessing.
    project_scale_units: Optional[int] = None
    project_scale_type: Optional[str] = None
    project_scale_basis: Optional[str] = None

    estimated_value_low: Optional[float] = None
    estimated_value_high: Optional[float] = None
    estimated_value_mid: Optional[float] = None
    estimated_value_currency: str = "USD"
    estimated_value_confidence: Optional[str] = None
    estimated_value_source_type: Optional[str] = None
    estimated_value_basis: Optional[str] = None

    public_funding_status: Optional[str] = None
    public_funding_confidence: Optional[str] = None
    public_funding_basis: Optional[str] = None

    public_spend_low: Optional[float] = None
    public_spend_high: Optional[float] = None
    public_spend_mid: Optional[float] = None
    public_spend_confidence: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# BASIC NORMALIZATION
# ============================================================================

def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def _int(value: Any, default: int = 0) -> int:
    if value is None:
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }

    return bool(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    if isinstance(value, str):
        if not value.strip():
            return []

        return [
            part.strip()
            for part in re.split(r"[,;|]", value)
            if part.strip()
        ]

    return [value]


def _clean_signal(value: Any) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip().lower()

    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_]+", "", value)

    return value or None


def normalize_signals(*values: Any) -> list[str]:
    result: list[str] = []

    for value in values:
        for item in _list(value):
            signal = _clean_signal(item)

            if signal and signal not in result:
                result.append(signal)

    return result


# ============================================================================
# DATE HELPERS
# ============================================================================

def _parse_iso_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()

    if not text:
        return None

    # ISO date first.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    # Common human-readable forms.
    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def calculate_days_until(
    project_date: Optional[str],
    reference_date: Optional[date] = None,
) -> Optional[int]:
    parsed = _parse_iso_date(project_date)

    if parsed is None:
        return None

    reference_date = reference_date or date.today()

    return (parsed - reference_date).days


# ============================================================================
# URGENCY
# ============================================================================

def classify_urgency(
    days_until_event: Optional[int],
    has_future_opportunity: bool,
) -> str:
    if not has_future_opportunity:
        return URGENCY_HISTORICAL

    if days_until_event is None:
        return URGENCY_UNKNOWN

    if days_until_event < 0:
        return URGENCY_HISTORICAL

    if days_until_event <= 7:
        return URGENCY_URGENT

    if days_until_event <= 30:
        return URGENCY_SOON

    return URGENCY_UPCOMING


# ============================================================================
# ACTIONABILITY
# ============================================================================

def normalize_application_type(value: Any) -> Optional[str]:
    text = _text(value)

    if not text:
        return None

    return re.sub(r"\s+", " ", text).strip()


def is_actionable_application(application: Mapping[str, Any]) -> bool:
    application_type = normalize_application_type(
        _first(
            application,
            "application_type",
            "type",
            "record_type",
        )
    )

    if not application_type:
        return False

    normalized = application_type.lower()

    if normalized in HIGH_VALUE_TYPES:
        return True

    # Conservative partial matching for government naming variations.
    keywords = (
        "rezone",
        "zone map",
        "concept",
        "project plan",
        "site plan",
        "variance",
        "subdivision",
        "development",
        "conditional use",
        "special exception",
    )

    return any(keyword in normalized for keyword in keywords)


# ============================================================================
# FRICTION EXTRACTION
# ============================================================================

def extract_friction_data(
    application: Mapping[str, Any],
    friction: Optional[Mapping[str, Any]] = None,
) -> tuple[int, list[str], list[dict[str, Any]]]:
    """
    Normalize friction analyzer output.

    Supported examples:

        {"friction_score": 100, "signals": ["denied"]}

        {"score": 100, "friction_signals": ["denied"]}

        {"events": [...], "signals": [...]}
    """

    friction = friction or {}

    score = _int(
        _first(
            friction,
            "friction_score",
            "score",
            "priority_score",
            default=_first(
                application,
                "friction_score",
                "score",
                default=0,
            ),
        )
    )

    signals = normalize_signals(
        _first(friction, "friction_signals"),
        _first(friction, "signals"),
        _first(application, "friction_signals"),
        _first(application, "signals"),
    )

    events = _list(
        _first(
            friction,
            "friction_events",
            "events",
            "evidence_events",
            "historical_evidence",
            default=_first(
                application,
                "friction_events",
                "events",
                "historical_evidence",
                default=[],
            ),
        )
    )

    normalized_events: list[dict[str, Any]] = []

    for event in events:
        if isinstance(event, Mapping):
            normalized_events.append(dict(event))
        else:
            normalized_events.append({"evidence": str(event)})

    return max(0, score), signals, normalized_events


# ============================================================================
# APPLICANT ENRICHMENT EXTRACTION
# ============================================================================

def extract_applicant_data(
    application: Mapping[str, Any],
    enrichment: Optional[Mapping[str, Any]] = None,
) -> dict[str, Optional[str]]:
    enrichment = enrichment or {}

    return {
        "applicant_name": _text(
            _first(
                enrichment,
                "applicant_name",
                "name",
                default=_first(
                    application,
                    "applicant_name",
                    "applicant",
                ),
            )
        ),
        "applicant_email": _text(
            _first(
                enrichment,
                "applicant_email",
                "email",
                "best_email",
                default=_first(
                    application,
                    "applicant_email",
                ),
            )
        ),
        "applicant_phone": _text(
            _first(
                enrichment,
                "applicant_phone",
                "phone",
                "best_phone",
                default=_first(
                    application,
                    "applicant_phone",
                ),
            )
        ),
    }


# ============================================================================
# PROJECT DATA EXTRACTION
# ============================================================================

def extract_project_data(
    application: Mapping[str, Any],
) -> dict[str, Optional[str]]:
    return {
        "application_number": _text(
            _first(
                application,
                "application_number",
                "application_no",
                "application_id",
            )
        ),
        "application_type": normalize_application_type(
            _first(
                application,
                "application_type",
                "type",
            )
        ),
        "project_address": _text(
            _first(
                application,
                "project_address",
                "address",
                "property_address",
            )
        ),
        "neighborhood": _text(
            _first(
                application,
                "neighborhood",
            )
        ),
        "description": _text(
            _first(
                application,
                "description",
                "project_description",
            )
        ),
    }


# ============================================================================
# PROPERTY / OWNER / APPLICANT-OF-RECORD / PARTY EXTRACTION
# ============================================================================
#
# All of these are additive to extract_project_data()/extract_applicant_data()
# above -- they never fabricate a value. When the source application dict
# carries no owner/property/party evidence (the common case for a packet
# that never labels ownership), every field below normalizes to None/[].

def extract_property_extras(
    application: Mapping[str, Any],
) -> dict[str, Optional[str]]:
    return {
        "parcel_number": _text(_first(application, "parcel_number")),
        "acreage": _text(_first(application, "acreage")),
        "zoning": _text(_first(application, "zoning")),
    }


def extract_address_intelligence(
    application: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Most complete evidence-backed property address + provenance,
    additive to project_address above. Never fabricates a missing
    component; see application_extractor for the capture rules.
    """

    components = _first(
        application,
        "property_address_components",
    )

    if not isinstance(components, Mapping):
        components = None

    return {
        "property_address_full": _text(
            _first(application, "property_address_full")
        ),
        "property_address_components": (
            dict(components) if components else None
        ),
        "property_address_completeness": _text(
            _first(application, "property_address_completeness")
        ),
        "property_address_source": _text(
            _first(application, "property_address_source")
        ),
        "property_address_confidence": _text(
            _first(application, "property_address_confidence")
        ),
        "property_address_evidence": _text(
            _first(application, "property_address_evidence")
        ),
    }


def extract_owner_data(
    application: Mapping[str, Any],
) -> dict[str, Optional[str]]:
    return {
        "owner_name": _text(_first(application, "owner_name")),
        "owner_entity": _text(_first(application, "owner_entity")),
        "owner_type": _text(_first(application, "owner_type")),
        "owner_contact_name": _text(_first(application, "owner_contact_name")),
        "owner_contact_email": _text(_first(application, "owner_contact_email")),
        "owner_contact_phone": _text(_first(application, "owner_contact_phone")),
        "owner_website": _text(_first(application, "owner_website")),
        "owner_source": _text(_first(application, "owner_source")),
        "owner_confidence": _text(_first(application, "owner_confidence")),
    }


def extract_applicant_of_record_data(
    application: Mapping[str, Any],
) -> dict[str, Optional[str]]:
    return {
        "applicant_entity": _text(_first(application, "applicant_entity")),
        "applicant_contact_name": _text(_first(application, "applicant_contact_name")),
        "applicant_contact_email": _text(_first(application, "applicant_contact_email")),
        "applicant_contact_phone": _text(_first(application, "applicant_contact_phone")),
        "applicant_source": _text(_first(application, "applicant_source")),
        "applicant_confidence": _text(_first(application, "applicant_confidence")),
    }


def extract_parties_data(
    application: Mapping[str, Any],
) -> list[dict[str, Any]]:
    parties = _first(application, "parties", default=[])

    if not isinstance(parties, list):
        return []

    return [dict(party) for party in parties if isinstance(party, Mapping)]


# ============================================================================
# DATE DATA EXTRACTION
# ============================================================================

def extract_date_data(
    application: Mapping[str, Any],
    dates: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    dates = dates or {}

    next_date = _text(
        _first(
            dates,
            "next_project_date",
            "next_date",
            default=_first(
                application,
                "next_project_date",
                "next_date",
            ),
        )
    )

    next_event = _text(
        _first(
            dates,
            "next_project_event",
            "next_event",
            default=_first(
                application,
                "next_project_event",
                "next_event",
            ),
        )
    )

    next_time = _text(
        _first(
            dates,
            "next_project_time",
            "next_time",
            default=_first(
                application,
                "next_project_time",
                "next_time",
            ),
        )
    )

    future = _bool(
        _first(
            dates,
            "has_future_opportunity",
            "has_future_event",
            default=_first(
                application,
                "has_future_opportunity",
                "has_future_event",
            ),
        )
    )

    future_dates = _list(
        _first(
            dates,
            "future_project_dates",
            "future_dates",
            default=_first(
                application,
                "future_project_dates",
                "future_dates",
                default=[],
            ),
        )
    )

    historical_dates = _list(
        _first(
            dates,
            "historical_project_dates",
            "historical_dates",
            default=_first(
                application,
                "historical_project_dates",
                "historical_dates",
                default=[],
            ),
        )
    )

    return {
        "next_project_date": next_date,
        "next_project_event": next_event,
        "next_project_time": next_time,
        "has_future_opportunity": future,
        "future_project_dates": future_dates,
        "historical_project_dates": historical_dates,
    }


# ============================================================================
# PRIORITY ENGINE
# ============================================================================

def calculate_priority_score(
    friction_score: int,
    has_future_opportunity: bool,
    days_until_event: Optional[int],
    is_actionable: bool,
    signals: Iterable[str],
) -> int:
    """
    Deterministic lead score.

    This is NOT the friction score.

    friction_score:
        measures approval/history friction.

    priority_score:
        measures whether PermitSignal should surface the lead now.
    """

    score = 0

    # Friction contribution.
    score += min(max(friction_score, 0), 100)

    # Future opportunity is mandatory for a live opportunity.
    if has_future_opportunity:
        score += 25

    # Actionable development type.
    if is_actionable:
        score += 15

    # Urgency.
    if days_until_event is not None and has_future_opportunity:
        if days_until_event <= 7:
            score += 35
        elif days_until_event <= 30:
            score += 20
        elif days_until_event <= 90:
            score += 10

    signal_set = set(signals)

    if signal_set.intersection(CRITICAL_SIGNALS):
        score += 20

    return min(score, 250)


def classify_priority(
    friction_score: int,
    has_future_opportunity: bool,
    days_until_event: Optional[int],
    is_actionable: bool,
    signals: Iterable[str],
) -> str:
    """
    High:
        live opportunity + serious friction/actionability/urgency.

    Medium:
        live opportunity but weaker evidence.

    Low:
        live opportunity with little evidence.

    Archived:
        no future event.
    """

    if not has_future_opportunity:
        return PRIORITY_ARCHIVED

    signal_set = set(signals)

    if (
        friction_score >= DEFAULT_HIGH_FRICTION
        and is_actionable
    ):
        return PRIORITY_HIGH

    if (
        signal_set.intersection(CRITICAL_SIGNALS)
        and is_actionable
    ):
        return PRIORITY_HIGH

    if (
        days_until_event is not None
        and days_until_event <= 7
        and (
            friction_score >= DEFAULT_MEDIUM_FRICTION
            or is_actionable
        )
    ):
        return PRIORITY_HIGH

    if (
        friction_score >= DEFAULT_MEDIUM_FRICTION
        or is_actionable
        or (
            days_until_event is not None
            and days_until_event <= 30
        )
    ):
        return PRIORITY_MEDIUM

    return PRIORITY_LOW


# ============================================================================
# OPPORTUNITY REASON
# ============================================================================

def build_opportunity_reason(
    applicant_name: Optional[str],
    application_type: Optional[str],
    friction_score: int,
    signals: list[str],
    next_project_date: Optional[str],
    next_project_event: Optional[str],
    next_project_time: Optional[str],
    priority: str,
    days_until_event: Optional[int],
) -> str:
    pieces: list[str] = []

    if applicant_name:
        pieces.append(applicant_name)

    if application_type:
        pieces.append(application_type)

    if friction_score > 0:
        pieces.append(
            f"friction score {friction_score}"
        )

    if signals:
        pieces.append(
            "signals: " + ", ".join(signals)
        )

    if next_project_date:
        event = next_project_event or "future event"

        timing = (
            f" in {days_until_event} days"
            if days_until_event is not None
            else ""
        )

        time_part = (
            f" at {next_project_time}"
            if next_project_time
            else ""
        )

        pieces.append(
            f"next {event} on {next_project_date}"
            f"{time_part}{timing}"
        )

    if not pieces:
        pieces.append(
            "No actionable project evidence detected."
        )

    prefix = f"{priority} opportunity: "

    return prefix + "; ".join(pieces) + "."


# ============================================================================
# OPPORTUNITY ID
# ============================================================================

def build_opportunity_id(
    application_number: Optional[str],
    project_address: Optional[str],
    applicant_name: Optional[str],
) -> Optional[str]:
    source = (
        application_number
        or project_address
        or applicant_name
    )

    if not source:
        return None

    cleaned = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        source.strip(),
    ).strip("-")

    return cleaned.lower() or None


# ============================================================================
# MAIN BUILDER
# ============================================================================

def build_opportunity(
    application: Mapping[str, Any],
    friction: Optional[Mapping[str, Any]] = None,
    enrichment: Optional[Mapping[str, Any]] = None,
    dates: Optional[Mapping[str, Any]] = None,
    reference_date: Optional[date] = None,
    source: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build the canonical PermitSignal opportunity.

    All inputs are optional except application.

    Example:

        opportunity = build_opportunity(
            application,
            friction=friction_result,
            enrichment=applicant_result,
            dates=date_result,
            reference_date=date(2026, 8, 1),
            source={
                "source": "Provo Planning Commission",
                "source_url": "...",
                "municipality": "Provo",
                "state": "Utah",
            },
        )
    """

    reference_date = reference_date or date.today()

    project = extract_project_data(application)

    applicant = extract_applicant_data(
        application,
        enrichment,
    )

    property_extras = extract_property_extras(application)
    address_intelligence = extract_address_intelligence(application)
    owner = extract_owner_data(application)
    applicant_of_record = extract_applicant_of_record_data(application)
    parties = extract_parties_data(application)

    friction_score, signals, events = extract_friction_data(
        application,
        friction,
    )

    date_data = extract_date_data(
        application,
        dates,
    )

    next_project_date = date_data[
        "next_project_date"
    ]

    has_future = date_data[
        "has_future_opportunity"
    ]

    # If a next date exists and is genuinely ahead of the reference date,
    # treat it as a future opportunity even when an upstream service omitted
    # the boolean.
    parsed_next_date = _parse_iso_date(
        next_project_date
    )

    if parsed_next_date is not None:
        has_future = parsed_next_date > reference_date

    days_until_event = calculate_days_until(
        next_project_date,
        reference_date,
    )

    # Never allow a historical date to be treated as a live opportunity.
    if (
        days_until_event is not None
        and days_until_event < 0
    ):
        has_future = False

    is_actionable = is_actionable_application(
        application
    )

    urgency = classify_urgency(
        days_until_event,
        has_future,
    )

    priority_score = calculate_priority_score(
        friction_score=friction_score,
        has_future_opportunity=has_future,
        days_until_event=days_until_event,
        is_actionable=is_actionable,
        signals=signals,
    )

    priority = classify_priority(
        friction_score=friction_score,
        has_future_opportunity=has_future,
        days_until_event=days_until_event,
        is_actionable=is_actionable,
        signals=signals,
    )

    source = source or {}

    opportunity_id = build_opportunity_id(
        project["application_number"],
        project["project_address"],
        applicant["applicant_name"],
    )

    reason = build_opportunity_reason(
        applicant_name=applicant["applicant_name"],
        application_type=project["application_type"],
        friction_score=friction_score,
        signals=signals,
        next_project_date=next_project_date
        if has_future
        else None,
        next_project_event=date_data[
            "next_project_event"
        ]
        if has_future
        else None,
        next_project_time=date_data[
            "next_project_time"
        ]
        if has_future
        else None,
        priority=priority,
        days_until_event=days_until_event
        if has_future
        else None,
    )

    opportunity = Opportunity(
        opportunity_id=opportunity_id,
        application_number=project[
            "application_number"
        ],
        applicant_name=applicant[
            "applicant_name"
        ],
        applicant_email=applicant[
            "applicant_email"
        ],
        applicant_phone=applicant[
            "applicant_phone"
        ],
        application_type=project[
            "application_type"
        ],
        project_address=project[
            "project_address"
        ],
        neighborhood=project[
            "neighborhood"
        ],
        description=project[
            "description"
        ],
        **address_intelligence,
        parcel_number=property_extras["parcel_number"],
        acreage=property_extras["acreage"],
        zoning=property_extras["zoning"],
        owner_name=owner["owner_name"],
        owner_entity=owner["owner_entity"],
        owner_type=owner["owner_type"],
        owner_contact_name=owner["owner_contact_name"],
        owner_contact_email=owner["owner_contact_email"],
        owner_contact_phone=owner["owner_contact_phone"],
        owner_website=owner["owner_website"],
        owner_source=owner["owner_source"],
        owner_confidence=owner["owner_confidence"],
        applicant_entity=applicant_of_record["applicant_entity"],
        applicant_contact_name=applicant_of_record["applicant_contact_name"],
        applicant_contact_email=applicant_of_record["applicant_contact_email"],
        applicant_contact_phone=applicant_of_record["applicant_contact_phone"],
        applicant_source=applicant_of_record["applicant_source"],
        applicant_confidence=applicant_of_record["applicant_confidence"],
        parties=parties,
        staff_contact=_text(
            _first(
                application,
                "staff_contact",
                "staff_name",
            )
        ),
        staff_email=_text(
            _first(
                application,
                "staff_email",
            )
        ),
        staff_phone=_text(
            _first(
                application,
                "staff_phone",
            )
        ),
        friction_score=friction_score,
        friction_signals=signals,
        friction_events=events,
        historical_evidence=events,
        next_project_date=(
            next_project_date
            if has_future
            else None
        ),
        next_project_event=(
            date_data["next_project_event"]
            if has_future
            else None
        ),
        next_project_time=(
            date_data["next_project_time"]
            if has_future
            else None
        ),
        has_future_opportunity=has_future,
        days_until_event=(
            days_until_event
            if has_future
            else None
        ),
        urgency=urgency,
        priority=priority,
        priority_score=priority_score,
        is_actionable=is_actionable,
        opportunity_reason=reason,
        source=_text(
            _first(
                source,
                "source",
                default=_first(
                    application,
                    "source",
                ),
            )
        ),
        source_url=_text(
            _first(
                source,
                "source_url",
                "url",
                default=_first(
                    application,
                    "source_url",
                    "url",
                ),
            )
        ),
        municipality=_text(
            _first(
                source,
                "municipality",
                default=_first(
                    application,
                    "municipality",
                ),
            )
        ),
        state=_text(
            _first(
                source,
                "state",
                default=_first(
                    application,
                    "state",
                ),
            )
        ),
        created_at=datetime.utcnow().isoformat(
            timespec="seconds"
        ) + "Z",
    )

    return opportunity.to_dict()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def build_opportunities(
    applications: Iterable[Mapping[str, Any]],
    friction_by_application: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
    enrichment_by_application: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
    dates_by_application: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
    reference_date: Optional[date] = None,
    source: Optional[Mapping[str, Any]] = None,
) -> list[dict[str, Any]]:

    friction_by_application = (
        friction_by_application or {}
    )
    enrichment_by_application = (
        enrichment_by_application or {}
    )
    dates_by_application = (
        dates_by_application or {}
    )

    results: list[dict[str, Any]] = []

    for application in applications:
        application_number = _text(
            _first(
                application,
                "application_number",
                "application_no",
                "application_id",
            )
        )

        friction = (
            friction_by_application.get(
                application_number,
                {},
            )
        )

        enrichment = (
            enrichment_by_application.get(
                application_number,
                {},
            )
        )

        dates = (
            dates_by_application.get(
                application_number,
                {},
            )
        )

        results.append(
            build_opportunity(
                application=application,
                friction=friction,
                enrichment=enrichment,
                dates=dates,
                reference_date=reference_date,
                source=source,
            )
        )

    return results


def sort_opportunities(
    opportunities: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Sort the lead queue:

        1. HIGH
        2. MEDIUM
        3. LOW
        4. ARCHIVED

    Within a priority, highest priority_score comes first.
    """

    priority_rank = {
        PRIORITY_HIGH: 0,
        PRIORITY_MEDIUM: 1,
        PRIORITY_LOW: 2,
        PRIORITY_ARCHIVED: 3,
    }

    return sorted(
        (
            dict(opportunity)
            for opportunity in opportunities
        ),
        key=lambda item: (
            priority_rank.get(
                str(
                    item.get("priority", "")
                ).upper(),
                99,
            ),
            -_int(
                item.get(
                    "priority_score",
                    0,
                )
            ),
            item.get(
                "next_project_date"
            ) or "9999-12-31",
        ),
    )


def high_priority_opportunities(
    opportunities: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in sort_opportunities(
            opportunities
        )
        if item.get("priority") == PRIORITY_HIGH
    ]


def validate_opportunity(
    opportunity: Mapping[str, Any],
) -> list[str]:
    """
    Return validation errors.

    An empty list means the record is structurally valid.
    """

    errors: list[str] = []

    required_fields = (
        "application_number",
        "applicant_name",
        "application_type",
    )

    for field_name in required_fields:
        if not opportunity.get(field_name):
            errors.append(
                f"missing {field_name}"
            )

    friction_score = opportunity.get(
        "friction_score"
    )

    if friction_score is not None:
        try:
            numeric_score = int(friction_score)

            if numeric_score < 0:
                errors.append(
                    "friction_score cannot be negative"
                )

        except (TypeError, ValueError):
            errors.append(
                "friction_score must be numeric"
            )

    if opportunity.get(
        "has_future_opportunity"
    ):
        if not opportunity.get(
            "next_project_date"
        ):
            errors.append(
                "future opportunity requires next_project_date"
            )

        if not opportunity.get(
            "next_project_event"
        ):
            errors.append(
                "future opportunity requires next_project_event"
            )

    return errors


# ============================================================================
# LEAD INTELLIGENCE
# ============================================================================
#
# An Opportunity says "something commercially interesting is happening."
# A Lead record says "here is who is associated with it, how we can publicly
# contact them, and whether that evidence is strong enough to act on."
#
# qualify_lead() is purely additive: it never touches application_number,
# applicant_name, friction, project-event, priority, or priority_score. It
# only reads fields the opportunity builder / applicant identity / contact
# enrichment stages already populated (or explicitly left null).

LEAD_STATUS_ARCHIVED = "ARCHIVED"
LEAD_STATUS_NEW = "NEW"
LEAD_STATUS_QUALIFIED = "QUALIFIED"
LEAD_STATUS_CONTACTABLE = "CONTACTABLE"
LEAD_STATUS_NO_CONTACT = "NO_CONTACT"

_GENERIC_CONTACT_PREFIXES = {
    "info",
    "contact",
    "hello",
    "office",
    "admin",
    "sales",
    "support",
    "leasing",
    "development",
    "planning",
    "projects",
    "inquiries",
    "inquiry",
    "marketing",
    "noreply",
    "no-reply",
    "webmaster",
}


def _party_contact(opportunity: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    The first (email, phone) pair from a distinct project party (Engineer/
    Architect/Contractor/Attorney/Developer/Representative/other
    participant, see application_extractor.extract_parties()/
    extract_staff_report_identity() and applicant_enrichment.
    discovered_parties) that carries usable contact evidence. The
    commercial lead behind a project is not always the owner or applicant
    -- a contactable party in any of these roles is real contact evidence
    too.
    """
    parties = opportunity.get("parties")

    if not isinstance(parties, list):
        return None, None

    for party in parties:
        if not isinstance(party, Mapping):
            continue

        email = _text(party.get("party_contact_email"))
        phone = _text(party.get("party_contact_phone"))

        if email or phone:
            return email, phone

    return None, None


def _contact_tier(opportunity: Mapping[str, Any]) -> str:
    """
    Classify the strength of the public contact evidence already present
    on a lead record. This never invents contact data -- it only reads
    fields the identity/enrichment stages already populated.

    Returns one of: "none", "weak", "strong".

    - A named professional email -> "strong".
    - A generic company mailbox (info@, contact@, ...) -> "weak".
    - A phone number with no email -> "strong" (a government-record
      applicant phone is explicitly treated as contactable per
      CONTACTABLE LOGIC in the project instructions).
    - Nothing at all -> "none".

    Checks the applicant/generic contact fields first, then the property
    owner and applicant-of-record's own contact fields, then any other
    distinct project party's contact fields -- a lead is not "no contact"
    just because the specific field checked first is empty.
    """
    email = (
        _text(opportunity.get("applicant_email"))
        or _text(opportunity.get("contact_email"))
        or _text(opportunity.get("owner_contact_email"))
        or _text(opportunity.get("applicant_contact_email"))
    )
    phone = (
        _text(opportunity.get("applicant_phone"))
        or _text(opportunity.get("contact_phone"))
        or _text(opportunity.get("owner_contact_phone"))
        or _text(opportunity.get("applicant_contact_phone"))
    )

    if not email and not phone:
        party_email, party_phone = _party_contact(opportunity)
        email, phone = party_email, party_phone

    if not email and not phone:
        return "none"

    if email:
        local = email.split("@", 1)[0].lower() if "@" in email else email.lower()

        if local in _GENERIC_CONTACT_PREFIXES:
            return "weak"

        return "strong"

    return "strong"


# Public aliases for backend.app.services.commercial_lead_intelligence
# (Phase 6), which classifies contactability at a finer grain (person vs.
# company vs. public-business contact) than the "none"/"weak"/"strong"
# tiers here but must never re-derive that classification from the raw
# contact fields a second time -- see DEVELOPMENT_RULES.md section 5 (Do
# Not Duplicate Business Logic).
contact_tier = _contact_tier
GENERIC_CONTACT_PREFIXES = _GENERIC_CONTACT_PREFIXES


def is_contactable_lead(opportunity: Mapping[str, Any]) -> bool:
    """
    True only when legitimate public contact evidence exists. Never
    fabricates a "yes" -- an opportunity with no email/phone is never
    contactable.
    """
    return _contact_tier(opportunity) != "none"


def classify_lead_status(opportunity: Mapping[str, Any]) -> str:
    """
    Deterministic lead status.

    Reuses the existing priority/actionability/future-event signals the
    opportunity builder already computed. This does NOT introduce a new
    scoring model and does NOT replace priority/priority_score.

    ARCHIVED     -- no live future project event.
    NEW          -- a live future event exists, but the opportunity has not
                    earned qualified-lead status (LOW priority or not
                    actionable).
    NO_CONTACT   -- qualifies as a real lead, but no public contact
                    evidence exists yet.
    QUALIFIED    -- qualifies as a real lead and a contact exists, but it is
                    a generic mailbox (lower specificity).
    CONTACTABLE  -- qualifies as a real lead and a named professional email
                    or a phone number exists (highest specificity).
    """
    if not opportunity.get("has_future_opportunity"):
        return LEAD_STATUS_ARCHIVED

    priority = str(opportunity.get("priority") or "LOW").upper()
    is_actionable = bool(opportunity.get("is_actionable"))
    meets_bar = priority in (PRIORITY_HIGH, PRIORITY_MEDIUM) and is_actionable

    if not meets_bar:
        return LEAD_STATUS_NEW

    tier = _contact_tier(opportunity)

    if tier == "none":
        return LEAD_STATUS_NO_CONTACT

    if tier == "weak":
        return LEAD_STATUS_QUALIFIED

    return LEAD_STATUS_CONTACTABLE


def qualify_lead(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """
    Attach lead-qualification metadata to an already-built, already
    identity/contact-enriched canonical opportunity.

    This is additive: every existing field on the opportunity is preserved
    unchanged; only "lead_status" and "is_contactable" are added/overwritten.
    """
    result = dict(opportunity)
    result["is_contactable"] = is_contactable_lead(result)
    result["lead_status"] = classify_lead_status(result)
    return result


__all__ = [
    "Opportunity",
    "build_opportunity",
    "build_opportunities",
    "sort_opportunities",
    "high_priority_opportunities",
    "validate_opportunity",
    "calculate_days_until",
    "classify_urgency",
    "calculate_priority_score",
    "classify_priority",
    "is_actionable_application",
    "extract_friction_data",
    "extract_applicant_data",
    "extract_project_data",
    "extract_date_data",
    "normalize_signals",
    "LEAD_STATUS_ARCHIVED",
    "LEAD_STATUS_NEW",
    "LEAD_STATUS_QUALIFIED",
    "LEAD_STATUS_CONTACTABLE",
    "LEAD_STATUS_NO_CONTACT",
    "is_contactable_lead",
    "classify_lead_status",
    "qualify_lead",
    "contact_tier",
    "GENERIC_CONTACT_PREFIXES",
]