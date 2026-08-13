"""
PermitSignal Applicant Identity & Contact Intelligence tests.

Run from project root:

    python -m scripts.test_applicant_identity
"""

from backend.app.services.applicant_identity import (
    ApplicantEnricher,
    build_search_queries,
    clean_applicant_name,
    confidence_label,
    domain_of,
    extract_emails,
    extract_phones,
    is_generic_email,
    is_placeholder_email,
    merge_identity_into_opportunity,
    score_email_candidate,
    validate_email,
)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 80)
    print("PERMITSIGNAL APPLICANT IDENTITY & CONTACT INTELLIGENCE")
    print("=" * 80)

    results = []

    print("\n[1/8] Name and basic normalization")

    results.append(
        check(
            clean_applicant_name(" Jared Morgan ") == "Jared Morgan",
            "Normalizes applicant name",
        )
    )

    results.append(
        check(
            domain_of("jared@example.com") == "example.com",
            "Extracts email domain",
        )
    )

    results.append(
        check(
            domain_of("https://www.example.com/contact") == "www.example.com",
            "Extracts website domain",
        )
    )

    print("\n[2/8] Email extraction")

    text = """
    Contact Jared Morgan at jared.morgan@acme-development.com
    or office@acme-development.com.
    Invalid placeholder: test@example.com.
    """

    emails = extract_emails(text)

    results.append(
        check(
            "jared.morgan@acme-development.com" in emails,
            "Extracts named email",
        )
    )

    results.append(
        check(
            "office@acme-development.com" in emails,
            "Extracts generic company email",
        )
    )

    results.append(
        check(
            is_placeholder_email("test@example.com"),
            "Rejects placeholder domain",
        )
    )

    results.append(
        check(
            validate_email("jared.morgan@acme-development.com"),
            "Accepts valid email",
        )
    )

    print("\n[3/8] Phone extraction")

    phones = extract_phones(
        "Call Jared at (801) 555-1212 or 801-555-3434."
    )

    results.append(
        check(
            len(phones) == 2,
            "Extracts two phone numbers",
        )
    )

    print("\n[4/8] Email candidate scoring")

    score = score_email_candidate(
        email="jared.morgan@acme-development.com",
        applicant_name="Jared Morgan",
        project_address="113/191 N Geneva Road",
        source_url="https://acme-development.com/contact",
        evidence_type="official_site",
    )

    results.append(
        check(
            score >= 0.80,
            f"Named email from official site scores HIGH ({score})",
        )
    )

    results.append(
        check(
            is_generic_email("office@acme-development.com"),
            "Detects generic mailbox",
        )
    )

    print("\n[5/8] Search query construction")

    queries = build_search_queries(
        "Jared Morgan",
        "113/191 N Geneva Road",
        "Provo",
        "Utah",
    )

    results.append(
        check(
            any("Jared Morgan" in q and "113/191 N Geneva Road" in q for q in queries),
            "Search query contains applicant and address",
        )
    )

    results.append(
        check(
            any("Jared Morgan" in q and "email" in q.lower() for q in queries),
            "Search query includes contact discovery",
        )
    )

    print("\n[6/8] Deterministic enrichment without live search")

    application = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "project_address": "113/191 N Geneva Road",
        "application_type": "Zone Map Amendment",
        "municipality": "Provo",
        "state": "Utah",
    }

    enricher = ApplicantEnricher(api_key=None)
    identity = enricher.enrich(
        application,
        live_search=False,
    )

    results.append(
        check(
            identity["applicant_name"] == "Jared Morgan",
            "Preserves applicant name",
        )
    )

    results.append(
        check(
            identity["enrichment_status"] == "search_disabled",
            "Reports disabled live search",
        )
    )

    results.append(
        check(
            identity["applicant_email"] is None,
            "Does not invent an applicant email",
        )
    )

    print("\n[7/8] Government-record contact precedence")

    application_with_contact = {
        **application,
        "applicant_email": "jared@government-record.example",
        "applicant_phone": "(801) 555-1000",
        "source_url": "https://www.provo.gov/AgendaCenter/",
    }

    identity2 = enricher.enrich(
        application_with_contact,
        live_search=False,
    )

    results.append(
        check(
            identity2["applicant_email"] == "jared@government-record.example",
            "Preserves supplied government-record email",
        )
    )

    results.append(
        check(
            identity2["email_confidence"] == "HIGH",
            "Government-record email receives HIGH confidence",
        )
    )

    results.append(
        check(
            identity2["applicant_phone"] == "(801) 555-1000",
            "Preserves supplied government-record phone",
        )
    )

    print("\n[8/8] Merge into canonical opportunity")

    opportunity = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "priority": "HIGH",
        "has_future_opportunity": True,
    }

    merged = merge_identity_into_opportunity(
        opportunity,
        identity2,
    )

    results.append(
        check(
            merged["application_number"] == "PLRZ20260264",
            "Preserves opportunity identity",
        )
    )

    results.append(
        check(
            merged["applicant_email"] == "jared@government-record.example",
            "Adds applicant email to opportunity",
        )
    )

    results.append(
        check(
            merged["email_confidence"] == "HIGH",
            "Carries email confidence",
        )
    )

    results.append(
        check(
            merged["enrichment_status"] == "search_disabled",
            "Carries enrichment status",
        )
    )

    passed = sum(results)
    failed = len(results) - passed

    print("\n" + "=" * 80)
    print(f"TESTS: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()