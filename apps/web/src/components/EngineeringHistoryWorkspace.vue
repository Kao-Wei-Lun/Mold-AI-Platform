<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  fetchCAEHistory,
  fetchCAEStudyDetail,
  fetchTrialCaseDetail,
  fetchTrialHistory,
  type ManagedCAEStudy,
  type ManagedCAESummary,
  type ManagedTrial,
  type ManagedTrialSummary,
} from "../api/engineeringData";
import {
  fetchHMIExtractionDetail,
  fetchHMIExtractionHistory,
  hmiResourceUrl,
  type HMIExtraction,
  type HMIExtractionSummary,
} from "../api/hmi";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RecordHeader from "./RecordHeader.vue";

type Domain = "trials" | "cae" | "hmi";

const props = defineProps<{ domain: Domain; path: string }>();
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

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  trial.value = null;
  study.value = null;
  extraction.value = null;
  try {
    if (props.domain === "trials") {
      if (recordId.value) trial.value = await fetchTrialCaseDetail(recordId.value);
      else trials.value = await fetchTrialHistory();
    } else if (props.domain === "cae") {
      if (recordId.value) study.value = await fetchCAEStudyDetail(recordId.value);
      else studies.value = await fetchCAEHistory();
    } else if (recordId.value) {
      extraction.value = await fetchHMIExtractionDetail(recordId.value);
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
      <RecordHeader :title="trial.case_code" :identifier="trial.trial_case_id" :status="trial.lifecycle_status" :version="`row ${trial.row_version}`" />
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
      <RecordHeader :title="study.study_code" :identifier="study.study_id" :status="study.lifecycle_status" :version="`row ${study.row_version}`" />
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
      <DataTable v-else-if="activeTab === 'fields'" :columns="[
        { key: 'parameter', label: t('Parameter') }, { key: 'raw', label: t('Raw OCR') }, { key: 'effective', label: t('Effective value') },
        { key: 'confidence', label: t('Confidence') }, { key: 'validation', label: t('Validation') }, { key: 'review', label: t('Review status') },
      ]" :items="extraction.fields.map((item) => ({ id: item.field_id, parameter: item.display_label, raw: item.raw_text, effective: `${item.effective_value ?? '—'} ${item.effective_unit}`, confidence: `${Math.round(item.confidence * 100)}%`, validation: item.validation_status, review: item.review_status }))" />
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
