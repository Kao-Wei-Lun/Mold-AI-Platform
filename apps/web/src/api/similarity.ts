import type { CADJob, CADModelResult } from "./cad";
import { apiFetch } from "./client";

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
  available_lane_score?: number;
  evidence_coverage?: number;
  score_policy?: string;
  geometry_ranking?: {
    score: number;
    policy: string;
    block_scores: Record<string, number>;
    block_coverage: number | null;
    coarse_cosine: number;
    fallback_reason: string | null;
  };
  geometry_validation_status?: string;
  sub_scores: Record<string, number | null>;
  effective_weights: Record<string, number>;
  feature_availability: Record<string, boolean>;
  similarities: SimilarityEvidence[];
  differences: SimilarityEvidence[];
  quality_flags: string[];
  preview: { artifact_version_id: string; download_url: string } | null;
};

export type SimilarityResult = {
  schema_version: "1.0" | "1.1";
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

export type SimilarityComparison = {
  schema_version: "1.0";
  comparison_id: string;
  search_id: string;
  candidate_artifact_version_id: string;
  created: boolean;
  alignment_status: "full" | "partial" | "skipped";
  transform: number[][];
  result: {
    alignment_status: "full" | "partial" | "skipped";
    alignment: {
      pca_rmse: number;
      final_rmse: number;
      icp_attempted: boolean;
      icp_converged: boolean;
      icp_iterations: number;
      symmetry_ambiguity: boolean;
    };
    deviation: {
      mode: "signed" | "unsigned";
      minimum: number;
      maximum: number;
      rmse: number;
      sample_count: number;
      tolerance: number;
    };
    roi: { min: number[]; max: number[] } | null;
    roi_similarity_score: number | null;
    heatmap: { positions: number[][]; deviations: number[] };
  };
  lineage_ref: string;
};

export type SimilarityEngineeringProfile = {
  artifact_version_id: string;
  tolerance_strictness: "standard" | "precision";
  ctq_count: number;
  surface_roughness_ra: number | null;
  flow_length_ratio: number | null;
  projected_area: number | null;
  clamp_force_band: string | null;
  gate_type: string | null;
  source_mode: string;
  row_version: number;
  updated_by: string;
  updated_at: string;
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
  const response = await apiFetch(`${apiBaseUrl}/api/v1/similarity-searches`, {
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
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as SimilarityJob;
}

export async function fetchSimilaritySearch(searchId: string): Promise<SimilarityJob> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/similarity-searches/${searchId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { job_id: string };
  return fetchSimilarityJob(payload.job_id);
}

export async function createSimilarityComparison(
  searchId: string,
  candidateVersionId: string,
  roi?: { min: number[]; max: number[] },
): Promise<SimilarityComparison> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/similarity-searches/${searchId}/candidates/${candidateVersionId}/comparison`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ schema_version: "1.0", roi: roi || null }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as SimilarityComparison;
}

export async function fetchSimilarityEngineeringProfile(
  artifactVersionId: string,
): Promise<SimilarityEngineeringProfile | null> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/artifact-versions/${artifactVersionId}/similarity-engineering-profile`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return ((await response.json()) as { profile: SimilarityEngineeringProfile | null }).profile;
}

export async function saveSimilarityEngineeringProfile(
  artifactVersionId: string,
  profile: Omit<SimilarityEngineeringProfile, "artifact_version_id" | "source_mode" | "updated_by" | "updated_at">,
): Promise<SimilarityEngineeringProfile> {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/artifact-versions/${artifactVersionId}/similarity-engineering-profile`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(profile),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return ((await response.json()) as { profile: SimilarityEngineeringProfile }).profile;
}

export async function recordSimilarityFeedback(
  searchId: string,
  candidateArtifactVersionId: string,
  action: "accept_reference" | "not_relevant",
  reasonCode = "",
): Promise<{ feedback_id: string; created: boolean; action: string }> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/similarity-searches/${searchId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      candidate_artifact_version_id: candidateArtifactVersionId,
      action,
      reason_code: reasonCode,
      idempotency_key: `web-feedback-${searchId}-${candidateArtifactVersionId}-${action}-${Date.now()}`,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as { feedback_id: string; created: boolean; action: string };
}
