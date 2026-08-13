-- PermitSignal party-role model: Property Owner / Principal, Applicant of
-- Record / Agent, and Engineer/Architect/other licensed professionals,
-- distinct from each other and from government staff.
--
-- Purely additive: no existing column is dropped, renamed, or retyped.
-- applicant_name/applicant_email/applicant_phone (existing columns) keep
-- their current meaning -- the individual the government record names as
-- "requesting" the application. The new applicant_entity/applicant_contact_*
-- columns below are for when a packet separately labels an Applicant of
-- Record (e.g. a design firm) distinct from that individual.
--
-- owner_* columns are populated only when the source document explicitly
-- labels ownership (see backend.app.services.application_extractor.
-- extract_owner()) -- never inferred from the applicant. A lead with no
-- such evidence keeps owner_name = NULL, which is the correct,
-- evidence-backed state, not a missing-data bug.
--
-- Apply via the Supabase SQL editor or `supabase db push`, after
-- 0001_create_leads_table.sql.

alter table public.leads
    add column if not exists parcel_number text,
    add column if not exists acreage text,
    add column if not exists zoning text,

    add column if not exists owner_name text,
    add column if not exists owner_entity text,
    add column if not exists owner_type text,
    add column if not exists owner_contact_name text,
    add column if not exists owner_contact_email text,
    add column if not exists owner_contact_phone text,
    add column if not exists owner_website text,
    add column if not exists owner_source text,
    add column if not exists owner_confidence text,

    add column if not exists applicant_entity text,
    add column if not exists applicant_contact_name text,
    add column if not exists applicant_contact_email text,
    add column if not exists applicant_contact_phone text,
    add column if not exists applicant_source text,
    add column if not exists applicant_confidence text,

    add column if not exists parties jsonb not null default '[]'::jsonb;

create index if not exists leads_owner_name_idx
    on public.leads (owner_name);

comment on column public.leads.owner_name is
    'Property Owner / Principal display name (contact person when named, otherwise the owning entity). NULL when the source document never labels ownership -- never inferred from the applicant.';

comment on column public.leads.parties is
    'Engineer/Architect/other licensed professionals: [{party_name, party_role, party_company, party_contact_email, party_contact_phone, party_source, party_confidence}, ...].';
