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
import { useI18n } from "../i18n";

const { locale, t } = useI18n();

const props = defineProps<{ context: AssistantContext }>();
const emit = defineEmits<{ executeAction: [action: UIAction] }>();

const message = ref("");
const submitting = ref(false);
const contextCleared = ref(false);
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const response = ref<AssistantResponse | null>(null);
const provider = ref<ProviderStatus | null>(null);
const waitStopped = ref(false);
let requestController: AbortController | null = null;

const effectiveContext = computed<AssistantContext>(() =>
  contextCleared.value
    ? { context_version: "1.0", page: "engineering_workspace", ui_locale: locale.value }
    : { ...props.context, ui_locale: locale.value },
);
const contextReferences = computed(() =>
  Object.entries(effectiveContext.value).filter(([key]) => key.endsWith("_id")),
);
const providerLabel = computed(() => {
  if (provider.value?.mode === "openai" && provider.value.llm_available) {
    return response.value ? t("OpenAI generated") : t("OpenAI ready");
  }
  return t("safe fallback");
});
const providerNote = computed(() => {
  if (!provider.value || provider.value.llm_available) return null;
  const messages: Record<string, string> = {
    LLM_PROVIDER_DISABLED: "OpenAI generation is disabled for this deployment.",
    DETERMINISTIC_MODE: "This deployment is intentionally using deterministic explanations.",
    OPENAI_API_KEY_MISCONFIGURED: "The server-side OpenAI API key is missing or invalid.",
    OPENAI_MODEL_REQUIRED: "No approved OpenAI model is configured on the server.",
    OPENAI_RATE_LIMITED: "OpenAI rate-limited this request.",
    OPENAI_TIMEOUT: "OpenAI did not complete before the server timeout.",
    OPENAI_SERVER_ERROR: "OpenAI was temporarily unavailable.",
    PROVIDER_INTERNAL_ERROR: "The generation adapter failed safely.",
  };
  return t(messages[provider.value.reason || ""] || "A deterministic engineering answer was used.");
});

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
  waitStopped.value = false;
  error.value = null;
  actionError.value = null;
  const controller = new AbortController();
  requestController = controller;
  try {
    response.value = await sendAssistantMessage(
      normalized,
      effectiveContext.value,
      controller.signal,
    );
    provider.value = response.value.provider;
    message.value = "";
  } catch (caught) {
    if (!(caught instanceof DOMException && caught.name === "AbortError")) {
      error.value = caught instanceof Error ? caught.message : t("Assistant request failed.");
    }
  } finally {
    if (requestController === controller) {
      requestController = null;
      submitting.value = false;
    }
  }
}

function stopWaiting(): void {
  requestController?.abort();
  requestController = null;
  submitting.value = false;
  waitStopped.value = true;
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
        <p class="eyebrow">{{ t("Context-aware") }}</p>
        <h2 id="assistant-title">Mold AI Assistant</h2>
      </div>
      <span class="assistant-provider" :class="provider?.status || 'unavailable'">
        {{ providerLabel }}
      </span>
    </div>

    <p v-if="providerNote" class="provider-note">
      {{ providerNote }} {{ t("Deterministic engineering explanations remain available.") }}
    </p>

    <details class="assistant-context" open>
      <summary>{{ t("Current context") }}</summary>
      <div class="context-summary">
        <span>{{ t(effectiveContext.page.replaceAll("_", " ")) }}</span>
        <code v-for="[key, value] in contextReferences" :key="key">{{ key }}: {{ value }}</code>
        <small v-if="contextReferences.length === 0">{{ t("No selected engineering object.") }}</small>
      </div>
      <button class="context-clear" type="button" @click="clearContext">{{ t("Clear context") }}</button>
    </details>

    <div v-if="response" class="assistant-answer" aria-live="polite">
      <p>{{ response.answer.summary }}</p>
      <details v-if="response.answer.facts.length">
        <summary>{{ t("Facts and computed evidence") }}</summary>
        <ul><li v-for="fact in response.answer.facts" :key="fact">{{ fact }}</li></ul>
      </details>
      <details v-if="response.answer.interpretation.length">
        <summary>{{ t("Interpretation") }}</summary>
        <ul><li v-for="item in response.answer.interpretation" :key="item">{{ item }}</li></ul>
      </details>
      <details v-if="response.answer.recommendations.length">
        <summary>{{ t("Recommendations") }}</summary>
        <ul>
          <li v-for="item in response.answer.recommendations" :key="item">{{ item }}</li>
        </ul>
      </details>
      <details v-if="response.answer.uncertainties.length">
        <summary>{{ t("Uncertainty and limitations") }}</summary>
        <ul><li v-for="item in response.answer.uncertainties" :key="item">{{ item }}</li></ul>
      </details>
      <button
        v-for="action in response.ui_actions"
        :key="action.action_id"
        type="button"
        class="assistant-action"
        @click="execute(action)"
      >
        {{ t("Show evidence in workspace") }}
      </button>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="actionError" class="error-message" role="alert">{{ actionError }}</p>
    <p v-if="waitStopped" class="provider-note" role="status">
      {{ t("You stopped waiting. This does not prove the server-side provider request was cancelled and may not prevent API usage.") }}
    </p>

    <form class="assistant-form" :aria-busy="submitting" @submit.prevent="submit">
      <label for="assistant-message">{{ t("Ask about the selected engineering result") }}</label>
      <textarea
        id="assistant-message"
        v-model="message"
        maxlength="2000"
        rows="4"
        :placeholder="t('Why is this ranked first?')"
      ></textarea>
      <button type="submit" :disabled="submitting || !message.trim()">
        {{ submitting ? t("Analyzing...") : t("Ask Assistant") }}
      </button>
      <button v-if="submitting" type="button" class="context-clear assistant-stop" @click="stopWaiting">
        {{ t("Stop waiting") }}
      </button>
    </form>
  </aside>
</template>
