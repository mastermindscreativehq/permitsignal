"""
PermitSignal Approval-Action Intelligence (Phase 3)

Purpose
-------
Turn the evidence already extracted earlier in the pipeline -- friction
signals/events (backend.app.analyzers.friction_analyzer), the current
agenda status (backend.app.services.application_extractor.
detect_agenda_status()), and scheduled project dates (backend.app.services.
project_date_extractor) -- into a conservative approval-action
recommendation attached to each canonical opportunity:

    approval_status, approval_action, approval_action_type,
    approval_confidence, approval_basis, approval_relevant_date,
    approval_source, approval_source_type, approval_evidence,
    approval_reason

Design principle
-----------------
This module performs NO new text extraction and interprets NO raw PDF
text. It only reasons over fields the pipeline has already computed, each
of which already carries its own evidence rules (friction_analyzer's
EVENT_RULES + explicit_historical_outcome() boilerplate filtering,
project_date_extractor's LABEL_PRIORITY classification). Every claim
traces back to a real `friction_events` entry, a current-item `status`
marker, or a real `future_project_dates` entry -- never invented from
application_type or generic industry/domain knowledge.

approval_basis distinguishes (CLAUDE.md section on Phase 3 / DEVELOPMENT_
RULES "evidence-first" rule):

    confirmed_requirement          -- explicit government-record evidence
                                       (a denial/withdrawal outcome, or a
                                       scheduled hearing/meeting/council
                                       date with explicit hearing-class
                                       evidence).
    evidence_backed_recommendation -- a real signal exists, but the
                                       specific recommended action is
                                       PermitSignal's own synthesis on top
                                       of it (e.g. "prepare for hearing" X
                                       days before a confirmed date).
    inferred_next_step             -- only weak/indirect evidence exists
                                       (a continuance/concern with no
                                       confirmed next date).
    unknown                        -- insufficient evidence; never guessed.

This module never claims "approved" or "conditionally_approved": no
existing extractor in this pipeline detects an affirmative approval
outcome, and inventing that detection here (e.g. keyword-matching
"approved" in free text) would violate the evidence-first rule ("claim
approval is guaranteed" / "present generic industry knowledge as a
government requirement"). Absence of negative signals is reported as
"scheduled" / "pending" / "unknown", never "approved".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional


# ============================================================================
# VOCABULARY
# ============================================================================

STATUS_UNKNOWN = "unknown"
ACTION_UNKNOWN = "unknown"

BASIS_CONFIRMED = "confirmed_requirement"
BASIS_RECOMMENDATION = "evidence_backed_recommendation"
BASIS_INFERRED = "inferred_next_step"
BASIS_UNKNOWN = "unknown"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

# project_date_extractor.LABEL_PRIORITY vocabulary for a genuine hearing/
# meeting-type event, as opposed to an administrative deadline or a bare
# "approval"/"decision" mention.
HEARING_LABELS = {
    "public_hearing",
    "public_meeting",
    "planning_commission_event",
    "municipal_council_event",
}

# Friction signals in priority order. The first one present in an
# application's friction_signals (or its current agenda `status`, for
# "continued") is the dominant evidence driving the recommendation.
SIGNAL_PRIORITY = [
    "denied",
    "withdrawn",
    "recommended_denial",
    "tabled",
    "continued",
    "staff_concern",
    "additional_information",
    "amended",
    "appeal",
    "neighborhood_concern",
    "public_opposition",
]


@dataclass
class ApprovalAction:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# EVIDENCE LOOKUP HELPERS
# ============================================================================

def _friction_signals(opportunity: Mapping[str, Any]) -> list[str]:
    signals = opportunity.get("friction_signals") or []

    if not isinstance(signals, list):
        return []

    return [str(signal).lower() for signal in signals if signal]


def _current_status_markers(opportunity: Mapping[str, Any]) -> list[str]:
    status = opportunity.get("status") or []

    if isinstance(status, str):
        status = [status]

    if not isinstance(status, list):
        return []

    return [str(item).lower() for item in status if item]


def _friction_events(opportunity: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = (
        opportunity.get("friction_events")
        or opportunity.get("historical_evidence")
        or []
    )

    return [event for event in events if isinstance(event, Mapping)]


def _best_event(
    events: list[dict[str, Any]],
    event_type: str,
) -> Optional[dict[str, Any]]:
    matches = [
        event
        for event in events
        if str(event.get("event_type") or "").lower() == event_type
    ]

    if not matches:
        return None

    matches.sort(
        key=lambda event: (
            event.get("event_date") is not None,
            float(event.get("confidence") or 0),
            len(str(event.get("evidence") or "")),
        ),
        reverse=True,
    )

    return matches[0]


def _matching_future_date(
    opportunity: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    next_date = opportunity.get("next_project_date")

    if not next_date:
        return None

    for candidate in opportunity.get("future_project_dates") or []:
        if isinstance(candidate, Mapping) and candidate.get("value") == next_date:
            return dict(candidate)

    return None


def _dominant_signal(signals: set) -> Optional[str]:
    for signal in SIGNAL_PRIORITY:
        if signal in signals:
            return signal

    return None


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _label_phrase(label: Optional[str]) -> str:
    return str(label or "event").replace("_", " ")


def _confidence_for_days(days: Optional[int]) -> str:
    if days is None:
        return CONFIDENCE_MEDIUM

    if days <= 30:
        return CONFIDENCE_HIGH

    return CONFIDENCE_MEDIUM


def _hearing_action(days: Optional[int]) -> tuple:
    if days is not None and days <= 7:
        return "attend scheduled hearing", "hearing_attendance"

    return "prepare for hearing", "hearing_preparation"


# ============================================================================
# MAIN DECISION ENGINE
# ============================================================================

def build_approval_action(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """
    Derive a single conservative approval-action recommendation for one
    already-built opportunity. Returns only the approval_* fields; callers
    merge them onto the opportunity (see apply_approval_intelligence()).
    """

    source_url = opportunity.get("source_url") or opportunity.get("source")

    signals = set(_friction_signals(opportunity)) | set(
        _current_status_markers(opportunity)
    )

    events = _friction_events(opportunity)

    has_future = bool(opportunity.get("has_future_opportunity"))
    next_event_label = opportunity.get("next_project_event")
    next_date = opportunity.get("next_project_date")
    days = _int_or_none(opportunity.get("days_until_event"))

    has_hearing = has_future and next_event_label in HEARING_LABELS

    dominant = _dominant_signal(signals)

    result = ApprovalAction()

    # ------------------------------------------------------------------
    # DENIED -- terminal outcome, explicit government-record language.
    # ------------------------------------------------------------------
    if dominant == "denied":
        event = _best_event(events, "denied")

        result.approval_status = "denied"
        result.approval_relevant_date = (event or {}).get("event_date")
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"

        if "appeal" in signals:
            appeal_event = _best_event(events, "appeal")

            result.approval_action = "follow up with the responsible department"
            result.approval_action_type = "follow_up"
            result.approval_basis = BASIS_RECOMMENDATION
            result.approval_confidence = CONFIDENCE_MEDIUM

            if appeal_event:
                result.approval_evidence = (
                    appeal_event.get("evidence") or result.approval_evidence
                )
                result.approval_relevant_date = (
                    appeal_event.get("event_date") or result.approval_relevant_date
                )

            result.approval_reason = (
                "Government record confirms the application was denied"
                + (
                    f" on {result.approval_relevant_date}"
                    if result.approval_relevant_date
                    else ""
                )
                + ", and an appeal is referenced in the record; follow up "
                "with the responsible department regarding the appeal status."
            )
        else:
            result.approval_action = "no immediate action identified"
            result.approval_action_type = "none"
            result.approval_basis = BASIS_CONFIRMED
            result.approval_confidence = CONFIDENCE_HIGH
            result.approval_reason = (
                "Government record confirms the application was denied"
                + (
                    f" on {result.approval_relevant_date}"
                    if result.approval_relevant_date
                    else ""
                )
                + "; no further government action is currently on record."
            )

        return result.to_dict()

    # ------------------------------------------------------------------
    # WITHDRAWN
    # ------------------------------------------------------------------
    if dominant == "withdrawn":
        event = _best_event(events, "withdrawn")

        result.approval_status = "withdrawn"
        result.approval_action = "no immediate action identified"
        result.approval_action_type = "none"
        result.approval_basis = BASIS_CONFIRMED
        result.approval_confidence = CONFIDENCE_HIGH
        result.approval_relevant_date = (event or {}).get("event_date")
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"
        result.approval_reason = (
            "Government record indicates the application was withdrawn; "
            "no further action is currently on record."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # RECOMMENDED DENIAL -- staff-level recommendation, not yet final.
    # ------------------------------------------------------------------
    if dominant == "recommended_denial":
        event = _best_event(events, "recommended_denial")

        result.approval_status = "recommended_denial"
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"

        if has_hearing:
            action, action_type = _hearing_action(days)

            result.approval_action = action
            result.approval_action_type = action_type
            result.approval_basis = BASIS_RECOMMENDATION
            result.approval_confidence = _confidence_for_days(days)
            result.approval_relevant_date = next_date
            result.approval_reason = (
                "Staff recommended denial"
                + (
                    f" on {(event or {}).get('event_date')}"
                    if (event or {}).get("event_date")
                    else ""
                )
                + f"; a {_label_phrase(next_event_label)} is scheduled on "
                f"{next_date} where this recommendation will be considered."
            )
        elif has_future:
            result.approval_action = "monitor the next decision"
            result.approval_action_type = "monitoring"
            result.approval_basis = BASIS_RECOMMENDATION
            result.approval_confidence = CONFIDENCE_MEDIUM
            result.approval_relevant_date = next_date
            result.approval_reason = (
                "Staff recommended denial; a future project date is on "
                f"record ({next_date}) but it is not explicitly a "
                "hearing/decision event."
            )
        else:
            result.approval_action = "monitor the next decision"
            result.approval_action_type = "monitoring"
            result.approval_basis = BASIS_INFERRED
            result.approval_confidence = CONFIDENCE_LOW
            result.approval_relevant_date = (event or {}).get("event_date")
            result.approval_reason = (
                "Staff recommended denial; no additional hearing/decision "
                "date is currently on record. Monitor for the next "
                "scheduled action."
            )

        return result.to_dict()

    # ------------------------------------------------------------------
    # TABLED / CONTINUED -- procedural delay.
    # ------------------------------------------------------------------
    if dominant in ("tabled", "continued"):
        event = _best_event(events, dominant)

        result.approval_status = "continued" if dominant == "continued" else "tabled"
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_relevant_date = (event or {}).get("event_date")
        result.approval_source = source_url
        result.approval_source_type = (
            "friction_analysis" if event else "government_record"
        )

        if has_hearing:
            action, action_type = _hearing_action(days)

            result.approval_action = action
            result.approval_action_type = action_type
            result.approval_basis = BASIS_CONFIRMED
            result.approval_confidence = _confidence_for_days(days)
            result.approval_relevant_date = next_date
            result.approval_reason = (
                f"Item was {result.approval_status}; a "
                f"{_label_phrase(next_event_label)} is scheduled on "
                f"{next_date}."
            )
        elif has_future:
            result.approval_action = "monitor the next decision"
            result.approval_action_type = "monitoring"
            result.approval_basis = BASIS_RECOMMENDATION
            result.approval_confidence = CONFIDENCE_MEDIUM
            result.approval_relevant_date = next_date
            result.approval_reason = (
                f"Item was {result.approval_status}; a future project date "
                f"is on record ({next_date}) but it is not explicitly a "
                "hearing/decision event."
            )
        else:
            result.approval_action = "monitor the next decision"
            result.approval_action_type = "monitoring"
            result.approval_basis = BASIS_INFERRED
            result.approval_confidence = CONFIDENCE_LOW
            result.approval_reason = (
                f"Item was {result.approval_status}; no confirmed next "
                "hearing date is currently on record."
            )

        return result.to_dict()

    # ------------------------------------------------------------------
    # STAFF CONCERN -- agency raised a concern with the application.
    # ------------------------------------------------------------------
    if dominant == "staff_concern":
        event = _best_event(events, "staff_concern")

        result.approval_status = "under_review"
        result.approval_action = "respond to agency comments"
        result.approval_action_type = "documentation"
        result.approval_basis = BASIS_RECOMMENDATION
        result.approval_confidence = CONFIDENCE_MEDIUM
        result.approval_relevant_date = (event or {}).get("event_date") or next_date
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"
        result.approval_reason = (
            "Government record notes staff concerns with the application; "
            "respond to the concerns raised by staff."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # ADDITIONAL INFORMATION REQUESTED
    # ------------------------------------------------------------------
    if dominant == "additional_information":
        event = _best_event(events, "additional_information")

        result.approval_status = "under_review"
        result.approval_action = "submit required documentation"
        result.approval_action_type = "documentation"
        result.approval_basis = BASIS_RECOMMENDATION
        result.approval_confidence = CONFIDENCE_MEDIUM
        result.approval_relevant_date = (event or {}).get("event_date") or next_date
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"
        result.approval_reason = (
            "Government record notes that additional information was "
            "requested; submit the requested documentation."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # AMENDED / REVISED APPLICATION
    # ------------------------------------------------------------------
    if dominant == "amended":
        event = _best_event(events, "amended")

        result.approval_status = "under_review"
        result.approval_action = "monitor the next decision"
        result.approval_action_type = "monitoring"
        result.approval_basis = BASIS_RECOMMENDATION
        result.approval_confidence = CONFIDENCE_MEDIUM
        result.approval_relevant_date = (event or {}).get("event_date") or next_date
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"
        result.approval_reason = (
            "Government record indicates the application was "
            "amended/revised; monitor for the next decision on the "
            "amended request."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # APPEAL REFERENCED (without an accompanying denial signal)
    # ------------------------------------------------------------------
    if dominant == "appeal":
        event = _best_event(events, "appeal")

        result.approval_status = "under_review"
        result.approval_action = "follow up with the responsible department"
        result.approval_action_type = "follow_up"
        result.approval_basis = BASIS_RECOMMENDATION
        result.approval_confidence = CONFIDENCE_MEDIUM
        result.approval_relevant_date = (event or {}).get("event_date") or next_date
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"
        result.approval_reason = (
            "Government record references an appeal; follow up with the "
            "responsible department regarding its status."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # NEIGHBORHOOD / PUBLIC OPPOSITION
    # ------------------------------------------------------------------
    if dominant in ("neighborhood_concern", "public_opposition"):
        event = _best_event(events, dominant)

        result.approval_status = "under_review"
        result.approval_evidence = (event or {}).get("evidence")
        result.approval_source = source_url
        result.approval_source_type = "friction_analysis"

        if has_hearing:
            action, action_type = _hearing_action(days)

            result.approval_action = action
            result.approval_action_type = action_type
            result.approval_basis = BASIS_RECOMMENDATION
            result.approval_confidence = CONFIDENCE_MEDIUM
            result.approval_relevant_date = next_date
            result.approval_reason = (
                "Government record notes community opposition/concern; a "
                f"{_label_phrase(next_event_label)} is scheduled on "
                f"{next_date} where this may be addressed."
            )
        else:
            result.approval_action = "monitor the next decision"
            result.approval_action_type = "monitoring"
            result.approval_basis = BASIS_INFERRED
            result.approval_confidence = CONFIDENCE_LOW
            result.approval_relevant_date = (event or {}).get("event_date")
            result.approval_reason = (
                "Government record notes community opposition/concern; no "
                "confirmed next hearing date is currently on record."
            )

        return result.to_dict()

    # ------------------------------------------------------------------
    # NO FRICTION SIGNAL -- rely purely on scheduling evidence.
    # ------------------------------------------------------------------
    if has_hearing:
        date_evidence = _matching_future_date(opportunity)

        if days is not None and days > 30:
            action, action_type = "monitor the next decision", "monitoring"
            confidence = CONFIDENCE_MEDIUM
        else:
            action, action_type = _hearing_action(days)
            confidence = _confidence_for_days(days)

        result.approval_status = "scheduled"
        result.approval_action = action
        result.approval_action_type = action_type
        result.approval_basis = BASIS_CONFIRMED
        result.approval_confidence = confidence
        result.approval_relevant_date = next_date
        result.approval_source = source_url
        result.approval_source_type = "project_date_extraction"
        result.approval_evidence = (date_evidence or {}).get("context")
        result.approval_reason = (
            f"A {_label_phrase(next_event_label)} is scheduled on {next_date}"
            + (
                f" at {opportunity.get('next_project_time')}"
                if opportunity.get("next_project_time")
                else ""
            )
            + "."
        )

        return result.to_dict()

    if has_future:
        date_evidence = _matching_future_date(opportunity)

        result.approval_status = "pending"
        result.approval_action = "monitor the next decision"
        result.approval_action_type = "monitoring"
        result.approval_basis = BASIS_RECOMMENDATION
        result.approval_confidence = CONFIDENCE_MEDIUM
        result.approval_relevant_date = next_date
        result.approval_source = source_url
        result.approval_source_type = "project_date_extraction"
        result.approval_evidence = (date_evidence or {}).get("context")
        result.approval_reason = (
            f"A future project date is on record ({next_date}, "
            f"{_label_phrase(next_event_label)}) but it is not explicitly "
            "a scheduled hearing/meeting."
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # INSUFFICIENT EVIDENCE
    # ------------------------------------------------------------------
    result.approval_status = STATUS_UNKNOWN
    result.approval_action = ACTION_UNKNOWN
    result.approval_action_type = "unknown"
    result.approval_basis = BASIS_UNKNOWN
    result.approval_confidence = None
    result.approval_reason = (
        "No approval-action evidence (friction signal or scheduled "
        "hearing/decision date) was found in the government record for "
        "this application."
    )

    return result.to_dict()


# ============================================================================
# PIPELINE ENTRY POINT
# ============================================================================

def apply_approval_intelligence(
    opportunities: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Additive pipeline stage: attaches approval_* fields to every
    already-built opportunity. Every existing field is preserved
    unchanged; only the ten approval_* keys are added/overwritten.
    """

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        item.update(build_approval_action(item))
        results.append(item)

    return results


__all__ = [
    "ApprovalAction",
    "build_approval_action",
    "apply_approval_intelligence",
    "HEARING_LABELS",
    "SIGNAL_PRIORITY",
    "BASIS_CONFIRMED",
    "BASIS_RECOMMENDATION",
    "BASIS_INFERRED",
    "BASIS_UNKNOWN",
]
