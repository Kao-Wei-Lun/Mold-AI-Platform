import { flushPromises, mount } from "@vue/test-utils";

import CAEWorkspace from "./CAEWorkspace.vue";

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function study(studyCode: string, runId: string, solverVersion = "2026.1") {
  return {
    study_id: `study-${runId}`,
    study_code: studyCode,
    solver_name: "Moldflow-like Demo Solver",
    product_ref: "DEMO-CONNECTOR-HOUSING@R3",
    mold_revision_ref: "DEMO-MOLD-HOUSING-A@R2",
    material_model_code: "PA6-GF30-DEMO@1",
    mesh_family: "DEMO-HOUSING-A-TETRA",
    objective: "Compare metrics",
    classification: "public_demo",
    provenance: {
      connector_key: "synthetic-cae-structured-export",
      integration_level: "synthetic_structured_export",
      source_record_id: studyCode,
      source_version: "2026.08.1",
      source_hash: "hash",
      mapping_version: "cae-canonical@1.0.0",
      official_solver_api_connected: false,
    },
    runs: [
      {
        run_id: runId,
        run_code: "RUN-001",
        solver: { name: "Moldflow-like Demo Solver", version: solverVersion },
        mesh: { artifact_ref: "mesh", checksum: "a", family: "DEMO-HOUSING-A-TETRA" },
        material_model_code: "PA6-GF30-DEMO@1",
        boundary_settings: {},
        process_settings: { injection_time_s: 1.2 },
        unit_system: "SI",
        status: "succeeded",
        input_hash: `hash-${runId}`,
        results: [],
      },
    ],
  };
}

const studies = [
  study("CAE-DEMO-BASELINE", "run-baseline"),
  study("CAE-DEMO-CANDIDATE", "run-candidate"),
  study("CAE-DEMO-INCOMPATIBLE-SOLVER", "run-solver", "2025.2"),
];

const compatibleComparison = {
  comparison_id: "comparison-1",
  schema_version: "1.0",
  capability: "cae.compare_runs@1.0.0",
  compatibility_profile_version: "cae-run-compatibility@1.0.0",
  compatible: true,
  incompatibilities: [],
  parsed_facts: {
    baseline: {
      study_id: "study-run-baseline",
      study_code: "CAE-DEMO-BASELINE",
      run_id: "run-baseline",
      run_code: "RUN-001",
    },
    candidate: {
      study_id: "study-run-candidate",
      study_code: "CAE-DEMO-CANDIDATE",
      run_id: "run-candidate",
      run_code: "RUN-001",
    },
  },
  comparison_summary: {
    comparable_metric_count: 2,
    excluded_metric_count: 0,
    finding_counts: { improved: 1, worsened: 0, unchanged: 0, changed_review_required: 1 },
  },
  metric_comparisons: [
    {
      metric_code: "max_injection_pressure_mpa",
      metric_label: "Maximum injection pressure",
      result_type: "scalar",
      unit: "MPa",
      baseline: { result_id: "result-b", value: 95, location: { scope: "node" } },
      candidate: { result_id: "result-c", value: 89, location: { scope: "node" } },
      delta: -6,
      percent_delta: -6.3158,
      finding: "improved",
      interpretation_type: "deterministic_metric_comparison",
      evidence_refs: [
        "cae-study:study-b",
        "cae-run:run-baseline",
        "cae-result:result-b",
        "cae-study:study-c",
        "cae-run:run-candidate",
        "cae-result:result-c",
        "cae-metric:max_injection_pressure_mpa",
      ],
    },
    {
      metric_code: "min_melt_front_temperature_c",
      metric_label: "Minimum melt-front temperature",
      result_type: "scalar",
      unit: "degC",
      baseline: { result_id: "temp-b", value: 252, location: { scope: "region" } },
      candidate: { result_id: "temp-c", value: 255, location: { scope: "region" } },
      delta: 3,
      percent_delta: 1.1905,
      finding: "changed_review_required",
      interpretation_type: "deterministic_metric_comparison",
      evidence_refs: ["cae-result:temp-b", "cae-result:temp-c"],
    },
  ],
  metric_incompatibilities: [],
  lineage: { comparison_ref: "cae-comparison:comparison-1" },
  limitations: ["Synthetic structured exports only.", "No optimization is generated."],
};

describe("CAEWorkspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function installFetch(comparisonPayload: unknown) {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/cae/demo-fixtures")) {
        return response({
          loaded_study_count: 3,
          connector: {
            status: "ok",
            source_version: "2026.08.1",
            record_count: 3,
            integration_level: "synthetic_structured_export",
            official_solver_api_connected: false,
          },
        });
      }
      if (url.endsWith("/cae-studies")) return response({ items: studies });
      if (url.endsWith("/cae-comparisons") && init?.method === "POST") {
        return response(comparisonPayload);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("shows deterministic metric deltas and evidence after compatibility passes", async () => {
    const fetchMock = installFetch(compatibleComparison);
    const wrapper = mount(CAEWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("3 canonical CAE studies");
    expect(wrapper.text()).toContain("No official solver API");
    await wrapper.get(".cae-compare-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Compatible");
    expect(wrapper.text()).toContain("Maximum injection pressure");
    expect(wrapper.text()).toContain("95 MPa");
    expect(wrapper.text()).toContain("89 MPa");
    expect(wrapper.text()).toContain("-6.000 MPa");
    expect(wrapper.text()).toContain("changed_review_required");
    expect(wrapper.text()).toContain("7 refs");
    expect(wrapper.text()).toContain("Synthetic structured exports only");
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/cae-comparisons"));
    const request = JSON.parse(String(call?.[1]?.body));
    expect(request).toEqual({
      baseline_run_id: "run-baseline",
      candidate_run_id: "run-candidate",
    });
  });

  it("shows incompatibility evidence and no metric table when comparison is blocked", async () => {
    const blocked = {
      ...compatibleComparison,
      comparison_id: "comparison-blocked",
      compatible: false,
      incompatibilities: [
        {
          code: "CAE_INCOMPATIBLE_SOLVER_VERSION",
          field: "solver_version",
          baseline: "2026.1",
          candidate: "2025.2",
        },
      ],
      comparison_summary: {
        comparable_metric_count: 0,
        excluded_metric_count: 0,
        finding_counts: {
          improved: 0,
          worsened: 0,
          unchanged: 0,
          changed_review_required: 0,
        },
      },
      metric_comparisons: [],
    };
    installFetch(blocked);
    const wrapper = mount(CAEWorkspace);
    await flushPromises();
    await wrapper.findAll(".cae-compare-form select")[1].setValue("run-solver");
    await wrapper.get(".cae-compare-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Comparison blocked");
    expect(wrapper.text()).toContain("No metric delta was calculated");
    expect(wrapper.text()).toContain("solver version");
    expect(wrapper.text()).toContain("CAE_INCOMPATIBLE_SOLVER_VERSION");
    expect(wrapper.find(".cae-metric-table").exists()).toBe(false);
  });
});
