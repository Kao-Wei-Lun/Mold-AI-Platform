<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = withDefaults(defineProps<{ open: boolean; title: string; subtitle?: string }>(), {
  subtitle: "",
});
const emit = defineEmits<{ close: [] }>();
const panel = ref<HTMLElement | null>(null);
let previousFocus: HTMLElement | null = null;

function close(): void {
  emit("close");
}

function onKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === "Escape") close();
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      previousFocus = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", onKeydown);
      await nextTick();
      panel.value?.focus();
    } else {
      document.removeEventListener("keydown", onKeydown);
      previousFocus?.focus?.();
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="detail-drawer-backdrop" @click.self="close">
      <aside ref="panel" class="detail-drawer" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
        <header>
          <div><h2>{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div>
          <button type="button" class="icon-button" aria-label="Close details" @click="close">×</button>
        </header>
        <div class="detail-drawer-body"><slot /></div>
        <footer v-if="$slots.footer"><slot name="footer" /></footer>
      </aside>
    </div>
  </Teleport>
</template>
