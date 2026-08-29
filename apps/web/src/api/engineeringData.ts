import { apiFetch } from "./client";

export type TrialCorrection = {
  correction_id: string;
  before_values: Record<string, unknown>;
  after_values: Record<string, unknown>;
  reason: string;
  corrected_by: string;
  created_at: string;
};

export type TrialProcessRun = {
  process_run_id: string;
  run_number: number;
  cycle_range: { start: number | null; end: number | null };
  parameters: Record<string, { value: number; unit: string; value_kind: string; sampling_method: string }>;
  environment: Record<string, unknown>;
  result: Record<string, unknown>;
  data_quality: Record<string, unknown>;
  defects: Array<{
    defect_id: string;
    defect_code: string;
    severity: string;
    location: string;
    quantity_rate: number | null;
    quantity_unit: string;
    inspection_method: string;
    evidence_refs: string[];
  }>;
  corrective_actions: Array<{
    action_id: string;
    action_code: string;
    description: string;
    before_values: Record<string, unknown>;
    after_values: Record<string, unknown>;
    rationale_source: string;
    approved_by: string;
    executed: boolean;
    observed_outcome: string;
    expected_effect: string;
    stop_condition: string;
    evidence_refs: string[];
  }>;
};

export type ManagedTrial = {
  trial_case_id: string;
  case_code: string;
  mold_revision_ref: string;
  machine_code: string;
  material_code: string;
  product_type: string;
  purpose: string;
  outcome: string;
  started_at: string;
  material_lot?: string;
  part_revision_ref?: string;
  classification?: string;
  acl_scopes?: string[];
  data_quality?: Record<string, unknown>;
  closed_at?: string | null;
  archive_reason?: string | null;
  lifecycle_status: "draft" | "closed" | "reopened" | "archived";
  row_version: number;
  corrections: TrialCorrection[];
  runs?: TrialProcessRun[];
  provenance: Record<string, unknown>;
};

export type ManagedTrialSummary = {
  trial_case_id: string;
  case_code: string;
  mold_revision_ref: string;
  machine_code: string;
  material_code: string;
  product_type: string;
  outcome: string;
  started_at: string;
  lifecycle_status: ManagedTrial["lifecycle_status"];
  row_version: number;
  run_count: number;
  correction_count: number;
};

export type CAEResult = {
  result_id: string;
  metric_code: string;
  result_type: string;
  value: number;
  unit: string;
  location: Record<string, unknown>;
  field_summary: Record<string, unknown>;
  quality_flags: string[];
  parser: { name: string; version: string };
  source_locator: Record<string, unknown>;
  evidence_refs: string[];
};

export type CAERun = {
  run_id: string;
  run_code: string;
  solver: { name: string; version: string };
  mesh: { artifact_ref: string; checksum: string; family: string };
  material_model_code: string;
  boundary_settings: Record<string, unknown>;
  process_settings: Record<string, unknown>;
  unit_system: string;
  status: string;
  input_hash: string;
  data_quality: Record<string, unknown>;
  results: CAEResult[];
};

export type ManagedCAEStudy = {
  study_id: string;
  study_code: string;
  solver_name: string;
  mold_revision_ref: string;
  material_model_code: string;
  mesh_family: string;
  objective: string;
  lifecycle_status: "active" | "archived";
  row_version: number;
  archive_reason: string | null;
  archived_at?: string | null;
  owner?: string;
  product_ref?: string;
  classification?: string;
  acl_scopes?: string[];
  data_quality?: Record<string, unknown>;
  provenance: Record<string, unknown>;
  runs: CAERun[];
};

export type ManagedCAESummary = {
  study_id: string;
  study_code: string;
  solver_name: string;
  mold_revision_ref: string;
  material_model_code: string;
  mesh_family: string;
  objective: string;
  lifecycle_status: ManagedCAEStudy["lifecycle_status"];
  row_version: number;
  run_count: number;
  result_count: number;
};

export type HMIProfile = {
  profile_id: string;
  profile_key: string;
  version: string;
  status: "draft" | "published" | "retired";
  field_specs: Array<Record<string, unknown>>;
  profile_checksum: string;
  change_summary: string;
  row_version: number;
  updated_at: string;
  extraction_count: number;
};

export class EngineeringDataError extends Error {
  constructor(message: string, public status: number, public code: string) {
    super(message);
    this.name = "EngineeringDataError";
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
    throw new EngineeringDataError(
      payload?.error?.message || `Engineering data returned HTTP ${response.status}`,
      response.status,
      payload?.error?.code || "ENGINEERING_DATA_ERROR",
    );
  }
  return payload as T;
}

export async function fetchEngineeringData(): Promise<{
  trials: ManagedTrial[];
  studies: ManagedCAEStudy[];
  profiles: HMIProfile[];
}> {
  const [trials, studies, profiles] = await Promise.all([
    request<{ items: ManagedTrial[] }>("/api/v1/trial-cases"),
    request<{ items: ManagedCAEStudy[] }>("/api/v1/cae-studies"),
    request<{ items: HMIProfile[] }>("/api/v1/hmi-profiles"),
  ]);
  return { trials: trials.items, studies: studies.items, profiles: profiles.items };
}

export async function fetchTrialHistory(): Promise<ManagedTrialSummary[]> {
  const payload = await request<{ items: ManagedTrialSummary[] }>("/api/v1/trial-cases?view=summary");
  return payload.items;
}

export function fetchTrialCaseDetail(id: string): Promise<ManagedTrial> {
  return request(`/api/v1/trial-cases/${id}`);
}

export async function fetchCAEHistory(): Promise<ManagedCAESummary[]> {
  const payload = await request<{ items: ManagedCAESummary[] }>("/api/v1/cae-studies?view=summary");
  return payload.items;
}

export function fetchCAEStudyDetail(id: string): Promise<ManagedCAEStudy> {
  return request(`/api/v1/cae-studies/${id}`);
}

export function createManagedTrial(input: Record<string, unknown>): Promise<ManagedTrial> {
  return request("/api/v1/trial-cases", { method: "POST", body: JSON.stringify(input) });
}

export function transitionTrial(
  trial: ManagedTrial,
  action: "close" | "reopen" | "archive",
  reason: string,
): Promise<ManagedTrial> {
  return request(`/api/v1/trial-cases/${trial.trial_case_id}`, {
    method: "PATCH",
    body: JSON.stringify({ action, reason, row_version: trial.row_version }),
  });
}

export function updateManagedTrial(
  trial: ManagedTrial,
  changes: Pick<ManagedTrial, "purpose" | "outcome" | "material_lot">,
  reason: string,
): Promise<ManagedTrial> {
  return request(`/api/v1/trial-cases/${trial.trial_case_id}`, {
    method: "PATCH",
    body: JSON.stringify({ action: "update", ...changes, reason, row_version: trial.row_version }),
  });
}

export function correctManagedTrial(
  trial: ManagedTrial,
  changes: Partial<Pick<ManagedTrial, "purpose" | "outcome" | "material_lot">>,
  reason: string,
): Promise<ManagedTrial> {
  return request(`/api/v1/trial-cases/${trial.trial_case_id}`, {
    method: "PATCH",
    body: JSON.stringify({ action: "correct", changes, reason, row_version: trial.row_version }),
  });
}

export function appendManagedProcessRun(
  trial: ManagedTrial,
  input: Record<string, unknown>,
): Promise<ManagedTrial> {
  return request(`/api/v1/trial-cases/${trial.trial_case_id}/runs`, {
    method: "POST",
    body: JSON.stringify({ ...input, row_version: trial.row_version }),
  });
}

export function createManagedCAEStudy(input: Record<string, unknown>): Promise<ManagedCAEStudy> {
  return request("/api/v1/cae-studies", { method: "POST", body: JSON.stringify(input) });
}

export function transitionCAEStudy(
  study: ManagedCAEStudy,
  action: "archive" | "restore",
  reason: string,
): Promise<ManagedCAEStudy> {
  return request(`/api/v1/cae-studies/${study.study_id}`, {
    method: "PATCH",
    body: JSON.stringify({ action, reason, row_version: study.row_version }),
  });
}

export function appendManagedCAERun(
  study: ManagedCAEStudy,
  input: Record<string, unknown>,
): Promise<ManagedCAEStudy> {
  return request(`/api/v1/cae-studies/${study.study_id}/runs`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function fetchHMIProfiles(): Promise<HMIProfile[]> {
  const payload = await request<{ items: HMIProfile[] }>("/api/v1/hmi-profiles");
  return payload.items;
}

export function updateHMIProfile(
  profile: HMIProfile,
  input: { field_specs: Array<Record<string, unknown>>; change_summary: string; reason: string },
): Promise<HMIProfile> {
  return request(`/api/v1/hmi-profiles/${profile.profile_id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: profile.row_version }),
  });
}

export function cloneHMIProfile(
  sourceProfileId: string,
  version: string,
  changeSummary: string,
  reason: string,
): Promise<HMIProfile> {
  return request("/api/v1/hmi-profiles", {
    method: "POST",
    body: JSON.stringify({
      source_profile_id: sourceProfileId,
      version,
      change_summary: changeSummary,
      reason,
    }),
  });
}

export function transitionHMIProfile(
  profile: HMIProfile,
  action: "publish" | "retire",
  reason: string,
): Promise<HMIProfile> {
  return request(`/api/v1/hmi-profiles/${profile.profile_id}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, reason, row_version: profile.row_version }),
  });
}
