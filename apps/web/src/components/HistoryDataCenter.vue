<script setup lang="ts">
import { computed, ref } from "vue";

import { useI18n } from "../i18n";
import type { LocalAccount } from "../api/identity";
import { emptyMasterDataOptions, type MasterDataOptions } from "../api/masterData";
import DataTable from "./DataTable.vue";
import DetailDrawer from "./DetailDrawer.vue";
import EngineeringHistoryWorkspace from "./EngineeringHistoryWorkspace.vue";
import EnterpriseHistoryWorkspace from "./EnterpriseHistoryWorkspace.vue";
import GovernanceHistoryWorkspace from "./GovernanceHistoryWorkspace.vue";
import OperationalHistoryWorkspace from "./OperationalHistoryWorkspace.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RegistryCadHistoryWorkspace from "./RegistryCadHistoryWorkspace.vue";
import RecordHeader from "./RecordHeader.vue";

type HistoryDomain = {
  slug: string;
  title: string;
  description: string;
  stage: string;
  permission: string;
};

const props = withDefaults(defineProps<{
  path: string;
  currentAccount?: LocalAccount | null;
  masterDataOptions?: MasterDataOptions;
}>(), { masterDataOptions: emptyMasterDataOptions });
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();
const drawerDomain = ref<HistoryDomain | null>(null);

const domains: HistoryDomain[] = [
  { slug: "molds", title: "Molds & revisions", description: "Projects, products, molds, revisions and governed relationships.", stage: "H3", permission: "registry:read" },
  { slug: "cad-artifacts", title: "CAD artifacts", description: "Artifact versions, geometry, previews, features, jobs and lineage.", stage: "H3", permission: "registry:read" },
  { slug: "trials", title: "Trial & process", description: "Runs, parameters, defects, actions and append-only corrections.", stage: "H2", permission: "engineering-data:read" },
  { slug: "cae", title: "CAE / Moldflow", description: "Studies, runs, solver settings, metrics, quality and comparisons.", stage: "H2", permission: "engineering-data:read" },
  { slug: "hmi", title: "HMI extractions", description: "Images, extracted fields, human decisions and versioned exports.", stage: "H2", permission: "engineering-data:read" },
  { slug: "knowledge", title: "Knowledge documents", description: "Document versions, chunks, authority, citations and ingestion jobs.", stage: "H5", permission: "public-demo:read" },
  { slug: "rules", title: "Mold rules", description: "Profiles, rule versions, workflow decisions and version differences.", stage: "H5", permission: "public-demo:read" },
  { slug: "analysis-results", title: "Analysis results", description: "Similarity, reviews, searches and comparisons with immutable inputs.", stage: "H6", permission: "public-demo:read" },
  { slug: "jobs", title: "Jobs & queue", description: "Processing attempts, event timelines, failures, retry and cancel controls.", stage: "H6", permission: "public-demo:read" },
  { slug: "audit-lineage", title: "Audit & lineage", description: "Actor decisions, changes, source evidence and derived relationships.", stage: "H6", permission: "public-demo:read" },
  { slug: "enterprise", title: "Enterprise controls", description: "Bulk import, retention, legal hold, DLP, SIEM and connector isolation.", stage: "H7", permission: "enterprise:read" },
];

const currentSlug = computed(() => {
  const pathname = new URL(props.path, window.location.origin).pathname;
  const segments = pathname.replace(/^\/+|\/+$/g, "").split("/");
  return segments[0] === "data" && segments[1] ? segments[1] : "overview";
});
const currentDomain = computed(() => domains.find((domain) => domain.slug === currentSlug.value) || null);

function openDomain(domain: HistoryDomain): void {
  emit("navigate", `/data/${domain.slug}`);
}
</script>

<template>
  <section class="history-data-center">
    <nav class="history-domain-nav" :aria-label="t('Historical data domains')">
      <button type="button" :class="{ active: currentSlug === 'overview' }" @click="emit('navigate', '/data/overview')">{{ t("Overview") }}</button>
      <button v-for="domain in domains" :key="domain.slug" type="button" :class="{ active: currentSlug === domain.slug }" @click="openDomain(domain)">{{ t(domain.title) }}</button>
    </nav>

    <template v-if="currentSlug === 'overview'">
      <section class="history-overview-hero">
        <div>
          <p class="eyebrow">{{ t("Historical data center") }}</p>
          <h2>{{ t("Find complete engineering evidence") }}</h2>
          <p>{{ t("Browse complete records here while engineering workspaces remain focused on creating and analyzing data.") }}</p>
        </div>
        <div class="history-overview-stat"><strong>{{ domains.length }}</strong><span>{{ t("governed domains") }}</span></div>
      </section>

      <div class="history-domain-grid">
        <article v-for="domain in domains" :key="domain.slug">
          <div class="history-domain-card-heading"><span>{{ domain.stage }}</span><small>{{ domain.permission }}</small></div>
          <h3>{{ t(domain.title) }}</h3>
          <p>{{ t(domain.description) }}</p>
          <div class="history-domain-card-actions">
            <button type="button" @click="openDomain(domain)">{{ t("Open records") }}</button>
            <button type="button" class="text-button" @click="drawerDomain = domain">{{ t("Quick details") }}</button>
          </div>
        </article>
      </div>
    </template>

    <EngineeringHistoryWorkspace
      v-else-if="currentSlug === 'trials' || currentSlug === 'cae' || currentSlug === 'hmi'"
      :domain="currentSlug"
      :path="path"
      :can-manage="currentAccount?.permissions.includes('engineering-data:manage') || false"
      @navigate="emit('navigate', $event)"
    />

    <RegistryCadHistoryWorkspace
      v-else-if="currentSlug === 'molds' || currentSlug === 'cad-artifacts'"
      :domain="currentSlug"
      :path="path"
      :can-manage="currentAccount?.permissions.includes('registry:manage') || false"
      :master-data-options="masterDataOptions"
      @navigate="emit('navigate', $event)"
    />

    <GovernanceHistoryWorkspace
      v-else-if="currentSlug === 'rules' || currentSlug === 'knowledge'"
      :domain="currentSlug"
      :path="path"
      :current-account="currentAccount"
      @navigate="emit('navigate', $event)"
    />

    <OperationalHistoryWorkspace
      v-else-if="currentSlug === 'analysis-results' || currentSlug === 'jobs' || currentSlug === 'audit-lineage'"
      :domain="currentSlug"
      :path="path"
      :current-account="currentAccount"
      @navigate="emit('navigate', $event)"
    />

    <EnterpriseHistoryWorkspace
      v-else-if="currentSlug === 'enterprise'"
      :path="path"
      :current-account="currentAccount"
      @navigate="emit('navigate', $event)"
    />

    <template v-else-if="currentDomain">
      <RecordHeader :title="t(currentDomain.title)" :identifier="`/data/${currentDomain.slug}`" status="Foundation ready" :version="currentDomain.stage">
        <template #actions><button type="button" @click="drawerDomain = currentDomain">{{ t("About this domain") }}</button></template>
      </RecordHeader>
      <section class="history-placeholder">
        <div class="history-toolbar">
          <label><span>{{ t("Search") }}</span><input type="search" :placeholder="t('Search historical records')" disabled /></label>
          <label><span>{{ t("Status") }}</span><select disabled><option>{{ t("All statuses") }}</option></select></label>
        </div>
        <DataTable :columns="[{ key: 'record', label: t('Record') }, { key: 'status', label: t('Status') }, { key: 'updated', label: t('Updated') }]" :items="[]" :empty-text="t('Domain detail will be enabled in its planned phase.')" />
      </section>
    </template>

    <section v-else class="workspace-state error-state">
      <strong>{{ t("Unsupported historical data page") }}</strong>
      <button type="button" @click="emit('navigate', '/data/overview')">{{ t("Return to historical data overview") }}</button>
    </section>

    <DetailDrawer :open="Boolean(drawerDomain)" :title="drawerDomain ? t(drawerDomain.title) : ''" :subtitle="drawerDomain ? t(drawerDomain.description) : ''" @close="drawerDomain = null">
      <PropertyGrid v-if="drawerDomain" :items="[
        { label: t('Planned phase'), value: drawerDomain.stage },
        { label: t('Route'), value: `/data/${drawerDomain.slug}`, copyable: true },
        { label: t('Minimum permission'), value: drawerDomain.permission },
        { label: t('History policy'), value: t('Version, correct or archive; do not overwrite evidence.') },
      ]" />
      <template #footer><button v-if="drawerDomain" type="button" @click="openDomain(drawerDomain); drawerDomain = null">{{ t("Open records") }}</button></template>
    </DetailDrawer>
  </section>
</template>
