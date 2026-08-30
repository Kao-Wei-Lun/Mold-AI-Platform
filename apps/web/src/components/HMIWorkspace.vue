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
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import FileDropZone from "./FileDropZone.vue";
import { formatFileSize, uploadPolicies, validateUploadFile } from "../fileUpload";

const { t } = useI18n();

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
  const validation = validateUploadFile(file, uploadPolicies.hmi);
  if (validation) {
    error.value = validation === "too_large"
      ? t("File size exceeds the {limit} MB limit.", { limit: 10 })
      : t("File type is not supported. Allowed: {formats}.", { formats: "PNG, JPG, JPEG" });
    return;
  }
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  selectedFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  extraction.value = null;
  exported.value = null;
  edits.value = {};
  error.value = null;
}

async function loadDemo(): Promise<void> {
  loadingDemo.value = true;
  error.value = null;
  try {
    setFile(await fetchDemoHMI());
    pushToast(t("Demo HMI image loaded."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load the Demo HMI image.");
    pushToast(error.value, "error");
  } finally {
    loadingDemo.value = false;
  }
}

async function extract(): Promise<void> {
  if (!selectedFile.value) {
    error.value = t("Choose an HMI PNG or JPG, or load the bounded Demo screen first.");
    return;
  }
  extracting.value = true;
  error.value = null;
  try {
    extraction.value = await uploadHMI(selectedFile.value);
    edits.value = Object.fromEntries(
      extraction.value.fields.map((field) => [field.field_id, String(field.effective_value ?? "")]),
    );
    pushToast(t("HMI extraction completed."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("HMI extraction failed.");
    pushToast(error.value, "error");
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
    pushToast(t("Field review saved."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Field review failed.");
    pushToast(error.value, "error");
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
    pushToast(t("Workbook generated."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Workbook export failed.");
    pushToast(error.value, "error");
  } finally {
    exporting.value = false;
  }
}

async function downloadExport(): Promise<void> {
  if (!exported.value) return;
  error.value = null;
  try {
    await downloadProtectedArtifact(exported.value.download_url, "reviewed-hmi-parameters.xlsx");
    pushToast(t("Workbook download started."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Workbook download failed.");
    pushToast(error.value, "error");
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
        <p class="eyebrow">{{ t("Machine UI to Excel") }}</p>
        <h2 id="hmi-title">{{ t("Review bounded HMI extraction before exporting") }}</h2>
      </div>
      <span class="demo-label">{{ t("Fixed synthetic profile · No cloud vision") }}</span>
    </div>

    <div class="hmi-input-bar">
      <FormField v-slot="{ fieldId, describedBy, invalid }" class="hmi-file-picker" :label="t('HMI image')" required :helper="t('PNG or JPG · maximum 10 MB')">
        <FileDropZone
          :id="fieldId"
          accept=".png,.jpg,.jpeg,image/png,image/jpeg"
          :prompt="t('Drop PNG or JPG here')"
          :selected-file="selectedFile"
          :described-by="describedBy"
          :invalid="invalid"
          :disabled="extracting"
          @select="setFile"
        />
      </FormField>
      <button type="button" class="secondary-button" :disabled="loadingDemo" :aria-busy="loadingDemo" @click="loadDemo">
        {{ loadingDemo ? t("Loading...") : t("Load low-confidence Demo screen") }}
      </button>
      <button type="button" :disabled="extracting || !selectedFile" :aria-busy="extracting" @click="extract">
        {{ extracting ? t("Extracting...") : t("Extract four parameters") }}
      </button>
    </div>

    <div v-if="previewUrl" class="hmi-preview-card">
      <img :src="previewUrl" :alt="t('Selected injection molding machine HMI screen')" />
      <div>
        <strong>{{ selectedFile?.name }}</strong>
        <span>{{ formatFileSize(selectedFile?.size || 0) }} · {{ t("Local preview · content is sent only to this platform API") }}</span>
      </div>
    </div>

    <template v-if="extraction">
      <div class="hmi-status" :class="extraction.review_status">
        <div>
          <span>{{ t("Review gate") }}</span>
          <strong v-if="extraction.review_status === 'ready_for_export'">{{ t("Ready for export") }}</strong>
          <strong v-else-if="extraction.review_status === 'rejected'">{{ t("Rejected") }}</strong>
          <strong v-else>{{ t("{count} field requires review", { count: pendingCount }) }}</strong>
        </div>
        <div>
          <span>{{ t("Profile / extractor") }}</span>
          <code>{{ extraction.profile }} · {{ extraction.extractor_version }}</code>
        </div>
      </div>

      <div class="hmi-table-wrap">
        <table class="hmi-table">
          <thead>
            <tr>
              <th>{{ t("Parameter") }}</th>
              <th>{{ t("Raw OCR") }}</th>
              <th>{{ t("Normalized") }}</th>
              <th>{{ t("Confidence") }}</th>
              <th>{{ t("Source region") }}</th>
              <th>{{ t("Review") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(field, fieldIndex) in extraction.fields" :key="field.field_id">
              <td><strong>{{ t(field.display_label) }}</strong><code>{{ field.parameter_code }}</code></td>
              <td>{{ field.raw_text || t("unreadable") }}</td>
              <td>{{ field.effective_value }} {{ field.effective_unit }}</td>
              <td>
                <span class="confidence-pill" :class="{ low: field.confidence < 0.9 }">
                  {{ confidenceText(field.confidence) }}
                </span>
              </td>
              <td>
                <details class="hmi-source-region">
                  <summary>{{ t("Region {label}", { label: String.fromCharCode(65 + fieldIndex) }) }}</summary>
                  <code>
                    x {{ field.source_region.x }} · y {{ field.source_region.y }} ·
                    {{ field.source_region.w }}×{{ field.source_region.h }}
                  </code>
                </details>
              </td>
              <td>
                <div v-if="field.review_status === 'needs_review'" class="hmi-review-controls">
                  <input
                    v-model="edits[field.field_id]"
                    type="number"
                    step="0.1"
                    :aria-label="t('Correct {label}', { label: t(field.display_label) })"
                  />
                  <span>{{ field.unit }}</span>
                  <button
                    type="button"
                    class="secondary-button"
                    :disabled="reviewingField === field.field_id"
                    @click="decide(field, 'confirm')"
                  >
                    {{ t("Confirm OCR") }}
                  </button>
                  <button
                    type="button"
                    :disabled="reviewingField === field.field_id"
                    @click="decide(field, 'correct')"
                  >
                    {{ t("Save correction") }}
                  </button>
                </div>
                <span v-else class="review-state" :class="field.review_status">
                  {{ t(field.review_status.replaceAll("_", " ")) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="hmi-export-bar">
        <div>
          <strong>{{ t("Versioned reviewed-parameter workbook") }}</strong>
          <span>{{ t("Includes source SHA-256, profile, extractor, confidence, regions, and audit data.") }}</span>
        </div>
        <button
          type="button"
          :disabled="exporting || extraction.review_status !== 'ready_for_export'"
          :aria-busy="exporting"
          @click="createExport"
        >
          {{ exporting ? t("Generating...") : t("Generate XLSX") }}
        </button>
        <button v-if="exported" type="button" class="download-link" @click="downloadExport">
          {{ t("Download {version}", { version: exported.template_version }) }}
        </button>
      </div>

      <div class="hmi-lineage">
        <span>{{ t("Source SHA-256") }}</span><code>{{ extraction.image_sha256 }}</code>
        <span>{{ t("Lineage") }}</span><code>{{ extraction.lineage_ref }}</code>
      </div>
      <p class="limitation-note">{{ extraction.limitations.join(" ") }}</p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
