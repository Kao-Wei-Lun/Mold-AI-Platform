import { flushPromises, mount } from "@vue/test-utils";

import { emptyMasterDataOptions } from "../api/masterData";
import MoldPlanningWorkspace from "./MoldPlanningWorkspace.vue";

const registry = {
  projects: [{ id: "project-1", code: "DEMO", name: "Demo", description: "", scope: "public-demo", classification: "public_demo", status: "active", row_version: 1, part_count: 1, mold_count: 1 }],
  parts: [{ id: "part-1", project_id: "project-1", project_code: "DEMO", part_number: "PART-1", name: "Housing", product_type: "housing", material_code: "ABS-GENERAL", status: "active", row_version: 1 }],
  molds: [{ id: "mold-1", project_id: "project-1", project_code: "DEMO", product_part_id: "part-1", part_number: "PART-1", mold_code: "MOLD-1", name: "Housing mold", mold_type: "three_plate", cavity_count: 2, status: "active", row_version: 1, revision_count: 1 }],
  revisions: [{ id: "revision-1", mold_id: "mold-1", mold_code: "MOLD-1", revision_code: "A", status: "released", change_summary: "", source_system: "demo", source_revision_id: null, row_version: 1, released_at: null, artifact_count: 1 }],
};
const artifacts = [{ artifact_id: "artifact-1", name: "Housing CAD", kind: "cad_source", classification: "public_demo", dataset_id: "demo", product_type: "housing", material_code: "ABS-GENERAL", mold_revision_id: "revision-1", mold_revision: { revision_code: "A", mold_id: "mold-1", mold_code: "MOLD-1" }, lifecycle_status: "active", quality_status: "accepted", created_at: "", updated_at: "", row_version: 1, source: null, jobs: [], versions: [{ artifact_version_id: "version-1", original_filename: "housing.stl", media_type: "model/stl", format: "stl", size_bytes: 10, sha256: "abc", version_number: 1, download_url: "/download" }] }];

const fetchRegistry = vi.fn(async () => registry);
const fetchRecentCAD = vi.fn(async () => artifacts);
const previewResolution = vi.fn(async (_input: unknown) => ({
  schema_version: "1.0", mold_revision_id: "revision-1", cad_artifact_version_id: "version-1", selection_mode: "automatic",
  context: { mold_type: "three_plate", product_type: "housing", material: "ABS-GENERAL", molding_process: "injection", project: "DEMO" },
  sources: { product_type: { source_type: "cad", source_ref: "version-1" } }, missing_fields: [],
  selected: { profile_id: "profile-1", profile_key: "housing-standard", display_name: "Housing Standard", version: "1.0", workflow_status: "published", owner: "owner", approved_by: "approver", effective_from: null, effective_to: null, specificity: 2, priority: 10, is_default: false, matched_dimensions: ["mold_type", "product_type"], applicability_checksum: "checksum" },
  candidates: [
    { profile_id: "profile-1", profile_key: "housing-standard", display_name: "Housing Standard", version: "1.0", workflow_status: "published", owner: "owner", approved_by: "approver", effective_from: null, effective_to: null, specificity: 2, priority: 10, is_default: false, matched_dimensions: ["mold_type", "product_type"], applicability_checksum: "checksum" },
    { profile_id: "profile-2", profile_key: "general-standard", display_name: "General Standard", version: "1.0", workflow_status: "published", owner: "owner", approved_by: "approver", effective_from: null, effective_to: null, specificity: 1, priority: 5, is_default: false, matched_dimensions: ["mold_type"], applicability_checksum: "checksum-2" },
  ], excluded_summary: [], reason: "Selected the most specific published profile.", applicability_checksum: "checksum",
}));
const compareResolution = vi.fn(async (_input: unknown) => ({
  schema_version: "1.0", context: {}, baseline_profile_id: "profile-1",
  items: [
    { profile_id: "profile-1", profile_key: "housing-standard", display_name: "Housing Standard", version: "1.0", priority: 10, is_default: false, owner: "owner", approved_by: "approver", effective_from: null, effective_to: null, applicability: [], enabled_rule_count: 3, risk_categories: ["demolding"], high_risk_rules: [{ rule_id: "RULE-1", title: "Draft", severity: "high", risk_type: "demolding" }], difference_summary: { baseline_profile_id: "profile-1", added: [], removed: [], modified: [] } },
    { profile_id: "profile-2", profile_key: "general-standard", display_name: "General Standard", version: "1.0", priority: 5, is_default: false, owner: "owner", approved_by: "approver", effective_from: null, effective_to: null, applicability: [], enabled_rule_count: 2, risk_categories: [], high_risk_rules: [], difference_summary: { baseline_profile_id: "profile-1", added: [], removed: ["RULE-1"], modified: [] } },
  ],
}));
const storedPlan = {
  plan_id: "plan-1", plan_code: "MP-1", name: "Housing plan", purpose: "new_mold", project_id: "project-1", project_code: "DEMO", part_id: "part-1", part_number: "PART-1", mold_id: "mold-1", mold_code: "MOLD-1", mold_revision_id: "revision-1", mold_revision: "A", cad_artifact_version_id: "version-1", status: "draft", owner_id: "owner", scope: "public-demo", classification: "public_demo", row_version: 1, latest_resolution: null, created_at: "2026-08-31T00:00:00Z", updated_at: "2026-08-31T00:00:00Z", archived_at: null, archive_reason: null,
} as const;
const fetchPlans = vi.fn(async () => ({ items: [], page: { page: 1, page_size: 25, total: 0 } }));
const createPlan = vi.fn(async (_input: unknown) => storedPlan);
const resolvePlan = vi.fn(async (_id: string) => ({ ...storedPlan, status: "ready", row_version: 2, latest_resolution: null }));

vi.mock("../api/registry", () => ({ fetchRegistry: () => fetchRegistry() }));
vi.mock("../api/cad", () => ({ fetchRecentCAD: () => fetchRecentCAD() }));
vi.mock("../api/moldPlanning", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/moldPlanning")>();
  return {
    ...actual,
    previewMoldPlanningResolution: (input: unknown) => previewResolution(input),
    compareMoldPlanningCandidates: (input: unknown) => compareResolution(input),
    fetchMoldPlans: () => fetchPlans(),
    fetchMoldPlan: async () => storedPlan,
    createMoldPlan: (input: unknown) => createPlan(input),
    updateMoldPlan: async () => storedPlan,
    resolveMoldPlan: (id: string) => resolvePlan(id),
    transitionMoldPlan: async () => storedPlan,
    selectMoldPlanProfile: async () => storedPlan,
    createMoldPlanHandoff: async () => ({
      handoff_id: "handoff-1",
      handoff_type: "cad",
      target_ref: "cad:plan-1",
      review_id: null,
      contract: { ui_path: "/engineering/cad" },
      created_by: "owner",
      created_at: "2026-08-31T00:00:00Z",
    }),
  };
});

const options = emptyMasterDataOptions();
options.mold_type = [{ id: "md-mold", code: "three_plate", name_en: "Three plate", name_zh_tw: "三板模", attributes: { process_family: "injection" }, row_version: 1 }];
options.product_type = [{ id: "md-product", code: "housing", name_en: "Housing", name_zh_tw: "外殼", attributes: {}, row_version: 1 }];
options.material = [{ id: "md-material", code: "ABS-GENERAL", name_en: "ABS", name_zh_tw: "ABS", attributes: {}, row_version: 1 }];
options.molding_process = [{ id: "md-process", code: "injection", name_en: "Injection", name_zh_tw: "射出成型", attributes: {}, row_version: 1 }];

describe("MoldPlanningWorkspace", () => {
  beforeEach(() => { fetchRegistry.mockClear(); fetchRecentCAD.mockClear(); previewResolution.mockClear(); compareResolution.mockClear(); fetchPlans.mockClear(); createPlan.mockClear(); resolvePlan.mockClear(); });

  it("loads a governed mold context without asking for a profile key", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();

    expect(wrapper.get("h2").text()).toContain("Plan the mold");
    expect(wrapper.text()).toContain("MOLD-1@A");
    expect(wrapper.text()).toContain("housing.stl");
    expect(wrapper.text()).not.toContain("Profile key");
    expect(wrapper.emitted("contextChange")?.[0]?.[0]).toMatchObject({
      page: "mold_planning",
      context_version: "1.0",
    });
  });

  it("makes the new-plan action visibly navigate to and focus the existing creation form", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();

    expect(wrapper.text()).toContain("Select applicable standards and create engineering requirements");
    expect(wrapper.text()).toContain("Creating a new mold plan");
    const action = wrapper.get(".plan-catalog-actions button");
    expect(action.text()).toContain("Go to new plan form");

    const editor = wrapper.get(".planning-work-grid").element as HTMLElement;
    const nameInput = wrapper.get('input[required]').element as HTMLInputElement;
    const scrollIntoView = vi.fn();
    const focus = vi.spyOn(nameInput, "focus");
    editor.scrollIntoView = scrollIntoView;
    await wrapper.get('input[required]').setValue("Unsaved plan");
    await action.trigger("click");
    await flushPromises();

    expect(nameInput.value).toBe("");
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(focus).toHaveBeenCalledOnce();
  });

  it("resolves and explains the recommended review rule set", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(previewResolution).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("Housing Standard");
    expect(wrapper.text()).toContain("2 matched dimensions");
  });

  it("keeps rule governance in the dedicated governance route", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();
    await wrapper.get(".planning-intro button").trigger("click");

    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/governance/rules"]);
  });

  it("compares two eligible candidates using the server contract", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    const candidates = wrapper.findAll(".candidate-option-list input");
    await candidates[1].setValue(true);
    await wrapper.get(".candidate-catalog > button").trigger("click");
    await flushPromises();

    expect(compareResolution).toHaveBeenCalledOnce();
    expect(wrapper.findAll(".comparison-card-grid article")).toHaveLength(2);
    expect(wrapper.text()).toContain("General Standard");
  });

  it("persists a draft and immutable resolution after preview", async () => {
    const wrapper = mount(MoldPlanningWorkspace, { props: { masterDataOptions: options } });
    await flushPromises();
    await wrapper.get('input[required]').setValue("Housing plan");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    await wrapper.get(".plan-save-actions button").trigger("click");
    await flushPromises();

    expect(createPlan).toHaveBeenCalledOnce();
    expect(resolvePlan).toHaveBeenCalledWith("plan-1");
  });
});
