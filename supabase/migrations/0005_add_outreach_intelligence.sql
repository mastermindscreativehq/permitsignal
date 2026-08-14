-- PermitSignal Outreach & Monetization Intelligence (Phase 8): the
-- controlled lead lifecycle (outreach_status), the selected outreach
-- target and channel, a personalized message draft, and follow-up
-- tracking layered on top of the existing commercial-readiness
-- classification (0004_add_commercial_lead_intelligence.sql). See
-- backend.app.services.outreach_intelligence.
--
-- Purely additive: no existing column is dropped, renamed, or retyped.
-- outreach_status defaults to 'NEW' (the correct starting state for any
-- lead, including rows persisted before this migration/feature existed --
-- their outreach lifecycle simply has not started yet, which is not a
-- fabricated claim). Every other new column defaults to NULL/false, which
-- is the correct, evidence-backed "not yet computed" state.
--
-- outreach_contact_type/outreach_contact_reason never duplicate the
-- underlying contact fields (owner_contact_*, applicant_email/phone,
-- applicant_contact_*, contact_email/phone) already added by
-- 0001/0002_*.sql -- they only record WHICH of those existing parties was
-- selected as the outreach target and why.
--
-- outreach_status also serves as the commercial/revenue status (Phase 8
-- requirement 10 -- Monetization): READY_FOR_OUTREACH is the point a
-- qualified lead becomes sellable (PermitSignal's existing case-report
-- PDF, see backend.app.services.case_report_generator, is the
-- deliverable); OPPORTUNITY/WON/LOST track the resulting deal outcome.
-- No separate monetization/commercial_status column is introduced.
--
-- Apply via the Supabase SQL editor or `supabase db push`, after
-- 0004_add_commercial_lead_intelligence.sql.

alter table public.leads
    add column if not exists outreach_status text not null default 'NEW',
    add column if not exists outreach_qualification_status text,
    add column if not exists outreach_channel text,
    add column if not exists outreach_contact_type text,
    add column if not exists outreach_contact_reason text,
    add column if not exists outreach_message_subject text,
    add column if not exists outreach_message_body text,
    add column if not exists follow_up_required boolean not null default false,
    add column if not exists follow_up_reason text,
    add column if not exists last_outreach_at timestamptz,
    add column if not exists outreach_events jsonb not null default '[]'::jsonb;

create index if not exists leads_outreach_status_idx
    on public.leads (outreach_status);

create index if not exists leads_outreach_qualification_status_idx
    on public.leads (outreach_qualification_status);

comment on column public.leads.outreach_status is
    'Controlled lead lifecycle: NEW | QUALIFIED | READY_FOR_OUTREACH | CONTACTED | REPLIED | ENGAGED | OPPORTUNITY | WON | LOST. NEW/QUALIFIED/READY_FOR_OUTREACH are recomputed every pipeline run from commercial_readiness; CONTACTED and beyond only change via an explicit outreach_intelligence.apply_outreach_event() call -- never reset by a pipeline rerun.';

comment on column public.leads.outreach_qualification_status is
    'QUALIFIED_NOT_CONTACTABLE | QUALIFIED_READY_FOR_OUTREACH | ALREADY_CONTACTED | ACTIVE_COMMERCIAL_OPPORTUNITY | NOT_QUALIFIED -- a re-labeling of commercial_readiness + outreach_status, never a second scoring model.';

comment on column public.leads.outreach_contact_type is
    'Which already-identified party (owner | applicant | applicant_of_record | company | none) is the appropriate outreach target -- never a new contact record.';

comment on column public.leads.outreach_events is
    'Append-only history of controlled outreach lifecycle events: [{event, note, occurred_at, previous_status, resulting_status}, ...]. Written only by outreach_intelligence.apply_outreach_event().';
