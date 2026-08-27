import { serializeDeepLink, type DeepLinkContext } from './deep-link';

export type ConnectionStatus = 'idle' | 'checking' | 'ready' | 'error';

export const TUNNEL_KEY = 'mold-ai.sites.tunnel-url';
export const TOKEN_KEY = 'mold-ai.sites.demo-token';
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

export async function verifyWorkspaceConnection(tunnelUrl: string, token: string): Promise<void> {
  const response = await fetch(`${tunnelUrl}/api/v1/system/info`, {
    method: 'GET',
    headers: { Accept: 'application/json', Authorization: `Bearer ${token.trim()}` },
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`Workspace identity check returned HTTP ${response.status}.`);
  const identity = (await response.json()) as { name?: string; api_version?: string };
  if (identity.name !== 'Mold AI Platform' || identity.api_version !== 'v1') {
    throw new Error('The HTTPS endpoint is not the expected Mold AI Platform API.');
  }
}

export function buildWorkspaceUrl(
  tunnelUrl: string,
  token: string,
  deepLink?: DeepLinkContext,
): string {
  const url = new URL(tunnelUrl);
  url.search = deepLink ? `?${serializeDeepLink(deepLink)}` : '';
  const params = new URLSearchParams({ token: token.trim() });
  url.hash = `mold-ai-bootstrap=${params.toString()}`;
  return url.toString();
}
