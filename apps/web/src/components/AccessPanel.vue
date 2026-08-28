<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { consumeDemoAccessBootstrap, getDemoAccessToken } from "../api/client";
import {
  clearDemoAccessToken,
  connectDemoAccess,
  fetchSecurityPreflight,
  type SecurityPreflight,
} from "../api/security";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";

const { t } = useI18n();

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
    error.value = caught instanceof Error ? caught.message : t("Security preflight failed.");
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
    error.value = caught instanceof Error ? caught.message : t("Demo access failed.");
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
  error.value = t("The Demo session expired or was rejected. Enter the access token again.");
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
      <p v-if="!compact || !connected" class="eyebrow">{{ t("Release security") }}</p>
      <h2 id="access-title">{{ compact && connected ? t("Private Demo connected") : t("Demo access boundary") }}</h2>
      <p v-if="preflight">
        <span class="access-state" :class="connected ? 'connected' : 'locked'">
          {{ connected ? t("Access ready") : t("Access locked") }}
        </span>
        <span>
          {{ preflight.auth.required ? t("Bearer token required") : t("Local authentication disabled") }}
        </span>
      </p>
    </div>

    <form v-if="preflight?.auth.required && !connected" class="access-form" @submit.prevent="connect">
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Demo access token')" required :helper="t('The token is kept only for this Demo session.')">
        <input :id="fieldId" v-model="token" type="password" autocomplete="current-password" required :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <button type="submit" :disabled="connecting || !token.trim()">
        {{ connecting ? t("Verifying...") : t("Unlock workspace") }}
      </button>
    </form>
    <button
      v-else-if="preflight?.auth.required && connected"
      type="button"
      class="secondary-button"
      @click="disconnect"
    >
      {{ t("Clear Demo session") }}
    </button>

    <details v-if="preflight && (!compact || !connected)" class="release-preflight">
      <summary>
        {{ t("External release preflight:") }}
        {{ preflight.production_ready ? t("ready") : t("{count} checks pending", { count: failedChecks.length }) }}
      </summary>
      <ul v-if="failedChecks.length">
        <li v-for="check in failedChecks" :key="check">{{ check }}</li>
      </ul>
      <p>
        {{ t("MCP path:") }} {{ preflight.mcp.secure_tunnel_configured ? t("Secure MCP Tunnel") : t("not configured") }}.
        {{ t("OAuth implemented:") }} {{ preflight.mcp.oauth_implemented ? t("yes") : t("no") }}.
      </p>
    </details>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
