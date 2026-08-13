"""
PermitSignal Applicant Identity & Contact Intelligence

Purpose
-------
Turn an extracted government applicant/project into a defensible contact record.

Design principles
-----------------
1. Never guess an email from a person's name.
2. Separate identity confidence from contact confidence.
3. Prefer evidence from official/company domains.
4. Keep every discovered URL/email with its source.
5. Support SerpAPI when SERPAPI_API_KEY is available.
6. Work without live search for deterministic unit testing.
7. Return a stable schema that can be persisted in Supabase later.

This module deliberately does NOT send outreach.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b"
)

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?"
    r"(?:\(?\d{3}\)?[\s.\-]?)"
    r"\d{3}[\s.\-]\d{4}(?!\d)"
)

DOMAIN_BADLIST = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "localhost",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}

GENERIC_MAILBOXES = {
    "info",
    "contact",
    "hello",
    "office",
    "admin",
    "sales",
    "support",
    "leasing",
    "development",
    "planning",
    "projects",
    "inquiries",
    "inquiry",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151.0 Safari/537.36 PermitSignal/1.0"
)


@dataclass
class Evidence:
    kind: str
    value: str
    source_url: Optional[str] = None
    source_domain: Optional[str] = None
    snippet: Optional[str] = None
    confidence: float = 0.0


@dataclass
class ContactCandidate:
    value: str
    kind: str
    source_url: Optional[str] = None
    source_domain: Optional[str] = None
    evidence_type: str = "unknown"
    confidence: float = 0.0
    is_generic: bool = False
    is_free_email: bool = False


@dataclass
class ApplicantIdentity:
    applicant_name: Optional[str] = None
    company_name: Optional[str] = None
    applicant_email: Optional[str] = None
    applicant_phone: Optional[str] = None
    company_website: Optional[str] = None
    linkedin_url: Optional[str] = None

    identity_confidence: str = "LOW"
    email_confidence: str = "LOW"
    phone_confidence: str = "LOW"
    enrichment_status: str = "not_searched"

    email_source: Optional[str] = None
    phone_source: Optional[str] = None
    website_source: Optional[str] = None

    evidence: list[dict[str, Any]] = field(default_factory=list)
    email_candidates: list[dict[str, Any]] = field(default_factory=list)
    phone_candidates: list[dict[str, Any]] = field(default_factory=list)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_space(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("mailto:", "")
    return value.strip(" <>[](){}.,;:")


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def domain_of(url_or_email: Optional[str]) -> Optional[str]:
    if not url_or_email:
        return None

    value = url_or_email.strip().lower()

    if "@" in value and "://" not in value:
        return value.rsplit("@", 1)[1].strip(" .")

    try:
        return urlparse(normalize_url(value)).netloc.lower().split(":")[0]
    except Exception:
        return None


def clean_applicant_name(name: Optional[str]) -> Optional[str]:
    name = normalize_space(name)
    if not name:
        return None

    # Remove obvious government-role labels when the extractor accidentally
    # includes them in the applicant field.
    name = re.sub(
        r"\b(requests?|development services|citywide application)\b",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"\s+", " ", name).strip(" -,:;")
    return name or None


def extract_emails(text: str) -> list[str]:
    if not text:
        return []

    found = []
    seen = set()

    # Handle PDF/HTML mailto artifacts.
    cleaned = (
        text.replace(r"\:", ":")
        .replace(r"\_", "_")
        .replace(r"\-", "-")
    )

    for match in EMAIL_RE.findall(cleaned):
        email = normalize_email(match)
        if email and email not in seen:
            seen.add(email)
            found.append(email)

    return found


def extract_phones(text: str) -> list[str]:
    if not text:
        return []

    found = []
    seen = set()

    for match in PHONE_RE.findall(text):
        phone = re.sub(r"\s+", " ", match).strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 10:
            normalized = phone
            if normalized not in seen:
                seen.add(normalized)
                found.append(normalized)

    return found


def is_placeholder_email(email: str) -> bool:
    email = normalize_email(email)
    domain = domain_of(email)
    return not domain or domain in DOMAIN_BADLIST


def is_free_email(email: str) -> bool:
    return domain_of(email) in FREE_EMAIL_DOMAINS


def mailbox_name(email: str) -> str:
    return normalize_email(email).split("@", 1)[0].lower()


def is_generic_email(email: str) -> bool:
    return mailbox_name(email) in GENERIC_MAILBOXES


def validate_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(EMAIL_RE.fullmatch(email)) and not is_placeholder_email(email)


def score_email_candidate(
    email: str,
    applicant_name: Optional[str],
    project_address: Optional[str],
    source_url: Optional[str],
    evidence_type: str,
) -> float:
    if not validate_email(email):
        return 0.0

    score = 0.40
    domain = domain_of(email)

    if evidence_type == "official_site":
        score += 0.25
    elif evidence_type == "search_result":
        score += 0.05
    elif evidence_type == "government_record":
        score += 0.30

    if domain and not is_free_email(email):
        score += 0.10

    if is_generic_email(email):
        score -= 0.10

    if applicant_name:
        tokens = [
            t.lower()
            for t in re.findall(r"[A-Za-z]{2,}", applicant_name)
        ]
        local = mailbox_name(email)
        if any(t in local for t in tokens):
            score += 0.10

    # A source on the same domain as the discovered company is stronger
    # than an unrelated aggregator.
    if source_url:
        source_domain = domain_of(source_url)
        if source_domain == domain:
            score += 0.05

    return min(1.0, round(score, 3))


def confidence_label(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    return "LOW"


def build_search_queries(
    applicant_name: Optional[str],
    project_address: Optional[str],
    municipality: Optional[str] = None,
    state: Optional[str] = None,
) -> list[str]:
    name = clean_applicant_name(applicant_name)
    address = normalize_space(project_address)
    municipality = normalize_space(municipality)
    state = normalize_space(state)

    queries: list[str] = []

    location = " ".join(x for x in [municipality, state] if x)

    if name and address:
        queries.append(f'"{name}" "{address}"')
    if name and location:
        queries.append(f'"{name}" "{location}"')
    if name:
        queries.append(f'"{name}" contact email')
    if name and address:
        queries.append(f'"{name}" "{address}" email')
    if name:
        queries.append(f'"{name}" LinkedIn')

    # Deduplicate while preserving order.
    output = []
    seen = set()
    for query in queries:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            output.append(query)

    return output


def _same_person_or_company_hint(
    applicant_name: Optional[str],
    text: str,
) -> float:
    if not applicant_name or not text:
        return 0.0

    name_tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z]{2,}", applicant_name)
    ]
    haystack = text.lower()

    if not name_tokens:
        return 0.0

    matches = sum(token in haystack for token in name_tokens)
    return min(0.30, matches * 0.15)


def parse_search_result(
    result: dict[str, Any],
    applicant_name: Optional[str],
    project_address: Optional[str],
) -> list[Evidence]:
    title = normalize_space(str(result.get("title") or ""))
    snippet = normalize_space(str(result.get("snippet") or ""))
    url = normalize_space(str(result.get("link") or result.get("url") or ""))

    text = " ".join(x for x in [title, snippet] if x)

    if not text:
        return []

    evidence = []
    name_bonus = _same_person_or_company_hint(
        applicant_name,
        text,
    )

    evidence.append(
        Evidence(
            kind="search_result",
            value=text[:500],
            source_url=url,
            source_domain=domain_of(url),
            snippet=snippet[:500] if snippet else None,
            confidence=min(0.90, 0.35 + name_bonus),
        )
    )

    return evidence


def extract_links_from_html(
    html: str,
    base_url: str,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        if full.startswith(("http://", "https://")):
            links.append(full)

    # preserve order and remove duplicates
    output = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            output.append(link)
    return output


def extract_contact_candidates_from_html(
    html: str,
    source_url: str,
    applicant_name: Optional[str] = None,
) -> tuple[list[ContactCandidate], list[ContactCandidate], list[Evidence]]:
    emails = extract_emails(html)
    phones = extract_phones(BeautifulSoup(html, "html.parser").get_text(" "))

    source_domain = domain_of(source_url)

    email_candidates = []
    for email in emails:
        score = score_email_candidate(
            email=email,
            applicant_name=applicant_name,
            project_address=None,
            source_url=source_url,
            evidence_type="official_site",
        )
        email_candidates.append(
            ContactCandidate(
                value=email,
                kind="email",
                source_url=source_url,
                source_domain=source_domain,
                evidence_type="official_site",
                confidence=score,
                is_generic=is_generic_email(email),
                is_free_email=is_free_email(email),
            )
        )

    phone_candidates = []
    for phone in phones:
        phone_candidates.append(
            ContactCandidate(
                value=phone,
                kind="phone",
                source_url=source_url,
                source_domain=source_domain,
                evidence_type="official_site",
                confidence=0.75,
            )
        )

    evidence = []
    for email in emails:
        evidence.append(
            Evidence(
                kind="email",
                value=email,
                source_url=source_url,
                source_domain=source_domain,
                confidence=0.75,
            )
        )

    return email_candidates, phone_candidates, evidence


class ApplicantEnricher:
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def search_serpapi(self, query: str) -> list[dict[str, Any]]:
        if not self.api_key:
            return []

        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": 10,
        }

        response = self.session.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        return data.get("organic_results", []) or []

    def fetch_page(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(
                normalize_url(url),
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and not response.text:
                return None

            return response.text
        except requests.RequestException:
            return None

    def _rank_email_candidates(
        self,
        candidates: Iterable[ContactCandidate],
    ) -> list[ContactCandidate]:
        unique: dict[str, ContactCandidate] = {}

        for candidate in candidates:
            key = candidate.value.lower()
            existing = unique.get(key)
            if not existing or candidate.confidence > existing.confidence:
                unique[key] = candidate

        return sorted(
            unique.values(),
            key=lambda x: x.confidence,
            reverse=True,
        )

    def enrich(
        self,
        application: dict[str, Any],
        live_search: bool = True,
        max_search_results: int = 10,
        crawl_result_pages: bool = True,
    ) -> dict[str, Any]:
        applicant_name = clean_applicant_name(
            application.get("applicant_name")
        )
        project_address = normalize_space(
            application.get("project_address")
        )
        municipality = normalize_space(application.get("municipality"))
        state = normalize_space(application.get("state"))

        identity = ApplicantIdentity(
            applicant_name=applicant_name,
            enrichment_status="not_searched",
        )

        if not applicant_name:
            identity.enrichment_status = "missing_applicant_name"
            return identity.to_dict()

        queries = build_search_queries(
            applicant_name,
            project_address,
            municipality,
            state,
        )

        identity.search_results = []
        all_email_candidates: list[ContactCandidate] = []
        all_phone_candidates: list[ContactCandidate] = []

        if not live_search or not self.api_key:
            identity.enrichment_status = (
                "search_disabled"
                if not live_search
                else "no_search_provider"
            )

            # Preserve contact data that may already exist in the application.
            for email in extract_emails(
                str(application.get("applicant_email") or "")
            ):
                if validate_email(email):
                    all_email_candidates.append(
                        ContactCandidate(
                            value=email,
                            kind="email",
                            evidence_type="government_record",
                            confidence=0.90,
                        )
                    )

            for phone in extract_phones(
                str(application.get("applicant_phone") or "")
            ):
                all_phone_candidates.append(
                    ContactCandidate(
                        value=phone,
                        kind="phone",
                        evidence_type="government_record",
                        confidence=0.90,
                    )
                )

        else:
            identity.enrichment_status = "searched"

            for query in queries:
                try:
                    results = self.search_serpapi(query)
                except (requests.RequestException, ValueError):
                    continue

                for result in results[:max_search_results]:
                    title = normalize_space(str(result.get("title") or ""))
                    snippet = normalize_space(str(result.get("snippet") or ""))
                    url = normalize_space(
                        str(result.get("link") or result.get("url") or "")
                    )

                    identity.search_results.append(
                        {
                            "query": query,
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                        }
                    )

                    identity.evidence.extend(
                        asdict(
                            evidence
                        )
                        for evidence in parse_search_result(
                            result,
                            applicant_name,
                            project_address,
                        )
                    )

                    text = " ".join(
                        x for x in [title, snippet] if x
                    )

                    for email in extract_emails(text):
                        score = score_email_candidate(
                            email=email,
                            applicant_name=applicant_name,
                            project_address=project_address,
                            source_url=url,
                            evidence_type="search_result",
                        )
                        all_email_candidates.append(
                            ContactCandidate(
                                value=email,
                                kind="email",
                                source_url=url,
                                source_domain=domain_of(url),
                                evidence_type="search_result",
                                confidence=score,
                                is_generic=is_generic_email(email),
                                is_free_email=is_free_email(email),
                            )
                        )

                    for phone in extract_phones(text):
                        all_phone_candidates.append(
                            ContactCandidate(
                                value=phone,
                                kind="phone",
                                source_url=url,
                                source_domain=domain_of(url),
                                evidence_type="search_result",
                                confidence=0.45,
                            )
                        )

                    # Crawl likely contact/company pages, but only for actual
                    # HTTP(S) result URLs.
                    if crawl_result_pages and url:
                        url_domain = domain_of(url)
                        if url_domain:
                            html = self.fetch_page(url)
                            if html:
                                (
                                    page_emails,
                                    page_phones,
                                    page_evidence,
                                ) = extract_contact_candidates_from_html(
                                    html,
                                    url,
                                    applicant_name,
                                )

                                all_email_candidates.extend(page_emails)
                                all_phone_candidates.extend(page_phones)
                                identity.evidence.extend(
                                    asdict(e) for e in page_evidence
                                )

                                links = extract_links_from_html(
                                    html,
                                    url,
                                )

                                # Crawl a small number of contact/about pages.
                                likely_links = [
                                    link
                                    for link in links
                                    if any(
                                        token in link.lower()
                                        for token in (
                                            "contact",
                                            "about",
                                            "team",
                                            "people",
                                            "staff",
                                        )
                                    )
                                ][:3]

                                for contact_url in likely_links:
                                    contact_html = self.fetch_page(
                                        contact_url
                                    )
                                    if not contact_html:
                                        continue

                                    (
                                        contact_emails,
                                        contact_phones,
                                        contact_evidence,
                                    ) = extract_contact_candidates_from_html(
                                        contact_html,
                                        contact_url,
                                        applicant_name,
                                    )

                                    all_email_candidates.extend(
                                        contact_emails
                                    )
                                    all_phone_candidates.extend(
                                        contact_phones
                                    )
                                    identity.evidence.extend(
                                        asdict(e)
                                        for e in contact_evidence
                                    )

        email_candidates = self._rank_email_candidates(
            all_email_candidates
        )
        phone_candidates = self._rank_email_candidates(
            all_phone_candidates
        )

        identity.email_candidates = [
            asdict(candidate)
            for candidate in email_candidates
        ]
        identity.phone_candidates = [
            asdict(candidate)
            for candidate in phone_candidates
        ]

        if email_candidates:
            best_email = email_candidates[0]
            identity.applicant_email = best_email.value
            identity.email_source = best_email.source_url
            identity.email_confidence = confidence_label(
                best_email.confidence
            )

        if phone_candidates:
            best_phone = phone_candidates[0]
            identity.applicant_phone = best_phone.value
            identity.phone_source = best_phone.source_url
            identity.phone_confidence = confidence_label(
                best_phone.confidence
            )

        # Existing government contact information is highly valuable,
        # but we keep it clearly distinguished from applicant identity.
        gov_email = application.get("applicant_email")
        gov_phone = application.get("applicant_phone")

        if gov_email and validate_email(str(gov_email)):
            identity.applicant_email = normalize_email(str(gov_email))
            identity.email_source = application.get("source_url")
            identity.email_confidence = "HIGH"

        if gov_phone:
            identity.applicant_phone = str(gov_phone)
            identity.phone_source = application.get("source_url")
            identity.phone_confidence = "HIGH"

        # Identity confidence is based on evidence, not merely finding a
        # matching name in a search result.
        identity_score = 0.0

        if applicant_name:
            identity_score += 0.25

        if project_address and identity.search_results:
            address_tokens = [
                t.lower()
                for t in re.findall(r"[A-Za-z0-9]{3,}", project_address)
            ]
            combined = " ".join(
                (
                    str(x.get("title") or ""),
                    str(x.get("snippet") or ""),
                )
                for x in identity.search_results
            ).lower()

            address_matches = sum(
                token in combined for token in address_tokens
            )
            if address_matches >= 2:
                identity_score += 0.30

        if identity.applicant_email:
            identity_score += 0.25

        if identity.company_website:
            identity_score += 0.20

        identity.identity_confidence = confidence_label(
            min(identity_score, 1.0)
        )

        return identity.to_dict()


def enrich_application(
    application: dict[str, Any],
    live_search: bool = True,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Convenience function used by the rest of PermitSignal.
    """
    enricher = ApplicantEnricher(api_key=api_key)
    return enricher.enrich(
        application,
        live_search=live_search,
    )


def enrich_applicant_identity(application: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministic applicant identity normalization.

    This is the "Applicant Identity" pipeline stage: it performs NO live
    network calls. It only normalizes what the government record (and any
    fields already attached by upstream services) provide, and prepares
    search queries for the separate, optional, live contact-enrichment
    stage (see applicant_enrichment.enrich_applicant_contact).

    Called by pipeline_orchestrator._enrich_applicants() on every run,
    live enrichment or not.
    """
    applicant_name = clean_applicant_name(application.get("applicant_name"))
    project_address = normalize_space(application.get("project_address"))
    municipality = normalize_space(application.get("municipality"))
    state = normalize_space(application.get("state"))

    identity = ApplicantIdentity(applicant_name=applicant_name)

    if not applicant_name:
        identity.enrichment_status = "missing_applicant_name"
        data = identity.to_dict()
        data["identity_status"] = data.pop("enrichment_status")
        return data

    identity.enrichment_status = "identity_only"

    # Government-record contact information has priority over anything a
    # later live-search stage might discover.
    gov_email = application.get("applicant_email")
    if gov_email and validate_email(str(gov_email)):
        identity.applicant_email = normalize_email(str(gov_email))
        identity.email_source = "government_record"
        identity.email_confidence = "HIGH"
        identity.evidence.append(
            asdict(
                Evidence(
                    kind="email",
                    value=identity.applicant_email,
                    source_url=normalize_space(application.get("source_url")),
                    source_domain=domain_of(application.get("source_url")),
                    confidence=1.0,
                )
            )
        )

    gov_phone = application.get("applicant_phone")
    if gov_phone:
        identity.applicant_phone = normalize_space(str(gov_phone))
        identity.phone_source = "government_record"
        identity.phone_confidence = "HIGH"

    # Never fabricate a company/website — only carry forward what an
    # upstream service has already independently attached.
    company_name = normalize_space(application.get("company_name"))
    if company_name:
        identity.company_name = company_name

    company_website = application.get("company_website") or application.get("website")
    if company_website:
        identity.company_website = normalize_url(str(company_website))
        identity.website_source = "government_record"

    identity.search_queries = build_search_queries(
        applicant_name,
        project_address,
        municipality,
        state,
    )

    identity_score = 0.0
    if applicant_name:
        identity_score += 0.25
    if identity.applicant_email:
        identity_score += 0.35
    if identity.company_website:
        identity_score += 0.20
    identity.identity_confidence = confidence_label(min(identity_score, 1.0))

    data = identity.to_dict()
    # Renamed so this identity-stage status never collides with the
    # separate contact-enrichment "enrichment_status" field set later in
    # the pipeline (disabled/enriched/not_found/failed).
    data["identity_status"] = data.pop("enrichment_status")
    data["normalized_applicant_name"] = applicant_name
    data["email_domain"] = domain_of(identity.applicant_email) if identity.applicant_email else None
    data["website_domain"] = domain_of(identity.company_website) if identity.company_website else None
    data["company_domain"] = data["website_domain"]
    return data


def merge_identity_into_opportunity(
    opportunity: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    """
    Attach identity/contact intelligence to a canonical opportunity
    without overwriting stronger existing government-record values.
    """
    result = dict(opportunity)

    mapping = {
        "applicant_email": "applicant_email",
        "applicant_phone": "applicant_phone",
        "company_name": "company_name",
        "company_website": "company_website",
        "linkedin_url": "linkedin_url",
    }

    for target, source in mapping.items():
        current = result.get(target)
        incoming = identity.get(source)
        if not current and incoming:
            result[target] = incoming

    result["identity_confidence"] = identity.get(
        "identity_confidence",
        "LOW",
    )
    result["email_confidence"] = identity.get(
        "email_confidence",
        "LOW",
    )
    result["phone_confidence"] = identity.get(
        "phone_confidence",
        "LOW",
    )
    result["enrichment_status"] = identity.get(
        "enrichment_status",
        "unknown",
    )
    result["email_source"] = identity.get("email_source")
    result["phone_source"] = identity.get("phone_source")
    result["website_source"] = identity.get("website_source")
    result["email_candidates"] = identity.get("email_candidates", [])
    result["phone_candidates"] = identity.get("phone_candidates", [])

    return result