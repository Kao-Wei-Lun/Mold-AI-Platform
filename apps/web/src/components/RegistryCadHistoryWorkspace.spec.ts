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

  it("shows CAD versions, geometry, feature indexes, jobs and lineage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      artifact_id: "artifact-1", name: "Housing A", kind: "cad_source", classification: "public_demo", dataset_id: "curated", product_type: "housing", material_code: "ABS", mold_revision_id: "revision-1", mold_revision: { revision_code: "A", mold_id: "mold-1", mold_code: "MOLD-001" }, lifecycle_status: "active", quality_status: "validated", created_at: "2026-08-29T00:00:00Z", source: null,
      versions: [{ artifact_version_id: "version-1", version_number: 1, original_filename: "housing.stl", media_type: "model/stl", format: "stl", size_bytes: 512, sha256: "abc", classification: "public_demo", malware_status: "basic_screened", source_system: "curated", supersedes_id: null, created_at: "2026-08-29T00:00:00Z", download_url: "/download/version-1" }],
      jobs: [{ schema_version: "1.0", job_id: "job-1", capability: "cad.parse@1.0.0", state: "succeeded", stage: "completed", progress: 100, attempt: 1, artifact_version_id: "version-1", correlation_id: "correlation-1", error: null, result: { cad_model_id: "cad-1", artifact_version_id: "version-1", cad_format: "stl", unit_system: "mm", parser: { name: "trimesh", version: "4" }, geometry_status: "succeeded", bounding_box: { min: { x: 0, y: 0, z: 0 }, max: { x: 1, y: 1, z: 1 }, size: { x: 1, y: 1, z: 1 } }, volume: 1, surface_area: 6, face_count: 12, edge_count: 18, surface_type_histogram: { triangle: 12 }, quality_flags: [], preview: { artifact_version_id: "preview-1", original_filename: "preview.stl", media_type: "model/stl", format: "stl", size_bytes: 256, sha256: "def", download_url: "/download/preview-1" }, similarity_index: null, feature_sets: [{ feature_set_id: "feature-1", schema_version: "1.0", extractor_version: "1", index_collection: "cad", index_version: "v1", status: "indexed", error_code: null, created_at: "2026-08-29T00:00:00Z" }] } }],
      lineage: [{ edge_id: "edge-1", from_artifact_version_id: "version-1", to_artifact_version_id: "preview-1", relationship: "derived_from", job_id: "job-1", direction: "outbound", created_at: "2026-08-29T00:00:00Z" }],
    })));
    const wrapper = mount(RegistryCadHistoryWorkspace, {
      props: { domain: "cad-artifacts", path: "/data/cad-artifacts/artifact-1?tab=geometry" },
      global: { stubs: { CadPreview: true } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("trimesh@4");
    expect(wrapper.text()).toContain("indexed");
    await wrapper.setProps({ path: "/data/cad-artifacts/artifact-1?tab=lineage" });
    await flushPromises();
    expect(wrapper.text()).toContain("derived_from");
    expect(wrapper.text()).toContain("preview-1");
  });
});
