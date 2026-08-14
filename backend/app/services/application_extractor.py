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
# APPLICATION NUMBER
# ============================================================

def extract_application_number(
    block: str,
) -> Optional[str]:

    match = APPLICATION_NUMBER_PATTERN.search(
        block
    )

    if not match:
        return None

    return match.group(0).upper()


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
    the government application number.
    """

    match = re.search(
        r"requests?\s+(.+?)"
        r"(?=\bPL[A-Z]{2,6}\d{8}\b)",
        block,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return None

    return clean(
        match.group(1)
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
    # application number.
    application_match = (
        APPLICATION_NUMBER_PATTERN.search(
            contact_area
        )
    )

    if application_match:
        contact_area = contact_area[
            :application_match.start()
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
    r"|Property\s+Owner|Owner(?:\s+of\s+Record|\s+Contact)?"
    r"|Engineer(?:\s+of\s+Record|\s+Contact)?"
    r"|Architect(?:\s+of\s+Record|\s+Contact)?"
    r"|Surveyor\s+of\s+Record|Landscape\s+Architect"
    r"|Zoning|Property\s+Location|Tract\s+Size|Total\s+Area|Acreage"
    r"|Parcel(?:\s+(?:Number|ID))?"
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

    return {
        "zoning": _labeled_value(text, "Zoning"),
        "acreage": _labeled_value(text, "Total Area") or _labeled_value(text, "Acreage"),
        "parcel_number": (
            _labeled_value(text, "Parcel Number")
            or _labeled_value(text, "Parcel ID")
            or _labeled_value(text, "Parcel")
        ),
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

        application_number = (
            extract_application_number(
                block
            )
        )

        # Study-session or administrative items without
        # an application ID are not applications.
        if not application_number:
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
                application_number,

            "application_type":
                extract_application_type(
                    block
                ),

            # Project
            "project_address":
                extract_address(
                    block
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

    application_number = (
        extract_application_number(
            block
        )
    )

    if not application_number:
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
            application_number,

        "application_type":
            extract_application_type(
                block
            ),

        "project_address":
            extract_address(
                block
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