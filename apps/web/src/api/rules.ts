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
  rule_count: number;
  rules: Array<ReviewRule & { enabled: boolean }>;
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
