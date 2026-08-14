import "server-only";

import type { Lead } from "./types";

export * from "./lead-helpers";

// Phase 4 API base URL (backend/app/main.py). Not a secret -- just a
// hostname. See dashboard/.env.local. Falls back to the local dev default
// so `next dev` works out of the box against `uvicorn backend.app.main:app`.
const PERMITSIGNAL_API_URL = process.env.PERMITSIGNAL_API_URL ?? "http://localhost:8000";

export class PermitSignalApiError extends Error {}

type LeadsResponse = { status: string; count: number; source: string | null; leads: unknown };
type LeadResponse = { status: string; application_number: string; source: string | null; lead: unknown };

/**
 * Every /leads and /leads/{application_number} call goes through here so
 * network failures, non-2xx responses, and malformed JSON all become one
 * clear PermitSignalApiError -- caught by dashboard/src/app/error.tsx --
 * instead of a raw fetch/TypeError with no context.
 */
async function apiGet<T>(path: string): Promise<T | null> {
  let response: Response;

  try {
    response = await fetch(`${PERMITSIGNAL_API_URL}${path}`, { cache: "no-store" });
  } catch (cause) {
    throw new PermitSignalApiError(
      `Could not reach the PermitSignal API at ${PERMITSIGNAL_API_URL}. Is the backend running?`,
      { cause }
    );
  }

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      // Non-JSON error body -- fall through with an empty detail.
    }
    throw new PermitSignalApiError(
      `PermitSignal API returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}.`
    );
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new PermitSignalApiError(`PermitSignal API returned malformed JSON for ${path}.`, { cause });
  }
}

/**
 * Fetch every lead from the Phase 4 API (GET /leads). This is real
 * production data -- the API's own ordering already applies
 * opportunity_builder.sort_opportunities(), sourced from Supabase when
 * configured and the pipeline's JSON artifact otherwise. Never backed by
 * fixtures/mocks.
 */
export async function getLeads(): Promise<Lead[]> {
  const payload = await apiGet<LeadsResponse>("/leads");

  if (payload === null) {
    return [];
  }

  if (!Array.isArray(payload.leads)) {
    throw new PermitSignalApiError("PermitSignal API /leads response did not contain a leads array.");
  }

  return payload.leads as Lead[];
}

export async function getLeadByApplicationNumber(applicationNumber: string): Promise<Lead | null> {
  const payload = await apiGet<LeadResponse>(`/leads/${encodeURIComponent(applicationNumber)}`);

  if (payload === null) {
    return null;
  }

  if (payload.lead === null || typeof payload.lead !== "object") {
    throw new PermitSignalApiError(
      `PermitSignal API /leads/${applicationNumber} response did not contain a lead object.`
    );
  }

  return payload.lead as Lead;
}
