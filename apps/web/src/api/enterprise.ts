import { apiFetch } from "./client";

export type EnterprisePolicy = {
  policy_id: string;
  scope: string;
  classification: string;
  connector_mode: "public_demo" | "company";
  retention_days: number;
  retention_cutoff: string;
  retention_eligible: Record<string, number>;
  purge_blocked: boolean;
  legal_hold: boolean;
  legal_hold_reason: string;
  dlp_enabled: boolean;
  export_allowed: boolean;
  siem: { enabled: boolean; destination?: string | null; status: string };
  isolation: {
    index_namespace: string;
    cache_namespace: string;
    cross_scope_queries: boolean;
    cross_scope_exports: boolean;
  };
  row_version: number;
  updated_by: string;
  updated_at: string;
};

export type ImportBatch = {
  batch_id: string;
  scope: string;
  domain: string;
  source_name: string;
  status: string;
  validation: { valid: boolean; record_count: number; valid_count: number; issues: unknown[] };
  reconciliation: Record<string, unknown>;
  created_at: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error?.message || `Enterprise API HTTP ${response.status}`);
  return payload as T;
}

export function fetchEnterprisePolicy(scope: string): Promise<EnterprisePolicy> {
  return request(`/api/v1/enterprise/policy?scope=${encodeURIComponent(scope)}`);
}

export function updateEnterprisePolicy(
  policy: EnterprisePolicy,
  changes: Record<string, unknown>,
  reason: string,
): Promise<EnterprisePolicy> {
  return request("/api/v1/enterprise/policy", {
    method: "PATCH",
    body: JSON.stringify({
      scope: policy.scope,
      row_version: policy.row_version,
      reason,
      ...changes,
    }),
  });
}

export async function fetchImportBatches(scope: string): Promise<ImportBatch[]> {
  const payload = await request<{ items: ImportBatch[] }>(
    `/api/v1/enterprise/import-batches?scope=${encodeURIComponent(scope)}`,
  );
  return payload.items;
}

export function validateImport(input: Record<string, unknown>): Promise<ImportBatch> {
  return request("/api/v1/enterprise/import-batches", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function commitImport(batchId: string, reason: string): Promise<ImportBatch> {
  return request(`/api/v1/enterprise/import-batches/${batchId}`, {
    method: "POST",
    body: JSON.stringify({ action: "commit", reason }),
  });
}

export function bulkArchive(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/v1/enterprise/bulk-archive", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
