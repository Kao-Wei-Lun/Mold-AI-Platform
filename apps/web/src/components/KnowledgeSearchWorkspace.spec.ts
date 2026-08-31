import { flushPromises, mount } from "@vue/test-utils";

import type { KnowledgeDocument } from "../api/knowledge";
import KnowledgeSearchWorkspace from "./KnowledgeSearchWorkspace.vue";

function jsonResponse(payload: object, status = 200): Response {
  return { ok: status < 400, status, json: async () => payload } as Response;
}

const indexedDocument = {
  document_id: "document-1", title: "Demo Mold Design Guide",
  ingestion_status: "indexed", publication_status: "published",
} as KnowledgeDocument;

const searchPayload = {
  search_id: "search-1", schema_version: "1.0", answer_mode: "extractive_evidence",
  answer: "Found 1 authorized source passages. Review the cited excerpts.",
  claims: [{
    text: "Rib thickness should be reviewed against nominal wall thickness.",
    evidence_refs: ["citation-1"], evidence_type: "document_excerpt",
  }],
  citations: [{
    citation_id: "citation-1", artifact_version_id: "version-1", document_id: "document-1",
    title: "Demo Mold Design Guide", locator: "section:Rib Design,paragraphs:1-1",
    authority: "reviewed_demo", effective_from: null, effective_to: null,
    source_url: "/api/v1/artifact-versions/version-1/download",
  }],
  results: [{
    rank: 1, chunk_id: "chunk-1",
    excerpt: "Rib thickness should be reviewed against nominal wall thickness.", score: 0.91,
    score_breakdown: { lexical: 1, vector: 0.9, authority: 0.9, freshness: 1 },
    citation_id: "citation-1",
  }],
  abstained: false, retrieved_at: "2026-08-26T00:00:00Z",
  principal_scope_source: "server_demo_policy", limitations: ["No LLM synthesis."],
};

describe("KnowledgeSearchWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("retrieves extractive evidence with a protected versioned citation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }))
      .mockResolvedValueOnce(jsonResponse(searchPayload));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(KnowledgeSearchWorkspace);
    await flushPromises();
    await wrapper.get(".knowledge-search-form textarea").setValue("rib thickness");
    await wrapper.get(".knowledge-search-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Found 1 authorized source passages");
    expect(wrapper.text()).toContain("Rib thickness should be reviewed");
    expect(wrapper.text()).toContain("section:Rib Design,paragraphs:1-1");
    const citation = wrapper.get(".citation-download");
    expect(citation.element.tagName).toBe("BUTTON");
    expect(citation.attributes("href")).toBeUndefined();
    expect(wrapper.text()).toContain("No LLM synthesis");
  });

  it("keeps retrieval disabled when no published document is indexed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      jsonResponse({ schema_version: "1.0", items: [] }),
    ));
    const wrapper = mount(KnowledgeSearchWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("0 published and indexed sources available");
    expect(wrapper.get('.knowledge-search-form button[type="submit"]').attributes("disabled")).toBeDefined();
  });

  it("opens the governed source record from a selected citation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }))
      .mockResolvedValueOnce(jsonResponse(searchPayload));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(KnowledgeSearchWorkspace);
    await flushPromises();
    await wrapper.get(".knowledge-search-form textarea").setValue("rib thickness");
    await wrapper.get(".knowledge-search-form").trigger("submit");
    await flushPromises();
    await wrapper.get(".knowledge-source-actions .secondary-button").trigger("click");

    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/knowledge/document-1"]);
  });
});
