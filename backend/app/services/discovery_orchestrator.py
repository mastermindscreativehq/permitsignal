from __future__ import annotations

"""
PermitSignal live government source discovery -> existing pipeline
connector (Phase 2).

Purpose
-------
Discover new Provo government packets via
backend.app.collectors.provo.collect_provo_records(), then feed each
newly discovered packet into the EXISTING PermitSignal ingestion
pipeline -- document_downloader.download_document() +
pipeline_orchestrator.run_and_save() -- unchanged from the file/URL
ingestion paths already used by /pipeline/ingest and the n8n intake
workflow.

This module does not implement a second extraction/intelligence engine.
Its only job is discovery -> registry bookkeeping -> handing a document
URL to the pipeline that already exists.

Idempotency
-----------
backend.app.services.document_registry tracks which document URLs have
already been discovered, so re-running discovery does not re-download or
re-run the pipeline against a document already known. Downstream lead
duplication is handled separately by lead_repository.upsert_leads()'s
existing application_number upsert, unrelated to and unaffected by this
module.

Scope
-----
Only GovernmentRecord.record_type == "agenda" entries are treated as
directly ingestible packets: those are the "/AgendaCenter/ViewFile/
Agenda/..." links already verified (CLAUDE.md Part 4, n8n/README.md) to
resolve to a real PDF. "previous_versions" links point to a version-
history page, not a PDF -- they are still registered as discovered (so
they are not re-scraped forever) but are not auto-ingested here.
"""

from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

from backend.app.collectors.provo import collect_provo_records
from backend.app.services import document_downloader, document_registry, pipeline_orchestrator


PACKET_RECORD_TYPES = {"agenda"}


def _record_to_dict(record: Any) -> dict[str, Any]:
    if is_dataclass(record):
        return asdict(record)
    return dict(record)


def discover_new_provo_documents(
    registry: dict[str, dict[str, Any]],
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Run the Provo collector and register every discovered document.

    Every record the collector returns (agenda + previous_versions) is
    registered, so the registry reflects everything ever seen -- but
    only "new_records" with record_type in PACKET_RECORD_TYPES are
    actionable packets for discover_and_ingest_provo() to hand to the
    pipeline.
    """
    raw_records = collect_provo_records()
    all_records = [_record_to_dict(record) for record in raw_records]

    new_records = document_registry.filter_new_records(all_records, registry)

    for record in new_records:
        document_registry.record_discovered(registry, record)

    document_registry.save_registry(registry, registry_path)

    return {
        "all_records": all_records,
        "new_records": new_records,
    }


def ingest_document(
    record: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
) -> dict[str, Any]:
    """
    Download one discovered document and run it through the existing
    PermitSignal pipeline (unchanged: document_downloader.
    download_document() -> pipeline_orchestrator.run_and_save()).
    Registers the outcome in the registry. Never raises -- a failure for
    one document must not abort a batch discovery run.
    """
    url = record.get("url")

    try:
        pdf_path = document_downloader.download_document(url)

        result = pipeline_orchestrator.run_and_save(
            pdf_path=pdf_path,
            reference_date=reference_date,
            live_enrichment=live_enrichment,
            sync_to_supabase=sync_to_supabase,
            verbose=False,
        )

        metadata = result.get("metadata", {})

        outcome = {
            "document_url": url,
            "status": "ingested",
            "pdf_path": str(pdf_path),
            "applications": len(result.get("applications", [])),
            "opportunities": len(result.get("opportunities", [])),
            "lead_queue": len(result.get("lead_queue", [])),
            "supabase_sync": metadata.get("supabase_sync"),
        }

        document_registry.record_processed(
            registry,
            url,
            status="ingested",
            pdf_path=outcome["pdf_path"],
            applications=outcome["applications"],
            opportunities=outcome["opportunities"],
            lead_queue=outcome["lead_queue"],
            supabase_sync=outcome["supabase_sync"],
            error=None,
        )

        return outcome

    except Exception as exc:
        outcome = {
            "document_url": url,
            "status": "error",
            "error": str(exc),
        }

        document_registry.record_processed(
            registry,
            url,
            status="error",
            error=str(exc),
        )

        return outcome


def discover_and_ingest_provo(
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Provo government source -> existing PermitSignal pipeline, end to
    end.

    dry_run=True discovers and registers documents (so idempotency can be
    verified) without downloading or running the pipeline -- useful for
    testing discovery against the real Provo site without triggering a
    full pipeline run / Supabase write.
    """
    registry = document_registry.load_registry(registry_path)

    discovery = discover_new_provo_documents(registry, registry_path)

    new_packets = [
        record
        for record in discovery["new_records"]
        if record.get("record_type") in PACKET_RECORD_TYPES
    ]

    skipped_non_packet = [
        record
        for record in discovery["new_records"]
        if record.get("record_type") not in PACKET_RECORD_TYPES
    ]

    ingested: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if not dry_run:
        for record in new_packets:
            outcome = ingest_document(
                record,
                registry,
                reference_date=reference_date,
                live_enrichment=live_enrichment,
                sync_to_supabase=sync_to_supabase,
            )

            if outcome.get("status") == "ingested":
                ingested.append(outcome)
            else:
                errors.append(outcome)

        document_registry.save_registry(registry, registry_path)

    return {
        "discovered_total": len(discovery["all_records"]),
        "new_total": len(discovery["new_records"]),
        "new_packets": len(new_packets),
        "skipped_non_packet": len(skipped_non_packet),
        "dry_run": dry_run,
        "ingested": ingested,
        "errors": errors,
    }


__all__ = [
    "PACKET_RECORD_TYPES",
    "discover_new_provo_documents",
    "ingest_document",
    "discover_and_ingest_provo",
]
