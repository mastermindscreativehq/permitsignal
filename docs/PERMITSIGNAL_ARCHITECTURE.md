# PermitSignal — System Architecture

## 1. Purpose

PermitSignal is a government approval intelligence platform.

It discovers government approval records and converts raw government documents into structured commercial intelligence.

The system is not simply a scraper.

The scraper/discovery layer is the entry point.

The primary value is the intelligence produced after discovery.

---

# 2. Core Intelligence Flow

```text
Government Sources
       ↓
Live Discovery
       ↓
Document / PDF
       ↓
Document Ingestion
       ↓
PDF Extraction
       ↓
Application Extraction
       ↓
Applicant / Company Intelligence
       ↓
Owner / Person Intelligence
       ↓
Approval-Action Intelligence
       ↓
Qualified Lead
       ↓
Frontend / API / Supabase
       ↓
Outreach / Monetization