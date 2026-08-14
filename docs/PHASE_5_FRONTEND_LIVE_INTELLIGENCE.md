# PermitSignal — Phase 5: Frontend Live Intelligence

## Objective

Connect the existing PermitSignal frontend/dashboard to the live intelligence already produced by the Python backend, API, and Supabase.

The frontend must consume real PermitSignal data rather than static/mock data.

---

## Existing System

Phases 1–4 are complete.

The Python system already provides:

- live government discovery
- document ingestion
- PDF extraction
- application extraction
- applicant/company enrichment
- owner/person enrichment
- opportunity generation
- approval-action intelligence
- lead qualification
- Supabase persistence
- API access to the complete lead/intelligence record

Phase 4 exposes:

- `GET /leads`
- `GET /leads/{application_number}`

These endpoints expose the existing intelligence record including project/application, applicant/company, owner/person, parties, friction, approval-action intelligence, priority and lead/opportunity data.

---

## Phase 5 Goal

Make the frontend a live intelligence interface for PermitSignal.

The frontend should allow a user to:

1. See the current qualified lead queue.
2. See which opportunities deserve attention first.
3. Open an individual lead.
4. See the complete intelligence for that project.
5. See applicant/company information.
6. See owner/person information when evidence exists.
7. See friction/problem signals.
8. See approval-action intelligence.
9. See the recommended next action.
10. See evidence/source information supporting the intelligence.

---

## Critical Rule

Do NOT rebuild the Python intelligence system.

Do NOT move Python intelligence into the frontend.

Do NOT replace the existing API with another architecture.

Do NOT create fake/mock intelligence to make the interface appear functional.

The frontend is a consumer of the existing PermitSignal intelligence.

---

## Step 1 — Audit Existing Frontend

Inspect the existing `dashboard/` directory and determine exactly what frontend/dashboard code already exists.

Determine:

- framework
- entry points
- routes/pages
- components
- existing API calls
- existing data models
- existing mock/static data
- current dashboard functionality
- current styling
- current build/run method

If `dashboard/` contains an existing frontend, extend it.

If the frontend is incomplete, preserve what exists and implement only what is required for Phase 5.

If there is no usable frontend implementation, document that fact before making architectural decisions.

Do not assume a frontend framework that is not present in the repository.

---

## Step 2 — Connect to Existing API

Use the existing Phase 4 API.

Primary endpoints:

- `GET /leads`
- `GET /leads/{application_number}`

Determine the correct production/base API URL from the existing project configuration.

Do not hardcode production secrets.

Use environment configuration where appropriate.

---

## Step 3 — Live Lead Queue

The main dashboard should consume `GET /leads`.

Display the qualified opportunities using the data already produced by PermitSignal.

The lead queue should make the following useful information visible where available:

- application number
- project/application identity
- applicant/company
- owner/person
- location
- priority
- priority score
- friction score/signals
- approval status
- approval action
- approval action type
- approval confidence
- recommended next step
- relevant project dates

Do not invent values when a field is unavailable.

---

## Step 4 — Lead Detail View

Selecting a lead should retrieve:

`GET /leads/{application_number}`

The detail view should present the complete intelligence record in a clear structure.

Organize information into logical sections such as:

### Project

- application/project identity
- application number
- project type
- location
- relevant dates

### Applicant / Company

- applicant name
- company information
- available contact information
- source/evidence where available

### Owner / Person

- owner/person name
- professional role
- relationship to applicant/project
- confidence
- evidence/source

Only display identity information supported by the backend evidence.

### Parties

Display discovered parties and their roles when available.

### Friction Intelligence

Display:

- friction score
- friction signals
- friction events
- supporting evidence

### Approval-Action Intelligence

Display:

- approval status
- recommended approval action
- approval action type
- approval confidence
- approval basis
- confirmed requirement
- evidence-backed recommendation
- inferred next step
- relevant date/source/evidence/reason

### Opportunity / Lead

Display the existing:

- opportunity
- lead qualification
- priority
- priority score
- recommended action

Do not create a second scoring system in the frontend.

---

## Step 5 — Evidence and Source Transparency

Where the API provides source information, expose it in the interface.

Users must be able to understand why PermitSignal produced an intelligence result.

Do not fabricate evidence.

Do not display unsupported owner/person identities.

Do not convert uncertain information into definitive claims.

---

## Step 6 — Loading, Empty and Error States

Implement proper states for:

- loading lead queue
- loading lead detail
- no leads
- lead not found
- API unavailable
- malformed API response
- empty optional intelligence fields

The application must fail gracefully rather than displaying misleading information.

---

## Step 7 — Preserve Existing Architecture

Do not modify:

- discovery architecture
- document ingestion
- extraction logic
- enrichment logic
- approval-action intelligence
- lead scoring
- Supabase schema
- n8n workflow
- outreach/monetization system

unless a frontend integration change is strictly required.

If an API deficiency is discovered, document it and make the smallest additive change necessary.

---

## Step 8 — Real Data Verification

Verify the frontend against real PermitSignal data.

Use the known-good Provo production data already used during previous phases.

Confirm:

- lead queue loads
- individual lead loads
- applicant/company data appears correctly
- owner/person data appears correctly when available
- friction intelligence appears correctly
- approval-action intelligence appears correctly
- priority ordering is preserved
- no intelligence is fabricated
- API errors are handled correctly

---

## Out of Scope

Do NOT:

- build n8n automation
- build scraping/discovery automation
- build outreach automation
- build monetization
- redesign the Python intelligence pipeline
- rebuild Supabase
- create a new intelligence engine
- change Phase 3 approval-action rules
- change Phase 2 enrichment rules
- invent missing intelligence in the frontend
- add unrelated product features

---

## Completion Criteria

Phase 5 is complete only when:

1. The existing frontend/dashboard has been audited.
2. The existing frontend is connected to the Phase 4 API.
3. `GET /leads` powers the live lead queue.
4. `GET /leads/{application_number}` powers the lead detail view.
5. Real PermitSignal data is displayed.
6. Applicant/company intelligence is visible.
7. Owner/person intelligence is visible when supported by evidence.
8. Friction intelligence is visible.
9. Approval-action intelligence is visible.
10. Priority and lead information are preserved.
11. Evidence/source information is preserved where available.
12. Loading, empty and error states work.
13. Real Provo data has been verified through the frontend.
14. No existing intelligence logic was duplicated or rewritten.
15. No Phase 6 or later work was introduced.

---

## Phase Boundary

Phase 5 ends at:

Python intelligence
→ API
→ frontend/dashboard
→ live intelligence visible to the user

The next phase is:

**Phase 6 — Qualified Lead Preparation for Outreach / Monetization**

Do not implement Phase 6 during Phase 5.