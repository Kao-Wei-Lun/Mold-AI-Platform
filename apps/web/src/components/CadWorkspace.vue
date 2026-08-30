<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";

import {
  fetchCADJob,
  fetchRecentCAD,
  type CADArtifactSummary,
  type CADJob,
  type CADModelResult,
  type CADUploadProgress,
  uploadCAD,
} from "../api/cad";
import { useI18n } from "../i18n";
import { emptyMasterDataOptions, type MasterDataOption, type MasterDataOptions } from "../api/masterData";
import { pushToast } from "../toast";
import { uploadPolicies, validateUploadFile } from "../fileUpload";
import { fetchRegistry, type RegistryRevision } from "../api/registry";
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
}>();

const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const selectedFile = ref<File | null>(null);
const artifactName = ref("");
const datasetId = ref("");
const productType = ref("");
const materialCode = ref("");
const uploadMode = ref<"quick_analysis" | "governed_archive">("quick_analysis");
const artifactTargetMode = ref<"new_artifact" | "new_version">("new_artifact");
const existingArtifactId = ref("");
const versionArtifacts = ref<CADArtifactSummary[]>([]);
const moldRevisionId = ref("");
const revisions = ref<RegistryRevision[]>([]);
const uploading = ref(false);
const uploadProgress = ref<CADUploadProgress | null>(null);
const error = ref<string | null>(null);
const warning = ref<string | null>(null);
const job = ref<CADJob | null>(null);
const recentJobs = ref<Array<{ job: CADJob; label: string }>>([]);
const selectedRecentJobId = ref("");
const loadingRecent = ref(false);
const catalogLabel = ref("recent processed CAD");
const restoreActiveResult = ref(true);
let pollTimer: number | null = null;

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
  () =>
    Number(!selectedFile.value) +
    Number(!datasetId.value) +
    Number(artifactTargetMode.value === "new_version" && !existingArtifactId.value) +
    Number(uploadMode.value === "governed_archive" && !moldRevisionId.value),
);

async function loadVersionArtifacts(): Promise<void> {
  try {
    versionArtifacts.value = await fetchRecentCAD();
  } catch {
    versionArtifacts.value = [];
  }
}

function optionLabel(option: MasterDataOption): string {
  return locale.value === "zh-TW" ? option.name_zh_tw : option.name_en;
}

watch(
  () => props.masterDataOptions.dataset,
  (options) => {
    if (!options.length || options.some((option) => option.code === datasetId.value)) return;
    datasetId.value = options.find((option) => option.attributes.default === true)?.code || options[0].code;
  },
  { immediate: true },
);

async function loadRevisions(): Promise<void> {
  try {
    const registry = await fetchRegistry();
    revisions.value = registry.revisions.filter((revision) => revision.status !== "archived");
    if (uploadMode.value === "governed_archive" && !moldRevisionId.value) {
      moldRevisionId.value = revisions.value.find((revision) => revision.status === "released")?.id || revisions.value[0]?.id || "";
    }
  } catch {
    revisions.value = [];
  }
}

watch(uploadMode, (mode) => {
  if (mode === "quick_analysis") {
    moldRevisionId.value = "";
    return;
  }
  moldRevisionId.value =
    revisions.value.find((revision) => revision.status === "released")?.id || revisions.value[0]?.id || "";
});

watch(artifactTargetMode, (mode) => {
  if (mode === "new_version" && !versionArtifacts.value.length) void loadVersionArtifacts();
  if (mode === "new_artifact") existingArtifactId.value = "";
});

watch(existingArtifactId, (id) => {
  const artifact = versionArtifacts.value.find((item) => item.artifact_id === id);
  if (!artifact) return;
  uploadMode.value = artifact.mold_revision_id ? "governed_archive" : "quick_analysis";
  moldRevisionId.value = artifact.mold_revision_id || "";
  datasetId.value = artifact.dataset_id;
  productType.value = artifact.product_type;
  materialCode.value = artifact.material_code;
});

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

async function submit(): Promise<void> {
  if (!selectedFile.value) {
    error.value = t("Choose a STEP or STL file first.");
    return;
  }
  if (uploadMode.value === "governed_archive" && !moldRevisionId.value) {
    error.value = t("Select a mold revision for governed archiving.");
    return;
  }

  uploading.value = true;
  uploadProgress.value = { loaded: 0, total: selectedFile.value.size, percent: 0 };
  error.value = null;
  warning.value = null;
  job.value = null;
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
        uploadMode: uploadMode.value,
        moldRevisionId: uploadMode.value === "governed_archive" ? moldRevisionId.value : undefined,
        artifactId: artifactTargetMode.value === "new_version" ? existingArtifactId.value : undefined,
      },
      { onProgress: (progress) => { uploadProgress.value = progress; } },
    );
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

async function browseRecent(curated = false): Promise<void> {
  loadingRecent.value = true;
  error.value = null;
  try {
    const artifacts = await fetchRecentCAD(curated ? "curated-cad-demo-v1" : undefined);
    catalogLabel.value = curated ? "curated Demo queries" : "recent processed CAD";
    recentJobs.value = artifacts.flatMap((artifact) =>
      artifact.jobs
        .filter(
          (candidate) =>
            candidate.capability.startsWith("cad.parse@") &&
            candidate.state === "succeeded" &&
            candidate.result?.similarity_index?.status === "indexed" &&
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
  emit("ready", selected.job.result);
}

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});

loadRevisions();
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
      <fieldset class="cad-upload-purpose form-wide">
        <legend>{{ t("Version action") }}</legend>
        <div class="upload-purpose-options">
          <label class="upload-purpose-option" :class="{ selected: artifactTargetMode === 'new_artifact' }">
            <input v-model="artifactTargetMode" type="radio" name="artifact-target" value="new_artifact" />
            <span><strong>{{ t("Create new CAD record") }}</strong><small>{{ t("Start a separately governed CAD history.") }}</small></span>
          </label>
          <label class="upload-purpose-option" :class="{ selected: artifactTargetMode === 'new_version' }">
            <input v-model="artifactTargetMode" type="radio" name="artifact-target" value="new_version" />
            <span><strong>{{ t("Add version to existing CAD") }}</strong><small>{{ t("Keep prior versions and engineering results unchanged.") }}</small></span>
          </label>
        </div>
      </fieldset>
      <FormField v-if="artifactTargetMode === 'new_version'" v-slot="{ fieldId, describedBy, invalid }" :label="t('Existing CAD record')" required :helper="t('The new file inherits dataset, revision and governance from this record.')">
        <select :id="fieldId" v-model="existingArtifactId" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="" disabled>{{ t("Select an existing CAD record") }}</option>
          <option v-for="artifact in versionArtifacts" :key="artifact.artifact_id" :value="artifact.artifact_id">{{ artifact.name }} · {{ artifact.versions?.length || 0 }} {{ t("versions") }}</option>
        </select>
      </FormField>
      <fieldset v-if="artifactTargetMode === 'new_artifact'" class="cad-upload-purpose form-wide">
        <legend>{{ t("Upload purpose") }}</legend>
        <div class="upload-purpose-options">
          <label class="upload-purpose-option" :class="{ selected: uploadMode === 'quick_analysis' }">
            <input v-model="uploadMode" type="radio" name="upload-purpose" value="quick_analysis" />
            <span>
              <strong>{{ t("Quick analysis") }}</strong>
              <small>{{ t("Upload now for preview, similarity and generic review. Link it to a mold revision later.") }}</small>
            </span>
          </label>
          <label class="upload-purpose-option" :class="{ selected: uploadMode === 'governed_archive' }">
            <input v-model="uploadMode" type="radio" name="upload-purpose" value="governed_archive" />
            <span>
              <strong>{{ t("Governed archive") }}</strong>
              <small>{{ t("Attach this CAD to an existing mold design revision for formal traceability.") }}</small>
            </span>
          </label>
        </div>
      </fieldset>
      <p v-if="uploadMode === 'quick_analysis'" class="cad-governance-note form-wide">
        {{ t("This CAD will be stored as unassigned. Preview and generic analysis remain available; mold-specific rules and formal engineering history require a mold revision.") }}
      </p>
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
      <FormField
        v-if="uploadMode === 'governed_archive'"
        v-slot="{ fieldId, describedBy, invalid }"
        :label="t('Related mold / design revision')"
        required
        :helper="revisions.length ? t('Required for governed archiving and formal Trial, CAE and review traceability.') : t('No active mold revisions are available. Create one in Mold Registry first.')"
      >
        <select :id="fieldId" v-model="moldRevisionId" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="" disabled>{{ t("Select a mold revision") }}</option>
          <option v-for="revision in revisions" :key="revision.id" :value="revision.id">{{ revision.mold_code }}@{{ revision.revision_code }} · {{ t(revision.status) }}</option>
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
  </section>
</template>
