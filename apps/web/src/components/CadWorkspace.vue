<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref } from "vue";

import { fetchCADJob, type CADJob, uploadCAD } from "../api/cad";

const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const selectedFile = ref<File | null>(null);
const artifactName = ref("");
const uploading = ref(false);
const error = ref<string | null>(null);
const warning = ref<string | null>(null);
const job = ref<CADJob | null>(null);
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
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Unable to refresh the CAD job.";
  }
}

async function submit(): Promise<void> {
  if (!selectedFile.value) {
    error.value = "Choose a STEP or STL file first.";
    return;
  }

  uploading.value = true;
  error.value = null;
  warning.value = null;
  job.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);

  try {
    const idempotencyKey = `web-${Date.now()}-${selectedFile.value.name}-${selectedFile.value.size}`;
    const accepted = await uploadCAD(selectedFile.value, artifactName.value, idempotencyKey);
    warning.value = accepted.warnings[0] || null;
    job.value = await fetchCADJob(accepted.job_id);
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "CAD upload failed.";
  } finally {
    uploading.value = false;
  }
}

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section class="cad-workspace" aria-labelledby="cad-workspace-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">CAD ingestion</p>
        <h2 id="cad-workspace-title">Upload and process engineering geometry</h2>
      </div>
      <span class="demo-label">Public / Synthetic Demo Data</span>
    </div>

    <form class="upload-form" @submit.prevent="submit">
      <label>
        <span>STEP or STL file</span>
        <input type="file" accept=".step,.stp,.stl" required @change="chooseFile" />
      </label>
      <label>
        <span>Artifact name</span>
        <input v-model="artifactName" type="text" maxlength="255" placeholder="Housing revision A" />
      </label>
      <button type="submit" :disabled="uploading">
        {{ uploading ? "Submitting..." : "Upload and process" }}
      </button>
    </form>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="warning" class="warning-message">{{ warning }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ job.state }}</span>
          <strong>{{ job.stage.replaceAll("_", " ") }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" aria-label="CAD processing progress">
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
        <div><span>Dimensions</span><strong>{{ dimensions }} {{ result.unit_system }}</strong></div>
        <div><span>Volume</span><strong>{{ result.volume?.toFixed(3) ?? "Not available" }}</strong></div>
        <div><span>Surface area</span><strong>{{ result.surface_area.toFixed(3) }}</strong></div>
        <div><span>Faces / Edges</span><strong>{{ result.face_count }} / {{ result.edge_count }}</strong></div>
        <div><span>Parser</span><strong>{{ result.parser.name }} {{ result.parser.version }}</strong></div>
        <div><span>Quality</span><strong>{{ result.quality_flags.join(", ") || "No flags" }}</strong></div>
      </div>
    </div>
  </section>
</template>
