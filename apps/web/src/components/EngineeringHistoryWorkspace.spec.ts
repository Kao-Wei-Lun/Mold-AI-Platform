import { flushPromises, mount } from "@vue/test-utils";

import { setLocale } from "../i18n";
import EngineeringHistoryWorkspace from "./EngineeringHistoryWorkspace.vue";

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

describe("EngineeringHistoryWorkspace", () => {
  beforeEach(() => setLocale("en"));
  afterEach(() => vi.restoreAllMocks());

  it("loads trial summaries first and complete detail on a stable route", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("view=summary")) {
        return response({ items: [{ trial_case_id: "trial-1", case_code: "TRIAL-001", mold_revision_ref: "M-1@A", machine_code: "IM-120T", material_code: "ABS", product_type: "housing", outcome: "accepted", started_at: "2026-08-29T00:00:00Z", lifecycle_status: "closed", row_version: 2, run_count: 1, correction_count: 1 }] });
      }
      return response({
        trial_case_id: "trial-1", case_code: "TRIAL-001", mold_revision_ref: "M-1@A", machine_code: "IM-120T", material_code: "ABS", material_lot: "LOT-7", product_type: "housing", purpose: "Qualification", outcome: "accepted", started_at: "2026-08-29T00:00:00Z", lifecycle_status: "closed", row_version: 2, data_quality: { status: "verified" },
        runs: [{ process_run_id: "run-1", run_number: 1, cycle_range: { start: 1, end: 20 }, parameters: { injection_pressure_mpa: { value: 88, unit: "MPa", value_kind: "setpoint", sampling_method: "hmi" } }, environment: {}, result: {}, data_quality: {}, defects: [], corrective_actions: [] }],
        corrections: [{ correction_id: "correction-1", before_values: { outcome: "pending" }, after_values: { outcome: "accepted" }, reason: "Signed sheet", corrected_by: "engineer", created_at: "2026-08-29T01:00:00Z" }], provenance: { connector_key: "fixture" },
      });
    }));
    const wrapper = mount(EngineeringHistoryWorkspace, { props: { domain: "trials", path: "/data/trials" } });
    await flushPromises();

    expect(wrapper.text()).toContain("TRIAL-001");
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/trials/trial-1"]);

    await wrapper.setProps({ path: "/data/trials/trial-1?tab=runs" });
    await flushPromises();
    expect(wrapper.text()).toContain("injection_pressure_mpa");
    expect(wrapper.text()).toContain("88 MPa");
  });

  it("renders CAE run settings and typed results", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      study_id: "study-1", study_code: "CAE-001", solver_name: "Moldflow", mold_revision_ref: "M-1@A", material_model_code: "ABS", mesh_family: "3d-tetra", objective: "Reduce pressure", lifecycle_status: "active", row_version: 1, archive_reason: null, owner: "analyst", data_quality: {}, provenance: { source_version: "1" },
      runs: [{ run_id: "run-1", run_code: "RUN-001", solver: { name: "Moldflow", version: "2026" }, mesh: { artifact_ref: "mesh-1", checksum: "abc", family: "3d-tetra" }, material_model_code: "ABS", boundary_settings: { gate: "center" }, process_settings: { melt_c: 230 }, unit_system: "SI", status: "succeeded", input_hash: "hash", data_quality: {}, results: [{ result_id: "result-1", metric_code: "fill_time_s", result_type: "scalar", value: 1.2, unit: "s", location: {}, field_summary: {}, quality_flags: [], parser: { name: "moldflow", version: "1" }, source_locator: {}, evidence_refs: [] }] }],
    })));
    const wrapper = mount(EngineeringHistoryWorkspace, { props: { domain: "cae", path: "/data/cae/study-1?tab=runs" } });
    await flushPromises();

    expect(wrapper.text()).toContain("RUN-001");
    expect(wrapper.text()).toContain("fill_time_s");
    expect(wrapper.text()).toContain("1.2 s");
  });

  it("renders HMI raw evidence, effective values and review decisions", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      schema_version: "1.0", extraction_id: "hmi-1", image_artifact_version_id: "image-1", image_sha256: "sha", image_download_url: "/download/image-1", profile: "demo@1.0", profile_definition_id: "profile-1", extractor_version: "1.0", status: "succeeded", image_dimensions: { width: 800, height: 500 }, preprocessing: {}, review_status: "ready_for_export", export_status: "ready", exports: [], lineage_ref: "hmi-extraction:hmi-1", created_at: "2026-08-29T00:00:00Z", limitations: [],
      fields: [{ field_id: "field-1", parameter_code: "pressure", display_label: "Pressure", raw_text: "55 MPa", value: 55, unit: "MPa", confidence: 0.82, source_region: { x: 0, y: 0, w: 1, h: 1, coordinate_space: "normalized" }, validation_status: "valid", review_status: "corrected", reviewer_correction: { value: 56, unit: "MPa", reviewed_by: "engineer" }, effective_value: 56, effective_unit: "MPa", correction_decisions: [{ decision_id: "decision-1", action: "correct", before_value: { value: 55 }, after_value: { value: 56 }, reason: "Glare", decided_by: "engineer", created_at: "2026-08-29T01:00:00Z" }] }],
    })));
    const wrapper = mount(EngineeringHistoryWorkspace, { props: { domain: "hmi", path: "/data/hmi/hmi-1?tab=fields" } });
    await flushPromises();

    expect(wrapper.text()).toContain("55 MPa");
    expect(wrapper.text()).toContain("56 MPa");
    await wrapper.findAll('[role="tab"]')[2].trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/hmi/hmi-1?tab=decisions"]);
  });
});
