# PermitSignal — Phase 4: API & Supabase Intelligence Exposure

## Objective

Expose the completed PermitSignal intelligence through the existing API and Supabase persistence layer so downstream systems can reliably consume the full intelligence record.

Phase 4 does NOT build the frontend.

The goal is to make the intelligence produced by the Python system accessible as a stable, structured backend contract.

---

## Completed Intelligence

Phases 1–3 are complete.

PermitSignal currently provides:

- live government discovery
- document ingestion
- PDF extraction
- application extraction
- opportunity generation
- lead queue generation
- applicant/company enrichment
- owner/person enrichment
- evidence-backed identity information
- approval-action intelligence
- Supabase persistence
- idempotent upsert behavior

Phase 4 must expose this existing intelligence without rebuilding it.

---

# Core Intelligence Flow

```text
Government Discovery
        ↓
Document Ingestion
        ↓
Application Extraction
        ↓
Opportunity Generation
        ↓
Applicant / Company Intelligence
        ↓
Owner / Person Intelligence
        ↓
Approval-Action Intelligence
        ↓
Qualified Lead Intelligence
        ↓
API / Supabase
        ↓
Future Frontend