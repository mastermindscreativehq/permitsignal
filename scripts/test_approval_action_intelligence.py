"""
PermitSignal Approval-Action Intelligence Tests (Phase 3)

Targets backend.app.services.approval_action_intelligence directly. Every
scenario below is deterministic (no PDF, no network) -- it hands the
module the same *shape* of already-computed opportunity fields the real
pipeline would have produced by the time this stage runs (friction_signals/
friction_events from friction_analyzer, next_project_date/event/time from
project_date_extractor, current-item status from application_extractor).

Run from the project root:

    python -m scripts.test_approval_action_intelligence
"""

from datetime import date
from pathlib import Path

from backend.app.services.approval_action_intelligence import (
    BASIS_CONFIRMED,
    BASIS_INFERRED,
    BASIS_RECOMMENDATION,
    BASIS_UNKNOWN,
    apply_approval_intelligence,
    build_approval_action,
)
from backend.app.services.pipeline_orchestrator import DEFAULT_PDF, run_pipeline


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL APPROVAL-ACTION INTELLIGENCE")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/10] Clearly supported approval action (denied, no appeal)")

    denied_opportunity = {
        "application_number": "PLTEST0001",
        "friction_signals": ["denied", "recommended_denial"],
        "friction_events": [
            {
                "event_type": "recommended_denial",
                "event_date": "2025-11-12",
                "confidence": 0.9,
                "evidence": "was recommended denial by the Planning Commission on November 12, 2025.",
            },
            {
                "event_type": "denied",
                "event_date": "2025-12-02",
                "confidence": 0.95,
                "evidence": "the request was ultimately denied by the Municipal Council on December 2, 2025.",
            },
        ],
        "has_future_opportunity": False,
        "source_url": "https://example.gov/agenda",
    }

    denied_result = build_approval_action(denied_opportunity)

    results.append(
        check(
            denied_result["approval_action"] == "no immediate action identified",
            "Denied application with no appeal -> no immediate action identified",
        )
    )
    results.append(
        check(
            denied_result["approval_basis"] == BASIS_CONFIRMED,
            "Denial action basis is confirmed_requirement",
        )
    )
    results.append(
        check(
            denied_result["approval_confidence"] == "HIGH",
            "Denial action confidence is HIGH",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[2/10] Clearly supported approval status (denied)")

    results.append(
        check(
            denied_result["approval_status"] == "denied",
            "Approval status is denied",
        )
    )
    results.append(
        check(
            denied_result["approval_relevant_date"] == "2025-12-02",
            "Relevant date is the denial event date, not the earlier "
            "recommendation date",
        )
    )
    results.append(
        check(
            denied_result["approval_evidence"] is not None
            and "denied" in denied_result["approval_evidence"].lower(),
            "Evidence text is the actual denial evidence snippet",
        )
    )

    # ------------------------------------------------------------------------
    print(
        "\n[3/10] Explicit government requirement (staff recommended denial "
        "+ scheduled hearing)"
    )

    recommended_denial_opportunity = {
        "application_number": "PLTEST0003",
        "friction_signals": ["recommended_denial"],
        "friction_events": [
            {
                "event_type": "recommended_denial",
                "event_date": "2026-07-01",
                "confidence": 0.9,
                "evidence": "was recommended denial by the Planning Commission on July 1, 2026.",
            }
        ],
        "has_future_opportunity": True,
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "days_until_event": 20,
        "source_url": "https://example.gov/agenda",
    }

    recommended_result = build_approval_action(recommended_denial_opportunity)

    results.append(
        check(
            recommended_result["approval_status"] == "recommended_denial",
            "Status reflects the explicit staff recommendation",
        )
    )
    results.append(
        check(
            recommended_result["approval_action"] == "prepare for hearing",
            "Action is prepare for hearing (20 days out)",
        )
    )
    results.append(
        check(
            recommended_result["approval_basis"] == BASIS_RECOMMENDATION,
            "Basis is evidence_backed_recommendation, not a confirmed "
            "requirement (the ACTION is PermitSignal's synthesis, even "
            "though the underlying recommendation is explicit)",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/10] Hearing/decision evidence (clean scheduled hearing, no friction)")

    scheduled_opportunity = {
        "application_number": "PLTEST0004",
        "friction_signals": [],
        "friction_events": [],
        "has_future_opportunity": True,
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "days_until_event": 5,
        "future_project_dates": [
            {
                "value": "2026-08-12",
                "label": "public_hearing",
                "context": "The Planning Commission will hold a public hearing on August 12, 2026 at 6:00 PM.",
                "confidence": 0.95,
                "time": "6:00 PM",
            }
        ],
        "source_url": "https://example.gov/agenda",
    }

    scheduled_result = build_approval_action(scheduled_opportunity)

    results.append(
        check(
            scheduled_result["approval_status"] == "scheduled",
            "Clean scheduled hearing produces status=scheduled",
        )
    )
    results.append(
        check(
            scheduled_result["approval_action"] == "attend scheduled hearing",
            "Imminent hearing (5 days) produces attend scheduled hearing",
        )
    )
    results.append(
        check(
            scheduled_result["approval_basis"] == BASIS_CONFIRMED,
            "A labeled public hearing date is a confirmed government-record fact",
        )
    )
    results.append(
        check(
            scheduled_result["approval_evidence"] is not None
            and "public hearing" in scheduled_result["approval_evidence"].lower(),
            "Evidence text is the real project-date-extractor context, not fabricated",
        )
    )
    results.append(
        check(
            scheduled_result["approval_source_type"] == "project_date_extraction",
            "Source type correctly attributes the evidence to date extraction",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[5/10] Ambiguous approval information (opposition, no schedule)")

    ambiguous_opportunity = {
        "application_number": "PLTEST0005",
        "friction_signals": ["public_opposition"],
        "friction_events": [
            {
                "event_type": "public_opposition",
                "event_date": None,
                "confidence": 0.6,
                "evidence": "Members of the public opposed the request at the hearing.",
            }
        ],
        "has_future_opportunity": False,
        "source_url": "https://example.gov/agenda",
    }

    ambiguous_result = build_approval_action(ambiguous_opportunity)

    results.append(
        check(
            ambiguous_result["approval_status"] == "under_review",
            "Opposition with no scheduled next step -> under_review, not "
            "denied/approved",
        )
    )
    results.append(
        check(
            ambiguous_result["approval_basis"] == BASIS_INFERRED,
            "Ambiguous evidence is marked as an inferred next step, not "
            "a confirmed requirement",
        )
    )
    results.append(
        check(
            ambiguous_result["approval_confidence"] == "LOW",
            "Ambiguous evidence carries LOW confidence",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[6/10] Insufficient evidence")

    empty_opportunity = {
        "application_number": "PLTEST0006",
        "friction_signals": [],
        "friction_events": [],
        "has_future_opportunity": False,
    }

    empty_result = build_approval_action(empty_opportunity)

    results.append(
        check(
            empty_result["approval_status"] == "unknown",
            "No evidence at all -> approval_status is unknown",
        )
    )
    results.append(
        check(
            empty_result["approval_action"] == "unknown",
            "No evidence at all -> approval_action is unknown",
        )
    )
    results.append(
        check(
            empty_result["approval_basis"] == BASIS_UNKNOWN,
            "No evidence at all -> basis is unknown",
        )
    )
    results.append(
        check(
            empty_result["approval_confidence"] is None,
            "No evidence at all -> confidence is None (not a fabricated LOW)",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[7/10] False-positive approval language (boilerplate text)")

    boilerplate_opportunity = {
        "application_number": "PLTEST0007",
        "description": (
            "Decisions of the Planning Commission may be appealed within "
            "ten days of the decision. Possible motions and findings: "
            "1. Recommend approval. 2. Recommend denial. 3. Continue."
        ),
        "friction_signals": [],
        "friction_events": [],
        "has_future_opportunity": False,
    }

    boilerplate_result = build_approval_action(boilerplate_opportunity)

    results.append(
        check(
            boilerplate_result["approval_status"] == "unknown",
            "Boilerplate procedural language in description never "
            "fabricates a denied/appeal/continued status -- the module "
            "only reads friction_signals/friction_events, never raw text",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[8/10] Unsupported inferred requirements (continued, no confirmed date)")

    continued_opportunity = {
        "application_number": "PLTEST0008",
        "status": ["continued"],
        "friction_signals": [],
        "friction_events": [],
        "has_future_opportunity": False,
    }

    continued_result = build_approval_action(continued_opportunity)

    results.append(
        check(
            continued_result["approval_status"] == "continued",
            "Current-item CONTINUED marker is recognized",
        )
    )
    results.append(
        check(
            continued_result["approval_basis"] == BASIS_INFERRED,
            "Continued with no confirmed next date is inferred_next_step, "
            "never confirmed_requirement",
        )
    )
    results.append(
        check(
            continued_result["approval_action"] == "monitor the next decision",
            "No specific hearing-prep action is claimed without a "
            "confirmed date",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[9/10] Regression: Phase 1/Phase 2 fields untouched")

    phase2_opportunity = {
        "application_number": "PLTEST0009",
        "applicant_name": "Test Applicant",
        "applicant_email": "gov@example.gov",
        "owner_name": "Test Owner LLC",
        "owner_source": "government_record",
        "owner_confidence": "HIGH",
        "parties": [{"party_name": "Test Engineer", "party_role": "Engineer"}],
        "friction_signals": [],
        "friction_events": [],
        "has_future_opportunity": False,
    }

    phase2_batch = apply_approval_intelligence([phase2_opportunity])
    phase2_result = phase2_batch[0]

    results.append(
        check(
            phase2_result["owner_name"] == "Test Owner LLC"
            and phase2_result["owner_source"] == "government_record"
            and phase2_result["applicant_email"] == "gov@example.gov"
            and phase2_result["parties"] == phase2_opportunity["parties"],
            "Owner/person enrichment (Phase 2) and applicant contact "
            "fields survive approval-action intelligence unchanged",
        )
    )
    results.append(
        check(
            "approval_status" in phase2_result,
            "Approval-action fields are additively attached",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[10/10] Idempotent repeated processing")

    first_pass = apply_approval_intelligence([denied_opportunity])[0]
    second_pass = apply_approval_intelligence([first_pass])[0]

    approval_keys = [
        "approval_status",
        "approval_action",
        "approval_action_type",
        "approval_confidence",
        "approval_basis",
        "approval_relevant_date",
        "approval_source",
        "approval_source_type",
        "approval_evidence",
        "approval_reason",
    ]

    results.append(
        check(
            all(first_pass[key] == second_pass[key] for key in approval_keys),
            "Re-running approval-action intelligence on an already-"
            "processed opportunity produces identical results (idempotent)",
        )
    )

    # ------------------------------------------------------------------------
    # Regression: a terminal friction signal (denied/withdrawn) can describe
    # a PAST submission cycle for the same application, while the current
    # cycle has its own live scheduled hearing or future date. The action
    # must reflect what is actually next, not claim "no further government
    # action is currently on record" when a hearing/future date proves
    # otherwise. Mirrors the real production case: PLRZ20260264 (Jared
    # Morgan) was denied on 2025-12-02 for a prior rezone request, but has
    # its own public_hearing scheduled 2026-08-12.
    # ------------------------------------------------------------------------
    print("\n[Regression] Denied application with a newly scheduled hearing")

    denied_with_hearing_opportunity = {
        "application_number": "PLTEST0010",
        "friction_signals": ["denied", "recommended_denial"],
        "friction_events": [
            {
                "event_type": "denied",
                "event_date": "2025-12-02",
                "confidence": 0.95,
                "evidence": "the request was ultimately denied by the Municipal Council on December 2, 2025.",
            },
        ],
        "has_future_opportunity": True,
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "days_until_event": 11,
        "source_url": "https://example.gov/agenda",
    }

    denied_with_hearing_result = build_approval_action(denied_with_hearing_opportunity)

    results.append(
        check(
            denied_with_hearing_result["approval_status"] == "denied",
            "Prior denial is still recorded as the historical status, not erased",
        )
    )
    results.append(
        check(
            denied_with_hearing_result["approval_action"] == "prepare for hearing",
            "A newly scheduled hearing produces a real next action, not "
            "'no immediate action identified'",
        )
    )
    results.append(
        check(
            "no further government action is currently on record"
            not in (denied_with_hearing_result["approval_reason"] or ""),
            "Reason never claims no further action is on record when a "
            "hearing is actually scheduled",
        )
    )
    results.append(
        check(
            "2026-08-12" in (denied_with_hearing_result["approval_reason"] or ""),
            "Reason references the newly scheduled hearing date",
        )
    )
    results.append(
        check(
            denied_with_hearing_result["approval_basis"] == BASIS_CONFIRMED,
            "A labeled scheduled hearing is a confirmed government-record fact",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[Regression] Denied application with a future non-hearing date")

    denied_with_future_opportunity = {
        "application_number": "PLTEST0011",
        "friction_signals": ["denied"],
        "friction_events": [
            {
                "event_type": "denied",
                "event_date": "2025-12-02",
                "confidence": 0.95,
                "evidence": "the request was denied by the Municipal Council on December 2, 2025.",
            },
        ],
        "has_future_opportunity": True,
        "next_project_date": "2026-09-02",
        "next_project_event": "future_project_event",
        "days_until_event": 32,
        "source_url": "https://example.gov/agenda",
    }

    denied_with_future_result = build_approval_action(denied_with_future_opportunity)

    results.append(
        check(
            denied_with_future_result["approval_action"] == "monitor the next decision",
            "A future non-hearing date after a denial produces monitoring, "
            "not 'no immediate action identified'",
        )
    )
    results.append(
        check(
            denied_with_future_result["approval_basis"] == BASIS_RECOMMENDATION,
            "A future non-hearing date after a denial is a recommendation, "
            "not a confirmed requirement",
        )
    )
    results.append(
        check(
            "no further government action is currently on record"
            not in (denied_with_future_result["approval_reason"] or ""),
            "Reason never claims no further action is on record when a "
            "future date is actually on record",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[Regression] Withdrawn application with a newly scheduled hearing")

    withdrawn_with_hearing_opportunity = {
        "application_number": "PLTEST0012",
        "friction_signals": ["withdrawn"],
        "friction_events": [
            {
                "event_type": "withdrawn",
                "event_date": "2025-10-01",
                "confidence": 0.9,
                "evidence": "the application was withdrawn by the applicant on October 1, 2025.",
            },
        ],
        "has_future_opportunity": True,
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "days_until_event": 3,
        "source_url": "https://example.gov/agenda",
    }

    withdrawn_with_hearing_result = build_approval_action(withdrawn_with_hearing_opportunity)

    results.append(
        check(
            withdrawn_with_hearing_result["approval_status"] == "withdrawn",
            "Prior withdrawal is still recorded as the historical status, not erased",
        )
    )
    results.append(
        check(
            withdrawn_with_hearing_result["approval_action"] == "attend scheduled hearing",
            "An imminent newly scheduled hearing (3 days) produces 'attend "
            "scheduled hearing', not 'no immediate action identified'",
        )
    )
    results.append(
        check(
            "no further action is currently on record"
            not in (withdrawn_with_hearing_result["approval_reason"] or ""),
            "Reason never claims no further action is on record when a "
            "hearing is actually scheduled",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[Regression] Real Provo packet: PLRZ20260264 resubmission after a prior denial")

    if not Path(DEFAULT_PDF).exists():
        print("Skipping real-packet section: PDF not present.")
    else:
        real_result = run_pipeline(
            pdf_path=DEFAULT_PDF,
            reference_date=date(2026, 8, 1),
            live_enrichment=False,
            sync_to_supabase=False,
            verbose=False,
        )

        by_number = {o["application_number"]: o for o in real_result["opportunities"]}
        morgan_rezone = by_number.get("PLRZ20260264")
        morgan_concept = by_number.get("PLCP20260261")

        for label, morgan in (("PLRZ20260264", morgan_rezone), ("PLCP20260261", morgan_concept)):
            results.append(
                check(
                    bool(morgan) and morgan.get("has_future_opportunity") is True,
                    f"Real packet sanity check: {label} still has a live future opportunity",
                )
            )
            results.append(
                check(
                    bool(morgan)
                    and "no further government action is currently on record"
                    not in (morgan.get("approval_reason") or ""),
                    f"Real packet: {label} (denied historically, but with a live scheduled "
                    "hearing) never claims no further government action is on record",
                )
            )
            results.append(
                check(
                    bool(morgan) and morgan.get("approval_action") != "no immediate action identified",
                    f"Real packet: {label} gets a real next action, reflecting its live "
                    "scheduled hearing, not the prior denial's terminal action",
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
