"""
PermitSignal Commercial Lead Intelligence (Phase 6)

Purpose
-------
Turn an already-qualified PermitSignal opportunity/lead record -- Phases
1-5: application extraction, friction analysis, project-date extraction,
opportunity building, applicant/owner identity + contact enrichment,
approval-action intelligence (backend.app.services.
approval_action_intelligence), and lead qualification (backend.app.
services.opportunity_builder.qualify_lead()) -- into a commercially
actionable representation:

    contactability_level            -- how usable the public contact
                                        evidence already on the record is
    commercial_readiness            -- READY_FOR_OUTREACH /
                                        NEEDS_CONTACT_ENRICHMENT /
                                        NEEDS_MORE_PROJECT_EVIDENCE /
                                        NOT_READY
    recommended_commercial_action   -- the next commercial step
    commercial_action_reason        -- why that step was recommended

Design principle
-----------------
This module performs NO new extraction, enrichment, identity matching, or
scoring. It only re-labels fields the pipeline has already computed:

    - lead_status / is_contactable          (opportunity_builder.qualify_lead)
    - applicant_email/phone, contact_email/phone, owner_contact_email/
      phone, applicant_contact_email/phone, and their *_source fields
                                             (applicant_identity /
                                              applicant_enrichment, Phase 2)
    - approval_status / approval_action / approval_basis / approval_reason
                                             (approval_action_intelligence,
                                              Phase 3)
    - owner_name / owner_entity             (application_extractor /
                                              applicant_identity, Phase 2)
    - parties (Engineer/Architect/Contractor/Attorney/Developer/
      Representative/other project participants, each with its own
      party_contact_email/phone/source/confidence)
                                             (application_extractor.
                                              extract_parties()/
                                              extract_staff_report_identity(),
                                              Phase 1/10, and applicant_
                                              enrichment.discovered_parties,
                                              Phase 2)

    The commercial lead behind a project is not always the owner or
    applicant -- it may be a developer, architect, engineer, contractor,
    attorney, or representative named as a distinct party. A contactable
    party of any of these roles is treated as real contact evidence here,
    exactly like an owner/applicant contact.

Every commercial_* claim traces back to one of those existing,
evidence-checked fields -- never a new identity match, never a new contact
guess, never a fabricated business reason to contact someone. If the
underlying evidence is absent, the corresponding commercial_* output is
the conservative "not enough evidence yet" state, never a guess. See
CLAUDE.md Phase 6 / docs/DEVELOPMENT_RULES.md ("Contact Enrichment
Integrity", "Do Not Duplicate Business Logic").

commercial_readiness is a deterministic re-labeling of
opportunity_builder.classify_lead_status() -- already the single source of
truth for "does this project + contact evidence combination qualify as a
lead":

    ARCHIVED               -> NOT_READY
                              (no live future project event)
    NEW                    -> NEEDS_MORE_PROJECT_EVIDENCE
                              (a live event exists, but priority/
                              actionability has not earned qualified-lead
                              status)
    NO_CONTACT             -> NEEDS_CONTACT_ENRICHMENT
                              (qualifies as a real lead; no public contact
                              evidence exists yet)
    QUALIFIED / CONTACTABLE -> READY_FOR_OUTREACH
                              (qualifies as a real lead AND a public
                              contact exists)

This does NOT introduce a second scoring/qualification model -- it is a
one-to-one re-labeling of the existing classification for a commercial
audience.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.services.approval_action_intelligence import (
    BASIS_CONFIRMED,
    BASIS_RECOMMENDATION,
)
from backend.app.services.opportunity_builder import (
    GENERIC_CONTACT_PREFIXES,
    LEAD_STATUS_ARCHIVED,
    LEAD_STATUS_CONTACTABLE,
    LEAD_STATUS_NEW,
    LEAD_STATUS_NO_CONTACT,
    LEAD_STATUS_QUALIFIED,
)


# ============================================================================
# VOCABULARY
# ============================================================================

READINESS_READY_FOR_OUTREACH = "READY_FOR_OUTREACH"
READINESS_NEEDS_CONTACT_ENRICHMENT = "NEEDS_CONTACT_ENRICHMENT"
READINESS_NEEDS_MORE_PROJECT_EVIDENCE = "NEEDS_MORE_PROJECT_EVIDENCE"
READINESS_NOT_READY = "NOT_READY"

_READINESS_BY_LEAD_STATUS = {
    LEAD_STATUS_ARCHIVED: READINESS_NOT_READY,
    LEAD_STATUS_NEW: READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
    LEAD_STATUS_NO_CONTACT: READINESS_NEEDS_CONTACT_ENRICHMENT,
    LEAD_STATUS_QUALIFIED: READINESS_READY_FOR_OUTREACH,
    LEAD_STATUS_CONTACTABLE: READINESS_READY_FOR_OUTREACH,
}

CONTACT_LEVEL_VERIFIED_PERSON = "VERIFIED_PERSON_CONTACT"
CONTACT_LEVEL_VERIFIED_COMPANY = "VERIFIED_COMPANY_CONTACT"
CONTACT_LEVEL_PUBLIC_BUSINESS = "PUBLIC_BUSINESS_CONTACT"
CONTACT_LEVEL_NONE = "NO_VERIFIED_CONTACT"

# Source-type vocabulary actually written by applicant_identity.py /
# applicant_enrichment.py / application_extractor.py (see those modules'
# source_type / *_source fields) -- these strings are not invented here.
_OFFICIAL_SOURCES = {
    "government_record",
    "official_website",
}

# Person-level contact triples already computed upstream: each is a
# (email_field, phone_field, source_field) attributed to a specific named
# individual in the record -- the applicant themselves, an identity/
# enrichment-discovered contact, the property owner's contact, or the
# applicant-of-record's contact. A hit on any of these is a real, named
# person, regardless of source, matching opportunity_builder.contact_tier's
# existing "strong" classification.
_PERSON_CONTACT_TRIPLES = (
    ("applicant_email", "applicant_phone", None),
    ("contact_email", "contact_phone", "contact_source"),
    ("owner_contact_email", "owner_contact_phone", "owner_source"),
    ("applicant_contact_email", "applicant_contact_phone", "applicant_source"),
)

ACTION_HOLD = "hold -- insufficient evidence"
ACTION_MONITOR = "monitor until a relevant project event"
ACTION_INVESTIGATE_DECISION_MAKER = "investigate missing decision-maker"
ACTION_ENRICH_CONTACT = "enrich missing contact information"
ACTION_FOLLOW_UP_APPROVAL = "follow up on an identified approval requirement"
ACTION_CONTACT_OWNER = "contact identified owner/principal"
ACTION_CONTACT_PARTY = "contact identified project party"
ACTION_CONTACT_APPLICANT = "contact applicant/company"

_NON_ACTIONS = {None, "", "unknown", "no immediate action identified"}


# ============================================================================
# HELPERS
# ============================================================================

def _text(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


def _is_generic_email(email: str) -> bool:
    local = email.split("@", 1)[0].lower() if "@" in email else email.lower()

    return local in GENERIC_CONTACT_PREFIXES


def _parties(opportunity: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    parties = opportunity.get("parties")

    if not isinstance(parties, list):
        return []

    return [party for party in parties if isinstance(party, Mapping)]


def find_contactable_party(
    opportunity: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """
    The first party (Engineer/Architect/Contractor/Attorney/Developer/
    Representative/other project participant) with usable public contact
    evidence already attached -- a named professional's phone, or a
    non-generic email. Never fabricates a contact: a party with only a
    name/role and no party_contact_email/phone is not returned here.
    """
    for party in _parties(opportunity):
        phone = _text(party.get("party_contact_phone"))
        email = _text(party.get("party_contact_email"))

        if phone or (email and not _is_generic_email(email)):
            return dict(party)

    return None


# ============================================================================
# CONTACTABILITY
# ============================================================================

def classify_contactability(opportunity: Mapping[str, Any]) -> str:
    """
    Classify the strength/kind of public contact evidence already present
    on a lead record. Never fabricates a value -- it only reads fields the
    identity/enrichment stages already populated.

    Returns one of CONTACT_LEVEL_VERIFIED_PERSON, CONTACT_LEVEL_
    VERIFIED_COMPANY, CONTACT_LEVEL_PUBLIC_BUSINESS, CONTACT_LEVEL_NONE.
    """
    for email_field, phone_field, _source_field in _PERSON_CONTACT_TRIPLES:
        phone = _text(opportunity.get(phone_field))

        if phone:
            return CONTACT_LEVEL_VERIFIED_PERSON

        email = _text(opportunity.get(email_field))

        if email and not _is_generic_email(email):
            return CONTACT_LEVEL_VERIFIED_PERSON

    # A contactable non-owner/applicant project participant (architect,
    # engineer, contractor, attorney, developer, representative, ...) is
    # just as real a commercial contact as a named owner/applicant.
    if find_contactable_party(opportunity) is not None:
        return CONTACT_LEVEL_VERIFIED_PERSON

    # No named person contact. A generic mailbox is still a legitimate
    # public business contact -- distinguish an official company channel
    # from a lower-confidence public listing using the same *_source
    # fields the identity/enrichment stages already recorded.
    for email_field, _phone_field, source_field in _PERSON_CONTACT_TRIPLES:
        email = _text(opportunity.get(email_field))

        if not email or not _is_generic_email(email):
            continue

        source = _text(opportunity.get(source_field)) if source_field else None
        source = source or _text(opportunity.get("email_source"))
        source = source or _text(opportunity.get("company_source"))

        if source in _OFFICIAL_SOURCES:
            return CONTACT_LEVEL_VERIFIED_COMPANY

        return CONTACT_LEVEL_PUBLIC_BUSINESS

    return CONTACT_LEVEL_NONE


# ============================================================================
# COMMERCIAL READINESS
# ============================================================================

def classify_commercial_readiness(opportunity: Mapping[str, Any]) -> str:
    """
    Deterministic re-labeling of opportunity_builder.classify_lead_status()
    for a commercial audience. Does not introduce a second scoring model --
    see module docstring for the full mapping.
    """
    lead_status = opportunity.get("lead_status")

    return _READINESS_BY_LEAD_STATUS.get(lead_status, READINESS_NOT_READY)


# ============================================================================
# RECOMMENDED COMMERCIAL ACTION
# ============================================================================

def recommend_commercial_action(
    opportunity: Mapping[str, Any],
    readiness: str,
    contactability: str,
) -> tuple[str, str]:
    """
    Derive a commercially useful next action and its evidence-backed
    reason. Never invents a business claim -- every branch either quotes
    an existing field (approval_reason, opportunity_reason, owner_name) or
    states the absence of evidence plainly.
    """
    if readiness == READINESS_NOT_READY:
        return (
            ACTION_HOLD,
            "No live project event is currently on record for this "
            "application; there is no active opportunity to act on yet.",
        )

    if readiness == READINESS_NEEDS_MORE_PROJECT_EVIDENCE:
        return (
            ACTION_MONITOR,
            "A future project date is on record, but this application "
            "does not yet meet PermitSignal's priority/actionability bar "
            "for a qualified commercial lead.",
        )

    owner_name = _text(opportunity.get("owner_name")) or _text(
        opportunity.get("owner_entity")
    )
    owner_contact = (
        _text(opportunity.get("owner_contact_name"))
        or _text(opportunity.get("owner_contact_email"))
        or _text(opportunity.get("owner_contact_phone"))
    )

    if readiness == READINESS_NEEDS_CONTACT_ENRICHMENT:
        if owner_name and not owner_contact:
            return (
                ACTION_INVESTIGATE_DECISION_MAKER,
                f"{owner_name} is on record as the property owner/"
                "principal, but no public contact evidence has been "
                "found for them yet.",
            )

        return (
            ACTION_ENRICH_CONTACT,
            "This application meets PermitSignal's lead-qualification "
            "bar, but no public applicant, owner, or company contact has "
            "been found yet.",
        )

    # readiness == READINESS_READY_FOR_OUTREACH
    approval_action = _text(opportunity.get("approval_action"))
    approval_basis = opportunity.get("approval_basis")

    if (
        approval_action not in _NON_ACTIONS
        and approval_basis in (BASIS_CONFIRMED, BASIS_RECOMMENDATION)
    ):
        return (
            ACTION_FOLLOW_UP_APPROVAL,
            _text(opportunity.get("approval_reason"))
            or f"PermitSignal identified a next approval action: "
            f"{approval_action}.",
        )

    if owner_name and contactability in (
        CONTACT_LEVEL_VERIFIED_PERSON,
        CONTACT_LEVEL_VERIFIED_COMPANY,
    ):
        return (
            ACTION_CONTACT_OWNER,
            f"{owner_name} is on record as the property owner/principal "
            "with usable public contact evidence.",
        )

    contactable_party = find_contactable_party(opportunity)

    if contactable_party is not None:
        party_name = _text(contactable_party.get("party_name")) or "An identified project party"
        party_role = _text(contactable_party.get("party_role")) or "project participant"
        party_company = _text(contactable_party.get("party_company"))
        company_clause = f" ({party_company})" if party_company else ""

        return (
            ACTION_CONTACT_PARTY,
            f"{party_name}{company_clause} is on record as the {party_role} "
            "on this project with usable public contact evidence.",
        )

    return (
        ACTION_CONTACT_APPLICANT,
        _text(opportunity.get("opportunity_reason"))
        or "This application is a qualified commercial opportunity with "
        "usable public contact evidence.",
    )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def build_commercial_intelligence(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """
    Derive the four Phase 6 commercial fields for one already-qualified
    opportunity. Returns only those four fields; callers merge them onto
    the opportunity (see apply_commercial_intelligence()).
    """
    contactability = classify_contactability(opportunity)
    readiness = classify_commercial_readiness(opportunity)
    action, reason = recommend_commercial_action(
        opportunity,
        readiness,
        contactability,
    )

    return {
        "contactability_level": contactability,
        "commercial_readiness": readiness,
        "recommended_commercial_action": action,
        "commercial_action_reason": reason,
    }


def apply_commercial_intelligence(
    opportunities: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Additive pipeline stage: attaches the four Phase 6 commercial fields to
    every already-qualified opportunity. Every existing field (including
    lead_status/is_contactable and every Phase 1-5 field) is preserved
    unchanged; only the four commercial_* keys are added/overwritten.
    """
    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        item.update(build_commercial_intelligence(item))
        results.append(item)

    return results


__all__ = [
    "READINESS_READY_FOR_OUTREACH",
    "READINESS_NEEDS_CONTACT_ENRICHMENT",
    "READINESS_NEEDS_MORE_PROJECT_EVIDENCE",
    "READINESS_NOT_READY",
    "CONTACT_LEVEL_VERIFIED_PERSON",
    "CONTACT_LEVEL_VERIFIED_COMPANY",
    "CONTACT_LEVEL_PUBLIC_BUSINESS",
    "CONTACT_LEVEL_NONE",
    "ACTION_HOLD",
    "ACTION_MONITOR",
    "ACTION_INVESTIGATE_DECISION_MAKER",
    "ACTION_ENRICH_CONTACT",
    "ACTION_FOLLOW_UP_APPROVAL",
    "ACTION_CONTACT_OWNER",
    "ACTION_CONTACT_PARTY",
    "ACTION_CONTACT_APPLICANT",
    "find_contactable_party",
    "classify_contactability",
    "classify_commercial_readiness",
    "recommend_commercial_action",
    "build_commercial_intelligence",
    "apply_commercial_intelligence",
]
