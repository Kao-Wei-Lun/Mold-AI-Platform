import { serializeDeepLink, type DeepLinkContext } from './deep-link';

export type ConnectionStatus = 'idle' | 'checking' | 'ready' | 'error';

export const TUNNEL_KEY = 'mold-ai.sites.tunnel-url';
export const PENDING_DEEP_LINK_KEY = 'mold-ai.sites.pending-deep-link';

export function normalizeTunnelUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    if (!url.hostname.endsWith('.trycloudflare.com')) return null;
    url.pathname = ''; url.search = ''; url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch { return null; }
}

export async function verifyWorkspaceConnection(tunnelUrl: string): Promise<void> {
  const response = await fetch(`${tunnelUrl}/api/v1/security/preflight`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`Workspace preflight returned HTTP ${response.status}.`);
  const preflight = (await response.json()) as {
    schema_version?: string;
    environment?: string;
    auth?: { mode?: string; local_accounts_enabled?: boolean; local_admin_configured?: boolean };
    quick_tunnel?: { ready?: boolean };
  };
  if (
    preflight.schema_version !== '1.0'
    || preflight.environment !== 'external-demo'
    || preflight.auth?.mode !== 'local'
    || !preflight.auth.local_accounts_enabled
  ) {
    throw new Error('The endpoint is not an external Mold AI local-account workspace.');
  }
  if (!preflight.auth.local_admin_configured || !preflight.quick_tunnel?.ready) {
    throw new Error('The workspace still requires local administrator bootstrap or security setup.');
  }
}

export function buildWorkspaceUrl(
  tunnelUrl: string,
  deepLink?: DeepLinkContext,
): string {
  const url = new URL(tunnelUrl);
  url.search = deepLink ? `?${serializeDeepLink(deepLink)}` : '';
  url.hash = '';
  return url.toString();
}
