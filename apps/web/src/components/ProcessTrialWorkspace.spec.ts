import { flushPromises, mount } from "@vue/test-utils";

import ProcessTrialWorkspace from "./ProcessTrialWorkspace.vue";

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

const trialCase = {
  trial_case_id: "trial-1",
  case_code: "TRIAL-DEMO-001",
  mold_revision_ref: "DEMO-MOLD-HOUSING-A@R2",
  part_revision_ref: "DEMO-HOUSING-A@R3",
  machine_code: "IM-180T",
  material_code: "PA6-GF30",
  product_type: "connector_housing",
  purpose: "Resolve short shot",
  outcome: "resolved",
  classification: "public_demo",
  provenance: {
    connector_key: "synthetic-process-trial",
    source_record_id: "TRIAL-DEMO-001",
    source_version: "2026.08.1",
    source_hash: "abc",
    mapping_version: "process-trial-canonical@1.0.0",
    source_type: "synthetic",
  },
};

const searchResult = {
  search_id: "search-1",
  schema_version: "1.0",
  capability: "process.case_search@1.0.0",
  scoring_profile_version: "process-case-demo@1.0.0",
  result_count: 1,
  results: [
    {
      rank: 1,
      trial_case_id: "trial-1",
      case_code: "TRIAL-DEMO-001",
      score: 0.98,
      score_breakdown: { defect: 1, material: 1, machine: 1, parameters: 0.94 },
      profile_version: "process-case-demo@1.0.0",
      material_code: "PA6-GF30",
      machine_code: "IM-180T",
      product_type: "connector_housing",
      mold_revision_ref: "DEMO-MOLD-HOUSING-A@R2",
      defect: {
        code: "short_shot",
        severity: "major",
        location: "far_flow_end",
        quantity_rate: 0.12,
        quantity_unit: "fraction",
      },
      parameters: { injection_pressure_mpa: { value: 82, unit: "MPa" } },
      corrective_action: {
        action_code: "increase_injection_pressure",
        description: "Run a controlled pressure step.",
        before_values: { injection_pressure_mpa: { value: 82, unit: "MPa" } },
        after_values: { injection_pressure_mpa: { value: 92, unit: "MPa" } },
        observed_outcome: { defect_rate_before: 0.12, defect_rate_after: 0.02 },
        expected_effect: "Associated historical improvement.",
        stop_condition: "Stop if flash appears.",
      },
      outcome: "resolved",
      similarities: [{ factor: "defect" }, { factor: "material" }],
      differences: [{ factor: "injection_pressure_mpa" }],
      evidence_refs: ["trial-case:trial-1", "TRIAL-DEMO-001:run:1:action"],
      provenance: trialCase.provenance,
    },
  ],
  rule_findings: [],
  recommendation: {
    abstained: false,
    reason_code: null,
    message: "Historical ranges are candidates for an engineer-approved controlled trial.",
    required_fields: [],
    controlled_trial_steps: [
      {
        rank: 1,
        action_code: "increase_injection_pressure",
        instruction: "Run a controlled pressure step.",
        historical_before: { injection_pressure_mpa: { value: 82, unit: "MPa" } },
        historical_after: { injection_pressure_mpa: { value: 92, unit: "MPa" } },
        expected_effect: "Associated historical improvement.",
        stop_condition: "Stop if flash appears.",
        confidence: { label: "case_association_only", score: 0.83, basis: "deterministic" },
        source_case_code: "TRIAL-DEMO-001",
        evidence_refs: ["trial-case:trial-1"],
        requires_engineer_approval: true,
        do_not_auto_apply: true,
      },
    ],
  },
  abstained: false,
  limitations: ["Synthetic fixtures only.", "No machine writes."],
  lineage: { search_ref: "process-case-search:search-1" },
};

describe("ProcessTrialWorkspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows ranked evidence and guarded controlled-trial steps", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/process-trial/demo-fixtures")) {
        return response({
          loaded_case_count: 6,
          connector: {
            status: "ok",
            source_type: "synthetic",
            source_version: "2026.08.1",
            record_count: 6,
          },
        });
      }
      if (url.endsWith("/trial-cases")) return response({ items: [trialCase] });
      if (url.endsWith("/process-case-searches") && init?.method === "POST") {
        return response(searchResult);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(ProcessTrialWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("6 canonical trial cases");
    expect(wrapper.text()).toContain("Source records remain clearly marked synthetic");
    expect(wrapper.get('.process-query-form button[type="submit"]').attributes("disabled")).toBeDefined();
    await wrapper.get(".demo-input-notice button").trigger("click");
    await wrapper.get(".process-query-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("TRIAL-DEMO-001");
    expect(wrapper.text()).toContain("Engineer review required");
    expect(wrapper.text()).toContain("82 MPa → injection pressure mpa: 92 MPa");
    expect(wrapper.text()).toContain("Approval required · Never auto-apply");
    expect(wrapper.text()).toContain("Synthetic fixtures only. No machine writes.");
    const searchCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/process-case-searches"),
    );
    const sent = JSON.parse(String(searchCall?.[1]?.body));
    expect(sent.material_code).toBe("PA6-GF30");
    expect(sent.parameters.injection_pressure_mpa).toEqual({ value: 84, unit: "MPa" });
  });

  it("can explicitly load the synthetic connector fixtures", async () => {
    let loaded = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/process-trial/demo-fixtures") && init?.method === "POST") {
        loaded = true;
        return response({ created: 6, existing: 0 }, 201);
      }
      if (url.endsWith("/process-trial/demo-fixtures")) {
        return response({
          loaded_case_count: loaded ? 6 : 0,
          connector: {
            status: "ok",
            source_type: "synthetic",
            source_version: "2026.08.1",
            record_count: 6,
          },
        });
      }
      if (url.endsWith("/trial-cases")) return response({ items: loaded ? [trialCase] : [] });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(ProcessTrialWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("0 canonical trial cases");
    await wrapper.get(".process-source-bar button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("6 canonical trial cases");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
  });
});
