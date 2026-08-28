<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref } from "vue";

import { fetchCADJob, fetchRecentCAD, type CADJob, uploadCAD } from "../api/cad";
import { useI18n } from "../i18n";

const { t } = useI18n();

const emit = defineEmits<{ ready: [result: NonNullable<CADJob["result"]>] }>();

const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const selectedFile = ref<File | null>(null);
const artifactName = ref("");
const datasetId = ref("manual-cad-upload-v1");
const productType = ref("");
const materialCode = ref("");
const uploading = ref(false);
const error = ref<string | null>(null);
const warning = ref<string | null>(null);
const job = ref<CADJob | null>(null);
const recentJobs = ref<Array<{ job: CADJob; label: string }>>([]);
const selectedRecentJobId = ref("");
const loadingRecent = ref(false);
const catalogLabel = ref("recent processed CAD");
let pollTimer: number | null = null;

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const result = computed(() => job.value?.result || null);
const dimensions = computed(() => {
  if (!result.value) return "-";
  const size = result.value.bounding_box.size;
  return `${size.x.toFixed(2)} x ${size.y.toFixed(2)} x ${size.z.toFixed(2)}`;
});

function chooseFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] || null;
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

  uploading.value = true;
  error.value = null;
  warning.value = null;
  job.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);

  try {
    const idempotencyKey = `web-${Date.now()}-${selectedFile.value.name}-${selectedFile.value.size}`;
    const accepted = await uploadCAD(selectedFile.value, artifactName.value, idempotencyKey, {
      datasetId: datasetId.value,
      productType: productType.value,
      materialCode: materialCode.value,
    });
    warning.value = accepted.warnings[0] || null;
    job.value = await fetchCADJob(accepted.job_id);
    if (job.value.state === "succeeded" && job.value.result) emit("ready", job.value.result);
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("CAD upload failed.");
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
  job.value = selected.job;
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
      <label>
        <span>{{ t("STEP or STL file") }}</span>
        <input type="file" accept=".step,.stp,.stl" required @change="chooseFile" />
      </label>
      <label>
        <span>{{ t("Artifact name") }}</span>
        <input v-model="artifactName" type="text" maxlength="255" :placeholder="t('Housing revision A')" />
      </label>
      <label>
        <span>{{ t("Dataset") }} <abbr class="required-mark" :title="t('Required')">*</abbr></span>
        <select v-model="datasetId" required>
          <option value="manual-cad-upload-v1">manual-cad-upload-v1</option>
          <option value="curated-cad-demo-v1">curated-cad-demo-v1</option>
          <option value="public-demo-v1">public-demo-v1</option>
        </select>
      </label>
      <label>
        <span>{{ t("Product type") }}</span>
        <select v-model="productType">
          <option value="">{{ t("Not specified") }}</option>
          <option value="housing">{{ t("Housing") }}</option>
          <option value="connector_housing">{{ t("Connector housing") }}</option>
          <option value="electronics_cover">{{ t("Electronics cover") }}</option>
          <option value="thin_wall_tray">{{ t("Thin-wall tray") }}</option>
        </select>
      </label>
      <label>
        <span>{{ t("Material") }}</span>
        <select v-model="materialCode">
          <option value="">{{ t("Not specified") }}</option>
          <option value="PA6-GF30">PA6-GF30</option>
          <option value="ABS-GENERAL">ABS-GENERAL</option>
          <option value="PP-HOMO">PP-HOMO</option>
          <option value="PC_ABS">PC_ABS</option>
        </select>
      </label>
      <button type="submit" :disabled="uploading">
        {{ uploading ? t("Submitting...") : t("Upload and process") }}
      </button>
    </form>

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
