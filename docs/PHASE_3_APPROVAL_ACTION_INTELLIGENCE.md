# PermitSignal — Phase 3: Approval-Action Intelligence

## Objective

Turn PermitSignal's discovered government project/application data into actionable approval intelligence.

PermitSignal must not only identify a project, applicant/company, opportunity, and associated person.

It must determine:

- what approval/permit action is relevant,
- what appears to be required,
- what stage/status the project is currently in,
- what action the applicant/project owner should take next,
- why that action is recommended,
- and what evidence supports the recommendation.

The goal is to help a project owner move toward approval rather than merely giving them information about a project.

---

## Existing System

The existing Python system already provides:

- live government discovery
- document ingestion
- PDF extraction
- application extraction
- opportunity generation
- lead queue generation
- Supabase persistence
- idempotent upsert behavior
- applicant/company enrichment
- owner/person enrichment
- evidence-backed identity information

Do NOT rebuild these capabilities.

Phase 3 must extend the existing intelligence pipeline.

---

## Current State

Phase 2 completed owner/person enrichment.

The system can now return structured information about:

- applicant
- company
- contact information
- owner/principal/executive/partner when legitimately discovered
- source URLs
- evidence text
- confidence
- contact role
- associated parties

The remaining intelligence gap is determining the **approval action** associated with the discovered project/application.

---

# Phase 3 Must

## 1. Inspect the Existing Pipeline

Before changing code:

- inspect the existing application extraction
- inspect opportunity generation
- inspect project/application status fields
- inspect document-derived facts
- inspect existing enrichment output
- inspect Supabase persistence
- inspect tests
- inspect the existing architecture and roadmap

Do not assume fields or structures that do not exist.

Reuse existing structures wherever possible.

---

## 2. Determine Existing Approval Evidence

Identify what approval-related information is already extracted from the government records.

Examples may include:

- application/project status
- hearing type
- meeting type
- agenda action
- decision
- approval condition
- recommendation
- required submission
- review stage
- permit/application type
- department involved
- board/commission involved
- hearing date
- decision date
- project milestone
- stated next step
- outstanding requirement

Only use information actually supported by the source document or verified public evidence.

---

## 3. Build Approval-Action Intelligence

Add a conservative approval-action intelligence layer.

For each qualifying application/project, determine where possible:

### Approval status

Examples:

- pending
- scheduled
- under review
- recommended
- approved
- conditionally approved
- denied
- continued
- withdrawn
- unknown

Do not invent a status when the source does not support one.

### Approval action

Determine the relevant action associated with the current state.

Examples:

- prepare for hearing
- submit required documentation
- address identified conditions
- respond to agency comments
- obtain required approval
- attend scheduled hearing
- satisfy approval conditions
- obtain additional permit/review
- follow up with the responsible department
- monitor for the next decision
- no immediate action identified

These are examples only.

The implementation must derive actions from the actual government/project evidence rather than blindly assigning generic recommendations.

---

## 4. Explain the Recommended Action

Every approval-action recommendation must contain evidence.

The structured result should make it possible to answer:

> Why does PermitSignal believe this is the next action?

Retain:

- recommended action
- approval status
- confidence
- source URL
- source type
- evidence text
- relevant date
- underlying application/project reference

Never present an inferred action as a confirmed government requirement.

Clearly distinguish:

- confirmed requirement
- evidence-backed recommendation
- inferred next step
- unknown

---

## 5. Preserve Evidence Boundaries

Approval-action intelligence must be evidence-first.

Do NOT:

- fabricate requirements
- invent permits
- invent deadlines
- invent approval conditions
- infer legal obligations without evidence
- claim approval is guaranteed
- present generic industry knowledge as a government requirement

If the evidence is insufficient:

```text
approval_action = "unknown"