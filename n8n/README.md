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

## Second workflow: Scheduled Government Discovery (Phase 7)

`permitsignal-scheduled-discovery.json` is the automation/orchestration
layer for **live** discovery — it does not wait for someone to hand n8n
a packet PDF (that's the intake workflow above). Instead it triggers the
backend's existing live-discovery boundary on a schedule, which finds
new government packets on its own.

This is a separate workflow file, not a modification of the intake
workflow above: the two have unrelated triggers (webhook vs. schedule)
and call different backend endpoints for different purposes (accepting
an already-obtained PDF vs. finding new PDFs at the source). Nothing in
the intake workflow was changed.

Flow: `Schedule Trigger / Manual Trigger -> Build Discovery Request ->
Discover Provo (HTTP) -> Classify Result -> one of five clearly-named
terminal nodes`.

Node-by-node:

| Node | What it does |
|---|---|
| `PS-Disc — Schedule Trigger` | `n8n-nodes-base.scheduleTrigger`, defaults to every 6 hours. Change the interval directly in this node (or deactivate it) without touching anything else. |
| `PS-Disc — Manual Trigger` | `n8n-nodes-base.manualTrigger` — lets you execute the exact same downstream path on demand for testing, whether or not the schedule is active. |
| `PS-Disc — Build Discovery Request` | `n8n-nodes-base.set`. Builds the request body from environment variables — `DISCOVERY_REFERENCE_DATE` (default: today), `DISCOVERY_LIVE_ENRICHMENT` (default: `false`), `DISCOVERY_SYNC_TO_SUPABASE` (default: `true`), `DISCOVERY_DRY_RUN` (default: `false`) — all four map 1:1 onto `backend.app.main.DiscoverProvoRequest`. No parameters are invented. |
| `PS-Disc — Discover Provo` | `n8n-nodes-base.httpRequest`, `POST {{ $env.PERMITSIGNAL_API_URL }}/discover/provo`. This single call is the entire Python discovery/idempotency/ingestion boundary: live Provo discovery (`backend.app.collectors.provo`), registry/idempotency filtering (`document_registry`), document download, and the full existing pipeline (applicant/company enrichment, approval-action intelligence, commercial/qualified-lead intelligence, Supabase persistence) for every newly discovered packet. `continueOnFail`/`alwaysOutputData` are enabled so a request failure produces an item to branch on instead of aborting the execution silently. |
| `PS-Disc — Classify Result` | `n8n-nodes-base.switch`. Routes the response into one of five outcomes purely by inspecting the real response — no duplicate idempotency logic. |
| `PS-Disc — ERROR: Discovery API Request Failed` | Unreachable backend, timeout, connection refused, or any non-2xx (including a 500 from an unhandled discovery exception). |
| `PS-Disc — ERROR: Malformed Discovery Response` | The API responded but the body has no `status` field — an unexpected response shape. |
| `PS-Disc — WARNING: Pipeline Errors During Ingestion` | Discovery succeeded but one or more newly discovered packets failed during download/pipeline ingestion (`discovery_orchestrator.ingest_document()` catches per-document failures so one bad packet never aborts the batch). Surfaces the real `errors` array. |
| `PS-Disc — SUCCESS: No New Records` | Discovery ran cleanly and found nothing new — the expected common case once the registry is caught up. |
| `PS-Disc — SUCCESS: New Records Found` | Discovery found new packets with zero per-document errors. When `dry_run=false` (the production default), the real pipeline outcome (`ingested`, `ingested_count`) is already final; check the `dry_run` field before treating counts as final. |

### Backend endpoint used

- `POST /discover/provo` (`backend/app/main.py` / `backend.app.services.discovery_orchestrator.discover_and_ingest_provo()`)
  — pre-existing Phase 2 boundary, not modified by this workflow. Accepts
  `reference_date`, `live_enrichment`, `sync_to_supabase`, `dry_run` —
  the only parameters this workflow sends.

### Idempotency

Entirely owned by `backend.app.services.document_registry`
(`data/state/document_registry.json`), unchanged by this workflow.
Re-running scheduled or manual discovery calls the same endpoint with
the same parameters; the backend decides what's new. n8n does not track,
diff, or cache which documents it has seen — it only classifies the
response for visibility.

### Setup

1. Same `PERMITSIGNAL_API_URL` environment variable as the intake
   workflow above.
2. Optional: `DISCOVERY_REFERENCE_DATE`, `DISCOVERY_LIVE_ENRICHMENT`,
   `DISCOVERY_SYNC_TO_SUPABASE`, `DISCOVERY_DRY_RUN` to override the
   discovery request defaults without editing the workflow.
3. Import `permitsignal-scheduled-discovery.json` and activate it to
   enable the schedule trigger; use the manual trigger to test without
   activating.
4. To change how often discovery runs, edit the interval on
   `PS-Disc — Schedule Trigger` directly (n8n stores the interval in the
   workflow, not an environment variable).

### Real-data verification performed for this change

n8n itself was not available to execute in this environment (same
constraint as the intake workflow above), so the exported JSON was
validated structurally (well-formed, every connection resolves to a
real node, every non-trigger node reachable from a trigger) and the
exact HTTP call `PS-Disc — Discover Provo` makes was issued directly
against a locally running `uvicorn backend.app.main:app` process:

- A `dry_run=true` call hit the real Provo government site and returned
  `discovered_total: 37`, `new_total: 37`, `new_packets: 19` — the
  registry (`data/state/document_registry.json`) did not exist before
  this run.
- A second `dry_run=true` call immediately after returned `new_total: 0`
  — confirming idempotency (registry-side, unchanged by this workflow).
- A request with an invalid `reference_date` and a request to an
  unreachable port both produced a non-2xx / connection failure — the
  two conditions `PS-Disc — Classify Result` routes to
  `PS-Disc — ERROR: Discovery API Request Failed`.
- A real `dry_run=false, sync_to_supabase=true` run was executed with
  the user's explicit approval; see the Phase 7 implementation report
  for the resulting counts and Supabase verification.

To execute the actual n8n workflow for final sign-off, import it into a
real n8n instance per Setup above with `PERMITSIGNAL_API_URL` pointed at
a running backend.

## Out of scope for the scheduled-discovery workflow

Per the Phase 7 boundary: this workflow ends at automated discovery
producing qualified leads through the existing pipeline. It does not
implement outreach execution, billing, payment collection, or any
Phase 8 end-to-end production testing — those are explicitly deferred.

## Third workflow: Outreach Preparation (Phase 8)

`permitsignal-outreach-preparation.json` is the automation/orchestration
layer for **outreach preparation** — it turns already-qualified,
outreach-ready leads (Phase 6 commercial lead intelligence) into
reviewable draft outreach packages. It never sends anything and never
duplicates any intelligence: contact selection, message drafting, and
lifecycle tracking all live in the backend
(`backend.app.services.outreach_intelligence`).

Flow: `Schedule Trigger / Manual Trigger -> Fetch Ready Leads -> Split
Ready Leads -> Not Yet Contacted -> Fetch Outreach Package -> Has Usable
Message -> Mark Outreach Prepared -> Build Review Summary`.

Node-by-node:

| Node | What it does |
|---|---|
| `PS-Out — Schedule Trigger` | `n8n-nodes-base.scheduleTrigger`, defaults to once every 24 hours. |
| `PS-Out — Manual Trigger` | `n8n-nodes-base.manualTrigger` — the same downstream path, on demand. |
| `PS-Out — Fetch Ready Leads` | `GET {{PERMITSIGNAL_API_URL}}/leads?commercial_readiness=READY_FOR_OUTREACH` — the existing Phase 4/6 retrieval boundary, filtered to Phase 6's commercial-readiness classification. Lead selection is entirely server-side (`backend.app.services.commercial_lead_intelligence`); n8n only consumes the result. |
| `PS-Out — Split Ready Leads` | `n8n-nodes-base.splitOut` on the `leads` array, so each lead is prepared independently. |
| `PS-Out — Not Yet Contacted` | Filters to `outreach_status` in `NEW`/`QUALIFIED`/`READY_FOR_OUTREACH` — a lead already `CONTACTED` or later was already acted on by a controlled event and must not be re-surfaced as if it were new. |
| `PS-Out — Fetch Outreach Package` | `GET {{PERMITSIGNAL_API_URL}}/leads/{application_number}/outreach` — the Phase 8 outreach-preparation boundary. Returns the selected contact target, recommended channel, and a personalized message draft built only from real PermitSignal evidence. This call never sends anything. |
| `PS-Out — Has Usable Message` | Drops any lead whose `message` is `null` — `outreach_intelligence.build_outreach_message()` returns `null` when there is no usable email/phone, never a fabricated contact. |
| `PS-Out — Mark Outreach Prepared` | `POST {{PERMITSIGNAL_API_URL}}/leads/{application_number}/outreach/events` with `{"event": "outreach_prepared"}` — records that a draft exists for human review. Advances `outreach_status` to `READY_FOR_OUTREACH` if it was still `NEW`/`QUALIFIED`; never sends anything itself. |
| `PS-Out — Build Review Summary` | Flattens the recipient, message draft, and commercial-action reasoning into one reviewable item. This is the **Human/Controlled Approval** boundary (CLAUDE.md Phase 8 section 11) — the workflow ends here. Wire your own notification node (Slack/Email/Sheet) after this node for your team; none is included since no such integration exists yet in this repo. |

### Backend endpoints used

- `GET /leads?commercial_readiness=READY_FOR_OUTREACH` — additive query
  filter on the existing Phase 4 `/leads` endpoint (`backend/app/main.py`).
- `GET /leads/{application_number}/outreach` — Phase 8 outreach-package
  boundary. Returns the selected contact, channel, message draft, and
  current lifecycle/qualification status. Read-only; prepares nothing on
  the server side either.
- `POST /leads/{application_number}/outreach/events` — Phase 8 controlled
  lifecycle boundary (`backend.app.services.outreach_intelligence.
  apply_outreach_event()`). Supported `event` values: `outreach_prepared`,
  `outreach_sent`, `response_received`, `engaged`, `follow_up_required`,
  `opportunity_created`, `won`, `lost`. Requires Supabase to be configured
  (`SUPABASE_URL`/`SUPABASE_KEY`) since outreach lifecycle state must
  survive the next pipeline run.

### Controlled sending — the human-in-the-loop step

PermitSignal never sends outreach automatically, in this workflow or
anywhere else. `PS-Out — Build Review Summary` is the terminal node: a
human (or your own downstream notification/CRM integration) reviews the
recipient and message draft and actually sends it through whatever
channel your team uses (email client, CRM, LinkedIn, etc). Once it has
genuinely been sent, confirm it so the lead's lifecycle advances and a
later pipeline run does not re-surface it as ready for outreach:

```bash
curl -X POST "{{PERMITSIGNAL_API_URL}}/leads/{application_number}/outreach/events" \
  -H "Content-Type: application/json" \
  -d '{"event": "outreach_sent"}'
```

Subsequent commercially meaningful events use the same endpoint:
`response_received`, `engaged`, `follow_up_required` (pass `"note"` for
the reason), `opportunity_created`, `won`, `lost`.

### Idempotency

`PS-Out — Not Yet Contacted` and `PS-Out — Mark Outreach Prepared`
together make repeated runs safe: a lead already prepared/contacted is
filtered out before this workflow would prepare it again, and
`outreach_intelligence.advance_outreach_status()` never lets a pipeline
rerun (or a second `outreach_prepared` event) regress a lead that has
already moved past `READY_FOR_OUTREACH` via a real controlled event.

### Real-data verification performed for this change

n8n itself was not available to execute in this environment (same
constraint as the two workflows above), so the exported JSON was
validated structurally (well-formed, every connection resolves to a real
node) and the exact HTTP calls this workflow makes were issued directly
against a locally running `uvicorn backend.app.main:app` process backed
by the real, configured Supabase project:

- `GET /leads?commercial_readiness=READY_FOR_OUTREACH` returned
  `status: success` (no leads currently meet the READY_FOR_OUTREACH bar
  for the real Provo packet — expected, since Phase 2 live enrichment is
  disabled and no packet applicant currently has a verified public
  contact).
- `GET /leads/PLRZ20260264/outreach` returned the real selected contact
  (`none` — no public contact evidence exists for this applicant),
  `channel: none`, and `message: null` — confirming no message is
  fabricated for a non-contactable lead.
- `POST /leads/PLRZ20260264/outreach/events` with `outreach_prepared`
  then `outreach_sent` was exercised directly against the real Supabase
  project: `outreach_status` advanced `NEW -> READY_FOR_OUTREACH ->
  CONTACTED`, and a subsequent full pipeline rerun
  (`--sync-supabase`) against the same real Provo packet confirmed the
  lead stayed `CONTACTED` rather than being reset — the core Phase 8
  lifecycle-integrity guarantee, verified end to end against live data.

To execute the actual n8n workflow for final sign-off, import it into a
real n8n instance per the Setup steps above (same `PERMITSIGNAL_API_URL`
environment variable as the other two workflows) with a running backend.

## Out of scope for the outreach-preparation workflow

Per the Phase 8 boundary: this workflow prepares outreach drafts for
human review and records that preparation happened. It does not send
messages through any channel, does not implement billing/payment
collection, and does not duplicate contact selection, message
generation, or lifecycle logic — all of that lives in
`backend.app.services.outreach_intelligence`.
