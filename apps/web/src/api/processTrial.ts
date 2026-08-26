import { apiFetch } from "./client";

export type Measurement = {
  value: number;
  unit: string;
};

export type TrialCase = {
  trial_case_id: string;
  case_code: string;
  mold_revision_ref: string;
  part_revision_ref: string;
  machine_code: string;
  material_code: string;
  product_type: string;
  purpose: string;
  outcome: string;
  classification: string;
  provenance: {
    connector_key: string;
    source_record_id: string;
    source_version: string;
    source_hash: string;
    mapping_version: string;
    source_type: "synthetic";
  };
};

export type ProcessMatch = {
  rank: number;
  trial_case_id: string;
  case_code: string;
  score: number;
  score_breakdown: Record<string, number>;
  profile_version: string;
  material_code: string;
  machine_code: string;
  product_type: string;
  mold_revision_ref: string;
  defect: {
    code: string;
    severity: string;
    location: string;
    quantity_rate: number | null;
    quantity_unit: string;
  };
  parameters: Record<string, Measurement>;
  corrective_action: {
    action_code: string;
    description: string;
    before_values: Record<string, Measurement>;
    after_values: Record<string, Measurement>;
    observed_outcome: Record<string, string | number>;
    expected_effect: string;
    stop_condition: string;
  } | null;
  outcome: string;
  similarities: Array<Record<string, unknown>>;
  differences: Array<Record<string, unknown>>;
  evidence_refs: string[];
  provenance: TrialCase["provenance"];
};

export type ControlledTrialStep = {
  rank: number;
  action_code: string;
  instruction: string;
  historical_before: Record<string, Measurement>;
  historical_after: Record<string, Measurement>;
  expected_effect: string;
  stop_condition: string;
  confidence: { label: string; score: number; basis: string };
  source_case_code: string;
  evidence_refs: string[];
  requires_engineer_approval: true;
  do_not_auto_apply: true;
};

export type ProcessSearchResult = {
  search_id: string;
  schema_version: "1.0";
  capability: string;
  scoring_profile_version: string;
  result_count: number;
  results: ProcessMatch[];
  rule_findings: Array<Record<string, unknown>>;
  recommendation: {
    abstained: boolean;
    reason_code: string | null;
    message: string;
    required_fields: string[];
    controlled_trial_steps: ControlledTrialStep[];
  };
  abstained: boolean;
  limitations: string[];
  lineage: Record<string, string>;
};

export type ProcessQuery = {
  defectCode: string;
  materialCode: string;
  machineCode: string;
  productType: string;
  location: string;
  injectionPressure: number | null;
  injectionSpeed: number | null;
  meltTemperature: number | null;
  topK: number;
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

export async function fetchProcessFixtureStatus(): Promise<{
  loaded_case_count: number;
  connector: { status: string; source_type: string; source_version: string; record_count: number };
}> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/process-trial/demo-fixtures`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function seedProcessFixtures(): Promise<{ created: number; existing: number }> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/process-trial/demo-fixtures`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: "{}",
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function fetchTrialCases(): Promise<TrialCase[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/trial-cases`);
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { items: TrialCase[] };
  return Array.isArray(payload.items) ? payload.items : [];
}

export async function searchProcessCases(query: ProcessQuery): Promise<ProcessSearchResult> {
  const parameters: Record<string, Measurement> = {};
  if (query.injectionPressure !== null) {
    parameters.injection_pressure_mpa = { value: query.injectionPressure, unit: "MPa" };
  }
  if (query.injectionSpeed !== null) {
    parameters.injection_speed_mm_s = { value: query.injectionSpeed, unit: "mm/s" };
  }
  if (query.meltTemperature !== null) {
    parameters.melt_temperature_c = { value: query.meltTemperature, unit: "degC" };
  }
  const response = await apiFetch(`${apiBaseUrl}/api/v1/process-case-searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      defect_code: query.defectCode,
      material_code: query.materialCode,
      machine_code: query.machineCode,
      product_type: query.productType,
      location: query.location,
      parameters,
      top_k: query.topK,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}
