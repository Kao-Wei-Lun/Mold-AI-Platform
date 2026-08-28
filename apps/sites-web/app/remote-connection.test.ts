import { describe, expect, it, vi } from 'vitest';
import {
  buildWorkspaceUrl,
  normalizeTunnelUrl,
  verifyWorkspaceConnection,
} from './remote-connection';

const SEARCH_ID = '11111111-1111-4111-8111-111111111111';

describe('remote connection helpers', () => {
  it('accepts only HTTPS Quick Tunnel hosts', () => {
    expect(normalizeTunnelUrl(' https://demo-name.trycloudflare.com/path?q=1 ')).toBe('https://demo-name.trycloudflare.com');
    expect(normalizeTunnelUrl('http://demo-name.trycloudflare.com')).toBeNull();
    expect(normalizeTunnelUrl('https://example.com')).toBeNull();
    expect(normalizeTunnelUrl('https://localhost')).toBeNull();
  });
  it('builds a workspace URL without credentials or fragments', () => {
    const result = buildWorkspaceUrl('https://demo-name.trycloudflare.com');
    expect(result).toBe('https://demo-name.trycloudflare.com/');
    expect(result).not.toContain('#');
  });
  it('preserves safe context in the query without carrying credentials', () => {
    const result = buildWorkspaceUrl('https://demo-name.trycloudflare.com', {
      deep_link_version: '1.0',
      target: 'similarity',
      refs: { search_id: SEARCH_ID },
    });
    expect(result).toContain(`target=similarity&search_id=${SEARCH_ID}`);
    expect(result).not.toContain('#');
  });
  it('verifies the public local-account workspace preflight', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: '1.0',
        environment: 'external-demo',
        auth: { mode: 'local', local_accounts_enabled: true, local_admin_configured: true },
        quick_tunnel: { ready: true },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await verifyWorkspaceConnection('https://demo-name.trycloudflare.com');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://demo-name.trycloudflare.com/api/v1/security/preflight',
      expect.objectContaining({
        headers: { Accept: 'application/json' },
      }),
    );
    vi.unstubAllGlobals();
  });
  it('rejects a workspace before local administrator bootstrap', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: '1.0',
        environment: 'external-demo',
        auth: { mode: 'local', local_accounts_enabled: true, local_admin_configured: false },
        quick_tunnel: { ready: false },
      }),
    }));

    await expect(verifyWorkspaceConnection('https://demo-name.trycloudflare.com')).rejects.toThrow(
      'local administrator bootstrap',
    );
    vi.unstubAllGlobals();
  });
});
