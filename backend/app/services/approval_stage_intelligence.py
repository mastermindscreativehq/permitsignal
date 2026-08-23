"""
Approval & Action Intelligence -- Step 2: ConditionExtractor.

Implements the frozen contract in docs/specs/action_intelligence_contract_v1.md:

- Extracts CONDITIONS (obligations, requirements, gating concerns) from
  government-record text already present on the lead.
- Evidence-first: every condition carries a verbatim evidence_quote and the
  source it came from. Absence of condition language yields an empty list --
  absence is never converted into a condition.
- Deterministic: stable field scan order, dedupe on normalized sentence,
  ids assigned C001.. after sorting.

v1 scope exclusions honored: no prior-cycle linkage, no other components.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

CONTRACT_VERSION = "1.0"

CONDITION_TYPES = (
    "staff_recommendation_condition",
    "code_standard_condition",
    "neighborhood_commitment",
    "procedural_condition",
    "prior_decision_requirement",
)

_CONFIDENCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?\n]+|$)")

_SENTENCE_SPLIT_DOT = "\x00"


def _protect_decimal_periods(text: str) -> str:
    """Mask periods inside numbers (Code 15.05.160) before splitting."""
    return re.sub(r"(?<=\d)\.(?=\d)", _SENTENCE_SPLIT_DOT, text)


def _restore_decimal_periods(text: str) -> str:
    return text.replace(_SENTENCE_SPLIT_DOT, ".")

_CODE_CITE_RE = re.compile(
    r"\b\d{1,2}\.\d{1,2}\.\d+\b|\bTitle\s+\d+\b|\bChapter\s+\d+\b"
    r"|\bSection\s+\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)

_NORMATIVE_RE = re.compile(
    r"subject to|conditioned upon|conditions? of approval|stipulat\w*"
    r"|provided that|required to|will be required|\bmust\b|\bshall\b",
    re.IGNORECASE,
)

_STAFF_RE = re.compile(
    r"staff recommend\w*|recommended denial"
    r"|recommended approval|commission concerned"
    r"|planning commission[^.?!]*(concern\w*|recommend\w*)"
    r"|municipal council[^.?!]*(concern\w*|recommend\w*)",
    re.IGNORECASE,
)

_NEIGHBORHOOD_RE = re.compile(
    r"\bresidents?\b[^.?!]*concern\w*|\bneighborhood\b[^.?!]*concern\w*"
    r"|homeowners? (?:association|objected)",
    re.IGNORECASE,
)

_PROCEDURAL_RE = re.compile(
    r"public hearing|notice of|filing (?:fee|deadline)|application deadline"
    r"|\bdeadline\b|\bsubmit(?:ted|ed)?\b|\battend\w*\b",
    re.IGNORECASE,
)

_PRIOR_DECISION_RE = re.compile(
    r"\bdenied\b|\bdenial\b|approval of this application requires",
    re.IGNORECASE,
)

_TEXT_KEYS = ("evidence_text", "evidence", "matched_text", "text", "quote")


def _clean(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip()


def split_sentences(text: str) -> list[tuple[str, int]]:
    """Split into (sentence, char_offset) pairs; decimal periods protected."""
    masked = _protect_decimal_periods(text)
    sentences: list[tuple[str, int]] = []
    for match in _SENTENCE_RE.finditer(masked):
        raw = _restore_decimal_periods(match.group(0))
        stripped = raw.strip()
        if len(stripped) >= 20:
            pad = len(raw) - len(raw.lstrip())
            sentences.append((stripped, match.start() + pad))
    return sentences


def _classify(sentence: str) -> tuple[Optional[str], str]:
    """
    Return (condition_type, confidence) for a candidate sentence, or
    (None, "NONE") when it carries no condition language at all.
    Classification precedence: code citation > prior-decision language >
    procedural obligation > staff recommendation > neighborhood concern >
    default staff recommendation (generic normative phrasing).
    """
    has_normative = bool(_NORMATIVE_RE.search(sentence))

    if _CODE_CITE_RE.search(sentence):
        return "code_standard_condition", "HIGH" if has_normative else "MEDIUM"
    if _PRIOR_DECISION_RE.search(sentence):
        return "prior_decision_requirement", \
            "HIGH" if has_normative else "MEDIUM"
    if _PROCEDURAL_RE.search(sentence):
        return "procedural_condition", "HIGH" if has_normative else "MEDIUM"
    if _STAFF_RE.search(sentence):
        return "staff_recommendation_condition", \
            "HIGH" if has_normative else "MEDIUM"
    if _NEIGHBORHOOD_RE.search(sentence):
        return "neighborhood_commitment", "HIGH" if has_normative else "MEDIUM"
    if has_normative:
        return "staff_recommendation_condition", "LOW"
    return None, "NONE"


def extract_conditions_from_text(
    text: Any,
    *,
    source_url: Optional[str] = None,
    event_date: Optional[str] = None,
    source_kind: str = "narrative",
) -> list[dict[str, Any]]:
    """
    Pull every condition-bearing sentence out of one block of text.
    Every returned condition carries its verbatim evidence_quote; blocks
    without condition language contribute nothing. Government-record
    provenance lifts any extracted condition to HIGH confidence.
    """
    clean = _clean(text)
    if not clean:
        return []

    found: list[dict[str, Any]] = []
    for sentence, offset in split_sentences(clean):
        cond_type, confidence = _classify(sentence)
        if cond_type is None:
            continue
        if source_kind == "government_record" and confidence != "HIGH":
            confidence = "HIGH"
        found.append({
            "statement": sentence,
            "condition_type": cond_type,
            "evidence_quote": sentence,
            "source_url": source_url,
            "event_date": event_date,
            "source_kind": source_kind,
            "char_offset": offset,
            "confidence": confidence,
        })
    return found


def _iter_lead_text_blocks(lead: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Yield text blocks in deterministic scan order with their provenance:
    description -> approval_evidence -> historical_evidence items ->
    friction_events items.
    """
    blocks: list[dict[str, Any]] = []
    source_url = lead.get("source_url")

    description = _clean(lead.get("description"))
    if description:
        blocks.append({
            "text": description, "order": 0, "source_url": source_url,
            "event_date": None, "source_kind": "government_record",
        })

    approval_evidence = _clean(lead.get("approval_evidence"))
    if approval_evidence:
        blocks.append({
            "text": approval_evidence, "order": 1,
            "source_url": lead.get("approval_source") or source_url,
            "event_date": None, "source_kind": "government_record",
        })

    order = 2
    for item in lead.get("historical_evidence") or []:
        if not isinstance(item, dict):
            continue
        text = next(
            (_clean(item.get(k)) for k in _TEXT_KEYS if _clean(item.get(k))),
            "",
        )
        if text:
            blocks.append({
                "text": text, "order": order,
                "source_url": item.get("source_url") or source_url,
                "event_date": item.get("event_date"),
                "source_kind": "narrative",
            })
            order += 1

    for event in lead.get("friction_events") or []:
        if not isinstance(event, dict):
            continue
        text = next(
            (_clean(event.get(k)) for k in _TEXT_KEYS if _clean(event.get(k))),
            "",
        )
        if text:
            blocks.append({
                "text": text, "order": order,
                "source_url": event.get("source_url") or source_url,
                "event_date": event.get("event_date"),
                "source_kind": "narrative",
            })
            order += 1

    return blocks


def build_conditions(lead: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Contract-shaped conditions[] for one lead: deduped across all text
    fields, deterministically ordered and id-assigned (C001..).
    """
    seen_keys: set[str] = set()
    collected: list[dict[str, Any]] = []

    for block in _iter_lead_text_blocks(lead):
        for cond in extract_conditions_from_text(
            block["text"],
            source_url=block["source_url"],
            event_date=block["event_date"],
            source_kind=block["source_kind"],
        ):
            key = re.sub(r"\s+", " ", cond["statement"].lower()).strip(" .")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            collected.append({
                **cond,
                "order": block["order"],
            })

    collected.sort(key=lambda c: (c["order"], c["char_offset"]))

    conditions: list[dict[str, Any]] = []
    for index, cond in enumerate(collected, start=1):
        conditions.append({
            "condition_id": f"C{index:03d}",
            "statement": cond["statement"],
            "condition_type": cond["condition_type"],
            "evidence_quote": cond["evidence_quote"],
            "source_url": cond["source_url"],
            "event_date": cond["event_date"],
            "subject_hint": None,
            "confidence": cond["confidence"],
        })
    return conditions


# ---------------------------------------------------------------------------
# RequestedActionNormalizer
# ---------------------------------------------------------------------------

REQUESTED_ACTION_TYPES: tuple[str, ...] = (
    "Zone Map Amendment",
    "Concept Plan",
    "Variance",
    "Ordinance Text Amendment",
    "Project Plan",
    "Conditional Use",
    "General Plan Amendment",
    "Subdivision",
    "Other",
    "Unknown",
)

_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("zone map amendment", "rezoning", "rezone"), "Zone Map Amendment"),
    (("concept plan",), "Concept Plan"),
    (("ordinance text amendment", "text amendment"),
     "Ordinance Text Amendment"),
    (("project plan",), "Project Plan"),
    (("conditional use", "conditional-use permit"), "Conditional Use"),
    (("general plan amendment", "general plan"), "General Plan Amendment"),
    (("variance",), "Variance"),
    (("subdivision", "plat approval", "final plat", "preliminary plat"),
     "Subdivision"),
)

_REQUEST_SIGNAL_RE = re.compile(
    r"\b(?:request(?:ing|ed)?|propos(?:al|ing)|application)\b",
    re.IGNORECASE,
)

_ZONE_FROM_RE = re.compile(
    r"from the\s+(.+?)\s*(?:\([^)]*\)\s*)?Zone\b", re.IGNORECASE
)
_ZONE_TO_RE = re.compile(
    r"to the\s+(.+?)\s*(?:\([^)]*\)\s*)?Zone\b", re.IGNORECASE
)

_UNITS_RE = re.compile(
    r"\b(\d+)\s+(?:townhomes?|single[- ]family homes?|dwelling units?"
    r"|residential units?|apartment units?|flex office development units?"
    r"|units?|lots?)\b",
    re.IGNORECASE,
)

_USE_LABELS: tuple[tuple[str, str], ...] = (
    ("mixed_use", r"mixed[- ]use"),
    ("townhomes", r"townhomes?"),
    ("commercial", r"commercial space"),
    ("live_work", r"live/work"),
    ("single_family", r"single[- ]family"),
    ("apartments", r"apartments?\b"),
    ("duplexes", r"duplex(?:es)?\b"),
    ("office", r"\boffice\b"),
    ("retail", r"\bretail\b"),
    ("industrial", r"\bindustrial\b"),
)


def _resolve_action_type(lead: dict[str, Any]) -> tuple[Optional[str], bool]:
    """
    Return (action_type, is_exact_vocabulary). Exact vocabulary means the
    application_type field itself names a REQUESTED-ACTION-TYPE; otherwise
    the type is keyword-derived from the government-record description.
    """
    raw_type = _clean(lead.get("application_type"))
    for candidate in REQUESTED_ACTION_TYPES:
        if raw_type and raw_type.lower() == candidate.lower():
            return candidate, True

    text = (_clean(lead.get("description"))
            or _clean(lead.get("project_description")) or "").lower()
    for patterns, label in _TYPE_KEYWORDS:
        if any(pattern in text for pattern in patterns):
            return label, False
    return None, False


def _normalize_zone_pair(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract explicit from/to zone tokens; both required or both null."""
    from_match = _ZONE_FROM_RE.search(text)
    to_match = _ZONE_TO_RE.search(text)
    if not from_match or not to_match or from_match.end() > to_match.start():
        return None, None
    return from_match.group(1).strip(), to_match.group(1).strip()


def _extract_scope(text: str) -> dict[str, Any]:
    units_match = _UNITS_RE.search(text)
    use_mix = sorted({
        label for label, pattern in _USE_LABELS
        if re.search(pattern, text, re.IGNORECASE)
    })
    return {
        "units": int(units_match.group(1)) if units_match else None,
        "use_mix": use_mix,
        "notes": None,
    }


def _pick_request_quote(
    text: str,
    *,
    action_type: Optional[str],
    has_zone_pair: bool,
    from_span: Optional[tuple[int, int]],
    to_span: Optional[tuple[int, int]],
) -> Optional[str]:
    """
    Choose one verbatim sentence as the request evidence: prefer the
    sentence carrying the zone pair, then the sentence naming the action
    type, then the first request-bearing sentence.
    """
    sentences = split_sentences(text)
    if not sentences:
        return None
    lowered = [(sentence, sentence.lower(), offset) for sentence, offset in sentences]

    if has_zone_pair and from_span is not None and to_span is not None:
        for sentence, _, offset in lowered:
            start = offset
            end = offset + len(sentence)
            if start <= from_span[0] and end >= to_span[1]:
                return sentence
    if action_type and action_type != "Other":
        needle = action_type.lower()
        for sentence, low, _ in lowered:
            if needle in low:
                return sentence
    for sentence, low, _ in lowered:
        if _REQUEST_SIGNAL_RE.search(low) or "zone" in low:
            return sentence
    return None


def build_requested_action(lead: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize what the applicant actually requested into the frozen
    Action Intelligence contract shape. Evidence-first: every populated
    value traces to the government-record description or application_type;
    absence yields Unknown/NONE rather than inference.
    """
    description = (_clean(lead.get("description"))
                   or _clean(lead.get("project_description")) or None)

    action_type, is_exact = _resolve_action_type(lead)
    from_state = to_state = None
    from_span = to_span = None
    scope: dict[str, Any] = {"units": None, "use_mix": [], "notes": None}
    evidence_quote: Optional[str] = None

    if description:
        from_match = _ZONE_FROM_RE.search(description)
        to_match = _ZONE_TO_RE.search(description)
        from_state, to_state = _normalize_zone_pair(description)
        if from_state is not None:
            from_span, to_span = from_match.span(), to_match.span()
        scope = _extract_scope(description)

        request_signal = (
            action_type is not None
            or from_state is not None
            or _REQUEST_SIGNAL_RE.search(description) is not None
        )
        if request_signal:
            evidence_quote = _pick_request_quote(
                description,
                action_type=action_type,
                has_zone_pair=from_state is not None,
                from_span=from_span,
                to_span=to_span,
            )

    if action_type is None:
        if description is None:
            action_type = "Unknown"
            confidence = "NONE"
        elif evidence_quote is None:
            confidence = "LOW"
            action_type = "Unknown"
        else:
            confidence = "MEDIUM"
            action_type = "Other"
    elif is_exact or from_state is not None:
        confidence = "HIGH"
    else:
        confidence = "MEDIUM"

    return {
        "action_type": action_type,
        "from_state": from_state,
        "to_state": to_state,
        "scope": scope,
        "evidence_quote": evidence_quote,
        "source_url": _clean(lead.get("source_url")) or None,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# DecisionStageResolver
# ---------------------------------------------------------------------------

DECISION_STAGES: tuple[str, ...] = (
    "pre_submission",
    "under_staff_review",
    "scheduled_public_hearing",
    "in_hearing_process",
    "approved_pending_conditions",
    "approved",
    "denied_appeal_window",
    "denied_current_application",
    "withdrawn",
    "unknown",
)

_APPEAL_MARKER_RE = re.compile(r"\bappeal\w*\b", re.IGNORECASE)
_CONTINUED_MARKER_RE = re.compile(
    r"\bcontinu(?:ed|ance)\b|\btabled\b|\bheld over\b", re.IGNORECASE
)
_STAFF_REVIEW_MARKER_RE = re.compile(
    r"staff (?:review|report|evaluation|analysis)|under review",
    re.IGNORECASE,
)
_PRE_SUBMISSION_MARKER_RE = re.compile(
    r"pre[- ]application|will submit|intend(?:s)? to apply"
    r"|not yet submitted",
    re.IGNORECASE,
)
_CONDITIONS_MARKER_RE = re.compile(
    r"subject to (?:the )?(?:following )?conditions"
    r"|conditions of approval",
    re.IGNORECASE,
)

_HEARING_BODY_TOKENS = (
    "planning_commission", "municipal_council", "board_of_adjustment",
    "hearing",
)


def _parse_iso_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _marker_sentence(blocks: list[dict[str, Any]],
                     marker_re: re.Pattern) -> Optional[str]:
    """First sentence (verbatim) matching a stage marker, or None."""
    for block in blocks:
        for sentence, _ in split_sentences(block["text"]):
            if marker_re.search(sentence):
                return sentence
    return None


def build_decision_stage(
    lead: dict[str, Any],
    *,
    reference_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Resolve one canonical decision stage from government-record evidence,
    walking a fixed precedence ladder. Insufficient evidence resolves to
    "unknown" rather than a guess; every resolution names its sources.

    Ladder (first match wins):
      1. withdrawal            (terminal status / friction signal)
      2. approved | approved_pending_conditions (terminal status)
      3. scheduled event       (future government-record project event;
                                a denial signal coexisting with a future
                                event is classified as prior-cycle history)
      4. denied_appeal_window | denied_current_application
      5. under_staff_review    (marker text, no event/status)
      6. pre_submission        (marker text only)
      7. unknown               (insufficient evidence)
    """
    ref = (_parse_iso_date(reference_date) if reference_date
           else date.today())
    ref_iso = ref.isoformat() if ref else None

    status = (_clean(lead.get("approval_status")) or "").lower()
    event_label = _clean(lead.get("next_project_event")) or ""
    event_date = _parse_iso_date(lead.get("next_project_date"))
    event_stale = bool(event_date and ref and event_date < ref)
    future_event = bool((event_label or lead.get("next_project_date"))
                        and not event_stale)

    blocks = _iter_lead_text_blocks(lead)
    corpus = " ".join(block["text"] for block in blocks)

    stale_notes: list[str] = []
    if event_stale:
        stale_notes.append(
            f"recorded project date {event_date.isoformat()} precedes "
            f"reference date {ref_iso}"
        )

    friction_signals = [
        str(signal).lower() for signal in (lead.get("friction_signals") or [])
        if isinstance(signal, str)
    ]
    denial_flavored = status == "denied" or any(
        token in signal for signal in friction_signals
        for token in ("denied", "denial")
    )

    def result(stage: str,
               confidence: str,
               source_fields: list[str],
               rationale: str,
               *,
               quote: Optional[str] = None,
               superseded: Optional[list[str]] = None) -> dict[str, Any]:
        return {
            "decision_stage": stage,
            "confidence": confidence,
            "source_fields": source_fields,
            "evidence_quote": quote,
            "rationale": rationale,
            "superseded_signals": superseded or [],
            "reference_date_used": ref_iso,
        }

    # 1. withdrawal -----------------------------------------------------
    if status == "withdrawn" or "withdrawn" in friction_signals:
        return result(
            "withdrawn", "HIGH",
            ["approval_status"] if status == "withdrawn"
            else ["friction_signals"],
            "Withdrawal recorded in government-record status.",
        )

    # 2. terminal approval ----------------------------------------------
    if status == "approved":
        conditions_marker = bool(build_conditions(lead)) \
            or bool(_CONDITIONS_MARKER_RE.search(corpus))
        if conditions_marker:
            quote = _marker_sentence(blocks, _CONDITIONS_MARKER_RE)
            return result(
                "approved_pending_conditions", "HIGH",
                ["approval_status"],
                "Approved with condition language present in the record.",
                quote=quote,
            )
        return result(
            "approved", "HIGH", ["approval_status"],
            "Terminal approval recorded without condition language.",
        )

    # 3. future scheduled event -----------------------------------------
    if future_event:
        label = event_label.lower()
        is_hearing = ("hearing" in label
                      or any(token in label for token in _HEARING_BODY_TOKENS))
        continued_quote = _marker_sentence(blocks, _CONTINUED_MARKER_RE)
        superseded: list[str] = list(stale_notes)
        if denial_flavored:
            superseded.append(
                "denial signals classified as prior-cycle history because a "
                "future government-record project event is scheduled"
            )
        if event_stale:
            superseded.extend(
                note for note in (
                    f"recorded project date {event_date.isoformat()} precedes "
                    f"reference date {ref_iso}"
                ) if note not in superseded
            )
        if continued_quote and is_hearing:
            return result(
                "in_hearing_process", "MEDIUM",
                ["next_project_event", "next_project_date"],
                "Continued/tabled item carried into a scheduled session.",
                quote=continued_quote,
                superseded=superseded,
            )
        if is_hearing:
            return result(
                "scheduled_public_hearing", "HIGH",
                ["next_project_event", "next_project_date"],
                "Future public-hearing body event on the government record.",
                superseded=superseded,
            )
        return result(
            "in_hearing_process", "MEDIUM",
            ["next_project_event", "next_project_date"],
            "Future non-hearing project event on the government record.",
            superseded=superseded,
        )

    # 4. current-application denial --------------------------------------
    if status == "denied":
        appeal_quote = _marker_sentence(blocks, _APPEAL_MARKER_RE)
        if appeal_quote:
            return result(
                "denied_appeal_window", "MEDIUM", ["approval_status"],
                "Denial recorded and appeal language present in the record.",
                quote=appeal_quote,
                superseded=stale_notes,
            )
        return result(
            "denied_current_application", "HIGH", ["approval_status"],
            "Denial recorded with no future event to reclassify it.",
            superseded=stale_notes,
        )
    if denial_flavored:
        return result(
            "denied_current_application", "MEDIUM",
            ["friction_signals"],
            "Denial derived from recorded friction signals alone.",
            superseded=stale_notes,
        )

    # 5. staff review ----------------------------------------------------
    staff_quote = _marker_sentence(blocks, _STAFF_REVIEW_MARKER_RE)
    if staff_quote:
        return result(
            "under_staff_review", "MEDIUM", [],
            "Staff-review language present without a scheduled event.",
            quote=staff_quote,
            superseded=stale_notes,
        )

    # 6. pre-submission ---------------------------------------------------
    pre_quote = _marker_sentence(blocks, _PRE_SUBMISSION_MARKER_RE)
    if pre_quote:
        return result(
            "pre_submission", "LOW", [],
            "Pre-submission language present; nothing yet on file.",
            quote=pre_quote,
            superseded=stale_notes,
        )

    # 7. insufficient evidence --------------------------------------------
    return result(
        "unknown", "NONE", [],
        "Insufficient evidence to resolve a decision stage.",
    )


# ---------------------------------------------------------------------------
# BlockerActionMapper
# ---------------------------------------------------------------------------

BLOCKER_TYPES: tuple[str, ...] = (
    "prior_denial_history",
    "unresolved_staff_concern",
    "neighborhood_opposition_risk",
    "code_compliance_requirement",
    "procedural_deadline",
    "missing_contact_information",
)

ACTION_CATEGORIES: tuple[str, ...] = (
    "hearing_preparation",
    "appeal_filing",
    "resubmission_prep",
    "condition_resolution",
    "documentation_prep",
    "stakeholder_engagement",
    "contact_enrichment",
    "monitoring_only",
)

_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_CONFIDENCE_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

_CONDITION_TYPE_TO_BLOCKER = {
    "staff_recommendation_condition": "unresolved_staff_concern",
    "neighborhood_commitment": "neighborhood_opposition_risk",
    "code_standard_condition": "code_compliance_requirement",
    "procedural_condition": "procedural_deadline",
}

_DENIAL_QUOTE_RE = re.compile(r"\bdenied\b|\bdenial\b", re.IGNORECASE)


def _denial_evidence_sentence(lead: dict[str, Any]) -> Optional[str]:
    """First verbatim narrative sentence recording a denial, or None."""
    for block in _iter_lead_text_blocks(lead):
        if block.get("source_kind") != "narrative":
            continue
        for sentence, _ in split_sentences(block["text"]):
            if _DENIAL_QUOTE_RE.search(sentence):
                return sentence
    return None


def _has_any_contact(lead: dict[str, Any]) -> bool:
    return any(
        _clean(lead.get(key))
        for key in ("applicant_email", "applicant_phone",
                    "contact_email", "contact_phone", "contact_name")
    )


def map_blockers_and_actions(
    lead: dict[str, Any],
    *,
    reference_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Identify blockers strictly from recorded evidence (extracted
    conditions, friction history, decision-stage resolution, contact
    fields) and map each to deterministic recommended actions. Nothing
    is invented: an empty evidence set yields an empty blocker list and
    a single explicit monitoring_only placeholder action.
    """
    conditions = build_conditions(lead)
    stage_info = build_decision_stage(lead, reference_date=reference_date)
    stage = stage_info["decision_stage"]

    raw_blockers: list[dict[str, Any]] = []

    friction_signals = [
        str(signal).lower() for signal in (lead.get("friction_signals") or [])
        if isinstance(signal, str)
    ]
    has_denial_evidence = (
        bool(stage_info["superseded_signals"])
        or any("denied" in s or "denial" in s for s in friction_signals)
        or stage == "denied_current_application"
    )
    if has_denial_evidence:
        try:
            score = int(lead.get("friction_score") or 0)
        except (TypeError, ValueError):
            score = 0
        raw_blockers.append({
            "blocker_type": "prior_denial_history",
            "description": "Recorded prior-cycle denial history on file.",
            "evidence_quote": _denial_evidence_sentence(lead),
            "source_url": _clean(lead.get("source_url")) or None,
            "severity": "HIGH" if score >= 80 else "MEDIUM",
            "confidence": "HIGH" if friction_signals else "MEDIUM",
            "_condition_ids": [],
        })

    condition_links: dict[str, list[dict[str, Any]]] = {}
    for cond in conditions:
        blocker_type = _CONDITION_TYPE_TO_BLOCKER.get(cond["condition_type"])
        if blocker_type is None:
            continue
        condition_links.setdefault(blocker_type, []).append(cond)

    base_severity = {
        "unresolved_staff_concern": "HIGH",
        "neighborhood_opposition_risk": "MEDIUM",
        "code_compliance_requirement": "MEDIUM",
        "procedural_deadline": "MEDIUM",
    }
    for blocker_type, linked in condition_links.items():
        top_confidence = max(linked,
                             key=lambda c: _CONFIDENCE_RANK[c["confidence"]])
        severity = base_severity[blocker_type]
        if severity == "HIGH" and top_confidence["confidence"] != "HIGH":
            severity = "MEDIUM"
        anchor = linked[0]
        raw_blockers.append({
            "blocker_type": blocker_type,
            "description":
                f"{len(linked)} recorded condition(s) require attention.",
            "evidence_quote": anchor["evidence_quote"],
            "source_url": anchor["source_url"],
            "severity": severity,
            "confidence": top_confidence["confidence"],
            "_condition_ids": [c["condition_id"] for c in linked],
        })

    lead_identified = bool(_clean(lead.get("application_number"))
                           or _clean(lead.get("applicant_name")))
    if lead_identified and not _has_any_contact(lead):
        raw_blockers.append({
            "blocker_type": "missing_contact_information",
            "description":
                "No public applicant/staff contact information on record.",
            "evidence_quote": None,
            "source_url": _clean(lead.get("source_url")) or None,
            "severity": "LOW",
            "confidence": "HIGH",
            "_condition_ids": [],
        })

    raw_blockers.sort(key=lambda b: (_SEVERITY_RANK[b["severity"]],
                                     b["blocker_type"]))
    blockers: list[dict[str, Any]] = []
    ids_by_type: dict[str, str] = {}
    for index, item in enumerate(raw_blockers, start=1):
        blocker_id = f"B{index:03d}"
        ids_by_type[item["blocker_type"]] = blocker_id
        blockers.append({
            "blocker_id": blocker_id,
            "blocker_type": item["blocker_type"],
            "description": item["description"],
            "evidence_quote": item["evidence_quote"],
            "source_url": item["source_url"],
            "severity": item["severity"],
            "confidence": item["confidence"],
            "related_condition_ids": item["_condition_ids"],
        })

    due_reference = _clean(lead.get("next_project_date")) or None
    raw_actions: list[dict[str, Any]] = []

    if "prior_denial_history" in ids_by_type \
            and stage == "scheduled_public_hearing":
        denial = blockers[[_b["blocker_type"] for _b in blockers]
                          .index("prior_denial_history")]
        raw_actions.append({
            "category": "hearing_preparation",
            "title": "Prepare hearing response addressing prior-cycle "
                     "denial.",
            "detail": denial["description"],
            "related_blocker_ids": [denial["blocker_id"]],
            "evidence_quote": denial["evidence_quote"],
            "confidence": denial["confidence"],
        })

    if stage == "denied_appeal_window":
        raw_actions.append({
            "category": "appeal_filing",
            "title": "Evaluate and file appeal within the recorded window.",
            "detail": stage_info["rationale"],
            "related_blocker_ids": [],
            "evidence_quote": stage_info["evidence_quote"],
            "confidence": stage_info["confidence"],
        })

    if stage == "denied_current_application":
        raw_actions.append({
            "category": "resubmission_prep",
            "title": "Prepare resubmission addressing recorded denial "
                     "grounds.",
            "detail": stage_info["rationale"],
            "related_blocker_ids": [],
            "evidence_quote": stage_info["evidence_quote"],
            "confidence": stage_info["confidence"],
        })

    if "unresolved_staff_concern" in ids_by_type:
        staff_b = blockers[[_b["blocker_type"] for _b in blockers]
                           .index("unresolved_staff_concern")]
        raw_actions.append({
            "category": "documentation_prep",
            "title": "Draft written responses to recorded staff conditions.",
            "detail": ", ".join(staff_b["related_condition_ids"]),
            "related_blocker_ids": [staff_b["blocker_id"]],
            "evidence_quote": staff_b["evidence_quote"],
            "confidence": staff_b["confidence"],
        })

    for cond_blocker_type, category in (
        ("code_compliance_requirement", "condition_resolution"),
        ("procedural_deadline", "condition_resolution"),
        ("neighborhood_opposition_risk", "stakeholder_engagement"),
    ):
        if cond_blocker_type in ids_by_type:
            blocker = blockers[[_b["blocker_type"] for _b in blockers]
                               .index(cond_blocker_type)]
            titles = {
                "condition_resolution":
                    "Resolve recorded code/procedural conditions on file.",
                "stakeholder_engagement":
                    "Engage neighborhood stakeholders on recorded concerns.",
            }
            raw_actions.append({
                "category": category,
                "title": titles[category],
                "detail": ", ".join(blocker["related_condition_ids"]),
                "related_blocker_ids": [blocker["blocker_id"]],
                "evidence_quote": blocker["evidence_quote"],
                "confidence": blocker["confidence"],
            })

    if "missing_contact_information" in ids_by_type:
        contact_b = blockers[[_b["blocker_type"] for _b in blockers]
                             .index("missing_contact_information")]
        raw_actions.append({
            "category": "contact_enrichment",
            "title": "Resolve public applicant/staff contact information.",
            "detail": contact_b["description"],
            "related_blocker_ids": [contact_b["blocker_id"]],
            "evidence_quote": None,
            "confidence": "HIGH",
        })

    if not raw_actions:
        raw_actions.append({
            "category": "monitoring_only",
            "title": "No mapped action from current evidence; continue "
                     "monitoring the record.",
            "detail": None,
            "related_blocker_ids": [],
            "evidence_quote": None,
            "confidence": "NONE",
        })

    category_rank = {name: rank for rank, name
                     in enumerate(ACTION_CATEGORIES)}
    raw_actions.sort(key=lambda a: (category_rank[a["category"]],
                                    a["title"]))
    actions: list[dict[str, Any]] = []
    for index, action in enumerate(raw_actions, start=1):
        actions.append({
            "action_id": f"A{index:03d}",
            "category": action["category"],
            "title": action["title"],
            "detail": action["detail"],
            "due_reference": due_reference,
            "related_blocker_ids": action["related_blocker_ids"],
            "evidence_quote": action["evidence_quote"],
            "confidence": action["confidence"],
        })

    return {"blockers": blockers, "actions": actions}


__all__ = [
    "ACTION_CATEGORIES",
    "BLOCKER_TYPES",
    "CONTRACT_VERSION",
    "CONDITION_TYPES",
    "DECISION_STAGES",
    "REQUESTED_ACTION_TYPES",
    "build_conditions",
    "build_decision_stage",
    "build_requested_action",
    "extract_conditions_from_text",
    "map_blockers_and_actions",
    "split_sentences",
]
