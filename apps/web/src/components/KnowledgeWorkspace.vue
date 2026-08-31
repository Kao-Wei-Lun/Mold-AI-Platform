<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
  fetchKnowledgeDocuments,
  fetchKnowledgeJob,
  transitionKnowledgeDocument,
  uploadKnowledge,
  type KnowledgeDocument,
  type KnowledgeJob,
} from "../api/knowledge";
import type { LocalAccount } from "../api/identity";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import { uploadPolicies, validateUploadFile } from "../fileUpload";
import FileDropZone from "./FileDropZone.vue";
import FormField from "./FormField.vue";

type WorkflowAction = "submit" | "approve" | "publish" | "retire";

const props = defineProps<{ path?: string; currentAccount?: LocalAccount | null }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();

const file = ref<File | null>(null);
const title = ref("");
const documentType = ref("design_guideline");
const authorityLevel = ref("demo");
const language = ref("en");
const documents = ref<KnowledgeDocument[]>([]);
const job = ref<KnowledgeJob | null>(null);
const lastUploadedDocumentId = ref("");
const uploading = ref(false);
const loadingDocuments = ref(false);
const error = ref<string | null>(null);
const uploadAttempted = ref(false);
const fileSelectionError = ref("");
const documentQuery = ref("");
const documentStatus = ref("");
const workflowBusyId = ref("");
const pendingWorkflow = ref<{ document: KnowledgeDocument; action: WorkflowAction } | null>(null);
const workflowReason = ref("");
let pollTimer: number | null = null;

const location = computed(() => new URL(props.path || "/governance/knowledge", window.location.origin));
const activeView = computed(() => location.value.searchParams.get("view") === "import" ? "import" : "documents");
const terminal = computed(() => ["succeeded", "failed", "cancelled", "expired"].includes(job.value?.state || ""));
const indexedCount = computed(() => documents.value.filter((document) => document.ingestion_status === "indexed").length);
const publishedCount = computed(() => documents.value.filter((document) => document.publication_status === "published").length);
const reviewCount = computed(() => documents.value.filter((document) => ["in_review", "approved"].includes(document.publication_status)).length);
const canAuthor = computed(() => props.currentAccount?.permissions.includes("knowledge:author") || false);
const canApprove = computed(() => props.currentAccount?.permissions.includes("knowledge:approve") || false);
const missingUploadFields = computed(() => Number(!file.value) + Number(title.value.trim().length < 3));
const filteredDocuments = computed(() => {
  const keyword = documentQuery.value.trim().toLocaleLowerCase();
  return documents.value.filter((document) => {
    const matchesKeyword = !keyword || [document.title, document.original_filename, document.document_type]
      .some((value) => value.toLocaleLowerCase().includes(keyword));
    return matchesKeyword && (!documentStatus.value || document.publication_status === documentStatus.value);
  });
});
const fileError = computed(() =>
  fileSelectionError.value || (uploadAttempted.value && !file.value
    ? t("Choose a TXT, Markdown, PDF or DOCX file.")
    : ""),
);
const titleError = computed(() =>
  uploadAttempted.value && title.value.trim().length < 3
    ? t("Enter a title with at least 3 characters.")
    : "",
);

function selectFile(candidate: File): void {
  fileSelectionError.value = "";
  const validation = validateUploadFile(candidate, uploadPolicies.knowledge);
  if (validation) {
    file.value = null;
    fileSelectionError.value = validation === "too_large"
      ? t("File size exceeds the {limit} MB limit.", { limit: 5 })
      : t("File type is not supported. Allowed: {formats}.", { formats: "TXT, MD, PDF, DOCX" });
    return;
  }
  file.value = candidate;
  if (!title.value) title.value = candidate.name.replace(/\.(md|txt|pdf|docx)$/i, "");
}

async function loadDocuments(): Promise<void> {
  loadingDocuments.value = true;
  error.value = null;
  try {
    documents.value = await fetchKnowledgeDocuments();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load knowledge documents.");
  } finally {
    loadingDocuments.value = false;
  }
}

function schedulePoll(): void {
  if (!terminal.value) pollTimer = window.setTimeout(refreshJob, 900);
}

async function refreshJob(): Promise<void> {
  if (!job.value) return;
  try {
    job.value = await fetchKnowledgeJob(job.value.job_id);
    if (job.value.state === "succeeded" || job.value.state === "failed") await loadDocuments();
    schedulePoll();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to refresh ingestion job.");
  }
}

async function submitUpload(): Promise<void> {
  uploadAttempted.value = true;
  if (missingUploadFields.value || !file.value) return;
  uploading.value = true;
  error.value = null;
  job.value = null;
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  try {
    const accepted = await uploadKnowledge(file.value, {
      title: title.value,
      documentType: documentType.value,
      authorityLevel: authorityLevel.value,
      language: language.value,
    });
    lastUploadedDocumentId.value = accepted.document_id;
    job.value = await fetchKnowledgeJob(accepted.job_id);
    uploadAttempted.value = false;
    file.value = null;
    title.value = "";
    fileSelectionError.value = "";
    schedulePoll();
    pushToast(t("Document ingestion started."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge upload failed.");
    pushToast(error.value, "error");
  } finally {
    uploading.value = false;
  }
}

function beginWorkflow(document: KnowledgeDocument, action: WorkflowAction): void {
  workflowReason.value = "";
  pendingWorkflow.value = { document, action };
}

function closeWorkflow(): void {
  if (workflowBusyId.value) return;
  pendingWorkflow.value = null;
  workflowReason.value = "";
}

function nextStatus(action: WorkflowAction): string {
  return { submit: "in_review", approve: "approved", publish: "published", retire: "retired" }[action];
}

function workflowImpact(action: WorkflowAction): string {
  if (action === "publish") return t("Publishing makes this version available to new engineering knowledge searches.");
  if (action === "retire") return t("Retiring removes this version from new searches while preserving historical citations.");
  if (action === "approve") return t("Approval confirms technical review and prepares this version for publication.");
  return t("Submission sends this draft into the controlled review workflow.");
}

async function confirmWorkflow(): Promise<void> {
  if (!pendingWorkflow.value || !workflowReason.value.trim()) return;
  const { document, action } = pendingWorkflow.value;
  workflowBusyId.value = document.document_id;
  error.value = null;
  try {
    await transitionKnowledgeDocument(document, action, workflowReason.value.trim());
    pendingWorkflow.value = null;
    workflowReason.value = "";
    await loadDocuments();
    pushToast(t("Knowledge lifecycle updated."), "success");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Knowledge workflow failed.");
    pushToast(error.value, "error");
  } finally {
    workflowBusyId.value = "";
  }
}

function documentTypeLabel(value: string): string {
  return t(value.replaceAll("_", " "));
}

onMounted(loadDocuments);
watch(() => activeView.value, () => { error.value = null; });
onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
});
</script>

<template>
  <section class="knowledge-workspace knowledge-management-workspace" aria-labelledby="knowledge-management-title">
    <div class="section-heading knowledge-management-heading">
      <div>
        <p class="eyebrow">{{ t("Knowledge governance") }}</p>
        <h2 id="knowledge-management-title">{{ t("Knowledge document management") }}</h2>
        <p>{{ t("Import, inspect and govern the document versions used by engineering knowledge search.") }}</p>
      </div>
      <div class="knowledge-heading-actions">
        <button type="button" class="secondary-button" :disabled="loadingDocuments" @click="loadDocuments">{{ t("Refresh") }}</button>
        <button v-if="canAuthor && activeView === 'documents'" type="button" @click="emit('navigate', '/governance/knowledge?view=import')">＋ {{ t("Import document") }}</button>
        <button v-if="activeView === 'import'" type="button" class="secondary-button" @click="emit('navigate', '/governance/knowledge')">← {{ t("Back to documents") }}</button>
      </div>
    </div>

    <template v-if="activeView === 'documents'">
      <section class="knowledge-management-summary" :aria-label="t('Knowledge document summary')">
        <div><span>{{ t("Documents") }}</span><strong>{{ documents.length }}</strong></div>
        <div><span>{{ t("Indexed") }}</span><strong>{{ indexedCount }}</strong></div>
        <div><span>{{ t("Published") }}</span><strong>{{ publishedCount }}</strong></div>
        <div><span>{{ t("Awaiting review") }}</span><strong>{{ reviewCount }}</strong></div>
      </section>

      <section class="knowledge-document-toolbar">
        <label><span>{{ t("Search documents") }}</span><input v-model="documentQuery" type="search" :placeholder="t('Title, file name or document type')" /></label>
        <label><span>{{ t("Publication status") }}</span><select v-model="documentStatus"><option value="">{{ t("All statuses") }}</option><option value="draft">{{ t("draft") }}</option><option value="in_review">{{ t("in review") }}</option><option value="approved">{{ t("approved") }}</option><option value="published">{{ t("published") }}</option><option value="retired">{{ t("retired") }}</option></select></label>
      </section>

      <p v-if="loadingDocuments" class="workspace-state">{{ t("Loading knowledge documents...") }}</p>
      <section v-else-if="filteredDocuments.length" class="knowledge-document-grid">
        <article v-for="document in filteredDocuments" :key="document.document_id" class="knowledge-document-card">
          <div class="knowledge-document-card-heading">
            <div><span>{{ documentTypeLabel(document.document_type) }} · v{{ document.version_number }}</span><h3>{{ document.title }}</h3><small>{{ document.original_filename }}</small></div>
            <span class="document-status" :class="document.ingestion_status">{{ t(document.publication_status) }}</span>
          </div>
          <dl>
            <div><dt>{{ t("Index status") }}</dt><dd>{{ t(document.ingestion_status) }}</dd></div>
            <div><dt>{{ t("Authority") }}</dt><dd>{{ t(document.authority_level.replaceAll("_", " ")) }}</dd></div>
            <div><dt>{{ t("Language") }}</dt><dd>{{ document.language }}</dd></div>
            <div><dt>{{ t("Chunks") }}</dt><dd>{{ document.chunk_count }}</dd></div>
          </dl>
          <div class="knowledge-document-actions">
            <button type="button" class="secondary-button" @click="emit('navigate', `/data/knowledge/${document.document_id}`)">{{ t("View document details") }}</button>
            <button v-if="canAuthor && document.publication_status === 'draft'" type="button" class="text-button" @click="beginWorkflow(document, 'submit')">{{ t("Submit") }}</button>
            <button v-if="canApprove && document.publication_status === 'in_review'" type="button" class="text-button" @click="beginWorkflow(document, 'approve')">{{ t("Approve") }}</button>
            <button v-if="canApprove && document.publication_status === 'approved'" type="button" class="text-button" @click="beginWorkflow(document, 'publish')">{{ t("Publish") }}</button>
            <button v-if="canApprove && document.publication_status === 'published'" type="button" class="text-button danger-text" @click="beginWorkflow(document, 'retire')">{{ t("Retire") }}</button>
          </div>
        </article>
      </section>
      <section v-else class="workspace-empty-state" role="status">
        <div><p class="eyebrow">{{ t("Knowledge documents") }}</p><h3>{{ t("No matching knowledge documents") }}</h3><p>{{ t("Adjust the filters or import a governed source document.") }}</p></div>
        <button v-if="canAuthor" type="button" @click="emit('navigate', '/governance/knowledge?view=import')">{{ t("Import document") }}</button>
      </section>
    </template>

    <template v-else>
      <section v-if="canAuthor" class="knowledge-import-workspace">
        <div class="knowledge-import-intro"><span>1</span><div><h3>{{ t("Import a governed knowledge document") }}</h3><p>{{ t("Select the source and describe how it may be used. Security screening and indexing run after submission.") }}</p></div></div>
        <form class="knowledge-upload-form" @submit.prevent="submitUpload">
          <FormField v-slot="{ fieldId, describedBy, invalid }" class="file-field" :label="t('Knowledge source file')" required :helper="t('TXT, Markdown, PDF or DOCX · maximum 5 MB · security screened')" :error="fileError">
            <FileDropZone :id="fieldId" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" :prompt="t('Drop TXT, Markdown, PDF or DOCX here')" :ready-text="t('Ready for security screening')" :selected-file="file" :described-by="describedBy" :invalid="invalid" :disabled="uploading" @select="selectFile" />
          </FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Title')" required :helper="t('Use at least 3 characters so the source is recognizable.')" :error="titleError"><input :id="fieldId" v-model="title" type="text" maxlength="255" minlength="3" required :placeholder="t('Demo molding SOP')" :aria-describedby="describedBy" :aria-invalid="invalid" /></FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Document type')" required><select :id="fieldId" v-model="documentType" required :aria-describedby="describedBy" :aria-invalid="invalid"><option value="demo_sop">{{ t("Demo SOP") }}</option><option value="design_guideline">{{ t("Design guideline") }}</option><option value="trial_report">{{ t("Trial report") }}</option><option value="case_note">{{ t("Case note") }}</option></select></FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Authority')" required><select :id="fieldId" v-model="authorityLevel" required :aria-describedby="describedBy" :aria-invalid="invalid"><option value="demo">Demo</option><option value="reviewed_demo">{{ t("Reviewed Demo") }}</option></select></FormField>
          <FormField v-slot="{ fieldId, describedBy, invalid }" :label="t('Language')" required><select :id="fieldId" v-model="language" required :aria-describedby="describedBy" :aria-invalid="invalid"><option value="en">{{ t("English") }}</option><option value="zh-Hant">{{ t("Traditional Chinese") }}</option></select></FormField>
          <p v-if="missingUploadFields" class="form-validation-summary" aria-live="polite">{{ t("Required fields remaining: {count}", { count: missingUploadFields }) }}</p>
          <button type="submit" :disabled="uploading" :aria-busy="uploading">{{ uploading ? t("Uploading...") : t("Import and start indexing") }}</button>
        </form>
        <div v-if="job" class="job-panel compact-job">
          <div class="job-heading"><div><span class="job-state" :class="job.state">{{ t(job.state) }}</span><strong>{{ t(job.stage.replaceAll("_", " ")) }}</strong></div><span>{{ job.progress }}%</span></div>
          <div class="progress-track" :aria-label="t('Knowledge ingestion progress')"><span :style="{ width: `${job.progress}%` }"></span></div>
          <div v-if="job.state === 'succeeded'" class="knowledge-import-handoff"><strong>{{ t("Document ingestion completed") }}</strong><div><button v-if="lastUploadedDocumentId" type="button" @click="emit('navigate', `/data/knowledge/${lastUploadedDocumentId}`)">{{ t("View imported document") }}</button><button type="button" class="secondary-button" @click="emit('navigate', '/governance/knowledge')">{{ t("Return to document management") }}</button></div></div>
        </div>
      </section>
      <section v-else class="workspace-state error-state"><strong>{{ t("Permission required") }}</strong><span>{{ t("Your account cannot import knowledge documents.") }}</span><button type="button" @click="emit('navigate', '/governance/knowledge')">{{ t("Back to documents") }}</button></section>
    </template>

    <div v-if="pendingWorkflow" class="workflow-dialog-backdrop" @click.self="closeWorkflow">
      <section class="workflow-dialog" role="dialog" aria-modal="true" :aria-labelledby="`knowledge-workflow-${pendingWorkflow.document.document_id}`">
        <p class="eyebrow">{{ t("Controlled knowledge workflow") }}</p>
        <h3 :id="`knowledge-workflow-${pendingWorkflow.document.document_id}`">{{ t(pendingWorkflow.action) }} · {{ pendingWorkflow.document.title }}</h3>
        <div class="workflow-transition"><span>{{ t(pendingWorkflow.document.publication_status) }}</span><b>→</b><span>{{ t(nextStatus(pendingWorkflow.action)) }}</span></div>
        <p>{{ workflowImpact(pendingWorkflow.action) }}</p>
        <FormField v-slot="{ fieldId }" :label="t('Workflow reason')" required :helper="t('Explain the engineering or governance reason recorded in the audit trail.')"><textarea :id="fieldId" v-model="workflowReason" rows="3" maxlength="512" required :placeholder="t('Example: Technical review completed against the approved molding standard.')"></textarea></FormField>
        <div class="workflow-dialog-actions"><button type="button" class="secondary-button" :disabled="Boolean(workflowBusyId)" @click="closeWorkflow">{{ t("Cancel") }}</button><button type="button" :disabled="Boolean(workflowBusyId) || !workflowReason.trim()" @click="confirmWorkflow">{{ t("Confirm workflow action") }}</button></div>
      </section>
    </div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
