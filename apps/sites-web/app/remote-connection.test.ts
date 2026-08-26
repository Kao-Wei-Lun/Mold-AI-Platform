import { describe, expect, it } from 'vitest';
import { buildWorkspaceUrl, normalizeTunnelUrl } from './remote-connection';

describe('remote connection helpers', () => {
  it('accepts only HTTPS Quick Tunnel hosts', () => {
    expect(normalizeTunnelUrl(' https://demo-name.trycloudflare.com/path?q=1 ')).toBe('https://demo-name.trycloudflare.com');
    expect(normalizeTunnelUrl('http://demo-name.trycloudflare.com')).toBeNull();
    expect(normalizeTunnelUrl('https://example.com')).toBeNull();
  });
  it('passes the token in a URL fragment rather than a server request', () => {
    const result = buildWorkspaceUrl('https://demo-name.trycloudflare.com', ' secret value ');
    expect(result).toContain('#mold-ai-bootstrap=token=secret+value');
    expect(result.split('#')[0]).not.toContain('secret');
  });
});
