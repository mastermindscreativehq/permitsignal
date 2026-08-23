"""
Deterministic tests for Step 2 -- ConditionExtractor.

Fixtures use VERBATIM text from the live PLRZ20260264 government record
(stored on the lead in Supabase) plus synthetic control sentences for
each vocabulary branch. Run: python -m scripts.test_action_conditions
"""

import json
import sys

from backend.app.services.approval_stage_intelligence import (
    build_conditions,
    extract_conditions_from_text,
)

FAILED_CHECKS = 0


def _check(label: str, ok: bool, detail: str = "") -> int:
    global FAILED_CHECKS
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" (got {detail})" if detail and not ok else ""))
    if not ok:
        FAILED_CHECKS += 1
    return 0 if ok else 1


REAL_DESCRIPTION = (
    "a Zone Map Amendment from the CG (General Commercial) Zone to the "
    "MU (Mixed-Use) Zone to entitle a mixed-use development containing 18 "
    "townhomes and commercial space, located at 113/191 N Geneva Road. "
    "Fort Utah Neighborhood. Megan Van De Graaff (801) 852-6408 "
    "mvandegraff@provo.gov"
)

REAL_APPROVAL_EVIDENCE = (
    "gs that were built in 1944 and 1999 and are currently utilized by "
    "Pearson Cabinet & Supply. The smaller parcel contains a single-family "
    "dwelling built in 1943. In spring 2025, Jared Morgan applied for a "
    "rezone and concept plan on the subject property which was recommended "
    "denial by the Planning Commission on November 12, 2025, and ultimately "
    "denied by the Municipal Council on December 2, 2025. That rezone "
    "request was for a Medium Density Residential zone with 26 townhomes "
    "that would be a mix of rentals and for- sale units. Eight of those 26 "
    "units would be live/work units with ground floor office space. The "
    "staff reports and meeting minutes from the 2025 Planning Commission "
    "meeting are attached to this report. According to these reports, both "
    "the Planning Commission and residents were concerned that the 2025 "
    "concept did not include traditional commercial uses. There is an "
    "application for a concept plan associated with this rezone, see "
    "Item 5. NEIGHBORHOOD FEEDBACK This item will be presented at the Septe"
)
REAL_SOURCE_URL = (
    "https://www.provo.gov/AgendaCenter/ViewFile/Agenda/_08122026-415"
)


def test_absence_yields_nothing() -> int:
    print()
    print("=" * 78)
    print("TEST 1: ABSENCE OF CONDITION LANGUAGE -> EMPTY (never fabricated)")
    print("=" * 78)
    failed = 0

    conds = extract_conditions_from_text(REAL_DESCRIPTION,
                                         source_url=REAL_SOURCE_URL,
                                         source_kind="government_record")
    failed += _check("real description contains no condition language",
                     conds == [], f"{len(conds)} conditions")

    conds = build_conditions({"description": REAL_DESCRIPTION})
    failed += _check("build_conditions on plain description -> []", conds == [])

    conds = build_conditions({})
    failed += _check("empty lead -> []", conds == [])
    return failed


def test_vocabulary_branches() -> int:
    print()
    print("=" * 78)
    print("TEST 2: VOCABULARY BRANCHES + CONFIDENCE + EVIDENCE QUOTES")
    print("=" * 78)
    failed = 0

    conds = extract_conditions_from_text(
        "Approval is subject to completion of right-of-way improvements.",
        source_kind="narrative")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "staff_recommendation_condition"
          and conds[0]["confidence"] == "LOW"
          and conds[0]["evidence_quote"] ==
          "Approval is subject to completion of right-of-way improvements.")
    failed += _check(f"generic normative -> default staff/LOW w/ verbatim quote",
                     ok, json.dumps(conds))

    conds = extract_conditions_from_text(
        "The request must comply with Provo City Code 15.05.160 regarding "
        "hillside development standards.", source_kind="narrative")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "code_standard_condition"
          and conds[0]["confidence"] == "HIGH")
    failed += _check("code citation + normative -> code_standard/HIGH", ok,
                     json.dumps(conds))

    conds = extract_conditions_from_text(
        "Staff recommends approval subject to the attached findings.",
        source_kind="narrative")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "staff_recommendation_condition"
          and conds[0]["confidence"] == "HIGH")
    failed += _check("explicit staff recommendation + normative -> HIGH", ok,
                     json.dumps(conds))

    conds = extract_conditions_from_text(
        "Residents expressed concern about drainage in the open field "
        "behind the lots.", source_kind="narrative")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "neighborhood_commitment"
          and conds[0]["confidence"] == "MEDIUM")
    failed += _check("resident concern -> neighborhood_commitment/MEDIUM",
                     ok, json.dumps(conds))

    conds = extract_conditions_from_text(
        "The applicant shall submit a final plat within twelve months of "
        "approval.", source_kind="government_record")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "procedural_condition"
          and conds[0]["confidence"] == "HIGH")
    failed += _check("procedural obligation from gov record -> HIGH", ok,
                     json.dumps(conds))

    conds = extract_conditions_from_text(
        "The original permit was denied by the commission.", source_kind="narrative")
    ok = (len(conds) == 1
          and conds[0]["condition_type"] == "prior_decision_requirement"
          and conds[0]["confidence"] == "MEDIUM")
    failed += _check("prior decision language -> prior_decision_requirement/MEDIUM",
                     ok, json.dumps(conds))

    gov = extract_conditions_from_text(
        "Residents expressed concern about parking.", source_kind="government_record")
    failed += _check("gov-record provenance bumps MEDIUM -> HIGH",
                     gov and gov[0]["confidence"] == "HIGH",
                     json.dumps(gov))
    return failed


def test_real_plrz20260264() -> int:
    print()
    print("=" * 78)
    print("TEST 3: REAL PLRZ20260264 FIXTURES (verbatim government text)")
    print("=" * 78)
    failed = 0

    lead = {
        "application_number": "PLRZ20260264",
        "description": REAL_DESCRIPTION,
        "source_url": REAL_SOURCE_URL,
        "approval_evidence": REAL_APPROVAL_EVIDENCE,
        "approval_source": REAL_SOURCE_URL,
        "historical_evidence": [
            {"evidence_text":
             "recommended denial by the Planning Commission on November 12, 2025",
             "event_date": "2025-11-12"},
            {"matched_text":
             "denied by the Municipal Council on December 2, 2025",
             "event_date": "2025-12-02"},
        ],
        "friction_events": [],
    }

    conds = build_conditions(lead)
    failed += _check(f"description contributes zero conditions; total from "
                     f"full record == expected (got {len(conds)})",
                     len(conds) == 4, str(len(conds)))

    by_id = {c["condition_id"]: c for c in conds}
    failed += _check("ids assigned C001.. in stable order",
                     list(by_id.keys()) == [f"C{i:03d}" for i in range(1, len(conds) + 1)],
                     str(list(by_id.keys())))

    concern = next((c for c in conds
                    if "traditional commercial uses" in c["statement"]), None)
    ok = (concern is not None
          and concern["condition_type"] == "staff_recommendation_condition"
          and concern["statement"] == concern["evidence_quote"]
          and concern["source_url"] == REAL_SOURCE_URL
          and concern["event_date"] is None
          and concern["subject_hint"] is None
          and concern["confidence"] == "HIGH")
    failed += _check("commission+resident concern extracted as staff condition "
                     "with verbatim quote (gov-record HIGH)", ok,
                     json.dumps(concern))

    hist_types = [c["condition_type"] for c in conds
                  if c["event_date"] in ("2025-11-12", "2025-12-02")]
    failed += _check(f"historical evidence yields prior_decision_requirement "
                     f"(got {hist_types})",
                     hist_types == ["prior_decision_requirement",
                                    "prior_decision_requirement"])

    dup_lead = dict(lead)
    dup_lead["friction_events"] = [{
        "matched_text": ("According to these reports, both the Planning "
                         "Commission and residents were concerned that the "
                         "2025 concept did not include traditional "
                         "commercial uses."),
        "event_date": "2025-12-02",
    }]
    deduped = build_conditions(dup_lead)
    failed += _check("identical sentence across fields is deduped to one",
                     sum(1 for c in deduped
                         if "traditional commercial uses" in c["statement"]) == 1,
                     str(len(deduped)))

    again = build_conditions(lead)
    failed += _check("deterministic: two runs identical JSON",
                     json.dumps(conds) == json.dumps(again))
    return failed


def main() -> int:
    failed = 0
    failed += test_absence_yields_nothing()
    failed += test_vocabulary_branches()
    failed += test_real_plrz20260264()

    print()
    print("=" * 78)
    if failed == 0:
        print("ALL CONDITION EXTRACTOR TESTS PASSED")
    else:
        print(f"CONDITION EXTRACTOR TESTS: {failed} FAILURES")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
