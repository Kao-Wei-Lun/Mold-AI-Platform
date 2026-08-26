<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";

import type { CADModelResult } from "../api/cad";
import {
  createSimilaritySearch,
  fetchSimilarityJob,
  type SimilarityJob,
  type SimilarityMatch,
} from "../api/similarity";

const props = defineProps<{ query: CADModelResult | null }>();
const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const datasetId = ref("public-demo-v1");
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
    error.value = caught instanceof Error ? caught.message : "Unable to refresh similarity job.";
  }
}

async function submit(): Promise<void> {
  if (!props.query) {
    error.value = "Upload and process a CAD artifact first.";
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
    error.value = caught instanceof Error ? caught.message : "Similarity search failed.";
  } finally {
    submitting.value = false;
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

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section class="similarity-workspace" aria-labelledby="similarity-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">CAD similarity</p>
        <h2 id="similarity-title">Find explainable reference geometry</h2>
      </div>
      <span class="demo-label">Deterministic Demo Profile</span>
    </div>

    <p v-if="!query" class="muted similarity-intro">
      Process a CAD artifact above to use it as the similarity query.
    </p>
    <template v-else>
      <div class="query-summary">
        <div>
          <span>Query artifact version</span>
          <code>{{ query.artifact_version_id }}</code>
        </div>
        <span class="index-state" :class="query.similarity_index?.status || 'missing'">
          {{ query.similarity_index?.status || "not indexed" }}
        </span>
      </div>

      <form class="similarity-form" @submit.prevent="submit">
        <label>
          <span>Dataset filter</span>
          <input v-model="datasetId" type="text" maxlength="128" />
        </label>
        <label>
          <span>Product type</span>
          <input v-model="productType" type="text" maxlength="128" placeholder="Any" />
        </label>
        <label>
          <span>Material</span>
          <input v-model="materialCode" type="text" maxlength="128" placeholder="Any" />
        </label>
        <label>
          <span>Top K</span>
          <input v-model.number="topK" type="number" min="1" max="20" />
        </label>
        <button type="submit" :disabled="submitting || !indexed">
          {{ submitting ? "Starting..." : "Search similar CAD" }}
        </button>
      </form>
      <p v-if="!indexed" class="warning-message">
        This CAD is not indexed. Reprocess it while Qdrant is available before searching.
      </p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ job.state }}</span>
          <strong>{{ job.stage.replaceAll("_", " ") }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" aria-label="Similarity search progress">
        <span :style="{ width: `${job.progress}%` }"></span>
      </div>
      <p v-if="job.error" class="error-message">
        {{ job.error.message }} ({{ job.error.code }})
      </p>
    </div>

    <div v-if="result" class="similarity-results">
      <div class="result-header">
        <div>
          <strong>{{ result.result_count }} ranked candidates</strong>
          <span>{{ result.profile }} · {{ result.index_version }}</span>
        </div>
        <span>Missing lanes are reweighted, never scored as zero.</span>
      </div>

      <p v-if="result.results.length === 0" class="muted">
        No indexed candidates matched the active dataset and metadata filters.
      </p>
      <div v-else class="similarity-layout">
        <ol class="match-list" aria-label="Ranked similarity candidates">
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
                <small>{{ match.product_type || "Unspecified product" }} · {{ match.dataset_id }}</small>
              </span>
              <strong class="overall-score">{{ scorePercent(match.overall_score) }}</strong>
            </button>
          </li>
        </ol>

        <article v-if="selectedMatch" class="match-detail">
          <div class="comparison-viewers">
            <div v-if="result.query_ref.preview">
              <span>Query</span>
              <CadPreview :source="result.query_ref.preview.download_url" />
            </div>
            <div v-if="selectedMatch.preview">
              <span>Candidate #{{ selectedMatch.rank }}</span>
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
              <h3>Major similarities</h3>
              <ul>
                <li v-for="item in selectedMatch.similarities" :key="item.evidence_ref">
                  {{ item.message }}
                </li>
              </ul>
            </div>
            <div>
              <h3>Major differences</h3>
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
