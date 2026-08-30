import { flushPromises, mount } from "@vue/test-utils";

import RuleManagementWorkspace from "./RuleManagementWorkspace.vue";

const profile = {
  profile_id: "11111111-1111-4111-8111-111111111111",
  profile_key: "demo-general-design",
  version: "1.0",
  status: "approved_demo",
  workflow_status: "published",
  change_summary: "",
  row_version: 1,
  owner: "mold-engineering-demo",
  submitted_by: null,
  reviewed_by: null,
  approved_by: "demo-governance",
  published_at: "2026-08-29T00:00:00Z",
  retired_at: null,
  ruleset_checksum: "a".repeat(64),
  priority: 0,
  is_default: true,
  effective_from: null,
  effective_to: null,
  scope: "public-demo",
  classification: "public_demo",
  resolution_status: "eligible",
  applicability_checksum: "b".repeat(64),
  applicability: [],
  rule_count: 2,
  rules: [
    {
      rule_version_id: "22222222-2222-4222-8222-222222222222",
      rule_id: "MOLD-DRAFT-001",
      rule_version: "1.0",
      title: "Minimum draft angle",
      description: "Draft must meet the approved Demo threshold.",
      evaluator: "minimum_threshold",
      condition: { operator: "gte", limit: 1, unit: "deg", tolerance: 0 },
      severity: "high",
      risk_type: "demolding",
      recommendation: "Review the draft angle.",
      reference: { document: "Demo Mold Standard", revision: "A", classification: "public_demo" },
      applicability: { formats: ["step", "stp", "stl"] },
      measurement_definition: { field: "minimum_draft_angle_deg" },
      enabled: true,
    },
    {
      rule_version_id: "33333333-3333-4333-8333-333333333333",
      rule_id: "MOLD-RIB-001",
      rule_version: "1.0",
      title: "Maximum rib ratio",
      description: "Rib ratio must remain bounded.",
      evaluator: "maximum_threshold",
      condition: { operator: "lte", limit: 0.6, unit: "ratio", tolerance: 0 },
      severity: "medium",
      risk_type: "sink_mark",
      recommendation: "Review rib thickness.",
      reference: { document: "Demo Mold Standard", revision: "A", classification: "public_demo" },
      applicability: { formats: ["step", "stp", "stl"] },
      measurement_definition: { field: "rib_ratio" },
      enabled: true,
    },
  ],
};

describe("RuleManagementWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows governed profile metadata and supports safe client-side filtering", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ schema_version: "1.0", items: [profile] }),
      }),
    );
    const wrapper = mount(RuleManagementWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("demo-general-design @ 1.0");
    expect(wrapper.text()).toContain("Approved rules are immutable in this Demo");
    const rulesTab = wrapper.findAll(".rule-detail-tabs button").find((button) => button.text() === "Rules");
    await rulesTab!.trigger("click");
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    await wrapper.get('input[type="search"]').setValue("draft");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.text()).toContain("MOLD-DRAFT-001");
  });

  it("renders an actionable typed error state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("rule service unavailable")));
    const wrapper = mount(RuleManagementWorkspace);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("rule service unavailable");
    expect(wrapper.get("button").text()).toContain("Try again");
  });

  it("offers controlled version cloning to authorized rule authors", async () => {
    const draft = { ...profile, version: "2.0", workflow_status: "draft" };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("master-data/options")) return { ok: true, status: 200, json: async () => ({ results: {} }) };
      if (init?.method === "POST") return { ok: true, status: 201, json: async () => draft };
      return { ok: true, status: 200, json: async () => ({ schema_version: "1.0", items: [profile] }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(RuleManagementWorkspace, {
      props: {
        currentAccount: {
          id: "owner-1", username: "owner", email: "owner@example.test", display_name: "Owner",
          status: "active", locale: "en", timezone: "Asia/Taipei", row_version: 1,
          roles: ["rule_owner"], permissions: ["rules:read", "rules:author"], data_scopes: ["public-demo"],
          role_assignments: [], last_login_at: null, created_at: "2026-08-29T00:00:00Z",
        },
      },
    });
    await flushPromises();
    await wrapper.get(".rule-catalog-toolbar button").trigger("click");
    await wrapper.get(".rule-create-wizard").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/rule-profiles"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("uses structured fields instead of exposing raw JSON to rule authors", async () => {
    const draft = { ...profile, workflow_status: "draft" };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes("master-data/options")
      ? { ok: true, status: 200, json: async () => ({ results: {} }) }
      : { ok: true, status: 200, json: async () => ({ schema_version: "1.0", items: [draft] }) }));
    const wrapper = mount(RuleManagementWorkspace, {
      props: { currentAccount: {
        id: "owner-1", username: "owner", email: "owner@example.test", display_name: "Owner",
        status: "active", locale: "en", timezone: "Asia/Taipei", row_version: 1,
        roles: ["rule_owner"], permissions: ["rules:read", "rules:author"], data_scopes: ["public-demo"],
        role_assignments: [], last_login_at: null, created_at: "2026-08-29T00:00:00Z",
      } },
    });
    await flushPromises();
    const rulesTab = wrapper.findAll(".rule-detail-tabs button").find((button) => button.text() === "Rules");
    await rulesTab!.trigger("click");

    expect(wrapper.find(".structured-rule-list").exists()).toBe(true);
    expect(wrapper.find('textarea[aria-label="Rules (JSON)"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("Evaluator");
    expect(wrapper.text()).toContain("Reference document");
  });
});
