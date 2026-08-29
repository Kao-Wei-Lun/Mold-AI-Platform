<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import type { LocalAccount } from "../api/identity";
import {
  archiveMasterData,
  createMasterData,
  fetchMasterData,
  updateMasterData,
  type MasterDataItem,
  type MasterDataKind,
  type MasterDataStatus,
} from "../api/masterData";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import FormField from "./FormField.vue";
import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

const props = defineProps<{ currentAccount: LocalAccount | null }>();
const emit = defineEmits<{ changed: [] }>();
const { locale, t } = useI18n();

const kinds: Array<{ code: MasterDataKind; label: string }> = [
  { code: "dataset", label: "Datasets" },
  { code: "product_type", label: "Product types" },
  { code: "material", label: "Materials" },
  { code: "machine", label: "Machines" },
  { code: "defect", label: "Defects" },
  { code: "location", label: "Locations" },
  { code: "unit", label: "Units" },
];

const selectedKind = ref<MasterDataKind>("dataset");
const statusFilter = ref<MasterDataStatus | "">("");
const search = ref("");
const page = ref(1);
const pageSize = 25;
const total = ref(0);
const items = ref<MasterDataItem[]>([]);
const selectedId = ref("");
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const createMode = ref(false);
const reason = ref("");
const attributesJson = ref("{}");
const aliasesText = ref("");
const form = reactive({
  code: "",
  name_en: "",
  name_zh_tw: "",
  description_en: "",
  description_zh_tw: "",
  sort_order: 100,
});

const canManage = computed(() => props.currentAccount?.permissions.includes("master-data:manage") || false);
const selected = computed(() => items.value.find((item) => item.id === selectedId.value) || null);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const activeCount = computed(() => items.value.filter((item) => item.status === "active").length);

function displayName(item: MasterDataItem): string {
  return locale.value === "zh-TW" ? item.name_zh_tw : item.name_en;
}

function resetForm(): void {
  Object.assign(form, {
    code: "",
    name_en: "",
    name_zh_tw: "",
    description_en: "",
    description_zh_tw: "",
    sort_order: 100,
  });
  attributesJson.value = "{}";
  aliasesText.value = "";
  reason.value = "";
}

function syncForm(item: MasterDataItem | null): void {
  if (!item || createMode.value) return;
  Object.assign(form, {
    code: item.code,
    name_en: item.name_en,
    name_zh_tw: item.name_zh_tw,
    description_en: item.description_en,
    description_zh_tw: item.description_zh_tw,
    sort_order: item.sort_order,
  });
  attributesJson.value = JSON.stringify(item.attributes, null, 2);
  aliasesText.value = item.aliases.join(", ");
  reason.value = "";
}

watch(selected, syncForm, { immediate: true });

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const payload = await fetchMasterData({
      kind: selectedKind.value,
      status: statusFilter.value,
      search: search.value.trim(),
      sort: "sort_order",
      page: page.value,
      pageSize,
    });
    items.value = payload.results;
    total.value = payload.pagination.total;
    if (!items.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = items.value[0]?.id || "";
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load master data.");
  } finally {
    loading.value = false;
  }
}

function chooseKind(kind: MasterDataKind): void {
  selectedKind.value = kind;
  page.value = 1;
  selectedId.value = "";
  createMode.value = false;
  load();
}

function beginCreate(): void {
  createMode.value = true;
  selectedId.value = "";
  resetForm();
}

function cancelCreate(): void {
  createMode.value = false;
  selectedId.value = items.value[0]?.id || "";
  syncForm(selected.value);
}

function parsedAttributes(): Record<string, unknown> {
  const parsed = JSON.parse(attributesJson.value || "{}");
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(t("Attributes must be a JSON object."));
  }
  return parsed as Record<string, unknown>;
}

async function save(): Promise<void> {
  if (!canManage.value) return;
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    const attributes = parsedAttributes();
    if (!reason.value.trim()) throw new Error(t("A change reason is required."));
    const aliases = aliasesText.value.split(",").map((alias) => alias.trim()).filter(Boolean);
    if (createMode.value) {
      const created = await createMasterData({
        kind: selectedKind.value,
        ...form,
        attributes,
        aliases,
        reason: reason.value.trim(),
      });
      notice.value = t("Master-data item created.");
      createMode.value = false;
      await load();
      selectedId.value = created.id;
    } else if (selected.value) {
      const updated = await updateMasterData(selected.value, {
        name_en: form.name_en,
        name_zh_tw: form.name_zh_tw,
        description_en: form.description_en,
        description_zh_tw: form.description_zh_tw,
        sort_order: form.sort_order,
        attributes,
        aliases,
        reason: reason.value.trim(),
      });
      const index = items.value.findIndex((item) => item.id === updated.id);
      if (index >= 0) items.value[index] = updated;
      reason.value = "";
      notice.value = t("Master-data item updated.");
    }
    emit("changed");
    pushToast(notice.value || t("Master data saved."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to save master data.");
    pushToast(error.value, "error");
  } finally {
    busy.value = false;
  }
}

async function setStatus(status: MasterDataStatus): Promise<void> {
  const item = selected.value;
  if (!item || !reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  if (!window.confirm(t("Confirm status change for {code}?", { code: item.code }))) return;
  busy.value = true;
  error.value = null;
  try {
    const updated = status === "archived"
      ? await archiveMasterData(item, reason.value.trim())
      : await updateMasterData(item, { status, reason: reason.value.trim() });
    const index = items.value.findIndex((candidate) => candidate.id === updated.id);
    if (index >= 0) items.value[index] = updated;
    reason.value = "";
    notice.value = t("Lifecycle status updated.");
    emit("changed");
    pushToast(notice.value, "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to update lifecycle status.");
  } finally {
    busy.value = false;
  }
}

function referenceText(item: MasterDataItem): string {
  const references = Object.entries(item.references || {});
  return references.length
    ? references.map(([kind, count]) => `${kind.replaceAll("_", " ")}: ${count}`).join(" · ")
    : t("No engineering references");
}

onMounted(load);
</script>

<template>
  <section class="master-data-workspace" aria-labelledby="master-data-title">
    <div class="section-heading">
      <div><p class="eyebrow">{{ t("Canonical catalog") }}</p><h2 id="master-data-title">{{ t("Govern engineering master data") }}</h2></div>
      <button v-if="canManage" type="button" @click="beginCreate">{{ t("Create item") }}</button>
    </div>

    <div class="master-data-summary">
      <div><span>{{ t("Selected domain") }}</span><strong>{{ t(kinds.find((kind) => kind.code === selectedKind)?.label || selectedKind) }}</strong></div>
      <div><span>{{ t("Matching records") }}</span><strong>{{ total }}</strong></div>
      <div><span>{{ t("Active on this page") }}</span><strong>{{ activeCount }}</strong></div>
      <div><span>{{ t("Cache SLA") }}</span><strong>≤ 60 s</strong></div>
    </div>

    <div class="master-data-kind-tabs" role="tablist" :aria-label="t('Master-data domains')">
      <button v-for="kind in kinds" :key="kind.code" type="button" role="tab" :aria-selected="selectedKind === kind.code" :class="{ active: selectedKind === kind.code }" @click="chooseKind(kind.code)">{{ t(kind.label) }}</button>
    </div>

    <form class="master-data-filters" @submit.prevent="page = 1; load()">
      <label><span>{{ t("Search") }}</span><input v-model="search" type="search" :placeholder="t('Code or bilingual name')" /></label>
      <label><span>{{ t("Lifecycle status") }}</span><select v-model="statusFilter"><option value="">{{ t("All statuses") }}</option><option value="active">{{ t("active") }}</option><option value="inactive">{{ t("inactive") }}</option><option value="archived">{{ t("archived") }}</option></select></label>
      <button type="submit" class="secondary-button">{{ t("Apply filters") }}</button>
    </form>

    <p v-if="error" class="error-message" role="alert">{{ error }} <button type="button" class="text-button" @click="load">{{ t("Retry") }}</button></p>
    <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
    <p v-if="loading" class="workspace-state">{{ t("Loading governed master data...") }}</p>

    <WorkspaceEmptyState v-else-if="!items.length && !createMode" :eyebrow="t('No records')" :title="t('No master data matches these filters')" :message="t('Clear filters or create the first controlled code in this domain.')" :action-label="canManage ? t('Create item') : ''" @action="beginCreate" />

    <div v-else class="master-data-layout">
      <div class="master-data-list" role="listbox" :aria-label="t('Master-data records')">
        <button v-for="item in items" :key="item.id" type="button" role="option" :aria-selected="selectedId === item.id" :class="{ selected: selectedId === item.id }" @click="createMode = false; selectedId = item.id">
          <span><strong>{{ displayName(item) }}</strong><code>{{ item.code }}</code></span>
          <small :class="`status-${item.status}`">{{ t(item.status) }}</small>
          <em>{{ referenceText(item) }}</em>
        </button>
        <div class="pagination-controls">
          <button type="button" class="text-button" :disabled="page <= 1" @click="page--; load()">{{ t("Previous") }}</button>
          <span>{{ page }} / {{ totalPages }}</span>
          <button type="button" class="text-button" :disabled="page >= totalPages" @click="page++; load()">{{ t("Next") }}</button>
        </div>
      </div>

      <form class="master-data-editor" @submit.prevent="save">
        <div class="editor-heading"><div><p class="eyebrow">{{ createMode ? t("New controlled code") : t("Selected record") }}</p><h3>{{ createMode ? t("Create {kind}", { kind: t(selectedKind) }) : selected?.code }}</h3></div><button v-if="createMode" type="button" class="text-button" @click="cancelCreate">{{ t("Cancel") }}</button></div>
        <div class="master-data-form-grid">
          <FormField v-slot="{ fieldId }" :label="t('Canonical code')" required :helper="createMode ? t('Code becomes immutable after creation.') : t('Immutable after creation; use aliases or a new code.')"><input :id="fieldId" v-model="form.code" required maxlength="128" pattern="[A-Za-z0-9][A-Za-z0-9._/-]*" :disabled="!createMode" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Sort order')" required><input :id="fieldId" v-model.number="form.sort_order" type="number" min="0" required /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('English name')" required><input :id="fieldId" v-model="form.name_en" required maxlength="255" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Traditional Chinese name')" required><input :id="fieldId" v-model="form.name_zh_tw" required maxlength="255" lang="zh-Hant" /></FormField>
          <FormField v-slot="{ fieldId }" :label="t('English description')"><textarea :id="fieldId" v-model="form.description_en" rows="3"></textarea></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Traditional Chinese description')"><textarea :id="fieldId" v-model="form.description_zh_tw" rows="3" lang="zh-Hant"></textarea></FormField>
          <FormField v-slot="{ fieldId }" class="form-wide" :label="t('Domain attributes (JSON)')" :helper="t('Use governed domain fields such as family, tonnage, severity, symbol or HMI profile.')"><textarea :id="fieldId" v-model="attributesJson" rows="6" spellcheck="false"></textarea></FormField>
          <FormField v-slot="{ fieldId }" class="form-wide" :label="t('Aliases')" :helper="t('Optional comma-separated legacy or source-system codes.')"><input :id="fieldId" v-model="aliasesText" maxlength="1000" /></FormField>
          <FormField v-slot="{ fieldId }" class="form-wide" :label="t('Change reason')" required :helper="t('Required for audit evidence and lifecycle changes.')"><input :id="fieldId" v-model="reason" required maxlength="512" /></FormField>
        </div>
        <div v-if="selected && !createMode" class="reference-summary"><span>{{ t("Reference summary") }}</span><strong>{{ referenceText(selected) }}</strong><small>{{ t("Historical records keep their canonical code after deactivation or archive.") }}</small></div>
        <div class="master-data-actions">
          <button type="submit" :disabled="busy || !canManage">{{ busy ? t("Saving...") : createMode ? t("Create item") : t("Save changes") }}</button>
          <template v-if="selected && !createMode && canManage">
            <button v-if="selected.status !== 'active'" type="button" class="secondary-button" :disabled="busy" @click="setStatus('active')">{{ t("Activate") }}</button>
            <button v-if="selected.status === 'active'" type="button" class="secondary-button" :disabled="busy" @click="setStatus('inactive')">{{ t("Deactivate") }}</button>
            <button v-if="selected.status !== 'archived'" type="button" class="danger-button" :disabled="busy" @click="setStatus('archived')">{{ t("Archive") }}</button>
          </template>
        </div>
      </form>
    </div>
  </section>
</template>
