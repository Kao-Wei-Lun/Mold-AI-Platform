import type { AssistantContext, UIAction } from "./api/assistant";

const allowedActionTypes = new Set(["assistant.show_evidence"]);

export function validateUIAction(action: UIAction, context: AssistantContext): string | null {
  if (action.protocol_version !== "1.0") return "Unsupported UI Action protocol version.";
  if (!allowedActionTypes.has(action.type)) return "This UI Action is not allowed.";
  const expiresAt = Date.parse(action.expires_at);
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return "This UI Action has expired.";
  for (const precondition of action.preconditions) {
    if (precondition.type !== "page" || precondition.equals !== context.page) {
      return "The current page does not satisfy this UI Action.";
    }
  }
  if (action.type === "assistant.show_evidence") {
    if (
      action.target.search_id !== context.similarity_search_id ||
      action.target.candidate_artifact_version_id !==
        context.selected_candidate_artifact_version_id
    ) {
      return "The UI Action target no longer matches the selected result.";
    }
  }
  return null;
}
