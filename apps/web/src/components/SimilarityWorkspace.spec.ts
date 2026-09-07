import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "../api/cad";
import { setLocale } from "../i18n";
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
  afterEach(() => { vi.restoreAllMocks(); setLocale("en"); });

  it.each(["computed", "unavailable"])("shows %s surface evidence without presenting unverified scores", async (status) => {
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
            diagnostics: { coarse_returned: 16, eligible_candidates: 15, computed: 15, budget_exceeded: 0, unavailable: 0, fine_seconds: 1.25, shared_cache_hits: 14, process_cache_hits: 0 },
            match_assessment: { status: "not_calibrated", decision: "insufficient_evidence", scope: "returned_candidates_only", qualified_count: 0 },
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
                baseline_overall_score: 0.99,
                ranking_basis: status === "computed" ? "surface_adjusted" : "reference_only",
                geometric_verification: status === "computed" ? {
                  status, algorithm: "cpu-surface-verification@1.0", mode: "normalized_shape",
                  calibration_status: "not_calibrated", query_coverage: 0.92, candidate_coverage: 0.85,
                  f_score: 0.88, mean_distance: 0.02, p95_distance: 0.05, tolerance: 0.08, score_factor: 0.94,
                } : {
                  status, algorithm: "cpu-surface-verification@1.0", mode: "normalized_shape",
                  calibration_status: "not_calibrated", error_code: "SURFACE_PREVIEW_MISSING",
                },
                geometry_ranking: {
                  score: 0.96, policy: "block-distance@1.0",
                  block_scores: { principal_extent_ratios: 0.94 },
                  block_coverage: 1, coarse_cosine: 0.99, fallback_reason: null,
                },
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
    if (status === "unavailable") {
      await wrapper.get('[data-testid="comparison-mode"]').setValue("engineering_size");
      expect(wrapper.text()).toContain("Surface tolerance (mm)");
    }
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const submitted = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(submitted.comparison_mode).toBe(status === "unavailable" ? "engineering_size" : "normalized_shape");
    expect(submitted.tolerance_mm).toBe(0.5);
    expect(wrapper.text()).toContain("Reference A");
    expect(wrapper.get('[data-testid="similarity-diagnostics"]').text()).toContain("Coarse candidates: 16");
    expect(wrapper.get('[data-testid="match-assessment"]').text()).toContain("Human calibration is not active");
    expect(wrapper.text()).toContain("How geometry was ranked");
    expect(wrapper.text()).toContain("block-distance@1.0");
    expect(wrapper.get('[data-testid="similarity-validation-note"]').text()).toContain(
      "not the probability that a mold can be reused",
    );
    expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("not calibrated");
    if (status === "computed") {
      expect(wrapper.get(".overall-score").text()).toBe("92.8%");
      expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("92.0%");
      expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("0.0200");
    } else {
      expect(wrapper.get(".overall-score").text()).toBe("Reference only");
      expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("not a verified match");
      expect(wrapper.get('[data-testid="surface-verification"]').text()).not.toContain("Mean surface distance");
    }
    setLocale("zh-TW");
    await flushPromises();
    expect(wrapper.get('[data-testid="similarity-diagnostics"]').text()).toContain("共用快取命中：14");
    expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("自動表面幾何驗證");
    expect(wrapper.get('[data-testid="surface-verification"]').text()).toContain("不代表工程核准");
    if (status === "unavailable") expect(wrapper.get(".overall-score").text()).toBe("僅供參考");
    setLocale("en");
    await flushPromises();
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

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { feedback_id: "feedback-1", created: true, action: "accept_reference" },
        201,
      ),
    );
    await wrapper.get(".feedback-actions button").trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(wrapper.text()).toContain("Feedback saved for offline evaluation.");
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
