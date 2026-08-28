<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { AssistantContext } from "../api/assistant";

import {
  compareCAERuns,
  fetchCAEFixtureStatus,
  fetchCAEStudies,
  seedCAEFixtures,
  type CAEComparison,
  type CAERun,
  type CAEStudy,
} from "../api/cae";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";

const { locale, t } = useI18n();

const emit = defineEmits<{ contextChange: [context: AssistantContext] }>();

const studies = ref<CAEStudy[]>([]);
const loadedStudyCount = ref(0);
const sourceVersion = ref("");
const integrationLevel = ref("");
const baselineRunId = ref("");
const candidateRunId = ref("");
const comparison = ref<CAEComparison | null>(null);
const loading = ref(false);
const seeding = ref(false);
const comparing = ref(false);
const error = ref<string | null>(null);

const runOptions = computed(() =>
  studies.value.flatMap((study) =>
    study.runs.map((run) => ({
      study,
      run,
      label: `${study.study_code} / ${run.run_code}`,
    })),
  ),
);
const missingComparisonFields = computed(
  () => Number(!baselineRunId.value) + Number(!candidateRunId.value),
);

function findRun(studyCode: string): CAERun | undefined {
  return studies.value.find((study) => study.study_code === studyCode)?.runs[0];
}

function setDefaultRuns(): void {
  if (!baselineRunId.value) {
    baselineRunId.value = findRun("CAE-DEMO-BASELINE")?.run_id || runOptions.value[0]?.run.run_id || "";
  }
  if (!candidateRunId.value) {
    candidateRunId.value =
      findRun("CAE-DEMO-CANDIDATE")?.run_id || runOptions.value[1]?.run.run_id || "";
  }
}

async function loadWorkspace(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [fixtureStatus, availableStudies] = await Promise.all([
      fetchCAEFixtureStatus(),
      fetchCAEStudies(),
    ]);
    loadedStudyCount.value = fixtureStatus.loaded_study_count;
    sourceVersion.value = fixtureStatus.connector.source_version;
    integrationLevel.value = fixtureStatus.connector.integration_level;
    studies.value = availableStudies;
    setDefaultRuns();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load CAE studies.");
  } finally {
    loading.value = false;
  }
}

async function seedFixtures(): Promise<void> {
  seeding.value = true;
  error.value = null;
  try {
    await seedCAEFixtures();
    await loadWorkspace();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load CAE fixtures.");
  } finally {
    seeding.value = false;
  }
}

async function submitComparison(): Promise<void> {
  if (!baselineRunId.value || !candidateRunId.value) return;
  comparing.value = true;
  error.value = null;
  comparison.value = null;
  try {
    comparison.value = await compareCAERuns(baselineRunId.value, candidateRunId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("CAE comparison failed.");
  } finally {
    comparing.value = false;
  }
}

function deltaText(delta: number, unit: string): string {
  const prefix = delta > 0 ? "+" : "";
  return `${prefix}${delta.toFixed(3)} ${unit}`;
}

function percentText(value: number | null): string {
  if (value === null) return "n/a";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

onMounted(loadWorkspace);
watch(
  () => comparison.value?.comparison_id,
  () => {
    if (!comparison.value?.comparison_id) return;
    emit("contextChange", {
      context_version: "1.0",
      page: "cae",
      ui_locale: locale.value,
      ...(comparison.value?.comparison_id
        ? { cae_comparison_id: comparison.value.comparison_id }
        : {}),
    });
  },
);
</script>

<template>
  <section id="cae" class="cae-workspace" aria-labelledby="cae-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">CAE / Moldflow</p>
        <h2 id="cae-title">{{ t("Compare only compatible structured simulation facts") }}</h2>
      </div>
      <span class="demo-label">{{ t("Synthetic export · No official solver API") }}</span>
    </div>

    <div class="cae-source-bar">
      <div>
        <strong>{{ t("{count} canonical CAE studies", { count: loadedStudyCount }) }}</strong>
        <span>{{ integrationLevel || t("not loaded") }} · {{ t("source {version}", { version: sourceVersion || "n/a" }) }}</span>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="seeding || loading"
        @click="seedFixtures"
      >
        {{ seeding ? t("Loading...") : loadedStudyCount ? t("Reload idempotently") : t("Load fixtures") }}
      </button>
    </div>

    <form class="cae-compare-form" @submit.prevent="submitComparison">
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Baseline study / run')" required :helper="t('Select the reference run for all metric deltas.')">
        <select :id="fieldId" v-model="baselineRunId" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option v-for="option in runOptions" :key="option.run.run_id" :value="option.run.run_id">
            {{ option.label }} · {{ option.run.solver.version }} · {{ option.run.material_model_code }}
          </option>
        </select>
      </FormField>
      <span class="comparison-arrow" aria-hidden="true">→</span>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Candidate study / run')" required :helper="t('Select the run to compare against the baseline.')">
        <select :id="fieldId" v-model="candidateRunId" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option v-for="option in runOptions" :key="option.run.run_id" :value="option.run.run_id">
            {{ option.label }} · {{ option.run.solver.version }} · {{ option.run.material_model_code }}
          </option>
        </select>
      </FormField>
      <p v-if="missingComparisonFields" class="form-validation-summary" aria-live="polite">
        {{ t("Required fields remaining: {count}", { count: missingComparisonFields }) }}
      </p>
      <button
        type="submit"
        :disabled="comparing || !baselineRunId || !candidateRunId || loadedStudyCount === 0"
      >
        {{ comparing ? t("Checking...") : t("Check compatibility and compare") }}
      </button>
    </form>

    <template v-if="comparison">
      <div class="cae-compatibility" :class="comparison.compatible ? 'compatible' : 'blocked'">
        <div>
          <span>{{ t("Compatibility gate") }}</span>
          <strong>{{ comparison.compatible ? t("Compatible") : t("Comparison blocked") }}</strong>
        </div>
        <code>{{ comparison.compatibility_profile_version }}</code>
      </div>

      <section v-if="!comparison.compatible" class="cae-blocked-panel" role="status">
        <h3>{{ t("No metric delta was calculated") }}</h3>
        <p>{{ t("Resolve every run-level incompatibility before comparing simulation results.") }}</p>
        <ul>
          <li v-for="item in comparison.incompatibilities" :key="item.code">
            <strong>{{ item.field.replaceAll("_", " ") }}</strong>
            <span>{{ item.baseline }} → {{ item.candidate }}</span>
            <code>{{ item.code }}</code>
          </li>
        </ul>
      </section>

      <template v-else>
        <div class="cae-summary-grid">
          <div>
            <span>{{ t("Comparable metrics") }}</span>
            <strong>{{ comparison.comparison_summary.comparable_metric_count }}</strong>
          </div>
          <div>
            <span>{{ t("Excluded metrics") }}</span>
            <strong>{{ comparison.comparison_summary.excluded_metric_count }}</strong>
          </div>
          <div>
            <span>{{ t("Improved indicators") }}</span>
            <strong>{{ comparison.comparison_summary.finding_counts.improved }}</strong>
          </div>
          <div>
            <span>{{ t("Review required") }}</span>
            <strong>{{ comparison.comparison_summary.finding_counts.changed_review_required }}</strong>
          </div>
        </div>

        <div class="cae-metric-table-wrap">
          <table class="cae-metric-table">
            <thead>
              <tr>
                <th>{{ t("Metric") }}</th>
                <th>{{ t("Baseline") }}</th>
                <th>{{ t("Candidate") }}</th>
                <th>{{ t("Delta") }}</th>
                <th>{{ t("Percent") }}</th>
                <th>{{ t("Finding") }}</th>
                <th>{{ t("Evidence") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="metric in comparison.metric_comparisons" :key="metric.metric_code">
                <td>
                  <strong>{{ metric.metric_label }}</strong>
                  <code>{{ metric.metric_code }}</code>
                </td>
                <td>{{ metric.baseline.value }} {{ metric.unit }}</td>
                <td>{{ metric.candidate.value }} {{ metric.unit }}</td>
                <td>{{ deltaText(metric.delta, metric.unit) }}</td>
                <td>{{ percentText(metric.percent_delta) }}</td>
                <td><span class="cae-finding" :class="metric.finding">{{ t(metric.finding) }}</span></td>
                <td>
                  <details>
                    <summary>{{ t("{count} refs", { count: metric.evidence_refs.length }) }}</summary>
                    <code v-for="evidence in metric.evidence_refs" :key="evidence">{{ evidence }}</code>
                  </details>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <div class="cae-lineage">
        <div>
          <span>{{ t("Baseline fact") }}</span>
          <strong>{{ comparison.parsed_facts.baseline.study_code }}</strong>
          <code>{{ comparison.parsed_facts.baseline.run_id }}</code>
        </div>
        <div>
          <span>{{ t("Candidate fact") }}</span>
          <strong>{{ comparison.parsed_facts.candidate.study_code }}</strong>
          <code>{{ comparison.parsed_facts.candidate.run_id }}</code>
        </div>
        <div>
          <span>{{ t("Comparison lineage") }}</span>
          <strong>{{ comparison.comparison_id }}</strong>
          <code>{{ comparison.lineage.comparison_ref }}</code>
        </div>
      </div>

      <p class="limitation-note">{{ comparison.limitations.join(" ") }}</p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
