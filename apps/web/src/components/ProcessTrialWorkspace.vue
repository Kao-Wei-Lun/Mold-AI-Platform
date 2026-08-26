<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  fetchProcessFixtureStatus,
  fetchTrialCases,
  searchProcessCases,
  seedProcessFixtures,
  type ControlledTrialStep,
  type Measurement,
  type ProcessMatch,
  type ProcessSearchResult,
  type TrialCase,
} from "../api/processTrial";

const loadedCaseCount = ref(0);
const sourceVersion = ref("");
const cases = ref<TrialCase[]>([]);
const loading = ref(false);
const seeding = ref(false);
const searching = ref(false);
const error = ref<string | null>(null);
const result = ref<ProcessSearchResult | null>(null);
const selected = ref<ProcessMatch | null>(null);

const defectCode = ref("short_shot");
const materialCode = ref("PA6-GF30");
const machineCode = ref("IM-180T");
const productType = ref("connector_housing");
const location = ref("far_flow_end");
const injectionPressure = ref<number | null>(84);
const injectionSpeed = ref<number | null>(43);
const meltTemperature = ref<number | null>(279);
const topK = ref(5);

const recommendation = computed(() => result.value?.recommendation || null);

async function loadWorkspace(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [status, trialCases] = await Promise.all([
      fetchProcessFixtureStatus(),
      fetchTrialCases(),
    ]);
    loadedCaseCount.value = status.loaded_case_count;
    sourceVersion.value = status.connector.source_version;
    cases.value = trialCases;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Unable to load Process/Trial data.";
  } finally {
    loading.value = false;
  }
}

async function seedFixtures(): Promise<void> {
  seeding.value = true;
  error.value = null;
  try {
    await seedProcessFixtures();
    await loadWorkspace();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Unable to load synthetic fixtures.";
  } finally {
    seeding.value = false;
  }
}

async function submitSearch(): Promise<void> {
  searching.value = true;
  error.value = null;
  result.value = null;
  selected.value = null;
  try {
    result.value = await searchProcessCases({
      defectCode: defectCode.value,
      materialCode: materialCode.value,
      machineCode: machineCode.value,
      productType: productType.value,
      location: location.value,
      injectionPressure: injectionPressure.value,
      injectionSpeed: injectionSpeed.value,
      meltTemperature: meltTemperature.value,
      topK: topK.value,
    });
    selected.value = result.value.results[0] || null;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Process case search failed.";
  } finally {
    searching.value = false;
  }
}

function measurementText(values: Record<string, Measurement>): string {
  return Object.entries(values)
    .map(([code, measurement]) => `${code.replaceAll("_", " ")}: ${measurement.value} ${measurement.unit}`)
    .join(" · ");
}

function scoreLabel(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function stepRange(step: ControlledTrialStep): string {
  return `${measurementText(step.historical_before)} → ${measurementText(step.historical_after)}`;
}

onMounted(loadWorkspace);
</script>

<template>
  <section class="process-workspace" aria-labelledby="process-trial-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Process / Trial</p>
        <h2 id="process-trial-title">Compare trial evidence before changing a process</h2>
      </div>
      <span class="demo-label">Synthetic evidence · No machine write</span>
    </div>

    <div class="process-source-bar">
      <div>
        <strong>{{ loadedCaseCount }} canonical trial cases</strong>
        <span>Connector: synthetic-process-trial · {{ sourceVersion || "not loaded" }}</span>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="seeding || loading"
        @click="seedFixtures"
      >
        {{ seeding ? "Loading..." : loadedCaseCount ? "Reload idempotently" : "Load fixtures" }}
      </button>
    </div>

    <form class="process-query-form" @submit.prevent="submitSearch">
      <label>
        <span>Defect</span>
        <select v-model="defectCode">
          <option value="short_shot">Short shot</option>
          <option value="sink_mark">Sink mark</option>
          <option value="warpage">Warpage</option>
          <option value="flash">Flash</option>
        </select>
      </label>
      <label>
        <span>Material</span>
        <select v-model="materialCode">
          <option value="">Not provided — abstain</option>
          <option value="PA6-GF30">PA6-GF30</option>
          <option value="ABS-GENERAL">ABS-GENERAL</option>
          <option value="PP-HOMO">PP-HOMO</option>
        </select>
      </label>
      <label>
        <span>Machine</span>
        <select v-model="machineCode">
          <option value="">Not provided — no ranges</option>
          <option value="IM-120T">IM-120T</option>
          <option value="IM-180T">IM-180T</option>
          <option value="IM-220T">IM-220T</option>
        </select>
      </label>
      <label>
        <span>Product type</span>
        <select v-model="productType">
          <option value="">Any</option>
          <option value="connector_housing">Connector housing</option>
          <option value="electronics_cover">Electronics cover</option>
          <option value="thin_wall_tray">Thin-wall tray</option>
        </select>
      </label>
      <label>
        <span>Location</span>
        <input v-model="location" type="text" maxlength="128" />
      </label>
      <label>
        <span>Injection pressure (MPa)</span>
        <input v-model.number="injectionPressure" type="number" min="0" max="500" step="0.1" />
      </label>
      <label>
        <span>Injection speed (mm/s)</span>
        <input v-model.number="injectionSpeed" type="number" min="0" max="600" step="0.1" />
      </label>
      <label>
        <span>Melt temperature (°C)</span>
        <input v-model.number="meltTemperature" type="number" min="0" max="500" step="0.1" />
      </label>
      <label>
        <span>Top K</span>
        <input v-model.number="topK" type="number" min="1" max="10" />
      </label>
      <button type="submit" :disabled="searching || loadedCaseCount === 0">
        {{ searching ? "Comparing..." : "Find governed cases" }}
      </button>
    </form>

    <p v-if="cases.length" class="process-catalog-note">
      Loaded cases cover {{ [...new Set(cases.map((item) => item.material_code))].join(", ") }}.
      Source records remain clearly marked synthetic.
    </p>

    <div v-if="result" class="process-results">
      <div class="process-result-summary">
        <div>
          <span>Search</span>
          <code>{{ result.search_id }}</code>
        </div>
        <div>
          <span>Scoring profile</span>
          <strong>{{ result.scoring_profile_version }}</strong>
        </div>
        <div>
          <span>Matches</span>
          <strong>{{ result.result_count }}</strong>
        </div>
      </div>

      <div v-if="result.results.length" class="process-match-layout">
        <ol class="process-match-list">
          <li v-for="match in result.results" :key="match.trial_case_id">
            <button
              type="button"
              :class="{ selected: selected?.trial_case_id === match.trial_case_id }"
              @click="selected = match"
            >
              <span>#{{ match.rank }}</span>
              <div>
                <strong>{{ match.case_code }}</strong>
                <small>{{ match.material_code }} · {{ match.machine_code }} · {{ match.outcome }}</small>
              </div>
              <b>{{ scoreLabel(match.score) }}</b>
            </button>
          </li>
        </ol>

        <article v-if="selected" class="process-match-detail">
          <div class="finding-heading">
            <div>
              <p class="eyebrow">Selected evidence</p>
              <h3>{{ selected.case_code }}</h3>
            </div>
            <span>{{ scoreLabel(selected.score) }}</span>
          </div>
          <div class="process-score-grid">
            <div v-for="(score, lane) in selected.score_breakdown" :key="lane">
              <span>{{ String(lane).replaceAll("_", " ") }}</span>
              <strong>{{ scoreLabel(score) }}</strong>
            </div>
          </div>
          <div class="process-evidence-columns">
            <div>
              <h4>Similar factors</h4>
              <ul>
                <li v-for="(item, index) in selected.similarities" :key="index">
                  {{ String(item.factor).replaceAll("_", " ") }}
                </li>
              </ul>
            </div>
            <div>
              <h4>Different factors</h4>
              <ul>
                <li v-for="(item, index) in selected.differences" :key="index">
                  {{ String(item.factor).replaceAll("_", " ") }}
                </li>
              </ul>
            </div>
          </div>
          <div v-if="selected.corrective_action" class="historical-action">
            <span>Historical action · {{ selected.outcome }}</span>
            <strong>{{ selected.corrective_action.description }}</strong>
            <p>
              {{ measurementText(selected.corrective_action.before_values) }} →
              {{ measurementText(selected.corrective_action.after_values) }}
            </p>
            <small>Evidence: {{ selected.evidence_refs.join(" · ") }}</small>
          </div>
        </article>
      </div>

      <section
        v-if="recommendation"
        class="controlled-recommendation"
        :class="{ abstained: recommendation.abstained }"
      >
        <div>
          <p class="eyebrow">Controlled recommendation</p>
          <h3>{{ recommendation.abstained ? "Recommendation withheld" : "Engineer review required" }}</h3>
          <p>{{ recommendation.message }}</p>
        </div>
        <article
          v-for="step in recommendation.controlled_trial_steps"
          :key="step.source_case_code + step.action_code"
          class="trial-step"
        >
          <span>Step {{ step.rank }} · {{ step.source_case_code }}</span>
          <strong>{{ step.instruction }}</strong>
          <code>{{ stepRange(step) }}</code>
          <p>{{ step.expected_effect }}</p>
          <small>Stop condition: {{ step.stop_condition }}</small>
          <b>Approval required · Never auto-apply</b>
        </article>
      </section>

      <p class="limitation-note">{{ result.limitations.join(" ") }}</p>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
