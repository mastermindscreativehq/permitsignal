"""
PermitSignal Outreach & Monetization Intelligence (Phase 8)

Purpose
-------
Turn an already-qualified PermitSignal commercial lead -- Phases 1-6:
application/opportunity intelligence, applicant/owner identity + contact
enrichment, approval-action intelligence (backend.app.services.
approval_action_intelligence), lead qualification (backend.app.services.
opportunity_builder.qualify_lead()), and commercial lead intelligence
(backend.app.services.commercial_lead_intelligence) -- into a controlled
commercial outreach process:

    outreach_status                 -- deterministic lead lifecycle:
                                        NEW / QUALIFIED / READY_FOR_OUTREACH /
                                        CONTACTED / REPLIED / ENGAGED /
                                        OPPORTUNITY / WON / LOST
    outreach_qualification_status   -- QUALIFIED_NOT_CONTACTABLE /
                                        QUALIFIED_READY_FOR_OUTREACH /
                                        ALREADY_CONTACTED /
                                        ACTIVE_COMMERCIAL_OPPORTUNITY /
                                        NOT_QUALIFIED
    outreach_channel                -- email / phone / none
    outreach_contact_type           -- WHICH already-computed party
                                        (owner / applicant /
                                        applicant_of_record / company / none)
                                        is the appropriate outreach target
    outreach_contact_reason         -- why that party was selected
    outreach_message_subject/body   -- personalized outreach draft built
                                        only from real, already-computed
                                        evidence
    follow_up_required/reason       -- deterministic follow-up tracking
    last_outreach_at                -- timestamp of the most recent
                                        outreach_sent event
    outreach_events                 -- append-only history of controlled
                                        lifecycle transitions

Design principle
-----------------
This module performs NO new extraction, enrichment, identity matching, or
scoring, and it never sends anything. It only re-labels/selects among
fields the pipeline has already computed (contact/company/owner fields
from applicant_identity/applicant_enrichment, approval_* from
approval_action_intelligence, commercial_* from
commercial_lead_intelligence) and produces a personalized message draft
from that same evidence. See CLAUDE.md Phase 8 / docs/DEVELOPMENT_RULES.md
("Contact Enrichment Integrity", "Do Not Duplicate Business Logic").

outreach_contact_type never duplicates the underlying contact fields --
it only records WHICH existing party (owner_contact_*, applicant_email/
phone, applicant_contact_*, contact_email/phone) is the appropriate
outreach target and why. resolve_outreach_contact() reads those existing
fields at call time rather than persisting a second copy of the values.

Lifecycle integrity
--------------------
outreach_status is the one genuinely new piece of mutable state this
module introduces. Pre-outreach (NEW/QUALIFIED/READY_FOR_OUTREACH), it is
recomputed every pipeline run from commercial_readiness -- purely
derived, like every other PermitSignal field. Once a controlled outreach
action has moved a lead to CONTACTED or later, advance_outreach_status()
freezes it against automatic pipeline recomputation: only an explicit,
human/n8n-triggered event (apply_outreach_event()) can move it further.
This is what makes "a human sent an email, then the pipeline re-ran
against the same packet" not silently reset the lead back to
READY_FOR_OUTREACH.

Monetization model (Phase 8 requirement 10)
--------------------------------------------
PermitSignal already generates a per-lead deliverable: the case-report
PDF (backend.app.services.case_report_generator, GET /leads/{number}/
report.pdf). The simplest viable monetization mechanism that reuses this
existing architecture -- no new payment infrastructure, no second
scoring model -- is pay-per-qualified-lead: PermitSignal sells access to
a lead's full intelligence record (and its case-report PDF) once it
reaches outreach_status == READY_FOR_OUTREACH (commercial_readiness ==
READY_FOR_OUTREACH is the qualification gate). outreach_status doubles
as the commercial/revenue status -- CONTACTED/REPLIED/ENGAGED track an
in-progress deal, OPPORTUNITY/WON/LOST track its outcome -- so no
separate "commercial_status" field is introduced.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from backend.app.services.commercial_lead_intelligence import (
    READINESS_NEEDS_CONTACT_ENRICHMENT,
    READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
    READINESS_NOT_READY,
    READINESS_READY_FOR_OUTREACH,
)


# ============================================================================
# VOCABULARY -- Lead lifecycle
# ============================================================================

OUTREACH_STATUS_NEW = "NEW"
OUTREACH_STATUS_QUALIFIED = "QUALIFIED"
OUTREACH_STATUS_READY = "READY_FOR_OUTREACH"
OUTREACH_STATUS_CONTACTED = "CONTACTED"
OUTREACH_STATUS_REPLIED = "REPLIED"
OUTREACH_STATUS_ENGAGED = "ENGAGED"
OUTREACH_STATUS_OPPORTUNITY = "OPPORTUNITY"
OUTREACH_STATUS_WON = "WON"
OUTREACH_STATUS_LOST = "LOST"

# Rank governs "never regress automatically" / "never regress via an event
# that targets an earlier stage". WON and LOST are both terminal (rank 7):
# neither is "ahead of" the other, they are simply two different endings.
_STATUS_RANK = {
    OUTREACH_STATUS_NEW: 0,
    OUTREACH_STATUS_QUALIFIED: 1,
    OUTREACH_STATUS_READY: 2,
    OUTREACH_STATUS_CONTACTED: 3,
    OUTREACH_STATUS_REPLIED: 4,
    OUTREACH_STATUS_ENGAGED: 5,
    OUTREACH_STATUS_OPPORTUNITY: 6,
    OUTREACH_STATUS_WON: 7,
    OUTREACH_STATUS_LOST: 7,
}

# Statuses the pipeline itself may still freely recompute from
# commercial_readiness. Anything at or beyond CONTACTED was reached via an
# explicit controlled event and must not be silently recomputed.
_PRE_OUTREACH_STATUSES = {
    OUTREACH_STATUS_NEW,
    OUTREACH_STATUS_QUALIFIED,
    OUTREACH_STATUS_READY,
}

_ALL_STATUSES = frozenset(_STATUS_RANK)

_READINESS_TO_NATURAL_STATUS = {
    READINESS_NOT_READY: OUTREACH_STATUS_NEW,
    READINESS_NEEDS_MORE_PROJECT_EVIDENCE: OUTREACH_STATUS_NEW,
    READINESS_NEEDS_CONTACT_ENRICHMENT: OUTREACH_STATUS_QUALIFIED,
    READINESS_READY_FOR_OUTREACH: OUTREACH_STATUS_READY,
}

# Controlled outreach events (Phase 8 requirement 8 -- Outreach Tracking)
# and the lifecycle stage each one represents. follow_up_required is
# special: it never changes outreach_status, it only raises the
# follow_up_required flag alongside whatever status the lead is already in.
EVENT_OUTREACH_PREPARED = "outreach_prepared"
EVENT_OUTREACH_SENT = "outreach_sent"
EVENT_RESPONSE_RECEIVED = "response_received"
EVENT_ENGAGED = "engaged"
EVENT_FOLLOW_UP_REQUIRED = "follow_up_required"
EVENT_OPPORTUNITY_CREATED = "opportunity_created"
EVENT_WON = "won"
EVENT_LOST = "lost"

_EVENT_TARGET_STATUS = {
    EVENT_OUTREACH_PREPARED: OUTREACH_STATUS_READY,
    EVENT_OUTREACH_SENT: OUTREACH_STATUS_CONTACTED,
    EVENT_RESPONSE_RECEIVED: OUTREACH_STATUS_REPLIED,
    EVENT_ENGAGED: OUTREACH_STATUS_ENGAGED,
    EVENT_FOLLOW_UP_REQUIRED: None,
    EVENT_OPPORTUNITY_CREATED: OUTREACH_STATUS_OPPORTUNITY,
    EVENT_WON: OUTREACH_STATUS_WON,
    EVENT_LOST: OUTREACH_STATUS_LOST,
}

SUPPORTED_EVENTS = tuple(_EVENT_TARGET_STATUS)

# ============================================================================
# VOCABULARY -- Qualification status (Phase 8 requirement 2)
# ============================================================================

QUALIFICATION_NOT_QUALIFIED = "NOT_QUALIFIED"
QUALIFICATION_QUALIFIED_NOT_CONTACTABLE = "QUALIFIED_NOT_CONTACTABLE"
QUALIFICATION_READY_FOR_OUTREACH = "QUALIFIED_READY_FOR_OUTREACH"
QUALIFICATION_ALREADY_CONTACTED = "ALREADY_CONTACTED"
QUALIFICATION_ACTIVE_OPPORTUNITY = "ACTIVE_COMMERCIAL_OPPORTUNITY"

# ============================================================================
# VOCABULARY -- Contact target selection
# ============================================================================

CONTACT_TYPE_OWNER = "owner"
CONTACT_TYPE_APPLICANT = "applicant"
CONTACT_TYPE_APPLICANT_OF_RECORD = "applicant_of_record"
CONTACT_TYPE_COMPANY = "company"
CONTACT_TYPE_NONE = "none"

CHANNEL_EMAIL = "email"
CHANNEL_PHONE = "phone"
CHANNEL_NONE = "none"


# ============================================================================
# HELPERS
# ============================================================================

def _text(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


# ============================================================================
# LEAD LIFECYCLE
# ============================================================================

def natural_outreach_status(commercial_readiness: Optional[str]) -> str:
    """
    The pre-outreach status implied purely by the existing commercial_
    readiness classification. Never guesses beyond NEW when readiness is
    missing/unrecognized -- conservative default, never READY_FOR_OUTREACH.
    """
    return _READINESS_TO_NATURAL_STATUS.get(commercial_readiness, OUTREACH_STATUS_NEW)


def advance_outreach_status(
    previous_status: Optional[str],
    commercial_readiness: Optional[str],
) -> str:
    """
    Deterministic, explainable lifecycle transition run on every pipeline
    pass. Pre-outreach statuses (NEW/QUALIFIED/READY_FOR_OUTREACH) track
    commercial_readiness exactly -- they are pure re-derivations, like
    every other PermitSignal field. Once a lead has reached CONTACTED or
    later via a controlled event, this function freezes it: re-running the
    pipeline against the same or a re-fetched packet must never silently
    move an in-progress or closed deal back to READY_FOR_OUTREACH.
    """
    natural = natural_outreach_status(commercial_readiness)

    if previous_status not in _ALL_STATUSES:
        return natural

    if previous_status in _PRE_OUTREACH_STATUSES:
        return natural

    return previous_status


# ============================================================================
# QUALIFICATION STATUS (Phase 8 requirement 2)
# ============================================================================

def classify_outreach_qualification(opportunity: Mapping[str, Any]) -> str:
    """
    Distinguishes the four (plus not-qualified) states Phase 8 requires:
    QUALIFIED_NOT_CONTACTABLE, QUALIFIED_READY_FOR_OUTREACH,
    ALREADY_CONTACTED, ACTIVE_COMMERCIAL_OPPORTUNITY, or NOT_QUALIFIED.
    Purely a re-labeling of commercial_readiness + outreach_status --
    never a second scoring model.
    """
    readiness = opportunity.get("commercial_readiness")
    status = opportunity.get("outreach_status") or OUTREACH_STATUS_NEW

    if readiness != READINESS_READY_FOR_OUTREACH:
        if readiness in (
            READINESS_NEEDS_CONTACT_ENRICHMENT,
            READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
        ):
            return QUALIFICATION_QUALIFIED_NOT_CONTACTABLE

        return QUALIFICATION_NOT_QUALIFIED

    if status in _PRE_OUTREACH_STATUSES:
        return QUALIFICATION_READY_FOR_OUTREACH

    if status in (
        OUTREACH_STATUS_CONTACTED,
        OUTREACH_STATUS_REPLIED,
        OUTREACH_STATUS_ENGAGED,
    ):
        return QUALIFICATION_ALREADY_CONTACTED

    return QUALIFICATION_ACTIVE_OPPORTUNITY


def is_outreach_eligible(opportunity: Mapping[str, Any]) -> bool:
    """
    True only when the existing Phase 6 commercial-readiness evidence
    already says this lead is ready for outreach. Never a new gate.
    """
    return opportunity.get("commercial_readiness") == READINESS_READY_FOR_OUTREACH


# ============================================================================
# CONTACT TARGET SELECTION (Phase 8 requirement 3)
# ============================================================================

def select_outreach_contact_type(opportunity: Mapping[str, Any]) -> tuple[str, str]:
    """
    Decide WHICH already-identified party is the appropriate outreach
    target, in the order: Property Owner/Principal (the primary
    commercially relevant party per opportunity_builder.py) -> Applicant
    of record -> Applicant-of-Record/Agent entity -> generic company
    contact -> none. Never fabricates a party -- only reads fields the
    identity/enrichment stages already populated. Returns
    (contact_type, reason).
    """
    owner_name = _text(opportunity.get("owner_name")) or _text(opportunity.get("owner_entity"))
    owner_has_contact = bool(
        _text(opportunity.get("owner_contact_email")) or _text(opportunity.get("owner_contact_phone"))
    )

    if owner_name and owner_has_contact:
        return (
            CONTACT_TYPE_OWNER,
            f"{owner_name} is on record as the property owner/principal "
            "with usable public contact evidence.",
        )

    applicant_name = _text(opportunity.get("applicant_name"))
    applicant_has_contact = bool(
        _text(opportunity.get("applicant_email"))
        or _text(opportunity.get("applicant_phone"))
        or _text(opportunity.get("contact_email"))
        or _text(opportunity.get("contact_phone"))
    )

    if applicant_name and applicant_has_contact:
        return (
            CONTACT_TYPE_APPLICANT,
            f"{applicant_name} is the applicant of record with usable "
            "public contact evidence.",
        )

    aor_name = _text(opportunity.get("applicant_contact_name")) or _text(
        opportunity.get("applicant_entity")
    )
    aor_has_contact = bool(
        _text(opportunity.get("applicant_contact_email"))
        or _text(opportunity.get("applicant_contact_phone"))
    )

    if aor_name and aor_has_contact:
        return (
            CONTACT_TYPE_APPLICANT_OF_RECORD,
            f"{aor_name} is the applicant-of-record/agent with usable "
            "public contact evidence.",
        )

    if owner_name and not owner_has_contact:
        return (
            CONTACT_TYPE_NONE,
            f"{owner_name} is on record as the property owner/principal, "
            "but no public contact evidence has been found for them yet.",
        )

    company_name = _text(opportunity.get("company_name"))

    if company_name and _text(opportunity.get("contact_email")):
        return (
            CONTACT_TYPE_COMPANY,
            f"{company_name} has a public business contact on record.",
        )

    return (
        CONTACT_TYPE_NONE,
        "No public applicant, owner, or company contact has been found yet.",
    )


def resolve_outreach_contact(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """
    Resolve the selected contact_type into a read-time contact projection
    (name/role/company/email/phone/source). Never persisted as a
    duplicate column -- callers (API, message generation) compute this on
    demand from the existing contact/company/owner fields.
    """
    contact_type, reason = select_outreach_contact_type(opportunity)

    if contact_type == CONTACT_TYPE_OWNER:
        contact: dict[str, Any] = {
            "name": _text(opportunity.get("owner_contact_name"))
            or _text(opportunity.get("owner_name"))
            or _text(opportunity.get("owner_entity")),
            "role": "Property Owner / Principal",
            "company": _text(opportunity.get("owner_entity")),
            "email": _text(opportunity.get("owner_contact_email")),
            "phone": _text(opportunity.get("owner_contact_phone")),
            "source": _text(opportunity.get("owner_source")),
        }
    elif contact_type == CONTACT_TYPE_APPLICANT:
        contact = {
            "name": _text(opportunity.get("applicant_name")),
            "role": _text(opportunity.get("contact_role")) or "Applicant",
            "company": _text(opportunity.get("company_name")),
            "email": _text(opportunity.get("applicant_email")) or _text(opportunity.get("contact_email")),
            "phone": _text(opportunity.get("applicant_phone")) or _text(opportunity.get("contact_phone")),
            "source": _text(opportunity.get("email_source")) or _text(opportunity.get("contact_source")),
        }
    elif contact_type == CONTACT_TYPE_APPLICANT_OF_RECORD:
        contact = {
            "name": _text(opportunity.get("applicant_contact_name"))
            or _text(opportunity.get("applicant_entity")),
            "role": "Applicant of Record / Agent",
            "company": _text(opportunity.get("applicant_entity")),
            "email": _text(opportunity.get("applicant_contact_email")),
            "phone": _text(opportunity.get("applicant_contact_phone")),
            "source": _text(opportunity.get("applicant_source")),
        }
    elif contact_type == CONTACT_TYPE_COMPANY:
        contact = {
            "name": _text(opportunity.get("company_name")),
            "role": "Company / Business Contact",
            "company": _text(opportunity.get("company_name")),
            "email": _text(opportunity.get("contact_email")),
            "phone": _text(opportunity.get("contact_phone")),
            "source": _text(opportunity.get("contact_source")) or _text(opportunity.get("company_source")),
        }
    else:
        contact = {
            "name": None,
            "role": None,
            "company": None,
            "email": None,
            "phone": None,
            "source": None,
        }

    contact["contact_type"] = contact_type
    contact["reason"] = reason

    return contact


def recommend_outreach_channel(contact: Mapping[str, Any]) -> str:
    """Email is preferred over phone when both exist; never invents a channel."""
    if contact.get("email"):
        return CHANNEL_EMAIL

    if contact.get("phone"):
        return CHANNEL_PHONE

    return CHANNEL_NONE


# ============================================================================
# OUTREACH MESSAGE (Phase 8 requirement 5)
# ============================================================================

def build_outreach_message(
    opportunity: Mapping[str, Any],
    contact: Mapping[str, Any],
) -> Optional[dict[str, str]]:
    """
    Build a personalized outreach draft from real, already-computed
    evidence only. Returns None when there is no usable contact channel --
    a message is never prepared for a lead that cannot actually be reached.

    Never claims an approval/denial outcome, an ownership relationship, or
    any fact beyond what approval_reason/opportunity_reason/commercial_
    action_reason already state -- those fields are themselves
    evidence-first (see approval_action_intelligence.py /
    commercial_lead_intelligence.py module docstrings).
    """
    if not contact.get("email") and not contact.get("phone"):
        return None

    name = contact.get("name") or "there"
    application_number = _text(opportunity.get("application_number")) or "an open application"
    application_type = _text(opportunity.get("application_type")) or "project"
    address = _text(opportunity.get("project_address"))
    municipality = _text(opportunity.get("municipality"))

    location = f" at {address}" if address else ""
    jurisdiction = f" in {municipality}" if municipality else ""

    situation = (
        _text(opportunity.get("approval_reason"))
        or _text(opportunity.get("opportunity_reason"))
        or "PermitSignal is tracking activity on this application."
    )

    action = _text(opportunity.get("recommended_commercial_action"))
    action_reason = _text(opportunity.get("commercial_action_reason"))

    subject = f"PermitSignal: {application_type} {application_number}{location}".strip()

    body_lines = [
        f"Hi {name},",
        "",
        f"PermitSignal is tracking application {application_number} "
        f"({application_type}){location}{jurisdiction}.",
        situation,
    ]

    if action and action != "hold -- insufficient evidence":
        action_line = f"Based on this record, PermitSignal recommends: {action}."

        if action_reason and action_reason != situation:
            action_line += f" {action_reason}"

        body_lines.append(action_line)

    body_lines.extend(
        [
            "",
            "We'd like to share the full intelligence PermitSignal has "
            "compiled on this project and discuss whether it would be "
            "useful to you.",
            "",
            "Would you be open to a brief conversation?",
            "",
            "-- PermitSignal",
        ]
    )

    return {"subject": subject, "body": "\n".join(body_lines)}


# ============================================================================
# OUTREACH EVENTS (Phase 8 requirement 8/9 -- Tracking & Follow-Up)
# ============================================================================

def apply_outreach_event(
    lead: Mapping[str, Any],
    event: str,
    note: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> dict[str, Any]:
    """
    Apply one controlled outreach lifecycle event to a lead record.

    This is the only function permitted to move outreach_status past
    READY_FOR_OUTREACH -- it represents a human/n8n-controlled action
    (Phase 8 requirement 6/7), never an automatic pipeline recomputation.

    Deterministic and explainable: a lifecycle event never moves
    outreach_status backward (except "lost", which is a valid terminal
    outcome from any active stage). follow_up_required is independent of
    outreach_status -- it only raises/clears the follow_up flag.

    Raises ValueError for an unrecognized event rather than silently
    ignoring it.
    """
    event = str(event or "").strip().lower()

    if event not in _EVENT_TARGET_STATUS:
        raise ValueError(
            f"Unknown outreach event: {event!r}. Supported events: "
            f"{', '.join(SUPPORTED_EVENTS)}."
        )

    result = dict(lead)
    current_status = result.get("outreach_status") or OUTREACH_STATUS_NEW

    # Normalize follow_up_required to a real boolean even when applying an
    # event directly to a pre-Phase-8 lead record that never had this field
    # (e.g. a row persisted before this migration/feature existed) --
    # never leave it as None, which would violate the "not null" schema
    # constraint at persistence time.
    result["follow_up_required"] = bool(result.get("follow_up_required", False))

    if event == EVENT_FOLLOW_UP_REQUIRED:
        result["follow_up_required"] = True
        result["follow_up_reason"] = note or result.get("follow_up_reason")
        resulting_status = current_status
    else:
        target_status = _EVENT_TARGET_STATUS[event]
        current_rank = _STATUS_RANK.get(current_status, 0)
        target_rank = _STATUS_RANK.get(target_status, 0)

        if event == EVENT_LOST or target_rank >= current_rank:
            result["outreach_status"] = target_status
        # Otherwise the event targets an earlier stage than the lead has
        # already reached -- never regress, keep the current status.

        resulting_status = result.get("outreach_status", current_status)

        if event in (EVENT_RESPONSE_RECEIVED, EVENT_ENGAGED, EVENT_OPPORTUNITY_CREATED):
            result["follow_up_required"] = False

        if event == EVENT_OUTREACH_SENT and occurred_at:
            result["last_outreach_at"] = occurred_at

    events = list(result.get("outreach_events") or [])
    events.append(
        {
            "event": event,
            "note": note,
            "occurred_at": occurred_at,
            "previous_status": current_status,
            "resulting_status": resulting_status,
        }
    )
    result["outreach_events"] = events

    return result


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def build_outreach_intelligence(
    opportunity: Mapping[str, Any],
    previous: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Derive the Phase 8 outreach fields for one already-qualified
    opportunity. `previous` is the same lead's prior persisted state (from
    Supabase or the pipeline's own JSON artifact), used only to carry
    forward outreach_status/outreach_events/follow_up_required/
    last_outreach_at across pipeline runs -- see advance_outreach_status().
    Callers merge the returned fields onto the opportunity (see
    apply_outreach_intelligence()).
    """
    previous = previous or {}

    previous_status = previous.get("outreach_status") or opportunity.get("outreach_status")
    commercial_readiness = opportunity.get("commercial_readiness")
    outreach_status = advance_outreach_status(previous_status, commercial_readiness)

    merged = dict(opportunity)
    merged["outreach_status"] = outreach_status

    contact = resolve_outreach_contact(merged)
    channel = recommend_outreach_channel(contact)
    message = build_outreach_message(merged, contact) if is_outreach_eligible(merged) else None

    qualification = classify_outreach_qualification(merged)

    return {
        "outreach_status": outreach_status,
        "outreach_qualification_status": qualification,
        "outreach_channel": channel,
        "outreach_contact_type": contact["contact_type"],
        "outreach_contact_reason": contact["reason"],
        "outreach_message_subject": message["subject"] if message else None,
        "outreach_message_body": message["body"] if message else None,
        "follow_up_required": bool(previous.get("follow_up_required", False)),
        "follow_up_reason": previous.get("follow_up_reason"),
        "last_outreach_at": previous.get("last_outreach_at"),
        "outreach_events": list(previous.get("outreach_events") or []),
    }


def apply_outreach_intelligence(
    opportunities: Iterable[Mapping[str, Any]],
    previous_by_number: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """
    Additive pipeline stage: attaches the Phase 8 outreach fields to every
    already-qualified opportunity. Every existing field (including every
    Phase 1-6 field) is preserved unchanged; only the outreach_*/
    follow_up_* keys are added/overwritten.
    """
    previous_by_number = previous_by_number or {}
    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        number = _text(item.get("application_number"))
        previous = previous_by_number.get(number) if number else None
        item.update(build_outreach_intelligence(item, previous))
        results.append(item)

    return results


__all__ = [
    "OUTREACH_STATUS_NEW",
    "OUTREACH_STATUS_QUALIFIED",
    "OUTREACH_STATUS_READY",
    "OUTREACH_STATUS_CONTACTED",
    "OUTREACH_STATUS_REPLIED",
    "OUTREACH_STATUS_ENGAGED",
    "OUTREACH_STATUS_OPPORTUNITY",
    "OUTREACH_STATUS_WON",
    "OUTREACH_STATUS_LOST",
    "EVENT_OUTREACH_PREPARED",
    "EVENT_OUTREACH_SENT",
    "EVENT_RESPONSE_RECEIVED",
    "EVENT_ENGAGED",
    "EVENT_FOLLOW_UP_REQUIRED",
    "EVENT_OPPORTUNITY_CREATED",
    "EVENT_WON",
    "EVENT_LOST",
    "SUPPORTED_EVENTS",
    "QUALIFICATION_NOT_QUALIFIED",
    "QUALIFICATION_QUALIFIED_NOT_CONTACTABLE",
    "QUALIFICATION_READY_FOR_OUTREACH",
    "QUALIFICATION_ALREADY_CONTACTED",
    "QUALIFICATION_ACTIVE_OPPORTUNITY",
    "CONTACT_TYPE_OWNER",
    "CONTACT_TYPE_APPLICANT",
    "CONTACT_TYPE_APPLICANT_OF_RECORD",
    "CONTACT_TYPE_COMPANY",
    "CONTACT_TYPE_NONE",
    "CHANNEL_EMAIL",
    "CHANNEL_PHONE",
    "CHANNEL_NONE",
    "natural_outreach_status",
    "advance_outreach_status",
    "classify_outreach_qualification",
    "is_outreach_eligible",
    "select_outreach_contact_type",
    "resolve_outreach_contact",
    "recommend_outreach_channel",
    "build_outreach_message",
    "apply_outreach_event",
    "build_outreach_intelligence",
    "apply_outreach_intelligence",
]
