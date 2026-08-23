import type {
  InvestigationResponse,
  InvestigationActionResponse,
  InvestigationAllResponse,
} from "./types";

const PERMITSIGNAL_API_URL = process.env.NEXT_PUBLIC_PERMITSIGNAL_API_URL ?? "http://localhost:8000";

async function apiPost<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${PERMITSIGNAL_API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(
      `Could not reach the Provo Administrative Services Finance API at ${PERMITSIGNAL_API_URL}. Is the backend running?`
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      // Non-JSON error body
    }
    throw new Error(`API returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}`);
  }

  return response.json() as Promise<T>;
}

async function apiGet<T>(path: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${PERMITSIGNAL_API_URL}${path}`, { cache: "no-store" });
  } catch {
    throw new Error(
      `Could not reach the Provo Administrative Services Finance API at ${PERMITSIGNAL_API_URL}. Is the backend running?`
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      // Non-JSON error body
    }
    throw new Error(`API returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}`);
  }

  return response.json() as Promise<T>;
}

export async function getInvestigation(applicationNumber: string): Promise<InvestigationResponse> {
  return apiGet(`/leads/${encodeURIComponent(applicationNumber)}/investigation`);
}

export async function investigateWeb(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/web`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateWebsite(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/website`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateDirectories(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/directories`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateLinkedin(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/linkedin`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigatePublicRecords(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/public-records`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateProject(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/project`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateContact(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationActionResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/contact`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}

export async function investigateAll(
  applicationNumber: string,
  options?: { force?: boolean; note?: string }
): Promise<InvestigationAllResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/investigation/all`, {
    force: options?.force ?? false,
    note: options?.note,
  });
}
