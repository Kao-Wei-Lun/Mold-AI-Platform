<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { fetchRuleProfiles, type RuleProfile } from "../api/rules";
import { useI18n } from "../i18n";

const { t } = useI18n();

const profiles = ref<RuleProfile[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const query = ref("");
const severity = ref("all");

const profile = computed(() => profiles.value[0] || null);
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
        <span class="governance-state">{{ t(profile.status.replaceAll("_", " ")) }}</span>
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
        <span>{{ t("Read-only governance") }}</span>
      </aside>

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
