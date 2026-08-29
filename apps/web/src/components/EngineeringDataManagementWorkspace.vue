<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  cloneHMIProfile,
  createManagedCAEStudy,
  createManagedTrial,
  fetchEngineeringData,
  transitionCAEStudy,
  transitionHMIProfile,
  transitionTrial,
  type HMIProfile,
  type ManagedCAEStudy,
  type ManagedTrial,
} from "../api/engineeringData";
import type { LocalAccount } from "../api/identity";
import type { MasterDataOptions } from "../api/masterData";
import { fetchRegistry, type RegistryRevision } from "../api/registry";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const props = defineProps<{
  currentAccount: LocalAccount | null;
  masterDataOptions: MasterDataOptions;
}>();
const { locale, t } = useI18n();
const tab = ref<"trials" | "cae" | "hmi">("trials");
const tabs = ["trials", "cae", "hmi"] as const;
const trials = ref<ManagedTrial[]>([]);
const studies = ref<ManagedCAEStudy[]>([]);
const profiles = ref<HMIProfile[]>([]);
const revisions = ref<RegistryRevision[]>([]);
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const reason = ref("");
const canManage = computed(
  () => props.currentAccount?.permissions.includes("engineering-data:manage") || false,
);
const trialForm = reactive({
  case_code: "",
  mold_revision_id: "",
  machine_code: "",
  material_code: "",
  product_type: "",
  purpose: "",
  outcome: "pending",
  started_at: new Date().toISOString().slice(0, 16),
});
const caeForm = reactive({
  study_code: "",
  solver_name: "Moldflow",
  mold_revision_ref: "",
  material_model_code: "",
  mesh_family: "3d-tetra",
  objective: "",
});
const profileForm = reactive({ source_profile_id: "", version: "", change_summary: "" });

function optionLabel(option: { name_en: string; name_zh_tw: string }): string {
  return locale.value === "zh-TW" ? option.name_zh_tw : option.name_en;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [data, registry] = await Promise.all([fetchEngineeringData(), fetchRegistry()]);
    trials.value = data.trials;
    studies.value = data.studies;
    profiles.value = data.profiles;
    revisions.value = registry.revisions;
    if (!trialForm.mold_revision_id) trialForm.mold_revision_id = revisions.value[0]?.id || "";
    if (!caeForm.mold_revision_ref && revisions.value[0]) {
      caeForm.mold_revision_ref = `${revisions.value[0].mold_code}@${revisions.value[0].revision_code}`;
    }
    if (!profileForm.source_profile_id) {
      profileForm.source_profile_id = profiles.value.find((item) => item.status === "published")?.profile_id || "";
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load engineering data.");
  } finally {
    loading.value = false;
  }
}

async function run(action: () => Promise<unknown>, success: string): Promise<void> {
  if (!reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  busy.value = true;
  error.value = null;
  try {
    await action();
    reason.value = "";
    await load();
    pushToast(t(success), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to save engineering data.");
    pushToast(error.value, "error");
  } finally {
    busy.value = false;
  }
}

function submitTrial(): Promise<void> {
  return run(
    () => createManagedTrial({ ...trialForm, started_at: new Date(trialForm.started_at).toISOString(), reason: reason.value }),
    "Trial case created.",
  );
}

function submitCAE(): Promise<void> {
  return run(() => createManagedCAEStudy({ ...caeForm, reason: reason.value }), "CAE study created.");
}

function submitProfile(): Promise<void> {
  return run(
    () => cloneHMIProfile(profileForm.source_profile_id, profileForm.version, profileForm.change_summary, reason.value),
    "HMI profile version created.",
  );
}

onMounted(load);
</script>

<template>
  <section class="mold-registry-workspace engineering-data-workspace" aria-labelledby="engineering-data-title">
    <div class="card-heading">
      <div><p class="eyebrow">{{ t("Governed operational evidence") }}</p><h2 id="engineering-data-title">{{ t("Trial, CAE and HMI data lifecycle") }}</h2></div>
      <button type="button" class="secondary-button" :disabled="loading" @click="load">{{ t("Refresh data") }}</button>
    </div>
    <div class="registry-summary">
      <div><span>{{ t("Trial cases") }}</span><strong>{{ trials.length }}</strong></div>
      <div><span>{{ t("CAE studies") }}</span><strong>{{ studies.length }}</strong></div>
      <div><span>{{ t("HMI profiles") }}</span><strong>{{ profiles.length }}</strong></div>
      <div><span>{{ t("Access") }}</span><strong>{{ canManage ? t("Manage") : t("Read only") }}</strong></div>
    </div>
    <div class="registry-tabs" role="tablist" :aria-label="t('Engineering data domains')">
      <button v-for="item in tabs" :key="item" type="button" :class="{ active: tab === item }" @click="tab = item">{{ t(item === 'trials' ? 'Trial cases' : item === 'cae' ? 'CAE studies' : 'HMI profiles') }}</button>
    </div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted">{{ t("Loading governed engineering data…") }}</p>
    <div v-else class="registry-layout">
      <section class="registry-catalog" aria-live="polite">
        <template v-if="tab === 'trials'">
          <WorkspaceEmptyState
            v-if="!trials.length"
            :eyebrow="t('Trial cases')"
            :title="t('No managed trial cases yet')"
            :message="t('Create a draft trial to begin its controlled lifecycle.')"
            :action-label="t('Refresh data')"
            @action="load"
          />
          <article v-for="trial in trials" :key="trial.trial_case_id">
            <div><strong>{{ trial.case_code }}</strong><span>{{ trial.mold_revision_ref }} · {{ trial.machine_code }} · {{ trial.material_code }}</span></div>
            <small>{{ trial.corrections.length }} {{ t("corrections") }} · {{ trial.outcome }}</small><em>{{ t(trial.lifecycle_status) }}</em>
            <button v-if="canManage && trial.lifecycle_status === 'draft'" type="button" class="text-button" @click="run(() => transitionTrial(trial, 'close', reason), 'Trial case closed.')">{{ t("Close") }}</button>
            <button v-else-if="canManage && trial.lifecycle_status === 'closed'" type="button" class="text-button" @click="run(() => transitionTrial(trial, 'reopen', reason), 'Trial case reopened.')">{{ t("Reopen") }}</button>
          </article>
        </template>
        <template v-else-if="tab === 'cae'">
          <WorkspaceEmptyState
            v-if="!studies.length"
            :eyebrow="t('CAE studies')"
            :title="t('No managed CAE studies yet')"
            :message="t('Create a structured study to retain solver lineage and results.')"
            :action-label="t('Refresh data')"
            @action="load"
          />
          <article v-for="study in studies" :key="study.study_id">
            <div><strong>{{ study.study_code }}</strong><span>{{ study.solver_name }} · {{ study.mold_revision_ref }}</span></div>
            <small>{{ study.runs.length }} {{ t("runs") }} · {{ study.mesh_family }}</small><em>{{ t(study.lifecycle_status) }}</em>
            <button v-if="canManage" type="button" class="text-button" @click="run(() => transitionCAEStudy(study, study.lifecycle_status === 'active' ? 'archive' : 'restore', reason), 'CAE lifecycle updated.')">{{ t(study.lifecycle_status === 'active' ? 'Archive' : 'Restore') }}</button>
          </article>
        </template>
        <template v-else>
          <article v-for="profile in profiles" :key="profile.profile_id">
            <div><strong>{{ profile.profile_key }}@{{ profile.version }}</strong><span>{{ profile.change_summary }}</span></div>
            <small>{{ profile.field_specs.length }} {{ t("fields") }} · {{ profile.extraction_count }} {{ t("extractions") }}</small><em>{{ t(profile.status) }}</em>
            <button v-if="canManage && profile.status === 'draft'" type="button" class="text-button" @click="run(() => transitionHMIProfile(profile, 'publish', reason), 'HMI profile published.')">{{ t("Publish") }}</button>
          </article>
        </template>
      </section>

      <form v-if="canManage" class="registry-editor" @submit.prevent="tab === 'trials' ? submitTrial() : tab === 'cae' ? submitCAE() : submitProfile()">
        <div><p class="eyebrow">{{ t("Create controlled record") }}</p><h3>{{ t(tab === 'trials' ? 'New trial case' : tab === 'cae' ? 'New CAE study' : 'New HMI profile version') }}</h3></div>
        <template v-if="tab === 'trials'">
          <FormField v-slot="{ fieldId }" :label="t('Trial code')" required><input :id="fieldId" v-model="trialForm.case_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold revision')" required><select :id="fieldId" v-model="trialForm.mold_revision_id" required><option v-for="revision in revisions" :key="revision.id" :value="revision.id">{{ revision.mold_code }}@{{ revision.revision_code }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Machine')" required><select :id="fieldId" v-model="trialForm.machine_code" required><option value="" disabled>{{ t("Select machine") }}</option><option v-for="option in masterDataOptions.machine" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material')" required><select :id="fieldId" v-model="trialForm.material_code" required><option value="" disabled>{{ t("Select material") }}</option><option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product type')" required><select :id="fieldId" v-model="trialForm.product_type" required><option value="" disabled>{{ t("Select product type") }}</option><option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Purpose')" required><input :id="fieldId" v-model="trialForm.purpose" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Started at')" required><input :id="fieldId" v-model="trialForm.started_at" type="datetime-local" required /></FormField>
        </template>
        <template v-else-if="tab === 'cae'">
          <FormField v-slot="{ fieldId }" :label="t('Study code')" required><input :id="fieldId" v-model="caeForm.study_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Solver')" required><input :id="fieldId" v-model="caeForm.solver_name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold revision')" required><select :id="fieldId" v-model="caeForm.mold_revision_ref" required><option v-for="revision in revisions" :key="revision.id" :value="`${revision.mold_code}@${revision.revision_code}`">{{ revision.mold_code }}@{{ revision.revision_code }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material model')" required><select :id="fieldId" v-model="caeForm.material_model_code" required><option value="" disabled>{{ t("Select material") }}</option><option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ optionLabel(option) }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mesh family')" required><select :id="fieldId" v-model="caeForm.mesh_family" required><option value="3d-tetra">3D tetra</option><option value="dual-domain">Dual domain</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Objective')"><textarea :id="fieldId" v-model="caeForm.objective" rows="3"></textarea></FormField>
        </template>
        <template v-else>
          <FormField v-slot="{ fieldId }" :label="t('Source profile')" required><select :id="fieldId" v-model="profileForm.source_profile_id" required><option v-for="profile in profiles" :key="profile.profile_id" :value="profile.profile_id">{{ profile.profile_key }}@{{ profile.version }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('New version')" required><input :id="fieldId" v-model="profileForm.version" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Change summary')" required><textarea :id="fieldId" v-model="profileForm.change_summary" rows="3" required></textarea></FormField>
        </template>
        <FormField v-slot="{ fieldId }" :label="t('Change reason')" required><input :id="fieldId" v-model="reason" required /></FormField>
        <button type="submit" :disabled="busy">{{ busy ? t("Saving...") : t("Create record") }}</button>
      </form>
      <aside v-else class="registry-editor read-only"><strong>{{ t("Read-only engineering data") }}</strong><p>{{ t("Your account can inspect lineage and lifecycle but cannot change records.") }}</p></aside>
    </div>
  </section>
</template>
