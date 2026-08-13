from pathlib import Path

import pymupdf

from backend.app.services.application_extractor import (
    extract_applications,
)


# ============================================================
# CONFIG
# ============================================================

PDF_PATH = Path(
    "data/documents/_08122026-415.pdf"
)


# ============================================================
# PDF READER
# ============================================================

def read_pdf(
    pdf_path: Path,
) -> str:

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    document = pymupdf.open(
        pdf_path
    )

    try:

        pages = []

        for page in document:

            pages.append(
                page.get_text("text")
            )

        return "\n".join(
            pages
        )

    finally:

        document.close()


# ============================================================
# DISPLAY
# ============================================================

def display_application(
    application: dict,
) -> None:

    print()
    print("-" * 80)

    print(
        f"ITEM:              "
        f"{application.get('item')}"
    )

    print(
        f"APPLICANT:         "
        f"{application.get('applicant_name')}"
    )

    print(
        f"APPLICANT EMAIL:   "
        f"{application.get('applicant_email')}"
    )

    print(
        f"APPLICANT PHONE:   "
        f"{application.get('applicant_phone')}"
    )

    print(
        f"STAFF CONTACT:     "
        f"{application.get('staff_contact_name')}"
    )

    print(
        f"STAFF EMAIL:       "
        f"{application.get('staff_contact_email')}"
    )

    print(
        f"STAFF PHONE:       "
        f"{application.get('staff_contact_phone')}"
    )

    print(
        f"TYPE:              "
        f"{application.get('application_type')}"
    )

    print(
        f"APPLICATION #:     "
        f"{application.get('application_number')}"
    )

    print(
        f"ADDRESS:           "
        f"{application.get('project_address')}"
    )

    print(
        f"NEIGHBORHOOD:      "
        f"{application.get('neighborhood')}"
    )

    print(
        f"STATUS:            "
        f"{', '.join(application.get('status', [])) or 'None'}"
    )

    print(
        f"SOURCE:            "
        f"{application.get('source')}"
    )

    print(
        f"SOURCE URL:        "
        f"{application.get('source_url')}"
    )

    print(
        f"DESCRIPTION:       "
        f"{application.get('project_description')}"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_applications(
    applications: list[dict],
) -> None:

    print()
    print("=" * 80)
    print("VALIDATION")
    print("=" * 80)

    total = len(applications)

    applicants = sum(
        bool(
            application.get(
                "applicant_name"
            )
        )
        for application in applications
    )

    addresses = sum(
        bool(
            application.get(
                "project_address"
            )
        )
        for application in applications
    )

    types = sum(
        bool(
            application.get(
                "application_type"
            )
        )
        for application in applications
    )

    application_numbers = sum(
        bool(
            application.get(
                "application_number"
            )
        )
        for application in applications
    )

    staff_contacts = sum(
        bool(
            application.get(
                "staff_contact_name"
            )
        )
        for application in applications
    )

    print(
        f"Applications:       {total}"
    )

    print(
        f"Applicants:         "
        f"{applicants}/{total}"
    )

    print(
        f"Addresses:          "
        f"{addresses}/{total}"
    )

    print(
        f"Application types:  "
        f"{types}/{total}"
    )

    print(
        f"Application numbers:"
        f" {application_numbers}/{total}"
    )

    print(
        f"Staff contacts:     "
        f"{staff_contacts}/{total}"
    )


# ============================================================
# EXPECTED PROVO CHECKS
# ============================================================

def run_known_checks(
    applications: list[dict],
) -> None:

    print()
    print("=" * 80)
    print("KNOWN PROVO CHECKS")
    print("=" * 80)

    by_number = {
        application[
            "application_number"
        ]: application
        for application in applications
    }

    expected = {
        "PLRZ20260116": {
            "applicant_name":
                "Tyson Reynolds",

            "application_type":
                "Zone Map Amendment",

            "project_address":
                "2000 N Canyon Road",

            "neighborhood":
                "Pleasant View",
        },

        "PLCP20260117": {
            "applicant_name":
                "Tyson Reynolds",

            "application_type":
                "Concept Plan",

            "project_address":
                "2000 N Canyon Road",

            "neighborhood":
                "Pleasant View",
        },

        "PLRZ20260264": {
            "applicant_name":
                "Jared Morgan",

            "application_type":
                "Zone Map Amendment",

            "neighborhood":
                "Fort Utah",
        },

        "PLCP20260261": {
            "applicant_name":
                "Jared Morgan",

            "application_type":
                "Concept Plan",

            "neighborhood":
                "Fort Utah",
        },

        "PLVAR20260373": {
            "applicant_name":
                "Kevin Jimenez",

            "application_type":
                "Variance",

            "project_address":
                "1065 E Hillside Circle",

            "neighborhood":
                "Sherwood Hills",
        },

        "PLPPA20250700": {
            "applicant_name":
                "Bret Nelson",

            "application_type":
                "Project Plan",

            "neighborhood":
                "Grandview South",
        },
    }

    passed = 0
    failed = 0

    for application_number, checks in expected.items():

        application = by_number.get(
            application_number
        )

        if not application:

            print(
                f"[FAIL] {application_number} "
                f"was not detected"
            )

            failed += 1
            continue

        application_passed = True

        for field, expected_value in checks.items():

            actual_value = application.get(
                field
            )

            # Some address formats may differ slightly.
            # Normalize whitespace for comparison.
            if isinstance(
                actual_value,
                str,
            ) and isinstance(
                expected_value,
                str,
            ):

                actual_compare = " ".join(
                    actual_value.split()
                ).lower()

                expected_compare = " ".join(
                    expected_value.split()
                ).lower()

                matches = (
                    expected_compare
                    in actual_compare
                )

            else:

                matches = (
                    actual_value
                    == expected_value
                )

            if matches:

                print(
                    f"[PASS] "
                    f"{application_number} "
                    f"{field}: "
                    f"{actual_value}"
                )

            else:

                print(
                    f"[FAIL] "
                    f"{application_number} "
                    f"{field}: "
                    f"expected={expected_value!r}, "
                    f"actual={actual_value!r}"
                )

                application_passed = False

        if application_passed:
            passed += 1
        else:
            failed += 1

    print()
    print(
        f"Checks passed: {passed}"
    )

    print(
        f"Checks failed: {failed}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("PERMITSIGNAL APPLICATION EXTRACTOR")
    print("=" * 80)

    # --------------------------------------------------------
    # 1. Read PDF
    # --------------------------------------------------------

    print()
    print(
        "[1/4] Reading government PDF..."
    )

    text = read_pdf(
        PDF_PATH
    )

    print(
        f"PDF: {PDF_PATH}"
    )

    print(
        f"Characters: "
        f"{len(text):,}"
    )

    # --------------------------------------------------------
    # 2. Extract
    # --------------------------------------------------------

    print()
    print(
        "[2/4] Extracting applications "
        "from the agenda section..."
    )

    applications = extract_applications(
        text
    )

    print(
        f"Applications detected: "
        f"{len(applications)}"
    )

    # --------------------------------------------------------
    # 3. Display
    # --------------------------------------------------------

    print()
    print(
        "[3/4] APPLICATION RESULTS"
    )

    print(
        "=" * 80
    )

    for application in applications:

        display_application(
            application
        )

    # --------------------------------------------------------
    # 4. Validate
    # --------------------------------------------------------

    print()
    print(
        "[4/4] ANALYSIS SUMMARY"
    )

    validate_applications(
        applications
    )

    run_known_checks(
        applications
    )

    print()
    print("=" * 80)
    print("APPLICATION EXTRACTION TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()