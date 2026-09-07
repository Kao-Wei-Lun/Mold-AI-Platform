import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "../api/cad";
import type { SimilarityJob } from "../api/similarity";
import type { DeepLinkContext } from "../deepLinks";
import SimilarityWorkspace from "./SimilarityWorkspace.vue";

const api = vi.hoisted(() => ({
  createSimilaritySearch: vi.fn(), fetchSimilarityJob: vi.fn(), fetchSimilaritySearch: vi.fn(),
  createSimilarityComparison: vi.fn(), fetchSimilarityEngineeringProfile: vi.fn(),
  recordSimilarityFeedback: vi.fn(), saveSimilarityEngineeringProfile: vi.fn(),
}));
vi.mock("../api/similarity", () => api);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => { resolve = yes; });
  return { promise, resolve };
}

const query = { artifact_version_id: "query-a", similarity_index: { status: "indexed" } } as CADModelResult;
function link(searchId: string, candidateId?: string): DeepLinkContext {
  return { deep_link_version: "1.0", target: "similarity", correlation_id: "test",
    refs: { search_id: searchId, ...(candidateId ? { candidate_id: candidateId } : {}) } };
}
function job(id: string): SimilarityJob {
  return {
    schema_version: "1.0", capability: "mold.similarity_search@1.0.0", attempt: 1,
    artifact_version_id: `query-${id}`, correlation_id: "test", error: null,
    job_id: id, state: "succeeded", stage: "completed", progress: 100,
    result: { schema_version: "1.1", search_id: id, profile: "test", index_version: "v2", result_count: 2,
      profile_weights: { geometry: 1 }, feature_schema_version: "2.0", extractor_version: "2.1.0",
      filters: {}, lineage_ref: "test",
      query_ref: { artifact_id: `artifact-${id}`, artifact_name: `Query ${id}`,
        cad_artifact_version_id: `query-${id}`,
        preview: { artifact_version_id: `query-preview-${id}`, download_url: `/query-${id}` } },
      results: [1, 2].map((i) => ({
        artifact_id: `${id}-artifact-${i}`, dataset_id: "test", product_type: "", material_code: "",
        coarse_score: .9, effective_weights: { geometry: 1 }, feature_availability: { geometry: true },
        quality_flags: [],
        artifact_version_id: `${id}-${i}`, artifact_name: `${id} candidate ${i}`, rank: i,
        sub_scores: { geometry: .9 }, overall_score: .9, similarities: [], differences: [],
        preview: { artifact_version_id: `${id}-preview-${i}`, download_url: `/${id}-${i}.stl` },
      })), limitations: [],
    },
  };
}
const global = { stubs: {
  CadPreview: { props: ["source"], template: '<div data-preview :data-source="source" />' },
  DeviationHeatmap: { template: '<div data-heatmap />' },
} };

describe("Similarity selection ownership", () => {
  beforeEach(() => Object.values(api).forEach((mock) => mock.mockReset()));

  it("does not replace the new query results when the old search finishes late", async () => {
    const oldJob = deferred<SimilarityJob>();
    api.createSimilaritySearch.mockResolvedValueOnce({ job_id: "old" }).mockResolvedValueOnce({ job_id: "new" });
    api.fetchSimilarityJob.mockReturnValueOnce(oldJob.promise).mockResolvedValueOnce(job("new"));
    const wrapper = mount(SimilarityWorkspace, { props: { query }, global });
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    await wrapper.setProps({ query: { ...query, artifact_version_id: "query-b" } });
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    oldJob.resolve(job("old"));
    await flushPromises();
    expect(wrapper.get(".match-card.selected").text()).toContain("new candidate 1");
    expect(wrapper.findAll("[data-preview]").map((item) => item.attributes("data-source")))
      .toEqual(["/query-new", "/new-1.stl"]);
    wrapper.unmount();
  });

  it("ignores a superseded deep-link result", async () => {
    const oldJob = deferred<SimilarityJob>();
    api.fetchSimilaritySearch.mockReturnValueOnce(oldJob.promise).mockResolvedValueOnce(job("new"));
    const wrapper = mount(SimilarityWorkspace, { props: { query, deepLink: link("old") }, global });
    await wrapper.setProps({ deepLink: link("new", "new-2") });
    await flushPromises();
    oldJob.resolve(job("old"));
    await flushPromises();
    expect(wrapper.get(".match-card.selected").text()).toContain("new candidate 2");
    wrapper.unmount();
  });

  it("preserves the user's candidate when the same search is refreshed without an explicit target", async () => {
    api.fetchSimilaritySearch.mockImplementation(async () => job("same"));
    const wrapper = mount(SimilarityWorkspace, { props: { query, deepLink: link("same", "same-1") }, global });
    await flushPromises();
    await wrapper.findAll(".match-card")[1].trigger("click");
    await wrapper.setProps({ deepLink: link("same") });
    await flushPromises();
    expect(wrapper.get(".match-card.selected").text()).toContain("same candidate 2");
    wrapper.unmount();
  });

  it("does not show a late deviation overlay for the previously selected candidate", async () => {
    const oldComparison = deferred<object>();
    api.fetchSimilaritySearch.mockResolvedValue(job("same"));
    api.createSimilarityComparison.mockReturnValue(oldComparison.promise);
    const wrapper = mount(SimilarityWorkspace, { props: { query, deepLink: link("same") }, global });
    await flushPromises();
    await wrapper.get(".deviation-heading button").trigger("click");
    await wrapper.findAll(".match-card")[1].trigger("click");
    oldComparison.resolve({ result: { alignment: { final_rmse: 0 }, deviation: {}, heatmap: {} } });
    await flushPromises();
    expect(wrapper.find("[data-heatmap]").exists()).toBe(false);
    expect(wrapper.get(".deviation-heading button").attributes("disabled")).toBeUndefined();
    expect(wrapper.get(".match-card.selected").text()).toContain("same candidate 2");
    wrapper.unmount();
  });
});
