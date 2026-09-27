// Monta o MP4 final (vídeo mestre + áudio já masterizado) e a capa em PNG.
// Mira: H.264 high, fps do roteiro, yuv420p, AAC 192k, faststart, até 30 MB.
//   node tools/assemble.mjs [--cover 29.4] [--out nome.mp4]
// Nome padrão: out/<slug da marca>-<name>.mp4 e -capa.png (slug em brand/marca.yaml, name no roteiro).
// Depois rode  python tools/verify.py  (quadros, fps, loudness do MP4 e sincronia).
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { ROOT, FFMPEG, loadCues, brandSlug } from './common.mjs';
const MARCA = brandSlug();

const args = process.argv.slice(2);
const get = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const CUES = loadCues();
const FPS = Number(CUES.fps || 60);
const DUR = Number(CUES.duration);
const OUT = path.join(ROOT, 'out');
const video = path.join(OUT, 'video_master.mkv');
const audio = path.join(ROOT, 'audio', 'master.wav');
const slug = String(CUES.name || 'video').toLowerCase().replace(/[^a-z0-9-]+/g, '-');
const mp4 = path.join(OUT, get('--out', `${MARCA}-${slug}.mp4`));
const cover = mp4.replace(/\.mp4$/, '-capa.png');
const coverAt = String(get('--cover', CUES.cover != null ? CUES.cover : Math.max(0, DUR - 0.3)));
for (const f of [video, audio]) if (!fs.existsSync(f)) { console.error('falta', f); process.exit(1); }

const encode = (crf, maxrate) => execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-i', video, '-i', audio,
  '-map', '0:v:0', '-map', '1:a:0',
  '-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high', '-level', '4.2', '-crf', String(crf),
  '-maxrate', maxrate, '-bufsize', '16M', '-pix_fmt', 'yuv420p', '-r', String(FPS),
  '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
  '-t', String(DUR), '-movflags', '+faststart', mp4]);

let crf = 17;
encode(crf, '7M');
let size = fs.statSync(mp4).size / 1024 / 1024;
while (size > 29.5 && crf < 26) { crf += 2; encode(crf, '6M'); size = fs.statSync(mp4).size / 1024 / 1024; }
execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-ss', coverAt, '-i', video, '-frames:v', '1', cover]);
fs.writeFileSync(path.join(OUT, 'last.json'), JSON.stringify({ mp4, cover, crf, mb: +size.toFixed(2) }, null, 2));
console.log(`MP4: ${mp4} (${size.toFixed(1)} MB, crf ${crf})`);
console.log(`Capa: ${cover} (quadro de ${coverAt} s)`);
