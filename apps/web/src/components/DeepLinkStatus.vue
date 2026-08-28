<script setup lang="ts">
import { ref, watch } from "vue";

import { fetchCADJob, type CADJob } from "../api/cad";
import {
  reportDeepLinkEvent,
  type DeepLinkContext,
  type DeepLinkError,
} from "../deepLinks";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps<{
  context: DeepLinkContext | null;
  error: DeepLinkError | null;
  accessReady: boolean;
}>();

const job = ref<CADJob | null>(null);
const loadError = ref<string | null>(null);

watch(
  [() => props.context, () => props.accessReady],
  async ([context, accessReady]) => {
    job.value = null;
    loadError.value = null;
    if (!context) return;
    reportDeepLinkEvent("opened", context, { status: accessReady ? "authorized" : "waiting" });
    if (!accessReady || context.target !== "job") return;
    const started = performance.now();
    try {
      job.value = await fetchCADJob(context.refs.job_id);
      reportDeepLinkEvent("resolved", context, {
        status: job.value.state,
        latency_ms: Math.round(performance.now() - started),
      });
    } catch (caught) {
      loadError.value = caught instanceof Error ? caught.message : t("Unable to load linked job.");
      reportDeepLinkEvent("failed", context, {
        status: "not_found_or_forbidden",
        latency_ms: Math.round(performance.now() - started),
      });
    }
  },
  { immediate: true },
);
</script>

<template>
  <section v-if="error" class="deep-link-state deep-link-error" role="alert">
    <div><p class="eyebrow">{{ error.code }}</p><h2>{{ t("Unable to open this Mold AI context") }}</h2></div>
    <p>{{ error.message }}</p>
  </section>
  <section v-else-if="context" id="deep-link-status" class="deep-link-state" aria-live="polite">
    <div>
      <p class="eyebrow">{{ t("Deep link {version}", { version: context.deep_link_version }) }}</p>
      <h2>{{ t(context.target.replaceAll("_", " ")) }}</h2>
    </div>
    <p v-if="!accessReady">{{ t("Waiting for Demo access before loading the referenced record.") }}</p>
    <p v-else-if="loadError" class="error-message">{{ t("The linked record is unavailable or not authorized.") }}</p>
    <p v-else-if="job">
      {{ t("Job {id} is {state} at {progress}% ({stage}).", { id: job.job_id, state: t(job.state), progress: job.progress, stage: job.stage }) }}
    </p>
    <p v-else>{{ t("Validated identifiers will be reloaded from the API below; no new analysis is started.") }}</p>
  </section>
</template>
