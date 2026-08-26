<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  fetchAssistantCapabilities,
  sendAssistantMessage,
  type AssistantContext,
  type AssistantResponse,
  type ProviderStatus,
  type UIAction,
} from "../api/assistant";
import { validateUIAction } from "../uiActions";

const props = defineProps<{ context: AssistantContext }>();
const emit = defineEmits<{ executeAction: [action: UIAction] }>();

const message = ref("");
const submitting = ref(false);
const contextCleared = ref(false);
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const response = ref<AssistantResponse | null>(null);
const provider = ref<ProviderStatus | null>(null);

const effectiveContext = computed<AssistantContext>(() =>
  contextCleared.value
    ? { context_version: "1.0", page: "engineering_workspace", ui_locale: "zh-TW" }
    : props.context,
);
const contextReferences = computed(() =>
  Object.entries(effectiveContext.value).filter(([key]) => key.endsWith("_id")),
);

async function loadCapabilities(): Promise<void> {
  try {
    const capabilities = await fetchAssistantCapabilities();
    if (capabilities.provider) provider.value = capabilities.provider;
  } catch {
    provider.value = {
      provider: "unknown",
      mode: "unavailable",
      llm_available: false,
      status: "unavailable",
      reason: "ASSISTANT_API_UNAVAILABLE",
    };
  }
}

async function submit(): Promise<void> {
  const normalized = message.value.trim();
  if (!normalized) return;
  submitting.value = true;
  error.value = null;
  actionError.value = null;
  try {
    response.value = await sendAssistantMessage(normalized, effectiveContext.value);
    provider.value = response.value.provider;
    message.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Assistant request failed.";
  } finally {
    submitting.value = false;
  }
}

function execute(action: UIAction): void {
  actionError.value = validateUIAction(action, effectiveContext.value);
  if (!actionError.value) emit("executeAction", action);
}

function clearContext(): void {
  contextCleared.value = true;
  response.value = null;
  actionError.value = null;
}

watch(
  () => props.context,
  () => {
    contextCleared.value = false;
    actionError.value = null;
  },
  { deep: true },
);

onMounted(loadCapabilities);
</script>

<template>
  <aside class="assistant-panel" aria-labelledby="assistant-title">
    <div class="assistant-heading">
      <div>
        <p class="eyebrow">Context-aware</p>
        <h2 id="assistant-title">Mold AI Assistant</h2>
      </div>
      <span class="assistant-provider" :class="provider?.status || 'unavailable'">
        {{ provider?.llm_available ? "LLM ready" : "safe fallback" }}
      </span>
    </div>

    <p v-if="provider && !provider.llm_available" class="provider-note">
      LLM unavailable: deterministic engineering explanations remain available.
    </p>

    <details class="assistant-context" open>
      <summary>Current context</summary>
      <div class="context-summary">
        <span>{{ effectiveContext.page.replaceAll("_", " ") }}</span>
        <code v-for="[key, value] in contextReferences" :key="key">{{ key }}: {{ value }}</code>
        <small v-if="contextReferences.length === 0">No selected engineering object.</small>
      </div>
      <button class="context-clear" type="button" @click="clearContext">Clear context</button>
    </details>

    <div v-if="response" class="assistant-answer" aria-live="polite">
      <p>{{ response.answer.summary }}</p>
      <details v-if="response.answer.facts.length">
        <summary>Facts and computed evidence</summary>
        <ul><li v-for="fact in response.answer.facts" :key="fact">{{ fact }}</li></ul>
      </details>
      <details v-if="response.answer.recommendations.length">
        <summary>Recommendations</summary>
        <ul>
          <li v-for="item in response.answer.recommendations" :key="item">{{ item }}</li>
        </ul>
      </details>
      <details v-if="response.answer.uncertainties.length">
        <summary>Uncertainty and limitations</summary>
        <ul><li v-for="item in response.answer.uncertainties" :key="item">{{ item }}</li></ul>
      </details>
      <button
        v-for="action in response.ui_actions"
        :key="action.action_id"
        type="button"
        class="assistant-action"
        @click="execute(action)"
      >
        Show evidence in workspace
      </button>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="actionError" class="error-message" role="alert">{{ actionError }}</p>

    <form class="assistant-form" @submit.prevent="submit">
      <label for="assistant-message">Ask about the selected engineering result</label>
      <textarea
        id="assistant-message"
        v-model="message"
        maxlength="2000"
        rows="4"
        placeholder="為什麼這個排第一？"
      ></textarea>
      <button type="submit" :disabled="submitting || !message.trim()">
        {{ submitting ? "Analyzing..." : "Ask Assistant" }}
      </button>
    </form>
  </aside>
</template>
