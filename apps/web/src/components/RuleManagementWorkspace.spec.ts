import { flushPromises, mount } from "@vue/test-utils";

import RuleManagementWorkspace from "./RuleManagementWorkspace.vue";

const profile = {
  profile_id: "11111111-1111-4111-8111-111111111111",
  profile_key: "demo-general-design",
  version: "1.0",
  status: "approved_demo",
  owner: "mold-engineering-demo",
  approved_by: "demo-governance",
  ruleset_checksum: "a".repeat(64),
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
});
