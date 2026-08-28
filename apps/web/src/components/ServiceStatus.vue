<script setup lang="ts">
import type { ServiceState } from "../api/system";
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps<{
  service: ServiceState;
}>();
</script>

<template>
  <li class="service-status">
    <span class="service-name">{{ service.name }}</span>
    <span class="status-pill" :class="service.status">
      {{ service.status === "ok" ? t("Ready") : t("Unavailable") }}
    </span>
  </li>
</template>
