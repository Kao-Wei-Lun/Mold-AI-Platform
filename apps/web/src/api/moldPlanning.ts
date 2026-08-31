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
