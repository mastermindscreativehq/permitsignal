"""
Step 3 deterministic tests: RequestedActionNormalizer.

Contract: docs/specs/action_intelligence_contract_v1.md
Real-case ground truth: PLRZ20260264 (Provo, Aug 12 2026 packet).
Run: python -m scripts.test_action_requested
"""
import json
import sys

from backend.app.services.approval_stage_intelligence import (
    REQUESTED_ACTION_TYPES,
    build_requested_action,
)
from scripts.test_action_conditions import (
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
    print("TEST 1: ABSENCE OF REQUEST EVIDENCE -> EXPLICIT UNKNOWN")
    print("=" * 78)

    result = build_requested_action({})
    ok = (
        result["action_type"] == "Unknown"
        and result["confidence"] == "NONE"
        and result["from_state"] is None
        and result["to_state"] is None
        and result["scope"] == {"units": None, "use_mix": [], "notes": None}
        and result["evidence_quote"] is None
        and result["source_url"] is None
    )
    failed += _check("empty lead -> Unknown/NONE with null evidence",
                     ok, json.dumps(result))

    desc_only = build_requested_action({"description": "Fort Utah Neighborhood."})
    ok = (
        desc_only["action_type"] == "Unknown"
        and desc_only["confidence"] == "LOW"
        and desc_only["evidence_quote"] is None
        and desc_only["scope"]["units"] is None
    )
    failed += _check("description without request language -> Unknown/LOW "
                     "(evidence-backed absence)", ok, json.dumps(desc_only))
    return failed


def test_branches() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 2: TYPE RESOLUTION, ZONES, UNITS, USE-MIX, CONFIDENCE")
    print("=" * 78)

    variance = build_requested_action({
        "application_type": "Variance",
        "description": "A request for a 5-foot setback reduction at 42 N 100 E.",
        "source_url": REAL_SOURCE_URL,
    })
    ok = (
        variance["action_type"] == "Variance"
        and variance["confidence"] == "HIGH"
        and variance["from_state"] is None
        and variance["to_state"] is None
        and variance["scope"]["units"] is None
        and variance["evidence_quote"] == (
            "A request for a 5-foot setback reduction at 42 N 100 E.")
    )
    failed += _check("exact-vocab application_type -> Variance/HIGH, no "
                     "fabricated zones/units", ok, json.dumps(variance))

    rezone = build_requested_action({
        "description": ("Rezone from the R1,6 Zone to the LDR Zone for 24 "
                        "single-family homes."),
    })
    ok = (
        rezone["action_type"] == "Zone Map Amendment"
        and rezone["from_state"] == "R1,6"
        and rezone["to_state"] == "LDR"
        and rezone["scope"]["units"] == 24
        and rezone["scope"]["use_mix"] == ["single_family"]
        and rezone["confidence"] == "HIGH"
        and "Rezone from the R1,6" in rezone["evidence_quote"]
    )
    failed += _check("keyword-typed rezone w/o parens -> R1,6->LDR, units=24, "
                     "single_family, HIGH", ok, json.dumps(rezone))

    other = build_requested_action({
        "description": "Requesting administrative review of signage standards.",
    })
    ok = (
        other["action_type"] == "Other"
        and other["confidence"] == "MEDIUM"
        and other["evidence_quote"] is not None
    )
    failed += _check("request signal with untypeable text -> Other/MEDIUM "
                     "with quote", ok, json.dumps(other))

    run_a = json.dumps(build_requested_action(
        {"application_type": "Concept Plan", "description": REAL_DESCRIPTION}),
        sort_keys=True)
    run_b = json.dumps(build_requested_action(
        {"application_type": "Concept Plan", "description": REAL_DESCRIPTION}),
        sort_keys=True)
    failed += _check("deterministic: two runs identical JSON", run_a == run_b)

    vocab_ok = all(t in REQUESTED_ACTION_TYPES
                   for t in ("Zone Map Amendment", "Other", "Unknown"))
    failed += _check("REQUESTED_ACTION_TYPES frozen vocabulary intact",
                     vocab_ok)
    return failed


def test_real_plrz20260264() -> int:
    failed = 0
    print("=" * 78)
    print("TEST 3: REAL PLRZ20260264 FIXTURE (verbatim government text)")
    print("=" * 78)

    lead = {
        "application_number": "PLRZ20260264",
        "application_type": "Zone Map Amendment",
        "description": REAL_DESCRIPTION,
        "source_url": REAL_SOURCE_URL,
    }
    result = build_requested_action(lead)
    print(json.dumps(result, indent=2))

    checks = [
        ("action_type == Zone Map Amendment (exact vocabulary)",
         result["action_type"] == "Zone Map Amendment"),
        ("from_state == CG", result["from_state"] == "CG"),
        ("to_state == MU", result["to_state"] == "MU"),
        ("scope.units == 18", result["scope"]["units"] == 18),
        ("use_mix == [commercial, mixed_use, townhomes]",
         result["scope"]["use_mix"] == ["commercial", "mixed_use", "townhomes"]),
        ("confidence == HIGH", result["confidence"] == "HIGH"),
        ("source_url passthrough", result["source_url"] == REAL_SOURCE_URL),
        ("evidence_quote is verbatim substring of description",
         result["evidence_quote"] in REAL_DESCRIPTION),
        ("quote opens with the request phrase",
         result["evidence_quote"].startswith("a Zone Map Amendment")),
        ("staff contact tail excluded from quote",
         "Van De Graaff" not in (result["evidence_quote"] or "")),
    ]
    for label, ok in checks:
        failed += _check(label, ok,
                         "" if ok else f"got={json.dumps(result)[:300]}")
    return failed


if __name__ == "__main__":
    total = test_absence() + test_branches() + test_real_plrz20260264()
    print("=" * 78)
    print("ALL REQUESTED ACTION TESTS PASSED" if total == 0
          else f"REQUESTED ACTION TESTS: {total} FAILURES")
    print("=" * 78)
    sys.exit(0 if total == 0 else 1)
