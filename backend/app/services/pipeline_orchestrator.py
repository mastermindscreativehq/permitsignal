from __future__ import annotations

"""
PermitSignal production pipeline orchestrator.

Location:
    backend/app/services/pipeline_orchestrator.py

Pipeline:
    PDF -> application extraction -> friction analysis
        -> future project dates -> opportunity builder
        -> applicant identity/enrichment -> approval-action intelligence
        -> lead qualification -> commercial lead intelligence
        -> sorted production queue

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
APPROVAL_INTELLIGENCE_MODULE = "backend.app.services.approval_action_intelligence"
ECONOMIC_INTELLIGENCE_MODULE = "backend.app.services.economic_intelligence"
COMMERCIAL_INTELLIGENCE_MODULE = "backend.app.services.commercial_lead_intelligence"
OUTREACH_INTELLIGENCE_MODULE = "backend.app.services.outreach_intelligence"
APPROVAL_INTELLIGENCE_ENGINE_MODULE = "backend.app.services.approval_intelligence_engine"
ACTION_STAGE_INTELLIGENCE_MODULE = "backend.app.services.approval_stage_intelligence"
PRICING_ENGINE_MODULE = "backend.app.services.pricing_engine"
ADDRESS_INTELLIGENCE_MODULE = "backend.app.services.address_intelligence"
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
# STAFF-REPORT IDENTITY (Phase 10)
# ============================================================================

def _apply_staff_report_identity(
    applications: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """
    Additive owner/applicant-of-record/property-party evidence from each
    application's own staff-report routing table elsewhere in the full
    packet (see application_extractor.extract_staff_report_identity()).
    Only fills a field that is currently None/empty on the agenda-section-
    derived application dict -- never overwrites an existing value.
    "parties" is merged by concatenation (deduplicated by name+role)
    rather than precedence, since the agenda section and the staff report
    can each legitimately name a different labeled party.
    """
    module = _import_service(APPLICATION_EXTRACTOR_MODULE)

    fn = getattr(module, "extract_staff_report_identity", None)

    if not callable(fn):
        return applications

    results: list[dict[str, Any]] = []

    for application in applications:
        number = application.get("application_number")

        try:
            staff_report = fn(text, number) if number else {}
        except Exception:
            staff_report = {}

        merged = dict(application)

        for key, value in (staff_report or {}).items():
            if key == "parties":
                combined = list(application.get("parties") or [])
                seen = {
                    (party.get("party_name"), party.get("party_role"))
                    for party in combined
                    if isinstance(party, dict)
                }

                for party in value or []:
                    if not isinstance(party, dict):
                        continue

                    party_key = (party.get("party_name"), party.get("party_role"))

                    if party_key in seen:
                        continue

                    seen.add(party_key)
                    combined.append(party)

                merged["parties"] = combined
                continue

            if merged.get(key) is None and value is not None:
                merged[key] = value

        results.append(merged)

    return results


# ============================================================================
# STAFF-REPORT FULL ADDRESS ENRICHMENT
# ============================================================================

_ADDRESS_COMPLETENESS_RANK = {
    None: 0,
    "free_text": 1,
    "area_description": 2,
    "street_only": 2,
    "street_with_unit": 3,
    "street_city_state": 4,
    "full_postal": 5,
}

# Fields that describe one atomic address finding: they are upgraded
# together (only to a strictly more complete form) or left alone --
# never mixed between two different evidence sources.
_ADDRESS_ATOMIC_FIELDS = (
    "property_address_full",
    "property_address_components",
    "property_address_completeness",
    "property_address_source",
    "property_address_confidence",
    "property_address_evidence",
)


def _apply_staff_report_addresses(
    applications: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """
    Upgrade each application's property address with fuller SAME-street
    evidence (city/state/ZIP/unit) and labeled parcel IDs from the
    application's own staff-report material elsewhere in the packet
    (see application_extractor.extract_staff_report_address()).

    Purely additive/upgrade-only:
      - parcel_number fills only when currently None;
      - the property_address_* field group is replaced only by a
        STRICTLY more complete form of the same street (ranked by
        _ADDRESS_COMPLETENESS_RANK), never by a weaker or unrelated one;
      - components merge per-key, never overwriting a present value.
    """
    module = _import_service(APPLICATION_EXTRACTOR_MODULE)

    fn = getattr(module, "extract_staff_report_address", None)

    if not callable(fn):
        return applications

    results: list[dict[str, Any]] = []

    for application in applications:

        try:
            enrichment = fn(text, application) or {}
        except Exception:
            enrichment = {}

        merged = dict(application)

        # Labeled parcel evidence fills only a missing parcel.
        if (
            merged.get("parcel_number") is None
            and enrichment.get("parcel_number")
        ):
            merged["parcel_number"] = enrichment["parcel_number"]

        current_rank = _ADDRESS_COMPLETENESS_RANK.get(
            application.get("property_address_completeness"),
            0,
        ) or (2 if application.get("project_address") else 0)

        upgrade_rank = _ADDRESS_COMPLETENESS_RANK.get(
            enrichment.get("property_address_completeness"),
            0,
        )

        if upgrade_rank > current_rank:

            merged_components = dict(
                application.get("property_address_components") or {}
            )

            for component_key, component_value in (
                enrichment.get("property_address_components") or {}
            ).items():
                if component_value is not None:
                    merged_components[component_key] = component_value

            for field_name in _ADDRESS_ATOMIC_FIELDS:
                if field_name == "property_address_components":
                    merged[field_name] = merged_components
                elif enrichment.get(field_name) is not None:
                    merged[field_name] = enrichment[field_name]

        results.append(merged)

    return results


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

                    # Owner/person enrichment (Phase 2): a distinct
                    # real-world person (owner/principal/executive/
                    # partner) discovered via public evidence is
                    # ADDITIVE to any party already extracted directly
                    # from the government document (application_extractor.
                    # extract_parties()) -- appended, never replacing the
                    # document-sourced list _merge_preserving_left() would
                    # otherwise overwrite it with.
                    discovered_parties = enrichment.get(
                        "discovered_parties"
                    )

                    if discovered_parties:
                        item["parties"] = list(
                            item.get("parties") or []
                        ) + list(discovered_parties)

                    item.pop("discovered_parties", None)

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
# APPROVAL-ACTION INTELLIGENCE (Phase 3)
# ============================================================================

def _apply_approval_intelligence(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attach a conservative, evidence-first approval_status/approval_action
    recommendation to each completed opportunity, using only fields already
    computed by friction analysis, project-date extraction, and the current
    agenda status -- never new text extraction. Purely additive: every
    existing field (including owner/person enrichment from stage 6 above)
    is preserved unchanged; only the approval_* fields are added.
    """
    module = _import_service(APPROVAL_INTELLIGENCE_MODULE)

    batch_fn = _first_callable(
        module,
        "apply_approval_intelligence",
    )

    if batch_fn is not None:
        try:
            result = batch_fn(opportunities)

            if isinstance(result, list):
                return result
        except TypeError:
            pass

    single_fn = _first_callable(
        module,
        "build_approval_action",
    )

    if single_fn is None:
        raise PipelineError(
            "approval_action_intelligence does not expose "
            "apply_approval_intelligence() or build_approval_action()."
        )

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        approval = single_fn(item)

        if isinstance(approval, dict):
            item.update(approval)

        results.append(item)

    return results


# ============================================================================
# ECONOMIC INTELLIGENCE (Phase 9)
# ============================================================================

def _apply_economic_intelligence(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attach project-value/public-spend fields (project_scale_*,
    estimated_value_*, public_funding_*, public_spend_*) to each
    already-approval-enriched opportunity. Purely additive and reads only
    application_type/description/applicant_name/company_name -- every
    existing field is preserved unchanged.
    """
    module = _import_service(ECONOMIC_INTELLIGENCE_MODULE)

    batch_fn = _first_callable(
        module,
        "apply_economic_intelligence",
    )

    if batch_fn is not None:
        try:
            result = batch_fn(opportunities)

            if isinstance(result, list):
                return result
        except TypeError:
            pass

    single_fn = _first_callable(
        module,
        "build_economic_intelligence",
    )

    if single_fn is None:
        raise PipelineError(
            "economic_intelligence does not expose "
            "apply_economic_intelligence() or build_economic_intelligence()."
        )

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        economic = single_fn(item)

        if isinstance(economic, dict):
            item.update(economic)

        results.append(item)

    return results


# ============================================================================
# COMMERCIAL LEAD INTELLIGENCE (Phase 6)
# ============================================================================

def _apply_commercial_intelligence(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attach commercial-readiness/contactability/recommended-action fields
    (contactability_level, commercial_readiness, recommended_commercial_
    action, commercial_action_reason) to each already-qualified
    opportunity. Purely additive and must run after _qualify_leads(): it
    re-labels lead_status/is_contactable rather than recomputing them.
    Every existing field is preserved unchanged.
    """
    module = _import_service(COMMERCIAL_INTELLIGENCE_MODULE)

    batch_fn = _first_callable(
        module,
        "apply_commercial_intelligence",
    )

    if batch_fn is not None:
        try:
            result = batch_fn(opportunities)

            if isinstance(result, list):
                return result
        except TypeError:
            pass

    single_fn = _first_callable(
        module,
        "build_commercial_intelligence",
    )

    if single_fn is None:
        raise PipelineError(
            "commercial_lead_intelligence does not expose "
            "apply_commercial_intelligence() or build_commercial_intelligence()."
        )

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        commercial = single_fn(item)

        if isinstance(commercial, dict):
            item.update(commercial)

        results.append(item)

    return results


# ============================================================================
# OUTREACH & MONETIZATION INTELLIGENCE (Phase 8)
# ============================================================================

def _load_previous_leads_by_number(
    sync_to_supabase: bool,
    output_path: Path,
) -> dict[str, dict[str, Any]]:
    """
    Load each application_number's prior persisted lead record, so
    outreach_intelligence can carry forward outreach_status/
    outreach_events/follow_up_required/last_outreach_at across pipeline
    runs (see outreach_intelligence.advance_outreach_status()). Every
    other field is still fully recomputed from scratch every run -- this
    lookup exists solely to make the Phase 8 lifecycle fields
    idempotent/non-regressive, not to change any other field's behavior.

    Best-effort only: this must never fail or slow down the pipeline. The
    pipeline's own previous JSON artifact (if present at output_path) is
    always consulted first; Supabase (when sync_to_supabase=True and
    configured) additionally overlays any fresher state, mirroring the
    Supabase-primary/JSON-fallback convention used by GET /leads.
    """
    previous: dict[str, dict[str, Any]] = {}

    try:
        if output_path.exists():
            existing = json.loads(output_path.read_text(encoding="utf-8"))

            for lead in existing.get("opportunities", []) or []:
                number = _normalize_application_number(lead.get("application_number"))

                if number:
                    previous[number] = lead
    except Exception:
        pass

    if sync_to_supabase:
        try:
            module = _import_service(LEAD_REPOSITORY_MODULE)
            is_configured_fn = getattr(module, "is_configured", None)

            if callable(is_configured_fn) and is_configured_fn():
                for lead in module.fetch_leads():
                    number = _normalize_application_number(lead.get("application_number"))

                    if number:
                        previous[number] = lead
        except Exception:
            pass

    return previous


def _apply_outreach_intelligence(
    opportunities: list[dict[str, Any]],
    previous_by_number: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attach outreach lifecycle/contact-target/message-draft fields
    (outreach_status, outreach_qualification_status, outreach_channel,
    outreach_contact_type, outreach_contact_reason,
    outreach_message_subject/body, follow_up_required/reason,
    last_outreach_at, outreach_events) to each already-qualified
    opportunity. Purely additive and must run after
    _apply_commercial_intelligence(): it re-labels commercial_readiness
    rather than recomputing it. Every existing field is preserved
    unchanged.
    """
    module = _import_service(OUTREACH_INTELLIGENCE_MODULE)

    batch_fn = _first_callable(
        module,
        "apply_outreach_intelligence",
    )

    if batch_fn is not None:
        try:
            result = batch_fn(opportunities, previous_by_number)

            if isinstance(result, list):
                return result
        except TypeError:
            pass

    single_fn = _first_callable(
        module,
        "build_outreach_intelligence",
    )

    if single_fn is None:
        raise PipelineError(
            "outreach_intelligence does not expose "
            "apply_outreach_intelligence() or build_outreach_intelligence()."
        )

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)
        number = _normalize_application_number(item.get("application_number"))
        previous = previous_by_number.get(number) if number else None
        outreach = single_fn(item, previous)

        if isinstance(outreach, dict):
            item.update(outreach)

        results.append(item)

    return results


# ============================================================================
# APPROVAL INTELLIGENCE ENGINE (Deep Intelligence)
# ============================================================================

def _apply_approval_intelligence_engine(
    opportunities: list[dict[str, Any]],
    reference_date: date,
) -> list[dict[str, Any]]:
    """
    Attach the comprehensive approval intelligence report to each
    opportunity. This is the PRIMARY APPROVAL INTELLIGENCE BRAIN --
    it produces the full intelligence package (evidence registry,
    denial history, blockers, requirements, actions, decision path,
    stakeholders, service recommendation, client message, internal
    strategy, pricing inputs) for each project.

    Purely additive: every existing field is preserved unchanged;
    only the approval_intelligence_* keys are added/overwritten.
    """
    module = _import_service(APPROVAL_INTELLIGENCE_ENGINE_MODULE)

    engine_fn = _first_callable(
        module,
        "build_approval_intelligence",
    )

    if engine_fn is None:
        return opportunities

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)

        try:
            intelligence = engine_fn(item, reference_date=reference_date)

            if isinstance(intelligence, dict):
                # Flatten the intelligence report into the opportunity record
                # so it's accessible from the same flat dict the rest of the
                # pipeline uses.
                item["approval_intelligence"] = intelligence

                # Also surface key fields at the top level for backward compat
                if intelligence.get("approval_status"):
                    item["deep_approval_status"] = intelligence["approval_status"]
                if intelligence.get("approval_risk"):
                    item["deep_approval_risk"] = intelligence["approval_risk"]
                if intelligence.get("approval_readiness"):
                    item["deep_approval_readiness"] = intelligence["approval_readiness"]

        except Exception as exc:
            item["approval_intelligence"] = {
                "status": "error",
                "error": str(exc),
            }

        results.append(item)

    return results


def _apply_action_intelligence(
    opportunities: list[dict[str, Any]],
    reference_date: date,
) -> list[dict[str, Any]]:
    """
    Attach the frozen Action Intelligence package (contract v1.0) to each
    opportunity: requested_action, conditions, decision_stage, blockers
    and mapped actions -- all evidence-first, computed only from data
    already present on the record.

    Purely additive: only the action_intelligence key is added; every
    existing field is preserved unchanged.
    """
    module = _import_service(ACTION_STAGE_INTELLIGENCE_MODULE)

    requested_fn = _first_callable(module, "build_requested_action")
    conditions_fn = _first_callable(module, "build_conditions")
    stage_fn = _first_callable(module, "build_decision_stage")
    blockers_fn = _first_callable(module, "map_blockers_and_actions")

    if None in (requested_fn, conditions_fn, stage_fn, blockers_fn):
        return opportunities

    contract_version = getattr(module, "CONTRACT_VERSION", "1.0")

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)

        try:
            package = {
                "contract_version": contract_version,
                "requested_action": requested_fn(item),
                "conditions": conditions_fn(item),
                "decision_stage": stage_fn(
                    item, reference_date=reference_date.isoformat()
                ),
                "blockers_and_actions": blockers_fn(
                    item, reference_date=reference_date.isoformat()
                ),
            }
            item["action_intelligence"] = package
        except Exception as exc:
            item["action_intelligence"] = {
                "status": "error",
                "error": str(exc),
            }

        results.append(item)

    return results


# ============================================================================
# ADDRESS INTELLIGENCE
# ============================================================================

def _apply_address_intelligence(
    opportunities: list[dict[str, Any]],
    previous_leads: dict[str, dict[str, Any]],
    force: bool = False,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """
    Enrich all opportunities with geocoded location intelligence.

    This is ADDITIVE ONLY: government-record addresses are never
    modified.  External provider failures are non-fatal.

    Inserted after staff-report address upgrades and before friction
    analysis so that downstream stages can benefit from enriched
    coordinates.
    """
    if verbose:
        print()
        print("[2c/10] Enriching address intelligence...")

    module = _import_service(ADDRESS_INTELLIGENCE_MODULE)

    enrich_all_fn = getattr(module, "enrich_all_addresses", None)

    if enrich_all_fn is None:
        if verbose:
            print("Address intelligence service not available — skipping.")
        return opportunities

    try:
        result = enrich_all_fn(
            opportunities,
            previous_leads=previous_leads,
            force=force,
            verbose=verbose,
        )

        if not isinstance(result, list):
            return opportunities

        return result

    except Exception as exc:
        if verbose:
            print(f"Address intelligence failed (non-fatal): {exc}")
        return opportunities


# ============================================================================
# PRICING ENGINE
# ============================================================================

def _apply_pricing(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Apply deterministic pricing to each opportunity that has
    pricing_inputs from the approval intelligence engine. Never
    invents prices -- only computes them from complexity signals.
    """
    module = _import_service(PRICING_ENGINE_MODULE)

    pricing_fn = _first_callable(
        module,
        "calculate_pricing",
    )

    if pricing_fn is None:
        return opportunities

    def _map_pricing_inputs(raw: dict) -> dict:
        """Map approval_intelligence pricing_inputs to pricing_engine format."""
        return {
            "service_level": raw.get("service_tier") or raw.get("service_level", "MONITORING"),
            "friction_score": raw.get("friction_score", 0),
            "has_denial": raw.get("has_denial_history", False) or raw.get("has_denial", False),
            "has_hearing": raw.get("has_future_event", False),
            "stakeholder_complexity": raw.get("complexity_tier", "medium"),
            "documentation_complexity": raw.get("complexity_tier", "medium"),
        }

    results: list[dict[str, Any]] = []

    for opportunity in opportunities:
        item = dict(opportunity)

        raw_inputs = item.get("pricing_inputs") or (
            item.get("approval_intelligence", {}).get("pricing_inputs")
        )

        if raw_inputs and isinstance(raw_inputs, dict):
            try:
                mapped = _map_pricing_inputs(raw_inputs)
                pricing = pricing_fn(mapped)

                if isinstance(pricing, dict):
                    item["pricing"] = pricing
            except Exception:
                item["pricing"] = {"status": "error"}

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

    # application_type is intentionally NOT validated as required: real
    # government packets legitimately omit a recognizable type phrase for
    # some agenda items (DEVELOPMENT_RULES.md Part 17 already documents
    # retaining it "when available" as the standing contract, not "always
    # present"). Every downstream stage already tolerates a null
    # application_type -- failing the entire document's batch over one
    # opportunity's unrecognized type phrase discarded otherwise-valid
    # opportunities in real Provo packets.

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
    output_path: Path | str = DEFAULT_OUTPUT,
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

    output_path identifies where this run's previous JSON artifact (if
    any) is read from to carry forward Phase 8 outreach-lifecycle state
    (see _load_previous_leads_by_number()) -- it does not, by itself,
    cause this function to write anything; saving is run_and_save()'s
    responsibility.
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
        print("[1/10] Reading government packet...")

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
        print("[2/10] Extracting applications...")

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

    applications = _apply_staff_report_identity(
        applications,
        text,
    )

    applications = _apply_staff_report_addresses(
        applications,
        text,
    )

    if verbose:
        print(
            f"Applications detected: {len(applications)}"
        )

    # Load previous leads early so address intelligence and outreach
    # intelligence both have access to cached state from prior runs.
    previous_leads_by_number = _load_previous_leads_by_number(
        sync_to_supabase,
        Path(output_path),
    )

    # ----------------------------------------------------------------
    # 2c. Address Intelligence
    # ----------------------------------------------------------------

    applications = _apply_address_intelligence(
        applications,
        previous_leads_by_number,
        verbose=verbose,
    )

    # ------------------------------------------------------------------------
    # 3. Friction
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[3/10] Analyzing historical friction...")

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
        print("[4/10] Extracting future project dates...")

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
        print("[5/10] Building canonical opportunities...")

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
        print("[6/10] Applying applicant identity and enrichment...")

    completed_opportunities = _enrich_applicants(
        completed_opportunities,
        live_enrichment=live_enrichment,
    )

    completed_opportunities = _apply_approval_intelligence(
        completed_opportunities
    )

    completed_opportunities = _apply_economic_intelligence(
        completed_opportunities
    )

    completed_opportunities = _qualify_leads(
        completed_opportunities
    )

    completed_opportunities = _apply_commercial_intelligence(
        completed_opportunities
    )

    completed_opportunities = _apply_outreach_intelligence(
        completed_opportunities,
        previous_leads_by_number,
    )

    # ------------------------------------------------------------------------
    # 8. Deep approval intelligence
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[8/10] Running deep approval intelligence engine...")

    completed_opportunities = _apply_approval_intelligence_engine(
        completed_opportunities,
        reference_date,
    )

    if verbose:
        print("[8/10] Attaching Action Intelligence package...")

    completed_opportunities = _apply_action_intelligence(
        completed_opportunities,
        reference_date,
    )

    # ------------------------------------------------------------------------
    # 9. Pricing
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[9/10] Computing deterministic pricing...")

    completed_opportunities = _apply_pricing(
        completed_opportunities,
    )

    # ------------------------------------------------------------------------
    # 10. Queue / validation
    # ------------------------------------------------------------------------

    if verbose:
        print()
        print("[10/10] Validating and sorting production queue...")

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
        "pipeline_version": "2.0",
        "source_pdf": str(pdf_path),
        "reference_date": reference_date.isoformat(),
        "live_enrichment": bool(live_enrichment),
        "characters_extracted": len(text),
        "applications_detected": len(applications),
        "opportunities_built": len(completed_opportunities),
        "future_opportunities": future_count,
        "intelligence_reports": sum(
            1
            for item in completed_opportunities
            if item.get("approval_intelligence")
        ),
        "pricing_computed": sum(
            1
            for item in completed_opportunities
            if item.get("pricing")
        ),
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
        output_path=output_path,
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
