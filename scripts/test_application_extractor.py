from pathlib import Path

import pymupdf

from backend.app.services.application_extractor import (
    extract_application_type,
    extract_applications,
    extract_agenda_section,
    split_agenda_items,
    extract_case_identifier,
    extract_description,
    extract_property_address,
    parse_address_components,
    find_case_identifiers,
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
# APPLICATION TYPE PHRASING REGRESSION CHECKS
# ============================================================

def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label}")
    return False


def run_application_type_regression_checks() -> bool:
    """
    Regression coverage for the real Provo failure where
    extract_application_type() returned None for legitimate General Plan
    Amendment applications because the government record used a different
    word order than the original narrow pattern -- causing
    pipeline_orchestrator to reject the entire containing document.
    """

    print()
    print("=" * 80)
    print("APPLICATION TYPE PHRASING REGRESSION CHECKS")
    print("=" * 80)

    results = []

    # Real text from data/documents/_03112026-362.pdf (PLGPA20250235).
    results.append(
        check(
            extract_application_type(
                "Brixton Capital requests a General Plan Map Amendment from "
                "the Commercial (C) designation to the Transit Oriented "
                "Development (TOD) designation for 23 acres of land."
            )
            == "General Plan Amendment",
            'Recognizes "General Plan Map Amendment" phrasing',
        )
    )

    # Real text from data/documents/_07082026-406.pdf (PLGPA20260012).
    results.append(
        check(
            extract_application_type(
                "Eric Langvardt requests an amendment to the General Plan "
                "Map to change the classification from Industrial (I) to "
                "Mixed-Use (M) for 21.6 acres of land."
            )
            == "General Plan Amendment",
            'Recognizes "amendment to the General Plan Map" phrasing',
        )
    )

    # The original narrow phrasing must still match.
    results.append(
        check(
            extract_application_type(
                "requests a General Plan Amendment for the property."
            )
            == "General Plan Amendment",
            'Still recognizes the original "General Plan Amendment" phrasing',
        )
    )

    # Real text from data/documents/_05272026-389.pdf (PLGPA20260193): no
    # recognizable amendment phrase is present at all. This must stay None
    # -- inferring a type from the application_number prefix instead of
    # the descriptive text would be fabrication, not extraction.
    results.append(
        check(
            extract_application_type(
                "Provo Public Works request adoption of the Storm Drain "
                "Master Plan into the General Plan along with an "
                "associated Impact Fee Facility Plan."
            )
            is None,
            "Returns None (not a fabricated type) when no recognizable "
            "phrase is present",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print()
    print(f"Checks passed: {passed}")
    print(f"Checks failed: {failed}")

    return failed == 0


# ============================================================
# CASE IDENTIFIER EXTRACTION REGRESSION CHECKS
# ============================================================

def run_case_identifier_checks() -> bool:
    """
    Regression coverage for multi-label Case ID / Application ID
    extraction: explicit labels (Case Number, Application Number, File
    Number, Project Number, Planning/Development variants), bare
    jurisdiction header style ("Case PUD-871", real Tulsa TMAPC staff
    report), the unlabeled Provo inline format, exact-source-value
    preservation, and evidence-backed None when no identifier exists.
    """

    print()
    print("=" * 80)
    print("CASE IDENTIFIER EXTRACTION CHECKS")
    print("=" * 80)

    results = []

    def expect_identifier(
        text,
        value,
        label=None,
        id_type=None,
        label_result=None,
    ):

        identifier = extract_case_identifier(text)

        passed = bool(identifier) and (
            identifier["value"] == value
        )

        if label is not None:
            passed = passed and (
                identifier.get("label") == label
            )

        if id_type is not None:
            passed = passed and (
                identifier.get("type") == id_type
            )

        results.append(
            check(
                passed,
                f"{label_result or value!r} <- "
                f"{text[:52]!r}",
            )
        )

        return identifier

    # Real Tulsa County TMAPC header style.
    expect_identifier(
        "Case PUD-871 Staff Report",
        "PUD-871",
        label="Case",
        id_type="case",
    )

    # Explicit labels across jurisdictions.
    expect_identifier(
        "Case Number: CZ-565",
        "CZ-565",
        label="Case Number",
        id_type="case",
    )

    expect_identifier(
        "Case No. 2024-SUP-0117",
        "2024-SUP-0117",
        label="Case No.",
    )

    expect_identifier(
        "Application Number APP-2024-0042",
        "APP-2024-0042",
        label="Application Number",
        id_type="application",
    )

    expect_identifier(
        "Application No. ZC-25-114",
        "ZC-25-114",
        label="Application No.",
    )

    expect_identifier(
        "File Number 22-5566",
        "22-5566",
        label="File Number",
        id_type="file",
    )

    expect_identifier(
        "Project Number PRJ-9911",
        "PRJ-9911",
        label="Project Number",
        id_type="project",
    )

    expect_identifier(
        "Planning Application Number PLA2025-001",
        "PLA2025-001",
        label="Planning Application Number",
    )

    expect_identifier(
        "Development Application No. DA-2026-77",
        "DA-2026-77",
        label="Development Application No.",
    )

    # Unlabeled Provo inline format: matched by format alone, so the
    # source label stays None and confidence is MEDIUM.
    provo = extract_case_identifier(
        "Tyson Reynolds requests a Zone Map Amendment "
        "from R1 to R2 for 2000 N Canyon Road. "
        "PLRZ20260116"
    )

    results.append(
        check(
            bool(provo)
            and provo["value"] == "PLRZ20260116"
            and provo["label"] is None
            and provo["confidence"] == "MEDIUM"
            and "PLRZ20260116" in provo["evidence"],
            "Unlabeled Provo inline number keeps provenance "
            "(label=None, confidence=MEDIUM, evidence present)",
        )
    )

    # Exact source preservation: no invented casing or reshaping.
    lowered = extract_case_identifier(
        "case cz-565 continued to next month"
    )

    results.append(
        check(
            bool(lowered)
            and lowered["value"] == "cz-565",
            'Exact source spelling preserved ("cz-565" '
            "is not uppercased or rewritten)",
        )
    )

    # Anti-fabrication: narrative "case" without an identifier-like
    # token must never yield an identifier.
    results.append(
        check(
            extract_case_identifier(
                "In this case the applicant asks for a "
                "continuance to September."
            )
            is None,
            'Narrative "in this case the applicant..." '
            "yields no identifier",
        )
    )

    results.append(
        check(
            extract_case_identifier(
                "Item 7 - Study Session on middle housing policy."
            )
            is None,
            "Study-session item with no identifier yields None "
            "(evidence-backed absence)",
        )
    )

    # The item's own header identifier outranks a related case
    # mentioned later in the same block.
    related = extract_case_identifier(
        "Case PUD-871 Staff Report\n"
        "(Related to case CZ-565 & Plat Clydesdale)"
    )

    results.append(
        check(
            bool(related)
            and related["value"] == "PUD-871"
            and len(find_case_identifiers(related_evidence_block()))
            >= 2,
            "Primary header identifier wins over later "
            "'Related to case' mention; both are findable",
        )
    )

    # Description terminates at any supported identifier format.
    results.append(
        check(
            extract_description(
                "Acme Development requests approval of a new "
                "data center. Case PUD-871 Staff Report"
            )
            == "approval of a new data center.",
            "Description ends at a non-Provo identifier "
            "('Case PUD-871') instead of swallowing it",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print()
    print(f"Checks passed: {passed}")
    print(f"Checks failed: {failed}")

    return failed == 0


def related_evidence_block():
    return (
        "Case PUD-871 Staff Report\n"
        "(Related to case CZ-565 & Plat Clydesdale)"
    )


# ============================================================
# LIVE DOCUMENT IDENTIFIER PROVENANCE
# ============================================================

def run_live_identifier_checks() -> None:
    """
    Show identifier provenance for every extracted application in the
    real Provo packet, plus the identifier found in the real Tulsa
    staff report -- and list agenda items where no identifier exists
    (evidence-backed absence, not fabrication).
    """

    import pymupdf

    print()
    print("=" * 80)
    print("LIVE IDENTIFIER PROVENANCE")
    print("=" * 80)

    # ------------------------------------------------------------
    # Tulsa staff report: jurisdiction-specific "Case <ID>" style.
    # ------------------------------------------------------------

    tulsa_path = Path("data/validation/PUD-871.pdf")

    if tulsa_path.exists():

        document = pymupdf.open(tulsa_path)
        tulsa_text = "\n".join(
            page.get_text("text")
            for page in document
        )
        document.close()

        identifier = extract_case_identifier(tulsa_text)

        if identifier:
            print()
            print("Tulsa staff report (data/validation/PUD-871.pdf):")
            print(f"  VALUE:      {identifier['value']}")
            print(f"  LABEL:      {identifier['label']}")
            print(f"  TYPE:       {identifier['type']}")
            print(f"  CONFIDENCE: {identifier['confidence']}")
            print(f"  EVIDENCE:   {identifier['evidence']!r}")
        else:
            print("[FAIL] No identifier found in PUD-871.pdf")

    # ------------------------------------------------------------
    # Provo packet: per-record provenance + items with no ID.
    # ------------------------------------------------------------

    if not PDF_PATH.exists():
        return

    text = read_pdf(PDF_PATH)

    applications = extract_applications(text)

    labeled = sum(
        1
        for application in applications
        if application.get("application_id_label")
    )

    print()
    print(
        f"Provo packet ({PDF_PATH.name}): "
        f"{len(applications)} applications, "
        f"{labeled} with an explicit source label, "
        f"{len(applications) - labeled} matched by format alone:"
    )

    for application in applications:

        print(
            f"  {application.get('application_number'):<14} "
            f"| label={application.get('application_id_label')!s:<6} "
            f"| type={application.get('application_id_type')!s:<12} "
            f"| conf={application.get('application_id_confidence')}"
        )

    agenda = extract_agenda_section(text)
    identified_items = {
        application.get("item")
        for application in applications
    }

    skipped = [
        item_number
        for item_number, _block in split_agenda_items(agenda)
        if item_number not in identified_items
    ]

    if skipped:
        print(
            f"  Agenda items with NO application identifier "
            f"(correctly not turned into records): {skipped}"
        )


# ============================================================
# PROPERTY ADDRESS EXTRACTION REGRESSION CHECKS
# ============================================================

def run_property_address_checks() -> bool:
    """
    Regression coverage for full property address intelligence:

    - labeled anchors (Property Address / Site Address / Project
      Address / Property Location) with same-line and following-line
      values,
    - located-at agenda style ("located at 2000 N Canyon Road."),
    - unit tails ("Suite 210"), city/state/ZIP comma tails, and their
      combination,
    - honest area_description capture for legal-description anchors
      (real Tulsa PUD-871.pdf wording),
    - evidence-backed absence: no address in the block means all
      property_address_* fields stay None -- never a fabricated one,
    - component parsing (street number/name/unit/city/state/ZIP).
    """

    print()
    print("=" * 80)
    print("PROPERTY ADDRESS EXTRACTION CHECKS")
    print("=" * 80)

    results = []

    def fields(block):
        intel = extract_property_address(block)
        return intel

    # --------------------------------------------------------
    # Located-at agenda style (Provo).
    # --------------------------------------------------------

    intel = fields(
        "PUBLIC HEARING - Petitioner Tyson Reynolds requests a Zone Map "
        "Amendment for the property located at 2000 N Canyon Road. "
        "Pleasant View Neighborhood. Dustin Wright 801-852-6415."
    )

    results.append(
        check(
            intel["property_address_full"] == "2000 N Canyon Road",
            'Located-at capture: full == "2000 N Canyon Road"',
        )
    )
    results.append(
        check(
            intel["property_address_completeness"] == "street_only",
            "Located-at completeness is street_only (no invented city/state)",
        )
    )
    results.append(
        check(
            intel["property_address_components"]["street_number"] == "2000"
            and intel["property_address_components"]["street_name"]
            == "N Canyon Road",
            "Located-at components split number and street name",
        )
    )
    results.append(
        check(
            intel["property_address_source"] == "government_record"
            and intel["property_address_confidence"] == "HIGH",
            "Located-at provenance is government_record/HIGH",
        )
    )
    results.append(
        check(
            "2000 N Canyon Road" in (intel["property_address_evidence"] or ""),
            "Located-at evidence quotes the source text",
        )
    )

    # --------------------------------------------------------
    # Full postal form.
    # --------------------------------------------------------

    intel = fields(
        "Property Address: 1507 South 180 East, Provo, UT 84601"
    )

    results.append(
        check(
            intel["property_address_full"]
            == "1507 South 180 East, Provo, UT 84601",
            'Labeled anchor keeps the full postal form verbatim',
        )
    )
    results.append(
        check(
            intel["property_address_completeness"] == "full_postal",
            "Full form classifies as full_postal",
        )
    )
    comps = intel["property_address_components"]
    results.append(
        check(
            comps["city"] == "Provo"
            and comps["state"] in ("UT", "Utah")
            and comps["postal_code"] == "84601",
            "Full-form components carry city/state/ZIP",
        )
    )

    # --------------------------------------------------------
    # Unit tail plus city/state (no ZIP present -> no invented ZIP).
    # --------------------------------------------------------

    intel = fields(
        "Site Address: 500 Main Street Suite 210, Provo, Utah"
    )

    results.append(
        check(
            intel["property_address_completeness"] == "street_city_state",
            "Unit + city/state without ZIP stays street_city_state",
        )
    )
    comps = intel["property_address_components"]
    results.append(
        check(
            comps["unit"] == "210"
            and comps["city"] == "Provo"
            and comps["postal_code"] is None,
            "Unit captured and missing ZIP stays None",
        )
    )

    # --------------------------------------------------------
    # Area description (real Tulsa PUD-871.pdf anchor wording).
    # --------------------------------------------------------

    intel = fields(
        "2. Property Location\nWest of North Sheridan Road between East "
        "76th Street North and East 86th Street North.\nTract Size: "
        "+506 acres"
    )

    results.append(
        check(
            intel["property_address_full"]
            == "West of North Sheridan Road between East 76th Street North "
            "and East 86th Street North",
            "Legal description captured verbatim under Property Location",
        )
    )
    results.append(
        check(
            intel["property_address_completeness"] == "area_description",
            "Non-street location classifies honestly as area_description",
        )
    )

    # --------------------------------------------------------
    # Evidence-backed absence.
    # --------------------------------------------------------

    intel = fields(
        "ORDINANCE TEXT AMENDMENT - Request to amend the zoning map "
        "text regarding accessory dwelling units citywide."
    )

    results.append(
        check(
            intel["property_address_full"] is None
            and intel["property_address_evidence"] is None
            and intel["property_address_completeness"] is None,
            "No address in block -> evidence-backed None everywhere",
        )
    )

    # --------------------------------------------------------
    # parse_address_components on an already-captured string.
    # --------------------------------------------------------

    comps = parse_address_components(
        "1507 South 180 East, Provo, UT 84601"
    )

    results.append(
        check(
            comps["street_number"] == "1507"
            and comps["street_name"].lower().startswith("south 180 east")
            and comps["city"] == "Provo"
            and comps["state"] in ("UT", "Utah")
            and comps["postal_code"] == "84601",
            "parse_address_components splits a full postal string",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print()
    print(f"Checks passed: {passed}")
    print(f"Checks failed: {failed}")

    return failed == 0


def run_live_property_address_checks() -> bool:
    """
    Live-document checks: the real Provo packet must keep its
    historical project_address values byte-identical while gaining
    property_address_full from agenda blocks, and the Tulsa staff
    report must yield its area description.
    """

    print()
    print("=" * 80)
    print("LIVE PROPERTY ADDRESS PROVENANCE CHECKS")
    print("=" * 80)

    results = []

    text = read_pdf(PDF_PATH)

    applications = extract_applications(text)

    by_number = {
        application.get("application_number"): application
        for application in applications
    }

    plrz = by_number.get("PLRZ20260116")

    results.append(
        check(
            plrz is not None
            and plrz.get("project_address") == "2000 N Canyon Road",
            "Live Provo: legacy project_address unchanged",
        )
    )
    results.append(
        check(
            plrz is not None
            and plrz.get("property_address_full") == "2000 N Canyon Road"
            and plrz.get("property_address_completeness") == "street_only",
            "Live Provo: property_address_full populated from agenda block",
        )
    )

    ordinance = [
        application
        for application in applications
        if application.get("application_type") == "Ordinance Text Amendment"
    ]

    results.append(
        check(
            ordinance
            and all(application.get("property_address_full") is None for application in ordinance),
            "Live Provo: addressless ordinance items keep None (no fabrication)",
        )
    )

    tulsa_path = Path("data/validation/PUD-871.pdf")

    if tulsa_path.exists():

        tulsa_text = read_pdf(tulsa_path)

        tulsa_apps = extract_applications(tulsa_text)

        tulsa_addresses = [
            application.get("property_address_full")
            for application in tulsa_apps
        ]

        results.append(
            check(
                any(
                    address
                    and address.startswith("West of North Sheridan Road")
                    for address in tulsa_addresses
                ),
                "Live Tulsa PUD-871.pdf: area description preserved",
            )
        )

    else:
        print(f"[SKIP] live Tulsa fixture not found: {tulsa_path}")

    passed = sum(results)
    failed = len(results) - passed

    print()
    print(f"Checks passed: {passed}")
    print(f"Checks failed: {failed}")

    return failed == 0


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

    # --------------------------------------------------------
    # 5. Application type phrasing regression checks
    # --------------------------------------------------------

    regression_passed = run_application_type_regression_checks()

    # --------------------------------------------------------
    # 6. Case identifier extraction regression checks
    # --------------------------------------------------------

    identifier_checks_passed = run_case_identifier_checks()

    # --------------------------------------------------------
    # 7. Live document identifier provenance
    # --------------------------------------------------------

    run_live_identifier_checks()

    # --------------------------------------------------------
    # 8. Property address extraction regression checks
    # --------------------------------------------------------

    property_address_passed = run_property_address_checks()

    # --------------------------------------------------------
    # 9. Live property address provenance
    # --------------------------------------------------------

    live_property_address_passed = run_live_property_address_checks()

    print()
    print("=" * 80)
    print("APPLICATION EXTRACTION TEST COMPLETE")
    print("=" * 80)

    if (
        not regression_passed
        or not identifier_checks_passed
        or not property_address_passed
        or not live_property_address_passed
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()