import { fetchDesignReview } from "./designReview";
import { fetchKnowledgeSearch } from "./knowledge";
import { fetchProcessSearch } from "./processTrial";
import { fetchSimilaritySearch } from "./similarity";

const JOB_ID = "11111111-1111-4111-8111-111111111111";

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

describe("deep-link read-only API resolution", () => {
  afterEach(() => vi.restoreAllMocks());

  it("resolves all MCP-linked records using GET requests only", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ job_id: JOB_ID }))
      .mockResolvedValueOnce(jsonResponse({ job_id: JOB_ID, state: "succeeded", result: {} }))
      .mockResolvedValueOnce(jsonResponse({ job_id: JOB_ID }))
      .mockResolvedValueOnce(jsonResponse({ job_id: JOB_ID, state: "succeeded", result: {} }))
      .mockResolvedValueOnce(jsonResponse({ search_id: "knowledge", results: [], citations: [] }))
      .mockResolvedValueOnce(jsonResponse({ search_id: "process", results: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchSimilaritySearch("similarity-id");
    await fetchDesignReview("review-id");
    await fetchKnowledgeSearch("knowledge-id");
    await fetchProcessSearch("process-id");

    expect(fetchMock).toHaveBeenCalledTimes(6);
    for (const [, init] of fetchMock.mock.calls) {
      expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
      expect((init as RequestInit | undefined)?.body).toBeUndefined();
    }
  });
});
