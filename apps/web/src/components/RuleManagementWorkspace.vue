<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { LocalAccount } from "../api/identity";
import type { DeepLinkContext } from "../deepLinks";
import { emptyMasterDataOptions, fetchMasterDataOptions, type MasterDataOptions } from "../api/masterData";
import {
  createRuleProfile,
  fetchRuleProfileDiff,
  fetchRuleProfiles,
  previewRuleImpact,
  transitionRuleProfile,
  updateRuleProfile,
  validateRuleProfile,
  type RuleApplicability,
  type RuleDefinition,
  type RuleImpact,
  type RuleProfile,
  type RuleProfileDiff,
  type RuleValidation,
} from "../api/rules";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";

const { t } = useI18n();
const props = defineProps<{
  currentAccount?: LocalAccount | null;
  deepLink?: DeepLinkContext | null;
}>();

const profiles = ref<RuleProfile[]>([]);
const selectedProfileId = ref("");
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const activeTab = ref("overview");
const query = ref("");
const severity = ref("all");
const reason = ref("Controlled rule lifecycle change");
const masterData = ref<MasterDataOptions>(emptyMasterDataOptions());
const draftRules = ref<RuleDefinition[]>([]);
const draftApplicability = ref<RuleApplicability[]>([]);
const validation = ref<RuleValidation | null>(null);
const impact = ref<RuleImpact | null>(null);
const diff = ref<RuleProfileDiff | null>(null);
const baselineId = ref("");
const showCreate = ref(false);
const createForm = ref({ mode: "clone" as "blank" | "template" | "clone", profileKey: "", sourceId: "", version: "2.0", changeSummary: "" });
const profileForm = ref({ changeSummary: "", priority: 0, isDefault: false, effectiveFrom: "", effectiveTo: "", resolutionStatus: "eligible" as "eligible" | "disabled" });

const tabs = ["overview", "applicability", "rules", "diff", "workflow", "usage"];
const evaluators = ["bbox_dimension", "bbox_aspect_ratio", "cad_scalar", "edge_face_ratio", "quality_flag_absent", "unit_known", "surface_share", "context_ratio", "context_value"];
const profile = computed(() => profiles.value.find((item) => item.profile_id === selectedProfileId.value) || profiles.value[0] || null);
const canAuthor = computed(() => props.currentAccount?.permissions.includes("rules:author") || false);
const canApprove = computed(() => props.currentAccount?.permissions.includes("rules:approve") || false);
const isDraft = computed(() => profile.value?.workflow_status === "draft");
const severities = computed(() => ["all", ...new Set((profile.value?.rules || []).map((rule) => rule.severity))]);
const filteredRules = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return (profile.value?.rules || []).filter((rule) => (severity.value === "all" || rule.severity === severity.value) && (!needle || [rule.rule_id, rule.title, rule.description, rule.risk_type, rule.reference.document].join(" ").toLowerCase().includes(needle)));
});
const baselineProfiles = computed(() => profiles.value.filter((item) => item.profile_id !== profile.value?.profile_id));

function copyProfileToEditor(): void {
  if (!profile.value) return;
  draftRules.value = JSON.parse(JSON.stringify(profile.value.rules)) as RuleDefinition[];
  draftApplicability.value = JSON.parse(JSON.stringify(profile.value.applicability || [])) as RuleApplicability[];
  profileForm.value = {
    changeSummary: profile.value.change_summary || "",
    priority: profile.value.priority || 0,
    isDefault: profile.value.is_default || false,
    effectiveFrom: profile.value.effective_from || "",
    effectiveTo: profile.value.effective_to || "",
    resolutionStatus: profile.value.resolution_status || "eligible",
  };
  validation.value = null;
  impact.value = null;
  diff.value = null;
  baselineId.value = baselineProfiles.value[0]?.profile_id || "";
}

watch(profile, copyProfileToEditor);

function conditionLabel(rule: RuleDefinition): string {
  const operator = { lte: "≤", gte: "≥", eq: "=" }[rule.condition.operator];
  return rule.condition.limit === null ? t("Evidence dependent") : `${operator} ${rule.condition.limit} ${rule.condition.unit}`;
}

function defaultParameters(evaluator: string): Record<string, unknown> {
  const values: Record<string, Record<string, unknown>> = {
    bbox_dimension: { aggregation: "max" }, bbox_aspect_ratio: {},
    cad_scalar: { field: "volume", location: "solid:aggregate" }, edge_face_ratio: {},
    quality_flag_absent: { flag: "OPEN_SHELL" }, unit_known: {}, surface_share: { surface_type: "plane" },
    context_ratio: { numerator: "max_rib_thickness_mm", denominator: "nominal_wall_thickness_mm", location: "context:rib-measurement" },
    context_value: { field: "minimum_draft_angle_deg", location: "context:draft-angle-measurement" },
  };
  return values[evaluator] || {};
}

function changeEvaluator(rule: RuleDefinition): void { rule.measurement_definition = defaultParameters(rule.evaluator); }

function newRule(): RuleDefinition {
  const number = draftRules.value.length + 1;
  return {
    rule_version_id: `new-${crypto.randomUUID()}`, rule_id: `RULE-${String(number).padStart(3, "0")}`,
    rule_version: profile.value?.version || "1.0", title: "", description: "", evaluator: "cad_scalar",
    applicability: { formats: ["step", "stp", "stl"] }, measurement_definition: defaultParameters("cad_scalar"),
    condition: { operator: "lte", limit: 0, unit: "mm", tolerance: 0 }, severity: "medium",
    risk_type: "manufacturability", recommendation: "",
    reference: { document: "", revision: "", classification: "public_demo" }, enabled: true,
  };
}

async function loadProfiles(preferredId = ""): Promise<void> {
  loading.value = true; error.value = null;
  try {
    const [profileItems, options] = await Promise.all([fetchRuleProfiles(), fetchMasterDataOptions()]);
    profiles.value = profileItems; masterData.value = options;
    const target = preferredId || selectedProfileId.value;
    selectedProfileId.value = profileItems.some((item) => item.profile_id === target) ? target : profileItems[0]?.profile_id || "";
    copyProfileToEditor();
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Unable to load mold rules."); }
  finally { loading.value = false; }
}

async function createProfile(): Promise<void> {
  if (!reason.value.trim() || !createForm.value.version.trim()) return;
  busy.value = true;
  try {
    const created = await createRuleProfile({ action: createForm.value.mode,
      profile_key: createForm.value.mode === "blank" ? createForm.value.profileKey : undefined,
      source_profile_id: createForm.value.mode === "blank" ? undefined : createForm.value.sourceId || profile.value?.profile_id,
      version: createForm.value.version, change_summary: createForm.value.changeSummary, reason: reason.value });
    showCreate.value = false; activeTab.value = "rules"; await loadProfiles(created.profile_id);
    pushToast(t("Draft rule profile created."), "success");
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Rule workflow failed."); }
  finally { busy.value = false; }
}

async function saveDraft(): Promise<void> {
  if (!profile.value || !isDraft.value || !reason.value.trim()) return;
  busy.value = true;
  try {
    const updated = await updateRuleProfile(profile.value, { change_summary: profileForm.value.changeSummary,
      rules: draftRules.value, applicability: draftApplicability.value, priority: profileForm.value.priority,
      is_default: profileForm.value.isDefault, effective_from: profileForm.value.effectiveFrom || null,
      effective_to: profileForm.value.effectiveTo || null, resolution_status: profileForm.value.resolutionStatus,
      reason: reason.value });
    profiles.value = profiles.value.map((item) => item.profile_id === updated.profile_id ? updated : item);
    copyProfileToEditor(); pushToast(t("Rule draft saved with a new checksum."), "success");
  } catch (caught) { error.value = caught instanceof Error ? caught.message : t("Rule workflow failed."); }
  finally { busy.value = false; }
}

async function transition(action: "test" | "submit" | "approve" | "publish" | "retire"): Promise<void> {
  if (!profile.value || !reason.value.trim() || !window.confirm(t("Confirm {action} for profile {version}?", { action: t(action), version: profile.value.version }))) return;
  busy.value = true;
  try { const updated = await transitionRuleProfile(profile.value, action, reason.value); await loadProfiles(updated.profile_id); pushToast(t("Rule lifecycle updated."), "success"); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : t("Rule workflow failed."); pushToast(error.value, "error"); }
  finally { busy.value = false; }
}

async function runValidation(): Promise<void> { if (profile.value) validation.value = await validateRuleProfile(profile.value); }
async function loadImpact(): Promise<void> { if (profile.value) impact.value = await previewRuleImpact(profile.value); }
async function loadDiff(): Promise<void> { if (profile.value && baselineId.value) diff.value = await fetchRuleProfileDiff(profile.value.profile_id, baselineId.value); }

function optionsFor(dimension: RuleApplicability["dimension"]): Array<{ code: string; name_en: string; name_zh_tw: string }> {
  if (dimension === "project") return [];
  return masterData.value[dimension] || [];
}
function addApplicability(): void { const first = masterData.value.mold_type[0]?.code; if (first) draftApplicability.value.push({ dimension: "mold_type", value_code: first, match_mode: "include" }); }

onMounted(() => loadProfiles(props.deepLink?.refs.profile_id || ""));
watch(
  () => props.deepLink?.refs.profile_id,
  (profileId) => {
    if (profileId && profiles.value.some((item) => item.profile_id === profileId)) {
      selectedProfileId.value = profileId;
    }
  },
);
</script>

<template>
  <section class="rule-management-workspace" aria-labelledby="rule-management-title">
    <div v-if="loading" class="workspace-state" role="status">{{ t("Loading approved rule profile…") }}</div>
    <div v-else-if="error && !profile" class="workspace-state error-state" role="alert"><strong>{{ t("Rule catalog unavailable") }}</strong><span>{{ error }}</span><button type="button" @click="loadProfiles()">{{ t("Try again") }}</button></div>
    <template v-else-if="profile">
      <div class="rule-catalog-toolbar">
        <FormField v-slot="{ fieldId }" :label="t('Rule profile')"><select :id="fieldId" v-model="selectedProfileId"><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_key }} @ {{ item.version }} · {{ t(item.workflow_status) }}</option></select></FormField>
        <button v-if="canAuthor" type="button" @click="showCreate = !showCreate">{{ t("Create rule profile") }}</button>
      </div>

      <form v-if="showCreate" class="rule-create-wizard" @submit.prevent="createProfile">
        <div><p class="eyebrow">{{ t("Creation wizard") }}</p><h3>{{ t("Start a governed draft") }}</h3></div>
        <FormField v-slot="{ fieldId }" :label="t('Creation method')" required><select :id="fieldId" v-model="createForm.mode"><option value="blank">{{ t("Blank") }}</option><option value="template">{{ t("Approved template") }}</option><option value="clone">{{ t("Clone existing version") }}</option></select></FormField>
        <FormField v-if="createForm.mode === 'blank'" v-slot="{ fieldId }" :label="t('Profile key')" required><input :id="fieldId" v-model="createForm.profileKey" required pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></FormField>
        <FormField v-else v-slot="{ fieldId }" :label="t('Source profile')" required><select :id="fieldId" v-model="createForm.sourceId" required><option value="">{{ t("Current profile") }}</option><option v-for="item in profiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_key }} @ {{ item.version }}</option></select></FormField>
        <FormField v-slot="{ fieldId }" :label="t('Version')" required><input :id="fieldId" v-model="createForm.version" required pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></FormField>
        <FormField v-slot="{ fieldId }" :label="t('Change summary')"><input :id="fieldId" v-model="createForm.changeSummary" /></FormField>
        <button type="submit" :disabled="busy">{{ t("Create draft") }}</button>
      </form>

      <div class="rule-profile-header"><div><p class="eyebrow">{{ t("Governed rule profile") }}</p><h2 id="rule-management-title">{{ profile.profile_key }} @ {{ profile.version }}</h2><p>{{ t("{count} enabled rules · owned by {owner} · approved by {approver}", { count: profile.rule_count, owner: profile.owner, approver: profile.approved_by || "—" }) }}</p></div><span class="governance-state">{{ t(profile.workflow_status) }}</span></div>
      <div v-if="error" class="inline-validation error-state" role="alert">{{ error }} <button type="button" @click="error = null">{{ t("Dismiss") }}</button></div>
      <nav class="rule-detail-tabs" :aria-label="t('Rule profile sections')"><button v-for="tab in tabs" :key="tab" type="button" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ t(tab === 'diff' ? 'Version diff' : tab[0].toUpperCase() + tab.slice(1)) }}</button></nav>

      <section v-if="activeTab === 'overview'" class="rule-tab-panel">
        <div class="governance-summary" :aria-label="t('Rule governance summary')"><div><span>{{ t("Profile version") }}</span><strong>{{ profile.version }}</strong></div><div><span>{{ t("Enabled rules") }}</span><strong>{{ profile.rule_count }}</strong></div><div><span>{{ t("Priority") }}</span><strong>{{ profile.priority }}</strong></div><div><span>{{ t("Ruleset checksum") }}</span><code>{{ profile.ruleset_checksum.slice(0, 12) }}…</code></div></div>
        <aside class="governance-boundary"><div><strong>{{ t("Approved rules are immutable in this Demo") }}</strong><p>{{ t("The catalog is managed here for discovery and audit. Safe editing requires a separate draft, validation, approval and activation workflow—never an in-place threshold change.") }}</p></div><span>{{ canAuthor || canApprove ? t("Controlled workflow") : t("Read-only governance") }}</span></aside>
        <div class="rule-overview-grid"><div><span>{{ t("Scope") }}</span><strong>{{ profile.scope || "—" }}</strong></div><div><span>{{ t("Classification") }}</span><strong>{{ profile.classification }}</strong></div><div><span>{{ t("Effective period") }}</span><strong>{{ profile.effective_from || "—" }} → {{ profile.effective_to || "—" }}</strong></div><div><span>{{ t("Resolution") }}</span><strong>{{ t(profile.resolution_status) }}</strong></div></div>
      </section>

      <section v-else-if="activeTab === 'applicability'" class="rule-tab-panel">
        <div class="section-heading"><div><h3>{{ t("Applicability editor") }}</h3><p>{{ t("Choose governed dimensions that include or exclude this profile during automatic resolution.") }}</p></div><button v-if="canAuthor && isDraft" type="button" @click="addApplicability">{{ t("Add condition") }}</button></div>
        <div v-if="draftApplicability.length" class="applicability-editor"><div v-for="(item, index) in draftApplicability" :key="index" class="applicability-row"><select v-model="item.dimension"><option value="mold_type">{{ t("Mold type") }}</option><option value="product_type">{{ t("Product type") }}</option><option value="material">{{ t("Material") }}</option><option value="molding_process">{{ t("Molding process") }}</option><option value="location">{{ t("Location") }}</option></select><select v-model="item.value_code"><option v-for="option in optionsFor(item.dimension)" :key="option.code" :value="option.code">{{ option.name_zh_tw || option.name_en }} ({{ option.code }})</option></select><select v-model="item.match_mode"><option value="include">{{ t("Include") }}</option><option value="exclude">{{ t("Exclude") }}</option></select><button v-if="canAuthor && isDraft" type="button" class="danger-button" @click="draftApplicability.splice(index, 1)">{{ t("Remove") }}</button></div></div>
        <p v-else class="workspace-state">{{ t("No applicability conditions. This profile can only resolve as a controlled default.") }}</p>
      </section>

      <section v-else-if="activeTab === 'rules'" class="rule-tab-panel">
        <div class="rule-filter-bar"><label><span>{{ t("Search rules") }}</span><input v-model="query" type="search" :placeholder="t('Rule ID, risk, title or reference')" /></label><label><span>{{ t("Severity") }}</span><select v-model="severity"><option v-for="item in severities" :key="item" :value="item">{{ item === "all" ? t("All severities") : t(item) }}</option></select></label><button v-if="canAuthor && isDraft" type="button" @click="draftRules.push(newRule())">{{ t("Add rule") }}</button><span class="result-count">{{ t("{count} shown", { count: isDraft ? draftRules.length : filteredRules.length }) }}</span></div>
        <div v-if="canAuthor && isDraft" class="structured-rule-list"><article v-for="(rule, index) in draftRules" :key="rule.rule_version_id" class="structured-rule-card"><header><strong>{{ rule.rule_id || t("New rule") }}</strong><div><button type="button" :disabled="index === 0" @click="draftRules.splice(index - 1, 0, draftRules.splice(index, 1)[0])">↑</button><button type="button" :disabled="index === draftRules.length - 1" @click="draftRules.splice(index + 1, 0, draftRules.splice(index, 1)[0])">↓</button><button type="button" class="danger-button" @click="draftRules.splice(index, 1)">{{ t("Remove") }}</button></div></header><div class="structured-rule-grid"><FormField v-slot="{ fieldId }" :label="t('Rule ID')" required><input :id="fieldId" v-model="rule.rule_id" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Title')" required><input :id="fieldId" v-model="rule.title" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Evaluator')" required><select :id="fieldId" v-model="rule.evaluator" @change="changeEvaluator(rule)"><option v-for="item in evaluators" :key="item" :value="item">{{ item }}</option></select></FormField><FormField v-slot="{ fieldId }" :label="t('Operator')" required><select :id="fieldId" v-model="rule.condition.operator"><option value="lte">≤</option><option value="gte">≥</option><option value="eq">=</option></select></FormField><FormField v-slot="{ fieldId }" :label="t('Threshold')" required><input :id="fieldId" v-model.number="rule.condition.limit" type="number" step="any" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Unit')" required><input :id="fieldId" v-model="rule.condition.unit" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Tolerance')"><input :id="fieldId" v-model.number="rule.condition.tolerance" type="number" step="any" /></FormField><FormField v-slot="{ fieldId }" :label="t('Severity')"><select :id="fieldId" v-model="rule.severity"><option value="low">{{ t("low") }}</option><option value="medium">{{ t("medium") }}</option><option value="high">{{ t("high") }}</option></select></FormField><FormField v-slot="{ fieldId }" :label="t('Risk type')"><input :id="fieldId" v-model="rule.risk_type" /></FormField><FormField v-slot="{ fieldId }" class="form-wide" :label="t('Description')"><textarea :id="fieldId" v-model="rule.description" rows="2" /></FormField><FormField v-slot="{ fieldId }" class="form-wide" :label="t('Recommendation')"><textarea :id="fieldId" v-model="rule.recommendation" rows="2" /></FormField><FormField v-slot="{ fieldId }" :label="t('Reference document')" required><input :id="fieldId" v-model="rule.reference.document" required /></FormField><FormField v-slot="{ fieldId }" :label="t('Reference revision')" required><input :id="fieldId" v-model="rule.reference.revision" required /></FormField><label class="rule-enabled"><input v-model="rule.enabled" type="checkbox" /> {{ t("Enabled") }}</label></div></article></div>
        <div v-else class="rule-table-wrap"><table class="rule-table"><thead><tr><th>{{ t("Rule") }}</th><th>{{ t("Condition") }}</th><th>{{ t("Risk / severity") }}</th><th>{{ t("Reference") }}</th></tr></thead><tbody><tr v-for="rule in filteredRules" :key="rule.rule_version_id"><td><code>{{ rule.rule_id }} · v{{ rule.rule_version }}</code><strong>{{ rule.title }}</strong><span>{{ rule.description }}</span></td><td><strong>{{ conditionLabel(rule) }}</strong><span>{{ rule.evaluator }}</span></td><td><span class="severity-chip" :class="`severity-${rule.severity}`">{{ t(rule.severity) }}</span><span>{{ rule.risk_type }}</span></td><td><strong>{{ rule.reference.document }}</strong><span>{{ rule.reference.revision }} · {{ rule.reference.classification }}</span></td></tr></tbody></table></div>
      </section>

      <section v-else-if="activeTab === 'diff'" class="rule-tab-panel"><div class="section-heading"><div><h3>{{ t("Version diff") }}</h3><p>{{ t("Compare immutable versions before approval or publication.") }}</p></div></div><div class="rule-diff-controls"><select v-model="baselineId"><option value="">{{ t("Select a baseline version.") }}</option><option v-for="item in baselineProfiles" :key="item.profile_id" :value="item.profile_id">{{ item.profile_key }} @ {{ item.version }}</option></select><button type="button" :disabled="!baselineId" @click="loadDiff">{{ t("Compare") }}</button></div><div v-if="diff" class="rule-diff-list"><article v-for="item in diff.changes" :key="item.rule_id"><span :class="`status-${item.change}`">{{ t(item.change) }}</span><strong>{{ item.rule_id }}</strong><small>{{ item.changed_fields.join(", ") || "—" }}</small></article><p v-if="!diff.changes.length">{{ t("No rule differences found.") }}</p></div></section>

      <section v-else-if="activeTab === 'workflow'" class="rule-tab-panel"><div class="rule-workflow-panel"><div><p class="eyebrow">{{ t("Publishing lifecycle") }}</p><h3>{{ t("Validate and publish without editing history") }}</h3></div><div class="rule-workflow-form"><FormField v-slot="{ fieldId }" :label="t('Change summary')"><input :id="fieldId" v-model="profileForm.changeSummary" :disabled="!isDraft" /></FormField><FormField v-slot="{ fieldId }" :label="t('Priority')"><input :id="fieldId" v-model.number="profileForm.priority" type="number" :disabled="!isDraft" /></FormField><FormField v-slot="{ fieldId }" :label="t('Resolution')"><select :id="fieldId" v-model="profileForm.resolutionStatus" :disabled="!isDraft"><option value="eligible">{{ t("eligible") }}</option><option value="disabled">{{ t("disabled") }}</option></select></FormField><FormField v-slot="{ fieldId }" :label="t('Effective from')"><input :id="fieldId" v-model="profileForm.effectiveFrom" type="date" :disabled="!isDraft" /></FormField><FormField v-slot="{ fieldId }" :label="t('Effective to')"><input :id="fieldId" v-model="profileForm.effectiveTo" type="date" :disabled="!isDraft" /></FormField><FormField v-slot="{ fieldId }" :label="t('Change reason')" required><input :id="fieldId" v-model="reason" required /></FormField></div><div class="master-data-actions"><button v-if="canAuthor && isDraft" type="button" :disabled="busy" @click="saveDraft">{{ t("Save draft") }}</button><button v-if="canAuthor && isDraft" type="button" :disabled="busy" @click="runValidation">{{ t("Preview validation") }}</button><button v-if="canAuthor && isDraft" type="button" :disabled="busy" @click="transition('test')">{{ t("Validate draft") }}</button><button v-if="canAuthor && profile.workflow_status === 'validated'" type="button" :disabled="busy" @click="transition('submit')">{{ t("Submit for review") }}</button><button v-if="canApprove && profile.workflow_status === 'in_review'" type="button" :disabled="busy" @click="transition('approve')">{{ t("Approve version") }}</button><button v-if="canApprove && profile.workflow_status === 'approved'" type="button" :disabled="busy" @click="transition('publish')">{{ t("Publish version") }}</button><button v-if="canApprove && profile.workflow_status === 'published'" type="button" class="danger-button" :disabled="busy" @click="transition('retire')">{{ t("Retire version") }}</button></div><div v-if="validation" class="validation-report" :class="{ valid: validation.valid }"><strong>{{ validation.valid ? t("Validation passed") : t("Validation requires attention") }}</strong><ul v-if="validation.issues.length"><li v-for="item in validation.issues" :key="`${item.code}-${item.rule_id}`"><code>{{ item.code }}</code> {{ item.rule_id }} {{ item.message }}</li></ul></div></div></section>

      <section v-else class="rule-tab-panel"><div class="section-heading"><div><h3>{{ t("Usage and impact") }}</h3><p>{{ t("Preview governed scope before publishing. Historical review results never change.") }}</p></div><button v-if="canAuthor" type="button" @click="loadImpact">{{ t("Refresh impact") }}</button></div><div v-if="impact" class="governance-summary"><div><span>{{ t("Molds") }}</span><strong>{{ impact.impact.molds }}</strong></div><div><span>{{ t("Revisions") }}</span><strong>{{ impact.impact.revisions }}</strong></div><div><span>{{ t("CAD artifacts") }}</span><strong>{{ impact.impact.cad_artifacts }}</strong></div><div><span>{{ t("Historical reviews") }}</span><strong>{{ impact.impact.historical_reviews }}</strong></div></div><p v-else class="workspace-state">{{ t("Run an impact preview before publishing this profile.") }}</p></section>

      <footer v-if="canAuthor && isDraft && activeTab !== 'workflow'" class="rule-sticky-actions"><span>{{ t("Draft changes are not applied until saved.") }}</span><button type="button" :disabled="busy || draftRules.length === 0" @click="saveDraft">{{ t("Save draft") }}</button></footer>
    </template>
    <p v-else class="workspace-state">{{ t("No approved rule profile is available.") }}</p>
  </section>
</template>
