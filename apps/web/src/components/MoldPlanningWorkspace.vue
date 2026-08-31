<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import type { AssistantContext } from "../api/assistant";
import { fetchRecentCAD, type CADArtifactSummary, type CADModelResult } from "../api/cad";
import type { MasterDataOptions } from "../api/masterData";
import {
  compareMoldPlanningCandidates,
  createMoldPlan,
  createMoldPlanHandoff,
  fetchMoldPlan,
  fetchMoldPlans,
  MoldPlanningError,
  previewMoldPlanningResolution,
  resolveMoldPlan,
  selectMoldPlanProfile,
  transitionMoldPlan,
  updateMoldPlan,
  type MoldPlan,
  type MoldPlanningCandidateComparison,
  type MoldPlanningResolutionPreview,
  type PlanningContextSource,
  type RuleResolutionCandidate,
} from "../api/moldPlanning";
import { fetchRegistry, type RegistryMold, type RegistryPart, type RegistryProject, type RegistryRevision } from "../api/registry";
import type { DeepLinkContext } from "../deepLinks";
import { useI18n } from "../i18n";
import FormField from "./FormField.vue";

const props = defineProps<{
  activeCad?: CADModelResult | null;
  masterDataOptions: MasterDataOptions;
  masterDataLoading?: boolean;
  masterDataError?: string | null;
  deepLink?: DeepLinkContext | null;
}>();
const emit = defineEmits<{
  navigate: [path: string];
  contextChange: [context: AssistantContext];
}>();
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
const plans = ref<MoldPlan[]>([]);
const storedPlan = ref<MoldPlan | null>(null);
const planName = ref("");
const planStatusFilter = ref("");
const saving = ref(false);
const handoffLoading = ref("");
const overrideCandidate = ref<RuleResolutionCandidate | null>(null);
const overrideReason = ref("");
const overriding = ref(false);
const hydratingPlan = ref(false);
const comparing = ref(false);
const selectedCandidateIds = ref<string[]>([]);
const comparison = ref<MoldPlanningCandidateComparison | null>(null);

const selectedMold = computed(() => molds.value.find((item) => item.id === selectedMoldId.value) || null);
const selectedRevision = computed(() => revisions.value.find((item) => item.id === selectedRevisionId.value) || null);
const selectedPart = computed(() => parts.value.find((item) => item.id === selectedMold.value?.product_part_id) || null);
const selectedProject = computed(() => projects.value.find((item) => item.id === selectedMold.value?.project_id) || null);
const availableRevisions = computed(() => revisions.value.filter((item) => item.mold_id === selectedMoldId.value));
const availableArtifacts = computed(() => artifacts.value.filter((item) => item.mold_revision_id === selectedRevisionId.value));
const selectedArtifact = computed(() => availableArtifacts.value.find((item) => item.versions?.some((version) => version.artifact_version_id === selectedCadVersionId.value)) || null);
const canResolve = computed(() => Boolean(selectedRevisionId.value && productType.value && material.value && moldingProcess.value));
const overrideSelectionCandidate = computed(() => {
  if (!preview.value) return null;
  const candidateId = selectedCandidateIds.value.find(
    (id) => id !== preview.value?.selected.profile_id,
  );
  return preview.value.candidates.find((item) => item.profile_id === candidateId) || null;
});

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
  comparison.value = null;
  selectedCandidateIds.value = [];
}

async function loadPlans(): Promise<void> {
  try {
    const payload = await fetchMoldPlans({ status: planStatusFilter.value || undefined });
    plans.value = payload.items;
  } catch {
    plans.value = [];
  }
}

watch(selectedMoldId, () => {
  if (hydratingPlan.value) return;
  selectedRevisionId.value = availableRevisions.value.find((item) => item.status === "released")?.id || availableRevisions.value[0]?.id || "";
  selectedCadVersionId.value = "";
  applySelectionContext();
});
watch(selectedRevisionId, () => {
  if (hydratingPlan.value) return;
  const activeVersion = props.activeCad?.artifact_version_id;
  selectedCadVersionId.value = availableArtifacts.value.some((item) => item.versions?.some((version) => version.artifact_version_id === activeVersion))
    ? activeVersion || ""
    : availableArtifacts.value[0]?.versions?.[0]?.artifact_version_id || "";
  applySelectionContext();
});
watch(selectedCadVersionId, () => {
  if (!hydratingPlan.value) applySelectionContext();
});

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
    await loadPlans();
    if (props.deepLink?.target === "mold_plan") {
      await openPlan(props.deepLink.refs.mold_plan_id);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load mold planning context.");
  } finally {
    loading.value = false;
  }
}

function newPlan(): void {
  storedPlan.value = null;
  planName.value = "";
  preview.value = null;
  comparison.value = null;
  error.value = null;
}

async function openPlan(planId: string): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const plan = await fetchMoldPlan(planId);
    hydratingPlan.value = true;
    storedPlan.value = plan;
    planName.value = plan.name;
    purpose.value = plan.purpose;
    selectedMoldId.value = plan.mold_id;
    selectedRevisionId.value = plan.mold_revision_id;
    selectedCadVersionId.value = plan.cad_artifact_version_id || "";
    productType.value = plan.context?.product_type?.value_code || "";
    material.value = plan.context?.material?.value_code || "";
    moldingProcess.value = plan.context?.molding_process?.value_code || "";
    location.value = plan.context?.location?.value_code || "";
    const latest = plan.latest_resolution;
    if (latest) {
      const selected = latest.candidates.find((item) => item.profile_id === latest.selected_profile_id);
      if (selected) {
        const sources: Record<string, PlanningContextSource> = Object.fromEntries(
          Object.entries(plan.context || {}).map(([key, value]) => [
            key,
            {
              source_type: value.source_type as PlanningContextSource["source_type"],
              source_ref: value.source_ref,
            },
          ]),
        );
        preview.value = {
          schema_version: "1.0",
          mold_revision_id: plan.mold_revision_id,
          cad_artifact_version_id: plan.cad_artifact_version_id,
          selection_mode: latest.selection_mode as MoldPlanningResolutionPreview["selection_mode"],
          context: latest.context,
          sources,
          missing_fields: [],
          selected,
          candidates: latest.candidates,
          excluded_summary: [],
          reason: latest.reason,
          applicability_checksum: latest.applicability_checksum,
        };
        selectedCandidateIds.value = [selected.profile_id];
      }
    }
    await nextTick();
    hydratingPlan.value = false;
  } catch (caught) {
    hydratingPlan.value = false;
    error.value = caught instanceof Error ? caught.message : t("Unable to open the mold plan.");
  } finally {
    loading.value = false;
  }
}

async function savePlan(): Promise<void> {
  if (!preview.value || planName.value.trim().length < 3) return;
  saving.value = true;
  error.value = null;
  try {
    let plan = storedPlan.value;
    if (plan?.status === "draft") {
      plan = await updateMoldPlan(plan, { name: planName.value.trim(), purpose: purpose.value as MoldPlan["purpose"] });
    } else if (!plan) {
      plan = await createMoldPlan({
        name: planName.value.trim(),
        purpose: purpose.value as MoldPlan["purpose"],
        mold_revision_id: selectedRevisionId.value,
        cad_artifact_version_id: selectedCadVersionId.value || undefined,
        context: { product_type: productType.value, material: material.value, molding_process: moldingProcess.value, location: location.value || undefined },
      });
    }
    if (plan?.status === "draft") plan = await resolveMoldPlan(plan.plan_id);
    storedPlan.value = plan;
    await loadPlans();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to save the mold plan.");
  } finally {
    saving.value = false;
  }
}

async function transitionPlan(action: "complete" | "reopen" | "archive"): Promise<void> {
  if (!storedPlan.value) return;
  const reason = window.prompt(t("Enter the lifecycle reason"), t("Mold planning lifecycle update"));
  if (!reason) return;
  saving.value = true;
  try {
    storedPlan.value = await transitionMoldPlan(storedPlan.value, action, reason);
    await loadPlans();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to update the mold plan.");
  } finally {
    saving.value = false;
  }
}

async function startHandoff(handoffType: "design_review" | "cad" | "similarity" | "cae"): Promise<void> {
  if (!storedPlan.value) return;
  handoffLoading.value = handoffType;
  error.value = null;
  try {
    const handoff = await createMoldPlanHandoff(storedPlan.value, handoffType);
    storedPlan.value = await fetchMoldPlan(storedPlan.value.plan_id);
    const path = handoff.contract.ui_path;
    if (handoffType === "design_review") {
      window.location.assign(path);
    } else {
      emit("navigate", path);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to start the engineering handoff.");
  } finally {
    handoffLoading.value = "";
  }
}

function requestProfileOverride(candidate: RuleResolutionCandidate): void {
  overrideCandidate.value = candidate;
  overrideReason.value = "";
}

async function confirmProfileOverride(): Promise<void> {
  if (!storedPlan.value || !overrideCandidate.value || overrideReason.value.trim().length < 10) return;
  overriding.value = true;
  error.value = null;
  try {
    storedPlan.value = await selectMoldPlanProfile(
      storedPlan.value,
      overrideCandidate.value.profile_id,
      overrideReason.value.trim(),
    );
    const selected = overrideCandidate.value;
    preview.value = {
      ...preview.value!,
      selection_mode: "manual_override",
      selected,
      reason: storedPlan.value.latest_resolution?.reason || "",
    };
    overrideCandidate.value = null;
    overrideReason.value = "";
    await loadPlans();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to change the selected rule set.");
  } finally {
    overriding.value = false;
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
    selectedCandidateIds.value = [preview.value.selected.profile_id];
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to resolve a review rule set.");
    errorCode.value = caught instanceof MoldPlanningError ? caught.code : "MOLD_PLANNING_ERROR";
  } finally {
    resolving.value = false;
  }
}

function toggleCandidate(profileId: string): void {
  if (selectedCandidateIds.value.includes(profileId)) {
    if (profileId !== preview.value?.selected.profile_id) {
      selectedCandidateIds.value = selectedCandidateIds.value.filter((item) => item !== profileId);
    }
    return;
  }
  if (selectedCandidateIds.value.length < 3) selectedCandidateIds.value.push(profileId);
}

async function compareCandidates(): Promise<void> {
  if (selectedCandidateIds.value.length < 2) return;
  comparing.value = true;
  error.value = null;
  try {
    comparison.value = await compareMoldPlanningCandidates({
      mold_revision_id: selectedRevisionId.value,
      cad_artifact_version_id: selectedCadVersionId.value || undefined,
      context: {
        product_type: productType.value,
        material: material.value,
        molding_process: moldingProcess.value,
        location: location.value || undefined,
      },
      profile_ids: selectedCandidateIds.value,
    });
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to compare review rule sets.");
  } finally {
    comparing.value = false;
  }
}

onMounted(load);

watch(
  () => [storedPlan.value?.plan_id, storedPlan.value?.latest_resolution?.resolution_id],
  () => {
    emit("contextChange", {
      context_version: "1.0",
      page: "mold_planning",
      ui_locale: locale.value,
      ...(storedPlan.value?.plan_id ? { mold_plan_id: storedPlan.value.plan_id } : {}),
      ...(storedPlan.value?.mold_revision_id
        ? { mold_revision_id: storedPlan.value.mold_revision_id }
        : {}),
      ...(storedPlan.value?.cad_artifact_version_id
        ? { cad_artifact_version_id: storedPlan.value.cad_artifact_version_id }
        : {}),
      ...(storedPlan.value?.latest_resolution?.resolution_id
        ? { resolution_id: storedPlan.value.latest_resolution.resolution_id }
        : {}),
      ...(storedPlan.value?.latest_resolution?.selected_profile_id
        ? { selected_profile_id: storedPlan.value.latest_resolution.selected_profile_id }
        : {}),
    });
  },
  { immediate: true },
);
</script>

<template>
  <section class="mold-planning-workspace" aria-labelledby="mold-planning-title">
    <header class="planning-intro">
      <div><p class="eyebrow">{{ t("Context-driven planning") }}</p><h2 id="mold-planning-title">{{ t("Plan the mold before selecting a review rule set") }}</h2><p>{{ t("Describe the engineering context first. The platform will resolve the applicable governed standard and preserve the reason for later review.") }}</p></div>
      <button type="button" class="secondary-button" @click="emit('navigate', '/governance/rules')">{{ t("Browse review rule sets") }}</button>
    </header>

    <section class="mold-plan-catalog" aria-labelledby="mold-plan-catalog-title">
      <div class="section-heading"><div><p class="eyebrow">{{ t("Saved planning records") }}</p><h3 id="mold-plan-catalog-title">{{ t("Mold plans") }}</h3></div><div class="plan-catalog-actions"><select v-model="planStatusFilter" :aria-label="t('Filter plans by status')" @change="loadPlans"><option value="">{{ t("All statuses") }}</option><option v-for="status in ['draft', 'ready', 'completed', 'archived']" :key="status" :value="status">{{ t(status) }}</option></select><button type="button" class="secondary-button" @click="newPlan">＋ {{ t("New plan") }}</button></div></div>
      <div v-if="plans.length" class="mold-plan-card-list">
        <button v-for="plan in plans" :key="plan.plan_id" type="button" :class="{ active: storedPlan?.plan_id === plan.plan_id }" @click="openPlan(plan.plan_id)"><span><strong>{{ plan.name }}</strong><small>{{ plan.plan_code }} · {{ plan.mold_code }}@{{ plan.mold_revision }}</small></span><em :class="`status-${plan.status}`">{{ t(plan.status) }}</em><small>{{ plan.latest_resolution?.selected_profile_key || t("Not resolved") }}</small></button>
      </div>
      <p v-else class="catalog-empty-note">{{ t("No saved mold plans match this view. Start a new plan below.") }}</p>
    </section>

    <div v-if="loading" class="workspace-state" role="status">{{ t("Loading mold planning context…") }}</div>
    <div v-else class="planning-work-grid">
      <form class="planning-context-panel" @submit.prevent="resolveStandard">
        <div class="section-heading"><div><span class="step-badge">1–2</span><h3>{{ t("Planning target and engineering context") }}</h3><p>{{ t("Choose a governed mold revision, then confirm the canonical conditions used for standard resolution.") }}</p></div></div>
        <div class="planning-form-grid">
          <FormField v-slot="{ fieldId }" class="form-wide" :label="t('Plan name')" required :hint="t('Use a name that identifies the product, mold and planning purpose.')"><input :id="fieldId" v-model="planName" minlength="3" maxlength="120" required :disabled="storedPlan?.status !== undefined && storedPlan.status !== 'draft'" /></FormField>
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
          <div class="plan-save-actions"><button v-if="!storedPlan || storedPlan.status === 'draft'" type="button" :disabled="saving || planName.trim().length < 3" @click="savePlan">{{ saving ? t("Saving…") : t("Save plan and resolution") }}</button><button v-if="storedPlan?.status === 'ready'" type="button" :disabled="saving" @click="transitionPlan('complete')">{{ t("Complete planning") }}</button><button v-if="storedPlan && storedPlan.status !== 'archived'" type="button" class="danger-button" :disabled="saving" @click="transitionPlan('archive')">{{ t("Archive plan") }}</button><button v-if="storedPlan && ['completed', 'archived'].includes(storedPlan.status)" type="button" class="secondary-button" :disabled="saving" @click="transitionPlan('reopen')">{{ t("Reopen as draft") }}</button></div>
        </article>
        <details v-if="preview" class="candidate-catalog" open>
          <summary>{{ t("Other eligible candidates") }} <span>{{ preview.candidates.length }}</span></summary>
          <p>{{ t("Select up to three eligible rule sets. The recommended set remains the comparison baseline.") }}</p>
          <div class="candidate-option-list">
            <label v-for="candidate in preview.candidates" :key="candidate.profile_id" :class="{ selected: selectedCandidateIds.includes(candidate.profile_id) }">
              <input
                type="checkbox"
                :checked="selectedCandidateIds.includes(candidate.profile_id)"
                :disabled="candidate.profile_id === preview.selected.profile_id || (!selectedCandidateIds.includes(candidate.profile_id) && selectedCandidateIds.length >= 3)"
                @change="toggleCandidate(candidate.profile_id)"
              />
              <span><strong>{{ candidate.display_name }}</strong><small>v{{ candidate.version }} · {{ candidate.specificity }} {{ t("matched dimensions") }} · {{ t("Priority") }} {{ candidate.priority }}</small></span>
              <em v-if="candidate.profile_id === preview.selected.profile_id">{{ t("Recommended") }}</em>
            </label>
          </div>
          <button type="button" :disabled="selectedCandidateIds.length < 2 || comparing" @click="compareCandidates">{{ comparing ? t("Comparing…") : t("Compare selected rule sets") }}</button>
          <button
            v-if="storedPlan?.status === 'ready' && overrideSelectionCandidate"
            type="button"
            class="secondary-button"
            @click="requestProfileOverride(overrideSelectionCandidate!)"
          >
            {{ t("Select compared rule set") }}
          </button>
        </details>
        <div v-else class="planning-preview-empty"><span>◇</span><h3>{{ t("Complete the context to see a recommendation") }}</h3><p>{{ t("No rule set is selected until the governed server-side resolution succeeds.") }}</p></div>
      </section>
    </div>

    <section v-if="storedPlan?.latest_resolution" class="planning-requirements" aria-labelledby="planning-requirements-title">
      <div class="section-heading"><div><span class="step-badge">4–5</span><h3 id="planning-requirements-title">{{ t("Planning requirements and engineering handoff") }}</h3><p>{{ t("Review the immutable rule requirements and pass the same governed context to the next engineering workspace.") }}</p></div></div>
      <div class="requirement-summary-grid">
        <article><small>{{ t("Total requirements") }}</small><strong>{{ storedPlan.latest_resolution.requirement_summary.total }}</strong></article>
        <article><small>{{ t("Must") }}</small><strong>{{ storedPlan.latest_resolution.requirement_summary.must }}</strong></article>
        <article><small>{{ t("High risk") }}</small><strong>{{ storedPlan.latest_resolution.requirement_summary.high_risk }}</strong></article>
        <article><small>{{ t("Insufficient data") }}</small><strong>{{ storedPlan.latest_resolution.requirement_summary.insufficient_data }}</strong></article>
      </div>
      <div class="requirement-list">
        <article v-for="requirement in storedPlan.latest_resolution.requirements" :key="requirement.requirement_id">
          <header><div><code>{{ requirement.rule_id }}@{{ requirement.rule_version }}</code><h4>{{ requirement.title }}</h4></div><span :class="`severity-${requirement.severity}`">{{ t(requirement.severity) }}</span></header>
          <p>{{ requirement.description }}</p>
          <dl><div><dt>{{ t("Threshold") }}</dt><dd>{{ requirement.operator }} {{ requirement.limit_value ?? "—" }} {{ requirement.unit }}</dd></div><div><dt>{{ t("Evidence") }}</dt><dd>{{ t(requirement.evidence_requirement.kind) }}</dd></div><div><dt>{{ t("Planning status") }}</dt><dd>{{ t(requirement.planning_status) }}</dd></div></dl>
          <p class="requirement-recommendation">{{ requirement.recommendation }}</p>
        </article>
      </div>
      <div class="planning-handoff-actions">
        <button type="button" :disabled="Boolean(handoffLoading)" @click="startHandoff('design_review')">{{ handoffLoading === 'design_review' ? t("Creating design review…") : t("Create design review") }}</button>
        <button type="button" class="secondary-button" :disabled="Boolean(handoffLoading)" @click="startHandoff('cad')">{{ t("Open CAD") }}</button>
        <button type="button" class="secondary-button" :disabled="Boolean(handoffLoading)" @click="startHandoff('similarity')">{{ t("Find similar molds") }}</button>
        <button type="button" class="secondary-button" :disabled="Boolean(handoffLoading)" @click="startHandoff('cae')">{{ t("Prepare CAE comparison") }}</button>
      </div>
      <p v-if="storedPlan.latest_resolution.handoffs.length" class="handoff-lineage-note">{{ t("Recorded handoffs") }}: {{ storedPlan.latest_resolution.handoffs.map((item) => t(item.handoff_type)).join("、") }}</p>
    </section>

    <section v-if="comparison" class="candidate-comparison" aria-labelledby="candidate-comparison-title">
      <div class="section-heading"><div><span class="step-badge">3B</span><h3 id="candidate-comparison-title">{{ t("Rule set comparison") }}</h3><p>{{ t("Engineering differences are calculated by the server against the recommended baseline.") }}</p></div><button type="button" class="text-button" @click="comparison = null">{{ t("Close comparison") }}</button></div>
      <div class="comparison-card-grid">
        <article v-for="item in comparison.items" :key="item.profile_id" :class="{ baseline: item.profile_id === comparison.baseline_profile_id }">
          <header><div><span v-if="item.profile_id === comparison.baseline_profile_id">{{ t("Baseline") }}</span><h4>{{ item.display_name }}</h4><p>{{ item.profile_key }} · v{{ item.version }}</p></div><strong>{{ item.enabled_rule_count }} {{ t("rules") }}</strong></header>
          <dl><div><dt>{{ t("Priority") }}</dt><dd>{{ item.priority }}</dd></div><div><dt>{{ t("High-risk rules") }}</dt><dd>{{ item.high_risk_rules.length }}</dd></div><div><dt>{{ t("Rule categories") }}</dt><dd>{{ item.risk_categories.join("、") || "—" }}</dd></div><div><dt>{{ t("Applicability") }}</dt><dd>{{ item.applicability.length }}</dd></div></dl>
          <div class="difference-chips"><span class="added">＋{{ item.difference_summary.added.length }}</span><span class="modified">△{{ item.difference_summary.modified.length }}</span><span class="removed">－{{ item.difference_summary.removed.length }}</span></div>
          <details v-if="item.high_risk_rules.length"><summary>{{ t("View high-risk rules") }}</summary><ul><li v-for="rule in item.high_risk_rules" :key="rule.rule_id"><code>{{ rule.rule_id }}</code> {{ rule.title }}</li></ul></details>
        </article>
      </div>
    </section>

    <div v-if="overrideCandidate" class="modal-backdrop" role="presentation" @click.self="overrideCandidate = null">
      <section class="override-dialog" role="dialog" aria-modal="true" aria-labelledby="override-dialog-title">
        <p class="eyebrow">{{ t("Governed manual selection") }}</p>
        <h3 id="override-dialog-title">{{ t("Change to {profile}", { profile: overrideCandidate.display_name }) }}</h3>
        <p>{{ t("This rule set is eligible for the saved context. The automatic recommendation and your reason will both remain in audit history.") }}</p>
        <FormField v-slot="{ fieldId }" :label="t('Override reason')" required :hint="t('Describe the engineering reason in at least 10 characters.')">
          <textarea :id="fieldId" v-model="overrideReason" minlength="10" maxlength="512" rows="4" required></textarea>
        </FormField>
        <div class="override-dialog-actions">
          <button type="button" class="secondary-button" :disabled="overriding" @click="overrideCandidate = null">{{ t("Cancel") }}</button>
          <button type="button" :disabled="overriding || overrideReason.trim().length < 10" @click="confirmProfileOverride">{{ overriding ? t("Saving…") : t("Confirm governed selection") }}</button>
        </div>
      </section>
    </div>
  </section>
</template>
