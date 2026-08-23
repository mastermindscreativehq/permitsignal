"""
Deep Case Research Engine — bounded iterative public-web entity research.

Purpose
-------
Starting from one canonical case (an agenda/application already extracted
by the existing pipeline), this engine:

1. seeds normalized entities from the government record
   (CASE, PROPERTY, APPLICANT, OWNER, AGENT/PARTIES, GOVERNMENT STAFF),
2. researches each eligible entity against the public web (SerpAPI +
   polite page fetches), respecting a strict source hierarchy,
3. discovers NEW relevant entities (a person's company, a company's
   people, a related property/case reference) and enqueues them while
   the bounded depth/budget allows,
4. resolves candidate identities with multi-signal scoring
   (never name-only identity),
5. records every claim as evidence tied to a source, discovery method,
   confidence, and verification status,
6. produces an additive, consumer-ready ``case_intelligence`` record on
   the lead (lead["case_intelligence"]) for future PDF/dashboard use.

Integrity rules honored here
-----------------------------
- Government staff are never contacted/researched as leads and never
  merged into applicant identities.
- Search snippets alone stay 'unverified'; only fetched pages corroborate,
  and only government/official sources verify.
- Absent information stays None with an explicit status. Nothing is ever
  invented to fill a field.

Product identity of generated output:
PROVO ADMINISTRATIVE SERVICES FINANCE.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from backend.app.services.applicant_enrichment import (
    clean_text,
    extract_emails,
    extract_phones,
    find_role_person_mentions,
    is_government_email,
    is_map_or_utility_url,
    is_probable_website,
    is_social_url,
    surrounding_text,
    valid_email,
    _looks_like_person_name,
)
from backend.app.services.entity_intelligence import (
    PRODUCT_NAME,
    SCHEMA_VERSION,
    EntityRecord,
    EvidenceRecord,
    RelationshipRecord,
    SourceRef,
    make_entity_key,
    now_iso,
)
from backend.app.services import entity_resolution
from backend.app.services import entity_repository

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 "
        "ProvoAdministrativeServicesFinance/1.0"
    ),
}

ORG_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z&'\.-]+(?:\s+[A-Z][A-Za-z&'\.-]+){0,4})\s*"
    r"(LLC|L\.L\.C\.|LC|L\.C\.|Inc|Incorporated|Corp|Corporation|Co|Company|"
    r"Ltd|Limited|LP|PLLC|PC|Holdings|Group|Partners|Development|Developments|"
    r"Homes|Properties|Realty|Capital|Ventures|Construction|Builders|"
    r"Investment|Investments|Associates|Advisors|Consulting|Engineering|"
    r"Surveying|Surveyors|Companies)\b"
)

# Base confidence by source hierarchy rank (snippet-level evidence).
_RANK_BASE_CONFIDENCE = {
    1: 0.95,
    2: 0.85,
    3: 0.80,
    4: 0.72,
    5: 0.55,
    6: 0.60,
    7: 0.45,
    8: 0.35,
}

SNIPPET_PENALTY = 0.15


def snippet_confidence(source: SourceRef) -> float:
    base = _RANK_BASE_CONFIDENCE.get(source.hierarchy_rank, 0.30)
    return round(max(base - SNIPPET_PENALTY, 0.05), 4)


def page_confidence(source: SourceRef) -> float:
    return round(_RANK_BASE_CONFIDENCE.get(source.hierarchy_rank, 0.30), 4)


# =========================================================================
# Case seeding — government-record entities and relationships
# =========================================================================

def _split_multi_owner(owner_value: Optional[str]) -> list[str]:
    if not owner_value:
        return []
    parts = re.split(r";\s*|\band\b", owner_value, flags=re.IGNORECASE)
    cleaned = []
    for part in parts:
        part = clean_text(part.replace("(ET AL)", "").replace("(et al)", ""))
        if part and part.lower() not in {"not applicable", "n/a", "none"}:
            cleaned.append(part.strip(" .,"))
    return [p for p in cleaned if p]


def _classify_party_type(name: str) -> tuple[str, bool]:
    """
    Classify a seeded party name -> (entity_type, et_al_flag).
    Organizations carry legal-form markers; everything else that fails the
    person-name heuristic is conservatively typed 'other'.
    """
    lowered = name.lower()
    et_al = "et al" in lowered
    stripped = re.sub(r"\(?\s*et\.?\s*al\.?\s*\)?", "", name, flags=re.IGNORECASE).strip()
    if re.search(
        r"\b(llc|l\.l\.c\.|lc|inc|corp|corporation|company|co\b|ltd|limited|lp\b|"
        r"plc|holdings|partners|development|properties|realty|capital|ventures|"
        r"construction|builders|group|university|foundation|mining)\b",
        lowered,
    ):
        return ("organization", et_al)
    # Government owner blocks are ALL-CAPS ("PEARSON, JOSEPH BYRD"); the
    # shared person-name heuristic rejects shouting, so evaluate in title
    # case without touching the canonical name itself.
    candidate = stripped
    if candidate.isupper():
        candidate = candidate.title()
    if _looks_like_person_name(candidate):
        return ("person", et_al)
    return ("other", et_al)


def seed_entities_from_lead(lead: dict[str, Any]) -> tuple[
    dict[str, EntityRecord],
    list[RelationshipRecord],
]:
    """
    Build the deterministic, government-backed seed graph for one case.

    Returns (entities_by_key, seed_relationships). Every seed carries a
    government_record source and 'verified' provenance claims; nothing
    here involves the public web yet.
    """
    app_number = str(lead.get("application_number") or "").strip()
    municipality = str(lead.get("municipality") or "Provo")
    state = str(lead.get("state") or "Utah")
    location = f"{municipality}, {state}".strip(", ")
    address = clean_text(str(lead.get("project_address") or ""))

    entities: dict[str, EntityRecord] = {}
    relationships: list[RelationshipRecord] = []

    def register(entity: EntityRecord) -> EntityRecord:
        existing = entities.get(entity.entity_key)
        if existing:
            for role in entity.case_roles:
                if role not in existing.case_roles:
                    existing.case_roles.append(role)
            return existing
        entities[entity.entity_key] = entity
        return entity

    def gov_source() -> SourceRef:
        return SourceRef(
            url=lead.get("source_url"),
            title=f"{municipality} Planning Commission record",
            discovery_method="government_record",
            source_type_override="government_record",
        )

    def add_claim(entity: EntityRecord, claim: str, value: Optional[str], src: SourceRef, text=None) -> None:
        if value in (None, ""):
            return
        entity.attach_evidence(EvidenceRecord(
            subject_type="entity",
            subject_key=entity.entity_key,
            application_number=app_number,
            claim=claim,
            value=value,
            source=src,
            evidence_text=text,
            confidence=_RANK_BASE_CONFIDENCE[1],
        ))

    # --- CASE -----------------------------------------------------------
    case = register(EntityRecord(
        entity_key=make_entity_key("case", app_number),
        entity_type="case",
        canonical_name=app_number,
        case_roles=["case_record"],
        match_status="verified",
        match_confidence=0.99,
        research_status="GOVERNMENT_RECORD",
        attributes={
            "application_number": app_number,
            "application_type": lead.get("application_type"),
            "status": lead.get("status"),
            "description": lead.get("description"),
            "source": lead.get("source"),
            "next_project_date": lead.get("next_project_date"),
            "next_project_event": lead.get("next_project_event"),
            "next_project_time": lead.get("next_project_time"),
        },
    ))

    # --- PROPERTY ---------------------------------------------------------
    property_entity: Optional[EntityRecord] = None
    if address or lead.get("parcel_number"):
        property_entity = register(EntityRecord(
            entity_key=make_entity_key("property", address or lead.get("parcel_number"), location),
            entity_type="property",
            canonical_name=address or str(lead.get("parcel_number")),
            case_roles=["property_of_case"],
            match_status="verified",
            match_confidence=0.95,
            research_status="GOVERNMENT_RECORD",
            attributes={
                "address": address or None,
                "parcel_number": lead.get("parcel_number"),
                "zoning": lead.get("zoning"),
                "acreage": lead.get("acreage"),
                "neighborhood": lead.get("neighborhood"),
                "location": location,
                "application_number": app_number,
            },
        ))
        add_claim(property_entity, "address", address or None, gov_source())
        add_claim(property_entity, "parcel_number", lead.get("parcel_number"), gov_source())
        add_claim(property_entity, "zoning", lead.get("zoning"), gov_source())
        relationships.append(RelationshipRecord(
            subject_entity_key=case.entity_key,
            predicate="concerns_property",
            object_entity_key=property_entity.entity_key,
            application_number=app_number,
            confidence=0.95,
            sources=[gov_source().to_dict()],
        ))

    # --- APPLICANT --------------------------------------------------------
    applicant_name = clean_name_for_seed(lead.get("applicant_name"))
    if applicant_name:
        ptype, et_al = _classify_party_type(applicant_name)
        applicant_type = ptype if ptype in ("person", "organization") else "other"
        applicant = register(EntityRecord(
            entity_key=make_entity_key(applicant_type, applicant_name, location),
            entity_type=applicant_type,
            canonical_name=applicant_name,
            case_roles=["applicant"],
            match_status="verified",
            match_confidence=0.95,
            research_status="GOVERNMENT_RECORD",
            attributes={"location": location, "application_number": app_number},
        ))
        if et_al:
            applicant.attributes["et_al"] = True
        add_claim(applicant, "role", "applicant", gov_source(), "Listed as applicant in the government record")
        add_claim(applicant, "email", lead.get("applicant_email"), gov_source())
        add_claim(applicant, "phone", lead.get("applicant_phone"), gov_source())
        add_claim(applicant, "contact_name", lead.get("applicant_contact_name"), gov_source())
        add_claim(applicant, "contact_email", lead.get("applicant_contact_email"), gov_source())
        add_claim(applicant, "contact_phone", lead.get("applicant_contact_phone"), gov_source())
        applicant_company = clean_name_for_seed(lead.get("applicant_entity") or lead.get("company_name"))
        if applicant_company and normalize_org(applicant_company) != normalize_org(applicant_name):
            org = register(EntityRecord(
                entity_key=make_entity_key("organization", applicant_company, location),
                entity_type="organization",
                canonical_name=applicant_company,
                case_roles=["related_organization"],
                match_status="verified",
                match_confidence=0.90,
                research_status="GOVERNMENT_RECORD",
                attributes={"location": location, "application_number": app_number},
            ))
            add_claim(org, "website", lead.get("company_website"), gov_source())
            relationships.append(RelationshipRecord(
                subject_entity_key=applicant.entity_key,
                predicate="affiliated_with",
                object_entity_key=org.entity_key,
                application_number=app_number,
                confidence=0.90,
                sources=[gov_source().to_dict()],
            ))
        relationships.append(RelationshipRecord(
            subject_entity_key=applicant.entity_key,
            predicate="applies_for",
            object_entity_key=case.entity_key,
            application_number=app_number,
            confidence=0.95,
            sources=[gov_source().to_dict()],
        ))
        if property_entity:
            relationships.append(RelationshipRecord(
                subject_entity_key=applicant.entity_key,
                predicate="associated_with",
                object_entity_key=property_entity.entity_key,
                application_number=app_number,
                confidence=0.90,
                sources=[gov_source().to_dict()],
            ))

    # --- OWNERS -----------------------------------------------------------
    owner_names = _split_multi_owner(lead.get("owner_name"))
    for owner_name in owner_names:
        ptype, et_al = _classify_party_type(owner_name)
        owner_type = ptype if ptype in ("person", "organization") else "other"
        owner = register(EntityRecord(
            entity_key=make_entity_key(owner_type, owner_name, location),
            entity_type=owner_type,
            canonical_name=owner_name,
            case_roles=["owner"],
            match_status="verified",
            match_confidence=0.95,
            research_status="GOVERNMENT_RECORD",
            attributes={"location": location, "application_number": app_number},
        ))
        if et_al:
            owner.attributes["et_al"] = True
        add_claim(owner, "role", "property owner", gov_source(), "Listed as owner in the government record")
        add_claim(owner, "contact_name", lead.get("owner_contact_name"), gov_source())
        add_claim(owner, "contact_email", lead.get("owner_contact_email"), gov_source())
        add_claim(owner, "contact_phone", lead.get("owner_contact_phone"), gov_source())
        add_claim(owner, "website", lead.get("owner_website"), gov_source())
        if property_entity:
            relationships.append(RelationshipRecord(
                subject_entity_key=owner.entity_key,
                predicate="owns",
                object_entity_key=property_entity.entity_key,
                application_number=app_number,
                confidence=0.95,
                sources=[gov_source().to_dict()],
            ))

    owner_entities = [
        e for e in entities.values()
        if e.entity_type == "organization" and clean_name_for_seed(lead.get("owner_entity")) == e.canonical_name
    ]
    owner_entity_name = clean_name_for_seed(lead.get("owner_entity"))
    raw_owner_value = clean_text(str(lead.get("owner_name") or ""))
    # Some government records repeat the full multi-owner block in the
    # owner_entity field; that is NOT a distinct organization.
    composite_duplicate = bool(
        owner_entity_name
        and er_normalize(owner_entity_name) == er_normalize(raw_owner_value)
    )
    if not owner_entities and owner_entity_name and not composite_duplicate \
            and _classify_party_type(owner_entity_name)[0] == "organization":
        owner_org = register(EntityRecord(
            entity_key=make_entity_key("organization", owner_entity_name, location),
            entity_type="organization",
            canonical_name=owner_entity_name,
            case_roles=["owner"],
            match_status="verified",
            match_confidence=0.95,
            research_status="GOVERNMENT_RECORD",
            attributes={"location": location, "application_number": app_number},
        ))
        if property_entity:
            relationships.append(RelationshipRecord(
                subject_entity_key=owner_org.entity_key,
                predicate="owns",
                object_entity_key=property_entity.entity_key,
                application_number=app_number,
                confidence=0.95,
                sources=[gov_source().to_dict()],
            ))

    # --- PARTIES / AGENTS ---------------------------------------------------
    for party in lead.get("parties") or []:
        pname = clean_name_for_seed(party.get("party_name"))
        if not pname:
            continue
        prole = clean_text(str(party.get("party_role") or "")) or None
        ptype, et_al = _classify_party_type(pname)
        party_type = ptype if ptype in ("person", "organization") else "professional" if prole else "other"
        entity = register(EntityRecord(
            entity_key=make_entity_key(party_type, pname, location),
            entity_type=party_type,
            canonical_name=pname,
            case_roles=["agent" if (prole and "agent" in prole.lower()) else "party"],
            match_status="verified",
            match_confidence=0.90,
            research_status="GOVERNMENT_RECORD",
            attributes={"location": location, "application_number": app_number},
        ))
        if prole:
            add_claim(entity, "role", prole, gov_source())
        add_claim(entity, "email", party.get("party_contact_email"), gov_source())
        add_claim(entity, "phone", party.get("party_contact_phone"), gov_source())

    # --- GOVERNMENT STAFF (recorded, never researched/enriched) -------------
    staff_name = clean_name_for_seed(lead.get("staff_contact_name"))
    if staff_name:
        staff = register(EntityRecord(
            entity_key=make_entity_key("government_staff", staff_name, municipality),
            entity_type="government_staff",
            canonical_name=staff_name,
            case_roles=["staff"],
            match_status="verified",
            match_confidence=0.95,
            research_status="GOVERNMENT_RECORD_NOT_RESEARCHED",
            attributes={"location": location, "municipality": municipality},
        ))
        add_claim(staff, "role", "government staff", gov_source())
        add_claim(staff, "email", lead.get("staff_contact_email"), gov_source())
        add_claim(staff, "phone", lead.get("staff_contact_phone"), gov_source())

    return entities, relationships


def clean_name_for_seed(value: Any) -> Optional[str]:
    text = clean_text(str(value or ""))
    return text or None


def normalize_org(name: Optional[str]) -> str:
    from backend.app.services.entity_intelligence import normalize_org_name
    return normalize_org_name(name)


# =========================================================================
# Research engine
# =========================================================================

class CaseResearchEngine:
    """
    Bounded iterative researcher for one case.

    Budgets (defaults): depth<=2, <=30 search queries, <=10 page fetches,
    <=14 entities total. Government-staff entities are never researched.
    """

    RESEARCHABLE_TYPES = {"person", "organization", "professional"}

    def __init__(
        self,
        lead: dict[str, Any],
        session: Optional[requests.Session] = None,
        serpapi_key: Optional[str] = None,
        max_depth: int = 2,
        max_queries: int = 30,
        max_pages: int = 10,
        max_entities: int = 14,
        request_delay: float = 0.3,
    ) -> None:
        self.lead = lead
        self.session = session or self._create_session()
        # serpapi_key=None -> auto-detect from environment; an explicit
        # empty string disables public-web search deterministically
        # (tests, offline seed-only builds).
        if serpapi_key is None:
            self.serpapi_key = os.environ.get("SERPAPI_API_KEY")
        else:
            self.serpapi_key = serpapi_key or None
        self.max_depth = max_depth
        self.max_queries = max_queries
        self.max_pages = max_pages
        self.max_entities = max_entities
        self.request_delay = request_delay

        self.entities: dict[str, EntityRecord] = {}
        self.relationships: list[RelationshipRecord] = []
        self.evidence_index: dict[str, dict] = {}
        self.sources_index: dict[str, dict] = {}

        self.queries_used = 0
        self.pages_fetched = 0
        self.errors: list[dict] = []
        self._fetched_urls: set[str] = set()
        self._page_cache: dict[str, tuple[str, str]] = {}

        self.run_id = str(uuid.uuid4())
        self.started_at = now_iso()

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    def _create_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        return session

    def _error(self, where: str, message: str) -> None:
        self.errors.append({"where": where, "error": str(message)[:300], "at": now_iso()})

    # -- public entry point -------------------------------------------------

    def run(self) -> dict[str, Any]:
        seed_entities, seed_relationships = seed_entities_from_lead(self.lead)
        self.entities = seed_entities
        self.relationships = list(seed_relationships)
        for entity in self.entities.values():
            for claim in entity.attributes.get("claims", []):
                eid = claim.get("evidence_id")
                if eid:
                    self.evidence_index[eid] = claim
            for src in entity.sources:
                if src.get("url"):
                    from backend.app.services.entity_intelligence import make_source_id
                    self.sources_index[make_source_id(src["url"])] = src

        processed: set[str] = set()
        depth_reached = 0

        # Role priority: the applicant and their organization are researched
        # before owners/parties so scarce query budget follows lead value.
        rank_by_role = {"applicant": 0, "related_organization": 1,
                        "property_of_case": 2, "owner": 3, "party": 4,
                        "agent": 4}

        def _sort_key(item):
            depth, key = item
            entity = self.entities[key]
            ranks = [rank_by_role.get(str(role), 4) for role in (entity.case_roles or [])]
            return (depth, min(ranks) if ranks else 4, key)

        while True:
            pending = [
                (e.depth, key)
                for key, e in self.entities.items()
                if key not in processed
                and e.research_status == "GOVERNMENT_RECORD"
                and e.depth <= self.max_depth
            ]
            if not pending:
                break
            pending.sort(key=_sort_key)
            _, key = pending[0]
            entity = self.entities[key]
            processed.add(key)

            if entity.entity_type not in self.RESEARCHABLE_TYPES:
                entity.research_status = "NOT_RESEARCHABLE"
                continue
            if self.queries_used >= self.max_queries and self.pages_fetched >= self.max_pages:
                entity.research_status = "BUDGET_EXHAUSTED"
                continue

            depth_reached = max(depth_reached, entity.depth)
            self.research_entity(entity, entity.depth)

        self.completed_at = now_iso()
        return self.build_case_intelligence(depth_reached=depth_reached)

    # -- research actions ----------------------------------------------------

    def research_entity(self, entity: EntityRecord, depth: int) -> None:
        entity.research_status = "RESEARCHED"

        queries = self._queries_for(entity)
        results = []
        for query in queries:
            if self.queries_used >= self.max_queries:
                entity.research_status = "BUDGET_EXHAUSTED"
                break
            batch = self._search(query)
            self.queries_used += 1
            results.extend(batch)
            time.sleep(self.request_delay)

        if not results:
            entity.attributes.setdefault("research_notes", []).append(
                "No public-web results retrieved"
            )

        candidates = self._candidates_from_results(results)
        self._collect_snippet_evidence(entity, results)
        self._discover_org_from_snippets(entity, results, depth)
        self._resolve_matches(entity, candidates)

        if self.pages_fetched < self.max_pages:
            self._fetch_top_pages(entity, candidates, depth)

    def _queries_for(self, entity: EntityRecord) -> list[str]:
        location = str(entity.attributes.get("location") or "Provo, Utah")
        name = entity.canonical_name
        quoted = f'"{name}"'
        queries: list[str] = []
        if entity.entity_type in ("person", "professional"):
            org = entity.attributes.get("organization") or entity.attributes.get("employer")
            queries.append(f'{quoted} "{location}"')
            if org:
                queries.append(f'{quoted} "{org}"')
            queries.append(f"{quoted} LinkedIn")
        elif entity.entity_type == "organization":
            queries.append(f'{quoted} "{location}"')
            queries.append(f'{quoted} Utah business entity')
            queries.append(f"{quoted} LinkedIn")
        elif entity.entity_type == "property":
            parcel = entity.attributes.get("parcel_number")
            if parcel:
                queries.append(f'"{parcel}"')
        return queries

    def _search(self, query: str) -> list[dict]:
        if not self.serpapi_key:
            self._error("search", "SERPAPI_API_KEY not configured; public-web research degraded to government-record seeds")
            return []
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": self.serpapi_key,
                "num": 8,
            }
            location_env = os.environ.get("SERPAPI_LOCATION")
            if location_env:
                params["location"] = location_env
            resp = self.session.get(
                "https://serpapi.com/search.json", params=params, timeout=20
            )
            if resp.status_code == 200:
                payload = resp.json()
                return payload.get("organic_results", []) or []
            if resp.status_code == 429:
                self._error("search", f"Rate limit hit on: {query}")
                time.sleep(1.5)
                return []
            self._error("search", f"HTTP {resp.status_code} on: {query}")
        except Exception as exc:
            self._error("search", exc)
        return []

    @staticmethod
    def _candidates_from_results(results: list[dict]) -> list[dict]:
        candidates = []
        seen_urls = set()
        for r in results:
            url = str(r.get("link") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append({
                "name": r.get("title"),
                "url": url,
                "text": f"{r.get('title') or ''}\n{r.get('snippet') or ''}",
                "domain": (r.get("link") or ""),
                "kind": "linkedin_profile" if "linkedin.com" in url.lower() else "web_result",
            })
        return candidates

    # -- evidence ------------------------------------------------------------

    def _register_source(self, source: SourceRef) -> dict:
        entry = source.to_dict()
        self.sources_index[source.source_id] = entry
        return entry

    def _add_evidence(
        self,
        entity: EntityRecord,
        claim: str,
        value: Optional[str],
        source: SourceRef,
        text: Optional[str],
        confidence: float,
    ) -> None:
        if value in (None, "", []):
            return
        record = EvidenceRecord(
            subject_type="entity",
            subject_key=entity.entity_key,
            application_number=str(self.lead.get("application_number") or ""),
            claim=claim,
            value=value if isinstance(value, str) else str(value),
            source=source,
            evidence_text=(text[:240] if text else None),
            confidence=confidence,
        )
        if entity.attach_evidence(record):
            self.evidence_index[record.evidence_id] = record.to_dict()
            self._register_source(source)

    def _collect_snippet_evidence(self, entity: EntityRecord, results: list[dict]) -> None:
        for r in results:
            title = str(r.get("title") or "")
            snippet = str(r.get("snippet") or "")
            combined = f"{title}\n{snippet}"
            source = SourceRef(
                url=r.get("link"),
                title=title,
                discovery_method="web_search",
                fetched_full_page=False,
            )

            for email in extract_emails(combined):
                if valid_email(email) and not is_government_email(email):
                    local = email.split("@")[0].lower()
                    if local.startswith(("info.", "contact.", "admin.")):
                        continue
                    self._add_evidence(
                        entity, "email", email.lower().removeprefix("mailto:"),
                        source, surrounding_text(combined, email, radius=120),
                        snippet_confidence(source),
                    )
            for phone in extract_phones(combined):
                self._add_evidence(
                    entity, "phone", clean_text(phone), source,
                    surrounding_text(combined, phone, radius=120),
                    snippet_confidence(source),
                )
            if (
                is_probable_website(r.get("link") or "")
                and not is_social_url(r.get("link") or "")
                and not is_map_or_utility_url(r.get("link") or "")
                and entity.entity_type == "organization"
                and not entity.attributes.get("website")
            ):
                self._add_evidence(
                    entity, "website", r.get("link"), source, title,
                    snippet_confidence(source),
                )
            if "linkedin.com" in (r.get("link") or "").lower():
                self._add_evidence(
                    entity, "linkedin_mention", r.get("link"), source,
                    snippet or title, snippet_confidence(source),
                )

    # -- matching ---------------------------------------------------------------

    def _resolve_matches(self, entity: EntityRecord, candidates: list[dict]) -> None:
        resolved = entity_resolution.resolve_entity(entity, candidates)
        for m in resolved:
            md = m.to_dict()
            if md["match_status"] == "not_found" and not md.get("candidate_url"):
                entity.match_status = "not_found"
                entity.match_confidence = 0.0
                entity.attributes["identity_resolution"] = {
                    "match_status": "not_found",
                    "match_reasons": ["No public-web candidates were available to evaluate"],
                }
                continue
            entity.matches.append(md)
        best = next((m for m in resolved if m.match_status != "not_found" and m.candidate_url), None)
        if best:
            entity.match_status = best.match_status
            entity.match_confidence = best.match_confidence
            if (
                best.candidate_kind == "linkedin_profile"
                and best.match_status in ("verified", "probable")
            ):
                entity.attributes["linkedin_url"] = best.candidate_url

    # -- page fetching & new-entity discovery -------------------------------------

    def _fetch_top_pages(self, entity: EntityRecord, candidates: list[dict], depth: int) -> None:
        preferred = [
            c for c in candidates
            if c.get("url")
            and not is_social_url(c["url"])
            and not is_map_or_utility_url(c["url"])
            and not ("facebook.com" in c["url"].lower())
        ]
        preferred.sort(key=lambda c: 0 if self._official_preferring(c) else 1)
        for candidate in preferred[:2]:
            if self.pages_fetched >= self.max_pages:
                break
            url = candidate["url"]
            cached = self._page_cache.get(url)
            if cached is not None:
                text, title = cached
            else:
                html = self._safe_fetch(url)
                self.pages_fetched += 1
                self._fetched_urls.add(url)
                if not html:
                    continue
                text, title = self._extract_text(html)
                self._page_cache[url] = (text, title)
            if len(text) < 60:
                continue
            source = SourceRef(
                url=url,
                title=title or candidate.get("name"),
                discovery_method="page_fetch",
                fetched_full_page=True,
            )
            self._harvest_page(entity, text, source, depth)

    @staticmethod
    def _official_preferring(candidate: dict) -> bool:
        domain = str(candidate.get("domain") or "").lower()
        return ".gov" in domain or ".us" in domain

    def _safe_fetch(self, url: str, timeout: int = 15) -> Optional[str]:
        try:
            resp = self.session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code < 400:
                return resp.text
        except Exception as exc:
            self._error("page_fetch", exc)
        return None

    @staticmethod
    def _extract_text(html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "lxml")
        title = (soup.title.string or "").strip() if soup.title else ""
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True), title

    def _harvest_page(
        self,
        entity: EntityRecord,
        text: str,
        source: SourceRef,
        depth: int,
    ) -> None:
        self._register_source(source)
        conf = page_confidence(source)

        for email in extract_emails(text):
            if valid_email(email) and not is_government_email(email):
                self._add_evidence(
                    entity, "email", email.lower(), source,
                    surrounding_text(text, email), conf,
                )
        for phone in extract_phones(text):
            self._add_evidence(
                entity, "phone", clean_text(phone), source,
                surrounding_text(text, phone), conf,
            )
        if entity.entity_type in ("person", "professional"):
            role_mentions = find_role_person_mentions(text)
            # New-person discovery is only trusted from the APPLICANT's
            # context (their own team page) -- people-search directories
            # about owners list unrelated names that must NOT become
            # entities. Self-role matches always count.
            discover_others = "applicant" in (entity.case_roles or [])
            for mentioned_name, role in role_mentions:
                mentioned_name = clean_text(mentioned_name)
                if not mentioned_name or not _looks_like_person_name(mentioned_name):
                    continue
                if _same_person(mentioned_name, entity.canonical_name):
                    self._add_evidence(entity, "role", role, source, None, conf)
                elif discover_others:
                    self._maybe_discover_person(mentioned_name, role, entity, source, text, depth)
        # Organization discovery from page harvests: NEW organizations are
        # only minted from person/applicant contexts (a person's page names
        # their company). An organization's own page naming OTHER companies
        # (press mentions, investors, partners) is crawler bait, not case
        # evidence -- known orgs resurfacing still get link backfill via
        # _maybe_discover_org.
        for match in ORG_SUFFIX_RE.finditer(text[:20000]):
            full_name = _clean_org_candidate(f"{match.group(1)} {match.group(2)}")
            if not full_name:
                continue
            if not _org_relevant(full_name, entity, self.entities.values()):
                continue
            candidate_key = make_entity_key("organization", full_name)
            if entity.entity_type in ("person", "professional") \
                    or candidate_key in self.entities:
                self._maybe_discover_org(full_name, entity, source, text, depth)
        if entity.entity_type == "organization":
            if not entity.attributes.get("website") and is_probable_website(source.url or "") \
                    and not is_social_url(source.url or ""):
                self._add_evidence(entity, "website", source.url, source, source.title, conf)
            officers = find_role_person_mentions(text)
            for officer_name, officer_role in officers:
                officer_name = clean_text(officer_name)
                if officer_name and _looks_like_person_name(officer_name) \
                        and not _same_person(officer_name, entity.canonical_name):
                    self._maybe_discover_person(
                        officer_name, officer_role, entity, source, text, depth
                    )
        self._discover_related_case_reference(entity, text, source)

    def _discover_org_from_snippets(
        self,
        entity: EntityRecord,
        results: list[dict],
        depth: int,
    ) -> None:
        """
        CASE -> APPLICANT -> COMPANY: when search results tie an entity
        (usually a person) to an organization-suffixed name in the same
        snippet window, register that organization as a discovered entity
        eligible for its own bounded research pass.
        """
        if entity.entity_type not in ("person", "professional"):
            return
        seen_spans = set()
        for r in results:
            combined = f"{r.get('title') or ''}\n{r.get('snippet') or ''}"
            for m in ORG_SUFFIX_RE.finditer(combined):
                org_core = clean_text(m.group(1))
                span = f"{org_core} {m.group(2)}".lower()
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                window = surrounding_text(combined, org_core).lower()
                name_tokens = set(er_normalize(entity.canonical_name).split())
                full_name = er_normalize(entity.canonical_name)
                surname_overlap = bool(
                    name_tokens & set(span.split())
                ) or any(t in window for t in name_tokens)
                if not surname_overlap:
                    continue
                # Snippet-level org discovery normally requires LOCALITY
                # (the case's geography in the same window), so every
                # same-named person on the web does not spawn phantom
                # companies. EXCEPTION: strong title adjacency -- the org
                # appears within a few words of the entity's FULL name in
                # the result title ("Jane Doe - Partner - Acme Development")
                # is an affiliation claim worth researching on its own.
                loc_tokens = {
                    t for t in
                    er_normalize(str(entity.attributes.get("location") or "")).split()
                    if t.isalpha()
                }
                if loc_tokens and not (loc_tokens & set(window.split())):
                    title = (r.get("title") or "").lower()
                    title_pos = title.find(full_name)
                    org_pos = m.start()
                    adjacent_in_title = (
                        0 <= title_pos < org_pos <= title_pos + len(full_name) + 40
                    ) if full_name in title else False
                    if not adjacent_in_title:
                        continue
                source = SourceRef(
                    url=r.get("link"),
                    title=r.get("title"),
                    discovery_method="web_search",
                    fetched_full_page=False,
                )
                candidate_name = _clean_org_candidate(f"{org_core} {m.group(2)}")
                if not candidate_name:
                    continue
                self._maybe_discover_org(candidate_name, entity, source, combined, depth)

    # -- new entity creation ------------------------------------------------------

    def _can_add_entity(self) -> bool:
        return len(self.entities) < self.max_entities

    def _link_existing_to_context(
        self,
        existing_key: str,
        context_entity: EntityRecord,
        source: SourceRef,
        page_text: str,
        mentioned_name: str,
    ) -> None:
        """
        When an already-known entity resurfaces in a DIFFERENT entity's
        evidence, record the additional associated_with relationship instead
        of silently dropping the corroboration. Policy: only ORGANIZATION
        contexts anchor co-mentions (person affiliated with a company).
        Person-to-person co-appearance on a page is NOT an association and
        must not create edges.
        """
        if existing_key == context_entity.entity_key:
            return
        if context_entity.entity_type in ("person", "professional"):
            return
        already = any(
            r.subject_entity_key == existing_key
            and r.predicate == "associated_with"
            and r.object_entity_key == context_entity.entity_key
            for r in self.relationships
        )
        if already:
            return
        self.relationships.append(RelationshipRecord(
            subject_entity_key=existing_key,
            predicate="associated_with",
            object_entity_key=context_entity.entity_key,
            application_number=str(self.lead.get("application_number") or ""),
            confidence=page_confidence(source),
            sources=[source.to_dict()],
        ))
        self._add_evidence(
            self.entities[existing_key], "associated_with",
            context_entity.canonical_name, source,
            surrounding_text(page_text, mentioned_name),
            page_confidence(source),
        )

    def _maybe_discover_person(
        self,
        name: str,
        role: Optional[str],
        context_entity: EntityRecord,
        source: SourceRef,
        page_text: str,
        depth: int,
    ) -> None:
        if depth >= self.max_depth or not self._can_add_entity():
            return
        key = make_entity_key("professional" if role else "person", name)
        if key in self.entities:
            self._link_existing_to_context(key, context_entity, source, page_text, name)
            return
        new_entity = EntityRecord(
            entity_key=key,
            entity_type="professional" if role else "person",
            canonical_name=name,
            case_roles=["related_person"],
            research_status="DISCOVERED_PENDING_CONTEXT",
            depth=depth + 1,
            attributes={
                "discovered_via": context_entity.canonical_name,
                "location": context_entity.attributes.get("location"),
                "application_number": self.lead.get("application_number"),
            },
        )
        if role:
            new_entity.attributes["role"] = role
        self.entities[key] = new_entity
        self._add_evidence(
            new_entity, "role", role, source, surrounding_text(page_text, name), page_confidence(source)
        )
        self._add_evidence(
            new_entity, "associated_with",
            context_entity.canonical_name, source, None, page_confidence(source),
        )
        self.relationships.append(RelationshipRecord(
            subject_entity_key=new_entity.entity_key,
            predicate="associated_with",
            object_entity_key=context_entity.entity_key,
            application_number=str(self.lead.get("application_number") or ""),
            confidence=page_confidence(source),
            sources=[source.to_dict()],
        ))
        new_entity.research_status = "GOVERNMENT_RECORD"

    def _maybe_discover_org(
        self,
        name: str,
        context_entity: EntityRecord,
        source: SourceRef,
        page_text: str,
        depth: int,
    ) -> None:
        if depth >= self.max_depth or not self._can_add_entity():
            return
        if not _plausible_org_candidate(
            name,
            [e.canonical_name for e in self.entities.values()
             if e.entity_type == "organization"],
        ):
            return
        key = make_entity_key("organization", name)
        if key in self.entities:
            self._link_existing_to_context(key, context_entity, source, page_text, name)
            return
        new_entity = EntityRecord(
            entity_key=key,
            entity_type="organization",
            canonical_name=name,
            case_roles=["related_organization"],
            research_status="DISCOVERED_PENDING_CONTEXT",
            depth=depth + 1,
            attributes={
                "discovered_via": context_entity.canonical_name,
                "application_number": self.lead.get("application_number"),
            },
        )
        self.entities[key] = new_entity
        self._add_evidence(
            new_entity, "associated_with", context_entity.canonical_name,
            source, surrounding_text(page_text, name), page_confidence(source),
        )
        self.relationships.append(RelationshipRecord(
            subject_entity_key=new_entity.entity_key,
            predicate="associated_with",
            object_entity_key=context_entity.entity_key,
            application_number=str(self.lead.get("application_number") or ""),
            confidence=page_confidence(source),
            sources=[source.to_dict()],
        ))
        new_entity.research_status = "GOVERNMENT_RECORD"

    def _discover_related_case_reference(
        self,
        entity: EntityRecord,
        text: str,
        source: SourceRef,
    ) -> None:
        refs = set(re.findall(r"\bPL[A-Z]{1,6}\d{6,8}\b", text.upper()))
        own = str(self.lead.get("application_number") or "").upper()
        for ref in refs:
            if ref == own:
                continue
            self._add_evidence(
                entity, "related_case_reference", ref, source,
                surrounding_text(text, ref), page_confidence(source),
            )

    # -- assembly ----------------------------------------------------------

    def build_case_intelligence(self, depth_reached: int = 0) -> dict[str, Any]:
        """Assemble the consumer-ready case_intelligence record."""
        entities_payload = [
            e.to_dict()
            for e in sorted(self.entities.values(), key=lambda x: x.depth)
        ]
        relationships_payload = [r.to_dict() for r in self.relationships]
        evidence_payload = sorted(
            self.evidence_index.values(),
            key=lambda e: e.get("confidence", 0),
            reverse=True,
        )
        sources_payload = sorted(
            self.sources_index.values(),
            key=lambda s: s.get("hierarchy_rank", 99),
        )

        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for e in self.entities.values():
            type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1
            status_counts[e.research_status] = status_counts.get(e.research_status, 0) + 1

        unresolved = [
            e.entity_key for e in self.entities.values()
            if e.entity_type in ("person", "professional", "organization")
            and e.match_status in ("ambiguous", "unverified", "not_found")
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "product": PRODUCT_NAME,
            "generated_at": now_iso(),
            "application_number": self.lead.get("application_number"),
            "case": {
                "application_number": self.lead.get("application_number"),
                "application_type": self.lead.get("application_type"),
                "project_address": self.lead.get("project_address"),
                "neighborhood": self.lead.get("neighborhood"),
                "status": self.lead.get("status"),
                "description": self.lead.get("description"),
                "source": self.lead.get("source"),
                "source_url": self.lead.get("source_url"),
                "next_project_date": self.lead.get("next_project_date"),
                "next_project_event": self.lead.get("next_project_event"),
                "next_project_time": self.lead.get("next_project_time"),
                "friction_score": self.lead.get("friction_score"),
                "friction_signals": self.lead.get("friction_signals", []),
            },
            "entities": entities_payload,
            "relationships": relationships_payload,
            "evidence": evidence_payload,
            "sources": sources_payload,
            "research_run": {
                "run_id": self.run_id,
                "status": "completed",
                "started_at": self.started_at,
                "completed_at": getattr(self, "completed_at", None),
                "params": {
                    "max_depth": self.max_depth,
                    "max_queries": self.max_queries,
                    "max_pages": self.max_pages,
                    "max_entities": self.max_entities,
                    "search_provider": "serpapi" if self.serpapi_key else "none",
                },
                "depth_reached": depth_reached,
                "queries_executed": self.queries_used,
                "pages_fetched": self.pages_fetched,
                "entities_discovered": len(self.entities),
                "evidence_collected": len(self.evidence_index),
                "errors": self.errors,
            },
            "stats": {
                "entity_types": type_counts,
                "research_statuses": status_counts,
                "relationships_total": len(relationships_payload),
                "evidence_total": len(evidence_payload),
                "sources_total": len(sources_payload),
                "verified_claims": sum(
                    1 for e in evidence_payload
                    if e.get("verification_status") == "verified"
                ),
                "unverified_claims": sum(
                    1 for e in evidence_payload
                    if e.get("verification_status") == "unverified"
                ),
                "unresolved_entity_keys": unresolved,
            },
        }


def _same_person(a: str, b: str) -> bool:
    from backend.app.services.entity_intelligence import normalize_person_name
    ta = set(normalize_person_name(a).split())
    tb = set(normalize_person_name(b).split())
    return bool(ta and tb and (ta <= tb or tb <= ta))


def er_normalize(name: str) -> str:
    from backend.app.services.entity_intelligence import normalize_person_name
    return normalize_person_name(name)


_ORG_BLOCK_TOKENS = {
    "vice", "president", "director", "manager", "partner", "owner",
    "principal", "ceo", "cfo", "profiles", "education", "university",
    "school", "church", "inc", "incorporated",
}


def _org_name_tokens(name: str) -> set:
    return set(er_normalize(name).split())


def _plausible_org_candidate(name: str, existing_org_names) -> bool:
    """
    Quality gate for regex-captured organization candidates. Rejects
    sentence fragments ('Investment. Albion Development'), role-prefixed
    titles ('Vice President-Global Education StoneX Group'), single
    common nouns ('Development'), and near-duplicates of organizations
    already registered for this case.
    """
    cleaned = _clean_org_candidate(name)
    if "." in cleaned:
        return False
    tokens = _org_name_tokens(cleaned)
    alpha = {t for t in tokens if t.isalpha()}
    if len(alpha) < 2 or not any(len(t) >= 4 for t in alpha):
        return False
    lowered = {t.lower() for t in tokens}
    if lowered & _ORG_BLOCK_TOKENS:
        return False
    new_tokens = lowered
    for existing in existing_org_names:
        ex_tokens = _org_name_tokens(existing)
        if not ex_tokens:
            continue
        union = new_tokens | ex_tokens
        jaccard = len(new_tokens & ex_tokens) / len(union)
        contained = new_tokens <= ex_tokens or ex_tokens <= new_tokens
        if jaccard >= 0.6 or contained:
            return False
    return True


_LOCATION_LEAD_WORDS = {"utah", "provo", "county", "city", "north", "south"}


def _clean_org_candidate(name: str) -> str:
    """
    Normalize a regex-captured organization candidate: drop location lead
    words the capture window swallowed and dedupe repeated halves, so
    'Utah Morgan Surveying LLC' and 'Morgan Surveying Morgan Surveying
    LLC' normalize toward one canonical name.
    """
    tokens = [t for t in name.split() if t]
    while tokens and tokens[0].strip(",.").lower() in _LOCATION_LEAD_WORDS:
        tokens = tokens[1:]
    half = len(tokens) // 2
    if half >= 1 and [t.lower() for t in tokens[:half]] == [t.lower() for t in tokens[half:half * 2][:half]]:
        tokens = tokens[:half] + tokens[half * 2:]
    return " ".join(tokens).strip(" .,")


def _org_relevant(name: str, context_entity: EntityRecord, all_entities: Any) -> bool:
    from backend.app.services.entity_intelligence import normalize_org_name
    ntokens = set(normalize_org_name(name).split())
    if not ntokens:
        return False
    ctx_tokens = set(normalize_org_name(context_entity.canonical_name).split()) | \
        set(normalize_org_name(str(context_entity.attributes.get("organization") or "")).split())
    for other in all_entities:
        otokens = set(normalize_org_name(other.canonical_name).split())
        if otokens and (ntokens <= otokens or otokens <= ntokens):
            return True
    return bool(ctx_tokens & ntokens)


# =========================================================================
# Consumer-ready record assembly
# =========================================================================

def run_case_research(
    lead: dict[str, Any],
    persist: bool = True,
    **engine_kwargs: Any,
) -> dict[str, Any]:
    """
    Convenience entry point: research one case, attach the additive
    ``case_intelligence`` record to the lead, optionally persist the
    normalized rows to Supabase, and return the record.
    """
    engine = CaseResearchEngine(lead, **engine_kwargs)
    record = engine.run()
    record["research_run"]["persistence"] = {"status": "skipped"}

    if persist:
        try:
            persistence = entity_repository.persist_case_intelligence(record)
            record["research_run"]["persistence"] = persistence
        except Exception as exc:
            record["research_run"]["persistence"] = {
                "status": "error",
                "error": str(exc)[:300],
            }

    lead["case_intelligence"] = {
        k: v for k, v in record.items() if not k.startswith("_")
    }
    return record


__all__ = [
    "CaseResearchEngine",
    "seed_entities_from_lead",
    "run_case_research",
]
