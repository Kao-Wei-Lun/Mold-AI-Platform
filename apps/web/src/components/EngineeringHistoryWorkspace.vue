<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";

import {
  appendManagedCAERun,
  appendManagedProcessRun,
  correctManagedTrial,
  EngineeringDataError,
  fetchCAEHistory,
  fetchCAEStudyDetail,
  fetchTrialCaseDetail,
  fetchTrialHistory,
  transitionCAEStudy,
  transitionTrial,
  updateManagedTrial,
  type ManagedCAEStudy,
  type ManagedCAESummary,
  type ManagedTrial,
  type ManagedTrialSummary,
} from "../api/engineeringData";
import {
  fetchHMIExtractionDetail,
  fetchHMIExtractionHistory,
  hmiResourceUrl,
  reviewHMI,
  type HMIExtraction,
  type HMIExtractionSummary,
} from "../api/hmi";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RecordHeader from "./RecordHeader.vue";

type Domain = "trials" | "cae" | "hmi";

const props = defineProps<{ domain: Domain; path: string; canManage?: boolean }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();
const loading = ref(false);
const error = ref<string | null>(null);
const trials = ref<ManagedTrialSummary[]>([]);
const studies = ref<ManagedCAESummary[]>([]);
const extractions = ref<HMIExtractionSummary[]>([]);
const trial = ref<ManagedTrial | null>(null);
const study = ref<ManagedCAEStudy | null>(null);
const extraction = ref<HMIExtraction | null>(null);
const mutating = ref(false);
const mutationError = ref<string | null>(null);
const mutationNotice = ref<string | null>(null);
const reason = ref("");
const trialForm = reactive({ purpose: "", outcome: "", material_lot: "" });
const processRunForm = reactive({ run_number: 1, cycle_start: 1, cycle_end: 20, result: "pending", parameter_code: "", parameter_value: 0, parameter_unit: "" });
const caeRunForm = reactive({ run_code: "", solver_version: "", metric_code: "", value: 0, unit: "" });
const hmiReviewForm = reactive({ field_id: "", action: "confirm" as "confirm" | "correct" | "reject", value: 0, unit: "", reason: "" });

const location = computed(() => new URL(props.path, window.location.origin));
const recordId = computed(() => location.value.pathname.split("/").filter(Boolean)[2] || "");
const activeTab = computed(() => location.value.searchParams.get("tab") || "overview");
const listPath = computed(() => `/data/${props.domain}`);
const title = computed(() => ({ trials: "Trial & process", cae: "CAE / Moldflow", hmi: "HMI extractions" })[props.domain]);

function pretty(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function setTab(tab: string): void {
  if (!recordId.value) return;
  emit("navigate", `${listPath.value}/${recordId.value}?tab=${tab}`);
}

function mutationMessage(caught: unknown): string {
  if (caught instanceof EngineeringDataError && caught.status === 409) {
    return t("This record changed after loading. Refresh it before saving again.");
  }
  return caught instanceof Error ? caught.message : t("Unable to save historical data.");
}

async function mutate(action: () => Promise<void>, notice: string): Promise<void> {
  if (!reason.value.trim()) {
    mutationError.value = t("A change reason is required.");
    return;
  }
  mutating.value = true;
  mutationError.value = null;
  mutationNotice.value = null;
  try {
    await action();
    reason.value = "";
    mutationNotice.value = t(notice);
  } catch (caught) {
    mutationError.value = mutationMessage(caught);
  } finally {
    mutating.value = false;
  }
}

function saveTrial(): Promise<void> {
  if (!trial.value) return Promise.resolve();
  return mutate(async () => {
    trial.value = await updateManagedTrial(trial.value!, { ...trialForm }, reason.value);
  }, "Trial metadata saved with audit evidence.");
}

function correctTrial(): Promise<void> {
  if (!trial.value) return Promise.resolve();
  const changes = Object.fromEntries(Object.entries(trialForm).filter(([key, value]) => value !== trial.value?.[key as keyof ManagedTrial]));
  return mutate(async () => {
    trial.value = await correctManagedTrial(trial.value!, changes, reason.value);
  }, "Trial correction appended without overwriting the source.");
}

function changeTrialLifecycle(action: "close" | "reopen" | "archive"): Promise<void> {
  if (!trial.value) return Promise.resolve();
  return mutate(async () => { trial.value = await transitionTrial(trial.value!, action, reason.value); }, "Trial lifecycle updated.");
}

function appendProcessRun(): Promise<void> {
  if (!trial.value) return Promise.resolve();
  const parameters = processRunForm.parameter_code ? [{ canonical_code: processRunForm.parameter_code, value: processRunForm.parameter_value, unit: processRunForm.parameter_unit, value_kind: "setpoint" }] : [];
  return mutate(async () => {
    trial.value = await appendManagedProcessRun(trial.value!, { ...processRunForm, parameters, reason: reason.value });
  }, "Process run appended as immutable evidence.");
}

function changeCAELifecycle(action: "archive" | "restore"): Promise<void> {
  if (!study.value) return Promise.resolve();
  return mutate(async () => { study.value = await transitionCAEStudy(study.value!, action, reason.value); }, "CAE lifecycle updated.");
}

function appendCAERun(): Promise<void> {
  if (!study.value) return Promise.resolve();
  return mutate(async () => {
    study.value = await appendManagedCAERun(study.value!, {
      run_code: caeRunForm.run_code,
      solver_version: caeRunForm.solver_version || "unknown",
      results: caeRunForm.metric_code ? [{ metric_code: caeRunForm.metric_code, value: caeRunForm.value, unit: caeRunForm.unit }] : [],
      reason: reason.value,
    });
  }, "CAE run imported as immutable evidence.");
}

function reviewExtractionField(): Promise<void> {
  if (!extraction.value || !hmiReviewForm.field_id) return Promise.resolve();
  return mutate(async () => {
    const decision = { field_id: hmiReviewForm.field_id, action: hmiReviewForm.action, reason: reason.value, ...(hmiReviewForm.action === "correct" ? { value: hmiReviewForm.value, unit: hmiReviewForm.unit } : {}) };
    extraction.value = await reviewHMI(extraction.value!.extraction_id, [decision]);
  }, "HMI review decision appended.");
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  trial.value = null;
  study.value = null;
  extraction.value = null;
  try {
    if (props.domain === "trials") {
      if (recordId.value) {
        trial.value = await fetchTrialCaseDetail(recordId.value);
        trialForm.purpose = trial.value.purpose;
        trialForm.outcome = trial.value.outcome;
        trialForm.material_lot = trial.value.material_lot || "";
      }
      else trials.value = await fetchTrialHistory();
    } else if (props.domain === "cae") {
      if (recordId.value) study.value = await fetchCAEStudyDetail(recordId.value);
      else studies.value = await fetchCAEHistory();
    } else if (recordId.value) {
      extraction.value = await fetchHMIExtractionDetail(recordId.value);
      hmiReviewForm.field_id = extraction.value.fields.find((field) => field.review_status === "needs_review")?.field_id || "";
    } else {
      extractions.value = await fetchHMIExtractionHistory();
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load historical data.");
  } finally {
    loading.value = false;
  }
}

watch(() => [props.domain, recordId.value], load, { immediate: true });
</script>

<template>
  <section class="engineering-history-workspace">
    <div class="history-list-heading">
      <div>
        <p class="eyebrow">{{ t("Historical data") }}</p>
        <h2>{{ t(title) }}</h2>
      </div>
      <div class="history-list-actions">
        <button v-if="recordId" type="button" class="text-button" @click="emit('navigate', listPath)">← {{ t("Back to records") }}</button>
        <button type="button" :disabled="loading" @click="load">{{ t("Refresh data") }}</button>
      </div>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }} <button type="button" @click="load">{{ t("Retry") }}</button></p>
    <section v-else-if="loading" class="workspace-state">{{ t("Loading complete historical record…") }}</section>
    <p v-if="mutationError" class="error-message history-mutation-message" role="alert">{{ mutationError }} <button type="button" @click="load">{{ t("Refresh data") }}</button></p>
    <p v-if="mutationNotice" class="success-message history-mutation-message" role="status">{{ mutationNotice }}</p>

    <template v-else-if="!recordId">
      <DataTable
        v-if="domain === 'trials'"
        :columns="[
          { key: 'code', label: t('Trial code') }, { key: 'mold', label: t('Mold revision') },
          { key: 'machine', label: t('Machine') }, { key: 'material', label: t('Material') },
          { key: 'runs', label: t('Runs') }, { key: 'status', label: t('Status') },
        ]"
        :items="trials.map((item) => ({ id: item.trial_case_id, code: item.case_code, mold: item.mold_revision_ref, machine: item.machine_code, material: item.material_code, runs: item.run_count, status: item.lifecycle_status }))"
        :empty-text="t('No trial history found.')"
        @select="emit('navigate', `${listPath}/${$event.id}`)"
      />
      <DataTable
        v-else-if="domain === 'cae'"
        :columns="[
          { key: 'code', label: t('Study code') }, { key: 'solver', label: t('Solver') },
          { key: 'mold', label: t('Mold revision') }, { key: 'mesh', label: t('Mesh family') },
          { key: 'runs', label: t('Runs') }, { key: 'results', label: t('Results') }, { key: 'status', label: t('Status') },
        ]"
        :items="studies.map((item) => ({ id: item.study_id, code: item.study_code, solver: item.solver_name, mold: item.mold_revision_ref, mesh: item.mesh_family, runs: item.run_count, results: item.result_count, status: item.lifecycle_status }))"
        :empty-text="t('No CAE history found.')"
        @select="emit('navigate', `${listPath}/${$event.id}`)"
      />
      <DataTable
        v-else
        :columns="[
          { key: 'profile', label: t('Profile') }, { key: 'fields', label: t('Fields') },
          { key: 'review', label: t('Review status') }, { key: 'needsReview', label: t('Needs review') },
          { key: 'exports', label: t('Exports') }, { key: 'created', label: t('Created') },
        ]"
        :items="extractions.map((item) => ({ id: item.extraction_id, profile: item.profile, fields: item.field_count, review: item.review_status, needsReview: item.needs_review_count, exports: item.export_count, created: new Date(item.created_at).toLocaleString() }))"
        :empty-text="t('No HMI extraction history found.')"
        @select="emit('navigate', `${listPath}/${$event.id}`)"
      />
    </template>

    <template v-else-if="trial">
      <RecordHeader :title="trial.case_code" :identifier="trial.trial_case_id" :status="trial.lifecycle_status" :version="`row ${trial.row_version}`">
        <template #actions>
          <button v-if="canManage && ['draft', 'reopened'].includes(trial.lifecycle_status)" type="button" @click="changeTrialLifecycle('close')">{{ t("Close") }}</button>
          <button v-if="canManage && trial.lifecycle_status === 'closed'" type="button" @click="changeTrialLifecycle('reopen')">{{ t("Reopen") }}</button>
          <button v-if="canManage && trial.lifecycle_status !== 'archived'" type="button" class="secondary-button" @click="changeTrialLifecycle('archive')">{{ t("Archive") }}</button>
        </template>
      </RecordHeader>
      <details v-if="canManage" class="history-mutation-panel">
        <summary>{{ t(trial.lifecycle_status === 'closed' ? 'Append correction' : 'Edit controlled trial') }}</summary>
        <p class="history-impact">{{ t(trial.lifecycle_status === 'closed' ? 'The source record stays unchanged; this creates an append-only correction.' : 'Saving updates safe metadata and increments row_version.') }}</p>
        <div class="history-mutation-grid">
          <label><span>{{ t("Purpose") }}</span><input v-model="trialForm.purpose" /></label>
          <label><span>{{ t("Outcome") }}</span><input v-model="trialForm.outcome" /></label>
          <label><span>{{ t("Material lot") }}</span><input v-model="trialForm.material_lot" /></label>
          <label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" required /></label>
        </div>
        <button type="button" :disabled="mutating" @click="trial.lifecycle_status === 'closed' ? correctTrial() : saveTrial()">{{ mutating ? t("Saving...") : t("Save controlled change") }}</button>
      </details>
      <DetailTabs :tabs="[
        { id: 'overview', label: t('Overview') }, { id: 'runs', label: t('Process runs'), count: trial.runs?.length || 0 },
        { id: 'corrections', label: t('Corrections'), count: trial.corrections.length }, { id: 'lineage', label: t('Lineage') },
      ]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[
        { label: t('Purpose'), value: trial.purpose }, { label: t('Outcome'), value: trial.outcome },
        { label: t('Mold revision'), value: trial.mold_revision_ref }, { label: t('Machine'), value: trial.machine_code },
        { label: t('Material'), value: `${trial.material_code}${trial.material_lot ? ` · ${trial.material_lot}` : ''}` },
        { label: t('Product type'), value: trial.product_type }, { label: t('Started at'), value: new Date(trial.started_at).toLocaleString() },
        { label: t('Data quality'), value: pretty(trial.data_quality) },
      ]" />
      <div v-else-if="activeTab === 'runs'" class="history-stack">
        <details v-if="canManage && ['draft', 'reopened'].includes(trial.lifecycle_status)" class="history-mutation-panel">
          <summary>{{ t("Append process run") }}</summary>
          <p class="history-impact">{{ t("The new run and child measurements become immutable historical evidence.") }}</p>
          <div class="history-mutation-grid">
            <label><span>{{ t("Run") }}</span><input v-model.number="processRunForm.run_number" type="number" min="1" /></label>
            <label><span>{{ t("Result") }}</span><input v-model="processRunForm.result" /></label>
            <label><span>{{ t("Cycle start") }}</span><input v-model.number="processRunForm.cycle_start" type="number" min="0" /></label>
            <label><span>{{ t("Cycle end") }}</span><input v-model.number="processRunForm.cycle_end" type="number" min="0" /></label>
            <label><span>{{ t("Parameter") }}</span><input v-model="processRunForm.parameter_code" /></label>
            <label><span>{{ t("Value") }}</span><input v-model.number="processRunForm.parameter_value" type="number" step="any" /></label>
            <label><span>{{ t("Unit") }}</span><input v-model="processRunForm.parameter_unit" /></label>
            <label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" required /></label>
          </div>
          <button type="button" :disabled="mutating" @click="appendProcessRun">{{ t("Append immutable run") }}</button>
        </details>
        <article v-for="run in trial.runs || []" :key="run.process_run_id" class="history-detail-card">
          <h3>{{ t("Run") }} {{ run.run_number }}</h3>
          <PropertyGrid :items="[
            { label: t('Cycle range'), value: `${run.cycle_range.start ?? '—'} – ${run.cycle_range.end ?? '—'}` },
            { label: t('Environment'), value: pretty(run.environment) }, { label: t('Result'), value: pretty(run.result) },
          ]" />
          <h4>{{ t("Parameters") }}</h4>
          <DataTable :columns="[{ key: 'code', label: t('Parameter') }, { key: 'value', label: t('Value') }, { key: 'method', label: t('Sampling method') }]" :items="Object.entries(run.parameters).map(([code, item]) => ({ id: code, code, value: `${item.value} ${item.unit}`, method: item.sampling_method }))" />
          <h4>{{ t("Defects") }}</h4>
          <DataTable :columns="[{ key: 'code', label: t('Defect') }, { key: 'severity', label: t('Severity') }, { key: 'location', label: t('Location') }, { key: 'inspection', label: t('Inspection method') }]" :items="run.defects.map((item) => ({ id: item.defect_id, code: item.defect_code, severity: item.severity, location: item.location, inspection: item.inspection_method }))" :empty-text="t('No defects recorded.')" />
          <h4>{{ t("Corrective actions") }}</h4>
          <DataTable :columns="[{ key: 'code', label: t('Action') }, { key: 'description', label: t('Description') }, { key: 'outcome', label: t('Observed outcome') }, { key: 'executed', label: t('Executed') }]" :items="run.corrective_actions.map((item) => ({ id: item.action_id, code: item.action_code, description: item.description, outcome: item.observed_outcome, executed: item.executed ? t('Yes') : t('No') }))" :empty-text="t('No corrective actions recorded.')" />
        </article>
        <p v-if="!trial.runs?.length" class="workspace-state">{{ t("No process runs recorded.") }}</p>
      </div>
      <div v-else-if="activeTab === 'corrections'" class="history-timeline">
        <article v-for="item in trial.corrections" :key="item.correction_id">
          <time>{{ new Date(item.created_at).toLocaleString() }}</time><strong>{{ item.corrected_by }}</strong><p>{{ item.reason }}</p>
          <div class="history-diff"><pre>{{ pretty(item.before_values) }}</pre><span>→</span><pre>{{ pretty(item.after_values) }}</pre></div>
        </article>
        <p v-if="trial.corrections.length === 0" class="workspace-state">{{ t("No corrections recorded.") }}</p>
      </div>
      <pre v-else class="history-json">{{ pretty(trial.provenance) }}</pre>
    </template>

    <template v-else-if="study">
      <RecordHeader :title="study.study_code" :identifier="study.study_id" :status="study.lifecycle_status" :version="`row ${study.row_version}`">
        <template #actions><button v-if="canManage" type="button" @click="changeCAELifecycle(study.lifecycle_status === 'active' ? 'archive' : 'restore')">{{ t(study.lifecycle_status === 'active' ? 'Archive' : 'Restore') }}</button></template>
      </RecordHeader>
      <DetailTabs :tabs="[
        { id: 'overview', label: t('Overview') }, { id: 'runs', label: t('CAE runs'), count: study.runs.length },
        { id: 'quality', label: t('Quality') }, { id: 'lineage', label: t('Lineage') },
      ]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[
        { label: t('Objective'), value: study.objective }, { label: t('Solver'), value: study.solver_name },
        { label: t('Mold revision'), value: study.mold_revision_ref }, { label: t('Material model'), value: study.material_model_code },
        { label: t('Mesh family'), value: study.mesh_family }, { label: t('Owner'), value: study.owner },
      ]" />
      <div v-else-if="activeTab === 'runs'" class="history-stack">
        <details v-if="canManage && study.lifecycle_status === 'active'" class="history-mutation-panel">
          <summary>{{ t("Import new CAE run") }}</summary>
          <p class="history-impact">{{ t("Existing solver results are immutable; this action appends a new run.") }}</p>
          <div class="history-mutation-grid">
            <label><span>{{ t("Run code") }} *</span><input v-model="caeRunForm.run_code" required /></label>
            <label><span>{{ t("Solver version") }}</span><input v-model="caeRunForm.solver_version" /></label>
            <label><span>{{ t("Metric") }}</span><input v-model="caeRunForm.metric_code" /></label>
            <label><span>{{ t("Value") }}</span><input v-model.number="caeRunForm.value" type="number" step="any" /></label>
            <label><span>{{ t("Unit") }}</span><input v-model="caeRunForm.unit" /></label>
            <label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" required /></label>
          </div>
          <button type="button" :disabled="mutating || !caeRunForm.run_code" @click="appendCAERun">{{ t("Import immutable run") }}</button>
        </details>
        <article v-for="run in study.runs" :key="run.run_id" class="history-detail-card">
          <h3>{{ run.run_code }} <span class="status-chip">{{ run.status }}</span></h3>
          <PropertyGrid :items="[
            { label: t('Solver'), value: `${run.solver.name} ${run.solver.version}` }, { label: t('Unit system'), value: run.unit_system },
            { label: t('Mesh'), value: `${run.mesh.family} · ${run.mesh.checksum || run.mesh.artifact_ref}` },
            { label: t('Boundary settings'), value: pretty(run.boundary_settings) }, { label: t('Process settings'), value: pretty(run.process_settings) },
          ]" />
          <DataTable :columns="[
            { key: 'metric', label: t('Metric') }, { key: 'value', label: t('Value') },
            { key: 'quality', label: t('Quality flags') }, { key: 'parser', label: t('Parser') },
          ]" :items="run.results.map((item) => ({ id: item.result_id, metric: item.metric_code, value: `${item.value} ${item.unit}`, quality: item.quality_flags.join(', ') || '—', parser: `${item.parser.name}@${item.parser.version}` }))" :empty-text="t('No CAE results recorded.')" />
        </article>
      </div>
      <PropertyGrid v-else-if="activeTab === 'quality'" :items="[
        { label: t('Study quality'), value: pretty(study.data_quality) },
        ...study.runs.map((run) => ({ label: run.run_code, value: pretty(run.data_quality) })),
      ]" />
      <pre v-else class="history-json">{{ pretty(study.provenance) }}</pre>
    </template>

    <template v-else-if="extraction">
      <RecordHeader :title="extraction.profile" :identifier="extraction.extraction_id" :status="extraction.review_status" :version="extraction.extractor_version" />
      <DetailTabs :tabs="[
        { id: 'overview', label: t('Overview') }, { id: 'fields', label: t('Fields'), count: extraction.fields.length },
        { id: 'decisions', label: t('Review decisions'), count: extraction.fields.reduce((count, field) => count + (field.correction_decisions?.length || 0), 0) },
        { id: 'exports', label: t('Exports'), count: extraction.exports.length }, { id: 'lineage', label: t('Lineage') },
      ]" :active="activeTab" @update:active="setTab" />
      <div v-if="activeTab === 'overview'" class="hmi-history-overview">
        <img :src="hmiResourceUrl(extraction.image_download_url)" :alt="t('Original HMI source')" />
        <PropertyGrid :items="[
          { label: t('Profile'), value: extraction.profile }, { label: t('Profile version ID'), value: extraction.profile_definition_id, copyable: true },
          { label: t('Image size'), value: `${extraction.image_dimensions.width} × ${extraction.image_dimensions.height}` },
          { label: t('Image SHA-256'), value: extraction.image_sha256, copyable: true }, { label: t('Created'), value: new Date(extraction.created_at).toLocaleString() },
          { label: t('Preprocessing'), value: pretty(extraction.preprocessing) },
        ]" />
      </div>
      <div v-else-if="activeTab === 'fields'" class="history-stack">
      <DataTable :columns="[
        { key: 'parameter', label: t('Parameter') }, { key: 'raw', label: t('Raw OCR') }, { key: 'effective', label: t('Effective value') },
        { key: 'confidence', label: t('Confidence') }, { key: 'validation', label: t('Validation') }, { key: 'review', label: t('Review status') },
      ]" :items="extraction.fields.map((item) => ({ id: item.field_id, parameter: item.display_label, raw: item.raw_text, effective: `${item.effective_value ?? '—'} ${item.effective_unit}`, confidence: `${Math.round(item.confidence * 100)}%`, validation: item.validation_status, review: item.review_status }))" />
      <details v-if="canManage && extraction.fields.some((field) => field.review_status === 'needs_review')" class="history-mutation-panel">
        <summary>{{ t("Review extracted field") }}</summary>
        <p class="history-impact">{{ t("Raw OCR remains immutable; the human decision is appended and becomes the effective value.") }}</p>
        <div class="history-mutation-grid">
          <label><span>{{ t("Field") }}</span><select v-model="hmiReviewForm.field_id"><option v-for="field in extraction.fields.filter((item) => item.review_status === 'needs_review')" :key="field.field_id" :value="field.field_id">{{ field.display_label }}</option></select></label>
          <label><span>{{ t("Action") }}</span><select v-model="hmiReviewForm.action"><option value="confirm">{{ t("Confirm") }}</option><option value="correct">{{ t("Correct") }}</option><option value="reject">{{ t("Reject") }}</option></select></label>
          <label v-if="hmiReviewForm.action === 'correct'"><span>{{ t("Value") }}</span><input v-model.number="hmiReviewForm.value" type="number" step="any" /></label>
          <label v-if="hmiReviewForm.action === 'correct'"><span>{{ t("Unit") }}</span><input v-model="hmiReviewForm.unit" /></label>
          <label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" required /></label>
        </div>
        <button type="button" :disabled="mutating || !hmiReviewForm.field_id" @click="reviewExtractionField">{{ t("Append review decision") }}</button>
      </details>
      </div>
      <div v-else-if="activeTab === 'decisions'" class="history-timeline">
        <template v-for="field in extraction.fields" :key="field.field_id">
          <article v-for="decision in field.correction_decisions || []" :key="decision.decision_id">
            <time>{{ new Date(decision.created_at).toLocaleString() }}</time><strong>{{ field.display_label }} · {{ decision.decided_by }}</strong><p>{{ decision.reason || decision.action }}</p>
            <div class="history-diff"><pre>{{ pretty(decision.before_value) }}</pre><span>→</span><pre>{{ pretty(decision.after_value) }}</pre></div>
          </article>
        </template>
        <p v-if="extraction.fields.every((field) => !field.correction_decisions?.length)" class="workspace-state">{{ t("No review decisions recorded.") }}</p>
      </div>
      <div v-else-if="activeTab === 'exports'" class="history-export-list">
        <article v-for="item in extraction.exports" :key="item.export_id">
          <div><strong>{{ item.template_version }}</strong><small>{{ item.artifact_version_id }}</small></div>
          <time>{{ item.created_at ? new Date(item.created_at).toLocaleString() : "—" }}</time>
          <a :href="hmiResourceUrl(item.download_url)" download>{{ t("Download") }}</a>
        </article>
        <p v-if="extraction.exports.length === 0" class="workspace-state">{{ t("No exports recorded.") }}</p>
      </div>
      <PropertyGrid v-else :items="[
        { label: t('Lineage reference'), value: extraction.lineage_ref, copyable: true },
        { label: t('Image artifact version'), value: extraction.image_artifact_version_id, copyable: true },
        { label: t('Profile version ID'), value: extraction.profile_definition_id, copyable: true },
        { label: t('Limitations'), value: extraction.limitations.join(' ') },
      ]" />
    </template>
  </section>
</template>
