# PermitSignal — Phase 8: Outreach & Monetization

## Objective

Turn qualified PermitSignal leads into actionable commercial opportunities.

PermitSignal has already completed:

- Live government discovery
- Document ingestion
- Application extraction
- Applicant/company enrichment
- Owner/person enrichment
- Approval-action intelligence
- API and Supabase intelligence exposure
- Frontend live intelligence
- Qualified lead/commercial intelligence
- Automated n8n discovery

Phase 8 uses those existing outputs to prepare and execute the commercial process.

---

## Core Mission

PermitSignal exists to:

> Find qualified project opportunities, understand who is responsible for them, determine what action is required to move the project forward, identify the appropriate commercial contact, and turn that intelligence into revenue.

The commercial flow is:

Government opportunity
↓
Applicant/company intelligence
↓
Owner/person intelligence
↓
Approval-action intelligence
↓
Commercial readiness
↓
Qualified lead
↓
Contact strategy
↓
Outreach
↓
Response
↓
Commercial opportunity
↓
Revenue

---

# Existing Intelligence

Do NOT rebuild intelligence already produced by Phases 1–7.

Use the existing fields for:

- project
- application
- applicant/company
- owner/person
- contact information
- parties
- friction
- approval status
- approval action
- approval basis
- evidence
- commercial readiness
- contactability
- recommended commercial action
- commercial action reason
- lead status
- priority
- priority score

---

# Phase 8 Requirements

## 1. Audit Existing Qualified Lead Data

Inspect the existing lead/opportunity representation.

Determine exactly what information is currently available for outreach.

Do not invent missing information.

---

## 2. Commercial Lead Selection

Create a deterministic method for selecting leads appropriate for outreach.

Use existing qualification/commercial-intelligence fields.

Do not create an unrelated scoring system.

A lead should be considered commercially actionable based on existing evidence such as:

- contactability
- commercial readiness
- lead status
- priority
- approval action
- owner/applicant information
- available contact information

---

## 3. Outreach Intelligence

For each qualified lead, determine:

- who should be contacted
- why they should be contacted
- what project/application triggered the opportunity
- what approval/action issue is relevant
- what commercial problem PermitSignal can help solve
- what outreach channel is appropriate
- what next action should be taken

The system must remain evidence-based.

Do not fabricate personal information.

---

## 4. Outreach Preparation

Create structured outreach-ready information.

The system should be capable of producing a lead record containing:

- recipient
- company
- role
- email
- phone
- project/application
- reason for outreach
- recommended channel
- recommended action
- evidence
- source
- qualification status

Where information is unavailable, preserve it as unknown/null.

---

## 5. Outreach Message Intelligence

Prepare the structured inputs necessary to generate personalized outreach.

Messages must be based on actual PermitSignal intelligence.

The system must not claim:

- an approval occurred when it did not
- a person owns a company when ownership is unverified
- a project is approved when the evidence does not establish approval
- a relationship that has not been established

---

## 6. Outreach Execution

Where existing integrations are available, prepare the system for controlled outreach through appropriate channels.

Potential channels may include:

- email
- SMS
- Telegram
- LinkedIn
- other approved business communication channels

Do not blindly send messages.

The system must support controlled execution and clear lead status tracking.

---

## 7. Lead Lifecycle

Establish or extend the existing lead lifecycle without breaking current behavior.

At minimum, support states equivalent to:

```text
NEW
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
ENGAGED
OPPORTUNITY
WON
LOST