import { apiFetch, configureApiXHR, notifyApiUnauthorized } from "./client";

export type ArtifactVersion = {
  artifact_version_id: string;
  original_filename: string;
  media_type: string;
  format: string;
  size_bytes: number;
  sha256: string;
  version_number?: number;
  classification?: string;
  malware_status?: string;
  source_system?: string;
  supersedes_id?: string | null;
  created_at?: string;
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
  feature_sets?: Array<{
    feature_set_id: string;
    schema_version: string;
    extractor_version: string;
    index_collection: string;
    index_version: string;
    status: string;
    error_code: string | null;
    created_at: string;
  }>;
};

type CADJobBase = {
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
  error: { code: string; message: string; retryable: boolean; correlation_id: string } | null;
};

export type CADJob = CADJobBase & {
  result: CADModelResult | null;
};

export type CADArtifactJob = CADJobBase & {
  // Artifact history contains capability-dependent results, including similarity and review payloads.
  result: unknown;
};

export function isCADModelJob(job: CADArtifactJob): job is CADJob & { result: CADModelResult } {
  if (!job.capability.startsWith("cad.parse@") || job.state !== "succeeded") return false;
  if (!job.result || typeof job.result !== "object") return false;
  const result = job.result as Partial<CADModelResult>;
  return (
    typeof result.cad_model_id === "string" &&
    typeof result.artifact_version_id === "string" &&
    typeof result.geometry_status === "string" &&
    typeof result.parser?.name === "string" &&
    typeof result.parser?.version === "string" &&
    Array.isArray(result.quality_flags)
  );
}

export type CADUploadAccepted = {
  status: "accepted";
  artifact_id: string;
  artifact_version_id: string;
  version_number: number;
  version_action: "new_artifact" | "new_version";
  job_id: string;
  ingestion_mode: "quick_analysis" | "governed_archive";
  governance_status: "unassigned" | "governed";
  mold_revision_id: string | null;
  idempotent_replay: boolean;
  warnings: string[];
  links: { artifact: string; status: string; ui: string };
};

export type CADUploadProgress = {
  loaded: number;
  total: number;
  percent: number;
};

export type CADArtifactSummary = {
  artifact_id: string;
  name: string;
  kind: "cad_source";
  classification: string;
  dataset_id: string;
  product_type: string;
  material_code: string;
  mold_revision_id: string | null;
  mold_revision: { revision_code: string; mold_id: string; mold_code: string } | null;
  lifecycle_status: string;
  quality_status: string;
  created_at: string;
  updated_at: string;
  row_version: number;
  source: {
    type: string;
    fixture_id?: string;
    role?: string;
    scenario?: string;
    rank_group?: string;
    dataset_version?: string;
  } | null;
  jobs: CADArtifactJob[];
  versions?: ArtifactVersion[];
  lineage?: CADLineageEdge[];
};

export type CADHistorySummary = {
  artifact_id: string;
  name: string;
  kind: "cad_source";
  classification: string;
  dataset_id: string;
  product_type: string;
  material_code: string;
  mold_revision_id: string | null;
  mold_revision: string | null;
  lifecycle_status: string;
  quality_status: string;
  version_count: number;
  job_count: number;
  latest_version_id: string | null;
  latest_format: string | null;
  latest_job_state: string | null;
  created_at: string;
};

export type CADLineageEdge = {
  edge_id: string;
  from_artifact_version_id: string;
  to_artifact_version_id: string;
  relationship: string;
  job_id: string;
  direction: "inbound" | "outbound";
  created_at: string;
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

function xhrErrorMessage(xhr: XMLHttpRequest): string {
  try {
    const payload = JSON.parse(xhr.responseText) as { error?: { message?: string; code?: string } };
    return payload.error?.message || payload.error?.code || `HTTP ${xhr.status}`;
  } catch {
    return `HTTP ${xhr.status || 0}`;
  }
}

export async function uploadCAD(
  file: File,
  artifactName: string,
  idempotencyKey: string,
  metadata: {
    datasetId: string;
    productType: string;
    materialCode: string;
    uploadMode: "quick_analysis" | "governed_archive";
    moldRevisionId?: string;
    artifactId?: string;
  },
  options: { onProgress?: (progress: CADUploadProgress) => void } = {},
): Promise<CADUploadAccepted> {
  const body = new FormData();
  body.append("file", file);
  if (artifactName.trim()) body.append("artifact_name", artifactName.trim());
  body.append("idempotency_key", idempotencyKey);
  body.append("dataset_id", metadata.datasetId);
  body.append("ingestion_mode", metadata.uploadMode);
  if (metadata.productType.trim()) body.append("product_type", metadata.productType.trim());
  if (metadata.materialCode.trim()) body.append("material_code", metadata.materialCode.trim());
  if (metadata.moldRevisionId) body.append("mold_revision_id", metadata.moldRevisionId);
  if (metadata.artifactId) body.append("artifact_id", metadata.artifactId);

  return await new Promise<CADUploadAccepted>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBaseUrl}/api/v1/cad-artifacts`);
    configureApiXHR(xhr, "POST");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) return;
      options.onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percent: Math.min(100, Math.round((event.loaded / event.total) * 100)),
      });
    };
    xhr.onerror = () => reject(new Error("CAD upload network error."));
    xhr.onabort = () => reject(new Error("CAD upload was cancelled."));
    xhr.onload = () => {
      notifyApiUnauthorized(xhr.status);
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhrErrorMessage(xhr)));
        return;
      }
      try {
        options.onProgress?.({ loaded: file.size, total: file.size, percent: 100 });
        resolve(JSON.parse(xhr.responseText) as CADUploadAccepted);
      } catch {
        reject(new Error("CAD upload returned an invalid response."));
      }
    };
    xhr.send(body);
  });
}

export async function fetchCADJob(jobId: string): Promise<CADJob> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as CADJob;
}

export async function fetchRecentCAD(datasetId?: string): Promise<CADArtifactSummary[]> {
  const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : "";
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cad-artifacts${query}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as {
    schema_version: "1.0";
    items: CADArtifactSummary[];
  };
  return payload.items;
}

export async function fetchCADHistory(): Promise<CADHistorySummary[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cad-artifacts?view=summary`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { items: CADHistorySummary[] };
  return payload.items;
}

export async function fetchCADArtifactDetail(id: string): Promise<CADArtifactSummary> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/cad-artifacts/${id}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return await response.json();
}
