-- PermitSignal Approval-Action Intelligence (Phase 3): a conservative,
-- evidence-first recommendation of what appears to be happening with the
-- approval process and what action is relevant next, derived entirely
-- from evidence already captured by friction analysis (friction_events),
-- the current agenda status, and scheduled project dates -- never a new
-- extraction pass and never a fabricated requirement/permit/deadline. See
-- backend.app.services.approval_action_intelligence.
--
-- Purely additive: no existing column is dropped, renamed, or retyped.
-- All new columns default to NULL, which is the correct, evidence-backed
-- state for a lead where approval-action intelligence has not (yet) been
-- computed for it (e.g. a record persisted before this migration/feature
-- existed) -- NULL is never fabricated at the database layer; the literal
-- string 'unknown' is only ever written by approval_action_intelligence
-- itself, when it genuinely finds insufficient evidence.
--
-- approval_relevant_date is TEXT rather than DATE: its source value can
-- come from either a friction event's event_date or a project date's
-- value, and friction_analyzer.normalize_date() falls back to returning
-- the raw matched string unchanged when it cannot parse a date -- storing
-- as TEXT avoids a insert failure on that rare malformed input, the same
-- reasoning applied to next_project_date's sibling text-typed columns.
--
-- Apply via the Supabase SQL editor or `supabase db push`, after
-- 0002_add_party_roles.sql.

alter table public.leads
    add column if not exists approval_status text,
    add column if not exists approval_action text,
    add column if not exists approval_action_type text,
    add column if not exists approval_confidence text,
    add column if not exists approval_basis text,
    add column if not exists approval_relevant_date text,
    add column if not exists approval_source text,
    add column if not exists approval_source_type text,
    add column if not exists approval_evidence text,
    add column if not exists approval_reason text;

create index if not exists leads_approval_status_idx
    on public.leads (approval_status);

comment on column public.leads.approval_status is
    'Conservative approval-process status derived from friction/date evidence (e.g. denied, withdrawn, continued, tabled, under_review, scheduled, pending, recommended_denial, unknown). NULL only for records persisted before this feature existed -- never fabricated.';

comment on column public.leads.approval_basis is
    'How approval_action was derived: confirmed_requirement | evidence_backed_recommendation | inferred_next_step | unknown. Never presents an inferred action as a confirmed government requirement.';
