import { apiFetch, clearCsrfToken, setCsrfToken } from "./client";

export type LocalAccount = {
  id: string;
  username: string;
  email: string;
  display_name: string;
  status: "active" | "suspended" | "disabled";
  locale: string;
  timezone: string;
  row_version: number;
  roles: string[];
  permissions: string[];
  data_scopes: string[];
  role_assignments: RoleAssignment[];
  last_login_at: string | null;
  created_at: string;
};

export type RoleAssignment = {
  id: string;
  role_code: string;
  role_name: string;
  scope_code: string;
  scope_name: string;
  valid_from: string | null;
  valid_to: string | null;
};

export type CurrentAccountResponse = {
  authenticated: boolean;
  authentication_method: "session" | "bearer_gateway" | "none";
  account: LocalAccount | null;
};

export type AccessRole = {
  code: string;
  name: string;
  description: string;
  permissions: string[];
};

export type DataScope = {
  id: string;
  code: string;
  name: string;
  classification: string;
};

export type IdentityCatalog = {
  roles: AccessRole[];
  data_scopes: DataScope[];
};

export type CreateAccountInput = {
  username: string;
  email: string;
  display_name: string;
  password: string;
  role_code: string;
  scope_code: string;
  reason: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

function errorMessage(payload: unknown, fallback: string): string {
  if (
    payload &&
    typeof payload === "object" &&
    "error" in payload &&
    payload.error &&
    typeof payload.error === "object" &&
    "message" in payload.error &&
    typeof payload.error.message === "string"
  ) {
    return payload.error.message;
  }
  return fallback;
}

export async function refreshCsrfToken(): Promise<void> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/csrf`, {
    headers: { Accept: "application/json" },
  });
  const payload = (await response.json()) as { csrf_token?: string };
  if (!response.ok || !payload.csrf_token) {
    throw new Error("Unable to establish a secure sign-in request.");
  }
  setCsrfToken(payload.csrf_token);
}

export async function fetchCurrentAccount(): Promise<CurrentAccountResponse> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/me`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Account status returned HTTP ${response.status}`);
  return (await response.json()) as CurrentAccountResponse;
}

export async function loginLocalAccount(
  username: string,
  password: string,
): Promise<LocalAccount> {
  await refreshCsrfToken();
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const payload = (await response.json()) as Partial<CurrentAccountResponse> & Record<string, unknown>;
  if (!response.ok || !payload.account) {
    throw new Error(errorMessage(payload, "Local account sign-in failed."));
  }
  await refreshCsrfToken();
  return payload.account;
}

export async function logoutLocalAccount(): Promise<void> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/logout`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  clearCsrfToken();
  if (!response.ok && response.status !== 204) {
    throw new Error(`Sign out returned HTTP ${response.status}`);
  }
}

async function identityRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await apiFetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(errorMessage(payload, `Identity request returned HTTP ${response.status}`));
  }
  return payload as T;
}

export async function fetchAccounts(): Promise<LocalAccount[]> {
  const payload = await identityRequest<{ results: LocalAccount[] }>("/api/v1/admin/users");
  return payload.results;
}

export function fetchIdentityCatalog(): Promise<IdentityCatalog> {
  return identityRequest<IdentityCatalog>("/api/v1/admin/identity-catalog");
}

export function createAccount(input: CreateAccountInput): Promise<LocalAccount> {
  return identityRequest<LocalAccount>("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateAccount(
  accountId: string,
  input: Pick<LocalAccount, "row_version" | "display_name" | "email" | "locale" | "timezone">,
): Promise<LocalAccount> {
  return identityRequest<LocalAccount>(`/api/v1/admin/users/${accountId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function changeAccountState(
  accountId: string,
  action: "activate" | "suspend" | "disable" | "revoke-sessions",
  reason: string,
): Promise<{ account: LocalAccount; revoked_sessions: number }> {
  return identityRequest(`/api/v1/admin/users/${accountId}/${action}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function assignRole(
  accountId: string,
  roleCode: string,
  scopeCode: string,
  reason: string,
): Promise<{ id: string }> {
  return identityRequest("/api/v1/admin/role-assignments", {
    method: "POST",
    body: JSON.stringify({
      account_id: accountId,
      role_code: roleCode,
      scope_code: scopeCode,
      reason,
    }),
  });
}

export function revokeRole(assignmentId: string, reason: string): Promise<null> {
  return identityRequest(`/api/v1/admin/role-assignments/${assignmentId}`, {
    method: "DELETE",
    body: JSON.stringify({ reason }),
  });
}
