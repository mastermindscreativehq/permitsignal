"""
PermitSignal Outreach & Monetization Intelligence Tests (Phase 8)

Targets backend.app.services.outreach_intelligence directly. Every
scenario below is deterministic (no PDF, no network) -- it hands the
module the same *shape* of already-computed fields the real pipeline
would have produced by the time this stage runs: commercial_readiness
(commercial_lead_intelligence, Phase 6), contact/company/owner fields
(applicant_identity / applicant_enrichment, Phase 2), and
approval_action/approval_reason (approval_action_intelligence, Phase 3).

Run from the project root:

    python -m scripts.test_outreach_intelligence
"""

from backend.app.services.commercial_lead_intelligence import (
    READINESS_NEEDS_CONTACT_ENRICHMENT,
    READINESS_NEEDS_MORE_PROJECT_EVIDENCE,
    READINESS_NOT_READY,
    READINESS_READY_FOR_OUTREACH,
)
from backend.app.services.outreach_intelligence import (
    CHANNEL_EMAIL,
    CHANNEL_NONE,
    CHANNEL_PHONE,
    CONTACT_TYPE_APPLICANT,
    CONTACT_TYPE_APPLICANT_OF_RECORD,
    CONTACT_TYPE_COMPANY,
    CONTACT_TYPE_NONE,
    CONTACT_TYPE_OWNER,
    OUTREACH_STATUS_CONTACTED,
    OUTREACH_STATUS_ENGAGED,
    OUTREACH_STATUS_LOST,
    OUTREACH_STATUS_NEW,
    OUTREACH_STATUS_OPPORTUNITY,
    OUTREACH_STATUS_QUALIFIED,
    OUTREACH_STATUS_READY,
    OUTREACH_STATUS_REPLIED,
    OUTREACH_STATUS_WON,
    QUALIFICATION_ACTIVE_OPPORTUNITY,
    QUALIFICATION_ALREADY_CONTACTED,
    QUALIFICATION_NOT_QUALIFIED,
    QUALIFICATION_QUALIFIED_NOT_CONTACTABLE,
    QUALIFICATION_READY_FOR_OUTREACH,
    advance_outreach_status,
    apply_outreach_event,
    apply_outreach_intelligence,
    build_outreach_intelligence,
    build_outreach_message,
    classify_outreach_qualification,
    is_outreach_eligible,
    recommend_outreach_channel,
    resolve_outreach_contact,
    select_outreach_contact_type,
)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL OUTREACH & MONETIZATION INTELLIGENCE (Phase 8)")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/14] Contact target selection: no evidence at all")

    results.append(
        check(
            select_outreach_contact_type({})[0] == CONTACT_TYPE_NONE,
            "Empty record selects no contact target",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[2/14] Contact target selection: owner outranks applicant")

    owner_and_applicant = {
        "owner_name": "Jane Owner",
        "owner_contact_email": "jane@owner-holdings.com",
        "applicant_name": "Jared Morgan",
        "applicant_email": "jared.morgan@acme-development.com",
    }

    results.append(
        check(
            select_outreach_contact_type(owner_and_applicant)[0] == CONTACT_TYPE_OWNER,
            "A contactable owner is selected over a contactable applicant",
        )
    )
    results.append(
        check(
            "Jane Owner" in select_outreach_contact_type(owner_and_applicant)[1],
            "The selection reason names the actual owner, not a placeholder",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[3/14] Contact target selection: owner known but not contactable never wins")

    owner_no_contact = {
        "owner_name": "Jane Owner",
        "applicant_name": "Jared Morgan",
        "applicant_email": "jared.morgan@acme-development.com",
    }

    results.append(
        check(
            select_outreach_contact_type(owner_no_contact)[0] == CONTACT_TYPE_APPLICANT,
            "A non-contactable owner falls back to the contactable applicant",
        )
    )

    results.append(
        check(
            select_outreach_contact_type({"owner_name": "Jane Owner"})[0] == CONTACT_TYPE_NONE,
            "A non-contactable owner with no other contactable party selects none, "
            "never fabricating a contact",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/14] Contact target selection: applicant-of-record and company fallbacks")

    results.append(
        check(
            select_outreach_contact_type(
                {
                    "applicant_contact_name": "Design Firm LLC",
                    "applicant_contact_email": "contact@designfirm.com",
                }
            )[0]
            == CONTACT_TYPE_APPLICANT_OF_RECORD,
            "Applicant-of-record contact is selected when the applicant "
            "themselves has no contact evidence",
        )
    )
    results.append(
        check(
            select_outreach_contact_type(
                {
                    "company_name": "Acme Development",
                    "contact_email": "info@acme-development.com",
                }
            )[0]
            == CONTACT_TYPE_COMPANY,
            "A generic company contact is the last resort before none",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[5/14] Contact resolution: no fabrication")

    empty_contact = resolve_outreach_contact({})

    results.append(
        check(
            all(
                empty_contact[key] is None
                for key in ("name", "role", "company", "email", "phone", "source")
            ),
            "An empty record resolves to an all-None contact, never a guess",
        )
    )

    owner_contact = resolve_outreach_contact(
        {
            "owner_name": "Jane Owner",
            "owner_entity": "Owner Holdings LLC",
            "owner_contact_email": "jane@owner-holdings.com",
            "owner_contact_phone": "(801) 555-1000",
            "owner_source": "official_website",
        }
    )

    results.append(
        check(
            owner_contact["email"] == "jane@owner-holdings.com"
            and owner_contact["phone"] == "(801) 555-1000"
            and owner_contact["contact_type"] == CONTACT_TYPE_OWNER,
            "Owner contact resolution reuses the real owner_contact_* fields verbatim",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[6/14] Outreach channel: email preferred over phone, none when absent")

    results.append(
        check(
            recommend_outreach_channel({"email": "a@b.com", "phone": "555-0000"}) == CHANNEL_EMAIL,
            "Email is preferred when both channels exist",
        )
    )
    results.append(
        check(
            recommend_outreach_channel({"phone": "555-0000"}) == CHANNEL_PHONE,
            "Phone is used when no email exists",
        )
    )
    results.append(
        check(
            recommend_outreach_channel({}) == CHANNEL_NONE,
            "No channel is fabricated when neither exists",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[7/14] Outreach message: never built without a usable contact channel")

    results.append(
        check(
            build_outreach_message({"application_number": "PLRZ20260264"}, {}) is None,
            "No message is prepared for a lead with no contact evidence",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[8/14] Outreach message: built only from real, existing evidence")

    real_opportunity = {
        "application_number": "PLRZ20260264",
        "application_type": "Zone Map Amendment",
        "project_address": "123 Main St",
        "municipality": "Provo",
        "approval_reason": "A public_hearing is scheduled on 2026-08-12 at 6:00 PM.",
        "recommended_commercial_action": "follow up on an identified approval requirement",
        "commercial_action_reason": "PermitSignal identified a next approval action: attend scheduled hearing.",
    }
    real_contact = {"name": "Jared Morgan", "email": "jared.morgan@acme-development.com"}

    message = build_outreach_message(real_opportunity, real_contact)

    results.append(
        check(
            message is not None
            and "Jared Morgan" in message["body"]
            and "PLRZ20260264" in message["body"]
            and "2026-08-12" in message["body"],
            "Message body reuses the real application number, contact name, "
            "and approval_reason verbatim",
        )
    )
    results.append(
        check(
            "approved" not in message["body"].lower()
            and "denied" not in message["body"].lower(),
            "Message never claims an approval/denial outcome that is not "
            "in the source evidence",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[9/14] Outreach eligibility mirrors existing commercial_readiness only")

    results.append(
        check(
            is_outreach_eligible({"commercial_readiness": READINESS_READY_FOR_OUTREACH}) is True,
            "READY_FOR_OUTREACH commercial_readiness is eligible",
        )
    )
    results.append(
        check(
            is_outreach_eligible({"commercial_readiness": READINESS_NEEDS_CONTACT_ENRICHMENT}) is False,
            "NEEDS_CONTACT_ENRICHMENT is not eligible -- no new gate introduced",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[10/14] Lifecycle: pre-outreach statuses track commercial_readiness")

    results.append(
        check(
            advance_outreach_status(None, READINESS_NOT_READY) == OUTREACH_STATUS_NEW,
            "No prior status + NOT_READY -> NEW",
        )
    )
    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_NEW, READINESS_NEEDS_MORE_PROJECT_EVIDENCE)
            == OUTREACH_STATUS_NEW,
            "NEW + NEEDS_MORE_PROJECT_EVIDENCE stays NEW",
        )
    )
    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_NEW, READINESS_NEEDS_CONTACT_ENRICHMENT)
            == OUTREACH_STATUS_QUALIFIED,
            "NEW auto-advances to QUALIFIED as evidence improves",
        )
    )
    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_QUALIFIED, READINESS_READY_FOR_OUTREACH)
            == OUTREACH_STATUS_READY,
            "QUALIFIED auto-advances to READY_FOR_OUTREACH as evidence improves",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[11/14] Lifecycle integrity: CONTACTED+ is frozen against pipeline reruns")

    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_CONTACTED, READINESS_READY_FOR_OUTREACH)
            == OUTREACH_STATUS_CONTACTED,
            "A CONTACTED lead stays CONTACTED even though readiness would "
            "naturally recompute to READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_WON, READINESS_NOT_READY)
            == OUTREACH_STATUS_WON,
            "A WON deal is never reset by a later pipeline run, even if "
            "the underlying project evidence changes",
        )
    )
    results.append(
        check(
            advance_outreach_status(OUTREACH_STATUS_ENGAGED, READINESS_READY_FOR_OUTREACH)
            == OUTREACH_STATUS_ENGAGED,
            "An ENGAGED lead is not silently downgraded or reset",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[12/14] Qualification status: the four (plus not-qualified) states")

    results.append(
        check(
            classify_outreach_qualification({"commercial_readiness": READINESS_NOT_READY})
            == QUALIFICATION_NOT_QUALIFIED,
            "NOT_READY -> NOT_QUALIFIED",
        )
    )
    results.append(
        check(
            classify_outreach_qualification(
                {"commercial_readiness": READINESS_NEEDS_CONTACT_ENRICHMENT}
            )
            == QUALIFICATION_QUALIFIED_NOT_CONTACTABLE,
            "NEEDS_CONTACT_ENRICHMENT -> QUALIFIED_NOT_CONTACTABLE",
        )
    )
    results.append(
        check(
            classify_outreach_qualification(
                {
                    "commercial_readiness": READINESS_READY_FOR_OUTREACH,
                    "outreach_status": OUTREACH_STATUS_READY,
                }
            )
            == QUALIFICATION_READY_FOR_OUTREACH,
            "READY_FOR_OUTREACH + not yet contacted -> QUALIFIED_READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            classify_outreach_qualification(
                {
                    "commercial_readiness": READINESS_READY_FOR_OUTREACH,
                    "outreach_status": OUTREACH_STATUS_CONTACTED,
                }
            )
            == QUALIFICATION_ALREADY_CONTACTED,
            "READY_FOR_OUTREACH + CONTACTED -> ALREADY_CONTACTED",
        )
    )
    results.append(
        check(
            classify_outreach_qualification(
                {
                    "commercial_readiness": READINESS_READY_FOR_OUTREACH,
                    "outreach_status": OUTREACH_STATUS_OPPORTUNITY,
                }
            )
            == QUALIFICATION_ACTIVE_OPPORTUNITY,
            "READY_FOR_OUTREACH + OPPORTUNITY -> ACTIVE_COMMERCIAL_OPPORTUNITY",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[13/14] Outreach events: deterministic transitions, no regression, invalid events rejected")

    lead = {"outreach_status": OUTREACH_STATUS_READY, "outreach_events": []}

    sent = apply_outreach_event(lead, "outreach_sent", occurred_at="2026-08-01T00:00:00+00:00")
    results.append(
        check(
            sent["outreach_status"] == OUTREACH_STATUS_CONTACTED
            and sent["last_outreach_at"] == "2026-08-01T00:00:00+00:00"
            and len(sent["outreach_events"]) == 1,
            "outreach_sent moves READY_FOR_OUTREACH to CONTACTED and records the event",
        )
    )

    replied = apply_outreach_event(sent, "response_received")
    results.append(
        check(
            replied["outreach_status"] == OUTREACH_STATUS_REPLIED,
            "response_received moves CONTACTED to REPLIED",
        )
    )

    regressed = apply_outreach_event(replied, "outreach_prepared")
    results.append(
        check(
            regressed["outreach_status"] == OUTREACH_STATUS_REPLIED,
            "An earlier-stage event never regresses an already-advanced lead",
        )
    )

    lost_from_replied = apply_outreach_event(replied, "lost", note="Went with a competitor")
    results.append(
        check(
            lost_from_replied["outreach_status"] == OUTREACH_STATUS_LOST,
            "lost is a valid terminal transition from any active stage",
        )
    )

    followed_up = apply_outreach_event(replied, "follow_up_required", note="No response in 2 weeks")
    results.append(
        check(
            followed_up["follow_up_required"] is True
            and followed_up["follow_up_reason"] == "No response in 2 weeks"
            and followed_up["outreach_status"] == OUTREACH_STATUS_REPLIED,
            "follow_up_required raises the flag without changing outreach_status",
        )
    )

    try:
        apply_outreach_event(lead, "not_a_real_event")
        results.append(check(False, "An unknown event raises ValueError"))
    except ValueError:
        results.append(check(True, "An unknown event raises ValueError"))

    # ------------------------------------------------------------------------
    print("\n[14/14] Batch application: preserves existing fields, idempotent, lifecycle-stable across reruns")

    real_shaped_opportunity = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "priority": "HIGH",
        "priority_score": 180,
        "friction_score": 100,
        "lead_status": "CONTACTABLE",
        "is_contactable": True,
        "applicant_email": "jared.morgan@acme-development.com",
        "commercial_readiness": READINESS_READY_FOR_OUTREACH,
        "recommended_commercial_action": "contact applicant/company",
        "commercial_action_reason": "This application is a qualified commercial opportunity.",
    }

    first_pass = apply_outreach_intelligence([real_shaped_opportunity])[0]

    results.append(
        check(
            first_pass["application_number"] == "PLRZ20260264"
            and first_pass["priority"] == "HIGH"
            and first_pass["priority_score"] == 180
            and first_pass["lead_status"] == "CONTACTABLE"
            and first_pass["commercial_readiness"] == READINESS_READY_FOR_OUTREACH,
            "Phase 1-6 fields survive outreach intelligence unchanged",
        )
    )
    results.append(
        check(
            first_pass["outreach_status"] == OUTREACH_STATUS_READY,
            "A fresh READY_FOR_OUTREACH lead starts at outreach_status READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            first_pass["outreach_message_subject"] is not None
            and first_pass["outreach_message_body"] is not None,
            "An eligible, contactable lead gets a prepared message draft",
        )
    )

    second_pass = apply_outreach_intelligence([first_pass])[0]
    outreach_keys = [
        "outreach_status",
        "outreach_qualification_status",
        "outreach_channel",
        "outreach_contact_type",
        "outreach_message_subject",
        "outreach_message_body",
    ]
    results.append(
        check(
            all(first_pass[key] == second_pass[key] for key in outreach_keys),
            "Re-running outreach intelligence on an already-processed "
            "opportunity produces identical results (idempotent)",
        )
    )

    # Simulate: a human sends outreach (advancing to CONTACTED via the
    # controlled event API), then the pipeline reruns against the same
    # packet and must not reset the lead back to READY_FOR_OUTREACH.
    contacted = apply_outreach_event(first_pass, "outreach_sent", occurred_at="2026-08-02T00:00:00+00:00")
    previous_by_number = {"PLRZ20260264": contacted}

    rerun = apply_outreach_intelligence([real_shaped_opportunity], previous_by_number)[0]

    results.append(
        check(
            rerun["outreach_status"] == OUTREACH_STATUS_CONTACTED,
            "A pipeline rerun preserves a CONTACTED lead's lifecycle state "
            "instead of resetting it to READY_FOR_OUTREACH",
        )
    )
    results.append(
        check(
            rerun["outreach_events"] and rerun["last_outreach_at"] == "2026-08-02T00:00:00+00:00",
            "The rerun carries forward the prior outreach event history and timestamp",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print("\n" + "=" * 90)
    print(f"TESTS: {passed} passed, {failed} failed")
    print("=" * 90)

    return failed == 0


def test_stale_contact_flag():
    """
    Regression coverage: outreach_status=CONTACTED must never coexist with
    contactability_level=NO_VERIFIED_CONTACT without an explicit
    stale/needs-review signal.

    outreach_status is correctly frozen once a controlled event moves it
    past READY_FOR_OUTREACH (advance_outreach_status()), so a later
    pipeline run that finds this lead's contact evidence no longer
    verified must not silently reset or hide that regression -- it must
    flag it.
    """

    print("\n" + "=" * 90)
    print("STALE CONTACT DETECTION (outreach_status vs. contactability_level)")
    print("=" * 90)

    results = []

    contactable_opportunity = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "commercial_readiness": READINESS_READY_FOR_OUTREACH,
        "contactability_level": "VERIFIED_PERSON_CONTACT",
        "applicant_email": "jared.morgan@acme-development.com",
    }

    first_pass = apply_outreach_intelligence([contactable_opportunity])[0]
    contacted = apply_outreach_event(
        first_pass,
        "outreach_sent",
        occurred_at="2026-08-02T00:00:00+00:00",
    )
    previous_by_number = {"PLRZ20260264": contacted}

    # A later pipeline run finds no verified contact evidence for the same
    # real-world lead (e.g. re-enrichment invalidated the prior contact).
    regressed_opportunity = dict(contactable_opportunity)
    regressed_opportunity["commercial_readiness"] = READINESS_NEEDS_CONTACT_ENRICHMENT
    regressed_opportunity["contactability_level"] = "NO_VERIFIED_CONTACT"
    regressed_opportunity.pop("applicant_email", None)

    rerun = apply_outreach_intelligence([regressed_opportunity], previous_by_number)[0]

    results.append(
        check(
            rerun["outreach_status"] == OUTREACH_STATUS_CONTACTED,
            "A lead's real CONTACTED history is preserved even after its "
            "contact evidence regresses",
        )
    )
    results.append(
        check(
            rerun["follow_up_required"] is True,
            "A CONTACTED lead whose contact evidence has since regressed "
            "is flagged for review",
        )
    )
    results.append(
        check(
            bool(rerun.get("follow_up_reason"))
            and "CONTACTED" in rerun["follow_up_reason"]
            and "contact" in rerun["follow_up_reason"].lower(),
            "The stale-contact flag carries an explicit, evidence-based reason",
        )
    )

    # Sanity: a healthy CONTACTED lead whose contact evidence is still
    # intact must never be falsely flagged.
    healthy_rerun = apply_outreach_intelligence(
        [contactable_opportunity],
        previous_by_number,
    )[0]

    results.append(
        check(
            healthy_rerun["follow_up_required"] is False,
            "A CONTACTED lead with intact contact evidence is not falsely "
            "flagged as stale",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print(f"\nSTALE CONTACT TESTS: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    main_ok = main()
    stale_ok = test_stale_contact_flag()

    if not (main_ok and stale_ok):
        raise SystemExit(1)
