<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { consumeDemoAccessBootstrap, getDemoAccessToken } from "../api/client";
import {
  clearDemoAccessToken,
  connectDemoAccess,
  fetchSecurityPreflight,
  type SecurityPreflight,
} from "../api/security";

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false });
const emit = defineEmits<{ ready: [ready: boolean] }>();
const preflight = ref<SecurityPreflight | null>(null);
const token = ref("");
const connecting = ref(false);
const connected = ref(false);
const error = ref<string | null>(null);

const failedChecks = computed(() =>
  Object.entries(preflight.value?.checks || {})
    .filter(([, passed]) => !passed)
    .map(([name]) => name.replaceAll("_", " ")),
);

async function verifyStoredToken(): Promise<void> {
  const stored = getDemoAccessToken();
  if (!stored) return;
  try {
    await connectDemoAccess(stored);
    connected.value = true;
    emit("ready", true);
  } catch {
    connected.value = false;
    emit("ready", false);
  }
}

async function loadPreflight(): Promise<void> {
  error.value = null;
  try {
    preflight.value = await fetchSecurityPreflight();
    if (!preflight.value.auth.required) {
      connected.value = true;
      emit("ready", true);
    } else {
      await verifyStoredToken();
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Security preflight failed.";
    emit("ready", false);
  }
}

async function connect(): Promise<void> {
  if (!token.value.trim()) return;
  connecting.value = true;
  error.value = null;
  try {
    await connectDemoAccess(token.value);
    token.value = "";
    connected.value = true;
    emit("ready", true);
  } catch (caught) {
    connected.value = false;
    error.value = caught instanceof Error ? caught.message : "Demo access failed.";
    emit("ready", false);
  } finally {
    connecting.value = false;
  }
}

function disconnect(): void {
  clearDemoAccessToken();
  connected.value = false;
  emit("ready", !preflight.value?.auth.required);
}

function onUnauthorized(): void {
  clearDemoAccessToken();
  connected.value = false;
  error.value = "The Demo session expired or was rejected. Enter the access token again.";
  emit("ready", false);
}

onMounted(() => {
  consumeDemoAccessBootstrap();
  window.addEventListener("mold-ai:unauthorized", onUnauthorized);
  loadPreflight();
});
onBeforeUnmount(() => window.removeEventListener("mold-ai:unauthorized", onUnauthorized));
</script>

<template>
  <section class="access-panel" :class="{ 'access-panel-compact': compact && connected }" aria-labelledby="access-title">
    <div>
      <p v-if="!compact || !connected" class="eyebrow">Release security</p>
      <h2 id="access-title">{{ compact && connected ? "Private Demo connected" : "Demo access boundary" }}</h2>
      <p v-if="preflight">
        <span class="access-state" :class="connected ? 'connected' : 'locked'">
          {{ connected ? "Access ready" : "Access locked" }}
        </span>
        <span>
          {{ preflight.auth.required ? "Bearer token required" : "Local authentication disabled" }}
        </span>
      </p>
    </div>

    <form v-if="preflight?.auth.required && !connected" class="access-form" @submit.prevent="connect">
      <label>
        <span>Demo access token</span>
        <input v-model="token" type="password" autocomplete="current-password" required />
      </label>
      <button type="submit" :disabled="connecting || !token.trim()">
        {{ connecting ? "Verifying..." : "Unlock workspace" }}
      </button>
    </form>
    <button
      v-else-if="preflight?.auth.required && connected"
      type="button"
      class="secondary-button"
      @click="disconnect"
    >
      Clear Demo session
    </button>

    <details v-if="preflight && (!compact || !connected)" class="release-preflight">
      <summary>
        External release preflight:
        {{ preflight.production_ready ? "ready" : `${failedChecks.length} checks pending` }}
      </summary>
      <ul v-if="failedChecks.length">
        <li v-for="check in failedChecks" :key="check">{{ check }}</li>
      </ul>
      <p>
        MCP path: {{ preflight.mcp.secure_tunnel_configured ? "Secure MCP Tunnel" : "not configured" }}.
        OAuth implemented: {{ preflight.mcp.oauth_implemented ? "yes" : "no" }}.
      </p>
    </details>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
