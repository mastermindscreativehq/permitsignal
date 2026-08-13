# PermitSignal — n8n Automation Layer

This directory holds n8n workflow exports for PermitSignal's automation
layer. n8n orchestrates; the PermitSignal backend (`backend/app/main.py`
+ the pipeline services under `backend/app/services/`) owns all
extraction, enrichment, scoring, and persistence logic. Workflows call
the backend's API rather than re-implementing any of that logic in n8n
nodes.

## First workflow: Government Packet Intake

`permitsignal-government-packet-intake.json` is the first production
boundary: `Webhook (real PDF upload) -> Validate Upload -> Document
Fetch (multipart forward) -> Validate Document -> Run PermitSignal ->
Supabase Upsert -> Execution Log -> Success/Error Response`.

This workflow ingests an **actual government packet PDF**, not a URL, a
filename, or a mock JSON payload. The trigger is a webhook that receives
the real file as a `multipart/form-data` upload (field name `file`);
n8n forwards those bytes, unmodified, to the backend.

Node-by-node:

| Node | What it does |
|---|---|
| `PS — Government Packet Webhook` | `n8n-nodes-base.webhook`, `POST /webhook/permitsignal-packet-intake`. Receives the real packet PDF as multipart form data (field `file`), plus optional form fields `reference_date` (`YYYY-MM-DD`), `live_enrichment`, `sync_to_supabase`. |
| `PS — Validate Upload` | Fast-fails if no binary file was attached to the request, before spending a backend round trip. |
| `PS — Document Fetch` | `POST {{PERMITSIGNAL_API_URL}}/pipeline/ingest/file` — forwards the uploaded PDF bytes as multipart/form-data. The backend re-validates the `%PDF` magic bytes, writes the file to `data/documents/`, then runs the full 7-stage pipeline (`pipeline_orchestrator.run_and_save()`), including the Supabase upsert when `sync_to_supabase=true`. |
| `PS — Validate Document` | Branches on the response's `status` field (`success` vs. anything else — invalid PDF, pipeline failure, Supabase failure, unreachable backend). |
| `PS — Run PermitSignal` | Surfaces the real `applications` / `opportunities` / `lead_queue` counts from the response. |
| `PS — Supabase Upsert` | Surfaces the real `supabase_sync` status (`disabled` / `skipped` / `synced` / `error`) and row count from the response. |
| `PS — Execution Log` | Builds a one-line run summary from the real counts above (n8n's own execution history retains the full per-node input/output for deeper tracing). |
| `PS — Success Response` | Structured JSON result built only from fields the backend actually computed (see "Response shape" below). |
| `PS — Respond Success` | Returns the success result as the webhook's HTTP response (200). |
| `PS — Error Response` | Builds a structured error result — missing upload or a non-success backend response — with the real error message, never swallowed. |
| `PS — Respond Error` | Returns the error result as the webhook's HTTP response (502). |

### Backend endpoints used

- `POST /pipeline/ingest/file` (multipart/form-data: `file`,
  `reference_date`, `live_enrichment`, `sync_to_supabase`) — the endpoint
  this workflow calls. Added in `backend/app/main.py` specifically so n8n
  can hand over real PDF bytes instead of a URL it would have to fetch
  itself. Internally: `document_downloader.save_uploaded_document()`
  (validates `%PDF` magic bytes, writes to `data/documents/`) then
  `pipeline_orchestrator.run_and_save()` (identical pipeline + optional
  Supabase upsert as every other ingestion path).
- `POST /pipeline/ingest` (JSON body: `source_url`, `reference_date`,
  `live_enrichment`, `sync_to_supabase`) — the original URL-based
  endpoint, unchanged and still available for callers that already have
  a public document URL rather than the file's bytes. Not used by this
  workflow.

Both endpoints share one bug fix made alongside this change:
`reference_date` arrives as a string (JSON field / form field) but
`pipeline_orchestrator.run_pipeline()` requires a `date` object (it calls
`.isoformat()` on it). `main.py`'s new `_parse_reference_date()` helper
converts it at the API boundary for both endpoints — this was a
pre-existing contract bug, not new pipeline logic.

### Response shape

```json
{
  "status": "success",
  "applications_processed": 8,
  "opportunities_processed": 8,
  "leads_synced": 8,
  "supabase_sync_status": "synced",
  "output_path": "data/output/permitsignal_opportunities.json",
  "errors": []
}
```

On failure:

```json
{
  "status": "error",
  "errors": ["<the real backend error / validation message>"]
}
```

Only fields the backend actually computes are populated. This pass does
**not** report `new_leads` / `updated_leads` / `unchanged_leads` /
`qualified_leads` / `contactable_leads` / `follow_up_candidates` /
`reports_generated` — see "Out of scope for this pass" below.

### Idempotency

`lead_repository.upsert_leads()` upserts on `application_number`
(`on_conflict="application_number"`). Submitting the same packet twice
updates the same Supabase rows rather than creating duplicates. Verified
against the real Provo packet: ingesting it twice produced `rows: 8` on
Supabase both times, with the same 8 `application_number`s present in
the table (no duplicate rows).

## Setup

1. In your n8n instance, set an environment variable
   `PERMITSIGNAL_API_URL` pointing at the running FastAPI backend (e.g.
   `http://localhost:8000` locally, or wherever it's deployed).
2. Ensure the backend process has `SUPABASE_URL` / `SUPABASE_KEY` (and
   optionally `SUPABASE_LEADS_TABLE`) configured — see
   `backend/app/services/lead_repository.py`'s module docstring — if you
   want `sync_to_supabase=true` runs to actually persist.
3. Import `permitsignal-government-packet-intake.json` (n8n → Workflows
   → Import from File).
4. Activate the workflow to expose the webhook at
   `{n8n_base_url}/webhook/permitsignal-packet-intake` (or
   `/webhook-test/...` while testing unactivated).
5. POST a real government packet PDF to that URL as
   `multipart/form-data` with the file under field name `file` (e.g.
   `curl -F "file=@packet.pdf" -F "reference_date=2026-08-01" <url>`).
6. Confirm the response and the backend's
   `data/output/permitsignal_opportunities.json` / Supabase `leads`
   table reflect the real packet before wiring this to a live intake
   source (email relay, portal watcher, upload form, etc).

## Real-data verification performed for this change

n8n itself was not available to execute in this environment, so the
exported workflow JSON above was validated structurally (well-formed,
every connection resolves to a real node) rather than run end-to-end
inside n8n. What it calls -- `POST /pipeline/ingest/file` -- was
verified directly against the real Provo packet already used by this
project (`data/documents/_08122026-415.pdf`), via FastAPI's `TestClient`
issuing an actual `multipart/form-data` request (the same request shape
n8n's `PS — Document Fetch` node sends):

- The real PDF was submitted twice.
- Both runs returned `status: success` with `applications: 8`,
  `opportunities: 8`, `lead_queue: 8` -- matching the existing verified
  pipeline baseline (CLAUDE.md Part 4).
- Both runs reported `supabase_sync: {"status": "synced", "rows": 8}`.
- A direct Supabase query after both runs found 8 distinct
  `application_number`s for this packet with no duplicates -- confirming
  upsert-based idempotency end-to-end, not just in unit tests.

To execute the actual n8n workflow for a final sign-off, run it inside a
real n8n instance per the Setup steps above with `PERMITSIGNAL_API_URL`
pointed at a running `uvicorn backend.app.main:app` process.

## Out of scope for this pass

Per CLAUDE.md Part 13 and the current integration scope: this is intake
only.

- Change detection (NEW / UPDATED / UNCHANGED classification of a
  resubmitted packet) is not implemented — the backend does not
  currently expose enough information to distinguish these, and adding
  that is a deliberately separate future change, not built here.
- The follow-up queue, contact-intelligence routing, and case-report
  generation triggering are likewise deliberately separate future
  workflows, not built here.
