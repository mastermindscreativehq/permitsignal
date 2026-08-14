"""
PermitSignal Commercial Lead Intelligence Tests (Phase 6)

Targets backend.app.services.commercial_lead_intelligence directly. Every
scenario below is deterministic (no PDF, no network) -- it hands the
module the same *shape* of already-computed fields the real pipeline
would have produced by the time this stage runs: lead_status/
is_contactable (opportunity_builder.qualify_lead), contact/company/owner
fields (applicant_identity / applicant_enrichment, Phase 2), and
approval_status/approval_action/approval_basis (approval_action_
intelligence, Phase 3).

Run from the project root:

    python -m scripts.test_commercial_lead_intelligence
"""

from backend.app.services.approval_action_intelligence import (
    BASIS_CONFIRMED,
)
from backend.app.services.commercial_lead_intelligence import (
    ACTION_CONTACT_APPLICANT,
    ACTION_CONTACT_OWNER,
    ACTION_ENRICH_CONTACT,
    ACTION_FOLLOW_UP_APPROVAL,
    ACTION_HOLD,
    ACTION_INVESTIGATE_DECISION_MAKER,
    ACTION_MONITOR,
    CONTACT_LEVEL_NONE,
    CONTACT_LEVEL_PUBLIC_BUSINESS,
    CONTACT_LEVEL_VERIFIED_COMPANY,
    CONTACT_LEVEL_VERIFIED_PERSON,
    READINESS_NEEDS_CONTACT_ENRICHMENT,
    READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
    READINESS_NOT_READY,
    READINESS_READY_FOR_OUTREACH,
    apply_commercial_intelligence,
    build_commercial_intelligence,
    classify_commercial_readiness,
    classify_contactability,
)
from backend.app.services.opportunity_builder import (
    LEAD_STATUS_ARCHIVED,
    LEAD_STATUS_CONTACTABLE,
    LEAD_STATUS_NEW,
    LEAD_STATUS_NO_CONTACT,
    LEAD_STATUS_QUALIFIED,
    PRIORITY_HIGH,
)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL COMMERCIAL LEAD INTELLIGENCE (Phase 6)")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/12] Contactability: no contact evidence at all")

    results.append(
        check(
            classify_contactability({}) == CONTACT_LEVEL_NONE,
            "Empty record has NO_VERIFIED_CONTACT",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[2/12] Contactability: named professional email -> verified person")

    results.append(
        check(
            classify_contactability(
                {"applicant_email": "jared.morgan@acme-development.com"}
            )
            == CONTACT_LEVEL_VERIFIED_PERSON,
            "Named applicant email is VERIFIED_PERSON_CONTACT",
        )
    )
    results.append(
        check(
            classify_contactability(
                {
                    "owner_contact_name": "Jane Owner",
                    "owner_contact_phone": "(801) 555-1000",
                }
            )
            == CONTACT_LEVEL_VERIFIED_PERSON,
            "Owner contact phone alone is VERIFIED_PERSON_CONTACT",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[3/12] Contactability: generic mailbox distinguishes source confidence")

    results.append(
        check(
            classify_contactability(
                {
                    "contact_email": "info@acme-development.com",
                    "contact_source": "official_website",
                }
            )
            == CONTACT_LEVEL_VERIFIED_COMPANY,
            "Generic mailbox from the company's own official website is "
            "VERIFIED_COMPANY_CONTACT",
        )
    )
    results.append(
        check(
            classify_contactability(
                {
                    "contact_email": "info@acme-development.com",
                    "contact_source": "public_business_directory",
                }
            )
            == CONTACT_LEVEL_PUBLIC_BUSINESS,
            "Generic mailbox from a public business directory is "
            "PUBLIC_BUSINESS_CONTACT (lower confidence than an official "
            "company source)",
        )
    )
    results.append(
        check(
            classify_contactability(
                {"applicant_email": "info@acme-development.com"}
            )
            == CONTACT_LEVEL_PUBLIC_BUSINESS,
            "A generic government-record applicant email with no "
            "explicit official source still degrades to "
            "PUBLIC_BUSINESS_CONTACT, never a fabricated VERIFIED tier",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/12] Commercial readiness: deterministic re-labeling of lead_status")

    results.append(
        check(
            classify_commercial_readiness({"lead_status": LEAD_STATUS_ARCHIVED})
            == READINESS_NOT_READY,
            "ARCHIVED lead_status -> NOT_READY",
        )
    )
    results.append(
        check(
            classify_commercial_readiness({"lead_status": LEAD_STATUS_NEW})
            == READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
            "NEW lead_status -> NEEDS_MORE_PROJECT_EVIDENCE",
        )
    )
    results.append(
        check(
            classify_commercial_readiness({"lead_status": LEAD_STATUS_NO_CONTACT})
            == READINESS_NEEDS_CONTACT_ENRICHMENT,
            "NO_CONTACT lead_status -> NEEDS_CONTACT_ENRICHMENT",
        )
    )
    results.append(
        check(
            classify_commercial_readiness({"lead_status": LEAD_STATUS_QUALIFIED})
            == READINESS_READY_FOR_OUTREACH,
            "QUALIFIED lead_status -> READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            classify_commercial_readiness({"lead_status": LEAD_STATUS_CONTACTABLE})
            == READINESS_READY_FOR_OUTREACH,
            "CONTACTABLE lead_status -> READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            classify_commercial_readiness({})
            == READINESS_NOT_READY,
            "Missing lead_status conservatively defaults to NOT_READY, "
            "never READY_FOR_OUTREACH",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[5/12] Recommended action: NOT_READY -> hold")

    not_ready = build_commercial_intelligence(
        {"lead_status": LEAD_STATUS_ARCHIVED}
    )

    results.append(
        check(
            not_ready["commercial_readiness"] == READINESS_NOT_READY,
            "Archived record is NOT_READY",
        )
    )
    results.append(
        check(
            not_ready["recommended_commercial_action"] == ACTION_HOLD,
            "NOT_READY recommends holding",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[6/12] Recommended action: NEEDS_MORE_PROJECT_EVIDENCE -> monitor")

    weak_signal = build_commercial_intelligence(
        {"lead_status": LEAD_STATUS_NEW}
    )

    results.append(
        check(
            weak_signal["recommended_commercial_action"] == ACTION_MONITOR,
            "NEEDS_MORE_PROJECT_EVIDENCE recommends monitoring",
        )
    )

    # ------------------------------------------------------------------------
    print(
        "\n[7/12] Recommended action: NEEDS_CONTACT_ENRICHMENT distinguishes "
        "a known owner from no identity at all"
    )

    owner_no_contact = build_commercial_intelligence(
        {
            "lead_status": LEAD_STATUS_NO_CONTACT,
            "owner_name": "Jane Owner",
        }
    )

    results.append(
        check(
            owner_no_contact["recommended_commercial_action"]
            == ACTION_INVESTIGATE_DECISION_MAKER,
            "A known owner with no contact evidence recommends "
            "investigating the missing decision-maker",
        )
    )
    results.append(
        check(
            "Jane Owner" in owner_no_contact["commercial_action_reason"],
            "The reason names the actual owner on record, not a "
            "generic placeholder",
        )
    )

    no_identity = build_commercial_intelligence(
        {"lead_status": LEAD_STATUS_NO_CONTACT}
    )

    results.append(
        check(
            no_identity["recommended_commercial_action"] == ACTION_ENRICH_CONTACT,
            "No owner/person identity at all recommends generic contact "
            "enrichment, not a fabricated decision-maker investigation",
        )
    )

    # ------------------------------------------------------------------------
    print(
        "\n[8/12] Recommended action: READY_FOR_OUTREACH prioritizes an "
        "identified approval requirement"
    )

    approval_ready = build_commercial_intelligence(
        {
            "lead_status": LEAD_STATUS_CONTACTABLE,
            "applicant_email": "jared.morgan@acme-development.com",
            "approval_action": "attend scheduled hearing",
            "approval_basis": BASIS_CONFIRMED,
            "approval_reason": "A public_hearing is scheduled on 2026-08-12.",
        }
    )

    results.append(
        check(
            approval_ready["recommended_commercial_action"]
            == ACTION_FOLLOW_UP_APPROVAL,
            "A confirmed approval action takes precedence over a plain "
            "contact-the-applicant recommendation",
        )
    )
    results.append(
        check(
            approval_ready["commercial_action_reason"]
            == "A public_hearing is scheduled on 2026-08-12.",
            "The reason reuses approval_reason verbatim rather than "
            "re-deriving a new explanation",
        )
    )

    # ------------------------------------------------------------------------
    print(
        "\n[9/12] Recommended action: READY_FOR_OUTREACH without an approval "
        "action falls back to owner or applicant/company"
    )

    owner_ready = build_commercial_intelligence(
        {
            "lead_status": LEAD_STATUS_CONTACTABLE,
            "owner_name": "Jane Owner",
            "owner_contact_email": "jane@owner-holdings.com",
            "approval_action": "unknown",
        }
    )

    results.append(
        check(
            owner_ready["recommended_commercial_action"] == ACTION_CONTACT_OWNER,
            "An identified, contactable owner is recommended over the "
            "generic applicant/company action",
        )
    )

    applicant_ready = build_commercial_intelligence(
        {
            "lead_status": LEAD_STATUS_QUALIFIED,
            "contact_email": "info@acme-development.com",
            "contact_source": "official_website",
            "opportunity_reason": "HIGH opportunity: Jared Morgan; Zone Map Amendment.",
        }
    )

    results.append(
        check(
            applicant_ready["recommended_commercial_action"]
            == ACTION_CONTACT_APPLICANT,
            "No owner on record falls back to contacting the applicant/"
            "company",
        )
    )
    results.append(
        check(
            applicant_ready["commercial_action_reason"]
            == "HIGH opportunity: Jared Morgan; Zone Map Amendment.",
            "The reason reuses the existing opportunity_reason rather "
            "than duplicating that business logic",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[10/12] No fabrication: absent evidence never becomes a claim")

    results.append(
        check(
            build_commercial_intelligence({})["contactability_level"]
            == CONTACT_LEVEL_NONE,
            "An empty record is never marked as having usable contact "
            "evidence",
        )
    )
    results.append(
        check(
            "owner" not in applicant_ready["commercial_action_reason"].lower(),
            "A record with no owner evidence never mentions an owner in "
            "the recommended action's reason",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[11/12] Batch application preserves every existing field")

    real_shaped_opportunity = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "priority": PRIORITY_HIGH,
        "priority_score": 180,
        "friction_score": 100,
        "friction_signals": ["denied", "recommended_denial"],
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "has_future_opportunity": True,
        "lead_status": LEAD_STATUS_NO_CONTACT,
        "is_contactable": False,
        "approval_status": "denied",
        "approval_action": "no immediate action identified",
        "approval_basis": BASIS_CONFIRMED,
    }

    batch = apply_commercial_intelligence([real_shaped_opportunity])
    processed = batch[0]

    results.append(
        check(
            processed["application_number"] == "PLRZ20260264"
            and processed["priority"] == PRIORITY_HIGH
            and processed["priority_score"] == 180
            and processed["friction_score"] == 100
            and processed["approval_status"] == "denied"
            and processed["lead_status"] == LEAD_STATUS_NO_CONTACT
            and processed["is_contactable"] is False,
            "Phase 1-5 fields (identity, priority, friction, approval, "
            "lead qualification) survive commercial intelligence unchanged",
        )
    )
    results.append(
        check(
            processed["commercial_readiness"] == READINESS_NEEDS_CONTACT_ENRICHMENT,
            "A denied, no-contact HIGH-priority lead is NEEDS_CONTACT_"
            "ENRICHMENT, not falsely READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            processed["recommended_commercial_action"] == ACTION_ENRICH_CONTACT,
            "Denied application with no contact and no owner recommends "
            "generic contact enrichment",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[12/12] Idempotent repeated processing")

    first_pass = apply_commercial_intelligence([real_shaped_opportunity])[0]
    second_pass = apply_commercial_intelligence([first_pass])[0]

    commercial_keys = [
        "contactability_level",
        "commercial_readiness",
        "recommended_commercial_action",
        "commercial_action_reason",
    ]

    results.append(
        check(
            all(first_pass[key] == second_pass[key] for key in commercial_keys),
            "Re-running commercial lead intelligence on an already-"
            "processed opportunity produces identical results (idempotent)",
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
