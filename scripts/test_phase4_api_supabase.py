"""
PermitSignal Phase 4 Tests -- API & Supabase Intelligence Exposure

Targets the two new Phase 4 retrieval endpoints (GET /leads,
GET /leads/{application_number}) plus the read functions they are built
on (backend.app.services.lead_repository.fetch_lead()/fetch_leads(),
backend.app.services.case_report_generator.load_lead_queue()).

Sections [1/12]-[9/12] are deterministic (mocked Supabase/JSON boundaries,
no network, no real Supabase writes). Sections [10/12]-[12/12] exercise
the REAL pipeline -> Supabase -> API path against the real Provo packet,
per CLAUDE.md section 10 (Testing Rules) and the Phase 4 spec's "REAL
PROVO VERIFICATION" requirement. They run only when SUPABASE_URL/
SUPABASE_KEY are actually configured in this environment (they degrade to
a printed SKIP, never a failure, when they are not) -- consistent with
lead_repository.is_configured()'s role everywhere else in this project.

Run from the project root:

    python -m scripts.test_phase4_api_supabase
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

# Force lead_repository's module-level load_dotenv() to run exactly once,
# right here -- same reasoning as scripts/test_pipeline_orchestrator.py.
import backend.app.services.lead_repository  # noqa: F401

from backend.app.main import app
from backend.app.services import (
    case_report_generator,
    lead_repository,
    pipeline_orchestrator,
)


client = TestClient(app)

SAMPLE_LEAD: dict[str, Any] = {
    "opportunity_id": "plrz99990001",
    "application_number": "PLRZ99990001",
    "applicant_name": "Sample Applicant",
    "applicant_email": None,
    "applicant_phone": None,
    "application_type": "Zone Map Amendment",
    "project_address": "100 Sample Street",
    "neighborhood": "Sample Neighborhood",
    "description": "Sample rezone request.",
    "parcel_number": "12:345:6789",
    "acreage": "1.2",
    "zoning": "R1",
    "owner_name": "Sample Owner",
    "owner_entity": "Sample Owner LLC",
    "owner_type": "LLC",
    "owner_contact_name": "Sample Owner",
    "owner_contact_email": None,
    "owner_contact_phone": None,
    "owner_website": None,
    "owner_source": "government_record",
    "owner_confidence": "HIGH",
    "applicant_entity": None,
    "applicant_contact_name": None,
    "applicant_contact_email": None,
    "applicant_contact_phone": None,
    "applicant_source": None,
    "applicant_confidence": None,
    "parties": [
        {
            "party_name": "Sample Engineer",
            "party_role": "Engineer",
            "party_company": "Sample Engineering Co",
        }
    ],
    "staff_contact": "Sample Staff",
    "staff_contact_name": "Sample Staff",
    "staff_contact_email": "staff@sample.gov",
    "staff_contact_phone": None,
    "friction_score": 100,
    "friction_signals": ["denied"],
    "friction_events": [
        {"event_type": "denied", "event_date": "2025-12-02", "confidence": 0.9}
    ],
    "historical_evidence": [],
    "next_project_date": "2026-08-12",
    "next_project_event": "public_hearing",
    "next_project_time": "6:00 PM",
    "has_future_opportunity": True,
    "days_until_event": 11,
    "urgency": "SOON",
    "priority": "HIGH",
    "priority_score": 180,
    "is_actionable": True,
    "opportunity_reason": "HIGH opportunity: sample.",
    "source": "Provo Planning Commission",
    "source_url": "https://www.provo.gov/sample.pdf",
    "municipality": "Provo",
    "state": "Utah",
    "company_name": None,
    "company_website": None,
    "company_domain": None,
    "contact_name": None,
    "contact_role": None,
    "contact_email": None,
    "contact_phone": None,
    "linkedin_url": None,
    "email_source": None,
    "phone_source": None,
    "company_source": None,
    "contact_source": None,
    "email_confidence": None,
    "phone_confidence": None,
    "contact_confidence": None,
    "contact_is_public": None,
    "contact_is_verified": None,
    "identity_status": None,
    "enrichment_status": "disabled",
    "enrichment_method": None,
    "lead_status": "NO_CONTACT",
    "is_contactable": False,
    "approval_status": "denied",
    "approval_action": "no immediate action identified",
    "approval_action_type": "none",
    "approval_confidence": "HIGH",
    "approval_basis": "confirmed_requirement",
    "approval_relevant_date": "2025-12-02",
    "approval_source": "https://www.provo.gov/sample.pdf",
    "approval_source_type": "friction_analysis",
    "approval_evidence": "was denied by the Planning Commission.",
    "approval_reason": "Government record confirms the application was denied.",
}


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


class FakeExecuteResult:
    def __init__(self, data):
        self.data = data


class FakeSupabaseQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, _column, value):
        self._rows = [row for row in self._rows if row.get("application_number") == value]
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return FakeExecuteResult(self._rows)


class FakeSupabaseTable:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return FakeSupabaseQuery(list(self._rows))


def main():
    print("=" * 90)
    print("PERMITSIGNAL PHASE 4 -- API & SUPABASE INTELLIGENCE EXPOSURE")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/12] lead_repository.fetch_lead()/fetch_leads() -- not configured")

    with patch("backend.app.services.lead_repository.is_configured", return_value=False):
        results.append(
            check(
                lead_repository.fetch_lead("PLRZ99990001") is None,
                "fetch_lead() returns None when Supabase is not configured",
            )
        )
        results.append(
            check(
                lead_repository.fetch_leads() == [],
                "fetch_leads() returns [] when Supabase is not configured",
            )
        )

    # ------------------------------------------------------------------------
    print("\n[2/12] lead_repository.fetch_lead()/fetch_leads() -- configured, fake client")

    fake_rows = [
        {"application_number": "PLRZ99990001", "record": SAMPLE_LEAD},
        {"application_number": "PLRZ99990002", "record": {**SAMPLE_LEAD, "application_number": "PLRZ99990002"}},
    ]
    fake_client = FakeSupabaseTable(fake_rows)

    with patch("backend.app.services.lead_repository.is_configured", return_value=True):
        found = lead_repository.fetch_lead("PLRZ99990001", client=fake_client, table="leads")
        missing = lead_repository.fetch_lead("PLRZ00000000", client=fake_client, table="leads")
        all_leads = lead_repository.fetch_leads(client=fake_client, table="leads")

    results.append(
        check(found == SAMPLE_LEAD, "fetch_lead() returns the row's verbatim 'record' payload")
    )
    results.append(
        check(missing is None, "fetch_lead() returns None for a non-matching application_number")
    )
    results.append(
        check(len(all_leads) == 2, "fetch_leads() returns every row's 'record' payload")
    )

    # ------------------------------------------------------------------------
    print("\n[3/12] case_report_generator.load_lead_queue()")

    missing_path = "data/output/_phase4_test_missing_output.json"
    results.append(
        check(
            case_report_generator.load_lead_queue(missing_path) == [],
            "load_lead_queue() returns [] when the JSON artifact does not exist",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/12] Backward compatibility: existing endpoints unaffected")

    root_response = client.get("/")
    health_response = client.get("/health")

    results.append(check(root_response.status_code == 200, "GET / still returns 200"))
    results.append(check(health_response.status_code == 200, "GET /health still returns 200"))
    results.append(
        check(health_response.json().get("status") == "ok", "GET /health still reports ok")
    )

    # ------------------------------------------------------------------------
    print("\n[5/12] GET /leads/{application_number} -- not found anywhere -> 404")

    with patch("backend.app.services.lead_repository.is_configured", return_value=False), patch(
        "backend.app.services.case_report_generator.load_lead_by_application_number",
        return_value=None,
    ):
        response = client.get("/leads/PLDOESNOTEXIST")

    results.append(check(response.status_code == 404, "Unknown application_number returns 404"))

    # ------------------------------------------------------------------------
    print("\n[6/12] GET /leads/{application_number} -- JSON-artifact fallback")

    with patch("backend.app.services.lead_repository.is_configured", return_value=False), patch(
        "backend.app.services.case_report_generator.load_lead_by_application_number",
        return_value=SAMPLE_LEAD,
    ):
        response = client.get("/leads/PLRZ99990001")

    body = response.json()
    results.append(check(response.status_code == 200, "JSON-fallback retrieval returns 200"))
    results.append(check(body.get("source") == "json_output", "Reports source=json_output"))
    results.append(
        check(
            body.get("lead", {}).get("approval_status") == "denied"
            and body.get("lead", {}).get("owner_name") == "Sample Owner"
            and body.get("lead", {}).get("priority_score") == 180,
            "Complete intelligence payload preserved (approval, owner, priority)",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[7/12] GET /leads/{application_number} -- Supabase-primary retrieval")

    with patch("backend.app.services.lead_repository.is_configured", return_value=True), patch(
        "backend.app.services.lead_repository.fetch_lead",
        return_value=SAMPLE_LEAD,
    ), patch(
        "backend.app.services.case_report_generator.load_lead_by_application_number",
    ) as mock_json_fallback:
        response = client.get("/leads/PLRZ99990001")

    body = response.json()
    results.append(check(response.status_code == 200, "Supabase retrieval returns 200"))
    results.append(check(body.get("source") == "supabase", "Reports source=supabase"))
    results.append(
        check(not mock_json_fallback.called, "JSON fallback is not consulted when Supabase has the record")
    )

    # ------------------------------------------------------------------------
    print("\n[8/12] GET /leads/{application_number} -- invalid/malformed identifier")

    with patch("backend.app.services.lead_repository.is_configured", return_value=False), patch(
        "backend.app.services.case_report_generator.load_lead_by_application_number",
        return_value=None,
    ):
        response = client.get("/leads/not a real application number !!")

    results.append(
        check(response.status_code == 404, "Malformed identifier is treated as not-found, not a server error")
    )

    # ------------------------------------------------------------------------
    print("\n[9/12] GET /leads -- list retrieval, JSON fallback, filtering")

    queue = [
        {**SAMPLE_LEAD, "application_number": "PLLOW0001", "priority": "LOW", "priority_score": 10},
        {**SAMPLE_LEAD, "application_number": "PLHIGH0001", "priority": "HIGH", "priority_score": 180},
    ]

    with patch("backend.app.services.lead_repository.is_configured", return_value=False), patch(
        "backend.app.services.case_report_generator.load_lead_queue",
        return_value=queue,
    ):
        response = client.get("/leads")
        filtered_response = client.get("/leads", params={"priority": "high"})

    body = response.json()
    filtered_body = filtered_response.json()

    results.append(check(response.status_code == 200, "GET /leads returns 200"))
    results.append(check(body.get("source") == "json_output", "GET /leads reports source=json_output"))
    results.append(check(body.get("count") == 2, "GET /leads returns every lead"))
    results.append(
        check(
            body["leads"][0]["application_number"] == "PLHIGH0001",
            "GET /leads sorts HIGH priority first",
        )
    )
    results.append(
        check(
            filtered_body.get("count") == 1
            and filtered_body["leads"][0]["application_number"] == "PLHIGH0001",
            "GET /leads honors the priority filter",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[10/12] REAL Provo pipeline -> Supabase -> API consistency")

    if not lead_repository.is_configured():
        print("[SKIP] SUPABASE_URL/SUPABASE_KEY not configured in this environment")
    else:
        real_result = pipeline_orchestrator.run_and_save(
            pdf_path=pipeline_orchestrator.DEFAULT_PDF,
            reference_date=date(2026, 8, 1),
            live_enrichment=False,
            sync_to_supabase=True,
            verbose=False,
        )

        supabase_sync = real_result["metadata"]["supabase_sync"]
        results.append(
            check(
                supabase_sync.get("status") == "synced",
                "Real pipeline run reports a successful Supabase sync",
            )
        )

        pipeline_jared = next(
            o
            for o in real_result["opportunities"]
            if o.get("application_number") == "PLRZ20260264"
        )

        api_response = client.get("/leads/PLRZ20260264")
        api_body = api_response.json()
        api_lead = api_body.get("lead", {})

        results.append(check(api_response.status_code == 200, "API retrieves the real lead by application_number"))
        results.append(check(api_body.get("source") == "supabase", "Real retrieval is served from Supabase"))
        results.append(
            check(
                api_lead.get("applicant_name") == pipeline_jared.get("applicant_name")
                and api_lead.get("application_type") == pipeline_jared.get("application_type")
                and api_lead.get("priority") == pipeline_jared.get("priority")
                and api_lead.get("priority_score") == pipeline_jared.get("priority_score")
                and api_lead.get("next_project_date") == pipeline_jared.get("next_project_date")
                and api_lead.get("friction_score") == pipeline_jared.get("friction_score")
                and api_lead.get("approval_status") == pipeline_jared.get("approval_status")
                and api_lead.get("approval_action") == pipeline_jared.get("approval_action"),
                "Pipeline -> Supabase -> API preserves project, priority, "
                "friction, and approval-action intelligence without loss",
            )
        )

        # --------------------------------------------------------------------
        print("\n[11/12] REAL Provo pipeline: GET /leads list consistency")

        list_response = client.get("/leads")
        list_body = list_response.json()

        results.append(check(list_response.status_code == 200, "GET /leads returns 200 against real data"))
        results.append(check(list_body.get("source") == "supabase", "GET /leads is served from Supabase"))
        results.append(
            check(
                list_body.get("count", 0) >= 8,
                "GET /leads includes at least the 8 known real Provo opportunities",
            )
        )

        matching = [
            lead
            for lead in list_body.get("leads", [])
            if lead.get("application_number") == "PLRZ20260264"
        ]
        results.append(
            check(len(matching) == 1, "Idempotent upsert: exactly one row for PLRZ20260264 after re-ingest")
        )

        top_priorities = [lead.get("priority") for lead in list_body.get("leads", [])[:2]]
        results.append(
            check(
                top_priorities == ["HIGH", "HIGH"],
                "GET /leads list preserves HIGH-priority-first ordering",
            )
        )

        # --------------------------------------------------------------------
        print("\n[12/12] Idempotency: re-running the pipeline does not duplicate rows")

        second_result = pipeline_orchestrator.run_and_save(
            pdf_path=pipeline_orchestrator.DEFAULT_PDF,
            reference_date=date(2026, 8, 1),
            live_enrichment=False,
            sync_to_supabase=True,
            verbose=False,
        )

        results.append(
            check(
                second_result["metadata"]["supabase_sync"].get("status") == "synced",
                "Re-running the pipeline against the same packet syncs successfully again",
            )
        )

        recheck_response = client.get("/leads")
        recheck_body = recheck_response.json()
        recheck_matching = [
            lead
            for lead in recheck_body.get("leads", [])
            if lead.get("application_number") == "PLRZ20260264"
        ]
        results.append(
            check(
                len(recheck_matching) == 1,
                "Re-running the pipeline still produces exactly one row for "
                "PLRZ20260264 (application_number upsert, no duplication)",
            )
        )

    passed = sum(results)
    failed = len(results) - passed

    print("\n" + "=" * 90)
    print(f"TESTS: {passed} passed, {failed} failed")
    print("=" * 90)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
