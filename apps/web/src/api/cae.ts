import { apiFetch } from "./client";

export type CAEResult = {
  result_id: string;
  metric_code: string;
  metric_label: string;
  result_type: "scalar" | "region_count";
  value: number;
  unit: string;
  location: Record<string, unknown>;
  quality_flags: string[];
  parser: { name: string; version: string };
  source_locator: Record<string, string>;
  evidence_refs: string[];
};

export type CAERun = {
  run_id: string;
  run_code: string;
  solver: { name: string; version: string };
  mesh: { artifact_ref: string; checksum: string; family: string };
  material_model_code: string;
  boundary_settings: Record<string, unknown>;
  process_settings: Record<string, number>;
  unit_system: string;
  status: string;
  input_hash: string;
  results: CAEResult[];
};

export type CAEStudy = {
  study_id: string;
  study_code: string;
  solver_name: string;
  product_ref: string;
  mold_revision_ref: string;
  material_model_code: string;
  mesh_family: string;
  objective: string;
  classification: string;
  provenance: {
    connector_key: string;
    integration_level: string;
    source_record_id: string;
    source_version: string;
    source_hash: string;
    mapping_version: string;
    official_solver_api_connected: false;
  };
  runs: CAERun[];
};

export type CAEMetricComparison = {
  metric_code: string;
  metric_label: string;
  result_type: string;
  unit: string;
  baseline: { result_id: string; value: number; location: Record<string, unknown> };
  candidate: { result_id: string; value: number; location: Record<string, unknown> };
  delta: number;
  percent_delta: number | null;
  finding: "improved" | "worsened" | "unchanged" | "changed_review_required";
  interpretation_type: "deterministic_metric_comparison";
  evidence_refs: string[];
};

export type CAEComparison = {
  comparison_id: string;
  schema_version: "1.0";
  capability: string;
  compatibility_profile_version: string;
  compatible: boolean;
  incompatibilities: Array<{
    code: string;
    field: string;
    baseline: unknown;
    candidate: unknown;
  }>;
  parsed_facts: {
    baseline: { study_id: string; study_code: string; run_id: string; run_code: string };
    candidate: { study_id: string; study_code: string; run_id: string; run_code: string };
  };
  comparison_summary: {
    comparable_metric_count: number;
    excluded_metric_count: number;
    finding_counts: Record<string, number>;
  };
  metric_comparisons: CAEMetricComparison[];
  metric_incompatibilities: Array<Record<string, unknown>>;
  lineage: Record<string, string>;
  limitations: string[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: { message?: string; code?: string } };
    return payload.error?.message || payload.error?.code || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function fetchCAEFixtureStatus(): Promise<{
  loaded_study_count: number;
  connector: {
    status: string;
    source_version: string;
    record_count: number;
    integration_level: string;
    official_solver_api_connected: false;
  };
}> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cae/demo-fixtures`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function seedCAEFixtures(): Promise<{ created: number; existing: number }> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cae/demo-fixtures`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: "{}",
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function fetchCAEStudies(): Promise<CAEStudy[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cae-studies`);
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { items: CAEStudy[] };
  return Array.isArray(payload.items) ? payload.items : [];
}

export async function compareCAERuns(
  baselineRunId: string,
  candidateRunId: string,
): Promise<CAEComparison> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cae-comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      baseline_run_id: baselineRunId,
      candidate_run_id: candidateRunId,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}
