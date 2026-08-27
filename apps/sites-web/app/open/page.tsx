'use client';

import { type FormEvent, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import { DeepLinkError, deepLinkTitle, parseDeepLink, serializeDeepLink } from '../deep-link';
import {
  buildWorkspaceUrl,
  normalizeTunnelUrl,
  PENDING_DEEP_LINK_KEY,
  TOKEN_KEY,
  TUNNEL_KEY,
  verifyWorkspaceConnection,
  type ConnectionStatus,
} from '../remote-connection';

export default function OpenDeepLink() {
  const parsed = useMemo(() => {
    if (typeof window === 'undefined') return null;
    try {
      return { context: parseDeepLink(window.location.search), error: null };
    } catch (caught) {
      const error = caught instanceof DeepLinkError ? caught : new DeepLinkError(
        'DEEP_LINK_REF_INVALID',
        'This Mold AI link could not be parsed.',
      );
      return { context: null, error };
    }
  }, []);
  const context = parsed?.context ?? null;
  const linkError = parsed?.error ?? null;
  const [tunnelInput, setTunnelInput] = useState(() =>
    typeof window === 'undefined' ? '' : (window.sessionStorage.getItem(TUNNEL_KEY) ?? ''),
  );
  const [token, setToken] = useState(() =>
    typeof window === 'undefined' ? '' : (window.sessionStorage.getItem(TOKEN_KEY) ?? ''),
  );
  const [status, setStatus] = useState<ConnectionStatus>('idle');
  const [message, setMessage] = useState('先驗證目前的 Windows Demo 連線，再開啟指定內容。');
  const normalizedUrl = useMemo(() => normalizeTunnelUrl(tunnelInput), [tunnelInput]);

  useEffect(() => {
    if (context) window.sessionStorage.setItem(PENDING_DEEP_LINK_KEY, serializeDeepLink(context));
  }, [context]);

  async function verifyConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!normalizedUrl || !token.trim()) {
      setStatus('error');
      setMessage('請輸入有效的 HTTPS Quick Tunnel URL 與 Demo token。');
      return;
    }
    setStatus('checking');
    setMessage('正在確認 Mold AI Platform 身分與存取權…');
    try {
      await verifyWorkspaceConnection(normalizedUrl, token);
      window.sessionStorage.setItem(TUNNEL_KEY, normalizedUrl);
      window.sessionStorage.setItem(TOKEN_KEY, token.trim());
      setStatus('ready');
      setMessage('連線身分已確認，可以安全開啟指定工程內容。');
    } catch {
      setStatus('error');
      setMessage('連線驗證失敗。請重新執行 Demo 啟動腳本並確認 Tunnel URL 與 token。');
    }
  }

  function openWorkspace() {
    if (!context || !normalizedUrl || !token.trim() || status !== 'ready') return;
    window.sessionStorage.removeItem(PENDING_DEEP_LINK_KEY);
    window.location.assign(buildWorkspaceUrl(normalizedUrl, token, context));
  }

  if (linkError) {
    return <main className="dispatcher-shell">
      <section className="dispatcher-card error-card" role="alert">
        <p className="eyebrow">{linkError.code}</p>
        <h1>無法開啟這個 Mold AI 連結</h1>
        <p>{linkError.message}</p>
        <Link className="text-link" href="/">返回私人 Demo 入口</Link>
      </section>
    </main>;
  }

  if (!context) return null;

  return <main className="dispatcher-shell">
    <nav className="topbar" aria-label="Mold AI deep link">
      <Link className="brand" href="/"><span className="brand-mark">MA</span><span>Mold AI Platform</span></Link>
      <span className="private-pill"><span />Validated deep link 1.0</span>
    </nav>
    <section className="dispatcher-card">
      <div>
        <p className="eyebrow">OPEN ENGINEERING CONTEXT</p>
        <h1>{deepLinkTitle(context.target)}</h1>
        <p className="lede">此入口只攜帶識別碼。內容、權限與最新狀態會由 Engineering Web 重新向 API 讀取。</p>
        <dl className="context-list">
          <div><dt>Target</dt><dd>{context.target}</dd></div>
          {Object.entries(context.refs).map(([key, value]) => <div key={key}><dt>{key}</dt><dd><code>{value}</code></dd></div>)}
        </dl>
      </div>
      <form className="connect-card" onSubmit={verifyConnection}>
        <div className="section-heading"><div><p className="eyebrow">CONNECTION</p><h2>確認目前 Workspace</h2></div><span className={`status status-${status}`}>{status === 'ready' ? 'READY' : status.toUpperCase()}</span></div>
        <label><span>HTTPS Quick Tunnel URL</span><input type="url" value={tunnelInput} onChange={(event) => { setTunnelInput(event.target.value); setStatus('idle'); }} placeholder="https://example.trycloudflare.com" required /></label>
        <label><span>Demo access token</span><input type="password" value={token} onChange={(event) => { setToken(event.target.value); setStatus('idle'); }} autoComplete="current-password" required /></label>
        <div className="button-row"><button className="primary" type="submit" disabled={status === 'checking'}>{status === 'checking' ? '驗證中…' : '驗證連線'}</button><button className="secondary" type="button" onClick={openWorkspace} disabled={status !== 'ready'}>開啟指定內容 →</button></div>
        <p className={`connection-message ${status === 'error' ? 'message-error' : ''}`} aria-live="polite"><span />{message}</p>
      </form>
    </section>
  </main>;
}
