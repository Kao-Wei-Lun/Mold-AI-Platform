<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";

import {
  fetchCADJob,
  fetchRecentCAD,
  isCADModelJob,
  type CADArtifactSummary,
  type CADJob,
  type CADModelResult,
  type CADUploadAccepted,
  type CADUploadProgress,
  uploadCAD,
} from "../api/cad";
import { useI18n } from "../i18n";
import { emptyMasterDataOptions, type MasterDataOption, type MasterDataOptions } from "../api/masterData";
import { pushToast } from "../toast";
import { uploadPolicies, validateUploadFile } from "../fileUpload";
import { fetchRegistry, linkArtifactToRevision, type RegistryRevision } from "../api/registry";
import FormField from "./FormField.vue";
import FileDropZone from "./FileDropZone.vue";

const { locale, t } = useI18n();

const props = withDefaults(defineProps<{
  activeResult?: CADModelResult | null;
  masterDataOptions?: MasterDataOptions;
  masterDataLoading?: boolean;
  masterDataError?: string | null;
}>(), {
  activeResult: null,
  masterDataOptions: emptyMasterDataOptions,
  masterDataLoading: false,
  masterDataError: null,
});
const emit = defineEmits<{
  ready: [result: NonNullable<CADJob["result"]>];
  retryMasterData: [];
  navigate: [route: string];
}>();

const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

// ── Upload form state ──
const selectedFile = ref<File | null>(null);
const artifactName = ref("");
const datasetId = ref("");
const productType = ref("");
const materialCode = ref("");
const uploading = ref(false);
const uploadProgress = ref<CADUploadProgress | null>(null);
const error = ref<string | null>(null);
const warning = ref<string | null>(null);
const job = ref<CADJob | null>(null);
const restoreActiveResult = ref(true);
let pollTimer: number | null = null;

// ── Post-upload action state ──
const lastAccepted = ref<CADUploadAccepted | null>(null);
const linkRevisionOpen = ref(false);
const linkRevisionId = ref("");
const linkVersionOpen = ref(false);
const revisions = ref<RegistryRevision[]>([]);
const revisionsLoaded = ref(false);
const linking = ref(false);

// ── Recent / demo catalog state ──
const recentJobs = ref<Array<{ job: CADJob; label: string }>>([]);
const selectedRecentJobId = ref("");
const loadingRecent = ref(false);
const catalogLabel = ref("recent processed CAD");

// ── Computed ──
const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const result = computed(() =>
  job.value?.result || (restoreActiveResult.value ? props.activeResult : null),
);
const dimensions = computed(() => {
  if (!result.value) return "-";
  const size = result.value.bounding_box.size;
  return `${size.x.toFixed(2)} x ${size.y.toFixed(2)} x ${size.z.toFixed(2)}`;
});
const missingUploadFields = computed(
  () => Number(!selectedFile.value) + Number(!datasetId.value),
);
const showPostActions = computed(
  () => result.value && job.value?.state === "succeeded" && lastAccepted.value,
);

function optionLabel(option: MasterDataOption): string {
  return locale.value === "zh-TW" ? option.name_zh_tw : option.name_en;
}

// ── Auto-select default dataset ──
watch(
  () => props.masterDataOptions.dataset,
  (options) => {
    if (!options.length || options.some((option) => option.code === datasetId.value)) return;
    datasetId.value = options.find((option) => option.attributes.default === true)?.code || options[0].code;
  },
  { immediate: true },
);

// ── Load revisions (for post-upload linking) ──
async function loadRevisions(): Promise<void> {
  if (revisionsLoaded.value) return;
  try {
    const registry = await fetchRegistry();
    revisions.value = registry.revisions.filter((revision) => revision.status !== "archived");
    revisionsLoaded.value = true;
  } catch {
    revisions.value = [];
  }
}

// ── File selection ──
function selectFile(candidate: File): void {
  uploadProgress.value = null;
  const validation = validateUploadFile(candidate, uploadPolicies.cad);
  if (validation) {
    selectedFile.value = null;
    error.value = validation === "too_large"
      ? t("File size exceeds the {limit} MB limit.", { limit: 200 })
      : t("File type is not supported. Allowed: {formats}.", { formats: "STEP, STP, STL" });
    return;
  }
  selectedFile.value = candidate;
  error.value = null;
  if (selectedFile.value && !artifactName.value) {
    artifactName.value = selectedFile.value.name.replace(/\.(step|stp|stl)$/i, "");
  }
}

// ── Job polling ──
function schedulePoll(): void {
  if (!terminal.value) pollTimer = window.setTimeout(refreshJob, 900);
}

async function refreshJob(): Promise<void> {
  if (!job.value) return;
  try {
    job.value = await fetchCADJob(job.value.job_id);
    if (job.value.state === "succeeded" && job.value.result) emit("ready", job.value.result);
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh the CAD job.");
  }
}

// ── Upload (always quick_analysis) ──
async function submit(): Promise<void> {
  if (!selectedFile.value) {
    error.value = t("Choose a STEP or STL file first.");
    return;
  }

  uploading.value = true;
  uploadProgress.value = { loaded: 0, total: selectedFile.value.size, percent: 0 };
  error.value = null;
  warning.value = null;
  job.value = null;
  lastAccepted.value = null;
  linkRevisionOpen.value = false;
  linkVersionOpen.value = false;
  restoreActiveResult.value = false;
  if (pollTimer !== null) window.clearTimeout(pollTimer);

  try {
    const idempotencyKey = `web-${Date.now()}-${selectedFile.value.name}-${selectedFile.value.size}`;
    const accepted = await uploadCAD(
      selectedFile.value,
      artifactName.value,
      idempotencyKey,
      {
        datasetId: datasetId.value,
        productType: productType.value,
        materialCode: materialCode.value,
        uploadMode: "quick_analysis",
      },
      { onProgress: (progress) => { uploadProgress.value = progress; } },
    );
    lastAccepted.value = accepted;
    warning.value = accepted.warnings.map((message) => t(message)).join(" ") || null;
    job.value = await fetchCADJob(accepted.job_id);
    if (job.value.state === "succeeded" && job.value.result) emit("ready", job.value.result);
    schedulePoll();
    selectedFile.value = null;
    artifactName.value = "";
    pushToast(t("CAD processing started."), "success");
  } catch (caught) {
    uploadProgress.value = null;
    error.value = caught instanceof Error ? caught.message : t("CAD upload failed.");
    pushToast(error.value, "error");
  } finally {
    uploading.value = false;
  }
}

// ── Post-upload: link to mold revision ──
function openLinkRevision(): void {
  linkRevisionOpen.value = true;
  linkVersionOpen.value = false;
  void loadRevisions();
  if (!linkRevisionId.value && revisions.value.length) {
    linkRevisionId.value = revisions.value.find((r) => r.status === "released")?.id || revisions.value[0].id;
  }
}

async function confirmLinkRevision(): Promise<void> {
  if (!lastAccepted.value || !linkRevisionId.value) return;
  linking.value = true;
  try {
    await linkArtifactToRevision(
      lastAccepted.value.artifact_id,
      0, // row_version: fresh artifact
      linkRevisionId.value,
      "Linked via CAD upload post-action.",
    );
    pushToast(t("CAD linked to mold revision."), "success");
    linkRevisionOpen.value = false;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Failed to link CAD to mold revision.");
    pushToast(error.value, "error");
  } finally {
    linking.value = false;
  }
}

// ── Recent / demo catalog ──
async function browseRecent(curated = false): Promise<void> {
  loadingRecent.value = true;
  error.value = null;
  try {
    const artifacts = await fetchRecentCAD(curated ? "curated-cad-demo-v1" : undefined);
    catalogLabel.value = curated ? "curated Demo queries" : "recent processed CAD";
    recentJobs.value = artifacts.flatMap((artifact) =>
      artifact.jobs
        .filter(isCADModelJob)
        .filter(
          (candidate) =>
            candidate.result.similarity_index?.status === "indexed" &&
            (!curated || artifact.source?.role === "query"),
        )
        .map((candidate) => ({
          job: candidate,
          label: `${artifact.name} · ${artifact.source?.scenario || artifact.dataset_id}`,
        })),
    );
    selectedRecentJobId.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load recent CAD artifacts.");
  } finally {
    loadingRecent.value = false;
  }
}

function activateRecent(): void {
  const selected = recentJobs.value.find((candidate) => candidate.job.job_id === selectedRecentJobId.value);
  if (!selected?.job.result) return;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  restoreActiveResult.value = false;
  job.value = selected.job;
  lastAccepted.value = null;
  emit("ready", selected.job.result);
}

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section class="cad-workspace" aria-labelledby="cad-workspace-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ t("CAD ingestion") }}</p>
        <h2 id="cad-workspace-title">{{ t("Upload and process engineering geometry") }}</h2>
      </div>
      <span class="demo-label">{{ t("Public / Synthetic Demo Data") }}</span>
    </div>

    <div class="recent-cad-loader">
      <button type="button" class="secondary-button" :disabled="loadingRecent" @click="browseRecent(false)">
        {{ loadingRecent ? t("Loading...") : t("Browse recent processed CAD") }}
      </button>
      <button type="button" class="secondary-button" :disabled="loadingRecent" @click="browseRecent(true)">
        {{ t("Load curated Demo queries") }}
      </button>
      <template v-if="recentJobs.length">
        <label>
          <span>{{ t("Select {catalog}", { catalog: t(catalogLabel) }) }}</span>
          <select v-model="selectedRecentJobId">
            <option value="" disabled>{{ t("Choose a CAD query") }}</option>
            <option v-for="candidate in recentJobs" :key="candidate.job.job_id" :value="candidate.job.job_id">
              {{ candidate.label }}
            </option>
          </select>
        </label>
        <button type="button" :disabled="!selectedRecentJobId" @click="activateRecent">{{ t("Use as query") }}</button>
      </template>
      <span v-else-if="!loadingRecent" class="muted">{{ t("Or upload a new STEP/STL below.") }}</span>
    </div>

    <form class="upload-form" @submit.prevent="submit">
      <div v-if="masterDataError" class="master-data-error form-wide" role="alert">
        <span>{{ t("Governed choices are unavailable: {message}", { message: masterDataError }) }}</span>
        <button type="button" class="text-button" @click="emit('retryMasterData')">{{ t("Retry") }}</button>
      </div>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('STEP or STL file')" required :helper="t('Accepted formats: STEP, STP or STL.')">
        <FileDropZone
          :id="fieldId"
          accept=".step,.stp,.stl"
          :prompt="t('Drop STEP, STP or STL here')"
          :selected-file="selectedFile"
          :described-by="describedBy"
          :invalid="invalid"
          :disabled="uploading"
          @select="selectFile"
        />
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Artifact name')" :helper="t('Use a recognizable engineering revision name.')">
        <input :id="fieldId" v-model="artifactName" type="text" maxlength="255" :placeholder="t('Housing revision A')" :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Dataset')" required :helper="t('Select where this CAD record belongs.')">
        <select :id="fieldId" v-model="datasetId" required :disabled="masterDataLoading || Boolean(masterDataError)" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="" disabled>{{ masterDataLoading ? t("Loading governed choices...") : t("Select a dataset") }}</option>
          <option v-for="option in masterDataOptions.dataset" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Product type')">
        <select :id="fieldId" v-model="productType" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Not specified") }}</option>
          <option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Material')">
        <select :id="fieldId" v-model="materialCode" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Not specified") }}</option>
          <option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
        </select>
      </FormField>
      <p v-if="missingUploadFields" class="form-validation-summary" aria-live="polite">
        {{ t("Required fields remaining: {count}", { count: missingUploadFields }) }}
      </p>
      <button type="submit" :disabled="uploading" :aria-busy="uploading">
        {{ uploading ? t("Submitting...") : t("Upload and process") }}
      </button>
    </form>

    <div v-if="uploadProgress" class="upload-progress-panel" aria-live="polite">
      <div>
        <strong>{{ uploadProgress.percent >= 100 ? t("Upload complete") : t("Uploading CAD file") }}</strong>
        <span>{{ uploadProgress.percent }}%</span>
      </div>
      <div
        class="progress-track"
        role="progressbar"
        :aria-label="t('CAD network upload progress')"
        :aria-valuenow="uploadProgress.percent"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: `${uploadProgress.percent}%` }"></span>
      </div>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="warning" class="warning-message">{{ warning }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ t(job.state) }}</span>
          <strong>{{ t(job.stage.replaceAll("_", " ")) }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" :aria-label="t('CAD processing progress')">
        <span :style="{ width: `${job.progress}%` }"></span>
      </div>
      <code>{{ job.job_id }}</code>
      <p v-if="job.error" class="error-message">
        {{ job.error.message }} ({{ job.error.code }})
      </p>
    </div>

    <div v-if="result" class="cad-result">
      <CadPreview :source="result.preview.download_url" />
      <div class="geometry-summary">
        <div><span>{{ t("Dimensions") }}</span><strong>{{ dimensions }} {{ result.unit_system }}</strong></div>
        <div><span>{{ t("Volume") }}</span><strong>{{ result.volume?.toFixed(3) ?? t("Not available") }}</strong></div>
        <div><span>{{ t("Surface area") }}</span><strong>{{ result.surface_area.toFixed(3) }}</strong></div>
        <div><span>{{ t("Faces / Edges") }}</span><strong>{{ result.face_count }} / {{ result.edge_count }}</strong></div>
        <div><span>{{ t("Parser") }}</span><strong>{{ result.parser.name }} {{ result.parser.version }}</strong></div>
        <div><span>{{ t("Quality") }}</span><strong>{{ result.quality_flags.join(", ") || t("No flags") }}</strong></div>
      </div>
    </div>

    <!-- Post-upload action cards -->
    <div v-if="showPostActions" class="post-upload-actions">
      <p class="post-upload-heading">{{ t("What would you like to do next?") }}</p>
      <div class="post-action-grid">
        <button type="button" class="post-action-card" :class="{ active: linkRevisionOpen }" @click="openLinkRevision">
          <span class="post-action-icon">🔗</span>
          <span class="post-action-content">
            <strong>{{ t("Link to mold revision") }}</strong>
            <small>{{ t("Attach this CAD to a mold design revision for formal traceability.") }}</small>
          </span>
        </button>
        <button type="button" class="post-action-card" @click="emit('navigate', 'similarity')">
          <span class="post-action-icon">🔍</span>
          <span class="post-action-content">
            <strong>{{ t("Find similar molds") }}</strong>
            <small>{{ t("Search for comparable molds and inspect similarity scores.") }}</small>
          </span>
        </button>
        <button type="button" class="post-action-card" @click="emit('navigate', 'design_review')">
          <span class="post-action-icon">📋</span>
          <span class="post-action-content">
            <strong>{{ t("Run design review") }}</strong>
            <small>{{ t("Validate this geometry against approved engineering rules.") }}</small>
          </span>
        </button>
      </div>

      <!-- Inline: link to mold revision -->
      <div v-if="linkRevisionOpen" class="post-action-detail">
        <p class="post-action-detail-title">{{ t("Select a mold revision to link") }}</p>
        <div class="post-action-detail-body">
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Mold revision')" required :helper="revisions.length ? t('The CAD will be governed under this mold revision.') : t('No active mold revisions are available. Create one in Mold Registry first.')">
            <select :id="fieldId" v-model="linkRevisionId" required :aria-describedby="describedBy" :aria-invalid="invalid">
              <option value="" disabled>{{ t("Select a mold revision") }}</option>
              <option v-for="revision in revisions" :key="revision.id" :value="revision.id">{{ revision.mold_code }}@{{ revision.revision_code }} · {{ t(revision.status) }}</option>
            </select>
          </FormField>
          <div class="post-action-detail-buttons">
            <button type="button" :disabled="!linkRevisionId || linking" :aria-busy="linking" @click="confirmLinkRevision">
              {{ linking ? t("Linking...") : t("Confirm link") }}
            </button>
            <button type="button" class="secondary-button" @click="linkRevisionOpen = false">{{ t("Cancel") }}</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
