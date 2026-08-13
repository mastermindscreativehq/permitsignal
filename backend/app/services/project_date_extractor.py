"""
PERMITSIGNAL PROJECT DATE EXTRACTOR
===================================

Complete production implementation.

Key rules:
1. Dates are compared against a supplied reference date.
2. Future dates are opportunities; historical dates are context only.
3. A single calendar date produces ONE ProjectDate record.
4. Event classification is resolved at DATE level so nearby agenda text
   cannot create duplicate/conflicting records.
5. Explicit "public hearing" evidence has priority over generic council
   language for the same date.
6. Explicit Municipal Council dates remain municipal_council_event.
7. Event times are normalized to "6:00 PM" format.
8. The next project event is always the earliest FUTURE date.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import re
from typing import Optional


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

DATE_RE = re.compile(
    r"\b(?:"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\b",
    re.IGNORECASE,
)


@dataclass
class ProjectDate:
    value: str
    date_type: str
    label: str
    is_future: bool
    score: int
    confidence: float
    context: str
    time: Optional[str] = None
    application_number: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()

    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return datetime.strptime(raw, "%Y-%m-%d").date()

        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw):
            return datetime.strptime(raw, "%m/%d/%Y").date()

        match = re.fullmatch(
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",
            raw,
        )

        if match:
            return date(
                int(match.group(3)),
                MONTHS[match.group(1).lower()],
                int(match.group(2)),
            )

    except (ValueError, KeyError):
        return None

    return None


def _normalize_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    match = TIME_RE.search(value)

    if not match:
        return None

    hour = int(match.group(1))
    minute = match.group(2)
    meridiem = match.group(3).upper()

    return f"{hour}:{minute} {meridiem}"


# ---------------------------------------------------------------------------
# CONTEXT
# ---------------------------------------------------------------------------

def _line_bounds(text: str, position: int) -> tuple[int, int]:
    """
    PDF extraction often destroys sentence boundaries. Lines remain a more
    reliable local boundary than treating an entire page as one sentence.
    """

    left = text.rfind("\n", 0, position)
    right = text.find("\n", position)

    if left == -1:
        left = 0
    else:
        left += 1

    if right == -1:
        right = len(text)

    return left, right


def _sentence_bounds(text: str, position: int) -> tuple[int, int]:
    separators = ".!?;\n"

    left = position
    while left > 0 and text[left - 1] not in separators:
        left -= 1

    right = position
    while right < len(text) and text[right] not in separators:
        right += 1

    return left, min(len(text), right + 1)


def _event_sentence(
    text: str,
    start: int,
    end: int,
) -> str:
    sentence_start, sentence_end = _sentence_bounds(
        text,
        start,
    )
    return _clean(text[sentence_start:sentence_end])


def _local_context(
    text: str,
    start: int,
    end: int,
    radius: int = 220,
) -> str:
    sentence_start, sentence_end = _sentence_bounds(
        text,
        start,
    )

    local_start = max(0, sentence_start - radius)
    local_end = min(len(text), sentence_end + radius)

    return _clean(text[local_start:local_end])


def _nearby_time(
    text: str,
    start: int,
    end: int,
    max_distance: int = 160,
) -> Optional[str]:
    """
    Prefer a time after the date:

        August 12, 2026 at 6:00 PM

    Then check a smaller backwards window.
    """

    forward = text[end:min(len(text), end + max_distance)]

    match = TIME_RE.search(forward)

    if match:
        return _normalize_time(match.group(0))

    backward_start = max(0, start - 90)
    backward = text[backward_start:start]

    matches = list(TIME_RE.finditer(backward))

    if matches:
        return _normalize_time(matches[-1].group(0))

    return None


# ---------------------------------------------------------------------------
# EVIDENCE
# ---------------------------------------------------------------------------

LABEL_PRIORITY = {
    # Highest priority: explicit event semantics.
    "public_hearing": 100,
    "public_meeting": 95,
    "municipal_council_event": 90,
    "planning_commission_event": 80,
    "public_comment_deadline": 75,
    "appeal_deadline": 70,
    "deadline": 65,
    "approval_event": 60,
    "decision_event": 55,
    "future_project_event": 40,
    "historical_denial": 30,
    "historical_event": 10,
}


def _classify_context(
    context: str,
    sentence: str,
    is_future: bool,
) -> str:
    """
    Classify the local evidence.

    IMPORTANT:
    "public hearing" is checked before generic council language.
    This prevents the surrounding September council sentence from
    hijacking the August 12 hearing.
    """

    s = sentence.lower()
    c = context.lower()

    # Administrative deadlines/reference dates must be classified before
    # broader surrounding-event language. A deadline can sit inside a
    # context window that also contains a public hearing or council event.
    # The date itself must not inherit that unrelated event.
    if (
        "day before" in s
        or "day-before" in s
        or "prior to" in s
        or "deadline" in s
        or "must be submitted before" in s
        or "comments must be submitted" in s
        or "public comments must be submitted" in s
    ):
        return "deadline"

    if (
        "day before" in c
        or "day-before" in c
        or "prior to" in c
    ) and not ("public hearing on" in s or "will hold a public hearing" in s):
        return "deadline"

    # Exact sentence evidence first.
    if "public hearing" in s:
        return "public_hearing"

    if "public meeting" in s:
        return "public_meeting"

    if "municipal council" in s or "city council" in s:
        return "municipal_council_event"

    if "planning commission" in s:
        return "planning_commission_event"

    if "public comment" in s:
        return "public_comment_deadline"

    if "appeal" in s and "deadline" in s:
        return "appeal_deadline"

    if "deadline" in s:
        return "deadline"

    if "approval" in s:
        return "approval_event"

    if "decision" in s:
        return "decision_event"

    # Local context second.
    if "public hearing" in c:
        return "public_hearing"

    if "public meeting" in c:
        return "public_meeting"

    if "municipal council" in c or "city council" in c:
        return "municipal_council_event"

    if "planning commission" in c:
        return "planning_commission_event"

    if "public comment" in c:
        return "public_comment_deadline"

    if "appeal" in c and "deadline" in c:
        return "appeal_deadline"

    if "deadline" in c:
        return "deadline"

    if "approval" in c and is_future:
        return "approval_event"

    if "decision" in c and is_future:
        return "decision_event"

    # Historical classification.
    if (
        "recommended denial" in s
        or "ultimately denied" in s
        or "was denied" in s
        or "denied by" in s
    ):
        return "historical_denial"

    if not is_future:
        if (
            "recommended denial" in c
            or "ultimately denied" in c
            or "was denied" in c
            or "denied by" in c
        ):
            return "historical_denial"

        return "historical_event"

    return "future_project_event"


def _score(
    context: str,
    sentence: str,
    is_future: bool,
    label: str,
) -> int:
    """
    Evidence score.

    The score is deliberately secondary to date/event classification.
    It should not be allowed to change which semantic event owns a date.
    """

    s = sentence.lower()
    c = context.lower()

    score = 20 if is_future else 0

    weights = {
        "public hearing": 30,
        "public meeting": 26,
        "municipal council": 28,
        "city council": 26,
        "planning commission": 24,
        "public comment": 20,
        "appeal": 18,
        "deadline": 18,
        "will hold": 16,
        "will consider": 16,
        "scheduled": 14,
        "approval": 12,
        "decision": 12,
        "recommended denial": 20,
        "ultimately denied": 25,
        "denied by": 25,
    }

    for term, weight in weights.items():
        if term in s:
            score += weight * 2
        elif term in c:
            score += weight

    score += LABEL_PRIORITY.get(label, 0) // 10

    return score


# ---------------------------------------------------------------------------
# RAW DATE OCCURRENCES
# ---------------------------------------------------------------------------

@dataclass
class _DateOccurrence:
    parsed: date
    is_future: bool
    sentence: str
    context: str
    label: str
    score: int
    time: Optional[str]
    position: int


def _extract_occurrences(
    text: str,
    reference_date: date,
) -> list[_DateOccurrence]:

    occurrences: list[_DateOccurrence] = []

    for match in DATE_RE.finditer(text):
        parsed = _parse_date(match.group())

        if parsed is None:
            continue

        is_future = parsed > reference_date

        sentence = _event_sentence(
            text,
            match.start(),
            match.end(),
        )

        context = _local_context(
            text,
            match.start(),
            match.end(),
        )

        label = _classify_context(
            context,
            sentence,
            is_future,
        )

        score = _score(
            context,
            sentence,
            is_future,
            label,
        )

        time = _nearby_time(
            text,
            match.start(),
            match.end(),
        )

        occurrences.append(
            _DateOccurrence(
                parsed=parsed,
                is_future=is_future,
                sentence=sentence,
                context=context,
                label=label,
                score=score,
                time=time,
                position=match.start(),
            )
        )

    return occurrences


# ---------------------------------------------------------------------------
# DATE-LEVEL RESOLUTION
# ---------------------------------------------------------------------------

def _resolve_date_group(
    occurrences: list[_DateOccurrence],
    application_number: Optional[str],
) -> ProjectDate:
    """
    Collapse every occurrence of the same calendar date into ONE event.

    Why this matters:

        August 12, 2026

    may appear in:
        - the agenda heading;
        - the public-hearing notice;
        - item descriptions.

    We must not emit three separate "events".

    We choose the semantic label using explicit evidence priority.
    """

    occurrences = sorted(
        occurrences,
        key=lambda x: (
            LABEL_PRIORITY.get(x.label, 0),
            x.score,
            x.time is not None,
        ),
        reverse=True,
    )

    best = occurrences[0]

    # A date may have one occurrence without a time and another with a time.
    # Always preserve a time if ANY occurrence has one.
    chosen_time = next(
        (
            occurrence.time
            for occurrence in occurrences
            if occurrence.time
        ),
        None,
    )

    # Prefer the richest context.
    richest_context = max(
        (x.context for x in occurrences),
        key=len,
        default=best.context,
    )

    # Boost score when explicit semantic evidence exists in another
    # occurrence of the same date.
    final_score = max(
        occurrence.score
        for occurrence in occurrences
    )

    confidence = min(
        0.99,
        max(
            0.50,
            0.55 + final_score / 250,
        ),
    )

    return ProjectDate(
        value=best.parsed.isoformat(),
        date_type=(
            "future_event"
            if best.is_future
            else "historical"
        ),
        label=best.label,
        is_future=best.is_future,
        score=final_score,
        confidence=round(confidence, 2),
        context=richest_context,
        time=_normalize_time(chosen_time),
        application_number=application_number,
    )


# ---------------------------------------------------------------------------
# PUBLIC EXTRACTION API
# ---------------------------------------------------------------------------

def extract_project_dates(
    text: str,
    reference_date: Optional[date] = None,
    application_number: Optional[str] = None,
) -> list[ProjectDate]:
    """
    Extract one ProjectDate per unique calendar date.
    """

    reference_date = reference_date or date.today()

    occurrences = _extract_occurrences(
        text,
        reference_date,
    )

    grouped: dict[str, list[_DateOccurrence]] = {}

    for occurrence in occurrences:
        key = occurrence.parsed.isoformat()
        grouped.setdefault(key, []).append(occurrence)

    results = [
        _resolve_date_group(
            group,
            application_number,
        )
        for group in grouped.values()
    ]

    # Chronological order, future dates first.
    results.sort(
        key=lambda item: (
            not item.is_future,
            item.value,
        )
    )

    return results


def future_project_dates(
    text: str,
    reference_date: Optional[date] = None,
    application_number: Optional[str] = None,
) -> list[ProjectDate]:

    # Only actual project/event dates belong in the live opportunity stream.
    # Administrative deadlines remain available through extract_project_dates
    # for auditability but cannot become next_project_date.
    non_project_labels = {
        "deadline",
        "public_comment_deadline",
        "appeal_deadline",
    }

    return [
        item
        for item in extract_project_dates(
            text,
            reference_date,
            application_number,
        )
        if item.is_future and item.label not in non_project_labels
    ]


def historical_project_dates(
    text: str,
    reference_date: Optional[date] = None,
    application_number: Optional[str] = None,
) -> list[ProjectDate]:

    return [
        item
        for item in extract_project_dates(
            text,
            reference_date,
            application_number,
        )
        if not item.is_future
    ]


# ---------------------------------------------------------------------------
# NEXT EVENT
# ---------------------------------------------------------------------------

def get_next_project_date(
    text: str,
    reference_date: Optional[date] = None,
    application_number: Optional[str] = None,
) -> Optional[ProjectDate]:

    future = future_project_dates(
        text,
        reference_date,
        application_number,
    )

    if not future:
        return None

    # Earliest FUTURE date only.
    return min(
        future,
        key=lambda item: item.value,
    )


# ---------------------------------------------------------------------------
# APPLICATION ENRICHMENT
# ---------------------------------------------------------------------------

def enrich_application_dates(
    application: dict,
    text: str,
    reference_date: Optional[date] = None,
) -> dict:
    """
    Add project-date intelligence to an application.

    Existing application fields are preserved.
    """

    application_number = application.get(
        "application_number"
    )

    dates = extract_project_dates(
        text,
        reference_date,
        application_number,
    )

    future = [
        item for item in dates
        if item.is_future
    ]

    historical = [
        item for item in dates
        if not item.is_future
    ]

    next_event = get_next_project_date(
        text,
        reference_date,
        application_number,
    )

    enriched = dict(application)

    enriched["project_dates"] = [
        item.to_dict()
        for item in dates
    ]

    enriched["future_project_dates"] = [
        item.to_dict()
        for item in future
    ]

    enriched["historical_project_dates"] = [
        item.to_dict()
        for item in historical
    ]

    enriched["next_project_date"] = (
        next_event.value
        if next_event
        else None
    )

    enriched["next_project_event"] = (
        next_event.label
        if next_event
        else None
    )

    enriched["next_project_time"] = (
        next_event.time
        if next_event
        else None
    )

    enriched["has_future_opportunity"] = bool(
        future
    )

    return enriched


def project_dates_to_dicts(
    dates: list[ProjectDate],
) -> list[dict]:
    return [
        item.to_dict()
        for item in dates
    ]


def get_future_event_summary(
    text: str,
    reference_date: Optional[date] = None,
    application_number: Optional[str] = None,
) -> dict:

    future = future_project_dates(
        text,
        reference_date,
        application_number,
    )

    next_event = get_next_project_date(
        text,
        reference_date,
        application_number,
    )

    return {
        "has_future_opportunity": bool(future),
        "next_project_date": (
            next_event.value
            if next_event
            else None
        ),
        "next_project_event": (
            next_event.label
            if next_event
            else None
        ),
        "next_project_time": (
            next_event.time
            if next_event
            else None
        ),
        "future_project_dates": (
            project_dates_to_dicts(future)
        ),
    }