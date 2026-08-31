<script setup lang="ts">
import { useI18n } from "../i18n";

const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();

const steps = [
  { number: "1", title: "Planning target", detail: "Choose the mold and revision that this plan governs." },
  { number: "2", title: "Engineering context", detail: "Confirm product, material, mold and process conditions." },
  { number: "3", title: "Recommended standard", detail: "Let the governed resolver explain the selected review rule set." },
  { number: "4", title: "Planning requirements", detail: "Review required evidence, risks and missing information." },
  { number: "5", title: "Save and hand off", detail: "Preserve the decision before starting downstream engineering work." },
];
</script>

<template>
  <section class="mold-planning-workspace" aria-labelledby="mold-planning-title">
    <header class="planning-intro">
      <div>
        <p class="eyebrow">{{ t("Context-driven planning") }}</p>
        <h2 id="mold-planning-title">{{ t("Plan the mold before selecting a review rule set") }}</h2>
        <p>{{ t("Describe the engineering context first. The platform will resolve the applicable governed standard and preserve the reason for later review.") }}</p>
      </div>
      <button type="button" class="secondary-button" @click="emit('navigate', '/governance/rules')">
        {{ t("Browse review rule sets") }}
      </button>
    </header>

    <ol class="planning-step-list" :aria-label="t('Mold planning steps')">
      <li v-for="step in steps" :key="step.number">
        <span>{{ step.number }}</span>
        <div><strong>{{ t(step.title) }}</strong><p>{{ t(step.detail) }}</p></div>
      </li>
    </ol>

    <section class="planning-empty-state">
      <span aria-hidden="true">◎</span>
      <div>
        <h3>{{ t("No mold plans yet") }}</h3>
        <p>{{ t("The first implementation phase establishes this dedicated engineering workspace. Planning records and automatic standard resolution are added in the following phases.") }}</p>
      </div>
      <button type="button" disabled>{{ t("Create mold plan") }}</button>
    </section>
  </section>
</template>
