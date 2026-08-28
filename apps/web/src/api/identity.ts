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
  last_login_at: string | null;
  created_at: string;
};

export type CurrentAccountResponse = {
  authenticated: boolean;
  authentication_method: "session" | "bearer_gateway" | "none";
  account: LocalAccount | null;
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
