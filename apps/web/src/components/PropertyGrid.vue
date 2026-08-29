<script setup lang="ts">
export type PropertyItem = {
  label: string;
  value: string | number | null | undefined;
  copyable?: boolean;
};

defineProps<{ items: PropertyItem[] }>();

async function copy(value: PropertyItem["value"]): Promise<void> {
  if (value === null || value === undefined) return;
  await navigator.clipboard?.writeText(String(value));
}
</script>

<template>
  <dl class="property-grid">
    <div v-for="item in items" :key="item.label">
      <dt>{{ item.label }}</dt>
      <dd>
        <span>{{ item.value === null || item.value === undefined || item.value === "" ? "—" : item.value }}</span>
        <button v-if="item.copyable && item.value" type="button" @click="copy(item.value)">Copy</button>
      </dd>
    </div>
  </dl>
</template>
