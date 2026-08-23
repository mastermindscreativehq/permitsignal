"""
Step 4 deterministic tests: DecisionStageResolver.

Contract: docs/specs/action_intelligence_contract_v1.md
Real-case ground truth: PLRZ20260264 (Provo, Aug 12 2026 packet).
Run: python -m scripts.test_action_decision
"""
import json
import sys

from backend.app.services.approval_stage_intelligence import (
    DECISION_STAGES,
    build_decision_stage,
)
from scripts.test_action_conditions import (
    REAL_APPROVAL_EVIDENCE,
    REAL_DESCRIPTION,
    REAL_SOURCE_URL,
)


def _check(label: str, ok: bool, detail: str = "") -> int:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         {detail}")
    return 0 if ok else 1


def test_absence() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 1: INSUFFICIENT EVIDENCE -> EXPLICIT UNKNOWN")
    print("=" * 78)

    result = build_decision_stage({}, reference_date="2026-08-01")
    print(json.dumps(result, indent=2))
    ok = (
        result["decision_stage"] == "unknown"
        and result["confidence"] == "NONE"
        and result["source_fields"] == []
        and result["evidence_quote"] is None
        and result["superseded_signals"] == []
        and result["reference_date_used"] == "2026-08-01"
    )
    failed += _check("empty lead -> unknown/NONE, no guessed stage",
                     ok, json.dumps(result))

    narrative = build_decision_stage(
        {"description": REAL_DESCRIPTION}, reference_date="2026-08-01")
    ok = (
        narrative["decision_stage"] in DECISION_STAGES
        and narrative["confidence"] in {"HIGH", "MEDIUM", "LOW", "NONE"}
    )
    failed += _check("vocabulary + confidence bands respected",
                     ok, json.dumps(narrative))
    return failed


def test_branches() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 2: LADDER PRECEDENCE BRANCHES")
    print("=" * 78)

    withdrawn = build_decision_stage(
        {"approval_status": "withdrawn"}, reference_date="2026-08-01")
    failed += _check("withdrawn status -> withdrawn/HIGH",
                     withdrawn["decision_stage"] == "withdrawn"
                     and withdrawn["confidence"] == "HIGH",
                     json.dumps(withdrawn))

    pending = build_decision_stage(
        {"approval_status": "approved",
         "description": ("Approval granted subject to the following "
                         "conditions: landscape buffer per Code 15.05.")},
        reference_date="2026-08-01")
    failed += _check("approved + condition language -> "
                     "approved_pending_conditions/HIGH with verbatim quote",
                     pending["decision_stage"] == "approved_pending_conditions"
                     and pending["confidence"] == "HIGH"
                     and "subject to the following" in
                     (pending["evidence_quote"] or ""),
                     json.dumps(pending))

    approved = build_decision_stage(
        {"approval_status": "approved"}, reference_date="2026-08-01")
    failed += _check("plain approved status -> approved/HIGH",
                     approved["decision_stage"] == "approved"
                     and approved["confidence"] == "HIGH",
                     json.dumps(approved))

    hearing = build_decision_stage(
        {"next_project_event": "public_hearing",
         "next_project_date": "2026-08-12"},
        reference_date="2026-08-01")
    failed += _check("future public_hearing event -> "
                     "scheduled_public_hearing/HIGH",
                     hearing["decision_stage"] == "scheduled_public_hearing"
                     and hearing["confidence"] == "HIGH"
                     and hearing["source_fields"] ==
                     ["next_project_event", "next_project_date"],
                     json.dumps(hearing))

    stale = build_decision_stage(
        {"approval_status": "denied",
         "next_project_event": "public_hearing",
         "next_project_date": "2026-07-01"},
        reference_date="2026-08-01")
    failed += _check("stale pre-reference date ignored -> "
                     "denied_current_application + superseded note",
                     stale["decision_stage"] == "denied_current_application"
                     and any("precedes" in note
                             for note in stale["superseded_signals"]),
                     json.dumps(stale))

    continued = build_decision_stage(
        {"next_project_event": "public_hearing",
         "next_project_date": "2026-08-12",
         "description": "This item was continued from the July session."},
        reference_date="2026-08-01")
    failed += _check("continued item into scheduled session -> "
                     "in_hearing_process/MEDIUM with quote",
                     continued["decision_stage"] == "in_hearing_process"
                     and continued["confidence"] == "MEDIUM"
                     and "continued from the July" in
                     (continued["evidence_quote"] or ""),
                     json.dumps(continued))

    denial = build_decision_stage(
        {"approval_status": "denied"}, reference_date="2026-08-01")
    failed += _check("denied status, no event -> "
                     "denied_current_application/HIGH",
                     denial["decision_stage"]
                     == "denied_current_application"
                     and denial["confidence"] == "HIGH",
                     json.dumps(denial))

    appeal = build_decision_stage(
        {"approval_status": "denied",
         "description": ("The Planning Commission decision may be appealed "
                         "to the Municipal Council within fourteen days.")},
        reference_date="2026-08-01")
    failed += _check("denial + appeal language -> denied_appeal_window/"
                     "MEDIUM with verbatim quote",
                     appeal["decision_stage"] == "denied_appeal_window"
                     and appeal["confidence"] == "MEDIUM"
                     and "appealed to the Municipal Council" in
                     (appeal["evidence_quote"] or ""),
                     json.dumps(appeal))

    staff = build_decision_stage(
        {"description": "The application remains under staff review."},
        reference_date="2026-08-01")
    failed += _check("staff-review marker only -> under_staff_review/MEDIUM",
                     staff["decision_stage"] == "under_staff_review"
                     and staff["confidence"] == "MEDIUM"
                     and staff["evidence_quote"] is not None,
                     json.dumps(staff))

    presub = build_decision_stage(
        {"description": "The applicant will submit revised plans next month."},
        reference_date="2026-08-01")
    failed += _check("pre-submission marker only -> pre_submission/LOW",
                     presub["decision_stage"] == "pre_submission"
                     and presub["confidence"] == "LOW",
                     json.dumps(presub))

    run_a = json.dumps(build_decision_stage(
        {"approval_status": "denied",
         "friction_signals": ["denied"],
         "next_project_event": "planning_commission_event",
         "next_project_date": "2026-09-02"},
        reference_date="2026-08-01"), sort_keys=True)
    run_b = json.dumps(build_decision_stage(
        {"approval_status": "denied",
         "friction_signals": ["denied"],
         "next_project_event": "planning_commission_event",
         "next_project_date": "2026-09-02"},
        reference_date="2026-08-01"), sort_keys=True)
    failed += _check("deterministic: two runs identical JSON",
                     run_a == run_b)

    vocab_ok = all(stage in DECISION_STAGES for stage in (
        "scheduled_public_hearing", "in_hearing_process",
        "denied_current_application", "unknown"))
    failed += _check("DECISION_STAGES frozen vocabulary intact", vocab_ok)
    return failed


def test_real_plrz20260264() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 3: REAL PLRZ20260264 FIXTURE (verbatim government text)")
    print("=" * 78)

    lead = {
        "application_number": "PLRZ20260264",
        "description": REAL_DESCRIPTION,
        "approval_evidence": REAL_APPROVAL_EVIDENCE,
        "approval_status": "denied",
        "friction_signals": ["denied", "recommended_denial"],
        "historical_evidence": [
            {
                "application_number": "PLRZ20250539",
                "event_type": "recommended_denial",
                "evidence_text": ("recommended denial by the Planning "
                                  "Commission on November 12, 2025"),
                "event_date": "2025-11-12",
            },
            {
                "application_number": "PLRZ20250539",
                "event_type": "denied",
                "evidence_text": ("denied by the Municipal Council on "
                                  "December 2, 2025"),
                "event_date": "2025-12-02",
            },
        ],
        "next_project_date": "2026-09-02",
        "next_project_event": "planning_commission_event",
        "source_url": REAL_SOURCE_URL,
    }
    result = build_decision_stage(lead, reference_date="2026-08-01")
    print(json.dumps(result, indent=2))

    checks = [
        ("stage == scheduled_public_hearing despite denied status",
         result["decision_stage"] == "scheduled_public_hearing"),
        ("confidence HIGH (gov-record event fields)",
         result["confidence"] == "HIGH"),
        ("sources name next_project_event/date",
         result["source_fields"] == ["next_project_event",
                                     "next_project_date"]),
        ("prior-cycle denial explicitly superseded",
         len(result["superseded_signals"]) == 1
         and "prior-cycle history"
         in result["superseded_signals"][0]),
        ("rationale deterministic and non-empty",
         bool(result["rationale"])),
        ("reference date echoed",
         result["reference_date_used"] == "2026-08-01"),
    ]
    for label, ok in checks:
        failed += _check(label, ok,
                         "" if ok else f"got={json.dumps(result)[:300]}")
    return failed


if __name__ == "__main__":
    total = test_absence() + test_branches() + test_real_plrz20260264()
    print("=" * 78)
    print("ALL DECISION STAGE TESTS PASSED" if total == 0
          else f"DECISION STAGE TESTS: {total} FAILURES")
    print("=" * 78)
    sys.exit(0 if total == 0 else 1)
