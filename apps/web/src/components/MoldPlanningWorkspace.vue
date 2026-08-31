<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import { fetchRecentCAD, type CADArtifactSummary, type CADModelResult } from "../api/cad";
import type { MasterDataOptions } from "../api/masterData";
import { MoldPlanningError, previewMoldPlanningResolution, type MoldPlanningResolutionPreview } from "../api/moldPlanning";
import { fetchRegistry, type RegistryMold, type RegistryPart, type RegistryProject, type RegistryRevision } from "../api/registry";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";

const props = defineProps<{
  activeCad?: CADModelResult | null;
  masterDataOptions: MasterDataOptions;
  masterDataLoading?: boolean;
  masterDataError?: string | null;
}>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { locale, t } = useI18n();

const loading = ref(true);
const resolving = ref(false);
const error = ref<string | null>(null);
const errorCode = ref("");
const projects = ref<RegistryProject[]>([]);
const parts = ref<RegistryPart[]>([]);
const molds = ref<RegistryMold[]>([]);
const revisions = ref<RegistryRevision[]>([]);
const artifacts = ref<CADArtifactSummary[]>([]);
const selectedMoldId = ref("");
const selectedRevisionId = ref("");
const selectedCadVersionId = ref("");
const purpose = ref("new_mold");
const productType = ref("");
const material = ref("");
const moldingProcess = ref("");
const location = ref("");
const preview = ref<MoldPlanningResolutionPreview | null>(null);

const selectedMold = computed(() => molds.value.find((item) => item.id === selectedMoldId.value) || null);
const selectedRevision = computed(() => revisions.value.find((item) => item.id === selectedRevisionId.value) || null);
const selectedPart = computed(() => parts.value.find((item) => item.id === selectedMold.value?.product_part_id) || null);
const selectedProject = computed(() => projects.value.find((item) => item.id === selectedMold.value?.project_id) || null);
const availableRevisions = computed(() => revisions.value.filter((item) => item.mold_id === selectedMoldId.value));
const availableArtifacts = computed(() => artifacts.value.filter((item) => item.mold_revision_id === selectedRevisionId.value));
const selectedArtifact = computed(() => availableArtifacts.value.find((item) => item.versions?.some((version) => version.artifact_version_id === selectedCadVersionId.value)) || null);
const canResolve = computed(() => Boolean(selectedRevisionId.value && productType.value && material.value && moldingProcess.value));

function sourceFor(dimension: string): string {
  if (preview.value?.sources[dimension]) return preview.value.sources[dimension].source_type;
  if (["mold_type", "project"].includes(dimension)) return "registry";
  if (["product_type", "material"].includes(dimension) && selectedArtifact.value) return "cad";
  if (["product_type", "material"].includes(dimension) && selectedPart.value) return "registry";
  if (["molding_process", "location"].includes(dimension)) return "reference_data";
  return "missing";
}

function optionLabel(item: { name_en: string; name_zh_tw: string; code: string }): string {
  return `${locale.value === "zh-TW" ? item.name_zh_tw || item.name_en : item.name_en} · ${item.code}`;
}

function applySelectionContext(): void {
  const artifact = selectedArtifact.value;
  productType.value = artifact?.product_type || selectedPart.value?.product_type || "";
  material.value = artifact?.material_code || selectedPart.value?.material_code || "";
  const moldType = props.masterDataOptions.mold_type.find((item) => item.code === selectedMold.value?.mold_type);
  const processFamily = typeof moldType?.attributes.process_family === "string" ? moldType.attributes.process_family : "";
  if (!moldingProcess.value || !props.masterDataOptions.molding_process.some((item) => item.code === moldingProcess.value)) {
    moldingProcess.value = processFamily || props.masterDataOptions.molding_process[0]?.code || "";
  }
  preview.value = null;
}

watch(selectedMoldId, () => {
  selectedRevisionId.value = availableRevisions.value.find((item) => item.status === "released")?.id || availableRevisions.value[0]?.id || "";
  selectedCadVersionId.value = "";
  applySelectionContext();
});
watch(selectedRevisionId, () => {
  const activeVersion = props.activeCad?.artifact_version_id;
  selectedCadVersionId.value = availableArtifacts.value.some((item) => item.versions?.some((version) => version.artifact_version_id === activeVersion))
    ? activeVersion || ""
    : availableArtifacts.value[0]?.versions?.[0]?.artifact_version_id || "";
  applySelectionContext();
});
watch(selectedCadVersionId, applySelectionContext);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [registry, cadItems] = await Promise.all([fetchRegistry(), fetchRecentCAD()]);
    projects.value = registry.projects;
    parts.value = registry.parts;
    molds.value = registry.molds.filter((item) => item.status === "active");
    revisions.value = registry.revisions.filter((item) => item.status !== "archived");
    artifacts.value = cadItems.filter((item) => item.mold_revision_id && item.lifecycle_status === "active");
    const activeArtifact = artifacts.value.find((item) => item.versions?.some((version) => version.artifact_version_id === props.activeCad?.artifact_version_id));
    selectedRevisionId.value = activeArtifact?.mold_revision_id || revisions.value.find((item) => item.status === "released")?.id || revisions.value[0]?.id || "";
    selectedMoldId.value = revisions.value.find((item) => item.id === selectedRevisionId.value)?.mold_id || molds.value[0]?.id || "";
    selectedCadVersionId.value = activeArtifact?.versions?.find((item) => item.artifact_version_id === props.activeCad?.artifact_version_id)?.artifact_version_id
      || availableArtifacts.value[0]?.versions?.[0]?.artifact_version_id || "";
    applySelectionContext();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load mold planning context.");
  } finally {
    loading.value = false;
  }
}

async function resolveStandard(): Promise<void> {
  if (!canResolve.value) return;
  resolving.value = true;
  error.value = null;
  errorCode.value = "";
  preview.value = null;
  try {
    preview.value = await previewMoldPlanningResolution({
      mold_revision_id: selectedRevisionId.value,
      cad_artifact_version_id: selectedCadVersionId.value || undefined,
      context: {
        product_type: productType.value,
        material: material.value,
        molding_process: moldingProcess.value,
        location: location.value || undefined,
      },
    });
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to resolve a review rule set.");
    errorCode.value = caught instanceof MoldPlanningError ? caught.code : "MOLD_PLANNING_ERROR";
  } finally {
    resolving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="mold-planning-workspace" aria-labelledby="mold-planning-title">
    <header class="planning-intro">
      <div><p class="eyebrow">{{ t("Context-driven planning") }}</p><h2 id="mold-planning-title">{{ t("Plan the mold before selecting a review rule set") }}</h2><p>{{ t("Describe the engineering context first. The platform will resolve the applicable governed standard and preserve the reason for later review.") }}</p></div>
      <button type="button" class="secondary-button" @click="emit('navigate', '/governance/rules')">{{ t("Browse review rule sets") }}</button>
    </header>

    <div v-if="loading" class="workspace-state" role="status">{{ t("Loading mold planning context…") }}</div>
    <div v-else class="planning-work-grid">
      <form class="planning-context-panel" @submit.prevent="resolveStandard">
        <div class="section-heading"><div><span class="step-badge">1–2</span><h3>{{ t("Planning target and engineering context") }}</h3><p>{{ t("Choose a governed mold revision, then confirm the canonical conditions used for standard resolution.") }}</p></div></div>
        <div class="planning-form-grid">
          <FormField v-slot="{ fieldId }" :label="t('Mold')" required><select :id="fieldId" v-model="selectedMoldId" required><option v-for="item in molds" :key="item.id" :value="item.id">{{ item.mold_code }} · {{ item.name }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Mold revision')" required><select :id="fieldId" v-model="selectedRevisionId" required><option v-for="item in availableRevisions" :key="item.id" :value="item.id">{{ item.mold_code }}@{{ item.revision_code }} · {{ t(item.status) }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Planning purpose')" required><select :id="fieldId" v-model="purpose"><option value="new_mold">{{ t("New mold") }}</option><option value="modification">{{ t("Mold modification") }}</option><option value="design_change">{{ t("Design change") }}</option><option value="trial_improvement">{{ t("Trial improvement") }}</option></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('CAD version')" :hint="t('Optional; when selected, CAD metadata becomes the source for product and material context.')"><select :id="fieldId" v-model="selectedCadVersionId"><option value="">{{ t("No CAD selected") }}</option><optgroup v-for="artifact in availableArtifacts" :key="artifact.artifact_id" :label="artifact.name"><option v-for="version in artifact.versions" :key="version.artifact_version_id" :value="version.artifact_version_id">v{{ version.version_number }} · {{ version.original_filename }}</option></optgroup></select></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Product type')" required><select :id="fieldId" v-model="productType" required><option value="">{{ t("Select product type") }}</option><option v-for="item in masterDataOptions.product_type" :key="item.code" :value="item.code">{{ optionLabel(item) }}</option></select><small class="context-source">{{ t(sourceFor('product_type')) }}</small></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Material')" required><select :id="fieldId" v-model="material" required><option value="">{{ t("Select material") }}</option><option v-for="item in masterDataOptions.material" :key="item.code" :value="item.code">{{ optionLabel(item) }}</option></select><small class="context-source">{{ t(sourceFor('material')) }}</small></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Molding process')" required><select :id="fieldId" v-model="moldingProcess" required><option value="">{{ t("Select molding process") }}</option><option v-for="item in masterDataOptions.molding_process" :key="item.code" :value="item.code">{{ optionLabel(item) }}</option></select><small class="context-source">{{ t(sourceFor('molding_process')) }}</small></FormField>
          <FormField v-slot="{ fieldId }" :label="t('Location')"><select :id="fieldId" v-model="location"><option value="">{{ t("Not specified") }}</option><option v-for="item in masterDataOptions.location" :key="item.code" :value="item.code">{{ optionLabel(item) }}</option></select><small class="context-source">{{ t(sourceFor('location')) }}</small></FormField>
        </div>
        <div class="planning-context-summary"><span><small>{{ t("Project") }}</small><strong>{{ selectedProject?.code || "—" }}</strong></span><span><small>{{ t("Mold type") }}</small><strong>{{ selectedMold?.mold_type || "—" }}</strong></span><span><small>{{ t("Context source") }}</small><strong>{{ selectedCadVersionId ? t("Registry + CAD") : t("Registry + reference data") }}</strong></span></div>
        <p v-if="masterDataError" class="inline-validation error-state" role="alert">{{ masterDataError }}</p>
        <p v-if="error" class="planning-resolution-error" role="alert"><code>{{ errorCode }}</code><strong>{{ error }}</strong><span v-if="errorCode === 'RULE_PROFILE_AMBIGUOUS'">{{ t("Conflicting candidates must be resolved in mold rule governance before planning can continue.") }}</span></p>
        <button type="submit" :disabled="resolving || masterDataLoading || !canResolve">{{ resolving ? t("Resolving standard…") : t("Resolve recommended standard") }}</button>
      </form>

      <section class="planning-resolution-panel" aria-live="polite">
        <div class="section-heading"><div><span class="step-badge">3</span><h3>{{ t("Recommended standard") }}</h3><p>{{ t("The server ranks eligible published rule sets by specificity and priority.") }}</p></div></div>
        <article v-if="preview" class="recommended-rule-card" :class="`mode-${preview.selection_mode}`">
          <header><div><span>{{ t(preview.selection_mode) }}</span><h3>{{ preview.selected.display_name }}</h3><p>{{ preview.selected.profile_key }} · v{{ preview.selected.version }}</p></div><strong>{{ preview.selected.specificity }} {{ t("matched dimensions") }}</strong></header>
          <p class="resolution-reason">{{ t(preview.reason) }}</p>
          <dl><div><dt>{{ t("Matched conditions") }}</dt><dd>{{ preview.selected.matched_dimensions.map((item) => t(item)).join("、") || t("Controlled default") }}</dd></div><div><dt>{{ t("Priority") }}</dt><dd>{{ preview.selected.priority }}</dd></div><div><dt>{{ t("Owner") }}</dt><dd>{{ preview.selected.owner || "—" }}</dd></div><div><dt>{{ t("Approved by") }}</dt><dd>{{ preview.selected.approved_by || "—" }}</dd></div></dl>
          <details><summary>{{ t("Technical resolution information") }}</summary><code>{{ preview.applicability_checksum }}</code></details>
        </article>
        <div v-else class="planning-preview-empty"><span>◇</span><h3>{{ t("Complete the context to see a recommendation") }}</h3><p>{{ t("No rule set is selected until the governed server-side resolution succeeds.") }}</p></div>
      </section>
    </div>
  </section>
</template>
