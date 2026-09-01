import { flushPromises, mount } from "@vue/test-utils";

import { setLocale } from "../i18n";
import RegistryCadHistoryWorkspace from "./RegistryCadHistoryWorkspace.vue";

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

describe("RegistryCadHistoryWorkspace", () => {
  beforeEach(() => setLocale("en"));
  afterEach(() => vi.restoreAllMocks());

  it("shows a mold with its revisions and opens the revision history route", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: "part-1", part_number: "PART-001", mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "active", row_version: 1, revision_count: 1,
      revisions: [{ id: "revision-1", mold_id: "mold-1", mold_code: "MOLD-001", revision_code: "A", status: "released", change_summary: "Initial release", source_system: "platform_demo", source_revision_id: null, row_version: 1, released_at: "2026-08-29T00:00:00Z", artifact_count: 2 }],
    })));
    const wrapper = mount(RegistryCadHistoryWorkspace, { props: { domain: "molds", path: "/data/molds/mold-1", canManage: true } });
    await flushPromises();

    expect(wrapper.text()).toContain("Housing mold");
    expect(wrapper.text()).toContain("Initial release");
    expect(wrapper.text()).toContain("Edit controlled metadata");
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/molds/revisions/revision-1"]);
  });

  it("supports stable registry detail routes and tab deep links", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: "part-1", part_number: "PART-001", mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "active", row_version: 1, revision_count: 1, current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 2,
      revisions: [{ id: "revision-1", mold_id: "mold-1", mold_code: "MOLD-001", revision_code: "A", status: "released", change_summary: "Initial release", source_system: "platform_demo", source_revision_id: null, row_version: 1, released_at: "2026-08-29T00:00:00Z", artifact_count: 2 }],
    })));
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "molds", path: "/governance/mold-registry/molds/mold-1?tab=versions", registryMode: true },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Initial release");
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toContain("Versions");
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/governance/mold-registry/revisions/revision-1"]);
  });

  it("creates the next governed revision from the mold detail action drawer", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") return response({
        id: "revision-2", mold_id: "mold-1", mold_code: "MOLD-001", revision_code: "B", status: "draft", change_summary: "Cooling update", source_system: "platform_demo", source_revision_id: "revision-1", row_version: 1, released_at: null, artifact_count: 0, allowed_actions: ["edit", "release", "archive"],
      });
      return response({
        id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: "part-1", part_number: "PART-001", mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "active", row_version: 1, revision_count: 1, current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 1, allowed_actions: ["edit", "create_revision", "retire", "archive"],
        revisions: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "molds", path: "/governance/mold-registry/molds/mold-1", registryMode: true, canManage: true },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Create next revision")!.trigger("click");
    await wrapper.findAll("textarea")[0].setValue("Cooling update");
    await wrapper.findAll("textarea")[1].setValue("Start reviewed iteration");
    await wrapper.findAll("button").find((button) => button.text() === "Confirm governed action")!.trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining("/api/v1/registry/molds/mold-1/revisions"), expect.objectContaining({ method: "POST" }));
    expect(wrapper.emitted("navigate")?.at(-1)).toEqual(["/governance/mold-registry/revisions/revision-2"]);
  });

  it("previews mold impact before a lifecycle action", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("impact-preview")) return response({ schema_version: "1.0", mold_id: "mold-1", mold_code: "MOLD-001", status: "active", row_version: 1, allowed_actions: ["retire"], impact: { draft_revisions: 1, released_revisions: 1, cad_artifacts: 2, mold_plans: 3, design_reviews: 4, similarity_searches: 5, cae_studies: 6, trial_cases: 7 } });
      if (init?.method === "POST") return response({ id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: null, part_number: null, mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "retired", row_version: 2, revision_count: 1, current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 2, allowed_actions: ["edit", "reactivate", "archive"], impact: {} });
      return response({ id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: null, part_number: null, mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "active", row_version: 1, revision_count: 1, current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 2, allowed_actions: ["edit", "create_revision", "retire", "archive"], revisions: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "molds", path: "/governance/mold-registry/molds/mold-1", registryMode: true, canManage: true },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Retire mold")!.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Mold planning records");
    expect(wrapper.text()).toContain("3");
    await wrapper.find("textarea").setValue("End new planning");
    await wrapper.findAll("button").find((button) => button.text() === "Confirm governed action")!.trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining("/api/v1/registry/molds/mold-1/actions"), expect.objectContaining({ method: "POST" }));
    expect(wrapper.text()).toContain("retired");
  });

  it("shows governed engineering history, lineage, audit and preserves deep links", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("engineering-history")) return response({
        schema_version: "1.0",
        subject: { mold_id: "mold-1", mold_code: "MOLD-001", revision_id: null, revision_code: null },
        counts: { mold_plan: 1, design_review: 0, similarity_search: 0, cae_study: 0, trial_case: 0 },
        items: [{ record_type: "mold_plan", record_id: "plan-1", title: "PLAN-001 · Housing", status: "ready", owner: "engineer", revision_ref: "MOLD-001@A", created_at: "2026-08-29T00:00:00Z", updated_at: "2026-08-29T01:00:00Z", deep_link: "/engineering/mold-planning?deep_link_version=1.0&target=mold_plan&mold_plan_id=00000000-0000-4000-8000-000000000001" }],
        page: { number: 1, size: 25, total: 1, has_next: false },
        lineage: { nodes: [{ id: "mold-1", type: "mold", label: "MOLD-001", status: "active" }], edges: [] },
        audit_events: [{ id: "audit-1", event_type: "registry.mold.created.v1", actor_id: "engineer", target_refs: ["mold:mold-1"], detail: { reason: "Create mold" }, payload_hash: "abcdef1234567890", created_at: "2026-08-29T00:00:00Z" }],
      });
      return response({ id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: null, part_number: null, mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection", cavity_count: 2, status: "active", row_version: 1, revision_count: 1, current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 1, revisions: [] });
    }));
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "molds", path: "/governance/mold-registry/molds/mold-1?tab=engineering-history", registryMode: true },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("PLAN-001 · Housing");
    expect(wrapper.emitted("contextChange")?.[0]?.[0]).toMatchObject({ page: "mold_registry", mold_id: "mold-1" });
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.emitted("navigate")?.at(-1)?.[0]).toContain("target=mold_plan");

    await wrapper.setProps({ path: "/governance/mold-registry/molds/mold-1?tab=lineage" });
    await flushPromises();
    expect(wrapper.text()).toContain("MOLD-001");
    await wrapper.setProps({ path: "/governance/mold-registry/molds/mold-1?tab=audit" });
    await flushPromises();
    expect(wrapper.text()).toContain("registry.mold.created.v1");
    expect(wrapper.text()).toContain("Create mold");
  });

  it("shows a governed message when the Registry returns HTML instead of JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("engineering-history")) return new Response(
        "<!doctype html><title>Server Error</title>",
        { status: 500, headers: { "content-type": "text/html; charset=utf-8" } },
      );
      return response({
        id: "mold-1", project_id: "project-1", project_code: "P-001", product_part_id: null,
        part_number: null, mold_code: "MOLD-001", name: "Housing mold", mold_type: "injection",
        cavity_count: 2, status: "active", row_version: 1, revision_count: 1,
        current_revision_id: "revision-1", current_revision_code: "A", artifact_count: 1,
        revisions: [],
      });
    }));
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "molds", path: "/governance/mold-registry/molds/mold-1", registryMode: true },
    });
    await flushPromises();

    expect(wrapper.text()).toContain(
      "The Registry service returned an invalid response. Please retry or contact the administrator.",
    );
    expect(wrapper.text()).not.toContain("Unexpected token");
  });

  it("shows CAD versions, geometry, feature indexes, jobs and lineage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      artifact_id: "artifact-1", name: "Housing A", kind: "cad_source", classification: "public_demo", dataset_id: "curated", product_type: "housing", material_code: "ABS", mold_revision_id: "revision-1", mold_revision: { revision_code: "A", mold_id: "mold-1", mold_code: "MOLD-001" }, lifecycle_status: "active", quality_status: "validated", created_at: "2026-08-29T00:00:00Z", source: null,
      versions: [{ artifact_version_id: "version-1", version_number: 1, original_filename: "housing.stl", media_type: "model/stl", format: "stl", size_bytes: 512, sha256: "abc", classification: "public_demo", malware_status: "basic_screened", source_system: "curated", supersedes_id: null, created_at: "2026-08-29T00:00:00Z", download_url: "/download/version-1" }],
      jobs: [
        { schema_version: "1.0", job_id: "search-1", capability: "mold.similarity_search@1.0.0", state: "succeeded", stage: "completed", progress: 100, attempt: 1, artifact_version_id: "version-1", correlation_id: "correlation-search", error: null, result: { search_id: "search-1", query_ref: {}, results: [] } },
        { schema_version: "1.0", job_id: "job-1", capability: "cad.parse@1.0.0", state: "succeeded", stage: "completed", progress: 100, attempt: 1, artifact_version_id: "version-1", correlation_id: "correlation-1", error: null, result: { cad_model_id: "cad-1", artifact_version_id: "version-1", cad_format: "stl", unit_system: "mm", parser: { name: "trimesh", version: "4" }, geometry_status: "succeeded", bounding_box: { min: { x: 0, y: 0, z: 0 }, max: { x: 1, y: 1, z: 1 }, size: { x: 1, y: 1, z: 1 } }, volume: 1, surface_area: 6, face_count: 12, edge_count: 18, surface_type_histogram: { triangle: 12 }, quality_flags: [], preview: { artifact_version_id: "preview-1", original_filename: "preview.stl", media_type: "model/stl", format: "stl", size_bytes: 20 * 1024 * 1024, sha256: "def", download_url: "/download/preview-1" }, similarity_index: null, feature_sets: [{ feature_set_id: "feature-1", schema_version: "1.0", extractor_version: "1", index_collection: "cad", index_version: "v1", status: "indexed", error_code: null, created_at: "2026-08-29T00:00:00Z" }] } },
      ],
      lineage: [{ edge_id: "edge-1", from_artifact_version_id: "version-1", to_artifact_version_id: "preview-1", relationship: "derived_from", job_id: "job-1", direction: "outbound", created_at: "2026-08-29T00:00:00Z" }],
    })));
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "cad-artifacts", path: "/data/cad-artifacts/artifact-1?tab=geometry" },
      global: { stubs: { CadPreview: true } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("trimesh@4");
    expect(wrapper.text()).toContain("indexed");
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toContain("1");
    expect(wrapper.findAll(".history-detail-card")).toHaveLength(1);
    expect(wrapper.text()).toContain("Large 3D preview");
    expect(wrapper.find("cad-preview-stub").exists()).toBe(false);
    await wrapper.get(".large-cad-preview-notice button").trigger("click");
    await flushPromises();
    expect(wrapper.find("cad-preview-stub").exists()).toBe(true);
    await wrapper.setProps({ path: "/data/cad-artifacts/artifact-1?tab=lineage" });
    await flushPromises();
    expect(wrapper.text()).toContain("derived_from");
    expect(wrapper.text()).toContain("preview-1");
  });
});
