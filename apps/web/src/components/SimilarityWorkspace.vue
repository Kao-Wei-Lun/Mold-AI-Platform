<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from "vue";

import type { AssistantContext, UIAction } from "../api/assistant";
import type { CADModelResult } from "../api/cad";
import { emptyMasterDataOptions, type MasterDataOption, type MasterDataOptions } from "../api/masterData";
import {
  createSimilarityComparison,
  createSimilaritySearch,
  fetchSimilarityEngineeringProfile,
  fetchSimilarityJob,
  fetchSimilaritySearch,
  recordSimilarityFeedback,
  saveSimilarityEngineeringProfile,
  type SimilarityEngineeringProfile,
  type SimilarityJob,
  type SimilarityMatch,
  type SimilarityComparison,
} from "../api/similarity";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const { locale, t } = useI18n();

const props = defineProps<{
  query: CADModelResult | null;
  uiAction?: UIAction | null;
  deepLink?: DeepLinkContext | null;
  masterDataOptions?: MasterDataOptions;
  masterDataLoading?: boolean;
  masterDataError?: string | null;
}>();
const emit = defineEmits<{
  contextChange: [context: AssistantContext];
  navigate: [route: "cad"];
  retryMasterData: [];
}>();
const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));
const DeviationHeatmap = defineAsyncComponent(() => import("./DeviationHeatmap.vue"));

const datasetId = ref("");
const productType = ref("");
const materialCode = ref("");
const topK = ref(5);
const comparisonMode = ref<"normalized_shape" | "engineering_size">("normalized_shape");
const toleranceMm = ref(0.5);
const job = ref<SimilarityJob | null>(null);
const selectedMatch = ref<SimilarityMatch | null>(null);
const submitting = ref(false);
const error = ref<string | null>(null);
const comparison = ref<SimilarityComparison | null>(null);
const comparing = ref(false);
const comparisonError = ref<string | null>(null);
const roiEnabled = ref(false);
const roi = ref({ minX: 0, minY: 0, minZ: 0, maxX: 0, maxY: 0, maxZ: 0 });
const engineeringProfile = ref<SimilarityEngineeringProfile | null>(null);
const engineeringProfileSaving = ref(false);
const engineeringProfileError = ref<string | null>(null);
const engineeringProfileLoaded = ref(false);
const feedbackReason = ref("");
const feedbackSending = ref(false);
const feedbackRecorded = ref<string | null>(null);
let pollTimer: number | null = null;
let searchGeneration = 0;
let comparisonGeneration = 0;
let disposed = false;

function invalidateSearch(): number {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  pollTimer = null;
  submitting.value = false;
  return ++searchGeneration;
}

function isCurrentSearch(generation: number): boolean {
  return !disposed && generation === searchGeneration;
}

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const result = computed(() => job.value?.result || null);
const indexed = computed(() => props.query?.similarity_index?.status === "indexed");
const governedOptions = computed(() => props.masterDataOptions || emptyMasterDataOptions());

function optionLabel(option: MasterDataOption): string {
  return locale.value === "zh-TW" ? option.name_zh_tw : option.name_en;
}

function scorePercent(score: number | null | undefined): string {
  return score === null || score === undefined ? "N/A" : `${(score * 100).toFixed(1)}%`;
}

function emptyEngineeringProfile(): SimilarityEngineeringProfile {
  return {
    artifact_version_id: props.query?.artifact_version_id || "",
    tolerance_strictness: "standard",
    ctq_count: 0,
    surface_roughness_ra: null,
    flow_length_ratio: null,
    projected_area: null,
    clamp_force_band: null,
    gate_type: null,
    source_mode: "manual_demo",
    row_version: 0,
    updated_by: "",
    updated_at: "",
  };
}

async function loadEngineeringProfile(): Promise<void> {
  if (!props.query) {
    engineeringProfile.value = null;
    return;
  }
  engineeringProfileError.value = null;
  try {
    engineeringProfile.value =
      (await fetchSimilarityEngineeringProfile(props.query.artifact_version_id)) ||
      emptyEngineeringProfile();
    engineeringProfileLoaded.value = true;
  } catch (caught) {
    engineeringProfileError.value =
      caught instanceof Error ? caught.message : t("Unable to load engineering constraints.");
  }
}

function openEngineeringProfile(event: Event): void {
  if ((event.currentTarget as HTMLDetailsElement).open && !engineeringProfileLoaded.value) {
    loadEngineeringProfile();
  }
}

async function saveEngineeringProfile(): Promise<void> {
  if (!props.query || !engineeringProfile.value) return;
  engineeringProfileSaving.value = true;
  engineeringProfileError.value = null;
  try {
    const profile = engineeringProfile.value;
    engineeringProfile.value = await saveSimilarityEngineeringProfile(
      props.query.artifact_version_id,
      {
        tolerance_strictness: profile.tolerance_strictness,
        ctq_count: profile.ctq_count,
        surface_roughness_ra: profile.surface_roughness_ra,
        flow_length_ratio: profile.flow_length_ratio,
        projected_area: profile.projected_area,
        clamp_force_band: profile.clamp_force_band,
        gate_type: profile.gate_type,
        row_version: profile.row_version,
      },
    );
    pushToast(t("Engineering constraints saved."), "success");
  } catch (caught) {
    engineeringProfileError.value =
      caught instanceof Error ? caught.message : t("Unable to save engineering constraints.");
  } finally {
    engineeringProfileSaving.value = false;
  }
}

async function sendFeedback(action: "accept_reference" | "not_relevant"): Promise<void> {
  if (!result.value || !selectedMatch.value) return;
  if (action === "not_relevant" && !feedbackReason.value) {
    comparisonError.value = t("Select an engineering reason before marking this result not relevant.");
    return;
  }
  feedbackSending.value = true;
  comparisonError.value = null;
  try {
    await recordSimilarityFeedback(
      result.value.search_id,
      selectedMatch.value.artifact_version_id,
      action,
      feedbackReason.value,
    );
    feedbackRecorded.value = action;
    pushToast(t("Similarity feedback recorded."), "success");
  } catch (caught) {
    comparisonError.value = caught instanceof Error ? caught.message : t("Unable to record feedback.");
  } finally {
    feedbackSending.value = false;
  }
}

function resetComparison(): void {
  ++comparisonGeneration;
  comparing.value = false;
  comparison.value = null;
  comparisonError.value = null;
}

async function analyzeDeviation(): Promise<void> {
  if (!result.value || !selectedMatch.value) return;
  const generation = ++comparisonGeneration;
  const isCurrent = () => !disposed && generation === comparisonGeneration;
  comparing.value = true;
  comparisonError.value = null;
  try {
    const nextComparison = await createSimilarityComparison(
      result.value.search_id,
      selectedMatch.value.artifact_version_id,
      roiEnabled.value
        ? {
            min: [roi.value.minX, roi.value.minY, roi.value.minZ],
            max: [roi.value.maxX, roi.value.maxY, roi.value.maxZ],
          }
        : undefined,
    );
    if (!isCurrent()) return;
    comparison.value = nextComparison;
    pushToast(t("3D deviation analysis completed."), "success");
  } catch (caught) {
    if (!isCurrent()) return;
    comparisonError.value = caught instanceof Error ? caught.message : t("3D deviation analysis failed.");
    pushToast(comparisonError.value, "error");
  } finally {
    if (isCurrent()) comparing.value = false;
  }
}

function schedulePoll(generation: number): void {
  if (!isCurrentSearch(generation)) return;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  pollTimer = null;
  if (!terminal.value) pollTimer = window.setTimeout(() => refreshJob(generation), 900);
}

function acceptJob(nextJob: SimilarityJob): void {
  const selectedId = job.value?.job_id === nextJob.job_id
    ? selectedMatch.value?.artifact_version_id : null;
  job.value = nextJob;
  if (nextJob.state === "succeeded" && nextJob.result) {
    selectedMatch.value = nextJob.result.results.find((item) => item.artifact_version_id === selectedId)
      || nextJob.result.results[0] || null;
  }
}

async function refreshJob(generation: number): Promise<void> {
  if (!job.value || !isCurrentSearch(generation)) return;
  const jobId = job.value.job_id;
  try {
    const nextJob = await fetchSimilarityJob(jobId);
    if (!isCurrentSearch(generation) || job.value?.job_id !== jobId) return;
    acceptJob(nextJob);
    schedulePoll(generation);
  } catch (caught) {
    if (!isCurrentSearch(generation)) return;
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh similarity job.");
  }
}

async function submit(): Promise<void> {
  if (!props.query) {
    error.value = t("Upload and process a CAD artifact first.");
    return;
  }
  const generation = invalidateSearch();
  const query = props.query;
  submitting.value = true;
  error.value = null;
  job.value = null;
  selectedMatch.value = null;
  try {
    const accepted = await createSimilaritySearch(
      query,
      {
        datasetIds: datasetId.value.trim() ? [datasetId.value.trim()] : [],
        productTypes: productType.value.trim() ? [productType.value.trim()] : [],
        materialCodes: materialCode.value.trim() ? [materialCode.value.trim()] : [],
      },
      topK.value,
      comparisonMode.value,
      toleranceMm.value,
    );
    if (!isCurrentSearch(generation)) return;
    const nextJob = await fetchSimilarityJob(accepted.job_id);
    if (!isCurrentSearch(generation)) return;
    acceptJob(nextJob);
    schedulePoll(generation);
    pushToast(t("Similarity search started."), "success");
  } catch (caught) {
    if (!isCurrentSearch(generation)) return;
    error.value = caught instanceof Error ? caught.message : t("Similarity search failed.");
    pushToast(error.value, "error");
  } finally {
    if (isCurrentSearch(generation)) submitting.value = false;
  }
}

async function loadDeepLink(): Promise<void> {
  if (props.deepLink?.target !== "similarity") return;
  const generation = invalidateSearch();
  const { search_id: searchId, candidate_id: candidateId } = props.deepLink.refs;
  error.value = null;
  try {
    const nextJob = await fetchSimilaritySearch(searchId);
    if (!isCurrentSearch(generation)) return;
    acceptJob(nextJob);
    if (candidateId && result.value) {
      const candidate = result.value.results.find(
        (item) => item.artifact_version_id === candidateId,
      );
      if (!candidate) throw new Error("DEEP_LINK_CONTEXT_MISMATCH");
      selectedMatch.value = candidate;
    }
    schedulePoll(generation);
  } catch (caught) {
    if (!isCurrentSearch(generation)) return;
    error.value =
      caught instanceof Error && caught.message === "DEEP_LINK_CONTEXT_MISMATCH"
        ? t("The linked candidate does not belong to this similarity search.")
        : t("The linked similarity result is unavailable or not authorized.");
  }
}

watch(
  () => props.query?.artifact_version_id,
  () => {
    invalidateSearch();
    job.value = null;
    selectedMatch.value = null;
    error.value = null;
    engineeringProfile.value = props.query ? emptyEngineeringProfile() : null;
    engineeringProfileLoaded.value = false;
  },
  { immediate: true, flush: "sync" },
);

watch(
  () => [result.value?.search_id, selectedMatch.value?.artifact_version_id] as const,
  () => {
    resetComparison();
    feedbackReason.value = "";
    feedbackRecorded.value = null;
  },
  { flush: "sync" },
);

watch(roiEnabled, (enabled) => {
  if (!enabled || !props.query) return;
  const bounds = props.query.bounding_box;
  roi.value = {
    minX: bounds.min.x,
    minY: bounds.min.y,
    minZ: bounds.min.z,
    maxX: bounds.max.x,
    maxY: bounds.max.y,
    maxZ: bounds.max.z,
  };
});

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
  disposed = true;
  invalidateSearch();
  resetComparison();
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

      <details v-if="engineeringProfile" class="engineering-constraints" @toggle="openEngineeringProfile">
        <summary>{{ t("Engineering similarity constraints") }}</summary>
        <p>{{ t("Manual CTQ and CAE summary fields are optional and only affect ranking when both records provide comparable evidence.") }}</p>
        <div class="engineering-constraint-grid">
          <FormField v-slot="{ fieldId }" :label="t('Tolerance strictness')"><select :id="fieldId" v-model="engineeringProfile.tolerance_strictness"><option value="standard">{{ t("Standard") }}</option><option value="precision">{{ t("Precision") }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('CTQ count')"><input :id="fieldId" v-model.number="engineeringProfile.ctq_count" type="number" min="0" max="10000" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Surface roughness Ra')"><input :id="fieldId" v-model.number="engineeringProfile.surface_roughness_ra" type="number" min="0" step="any" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Flow length ratio')"><input :id="fieldId" v-model.number="engineeringProfile.flow_length_ratio" type="number" min="0" step="any" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Projected area')"><input :id="fieldId" v-model.number="engineeringProfile.projected_area" type="number" min="0" step="any" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Clamp force band')"><input :id="fieldId" v-model="engineeringProfile.clamp_force_band" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Gate type')"><input :id="fieldId" v-model="engineeringProfile.gate_type" /></FormField>
        </div>
        <p v-if="engineeringProfileError" class="error-message">{{ engineeringProfileError }}</p>
        <button type="button" :disabled="engineeringProfileSaving" @click="saveEngineeringProfile">{{ engineeringProfileSaving ? t("Saving...") : t("Save engineering constraints") }}</button>
      </details>

      <form class="similarity-form" @submit.prevent="submit">
        <div v-if="masterDataError" class="master-data-error form-wide" role="alert">
          <span>{{ t("Governed choices are unavailable: {message}", { message: masterDataError }) }}</span>
          <button type="button" class="text-button" @click="emit('retryMasterData')">{{ t("Retry") }}</button>
        </div>
        <div class="form-wide score-grid" data-testid="comparison-mode-controls">
          <FormField v-slot="{ fieldId }" :label="t('Geometry comparison mode')">
            <select :id="fieldId" v-model="comparisonMode" data-testid="comparison-mode">
              <option value="normalized_shape">{{ t("Shape only (uniform scale allowed)") }}</option>
              <option value="engineering_size">{{ t("Actual size (known units required)") }}</option>
            </select>
          </FormField>
          <FormField v-if="comparisonMode === 'engineering_size'" v-slot="{ fieldId }" :label="t('Surface tolerance (mm)')">
            <input :id="fieldId" v-model.number="toleranceMm" type="number" min="0.001" max="10" step="0.001" required />
          </FormField>
        </div>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Dataset filter')">
          <select :id="fieldId" v-model="datasetId" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option v-for="option in governedOptions.dataset" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Product type')">
          <select :id="fieldId" v-model="productType" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option v-for="option in governedOptions.product_type" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Material')">
          <select :id="fieldId" v-model="materialCode" :aria-describedby="describedBy" :aria-invalid="invalid">
            <option value="">{{ t("Any") }}</option>
            <option v-for="option in governedOptions.material" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
          </select>
        </FormField>
        <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Maximum results')" required :helper="t('Choose between 1 and 20 ranked candidates.')">
          <input :id="fieldId" v-model.number="topK" type="number" min="1" max="20" required :aria-describedby="describedBy" :aria-invalid="invalid" />
        </FormField>
        <button type="submit" :disabled="submitting || !indexed" :aria-busy="submitting">
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
        <span>{{ t("Missing lanes reduce evidence coverage and the overall ranking score.") }}</span>
      </div>

      <p class="limitation-note" role="note" data-testid="similarity-validation-note">
        {{ t("Scores express ranking relevance, not the probability that a mold can be reused.") }}
        {{ t("Public CAD geometry ranking has not yet passed independent human-labelled evaluation.") }}
      </p>

      <p v-if="result.match_assessment" class="limitation-note" data-testid="match-assessment">{{ result.match_assessment.decision === 'no_reliable_match' ? t("No returned candidate passed the calibrated threshold. This does not prove the whole database has no match.") : result.match_assessment.status !== 'validated_holdout' ? t("Human calibration is not active. Scores are experimental; no reliable-match threshold is applied.") : t("A dataset-scoped calibrated threshold was evaluated; inspect each candidate decision.") }}</p>
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
                <small v-if="match.match_decision === 'below_threshold'">{{ t("Below calibrated threshold") }}</small>
                <small>{{ match.product_type || t("Unspecified product") }} · {{ match.dataset_id }}</small>
              </span>
              <strong class="overall-score">{{ match.ranking_basis === "reference_only"
                ? t("Reference only") : scorePercent(match.overall_score) }}</strong>
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

          <section v-if="selectedMatch.geometric_verification" class="roi-controls" data-testid="surface-verification">
            <h3>{{ t("Automatic surface verification") }}</h3>
            <p>{{ selectedMatch.geometric_verification.mode === 'engineering_size' ? t("Actual-size comparison uses mm and permits rigid rotation and translation only.") : t("Shape-only comparison allows uniform scaling. Distances use normalized surface RMS radius, not mm.") }}</p>
            <template v-if="selectedMatch.geometric_verification.status === 'computed'">
              <div class="score-grid">
                <div><span>{{ t("Query surface coverage") }}</span><strong>{{ scorePercent(selectedMatch.geometric_verification.query_coverage) }}</strong></div>
                <div><span>{{ t("Candidate surface coverage") }}</span><strong>{{ scorePercent(selectedMatch.geometric_verification.candidate_coverage) }}</strong></div>
                <div><span>{{ t("Surface F-score") }}</span><strong>{{ scorePercent(selectedMatch.geometric_verification.f_score) }}</strong></div>
                <div><span>{{ t("Mean surface distance") }}</span><strong>{{ selectedMatch.geometric_verification.mean_distance?.toFixed(4) }}</strong></div>
                <div><span>{{ t("P95 surface distance") }}</span><strong>{{ selectedMatch.geometric_verification.p95_distance?.toFixed(4) }}</strong></div>
              </div>
              <p>{{ t("Baseline ranking score") }}: {{ scorePercent(selectedMatch.baseline_overall_score) }} · {{ t("Surface adjustment factor") }}: {{ scorePercent(selectedMatch.geometric_verification.score_factor) }}</p>
              <p>{{ t("Coverage tolerance") }}: {{ selectedMatch.geometric_verification.tolerance }}</p>
              <div v-if="selectedMatch.geometric_verification.local_evidence" class="score-grid">
                <div v-for="level in selectedMatch.geometric_verification.local_evidence.levels" :key="level.grid">
                  <span>{{ t("Local lower-quartile coverage") }} ({{ level.grid }}×{{ level.grid }}×{{ level.grid }})</span>
                  <strong>{{ scorePercent(level.lower_quartile_coverage) }}</strong>
                </div>
              </div>
              <p v-if="selectedMatch.geometric_verification.brep_structure">{{ t("STEP adjacency agreement") }}: {{ selectedMatch.geometric_verification.brep_structure.status === 'computed' ? scorePercent(selectedMatch.geometric_verification.brep_structure.agreement) : t("Unavailable; STEP reprocessing may be required.") }}</p>
              <details v-if="selectedMatch.geometric_verification.tolerance_curve"><summary>{{ t("Multi-tolerance evidence") }}</summary>
                <p v-for="row in selectedMatch.geometric_verification.tolerance_curve" :key="row.tolerance">{{ row.tolerance.toFixed(4) }} → {{ scorePercent(row.f_score) }}</p>
              </details>
            </template>
            <p v-else role="status">{{ t("Surface verification is incomplete. This candidate is reference-only; its baseline score is not a verified match.") }} <code>{{ selectedMatch.geometric_verification.error_code }}</code></p>
            <p>{{ t("Experimental surface evidence; not calibrated against human judgments and not an engineering approval.") }}</p>
          </section>

          <p v-if="selectedMatch.geometric_verification" class="muted">{{ t("The breakdown below is the baseline evidence before surface adjustment.") }}</p>
          <div class="score-grid">
            <div v-for="(score, lane) in selectedMatch.sub_scores" :key="lane">
              <span>{{ t(String(lane)) }}</span>
              <strong>{{ scorePercent(score) }}</strong>
            </div>
          </div>
          <p v-if="selectedMatch.evidence_coverage !== undefined" class="evidence-coverage-note">
            {{ t("Evidence coverage: {coverage}. Available-lane score before adjustment: {score}.", {
              coverage: scorePercent(selectedMatch.evidence_coverage),
              score: scorePercent(selectedMatch.available_lane_score),
            }) }}
          </p>

          <details v-if="selectedMatch.geometry_ranking" class="roi-controls">
            <summary>{{ t("How geometry was ranked") }}</summary>
            <p>{{ t("Geometry ranking policy") }}: {{ selectedMatch.geometry_ranking.policy }}</p>
            <p v-if="selectedMatch.geometry_ranking.fallback_reason">
              {{ t("Structured shape blocks are missing; this result uses legacy cosine scoring.") }}
            </p>
            <p v-if="selectedMatch.geometry_ranking.block_coverage !== null">
              {{ t("Shape block coverage") }}: {{ scorePercent(selectedMatch.geometry_ranking.block_coverage) }}
            </p>
            <div class="score-grid">
              <div v-for="(score, block) in selectedMatch.geometry_ranking.block_scores" :key="block">
                <span>{{ t(String(block)) }}</span>
                <strong>{{ scorePercent(score) }}</strong>
              </div>
            </div>
          </details>

          <section class="deviation-analysis" aria-labelledby="deviation-analysis-title">
            <div class="deviation-heading">
              <div>
                <h3 id="deviation-analysis-title">{{ t("3D alignment and deviation") }}</h3>
                <p>{{ t("Run bounded CPU alignment and inspect geometric differences as evidence.") }}</p>
              </div>
              <button type="button" :disabled="comparing" @click="analyzeDeviation">
                {{ comparing ? t("Analyzing...") : t("Analyze 3D deviation") }}
              </button>
            </div>
            <details class="roi-controls">
              <summary>{{ t("Optional ROI bounds") }}</summary>
              <label><input v-model="roiEnabled" type="checkbox" /> {{ t("Limit comparison to this bounding box") }}</label>
              <div v-if="roiEnabled" class="roi-grid">
                <FormField v-slot="{ fieldId }" label="Min X"><input :id="fieldId" v-model.number="roi.minX" type="number" step="any" /></FormField>
                <FormField v-slot="{ fieldId }" label="Min Y"><input :id="fieldId" v-model.number="roi.minY" type="number" step="any" /></FormField>
                <FormField v-slot="{ fieldId }" label="Min Z"><input :id="fieldId" v-model.number="roi.minZ" type="number" step="any" /></FormField>
                <FormField v-slot="{ fieldId }" label="Max X"><input :id="fieldId" v-model.number="roi.maxX" type="number" step="any" /></FormField>
                <FormField v-slot="{ fieldId }" label="Max Y"><input :id="fieldId" v-model.number="roi.maxY" type="number" step="any" /></FormField>
                <FormField v-slot="{ fieldId }" label="Max Z"><input :id="fieldId" v-model.number="roi.maxZ" type="number" step="any" /></FormField>
              </div>
            </details>
            <p v-if="comparisonError" class="error-message" role="alert">{{ comparisonError }}</p>
            <div v-if="comparison" class="deviation-result">
              <div class="score-grid">
                <div><span>{{ t("Alignment") }}</span><strong>{{ t(comparison.alignment_status) }}</strong></div>
                <div><span>{{ t("Distance mode") }}</span><strong>{{ t(comparison.result.deviation.mode) }}</strong></div>
                <div><span>RMSE</span><strong>{{ comparison.result.deviation.rmse }}</strong></div>
                <div v-if="comparison.result.roi_similarity_score !== null"><span>{{ t("ROI similarity") }}</span><strong>{{ scorePercent(comparison.result.roi_similarity_score) }}</strong></div>
              </div>
              <DeviationHeatmap
                :positions="comparison.result.heatmap.positions"
                :deviations="comparison.result.heatmap.deviations"
                :tolerance="comparison.result.deviation.tolerance"
              />
              <small>{{ comparison.lineage_ref }} · {{ comparison.result.deviation.sample_count }} {{ t("samples") }}</small>
            </div>
          </section>

          <div class="evidence-columns">
            <div>
              <h3>{{ t("Major similarities") }}</h3>
              <ul>
                <li v-for="item in (selectedMatch.similarities || [])" :key="item.evidence_ref">
                  {{ t(item.message) }}
                </li>
              </ul>
              <p v-if="!selectedMatch.similarities?.length" class="muted evidence-empty">
                {{ t("No similarity evidence was recorded for this result.") }}
              </p>
            </div>
            <div>
              <h3>{{ t("Major differences") }}</h3>
              <ul>
                <li v-for="item in (selectedMatch.differences || [])" :key="item.evidence_ref">
                  {{ t(item.message) }}
                </li>
              </ul>
              <p v-if="!selectedMatch.differences?.length" class="muted evidence-empty">
                {{ t("No difference evidence was recorded for this result.") }}
              </p>
            </div>
          </div>

          <section class="similarity-feedback" aria-labelledby="similarity-feedback-title">
            <div>
              <h3 id="similarity-feedback-title">{{ t("Was this reference useful?") }}</h3>
              <p>{{ t("Only explicit choices are retained as offline learning labels.") }}</p>
            </div>
            <div class="feedback-actions">
              <button type="button" :disabled="feedbackSending" @click="sendFeedback('accept_reference')">{{ t("Accept as reference") }}</button>
              <select v-model="feedbackReason" :aria-label="t('Not relevant reason')">
                <option value="">{{ t("Select reason") }}</option>
                <option value="different_function">{{ t("Different function") }}</option>
                <option value="different_manufacturing_process">{{ t("Different manufacturing process") }}</option>
                <option value="geometry_not_comparable">{{ t("Geometry is not comparable") }}</option>
                <option value="wrong_scale">{{ t("Wrong scale") }}</option>
                <option value="other_engineering_reason">{{ t("Other engineering reason") }}</option>
              </select>
              <button type="button" class="secondary-button" :disabled="feedbackSending || !feedbackReason" @click="sendFeedback('not_relevant')">{{ t("Mark not relevant") }}</button>
            </div>
            <p v-if="feedbackRecorded" class="success-message">{{ t("Feedback saved for offline evaluation.") }}</p>
          </section>
        </article>
      </div>

      <p class="limitation-note">{{ result.limitations.map((item) => t(item)).join(" ") }}</p>
    </div>
  </section>
</template>
