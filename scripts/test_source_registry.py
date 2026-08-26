"""
PermitSignal Source Registry and Multi-Source Ingestion Tests

Tests the source_registry, source_adapters, and discovery_orchestrator
multi-source functionality.  Uses JSON fallback mode (no Supabase required).
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.services import source_registry
from backend.app.services.source_adapters.base import BaseAdapter, DocumentRecord
from backend.app.services.source_adapters import get_adapter, ADAPTER_REGISTRY
from backend.app.services.source_adapters.pdf_adapter import PdfAdapter
from backend.app.services.source_adapters.html_adapter import HtmlPlaywrightAdapter


# =========================================================================
# Helpers
# =========================================================================

SAMPLE_SOURCE = {
    "source_key": "test_source_001",
    "state": "Oklahoma",
    "city": "Tulsa",
    "county": "Tulsa County",
    "agency": "Tulsa County Planning Commission",
    "source_url": "https://www.tulsacounty.org/planning/agenda",
    "source_type": "html_agenda",
    "platform": None,
    "adapter": "html_playwright",
    "active": True,
    "config": {
        "categories": ["https://www.tulsacounty.org/planning/agenda"],
        "link_patterns": ["/agenda/", "/minutes/"],
    },
}

SAMPLE_PDF_SOURCE = {
    "source_key": "test_pdf_001",
    "state": "Colorado",
    "city": "Denver",
    "county": "Denver County",
    "agency": "Denver Planning Board",
    "source_url": "https://denvergov.org/planning/current_agenda.pdf",
    "source_type": "pdf_direct",
    "platform": None,
    "adapter": "pdf",
    "active": True,
    "config": {},
}


def _patch_fallback():
    """Temporarily redirect the JSON fallback to a temp file and force fallback mode."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    )
    tmp.close()
    original = source_registry.FALLBACK_PATH
    source_registry.FALLBACK_PATH = Path(tmp.name)
    # Force fallback mode by saving and clearing env vars
    saved_url = os.environ.pop("SUPABASE_URL", None)
    saved_key = os.environ.pop("SUPABASE_KEY", None)
    return original, Path(tmp.name), saved_url, saved_key


def _cleanup(original, tmp_path, saved_url=None, saved_key=None):
    source_registry.FALLBACK_PATH = original
    if tmp_path.exists():
        tmp_path.unlink()
    # Restore env vars
    if saved_url is not None:
        os.environ["SUPABASE_URL"] = saved_url
    if saved_key is not None:
        os.environ["SUPABASE_KEY"] = saved_key


# =========================================================================
# Source Registry Tests
# =========================================================================

def test_source_registry_upsert_and_get():
    """Upsert a source, retrieve it, verify all fields."""
    print("Test: source_registry upsert and get")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        result = source_registry.upsert_source(SAMPLE_SOURCE)
        assert result["source_key"] == "test_source_001"
        assert result["state"] == "Oklahoma"
        assert result["agency"] == "Tulsa County Planning Commission"
        assert result["active"] is True

        fetched = source_registry.get_source("test_source_001")
        assert fetched is not None
        assert fetched["source_key"] == "test_source_001"
        assert fetched["city"] == "Tulsa"
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_list():
    """List sources, filter by active and state."""
    print("Test: source_registry list")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        source_registry.upsert_source(SAMPLE_SOURCE)
        source_registry.upsert_source(SAMPLE_PDF_SOURCE)

        all_sources = source_registry.list_sources()
        assert len(all_sources) == 2

        active_only = source_registry.list_sources(active_only=True)
        assert len(active_only) == 2

        oklahoma = source_registry.list_sources(state="Oklahoma")
        assert len(oklahoma) == 1
        assert oklahoma[0]["source_key"] == "test_source_001"
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_deactivate():
    """Deactivate a source."""
    print("Test: source_registry deactivate")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        source_registry.upsert_source(SAMPLE_SOURCE)
        found = source_registry.deactivate_source("test_source_001")
        assert found is True

        fetched = source_registry.get_source("test_source_001")
        assert fetched["active"] is False

        active = source_registry.list_sources(active_only=True)
        assert len(active) == 0
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_upsert_requires_key():
    """Upsert without source_key raises ValueError."""
    print("Test: source_registry upsert requires source_key")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        try:
            source_registry.upsert_source({"state": "Utah"})
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_get_nonexistent():
    """Get a source that doesn't exist returns None."""
    print("Test: source_registry get nonexistent")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        result = source_registry.get_source("nonexistent")
        assert result is None
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_ingestion_metadata():
    """Update ingestion metadata."""
    print("Test: source_registry ingestion metadata")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        source_registry.upsert_source(SAMPLE_SOURCE)
        source_registry.update_ingestion_metadata(
            "test_source_001",
            {"documents_discovered": 5, "documents_ingested": 3},
        )
        fetched = source_registry.get_source("test_source_001")
        assert fetched["ingestion_metadata"]["documents_discovered"] == 5
        assert fetched["last_ingested_at"] is not None
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_source_registry_backward_compat_provo():
    """The Provo source should be retrievable from the JSON fallback."""
    print("Test: source_registry backward compat Provo")
    original, tmp, saved_url, saved_key = _patch_fallback()
    try:
        provo = {
            "source_key": "provo_planning",
            "state": "Utah",
            "city": "Provo",
            "county": "Utah County",
            "agency": "Provo Planning Commission",
            "source_url": "https://www.provo.gov/AgendaCenter/Planning-Commission-2",
            "source_type": "html_agenda",
            "platform": "civicplus",
            "adapter": "html_playwright",
            "active": True,
            "config": {
                "categories": [
                    "https://www.provo.gov/AgendaCenter/Planning-Commission-2",
                ],
                "rss_url": "https://www.provo.gov/RSSFeed.aspx?ModID=65&CID=All-0",
                "link_patterns": [
                    "/AgendaCenter/ViewFile/Agenda/",
                    "/AgendaCenter/PreviousVersions/",
                ],
            },
        }
        source_registry.upsert_source(provo)
        fetched = source_registry.get_source("provo_planning")
        assert fetched is not None
        assert fetched["adapter"] == "html_playwright"
        assert fetched["config"]["rss_url"] is not None
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


# =========================================================================
# Source Adapter Tests
# =========================================================================

def test_adapter_registry():
    """The adapter registry contains pdf and html_playwright."""
    print("Test: adapter registry")
    assert "pdf" in ADAPTER_REGISTRY
    assert "html_playwright" in ADAPTER_REGISTRY
    assert ADAPTER_REGISTRY["pdf"] is PdfAdapter
    assert ADAPTER_REGISTRY["html_playwright"] is HtmlPlaywrightAdapter
    print("  PASS")


def test_get_adapter():
    """get_adapter returns correct instances."""
    print("Test: get_adapter")
    pdf = get_adapter("pdf")
    assert isinstance(pdf, PdfAdapter)

    html = get_adapter("html_playwright")
    assert isinstance(html, HtmlPlaywrightAdapter)

    try:
        get_adapter("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  PASS")


def test_document_record():
    """DocumentRecord dataclass fields."""
    print("Test: DocumentRecord")
    doc = DocumentRecord(
        source_key="test",
        url="https://example.com/agenda.pdf",
        title="Test Agenda",
        document_date="2026-08-12",
        record_type="agenda",
    )
    assert doc.source_key == "test"
    assert doc.url == "https://example.com/agenda.pdf"
    assert doc.title == "Test Agenda"
    assert doc.document_date == "2026-08-12"
    assert doc.record_type == "agenda"
    assert doc.metadata == {}
    print("  PASS")


def test_pdf_adapter_discover_single_url():
    """PdfAdapter discovers a single PDF URL."""
    print("Test: PdfAdapter discover single URL")
    adapter = PdfAdapter()
    source = {
        "source_key": "test_pdf",
        "source_url": "https://example.com/current_agenda.pdf",
        "agency": "Test Agency",
        "config": {},
    }
    records = adapter.discover(source)
    assert len(records) == 1
    assert records[0].url == "https://example.com/current_agenda.pdf"
    assert records[0].source_key == "test_pdf"
    assert records[0].record_type == "pdf_direct"
    print("  PASS")


def test_pdf_adapter_discover_with_links():
    """PdfAdapter discovers PDF links from config."""
    print("Test: PdfAdapter discover with links")
    adapter = PdfAdapter()
    source = {
        "source_key": "test_multi",
        "source_url": "https://example.com/agendas/",
        "agency": "Test Agency",
        "config": {
            "pdf_links": [
                {"url": "agenda_jan.pdf", "title": "January Agenda", "date": "2026-01-15"},
                {"url": "agenda_feb.pdf", "title": "February Agenda"},
            ],
        },
    }
    records = adapter.discover(source)
    assert len(records) == 2
    assert records[0].title == "January Agenda"
    assert records[0].document_date == "2026-01-15"
    assert records[1].title == "February Agenda"
    print("  PASS")


def test_pdf_adapter_is_ingestible():
    """PdfAdapter is_ingestible checks record_type."""
    print("Test: PdfAdapter is_ingestible")
    adapter = PdfAdapter()
    assert adapter.is_ingestible(DocumentRecord("k", "u", record_type="pdf_direct"))
    assert adapter.is_ingestible(DocumentRecord("k", "u", record_type="agenda"))
    assert not adapter.is_ingestible(DocumentRecord("k", "u", record_type="previous_versions"))
    print("  PASS")


def test_html_adapter_is_ingestible():
    """HtmlPlaywrightAdapter is_ingestible checks record_type."""
    print("Test: HtmlPlaywrightAdapter is_ingestible")
    adapter = HtmlPlaywrightAdapter()
    assert adapter.is_ingestible(DocumentRecord("k", "u", record_type="agenda"))
    assert adapter.is_ingestible(DocumentRecord("k", "u", record_type="pdf_direct"))
    assert adapter.is_ingestible(DocumentRecord("k", "u", record_type="minutes"))
    assert not adapter.is_ingestible(DocumentRecord("k", "u", record_type="previous_versions"))
    print("  PASS")


# =========================================================================
# Discovery Orchestrator Multi-Source Tests
# =========================================================================

def test_discover_from_source_no_adapter():
    """discover_from_source returns error for unknown adapter."""
    print("Test: discover_from_source bad adapter")
    from backend.app.services.discovery_orchestrator import discover_from_source
    from backend.app.services import document_registry

    registry = {}
    source = {
        "source_key": "bad_adapter",
        "adapter": "nonexistent_widget",
        "source_url": "https://example.com",
        "config": {},
    }
    result = discover_from_source(source, registry)
    assert result.get("error") is not None
    assert "nonexistent_widget" in result["error"]
    print("  PASS")


def test_discover_from_source_pdf():
    """discover_from_source with PDF adapter discovers documents."""
    print("Test: discover_from_source PDF adapter")
    from backend.app.services.discovery_orchestrator import discover_from_source

    original, tmp, saved_url, saved_key = _patch_fallback()
    registry = {}
    try:
        source = {
            "source_key": "pdf_test",
            "adapter": "pdf",
            "source_url": "https://example.com/agenda.pdf",
            "agency": "Test",
            "source_type": "pdf_direct",
            "config": {},
        }
        result = discover_from_source(source, registry)
        assert result.get("source_key") == "pdf_test"
        assert result.get("adapter") == "pdf"
        assert len(result.get("new_records", [])) == 1
        assert result["new_records"][0]["url"] == "https://example.com/agenda.pdf"
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_discover_from_source_deduplication():
    """Re-running discovery skips already-known documents."""
    print("Test: discover_from_source deduplication")
    from backend.app.services.discovery_orchestrator import discover_from_source

    original, tmp, saved_url, saved_key = _patch_fallback()
    registry = {}
    try:
        source = {
            "source_key": "dedup_test",
            "adapter": "pdf",
            "source_url": "https://example.com/agenda.pdf",
            "agency": "Test",
            "config": {},
        }
        result1 = discover_from_source(source, registry)
        assert len(result1["new_records"]) == 1

        result2 = discover_from_source(source, registry)
        assert len(result2["new_records"]) == 0
        assert len(result2["all_records"]) == 1
    finally:
        _cleanup(original, tmp, saved_url, saved_key)
    print("  PASS")


def test_pipeline_backward_compat():
    """The existing pipeline orchestrator signature is unchanged."""
    print("Test: pipeline backward compatibility")
    import inspect
    from backend.app.services import pipeline_orchestrator

    sig = inspect.signature(pipeline_orchestrator.run_pipeline)
    params = list(sig.parameters.keys())
    assert "pdf_path" in params
    assert "reference_date" in params
    assert "sync_to_supabase" in params
    print("  PASS")


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 70)
    print("PERMITSIGNAL SOURCE REGISTRY & MULTI-SOURCE INGESTION TEST")
    print("=" * 70)
    print()

    test_source_registry_upsert_and_get()
    test_source_registry_list()
    test_source_registry_deactivate()
    test_source_registry_upsert_requires_key()
    test_source_registry_get_nonexistent()
    test_source_registry_ingestion_metadata()
    test_source_registry_backward_compat_provo()
    print()
    test_adapter_registry()
    test_get_adapter()
    test_document_record()
    test_pdf_adapter_discover_single_url()
    test_pdf_adapter_discover_with_links()
    test_pdf_adapter_is_ingestible()
    test_html_adapter_is_ingestible()
    print()
    test_discover_from_source_no_adapter()
    test_discover_from_source_pdf()
    test_discover_from_source_deduplication()
    test_pipeline_backward_compat()

    print()
    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
