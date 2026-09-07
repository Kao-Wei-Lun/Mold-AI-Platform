import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "../api/cad";
import SimilarityWorkspace from "./SimilarityWorkspace.vue";

const query: CADModelResult = {
  cad_model_id: "cad-query",
  artifact_version_id: "version-query",
  cad_format: "stl",
  unit_system: "unknown",
  parser: { name: "trimesh", version: "4.12.2" },
  geometry_status: "succeeded",
  bounding_box: {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 10, y: 10, z: 10 },
    size: { x: 10, y: 10, z: 10 },
  },
  volume: 166.67,
  surface_area: 236.6,
  face_count: 4,
  edge_count: 6,
  surface_type_histogram: { triangle: 4 },
  quality_flags: ["UNIT_UNCERTAIN"],
  preview: {
    artifact_version_id: "preview-query",
    original_filename: "query.preview.stl",
    media_type: "model/stl",
    format: "stl",
    size_bytes: 100,
    sha256: "query-sha",
    download_url: "/query-preview",
  },
  similarity_index: {
    feature_set_id: "feature-query",
    schema_version: "1.0",
    extractor_version: "1.0.0",
    index_version: "cad-demo-v1",
    status: "indexed",
    error_code: null,
  },
};

function jsonResponse(payload: object, status = 200): Response {
  return { ok: status < 400, status, json: async () => payload } as Response;
}

describe("SimilarityWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("runs a search and shows deterministic scores and evidence", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            search_id: "search-1",
            job_id: "job-1",
            idempotent_replay: false,
            links: { status: "/job-1", result: "/search-1", ui: "/similarity/job-1" },
          },
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-1",
          capability: "mold.similarity_search@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-query",
          correlation_id: "correlation-1",
          error: null,
          result: {
            schema_version: "1.0",
            search_id: "search-1",
            query_ref: {
              artifact_id: "artifact-query",
              cad_artifact_version_id: "version-query",
              artifact_name: "Query",
              preview: {
                artifact_version_id: "preview-query",
                download_url: "/query-preview",
              },
            },
            profile: "demo-general@1.0",
            profile_weights: { geometry: 0.35, dimension: 0.25, topology: 0.3, metadata: 0.1 },
            feature_schema_version: "1.0",
            extractor_version: "1.0.0",
            index_version: "cad-demo-v1",
            filters: { dataset_ids: ["public-demo-v1"] },
            result_count: 1,
            results: [
              {
                rank: 1,
                artifact_id: "artifact-a",
                artifact_version_id: "version-a",
                artifact_name: "Reference A",
                dataset_id: "public-demo-v1",
                product_type: "housing",
                material_code: "PC_ABS",
                coarse_score: 0.97,
                overall_score: 0.928,
                sub_scores: { geometry: 0.96, dimension: 0.94, topology: 0.91, metadata: 1 },
                effective_weights: {
                  geometry: 0.35,
                  dimension: 0.25,
                  topology: 0.3,
                  metadata: 0.1,
                },
                feature_availability: {
                  geometry: true,
                  dimension: true,
                  topology: true,
                  metadata: true,
                },
                similarities: [
                  {
                    type: "shape_proportions",
                    message: "Overall proportions are close.",
                    evidence_ref: "feature:a:geometry",
                  },
                ],
                differences: [
                  {
                    type: "overall_dimensions",
                    message: "One dimension is slightly different.",
                    evidence_ref: "feature:a:dimension",
                  },
                ],
                quality_flags: [],
                preview: { artifact_version_id: "preview-a", download_url: "/preview-a" },
              },
            ],
            limitations: ["Visual embedding is not included."],
            lineage_ref: "similarity-search:search-1",
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(SimilarityWorkspace, {
      props: { query },
      global: { stubs: { CadPreview: true, DeviationHeatmap: true } },
    });
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Reference A");
    expect(wrapper.text()).toContain("92.8%");
    expect(wrapper.text()).toContain("Overall proportions are close");
    expect(wrapper.text()).toContain("One dimension is slightly different");
    expect(wrapper.findAllComponents({ name: "CadPreview" })).toHaveLength(2);

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          schema_version: "1.0",
          comparison_id: "comparison-1",
          search_id: "search-1",
          candidate_artifact_version_id: "version-a",
          created: true,
          alignment_status: "full",
          transform: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
          result: {
            alignment_status: "full",
            alignment: { pca_rmse: 0.02, final_rmse: 0.01, icp_attempted: true, icp_converged: true, icp_iterations: 3, symmetry_ambiguity: false },
            deviation: { mode: "signed", minimum: -0.02, maximum: 0.03, rmse: 0.01, sample_count: 128, tolerance: 0.05 },
            roi: null,
            roi_similarity_score: null,
            heatmap: { positions: [[0, 0, 0]], deviations: [0.01] },
          },
          lineage_ref: "similarity-comparison:comparison-1",
        },
        201,
      ),
    );
    await wrapper.get(".deviation-heading button").trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(wrapper.text()).toContain("3D alignment and deviation");
    expect(wrapper.text()).toContain("0.01");
    expect(wrapper.findComponent({ name: "DeviationHeatmap" }).exists()).toBe(true);
  });

  it("keeps search disabled when the query has no indexed feature", () => {
    const wrapper = mount(SimilarityWorkspace, {
      props: { query: { ...query, similarity_index: null } },
    });

    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("not indexed");
  });

  it("guides the user to prepare CAD when no query is selected", async () => {
    const wrapper = mount(SimilarityWorkspace, { props: { query: null } });

    expect(wrapper.text()).toContain("Prepare a CAD query first");
    expect(wrapper.find("form").exists()).toBe(false);
    await wrapper.get(".workspace-empty-state button").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["cad"]);
  });
});
