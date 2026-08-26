export type ConnectionStatus = 'idle' | 'checking' | 'ready' | 'error';

export function normalizeTunnelUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    if (!url.hostname.endsWith('.trycloudflare.com') && url.hostname !== 'localhost') return null;
    url.pathname = ''; url.search = ''; url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch { return null; }
}

export function buildWorkspaceUrl(tunnelUrl: string, token: string): string {
  const url = new URL(tunnelUrl);
  const params = new URLSearchParams({ token: token.trim() });
  url.hash = `mold-ai-bootstrap=${params.toString()}`;
  return url.toString();
}
