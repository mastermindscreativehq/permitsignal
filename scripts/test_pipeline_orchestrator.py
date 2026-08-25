"""
PermitSignal Pipeline Orchestrator Tests

These tests target the CURRENT backend.app.services.pipeline_orchestrator
API. Sections [1/11]-[7/11] are deterministic (mocked service boundaries, no
PDF, no network). Sections [8/11]-[10/11] run the real production pipeline
against the real Provo packet, per DEVELOPMENT_RULES section 15
(Real-PDF Validation). Section [11/11] exercises Supabase lead persistence
via _persist_leads() directly. The disabled path runs for real (it never
even imports lead_repository). The "not configured" path forces
SUPABASE_URL/SUPABASE_KEY out of the environment for the duration of that
one call -- lead_repository.py loads .env on import, so this must not
assume the ambient environment is unconfigured, or this "deterministic"
test could perform a real network upsert against production Supabase. The
synced/error paths use a mocked lead_repository module.

Run from the project root:

    python -m scripts.test_pipeline_orchestrator
"""

import os
from datetime import date
from unittest.mock import patch

# Force lead_repository's module-level load_dotenv() to run exactly once,
# right here, rather than lazily inside pipeline_orchestrator's first real
# _import_service() call. Section [11/11] below deliberately pops
# SUPABASE_URL/SUPABASE_KEY from os.environ to test the "not configured"
# path -- if that were also the module's first import, load_dotenv() would
# silently repopulate those variables from .env after the pop and before
# is_configured() runs, turning a "deterministic" test into a real network
# call against production Supabase.
import backend.app.services.lead_repository  # noqa: F401

from backend.app.services import commercial_lead_intelligence, economic_intelligence, outreach_intelligence
from backend.app.services import address_intelligence
from backend.app.services import approval_stage_intelligence as action_stage_intelligence
from backend.app.services import pipeline_orchestrator as po
from backend.app.services.commercial_lead_intelligence import (
    READINESS_NEEDS_CONTACT_ENRICHMENT,
    READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
    READINESS_NOT_READY,
    READINESS_READY_FOR_OUTREACH,
)
from backend.app.services.pipeline_orchestrator import (
    DEFAULT_PDF,
    PRIORITY_ORDER,
    _adapt_dates,
    _deduplicate_applications,
    _enrich_applicants,
    _normalize_friction_record,
    _persist_leads,
    _sort_opportunities,
    _validate_batch,
    _validate_opportunity,
    run_pipeline,
)


REFERENCE_DATE = date(2026, 8, 1)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL PIPELINE ORCHESTRATOR")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/11] Application deduplication")

    records = [
        {"application_number": "PLRZ20260264", "applicant_name": "Jared Morgan"},
        {"application_number": "plrz20260264", "applicant_name": "Jared Morgan"},
        {"application_number": "PLCP20260261", "applicant_name": "Jared Morgan"},
    ]

    deduped = _deduplicate_applications(records)

    results.append(
        check(len(deduped) == 2, "Removes duplicate application numbers")
    )
    results.append(
        check(
            deduped[0]["application_number"] == "PLRZ20260264",
            "Preserves first canonical record",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[2/11] Friction record normalization")

    application = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
    }

    friction = {
        "friction_score": 100,
        "friction_signals": ["denied", "recommended_denial"],
        "friction_events": [
            {
                "event_type": "denied",
                "event_date": "2025-12-02",
            }
        ],
    }

    merged = _normalize_friction_record(application, friction)

    results.append(
        check(merged["friction_score"] == 100, "Carries friction score")
    )
    results.append(
        check(
            "denied" in merged["friction_signals"],
            "Carries friction signals",
        )
    )
    results.append(
        check(
            len(merged["friction_events"]) == 1,
            "Carries historical evidence events",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[3/11] Date adapter integration and historical-date safety")

    class FakeDateModule:
        @staticmethod
        def enrich_application_dates(application, text, reference_date):
            if application["application_number"] == "FUTURE":
                return {
                    **application,
                    "next_project_date": "2026-08-12",
                    "next_project_event": "public_hearing",
                    "next_project_time": "6:00 PM",
                    "has_future_opportunity": True,
                }
            # An administrative/historical date that has already passed
            # relative to the reference date must never survive as the
            # live next-event field (CLAUDE.md section 12 / DEVELOPMENT_RULES
            # section 6).
            return {
                **application,
                "next_project_date": "2026-01-01",
                "next_project_event": "public_hearing",
                "next_project_time": "6:00 PM",
                "has_future_opportunity": True,
            }

    def _fake_import_date_only(name):
        if name == po.PROJECT_DATE_MODULE:
            return FakeDateModule
        raise AssertionError(f"Unexpected module import: {name}")

    with patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import_date_only,
    ):
        date_results = _adapt_dates(
            [
                {"application_number": "FUTURE", "applicant_name": "Jared Morgan"},
                {"application_number": "PAST", "applicant_name": "Kevin Jimenez"},
            ],
            "Planning Commission public hearing August 12, 2026 at 6:00 PM.",
            REFERENCE_DATE,
        )

    future_record = next(r for r in date_results if r["application_number"] == "FUTURE")
    past_record = next(r for r in date_results if r["application_number"] == "PAST")

    results.append(
        check(
            future_record["next_project_date"] == "2026-08-12",
            "Date adapter carries a genuine future date",
        )
    )
    results.append(
        check(
            future_record["next_project_event"] == "public_hearing",
            "Date adapter carries event type",
        )
    )
    results.append(
        check(
            future_record["next_project_time"] == "6:00 PM",
            "Date adapter carries event time",
        )
    )
    results.append(
        check(
            future_record["has_future_opportunity"] is True,
            "Date adapter marks future opportunity",
        )
    )
    results.append(
        check(
            past_record["next_project_date"] is None
            and past_record["next_project_event"] is None
            and past_record["has_future_opportunity"] is False,
            "Date adapter clears a historical date from the live next-event field",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/11] Priority sorting")

    queue = [
        {"application_number": "LOW", "priority": "LOW", "priority_score": 40},
        {"application_number": "HIGH", "priority": "HIGH", "priority_score": 180},
        {"application_number": "MEDIUM", "priority": "MEDIUM", "priority_score": 90},
        {"application_number": "ARCHIVED", "priority": "ARCHIVED", "priority_score": 0},
    ]

    ordered = _sort_opportunities(queue)

    results.append(
        check(
            [x["application_number"] for x in ordered]
            == ["HIGH", "MEDIUM", "LOW", "ARCHIVED"],
            "Sorts production queue by priority",
        )
    )

    # ------------------------------------------------------------------------
    print(
        "\n[5/11] Applicant identity/contact enrichment orchestration "
        "(staff separation + government-record precedence)"
    )

    class FakeIdentityModule:
        @staticmethod
        def enrich_applicant_identity(application):
            # A real identity stage never touches contact fields it has no
            # evidence for; it only adds normalization/company context.
            return {
                "applicant_name": application.get("applicant_name"),
                "company_name": "Fake Identity Co",
                "identity_status": "identity_only",
            }

    class FakeEnrichmentModule:
        @staticmethod
        def enrich_applicant_contact(application, live_search=True):
            # Deliberately returns a DIFFERENT contact than any
            # government-record value, to prove the orchestrator enforces
            # precedence rather than trusting whatever enrichment returns.
            return {
                "applicant_email": "discovered@public-web.example",
                "applicant_phone": "(801) 555-9999",
                "contact_source": "official_company_website",
                "contact_confidence": 0.9,
                "enrichment_status": "enriched",
            }

    def _fake_import_identity_enrichment(name):
        mapping = {
            po.APPLICANT_IDENTITY_MODULE: FakeIdentityModule,
            po.APPLICANT_ENRICHMENT_MODULE: FakeEnrichmentModule,
        }
        return mapping[name]

    opportunities_in = [
        {
            "application_number": "PLGOV0001",
            "applicant_name": "Alex Gov Applicant",
            "applicant_email": "alex@government-record.example",
            "applicant_phone": "(801) 555-2000",
            "staff_contact_name": "Staff Person",
            "staff_contact_email": "staffperson@provo.gov",
        },
        {
            "application_number": "PLNOGOV0002",
            "applicant_name": "Jamie NoRecord Applicant",
        },
    ]

    with patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import_identity_enrichment,
    ):
        enriched = _enrich_applicants(opportunities_in, live_enrichment=True)

    gov_record = next(o for o in enriched if o["application_number"] == "PLGOV0001")
    no_record = next(o for o in enriched if o["application_number"] == "PLNOGOV0002")

    results.append(
        check(
            gov_record["applicant_email"] == "alex@government-record.example",
            "Government-record email is never overwritten by enrichment",
        )
    )
    results.append(
        check(
            gov_record["applicant_phone"] == "(801) 555-2000",
            "Government-record phone is never overwritten by enrichment",
        )
    )
    results.append(
        check(
            gov_record["email_source"] == "government_record",
            "Government-record email keeps its source label",
        )
    )
    results.append(
        check(
            gov_record["staff_contact_email"] == "staffperson@provo.gov",
            "Staff email is preserved",
        )
    )
    results.append(
        check(
            gov_record["staff_contact_email"] != gov_record["applicant_email"],
            "Staff email never leaks into applicant email",
        )
    )
    results.append(
        check(
            no_record["applicant_email"] == "discovered@public-web.example",
            "Public-web discovery populates contact only when no "
            "government record exists",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[6/11] Full pipeline with mocked service boundaries")

    SAMPLE_TEXT = (
        "Planning Commission public hearing August 12, 2026 at 6:00 PM."
    )

    class FakeApplicationModule:
        @staticmethod
        def extract_applications(text):
            return [
                {
                    "application_number": "PLRZ20260264",
                    "applicant_name": "Jared Morgan",
                    "applicant_email": None,
                    "applicant_phone": None,
                    "staff_contact_name": "Staff Person",
                    "staff_contact_email": "staffperson@provo.gov",
                    "application_type": "Zone Map Amendment",
                    "project_address": "113/191 N Geneva Road",
                    "neighborhood": "Fort Utah",
                },
                # Duplicate application number to confirm run_pipeline()
                # deduplicates even before friction/date/opportunity stages.
                {
                    "application_number": "PLRZ20260264",
                    "applicant_name": "Jared Morgan",
                },
                {
                    "application_number": "PLGOV0002",
                    "applicant_name": "Alex Gov Applicant",
                    "applicant_email": "alex@government-record.example",
                    "applicant_phone": "(801) 555-2000",
                    "application_type": "Variance",
                    "project_address": "1 Test Street",
                },
            ]

    class FakeFrictionModule:
        @staticmethod
        def analyze_applications(text, applications):
            return [
                {
                    "application_number": "PLRZ20260264",
                    "friction_score": 100,
                    "friction_signals": ["denied", "recommended_denial"],
                    "friction_events": [
                        {"event_type": "denied", "event_date": "2025-12-02"}
                    ],
                },
                {
                    "application_number": "PLGOV0002",
                    "friction_score": 0,
                    "friction_signals": [],
                    "friction_events": [],
                },
            ]

    class FakeDateModuleFull:
        @staticmethod
        def enrich_application_dates(application, text, reference_date):
            return {
                **application,
                "next_project_date": "2026-08-12",
                "next_project_event": "public_hearing",
                "next_project_time": "6:00 PM",
                "has_future_opportunity": True,
            }

    class FakeOpportunityModule:
        @staticmethod
        def build_opportunities(applications, reference_date=None):
            result = []
            for application in applications:
                friction_score = application.get("friction_score", 0)
                is_high = friction_score >= 70
                result.append(
                    {
                        **application,
                        "priority": "HIGH" if is_high else "MEDIUM",
                        "priority_score": 180 if is_high else 60,
                        "is_actionable": True,
                        "urgency": "SOON",
                        "days_until_event": 11,
                    }
                )
            return result

    class FakeIdentityModuleFull:
        @staticmethod
        def enrich_applicant_identity(application):
            return {
                "applicant_name": application.get("applicant_name"),
                "company_name": "Fake Identity Co",
                "identity_status": "identity_only",
            }

    class FakeEnrichmentModuleFull:
        @staticmethod
        def enrich_applicant_contact(application, live_search=True):
            return {
                "applicant_email": "should-not-be-used@public-web.example",
                "enrichment_status": "enriched",
            }

    class FakeApprovalModuleFull:
        @staticmethod
        def apply_approval_intelligence(opportunities):
            # Mirrors the real module's shape closely enough to prove the
            # pipeline wires this Phase 3 stage in without disturbing any
            # field an earlier stage already set.
            results = []
            for opportunity in opportunities:
                if opportunity.get("friction_score", 0) >= 70:
                    approval = {
                        "approval_status": "denied",
                        "approval_action": "no immediate action identified",
                    }
                else:
                    approval = {
                        "approval_status": "scheduled",
                        "approval_action": "attend scheduled hearing",
                    }
                results.append({**opportunity, **approval})
            return results

    class FakeIntelligenceEngineModule:
        @staticmethod
        def build_approval_intelligence(lead, reference_date=None):
            return {
                "version": "1.0",
                "status": "computed",
                "executive_diagnosis": "Test diagnosis",
                "approval_status": "PENDING",
                "approval_risk": "MEDIUM",
                "approval_readiness": "PARTIAL",
                "approval_blockers": [],
                "requirements": [],
                "recommended_actions": [],
                "stakeholders": [],
                "decision_path": [],
                "evidence": [],
                "pricing_inputs": {
                    "service_tier": "MONITORING",
                    "friction_score": lead.get("friction_score", 0),
                    "has_denial_history": False,
                    "has_future_event": bool(lead.get("has_future_opportunity")),
                    "complexity_tier": "medium",
                },
                "client_message": {"subject": "Test", "body": "Test"},
                "internal_strategy": {"assessment": "Test"},
                "model_warnings": [],
                "unresolved_questions": [],
            }

    class FakePricingEngineModule:
        @staticmethod
        def calculate_pricing(pricing_inputs):
            return {
                "fee_low": 150.0,
                "fee_high": 300.0,
                "recommended_fee": 225.0,
                "deposit_percent": 50,
                "deposit_amount": 112.5,
                "pricing_rationale": ["Test pricing"],
            }

    def _fake_import_full(name):
        mapping = {
            po.APPLICATION_EXTRACTOR_MODULE: FakeApplicationModule,
            po.FRICTION_ANALYZER_MODULE: FakeFrictionModule,
            po.PROJECT_DATE_MODULE: FakeDateModuleFull,
            po.OPPORTUNITY_MODULE: FakeOpportunityModule,
            po.APPLICANT_IDENTITY_MODULE: FakeIdentityModuleFull,
            po.APPLICANT_ENRICHMENT_MODULE: FakeEnrichmentModuleFull,
            po.APPROVAL_INTELLIGENCE_MODULE: FakeApprovalModuleFull,
            po.APPROVAL_INTELLIGENCE_ENGINE_MODULE: FakeIntelligenceEngineModule,
            po.PRICING_ENGINE_MODULE: FakePricingEngineModule,
            # Phase 6 commercial lead intelligence, Phase 8 outreach
            # intelligence, and Phase 9 economic intelligence are all
            # deterministic and have no PDF/network dependency, so the full
            # mocked pipeline runs the real modules rather than fakes --
            # this proves the actual wiring, not a stand-in for it.
            po.ECONOMIC_INTELLIGENCE_MODULE: economic_intelligence,
            po.COMMERCIAL_INTELLIGENCE_MODULE: commercial_lead_intelligence,
            po.OUTREACH_INTELLIGENCE_MODULE: outreach_intelligence,
            # Action Intelligence (contract v1.0) is deterministic with no
            # PDF/network dependency, so the full mocked pipeline runs the
            # real module -- proving the actual hook wiring.
            po.ACTION_STAGE_INTELLIGENCE_MODULE: action_stage_intelligence,
            # Address intelligence is deterministic (no network when
            # providers are not configured), so the full mocked pipeline
            # runs the real module.
            po.ADDRESS_INTELLIGENCE_MODULE: address_intelligence,
        }
        return mapping[name]

    with patch(
        "backend.app.services.pipeline_orchestrator._read_pdf_text",
        return_value=SAMPLE_TEXT,
    ), patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import_full,
    ):
        mocked_result = run_pipeline(
            "fake.pdf",
            reference_date=REFERENCE_DATE,
            live_enrichment=False,
            # A nonexistent path keeps this mocked section fully isolated
            # from whatever the real production JSON artifact
            # (data/output/permitsignal_opportunities.json) currently
            # contains on disk -- Phase 8's outreach-lifecycle lookup
            # (pipeline_orchestrator._load_previous_leads_by_number) reads
            # that file directly, not through the mocked _import_service.
            output_path="data/output/__test_pipeline_orchestrator_mocked__.json",
            verbose=False,
        )

    results.append(
        check(
            isinstance(mocked_result, dict)
            and set(mocked_result.keys())
            >= {"metadata", "applications", "opportunities", "lead_queue"},
            "Pipeline result contains the required output containers",
        )
    )
    results.append(
        check(
            len(mocked_result["applications"]) == 2,
            "Full pipeline deduplicates applications end to end",
        )
    )

    mocked_opportunities = mocked_result["opportunities"]
    mocked_jared = next(
        o for o in mocked_opportunities if o["application_number"] == "PLRZ20260264"
    )
    mocked_gov = next(
        o for o in mocked_opportunities if o["application_number"] == "PLGOV0002"
    )

    results.append(
        check(mocked_jared["friction_score"] == 100, "Pipeline carries friction score")
    )
    results.append(
        check(
            mocked_jared["next_project_date"] == "2026-08-12"
            and mocked_jared["next_project_event"] == "public_hearing"
            and mocked_jared["next_project_time"] == "6:00 PM",
            "Pipeline carries future project date/event/time",
        )
    )
    results.append(
        check(mocked_jared["priority"] == "HIGH", "Pipeline carries priority")
    )
    results.append(
        check(
            mocked_jared.get("approval_status") == "denied",
            "Pipeline applies approval-action intelligence (Phase 3) "
            "after friction/date/opportunity/enrichment stages",
        )
    )
    results.append(
        check(
            mocked_jared.get("company_name") == "Fake Identity Co",
            "Pipeline applies applicant identity enrichment",
        )
    )
    results.append(
        check(
            mocked_jared.get("enrichment_status") == "disabled",
            "Pipeline reports contact enrichment as disabled when "
            "live_enrichment=False",
        )
    )
    results.append(
        check(
            mocked_jared.get("commercial_readiness")
            in {
                READINESS_READY_FOR_OUTREACH,
                READINESS_NEEDS_CONTACT_ENRICHMENT,
                READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
                READINESS_NOT_READY,
            },
            "Pipeline applies commercial lead intelligence (Phase 6) "
            "after lead qualification, producing one of the four defined "
            "readiness states",
        )
    )
    results.append(
        check(
            bool(mocked_jared.get("recommended_commercial_action")),
            "Pipeline attaches a non-empty recommended commercial action",
        )
    )
    results.append(
        check(
            mocked_jared.get("outreach_status")
            in {
                outreach_intelligence.OUTREACH_STATUS_NEW,
                outreach_intelligence.OUTREACH_STATUS_QUALIFIED,
                outreach_intelligence.OUTREACH_STATUS_READY,
            },
            "Pipeline applies Phase 8 outreach intelligence (lifecycle "
            "status) after commercial lead intelligence",
        )
    )
    results.append(
        check(
            bool(mocked_jared.get("outreach_qualification_status")),
            "Pipeline attaches a non-empty outreach qualification status",
        )
    )
    results.append(
        check(
            mocked_gov["applicant_email"] == "alex@government-record.example",
            "Pipeline preserves government-record email through full run",
        )
    )
    results.append(
        check(
            mocked_jared["staff_contact_email"] != mocked_jared.get("applicant_email"),
            "Pipeline never assigns a staff email as the applicant email",
        )
    )

    mocked_lead_queue = mocked_result["lead_queue"]
    results.append(
        check(
            mocked_lead_queue[0]["application_number"] == "PLRZ20260264",
            "Lead queue ranks the high-friction opportunity first",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[7/11] Missing application_type does not fail validation or the batch")

    # Regression test for the real Provo failure: 5 of 19 live packets each
    # had exactly one opportunity whose government-record text used an
    # application_type phrasing extract_application_type() didn't recognize
    # (e.g. "General Plan Map Amendment" vs. the narrower "General Plan
    # Amendment" pattern). _validate_batch() previously raised PipelineError
    # for the entire document over that single field, discarding every
    # other valid opportunity in the same packet.
    results.append(
        check(
            _validate_opportunity(
                {
                    "application_number": "PLGPA20250235",
                    "applicant_name": "Brixton Capital",
                    "application_type": None,
                }
            )
            == [],
            "A record with only application_type missing has no validation errors",
        )
    )
    results.append(
        check(
            _validate_opportunity(
                {
                    "application_number": None,
                    "applicant_name": "Brixton Capital",
                    "application_type": "Zone Map Amendment",
                }
            )
            == ["missing application_number"],
            "application_number is still required (validation not weakened for unrelated fields)",
        )
    )
    results.append(
        check(
            _validate_opportunity(
                {
                    "application_number": "PLGPA20250235",
                    "applicant_name": None,
                    "application_type": "Zone Map Amendment",
                }
            )
            == ["missing applicant_name"],
            "applicant_name is still required (validation not weakened for unrelated fields)",
        )
    )

    mixed_batch = [
        {
            "application_number": "PLRZ20250236",
            "applicant_name": "Brixton Capital",
            "application_type": "Zone Map Amendment",
        },
        {
            # Mirrors the real _03112026-362.pdf failure: a legitimate
            # opportunity whose type phrase went unrecognized.
            "application_number": "PLGPA20250235",
            "applicant_name": "Brixton Capital",
            "application_type": None,
        },
    ]

    batch_error = None
    try:
        _validate_batch(mixed_batch)
    except Exception as exc:  # noqa: BLE001 - asserting no raise at all
        batch_error = exc

    results.append(
        check(
            batch_error is None,
            "A batch with one missing-application_type opportunity no longer "
            "raises PipelineError for the whole document",
        )
    )
    results.append(
        check(
            mixed_batch[1]["application_type"] is None,
            "The unresolved application_type is preserved as None, never fabricated",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[8/11] Real Provo packet: counts, priority, and project dates")

    real_result = run_pipeline(
        DEFAULT_PDF,
        reference_date=REFERENCE_DATE,
        live_enrichment=False,
        verbose=False,
    )

    real_applications = real_result["applications"]
    real_opportunities = real_result["opportunities"]
    real_lead_queue = real_result["lead_queue"]

    results.append(
        check(len(real_applications) == 8, "Real packet produces 8 applications")
    )
    results.append(
        check(len(real_opportunities) == 8, "Real packet produces 8 opportunities")
    )

    real_future_count = sum(
        1
        for o in real_opportunities
        if o.get("has_future_opportunity") is True
    )
    results.append(
        check(real_future_count == 8, "Real packet produces 8 future opportunities")
    )

    jared_records = [
        o
        for o in real_opportunities
        if o.get("application_number") == "PLRZ20260264"
    ]
    results.append(
        check(len(jared_records) == 1, "Jared Morgan's PLRZ20260264 is present")
    )

    jared = jared_records[0]
    results.append(
        check(jared["applicant_name"] == "Jared Morgan", "Applicant name preserved")
    )
    results.append(
        check(jared["priority"] == "HIGH", "Jared Morgan remains HIGH priority")
    )
    results.append(
        check(jared["priority_score"] == 180, "Jared Morgan keeps priority score 180")
    )
    results.append(
        check(
            jared["next_project_date"] == "2026-08-12",
            "next_project_date is 2026-08-12",
        )
    )
    results.append(
        check(
            jared["next_project_event"] == "public_hearing",
            "next_project_event is public_hearing",
        )
    )
    results.append(
        check(
            jared["next_project_time"] == "6:00 PM",
            "next_project_time is 6:00 PM",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[9/11] Real Provo packet: contact integrity and output structure")

    results.append(
        check(
            isinstance(real_result, dict)
            and set(real_result.keys())
            >= {"metadata", "applications", "opportunities", "lead_queue"},
            "Result contains the required output containers",
        )
    )
    results.append(
        check(
            len(real_lead_queue) == len(real_opportunities),
            "Lead queue contains every opportunity",
        )
    )

    ranks = [
        PRIORITY_ORDER.get(str(o.get("priority") or "LOW").upper(), 0)
        for o in real_lead_queue
    ]
    results.append(
        check(
            ranks == sorted(ranks, reverse=True),
            "Lead queue is sorted from highest to lowest priority",
        )
    )

    no_confusion = all(
        not (
            o.get("applicant_email")
            and o.get("staff_contact_email")
            and o.get("applicant_email") == o.get("staff_contact_email")
        )
        for o in real_opportunities
    )
    results.append(
        check(
            no_confusion,
            "No opportunity assigns a staff email as the applicant email",
        )
    )

    # Known worked example from CLAUDE.md section 7: Tyson Reynolds is the
    # applicant, Dustin Wright (dwright@provo.gov) is government staff.
    tyson_records = [
        o
        for o in real_opportunities
        if o.get("applicant_name") == "Tyson Reynolds"
    ]
    results.append(
        check(
            all(o.get("staff_contact_email") != "dwright@provo.gov"
                or o.get("applicant_email") is None
                for o in tyson_records),
            "Tyson Reynolds' applicant record never inherits staff "
            "Dustin Wright's email",
        )
    )

    no_fabrication = all(
        o.get("applicant_email") is None for o in real_opportunities
    )
    results.append(
        check(
            no_fabrication,
            "No opportunity has a fabricated applicant email "
            "(live_enrichment disabled, no government-record email present)",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[10/11] Real Provo packet: lead intelligence and queue stability")

    results.append(
        check(
            all("lead_status" in o and "is_contactable" in o for o in real_opportunities),
            "Every real opportunity carries lead_status and is_contactable",
        )
    )

    # No government-record contact and live enrichment disabled -> nothing
    # is contactable, and the friction/actionable/future-event records that
    # don't meet the qualification bar for a live lead are NOT falsely
    # marked ARCHIVED (they still have a future event).
    results.append(
        check(
            all(o.get("is_contactable") is False for o in real_opportunities),
            "No real opportunity is falsely marked contactable "
            "without evidence",
        )
    )
    results.append(
        check(
            all(o.get("lead_status") != "ARCHIVED" for o in real_opportunities),
            "No real opportunity is marked ARCHIVED "
            "(all 8 have a live future event)",
        )
    )

    jared_lead = next(
        o for o in real_opportunities if o.get("application_number") == "PLRZ20260264"
    )
    results.append(
        check(
            jared_lead.get("lead_status") == "NO_CONTACT",
            "Jared Morgan is a qualified HIGH-priority lead with no "
            "contact evidence yet (NO_CONTACT, not fabricated)",
        )
    )

    # Phase 6: commercial lead intelligence must be present on every real
    # opportunity, and must never claim readiness for outreach without
    # underlying contact evidence.
    results.append(
        check(
            all(
                "commercial_readiness" in o
                and "contactability_level" in o
                and "recommended_commercial_action" in o
                and "commercial_action_reason" in o
                for o in real_opportunities
            ),
            "Every real opportunity carries the four Phase 6 commercial "
            "fields",
        )
    )
    results.append(
        check(
            all(
                o.get("commercial_readiness") != READINESS_READY_FOR_OUTREACH
                for o in real_opportunities
                if not o.get("is_contactable")
            ),
            "No real opportunity is marked READY_FOR_OUTREACH without "
            "contactable evidence",
        )
    )
    results.append(
        check(
            jared_lead.get("commercial_readiness")
            == READINESS_NEEDS_CONTACT_ENRICHMENT,
            "Jared Morgan's NO_CONTACT lead maps to "
            "NEEDS_CONTACT_ENRICHMENT, not a fabricated READY_FOR_OUTREACH",
        )
    )

    # Phase 8: every real opportunity must carry outreach lifecycle fields,
    # and none may be fabricated into an advanced lifecycle stage.
    results.append(
        check(
            all(
                "outreach_status" in o and "outreach_qualification_status" in o
                for o in real_opportunities
            ),
            "Every real opportunity carries the Phase 8 outreach lifecycle "
            "fields",
        )
    )
    _VALID_OUTREACH_STATUSES = {
        outreach_intelligence.OUTREACH_STATUS_NEW,
        outreach_intelligence.OUTREACH_STATUS_QUALIFIED,
        outreach_intelligence.OUTREACH_STATUS_READY,
        outreach_intelligence.OUTREACH_STATUS_CONTACTED,
        outreach_intelligence.OUTREACH_STATUS_REPLIED,
        outreach_intelligence.OUTREACH_STATUS_ENGAGED,
        outreach_intelligence.OUTREACH_STATUS_OPPORTUNITY,
        outreach_intelligence.OUTREACH_STATUS_WON,
        outreach_intelligence.OUTREACH_STATUS_LOST,
    }
    _PRE_OUTREACH = {
        outreach_intelligence.OUTREACH_STATUS_NEW,
        outreach_intelligence.OUTREACH_STATUS_QUALIFIED,
        outreach_intelligence.OUTREACH_STATUS_READY,
    }

    results.append(
        check(
            all(o.get("outreach_status") in _VALID_OUTREACH_STATUSES for o in real_opportunities),
            "Every real opportunity's outreach_status is a valid lifecycle value",
        )
    )
    results.append(
        check(
            all(
                o.get("outreach_status") in _PRE_OUTREACH or o.get("outreach_events")
                for o in real_opportunities
            ),
            "No real opportunity is fabricated into an advanced lifecycle "
            "stage without a recorded controlled event -- this repo's "
            "shared production JSON/Supabase state may legitimately carry "
            "forward real outreach history from prior manual verification "
            "runs against the live Provo packet, which is expected",
        )
    )
    results.append(
        check(
            jared_lead.get("outreach_qualification_status")
            == outreach_intelligence.QUALIFICATION_QUALIFIED_NOT_CONTACTABLE,
            "Jared Morgan's NEEDS_CONTACT_ENRICHMENT readiness maps to "
            "QUALIFIED_NOT_CONTACTABLE, not a fabricated ready-for-outreach "
            "state",
        )
    )

    # The lead-intelligence stage must not disturb the existing priority
    # ordering: PLRZ20260264 and PLCP20260261 stay on top at HIGH/180.
    top_two = [
        (item.get("application_number"), item.get("priority"), item.get("priority_score"))
        for item in real_lead_queue[:2]
    ]
    results.append(
        check(
            top_two
            == [
                ("PLRZ20260264", "HIGH", 180),
                ("PLCP20260261", "HIGH", 180),
            ],
            "Lead intelligence preserves the existing top-two lead queue "
            "ordering (PLRZ20260264, PLCP20260261 both HIGH/180)",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[11/11] Supabase lead persistence (compatibility-layer safety)")

    sample_opportunities = [
        {"application_number": "PLRZ20260264", "applicant_name": "Jared Morgan"},
    ]

    disabled_status = _persist_leads(sample_opportunities, sync_to_supabase=False)

    results.append(
        check(
            disabled_status == {"status": "disabled"},
            "sync_to_supabase=False never attempts persistence",
        )
    )

    # Real lead_repository module, no mocking -- but SUPABASE_URL/KEY may
    # legitimately be present in this environment (lead_repository loads
    # .env on import), so the "not configured" path is forced deterministically
    # by clearing them for the duration of this one call. This must never
    # depend on the ambient environment, or this "deterministic" test could
    # silently perform a real network upsert against production Supabase.
    _original_supabase_url = os.environ.pop("SUPABASE_URL", None)
    _original_supabase_key = os.environ.pop("SUPABASE_KEY", None)

    try:
        skipped_status = _persist_leads(sample_opportunities, sync_to_supabase=True)
    finally:
        if _original_supabase_url is not None:
            os.environ["SUPABASE_URL"] = _original_supabase_url

        if _original_supabase_key is not None:
            os.environ["SUPABASE_KEY"] = _original_supabase_key

    results.append(
        check(
            skipped_status == {"status": "skipped", "reason": "not_configured"},
            "sync_to_supabase=True without Supabase configured degrades "
            "gracefully instead of crashing",
        )
    )

    class FakeSuccessRepository:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def upsert_leads(opportunities):
            return {"status": "synced", "rows": len(opportunities)}

    def _fake_import_success(name):
        if name == po.LEAD_REPOSITORY_MODULE:
            return FakeSuccessRepository
        raise AssertionError(f"Unexpected module import: {name}")

    with patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import_success,
    ):
        synced_status = _persist_leads(sample_opportunities, sync_to_supabase=True)

    results.append(
        check(
            synced_status == {"status": "synced", "rows": 1},
            "A configured, successful repository reports synced with a row count",
        )
    )

    class FakeFailingRepository:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def upsert_leads(opportunities):
            raise RuntimeError("simulated Supabase outage")

    def _fake_import_failing(name):
        if name == po.LEAD_REPOSITORY_MODULE:
            return FakeFailingRepository
        raise AssertionError(f"Unexpected module import: {name}")

    with patch(
        "backend.app.services.pipeline_orchestrator._import_service",
        side_effect=_fake_import_failing,
    ):
        error_status = _persist_leads(sample_opportunities, sync_to_supabase=True)

    results.append(
        check(
            error_status.get("status") == "error"
            and "simulated Supabase outage" in error_status.get("error", ""),
            "A repository failure is recorded as an error status, not raised",
        )
    )

    # The whole point of the compatibility layer: running the full,
    # real-PDF pipeline with the default sync_to_supabase=False must
    # produce metadata reporting persistence as disabled, and the JSON
    # output containers must be completely unaffected.
    results.append(
        check(
            real_result["metadata"]["supabase_sync"] == {"status": "disabled"},
            "Default pipeline run reports Supabase sync as disabled in metadata",
        )
    )
    results.append(
        check(
            set(real_result.keys()) == {"metadata", "applications", "opportunities", "lead_queue"},
            "JSON output container shape is unchanged by the persistence feature",
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
