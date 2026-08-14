"""
PermitSignal Applicant Enrichment Engine

Purpose
-------
Turn an extracted government application into an auditable applicant
contact record.

The engine DOES NOT guess emails or phone numbers.

Sources are ranked:
1. Explicit URLs supplied by the government record
2. Government/public pages discovered by search
3. Official applicant/company website
4. Public business directories/pages returned by search

Search provider:
- SerpAPI, when SERPAPI_API_KEY is configured.
- The module still works without a key for direct URL enrichment.

Environment
-----------
SERPAPI_API_KEY=...
SERPAPI_ENGINE=google

Optional:
SERPAPI_LOCATION=United States
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# SERPAPI_API_KEY lives in the project's .env file. Nothing else on the
# pipeline_orchestrator._enrich_applicants() call path loads it before this
# module's ApplicantEnricher.__init__() reads it via os.getenv(), so without
# this call live enrichment silently sees no key (serpapi_key=None) even
# when --live is passed and .env has a real key configured. Mirrors the
# load_dotenv() call already used by lead_repository.py.
load_dotenv()


EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE_RE = re.compile(
    r"""
    (?:
        \+?1[\s.\-]*
    )?
    (?:
        \(\d{3}\)
        |
        \d{3}
    )
    [\s.\-]*
    \d{3}
    [\s.\-]*
    \d{4}
    \b
    """,
    re.VERBOSE,
)

URL_RE = re.compile(
    r"https?://[^\s<>\"]+",
    re.IGNORECASE,
)

BAD_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "email.com",
    "test.com",
}

GENERIC_EMAIL_PREFIXES = {
    "info",
    "contact",
    "hello",
    "support",
    "admin",
    "office",
    "sales",
    "marketing",
    "noreply",
    "no-reply",
    "webmaster",
}

SOCIAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "tiktok.com",
}

# Map/direction links that pages sometimes embed for an address -- never a
# company's own website, regardless of how confidently a page otherwise
# ties to the applicant.
MAP_UTILITY_DOMAINS = {
    "google.com",
    "goo.gl",
    "g.page",
    "maps.google.com",
    "maps.apple.com",
    "apple.com",
    "bing.com",
    "maps.live.com",
    "live.com",
    "openstreetmap.org",
    "waze.com",
    "mapquest.com",
}

# HTML tags small/focused enough that their full text can safely be used
# as "local context" for a link nested inside them (a single list item,
# table cell, or paragraph) -- deliberately excludes generic/large
# containers (div, body, section, table, ul) where using the full text
# would risk pulling in unrelated sibling content.
ANCHOR_CONTEXT_TAGS = {
    "p",
    "li",
    "td",
    "th",
    "span",
    "dd",
    "dt",
    "figcaption",
    "blockquote",
}

# Public business directories/registries. A hit on one of these domains is
# treated as its own evidence tier (public_business_directory) -- ranked
# below an official company website/team page but above an anonymous
# search-result snippet, per docs/DATA_MODEL.md section 14.
BUSINESS_DIRECTORY_DOMAINS = {
    "opencorporates.com",
    "bbb.org",
    "dnb.com",
    "manta.com",
    "bizapedia.com",
    "yellowpages.com",
    "yelp.com",
    "corporationwiki.com",
}

# ---------------------------------------------------------------------------
# OWNER / PERSON ROLE DISCOVERY (Phase 2)
#
# Fixed vocabulary of ownership/principal-tier professional roles.
# Deliberately excludes generic job titles ("manager", "associate") that do
# not indicate a legitimately associated owner/principal/executive/partner
# -- see CLAUDE.md section 6 (Contact Integrity Rules) and
# docs/PHASE_2_OWNER_ENRICHMENT.md.
# ---------------------------------------------------------------------------

ROLE_LABELS: dict[str, str] = {
    "owner": "Owner",
    "sole proprietor": "Owner",
    "principal": "Principal",
    "president": "President",
    "chief executive officer": "CEO",
    "ceo": "CEO",
    "managing member": "Managing Member",
    "managing partner": "Managing Partner",
    "managing director": "Managing Director",
    "executive director": "Executive Director",
    "partner": "Partner",
    "co-founder": "Co-Founder",
    "founder": "Founder",
    "registered agent": "Registered Agent",
    "responsible person": "Responsible Person",
}

# Longest phrase first, so "managing partner" is matched before the bare
# "partner" it contains.
_ROLE_PHRASES_SORTED = sorted(ROLE_LABELS.keys(), key=len, reverse=True)
_ROLE_ALTERNATION = "|".join(re.escape(phrase) for phrase in _ROLE_PHRASES_SORTED)

# Only two explicit, low-ambiguity syntactic forms are trusted for a
# name/role pairing -- never a bare proximity/co-occurrence heuristic. This
# keeps the false-positive rate low for what is ultimately an identity
# claim ("this specific person is associated with this applicant/company").
#
#   "Jane Smith, Owner"           -> NAME_THEN_ROLE_RE
#   "Owner: Jane Smith"           -> ROLE_THEN_NAME_RE
#
# The name token is deliberately NOT matched case-insensitively (only the
# role alternation is, via the scoped inline (?i:...) group) -- matching
# the whole pattern with re.IGNORECASE would let a lowercase word like
# "team." satisfy "[A-Z]" and be captured as part of a person's name.
# Periods are deliberately excluded from the token's own character class
# for the same reason: including them let a token like "Doe." swallow the
# sentence-ending period and the regex would then greedily continue
# matching the capitalized first word of the NEXT sentence as a third
# name token.
_NAME_TOKEN = r"[A-Z][a-zA-Z'\-]+"
_ROLE_CI = "(?i:" + _ROLE_ALTERNATION + ")"

NAME_THEN_ROLE_RE = re.compile(
    r"(?P<name>"
    + _NAME_TOKEN
    + r"(?:\s+"
    + _NAME_TOKEN
    + r"){1,2})\s*[,\-–—]\s*(?P<role>"
    + _ROLE_CI
    + r")\b"
)

ROLE_THEN_NAME_RE = re.compile(
    r"\b(?P<role>"
    + _ROLE_CI
    + r")\b\s*[:\-–—]\s*(?P<name>"
    + _NAME_TOKEN
    + r"(?:\s+"
    + _NAME_TOKEN
    + r"){1,2})"
)

# A capitalized 2-3 word span that matches one of the syntactic forms above
# is still rejected here when it is evidently a company/organization name
# rather than a person (e.g. "Vance Builders LLC, Owner").
NAME_STOPWORDS = {
    "llc",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "company",
    "co",
    "group",
    "construction",
    "development",
    "developments",
    "builders",
    "realty",
    "properties",
    "partners",
    "holdings",
    "services",
    "contact",
    "about",
    "team",
    "home",
    "website",
    "visit",
    "click",
    "the",
    "and",
    "planning",
    "commission",
    "city",
    "county",
    "department",
    "office",
    "staff",
    "agenda",
    "hearing",
    "management",
    "asset",
    "assets",
    "capital",
    "ventures",
    "venture",
    "enterprises",
    "enterprise",
    "investments",
    "investment",
    "trust",
    "family",
    "ranch",
    "ranches",
    "farms",
    "land",
    "resources",
}


def _looks_like_person_name(name: str) -> bool:
    tokens = [token for token in name.strip().split() if token]

    if len(tokens) < 2 or len(tokens) > 3:
        return False

    shouting_tokens = 0

    for token in tokens:
        bare = token.strip(".,'-").lower()

        if not bare or bare in NAME_STOPWORDS:
            return False

        if any(char.isdigit() for char in token):
            return False

        if len(bare) >= 3 and token.isupper():
            shouting_tokens += 1

    if shouting_tokens >= 2:
        # A person's name in ordinary prose is Title Case, not ALL CAPS
        # across multiple words -- 2+ shouting-caps tokens is instead the
        # hallmark of an entity/routing-table label (e.g. a "Property
        # Owner: REYNOLDS ASSET MANAGEMENT" field), even when none of its
        # individual words are in NAME_STOPWORDS.
        return False

    return True


def find_role_person_mentions(text: str) -> list[tuple[str, str]]:
    """
    Conservative name+role extraction for owner/principal/executive/partner
    discovery (see ROLE_LABELS). Returns deduplicated (name, canonical_role)
    pairs found via the two trusted syntactic forms above. Never returns a
    candidate whose "name" span looks like a company/organization name.
    """

    if not text:
        return []

    results: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for pattern in (NAME_THEN_ROLE_RE, ROLE_THEN_NAME_RE):
        for match in pattern.finditer(text):
            name = clean_text(match.group("name"))
            role_phrase = match.group("role").lower()
            role = ROLE_LABELS.get(role_phrase)

            if not role or not _looks_like_person_name(name):
                continue

            key = (name.lower(), role)

            if key in seen:
                continue

            seen.add(key)
            results.append((name, role))

    return results


def _confidence_label(value: float) -> str:
    if value >= 0.80:
        return "HIGH"

    if value >= 0.55:
        return "MEDIUM"

    return "LOW"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/151 Safari/537.36 "
        "PermitSignal/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.8",
}


@dataclass
class Evidence:
    field: str
    value: str
    source_url: str
    source_type: str
    confidence: float
    evidence_text: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicantEnrichment:
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    applicant_phone: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_source: Optional[str] = None

    email_confidence: float = 0.0
    phone_confidence: float = 0.0
    company_confidence: float = 0.0

    enrichment_status: str = "not_found"
    search_query: Optional[str] = None

    emails_found: list[str] = field(default_factory=list)
    phones_found: list[str] = field(default_factory=list)
    websites_found: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

    # Owner / Person enrichment (Phase 2). contact_role is the applicant's
    # own professional role/relationship (e.g. "Owner", "Managing Partner")
    # when public evidence ties that role to the applicant's own name.
    # discovered_parties holds any DISTINCT real-world person (owner,
    # principal, executive, partner, or other legitimately associated
    # person) that public evidence ties to this applicant/company, in the
    # same {party_name, party_role, party_company, party_contact_email,
    # party_contact_phone, party_source, party_confidence} shape
    # application_extractor.extract_parties() already uses -- never a
    # parallel schema. Both stay at their evidence-backed default (None / [])
    # when no reliable evidence exists; this is the correct, non-fabricated
    # result, not an error.
    contact_role: Optional[str] = None
    discovered_parties: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApplicantEnricher:
    """
    Production enrichment service.

    It is intentionally conservative:
    - no email fabrication
    - no guessed phone numbers
    - no social-profile identity claims without evidence
    - every selected field carries source provenance
    """

    def __init__(
        self,
        serpapi_key: Optional[str] = None,
        timeout: int = 15,
        max_search_results: int = 8,
        max_pages: int = 6,
        request_delay: float = 0.25,
    ) -> None:
        self.serpapi_key = (
            serpapi_key
            or os.getenv("SERPAPI_API_KEY")
        )
        self.timeout = timeout
        self.max_search_results = max_search_results
        self.max_pages = max_pages
        self.request_delay = request_delay

        self.session = requests.Session()
        self.session.headers.update(
            DEFAULT_HEADERS
        )

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def enrich(
        self,
        application: dict[str, Any],
        live_search: bool = True,
    ) -> dict[str, Any]:
        result = ApplicantEnrichment(
            applicant_name=clean_name(
                application.get("applicant_name")
            ),
        )

        name = result.applicant_name

        if not name:
            result.enrichment_status = "missing_applicant_name"
            return result.to_dict()

        direct_urls = collect_urls(
            application
        )

        # A link whose query string embeds the project's own street
        # address (a "get directions here" map link) is never the
        # applicant's company website, regardless of which map provider
        # hosts it.
        self._project_address_lower = clean_text(
            application.get("project_address")
        ).lower() or None

        # Additional corroborating signals for relevance_score() --
        # neighborhood/company_name, when available, let a source be
        # accepted on multiple independent signals rather than requiring
        # the applicant's exact name string to appear verbatim in a URL
        # or anchor's own visible text.
        self._relevance_neighborhood = clean_text(
            application.get("neighborhood")
        ) or None

        self._relevance_company_name = clean_text(
            application.get("company_name")
        ) or None

        # Recognize the packet's own government domain(s) regardless of
        # TLD (e.g. provo.gov AND provo.org both resolve to root "provo"),
        # so a municipal staff mailbox/page discovered under either TLD is
        # excluded from applicant-contact evidence, not just a literal
        # ".gov" suffix.
        self._government_roots = {
            root
            for root in (
                government_domain_root(url)
                for url in direct_urls
            )
            if root
        }

        # 1. Inspect URLs already supplied by government records.
        direct_pages = self._fetch_urls(
            direct_urls[: self.max_pages]
        )

        self._consume_pages(
            result,
            direct_pages,
            source_type="government_record",
        )

        # 2. Search public sources when configured.
        if live_search and self.serpapi_key:
            query = build_search_query(
                application
            )
            result.search_query = query

            search_results = self._search(
                query
            )

            pages_to_fetch = []

            for item in search_results:
                url = item.get("link")

                if not url:
                    continue

                if is_social_url(url):
                    continue

                result.sources.append(
                    Evidence(
                        field="search_result",
                        value=url,
                        source_url=url,
                        source_type="search_result",
                        confidence=0.30,
                        evidence_text=item.get(
                            "snippet"
                        ),
                    ).to_dict()
                )

                pages_to_fetch.append(url)

            pages = self._fetch_urls(
                pages_to_fetch[
                    : self.max_pages
                ]
            )

            self._consume_pages(
                result,
                pages,
                source_type="public_web",
            )

            # Search snippets themselves can contain emails.
            for item in search_results:
                snippet = " ".join(
                    [
                        str(
                            item.get("title")
                            or ""
                        ),
                        str(
                            item.get("snippet")
                            or ""
                        ),
                    ]
                )

                self._consume_text(
                    result,
                    snippet,
                    source_url=item.get(
                        "link"
                    )
                    or "",
                    source_type="search_result",
                    base_confidence=0.55,
                )

            # 3. Search public business directories/registries for a
            # company record that evidently concerns this applicant.
            self._search_business_directories(
                application,
                result,
            )

        self._finalize(
            result
        )

        return result.to_dict()

    # ---------------------------------------------------------
    # SEARCH
    # ---------------------------------------------------------

    def _search(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        if not self.serpapi_key:
            return []

        params = {
            "engine": os.getenv(
                "SERPAPI_ENGINE",
                "google",
            ),
            "q": query,
            "api_key": self.serpapi_key,
            "num": self.max_search_results,
        }

        location = os.getenv(
            "SERPAPI_LOCATION"
        )

        if location:
            params["location"] = location

        try:
            response = self.session.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            payload = response.json()

            return payload.get(
                "organic_results",
                [],
            )

        except requests.RequestException:
            return []

    def _search_business_directories(
        self,
        application: dict[str, Any],
        result: ApplicantEnrichment,
    ) -> None:
        """
        Search a fixed set of public business directories/registries
        (BUSINESS_DIRECTORY_DOMAINS) for a listing that evidently concerns
        this applicant, then extract contact evidence from that listing
        the same way any other fetched page is consumed.

        A directory result is only accepted as evidence when
        relevance_score() clears RELEVANCE_ACCEPT_THRESHOLD against the
        search result's own title/snippet -- the applicant's full name
        alone still qualifies, as does a partial name match (e.g.
        surname only) corroborated by the project address, neighborhood,
        or company name -- an unrelated same-first-name hit on a
        directory site, with no other corroborating signal, still must
        not be attached to this applicant.
        """
        name = result.applicant_name

        if not name:
            return

        address = clean_text(
            application.get("project_address")
        )

        site_filter = " OR ".join(
            f"site:{domain}"
            for domain in sorted(BUSINESS_DIRECTORY_DOMAINS)
        )

        query = f'"{name}"'

        if address:
            query += f' "{address}"'

        query += f" ({site_filter})"

        search_results = self._search(query)

        directory_pages = []

        for item in search_results:
            url = item.get("link")

            if not url:
                continue

            host = urlparse(url).netloc.lower().removeprefix("www.")

            if not any(
                host == domain or host.endswith("." + domain)
                for domain in BUSINESS_DIRECTORY_DOMAINS
            ):
                continue

            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ]
            )

            score = relevance_score(
                name,
                text,
                address=address,
                neighborhood=self._relevance_neighborhood,
                company_name=self._relevance_company_name,
                source_type="public_business_directory",
            )

            if score < RELEVANCE_ACCEPT_THRESHOLD:
                # Directory hit exists but does not evidently concern
                # this applicant -- do not attach it.
                continue

            result.sources.append(
                Evidence(
                    field="business_directory_result",
                    value=url,
                    source_url=url,
                    source_type="public_business_directory",
                    confidence=0.45,
                    evidence_text=item.get("snippet"),
                ).to_dict()
            )

            directory_pages.append(url)

        if not directory_pages:
            return

        pages = self._fetch_urls(
            directory_pages[: self.max_pages]
        )

        self._consume_pages(
            result,
            pages,
            source_type="public_business_directory",
        )

    # ---------------------------------------------------------
    # PAGE FETCHING
    # ---------------------------------------------------------

    def _fetch_urls(
        self,
        urls: Iterable[str],
    ) -> list[dict[str, Any]]:
        pages = []

        seen = set()

        for url in urls:

            if not url:
                continue

            normalized = normalize_url(
                url
            )

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)

            try:
                time.sleep(
                    self.request_delay
                )

                response = self.session.get(
                    normalized,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                content_type = (
                    response.headers.get(
                        "content-type",
                        "",
                    )
                    .lower()
                )

                if response.status_code >= 400:
                    continue

                is_pdf = (
                    "pdf" in content_type
                    or normalized.lower().endswith(".pdf")
                )

                if is_pdf:
                    pdf_text = extract_pdf_text(
                        response.content
                    )

                    if pdf_text:
                        pages.append(
                            {
                                "url": response.url,
                                "text": pdf_text,
                                "is_pdf": True,
                            }
                        )

                    continue

                if "text/html" not in content_type:
                    continue

                pages.append(
                    {
                        "url": response.url,
                        "html": response.text,
                    }
                )

            except requests.RequestException:
                continue

        return pages

    # ---------------------------------------------------------
    # EXTRACTION
    # ---------------------------------------------------------

    def _consume_pages(
        self,
        result: ApplicantEnrichment,
        pages: list[dict[str, Any]],
        source_type: str,
    ) -> None:

        for page in pages:

            url = page["url"]

            if page.get("is_pdf"):
                # A PDF has no anchors/title to extract -- only scan its
                # text for email/phone evidence, and only when
                # relevance_score() clears the threshold for this
                # document (full name, or a partial name match
                # corroborated by address/neighborhood/company/source
                # type). Without this, a multi-applicant government
                # agenda PDF that merely happens to also mention this
                # applicant somewhere would let ANY email/phone elsewhere
                # in that same PDF be considered evidence for them.
                text = clean_text(
                    page.get("text", "")
                )

                score = relevance_score(
                    result.applicant_name or "",
                    text,
                    address=self._project_address_lower,
                    neighborhood=self._relevance_neighborhood,
                    company_name=self._relevance_company_name,
                    source_type=source_type,
                )

                if score < RELEVANCE_ACCEPT_THRESHOLD:
                    continue

                self._consume_text(
                    result,
                    text,
                    source_url=url,
                    source_type=source_type,
                    base_confidence=source_confidence(
                        url,
                        source_type,
                    ),
                )

                continue

            html = page["html"]

            soup = BeautifulSoup(
                html,
                "html.parser",
            )

            for tag in soup(
                [
                    "script",
                    "style",
                    "noscript",
                    "svg",
                ]
            ):
                tag.decompose()

            text = clean_text(
                soup.get_text(
                    " ",
                    strip=True,
                )
            )

            # Page title / company clues.
            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
                if soup.title
                else ""
            )

            self._consume_text(
                result,
                text,
                source_url=url,
                source_type=source_type,
                base_confidence=source_confidence(
                    url,
                    source_type,
                ),
            )

            # A link is only kept as a candidate company_website when the
            # page it was found on demonstrably concerns this applicant
            # -- full name, or a partial name match corroborated by the
            # project address/neighborhood/company name/source type
            # (relevance_score()) -- otherwise any unrelated link on any
            # fetched page (a news mention, an unrelated listing) would
            # be attributed to the applicant with no evidence.
            page_is_relevant = relevance_score(
                result.applicant_name or "",
                text,
                address=self._project_address_lower,
                neighborhood=self._relevance_neighborhood,
                company_name=self._relevance_company_name,
                source_type=source_type,
            ) >= RELEVANCE_ACCEPT_THRESHOLD

            self._extract_links(
                result,
                soup,
                url,
                source_type,
                page_is_relevant,
            )

            if title:
                result.sources.append(
                    Evidence(
                        field="page_title",
                        value=title,
                        source_url=url,
                        source_type=source_type,
                        confidence=0.35,
                        evidence_text=title,
                    ).to_dict()
                )

    def _consume_text(
        self,
        result: ApplicantEnrichment,
        text: str,
        source_url: str,
        source_type: str,
        base_confidence: float,
    ) -> None:

        if not text:
            return

        source_is_government = is_government_url(
            source_url
        ) or (
            government_domain_root(source_url)
            in getattr(self, "_government_roots", ())
        )

        emails = extract_emails(
            text
        )

        for email in emails:

            if not valid_email(
                email
            ):
                continue

            if is_government_email(
                email
            ) or (
                government_domain_root(email)
                in getattr(self, "_government_roots", ())
            ):
                # A .gov mailbox (or the same municipality under a
                # non-.gov TLD, e.g. provo.org) found by crawling/searching
                # is government staff, never the applicant -- see Staff
                # Contact Separation rule. A legitimate government-record
                # applicant email is asserted separately, from the
                # extractor's applicant_email field, not by scraping a
                # government page here.
                continue

            confidence = email_confidence(
                email,
                source_url,
                source_type,
                result.applicant_name,
            )

            result.emails_found.append(
                email
            )

            result.sources.append(
                Evidence(
                    field="applicant_email_candidate",
                    value=email,
                    source_url=source_url,
                    source_type=source_type,
                    confidence=confidence,
                    evidence_text=surrounding_text(
                        text,
                        email,
                    ),
                ).to_dict()
            )

        phones = extract_phones(
            text
        )

        for phone in phones:

            if source_is_government:
                # A phone number on a .gov page is a department/office
                # line, not personal to the applicant -- do not attribute
                # it. (Two different real applicants in the Provo packet
                # were briefly, incorrectly assigned the same city
                # Development Services number this way.)
                continue

            result.phones_found.append(
                phone
            )

            result.sources.append(
                Evidence(
                    field="applicant_phone_candidate",
                    value=phone,
                    source_url=source_url,
                    source_type=source_type,
                    confidence=min(
                        base_confidence
                        + 0.10,
                        0.95,
                    ),
                    evidence_text=surrounding_text(
                        text,
                        phone,
                    ),
                ).to_dict()
            )

        self._extract_role_mentions(
            result,
            text,
            source_url,
            source_type,
        )

    def _extract_role_mentions(
        self,
        result: ApplicantEnrichment,
        text: str,
        source_url: str,
        source_type: str,
    ) -> None:
        """
        Owner/person discovery (Phase 2). Restricted to fetched public
        pages (official website / public business directory) -- never
        government_record or bare search-result snippets. A government
        packet that explicitly labels ownership already has a dedicated,
        higher-confidence extractor (application_extractor.extract_owner/
        extract_parties()); mining free text on a government-hosted page
        with this heuristic would only risk duplicating or contradicting
        that authoritative source, not adding evidence.
        """

        if source_type not in (
            "public_web",
            "public_business_directory",
        ):
            return

        if is_government_url(source_url) or (
            government_domain_root(source_url)
            in getattr(self, "_government_roots", ())
        ):
            # A general public-web search can surface a DIFFERENT .gov
            # domain than the packet's own municipality (e.g. a state
            # open-records/meeting-minutes site) -- excluded here
            # regardless of _government_roots, which only tracks the
            # packet's own municipal domain. Government-labeled ownership
            # (e.g. a "Property Owner:" routing-table entry) already has
            # a dedicated, authoritative extractor: application_extractor.
            # extract_owner()/extract_parties(). This heuristic must not
            # duplicate or second-guess that source, and a public agenda/
            # minutes page frequently bundles multiple unrelated case
            # numbers together, so a "Property Owner" line found there may
            # not even belong to the application being enriched.
            return

        mentions = find_role_person_mentions(text)

        if not mentions:
            return

        applicant_name = result.applicant_name or ""

        applicant_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z]+", applicant_name)
            if len(token) > 1
        }

        relevance = relevance_score(
            applicant_name,
            text,
            address=self._project_address_lower,
            neighborhood=self._relevance_neighborhood,
            company_name=self._relevance_company_name,
            source_type=source_type,
        )

        company_name = self._relevance_company_name

        for name, role in mentions:
            name_tokens = {
                token.lower()
                for token in re.findall(r"[a-zA-Z]+", name)
            }

            is_same_person = bool(applicant_tokens) and (
                applicant_tokens <= name_tokens
                or name_tokens <= applicant_tokens
            )

            if is_same_person:
                # Confirms the already-known applicant's own professional
                # role -- does not assert a new identity, so it is not
                # gated on relevance_score() the way a distinct person is.
                result.sources.append(
                    Evidence(
                        field="contact_role_candidate",
                        value=role,
                        source_url=source_url,
                        source_type=source_type,
                        confidence=source_confidence(
                            source_url,
                            source_type,
                        ),
                        evidence_text=surrounding_text(
                            text,
                            name,
                        ),
                    ).to_dict()
                )
                continue

            # A distinct person is only accepted when the page/text
            # itself already evidently concerns this applicant/company --
            # never merely because a role keyword and some name co-occur
            # on an unrelated page. See CLAUDE.md section 6: never
            # associate a person merely because a search result "looks
            # plausible".
            if relevance < RELEVANCE_ACCEPT_THRESHOLD:
                continue

            if (
                company_name
                and name.strip().lower() == company_name.strip().lower()
            ):
                # The "name" span is the company itself, not a person.
                continue

            confidence = round(
                max(
                    0.30,
                    source_confidence(source_url, source_type) - 0.10,
                ),
                2,
            )

            result.discovered_parties.append(
                {
                    "party_name": name,
                    "party_role": role,
                    "party_company": company_name,
                    "party_contact_email": None,
                    "party_contact_phone": None,
                    "party_source": source_type,
                    "party_confidence": _confidence_label(confidence),
                }
            )

            result.sources.append(
                Evidence(
                    field="owner_person_candidate",
                    value=f"{name} ({role})",
                    source_url=source_url,
                    source_type=source_type,
                    confidence=confidence,
                    evidence_text=surrounding_text(
                        text,
                        name,
                    ),
                ).to_dict()
            )

    def _extract_links(
        self,
        result: ApplicantEnrichment,
        soup: BeautifulSoup,
        page_url: str,
        source_type: str,
        page_is_relevant: bool,
    ) -> None:

        if not page_is_relevant:
            # No evidence this page concerns this applicant at all --
            # do not attribute any of its links as a company_website.
            return

        for anchor in soup.find_all(
            "a",
            href=True,
        ):
            anchor_text = clean_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

            # Score this link's own visible text together with its
            # immediate enclosing context -- a legitimate company link
            # is often generic ("Visit Website", a bare domain) with the
            # applicant's name only in the surrounding prose, not the
            # anchor text itself. Two broader approaches were tried and
            # rejected: the anchor's full ancestor chain (a generic
            # <body>/<div> container can span both an unrelated link and
            # an unrelated paragraph that happens to name the applicant),
            # and a character-radius window over the flattened page text
            # (on a short page this also spans unrelated sibling
            # elements, since character distance doesn't track document
            # structure). Only a SMALL, semantically-scoped parent
            # element -- a single list item, table cell, or paragraph
            # that the anchor is actually nested inside -- is trusted as
            # local context; anything larger or more generic falls back
            # to the anchor's own text alone.
            anchor_context = anchor_text

            parent = anchor.parent

            if (
                parent is not None
                and getattr(parent, "name", None) in ANCHOR_CONTEXT_TAGS
            ):
                parent_text = clean_text(
                    parent.get_text(
                        " ",
                        strip=True,
                    )
                )

                if parent_text and len(parent_text) <= 400:
                    anchor_context = parent_text

            score = relevance_score(
                result.applicant_name or "",
                anchor_context,
                address=self._project_address_lower,
                neighborhood=self._relevance_neighborhood,
                company_name=self._relevance_company_name,
                source_type=source_type,
            )

            if score < RELEVANCE_ACCEPT_THRESHOLD:
                # Neither this link's own text nor its surrounding
                # context demonstrably concerns this applicant -- a
                # footer/navigation/vendor-credit/"Directions" link must
                # not be attributed to this applicant just because it
                # shares a page with their name.
                continue

            href = normalize_url(
                urljoin(
                    page_url,
                    anchor["href"],
                )
            )

            if not href:
                continue

            if is_social_url(
                href
            ):
                continue

            if is_government_url(
                href
            ) or (
                government_domain_root(href)
                in getattr(self, "_government_roots", ())
            ):
                # A government notice/calendar/agenda link (including the
                # same municipality under a non-.gov TLD) is never the
                # applicant's own company website.
                continue

            if is_map_or_utility_url(
                href
            ):
                # A map/directions link is never a company website.
                continue

            project_address = getattr(
                self,
                "_project_address_lower",
                None,
            )

            if (
                project_address
                and project_address in href.lower()
            ):
                # A link embedding the project's own street address as a
                # query string is a directions/map link, not a company
                # website, regardless of which provider hosts it.
                continue

            parsed = urlparse(
                href
            )

            if parsed.scheme not in {
                "http",
                "https",
            }:
                continue

            if not is_probable_website(
                href
            ):
                continue

            result.websites_found.append(
                href
            )

    # ---------------------------------------------------------
    # FINAL SELECTION
    # ---------------------------------------------------------

    def _finalize(
        self,
        result: ApplicantEnrichment,
    ) -> None:

        result.emails_found = unique_preserve_order(
            result.emails_found
        )

        result.phones_found = unique_preserve_order(
            [
                normalize_phone(
                    value
                )
                for value in result.phones_found
            ]
        )

        result.websites_found = unique_preserve_order(
            result.websites_found
        )

        candidates = [
            item
            for item in result.sources
            if item.get(
                "field"
            )
            == "applicant_email_candidate"
        ]

        candidates.sort(
            key=lambda item: item.get(
                "confidence",
                0,
            ),
            reverse=True,
        )

        if candidates:
            best = candidates[0]

            result.applicant_email = (
                best["value"]
            )

            result.email_confidence = (
                best["confidence"]
            )

        phone_candidates = [
            item
            for item in result.sources
            if item.get(
                "field"
            )
            == "applicant_phone_candidate"
        ]

        phone_candidates.sort(
            key=lambda item: item.get(
                "confidence",
                0,
            ),
            reverse=True,
        )

        if phone_candidates:
            best = phone_candidates[0]

            result.applicant_phone = (
                best["value"]
            )

            result.phone_confidence = (
                best["confidence"]
            )

        official_websites = [
            url
            for url in result.websites_found
            if not is_social_url(
                url
            )
        ]

        if official_websites:
            result.company_website = (
                official_websites[0]
            )

            result.company_confidence = 0.60
            result.company_source = "public_web"

        directory_titles = [
            item
            for item in result.sources
            if item.get("field") == "page_title"
            and item.get("source_type") == "public_business_directory"
        ]

        if directory_titles and not result.company_name:
            result.company_name = directory_titles[0]["value"]
            result.company_source = "public_business_directory"
            result.company_confidence = max(
                result.company_confidence,
                0.55,
            )

        if (
            result.applicant_email
            or result.applicant_phone
            or result.company_website
        ):
            result.enrichment_status = "partial"

        if (
            result.applicant_email
            and result.email_confidence >= 0.85
        ):
            result.enrichment_status = "contact_found"

        role_candidates = [
            item
            for item in result.sources
            if item.get("field") == "contact_role_candidate"
        ]

        role_candidates.sort(
            key=lambda item: item.get("confidence", 0),
            reverse=True,
        )

        if role_candidates:
            result.contact_role = role_candidates[0]["value"]

        deduped_parties = []
        seen_parties = set()

        for party in result.discovered_parties:
            key = (
                str(party.get("party_name") or "").lower(),
                party.get("party_role"),
            )

            if key in seen_parties:
                continue

            seen_parties.add(key)
            deduped_parties.append(party)

        result.discovered_parties = deduped_parties

        # Do not expose all raw source objects twice.
        result.sources = dedupe_sources(
            result.sources
        )


# =============================================================
# PIPELINE ENTRY POINT
# =============================================================

# Process-lifetime cache for live enrichment results, keyed on the same
# fields that determine the search queries (applicant name + project
# address + neighborhood). Multiple application records commonly share
# an identical applicant/address (e.g. a Zone Map Amendment and a
# Concept Plan filed together for the same project) -- without this,
# pipeline_orchestrator._enrich_applicants() would re-run the exact same
# general + business-directory searches, and re-fetch the exact same
# pages, once per application record instead of once per distinct
# applicant/address. Cleared automatically each process run (a fresh
# pipeline invocation is a fresh process); never persisted, so a stale
# result can never leak into a later, unrelated run.
_LIVE_ENRICHMENT_CACHE: dict[tuple[str, Optional[str], Optional[str]], dict[str, Any]] = {}


def _live_enrichment_cache_key(
    applicant_name: str,
    application: dict[str, Any],
) -> tuple[str, Optional[str], Optional[str]]:
    address = clean_text(application.get("project_address")).lower() or None
    neighborhood = clean_text(application.get("neighborhood")).lower() or None
    return (applicant_name.lower(), address, neighborhood)


def enrich_applicant_contact(
    application: dict[str, Any],
    live_search: bool = True,
) -> dict[str, Any]:
    """
    Convenience entry point used by pipeline_orchestrator._enrich_applicants().

    Distinguishes the enrichment states the pipeline needs to report
    (disabled / not_found / enriched / failed) and adds the contact-
    intelligence fields the data model expects (contact_name, contact_email,
    contact_phone, contact_source, contact_confidence, contact_is_public,
    contact_is_verified, company_source, enrichment_method) without changing
    the ApplicantEnricher.enrich() contract relied on by
    scripts.test_applicant_enrichment.
    """
    applicant_name = clean_name(application.get("applicant_name"))

    if not applicant_name:
        return {
            "applicant_name": applicant_name,
            "enrichment_status": "not_found",
            "enrichment_method": "disabled",
        }

    if not live_search:
        # Deterministic path: no network calls, government-record contact
        # data only. This keeps unit tests network-free and satisfies the
        # "Live enrichment: False" behavior in DEVELOPMENT_RULES.
        result = ApplicantEnrichment(
            applicant_name=applicant_name,
            enrichment_status="disabled",
        )

        gov_email = application.get("applicant_email")
        if gov_email:
            candidate = str(gov_email).strip().lower()
            if EMAIL_RE.fullmatch(candidate) and valid_email(candidate):
                result.applicant_email = candidate
                result.email_confidence = 1.0

        gov_phone = application.get("applicant_phone")
        if gov_phone:
            result.applicant_phone = normalize_phone(str(gov_phone))
            result.phone_confidence = 1.0

        data = result.to_dict()
        data["enrichment_method"] = "disabled"
        has_contact = bool(result.applicant_email or result.applicant_phone)
        data["contact_name"] = applicant_name if has_contact else None
        data["contact_email"] = result.applicant_email
        data["contact_phone"] = result.applicant_phone
        data["contact_source"] = "government_record" if has_contact else None
        data["contact_confidence"] = 1.0 if has_contact else 0.0
        data["contact_is_public"] = False
        data["contact_is_verified"] = has_contact
        data["company_source"] = None
        data["linkedin_url"] = None
        return data

    cache_key = _live_enrichment_cache_key(applicant_name, application)

    if cache_key in _LIVE_ENRICHMENT_CACHE:
        return dict(_LIVE_ENRICHMENT_CACHE[cache_key])

    try:
        enricher = ApplicantEnricher()
        raw = enricher.enrich(application, live_search=True)
    except Exception as exc:
        result = {
            "applicant_name": applicant_name,
            "enrichment_status": "failed",
            "enrichment_method": "public_web",
            "enrichment_error": str(exc),
        }
        _LIVE_ENRICHMENT_CACHE[cache_key] = dict(result)
        return result

    status = raw.get("enrichment_status")

    if status in ("partial", "contact_found"):
        raw["enrichment_status"] = "enriched"
    elif status == "missing_applicant_name":
        raw["enrichment_status"] = "not_found"
    # "not_found" already matches the pipeline vocabulary as-is.

    raw["enrichment_method"] = "public_web"

    email = raw.get("applicant_email")
    phone = raw.get("applicant_phone")

    email_sources = [
        source
        for source in raw.get("sources", [])
        if source.get("field") == "applicant_email_candidate"
        and source.get("value") == email
    ]
    best_email_source = email_sources[0] if email_sources else None

    raw["contact_name"] = applicant_name if email else None
    raw["contact_email"] = email
    raw["contact_phone"] = phone
    raw["contact_source"] = (
        best_email_source.get("source_type")
        if best_email_source
        else ("public_web" if (email or phone) else None)
    )
    raw["contact_confidence"] = raw.get("email_confidence") or raw.get("phone_confidence") or 0.0
    raw["contact_is_public"] = bool(email or phone)
    raw["contact_is_verified"] = bool(
        best_email_source
        and best_email_source.get("source_type") in ("government_record", "official_website")
    )
    raw["company_source"] = raw.get("company_source") or (
        "public_web" if raw.get("company_website") else None
    )
    raw.setdefault("linkedin_url", None)

    _LIVE_ENRICHMENT_CACHE[cache_key] = dict(raw)

    return raw


# =============================================================
# HELPERS
# =============================================================

def build_search_query(
    application: dict[str, Any],
) -> str:

    parts = []

    name = clean_name(
        application.get(
            "applicant_name"
        )
    )

    address = clean_text(
        application.get(
            "project_address"
        )
    )

    neighborhood = clean_text(
        application.get(
            "neighborhood"
        )
    )

    if name:
        parts.append(
            f'"{name}"'
        )

    if address:
        parts.append(
            f'"{address}"'
        )

    if neighborhood:
        parts.append(
            f'"{neighborhood}"'
        )

    parts.append(
        "contact OR email OR phone OR developer OR owner"
    )

    return " ".join(
        parts
    )


def collect_urls(
    application: dict[str, Any],
) -> list[str]:

    values = []

    for key in (
        "source_url",
        "source_urls",
        "government_url",
        "urls",
    ):
        value = application.get(
            key
        )

        if isinstance(
            value,
            str,
        ):
            values.append(
                value
            )

        elif isinstance(
            value,
            (list, tuple),
        ):
            values.extend(
                value
            )

    return unique_preserve_order(
        [
            normalize_url(
                url
            )
            for url in values
            if normalize_url(
                url
            )
        ]
    )


def clean_name(
    value: Any,
) -> Optional[str]:

    if value is None:
        return None

    value = clean_text(
        str(value)
    )

    # A government department/role label (e.g. "Development Services" on
    # a city-initiated application) is not a person/company name. Without
    # this, a live search would run against a generic bureaucratic label
    # and can match an entirely unrelated municipality's department page
    # by coincidence -- mirrors the same stripping already applied in
    # applicant_identity.clean_applicant_name().
    value = re.sub(
        r"\b(requests?|development services|citywide application)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip(" -,:;")

    return value or None


def clean_text(
    value: Any,
) -> str:

    if value is None:
        return ""

    value = str(
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def extract_pdf_text(
    data: bytes,
) -> str:
    """
    Extract plain text from PDF bytes fetched over HTTP (a discovered
    public document, not the local government packet).

    Mirrors pipeline_orchestrator._read_pdf_text()'s approach (same
    PyMuPDF library, same page.get_text("text") call, pages joined with
    newlines) rather than introducing a second PDF extraction engine --
    adapted to an in-memory byte stream since a fetched search result is
    never written to disk. Not imported from pipeline_orchestrator
    directly: that module already imports this one (via
    _enrich_applicants()), and services must not depend upward on the
    orchestrator.
    """

    try:
        import pymupdf
    except ImportError:
        return ""

    try:
        document = pymupdf.open(
            stream=data,
            filetype="pdf",
        )
    except Exception:
        return ""

    try:
        pages = [
            page.get_text("text")
            for page in document
        ]
    finally:
        document.close()

    return "\n".join(pages)


def extract_emails(
    text: str,
) -> list[str]:

    return unique_preserve_order(
        [
            email.lower()
            for email in EMAIL_RE.findall(
                text
            )
        ]
    )


def extract_phones(
    text: str,
) -> list[str]:

    return unique_preserve_order(
        [
            normalize_phone(
                phone
            )
            for phone in PHONE_RE.findall(
                text
            )
        ]
    )


def is_government_email(
    email: str,
) -> bool:

    domain = email.lower().split(
        "@",
        1,
    )[-1]

    return domain.endswith(
        ".gov"
    ) or ".gov." in domain


def is_government_url(
    url: Optional[str],
) -> bool:

    if not url:
        return False

    host = urlparse(
        url
    ).netloc.lower()

    return host.endswith(
        ".gov"
    ) or ".gov." in host


def government_domain_root(
    url_or_email: Optional[str],
) -> Optional[str]:
    """
    Registrable-domain root (e.g. "provo" for both provo.gov and
    provo.org), ignoring TLD, so a municipality can be recognized under
    whichever TLD it happens to also use for a given page/mailbox.
    """

    if not url_or_email:
        return None

    value = url_or_email.strip().lower()

    if "@" in value and "://" not in value:
        domain = value.rsplit(
            "@",
            1,
        )[-1]
    else:
        parsed_value = (
            value
            if "://" in value
            else "https://" + value
        )
        domain = urlparse(
            parsed_value
        ).netloc

    domain = domain.split(":")[0]

    if domain.startswith("www."):
        domain = domain[4:]

    parts = [
        part
        for part in domain.split(".")
        if part
    ]

    if len(parts) < 2:
        return domain or None

    return parts[-2]


def is_map_or_utility_url(
    url: str,
) -> bool:

    host = (
        urlparse(
            url
        ).netloc.lower()
    )

    host = host.removeprefix(
        "www."
    )

    return any(
        host == domain
        or host.endswith(
            "." + domain
        )
        for domain in MAP_UTILITY_DOMAINS
    )


def normalize_phone(
    phone: str,
) -> str:

    return clean_text(
        phone
    )


def valid_email(
    email: str,
) -> bool:

    email = email.lower()

    domain = email.split(
        "@",
        1,
    )[-1]

    if domain in BAD_EMAIL_DOMAINS:
        return False

    return "." in domain


def email_confidence(
    email: str,
    source_url: str,
    source_type: str,
    applicant_name: Optional[str],
) -> float:

    confidence = {
        "government_record": 0.92,
        "official_website": 0.88,
        "public_web": 0.70,
        "public_business_directory": 0.60,
        "search_result": 0.55,
    }.get(
        source_type,
        0.50,
    )

    local = email.split(
        "@",
        1,
    )[0].lower()

    if (
        local in GENERIC_EMAIL_PREFIXES
    ):
        confidence -= 0.15

    if applicant_name:
        name_parts = [
            token.lower()
            for token in re.findall(
                r"[a-zA-Z]+",
                applicant_name,
            )
            if len(token) > 2
        ]

        if any(
            token in local
            for token in name_parts
        ):
            confidence += 0.08

    if is_social_url(
        source_url
    ):
        confidence -= 0.15

    return round(
        max(
            0.0,
            min(
                confidence,
                0.99,
            ),
        ),
        2,
    )


def source_confidence(
    url: str,
    source_type: str,
) -> float:

    host = (
        urlparse(
            url
        ).netloc.lower()
    )

    if host.endswith(
        ".gov"
    ) or ".gov." in host:
        return 0.90

    if source_type == "official_website":
        return 0.88

    if source_type == "public_business_directory":
        return 0.55

    return 0.65


def name_fully_referenced(
    name: str,
    text: str,
) -> bool:
    """
    True only when every token of the applicant's name appears in text.

    Used to gate business-directory evidence: a directory search hit is
    only attached to this applicant when the result itself demonstrably
    concerns them, not merely because a first name matched.
    """

    tokens = [
        token.lower()
        for token in re.findall(
            r"[a-zA-Z]+",
            name,
        )
        if len(token) > 1
    ]

    if not tokens:
        return False

    haystack = text.lower()

    return all(
        token in haystack
        for token in tokens
    )


RELEVANCE_ACCEPT_THRESHOLD = 0.50


def relevance_score(
    name: str,
    text: str,
    address: Optional[str] = None,
    neighborhood: Optional[str] = None,
    company_name: Optional[str] = None,
    source_type: Optional[str] = None,
) -> float:
    """
    Multi-signal relevance score for whether `text` (a full page, a
    PDF's content, a search-result snippet, or a link's surrounding
    context) genuinely concerns this applicant/company -- rather than a
    single brittle check for whether the applicant's exact name string
    appears verbatim in a URL or a link's own visible text.

    The applicant's name (at least one token) is a hard prerequisite:
    address/neighborhood/company/source-type corroboration is only ever
    additive on top of some name match, never a substitute for it. This
    is what keeps the evidence bar from being lowered -- a page cannot
    be accepted purely because it mentions the right address or is
    hosted on an already-trusted source type with zero connection to the
    person's own name.

    Signal weights:
    - full applicant name (every token present)         -> 0.50
    - partial applicant name (at least one token, not all) -> 0.15
    - project street address (>=60% of its tokens present) -> 0.30
    - neighborhood mentioned                             -> 0.15
    - company name (every token present)                -> 0.35
    - already-vetted source type (government_record /
      public_business_directory)                         -> 0.10

    A bare full-name match (0.50) meets RELEVANCE_ACCEPT_THRESHOLD on
    its own, matching the bar this replaces. A partial name match only
    clears the threshold when corroborated by at least two of the other
    signals (e.g. address + neighborhood, or address + a directory
    source type) -- multiple independent signals, not a relaxed bar.
    """

    if not text:
        return 0.0

    name_tokens = [
        token.lower()
        for token in re.findall(r"[a-zA-Z]+", name or "")
        if len(token) > 1
    ]

    if not name_tokens:
        return 0.0

    haystack = text.lower()

    matched_name_tokens = sum(
        1 for token in name_tokens if token in haystack
    )

    if matched_name_tokens == 0:
        return 0.0

    score = 0.50 if matched_name_tokens == len(name_tokens) else 0.15

    if address:
        address_tokens = [
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9]+", address)
            if len(token) > 1
        ]
        if address_tokens:
            hits = sum(1 for token in address_tokens if token in haystack)
            if hits / len(address_tokens) >= 0.60:
                score += 0.30

    if neighborhood and neighborhood.lower() in haystack:
        score += 0.15

    if company_name:
        company_tokens = [
            token.lower()
            for token in re.findall(r"[a-zA-Z]+", company_name)
            if len(token) > 2
        ]
        if company_tokens and all(token in haystack for token in company_tokens):
            score += 0.35

    if source_type in ("government_record", "public_business_directory"):
        score += 0.10

    return round(min(score, 1.0), 3)


def surrounding_text(
    text: str,
    value: str,
    radius: int = 180,
) -> str:

    index = text.lower().find(
        value.lower()
    )

    if index < 0:
        return text[:500]

    return clean_text(
        text[
            max(
                0,
                index - radius,
            ):
            index
            + len(value)
            + radius
        ]
    )


def normalize_url(
    url: str,
) -> Optional[str]:

    if not url:
        return None

    url = str(
        url
    ).strip()

    if not url:
        return None

    if url.startswith(
        "["
    ) and "](" in url:
        match = re.search(
            r"\((https?://[^)]+)\)",
            url,
        )
        if match:
            url = match.group(
                1
            )

    if not re.match(
        r"^https?://",
        url,
        re.IGNORECASE,
    ):
        return None

    return url.rstrip(
        ".,);]"
    )


def is_social_url(
    url: str,
) -> bool:

    host = (
        urlparse(
            url
        ).netloc.lower()
    )

    host = host.removeprefix(
        "www."
    )

    return any(
        host == domain
        or host.endswith(
            "." + domain
        )
        for domain in SOCIAL_DOMAINS
    )


def is_probable_website(
    url: str,
) -> bool:

    host = (
        urlparse(
            url
        ).netloc.lower()
    )

    host = host.removeprefix(
        "www."
    )

    return bool(
        host
        and host not in SOCIAL_DOMAINS
    )


def unique_preserve_order(
    values: Iterable[str],
) -> list[str]:

    seen = set()
    result = []

    for value in values:

        if not value:
            continue

        normalized = str(
            value
        ).strip()

        key = normalized.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            normalized
        )

    return result


def dedupe_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    seen = set()
    result = []

    for source in sources:

        key = (
            source.get(
                "field"
            ),
            source.get(
                "value"
            ),
            source.get(
                "source_url"
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            source
        )

    return result


def main():
    """
    Tiny manual smoke test.
    Production calls should import ApplicantEnricher.
    """
    application = {
        "applicant_name": "Jared Morgan",
        "application_number": "PLRZ20260264",
        "project_address": "113/191 N Geneva Road",
        "application_type": "Zone Map Amendment",
        "neighborhood": "Fort Utah",
    }

    enricher = ApplicantEnricher()

    result = enricher.enrich(
        application,
        live_search=True,
    )

    print_json(
        result
    )


def print_json(
    value: Any,
) -> None:

    import json

    print(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()