<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";

import {
  exportHMI,
  fetchDemoHMI,
  reviewHMI,
  uploadHMI,
  type HMIExport,
  type HMIExtraction,
  type HMIField,
} from "../api/hmi";
import { downloadProtectedArtifact } from "../api/client";

const selectedFile = ref<File | null>(null);
const previewUrl = ref("");
const extraction = ref<HMIExtraction | null>(null);
const exported = ref<HMIExport | null>(null);
const edits = ref<Record<string, string>>({});
const loadingDemo = ref(false);
const extracting = ref(false);
const reviewingField = ref("");
const exporting = ref(false);
const error = ref<string | null>(null);

const pendingCount = computed(
  () => extraction.value?.fields.filter((field) => field.review_status === "needs_review").length || 0,
);

function setFile(file: File): void {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  selectedFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  extraction.value = null;
  exported.value = null;
  edits.value = {};
}

function onFile(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file) setFile(file);
}

async function loadDemo(): Promise<void> {
  loadingDemo.value = true;
  error.value = null;
  try {
    setFile(await fetchDemoHMI());
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Unable to load the Demo HMI image.";
  } finally {
    loadingDemo.value = false;
  }
}

async function extract(): Promise<void> {
  if (!selectedFile.value) {
    error.value = "Choose an HMI PNG or JPG, or load the bounded Demo screen first.";
    return;
  }
  extracting.value = true;
  error.value = null;
  try {
    extraction.value = await uploadHMI(selectedFile.value);
    edits.value = Object.fromEntries(
      extraction.value.fields.map((field) => [field.field_id, String(field.effective_value ?? "")]),
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "HMI extraction failed.";
  } finally {
    extracting.value = false;
  }
}

async function decide(field: HMIField, action: "confirm" | "correct" | "reject"): Promise<void> {
  if (!extraction.value) return;
  reviewingField.value = field.field_id;
  error.value = null;
  try {
    const decision =
      action === "correct"
        ? {
            field_id: field.field_id,
            action,
            value: Number(edits.value[field.field_id]),
            unit: field.unit,
          }
        : { field_id: field.field_id, action };
    extraction.value = await reviewHMI(extraction.value.extraction_id, [decision]);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Field review failed.";
  } finally {
    reviewingField.value = "";
  }
}

async function createExport(): Promise<void> {
  if (!extraction.value) return;
  exporting.value = true;
  error.value = null;
  try {
    exported.value = await exportHMI(extraction.value.extraction_id);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Workbook export failed.";
  } finally {
    exporting.value = false;
  }
}

async function downloadExport(): Promise<void> {
  if (!exported.value) return;
  error.value = null;
  try {
    await downloadProtectedArtifact(exported.value.download_url, "reviewed-hmi-parameters.xlsx");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Workbook download failed.";
  }
}

function confidenceText(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
});
</script>

<template>
  <section id="hmi" class="hmi-workspace" aria-labelledby="hmi-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Machine UI to Excel</p>
        <h2 id="hmi-title">Review bounded HMI extraction before exporting</h2>
      </div>
      <span class="demo-label">Fixed synthetic profile · No cloud vision</span>
    </div>

    <div class="hmi-input-bar">
      <label class="hmi-file-picker">
        <span>PNG or JPG · maximum 10 MB</span>
        <input type="file" accept="image/png,image/jpeg" @change="onFile" />
      </label>
      <button type="button" class="secondary-button" :disabled="loadingDemo" @click="loadDemo">
        {{ loadingDemo ? "Loading..." : "Load low-confidence Demo screen" }}
      </button>
      <button type="button" :disabled="extracting || !selectedFile" @click="extract">
        {{ extracting ? "Extracting..." : "Extract four parameters" }}
      </button>
    </div>

    <div v-if="previewUrl" class="hmi-preview-card">
      <img :src="previewUrl" alt="Selected injection molding machine HMI screen" />
      <div>
        <strong>{{ selectedFile?.name }}</strong>
        <span>Local preview · content is sent only to this platform API</span>
      </div>
    </div>

    <template v-if="extraction">
      <div class="hmi-status" :class="extraction.review_status">
        <div>
          <span>Review gate</span>
          <strong v-if="extraction.review_status === 'ready_for_export'">Ready for export</strong>
          <strong v-else-if="extraction.review_status === 'rejected'">Rejected</strong>
          <strong v-else>{{ pendingCount }} field requires review</strong>
        </div>
        <div>
          <span>Profile / extractor</span>
          <code>{{ extraction.profile }} · {{ extraction.extractor_version }}</code>
        </div>
      </div>

      <div class="hmi-table-wrap">
        <table class="hmi-table">
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Raw OCR</th>
              <th>Normalized</th>
              <th>Confidence</th>
              <th>Source region</th>
              <th>Review</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="field in extraction.fields" :key="field.field_id">
              <td><strong>{{ field.display_label }}</strong><code>{{ field.parameter_code }}</code></td>
              <td>{{ field.raw_text || "unreadable" }}</td>
              <td>{{ field.effective_value }} {{ field.effective_unit }}</td>
              <td>
                <span class="confidence-pill" :class="{ low: field.confidence < 0.9 }">
                  {{ confidenceText(field.confidence) }}
                </span>
              </td>
              <td>
                <code>
                  x {{ field.source_region.x }} · y {{ field.source_region.y }} ·
                  {{ field.source_region.w }}×{{ field.source_region.h }}
                </code>
              </td>
              <td>
                <div v-if="field.review_status === 'needs_review'" class="hmi-review-controls">
                  <input
                    v-model="edits[field.field_id]"
                    type="number"
                    step="0.1"
                    :aria-label="`Correct ${field.display_label}`"
                  />
                  <span>{{ field.unit }}</span>
                  <button
                    type="button"
                    class="secondary-button"
                    :disabled="reviewingField === field.field_id"
                    @click="decide(field, 'confirm')"
                  >
                    Confirm OCR
                  </button>
                  <button
                    type="button"
                    :disabled="reviewingField === field.field_id"
                    @click="decide(field, 'correct')"
                  >
                    Save correction
                  </button>
                </div>
                <span v-else class="review-state" :class="field.review_status">
                  {{ field.review_status.replaceAll("_", " ") }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="hmi-export-bar">
        <div>
          <strong>Versioned reviewed-parameter workbook</strong>
          <span>Includes source SHA-256, profile, extractor, confidence, regions, and audit data.</span>
        </div>
        <button
          type="button"
          :disabled="exporting || extraction.review_status !== 'ready_for_export'"
          @click="createExport"
        >
          {{ exporting ? "Generating..." : "Generate XLSX" }}
        </button>
        <button v-if="exported" type="button" class="download-link" @click="downloadExport">
          Download {{ exported.template_version }}
        </button>
      </div>

      <div class="hmi-lineage">
        <span>Source SHA-256</span><code>{{ extraction.image_sha256 }}</code>
        <span>Lineage</span><code>{{ extraction.lineage_ref }}</code>
      </div>
      <p class="limitation-note">{{ extraction.limitations.join(" ") }}</p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
