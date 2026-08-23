"""
PermitSignal Phase 2B -- Investigation Engine Tests

Deterministic, network-free tests for the owner/person/entity
investigation capability added to
backend.app.services.investigation_engine.

Run:

    python -m scripts.test_investigation_engine
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.investigation_engine import (
    new_investigation_profile,
    get_investigation,
    run_web_search,
    run_website_discovery,
    run_business_directories,
    run_linkedin_discovery,
    run_public_records,
    run_project_relationships,
    run_contact_discovery,
    run_all,
    run_single_source,
    resolve_identities,
    _refresh_contacts,
    _refresh_summary,
    _update_overall_status,
    _build_queries,
    _is_generic_email,
    _domain_of,
    _dedupe_evidence,
    _confidence_label,
    INVESTIGATION_SOURCES,
)


def check(condition: bool, label: str) -> bool:
    if condition:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label}")
    return False


def _make_lead(**overrides) -> dict[str, Any]:
    base = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "owner_name": "PEARSON, JOSEPH BYRD",
        "owner_entity": "Pearson Development LLC",
        "owner_type": "individual",
        "project_address": "123 Main St",
        "neighborhood": "Downtown",
        "application_type": "Zone Map Amendment",
        "municipality": "Provo",
        "state": "Utah",
    }
    base.update(overrides)
    return base


def _mock_session(html: str = "") -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"organic_results": []}
    resp.text = html
    session.get.return_value = resp
    return session


def _mock_session_with_results(results: list[dict]) -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"organic_results": results}
    session.get.return_value = resp
    return session


def _mock_session_rate_limit() -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 429
    resp.json.return_value = {}
    session.get.return_value = resp
    return session


def test_new_investigation_profile() -> int:
    print()
    print("=" * 80)
    print("[1/11] new_investigation_profile() and get_investigation()")
    print("=" * 80)
    passed = 0
    failed = 0

    profile = new_investigation_profile()
    if check(profile["status"] == "NOT_STARTED", "New profile has NOT_STARTED status"):
        passed += 1
    else:
        failed += 1
    if check(all(s == "NOT_STARTED" for s in profile["sources"].values()), "All sources start as NOT_STARTED"):
        passed += 1
    else:
        failed += 1
    if check(profile["evidence"] == [], "Evidence starts empty"):
        passed += 1
    else:
        failed += 1
    if check(len(profile["sources"]) == 7, "Profile tracks 7 investigation sources"):
        passed += 1
    else:
        failed += 1

    lead = _make_lead()
    inv = get_investigation(lead)
    if check(inv["status"] == "NOT_STARTED", "get_investigation creates profile for lead without one"):
        passed += 1
    else:
        failed += 1

    lead2 = _make_lead()
    lead2["investigation"] = {
        "status": "ENRICHED",
        "sources": {s: "NOT_STARTED" for s in INVESTIGATION_SOURCES},
        "evidence": [{"field": "email", "value": "test@example.com"}],
        "events": [],
        "contacts": {"preferred_email": "test@example.com"},
        "identity_matches": [],
        "summary": {"emails_found": 1},
        "errors": [],
    }
    lead2["investigation"]["sources"]["web"] = "ENRICHED"
    inv2 = get_investigation(lead2)
    if check(inv2["status"] == "ENRICHED", "get_investigation preserves existing status"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[1/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_query_building() -> int:
    print()
    print("=" * 80)
    print("[2/11] _build_queries() -- owner-aware search query construction")
    print("=" * 80)
    passed = 0
    failed = 0

    queries = _build_queries(
        owner_name="Joseph Pearson",
        owner_entity="Pearson Development LLC",
        applicant_name="Jared Morgan",
        project_address="123 Main St",
        application_number="PLRZ20260264",
        municipality="Provo",
    )
    if check(len(queries) >= 5, f"Generates {len(queries)} queries from full inputs"):
        passed += 1
    else:
        failed += 1
    if check(any("Pearson Development LLC" in q for q in queries), "Entity-based query present"):
        passed += 1
    else:
        failed += 1
    if check(any("123 Main St" in q for q in queries), "Address-based query present"):
        passed += 1
    else:
        failed += 1
    if check(any("contact" in q.lower() for q in queries), "Contact query present"):
        passed += 1
    else:
        failed += 1

    empty = _build_queries(None, None, None, None, None)
    if check(empty == [], "Returns empty list when no identifiers available"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[2/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_web_search_pipeline() -> int:
    print()
    print("=" * 80)
    print("[3/11] run_web_search() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    inv = run_web_search(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["web"] == "ERROR", "Returns ERROR when no SERPAPI_API_KEY"):
        passed += 1
    else:
        failed += 1

    lead2 = _make_lead()
    inv2 = run_web_search(lead2, _mock_session(), serpapi_key="test-key")
    if check(inv2["sources"]["web"] == "NOT_FOUND", "Returns NOT_FOUND when no results"):
        passed += 1
    else:
        failed += 1

    session = _mock_session_with_results([{
        "title": "Pearson Development",
        "link": "https://pearsondev.com/about",
        "snippet": "Contact us at info@pearsondev.com or call (801) 555-0123",
    }])
    lead3 = _make_lead()
    inv3 = run_web_search(lead3, session, serpapi_key="test-key")
    email_ev = [e for e in inv3["evidence"] if e.get("field") == "email"]
    if check(len(email_ev) > 0, "Discovers email from search results"):
        passed += 1
    else:
        failed += 1
    if check(inv3["sources"]["web"] == "ENRICHED", "Sets source to ENRICHED when evidence found"):
        passed += 1
    else:
        failed += 1
    if check(inv3["started_at"] is not None, "Sets started_at timestamp"):
        passed += 1
    else:
        failed += 1
    if check(len(inv3["events"]) > 0, "Creates investigation event"):
        passed += 1
    else:
        failed += 1

    inv3b = run_web_search(lead3, session, serpapi_key="test-key", force=True)
    if check(inv3b["sources"]["web"] in ("ENRICHED", "PARTIAL"), "force=True allows re-running"):
        passed += 1
    else:
        failed += 1

    session_rl = _mock_session_rate_limit()
    lead4 = _make_lead()
    inv4 = run_web_search(lead4, session_rl, serpapi_key="test-key")
    if check(inv4["sources"]["web"] in ("NOT_FOUND", "PARTIAL", "ERROR"), "Handles rate limit gracefully"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[3/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_website_discovery_pipeline() -> int:
    print()
    print("=" * 80)
    print("[4/11] run_website_discovery() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    inv = run_website_discovery(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["website"] == "NOT_FOUND", "Returns NOT_FOUND without API key or evidence"):
        passed += 1
    else:
        failed += 1

    lead2 = _make_lead()
    lead2["investigation"] = new_investigation_profile()
    lead2["investigation"]["evidence"] = [{
        "field": "website",
        "value": "https://pearsondev.com",
        "source_type": "search_result",
        "source_domain": "pearsondev.com",
    }]

    html = "<html><head><title>Pearson Dev</title></head><body>Contact info@pearsondev.com (801) 555-1234</body></html>"
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    session.get.return_value = resp

    inv2 = run_website_discovery(lead2, session, serpapi_key=None)
    email_ev = [e for e in inv2["evidence"] if e.get("field") == "email"]
    if check(len(email_ev) > 0, "Extracts emails from official website"):
        passed += 1
    else:
        failed += 1
    if check(any(e.get("source_type") == "official_website" for e in inv2["evidence"]), "Evidence has official_website source type"):
        passed += 1
    else:
        failed += 1

    lead3 = _make_lead()
    inv3 = run_website_discovery(lead3, _mock_session(), serpapi_key="test-key")
    if check(inv3["sources"]["website"] == "NOT_FOUND", "Returns NOT_FOUND with no search results"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[4/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_business_directories_pipeline() -> int:
    print()
    print("=" * 80)
    print("[5/11] run_business_directories() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    inv = run_business_directories(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["directories"] == "ERROR", "Returns ERROR when no API key"):
        passed += 1
    else:
        failed += 1

    lead2 = _make_lead()
    inv2 = run_business_directories(lead2, _mock_session(), serpapi_key="test-key")
    if check(inv2["sources"]["directories"] == "NOT_FOUND", "Returns NOT_FOUND with no results"):
        passed += 1
    else:
        failed += 1

    session = _mock_session_with_results([{
        "title": "Pearson Development LLC - OpenCorporates",
        "link": "https://opencorporates.com/companies/us/pearsondev",
        "snippet": "Pearson Development LLC, Utah. Email: office@pearsondev.com",
    }])
    lead3 = _make_lead()
    inv3 = run_business_directories(lead3, session, serpapi_key="test-key")
    if check(inv3["sources"]["directories"] in ("ENRICHED", "PARTIAL"), "Enriched when directory listing found"):
        passed += 1
    else:
        failed += 1

    entity_ev = [e for e in inv3["evidence"] if e.get("field") == "business_listing"]
    if check(len(entity_ev) > 0, "Records business listing evidence"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[5/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_linkedin_pipeline() -> int:
    print()
    print("=" * 80)
    print("[6/11] run_linkedin_discovery() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    inv = run_linkedin_discovery(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["linkedin"] == "ERROR", "Returns ERROR when no API key"):
        passed += 1
    else:
        failed += 1

    lead_empty = _make_lead(owner_name=None, applicant_name=None)
    inv_empty = run_linkedin_discovery(lead_empty, _mock_session(), serpapi_key="test-key")
    if check(inv_empty["sources"]["linkedin"] == "NOT_FOUND", "Returns NOT_FOUND when no name available"):
        passed += 1
    else:
        failed += 1

    session = _mock_session_with_results([{
        "title": "Joseph Pearson - LinkedIn",
        "link": "https://www.linkedin.com/in/joseph-pearson-dev",
        "snippet": "Owner at Pearson Development LLC, Provo, Utah",
    }])
    lead2 = _make_lead()
    inv2 = run_linkedin_discovery(lead2, session, serpapi_key="test-key")
    li_ev = [e for e in inv2["evidence"] if e.get("field") == "linkedin_profile"]
    if check(len(li_ev) > 0, "Discovers LinkedIn profile"):
        passed += 1
    else:
        failed += 1
    if check(inv2["sources"]["linkedin"] == "ENRICHED", "Sets source to ENRICHED"):
        passed += 1
    else:
        failed += 1

    session_no_li = _mock_session_with_results([{
        "title": "Some unrelated page",
        "link": "https://example.com/page",
        "snippet": "Not a LinkedIn page",
    }])
    lead3 = _make_lead()
    inv3 = run_linkedin_discovery(lead3, session_no_li, serpapi_key="test-key")
    if check(inv3["sources"]["linkedin"] == "NOT_FOUND", "Returns NOT_FOUND when no LinkedIn results"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[6/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_project_relationships_pipeline() -> int:
    print()
    print("=" * 80)
    print("[7/11] run_project_relationships() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead(owner_name=None, owner_entity=None, applicant_name=None)
    inv = run_project_relationships(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["project"] == "NOT_FOUND", "Returns NOT_FOUND with no identifiers"):
        passed += 1
    else:
        failed += 1

    session = _mock_session_with_results([{
        "title": "123 Main St Development",
        "link": "https://provo.gov/dev/123-main",
        "snippet": "Pearson Development LLC submitted a concept plan for 123 Main St in the Downtown neighborhood",
    }])
    lead2 = _make_lead()
    inv2 = run_project_relationships(lead2, session, serpapi_key="test-key")
    rel_ev = [e for e in inv2["evidence"] if e.get("field") == "project_relationship"]
    if check(len(rel_ev) > 0, "Discovers entity-address relationship"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[7/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_contact_discovery_pipeline() -> int:
    print()
    print("=" * 80)
    print("[8/11] run_contact_discovery() pipeline")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    inv = run_contact_discovery(lead, _mock_session(), serpapi_key=None)
    if check(inv["sources"]["contact"] == "ERROR", "Returns ERROR when no API key"):
        passed += 1
    else:
        failed += 1

    session = _mock_session_with_results([{
        "title": "Pearson Development LLC",
        "link": "https://pearsondev.com",
        "snippet": "Call (801) 555-9999 or email jpearson@pearsondev.com",
    }])
    lead2 = _make_lead()
    inv2 = run_contact_discovery(lead2, session, serpapi_key="test-key")
    email_ev = [e for e in inv2["evidence"] if e.get("field") == "email"]
    phone_ev = [e for e in inv2["evidence"] if e.get("field") == "phone"]
    if check(len(email_ev) > 0 or len(phone_ev) > 0, "Discovers contact information"):
        passed += 1
    else:
        failed += 1

    # Test: Already has enough contacts
    lead3 = _make_lead()
    lead3["investigation"] = new_investigation_profile()
    lead3["investigation"]["evidence"] = [
        {"field": "email", "value": "a@a.com"},
        {"field": "email", "value": "b@b.com"},
        {"field": "email", "value": "c@c.com"},
    ]
    inv3 = run_contact_discovery(lead3, _mock_session(), serpapi_key="test-key")
    if check(inv3["sources"]["contact"] == "ENRICHED", "Skips search when enough contacts exist"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[8/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_identity_resolution() -> int:
    print()
    print("=" * 80)
    print("[9/11] resolve_identities() -- deterministic identity matching")
    print("=" * 80)
    passed = 0
    failed = 0

    lead = _make_lead()
    matches = resolve_identities(lead)
    if check(matches == [], "Returns empty when no investigation evidence"):
        passed += 1
    else:
        failed += 1

    lead2 = _make_lead()
    lead2["investigation"] = new_investigation_profile()
    lead2["investigation"]["evidence"] = [{
        "field": "email",
        "value": "jpearson@pearsondev.com",
        "source_url": "https://pearsondev.com/contact",
        "source_type": "official_website",
        "source_domain": "pearsondev.com",
        "confidence_score": 0.85,
        "evidence_text": "Joseph Pearson, Owner of Pearson Development LLC. Contact: jpearson@pearsondev.com",
    }]
    matches2 = resolve_identities(lead2)
    if check(len(matches2) > 0, "Produces identity match for email evidence"):
        passed += 1
    else:
        failed += 1
    if check(matches2[0].get("match_score", 0) > 0.0, "Match score is positive"):
        passed += 1
    else:
        failed += 1
    if check(len(matches2[0].get("matched_signals", [])) > 0, "Matched signals are recorded"):
        passed += 1
    else:
        failed += 1
    if check(matches2[0].get("reasoning", ""), "Reasoning is provided"):
        passed += 1
    else:
        failed += 1

    lead3 = _make_lead()
    lead3["investigation"] = new_investigation_profile()
    lead3["investigation"]["evidence"] = [{
        "field": "email",
        "value": "random@example.com",
        "source_url": "https://unrelated.com/page",
        "source_type": "public_web",
        "source_domain": "unrelated.com",
        "confidence_score": 0.30,
        "evidence_text": "No mention of owner or project",
    }]
    matches3 = resolve_identities(lead3)
    if check(matches3 and matches3[0].get("match_score", 0) < 0.30, "Unrelated evidence scores lower"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[9/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_contact_ranking() -> int:
    print()
    print("=" * 80)
    print("[10/11] _refresh_contacts() -- deterministic contact ranking")
    print("=" * 80)
    passed = 0
    failed = 0

    inv = new_investigation_profile()
    inv["evidence"] = [
        {"field": "email", "value": "info@example.com", "source_type": "public_web",
         "source_domain": "example.com", "confidence_score": 0.45},
        {"field": "email", "value": "jpearson@pearsondev.com", "source_type": "official_website",
         "source_domain": "pearsondev.com", "confidence_score": 0.88},
        {"field": "email", "value": "contact@example.com", "source_type": "business_directory",
         "source_domain": "bbb.org", "confidence_score": 0.55},
        {"field": "phone", "value": "(801) 555-0123", "source_type": "official_website",
         "source_domain": "pearsondev.com", "confidence_score": 0.75},
        {"field": "website", "value": "https://pearsondev.com", "source_type": "official_website",
         "source_domain": "pearsondev.com", "confidence_score": 0.80},
    ]
    _refresh_contacts(inv)
    contacts = inv["contacts"]

    if check(contacts["preferred_email"] == "jpearson@pearsondev.com",
             "Preferred email is official website non-generic"):
        passed += 1
    else:
        failed += 1
    if check(contacts["preferred_phone"] == "(801) 555-0123", "Preferred phone found"):
        passed += 1
    else:
        failed += 1
    if check(contacts["preferred_website"] == "https://pearsondev.com", "Preferred website found"):
        passed += 1
    else:
        failed += 1
    if check(len(contacts["email_candidates"]) == 3, "All email candidates preserved"):
        passed += 1
    else:
        failed += 1
    if check(contacts["email_candidates"][0]["source_type"] == "official_website",
             "Official website email ranked first"):
        passed += 1
    else:
        failed += 1

    inv2 = new_investigation_profile()
    inv2["evidence"] = [
        {"field": "email", "value": "info@example.com", "source_type": "public_web",
         "source_domain": "example.com", "confidence_score": 0.45},
        {"field": "email", "value": "info@example.com", "source_type": "official_website",
         "source_domain": "example.com", "confidence_score": 0.80},
    ]
    _refresh_contacts(inv2)
    if check(len(inv2["contacts"]["email_candidates"]) == 1, "Deduplicates by email value"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[10/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def test_orchestrator_and_status() -> int:
    print()
    print("=" * 80)
    print("[11/11] run_all(), run_single_source(), status transitions, idempotency")
    print("=" * 80)
    passed = 0
    failed = 0

    # Test: run_all with no API key produces ERROR statuses (patch env to suppress real key)
    from unittest.mock import patch
    import os

    with patch.dict("os.environ", {}, clear=True):
        lead = _make_lead()
        inv = run_all(lead, serpapi_key=None)
        if check(inv["status"] in ("ERROR", "NOT_FOUND", "IN_PROGRESS"),
                 "run_all without API key doesn't crash"):
            passed += 1
        else:
            failed += 1

        # Test: run_single_source
        lead2 = _make_lead()
        inv2 = run_single_source(lead2, "web", serpapi_key=None)
        if check(inv2["sources"]["web"] == "ERROR", "run_single_source works for web"):
            passed += 1
        else:
            failed += 1

        # Test: unknown source
        lead3 = _make_lead()
        inv3 = run_single_source(lead3, "unknown_source", serpapi_key=None)
        if check("Unknown source" in str(inv3.get("errors", [])), "Unknown source produces error"):
            passed += 1
        else:
            failed += 1

    # Test: Overall status transitions
    inv4 = new_investigation_profile()
    _update_overall_status(inv4)
    if check(inv4["status"] == "NOT_STARTED", "All NOT_STARTED -> NOT_STARTED"):
        passed += 1
    else:
        failed += 1

    inv5 = new_investigation_profile()
    inv5["sources"]["web"] = "ENRICHED"
    _update_overall_status(inv5)
    if check(inv5["status"] in ("PARTIAL", "ENRICHED"), "One ENRICHED -> PARTIAL or ENRICHED"):
        passed += 1
    else:
        failed += 1

    inv6 = new_investigation_profile()
    for s in inv6["sources"]:
        inv6["sources"][s] = "ENRICHED"
    _update_overall_status(inv6)
    if check(inv6["status"] == "ENRICHED", "All ENRICHED -> ENRICHED"):
        passed += 1
    else:
        failed += 1

    inv7 = new_investigation_profile()
    inv7["sources"]["web"] = "ERROR"
    _update_overall_status(inv7)
    if check(inv7["status"] == "ERROR", "All ERROR or NOT_STARTED -> ERROR"):
        passed += 1
    else:
        failed += 1

    inv8 = new_investigation_profile()
    inv8["sources"]["web"] = "ERROR"
    inv8["sources"]["website"] = "ENRICHED"
    _update_overall_status(inv8)
    if check(inv8["status"] == "PARTIAL", "Mix ERROR+ENRICHED -> PARTIAL"):
        passed += 1
    else:
        failed += 1

    # Test: deduplication
    ev = [
        {"field": "email", "value": "a@b.com", "source_url": "https://x.com"},
        {"field": "email", "value": "a@b.com", "source_url": "https://x.com"},
        {"field": "email", "value": "A@B.com", "source_url": "https://x.com"},
        {"field": "phone", "value": "555-1234", "source_url": "https://y.com"},
    ]
    deduped = _dedupe_evidence(ev)
    if check(len(deduped) == 2, f"Dedupe by field+value+url ({len(deduped)} == 2)"):
        passed += 1
    else:
        failed += 1

    # Test: confidence label
    if check(_confidence_label(0.90) == "HIGH", "0.90 -> HIGH"):
        passed += 1
    else:
        failed += 1
    if check(_confidence_label(0.65) == "MEDIUM", "0.65 -> MEDIUM"):
        passed += 1
    else:
        failed += 1
    if check(_confidence_label(0.30) == "LOW", "0.30 -> LOW"):
        passed += 1
    else:
        failed += 1

    # Test: generic email detection
    if check(_is_generic_email("info@company.com"), "info@ is generic"):
        passed += 1
    else:
        failed += 1
    if check(not _is_generic_email("jpearson@company.com"), "jpearson@ is not generic"):
        passed += 1
    else:
        failed += 1

    # Test: domain extraction
    if check(_domain_of("https://example.com/path") == "example.com", "Domain from URL"):
        passed += 1
    else:
        failed += 1
    if check(_domain_of("user@example.com") == "example.com", "Domain from email"):
        passed += 1
    else:
        failed += 1

    print()
    print(f"[11/11] TESTS: {passed} passed, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    print("=" * 80)
    print("PERMITSIGNAL PHASE 2B -- INVESTIGATION ENGINE")
    print("=" * 80)

    for test_fn in (
        test_new_investigation_profile,
        test_query_building,
        test_web_search_pipeline,
        test_website_discovery_pipeline,
        test_business_directories_pipeline,
        test_linkedin_pipeline,
        test_project_relationships_pipeline,
        test_contact_discovery_pipeline,
        test_identity_resolution,
        test_contact_ranking,
        test_orchestrator_and_status,
    ):
        result = test_fn()
        if result != 0:
            return result

    print()
    print("=" * 80)
    print("ALL PHASE 2B INVESTIGATION ENGINE TESTS PASSED")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
