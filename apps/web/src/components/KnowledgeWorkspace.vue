<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
  fetchKnowledgeDocuments,
  fetchKnowledgeJob,
  fetchKnowledgeSearch,
  searchKnowledge,
  uploadKnowledge,
  type KnowledgeDocument,
  type KnowledgeJob,
  type KnowledgeResultItem,
  type KnowledgeSearchResult,
} from "../api/knowledge";
import { downloadProtectedArtifact } from "../api/client";
import type { AssistantContext } from "../api/assistant";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";

const { locale, t } = useI18n();

const props = defineProps<{ deepLink?: DeepLinkContext | null }>();
const emit = defineEmits<{ contextChange: [context: AssistantContext] }>();

const file = ref<File | null>(null);
const title = ref("");
const documentType = ref("design_guideline");
const authorityLevel = ref("demo");
const language = ref("en");
const documents = ref<KnowledgeDocument[]>([]);
const job = ref<KnowledgeJob | null>(null);
const uploading = ref(false);
const loadingDocuments = ref(false);
const query = ref("");
const searchType = ref("");
const searchAuthority = ref("");
const topK = ref(5);
const searching = ref(false);
const searchResult = ref<KnowledgeSearchResult | null>(null);
const selectedResult = ref<KnowledgeResultItem | null>(null);
const error = ref<string | null>(null);
let pollTimer: number | null = null;

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const indexedCount = computed(
  () => documents.value.filter((document) => document.ingestion_status === "indexed").length,
);

function onFile(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] || null;
  if (file.value && !title.value) title.value = file.value.name.replace(/\.(md|txt)$/i, "");
}

async function loadDocuments(): Promise<void> {
  loadingDocuments.value = true;
  try {
    documents.value = await fetchKnowledgeDocuments();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load knowledge documents.");
  } finally {
    loadingDocuments.value = false;
  }
}

function schedulePoll(): void {
  if (!terminal.value) pollTimer = window.setTimeout(refreshJob, 900);
}

async function refreshJob(): Promise<void> {
  if (!job.value) return;
  try {
    job.value = await fetchKnowledgeJob(job.value.job_id);
    if (job.value.state === "succeeded" || job.value.state === "failed") await loadDocuments();
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh ingestion job.");
  }
}

async function submitUpload(): Promise<void> {
  if (!file.value) {
    error.value = t("Choose a UTF-8 TXT or Markdown file first.");
    return;
  }
  uploading.value = true;
  error.value = null;
  job.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    const accepted = await uploadKnowledge(file.value, {
      title: title.value,
      documentType: documentType.value,
      authorityLevel: authorityLevel.value,
      language: language.value,
    });
    job.value = await fetchKnowledgeJob(accepted.job_id);
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge upload failed.");
  } finally {
    uploading.value = false;
  }
}

async function submitSearch(): Promise<void> {
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
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge search failed.");
  } finally {
    searching.value = false;
  }
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

onMounted(loadDocuments);
watch(
  () => [
    props.deepLink?.target,
    props.deepLink?.refs.knowledge_search_id,
    props.deepLink?.refs.citation_id,
  ],
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
      ...(searchResult.value?.search_id
        ? { knowledge_search_id: searchResult.value.search_id }
        : {}),
    });
  },
);
onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section id="knowledge" class="knowledge-workspace" aria-labelledby="knowledge-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Knowledge / RAG</p>
        <h2 id="knowledge-title">{{ t("Retrieve governed source evidence") }}</h2>
      </div>
      <span class="demo-label">{{ t("Extractive · No LLM Synthesis") }}</span>
    </div>

    <div class="knowledge-layout">
      <article class="knowledge-ingestion">
        <div class="subsection-heading">
          <div>
            <h3>{{ t("Document ingestion") }}</h3>
            <span>{{ t("{count} indexed · Public Demo ACL", { count: indexedCount }) }}</span>
          </div>
          <button type="button" class="secondary-button" :disabled="loadingDocuments" @click="loadDocuments">
            {{ t("Refresh") }}
          </button>
        </div>
        <form class="knowledge-upload-form" @submit.prevent="submitUpload">
          <label class="file-field">
            <span>{{ t("UTF-8 TXT or Markdown") }}</span>
            <input type="file" accept=".txt,.md,text/plain,text/markdown" @change="onFile" />
          </label>
          <label>
            <span>{{ t("Title") }}</span>
            <input v-model="title" type="text" maxlength="255" :placeholder="t('Demo molding SOP')" />
          </label>
          <label>
            <span>{{ t("Document type") }}</span>
            <select v-model="documentType">
              <option value="demo_sop">{{ t("Demo SOP") }}</option>
              <option value="design_guideline">{{ t("Design guideline") }}</option>
              <option value="trial_report">{{ t("Trial report") }}</option>
              <option value="case_note">{{ t("Case note") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("Authority") }}</span>
            <select v-model="authorityLevel">
              <option value="demo">Demo</option>
              <option value="reviewed_demo">{{ t("Reviewed Demo") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("Language") }}</span>
            <select v-model="language">
              <option value="en">{{ t("English") }}</option>
              <option value="zh-Hant">{{ t("Traditional Chinese") }}</option>
            </select>
          </label>
          <button type="submit" :disabled="uploading">
            {{ uploading ? t("Uploading...") : t("Ingest document") }}
          </button>
        </form>

        <div v-if="job" class="job-panel compact-job">
          <div class="job-heading">
            <div>
              <span class="job-state" :class="job.state">{{ t(job.state) }}</span>
              <strong>{{ t(job.stage.replaceAll("_", " ")) }}</strong>
            </div>
            <span>{{ job.progress }}%</span>
          </div>
          <div class="progress-track" :aria-label="t('Knowledge ingestion progress')">
            <span :style="{ width: `${job.progress}%` }"></span>
          </div>
        </div>

        <ul class="document-list" :aria-label="t('Knowledge documents')">
          <li v-for="document in documents.slice(0, 8)" :key="document.document_id">
            <div>
              <strong>{{ document.title }}</strong>
              <span>{{ t(document.document_type.replaceAll("_", " ")) }} · {{ t("{count} chunks", { count: document.chunk_count }) }}</span>
            </div>
            <span class="document-status" :class="document.ingestion_status">
              {{ t(document.ingestion_status) }}
            </span>
          </li>
        </ul>
      </article>

      <article class="knowledge-search">
        <h3>{{ t("Evidence search") }}</h3>
        <form class="knowledge-search-form" @submit.prevent="submitSearch">
          <label class="query-field">
            <span>{{ t("Engineering question or terms") }}</span>
            <textarea
              v-model="query"
              rows="3"
              maxlength="500"
              :placeholder="t('What does the source say about rib thickness?')"
              required
            ></textarea>
          </label>
          <label>
            <span>{{ t("Document type") }}</span>
            <select v-model="searchType">
              <option value="">{{ t("Any") }}</option>
              <option value="demo_sop">{{ t("Demo SOP") }}</option>
              <option value="design_guideline">{{ t("Design guideline") }}</option>
              <option value="trial_report">{{ t("Trial report") }}</option>
              <option value="case_note">{{ t("Case note") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("Authority") }}</span>
            <select v-model="searchAuthority">
              <option value="">{{ t("Any") }}</option>
              <option value="demo">Demo</option>
              <option value="reviewed_demo">{{ t("Reviewed Demo") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("Top K") }}</span>
            <input v-model.number="topK" type="number" min="1" max="10" />
          </label>
          <button type="submit" :disabled="searching || indexedCount === 0">
            {{ searching ? t("Retrieving...") : t("Search authorized evidence") }}
          </button>
        </form>

        <template v-if="searchResult">
          <div class="knowledge-answer" :class="{ abstained: searchResult.abstained }">
            <span>{{ searchResult.answer_mode.replaceAll("_", " ") }}</span>
            <strong>{{ searchResult.answer }}</strong>
          </div>
          <div v-if="selectedResult" class="knowledge-evidence">
            <div class="evidence-score-row">
              <strong>{{ t("Evidence #{rank}", { rank: selectedResult.rank }) }}</strong>
              <span>{{ (selectedResult.score * 100).toFixed(1) }}%</span>
            </div>
            <blockquote>{{ selectedResult.excerpt }}</blockquote>
            <button
              v-if="citationFor(selectedResult)"
              type="button"
              class="citation-download"
              @click="downloadCitation"
            >
              {{ citationFor(selectedResult)?.title }} · {{ citationFor(selectedResult)?.locator }}
            </button>
          </div>
          <ol class="knowledge-result-list">
            <li v-for="item in searchResult.results" :key="item.chunk_id">
              <button
                type="button"
                :class="{ selected: selectedResult?.chunk_id === item.chunk_id }"
                @click="selectedResult = item"
              >
                <span>#{{ item.rank }}</span>
                <strong>{{ citationFor(item)?.title }}</strong>
                <small>{{ citationFor(item)?.locator }}</small>
              </button>
            </li>
          </ol>
          <p class="limitation-note">{{ searchResult.limitations.join(" ") }}</p>
        </template>
      </article>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
