import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.collectors.provo import (
    collect_provo_records_dict,
)
from backend.app.services import case_report_generator, discovery_orchestrator, document_downloader
from backend.app.services import lead_repository, opportunity_builder, outreach_intelligence, pipeline_orchestrator
from backend.app.services import investigation_engine


app = FastAPI(
    title="PermitSignal API",
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
        "service": "PermitSignal",
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
    single lead, read from the pipeline's production JSON artifact
    (data/output/permitsignal_opportunities.json). See
    backend/app/services/case_report_generator.py for the no-fabrication
    rendering rules this follows.
    """
    try:
        lead = case_report_generator.load_lead_by_application_number(application_number)

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
                "Content-Disposition": f'inline; filename="permitsignal_case_report_{application_number}.pdf"',
            },
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