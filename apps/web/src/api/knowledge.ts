import type { CADJob } from "./cad";
import { apiFetch } from "./client";

export type KnowledgeDocument = {
  document_id: string;
  artifact_id: string;
  artifact_version_id: string;
  title: string;
  original_filename: string;
  format: "txt" | "md";
  sha256: string;
  document_type: "demo_sop" | "design_guideline" | "trial_report" | "case_note";
  authority_level: "demo" | "reviewed_demo";
  effective_from: string | null;
  effective_to: string | null;
  owner: string;
  classification: string;
  acl_scopes: string[];
  language: "en" | "zh-Hant";
  parser_version: string;
  chunker_version: string;
  ingestion_status: "queued" | "running" | "indexed" | "quarantined" | "failed" | "obsolete";
  injection_scan_status: "pending" | "clear" | "suspicious";
  injection_findings: string[];
  chunk_count: number;
  indexed_at: string | null;
  error_code: string | null;
  download_url: string;
  created_at: string;
};

export type KnowledgeJob = Omit<CADJob, "result"> & { result: KnowledgeDocument | null };

export type KnowledgeUploadAccepted = {
  status: "accepted";
  artifact_id: string;
  artifact_version_id: string;
  document_id: string;
  job_id: string;
  idempotent_replay: boolean;
};

export type KnowledgeCitation = {
  citation_id: string;
  artifact_version_id: string;
  document_id: string;
  title: string;
  locator: string;
  authority: string;
  effective_from: string | null;
  effective_to: string | null;
  source_url: string;
};

export type KnowledgeResultItem = {
  rank: number;
  chunk_id: string;
  excerpt: string;
  score: number;
  score_breakdown: Record<"lexical" | "vector" | "authority" | "freshness", number>;
  citation_id: string;
};

export type KnowledgeSearchResult = {
  search_id: string;
  schema_version: "1.0";
  answer_mode: "extractive_evidence";
  answer: string;
  claims: { text: string; evidence_refs: string[]; evidence_type: "document_excerpt" }[];
  citations: KnowledgeCitation[];
  results: KnowledgeResultItem[];
  abstained: boolean;
  retrieved_at: string;
  principal_scope_source: "server_demo_policy";
  limitations: string[];
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

export async function uploadKnowledge(
  file: File,
  metadata: {
    title: string;
    documentType: string;
    authorityLevel: string;
    language: string;
  },
): Promise<KnowledgeUploadAccepted> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", metadata.title.trim());
  body.append("document_type", metadata.documentType);
  body.append("authority_level", metadata.authorityLevel);
  body.append("language", metadata.language);
  body.append("idempotency_key", `web-knowledge-${Date.now()}-${file.name}-${file.size}`);
  const response = await apiFetch(`${apiBaseUrl}/api/v1/knowledge-documents`, {
    method: "POST",
    body,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as KnowledgeUploadAccepted;
}

export async function fetchKnowledgeJob(jobId: string): Promise<KnowledgeJob> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as KnowledgeJob;
}

export async function fetchKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/knowledge-documents`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = (await response.json()) as { items: KnowledgeDocument[] };
  return Array.isArray(payload.items) ? payload.items : [];
}

export async function searchKnowledge(
  query: string,
  filters: { documentTypes: string[]; authorityLevels: string[]; topK: number },
): Promise<KnowledgeSearchResult> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/knowledge-searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      query,
      document_types: filters.documentTypes,
      authority_levels: filters.authorityLevels,
      top_k: filters.topK,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as KnowledgeSearchResult;
}
