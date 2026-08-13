from datetime import date
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from backend.app.collectors.provo import (
    collect_provo_records_dict,
)
from backend.app.services import case_report_generator, document_downloader
from backend.app.services import pipeline_orchestrator


app = FastAPI(
    title="PermitSignal API",
    description="Government approval intelligence platform",
    version="1.0.0",
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