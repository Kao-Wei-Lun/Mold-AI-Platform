import type { ArtifactVersion, CADJob, CADModelResult } from "./cad";

export type ReviewResultState =
  | "PASS"
  | "FAIL"
  | "NOT_APPLICABLE"
  | "NOT_EVALUATED"
  | "ERROR";

export type ReviewRule = {
  rule_version_id: string;
  rule_id: string;
  rule_version: string;
  title: string;
  description: string;
  evaluator: string;
  condition: { operator: "lte" | "gte" | "eq"; limit: number | null; unit: string; tolerance: number };
  severity: string;
  risk_type: string;
  recommendation: string;
  reference: { document: string; revision: string; classification: string };
};

export type ReviewDecision = {
  decision_id: string;
  decision: "accepted" | "rejected" | "waived";
  reason: string;
  decided_by: string;
  approved_by: string | null;
  created_at: string;
};

export type ReviewFinding = {
  finding_id: string;
  rule: ReviewRule;
  result: ReviewResultState;
  actual_value: number | null;
  limit_value: number | null;
  unit: string;
  severity: string;
  risk_type: string;
  geometry_location: { scope: string };
  evidence_refs: string[];
  quality_flags: string[];
  message: string;
  decisions: ReviewDecision[];
};

export type DesignReviewResult = {
  review_id: string;
  job_id: string;
  review_status: string;
  artifact_version_id: string;
  profile: {
    profile_key: string;
    version: string;
    status: string;
    ruleset_checksum: string;
    rule_count: number;
  };
  geometry_engine_version: string;
  input_snapshot: Record<string, unknown>;
  context: Record<string, number>;
  summary: {
    total: number;
    decision: "PASS" | "FAIL" | "INCOMPLETE";
    counts: Record<ReviewResultState, number>;
  };
  preview: ArtifactVersion | null;
  findings: ReviewFinding[];
  limitations: string[];
};

export type DesignReviewJob = Omit<CADJob, "result"> & { result: DesignReviewResult | null };

export type DesignReviewAccepted = {
  status: "accepted";
  review_id: string;
  job_id: string;
  idempotent_replay: boolean;
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

export async function createDesignReview(
  query: CADModelResult,
  context: Record<string, number>,
): Promise<DesignReviewAccepted> {
  const response = await fetch(`${apiBaseUrl}/api/v1/design-reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      schema_version: "1.0",
      cad_artifact_version_id: query.artifact_version_id,
      profile: "demo-general-design@1.0",
      context,
      idempotency_key: `web-review-${Date.now()}-${query.artifact_version_id}`,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as DesignReviewAccepted;
}

export async function fetchDesignReviewJob(jobId: string): Promise<DesignReviewJob> {
  const response = await fetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as DesignReviewJob;
}

export async function createFindingDecision(
  reviewId: string,
  findingId: string,
  input: {
    decision: "accepted" | "rejected" | "waived";
    reason: string;
    approvedBy: string;
  },
): Promise<ReviewDecision> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/design-reviews/${reviewId}/findings/${findingId}/decisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        decision: input.decision,
        reason: input.reason,
        decided_by: "demo-reviewer",
        approved_by: input.approvedBy,
      }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { record: ReviewDecision };
  return payload.record;
}
