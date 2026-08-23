-- 0008_add_entity_intelligence.sql
-- Entity Intelligence Layer: normalized entities, case-entity links,
-- relationships, entity sources, claim-level evidence, candidate matches,
-- and research run history.
--
-- Design notes:
-- - "cases" are intentionally NOT re-modeled here. The existing
--   public.leads table (keyed by application_number) remains the canonical
--   case record; entity rows link to cases via application_number columns.
--   This avoids creating a duplicate concept (CLAUDE.md rule 9).
-- - entity_key is a deterministic application-layer id derived from
--   (entity_type, normalized name, discriminator), so repeated research
--   runs upsert the same entity instead of duplicating it.
-- - evidence_id / match_id / source_id are deterministic hashes so that
--   re-running research upserts idempotently.
-- - Every evidence row carries its source and verification status:
--   search-snippet-only claims are stored as 'unverified', never as facts.
-- - No cross-table foreign keys, matching the convention of migrations
--   0001-0007; referential ordering is enforced by the repository layer.
-- - IMPORTANT: the evidence-source registry for this subsystem is named
--   public.entity_sources. public.sources ALREADY EXISTS as the document /
--   collector source registry (external_id, municipality_id, ...) and must
--   not be altered or reused.
-- - Fully idempotent: tables/indexes use IF NOT EXISTS and policies are
--   dropped-before-create, so the file can be safely re-run.

create extension if not exists pgcrypto;

create table if not exists public.entities (
    entity_key text primary key,
    entity_type text not null check (entity_type in (
        'case', 'person', 'organization', 'property', 'government_staff',
        'professional', 'other')),
    canonical_name text not null,
    attributes jsonb not null default '{}'::jsonb,
    match_status text,
    match_confidence numeric,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_entities_type
    on public.entities (entity_type);
create index if not exists idx_entities_canonical_name
    on public.entities (canonical_name);

create table if not exists public.case_entities (
    id uuid primary key default gen_random_uuid(),
    application_number text not null,
    entity_key text not null,
    case_role text not null,
    confidence numeric,
    sources jsonb not null default '[]'::jsonb,
    discovered_at timestamptz not null default now()
);

create unique index if not exists uq_case_entities_app_entity_role
    on public.case_entities (application_number, entity_key, case_role);
create index if not exists idx_case_entities_application
    on public.case_entities (application_number);

create table if not exists public.relationships (
    relationship_id uuid primary key default gen_random_uuid(),
    subject_entity_key text not null,
    predicate text not null,
    object_entity_key text not null,
    application_number text not null default '',
    confidence numeric,
    sources jsonb not null default '[]'::jsonb,
    evidence_ids jsonb not null default '[]'::jsonb,
    discovered_at timestamptz not null default now()
);

create unique index if not exists uq_relationships_triple_case
    on public.relationships
    (subject_entity_key, predicate, object_entity_key, application_number);
create index if not exists idx_relationships_application
    on public.relationships (application_number);

create table if not exists public.entity_sources (
    source_id text primary key,
    url text not null,
    domain text,
    title text,
    source_type text not null,
    hierarchy_rank integer not null default 99,
    discovery_method text,
    metadata jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now()
);

create index if not exists idx_entity_sources_domain
    on public.entity_sources (domain);

create table if not exists public.evidence (
    evidence_id text primary key,
    application_number text not null,
    subject_type text not null,
    subject_key text not null,
    claim text not null,
    value text,
    source_id text,
    source_url text,
    source_domain text,
    source_title text,
    source_type text,
    hierarchy_rank integer,
    discovery_method text,
    evidence_text text,
    discovered_at timestamptz,
    confidence numeric,
    verification_status text not null default 'unverified'
);

create index if not exists idx_evidence_application
    on public.evidence (application_number);
create index if not exists idx_evidence_subject
    on public.evidence (subject_type, subject_key);

create table if not exists public.entity_matches (
    match_id text primary key,
    entity_key text not null,
    candidate_kind text not null,
    candidate_name text,
    candidate_url text,
    match_status text not null,
    match_confidence numeric,
    match_reasons jsonb not null default '[]'::jsonb,
    matched_signals jsonb not null default '[]'::jsonb,
    conflicting_signals jsonb not null default '[]'::jsonb,
    source_url text,
    created_at timestamptz not null default now()
);

create index if not exists idx_entity_matches_entity
    on public.entity_matches (entity_key);

create table if not exists public.research_runs (
    run_id uuid primary key default gen_random_uuid(),
    application_number text not null,
    status text not null default 'running',
    depth_reached integer not null default 0,
    queries_executed integer not null default 0,
    pages_fetched integer not null default 0,
    entities_discovered integer not null default 0,
    evidence_collected integer not null default 0,
    errors jsonb not null default '[]'::jsonb,
    params jsonb not null default '{}'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create index if not exists idx_research_runs_application
    on public.research_runs (application_number);

-- Row-level security: enabled but permissive for service-role access,
-- mirroring 0006/0007. Policies are dropped first so re-runs converge.
ALTER TABLE public.entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.case_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entity_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entity_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on entities"
    ON public.entities;
CREATE POLICY "Service role full access on entities"
    ON public.entities FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on case_entities"
    ON public.case_entities;
CREATE POLICY "Service role full access on case_entities"
    ON public.case_entities FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on relationships"
    ON public.relationships;
CREATE POLICY "Service role full access on relationships"
    ON public.relationships FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on entity_sources"
    ON public.entity_sources;
CREATE POLICY "Service role full access on entity_sources"
    ON public.entity_sources FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on evidence"
    ON public.evidence;
CREATE POLICY "Service role full access on evidence"
    ON public.evidence FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on entity_matches"
    ON public.entity_matches;
CREATE POLICY "Service role full access on entity_matches"
    ON public.entity_matches FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on research_runs"
    ON public.research_runs;
CREATE POLICY "Service role full access on research_runs"
    ON public.research_runs FOR ALL USING (true) WITH CHECK (true);
