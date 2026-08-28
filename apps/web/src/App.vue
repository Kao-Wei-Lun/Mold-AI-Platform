<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { AssistantContext, UIAction } from "./api/assistant";
import type { CADModelResult } from "./api/cad";
import { fetchReadiness, type ReadinessResponse } from "./api/system";
import AccessPanel from "./components/AccessPanel.vue";
import AssistantPanel from "./components/AssistantPanel.vue";
import CAEWorkspace from "./components/CAEWorkspace.vue";
import CadWorkspace from "./components/CadWorkspace.vue";
import DeepLinkStatus from "./components/DeepLinkStatus.vue";
import DesignReviewWorkspace from "./components/DesignReviewWorkspace.vue";
import HMIWorkspace from "./components/HMIWorkspace.vue";
import KnowledgeWorkspace from "./components/KnowledgeWorkspace.vue";
import ProcessTrialWorkspace from "./components/ProcessTrialWorkspace.vue";
import RuleManagementWorkspace from "./components/RuleManagementWorkspace.vue";
import ServiceStatus from "./components/ServiceStatus.vue";
import SimilarityWorkspace from "./components/SimilarityWorkspace.vue";
import { parseDeepLink } from "./deepLinks";
import {
  resolveWorkspaceRoute,
  routeForDeepLink,
  workspaceRoutes,
  type WorkspaceRoute,
  type WorkspaceRouteId,
} from "./routing";

const readiness = ref<ReadinessResponse | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const activeCAD = ref<CADModelResult | null>(null);
const pendingUIAction = ref<UIAction | null>(null);
const accessReady = ref(false);
const assistantOpen = ref(true);
const navigationOpen = ref(false);
const deepLinkState = parseDeepLink(window.location.search);
const deepLinkVisible = ref(Boolean(deepLinkState.context || deepLinkState.error));
const initialRoute = deepLinkState.context
  ? routeForDeepLink(deepLinkState.context.target)
  : resolveWorkspaceRoute(window.location.pathname);
const currentRoute = ref<WorkspaceRoute>(initialRoute);
const assistantContext = ref<AssistantContext>({
  context_version: "1.0",
  page: "engineering_workspace",
  ui_locale: "zh-TW",
});

const navigationGroups = computed(() =>
  ["Overview", "Engineering", "Governance"].map((group) => ({
    group,
    routes: workspaceRoutes.filter((route) => route.group === group),
  })),
);
const activeDeepLink = computed(() => {
  if (!deepLinkVisible.value || !deepLinkState.context) return null;
  return routeForDeepLink(deepLinkState.context.target).id === currentRoute.value.id
    ? deepLinkState.context
    : null;
});
const selectedCadLabel = computed(() =>
  activeCAD.value ? activeCAD.value.artifact_version_id.slice(0, 8) : "No CAD selected",
);

const guidedSteps: Array<{ number: string; route: WorkspaceRouteId; title: string; detail: string }> = [
  { number: "01", route: "cad", title: "Prepare CAD", detail: "Select a curated model or process STEP/STL." },
  { number: "02", route: "similarity", title: "Find precedents", detail: "Rank comparable molds and inspect score lanes." },
  { number: "03", route: "design_review", title: "Review design", detail: "Run approved deterministic engineering rules." },
  { number: "04", route: "process_trial", title: "Compare trials", detail: "Review historical evidence and controlled candidates." },
  { number: "05", route: "cae", title: "Compare CAE", detail: "Confirm compatibility before reading metric deltas." },
  { number: "06", route: "hmi", title: "Review HMI", detail: "Confirm extracted fields before Excel export." },
  { number: "07", route: "knowledge", title: "Verify knowledge", detail: "Ground conclusions in authorized citations." },
];

function routeById(routeId: WorkspaceRouteId): WorkspaceRoute {
  return workspaceRoutes.find((route) => route.id === routeId) || workspaceRoutes[0];
}

function navigate(routeId: WorkspaceRouteId): void {
  const route = routeById(routeId);
  if (currentRoute.value.id !== route.id || window.location.search) {
    window.history.pushState(null, "", route.path);
    currentRoute.value = route;
  }
  deepLinkVisible.value = false;
  navigationOpen.value = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function onPopState(): void {
  currentRoute.value = resolveWorkspaceRoute(window.location.pathname);
  deepLinkVisible.value = Boolean(window.location.search);
}

function executeUIAction(action: UIAction): void {
  pendingUIAction.value = action;
}

async function refreshHealth(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    readiness.value = await fetchReadiness();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Unable to reach platform API";
    readiness.value = null;
  } finally {
    loading.value = false;
  }
}

watch(
  () => currentRoute.value.id,
  () => {
    document.title = `${currentRoute.value.label} · Mold AI Platform`;
    assistantContext.value = {
      context_version: "1.0",
      page: "engineering_workspace",
      ui_locale: "zh-TW",
    };
  },
  { immediate: true },
);

onMounted(() => {
  if (deepLinkState.context && window.location.pathname !== initialRoute.path) {
    window.history.replaceState(
      null,
      "",
      `${initialRoute.path}${window.location.search}${window.location.hash}`,
    );
  }
  window.addEventListener("popstate", onPopState);
  refreshHealth();
});
onBeforeUnmount(() => window.removeEventListener("popstate", onPopState));
</script>

<template>
  <div class="app-shell" :class="{ 'assistant-collapsed': !assistantOpen }">
    <aside class="sidebar" :class="{ 'navigation-open': navigationOpen }">
      <div class="sidebar-brand">
        <span class="brand-mark">MA</span>
        <span><strong>Mold AI</strong><small>Engineering Platform</small></span>
      </div>

      <nav id="primary-navigation" aria-label="Primary navigation">
        <div v-for="group in navigationGroups" :key="group.group" class="navigation-group">
          <p>{{ group.group }}</p>
          <a
            v-for="route in group.routes"
            :key="route.id"
            :href="route.path"
            :class="{ active: currentRoute.id === route.id }"
            :aria-current="currentRoute.id === route.id ? 'page' : undefined"
            @click.prevent="navigate(route.id)"
          >
            <span class="navigation-marker">{{ route.label.slice(0, 2).toUpperCase() }}</span>
            <span>{{ route.label }}</span>
          </a>
        </div>
      </nav>

      <div class="sidebar-foot">
        <span class="demo-scope-dot"></span>
        <span><strong>Public synthetic Demo</strong><small>No company data</small></span>
      </div>
    </aside>

    <div class="main-column">
      <header class="top-context-bar">
        <button
          type="button"
          class="mobile-nav-button"
          aria-controls="primary-navigation"
          :aria-expanded="navigationOpen"
          @click="navigationOpen = !navigationOpen"
        >
          Menu
        </button>
        <div class="breadcrumb" aria-label="Current location">
          <span>Mold AI</span><b>/</b><strong>{{ currentRoute.group }}</strong><b>/</b><span>{{ currentRoute.label }}</span>
        </div>
        <div class="top-context-actions">
          <span class="context-chip" :title="activeCAD?.artifact_version_id || ''">{{ selectedCadLabel }}</span>
          <span class="environment-chip">Demo</span>
          <button type="button" class="assistant-toggle" @click="assistantOpen = !assistantOpen">
            {{ assistantOpen ? "Hide assistant" : "Open assistant" }}
          </button>
        </div>
      </header>

      <main class="workspace">
        <header class="page-header">
          <div>
            <p class="eyebrow">{{ currentRoute.eyebrow }}</p>
            <h1>{{ currentRoute.title }}</h1>
            <p>{{ currentRoute.description }}</p>
          </div>
          <span v-if="activeDeepLink" class="opened-from-mcp">Opened from ChatGPT MCP</span>
        </header>

        <AccessPanel :compact="true" @ready="accessReady = $event" />
        <DeepLinkStatus
          :context="activeDeepLink"
          :error="deepLinkVisible ? deepLinkState.error : null"
          :access-ready="accessReady"
        />

        <template v-if="currentRoute.id === 'home'">
          <section class="home-overview" aria-labelledby="guided-demo-title">
            <div class="home-intro-card">
              <p class="eyebrow">Recommended path</p>
              <h2 id="guided-demo-title">Complete the seven-step guided Demo</h2>
              <p>Each step opens a focused workspace. Your selected CAD context remains available while navigating.</p>
              <button type="button" @click="navigate('cad')">Start with CAD & artifacts</button>
            </div>
            <div class="home-status-card">
              <span>Core services</span>
              <strong v-if="loading">Checking…</strong>
              <strong v-else-if="readiness" :class="readiness.status">{{ readiness.status }}</strong>
              <strong v-else class="error">Unavailable</strong>
              <small>Database · Redis · Qdrant</small>
              <button type="button" class="text-button" :disabled="loading" @click="refreshHealth">Refresh status</button>
            </div>
          </section>
          <section class="guided-grid" aria-label="Guided Demo steps">
            <article v-for="step in guidedSteps" :key="step.route">
              <span>{{ step.number }}</span>
              <div><h3>{{ step.title }}</h3><p>{{ step.detail }}</p></div>
              <button type="button" :aria-label="`Open ${step.title}`" @click="navigate(step.route)">Open →</button>
            </article>
          </section>
          <section class="governance-callout">
            <div><p class="eyebrow">New governance workspace</p><h2>Review mold rules before running design review</h2></div>
            <p>See profile ownership, approval, versions, thresholds and references in the system—not only in fixture files.</p>
            <button type="button" @click="navigate('rules')">Open mold rules</button>
          </section>
        </template>

        <section v-else-if="currentRoute.id === 'status'" class="status-card" aria-labelledby="platform-status-title">
          <div class="card-heading">
            <div><p class="eyebrow">Environment status</p><h2 id="platform-status-title">Platform services</h2></div>
            <button type="button" :disabled="loading" @click="refreshHealth">{{ loading ? "Checking…" : "Check again" }}</button>
          </div>
          <p v-if="error" class="error-message" role="alert">{{ error }}</p>
          <p v-else-if="loading" class="muted">Connecting to the platform API…</p>
          <ul v-else-if="readiness" class="service-list">
            <ServiceStatus v-for="service in readiness.services" :key="service.name" :service="service" />
          </ul>
        </section>

        <CadWorkspace v-else-if="currentRoute.id === 'cad' && accessReady" @ready="activeCAD = $event" />
        <SimilarityWorkspace
          v-else-if="currentRoute.id === 'similarity' && accessReady"
          :query="activeCAD"
          :ui-action="pendingUIAction"
          :deep-link="activeDeepLink"
          @context-change="assistantContext = $event"
        />
        <DesignReviewWorkspace
          v-else-if="currentRoute.id === 'design_review' && accessReady"
          :query="activeCAD"
          :deep-link="activeDeepLink"
          @context-change="assistantContext = $event"
        />
        <KnowledgeWorkspace
          v-else-if="currentRoute.id === 'knowledge' && accessReady"
          :deep-link="activeDeepLink"
          @context-change="assistantContext = $event"
        />
        <ProcessTrialWorkspace
          v-else-if="currentRoute.id === 'process_trial' && accessReady"
          :deep-link="activeDeepLink"
          @context-change="assistantContext = $event"
        />
        <CAEWorkspace v-else-if="currentRoute.id === 'cae' && accessReady" @context-change="assistantContext = $event" />
        <HMIWorkspace v-else-if="currentRoute.id === 'hmi' && accessReady" />
        <RuleManagementWorkspace v-else-if="currentRoute.id === 'rules' && accessReady" />
        <section v-else-if="currentRoute.id === 'not_found'" class="workspace-state error-state">
          <strong>Unsupported page</strong><span>The URL does not map to a Mold AI workspace.</span>
          <button type="button" @click="navigate('home')">Return to Demo guide</button>
        </section>
        <section v-else-if="!accessReady" class="workspace-state">
          Unlock the private Demo above to load this engineering workspace.
        </section>
      </main>
    </div>

    <AssistantPanel v-if="accessReady && assistantOpen" :context="assistantContext" @execute-action="executeUIAction" />
  </div>
</template>
