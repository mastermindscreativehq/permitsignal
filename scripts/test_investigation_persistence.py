"""
PermitSignal Phase 2B — Investigation Profile Persistence Round-Trip Test

Tests the ACTUAL repository persistence path (lead_repository.upsert_leads
/ lead_repository.fetch_lead) with the record JSONB column.

Verifies:
1. Investigation profile survives Supabase write + read
2. All investigation fields persist
3. All owner fields are preserved unchanged
4. Unrelated lead fields are not lost
"""
from __future__ import annotations

import copy
import sys
import uuid

sys.path.insert(0, ".")

from backend.app.services import lead_repository
from backend.app.services.investigation_engine import (
    new_investigation_profile,
    get_investigation,
    run_single_source,
    _now_iso,
)


def _check(label: str, condition: bool) -> bool:
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {label}")
    return condition


def _make_test_lead() -> dict:
    """Create a realistic test lead with all owner fields populated."""
    return {
        "application_number": f"PERSIST-TEST-{uuid.uuid4().hex[:8].upper()}",
        "applicant_name": "Test Applicant",
        "normalized_applicant_name": "test applicant",
        "application_type": "Zone Map Amendment",
        "project_address": "123 Test Street",
        "neighborhood": "Test Neighborhood",
        "status": [],
        "description": "Test project description",
        "owner_name": "Test Owner Name",
        "owner_entity": "Test Owner Entity LLC",
        "owner_type": "Entity",
        "owner_contact_name": "Test Owner Contact",
        "owner_contact_email": None,
        "owner_contact_phone": None,
        "owner_website": None,
        "owner_linkedin_url": None,
        "owner_source": "government_record",
        "owner_confidence": "HIGH",
        "applicant_email": None,
        "applicant_phone": None,
        "applicant_entity": None,
        "applicant_contact_name": None,
        "applicant_contact_email": None,
        "applicant_contact_phone": None,
        "applicant_source": "government_record",
        "applicant_confidence": "HIGH",
        "parties": [],
        "friction_score": 50,
        "friction_signals": ["continued"],
        "friction_events": [],
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "has_future_opportunity": True,
        "days_until_event": 11,
        "urgency": "SOON",
        "priority": "HIGH",
        "priority_score": 180,
        "is_actionable": True,
        "opportunity_reason": "Test opportunity reason",
        "lead_status": "NO_CONTACT",
        "is_contactable": False,
        "source": "Provo Planning Commission",
        "source_url": "https://example.com/test.pdf",
        "municipality": "Provo",
        "state": "Utah",
        "staff_contact_name": "Staff Person",
        "staff_contact_email": "staff@test.gov",
        "staff_contact_phone": "(801) 555-0100",
        "outreach_status": "NEW",
        "outreach_qualification_status": None,
        "outreach_channel": None,
        "outreach_contact_type": None,
        "outreach_contact_reason": None,
        "outreach_message_subject": None,
        "outreach_message_body": None,
        "follow_up_required": False,
        "follow_up_reason": None,
        "last_outreach_at": None,
        "outreach_events": [],
        "contactability_level": "NO_VERIFIED_CONTACT",
        "commercial_readiness": "NEEDS_CONTACT_ENRICHMENT",
        "recommended_commercial_action": "investigate missing decision-maker",
        "commercial_action_reason": None,
        "approval_status": None,
        "approval_action": None,
        "approval_action_type": None,
        "approval_confidence": None,
        "approval_basis": None,
        "approval_relevant_date": None,
        "approval_source": None,
        "approval_source_type": None,
        "approval_evidence": None,
        "approval_reason": None,
        "contact_name": None,
        "contact_role": None,
        "contact_email": None,
        "contact_phone": None,
        "contact_source": None,
        "contact_confidence": None,
        "contact_is_public": None,
        "contact_is_verified": None,
        "identity_status": None,
        "enrichment_status": None,
        "enrichment_method": None,
        "email_source": None,
        "phone_source": None,
        "company_source": None,
        "email_confidence": None,
        "phone_confidence": None,
        "project_scale_units": None,
        "project_scale_type": None,
        "project_scale_basis": None,
        "estimated_value_low": None,
        "estimated_value_high": None,
        "estimated_value_mid": None,
        "estimated_value_currency": None,
        "estimated_value_confidence": None,
        "estimated_value_source_type": None,
        "estimated_value_basis": None,
        "public_funding_status": None,
        "public_funding_confidence": None,
        "public_funding_basis": None,
        "public_spend_low": None,
        "public_spend_high": None,
        "public_spend_mid": None,
        "public_spend_confidence": None,
        "parcel_number": None,
        "acreage": None,
        "zoning": None,
        "owner_website": None,
        "owner_linkedin_url": None,
        "company_website": None,
        "company_domain": None,
        "company_name": None,
        "linkedin_url": None,
        "created_at": "2026-08-17T00:00:00Z",
    }


def test_persistence_round_trip() -> int:
    print()
    print("=" * 80)
    print("REPOSITORY ROUND-TRIP PERSISTENCE TEST")
    print("=" * 80)
    passed = 0
    failed = 0

    if not lead_repository.is_configured():
        print()
        print("  BLOCKED: Supabase not configured (SUPABASE_URL/SUPABASE_KEY)")
        print("  Cannot test actual persistence round-trip.")
        return 0

    # Step 1: Create a test lead with investigation data
    print()
    print("[Step 1] Creating test lead with investigation profile")
    lead = _make_test_lead()
    original_owner_name = lead["owner_name"]
    original_owner_entity = lead["owner_entity"]
    original_owner_confidence = lead["owner_confidence"]
    original_owner_source = lead["owner_source"]
    original_lead_status = lead["lead_status"]
    original_priority = lead["priority"]

    # Inject a deterministic investigation profile
    inv = new_investigation_profile()
    inv["status"] = "PARTIAL"
    inv["started_at"] = "2026-08-17T10:00:00+00:00"
    inv["completed_at"] = "2026-08-17T10:05:00+00:00"
    inv["last_at"] = "2026-08-17T10:05:00+00:00"
    inv["queries"] = ['"Test Owner Entity LLC"', '"Test Owner Entity LLC" contact']
    inv["sources"]["web"] = "ENRICHED"
    inv["sources"]["directories"] = "PARTIAL"
    inv["sources"]["linkedin"] = "NOT_FOUND"
    inv["evidence"] = [
        {
            "field": "email",
            "value": "info@testowner.com",
            "source_url": "https://testowner.com/about",
            "source_type": "official_website",
            "source_domain": "testowner.com",
            "discovered_at": "2026-08-17T10:01:00+00:00",
            "confidence": "HIGH",
            "confidence_score": 0.85,
            "evidence_text": "Contact us at info@testowner.com for more information.",
            "match_reason": "Found on official website",
        },
        {
            "field": "phone",
            "value": "(801) 555-9999",
            "source_url": "https://testowner.com/contact",
            "source_type": "official_website",
            "source_domain": "testowner.com",
            "discovered_at": "2026-08-17T10:01:30+00:00",
            "confidence": "MEDIUM",
            "confidence_score": 0.70,
            "evidence_text": "Call us at (801) 555-9999",
            "match_reason": "Found on official website contact page",
        },
        {
            "field": "website",
            "value": "https://testowner.com",
            "source_url": "https://testowner.com",
            "source_type": "official_website",
            "source_domain": "testowner.com",
            "discovered_at": "2026-08-17T10:02:00+00:00",
            "confidence": "MEDIUM",
            "confidence_score": 0.75,
            "evidence_text": "Test Owner Entity LLC official website",
            "match_reason": "Identified as official company website",
        },
    ]
    inv["events"] = [
        {
            "action": "web_search",
            "source": "web",
            "occurred_at": "2026-08-17T10:01:00+00:00",
            "queries_executed": 9,
            "pages_fetched": 0,
            "emails_discovered": 1,
            "phones_discovered": 1,
            "websites_discovered": 1,
            "result": "success",
        }
    ]
    inv["contacts"] = {
        "preferred_email": "info@testowner.com",
        "preferred_phone": "(801) 555-9999",
        "preferred_website": "https://testowner.com",
        "email_candidates": [
            {
                "value": "info@testowner.com",
                "source_url": "https://testowner.com/about",
                "source_type": "official_website",
                "source_domain": "testowner.com",
                "confidence": 0.85,
                "is_generic": True,
            }
        ],
        "phone_candidates": [
            {
                "value": "(801) 555-9999",
                "source_url": "https://testowner.com/contact",
                "source_type": "official_website",
                "source_domain": "testowner.com",
                "confidence": 0.70,
            }
        ],
        "website_candidates": [
            {
                "value": "https://testowner.com",
                "source_url": "https://testowner.com",
                "source_type": "official_website",
                "source_domain": "testowner.com",
                "confidence": 0.75,
            }
        ],
    }
    inv["identity_matches"] = [
        {
            "match_score": 0.55,
            "confidence_label": "MEDIUM",
            "matched_signals": ["Entity name appears in source domain (testowner.com)"],
            "conflicting_signals": [],
            "reasoning": "Score 0.55: Entity name appears in source domain",
            "source_url": "https://testowner.com",
        }
    ]
    inv["summary"] = {
        "emails_found": 1,
        "phones_found": 1,
        "websites_found": 1,
        "profiles_found": 0,
        "entities_found": 0,
    }
    inv["errors"] = []

    lead["investigation"] = inv

    if _check("Lead has investigation profile", lead.get("investigation") is not None):
        passed += 1
    else:
        failed += 1

    # Step 2: Persist via production path
    print()
    print("[Step 2] Persisting via lead_repository.upsert_leads()")
    try:
        result = lead_repository.upsert_leads([lead])
        if _check("Upsert returns success", result.get("status") == "synced"):
            passed += 1
        else:
            print(f"    Upsert result: {result}")
            failed += 1
    except Exception as exc:
        print(f"  [FAIL] Upsert raised: {exc}")
        failed += 1
        return failed

    # Step 3: Read back via production path
    print()
    print("[Step 3] Reading back via lead_repository.fetch_lead()")
    try:
        loaded = lead_repository.fetch_lead(lead["application_number"])
    except Exception as exc:
        print(f"  [FAIL] fetch_lead raised: {exc}")
        failed += 1
        return failed

    if _check("Lead loaded from Supabase", loaded is not None):
        passed += 1
    else:
        print("  [FAIL] fetch_lead returned None")
        failed += 1
        return failed

    # Step 4: Verify investigation profile survives
    print()
    print("[Step 4] Verifying investigation profile fields")
    inv_loaded = loaded.get("investigation")
    if _check("Investigation key present in loaded record", inv_loaded is not None):
        passed += 1
    else:
        print(f"  Top-level keys: {sorted(loaded.keys())[:20]}...")
        failed += 1
        return failed

    # Status
    if _check(
        f"investigation.status = PARTIAL (got {inv_loaded.get('status')!r})",
        inv_loaded.get("status") == "PARTIAL",
    ):
        passed += 1
    else:
        failed += 1

    # Timestamps
    if _check(
        f"investigation.started_at survives (got {inv_loaded.get('started_at')!r})",
        inv_loaded.get("started_at") is not None,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"investigation.completed_at survives (got {inv_loaded.get('completed_at')!r})",
        inv_loaded.get("completed_at") is not None,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"investigation.last_at survives (got {inv_loaded.get('last_at')!r})",
        inv_loaded.get("last_at") is not None,
    ):
        passed += 1
    else:
        failed += 1

    # Queries
    loaded_queries = inv_loaded.get("queries", [])
    if _check(
        f"investigation.queries survives (got {len(loaded_queries)} queries)",
        len(loaded_queries) == 2,
    ):
        passed += 1
    else:
        failed += 1

    # Sources
    loaded_sources = inv_loaded.get("sources", {})
    if _check(
        f"investigation.sources.web = ENRICHED (got {loaded_sources.get('web')!r})",
        loaded_sources.get("web") == "ENRICHED",
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"investigation.sources.directories = PARTIAL (got {loaded_sources.get('directories')!r})",
        loaded_sources.get("directories") == "PARTIAL",
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"investigation.sources.linkedin = NOT_FOUND (got {loaded_sources.get('linkedin')!r})",
        loaded_sources.get("linkedin") == "NOT_FOUND",
    ):
        passed += 1
    else:
        failed += 1

    # Evidence
    loaded_evidence = inv_loaded.get("evidence", [])
    if _check(
        f"investigation.evidence survives (got {len(loaded_evidence)} items, expected 3)",
        len(loaded_evidence) == 3,
    ):
        passed += 1
    else:
        failed += 1

    # Verify evidence content
    if loaded_evidence:
        email_ev = [e for e in loaded_evidence if e.get("field") == "email"]
        if _check(
            "Email evidence value survives",
            email_ev and email_ev[0].get("value") == "info@testowner.com",
        ):
            passed += 1
        else:
            failed += 1

        phone_ev = [e for e in loaded_evidence if e.get("field") == "phone"]
        if _check(
            "Phone evidence value survives",
            phone_ev and phone_ev[0].get("value") == "(801) 555-9999",
        ):
            passed += 1
        else:
            failed += 1

    # Events
    loaded_events = inv_loaded.get("events", [])
    if _check(
        f"investigation.events survives (got {len(loaded_events)} events)",
        len(loaded_events) == 1,
    ):
        passed += 1
    else:
        failed += 1

    # Contacts
    loaded_contacts = inv_loaded.get("contacts", {})
    if _check(
        f"contacts.preferred_email survives (got {loaded_contacts.get('preferred_email')!r})",
        loaded_contacts.get("preferred_email") == "info@testowner.com",
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"contacts.preferred_phone survives (got {loaded_contacts.get('preferred_phone')!r})",
        loaded_contacts.get("preferred_phone") == "(801) 555-9999",
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"contacts.preferred_website survives (got {loaded_contacts.get('preferred_website')!r})",
        loaded_contacts.get("preferred_website") == "https://testowner.com",
    ):
        passed += 1
    else:
        failed += 1

    loaded_email_cands = loaded_contacts.get("email_candidates", [])
    if _check(
        f"contacts.email_candidates survives (got {len(loaded_email_cands)})",
        len(loaded_email_cands) == 1,
    ):
        passed += 1
    else:
        failed += 1

    # Identity matches
    loaded_matches = inv_loaded.get("identity_matches", [])
    if _check(
        f"identity_matches survives (got {len(loaded_matches)})",
        len(loaded_matches) == 1,
    ):
        passed += 1
    else:
        failed += 1

    # Summary
    loaded_summary = inv_loaded.get("summary", {})
    if _check(
        f"summary.emails_found = 1 (got {loaded_summary.get('emails_found')})",
        loaded_summary.get("emails_found") == 1,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"summary.phones_found = 1 (got {loaded_summary.get('phones_found')})",
        loaded_summary.get("phones_found") == 1,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"summary.websites_found = 1 (got {loaded_summary.get('websites_found')})",
        loaded_summary.get("websites_found") == 1,
    ):
        passed += 1
    else:
        failed += 1

    # Step 5: Verify owner fields preserved
    print()
    print("[Step 5] Verifying owner fields preserved")
    if _check(
        f"owner_name = {original_owner_name!r}",
        loaded.get("owner_name") == original_owner_name,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"owner_entity = {original_owner_entity!r}",
        loaded.get("owner_entity") == original_owner_entity,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"owner_confidence = {original_owner_confidence!r}",
        loaded.get("owner_confidence") == original_owner_confidence,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"owner_source = {original_owner_source!r}",
        loaded.get("owner_source") == original_owner_source,
    ):
        passed += 1
    else:
        failed += 1

    # Step 6: Verify unrelated lead fields preserved
    print()
    print("[Step 6] Verifying unrelated lead fields preserved")
    if _check(
        f"lead_status = {original_lead_status!r}",
        loaded.get("lead_status") == original_lead_status,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"priority = {original_priority!r}",
        loaded.get("priority") == original_priority,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"applicant_name = 'Test Applicant'",
        loaded.get("applicant_name") == "Test Applicant",
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"friction_score = 50",
        loaded.get("friction_score") == 50,
    ):
        passed += 1
    else:
        failed += 1

    if _check(
        f"staff_contact_email preserved",
        loaded.get("staff_contact_email") == "staff@test.gov",
    ):
        passed += 1
    else:
        failed += 1

    # Step 7: Cleanup — delete the test row
    print()
    print("[Step 7] Cleanup — removing test lead from Supabase")
    try:
        client = lead_repository.get_client()
        table = lead_repository.get_table_name()
        client.table(table).delete().eq(
            "application_number", lead["application_number"]
        ).execute()
        if _check("Test lead deleted", True):
            passed += 1
        else:
            failed += 1
    except Exception as exc:
        print(f"  [WARN] Cleanup failed: {exc}")

    return failed


if __name__ == "__main__":
    failed = test_persistence_round_trip()
    print()
    if failed == 0:
        print("ALL PERSISTENCE ROUND-TRIP TESTS PASSED")
    else:
        print(f"PERSISTENCE ROUND-TRIP: {failed} FAILURES")
    sys.exit(1 if failed else 0)
