<script setup lang="ts">
import type { ServiceState } from "../api/system";

defineProps<{
  service: ServiceState;
}>();
</script>

<template>
  <li class="service-status">
    <span class="service-name">{{ service.name }}</span>
    <span class="status-pill" :class="service.status">
      {{ service.status === "ok" ? "Ready" : "Unavailable" }}
    </span>
  </li>
</template>
