PermitSignal — Claude Project Instructions

1. Project Identity

PermitSignal is a government planning/permit intelligence system.

Its purpose is to turn public government planning documents into structured, actionable business opportunities.

The system currently processes government planning packets/PDFs and produces:

normalized applications

applicant identity information

historical friction intelligence

future project-event intelligence

opportunity scores

applicant/contact enrichment

a production lead queue

JSON output for downstream systems

The project is being built as a production intelligence pipeline, not as a one-off PDF parser.

2. Current Production Pipeline

The canonical pipeline is:

Government PDF
    ↓
Document/Text Extraction
    ↓
Application Extraction
    ↓
Historical Friction Analysis
    ↓
Project Date / Event Extraction
    ↓
Opportunity Builder
    ↓
Applicant Identity
    ↓
Applicant / Contact Enrichment
    ↓
Validation
    ↓
Priority Sorting
    ↓
Production Lead Queue
    ↓
JSON Output

The production orchestrator currently reports seven stages:

[1/7] Reading government packet
[2/7] Extracting applications
[3/7] Analyzing historical friction
[4/7] Extracting future project dates
[5/7] Building canonical opportunities
[6/7] Applying applicant identity and enrichment
[7/7] Validating and sorting production queue

Do not change this architecture casually.

3. Current Services

The primary service directory is:

backend/app/services/

Known services include:

applicant_enrichment.py
applicant_identity.py
document_downloader.py
opportunity_builder.py
pipeline_orchestrator.py
project_date_extractor.py
__init__.py

The application extraction and friction analysis components are also part of the working system and are imported by the pipeline. Before modifying imports or moving files, inspect the actual repository structure.

The test directory is:

scripts/

Known tests include:

test_applicant_enrichment.py
test_applicant_identity.py
test_application_extractor.py
test_document_pipeline.py
test_friction_analyzer.py
test_opportunity_builder.py
test_pipeline_orchestrator.py
test_playwright.py
test_project_date_extractor.py

4. Current Verified Capabilities

The following components have already been tested successfully.

Application extraction

The system can extract applications from the Provo Planning Commission government packet, including:

applicant

applicant email when present in the government record

applicant phone when present

staff contact

staff email

staff phone

application type

application number

project address

neighborhood

status

source

source URL

description

Friction analysis

The system detects historical friction signals such as:

denied

recommended_denial

continued

It produces:

friction score

friction signals

historical evidence events

event dates

severity

confidence

relevance

evidence text

Project date extraction

The date extractor distinguishes project events from administrative/deadline dates.

A critical bug involving an August 11 administrative deadline has already been fixed.

For the current Provo packet:

2026-08-12 | public_hearing | 6:00 PM

is the correct next project event.

Do not regress this behavior.

Opportunity builder

The system calculates:

days until event

urgency

actionability

priority

priority score

human-readable opportunity reason

Applicant identity

The system handles:

applicant normalization

email domain extraction

website/domain extraction

email candidate scoring

generic mailbox detection

search query construction

government-record contact precedence

canonical opportunity merging

Pipeline

The production pipeline currently completes successfully against the Provo packet.

A verified run has produced:

Applications:         8
Opportunities:        8
Future opportunities: 8

The lead queue currently ranks:

01 HIGH   | PLRZ20260264 | Jared Morgan | Zone Map Amendment | SCORE=180 | DATE=2026-08-12
02 HIGH   | PLCP20260261 | Jared Morgan | Concept Plan      | SCORE=180 | DATE=2026-08-12
03 MEDIUM | PLVAR20260373 | Kevin Jimenez | Variance          | SCORE=80  | DATE=2026-08-12
04 MEDIUM | PLOTA20260371 | Development Services | Ordinance Text Amendment | SCORE=60 | DATE=2026-08-12
05 MEDIUM | PLRZ20260116 | Tyson Reynolds | Zone Map Amendment | SCORE=60 | DATE=2026-08-12
06 MEDIUM | PLCP20260117 | Tyson Reynolds | Concept Plan | SCORE=60 | DATE=2026-08-12
07 MEDIUM | PLOTA20260414 | Development Services | Ordinance Text Amendment | SCORE=60 | DATE=2026-08-12
08 MEDIUM | PLPPA20250700 | Bret Nelson | Project Plan | SCORE=60 | DATE=2026-08-12

5. Current Development Objective

The next major objective is:

CONTACT ENRICHMENT

PermitSignal needs to turn an applicant into a commercially useful intelligence record.

Target progression:

Applicant
    ↓
Company
    ↓
Professional Role
    ↓
Public Contact Information
    ↓
Evidence
    ↓
Confidence
    ↓
Lead Qualification
    ↓
Outreach-ready Lead

Important contact fields include:

applicant_email
applicant_phone
company_name
company_website
company_domain
contact_name
contact_role
contact_email
contact_phone
linkedin_url
email_source
phone_source
company_source
contact_source
email_confidence
phone_confidence
contact_confidence
enrichment_status
enrichment_method
contact_is_public
contact_is_verified

6. Contact Integrity Rules

Never fabricate an applicant or professional email.

Do NOT infer:

john.smith@company.com

from a person's name unless that exact address is independently found in a public source.

If no email is found:

applicant_email = None

is correct.

Evidence-backed None is better than fabricated data.

Contact precedence

Use this order:

Government-record applicant email

Government-record applicant phone

Official applicant/company website

Official company contact/team page

Public professional/business directory

Other reputable public business source

Government-record contact information must not be overwritten by lower-confidence enrichment.

7. Staff Contact Separation

Government staff are not applicants.

For example:

Applicant:
Tyson Reynolds

Staff:
Dustin Wright
dwright@provo.gov

must remain:

applicant_name = Tyson Reynolds
applicant_email = None

staff_contact_name = Dustin Wright
staff_email = dwright@provo.gov

Never assign a staff email to the applicant.

8. Public Contact Policy

Contact enrichment should use publicly available professional/business information.

The system should prefer:

official company websites

official team/contact pages

public business directories

public professional pages

other reputable public sources

Do not attempt to obtain:

private/non-public contact data

credentials

restricted personal information

information behind access controls

The goal is legitimate business intelligence.

9. Editing Rules

Before modifying a file:

Inspect the existing implementation.

Understand its public functions.

Inspect the tests.

Preserve compatible APIs.

Make the smallest change that solves the requirement.

Never replace a large working implementation with a shortened approximation.

Never create a "simplified" replacement just because the existing file is long.

Never delete existing functionality without explicit authorization.

Do not modify unrelated services while fixing one component.

Do not change the project-date logic unless the requested task specifically concerns dates.

10. Testing Rules

Run the existing relevant test before and after modifications.

For pipeline changes, use the real Provo PDF whenever possible.

Production command:

python -m backend.app.services.pipeline_orchestrator --reference-date 2026-08-01

Project date test:

python -m scripts.test_project_date_extractor

Application extraction test:

python -m scripts.test_application_extractor

Friction test:

python -m scripts.test_friction_analyzer

Opportunity test:

python -m scripts.test_opportunity_builder

Applicant identity test:

python -m scripts.test_applicant_identity

Applicant enrichment test:

python -m scripts.test_applicant_enrichment

Pipeline test:

python -m scripts.test_pipeline_orchestrator

11. Production Output

The production result is saved to:

data/output/permitsignal_opportunities.json

Do not assume a sandbox path or invent an output file.

Inspect the actual generated file when validating integration.

12. Date Safety

This is a critical invariant.

A future date is not automatically a future project event.

Administrative dates such as:

public comment deadlines

submission deadlines

cutoff dates

day-before-hearing dates

must not become next_project_date.

For the current Provo packet:

August 11, 2026

must not replace:

August 12, 2026

The correct live event is:

next_project_date = 2026-08-12
next_project_event = public_hearing
next_project_time = 6:00 PM

13. Working Style

When asked to implement something:

Inspect first.

State what is already working.

Identify the exact change.

Implement only what is necessary.

Run tests.

Run integration tests.

Report exact results.

Do not repeatedly ask the user to recreate information already present in the repository.

Do not claim a file is complete without checking its actual contents/line count when the user specifically asks for a complete file.

14. Architecture Principle

PermitSignal is being built as an intelligence machine.

The system should progressively transform:

Raw government documents

into:

Structured applications
→ historical context
→ future events
→ opportunity scores
→ applicant identity
→ verified public contact intelligence
→ qualified business leads

Optimize for:

reliability

evidence

repeatability

explainability

scalability

clean interfaces between services

Do not optimize for code brevity at the expense of existing functionality.