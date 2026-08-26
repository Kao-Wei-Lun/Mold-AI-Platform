import type { CADJob, CADModelResult } from "./cad";

export type SimilarityEvidence = {
  type: string;
  message: string;
  evidence_ref: string;
};

export type SimilarityMatch = {
  rank: number;
  artifact_id: string;
  artifact_version_id: string;
  artifact_name: string;
  dataset_id: string;
  product_type: string;
  material_code: string;
  coarse_score: number;
  overall_score: number;
  sub_scores: Record<"geometry" | "dimension" | "topology" | "metadata", number | null>;
  effective_weights: Record<string, number>;
  feature_availability: Record<string, boolean>;
  similarities: SimilarityEvidence[];
  differences: SimilarityEvidence[];
  quality_flags: string[];
  preview: { artifact_version_id: string; download_url: string } | null;
};

export type SimilarityResult = {
  schema_version: "1.0";
  search_id: string;
  query_ref: {
    artifact_id: string;
    cad_artifact_version_id: string;
    artifact_name: string;
    preview: { artifact_version_id: string; download_url: string } | null;
  };
  profile: string;
  profile_weights: Record<string, number>;
  feature_schema_version: string;
  extractor_version: string;
  index_version: string;
  filters: Record<string, string[]>;
  result_count: number;
  results: SimilarityMatch[];
  limitations: string[];
  lineage_ref: string;
};

export type SimilarityJob = Omit<CADJob, "result"> & { result: SimilarityResult | null };

export type SimilarityAccepted = {
  status: "accepted";
  search_id: string;
  job_id: string;
  idempotent_replay: boolean;
  links: { status: string; result: string; ui: string };
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

export async function createSimilaritySearch(
  query: CADModelResult,
  filters: { datasetIds: string[]; productTypes: string[]; materialCodes: string[] },
  topK: number,
): Promise<SimilarityAccepted> {
  const response = await fetch(`${apiBaseUrl}/api/v1/similarity-searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      schema_version: "1.0",
      idempotency_key: `web-sim-${Date.now()}-${query.artifact_version_id}`,
      query: { cad_artifact_version_id: query.artifact_version_id },
      filters: {
        dataset_ids: filters.datasetIds,
        product_types: filters.productTypes,
        material_codes: filters.materialCodes,
      },
      top_k: topK,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as SimilarityAccepted;
}

export async function fetchSimilarityJob(jobId: string): Promise<SimilarityJob> {
  const response = await fetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as SimilarityJob;
}
