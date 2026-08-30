<script setup lang="ts">
import { ref, watch } from "vue";

import { formatFileSize } from "../fileUpload";
import { useI18n } from "../i18n";

const props = withDefaults(defineProps<{
  id: string;
  accept: string;
  prompt: string;
  readyText?: string;
  selectedFile?: File | null;
  describedBy?: string;
  invalid?: boolean;
  disabled?: boolean;
}>(), {
  selectedFile: null,
  describedBy: undefined,
  invalid: false,
  disabled: false,
  readyText: "",
});

const emit = defineEmits<{ select: [file: File] }>();
const { t } = useI18n();
const input = ref<HTMLInputElement | null>(null);
const dragging = ref(false);

function choose(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file) emit("select", file);
}

function drop(event: DragEvent): void {
  dragging.value = false;
  if (props.disabled) return;
  const file = event.dataTransfer?.files?.[0];
  if (file) emit("select", file);
}

watch(
  () => props.selectedFile,
  (file) => {
    if (!file && input.value) input.value.value = "";
  },
);
</script>

<template>
  <div
    class="file-drop-zone"
    :class="{ dragging, selected: selectedFile, disabled, invalid }"
    @dragenter.prevent="dragging = true"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="drop"
  >
    <input
      :id="id"
      ref="input"
      class="file-drop-input"
      type="file"
      :accept="accept"
      :disabled="disabled"
      :required="!selectedFile"
      :aria-describedby="describedBy"
      :aria-invalid="invalid"
      @change="choose"
    />
    <div class="file-drop-copy" aria-hidden="true">
      <span class="file-drop-icon">⇧</span>
      <span><strong>{{ dragging ? t("Release to select this file") : prompt }}</strong><small>{{ t("Drag and drop or choose a file") }}</small></span>
    </div>
    <div v-if="selectedFile" class="selected-file-summary" aria-live="polite">
      <strong>{{ selectedFile.name }}</strong>
      <span>{{ formatFileSize(selectedFile.size) }} · {{ readyText || t("Ready to upload") }}</span>
    </div>
  </div>
</template>
