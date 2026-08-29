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
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    const message = payload?.error?.message || `Registry returned HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export async function fetchRegistry(): Promise<{
  projects: RegistryProject[];
  parts: RegistryPart[];
  molds: RegistryMold[];
  revisions: RegistryRevision[];
}> {
  const [projectPayload, partPayload, moldPayload, revisionPayload] = await Promise.all([
    request<{ items: RegistryProject[] }>("/api/v1/registry/projects"),
    request<{ items: RegistryPart[] }>("/api/v1/registry/parts"),
    request<{ items: RegistryMold[] }>("/api/v1/registry/molds"),
    request<{ items: RegistryRevision[] }>("/api/v1/registry/revisions"),
  ]);
  return {
    projects: projectPayload.items,
    parts: partPayload.items,
    molds: moldPayload.items,
    revisions: revisionPayload.items,
  };
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

export function updateRevision(
  revision: RegistryRevision,
  input: { status?: RegistryRevision["status"]; change_summary?: string; reason: string },
): Promise<RegistryRevision> {
  return request(`/api/v1/registry/revisions/${revision.id}`, {
    method: "PATCH",
    body: JSON.stringify({ ...input, row_version: revision.row_version }),
  });
}
