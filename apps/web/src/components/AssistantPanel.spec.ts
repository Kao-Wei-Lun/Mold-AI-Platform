import { flushPromises, mount } from "@vue/test-utils";

import type { AssistantContext } from "../api/assistant";
import AssistantPanel from "./AssistantPanel.vue";

const context: AssistantContext = {
  context_version: "1.0",
  page: "similarity_search",
  query_artifact_version_id: "d49ea0ae-7403-4a62-a608-d3285c39359d",
  similarity_search_id: "db045b8d-4298-486d-ab20-8b4f3d7088ad",
  selected_candidate_artifact_version_id: "c4fef76c-2b1b-4590-97b0-260972486fb8",
  job_id: "e1b632ac-8cb5-4a29-a737-c260def136e4",
  ui_locale: "zh-TW",
};

function jsonResponse(payload: object): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

describe("AssistantPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends minimal UI references and renders a grounded fallback answer", async () => {
    const action = {
      protocol_version: "1.0",
      action_id: "action-1",
      type: "assistant.show_evidence",
      target: {
        search_id: context.similarity_search_id,
        candidate_artifact_version_id: context.selected_candidate_artifact_version_id,
      },
      parameters: {},
      preconditions: [{ type: "page", equals: "similarity_search" }],
      requires_confirmation: false,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      evidence_refs: ["feature:a:geometry"],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          context_version: "1.0",
          ui_action_protocol_version: "1.0",
          provider: {
            provider: "deterministic-demo",
            mode: "deterministic_fallback",
            llm_available: false,
            status: "degraded",
            reason: "LLM_PROVIDER_DISABLED",
          },
          supported_intents: ["explain_similarity"],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          assistant_message_id: "message-1",
          context,
          provider: {
            provider: "deterministic-demo",
            mode: "deterministic_fallback",
            llm_available: false,
            status: "degraded",
            reason: "LLM_PROVIDER_DISABLED",
          },
          answer: {
            summary: "Reference A ranked #1 with an overall similarity score of 92.8%.",
            facts: ["geometry: 96.2%"],
            interpretation: [],
            recommendations: ["Review the geometric differences."],
            uncertainties: ["Visual embedding is not included."],
            evidence_refs: ["feature:a:geometry"],
          },
          tool_calls: [
            {
              name: "get_similarity_explanation",
              status: "succeeded",
              arguments: {},
              result_ref: "similarity-search:search-1",
            },
          ],
          ui_actions: [action],
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(AssistantPanel, { props: { context } });
    await flushPromises();

    await wrapper.get("textarea").setValue("為什麼這個排第一？");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    const request = fetchMock.mock.calls[1][1] as RequestInit;
    const body = JSON.parse(String(request.body));
    expect(body.context).toEqual(context);
    expect(request.signal).toBeInstanceOf(AbortSignal);
    expect(wrapper.text()).toContain("92.8%");
    expect(wrapper.text()).toContain("safe fallback");

    await wrapper.get(".assistant-action").trigger("click");
    expect(wrapper.emitted("executeAction")?.[0]).toEqual([action]);
  });

  it("clears object references without mutating the parent context", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          provider: {
            provider: "deterministic-demo",
            mode: "deterministic_fallback",
            llm_available: false,
            status: "degraded",
            reason: "LLM_PROVIDER_DISABLED",
          },
        }),
      ),
    );
    const wrapper = mount(AssistantPanel, { props: { context } });
    await flushPromises();

    expect(wrapper.text()).toContain(context.similarity_search_id!);
    await wrapper.get(".context-clear").trigger("click");

    expect(wrapper.text()).toContain("No selected engineering object");
    expect(wrapper.props("context")).toEqual(context);
  });

  it("shows OpenAI generation separately from a deterministic fallback", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          provider: {
            provider: "openai-responses",
            mode: "openai",
            llm_available: true,
            status: "ok",
            reason: null,
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          assistant_message_id: "message-openai",
          context,
          provider: {
            provider: "openai-responses",
            mode: "openai",
            llm_available: true,
            status: "ok",
            reason: null,
            model: "configured-at-runtime",
          },
          answer: {
            summary: "Grounded generated explanation.",
            facts: ["The persisted score is 92.8%."],
            interpretation: ["The available feature lanes support the ranking."],
            recommendations: [],
            uncertainties: ["Engineer review is required."],
            evidence_refs: ["similarity-search:demo"],
          },
          tool_calls: [],
          ui_actions: [],
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(AssistantPanel, { props: { context } });
    await flushPromises();

    expect(wrapper.text()).toContain("OpenAI ready");
    await wrapper.get("textarea").setValue("Explain this result");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("OpenAI generated");
    expect(wrapper.text()).toContain("The available feature lanes support the ranking.");
  });

  it("stops waiting without claiming the server request was cancelled", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          provider: {
            provider: "openai-responses",
            mode: "openai",
            llm_available: true,
            status: "ok",
            reason: null,
          },
        }),
      )
      .mockImplementationOnce((_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(AssistantPanel, { props: { context } });
    await flushPromises();

    await wrapper.get("textarea").setValue("Explain this result");
    await wrapper.get("form").trigger("submit");
    await wrapper.get(".assistant-stop").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("does not prove the server-side provider request was cancelled");
    expect(wrapper.find(".assistant-stop").exists()).toBe(false);
  });
});
