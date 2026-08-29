<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import type { LocalAccount } from "../api/identity";
import type { MasterDataOptions } from "../api/masterData";
import {
  createMold,
  createPart,
  createProject,
  createRevision,
  fetchRegistry,
  updateRevision,
  type RegistryMold,
  type RegistryPart,
  type RegistryProject,
  type RegistryRevision,
} from "../api/registry";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const props = defineProps<{
  currentAccount: LocalAccount | null;
  masterDataOptions: MasterDataOptions;
}>();
const { locale, t } = useI18n();

type RegistryTab = "projects" | "parts" | "molds" | "revisions";
const tab = ref<RegistryTab>("projects");
const projects = ref<RegistryProject[]>([]);
const parts = ref<RegistryPart[]>([]);
const molds = ref<RegistryMold[]>([]);
const revisions = ref<RegistryRevision[]>([]);
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const reason = ref("Demo registry maintenance");

const projectForm = reactive({ code: "", name: "", description: "" });
const partForm = reactive({ project_id: "", part_number: "", name: "", product_type: "", material_code: "" });
const moldForm = reactive({ project_id: "", product_part_id: "", mold_code: "", name: "", mold_type: "injection", cavity_count: 1 });
const revisionForm = reactive({ mold_id: "", revision_code: "", change_summary: "" });

const canManage = computed(() => props.currentAccount?.permissions.includes("registry:manage") || false);
const activeParts = computed(() => parts.value.filter((item) => !moldForm.project_id || item.project_id === moldForm.project_id));
const releasedCount = computed(() => revisions.value.filter((item) => item.status === "released").length);

function masterLabel(kind: "product_type" | "material", code: string): string {
  const item = props.masterDataOptions[kind].find((option) => option.code === code);
  if (!item) return code;
  return locale.value === "zh-TW" ? item.name_zh_tw : item.name_en;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const payload = await fetchRegistry();
    projects.value = payload.projects;
    parts.value = payload.parts;
    molds.value = payload.molds;
    revisions.value = payload.revisions;
    if (!partForm.project_id) partForm.project_id = projects.value[0]?.id || "";
    if (!moldForm.project_id) moldForm.project_id = projects.value[0]?.id || "";
    if (!revisionForm.mold_id) revisionForm.mold_id = molds.value[0]?.id || "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load mold registry.");
  } finally {
    loading.value = false;
  }
}

async function submitProject(): Promise<void> {
  await mutate(async () => {
    await createProject({ ...projectForm, reason: reason.value });
    Object.assign(projectForm, { code: "", name: "", description: "" });
  }, t("Project created."));
}

async function submitPart(): Promise<void> {
  await mutate(async () => {
    await createPart({ ...partForm, reason: reason.value });
    Object.assign(partForm, { ...partForm, part_number: "", name: "" });
  }, t("Part created."));
}

async function submitMold(): Promise<void> {
  await mutate(async () => {
    await createMold({ ...moldForm, product_part_id: moldForm.product_part_id || null, reason: reason.value });
    Object.assign(moldForm, { ...moldForm, mold_code: "", name: "", cavity_count: 1 });
  }, t("Mold created."));
}

async function submitRevision(): Promise<void> {
  await mutate(async () => {
    await createRevision({ ...revisionForm, reason: reason.value });
    Object.assign(revisionForm, { ...revisionForm, revision_code: "", change_summary: "" });
  }, t("Revision created."));
}

async function releaseRevision(revision: RegistryRevision): Promise<void> {
  if (!window.confirm(t("Release revision {revision}?", { revision: `${revision.mold_code}@${revision.revision_code}` }))) return;
  await mutate(
    () => updateRevision(revision, { status: "released", reason: reason.value }),
    t("Revision released and previous release superseded."),
  );
}

async function mutate(action: () => Promise<unknown>, success: string): Promise<void> {
  if (!reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  busy.value = true;
  error.value = null;
  try {
    await action();
    await load();
    pushToast(success, "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Registry change failed.");
    pushToast(error.value, "error");
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="mold-registry-workspace" aria-labelledby="registry-title">
    <div class="section-heading">
      <div><p class="eyebrow">{{ t("Governed engineering hierarchy") }}</p><h2 id="registry-title">{{ t("Mold registry and revision lifecycle") }}</h2></div>
      <button type="button" class="secondary-button" :disabled="loading" @click="load">{{ t("Refresh registry") }}</button>
    </div>

    <div class="registry-summary">
      <div><span>{{ t("Projects") }}</span><strong>{{ projects.length }}</strong></div>
      <div><span>{{ t("Parts") }}</span><strong>{{ parts.length }}</strong></div>
      <div><span>{{ t("Molds") }}</span><strong>{{ molds.length }}</strong></div>
      <div><span>{{ t("Released revisions") }}</span><strong>{{ releasedCount }}</strong></div>
    </div>

    <div class="registry-tabs" role="tablist" :aria-label="t('Registry domains')">
      <button v-for="item in (['projects', 'parts', 'molds', 'revisions'] as RegistryTab[])" :key="item" type="button" role="tab" :aria-selected="tab === item" :class="{ active: tab === item }" @click="tab = item">{{ t(item) }}</button>
    </div>

    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="loading" class="workspace-state">{{ t("Loading mold registry...") }}</p>

    <div v-else class="registry-layout">
      <section class="registry-catalog">
        <template v-if="tab === 'projects'">
          <article v-for="project in projects" :key="project.id">
            <div><strong>{{ project.code }}</strong><span>{{ project.name }}</span></div>
            <small>{{ project.part_count }} {{ t("parts") }} · {{ project.mold_count }} {{ t("molds") }}</small>
            <em :class="`status-${project.status}`">{{ t(project.status) }}</em>
          </article>
          <WorkspaceEmptyState v-if="!projects.length" eyebrow="" :title="t('No projects')" :message="t('Create the first governed engineering project.')" action-label="" />
        </template>
        <template v-else-if="tab === 'parts'">
          <article v-for="part in parts" :key="part.id">
            <div><strong>{{ part.part_number }}</strong><span>{{ part.name }}</span></div>
            <small>{{ part.project_code }} · {{ masterLabel('product_type', part.product_type) }} · {{ masterLabel('material', part.material_code) }}</small>
            <em :class="`status-${part.status}`">{{ t(part.status) }}</em>
          </article>
        </template>
        <template v-else-if="tab === 'molds'">
          <article v-for="mold in molds" :key="mold.id">
            <div><strong>{{ mold.mold_code }}</strong><span>{{ mold.name }}</span></div>
            <small>{{ mold.project_code }} · {{ mold.part_number || t('No part') }} · {{ mold.revision_count }} {{ t('revisions') }}</small>
            <em :class="`status-${mold.status}`">{{ t(mold.status) }}</em>
          </article>
        </template>
        <template v-else>
          <article v-for="revision in revisions" :key="revision.id">
            <div><strong>{{ revision.mold_code }}@{{ revision.revision_code }}</strong><span>{{ revision.change_summary || t("No change summary") }}</span></div>
            <small>{{ revision.artifact_count }} {{ t("CAD artifacts") }} · {{ revision.source_system }}</small>
            <em :class="`status-${revision.status}`">{{ t(revision.status) }}</em>
            <button v-if="canManage && revision.status === 'draft'" type="button" class="text-button" :disabled="busy" @click="releaseRevision(revision)">{{ t("Release") }}</button>
          </article>
        </template>
      </section>

      <form v-if="canManage" class="registry-editor" @submit.prevent="tab === 'projects' ? submitProject() : tab === 'parts' ? submitPart() : tab === 'molds' ? submitMold() : submitRevision()">
        <div><p class="eyebrow">{{ t("Create controlled record") }}</p><h3>{{ t(`New ${tab.slice(0, -1)}`) }}</h3></div>
        <template v-if="tab === 'projects'">
          <FormField v-slot="{ fieldId }" :label="t('Project code')" required><input :id="fieldId" v-model="projectForm.code" required pattern="[A-Za-z0-9][A-Za-z0-9._/-]*" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Project name')" required><input :id="fieldId" v-model="projectForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Description')"><textarea :id="fieldId" v-model="projectForm.description" rows="3"></textarea></FormField>
        </template>
        <template v-else-if="tab === 'parts'">
          <FormField v-slot="{ fieldId }" :label="t('Project')" required><select :id="fieldId" v-model="partForm.project_id" required><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.code }} · {{ project.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Part number')" required><input :id="fieldId" v-model="partForm.part_number" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Part name')" required><input :id="fieldId" v-model="partForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product type')"><select :id="fieldId" v-model="partForm.product_type"><option value="">{{ t("Not specified") }}</option><option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material')"><select :id="fieldId" v-model="partForm.material_code"><option value="">{{ t("Not specified") }}</option><option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
        </template>
        <template v-else-if="tab === 'molds'">
          <FormField v-slot="{ fieldId }" :label="t('Project')" required><select :id="fieldId" v-model="moldForm.project_id" required><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.code }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product / part')"><select :id="fieldId" v-model="moldForm.product_part_id"><option value="">{{ t("Not specified") }}</option><option v-for="part in activeParts" :key="part.id" :value="part.id">{{ part.part_number }} · {{ part.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold code')" required><input :id="fieldId" v-model="moldForm.mold_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold name')" required><input :id="fieldId" v-model="moldForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Cavity count')" required><input :id="fieldId" v-model.number="moldForm.cavity_count" type="number" min="1" max="128" required /></FormField>
        </template>
        <template v-else>
          <FormField v-slot="{ fieldId }" :label="t('Mold')" required><select :id="fieldId" v-model="revisionForm.mold_id" required><option v-for="mold in molds" :key="mold.id" :value="mold.id">{{ mold.mold_code }} · {{ mold.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Revision code')" required><input :id="fieldId" v-model="revisionForm.revision_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Change summary')"><textarea :id="fieldId" v-model="revisionForm.change_summary" rows="3"></textarea></FormField>
        </template>
        <FormField v-slot="{ fieldId }" :label="t('Change reason')" required><input :id="fieldId" v-model="reason" required /></FormField>
        <button type="submit" :disabled="busy">{{ busy ? t("Saving...") : t("Create record") }}</button>
      </form>
      <aside v-else class="registry-editor read-only"><strong>{{ t("Read-only registry") }}</strong><p>{{ t("Your account can inspect the hierarchy but cannot change it.") }}</p></aside>
    </div>
  </section>
</template>
