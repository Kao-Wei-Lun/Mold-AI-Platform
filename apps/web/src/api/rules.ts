import { apiFetch } from "./client";
import type { ReviewRule } from "./designReview";

export type RuleProfile = {
  profile_id: string;
  profile_key: string;
  version: string;
  status: string;
  owner: string;
  approved_by: string;
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
