# PermitSignal — Phase 7: n8n Automated Discovery

## Objective

Connect n8n to the existing PermitSignal Python discovery system so government project/application discovery can run automatically on a schedule and feed newly discovered records into the existing production pipeline.

Phase 7 is an automation/orchestration phase.

The existing Python system remains the source of truth for discovery, extraction, enrichment, approval-action intelligence, commercial intelligence, and persistence.

n8n must orchestrate the existing capabilities rather than rebuild them.

---

## Existing System

PermitSignal already provides:

- live government discovery
- document discovery
- PDF/document ingestion
- application extraction
- applicant/company enrichment
- owner/person enrichment
- opportunity generation
- approval-action intelligence
- commercial/qualified-lead intelligence
- lead qualification
- Supabase persistence
- idempotent upsert behavior
- API endpoints
- frontend live intelligence

The existing Python discovery endpoint is:

POST /discover/provo

The existing n8n workflow is:

n8n/permitsignal-government-packet-intake.json

Inspect the actual repository and existing n8n workflow before making changes.

Do not assume missing functionality exists or recreate functionality that already exists.

---

# Phase 7 Scope

Implement only the automated discovery/orchestration layer.

The target flow is:

```text
n8n Schedule Trigger
        ↓
PermitSignal Discovery API
        ↓
Python Live Government Discovery
        ↓
Registry / Idempotency Check
        ↓
Document Download
        ↓
Existing 7-Stage Pipeline
        ↓
Applicant / Company Intelligence
        ↓
Owner / Person Intelligence
        ↓
Approval-Action Intelligence
        ↓
API / Supabase Persistence
        ↓
Qualified Lead Available