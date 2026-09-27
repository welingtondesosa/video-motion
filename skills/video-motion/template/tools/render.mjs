// Render final: o vídeo inteiro (duração e fps do cues.json) com motion blur real.
// Cada quadro de saída = média de SUB subquadros espalhados em meio intervalo
// (obturador de 180 graus). Os subquadros são gravados a FPS*SUB e o ffmpeg
// faz a média (tmix) e fica com 1 de cada SUB.
// Vários navegadores em paralelo, cada um num pedaço contíguo do tempo.
//   node tools/render.mjs [--workers 6] [--from 0] [--to <duração>] [--sub 4]
// Sai em out/video_master.mkv (H.264 yuv444p crf 8, sem áudio) e confere o nº de quadros.
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { ROOT, chromium, startServer, openPage, cdpFor, FFMPEG, loadCues } from './common.mjs';

const args = process.argv.slice(2);
const get = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const CUES = loadCues();
const FPS = Number(CUES.fps || 60);
const SUB = Number(get('--sub', 4));
const SHUTTER = 0.5; // fração do intervalo do quadro
const WORKERS = Number(get('--workers', 6));
const T0 = Number(get('--from', 0));
const T1 = Number(get('--to', CUES.duration));
const OUT = path.join(ROOT, 'out');
const SEG = path.join(OUT, 'segments');
fs.rmSync(SEG, { recursive: true, force: true });
fs.mkdirSync(SEG, { recursive: true });

const F0 = Math.round(T0 * FPS), F1 = Math.round(T1 * FPS);
const total = F1 - F0;
const per = Math.ceil(total / WORKERS);
const { srv, url } = await startServer();
const started = Date.now();
let done = 0;
let jsErrors = 0;

async function worker(w) {
  const a = F0 + w * per, b = Math.min(F1, a + per);
  if (a >= b) return null;
  const browser = await chromium.launch();
  const { page, errors } = await openPage(browser, url);
  const shot = await cdpFor(page);
  const seg = path.join(SEG, `seg_${String(w).padStart(2, '0')}.mkv`);
  // O Chrome às vezes grava o PNG com alfa (RGBA) em vez de RGB (1 a 3 pixels
  // transparentes na borda de um elemento). Sem proteção, o ffmpeg reinicia o grafo
  // de filtros, o tmix/select/setpts=N recomeçam do zero e quadros somem calados
  // (aconteceu: trecho 13-15 s sumiu e o vídeo saiu com 28 s). Por isso:
  // -reinit_filter 0 (não reinicia) + scale/format na entrada (converte cada
  // quadro, RGB ou RGBA, para gbrp antes do tmix).
  const norm = 'scale=1080:1920,format=gbrp,';
  const vf = SUB > 1
    ? `${norm}tmix=frames=${SUB}:weights='${Array(SUB).fill(1).join(' ')}',select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/(${FPS}*TB)`
    : `${norm}setpts=N/(${FPS}*TB)`;
  const ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-reinit_filter', '0', '-f', 'image2pipe', '-framerate', String(FPS * SUB), '-i', '-',
    '-vf', vf, '-r', String(FPS), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '8', '-pix_fmt', 'yuv444p', seg], { stdio: ['pipe', 'inherit', 'inherit'] });
  const write = (buf) => new Promise((res) => { if (!ff.stdin.write(buf)) ff.stdin.once('drain', res); else res(); });
  for (let f = a; f < b; f++) {
    for (let k = 0; k < SUB; k++) {
      const t = f / FPS + (SUB > 1 ? (k / SUB) * (SHUTTER / FPS) : 0);
      await page.evaluate((tt) => window.__render(tt), t);
      await write(await shot());
    }
    done++;
    if (done % 120 === 0) {
      const el = (Date.now() - started) / 1000;
      console.log(`${done}/${total} quadros  ${el.toFixed(0)}s  eta ${((total - done) * el / done).toFixed(0)}s`);
    }
  }
  ff.stdin.end();
  await new Promise((res) => ff.on('close', res));
  await browser.close();
  if (errors.length) { jsErrors += errors.length; console.log(`worker ${w} ERROS JS:\n${errors.join('\n')}`); }
  return seg;
}

const segs = (await Promise.all(Array.from({ length: WORKERS }, (_, w) => worker(w)))).filter(Boolean);
srv.close();
const list = path.join(SEG, 'list.txt');
fs.writeFileSync(list, segs.map((s) => `file '${s.replace(/\\/g, '/')}'`).join('\n'));
execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', path.join(OUT, 'video_master.mkv')]);
// Conferência: o mestre tem que ter exatamente `total` quadros.
const probe = spawnSync(FFMPEG, ['-hide_banner', '-i', path.join(OUT, 'video_master.mkv'), '-map', '0:v:0', '-c', 'copy', '-f', 'null', '-']).stderr.toString();
const got = Number([...probe.matchAll(/frame=\s*(\d+)/g)].pop()?.[1] ?? -1);
if (got !== total) { console.log(`ERRO: video_master.mkv tem ${got} quadros, esperado ${total}`); process.exitCode = 1; }
if (jsErrors) { console.log(`ERRO: ${jsErrors} erros de JS durante o render`); process.exitCode = 1; }
console.log(`video_master.mkv pronto em ${((Date.now() - started) / 1000).toFixed(0)}s (${got}/${total} quadros, ${FPS} fps, ${SUB} subquadros cada)`);
