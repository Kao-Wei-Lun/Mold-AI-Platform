// Real Chromium layout regression. Run from the repository root; no API or account required.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const chrome = process.env.LAYOUT_CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
if (!existsSync(chrome)) throw new Error('Set LAYOUT_CHROME_PATH to an installed Chromium executable');
const evidence = path.join(root, '.runtime', 'similarity-layout', new Date().toISOString().replaceAll(':', '-'));
mkdirSync(evidence, { recursive: true });
const port = 5199;
const vite = spawn(process.execPath, [path.join(root, 'apps/web/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: path.join(root, 'apps/web'), windowsHide: true, stdio: 'ignore' });
try {
  let ready = false;
  for (let i=0; i<60; i++) {
    if (vite.exitCode !== null) throw new Error('Isolated Vite server failed to start (port may be in use)');
    try { ready = (await fetch(`http://127.0.0.1:${port}/tests/layout/similarity.html`)).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  if (!ready) throw new Error('Layout server readiness timeout');
  const results = [];
  for (const width of [1600, 1200, 900, 500]) for (const locale of ['en', 'zh-TW']) for (const mode of ['normalized_shape', 'engineering_size']) {
    const name = `${width}-${locale}-${mode}`;
    const run = spawnSync(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-extensions', `--user-data-dir=${path.join(evidence,'chrome-profile')}`, `--window-size=${width},1000`, '--force-device-scale-factor=1', '--virtual-time-budget=5000', '--dump-dom', `--screenshot=${path.join(evidence,name+'.png')}`, `http://127.0.0.1:${port}/tests/layout/similarity.html?locale=${locale}&mode=${mode}`], { windowsHide:true, encoding:'utf8', timeout:30000, maxBuffer:2*1024*1024 });
    const json = run.stdout?.match(/<pre id="layout-results">([^<]+)<\/pre>/)?.[1];
    if (run.status !== 0 || !json || json === 'pending') throw new Error(`${name}: Chromium did not finish the layout check`);
    const result = JSON.parse(json.replaceAll('&quot;', '"').replaceAll('&amp;', '&'));
    results.push(result);
    writeFileSync(path.join(evidence,'results.json'), JSON.stringify(results,null,2));
    if (result.errors.length) throw new Error(`${name}: ${result.errors.join('; ')}`);
    console.log(`PASS ${name} (${result.rows.length} fields; viewport ${result.width}px)`);
  }
  console.log(`Evidence: ${evidence}`);
} finally {
  vite.kill();
}
