<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";

import {
  bulkArchive,
  commitImport,
  fetchEnterprisePolicy,
  fetchImportBatches,
  updateEnterprisePolicy,
  validateImport,
  type EnterprisePolicy,
  type ImportBatch,
} from "../api/enterprise";
import type { LocalAccount } from "../api/identity";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";

const props = defineProps<{ path: string; currentAccount?: LocalAccount | null }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();
const scope = ref(props.currentAccount?.data_scopes[0] || "public-demo");
const policy = ref<EnterprisePolicy | null>(null);
const batches = ref<ImportBatch[]>([]);
const loading = ref(false);
const error = ref("");
const notice = ref("");
const reason = ref("");
const validatedBatch = ref<ImportBatch | null>(null);
const importForm = reactive({
  domain: "master_data",
  source_name: "manual-json",
  idempotency_key: "",
  records: '[\n  {"kind":"material","code":"DEMO-MATERIAL","name_en":"Demo material"}\n]',
});
const archiveForm = reactive({ domain: "artifacts", ids: "" });
const policyForm = reactive({
  connector_mode: "public_demo" as "public_demo" | "company",
  retention_days: 2555,
  legal_hold: false,
  legal_hold_reason: "",
  dlp_enabled: true,
  export_allowed: true,
  siem_enabled: false,
  siem_destination: "",
  index_namespace: "",
  cache_namespace: "",
});
const activeTab = computed(() => new URL(props.path, window.location.origin).searchParams.get("tab") || "policy");
const canManage = computed(() => props.currentAccount?.permissions.includes("enterprise:manage"));
const canBulk = computed(() => props.currentAccount?.permissions.includes("bulk:manage"));

function setTab(tab: string): void { emit("navigate", `/data/enterprise?tab=${tab}`); }
function pretty(value: unknown): string { return JSON.stringify(value, null, 2); }

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [policy.value, batches.value] = await Promise.all([
      fetchEnterprisePolicy(scope.value), fetchImportBatches(scope.value),
    ]);
    Object.assign(policyForm, {
      connector_mode: policy.value.connector_mode,
      retention_days: policy.value.retention_days,
      legal_hold: policy.value.legal_hold,
      legal_hold_reason: policy.value.legal_hold_reason,
      dlp_enabled: policy.value.dlp_enabled,
      export_allowed: policy.value.export_allowed,
      siem_enabled: policy.value.siem.enabled,
      siem_destination: policy.value.siem.destination || "",
      index_namespace: policy.value.isolation.index_namespace,
      cache_namespace: policy.value.isolation.cache_namespace,
    });
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to load enterprise controls."); }
  finally { loading.value = false; }
}

async function savePolicy(): Promise<void> {
  if (!policy.value || !reason.value.trim()) { error.value = t("A change reason is required."); return; }
  try { policy.value = await updateEnterprisePolicy(policy.value, { ...policyForm }, reason.value); reason.value = ""; notice.value = t("Enterprise policy updated."); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to update enterprise policy."); }
}

async function dryRunImport(): Promise<void> {
  error.value = "";
  try {
    const records = JSON.parse(importForm.records);
    validatedBatch.value = await validateImport({ scope: scope.value, ...importForm, records });
    await load();
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Import validation failed."); }
}

async function commitValidated(): Promise<void> {
  if (!validatedBatch.value || !reason.value.trim()) { error.value = t("A change reason is required."); return; }
  try { validatedBatch.value = await commitImport(validatedBatch.value.batch_id, reason.value); reason.value = ""; notice.value = t("Import committed and reconciled."); await load(); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Import commit failed."); }
}

async function previewArchive(commit = false): Promise<void> {
  if (!reason.value.trim()) { error.value = t("A change reason is required."); return; }
  try {
    const result = await bulkArchive({ scope: scope.value, domain: archiveForm.domain, record_ids: archiveForm.ids.split(/[\s,]+/).filter(Boolean), dry_run: !commit, reason: reason.value });
    notice.value = pretty(result);
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Bulk archive failed."); }
}

watch(scope, load, { immediate: true });
</script>

<template>
  <section class="enterprise-history-workspace">
    <div class="history-list-heading"><div><p class="eyebrow">H7 · Enterprise</p><h2>{{ t("Enterprise data controls") }}</h2></div><label class="enterprise-scope"><span>{{ t("Data scope") }}</span><select v-model="scope"><option v-for="item in currentAccount?.data_scopes || ['public-demo']" :key="item" :value="item">{{ item }}</option></select></label></div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p><pre v-if="notice" class="success-message" role="status">{{ notice }}</pre>
    <section v-if="loading" class="workspace-state">{{ t("Loading enterprise controls…") }}</section>
    <template v-else>
      <DetailTabs :tabs="[{ id: 'policy', label: t('Retention & security') }, { id: 'import', label: t('Bulk import') }, { id: 'archive', label: t('Bulk archive') }]" :active="activeTab" @update:active="setTab" />
      <template v-if="activeTab === 'policy' && policy">
        <PropertyGrid :items="[{ label: t('Connector mode'), value: policy.connector_mode }, { label: t('Classification'), value: policy.classification }, { label: t('Index namespace'), value: policy.isolation.index_namespace, copyable: true }, { label: t('Cache namespace'), value: policy.isolation.cache_namespace, copyable: true }, { label: t('Retention cutoff'), value: new Date(policy.retention_cutoff).toLocaleString() }, { label: t('Retention candidates'), value: pretty(policy.retention_eligible) }, { label: 'DLP', value: policy.dlp_enabled ? t('Enabled') : t('Disabled') }, { label: 'SIEM', value: policy.siem.status }, { label: t('Cross-scope access'), value: policy.isolation.cross_scope_queries ? t('Allowed') : t('Blocked') }]" />
        <details v-if="canManage" class="history-mutation-panel"><summary>{{ t("Edit enterprise policy") }}</summary><div class="history-mutation-grid"><label><span>{{ t('Connector mode') }}</span><select v-model="policyForm.connector_mode"><option value="public_demo">public_demo</option><option value="company">company</option></select></label><label><span>{{ t('Retention days') }}</span><input v-model.number="policyForm.retention_days" type="number" min="30" max="36500" /></label><label><span>{{ t('Index namespace') }}</span><input v-model="policyForm.index_namespace" /></label><label><span>{{ t('Cache namespace') }}</span><input v-model="policyForm.cache_namespace" /></label><label><span>{{ t('Legal hold') }}</span><select v-model="policyForm.legal_hold"><option :value="false">{{ t('Disabled') }}</option><option :value="true">{{ t('Enabled') }}</option></select></label><label class="form-wide"><span>{{ t('Legal hold reason') }}</span><input v-model="policyForm.legal_hold_reason" /></label><label><span>DLP</span><select v-model="policyForm.dlp_enabled"><option :value="true">{{ t('Enabled') }}</option><option :value="false">{{ t('Disabled') }}</option></select></label><label><span>{{ t('Exports') }}</span><select v-model="policyForm.export_allowed"><option :value="true">{{ t('Allowed') }}</option><option :value="false">{{ t('Blocked') }}</option></select></label><label><span>SIEM</span><select v-model="policyForm.siem_enabled"><option :value="false">{{ t('Disabled') }}</option><option :value="true">{{ t('Enabled') }}</option></select></label><label><span>{{ t('SIEM destination') }}</span><input v-model="policyForm.siem_destination" /></label><label class="form-wide"><span>{{ t('Change reason') }} *</span><input v-model="reason" /></label></div><button type="button" @click="savePolicy">{{ t('Save policy') }}</button></details>
      </template>
      <template v-else-if="activeTab === 'import'"><section v-if="canBulk" class="enterprise-bulk-panel"><h3>{{ t('Validate before committing') }}</h3><div class="history-mutation-grid"><label><span>{{ t('Domain') }}</span><select v-model="importForm.domain"><option value="master_data">master_data</option><option value="projects">projects</option></select></label><label><span>{{ t('Idempotency key') }}</span><input v-model="importForm.idempotency_key" /></label><label class="form-wide"><span>{{ t('JSON records') }}</span><textarea v-model="importForm.records" rows="8" /></label><label class="form-wide"><span>{{ t('Change reason') }} *</span><input v-model="reason" /></label></div><div class="history-inline-actions"><button type="button" @click="dryRunImport">{{ t('Run dry validation') }}</button><button v-if="validatedBatch?.validation.valid && validatedBatch.status === 'validated'" type="button" @click="commitValidated">{{ t('Commit validated batch') }}</button></div><pre v-if="validatedBatch" class="history-json">{{ pretty(validatedBatch) }}</pre></section><DataTable :columns="[{ key: 'source', label: t('Source') }, { key: 'domain', label: t('Domain') }, { key: 'status', label: t('Status') }, { key: 'records', label: t('Records') }, { key: 'created', label: t('Created') }]" :items="batches.map((item) => ({ id: item.batch_id, source: item.source_name, domain: item.domain, status: item.status, records: item.validation.record_count, created: new Date(item.created_at).toLocaleString() }))" :empty-text="t('No import batches found.')" /></template>
      <template v-else><section v-if="canBulk" class="enterprise-bulk-panel"><h3>{{ t('Controlled batch archive') }}</h3><p>{{ t('A dry run shows scope and legal-hold impact before any record changes.') }}</p><div class="history-mutation-grid"><label><span>{{ t('Domain') }}</span><select v-model="archiveForm.domain"><option value="artifacts">artifacts</option><option value="trials">trials</option><option value="cae">cae</option></select></label><label class="form-wide"><span>{{ t('Record UUIDs') }}</span><textarea v-model="archiveForm.ids" rows="5" /></label><label class="form-wide"><span>{{ t('Change reason') }} *</span><input v-model="reason" /></label></div><div class="history-inline-actions"><button type="button" @click="previewArchive(false)">{{ t('Preview impact') }}</button><button type="button" class="secondary-button" :disabled="policy?.legal_hold" @click="previewArchive(true)">{{ t('Commit archive') }}</button></div></section></template>
    </template>
  </section>
</template>
