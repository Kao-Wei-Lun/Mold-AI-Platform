export const DEEP_LINK_VERSION = "1.0" as const;

export type DeepLinkTarget =
  | "home"
  | "job"
  | "similarity"
  | "design_review"
  | "knowledge"
  | "process_trial"
  | "cae"
  | "hmi"
  | "rule_profile"
  | "ingestion_batch";

export type DeepLinkContext = {
  deep_link_version: typeof DEEP_LINK_VERSION;
  target: DeepLinkTarget;
  refs: Record<string, string>;
  correlation_id: string;
};

export type DeepLinkError = {
  code:
    | "DEEP_LINK_VERSION_UNSUPPORTED"
    | "DEEP_LINK_TARGET_INVALID"
    | "DEEP_LINK_REF_INVALID";
  message: string;
};

export type DeepLinkState = { context: DeepLinkContext | null; error: DeepLinkError | null };

const targetRefs: Record<DeepLinkTarget, { required: string[]; optional: string[] }> = {
  home: { required: [], optional: [] },
  job: { required: ["job_id"], optional: [] },
  similarity: { required: ["search_id"], optional: ["candidate_id"] },
  design_review: { required: ["review_id"], optional: ["finding_id"] },
  knowledge: { required: ["knowledge_search_id"], optional: ["citation_id"] },
  process_trial: { required: ["process_search_id"], optional: ["case_id"] },
  cae: { required: ["cae_comparison_id"], optional: ["metric_code"] },
  hmi: { required: ["hmi_extraction_id"], optional: [] },
  rule_profile: { required: ["profile_id"], optional: [] },
  ingestion_batch: { required: ["batch_id"], optional: [] },
};

const uuidRefs = new Set([
  "job_id",
  "search_id",
  "candidate_id",
  "review_id",
  "finding_id",
  "knowledge_search_id",
  "citation_id",
  "process_search_id",
  "case_id",
  "cae_comparison_id",
  "hmi_extraction_id",
  "profile_id",
  "batch_id",
]);

const forbiddenFields = new Set([
  "token",
  "api_key",
  "tunnel_id",
  "workspace_url",
  "return_url",
  "javascript",
  "permission",
]);

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function failure(code: DeepLinkError["code"], message: string): DeepLinkState {
  return { context: null, error: { code, message } };
}

function correlationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `deep-link-${Date.now()}`;
}

export function parseDeepLink(search: string): DeepLinkState {
  const params = new URLSearchParams(search);
  if ([...params.keys()].length === 0) return { context: null, error: null };
  for (const key of new Set(params.keys())) {
    if (params.getAll(key).length > 1) {
      return failure("DEEP_LINK_REF_INVALID", `Duplicate parameter: ${key}`);
    }
  }

  const version = params.get("deep_link_version");
  if (version !== DEEP_LINK_VERSION) {
    return failure(
      "DEEP_LINK_VERSION_UNSUPPORTED",
      "This Mold AI link uses an unsupported contract version.",
    );
  }
  const rawTarget = params.get("target");
  if (!rawTarget || !(rawTarget in targetRefs)) {
    return failure("DEEP_LINK_TARGET_INVALID", "This Mold AI target is not supported.");
  }
  const target = rawTarget as DeepLinkTarget;
  const schema = targetRefs[target];
  const allowed = new Set(["deep_link_version", "target", ...schema.required, ...schema.optional]);
  for (const key of params.keys()) {
    if (forbiddenFields.has(key) || !allowed.has(key)) {
      return failure("DEEP_LINK_REF_INVALID", `Unexpected parameter: ${key}`);
    }
  }

  const refs: Record<string, string> = {};
  for (const key of [...schema.required, ...schema.optional]) {
    const value = params.get(key) || "";
    if (!value) {
      if (schema.required.includes(key)) {
        return failure("DEEP_LINK_REF_INVALID", `Missing parameter: ${key}`);
      }
      continue;
    }
    if (
      value.length > 128 ||
      /[\u0000-\u001f\u007f]/.test(value) ||
      (uuidRefs.has(key) && !uuidPattern.test(value))
    ) {
      return failure("DEEP_LINK_REF_INVALID", `Invalid parameter: ${key}`);
    }
    refs[key] = value;
  }
  return {
    context: {
      deep_link_version: DEEP_LINK_VERSION,
      target,
      refs,
      correlation_id: correlationId(),
    },
    error: null,
  };
}

export function reportDeepLinkEvent(
  event: "opened" | "resolved" | "failed",
  context: DeepLinkContext,
  detail: { status: string; latency_ms?: number },
): void {
  window.dispatchEvent(
    new CustomEvent(`mold-ai:deep-link-${event}`, {
      detail: {
        contract_version: context.deep_link_version,
        target: context.target,
        correlation_id: context.correlation_id,
        ...detail,
      },
    }),
  );
}
