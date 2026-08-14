"""
PermitSignal Identity + Contact Intelligence Tests (Phase 10)

Covers the extensions made to move beyond "owner not found":

    1. application_extractor.PARTY_ROLE_LABELS / extract_parties() --
       broadened government-record-labeled role vocabulary (Contractor,
       Attorney, Developer, Representative in addition to Engineer/
       Architect/Surveyor/Landscape Architect).
    2. application_extractor.extract_staff_report_identity() -- Property
       Owner / Applicant-of-Record evidence from a specific application's
       own staff-report routing table elsewhere in the full packet.
    3. applicant_enrichment.ROLE_LABELS / find_role_person_mentions() --
       broadened public-web role vocabulary (Developer, Representative,
       Agent, Attorney, Contractor, Architect, Engineer, Project Manager)
       in addition to the existing ownership-tier roles.
    4. opportunity_builder._contact_tier() -- now also recognizes owner/
       applicant-of-record contact fields and a contactable project party,
       not just applicant_email/contact_email.
    5. commercial_lead_intelligence.find_contactable_party() /
       classify_contactability() / recommend_commercial_action() -- a
       contactable non-owner party (architect/engineer/contractor/
       attorney/developer/representative) is real commercial contact
       evidence, with a role-aware recommended action.

Every scenario is deterministic (no PDF, no network) except the final
section, which runs against the real Provo packet already used by
scripts.test_pipeline_orchestrator.

Run from the project root:

    python -m scripts.test_identity_contact_intelligence
"""

from pathlib import Path

from backend.app.services.application_extractor import (
    extract_owner,
    extract_parties,
    extract_staff_report_identity,
)
from backend.app.services.applicant_enrichment import find_role_person_mentions
from backend.app.services.opportunity_builder import contact_tier, qualify_lead
from backend.app.services.commercial_lead_intelligence import (
    ACTION_CONTACT_PARTY,
    ACTION_INVESTIGATE_DECISION_MAKER,
    apply_commercial_intelligence,
    build_commercial_intelligence,
    find_contactable_party,
)
from backend.app.services.lead_repository import lead_to_row
from backend.app.services.pipeline_orchestrator import run_pipeline, DEFAULT_PDF
from datetime import date


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 90)
    print("PERMITSIGNAL IDENTITY + CONTACT INTELLIGENCE (PHASE 10)")
    print("=" * 90)

    results = []

    # ------------------------------------------------------------------------
    print("\n[1/6] Broadened government-record party role vocabulary (Phase 1)")

    routing_table = (
        "APPLICANT: Jane Smith\n"
        "PROPERTY OWNER: ABC Holdings LLC\n"
        "GENERAL CONTRACTOR: John Builder | jbuilder@buildco.com\n"
        "ATTORNEY OF RECORD: Alice Attorney | alice@lawfirm.com\n"
        "DEVELOPER OF RECORD: Big Development Co\n"
        "PARCEL ID: 12:345:6789\n"
    )

    parties = extract_parties(routing_table)
    roles_found = {p["party_role"] for p in parties}

    results.append(check("Contractor" in roles_found, "Extracts Contractor from 'General Contractor' label"))
    results.append(check("Attorney" in roles_found, "Extracts Attorney from 'Attorney of Record' label"))
    results.append(
        check(
            any(p["party_role"] == "Contractor" and p["party_contact_email"] == "jbuilder@buildco.com" for p in parties),
            "Contractor party carries its labeled email",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[2/6] Staff-report identity: owner evidence from elsewhere in the full packet")

    full_doc = (
        "Item 3\nJane Smith requests a Zone Map Amendment. PLRZ20990001\n\n"
        "Planning Commission Hearing Staff Report\n"
        "PLRZ20990001\n"
        "APPLICANT: \nJane Smith \n"
        "PROPERTY OWNER: \nRIVERSIDE HOLDINGS LLC \n"
        "PARCEL ID: \n11:222:3333 \n"
    )

    staff_identity = extract_staff_report_identity(full_doc, "PLRZ20990001")

    results.append(check(staff_identity["owner_entity"] == "RIVERSIDE HOLDINGS LLC", "Finds owner from staff-report routing table"))
    results.append(check(staff_identity["owner_source"] == "government_record", "Owner source is government_record"))
    results.append(check(staff_identity["owner_confidence"] == "HIGH", "Owner confidence is HIGH (labeled government evidence)"))

    print("\n[2/6] No fabrication: an application number with no staff-report block")

    no_staff_report = extract_staff_report_identity("Item 1\nUnrelated text. PLXX000\n", "PLXX000")
    results.append(check(no_staff_report["owner_entity"] is None, "No staff-report evidence -> owner_entity is None, not guessed"))
    results.append(check(no_staff_report["parties"] == [], "No staff-report evidence -> parties is empty, not guessed"))

    print("\n[2/6] Never attributes a DIFFERENT application's routing table")

    two_applications = (
        "Item 1\nFirst Person requests approval. PLAAA20260001\n"
        "Item 2\nSecond Person requests approval. PLBBB20260002\n\n"
        "Staff Report\nPLBBB20260002\nAPPLICANT: \nSecond Person \nPROPERTY OWNER: \nSECOND OWNER LLC \n"
    )

    first_app_identity = extract_staff_report_identity(two_applications, "PLAAA20260001")
    results.append(
        check(
            first_app_identity["owner_entity"] is None,
            "Application with no routing table of its own never inherits a different application's owner",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[3/6] Broadened public-web role vocabulary (Phase 2)")

    page_text = (
        "About Our Team. John Architect, Architect. Contact us for your next project. "
        "Jane Developer - Developer. Represented by Bob Agent, Representative."
    )

    mentions = find_role_person_mentions(page_text)
    mention_roles = {role for _name, role in mentions}

    results.append(check("Architect" in mention_roles, "Recognizes 'Name, Architect' pattern"))
    results.append(check("Developer" in mention_roles, "Recognizes 'Name - Developer' pattern"))
    results.append(check("Representative" in mention_roles, "Recognizes 'Name, Representative' pattern"))

    print("\n[3/6] Still rejects a company name masquerading as a person")

    company_text = "ABC Architects, Architect of record for this project."
    company_mentions = find_role_person_mentions(company_text)
    results.append(
        check(
            not any(name.lower().startswith("abc architects") for name, _role in company_mentions),
            "'ABC Architects, Architect' is not captured as a person name",
        )
    )

    # ------------------------------------------------------------------------
    print("\n[4/6] Contact tier recognizes owner/applicant-of-record/party contacts, not just applicant_email")

    owner_only = {
        "applicant_name": "Jane Smith",
        "owner_contact_email": "owner@riverside-holdings.com",
    }
    results.append(check(contact_tier(owner_only) == "strong", "Owner contact email alone yields a strong contact tier"))

    party_only = {
        "applicant_name": "Jane Smith",
        "parties": [
            {
                "party_name": "John Architect",
                "party_role": "Architect",
                "party_company": "ArchCo",
                "party_contact_email": "john@archco.com",
                "party_contact_phone": None,
                "party_source": "government_record",
                "party_confidence": "HIGH",
            }
        ],
    }
    results.append(check(contact_tier(party_only) == "strong", "A contactable Architect party alone yields a strong contact tier"))

    lead = qualify_lead({**party_only, "priority": "HIGH", "is_actionable": True, "has_future_opportunity": True})
    results.append(check(lead["lead_status"] == "CONTACTABLE", "A qualifying lead with only a party contact becomes CONTACTABLE, not NO_CONTACT"))

    no_contact_at_all = {"applicant_name": "Jane Smith", "parties": []}
    results.append(check(contact_tier(no_contact_at_all) == "none", "No contact anywhere (including parties) is still 'none'"))

    # ------------------------------------------------------------------------
    print("\n[5/6] Commercial intelligence recommends the specific contactable party, not just owner/applicant")

    party_opportunity = {
        "application_number": "PLTEST9001",
        "has_future_opportunity": True,
        "priority": "HIGH",
        "is_actionable": True,
        "parties": [
            {
                "party_name": "John Engineer",
                "party_role": "Engineer",
                "party_company": "EngCo",
                "party_contact_email": "john@engco.com",
                "party_contact_phone": None,
                "party_source": "government_record",
                "party_confidence": "HIGH",
            }
        ],
    }
    party_opportunity = qualify_lead(party_opportunity)
    party_opportunity.update(build_commercial_intelligence(party_opportunity))

    results.append(check(party_opportunity["commercial_readiness"] == "READY_FOR_OUTREACH", "Party-only contact reaches READY_FOR_OUTREACH"))
    results.append(check(party_opportunity["recommended_commercial_action"] == ACTION_CONTACT_PARTY, "Recommends contacting the specific party"))
    results.append(
        check(
            "John Engineer" in party_opportunity["commercial_action_reason"]
            and "Engineer" in party_opportunity["commercial_action_reason"],
            "Reason names the specific party and their role, not a generic placeholder",
        )
    )

    found_party = find_contactable_party(party_opportunity)
    results.append(check(found_party is not None and found_party["party_name"] == "John Engineer", "find_contactable_party() returns the winning party"))

    print("\n[5/6] A party with a name/role but no contact info is never treated as contactable")

    no_contact_party = {
        "application_number": "PLTEST9002",
        "has_future_opportunity": True,
        "priority": "HIGH",
        "is_actionable": True,
        "parties": [
            {
                "party_name": "Jane NoContact",
                "party_role": "Attorney",
                "party_company": None,
                "party_contact_email": None,
                "party_contact_phone": None,
                "party_source": "public_web",
                "party_confidence": "LOW",
            }
        ],
    }
    results.append(check(find_contactable_party(no_contact_party) is None, "A party with no email/phone is never fabricated into a usable contact"))

    # ------------------------------------------------------------------------
    print("\n[6/6] Real Provo packet: staff-report owner evidence and end-to-end wiring")

    if not Path(DEFAULT_PDF).exists():
        print("Skipping real-packet section: PDF not present.")
    else:
        result = run_pipeline(
            pdf_path=DEFAULT_PDF,
            reference_date=date(2026, 8, 1),
            live_enrichment=False,
            sync_to_supabase=False,
            verbose=False,
        )

        by_number = {o["application_number"]: o for o in result["opportunities"]}

        reynolds = by_number.get("PLRZ20260116")
        nelson = by_number.get("PLPPA20250700")
        morgan = by_number.get("PLRZ20260264")

        results.append(
            check(
                bool(reynolds) and reynolds.get("owner_entity") == "REYNOLDS ASSET MANAGEMENT LLC",
                "Real packet: Tyson Reynolds' project owner is found (REYNOLDS ASSET MANAGEMENT LLC)",
            )
        )

        # Regression coverage for the production bug where PLRZ20260116's
        # staff-report-derived owner evidence never reached the final lead
        # returned by the API (owner_name/owner_entity/owner_type null,
        # recommended_commercial_action stuck on the no-identity-at-all
        # "enrich missing contact information" action). The staff-report
        # extraction itself was already covered above; this closes the
        # loop end-to-end through commercial intelligence and the
        # Supabase row-mapping boundary so a future regression here is
        # caught by this test instead of only showing up as stale/null
        # production data.
        results.append(
            check(
                bool(reynolds) and reynolds.get("owner_name") == "REYNOLDS ASSET MANAGEMENT LLC",
                "Real packet: owner_name (not just owner_entity) is populated for Tyson Reynolds",
            )
        )
        results.append(
            check(
                bool(reynolds)
                and reynolds.get("recommended_commercial_action") == ACTION_INVESTIGATE_DECISION_MAKER
                and "REYNOLDS ASSET MANAGEMENT LLC" in (reynolds.get("commercial_action_reason") or ""),
                "Real packet: known-owner-no-contact correctly recommends investigating the "
                "decision-maker by name, not the generic 'no identity at all' action",
            )
        )
        if reynolds:
            reynolds_row = lead_to_row(reynolds)
            results.append(
                check(
                    reynolds_row.get("owner_entity") == "REYNOLDS ASSET MANAGEMENT LLC"
                    and reynolds_row.get("owner_name") == "REYNOLDS ASSET MANAGEMENT LLC",
                    "Real packet: owner evidence survives the Supabase row-mapping boundary "
                    "(lead_repository.lead_to_row), so a synced lead never regresses to null",
                )
            )

        results.append(
            check(
                bool(nelson) and nelson.get("owner_entity") == "TRACE LLC",
                "Real packet: Bret Nelson's project owner is found (TRACE LLC)",
            )
        )
        results.append(
            check(
                bool(morgan) and morgan.get("owner_entity") == "PEARSON, JOSEPH BYRD (ET AL); ADAMS, SUANN P (ET AL)",
                "Real packet: multi-owner list separator (;) is preserved, not stripped",
            )
        )
        results.append(
            check(
                all(o.get("owner_source") in (None, "government_record") for o in result["opportunities"]),
                "Real packet: every populated owner_source is government_record, never fabricated",
            )
        )
        results.append(
            check(
                all(o.get("owner_confidence") in (None, "HIGH") for o in result["opportunities"]),
                "Real packet: every populated owner_confidence is HIGH (labeled routing-table evidence)",
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
