import { apiFetch, downloadProtectedArtifact } from "./client";

export type Page = { number: number; size: number; total: number };
export type HistoryLifecycle = {
  status: "active" | "archived";
  row_version: number;
  archive_reason?: string | null;
  archived_at?: string | null;
};
export type AnalysisSummary = {
  analysis_type: string;
  analysis_id: string;
  title: string;
  state: string;
  job_id?: string | null;
  created_at: string;
  result_count: number;
  lifecycle: HistoryLifecycle;
};
export type AnalysisDetail = {
  analysis_type: string;
  analysis_id: string;
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
  job?: Record<string, unknown>;
  created_at: string;
  lifecycle: HistoryLifecycle;
};
export type JobEvent = {
  event_id: string;
  from_state?: string | null;
  to_state: string;
  stage: string;
  progress: number;
  detail: Record<string, unknown>;
  created_at: string;
};
export type HistoryJob = {
  job_id: string;
  capability_id: string;
  state: string;
  stage: string;
  progress: number;
  error?: { code?: string; message?: string } | null;
  input_snapshot?: Record<string, unknown>;
  events?: JobEvent[];
  created_at: string;
};
export type AuditRecord = {
  event_id: string;
  event_type: string;
  actor_id: string;
  target_refs: string[];
  detail: Record<string, unknown>;
  payload_hash: string;
  created_at: string;
};
export type LineageGraph = {
  schema_version: string;
  root: { type: string; id: string; key: string };
  nodes: Array<{ key: string; type: string; id: string; label: string; status: string }>;
  edges: Array<{ from: string; to: string; relation: string }>;
};

export class HistoryApiError extends Error {
  constructor(message: string, public status: number, public code: string) {
    super(message);
    this.name = "HistoryApiError";
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    throw new HistoryApiError(
      payload?.error?.message || `History API returned HTTP ${response.status}`,
      response.status,
      payload?.error?.code || "HISTORY_API_ERROR",
    );
  }
  return payload as T;
}

export function fetchAnalyses(type = ""): Promise<{ items: AnalysisSummary[]; page: Page }> {
  const query = type ? `?analysis_type=${encodeURIComponent(type)}` : "";
  return request(`/api/v1/history/analyses${query}`);
}

export function fetchAnalysis(type: string, id: string): Promise<AnalysisDetail> {
  return request(`/api/v1/history/analyses/${encodeURIComponent(type)}/${id}`);
}

export function mutateAnalysis(
  item: AnalysisDetail,
  action: "rerun" | "archive" | "restore",
  reason: string,
): Promise<AnalysisDetail> {
  return request(`/api/v1/history/analyses/${item.analysis_type}/${item.analysis_id}`, {
    method: "POST",
    body: JSON.stringify({ action, reason, row_version: item.lifecycle.row_version }),
  });
}

export function fetchJobs(state = ""): Promise<{ items: HistoryJob[]; page: Page }> {
  const query = state ? `?state=${encodeURIComponent(state)}` : "";
  return request(`/api/v1/history/jobs${query}`);
}

export function fetchJob(id: string): Promise<HistoryJob> {
  return request(`/api/v1/history/jobs/${id}`);
}

export function mutateJob(
  id: string,
  action: "cancel" | "retry",
  reason: string,
): Promise<HistoryJob> {
  return request(`/api/v1/history/jobs/${id}`, {
    method: "POST",
    body: JSON.stringify({ action, reason }),
  });
}

export function fetchAudit(eventType = ""): Promise<{ items: AuditRecord[]; page: Page }> {
  const query = eventType ? `?event_type=${encodeURIComponent(eventType)}` : "";
  return request(`/api/v1/history/audit-events${query}`);
}

export function fetchAuditDetail(id: string): Promise<AuditRecord> {
  return request(`/api/v1/history/audit-events/${id}`);
}

export function exportAudit(): Promise<void> {
  return downloadProtectedArtifact(
    `${apiBaseUrl}/api/v1/history/audit-events/export`,
    "mold-ai-audit.csv",
  );
}

export function fetchLineage(rootType: string, rootId: string): Promise<LineageGraph> {
  const query = new URLSearchParams({ root_type: rootType, root_id: rootId });
  return request(`/api/v1/history/lineage?${query}`);
}
