"""
PermitSignal Phase 2 -- Owner / Person Enrichment Tests

Deterministic, network-free tests for the owner/principal/executive/
partner discovery capability added to backend.app.services.
applicant_enrichment (ApplicantEnricher._extract_role_mentions /
find_role_person_mentions) and its additive integration into
pipeline_orchestrator._enrich_applicants().

Run:

    python -m scripts.test_owner_enrichment
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.applicant_enrichment import (
    ApplicantEnricher,
    find_role_person_mentions,
)
from backend.app.services import pipeline_orchestrator as po
from backend.app.services.pipeline_orchestrator import _enrich_applicants


def check(condition: bool, label: str) -> bool:
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def run_enricher(application, html):
    enricher = ApplicantEnricher()
    enricher.serpapi_key = "test-key"

    def fake_search(query):
        if "site:" in query:
            return []
        return [
            {
                "title": "Company page",
                "link": "https://example-company.test/team",
                "snippet": "Company team page.",
            }
        ]

    def fake_fetch_urls(urls):
        return [
            {"url": "https://example-company.test/team", "html": html}
            for _ in urls
        ]

    enricher._search = fake_search
    enricher._fetch_urls = fake_fetch_urls

    return enricher.enrich(application, live_search=True)


def test_role_regex_unit() -> int:
    print()
    print("=" * 80)
    print("[1/5] find_role_person_mentions() unit behavior")
    print("=" * 80)

    passed = 0
    failed = 0

    mentions = find_role_person_mentions(
        "Meet our team. Jane Smith, Owner. Contact us for a quote."
    )

    if check(
        ("Jane Smith", "Owner") in mentions,
        "Extracts a comma-form name/role pair",
    ):
        passed += 1
    else:
        failed += 1

    mentions_colon = find_role_person_mentions(
        "Managing Partner: John Doe. Reach out any time."
    )

    if check(
        ("John Doe", "Managing Partner") in mentions_colon,
        "Extracts a colon-form role/name pair",
    ):
        passed += 1
    else:
        failed += 1

    mentions_company = find_role_person_mentions(
        "Vance Builders LLC, Owner of the finest homes in the valley."
    )

    if check(
        not mentions_company,
        "Rejects a company/organization name masquerading as a person",
    ):
        passed += 1
    else:
        failed += 1

    mentions_none = find_role_person_mentions(
        "Jane Smith is our lead project manager for this development."
    )

    if check(
        not mentions_none,
        "Never matches a generic job title outside the fixed ownership vocabulary",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[1/5] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_contact_role_same_person() -> int:
    print()
    print("=" * 80)
    print("[2/5] contact_role: applicant's own professional role")
    print("=" * 80)

    passed = 0
    failed = 0

    application = {
        "applicant_name": "Alexandra Whitfield",
        "application_number": "TEST-OWNER-0001",
        "application_type": "Concept Plan",
        "project_address": "500 Test Ave",
        "neighborhood": "Test Heights",
    }

    result = run_enricher(
        application,
        (
            "<html><body><p>Alexandra Whitfield, Managing Partner at "
            "Whitfield Development. Call (801) 555-0100.</p></body></html>"
        ),
    )

    if check(
        result.get("contact_role") == "Managing Partner",
        "Attaches the applicant's own role discovered on an official page",
    ):
        passed += 1
    else:
        failed += 1

    role_sources = [
        source
        for source in result.get("sources", [])
        if source.get("field") == "contact_role_candidate"
    ]

    if check(
        len(role_sources) > 0 and role_sources[0].get("source_url"),
        "Records evidence (source_url) for the discovered role",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        not result.get("discovered_parties"),
        "Does not also record the applicant as a separate discovered party",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[2/5] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_distinct_owner_discovery() -> int:
    print()
    print("=" * 80)
    print("[3/5] Distinct owner/principal discovery with evidence")
    print("=" * 80)

    passed = 0
    failed = 0

    application = {
        "applicant_name": "Summit Ridge Holdings",
        "application_number": "TEST-OWNER-0002",
        "application_type": "Concept Plan",
        "project_address": "12 Test Court",
        "neighborhood": "Test Meadows",
    }

    result = run_enricher(
        application,
        (
            "<html><body><p>Summit Ridge Holdings, 12 Test Court, "
            "Test Meadows. Principal: Marcus Reyes. He can be reached "
            "for project inquiries.</p></body></html>"
        ),
    )

    parties = result.get("discovered_parties") or []

    if check(
        any(
            party.get("party_name") == "Marcus Reyes"
            and party.get("party_role") == "Principal"
            for party in parties
        ),
        "Discovers a distinct principal tied to the applicant/company",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        all(party.get("party_confidence") for party in parties),
        "Every discovered party carries a confidence label",
    ):
        passed += 1
    else:
        failed += 1

    evidence = [
        source
        for source in result.get("sources", [])
        if source.get("field") == "owner_person_candidate"
    ]

    if check(
        len(evidence) > 0
        and evidence[0].get("evidence_text")
        and evidence[0].get("source_url"),
        "Retains evidence_text and source_url so the association is traceable",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[3/5] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_no_fabrication_when_unrelated_or_absent() -> int:
    print()
    print("=" * 80)
    print("[4/5] No fabrication: unresolved cases stay null/empty")
    print("=" * 80)

    passed = 0
    failed = 0

    application_no_evidence = {
        "applicant_name": "Riverbend Partners",
        "application_number": "TEST-OWNER-0003",
        "application_type": "Concept Plan",
        "project_address": "88 Quiet Lane",
        "neighborhood": "Riverbend",
    }

    result_none = run_enricher(
        application_no_evidence,
        "<html><body><p>Riverbend Partners, 88 Quiet Lane, Riverbend. "
        "No further details.</p></body></html>",
    )

    if check(
        result_none.get("contact_role") is None
        and not result_none.get("discovered_parties"),
        "No role/person evidence -> contact_role=None, discovered_parties=[] (not fabricated)",
    ):
        passed += 1
    else:
        failed += 1

    application_unrelated = {
        "applicant_name": "Deacon Fields",
        "application_number": "TEST-OWNER-0004",
        "application_type": "Variance",
        "project_address": "77 Elm Street",
        "neighborhood": "Elm Grove",
    }

    result_unrelated = run_enricher(
        application_unrelated,
        (
            "<html><body><p>An unrelated business down the street. "
            "Owner: Priya Chandrasekaran. Nothing to do with this "
            "applicant or project.</p></body></html>"
        ),
    )

    if check(
        not result_unrelated.get("discovered_parties"),
        "Rejects a role+name pair found on a page that never evidently concerns this applicant",
    ):
        passed += 1
    else:
        failed += 1

    # Government-record pages must never feed this heuristic -- the
    # structured extractor (application_extractor.extract_owner/
    # extract_parties) is the sole authority for government-labeled
    # ownership.
    application_gov = {
        "applicant_name": "Casey Nolan",
        "application_number": "TEST-OWNER-0005",
        "application_type": "Variance",
        "project_address": "44 Gov Way",
        "neighborhood": "Downtown",
        "source_url": "https://www.provo.gov/AgendaCenter/ViewFile/Agenda/_test",
    }

    enricher = ApplicantEnricher()
    enricher.serpapi_key = "test-key"
    enricher._search = lambda query: []
    enricher._fetch_urls = lambda urls: [
        {
            "url": "https://www.provo.gov/AgendaCenter/ViewFile/Agenda/_test",
            "html": (
                "<html><body><p>Casey Nolan, Owner. Staff contact "
                "dspublichearings@provo.org.</p></body></html>"
            ),
        }
        for _ in urls
    ]

    result_gov = enricher.enrich(application_gov, live_search=True)

    if check(
        result_gov.get("contact_role") is None,
        "Never mines a government-hosted page for role/person evidence",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[4/5] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_pipeline_additive_merge() -> int:
    print()
    print("=" * 80)
    print("[5/5] pipeline_orchestrator: discovered parties are additive")
    print("=" * 80)

    passed = 0
    failed = 0

    class FakeIdentityModule:
        @staticmethod
        def enrich_applicant_identity(application):
            return {
                "applicant_name": application.get("applicant_name"),
                "identity_status": "identity_only",
            }

    class FakeEnrichmentModule:
        @staticmethod
        def enrich_applicant_contact(application, live_search=True):
            return {
                "contact_role": "Managing Partner",
                "discovered_parties": [
                    {
                        "party_name": "Marcus Reyes",
                        "party_role": "Principal",
                        "party_company": None,
                        "party_contact_email": None,
                        "party_contact_phone": None,
                        "party_source": "public_web",
                        "party_confidence": "MEDIUM",
                    }
                ],
                "enrichment_status": "enriched",
            }

    def _fake_import(name):
        mapping = {
            po.APPLICANT_IDENTITY_MODULE: FakeIdentityModule,
            po.APPLICANT_ENRICHMENT_MODULE: FakeEnrichmentModule,
        }
        return mapping[name]

    opportunities_in = [
        {
            "application_number": "PLOWNER0001",
            "applicant_name": "Summit Ridge Holdings",
            "parties": [
                {
                    "party_name": "Jordan Lee",
                    "party_role": "Engineer",
                    "party_company": None,
                    "party_contact_email": None,
                    "party_contact_phone": None,
                    "party_source": "government_record",
                    "party_confidence": "HIGH",
                }
            ],
        }
    ]

    with patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import,
    ):
        enriched = _enrich_applicants(opportunities_in, live_enrichment=True)

    record = enriched[0]
    parties = record.get("parties") or []

    if check(
        any(p.get("party_role") == "Engineer" for p in parties),
        "Preserves the document-extracted party (Engineer) unchanged",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        any(
            p.get("party_name") == "Marcus Reyes"
            and p.get("party_role") == "Principal"
            for p in parties
        ),
        "Appends the newly discovered owner/principal without replacing existing parties",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        len(parties) == 2,
        "Result has exactly document party + discovered party (no overwrite, no duplication)",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        record.get("contact_role") == "Managing Partner",
        "Surfaces contact_role onto the canonical opportunity record",
    ):
        passed += 1
    else:
        failed += 1

    if check(
        "discovered_parties" not in record,
        "Removes the transient discovered_parties key once merged into parties",
    ):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[5/5] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    print("=" * 80)
    print("PERMITSIGNAL PHASE 2 -- OWNER / PERSON ENRICHMENT")
    print("=" * 80)

    for test_fn in (
        test_role_regex_unit,
        test_contact_role_same_person,
        test_distinct_owner_discovery,
        test_no_fabrication_when_unrelated_or_absent,
        test_pipeline_additive_merge,
    ):
        result = test_fn()
        if result != 0:
            return result

    print()
    print("=" * 80)
    print("ALL PHASE 2 OWNER/PERSON ENRICHMENT TESTS PASSED")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
