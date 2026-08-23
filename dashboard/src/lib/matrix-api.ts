export interface MatrixMessage {
  role: "user" | "assistant";
  content: string;
}

export interface MatrixOutput {
  id: string;
  application_number: string;
  instruction: string;
  output: string;
  version: number;
  is_draft: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MatrixGenerateResponse {
  status: string;
  application_number: string;
  output: string;
  version: number;
  is_draft: boolean;
  id: string;
}

export interface MatrixListResponse {
  status: string;
  application_number: string;
  count: number;
  outputs: MatrixOutput[];
}

export interface MatrixGetResponse {
  status: string;
  application_number: string;
  output: MatrixOutput;
}

const PERMITSIGNAL_API_URL =
  process.env.NEXT_PUBLIC_PERMITSIGNAL_API_URL ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${PERMITSIGNAL_API_URL}${path}`, {
      cache: "no-store",
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
    throw new Error(
      `API returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}`
    );
  }

  return response.json() as Promise<T>;
}

async function apiPost<T>(
  path: string,
  body?: Record<string, unknown>
): Promise<T> {
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
    throw new Error(
      `API returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}`
    );
  }

  return response.json() as Promise<T>;
}

export async function generateMatrixChat(
  applicationNumber: string,
  messages: MatrixMessage[],
  options?: { is_draft?: boolean }
): Promise<MatrixGenerateResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/matrix`, {
    messages,
    is_draft: options?.is_draft ?? false,
  });
}

export async function generateMatrixOutput(
  applicationNumber: string,
  instruction: string,
  options?: { is_draft?: boolean; previous_version?: number }
): Promise<MatrixGenerateResponse> {
  return apiPost(`/leads/${encodeURIComponent(applicationNumber)}/matrix`, {
    instruction,
    is_draft: options?.is_draft ?? false,
    previous_version: options?.previous_version,
  });
}

export async function listMatrixOutputs(
  applicationNumber: string,
  limit?: number
): Promise<MatrixListResponse> {
  const qs = limit ? `?limit=${limit}` : "";
  return apiGet(
    `/leads/${encodeURIComponent(applicationNumber)}/matrix${qs}`
  );
}

export async function getMatrixOutput(
  applicationNumber: string,
  version: number
): Promise<MatrixGetResponse> {
  return apiGet(
    `/leads/${encodeURIComponent(applicationNumber)}/matrix/${version}`
  );
}
