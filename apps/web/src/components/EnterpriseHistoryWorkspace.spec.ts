import { flushPromises, mount } from "@vue/test-utils";

import type { LocalAccount } from "../api/identity";
import EnterpriseHistoryWorkspace from "./EnterpriseHistoryWorkspace.vue";

const account = {
  data_scopes: ["public-demo"],
  permissions: ["enterprise:read", "enterprise:manage", "bulk:manage"],
} as LocalAccount;

function json(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

const policy = {
  policy_id: "policy-1", scope: "public-demo", classification: "public_demo",
  connector_mode: "public_demo", retention_days: 2555, retention_cutoff: "2019-08-29T00:00:00Z",
  retention_eligible: { artifacts: 0, trials: 0, cae_studies: 0 }, purge_blocked: false,
  legal_hold: false, legal_hold_reason: "", dlp_enabled: true, export_allowed: true,
  siem: { enabled: false, destination: null, status: "disabled" },
  isolation: { index_namespace: "public-index", cache_namespace: "public-cache", cross_scope_queries: false, cross_scope_exports: false },
  row_version: 1, updated_by: "system", updated_at: "2026-08-29T00:00:00Z",
};

describe("EnterpriseHistoryWorkspace", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows retention, DLP, SIEM and scope isolation controls", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("import-batches") ? json({ items: [] }) : json(policy),
    ));
    const wrapper = mount(EnterpriseHistoryWorkspace, {
      props: { path: "/data/enterprise?tab=policy", currentAccount: account },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("public-index");
    expect(wrapper.text()).toContain("DLP");
    expect(wrapper.text()).toContain("SIEM");
    expect(wrapper.text()).toContain("Blocked");
    expect(wrapper.text()).toContain("Edit enterprise policy");
  });

  it("offers dry-run then commit for governed bulk import", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("policy")) return json(policy);
      if (!init?.method) return json({ items: [] });
      return json({ batch_id: "batch-1", status: "validated", validation: { valid: true, record_count: 1, valid_count: 1, issues: [] }, reconciliation: {}, created_at: "2026-08-29T00:00:00Z" });
    }));
    const wrapper = mount(EnterpriseHistoryWorkspace, {
      props: { path: "/data/enterprise?tab=import", currentAccount: account },
    });
    await flushPromises();
    await wrapper.find('input').setValue("batch-key-1");
    await wrapper.findAll("button").find((button) => button.text().includes("Run dry validation"))?.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Commit validated batch");
    expect(wrapper.text()).toContain("batch-1");
  });
});
