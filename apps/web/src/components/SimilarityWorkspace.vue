<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from "vue";

import type { AssistantContext, UIAction } from "../api/assistant";
import type { CADModelResult } from "../api/cad";
import {
  createSimilaritySearch,
  fetchSimilarityJob,
  fetchSimilaritySearch,
  type SimilarityJob,
  type SimilarityMatch,
} from "../api/similarity";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const { locale, t } = useI18n();

const props = defineProps<{
  query: CADModelResult | null;
  uiAction?: UIAction | null;
  deepLink?: DeepLinkContext | null;
}>();
const emit = defineEmits<{
  contextChange: [context: AssistantContext];
  navigate: [route: "cad"];
}>();
const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const datasetId = ref("");
const productType = ref("");
const materialCode = ref("");
const topK = ref(5);
const job = ref<SimilarityJob | null>(null);
const selectedMatch = ref<SimilarityMatch | null>(null);
const submitting = ref(false);
const error = ref<string | null>(null);
let pollTimer: number | null = null;

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const result = computed(() => job.value?.result || null);
const indexed = computed(() => props.query?.similarity_index?.status === "indexed");

function scorePercent(score: number | null): string {
  return score === null ? "N/A" : `${(score * 100).toFixed(1)}%`;
}

function schedulePoll(): void {
  if (!terminal.value) pollTimer = window.setTimeout(refreshJob, 900);
}

function acceptJob(nextJob: SimilarityJob): void {
  job.value = nextJob;
  if (nextJob.state === "succeeded" && nextJob.result) {
    selectedMatch.value = nextJob.result.results[0] || null;
  }
}

async function refreshJob(): Promise<void> {
  if (!job.value) return;
  try {
    acceptJob(await fetchSimilarityJob(job.value.job_id));
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh similarity job.");
  }
}

async function submit(): Promise<void> {
  if (!props.query) {
    error.value = t("Upload and process a CAD artifact first.");
    return;
  }
  submitting.value = true;
  error.value = null;
  job.value = null;
  selectedMatch.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    const accepted = await createSimilaritySearch(
      props.query,
      {
        datasetIds: datasetId.value.trim() ? [datasetId.value.trim()] : [],
        productTypes: productType.value.trim() ? [productType.value.trim()] : [],
        materialCodes: materialCode.value.trim() ? [materialCode.value.trim()] : [],
      },
      topK.value,
    );
    acceptJob(await fetchSimilarityJob(accepted.job_id));
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Similarity search failed.");
  } finally {
    submitting.value = false;
  }
}

async function loadDeepLink(): Promise<void> {
  if (props.deepLink?.target !== "similarity") return;
  error.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    acceptJob(await fetchSimilaritySearch(props.deepLink.refs.search_id));
    const candidateId = props.deepLink.refs.candidate_id;
    if (candidateId && result.value) {
      const candidate = result.value.results.find(
        (item) => item.artifact_version_id === candidateId,
      );
      if (!candidate) throw new Error("DEEP_LINK_CONTEXT_MISMATCH");
      selectedMatch.value = candidate;
    }
    schedulePoll();
  } catch (caught) {
    error.value =
      caught instanceof Error && caught.message === "DEEP_LINK_CONTEXT_MISMATCH"
        ? t("The linked candidate does not belong to this similarity search.")
        : t("The linked similarity result is unavailable or not authorized.");
  }
}

watch(
  () => props.query?.artifact_version_id,
  () => {
    job.value = null;
    selectedMatch.value = null;
    error.value = null;
    if (pollTimer !== null) window.clearTimeout(pollTimer);
  },
);

watch(
  () => [
    props.deepLink?.target,
    props.deepLink?.refs.search_id,
    props.deepLink?.refs.candidate_id,
  ],
  loadDeepLink,
  { immediate: true },
);

watch(
  [() => result.value?.search_id, () => selectedMatch.value?.artifact_version_id],
  () => {
    if (!result.value || !selectedMatch.value || !job.value) return;
    emit("contextChange", {
      context_version: "1.0",
      page: "similarity_search",
      query_artifact_version_id: result.value.query_ref.cad_artifact_version_id,
      similarity_search_id: result.value.search_id,
      selected_candidate_artifact_version_id: selectedMatch.value.artifact_version_id,
      job_id: job.value.job_id,
      ui_locale: locale.value,
    });
  },
);

watch(
  () => props.uiAction?.action_id,
  async () => {
    const action = props.uiAction;
    if (!action || action.type !== "assistant.show_evidence" || !result.value) return;
    if (action.target.search_id !== result.value.search_id) return;
    const selected = result.value.results.find(
      (item) => item.artifact_version_id === action.target.candidate_artifact_version_id,
    );
    if (!selected) return;
    selectedMatch.value = selected;
    await nextTick();
    document.getElementById("similarity")?.scrollIntoView({ behavior: "smooth", block: "start" });
  },
);

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section id="similarity" class="similarity-workspace" aria-labelledby="similarity-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ t("CAD similarity") }}</p>
        <h2 id="similarity-title">{{ t("Find explainable reference geometry") }}</h2>
      </div>
      <span class="demo-label">{{ t("Deterministic Demo Profile") }}</span>
    </div>

    <WorkspaceEmptyState
      v-if="!query"
      :eyebrow="t('CAD required')"
      :title="t('Prepare a CAD query first')"
      :message="t('Open CAD & artifacts, process or select a model, then return here to search comparable molds.')"
      :action-label="t('Open CAD & artifacts')"
      @action="emit('navigate', 'cad')"
    />
    <template v-else>
      <div class="query-summary">
        <div>
          <span>{{ t("Query artifact version") }}</span>
          <code>{{ query.artifact_version_id }}</code>
        </div>
        <span class="index-state" :class="query.similarity_index?.status || 'missing'">
          {{ t(query.similarity_index?.status || "not indexed") }}
        </span>
      </div>

      <form class="similarity-form" @submit.prevent="submit">
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Dataset filter')">
          <select :id="fieldId" v-model="datasetId" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option value="public-demo-v1">public-demo-v1</option>
            <option value="curated-cad-demo-v1">curated-cad-demo-v1</option>
            <option value="manual-cad-upload-v1">manual-cad-upload-v1</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Product type')">
          <select :id="fieldId" v-model="productType" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option value="housing">{{ t("Housing") }}</option>
            <option value="connector_housing">{{ t("Connector housing") }}</option>
            <option value="electronics_cover">{{ t("Electronics cover") }}</option>
            <option value="thin_wall_tray">{{ t("Thin-wall tray") }}</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Material')">
          <select :id="fieldId" v-model="materialCode" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option value="PA6-GF30">PA6-GF30</option>
            <option value="ABS-GENERAL">ABS-GENERAL</option>
            <option value="PP-HOMO">PP-HOMO</option>
            <option value="PC_ABS">PC_ABS</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Maximum results')" required :helper="t('Choose between 1 and 20 ranked candidates.')">
          <input :id="fieldId" v-model.number="topK" type="number" min="1" max="20" required :aria-describedby="describedBy" :aria-invalid="invalid" />
        </FormField>
        <button type="submit" :disabled="submitting || !indexed">
          {{ submitting ? t("Starting...") : t("Search similar CAD") }}
        </button>
      </form>
      <p v-if="!indexed" class="warning-message">
        {{ t("This CAD is not indexed. Reprocess it while Qdrant is available before searching.") }}
      </p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ t(job.state) }}</span>
          <strong>{{ t(job.stage.replaceAll("_", " ")) }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" :aria-label="t('Similarity search progress')">
        <span :style="{ width: `${job.progress}%` }"></span>
      </div>
      <p v-if="job.error" class="error-message">
        {{ job.error.message }} ({{ job.error.code }})
      </p>
    </div>

    <div v-if="result" class="similarity-results">
      <div class="result-header">
        <div>
          <strong>{{ t("{count} ranked candidates", { count: result.result_count }) }}</strong>
          <span>{{ result.profile }} · {{ result.index_version }}</span>
        </div>
        <span>{{ t("Missing lanes are reweighted, never scored as zero.") }}</span>
      </div>

      <p v-if="result.results.length === 0" class="muted">
        {{ t("No indexed candidates matched the active dataset and metadata filters.") }}
      </p>
      <div v-else class="similarity-layout">
        <ol class="match-list" :aria-label="t('Ranked similarity candidates')">
          <li v-for="match in result.results" :key="match.artifact_version_id">
            <button
              type="button"
              class="match-card"
              :class="{ selected: selectedMatch?.artifact_version_id === match.artifact_version_id }"
              @click="selectedMatch = match"
            >
              <span class="rank">#{{ match.rank }}</span>
              <span>
                <strong>{{ match.artifact_name }}</strong>
                <small>{{ match.product_type || t("Unspecified product") }} · {{ match.dataset_id }}</small>
              </span>
              <strong class="overall-score">{{ scorePercent(match.overall_score) }}</strong>
            </button>
          </li>
        </ol>

        <article v-if="selectedMatch" class="match-detail">
          <div class="comparison-viewers">
            <div v-if="result.query_ref.preview">
              <span>{{ t("Query") }}</span>
              <CadPreview :source="result.query_ref.preview.download_url" />
            </div>
            <div v-if="selectedMatch.preview">
              <span>{{ t("Candidate #{rank}", { rank: selectedMatch.rank }) }}</span>
              <CadPreview :source="selectedMatch.preview.download_url" />
            </div>
          </div>

          <div class="score-grid">
            <div v-for="(score, lane) in selectedMatch.sub_scores" :key="lane">
              <span>{{ lane }}</span>
              <strong>{{ scorePercent(score) }}</strong>
            </div>
          </div>

          <div class="evidence-columns">
            <div>
              <h3>{{ t("Major similarities") }}</h3>
              <ul>
                <li v-for="item in selectedMatch.similarities" :key="item.evidence_ref">
                  {{ item.message }}
                </li>
              </ul>
            </div>
            <div>
              <h3>{{ t("Major differences") }}</h3>
              <ul>
                <li v-for="item in selectedMatch.differences" :key="item.evidence_ref">
                  {{ item.message }}
                </li>
              </ul>
            </div>
          </div>
        </article>
      </div>

      <p class="limitation-note">{{ result.limitations.join(" ") }}</p>
    </div>
  </section>
</template>
