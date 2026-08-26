import { apiFetch } from "./client";

export type AssistantContext = {
  context_version: "1.0";
  page:
    | "engineering_workspace"
    | "cad_processing"
    | "similarity_search"
    | "design_review"
    | "knowledge_search";
  query_artifact_version_id?: string;
  similarity_search_id?: string;
  selected_candidate_artifact_version_id?: string;
  job_id?: string;
  ui_locale: string;
};

export type UIAction = {
  protocol_version: "1.0";
  action_id: string;
  type: string;
  target: Record<string, string>;
  parameters: Record<string, unknown>;
  preconditions: Array<{ type: string; equals: string }>;
  requires_confirmation: boolean;
  expires_at: string;
  evidence_refs: string[];
};

export type ProviderStatus = {
  provider: string;
  mode: string;
  llm_available: boolean;
  status: "ok" | "degraded" | "unavailable";
  reason: string | null;
};

export type AssistantAnswer = {
  summary: string;
  facts: string[];
  interpretation: string[];
  recommendations: string[];
  uncertainties: string[];
  evidence_refs: string[];
};

export type AssistantResponse = {
  schema_version: "1.0";
  assistant_message_id: string;
  context: AssistantContext;
  provider: ProviderStatus;
  answer: AssistantAnswer;
  tool_calls: Array<{
    name: string;
    status: string;
    arguments: Record<string, string>;
    result_ref: string;
  }>;
  ui_actions: UIAction[];
};

export type AssistantCapabilities = {
  schema_version: "1.0";
  context_version: "1.0";
  ui_action_protocol_version: "1.0";
  provider: ProviderStatus;
  supported_intents: string[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: { message?: string; code?: string } };
    return payload.error?.message || payload.error?.code || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function fetchAssistantCapabilities(): Promise<AssistantCapabilities> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/assistant/capabilities`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as AssistantCapabilities;
}

export async function sendAssistantMessage(
  message: string,
  context: AssistantContext,
): Promise<AssistantResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/assistant/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ schema_version: "1.0", message, context }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as AssistantResponse;
}
