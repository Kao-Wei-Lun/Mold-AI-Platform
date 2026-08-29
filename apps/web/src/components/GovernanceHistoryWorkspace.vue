<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { downloadProtectedArtifact } from "../api/client";
import type { LocalAccount } from "../api/identity";
import {
  fetchKnowledgeDocument,
  fetchKnowledgeDocuments,
  transitionKnowledgeDocument,
  uploadKnowledgeVersion,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
} from "../api/knowledge";
import {
  cloneRuleProfile,
  fetchRuleProfile,
  fetchRuleProfileDiff,
  fetchRuleProfiles,
  transitionRuleProfile,
  updateRuleProfile,
  type RuleProfile,
  type RuleProfileDiff,
} from "../api/rules";
import { useI18n } from "../i18n";
import DataTable from "./DataTable.vue";
import DetailTabs from "./DetailTabs.vue";
import PropertyGrid from "./PropertyGrid.vue";
import RecordHeader from "./RecordHeader.vue";

const props = defineProps<{ domain: "rules" | "knowledge"; path: string; currentAccount?: LocalAccount | null }>();
const emit = defineEmits<{ navigate: [path: string] }>();
const { t } = useI18n();
const loading = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const reason = ref("");
const profiles = ref<RuleProfile[]>([]);
const profile = ref<RuleProfile | null>(null);
const diff = ref<RuleProfileDiff | null>(null);
const ruleJson = ref("[]");
const changeSummary = ref("");
const cloneVersion = ref("");
const documents = ref<KnowledgeDocument[]>([]);
const document = ref<KnowledgeDocumentDetail | null>(null);
const versionFile = ref<File | null>(null);
const versionTitle = ref("");
const acceptedJobId = ref("");

const location = computed(() => new URL(props.path, window.location.origin));
const recordId = computed(() => location.value.pathname.split("/").filter(Boolean)[2] || "");
const activeTab = computed(() => location.value.searchParams.get("tab") || "overview");
const against = computed(() => location.value.searchParams.get("against") || "");
const canRuleAuthor = computed(() => props.currentAccount?.permissions.includes("rules:author") || false);
const canRuleApprove = computed(() => props.currentAccount?.permissions.includes("rules:approve") || false);
const canKnowledgeAuthor = computed(() => props.currentAccount?.permissions.includes("knowledge:author") || false);
const canKnowledgeApprove = computed(() => props.currentAccount?.permissions.includes("knowledge:approve") || false);

function setTab(tab: string): void {
  if (!recordId.value) return;
  const query = new URLSearchParams({ tab });
  if (props.domain === "rules" && against.value) query.set("against", against.value);
  emit("navigate", `/data/${props.domain}/${recordId.value}?${query}`);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  notice.value = null;
  profile.value = null;
  document.value = null;
  diff.value = null;
  try {
    if (props.domain === "rules") {
      profiles.value = await fetchRuleProfiles();
      if (recordId.value) {
        profile.value = await fetchRuleProfile(recordId.value);
        ruleJson.value = JSON.stringify(profile.value.rules, null, 2);
        changeSummary.value = profile.value.change_summary;
        if (activeTab.value === "diff" && against.value) {
          diff.value = await fetchRuleProfileDiff(recordId.value, against.value);
        }
      }
    } else if (recordId.value) {
      document.value = await fetchKnowledgeDocument(recordId.value);
      versionTitle.value = document.value.title;
    } else {
      documents.value = await fetchKnowledgeDocuments();
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load governance history.");
  } finally {
    loading.value = false;
  }
}

async function mutate(action: () => Promise<void>, message: string): Promise<void> {
  if (!reason.value.trim()) {
    error.value = t("A change reason is required.");
    return;
  }
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await action();
    reason.value = "";
    notice.value = t(message);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Governance operation failed.");
  } finally {
    busy.value = false;
  }
}

function saveRuleDraft(): Promise<void> {
  if (!profile.value) return Promise.resolve();
  let rules: RuleProfile["rules"];
  try {
    const parsed = JSON.parse(ruleJson.value);
    if (!Array.isArray(parsed)) throw new Error();
    rules = parsed;
  } catch {
    error.value = t("Rules must be a valid JSON array.");
    return Promise.resolve();
  }
  return mutate(async () => {
    profile.value = await updateRuleProfile(profile.value!, { rules, change_summary: changeSummary.value, reason: reason.value });
    ruleJson.value = JSON.stringify(profile.value.rules, null, 2);
  }, "Rule draft saved with a new checksum.");
}

function cloneRules(): Promise<void> {
  if (!profile.value) return Promise.resolve();
  return mutate(async () => {
    const cloned = await cloneRuleProfile(profile.value!, { version: cloneVersion.value, changeSummary: changeSummary.value, reason: reason.value });
    emit("navigate", `/data/rules/${cloned.profile_id}`);
  }, "Rule draft version created.");
}

function transitionRules(action: "test" | "submit" | "approve" | "publish" | "retire"): Promise<void> {
  if (!profile.value) return Promise.resolve();
  return mutate(async () => {
    profile.value = await transitionRuleProfile(profile.value!, action, reason.value);
  }, "Rule lifecycle updated.");
}

function transitionDocument(action: "submit" | "approve" | "publish" | "retire"): Promise<void> {
  if (!document.value) return Promise.resolve();
  return mutate(async () => {
    const updated = await transitionKnowledgeDocument(document.value!, action, reason.value);
    document.value = { ...document.value!, ...updated };
  }, "Knowledge lifecycle updated.");
}

function chooseVersionFile(event: Event): void {
  versionFile.value = (event.target as HTMLInputElement).files?.[0] || null;
}

function createKnowledgeVersion(): Promise<void> {
  if (!document.value || !versionFile.value) {
    error.value = t("Choose a UTF-8 TXT or Markdown file.");
    return Promise.resolve();
  }
  return mutate(async () => {
    const accepted = await uploadKnowledgeVersion(document.value!, versionFile.value!, {
      title: versionTitle.value,
      documentType: document.value!.document_type,
      authorityLevel: document.value!.authority_level,
      language: document.value!.language,
    });
    acceptedJobId.value = accepted.job_id;
  }, "New knowledge version ingestion started.");
}

function selectBaseline(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  emit("navigate", `/data/rules/${recordId.value}?tab=diff${value ? `&against=${value}` : ""}`);
}

watch(() => [props.domain, recordId.value, activeTab.value, against.value], load, { immediate: true });
</script>

<template>
  <section class="governance-history-workspace">
    <div class="history-list-heading"><div><p class="eyebrow">{{ t("Historical data") }}</p><h2>{{ t(domain === "rules" ? "Mold rules" : "Knowledge documents") }}</h2></div><div class="history-list-actions"><button v-if="recordId" type="button" class="text-button" @click="emit('navigate', `/data/${domain}`)">← {{ t("Back to records") }}</button><button type="button" :disabled="loading" @click="load">{{ t("Refresh data") }}</button></div></div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
    <section v-if="loading" class="workspace-state">{{ t("Loading complete historical record…") }}</section>

    <template v-else-if="domain === 'rules' && !recordId">
      <DataTable :columns="[{ key: 'key', label: t('Profile') }, { key: 'version', label: t('Version') }, { key: 'rules', label: t('Rules') }, { key: 'owner', label: t('Owner') }, { key: 'status', label: t('Status') }, { key: 'summary', label: t('Change summary') }]" :items="profiles.map((item) => ({ id: item.profile_id, key: item.profile_key, version: item.version, rules: item.rule_count, owner: item.owner, status: item.workflow_status, summary: item.change_summary }))" @select="emit('navigate', `/data/rules/${$event.id}`)" />
    </template>

    <template v-else-if="profile">
      <RecordHeader :title="profile.profile_key" :identifier="profile.profile_id" :status="profile.workflow_status" :version="`${profile.version} · row ${profile.row_version}`" />
      <div v-if="canRuleAuthor || canRuleApprove" class="history-governance-actions">
        <input v-model="reason" :placeholder="t('Change reason')" />
        <button v-if="canRuleAuthor && profile.workflow_status === 'draft'" type="button" :disabled="busy" @click="transitionRules('test')">{{ t("Validate") }}</button>
        <button v-if="canRuleAuthor && profile.workflow_status === 'validated'" type="button" :disabled="busy" @click="transitionRules('submit')">{{ t("Submit") }}</button>
        <button v-if="canRuleApprove && profile.workflow_status === 'in_review'" type="button" :disabled="busy" @click="transitionRules('approve')">{{ t("Approve") }}</button>
        <button v-if="canRuleApprove && profile.workflow_status === 'approved'" type="button" :disabled="busy" @click="transitionRules('publish')">{{ t("Publish") }}</button>
        <button v-if="canRuleApprove && profile.workflow_status === 'published'" type="button" :disabled="busy" @click="transitionRules('retire')">{{ t("Retire") }}</button>
      </div>
      <DetailTabs :tabs="[{ id: 'overview', label: t('Overview') }, { id: 'rules', label: t('Rules'), count: profile.rules.length }, { id: 'diff', label: t('Version diff') }, { id: 'workflow', label: t('Workflow') }]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[{ label: t('Change summary'), value: profile.change_summary }, { label: t('Owner'), value: profile.owner }, { label: t('Approver'), value: profile.approved_by }, { label: t('Ruleset checksum'), value: profile.ruleset_checksum, copyable: true }, { label: t('Published'), value: profile.published_at ? new Date(profile.published_at).toLocaleString() : '—' }]" />
      <div v-else-if="activeTab === 'rules'" class="history-stack">
        <DataTable :columns="[{ key: 'id', label: t('Rule') }, { key: 'title', label: t('Title') }, { key: 'condition', label: t('Condition') }, { key: 'severity', label: t('Severity') }, { key: 'evaluator', label: t('Evaluator') }]" :items="profile.rules.map((item) => ({ id: item.rule_id, title: item.title, condition: `${item.condition.operator} ${item.condition.limit ?? '—'} ${item.condition.unit}`, severity: item.severity, evaluator: item.evaluator }))" />
        <details v-if="canRuleAuthor && profile.workflow_status === 'draft'" class="history-mutation-panel"><summary>{{ t("Edit rule draft JSON") }}</summary><p class="history-impact">{{ t("Only drafts can change. Validation recalculates the ruleset checksum; published versions remain immutable.") }}</p><label class="history-json-field"><span>{{ t("Change summary") }}</span><input v-model="changeSummary" /></label><label class="history-json-field"><span>{{ t("Rules (JSON)") }}</span><textarea v-model="ruleJson" rows="24"></textarea></label><button type="button" :disabled="busy" @click="saveRuleDraft">{{ t("Save controlled change") }}</button></details>
      </div>
      <div v-else-if="activeTab === 'diff'" class="history-stack"><label class="history-baseline-select"><span>{{ t("Compare against") }}</span><select :value="against" @change="selectBaseline"><option value="">{{ t("Select version") }}</option><option v-for="item in profiles.filter((item) => item.profile_id !== profile?.profile_id)" :key="item.profile_id" :value="item.profile_id">{{ item.version }} · {{ item.workflow_status }}</option></select></label><DataTable :columns="[{ key: 'rule', label: t('Rule') }, { key: 'change', label: t('Change') }, { key: 'fields', label: t('Changed fields') }]" :items="(diff?.changes || []).map((item) => ({ id: item.rule_id, rule: item.rule_id, change: item.change, fields: item.changed_fields.join(', ') }))" :empty-text="t(against ? 'No rule differences found.' : 'Select a baseline version.')" /></div>
      <div v-else class="history-stack"><PropertyGrid :items="[{ label: t('Workflow status'), value: profile.workflow_status }, { label: t('Submitted by'), value: profile.submitted_by }, { label: t('Reviewed by'), value: profile.reviewed_by }, { label: t('Approved by'), value: profile.approved_by }, { label: t('Published'), value: profile.published_at }, { label: t('Retired'), value: profile.retired_at }]" /><details v-if="canRuleAuthor && ['published', 'retired'].includes(profile.workflow_status)" class="history-mutation-panel"><summary>{{ t("Clone governed version") }}</summary><p class="history-impact">{{ t("Published rule content cannot be edited in place. A clone starts a separate draft version.") }}</p><div class="history-mutation-grid"><label><span>{{ t("New version") }}</span><input v-model="cloneVersion" /></label><label><span>{{ t("Change summary") }}</span><input v-model="changeSummary" /></label></div><button type="button" :disabled="busy || !cloneVersion" @click="cloneRules">{{ t("Create draft version") }}</button></details></div>
    </template>

    <template v-else-if="domain === 'knowledge' && !recordId">
      <DataTable :columns="[{ key: 'title', label: t('Title') }, { key: 'version', label: t('Version') }, { key: 'type', label: t('Document type') }, { key: 'authority', label: t('Authority') }, { key: 'chunks', label: t('Chunks') }, { key: 'status', label: t('Status') }]" :items="documents.map((item) => ({ id: item.document_id, title: item.title, version: item.version_number, type: item.document_type, authority: item.authority_level, chunks: item.chunk_count, status: item.publication_status }))" @select="emit('navigate', `/data/knowledge/${$event.id}`)" />
    </template>

    <template v-else-if="document">
      <RecordHeader :title="document.title" :identifier="document.document_key" :status="document.publication_status" :version="`v${document.version_number} · row ${document.row_version}`" />
      <div v-if="canKnowledgeAuthor || canKnowledgeApprove" class="history-governance-actions"><input v-model="reason" :placeholder="t('Change reason')" /><button v-if="canKnowledgeAuthor && document.publication_status === 'draft'" type="button" @click="transitionDocument('submit')">{{ t("Submit") }}</button><button v-if="canKnowledgeApprove && document.publication_status === 'in_review'" type="button" @click="transitionDocument('approve')">{{ t("Approve") }}</button><button v-if="canKnowledgeApprove && document.publication_status === 'approved'" type="button" @click="transitionDocument('publish')">{{ t("Publish") }}</button><button v-if="canKnowledgeApprove && document.publication_status === 'published'" type="button" @click="transitionDocument('retire')">{{ t("Retire") }}</button></div>
      <DetailTabs :tabs="[{ id: 'overview', label: t('Overview') }, { id: 'chunks', label: t('Chunks'), count: document.chunks.length }, { id: 'versions', label: t('Versions'), count: document.versions.length }, { id: 'citations', label: t('Citations'), count: document.citations.length }, { id: 'governance', label: t('Governance') }]" :active="activeTab" @update:active="setTab" />
      <PropertyGrid v-if="activeTab === 'overview'" :items="[{ label: t('Document type'), value: document.document_type }, { label: t('Authority'), value: document.authority_level }, { label: t('Language'), value: document.language }, { label: 'SHA-256', value: document.sha256, copyable: true }, { label: t('Parser'), value: document.parser_version }, { label: t('Chunker'), value: document.chunker_version }, { label: t('Injection scan'), value: document.injection_scan_status }, { label: t('Indexed'), value: document.indexed_at }]" />
      <div v-else-if="activeTab === 'chunks'" class="history-stack"><article v-for="chunk in document.chunks" :key="chunk.chunk_id" class="history-detail-card"><h3>#{{ chunk.ordinal }} <span class="status-chip">{{ chunk.index_status }}</span></h3><pre class="history-json">{{ chunk.text }}</pre><PropertyGrid :items="[{ label: t('Locator'), value: JSON.stringify(chunk.locator) }, { label: t('Text hash'), value: chunk.text_hash, copyable: true }, { label: t('Embedding model'), value: chunk.embedding_model }]" /></article></div>
      <div v-else-if="activeTab === 'versions'" class="history-stack"><DataTable :columns="[{ key: 'version', label: t('Version') }, { key: 'file', label: t('File') }, { key: 'sha', label: 'SHA-256' }, { key: 'status', label: t('Status') }, { key: 'created', label: t('Created') }]" :items="document.versions.map((item) => ({ id: item.document_id, version: item.version_number, file: item.original_filename, sha: item.sha256, status: item.publication_status, created: new Date(item.created_at).toLocaleString() }))" @select="emit('navigate', `/data/knowledge/${$event.id}?tab=versions`)" /><details v-if="canKnowledgeAuthor" class="history-mutation-panel"><summary>{{ t("Create superseding knowledge version") }}</summary><p class="history-impact">{{ t("The current file and chunks remain immutable. The uploaded file becomes a new version linked by supersedes.") }}</p><div class="history-mutation-grid"><label><span>{{ t("Title") }}</span><input v-model="versionTitle" /></label><label><span>{{ t("TXT or Markdown file") }}</span><input type="file" accept=".txt,.md,text/plain,text/markdown" @change="chooseVersionFile" /></label><label class="form-wide"><span>{{ t("Change reason") }} *</span><input v-model="reason" /></label></div><button type="button" :disabled="busy || !versionFile" @click="createKnowledgeVersion">{{ t("Start version ingestion") }}</button><p v-if="acceptedJobId"><code>{{ acceptedJobId }}</code> · {{ t("Track this ingestion in Jobs & queue.") }}</p></details></div>
      <DataTable v-else-if="activeTab === 'citations'" :columns="[{ key: 'locator', label: t('Locator') }, { key: 'authority', label: t('Authority') }, { key: 'search', label: t('Search') }, { key: 'created', label: t('Created') }]" :items="document.citations.map((item) => ({ id: item.citation_id, locator: item.locator, authority: item.authority, search: item.search_id, created: new Date(item.search_created_at).toLocaleString() }))" :empty-text="t('No citations currently reference this version.')" />
      <div v-else class="history-stack"><PropertyGrid :items="[{ label: t('Owner'), value: document.owner }, { label: t('Classification'), value: document.classification }, { label: t('ACL scopes'), value: document.acl_scopes.join(', ') }, { label: t('Submitted by'), value: document.submitted_by }, { label: t('Reviewed by'), value: document.reviewed_by }, { label: t('Approved by'), value: document.approved_by }, { label: t('Published'), value: document.published_at }, { label: t('Retired'), value: document.retired_at }]" /><button type="button" class="secondary-button" @click="downloadProtectedArtifact(document.download_url, document.original_filename)">{{ t("Download source") }}</button></div>
    </template>
  </section>
</template>
