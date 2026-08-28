<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";

import type { CADModelResult } from "../api/cad";
import type { AssistantContext } from "../api/assistant";
import {
  createDesignReview,
  createFindingDecision,
  fetchDesignReview,
  fetchDesignReviewJob,
  type DesignReviewJob,
  type ReviewFinding,
} from "../api/designReview";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";

const { locale, t } = useI18n();

const props = defineProps<{ query: CADModelResult | null; deepLink?: DeepLinkContext | null }>();
const emit = defineEmits<{ contextChange: [context: AssistantContext] }>();
const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));

const nominalWall = ref("");
const maximumRib = ref("");
const minimumDraft = ref("");
const job = ref<DesignReviewJob | null>(null);
const selectedFinding = ref<ReviewFinding | null>(null);
const submitting = ref(false);
const error = ref<string | null>(null);
const decisionChoice = ref<"accepted" | "rejected" | "waived">("accepted");
const decisionReason = ref("");
const decisionApprover = ref("");
const savingDecision = ref(false);
let pollTimer: number | null = null;

const terminal = computed(() =>
  ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""),
);
const result = computed(() => job.value?.result || null);

function numericContext(): Record<string, number> {
  const values: Record<string, number> = {};
  if (nominalWall.value !== "") values.nominal_wall_thickness_mm = Number(nominalWall.value);
  if (maximumRib.value !== "") values.max_rib_thickness_mm = Number(maximumRib.value);
  if (minimumDraft.value !== "") values.minimum_draft_angle_deg = Number(minimumDraft.value);
  return values;
}

function formatMeasurement(value: number | null, unit: string): string {
  return value === null ? t("Not available") : `${value.toFixed(3).replace(/\.?0+$/, "")} ${unit}`;
}

function acceptJob(nextJob: DesignReviewJob): void {
  job.value = nextJob;
  if (nextJob.state === "succeeded" && nextJob.result) {
    selectedFinding.value =
      nextJob.result.findings.find((finding) => finding.result === "FAIL") ||
      nextJob.result.findings[0] ||
      null;
  }
}

function schedulePoll(): void {
  if (!terminal.value) pollTimer = window.setTimeout(refreshJob, 900);
}

async function refreshJob(): Promise<void> {
  if (!job.value) return;
  try {
    acceptJob(await fetchDesignReviewJob(job.value.job_id));
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh design review.");
  }
}

async function submit(): Promise<void> {
  if (!props.query) {
    error.value = t("Upload and process a CAD artifact first.");
    return;
  }
  submitting.value = true;
  error.value = null;
  job.value = null;
  selectedFinding.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    const accepted = await createDesignReview(props.query, numericContext());
    acceptJob(await fetchDesignReviewJob(accepted.job_id));
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Design review failed.");
  } finally {
    submitting.value = false;
  }
}

async function loadDeepLink(): Promise<void> {
  if (props.deepLink?.target !== "design_review") return;
  error.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    acceptJob(await fetchDesignReview(props.deepLink.refs.review_id));
    const findingId = props.deepLink.refs.finding_id;
    if (findingId && result.value) {
      const finding = result.value.findings.find((item) => item.finding_id === findingId);
      if (!finding) throw new Error("DEEP_LINK_CONTEXT_MISMATCH");
      selectedFinding.value = finding;
    }
    schedulePoll();
  } catch (caught) {
    error.value =
      caught instanceof Error && caught.message === "DEEP_LINK_CONTEXT_MISMATCH"
        ? t("The linked finding does not belong to this design review.")
        : t("The linked design review is unavailable or not authorized.");
  }
}

async function saveDecision(): Promise<void> {
  if (!result.value || !selectedFinding.value) return;
  savingDecision.value = true;
  error.value = null;
  try {
    const record = await createFindingDecision(
      result.value.review_id,
      selectedFinding.value.finding_id,
      {
        decision: decisionChoice.value,
        reason: decisionReason.value,
        approvedBy: decisionApprover.value,
      },
    );
    selectedFinding.value.decisions.push(record);
    decisionReason.value = "";
    decisionApprover.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to save review decision.");
  } finally {
    savingDecision.value = false;
  }
}

watch(
  () => props.query?.artifact_version_id,
  () => {
    job.value = null;
    selectedFinding.value = null;
    error.value = null;
    if (pollTimer !== null) window.clearTimeout(pollTimer);
  },
);

watch(
  () => [result.value?.review_id, selectedFinding.value?.finding_id],
  () => {
    if (!result.value?.review_id) return;
    emit("contextChange", {
      context_version: "1.0",
      page: "design_review",
      ui_locale: locale.value,
      ...(result.value?.review_id ? { review_id: result.value.review_id } : {}),
      ...(selectedFinding.value?.finding_id
        ? { finding_id: selectedFinding.value.finding_id }
        : {}),
    });
  },
);

watch(
  () => [
    props.deepLink?.target,
    props.deepLink?.refs.review_id,
    props.deepLink?.refs.finding_id,
  ],
  loadDeepLink,
  { immediate: true },
);

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section id="design-review" class="design-review-workspace" aria-labelledby="design-review-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ t("Deterministic design review") }}</p>
        <h2 id="design-review-title">{{ t("Evaluate versioned engineering rules") }}</h2>
      </div>
      <span class="demo-label">{{ t("13 Synthetic Demo Rules") }}</span>
    </div>

    <p v-if="!query" class="muted review-intro">
      {{ t("Process a CAD artifact above before starting a design review.") }}
    </p>
    <template v-else>
      <div class="query-summary">
        <div>
          <span>{{ t("Input artifact version") }}</span>
          <code>{{ query.artifact_version_id }}</code>
        </div>
        <span class="index-state indexed">{{ t("Geometry ready") }}</span>
      </div>

      <form class="review-form" @submit.prevent="submit">
        <label>
          <span>{{ t("Nominal wall (mm)") }}</span>
          <input v-model="nominalWall" type="number" min="0" max="10" step="0.01" :placeholder="t('e.g. 1.5 – 5.0')" />
          <small class="field-hint">{{ t("Typical range: 1.0 – 5.0 mm") }}</small>
        </label>
        <label>
          <span>{{ t("Max rib (mm)") }}</span>
          <input v-model="maximumRib" type="number" min="0" max="10" step="0.01" :placeholder="t('e.g. 0.5 – 4.0')" />
          <small class="field-hint">{{ t("Typical range: 0.5 – 4.0 mm") }}</small>
        </label>
        <label>
          <span>{{ t("Min draft (deg)") }}</span>
          <input v-model="minimumDraft" type="number" min="0" max="30" step="0.01" :placeholder="t('e.g. 0.5 – 5.0')" />
          <small class="field-hint">{{ t("Typical range: 0.5 – 5.0°") }}</small>
        </label>
        <button type="submit" :disabled="submitting">
          {{ submitting ? t("Starting...") : t("Run design review") }}
        </button>
      </form>
      <p class="limitation-note">
        {{ t("Optional values are explicit Demo measurements, not measurements extracted from local CAD faces.") }}
      </p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ t(job.state) }}</span>
          <strong>{{ t(job.stage.replaceAll("_", " ")) }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" :aria-label="t('Design review progress')">
        <span :style="{ width: `${job.progress}%` }"></span>
      </div>
      <p v-if="job.error" class="error-message">
        {{ job.error.message }} ({{ job.error.code }})
      </p>
    </div>

    <div v-if="result" class="review-results">
      <div class="review-summary">
        <div class="review-decision" :class="result.summary.decision.toLowerCase()">
          <span>{{ t("Overall") }}</span>
          <strong>{{ t(result.summary.decision) }}</strong>
        </div>
        <div v-for="(count, state) in result.summary.counts" :key="state">
          <span>{{ t(state) }}</span>
          <strong>{{ count }}</strong>
        </div>
      </div>

      <div class="review-layout">
        <ol class="finding-list" :aria-label="t('Design review findings')">
          <li v-for="finding in result.findings" :key="finding.finding_id">
            <button
              type="button"
              class="finding-card"
              :class="[
                finding.result.toLowerCase(),
                { selected: selectedFinding?.finding_id === finding.finding_id },
              ]"
              @click="selectedFinding = finding"
            >
              <span class="finding-state">{{ t(finding.result) }}</span>
              <strong>{{ finding.rule.title }}</strong>
              <small>{{ finding.rule.rule_id }}@{{ finding.rule.rule_version }}</small>
            </button>
          </li>
        </ol>

        <article v-if="selectedFinding" class="finding-detail">
          <div v-if="result.preview" class="review-viewer">
            <CadPreview
              :source="result.preview.download_url"
              :accent="selectedFinding.result === 'FAIL' ? 'warning' : 'default'"
            />
            <span>{{ t("Evidence scope: {scope}", { scope: selectedFinding.geometry_location.scope }) }}</span>
          </div>

          <div class="finding-heading">
            <div>
              <span class="finding-state" :class="selectedFinding.result.toLowerCase()">
                {{ t(selectedFinding.result) }}
              </span>
              <h3>{{ selectedFinding.rule.title }}</h3>
            </div>
            <span>{{ t("{severity} severity", { severity: selectedFinding.severity }) }}</span>
          </div>

          <p>{{ selectedFinding.message }}</p>
          <div class="measurement-grid">
            <div>
              <span>{{ t("Actual") }}</span>
              <strong>{{ formatMeasurement(selectedFinding.actual_value, selectedFinding.unit) }}</strong>
            </div>
            <div>
              <span>{{ t("Limit") }}</span>
              <strong>{{ formatMeasurement(selectedFinding.limit_value, selectedFinding.unit) }}</strong>
            </div>
            <div>
              <span>{{ t("Risk") }}</span>
              <strong>{{ selectedFinding.risk_type }}</strong>
            </div>
            <div>
              <span>{{ t("Rule reference") }}</span>
              <strong>{{ selectedFinding.rule.reference.document }} rev. {{ selectedFinding.rule.reference.revision }}</strong>
            </div>
          </div>
          <p class="recommendation"><strong>{{ t("Recommendation:") }}</strong> {{ selectedFinding.rule.recommendation }}</p>

          <div v-if="selectedFinding.decisions.length" class="decision-history">
            <strong>{{ t("Recorded decisions") }}</strong>
            <p v-for="record in selectedFinding.decisions" :key="record.decision_id">
              {{ t("{decision} by {user}", { decision: t(record.decision), user: record.decided_by }) }}
              <span v-if="record.reason"> — {{ record.reason }}</span>
            </p>
          </div>

          <form
            v-if="selectedFinding.result === 'FAIL'"
            class="decision-form"
            @submit.prevent="saveDecision"
          >
            <h3>{{ t("Record reviewer decision") }}</h3>
            <label>
              <span>{{ t("Decision") }}</span>
              <select v-model="decisionChoice">
                <option value="accepted">{{ t("Accept finding") }}</option>
                <option value="rejected">{{ t("Reject finding") }}</option>
                <option value="waived">{{ t("Waive finding") }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("Reason") }}</span>
              <textarea v-model="decisionReason" rows="2" maxlength="2000"></textarea>
            </label>
            <label>
              <span>{{ t("Approver (required for waiver)") }}</span>
              <select v-model="decisionApprover">
                <option value="">{{ t("Select approver") }}</option>
                <option value="demo-lead-engineer">{{ t("Lead Engineer") }}</option>
                <option value="demo-quality-manager">{{ t("Quality Manager") }}</option>
                <option value="demo-tooling-supervisor">{{ t("Tooling Supervisor") }}</option>
              </select>
            </label>
            <button type="submit" :disabled="savingDecision">
              {{ savingDecision ? t("Saving...") : t("Record decision") }}
            </button>
          </form>
        </article>
      </div>

      <p class="limitation-note">{{ result.limitations.join(" ") }}</p>
    </div>
  </section>
</template>
