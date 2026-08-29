import { flushPromises, mount } from "@vue/test-utils";

import { setLocale } from "../i18n";
import GovernanceHistoryWorkspace from "./GovernanceHistoryWorkspace.vue";

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

const ruleProfile = {
  profile_id: "profile-1", profile_key: "demo-rules", version: "2.0", status: "draft", workflow_status: "draft", change_summary: "Next rules", row_version: 1, owner: "owner", submitted_by: null, reviewed_by: null, approved_by: "", published_at: null, retired_at: null, ruleset_checksum: "abcdef", rule_count: 1,
  rules: [{ rule_version_id: "rule-version-1", rule_id: "draft_angle", rule_version: "2.0", title: "Draft angle", description: "Minimum draft", evaluator: "minimum_draft_angle", applicability: {}, measurement_definition: {}, condition: { operator: "gte", limit: 1, unit: "deg", tolerance: 0 }, severity: "high", risk_type: "release", recommendation: "Increase draft", reference: { document: "Demo", revision: "1", classification: "public_demo" }, enabled: true }],
};

describe("GovernanceHistoryWorkspace", () => {
  beforeEach(() => setLocale("en"));
  afterEach(() => vi.restoreAllMocks());

  it("renders a rule draft with versioned editing and diff tabs", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/diff")) return response({ schema_version: "1.0", baseline_profile_id: "profile-0", profile_id: "profile-1", changes: [{ rule_id: "draft_angle", change: "modified", changed_fields: ["limit_value"] }] });
      if (url.endsWith("/profile-1")) return response(ruleProfile);
      return response({ schema_version: "1.0", items: [ruleProfile, { ...ruleProfile, profile_id: "profile-0", version: "1.0", workflow_status: "published" }] });
    }));
    const wrapper = mount(GovernanceHistoryWorkspace, { props: { domain: "rules", path: "/data/rules/profile-1?tab=rules", currentAccount: { permissions: ["rules:author"] } as never } });
    await flushPromises();
    expect(wrapper.text()).toContain("Draft angle");
    expect(wrapper.text()).toContain("Edit rule draft JSON");
    await wrapper.setProps({ path: "/data/rules/profile-1?tab=diff&against=profile-0" });
    await flushPromises();
    expect(wrapper.text()).toContain("limit_value");
  });

  it("renders knowledge chunks, versions and citation evidence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      document_id: "doc-1", document_key: "guide", version_number: 2, supersedes_document_id: "doc-0", artifact_id: "artifact-1", artifact_version_id: "version-1", title: "Mold guide", original_filename: "guide.md", format: "md", sha256: "abc", document_type: "design_guideline", authority_level: "reviewed_demo", effective_from: null, effective_to: null, owner: "curator", classification: "public_demo", acl_scopes: ["public-demo"], language: "en", parser_version: "plain@1", chunker_version: "chunks@1", ingestion_status: "indexed", injection_scan_status: "clear", injection_findings: [], chunk_count: 1, indexed_at: "2026-08-29T00:00:00Z", error_code: null, publication_status: "published", row_version: 4, submitted_by: "curator", reviewed_by: "reviewer", approved_by: "approver", published_at: "2026-08-29T00:00:00Z", retired_at: null, download_url: "/download", created_at: "2026-08-29T00:00:00Z",
      versions: [], chunks: [{ chunk_id: "chunk-1", ordinal: 1, text: "Rib thickness evidence", text_hash: "hash", locator: { section: "Ribs" }, language: "en", embedding_model: "hash@1", index_status: "indexed", injection_scan_status: "clear" }], citations: [{ citation_id: "citation-1", artifact_version_id: "version-1", document_id: "doc-1", title: "Mold guide", locator: "Ribs", authority: "reviewed_demo", effective_from: null, effective_to: null, source_url: "/download", search_id: "search-1", search_created_at: "2026-08-29T01:00:00Z" }],
    })));
    const wrapper = mount(GovernanceHistoryWorkspace, { props: { domain: "knowledge", path: "/data/knowledge/doc-1?tab=chunks" } });
    await flushPromises();
    expect(wrapper.text()).toContain("Rib thickness evidence");
    await wrapper.setProps({ path: "/data/knowledge/doc-1?tab=citations" });
    await flushPromises();
    expect(wrapper.text()).toContain("search-1");
  });
});
