"""
Step 5 deterministic tests: BlockerActionMapper.

Contract: docs/specs/action_intelligence_contract_v1.md
Real-case ground truth: PLRZ20260264 (Provo, Aug 12 2026 packet).
Run: python -m scripts.test_action_blockers
"""
import json
import sys

from backend.app.services.approval_stage_intelligence import (
    ACTION_CATEGORIES,
    BLOCKER_TYPES,
    map_blockers_and_actions,
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


def _types(result: dict) -> list[str]:
    return [b["blocker_type"] for b in result["blockers"]]


def _categories(result: dict) -> list[str]:
    return [a["category"] for a in result["actions"]]


def test_absence() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 1: NO EVIDENCE -> NO INVENTED BLOCKERS")
    print("=" * 78)

    result = map_blockers_and_actions({}, reference_date="2026-08-01")
    print(json.dumps(result, indent=2))
    ok = (
        result["blockers"] == []
        and len(result["actions"]) == 1
        and result["actions"][0]["category"] == "monitoring_only"
        and result["actions"][0]["confidence"] == "NONE"
        and result["actions"][0]["action_id"] == "A001"
    )
    failed += _check("empty lead -> zero blockers + explicit monitoring_only",
                     ok, json.dumps(result))
    return failed


def test_branches() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 2: BLOCKER SOURCES AND ACTION MAPPING BRANCHES")
    print("=" * 78)

    appeal = map_blockers_and_actions(
        {"approval_status": "denied",
         "description": ("The Planning Commission decision may be appealed "
                         "to the Municipal Council within fourteen days.")},
        reference_date="2026-08-01")
    ok = (_types(appeal) == []
          and _categories(appeal) == ["appeal_filing"]
          and "appealed to the Municipal Council"
          in (appeal["actions"][0]["evidence_quote"] or ""))
    failed += _check("appeal-window stage -> appeal_filing action, no "
                     "duplicate denial blocker", ok, json.dumps(appeal))

    denial = map_blockers_and_actions(
        {"approval_status": "denied"}, reference_date="2026-08-01")
    ok = (_types(denial) == ["prior_denial_history"]
          and denial["blockers"][0]["severity"] == "MEDIUM"
          and _categories(denial) == ["resubmission_prep"])
    failed += _check("bare denied status -> prior_denial_history(MEDIUM) + "
                     "resubmission_prep", ok, json.dumps(denial))

    neighborhood = map_blockers_and_actions(
        {"description":
            "Residents expressed concern about traffic impacts on Geneva "
            "Road during earlier discussions."},
        reference_date="2026-08-01")
    ok = (_types(neighborhood) == ["neighborhood_opposition_risk"]
          and neighborhood["blockers"][0]["severity"] == "MEDIUM"
          and _categories(neighborhood) == ["stakeholder_engagement"]
          and "expressed concern"
          in (neighborhood["blockers"][0]["evidence_quote"] or ""))
    failed += _check("neighborhood concern condition -> "
                     "neighborhood_opposition_risk + stakeholder_engagement",
                     ok, json.dumps(neighborhood))

    code = map_blockers_and_actions(
        {"application_number": "PLSUB20260001",
         "description": ("The request must comply with Provo City Code "
                         "15.05.160. The applicant shall submit a final "
                         "plat within twelve months of approval.")},
        reference_date="2026-08-01")
    ok = (_types(code) == ["code_compliance_requirement",
                           "procedural_deadline",
                           "missing_contact_information"]
          and all(b["severity"] == "MEDIUM" for b in code["blockers"][:2])
          and _categories(code) == ["condition_resolution",
                                    "condition_resolution",
                                    "contact_enrichment"]
          and code["actions"][0]["related_blocker_ids"] == ["B001"]
          and code["actions"][1]["related_blocker_ids"] == ["B002"]
          and code["actions"][0]["detail"] == "C001"
          and code["actions"][1]["detail"] == "C002"
          and code["actions"][0]["action_id"] == "A001"
          and code["actions"][1]["action_id"] == "A002")
    failed += _check("code + procedural conditions -> two condition_resolution "
                     "actions with stable ids", ok, json.dumps(code))

    contact = map_blockers_and_actions(
        {"application_number": "PLRZ20260999",
         "applicant_name": "Jordan Lee"},
        reference_date="2026-08-01")
    ok = (_types(contact) == ["missing_contact_information"]
          and _categories(contact) == ["contact_enrichment"]
          and contact["blockers"][0]["confidence"] == "HIGH")
    failed += _check("identified lead without contacts -> "
                     "missing_contact_information + contact_enrichment",
                     ok, json.dumps(contact))

    low_score = map_blockers_and_actions(
        {"friction_signals": ["denied"], "friction_score": 40},
        reference_date="2026-08-01")
    ok = (_types(low_score) == ["prior_denial_history"]
          and low_score["blockers"][0]["severity"] == "MEDIUM"
          and low_score["blockers"][0]["confidence"] == "HIGH"
          and _categories(low_score) == ["resubmission_prep"]
          and low_score["actions"][0]["confidence"] == "MEDIUM")
    failed += _check("signal-only denial -> MEDIUM blocker + resubmission_prep "
                     "(ladder rung 4), no invented hearing work", ok,
                     json.dumps(low_score))

    run_a = json.dumps(map_blockers_and_actions(
        {"approval_status": "denied", "friction_signals": ["denied"],
         "friction_score": 100,
         "next_project_event": "planning_commission_event",
         "next_project_date": "2026-09-02"},
        reference_date="2026-08-01"), sort_keys=True)
    run_b = json.dumps(map_blockers_and_actions(
        {"approval_status": "denied", "friction_signals": ["denied"],
         "friction_score": 100,
         "next_project_event": "planning_commission_event",
         "next_project_date": "2026-09-02"},
        reference_date="2026-08-01"), sort_keys=True)
    failed += _check("deterministic: two runs identical JSON", run_a == run_b)

    vocab_ok = (all(t in BLOCKER_TYPES for t in (
        "prior_denial_history", "unresolved_staff_concern",
        "missing_contact_information"))
        and all(c in ACTION_CATEGORIES for c in (
            "hearing_preparation", "appeal_filing", "resubmission_prep",
            "contact_enrichment", "monitoring_only")))
    failed += _check("BLOCKER_TYPES / ACTION_CATEGORIES vocab intact",
                     vocab_ok)
    return failed


def test_real_plrz20260264() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 3: REAL PLRZ20260264 FIXTURE (verbatim government text)")
    print("=" * 78)

    lead = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "description": REAL_DESCRIPTION,
        "approval_evidence": REAL_APPROVAL_EVIDENCE,
        "friction_signals": ["denied", "recommended_denial"],
        "friction_score": 100,
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
    result = map_blockers_and_actions(lead, reference_date="2026-08-01")
    print(json.dumps(result, indent=2))

    blockers = {_b["blocker_id"]: _b for _b in result["blockers"]}
    actions_by_cat = {a["category"]: a for a in result["actions"]}
    checks = [
        ("exactly three blockers identified",
         len(result["blockers"]) == 3),
        ("B001 prior_denial_history HIGH/HIGH with verbatim narrative quote",
         blockers.get("B001", {}).get("blocker_type")
         == "prior_denial_history"
         and blockers["B001"]["severity"] == "HIGH"
         and blockers["B001"]["confidence"] == "HIGH"
         and blockers["B001"]["evidence_quote"]
         == ("recommended denial by the Planning Commission on "
             "November 12, 2025")),
        ("B002 unresolved_staff_concern HIGH from gov-record condition",
         blockers.get("B002", {}).get("blocker_type")
         == "unresolved_staff_concern"
         and blockers["B002"]["severity"] == "HIGH"
         and "concerned that the 2025 concept"
         in (blockers["B002"].get("evidence_quote") or "")),
        ("B003 missing_contact_information LOW (no fabricated contact)",
         blockers.get("B003", {}).get("blocker_type")
         == "missing_contact_information"
         and blockers["B003"]["severity"] == "LOW"),
        ("staff-concern blocker links its condition id C002",
         "C002" in blockers.get("B002", {}).get("related_condition_ids", [])),
        ("A001 hearing_preparation tied to denial blocker + due date",
         actions_by_cat.get("hearing_preparation", {})
         .get("related_blocker_ids") == ["B001"]
         and actions_by_cat["hearing_preparation"]["due_reference"]
         == "2026-09-02"),
        ("A002 documentation_prep tied to staff-concern blocker",
         actions_by_cat.get("documentation_prep", {})
         .get("related_blocker_ids") == ["B002"]),
        ("A003 contact_enrichment tied to missing-contact blocker",
         actions_by_cat.get("contact_enrichment", {})
         .get("related_blocker_ids") == ["B003"]),
        ("no appeal/resubmission actions for a scheduled hearing",
         "appeal_filing" not in actions_by_cat
         and "resubmission_prep" not in actions_by_cat),
        ("source_url propagated onto evidence-backed blockers",
         all(b["source_url"] == REAL_SOURCE_URL
             for b in result["blockers"])),
    ]
    for label, ok in checks:
        failed += _check(label, ok,
                         "" if ok else f"got={json.dumps(result)[:400]}")
    return failed


if __name__ == "__main__":
    total = test_absence() + test_branches() + test_real_plrz20260264()
    print("=" * 78)
    print("ALL BLOCKER ACTION TESTS PASSED" if total == 0
          else f"BLOCKER ACTION TESTS: {total} FAILURES")
    print("=" * 78)
    sys.exit(0 if total == 0 else 1)
