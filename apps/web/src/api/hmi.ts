import { apiFetch } from "./client";

export type HMIField = {
  field_id: string;
  parameter_code: string;
  display_label: string;
  raw_text: string;
  value: number | null;
  unit: string;
  confidence: number;
  source_region: { x: number; y: number; w: number; h: number; coordinate_space: string };
  validation_status: string;
  review_status: "not_required" | "needs_review" | "confirmed" | "corrected" | "rejected";
  reviewer_correction: { value: number | null; unit: string; reviewed_by: string } | null;
  effective_value: number | null;
  effective_unit: string;
};

export type HMIExtraction = {
  schema_version: "1.0";
  extraction_id: string;
  image_artifact_version_id: string;
  image_sha256: string;
  image_download_url: string;
  profile: string;
  extractor_version: string;
  status: string;
  image_dimensions: { width: number; height: number };
  preprocessing: Record<string, unknown>;
  fields: HMIField[];
  review_status: "needs_review" | "ready_for_export" | "rejected";
  export_status: "ready" | "blocked_pending_review";
  exports: HMIExport[];
  lineage_ref: string;
  created_at: string;
  limitations: string[];
};

export type HMIExport = {
  export_id: string;
  artifact_version_id: string;
  template_version: string;
  download_url: string;
  created_at?: string;
};

export type HMIReviewDecision = {
  field_id: string;
  action: "confirm" | "correct" | "reject";
  value?: number;
  unit?: string;
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

export function hmiResourceUrl(path: string): string {
  return `${apiBaseUrl}${path}`;
}

export async function fetchDemoHMI(): Promise<File> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/hmi/demo-fixture?variant=low-confidence`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return new File([await response.blob()], "demo-hmi-low-confidence.png", { type: "image/png" });
}

export async function uploadHMI(file: File): Promise<HMIExtraction> {
  const form = new FormData();
  form.append("file", file);
  form.append("profile", "demo-generic-injection@1.0");
  const response = await apiFetch(`${apiBaseUrl}/api/v1/hmi-extractions`, {
    method: "POST",
    body: form,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function reviewHMI(
  extractionId: string,
  decisions: HMIReviewDecision[],
): Promise<HMIExtraction> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/hmi-extractions/${extractionId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ reviewed_by: "demo-engineer", fields: decisions }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}

export async function exportHMI(extractionId: string): Promise<HMIExport> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/hmi-extractions/${extractionId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ created_by: "demo-engineer" }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}
