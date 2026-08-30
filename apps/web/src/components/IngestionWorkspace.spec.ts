import { flushPromises, mount } from "@vue/test-utils";

import type { LocalAccount } from "../api/identity";
import IngestionWorkspace from "./IngestionWorkspace.vue";

const account: LocalAccount = {
  id: "account-1", username: "admin", email: "admin@example.test", display_name: "Admin",
  status: "active", locale: "en", timezone: "Asia/Taipei", row_version: 1,
  roles: ["platform_admin"], permissions: ["ingestion:read", "ingestion:create", "ingestion:validate", "ingestion:commit"],
  data_scopes: ["public-demo"], role_assignments: [], last_login_at: null, created_at: "2026-08-30T00:00:00Z",
};

function batch(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0", batch_id: "11111111-1111-4111-8111-111111111111",
    canonical_id: "ingestion:11111111-1111-4111-8111-111111111111", scope: "public-demo",
    classification: "public_demo", domain: "master_data", source_name: "materials.csv",
    status: "draft", mapping_version: "1.0", validation: {}, reconciliation: {}, job_id: null,
    created_by: "account-1", created_at: "2026-08-30T00:00:00Z", updated_at: "2026-08-30T00:00:00Z",
    deep_link: "/data/imports/11111111-1111-4111-8111-111111111111", request_id: "request-1",
    correlation_id: null, field_mapping: {}, records: [], source_files: [], issues: [], ...overrides,
  };
}

describe("IngestionWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates and uploads a screened source without committing domain data", async () => {
    const draft = batch();
    const uploaded = batch({ status: "mapping_required", records: [{ type: "material", code: "ABS" }], source_files: [{ source_file_id: "file-1", artifact_version_id: "version-1", file_name: "materials.csv", sha256: "a".repeat(64), mime_type: "text/csv", size_bytes: 32, screening: { malware: "basic_screened" } }] });
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/ingestions") && init?.method === "POST") return { ok: true, status: 201, json: async () => draft };
      if (url.includes("/files")) return { ok: true, status: 201, json: async () => uploaded };
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(IngestionWorkspace, { props: { path: "/data/imports", currentAccount: account } });
    await flushPromises();
    const input = wrapper.get('input[type="file"]');
    const file = new File(["kind,code,name_en\nmaterial,ABS,ABS"], "materials.csv", { type: "text/csv" });
    Object.defineProperty(input.element, "files", { value: [file] });
    await input.trigger("change");
    await wrapper.get(".ingestion-create-grid").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/ingestions"), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/files"), expect.objectContaining({ method: "POST" }));
    expect(wrapper.text()).toContain("Field mapping");
    expect(wrapper.text()).not.toContain("Commit validated batch");
  });

  it("shows row-level issues from a read-only dry run", async () => {
    const invalid = batch({ status: "validation_failed", validation: { valid: false, record_count: 1, valid_count: 0, existing_count: 0 }, issues: [{ issue_id: "issue-1", row_number: 1, field_name: "name_en", code: "REQUIRED_FIELDS", message: "name_en is required", raw_value: "", suggestion: "", severity: "blocking" }] });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes(invalid.batch_id)
      ? { ok: true, status: 200, json: async () => invalid }
      : { ok: true, status: 200, json: async () => ({ items: [invalid] }) }));
    const wrapper = mount(IngestionWorkspace, { props: { path: `/data/imports/${invalid.batch_id}`, currentAccount: account } });
    await flushPromises();

    expect(wrapper.text()).toContain("REQUIRED_FIELDS");
    expect(wrapper.text()).toContain("name_en is required");
    expect(wrapper.text()).toContain("Source rows");
  });
});
