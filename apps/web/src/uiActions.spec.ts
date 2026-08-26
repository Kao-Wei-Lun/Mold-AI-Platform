import type { AssistantContext, UIAction } from "./api/assistant";
import { validateUIAction } from "./uiActions";

const context: AssistantContext = {
  context_version: "1.0",
  page: "similarity_search",
  similarity_search_id: "search-1",
  selected_candidate_artifact_version_id: "candidate-1",
  ui_locale: "zh-TW",
};

function action(overrides: Partial<UIAction> = {}): UIAction {
  return {
    protocol_version: "1.0",
    action_id: "action-1",
    type: "assistant.show_evidence",
    target: { search_id: "search-1", candidate_artifact_version_id: "candidate-1" },
    parameters: {},
    preconditions: [{ type: "page", equals: "similarity_search" }],
    requires_confirmation: false,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    evidence_refs: [],
    ...overrides,
  };
}

describe("validateUIAction", () => {
  it("accepts an allowlisted action that still matches current context", () => {
    expect(validateUIAction(action(), context)).toBeNull();
  });

  it("rejects expired, mismatched, and non-allowlisted actions", () => {
    expect(
      validateUIAction(action({ expires_at: new Date(Date.now() - 1000).toISOString() }), context),
    ).toContain("expired");
    expect(validateUIAction(action({ target: { search_id: "other" } }), context)).toContain(
      "no longer matches",
    );
    expect(validateUIAction(action({ type: "navigation.open_url" }), context)).toContain(
      "not allowed",
    );
  });
});
