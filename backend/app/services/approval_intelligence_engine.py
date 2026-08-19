"""
PermitSignal Approval Intelligence Engine
==========================================

Purpose
-------
Turn every piece of evidence the pipeline has already computed -- friction
signals/events, project dates, application records, applicant/owner/contact
data -- into a single, comprehensive approval-intelligence report that
answers:

    What is the current approval status?
    What has historically gone wrong?
    What will block approval?
    What must the applicant do?
    Who is involved?
    What is the decision path?
    What service does this applicant need?
    What is the internal strategy?

Design principle
-----------------
This module performs NO new text extraction, NO web searches, NO AI
inference. It only reads fields earlier pipeline stages already computed,
each of which carries its own evidence rules. Every claim in the output is
classified as FACT, INFERENCE, RECOMMENDATION, or UNKNOWN, and every
claim traces back to one or more evidence_ids in the unified evidence
registry.

The engine deliberately never outputs:

    - "100% approval" or "guaranteed approval" or "will approve"
    - Fabricated fees, costs, or pricing
    - Fabricated contacts, emails, or phone numbers
    - Fabricated government decisions or outcomes
    - Fabricated zoning requirements

An evidence-backed None is always preferred over fabricated data.

Requirements classification:

    A -- Explicit government requirements (found verbatim in government
         documents: application forms, staff reports, hearing notices).
    B -- Derived/inferred requirements (logical consequences of the
         application type, status, or government process that are not
         stated verbatim but are standard for the jurisdiction).
    C -- PermitSignal recommendations (best-practice actions the applicant
         should take to improve their position; not government-mandated).

Pipeline stage name: APPROVAL_INTELLIGENCE_MODULE

Public API
----------
build_approval_intelligence(lead: dict, reference_date: date) -> dict
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Optional
import re


# ============================================================================
# VOCABULARY
# ============================================================================

REPORT_VERSION = "1.0.0"

# Claim classifications -- every output claim must be one of these.
CLAIM_FACT = "FACT"
CLAIM_INFERENCE = "INFERENCE"
CLAIM_RECOMMENDATION = "RECOMMENDATION"
CLAIM_UNKNOWN = "UNKNOWN"

# Severity levels for blockers and intelligence items.
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# Approval risk levels.
RISK_HIGH = "HIGH"
RISK_MEDIUM = "MEDIUM"
RISK_LOW = "LOW"
RISK_UNKNOWN = "UNKNOWN"

# Approval readiness levels.
READINESS_READY = "READY"
READINESS_PROVISIONAL = "PROVISIONAL"
READINESS_NOT_READY = "NOT_READY"
READINESS_UNKNOWN = "UNKNOWN"

# Service recommendation types.
SERVICE_APPROVAL_STRATEGY = "APPROVAL STRATEGY"
SERVICE_APPROVAL_ASSISTANCE = "APPROVAL ASSISTANCE"
SERVICE_APPROVAL_DIAGNOSTIC = "APPROVAL DIAGNOSTIC"
SERVICE_MONITORING = "MONITORING"

# Evidence source types.
SOURCE_FRICTION = "friction_analysis"
SOURCE_DATE = "project_date_extraction"
SOURCE_APPLICATION = "application_extraction"
SOURCE_ENRICHMENT = "applicant_enrichment"
SOURCE_IDENTITY = "applicant_identity"
SOURCE_GOVERNMENT = "government_record"
SOURCE_APPROVAL = "approval_action_intelligence"

# Denial/friction signal categories.
OBJECTION_PROCEDURAL = "procedural"
OBJECTION_SUBSTANTIVE = "substantive"
OBJECTION_DESIGN = "design"
OBJECTION_SITE = "site"
OBJECTION_ZONING = "zoning"
OBJECTION_ENVIRONMENTAL = "environmental"
OBJECTION_UNKNOWN = "unknown"

# Decision path stages.
PATH_APPLICATION_FILED = "application_filed"
PATH_STAFF_REVIEW = "staff_review"
PATH_PLANNING_COMMISSION = "planning_commission"
PATH_CITY_COUNCIL = "city_council"
PATH_COMPLETED = "completed"

# Friction signals in descending severity order.
DENIAL_SIGNALS = frozenset({
    "denied",
    "recommended_denial",
})

HIGH_FRICTION_SIGNALS = frozenset({
    "denied",
    "recommended_denial",
    "withdrawn",
    "appeal",
    "staff_concern",
    "neighborhood_concern",
    "public_opposition",
})

PROCEDURAL_SIGNALS = frozenset({
    "continued",
    "tabled",
    "deferred",
    "postponed",
})

ADDITIONAL_INFO_SIGNALS = frozenset({
    "additional_information",
    "amended",
    "revised",
})


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class EvidenceRecord:
    """A single, deduplicated piece of evidence in the registry."""

    evidence_id: str
    claim: str
    source_type: str
    source_url: Optional[str] = None
    document_name: Optional[str] = None
    page: Optional[int] = None
    date: Optional[str] = None
    excerpt: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntelligenceItem:
    """A single finding in the intelligence report."""

    title: str
    statement: str
    classification: str
    severity: str
    confidence: str
    evidence_ids: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalIntelligenceReport:
    """The complete approval intelligence report for a single lead."""

    version: str = REPORT_VERSION
    status: str = "complete"
    executive_diagnosis: str = ""
    approval_status: str = "unknown"
    approval_risk: str = RISK_UNKNOWN
    approval_readiness: str = READINESS_UNKNOWN
    denial_history: list[dict[str, Any]] = field(default_factory=list)
    approval_blockers: list[dict[str, Any]] = field(default_factory=list)
    requirements: list[dict[str, Any]] = field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = field(default_factory=list)
    stakeholder_actions: list[dict[str, Any]] = field(default_factory=list)
    decision_path: list[dict[str, Any]] = field(default_factory=list)
    service_recommendation: str = SERVICE_MONITORING
    service_scope: str = ""
    pricing_inputs: dict[str, Any] = field(default_factory=dict)
    client_message: str = ""
    internal_strategy: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    model_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# EVIDENCE REGISTRY
# ============================================================================

class EvidenceRegistry:
    """
    Unified, deduplicated evidence store.

    Every piece of evidence added gets a stable evidence_id. Identical
    (source_type, claim) pairs are deduplicated, keeping the first version
    with the highest confidence.
    """

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._counter: int = 0

    def add(
        self,
        claim: str,
        source_type: str,
        source_url: Optional[str] = None,
        document_name: Optional[str] = None,
        page: Optional[int] = None,
        date: Optional[str] = None,
        excerpt: Optional[str] = None,
        confidence: float = 0.5,
    ) -> str:
        """Add evidence and return its evidence_id."""

        dedup_key = f"{source_type}::{claim}"

        for record in self._records.values():
            if record.source_type == source_type and record.claim == claim:
                if confidence <= record.confidence:
                    return record.evidence_id

        self._counter += 1
        evidence_id = f"E{self._counter:04d}"

        record = EvidenceRecord(
            evidence_id=evidence_id,
            claim=claim,
            source_type=source_type,
            source_url=source_url,
            document_name=document_name,
            page=page,
            date=date,
            excerpt=excerpt,
            confidence=confidence,
        )

        self._records[evidence_id] = record
        return evidence_id

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        return self._records.get(evidence_id)

    def all_records(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def all_dicts(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self._records.values()]

    def ids_for_claims(self, claims: list[str]) -> list[str]:
        claim_set = set(claims)
        return [
            record.evidence_id
            for record in self._records.values()
            if record.claim in claim_set
        ]


# ============================================================================
# NORMALIZATION HELPERS
# ============================================================================

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

    if isinstance(value, (tuple, set)):
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


def _first(
    mapping: Mapping[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _normalize_signals(value: Any) -> list[str]:
    if value is None:
        return []

    raw = _list(value)

    result: list[str] = []

    for item in raw:
        signal = str(item).strip().lower()
        signal = re.sub(r"\s+", "_", signal)
        signal = re.sub(r"[^a-z0-9_]+", "", signal)

        if signal and signal not in result:
            result.append(signal)

    return result


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

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

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


def _days_until(
    target: Optional[str],
    reference: date,
) -> Optional[int]:
    parsed = _parse_iso_date(target)

    if parsed is None:
        return None

    return (parsed - reference).days


# ============================================================================
# EVIDENCE BUILDER -- builds the registry from a lead record
# ============================================================================

def _build_evidence_registry(
    lead: Mapping[str, Any],
) -> EvidenceRegistry:
    """
    Construct a unified evidence registry from every piece of data the
    pipeline has already computed on this lead.
    """

    registry = EvidenceRegistry()

    source_url = _text(
        _first(lead, "source_url", "source", default=None)
    )
    source_name = _text(
        _first(lead, "source", default=None)
    )
    app_number = _text(
        _first(lead, "application_number", default=None)
    )

    # -- Application record evidence --
    applicant_name = _text(_first(lead, "applicant_name", default=None))
    app_type = _text(_first(lead, "application_type", default=None))
    project_address = _text(_first(lead, "project_address", default=None))
    description = _text(_first(lead, "description", default=None))
    status = _text(_first(lead, "status", default=None))

    if applicant_name:
        registry.add(
            claim=f"Applicant: {applicant_name}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=1.0,
        )

    if app_number:
        registry.add(
            claim=f"Application number: {app_number}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=1.0,
        )

    if app_type:
        registry.add(
            claim=f"Application type: {app_type}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=1.0,
        )

    if project_address:
        registry.add(
            claim=f"Project address: {project_address}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=1.0,
        )

    if description:
        registry.add(
            claim=f"Project description: {description}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=0.9,
        )

    if status:
        registry.add(
            claim=f"Current status: {status}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            document_name=source_name,
            confidence=1.0,
        )

    # -- Friction evidence --
    friction_score = _int(_first(lead, "friction_score", default=0))
    friction_signals = _normalize_signals(
        _first(lead, "friction_signals", "signals", default=[])
    )

    if friction_score > 0:
        registry.add(
            claim=f"Friction score: {friction_score}",
            source_type=SOURCE_FRICTION,
            source_url=source_url,
            confidence=0.9,
        )

    for signal in friction_signals:
        registry.add(
            claim=f"Friction signal: {signal}",
            source_type=SOURCE_FRICTION,
            source_url=source_url,
            confidence=0.9,
        )

    friction_events = _list(
        _first(lead, "friction_events", "events", "historical_evidence", default=[])
    )

    for event in friction_events:
        if not isinstance(event, Mapping):
            continue

        event_type = _text(event.get("event_type")) or _text(event.get("type")) or "unknown"
        evidence_text = _text(event.get("evidence"))
        event_date = _text(event.get("event_date"))
        event_confidence = float(event.get("confidence") or 0.7)

        claim = f"Historical event: {event_type}"

        if evidence_text:
            claim = f"Historical event: {event_type} -- {evidence_text}"

        registry.add(
            claim=claim,
            source_type=SOURCE_FRICTION,
            source_url=source_url,
            date=event_date,
            excerpt=evidence_text,
            confidence=event_confidence,
        )

    # -- Project date evidence --
    next_date = _text(_first(lead, "next_project_date", default=None))
    next_event = _text(_first(lead, "next_project_event", default=None))
    next_time = _text(_first(lead, "next_project_time", default=None))
    has_future = _bool(_first(lead, "has_future_opportunity", default=False))
    days_until = lead.get("days_until_event")

    if next_date and has_future:
        time_part = f" at {next_time}" if next_time else ""
        event_label = next_event.replace("_", " ") if next_event else "event"
        registry.add(
            claim=f"Scheduled {event_label} on {next_date}{time_part}",
            source_type=SOURCE_DATE,
            source_url=source_url,
            date=next_date,
            confidence=0.95,
        )

    future_dates = _list(
        _first(lead, "future_project_dates", "future_dates", default=[])
    )

    for fd in future_dates:
        if isinstance(fd, Mapping):
            fd_value = _text(fd.get("value"))
            fd_label = _text(fd.get("label"))
            fd_context = _text(fd.get("context"))

            if fd_value and fd_label:
                registry.add(
                    claim=f"Future date: {fd_label} on {fd_value}",
                    source_type=SOURCE_DATE,
                    source_url=source_url,
                    date=fd_value,
                    excerpt=fd_context,
                    confidence=0.8,
                )

    historical_dates = _list(
        _first(lead, "historical_project_dates", "historical_dates", default=[])
    )

    for hd in historical_dates:
        if isinstance(hd, Mapping):
            hd_value = _text(hd.get("value"))
            hd_label = _text(hd.get("label"))

            if hd_value and hd_label:
                registry.add(
                    claim=f"Historical date: {hd_label} on {hd_value}",
                    source_type=SOURCE_DATE,
                    source_url=source_url,
                    date=hd_value,
                    confidence=0.7,
                )

    # -- Contact evidence --
    applicant_email = _text(_first(lead, "applicant_email", default=None))
    applicant_phone = _text(_first(lead, "applicant_phone", default=None))
    contact_email = _text(_first(lead, "contact_email", default=None))
    contact_phone = _text(_first(lead, "contact_phone", default=None))
    owner_email = _text(_first(lead, "owner_contact_email", default=None))
    owner_phone = _text(_first(lead, "owner_contact_phone", default=None))
    staff_email = _text(_first(lead, "staff_email", default=None))
    staff_name = _text(_first(lead, "staff_contact", default=None))
    company_name = _text(_first(lead, "company_name", default=None))
    owner_name = _text(_first(lead, "owner_name", default=None))

    if applicant_email:
        email_source = _text(_first(lead, "email_source", default="unknown"))
        registry.add(
            claim=f"Applicant email: {applicant_email} (source: {email_source})",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.9,
        )

    if applicant_phone:
        phone_source = _text(_first(lead, "phone_source", default="unknown"))
        registry.add(
            claim=f"Applicant phone: {applicant_phone} (source: {phone_source})",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.9,
        )

    if contact_email and contact_email != applicant_email:
        registry.add(
            claim=f"Contact email: {contact_email}",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.8,
        )

    if contact_phone and contact_phone != applicant_phone:
        registry.add(
            claim=f"Contact phone: {contact_phone}",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.8,
        )

    if owner_email:
        registry.add(
            claim=f"Owner contact email: {owner_email}",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.8,
        )

    if owner_phone:
        registry.add(
            claim=f"Owner contact phone: {owner_phone}",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.8,
        )

    if staff_name:
        registry.add(
            claim=f"Staff contact: {staff_name}",
            source_type=SOURCE_GOVERNMENT,
            source_url=source_url,
            confidence=1.0,
        )

    if staff_email:
        registry.add(
            claim=f"Staff email: {staff_email}",
            source_type=SOURCE_GOVERNMENT,
            source_url=source_url,
            confidence=1.0,
        )

    if company_name:
        registry.add(
            claim=f"Company: {company_name}",
            source_type=SOURCE_ENRICHMENT,
            source_url=source_url,
            confidence=0.8,
        )

    if owner_name:
        registry.add(
            claim=f"Property owner: {owner_name}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            confidence=0.9,
        )

    # -- Parties evidence --
    parties = _list(_first(lead, "parties", default=[]))

    for party in parties:
        if not isinstance(party, Mapping):
            continue

        party_name = _text(party.get("party_name"))
        party_role = _text(party.get("party_role"))
        party_company = _text(party.get("party_company"))
        party_email = _text(party.get("party_contact_email"))
        party_phone = _text(party.get("party_contact_phone"))
        party_source = _text(party.get("party_source", default="government_record"))

        if party_name and party_role:
            role_text = f" ({party_role})" if party_role else ""
            company_text = f" at {party_company}" if party_company else ""
            registry.add(
                claim=f"Project party: {party_name}{role_text}{company_text}",
                source_type=SOURCE_APPLICATION,
                source_url=source_url,
                confidence=0.9,
            )

        if party_email:
            registry.add(
                claim=f"Party contact email: {party_email} ({party_name or 'unknown'})",
                source_type=SOURCE_ENRICHMENT,
                source_url=source_url,
                confidence=0.8,
            )

        if party_phone:
            registry.add(
                claim=f"Party contact phone: {party_phone} ({party_name or 'unknown'})",
                source_type=SOURCE_ENRICHMENT,
                source_url=source_url,
                confidence=0.8,
            )

    # -- Approval-action intelligence evidence --
    approval_status = _text(_first(lead, "approval_status", default=None))
    approval_action = _text(_first(lead, "approval_action", default=None))
    approval_basis = _text(_first(lead, "approval_basis", default=None))
    approval_reason = _text(_first(lead, "approval_reason", default=None))

    if approval_status:
        registry.add(
            claim=f"Approval status: {approval_status}",
            source_type=SOURCE_APPROVAL,
            source_url=source_url,
            confidence=0.9,
        )

    if approval_action and approval_action != "unknown":
        registry.add(
            claim=f"Approval action: {approval_action}",
            source_type=SOURCE_APPROVAL,
            source_url=source_url,
            confidence=0.8,
        )

    if approval_reason:
        registry.add(
            claim=f"Approval reason: {approval_reason}",
            source_type=SOURCE_APPROVAL,
            source_url=source_url,
            confidence=0.8,
        )

    # -- Property / zoning evidence --
    parcel = _text(_first(lead, "parcel_number", default=None))
    acreage = _text(_first(lead, "acreage", default=None))
    zoning = _text(_first(lead, "zoning", default=None))
    neighborhood = _text(_first(lead, "neighborhood", default=None))

    if parcel:
        registry.add(
            claim=f"Parcel number: {parcel}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            confidence=1.0,
        )

    if acreage:
        registry.add(
            claim=f"Acreage: {acreage}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            confidence=0.9,
        )

    if zoning:
        registry.add(
            claim=f"Zoning: {zoning}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            confidence=1.0,
        )

    if neighborhood:
        registry.add(
            claim=f"Neighborhood: {neighborhood}",
            source_type=SOURCE_APPLICATION,
            source_url=source_url,
            confidence=1.0,
        )

    return registry


# ============================================================================
# DENIAL / FRICTION HISTORY ANALYZER
# ============================================================================

def _classify_objection_type(
    event: Mapping[str, Any],
    application_type: Optional[str],
) -> str:
    """
    Classify a friction event into a objection category.

    Returns one of: procedural, substantive, design, site, zoning,
    environmental, unknown.
    """

    event_type = str(
        event.get("event_type")
        or event.get("type")
        or ""
    ).lower()

    evidence = str(event.get("evidence") or "").lower()

    combined = f"{event_type} {evidence}"

    # Procedural objections relate to process/timing/documentation.
    procedural_keywords = (
        "continued",
        "tabled",
        "deferred",
        "incomplete",
        "documentation",
        "deadline",
        "submission",
        "procedural",
        "application form",
    )

    if any(kw in combined for kw in procedural_keywords):
        return OBJECTION_PROCEDURAL

    # Zoning objections.
    zoning_keywords = (
        "zoning",
        "zone",
        "rezone",
        "rezoning",
        "variance",
        "zone map",
        "nonconforming",
        "use permit",
        "conditional use",
    )

    if any(kw in combined for kw in zoning_keywords):
        return OBJECTION_ZONING

    # Design objections.
    design_keywords = (
        "design",
        "aesthetic",
        "architectural",
        "elevation",
        "setback",
        "height",
        "façade",
        "facade",
        "appearance",
    )

    if any(kw in combined for kw in design_keywords):
        return OBJECTION_DESIGN

    # Site/infrastructure objections.
    site_keywords = (
        "site plan",
        "grading",
        "drainage",
        "parking",
        "traffic",
        "access",
        "curb",
        "utility",
        "infrastructure",
        "erosion",
    )

    if any(kw in combined for kw in site_keywords):
        return OBJECTION_SITE

    # Environmental objections.
    env_keywords = (
        "environmental",
        "noise",
        "pollution",
        "wetland",
        "wildlife",
        "habitat",
        "stormwater",
        "flood",
    )

    if any(kw in combined for kw in env_keywords):
        return OBJECTION_ENVIRONMENTAL

    # If the event is a denial or recommended denial with no contextual
    # keywords, it is a substantive objection by default.
    if event_type in ("denied", "recommended_denial"):
        return OBJECTION_SUBSTANTIVE

    # Staff concern without specific keywords -- substantive.
    if event_type in ("staff_concern",):
        return OBJECTION_SUBSTANTIVE

    return OBJECTION_UNKNOWN


def _is_procedural_event(event: Mapping[str, Any]) -> bool:
    """True if the event represents a procedural delay, not a substance rejection."""

    event_type = str(
        event.get("event_type")
        or event.get("type")
        or ""
    ).lower()

    return event_type in PROCEDURAL_SIGNALS


def _analyze_denial_history(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Analyze the denial/friction history in depth.

    Returns:
        (denial_history_items, evidence_ids_used)
    """

    friction_events = _list(
        _first(
            lead,
            "friction_events",
            "events",
            "historical_evidence",
            default=[],
        )
    )

    application_type = _text(
        _first(lead, "application_type", default=None)
    )

    denial_history: list[dict[str, Any]] = []
    all_evidence_ids: list[str] = []

    for event in friction_events:
        if not isinstance(event, Mapping):
            continue

        event_type = str(
            event.get("event_type")
            or event.get("type")
            or ""
        ).lower()

        if not event_type:
            continue

        objection_type = _classify_objection_type(event, application_type)
        is_procedural = _is_procedural_event(event)
        event_date = _text(event.get("event_date"))
        evidence_text = _text(event.get("evidence"))
        confidence = float(event.get("confidence") or 0.7)

        # Find evidence_id in registry for this event.
        evidence_id = _find_evidence_id(
            registry,
            f"Historical event: {event_type}",
            source_type=SOURCE_FRICTION,
        )

        evidence_ids: list[str] = []

        if evidence_id:
            evidence_ids.append(evidence_id)
            all_evidence_ids.append(evidence_id)

        item: dict[str, Any] = {
            "event_type": event_type,
            "event_date": event_date,
            "objection_type": objection_type,
            "is_procedural": is_procedural,
            "evidence_text": evidence_text,
            "confidence": confidence,
            "evidence_ids": evidence_ids,
        }

        denial_history.append(item)

    # Check for recurrence -- same objection type appearing more than once.
    objection_counts: dict[str, int] = {}

    for item in denial_history:
        otype = item["objection_type"]
        objection_counts[otype] = objection_counts.get(otype, 0) + 1

    recurrence_flags: dict[str, bool] = {
        otype: count > 1
        for otype, count in objection_counts.items()
    }

    for item in denial_history:
        item["is_recurrence"] = recurrence_flags.get(
            item["objection_type"], False
        )

    return denial_history, all_evidence_ids


def _find_evidence_id(
    registry: EvidenceRegistry,
    claim_prefix: str,
    source_type: Optional[str] = None,
) -> Optional[str]:
    """Find the first evidence_id matching a claim prefix."""

    for record in registry.all_records():
        if record.claim.startswith(claim_prefix):
            if source_type is None or record.source_type == source_type:
                return record.evidence_id

    return None


# ============================================================================
# APPROVAL BLOCKER IDENTIFIER
# ============================================================================

def _identify_blockers(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
    denial_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Identify approval blockers ranked by severity.

    Severity order: CRITICAL > HIGH > MEDIUM > LOW.

    Blocker types:
        denial               -- application was denied
        recommended_denial   -- staff recommended denial
        continuance          -- application was continued/tabled
        high_friction        -- high friction score without specific denial
        staff_concern        -- staff raised a concern
        no_contact           -- no contact evidence for outreach
    """

    blockers: list[dict[str, Any]] = []

    friction_score = _int(
        _first(lead, "friction_score", default=0)
    )
    friction_signals = _normalize_signals(
        _first(lead, "friction_signals", "signals", default=[])
    )
    signal_set = set(friction_signals)

    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )
    contact_email = _text(
        _first(lead, "contact_email", default=None)
    )
    contact_phone = _text(
        _first(lead, "contact_phone", default=None)
    )
    owner_email = _text(
        _first(lead, "owner_contact_email", default=None)
    )
    owner_phone = _text(
        _first(lead, "owner_contact_phone", default=None)
    )
    parties = _list(_first(lead, "parties", default=[]))
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    priority = str(
        _first(lead, "priority", default="LOW")
    ).upper()

    source_url = _text(
        _first(lead, "source_url", "source", default=None)
    )

    # -- CRITICAL: Denial --
    if "denied" in signal_set:
        denial_events = [
            d for d in denial_history
            if d["event_type"] == "denied"
        ]

        evidence_ids: list[str] = []

        for de in denial_events:
            evidence_ids.extend(de.get("evidence_ids", []))

        blockers.append({
            "blocker_type": "denial",
            "severity": SEVERITY_CRITICAL,
            "statement": "Government record confirms the application was denied.",
            "classification": CLAIM_FACT,
            "confidence": "HIGH",
            "evidence_ids": evidence_ids,
            "rationale": (
                "A denial is a terminal government decision on the current "
                "application cycle. Without a re-submission or appeal, no "
                "further approval action can proceed."
            ),
        })

    # -- HIGH: Recommended denial --
    if "recommended_denial" in signal_set:
        rec_denial_events = [
            d for d in denial_history
            if d["event_type"] == "recommended_denial"
        ]

        rec_evidence_ids: list[str] = []

        for de in rec_denial_events:
            rec_evidence_ids.extend(de.get("evidence_ids", []))

        blockers.append({
            "blocker_type": "recommended_denial",
            "severity": SEVERITY_HIGH,
            "statement": (
                "Staff recommended denial of the application."
            ),
            "classification": CLAIM_FACT,
            "confidence": "HIGH",
            "evidence_ids": rec_evidence_ids,
            "rationale": (
                "A staff-level denial recommendation signals serious "
                "deficiencies. The planning commission may follow the "
                "recommendation, though it is not binding."
            ),
        })

    # -- HIGH: Staff concern --
    if "staff_concern" in signal_set:
        concern_events = [
            d for d in denial_history
            if d["event_type"] == "staff_concern"
        ]

        concern_evidence_ids: list[str] = []

        for de in concern_events:
            concern_evidence_ids.extend(de.get("evidence_ids", []))

        blockers.append({
            "blocker_type": "staff_concern",
            "severity": SEVERITY_HIGH,
            "statement": (
                "Staff raised concerns about the application."
            ),
            "classification": CLAIM_FACT,
            "confidence": "MEDIUM",
            "evidence_ids": concern_evidence_ids,
            "rationale": (
                "Staff concerns that are not resolved before the hearing "
                "may result in a denial recommendation or conditions."
            ),
        })

    # -- MEDIUM: Continuance/tabled --
    has_continuance = signal_set.intersection(PROCEDURAL_SIGNALS)

    if has_continuance:
        cont_evidence_ids: list[str] = []

        for de in denial_history:
            if de.get("is_procedural"):
                cont_evidence_ids.extend(de.get("evidence_ids", []))

        blockers.append({
            "blocker_type": "continuance",
            "severity": SEVERITY_MEDIUM,
            "statement": (
                "The application has been continued or tabled, indicating "
                "a procedural delay."
            ),
            "classification": CLAIM_FACT,
            "confidence": "MEDIUM",
            "evidence_ids": cont_evidence_ids,
            "rationale": (
                "Continuances often indicate unresolved staff concerns, "
                "applicant-requested delays, or scheduling conflicts. "
                "Each continuance delays the approval timeline."
            ),
        })

    # -- MEDIUM: High friction score without specific denial --
    if (
        friction_score >= 50
        and not signal_set.intersection(DENIAL_SIGNALS)
    ):
        blockers.append({
            "blocker_type": "high_friction",
            "severity": SEVERITY_MEDIUM,
            "statement": (
                f"The application has a friction score of {friction_score}, "
                "indicating elevated approval difficulty."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "rationale": (
                "A high friction score without a specific denial signal "
                "suggests accumulated complications that may impede "
                "approval."
            ),
        })

    # -- MEDIUM: Neighborhood/public opposition --
    opposition_signals = signal_set.intersection({
        "neighborhood_concern",
        "public_opposition",
    })

    if opposition_signals:
        opp_evidence_ids: list[str] = []

        for de in denial_history:
            if de["event_type"] in opposition_signals:
                opp_evidence_ids.extend(de.get("evidence_ids", []))

        blockers.append({
            "blocker_type": "opposition",
            "severity": SEVERITY_MEDIUM,
            "statement": (
                "Community or neighborhood opposition has been recorded."
            ),
            "classification": CLAIM_FACT,
            "confidence": "MEDIUM",
            "evidence_ids": opp_evidence_ids,
            "rationale": (
                "Community opposition can influence planning commission "
                "decisions, especially in public hearing settings."
            ),
        })

    # -- LOW: No contact evidence --
    has_any_contact = any([
        applicant_email,
        applicant_phone,
        contact_email,
        contact_phone,
        owner_email,
        owner_phone,
    ])

    party_has_contact = False

    for party in parties:
        if isinstance(party, Mapping):
            if party.get("party_contact_email") or party.get("party_contact_phone"):
                party_has_contact = True
                break

    if not has_any_contact and not party_has_contact:
        blockers.append({
            "blocker_type": "no_contact",
            "severity": SEVERITY_LOW,
            "statement": (
                "No public contact evidence was found for the applicant "
                "or project parties."
            ),
            "classification": CLAIM_FACT,
            "confidence": "HIGH",
            "evidence_ids": [],
            "rationale": (
                "Without contact evidence, outreach and assistance "
                "cannot proceed. This is an intelligence gap, not an "
                "approval blocker per se, but limits commercial value."
            ),
        })

    # Sort by severity.
    severity_rank = {
        SEVERITY_CRITICAL: 0,
        SEVERITY_HIGH: 1,
        SEVERITY_MEDIUM: 2,
        SEVERITY_LOW: 3,
    }

    blockers.sort(key=lambda b: severity_rank.get(b["severity"], 99))

    return blockers


# ============================================================================
# REQUIREMENTS CLASSIFIER
# ============================================================================

def _classify_requirements(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
    denial_history: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Classify requirements into three groups:

        A -- Explicit government requirements (verbatim in documents).
        B -- Derived/inferred requirements (standard process consequences).
        C -- PermitSignal recommendations (best-practice actions).

    Every requirement is backed by evidence_ids and classified.
    """

    requirements: list[dict[str, Any]] = []
    req_counter = 0

    app_type = _text(
        _first(lead, "application_type", default=None)
    )
    friction_signals = set(
        _normalize_signals(
            _first(lead, "friction_signals", "signals", default=[])
        )
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    next_event = _text(
        _first(lead, "next_project_event", default=None)
    )
    days_until = lead.get("days_until_event")

    if days_until is not None:
        try:
            days_until = int(days_until)
        except (TypeError, ValueError):
            days_until = None

    source_url = _text(
        _first(lead, "source_url", "source", default=None)
    )
    staff_email = _text(
        _first(lead, "staff_email", default=None)
    )
    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    # -- GROUP A: Explicit government requirements --

    # A hearing/meeting is scheduled -- attendance is an explicit requirement.
    hearing_labels = {
        "public_hearing",
        "public_meeting",
        "planning_commission_event",
        "municipal_council_event",
    }

    if has_future and next_event in hearing_labels:
        next_date = _text(
            _first(lead, "next_project_date", default=None)
        )
        next_time = _text(
            _first(lead, "next_project_time", default=None)
        )

        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "A",
            "group_label": "explicit_government",
            "statement": (
                f"Attend the scheduled {next_event.replace('_', ' ')} "
                f"on {next_date}"
                + (f" at {next_time}" if next_time else "")
                + "."
            ),
            "classification": CLAIM_FACT,
            "confidence": "HIGH",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Scheduled"
            ),
            "rationale": (
                "A public hearing or meeting is explicitly scheduled in "
                "the government record; attendance is required for the "
                "application to proceed."
            ),
        })

    # Staff required additional information.
    if "additional_information" in friction_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "A",
            "group_label": "explicit_government",
            "statement": "Submit the additional documentation requested by staff.",
            "classification": CLAIM_FACT,
            "confidence": "HIGH",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: additional_information"
            ),
            "rationale": (
                "The government record indicates additional information "
                "was requested; failure to provide it may result in "
                "denial or continued deferral."
            ),
        })

    # -- GROUP B: Derived/inferred requirements --

    # If denied, a re-submission or appeal is required to proceed.
    if "denied" in friction_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "B",
            "group_label": "derived_inferred",
            "statement": (
                "File an appeal or submit a new application to proceed "
                "after denial."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: denied"
            ),
            "rationale": (
                "A denial is a terminal outcome on the current cycle. "
                "The applicant must either appeal within the jurisdiction's "
                "deadline or submit a new application."
            ),
        })

    # If staff recommended denial, address the specific concerns before
    # the hearing.
    if "recommended_denial" in friction_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "B",
            "group_label": "derived_inferred",
            "statement": (
                "Address staff's stated concerns before the planning "
                "commission hearing."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: recommended_denial"
            ),
            "rationale": (
                "Staff recommendations carry significant weight with the "
                "planning commission. Addressing the underlying concerns "
                "before the hearing is the most effective way to change "
                "the trajectory."
            ),
        })

    # If staff concern, resolve the concern.
    if "staff_concern" in friction_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "B",
            "group_label": "derived_inferred",
            "statement": (
                "Resolve the concerns raised by staff before the "
                "scheduled hearing."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: staff_concern"
            ),
            "rationale": (
                "Unresolved staff concerns may result in a denial "
                "recommendation at the hearing."
            ),
        })

    # If the application was continued, identify and resolve the reason.
    cont_signals = friction_signals.intersection(PROCEDURAL_SIGNALS)

    if cont_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "B",
            "group_label": "derived_inferred",
            "statement": (
                "Determine the reason for the prior continuance and "
                "resolve it before the next hearing."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "rationale": (
                "Continuances typically indicate unresolved issues. "
                "Identifying and resolving the underlying cause reduces "
                "the risk of another delay."
            ),
        })

    # High-value application types often require additional documentation.
    high_value_types = {
        "zone map amendment",
        "rezone",
        "rezoning",
        "concept plan",
        "project plan",
        "variance",
        "conditional use",
        "conditional use permit",
        "site plan",
        "development agreement",
        "subdivision",
    }

    app_type_lower = (app_type or "").lower()

    if app_type_lower in high_value_types:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "B",
            "group_label": "derived_inferred",
            "statement": (
                f"Prepare a complete submission package for the "
                f"{app_type} including all required supporting "
                "documents."
            ),
            "classification": CLAIM_INFERENCE,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "rationale": (
                f"High-value application types such as {app_type} "
                "typically require comprehensive supporting documentation "
                "including site plans, narratives, and impact analyses."
            ),
        })

    # -- GROUP C: PermitSignal recommendations --

    # Recommendation: Contact staff before the hearing.
    if has_future and staff_email:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "C",
            "group_label": "permitsignal_recommendation",
            "statement": (
                "Contact the assigned staff member before the hearing "
                "to discuss the application and address any outstanding "
                "questions."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Staff email:"
            ),
            "rationale": (
                "Pre-hearing staff communication helps clarify expectations "
                "and can prevent surprises at the hearing."
            ),
        })

    # Recommendation: Prepare a presentation for the hearing.
    if has_future and next_event in hearing_labels:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "C",
            "group_label": "permitsignal_recommendation",
            "statement": (
                "Prepare a clear, concise presentation for the planning "
                "commission hearing addressing the project scope, "
                "compliance with zoning standards, and responses to any "
                "staff concerns."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "rationale": (
                "Planning commission hearings are public forums where "
                "the applicant presents their case. Prepared presentations "
                "demonstrate professionalism and improve outcomes."
            ),
        })

    # Recommendation: Engage professional services.
    if friction_score_high(friction_signals) or "denied" in friction_signals:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "C",
            "group_label": "permitsignal_recommendation",
            "statement": (
                "Consider engaging a land-use attorney or planning "
                "consultant to assist with the application or appeal."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "LOW",
            "evidence_ids": [],
            "rationale": (
                "Complex or previously denied applications benefit from "
                "professional guidance to navigate the approval process "
                "and address technical deficiencies."
            ),
        })

    # Recommendation: Community outreach.
    opposition = friction_signals.intersection({
        "neighborhood_concern",
        "public_opposition",
    })

    if opposition:
        req_counter += 1
        requirements.append({
            "requirement_id": f"R{req_counter:03d}",
            "group": "C",
            "group_label": "permitsignal_recommendation",
            "statement": (
                "Conduct community outreach to address neighborhood "
                "concerns before the hearing."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "rationale": (
                "Proactive community engagement can reduce opposition "
                "at the hearing and demonstrate good faith."
            ),
        })

    return requirements


def friction_score_high(signals: set) -> bool:
    """Check if friction signals indicate high difficulty."""

    return bool(signals.intersection(HIGH_FRICTION_SIGNALS))


def _find_evidence_ids_by_prefix(
    registry: EvidenceRegistry,
    prefix: str,
) -> list[str]:
    """Find all evidence_ids whose claim starts with a given prefix."""

    return [
        record.evidence_id
        for record in registry.all_records()
        if record.claim.startswith(prefix)
    ]


# ============================================================================
# ACTION PLAN GENERATOR
# ============================================================================

def _generate_action_plan(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Generate a prioritized action plan.

    Priority order:
        1. Address staff concerns / resolve denial
        2. Prepare for hearing
        3. Obtain contact / complete documentation
        4. Community engagement
        5. Monitoring
    """

    actions: list[dict[str, Any]] = []
    action_counter = 0

    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    next_event = _text(
        _first(lead, "next_project_event", default=None)
    )
    next_date = _text(
        _first(lead, "next_project_date", default=None)
    )
    days_until = lead.get("days_until_event")

    if days_until is not None:
        try:
            days_until = int(days_until)
        except (TypeError, ValueError):
            days_until = None

    friction_signals = set(
        _normalize_signals(
            _first(lead, "friction_signals", "signals", default=[])
        )
    )
    staff_email = _text(
        _first(lead, "staff_email", default=None)
    )
    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    # Priority 1: Address staff concerns.
    if "staff_concern" in friction_signals:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 1,
            "action": (
                "Contact staff to understand and address their concerns "
                "about the application."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: staff_concern"
            ),
            "deadline": next_date,
            "rationale": (
                "Unresolved staff concerns are the most immediate threat "
                "to approval. Early resolution is critical."
            ),
        })

    # Priority 1: Resolve denial.
    if "denied" in friction_signals:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 1,
            "action": (
                "Determine whether to appeal the denial or submit a new "
                "application. Check jurisdiction deadlines for appeal "
                "filing."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: denied"
            ),
            "deadline": None,
            "rationale": (
                "A denial is terminal on the current cycle. The applicant "
                "must act within the appeal window or start over."
            ),
        })

    # Priority 1: Address recommended denial.
    if "recommended_denial" in friction_signals:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 1,
            "action": (
                "Prepare a written response or presentation addressing "
                "staff's denial recommendation before the hearing."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: recommended_denial"
            ),
            "deadline": next_date,
            "rationale": (
                "A staff denial recommendation must be directly addressed "
                "to change the commission's trajectory."
            ),
        })

    # Priority 2: Prepare for hearing.
    hearing_labels = {
        "public_hearing",
        "public_meeting",
        "planning_commission_event",
        "municipal_council_event",
    }

    if has_future and next_event in hearing_labels:
        urgency_note = ""

        if days_until is not None and days_until <= 7:
            urgency_note = " (URGENT: less than 7 days away)"

        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 2,
            "action": (
                f"Prepare all materials for the {next_event.replace('_', ' ')} "
                f"on {next_date}{urgency_note}."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "HIGH",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Scheduled"
            ),
            "deadline": next_date,
            "rationale": (
                "A hearing is explicitly scheduled. The applicant must "
                "be prepared to present their case."
            ),
        })

    # Priority 3: Submit additional documentation.
    if "additional_information" in friction_signals:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 3,
            "action": (
                "Compile and submit the additional documentation requested "
                "by staff."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "HIGH",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: additional_information"
            ),
            "deadline": next_date,
            "rationale": (
                "Failure to provide requested documentation will likely "
                "result in continued delay or denial."
            ),
        })

    # Priority 3: Community outreach.
    opposition = friction_signals.intersection({
        "neighborhood_concern",
        "public_opposition",
    })

    if opposition and has_future:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 3,
            "action": (
                "Conduct community outreach to address neighborhood "
                "concerns before the hearing."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "MEDIUM",
            "evidence_ids": [],
            "deadline": next_date,
            "rationale": (
                "Community opposition can sway the planning commission. "
                "Proactive engagement demonstrates good faith."
            ),
        })

    # Priority 4: Obtain contact.
    blockers_types = {b["blocker_type"] for b in blockers}

    if "no_contact" in blockers_types:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 4,
            "action": (
                "Obtain public contact information for the applicant "
                "or project owner."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "LOW",
            "evidence_ids": [],
            "deadline": None,
            "rationale": (
                "No contact evidence was found. This limits outreach "
                "capability and commercial value."
            ),
        })

    # Priority 5: Monitor (always present as fallback).
    if not has_future:
        action_counter += 1
        actions.append({
            "action_id": f"A{action_counter:03d}",
            "priority_rank": 5,
            "action": (
                "Monitor government records for future filing dates or "
                "re-submission opportunities."
            ),
            "classification": CLAIM_RECOMMENDATION,
            "confidence": "LOW",
            "evidence_ids": [],
            "deadline": None,
            "rationale": (
                "No future project event is currently on record. Monitor "
                "for new filings or scheduling updates."
            ),
        })

    return actions


# ============================================================================
# STAKEHOLDER IDENTIFIER
# ============================================================================

def _identify_stakeholders(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
) -> list[dict[str, Any]]:
    """
    Identify all stakeholders and their roles.

    Categories: applicant, owner, staff, parties.
    """

    stakeholders: list[dict[str, Any]] = []

    applicant_name = _text(
        _first(lead, "applicant_name", default=None)
    )
    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    owner_name = _text(
        _first(lead, "owner_name", default=None)
    )
    owner_email = _text(
        _first(lead, "owner_contact_email", default=None)
    )
    owner_phone = _text(
        _first(lead, "owner_contact_phone", default=None)
    )

    staff_name = _text(
        _first(lead, "staff_contact", default=None)
    )
    staff_email = _text(
        _first(lead, "staff_email", default=None)
    )
    staff_phone = _text(
        _first(lead, "staff_phone", default=None)
    )

    company_name = _text(
        _first(lead, "company_name", default=None)
    )

    # Applicant.
    if applicant_name:
        stakeholders.append({
            "stakeholder_type": "applicant",
            "name": applicant_name,
            "email": applicant_email,
            "phone": applicant_phone,
            "organization": company_name,
            "role": "applicant_of_record",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Applicant:"
            ),
        })

    # Owner.
    if owner_name and owner_name != applicant_name:
        stakeholders.append({
            "stakeholder_type": "owner",
            "name": owner_name,
            "email": owner_email,
            "phone": owner_phone,
            "organization": None,
            "role": "property_owner",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Property owner:"
            ),
        })

    # Staff.
    if staff_name:
        stakeholders.append({
            "stakeholder_type": "staff",
            "name": staff_name,
            "email": staff_email,
            "phone": staff_phone,
            "organization": None,
            "role": "government_staff",
            "evidence_ids": (
                _find_evidence_ids_by_prefix(registry, "Staff contact:")
                + _find_evidence_ids_by_prefix(registry, "Staff email:")
            ),
        })

    # Other parties.
    parties = _list(_first(lead, "parties", default=[]))

    seen_party_names: set[str] = set()

    for party in parties:
        if not isinstance(party, Mapping):
            continue

        party_name = _text(party.get("party_name"))
        party_role = _text(party.get("party_role"))
        party_company = _text(party.get("party_company"))
        party_email = _text(party.get("party_contact_email"))
        party_phone = _text(party.get("party_contact_phone"))

        if not party_name:
            continue

        if party_name in seen_party_names:
            continue

        seen_party_names.add(party_name)

        stakeholders.append({
            "stakeholder_type": "party",
            "name": party_name,
            "email": party_email,
            "phone": party_phone,
            "organization": party_company,
            "role": party_role or "unknown",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, f"Project party: {party_name}"
            ),
        })

    return stakeholders


# ============================================================================
# DECISION PATH RECONSTRUCTOR
# ============================================================================

def _reconstruct_decision_path(
    lead: Mapping[str, Any],
    registry: EvidenceRegistry,
    denial_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Reconstruct the decision path from evidence.

    Typical path:
        application_filed -> staff_review -> planning_commission
        -> city_council -> completed

    Only stages with evidence are included. Stages are not fabricated.
    """

    path: list[dict[str, Any]] = []

    app_number = _text(
        _first(lead, "application_number", default=None)
    )
    app_type = _text(
        _first(lead, "application_type", default=None)
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    next_event = _text(
        _first(lead, "next_project_event", default=None)
    )
    next_date = _text(
        _first(lead, "next_project_date", default=None)
    )
    priority = str(
        _first(lead, "priority", default="LOW")
    ).upper()
    friction_signals = set(
        _normalize_signals(
            _first(lead, "friction_signals", "signals", default=[])
        )
    )
    approval_status = _text(
        _first(lead, "approval_status", default=None)
    )
    staff_name = _text(
        _first(lead, "staff_contact", default=None)
    )

    # Stage 1: Application filed -- always present.
    evidence_ids = _find_evidence_ids_by_prefix(
        registry, "Application number:"
    )

    path.append({
        "stage": PATH_APPLICATION_FILED,
        "stage_label": "Application Filed",
        "status": "completed",
        "evidence": (
            f"Application {app_number} ({app_type}) is on record."
            if app_number and app_type
            else "Application is on record."
        ),
        "evidence_ids": evidence_ids,
        "classification": CLAIM_FACT,
    })

    # Stage 2: Staff review -- present if staff contact exists, if there
    # are friction events (which always occur after staff review), or if
    # the approval status indicates review.
    staff_review_needed = (
        staff_name
        or bool(denial_history)
        or approval_status in ("under_review", "scheduled", "pending")
    )

    if staff_review_needed:
        review_status = "completed"

        if approval_status == "under_review":
            review_status = "in_progress"
        elif friction_signals.intersection(DENIAL_SIGNALS):
            review_status = "completed_with_issues"
        elif "staff_concern" in friction_signals:
            review_status = "concerns_raised"
        elif "additional_information" in friction_signals:
            review_status = "awaiting_information"

        review_evidence: list[str] = []

        if staff_name:
            review_evidence.extend(
                _find_evidence_ids_by_prefix(registry, "Staff contact:")
            )

        for event in denial_history:
            review_evidence.extend(event.get("evidence_ids", []))

        path.append({
            "stage": PATH_STAFF_REVIEW,
            "stage_label": "Staff Review",
            "status": review_status,
            "evidence": (
                f"Staff review has been completed"
                + (f" ({len(denial_history)} issues identified)" if denial_history else "")
                + "."
            ),
            "evidence_ids": review_evidence[:10],
            "classification": CLAIM_FACT,
        })

    # Stage 3: Planning commission -- present if a hearing is scheduled
    # or if the application has been to (or is heading to) the commission.
    commission_needed = (
        has_future
        and next_event in {
            "public_hearing",
            "public_meeting",
            "planning_commission_event",
        }
    )

    commission_previous = (
        "continued" in friction_signals
        or "tabled" in friction_signals
        or "denied" in friction_signals
        or "recommended_denial" in friction_signals
    )

    if commission_needed or commission_previous:
        if commission_needed and next_date:
            commission_status = "scheduled"
            commission_evidence_text = (
                f"Hearing scheduled on {next_date}."
            )
        elif commission_previous:
            commission_status = "previously_reviewed"
            commission_evidence_text = (
                "The application has been before the planning commission "
                "previously."
            )
        else:
            commission_status = "pending"
            commission_evidence_text = (
                "Planning commission review is anticipated."
            )

        commission_evidence_ids: list[str] = []

        if commission_needed:
            commission_evidence_ids.extend(
                _find_evidence_ids_by_prefix(registry, "Scheduled")
            )

        path.append({
            "stage": PATH_PLANNING_COMMISSION,
            "stage_label": "Planning Commission",
            "status": commission_status,
            "evidence": commission_evidence_text,
            "evidence_ids": commission_evidence_ids,
            "classification": CLAIM_FACT if commission_needed else CLAIM_INFERENCE,
        })

    # Stage 4: City council -- only present if the application type
    # typically requires council approval (zone map amendments, ordinance
    # text amendments, etc.) or if there is evidence of council involvement.
    council_types = {
        "zone map amendment",
        "rezone",
        "rezoning",
        "ordinance text amendment",
        "development agreement",
    }

    app_type_lower = (app_type or "").lower()

    if app_type_lower in council_types:
        council_status = "pending"

        if has_future and next_event == "municipal_council_event":
            council_status = "scheduled"
        elif "denied" in friction_signals:
            council_status = "not_reached"

        council_evidence_text = (
            f"This application type ({app_type}) typically requires "
            "city council approval after the planning commission."
        )

        path.append({
            "stage": PATH_CITY_COUNCIL,
            "stage_label": "City Council",
            "status": council_status,
            "evidence": council_evidence_text,
            "evidence_ids": [],
            "classification": CLAIM_INFERENCE,
        })

    # Stage 5: Completed -- only if the process has reached a terminal
    # state (denial without future hearing, or approval).
    is_terminal = (
        "denied" in friction_signals
        and not has_future
    )

    if is_terminal:
        path.append({
            "stage": PATH_COMPLETED,
            "stage_label": "Completed",
            "status": "denied",
            "evidence": "The application has been denied with no further action on record.",
            "evidence_ids": _find_evidence_ids_by_prefix(
                registry, "Friction signal: denied"
            ),
            "classification": CLAIM_FACT,
        })

    return path


# ============================================================================
# SERVICE RECOMMENDATION
# ============================================================================

def _recommend_service(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
) -> tuple[str, str]:
    """
    Recommend a service type and scope based on complexity.

    Returns:
        (service_recommendation, service_scope)

    Service types:
        APPROVAL STRATEGY     -- complex case with denial history, multiple
                                 blockers, high friction.
        APPROVAL ASSISTANCE   -- moderate complexity, hearing preparation
                                 needed, some friction.
        APPROVAL DIAGNOSTIC   -- low complexity, straightforward application
                                 with a scheduled hearing.
        MONITORING            -- no immediate action, monitoring for future
                                 developments.
    """

    friction_signals = set(
        _normalize_signals(
            _first(lead, "friction_signals", "signals", default=[])
        )
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    priority = str(
        _first(lead, "priority", default="LOW")
    ).upper()
    blocker_types = {b["blocker_type"] for b in blockers}

    has_denial = bool(friction_signals.intersection(DENIAL_SIGNALS))
    has_high_friction = bool(
        friction_signals.intersection(HIGH_FRICTION_SIGNALS)
    )
    critical_blockers = sum(
        1 for b in blockers
        if b["severity"] in (SEVERITY_CRITICAL, SEVERITY_HIGH)
    )

    # APPROVAL STRATEGY: complex case needing strategic navigation.
    if (
        has_denial
        or critical_blockers >= 2
        or len(denial_history) >= 3
    ):
        scope_parts = []

        if has_denial:
            scope_parts.append("denial response")

        if critical_blockers >= 2:
            scope_parts.append("multi-blocker resolution")

        if len(denial_history) >= 3:
            scope_parts.append("complex friction history")

        scope = (
            "Strategic approval navigation including "
            + " and ".join(scope_parts)
            + "."
        )

        return SERVICE_APPROVAL_STRATEGY, scope

    # APPROVAL ASSISTANCE: moderate complexity with actionable items.
    if (
        has_high_friction
        or "staff_concern" in blocker_types
        or "recommended_denial" in blocker_types
        or (
            has_future
            and priority in ("HIGH", "MEDIUM")
        )
    ):
        scope_parts = []

        if "staff_concern" in blocker_types:
            scope_parts.append("staff concern resolution")

        if "recommended_denial" in blocker_types:
            scope_parts.append("denial recommendation response")

        if has_future:
            scope_parts.append("hearing preparation")

        scope = (
            "Approval assistance including "
            + " and ".join(scope_parts)
            + "."
        ) if scope_parts else "Approval assistance for the scheduled hearing."

        return SERVICE_APPROVAL_ASSISTANCE, scope

    # APPROVAL DIAGNOSTIC: straightforward application.
    if has_future:
        return (
            SERVICE_APPROVAL_DIAGNOSTIC,
            "Diagnostic review of the application and scheduled hearing.",
        )

    # MONITORING: no immediate action.
    return (
        SERVICE_MONITORING,
        "Ongoing monitoring for future scheduling updates or re-filing opportunities.",
    )


# ============================================================================
# PRICING INPUTS (complexity signals only -- never actual prices)
# ============================================================================

def _build_pricing_inputs(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
    service_recommendation: str,
) -> dict[str, Any]:
    """
    Generate pricing inputs -- complexity signals for downstream pricing.

    This module NEVER generates actual prices, fees, or cost estimates.
    It only produces signals that a pricing module could use.
    """

    friction_score = _int(
        _first(lead, "friction_score", default=0)
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    days_until = lead.get("days_until_event")

    if days_until is not None:
        try:
            days_until = int(days_until)
        except (TypeError, ValueError):
            days_until = None

    critical_blockers = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_CRITICAL
    )
    high_blockers = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_HIGH
    )
    total_blockers = len(blockers)

    group_a_count = sum(
        1 for r in requirements
        if r.get("group") == "A"
    )
    group_b_count = sum(
        1 for r in requirements
        if r.get("group") == "B"
    )
    group_c_count = sum(
        1 for r in requirements
        if r.get("group") == "C"
    )
    total_requirements = len(requirements)

    complexity_signals = {
        "service_tier": service_recommendation,
        "friction_score": friction_score,
        "critical_blocker_count": critical_blockers,
        "high_blocker_count": high_blockers,
        "total_blocker_count": total_blockers,
        "has_denial_history": any(
            d["event_type"] in ("denied", "recommended_denial")
            for d in denial_history
        ),
        "denial_event_count": sum(
            1 for d in denial_history
            if d["event_type"] == "denied"
        ),
        "total_event_count": len(denial_history),
        "explicit_requirement_count": group_a_count,
        "inferred_requirement_count": group_b_count,
        "recommendation_count": group_c_count,
        "total_requirement_count": total_requirements,
        "has_future_event": has_future,
        "days_until_event": days_until,
        "urgency_signal": (
            "urgent"
            if days_until is not None and days_until <= 7
            else "soon"
            if days_until is not None and days_until <= 30
            else "standard"
            if days_until is not None
            else "unknown"
        ),
    }

    # Complexity tier -- a composite signal for pricing.
    score = 0
    score += min(friction_score, 100)
    score += critical_blockers * 30
    score += high_blockers * 15
    score += total_blockers * 5
    score += group_a_count * 5
    score += group_b_count * 3
    score += group_c_count * 1
    score += len(denial_history) * 10

    if days_until is not None and days_until <= 7:
        score += 20
    elif days_until is not None and days_until <= 30:
        score += 10

    complexity_signals["complexity_score"] = min(score, 500)

    if score >= 150:
        complexity_signals["complexity_tier"] = "complex"
    elif score >= 50:
        complexity_signals["complexity_tier"] = "moderate"
    else:
        complexity_signals["complexity_tier"] = "straightforward"

    return complexity_signals


# ============================================================================
# CLIENT MESSAGE BUILDER
# ============================================================================

def _build_client_message(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    service_recommendation: str,
    service_scope: str,
) -> str:
    """
    Build a professional, client-ready message.

    Rules:
        - No guarantees of approval.
        - No fabricated prices, fees, or contacts.
        - Evidence-driven language.
        - Professional tone.
        - Clear next steps.
    """

    app_type = _text(
        _first(lead, "application_type", default=None)
    )
    applicant_name = _text(
        _first(lead, "applicant_name", default=None)
    )
    next_date = _text(
        _first(lead, "next_project_date", default=None)
    )
    next_event = _text(
        _first(lead, "next_project_event", default=None)
    )
    project_address = _text(
        _first(lead, "project_address", default=None)
    )
    app_number = _text(
        _first(lead, "application_number", default=None)
    )

    pieces: list[str] = []

    # Opening.
    if applicant_name:
        pieces.append(f"Dear {applicant_name},")
    else:
        pieces.append("Dear Applicant,")

    pieces.append("")

    # Project identification.
    project_line = "We have reviewed the government record for your"

    if app_type and project_address:
        project_line += f" {app_type} application at {project_address}"
    elif app_type:
        project_line += f" {app_type} application"
    elif project_address:
        project_line += f" application at {project_address}"
    else:
        project_line += " application"

    if app_number:
        project_line += f" ({app_number})"

    project_line += "."

    pieces.append(project_line)
    pieces.append("")

    # Current status.
    critical_blockers = [
        b for b in blockers
        if b["severity"] in (SEVERITY_CRITICAL, SEVERITY_HIGH)
    ]

    if critical_blockers:
        pieces.append("Current Status:")

        for blocker in critical_blockers:
            pieces.append(f"- {blocker['statement']}")

        pieces.append("")

    # Upcoming events.
    if next_date and next_event:
        event_label = next_event.replace("_", " ")
        pieces.append(
            f"The next scheduled government action is a {event_label} "
            f"on {next_date}."
        )
        pieces.append("")

    # Requirements summary.
    group_a = [r for r in requirements if r.get("group") == "A"]

    if group_a:
        pieces.append("Government-Required Actions:")

        for req in group_a:
            pieces.append(f"- {req['statement']}")

        pieces.append("")

    # Service recommendation.
    pieces.append(f"Recommended Service: {service_recommendation}")

    if service_scope:
        pieces.append(service_scope)

    pieces.append("")

    # Disclaimer.
    pieces.append(
        "This analysis is based on publicly available government records "
        "and does not constitute legal advice. No guarantees of approval "
        "are made or implied. We recommend consulting with a qualified "
        "land-use professional for specific guidance."
    )

    return "\n".join(pieces)


# ============================================================================
# INTERNAL STRATEGY BUILDER
# ============================================================================

def _build_internal_strategy(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
    stakeholders: list[dict[str, Any]],
    service_recommendation: str,
) -> str:
    """
    Build an internal strategy document.

    This is NOT client-facing. It is brutally direct and intended
    for PermitSignal's internal use only.
    """

    app_type = _text(
        _first(lead, "application_type", default=None)
    )
    applicant_name = _text(
        _first(lead, "applicant_name", default=None)
    )
    friction_score = _int(
        _first(lead, "friction_score", default=0)
    )
    priority = str(
        _first(lead, "priority", default="LOW")
    ).upper()
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    days_until = lead.get("days_until_event")

    if days_until is not None:
        try:
            days_until = int(days_until)
        except (TypeError, ValueError):
            days_until = None

    pieces: list[str] = []

    pieces.append("=" * 60)
    pieces.append("INTERNAL STRATEGY -- NOT FOR CLIENT DISTRIBUTION")
    pieces.append("=" * 60)
    pieces.append("")

    # Situation assessment.
    pieces.append("SITUATION:")

    if applicant_name:
        pieces.append(f"  Applicant: {applicant_name}")

    if app_type:
        pieces.append(f"  Type: {app_type}")

    pieces.append(f"  Priority: {priority}")
    pieces.append(f"  Friction score: {friction_score}")

    if has_future and days_until is not None:
        pieces.append(f"  Days until event: {days_until}")

    pieces.append(f"  Service tier: {service_recommendation}")
    pieces.append("")

    # Blocker assessment.
    pieces.append("BLOCKERS:")

    if blockers:
        for blocker in blockers:
            pieces.append(
                f"  [{blocker['severity']}] {blocker['blocker_type']}: "
                f"{blocker['statement']}"
            )
    else:
        pieces.append("  None identified.")

    pieces.append("")

    # Denial history assessment.
    if denial_history:
        pieces.append("FRICTION HISTORY:")

        for event in denial_history:
            recurrence = " [RECURRENCE]" if event.get("is_recurrence") else ""
            pieces.append(
                f"  - {event['event_type']} ({event['objection_type']})"
                f"{recurrence}"
            )

        pieces.append("")

    # Stakeholder map.
    pieces.append("STAKEHOLDERS:")

    for s in stakeholders:
        pieces.append(
            f"  {s['stakeholder_type']}: {s['name']}"
            + (f" <{s['email']}>" if s.get("email") else "")
            + (f" [{s['role']}]" if s.get("role") else "")
        )

    pieces.append("")

    # Honest assessment.
    pieces.append("HONEST ASSESSMENT:")

    critical_count = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_CRITICAL
    )
    high_count = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_HIGH
    )

    if critical_count > 0:
        pieces.append(
            f"  This case has {critical_count} critical blocker(s). "
            "The approval path is seriously compromised."
        )
    elif high_count > 0:
        pieces.append(
            f"  This case has {high_count} high-severity blocker(s). "
            "Significant work is needed before approval."
        )
    elif has_future:
        pieces.append(
            "  This case has a scheduled hearing and moderate friction. "
            "Preparation is the priority."
        )
    else:
        pieces.append(
            "  This case has no scheduled future event. Monitoring "
            "is the primary activity."
        )

    # Contact status.
    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    if not applicant_email and not applicant_phone:
        pieces.append(
            "  WARNING: No contact evidence. Outreach is impossible "
            "until contact is obtained."
        )

    pieces.append("")
    pieces.append("=" * 60)

    return "\n".join(pieces)


# ============================================================================
# EXECUTIVE DIAGNOSIS GENERATOR
# ============================================================================

def _generate_executive_diagnosis(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
    service_recommendation: str,
) -> str:
    """
    Generate a one-paragraph executive diagnosis.

    Must be a single paragraph. Must be evidence-driven. Must not
    make guarantees.
    """

    app_type = _text(
        _first(lead, "application_type", default=None)
    )
    applicant_name = _text(
        _first(lead, "applicant_name", default=None)
    )
    project_address = _text(
        _first(lead, "project_address", default=None)
    )
    friction_score = _int(
        _first(lead, "friction_score", default=0)
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    next_date = _text(
        _first(lead, "next_project_date", default=None)
    )

    critical_blockers = [
        b for b in blockers
        if b["severity"] in (SEVERITY_CRITICAL, SEVERITY_HIGH)
    ]

    pieces: list[str] = []

    # Subject identification.
    subject = applicant_name or "This applicant"

    if app_type and project_address:
        pieces.append(
            f"{subject}'s {app_type} application at {project_address}"
        )
    elif app_type:
        pieces.append(
            f"{subject}'s {app_type} application"
        )
    elif project_address:
        pieces.append(
            f"The application at {project_address}"
        )
    else:
        pieces.append("This application")

    # Status assessment.
    if critical_blockers:
        blocker_descriptions = [
            b["statement"].rstrip(".")
            for b in critical_blockers
        ]

        pieces.append(
            f" faces {len(critical_blockers)} significant "
            f"challenge(s): {'; '.join(blocker_descriptions)}"
        )
    elif denial_history:
        pieces.append(
            f" has {len(denial_history)} friction event(s) on record"
        )
    else:
        pieces.append(" has a relatively clean government record")

    # Friction context.
    if friction_score > 0:
        pieces.append(
            f" with a friction score of {friction_score}"
        )

    # Timeline.
    if has_future and next_date:
        pieces.append(
            f". A hearing is scheduled on {next_date}"
        )
    else:
        pieces.append(
            " with no future hearing currently scheduled"
        )

    # Requirement summary.
    group_a = [r for r in requirements if r.get("group") == "A"]

    if group_a:
        pieces.append(
            f". There are {len(group_a)} government-required "
            "action(s) that must be addressed"
        )

    pieces.append(".")

    # Service recommendation.
    pieces.append(
        f" We recommend a {service_recommendation} engagement."
    )

    return "".join(pieces)


# ============================================================================
# REPORT VALIDATOR -- 15 quality checks
# ============================================================================

def _validate_report(
    report: ApprovalIntelligenceReport,
) -> list[str]:
    """
    Run 15 quality checks against the report.

    Returns a list of validation errors. An empty list means the
    report passes all checks.
    """

    errors: list[str] = []

    # Check 1: Evidence backing -- every intelligence item must have at
    # least one evidence_id. Absence-of-evidence claims (no_contact,
    # high_friction without specific signal) are exempt because their
    # evidence is the absence of something that cannot have an id.
    absence_blocker_types = {"no_contact", "high_friction"}

    for field_name in ("approval_blockers", "requirements", "recommended_actions"):
        items = getattr(report, field_name, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping):
                    eids = item.get("evidence_ids", [])
                    item_name = item.get("title") or item.get("statement") or item.get("requirement_id", "unknown")
                    blocker_type = item.get("blocker_type", "")

                    is_absence_claim = (
                        field_name == "approval_blockers"
                        and blocker_type in absence_blocker_types
                    )

                    if not eids and item.get("classification") == CLAIM_FACT and not is_absence_claim:
                        errors.append(
                            f"Check 1: FACT claim '{item_name}' in "
                            f"{field_name} has no evidence_ids"
                        )

    # Check 2: Inference labels -- no INFERENCE claim should be presented
    # as a FACT.
    for field_name in ("approval_blockers", "requirements", "recommended_actions"):
        items = getattr(report, field_name, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping):
                    classification = item.get("classification", "")
                    item_name = item.get("title") or item.get("statement") or "unknown"

                    if classification not in (
                        CLAIM_FACT,
                        CLAIM_INFERENCE,
                        CLAIM_RECOMMENDATION,
                        CLAIM_UNKNOWN,
                    ):
                        errors.append(
                            f"Check 2: Invalid classification "
                            f"'{classification}' on '{item_name}' in "
                            f"{field_name}"
                        )

    # Check 3: No guarantees -- client_message must not contain
    # guarantee language.
    guarantee_phrases = (
        "will be approved",
        "will approve",
        "100% approval",
        "guaranteed approval",
        "guaranteed to approve",
        "certain approval",
        "approval is certain",
        "will definitely",
        "you will be approved",
        "approval guaranteed",
    )

    message_lower = report.client_message.lower()

    for phrase in guarantee_phrases:
        if phrase in message_lower:
            errors.append(
                f"Check 3: client_message contains guarantee phrase "
                f"'{phrase}'"
            )

    # Check 4: No fabricated prices -- pricing_inputs must not contain
    # actual price fields.
    price_keys = (
        "price",
        "cost",
        "fee",
        "total",
        "amount",
        "charge",
        "rate",
        "quote",
        "estimate_usd",
        "dollar",
    )

    for key in report.pricing_inputs:
        key_lower = key.lower()

        for price_key in price_keys:
            if price_key in key_lower and key_lower not in (
                "complexity_score",
                "complexity_tier",
                "total_blocker_count",
                "total_event_count",
                "total_requirement_count",
            ):
                errors.append(
                    f"Check 4: pricing_inputs contains potential price "
                    f"field '{key}'"
                )

    # Check 5: No fabricated contacts -- the report must not invent email
    # addresses or phone numbers that do not appear in evidence.
    evidence_claims = {
        record.claim
        for record_data in report.evidence
        if isinstance(record_data, Mapping)
        for record_claim in [record_data.get("claim", "")]
        for record in [type("R", (), {"claim": record_claim})()]
    }

    all_evidence_text = " ".join(
        str(item.get("statement", ""))
        for item in report.approval_blockers
        if isinstance(item, Mapping)
    )

    email_pattern = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

    found_emails_in_report = set(email_pattern.findall(all_evidence_text))

    for email in found_emails_in_report:
        email_in_evidence = any(
            email.lower() in claim.lower()
            for claim in evidence_claims
        )

        if not email_in_evidence:
            errors.append(
                f"Check 5: Blocker statement contains email '{email}' "
                "not found in evidence"
            )

    # Check 6: Evidence registry is non-empty.
    if not report.evidence:
        errors.append(
            "Check 6: Evidence registry is empty"
        )

    # Check 7: Executive diagnosis is non-empty.
    if not report.executive_diagnosis.strip():
        errors.append(
            "Check 7: Executive diagnosis is empty"
        )

    # Check 8: Client message is non-empty.
    if not report.client_message.strip():
        errors.append(
            "Check 8: Client message is empty"
        )

    # Check 9: Internal strategy is non-empty.
    if not report.internal_strategy.strip():
        errors.append(
            "Check 9: Internal strategy is empty"
        )

    # Check 10: Approval status is a recognized value.
    valid_statuses = {
        "unknown",
        "scheduled",
        "pending",
        "under_review",
        "denied",
        "recommended_denial",
        "withdrawn",
        "continued",
        "tabled",
    }

    if report.approval_status not in valid_statuses:
        errors.append(
            f"Check 10: approval_status '{report.approval_status}' "
            "is not a recognized value"
        )

    # Check 11: Approval risk is a recognized value.
    valid_risks = {RISK_HIGH, RISK_MEDIUM, RISK_LOW, RISK_UNKNOWN}

    if report.approval_risk not in valid_risks:
        errors.append(
            f"Check 11: approval_risk '{report.approval_risk}' "
            "is not a recognized value"
        )

    # Check 12: Service recommendation is a recognized value.
    valid_services = {
        SERVICE_APPROVAL_STRATEGY,
        SERVICE_APPROVAL_ASSISTANCE,
        SERVICE_APPROVAL_DIAGNOSTIC,
        SERVICE_MONITORING,
    }

    if report.service_recommendation not in valid_services:
        errors.append(
            f"Check 12: service_recommendation "
            f"'{report.service_recommendation}' is not a recognized value"
        )

    # Check 13: Decision path is non-empty when evidence exists.
    if not report.decision_path and report.evidence:
        errors.append(
            "Check 13: Decision path is empty despite having evidence"
        )

    # Check 14: Stakeholder actions reference valid stakeholders.
    stakeholder_names = {
        s.get("name", "")
        for s in report.stakeholder_actions
        if isinstance(s, Mapping)
    }

    # Check 15: All evidence_ids referenced in intelligence items exist
    # in the evidence registry.
    evidence_ids_in_registry = {
        e.get("evidence_id", "")
        for e in report.evidence
        if isinstance(e, Mapping)
    }

    all_referenced_ids: list[str] = []

    for field_name in ("approval_blockers", "requirements", "recommended_actions", "stakeholder_actions"):
        items = getattr(report, field_name, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping):
                    eids = item.get("evidence_ids", [])
                    if isinstance(eids, list):
                        all_referenced_ids.extend(eids)

    for eid in all_referenced_ids:
        if eid and eid not in evidence_ids_in_registry:
            errors.append(
                f"Check 15: evidence_id '{eid}' referenced in report "
                "but not found in evidence registry"
            )

    return errors


# ============================================================================
# RISK AND READINESS CLASSIFIER
# ============================================================================

def _classify_risk(
    friction_score: int,
    blockers: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
) -> str:
    """Classify overall approval risk."""

    critical = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_CRITICAL
    )
    high = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_HIGH
    )

    if critical > 0 or friction_score >= 80:
        return RISK_HIGH

    if high > 0 or friction_score >= 40:
        return RISK_MEDIUM

    if friction_score > 0 or len(denial_history) > 0:
        return RISK_LOW

    return RISK_LOW


def _classify_readiness(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> str:
    """Classify approval readiness."""

    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )

    critical = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_CRITICAL
    )

    high = sum(
        1 for b in blockers
        if b["severity"] == SEVERITY_HIGH
    )

    group_a = sum(
        1 for r in requirements
        if r.get("group") == "A"
    )

    if critical > 0:
        return READINESS_NOT_READY

    if high > 0 or group_a > 2:
        return READINESS_NOT_READY

    if has_future and high == 0 and critical == 0:
        if group_a == 0:
            return READINESS_READY
        return READINESS_PROVISIONAL

    if not has_future:
        return READINESS_UNKNOWN

    return READINESS_PROVISIONAL


# ============================================================================
# MAIN PUBLIC API
# ============================================================================

def build_approval_intelligence(
    lead: dict[str, Any],
    reference_date: date,
) -> dict[str, Any]:
    """
    Build a complete approval intelligence report for a single lead.

    This is the public API entry point for the APPROVAL_INTELLIGENCE_MODULE
    pipeline stage.

    Parameters:
        lead: A fully-built, enriched canonical opportunity/lead dict from
              the pipeline (after opportunity_builder, applicant_identity,
              applicant_enrichment, approval_action_intelligence stages).
        reference_date: The pipeline's reference date for timeline
                        calculations.

    Returns:
        A dict matching the ApprovalIntelligenceReport schema, ready
        to be attached to the lead record or serialized to JSON.
    """

    # 1. Build evidence registry.
    registry = _build_evidence_registry(lead)

    # 2. Analyze denial/friction history.
    denial_history, denial_evidence_ids = _analyze_denial_history(
        lead, registry
    )

    # 3. Identify approval blockers.
    blockers = _identify_blockers(lead, registry, denial_history)

    # 4. Classify requirements.
    requirements = _classify_requirements(
        lead, registry, denial_history, blockers
    )

    # 5. Generate action plan.
    actions = _generate_action_plan(
        lead, registry, blockers, requirements
    )

    # 6. Reconstruct decision path.
    decision_path = _reconstruct_decision_path(
        lead, registry, denial_history
    )

    # 7. Identify stakeholders.
    stakeholders = _identify_stakeholders(lead, registry)

    # 8. Recommend service.
    service_rec, service_scope = _recommend_service(
        lead, blockers, requirements, denial_history
    )

    # 9. Build pricing inputs.
    pricing_inputs = _build_pricing_inputs(
        lead, blockers, requirements, denial_history, service_rec
    )

    # 10. Build client message.
    client_message = _build_client_message(
        lead, blockers, requirements, service_rec, service_scope
    )

    # 11. Build internal strategy.
    internal_strategy = _build_internal_strategy(
        lead, blockers, requirements, denial_history, stakeholders, service_rec
    )

    # 12. Generate executive diagnosis.
    executive_diagnosis = _generate_executive_diagnosis(
        lead, blockers, requirements, denial_history, service_rec
    )

    # 13. Classify risk and readiness.
    friction_score = _int(
        _first(lead, "friction_score", default=0)
    )

    approval_risk = _classify_risk(
        friction_score, blockers, denial_history
    )

    approval_readiness = _classify_readiness(
        lead, blockers, requirements
    )

    # 14. Determine approval status.
    approval_status = _text(
        _first(lead, "approval_status", default="unknown")
    ) or "unknown"

    # 15. Build unresolved questions.
    unresolved_questions = _build_unresolved_questions(
        lead, blockers, denial_history
    )

    # 16. Build model warnings.
    model_warnings = _build_model_warnings(
        lead, blockers, requirements
    )

    # Assemble report.
    report = ApprovalIntelligenceReport(
        version=REPORT_VERSION,
        status="complete",
        executive_diagnosis=executive_diagnosis,
        approval_status=approval_status,
        approval_risk=approval_risk,
        approval_readiness=approval_readiness,
        denial_history=[
            {
                "event_type": d["event_type"],
                "event_date": d["event_date"],
                "objection_type": d["objection_type"],
                "is_procedural": d["is_procedural"],
                "is_recurrence": d.get("is_recurrence", False),
                "confidence": d["confidence"],
                "evidence_ids": d["evidence_ids"],
            }
            for d in denial_history
        ],
        approval_blockers=blockers,
        requirements=requirements,
        recommended_actions=actions,
        stakeholder_actions=[
            {
                "stakeholder_type": s["stakeholder_type"],
                "name": s["name"],
                "role": s["role"],
                "email": s.get("email"),
                "suggested_action": _stakeholder_suggested_action(s),
            }
            for s in stakeholders
        ],
        decision_path=decision_path,
        service_recommendation=service_rec,
        service_scope=service_scope,
        pricing_inputs=pricing_inputs,
        client_message=client_message,
        internal_strategy=internal_strategy,
        evidence=registry.all_dicts(),
        unresolved_questions=unresolved_questions,
        model_warnings=model_warnings,
    )

    return report.to_dict()


# ============================================================================
# HELPER: STAKEHOLDER SUGGESTED ACTION
# ============================================================================

def _stakeholder_suggested_action(
    stakeholder: Mapping[str, Any],
) -> str:
    """Generate a suggested action for each stakeholder type."""

    stype = stakeholder.get("stakeholder_type", "")
    role = stakeholder.get("role", "")

    if stype == "applicant":
        return "Primary contact for application-related communications."

    if stype == "owner":
        return "Property owner; may have independent authority or interest."

    if stype == "staff":
        return (
            "Government staff contact; responsible for staff review "
            "and recommendation."
        )

    if stype == "party":
        role_lower = str(role).lower()

        if "engineer" in role_lower:
            return "Technical consultant; may provide supporting documentation."

        if "architect" in role_lower:
            return "Design professional; responsible for design-related submissions."

        if "attorney" in role_lower:
            return "Legal counsel; may represent the applicant in hearings."

        if "contractor" in role_lower:
            return "Construction party; may be involved in implementation."

        if "developer" in role_lower:
            return "Development entity; may be the primary decision-maker."

        return "Project participant; role-specific engagement may be needed."

    return "Unknown stakeholder role."


# ============================================================================
# HELPER: UNRESOLVED QUESTIONS
# ============================================================================

def _build_unresolved_questions(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    denial_history: list[dict[str, Any]],
) -> list[str]:
    """Identify questions that remain unanswered from the evidence."""

    questions: list[str] = []

    friction_signals = set(
        _normalize_signals(
            _first(lead, "friction_signals", "signals", default=[])
        )
    )
    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )
    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    if "denied" in friction_signals:
        questions.append(
            "What was the specific reason for the denial?"
        )

        if "appeal" not in friction_signals:
            questions.append(
                "Has an appeal been filed or is the appeal window still open?"
            )

    if "recommended_denial" in friction_signals:
        questions.append(
            "What specific concerns did staff cite in the denial "
            "recommendation?"
        )

    if "staff_concern" in friction_signals:
        questions.append(
            "What are the specific staff concerns, and have they been "
            "formally communicated to the applicant?"
        )

    if not applicant_email and not applicant_phone:
        questions.append(
            "Can contact information for the applicant be obtained "
            "from public records?"
        )

    if not has_future:
        questions.append(
            "When is the next expected filing period or hearing date?"
        )

    blocker_types = {b["blocker_type"] for b in blockers}

    if "continuance" in blocker_types:
        questions.append(
            "What was the reason for the prior continuance?"
        )

    return questions


# ============================================================================
# HELPER: MODEL WARNINGS
# ============================================================================

def _build_model_warnings(
    lead: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> list[str]:
    """
    Generate warnings about limitations of the analysis.

    These are honest disclosures about what the model cannot determine.
    """

    warnings: list[str] = []

    friction_events = _list(
        _first(lead, "friction_events", "events", "historical_evidence", default=[])
    )

    if not friction_events:
        warnings.append(
            "No friction events were found in the government record. "
            "This does not mean the application is trouble-free -- "
            "it may simply mean the friction analyzer did not detect "
            "any signals in the available text."
        )

    applicant_email = _text(
        _first(lead, "applicant_email", default=None)
    )
    applicant_phone = _text(
        _first(lead, "applicant_phone", default=None)
    )

    if not applicant_email and not applicant_phone:
        warnings.append(
            "No public contact evidence was found for the applicant. "
            "This limits the ability to provide outreach-ready "
            "intelligence."
        )

    has_future = _bool(
        _first(lead, "has_future_opportunity", default=False)
    )

    if not has_future:
        warnings.append(
            "No future project event is currently scheduled. The "
            "approval timeline cannot be determined."
        )

    description = _text(
        _first(lead, "description", default=None)
    )

    if not description:
        warnings.append(
            "No project description was found in the government record. "
            "Some requirements and recommendations may be less accurate "
            "without a detailed description."
        )

    zoning = _text(
        _first(lead, "zoning", default=None)
    )

    if not zoning:
        warnings.append(
            "No zoning information was found. Zoning-related requirements "
            "and blockers may be under-represented."
        )

    warnings.append(
        "This analysis is based solely on publicly available government "
        "records. It does not account for private negotiations, informal "
        "discussions, or information not captured in the public record."
    )

    return warnings


# ============================================================================
# PIPELINE ENTRY POINT
# ============================================================================

def apply_approval_intelligence_engine(
    leads: list[dict[str, Any]],
    reference_date: date,
) -> list[dict[str, Any]]:
    """
    Batch pipeline stage: attach approval_intelligence to every lead.

    This is additive -- every existing field on each lead is preserved
    unchanged; only the approval_intelligence key is added.
    """

    results: list[dict[str, Any]] = []

    for lead in leads:
        item = dict(lead)

        report = build_approval_intelligence(item, reference_date)
        item["approval_intelligence"] = report

        results.append(item)

    return results


# ============================================================================
# __all__
# ============================================================================

__all__ = [
    "EvidenceRecord",
    "IntelligenceItem",
    "ApprovalIntelligenceReport",
    "EvidenceRegistry",
    "build_approval_intelligence",
    "apply_approval_intelligence_engine",
    "CLAIM_FACT",
    "CLAIM_INFERENCE",
    "CLAIM_RECOMMENDATION",
    "CLAIM_UNKNOWN",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "RISK_HIGH",
    "RISK_MEDIUM",
    "RISK_LOW",
    "RISK_UNKNOWN",
    "READINESS_READY",
    "READINESS_PROVISIONAL",
    "READINESS_NOT_READY",
    "READINESS_UNKNOWN",
    "SERVICE_APPROVAL_STRATEGY",
    "SERVICE_APPROVAL_ASSISTANCE",
    "SERVICE_APPROVAL_DIAGNOSTIC",
    "SERVICE_MONITORING",
    "SOURCE_FRICTION",
    "SOURCE_DATE",
    "SOURCE_APPLICATION",
    "SOURCE_ENRICHMENT",
    "SOURCE_IDENTITY",
    "SOURCE_GOVERNMENT",
    "SOURCE_APPROVAL",
    "OBJECTION_PROCEDURAL",
    "OBJECTION_SUBSTANTIVE",
    "OBJECTION_DESIGN",
    "OBJECTION_SITE",
    "OBJECTION_ZONING",
    "OBJECTION_ENVIRONMENTAL",
    "OBJECTION_UNKNOWN",
    "PATH_APPLICATION_FILED",
    "PATH_STAFF_REVIEW",
    "PATH_PLANNING_COMMISSION",
    "PATH_CITY_COUNCIL",
    "PATH_COMPLETED",
    "REPORT_VERSION",
]
