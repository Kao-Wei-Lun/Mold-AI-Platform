import { apiFetch } from "./client";

export type IngestionIssue = {
  issue_id: string;
  row_number: number | null;
  field_name: string;
  code: string;
  message: string;
  raw_value: unknown;
  suggestion: string;
  severity: "blocking" | "warning";
};

export type IngestionBatch = {
  schema_version: "1.0";
  batch_id: string;
  canonical_id: string;
  scope: string;
  classification: string;
  domain: string;
  source_name: string;
  status: string;
  mapping_version: string;
  validation: { valid?: boolean; record_count?: number; valid_count?: number; existing_count?: number; issues?: unknown[] };
  reconciliation: Record<string, unknown>;
  job_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  deep_link: string;
  request_id: string;
  correlation_id: string | null;
  field_mapping?: Record<string, string>;
  records?: Array<Record<string, unknown>>;
  source_files?: Array<{ source_file_id: string; artifact_version_id: string; file_name: string; sha256: string; mime_type: string; size_bytes: number; screening: Record<string, unknown> }>;
  issues?: IngestionIssue[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error?.message || `Ingestion API HTTP ${response.status}`);
  return payload as T;
}

export async function fetchIngestions(scope: string): Promise<IngestionBatch[]> {
  const payload = await request<{ items: IngestionBatch[] }>(`/api/v1/ingestions?scope=${encodeURIComponent(scope)}`);
  return payload.items;
}

export function fetchIngestion(id: string): Promise<IngestionBatch> {
  return request(`/api/v1/ingestions/${id}`);
}

export function createIngestion(input: { scope: string; domain: string; source_name: string; idempotency_key: string }): Promise<IngestionBatch> {
  return request("/api/v1/ingestions", { method: "POST", body: JSON.stringify(input) });
}

export function uploadIngestionFile(id: string, file: File): Promise<IngestionBatch> {
  const body = new FormData();
  body.set("file", file);
  return request(`/api/v1/ingestions/${id}/files`, { method: "POST", body });
}

export function updateIngestionMapping(id: string, fieldMapping: Record<string, string>): Promise<IngestionBatch> {
  return request(`/api/v1/ingestions/${id}/mapping`, { method: "PUT", body: JSON.stringify({ field_mapping: fieldMapping, mapping_version: "1.0" }) });
}

export function validateIngestion(id: string): Promise<IngestionBatch> {
  return request(`/api/v1/ingestions/${id}/validate`, { method: "POST", body: "{}" });
}

export function commitIngestion(id: string, reason: string): Promise<IngestionBatch> {
  return request(`/api/v1/ingestions/${id}/commit`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function cancelIngestion(id: string): Promise<IngestionBatch> {
  return request(`/api/v1/ingestions/${id}/cancel`, { method: "POST", body: "{}" });
}

export function importTemplateUrl(domain: string): string {
  return `${apiBaseUrl}/api/v1/import-templates/${encodeURIComponent(domain)}`;
}
