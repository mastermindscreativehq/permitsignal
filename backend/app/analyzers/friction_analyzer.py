from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional


# ============================================================
# PERMITSIGNAL FRICTION ANALYZER
# ============================================================
#
# Purpose:
#   Turn raw government packet text + current applications into
#   structured historical friction events.
#
# Important design rule:
#   A keyword is NOT enough.
#
#   Every event must have:
#       - application/applicant context
#       - evidence snippet
#       - event type
#       - severity
#       - confidence
#       - source position
#
# This prevents generic municipal boilerplate from contaminating
# every application.
# ============================================================


# ============================================================
# EVENT RULES
# ============================================================

EVENT_RULES: dict[str, dict[str, Any]] = {
    "recommended_denial": {
        "patterns": [
            # Historical decision language.
            r"\bwas\s+recommended\s+denial\b",
            r"\bwere\s+recommended\s+denial\b",
            r"\brecommended\s+denial\s+by\s+the\s+planning\s+commission\b",
            r"\brecommended\s+denial\s+on\s+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},\s+\d{4}\b",
            r"\bstaff\s+(?:recommended|recommends)\s+denial\s+of\b",
        ],
        "severity": "high",
        "weight": 50,
    },

    "denied": {
        "patterns": [
            r"\bultimately\s+denied\b",
            r"\bapplication\s+was\s+denied\b",
            r"\brequest\s+was\s+denied\b",
            r"\brezone\s+request\s+was\s+denied\b",
            r"\bwas\s+denied\s+by\s+the\s+(?:municipal\s+)?council\b",
            r"\bdenied\s+by\s+the\s+municipal\s+council\b",
        ],
        "severity": "critical",
        "weight": 60,
    },

    "continued": {
        "patterns": [
            r"\*{2,}\s*continued\s*\*{2,}",
            r"\bcontinued\s+from\b",
            r"\bcontinued\s+to\b",
            r"\bcontinued\s+until\b",
        ],
        "severity": "medium",
        "weight": 20,
    },

    "staff_concern": {
        "patterns": [
            r"\bstaff\s+concern(?:s)?\b",
            r"\bstaff\s+(?:is|are|was|were)\s+concerned\b",
            r"\bstaff\s+expressed\s+concern\b",
            r"\bstaff\s+has\s+concerns\b",
        ],
        "severity": "high",
        "weight": 30,
    },

    "neighborhood_concern": {
        "patterns": [
            r"\bneighborhood\s+concern(?:s)?\b",
            r"\bneighborhood\s+opposition\b",
            r"\bresident(?:s)?\s+(?:raised|expressed)\s+concern\b",
            r"\bresident(?:s)?\s+opposition\b",
            r"\bcommunity\s+opposition\b",
            r"\bneighborhood\s+opposed\b",
        ],
        "severity": "high",
        "weight": 30,
    },

    "public_opposition": {
        "patterns": [
            r"\bpublic\s+opposition\b",
            r"\bpublic\s+opposed\b",
            r"\bopposition\s+from\s+the\s+public\b",
            r"\bmembers\s+of\s+the\s+public\s+opposed\b",
        ],
        "severity": "high",
        "weight": 25,
    },

    "appeal": {
        "patterns": [
            r"\bappeal(?:ed|s)?\s+(?:the\s+)?decision\b",
            r"\bfiled\s+an\s+appeal\b",
            r"\bappeal\s+was\s+filed\b",
        ],
        "severity": "high",
        "weight": 35,
    },

    "additional_information": {
        "patterns": [
            r"\badditional\s+information\s+was\s+requested\b",
            r"\brequested\s+additional\s+information\b",
            r"\badditional\s+information\s+requested\b",
            r"\badditional\s+materials\s+were\s+requested\b",
            r"\bfurther\s+information\s+was\s+requested\b",
        ],
        "severity": "medium",
        "weight": 15,
    },

    "amended": {
        "patterns": [
            r"\bamended\s+application\b",
            r"\bamended\s+request\b",
            r"\bapplication\s+was\s+amended\b",
            r"\brevised\s+application\b",
            r"\brevised\s+request\b",
        ],
        "severity": "medium",
        "weight": 15,
    },

    "withdrawn": {
        "patterns": [
            r"\bapplication\s+was\s+withdrawn\b",
            r"\brequest\s+was\s+withdrawn\b",
            r"\bwithdrawn\s+application\b",
            r"\bapplicant\s+withdrew\b",
        ],
        "severity": "high",
        "weight": 35,
    },

    "tabled": {
        "patterns": [
            r"\btabled\s+the\s+item\b",
            r"\bitem\s+was\s+tabled\b",
            r"\bapplication\s+was\s+tabled\b",
        ],
        "severity": "medium",
        "weight": 20,
    },
}


# Generic boilerplate phrases. These should NOT create friction.
BOILERPLATE_PATTERNS = [
    r"decisions?.{0,100}\bmay be appealed\b",
    r"\badditional information can be found at\b",
    r"\bfor more information\b",
    r"\bpublic comments?\b",

    # These are hypothetical procedural options, NOT actual outcomes.
    r"\bpossible motions and findings\b",
    r"\bthe planning commission may make any of the following findings\b",
    r"\b1\.\s*recommend approval.*?2\.\s*recommend denial\b",
    r"\b2\.\s*recommend denial.*?3\.\s*continue\b",
]


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


def clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_name(name: Optional[str]) -> str:
    if not name:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        name.lower(),
    ).strip()


def normalize_address(address: Optional[str]) -> str:
    if not address:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        address.lower(),
    ).strip()


# ============================================================
# APPLICATION NUMBER
# ============================================================

APPLICATION_NUMBER_PATTERN = re.compile(
    r"\bPL[A-Z]{2,6}\d{8}\b",
    re.IGNORECASE,
)


# ============================================================
# ITEM BOUNDARIES
# ============================================================

ITEM_PATTERN = re.compile(
    r"(?m)^\s*(?:\*+\s*)?[-]?\s*Item\s+(\d+)\b",
    re.IGNORECASE,
)


def find_item_boundaries(
    text: str,
) -> list[dict[str, Any]]:
    """
    Return agenda item boundaries.

    This is deliberately separate from application extraction.
    It lets us prevent Item 7's CONTINUED marker from becoming
    Item 8's CONTINUED marker.
    """

    matches = list(
        ITEM_PATTERN.finditer(text)
    )

    boundaries = []

    for index, match in enumerate(matches):

        start = match.start()

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        boundaries.append(
            {
                "item": int(match.group(1)),
                "start": start,
                "end": end,
                "text": text[start:end],
            }
        )

    return boundaries


# ============================================================
# APPLICATION LOCATION
# ============================================================

def find_application_positions(
    text: str,
    application_number: str,
) -> list[int]:

    if not application_number:
        return []

    return [
        match.start()
        for match in re.finditer(
            re.escape(application_number),
            text,
            re.IGNORECASE,
        )
    ]


def find_applicant_positions(
    text: str,
    applicant_name: Optional[str],
) -> list[int]:

    if not applicant_name:
        return []

    # Flexible whitespace between words.
    words = re.findall(
        r"[A-Za-z0-9]+",
        applicant_name,
    )

    if not words:
        return []

    pattern = r"\s+".join(
        re.escape(word)
        for word in words
    )

    return [
        match.start()
        for match in re.finditer(
            pattern,
            text,
            re.IGNORECASE,
        )
    ]


def find_address_positions(
    text: str,
    address: Optional[str],
) -> list[int]:

    if not address:
        return []

    normalized = normalize_address(
        address
    )

    if not normalized:
        return []

    words = normalized.split()

    pattern = r"[\s,./-]+".join(
        re.escape(word)
        for word in words
    )

    return [
        match.start()
        for match in re.finditer(
            pattern,
            text,
            re.IGNORECASE,
        )
    ]


# ============================================================
# CONTEXT
# ============================================================

def context_window(
    text: str,
    position: int,
    before: int = 500,
    after: int = 900,
) -> str:

    start = max(
        0,
        position - before,
    )

    end = min(
        len(text),
        position + after,
    )

    return text[start:end]


def context_contains_application(
    context: str,
    application_number: str,
) -> bool:

    return bool(
        re.search(
            re.escape(application_number),
            context,
            re.IGNORECASE,
        )
    )


def context_contains_applicant(
    context: str,
    applicant_name: Optional[str],
) -> bool:

    if not applicant_name:
        return False

    normalized_context = normalize_name(
        context
    )

    normalized_applicant = normalize_name(
        applicant_name
    )

    return normalized_applicant in normalized_context


# ============================================================
# DATE EXTRACTION
# ============================================================

MONTHS = (
    "January|February|March|April|May|June|July|"
    "August|September|October|November|December"
)

DATE_PATTERNS = [
    re.compile(
        rf"\b({MONTHS})\s+"
        r"(\d{1,2}),\s*(\d{4})\b",
        re.IGNORECASE,
    ),

    re.compile(
        rf"\b(\d{{1,2}})\s+({MONTHS})\s+"
        r"(\d{4})\b",
        re.IGNORECASE,
    ),
]


def extract_dates(
    text: str,
) -> list[str]:

    dates = []

    for pattern in DATE_PATTERNS:

        for match in pattern.finditer(text):

            try:

                if match.group(1).isdigit():

                    day = int(
                        match.group(1)
                    )

                    month_name = (
                        match.group(2)
                    )

                    year = int(
                        match.group(3)
                    )

                else:

                    month_name = (
                        match.group(1)
                    )

                    day = int(
                        match.group(2)
                    )

                    year = int(
                        match.group(3)
                    )

                parsed = date(
                    year,
                    _month_number(
                        month_name
                    ),
                    day,
                )

                dates.append(
                    parsed.isoformat()
                )

            except ValueError:
                continue

    return sorted(
        set(dates)
    )


def _month_number(
    month_name: str,
) -> int:

    names = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]

    return (
        names.index(
            month_name.lower()
        )
        + 1
    )


MONTH_DATE_PATTERN = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
)


def normalize_date(
    value: str,
) -> Optional[str]:
    """
    Convert 'December 2, 2025' into ISO format.
    """
    from datetime import datetime

    if not value:
        return None

    value = clean(
        value
    )

    try:
        return datetime.strptime(
            value,
            "%B %d, %Y",
        ).date().isoformat()
    except ValueError:
        return value


def extract_event_date(
    event_type: str,
    evidence: str,
) -> Optional[str]:
    """
    Extract the date belonging to THIS event.

    We must not simply take the first date in a large evidence
    window. A single staff-report sentence can contain multiple
    historical decisions, for example:

        recommended denial ... on November 12, 2025,
        and ultimately denied ... on December 2, 2025.

    The old nearest_date() function incorrectly assigned
    November 12 to both events.

    This function first applies event-specific patterns, then
    falls back to the closest date only when the evidence contains
    a single unambiguous date.
    """

    if not evidence:
        return None

    # --------------------------------------------------------
    # RECOMMENDED DENIAL
    # --------------------------------------------------------

    if event_type == "recommended_denial":

        patterns = [
            rf"recommended\s+(?:for\s+)?denial"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",

            rf"recommend(?:ed|s)?\s+denial"
            rf".{{0,180}}?\b("
            rf"{MONTH_DATE_PATTERN}"
            rf")",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                evidence,
                re.IGNORECASE
                | re.DOTALL,
            )

            if match:
                return normalize_date(
                    match.group(1)
                )

    # --------------------------------------------------------
    # DENIED
    # --------------------------------------------------------

    if event_type == "denied":

        # The common staff-report construction:
        #
        # "... recommended denial ... on November 12, 2025,
        #  and ultimately denied by the Municipal Council on
        #  December 2, 2025."
        #
        # Capture the SECOND date.
        match = re.search(
            rf"recommended\s+(?:for\s+)?denial"
            rf".{{0,180}}?\bon\s+"
            rf"{MONTH_DATE_PATTERN}"
            rf".{{0,220}}?"
            rf"(?:ultimately\s+)?denied"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",
            evidence,
            re.IGNORECASE
            | re.DOTALL,
        )

        if match:
            return normalize_date(
                match.group(1)
            )

        # Other explicit historical forms.
        patterns = [
            rf"ultimately\s+denied"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",

            rf"denied\s+by\s+(?:the\s+)?"
            rf"(?:municipal\s+)?council"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",

            rf"application\s+was\s+denied"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",

            rf"request\s+was\s+denied"
            rf".{{0,180}}?\bon\s+"
            rf"({MONTH_DATE_PATTERN})",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                evidence,
                re.IGNORECASE
                | re.DOTALL,
            )

            if match:
                return normalize_date(
                    match.group(1)
                )

    # --------------------------------------------------------
    # GENERIC FALLBACK
    # --------------------------------------------------------

    dates = extract_dates(
        evidence
    )

    if len(dates) == 1:
        return dates[0]

    return None


def nearest_date(
    text: str,
    match_position: int,
    radius: int = 500,
) -> Optional[str]:
    """
    Backward-compatible fallback for signals that do not have
    event-specific date syntax.
    """

    start = max(
        0,
        match_position - radius,
    )

    end = min(
        len(text),
        match_position + radius,
    )

    dates = extract_dates(
        text[start:end]
    )

    if not dates:
        return None

    if len(dates) == 1:
        return dates[0]

    return None


# ============================================================
# PAGE / SOURCE POSITION
# ============================================================

def estimate_page_number(
    text: str,
    position: int,
) -> Optional[int]:
    """
    Estimate page from form-feed characters when available.

    The current Provo test reader joins pages with newlines, so
    this will normally return None. It is kept for production
    readers that preserve page boundaries.
    """

    if "\f" not in text:
        return None

    return text[:position].count(
        "\f"
    ) + 1


# ============================================================
# BOILERPLATE FILTER
# ============================================================

def is_boilerplate(
    snippet: str,
) -> bool:

    for pattern in BOILERPLATE_PATTERNS:

        if re.search(
            pattern,
            snippet,
            re.IGNORECASE | re.DOTALL,
        ):
            return True

    return False


# ============================================================
# EVIDENCE EXTRACTION
# ============================================================

def extract_evidence(
    text: str,
    pattern: str,
    signal: str,
    position_scope: Optional[tuple[int, int]] = None,
) -> list[dict[str, Any]]:

    results = []

    flags = (
        re.IGNORECASE
        | re.DOTALL
    )

    for match in re.finditer(
        pattern,
        text,
        flags,
    ):

        position = match.start()

        if position_scope:

            start_scope, end_scope = (
                position_scope
            )

            if not (
                start_scope
                <= position
                < end_scope
            ):
                continue

        start = max(
            0,
            match.start() - 350,
        )

        end = min(
            len(text),
            match.end() + 650,
        )

        snippet = clean(
            text[start:end]
        )

        if not snippet:
            continue

        if is_boilerplate(
            snippet
        ):
            continue

        results.append(
            {
                "signal": signal,
                "match": clean(
                    match.group(0)
                ),
                "snippet": snippet,
                "position": position,
                "page": estimate_page_number(
                    text,
                    position,
                ),
            }
        )

    return results


# ============================================================
# HISTORY RELEVANCE
# ============================================================

def relevance_score(
    evidence: dict[str, Any],
    application: dict[str, Any],
    full_text: str,
) -> float:

    snippet = evidence[
        "snippet"
    ]

    score = 0.0

    app_number = application.get(
        "application_number"
    )

    applicant = application.get(
        "applicant_name"
    )

    address = application.get(
        "project_address"
    )

    # Strongest signal: exact application number.
    if app_number and re.search(
        re.escape(app_number),
        snippet,
        re.IGNORECASE,
    ):
        score += 0.60

    # Applicant name.
    if applicant and context_contains_applicant(
        snippet,
        applicant,
    ):
        score += 0.25

    # Property address.
    if address:

        snippet_address = normalize_address(
            snippet
        )

        normalized_address = normalize_address(
            address
        )

        if (
            normalized_address
            and normalized_address in snippet_address
        ):
            score += 0.25

    return min(
        1.0,
        score,
    )


# ============================================================
# EVENT CONFIDENCE
# ============================================================

def calculate_confidence(
    evidence: dict[str, Any],
    application: dict[str, Any],
    full_text: str,
) -> float:

    score = 0.45

    app_number = application.get(
        "application_number"
    )

    applicant = application.get(
        "applicant_name"
    )

    address = application.get(
        "project_address"
    )

    snippet = evidence[
        "snippet"
    ]

    if app_number and re.search(
        re.escape(app_number),
        snippet,
        re.IGNORECASE,
    ):
        score += 0.35

    if applicant and context_contains_applicant(
        snippet,
        applicant,
    ):
        score += 0.15

    if address and normalize_address(
        address
    ) in normalize_address(
        snippet
    ):
        score += 0.10

    return round(
        min(score, 0.99),
        2,
    )



# ============================================================
# APPLICATION-SPECIFIC ITEM CONTEXT
# ============================================================

def get_application_item_text(
    full_text: str,
    application: dict[str, Any],
) -> str:
    """
    Restrict CURRENT agenda signals to the application's own
    Item N block. This prevents Item 7's CONTINUED marker from
    contaminating Items 1, 6, or 8.
    """
    item = application.get("item")

    if item is None:
        return ""

    boundaries = find_item_boundaries(full_text)

    for boundary in boundaries:
        if boundary["item"] == int(item):
            return boundary["text"]

    return ""


def explicit_historical_outcome(
    event_type: str,
    snippet: str,
) -> bool:
    """
    Decide whether wording describes a real historical event
    instead of a hypothetical procedural option.

    Example rejected:
        "The Planning Commission may make ... Recommend Denial"

    Example accepted:
        "Jared Morgan ... was recommended denial by the
         Planning Commission on November 12, 2025"
    """
    lower = snippet.lower()

    if "possible motions and findings" in lower:
        return False

    if "may make any of the following findings" in lower:
        return False

    if event_type == "recommended_denial":
        historical_markers = [
            "was recommended denial",
            "were recommended denial",
            "recommended denial by",
            "recommended denial on",
            "staff recommended denial of",
        ]

        return any(
            marker in lower
            for marker in historical_markers
        )

    if event_type == "denied":
        historical_markers = [
            "ultimately denied",
            "was denied by the municipal council",
            "denied by the municipal council",
            "application was denied",
            "request was denied",
        ]

        return any(
            marker in lower
            for marker in historical_markers
        )

    return True


def current_signal_from_item(
    event_type: str,
    item_text: str,
    application: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract only signals that actually occur in the current
    application's own agenda item.
    """
    if not item_text:
        return []

    results = []

    rule = EVENT_RULES.get(event_type)

    if not rule:
        return results

    for pattern in rule["patterns"]:
        for match in re.finditer(
            pattern,
            item_text,
            re.IGNORECASE | re.DOTALL,
        ):
            snippet_start = max(
                0,
                match.start() - 300,
            )
            snippet_end = min(
                len(item_text),
                match.end() + 500,
            )

            snippet = clean(
                item_text[
                    snippet_start:snippet_end
                ]
            )

            if not snippet:
                continue

            if is_boilerplate(snippet):
                continue

            # Hypothetical "recommend denial" language is not
            # evidence that denial actually occurred.
            if event_type in {
                "recommended_denial",
                "denied",
            }:
                if not explicit_historical_outcome(
                    event_type,
                    snippet,
                ):
                    continue

            results.append(
                {
                    "signal": event_type,
                    "match": clean(
                        match.group(0)
                    ),
                    "snippet": snippet,
                    "position": match.start(),
                    "page": estimate_page_number(
                        item_text,
                        match.start(),
                    ),
                }
            )

    return results


# ============================================================
# EVENT EXTRACTION FOR ONE APPLICATION
# ============================================================

def analyze_application(
    text: str,
    application: dict[str, Any],
) -> dict[str, Any]:

    application_number = application.get(
        "application_number"
    )

    applicant_name = application.get(
        "applicant_name"
    )

    if not application_number:
        return {
            "application_number": None,
            "events": [],
            "friction_score": 0,
            "signals": [],
        }

    normalized_text = normalize_text(text)

    events = []

    # --------------------------------------------------------
    # 1. CURRENT AGENDA SIGNALS
    #
    # Only inspect this application's own Item N block.
    # --------------------------------------------------------

    item_text = get_application_item_text(
        normalized_text,
        application,
    )

    status = str(
        application.get(
            "status",
            ""
        ) or ""
    ).lower()

    # CONTINUED is a current status only when the extractor
    # explicitly marked this application as continued OR the
    # application's own item contains ***CONTINUED***.
    if (
        "continued" in status
        or re.search(
            r"\*{2,}\s*continued\s*\*{2,}",
            item_text,
            re.IGNORECASE,
        )
    ):
        current_events = current_signal_from_item(
            "continued",
            item_text,
            application,
        )

        # The current application has at most one meaningful
        # CONTINUED state.
        if current_events:
            current_events = [
                current_events[0]
            ]

        for evidence in current_events:
            events.append(
                {
                    "event_type": "continued",
                    "severity": "medium",
                    "weight": EVENT_RULES["continued"]["weight"],
                    "confidence": 0.99,
                    "relevance": 1.0,
                    "event_date": None,
                    "application_number": application_number,
                    "applicant_name": applicant_name,
                    "project_address": application.get(
                        "project_address"
                    ),
                    "evidence": evidence["snippet"],
                    "matched_text": evidence["match"],
                    "source_position": evidence["position"],
                    "source_page": evidence["page"],
                }
            )

    # --------------------------------------------------------
    # 2. HISTORICAL EVENTS
    #
    # Search the full packet, but require:
    #   - applicant context, OR
    #   - property/address context
    #
    # Strong historical outcomes get special handling.
    # --------------------------------------------------------

    for event_type in (
        "recommended_denial",
        "denied",
        "withdrawn",
        "staff_concern",
        "neighborhood_concern",
        "public_opposition",
        "appeal",
        "additional_information",
        "amended",
        "tabled",
    ):

        rule = EVENT_RULES[event_type]

        for pattern in rule["patterns"]:

            raw_evidence = extract_evidence(
                normalized_text,
                pattern,
                event_type,
            )

            for evidence in raw_evidence:

                snippet = evidence["snippet"]

                # Never treat procedural "possible motions"
                # as actual historical outcomes.
                if not explicit_historical_outcome(
                    event_type,
                    snippet,
                ):
                    continue

                relevance = relevance_score(
                    evidence,
                    application,
                    normalized_text,
                )

                applicant_match = (
                    applicant_name
                    and context_contains_applicant(
                        snippet,
                        applicant_name,
                    )
                )

                address = application.get(
                    "project_address"
                )

                address_match = False

                if address:
                    address_match = (
                        normalize_address(
                            address
                        )
                        in normalize_address(
                            snippet
                        )
                    )

                # Historical evidence must be attached to the
                # same person/property. Generic packet language
                # is rejected.
                if not (
                    applicant_match
                    or address_match
                ):
                    continue

                # For high-value decision events, applicant or
                # address context is enough.
                if (
                    event_type
                    in {
                        "recommended_denial",
                        "denied",
                    }
                ):
                    relevance = max(
                        relevance,
                        0.40,
                    )

                confidence = calculate_confidence(
                    evidence,
                    application,
                    normalized_text,
                )

                # Strong historical outcome with explicit
                # applicant/address match should pass.
                if applicant_match:
                    confidence = max(
                        confidence,
                        0.75,
                    )

                if address_match:
                    confidence = max(
                        confidence,
                        0.80,
                    )

                if confidence < 0.55:
                    continue

                event_date = extract_event_date(
                    event_type,
                    snippet,
                )

                if event_date is None:
                    event_date = nearest_date(
                        normalized_text,
                        evidence["position"],
                    )

                events.append(
                    {
                        "event_type": event_type,
                        "severity": rule["severity"],
                        "weight": rule["weight"],
                        "confidence": round(
                            min(confidence, 0.99),
                            2,
                        ),
                        "relevance": round(
                            relevance,
                            2,
                        ),
                        "event_date": event_date,
                        "application_number":
                            application_number,
                        "applicant_name":
                            applicant_name,
                        "project_address":
                            application.get(
                                "project_address"
                            ),
                        "evidence":
                            snippet,
                        "matched_text":
                            evidence["match"],
                        "source_position":
                            evidence["position"],
                        "source_page":
                            evidence["page"],
                    }
                )

    # --------------------------------------------------------
    # 3. DEDUPLICATE
    # --------------------------------------------------------

    events = deduplicate_events(
        events
    )

    # --------------------------------------------------------
    # 4. SCORE
    # --------------------------------------------------------

    friction_score = calculate_friction_score(
        events
    )

    signals = sorted(
        set(
            event["event_type"]
            for event in events
        )
    )

    return {
        "application_number":
            application_number,
        "applicant_name":
            applicant_name,
        "project_address":
            application.get(
                "project_address"
            ),
        "events":
            events,
        "signals":
            signals,
        "friction_score":
            friction_score,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Collapse multiple regex hits referring to the same underlying
    decision/event.

    A staff report can contain the same sentence several times
    because of repeated headings, attachments, or nearby matches.
    Those are not separate friction events.

    We therefore keep one event per:
        application + event_type + event_date

    When several candidates exist, retain the strongest and clearest
    evidence snippet.
    """

    grouped: dict[tuple, dict[str, Any]] = {}

    def evidence_quality(event: dict[str, Any]) -> float:
        text = str(
            event.get("evidence", "")
        )

        score = 0.0

        # Prefer explicit historical decision language.
        lower = text.lower()

        if "ultimately denied" in lower:
            score += 10

        if "was recommended denial" in lower:
            score += 10

        if "recommended denial by the planning commission" in lower:
            score += 8

        if "municipal council" in lower:
            score += 4

        if "planning commission" in lower:
            score += 3

        # Prefer applicant/property context.
        if event.get("applicant_name"):
            if str(
                event["applicant_name"]
            ).lower() in lower:
                score += 5

        if event.get("project_address"):
            address = str(
                event["project_address"]
            ).lower()

            address_tokens = [
                token
                for token in re.findall(
                    r"[a-z0-9]+",
                    address,
                )
                if len(token) > 2
            ]

            score += sum(
                1
                for token in address_tokens
                if token in lower
            )

        # Prefer longer complete evidence, but cap the influence.
        score += min(
            len(text) / 500.0,
            3.0,
        )

        score += float(
            event.get(
                "confidence",
                0,
            )
        )

        score += float(
            event.get(
                "relevance",
                0,
            )
        )

        return score

    for event in events:

        key = (
            event.get(
                "event_type"
            ),
            event.get(
                "event_date"
            ),
        )

        existing = grouped.get(key)

        if existing is None:
            grouped[key] = event
            continue

        if evidence_quality(event) > evidence_quality(existing):
            grouped[key] = event

    # Stable ordering: historical date first, then event type.
    result = list(
        grouped.values()
    )

    result.sort(
        key=lambda event: (
            str(
                event.get(
                    "event_date"
                )
                or ""
            ),
            str(
                event.get(
                    "event_type"
                )
                or ""
            ),
        )
    )

    return result


# ============================================================
# SCORE
# ============================================================

def calculate_friction_score(
    events: list[dict[str, Any]],
) -> int:

    if not events:
        return 0

    # Count each event type once for the base score. Repeated
    # snippets from the same staff report should not inflate
    # the lead score.
    best_by_type: dict[str, dict[str, Any]] = {}

    for event in events:

        event_type = event.get(
            "event_type"
        )

        existing = best_by_type.get(
            event_type
        )

        if (
            existing is None
            or (
                event.get(
                    "confidence",
                    0,
                )
                > existing.get(
                    "confidence",
                    0,
                )
            )
        ):
            best_by_type[event_type] = event

    score = 0.0

    for event in best_by_type.values():

        score += (
            event.get(
                "weight",
                0,
            )
            * event.get(
                "confidence",
                0,
            )
        )

    event_types = set(
        best_by_type.keys()
    )

    # Compound friction is meaningful.
    if (
        "recommended_denial"
        in event_types
        and "denied"
        in event_types
    ):
        score += 20

    if (
        "denied"
        in event_types
        and "continued"
        in event_types
    ):
        score += 10

    if (
        "recommended_denial"
        in event_types
        and "continued"
        in event_types
    ):
        score += 10

    # Keep the score bounded, but make the meaning explicit:
    # 100 is reserved for a genuinely compounded/high-friction
    # record, not simply repeated mentions of one event.
    return int(
        min(
            round(score),
            100,
        )
    )


# ============================================================
# BATCH ANALYSIS
# ============================================================

def analyze_applications(
    text: str,
    applications: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized_text = normalize_text(
        text
    )

    results = []

    for application in applications:

        result = analyze_application(
            normalized_text,
            application,
        )

        # Preserve the original application record.
        merged = {
            **application,
            "friction_score":
                result[
                    "friction_score"
                ],
            "friction_signals":
                result[
                    "signals"
                ],
            "friction_events":
                result[
                    "events"
                ],
        }

        results.append(
            merged
        )

    return results


# ============================================================
# HIGH PRIORITY
# ============================================================

def get_high_priority_applications(
    analyzed_applications: list[dict[str, Any]],
    minimum_score: int = 40,
) -> list[dict[str, Any]]:

    return sorted(
        [
            application
            for application
            in analyzed_applications
            if application.get(
                "friction_score",
                0,
            ) >= minimum_score
        ],
        key=lambda application: application.get(
            "friction_score",
            0,
        ),
        reverse=True,
    )


# ============================================================
# COMPATIBILITY HELPER
# ============================================================

def analyze_application_history(
    text: str,
    application_number: str,
) -> dict[str, Any]:
    """
    Compatibility helper for earlier tests.

    Creates a minimal application record and returns the
    structured friction result.
    """

    application = {
        "application_number":
            application_number,
    }

    return analyze_application(
        text,
        application,
    )


# ============================================================
# EVENT SUMMARY
# ============================================================

def summarize_events(
    events: list[dict[str, Any]],
) -> list[str]:

    summaries = []

    for event in events:

        event_type = event.get(
            "event_type"
        )

        event_date = event.get(
            "event_date"
        )

        severity = event.get(
            "severity"
        )

        if event_date:
            summaries.append(
                f"{event_type} "
                f"({event_date}, "
                f"{severity})"
            )
        else:
            summaries.append(
                f"{event_type} "
                f"({severity})"
            )

    return summaries
