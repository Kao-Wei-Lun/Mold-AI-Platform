<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  compareCAERuns,
  fetchCAEFixtureStatus,
  fetchCAEStudies,
  seedCAEFixtures,
  type CAEComparison,
  type CAERun,
  type CAEStudy,
} from "../api/cae";

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
    error.value = caught instanceof Error ? caught.message : "Unable to load CAE studies.";
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
    error.value = caught instanceof Error ? caught.message : "Unable to load CAE fixtures.";
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
    error.value = caught instanceof Error ? caught.message : "CAE comparison failed.";
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
</script>

<template>
  <section id="cae" class="cae-workspace" aria-labelledby="cae-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">CAE / Moldflow</p>
        <h2 id="cae-title">Compare only compatible structured simulation facts</h2>
      </div>
      <span class="demo-label">Synthetic export · No official solver API</span>
    </div>

    <div class="cae-source-bar">
      <div>
        <strong>{{ loadedStudyCount }} canonical CAE studies</strong>
        <span>{{ integrationLevel || "not loaded" }} · source {{ sourceVersion || "n/a" }}</span>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="seeding || loading"
        @click="seedFixtures"
      >
        {{ seeding ? "Loading..." : loadedStudyCount ? "Reload idempotently" : "Load fixtures" }}
      </button>
    </div>

    <form class="cae-compare-form" @submit.prevent="submitComparison">
      <label>
        <span>Baseline study / run</span>
        <select v-model="baselineRunId" required>
          <option v-for="option in runOptions" :key="option.run.run_id" :value="option.run.run_id">
            {{ option.label }} · {{ option.run.solver.version }} · {{ option.run.material_model_code }}
          </option>
        </select>
      </label>
      <span class="comparison-arrow" aria-hidden="true">→</span>
      <label>
        <span>Candidate study / run</span>
        <select v-model="candidateRunId" required>
          <option v-for="option in runOptions" :key="option.run.run_id" :value="option.run.run_id">
            {{ option.label }} · {{ option.run.solver.version }} · {{ option.run.material_model_code }}
          </option>
        </select>
      </label>
      <button
        type="submit"
        :disabled="comparing || !baselineRunId || !candidateRunId || loadedStudyCount === 0"
      >
        {{ comparing ? "Checking..." : "Check compatibility and compare" }}
      </button>
    </form>

    <template v-if="comparison">
      <div class="cae-compatibility" :class="comparison.compatible ? 'compatible' : 'blocked'">
        <div>
          <span>Compatibility gate</span>
          <strong>{{ comparison.compatible ? "Compatible" : "Comparison blocked" }}</strong>
        </div>
        <code>{{ comparison.compatibility_profile_version }}</code>
      </div>

      <section v-if="!comparison.compatible" class="cae-blocked-panel" role="status">
        <h3>No metric delta was calculated</h3>
        <p>Resolve every run-level incompatibility before comparing simulation results.</p>
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
            <span>Comparable metrics</span>
            <strong>{{ comparison.comparison_summary.comparable_metric_count }}</strong>
          </div>
          <div>
            <span>Excluded metrics</span>
            <strong>{{ comparison.comparison_summary.excluded_metric_count }}</strong>
          </div>
          <div>
            <span>Improved indicators</span>
            <strong>{{ comparison.comparison_summary.finding_counts.improved }}</strong>
          </div>
          <div>
            <span>Review required</span>
            <strong>{{ comparison.comparison_summary.finding_counts.changed_review_required }}</strong>
          </div>
        </div>

        <div class="cae-metric-table-wrap">
          <table class="cae-metric-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Baseline</th>
                <th>Candidate</th>
                <th>Delta</th>
                <th>Percent</th>
                <th>Finding</th>
                <th>Evidence</th>
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
                <td><span class="cae-finding" :class="metric.finding">{{ metric.finding }}</span></td>
                <td>
                  <details>
                    <summary>{{ metric.evidence_refs.length }} refs</summary>
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
          <span>Baseline fact</span>
          <strong>{{ comparison.parsed_facts.baseline.study_code }}</strong>
          <code>{{ comparison.parsed_facts.baseline.run_id }}</code>
        </div>
        <div>
          <span>Candidate fact</span>
          <strong>{{ comparison.parsed_facts.candidate.study_code }}</strong>
          <code>{{ comparison.parsed_facts.candidate.run_id }}</code>
        </div>
        <div>
          <span>Comparison lineage</span>
          <strong>{{ comparison.comparison_id }}</strong>
          <code>{{ comparison.lineage.comparison_ref }}</code>
        </div>
      </div>

      <p class="limitation-note">{{ comparison.limitations.join(" ") }}</p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
