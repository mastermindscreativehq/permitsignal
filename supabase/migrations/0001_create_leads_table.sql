-- PermitSignal Lead Intelligence table.
--
-- One row per canonical lead record. application_number is the natural
-- business key: re-running the pipeline with sync_to_supabase=True (or
-- `--sync-supabase`) upserts on application_number, so lead_status and
-- contact fields can be tracked and updated over repeated runs instead
-- of being recomputed from scratch every time.
--
-- Apply this once via the Supabase SQL editor or `supabase db push`
-- before enabling sync_to_supabase -- backend.app.services.lead_repository
-- does not run DDL itself.
--
-- Confidence columns (email_confidence, phone_confidence,
-- contact_confidence) are TEXT rather than numeric because
-- PermitSignal's existing identity/enrichment services intentionally use
-- two different confidence models (HIGH/MEDIUM/LOW labels vs. 0.0-1.0
-- floats) -- see docs/DEVELOPMENT_RULES.md section 11. This mirrors the
-- existing convention rather than forcing a new one.

create extension if not exists pgcrypto;

create table if not exists public.leads (
    id uuid primary key default gen_random_uuid(),

    -- Identity
    application_number text not null unique,
    applicant_name text,
    normalized_applicant_name text,
    company_name text,
    company_website text,
    company_domain text,

    -- Project
    application_type text,
    project_address text,
    neighborhood text,
    status text,
    description text,

    -- Friction
    friction_score integer,
    friction_signals jsonb not null default '[]'::jsonb,
    friction_events jsonb not null default '[]'::jsonb,

    -- Project event
    next_project_date date,
    next_project_event text,
    next_project_time text,
    has_future_opportunity boolean not null default false,
    days_until_event integer,
    urgency text,

    -- Opportunity / qualification
    priority text,
    priority_score integer,
    is_actionable boolean not null default false,
    opportunity_reason text,

    -- Contact
    contact_name text,
    contact_role text,
    applicant_email text,
    applicant_phone text,
    contact_email text,
    contact_phone text,
    linkedin_url text,

    -- Contact evidence
    email_source text,
    phone_source text,
    company_source text,
    contact_source text,
    email_confidence text,
    phone_confidence text,
    contact_confidence text,
    contact_is_public boolean,
    contact_is_verified boolean,

    -- Enrichment
    identity_status text,
    enrichment_status text,
    enrichment_method text,

    -- Lead intelligence
    lead_status text,
    is_contactable boolean not null default false,

    -- Provenance
    source text,
    source_url text,
    municipality text,
    state text,

    -- Government staff contact (kept separate from applicant contact --
    -- see docs/DEVELOPMENT_RULES.md section 7)
    staff_contact_name text,
    staff_contact_email text,
    staff_contact_phone text,

    -- Full canonical lead record, verbatim. Nothing is ever lost here,
    -- even for fields not promoted to their own column above.
    record jsonb not null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists leads_priority_idx
    on public.leads (priority);

create index if not exists leads_lead_status_idx
    on public.leads (lead_status);

create index if not exists leads_next_project_date_idx
    on public.leads (next_project_date);

comment on table public.leads is
    'PermitSignal canonical lead intelligence records. One row per application_number. Upserted by backend.app.services.lead_repository.upsert_leads().';
