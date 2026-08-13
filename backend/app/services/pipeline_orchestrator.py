from __future__ import annotations

"""
PermitSignal production pipeline orchestrator.

Location:
    backend/app/services/pipeline_orchestrator.py

Pipeline:
    PDF -> application extraction -> friction analysis
        -> future project dates -> opportunity builder
        -> applicant identity/enrichment -> sorted production queue

This file deliberately keeps service imports at runtime so the orchestrator
can be unit-tested with mocked modules and so analyzer modules can live under
backend.app.analyzers while service modules live under backend.app.services.
"""

import argparse
import importlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_PDF = Path("data/documents/_08122026-415.pdf")
DEFAULT_OUTPUT = Path("data/output/permitsignal_opportunities.json")

APPLICATION_EXTRACTOR_MODULE = "backend.app.services.application_extractor"
FRICTION_ANALYZER_MODULE = "backend.app.analyzers.friction_analyzer"
PROJECT_DATE_MODULE = "backend.app.services.project_date_extractor"
OPPORTUNITY_MODULE = "backend.app.services.opportunity_builder"
APPLICANT_IDENTITY_MODULE = "backend.app.services.applicant_identity"
APPLICANT_ENRICHMENT_MODULE = "backend.app.services.applicant_enrichment"
LEAD_REPOSITORY_MODULE = "backend.app.services.lead_repository"


# ============================================================================
# ERRORS
# ============================================================================

class PipelineError(RuntimeError):
    """Raised when a required pipeline stage cannot execute."""


# ============================================================================
# IMPORT / COMPATIBILITY HELPERS
# ============================================================================

def _import_service(module_name: str):
    """
    Import a service module and raise a useful PipelineError.

    Important:
    friction_analyzer.py belongs in backend/app/analyzers/, not services/.
    """
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise PipelineError(
            f"Unable to import required service '{module_name}': {exc}"
        ) from exc


def _first_callable(module: Any, *names: str) -> Optional[Callable[..., Any]]:
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def _call_compatible(
    fn: Callable[..., Any],
    attempts: list[tuple[tuple[Any, ...], dict[str, Any]]],
) -> Any:
    """
    Call a function against a small list of known-compatible signatures.

    This lets the orchestrator work with the service versions already built
    during the project without forcing all modules to share one giant API.
    """
    last_error: Optional[Exception] = None

    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs)
        except TypeError as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error

    raise PipelineError(f"Unable to call {fn!r}")


# ============================================================================
# PDF
# ============================================================================

def _read_pdf_text(pdf_path: Path | str) -> str:
    path = Path(pdf_path)

    if not path.exists():
        raise PipelineError(
            f"Government PDF does not exist: {path}"
        )

    try:
        import pymupdf
    except ImportError as exc:
        raise PipelineError(
            "PyMuPDF is required. Install it with: "
            "python -m pip install pymupdf"
        ) from exc

    document = pymupdf.open(path)

    try:
        pages = [
            page.get_text("text")
            for page in document
        ]
    finally:
        document.close()

    return "\n".join(pages)


# ============================================================================
# NORMALIZATION
# ============================================================================

def _clean(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", value).strip()


def _normalize_application_number(value: Any) -> Optional[str]:
    if not value:
        return None
    return str(value).strip().upper()


def _deduplicate_applications(
    applications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Deduplicate by application_number while preserving the first canonical
    application record.
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for application in applications:
        if not isinstance(application, dict):
            continue

        number = _normalize_application_number(
            application.get("application_number")
        )

        if not number:
            # Preserve malformed records rather than silently deleting them.
            result.append(dict(application))
            continue

        if number in seen:
            continue

        seen.add(number)

        item = dict(application)
        item["application_number"] = number
        result.append(item)

    return result


def _merge_preserving_left(
    base: dict[str, Any],
    overlay: Optional[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(base)

    if not overlay:
        return result

    for key, value in overlay.items():
        if value is not None:
            result[key] = value

    return result


# ============================================================================
# FRICTION ADAPTER
# ============================================================================

def _normalize_friction_record(
    application: dict[str, Any],
    friction: Optional[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(application)

    friction = friction or {}

    events = (
        friction.get("friction_events")
        or friction.get("events")
        or []
    )

    signals = (
        friction.get("friction_signals")
        or friction.get("signals")
        or []
    )

    score = friction.get("friction_score")

    if score is None:
        score = 0

    result["friction_score"] = int(score or 0)
    result["friction_signals"] = list(dict.fromkeys(signals))
    result["friction_events"] = list(events)

    # Some historical versions exposed "events" / "signals" only.
    result["events"] = result["friction_events"]
    result["signals"] = result["friction_signals"]

    return result


def _analyze_friction(
    text: str,
    applications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    module = _import_service(FRICTION_ANALYZER_MODULE)

    fn = _first_callable(
        module,
        "analyze_applications",
        "analyze_application_friction",
    )

    if fn is None:
        raise PipelineError(
            "Friction analyzer does not expose "
            "analyze_applications() or analyze_application_friction()."
        )

    raw = _call_compatible(
        fn,
        [
            ((text, applications), {}),
            ((applications, text), {}),
        ],
    )

    if not isinstance(raw, list):
        raise PipelineError(
            "Friction analyzer returned a non-list result."
        )

    by_number: dict[str, dict[str, Any]] = {}

    for record in raw:
        if not isinstance(record, dict):
            continue

        number = _normalize_application_number(
            record.get("application_number")
        )

        if number:
            by_number[number] = record

    merged: list[dict[str, Any]] = []

    for application in applications:
        number = _normalize_application_number(
            application.get("application_number")
        )

        friction = by_number.get(number, {})
        merged.append(
            _normalize_friction_record(
                application,
                friction,
            )
        )

    return merged


# ============================================================================
# DATE ADAPTER
# ============================================================================

def _adapt_dates(
    applications: list[dict[str, Any]],
    text: str,
    reference_date: date,
) -> list[dict[str, Any]]:
    module = _import_service(PROJECT_DATE_MODULE)

    enrich_fn = getattr(
        module,
        "enrich_application_dates",
        None,
    )

    if not callable(enrich_fn):
        raise PipelineError(
            "project_date_extractor must expose "
            "enrich_application_dates()."
        )

    enriched: list[dict[str, Any]] = []

    for application in applications:
        record = _call_compatible(
            enrich_fn,
            [
                ((application, text, reference_date), {}),
                ((application, text), {"reference_date": reference_date}),
                ((application, text), {}),
            ],
        )

        if not isinstance(record, dict):
            raise PipelineError(
                "enrich_application_dates() returned a non-dict record."
            )

        item = _merge_preserving_left(
            application,
            record,
        )

        # Safety rule:
        # historical dates must NEVER remain in the live next-event fields.
        next_date = item.get("next_project_date")

        if next_date:
            try:
                parsed = date.fromisoformat(
                    str(next_date)[:10]
                )
            except ValueError:
                parsed = None

            if parsed is not None and parsed < reference_date:
                item["next_project_date"] = None
                item["next_project_event"] = None
                item["next_project_time"] = None
                item["has_future_opportunity"] = False
                item["days_until_event"] = None

        enriched.append(item)

    return enriched


# ============================================================================
# OPPORTUNITY BUILDER
# ============================================================================

def _build_opportunities(
    applications: list[dict[str, Any]],
    reference_date: date,
) -> list[dict[str, Any]]:
    module = _import_service(OPPORTUNITY_MODULE)

    batch_fn = _first_callable(
        module,
        "build_opportunities",
        "build_canonical_opportunities",
    )

    if batch_fn is not None:
        try:
            result = _call_compatible(
                batch_fn,
                [
                    ((applications,), {"reference_date": reference_date}),
                    ((applications,), {}),
                ],
            )

            if isinstance(result, list):
                return result
        except TypeError:
            pass

    single_fn = _first_callable(
        module,
        "build_opportunity",
        "build_canonical_opportunity",
        "build_opportunity_record",
    )

    if single_fn is None:
        raise PipelineError(
            "Opportunity builder does not expose a supported "
            "batch or single-record builder."
        )

    result: list[dict[str, Any]] = []

    for application in applications:
        opportunity = _call_compatible(
            single_fn,
            [
                ((application, reference_date), {}),
                ((application,), {"reference_date": reference_date}),
                ((application,), {}),
            ],
        )

        if not isinstance(opportunity, dict):
            raise PipelineError(
                "Opportunity builder returned a non-dict record."
            )

        result.append(opportunity)

    return result


# ============================================================================
# APPLICANT IDENTITY / ENRICHMENT
# ============================================================================

def _merge_identity(
    opportunity: dict[str, Any],
    application: dict[str, Any],
) -> dict[str, Any]:
    """
    Prefer government-record contact data over inferred/public-web data.
    """
    result = dict(opportunity)

    government_email = (
        application.get("applicant_email")
        or application.get("applicant_email_candidate")
    )
    government_phone = (
        application.get("applicant_phone")
        or application.get("applicant_phone_candidate")
    )

    if government_email:
        result["applicant_email"] = government_email
        result["email_confidence"] = 1.0
        result["email_source"] = "government_record"

    if government_phone:
        result["applicant_phone"] = government_phone
        result["phone_confidence"] = 1.0
        result["phone_source"] = "government_record"

    return result


def _enrich_applicants(
    opportunities: list[dict[str, Any]],
    live_enrichment: bool,
) -> list[dict[str, Any]]:
    identity_module = _import_service(
        APPLICANT_IDENTITY_MODULE
    )

    enrichment_module = _import_service(
        APPLICANT_ENRICHMENT_MODULE
    )

    identity_fn = _first_callable(
        identity_module,
        "enrich_applicant_identity",
        "build_applicant_identity",
        "normalize_applicant_identity",
    )

    enrichment_fn = _first_callable(
        enrichment_module,
        "enrich_applicant",
        "enrich_application",
        "enrich_applicant_contact",
    )

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)

        if identity_fn is not None:
            try:
                identity = _call_compatible(
                    identity_fn,
                    [
                        ((item,), {}),
                    ],
                )

                if isinstance(identity, dict):
                    item = _merge_preserving_left(
                        item,
                        identity,
                    )
            except TypeError:
                # Identity enrichment is optional at this boundary.
                pass

        # Government-record precedence.
        item = _merge_identity(
            item,
            opportunity,
        )

        if live_enrichment and enrichment_fn is not None:
            try:
                enrichment = _call_compatible(
                    enrichment_fn,
                    [
                        ((item,), {"live_search": True}),
                        ((item,), {"use_live_search": True}),
                        ((item,), {}),
                    ],
                )

                if isinstance(enrichment, dict):
                    # Never overwrite a government-record contact with
                    # lower-confidence public-web guesses.
                    government_email = opportunity.get(
                        "applicant_email"
                    )
                    government_phone = opportunity.get(
                        "applicant_phone"
                    )

                    item = _merge_preserving_left(
                        item,
                        enrichment,
                    )

                    if government_email:
                        item["applicant_email"] = government_email
                        item["email_source"] = "government_record"
                        item["email_confidence"] = 1.0

                    if government_phone:
                        item["applicant_phone"] = government_phone
                        item["phone_source"] = "government_record"
                        item["phone_confidence"] = 1.0

            except Exception as exc:
                item["enrichment_status"] = "error"
                item["enrichment_error"] = str(exc)

        elif not live_enrichment:
            item.setdefault(
                "enrichment_status",
                "disabled",
            )

        results.append(item)

    return results


# ============================================================================
# LEAD QUALIFICATION
# ============================================================================

def _qualify_leads(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attach lead-qualification metadata (lead_status / is_contactable) to
    each completed opportunity. Purely additive: does not touch priority,
    priority_score, or any field used for sorting.
    """
    module = _import_service(OPPORTUNITY_MODULE)

    qualify_fn = _first_callable(
        module,
        "qualify_lead",
        "build_lead_record",
    )

    if qualify_fn is None:
        return opportunities

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        qualified = _call_compatible(
            qualify_fn,
            [
                ((opportunity,), {}),
            ],
        )

        results.append(
            qualified if isinstance(qualified, dict) else opportunity
        )

    return results


# ============================================================================
# LEAD PERSISTENCE (SUPABASE)
# ============================================================================

def _persist_leads(
    opportunities: list[dict[str, Any]],
    sync_to_supabase: bool,
) -> dict[str, Any]:
    """
    Optionally persist canonical lead records to Supabase.

    This NEVER raises out of the pipeline. data/output/permitsignal_
    opportunities.json is the pipeline's primary, always-produced
    compatibility-layer artifact; Supabase persistence is a strictly
    additive, opt-in capability. A missing configuration or a genuine
    Supabase/network failure is recorded in the returned status dict
    instead of failing the run.
    """
    if not sync_to_supabase:
        return {"status": "disabled"}

    module = _import_service(LEAD_REPOSITORY_MODULE)

    is_configured_fn = getattr(module, "is_configured", None)

    if callable(is_configured_fn) and not is_configured_fn():
        return {
            "status": "skipped",
            "reason": "not_configured",
        }

    upsert_fn = getattr(module, "upsert_leads", None)

    if not callable(upsert_fn):
        return {
            "status": "error",
            "error": "lead_repository does not expose upsert_leads().",
        }

    try:
        result = upsert_fn(opportunities)
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }

    return result if isinstance(result, dict) else {"status": "synced"}


# ============================================================================
# SORTING / VALIDATION
# ============================================================================

PRIORITY_ORDER = {
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "ARCHIVED": 1,
}


def _priority_sort_key(record: dict[str, Any]) -> tuple:
    priority = str(
        record.get("priority") or "LOW"
    ).upper()

    score = record.get("priority_score") or 0
    friction = record.get("friction_score") or 0
    days = record.get("days_until_event")

    if days is None:
        days_sort = 10**9
    else:
        try:
            days_sort = int(days)
        except (TypeError, ValueError):
            days_sort = 10**9

    return (
        -PRIORITY_ORDER.get(priority, 0),
        -int(score or 0),
        -int(friction or 0),
        days_sort,
    )


def _sort_opportunities(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        opportunities,
        key=_priority_sort_key,
    )


def _validate_opportunity(
    record: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    if not record.get("application_number"):
        errors.append(
            "missing application_number"
        )

    if not record.get("applicant_name"):
        errors.append(
            "missing applicant_name"
        )

    if not record.get("application_type"):
        errors.append(
            "missing application_type"
        )

    return errors


def _validate_batch(
    opportunities: list[dict[str, Any]],
) -> None:
    for index, opportunity in enumerate(opportunities, start=1):
        errors = _validate_opportunity(
            opportunity
        )

        if errors:
            raise PipelineError(
                f"Invalid opportunity #{index}: "
                + "; ".join(errors)
            )


# ============================================================================
# PIPELINE
# ============================================================================

def run_pipeline(
    pdf_path: Path | str = DEFAULT_PDF,
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Execute the complete PermitSignal pipeline.

    Returns:
        {
            "metadata": {...},
            "applications": [...],
            "opportunities": [...],
            "lead_queue": [...]
        }

    sync_to_supabase defaults to False: the JSON output above remains the
    pipeline's primary, always-produced artifact regardless of this flag.
    When True, canonical lead records are additionally upserted into
    Supabase (see backend.app.services.lead_repository); a missing
    configuration or a genuine Supabase failure is recorded in
    metadata["supabase_sync"] rather than failing the run.
    """
    if reference_date is None:
        reference_date = date.today()

    pdf_path = Path(pdf_path)

    if verbose:
        print("=" * 90)
        print("PERMITSIGNAL PRODUCTION PIPELINE")
        print("=" * 90)
        print(
            f"PDF:             {pdf_path}"
        )
        print(
            f"Reference date:  {reference_date.isoformat()}"
        )
        print(
            f"Live enrichment: {live_enrichment}"
        )

    # ------------------------------------------------------------------------
    # 1. PDF
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[1/7] Reading government packet...")

    text = _read_pdf_text(pdf_path)

    if verbose:
        print(
            f"Characters extracted: {len(text):,}"
        )

    # ------------------------------------------------------------------------
    # 2. Applications
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[2/7] Extracting applications...")

    application_module = _import_service(
        APPLICATION_EXTRACTOR_MODULE
    )

    extract_fn = _first_callable(
        application_module,
        "extract_applications",
    )

    if extract_fn is None:
        raise PipelineError(
            "application_extractor does not expose "
            "extract_applications()."
        )

    applications = extract_fn(text)

    if not isinstance(applications, list):
        raise PipelineError(
            "extract_applications() returned a non-list result."
        )

    applications = _deduplicate_applications(
        applications
    )

    if verbose:
        print(
            f"Applications detected: {len(applications)}"
        )

    # ------------------------------------------------------------------------
    # 3. Friction
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[3/7] Analyzing historical friction...")

    friction_enriched = _analyze_friction(
        text,
        applications,
    )

    if verbose:
        high_friction = sum(
            1
            for item in friction_enriched
            if int(item.get("friction_score") or 0) >= 40
        )
        print(
            f"Applications analyzed: {len(friction_enriched)}"
        )
        print(
            f"High-friction applications: {high_friction}"
        )

    # ------------------------------------------------------------------------
    # 4. Dates
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[4/7] Extracting future project dates...")

    date_enriched = _adapt_dates(
        friction_enriched,
        text,
        reference_date,
    )

    future_count = sum(
        1
        for item in date_enriched
        if item.get("has_future_opportunity") is True
    )

    if verbose:
        print(
            f"Future opportunities detected: {future_count}"
        )

    # ------------------------------------------------------------------------
    # 5. Opportunities
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[5/7] Building canonical opportunities...")

    opportunities = _build_opportunities(
        date_enriched,
        reference_date,
    )

    if not isinstance(opportunities, list):
        raise PipelineError(
            "Opportunity builder returned a non-list result."
        )

    # Preserve source fields if a builder implementation returns only a
    # subset of the canonical record.
    by_number = {
        _normalize_application_number(
            item.get("application_number")
        ): item
        for item in date_enriched
    }

    completed_opportunities: list[dict[str, Any]] = []

    for opportunity in opportunities:
        number = _normalize_application_number(
            opportunity.get("application_number")
        )

        source = by_number.get(number, {})

        merged = dict(source)
        merged.update(opportunity)

        completed_opportunities.append(
            merged
        )

    # ------------------------------------------------------------------------
    # 6. Applicant intelligence
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[6/7] Applying applicant identity and enrichment...")

    completed_opportunities = _enrich_applicants(
        completed_opportunities,
        live_enrichment=live_enrichment,
    )

    completed_opportunities = _qualify_leads(
        completed_opportunities
    )

    # ------------------------------------------------------------------------
    # 7. Queue / validation
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[7/7] Validating and sorting production queue...")

    _validate_batch(
        completed_opportunities
    )

    lead_queue = _sort_opportunities(
        completed_opportunities
    )

    supabase_sync = _persist_leads(
        completed_opportunities,
        sync_to_supabase=sync_to_supabase,
    )

    metadata = {
        "pipeline": "PermitSignal",
        "pipeline_version": "1.0",
        "source_pdf": str(pdf_path),
        "reference_date": reference_date.isoformat(),
        "live_enrichment": bool(live_enrichment),
        "characters_extracted": len(text),
        "applications_detected": len(applications),
        "opportunities_built": len(completed_opportunities),
        "future_opportunities": future_count,
        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "supabase_sync": supabase_sync,
    }

    result = {
        "metadata": metadata,
        "applications": applications,
        "opportunities": completed_opportunities,
        "lead_queue": lead_queue,
    }

    if verbose:
        print()
        print("=" * 90)
        print("PRODUCTION PIPELINE COMPLETE")
        print("=" * 90)
        print(
            f"Applications:         {len(applications)}"
        )
        print(
            f"Opportunities:        {len(completed_opportunities)}"
        )
        print(
            f"Future opportunities: {future_count}"
        )
        print(
            f"Supabase sync:        {supabase_sync.get('status')}"
        )

        print()
        print("LEAD QUEUE")

        for index, item in enumerate(
            lead_queue,
            start=1,
        ):
            print(
                f"{index:02d}. "
                f"{item.get('priority', 'UNKNOWN'):9} | "
                f"{item.get('application_number')} | "
                f"{item.get('applicant_name')} | "
                f"{item.get('application_type')} | "
                f"SCORE={item.get('priority_score')} | "
                f"DATE={item.get('next_project_date')}"
            )

    return result


# ============================================================================
# SAVE
# ============================================================================

def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    return str(value)


def save_pipeline_result(
    result: dict[str, Any],
    output_path: Path | str = DEFAULT_OUTPUT,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        ),
        encoding="utf-8",
    )

    return path


def run_and_save(
    pdf_path: Path | str = DEFAULT_PDF,
    reference_date: Optional[date] = None,
    live_enrichment: bool = False,
    sync_to_supabase: bool = False,
    output_path: Path | str = DEFAULT_OUTPUT,
    verbose: bool = True,
) -> dict[str, Any]:
    result = run_pipeline(
        pdf_path=pdf_path,
        reference_date=reference_date,
        live_enrichment=live_enrichment,
        sync_to_supabase=sync_to_supabase,
        verbose=verbose,
    )

    saved = save_pipeline_result(
        result,
        output_path,
    )

    if verbose:
        print()
        print(
            f"Saved result: {saved}"
        )

    result["metadata"]["output_path"] = str(
        saved
    )

    return result


# ============================================================================
# CLI
# ============================================================================

def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Date must be YYYY-MM-DD"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PermitSignal production pipeline."
    )

    parser.add_argument(
        "--pdf",
        default=str(DEFAULT_PDF),
        help="Government PDF path.",
    )

    parser.add_argument(
        "--reference-date",
        type=_parse_date,
        default=date.today(),
        help="Reference date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="JSON output path.",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable public-web applicant enrichment.",
    )

    parser.add_argument(
        "--sync-supabase",
        action="store_true",
        help=(
            "Additionally upsert canonical lead records into Supabase. "
            "Requires SUPABASE_URL and SUPABASE_KEY. The JSON output is "
            "always produced regardless of this flag."
        ),
    )

    args = parser.parse_args()

    run_and_save(
        pdf_path=args.pdf,
        reference_date=args.reference_date,
        live_enrichment=args.live,
        sync_to_supabase=args.sync_supabase,
        output_path=args.output,
        verbose=True,
    )


if __name__ == "__main__":
    main()
