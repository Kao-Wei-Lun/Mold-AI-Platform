import { apiFetch } from "./client";

export type MasterDataKind =
  | "dataset"
  | "product_type"
  | "material"
  | "machine"
  | "defect"
  | "location"
  | "unit";

export type MasterDataStatus = "active" | "inactive" | "archived";

export type MasterDataOption = {
  id: string;
  code: string;
  name_en: string;
  name_zh_tw: string;
  attributes: Record<string, unknown>;
  row_version: number;
};

export type MasterDataOptions = Record<MasterDataKind, MasterDataOption[]>;

export type MasterDataItem = MasterDataOption & {
  kind: MasterDataKind;
  description_en: string;
  description_zh_tw: string;
  status: MasterDataStatus;
  sort_order: number;
  aliases: string[];
  source_system: string;
  source_refs: string[];
  scope: string;
  classification: string;
  effective_from: string | null;
  effective_to: string | null;
  created_at: string;
  updated_at: string;
  references: Record<string, number>;
};

export const emptyMasterDataOptions = (): MasterDataOptions => ({
  dataset: [],
  product_type: [],
  material: [],
  machine: [],
  defect: [],
  location: [],
  unit: [],
});

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    const error = payload.error;
    if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
      return error.message;
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) throw new Error(errorMessage(payload, `Master data returned HTTP ${response.status}`));
  return payload as T;
}

export async function fetchMasterDataOptions(): Promise<MasterDataOptions> {
  const payload = await request<{ results: MasterDataOptions }>("/api/v1/master-data/options");
  return { ...emptyMasterDataOptions(), ...payload.results };
}

export async function fetchMasterData(input: {
  kind?: MasterDataKind;
  status?: MasterDataStatus | "";
  search?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<{ results: MasterDataItem[]; pagination: { page: number; page_size: number; total: number } }> {
  const query = new URLSearchParams();
  if (input.kind) query.set("kind", input.kind);
  if (input.status) query.set("status", input.status);
  if (input.search) query.set("search", input.search);
  if (input.sort) query.set("sort", input.sort);
  query.set("page", String(input.page || 1));
  query.set("page_size", String(input.pageSize || 25));
  return request(`/api/v1/master-data?${query}`);
}

export function createMasterData(input: {
  kind: MasterDataKind;
  code: string;
  name_en: string;
  name_zh_tw: string;
  description_en?: string;
  description_zh_tw?: string;
  sort_order?: number;
  attributes?: Record<string, unknown>;
  aliases?: string[];
  reason: string;
}): Promise<MasterDataItem> {
  return request("/api/v1/master-data", { method: "POST", body: JSON.stringify(input) });
}

export function updateMasterData(
  item: MasterDataItem,
  input: Partial<Pick<MasterDataItem, "name_en" | "name_zh_tw" | "description_en" | "description_zh_tw" | "status" | "sort_order" | "attributes" | "aliases">> & { reason: string },
): Promise<MasterDataItem> {
  return request(`/api/v1/master-data/${item.id}`, {
    method: "PATCH",
    headers: { "If-Match": `W/"master-data-${item.id}-${item.row_version}"` },
    body: JSON.stringify(input),
  });
}

export function archiveMasterData(item: MasterDataItem, reason: string): Promise<MasterDataItem> {
  return request(`/api/v1/master-data/${item.id}`, {
    method: "DELETE",
    headers: { "If-Match": `W/"master-data-${item.id}-${item.row_version}"` },
    body: JSON.stringify({ row_version: item.row_version, reason }),
  });
}
