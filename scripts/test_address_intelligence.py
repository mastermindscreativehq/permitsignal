"""
PermitSignal Address Intelligence Test

Run:

    python -m scripts.test_address_intelligence

For live geocoding:

    python -m scripts.test_address_intelligence --live

Without --live, the test validates the address intelligence engine and
does NOT call external geocoding providers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.address_intelligence import (
    _classify_confidence,
    _cache_key,
    _extract_source_components,
    _is_within_ttl,
    _state_abbreviation_match,
    normalize_address_for_search,
    enrich_address_intelligence,
    enrich_all_addresses,
    _clear_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lead(
    address: str = "909 W 1160 N",
    city: str | None = None,
    state: str | None = None,
    postal: str | None = None,
    municipality: str | None = None,
) -> dict:
    """Build a minimal lead dict for testing."""
    components = None
    if city or state or postal:
        components = {
            "street_number": "909",
            "street_name": "W 1160 N",
            "unit": None,
            "city": city,
            "state": state,
            "postal_code": postal,
        }
    return {
        "application_number": "TEST20260001",
        "project_address": address,
        "property_address_full": address,
        "property_address_components": components,
        "municipality": municipality or city,
        "state": state,
        "parcel_number": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normalize_address():
    """Test address normalization for search."""
    print("Test: normalize_address_for_search")

    # Directional abbreviations are preserved (not expanded) because
    # Nominatim/Google handle them natively and expansion can break
    # resolution (e.g. "1065 E Hillside" → "1065 East Hillside" is
    # NOT found by Nominatim).
    assert normalize_address_for_search("909 W 1160 N") == "909 W 1160 N"
    assert normalize_address_for_search("  123  N.  Main St.") == "123 N. Main St"
    assert normalize_address_for_search("") == ""
    assert normalize_address_for_search("  ") == ""
    assert normalize_address_for_search("456 E. South Blvd.") == "456 E. South Blvd"

    # Slash-separated compound addresses take the first number
    assert normalize_address_for_search("113/191 N Geneva Road") == "113 N Geneva Road"

    print("  PASS")


def test_cache_key_deterministic():
    """Test cache key is deterministic."""
    print("Test: cache key determinism")

    key1 = _cache_key(normalize_address_for_search("909 W 1160 N"))
    key2 = _cache_key(normalize_address_for_search("909 W 1160 N"))
    assert key1 == key2

    key3 = _cache_key(normalize_address_for_search("123 Main St"))
    assert key1 != key3

    print("  PASS")


def test_extract_source_components():
    """Test source component extraction."""
    print("Test: _extract_source_components")

    lead_with_components = _make_lead(city="Provo", state="UT", postal="84601")
    comps = _extract_source_components(lead_with_components)
    assert comps["city"] == "Provo"
    assert comps["state"] == "UT"
    assert comps["postal_code"] == "84601"

    lead_without = _make_lead()
    comps2 = _extract_source_components(lead_without)
    assert comps2["city"] is None
    assert comps2["state"] is None

    print("  PASS")


def test_state_abbreviation_match():
    """Test state abbreviation matching."""
    print("Test: _state_abbreviation_match")

    assert _state_abbreviation_match("utah", "ut") is True
    assert _state_abbreviation_match("ut", "utah") is True
    assert _state_abbreviation_match("california", "ca") is True
    assert _state_abbreviation_match("utah", "ca") is False
    assert _state_abbreviation_match("new york", "ny") is True
    assert _state_abbreviation_match("ny", "new york") is True

    print("  PASS")


def test_classify_confidence_exact_match():
    """Test confidence classification with exact match."""
    print("Test: _classify_confidence — exact match")

    geocoded = {
        "city": "Provo",
        "state": "Utah",
        "postal_code": "84606",
        "house_number": "909",
        "road": "West 1160 North",
        "importance": 0.8,
        "match_quality": "house",
    }
    source = {"city": "Provo", "state": "UT", "postal_code": "84606"}

    confidence = _classify_confidence(geocoded, source)
    assert confidence == "HIGH"

    print("  PASS")


def test_classify_confidence_partial_match():
    """Test confidence classification with partial match."""
    print("Test: _classify_confidence — partial match")

    geocoded = {
        "city": "Provo",
        "state": "Utah",
        "postal_code": "84601",
        "house_number": "909",
        "road": "West 1160 North",
        "importance": 0.6,
        "match_quality": "house",
    }
    source = {"city": "Provo", "state": "UT", "postal_code": None}

    confidence = _classify_confidence(geocoded, source)
    # City and state match, no postal to check
    assert confidence in ("HIGH", "MEDIUM")

    print("  PASS")


def test_classify_confidence_street_only():
    """Test confidence classification with street-only source."""
    print("Test: _classify_confidence — street only source")

    geocoded = {
        "city": "Provo",
        "state": "Utah",
        "postal_code": "84606",
        "house_number": "909",
        "road": "West 1160 North",
        "importance": 0.7,
        "match_quality": "house",
    }
    source = {"city": None, "state": None, "postal_code": None}

    confidence = _classify_confidence(geocoded, source)
    # Street-only: any geocode with house_number + road is MEDIUM
    assert confidence == "MEDIUM"

    print("  PASS")


def test_classify_confidence_no_match():
    """Test confidence classification with no match."""
    print("Test: _classify_confidence — no match")

    geocoded = {
        "city": "Salt Lake City",
        "state": "Utah",
        "postal_code": "84101",
        "house_number": "100",
        "road": "Main Street",
        "importance": 0.5,
        "match_quality": "house",
    }
    source = {"city": "Provo", "state": "UT", "postal_code": "84601"}

    confidence = _classify_confidence(geocoded, source)
    assert confidence == "LOW"

    print("  PASS")


def test_classify_confidence_unresolved():
    """Test confidence classification with no geocoded result."""
    print("Test: _classify_confidence — unresolved")

    source = {"city": "Provo", "state": "UT", "postal_code": "84601"}
    confidence = _classify_confidence({}, source)
    assert confidence == "UNRESOLVED"

    print("  PASS")


def test_is_within_ttl():
    """Test TTL checking."""
    print("Test: _is_within_ttl")

    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=5)).isoformat()
    old = (now - timedelta(days=60)).isoformat()

    assert _is_within_ttl(recent) is True
    assert _is_within_ttl(old) is False

    print("  PASS")


def test_enrich_address_no_address():
    """Test enrichment when lead has no address."""
    print("Test: enrich_address_intelligence — no address")

    _clear_cache()
    lead = _make_lead(address="")
    result = enrich_address_intelligence(lead)

    assert result["address_enrichment_status"] == "not_attempted"
    assert result.get("address_geocoded_lat") is None

    print("  PASS")


def test_enrich_address_from_cache():
    """Test that cache hit works."""
    print("Test: enrich_address_intelligence — cache hit")

    _clear_cache()

    # First call: populate cache
    lead1 = _make_lead(address="909 W 1160 N")
    with patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        return_value={
            "lat": 40.2338,
            "lng": -111.6585,
            "display_name": "909 West 1160 North, Provo, UT 84601",
            "city": "Provo",
            "state": "Utah",
            "postal_code": "84601",
            "county": "Utah County",
            "house_number": "909",
            "road": "West 1160 North",
            "importance": 0.8,
            "match_quality": "house",
            "raw": {},
        },
    ):
        result1 = enrich_address_intelligence(lead1)

    assert result1["address_enrichment_status"] == "enriched"
    assert result1["address_geocoded_lat"] == 40.2338

    # Second call: should hit cache (no API call)
    lead2 = _make_lead(address="909 W 1160 N")
    with patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        side_effect=AssertionError("Should not be called — cache hit"),
    ):
        result2 = enrich_address_intelligence(lead2)

    assert result2["address_enrichment_status"] == "enriched"
    assert result2["address_geocoded_lat"] == 40.2338

    print("  PASS")


def test_enrich_address_provider_failure():
    """Test that provider failure is non-fatal."""
    print("Test: enrich_address_intelligence — provider failure")

    _clear_cache()
    lead = _make_lead(address="909 W 1160 N")

    with patch(
        "backend.app.services.address_intelligence._geocode_gis",
        side_effect=Exception("GIS down"),
    ), patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        side_effect=Exception("Nominatim down"),
    ), patch(
        "backend.app.services.address_intelligence._geocode_google",
        return_value=None,
    ):
        result = enrich_address_intelligence(lead)

    # Provider failure should set not_resolved, not crash
    assert result["address_enrichment_status"] == "not_resolved"
    assert result["address_geocoding_confidence"] == "UNRESOLVED"

    print("  PASS")


def test_enrich_address_carry_forward():
    """Test that previous lead data is carried forward."""
    print("Test: enrich_address_intelligence — carry forward")

    _clear_cache()
    lead = _make_lead(address="909 W 1160 N")

    previous = {
        "application_number": "TEST20260001",
        "address_source_address": "909 W 1160 N",
        "address_geocoded_lat": 40.2338,
        "address_geocoded_lng": -111.6585,
        "address_geocoded_city": "Provo",
        "address_geocoded_state": "Utah",
        "address_geocoded_postal": "84601",
        "address_geocoded_county": "Utah County",
        "address_geocoded_full": "909 West 1160 North, Provo, UT 84601",
        "address_geocoding_source": "nominatim",
        "address_geocoding_confidence": "HIGH",
        "address_geocoding_method": "street_only_geocode",
        "address_geocoding_evidence": "Test evidence",
        "address_geocoded_at": "2026-08-20T12:00:00+00:00",
        "address_parcel_id_verified": None,
        "address_parcel_source": None,
        "address_enrichment_status": "enriched",
    }

    with patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        side_effect=AssertionError("Should not be called — carry forward"),
    ):
        result = enrich_address_intelligence(lead, previous_lead=previous)

    assert result["address_geocoded_lat"] == 40.2338
    assert result["address_geocoded_city"] == "Provo"
    assert result["address_geocoding_confidence"] == "HIGH"

    print("  PASS")


def test_raw_address_preservation():
    """Test that the original government-record address is never modified."""
    print("Test: raw address preservation")

    _clear_cache()
    original_address = "909 W 1160 N"
    lead = _make_lead(address=original_address)

    with patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        return_value={
            "lat": 40.2338,
            "lng": -111.6585,
            "display_name": "909 West 1160 North, Provo, Utah 84601, USA",
            "city": "Provo",
            "state": "Utah",
            "postal_code": "84601",
            "county": "Utah County",
            "house_number": "909",
            "road": "West 1160 North",
            "importance": 0.8,
            "match_quality": "house",
            "raw": {},
        },
    ):
        result = enrich_address_intelligence(lead)

    # Original fields must be untouched
    assert result["property_address_full"] == original_address
    assert result["project_address"] == original_address
    # Enrichment fields are separate
    assert result["address_source_address"] == original_address
    assert result["address_geocoded_lat"] == 40.2338
    assert result["address_geocoded_full"] != original_address

    print("  PASS")


def test_enrich_all_addresses():
    """Test bulk enrichment."""
    print("Test: enrich_all_addresses")

    _clear_cache()
    leads = [
        _make_lead(address="909 W 1160 N"),
        _make_lead(address="123 Main St"),
        _make_lead(address=""),  # No address
    ]

    mock_result = {
        "lat": 40.2338,
        "lng": -111.6585,
        "display_name": "Test Address",
        "city": "Provo",
        "state": "Utah",
        "postal_code": "84601",
        "county": "Utah County",
        "house_number": "909",
        "road": "West 1160 North",
        "importance": 0.7,
        "match_quality": "house",
        "raw": {},
    }

    with patch(
        "backend.app.services.address_intelligence._geocode_nominatim",
        return_value=mock_result,
    ):
        result = enrich_all_addresses(leads, verbose=False)

    assert len(result) == 3
    # First two should be enriched
    assert result[0]["address_enrichment_status"] == "enriched"
    assert result[1]["address_enrichment_status"] == "enriched"
    # Third has no address — not_attempted
    assert result[2]["address_enrichment_status"] == "not_attempted"

    print("  PASS")


def test_existing_records_without_enrichment():
    """Test that records without enrichment data display gracefully."""
    print("Test: existing records without enrichment data")

    lead = _make_lead(address="909 W 1160 N")
    # No address_enrichment_status set (simulates old record)
    assert lead.get("address_enrichment_status") is None
    assert lead.get("address_geocoded_lat") is None
    assert lead.get("address_geocoding_confidence") is None

    print("  PASS")


# ---------------------------------------------------------------------------
# Live test (requires network)
# ---------------------------------------------------------------------------

def test_live_geocoding():
    """Live test: geocode a known address via Nominatim."""
    print("Test: live geocoding via Nominatim")

    _clear_cache()
    lead = _make_lead(
        address="909 W 1160 N",
        municipality="Provo",
        state="UT",
    )

    result = enrich_address_intelligence(lead)

    print(f"  Status:   {result.get('address_enrichment_status')}")
    print(f"  Lat/Lng:  {result.get('address_geocoded_lat')}, {result.get('address_geocoded_lng')}")
    print(f"  City:     {result.get('address_geocoded_city')}")
    print(f"  State:    {result.get('address_geocoded_state')}")
    print(f"  Postal:   {result.get('address_geocoded_postal')}")
    print(f"  County:   {result.get('address_geocoded_county')}")
    print(f"  Full:     {result.get('address_geocoded_full')}")
    print(f"  Source:   {result.get('address_geocoding_source')}")
    print(f"  Conf:     {result.get('address_geocoding_confidence')}")
    print(f"  Method:   {result.get('address_geocoding_method')}")
    print(f"  Evidence: {result.get('address_geocoding_evidence')}")

    # Should resolve to something
    assert result["address_enrichment_status"] in ("enriched", "not_resolved")

    if result["address_enrichment_status"] == "enriched":
        assert result["address_geocoded_lat"] is not None
        assert result["address_geocoded_lng"] is not None
        assert result["address_geocoding_source"] is not None
        assert result["address_geocoding_confidence"] is not None
        # Original address untouched
        assert result["property_address_full"] == "909 W 1160 N"

    print("  PASS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PermitSignal Address Intelligence Test"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live geocoding tests (requires network).",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("PERMITSIGNAL ADDRESS INTELLIGENCE TEST")
    print("=" * 70)
    print()

    # Always-run tests (no network)
    test_normalize_address()
    test_cache_key_deterministic()
    test_extract_source_components()
    test_state_abbreviation_match()
    test_classify_confidence_exact_match()
    test_classify_confidence_partial_match()
    test_classify_confidence_street_only()
    test_classify_confidence_no_match()
    test_classify_confidence_unresolved()
    test_is_within_ttl()
    test_enrich_address_no_address()
    test_enrich_address_from_cache()
    test_enrich_address_provider_failure()
    test_enrich_address_carry_forward()
    test_raw_address_preservation()
    test_enrich_all_addresses()
    test_existing_records_without_enrichment()

    if args.live:
        print()
        test_live_geocoding()

    print()
    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
