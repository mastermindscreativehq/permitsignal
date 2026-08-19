"""
PermitSignal Owner / Person / Entity Investigation Engine (Phase 2B)

Purpose
-------
After PermitSignal extracts a government project/agenda/application and
creates a lead profile, this engine allows user-triggered investigation
of the owner, applicant, company/entity, and project using publicly
available business/professional information.

The investigation produces:
- additional identity information
- company information
- official website
- publicly listed business contact information
- professional contact information
- publicly indexed professional profiles
- LinkedIn discovery where publicly discoverable and permitted
- business directory information
- public business/entity records where accessible
- project/entity relationships
- supporting evidence with provenance
- confidence scores
- identity-match reasoning
- investigation history

Design principle: this module is entirely ADDITIVE.  It never overwrites
government-record data.  It stores external discoveries alongside existing
intelligence in the lead's JSONB record.

Architecture
------------
Source-specific investigation pipelines:

1. WEB SEARCH          - General web search for owner/company/project
2. OFFICIAL WEBSITE    - Discover and crawl official company websites
3. BUSINESS DIRECTORIES- Search public business directory listings
4. LINKEDIN DISCOVERY  - Find publicly indexed professional profiles
5. PUBLIC RECORDS      - Public business/entity records
6. PROJECT RELATIONSHIPS - Connections between owner/company/project
7. PUBLIC CONTACT DISCOVERY - Discover public contact information

Each pipeline has its own:
- investigation action
- status tracking
- evidence collection
- event logging
- error handling
- result normalization

Search provider: SerpAPI (same as applicant_enrichment).

Environment
-----------
SERPAPI_API_KEY=...
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Reuse extraction utilities from applicant_enrichment where possible
# ---------------------------------------------------------------------------
from backend.app.services.applicant_enrichment import (
    EMAIL_RE,
    PHONE_RE,
    GENERIC_EMAIL_PREFIXES,
    BAD_EMAIL_DOMAINS,
    SOCIAL_DOMAINS,
    MAP_UTILITY_DOMAINS,
    BUSINESS_DIRECTORY_DOMAINS,
    extract_emails,
    extract_phones,
    valid_email,
    is_government_email,
    is_government_url,
    is_social_url,
    is_map_or_utility_url,
    is_probable_website,
    normalize_url,
    clean_name,
    clean_text,
    surrounding_text,
    _looks_like_person_name,
    _confidence_label,
    email_confidence as _applicant_email_confidence,
    source_confidence as _source_confidence,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 "
        "PermitSignal/2.0"
    ),
}

BUSINESS_DIRECTORY_DOMAINS_SET = set(BUSINESS_DIRECTORY_DOMAINS)

# Source quality classifications
SOURCE_QUALITY = {
    "government_record": "OFFICIAL_GOVERNMENT",
    "official_website": "OFFICIAL_COMPANY",
    "official_business": "OFFICIAL_BUSINESS",
    "business_directory": "REPUTABLE_DIRECTORY",
    "professional_profile": "PROFESSIONAL_PROFILE",
    "public_web": "PUBLIC_WEB",
    "search_result": "PUBLIC_WEB",
    "other": "OTHER",
}

INVESTIGATION_SOURCES = [
    "web",
    "website",
    "directories",
    "linkedin",
    "public_records",
    "project",
    "contact",
]

INVESTIGATION_STATUSES = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "ENRICHED",
    "PARTIAL",
    "NOT_FOUND",
    "ERROR",
}


# =========================================================================
# Data Model
# =========================================================================

@dataclass
class InvestigationEvidence:
    field: str
    value: str
    source_url: Optional[str] = None
    source_type: str = "public_web"
    source_title: Optional[str] = None
    source_domain: Optional[str] = None
    discovered_at: Optional[str] = None
    confidence: str = "LOW"
    confidence_score: float = 0.0
    evidence_text: Optional[str] = None
    match_reason: Optional[str] = None
    entity_type: Optional[str] = None
    entity_identifier: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class InvestigationEvent:
    action: str
    occurred_at: Optional[str] = None
    source: Optional[str] = None
    queries_executed: int = 0
    pages_fetched: int = 0
    emails_discovered: int = 0
    phones_discovered: int = 0
    websites_discovered: int = 0
    profiles_discovered: int = 0
    entities_discovered: int = 0
    evidence_created: int = 0
    result: str = "success"
    error: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class IdentityMatch:
    match_score: float = 0.0
    confidence_label: str = "LOW"
    matched_signals: list[str] = field(default_factory=list)
    conflicting_signals: list[str] = field(default_factory=list)
    reasoning: str = ""
    discovered_name: Optional[str] = None
    discovered_company: Optional[str] = None
    discovered_role: Optional[str] = None
    source_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ContactCandidate:
    value: str
    contact_type: str  # "email" | "phone" | "website"
    source_url: Optional[str] = None
    source_type: str = "public_web"
    source_title: Optional[str] = None
    source_domain: Optional[str] = None
    confidence: float = 0.0
    public_status: str = "public"
    evidence_text: Optional[str] = None
    associated_entity: Optional[str] = None
    associated_person: Optional[str] = None
    match_reason: Optional[str] = None
    is_generic: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


# =========================================================================
# Utility Functions
# =========================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _domain_of(url_or_email: str) -> Optional[str]:
    if "@" in url_or_email:
        return url_or_email.split("@")[-1].lower().strip(".")
    try:
        parsed = urlparse(url_or_email)
        return (parsed.hostname or "").lower().strip(".")
    except Exception:
        return None


def _is_generic_email(email: str) -> bool:
    prefix = email.split("@")[0].lower()
    return prefix in GENERIC_EMAIL_PREFIXES


def _dedupe_by_value(items: list[dict], key: str = "value") -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        val = (item.get(key) or "").lower().strip()
        if val and val not in seen:
            seen.add(val)
            result.append(item)
    return result


def _dedupe_evidence(evidence: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    result: list[dict] = []
    for e in evidence:
        key = (
            e.get("field", ""),
            (e.get("value") or "").lower().strip(),
            e.get("source_url", ""),
        )
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result


def _normalize_email(value: str) -> str:
    return value.strip().lower().removeprefix("mailto:")


def _normalize_phone(value: str) -> str:
    return clean_text(value)


def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    return "LOW"


def _looks_like_company(name: str) -> bool:
    indicators = [
        "llc", "inc", "corp", "ltd", "company", "enterprises",
        "holdings", "group", "partners", "associates", "developments",
        "construction", "builders", "properties", "realty", "investments",
        "ventures", "capital", "management", "services", "solutions",
        "consulting", "design", "architecture", "engineering",
    ]
    lower = name.lower()
    return any(ind in lower for ind in indicators)


def _safe_fetch(url: str, session: requests.Session, timeout: int = 15) -> Optional[str]:
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code < 400:
            return resp.text
    except Exception:
        pass
    return None


def _extract_text_from_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text, title


def _build_queries(
    owner_name: Optional[str],
    owner_entity: Optional[str],
    applicant_name: Optional[str],
    project_address: Optional[str],
    application_number: Optional[str],
    municipality: Optional[str] = None,
) -> list[str]:
    queries: list[str] = []
    primary = owner_entity or owner_name or applicant_name

    if not primary:
        return queries

    address_part = f'"{project_address}"' if project_address else ""

    queries.append(f'"{primary}"')
    if owner_name and owner_entity:
        queries.append(f'"{owner_name}" "{owner_entity}"')
    if address_part:
        queries.append(f'"{primary}" {address_part}')
    queries.append(f'"{primary}" contact')
    queries.append(f'"{primary}" email phone')
    if owner_entity:
        queries.append(f'"{owner_entity}" website')
    if application_number:
        queries.append(f'"{application_number}"')
    if project_address:
        queries.append(f'"{project_address}" development')
    if municipality:
        queries.append(f'"{primary}" "{municipality}"')

    return queries


# =========================================================================
# Investigation Profile — Data Shape
# =========================================================================

def new_investigation_profile() -> dict[str, Any]:
    return {
        "status": "NOT_STARTED",
        "started_at": None,
        "completed_at": None,
        "last_at": None,
        "sources": {s: "NOT_STARTED" for s in INVESTIGATION_SOURCES},
        "queries": [],
        "evidence": [],
        "events": [],
        "contacts": {
            "preferred_email": None,
            "preferred_phone": None,
            "preferred_website": None,
            "email_candidates": [],
            "phone_candidates": [],
            "website_candidates": [],
        },
        "identity_matches": [],
        "summary": {
            "emails_found": 0,
            "phones_found": 0,
            "websites_found": 0,
            "profiles_found": 0,
            "entities_found": 0,
        },
        "errors": [],
    }


def get_investigation(lead: dict[str, Any]) -> dict[str, Any]:
    inv = lead.get("investigation")
    if not inv or not isinstance(inv, dict):
        inv = new_investigation_profile()
        lead["investigation"] = inv
    for key in new_investigation_profile():
        if key not in inv:
            inv[key] = new_investigation_profile()[key]
    if "sources" not in inv or not isinstance(inv["sources"], dict):
        inv["sources"] = new_investigation_profile()["sources"]
    return inv


# =========================================================================
# Web Search Pipeline
# =========================================================================

def run_web_search(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("web", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["web"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="web_search",
        source="web",
        occurred_at=_now_iso(),
        note=note,
    )

    if not serpapi_key:
        event.result = "error"
        event.error = "SERPAPI_API_KEY not configured"
        inv["sources"]["web"] = "ERROR"
        inv["events"].append(event.to_dict())
        inv["errors"].append(event.error)
        return inv

    owner_name = lead.get("owner_name")
    owner_entity = lead.get("owner_entity")
    applicant_name = lead.get("applicant_name")
    project_address = lead.get("project_address")
    application_number = lead.get("application_number")

    queries = _build_queries(owner_name, owner_entity, applicant_name, project_address, application_number)
    event.queries_executed = len(queries)
    inv["queries"] = list(queries)

    all_results: list[dict] = []
    for query in queries:
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": serpapi_key,
                "num": 8,
            }
            location = os.environ.get("SERPAPI_LOCATION")
            if location:
                params["location"] = location

            resp = session.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=20,
            )
            if resp.status_code == 200:
                payload = resp.json()
                results = payload.get("organic_results", [])
                for r in results:
                    all_results.append({
                        "query": query,
                        "title": r.get("title", ""),
                        "link": r.get("link", ""),
                        "snippet": r.get("snippet", ""),
                    })
            elif resp.status_code == 429:
                event.result = "partial"
                event.error = "Rate limit hit"
                break
            time.sleep(0.3)
        except Exception as exc:
            event.error = str(exc)

    for r in all_results:
        snippet = r.get("snippet", "")
        title = r.get("title", "")
        link = r.get("link", "")
        combined = f"{title}\n{snippet}"

        emails = extract_emails(combined)
        phones = extract_phones(combined)

        for email in emails:
            if valid_email(email) and not is_government_email(email):
                ev = InvestigationEvidence(
                    field="email",
                    value=_normalize_email(email),
                    source_url=link,
                    source_type="search_result",
                    source_title=title,
                    source_domain=_domain_of(link),
                    discovered_at=_now_iso(),
                    confidence=_confidence_label(0.55),
                    confidence_score=0.55,
                    evidence_text=surrounding_text(combined, email, radius=120),
                    match_reason="Found in web search result for owner/company query",
                )
                inv["evidence"].append(ev.to_dict())
                event.emails_discovered += 1

        for phone in phones:
            ev = InvestigationEvidence(
                field="phone",
                value=_normalize_phone(phone),
                source_url=link,
                source_type="search_result",
                source_title=title,
                source_domain=_domain_of(link),
                discovered_at=_now_iso(),
                confidence=_confidence_label(0.50),
                confidence_score=0.50,
                evidence_text=surrounding_text(combined, phone, radius=120),
                match_reason="Found in web search result for owner/company query",
            )
            inv["evidence"].append(ev.to_dict())
            event.phones_discovered += 1

        if is_probable_website(link) and not is_social_url(link) and not is_map_or_utility_url(link):
            domain = _domain_of(link)
            if domain and domain not in BUSINESS_DIRECTORY_DOMAINS_SET:
                ev = InvestigationEvidence(
                    field="website",
                    value=link,
                    source_url=link,
                    source_type="search_result",
                    source_title=title,
                    source_domain=domain,
                    discovered_at=_now_iso(),
                    confidence=_confidence_label(0.45),
                    confidence_score=0.45,
                    evidence_text=title,
                    match_reason="URL found in web search results",
                )
                inv["evidence"].append(ev.to_dict())
                event.websites_discovered += 1

    inv["evidence"] = _dedupe_evidence(inv["evidence"])
    event.evidence_created = event.emails_discovered + event.phones_discovered + event.websites_discovered
    inv["events"].append(event.to_dict())

    if event.emails_discovered or event.phones_discovered or event.websites_discovered:
        inv["sources"]["web"] = "ENRICHED"
    elif all_results:
        inv["sources"]["web"] = "PARTIAL"
    else:
        inv["sources"]["web"] = "NOT_FOUND"

    _refresh_contacts(inv)
    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Official Website Pipeline
# =========================================================================

def run_website_discovery(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("website", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["website"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="website_discovery",
        source="website",
        occurred_at=_now_iso(),
        note=note,
    )

    owner_name = lead.get("owner_name")
    owner_entity = lead.get("owner_entity")
    applicant_name = lead.get("applicant_name")
    primary = owner_entity or owner_name or applicant_name

    if not primary:
        event.result = "not_found"
        event.error = "No owner/entity/applicant name available"
        inv["sources"]["website"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    website_candidates_from_evidence = [
        e for e in inv["evidence"]
        if e.get("field") == "website" and e.get("source_type") in ("search_result", "public_web")
    ]

    if website_candidates_from_evidence:
        best = website_candidates_from_evidence[0]
        website_url = best.get("value", "")
        website_domain = best.get("source_domain", "")
    elif serpapi_key:
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": f'"{primary}" official website',
                "api_key": serpapi_key,
                "num": 5,
            }
            resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
            event.queries_executed = 1
            if resp.status_code == 200:
                results = resp.json().get("organic_results", [])
                website_url = None
                website_domain = None
                for r in results:
                    link = r.get("link", "")
                    domain = _domain_of(link)
                    if (domain and is_probable_website(link)
                            and not is_social_url(link)
                            and not is_map_or_utility_url(link)
                            and domain not in BUSINESS_DIRECTORY_DOMAINS_SET):
                        website_url = link
                        website_domain = domain
                        break
            else:
                website_url = None
                website_domain = None
            time.sleep(0.3)
        except Exception:
            website_url = None
            website_domain = None
    else:
        website_url = None
        website_domain = None

    if not website_url:
        event.result = "not_found"
        inv["sources"]["website"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    if website_url:
        html = _safe_fetch(website_url, session)
        if html:
            event.pages_fetched += 1
            text, title = _extract_text_from_html(html)

            emails = extract_emails(text)
            phones = extract_phones(text)

            for email in emails:
                if valid_email(email) and not is_government_email(email):
                    conf = _applicant_email_confidence(email, website_url, "official_website", owner_name or "")
                    ev = InvestigationEvidence(
                        field="email",
                        value=_normalize_email(email),
                        source_url=website_url,
                        source_type="official_website",
                        source_title=title,
                        source_domain=website_domain,
                        discovered_at=_now_iso(),
                        confidence=_confidence_label(conf),
                        confidence_score=conf,
                        evidence_text=surrounding_text(text, email, radius=120),
                        match_reason=f"Found on official website ({website_domain})",
                    )
                    inv["evidence"].append(ev.to_dict())
                    event.emails_discovered += 1

            for phone in phones:
                ev = InvestigationEvidence(
                    field="phone",
                    value=_normalize_phone(phone),
                    source_url=website_url,
                    source_type="official_website",
                    source_title=title,
                    source_domain=website_domain,
                    discovered_at=_now_iso(),
                    confidence=_confidence_label(0.70),
                    confidence_score=0.70,
                    evidence_text=surrounding_text(text, phone, radius=120),
                    match_reason=f"Found on official website ({website_domain})",
                )
                inv["evidence"].append(ev.to_dict())
                event.phones_discovered += 1

            contact_pages = ["/contact", "/about", "/team", "/leadership", "/people"]
            base = f"{urlparse(website_url).scheme}://{urlparse(website_url).hostname}"
            for path in contact_pages:
                page_url = base + path
                page_html = _safe_fetch(page_url, session)
                if page_html:
                    event.pages_fetched += 1
                    page_text, page_title = _extract_text_from_html(page_html)
                    if len(page_text) > 100:
                        p_emails = extract_emails(page_text)
                        p_phones = extract_phones(page_text)
                        for email in p_emails:
                            if valid_email(email) and not is_government_email(email):
                                conf = _applicant_email_confidence(email, page_url, "official_website", owner_name or "")
                                ev = InvestigationEvidence(
                                    field="email",
                                    value=_normalize_email(email),
                                    source_url=page_url,
                                    source_type="official_website",
                                    source_title=page_title,
                                    source_domain=website_domain,
                                    discovered_at=_now_iso(),
                                    confidence=_confidence_label(conf),
                                    confidence_score=conf,
                                    evidence_text=surrounding_text(page_text, email, radius=120),
                                    match_reason=f"Found on official website {path} page",
                                )
                                inv["evidence"].append(ev.to_dict())
                                event.emails_discovered += 1
                        for phone in p_phones:
                            ev = InvestigationEvidence(
                                field="phone",
                                value=_normalize_phone(phone),
                                source_url=page_url,
                                source_type="official_website",
                                source_title=page_title,
                                source_domain=website_domain,
                                discovered_at=_now_iso(),
                                confidence=_confidence_label(0.70),
                                confidence_score=0.70,
                                evidence_text=surrounding_text(page_text, phone, radius=120),
                                match_reason=f"Found on official website {path} page",
                            )
                            inv["evidence"].append(ev.to_dict())
                            event.phones_discovered += 1
                    time.sleep(0.2)

            ev = InvestigationEvidence(
                field="website",
                value=website_url,
                source_url=website_url,
                source_type="official_website",
                source_title=title,
                source_domain=website_domain,
                discovered_at=_now_iso(),
                confidence=_confidence_label(0.75),
                confidence_score=0.75,
                evidence_text=title or website_url,
                match_reason="Identified as official company/entity website",
            )
            inv["evidence"].append(ev.to_dict())
            event.websites_discovered += 1

    inv["evidence"] = _dedupe_evidence(inv["evidence"])
    event.evidence_created = event.emails_discovered + event.phones_discovered + event.websites_discovered
    inv["events"].append(event.to_dict())

    if event.emails_discovered or event.phones_discovered:
        inv["sources"]["website"] = "ENRICHED"
    elif event.websites_discovered:
        inv["sources"]["website"] = "ENRICHED"
    else:
        inv["sources"]["website"] = "PARTIAL"

    _refresh_contacts(inv)
    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Business Directory Pipeline
# =========================================================================

def run_business_directories(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("directories", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["directories"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="business_directories",
        source="directories",
        occurred_at=_now_iso(),
        note=note,
    )

    if not serpapi_key:
        event.result = "error"
        event.error = "SERPAPI_API_KEY not configured"
        inv["sources"]["directories"] = "ERROR"
        inv["events"].append(event.to_dict())
        inv["errors"].append(event.error)
        return inv

    owner_entity = lead.get("owner_entity")
    owner_name = lead.get("owner_name")
    applicant_name = lead.get("applicant_name")
    primary = owner_entity or owner_name or applicant_name

    if not primary:
        event.result = "not_found"
        inv["sources"]["directories"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    site_filter = " OR ".join(f"site:{d}" for d in list(BUSINESS_DIRECTORY_DOMAINS)[:6])
    query = f'"{primary}" ({site_filter})'
    event.queries_executed = 1

    try:
        params = {
            "engine": os.environ.get("SERPAPI_ENGINE", "google"),
            "q": query,
            "api_key": serpapi_key,
            "num": 8,
        }
        resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
        if resp.status_code == 200:
            results = resp.json().get("organic_results", [])
            for r in results:
                link = r.get("link", "")
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                domain = _domain_of(link)

                if domain in BUSINESS_DIRECTORY_DOMAINS_SET:
                    ev = InvestigationEvidence(
                        field="business_listing",
                        value=primary,
                        source_url=link,
                        source_type="business_directory",
                        source_title=title,
                        source_domain=domain,
                        discovered_at=_now_iso(),
                        confidence=_confidence_label(0.55),
                        confidence_score=0.55,
                        evidence_text=snippet,
                        match_reason=f"Found in business directory: {domain}",
                        entity_type="company",
                        entity_identifier=primary,
                    )
                    inv["evidence"].append(ev.to_dict())
                    event.entities_discovered += 1

                    combined = f"{title}\n{snippet}"
                    dir_emails = extract_emails(combined)
                    for email in dir_emails:
                        if valid_email(email) and not is_government_email(email):
                            ev = InvestigationEvidence(
                                field="email",
                                value=_normalize_email(email),
                                source_url=link,
                                source_type="business_directory",
                                source_title=title,
                                source_domain=domain,
                                discovered_at=_now_iso(),
                                confidence=_confidence_label(0.50),
                                confidence_score=0.50,
                                evidence_text=surrounding_text(combined, email, radius=120),
                                match_reason=f"Found in business directory listing ({domain})",
                            )
                            inv["evidence"].append(ev.to_dict())
                            event.emails_discovered += 1

                    dir_phones = extract_phones(combined)
                    for phone in dir_phones:
                        ev = InvestigationEvidence(
                            field="phone",
                            value=_normalize_phone(phone),
                            source_url=link,
                            source_type="business_directory",
                            source_title=title,
                            source_domain=domain,
                            discovered_at=_now_iso(),
                            confidence=_confidence_label(0.45),
                            confidence_score=0.45,
                            evidence_text=surrounding_text(combined, phone, radius=120),
                            match_reason=f"Found in business directory listing ({domain})",
                        )
                        inv["evidence"].append(ev.to_dict())
                        event.phones_discovered += 1
        elif resp.status_code == 429:
            event.result = "partial"
            event.error = "Rate limit hit"
    except Exception as exc:
        event.error = str(exc)

    inv["evidence"] = _dedupe_evidence(inv["evidence"])
    event.evidence_created = event.entities_discovered + event.emails_discovered + event.phones_discovered
    inv["events"].append(event.to_dict())

    if event.entities_discovered:
        inv["sources"]["directories"] = "ENRICHED"
    elif event.emails_discovered or event.phones_discovered:
        inv["sources"]["directories"] = "PARTIAL"
    else:
        inv["sources"]["directories"] = "NOT_FOUND"

    _refresh_contacts(inv)
    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# LinkedIn Discovery Pipeline
# =========================================================================

def run_linkedin_discovery(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("linkedin", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["linkedin"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="linkedin_discovery",
        source="linkedin",
        occurred_at=_now_iso(),
        note=note,
    )

    if not serpapi_key:
        event.result = "error"
        event.error = "SERPAPI_API_KEY not configured"
        inv["sources"]["linkedin"] = "ERROR"
        inv["events"].append(event.to_dict())
        inv["errors"].append(event.error)
        return inv

    owner_name = lead.get("owner_name")
    owner_entity = lead.get("owner_entity")
    applicant_name = lead.get("applicant_name")
    primary = owner_name or applicant_name

    if not primary:
        event.result = "not_found"
        inv["sources"]["linkedin"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    queries = [f'"{primary}" LinkedIn']
    if owner_entity:
        queries.append(f'"{primary}" "{owner_entity}" LinkedIn')
    if owner_entity:
        queries.append(f'"{owner_entity}" LinkedIn')

    event.queries_executed = len(queries)
    profiles_found = 0

    for query in queries:
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": serpapi_key,
                "num": 5,
            }
            resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
            if resp.status_code == 200:
                results = resp.json().get("organic_results", [])
                for r in results:
                    link = r.get("link", "")
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    domain = _domain_of(link)

                    if domain and "linkedin.com" in domain:
                        profiles_found += 1
                        ev = InvestigationEvidence(
                            field="linkedin_profile",
                            value=link,
                            source_url=link,
                            source_type="professional_profile",
                            source_title=title,
                            source_domain=domain,
                            discovered_at=_now_iso(),
                            confidence=_confidence_label(0.60),
                            confidence_score=0.60,
                            evidence_text=snippet or title,
                            match_reason=f"LinkedIn profile found for {primary}",
                            entity_type="person",
                            entity_identifier=primary,
                        )
                        inv["evidence"].append(ev.to_dict())
            elif resp.status_code == 429:
                event.result = "partial"
                event.error = "Rate limit hit"
                break
            time.sleep(0.3)
        except Exception as exc:
            event.error = str(exc)

    event.profiles_discovered = profiles_found
    inv["events"].append(event.to_dict())

    if profiles_found:
        inv["sources"]["linkedin"] = "ENRICHED"
    else:
        inv["sources"]["linkedin"] = "NOT_FOUND"

    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Public Business Records Pipeline
# =========================================================================

def run_public_records(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("public_records", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["public_records"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="public_records",
        source="public_records",
        occurred_at=_now_iso(),
        note=note,
    )

    if not serpapi_key:
        event.result = "error"
        event.error = "SERPAPI_API_KEY not configured"
        inv["sources"]["public_records"] = "ERROR"
        inv["events"].append(event.to_dict())
        inv["errors"].append(event.error)
        return inv

    owner_entity = lead.get("owner_entity")
    owner_name = lead.get("owner_name")
    primary = owner_entity or owner_name

    if not primary:
        event.result = "not_found"
        inv["sources"]["public_records"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    queries = [f'"{primary}" business entity']
    if lead.get("project_address"):
        queries.append(f'"{primary}" "{lead["project_address"]}" property')

    event.queries_executed = len(queries)

    for query in queries:
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": serpapi_key,
                "num": 5,
            }
            resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
            if resp.status_code == 200:
                results = resp.json().get("organic_results", [])
                for r in results:
                    link = r.get("link", "")
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    domain = _domain_of(link)
                    combined = f"{title}\n{snippet}"

                    if domain and _looks_like_company(primary):
                        record_keywords = ["business entity", "llc", "corporation", "registered", "filing"]
                        if any(kw in combined.lower() for kw in record_keywords):
                            ev = InvestigationEvidence(
                                field="business_record",
                                value=primary,
                                source_url=link,
                                source_type="public_record",
                                source_title=title,
                                source_domain=domain,
                                discovered_at=_now_iso(),
                                confidence=_confidence_label(0.50),
                                confidence_score=0.50,
                                evidence_text=snippet,
                                match_reason="Public business/entity record found",
                                entity_type="company",
                                entity_identifier=primary,
                            )
                            inv["evidence"].append(ev.to_dict())
                            event.entities_discovered += 1
            elif resp.status_code == 429:
                event.result = "partial"
                event.error = "Rate limit hit"
                break
            time.sleep(0.3)
        except Exception as exc:
            event.error = str(exc)

    inv["events"].append(event.to_dict())

    if event.entities_discovered:
        inv["sources"]["public_records"] = "ENRICHED"
    else:
        inv["sources"]["public_records"] = "NOT_FOUND"

    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Project Relationship Investigation
# =========================================================================

def run_project_relationships(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("project", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["project"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="project_relationships",
        source="project",
        occurred_at=_now_iso(),
        note=note,
    )

    owner_name = lead.get("owner_name")
    owner_entity = lead.get("owner_entity")
    applicant_name = lead.get("applicant_name")
    project_address = lead.get("project_address")
    application_number = lead.get("application_number")
    primary = owner_entity or owner_name or applicant_name

    if not primary:
        event.result = "not_found"
        inv["sources"]["project"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    queries = []
    if project_address:
        queries.append(f'"{project_address}" development project')
        queries.append(f'"{project_address}" zoning planning')
    if application_number:
        queries.append(f'"{application_number}" planning')
    if primary and project_address:
        queries.append(f'"{primary}" "{project_address}"')

    event.queries_executed = len(queries)
    relationships_found = 0

    for query in queries:
        if not serpapi_key:
            break
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": serpapi_key,
                "num": 5,
            }
            resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
            if resp.status_code == 200:
                results = resp.json().get("organic_results", [])
                for r in results:
                    link = r.get("link", "")
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    combined = f"{title}\n{snippet}".lower()

                    address_tokens = (project_address or "").lower().split()
                    entity_tokens = primary.lower().split()
                    has_address = sum(1 for t in address_tokens if len(t) > 1 and t in combined) >= 2
                    has_entity = sum(1 for t in entity_tokens if len(t) > 2 and t in combined) >= 1

                    if has_address and has_entity:
                        relationships_found += 1
                        ev = InvestigationEvidence(
                            field="project_relationship",
                            value=f"{primary} -> {project_address}",
                            source_url=link,
                            source_type="public_web",
                            source_title=title,
                            source_domain=_domain_of(link),
                            discovered_at=_now_iso(),
                            confidence=_confidence_label(0.60),
                            confidence_score=0.60,
                            evidence_text=snippet,
                            match_reason=f"Entity '{primary}' mentioned alongside project address '{project_address}'",
                            entity_type="project_relationship",
                            entity_identifier=project_address,
                        )
                        inv["evidence"].append(ev.to_dict())
            elif resp.status_code == 429:
                event.result = "partial"
                event.error = "Rate limit hit"
                break
            time.sleep(0.3)
        except Exception as exc:
            event.error = str(exc)

    event.entities_discovered = relationships_found
    inv["events"].append(event.to_dict())

    if relationships_found:
        inv["sources"]["project"] = "ENRICHED"
    else:
        inv["sources"]["project"] = "NOT_FOUND"

    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Public Contact Discovery Pipeline
# =========================================================================

def run_contact_discovery(
    lead: dict[str, Any],
    session: requests.Session,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    source_status = inv["sources"].get("contact", "NOT_STARTED")

    if source_status == "ENRICHED" and not force:
        return inv

    inv["sources"]["contact"] = "IN_PROGRESS"
    inv["status"] = "IN_PROGRESS"
    if not inv["started_at"]:
        inv["started_at"] = _now_iso()
    inv["last_at"] = _now_iso()

    event = InvestigationEvent(
        action="contact_discovery",
        source="contact",
        occurred_at=_now_iso(),
        note=note,
    )

    if not serpapi_key:
        event.result = "error"
        event.error = "SERPAPI_API_KEY not configured"
        inv["sources"]["contact"] = "ERROR"
        inv["events"].append(event.to_dict())
        inv["errors"].append(event.error)
        return inv

    owner_name = lead.get("owner_name")
    owner_entity = lead.get("owner_entity")
    applicant_name = lead.get("applicant_name")
    primary = owner_entity or owner_name or applicant_name

    if not primary:
        event.result = "not_found"
        inv["sources"]["contact"] = "NOT_FOUND"
        inv["events"].append(event.to_dict())
        return inv

    contact_evidence = [
        e for e in inv["evidence"]
        if e.get("field") in ("email", "phone", "website")
    ]

    if len(contact_evidence) >= 3:
        event.result = "success"
        event.note = f"Contact candidates already available ({len(contact_evidence)} found)"
        inv["sources"]["contact"] = "ENRICHED"
        inv["events"].append(event.to_dict())
        _refresh_contacts(inv)
        _refresh_summary(inv)
        _update_overall_status(inv)
        return inv

    queries = [
        f'"{primary}" email contact',
        f'"{primary}" phone number',
    ]
    event.queries_executed = len(queries)

    for query in queries:
        try:
            params = {
                "engine": os.environ.get("SERPAPI_ENGINE", "google"),
                "q": query,
                "api_key": serpapi_key,
                "num": 5,
            }
            resp = session.get("https://serpapi.com/search.json", params=params, timeout=20)
            if resp.status_code == 200:
                results = resp.json().get("organic_results", [])
                for r in results:
                    link = r.get("link", "")
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    combined = f"{title}\n{snippet}"

                    c_emails = extract_emails(combined)
                    for email in c_emails:
                        if valid_email(email) and not is_government_email(email):
                            ev = InvestigationEvidence(
                                field="email",
                                value=_normalize_email(email),
                                source_url=link,
                                source_type="public_web",
                                source_title=title,
                                source_domain=_domain_of(link),
                                discovered_at=_now_iso(),
                                confidence=_confidence_label(0.50),
                                confidence_score=0.50,
                                evidence_text=surrounding_text(combined, email, radius=120),
                                match_reason=f"Found in contact-focused search ({primary})",
                            )
                            inv["evidence"].append(ev.to_dict())
                            event.emails_discovered += 1

                    c_phones = extract_phones(combined)
                    for phone in c_phones:
                        ev = InvestigationEvidence(
                            field="phone",
                            value=_normalize_phone(phone),
                            source_url=link,
                            source_type="public_web",
                            source_title=title,
                            source_domain=_domain_of(link),
                            discovered_at=_now_iso(),
                            confidence=_confidence_label(0.45),
                            confidence_score=0.45,
                            evidence_text=surrounding_text(combined, phone, radius=120),
                            match_reason=f"Found in contact-focused search ({primary})",
                        )
                        inv["evidence"].append(ev.to_dict())
                        event.phones_discovered += 1
            elif resp.status_code == 429:
                event.result = "partial"
                event.error = "Rate limit hit"
                break
            time.sleep(0.3)
        except Exception as exc:
            event.error = str(exc)

    inv["evidence"] = _dedupe_evidence(inv["evidence"])
    event.evidence_created = event.emails_discovered + event.phones_discovered
    inv["events"].append(event.to_dict())

    if event.emails_discovered or event.phones_discovered:
        inv["sources"]["contact"] = "ENRICHED"
    else:
        inv["sources"]["contact"] = "NOT_FOUND"

    _refresh_contacts(inv)
    _refresh_summary(inv)
    _update_overall_status(inv)
    return inv


# =========================================================================
# Identity Resolution
# =========================================================================

def resolve_identities(lead: dict[str, Any]) -> list[dict[str, Any]]:
    inv = get_investigation(lead)
    matches: list[IdentityMatch] = []

    owner_name = (lead.get("owner_name") or "").strip()
    owner_entity = (lead.get("owner_entity") or "").strip()
    applicant_name = (lead.get("applicant_name") or "").strip()
    project_address = (lead.get("project_address") or "").strip()

    email_evidence = [e for e in inv["evidence"] if e.get("field") == "email"]
    phone_evidence = [e for e in inv["evidence"] if e.get("field") == "phone"]
    website_evidence = [e for e in inv["evidence"] if e.get("field") == "website"]
    linkedin_evidence = [e for e in inv["evidence"] if e.get("field") == "linkedin_profile"]

    for ev in email_evidence + phone_evidence:
        score = 0.0
        signals: list[str] = []
        conflicts: list[str] = []
        source_url = ev.get("source_url", "")
        source_domain = ev.get("source_domain", "")
        evidence_text = (ev.get("evidence_text") or "").lower()

        if owner_name:
            name_tokens = [t for t in owner_name.lower().split() if len(t) > 2]
            name_matches = sum(1 for t in name_tokens if t in evidence_text)
            if name_matches >= 1:
                score += 0.25
                signals.append(f"Owner name tokens found in evidence ({name_matches}/{len(name_tokens)})")
            else:
                conflicts.append("Owner name not found in evidence text")

        if owner_entity and source_domain:
            entity_tokens = [t for t in owner_entity.lower().split() if len(t) > 2]
            domain_str = source_domain.lower()
            entity_in_domain = sum(1 for t in entity_tokens if t in domain_str)
            if entity_in_domain >= 1:
                score += 0.30
                signals.append(f"Entity name appears in source domain ({source_domain})")

        if project_address:
            addr_tokens = [t for t in project_address.lower().split() if len(t) > 3]
            addr_matches = sum(1 for t in addr_tokens if t in evidence_text)
            if addr_matches >= 2:
                score += 0.20
                signals.append(f"Project address found in evidence ({addr_matches}/{len(addr_tokens)})")

        gov_domains = [".gov", ".gov."]
        if any(gd in source_domain for gd in gov_domains):
            score += 0.15
            signals.append("Source is government domain")

        if source_domain in BUSINESS_DIRECTORY_DOMAINS_SET:
            score += 0.10
            signals.append("Source is recognized business directory")

        if "linkedin.com" in (source_domain or ""):
            score += 0.15
            signals.append("Source is LinkedIn (professional profile)")

        if not signals:
            conflicts.append("No identity signals could be matched")

        clamped = min(score, 1.0)
        match = IdentityMatch(
            match_score=clamped,
            confidence_label=_confidence_label(clamped),
            matched_signals=signals,
            conflicting_signals=conflicts,
            reasoning=f"Score {clamped:.2f}: {', '.join(signals[:3]) or 'No signals matched'}",
            discovered_name=ev.get("entity_identifier"),
            source_url=source_url,
        )
        matches.append(match)

    unique_matches: list[dict] = []
    seen_scores: set[tuple] = set()
    for m in matches:
        key = (m.match_score, m.source_url or "")
        if key not in seen_scores:
            seen_scores.add(key)
            unique_matches.append(m.to_dict())

    unique_matches.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return unique_matches[:20]


# =========================================================================
# Contact Ranking
# =========================================================================

SOURCE_RANKING = {
    "government_record": 1,
    "official_website": 2,
    "official_business": 3,
    "business_directory": 4,
    "professional_profile": 5,
    "public_web": 6,
    "search_result": 7,
    "public_record": 8,
}


def _refresh_contacts(inv: dict[str, Any]) -> None:
    email_candidates: list[dict] = []
    phone_candidates: list[dict] = []
    website_candidates: list[dict] = []

    for e in inv["evidence"]:
        field = e.get("field", "")
        if field == "email":
            email_candidates.append({
                "value": e.get("value", ""),
                "source_url": e.get("source_url"),
                "source_type": e.get("source_type", "public_web"),
                "source_domain": e.get("source_domain"),
                "confidence": e.get("confidence_score", 0),
                "evidence_text": e.get("evidence_text"),
                "is_generic": _is_generic_email(e.get("value", "")),
            })
        elif field == "phone":
            phone_candidates.append({
                "value": e.get("value", ""),
                "source_url": e.get("source_url"),
                "source_type": e.get("source_type", "public_web"),
                "source_domain": e.get("source_domain"),
                "confidence": e.get("confidence_score", 0),
                "evidence_text": e.get("evidence_text"),
            })
        elif field == "website":
            website_candidates.append({
                "value": e.get("value", ""),
                "source_url": e.get("source_url"),
                "source_type": e.get("source_type", "public_web"),
                "source_domain": e.get("source_domain"),
                "confidence": e.get("confidence_score", 0),
            })

    def _sort_key(c: dict) -> tuple:
        rank = SOURCE_RANKING.get(c.get("source_type", ""), 99)
        conf = c.get("confidence", 0)
        generic_penalty = -0.1 if c.get("is_generic") else 0
        return (rank, -(conf + generic_penalty))

    email_candidates.sort(key=_sort_key)
    phone_candidates.sort(key=_sort_key)
    website_candidates.sort(key=_sort_key)

    email_candidates = _dedupe_by_value(email_candidates, "value")
    phone_candidates = _dedupe_by_value(phone_candidates, "value")
    website_candidates = _dedupe_by_value(website_candidates, "value")

    inv["contacts"]["email_candidates"] = email_candidates
    inv["contacts"]["phone_candidates"] = phone_candidates
    inv["contacts"]["website_candidates"] = website_candidates

    non_generic_emails = [c for c in email_candidates if not c.get("is_generic")]
    inv["contacts"]["preferred_email"] = (
        non_generic_emails[0]["value"] if non_generic_emails
        else (email_candidates[0]["value"] if email_candidates else None)
    )
    inv["contacts"]["preferred_phone"] = phone_candidates[0]["value"] if phone_candidates else None
    inv["contacts"]["preferred_website"] = website_candidates[0]["value"] if website_candidates else None


def _refresh_summary(inv: dict[str, Any]) -> None:
    inv["summary"] = {
        "emails_found": len([e for e in inv["evidence"] if e.get("field") == "email"]),
        "phones_found": len([e for e in inv["evidence"] if e.get("field") == "phone"]),
        "websites_found": len([e for e in inv["evidence"] if e.get("field") == "website"]),
        "profiles_found": len([e for e in inv["evidence"] if e.get("field") == "linkedin_profile"]),
        "entities_found": len([
            e for e in inv["evidence"]
            if e.get("field") in ("business_listing", "business_record", "project_relationship")
        ]),
    }


def _update_overall_status(inv: dict[str, Any]) -> None:
    statuses = list(inv["sources"].values())

    if all(s == "NOT_STARTED" for s in statuses):
        inv["status"] = "NOT_STARTED"
    elif all(s in ("ENRICHED", "NOT_FOUND") for s in statuses):
        enriched_count = sum(1 for s in statuses if s == "ENRICHED")
        if enriched_count >= 3:
            inv["status"] = "ENRICHED"
        elif enriched_count >= 1:
            inv["status"] = "PARTIAL"
        else:
            inv["status"] = "NOT_FOUND"
    elif any(s == "ERROR" for s in statuses):
        non_error = [s for s in statuses if s != "ERROR"]
        if any(s == "ENRICHED" for s in non_error):
            inv["status"] = "PARTIAL"
        else:
            inv["status"] = "ERROR"
    elif any(s == "IN_PROGRESS" for s in statuses):
        inv["status"] = "IN_PROGRESS"
    elif any(s == "ENRICHED" for s in statuses):
        inv["status"] = "PARTIAL"
    else:
        inv["status"] = "NOT_FOUND"

    inv["completed_at"] = _now_iso()


# =========================================================================
# Investigation Orchestrator
# =========================================================================

def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def run_all(
    lead: dict[str, Any],
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    inv["status"] = "IN_PROGRESS"
    inv["started_at"] = inv["started_at"] or _now_iso()
    inv["last_at"] = _now_iso()

    session = _create_session()
    key = serpapi_key or os.environ.get("SERPAPI_API_KEY")

    pipelines = [
        ("web", run_web_search),
        ("website", run_website_discovery),
        ("directories", run_business_directories),
        ("project", run_project_relationships),
        ("linkedin", run_linkedin_discovery),
        ("contact", run_contact_discovery),
        ("public_records", run_public_records),
    ]

    for source_name, pipeline_fn in pipelines:
        try:
            inv = pipeline_fn(
                lead=lead,
                session=session,
                serpapi_key=key,
                force=force,
                note=note,
            )
            lead["investigation"] = inv
        except Exception as exc:
            inv["sources"][source_name] = "ERROR"
            inv["errors"].append(f"{source_name}: {exc}")
            event = InvestigationEvent(
                action=f"{source_name}_error",
                source=source_name,
                occurred_at=_now_iso(),
                result="error",
                error=str(exc),
            )
            inv["events"].append(event.to_dict())

    inv["identity_matches"] = resolve_identities(lead)
    inv = get_investigation(lead)
    _update_overall_status(inv)
    inv["completed_at"] = _now_iso()

    lead["investigation"] = inv
    return inv


def run_single_source(
    lead: dict[str, Any],
    source: str,
    serpapi_key: Optional[str] = None,
    force: bool = False,
    note: Optional[str] = None,
) -> dict[str, Any]:
    inv = get_investigation(lead)
    inv["status"] = "IN_PROGRESS"
    inv["started_at"] = inv["started_at"] or _now_iso()
    inv["last_at"] = _now_iso()

    session = _create_session()
    key = serpapi_key or os.environ.get("SERPAPI_API_KEY")

    pipeline_map = {
        "web": run_web_search,
        "website": run_website_discovery,
        "directories": run_business_directories,
        "linkedin": run_linkedin_discovery,
        "public_records": run_public_records,
        "project": run_project_relationships,
        "contact": run_contact_discovery,
    }

    fn = pipeline_map.get(source)
    if not fn:
        inv["errors"].append(f"Unknown source: {source}")
        return inv

    try:
        inv = fn(
            lead=lead,
            session=session,
            serpapi_key=key,
            force=force,
            note=note,
        )
    except Exception as exc:
        inv["sources"][source] = "ERROR"
        inv["errors"].append(f"{source}: {exc}")
        event = InvestigationEvent(
            action=f"{source}_error",
            source=source,
            occurred_at=_now_iso(),
            result="error",
            error=str(exc),
        )
        inv["events"].append(event.to_dict())

    lead["investigation"] = inv
    inv["identity_matches"] = resolve_identities(lead)
    inv = get_investigation(lead)
    _update_overall_status(inv)
    inv["completed_at"] = _now_iso()

    lead["investigation"] = inv
    return inv


__all__ = [
    "new_investigation_profile",
    "get_investigation",
    "run_all",
    "run_single_source",
    "run_web_search",
    "run_website_discovery",
    "run_business_directories",
    "run_linkedin_discovery",
    "run_public_records",
    "run_project_relationships",
    "run_contact_discovery",
    "resolve_identities",
    "INVESTIGATION_SOURCES",
    "INVESTIGATION_STATUSES",
]
