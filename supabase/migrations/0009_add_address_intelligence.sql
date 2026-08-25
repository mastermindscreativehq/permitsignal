-- Address Intelligence: geocoded coordinates, verified city/state/ZIP,
-- geocoding source, confidence, and provenance for property addresses.
-- Purely additive: no existing columns dropped or retyped.
--
-- Applied by backend.app.services.lead_repository after every pipeline run
-- that includes address intelligence enrichment.  The original
-- property_address_full (government-record source) is never modified.

ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS address_geocoded_lat numeric,
    ADD COLUMN IF NOT EXISTS address_geocoded_lng numeric,
    ADD COLUMN IF NOT EXISTS address_geocoded_city text,
    ADD COLUMN IF NOT EXISTS address_geocoded_state text,
    ADD COLUMN IF NOT EXISTS address_geocoded_postal text,
    ADD COLUMN IF NOT EXISTS address_geocoded_county text,
    ADD COLUMN IF NOT EXISTS address_geocoded_full text,
    ADD COLUMN IF NOT EXISTS address_geocoding_source text,
    ADD COLUMN IF NOT EXISTS address_geocoding_confidence text,
    ADD COLUMN IF NOT EXISTS address_geocoding_method text,
    ADD COLUMN IF NOT EXISTS address_geocoding_evidence text,
    ADD COLUMN IF NOT EXISTS address_geocoded_at timestamptz,
    ADD COLUMN IF NOT EXISTS address_parcel_id_verified text,
    ADD COLUMN IF NOT EXISTS address_parcel_source text,
    ADD COLUMN IF NOT EXISTS address_source_address text,
    ADD COLUMN IF NOT EXISTS address_enrichment_status text;

COMMENT ON COLUMN public.leads.address_geocoded_lat IS 'Latitude from authoritative geocoding source.';
COMMENT ON COLUMN public.leads.address_geocoded_lng IS 'Longitude from authoritative geocoding source.';
COMMENT ON COLUMN public.leads.address_geocoded_city IS 'Verified city from geocoding (never overwrites government-record city).';
COMMENT ON COLUMN public.leads.address_geocoded_state IS 'Verified state from geocoding.';
COMMENT ON COLUMN public.leads.address_geocoded_postal IS 'Verified postal/ZIP code from geocoding.';
COMMENT ON COLUMN public.leads.address_geocoded_county IS 'County resolved from geocoding or GIS.';
COMMENT ON COLUMN public.leads.address_geocoded_full IS 'Full standardized address as resolved by geocoding provider.';
COMMENT ON COLUMN public.leads.address_geocoding_source IS 'Provider that resolved the address (nominatim/google_maps/parcel_lookup/government_record).';
COMMENT ON COLUMN public.leads.address_geocoding_confidence IS 'HIGH/MEDIUM/LOW/UNRESOLVED -- independent verification level.';
COMMENT ON COLUMN public.leads.address_geocoding_method IS 'How the address was resolved (full_address_geocode/street_only_geocode/jurisdiction_hint).';
COMMENT ON COLUMN public.leads.address_geocoding_evidence IS 'Raw API response or verification snippet proving the result.';
COMMENT ON COLUMN public.leads.address_geocoded_at IS 'Timestamp of last successful geocoding enrichment.';
COMMENT ON COLUMN public.leads.address_parcel_id_verified IS 'Parcel ID confirmed by GIS/parcel lookup (when available).';
COMMENT ON COLUMN public.leads.address_parcel_source IS 'Source of parcel verification.';
COMMENT ON COLUMN public.leads.address_source_address IS 'Original government-record address as stored before enrichment.';
COMMENT ON COLUMN public.leads.address_enrichment_status IS 'enriched/error/timeout/not_attempted -- status of address enrichment.';

CREATE INDEX IF NOT EXISTS leads_address_geocoding_confidence_idx
    ON public.leads (address_geocoding_confidence);
