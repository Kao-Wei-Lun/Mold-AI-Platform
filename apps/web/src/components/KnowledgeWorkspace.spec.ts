import { flushPromises, mount } from "@vue/test-utils";

import type { LocalAccount } from "../api/identity";
import type { KnowledgeDocument } from "../api/knowledge";
import KnowledgeWorkspace from "./KnowledgeWorkspace.vue";

function jsonResponse(payload: object, status = 200): Response {
  return { ok: status < 400, status, json: async () => payload } as Response;
}

const account: LocalAccount = {
  id: "account-1", username: "knowledge-owner", email: "owner@example.com",
  display_name: "Knowledge Owner", status: "active", locale: "en", timezone: "Asia/Taipei",
  row_version: 1, roles: ["knowledge_owner"], permissions: ["knowledge:author", "knowledge:approve"],
  data_scopes: ["public-demo"], role_assignments: [], last_login_at: null,
  created_at: "2026-08-26T00:00:00Z",
};

const indexedDocument: KnowledgeDocument = {
  document_id: "document-1", document_key: "demo-mold-design-guide", version_number: 1,
  supersedes_document_id: null, artifact_id: "artifact-1", artifact_version_id: "version-1",
  title: "Demo Mold Design Guide", original_filename: "guide.md", format: "md", sha256: "sha",
  document_type: "design_guideline", authority_level: "reviewed_demo", effective_from: null,
  effective_to: null, owner: "curator", classification: "public_demo", acl_scopes: ["public-demo"],
  language: "en", parser_version: "plain-text@1.0.0", chunker_version: "section-paragraph@1.0.0",
  ingestion_status: "indexed", injection_scan_status: "clear", injection_findings: [], chunk_count: 2,
  indexed_at: "2026-08-26T00:00:00Z", error_code: null, publication_status: "published", row_version: 1,
  submitted_by: "curator", reviewed_by: "reviewer", approved_by: "approver",
  published_at: "2026-08-26T00:00:00Z", retired_at: null,
  download_url: "/api/v1/artifact-versions/version-1/download", created_at: "2026-08-26T00:00:00Z",
};

function mountImport() {
  return mount(KnowledgeWorkspace, {
    props: { path: "/governance/knowledge?view=import", currentAccount: account },
  });
}

describe("KnowledgeWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows document management separately from the import form", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      jsonResponse({ schema_version: "1.0", items: [indexedDocument] }),
    ));
    const wrapper = mount(KnowledgeWorkspace, {
      props: { path: "/governance/knowledge", currentAccount: account },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Demo Mold Design Guide");
    expect(wrapper.find(".knowledge-upload-form").exists()).toBe(false);
    await wrapper.get(".knowledge-heading-actions button:last-child").trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/governance/knowledge?view=import"]);
  });

  it("shows field guidance and does not upload an incomplete document", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ schema_version: "1.0", items: [indexedDocument] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mountImport();
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
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      jsonResponse({ schema_version: "1.0", items: [indexedDocument] }),
    ));
    const wrapper = mountImport();
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
    const wrapper = mountImport();
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

  it("clears only file-related fields after ingestion is accepted", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }))
      .mockResolvedValueOnce(jsonResponse({
        status: "accepted", artifact_id: "artifact-2", artifact_version_id: "version-2",
        document_id: "document-2", job_id: "job-2", idempotent_replay: false,
      }, 202))
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "1.0", job_id: "job-2", capability: "knowledge.ingest@1.0.0",
        state: "queued", stage: "queued", progress: 0, attempt: 1,
        artifact_version_id: "version-2", correlation_id: "correlation-2", result: null, error: null,
      }));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mountImport();
    await flushPromises();
    const input = wrapper.get('.knowledge-upload-form input[type="file"]');
    const file = new File(["guide"], "repeatable-guide.md", { type: "text/markdown" });
    Object.defineProperty(input.element, "files", { value: [file] });
    await input.trigger("change");
    await wrapper.get(".knowledge-upload-form").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".file-drop-zone .selected-file-summary").exists()).toBe(false);
    expect((wrapper.get('.knowledge-upload-form input[type="text"]').element as HTMLInputElement).value).toBe("");
    const selects = wrapper.findAll(".knowledge-upload-form select");
    expect((selects[0].element as HTMLSelectElement).value).toBe("design_guideline");
    expect((selects[1].element as HTMLSelectElement).value).toBe("demo");
    expect((selects[2].element as HTMLSelectElement).value).toBe("en");
  });

  it("requests a contextual audit reason only after a lifecycle action is chosen", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [indexedDocument] }))
      .mockResolvedValueOnce(jsonResponse({ ...indexedDocument, publication_status: "retired" }))
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(KnowledgeWorkspace, {
      props: { path: "/governance/knowledge", currentAccount: account },
    });
    await flushPromises();

    expect(wrapper.find(".workflow-dialog").exists()).toBe(false);
    expect(wrapper.find('textarea[required]').exists()).toBe(false);
    await wrapper.get(".danger-text").trigger("click");
    expect(wrapper.get(".workflow-dialog").text()).toContain("Retiring removes this version");
    const confirm = wrapper.get(".workflow-dialog-actions button:last-child");
    expect(confirm.attributes("disabled")).toBeDefined();
    await wrapper.get(".workflow-dialog textarea").setValue("Superseded by the approved 2026 standard.");
    await confirm.trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenNthCalledWith(
      2, "/api/v1/knowledge-documents/document-1/actions", expect.objectContaining({ method: "POST" }),
    );
    expect(wrapper.find(".workflow-dialog").exists()).toBe(false);
  });
});
