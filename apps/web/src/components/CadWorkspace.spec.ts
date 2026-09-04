import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "../api/cad";
import * as registryApi from "../api/registry";
import CadWorkspace from "./CadWorkspace.vue";

const stlFile = new File(["solid test\nfacet normal 0 0 1\nendsolid test"], "part.stl", {
  type: "model/stl",
});

class FetchBackedXMLHttpRequest {
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  withCredentials = false;
  status = 0;
  responseText = "";
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  private method = "POST";
  private url = "";
  private headers: Record<string, string> = {};

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(key: string, value: string): void {
    this.headers[key] = value;
  }

  async send(body: FormData): Promise<void> {
    const file = body.get("file") as File;
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded: Math.max(1, Math.floor(file.size / 2)),
      total: file.size,
    } as ProgressEvent);
    const response = await fetch(this.url, { method: this.method, headers: this.headers, body });
    this.status = response.status;
    this.responseText = JSON.stringify(await response.json());
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded: file.size,
      total: file.size,
    } as ProgressEvent);
    this.onload?.();
  }
}

function jsonResponse(payload: object, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

const succeededResult = {
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
  similarity_index: null,
};

describe("CadWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal("XMLHttpRequest", FetchBackedXMLHttpRequest);
    vi.spyOn(registryApi, "fetchRegistry").mockResolvedValue({
      projects: [],
      parts: [],
      molds: [],
      revisions: [
        {
          id: "revision-1",
          mold_id: "mold-1",
          mold_code: "MOLD-001",
          revision_code: "A",
          status: "released",
          change_summary: "Demo",
          source_system: "test",
          source_revision_id: null,
          row_version: 1,
          released_at: "2026-08-29T00:00:00Z",
          artifact_count: 0,
        },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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
            ingestion_mode: "quick_analysis",
            governance_status: "unassigned",
            mold_revision_id: null,
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
          result: succeededResult,
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
    const uploadBody = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(uploadBody.get("ingestion_mode")).toBe("quick_analysis");
    expect(uploadBody.has("mold_revision_id")).toBe(false);
    expect(wrapper.text()).toContain("succeeded");
    expect(wrapper.text()).toContain("1.00 x 1.00 x 1.00");
    expect(wrapper.text()).toContain("4 / 6");
    expect(wrapper.text()).toContain("UNIT_UNCERTAIN");
    expect(wrapper.get('[role="progressbar"]').attributes("aria-valuenow")).toBe("100");
    expect(wrapper.find(".file-drop-zone .selected-file-summary").exists()).toBe(false);
    expect((wrapper.get('input[placeholder="Housing revision A"]').element as HTMLInputElement).value)
      .toBe("");
  });

  it("shows post-upload action cards after successful processing", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            artifact_id: "artifact-post",
            artifact_version_id: "version-post",
            version_number: 1,
            version_action: "new_artifact",
            job_id: "job-post",
            ingestion_mode: "quick_analysis",
            governance_status: "unassigned",
            mold_revision_id: null,
            idempotent_replay: false,
            warnings: [],
            links: { artifact: "/artifact-post", status: "/job-post", ui: "/cad/job-post" },
          },
          true,
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-post",
          capability: "cad.parse@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-post",
          correlation_id: "correlation-post",
          error: null,
          result: succeededResult,
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

    expect(wrapper.text()).toContain("What would you like to do next?");
    expect(wrapper.text()).toContain("Link to mold revision");
    expect(wrapper.text()).toContain("Find similar molds");
    expect(wrapper.text()).toContain("Run design review");
  });

  it("links to a mold revision via post-upload action", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            artifact_id: "artifact-link",
            artifact_version_id: "version-link",
            version_number: 1,
            version_action: "new_artifact",
            job_id: "job-link",
            ingestion_mode: "quick_analysis",
            governance_status: "unassigned",
            mold_revision_id: null,
            idempotent_replay: false,
            warnings: [],
            links: { artifact: "/artifact-link", status: "/job-link", ui: "/cad/job-link" },
          },
          true,
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-link",
          capability: "cad.parse@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-link",
          correlation_id: "correlation-link",
          error: null,
          result: succeededResult,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const linkMock = vi.spyOn(registryApi, "linkArtifactToRevision").mockResolvedValue({
      artifact_id: "artifact-link",
      name: "part",
      mold_revision_id: "revision-1",
      mold_revision: "MOLD-001@A",
      lifecycle_status: "active",
      quality_status: "pending",
      archive_reason: null,
      archived_at: null,
      row_version: 1,
      updated_at: "2026-09-04T00:00:00Z",
      references: { versions: 1, jobs: 1, feature_sets: 0, design_reviews: 0 },
      hard_delete_allowed: false,
    });

    const wrapper = mount(CadWorkspace, {
      global: { stubs: { CadPreview: true } },
    });
    const fileInput = wrapper.get('input[type="file"]');
    Object.defineProperty(fileInput.element, "files", { value: [stlFile] });
    await fileInput.trigger("change");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    // Click "Link to mold revision" action card
    const actionCards = wrapper.findAll(".post-action-card");
    await actionCards[0].trigger("click");
    await flushPromises();

    // The link panel should be open with revision selector
    expect(wrapper.text()).toContain("Select a mold revision to link");
    expect(wrapper.text()).toContain("MOLD-001@A");

    // Select revision and confirm
    await wrapper.get(".post-action-detail select").setValue("revision-1");
    await wrapper.get(".post-action-detail button").trigger("click");
    await flushPromises();

    expect(linkMock).toHaveBeenCalledWith(
      "artifact-link",
      0,
      "revision-1",
      "Linked via CAD upload post-action.",
    );
  });

  it("emits navigate when post-upload action cards are clicked", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            artifact_id: "artifact-nav",
            artifact_version_id: "version-nav",
            version_number: 1,
            version_action: "new_artifact",
            job_id: "job-nav",
            ingestion_mode: "quick_analysis",
            governance_status: "unassigned",
            mold_revision_id: null,
            idempotent_replay: false,
            warnings: [],
            links: {},
          },
          true,
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-nav",
          capability: "cad.parse@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-nav",
          correlation_id: "correlation-nav",
          error: null,
          result: succeededResult,
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

    const actionCards = wrapper.findAll(".post-action-card");
    // Click "Find similar molds" (index 1)
    await actionCards[1].trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["similarity"]);

    // Click "Run design review" (index 2)
    await actionCards[2].trigger("click");
    expect(wrapper.emitted("navigate")?.[1]).toEqual(["design_review"]);
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

  it("rejects an oversized CAD file before using network bandwidth", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const oversized = new File(["x"], "oversized.step", { type: "model/step" });
    Object.defineProperty(oversized, "size", { value: 200 * 1024 * 1024 + 1 });
    const wrapper = mount(CadWorkspace);
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [oversized] });

    await input.trigger("change");

    expect(wrapper.get('[role="alert"]').text()).toContain("200 MB");
    expect(wrapper.text()).not.toContain("oversized.step");
    expect(fetchMock).not.toHaveBeenCalled();
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
              source: null,
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
    await wrapper.get(".recent-cad-loader select").setValue("job-existing");
    await wrapper.get(".recent-cad-loader button:last-child").trigger("click");

    expect(wrapper.emitted("ready")?.[0]?.[0]).toMatchObject({
      artifact_version_id: "version-existing",
    });
  });

  it("loads only curated query roles and requires explicit activation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: "1.0",
        items: [
          {
            artifact_id: "artifact-query",
            name: "SIM-A Query Housing",
            kind: "cad_source",
            classification: "public_demo",
            dataset_id: "curated-cad-demo-v1",
            product_type: "housing",
            material_code: "PC_ABS",
            created_at: "2026-08-28T00:00:00Z",
            source: { type: "curated_fixture", fixture_id: "sim-a-query", role: "query", scenario: "SIM-A" },
            jobs: [
              {
                schema_version: "1.0",
                job_id: "job-query",
                capability: "cad.parse@1.0.0",
                state: "succeeded",
                stage: "completed",
                progress: 100,
                attempt: 1,
                artifact_version_id: "version-query",
                correlation_id: "correlation-query",
                error: null,
                result: {
                  cad_model_id: "cad-query",
                  artifact_version_id: "version-query",
                  cad_format: "stl",
                  unit_system: "unknown",
                  parser: { name: "trimesh", version: "4.12.2" },
                  geometry_status: "succeeded",
                  bounding_box: {
                    min: { x: 0, y: 0, z: 0 },
                    max: { x: 20, y: 12, z: 6 },
                    size: { x: 20, y: 12, z: 6 },
                  },
                  volume: 1440,
                  surface_area: 864,
                  face_count: 12,
                  edge_count: 18,
                  surface_type_histogram: { triangle: 12 },
                  quality_flags: ["UNIT_UNCERTAIN"],
                  preview: { download_url: "/preview-query" },
                  similarity_index: { status: "indexed" },
                },
              },
            ],
          },
          {
            artifact_id: "artifact-candidate",
            name: "SIM-A Strong 1",
            dataset_id: "curated-cad-demo-v1",
            source: { type: "curated_fixture", role: "candidate", scenario: "SIM-A" },
            jobs: [],
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(CadWorkspace, { global: { stubs: { CadPreview: true } } });

    await wrapper.findAll(".recent-cad-loader > button")[1].trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("dataset_id=curated-cad-demo-v1"),
      expect.anything(),
    );
    expect(wrapper.text()).toContain("SIM-A Query Housing");
    expect(wrapper.text()).not.toContain("SIM-A Strong 1");
    expect(wrapper.emitted("ready")).toBeUndefined();
    expect(wrapper.get(".recent-cad-loader button:last-child").attributes("disabled")).toBeDefined();

    await wrapper.get(".recent-cad-loader select").setValue("job-query");
    await wrapper.get(".recent-cad-loader button:last-child").trigger("click");
    expect(wrapper.emitted("ready")?.[0]?.[0]).toMatchObject({
      artifact_version_id: "version-query",
    });
  });

  it("restores the active CAD preview after the workspace is mounted again", () => {
    const activeResult: CADModelResult = {
      cad_model_id: "cad-restored",
      artifact_version_id: "version-restored",
      cad_format: "stl",
      unit_system: "mm",
      parser: { name: "trimesh", version: "4.12.2" },
      geometry_status: "succeeded",
      bounding_box: {
        min: { x: 0, y: 0, z: 0 },
        max: { x: 160, y: 160, z: 5 },
        size: { x: 160, y: 160, z: 5 },
      },
      volume: 117091.109,
      surface_area: 53218.77,
      face_count: 79558,
      edge_count: 119337,
      surface_type_histogram: { triangle: 79558 },
      quality_flags: ["UNIT_UNCERTAIN"],
      preview: {
        artifact_version_id: "preview-restored",
        original_filename: "restored.preview.stl",
        media_type: "model/stl",
        format: "stl",
        size_bytes: 3977984,
        sha256: "restored-sha",
        download_url: "/preview-restored",
      },
      similarity_index: null,
    };

    const wrapper = mount(CadWorkspace, {
      props: { activeResult },
      global: { stubs: { CadPreview: true } },
    });

    expect(wrapper.text()).toContain("160.00 x 160.00 x 5.00 mm");
    expect(wrapper.text()).toContain("79558 / 119337");
    expect(wrapper.findComponent({ name: "CadPreview" }).attributes("source")).toBe(
      "/preview-restored",
    );
  });
});
