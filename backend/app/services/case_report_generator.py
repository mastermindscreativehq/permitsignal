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
load_lead_queue(output_path=DEFAULT_OUTPUT)
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
CONTENT_WIDTH = PAGE_SIZE[0] - 2 * MARGIN

INK = colors.HexColor("#20232a")
MUTED = colors.HexColor("#63666b")
FAINT = colors.HexColor("#8a8d92")
BRASS = colors.HexColor("#a97a2f")
HAIRLINE = colors.HexColor("#d8d3c8")

HEADER_BG = colors.HexColor("#2f3a42")
LABEL_BG = colors.HexColor("#edf0f2")
ROW_ALT_BG = colors.HexColor("#f7f8f9")
WHITE = colors.white

NOT_FOUND = "NOT FOUND"
OWNERSHIP_NOT_ESTABLISHED = "OWNERSHIP NOT ESTABLISHED"
UNVERIFIED = "UNVERIFIED"

_STYLES = getSampleStyleSheet()

# -- Typography --

STYLE_TITLE = ParagraphStyle(
    "CaseTitle", parent=_STYLES["Title"], fontName="Helvetica-Bold",
    fontSize=18, leading=20, textColor=INK, spaceAfter=1, alignment=0,
)
STYLE_TITLE2 = ParagraphStyle(
    "CaseTitle2", parent=STYLE_TITLE, fontSize=11, leading=13,
    textColor=BRASS, fontName="Helvetica",
)
STYLE_SUBTITLE = ParagraphStyle(
    "CaseSubtitle", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=7.5, textColor=MUTED, spaceAfter=6, alignment=0,
)
STYLE_SECTION = ParagraphStyle(
    "SectionHeading", parent=_STYLES["Heading2"], fontName="Helvetica-Bold",
    fontSize=11, textColor=INK, spaceBefore=14, spaceAfter=3,
)
STYLE_SUBSECTION = ParagraphStyle(
    "SubsectionHeading", parent=_STYLES["Heading3"], fontName="Helvetica-Bold",
    fontSize=9, textColor=INK, spaceBefore=8, spaceAfter=3,
)
STYLE_BODY = ParagraphStyle(
    "Body", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=8.5, textColor=INK, leading=12,
)
STYLE_LABEL = ParagraphStyle(
    "Label", parent=_STYLES["Normal"], fontName="Helvetica-Bold",
    fontSize=7.6, textColor=INK, leading=10,
)
STYLE_SMALL = ParagraphStyle(
    "Small", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=7.6, textColor=MUTED, leading=10,
)
STYLE_TAG = ParagraphStyle(
    "Tag", parent=_STYLES["Normal"], fontName="Helvetica-Bold",
    fontSize=7.5, textColor=BRASS, leading=10, spaceAfter=2,
)
STYLE_FINE = ParagraphStyle(
    "Fine", parent=_STYLES["Normal"], fontName="Helvetica",
    fontSize=6.5, textColor=FAINT, leading=9,
)
STYLE_FINE_BOLD = ParagraphStyle(
    "FineBold", parent=STYLE_FINE, fontName="Helvetica-Bold",
)
STYLE_TH_BODY = ParagraphStyle(
    "TableHeaderBody", parent=STYLE_BODY, fontSize=8, leading=11,
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


def _pb(value: Any, fallback: str = NOT_FOUND) -> Paragraph:
    """Bold paragraph."""
    return Paragraph(f"<b>{_esc(_text(value, fallback))}</b>", STYLE_BODY)


# ============================================================================
# PARTY / OWNERSHIP HELPERS -- mirror dashboard/src/lib/lead-helpers.ts
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
    return lead.get("friction_events") or lead.get("events") or []


# ============================================================================
# SHARED FLOWABLE BUILDERS
# ============================================================================

def _section_heading(number_and_title: str) -> list:
    return [
        Spacer(1, 4),
        Paragraph(number_and_title, STYLE_SECTION),
        HRFlowable(width="100%", thickness=0.5, color=HAIRLINE, spaceAfter=4),
    ]


def _kv_table(rows: list[tuple[str, Any]], fallback: str = NOT_FOUND) -> Table:
    """Key-value table with grey-filled label cells, matching reference PDF style."""
    data = [[_p(label, style=STYLE_LABEL), _p(value, fallback)] for label, value in rows]
    table = Table(data, colWidths=[1.6 * inch, CONTENT_WIDTH - 1.6 * inch])
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (0, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ]
    # Grey background on label cells
    for i in range(len(data)):
        style_cmds.append(("BACKGROUND", (0, i), (0, i), LABEL_BG))
    table.setStyle(TableStyle(style_cmds))
    return table


def _header_row_style(num_cols: int) -> TableStyle:
    """Dark header row style for data tables."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, HAIRLINE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ])


def _data_table_style() -> TableStyle:
    """Standard data table style with alternating rows."""
    return TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ])


# ============================================================================
# REPORT HEADER BLOCK
# ============================================================================

def _build_report_header(lead: dict) -> list:
    """PermitSignal wordmark + title + case metadata grid."""
    review_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    app_number = _text(lead.get("application_number"), "")

    meta_table = Table(
        [
            [_p("Case Number", style=STYLE_LABEL), _p(lead.get("application_number")),
             _p("Review Date", style=STYLE_LABEL), _p(review_date)],
            [_p("Application Type", style=STYLE_LABEL), _p(lead.get("application_type")),
             _p("Priority", style=STYLE_LABEL), _p(lead.get("priority"))],
            [_p("Property Address", style=STYLE_LABEL), _p(lead.get("project_address")),
             _p("Jurisdiction", style=STYLE_LABEL), _p(lead.get("municipality"))],
            [_p("Source Packet", style=STYLE_LABEL), _p(lead.get("source")),
             _p("Applicant", style=STYLE_LABEL), _p(lead.get("applicant_name"))],
        ],
        colWidths=[1.1 * inch, 2.15 * inch, 1.1 * inch, 2.15 * inch],
    )
    meta_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ]
    for i in range(4):
        meta_style.append(("BACKGROUND", (0, i), (0, i), LABEL_BG))
        meta_style.append(("BACKGROUND", (2, i), (2, i), LABEL_BG))
    meta_table.setStyle(TableStyle(meta_style))

    return [
        Spacer(1, 2),
        Paragraph("PERMITSIGNAL", STYLE_TITLE),
        Paragraph("PROPERTY INTELLIGENCE CASE REPORT", STYLE_TITLE2),
        Paragraph(
            "DRAFT \u2014 INTERNAL PROPERTY INTELLIGENCE REVIEW \u00b7 NOT A GOVERNMENT RECORD",
            STYLE_SUBTITLE,
        ),
        HRFlowable(width="100%", thickness=1.0, color=BRASS, spaceAfter=8),
        meta_table,
        Spacer(1, 6),
    ]


# ============================================================================
# CASE SUMMARY (page 1 high-level)
# ============================================================================

def _build_case_summary(lead: dict) -> list:
    """Approval status, risk, readiness, owner, applicant in a compact summary."""
    intel = lead.get("approval_intelligence") or {}
    status = lead.get("approval_status") or intel.get("approval_status") or NOT_FOUND
    risk = lead.get("deep_approval_risk") or intel.get("approval_risk") or NOT_FOUND
    readiness = lead.get("deep_approval_readiness") or intel.get("approval_readiness") or NOT_FOUND
    owner_known = _is_owner_known(lead)

    rows = [
        ("Approval Status", status),
        ("Approval Risk", risk),
        ("Approval Readiness", readiness),
        ("Property Owner", _primary_owner(lead) if owner_known else None),
        ("Applicant / Agent", lead.get("applicant_name")),
        ("Organization", lead.get("company_name")),
        ("Neighborhood", lead.get("neighborhood")),
        ("Application Type", lead.get("application_type")),
    ]
    return [
        *_section_heading("CASE SUMMARY"),
        KeepTogether([_kv_table(rows)]),
        Spacer(1, 4),
    ]


# ============================================================================
# EXECUTIVE DIAGNOSIS
# ============================================================================

def _build_executive_diagnosis(lead: dict) -> list:
    intel = lead.get("approval_intelligence") or {}
    diagnosis = intel.get("executive_diagnosis")
    if not diagnosis:
        return []
    return [
        *_section_heading("EXECUTIVE DIAGNOSIS"),
        Paragraph(_xml_escape(diagnosis), STYLE_BODY),
        Spacer(1, 4),
    ]


# ============================================================================
# HEARING / EVENT INFORMATION
# ============================================================================

def _build_hearing_information(lead: dict) -> list:
    upcoming = bool(lead.get("has_future_opportunity") and lead.get("next_project_date"))
    if not upcoming:
        return []

    rows = [
        ("Next Event", lead.get("next_project_event")),
        ("Event Date", lead.get("next_project_date")),
        ("Event Time", lead.get("next_project_time")),
        ("Days Until Event", lead.get("days_until_event")),
        ("Urgency", lead.get("urgency")),
    ]
    future_dates = lead.get("future_project_dates") or []
    if future_dates:
        dates_text = "; ".join(
            f"{d.get('label', '?')} on {d.get('value', '?')}"
            for d in future_dates[:4]
        )
        rows.append(("Additional Dates", dates_text))

    return [
        *_section_heading("HEARING / EVENT INFORMATION"),
        KeepTogether([_kv_table(rows)]),
        Spacer(1, 4),
    ]


# ============================================================================
# APPROVAL INTELLIGENCE (blockers + denial history)
# ============================================================================

def _build_approval_intelligence(lead: dict) -> list:
    intel = lead.get("approval_intelligence") or {}
    blockers = intel.get("approval_blockers") or []
    denial_history = intel.get("denial_history") or []

    if not blockers and not denial_history:
        return []

    flow = _section_heading("APPROVAL INTELLIGENCE")

    if denial_history:
        flow.append(Paragraph("DENIAL HISTORY", STYLE_SUBSECTION))
        for h in denial_history:
            event_type = (h.get("event_type") or "unknown").replace("_", " ").title()
            event_date = h.get("event_date") or "N/A"
            objection = h.get("objection_type") or "unknown"
            recurrence = " [RECURRENCE]" if h.get("is_recurrence") else ""
            flow.append(Paragraph(
                f"<b>{_esc(event_type)}</b> ({_esc(event_date)}) \u2014 Objection: {_esc(objection)}{_esc(recurrence)}",
                STYLE_SMALL,
            ))
        flow.append(Spacer(1, 4))

    if blockers:
        flow.append(Paragraph("APPROVAL BLOCKERS", STYLE_SUBSECTION))
        for b in blockers:
            severity = (b.get("severity") or "UNKNOWN").upper()
            btype = (b.get("blocker_type") or "unknown").replace("_", " ").title()
            statement = b.get("statement") or ""
            classification = b.get("classification") or ""
            tag = f"[{_esc(severity)}] {_esc(btype)}"
            if classification:
                tag += f" \u2014 {_esc(classification)}"
            flow.append(Paragraph(f"<b>{tag}</b>", STYLE_TAG))
            if statement:
                flow.append(Paragraph(_xml_escape(statement), STYLE_SMALL))
        flow.append(Spacer(1, 4))

    return flow


# ============================================================================
# WHAT MUST CHANGE (requirements A/B/C)
# ============================================================================

def _build_requirements(lead: dict) -> list:
    intel = lead.get("approval_intelligence") or {}
    requirements = intel.get("requirements") or []
    if not requirements:
        return []

    flow = _section_heading("WHAT MUST CHANGE")

    group_labels = {
        "A": "EXPLICIT GOVERNMENT REQUIREMENTS",
        "B": "DERIVED / INFERRED",
        "C": "PERMITSIGNAL RECOMMENDATIONS",
    }
    for group_key in ("A", "B", "C"):
        items = [r for r in requirements if r.get("group") == group_key]
        if not items:
            continue
        flow.append(Paragraph(f"<b>{group_labels.get(group_key, group_key)}</b>", STYLE_SUBSECTION))
        for r in items:
            statement = r.get("statement") or ""
            classification = r.get("classification") or ""
            flow.append(Paragraph(
                f"<b>[{_esc(classification)}]</b> {_xml_escape(statement)}",
                STYLE_SMALL,
            ))
    flow.append(Spacer(1, 4))
    return flow


# ============================================================================
# ACTION PLAN (recommended actions + decision path)
# ============================================================================

def _build_action_plan(lead: dict) -> list:
    intel = lead.get("approval_intelligence") or {}
    actions = intel.get("recommended_actions") or []
    path = intel.get("decision_path") or []

    if not actions and not path:
        return []

    flow = _section_heading("ACTION PLAN")

    if actions:
        flow.append(Paragraph("RECOMMENDED ACTIONS", STYLE_SUBSECTION))
        sorted_actions = sorted(actions, key=lambda a: a.get("priority_rank", 99))
        for a in sorted_actions:
            rank = a.get("priority_rank", "?")
            action_text = a.get("action") or ""
            deadline = a.get("deadline") or ""
            line = f"<b>#{_esc(str(rank))}</b> {_xml_escape(action_text)}"
            if deadline:
                line += f" (Deadline: {_esc(deadline)})"
            flow.append(Paragraph(line, STYLE_SMALL))
        flow.append(Spacer(1, 4))

    if path:
        flow.append(Paragraph("DECISION PATH", STYLE_SUBSECTION))
        for stage in path:
            label = stage.get("stage_label") or stage.get("stage") or "Unknown"
            status = (stage.get("status") or "unknown").replace("_", " ").title()
            classification = stage.get("classification") or ""
            line = f"<b>{_esc(label)}</b>: {_esc(status)}"
            if classification:
                line += f" [{_esc(classification)}]"
            flow.append(Paragraph(line, STYLE_SMALL))
        flow.append(Spacer(1, 4))

    return flow


# ============================================================================
# STAKEHOLDERS
# ============================================================================

def _build_stakeholders(lead: dict) -> list:
    engineer, architect, others = _parties_by_role(lead)
    owner_known = _is_owner_known(lead)
    owner_primary = _primary_owner(lead)
    owner_contact = _owner_contact_name(lead)
    intel = lead.get("approval_intelligence") or {}
    stakeholder_actions = intel.get("stakeholder_actions") or []

    has_parties = owner_known or engineer or architect or others or stakeholder_actions
    if not has_parties:
        return []

    flow = _section_heading("STAKEHOLDERS")

    rows = []
    if owner_known:
        contact_clause = f" ({_esc(_text(owner_contact))})" if owner_contact else ""
        rows.append(("Property Owner", f"{_esc(_text(owner_primary))}{contact_clause}"))
    if lead.get("applicant_name"):
        rows.append(("Applicant / Agent", _esc(_text(lead.get("applicant_name")))))
    if engineer:
        rows.append(("Engineer", f"{_esc(_text(engineer.get('party_name')))} ({_esc(_text(engineer.get('party_company'), 'company not on record'))})"))
    if architect:
        rows.append(("Architect", f"{_esc(_text(architect.get('party_name')))} ({_esc(_text(architect.get('party_company'), 'company not on record'))})"))
    for party in others:
        rows.append((_esc(_text(party.get('party_role'), 'Other Party')), _esc(_text(party.get('party_name')))))
    if lead.get("staff_contact_name"):
        rows.append(("Government Staff", f"{_esc(_text(lead.get('staff_contact_name')))} \u2014 {_esc(_text(lead.get('staff_contact_email')))} / {_esc(_text(lead.get('staff_contact_phone')))}"))

    if rows:
        flow.append(_kv_table(rows))
        flow.append(Spacer(1, 4))

    if stakeholder_actions:
        flow.append(Paragraph("STAKEHOLDER ACTIONS", STYLE_SUBSECTION))
        for sa in stakeholder_actions:
            stype = sa.get("stakeholder_type") or "Unknown"
            name = sa.get("name") or "Unknown"
            action = sa.get("suggested_action") or ""
            flow.append(Paragraph(
                f"<b>{_esc(stype)}: {_esc(name)}</b> \u2014 {_xml_escape(action)}",
                STYLE_SMALL,
            ))
        flow.append(Spacer(1, 4))

    return flow


# ============================================================================
# CONTACT INTELLIGENCE
# ============================================================================

def _build_contact_intelligence(lead: dict) -> list:
    owner_contact = _owner_contact_name(lead)
    verified = bool(lead.get("contact_is_verified"))
    public = bool(lead.get("contact_is_public"))
    verification = "VERIFIED" if verified else ("PUBLIC \u2014 UNVERIFIED" if public else UNVERIFIED)

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
    table = Table(data, colWidths=[1.6 * inch, CONTENT_WIDTH - 1.6 * inch])
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (0, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ]
    for i in range(len(data)):
        style_cmds.append(("BACKGROUND", (0, i), (0, i), LABEL_BG))
    table.setStyle(TableStyle(style_cmds))

    return [
        *_section_heading("CONTACT INTELLIGENCE"),
        KeepTogether([table]),
        Spacer(1, 4),
    ]


# ============================================================================
# PRICING / FEE ASSESSMENT (itemized table)
# ============================================================================

def _build_pricing_assessment(lead: dict) -> list:
    pricing = lead.get("pricing") or {}
    if not pricing or pricing.get("status") == "error":
        return [
            *_section_heading("PRICING / FEE ASSESSMENT"),
            Paragraph("Pricing data not available for this case.", STYLE_BODY),
            Spacer(1, 4),
        ]

    flow = _section_heading("PRICING / FEE ASSESSMENT")

    fee_low = pricing.get("fee_low")
    fee_high = pricing.get("fee_high")
    recommended = pricing.get("recommended_fee")
    deposit_pct = pricing.get("deposit_percent")
    deposit_amt = pricing.get("deposit_amount")
    rationale = pricing.get("pricing_rationale") or []

    # Parse rationale into structured rows
    rows = [
        [_p("DESCRIPTION", style=STYLE_LABEL), _p("AMOUNT", style=STYLE_LABEL), _p("BASIS / PURPOSE", style=STYLE_LABEL)],
    ]

    if rationale:
        for line in rationale:
            # Parse known patterns from pricing_engine rationale
            if line.startswith("Service tier:"):
                rows.append([
                    _p("Service tier"),
                    _p(""),
                    _p(line),
                ])
            elif line.startswith("Base fee range:"):
                rows.append([
                    _p("Base fee range"),
                    _p(line.split(": ", 1)[-1] if ": " in line else ""),
                    _p("Before complexity adjustments"),
                ])
            elif line.startswith("Complexity multipliers applied:"):
                rows.append([
                    _p("Complexity adjustments"),
                    _p(""),
                    _p(line),
                ])
            elif line.startswith("Project value range:"):
                rows.append([
                    _p("Estimated project value"),
                    _p(line.split(": ", 1)[-1] if ": " in line else ""),
                    _p("For reference \u2014 not included in fee calculation"),
                ])
            elif line.startswith("Final fee range:"):
                rows.append([
                    _p("Final fee range"),
                    _p(line.split(": ", 1)[-1] if ": " in line else ""),
                    _p("After all adjustments"),
                ])
            elif line.startswith("Recommended fee:"):
                rows.append([
                    _p("Recommended engagement fee"),
                    _p(line.split(": ", 1)[-1] if ": " in line else ""),
                    _p("Midpoint of adjusted range"),
                ])
            elif line.startswith("Deposit:"):
                rows.append([
                    _p("Deposit"),
                    _p(line.split(": ", 1)[-1] if ": " in line else ""),
                    _p("Due at engagement"),
                ])
            else:
                rows.append([_p(line), _p(""), _p("")])
    else:
        if fee_low is not None and fee_high is not None:
            rows.append([_p("Fee range"), _p(f"${fee_low:,.0f} \u2013 ${fee_high:,.0f}"), _p("Adjusted range")])
        if recommended is not None:
            rows.append([_p("Recommended fee"), _p(f"${recommended:,.0f}"), _p("Midpoint")])
        if deposit_pct is not None and deposit_amt is not None:
            rows.append([_p("Deposit"), _p(f"{deposit_pct}% (${deposit_amt:,.0f})"), _p("Due at engagement")])

    # TOTAL ASSESSMENT row
    if recommended is not None:
        rows.append([
            Paragraph("<b>TOTAL ASSESSMENT</b>", STYLE_BODY),
            Paragraph(f"<b>${recommended:,.0f}</b>", STYLE_BODY),
            Paragraph("<b>Recommended engagement fee</b>", STYLE_BODY),
        ])

    table = Table(rows, colWidths=[2.0 * inch, 1.8 * inch, CONTENT_WIDTH - 3.8 * inch])

    # Style: dark header, subtle rows, bold total
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HAIRLINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HAIRLINE),
    ]
    # Total row background
    if len(rows) > 1:
        total_row = len(rows) - 1
        style_cmds.append(("BACKGROUND", (0, total_row), (-1, total_row), LABEL_BG))
        style_cmds.append(("LINEABOVE", (0, total_row), (-1, total_row), 0.75, INK))

    table.setStyle(TableStyle(style_cmds))
    flow.append(table)
    flow.append(Spacer(1, 4))

    return flow


# ============================================================================
# EVIDENCE REGISTRY
# ============================================================================

def _build_evidence_registry(lead: dict) -> list:
    entries: list[list[str]] = []
    idx = 1
    source = _text(lead.get("source"))
    source_url = _text(lead.get("source_url"))

    for event in _friction_events(lead):
        entries.append([
            f"E-{idx:02d}", source, "Government Record",
            _text(event.get("event_date")), _text(event.get("evidence"))[:220],
            "Historical friction", _text(event.get("confidence"), UNVERIFIED),
        ])
        idx += 1

    for date_entry in (lead.get("future_project_dates") or []):
        entries.append([
            f"E-{idx:02d}", source, "Government Record",
            _text(date_entry.get("value")), _text(date_entry.get("context"))[:220],
            "Project event / date", _text(date_entry.get("confidence"), UNVERIFIED),
        ])
        idx += 1

    contact_source = lead.get("contact_source") or lead.get("email_source") or lead.get("company_source")
    if contact_source:
        entries.append([
            f"E-{idx:02d}", _text(contact_source), "Public Contact Source",
            "\u2014", "Contact record supplied by enrichment source.",
            "Contact Intelligence", _text(lead.get("contact_confidence"), UNVERIFIED),
        ])
        idx += 1
    else:
        queries = lead.get("search_queries") or []
        if queries:
            entries.append([
                f"E-{idx:02d}", "PermitSignal Contact Discovery", "Search Attempt",
                "\u2014", f"Queries attempted, no verified contact found: {', '.join(queries[:3])}",
                "Contact Intelligence (absence)", "N/A",
            ])
            idx += 1

    flow = _section_heading("EVIDENCE REGISTRY")

    if not entries:
        flow.append(Paragraph(
            "No additional evidence on record beyond the source packet cited in the title block.",
            STYLE_SMALL,
        ))
        flow.append(Spacer(1, 4))
        return flow

    header = ["ID", "Source", "Type", "Date", "Excerpt", "Supports", "Confidence"]
    rows = [[_p(h, style=STYLE_LABEL) for h in header]]
    for entry in entries:
        rows.append([_p(cell, style=STYLE_SMALL) for cell in entry])

    table = Table(
        rows,
        colWidths=[0.35 * inch, 0.85 * inch, 0.7 * inch, 0.55 * inch, 2.2 * inch, 1.0 * inch, 0.55 * inch],
        repeatRows=1,
    )
    table.setStyle(_data_table_style())
    flow.append(table)
    flow.append(Spacer(1, 4))
    return flow


# ============================================================================
# RELEVANT SOURCES
# ============================================================================

def _build_relevant_sources(lead: dict) -> list:
    source = lead.get("source")
    source_url = lead.get("source_url")
    if not source and not source_url:
        return []

    rows = [("Source Packet", source), ("Source URL", source_url)]
    approval_source = lead.get("approval_source")
    if approval_source and approval_source != source_url:
        rows.append(("Approval Source", approval_source))

    return [
        *_section_heading("RELEVANT SOURCES"),
        KeepTogether([_kv_table(rows)]),
        Spacer(1, 4),
    ]


# ============================================================================
# UNRESOLVED QUESTIONS + MODEL WARNINGS
# ============================================================================

def _build_model_output(lead: dict) -> list:
    intel = lead.get("approval_intelligence") or {}
    warnings = intel.get("model_warnings") or []
    questions = intel.get("unresolved_questions") or []

    if not warnings and not questions:
        return []

    flow = _section_heading("MODEL WARNINGS &amp; UNRESOLVED QUESTIONS")

    if warnings:
        flow.append(Paragraph("MODEL WARNINGS", STYLE_SUBSECTION))
        for w in warnings:
            flow.append(Paragraph(f"\u2022 {_xml_escape(str(w))}", STYLE_SMALL))
        flow.append(Spacer(1, 4))

    if questions:
        flow.append(Paragraph("UNRESOLVED QUESTIONS", STYLE_SUBSECTION))
        for q in questions:
            flow.append(Paragraph(f"\u2022 {_xml_escape(str(q))}", STYLE_SMALL))
        flow.append(Spacer(1, 4))

    return flow


# ============================================================================
# DISCLAIMER
# ============================================================================

def _build_disclaimer(lead: dict) -> list:
    return [
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=0.5, color=HAIRLINE, spaceAfter=4),
        Paragraph(
            "<b>Applicant notice:</b> This case report is a PermitSignal-generated internal intelligence "
            "review. It does not independently create or determine planning, zoning, hearing, or "
            "development obligations. All pricing is PermitSignal's assessment, not a government-issued "
            "charge. Verify against the current official agenda and case record before issuance.",
            STYLE_FINE,
        ),
        Spacer(1, 4),
    ]


# ============================================================================
# PAGE FURNITURE -- consistent header/footer + "Page X of Y" on every page.
# ============================================================================

class _CaseReportCanvas(Canvas):
    """Two-pass recipe for accurate 'Page X of Y' and per-page header/footer."""

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
        width, height = PAGE_SIZE

        # -- Dark header band --
        self.setFillColor(HEADER_BG)
        self.rect(0, height - 0.65 * inch, width, 0.65 * inch, fill=1, stroke=0)

        # -- Wordmark in header --
        self.setFillColor(WHITE)
        self.setFont("Helvetica-Bold", 9)
        self.drawString(MARGIN, height - 0.42 * inch, "PERMITSIGNAL")

        # -- Report title in header --
        self.setFillColor(colors.HexColor("#c0c4c8"))
        self.setFont("Helvetica", 7.5)
        self.drawRightString(width - MARGIN, height - 0.42 * inch, "PROPERTY INTELLIGENCE CASE REPORT")

        # -- Brass accent line below header --
        self.setStrokeColor(BRASS)
        self.setLineWidth(1.5)
        self.line(0, height - 0.65 * inch, width, height - 0.65 * inch)

        # -- Footer separator --
        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, 0.55 * inch, width - MARGIN, 0.55 * inch)

        # -- Footer text --
        self.setFillColor(FAINT)
        self.setFont("Helvetica", 6)
        self.drawString(MARGIN, 0.4 * inch, "PermitSignal \u2014 Internal Case Intelligence \u2014 Not a government record")
        self.drawRightString(width - MARGIN, 0.4 * inch, f"Page {self._pageNumber} of {total_pages}")


# ============================================================================
# PUBLIC API -- data loading (unchanged from original)
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

    # -- Page 1: header + high-level summary --
    story.extend(_build_report_header(lead))
    story.extend(_build_case_summary(lead))
    story.extend(_build_executive_diagnosis(lead))
    story.extend(_build_hearing_information(lead))

    # -- Detailed intelligence sections --
    story.extend(_build_approval_intelligence(lead))
    story.extend(_build_requirements(lead))
    story.extend(_build_action_plan(lead))

    # -- Parties + contacts --
    story.extend(_build_stakeholders(lead))
    story.extend(_build_contact_intelligence(lead))

    # -- Pricing (itemized fee table) --
    story.extend(_build_pricing_assessment(lead))

    # -- Evidence + sources --
    story.extend(_build_evidence_registry(lead))
    story.extend(_build_relevant_sources(lead))

    # -- Model output --
    story.extend(_build_model_output(lead))

    # -- Disclaimer --
    story.extend(_build_disclaimer(lead))

    doc.build(story, canvasmaker=_CaseReportCanvas)
    return buffer.getvalue()


__all__ = ["load_lead_by_application_number", "load_lead_queue", "generate_case_report_pdf"]
