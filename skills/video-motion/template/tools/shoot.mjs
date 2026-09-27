// Fotografa páginas HTML estáticas (quadros-chave de estilo) em 1080x1920.
//   node tools/shoot.mjs styleframes/a/k1.html styleframes/a/k2.html ... [--sheet styleframes/a/sheet.png]
// Cada .html vira um .png ao lado. Com --sheet, monta uma folha com todos lado a lado.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { ROOT, chromium, startServer, FFMPEG } from './common.mjs';

const args = process.argv.slice(2);
const si = args.indexOf('--sheet');
const sheet = si >= 0 ? path.resolve(ROOT, args[si + 1]) : null;
const pages = args.filter((a, i) => a.endsWith('.html') && !(si >= 0 && i === si + 1));
const { srv, url } = await startServer();
const base = url.replace(/index\.html$/, '');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
const outs = [];
for (const p of pages) {
  await page.goto(base + p.replace(/\\/g, '/'));
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(Array.from(document.images).map((im) => (im.decode ? im.decode().catch(() => {}) : 0)));
  });
  const out = path.resolve(ROOT, p.replace(/\.html$/, '.png'));
  await page.screenshot({ path: out });
  outs.push(out);
}
await browser.close();
srv.close();
if (sheet && outs.length) {
  const inputs = outs.flatMap((o) => ['-i', o]);
  const n = outs.length;
  const filt = outs.map((_, i) => `[${i}:v]scale=540:960[s${i}]`).join(';') + ';' + outs.map((_, i) => `[s${i}]`).join('') + `hstack=inputs=${n}`;
  execFileSync(FFMPEG, ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', n > 1 ? filt : '[0:v]scale=540:960', '-frames:v', '1', sheet]);
  console.log('sheet:', sheet);
}
console.log(`ok ${outs.length} quadros${errors.length ? '  ERROS JS: ' + errors.join(' | ') : ''}`);
