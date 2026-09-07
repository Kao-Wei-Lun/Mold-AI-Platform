<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type { KnowledgeCitation } from "../api/knowledge";
import { getDemoAccessToken } from "../api/client";
import { useI18n } from "../i18n";
import { citationOverlayStyle } from "../pdfCitation";

const props = defineProps<{ open: boolean; citation: KnowledgeCitation | null }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();

const canvas = ref<HTMLCanvasElement | null>(null);
const loading = ref(false);
const error = ref("");
const pageNumber = ref(1);
const pageCount = ref(0);
let pdfDocument: { numPages: number; getPage: (page: number) => Promise<any> } | null = null;
let loadingTask: { destroy: () => Promise<void> } | null = null;
let loadGeneration = 0;

const overlay = computed(() => citationOverlayStyle(props.citation?.citation_anchor));
const hasExactHighlight = computed(() => Boolean(overlay.value));

async function renderPage(): Promise<void> {
  if (!pdfDocument || !canvas.value) return;
  const page = await pdfDocument.getPage(pageNumber.value);
  const baseViewport = page.getViewport({ scale: 1 });
  const availableWidth = Math.min(window.innerWidth - 64, 980);
  const scale = Math.max(0.5, Math.min(2, availableWidth / baseViewport.width));
  const viewport = page.getViewport({ scale });
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const context = canvas.value.getContext("2d");
  if (!context) throw new Error("Canvas is unavailable.");
  canvas.value.width = Math.floor(viewport.width * ratio);
  canvas.value.height = Math.floor(viewport.height * ratio);
  canvas.value.style.width = `${viewport.width}px`;
  canvas.value.style.height = `${viewport.height}px`;
  await page.render({
    canvas: canvas.value,
    canvasContext: context,
    viewport,
    transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
  }).promise;
}

async function loadCitation(): Promise<void> {
  const citation = props.citation;
  const generation = ++loadGeneration;
  error.value = "";
  if (!props.open || !citation) return;
  if (citation.source_format !== "pdf") {
    error.value = t("PDF preview is available only for PDF sources.");
    return;
  }
  loading.value = true;
  try {
    if (loadingTask) await loadingTask.destroy();
    const pdfjs = await import("pdfjs-dist");
    pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
    const token = getDemoAccessToken();
    const task = pdfjs.getDocument({
      url: citation.source_url,
      httpHeaders: token ? { Authorization: `Bearer ${token}` } : undefined,
      withCredentials: true,
      disableRange: false,
      rangeChunkSize: 64 * 1024,
    });
    loadingTask = task;
    const loaded = await task.promise;
    if (generation !== loadGeneration) {
      await task.destroy();
      return;
    }
    pdfDocument = loaded;
    pageCount.value = loaded.numPages;
    const requestedPage = citation.citation_anchor?.page_no || 1;
    pageNumber.value = Math.min(Math.max(requestedPage, 1), loaded.numPages);
    await nextTick();
    await renderPage();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("PDF preview could not be loaded.");
  } finally {
    if (generation === loadGeneration) loading.value = false;
  }
}

async function changePage(delta: number): Promise<void> {
  const next = Math.min(Math.max(pageNumber.value + delta, 1), pageCount.value);
  if (next === pageNumber.value) return;
  pageNumber.value = next;
  loading.value = true;
  try {
    await renderPage();
  } finally {
    loading.value = false;
  }
}

watch(() => [props.open, props.citation?.citation_id], loadCitation, { immediate: true });
onBeforeUnmount(async () => {
  loadGeneration += 1;
  if (loadingTask) await loadingTask.destroy();
});
</script>

<template>
  <div v-if="open" class="pdf-citation-backdrop" role="presentation" @click.self="emit('close')">
    <section class="pdf-citation-viewer" role="dialog" aria-modal="true" :aria-label="t('Cited PDF source')">
      <header>
        <div>
          <p>{{ t("Governed source evidence") }}</p>
          <h3>{{ citation?.title }}</h3>
        </div>
        <button type="button" class="secondary-button" @click="emit('close')">{{ t("Close preview") }}</button>
      </header>
      <div class="pdf-citation-toolbar">
        <button type="button" :disabled="loading || pageNumber <= 1" @click="changePage(-1)">{{ t("Previous page") }}</button>
        <strong>{{ t("Page {page} of {pages}", { page: pageNumber, pages: pageCount || "—" }) }}</strong>
        <button type="button" :disabled="loading || pageNumber >= pageCount" @click="changePage(1)">{{ t("Next page") }}</button>
        <span :class="hasExactHighlight ? 'exact' : 'page-only'">
          {{ hasExactHighlight ? t("Exact passage highlight") : t("Page-level citation") }}
        </span>
      </div>
      <p v-if="!hasExactHighlight && !error" class="pdf-citation-notice">
        {{ t("This source has no reliable bounding box, so only the cited page is shown.") }}
      </p>
      <div class="pdf-page-scroll">
        <div class="pdf-page-stage">
          <canvas ref="canvas"></canvas>
          <span v-if="overlay" class="pdf-citation-highlight" :style="overlay" aria-hidden="true"></span>
          <span v-if="loading" class="pdf-citation-loading">{{ t("Loading cited page...") }}</span>
        </div>
      </div>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    </section>
  </div>
</template>
