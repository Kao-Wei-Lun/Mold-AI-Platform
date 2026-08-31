import { apiFetch } from "./client";

export type PlanningContextSource = {
  source_type: "registry" | "cad" | "reference_data" | "user_confirmed";
  source_ref: string;
};

export type RuleResolutionCandidate = {
  profile_id: string;
  profile_key: string;
  display_name: string;
  version: string;
  workflow_status: string;
  owner: string;
  approved_by: string;
  effective_from: string | null;
  effective_to: string | null;
  specificity: number;
  priority: number;
  is_default: boolean;
  matched_dimensions: string[];
  applicability_checksum: string;
};

export type MoldPlanningResolutionPreview = {
  schema_version: "1.0";
  mold_revision_id: string;
  cad_artifact_version_id: string | null;
  selection_mode: "automatic" | "default" | "manual_override";
  context: Record<string, string>;
  sources: Record<string, PlanningContextSource>;
  missing_fields: string[];
  selected: RuleResolutionCandidate;
  candidates: RuleResolutionCandidate[];
  excluded_summary: Array<{ profile_id: string; profile_key: string; reason_code: string; dimensions: string[] }>;
  reason: string;
  applicability_checksum: string;
};

export type MoldPlanningCandidateComparison = {
  schema_version: "1.0";
  context: Record<string, string>;
  baseline_profile_id: string;
  items: Array<{
    profile_id: string;
    profile_key: string;
    display_name: string;
    version: string;
    priority: number;
    is_default: boolean;
    owner: string;
    approved_by: string;
    effective_from: string | null;
    effective_to: string | null;
    applicability: Array<{ dimension: string; value_code: string; match_mode: string }>;
    enabled_rule_count: number;
    risk_categories: string[];
    high_risk_rules: Array<{ rule_id: string; title: string; severity: string; risk_type: string }>;
    difference_summary: { baseline_profile_id: string; added: string[]; removed: string[]; modified: string[] };
  }>;
};

export type MoldPlan = {
  plan_id: string;
  plan_code: string;
  name: string;
  purpose: "new_mold" | "modification" | "design_change" | "trial_improvement" | "other";
  project_id: string;
  project_code: string;
  part_id: string | null;
  part_number: string | null;
  mold_id: string;
  mold_code: string;
  mold_revision_id: string;
  mold_revision: string;
  cad_artifact_version_id: string | null;
  status: "draft" | "ready" | "completed" | "archived";
  owner_id: string;
  scope: string;
  classification: string;
  row_version: number;
  latest_resolution: null | {
    resolution_id: string;
    resolution_number: number;
    context_checksum: string;
    selected_profile_id: string;
    selected_profile_key: string;
    selected_profile_version: string;
    ruleset_checksum: string;
    applicability_checksum: string;
    selection_mode: string;
    reason: string;
    context: Record<string, string>;
    candidates: RuleResolutionCandidate[];
    excluded_summary: unknown[];
    resolved_by: string;
    resolved_at: string;
  };
  context?: Record<string, { value_code: string; source_type: string; source_ref: string }>;
  resolutions?: NonNullable<MoldPlan["latest_resolution"]>[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  archive_reason: string | null;
};

export class MoldPlanningError extends Error {
  constructor(message: string, public status: number, public code: string, public detail: Record<string, unknown> = {}) {
    super(message);
    this.name = "MoldPlanningError";
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export async function previewMoldPlanningResolution(input: {
  mold_revision_id: string;
  cad_artifact_version_id?: string;
  context: Partial<Record<"product_type" | "material" | "molding_process" | "location", string | undefined>>;
}): Promise<MoldPlanningResolutionPreview> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/mold-plans/resolution-preview`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = payload?.error || {};
    throw new MoldPlanningError(error.message || `Mold planning preview returned HTTP ${response.status}`, response.status, error.code || "MOLD_PLANNING_ERROR", error);
  }
  return payload as MoldPlanningResolutionPreview;
}

export async function compareMoldPlanningCandidates(input: {
  mold_revision_id: string;
  cad_artifact_version_id?: string;
  context: Partial<Record<"product_type" | "material" | "molding_process" | "location", string | undefined>>;
  profile_ids: string[];
}): Promise<MoldPlanningCandidateComparison> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/mold-plans/candidates/compare`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = payload?.error || {};
    throw new MoldPlanningError(error.message || `Candidate comparison returned HTTP ${response.status}`, response.status, error.code || "MOLD_PLANNING_COMPARISON_ERROR", error);
  }
  return payload as MoldPlanningCandidateComparison;
}

async function planRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    const error = payload?.error || {};
    throw new MoldPlanningError(error.message || `Mold plan returned HTTP ${response.status}`, response.status, error.code || "MOLD_PLAN_ERROR", error);
  }
  return payload as T;
}

export function fetchMoldPlans(input: { status?: string; q?: string } = {}): Promise<{ items: MoldPlan[]; page: { page: number; page_size: number; total: number } }> {
  const query = new URLSearchParams();
  if (input.status) query.set("status", input.status);
  if (input.q) query.set("q", input.q);
  return planRequest(`/api/v1/mold-plans${query.size ? `?${query}` : ""}`);
}

export function fetchMoldPlan(planId: string): Promise<MoldPlan> {
  return planRequest(`/api/v1/mold-plans/${planId}`);
}

export function createMoldPlan(input: {
  name: string;
  purpose: MoldPlan["purpose"];
  mold_revision_id: string;
  cad_artifact_version_id?: string;
  context: Partial<Record<"product_type" | "material" | "molding_process" | "location", string | undefined>>;
}): Promise<MoldPlan> {
  return planRequest("/api/v1/mold-plans", { method: "POST", body: JSON.stringify(input) });
}

export function updateMoldPlan(plan: MoldPlan, input: { name: string; purpose: MoldPlan["purpose"] }): Promise<MoldPlan> {
  return planRequest(`/api/v1/mold-plans/${plan.plan_id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: plan.row_version }),
  });
}

export function resolveMoldPlan(planId: string): Promise<MoldPlan> {
  return planRequest(`/api/v1/mold-plans/${planId}/resolve`, { method: "POST", body: "{}" });
}

export function transitionMoldPlan(plan: MoldPlan, action: "complete" | "reopen" | "archive", reason: string): Promise<MoldPlan> {
  return planRequest(`/api/v1/mold-plans/${plan.plan_id}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, reason, row_version: plan.row_version }),
  });
}
