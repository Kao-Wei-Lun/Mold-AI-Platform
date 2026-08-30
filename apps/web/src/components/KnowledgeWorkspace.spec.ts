import { flushPromises, mount } from "@vue/test-utils";

import KnowledgeWorkspace from "./KnowledgeWorkspace.vue";

function jsonResponse(payload: object, status = 200): Response {
  return { ok: status < 400, status, json: async () => payload } as Response;
}

const indexedDocument = {
  document_id: "document-1",
  artifact_id: "artifact-1",
  artifact_version_id: "version-1",
  title: "Demo Mold Design Guide",
  original_filename: "guide.md",
  format: "md",
  sha256: "sha",
  document_type: "design_guideline",
  authority_level: "reviewed_demo",
  effective_from: null,
  effective_to: null,
  owner: "curator",
  classification: "public_demo",
  acl_scopes: ["public-demo"],
  language: "en",
  parser_version: "plain-text@1.0.0",
  chunker_version: "section-paragraph@1.0.0",
  ingestion_status: "indexed",
  injection_scan_status: "clear",
  injection_findings: [],
  chunk_count: 2,
  indexed_at: "2026-08-26T00:00:00Z",
  error_code: null,
  download_url: "/api/v1/artifact-versions/version-1/download",
  created_at: "2026-08-26T00:00:00Z",
};

describe("KnowledgeWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("retrieves extractive evidence with a protected versioned citation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }))
      .mockResolvedValueOnce(
        jsonResponse({
          search_id: "search-1",
          schema_version: "1.0",
          answer_mode: "extractive_evidence",
          answer: "Found 1 authorized source passages. Review the cited excerpts.",
          claims: [
            {
              text: "Rib thickness should be reviewed against nominal wall thickness.",
              evidence_refs: ["citation-1"],
              evidence_type: "document_excerpt",
            },
          ],
          citations: [
            {
              citation_id: "citation-1",
              artifact_version_id: "version-1",
              document_id: "document-1",
              title: "Demo Mold Design Guide",
              locator: "section:Rib Design,paragraphs:1-1",
              authority: "reviewed_demo",
              effective_from: null,
              effective_to: null,
              source_url: "/api/v1/artifact-versions/version-1/download",
            },
          ],
          results: [
            {
              rank: 1,
              chunk_id: "chunk-1",
              excerpt: "Rib thickness should be reviewed against nominal wall thickness.",
              score: 0.91,
              score_breakdown: { lexical: 1, vector: 0.9, authority: 0.9, freshness: 1 },
              citation_id: "citation-1",
            },
          ],
          abstained: false,
          retrieved_at: "2026-08-26T00:00:00Z",
          principal_scope_source: "server_demo_policy",
          limitations: ["No LLM synthesis."],
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(KnowledgeWorkspace);
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

  it("keeps retrieval disabled when no document is indexed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schema_version: "1.0", items: [] })),
    );

    const wrapper = mount(KnowledgeWorkspace);
    await flushPromises();

    expect(wrapper.text()).toContain("0 indexed");
    expect(wrapper.get(".knowledge-search-form button").attributes("disabled")).toBeDefined();
  });

  it("shows field guidance and does not upload an incomplete document", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }));
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(KnowledgeWorkspace);
    await flushPromises();
    await wrapper.get('.knowledge-upload-form input[type="text"]').setValue("x");
    await wrapper.get(".knowledge-upload-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Choose a TXT, Markdown, PDF or DOCX file");
    expect(wrapper.text()).toContain("Enter a title with at least 3 characters");
    expect(wrapper.text()).toContain("Required fields remaining: 2");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("accepts PDF and DOCX in the governed picker and shows a file summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schema_version: "1.0", items: [indexedDocument] })),
    );
    const wrapper = mount(KnowledgeWorkspace);
    await flushPromises();
    const input = wrapper.get('.knowledge-upload-form input[type="file"]');
    const pdf = new File(["demo"], "mold-guide.pdf", { type: "application/pdf" });
    Object.defineProperty(input.element, "files", { value: [pdf] });

    await input.trigger("change");

    expect(input.attributes("accept")).toContain(".pdf");
    expect(input.attributes("accept")).toContain(".docx");
    expect(wrapper.text()).toContain("mold-guide.pdf");
    expect(wrapper.text()).toContain("Ready for security screening");
    expect((wrapper.get('.knowledge-upload-form input[type="text"]').element as HTMLInputElement).value)
      .toBe("mold-guide");
  });

  it("rejects a Knowledge file over 5 MB before upload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ schema_version: "1.0", items: [indexedDocument] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(KnowledgeWorkspace);
    await flushPromises();
    const input = wrapper.get('.knowledge-upload-form input[type="file"]');
    const oversized = new File(["x"], "large.pdf", { type: "application/pdf" });
    Object.defineProperty(oversized, "size", { value: 5 * 1024 * 1024 + 1 });
    Object.defineProperty(input.element, "files", { value: [oversized] });

    await input.trigger("change");

    expect(wrapper.text()).toContain("5 MB");
    expect(wrapper.text()).not.toContain("Ready for security screening");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
