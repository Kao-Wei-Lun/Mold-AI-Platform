import { flushPromises, mount } from "@vue/test-utils";

import CadWorkspace from "./CadWorkspace.vue";

const stlFile = new File(["solid test\nfacet normal 0 0 1\nendsolid test"], "part.stl", {
  type: "model/stl",
});

function jsonResponse(payload: object, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

describe("CadWorkspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uploads a CAD artifact and renders the completed geometry result", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            artifact_id: "artifact-1",
            artifact_version_id: "version-1",
            job_id: "job-1",
            idempotent_replay: false,
            warnings: ["Basic screening only."],
            links: { artifact: "/artifact-1", status: "/job-1", ui: "/cad/job-1" },
          },
          true,
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-1",
          capability: "cad.parse@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-1",
          correlation_id: "correlation-1",
          error: null,
          result: {
            cad_model_id: "cad-1",
            artifact_version_id: "version-1",
            cad_format: "stl",
            unit_system: "unknown",
            parser: { name: "trimesh", version: "4.12.2" },
            geometry_status: "succeeded",
            bounding_box: {
              min: { x: 0, y: 0, z: 0 },
              max: { x: 1, y: 1, z: 1 },
              size: { x: 1, y: 1, z: 1 },
            },
            volume: 0.1667,
            surface_area: 2.366,
            face_count: 4,
            edge_count: 6,
            surface_type_histogram: { triangle: 4 },
            quality_flags: ["UNIT_UNCERTAIN"],
            preview: {
              artifact_version_id: "preview-1",
              original_filename: "part.preview.stl",
              media_type: "model/stl",
              format: "stl",
              size_bytes: 100,
              sha256: "abc",
              download_url: "/preview-1",
            },
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(CadWorkspace, {
      global: { stubs: { CadPreview: true } },
    });
    const fileInput = wrapper.get('input[type="file"]');
    Object.defineProperty(fileInput.element, "files", { value: [stlFile] });
    await fileInput.trigger("change");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("succeeded");
    expect(wrapper.text()).toContain("1.00 x 1.00 x 1.00");
    expect(wrapper.text()).toContain("4 / 6");
    expect(wrapper.text()).toContain("UNIT_UNCERTAIN");
  });

  it("shows a server validation message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "VALIDATION_FILE_SIGNATURE", message: "Invalid STL signature." } },
          false,
          400,
        ),
      ),
    );
    const wrapper = mount(CadWorkspace);
    const fileInput = wrapper.get('input[type="file"]');
    Object.defineProperty(fileInput.element, "files", { value: [stlFile] });
    await fileInput.trigger("change");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("Invalid STL signature");
  });

  it("loads an existing indexed CAD artifact as the active query", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          schema_version: "1.0",
          items: [
            {
              artifact_id: "artifact-existing",
              name: "Existing housing",
              kind: "cad_source",
              classification: "public_demo",
              dataset_id: "public-demo-v1",
              product_type: "housing",
              material_code: "PC_ABS",
              created_at: "2026-08-26T00:00:00Z",
              jobs: [
                {
                  schema_version: "1.0",
                  job_id: "job-existing",
                  capability: "cad.parse@1.0.0",
                  state: "succeeded",
                  stage: "completed",
                  progress: 100,
                  attempt: 1,
                  artifact_version_id: "version-existing",
                  correlation_id: "correlation-existing",
                  error: null,
                  result: {
                    cad_model_id: "cad-existing",
                    artifact_version_id: "version-existing",
                    cad_format: "stl",
                    unit_system: "unknown",
                    parser: { name: "trimesh", version: "4.12.2" },
                    geometry_status: "succeeded",
                    bounding_box: {
                      min: { x: 0, y: 0, z: 0 },
                      max: { x: 1, y: 1, z: 1 },
                      size: { x: 1, y: 1, z: 1 },
                    },
                    volume: 0.1667,
                    surface_area: 2.366,
                    face_count: 4,
                    edge_count: 6,
                    surface_type_histogram: { triangle: 4 },
                    quality_flags: ["UNIT_UNCERTAIN"],
                    preview: {
                      artifact_version_id: "preview-existing",
                      download_url: "/preview-existing",
                    },
                    similarity_index: {
                      feature_set_id: "feature-existing",
                      schema_version: "1.0",
                      extractor_version: "1.0.0",
                      index_version: "cad-demo-v1",
                      status: "indexed",
                      error_code: null,
                    },
                  },
                },
              ],
            },
          ],
        }),
      ),
    );
    const wrapper = mount(CadWorkspace, {
      global: { stubs: { CadPreview: true } },
    });

    await wrapper.get(".recent-cad-loader > button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Existing housing");
    await wrapper.get(".recent-cad-loader button:last-child").trigger("click");

    expect(wrapper.emitted("ready")?.[0]?.[0]).toMatchObject({
      artifact_version_id: "version-existing",
    });
  });
});
