<script setup lang="ts">
import { onMounted, ref } from "vue";

import { fetchReadiness, type ReadinessResponse } from "./api/system";
import type { CADModelResult } from "./api/cad";
import CadWorkspace from "./components/CadWorkspace.vue";
import DesignReviewWorkspace from "./components/DesignReviewWorkspace.vue";
import ServiceStatus from "./components/ServiceStatus.vue";
import SimilarityWorkspace from "./components/SimilarityWorkspace.vue";

const readiness = ref<ReadinessResponse | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const activeCAD = ref<CADModelResult | null>(null);

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

onMounted(refreshHealth);
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-mark">MA</div>
      <div>
        <strong>Mold AI</strong>
        <span>Platform</span>
      </div>
    </aside>

    <main class="workspace">
      <header class="hero">
        <p class="eyebrow">Engineering workspace</p>
        <h1>Explainable mold engineering workspace</h1>
        <p>
          Process versioned CAD, find comparable geometry, and evaluate deterministic design rules
          with traceable evidence and reviewer decisions.
        </p>
      </header>

      <section class="status-card" aria-labelledby="platform-status-title">
        <div class="card-heading">
          <div>
            <p class="eyebrow">Environment status</p>
            <h2 id="platform-status-title">Platform services</h2>
          </div>
          <button type="button" :disabled="loading" @click="refreshHealth">
            {{ loading ? "Checking..." : "Check again" }}
          </button>
        </div>

        <p v-if="error" class="error-message" role="alert">{{ error }}</p>
        <p v-else-if="loading" class="muted">Connecting to the platform API...</p>
        <ul v-else-if="readiness" class="service-list">
          <ServiceStatus
            v-for="service in readiness.services"
            :key="service.name"
            :service="service"
          />
        </ul>
      </section>

      <CadWorkspace @ready="activeCAD = $event" />
      <SimilarityWorkspace :query="activeCAD" />
      <DesignReviewWorkspace :query="activeCAD" />
    </main>
  </div>
</template>
