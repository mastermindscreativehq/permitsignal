PermitSignal Development Rules

1. Core Rule

PermitSignal is a working production intelligence pipeline.

The default behavior is:

Preserve working functionality and make the smallest safe change required.

Do not rewrite functioning components merely because they can be written more simply.

2. Never Replace Large Working Files With Short Approximations

This is a hard rule.

If an existing service contains hundreds of lines of working logic:

DO NOT

replace it with a short "equivalent" implementation without explicit authorization.

Before editing a large file:

inspect it

understand its functions

preserve its APIs

patch the required section

run tests

If the user asks for a complete file, verify the complete file actually contains the existing implementation.

3. Inspect Before Editing

Before making a change:

1. Find the target file.
2. Read the current implementation.
3. Read the relevant tests.
4. Identify dependencies.
5. Identify callers.
6. Identify public function signatures.
7. Determine the smallest safe patch.

Never assume a file is missing because an import fails.

Inspect the repository first.

4. Preserve Public APIs

Do not casually change:

function names
parameter order
return structures
dictionary field names
module paths

The pipeline depends on service interfaces.

If an API must change:

identify all callers

update callers deliberately

update tests

run integration tests

5. Do Not Duplicate Business Logic

The orchestrator should coordinate.

It should not contain a second implementation of:

application extraction

friction analysis

date extraction

opportunity scoring

contact extraction

Specialized services own specialized logic.

6. Date Integrity

This is a critical invariant.

Never turn an administrative deadline into a project event.

Examples:

comment deadline
submission deadline
day-before-hearing
cutoff
response deadline

must not become:

next_project_date

For the current Provo packet:

2026-08-11

must not replace:

2026-08-12

Correct:

next_project_date = 2026-08-12
next_project_event = public_hearing
next_project_time = 6:00 PM

7. Applicant vs Staff

Never confuse:

applicant

with:

government staff

If the government packet says:

Applicant: Tyson Reynolds
Staff: Dustin Wright
Staff Email: dwright@provo.gov

then:

applicant_name = Tyson Reynolds
applicant_email = null

staff_contact_name = Dustin Wright
staff_email = dwright@provo.gov

Staff data must remain separate.

8. Contact Enrichment Integrity

Contact enrichment must be evidence-driven.

Allowed:

public official company website
public company team page
public business directory
public professional page
government record

Not allowed:

guessing email patterns
inventing phone numbers
inventing companies
inventing job titles
inventing LinkedIn URLs

If evidence is missing:

null

is correct.

9. Government Contact Precedence

If an applicant email is explicitly present in the government record:

government_record

has priority over external discovery.

External enrichment must not overwrite it.

Likewise for government-record applicant phone numbers.

10. Email Quality Rules

Extract:

normal emails
mailto links
HTML email text
common public obfuscations

Examples:

name [at] domain [dot] com
name(at)domain.com
name @ domain . com

Normalize the result.

Reject:

malformed emails
placeholder addresses
test addresses

For human-contact discovery, distinguish generic mailboxes:

info@
contact@
office@
sales@
hello@
admin@

from named addresses.

Generic mailboxes can still be retained as useful business contacts.

11. Confidence Rules

Every externally discovered contact should have a confidence level.

Possible values:

HIGH
MEDIUM
LOW

or the project's existing numeric confidence model.

Do not claim "verified" merely because a search result exists.

Verification should mean the source directly supports the association.

12. Source Evidence

Store source metadata whenever possible.

For example:

email_source = official_company_website
contact_source = official_company_team_page
email_confidence = 0.95

The source should be traceable enough for a reviewer to understand why the value was accepted.

13. Live Enrichment

The pipeline supports:

Live enrichment: False

When disabled:

do not perform live discovery

perform deterministic extraction where available

preserve government-record contacts

do not invent data

return an explicit disabled/not-run status

When enabled:

use controlled public-source discovery

limit searches

preserve source evidence

cache where appropriate

avoid unnecessary requests

Status: implemented.

pipeline_orchestrator._enrich_applicants() calls applicant_identity.enrich_applicant_identity() unconditionally (deterministic, no network) and only calls applicant_enrichment.enrich_applicant_contact() when live_enrichment=True. When disabled, every opportunity receives an explicit enrichment_status = "disabled". Government-record applicant_email/applicant_phone are reasserted after enrichment runs, so a live-search failure or a lower-confidence public-web result can never overwrite them.

14. Testing

A change is not complete merely because the code imports.

Run:

python -m scripts.test_project_date_extractor

for date changes.

Run:

python -m scripts.test_application_extractor

for application extraction.

Run:

python -m scripts.test_friction_analyzer

for friction changes.

Run:

python -m scripts.test_opportunity_builder

for opportunity changes.

Run:

python -m scripts.test_applicant_identity

for identity changes.

Run:

python -m scripts.test_applicant_enrichment

for enrichment changes.

Run:

python -m scripts.test_pipeline_orchestrator

for orchestration changes.

Run:

python -m scripts.test_lead_repository

for Supabase lead-persistence changes. This test is network-free: it checks configuration detection and lead-to-row mapping directly, and exercises upsert_leads() against a fake Supabase client, never a real one.

For production validation:

python -m backend.app.services.pipeline_orchestrator --reference-date 2026-08-01

To additionally persist leads to Supabase (requires SUPABASE_URL and SUPABASE_KEY, and that supabase/migrations/0001_create_leads_table.sql has already been applied):

python -m backend.app.services.pipeline_orchestrator --reference-date 2026-08-01 --sync-supabase

15. Real-PDF Validation

Unit tests are necessary but insufficient.

When possible, validate against:

data/documents/_08122026-415.pdf

because the real government packet exposed bugs that a synthetic unit-test string did not.

The production pipeline must be tested against the real packet after significant changes.

16. Regression Protection

Known invariant:

August 11 administrative date

must not become the live project event.

Expected:

August 12, 2026
public_hearing
6:00 PM

Any change that causes the system to output:

2026-08-11

as the next project event is a regression.

scripts/test_pipeline_orchestrator.py verifies this invariant directly against pipeline_orchestrator._adapt_dates() (a historical date must be cleared from next_project_date/next_project_event/next_project_time/has_future_opportunity) and against the real Provo packet output. As of the last verified run: 43/43 checks passed, and the real pipeline produced next_project_date=2026-08-12 / public_hearing / 6:00 PM with 8 applications, 8 opportunities, 8 future opportunities, and Jared Morgan HIGH/180 on both PLRZ20260264 and PLCP20260261.

17. Output Validation

Production output:

data/output/permitsignal_opportunities.json

must contain:

applications
opportunities
lead_queue

Every production opportunity should retain its:

application_number
applicant_name
application_type
project_address

when those fields were available from the source.

18. Opportunity Integrity

The priority engine combines:

friction
future project event
actionability
urgency

Do not manually override priority in the orchestrator.

The opportunity builder owns the scoring logic.

18A. Lead Qualification Integrity

qualify_lead() (opportunity_builder.py) and pipeline_orchestrator._qualify_leads() are purely additive.

They may only add/overwrite two fields: lead_status and is_contactable.

They must never touch application_number, applicant_name, friction_score, friction_signals, friction_events, next_project_date/event/time, has_future_opportunity, priority, or priority_score.

lead_status is derived entirely from fields the opportunity builder and applicant identity/enrichment stages already computed. It does not introduce a second scoring model.

is_contactable must be false whenever no applicant_email/applicant_phone/contact_email/contact_phone is present. A record can never be marked contactable without a corresponding, already-evidence-checked contact value.

Status: implemented. Do not add a parallel Lead dataclass -- the canonical Opportunity dataclass in opportunity_builder.py already carries the full lead schema (contact/company/identity/enrichment fields with explicit null defaults, plus lead_status/is_contactable).

18B. Lead Persistence Integrity (Supabase)

data/output/permitsignal_opportunities.json is the pipeline's primary artifact. It must be produced on every run regardless of Supabase configuration or availability -- this is the "compatibility layer" guarantee.

pipeline_orchestrator._persist_leads() must never raise. A missing SUPABASE_URL/SUPABASE_KEY, a network failure, or any other exception from lead_repository must be caught and recorded as metadata["supabase_sync"] = {"status": "error", "error": "..."}, never allowed to abort run_pipeline()/run_and_save().

sync_to_supabase defaults to False everywhere (run_pipeline, run_and_save, the CLI). Enabling it must not change any field in applications/opportunities/lead_queue -- verified by running the real Provo packet both with and without --sync-supabase and diffing the output (identical aside from the pipeline's own pre-existing per-run created_at timestamp).

lead_repository.upsert_leads() must never assign a fabricated application_number to a record that lacks one -- such records are skipped and counted, not silently dropped or invented.

Do not run schema DDL from application code. supabase/migrations/0001_create_leads_table.sql must be applied once via the Supabase SQL editor or `supabase db push` before sync_to_supabase=True can succeed.

Status: implemented. backend/app/services/lead_repository.py is the only module permitted to talk to Supabase; pipeline_orchestrator only calls upsert_leads() through the same _import_service()/_first_callable() dispatch pattern used for every other service boundary.

19. Dependency Discipline

Do not install a large dependency for a simple operation.

Prefer existing dependencies.

Before adding a package:

check whether an existing dependency solves the problem

determine whether the package is actually required

add it deliberately

update requirements if appropriate

test the environment

20. File Placement

Services belong under:

backend/app/services/

Tests belong under:

scripts/

Database schema/migrations belong under:

supabase/migrations/

Do not scatter business logic into arbitrary directories.

requirements.txt already includes supabase, postgrest, supabase-auth, and supabase-functions. Lead persistence did not require adding a new dependency.

21. Documentation Discipline

After a major architectural change:

Update the relevant documentation.

At minimum, consider:

CLAUDE.md
docs/ARCHITECTURE.md
docs/DATA_MODEL.md
docs/DEVELOPMENT_RULES.md

Do not create documentation that contradicts the actual code.

Documentation should describe what exists, not what we merely intend to build.

22. Change Isolation

If fixing:

project_date_extractor.py

do not simultaneously rewrite:

opportunity_builder.py
applicant_enrichment.py
pipeline_orchestrator.py

unless the dependency requires it.

Small changes are easier to test and roll back.

23. Error Handling

Errors should be explicit.

Do not silently swallow failures that could corrupt lead data.

A failed enrichment should produce something like:

enrichment_status = failed

rather than pretending the applicant has no contact information.

Distinguish:

disabled
not_found
enriched
failed

where the existing model supports those states.

24. No Fake Success

Never report:

SUCCESS

unless the relevant test or operation actually completed successfully.

If a test failed:

1 failed

means the work is not finished.

If only unit tests pass but the real PDF integration fails, the feature is not finished.

25. Production Mindset

PermitSignal is intended to become a repeatable intelligence system.

Optimize for:

Evidence
Reliability
Repeatability
Traceability
Scalability

not merely:

"the script runs"

26. Preferred Development Loop

Use this cycle:

Inspect
  ↓
Plan
  ↓
Patch
  ↓
Unit Test
  ↓
Integration Test
  ↓
Real PDF Test
  ↓
Inspect Output
  ↓
Document

Do not skip the output inspection step for pipeline changes.

27. Final Rule

The most important rule:

Do not break a working system to make one new feature easier to implement.

Extend the existing architecture.

Preserve working behavior.

Test every change.

Use evidence instead of assumptions.