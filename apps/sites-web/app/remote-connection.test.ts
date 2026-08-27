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
  it('passes the token in a URL fragment rather than a server request', () => {
    const result = buildWorkspaceUrl('https://demo-name.trycloudflare.com', ' secret value ');
    expect(result).toContain('#mold-ai-bootstrap=token=secret+value');
    expect(result.split('#')[0]).not.toContain('secret');
  });
  it('preserves safe context in the query while keeping the token in the fragment', () => {
    const result = buildWorkspaceUrl('https://demo-name.trycloudflare.com', 'secret', {
      deep_link_version: '1.0',
      target: 'similarity',
      refs: { search_id: SEARCH_ID },
    });
    expect(result).toContain(`target=similarity&search_id=${SEARCH_ID}`);
    expect(result).toContain('#mold-ai-bootstrap=token=secret');
    expect(result.split('#')[0]).not.toContain('secret');
  });
  it('verifies the authenticated Mold AI identity', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ name: 'Mold AI Platform', api_version: 'v1' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await verifyWorkspaceConnection('https://demo-name.trycloudflare.com', 'private-token');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://demo-name.trycloudflare.com/api/v1/system/info',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer private-token' }),
      }),
    );
    vi.unstubAllGlobals();
  });
});
