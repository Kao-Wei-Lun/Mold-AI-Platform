<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { cloneRuleProfile, fetchRuleProfiles, transitionRuleProfile, type RuleProfile } from "../api/rules";
import type { LocalAccount } from "../api/identity";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";

const { t } = useI18n();
const props = defineProps<{ currentAccount?: LocalAccount | null }>();

const profiles = ref<RuleProfile[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const query = ref("");
const severity = ref("all");
const busy = ref(false);
const nextVersion = ref("2.0");
const changeSummary = ref("");
const reason = ref("Controlled rule lifecycle change");

const profile = computed(() => profiles.value[0] || null);
const canAuthor = computed(() => props.currentAccount?.permissions.includes("rules:author") || false);
const canApprove = computed(() => props.currentAccount?.permissions.includes("rules:approve") || false);
const workflowStatus = computed(() => profile.value?.workflow_status || "published");
const severities = computed(() => [
  "all",
  ...new Set((profile.value?.rules || []).map((rule) => rule.severity)),
]);
const filteredRules = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return (profile.value?.rules || []).filter((rule) => {
    const matchesSeverity = severity.value === "all" || rule.severity === severity.value;
    const matchesQuery =
      !needle ||
      [rule.rule_id, rule.title, rule.description, rule.risk_type, rule.reference.document]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    return matchesSeverity && matchesQuery;
  });
});

function conditionLabel(rule: RuleProfile["rules"][number]): string {
  const operator = { lte: "≤", gte: "≥", eq: "=" }[rule.condition.operator];
  return rule.condition.limit === null
    ? t("Evidence dependent")
    : `${operator} ${rule.condition.limit} ${rule.condition.unit}`;
}

async function loadProfiles(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    profiles.value = await fetchRuleProfiles();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load mold rules.");
  } finally {
    loading.value = false;
  }
}

async function cloneProfile(): Promise<void> {
  if (!profile.value || !reason.value.trim()) return;
  busy.value = true;
  error.value = null;
  try {
    await cloneRuleProfile(profile.value, {
      version: nextVersion.value,
      changeSummary: changeSummary.value,
      reason: reason.value,
    });
    await loadProfiles();
    pushToast(t("Draft rule profile created."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Rule workflow failed.");
  } finally {
    busy.value = false;
  }
}

async function transition(action: "test" | "submit" | "approve" | "publish" | "retire"): Promise<void> {
  if (!profile.value || !reason.value.trim()) return;
  if (!window.confirm(t("Confirm {action} for profile {version}?", { action: t(action), version: profile.value.version }))) return;
  busy.value = true;
  error.value = null;
  try {
    await transitionRuleProfile(profile.value, action, reason.value);
    await loadProfiles();
    pushToast(t("Rule lifecycle updated."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Rule workflow failed.");
    pushToast(error.value, "error");
  } finally {
    busy.value = false;
  }
}

onMounted(loadProfiles);
</script>

<template>
  <section class="rule-management-workspace" aria-labelledby="rule-management-title">
    <div v-if="loading" class="workspace-state" role="status">{{ t("Loading approved rule profile…") }}</div>
    <div v-else-if="error" class="workspace-state error-state" role="alert">
      <strong>{{ t("Rule catalog unavailable") }}</strong>
      <span>{{ error }}</span>
      <button type="button" @click="loadProfiles">{{ t("Try again") }}</button>
    </div>
    <template v-else-if="profile">
      <div class="rule-profile-header">
        <div>
          <p class="eyebrow">{{ t("Approved rule profile") }}</p>
          <h2 id="rule-management-title">{{ profile.profile_key }} @ {{ profile.version }}</h2>
          <p>
            {{ t("{count} enabled rules · owned by {owner} · approved by {approver}", { count: profile.rule_count, owner: profile.owner, approver: profile.approved_by }) }}
          </p>
        </div>
        <span class="governance-state">{{ t(workflowStatus.replaceAll("_", " ")) }}</span>
      </div>

      <div class="governance-summary" :aria-label="t('Rule governance summary')">
        <div><span>{{ t("Profile version") }}</span><strong>{{ profile.version }}</strong></div>
        <div><span>{{ t("Enabled rules") }}</span><strong>{{ profile.rule_count }}</strong></div>
        <div><span>{{ t("Ruleset checksum") }}</span><code>{{ profile.ruleset_checksum.slice(0, 12) }}…</code></div>
        <div><span>{{ t("Change policy") }}</span><strong>{{ t("Versioned approval") }}</strong></div>
      </div>

      <aside class="governance-boundary">
        <div>
          <strong>{{ t("Approved rules are immutable in this Demo") }}</strong>
          <p>
            {{ t("The catalog is managed here for discovery and audit. Safe editing requires a separate draft, validation, approval and activation workflow—never an in-place threshold change.") }}
          </p>
        </div>
        <span>{{ canAuthor || canApprove ? t("Controlled workflow") : t("Read-only governance") }}</span>
      </aside>

      <section v-if="canAuthor || canApprove" class="rule-workflow-panel" aria-labelledby="rule-workflow-title">
        <div><p class="eyebrow">{{ t("Publishing lifecycle") }}</p><h3 id="rule-workflow-title">{{ t("Validate and publish without editing history") }}</h3></div>
        <div class="rule-workflow-form">
          <FormField v-if="canAuthor && ['published', 'retired'].includes(workflowStatus)" v-slot="{ fieldId }" :label="t('Next version')" required><input :id="fieldId" v-model="nextVersion" required pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></FormField>
          <FormField v-if="canAuthor && ['published', 'retired'].includes(workflowStatus)" v-slot="{ fieldId }" :label="t('Change summary')"><input :id="fieldId" v-model="changeSummary" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Change reason')" required><input :id="fieldId" v-model="reason" required /></FormField>
        </div>
        <div class="master-data-actions">
          <button v-if="canAuthor && ['published', 'retired'].includes(workflowStatus)" type="button" :disabled="busy" @click="cloneProfile">{{ t("Create draft version") }}</button>
          <button v-if="canAuthor && workflowStatus === 'draft'" type="button" :disabled="busy" @click="transition('test')">{{ t("Run deterministic validation") }}</button>
          <button v-if="canAuthor && workflowStatus === 'validated'" type="button" :disabled="busy" @click="transition('submit')">{{ t("Submit for review") }}</button>
          <button v-if="canApprove && workflowStatus === 'in_review'" type="button" :disabled="busy" @click="transition('approve')">{{ t("Approve version") }}</button>
          <button v-if="canApprove && workflowStatus === 'approved'" type="button" :disabled="busy" @click="transition('publish')">{{ t("Publish version") }}</button>
          <button v-if="canApprove && workflowStatus === 'published'" type="button" class="danger-button" :disabled="busy" @click="transition('retire')">{{ t("Retire version") }}</button>
        </div>
      </section>

      <div class="rule-filter-bar">
        <label>
          <span>{{ t("Search rules") }}</span>
          <input v-model="query" type="search" :placeholder="t('Rule ID, risk, title or reference')" />
        </label>
        <label>
          <span>{{ t("Severity") }}</span>
          <select v-model="severity">
            <option v-for="item in severities" :key="item" :value="item">
              {{ item === "all" ? t("All severities") : t(item) }}
            </option>
          </select>
        </label>
        <span class="result-count">{{ t("{count} shown", { count: filteredRules.length }) }}</span>
      </div>

      <div class="rule-table-wrap">
        <table class="rule-table">
          <thead>
            <tr>
              <th>{{ t("Rule") }}</th>
              <th>{{ t("Condition") }}</th>
              <th>{{ t("Risk / severity") }}</th>
              <th>{{ t("Reference") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in filteredRules" :key="rule.rule_version_id">
              <td>
                <code>{{ rule.rule_id }} · v{{ rule.rule_version }}</code>
                <strong>{{ rule.title }}</strong>
                <span>{{ rule.description }}</span>
              </td>
              <td><strong>{{ conditionLabel(rule) }}</strong><span>{{ rule.evaluator }}</span></td>
              <td>
                <span class="severity-chip" :class="`severity-${rule.severity}`">{{ t(rule.severity) }}</span>
                <span>{{ rule.risk_type }}</span>
              </td>
              <td>
                <strong>{{ rule.reference.document }}</strong>
                <span>{{ rule.reference.revision }} · {{ rule.reference.classification }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="filteredRules.length === 0" class="workspace-state">{{ t("No rules match these filters.") }}</p>
    </template>
    <p v-else class="workspace-state">{{ t("No approved rule profile is available.") }}</p>
  </section>
</template>
