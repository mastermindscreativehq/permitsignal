"""
PERMITSIGNAL OPPORTUNITY BUILDER TESTS
======================================

Run from the permit-signal project root:

    python -m scripts.test_opportunity_builder

These tests exercise the complete deterministic opportunity-building layer.
"""

from datetime import date

from backend.app.services.opportunity_builder import (
    LEAD_STATUS_ARCHIVED,
    LEAD_STATUS_CONTACTABLE,
    LEAD_STATUS_NEW,
    LEAD_STATUS_NO_CONTACT,
    LEAD_STATUS_QUALIFIED,
    PRIORITY_ARCHIVED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    URGENCY_SOON,
    URGENCY_URGENT,
    URGENCY_UPCOMING,
    build_opportunities,
    build_opportunity,
    calculate_days_until,
    calculate_priority_score,
    classify_lead_status,
    classify_priority,
    classify_urgency,
    high_priority_opportunities,
    is_actionable_application,
    is_contactable_lead,
    qualify_lead,
    sort_opportunities,
    validate_opportunity,
)


REFERENCE_DATE = date(2026, 8, 1)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 80)
    print("PERMITSIGNAL OPPORTUNITY BUILDER")
    print("=" * 80)

    results = []

    application = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "application_type": "Zone Map Amendment",
        "project_address": "113/191 N Geneva Road",
        "neighborhood": "Fort Utah",
        "description": (
            "Mixed-use development containing 18 townhomes "
            "and commercial space."
        ),
        "staff_contact": "Megan Van De Graaff",
        "staff_email": "mvandegraaff@provo.gov",
        "staff_phone": "(801) 852-6408",
        "source": "Provo Planning Commission",
        "source_url": (
            "https://www.provo.gov/AgendaCenter/"
            "ViewFile/Agenda/_08122026-415"
        ),
    }

    friction = {
        "friction_score": 100,
        "signals": [
            "denied",
            "recommended_denial",
        ],
        "events": [
            {
                "type": "recommended_denial",
                "date": "2025-11-12",
                "severity": "high",
            },
            {
                "type": "denied",
                "date": "2025-12-02",
                "severity": "critical",
            },
        ],
    }

    enrichment = {
        "applicant_name": "Jared Morgan",
        "applicant_email": None,
        "applicant_phone": None,
    }

    dates = {
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "has_future_opportunity": True,
        "future_project_dates": [
            {
                "value": "2026-08-12",
                "label": "public_hearing",
                "time": "6:00 PM",
            },
            {
                "value": "2026-09-08",
                "label": "municipal_council_event",
                "time": "5:30 PM",
            },
        ],
        "historical_project_dates": [
            {
                "value": "2025-11-12",
                "label": "planning_commission_event",
            },
            {
                "value": "2025-12-02",
                "label": "municipal_council_event",
            },
        ],
    }

    # ------------------------------------------------------------------
    # 1. DATE HELPERS
    # ------------------------------------------------------------------

    print("\n[1/12] Date and urgency logic")

    results.append(
        check(
            calculate_days_until(
                "2026-08-12",
                REFERENCE_DATE,
            ) == 11,
            "Calculates days until hearing",
        )
    )

    results.append(
        check(
            classify_urgency(
                5,
                True,
            ) == URGENCY_URGENT,
            "Classifies <=7 days as URGENT",
        )
    )

    results.append(
        check(
            classify_urgency(
                20,
                True,
            ) == URGENCY_SOON,
            "Classifies 8-30 days as SOON",
        )
    )

    results.append(
        check(
            classify_urgency(
                60,
                True,
            ) == URGENCY_UPCOMING,
            "Classifies >30 days as UPCOMING",
        )
    )

    results.append(
        check(
            classify_urgency(
                None,
                False,
            ) == "HISTORICAL",
            "Classifies non-future record as HISTORICAL",
        )
    )

    # ------------------------------------------------------------------
    # 2. APPLICATION ACTIONABILITY
    # ------------------------------------------------------------------

    print("\n[2/12] Application actionability")

    results.append(
        check(
            is_actionable_application(
                application
            ),
            "Zone Map Amendment is actionable",
        )
    )

    results.append(
        check(
            is_actionable_application(
                {
                    "application_type": "Concept Plan"
                }
            ),
            "Concept Plan is actionable",
        )
    )

    results.append(
        check(
            not is_actionable_application(
                {
                    "application_type": "Administrative Hearing"
                }
            ),
            "Generic administrative hearing is not automatically actionable",
        )
    )

    # ------------------------------------------------------------------
    # 3. PRIORITY
    # ------------------------------------------------------------------

    print("\n[3/12] Priority engine")

    high_priority = classify_priority(
        friction_score=100,
        has_future_opportunity=True,
        days_until_event=11,
        is_actionable=True,
        signals=[
            "denied",
            "recommended_denial",
        ],
    )

    results.append(
        check(
            high_priority == PRIORITY_HIGH,
            "High-friction future project becomes HIGH",
        )
    )

    medium_priority = classify_priority(
        friction_score=30,
        has_future_opportunity=True,
        days_until_event=45,
        is_actionable=True,
        signals=[],
    )

    results.append(
        check(
            medium_priority == PRIORITY_MEDIUM,
            "Actionable future project becomes MEDIUM",
        )
    )

    low_priority = classify_priority(
        friction_score=0,
        has_future_opportunity=True,
        days_until_event=90,
        is_actionable=False,
        signals=[],
    )

    results.append(
        check(
            low_priority == PRIORITY_LOW,
            "Weak future project becomes LOW",
        )
    )

    archived_priority = classify_priority(
        friction_score=100,
        has_future_opportunity=False,
        days_until_event=None,
        is_actionable=True,
        signals=["denied"],
    )

    results.append(
        check(
            archived_priority == PRIORITY_ARCHIVED,
            "No future opportunity becomes ARCHIVED",
        )
    )

    score = calculate_priority_score(
        friction_score=100,
        has_future_opportunity=True,
        days_until_event=11,
        is_actionable=True,
        signals=["denied"],
    )

    results.append(
        check(
            score > 100,
            "Priority score combines friction, future event, actionability and urgency",
        )
    )

    # ------------------------------------------------------------------
    # 4. BUILD CORE OPPORTUNITY
    # ------------------------------------------------------------------

    print("\n[4/12] Building canonical opportunity")

    opportunity = build_opportunity(
        application=application,
        friction=friction,
        enrichment=enrichment,
        dates=dates,
        reference_date=REFERENCE_DATE,
        source={
            "source": "Provo Planning Commission",
            "source_url": (
                "https://www.provo.gov/AgendaCenter/"
                "ViewFile/Agenda/_08122026-415"
            ),
            "municipality": "Provo",
            "state": "Utah",
        },
    )

    results.append(
        check(
            opportunity["application_number"]
            == "PLRZ20260264",
            "Preserves application number",
        )
    )

    results.append(
        check(
            opportunity["applicant_name"]
            == "Jared Morgan",
            "Preserves applicant name",
        )
    )

    results.append(
        check(
            opportunity["application_type"]
            == "Zone Map Amendment",
            "Preserves application type",
        )
    )

    results.append(
        check(
            opportunity["project_address"]
            == "113/191 N Geneva Road",
            "Preserves project address",
        )
    )

    results.append(
        check(
            opportunity["friction_score"] == 100,
            "Carries friction score",
        )
    )

    results.append(
        check(
            set(
                opportunity["friction_signals"]
            )
            == {
                "denied",
                "recommended_denial",
            },
            "Carries friction signals",
        )
    )

    results.append(
        check(
            opportunity["next_project_date"]
            == "2026-08-12",
            "Carries future project date",
        )
    )

    results.append(
        check(
            opportunity["next_project_event"]
            == "public_hearing",
            "Carries future project event",
        )
    )

    results.append(
        check(
            opportunity["next_project_time"]
            == "6:00 PM",
            "Carries future project time",
        )
    )

    results.append(
        check(
            opportunity["has_future_opportunity"] is True,
            "Marks future opportunity",
        )
    )

    results.append(
        check(
            opportunity["days_until_event"] == 11,
            "Calculates days until event",
        )
    )

    results.append(
        check(
            opportunity["urgency"] == URGENCY_SOON,
            "Classifies 11-day event as SOON",
        )
    )

    results.append(
        check(
            opportunity["priority"] == PRIORITY_HIGH,
            "Classifies Jared Morgan as HIGH",
        )
    )

    results.append(
        check(
            opportunity["is_actionable"] is True,
            "Marks Zone Map Amendment actionable",
        )
    )

    results.append(
        check(
            "Jared Morgan" in opportunity[
                "opportunity_reason"
            ],
            "Creates human-readable opportunity reason",
        )
    )

    # ------------------------------------------------------------------
    # 5. HISTORICAL DATE SAFETY
    # ------------------------------------------------------------------

    print("\n[5/12] Historical date safety")

    historical_dates = {
        "next_project_date": "2025-12-02",
        "next_project_event": "municipal_council_event",
        "next_project_time": None,
        "has_future_opportunity": True,
    }

    historical_opportunity = build_opportunity(
        application=application,
        friction=friction,
        dates=historical_dates,
        reference_date=REFERENCE_DATE,
    )

    results.append(
        check(
            historical_opportunity[
                "has_future_opportunity"
            ] is False,
            "Historical date cannot remain a future opportunity",
        )
    )

    results.append(
        check(
            historical_opportunity[
                "next_project_date"
            ] is None,
            "Historical date is removed from live next-event field",
        )
    )

    results.append(
        check(
            historical_opportunity[
                "priority"
            ] == PRIORITY_ARCHIVED,
            "Historical-only record becomes ARCHIVED",
        )
    )

    # ------------------------------------------------------------------
    # 6. MULTIPLE OPPORTUNITIES
    # ------------------------------------------------------------------

    print("\n[6/12] Batch opportunity building")

    second_application = {
        "application_number": "PLCP20260117",
        "applicant_name": "Tyson Reynolds",
        "application_type": "Concept Plan",
        "project_address": "2000 N Canyon Road",
        "neighborhood": "Pleasant View",
    }

    third_application = {
        "application_number": "PLVAR20260373",
        "applicant_name": "Kevin Jimenez",
        "application_type": "Variance",
        "project_address": "1065 E Hillside Circle",
        "neighborhood": "Sherwood Hills",
    }

    batch = build_opportunities(
        applications=[
            application,
            second_application,
            third_application,
        ],
        friction_by_application={
            "PLRZ20260264": friction,
            "PLCP20260117": {
                "friction_score": 0,
                "signals": [],
            },
            "PLVAR20260373": {
                "friction_score": 20,
                "signals": ["continued"],
            },
        },
        dates_by_application={
            "PLRZ20260264": dates,
            "PLCP20260117": {
                "next_project_date": "2026-08-12",
                "next_project_event": "public_hearing",
                "next_project_time": "6:00 PM",
                "has_future_opportunity": True,
            },
            "PLVAR20260373": {
                "next_project_date": "2026-08-20",
                "next_project_event": "public_hearing",
                "next_project_time": "6:00 PM",
                "has_future_opportunity": True,
            },
        },
        reference_date=REFERENCE_DATE,
    )

    results.append(
        check(
            len(batch) == 3,
            "Builds all supplied applications",
        )
    )

    results.append(
        check(
            all(
                item.get("application_number")
                for item in batch
            ),
            "Every batch opportunity has application number",
        )
    )

    # ------------------------------------------------------------------
    # 7. SORTING
    # ------------------------------------------------------------------

    print("\n[7/12] Lead queue sorting")

    sorted_batch = sort_opportunities(batch)

    results.append(
        check(
            sorted_batch[0]["priority"]
            == PRIORITY_HIGH,
            "Highest priority opportunity appears first",
        )
    )

    high = high_priority_opportunities(
        batch
    )

    results.append(
        check(
            len(high) >= 1,
            "High-priority queue contains Jared Morgan",
        )
    )

    # ------------------------------------------------------------------
    # 8. VALIDATION
    # ------------------------------------------------------------------

    print("\n[8/12] Record validation")

    errors = validate_opportunity(
        opportunity
    )

    results.append(
        check(
            errors == [],
            "Canonical opportunity passes validation",
        )
    )

    invalid = dict(opportunity)
    invalid["application_number"] = None

    invalid_errors = validate_opportunity(
        invalid
    )

    results.append(
        check(
            any(
                "application_number"
                in error
                for error in invalid_errors
            ),
            "Validation detects missing application number",
        )
    )

    # ------------------------------------------------------------------
    # 9. OPPORTUNITY -> LEAD CONVERSION
    # ------------------------------------------------------------------

    print("\n[9/12] Opportunity to lead conversion")

    lead = qualify_lead(opportunity)

    results.append(
        check(
            lead["application_number"] == opportunity["application_number"],
            "Lead conversion preserves application number",
        )
    )
    results.append(
        check(
            lead["applicant_name"] == opportunity["applicant_name"],
            "Lead conversion preserves applicant identity",
        )
    )
    results.append(
        check(
            lead["priority"] == opportunity["priority"]
            and lead["priority_score"] == opportunity["priority_score"],
            "Lead conversion preserves priority and priority score",
        )
    )
    results.append(
        check(
            lead["friction_score"] == opportunity["friction_score"]
            and lead["friction_signals"] == opportunity["friction_signals"],
            "Lead conversion preserves friction",
        )
    )
    results.append(
        check(
            lead["next_project_date"] == opportunity["next_project_date"]
            and lead["has_future_opportunity"]
            == opportunity["has_future_opportunity"],
            "Lead conversion preserves future project data",
        )
    )
    results.append(
        check(
            "lead_status" in lead and "is_contactable" in lead,
            "Lead conversion adds lead_status and is_contactable",
        )
    )

    provenance_opportunity = dict(opportunity)
    provenance_opportunity.update(
        {
            "company_name": "Acme Development LLC",
            "company_website": "https://acme-development.com",
            "contact_email": "jared.morgan@acme-development.com",
            "contact_phone": "(801) 555-1212",
            "contact_source": "official_company_website",
            "contact_confidence": 0.92,
        }
    )

    provenance_lead = qualify_lead(provenance_opportunity)

    results.append(
        check(
            provenance_lead["company_name"] == "Acme Development LLC",
            "Lead conversion preserves company name",
        )
    )
    results.append(
        check(
            provenance_lead["contact_email"]
            == "jared.morgan@acme-development.com",
            "Lead conversion preserves contact email",
        )
    )
    results.append(
        check(
            provenance_lead["contact_phone"] == "(801) 555-1212",
            "Lead conversion preserves contact phone",
        )
    )
    results.append(
        check(
            provenance_lead["contact_source"] == "official_company_website",
            "Lead conversion preserves contact source",
        )
    )
    results.append(
        check(
            provenance_lead["contact_confidence"] == 0.92,
            "Lead conversion preserves contact confidence",
        )
    )

    # ------------------------------------------------------------------
    # 10. CONTACTABLE LEAD DETECTION
    # ------------------------------------------------------------------

    print("\n[10/12] Contactable lead detection")

    named_contact_opportunity = dict(opportunity)
    named_contact_opportunity["applicant_email"] = (
        "jared.morgan@acme-development.com"
    )
    named_contact_opportunity["email_source"] = "official_company_website"

    named_lead = qualify_lead(named_contact_opportunity)

    results.append(
        check(
            named_lead["is_contactable"] is True,
            "Named professional email is contactable",
        )
    )
    results.append(
        check(
            named_lead["lead_status"] == LEAD_STATUS_CONTACTABLE,
            "Named professional email yields CONTACTABLE status",
        )
    )

    phone_only_opportunity = dict(opportunity)
    phone_only_opportunity["applicant_phone"] = "(801) 555-1000"
    phone_only_opportunity["phone_source"] = "government_record"

    phone_lead = qualify_lead(phone_only_opportunity)

    results.append(
        check(
            phone_lead["is_contactable"] is True,
            "Government-record phone is contactable",
        )
    )
    results.append(
        check(
            phone_lead["lead_status"] == LEAD_STATUS_CONTACTABLE,
            "Government-record phone yields CONTACTABLE status",
        )
    )

    generic_email_opportunity = dict(opportunity)
    generic_email_opportunity["applicant_email"] = (
        "info@acme-development.com"
    )

    generic_lead = qualify_lead(generic_email_opportunity)

    results.append(
        check(
            generic_lead["is_contactable"] is True,
            "Generic company email is still contactable",
        )
    )
    results.append(
        check(
            generic_lead["lead_status"] == LEAD_STATUS_QUALIFIED,
            "Generic company email yields QUALIFIED "
            "(lower specificity than CONTACTABLE)",
        )
    )

    # ------------------------------------------------------------------
    # 11. NO-CONTACT LEAD DETECTION / NO FABRICATION
    # ------------------------------------------------------------------

    print("\n[11/12] No-contact lead detection and no fabrication")

    no_contact_lead = qualify_lead(opportunity)

    results.append(
        check(
            no_contact_lead["is_contactable"] is False,
            "No contact information is never treated as contactable",
        )
    )
    results.append(
        check(
            no_contact_lead["lead_status"] == LEAD_STATUS_NO_CONTACT,
            "HIGH-priority lead without contact becomes NO_CONTACT",
        )
    )
    results.append(
        check(
            no_contact_lead.get("applicant_email") is None
            and no_contact_lead.get("contact_email") is None,
            "Lead qualification never fabricates a contact email",
        )
    )
    results.append(
        check(
            not is_contactable_lead(
                {"has_future_opportunity": True, "priority": "HIGH"}
            ),
            "A record with no contact fields at all is never contactable",
        )
    )

    # ------------------------------------------------------------------
    # 12. LEAD STATUS BOUNDARIES / STAFF SEPARATION
    # ------------------------------------------------------------------

    print("\n[12/12] Lead status boundaries and staff separation")

    weak_signal_opportunity = {
        "application_number": "PLWEAK0001",
        "applicant_name": "Weak Signal Co",
        "priority": PRIORITY_LOW,
        "is_actionable": False,
        "has_future_opportunity": True,
        "applicant_email": None,
        "applicant_phone": None,
    }

    weak_lead = qualify_lead(weak_signal_opportunity)

    results.append(
        check(
            weak_lead["lead_status"] == LEAD_STATUS_NEW,
            "Weak-signal future opportunity becomes NEW, "
            "not falsely QUALIFIED",
        )
    )

    archived_lead = qualify_lead(historical_opportunity)

    results.append(
        check(
            archived_lead["lead_status"] == LEAD_STATUS_ARCHIVED,
            "Historical-only opportunity becomes ARCHIVED as a lead",
        )
    )
    results.append(
        check(
            archived_lead["is_contactable"] is False,
            "Archived lead is never marked contactable",
        )
    )

    staff_check_opportunity = dict(opportunity)
    staff_check_opportunity["applicant_email"] = None

    staff_lead = qualify_lead(staff_check_opportunity)

    results.append(
        check(
            staff_lead.get("staff_email") == "mvandegraaff@provo.gov",
            "Lead conversion preserves staff contact separately",
        )
    )
    results.append(
        check(
            staff_lead.get("applicant_email")
            != staff_lead.get("staff_email"),
            "Lead conversion never assigns staff email as applicant email",
        )
    )
    results.append(
        check(
            classify_lead_status(
                {"has_future_opportunity": False, "priority": "HIGH"}
            )
            == LEAD_STATUS_ARCHIVED,
            "classify_lead_status treats absent future event as ARCHIVED "
            "regardless of priority",
        )
    )

    print("\n" + "=" * 80)

    passed = sum(results)
    failed = len(results) - passed

    print(
        f"TESTS: {passed} passed, {failed} failed"
    )

    print("=" * 80)

    print("\nSAMPLE OPPORTUNITY")
    print("-" * 80)

    display_fields = (
        "application_number",
        "applicant_name",
        "applicant_email",
        "application_type",
        "project_address",
        "neighborhood",
        "friction_score",
        "friction_signals",
        "next_project_date",
        "next_project_event",
        "next_project_time",
        "days_until_event",
        "urgency",
        "priority",
        "priority_score",
        "is_actionable",
        "has_future_opportunity",
    )

    for field_name in display_fields:
        print(
            f"{field_name}: "
            f"{opportunity.get(field_name)}"
        )

    print("\nSAMPLE LEAD RECORD (qualify_lead applied)")
    print("-" * 80)

    lead_display_fields = (
        "company_name",
        "contact_email",
        "contact_phone",
        "contact_source",
        "contact_confidence",
        "identity_status",
        "is_contactable",
        "lead_status",
    )

    for field_name in lead_display_fields:
        print(
            f"{field_name}: "
            f"{lead.get(field_name)}"
        )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()