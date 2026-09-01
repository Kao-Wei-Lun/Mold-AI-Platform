import { apiFetch } from "./client";

export type RegistryProject = {
  id: string;
  code: string;
  name: string;
  description: string;
  scope: string;
  classification: string;
  status: "active" | "archived";
  row_version: number;
  part_count: number;
  mold_count: number;
  created_at?: string;
  updated_at?: string;
};

export type RegistryPart = {
  id: string;
  project_id: string;
  project_code: string;
  part_number: string;
  name: string;
  product_type: string;
  material_code: string;
  status: "active" | "archived";
  row_version: number;
  mold_count?: number;
  molds?: RegistryMold[];
  created_at?: string;
  updated_at?: string;
};

export type RegistryMold = {
  id: string;
  project_id: string;
  project_code: string;
  product_part_id: string | null;
  part_number: string | null;
  mold_code: string;
  name: string;
  mold_type: string;
  cavity_count: number;
  status: "active" | "retired" | "archived";
  row_version: number;
  revision_count: number;
  current_revision_id: string | null;
  current_revision_code: string | null;
  artifact_count: number;
  allowed_actions?: Array<"edit" | "create_revision" | "retire" | "reactivate" | "archive">;
  revisions?: RegistryRevision[];
  created_at?: string;
  updated_at?: string;
};

export type RegistryPage = {
  number: number;
  size: number;
  total: number;
  sort: string;
  has_next: boolean;
};

export type RegistryListPayload<T> = {
  schema_version: "1.0";
  items: T[];
  page: RegistryPage;
};

export type RegistryOverview = {
  schema_version: "1.0";
  counts: {
    active_projects: number;
    active_molds: number;
    released_revisions: number;
    draft_revisions: number;
    released_without_cad: number;
    pending_mapping: number;
  };
};

export type RegistryQuery = {
  q?: string;
  status?: string;
  project_id?: string;
  part_id?: string;
  mold_type?: string;
  product_type?: string;
  material_code?: string;
  revision_status?: string;
  has_cad?: "true" | "false";
  view?: "table" | "tree";
  sort?: string;
  page?: number;
  page_size?: number;
};

export type RegistryRevision = {
  id: string;
  mold_id: string;
  mold_code: string;
  revision_code: string;
  status: "draft" | "released" | "superseded" | "archived";
  change_summary: string;
  source_system: string;
  source_revision_id: string | null;
  row_version: number;
  released_at: string | null;
  artifact_count: number;
  allowed_actions?: Array<"edit" | "release" | "archive">;
  artifacts?: RegistryArtifactGovernance[];
  created_at?: string;
  updated_at?: string;
};

export type RegistryArtifactGovernance = {
  artifact_id: string;
  name: string;
  mold_revision_id: string | null;
  mold_revision: string | null;
  lifecycle_status: string;
  quality_status: string;
  archive_reason: string | null;
  archived_at: string | null;
  row_version: number;
  updated_at: string;
  references: { versions: number; jobs: number; feature_sets: number; design_reviews: number };
  hard_delete_allowed: boolean;
};

export type RegistryMoldImpact = {
  schema_version: "1.0";
  mold_id: string;
  mold_code: string;
  status: RegistryMold["status"];
  row_version: number;
  impact: {
    draft_revisions: number;
    released_revisions: number;
    cad_artifacts: number;
    mold_plans: number;
    design_reviews: number;
    similarity_searches: number;
    cae_studies: number;
    trial_cases: number;
  };
  allowed_actions: NonNullable<RegistryMold["allowed_actions"]>;
};

export type RegistryEngineeringRecord = {
  record_type: "mold_plan" | "design_review" | "similarity_search" | "cae_study" | "trial_case";
  record_id: string;
  title: string;
  status: string;
  owner: string;
  revision_ref: string;
  created_at: string;
  updated_at: string;
  deep_link: string;
};

export type RegistryEngineeringHistory = {
  schema_version: "1.0";
  subject: { mold_id: string; mold_code: string; revision_id: string | null; revision_code: string | null };
  counts: Record<RegistryEngineeringRecord["record_type"], number>;
  items: RegistryEngineeringRecord[];
  page: { number: number; size: number; total: number; has_next: boolean };
  lineage: {
    nodes: Array<{ id: string; type: string; label: string; status: string }>;
    edges: Array<{ from: string; to: string; relationship: string }>;
  };
  audit_events: Array<{
    id: string;
    event_type: string;
    actor_id: string;
    target_refs: string[];
    detail: Record<string, unknown>;
    payload_hash: string;
    created_at: string;
  }>;
};

export type RegistryDataQuality = {
  schema_version: "1.0";
  summary: { total: number; critical: number; warning: number; info: number; mapping_required: number };
  items: Array<{
    code: string;
    severity: "critical" | "warning" | "info";
    title: string;
    message: string;
    entity_type: string;
    entity_id: string;
    action_path: string;
  }>;
  recent_imports: Array<{
    batch_id: string;
    source_name: string;
    status: string;
    issue_count: number;
    created_by: string;
    created_at: string;
    deep_link: string;
  }>;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export class RegistryError extends Error {
  constructor(message: string, public status: number, public code: string) {
    super(message);
    this.name = "RegistryError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const contentType = response.headers?.get?.("content-type") || "";
  if (contentType && !contentType.toLowerCase().includes("json")) {
    throw new RegistryError(
      `Registry service returned an invalid response (HTTP ${response.status}).`,
      response.status,
      "REGISTRY_RESPONSE_INVALID",
    );
  }
  let payload: any;
  try {
    payload = await response.json();
  } catch {
    throw new RegistryError(
      `Registry service returned an invalid response (HTTP ${response.status}).`,
      response.status,
      "REGISTRY_RESPONSE_INVALID",
    );
  }
  if (!response.ok) {
    const message = payload?.error?.message || `Registry returned HTTP ${response.status}`;
    throw new RegistryError(message, response.status, payload?.error?.code || "REGISTRY_ERROR");
  }
  return payload as T;
}

function withQuery(path: string, query: RegistryQuery = {}): string {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, String(value));
    }
  });
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

export function fetchRegistryOverview(): Promise<RegistryOverview> {
  return request("/api/v1/registry/overview");
}

export function fetchRegistryDataQuality(): Promise<RegistryDataQuality> {
  return request("/api/v1/registry/data-quality");
}

export function fetchRegistryProjects(query: RegistryQuery = {}): Promise<RegistryListPayload<RegistryProject>> {
  return request(withQuery("/api/v1/registry/projects", query));
}

export function fetchRegistryParts(query: RegistryQuery = {}): Promise<RegistryListPayload<RegistryPart>> {
  return request(withQuery("/api/v1/registry/parts", query));
}

export function fetchRegistryMolds(query: RegistryQuery = {}): Promise<RegistryListPayload<RegistryMold>> {
  return request(withQuery("/api/v1/registry/molds", query));
}

export function fetchRegistryRevisions(query: RegistryQuery = {}): Promise<RegistryListPayload<RegistryRevision>> {
  return request(withQuery("/api/v1/registry/revisions", query));
}

export async function fetchRegistry(): Promise<{
  projects: RegistryProject[];
  parts: RegistryPart[];
  molds: RegistryMold[];
  revisions: RegistryRevision[];
}> {
  const [projectPayload, partPayload, moldPayload, revisionPayload] = await Promise.all([
    fetchRegistryProjects({ page_size: 100 }),
    fetchRegistryParts({ page_size: 100 }),
    fetchRegistryMolds({ page_size: 100 }),
    fetchRegistryRevisions({ page_size: 100 }),
  ]);
  return {
    projects: projectPayload.items,
    parts: partPayload.items,
    molds: moldPayload.items,
    revisions: revisionPayload.items,
  };
}

export function fetchRegistryProjectDetail(id: string): Promise<RegistryProject> {
  return request(`/api/v1/registry/projects/${id}`);
}

export function fetchRegistryPartDetail(id: string): Promise<RegistryPart> {
  return request(`/api/v1/registry/parts/${id}`);
}

export function fetchRegistryMoldDetail(id: string): Promise<RegistryMold> {
  return request(`/api/v1/registry/molds/${id}`);
}

export function fetchRegistryRevisionDetail(id: string): Promise<RegistryRevision> {
  return request(`/api/v1/registry/revisions/${id}`);
}

export function createProject(input: {
  code: string;
  name: string;
  description: string;
  reason: string;
}): Promise<RegistryProject> {
  return request("/api/v1/registry/projects", { method: "POST", body: JSON.stringify(input) });
}

export function createPart(input: {
  project_id: string;
  part_number: string;
  name: string;
  product_type: string;
  material_code: string;
  reason: string;
}): Promise<RegistryPart> {
  return request("/api/v1/registry/parts", { method: "POST", body: JSON.stringify(input) });
}

export function createMold(input: {
  project_id: string;
  product_part_id: string | null;
  mold_code: string;
  name: string;
  mold_type: string;
  cavity_count: number;
  reason: string;
}): Promise<RegistryMold> {
  return request("/api/v1/registry/molds", { method: "POST", body: JSON.stringify(input) });
}

export function createRevision(input: {
  mold_id: string;
  revision_code: string;
  change_summary: string;
  reason: string;
}): Promise<RegistryRevision> {
  return request("/api/v1/registry/revisions", { method: "POST", body: JSON.stringify(input) });
}

export function createNextRevision(
  moldId: string,
  input: { revision_code?: string; change_summary: string; reason: string },
): Promise<RegistryRevision & { suggested_revision_code?: string }> {
  return request(`/api/v1/registry/molds/${moldId}/revisions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchMoldImpactPreview(id: string): Promise<RegistryMoldImpact> {
  return request(`/api/v1/registry/molds/${id}/impact-preview`);
}

export function fetchRegistryEngineeringHistory(
  kind: "molds" | "revisions",
  id: string,
): Promise<RegistryEngineeringHistory> {
  return request(`/api/v1/registry/${kind}/${id}/engineering-history`);
}

export function transitionMold(
  mold: RegistryMold,
  action: "retire" | "reactivate" | "archive",
  reason: string,
): Promise<RegistryMold & { impact: RegistryMoldImpact["impact"] }> {
  return request(`/api/v1/registry/molds/${mold.id}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, reason, row_version: mold.row_version }),
  });
}

export function transitionRevision(
  revision: RegistryRevision,
  action: "release" | "archive",
  reason: string,
): Promise<RegistryRevision & { warnings?: Array<{ code: string; message: string }>; superseded_revision_id?: string | null }> {
  return request(`/api/v1/registry/revisions/${revision.id}/actions`, {
    method: "POST",
    body: JSON.stringify({ action, reason, row_version: revision.row_version }),
  });
}

export function updateRevision(
  revision: RegistryRevision,
  input: { status?: RegistryRevision["status"]; change_summary?: string; reason: string },
): Promise<RegistryRevision> {
  return request(`/api/v1/registry/revisions/${revision.id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: revision.row_version }),
  });
}

export function updateProject(
  project: RegistryProject,
  input: { name: string; description: string; status: RegistryProject["status"]; reason: string },
): Promise<RegistryProject> {
  return request(`/api/v1/registry/projects/${project.id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: project.row_version }),
  });
}

export function updatePart(
  part: RegistryPart,
  input: { name: string; product_type: string; material_code: string; status: RegistryPart["status"]; reason: string },
): Promise<RegistryPart> {
  return request(`/api/v1/registry/parts/${part.id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: part.row_version }),
  });
}

export function updateMold(
  mold: RegistryMold,
  input: { name: string; mold_type: string; cavity_count: number; status: RegistryMold["status"]; reason: string },
): Promise<RegistryMold> {
  return request(`/api/v1/registry/molds/${mold.id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: mold.row_version }),
  });
}

export function updateArtifactGovernance(
  artifact: { artifact_id: string; row_version: number },
  input: { name: string; product_type: string; material_code: string; lifecycle_status: string; quality_status: string; reason: string },
): Promise<RegistryArtifactGovernance> {
  return request(`/api/v1/registry/artifacts/${artifact.artifact_id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: artifact.row_version }),
  });
}
