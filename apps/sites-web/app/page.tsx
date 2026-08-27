'use client';

import { type FormEvent, useMemo, useState } from 'react';
import {
  buildWorkspaceUrl,
  normalizeTunnelUrl,
  TOKEN_KEY,
  TUNNEL_KEY,
  verifyWorkspaceConnection,
  type ConnectionStatus,
} from './remote-connection';
const capabilities = [
  ['CAD ingestion', '上傳、版本化與特徵擷取'], ['Similarity', '可解釋的相似模具搜尋'],
  ['Design review', '規則檢查與人工覆核邊界'], ['Knowledge / RAG', '具來源依據的工程知識查詢'],
  ['Process & CAE', '試模分析、Moldflow 比較與追溯'], ['HMI → Excel', '受控擷取、審查與活頁簿輸出'],
];

export default function Home() {
  const [tunnelInput, setTunnelInput] = useState(() =>
    typeof window === 'undefined' ? '' : (window.sessionStorage.getItem(TUNNEL_KEY) ?? ''),
  );
  const [token, setToken] = useState(() =>
    typeof window === 'undefined' ? '' : (window.sessionStorage.getItem(TOKEN_KEY) ?? ''),
  );
  const [status, setStatus] = useState<ConnectionStatus>('idle');
  const [message, setMessage] = useState('尚未檢查本機 Demo 連線');
  const normalizedUrl = useMemo(() => normalizeTunnelUrl(tunnelInput), [tunnelInput]);
  const canOpen = Boolean(normalizedUrl && token.trim() && status === 'ready');

  async function verifyConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!normalizedUrl || !token.trim()) {
      setStatus('error'); setMessage('請輸入有效的 HTTPS Tunnel URL 與 Demo token。'); return;
    }
    setStatus('checking'); setMessage('正在檢查 HTTPS Tunnel…');
    try {
      await verifyWorkspaceConnection(normalizedUrl, token);
      window.sessionStorage.setItem(TUNNEL_KEY, normalizedUrl);
      window.sessionStorage.setItem(TOKEN_KEY, token.trim());
      setStatus('ready'); setMessage('Tunnel 可連線；可開啟完整工程工作區。');
    } catch {
      setStatus('error'); setMessage('無法連上 Tunnel。請確認 Windows 主機、Docker 與 tunnel 容器仍在執行。');
    }
  }
  function openWorkspace() {
    if (!normalizedUrl || !token.trim()) return;
    window.open(buildWorkspaceUrl(normalizedUrl, token), '_blank', 'noopener,noreferrer');
  }
  function clearSession() {
    window.sessionStorage.removeItem(TUNNEL_KEY); window.sessionStorage.removeItem(TOKEN_KEY);
    setTunnelInput(''); setToken(''); setStatus('idle'); setMessage('此瀏覽器工作階段的連線資料已清除。');
  }

  return <main>
    <nav className="topbar" aria-label="Mold AI remote console">
      <a className="brand" href="#top" aria-label="Mold AI 首頁"><span className="brand-mark">MA</span><span>Mold AI Platform</span></a>
      <span className="private-pill"><span />Owner-only Sites portal</span>
    </nav>
    <section id="top" className="hero">
      <div className="hero-copy">
        <p className="eyebrow">REMOTE DEMO CONSOLE · STAGE 11</p>
        <h1>從外部網路，安全進入你的模具工程工作區。</h1>
        <p className="lede">Sites 負責私人入口；HTTPS Tunnel 連回 Windows 上的完整 Mold AI Web；ChatGPT 的 MCP 連線則使用獨立的 Secure MCP Tunnel。</p>
        <div className="route" aria-label="連線路徑"><span>Private Sites</span><b>→</b><span>HTTPS Tunnel</span><b>→</b><span>Windows + Docker</span></div>
      </div>
      <aside className="boundary-card">
        <p className="eyebrow">SECURITY BOUNDARY</p><h2>兩層私人控制</h2>
        <ol><li><b>Sites 帳號層</b><span>目前僅擁有者可開啟此入口。</span></li><li><b>Demo API 層</b><span>完整工作區仍需強式 Bearer token。</span></li></ol>
        <p className="note">Tunnel URL 與 token 只保存在目前分頁的 sessionStorage。</p>
      </aside>
    </section>
    <section className="connection-grid" aria-labelledby="connect-title">
      <form className="connect-card" onSubmit={verifyConnection}>
        <div className="section-heading"><div><p className="eyebrow">STEP 01</p><h2 id="connect-title">連接本機 Demo</h2></div><span className={`status status-${status}`}>{status === 'ready' ? 'READY' : status.toUpperCase()}</span></div>
        <label><span>HTTPS Quick Tunnel URL</span><input type="url" inputMode="url" autoComplete="url" placeholder="https://example.trycloudflare.com" value={tunnelInput} onChange={(event) => { setTunnelInput(event.target.value); setStatus('idle'); }} required /></label>
        <label><span>Demo access token</span><input type="password" autoComplete="current-password" placeholder="由 scripts/sites-demo-start.ps1 顯示" value={token} onChange={(event) => { setToken(event.target.value); setStatus('idle'); }} required /></label>
        <div className="button-row"><button className="primary" type="submit" disabled={status === 'checking'}>{status === 'checking' ? '檢查中…' : '檢查連線'}</button><button className="secondary" type="button" onClick={openWorkspace} disabled={!canOpen}>開啟完整工作區 ↗</button><button className="quiet" type="button" onClick={clearSession}>清除</button></div>
        <p className={`connection-message ${status === 'error' ? 'message-error' : ''}`} aria-live="polite"><span />{message}</p>
      </form>
      <aside className="mcp-card">
        <p className="eyebrow">STEP 02 · CHATGPT APP</p><h2>同時測試 MCP</h2>
        <p>ChatGPT 不共用 Web Tunnel；它透過 OpenAI Secure MCP Tunnel 連至本機 <code>127.0.0.1:8002</code>。</p>
        <div className="mcp-route"><span>ChatGPT</span><b>⇄</b><span>Secure MCP</span><b>⇄</b><span>MCP Gateway</span></div>
        <ul><li>Windows 上的 MCP gateway 保持 loopback-only</li><li>不需要固定 IP，也不開放路由器連入埠</li><li>完成 Tunnel 建立後，在 ChatGPT 設定選擇該 Tunnel</li></ul>
      </aside>
    </section>
    <section className="capability-section" aria-labelledby="capability-title">
      <div className="section-heading"><div><p className="eyebrow">CURRENT DEMO SURFACE</p><h2 id="capability-title">一個入口，沿用所有已完成能力</h2></div></div>
      <div className="capability-grid">{capabilities.map(([title, detail], index) => <article key={title}><span>{String(index + 1).padStart(2, '0')}</span><h3>{title}</h3><p>{detail}</p></article>)}</div>
    </section>
    <footer><p><b>Mold AI Platform</b> · Controlled external demo</p><p>Quick Tunnel 每次重啟會更換網址，僅供私人測試，不是正式上線方案。</p></footer>
  </main>;
}
