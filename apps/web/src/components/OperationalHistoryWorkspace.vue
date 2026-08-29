<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  exportAudit,
  fetchAnalyses,
  fetchAnalysis,
  fetchAudit,
  fetchAuditDetail,
  fetchJob,
  fetchJobs,
  fetchLineage,
  HistoryApiError,
  mutateAnalysis,
  mutateJob,
  type AnalysisDetail,
  type AnalysisSummary,
  type AuditRecord,
  type HistoryJob,
  type LineageGraph,
} from "../api/history";
import type { LocalAccount } from "../api/identity";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RecordHeader from "./RecordHeader.vue";

type Domain = "analysis-results" | "jobs" | "audit-lineage";
const props = defineProps<{ domain: Domain; path: string; currentAccount?: LocalAccount | null }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();

const loading = ref(false);
const mutating = ref(false);
const error = ref("");
const notice = ref("");
const reason = ref("");
const analyses = ref<AnalysisSummary[]>([]);
const analysis = ref<AnalysisDetail | null>(null);
const comparison = ref<AnalysisDetail | null>(null);
const comparisonId = ref("");
const jobs = ref<HistoryJob[]>([]);
const job = ref<HistoryJob | null>(null);
const audits = ref<AuditRecord[]>([]);
const audit = ref<AuditRecord | null>(null);
const lineage = ref<LineageGraph | null>(null);
const analysisFilter = ref("");
const jobFilter = ref("");
const auditFilter = ref("");
const lineageRootType = ref("artifact_version");
const lineageRootId = ref("");

const location = computed(() => new URL(props.path, window.location.origin));
const segments = computed(() => location.value.pathname.split("/").filter(Boolean));
const recordId = computed(() => segments.value[2] || "");
const recordType = computed(() => location.value.searchParams.get("type") || "");
const activeTab = computed(() => location.value.searchParams.get("tab") || "overview");
const auditMode = computed(() => location.value.searchParams.get("view") !== "lineage");
const listPath = computed(() => `/data/${props.domain}`);
const canManageAnalysis = computed(() => props.currentAccount?.permissions.includes("analysis:manage"));
const canManageJobs = computed(() => ({
  cancel: props.currentAccount?.permissions.includes("job:cancel"),
  retry: props.currentAccount?.permissions.includes("job:retry"),
}));
const canExportAudit = computed(() => props.currentAccount?.permissions.includes("audit:export"));
const title = computed(() => ({
  "analysis-results": "Analysis results",
  jobs: "Jobs & queue",
  "audit-lineage": "Audit & lineage",
})[props.domain]);

function pretty(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function setTab(tab: string): void {
  const params = new URLSearchParams(location.value.search);
  params.set("tab", tab);
  emit("navigate", `${location.value.pathname}?${params}`);
}

function detailPath(item: AnalysisSummary): string {
  return `${listPath.value}/${item.analysis_id}?type=${encodeURIComponent(item.analysis_type)}`;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  analysis.value = null;
  job.value = null;
  audit.value = null;
  try {
    if (props.domain === "analysis-results") {
      if (recordId.value && recordType.value) analysis.value = await fetchAnalysis(recordType.value, recordId.value);
      else analyses.value = (await fetchAnalyses(analysisFilter.value)).items;
    } else if (props.domain === "jobs") {
      if (recordId.value) job.value = await fetchJob(recordId.value);
      else jobs.value = (await fetchJobs(jobFilter.value)).items;
    } else if (recordId.value) {
      audit.value = await fetchAuditDetail(recordId.value);
    } else if (auditMode.value) {
      audits.value = (await fetchAudit(auditFilter.value)).items;
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load historical data.");
  } finally {
    loading.value = false;
  }
}

async function changeAnalysis(action: "rerun" | "archive" | "restore"): Promise<void> {
  if (!analysis.value || !reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  mutating.value = true;
  try {
    analysis.value = await mutateAnalysis(analysis.value, action, reason.value);
    reason.value = "";
    notice.value = t(action === "rerun" ? "Analysis rerun created." : "Analysis lifecycle updated.");
  } catch (caught) {
    error.value = caught instanceof HistoryApiError && caught.status === 409
      ? t("This record changed after loading. Refresh it before saving again.")
      : caught instanceof Error ? caught.message : t("Unable to update analysis.");
  } finally {
    mutating.value = false;
  }
}

async function changeJob(action: "cancel" | "retry"): Promise<void> {
  if (!job.value || !reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  mutating.value = true;
  try {
    job.value = await mutateJob(job.value.job_id, action, reason.value);
    reason.value = "";
    notice.value = t(action === "retry" ? "Retry job created." : "Cancellation requested.");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to update job.");
  } finally {
    mutating.value = false;
  }
}

async function loadComparison(): Promise<void> {
  if (!analysis.value || !comparisonId.value.trim()) return;
  loading.value = true;
  error.value = "";
  try {
    comparison.value = await fetchAnalysis(analysis.value.analysis_type, comparisonId.value.trim());
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load comparison.");
  } finally {
    loading.value = false;
  }
}

async function loadLineage(): Promise<void> {
  if (!lineageRootId.value.trim()) return;
  loading.value = true;
  error.value = "";
  try { lineage.value = await fetchLineage(lineageRootType.value, lineageRootId.value.trim()); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to load lineage."); }
  finally { loading.value = false; }
}

watch(() => [props.domain, recordId.value, recordType.value, auditMode.value], load, { immediate: true });
</script>

<template>
  <section class="operational-history-workspace">
    <div class="history-list-heading">
      <div><p class="eyebrow">{{ t("Historical data") }}</p><h2>{{ t(title) }}</h2></div>
      <div class="history-list-actions">
        <button v-if="recordId" type="button" class="text-button" @click="emit('navigate', listPath)">← {{ t("Back to records") }}</button>
        <button type="button" :disabled="loading" @click="load">{{ t("Refresh data") }}</button>
      </div>
    </div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
    <section v-if="loading" class="workspace-state">{{ t("Loading complete historical record…") }}</section>

    <template v-else-if="domain === 'analysis-results' && !recordId">
      <div class="history-filter-strip">
        <label><span>{{ t("Analysis type") }}</span><select v-model="analysisFilter" @change="load"><option value="">{{ t("All types") }}</option><option value="similarity">Similarity</option><option value="design_review">Design review</option><option value="knowledge_search">Knowledge</option><option value="process_search">Process</option><option value="cae_comparison">CAE</option></select></label>
      </div>
      <DataTable :columns="[{ key: 'title', label: t('Analysis') }, { key: 'type', label: t('Type') }, { key: 'state', label: t('Status') }, { key: 'results', label: t('Results') }, { key: 'created', label: t('Created') }]" :items="analyses.map((item) => ({ id: item.analysis_id, source: item, title: item.title, type: item.analysis_type, state: `${item.state} · ${item.lifecycle.status}`, results: item.result_count, created: new Date(item.created_at).toLocaleString() }))" :empty-text="t('No analysis history found.')" @select="emit('navigate', detailPath($event.source as AnalysisSummary))" />
    </template>

    <template v-else-if="domain === 'analysis-results' && analysis">
      <RecordHeader :title="`${analysis.analysis_type} analysis`" :identifier="analysis.analysis_id" :status="analysis.lifecycle.status" :version="`row ${analysis.lifecycle.row_version}`" />
      <details v-if="canManageAnalysis" class="history-mutation-panel"><summary>{{ t("Govern analysis result") }}</summary><div class="history-mutation-grid"><label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" /></label></div><div class="history-inline-actions"><button type="button" :disabled="mutating" @click="changeAnalysis('rerun')">{{ t("Rerun") }}</button><button v-if="analysis.lifecycle.status === 'active'" type="button" class="secondary-button" @click="changeAnalysis('archive')">{{ t("Archive") }}</button><button v-else type="button" class="secondary-button" @click="changeAnalysis('restore')">{{ t("Restore") }}</button></div></details>
      <DetailTabs :tabs="[{ id: 'overview', label: t('Overview') }, { id: 'inputs', label: t('Inputs') }, { id: 'result', label: t('Result') }, { id: 'compare', label: t('Compare') }, { id: 'lineage', label: t('Lineage') }]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[{ label: t('Type'), value: analysis.analysis_type }, { label: t('Created'), value: new Date(analysis.created_at).toLocaleString() }, { label: t('Lifecycle'), value: analysis.lifecycle.status }, { label: t('Archive reason'), value: analysis.lifecycle.archive_reason }]" />
      <pre v-else-if="activeTab === 'inputs'" class="history-json">{{ pretty(analysis.inputs) }}</pre>
      <pre v-else-if="activeTab === 'result'" class="history-json">{{ pretty(analysis.result) }}</pre>
      <section v-else-if="activeTab === 'compare'" class="history-compare-panel"><div class="history-lineage-query"><label><span>{{ t('Comparison result ID') }}</span><input v-model="comparisonId" /></label><button type="button" @click="loadComparison">{{ t('Load comparison') }}</button></div><div v-if="comparison" class="history-compare-grid"><article><strong>{{ analysis.analysis_id }}</strong><pre class="history-json">{{ pretty(analysis.result) }}</pre></article><article><strong>{{ comparison.analysis_id }}</strong><pre class="history-json">{{ pretty(comparison.result) }}</pre></article></div></section>
      <section v-else class="history-lineage-handoff"><p>{{ t("Open the lineage center with the related artifact or job identifier.") }}</p><button v-if="analysis.job" type="button" @click="emit('navigate', `/data/jobs/${analysis.job.job_id}`)">{{ t("Open related job") }}</button></section>
    </template>

    <template v-else-if="domain === 'jobs' && !recordId">
      <div class="history-filter-strip"><label><span>{{ t("Status") }}</span><select v-model="jobFilter" @change="load"><option value="">{{ t("All statuses") }}</option><option v-for="state in ['queued','running','succeeded','failed','cancel_requested','cancelled','expired']" :key="state" :value="state">{{ state }}</option></select></label></div>
      <DataTable :columns="[{ key: 'capability', label: t('Capability') }, { key: 'state', label: t('Status') }, { key: 'stage', label: t('Stage') }, { key: 'progress', label: t('Progress') }, { key: 'created', label: t('Created') }]" :items="jobs.map((item) => ({ id: item.job_id, capability: item.capability_id, state: item.state, stage: item.stage, progress: `${item.progress}%`, created: new Date(item.created_at).toLocaleString() }))" :empty-text="t('No job history found.')" @select="emit('navigate', `${listPath}/${$event.id}`)" />
    </template>

    <template v-else-if="domain === 'jobs' && job">
      <RecordHeader :title="job.capability_id" :identifier="job.job_id" :status="job.state" :version="job.stage" />
      <details v-if="canManageJobs.cancel || canManageJobs.retry" class="history-mutation-panel"><summary>{{ t("Job controls") }}</summary><div class="history-mutation-grid"><label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" /></label></div><div class="history-inline-actions"><button v-if="canManageJobs.cancel && ['queued','running'].includes(job.state)" type="button" @click="changeJob('cancel')">{{ t("Request cancellation") }}</button><button v-if="canManageJobs.retry && ['failed','cancelled','expired'].includes(job.state)" type="button" @click="changeJob('retry')">{{ t("Retry as new job") }}</button></div></details>
      <DetailTabs :tabs="[{ id: 'overview', label: t('Overview') }, { id: 'events', label: t('Event timeline'), count: job.events?.length || 0 }, { id: 'input', label: t('Input snapshot') }, { id: 'error', label: t('Error') }]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[{ label: t('Capability'), value: job.capability_id }, { label: t('Status'), value: job.state }, { label: t('Stage'), value: job.stage }, { label: t('Progress'), value: `${job.progress}%` }, { label: t('Created'), value: new Date(job.created_at).toLocaleString() }]" />
      <ol v-else-if="activeTab === 'events'" class="history-event-timeline"><li v-for="event in job.events" :key="event.event_id"><span>{{ new Date(event.created_at).toLocaleString() }}</span><strong>{{ event.from_state || 'created' }} → {{ event.to_state }}</strong><small>{{ event.stage }} · {{ event.progress }}%</small></li></ol>
      <pre v-else-if="activeTab === 'input'" class="history-json">{{ pretty(job.input_snapshot) }}</pre><pre v-else class="history-json">{{ pretty(job.error) }}</pre>
    </template>

    <template v-else-if="domain === 'audit-lineage'">
      <DetailTabs :tabs="[{ id: 'audit', label: t('Audit events') }, { id: 'lineage', label: t('Lineage explorer') }]" :active="auditMode ? 'audit' : 'lineage'" @update:active="emit('navigate', `${listPath}?view=${$event}`)" />
      <template v-if="auditMode && !recordId"><div class="history-filter-strip"><label><span>{{ t("Event type") }}</span><input v-model="auditFilter" type="search" @keyup.enter="load" /></label><button type="button" @click="load">{{ t("Apply filter") }}</button><button v-if="canExportAudit" type="button" class="secondary-button" @click="exportAudit">{{ t("Export CSV") }}</button></div><DataTable :columns="[{ key: 'event', label: t('Event') }, { key: 'actor', label: t('Actor') }, { key: 'targets', label: t('Targets') }, { key: 'created', label: t('Created') }]" :items="audits.map((item) => ({ id: item.event_id, event: item.event_type, actor: item.actor_id, targets: item.target_refs.join(', '), created: new Date(item.created_at).toLocaleString() }))" :empty-text="t('No audit events found.')" @select="emit('navigate', `${listPath}/${$event.id}?view=audit`)" /></template>
      <template v-else-if="audit"><RecordHeader :title="audit.event_type" :identifier="audit.event_id" status="append-only" /><PropertyGrid :items="[{ label: t('Actor'), value: audit.actor_id }, { label: t('Created'), value: new Date(audit.created_at).toLocaleString() }, { label: t('Targets'), value: audit.target_refs.join(', ') }, { label: t('Payload hash'), value: audit.payload_hash, copyable: true }]" /><pre class="history-json">{{ pretty(audit.detail) }}</pre></template>
      <template v-else><div class="history-lineage-query"><label><span>{{ t('Root type') }}</span><select v-model="lineageRootType"><option value="artifact_version">artifact_version</option><option value="job">job</option></select></label><label><span>{{ t('Root ID') }}</span><input v-model="lineageRootId" /></label><button type="button" @click="loadLineage">{{ t('Trace lineage') }}</button></div><template v-if="lineage"><section class="history-lineage-summary"><strong>{{ lineage.nodes.length }}</strong><span>{{ t('nodes') }}</span><strong>{{ lineage.edges.length }}</strong><span>{{ t('relationships') }}</span></section><DataTable :columns="[{ key: 'type', label: t('Type') }, { key: 'label', label: t('Label') }, { key: 'status', label: t('Status') }, { key: 'id', label: 'ID' }]" :items="lineage.nodes" :empty-text="t('No lineage nodes found.')" /><pre class="history-json">{{ pretty(lineage.edges) }}</pre></template></template>
    </template>
  </section>
</template>
