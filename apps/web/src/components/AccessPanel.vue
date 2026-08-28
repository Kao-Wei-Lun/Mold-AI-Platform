<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { consumeDemoAccessBootstrap, getDemoAccessToken } from "../api/client";
import {
  clearDemoAccessToken,
  connectDemoAccess,
  fetchSecurityPreflight,
  type SecurityPreflight,
} from "../api/security";
import {
  fetchCurrentAccount,
  loginLocalAccount,
  logoutLocalAccount,
  refreshCsrfToken,
  type LocalAccount,
} from "../api/identity";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";

const { t } = useI18n();

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false });
const emit = defineEmits<{ ready: [ready: boolean] }>();
const preflight = ref<SecurityPreflight | null>(null);
const token = ref("");
const username = ref("");
const password = ref("");
const account = ref<LocalAccount | null>(null);
const connecting = ref(false);
const connected = ref(false);
const error = ref<string | null>(null);

const failedChecks = computed(() =>
  Object.entries(preflight.value?.checks || {})
    .filter(([, passed]) => !passed)
    .map(([name]) => name.replaceAll("_", " ")),
);
const roleSummary = computed(() =>
  (account.value?.roles || []).map((role) => role.replaceAll("_", " ")).join(" · "),
);
const accessDescription = computed(() => {
  if (preflight.value?.auth.mode === "local") {
    return account.value ? t("Individual account session") : t("Individual account required");
  }
  return preflight.value?.auth.required ? t("Bearer token required") : t("Local authentication disabled");
});

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
    if (preflight.value.auth.mode === "local") {
      clearDemoAccessToken();
      const current = await fetchCurrentAccount();
      account.value = current.authenticated ? current.account : null;
      connected.value = Boolean(account.value);
      if (connected.value) await refreshCsrfToken();
      emit("ready", connected.value);
    } else if (!preflight.value.auth.required) {
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

async function connectBearer(): Promise<void> {
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

async function signIn(): Promise<void> {
  if (!username.value.trim() || !password.value) return;
  connecting.value = true;
  error.value = null;
  try {
    account.value = await loginLocalAccount(username.value, password.value);
    password.value = "";
    connected.value = true;
    emit("ready", true);
  } catch (caught) {
    account.value = null;
    connected.value = false;
    error.value = caught instanceof Error ? caught.message : t("Local account sign-in failed.");
    emit("ready", false);
  } finally {
    connecting.value = false;
  }
}

async function disconnect(): Promise<void> {
  error.value = null;
  if (preflight.value?.auth.mode === "local") {
    connecting.value = true;
    try {
      await logoutLocalAccount();
      account.value = null;
      connected.value = false;
      emit("ready", false);
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : t("Sign out failed.");
    } finally {
      connecting.value = false;
    }
    return;
  }
  clearDemoAccessToken();
  connected.value = false;
  emit("ready", !preflight.value?.auth.required);
}

function onUnauthorized(): void {
  clearDemoAccessToken();
  account.value = null;
  connected.value = false;
  error.value =
    preflight.value?.auth.mode === "local"
      ? t("Your account session expired or was revoked. Sign in again.")
      : t("The Demo session expired or was rejected. Enter the access token again.");
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
      <h2 id="access-title">
        {{ compact && account ? account.display_name : compact && connected ? t("Private Demo connected") : t("Demo access boundary") }}
      </h2>
      <p v-if="preflight">
        <span class="access-state" :class="connected ? 'connected' : 'locked'">
          {{ connected ? t("Access ready") : t("Access locked") }}
        </span>
        <span>{{ account ? roleSummary : accessDescription }}</span>
      </p>
    </div>

    <form
      v-if="preflight?.auth.mode === 'local' && !connected"
      class="access-form local-account-form"
      @submit.prevent="signIn"
    >
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Username')" required>
        <input
          :id="fieldId"
          v-model="username"
          type="text"
          autocomplete="username"
          required
          maxlength="150"
          :aria-describedby="describedBy"
          :aria-invalid="invalid"
        />
      </FormField>
      <FormField
        v-slot="{ fieldId, describedBy, invalid }"
        :label="t('Password')"
        required
        :helper="t('Use your individual Demo account. Credentials are not stored in the browser.')"
      >
        <input
          :id="fieldId"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :aria-describedby="describedBy"
          :aria-invalid="invalid"
        />
      </FormField>
      <button type="submit" :disabled="connecting || !username.trim() || !password" :aria-busy="connecting">
        {{ connecting ? t("Signing in…") : t("Sign in") }}
      </button>
    </form>

    <form
      v-else-if="preflight?.auth.mode === 'required' && !connected"
      class="access-form"
      @submit.prevent="connectBearer"
    >
      <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Demo access token')" required :helper="t('The token is kept only for this Demo session.')">
        <input :id="fieldId" v-model="token" type="password" autocomplete="current-password" required :aria-describedby="describedBy" :aria-invalid="invalid" />
      </FormField>
      <button type="submit" :disabled="connecting || !token.trim()" :aria-busy="connecting">
        {{ connecting ? t("Verifying...") : t("Unlock workspace") }}
      </button>
    </form>
    <button
      v-else-if="preflight?.auth.required && connected"
      type="button"
      class="secondary-button"
      :disabled="connecting"
      @click="disconnect"
    >
      {{ preflight.auth.mode === "local" ? t("Sign out") : t("Clear Demo session") }}
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
