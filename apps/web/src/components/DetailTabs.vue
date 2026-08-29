<script setup lang="ts">
export type DetailTab = { id: string; label: string; count?: number };

defineProps<{ tabs: DetailTab[]; active: string }>();
defineEmits<{ "update:active": [value: string] }>();
</script>

<template>
  <div class="detail-tabs" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      role="tab"
      :aria-selected="active === tab.id"
      :class="{ active: active === tab.id }"
      @click="$emit('update:active', tab.id)"
    >
      {{ tab.label }}<span v-if="tab.count !== undefined">{{ tab.count }}</span>
    </button>
  </div>
</template>
