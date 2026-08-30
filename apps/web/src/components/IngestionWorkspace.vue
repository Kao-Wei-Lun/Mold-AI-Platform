<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import type { LocalAccount } from "../api/identity";
import {
  cancelIngestion,
  commitIngestion,
  createIngestion,
  fetchIngestion,
  fetchIngestions,
  importTemplateUrl,
  updateIngestionMapping,
  uploadIngestionFile,
  validateIngestion,
  type IngestionBatch,
} from "../api/ingestions";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import DataTable from "./DataTable.vue";
import FormField from "./FormField.vue";

const props = defineProps<{ path: string; currentAccount?: LocalAccount | null }>();
const { t } = useI18n();
const scope = ref(props.currentAccount?.data_scopes[0] || "public-demo");
const batches = ref<IngestionBatch[]>([]);
const selected = ref<IngestionBatch | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const reason = ref("");
const upload = ref<File | null>(null);
const form = ref({ domain: "master_data", sourceName: "", idempotencyKey: crypto.randomUUID() });
const mapping = ref<Record<string, string>>({});

const canCreate = computed(() => props.currentAccount?.permissions.some((item) => ["ingestion:create", "bulk:manage"].includes(item)) || false);
const canCommit = computed(() => props.currentAccount?.permissions.some((item) => ["ingestion:commit", "bulk:manage"].includes(item)) || false);
const detailId = computed(() => {
  const segments = new URL(props.path, window.location.origin).pathname.split("/").filter(Boolean);
  return segments[0] === "data" && segments[1] === "imports" ? segments[2] || "" : "";
});
const mappingFields = computed(() => {
  if (form.value.domain === "master_data") return [{ canonical: "kind", label: t("Type") }, { canonical: "code", label: t("Code") }, { canonical: "name_en", label: t("English name") }, { canonical: "name_zh_tw", label: t("Traditional Chinese name") }];
  if (form.value.domain === "registry") return ["project_code", "project_name", "part_number", "part_name", "product_type", "material_code", "mold_code", "mold_name", "mold_type", "cavity_count", "revision_code", "change_summary"].map((canonical) => ({ canonical, label: t(canonical.replaceAll("_", " ")) }));
  return [{ canonical: "code", label: t("Project code") }, { canonical: "name", label: t("Project name") }, { canonical: "description", label: t("Description") }];
});
const sourceColumns = computed(() => Object.keys(selected.value?.records?.[0] || {}));
const jobPending = computed(() => ["queued", "committing"].includes(selected.value?.status || ""));

async function load(): Promise<void> {
  loading.value = true; error.value = "";
  try {
    batches.value = await fetchIngestions(scope.value);
    selected.value = detailId.value ? await fetchIngestion(detailId.value) : selected.value;
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to load import center."); }
  finally { loading.value = false; }
}

async function startImport(): Promise<void> {
  if (!upload.value) { error.value = t("Choose a source file first."); return; }
  busy.value = true; error.value = "";
  try {
    let batch = await createIngestion({ scope: scope.value, domain: form.value.domain, source_name: form.value.sourceName || upload.value.name, idempotency_key: form.value.idempotencyKey });
    batch = await uploadIngestionFile(batch.batch_id, upload.value);
    selected.value = batch;
    mapping.value = Object.fromEntries(mappingFields.value.map((item) => [item.canonical, sourceColumns.value.includes(item.canonical) ? item.canonical : ""]));
    batches.value = await fetchIngestions(scope.value);
    pushToast(t("Source uploaded and screened."), "success");
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to create import batch."); }
  finally { busy.value = false; }
}

async function saveMapping(): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  try { selected.value = await updateIngestionMapping(selected.value.batch_id, Object.fromEntries(Object.entries(mapping.value).filter(([, value]) => value))); pushToast(t("Field mapping saved."), "success"); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to save field mapping."); }
  finally { busy.value = false; }
}

async function dryRun(): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  try { selected.value = await validateIngestion(selected.value.batch_id); pushToast(selected.value.validation.valid ? t("Dry run passed.") : t("Dry run found blocking issues."), selected.value.validation.valid ? "success" : "error"); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Dry run failed."); }
  finally { busy.value = false; }
}

async function commit(): Promise<void> {
  if (!selected.value || !reason.value.trim()) { error.value = t("A change reason is required."); return; }
  busy.value = true;
  try { selected.value = await commitIngestion(selected.value.batch_id, reason.value); reason.value = ""; pushToast(t("Import queued for atomic commit."), "success"); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Import commit failed."); }
  finally { busy.value = false; }
}

async function refreshSelected(): Promise<void> { if (selected.value) selected.value = await fetchIngestion(selected.value.batch_id); }
async function cancel(): Promise<void> { if (selected.value) selected.value = await cancelIngestion(selected.value.batch_id); }
function selectBatch(item: Record<string, unknown>): void { const id = String(item.id); fetchIngestion(id).then((value) => { selected.value = value; }); }
function onFile(event: Event): void { upload.value = (event.target as HTMLInputElement).files?.[0] || null; }

onMounted(load);
</script>

<template>
  <section class="ingestion-workspace" aria-labelledby="ingestion-title">
    <header class="history-list-heading"><div><p class="eyebrow">I1 · Ingestion</p><h2 id="ingestion-title">{{ t("Data import center") }}</h2><p>{{ t("Upload, map, dry run, commit and reconcile governed engineering data.") }}</p></div><label class="enterprise-scope"><span>{{ t("Data scope") }}</span><select v-model="scope" @change="load"><option v-for="item in currentAccount?.data_scopes || ['public-demo']" :key="item" :value="item">{{ item }}</option></select></label></header>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <section v-if="canCreate" class="ingestion-create-panel">
      <div class="section-heading"><div><h3>{{ t("New import batch") }}</h3><p>{{ t("JSON, CSV and XLSX sources are screened and preserved as immutable artifacts.") }}</p></div><a :href="importTemplateUrl(form.domain)">{{ t("Download template") }}</a></div>
      <form class="ingestion-create-grid" @submit.prevent="startImport"><FormField v-slot="{ fieldId }" :label="t('Data type')" required><select :id="fieldId" v-model="form.domain"><option value="master_data">{{ t("Engineering reference data") }}</option><option value="projects">{{ t("Projects") }}</option><option value="registry">{{ t("Project, part, mold and revision registry") }}</option></select></FormField><FormField v-slot="{ fieldId }" :label="t('Source name')"><input :id="fieldId" v-model="form.sourceName" /></FormField><FormField v-slot="{ fieldId }" :label="t('Idempotency key')" required><input :id="fieldId" v-model="form.idempotencyKey" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Source file')" required hint="JSON · CSV · XLSX"><input :id="fieldId" type="file" accept=".json,.csv,.xlsx" required @change="onFile" /></FormField><button type="submit" :disabled="busy">{{ t("Upload and screen") }}</button></form>
    </section>
    <section v-if="selected" class="ingestion-detail-panel">
      <div class="record-header"><div><span>{{ selected.canonical_id }}</span><h3>{{ selected.source_name }}</h3><p>{{ selected.domain }} · {{ selected.scope }} · {{ selected.classification }}</p></div><span class="governance-state">{{ t(selected.status) }}</span></div>
      <div class="ingestion-stepper"><span :class="{ done: selected.source_files?.length }">1 {{ t("Source") }}</span><span :class="{ done: selected.field_mapping && selected.status !== 'mapping_required' }">2 {{ t("Mapping") }}</span><span :class="{ done: selected.validation.valid }">3 {{ t("Dry run") }}</span><span :class="{ done: ['queued', 'committing', 'committed'].includes(selected.status) }">4 {{ t("Commit") }}</span><span :class="{ done: selected.status === 'committed' }">5 {{ t("Reconciliation") }}</span></div>
      <section v-if="['mapping_required', 'uploaded'].includes(selected.status)" class="mapping-editor"><h4>{{ t("Field mapping") }}</h4><div class="mapping-grid"><label v-for="field in mappingFields" :key="field.canonical"><span>{{ field.label }}</span><select v-model="mapping[field.canonical]"><option value="">{{ t("Not mapped") }}</option><option v-for="column in sourceColumns" :key="column" :value="column">{{ column }}</option></select></label></div><button type="button" :disabled="busy" @click="saveMapping">{{ t("Save mapping") }}</button></section>
      <div class="ingestion-actions"><button v-if="['uploaded', 'validation_failed', 'validated'].includes(selected.status)" type="button" :disabled="busy" @click="dryRun">{{ t("Run dry validation") }}</button><FormField v-if="selected.status === 'validated' && canCommit" v-slot="{ fieldId }" :label="t('Commit reason')" required><input :id="fieldId" v-model="reason" required /></FormField><button v-if="selected.status === 'validated' && canCommit" type="button" :disabled="busy" @click="commit">{{ t("Commit validated batch") }}</button><button v-if="jobPending" type="button" @click="refreshSelected">{{ t("Refresh job progress") }}</button><button v-if="!['committing', 'committed', 'cancelled'].includes(selected.status)" type="button" class="danger-button" @click="cancel">{{ t("Cancel") }}</button></div>
      <div v-if="selected.validation.record_count !== undefined" class="governance-summary"><div><span>{{ t("Source rows") }}</span><strong>{{ selected.validation.record_count }}</strong></div><div><span>{{ t("Valid rows") }}</span><strong>{{ selected.validation.valid_count }}</strong></div><div><span>{{ t("Existing rows") }}</span><strong>{{ selected.validation.existing_count }}</strong></div><div><span>{{ t("Blocking issues") }}</span><strong>{{ selected.issues?.length || 0 }}</strong></div></div>
      <div v-if="selected.issues?.length" class="ingestion-issue-list"><article v-for="issue in selected.issues" :key="issue.issue_id"><code>{{ issue.code }}</code><strong>{{ t("Row {row}", { row: issue.row_number || 0 }) }}</strong><span>{{ issue.message }}</span></article></div>
      <pre v-if="Object.keys(selected.reconciliation).length" class="history-json">{{ JSON.stringify(selected.reconciliation, null, 2) }}</pre>
    </section>
    <section class="ingestion-history"><h3>{{ t("Import history") }}</h3><p v-if="loading" class="workspace-state">{{ t("Loading import batches…") }}</p><DataTable v-else :columns="[{ key: 'source', label: t('Source') }, { key: 'domain', label: t('Domain') }, { key: 'status', label: t('Status') }, { key: 'created', label: t('Created') }]" :items="batches.map((item) => ({ id: item.batch_id, source: item.source_name, domain: item.domain, status: item.status, created: new Date(item.created_at).toLocaleString() }))" :empty-text="t('No import batches found.')" @select="selectBatch" /></section>
  </section>
</template>
