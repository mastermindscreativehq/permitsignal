"""
Address Intelligence Service — geocode, verify, and enrich property
addresses extracted from government planning records.

Purpose
-------
Turn a partial or ambiguous government-record address (e.g. "909 W
1160 N") into verified real-world location intelligence: lat/lng
coordinates, confirmed city/state/ZIP, county, and standardized full
address.

This module is entirely ADDITIVE.  The original government-record
address (property_address_full / project_address) is never modified.

Design principles
-----------------
- Never fabricate: absent information stays None with an explicit
  status (not_found / unverified / ambiguous).
- A search snippet or geocode result alone is NOT a verified fact;
  verification requires either an authoritative government GIS source
  or corroborating independent sources.
- This module never overwrites government-record data on the lead.
- External provider failures are non-fatal.
- Results are cached per normalized address to avoid duplicate lookups.

Provider hierarchy
------------------
1. Government GIS / parcel database (when explicitly configured)
2. OpenStreetMap Nominatim (free, no key required)
3. Google Geocoding API (when GOOGLE_GEOCODING_API_KEY is set)

Provider selection is driven by environment variables so credentials
are never hardcoded.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# =========================================================================
# Configuration
# =========================================================================

GOOGLE_GEOCODING_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY", "")
NOMINATIM_BASE_URL = os.getenv(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
)
# Custom GIS endpoint (e.g. a city ArcGIS REST service)
GIS_BASE_URL = os.getenv("ADDRESS_GIS_BASE_URL", "")
GIS_API_KEY = os.getenv("ADDRESS_GIS_API_KEY", "")

# Rate limiting: milliseconds between external calls
CALL_DELAY_MS = int(os.getenv("ADDRESS_CALL_DELAY_MS", "110"))
MAX_ADDRESSES_PER_RUN = int(os.getenv("ADDRESS_MAX_PER_RUN", "500"))
REQUEST_TIMEOUT = float(os.getenv("ADDRESS_REQUEST_TIMEOUT", "5.0"))

# Cache TTL: skip re-enrichment if geocoded within this many days
CACHE_TTL_DAYS = int(os.getenv("ADDRESS_CACHE_TTL_DAYS", "30"))

# Confidence thresholds
# HIGH:   geocode returned exact match to source components
# MEDIUM: strong geocode match + contextual support, no GIS confirmation
# LOW:    plausible candidate, insufficient verification
# UNRESOLVED: no reliable match

PRODUCT_NAME = "PROVO ADMINISTRATIVE SERVICES FINANCE"

# =========================================================================
# In-memory cache (per pipeline run)
# =========================================================================

_address_cache: dict[str, dict[str, Any]] = {}


def _clear_cache() -> None:
    """Clear the in-memory address cache (for testing)."""
    global _address_cache
    _address_cache = {}


# =========================================================================
# Normalization (for search only — original preserved unchanged)
# =========================================================================

_UNIT_SUFFIXES = re.compile(
    r"\b(apt|unit|suite|ste|bldg|building|floor|fl|rm|room|dept|parking)\b",
    re.IGNORECASE,
)


def normalize_address_for_search(raw: str) -> str:
    """
    Produce a search-optimized form of the address.  The raw value is
    never modified or stored — this is used solely for geocoding API
    queries.
    """
    if not raw:
        return ""

    addr = raw.strip()

    # Normalize unicode
    addr = unicodedata.normalize("NFKD", addr)

    # Remove trailing periods / commas
    addr = addr.rstrip(".,;:")

    # Handle compound addresses like "113/191 N Geneva Road" — take
    # the first number since geocoders can't parse slash-separated
    # parcel ranges.
    addr = re.sub(r"(\d+)\s*/\s*\d+\s+", r"\1 ", addr)

    # Collapse whitespace
    addr = re.sub(r"\s+", " ", addr).strip()

    # Standardize common abbreviations for search.
    # Keep directional abbreviations as-is (N, S, E, W) since
    # Nominatim/Google handle them natively.  Expanding them can
    # break resolution (e.g. "1065 E Hillside" → "1065 East
    # Hillside" is NOT found by Nominatim).

    return addr.strip()


def _cache_key(normalized: str) -> str:
    return hashlib.sha256(normalized.lower().encode()).hexdigest()[:16]


# =========================================================================
# Provider: Nominatim (OpenStreetMap)
# =========================================================================

def _geocode_nominatim(
    query: str,
    context_hint: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """
    Geocode an address via Nominatim.  Returns structured result dict
    or None on failure.
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — Nominatim geocoding unavailable")
        return None

    params: dict[str, str] = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "5",
        "countrycodes": "us",
    }

    # Jurisdiction hint: when source is street-only, append city/state
    # to the query so Nominatim resolves to the correct location.
    # This is a search hint, NOT proof — the result is still verified
    # against source components for confidence classification.
    if context_hint:
        city = context_hint.get("city") or context_hint.get("municipality")
        state = context_hint.get("state")
        if city and state and state not in query:
            params["q"] = f"{query}, {city}, {state}"
        elif city and city not in query:
            params["q"] = f"{query}, {city}"

    headers = {
        "User-Agent": f"PermitSignal Address Intelligence ({PRODUCT_NAME})",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(
                f"{NOMINATIM_BASE_URL}/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            results = response.json()

        if not results:
            return None

        best = results[0]

        address_parts = best.get("address", {})

        return {
            "lat": float(best.get("lat", 0)),
            "lng": float(best.get("lon", 0)),
            "display_name": best.get("display_name", ""),
            "city": (
                address_parts.get("city")
                or address_parts.get("town")
                or address_parts.get("village")
                or address_parts.get("hamlet")
            ),
            "state": address_parts.get("state"),
            "postal_code": address_parts.get("postcode"),
            "county": address_parts.get("county"),
            "house_number": address_parts.get("house_number"),
            "road": address_parts.get("road"),
            "osm_type": best.get("osm_type"),
            "osm_id": best.get("osm_id"),
            "importance": best.get("importance", 0),
            "match_quality": best.get("type", ""),
            "raw": best,
        }

    except Exception as exc:
        logger.warning("Nominatim geocoding failed for %r: %s", query, exc)
        return None


# =========================================================================
# Provider: Google Geocoding API
# =========================================================================

def _geocode_google(
    query: str,
    context_hint: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """
    Geocode an address via Google Geocoding API.  Requires
    GOOGLE_GEOCODING_API_KEY.
    """
    if not GOOGLE_GEOCODING_API_KEY:
        return None

    try:
        import httpx
    except ImportError:
        return None

    params: dict[str, str] = {
        "address": query,
        "key": GOOGLE_GEOCODING_API_KEY,
    }

    if context_hint:
        components: list[str] = []
        city = context_hint.get("city") or context_hint.get("municipality")
        state = context_hint.get("state")
        if city:
            components.append(f"locality:{city}")
        if state:
            components.append(f"administrative_area:{state}")
        if components:
            params["components"] = "|".join(components)

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return None

        best = data["results"][0]
        loc = best.get("geometry", {}).get("location", {})
        parts = best.get("address_components", [])

        def _component(short_type: str) -> Optional[str]:
            for part in parts:
                if short_type in part.get("types", []):
                    return part.get("long_name")
            return None

        return {
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "display_name": best.get("formatted_address", ""),
            "city": _component("locality"),
            "state": _component("administrative_area_level_1"),
            "postal_code": _component("postal_code"),
            "county": _component("administrative_area_level_2"),
            "house_number": _component("street_number"),
            "road": _component("route"),
            "place_id": best.get("place_id"),
            "match_quality": best.get("geometry", {}).get("location_type", ""),
            "raw": best,
        }

    except Exception as exc:
        logger.warning("Google geocoding failed for %r: %s", query, exc)
        return None


# =========================================================================
# Provider: Custom GIS endpoint
# =========================================================================

def _geocode_gis(
    query: str,
    context_hint: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """
    Geocode via a configured ArcGIS REST / custom GIS endpoint.  The
    endpoint must accept a 'SingleLine' parameter and return
    ArcGIS-standard JSON.
    """
    if not GIS_BASE_URL:
        return None

    try:
        import httpx
    except ImportError:
        return None

    params: dict[str, str] = {
        "SingleLine": query,
        "f": "json",
        "outFields": "*",
    }

    if GIS_API_KEY:
        params["token"] = GIS_API_KEY

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(GIS_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            return None

        best = candidates[0]
        attrs = best.get("attributes", {})
        loc = best.get("location", {})

        return {
            "lat": loc.get("y"),
            "lng": loc.get("x"),
            "display_name": best.get("address", ""),
            "city": attrs.get("City") or attrs.get("city"),
            "state": attrs.get("State") or attrs.get("state"),
            "postal_code": (
                attrs.get("Postal") or attrs.get("ZIP") or attrs.get("zip")
            ),
            "county": attrs.get("County") or attrs.get("county"),
            "score": best.get("score", 0),
            "match_quality": "gis_candidate",
            "raw": best,
        }

    except Exception as exc:
        logger.warning("GIS geocoding failed for %r: %s", query, exc)
        return None


# =========================================================================
# Confidence classification
# =========================================================================

def _classify_confidence(
    geocoded: dict[str, Any],
    source_components: dict[str, Optional[str]],
) -> str:
    """
    Compare geocoded result against source components to determine
    confidence.  Never modifies source_components.
    """
    if not geocoded:
        return "UNRESOLVED"

    # Score matches on city, state, postal
    matches = 0
    checks = 0

    source_city = (source_components.get("city") or "").strip().lower()
    source_state = (source_components.get("state") or "").strip().lower()
    source_postal = (source_components.get("postal_code") or "").strip()

    geo_city = (geocoded.get("city") or "").strip().lower()
    geo_state = (geocoded.get("state") or "").strip().lower()
    geo_postal = (geocoded.get("postal_code") or "").strip()

    if source_city:
        checks += 1
        if geo_city and source_city in geo_city or geo_city in source_city:
            matches += 1
    if source_state:
        checks += 1
        if geo_state and _state_abbreviation_match(source_state, geo_state):
            matches += 1
    if source_postal:
        checks += 1
        if geo_postal and source_postal[:5] == geo_postal[:5]:
            matches += 1

    # Score based on GIS / parcel confirmation
    gis_score = geocoded.get("score")
    is_gis = geocoded.get("match_quality") == "gis_candidate"
    is_government = geocoded.get("match_quality") == "government_record"

    if is_government:
        return "HIGH"

    if is_gis and gis_score and gis_score >= 90:
        if checks == 0 or matches == checks:
            return "HIGH"
        if matches > 0:
            return "MEDIUM"
        return "MEDIUM"

    # Nominatim / Google
    importance = geocoded.get("importance") or 0
    match_type = geocoded.get("match_quality") or ""

    if checks > 0 and matches == checks:
        if importance >= 0.7 or match_type in ("house", "apartment"):
            return "HIGH"
        return "MEDIUM"

    if checks > 0 and matches > 0:
        # State-only match is not sufficient for MEDIUM — require at
        # least a city match for medium confidence.
        city_matched = bool(source_city and geo_city and (
            source_city in geo_city or geo_city in source_city
        ))
        if city_matched or matches >= 2:
            return "MEDIUM"
        return "LOW"

    if checks == 0:
        # Source was street-only — any geocode result is MEDIUM if street
        # was found, LOW otherwise
        if geocoded.get("house_number") and geocoded.get("road"):
            return "MEDIUM"
        return "LOW"

    return "LOW"


def _state_abbreviation_match(a: str, b: str) -> bool:
    """Check if two state strings match as abbreviation vs full name."""
    _ABBREV_MAP = {
        "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
        "california": "ca", "colorado": "co", "connecticut": "ct",
        "delaware": "de", "florida": "fl", "georgia": "ga", "hawaii": "hi",
        "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
        "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me",
        "maryland": "md", "massachusetts": "ma", "michigan": "mi",
        "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
        "montana": "mt", "nebraska": "ne", "nevada": "nv",
        "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm",
        "new york": "ny", "north carolina": "nc", "north dakota": "nd",
        "ohio": "oh", "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa",
        "rhode island": "ri", "south carolina": "sc", "south dakota": "sd",
        "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
        "virginia": "va", "washington": "wa", "west virginia": "wv",
        "wisconsin": "wi", "wyoming": "wy",
        "district of columbia": "dc",
    }
    abbrev_a = _ABBREV_MAP.get(a)
    abbrev_b = _ABBREV_MAP.get(b)
    if abbrev_a and abbrev_a == b:
        return True
    if abbrev_b and abbrev_b == a:
        return True
    return False


# =========================================================================
# Source component extraction
# =========================================================================

def _extract_source_components(
    opportunity: dict[str, Any],
) -> dict[str, Optional[str]]:
    """
    Extract address components from the lead/opportunity dict without
    modifying it.  Uses property_address_components first, falls back
    to individual fields.
    """
    components = opportunity.get("property_address_components")
    if isinstance(components, dict):
        return {
            "city": components.get("city"),
            "state": components.get("state"),
            "postal_code": components.get("postal_code"),
            "street_number": components.get("street_number"),
            "street_name": components.get("street_name"),
            "unit": components.get("unit"),
        }

    return {
        "city": None,
        "state": None,
        "postal_code": None,
        "street_number": None,
        "street_name": None,
        "unit": None,
    }


def _source_address_for_enrichment(
    opportunity: dict[str, Any],
) -> Optional[str]:
    """
    Return the best available source address for geocoding.  Prefers
    property_address_full (the most complete source form) over
    project_address (may be partial).
    """
    return (
        opportunity.get("property_address_full")
        or opportunity.get("project_address")
    )


def _context_hint(opportunity: dict[str, Any]) -> dict[str, Optional[str]]:
    """
    Build a context-hint dict from the lead for provider biasing.
    This is a hint, NOT proof — never used as ground truth.

    Extracts jurisdiction from multiple sources in priority order:
    1. Explicit municipality / state fields (if populated)
    2. Source name (e.g. "Provo Planning Commission" → city=Provo)
    3. Source URL domain (e.g. provo.gov → city=Provo)
    """
    city = opportunity.get("municipality")
    state = opportunity.get("state")

    # Fallback: extract city from source name
    if not city:
        city = _city_from_source_name(opportunity.get("source") or "")

    # Fallback: extract city from source URL
    if not city:
        city = _city_from_source_url(opportunity.get("source_url") or "")

    # Map well-known Utah cities to state
    if city and not state:
        state = _utah_city_to_state.get(city.lower())

    return {
        "city": city,
        "state": state,
        "county": None,
        "parcel_number": opportunity.get("parcel_number"),
    }


# Known Utah jurisdiction mappings (from Provo packet context)
_utmunicipality_source = re.compile(
    r"(Provo|Orem|Lehi|Pleasant Grove|Spanish Fork|Springville|Mapleton|Payson|Salem|Spanish Fork|Lindon|American Fork|Highland|Cedar Hills|Alpine|Draper|Sandy|South Jordan|West Jordan|Murray|Taylorsville|Midvale|Millcreek|Holladay|Cottonwood Heights|Brighton|Bountiful|Layton|Kaysville|Farmington|Centerville|Clearfield|Roy|Ogden|Layton|Logan|St\. George|Cedar City)",
    re.IGNORECASE,
)


def _city_from_source_name(source: str) -> Optional[str]:
    """
    Extract city name from a government source label like
    "Provo Planning Commission" or "Orem City Council".
    """
    if not source:
        return None

    match = _utmunicipality_source.search(source)
    if match:
        return match.group(1)

    return None


def _city_from_source_url(url: str) -> Optional[str]:
    """
    Extract city from a source URL like
    "https://www.provo.gov/AgendaCenter/..."
    """
    if not url:
        return None

    # Common pattern: www.{city}.gov or {city}.gov
    match = re.search(r"https?://(?:www\.)?([a-z]+)\.gov", url, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()

    return None


# Utah city → state mapping (addresses in these cities are in Utah)
_utah_city_to_state: dict[str, str] = {
    "provo": "Utah",
    "orem": "Utah",
    "lehi": "Utah",
    "pleasant grove": "Utah",
    "spanish fork": "Utah",
    "springville": "Utah",
    "mapleton": "Utah",
    "payson": "Utah",
    "salem": "Utah",
    "lindon": "Utah",
    "american fork": "Utah",
    "highland": "Utah",
    "cedar hills": "Utah",
    "alpine": "Utah",
    "draper": "Utah",
    "sandy": "Utah",
    "south jordan": "Utah",
    "west jordan": "Utah",
    "murray": "Utah",
    "taylorsville": "Utah",
    "midvale": "Utah",
    "millcreek": "Utah",
    "holladay": "Utah",
    "cottonwood heights": "Utah",
    "brighton": "Utah",
    "bountiful": "Utah",
    "layton": "Utah",
    "kaysville": "Utah",
    "farmington": "Utah",
    "centerville": "Utah",
    "clearfield": "Utah",
    "roy": "Utah",
    "ogden": "Utah",
    "logan": "Utah",
    "st. george": "Utah",
    "cedar city": "Utah",
}


# =========================================================================
# Main enrichment function
# =========================================================================

def enrich_address_intelligence(
    opportunity: dict[str, Any],
    force: bool = False,
    previous_lead: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Enrich a single lead/opportunity's property address with geocoded
    location intelligence.

    This is ADDITIVE ONLY: it writes to address_geocoded_* and
    address_enrichment_status fields but never modifies
    property_address_full, project_address, or any government-record
    field.

    Parameters
    ----------
    opportunity : dict
        The canonical lead/opportunity dict (modified in place).
    force : bool
        When True, re-enrich even if previously enriched within TTL.
    previous_lead : dict | None
        If provided, used for cache-check: address intelligence fields
        from the previous run are examined before calling external APIs.

    Returns
    -------
    dict
        The same opportunity dict with address intelligence fields set.
    """
    source_addr = _source_address_for_enrichment(opportunity)

    if not source_addr or not source_addr.strip():
        _set_not_attempted(opportunity, "no_address_in_source")
        return opportunity

    # --- Check cache (previous lead or in-memory) ---
    normalized = normalize_address_for_search(source_addr)
    cache_key = _cache_key(normalized)

    # Check in-memory cache first (dedup across applications in same run)
    if cache_key in _address_cache and not force:
        cached = _address_cache[cache_key]
        _apply_cached_result(opportunity, source_addr, cached)
        logger.debug(
            "Address cache hit for %r (key=%s)", source_addr, cache_key
        )
        return opportunity

    # Check previous lead (from prior pipeline run)
    if not force and previous_lead:
        prev_status = previous_lead.get("address_enrichment_status")
        prev_at = previous_lead.get("address_geocoded_at")
        prev_source = previous_lead.get("address_source_address")

        if prev_status == "enriched" and prev_at and prev_source:
            if _is_within_ttl(prev_at):
                # Carry forward previous enrichment
                _carry_forward(opportunity, previous_lead, source_addr)
                _address_cache[cache_key] = _extract_cache_entry(
                    previous_lead
                )
                logger.debug(
                    "Carrying forward address intelligence for %r",
                    source_addr,
                )
                return opportunity

    # --- Perform geocoding ---
    _set_status(opportunity, source_addr, "resolving")

    context = _context_hint(opportunity)
    source_components = _extract_source_components(opportunity)

    # Try providers in hierarchy order
    geocoded = None
    provider = None

    # 1. Custom GIS
    try:
        geocoded = _geocode_gis(normalized, context)
    except Exception as exc:
        logger.debug("GIS provider failed: %s", exc)
        geocoded = None
    if geocoded:
        provider = "parcel_lookup" if geocoded.get("match_quality") == "gis_candidate" else "gis"

    # 2. Nominatim (always available, no key needed)
    if not geocoded:
        time.sleep(CALL_DELAY_MS / 1000.0)
        try:
            geocoded = _geocode_nominatim(normalized, context)
        except Exception as exc:
            logger.debug("Nominatim provider failed: %s", exc)
            geocoded = None
        if geocoded:
            provider = "nominatim"

    # 3. Google (when configured)
    if not geocoded and GOOGLE_GEOCODING_API_KEY:
        time.sleep(CALL_DELAY_MS / 1000.0)
        try:
            geocoded = _geocode_google(normalized, context)
        except Exception as exc:
            logger.debug("Google provider failed: %s", exc)
            geocoded = None
        if geocoded:
            provider = "google_maps"

    if not geocoded:
        _set_not_resolved(opportunity, source_addr, "no_provider_match")
        _address_cache[cache_key] = {"status": "not_resolved"}
        return opportunity

    # --- Classify confidence ---
    confidence = _classify_confidence(geocoded, source_components)

    # --- Write enrichment fields (additive only) ---
    opportunity["address_source_address"] = source_addr
    opportunity["address_geocoded_lat"] = geocoded.get("lat")
    opportunity["address_geocoded_lng"] = geocoded.get("lng")
    opportunity["address_geocoded_city"] = geocoded.get("city")
    opportunity["address_geocoded_state"] = geocoded.get("state")
    opportunity["address_geocoded_postal"] = geocoded.get("postal_code")
    opportunity["address_geocoded_county"] = geocoded.get("county")
    opportunity["address_geocoded_full"] = geocoded.get("display_name")
    opportunity["address_geocoding_source"] = provider
    opportunity["address_geocoding_confidence"] = confidence
    opportunity["address_geocoding_method"] = _determine_method(
        source_components, geocoded
    )
    opportunity["address_geocoding_evidence"] = _build_evidence(
        geocoded, provider, confidence
    )
    opportunity["address_geocoded_at"] = datetime.now(timezone.utc).isoformat()
    opportunity["address_enrichment_status"] = "enriched"

    # Parcel verification (if GIS provided parcel data)
    if geocoded.get("parcel_id"):
        opportunity["address_parcel_id_verified"] = geocoded["parcel_id"]
        opportunity["address_parcel_source"] = provider

    # Cache for dedup
    _address_cache[cache_key] = _extract_cache_entry(opportunity)

    logger.info(
        "Address enriched: %r -> %s (%s, %s) via %s",
        source_addr,
        geocoded.get("display_name", "?"),
        confidence,
        geocoded.get("city", "?"),
        provider,
    )

    return opportunity


# =========================================================================
# Bulk enrichment
# =========================================================================

def enrich_all_addresses(
    opportunities: list[dict[str, Any]],
    previous_leads: Optional[dict[str, dict[str, Any]]] = None,
    force: bool = False,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """
    Enrich address intelligence for all opportunities in a batch.

    Parameters
    ----------
    opportunities : list[dict]
        List of canonical lead/opportunity dicts.
    previous_leads : dict | None
        Mapping of application_number -> previous lead dict (for caching).
    force : bool
        Re-enrich even if previously resolved within TTL.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    list[dict]
        Same list with address intelligence fields populated.
    """
    if not opportunities:
        return opportunities

    previous_leads = previous_leads or {}
    enriched_count = 0
    skipped_count = 0
    error_count = 0
    unresolved_count = 0

    _clear_cache()

    for i, opportunity in enumerate(opportunities):
        app_number = opportunity.get("application_number", "?")
        prev = previous_leads.get(app_number)

        try:
            result = enrich_address_intelligence(
                opportunity,
                force=force,
                previous_lead=prev,
            )

            status = result.get("address_enrichment_status")
            if status == "enriched":
                enriched_count += 1
            elif status == "not_attempted":
                skipped_count += 1
            else:
                unresolved_count += 1

        except Exception as exc:
            logger.warning(
                "Address intelligence failed for %s: %s", app_number, exc
            )
            _set_not_attempted(opportunity, f"error: {exc}")
            error_count += 1

    if verbose:
        print(
            f"Address intelligence: {enriched_count} enriched, "
            f"{unresolved_count} unresolved, "
            f"{skipped_count} skipped, "
            f"{error_count} errors"
        )

    return opportunities


# =========================================================================
# Helpers
# =========================================================================

def _set_not_attempted(opportunity: dict, reason: str) -> None:
    opportunity["address_enrichment_status"] = "not_attempted"
    opportunity["address_source_address"] = (
        opportunity.get("property_address_full")
        or opportunity.get("project_address")
    )
    opportunity["address_geocoding_evidence"] = reason


def _set_status(opportunity: dict, source_addr: str, status: str) -> None:
    opportunity["address_enrichment_status"] = status
    opportunity["address_source_address"] = source_addr


def _set_not_resolved(opportunity: dict, source_addr: str, reason: str) -> None:
    opportunity["address_enrichment_status"] = "not_resolved"
    opportunity["address_source_address"] = source_addr
    opportunity["address_geocoding_confidence"] = "UNRESOLVED"
    opportunity["address_geocoding_evidence"] = reason


def _determine_method(
    source_components: dict[str, Optional[str]],
    geocoded: dict[str, Any],
) -> str:
    """Determine the geocoding method used."""
    has_city = bool(source_components.get("city"))
    has_state = bool(source_components.get("state"))
    has_postal = bool(source_components.get("postal_code"))

    if has_city and has_state and has_postal:
        return "full_address_geocode"
    if has_city and has_state:
        return "street_city_geocode"
    if has_state:
        return "street_state_geocode"
    return "street_only_geocode"


def _build_evidence(
    geocoded: dict[str, Any],
    provider: str,
    confidence: str,
) -> str:
    """Build a human-readable evidence string."""
    parts = [
        f"Provider: {provider}",
        f"Confidence: {confidence}",
    ]

    if geocoded.get("display_name"):
        parts.append(f"Resolved: {geocoded['display_name']}")

    if geocoded.get("lat") and geocoded.get("lng"):
        parts.append(f"Coordinates: {geocoded['lat']:.6f}, {geocoded['lng']:.6f}")

    if geocoded.get("county"):
        parts.append(f"County: {geocoded['county']}")

    return " | ".join(parts)


def _is_within_ttl(iso_timestamp: str) -> bool:
    """Check if a timestamp is within the cache TTL."""
    try:
        if isinstance(iso_timestamp, str):
            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        else:
            dt = iso_timestamp
        now = datetime.now(timezone.utc)
        delta = now - dt
        return delta.days < CACHE_TTL_DAYS
    except Exception:
        return False


def _extract_cache_entry(lead: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields needed for in-memory cache from a lead dict."""
    return {
        "lat": lead.get("address_geocoded_lat"),
        "lng": lead.get("address_geocoded_lng"),
        "city": lead.get("address_geocoded_city"),
        "state": lead.get("address_geocoded_state"),
        "postal": lead.get("address_geocoded_postal"),
        "county": lead.get("address_geocoded_county"),
        "full": lead.get("address_geocoded_full"),
        "source": lead.get("address_geocoding_source"),
        "confidence": lead.get("address_geocoding_confidence"),
        "method": lead.get("address_geocoding_method"),
        "evidence": lead.get("address_geocoding_evidence"),
        "at": lead.get("address_geocoded_at"),
        "parcel": lead.get("address_parcel_id_verified"),
        "parcel_source": lead.get("address_parcel_source"),
        "status": lead.get("address_enrichment_status"),
    }


def _apply_cached_result(
    opportunity: dict,
    source_addr: str,
    cached: dict[str, Any],
) -> None:
    """Apply a cached geocoding result to a lead."""
    opportunity["address_source_address"] = source_addr
    opportunity["address_geocoded_lat"] = cached.get("lat")
    opportunity["address_geocoded_lng"] = cached.get("lng")
    opportunity["address_geocoded_city"] = cached.get("city")
    opportunity["address_geocoded_state"] = cached.get("state")
    opportunity["address_geocoded_postal"] = cached.get("postal")
    opportunity["address_geocoded_county"] = cached.get("county")
    opportunity["address_geocoded_full"] = cached.get("full")
    opportunity["address_geocoding_source"] = cached.get("source")
    opportunity["address_geocoding_confidence"] = cached.get("confidence")
    opportunity["address_geocoding_method"] = cached.get("method")
    opportunity["address_geocoding_evidence"] = cached.get("evidence")
    opportunity["address_geocoded_at"] = cached.get("at")
    opportunity["address_parcel_id_verified"] = cached.get("parcel")
    opportunity["address_parcel_source"] = cached.get("parcel_source")
    opportunity["address_enrichment_status"] = cached.get("status", "enriched")


def _carry_forward(
    opportunity: dict,
    previous_lead: dict,
    source_addr: str,
) -> None:
    """Carry forward address intelligence from a previous pipeline run."""
    opportunity["address_source_address"] = previous_lead.get(
        "address_source_address", source_addr
    )
    for field in (
        "address_geocoded_lat",
        "address_geocoded_lng",
        "address_geocoded_city",
        "address_geocoded_state",
        "address_geocoded_postal",
        "address_geocoded_county",
        "address_geocoded_full",
        "address_geocoding_source",
        "address_geocoding_confidence",
        "address_geocoding_method",
        "address_geocoding_evidence",
        "address_geocoded_at",
        "address_parcel_id_verified",
        "address_parcel_source",
        "address_enrichment_status",
    ):
        if field in previous_lead and previous_lead[field] is not None:
            opportunity[field] = previous_lead[field]
