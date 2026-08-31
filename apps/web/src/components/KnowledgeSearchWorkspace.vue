<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  fetchKnowledgeDocuments,
  fetchKnowledgeSearch,
  searchKnowledge,
  type KnowledgeResultItem,
  type KnowledgeSearchResult,
} from "../api/knowledge";
import { downloadProtectedArtifact } from "../api/client";
import type { AssistantContext } from "../api/assistant";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";

const props = defineProps<{ deepLink?: DeepLinkContext | null }>();
const emit = defineEmits<{
  contextChange: [context: AssistantContext];
  navigate: [path: string];
}>();
const { locale, t } = useI18n();

const indexedCount = ref(0);
const query = ref("");
const searchType = ref("");
const searchAuthority = ref("");
const topK = ref(5);
const searching = ref(false);
const searchAttempted = ref(false);
const searchResult = ref<KnowledgeSearchResult | null>(null);
const selectedResult = ref<KnowledgeResultItem | null>(null);
const error = ref<string | null>(null);

const missingSearchFields = computed(() => Number(!query.value.trim()));
const queryError = computed(() =>
  searchAttempted.value && !query.value.trim() ? t("Enter an engineering question or terms.") : "",
);

async function loadAvailability(): Promise<void> {
  try {
    const documents = await fetchKnowledgeDocuments();
    indexedCount.value = documents.filter(
      (document) =>
        document.ingestion_status === "indexed" &&
        (document.publication_status || "published") === "published",
    ).length;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load knowledge documents.");
  }
}

async function submitSearch(): Promise<void> {
  searchAttempted.value = true;
  if (missingSearchFields.value) return;
  searching.value = true;
  error.value = null;
  searchResult.value = null;
  selectedResult.value = null;
  try {
    searchResult.value = await searchKnowledge(query.value, {
      documentTypes: searchType.value ? [searchType.value] : [],
      authorityLevels: searchAuthority.value ? [searchAuthority.value] : [],
      topK: topK.value,
    });
    selectedResult.value = searchResult.value.results[0] || null;
    searchAttempted.value = false;
    pushToast(t("Evidence search completed."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge search failed.");
    pushToast(error.value, "error");
  } finally {
    searching.value = false;
  }
}

async function useExample(example: string): Promise<void> {
  query.value = t(example);
  await submitSearch();
}

async function loadDeepLink(): Promise<void> {
  if (props.deepLink?.target !== "knowledge") return;
  error.value = null;
  try {
    searchResult.value = await fetchKnowledgeSearch(props.deepLink.refs.knowledge_search_id);
    const citationId = props.deepLink.refs.citation_id;
    selectedResult.value = citationId
      ? searchResult.value.results.find((item) => item.citation_id === citationId) || null
      : searchResult.value.results[0] || null;
    if (citationId && !selectedResult.value) {
      error.value = t("The linked citation does not belong to this knowledge search.");
    }
  } catch {
    error.value = t("The linked knowledge result is unavailable or not authorized.");
  }
}

function citationFor(item: KnowledgeResultItem) {
  return searchResult.value?.citations.find((citation) => citation.citation_id === item.citation_id);
}

async function downloadCitation(): Promise<void> {
  if (!selectedResult.value) return;
  const citation = citationFor(selectedResult.value);
  if (!citation) return;
  try {
    await downloadProtectedArtifact(citation.source_url, citation.title);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Source download failed.");
  }
}

onMounted(loadAvailability);
watch(
  () => [props.deepLink?.target, props.deepLink?.refs.knowledge_search_id, props.deepLink?.refs.citation_id],
  loadDeepLink,
  { immediate: true },
);
watch(
  () => [searchResult.value?.search_id, selectedResult.value?.citation_id],
  () => {
    if (!searchResult.value?.search_id) return;
    emit("contextChange", {
      context_version: "1.0",
      page: "knowledge_search",
      ui_locale: locale.value,
      knowledge_search_id: searchResult.value.search_id,
    });
  },
);
</script>

<template>
  <section class="knowledge-search-workspace" aria-labelledby="knowledge-search-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ t("Knowledge / RAG") }}</p>
        <h2 id="knowledge-search-title">{{ t("Search governed engineering knowledge") }}</h2>
        <p>{{ t("Ask an engineering question and inspect the authorized source evidence before using it.") }}</p>
      </div>
      <span class="demo-label">{{ t("Extractive · No LLM Synthesis") }}</span>
    </div>

    <article class="knowledge-query-card">
      <div class="subsection-heading">
        <div>
          <h3>{{ t("Engineering knowledge search") }}</h3>
          <span>{{ t("{count} published and indexed sources available", { count: indexedCount }) }}</span>
        </div>
      </div>
      <form class="knowledge-search-form" @submit.prevent="submitSearch">
        <FormField v-slot="{ fieldId, describedBy, invalid }" class="query-field" :label="t('Engineering question or terms')" required :error="queryError">
          <textarea
            :id="fieldId"
            v-model="query"
            rows="3"
            maxlength="500"
            :placeholder="t('What does the source say about rib thickness?')"
            required
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          ></textarea>
        </FormField>
        <details class="knowledge-search-filters">
          <summary>{{ t("Advanced filters") }}</summary>
          <div>
            <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Document type')">
              <select :id="fieldId" v-model="searchType" :aria-describedby="describedBy" :aria-invalid="invalid">
                <option value="">{{ t("Any") }}</option>
                <option value="demo_sop">{{ t("Demo SOP") }}</option>
                <option value="design_guideline">{{ t("Design guideline") }}</option>
                <option value="trial_report">{{ t("Trial report") }}</option>
                <option value="case_note">{{ t("Case note") }}</option>
              </select>
            </FormField>
            <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Authority')">
              <select :id="fieldId" v-model="searchAuthority" :aria-describedby="describedBy" :aria-invalid="invalid">
                <option value="">{{ t("Any") }}</option>
                <option value="demo">Demo</option>
                <option value="reviewed_demo">{{ t("Reviewed Demo") }}</option>
              </select>
            </FormField>
            <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Maximum results')" required :helper="t('Choose between 1 and 10 evidence results.')">
              <input :id="fieldId" v-model.number="topK" type="number" min="1" max="10" required :aria-describedby="describedBy" :aria-invalid="invalid" />
            </FormField>
          </div>
        </details>
        <p v-if="missingSearchFields" class="form-validation-summary" aria-live="polite">
          {{ t("Required fields remaining: {count}", { count: missingSearchFields }) }}
        </p>
        <button type="submit" class="knowledge-form-primary-action" :disabled="searching || indexedCount === 0" :aria-busy="searching">
          {{ searching ? t("Retrieving...") : t("Search authorized evidence") }}
        </button>
      </form>
      <div v-if="!searchResult" class="knowledge-query-examples">
        <span>{{ t("Try an example") }}</span>
        <button type="button" :disabled="indexedCount === 0" @click="useExample('What is the recommended rib thickness ratio?')">{{ t("What is the recommended rib thickness ratio?") }}</button>
        <button type="button" :disabled="indexedCount === 0" @click="useExample('How should draft angle be reviewed?')">{{ t("How should draft angle be reviewed?") }}</button>
      </div>
    </article>

    <section v-if="searchResult" class="knowledge-search-results" aria-live="polite">
      <div class="knowledge-answer" :class="{ abstained: searchResult.abstained }">
        <span>{{ searchResult.answer_mode.replaceAll("_", " ") }}</span>
        <strong>{{ searchResult.answer }}</strong>
      </div>
      <div class="knowledge-search-result-layout">
        <ol class="knowledge-result-list" :aria-label="t('Evidence results')">
          <li v-for="item in searchResult.results" :key="item.chunk_id">
            <button type="button" :class="{ selected: selectedResult?.chunk_id === item.chunk_id }" @click="selectedResult = item">
              <span>#{{ item.rank }}</span>
              <strong>{{ citationFor(item)?.title }}</strong>
              <small>{{ citationFor(item)?.locator }}</small>
            </button>
          </li>
        </ol>
        <article v-if="selectedResult" class="knowledge-evidence">
          <div class="evidence-score-row">
            <strong>{{ t("Evidence #{rank}", { rank: selectedResult.rank }) }}</strong>
            <span>{{ (selectedResult.score * 100).toFixed(1) }}%</span>
          </div>
          <blockquote>{{ selectedResult.excerpt }}</blockquote>
          <div class="knowledge-source-actions">
            <button v-if="citationFor(selectedResult)" type="button" class="citation-download" @click="downloadCitation">
              {{ t("Download source") }} · {{ citationFor(selectedResult)?.locator }}
            </button>
            <button v-if="citationFor(selectedResult)?.document_id" type="button" class="secondary-button" @click="emit('navigate', `/data/knowledge/${citationFor(selectedResult)?.document_id}`)">
              {{ t("View source document") }}
            </button>
          </div>
        </article>
      </div>
      <p class="limitation-note">{{ searchResult.limitations.join(" ") }}</p>
    </section>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
