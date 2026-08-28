<script setup lang="ts">
import { useI18n } from "../i18n";
import { dismissToast, toasts } from "../toast";

const { t } = useI18n();
</script>

<template>
  <div class="toast-region" :aria-label="t('Notifications')">
    <TransitionGroup name="toast-list">
      <article
        v-for="toast in toasts"
        :key="toast.id"
        class="toast-message"
        :class="toast.tone"
        :role="toast.tone === 'error' ? 'alert' : 'status'"
      >
        <span class="toast-symbol" aria-hidden="true">
          {{ toast.tone === "success" ? "✓" : toast.tone === "error" ? "!" : "i" }}
        </span>
        <p>{{ toast.message }}</p>
        <button type="button" :aria-label="t('Dismiss notification')" @click="dismissToast(toast.id)">×</button>
      </article>
    </TransitionGroup>
  </div>
</template>
