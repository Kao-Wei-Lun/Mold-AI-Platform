import { flushPromises, mount } from "@vue/test-utils";

import type { LocalAccount } from "../api/identity";
import OperationalHistoryWorkspace from "./OperationalHistoryWorkspace.vue";

const account = {
  permissions: ["analysis:manage", "job:cancel", "job:retry", "audit:export"],
} as LocalAccount;

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

describe("OperationalHistoryWorkspace", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows analysis records and emits a typed detail route", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      items: [{ analysis_type: "knowledge_search", analysis_id: "analysis-1", title: "Knowledge · draft angle", state: "completed", created_at: "2026-08-29T00:00:00Z", result_count: 2, lifecycle: { status: "active", row_version: 1 } }],
      page: { number: 1, size: 25, total: 1 },
    })));
    const wrapper = mount(OperationalHistoryWorkspace, {
      props: { domain: "analysis-results", path: "/data/analysis-results", currentAccount: account },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Knowledge · draft angle");
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual([
      "/data/analysis-results/analysis-1?type=knowledge_search",
    ]);
  });

  it("renders a complete job event timeline", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      job_id: "job-1", capability_id: "cad.parse", state: "failed", stage: "parse", progress: 42,
      created_at: "2026-08-29T00:00:00Z", input_snapshot: { dataset_id: "public-demo-v1" },
      error: { code: "CAD_PARSE_FAILED", message: "Parser stopped" },
      events: [{ event_id: "event-1", from_state: "running", to_state: "failed", stage: "parse", progress: 42, detail: {}, created_at: "2026-08-29T00:01:00Z" }],
    })));
    const wrapper = mount(OperationalHistoryWorkspace, {
      props: { domain: "jobs", path: "/data/jobs/job-1?tab=events", currentAccount: account },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("running → failed");
    expect(wrapper.text()).toContain("Retry as new job");
  });

  it("switches from append-only audit records to lineage query", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ items: [], page: { total: 0 } })));
    const wrapper = mount(OperationalHistoryWorkspace, {
      props: { domain: "audit-lineage", path: "/data/audit-lineage", currentAccount: account },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("Audit events");
    expect(wrapper.text()).toContain("Export CSV");

    await wrapper.findAll(".detail-tabs button")[1].trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/audit-lineage?view=lineage"]);
  });
});
