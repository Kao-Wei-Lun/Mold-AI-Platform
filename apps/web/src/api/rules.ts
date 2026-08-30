import { apiFetch } from "./client";
import type { ReviewRule } from "./designReview";

export type RuleProfile = {
  profile_id: string;
  profile_key: string;
  version: string;
  status: string;
  workflow_status: "draft" | "validated" | "in_review" | "approved" | "published" | "retired";
  change_summary: string;
  row_version: number;
  owner: string;
  submitted_by: string | null;
  reviewed_by: string | null;
  approved_by: string;
  published_at: string | null;
  retired_at: string | null;
  ruleset_checksum: string;
  priority: number;
  is_default: boolean;
  effective_from: string | null;
  effective_to: string | null;
  scope: string | null;
  classification: string;
  resolution_status: "eligible" | "disabled";
  applicability_checksum: string;
  applicability: RuleApplicability[];
  rule_count: number;
  rules: RuleDefinition[];
};

export type RuleApplicability = {
  dimension: "mold_type" | "product_type" | "material" | "molding_process" | "project" | "location";
  value_code: string;
  match_mode: "include" | "exclude";
};

export type RuleDefinition = ReviewRule & {
  enabled: boolean;
  applicability: Record<string, unknown>;
  measurement_definition: Record<string, unknown>;
};

export type RuleProfileDiff = {
  schema_version: "1.0";
  baseline_profile_id: string;
  profile_id: string;
  changes: Array<{ rule_id: string; change: "added" | "removed" | "modified"; changed_fields: string[] }>;
};

export type RuleValidation = {
  schema_version: "1.0";
  profile_id: string;
  valid: boolean;
  issues: Array<{ code: string; rule_id?: string; message: string }>;
  ruleset_checksum: string;
};

export type RuleImpact = {
  schema_version: "1.0";
  profile_id: string;
  impact: { molds: number; revisions: number; cad_artifacts: number; historical_reviews: number };
  note: string;
};

type RuleProfileList = {
  schema_version: "1.0";
  items: RuleProfile[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export async function fetchRuleProfiles(): Promise<RuleProfile[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rule-profiles`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Rule profile endpoint returned HTTP ${response.status}`);
  return ((await response.json()) as RuleProfileList).items;
}

async function ruleRequest<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await apiFetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error?.message || `Rule workflow returned HTTP ${response.status}`);
  return payload as T;
}

export async function fetchRuleProfile(id: string): Promise<RuleProfile> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rule-profiles/${id}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Rule profile endpoint returned HTTP ${response.status}`);
  return await response.json();
}

export async function fetchRuleProfileDiff(id: string, against: string): Promise<RuleProfileDiff> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rule-profiles/${id}/diff?against=${encodeURIComponent(against)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Rule diff endpoint returned HTTP ${response.status}`);
  return await response.json();
}

export async function updateRuleProfile(
  profile: RuleProfile,
  input: {
    change_summary: string;
    rules: RuleProfile["rules"];
    applicability?: RuleApplicability[];
    priority?: number;
    is_default?: boolean;
    effective_from?: string | null;
    effective_to?: string | null;
    resolution_status?: "eligible" | "disabled";
    reason: string;
  },
): Promise<RuleProfile> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rule-profiles/${profile.profile_id}`, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, row_version: profile.row_version }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error?.message || `Rule update returned HTTP ${response.status}`);
  return payload;
}

export function createRuleProfile(input: {
  action: "blank" | "template" | "clone";
  profile_key?: string;
  source_profile_id?: string;
  version: string;
  change_summary: string;
  reason: string;
}): Promise<RuleProfile> {
  return ruleRequest("/api/v1/rule-profiles", input);
}

export function cloneRuleProfile(
  source: RuleProfile,
  input: { version: string; changeSummary: string; reason: string },
): Promise<RuleProfile> {
  return ruleRequest("/api/v1/rule-profiles", {
    action: "clone",
    source_profile_id: source.profile_id,
    version: input.version,
    change_summary: input.changeSummary,
    reason: input.reason,
  });
}

export function transitionRuleProfile(
  profile: RuleProfile,
  action: "test" | "submit" | "approve" | "publish" | "retire",
  reason: string,
): Promise<RuleProfile> {
  return ruleRequest(`/api/v1/rule-profiles/${profile.profile_id}/actions`, {
    action,
    reason,
    row_version: profile.row_version,
  });
}

export function validateRuleProfile(profile: RuleProfile): Promise<RuleValidation> {
  return ruleRequest(`/api/v1/rule-profiles/${profile.profile_id}/validate`, {});
}

export function previewRuleImpact(profile: RuleProfile): Promise<RuleImpact> {
  return ruleRequest(`/api/v1/rule-profiles/${profile.profile_id}/impact-preview`, {});
}
