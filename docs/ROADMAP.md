# PermitSignal — Project Roadmap

## Mission

PermitSignal is a government approval intelligence and lead-generation system.

Its purpose is to discover real government approval opportunities, identify and enrich the applicant/company behind each opportunity, identify the relevant people, determine what action is required to improve the chance of approval, expose that intelligence through the system, and ultimately produce qualified leads that can be monetized.

The core business outcome is:

> Find opportunities and leads, determine what they need to do to get their project approved, connect that intelligence to the appropriate buyer/service provider, and monetize the qualified lead.

---

# Critical Path

## Phase 1 — Audit Existing Python System

Status: COMPLETE

Understand and preserve the existing Python intelligence system.

Existing capabilities include:

- Government source discovery
- Document ingestion
- PDF extraction
- Application extraction
- Opportunity generation
- Lead queue generation
- Applicant/company enrichment
- Supabase persistence
- Idempotent upsert behavior

---

## Phase 2 — Owner / Person Enrichment

Status: COMPLETE

Complete the existing applicant/company enrichment capability so PermitSignal can identify the real-world:

- owner
- principal
- responsible person
- executive
- partner
- or other legitimately associated person

when reliable evidence is available.

The existing applicant/company enrichment must remain intact.

Detailed specification:

docs/PHASE_2_OWNER_ENRICHMENT.md

---

## Phase 3 — Approval-Action Intelligence

Status: COMPLETE

Determine what the applicant/project needs to do to improve its approval outcome.

The system should transform government/project information into actionable intelligence.

Conceptually:

Government requirement / issue
→ project-specific interpretation
→ required action
→ recommended next step
→ potential service/opportunity

This phase must use the intelligence produced by the earlier phases.

---

## Phase 4 — API / Supabase Intelligence

Status: COMPLETE

Ensure the resulting intelligence is exposed cleanly through the existing API and persisted through Supabase.

The objective is to make the intelligence available to downstream systems without duplicating the Python intelligence layer.

---

## Phase 5 — Frontend Live Intelligence

Status: COMPLETE

Connect the existing frontend/dashboard to live PermitSignal intelligence.

The frontend should consume the actual backend/Supabase data rather than using static demonstration data.

---

## Phase 6 — Qualified Leads / Outreach / Monetization

Status: COMPLETE

Turn discovered and enriched opportunities into qualified commercial leads.

The system should eventually support:

- lead qualification
- owner/applicant information
- company information
- project information
- approval situation
- required action
- relevant service opportunity
- outreach readiness
- monetization

---

## Phase 7 — n8n Automated Discovery

Status: COMPLETE

Use n8n to automate the triggering and scheduling of the existing Python discovery/intelligence system.

n8n is the automation/orchestration layer.

Python remains the core intelligence and processing layer.

Do not move working Python intelligence into n8n unnecessarily.

---

## Phase 8 — End-to-End Production Testing

Status: PLANNED

Verify the complete production system:

Discovery
→ ingestion
→ extraction
→ application intelligence
→ applicant/company enrichment
→ owner/person enrichment
→ approval-action intelligence
→ persistence
→ frontend
→ qualified lead
→ outreach/monetization workflow

Test reliability, idempotency, data quality, and production behavior.

---

# Execution Rule

PermitSignal is developed one phase at a time.

A phase must be:

1. implemented;
2. tested;
3. verified;
4. documented;

before the next phase begins.

Do not implement later phases early unless explicitly instructed.

---

# Architecture Principle

Python is the core intelligence and processing system.

Supabase is the persistence/data layer.

The API exposes backend intelligence.
The frontend consumes live intelligence.

n8n provides automation/orchestration.

Each layer has a defined responsibility.

Do not duplicate working functionality across layers without a clear reason.