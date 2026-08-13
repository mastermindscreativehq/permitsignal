"""
PermitSignal Applicant Enrichment Test

Run:

    python -m scripts.test_applicant_enrichment

For live SerpAPI enrichment:

    $env:SERPAPI_API_KEY="YOUR_KEY"
    python -m scripts.test_applicant_enrichment --live

Without --live, the test validates the enrichment engine and
does NOT call a search provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Make project-root imports reliable when the script is executed
# through Python's -m mechanism.
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from backend.app.services.applicant_enrichment import (
    ApplicantEnricher,
    build_search_query,
    extract_emails,
    extract_pdf_text,
    extract_phones,
    valid_email,
)


def make_test_pdf(text: str) -> bytes:
    """
    Build a minimal real PDF in-memory for deterministic, network-free
    tests. Uses insert_textbox (auto-wrapping) rather than insert_text,
    which silently clips any line wider than the page.
    """

    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    rect = pymupdf.Rect(72, 72, 540, 720)
    page.insert_textbox(rect, text, fontsize=11)
    data = document.tobytes()
    document.close()

    return data


TEST_APPLICATIONS = [
    {
        "applicant_name": "Tyson Reynolds",
        "application_number": "PLRZ20260116",
        "application_type": "Zone Map Amendment",
        "project_address": "2000 N Canyon Road",
        "neighborhood": "Pleasant View",
        "source_url": (
            "https://www.provo.gov/"
            "AgendaCenter/ViewFile/Agenda/_08122026-415"
        ),
    },
    {
        "applicant_name": "Jared Morgan",
        "application_number": "PLRZ20260264",
        "application_type": "Zone Map Amendment",
        "project_address": "113/191 N Geneva Road",
        "neighborhood": "Fort Utah",
        "source_url": (
            "https://www.provo.gov/"
            "AgendaCenter/ViewFile/Agenda/_08122026-415"
        ),
    },
]


def check(
    condition: bool,
    label: str,
) -> bool:

    if condition:
        print(
            f"[PASS] {label}"
        )
        return True

    print(
        f"[FAIL] {label}"
    )
    return False


def unit_tests() -> int:

    print("=" * 80)
    print(
        "PERMITSIGNAL APPLICANT ENRICHMENT"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    print()
    print("[1/5] Email extraction")

    emails = extract_emails(
        """
        Contact john.doe@example.com or
        jared@example.org for information.
        """
    )

    if check(
        "john.doe@example.com" in emails,
        "Extracts email addresses",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("[2/5] Phone extraction")

    phones = extract_phones(
        """
        Call (801) 852-6408 or
        801-555-1234.
        """
    )

    if check(
        len(phones) >= 2,
        "Extracts phone numbers",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("[3/5] Email validation")

    if check(
    valid_email(
        "person@provo.gov"
    ),
    "Accepts valid email format",
):
        passed += 1
    else:
        failed += 1

    if check(
        not valid_email(
            "fake@example.com"
        ),
        "Rejects placeholder domain",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("[4/5] Search query construction")

    query = build_search_query(
        TEST_APPLICATIONS[1]
    )

    if check(
        "Jared Morgan" in query
        and "113/191 N Geneva Road" in query,
        "Search query contains applicant and address",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("[5/5] Enrichment without live search")

    enricher = ApplicantEnricher()

    result = enricher.enrich(
        TEST_APPLICATIONS[0],
        live_search=False,
    )

    if check(
        result["applicant_name"]
        == "Tyson Reynolds",
        "Preserves applicant name",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result["enrichment_status"]
        in {
            "not_found",
            "partial",
            "contact_found",
        },
        "Returns a valid enrichment status",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"UNIT TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def mocked_directory_test() -> int:
    """
    Deterministic, network-free test of the business-directory discovery
    path added to ApplicantEnricher. Mocks only ApplicantEnricher._search
    and ._fetch_urls (never real HTTP) with captured/structured response
    shapes, per the no-fabrication testing rule: no fake applicant data
    is inserted into any application/opportunity/production record here,
    only into an isolated ApplicantEnricher.enrich() call for a synthetic
    test applicant that never reaches the pipeline or JSON output.
    """

    print()
    print("=" * 80)
    print(
        "[6/10] Business directory discovery (mocked, no network)"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    application = {
        "applicant_name": "Alexandra Whitfield",
        "application_number": "TEST0001",
        "application_type": "Concept Plan",
        "project_address": "500 Test Ave",
        "neighborhood": "Test Heights",
    }

    enricher = ApplicantEnricher()
    enricher.serpapi_key = "test-key"

    def fake_search(query):
        if "site:" not in query:
            return []

        return [
            {
                "title": "Alexandra Whitfield Construction - BBB Business Profile",
                "link": (
                    "https://www.bbb.org/us/ut/provo/profile/contractor/"
                    "alexandra-whitfield-construction-0001"
                ),
                "snippet": "Alexandra Whitfield Construction is a BBB accredited business.",
            },
            {
                "title": "Unrelated Business - BBB Profile",
                "link": "https://www.bbb.org/us/ut/provo/profile/unrelated-9999",
                "snippet": "An unrelated business with no connection to this applicant.",
            },
        ]

    def fake_fetch_urls(urls):
        pages = []

        for url in urls:
            if "alexandra-whitfield-construction" in url:
                pages.append(
                    {
                        "url": url,
                        "html": (
                            "<html><head>"
                            "<title>Alexandra Whitfield Construction</title>"
                            "</head><body><p>Contact Alexandra Whitfield "
                            "Construction at "
                            "info@alexandrawhitfieldconstruction.com or "
                            "(801) 555-0142.</p></body></html>"
                        ),
                    }
                )

        return pages

    enricher._search = fake_search
    enricher._fetch_urls = fake_fetch_urls

    result = enricher.enrich(
        application,
        live_search=True,
    )

    if check(
        result.get("company_name") == "Alexandra Whitfield Construction",
        "Attaches company_name from a name-matched directory listing",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        (result.get("company_confidence") or 0) > 0,
        "Assigns a non-zero company_confidence for the directory hit",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result.get("applicant_email") == "info@alexandrawhitfieldconstruction.com",
        "Extracts the mailbox found on the matched directory page",
    ):
        passed += 1
    else:
        failed += 1

    directory_sources = [
        source
        for source in result.get("sources", [])
        if source.get("source_type") == "public_business_directory"
    ]

    if check(
        len(directory_sources) > 0,
        "Records public_business_directory evidence with source URLs",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        not any(
            "unrelated-9999" in str(source.get("value", ""))
            or "unrelated-9999" in str(source.get("source_url", ""))
            for source in result.get("sources", [])
        ),
        "Rejects a directory hit whose title/snippet does not reference the applicant",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"[6/10] TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def mocked_government_exclusion_test() -> int:
    """
    Deterministic, network-free test that a government page discovered
    through general search can never contaminate applicant contact data
    (Staff Contact Separation), including a non-.gov municipal alias
    domain, a map/directions link, and a CMS-vendor credit link. Mocks
    ApplicantEnricher._search/._fetch_urls only; no fabricated data
    reaches the pipeline or production output.
    """

    print()
    print("=" * 80)
    print(
        "[7/10] Government/map source exclusion (mocked, no network)"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    application = {
        "applicant_name": "Marcus Ford",
        "application_number": "TEST0002",
        "application_type": "Variance",
        "project_address": "900 Sample Blvd",
        "neighborhood": "Sample Hills",
        "source_url": (
            "https://www.provo.gov/"
            "AgendaCenter/ViewFile/Agenda/_test2"
        ),
    }

    enricher = ApplicantEnricher()
    enricher.serpapi_key = "test-key"

    def fake_search(query):
        if "site:" in query:
            return []

        return [
            {
                "title": "Marcus Ford - Planning Commission Agenda",
                "link": (
                    "https://www.provo.gov/"
                    "AgendaCenter/ViewFile/Agenda/_test2"
                ),
                "snippet": "Marcus Ford requests a variance.",
            }
        ]

    def fake_fetch_urls(urls):
        pages = []

        for url in urls:
            if "provo.gov" in url:
                pages.append(
                    {
                        "url": url,
                        "html": (
                            "<html><body>"
                            "<p>Marcus Ford requests a variance at "
                            "900 Sample Blvd. Staff contact: "
                            "dspublichearings@provo.org, "
                            "(801) 852-6120.</p>"
                            '<a href="http://maps.google.com/maps?'
                            'q=900+Sample+Blvd">Directions</a>'
                            '<a href="https://connect.civicplus.com/'
                            'referral">Powered by CivicPlus</a>'
                            "</body></html>"
                        ),
                    }
                )

        return pages

    enricher._search = fake_search
    enricher._fetch_urls = fake_fetch_urls

    result = enricher.enrich(
        application,
        live_search=True,
    )

    if check(
        result.get("applicant_email") is None,
        "Never attributes a .gov-alias (.org) staff mailbox to the applicant",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result.get("applicant_phone") is None,
        "Never attributes a phone number found on a government page to the applicant",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result.get("company_website") is None,
        "Never attributes a map/directions link or CMS-vendor credit link as the company website",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"[7/10] TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def mocked_pdf_test() -> int:
    """
    Deterministic, network-free test of PDF/document intelligence.
    Real PDF bytes are built with pymupdf so extract_pdf_text() runs for
    real; only ApplicantEnricher._search/._fetch_urls are mocked, so no
    HTTP call is made. No fabricated data reaches any application/
    opportunity/production record -- these are isolated enrich() calls
    against synthetic test applicants.
    """

    print()
    print("=" * 80)
    print(
        "[8/10] PDF/document intelligence (mocked search, real PDF parsing)"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    # Case A: a relevant PDF names the applicant and carries a real,
    # non-government contact -- should be accepted.
    application_a = {
        "applicant_name": "Priya Sundaram",
        "application_number": "TEST0003",
        "application_type": "Concept Plan",
        "project_address": "12 Test Court",
        "neighborhood": "Test Meadows",
    }

    relevant_pdf_text = extract_pdf_text(
        make_test_pdf(
            "Site Plan submitted by Priya Sundaram. Contact Priya "
            "Sundaram Development at priya@sundaramdevelopment.com "
            "or (801) 555-0199."
        )
    )

    enricher_a = ApplicantEnricher()
    enricher_a.serpapi_key = "test-key"

    def fake_search_a(query):
        if "site:" in query:
            return []
        return [
            {
                "title": "Site Plan - Priya Sundaram",
                "link": "https://example-county-docs.test/siteplan.pdf",
                "snippet": "Site plan submitted by Priya Sundaram.",
            }
        ]

    def fake_fetch_urls_a(urls):
        return [
            {
                "url": "https://example-county-docs.test/siteplan.pdf",
                "text": relevant_pdf_text,
                "is_pdf": True,
            }
            for _ in urls
        ]

    enricher_a._search = fake_search_a
    enricher_a._fetch_urls = fake_fetch_urls_a

    result_a = enricher_a.enrich(
        application_a,
        live_search=True,
    )

    if check(
        result_a.get("applicant_email") == "priya@sundaramdevelopment.com",
        "Extracts a real contact email from a PDF that names the applicant",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result_a.get("applicant_phone") == "(801) 555-0199",
        "Extracts a real contact phone from a PDF that names the applicant",
    ):
        passed += 1
    else:
        failed += 1

    # Case B: a PDF is fetched but its own text never names this
    # applicant -- must not attribute an email found elsewhere in that
    # unrelated document just because it happened to be returned by a
    # search for this applicant's name.
    application_b = {
        "applicant_name": "Priya Sundaram",
        "application_number": "TEST0004",
        "application_type": "Concept Plan",
        "project_address": "12 Test Court",
        "neighborhood": "Test Meadows",
    }

    unrelated_pdf_text = extract_pdf_text(
        make_test_pdf(
            "Site Plan submitted by a different owner, Jamal Whitfield. "
            "Contact Jamal Whitfield at jamal@whitfieldholdings.com."
        )
    )

    enricher_b = ApplicantEnricher()
    enricher_b.serpapi_key = "test-key"

    def fake_search_b(query):
        if "site:" in query:
            return []
        return [
            {
                "title": "Site Plan (unrelated)",
                "link": "https://example-county-docs.test/other-siteplan.pdf",
                "snippet": "An unrelated site plan.",
            }
        ]

    def fake_fetch_urls_b(urls):
        return [
            {
                "url": "https://example-county-docs.test/other-siteplan.pdf",
                "text": unrelated_pdf_text,
                "is_pdf": True,
            }
            for _ in urls
        ]

    enricher_b._search = fake_search_b
    enricher_b._fetch_urls = fake_fetch_urls_b

    result_b = enricher_b.enrich(
        application_b,
        live_search=True,
    )

    if check(
        result_b.get("applicant_email") is None,
        "Never attributes an email from a PDF that does not name the applicant",
    ):
        passed += 1
    else:
        failed += 1

    # Case C: a PDF names the applicant, but the only contact info inside
    # it is a government staff mailbox on the packet's own domain --
    # Staff Contact Separation must hold for PDF-sourced evidence too.
    application_c = {
        "applicant_name": "Priya Sundaram",
        "application_number": "TEST0005",
        "application_type": "Concept Plan",
        "project_address": "12 Test Court",
        "neighborhood": "Test Meadows",
        "source_url": (
            "https://www.exampletown.gov/"
            "AgendaCenter/ViewFile/Agenda/_test3"
        ),
    }

    government_pdf_text = extract_pdf_text(
        make_test_pdf(
            "Priya Sundaram requests Concept Plan approval. Staff "
            "contact: Jordan Lee, jlee@exampletown.gov, (555) 555-0100."
        )
    )

    enricher_c = ApplicantEnricher()
    enricher_c.serpapi_key = "test-key"

    def fake_search_c(query):
        return []

    def fake_fetch_urls_c(urls):
        return [
            {
                "url": (
                    "https://www.exampletown.gov/"
                    "AgendaCenter/ViewFile/Agenda/_test3"
                ),
                "text": government_pdf_text,
                "is_pdf": True,
            }
            for _ in urls
        ]

    enricher_c._search = fake_search_c
    enricher_c._fetch_urls = fake_fetch_urls_c

    result_c = enricher_c.enrich(
        application_c,
        live_search=True,
    )

    if check(
        result_c.get("applicant_email") is None,
        "Never attributes a government-staff email found inside a PDF to the applicant",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result_c.get("applicant_phone") is None,
        "Never attributes a phone number found inside a government-hosted PDF to the applicant",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"[8/10] TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def mocked_dedup_test() -> int:
    """
    Deterministic, network-free test that enrich_applicant_contact()
    reuses a cached live-enrichment result for a second application
    record sharing the same applicant name/address/neighborhood, instead
    of re-running the same searches. Verified by counting
    ApplicantEnricher instantiations (a fresh instance is only ever
    constructed on a cache miss), not by asserting on live network
    behavior.
    """

    print()
    print("=" * 80)
    print(
        "[9/10] Enrichment-query deduplication (mocked, no network)"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    import backend.app.services.applicant_enrichment as enrichment_module

    instantiations = []
    original_cls = enrichment_module.ApplicantEnricher

    class CountingEnricher(original_cls):
        def __init__(self, *args, **kwargs):
            instantiations.append(1)
            super().__init__(*args, **kwargs)
            self.serpapi_key = "test-key"
            self._search = lambda query: []
            self._fetch_urls = lambda urls: []

    enrichment_module.ApplicantEnricher = CountingEnricher
    # A clean slate regardless of what ran before this test in the same
    # process.
    enrichment_module._LIVE_ENRICHMENT_CACHE.clear()

    try:
        application_1 = {
            "applicant_name": "Dana Fields",
            "application_number": "TEST0006",
            "project_address": "77 Repeat Lane",
            "neighborhood": "Duplicate Heights",
        }
        application_2 = dict(
            application_1,
            application_number="TEST0007",
        )
        application_3 = {
            "applicant_name": "Dana Fields",
            "application_number": "TEST0008",
            "project_address": "99 Different Ave",
            "neighborhood": "Other Neighborhood",
        }

        result_1 = enrichment_module.enrich_applicant_contact(
            application_1,
            live_search=True,
        )
        result_2 = enrichment_module.enrich_applicant_contact(
            application_2,
            live_search=True,
        )
        result_3 = enrichment_module.enrich_applicant_contact(
            application_3,
            live_search=True,
        )
    finally:
        enrichment_module.ApplicantEnricher = original_cls

    if check(
        len(instantiations) == 2,
        (
            "Runs a live search only once for two applications sharing "
            "applicant/address (and once more for a distinct address) "
            "-- 2 live searches total, not 3"
        ),
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result_1 == result_2,
        "Returns an identical result for the two applications sharing applicant/address",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        result_3["applicant_name"] == "Dana Fields",
        "Still runs a fresh search for a distinct applicant/address",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"[9/10] TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def mocked_relevance_scoring_test() -> int:
    """
    Deterministic, network-free test of relevance_score()-based
    evidence matching. Proves the new capability actually accepts a
    legitimate source that the old anchor-text-only check would have
    rejected (a generic "Visit Website" link whose own text has no name
    reference, corroborated by surname + address + neighborhood in its
    immediate enclosing list item) -- and proves the bar was not
    lowered: neither the address alone, nor the surname alone, is
    sufficient without a second corroborating signal.
    """

    print()
    print("=" * 80)
    print(
        "[10/10] Multi-signal relevance scoring (mocked, no network)"
    )
    print("=" * 80)

    passed = 0
    failed = 0

    def run(applicant_name, html):
        application = {
            "applicant_name": applicant_name,
            "application_number": "TEST0009",
            "project_address": "12 Test Court",
            "neighborhood": "Meadow Grove",
        }

        enricher = ApplicantEnricher()
        enricher.serpapi_key = "test-key"

        def fake_search(query):
            if "site:" in query:
                return []
            return [
                {
                    "title": "Local Business Directory",
                    "link": "https://example-listings.test/directory",
                    "snippet": "A local business listing page.",
                }
            ]

        def fake_fetch_urls(urls):
            return [
                {"url": "https://example-listings.test/directory", "html": html}
                for _ in urls
            ]

        enricher._search = fake_search
        enricher._fetch_urls = fake_fetch_urls

        return enricher.enrich(application, live_search=True)

    # Case 1: generic anchor text, but the enclosing <li> corroborates
    # with surname + address + neighborhood -- should now be ACCEPTED.
    result_1 = run(
        "Jordan Vance",
        (
            "<html><body><ul>"
            "<li>Vance Builders LLC &mdash; 12 Test Court, Meadow Grove. "
            '<a href="https://vancebuilders.test/">Visit Website</a></li>'
            "</ul></body></html>"
        ),
    )

    if check(
        result_1.get("company_website") == "https://vancebuilders.test/",
        "Accepts a generic-text link corroborated by surname + address + neighborhood in its own list item",
    ):
        passed += 1
    else:
        failed += 1

    # Case 2: the address alone (no name reference anywhere in the
    # listing) must still be rejected -- the bar is not lowered.
    result_2 = run(
        "Jordan Vance",
        (
            "<html><body><ul>"
            "<li>Now serving 12 Test Court, Meadow Grove. "
            '<a href="https://unrelated-business.test/">Visit Website</a></li>'
            "</ul></body></html>"
        ),
    )

    if check(
        result_2.get("company_website") is None,
        "Still rejects a link corroborated only by address/neighborhood with no name reference at all",
    ):
        passed += 1
    else:
        failed += 1

    # Case 3: the surname alone, with no address/neighborhood/company
    # corroboration, must still be rejected -- a partial name match by
    # itself was never sufficient before and still isn't.
    result_3 = run(
        "Jordan Vance",
        (
            "<html><body><ul>"
            "<li>Vance Plumbing, unrelated business. "
            '<a href="https://unrelated-vance.test/">Visit Website</a></li>'
            "</ul></body></html>"
        ),
    )

    if check(
        result_3.get("company_website") is None,
        "Still rejects a link corroborated only by a partial (surname-only) name match with nothing else",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 80)
    print(
        f"[10/10] TESTS: {passed} passed, {failed} failed"
    )
    print("=" * 80)

    return 1 if failed else 0


def live_test() -> int:

    print()
    print("=" * 80)
    print(
        "LIVE APPLICANT ENRICHMENT"
    )
    print("=" * 80)

    import os

    if not os.getenv(
        "SERPAPI_API_KEY"
    ):
        print(
            "[ERROR] SERPAPI_API_KEY is not configured."
        )
        print(
            "PowerShell:"
        )
        print(
            '$env:SERPAPI_API_KEY="YOUR_KEY"'
        )
        return 1

    enricher = ApplicantEnricher(
        max_search_results=6,
        max_pages=5,
    )

    for application in TEST_APPLICATIONS:

        print()
        print(
            "-" * 80
        )

        print(
            f"APPLICANT: "
            f"{application['applicant_name']}"
        )

        result = enricher.enrich(
            application,
            live_search=True,
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    return 0


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--live",
        action="store_true",
        help="Use SerpAPI for live public-web enrichment.",
    )

    args = parser.parse_args()

    result = unit_tests()

    if result != 0:
        return result

    result = mocked_directory_test()

    if result != 0:
        return result

    result = mocked_government_exclusion_test()

    if result != 0:
        return result

    result = mocked_pdf_test()

    if result != 0:
        return result

    result = mocked_dedup_test()

    if result != 0:
        return result

    result = mocked_relevance_scoring_test()

    if result != 0:
        return result

    if args.live:
        return live_test()

    print()
    print(
        "Smoke tests complete."
    )

    print(
        "Use --live after configuring SERPAPI_API_KEY "
        "to test public-web enrichment."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )