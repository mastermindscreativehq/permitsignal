"""
PermitSignal Project Date Extractor - Production Tests
"""

from datetime import date

from backend.app.services.project_date_extractor import (
    extract_project_dates,
    future_project_dates,
    historical_project_dates,
    get_next_project_date,
    enrich_application_dates,
)


REFERENCE_DATE = date(2026, 8, 1)


def check(condition: bool, label: str) -> bool:
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def print_dates(title, dates):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    for item in dates:
        print(
            f"DATE={item.value} | "
            f"LABEL={item.label} | "
            f"FUTURE={item.is_future} | "
            f"TIME={item.time} | "
            f"SCORE={item.score}"
        )

    if not dates:
        print("NONE")


def main():
    print("=" * 80)
    print("PERMITSIGNAL PROJECT DATE EXTRACTOR")
    print("=" * 80)

    text = """
    Planning Commission Agenda, August 12, 2026.

    The Provo City Planning Commission will hold a public hearing
    on August 12, 2026 at 6:00 PM.

    On Tuesday, September 8, 2026, at 5:30 PM the Municipal Council
    will consider the items noted below.

    Public comments must be submitted before 6:00 PM the day before
    the hearing.

    In spring 2025, Jared Morgan applied for a rezone.

    The Planning Commission recommended denial on November 12, 2025,
    and the Municipal Council ultimately denied the request on December 2, 2025.
    """

    results = []

    # ------------------------------------------------------------------
    # ALL DATES
    # ------------------------------------------------------------------

    all_dates = extract_project_dates(
        text,
        REFERENCE_DATE,
        "PLRZ20260264",
    )

    print_dates("ALL EXTRACTED DATES", all_dates)

    results.append(
        check(
            len(all_dates) == 4,
            f"Extracts exactly 4 unique dates (found {len(all_dates)})",
        )
    )

    # ------------------------------------------------------------------
    # FUTURE DATES
    # ------------------------------------------------------------------

    future = future_project_dates(
        text,
        REFERENCE_DATE,
        "PLRZ20260264",
    )

    print_dates("FUTURE PROJECT DATES", future)

    hearing = next(
        (
            item
            for item in future
            if item.value == "2026-08-12"
        ),
        None,
    )

    council = next(
        (
            item
            for item in future
            if item.value == "2026-09-08"
        ),
        None,
    )

    results.append(
        check(
            hearing is not None,
            "Finds August 12, 2026 future event",
        )
    )

    results.append(
        check(
            council is not None,
            "Finds September 8, 2026 future event",
        )
    )

    results.append(
        check(
            hearing is not None
            and hearing.label == "public_hearing",
            "August 12 is classified as public_hearing",
        )
    )

    results.append(
        check(
            hearing is not None
            and hearing.time == "6:00 PM",
            "August 12 captures 6:00 PM",
        )
    )

    results.append(
        check(
            council is not None
            and council.label == "municipal_council_event",
            "September 8 is classified as municipal_council_event",
        )
    )

    results.append(
        check(
            council is not None
            and council.time == "5:30 PM",
            "September 8 captures 5:30 PM",
        )
    )

    # ------------------------------------------------------------------
    # HISTORICAL
    # ------------------------------------------------------------------

    historical = historical_project_dates(
        text,
        REFERENCE_DATE,
        "PLRZ20260264",
    )

    print_dates("HISTORICAL PROJECT DATES", historical)

    denial_recommendation = next(
        (
            item
            for item in historical
            if item.value == "2025-11-12"
        ),
        None,
    )

    denial = next(
        (
            item
            for item in historical
            if item.value == "2025-12-02"
        ),
        None,
    )

    results.append(
        check(
            denial_recommendation is not None,
            "Keeps November 12, 2025 historical",
        )
    )

    results.append(
        check(
            denial is not None,
            "Keeps December 2, 2025 historical",
        )
    )

    # ------------------------------------------------------------------
    # NEXT EVENT
    # ------------------------------------------------------------------

    next_event = get_next_project_date(
        text,
        REFERENCE_DATE,
        "PLRZ20260264",
    )

    print()
    print("=" * 80)
    print("NEXT PROJECT EVENT")
    print("=" * 80)

    if next_event:
        print(f"DATE:       {next_event.value}")
        print(f"LABEL:      {next_event.label}")
        print(f"TIME:       {next_event.time}")
        print(f"SCORE:      {next_event.score}")
        print(f"CONFIDENCE: {next_event.confidence}")
    else:
        print("NONE")

    results.append(
        check(
            next_event is not None,
            "Finds next project event",
        )
    )

    results.append(
        check(
            next_event is not None
            and next_event.value == "2026-08-12",
            "Next event is August 12, 2026",
        )
    )

    results.append(
        check(
            next_event is not None
            and next_event.label == "public_hearing",
            "Next event is public hearing",
        )
    )

    results.append(
        check(
            next_event is not None
            and next_event.time == "6:00 PM",
            "Next event time is 6:00 PM",
        )
    )

    # ------------------------------------------------------------------
    # APPLICATION ENRICHMENT
    # ------------------------------------------------------------------

    application = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "project_address": "113/191 N Geneva Road",
        "application_type": "Zone Map Amendment",
    }

    enriched = enrich_application_dates(
        application,
        text,
        REFERENCE_DATE,
    )

    print()
    print("=" * 80)
    print("ENRICHED APPLICATION")
    print("=" * 80)

    print(f"Application:        {enriched.get('application_number')}")
    print(f"Applicant:          {enriched.get('applicant_name')}")
    print(f"Next date:          {enriched.get('next_project_date')}")
    print(f"Next event:         {enriched.get('next_project_event')}")
    print(f"Next time:          {enriched.get('next_project_time')}")
    print(
        "Future opportunity: "
        f"{enriched.get('has_future_opportunity')}"
    )

    results.append(
        check(
            enriched.get("next_project_date") == "2026-08-12",
            "Application receives next_project_date",
        )
    )

    results.append(
        check(
            enriched.get("next_project_event") == "public_hearing",
            "Application receives next_project_event",
        )
    )

    results.append(
        check(
            enriched.get("next_project_time") == "6:00 PM",
            "Application receives next_project_time",
        )
    )

    results.append(
        check(
            enriched.get("has_future_opportunity") is True,
            "Application is marked as future opportunity",
        )
    )

    # ------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------

    passed = sum(results)
    failed = len(results) - passed

    print()
    print("=" * 80)
    print(f"TESTS: {passed} passed, {failed} failed")
    print("=" * 80)

    return failed == 0


def test_application_scoping() -> bool:
    """
    Regression coverage for cross-application date/evidence contamination.

    A real government packet contains multiple applications in one PDF,
    separated by "Item N" markers. Item 1 (a citywide ordinance text
    amendment) has no date content of its own. Item 2 (a rezone) has its
    own future project date and denial history.

    Before the fix, enrich_application_dates() searched the ENTIRE packet
    text for every application, so Item 1 silently inherited Item 2's
    September 2, 2026 date and evidence. Each application must only ever
    receive dates/evidence from its own Item N block.
    """

    print()
    print("=" * 80)
    print("APPLICATION-SCOPED DATE EXTRACTION (cross-application contamination)")
    print("=" * 80)

    text = """
    * Item 1
    PLOTA20260371
    Development Services requests an Ordinance Text Amendment to Provo
    City Code 14.34.290 to add Provo River Design Corridor standards.
    Citywide Application.

    * Item 2
    PLRZ20260264
    Jared Morgan requests approval of a Zone Map Amendment. The
    application was ultimately denied by the Municipal Council on
    December 2, 2025. This item will be presented at the September 2,
    2026, West District neighborhood meeting.
    """

    # Reference date is AFTER the shared August 12 hearing has already
    # passed, forcing the extractor to fall through to the next-nearest
    # future date in the document -- exactly the condition that exposed
    # the bug in real production data.
    reference_date = date(2026, 8, 14)

    item_1 = {
        "application_number": "PLOTA20260371",
        "item": 1,
    }

    item_2 = {
        "application_number": "PLRZ20260264",
        "item": 2,
    }

    enriched_1 = enrich_application_dates(item_1, text, reference_date)
    enriched_2 = enrich_application_dates(item_2, text, reference_date)

    print(f"Item 1 next_project_date:   {enriched_1.get('next_project_date')}")
    print(f"Item 1 has_future_opportunity: {enriched_1.get('has_future_opportunity')}")
    print(f"Item 1 project_dates:       {enriched_1.get('project_dates')}")
    print(f"Item 2 next_project_date:   {enriched_2.get('next_project_date')}")
    print(f"Item 2 has_future_opportunity: {enriched_2.get('has_future_opportunity')}")

    results = []

    results.append(
        check(
            enriched_1.get("next_project_date") is None,
            "Item 1 (no date content of its own) receives no next_project_date",
        )
    )

    results.append(
        check(
            enriched_1.get("has_future_opportunity") is False,
            "Item 1 is not marked as a future opportunity",
        )
    )

    results.append(
        check(
            enriched_1.get("project_dates") == [],
            "Item 1 receives no dates at all from Item 2's text",
        )
    )

    results.append(
        check(
            enriched_2.get("next_project_date") == "2026-09-02",
            "Item 2 receives its own September 2, 2026 date",
        )
    )

    results.append(
        check(
            enriched_2.get("has_future_opportunity") is True,
            "Item 2 is correctly marked as a future opportunity",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print()
    print("=" * 80)
    print(f"APPLICATION SCOPING TESTS: {passed} passed, {failed} failed")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    main_ok = main()
    scoping_ok = test_application_scoping()

    if not (main_ok and scoping_ok):
        raise SystemExit(1)
