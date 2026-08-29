<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { AssistantContext } from "../api/assistant";
import { emptyMasterDataOptions, type MasterDataOption, type MasterDataOptions } from "../api/masterData";

import {
  fetchProcessFixtureStatus,
  fetchProcessSearch,
  fetchTrialCases,
  searchProcessCases,
  seedProcessFixtures,
  type ControlledTrialStep,
  type Measurement,
  type ProcessMatch,
  type ProcessSearchResult,
  type TrialCase,
} from "../api/processTrial";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const { locale, t } = useI18n();

const props = withDefaults(defineProps<{
  deepLink?: DeepLinkContext | null;
  masterDataOptions?: MasterDataOptions;
  masterDataLoading?: boolean;
  masterDataError?: string | null;
}>(), {
  masterDataOptions: emptyMasterDataOptions,
  masterDataLoading: false,
  masterDataError: null,
});
const emit = defineEmits<{
  contextChange: [context: AssistantContext];
  retryMasterData: [];
}>();

const loadedCaseCount = ref(0);
const sourceVersion = ref("");
const cases = ref<TrialCase[]>([]);
const loading = ref(false);
const seeding = ref(false);
const searching = ref(false);
const error = ref<string | null>(null);
const result = ref<ProcessSearchResult | null>(null);
const selected = ref<ProcessMatch | null>(null);
const submitAttempted = ref(false);

const defectCode = ref("");
const materialCode = ref("");
const machineCode = ref("");
const productType = ref("");
const location = ref("");
const injectionPressure = ref<number | null>(null);
const injectionSpeed = ref<number | null>(null);
const meltTemperature = ref<number | null>(null);
const topK = ref(5);

function optionLabel(option: MasterDataOption): string {
  return locale.value === "zh-TW" ? option.name_zh_tw : option.name_en;
}

function demoOption(kind: keyof MasterDataOptions, preferred: string): string {
  const choices = props.masterDataOptions[kind];
  return choices.find((choice) => choice.code === preferred)?.code || choices[0]?.code || preferred;
}

const recommendation = computed(() => result.value?.recommendation || null);
const missingQueryFields = computed(
  () => Number(!defectCode.value) + Number(!materialCode.value),
);
const defectError = computed(() =>
  submitAttempted.value && !defectCode.value ? t("Select a defect.") : "",
);
const materialError = computed(() =>
  submitAttempted.value && !materialCode.value ? t("Select a material.") : "",
);

function useExplicitDemoInputs(): void {
  defectCode.value = demoOption("defect", "short_shot");
  materialCode.value = demoOption("material", "PA6-GF30");
  machineCode.value = demoOption("machine", "IM-180T");
  productType.value = demoOption("product_type", "connector_housing");
  location.value = demoOption("location", "far_flow_end");
  injectionPressure.value = 84;
  injectionSpeed.value = 43;
  meltTemperature.value = 279;
}

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
    error.value = caught instanceof Error ? caught.message : t("Unable to load Process/Trial data.");
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
    pushToast(t("Trial data loaded."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load synthetic fixtures.");
    pushToast(error.value, "error");
  } finally {
    seeding.value = false;
  }
}

async function submitSearch(): Promise<void> {
  submitAttempted.value = true;
  if (missingQueryFields.value) return;
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
    submitAttempted.value = false;
    pushToast(t("Trial comparison completed."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Process case search failed.");
    pushToast(error.value, "error");
  } finally {
    searching.value = false;
  }
}

async function loadDeepLink(): Promise<void> {
  if (props.deepLink?.target !== "process_trial") return;
  error.value = null;
  try {
    result.value = await fetchProcessSearch(props.deepLink.refs.process_search_id);
    const caseId = props.deepLink.refs.case_id;
    selected.value = caseId
      ? result.value.results.find((item) => item.trial_case_id === caseId) || null
      : result.value.results[0] || null;
    if (caseId && !selected.value) {
      error.value = t("The linked case does not belong to this Process/Trial search.");
    }
  } catch {
    error.value = t("The linked Process/Trial result is unavailable or not authorized.");
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
watch(
  () => [
    props.deepLink?.target,
    props.deepLink?.refs.process_search_id,
    props.deepLink?.refs.case_id,
  ],
  loadDeepLink,
  { immediate: true },
);
watch(
  () => [result.value?.search_id, selected.value?.trial_case_id],
  () => {
    if (!result.value?.search_id) return;
    emit("contextChange", {
      context_version: "1.0",
      page: "process_trial",
      ui_locale: locale.value,
      ...(result.value?.search_id ? { process_search_id: result.value.search_id } : {}),
    });
  },
);
</script>

<template>
  <section id="process-trial" class="process-workspace" aria-labelledby="process-trial-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Process / Trial</p>
        <h2 id="process-trial-title">{{ t("Compare trial evidence before changing a process") }}</h2>
      </div>
      <span class="demo-label">{{ t("Synthetic evidence · No machine write") }}</span>
    </div>

    <div class="process-source-bar">
      <div>
        <strong>{{ t("{count} canonical trial cases", { count: loadedCaseCount }) }}</strong>
        <span>{{ t("Connector: synthetic-process-trial · {version}", { version: sourceVersion || t("not loaded") }) }}</span>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="seeding || loading"
        :aria-busy="seeding"
        @click="seedFixtures"
      >
        {{ seeding ? t("Loading...") : loadedCaseCount ? t("Reload Demo data") : t("Load fixtures") }}
      </button>
    </div>

    <WorkspaceEmptyState
      v-if="!loading && loadedCaseCount === 0"
      :eyebrow="t('Demo data required')"
      :title="t('Load the governed trial catalog first')"
      :message="t('Synthetic fixtures provide the bounded cases, provenance and scoring evidence required for this Demo search.')"
      :action-label="t('Load trial fixtures')"
      @action="seedFixtures"
    />

    <form class="process-query-form" @submit.prevent="submitSearch">
      <div v-if="masterDataError" class="master-data-error form-wide" role="alert">
        <span>{{ t("Governed choices are unavailable: {message}", { message: masterDataError }) }}</span>
        <button type="button" class="text-button" @click="emit('retryMasterData')">{{ t("Retry") }}</button>
      </div>
      <div class="form-wide demo-input-notice">
        <p>{{ t("Inputs are empty by default so the platform never presents Demo values as user context.") }}</p>
        <button type="button" class="secondary-button" @click="useExplicitDemoInputs">
          {{ t("Use explicit Demo inputs") }}
        </button>
      </div>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Defect')" required :error="defectError">
        <select :id="fieldId" v-model="defectCode" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Select a defect") }}</option>
          <option v-for="option in masterDataOptions.defect" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Material')" required :error="materialError">
        <select :id="fieldId" v-model="materialCode" required :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Not provided — abstain") }}</option>
          <option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Machine')">
        <select :id="fieldId" v-model="machineCode" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Not provided — no ranges") }}</option>
          <option v-for="option in masterDataOptions.machine" :key="option.id" :value="option.code">{{ optionLabel(option) }} · {{ option.code }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Product type')">
        <select :id="fieldId" v-model="productType" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Any") }}</option>
          <option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Location')">
        <select :id="fieldId" v-model="location" :aria-describedby="describedBy" :aria-invalid="invalid">
          <option value="">{{ t("Any location") }}</option>
          <option v-for="option in masterDataOptions.location" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option>
        </select>
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Injection pressure (MPa)')" :helper="t('Allowed range: 0–500 MPa.')">
        <input :id="fieldId" v-model.number="injectionPressure" type="number" min="0" max="500" step="0.1" :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Injection speed (mm/s)')" :helper="t('Allowed range: 0–600 mm/s.')">
        <input :id="fieldId" v-model.number="injectionSpeed" type="number" min="0" max="600" step="0.1" :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Melt temperature (°C)')" :helper="t('Allowed range: 0–500 °C.')">
        <input :id="fieldId" v-model.number="meltTemperature" type="number" min="0" max="500" step="0.1" :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Maximum results')" required :helper="t('Choose between 1 and 10 governed cases.')">
        <input :id="fieldId" v-model.number="topK" type="number" min="1" max="10" required :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <p v-if="missingQueryFields" class="form-validation-summary" aria-live="polite">
        {{ t("Required fields remaining: {count}", { count: missingQueryFields }) }}
      </p>
      <button
        type="submit"
        :disabled="searching || loadedCaseCount === 0 || !defectCode || !materialCode"
        :aria-busy="searching"
      >
        {{ searching ? t("Comparing...") : t("Find governed cases") }}
      </button>
    </form>

    <p v-if="cases.length" class="process-catalog-note">
      {{ t("Loaded cases cover {materials}. Source records remain clearly marked synthetic.", { materials: [...new Set(cases.map((item) => item.material_code))].join(", ") }) }}
    </p>

    <div v-if="result" class="process-results">
      <div class="process-result-summary">
        <div>
          <span>{{ t("Search") }}</span>
          <code>{{ result.search_id }}</code>
        </div>
        <div>
          <span>{{ t("Scoring profile") }}</span>
          <strong>{{ result.scoring_profile_version }}</strong>
        </div>
        <div>
          <span>{{ t("Matches") }}</span>
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
              <p class="eyebrow">{{ t("Selected evidence") }}</p>
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
              <h4>{{ t("Similar factors") }}</h4>
              <ul>
                <li v-for="(item, index) in selected.similarities" :key="index">
                  {{ String(item.factor).replaceAll("_", " ") }}
                </li>
              </ul>
            </div>
            <div>
              <h4>{{ t("Different factors") }}</h4>
              <ul>
                <li v-for="(item, index) in selected.differences" :key="index">
                  {{ String(item.factor).replaceAll("_", " ") }}
                </li>
              </ul>
            </div>
          </div>
          <div v-if="selected.corrective_action" class="historical-action">
            <span>{{ t("Historical action · {outcome}", { outcome: selected.outcome }) }}</span>
            <strong>{{ selected.corrective_action.description }}</strong>
            <p>
              {{ measurementText(selected.corrective_action.before_values) }} →
              {{ measurementText(selected.corrective_action.after_values) }}
            </p>
            <small>{{ t("Evidence: {refs}", { refs: selected.evidence_refs.join(" · ") }) }}</small>
          </div>
        </article>
      </div>

      <section
        v-if="recommendation"
        class="controlled-recommendation"
        :class="{ abstained: recommendation.abstained }"
      >
        <div>
          <p class="eyebrow">{{ t("Controlled recommendation") }}</p>
          <h3>{{ recommendation.abstained ? t("Recommendation withheld") : t("Engineer review required") }}</h3>
          <p>{{ recommendation.message }}</p>
        </div>
        <article
          v-for="step in recommendation.controlled_trial_steps"
          :key="step.source_case_code + step.action_code"
          class="trial-step"
        >
          <span>{{ t("Step {rank} · {code}", { rank: step.rank, code: step.source_case_code }) }}</span>
          <strong>{{ step.instruction }}</strong>
          <code>{{ stepRange(step) }}</code>
          <p>{{ step.expected_effect }}</p>
          <small>{{ t("Stop condition: {condition}", { condition: step.stop_condition }) }}</small>
          <b>{{ t("Approval required · Never auto-apply") }}</b>
        </article>
      </section>

      <p class="limitation-note">{{ result.limitations.join(" ") }}</p>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
