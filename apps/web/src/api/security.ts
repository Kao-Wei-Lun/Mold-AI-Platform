import { apiFetch, clearDemoAccessToken, setDemoAccessToken } from "./client";

export type SecurityPreflight = {
  schema_version: "1.0";
  environment: string;
  auth: {
    mode: "disabled" | "required" | "local";
    required: boolean;
    token_configured: boolean;
    local_accounts_enabled?: boolean;
    local_admin_configured?: boolean;
    methods?: string[];
    scopes: string[];
  };
  request_security: { is_secure: boolean; trusted_proxy_headers: boolean };
  mcp: {
    public_https_configured: boolean;
    secure_tunnel_configured: boolean;
    recommended_demo_path: string;
    oauth_implemented: false;
  };
  checks: Record<string, boolean>;
  external_mode: boolean;
  production_ready: boolean;
  limitations: string[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export async function fetchSecurityPreflight(): Promise<SecurityPreflight> {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/security/preflight`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Security preflight returned HTTP ${response.status}`);
  const payload = (await response.json()) as Partial<SecurityPreflight>;
  if (!payload.auth || typeof payload.auth.required !== "boolean") {
    throw new Error("Security preflight returned an invalid contract.");
  }
  return payload as SecurityPreflight;
}

export async function connectDemoAccess(token: string): Promise<void> {
  setDemoAccessToken(token);
  const response = await apiFetch(`${apiBaseUrl}/api/v1/system/info`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    clearDemoAccessToken();
    throw new Error(response.status === 401 ? "Demo access token was rejected." : `HTTP ${response.status}`);
  }
}

export { clearDemoAccessToken };
