import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.collectors.provo import (
    collect_provo_records_dict,
)
from backend.app.services import applicant_enrichment, case_report_generator, case_report_store, discovery_orchestrator, document_downloader
from backend.app.services import lead_repository, matrix_engine, opportunity_builder, outreach_intelligence, pipeline_orchestrator
from backend.app.services import investigation_engine, source_registry


app = FastAPI(
    title="PROVO ADMINISTRATIVE SERVICES FINANCE API",
    description="Government approval intelligence platform",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the frontend origin(s) to call this API.
#
# PERMITSIGNAL_CORS_ORIGINS is a comma-separated list read from the
# environment.  For local development the Vercel dev server (localhost:3000)
# is included by default.  In production set the variable to the actual
# deployed frontend origin (e.g. https://permitsignal.vercel.app).
# ---------------------------------------------------------------------------
_cors_raw = os.environ.get("PERMITSIGNAL_CORS_ORIGINS", "")
_allowed_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
if not _allowed_origins:
    # Sensible defaults when the env var is unset (local development).
    _allowed_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
# Always allow the production Vercel frontend regardless of env var.
_vercel_origin = "https://permitsignal.vercel.app"
if _vercel_origin not in _allowed_origins:
    _allowed_origins.append(_vercel_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "Provo Administrative Services Finance",
        "status": "online",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "permitsignal-api",
        "version": "1.0.0",
    }


@app.get("/scrape/provo")
def scrape_provo():
    try:
        records = collect_provo_records_dict()

        return {
            "status": "success",
            "municipality": "Provo",
            "state": "Utah",
            "count": len(records),
            "records": records,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


class DiscoverProvoRequest(BaseModel):
    reference_date: Optional[str] = None
    live_enrichment: bool = False
    sync_to_supabase: bool = True
    dry_run: bool = False


@app.post("/discover/provo")
def discover_provo(request: DiscoverProvoRequest):
    """
    Phase 2 live discovery boundary: discovers current Provo government
    packets (backend.app.collectors.provo.collect_provo_records()), skips
    any already known (backend.app.services.document_registry), and
    feeds every new packet into the EXISTING ingestion pipeline
    (document_downloader.download_document() +
    pipeline_orchestrator.run_and_save()) -- the same pipeline
    /pipeline/ingest uses. A scheduler (e.g. n8n) calls this endpoint on
    an interval; no discovery/extraction logic is duplicated there.
    """
    try:
        summary = discovery_orchestrator.discover_and_ingest_provo(
            reference_date=_parse_reference_date(request.reference_date),
            live_enrichment=request.live_enrichment,
            sync_to_supabase=request.sync_to_supabase,
            dry_run=request.dry_run,
        )

        return {"status": "success", **summary}

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads")
def list_leads(
    priority: Optional[str] = None,
    limit: Optional[int] = None,
    commercial_readiness: Optional[str] = None,
    outreach_status: Optional[str] = None,
):
    """
    Phase 4 intelligence retrieval boundary: returns the complete
    production lead queue -- every canonical lead/opportunity record
    (project/application, applicant/company, owner/person, approval-action,
    and lead/opportunity intelligence -- the same shape pipeline_orchestrator
    produces and lead_repository.upsert_leads() persists), sorted the same
    way the pipeline's own lead queue is sorted.

    Supabase (lead_repository.fetch_leads()) is the primary source when
    configured; the pipeline's always-produced JSON artifact
    (case_report_generator.load_lead_queue()) is the fallback whenever
    Supabase is not configured, has no rows yet, or a genuine Supabase
    error occurs -- so this endpoint works in every environment the
    pipeline already runs in.
    """
    try:
        leads: list = []
        source: Optional[str] = None

        if lead_repository.is_configured():
            try:
                leads = lead_repository.fetch_leads()
                if leads:
                    source = "supabase"
            except Exception:
                leads = []

        if not leads:
            leads = case_report_generator.load_lead_queue()
            source = "json_output"

        leads = opportunity_builder.sort_opportunities(leads)

        if priority:
            leads = [
                lead
                for lead in leads
                if str(lead.get("priority") or "").upper() == priority.upper()
            ]

        if commercial_readiness:
            leads = [
                lead
                for lead in leads
                if str(lead.get("commercial_readiness") or "").upper()
                == commercial_readiness.upper()
            ]

        if outreach_status:
            leads = [
                lead
                for lead in leads
                if str(lead.get("outreach_status") or "").upper()
                == outreach_status.upper()
            ]

        if limit is not None:
            leads = leads[: max(limit, 0)]

        return {
            "status": "success",
            "count": len(leads),
            "source": source,
            "leads": leads,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}")
def get_lead(application_number: str):
    """
    Phase 4 intelligence retrieval boundary: returns the complete canonical
    lead/opportunity record for one application_number -- project/
    application, applicant/company, owner/person, approval-action, and
    lead/opportunity intelligence, evidence, sources, confidence, and
    relevant dates all included, since every field the pipeline computes is
    preserved verbatim in this one record (see Opportunity.to_dict() /
    lead_repository's "record" JSONB column).

    Supabase (lead_repository.fetch_lead()) is the primary source when
    configured; the pipeline's always-produced JSON artifact
    (case_report_generator.load_lead_by_application_number(), the same
    source /leads/{application_number}/report.pdf already reads) is the
    fallback whenever Supabase is not configured, has no matching row, or a
    genuine Supabase error occurs.
    """
    try:
        lead = None
        source: Optional[str] = None

        if lead_repository.is_configured():
            try:
                lead = lead_repository.fetch_lead(application_number)
                if lead is not None:
                    source = "supabase"
            except Exception:
                lead = None

        if lead is None:
            lead = case_report_generator.load_lead_by_application_number(application_number)
            if lead is not None:
                source = "json_output"

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        return {
            "status": "success",
            "application_number": application_number,
            "source": source,
            "lead": lead,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/report.pdf")
def get_case_report_pdf(application_number: str):
    """
    Renders the PermitSignal Property Intelligence Case Report PDF for a
    single lead. Uses the same Supabase-primary / JSON-fallback lookup as
    GET /leads/{application_number} so the report endpoint can find any
    lead the case page can display.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        pdf_bytes = case_report_generator.generate_case_report_pdf(lead)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="provo_administrative_services_finance_case_report_{application_number}.pdf"',
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# Case Report History endpoints
# ---------------------------------------------------------------------------


@app.post("/leads/{application_number}/report")
def generate_and_store_report(application_number: str):
    """
    Generates a Property Intelligence Case Report PDF for a lead and
    persists the result to Supabase as a versioned artifact. Returns
    the stored record metadata (without the PDF payload); use
    GET .../reports/{version}/pdf to download the actual PDF.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        stored = case_report_store.generate_and_store(lead, generated_by="api")

        return {
            "status": "success",
            "application_number": application_number,
            "version": stored.get("version"),
            "generated_at": stored.get("generated_at"),
            "page_count": stored.get("page_count"),
            "file_size_bytes": stored.get("file_size_bytes"),
            "checksum": stored.get("checksum"),
            "storage": "supabase" if case_report_store.is_configured() else "memory_only",
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/reports")
def list_case_reports(application_number: str, limit: int = 20):
    """
    Returns the case report history for an application, newest first.
    Each record includes metadata (version, timestamp, page count, size)
    but not the PDF payload itself. Use GET .../reports/{version}/pdf
    to download a specific version.
    """
    try:
        if not case_report_store.is_configured():
            return {
                "status": "success",
                "application_number": application_number,
                "count": 0,
                "reports": [],
                "storage": "not_configured",
            }

        reports = case_report_store.fetch_reports(application_number, limit=limit)

        return {
            "status": "success",
            "application_number": application_number,
            "count": len(reports),
            "reports": reports,
            "storage": "supabase",
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/reports/{version}")
def get_case_report_metadata(application_number: str, version: int):
    """
    Returns the stored case report record metadata for a specific version.
    Does not include the PDF payload; use .../reports/{version}/pdf for that.
    """
    try:
        if not case_report_store.is_configured():
            raise HTTPException(
                status_code=404,
                detail="Case report storage is not configured (Supabase required).",
            )

        record = case_report_store.fetch_report(application_number, version)

        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"No case report found for application_number={application_number!r} version={version}",
            )

        # Strip pdf_base64 from response
        record.pop("pdf_base64", None)

        return {
            "status": "success",
            "application_number": application_number,
            "report": record,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/reports/{version}/pdf")
def get_case_report_pdf_version(application_number: str, version: int):
    """
    Downloads the actual PDF for a specific stored case report version.
    Falls back to on-the-fly generation if Supabase is not configured
    and version=1 is requested.
    """
    try:
        if case_report_store.is_configured():
            record = case_report_store.fetch_report(application_number, version)
            if record is not None:
                pdf_bytes = case_report_store.get_pdf_bytes(record)
                if pdf_bytes:
                    return Response(
                        content=pdf_bytes,
                        media_type="application/pdf",
                        headers={
                            "Content-Disposition": f'inline; filename="provo_administrative_services_finance_case_report_{application_number}_v{version}.pdf"',
                        },
                    )

        # Fallback: generate on the fly for version 1 if storage is unavailable
        if version == 1:
            lead = _fetch_lead_any_source(application_number)
            if lead is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No lead on record for application_number={application_number!r}",
                )
            pdf_bytes = case_report_generator.generate_case_report_pdf(lead)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                            "Content-Disposition": f'inline; filename="provo_administrative_services_finance_case_report_{application_number}.pdf"',
                },
            )

        raise HTTPException(
            status_code=404,
            detail=f"No case report found for application_number={application_number!r} version={version}",
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


def _fetch_lead_any_source(application_number: str) -> Optional[dict]:
    """
    Shared Supabase-primary/JSON-fallback lookup used by the Phase 8
    outreach endpoints below -- identical precedence to GET /leads/
    {application_number} above, kept as its own helper since both new
    endpoints need the raw lead dict rather than the wrapped response.
    """
    lead = None

    if lead_repository.is_configured():
        try:
            lead = lead_repository.fetch_lead(application_number)
        except Exception:
            lead = None

    if lead is None:
        lead = case_report_generator.load_lead_by_application_number(application_number)

    return lead


@app.get("/leads/{application_number}/outreach")
def get_outreach_package(application_number: str):
    """
    Phase 8 outreach preparation boundary: returns the structured
    outreach-ready representation for one lead -- the selected contact
    target (backend.app.services.outreach_intelligence.
    resolve_outreach_contact()), recommended channel, a personalized
    message draft (never generated for a lead with no usable contact
    evidence), current lifecycle/qualification status, and the existing
    Phase 3/6 evidence (approval_action/commercial_action_reason) behind
    it. This is preparation only -- it never sends anything.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        contact = outreach_intelligence.resolve_outreach_contact(lead)
        channel = outreach_intelligence.recommend_outreach_channel(contact)
        message = (
            outreach_intelligence.build_outreach_message(lead, contact)
            if outreach_intelligence.is_outreach_eligible(lead)
            else None
        )

        return {
            "status": "success",
            "application_number": application_number,
            "outreach_status": lead.get("outreach_status"),
            "outreach_qualification_status": lead.get("outreach_qualification_status")
            or outreach_intelligence.classify_outreach_qualification(lead),
            "commercial_readiness": lead.get("commercial_readiness"),
            "recommended_commercial_action": lead.get("recommended_commercial_action"),
            "commercial_action_reason": lead.get("commercial_action_reason"),
            "contact": contact,
            "channel": channel,
            "message": message,
            "follow_up_required": lead.get("follow_up_required", False),
            "follow_up_reason": lead.get("follow_up_reason"),
            "outreach_events": lead.get("outreach_events") or [],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


class OutreachEventRequest(BaseModel):
    event: str
    note: Optional[str] = None


@app.get("/leads/{application_number}/intelligence")
def get_intelligence_package(application_number: str):
    """
    Returns the full approval intelligence package for one lead:
    evidence registry, denial history, approval blockers, requirements
    (A/B/C classified), recommended actions, decision path, stakeholders,
    service recommendation, pricing, client message, and internal strategy.
    """
    try:
        from backend.app.services.approval_intelligence_engine import build_approval_intelligence
        from backend.app.services.pricing_engine import calculate_pricing
        from datetime import date as date_cls

        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        intelligence = build_approval_intelligence(lead, reference_date=date_cls.today())

        pricing = None
        pricing_inputs = intelligence.get("pricing_inputs")
        if pricing_inputs and isinstance(pricing_inputs, dict):
            try:
                pricing = calculate_pricing(pricing_inputs)
            except Exception:
                pricing = {"status": "error"}

        return {
            "status": "success",
            "application_number": application_number,
            "intelligence": intelligence,
            "pricing": pricing,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/leads/{application_number}/outreach/events")
def record_outreach_event(application_number: str, request: OutreachEventRequest):
    """
    Phase 8 controlled lead-lifecycle boundary: applies one outreach event
    (outreach_prepared, outreach_sent, response_received, engaged,
    follow_up_required, opportunity_created, won, lost -- see
    outreach_intelligence.SUPPORTED_EVENTS) to a lead's outreach_status,
    then persists the result. This is the "Human/Controlled Approval"
    step (CLAUDE.md Phase 8 section 11) -- PermitSignal never sends
    outreach or advances a lead automatically; a human or an n8n step
    calls this endpoint deliberately after outreach actually happens.

    Requires Supabase persistence to be configured: outreach lifecycle
    state must survive the next pipeline run (see
    pipeline_orchestrator._load_previous_leads_by_number()), and the
    JSON artifact is only ever written by a full pipeline run, not by
    this endpoint.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        try:
            updated = outreach_intelligence.apply_outreach_event(
                lead,
                request.event,
                note=request.note,
                occurred_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not lead_repository.is_configured():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Supabase is not configured (SUPABASE_URL/SUPABASE_KEY). "
                    "Outreach lifecycle tracking requires persistence that "
                    "survives the next pipeline run."
                ),
            )

        lead_repository.upsert_leads([updated])

        return {
            "status": "success",
            "application_number": application_number,
            "lead": updated,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


class InvestigationRequest(BaseModel):
    note: Optional[str] = None
    force: bool = False


def _get_investigation_lead_or_404(application_number: str) -> dict:
    lead = _fetch_lead_any_source(application_number)
    if lead is None:
        raise HTTPException(
            status_code=404,
            detail=f"No lead on record for application_number={application_number!r}",
        )
    return lead


def _persist_investigation_lead(lead: dict) -> None:
    if lead_repository.is_configured():
        try:
            lead_repository.upsert_leads([lead])
        except Exception as exc:
            import logging
            logging.warning(
                "Investigation persistence failed for %s: %s",
                lead.get("application_number", "?"),
                exc,
            )


@app.get("/leads/{application_number}/investigation")
def get_investigation(application_number: str):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.get_investigation(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation": inv,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/leads/{application_number}/investigation/status")
def get_investigation_status(application_number: str):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.get_investigation(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status", "NOT_STARTED"),
            "source_status": inv.get("sources", {}),
            "summary": inv.get("summary", {}),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/leads/{application_number}/investigation/evidence")
def get_investigation_evidence(application_number: str):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.get_investigation(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "evidence": inv.get("evidence", []),
            "contacts": inv.get("contacts", {}),
            "identity_matches": inv.get("identity_matches", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/leads/{application_number}/investigation/events")
def get_investigation_events(application_number: str):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.get_investigation(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "events": inv.get("events", []),
            "errors": inv.get("errors", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/web")
def investigate_web(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "web", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/website")
def investigate_website(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "website", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/directories")
def investigate_directories(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "directories", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/linkedin")
def investigate_linkedin(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "linkedin", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/public-records")
def investigate_public_records(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "public_records", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/project")
def investigate_project(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "project", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/contact")
def investigate_contact(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_single_source(
            lead, "contact", force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "events": inv.get("events", [])[-1:],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/investigation/all")
def investigate_all(application_number: str, request: InvestigationRequest):
    try:
        lead = _get_investigation_lead_or_404(application_number)
        inv = investigation_engine.run_all(
            lead, force=request.force, note=request.note,
        )
        _persist_investigation_lead(lead)
        contacts = inv.get("contacts", {})
        summary = inv.get("summary", {})
        return {
            "status": "success",
            "application_number": application_number,
            "investigation_status": inv.get("status"),
            "source_status": inv.get("sources", {}),
            "evidence_count": len(inv.get("evidence", [])),
            "emails_found": summary.get("emails_found", 0),
            "phones_found": summary.get("phones_found", 0),
            "websites_found": summary.get("websites_found", 0),
            "profiles_found": summary.get("profiles_found", 0),
            "identity_matches": len(inv.get("identity_matches", [])),
            "preferred_email": contacts.get("preferred_email"),
            "preferred_phone": contacts.get("preferred_phone"),
            "preferred_website": contacts.get("preferred_website"),
            "events": inv.get("events", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/leads/{application_number}/enrich")
def enrich_lead(application_number: str):
    """
    Single-lead live contact enrichment boundary. Calls the existing
    applicant_enrichment.enrich_applicant_contact() with live_search=True
    to perform public-web SerpAPI searches for this one applicant. Preserves
    government-record contact precedence (never overwrites a government-
    sourced email/phone with a lower-confidence public-web guess).
    Persists the enriched lead to Supabase via the same path the
    investigation endpoints use.
    """
    try:
        lead = _get_investigation_lead_or_404(application_number)

        enrichment = applicant_enrichment.enrich_applicant_contact(
            lead, live_search=True,
        )

        if not isinstance(enrichment, dict):
            raise HTTPException(
                status_code=500,
                detail="enrich_applicant_contact returned an unexpected type",
            )

        # Government-record precedence: never overwrite a government-
        # sourced email/phone with a lower-confidence public-web guess.
        government_email = lead.get("applicant_email")
        government_phone = lead.get("applicant_phone")

        # Merge enrichment results onto the lead (overlay non-None keys).
        for key, value in enrichment.items():
            if value is not None:
                lead[key] = value

        if government_email:
            lead["applicant_email"] = government_email
            lead["email_source"] = "government_record"
            lead["email_confidence"] = 1.0

        if government_phone:
            lead["applicant_phone"] = government_phone
            lead["phone_source"] = "government_record"
            lead["phone_confidence"] = 1.0

        # Additive discovered parties (same pattern as pipeline_orchestrator).
        discovered_parties = enrichment.get("discovered_parties")
        if discovered_parties:
            lead["parties"] = list(lead.get("parties") or []) + list(
                discovered_parties
            )
        lead.pop("discovered_parties", None)

        lead["enrichment_status"] = enrichment.get(
            "enrichment_status", "enriched"
        )

        _persist_investigation_lead(lead)

        return {
            "status": "success",
            "application_number": application_number,
            "enrichment_status": lead.get("enrichment_status"),
            "enrichment_method": enrichment.get("enrichment_method"),
            "applicant_email": lead.get("applicant_email"),
            "applicant_phone": lead.get("applicant_phone"),
            "email_confidence": lead.get("email_confidence"),
            "phone_confidence": lead.get("phone_confidence"),
            "company_website": lead.get("company_website"),
            "company_name": lead.get("company_name"),
            "contact_name": lead.get("contact_name"),
            "contact_email": lead.get("contact_email"),
            "contact_phone": lead.get("contact_phone"),
            "contact_source": lead.get("contact_source"),
            "contact_confidence": lead.get("contact_confidence"),
            "contact_is_public": lead.get("contact_is_public"),
            "contact_is_verified": lead.get("contact_is_verified"),
            "company_source": lead.get("company_source"),
            "linkedin_url": lead.get("linkedin_url"),
            "sources_count": len(enrichment.get("sources", [])),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Address Intelligence
#
# Geocode, verify, and enrich a single lead's property address with
# verified real-world location intelligence.  Entirely additive:
# government-record addresses are never modified.
# ---------------------------------------------------------------------------

class AddressEnrichmentRequest(BaseModel):
    force: bool = False


@app.post("/leads/{application_number}/address/enrich")
def enrich_address(application_number: str, request: AddressEnrichmentRequest):
    """
    Enrich a single lead's property address with geocoded location
    intelligence.

    This is additive-only: the original government-record address is
    never modified.  Results are cached per normalized address and
    carried forward across pipeline runs.

    force=True re-enriches even if previously resolved within TTL.
    """
    try:
        from backend.app.services import address_intelligence
        from backend.app.services import lead_repository

        lead = _get_investigation_lead_or_404(application_number)

        # Carry forward any existing address intelligence fields
        # from the lead record for the enrichment function.
        result = address_intelligence.enrich_address_intelligence(
            lead,
            force=request.force,
        )

        # Persist the enriched address fields back to the lead
        _persist_investigation_lead(lead)

        return {
            "status": "success",
            "application_number": application_number,
            "address_enrichment_status": lead.get("address_enrichment_status"),
            "address_source_address": lead.get("address_source_address"),
            "address_geocoded_lat": lead.get("address_geocoded_lat"),
            "address_geocoded_lng": lead.get("address_geocoded_lng"),
            "address_geocoded_city": lead.get("address_geocoded_city"),
            "address_geocoded_state": lead.get("address_geocoded_state"),
            "address_geocoded_postal": lead.get("address_geocoded_postal"),
            "address_geocoded_county": lead.get("address_geocoded_county"),
            "address_geocoded_full": lead.get("address_geocoded_full"),
            "address_geocoding_source": lead.get("address_geocoding_source"),
            "address_geocoding_confidence": lead.get("address_geocoding_confidence"),
            "address_geocoding_method": lead.get("address_geocoding_method"),
            "address_geocoding_evidence": lead.get("address_geocoding_evidence"),
            "address_geocoded_at": lead.get("address_geocoded_at"),
            "address_parcel_id_verified": lead.get("address_parcel_id_verified"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Entity Intelligence (deep case research)
#
# Bounded iterative public-web research over one case's entities:
# CASE -> PROPERTY -> OWNER -> APPLICANT -> AGENT -> PEOPLE ->
# ORGANIZATIONS -> ENTITY RESOLUTION -> RELATIONSHIPS -> EVIDENCE ->
# ENRICHED CASE INTELLIGENCE. Entirely additive to the lead record; the
# result is stored under lead["case_intelligence"] and, when Supabase
# tables from migration 0008 exist, mirrored into normalized rows.
# ---------------------------------------------------------------------------

class CaseResearchRequest(BaseModel):
    max_depth: int = 2
    max_queries: int = 30
    max_pages: int = 10
    persist_entities: bool = True


def _build_seed_only_case_intelligence(lead: dict):
    """
    Deterministic, network-free enriched case record built purely from
    the government-record seed graph (used when no research has run yet).
    """
    from backend.app.services.case_research_engine import CaseResearchEngine

    engine = CaseResearchEngine(
        lead,
        serpapi_key=None,
        max_queries=0,
        max_pages=0,
        max_depth=0,
    )
    return engine.run()


@app.post("/leads/{application_number}/intelligence/research")
def research_case_intelligence(application_number: str, request: CaseResearchRequest):
    """
    Run bounded deep research for one case: seeds entities from the
    government record, searches the public web per source-hierarchy
    priority, resolves identities with multi-signal matching, records
    claim-level evidence, and stores the additive case_intelligence
    record on the lead (persisted like other investigation state).
    """
    try:
        from backend.app.services.case_research_engine import run_case_research

        lead = _get_investigation_lead_or_404(application_number)

        record = run_case_research(
            lead,
            persist=request.persist_entities,
            max_depth=max(0, min(request.max_depth, 3)),
            max_queries=max(0, min(request.max_queries, 60)),
            max_pages=max(0, min(request.max_pages, 20)),
        )

        _persist_investigation_lead(lead)

        stats = record.get("stats", {})
        return {
            "status": "success",
            "application_number": application_number,
            "research_run": record.get("research_run", {}),
            "stats": stats,
            "entities": [
                {
                    "entity_key": e.get("entity_key"),
                    "entity_type": e.get("entity_type"),
                    "canonical_name": e.get("canonical_name"),
                    "match_status": e.get("match_status"),
                    "match_confidence": e.get("match_confidence"),
                }
                for e in record.get("entities", [])
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/leads/{application_number}/intelligence/entities")
def get_case_entities(application_number: str):
    """Entity/evidence/match view of one case's stored intelligence."""
    try:
        lead = _get_investigation_lead_or_404(application_number)
        stored = lead.get("case_intelligence")

        if not isinstance(stored, dict) or not stored.get("entities"):
            stored = _build_seed_only_case_intelligence(lead)

        return {
            "status": "success",
            "application_number": application_number,
            "product": stored.get("product"),
            "entities": stored.get("entities", []),
            "relationships": stored.get("relationships", []),
            "evidence": stored.get("evidence", []),
            "sources": stored.get("sources", []),
            "research_run": stored.get("research_run", {}),
            "stats": stored.get("stats", {}),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/leads/{application_number}/intelligence/enriched-case")
def get_enriched_case(application_number: str):
    """
    Consumer-ready enriched case intelligence record (the structure a
    future PDF/dashboard consumes): case, property, people,
    organizations, relationships, contact claims, evidence with source
    hierarchy ranks, confidence, and research status. Falls back to the
    deterministic government-record seed record when no live research
    has been run yet.
    """
    try:
        lead = _get_investigation_lead_or_404(application_number)
        stored = lead.get("case_intelligence")

        if not isinstance(stored, dict) or not stored.get("entities"):
            stored = _build_seed_only_case_intelligence(lead)

        return {
            "status": "success",
            "application_number": application_number,
            "case_intelligence": stored,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _parse_reference_date(value: Optional[str]) -> Optional[date]:
    """
    pipeline_orchestrator.run_pipeline() requires reference_date as a
    date object (it calls .isoformat() on it); both ingest endpoints
    receive it as a plain string (JSON body / multipart form field), so
    it must be parsed here at the API boundary before being passed
    through.
    """
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"reference_date must be YYYY-MM-DD, got {value!r}",
        ) from exc


class PipelineIngestRequest(BaseModel):
    source_url: str
    reference_date: Optional[str] = None
    live_enrichment: bool = False
    sync_to_supabase: bool = True


@app.post("/pipeline/ingest")
def pipeline_ingest(request: PipelineIngestRequest):
    """
    First n8n production boundary (CLAUDE.md Part 11): fetches a government
    packet from source_url, validates it's a real PDF (both handled by
    document_downloader.download_document()), then runs the full
    PermitSignal pipeline -- including, when sync_to_supabase=True, the
    Supabase upsert -- via pipeline_orchestrator.run_and_save(). n8n's job
    is to call this endpoint and branch on the response; the fetch,
    extraction, enrichment, and persistence logic all stay in this
    backend, not duplicated in the n8n workflow.
    """
    try:
        pdf_path = document_downloader.download_document(request.source_url)

        result = pipeline_orchestrator.run_and_save(
            pdf_path=pdf_path,
            reference_date=_parse_reference_date(request.reference_date),
            live_enrichment=request.live_enrichment,
            sync_to_supabase=request.sync_to_supabase,
        )

        metadata = result.get("metadata", {})

        return {
            "status": "success",
            "pdf_path": str(pdf_path),
            "output_path": metadata.get("output_path"),
            "counts": {
                "applications": len(result.get("applications", [])),
                "opportunities": len(result.get("opportunities", [])),
                "lead_queue": len(result.get("lead_queue", [])),
            },
            "supabase_sync": metadata.get("supabase_sync"),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# =========================================================================
# SOURCE REGISTRY — government source management
# =========================================================================


class GovernmentSourceRequest(BaseModel):
    source_key: str
    state: str
    city: Optional[str] = None
    county: Optional[str] = None
    agency: str
    source_url: str
    source_type: str
    platform: Optional[str] = None
    adapter: str = "pdf"
    active: bool = True
    config: Optional[dict] = None


@app.get("/sources")
def list_sources(
    active_only: bool = False,
    state: Optional[str] = None,
):
    """List all configured government sources."""
    sources = source_registry.list_sources(active_only=active_only, state=state)
    return {
        "status": "success",
        "sources": sources,
        "total": len(sources),
    }


@app.get("/sources/{source_key}")
def get_source(source_key: str):
    """Get a single government source by key."""
    source = source_registry.get_source(source_key)
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"No source found for source_key={source_key!r}",
        )
    return {"status": "success", "source": source}


@app.post("/sources")
def create_source(request: GovernmentSourceRequest):
    """Create or update a government source."""
    source = request.model_dump()
    if request.config is None:
        source["config"] = {}
    result = source_registry.upsert_source(source)
    return {"status": "success", "source": result}


@app.post("/sources/{source_key}/deactivate")
def deactivate_source(source_key: str):
    """Deactivate a government source."""
    found = source_registry.deactivate_source(source_key)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"No source found for source_key={source_key!r}",
        )
    return {"status": "success", "source_key": source_key, "active": False}


@app.post("/sources/ingest")
def ingest_all_sources(
    reference_date: Optional[date] = None,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
    source_keys: Optional[list[str]] = None,
):
    """
    Run multi-source discovery and ingestion across all active sources.
    Each source is discovered via its configured adapter, new documents
    are downloaded, and ingestible documents are run through the pipeline.
    """
    try:
        result = discovery_orchestrator.discover_and_ingest_all(
            reference_date=reference_date,
            sync_to_supabase=sync_to_supabase,
            dry_run=dry_run,
            source_keys=source_keys,
        )
        return {"status": "success", **result}

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/sources/{source_key}/ingest")
def ingest_source(
    source_key: str,
    reference_date: Optional[date] = None,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
):
    """
    Discover and ingest documents from a single government source.
    """
    source = source_registry.get_source(source_key)
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"No source found for source_key={source_key!r}",
        )

    try:
        from backend.app.services import document_registry
        registry = document_registry.load_registry()
        result = discovery_orchestrator.ingest_from_source(
            source,
            registry,
            reference_date=reference_date,
            sync_to_supabase=sync_to_supabase,
            dry_run=dry_run,
        )
        return {"status": "success", **result}

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# Profile Matrix endpoints
# ---------------------------------------------------------------------------

class MatrixGenerateRequest(BaseModel):
    instruction: Optional[str] = None
    is_draft: bool = False
    previous_version: Optional[int] = None
    messages: Optional[list[dict[str, str]]] = None


@app.post("/leads/{application_number}/matrix")
def matrix_generate(application_number: str, request: MatrixGenerateRequest):
    """
    Profile Matrix generation boundary: executes a Matrix instruction against
    an existing lead profile.

    Supports two modes:
      - Chat mode (messages provided): full conversational interaction with
        context filtering, conversation history, and task-aware responses.
      - Legacy mode (instruction provided): single-instruction generation
        with full profile context.

    Reads the lead (read-only), builds profile context, calls the configured
    LLM, stores the output as a versioned artifact in matrix_outputs, and
    returns it. The source lead record is NEVER mutated.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        if request.messages:
            generated_output = matrix_engine.execute_matrix_chat(
                lead, request.messages,
            )
            last_user_msg = ""
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")
                    break
            instruction_for_storage = last_user_msg or "[chat]"
        else:
            instruction_text = request.instruction or ""
            previous_output = None
            if request.previous_version is not None:
                previous_record = matrix_engine.fetch_output_by_version(
                    application_number, request.previous_version,
                )
                if previous_record is not None:
                    previous_output = previous_record.get("output")

            generated_output = matrix_engine.execute_matrix_instruction(
                lead, instruction_text, previous_output=previous_output,
            )
            instruction_for_storage = instruction_text

        version = matrix_engine.get_next_version(application_number)

        if request.is_draft:
            stored = matrix_engine.save_draft(
                application_number=application_number,
                instruction=instruction_for_storage,
                output=generated_output,
            )
        else:
            stored = matrix_engine.save_final(
                application_number=application_number,
                instruction=instruction_for_storage,
                output=generated_output,
            )

        return {
            "status": "success",
            "application_number": application_number,
            "output": generated_output,
            "version": stored.get("version", version),
            "is_draft": stored.get("is_draft", request.is_draft),
            "id": stored.get("id"),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/matrix")
def matrix_list_outputs(application_number: str, limit: int = 50):
    """
    Returns the Matrix output history for an application/profile, newest
    first. Each record is a versioned artifact stored in matrix_outputs --
    the source lead is never read by this endpoint.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        outputs = matrix_engine.fetch_outputs(application_number, limit=limit)

        return {
            "status": "success",
            "application_number": application_number,
            "count": len(outputs),
            "outputs": outputs,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/leads/{application_number}/matrix/{version}")
def matrix_get_output(application_number: str, version: int):
    """
    Returns a single Matrix output by version number for an application.
    """
    try:
        lead = _fetch_lead_any_source(application_number)

        if lead is None:
            raise HTTPException(
                status_code=404,
                detail=f"No lead on record for application_number={application_number!r}",
            )

        record = matrix_engine.fetch_output_by_version(application_number, version)

        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"No Matrix output found for application_number={application_number!r} version={version}",
            )

        return {
            "status": "success",
            "application_number": application_number,
            "output": record,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/pipeline/ingest/file")
async def pipeline_ingest_file(
    file: UploadFile = File(...),
    reference_date: Optional[str] = Form(None),
    live_enrichment: bool = Form(False),
    sync_to_supabase: bool = Form(True),
):
    """
    Second n8n production boundary: accepts an actual government packet
    PDF as a real multipart/form-data file upload (e.g. from an n8n
    Webhook trigger's binary data), rather than a source_url n8n would
    have to fetch itself. This is for callers that already hold the
    packet's bytes (an inbound webhook, an email attachment, a watched
    folder) instead of a public URL /pipeline/ingest can GET.

    document_downloader.save_uploaded_document() validates the upload is
    a real PDF (checks the %PDF magic bytes, same as download_document())
    and writes it into data/documents/, then pipeline_orchestrator.
    run_and_save() runs the identical pipeline -- including the Supabase
    upsert when sync_to_supabase=True -- as the URL-based endpoint above.
    """
    try:
        content = await file.read()

        pdf_path = document_downloader.save_uploaded_document(
            file.filename,
            content,
        )

        result = pipeline_orchestrator.run_and_save(
            pdf_path=pdf_path,
            reference_date=_parse_reference_date(reference_date),
            live_enrichment=live_enrichment,
            sync_to_supabase=sync_to_supabase,
        )

        metadata = result.get("metadata", {})

        return {
            "status": "success",
            "pdf_path": str(pdf_path),
            "output_path": metadata.get("output_path"),
            "counts": {
                "applications": len(result.get("applications", [])),
                "opportunities": len(result.get("opportunities", [])),
                "lead_queue": len(result.get("lead_queue", [])),
            },
            "supabase_sync": metadata.get("supabase_sync"),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )