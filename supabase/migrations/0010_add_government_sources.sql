-- 0010_add_government_sources.sql
-- Source Registry: configuration-driven government source management.
-- Each row represents a government agency whose planning/permit documents
-- can be discovered and ingested through the PermitSignal pipeline.
--
-- Adding a new source = inserting a row.  No new code required for
-- standard PDF or HTML-agenda sources.

CREATE TABLE IF NOT EXISTS government_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key      TEXT UNIQUE NOT NULL,
    state           TEXT NOT NULL,
    city            TEXT,
    county          TEXT,
    agency          TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    platform        TEXT,
    adapter         TEXT NOT NULL DEFAULT 'pdf',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    ingestion_metadata JSONB DEFAULT '{}',
    last_ingested_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE government_sources IS 'Source Registry: configuration-driven government source management for multi-source ingestion.';
COMMENT ON COLUMN government_sources.source_key IS 'Unique machine key, e.g. provo_planning, tulsa_county_pud.';
COMMENT ON COLUMN government_sources.source_type IS 'Content type: pdf_direct, html_agenda, platform_civicplus, platform_qalert, etc.';
COMMENT ON COLUMN government_sources.adapter IS 'Adapter used to discover/download: pdf, html_playwright, platform.';
COMMENT ON COLUMN government_sources.config IS 'Adapter-specific configuration (e.g. scrape selectors, RSS URLs, page categories).';
COMMENT ON COLUMN government_sources.ingestion_metadata IS 'Last run stats: documents_discovered, documents_ingested, errors, etc.';

-- Index for active-source queries
CREATE INDEX IF NOT EXISTS idx_government_sources_active ON government_sources (active) WHERE active = TRUE;

-- Seed: the existing Provo Planning Commission source (backward-compatible)
INSERT INTO government_sources (
    source_key, state, city, county, agency, source_url,
    source_type, platform, adapter, config
) VALUES (
    'provo_planning',
    'Utah',
    'Provo',
    'Utah County',
    'Provo Planning Commission',
    'https://www.provo.gov/AgendaCenter/Planning-Commission-2',
    'html_agenda',
    'civicplus',
    'html_playwright',
    '{
        "categories": [
            "https://www.provo.gov/AgendaCenter/Planning-Commission-2",
            "https://www.provo.gov/AgendaCenter/Planning-Commission-Administrative-Heari-5"
        ],
        "rss_url": "https://www.provo.gov/RSSFeed.aspx?ModID=65&CID=All-0",
        "link_patterns": ["/AgendaCenter/ViewFile/Agenda/", "/AgendaCenter/PreviousVersions/"],
        "pdf_content_types": ["application/pdf"]
    }'
) ON CONFLICT (source_key) DO NOTHING;

-- Add source_key to leads table for provenance tracking
ALTER TABLE leads ADD COLUMN IF NOT EXISTS source_key TEXT;
COMMENT ON COLUMN leads.source_key IS 'Foreign key to government_sources.source_key identifying which government source produced this lead.';
