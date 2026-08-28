<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  message: string;
  actionLabel: string;
}>();

const emit = defineEmits<{ action: [] }>();
</script>

<template>
  <section class="workspace-empty-state" role="status">
    <div>
      <p class="eyebrow">{{ eyebrow }}</p>
      <h3>{{ title }}</h3>
      <p>{{ message }}</p>
    </div>
    <button type="button" @click="emit('action')">{{ actionLabel }}</button>
  </section>
</template>
