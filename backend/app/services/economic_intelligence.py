"""
PermitSignal Economic Intelligence (Phase 9)

Purpose
-------
Attach two DISTINCT, evidence-first economic dimensions to each already-built
canonical opportunity:

    1. PROJECT VALUE  -- the estimated overall economic scale of the project
       itself (estimated_value_low/high/mid/currency/confidence/
       source_type/basis), and the measurable scale evidence behind it
       (project_scale_units/type/basis).

    2. PUBLIC / GOVERNMENT SPEND -- whether government money is actually
       expected to be spent on the project (public_funding_status/
       confidence/basis, public_spend_low/high/mid/confidence).

These are never the same number. A private developer's $8M townhome project
has an estimated project value of ~$8M and public spend of $0 -- the
government's only role is regulatory approval, not funding. A project
initiated by a government department is flagged as likely public funding,
but this module never claims "confirmed" public spend from applicant-name
pattern matching alone; that requires stronger evidence (an explicit
contract/procurement/budget figure) than this pipeline currently extracts.

Design principle
-----------------
This module performs NO live web lookups and NO fabrication. It only reads:

    application_type   (already normalized by opportunity_builder)
    description         (already-extracted government-record text)
    applicant_name / company_name (already-computed identity fields)

Scale evidence (unit counts, "single-family home") is read verbatim from
description text already extracted from the government packet -- never
invented. Where no disclosed dollar value exists in the record, a value
estimate is built from a per-unit construction-cost BENCHMARK and is always
labeled as an ESTIMATE with its calculation shown (estimated_value_basis),
never presented as an official value. Where no scale evidence exists at
all, estimated_value_* fields stay None with source_type ==
VALUE_SOURCE_NONE -- "insufficient evidence" is always preferred over a
guess.

Public-funding classification is based only on whether the applicant of
record reads as a government department/entity (e.g. "Development
Services", "City of X", a school district) versus a private individual or
company. This is real evidence (who filed the application) applied
conservatively -- it can only produce "likely_public_funding" or
"private_project", never "confirmed_public_funding" or
"government_procurement" (those require budget/contract evidence this
pipeline does not have).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional
import re


# ============================================================================
# VOCABULARY
# ============================================================================

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

VALUE_SOURCE_DISCLOSED = "disclosed_document_value"
VALUE_SOURCE_BENCHMARK = "construction_benchmark_estimate"
VALUE_SOURCE_NONE = "insufficient_evidence"

FUNDING_CONFIRMED = "confirmed_public_funding"
FUNDING_LIKELY = "likely_public_funding"
FUNDING_MIXED = "mixed_public_private"
FUNDING_PRIVATE = "private_project"
FUNDING_PROCUREMENT = "government_procurement"
FUNDING_UNKNOWN = "funding_unknown"
FUNDING_INSUFFICIENT = "insufficient_evidence"

# Application types that are policy/regulatory actions with no discrete
# construction scope to value (a citywide code change, not a buildable
# project). Everything else is treated as potentially having a
# construction scope -- if no scale evidence is found, the value fields
# simply stay None with VALUE_SOURCE_NONE rather than assuming one way or
# the other.
NON_CONSTRUCTION_APPLICATION_TYPES = {
    "ordinance text amendment",
    "general plan amendment",
}

# Applicant-of-record substrings that indicate a government department/
# entity rather than a private individual or company. Deliberately
# conservative -- these are the patterns actually observed in real
# municipal packets (e.g. a city's own "Development Services" department
# as the applicant on a citywide ordinance change).
_GOV_ENTITY_KEYWORDS = (
    "development services",
    "public works",
    "city of ",
    "city corporation",
    "county of ",
    "county government",
    "township of ",
    "school district",
    "redevelopment agency",
    "housing authority",
    "transit authority",
    "water district",
    "municipal corporation",
    "planning commission",
)

# Approximate, per-unit HARD construction-cost benchmarks (USD). These are
# industry-typical ranges, not a project-specific or officially disclosed
# figure -- always surfaced as an ESTIMATE with source_type ==
# VALUE_SOURCE_BENCHMARK, never as an official value. Excludes land, soft
# costs, and local market adjustment.
BENCHMARKS: dict[str, tuple[int, int, str]] = {
    "townhome_residential": (
        200_000,
        320_000,
        "industry benchmark for attached/townhome residential hard construction cost per unit",
    ),
    "single_family": (
        280_000,
        480_000,
        "industry benchmark for a custom/infill single-family home hard construction cost",
    ),
    "flex_office": (
        180_000,
        320_000,
        "industry benchmark for small flex/office space hard construction cost per unit",
    ),
}

_UNIT_COUNT_PATTERN = re.compile(
    r"\b(\d{1,4})[\s-]*(?:unit|units|townhomes?|dwelling\s+units?)\b",
    re.IGNORECASE,
)

_SINGLE_FAMILY_PATTERN = re.compile(
    r"single[- ]family\s+home",
    re.IGNORECASE,
)

_DOLLAR_PATTERN = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|m\b|k\b|thousand)?",
    re.IGNORECASE,
)


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class EconomicIntelligence:
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
# HELPERS
# ============================================================================

def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _looks_like_government_entity(name: str) -> bool:
    lower = name.strip().lower()
    return any(keyword in lower for keyword in _GOV_ENTITY_KEYWORDS)


def _extract_scale(
    description: Optional[str],
) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Read unit-count/asset-type scale evidence verbatim from already-extracted
    description text. Returns (units, scale_type, evidence_snippet).

    Never infers a count that isn't literally present -- "18 townhomes and
    commercial space" yields units=18 for the residential component only;
    it never guesses at the unrepresented commercial square footage.
    """
    if not description:
        return None, None, None

    lower = description.lower()

    if "flex" in lower and "office" in lower:
        scale_type = "flex_office"
    elif "townhome" in lower or "town home" in lower:
        scale_type = "townhome_residential"
    else:
        match = _SINGLE_FAMILY_PATTERN.search(description)
        if match:
            return 1, "single_family", match.group(0)
        return None, None, None

    match = _UNIT_COUNT_PATTERN.search(description)

    if match:
        return int(match.group(1)), scale_type, match.group(0).strip()

    return None, scale_type, None


def _extract_disclosed_value(
    description: Optional[str],
) -> Optional[tuple[float, float, float, str]]:
    """
    Read an explicit dollar figure verbatim from description text, if the
    government record discloses one. Returns (low, high, mid, evidence)
    with low == high == mid for a single disclosed figure. None of the
    current production packets disclose a dollar value -- this exists for
    municipalities/packets that do (spec: "official application valuation").
    """
    if not description:
        return None

    match = _DOLLAR_PATTERN.search(description)

    if not match:
        return None

    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None

    unit = (match.group(2) or "").lower()

    if unit in ("million", "m"):
        value *= 1_000_000
    elif unit in ("k", "thousand"):
        value *= 1_000

    snippet = match.group(0).strip()

    return value, value, value, snippet


# ============================================================================
# MAIN BUILDER
# ============================================================================

def build_economic_intelligence(
    opportunity: Mapping[str, Any],
) -> dict[str, Any]:
    application_type = _text(opportunity.get("application_type"))
    description = _text(opportunity.get("description"))
    applicant = _text(opportunity.get("applicant_name")) or _text(
        opportunity.get("company_name")
    )

    normalized_type = (application_type or "").strip().lower()
    construction_scope = normalized_type not in NON_CONSTRUCTION_APPLICATION_TYPES

    result = EconomicIntelligence()

    # --------------------------------------------------------------------
    # PROJECT VALUE
    # --------------------------------------------------------------------
    if construction_scope:
        units, scale_type, scale_evidence = _extract_scale(description)
        result.project_scale_units = units
        result.project_scale_type = scale_type
        result.project_scale_basis = scale_evidence

        disclosed = _extract_disclosed_value(description)

        if disclosed is not None:
            low, high, mid, evidence = disclosed
            result.estimated_value_low = low
            result.estimated_value_high = high
            result.estimated_value_mid = mid
            result.estimated_value_confidence = CONFIDENCE_MEDIUM
            result.estimated_value_source_type = VALUE_SOURCE_DISCLOSED
            result.estimated_value_basis = (
                f'Dollar figure disclosed in the government record: "{evidence}".'
            )
        elif units and scale_type and scale_type in BENCHMARKS:
            low_per, high_per, label = BENCHMARKS[scale_type]
            low = float(units * low_per)
            high = float(units * high_per)
            result.estimated_value_low = low
            result.estimated_value_high = high
            result.estimated_value_mid = (low + high) / 2
            result.estimated_value_confidence = CONFIDENCE_LOW
            result.estimated_value_source_type = VALUE_SOURCE_BENCHMARK
            caveat = (
                " Covers the residential unit count only; excludes any additional"
                " commercial square footage described in the record."
                if description and "commercial" in description.lower()
                else ""
            )
            result.estimated_value_basis = (
                f"{units} unit(s) x ${low_per:,}-${high_per:,} per unit ({label}) "
                f"= ${low:,.0f}-${high:,.0f}. This is an ESTIMATE, not an official "
                f"project value.{caveat}"
            )
        else:
            result.estimated_value_source_type = VALUE_SOURCE_NONE
            result.estimated_value_basis = (
                "No disclosed value and no extractable project-scale evidence "
                "(unit count, square footage) in the government record."
            )
    else:
        result.estimated_value_source_type = VALUE_SOURCE_NONE
        result.estimated_value_basis = (
            f'"{application_type}" is a policy/regulatory action with no discrete '
            f"construction scope to value."
        )

    # --------------------------------------------------------------------
    # PUBLIC / GOVERNMENT SPEND (distinct from project value above)
    # --------------------------------------------------------------------
    if not applicant:
        result.public_funding_status = FUNDING_UNKNOWN
        result.public_funding_confidence = CONFIDENCE_LOW
        result.public_funding_basis = (
            "No applicant/company on record to evaluate public-funding likelihood."
        )
    elif _looks_like_government_entity(applicant):
        result.public_funding_status = FUNDING_LIKELY
        result.public_funding_confidence = CONFIDENCE_MEDIUM
        result.public_funding_basis = (
            f'Applicant of record ("{applicant}") is a government department/entity, '
            f"not a private individual or company. This suggests likely public "
            f"involvement, but the specific funding source/amount is not confirmed "
            f"by this record."
        )
    else:
        result.public_funding_status = FUNDING_PRIVATE
        result.public_funding_confidence = CONFIDENCE_HIGH
        result.public_funding_basis = (
            f'Applicant of record ("{applicant}") is a private individual/company. '
            f"The government's role on this record is regulatory approval, not "
            f"funding -- private project value is not government spend."
        )

    if result.public_funding_status == FUNDING_PRIVATE:
        result.public_spend_low = 0.0
        result.public_spend_high = 0.0
        result.public_spend_mid = 0.0
        result.public_spend_confidence = CONFIDENCE_HIGH
    elif (
        result.public_funding_status
        in (FUNDING_LIKELY, FUNDING_CONFIRMED, FUNDING_PROCUREMENT)
        and result.estimated_value_low is not None
    ):
        result.public_spend_low = result.estimated_value_low
        result.public_spend_high = result.estimated_value_high
        result.public_spend_mid = result.estimated_value_mid
        result.public_spend_confidence = (
            CONFIDENCE_MEDIUM
            if result.public_funding_status == FUNDING_CONFIRMED
            else CONFIDENCE_LOW
        )
    # FUNDING_MIXED / FUNDING_UNKNOWN / FUNDING_INSUFFICIENT, or no sizable
    # value to attribute: public_spend_* stays None rather than guessing a
    # public/private split with no evidence for the ratio.

    return result.to_dict()


def apply_economic_intelligence(
    opportunities: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Additive pipeline stage: attaches the economic-intelligence fields to
    every already-built opportunity. Every existing field is preserved
    unchanged; only the fields declared on EconomicIntelligence are
    added/overwritten.
    """
    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        item.update(build_economic_intelligence(item))
        results.append(item)

    return results


__all__ = [
    "EconomicIntelligence",
    "build_economic_intelligence",
    "apply_economic_intelligence",
    "BENCHMARKS",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "VALUE_SOURCE_DISCLOSED",
    "VALUE_SOURCE_BENCHMARK",
    "VALUE_SOURCE_NONE",
    "FUNDING_CONFIRMED",
    "FUNDING_LIKELY",
    "FUNDING_MIXED",
    "FUNDING_PRIVATE",
    "FUNDING_PROCUREMENT",
    "FUNDING_UNKNOWN",
    "FUNDING_INSUFFICIENT",
]
