// Utilitários compartilhados: servidor estático local, navegador e ffmpeg.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Playwright: procura em ordem (1) no próprio projeto do vídeo, (2) nas dependências do motor
// (instaladas uma vez por tools/setup.mjs em ~/.video-motion/deps ou em VIDEO_MOTION_DEPS),
// (3) em PLAYWRIGHT_FROM (pasta de outro projeto que já o tenha).
export const DEPS = process.env.VIDEO_MOTION_DEPS || path.join(os.homedir(), '.video-motion', 'deps');
function loadPlaywright() {
  const cands = [path.join(ROOT, 'package.json'), path.join(DEPS, 'package.json')];
  if (process.env.PLAYWRIGHT_FROM) cands.push(path.join(process.env.PLAYWRIGHT_FROM, 'package.json'));
  for (const c of cands) {
    try { return createRequire(c)('playwright'); } catch { /* tenta o próximo */ }
  }
  console.error('Playwright nao encontrado. Rode uma vez:  node tools/setup.mjs');
  process.exit(1);
}
export const { chromium } = loadPlaywright();

/** slug da marca do kit (brand/marca.yaml: slug), usado no nome do MP4. */
export function brandSlug() {
  const f = path.join(ROOT, 'brand', 'marca.yaml');
  if (!fs.existsSync(f)) return 'video';
  const m = fs.readFileSync(f, 'utf8').match(/^slug:\s*["']?([a-z0-9-]+)/m);
  return m ? m[1] : 'video';
}

/** Comando do Python 3 desta máquina (python3 no macOS/Linux, python ou py no Windows). */
export const PYTHON = (() => {
  const cands = process.env.PYTHON ? [process.env.PYTHON]
    : process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
  for (const c of cands) {
    try {
      const v = execFileSync(c, ['-c', 'import sys;print(sys.version_info[0])'], { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
      if (v === '3') return c;
    } catch { /* tenta o próximo */ }
  }
  return cands[0];
})();

// ffmpeg: variável FFMPEG, senão o do pacote Python imageio-ffmpeg, senão o ffmpeg do PATH.
export const FFMPEG = process.env.FFMPEG || (() => {
  try {
    return execFileSync(PYTHON, ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'],
      { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch { return 'ffmpeg'; }
})();

/** cues.json do projeto (gerado por tools/make_cues.py a partir do roteiro). */
export function loadCues() {
  const f = path.join(ROOT, 'cues.json');
  if (!fs.existsSync(f)) { console.error('falta cues.json: rode  python tools/make_cues.py'); process.exit(1); }
  return JSON.parse(fs.readFileSync(f, 'utf8'));
}

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.wav': 'audio/wav', '.mp3': 'audio/mpeg' };

export function startServer() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      const f = path.join(ROOT, p === '/' ? 'index.html' : p);
      if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      fs.createReadStream(f).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve({ srv, url: `http://127.0.0.1:${srv.address().port}/index.html` }));
  });
}

export async function openPage(browser, url) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(url);
  await page.evaluate(() => window.__ready);
  return { page, errors };
}

/** Captura rápida via CDP (PNG). */
export async function cdpFor(page) {
  const cdp = await page.context().newCDPSession(page);
  return async () => {
    const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true, captureBeyondViewport: false });
    return Buffer.from(data, 'base64');
  };
}
