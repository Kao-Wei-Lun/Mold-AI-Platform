<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from "vue";

import { fetchCADArtifactDetail, fetchCADHistory, type CADArtifactSummary, type CADHistorySummary } from "../api/cad";
import {
  fetchRegistry,
  fetchRegistryMoldDetail,
  fetchRegistryPartDetail,
  fetchRegistryProjectDetail,
  fetchRegistryRevisionDetail,
  type RegistryMold,
  type RegistryPart,
  type RegistryProject,
  type RegistryRevision,
} from "../api/registry";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RecordHeader from "./RecordHeader.vue";

const CadPreview = defineAsyncComponent(() => import("./CadPreview.vue"));
const props = defineProps<{ domain: "molds" | "cad-artifacts"; path: string }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();
const loading = ref(false);
const error = ref<string | null>(null);
const projects = ref<RegistryProject[]>([]);
const parts = ref<RegistryPart[]>([]);
const molds = ref<RegistryMold[]>([]);
const revisions = ref<RegistryRevision[]>([]);
const project = ref<RegistryProject | null>(null);
const part = ref<RegistryPart | null>(null);
const mold = ref<RegistryMold | null>(null);
const revision = ref<RegistryRevision | null>(null);
const artifacts = ref<CADHistorySummary[]>([]);
const artifact = ref<CADArtifactSummary | null>(null);

const location = computed(() => new URL(props.path, window.location.origin));
const segments = computed(() => location.value.pathname.split("/").filter(Boolean));
const activeTab = computed(() => location.value.searchParams.get("tab") || "overview");
const registryView = computed(() => location.value.searchParams.get("view") || "molds");
const registryKind = computed(() => ["projects", "parts", "revisions"].includes(segments.value[2]) ? segments.value[2] : "molds");
const recordId = computed(() => registryKind.value === "molds" ? (segments.value[2] || "") : (segments.value[3] || ""));
const cadId = computed(() => segments.value[2] || "");
const cadModels = computed(() => (artifact.value?.jobs || []).flatMap((job) => job.result ? [job.result] : []));

function pretty(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function setTab(tab: string): void {
  const base = props.domain === "cad-artifacts" ? `/data/cad-artifacts/${cadId.value}` : location.value.pathname;
  emit("navigate", `${base}?tab=${tab}`);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  project.value = null;
  part.value = null;
  mold.value = null;
  revision.value = null;
  artifact.value = null;
  try {
    if (props.domain === "cad-artifacts") {
      if (cadId.value) artifact.value = await fetchCADArtifactDetail(cadId.value);
      else artifacts.value = await fetchCADHistory();
    } else if (!recordId.value) {
      const payload = await fetchRegistry();
      projects.value = payload.projects;
      parts.value = payload.parts;
      molds.value = payload.molds;
      revisions.value = payload.revisions;
    } else if (registryKind.value === "projects") {
      project.value = await fetchRegistryProjectDetail(recordId.value);
    } else if (registryKind.value === "parts") {
      part.value = await fetchRegistryPartDetail(recordId.value);
    } else if (registryKind.value === "revisions") {
      revision.value = await fetchRegistryRevisionDetail(recordId.value);
    } else {
      mold.value = await fetchRegistryMoldDetail(recordId.value);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load historical data.");
  } finally {
    loading.value = false;
  }
}

watch(() => [props.domain, location.value.pathname], load, { immediate: true });
</script>

<template>
  <section class="registry-cad-history">
    <div class="history-list-heading">
      <div><p class="eyebrow">{{ t("Historical data") }}</p><h2>{{ t(domain === "molds" ? "Molds & revisions" : "CAD artifacts") }}</h2></div>
      <div class="history-list-actions">
        <button v-if="recordId || cadId" type="button" class="text-button" @click="emit('navigate', domain === 'molds' ? '/data/molds' : '/data/cad-artifacts')">← {{ t("Back to records") }}</button>
        <button type="button" :disabled="loading" @click="load">{{ t("Refresh data") }}</button>
      </div>
    </div>
    <p v-if="error" class="error-message" role="alert">{{ error }} <button type="button" @click="load">{{ t("Retry") }}</button></p>
    <section v-else-if="loading" class="workspace-state">{{ t("Loading complete historical record…") }}</section>

    <template v-else-if="domain === 'molds' && !recordId">
      <div class="registry-history-tabs">
        <button v-for="view in ['projects', 'parts', 'molds', 'revisions']" :key="view" type="button" :class="{ active: registryView === view }" @click="emit('navigate', `/data/molds?view=${view}`)">{{ t(view[0].toUpperCase() + view.slice(1)) }}</button>
      </div>
      <DataTable v-if="registryView === 'projects'" :columns="[{ key: 'code', label: t('Project code') }, { key: 'name', label: t('Project name') }, { key: 'parts', label: t('Parts') }, { key: 'molds', label: t('Molds') }, { key: 'status', label: t('Status') }]" :items="projects.map((item) => ({ id: item.id, code: item.code, name: item.name, parts: item.part_count, molds: item.mold_count, status: item.status }))" @select="emit('navigate', `/data/molds/projects/${$event.id}`)" />
      <DataTable v-else-if="registryView === 'parts'" :columns="[{ key: 'number', label: t('Part number') }, { key: 'name', label: t('Name') }, { key: 'project', label: t('Project') }, { key: 'product', label: t('Product type') }, { key: 'material', label: t('Material') }]" :items="parts.map((item) => ({ id: item.id, number: item.part_number, name: item.name, project: item.project_code, product: item.product_type, material: item.material_code }))" @select="emit('navigate', `/data/molds/parts/${$event.id}`)" />
      <DataTable v-else-if="registryView === 'revisions'" :columns="[{ key: 'revision', label: t('Revision') }, { key: 'mold', label: t('Mold') }, { key: 'summary', label: t('Change summary') }, { key: 'artifacts', label: t('CAD artifacts') }, { key: 'status', label: t('Status') }]" :items="revisions.map((item) => ({ id: item.id, revision: item.revision_code, mold: item.mold_code, summary: item.change_summary, artifacts: item.artifact_count, status: item.status }))" @select="emit('navigate', `/data/molds/revisions/${$event.id}`)" />
      <DataTable v-else :columns="[{ key: 'code', label: t('Mold code') }, { key: 'name', label: t('Name') }, { key: 'part', label: t('Part number') }, { key: 'type', label: t('Mold type') }, { key: 'cavities', label: t('Cavities') }, { key: 'revisions', label: t('Revisions') }, { key: 'status', label: t('Status') }]" :items="molds.map((item) => ({ id: item.id, code: item.mold_code, name: item.name, part: item.part_number, type: item.mold_type, cavities: item.cavity_count, revisions: item.revision_count, status: item.status }))" @select="emit('navigate', `/data/molds/${$event.id}`)" />
    </template>

    <template v-else-if="project">
      <RecordHeader :title="project.name" :identifier="project.code" :status="project.status" :version="`row ${project.row_version}`" />
      <PropertyGrid :items="[{ label: t('Description'), value: project.description }, { label: t('Scope'), value: project.scope }, { label: t('Classification'), value: project.classification }, { label: t('Parts'), value: project.part_count }, { label: t('Molds'), value: project.mold_count }, { label: t('Updated'), value: project.updated_at ? new Date(project.updated_at).toLocaleString() : '—' }]" />
    </template>

    <template v-else-if="part">
      <RecordHeader :title="part.name" :identifier="part.part_number" :status="part.status" :version="`row ${part.row_version}`" />
      <PropertyGrid :items="[{ label: t('Project'), value: part.project_code }, { label: t('Product type'), value: part.product_type }, { label: t('Material'), value: part.material_code }, { label: t('Molds'), value: part.mold_count || part.molds?.length || 0 }]" />
      <DataTable :columns="[{ key: 'code', label: t('Mold code') }, { key: 'name', label: t('Name') }, { key: 'revisions', label: t('Revisions') }, { key: 'status', label: t('Status') }]" :items="(part.molds || []).map((item) => ({ id: item.id, code: item.mold_code, name: item.name, revisions: item.revision_count, status: item.status }))" @select="emit('navigate', `/data/molds/${$event.id}`)" />
    </template>

    <template v-else-if="mold">
      <RecordHeader :title="mold.name" :identifier="mold.mold_code" :status="mold.status" :version="`row ${mold.row_version}`" />
      <PropertyGrid :items="[{ label: t('Project'), value: mold.project_code }, { label: t('Part number'), value: mold.part_number }, { label: t('Mold type'), value: mold.mold_type }, { label: t('Cavities'), value: mold.cavity_count }, { label: t('Revisions'), value: mold.revisions?.length || 0 }]" />
      <DataTable :columns="[{ key: 'code', label: t('Revision') }, { key: 'summary', label: t('Change summary') }, { key: 'artifacts', label: t('CAD artifacts') }, { key: 'released', label: t('Released at') }, { key: 'status', label: t('Status') }]" :items="(mold.revisions || []).map((item) => ({ id: item.id, code: item.revision_code, summary: item.change_summary, artifacts: item.artifact_count, released: item.released_at ? new Date(item.released_at).toLocaleString() : '—', status: item.status }))" @select="emit('navigate', `/data/molds/revisions/${$event.id}`)" />
    </template>

    <template v-else-if="revision">
      <RecordHeader :title="`${revision.mold_code}@${revision.revision_code}`" :identifier="revision.id" :status="revision.status" :version="`row ${revision.row_version}`" />
      <PropertyGrid :items="[{ label: t('Change summary'), value: revision.change_summary }, { label: t('Source system'), value: revision.source_system }, { label: t('Source revision ID'), value: revision.source_revision_id }, { label: t('Released at'), value: revision.released_at ? new Date(revision.released_at).toLocaleString() : '—' }]" />
      <DataTable :columns="[{ key: 'name', label: t('Artifact name') }, { key: 'versions', label: t('Versions') }, { key: 'jobs', label: t('Jobs') }, { key: 'features', label: t('Feature sets') }, { key: 'reviews', label: t('Design reviews') }, { key: 'quality', label: t('Quality') }, { key: 'status', label: t('Status') }]" :items="(revision.artifacts || []).map((item) => ({ id: item.artifact_id, name: item.name, versions: item.references.versions, jobs: item.references.jobs, features: item.references.feature_sets, reviews: item.references.design_reviews, quality: item.quality_status, status: item.lifecycle_status }))" @select="emit('navigate', `/data/cad-artifacts/${$event.id}`)" />
    </template>

    <template v-else-if="domain === 'cad-artifacts' && !cadId">
      <DataTable :columns="[{ key: 'name', label: t('Artifact name') }, { key: 'dataset', label: t('Dataset') }, { key: 'revision', label: t('Mold revision') }, { key: 'format', label: t('Format') }, { key: 'versions', label: t('Versions') }, { key: 'jobs', label: t('Jobs') }, { key: 'quality', label: t('Quality') }, { key: 'status', label: t('Status') }]" :items="artifacts.map((item) => ({ id: item.artifact_id, name: item.name, dataset: item.dataset_id, revision: item.mold_revision, format: item.latest_format, versions: item.version_count, jobs: item.job_count, quality: item.quality_status, status: item.lifecycle_status }))" @select="emit('navigate', `/data/cad-artifacts/${$event.id}`)" />
    </template>

    <template v-else-if="artifact">
      <RecordHeader :title="artifact.name" :identifier="artifact.artifact_id" :status="artifact.lifecycle_status" :version="`${artifact.versions?.length || 0} versions`" />
      <DetailTabs :tabs="[{ id: 'overview', label: t('Overview') }, { id: 'versions', label: t('Versions'), count: artifact.versions?.length || 0 }, { id: 'geometry', label: t('Geometry'), count: cadModels.length }, { id: 'jobs', label: t('Jobs'), count: artifact.jobs.length }, { id: 'lineage', label: t('Lineage'), count: artifact.lineage?.length || 0 }]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[{ label: t('Dataset'), value: artifact.dataset_id }, { label: t('Mold revision'), value: artifact.mold_revision ? `${artifact.mold_revision.mold_code}@${artifact.mold_revision.revision_code}` : '—' }, { label: t('Product type'), value: artifact.product_type }, { label: t('Material'), value: artifact.material_code }, { label: t('Classification'), value: artifact.classification }, { label: t('Quality'), value: artifact.quality_status }, { label: t('Created'), value: new Date(artifact.created_at).toLocaleString() }]" />
      <DataTable v-else-if="activeTab === 'versions'" :columns="[{ key: 'version', label: t('Version') }, { key: 'file', label: t('File') }, { key: 'format', label: t('Format') }, { key: 'size', label: t('Size') }, { key: 'sha', label: 'SHA-256' }, { key: 'screening', label: t('Malware status') }, { key: 'source', label: t('Source system') }]" :items="(artifact.versions || []).map((item) => ({ id: item.artifact_version_id, version: item.version_number, file: item.original_filename, format: item.format, size: item.size_bytes, sha: item.sha256, screening: item.malware_status, source: item.source_system }))" />
      <div v-else-if="activeTab === 'geometry'" class="history-stack">
        <article v-for="model in cadModels" :key="model.cad_model_id" class="history-detail-card">
          <CadPreview v-if="model.preview?.download_url" :source="model.preview.download_url" />
          <PropertyGrid :items="[{ label: t('Geometry status'), value: model.geometry_status }, { label: t('Parser'), value: `${model.parser.name}@${model.parser.version}` }, { label: t('Unit system'), value: model.unit_system }, { label: t('Bounding box'), value: pretty(model.bounding_box) }, { label: t('Volume'), value: model.volume }, { label: t('Surface area'), value: model.surface_area }, { label: t('Faces / Edges'), value: `${model.face_count} / ${model.edge_count}` }, { label: t('Quality flags'), value: model.quality_flags.join(', ') || '—' }]" />
          <DataTable :columns="[{ key: 'schema', label: t('Feature schema') }, { key: 'extractor', label: t('Extractor') }, { key: 'collection', label: t('Index collection') }, { key: 'version', label: t('Index version') }, { key: 'status', label: t('Status') }]" :items="(model.feature_sets || []).map((item) => ({ id: item.feature_set_id, schema: item.schema_version, extractor: item.extractor_version, collection: item.index_collection, version: item.index_version, status: item.status }))" :empty-text="t('No feature sets recorded.')" />
        </article>
      </div>
      <DataTable v-else-if="activeTab === 'jobs'" :columns="[{ key: 'capability', label: t('Capability') }, { key: 'stage', label: t('Stage') }, { key: 'progress', label: t('Progress') }, { key: 'attempt', label: t('Attempt') }, { key: 'state', label: t('Status') }, { key: 'error', label: t('Error') }]" :items="artifact.jobs.map((item) => ({ id: item.job_id, capability: item.capability, stage: item.stage, progress: `${item.progress}%`, attempt: item.attempt, state: item.state, error: item.error?.code || '—' }))" />
      <DataTable v-else :columns="[{ key: 'relation', label: t('Relationship') }, { key: 'from', label: t('From version') }, { key: 'to', label: t('To version') }, { key: 'direction', label: t('Direction') }, { key: 'job', label: t('Job') }]" :items="(artifact.lineage || []).map((item) => ({ id: item.edge_id, relation: item.relationship, from: item.from_artifact_version_id, to: item.to_artifact_version_id, direction: item.direction, job: item.job_id }))" :empty-text="t('No lineage edges recorded.')" />
    </template>
  </section>
</template>
