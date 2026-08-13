PermitSignal Architecture

1. Purpose

PermitSignal converts public government planning/permit documents into structured commercial intelligence.

The architecture is intentionally pipeline-oriented.

The goal is not merely to extract text. The goal is to determine:

What projects/applications exist?

Who is associated with them?

What historical friction exists?

What project event happens next?

How urgent/actionable is the opportunity?

Who can be contacted using public professional/business information?

Which opportunities should enter the production lead queue?

2. High-Level Architecture

                    GOVERNMENT SOURCES
                           │
                           ▼
                  Document Downloader
                           │
                           ▼
                       PDF/Text
                           │
                           ▼
                Application Extractor
                           │
                           ▼
                Historical Friction
                    Analyzer
                           │
                           ▼
                Project Date / Event
                     Extractor
                           │
                           ▼
                 Opportunity Builder
                           │
                           ▼
                 Applicant Identity
                           │
                           ▼
                Contact Enrichment
                           │
                           ▼
                 Lead Qualification
                           │
                           ▼
                     Validation
                           │
                           ▼
                    Lead Queue
                           │
                           ▼
                permitsignal_opportunities.json
                     (always produced)
                           │
                           ▼
              Lead Persistence (Supabase)
              (optional, --sync-supabase)

3. Service Responsibilities

3.1 Document Downloader

Primary responsibility:

locate/download government documents

preserve source metadata

provide the PDF to the extraction pipeline

It should not perform applicant qualification.

3.2 Application Extractor

Primary responsibility:

Convert government packet text into structured application records.

Typical fields:

item
applicant_name
applicant_email
applicant_phone

staff_contact_name
staff_email
staff_phone

application_type
application_number
project_address
neighborhood
status

source
source_url
description

The extractor must distinguish applicants from government staff.

3.3 Friction Analyzer

Primary responsibility:

Find historical evidence associated with an application.

Examples:

denied
recommended_denial
continued

Output includes:

friction_score
friction_signals
friction_events

Each event may contain:

event_type
event_date
severity
confidence
relevance
source_page
evidence

The friction analyzer should preserve evidence so downstream users can understand why an opportunity received a score.

4. Project Date Extractor

The date extractor is responsible for identifying dates that matter to project progression.

It must distinguish:

Live project events

Examples:

public_hearing
planning_commission_event
municipal_council_event

Administrative/reference dates

Examples:

comment deadline
submission deadline
day-before-hearing date
cutoff date

Administrative dates must not become the live next_project_date.

For the current Provo packet:

2026-08-12
public_hearing
6:00 PM

is the correct next event.

The date extractor exposes functionality used by the rest of the system to:

extract dates

identify future dates

identify historical dates

select the next project event

enrich application records with date information

5. Opportunity Builder

The opportunity builder converts application/friction/date information into canonical opportunities.

It determines:

days_until_event
urgency
is_actionable
priority
priority_score
has_future_opportunity
opportunity_reason

Typical urgency classes:

URGENT
SOON
UPCOMING
HISTORICAL

Typical priorities:

HIGH
MEDIUM
LOW
ARCHIVED

The exact scoring rules already implemented in the repository are authoritative.

Do not replace them with invented scoring unless explicitly requested.

6. Applicant Identity

Applicant identity normalizes the applicant and prepares the record for enrichment.

Responsibilities include:

normalize applicant name

extract email domain

extract website domain

score email candidates

identify generic mailboxes

construct deterministic search queries

preserve government-record contact information

merge identity information into opportunities

It must never confuse:

applicant

with:

government staff contact

Status: implemented and wired into the orchestrator.

backend/app/services/applicant_identity.py exposes enrich_applicant_identity(application), a deterministic, network-free function called on every pipeline run (live enrichment enabled or not). It returns its own status under identity_status (not enrichment_status) specifically so it never collides with the separate contact-enrichment status described below.

7. Contact Enrichment

This is the next major layer.

Its purpose is to transform:

Applicant:
Jared Morgan

into, when evidence exists:

Applicant:
Jared Morgan

Company:
Example Development LLC

Website:
example.com

Professional contact:
Jared Morgan

Email:
jared@example.com

Phone:
...

Evidence:
official company website

Confidence:
HIGH

The enrichment layer should be evidence-driven.

Possible sources:

government record
official company website
official contact/team page
public business directory
public professional page
other reputable public source

No fabricated email addresses.

Status: implemented and wired into the orchestrator.

backend/app/services/applicant_enrichment.py exposes enrich_applicant_contact(application, live_search=True), called from stage 6 only when live_enrichment=True. It reports one of four enrichment_status values: enriched, not_found, disabled, failed. When live_search=False it takes a fully deterministic, network-free path that only surfaces government-record contact data. It never overrides applicant_email/applicant_phone once a government record has supplied them (pipeline_orchestrator._merge_identity enforces this precedence regardless of what enrichment returns).

8. Contact Precedence

The order is:

Government applicant contact
        ↓
Official company website
        ↓
Official team/contact page
        ↓
Public business directory
        ↓
Other reputable public source

Government-record information has precedence.

Government staff information is stored separately.

8A. Lead Intelligence

An Opportunity and a Lead are not the same thing.

An opportunity says: "something commercially interesting is happening."

A lead record says: "who is associated with it, what they are doing, how commercially interesting it is, how we can publicly contact them, why they are worth attention, and what evidence supports the record."

Status: implemented as an extension of the canonical opportunity model, not a second parallel data structure.

backend/app/services/opportunity_builder.py's Opportunity dataclass carries the full lead schema (identity, project, friction, project event, contact, contact evidence, enrichment, and opportunity fields) with explicit null defaults, so every produced record has a complete, consistent shape even when no contact evidence exists yet.

qualify_lead(opportunity) is a pure, additive function that reads the already-computed priority/is_actionable/has_future_opportunity/contact fields and adds two fields without altering anything else:

lead_status: one of ARCHIVED, NEW, NO_CONTACT, QUALIFIED, CONTACTABLE

is_contactable: true only when legitimate public contact evidence (a named professional email, a generic company email, or a phone number) is already present

Precedence used by classify_lead_status():

no future project event -> ARCHIVED

future event exists but priority/actionability do not meet the bar -> NEW

meets the bar, no contact evidence -> NO_CONTACT

meets the bar, generic mailbox only (info@, contact@, ...) -> QUALIFIED

meets the bar, named professional email or a phone number -> CONTACTABLE

This does not replace or duplicate the opportunity priority engine; priority/priority_score remain authoritative for the queue's sort order. pipeline_orchestrator._qualify_leads() calls qualify_lead() once per opportunity between stage 6 (applicant identity/enrichment) and stage 7 (validate/sort) and never changes existing field values.

9. Pipeline Orchestrator

The orchestrator coordinates services.

Current logical stages:

[1/7] Reading government packet
[2/7] Extracting applications
[3/7] Analyzing historical friction
[4/7] Extracting future project dates
[5/7] Building canonical opportunities
[6/7] Applying applicant identity and enrichment
[7/7] Validating and sorting production queue

The orchestrator should coordinate services rather than duplicate their internal logic.

For example:

orchestrator
    calls
application_extractor
    calls
friction analyzer
    calls
project_date_extractor
    calls
opportunity_builder
    calls
applicant identity/enrichment

Do not put large extraction algorithms directly into the orchestrator.

10. Canonical Data Flow

A typical application starts as:

raw PDF text

becomes:

application

then:

friction-enriched application

then:

date-enriched application

then:

canonical opportunity

then:

identity/contact-enriched opportunity

then:

qualified lead (lead_status / is_contactable attached)

then:

validated lead

then, optionally:

persisted Supabase row

11. Production Output

The pipeline writes:

data/output/permitsignal_opportunities.json

The output contains:

applications
opportunities
lead_queue

The lead queue is sorted according to the opportunity engine.

This JSON file is the pipeline's primary, always-produced artifact. It is written on every run regardless of whether Supabase persistence is enabled -- see section 11A.

11A. Lead Persistence (Supabase)

Status: implemented as an additive compatibility layer, not a replacement for the JSON output.

backend/app/services/lead_repository.py exposes upsert_leads(leads), which upserts canonical lead records into a Supabase "leads" table keyed on application_number (see supabase/migrations/0001_create_leads_table.sql for the schema). Every column not promoted to its own indexed field is still preserved verbatim in a JSONB "record" column, so the row is never a lossy projection of the lead.

pipeline_orchestrator.run_pipeline(sync_to_supabase=False) controls this layer (CLI: --sync-supabase). The default is False, so:

the JSON output is byte-for-byte unaffected by this feature (verified: running with and without --sync-supabase against the real Provo packet produces identical applications/opportunities/lead_queue, aside from the pipeline's pre-existing per-run created_at timestamp)

metadata["supabase_sync"] always reports one of: disabled, skipped (not configured, or no application_number), synced, error

a missing SUPABASE_URL/SUPABASE_KEY, or a genuine Supabase/network failure, is recorded in metadata["supabase_sync"] and never raises out of the pipeline -- the JSON artifact is still produced

Confidence fields (email_confidence, phone_confidence, contact_confidence) are stored as TEXT columns in Supabase, matching the existing mixed HIGH/MEDIUM/LOW-vs-numeric convention already documented in DEVELOPMENT_RULES.md section 11, rather than forcing a new normalized scoring model.

12. Current Verified Example

The current Provo packet has eight applications.

The top two opportunities are:

PLRZ20260264
Jared Morgan
Zone Map Amendment
HIGH
180
2026-08-12

and:

PLCP20260261
Jared Morgan
Concept Plan
HIGH
180
2026-08-12

Historical friction explains the high priority.

Verified end to end against the real Provo packet (data/documents/_08122026-415.pdf, reference date 2026-08-01):

- 8 applications, 8 opportunities, 8 future opportunities
- Jared Morgan remains HIGH / 180 on both PLRZ20260264 and PLCP20260261
- next_project_date = 2026-08-12, next_project_event = public_hearing, next_project_time = 6:00 PM
- applicant/staff contact separation holds (e.g. Tyson Reynolds / staff Dustin Wright dwright@provo.gov never merge)
- no fabricated applicant_email/applicant_phone appears anywhere in the output
- scripts/test_pipeline_orchestrator.py: 48/48 checks passed, covering deduplication, friction integration, date-adapter historical-date safety, priority sorting, applicant identity/contact-enrichment orchestration (staff separation + government-record precedence), full mocked-pipeline structural integrity, lead-intelligence field presence, and the real-PDF invariants above (including that the top of the lead queue stays PLRZ20260264 then PLCP20260261, both HIGH/180, after lead qualification runs).
- scripts/test_opportunity_builder.py: 64/64 checks passed, including opportunity-to-lead conversion, contactable/no-contact/qualified/archived lead-status boundaries, and no-fabrication checks on qualify_lead().
- scripts/test_lead_repository.py: 20/20 checks passed, covering configuration detection, lead-to-row mapping (including that fields without an evidence value are never fabricated and that fields not promoted to a column still survive in the JSONB record), upsert behavior against a fake Supabase client, and the RuntimeError raised by get_client() when unconfigured.
- scripts/test_pipeline_orchestrator.py section [10/10]: 6/6 checks passed, covering the disabled/skipped/synced/error status states of _persist_leads() and confirming the JSON output container shape is unaffected by the persistence feature.
- With live_enrichment disabled (the production default) and no government-record contact present in the Provo packet, all 8 real opportunities currently classify as lead_status = NO_CONTACT with is_contactable = False -- an honest reflection of the evidence available, not a gap in the qualification logic.

13. Future Architecture

Lead Qualification (see section 8A) and Lead Persistence (see section 11A) are implemented. The remaining forward path is:

Persisted Lead (Supabase)
    ↓
CRM/Database sync
    ↓
Outreach Personalization
    ↓
Email/CRM Automation
    ↓
Response Tracking
    ↓
Opportunity Feedback

The intelligence pipeline should remain separate from the outreach execution layer.

This separation makes the system easier to test, replace, and scale.

14. Architectural Rule

Every service should have one clear responsibility.

Avoid creating a giant "do everything" service.

Preferred:

application_extractor
friction_analyzer
project_date_extractor
opportunity_builder
applicant_identity
applicant_enrichment
lead_repository
pipeline_orchestrator

rather than one giant script.

lead_repository owns Supabase persistence exclusively. It must never be responsible for identity/contact discovery, scoring, or qualification -- it only maps an already-canonical lead dict to a database row and upserts it.

The orchestrator coordinates.

The services perform the specialized work.