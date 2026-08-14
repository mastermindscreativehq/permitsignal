-- PermitSignal Commercial Lead Intelligence (Phase 6): a deterministic
-- re-labeling of the existing lead_status/is_contactable classification
-- (0001_create_leads_table.sql) into a commercial-readiness/contactability
-- representation, plus a recommended next commercial action derived from
-- that classification and the existing approval-action intelligence
-- (0003_add_approval_action_intelligence.sql). See
-- backend.app.services.commercial_lead_intelligence.
--
-- Purely additive: no existing column is dropped, renamed, or retyped.
-- All new columns default to NULL, which is the correct, evidence-backed
-- state for a lead where commercial lead intelligence has not (yet) been
-- computed for it (e.g. a record persisted before this migration/feature
-- existed) -- NULL is never fabricated at the database layer.
--
-- Apply via the Supabase SQL editor or `supabase db push`, after
-- 0003_add_approval_action_intelligence.sql.

alter table public.leads
    add column if not exists contactability_level text,
    add column if not exists commercial_readiness text,
    add column if not exists recommended_commercial_action text,
    add column if not exists commercial_action_reason text;

create index if not exists leads_commercial_readiness_idx
    on public.leads (commercial_readiness);

comment on column public.leads.commercial_readiness is
    'Deterministic re-labeling of lead_status for a commercial audience: READY_FOR_OUTREACH | NEEDS_CONTACT_ENRICHMENT | NEEDS_MORE_PROJECT_EVIDENCE | NOT_READY. NULL only for records persisted before this feature existed -- never fabricated.';

comment on column public.leads.contactability_level is
    'How usable the already-discovered public contact evidence is: VERIFIED_PERSON_CONTACT | VERIFIED_COMPANY_CONTACT | PUBLIC_BUSINESS_CONTACT | NO_VERIFIED_CONTACT. Never inferred from a name -- only from evidence-checked contact fields.';
