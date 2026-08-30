<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
  fetchKnowledgeDocuments,
  fetchKnowledgeJob,
  fetchKnowledgeSearch,
  searchKnowledge,
  transitionKnowledgeDocument,
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
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import type { LocalAccount } from "../api/identity";
import { formatFileSize, uploadPolicies, validateUploadFile } from "../fileUpload";

const { locale, t } = useI18n();

const props = defineProps<{ deepLink?: DeepLinkContext | null; currentAccount?: LocalAccount | null }>();
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
const uploadAttempted = ref(false);
const fileSelectionError = ref("");
const searchAttempted = ref(false);
const workflowReason = ref("Controlled knowledge lifecycle change");
const workflowBusyId = ref("");
let pollTimer: number | null = null;

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const indexedCount = computed(
  () => documents.value.filter((document) => document.ingestion_status === "indexed" && (document.publication_status || "published") === "published").length,
);
const canAuthor = computed(() => props.currentAccount?.permissions.includes("knowledge:author") || false);
const canApprove = computed(() => props.currentAccount?.permissions.includes("knowledge:approve") || false);
const missingUploadFields = computed(
  () => Number(!file.value) + Number(title.value.trim().length < 3),
);
const missingSearchFields = computed(() => Number(!query.value.trim()));
const fileError = computed(() =>
  fileSelectionError.value || (uploadAttempted.value && !file.value
    ? t("Choose a TXT, Markdown, PDF or DOCX file.")
    : ""),
);
const titleError = computed(() =>
  uploadAttempted.value && title.value.trim().length < 3
    ? t("Enter a title with at least 3 characters.")
    : "",
);
const queryError = computed(() =>
  searchAttempted.value && !query.value.trim() ? t("Enter an engineering question or terms.") : "",
);

function onFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  const candidate = input.files?.[0] || null;
  fileSelectionError.value = "";
  if (!candidate) {
    file.value = null;
    return;
  }
  const validation = validateUploadFile(candidate, uploadPolicies.knowledge);
  if (validation) {
    file.value = null;
    input.value = "";
    fileSelectionError.value = validation === "too_large"
      ? t("File size exceeds the {limit} MB limit.", { limit: 5 })
      : t("File type is not supported. Allowed: {formats}.", { formats: "TXT, MD, PDF, DOCX" });
    return;
  }
  file.value = candidate;
  if (!title.value) title.value = candidate.name.replace(/\.(md|txt|pdf|docx)$/i, "");
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
  uploadAttempted.value = true;
  if (missingUploadFields.value || !file.value) return;
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
    uploadAttempted.value = false;
    schedulePoll();
    pushToast(t("Document ingestion started."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge upload failed.");
    pushToast(error.value, "error");
  } finally {
    uploading.value = false;
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

async function transitionDocument(
  document: KnowledgeDocument,
  action: "submit" | "approve" | "publish" | "retire",
): Promise<void> {
  if (!workflowReason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  if (!window.confirm(t("Confirm {action} for {title}?", { action: t(action), title: document.title }))) return;
  workflowBusyId.value = document.document_id;
  error.value = null;
  try {
    await transitionKnowledgeDocument(document, action, workflowReason.value);
    await loadDocuments();
    pushToast(t("Knowledge lifecycle updated."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge workflow failed.");
    pushToast(error.value, "error");
  } finally {
    workflowBusyId.value = "";
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
          <FormField v-slot="{ fieldId, describedBy, invalid }" class="file-field" :label="t('Knowledge source file')" required :helper="t('TXT, Markdown, PDF or DOCX · maximum 5 MB · security screened')" :error="fileError">
            <input :id="fieldId" type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required :aria-describedby="describedBy" :aria-invalid="invalid" @change="onFile" />
            <div v-if="file" class="selected-file-summary" aria-live="polite">
              <strong>{{ file.name }}</strong>
              <span>{{ formatFileSize(file.size) }} · {{ t("Ready for security screening") }}</span>
            </div>
          </FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Title')" required :helper="t('Use at least 3 characters so the source is recognizable.')" :error="titleError">
            <input :id="fieldId" v-model="title" type="text" maxlength="255" minlength="3" required :placeholder="t('Demo molding SOP')" :aria-describedby="describedBy" :aria-invalid="invalid" />
          </FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Document type')" required>
            <select :id="fieldId" v-model="documentType" required :aria-describedby="describedBy" :aria-invalid="invalid">
              <option value="demo_sop">{{ t("Demo SOP") }}</option>
              <option value="design_guideline">{{ t("Design guideline") }}</option>
              <option value="trial_report">{{ t("Trial report") }}</option>
              <option value="case_note">{{ t("Case note") }}</option>
            </select>
          </FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Authority')" required>
            <select :id="fieldId" v-model="authorityLevel" required :aria-describedby="describedBy" :aria-invalid="invalid">
              <option value="demo">Demo</option>
              <option value="reviewed_demo">{{ t("Reviewed Demo") }}</option>
            </select>
          </FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Language')" required>
            <select :id="fieldId" v-model="language" required :aria-describedby="describedBy" :aria-invalid="invalid">
              <option value="en">{{ t("English") }}</option>
              <option value="zh-Hant">{{ t("Traditional Chinese") }}</option>
            </select>
          </FormField>
          <p v-if="missingUploadFields" class="form-validation-summary" aria-live="polite">
            {{ t("Required fields remaining: {count}", { count: missingUploadFields }) }}
          </p>
          <button type="submit" :disabled="uploading" :aria-busy="uploading">
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
            <span class="document-status" :class="document.ingestion_status">{{ t(document.ingestion_status) }} · {{ t(document.publication_status || 'published') }}</span>
            <div v-if="canAuthor || canApprove" class="document-workflow-actions">
              <button v-if="canAuthor && document.publication_status === 'draft'" type="button" class="text-button" :disabled="workflowBusyId === document.document_id" @click="transitionDocument(document, 'submit')">{{ t("Submit") }}</button>
              <button v-if="canApprove && document.publication_status === 'in_review'" type="button" class="text-button" :disabled="workflowBusyId === document.document_id" @click="transitionDocument(document, 'approve')">{{ t("Approve") }}</button>
              <button v-if="canApprove && document.publication_status === 'approved'" type="button" class="text-button" :disabled="workflowBusyId === document.document_id" @click="transitionDocument(document, 'publish')">{{ t("Publish") }}</button>
              <button v-if="canApprove && document.publication_status === 'published'" type="button" class="text-button" :disabled="workflowBusyId === document.document_id" @click="transitionDocument(document, 'retire')">{{ t("Retire") }}</button>
            </div>
          </li>
        </ul>
        <FormField v-if="canAuthor || canApprove" v-slot="{ fieldId }" :label="t('Workflow reason')" required><input :id="fieldId" v-model="workflowReason" required maxlength="512" /></FormField>
      </article>

      <article class="knowledge-search">
        <h3>{{ t("Evidence search") }}</h3>
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
          <p v-if="missingSearchFields" class="form-validation-summary" aria-live="polite">
            {{ t("Required fields remaining: {count}", { count: missingSearchFields }) }}
          </p>
          <button type="submit" :disabled="searching || indexedCount === 0" :aria-busy="searching">
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
