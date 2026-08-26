<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";

import type { CADModelResult } from "../api/cad";
import {
  createDesignReview,
  createFindingDecision,
  fetchDesignReviewJob,
  type DesignReviewJob,
  type ReviewFinding,
} from "../api/designReview";

const props = defineProps<{ query: CADModelResult | null }>();
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
  return value === null ? "Not available" : `${value.toFixed(3).replace(/\.?0+$/, "")} ${unit}`;
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
    error.value = caught instanceof Error ? caught.message : "Unable to refresh design review.";
  }
}

async function submit(): Promise<void> {
  if (!props.query) {
    error.value = "Upload and process a CAD artifact first.";
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
    error.value = caught instanceof Error ? caught.message : "Design review failed.";
  } finally {
    submitting.value = false;
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
    error.value = caught instanceof Error ? caught.message : "Unable to save review decision.";
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

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section class="design-review-workspace" aria-labelledby="design-review-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Deterministic design review</p>
        <h2 id="design-review-title">Evaluate versioned engineering rules</h2>
      </div>
      <span class="demo-label">13 Synthetic Demo Rules</span>
    </div>

    <p v-if="!query" class="muted review-intro">
      Process a CAD artifact above before starting a design review.
    </p>
    <template v-else>
      <div class="query-summary">
        <div>
          <span>Input artifact version</span>
          <code>{{ query.artifact_version_id }}</code>
        </div>
        <span class="index-state indexed">Geometry ready</span>
      </div>

      <form class="review-form" @submit.prevent="submit">
        <label>
          <span>Nominal wall (mm)</span>
          <input v-model="nominalWall" type="number" min="0" step="0.01" placeholder="Optional" />
        </label>
        <label>
          <span>Max rib (mm)</span>
          <input v-model="maximumRib" type="number" min="0" step="0.01" placeholder="Optional" />
        </label>
        <label>
          <span>Min draft (deg)</span>
          <input v-model="minimumDraft" type="number" min="0" step="0.01" placeholder="Optional" />
        </label>
        <button type="submit" :disabled="submitting">
          {{ submitting ? "Starting..." : "Run design review" }}
        </button>
      </form>
      <p class="limitation-note">
        Optional values are explicit Demo measurements, not measurements extracted from local CAD faces.
      </p>
    </template>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="job" class="job-panel">
      <div class="job-heading">
        <div>
          <span class="job-state" :class="job.state">{{ job.state }}</span>
          <strong>{{ job.stage.replaceAll("_", " ") }}</strong>
        </div>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="progress-track" aria-label="Design review progress">
        <span :style="{ width: `${job.progress}%` }"></span>
      </div>
      <p v-if="job.error" class="error-message">
        {{ job.error.message }} ({{ job.error.code }})
      </p>
    </div>

    <div v-if="result" class="review-results">
      <div class="review-summary">
        <div class="review-decision" :class="result.summary.decision.toLowerCase()">
          <span>Overall</span>
          <strong>{{ result.summary.decision }}</strong>
        </div>
        <div v-for="(count, state) in result.summary.counts" :key="state">
          <span>{{ state.replaceAll("_", " ") }}</span>
          <strong>{{ count }}</strong>
        </div>
      </div>

      <div class="review-layout">
        <ol class="finding-list" aria-label="Design review findings">
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
              <span class="finding-state">{{ finding.result.replaceAll("_", " ") }}</span>
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
            <span>Evidence scope: {{ selectedFinding.geometry_location.scope }}</span>
          </div>

          <div class="finding-heading">
            <div>
              <span class="finding-state" :class="selectedFinding.result.toLowerCase()">
                {{ selectedFinding.result.replaceAll("_", " ") }}
              </span>
              <h3>{{ selectedFinding.rule.title }}</h3>
            </div>
            <span>{{ selectedFinding.severity }} severity</span>
          </div>

          <p>{{ selectedFinding.message }}</p>
          <div class="measurement-grid">
            <div>
              <span>Actual</span>
              <strong>{{ formatMeasurement(selectedFinding.actual_value, selectedFinding.unit) }}</strong>
            </div>
            <div>
              <span>Limit</span>
              <strong>{{ formatMeasurement(selectedFinding.limit_value, selectedFinding.unit) }}</strong>
            </div>
            <div>
              <span>Risk</span>
              <strong>{{ selectedFinding.risk_type }}</strong>
            </div>
            <div>
              <span>Rule reference</span>
              <strong>{{ selectedFinding.rule.reference.document }} rev. {{ selectedFinding.rule.reference.revision }}</strong>
            </div>
          </div>
          <p class="recommendation"><strong>Recommendation:</strong> {{ selectedFinding.rule.recommendation }}</p>

          <div v-if="selectedFinding.decisions.length" class="decision-history">
            <strong>Recorded decisions</strong>
            <p v-for="record in selectedFinding.decisions" :key="record.decision_id">
              {{ record.decision }} by {{ record.decided_by }}
              <span v-if="record.reason"> — {{ record.reason }}</span>
            </p>
          </div>

          <form
            v-if="selectedFinding.result === 'FAIL'"
            class="decision-form"
            @submit.prevent="saveDecision"
          >
            <h3>Record reviewer decision</h3>
            <label>
              <span>Decision</span>
              <select v-model="decisionChoice">
                <option value="accepted">Accept finding</option>
                <option value="rejected">Reject finding</option>
                <option value="waived">Waive finding</option>
              </select>
            </label>
            <label>
              <span>Reason</span>
              <textarea v-model="decisionReason" rows="2" maxlength="2000"></textarea>
            </label>
            <label>
              <span>Approver (required for waiver)</span>
              <input v-model="decisionApprover" type="text" maxlength="128" />
            </label>
            <button type="submit" :disabled="savingDecision">
              {{ savingDecision ? "Saving..." : "Record decision" }}
            </button>
          </form>
        </article>
      </div>

      <p class="limitation-note">{{ result.limitations.join(" ") }}</p>
    </div>
  </section>
</template>
