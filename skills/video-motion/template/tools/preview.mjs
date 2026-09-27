// Prévia de quadros.
//   node tools/preview.mjs --times 0.5,1,2.3 [--out frames-preview/x] [--sheet] [--cols 4]
//   node tools/preview.mjs --range 2:4.5:0.25 --sheet
// Salva f_0000.png... (quadro limpo, 1080x1920) e, com --sheet, uma folha de contato sheet.png
// (cada quadro reduzido a 1/3, com o tempo e o número do quadro no canto de baixo).
// Tempo >= duração vira o último quadro (duração - 1/fps): em t = duração nenhuma cena aparece.
// Grava errors.txt com erros de JS da página (deve ficar vazio; se não, sai com código 1) e times.txt.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { ROOT, chromium, startServer, openPage, FFMPEG } from './common.mjs';

const args = process.argv.slice(2);
const get = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
let times = [];
if (get('--times')) times = get('--times').split(',').map(Number);
if (get('--range')) { const [a, b, st] = get('--range').split(':').map(Number); for (let t = a; t <= b + 1e-9; t += st) times.push(+t.toFixed(4)); }
if (!times.length) { console.error('use --times ou --range'); process.exit(1); }
const out = path.resolve(ROOT, get('--out', 'frames-preview/last'));
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

const { srv, url } = await startServer();
const browser = await chromium.launch();
const { page, errors } = await openPage(browser, url);
// duração e fps do window.CUES da própria página (funciona com ou sem cues.json)
const CUES = await page.evaluate(() => ({ duration: window.CUES.duration, fps: window.CUES.fps || 60 }));
const last = +(CUES.duration - 1 / CUES.fps).toFixed(4);
times = [...new Set(times.map((t) => (t >= CUES.duration - 1e-9 ? last : t)))];
const cols = Number(get('--cols', Math.min(times.length, 5)));
const rows = [];
for (let i = 0; i < times.length; i++) {
  await page.evaluate((tt) => window.__render(tt), times[i]);
  const f = path.join(out, `f_${String(i).padStart(4, '0')}.png`);
  await page.screenshot({ path: f });
  rows.push(`${path.basename(f)}\t${times[i]}`);
}
fs.writeFileSync(path.join(out, 'times.txt'), rows.join('\n') + '\n');
fs.writeFileSync(path.join(out, 'errors.txt'), errors.join('\n'));
await browser.close();
srv.close();

if (args.includes('--sheet')) {
  // miniatura de cada quadro com rótulo (tempo e número do quadro), depois a grade
  const th = path.join(out, 'thumbs');
  fs.mkdirSync(th, { recursive: true });
  const font = ['C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf'].find((f) => fs.existsSync(f));
  times.forEach((t, k) => {
    const label = `${t.toFixed(3)} s  q${Math.round(t * CUES.fps)}`;
    const dt = `drawtext=${font ? `fontfile='${font.replace(':', '\\:')}':` : ''}text='${label}':x=8:y=h-th-12:fontsize=26:`
      + 'fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=6';
    execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-i', path.join(out, `f_${String(k).padStart(4, '0')}.png`),
      '-vf', `scale=360:640,${dt}`, path.join(th, `t_${String(k).padStart(4, '0')}.png`)]);
  });
  const nrows = Math.ceil(times.length / cols);
  execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-framerate', '1', '-i', path.join(th, 't_%04d.png'),
    '-vf', `tile=${cols}x${nrows}:padding=6:color=0x333333`, '-frames:v', '1', path.join(out, 'sheet.png')]);
  fs.rmSync(th, { recursive: true, force: true });
  console.log('sheet:', path.join(out, 'sheet.png'));
}
console.log(`ok ${times.length} quadros em ${out}${errors.length ? `  ERROS JS: ${errors.length} (ver errors.txt)` : ''}`);
console.log('tempos:', times.join(', '));
if (errors.length) process.exit(1);
