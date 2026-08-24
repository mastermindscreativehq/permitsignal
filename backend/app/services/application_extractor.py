from __future__ import annotations

import re
from typing import Optional


# ============================================================
# PERMITSIGNAL APPLICATION EXTRACTOR
# Production-oriented agenda/application extraction
# ============================================================

# Government application IDs such as:
# PLOTA20260371
# PLRZ20260116
# PLCP20260117
# PLVAR20260373
APPLICATION_NUMBER_PATTERN = re.compile(
    r"\bPL[A-Z]{2,6}\d{8}\b",
    re.IGNORECASE,
)

# Agenda item headings.
ITEM_PATTERN = re.compile(
    r"(?m)^\s*(?:\*+\s*)?[-]?\s*Item\s+(\d+)\b",
    re.IGNORECASE,
)

# "Tyson Reynolds requests..."
REQUEST_PATTERN = re.compile(
    r"(?P<applicant>"
    r"[A-Z][A-Za-z.'\-]+"
    r"(?:\s+[A-Z][A-Za-z.'\-]+){0,5}"
    r")\s+requests?\b",
    re.IGNORECASE,
)

EMAIL_PATTERN = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"\(?\d{3}\)?[\s.-]+\d{3}[\s.-]+\d{4}"
)

# Standard street-address patterns.
ADDRESS_PATTERN = re.compile(
    r"\b"
    r"\d{1,6}"
    r"\s+"
    r"[A-Za-z0-9.'\-]+"
    r"(?:\s+[A-Za-z0-9.'\-]+){0,6}"
    r"\s+"
    r"(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|"
    r"Drive|Dr|Circle|Cir|Lane|Ln|Way|Court|Ct|"
    r"Place|Pl|Parkway|Pkwy|Highway|Hwy)"
    r"\b",
    re.IGNORECASE,
)

# Addresses such as:
# 113/191 N Geneva Road
# 1722 West 820 North
# 1065 E Hillside Circle
SPECIAL_ADDRESS_PATTERN = re.compile(
    r"\b"
    r"\d+(?:/\d+)?"
    r"\s+"
    r"(?:N|S|E|W|North|South|East|West)?"
    r"\s*"
    r"[A-Za-z0-9.'\-]+"
    r"(?:\s+[A-Za-z0-9.'\-]+){0,5}"
    r"\s+"
    r"(?:Road|Rd|Street|St|Avenue|Ave|"
    r"Boulevard|Blvd|Drive|Dr|Circle|Cir|"
    r"Lane|Ln|Way|Court|Ct|Place|Pl|"
    r"Parkway|Pkwy|Highway|Hwy|North|South|East|West)"
    r"\b",
    re.IGNORECASE,
)

# Common application categories.
APPLICATION_TYPES = [
    ("Ordinance Text Amendment", r"ordinance text amendment"),
    ("Zone Map Amendment", r"zone map amendment"),
    ("Concept Plan", r"concept plan"),
    ("Project Plan", r"project plan"),
    ("Variance", r"\bvariance\b"),
    ("Conditional Use", r"conditional use"),
    ("Subdivision", r"\bsubdivision\b"),
    ("General Plan Amendment", r"general plan amendment"),
    # Real Provo packets also phrase this as "General Plan Map Amendment"
    # or "amendment to the General Plan Map" -- both distinct word orders
    # from the base pattern above, not a different application category.
    ("General Plan Amendment", r"general plan map amendment"),
    ("General Plan Amendment", r"amendment to the general plan map"),
]


# ============================================================
# CLEANING
# ============================================================

def clean(value: Optional[str]) -> Optional[str]:
    """Normalize extracted text without destroying useful content."""

    if not value:
        return None

    value = value.replace("\x00", " ")
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_email(
    email: Optional[str],
) -> Optional[str]:

    if not email:
        return None

    return email.strip().lower()


def normalize_phone(
    phone: Optional[str],
) -> Optional[str]:

    if not phone:
        return None

    phone = re.sub(r"\s+", " ", phone.strip())
    phone = re.sub(r"\s*([\-])\s*", r"\1", phone)
    phone = re.sub(r"\(\s*", "(", phone)
    phone = re.sub(r"\s*\)", ")", phone)
    return phone


# ============================================================
# AGENDA SECTION
# ============================================================

def extract_agenda_section(
    text: str,
) -> str:
    """
    Extract the public-hearing agenda portion.

    We deliberately do not parse the entire 500+ page packet
    for applicant identity. Staff reports/history are handled
    separately by the friction analyzer.
    """

    match = re.search(
        r"\bPublic Hearings\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        # Safe fallback for unusual municipal formats.
        return text[:30000]

    start = match.start()

    end_patterns = [
        r"Preceding the public hearing",
        r"To send public comments",
        r"Copies of the agenda materials",
    ]

    end_positions = []

    for pattern in end_patterns:

        found = re.search(
            pattern,
            text[start:],
            re.IGNORECASE,
        )

        if found:
            end_positions.append(
                start + found.start()
            )

    if end_positions:
        end = min(end_positions)
    else:
        end = min(
            len(text),
            start + 30000,
        )

    return text[start:end]


# ============================================================
# AGENDA ITEM SPLITTING
# ============================================================

def split_agenda_items(
    agenda_text: str,
) -> list[tuple[int, str]]:
    """
    Split the public-hearing agenda into individual item blocks.
    """

    matches = list(
        ITEM_PATTERN.finditer(
            agenda_text
        )
    )

    items = []

    for index, match in enumerate(matches):

        item_number = int(
            match.group(1)
        )

        start = match.start()

        if index + 1 < len(matches):
            end = matches[
                index + 1
            ].start()
        else:
            end = len(
                agenda_text
            )

        block = agenda_text[
            start:end
        ].strip()

        items.append(
            (
                item_number,
                block,
            )
        )

    return items


# ============================================================
# APPLICANT
# ============================================================

def extract_applicant(
    block: str,
) -> Optional[str]:
    """
    Extract the party immediately responsible for the request.

    Example:
        Tyson Reynolds requests approval...
        Jared Morgan requests a Zone Map Amendment...
    """

    match = REQUEST_PATTERN.search(
        block
    )

    if not match:
        return None

    applicant = clean(
        match.group("applicant")
    )

    return applicant


# ============================================================
# CASE / APPLICATION IDENTIFIERS
#
# Jurisdictions label the same concept differently: "Case Number",
# "Case ID", "Application Number", "Project Number", "File Number",
# "Planning Application Number", "Development Application Number",
# bare "Case PUD-871" header style (real Tulsa County TMAPC staff
# report), or no label at all with a distinctive jurisdiction format
# (Provo's inline PLRZ20260264-style numbers).
#
# Extraction is label-driven first, then falls back to known formats.
# Every identifier is preserved EXACTLY as written in the source --
# never normalized into a different shape, never inferred from names,
# addresses, or other context. When no identifier exists the result is
# an evidence-backed None.
# ============================================================

# The value token following an identifier label. Deliberately broad
# (letters, digits, dashes, slashes, dots, underscores) so formats such
# as PUD-871, CZ-565, 22-5566, APP-2024-0042 and PLRZ20260264 all fit;
# _validated_case_id_value() below rejects anything that is not
# plausibly an identifier.
CASE_ID_VALUE_PATTERN = r"(?P<value>[A-Za-z0-9][A-Za-z0-9\-/_.]{0,39})"

# Explicit identifier labels, most specific first. When two specs match
# the same span (e.g. "Planning Application Number" contains the generic
# "Application Number"), the earlier, more specific spec wins.
CASE_ID_LABEL_SPECS = (
    (r"(?:Planning|Development)\s+Application\s*(?:Number|Nos?\.?|#|ID)", "application"),
    (r"(?:Planning|Zoning|Development)\s+Case\s*(?:Number|Nos?\.?|#|ID)", "case"),
    (r"Application\s*(?:Number|Nos?\.?|#|ID)", "application"),
    (r"Case\s*(?:Number|Nos?\.?|#|ID)", "case"),
    (r"Project\s*(?:Number|Nos?\.?|#|ID)", "project"),
    (r"File\s*(?:Number|Nos?\.?|#|ID)", "file"),
    # Bare jurisdiction header style: "Case PUD-871 Staff Report".
    # The lookahead requires an identifier-like token to follow, so
    # narrative phrases such as "in this case the applicant" never match.
    (r"Case\s*(?=[A-Za-z0-9#])", "case"),
)

_IDENTIFIER_TRAILING_PUNCTUATION = "./-,_:;)'\""

# Precompiled once: these patterns are scanned against full packet
# texts, not just individual agenda blocks.
_COMPILED_CASE_ID_SPECS = [
    (
        re.compile(
            rf"(?P<label>{body})\s*[:#]?\s*{CASE_ID_VALUE_PATTERN}",
            re.IGNORECASE,
        ),
        id_type,
    )
    for body, id_type in CASE_ID_LABEL_SPECS
]


def _validated_case_id_value(raw: Optional[str]) -> Optional[str]:
    """Accept only plausible identifiers; everything else is rejected."""

    if not raw:
        return None

    value = raw.strip().strip(_IDENTIFIER_TRAILING_PUNCTUATION).strip()

    if not (2 <= len(value) <= 40):
        return None

    # A real case/application/file/project number always carries at
    # least one digit. This single rule rejects captured prose such as
    # "the" after a narrative "in this case ...".
    if not re.search(r"\d", value):
        return None

    return value


def find_case_identifiers(
    text: str,
) -> list[dict]:
    """
    All evidence-backed identifier occurrences in document order.

    Each entry: {value, label, type, confidence, start, end,
    label_start}. `label` is the exact source label (whitespace-
    normalized) or None when found by format alone. Never fabricates:
    every value is verbatim source text.
    """

    if not text:
        return []

    candidates = []

    for pattern, id_type in _COMPILED_CASE_ID_SPECS:

        for match in pattern.finditer(text):
            candidates.append(
                {
                    "order": match.start(),
                    # Boundary where the identifier mention begins,
                    # including its label -- used whenever surrounding
                    # text must be cut before the mention.
                    "label_start": match.start(),
                    "start": match.start("value"),
                    "end": match.end("value"),
                    "raw_value": match.group("value"),
                    "label": clean(match.group("label")),
                    "id_type": id_type,
                }
            )

    # Unlabeled jurisdiction format (Provo): matched by format alone,
    # therefore lower confidence than an explicit source label.
    for match in APPLICATION_NUMBER_PATTERN.finditer(text):
        candidates.append(
            {
                "order": match.start(),
                "label_start": match.start(),
                "start": match.start(),
                "end": match.end(),
                "raw_value": match.group(0),
                "label": None,
                "id_type": "application",
            }
        )

    identifiers = []
    taken_spans = []

    for candidate in sorted(
        candidates,
        key=lambda entry: entry["order"],
    ):

        start = candidate["start"]
        end = candidate["end"]

        if any(
            start < taken_end and taken_start < end
            for taken_start, taken_end in taken_spans
        ):
            continue

        value = _validated_case_id_value(
            candidate["raw_value"]
        )

        if not value:
            continue

        taken_spans.append((start, end))

        identifiers.append(
            {
                "value": value,
                "label": candidate["label"],
                "type": candidate["id_type"],
                "confidence": (
                    "HIGH" if candidate["label"] else "MEDIUM"
                ),
                "start": start,
                "end": end,
                "label_start": candidate["label_start"],
            }
        )

    return identifiers


def _identifier_evidence(
    text: str,
    start: int,
    end: int,
) -> str:
    """Source snippet around the identifier, proving where it came from."""

    return clean(
        text[max(0, start - 60):min(len(text), end + 80)]
    )


def extract_case_identifier(
    block: str,
) -> Optional[dict]:
    """
    The record's primary identifier: the first evidence-backed
    identifier in the block. Related/secondary cases mentioned later
    (e.g. "Related to case CZ-565") never displace it.
    """

    identifiers = find_case_identifiers(block)

    if not identifiers:
        return None

    primary = dict(identifiers[0])

    primary["evidence"] = _identifier_evidence(
        block,
        primary["start"],
        primary["end"],
    )

    primary["source"] = "government_record"

    return primary


def extract_application_number(
    block: str,
) -> Optional[str]:
    """
    Compatibility wrapper returning just the primary identifier value.
    Preserves the exact source spelling (no forced uppercasing).
    """

    identifier = extract_case_identifier(block)

    if not identifier:
        return None

    return identifier["value"]


# ============================================================
# APPLICATION TYPE
# ============================================================

def extract_application_type(
    block: str,
) -> Optional[str]:

    lower = block.lower()

    # More specific phrase matching first.
    for name, pattern in APPLICATION_TYPES:

        if re.search(
            pattern,
            lower,
        ):
            return name

    return None


# ============================================================
# ADDRESS
# ============================================================

def extract_address(
    block: str,
) -> Optional[str]:
    """
    Prefer an address associated with 'located at'.

    Handles:
        2000 N Canyon Road
        113/191 N Geneva Road
        1065 E Hillside Circle
        1722 West 820 North
    """

    # --------------------------------------------------------
    # First: inspect the "located at" phrase.
    # --------------------------------------------------------

    located = re.search(
        r"located at\s+(.{5,220}?)"
        r"(?:\.\s+|\bNeighborhood\b)",
        block,
        re.IGNORECASE | re.DOTALL,
    )

    if located:

        candidate = clean(
            located.group(1)
        )

        if candidate:

            special = (
                SPECIAL_ADDRESS_PATTERN.search(
                    candidate
                )
            )

            if special:
                return clean(
                    special.group(0)
                )

            normal = ADDRESS_PATTERN.search(
                candidate
            )

            if normal:
                return clean(
                    normal.group(0)
                )

            # Preserve a candidate when the municipality
            # uses an unusual address format.
            return candidate

    # --------------------------------------------------------
    # Second: special address pattern.
    # --------------------------------------------------------

    matches = SPECIAL_ADDRESS_PATTERN.findall(
        block
    )

    if matches:
        return clean(
            matches[0]
        )

    # --------------------------------------------------------
    # Third: standard address pattern.
    # --------------------------------------------------------

    matches = ADDRESS_PATTERN.findall(
        block
    )

    if matches:
        return clean(
            matches[0]
        )

    return None


# ============================================================
# FULL PROPERTY ADDRESS INTELLIGENCE
#
# extract_address() above deliberately keeps its historical contract
# (street-level project_address, byte-compatible). This layer captures
# the MOST COMPLETE address the source actually provides -- street
# number, street name, explicitly stated unit information, and
# city/state/ZIP where the document includes them -- without ever
# inventing missing components. An agenda that states only
# "2000 N Canyon Road" yields street-only components and an
# evidence-backed None for city/state/ZIP.
#
# Preference order mirrors real packets: an explicitly labeled
# property/site/project address outranks the "located at" phrase,
# which outranks a bare street-pattern match. Applicant/staff mailing
# addresses (e.g. the city's own "445 W Center Street, Suite 200")
# are never substituted for the project address: every capture is
# anchored to the project phrase itself.
# ============================================================

ADDRESS_COMPONENT_KEYS = (
    "street_number",
    "street_name",
    "unit",
    "city",
    "state",
    "postal_code",
)

# Explicitly stated unit/designator immediately following a street
# address ("Suite 200", "Unit B", "#12"). Never applied unless the
# source places it directly after the captured address.
ADDRESS_UNIT_TAIL_PATTERN = re.compile(
    r"[ ]*,?[ ]*(?:Unit|Suite|Ste\.?|#)[ ]*:?[ ]*"
    r"(?P<unit>[A-Za-z0-9][A-Za-z0-9\-]{0,9})\b",
    re.IGNORECASE,
)

# Trailing ", City, ST 84604" / ", City, Utah 84604-1234" /
# ", Provo UT" style tails. Requires a comma so ordinary sentence
# continuation can never be mistaken for a city/state pair.
ADDRESS_CITY_STATE_TAIL_PATTERN = re.compile(
    r",[ ]*"
    r"(?P<city>[A-Z][A-Za-z .'\-]{0,39}?)"
    r"[ ]*,?[ ]+"
    r"(?P<state>[A-Z]{2}|[A-Z][a-z]{2,14}(?:[ ]+[A-Z][a-z]{2,14})?)"
    r"[ ]*"
    r"(?P<postal>\d{5}(?:-\d{4})?)?"
    r"(?![A-Za-z0-9])",
)

# Labeled anchors, most authoritative first. Values may sit on the
# same line or on the following line(s) (routing-table style).
PROPERTY_ADDRESS_ANCHOR_LABELS = (
    "Property Address",
    "Site Address",
    "Project Address",
    "Property Location",
)


def _empty_property_address() -> dict:
    """Stable all-absent shape; absence is evidence-backed, never guessed."""

    return {
        "address": None,
        "components": {key: None for key in ADDRESS_COMPONENT_KEYS},
        "completeness": None,
        "anchor": None,
        "confidence": None,
        "evidence": None,
        "source": None,
    }


def _address_core_and_tail(
    candidate: str,
) -> Optional[dict]:
    """
    Street-core capture (same SPECIAL-before-normal precedence as
    extract_address()) plus optional unit/city/state/ZIP tails, taken
    only from characters actually present in the candidate.
    """

    core = (
        SPECIAL_ADDRESS_PATTERN.search(candidate)
        or ADDRESS_PATTERN.search(candidate)
    )

    address_text = None
    components = {key: None for key in ADDRESS_COMPONENT_KEYS}
    matched_end = None

    if core:

        address_text = clean(core.group(0))
        matched_end = core.end()

        components["street_number"] = clean(
            re.match(r"\d{1,6}(?:/\d+)?", address_text).group(0)
        )
        components["street_name"] = clean(
            address_text[
                len(components["street_number"]):
            ].strip(" ,.-")
        ) or None

        completeness = "street_only"

    elif re.search(r"\d", candidate):
        # Unusual jurisdiction format with a number but no recognized
        # street suffix: keep the verbatim text rather than dropping it.
        address_text = clean(candidate)
        completeness = "free_text"

    else:
        return None

    if matched_end is not None:

        unit_match = ADDRESS_UNIT_TAIL_PATTERN.match(
            candidate,
            matched_end,
        )

        if unit_match:
            components["unit"] = clean(unit_match.group("unit"))
            matched_end = unit_match.end()
            completeness = "street_with_unit"

        state_zip_match = ADDRESS_CITY_STATE_TAIL_PATTERN.match(
            candidate,
            matched_end,
        )

        if state_zip_match:

            components["city"] = clean(state_zip_match.group("city"))
            components["state"] = clean(state_zip_match.group("state"))

            postal = clean(state_zip_match.group("postal"))

            components["postal_code"] = (
                postal
                if postal and re.fullmatch(r"\d{5}(?:-\d{4})?", postal)
                else None
            )

            if components["postal_code"]:
                completeness = "full_postal"
            else:
                completeness = "street_city_state"

            matched_end = state_zip_match.end()

        address_text = clean(candidate[:matched_end])

    return {
        "address": address_text,
        "components": components,
        "completeness": completeness,
    }


def _bounded_location_candidate(
    raw_value: str,
) -> str:
    """
    Trim an anchored raw capture to the address-bearing portion:
    stops at a following sentence, a Neighborhood tag, or the next
    labeled field -- whatever comes first.
    """

    value = clean(raw_value) or ""

    value = re.split(
        r"\.\s+[A-Z]|\bNeighborhood\b|\s{2,}",
        value,
        maxsplit=1,
    )[0]

    return value.strip(" .;,") or ""


def _anchor_label_value(
    text: str,
    label: str,
) -> Optional[str]:
    """
    Value of a labeled address field, same-line or on the following
    line(s), stopping before the next recognized field label.
    """

    lines = _labeled_lines(text, label)

    if lines:
        return clean(" ".join(lines))

    return None


def extract_property_address(
    block: str,
) -> dict:
    """
    Most complete evidence-backed property address in an agenda item
    block. See the section comment above for the preference rules.
    Returns the stable shape from _empty_property_address().
    """

    if not block:
        return _empty_property_address()

    attempts: list[tuple[str, str]] = []

    # --------------------------------------------------------
    # First: explicitly labeled property-address fields.
    # --------------------------------------------------------

    for label in PROPERTY_ADDRESS_ANCHOR_LABELS:

        value = _anchor_label_value(block, label)

        if value:
            attempts.append((label.lower(), _bounded_location_candidate(value)))

    # --------------------------------------------------------
    # Second: the "located at" project phrase.
    # --------------------------------------------------------

    located = re.search(
        r"located at\s+(.{5,220}?)"
        r"(?:\.\s+|\bNeighborhood\b|$)",
        block,
        re.IGNORECASE | re.DOTALL,
    )

    if located:
        attempts.append(("located_at", _bounded_location_candidate(located.group(1))))

    # --------------------------------------------------------
    # Third: whole-block street-pattern fallback.
    # --------------------------------------------------------

    bare = (
        SPECIAL_ADDRESS_PATTERN.search(block)
        or ADDRESS_PATTERN.search(block)
    )

    if bare:
        attempts.append(("street_pattern", clean(bare.group(0))))

    for anchor, candidate in attempts:

        if not candidate:
            continue

        intel = _address_core_and_tail(candidate)

        if not intel:
            # A labeled area description with no street address
            # (real Tulsa TMAPC style: "West of North Sheridan Road
            # between East 76th Street North and East 86th Street
            # North") is still genuine government-record location
            # evidence -- captured as-is, flagged as an area.
            if anchor != "street_pattern":
                return {
                    "address": candidate,
                    "components": {
                        key: None for key in ADDRESS_COMPONENT_KEYS
                    },
                    "completeness": "area_description",
                    "anchor": anchor,
                    "confidence": (
                        "MEDIUM" if anchor == "located_at" else "HIGH"
                    ),
                    "evidence": _property_address_evidence(
                        block,
                        candidate,
                    ),
                    "source": "government_record",
                }
            continue

        intel["anchor"] = anchor
        intel["confidence"] = (
            "HIGH" if anchor != "street_pattern" else "MEDIUM"
        )

        # An anchored capture with no recognizable street core and no
        # leading house number is an area/description location (real
        # Tulsa style: "West of North Sheridan Road between East 76th
        # Street North ..."), even when it mentions numbered streets.
        if (
            intel["completeness"] == "free_text"
            and anchor != "street_pattern"
            and not re.match(r"\s*\d", candidate)
        ):
            intel["components"] = {
                key: None for key in ADDRESS_COMPONENT_KEYS
            }
            intel["completeness"] = "area_description"

        intel["evidence"] = _property_address_evidence(
            block,
            intel["address"],
        )
        intel["source"] = "government_record"

        return intel

    return _empty_property_address()


def _property_address_evidence(
    block: str,
    address_text: str,
) -> Optional[str]:
    """Source snippet around the captured address, proving its origin."""

    if not address_text:
        return None

    probe = address_text[:40]
    position = block.find(probe.split(",")[0][:20])

    if position < 0:
        position = 0

    return clean(
        block[
            max(0, position - 60):
            min(len(block), position + len(probe) + 120)
        ]
    )


def parse_address_components(
    address: Optional[str],
) -> dict:
    """
    Split an already-captured address string into its evidence-backed
    components. Components the string does not contain stay None.
    """

    components = {key: None for key in ADDRESS_COMPONENT_KEYS}

    if not address:
        return components

    intel = _address_core_and_tail(clean(address))

    if intel:
        return intel["components"]

    return components


def _property_address_fields(
    intel: dict,
) -> dict:
    """Flatten an extract_property_address() result into record fields."""

    return {
        "property_address_full": intel.get("address"),
        "property_address_components": intel.get("components"),
        "property_address_completeness": intel.get("completeness"),
        "property_address_source": intel.get("source"),
        "property_address_confidence": intel.get("confidence"),
        "property_address_evidence": intel.get("evidence"),
    }


# ============================================================
# NEIGHBORHOOD
# ============================================================

def extract_neighborhood(
    block: str,
) -> Optional[str]:

    match = re.search(
        r"([A-Za-z0-9.'\- ]+?)"
        r"\s+Neighborhood\b",
        block,
        re.IGNORECASE,
    )

    if not match:
        return None

    value = clean(
        match.group(1)
    )

    if not value:
        return None

    # If the regex captured previous sentence text,
    # keep only the final phrase.
    if "." in value:
        value = value.split(
            "."
        )[-1].strip()

    # Remove common leading noise.
    value = re.sub(
        r"^(?:located at|the)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return value or None


# ============================================================
# PROJECT DESCRIPTION
# ============================================================

def extract_description(
    block: str,
) -> Optional[str]:
    """
    Extract the request description between "requests" and
    the case/application identifier, whatever label or format
    the jurisdiction uses for that identifier.
    """

    request_match = re.search(
        r"requests?\s+",
        block,
        re.IGNORECASE,
    )

    if not request_match:
        return None

    # The description ends where the identifier mention (label included)
    # begins. Preserves the original contract: without a terminating
    # identifier there is no bounded description (None), never an
    # unbounded swallow of the rest of the block.
    boundary = next(
        (
            identifier["label_start"]
            for identifier in find_case_identifiers(block)
            if identifier["label_start"] >= request_match.end()
        ),
        None,
    )

    if boundary is None:
        return None

    return clean(
        block[request_match.end():boundary]
    )


# ============================================================
# STAFF CONTACT
# ============================================================

def extract_staff_contact(
    block: str,
    applicant: Optional[str],
) -> dict:
    """
    Extract municipal staff contact information.

    IMPORTANT:
    A city staff email is NOT treated as an applicant email.
    """

    result = {
        "staff_contact_name": None,
        "staff_contact_email": None,
        "staff_contact_phone": None,
    }

    request_match = re.search(
        r"requests?\s+",
        block,
        re.IGNORECASE,
    )

    if not request_match:
        return result

    contact_area = block[
        request_match.end():
    ]

    # Only inspect the contact material before the
    # case/application identifier.
    identifiers = find_case_identifiers(
        contact_area
    )

    if identifiers:
        contact_area = contact_area[
            :identifiers[0]["label_start"]
        ]

    emails = EMAIL_PATTERN.findall(
        contact_area
    )

    phones = PHONE_PATTERN.findall(
        contact_area
    )

    if emails:
        result[
            "staff_contact_email"
        ] = normalize_email(
            emails[-1]
        )

    if phones:
        result[
            "staff_contact_phone"
        ] = normalize_phone(
            phones[-1]
        )

    # --------------------------------------------------------
    # Staff name
    # --------------------------------------------------------

    # The staff name is normally immediately before the phone.
    # Use the final sentence fragment before the phone instead of
    # a broad capitalized-word regex. This prevents values such as
    # "Pleasant View Neighborhood. Dustin Wright" from being captured.
    if result["staff_contact_phone"]:

        # Search using the normalized phone first. If OCR inserted
        # spaces inside the number, fall back to the raw phone regex.
        phone_position = contact_area.find(
            result["staff_contact_phone"]
        )

        if phone_position < 0:
            raw_phone_match = PHONE_PATTERN.search(
                contact_area
            )
            phone_position = (
                raw_phone_match.start()
                if raw_phone_match
                else -1
            )

        before_phone = contact_area[
            max(0, phone_position - 180):
            phone_position
        ] if phone_position >= 0 else contact_area[-180:]

        # Remove email/mailto markup if it occurs before the phone.
        before_phone = re.sub(
            r"\[[^\]]*\]\([^)]*\)",
            " ",
            before_phone,
        )

        # The contact name normally follows the last period.
        fragments = re.split(
            r"[.!?]\s+",
            before_phone,
        )

        candidate = fragments[-1].strip() if fragments else ""

        # Remove common neighborhood/application labels.
        candidate = re.sub(
            r"^(?:Citywide Application|"
            r"[A-Za-z0-9.'\- ]+Neighborhood)\s*[,;:\-]?\s*",
            "",
            candidate,
            flags=re.IGNORECASE,
        )

        # Keep the final plausible person's name.
        name_match = re.search(
            r"([A-Z][A-Za-z.'\-]+"
            r"(?:\s+[A-Z][A-Za-z.'\-]+){1,4})"
            r"\s*$",
            candidate,
        )

        # Direct fallback for PDF/OCR text such as:
        # "Citywide Application. Hannah Salzl "
        direct_name_matches = re.findall(
            r"\b([A-Z][A-Za-z.'\-]+"
            r"(?:\s+[A-Z][A-Za-z.'\-]+){1,3})\s*$",
            candidate,
        )

        if direct_name_matches:
            name_match = re.search(
                r"([A-Z][A-Za-z.'\-]+"
                r"(?:\s+[A-Z][A-Za-z.'\-]+){1,3})\s*$",
                candidate,
            )

        if name_match:
            result[
                "staff_contact_name"
            ] = clean(
                name_match.group(1)
            )

    # Fallback: if the phone-based method failed, inspect the
    # short region immediately before the email.
    if (
        not result["staff_contact_name"]
        and result["staff_contact_email"]
    ):

        email_position = contact_area.lower().find(
            result["staff_contact_email"].lower()
        )

        before_email = contact_area[
            max(0, email_position - 120):
            email_position
        ]

        before_email = re.sub(
            r"\[[^\]]*\]\([^)]*\)",
            " ",
            before_email,
        )

        fragments = re.split(
            r"[.!?]\s+",
            before_email,
        )

        candidate = fragments[-1].strip() if fragments else ""

        name_match = re.search(
            r"([A-Z][A-Za-z.'\-]+"
            r"(?:\s+[A-Z][A-Za-z.'\-]+){1,4})"
            r"\s*$",
            candidate,
        )

        if name_match:
            result[
                "staff_contact_name"
            ] = clean(
                name_match.group(1)
            )

    return result


# ============================================================
# APPLICANT CONTACT
# ============================================================

def extract_applicant_contact(
    block: str,
    applicant: Optional[str],
) -> dict:
    """
    Only assign an email to the applicant when the evidence
    actually places an email with the applicant.

    Municipal @provo.gov contacts are never automatically
    classified as applicant emails.
    """

    result = {
        "applicant_email": None,
        "applicant_phone": None,
    }

    if not applicant:
        return result

    applicant_match = re.search(
        re.escape(applicant),
        block,
        re.IGNORECASE,
    )

    if not applicant_match:
        return result

    # Search only a relatively short region after the
    # applicant name to avoid accidentally grabbing the
    # municipal staff contact.
    local_region = block[
        applicant_match.end():
        applicant_match.end() + 300
    ]

    emails = EMAIL_PATTERN.findall(
        local_region
    )

    phones = PHONE_PATTERN.findall(
        local_region
    )

    # Only accept non-government email addresses.
    # Government staff addresses are not applicant contacts.
    for email in emails:

        normalized = normalize_email(
            email
        )

        if (
            normalized
            and not normalized.endswith("@provo.gov")
            and not normalized.endswith("@provo.com")
        ):
            result[
                "applicant_email"
            ] = normalized
            break

    # Applicant phone is only accepted when it appears
    # directly after the applicant name, not when it is
    # obviously the staff contact phone.
    if phones and result["applicant_email"]:
        result[
            "applicant_phone"
        ] = normalize_phone(
            phones[0]
        )

    return result


# ============================================================
# PARTY ROLES (Owner / Applicant-of-Record / Engineer / Other)
#
# Not every government source labels roles explicitly the way Provo's
# agenda does ("Tyson Reynolds requests..."). Some packets instead use a
# routing-table format that explicitly separates:
#
#   Property Owner / Owner Contact
#   Applicant of Record / Applicant Contact
#   Engineer of Record / Architect of Record
#   Zoning / Total Area / Parcel
#
# These extractors only populate a field when that exact label is present
# in the source text. When a packet never states ownership (e.g. the
# current Provo agenda), every owner_* field below stays None -- an
# evidence-backed None, not a fabricated guess.
# ============================================================

LABELED_LINE_TEMPLATE = r"(?m)^[ \t]*{label}[ \t]*[:\-]?[ \t]+(.+?)[ \t]*$"

# Bound label matching to the document's case-identification block, not its
# full narrative body. Without this, a label like "Zoning" can match a
# sentence deep in a staff report's narrative section that happens to start
# with the same word (e.g. "Zoning Regulations and does not modify...")
# instead of the actual identification table's "Zoning" entry -- observed
# against a real Tulsa County TMAPC staff report (PUD-871), not merely a
# theoretical risk. Identification tables always appear before the staff
# analysis narrative, so this mirrors extract_agenda_section()'s existing
# text[:30000] fallback bound rather than introducing a new pattern.
IDENTIFICATION_SECTION_BOUNDARY_PATTERN = re.compile(
    r"\bSECTION\s+1\b",
    re.IGNORECASE,
)

IDENTIFICATION_REGION_FALLBACK_CHARS = 4000

PARTY_ROLE_LABELS = (
    ("Engineer of Record", "Engineer"),
    ("Architect of Record", "Architect"),
    ("Surveyor of Record", "Surveyor"),
    ("Landscape Architect", "Landscape Architect"),
    ("General Contractor", "Contractor"),
    ("Contractor of Record", "Contractor"),
    ("Attorney of Record", "Attorney"),
    ("Developer of Record", "Developer"),
    ("Representative of Record", "Representative"),
    ("Agent of Record", "Representative"),
)

NAME_CONTACT_PATTERN = re.compile(
    r"^(?P<name>[^|]+?)\s*\|\s*(?P<rest>.+)$"
)


def _identification_region(text: str) -> str:
    """Bound label matching to the case-identification block (see comment above)."""

    boundary = IDENTIFICATION_SECTION_BOUNDARY_PATTERN.search(text)

    if boundary:
        return text[: boundary.start()]

    return text[:IDENTIFICATION_REGION_FALLBACK_CHARS]


# Other field labels this module recognizes. Used only to detect where a
# multi-line value (see _labeled_lines() below) ends -- e.g. a bare
# "Property Owner:" line followed by the entity name on the next line(s),
# stopping before the next field rather than swallowing it.
_KNOWN_LABEL_STARTS = re.compile(
    r"^[ \t]*(?:"
    r"Applicant(?:\s+of\s+Record|\s+Contact)?"
    r"|Agent(?:\s+of\s+Record)?"
    r"|Representative(?:\s+of\s+Record)?"
    r"|Property\s+Owner|Owner(?:\s+of\s+Record|\s+Contact)?"
    r"|Engineer(?:\s+of\s+Record|\s+Contact)?"
    r"|Architect(?:\s+of\s+Record|\s+Contact)?"
    r"|Surveyor\s+of\s+Record|Landscape\s+Architect"
    r"|(?:General\s+)?Contractor(?:\s+of\s+Record)?"
    r"|Attorney(?:\s+of\s+Record)?"
    r"|Developer(?:\s+of\s+Record)?"
    r"|Zoning|Property\s+Location|Tract\s+Size|Total\s+Area|Acreage"
    r"|Parcel(?:\s+(?:Number|ID))?"
    r"|(?:Property\s+|Site\s+|Project\s+)?Address"
    r"|Staff\s+Contact|Prepared\s+by"
    r")\b",
    re.IGNORECASE,
)


def _labeled_value(text: str, label: str) -> Optional[str]:
    """Return the value following an exact `Label ... value` (same-line) field."""

    match = re.search(
        LABELED_LINE_TEMPLATE.format(label=re.escape(label)),
        _identification_region(text),
        re.IGNORECASE,
    )

    if not match:
        return None

    return clean(match.group(1))


def _labeled_lines(text: str, label: str) -> list[str]:
    """
    Value line(s) following a `Label` field that may span multiple lines,
    e.g. "Property Owner:\nBird Creek Ranch...\nc/o Lou Reynolds" -- the
    label alone on its own line, value on the line(s) immediately after it.

    Deliberately NOT used for every label (see _labeled_value() above for
    the same-line-only case): a section header like a bare "Zoning" line
    is followed by unrelated *sub*-fields ("Existing Zoning:", "Proposed
    Zoning:"), not a single continued value, so applying this fallback
    there would swallow the wrong text. Only extract_owner() uses this,
    where a multi-line entity name is a real, observed pattern (a real
    Tulsa County TMAPC staff report, case PUD-871).

    Collection stops at the next blank line or the next recognized field
    label (_KNOWN_LABEL_STARTS). Returns [] when the label isn't present,
    or falls back to _labeled_value()'s same-line match as a single-item
    list when that's how the label appears.
    """

    region = _identification_region(text)

    same_line = re.search(
        LABELED_LINE_TEMPLATE.format(label=re.escape(label)),
        region,
        re.IGNORECASE,
    )

    if same_line:
        value = clean(same_line.group(1))
        return [value] if value else []

    bare_line = re.search(
        rf"(?m)^[ \t]*{re.escape(label)}[ \t]*[:\-]?[ \t]*$",
        region,
        re.IGNORECASE,
    )

    if not bare_line:
        return []

    collected: list[str] = []

    for line in region[bare_line.end():].splitlines():
        stripped = line.strip()

        if not stripped:
            if collected:
                break
            continue

        if _KNOWN_LABEL_STARTS.match(stripped):
            break

        collected.append(stripped)

        if len(collected) >= 3:
            break

    return collected


def _split_name_contact(value: Optional[str]) -> dict:
    """
    Split a routing-table contact cell such as:
        "Robert Thompson | rthompson@tciok.com"
        "Nicole Watts, P.E. | nicole.watts@wallace.design"
    into its name/email/phone parts. Never fabricates a missing part.
    """

    result: dict = {"name": None, "email": None, "phone": None}

    if not value:
        return result

    remainder = value
    name_match = NAME_CONTACT_PATTERN.match(value)

    if name_match:
        result["name"] = clean(name_match.group("name"))
        remainder = name_match.group("rest")

    email_match = EMAIL_PATTERN.search(remainder)
    if email_match:
        result["email"] = normalize_email(email_match.group(0))

    phone_match = PHONE_PATTERN.search(remainder)
    if phone_match:
        result["phone"] = normalize_phone(phone_match.group(0))

    if not name_match and not result["email"] and not result["phone"]:
        result["name"] = clean(value)

    return result


def extract_property_details(text: str) -> dict:
    """
    Property-level facts (zoning/area/parcel), only when explicitly labeled.
    """

    # Specific labels first, same-line and multi-line forms, before the
    # generic bare "Parcel" label: its loose template can otherwise
    # misread a "PARCEL ID:" row's trailing "ID:" as the value.
    parcel = (
        _labeled_value(text, "Parcel Number")
        or _labeled_value(text, "Parcel ID")
    )

    if not parcel:
        # Real Provo routing tables put the label alone on its line with
        # the (often multiple, comma-separated) parcel numbers wrapped
        # across following lines. Joining continuation lines preserves
        # the source commas verbatim.
        parcel_lines = (
            _labeled_lines(text, "Parcel ID")
            or _labeled_lines(text, "Parcel Number")
        )

        if parcel_lines:
            parcel = clean(" ".join(parcel_lines))

    if not parcel:
        bare = _labeled_value(text, "Parcel")

        if bare and not re.fullmatch(
            r"(?i)(?:id|number)\s*:?",
            bare,
        ):
            parcel = bare

    return {
        "zoning": _labeled_value(text, "Zoning"),
        "acreage": _labeled_value(text, "Total Area") or _labeled_value(text, "Acreage"),
        "parcel_number": parcel,
    }


CARE_OF_PATTERN = re.compile(r"^c/o\s+(.+)$", re.IGNORECASE)


def extract_owner(text: str) -> dict:
    """
    Property Owner / Principal, distinct from the Applicant of Record.

    "Property Owner" typically names the legal entity (owner_entity);
    "Owner Contact" typically names the individual principal and their
    email/phone (owner_contact_*). owner_name mirrors whichever of those
    is the more specific, human-facing identity -- the contact person
    when named, otherwise the entity itself.

    Also recognizes a "c/o <Name>" continuation line under a multi-line
    "Property Owner:" entry (a standard real-estate/legal convention for
    naming an entity's contact person) as an owner_contact_name candidate,
    distinct from the entity name itself.
    """

    owner_lines = _labeled_lines(text, "Property Owner") or _labeled_lines(
        text, "Owner of Record"
    )

    owner_entity = None
    care_of_name = None

    for line in owner_lines:
        care_of_match = CARE_OF_PATTERN.match(line)

        if care_of_match:
            care_of_name = clean(care_of_match.group(1))
            continue

        # A line-wrap artifact in the source PDF text can leave a trailing
        # comma on an entity-name line (e.g. "REYNOLDS ASSET MANAGEMENT
        # LLC," immediately before an unrelated field on the next line) --
        # strip it so it never becomes part of the stored entity name. A
        # trailing SEMICOLON is deliberately left alone: real packets use
        # it as a multi-owner list separator (e.g. "PEARSON, JOSEPH BYRD
        # (ET AL); \nADAMS, SUANN P (ET AL)"), and stripping it would fuse
        # two distinct owners into one unreadable string.
        line = line.rstrip(",")

        owner_entity = f"{owner_entity} {line}" if owner_entity else line

    contact = _split_name_contact(_labeled_value(text, "Owner Contact"))
    contact["name"] = contact["name"] or care_of_name

    if not owner_entity and not contact["name"] and not contact["email"]:
        return {
            "owner_name": None,
            "owner_entity": None,
            "owner_type": None,
            "owner_contact_name": None,
            "owner_contact_email": None,
            "owner_contact_phone": None,
            "owner_source": None,
            "owner_confidence": None,
        }

    owner_type = None
    if owner_entity and re.search(
        r"\b(LLC|L\.L\.C\.|Inc\.?|Corp\.?|LP|L\.P\.|Ltd\.?|PC|P\.C\.)\b",
        owner_entity,
        re.IGNORECASE,
    ):
        owner_type = "Entity"
    elif owner_entity or contact["name"]:
        owner_type = "Individual" if not owner_entity else "Entity"

    return {
        "owner_name": contact["name"] or owner_entity,
        "owner_entity": owner_entity,
        "owner_type": owner_type,
        "owner_contact_name": contact["name"],
        "owner_contact_email": contact["email"],
        "owner_contact_phone": contact["phone"],
        "owner_source": "government_record",
        "owner_confidence": "HIGH",
    }


def extract_applicant_of_record(text: str) -> dict:
    """
    Applicant-of-record / agent fields from an explicit routing table.

    Deliberately separate from extract_applicant()/extract_applicant_contact()
    (the "X requests..." pattern used for Provo-style agendas) -- this only
    adds applicant_entity/applicant_contact_* when a packet explicitly labels
    an applicant distinct from the requesting individual. Recognizes the
    exact label "Applicant of Record" or "Agent of Record", and a plain
    "Applicant" label (some case-identification tables label this field
    without the "of Record" suffix -- e.g. a bare "Applicant: <name>" row).
    """

    applicant_entity = (
        _labeled_value(text, "Applicant of Record")
        or _labeled_value(text, "Agent of Record")
        or _labeled_value(text, "Applicant")
    )
    contact = _split_name_contact(_labeled_value(text, "Applicant Contact"))

    if not applicant_entity and not contact["name"] and not contact["email"]:
        return {
            "applicant_entity": None,
            "applicant_contact_name": None,
            "applicant_contact_email": None,
            "applicant_contact_phone": None,
            "applicant_source": None,
            "applicant_confidence": None,
        }

    return {
        "applicant_entity": applicant_entity,
        "applicant_contact_name": contact["name"],
        "applicant_contact_email": contact["email"],
        "applicant_contact_phone": contact["phone"],
        "applicant_source": "government_record",
        "applicant_confidence": "HIGH",
    }


def extract_parties(text: str) -> list[dict]:
    """
    Engineer/architect/other licensed-professional parties, only when
    explicitly labeled. Never infers a party_company from context --
    an email domain matching another party's company is a coincidence,
    not evidence.
    """

    parties: list[dict] = []

    for label, role in PARTY_ROLE_LABELS:
        raw = _labeled_value(text, label)

        if not raw:
            continue

        contact = _split_name_contact(raw)

        if not contact["name"] and not contact["email"]:
            continue

        parties.append(
            {
                "party_name": contact["name"],
                "party_role": role,
                "party_company": None,
                "party_contact_email": contact["email"],
                "party_contact_phone": contact["phone"],
                "party_source": "government_record",
                "party_confidence": "HIGH",
            }
        )

    return parties


# ============================================================
# STAFF-REPORT IDENTITY (Phase 10)
#
# extract_applications() above intentionally operates on the agenda
# section only ("Historical staff-report evidence belongs in the friction
# analyzer"). But real multi-application Provo Planning Commission packets
# ALSO repeat a compact routing table -- "APPLICANT: / PROPERTY OWNER: /
# PARCEL ID: / ACREAGE: / CURRENT LEGAL USE:" -- directly after each
# application's own number reappears in its separate staff-report section,
# further down in the SAME document. This is real, labeled government-
# record evidence (the same shape extract_owner()/extract_applicant_of_
# record()/extract_property_details()/extract_parties() already parse),
# just located outside the agenda section this module otherwise stays
# within. extract_staff_report_identity() scans the FULL document once per
# application, anchored on that application's own number (never on the
# applicant's name, which is not guaranteed unique), and reuses those same
# extractors unchanged against the bounded window found there -- no new
# parsing logic, no fabrication, and no data attributed to the wrong
# application/routing table.
# ============================================================

STAFF_REPORT_WINDOW_CHARS = 3000


def _application_number_positions(text: str, application_number: str) -> list[int]:
    if not text or not application_number:
        return []

    return [
        match.start()
        for match in re.finditer(re.escape(application_number), text, re.IGNORECASE)
    ]


def _next_other_application_number_position(
    text: str,
    application_number: str,
    after: int,
) -> Optional[int]:
    """
    Position of the next DIFFERENT case/application identifier appearing
    after `after`, if any, regardless of jurisdiction format. Used to cap
    a staff-report window so that an application with no routing table of
    its own never absorbs the next application's routing table just
    because nothing distinguishes the text in between.
    """

    for identifier in find_case_identifiers(text):

        if identifier["label_start"] < after:
            continue

        if identifier["value"].upper() != application_number.upper():
            return identifier["label_start"]

    return None


def extract_staff_report_identity(text: str, application_number: Optional[str]) -> dict:
    """
    Property Owner / Applicant-of-Record / property routing-table evidence
    from this specific application's own staff-report section elsewhere in
    the full government packet. Returns the same shape as extract_owner()
    + extract_applicant_of_record() + {"parties": extract_parties(...)}
    combined. Deliberately excludes extract_property_details() (zoning/
    acreage/parcel) -- out of scope for identity/contact intelligence.

    Never fabricates: when this application has no staff-report routing
    table (most municipalities' packets, and Provo's own ordinance text
    amendments/general plan amendments, which have no staff report at
    all), every field stays at its evidence-backed None/[] default exactly
    as those functions already return for empty input.
    """

    empty = {
        **extract_owner(""),
        **extract_applicant_of_record(""),
        "parties": [],
    }

    if not application_number or not text:
        return empty

    for position in _application_number_positions(text, application_number):
        window_end = position + STAFF_REPORT_WINDOW_CHARS

        next_other = _next_other_application_number_position(
            text,
            application_number,
            position + len(application_number),
        )

        if next_other is not None:
            window_end = min(window_end, next_other)

        window = text[position:window_end]

        if "APPLICANT" not in window.upper() and "PROPERTY OWNER" not in window.upper():
            continue

        owner = extract_owner(window)
        applicant_of_record = extract_applicant_of_record(window)
        parties = extract_parties(window)

        found_anything = (
            owner["owner_name"]
            or owner["owner_entity"]
            or applicant_of_record["applicant_entity"]
            or applicant_of_record["applicant_contact_name"]
            or parties
        )

        if found_anything:
            return {
                **owner,
                **applicant_of_record,
                "parties": parties,
            }

    return empty


# ============================================================
# STAFF-REPORT FULL ADDRESS ENRICHMENT
#
# Agenda blocks usually state the project street address without
# city/state/ZIP ("located at 2000 N Canyon Road."). The SAME packet's
# staff reports / applicant letters often carry the fuller form
# ("1507 South 180 East, Provo, UT"). This enrichment scans the same
# per-application staff-report windows used by
# extract_staff_report_identity() and upgrades an application's address
# ONLY with a fuller form of the SAME street -- matched by street
# number plus direction-tolerant street-name tokens -- so the city's
# own mailing address or an unrelated property can never be attached.
# When the agenda block had no usable address at all, only explicitly
# LABELED address fields ("Property Address:", "Site Address:",
# "Project Address:", "Property Location:") are trusted. Parcel IDs
# come solely from explicitly labeled routing-table fields.
#
# Never fabricates: every component is verbatim source text.
# ============================================================

_DIRECTION_TOKEN_ALTERNATIVES = {
    "n": "(?:N|North)",
    "s": "(?:S|South)",
    "e": "(?:E|East)",
    "w": "(?:W|West)",
    "north": "(?:N|North)",
    "south": "(?:S|South)",
    "east": "(?:E|East)",
    "west": "(?:W|West)",
}

_PROPERTY_ADDRESS_COMPLETENESS_RANK = {
    None: 0,
    "free_text": 1,
    "area_description": 2,
    "street_only": 2,
    "street_with_unit": 3,
    "street_city_state": 4,
    "full_postal": 5,
}


def _address_core_tokens(
    address_text: Optional[str],
) -> Optional[list[str]]:
    """
    Street-core tokens (number + street name/direction/suffix words)
    from an already-captured address, for same-street matching.
    """

    if not address_text:
        return None

    core = (
        SPECIAL_ADDRESS_PATTERN.search(address_text)
        or ADDRESS_PATTERN.search(address_text)
    )

    source_text = core.group(0) if core else address_text

    tokens = re.findall(r"[A-Za-z0-9]+", source_text)

    if not tokens or not tokens[0].isdigit():
        return None

    return tokens


def _same_street_pattern(
    address_tokens: list[str],
) -> re.Pattern:
    """
    Flexible regex matching the SAME street with direction-word
    variants ("1507 S 180 E" == "1507 South 180 East"). Non-direction
    tokens must appear verbatim, whitespace-tolerant.
    """

    parts = []

    for token in address_tokens:
        alternative = _DIRECTION_TOKEN_ALTERNATIVES.get(
            token.lower()
        )
        parts.append(
            alternative
            if alternative
            else re.escape(token)
        )

    return re.compile(
        # Trailing boundary keeps short direction alternatives
        # ("E") from matching inside longer words ("East").
        r"\b" + r"\s+".join(parts) + r"\b",
        re.IGNORECASE,
    )


def _staff_report_window_intel(
    window: str,
    application: dict,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Best address upgrade + parcel evidence from one staff-report
    window. Returns (intel_or_None, parcel_or_None).
    """

    parcel = extract_property_details(window).get(
        "parcel_number"
    )

    baseline_full = (
        application.get("property_address_full")
        or application.get("project_address")
    )

    baseline_components = (
        application.get("property_address_components")
        or {}
    )

    baseline_rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
        application.get("property_address_completeness"),
        0,
    ) or (2 if baseline_full else 0)

    address_tokens = _address_core_tokens(baseline_full)

    best_intel = None

    # --------------------------------------------------------
    # Same-street fuller forms.
    # --------------------------------------------------------

    if address_tokens:

        pattern = _same_street_pattern(address_tokens)

        for match in pattern.finditer(window):

            # Bound the tail slice at sentence/neighborhood
            # terminators so a period cannot leak into the captured
            # address while comma tails (", Provo, UT 84601") remain
            # reachable.
            candidate = _bounded_location_candidate(
                window[
                    match.start():match.end() + 120
                ]
            )

            if not candidate:
                continue

            tail = _address_core_and_tail(candidate)

            if not tail or not tail["address"]:
                continue

            candidate_rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
                tail["completeness"],
                0,
            )

            if candidate_rank <= baseline_rank:
                continue

            new_components = {
                **baseline_components,
                **{
                    key: value
                    for key, value in tail["components"].items()
                    if value is not None
                },
            }

            candidate_intel = {
                "property_address_full": tail["address"],
                "property_address_components": new_components,
                "property_address_completeness": tail["completeness"],
                "property_address_source": "government_record",
                "property_address_confidence": "HIGH",
                "property_address_evidence": clean(
                    window[
                        max(0, match.start() - 60):
                        match.end() + 140
                    ]
                ),
            }

            if best_intel is None or candidate_rank > _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
                best_intel["property_address_completeness"],
                0,
            ):
                best_intel = candidate_intel

    # --------------------------------------------------------
    # No usable agenda address: trust explicit labels only.
    # --------------------------------------------------------

    elif not baseline_full:

        for label in PROPERTY_ADDRESS_ANCHOR_LABELS:

            raw = _anchor_label_value(window, label)

            if not raw:
                continue

            candidate = _bounded_location_candidate(raw)

            if not candidate:
                continue

            intel = _address_core_and_tail(candidate)

            if intel and intel["address"]:

                best_intel = {
                    "property_address_full": intel["address"],
                    "property_address_components": intel["components"],
                    "property_address_completeness": intel["completeness"],
                    "property_address_source": "government_record",
                    "property_address_confidence": "HIGH",
                    "property_address_evidence": _property_address_evidence(
                        window,
                        intel["address"],
                    ),
                }

            else:

                best_intel = {
                    "property_address_full": candidate,
                    "property_address_components": {
                        key: None for key in ADDRESS_COMPONENT_KEYS
                    },
                    "property_address_completeness": "area_description",
                    "property_address_source": "government_record",
                    "property_address_confidence": "HIGH",
                    "property_address_evidence": _property_address_evidence(
                        window,
                        candidate,
                    ),
                }

            break

    return best_intel, parcel


def _document_wide_same_street_intel(
    text: str,
    application: dict,
) -> Optional[dict]:
    """
    Best fuller same-street address anywhere in the packet text.

    Applications routinely share one property across several items,
    and the fullest spelling of that address often appears only in
    one item's staff-report letter. Same-street matching (exact
    street number plus direction-tolerant name tokens) keeps this
    safe: a different property cannot collide.
    """

    address_tokens = _address_core_tokens(
        application.get("property_address_full")
        or application.get("project_address")
    )

    if not address_tokens:
        return None

    baseline_components = (
        application.get("property_address_components")
        or {}
    )

    baseline_rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
        application.get("property_address_completeness"),
        0,
    ) or (2 if application.get("property_address_full") else 0)

    pattern = _same_street_pattern(address_tokens)

    best_intel = None
    best_rank = baseline_rank

    for match in pattern.finditer(text):

        candidate = _bounded_location_candidate(
            text[
                match.start():match.end() + 120
            ]
        )

        if not candidate:
            continue

        tail = _address_core_and_tail(candidate)

        if not tail or not tail["address"]:
            continue

        candidate_rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
            tail["completeness"],
            0,
        )

        if candidate_rank <= best_rank:
            continue

        best_rank = candidate_rank
        best_intel = {
            "property_address_full": tail["address"],
            "property_address_components": {
                **baseline_components,
                **{
                    key: value
                    for key, value in tail["components"].items()
                    if value is not None
                },
            },
            "property_address_completeness": tail["completeness"],
            "property_address_source": "government_record",
            "property_address_confidence": "HIGH",
            "property_address_evidence": _property_address_evidence(
                text,
                tail["address"],
            ),
        }

        if best_rank >= _PROPERTY_ADDRESS_COMPLETENESS_RANK["full_postal"]:
            break

    return best_intel


def extract_staff_report_address(
    text: str,
    application: dict,
) -> dict:
    """
    Fuller same-street address + labeled parcel evidence from this
    application's own staff-report material elsewhere in the packet.

    Returns a stable shape of property_address_* fields plus
    parcel_number; every value is None when the packet provides
    nothing beyond what the agenda block already established.
    """

    empty = {
        **_property_address_fields(_empty_property_address()),
        "parcel_number": None,
    }

    if not text or not isinstance(application, dict):
        return empty

    application_number = application.get("application_number")

    if not application_number:
        return empty

    best_intel = None
    best_rank = 0
    parcel_number = application.get("parcel_number")

    for position in _application_number_positions(
        text,
        application_number,
    ):

        window_end = position + STAFF_REPORT_WINDOW_CHARS

        next_other = _next_other_application_number_position(
            text,
            application_number,
            position + len(application_number),
        )

        if next_other is not None:
            window_end = min(window_end, next_other)

        window = text[position:window_end]

        intel, parcel = _staff_report_window_intel(
            window,
            application,
        )

        if parcel and not parcel_number:
            parcel_number = parcel

        if intel:

            rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
                intel["property_address_completeness"],
                0,
            )

            if rank > best_rank:
                best_rank = rank
                best_intel = intel

        if best_intel and best_rank >= _PROPERTY_ADDRESS_COMPLETENESS_RANK["full_postal"]:
            break

    # Document-wide fallback: the fullest same-street form sometimes
    # appears only in another item's letter inside the same packet.
    if best_rank < _PROPERTY_ADDRESS_COMPLETENESS_RANK["full_postal"]:

        document_intel = _document_wide_same_street_intel(
            text,
            application,
        )

        if document_intel:
            rank = _PROPERTY_ADDRESS_COMPLETENESS_RANK.get(
                document_intel["property_address_completeness"],
                0,
            )

            if rank > best_rank:
                best_rank = rank
                best_intel = document_intel

    result = dict(empty)

    if best_intel:
        result.update(best_intel)

    result["parcel_number"] = parcel_number

    return result


# ============================================================
# AGENDA STATUS
# ============================================================

def detect_agenda_status(
    block: str,
) -> list[str]:
    """
    Detect explicit status markers belonging to THIS agenda item.
    """

    upper = block.upper()

    statuses = []

    if "***CONTINUED***" in upper:
        statuses.append(
            "continued"
        )

    return sorted(
        set(statuses)
    )


# ============================================================
# CURRENT APPLICATION EXTRACTION
# ============================================================

def extract_applications(
    text: str,
) -> list[dict]:
    """
    Extract current agenda applications.

    This function intentionally operates on the agenda section
    only. Historical staff-report evidence belongs in the
    friction analyzer.
    """

    agenda = extract_agenda_section(
        text
    )

    items = split_agenda_items(
        agenda
    )

    applications = []

    for item_number, block in items:

        identifier = extract_case_identifier(
            block
        )

        # Study-session or administrative items without
        # a case/application identifier are not applications.
        if not identifier:
            continue

        applicant = extract_applicant(
            block
        )

        staff = extract_staff_contact(
            block,
            applicant,
        )

        applicant_contact = (
            extract_applicant_contact(
                block,
                applicant,
            )
        )

        owner = extract_owner(block)
        applicant_of_record = extract_applicant_of_record(block)
        property_details = extract_property_details(block)
        parties = extract_parties(block)

        application = {
            # Agenda identity
            "item": item_number,

            # Applicant
            "applicant_name": applicant,

            "applicant_email": (
                applicant_contact[
                    "applicant_email"
                ]
            ),

            "applicant_phone": (
                applicant_contact[
                    "applicant_phone"
                ]
            ),

            # Applicant of record / agent (explicit routing-table packets only)
            **applicant_of_record,

            # Property Owner / Principal (explicit routing-table packets only)
            **owner,

            # Engineer / Architect / other licensed professionals
            "parties": parties,

            # Property (zoning/area/parcel, when labeled)
            **property_details,

            # Municipal contact
            "staff_contact_name": (
                staff[
                    "staff_contact_name"
                ]
            ),

            "staff_contact_email": (
                staff[
                    "staff_contact_email"
                ]
            ),

            "staff_contact_phone": (
                staff[
                    "staff_contact_phone"
                ]
            ),

            # Application
            "application_number":
                identifier["value"],

            # Identifier provenance: exact source label ("Case Number",
            # "File No.", ...), canonical type, confidence, and the
            # source snippet proving where the identifier came from.
            "application_id_label":
                identifier["label"],

            "application_id_type":
                identifier["type"],

            "application_id_confidence":
                identifier["confidence"],

            "application_id_evidence":
                identifier["evidence"],

            "application_id_source":
                identifier["source"],

            "application_type":
                extract_application_type(
                    block
                ),

            # Project
            "project_address":
                extract_address(
                    block
                ),

            # Full property address intelligence (street number/name,
            # explicit unit, city/state/ZIP -- each only when the source
            # provides it). project_address above keeps its historical
            # street-level contract; this is the most complete
            # evidence-backed form.
            **_property_address_fields(
                extract_property_address(block)
            ),

            "neighborhood":
                extract_neighborhood(
                    block
                ),

            "project_description":
                extract_description(
                    block
                ),

            # Current agenda status
            "status":
                detect_agenda_status(
                    block
                ),

            # Source
            "source":
                "Provo Planning Commission",

            "source_url":
                (
                    "https://www.provo.gov/"
                    "AgendaCenter/ViewFile/Agenda/"
                    "_08122026-415"
                ),
        }

        applications.append(
            application
        )

    return applications


# ============================================================
# HIGH PRIORITY COMPATIBILITY
# ============================================================

def extract_high_priority_applications(
    text: str,
    minimum_score: int = 20,
) -> list[dict]:
    """
    Compatibility helper.

    Actual friction scoring is intentionally separated into
    friction_analyzer.py so application identity and historical
    evidence are not mixed together.
    """

    return extract_applications(
        text
    )


# ============================================================
# OPTIONAL SINGLE-ITEM HELPER
# ============================================================

def extract_application_from_block(
    block: str,
    item_number: Optional[int] = None,
) -> Optional[dict]:
    """
    Useful for unit tests or future municipal adapters.
    """

    identifier = extract_case_identifier(
        block
    )

    if not identifier:
        return None

    applicant = extract_applicant(
        block
    )

    staff = extract_staff_contact(
        block,
        applicant,
    )

    applicant_contact = (
        extract_applicant_contact(
            block,
            applicant,
        )
    )

    return {
        "item": item_number,

        "applicant_name": applicant,

        "applicant_email": applicant_contact[
            "applicant_email"
        ],

        "applicant_phone": applicant_contact[
            "applicant_phone"
        ],

        **extract_applicant_of_record(block),
        **extract_owner(block),
        "parties": extract_parties(block),
        **extract_property_details(block),

        "staff_contact_name": staff[
            "staff_contact_name"
        ],

        "staff_contact_email": staff[
            "staff_contact_email"
        ],

        "staff_contact_phone": staff[
            "staff_contact_phone"
        ],

        "application_number":
            identifier["value"],

        "application_id_label":
            identifier["label"],

        "application_id_type":
            identifier["type"],

        "application_id_confidence":
            identifier["confidence"],

        "application_id_evidence":
            identifier["evidence"],

        "application_id_source":
            identifier["source"],

        "application_type":
            extract_application_type(
                block
            ),

        "project_address":
            extract_address(
                block
            ),

        **_property_address_fields(
            extract_property_address(block)
        ),

        "neighborhood":
            extract_neighborhood(
                block
            ),

        "project_description":
            extract_description(
                block
            ),

        "status":
            detect_agenda_status(
                block
            ),

        "source":
            "Provo Planning Commission",

        "source_url":
            (
                "https://www.provo.gov/"
                "AgendaCenter/ViewFile/Agenda/"
                "_08122026-415"
            ),
    }