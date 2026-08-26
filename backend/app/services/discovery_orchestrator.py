from __future__ import annotations

"""
PermitSignal discovery and ingestion orchestrator — multi-source.

Purpose
-------
Discover new government documents from configured sources, then feed
each newly discovered document into the EXISTING PermitSignal ingestion
pipeline (document_downloader + pipeline_orchestrator) unchanged.

This module does NOT implement a second extraction/intelligence engine.
Its only job is: source config -> adapter selection -> discovery ->
registry bookkeeping -> pipeline handoff.

Backward Compatibility
----------------------
``discover_and_ingest_provo()`` is preserved unchanged.  The new
``discover_and_ingest_all()`` function iterates over ALL active sources
from the source registry, using the adapter specified on each source
record.

Idempotency
-----------
``document_registry`` tracks which document URLs have already been
discovered, so re-running discovery does not re-download or re-run
the pipeline against a document already known.  Downstream lead
duplication is handled separately by ``lead_repository.upsert_leads()``.
"""

from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

from backend.app.collectors.provo import collect_provo_records
from backend.app.services import document_downloader, document_registry, pipeline_orchestrator
from backend.app.services.source_adapters.base import DocumentRecord


PACKET_RECORD_TYPES = {"agenda", "pdf_direct", "minutes"}


def _record_to_dict(record: Any) -> dict[str, Any]:
    if is_dataclass(record):
        return asdict(record)
    return dict(record)


def _document_record_to_dict(record: DocumentRecord) -> dict[str, Any]:
    return {
        "source_key": record.source_key,
        "url": record.url,
        "title": record.title,
        "date": record.document_date,
        "record_type": record.record_type,
        "source": record.source_key,
        **record.metadata,
    }


# =========================================================================
# Provo-specific (preserved for backward compatibility)
# =========================================================================


def discover_new_provo_documents(
    registry: dict[str, dict[str, Any]],
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Run the Provo collector and register every discovered document.
    Preserved for backward compatibility.
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


def discover_and_ingest_provo(
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Provo government source -> existing PermitSignal pipeline, end to
    end.  Preserved for backward compatibility.
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
        "source": "provo_planning",
        "discovered_total": len(discovery["all_records"]),
        "new_total": len(discovery["new_records"]),
        "new_packets": len(new_packets),
        "skipped_non_packet": len(skipped_non_packet),
        "dry_run": dry_run,
        "ingested": ingested,
        "errors": errors,
    }


# =========================================================================
# Multi-source (new)
# =========================================================================


def ingest_document(
    record: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
) -> dict[str, Any]:
    """
    Download one discovered document and run it through the existing
    PermitSignal pipeline.  Never raises.
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


def discover_from_source(
    source_config: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Discover new documents from a single source using its configured
    adapter.  Registers new documents in the registry.
    """
    from backend.app.services.source_adapters import get_adapter

    source_key = source_config.get("source_key", "?")
    adapter_name = source_config.get("adapter", "pdf")

    try:
        adapter = get_adapter(adapter_name)
    except ValueError as exc:
        return {
            "source_key": source_key,
            "error": str(exc),
            "all_records": [],
            "new_records": [],
        }

    try:
        doc_records = adapter.discover(source_config)
    except Exception as exc:
        return {
            "source_key": source_key,
            "error": f"Discovery failed: {exc}",
            "all_records": [],
            "new_records": [],
        }

    all_records = [_document_record_to_dict(r) for r in doc_records]
    new_records = document_registry.filter_new_records(all_records, registry)

    for record in new_records:
        document_registry.record_discovered(registry, record)

    document_registry.save_registry(registry, registry_path)

    return {
        "source_key": source_key,
        "adapter": adapter_name,
        "all_records": all_records,
        "new_records": new_records,
    }


def ingest_from_source(
    source_config: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    registry_path: Path | str = document_registry.REGISTRY_PATH,
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Full cycle for one source: discover -> filter ingestible -> download
    -> pipeline -> registry update.
    """
    from backend.app.services.source_adapters import get_adapter
    from backend.app.services import source_registry

    source_key = source_config.get("source_key", "?")
    adapter_name = source_config.get("adapter", "pdf")

    discovery = discover_from_source(
        source_config, registry, registry_path
    )

    if discovery.get("error"):
        return {
            "source_key": source_key,
            "status": "error",
            "error": discovery["error"],
            "discovered_total": 0,
            "new_total": 0,
            "ingested": [],
            "errors": [],
        }

    try:
        adapter = get_adapter(adapter_name)
    except ValueError:
        adapter = None

    new_records = discovery["new_records"]

    ingestible = [
        r for r in new_records
        if adapter is None
        or adapter.is_ingestible(
            DocumentRecord(
                source_key=r.get("source_key", source_key),
                url=r.get("url", ""),
                title=r.get("title", ""),
                record_type=r.get("record_type", "unknown"),
            )
        )
    ]

    skipped = len(new_records) - len(ingestible)
    ingested: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if not dry_run:
        for record in ingestible:
            outcome = ingest_document(
                record,
                registry,
                reference_date=reference_date,
                live_enrichment=live_enrichment,
                sync_to_supabase=sync_to_supabase,
            )
            outcome["source_key"] = source_key

            if outcome.get("status") == "ingested":
                ingested.append(outcome)
            else:
                errors.append(outcome)

        document_registry.save_registry(registry, registry_path)

        source_registry.update_ingestion_metadata(
            source_key,
            {
                "documents_discovered": len(discovery["all_records"]),
                "documents_new": len(new_records),
                "documents_ingested": len(ingested),
                "documents_errors": len(errors),
                "documents_skipped": skipped,
            },
        )

    return {
        "source_key": source_key,
        "adapter": adapter_name,
        "status": "completed",
        "discovered_total": len(discovery["all_records"]),
        "new_total": len(new_records),
        "ingestible": len(ingestible),
        "skipped": skipped,
        "dry_run": dry_run,
        "ingested": ingested,
        "errors": errors,
    }


def discover_and_ingest_all(
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    dry_run: bool = False,
    source_keys: Optional[list[str]] = None,
    registry_path: Path | str = document_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """
    Multi-source discovery and ingestion.

    Loads all active sources from the source registry, discovers new
    documents from each, and feeds ingestible documents through the
    pipeline.

    Parameters
    ----------
    source_keys : list[str] | None
        If provided, only process these specific sources.  Otherwise
        process all active sources.
    """
    from backend.app.services import source_registry

    sources = source_registry.list_sources(active_only=True)
    if source_keys:
        sources = [s for s in sources if s.get("source_key") in source_keys]

    registry = document_registry.load_registry(registry_path)

    results: list[dict[str, Any]] = []
    total_ingested = 0
    total_errors = 0

    for source_config in sources:
        source_key = source_config.get("source_key", "?")
        try:
            result = ingest_from_source(
                source_config,
                registry,
                registry_path=registry_path,
                reference_date=reference_date,
                live_enrichment=live_enrichment,
                sync_to_supabase=sync_to_supabase,
                dry_run=dry_run,
            )
            results.append(result)
            total_ingested += len(result.get("ingested", []))
            total_errors += len(result.get("errors", []))
        except Exception as exc:
            results.append({
                "source_key": source_key,
                "status": "error",
                "error": str(exc),
            })
            total_errors += 1

    return {
        "sources_processed": len(sources),
        "total_ingested": total_ingested,
        "total_errors": total_errors,
        "dry_run": dry_run,
        "results": results,
    }


__all__ = [
    "PACKET_RECORD_TYPES",
    "discover_new_provo_documents",
    "ingest_document",
    "discover_and_ingest_provo",
    "discover_from_source",
    "ingest_from_source",
    "discover_and_ingest_all",
]
