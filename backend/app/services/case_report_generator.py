"""
PermitSignal Case Report Generator
===================================

Purpose
-------
Render an already-canonical PermitSignal lead record -- the same shape
produced by pipeline_orchestrator.run_and_save() / stored under
"lead_queue" in data/output/permitsignal_opportunities.json -- into a
formal, printable PDF "Property Intelligence Case Report."

This module performs NO extraction, scoring, or enrichment of its own.
It only reads fields the pipeline has already computed and renders them.
Every missing field renders an explicit fallback (NOT FOUND /
OWNERSHIP NOT ESTABLISHED / UNVERIFIED) rather than inventing a value,
per CLAUDE.md sections 6 and 9 (Contact Integrity / PDF Evidence and
Truth). "SOURCE FACT" (raw government-record evidence) is always
labeled separately from "PERMITSIGNAL ANALYSIS" (this system's computed
interpretation), per CLAUDE.md Part 9.

The document identifies itself as a PermitSignal-generated internal work
product -- it never claims government/municipal authorship.

Public API
----------
load_lead_by_application_number(application_number, output_path=DEFAULT_OUTPUT)
generate_case_report_pdf(lead) -> bytes
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.services.pipeline_orchestrator import DEFAULT_OUTPUT


# ============================================================================
# CONSTANTS -- palette / layout
# ============================================================================

PAGE_SIZE = LETTER
MARGIN = 0.65 * inch

INK = colors.HexColor("#20232a")
MUTED = colors.HexColor("#63666b")
FAINT = colors.HexColor("#8a8d92")
BRASS = colors.HexColor("#a97a2f")
HAIRLINE = colors.HexColor("#d8d3c8")

NOT_FOUND = "NOT FOUND"
OWNERSHIP_NOT_ESTABLISHED = "OWNERSHIP NOT ESTABLISHED"
UNVERIFIED = "UNVERIFIED"

_STYLES = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    "CaseTitle", parent=_STYLES["Title"], fontName="Helvetica-Bold",
    fontSize=16, leading=18, textColor=INK, spaceAfter=2, alignment=0,
)
STYLE_TITLE2 = ParagraphStyle(
    "CaseTitle2", parent=STYLE_TITLE, fontSize=12.5, textColor=MUTED,
)
STYLE_SUBTITLE = ParagraphStyle(
    "CaseSubtitle", parent=_STYLES["Normal"], fontName="Helvetica-Bold",
    fontSize=8.5, textColor=BRASS, spaceAfter=10, alignment=0,
)
STYLE_SECTION = ParagraphStyle(
    "SectionHeading", parent=_STYLES["Heading2"], fontName="Helvetica-Bold",
    fontSize=11.5, textColor=INK, spaceBefore=14, spaceAfter=4,
)
STYLE_SUBSECTION = ParagraphStyle(
    "SubsectionHeading", parent=_STYLES["Heading3"], fontName="Helvetica-Bold",
    fontSize=9.5, textColor=INK, spaceBefore=8, spaceAfter=3,
)
STYLE_BODY = ParagraphStyle(
    "Body", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=9, textColor=INK, leading=13,
)
STYLE_LABEL = ParagraphStyle(
    "Label", parent=_STYLES["Normal"], fontName="Helvetica-Bold",
    fontSize=8, textColor=MUTED, leading=11,
)
STYLE_TAG = ParagraphStyle(
    "Tag", parent=_STYLES["Normal"], fontName="Helvetica-Bold",
    fontSize=7.5, textColor=BRASS, leading=10, spaceAfter=3,
)
STYLE_SMALL = ParagraphStyle(
    "Small", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=8, textColor=MUTED, leading=11,
)


# ============================================================================
# FALLBACK-SAFE TEXT HELPERS -- no field ever renders a fabricated value.
# ============================================================================

def _text(value: Any, fallback: str = NOT_FOUND) -> str:
    """Real value verbatim, or an explicit evidence-backed fallback -- never a guess."""
    if value is None:
        return fallback
    if isinstance(value, (list, tuple, dict)) and not value:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _esc(value: str) -> str:
    return _xml_escape(value)


def _p(value: Any, fallback: str = NOT_FOUND, style: ParagraphStyle = STYLE_BODY) -> Paragraph:
    return Paragraph(_esc(_text(value, fallback)), style)


# ============================================================================
# PARTY / OWNERSHIP HELPERS -- mirror dashboard/src/lib/lead-helpers.ts
# (getPrimaryOwnerDisplay / isOwnerKnown / getPartiesByRole) so the PDF and
# the dashboard never disagree about who counts as "the owner."
# ============================================================================

def _is_owner_known(lead: dict) -> bool:
    return bool(lead.get("owner_name") or lead.get("owner_entity"))


def _primary_owner(lead: dict) -> Optional[str]:
    return lead.get("owner_entity") or lead.get("owner_name")


def _owner_contact_name(lead: dict) -> Optional[str]:
    primary = _primary_owner(lead)
    contact = lead.get("owner_contact_name")
    if contact:
        return contact
    owner_name = lead.get("owner_name")
    if owner_name and owner_name != primary:
        return owner_name
    return None


def _parties_by_role(lead: dict) -> tuple[Optional[dict], Optional[dict], list[dict]]:
    parties = lead.get("parties") or []
    engineer = next((p for p in parties if "engineer" in (p.get("party_role") or "").lower()), None)
    architect = next((p for p in parties if "architect" in (p.get("party_role") or "").lower()), None)
    others = [p for p in parties if p is not engineer and p is not architect]
    return engineer, architect, others


def _friction_events(lead: dict) -> list[dict]:
    # The promoted friction_events column is currently always [] for this
    # pipeline -- the real evidence lives in the raw "events" field. See
    # dashboard/src/lib/lead-helpers.ts's getFrictionEvidence() for the
    # equivalent fallback on the frontend side.
    return lead.get("friction_events") or lead.get("events") or []


# ============================================================================
# SHARED FLOWABLE BUILDERS
# ============================================================================

def _section_heading(number_and_title: str) -> list:
    return [
        Paragraph(number_and_title, STYLE_SECTION),
        HRFlowable(width="100%", thickness=0.75, color=BRASS, spaceAfter=6),
    ]


def _kv_table(rows: list[tuple[str, Any]], fallback: str = NOT_FOUND) -> Table:
    data = [[_p(label, style=STYLE_LABEL), _p(value, fallback)] for label, value in rows]
    table = Table(data, colWidths=[1.7 * inch, 4.85 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, HAIRLINE),
    ]))
    return table


def _evidence_table_style() -> TableStyle:
    return TableStyle([
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, BRASS),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, HAIRLINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


# ============================================================================
# SECTION BUILDERS -- each returns a list of flowables for the story.
# ============================================================================

def _build_title_block(lead: dict) -> list:
    review_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header_table = Table(
        [
            [_p("Jurisdiction", style=STYLE_LABEL), _p(lead.get("municipality")),
             _p("Case Number", style=STYLE_LABEL), _p(lead.get("application_number"))],
            [_p("Property", style=STYLE_LABEL), _p(lead.get("project_address")),
             _p("Review Date", style=STYLE_LABEL), _p(review_date)],
            [_p("Source Packet", style=STYLE_LABEL), _p(lead.get("source")),
             _p("Source URL", style=STYLE_LABEL), _p(lead.get("source_url"))],
        ],
        colWidths=[0.85 * inch, 2.6 * inch, 0.85 * inch, 2.25 * inch],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [
        Paragraph("PERMITSIGNAL", STYLE_TITLE),
        Paragraph("PROPERTY INTELLIGENCE CASE REPORT", STYLE_TITLE2),
        Paragraph("DRAFT — INTERNAL PROPERTY INTELLIGENCE REVIEW · NOT A GOVERNMENT RECORD", STYLE_SUBTITLE),
        HRFlowable(width="100%", thickness=1.2, color=BRASS, spaceAfter=10),
        header_table,
        Spacer(1, 10),
    ]


def _build_case_identification(lead: dict) -> list:
    engineer, architect, _others = _parties_by_role(lead)
    owner_known = _is_owner_known(lead)

    rows = [
        ("Property Owner", _primary_owner(lead) if owner_known else None),
        ("Owner Contact", _owner_contact_name(lead)),
        ("Applicant / Agent", lead.get("applicant_name")),
        ("Applicant Contact", lead.get("applicant_contact_name") or lead.get("contact_name")),
        ("Engineer", engineer.get("party_name") if engineer else None),
        ("Architect", architect.get("party_name") if architect else None),
        ("Property Address", lead.get("project_address")),
        ("Parcel", lead.get("parcel_number")),
        ("Zoning", lead.get("zoning")),
        ("Acreage", lead.get("acreage")),
        ("Municipality", lead.get("municipality")),
        ("Government Staff", lead.get("staff_contact_name")),
        ("Application Type", lead.get("application_type")),
        ("Application Status", lead.get("status") or lead.get("lead_status")),
    ]
    fallback_rows = [(label, value, OWNERSHIP_NOT_ESTABLISHED if label == "Property Owner" else NOT_FOUND) for label, value in rows]
    data = [[_p(label, style=STYLE_LABEL), _p(value, fb)] for label, value, fb in fallback_rows]
    table = Table(data, colWidths=[1.7 * inch, 4.85 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, HAIRLINE),
    ]))

    return [
        *_section_heading("1. CASE IDENTIFICATION"),
        KeepTogether([table]),
        Spacer(1, 6),
    ]


def _build_parties(lead: dict) -> list:
    engineer, architect, others = _parties_by_role(lead)
    owner_known = _is_owner_known(lead)
    owner_primary = _primary_owner(lead)
    owner_contact = _owner_contact_name(lead)

    flow = _section_heading("2. PARTIES — ROLES &amp; RESPONSIBILITIES")

    # 2.1 Property Owner / Principal
    owner_block = [Paragraph("2.1 PROPERTY OWNER / PRINCIPAL", STYLE_SUBSECTION)]
    if owner_known:
        contact_clause = f", contact {_esc(_text(owner_contact))}" if owner_contact else ""
        owner_block.append(Paragraph(
            f"Named on record as <b>{_esc(_text(owner_primary))}</b>{contact_clause}. "
            f"Source: {_esc(_text(lead.get('owner_source'), UNVERIFIED))}. "
            f"Confidence: {_esc(_text(lead.get('owner_confidence'), UNVERIFIED))}.",
            STYLE_BODY,
        ))
    else:
        owner_block.append(Paragraph(
            f"<b>{OWNERSHIP_NOT_ESTABLISHED}.</b> The source document does not label a property owner "
            "distinct from the applicant. PermitSignal does not substitute the applicant's name into the "
            "owner field -- this is an evidence-backed absence, not a missing-data gap.",
            STYLE_BODY,
        ))
    flow.append(KeepTogether(owner_block))
    flow.append(Spacer(1, 4))

    # 2.2 Applicant / Agent
    applicant_block = [Paragraph("2.2 APPLICANT / AGENT", STYLE_SUBSECTION)]
    applicant_name = lead.get("applicant_name")
    if applicant_name:
        if not owner_known:
            relationship = "Property Owner not established -- relationship to any owner is unconfirmed."
        elif applicant_name == owner_primary:
            relationship = "Also the Property Owner on this record."
        else:
            relationship = "Distinct from the Property Owner."
        applicant_block.append(Paragraph(
            f"Named on record as <b>{_esc(_text(applicant_name))}</b>. {relationship} "
            f"Source: {_esc(_text(lead.get('applicant_source'), UNVERIFIED))}. "
            f"Confidence: {_esc(_text(lead.get('applicant_confidence'), UNVERIFIED))}.",
            STYLE_BODY,
        ))
    else:
        applicant_block.append(Paragraph(f"<b>{NOT_FOUND}.</b> No applicant of record.", STYLE_BODY))
    flow.append(KeepTogether(applicant_block))
    flow.append(Spacer(1, 4))

    # 2.3 Engineer / Architect
    eng_arch_block = [Paragraph("2.3 ENGINEER / ARCHITECT", STYLE_SUBSECTION)]
    if engineer or architect or others:
        lines = []
        if engineer:
            lines.append(f"Engineer: <b>{_esc(_text(engineer.get('party_name')))}</b> ({_esc(_text(engineer.get('party_company'), 'company not on record'))})")
        if architect:
            lines.append(f"Architect: <b>{_esc(_text(architect.get('party_name')))}</b> ({_esc(_text(architect.get('party_company'), 'company not on record'))})")
        for party in others:
            lines.append(f"{_esc(_text(party.get('party_role'), 'Other Party'))}: <b>{_esc(_text(party.get('party_name')))}</b>")
        eng_arch_block.append(Paragraph("<br/>".join(lines), STYLE_BODY))
    else:
        eng_arch_block.append(Paragraph(
            f"{NOT_FOUND}. No engineer, architect, or other licensed professional named on record.", STYLE_BODY,
        ))
    flow.append(KeepTogether(eng_arch_block))
    flow.append(Spacer(1, 4))

    # 2.4 Government Staff
    staff_block = [Paragraph("2.4 GOVERNMENT STAFF", STYLE_SUBSECTION)]
    if lead.get("staff_contact_name") or lead.get("staff_contact_email") or lead.get("staff_contact_phone"):
        staff_block.append(Paragraph(
            f"<b>{_esc(_text(lead.get('staff_contact_name')))}</b> — "
            f"{_esc(_text(lead.get('staff_contact_email')))} / {_esc(_text(lead.get('staff_contact_phone')))}. "
            "Government-side personnel of record. Never a commercial or applicant party.",
            STYLE_BODY,
        ))
    else:
        staff_block.append(Paragraph(f"{NOT_FOUND}. No government staff contact on record.", STYLE_BODY))
    flow.append(KeepTogether(staff_block))
    flow.append(Spacer(1, 6))

    return flow


def _build_project_intelligence(lead: dict) -> list:
    upcoming = bool(lead.get("has_future_opportunity") and lead.get("next_project_date"))
    if upcoming:
        time_clause = f" at {_text(lead.get('next_project_time'))}" if lead.get("next_project_time") else ""
        event_line = (
            f"{_text(lead.get('next_project_event'))} on {_text(lead.get('next_project_date'))}{time_clause} "
            f"— urgency {_text(lead.get('urgency'))}, {_text(lead.get('days_until_event'))} day(s) out."
        )
    else:
        event_line = "No upcoming project event on record."

    rows = [
        ("Application History", lead.get("application_type")),
        ("Current Status", lead.get("lead_status")),
        ("Project Description", lead.get("description") or lead.get("project_description")),
        ("Next Event", event_line),
    ]
    return [
        *_section_heading("3. PROJECT / APPLICATION INTELLIGENCE"),
        KeepTogether([_kv_table(rows)]),
        Spacer(1, 6),
    ]


def _build_friction(lead: dict) -> list:
    friction_score = lead.get("friction_score") or 0
    signals = lead.get("friction_signals") or []
    events = _friction_events(lead)

    flow = _section_heading("4. HISTORICAL FRICTION")

    analysis_block = [
        Paragraph("PERMITSIGNAL ANALYSIS", STYLE_TAG),
        Paragraph(
            f"Friction score <b>{friction_score}</b>. Signals: {_esc(_text(', '.join(signals) if signals else None))}. "
            "This score is PermitSignal's computed interpretation of the source evidence below -- "
            "not a government determination.",
            STYLE_BODY,
        ),
    ]
    flow.append(KeepTogether(analysis_block))
    flow.append(Spacer(1, 4))

    if events:
        flow.append(Paragraph("SOURCE FACT — Historical Evidence", STYLE_TAG))
        rows = [[_p("Date", style=STYLE_LABEL), _p("Event", style=STYLE_LABEL), _p("Severity", style=STYLE_LABEL),
                 _p("Confidence", style=STYLE_LABEL), _p("Evidence", style=STYLE_LABEL)]]
        for event in events:
            rows.append([
                _p(event.get("event_date"), style=STYLE_SMALL),
                _p(event.get("event_type"), style=STYLE_SMALL),
                _p(event.get("severity"), UNVERIFIED, STYLE_SMALL),
                _p(event.get("confidence"), UNVERIFIED, STYLE_SMALL),
                _p(_text(event.get("evidence"))[:400], style=STYLE_SMALL),
            ])
        table = Table(rows, colWidths=[0.65 * inch, 1.0 * inch, 0.65 * inch, 0.7 * inch, 3.0 * inch], repeatRows=1)
        table.setStyle(_evidence_table_style())
        flow.append(table)
    else:
        flow.append(Paragraph("SOURCE FACT — No historical friction evidence on record.", STYLE_SMALL))
    flow.append(Spacer(1, 6))
    return flow


def _build_contact_intelligence(lead: dict) -> list:
    owner_contact = _owner_contact_name(lead)
    verified = bool(lead.get("contact_is_verified"))
    public = bool(lead.get("contact_is_public"))
    verification = "VERIFIED" if verified else ("PUBLIC — UNVERIFIED" if public else UNVERIFIED)

    # Identity/value fields render an evidence-absence as NOT FOUND; only
    # the verification-status-shaped fields below use UNVERIFIED, per
    # CLAUDE.md Part 9 ("If a contact isn't verified: UNVERIFIED" is
    # distinct from "If something isn't found: NOT FOUND").
    identity_rows = [
        ("Owner Contact", owner_contact),
        ("Owner Contact Email", lead.get("owner_contact_email")),
        ("Owner Contact Phone", lead.get("owner_contact_phone")),
        ("Applicant Contact", lead.get("contact_name") or lead.get("applicant_contact_name")),
        ("Applicant Email", lead.get("applicant_email") or lead.get("contact_email")),
        ("Applicant Phone", lead.get("applicant_phone") or lead.get("contact_phone")),
        ("Company", lead.get("company_name")),
        ("Website", lead.get("company_website") or lead.get("owner_website")),
        ("LinkedIn", lead.get("linkedin_url")),
    ]
    verification_rows = [
        ("Source", lead.get("contact_source") or lead.get("email_source") or lead.get("phone_source")),
        ("Confidence", lead.get("contact_confidence") or lead.get("email_confidence")),
        ("Verification Status", verification),
    ]

    data = [[_p(label, style=STYLE_LABEL), _p(value, NOT_FOUND)] for label, value in identity_rows]
    data += [[_p(label, style=STYLE_LABEL), _p(value, UNVERIFIED)] for label, value in verification_rows]
    table = Table(data, colWidths=[1.7 * inch, 4.85 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, HAIRLINE),
    ]))

    return [
        *_section_heading("5. CONTACT INTELLIGENCE"),
        KeepTogether([table]),
        Spacer(1, 6),
    ]


def _build_follow_up(lead: dict) -> list:
    reason = lead.get("opportunity_reason")
    contact_target = _owner_contact_name(lead) or lead.get("contact_name") or lead.get("applicant_name")
    friction_score = lead.get("friction_score") or 0
    signals = lead.get("friction_signals") or []
    upcoming = bool(lead.get("has_future_opportunity") and lead.get("next_project_date"))

    lines = [_esc(_text(reason, "No opportunity narrative on record."))]
    lines.append(
        f"Likely correct property-side contact: <b>{_esc(_text(contact_target))}</b>."
        if contact_target else f"Likely correct property-side contact: {NOT_FOUND}."
    )
    lines.append(
        f"Historical hindrance on record: friction score {friction_score} ({_esc(_text(', '.join(signals) if signals else None))})."
        if friction_score else "No historical hindrance on record."
    )
    lines.append(
        f"Urgency driver: {_esc(_text(lead.get('next_project_event')))} on {_esc(_text(lead.get('next_project_date')))} "
        f"({_esc(_text(lead.get('urgency')))})."
        if upcoming else "No scheduled event currently creates urgency."
    )

    body = [Paragraph(
        "PERMITSIGNAL ANALYSIS — the recommendations below are derived only from already-computed "
        "opportunity/friction fields; they are not a source-document statement.",
        STYLE_TAG,
    )]
    body.extend(Paragraph(line, STYLE_BODY) for line in lines)

    return [
        *_section_heading("6. FOLLOW-UP INTELLIGENCE"),
        KeepTogether(body),
        Spacer(1, 6),
    ]


def _build_evidence_register(lead: dict) -> list:
    entries: list[list[str]] = []
    idx = 1
    source = _text(lead.get("source"))
    source_url = _text(lead.get("source_url"))

    for event in _friction_events(lead):
        entries.append([
            f"E-{idx:02d}", source, source_url, "Government Record",
            _text(event.get("event_date")), _text(event.get("evidence"))[:220],
            "Historical friction score/signal", _text(event.get("confidence"), UNVERIFIED),
        ])
        idx += 1

    for date_entry in (lead.get("future_project_dates") or []):
        entries.append([
            f"E-{idx:02d}", source, source_url, "Government Record",
            _text(date_entry.get("value")), _text(date_entry.get("context"))[:220],
            "Next project event / date", _text(date_entry.get("confidence"), UNVERIFIED),
        ])
        idx += 1

    contact_source = lead.get("contact_source") or lead.get("email_source") or lead.get("company_source")
    if contact_source:
        entries.append([
            f"E-{idx:02d}", _text(contact_source), _text(lead.get("company_website") or lead.get("owner_website")),
            "Public Contact Source", "—", "Contact record supplied by enrichment source above.",
            "Contact Intelligence (Section 5)", _text(lead.get("contact_confidence"), UNVERIFIED),
        ])
        idx += 1
    else:
        queries = lead.get("search_queries") or []
        if queries:
            entries.append([
                f"E-{idx:02d}", "PermitSignal Contact Discovery", "—", "Search Attempt", "—",
                f"Queries attempted, no verified public contact found: {', '.join(queries[:3])}",
                "Contact Intelligence (Section 5) -- absence", "N/A",
            ])
            idx += 1

    flow = _section_heading("7. EVIDENCE REGISTER")

    if not entries:
        flow.append(Paragraph(
            "No additional evidence on record beyond the source packet cited in the title block.", STYLE_SMALL,
        ))
        flow.append(Spacer(1, 6))
        return flow

    header = ["ID", "Source", "URL / Document", "Type", "Date", "Excerpt", "Supports", "Confidence"]
    rows = [[_p(h, style=STYLE_LABEL) for h in header]]
    for entry in entries:
        rows.append([_p(cell, style=STYLE_SMALL) for cell in entry])

    table = Table(
        rows,
        colWidths=[0.35 * inch, 0.75 * inch, 1.0 * inch, 0.75 * inch, 0.55 * inch, 1.7 * inch, 1.0 * inch, 0.55 * inch],
        repeatRows=1,
    )
    table.setStyle(_evidence_table_style())
    flow.append(table)
    flow.append(Spacer(1, 6))
    return flow


def _build_verification_checklist(lead: dict) -> list:
    owner_known = _is_owner_known(lead)
    applicant_present = bool(lead.get("applicant_name"))
    staff_present = bool(lead.get("staff_contact_name") or lead.get("staff_contact_email"))
    contact_verified = bool(lead.get("contact_is_verified"))
    contact_source_present = bool(lead.get("contact_source") or lead.get("email_source") or lead.get("phone_source"))
    project_date_present = bool(lead.get("next_project_date"))
    friction_evidence_present = bool(_friction_events(lead))
    same_party = owner_known and applicant_present and _primary_owner(lead) == lead.get("applicant_name")

    checklist = [
        ("Owner verified", "YES" if owner_known else "NOT ESTABLISHED"),
        ("Owner contact verified", "YES" if _owner_contact_name(lead) else "NOT ESTABLISHED"),
        ("Applicant verified", "YES" if applicant_present else "NOT ON RECORD"),
        ("Applicant/owner relationship checked",
         "SAME PARTY" if same_party else ("DISTINCT" if owner_known else "OWNER NOT ESTABLISHED")),
        ("Government staff separated", "YES" if staff_present else "NO STAFF ON RECORD"),
        ("Contact source verified",
         "VERIFIED" if contact_verified else ("SOURCED — UNVERIFIED" if contact_source_present else "NO CONTACT SOURCE")),
        ("Project date verified", "YES" if project_date_present else "NO UPCOMING EVENT"),
        ("Friction evidence verified", "YES" if friction_evidence_present else "NO FRICTION EVIDENCE"),
        ("Case source retained", "YES" if lead.get("source_url") else "NO SOURCE URL"),
        ("Follow-up recommendation reviewed", "PENDING MANUAL REVIEW"),
    ]

    rows = [[_p(label, style=STYLE_BODY), Paragraph(status, STYLE_BODY)] for label, status in checklist]
    table = Table(rows, colWidths=[3.7 * inch, 2.85 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
    ]))

    signoff = Table(
        [
            [_p("Prepared By", style=STYLE_LABEL), _p("Reviewed By", style=STYLE_LABEL),
             _p("Date", style=STYLE_LABEL), _p("Status", style=STYLE_LABEL)],
            [Paragraph("", STYLE_BODY)] * 4,
        ],
        colWidths=[1.65 * inch] * 4,
        rowHeights=[16, 28],
    )
    signoff.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))

    return [
        *_section_heading("8. INTERNAL VERIFICATION CHECKLIST"),
        table,
        Spacer(1, 10),
        signoff,
    ]


# ============================================================================
# PAGE FURNITURE -- consistent header/footer + "Page X of Y" on every page.
# ============================================================================

class _CaseReportCanvas(Canvas):
    """Standard ReportLab two-pass recipe for accurate 'Page X of Y' numbering."""

    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_furniture(total_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_page_furniture(self, total_pages: int) -> None:
        # Deliberately no full-page background fill here: this canvas
        # subclass replays header/footer drawing AFTER each page's body
        # content is already in the PDF content stream (see save()), so a
        # full-page rect at this point would paint over the body -- it
        # must stay confined to the header/footer strips outside the
        # content frame's margins.
        width, height = PAGE_SIZE

        self.setFillColor(INK)
        self.setFont("Helvetica-Bold", 9)
        self.drawString(MARGIN, height - 0.45 * inch, "PERMITSIGNAL")
        self.setFillColor(BRASS)
        self.setFont("Helvetica", 8)
        self.drawRightString(width - MARGIN, height - 0.45 * inch, "PROPERTY INTELLIGENCE CASE REPORT")
        self.setStrokeColor(BRASS)
        self.setLineWidth(1)
        self.line(MARGIN, height - 0.55 * inch, width - MARGIN, height - 0.55 * inch)

        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, 0.55 * inch, width - MARGIN, 0.55 * inch)
        self.setFillColor(MUTED)
        self.setFont("Helvetica", 7.5)
        self.drawString(MARGIN, 0.4 * inch, "PermitSignal — Internal Case Intelligence — Not a government record")
        self.drawRightString(width - MARGIN, 0.4 * inch, f"Page {self._pageNumber} of {total_pages}")


# ============================================================================
# PUBLIC API
# ============================================================================

def _load_output(output_path: "Path | str" = DEFAULT_OUTPUT) -> Optional[dict]:
    path = Path(output_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_lead_by_application_number(
    application_number: str,
    output_path: "Path | str" = DEFAULT_OUTPUT,
) -> Optional[dict]:
    """Reads the pipeline's always-produced JSON artifact and returns the matching lead_queue entry, or None."""
    data = _load_output(output_path)
    if data is None:
        return None
    for lead in data.get("lead_queue", []):
        if lead.get("application_number") == application_number:
            return lead
    return None


def load_lead_queue(output_path: "Path | str" = DEFAULT_OUTPUT) -> list[dict]:
    """
    Phase 4 API retrieval fallback: reads the pipeline's always-produced
    JSON artifact and returns the full lead_queue list, or [] when the
    artifact does not exist yet. Used by GET /leads when Supabase is not
    configured or has no rows.
    """
    data = _load_output(output_path)
    if data is None:
        return []
    return data.get("lead_queue", [])


# ============================================================================
# DEEP INTELLIGENCE SECTIONS (from approval_intelligence_engine)
# ============================================================================


def _build_executive_diagnosis(lead: dict) -> list:
    """Section: Executive Diagnosis from deep intelligence."""
    intel = lead.get("approval_intelligence") or {}
    diagnosis = intel.get("executive_diagnosis")
    if not diagnosis:
        return []
    return [
        Paragraph("EXECUTIVE DIAGNOSIS", STYLE_SECTION),
        Paragraph(_xml_escape(diagnosis), STYLE_BODY),
        Spacer(1, 6),
    ]


def _build_denial_history(lead: dict) -> list:
    """Section: Denial History."""
    intel = lead.get("approval_intelligence") or {}
    history = intel.get("denial_history") or []
    if not history:
        return []
    story: list = [Paragraph("DENIAL HISTORY", STYLE_SECTION)]
    for h in history:
        event_type = (h.get("event_type") or "unknown").replace("_", " ").title()
        event_date = h.get("event_date") or "N/A"
        objection = h.get("objection_type") or "unknown"
        recurrence = " [RECURRENCE]" if h.get("is_recurrence") else ""
        story.append(
            Paragraph(
                f"<b>{event_type}</b> ({event_date}) -- Objection: {objection}{recurrence}",
                STYLE_SMALL,
            )
        )
    story.append(Spacer(1, 6))
    return story


def _build_approval_blockers(lead: dict) -> list:
    """Section: Approval Blockers."""
    intel = lead.get("approval_intelligence") or {}
    blockers = intel.get("approval_blockers") or []
    if not blockers:
        return []
    story: list = [Paragraph("APPROVAL BLOCKERS", STYLE_SECTION)]
    for b in blockers:
        severity = (b.get("severity") or "UNKNOWN").upper()
        btype = (b.get("blocker_type") or "unknown").replace("_", " ").title()
        statement = b.get("statement") or ""
        classification = b.get("classification") or ""
        tag = f"[{severity}] {btype}"
        if classification:
            tag += f" -- {classification}"
        story.append(Paragraph(f"<b>{_xml_escape(tag)}</b>", STYLE_TAG))
        if statement:
            story.append(Paragraph(_xml_escape(statement), STYLE_SMALL))
    story.append(Spacer(1, 6))
    return story


def _build_requirements_intelligence(lead: dict) -> list:
    """Section: Requirements (Groups A / B / C)."""
    intel = lead.get("approval_intelligence") or {}
    requirements = intel.get("requirements") or []
    if not requirements:
        return []
    story: list = [Paragraph("REQUIREMENTS", STYLE_SECTION)]
    group_labels = {
        "A": "EXPLICIT GOVERNMENT REQUIREMENTS",
        "B": "DERIVED / INFERRED",
        "C": "PERMITSIGNAL RECOMMENDATIONS",
    }
    for group_key in ("A", "B", "C"):
        items = [r for r in requirements if r.get("group") == group_key]
        if not items:
            continue
        story.append(Paragraph(f"<b>{group_labels.get(group_key, group_key)}</b>", STYLE_SUBSECTION))
        for r in items:
            statement = r.get("statement") or ""
            classification = r.get("classification") or ""
            story.append(Paragraph(
                f"<b>[{classification}]</b> {_xml_escape(statement)}",
                STYLE_SMALL,
            ))
    story.append(Spacer(1, 6))
    return story


def _build_actions_intelligence(lead: dict) -> list:
    """Section: Recommended Actions."""
    intel = lead.get("approval_intelligence") or {}
    actions = intel.get("recommended_actions") or []
    if not actions:
        return []
    sorted_actions = sorted(actions, key=lambda a: a.get("priority_rank", 99))
    story: list = [Paragraph("RECOMMENDED ACTIONS", STYLE_SECTION)]
    for a in sorted_actions:
        rank = a.get("priority_rank", "?")
        action_text = a.get("action") or ""
        deadline = a.get("deadline") or ""
        line = f"<b>#{rank}</b> {_xml_escape(action_text)}"
        if deadline:
            line += f" (Deadline: {deadline})"
        story.append(Paragraph(line, STYLE_SMALL))
    story.append(Spacer(1, 6))
    return story


def _build_decision_path_intelligence(lead: dict) -> list:
    """Section: Decision Path."""
    intel = lead.get("approval_intelligence") or {}
    path = intel.get("decision_path") or []
    if not path:
        return []
    story: list = [Paragraph("DECISION PATH", STYLE_SECTION)]
    for stage in path:
        label = stage.get("stage_label") or stage.get("stage") or "Unknown"
        status = (stage.get("status") or "unknown").replace("_", " ").title()
        classification = stage.get("classification") or ""
        line = f"<b>{_xml_escape(label)}</b>: {status}"
        if classification:
            line += f" [{classification}]"
        story.append(Paragraph(line, STYLE_SMALL))
    story.append(Spacer(1, 6))
    return story


def _build_client_message_intelligence(lead: dict) -> list:
    """Section: Client Message (from intelligence engine)."""
    intel = lead.get("approval_intelligence") or {}
    message = intel.get("client_message")
    if not message:
        return []
    return [
        Paragraph("CLIENT MESSAGE", STYLE_SECTION),
        Paragraph(_xml_escape(message), STYLE_SMALL),
        Spacer(1, 6),
    ]


def _build_pricing_intelligence(lead: dict) -> list:
    """Section: Pricing (from pricing engine)."""
    pricing = lead.get("pricing") or {}
    if not pricing or pricing.get("status") == "error":
        return []
    story: list = [Paragraph("PRICING", STYLE_SECTION)]
    fee_low = pricing.get("fee_low")
    fee_high = pricing.get("fee_high")
    recommended = pricing.get("recommended_fee")
    deposit_pct = pricing.get("deposit_percent")
    deposit_amt = pricing.get("deposit_amount")
    if fee_low is not None and fee_high is not None:
        story.append(Paragraph(
            f"<b>Fee range:</b> ${fee_low:,.0f} -- ${fee_high:,.0f}",
            STYLE_SMALL,
        ))
    if recommended is not None:
        story.append(Paragraph(
            f"<b>Recommended fee:</b> ${recommended:,.0f}",
            STYLE_SMALL,
        ))
    if deposit_pct is not None and deposit_amt is not None:
        story.append(Paragraph(
            f"<b>Deposit:</b> {deposit_pct}% (${deposit_amt:,.0f})",
            STYLE_SMALL,
        ))
    rationale = pricing.get("pricing_rationale") or []
    if rationale:
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Pricing Rationale:</b>", STYLE_LABEL))
        for line in rationale:
            story.append(Paragraph(f"  {_xml_escape(line)}", STYLE_SMALL))
    story.append(Spacer(1, 6))
    return story


# ============================================================================
# MAIN PDF GENERATION
# ============================================================================


def generate_case_report_pdf(lead: dict) -> bytes:
    """Renders a canonical lead dict into a formal PermitSignal case-report PDF, returned as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title=f"PermitSignal Case Report - {_text(lead.get('application_number'), '')}",
        author="PermitSignal",
    )

    story: list = []
    story.extend(_build_title_block(lead))
    story.extend(_build_case_identification(lead))
    story.extend(_build_parties(lead))
    story.extend(_build_project_intelligence(lead))
    story.extend(_build_friction(lead))
    story.extend(_build_contact_intelligence(lead))
    story.extend(_build_follow_up(lead))
    # Deep intelligence sections (from approval_intelligence_engine)
    story.extend(_build_executive_diagnosis(lead))
    story.extend(_build_denial_history(lead))
    story.extend(_build_approval_blockers(lead))
    story.extend(_build_requirements_intelligence(lead))
    story.extend(_build_actions_intelligence(lead))
    story.extend(_build_decision_path_intelligence(lead))
    story.extend(_build_pricing_intelligence(lead))
    story.extend(_build_client_message_intelligence(lead))
    # Existing evidence and verification
    story.extend(_build_evidence_register(lead))
    story.extend(_build_verification_checklist(lead))

    doc.build(story, canvasmaker=_CaseReportCanvas)
    return buffer.getvalue()


__all__ = ["load_lead_by_application_number", "load_lead_queue", "generate_case_report_pdf"]
