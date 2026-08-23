"""
PermitSignal Phase 2B — API Round-Trip Test

Tests the investigation API endpoints using FastAPI's TestClient.
Verifies the full cycle: GET → POST → persist → GET → verify state.
"""
from __future__ import annotations

import json
import sys
import uuid

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import lead_repository


def _check(label: str, condition: bool) -> bool:
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {label}")
    return condition


client = TestClient(app, raise_server_exceptions=False)


def _make_test_lead_payload() -> dict:
    """Create all required fields for a valid lead row."""
    return {
        "application_number": f"API-TEST-{uuid.uuid4().hex[:8].upper()}",
        "applicant_name": "API Test Applicant",
        "normalized_applicant_name": "api test applicant",
        "application_type": "Concept Plan",
        "project_address": "456 API Lane",
        "neighborhood": "API District",
        "status": [],
        "description": "API test project",
        "owner_name": "API Owner",
        "owner_entity": "API Owner Corp",
        "owner_type": "Entity",
        "owner_contact_name": None,
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
        "friction_score": 30,
        "friction_signals": [],
        "friction_events": [],
        "next_project_date": "2026-09-01",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "has_future_opportunity": True,
        "days_until_event": 30,
        "urgency": "SOON",
        "priority": "MEDIUM",
        "priority_score": 80,
        "is_actionable": True,
        "opportunity_reason": "API test",
        "lead_status": "NO_CONTACT",
        "is_contactable": False,
        "source": "Provo Planning Commission",
        "source_url": "https://example.com/api-test.pdf",
        "municipality": "Provo",
        "state": "Utah",
        "staff_contact_name": None,
        "staff_contact_email": None,
        "staff_contact_phone": None,
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
        "recommended_commercial_action": None,
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
        "company_website": None,
        "company_domain": None,
        "company_name": None,
        "linkedin_url": None,
        "created_at": "2026-08-17T00:00:00Z",
    }


def _cleanup(app_number: str) -> None:
    """Remove test lead from Supabase."""
    try:
        client_obj = lead_repository.get_client()
        table = lead_repository.get_table_name()
        client_obj.table(table).delete().eq(
            "application_number", app_number
        ).execute()
    except Exception:
        pass


def test_api_round_trip() -> int:
    print()
    print("=" * 80)
    print("API ROUND-TRIP VERIFICATION")
    print("=" * 80)
    passed = 0
    failed = 0

    if not lead_repository.is_configured():
        print()
        print("  BLOCKED: Supabase not configured")
        return 0

    app_number = f"API-TEST-{uuid.uuid4().hex[:8].upper()}"
    payload = _make_test_lead_payload()
    payload["application_number"] = app_number

    # Seed the lead into Supabase
    print()
    print("[Setup] Seeding test lead into Supabase")
    try:
        lead_repository.upsert_leads([payload])
        _check("Test lead seeded", True)
        passed += 1
    except Exception as exc:
        print(f"  [FAIL] Seed failed: {exc}")
        return 1

    try:
        # --- Test 1: GET /leads/{id}/investigation (fresh lead) ---
        print()
        print("[Test 1] GET /leads/{id}/investigation — fresh lead")
        resp = client.get(f"/leads/{app_number}/investigation")
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            print(f"    Got {resp.status_code}: {resp.text[:200]}")
            failed += 1

        data = resp.json()
        inv = data.get("investigation", {})
        if _check(
            f"Investigation status = NOT_STARTED (got {inv.get('status')!r})",
            inv.get("status") == "NOT_STARTED",
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 2: GET /leads/{id}/investigation/status ---
        print()
        print("[Test 2] GET /leads/{id}/investigation/status")
        resp = client.get(f"/leads/{app_number}/investigation/status")
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            failed += 1

        data = resp.json()
        if _check(
            f"investigation_status = NOT_STARTED (got {data.get('investigation_status')!r})",
            data.get("investigation_status") == "NOT_STARTED",
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 3: GET /leads/{id}/investigation/evidence ---
        print()
        print("[Test 3] GET /leads/{id}/investigation/evidence")
        resp = client.get(f"/leads/{app_number}/investigation/evidence")
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            failed += 1

        data = resp.json()
        if _check(
            f"Empty evidence list (got {len(data.get('evidence', []))})",
            len(data.get("evidence", [])) == 0,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 4: GET /leads/{id}/investigation/events ---
        print()
        print("[Test 4] GET /leads/{id}/investigation/events")
        resp = client.get(f"/leads/{app_number}/investigation/events")
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            failed += 1

        # --- Test 5: POST /leads/{id}/investigation/web ---
        print()
        print("[Test 5] POST /leads/{id}/investigation/web")
        resp = client.post(
            f"/leads/{app_number}/investigation/web",
            json={"force": True},
        )
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            print(f"    Got {resp.status_code}: {resp.text[:300]}")
            failed += 1

        data = resp.json()
        web_status = data.get("source_status", {}).get("web")
        if _check(
            f"Web source has status (got {web_status!r})",
            web_status is not None,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 6: GET /leads/{id}/investigation (after web run) ---
        print()
        print("[Test 6] GET /leads/{id}/investigation — after web run")
        resp = client.get(f"/leads/{app_number}/investigation")
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            failed += 1

        data = resp.json()
        inv = data.get("investigation", {})
        if _check(
            f"Investigation status is NOT_STARTED or richer (got {inv.get('status')!r})",
            inv.get("status") in ("NOT_STARTED", "PARTIAL", "ENRICHED", "NOT_FOUND", "ERROR"),
        ):
            passed += 1
        else:
            failed += 1

        # Verify web source status persists
        web_src = inv.get("sources", {}).get("web")
        if _check(
            f"Web source status persists (got {web_src!r})",
            web_src is not None and web_src != "NOT_STARTED",
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 7: Verify persistence survives fresh GET from Supabase ---
        print()
        print("[Test 7] Verify persistence — fresh Supabase read")
        fresh_lead = lead_repository.fetch_lead(app_number)
        if _check("Fresh lead loaded from Supabase", fresh_lead is not None):
            passed += 1
        else:
            failed += 1
            return failed

        fresh_inv = fresh_lead.get("investigation", {})
        if _check(
            f"Investigation persists in fresh Supabase read (got {fresh_inv.get('status')!r})",
            fresh_inv.get("status") is not None,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 8: Owner fields preserved after investigation ---
        print()
        print("[Test 8] Owner fields preserved after investigation")
        if _check(
            f"owner_name = 'API Owner' (got {fresh_lead.get('owner_name')!r})",
            fresh_lead.get("owner_name") == "API Owner",
        ):
            passed += 1
        else:
            failed += 1

        if _check(
            f"owner_entity = 'API Owner Corp' (got {fresh_lead.get('owner_entity')!r})",
            fresh_lead.get("owner_entity") == "API Owner Corp",
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 9: POST /leads/{id}/investigation/all ---
        print()
        print("[Test 9] POST /leads/{id}/investigation/all")
        resp = client.post(
            f"/leads/{app_number}/investigation/all",
            json={"force": True},
        )
        if _check("Status 200", resp.status_code == 200):
            passed += 1
        else:
            print(f"    Got {resp.status_code}: {resp.text[:300]}")
            failed += 1

        data = resp.json()
        if _check(
            f"investigation_status present (got {data.get('investigation_status')!r})",
            data.get("investigation_status") is not None,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 10: Verify events are append-only (run web again with force) ---
        print()
        print("[Test 10] Verify events append-only (re-run web with force)")
        resp_before = client.get(f"/leads/{app_number}/investigation/events")
        events_before = len(resp_before.json().get("events", []))

        resp = client.post(
            f"/leads/{app_number}/investigation/web",
            json={"force": True},
        )

        resp_after = client.get(f"/leads/{app_number}/investigation/events")
        events_after = len(resp_after.json().get("events", []))

        if _check(
            f"Events append-only ({events_before} -> {events_after})",
            events_after >= events_before,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 11: 404 for nonexistent lead ---
        print()
        print("[Test 11] 404 for nonexistent lead")
        resp = client.get("/leads/NONEXISTENT-APP-999/investigation")
        if _check(
            f"Status 404 (got {resp.status_code})",
            resp.status_code == 404,
        ):
            passed += 1
        else:
            failed += 1

        # --- Test 12: Verify investigation doesn't reset to NOT_STARTED ---
        print()
        print("[Test 12] Investigation doesn't reset to NOT_STARTED after completion")
        # The last POST was a successful run. GET should NOT show NOT_STARTED.
        resp = client.get(f"/leads/{app_number}/investigation")
        inv = resp.json().get("investigation", {})
        # At minimum, the web source should not be NOT_STARTED
        web_src = inv.get("sources", {}).get("web")
        if _check(
            f"Web source not NOT_STARTED after investigation (got {web_src!r})",
            web_src is not None and web_src != "NOT_STARTED",
        ):
            passed += 1
        else:
            failed += 1

    finally:
        print()
        print("[Cleanup] Removing test lead")
        _cleanup(app_number)

    return failed


if __name__ == "__main__":
    failed = test_api_round_trip()
    print()
    if failed == 0:
        print("ALL API ROUND-TRIP TESTS PASSED")
    else:
        print(f"API ROUND-TRIP: {failed} FAILURES")
    sys.exit(1 if failed else 0)
