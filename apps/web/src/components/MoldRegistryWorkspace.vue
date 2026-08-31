<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import type { LocalAccount } from "../api/identity";
import type { MasterDataOptions } from "../api/masterData";
import {
  createMold,
  createPart,
  createProject,
  createRevision,
  fetchRegistryMolds,
  fetchRegistryOverview,
  fetchRegistryParts,
  fetchRegistryProjects,
  updateRevision,
  type RegistryMold,
  type RegistryOverview,
  type RegistryPage,
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
type RegistryView = "table" | "tree";
type TreePartGroup = { key: string; label: string; molds: RegistryMold[] };
type TreeProjectGroup = { key: string; code: string; name: string; parts: TreePartGroup[] };

const emptyOverview = (): RegistryOverview => ({
  schema_version: "1.0",
  counts: {
    active_projects: 0,
    active_molds: 0,
    released_revisions: 0,
    draft_revisions: 0,
    released_without_cad: 0,
    pending_mapping: 0,
  },
});

const emptyPage = (): RegistryPage => ({ number: 1, size: 25, total: 0, sort: "-updated_at", has_next: false });

const projects = ref<RegistryProject[]>([]);
const parts = ref<RegistryPart[]>([]);
const molds = ref<RegistryMold[]>([]);
const overview = ref<RegistryOverview>(emptyOverview());
const pageInfo = ref<RegistryPage>(emptyPage());
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const createOpen = ref(false);
const createTab = ref<RegistryTab>("molds");
const reason = ref("Demo registry maintenance");
const searchInput = ref("");
const view = ref<RegistryView>("table");

const filters = reactive({
  q: "",
  project_id: "",
  part_id: "",
  mold_type: "",
  product_type: "",
  material_code: "",
  status: "",
  revision_status: "",
  has_cad: "" as "" | "true" | "false",
  sort: "-updated_at",
  page: 1,
});

const projectForm = reactive({ code: "", name: "", description: "" });
const partForm = reactive({ project_id: "", part_number: "", name: "", product_type: "", material_code: "" });
const moldForm = reactive({ project_id: "", product_part_id: "", mold_code: "", name: "", mold_type: "injection", cavity_count: 1 });
const revisionForm = reactive({ mold_id: "", revision_code: "", change_summary: "" });

const canManage = computed(() => props.currentAccount?.permissions.includes("registry:manage") || false);
const availableParts = computed(() => parts.value.filter((item) => !filters.project_id || item.project_id === filters.project_id));
const activeParts = computed(() => parts.value.filter((item) => !moldForm.project_id || item.project_id === moldForm.project_id));
const activeFilterCount = computed(() => [
  filters.q,
  filters.project_id,
  filters.part_id,
  filters.mold_type,
  filters.product_type,
  filters.material_code,
  filters.status,
  filters.revision_status,
  filters.has_cad,
].filter(Boolean).length);
const pageStart = computed(() => pageInfo.value.total ? (pageInfo.value.number - 1) * pageInfo.value.size + 1 : 0);
const pageEnd = computed(() => Math.min(pageInfo.value.number * pageInfo.value.size, pageInfo.value.total));
const totalPages = computed(() => Math.max(1, Math.ceil(pageInfo.value.total / pageInfo.value.size)));

const treeGroups = computed<TreeProjectGroup[]>(() => {
  const grouped = new Map<string, TreeProjectGroup>();
  molds.value.forEach((mold) => {
    let project = grouped.get(mold.project_id);
    if (!project) {
      project = { key: mold.project_id, code: mold.project_code, name: projectName(mold.project_id), parts: [] };
      grouped.set(mold.project_id, project);
    }
    const partKey = mold.product_part_id || "unassigned";
    let part = project.parts.find((item) => item.key === partKey);
    if (!part) {
      part = { key: partKey, label: mold.part_number || t("Unassigned product / part"), molds: [] };
      project.parts.push(part);
    }
    part.molds.push(mold);
  });
  return [...grouped.values()];
});

function projectName(id: string): string {
  return projects.value.find((item) => item.id === id)?.name || "";
}

function masterLabel(kind: "product_type" | "material" | "mold_type", code: string): string {
  if (!code) return t("Not specified");
  const item = props.masterDataOptions[kind].find((option) => option.code === code);
  if (!item) return code;
  return locale.value === "zh-TW" ? item.name_zh_tw : item.name_en;
}

function formatDate(value?: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale.value === "zh-TW" ? "zh-TW" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function readUrlState(): void {
  const params = new URLSearchParams(window.location.search);
  filters.q = params.get("q") || "";
  searchInput.value = filters.q;
  filters.project_id = params.get("project_id") || "";
  filters.part_id = params.get("part_id") || "";
  filters.mold_type = params.get("mold_type") || "";
  filters.product_type = params.get("product_type") || "";
  filters.material_code = params.get("material_code") || "";
  filters.status = params.get("status") || "";
  filters.revision_status = params.get("revision_status") || "";
  filters.has_cad = params.get("has_cad") === "true" || params.get("has_cad") === "false"
    ? params.get("has_cad") as "true" | "false"
    : "";
  filters.sort = params.get("sort") || "-updated_at";
  filters.page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  view.value = params.get("view") === "tree" ? "tree" : "table";
}

function syncUrlState(): void {
  const params = new URLSearchParams(window.location.search);
  ["q", "project_id", "part_id", "mold_type", "product_type", "material_code", "status", "revision_status", "has_cad", "sort", "page", "view"].forEach((key) => params.delete(key));
  Object.entries(filters).forEach(([key, value]) => {
    if (key === "page" && value === 1) return;
    if (key === "sort" && value === "-updated_at") return;
    if (value !== "") params.set(key, String(value));
  });
  if (view.value === "tree") params.set("view", "tree");
  const query = params.toString();
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [overviewPayload, projectPayload, partPayload, moldPayload] = await Promise.all([
      fetchRegistryOverview(),
      fetchRegistryProjects({ page_size: 100, sort: "code" }),
      fetchRegistryParts({ page_size: 100, sort: "part_number" }),
      fetchRegistryMolds({
        q: filters.q,
        project_id: filters.project_id,
        part_id: filters.part_id,
        mold_type: filters.mold_type,
        product_type: filters.product_type,
        material_code: filters.material_code,
        status: filters.status,
        revision_status: filters.revision_status,
        has_cad: filters.has_cad || undefined,
        view: view.value,
        sort: filters.sort,
        page: filters.page,
        page_size: 25,
      }),
    ]);
    overview.value = overviewPayload;
    projects.value = projectPayload.items;
    parts.value = partPayload.items;
    molds.value = moldPayload.items;
    pageInfo.value = moldPayload.page;
    if (filters.page > totalPages.value) {
      filters.page = totalPages.value;
      syncUrlState();
      await load();
      return;
    }
    if (!partForm.project_id) partForm.project_id = projects.value[0]?.id || "";
    if (!moldForm.project_id) moldForm.project_id = projects.value[0]?.id || "";
    if (!revisionForm.mold_id) revisionForm.mold_id = molds.value[0]?.id || "";
    if (!props.masterDataOptions.mold_type.some((item) => item.code === moldForm.mold_type)) {
      moldForm.mold_type = props.masterDataOptions.mold_type[0]?.code || "";
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load mold registry.");
  } finally {
    loading.value = false;
  }
}

async function applyFilters(): Promise<void> {
  if (filters.part_id && filters.part_id !== "unassigned" && !availableParts.value.some((item) => item.id === filters.part_id)) filters.part_id = "";
  filters.page = 1;
  syncUrlState();
  await load();
}

async function submitSearch(): Promise<void> {
  filters.q = searchInput.value.trim();
  await applyFilters();
}

async function clearFilters(): Promise<void> {
  Object.assign(filters, {
    q: "", project_id: "", part_id: "", mold_type: "", product_type: "", material_code: "",
    status: "", revision_status: "", has_cad: "", sort: "-updated_at", page: 1,
  });
  searchInput.value = "";
  syncUrlState();
  await load();
}

async function setView(next: RegistryView): Promise<void> {
  if (view.value === next) return;
  view.value = next;
  filters.page = 1;
  syncUrlState();
  await load();
}

async function goToPage(page: number): Promise<void> {
  filters.page = Math.min(totalPages.value, Math.max(1, page));
  syncUrlState();
  await load();
}

function openCreate(tab: RegistryTab = "molds"): void {
  createTab.value = tab;
  createOpen.value = true;
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
    false,
  );
}

async function mutate(action: () => Promise<unknown>, success: string, close = true): Promise<void> {
  if (!reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  busy.value = true;
  error.value = null;
  try {
    await action();
    if (close) createOpen.value = false;
    await load();
    pushToast(success, "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Registry change failed.");
    pushToast(error.value, "error");
  } finally {
    busy.value = false;
  }
}

function handlePopState(): void {
  readUrlState();
  void load();
}

onMounted(() => {
  readUrlState();
  window.addEventListener("popstate", handlePopState);
  void load();
});
onBeforeUnmount(() => window.removeEventListener("popstate", handlePopState));
</script>

<template>
  <section class="mold-registry-workspace" aria-labelledby="registry-title">
    <header class="registry-hero">
      <div>
        <p class="eyebrow">{{ t("Governance / Mold registry") }}</p>
        <h2 id="registry-title">{{ t("Mold registry") }}</h2>
        <p>{{ t("Manage mold identities, revisions and complete engineering history.") }}</p>
      </div>
      <div class="registry-primary-actions">
        <button type="button" class="secondary-button" :disabled="loading" @click="load">{{ t("Refresh registry") }}</button>
        <button v-if="canManage" type="button" @click="openCreate('molds')">＋ {{ t("Add data") }}</button>
      </div>
    </header>

    <div class="registry-summary" :aria-label="t('Registry overview')">
      <button type="button" @click="clearFilters"><span>{{ t("Active projects") }}</span><strong>{{ overview.counts.active_projects }}</strong></button>
      <button type="button" @click="filters.status = 'active'; applyFilters()"><span>{{ t("Active molds") }}</span><strong>{{ overview.counts.active_molds }}</strong></button>
      <button type="button" @click="filters.revision_status = 'released'; applyFilters()"><span>{{ t("Released revisions") }}</span><strong>{{ overview.counts.released_revisions }}</strong></button>
      <button type="button" @click="filters.revision_status = 'draft'; applyFilters()"><span>{{ t("Draft revisions") }}</span><strong>{{ overview.counts.draft_revisions }}</strong></button>
      <button type="button" @click="filters.revision_status = 'released'; filters.has_cad = 'false'; applyFilters()"><span>{{ t("Released without CAD") }}</span><strong>{{ overview.counts.released_without_cad }}</strong></button>
      <button type="button" @click="filters.status = 'active'; filters.part_id = 'unassigned'; applyFilters()"><span>{{ t("Pending mapping") }}</span><strong>{{ overview.counts.pending_mapping }}</strong></button>
    </div>

    <section class="registry-discovery" aria-labelledby="registry-list-title">
      <div class="registry-discovery-heading">
        <div><p class="eyebrow">{{ t("Governed mold records") }}</p><h3 id="registry-list-title">{{ t("Mold list") }}</h3></div>
        <div class="registry-view-switch" role="group" :aria-label="t('View mode')">
          <button type="button" :class="{ active: view === 'table' }" :aria-pressed="view === 'table'" @click="setView('table')">{{ t("Table") }}</button>
          <button type="button" :class="{ active: view === 'tree' }" :aria-pressed="view === 'tree'" @click="setView('tree')">{{ t("Hierarchy") }}</button>
        </div>
      </div>

      <form class="registry-search" role="search" @submit.prevent="submitSearch">
        <label for="registry-search-input">{{ t("Search mold registry") }}</label>
        <div>
          <input id="registry-search-input" v-model="searchInput" type="search" :placeholder="t('Search project, part, mold or revision code')" />
          <button type="submit">{{ t("Search") }}</button>
        </div>
      </form>

      <details class="registry-filter-panel" :open="activeFilterCount > 0">
        <summary>{{ t("Filters") }} <span v-if="activeFilterCount">{{ activeFilterCount }}</span></summary>
        <div class="registry-filter-grid">
          <FormField v-slot="{ fieldId }" :label="t('Project')"><select :id="fieldId" v-model="filters.project_id" @change="applyFilters"><option value="">{{ t("All projects") }}</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.code }} · {{ project.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product / part')"><select :id="fieldId" v-model="filters.part_id" @change="applyFilters"><option value="">{{ t("All parts") }}</option><option value="unassigned">{{ t("Unassigned") }}</option><option v-for="part in availableParts" :key="part.id" :value="part.id">{{ part.part_number }} · {{ part.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold type')"><select :id="fieldId" v-model="filters.mold_type" @change="applyFilters"><option value="">{{ t("All mold types") }}</option><option v-for="option in masterDataOptions.mold_type" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product type')"><select :id="fieldId" v-model="filters.product_type" @change="applyFilters"><option value="">{{ t("All product types") }}</option><option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material')"><select :id="fieldId" v-model="filters.material_code" @change="applyFilters"><option value="">{{ t("All materials") }}</option><option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold status')"><select :id="fieldId" v-model="filters.status" @change="applyFilters"><option value="">{{ t("All statuses") }}</option><option value="active">{{ t("active") }}</option><option value="retired">{{ t("retired") }}</option><option value="archived">{{ t("archived") }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Revision status')"><select :id="fieldId" v-model="filters.revision_status" @change="applyFilters"><option value="">{{ t("All statuses") }}</option><option value="draft">{{ t("draft") }}</option><option value="released">{{ t("released") }}</option><option value="superseded">{{ t("superseded") }}</option><option value="archived">{{ t("archived") }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('CAD status')"><select :id="fieldId" v-model="filters.has_cad" @change="applyFilters"><option value="">{{ t("Any CAD status") }}</option><option value="true">{{ t("Has CAD") }}</option><option value="false">{{ t("No CAD") }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Sort by')"><select :id="fieldId" v-model="filters.sort" @change="applyFilters"><option value="-updated_at">{{ t("Recently updated") }}</option><option value="mold_code">{{ t("Mold code A-Z") }}</option><option value="-mold_code">{{ t("Mold code Z-A") }}</option><option value="project_code">{{ t("Project code") }}</option><option value="status">{{ t("Status") }}</option></select></FormField>
        </div>
        <button v-if="activeFilterCount" type="button" class="text-button" @click="clearFilters">{{ t("Clear all filters") }}</button>
      </details>

      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <p v-if="loading" class="workspace-state" aria-live="polite">{{ t("Loading mold registry...") }}</p>

      <template v-else>
        <div v-if="molds.length && view === 'table'" class="registry-table-wrap">
          <table class="registry-table">
            <thead><tr><th>{{ t("Mold") }}</th><th>{{ t("Project / part") }}</th><th>{{ t("Mold type") }}</th><th>{{ t("Cavities") }}</th><th>{{ t("Current revision") }}</th><th>{{ t("CAD") }}</th><th>{{ t("Status") }}</th><th>{{ t("Last updated") }}</th><th><span class="sr-only">{{ t("Actions") }}</span></th></tr></thead>
            <tbody>
              <tr v-for="mold in molds" :key="mold.id">
                <td :data-label="t('Mold')"><strong>{{ mold.mold_code }}</strong><span>{{ mold.name }}</span></td>
                <td :data-label="t('Project / part')"><strong>{{ mold.project_code }}</strong><span>{{ mold.part_number || t("Unassigned") }}</span></td>
                <td :data-label="t('Mold type')">{{ masterLabel('mold_type', mold.mold_type) }}</td>
                <td :data-label="t('Cavities')">{{ mold.cavity_count }}</td>
                <td :data-label="t('Current revision')">{{ mold.current_revision_code || t("No released revision") }}</td>
                <td :data-label="t('CAD')">{{ mold.artifact_count }}</td>
                <td :data-label="t('Status')"><em :class="`status-${mold.status}`">{{ t(mold.status) }}</em></td>
                <td :data-label="t('Last updated')">{{ formatDate(mold.updated_at) }}</td>
                <td class="registry-row-actions"><a class="secondary-button" :href="`/data/molds/${mold.id}`">{{ t("View") }}</a></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="molds.length" class="registry-tree">
          <details v-for="project in treeGroups" :key="project.key" open>
            <summary><span>{{ t("Project") }}</span><strong>{{ project.code }}</strong><small>{{ project.name }}</small></summary>
            <div class="registry-tree-branch">
              <details v-for="part in project.parts" :key="part.key" open>
                <summary><span>{{ t("Product / part") }}</span><strong>{{ part.label }}</strong><small>{{ part.molds.length }} {{ t("molds") }}</small></summary>
                <div class="registry-tree-branch">
                  <article v-for="mold in part.molds" :key="mold.id" class="registry-tree-mold">
                    <div><span>{{ t("Mold") }}</span><strong>{{ mold.mold_code }}</strong><small>{{ mold.name }} · {{ masterLabel('mold_type', mold.mold_type) }}</small></div>
                    <em :class="`status-${mold.status}`">{{ t(mold.status) }}</em>
                    <a class="secondary-button" :href="`/data/molds/${mold.id}`">{{ t("View") }}</a>
                    <div v-if="mold.revisions?.length" class="registry-tree-revisions">
                      <div v-for="revision in mold.revisions" :key="revision.id">
                        <span>{{ t("Revision") }}</span><strong>{{ revision.revision_code }}</strong><em :class="`status-${revision.status}`">{{ t(revision.status) }}</em><small>{{ revision.artifact_count }} {{ t("CAD artifacts") }}</small>
                        <button v-if="canManage && revision.status === 'draft'" type="button" class="text-button" :disabled="busy" @click="releaseRevision(revision)">{{ t("Release") }}</button>
                      </div>
                    </div>
                    <p v-else class="registry-tree-empty">{{ t("No revisions yet") }}</p>
                  </article>
                </div>
              </details>
            </div>
          </details>
        </div>

        <WorkspaceEmptyState v-else eyebrow="" :title="t('No matching molds')" :message="t('Adjust the search or filters, or add the first governed mold record.')" :action-label="canManage ? t('Add data') : ''" @action="openCreate('molds')" />

        <nav v-if="pageInfo.total" class="registry-pagination" :aria-label="t('Registry pagination')">
          <p>{{ t("Showing {start}-{end} of {total}", { start: pageStart, end: pageEnd, total: pageInfo.total }) }}</p>
          <div><button type="button" class="secondary-button" :disabled="pageInfo.number <= 1" @click="goToPage(pageInfo.number - 1)">{{ t("Previous") }}</button><span>{{ t("Page {page} of {pages}", { page: pageInfo.number, pages: totalPages }) }}</span><button type="button" class="secondary-button" :disabled="!pageInfo.has_next" @click="goToPage(pageInfo.number + 1)">{{ t("Next") }}</button></div>
        </nav>
      </template>
    </section>

    <div v-if="createOpen && canManage" class="registry-drawer-backdrop" @click.self="createOpen = false">
      <form class="registry-editor" role="dialog" aria-modal="true" :aria-label="t('Add governed registry data')" @submit.prevent="createTab === 'projects' ? submitProject() : createTab === 'parts' ? submitPart() : createTab === 'molds' ? submitMold() : submitRevision()">
        <header><div><p class="eyebrow">{{ t("Create controlled record") }}</p><h3>{{ t("Add data") }}</h3></div><button type="button" class="icon-button" :aria-label="t('Close')" @click="createOpen = false">×</button></header>
        <div class="registry-tabs" role="tablist" :aria-label="t('Registry domains')">
          <button v-for="item in (['projects', 'parts', 'molds', 'revisions'] as RegistryTab[])" :key="item" type="button" role="tab" :aria-selected="createTab === item" :class="{ active: createTab === item }" @click="createTab = item">{{ t(item) }}</button>
        </div>
        <template v-if="createTab === 'projects'">
          <FormField v-slot="{ fieldId }" :label="t('Project code')" required><input :id="fieldId" v-model="projectForm.code" required pattern="[A-Za-z0-9][A-Za-z0-9._/-]*" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Project name')" required><input :id="fieldId" v-model="projectForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Description')"><textarea :id="fieldId" v-model="projectForm.description" rows="3"></textarea></FormField>
        </template>
        <template v-else-if="createTab === 'parts'">
          <FormField v-slot="{ fieldId }" :label="t('Project')" required><select :id="fieldId" v-model="partForm.project_id" required><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.code }} · {{ project.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Part number')" required><input :id="fieldId" v-model="partForm.part_number" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Part name')" required><input :id="fieldId" v-model="partForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product type')"><select :id="fieldId" v-model="partForm.product_type"><option value="">{{ t("Not specified") }}</option><option v-for="option in masterDataOptions.product_type" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material')"><select :id="fieldId" v-model="partForm.material_code"><option value="">{{ t("Not specified") }}</option><option v-for="option in masterDataOptions.material" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
        </template>
        <template v-else-if="createTab === 'molds'">
          <FormField v-slot="{ fieldId }" :label="t('Project')" required><select :id="fieldId" v-model="moldForm.project_id" required><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.code }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product / part')"><select :id="fieldId" v-model="moldForm.product_part_id"><option value="">{{ t("Not specified") }}</option><option v-for="part in activeParts" :key="part.id" :value="part.id">{{ part.part_number }} · {{ part.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold code')" required><input :id="fieldId" v-model="moldForm.mold_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold name')" required><input :id="fieldId" v-model="moldForm.name" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold type')" required :helper="t('Choose an active value maintained in Engineering reference data.')"><select :id="fieldId" v-model="moldForm.mold_type" required><option value="" disabled>{{ t("Select a mold type") }}</option><option v-for="option in masterDataOptions.mold_type" :key="option.id" :value="option.code">{{ locale === 'zh-TW' ? option.name_zh_tw : option.name_en }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Cavity count')" required><input :id="fieldId" v-model.number="moldForm.cavity_count" type="number" min="1" max="128" required /></FormField>
        </template>
        <template v-else>
          <FormField v-slot="{ fieldId }" :label="t('Mold')" required><select :id="fieldId" v-model="revisionForm.mold_id" required><option v-for="mold in molds" :key="mold.id" :value="mold.id">{{ mold.mold_code }} · {{ mold.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Revision code')" required><input :id="fieldId" v-model="revisionForm.revision_code" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Change summary')"><textarea :id="fieldId" v-model="revisionForm.change_summary" rows="3"></textarea></FormField>
        </template>
        <FormField v-slot="{ fieldId }" :label="t('Change reason')" required><input :id="fieldId" v-model="reason" required /></FormField>
        <footer><button type="button" class="secondary-button" @click="createOpen = false">{{ t("Cancel") }}</button><button type="submit" :disabled="busy">{{ busy ? t("Saving...") : t("Create record") }}</button></footer>
      </form>
    </div>
  </section>
</template>
