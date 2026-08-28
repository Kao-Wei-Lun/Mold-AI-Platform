<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";

import {
  assignRole,
  changeAccountState,
  createAccount,
  fetchAccounts,
  fetchIdentityCatalog,
  revokeRole,
  updateAccount,
  type CreateAccountInput,
  type IdentityCatalog,
  type LocalAccount,
} from "../api/identity";
import { useI18n } from "../i18n";

const props = defineProps<{ currentAccount: LocalAccount | null }>();
const { t } = useI18n();

const accounts = ref<LocalAccount[]>([]);
const catalog = ref<IdentityCatalog>({ roles: [], data_scopes: [] });
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const query = ref("");
const statusFilter = ref("all");
const selectedAccountId = ref("");
const createOpen = ref(false);
const actionReason = ref("");
const assignmentRole = ref("");
const assignmentScope = ref("");

const createForm = reactive<CreateAccountInput>({
  username: "",
  email: "",
  display_name: "",
  password: "",
  role_code: "viewer",
  scope_code: "public-demo",
  reason: "",
});
const editForm = reactive({
  display_name: "",
  email: "",
  locale: "zh-TW",
  timezone: "Asia/Taipei",
});

const canManage = computed(() => props.currentAccount?.permissions.includes("identity:manage") || false);
const selectedAccount = computed(
  () => accounts.value.find((account) => account.id === selectedAccountId.value) || null,
);
const selectedIsCurrentAccount = computed(
  () => Boolean(selectedAccount.value && selectedAccount.value.id === props.currentAccount?.id),
);
const filteredAccounts = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return accounts.value.filter((account) => {
    const matchesStatus = statusFilter.value === "all" || account.status === statusFilter.value;
    const matchesQuery =
      !needle ||
      [account.username, account.display_name, account.email, ...account.roles, ...account.data_scopes]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    return matchesStatus && matchesQuery;
  });
});
const summary = computed(() => ({
  total: accounts.value.length,
  active: accounts.value.filter((account) => account.status === "active").length,
  admins: accounts.value.filter((account) => account.roles.includes("platform_admin")).length,
  attention: accounts.value.filter((account) => account.status !== "active").length,
}));

function syncSelectedAccount(account: LocalAccount | null): void {
  if (!account) return;
  editForm.display_name = account.display_name;
  editForm.email = account.email;
  editForm.locale = account.locale;
  editForm.timezone = account.timezone;
}

watch(selectedAccount, syncSelectedAccount, { immediate: true });

function replaceAccount(updated: LocalAccount): void {
  const index = accounts.value.findIndex((account) => account.id === updated.id);
  if (index >= 0) accounts.value[index] = updated;
  else accounts.value.push(updated);
  selectedAccountId.value = updated.id;
}

function roleLabel(code: string): string {
  return catalog.value.roles.find((role) => role.code === code)?.name || code.replaceAll("_", " ");
}

function formatTime(value: string | null): string {
  if (!value) return t("Never");
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

async function loadIdentity(): Promise<void> {
  if (!canManage.value) {
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const [nextAccounts, nextCatalog] = await Promise.all([
      fetchAccounts(),
      fetchIdentityCatalog(),
    ]);
    accounts.value = nextAccounts;
    catalog.value = nextCatalog;
    if (!selectedAccountId.value && nextAccounts.length) selectedAccountId.value = nextAccounts[0].id;
    assignmentRole.value = nextCatalog.roles[0]?.code || "";
    assignmentScope.value = nextCatalog.data_scopes[0]?.code || "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to load identity management.");
  } finally {
    loading.value = false;
  }
}

async function submitCreate(): Promise<void> {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    const created = await createAccount(createForm);
    replaceAccount(created);
    Object.assign(createForm, {
      username: "",
      email: "",
      display_name: "",
      password: "",
      role_code: "viewer",
      scope_code: "public-demo",
      reason: "",
    });
    createOpen.value = false;
    notice.value = t("Account created successfully.");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to create account.");
  } finally {
    busy.value = false;
  }
}

async function saveProfile(): Promise<void> {
  if (!selectedAccount.value) return;
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    const updated = await updateAccount(selectedAccount.value.id, {
      row_version: selectedAccount.value.row_version,
      ...editForm,
    });
    replaceAccount(updated);
    notice.value = t("Account profile updated.");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to update account.");
  } finally {
    busy.value = false;
  }
}

async function performStateAction(
  action: "activate" | "suspend" | "disable" | "revoke-sessions",
): Promise<void> {
  const account = selectedAccount.value;
  if (!account || !actionReason.value.trim()) return;
  const confirmed = window.confirm(
    t("Confirm {action} for {account}?", { action: t(action), account: account.display_name }),
  );
  if (!confirmed) return;
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    const result = await changeAccountState(account.id, action, actionReason.value);
    replaceAccount(result.account);
    actionReason.value = "";
    notice.value = t("Account action completed. {count} sessions revoked.", {
      count: result.revoked_sessions,
    });
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to change account state.");
  } finally {
    busy.value = false;
  }
}

async function submitAssignment(): Promise<void> {
  if (!selectedAccount.value || !assignmentRole.value || !assignmentScope.value || !actionReason.value.trim()) {
    return;
  }
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await assignRole(
      selectedAccount.value.id,
      assignmentRole.value,
      assignmentScope.value,
      actionReason.value,
    );
    actionReason.value = "";
    notice.value = t("Role assigned successfully.");
    await loadIdentity();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to assign role.");
  } finally {
    busy.value = false;
  }
}

async function removeAssignment(assignmentId: string, roleName: string): Promise<void> {
  if (!actionReason.value.trim()) return;
  if (!window.confirm(t("Revoke the {role} assignment?", { role: roleName }))) return;
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await revokeRole(assignmentId, actionReason.value);
    actionReason.value = "";
    notice.value = t("Role revoked successfully.");
    await loadIdentity();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("Unable to revoke role.");
  } finally {
    busy.value = false;
  }
}

watch(
  canManage,
  (allowed, previouslyAllowed) => {
    if (allowed && !previouslyAllowed) void loadIdentity();
    if (!allowed) loading.value = false;
  },
  { immediate: true },
);
</script>

<template>
  <section class="identity-management-workspace" aria-labelledby="identity-management-title">
    <div v-if="!canManage" class="workspace-state error-state" role="alert">
      <strong>{{ t("Identity management access denied") }}</strong>
      <span>{{ t("Your account does not have permission to manage users, roles or sessions.") }}</span>
    </div>
    <div v-else-if="loading" class="workspace-state" role="status">{{ t("Loading accounts and access policy…") }}</div>
    <div v-else-if="error && accounts.length === 0" class="workspace-state error-state" role="alert">
      <strong>{{ t("Identity management unavailable") }}</strong><span>{{ error }}</span>
      <button type="button" @click="loadIdentity">{{ t("Try again") }}</button>
    </div>
    <template v-else>
      <div class="identity-heading">
        <div>
          <p class="eyebrow">{{ t("Local identity governance") }}</p>
          <h2 id="identity-management-title">{{ t("Accounts and access") }}</h2>
          <p>{{ t("Manage individual Demo identities, governed roles, data scopes and active sessions.") }}</p>
        </div>
        <button type="button" @click="createOpen = !createOpen">
          {{ createOpen ? t("Close account form") : t("Create account") }}
        </button>
      </div>

      <div class="identity-summary" :aria-label="t('Account summary')">
        <div><span>{{ t("Total accounts") }}</span><strong>{{ summary.total }}</strong></div>
        <div><span>{{ t("Active") }}</span><strong>{{ summary.active }}</strong></div>
        <div><span>{{ t("Platform admins") }}</span><strong>{{ summary.admins }}</strong></div>
        <div><span>{{ t("Needs attention") }}</span><strong>{{ summary.attention }}</strong></div>
      </div>

      <form v-if="createOpen" class="identity-create-form" @submit.prevent="submitCreate">
        <div class="identity-form-heading">
          <div><strong>{{ t("Create individual account") }}</strong><span>{{ t("A reason and initial governed role are required.") }}</span></div>
          <span class="governance-state">{{ t("Audited action") }}</span>
        </div>
        <label><span>{{ t("Username") }} *</span><input v-model="createForm.username" autocomplete="off" required maxlength="150" /></label>
        <label><span>{{ t("Display name") }}</span><input v-model="createForm.display_name" autocomplete="off" /></label>
        <label><span>{{ t("Email") }}</span><input v-model="createForm.email" type="email" autocomplete="off" /></label>
        <label><span>{{ t("Initial password") }} *</span><input v-model="createForm.password" type="password" autocomplete="new-password" required /></label>
        <label>
          <span>{{ t("Initial role") }} *</span>
          <select v-model="createForm.role_code" required>
            <option v-for="role in catalog.roles" :key="role.code" :value="role.code">{{ role.name }}</option>
          </select>
        </label>
        <label>
          <span>{{ t("Data scope") }} *</span>
          <select v-model="createForm.scope_code" required>
            <option v-for="scope in catalog.data_scopes" :key="scope.code" :value="scope.code">{{ scope.name }}</option>
          </select>
        </label>
        <label class="identity-reason-field"><span>{{ t("Reason") }} *</span><input v-model="createForm.reason" required :placeholder="t('Why is this access required?')" /></label>
        <button type="submit" :disabled="busy" :aria-busy="busy">{{ busy ? t("Creating…") : t("Create governed account") }}</button>
      </form>

      <p v-if="notice" class="identity-notice" role="status">{{ notice }}</p>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>

      <div class="identity-toolbar">
        <label><span>{{ t("Search accounts") }}</span><input v-model="query" type="search" :placeholder="t('Name, username, email, role or scope')" /></label>
        <label>
          <span>{{ t("Status") }}</span>
          <select v-model="statusFilter">
            <option value="all">{{ t("All statuses") }}</option>
            <option value="active">{{ t("active") }}</option>
            <option value="suspended">{{ t("suspended") }}</option>
            <option value="disabled">{{ t("disabled") }}</option>
          </select>
        </label>
        <span>{{ t("{count} accounts shown", { count: filteredAccounts.length }) }}</span>
      </div>

      <div class="identity-layout">
        <div class="identity-table-wrap">
          <table class="identity-table">
            <thead><tr><th>{{ t("Account") }}</th><th>{{ t("Roles and scope") }}</th><th>{{ t("Status") }}</th><th>{{ t("Last sign-in") }}</th></tr></thead>
            <tbody>
              <tr
                v-for="accountItem in filteredAccounts"
                :key="accountItem.id"
                :class="{ selected: selectedAccountId === accountItem.id }"
                tabindex="0"
                @click="selectedAccountId = accountItem.id"
                @keydown.enter="selectedAccountId = accountItem.id"
              >
                <td><strong>{{ accountItem.display_name }}</strong><span>{{ accountItem.username }}<template v-if="accountItem.email"> · {{ accountItem.email }}</template></span></td>
                <td><span>{{ accountItem.roles.map(roleLabel).join(", ") || t("No active role") }}</span><small>{{ accountItem.data_scopes.join(", ") || t("No active scope") }}</small></td>
                <td><span class="account-status" :class="`status-${accountItem.status}`">{{ t(accountItem.status) }}</span></td>
                <td>{{ formatTime(accountItem.last_login_at) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="filteredAccounts.length === 0" class="workspace-state">{{ t("No accounts match these filters.") }}</p>
        </div>

        <aside v-if="selectedAccount" class="identity-detail" aria-labelledby="selected-account-title">
          <div class="identity-detail-heading">
            <div><span>{{ selectedAccount.username }}</span><h3 id="selected-account-title">{{ selectedAccount.display_name }}</h3></div>
            <span class="account-status" :class="`status-${selectedAccount.status}`">{{ t(selectedAccount.status) }}</span>
          </div>

          <form class="identity-profile-form" @submit.prevent="saveProfile">
            <label><span>{{ t("Display name") }}</span><input v-model="editForm.display_name" required /></label>
            <label><span>{{ t("Email") }}</span><input v-model="editForm.email" type="email" /></label>
            <label><span>{{ t("Language") }}</span><select v-model="editForm.locale"><option value="zh-TW">繁體中文</option><option value="en">English</option></select></label>
            <label><span>{{ t("Timezone") }}</span><input v-model="editForm.timezone" required /></label>
            <button type="submit" class="secondary-button" :disabled="busy">{{ t("Save profile") }}</button>
          </form>

          <div class="identity-assignment-section">
            <div><strong>{{ t("Active role assignments") }}</strong><span>{{ t("Every role is limited to an explicit data scope.") }}</span></div>
            <ul>
              <li v-for="assignment in selectedAccount.role_assignments" :key="assignment.id">
                <div><strong>{{ assignment.role_name }}</strong><span>{{ assignment.scope_name }}</span></div>
                <button
                  v-if="!(selectedIsCurrentAccount && assignment.role_code === 'platform_admin')"
                  type="button"
                  class="text-button danger-text"
                  :disabled="busy || !actionReason.trim()"
                  @click="removeAssignment(assignment.id, assignment.role_name)"
                >{{ t("Revoke") }}</button>
              </li>
            </ul>
            <form class="identity-assignment-form" @submit.prevent="submitAssignment">
              <select v-model="assignmentRole" :aria-label="t('Role')"><option v-for="role in catalog.roles" :key="role.code" :value="role.code">{{ role.name }}</option></select>
              <select v-model="assignmentScope" :aria-label="t('Data scope')"><option v-for="scope in catalog.data_scopes" :key="scope.code" :value="scope.code">{{ scope.name }}</option></select>
              <button type="submit" class="secondary-button" :disabled="busy || !actionReason.trim()">{{ t("Assign role") }}</button>
            </form>
          </div>

          <div class="identity-action-section">
            <label><span>{{ t("Reason for role or account action") }} *</span><textarea v-model="actionReason" rows="2" :placeholder="t('Required for audit')"></textarea></label>
            <div class="identity-action-buttons">
              <button v-if="selectedAccount.status !== 'active'" type="button" class="secondary-button" :disabled="busy || !actionReason.trim()" @click="performStateAction('activate')">{{ t("Activate") }}</button>
              <button v-if="selectedAccount.status === 'active' && !selectedIsCurrentAccount" type="button" class="secondary-button" :disabled="busy || !actionReason.trim()" @click="performStateAction('suspend')">{{ t("Suspend") }}</button>
              <button v-if="selectedAccount.status === 'active' && !selectedIsCurrentAccount" type="button" class="danger-button" :disabled="busy || !actionReason.trim()" @click="performStateAction('disable')">{{ t("Disable") }}</button>
              <button type="button" class="secondary-button" :disabled="busy || !actionReason.trim()" @click="performStateAction('revoke-sessions')">{{ t("Revoke sessions") }}</button>
            </div>
          </div>
        </aside>
      </div>
    </template>
  </section>
</template>
