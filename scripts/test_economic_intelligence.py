"""
PermitSignal Economic Intelligence Tests (Phase 9)

Targets backend.app.services.economic_intelligence directly. Every scenario
is deterministic (no PDF, no network) -- it hands the module the same
*shape* of already-computed opportunity fields (application_type,
description, applicant_name/company_name) the real pipeline would have
produced by the time this stage runs.

Run from the project root:

    python -m scripts.test_economic_intelligence
"""

from backend.app.services.economic_intelligence import (
    FUNDING_LIKELY,
    FUNDING_PRIVATE,
    FUNDING_UNKNOWN,
    VALUE_SOURCE_BENCHMARK,
    VALUE_SOURCE_DISCLOSED,
    VALUE_SOURCE_NONE,
    apply_economic_intelligence,
    build_economic_intelligence,
)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL ECONOMIC INTELLIGENCE")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/6] Private developer, 33-unit townhome project -> value estimate, zero public spend")

    private_townhomes = {
        "application_number": "PLTEST0001",
        "application_type": "Zone Map Amendment",
        "description": (
            "approval of a Zone Map Amendment from the R1,6 (One Family "
            "Residential) Zone to the LDR (Low Density Residential) Zone in "
            "order to create a 33-unit townhome development, located at "
            "2000 N Canyon Road."
        ),
        "applicant_name": "Tyson Reynolds",
    }

    result = build_economic_intelligence(private_townhomes)

    results.append(check(result["project_scale_units"] == 33, "Extracts 33-unit scale"))
    results.append(check(result["project_scale_type"] == "townhome_residential", "Classifies townhome_residential"))
    results.append(
        check(
            result["estimated_value_source_type"] == VALUE_SOURCE_BENCHMARK,
            "Falls back to construction-benchmark estimate",
        )
    )
    results.append(
        check(
            result["estimated_value_low"] == 33 * 200_000 and result["estimated_value_high"] == 33 * 320_000,
            "Benchmark value range scales with unit count",
        )
    )
    results.append(check(result["public_funding_status"] == FUNDING_PRIVATE, "Private applicant -> private_project"))
    results.append(
        check(
            result["public_spend_low"] == 0.0 and result["public_spend_high"] == 0.0,
            "Private project -> public spend is exactly 0, not fabricated",
        )
    )
    results.append(
        check(result["estimated_value_low"] > 0 and result["public_spend_low"] == 0.0, "Project value != public spend")
    )

    # ------------------------------------------------------------------------
    print("\n[2/6] Government department applicant -> likely public funding, spend mirrors value")

    gov_applicant = {
        "application_number": "PLTEST0002",
        "application_type": "Project Plan",
        "description": "Project Plan approval for a 7-unit flex office development.",
        "applicant_name": "Development Services",
    }

    result = build_economic_intelligence(gov_applicant)

    results.append(check(result["project_scale_type"] == "flex_office", "Classifies flex_office"))
    results.append(check(result["project_scale_units"] == 7, "Extracts 7-unit scale"))
    results.append(
        check(result["public_funding_status"] == FUNDING_LIKELY, "Government-department applicant -> likely_public_funding")
    )
    results.append(
        check(
            result["public_spend_low"] == result["estimated_value_low"]
            and result["public_spend_high"] == result["estimated_value_high"],
            "Likely-public-funding spend mirrors the estimated value range",
        )
    )
    results.append(check(result["public_spend_confidence"] == "LOW", "Likely (not confirmed) funding -> LOW spend confidence"))

    # ------------------------------------------------------------------------
    print("\n[3/6] Ordinance text amendment -> no construction scope, no value fabricated")

    policy_action = {
        "application_number": "PLTEST0003",
        "application_type": "Ordinance Text Amendment",
        "description": "an Ordinance Text Amendment to Provo City Code 14.34.290 to add design standards.",
        "applicant_name": "Development Services",
    }

    result = build_economic_intelligence(policy_action)

    results.append(check(result["estimated_value_low"] is None, "No project value for a policy/regulatory action"))
    results.append(
        check(result["estimated_value_source_type"] == VALUE_SOURCE_NONE, "source_type is insufficient_evidence")
    )
    results.append(check(result["project_scale_units"] is None, "No scale evidence attempted"))

    # ------------------------------------------------------------------------
    print("\n[4/6] Single-family home variance -> unit count of 1")

    single_family = {
        "application_number": "PLTEST0004",
        "application_type": "Variance",
        "description": (
            "a Variance to allow grading and the building of a single-family "
            "home on slopes 30% or greater."
        ),
        "applicant_name": "Kevin Jimenez",
    }

    result = build_economic_intelligence(single_family)

    results.append(check(result["project_scale_units"] == 1, "Single-family home -> 1 unit"))
    results.append(check(result["project_scale_type"] == "single_family", "Classifies single_family"))
    results.append(check(result["estimated_value_low"] == 280_000, "Uses single_family benchmark low bound"))

    # ------------------------------------------------------------------------
    print("\n[5/6] No applicant on record -> funding_unknown, never guessed")

    no_applicant = {
        "application_number": "PLTEST0005",
        "application_type": "Concept Plan",
        "description": "Concept Plan approval for a mixed-use development.",
    }

    result = build_economic_intelligence(no_applicant)

    results.append(check(result["public_funding_status"] == FUNDING_UNKNOWN, "Missing applicant -> funding_unknown"))
    results.append(check(result["public_spend_low"] is None, "No spend guessed without an applicant"))

    # ------------------------------------------------------------------------
    print("\n[6/6] Disclosed dollar figure takes precedence over the benchmark")

    disclosed_value = {
        "application_number": "PLTEST0006",
        "application_type": "Site Plan",
        "description": "Site Plan approval for a 12-unit townhome development with an estimated construction cost of $3.2 million.",
        "applicant_name": "ABC Development LLC",
    }

    result = build_economic_intelligence(disclosed_value)

    results.append(
        check(result["estimated_value_source_type"] == VALUE_SOURCE_DISCLOSED, "Disclosed value wins over benchmark")
    )
    results.append(check(result["estimated_value_low"] == 3_200_000, "Parses '$3.2 million' correctly"))

    # ------------------------------------------------------------------------
    print("\n[batch] apply_economic_intelligence() is additive over a list")

    batch = apply_economic_intelligence([private_townhomes, gov_applicant])
    results.append(check(len(batch) == 2, "Batch preserves record count"))
    results.append(
        check(
            batch[0]["application_number"] == "PLTEST0001" and "estimated_value_low" in batch[0],
            "Batch preserves existing fields and adds economic fields",
        )
    )

    print()
    print("=" * 90)
    passed = sum(1 for r in results if r)
    print(f"RESULTS: {passed}/{len(results)} passed")
    print("=" * 90)

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
