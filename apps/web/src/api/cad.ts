import { apiFetch } from "./client";

export type ArtifactVersion = {
  artifact_version_id: string;
  original_filename: string;
  media_type: string;
  format: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
};

export type CADModelResult = {
  cad_model_id: string;
  artifact_version_id: string;
  cad_format: string;
  unit_system: string;
  parser: { name: string; version: string };
  geometry_status: "queued" | "running" | "succeeded" | "failed";
  bounding_box: {
    min: Record<"x" | "y" | "z", number>;
    max: Record<"x" | "y" | "z", number>;
    size: Record<"x" | "y" | "z", number>;
  };
  volume: number | null;
  surface_area: number;
  face_count: number;
  edge_count: number;
  surface_type_histogram: Record<string, number>;
  quality_flags: string[];
  preview: ArtifactVersion;
  similarity_index: {
    feature_set_id: string;
    schema_version: string;
    extractor_version: string;
    index_version: string;
    status: "pending" | "indexed" | "failed";
    error_code: string | null;
  } | null;
};

export type CADJob = {
  schema_version: "1.0";
  job_id: string;
  capability: string;
  state:
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "cancel_requested"
    | "cancelled"
    | "expired";
  stage: string;
  progress: number;
  attempt: number;
  artifact_version_id: string;
  correlation_id: string;
  result: CADModelResult | null;
  error: { code: string; message: string; retryable: boolean; correlation_id: string } | null;
};

export type CADUploadAccepted = {
  status: "accepted";
  artifact_id: string;
  artifact_version_id: string;
  job_id: string;
  idempotent_replay: boolean;
  warnings: string[];
  links: { artifact: string; status: string; ui: string };
};

export type CADArtifactSummary = {
  artifact_id: string;
  name: string;
  kind: "cad_source";
  classification: string;
  dataset_id: string;
  product_type: string;
  material_code: string;
  created_at: string;
  jobs: CADJob[];
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

export async function uploadCAD(
  file: File,
  artifactName: string,
  idempotencyKey: string,
  metadata: { datasetId: string; productType: string; materialCode: string },
): Promise<CADUploadAccepted> {
  const body = new FormData();
  body.append("file", file);
  if (artifactName.trim()) body.append("artifact_name", artifactName.trim());
  body.append("idempotency_key", idempotencyKey);
  body.append("dataset_id", metadata.datasetId);
  if (metadata.productType.trim()) body.append("product_type", metadata.productType.trim());
  if (metadata.materialCode.trim()) body.append("material_code", metadata.materialCode.trim());

  const response = await apiFetch(`${apiBaseUrl}/api/v1/cad-artifacts`, {
    method: "POST",
    body,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as CADUploadAccepted;
}

export async function fetchCADJob(jobId: string): Promise<CADJob> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as CADJob;
}

export async function fetchRecentCAD(): Promise<CADArtifactSummary[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cad-artifacts`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as {
    schema_version: "1.0";
    items: CADArtifactSummary[];
  };
  return payload.items;
}
