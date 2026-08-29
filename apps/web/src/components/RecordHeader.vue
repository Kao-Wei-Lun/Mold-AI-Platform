<script setup lang="ts">
withDefaults(defineProps<{ title: string; identifier?: string; status?: string; version?: string }>(), {
  identifier: "",
  status: "",
  version: "",
});
</script>

<template>
  <header class="record-header">
    <div>
      <p v-if="identifier" class="record-identifier">{{ identifier }}</p>
      <h2>{{ title }}</h2>
      <div class="record-badges">
        <span v-if="status" class="status-chip">{{ status }}</span>
        <span v-if="version" class="version-chip">{{ version }}</span>
      </div>
    </div>
    <div v-if="$slots.actions" class="record-actions"><slot name="actions" /></div>
  </header>
</template>
