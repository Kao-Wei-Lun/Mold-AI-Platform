import { apiFetch } from "./client";

export type TrialCorrection = {
  correction_id: string;
  before_values: Record<string, unknown>;
  after_values: Record<string, unknown>;
  reason: string;
  corrected_by: string;
  created_at: string;
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
  lifecycle_status: "draft" | "closed" | "reopened" | "archived";
  row_version: number;
  corrections: TrialCorrection[];
  provenance: Record<string, unknown>;
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
  provenance: Record<string, unknown>;
  runs: Array<{ run_id: string; run_code: string; results: Array<Record<string, unknown>> }>;
};

export type HMIProfile = {
  profile_id: string;
  profile_key: string;
  version: string;
  status: "draft" | "published" | "retired";
  field_specs: Array<Record<string, unknown>>;
  profile_checksum: string;
  change_summary: string;
  extraction_count: number;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error?.message || `Engineering data returned HTTP ${response.status}`);
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
    body: JSON.stringify({ action, reason }),
  });
}
