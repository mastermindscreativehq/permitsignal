"""
Entity Intelligence Layer — shared models, source hierarchy, and policy.

Purpose
-------
This module defines the canonical entity model used by the deep case
research engine (case_research_engine) and the multi-signal entity
resolver (entity_resolution):

- PERSON / ORGANIZATION / PROPERTY / CASE / GOVERNMENT_STAFF /
  PROFESSIONAL / OTHER entities
- claim-level evidence records tied to sources
- a strict source hierarchy for ranking and verification policy
- deterministic entity/evidence/source keys so repeated research runs
  upsert idempotently instead of duplicating rows

Design principles
-----------------
- Never fabricate a value: absent information stays None with an
  explicit status (not_found / unverified / ambiguous).
- A search snippet alone is NEVER a verified fact; verification requires
  either a government record or fetched page content.
- This module is entirely ADDITIVE to the existing pipeline. It never
  overwrites government-record data on the lead.

Product identity in generated intelligence output:
PROVO ADMINISTRATIVE SERVICES FINANCE.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.services.applicant_enrichment import (
    BUSINESS_DIRECTORY_DOMAINS,
    is_government_url,
)

PRODUCT_NAME = "PROVO ADMINISTRATIVE SERVICES FINANCE"
SCHEMA_VERSION = "1.0"

# =========================================================================
# Vocabularies
# =========================================================================

ENTITY_TYPES = (
    "person",
    "organization",
    "property",
    "case",
    "government_staff",
    "professional",
    "other",
)

# Roles an entity can hold on a specific case.
CASE_ROLES = (
    "applicant",
    "owner",
    "agent",
    "staff",
    "party",
    "related_person",
    "related_organization",
    "property_of_case",
    "case_record",
)

MATCH_STATUSES = (
    "verified",
    "probable",
    "ambiguous",
    "unverified",
    "not_found",
)

VERIFICATION_STATUSES = (
    "verified",      # government record or full fetched official content
    "corroborated",  # fetched public page (non-official) supports the claim
    "unverified",    # search-snippet-only or otherwise unconfirmed
)

DISCOVERY_METHODS = (
    "government_record",
    "web_search",
    "page_fetch",
    "linkedin_search",
    "directory_search",
    "registry_search",
    "lead_seed",
)

CANDIDATE_KINDS = (
    "linkedin_profile",
    "web_result",
    "directory_record",
    "registry_record",
    "government_record",
)

# Source hierarchy. Lower rank = more authoritative.
SOURCE_HIERARCHY = {
    "government_record": 1,
    "official_government": 2,
    "official_company_website": 3,
    "public_registry": 4,
    "professional_profile": 5,
    "business_directory": 6,
    "public_web": 7,
    "search_result": 8,
    "unknown": 99,
}

STATE_REGISTRY_DOMAINS = (
    "opencorporates.com",
    "corporations.utah.gov",
    "businesssearch.utah.gov",
    "secure.utah.gov",
    "bizstandards.utah.gov",
    "sunbiz.org",
    "icis.corp.delaware.gov",
    "ecorp.sos.ga.gov",
    "bis.dsd.wa.gov.au",
)

BUSINESS_DIRECTORY_DOMAINS_SET = set(BUSINESS_DIRECTORY_DOMAINS)


def classify_source(url: Optional[str]) -> tuple[str, int]:
    """
    Classify a URL into (source_type, hierarchy_rank).

    Order of checks matters: registry/professional/directory domains are
    checked before generic web classification so e.g. linkedin.com never
    degrades to public_web.
    """
    if not url:
        return ("unknown", SOURCE_HIERARCHY["unknown"])

    lowered = url.lower().strip()
    domain = _domain_of(lowered)

    if not domain:
        return ("unknown", SOURCE_HIERARCHY["unknown"])

    if is_government_url(url):
        return ("official_government", SOURCE_HIERARCHY["official_government"])

    for registry_domain in STATE_REGISTRY_DOMAINS:
        if domain == registry_domain or domain.endswith("." + registry_domain):
            return ("public_registry", SOURCE_HIERARCHY["public_registry"])

    if domain == "linkedin.com" or domain.endswith(".linkedin.com"):
        return ("professional_profile", SOURCE_HIERARCHY["professional_profile"])

    for directory_domain in BUSINESS_DIRECTORY_DOMAINS_SET:
        if domain == directory_domain or domain.endswith("." + directory_domain):
            return ("business_directory", SOURCE_HIERARCHY["business_directory"])

    return ("public_web", SOURCE_HIERARCHY["public_web"])


def verification_for(source_type: str, fetched_full_page: bool) -> str:
    """
    Decide the verification status of a claim from its source.

    Government records are verified by definition. Claims taken from a
    fully fetched page are corroborated at best unless the source is
    official/government. Search snippets are always unverified.
    """
    if source_type == "government_record":
        return "verified"

    if source_type in ("official_government", "public_registry"):
        return "verified" if fetched_full_page else "corroborated"

    if fetched_full_page:
        return "corroborated"

    return "unverified"


# =========================================================================
# Normalization helpers
# =========================================================================

_ORG_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|llc|l\.l\.c\.|"
    r"lc|l\.c\.|plc|lp|l\.l\.p\.|lllp|pc|p\.c\.|pllc|holdings?|enterprises?)\b\.?",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _domain_of(url_or_email: str) -> str | None:
    value = url_or_email.strip()
    if "@" in value and "://" not in value:
        candidate = value.split("@")[-1]
        return candidate.lower().strip(".") or None
    match = re.search(r"(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})", value.lower())
    if match:
        return match.group(1).strip(".")
    return None


def normalize_person_name(name: Optional[str]) -> str:
    """Lowercase, unicode-folded name without punctuation."""
    if not name:
        return ""
    folded = unicodedata.normalize("NFKD", name)
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = _PUNCT_RE.sub(" ", ascii_name.lower())
    return _WS_RE.sub(" ", cleaned).strip()


def normalize_org_name(name: Optional[str]) -> str:
    """Lowercased org name with legal suffixes removed, for keying only."""
    normalized = normalize_person_name(name)
    if not normalized:
        return ""
    stripped = _ORG_SUFFIX_RE.sub(" ", normalized)
    return _WS_RE.sub(" ", stripped).strip()


def make_entity_key(
    entity_type: str,
    name: Optional[str],
    discriminator: Optional[str] = None,
) -> str:
    """
    Deterministic entity key: '<type>:<hash>' where hash covers type,
    normalized name, and optional discriminator (e.g. city/state or
    address fragment). The same real-world entity discovered across
    multiple research runs produces the same key.
    """
    normalized = (
        normalize_org_name(name) if entity_type in ("organization",)
        else normalize_person_name(name)
    )
    payload = f"{entity_type}|{normalized}|{normalize_person_name(discriminator or '')}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{entity_type}:{digest}"


def make_source_id(url: Optional[str]) -> str:
    return "src:" + hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]


def make_evidence_id(
    subject_key: str,
    claim: str,
    value: Optional[str],
    source_url: Optional[str],
) -> str:
    payload = f"{subject_key}|{claim}|{value or ''}|{source_url or ''}"
    return "ev:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def make_match_id(entity_key: str, candidate_url: Optional[str]) -> str:
    payload = f"{entity_key}|{candidate_url or ''}"
    return "match:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def confidence_label(score: Optional[float]) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.80:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    return "LOW"


# =========================================================================
# Data model
# =========================================================================

@dataclass
class SourceRef:
    url: Optional[str] = None
    title: Optional[str] = None
    discovery_method: str = "web_search"
    fetched_full_page: bool = False
    source_type_override: Optional[str] = None

    def __post_init__(self) -> None:
        self.source_type, self.hierarchy_rank = self._classify()

    def _classify(self) -> tuple[str, int]:
        if self.source_type_override:
            return (self.source_type_override, SOURCE_HIERARCHY.get(self.source_type_override, 99))
        return classify_source(self.url)

    @property
    def source_id(self) -> str:
        return make_source_id(self.url)

    @property
    def domain(self) -> Optional[str]:
        return _domain_of(self.url or "")

    def verification_status(self) -> str:
        return verification_for(self.source_type, self.fetched_full_page)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "source_type": self.source_type,
            "hierarchy_rank": self.hierarchy_rank,
            "discovery_method": self.discovery_method,
            "fetched_full_page": self.fetched_full_page,
            "verification_status": self.verification_status(),
        }


@dataclass
class EvidenceRecord:
    subject_type: str          # 'entity' | 'relationship' | 'property' | 'case'
    subject_key: str           # entity key, property key, or application number
    application_number: str
    claim: str                 # what this evidence supports, e.g. 'email'
    value: Optional[str]       # the claimed value (None when absence observed)
    source: SourceRef
    evidence_text: Optional[str] = None
    confidence: float = 0.0
    discovered_at: str = field(default_factory=now_iso)

    @property
    def evidence_id(self) -> str:
        return make_evidence_id(
            self.subject_key, self.claim, self.value, self.source.url
        )

    @property
    def verification_status(self) -> str:
        return self.source.verification_status()

    def to_dict(self) -> dict[str, Any]:
        d = self.source.to_dict()
        d.update({
            "evidence_id": self.evidence_id,
            "application_number": self.application_number,
            "subject_type": self.subject_type,
            "subject_key": self.subject_key,
            "claim": self.claim,
            "value": self.value,
            "evidence_text": self.evidence_text,
            "confidence": round(float(self.confidence), 4),
            "confidence_label": confidence_label(self.confidence),
            "verification_status": self.verification_status,
            "discovered_at": self.discovered_at,
        })
        return d


@dataclass
class EntityMatch:
    entity_key: str
    candidate_kind: str        # one of CANDIDATE_KINDS
    candidate_name: Optional[str]
    candidate_url: Optional[str]
    match_status: str          # one of MATCH_STATUSES
    match_confidence: float = 0.0
    matched_signals: list[str] = field(default_factory=list)
    conflicting_signals: list[str] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)
    source: Optional[SourceRef] = None

    @property
    def match_id(self) -> str:
        return make_match_id(self.entity_key, self.candidate_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "entity_key": self.entity_key,
            "candidate_kind": self.candidate_kind,
            "candidate_name": self.candidate_name,
            "candidate_url": self.candidate_url,
            "match_status": self.match_status,
            "match_confidence": round(float(self.match_confidence), 4),
            "match_reasons": self.match_reasons,
            "matched_signals": self.matched_signals,
            "conflicting_signals": self.conflicting_signals,
            "source_url": self.source.url if self.source else None,
            "created_at": now_iso(),
        }


@dataclass
class RelationshipRecord:
    subject_entity_key: str
    predicate: str             # e.g. 'owns', 'applies_for', 'employed_by', 'agent_for', 'associated_with'
    object_entity_key: str
    application_number: str
    confidence: float = 0.0
    sources: list[dict] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_entity_key": self.subject_entity_key,
            "predicate": self.predicate,
            "object_entity_key": self.object_entity_key,
            "application_number": self.application_number,
            "confidence": round(float(self.confidence), 4),
            "sources": self.sources,
            "evidence_ids": self.evidence_ids,
            "discovered_at": self.discovered_at,
        }


@dataclass
class EntityRecord:
    entity_key: str
    entity_type: str
    canonical_name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    case_roles: list[str] = field(default_factory=list)
    match_status: str = "unverified"
    match_confidence: float = 0.0
    research_status: str = "NOT_STARTED"   # NOT_STARTED/RESEARCHED/EXHAUSTED/ERROR/SKIPPED
    depth: int = 0                          # BFS depth at which it was discovered
    evidence_ids: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    matches: list[dict] = field(default_factory=list)

    def attach_evidence(self, record: EvidenceRecord) -> bool:
        """Attach one evidence record; returns True when newly added."""
        eid = record.evidence_id
        if eid in self.evidence_ids:
            return False
        existing_values = {
            (e.get("claim"), (e.get("value") or "").lower())
            for e in self.attributes.get("claims", [])
        }
        claim_pair = (record.claim, (record.value or "").lower())
        if claim_pair not in existing_values:
            self.attributes.setdefault("claims", []).append(record.to_dict())
        self.evidence_ids.append(eid)
        src = record.source.to_dict()
        if src["url"] and all(s.get("url") != src["url"] for s in self.sources):
            self.sources.append(src)
        return True

    def best_linkedin(self) -> Optional[dict]:
        candidates = [
            m for m in self.matches if m.get("candidate_kind") == "linkedin_profile"
        ]
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda m: m.get("match_confidence", 0),
            reverse=True,
        )
        return ranked[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_key": self.entity_key,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "attributes": {
                k: v for k, v in self.attributes.items() if k != "claims"
            },
            "claims": self.attributes.get("claims", []),
            "case_roles": self.case_roles,
            "match_status": self.match_status,
            "match_confidence": round(float(self.match_confidence), 4),
            "research_status": self.research_status,
            "depth": self.depth,
            "evidence_ids": list(dict.fromkeys(self.evidence_ids)),
            "sources": self.sources,
            "matches": self.matches,
        }


__all__ = [
    "PRODUCT_NAME",
    "SCHEMA_VERSION",
    "ENTITY_TYPES",
    "CASE_ROLES",
    "MATCH_STATUSES",
    "VERIFICATION_STATUSES",
    "DISCOVERY_METHODS",
    "CANDIDATE_KINDS",
    "SOURCE_HIERARCHY",
    "classify_source",
    "verification_for",
    "normalize_person_name",
    "normalize_org_name",
    "make_entity_key",
    "make_source_id",
    "make_evidence_id",
    "make_match_id",
    "now_iso",
    "confidence_label",
    "SourceRef",
    "EvidenceRecord",
    "EntityMatch",
    "RelationshipRecord",
    "EntityRecord",
]
