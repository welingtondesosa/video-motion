// Instala as dependencias do motor UMA vez por maquina, fora da skill (sobrevive a atualizacoes):
//   ~/.video-motion/deps   (ou a pasta da variavel VIDEO_MOTION_DEPS)
// Node: Playwright + o Chromium dele. Python 3: numpy, soundfile, pyyaml e imageio-ffmpeg (traz o ffmpeg).
//   node tools/setup.mjs
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execSync, execFileSync } from 'node:child_process';

const DEPS = process.env.VIDEO_MOTION_DEPS || path.join(os.homedir(), '.video-motion', 'deps');
fs.mkdirSync(DEPS, { recursive: true });
if (!fs.existsSync(path.join(DEPS, 'package.json'))) fs.writeFileSync(path.join(DEPS, 'package.json'), '{"name":"video-motion-deps","private":true}');
const run = (c, cwd) => { console.log('>', c); execSync(c, { stdio: 'inherit', cwd }); };

run('npm install playwright@1 --no-audit --no-fund', DEPS);
run('npx playwright install chromium', DEPS);

const cands = process.env.PYTHON ? [process.env.PYTHON]
  : process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
const py = cands.find((c) => {
  try { return execFileSync(c, ['-c', 'import sys;print(sys.version_info[0])'], { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() === '3'; }
  catch { return false; }
});
if (!py) { console.error('Python 3 nao encontrado. Instale em https://www.python.org e rode de novo.'); process.exit(1); }
const pkgs = 'numpy soundfile pyyaml imageio-ffmpeg';
try { run(`${py} -m pip install --user ${pkgs}`, DEPS); }
catch { run(`${py} -m pip install ${pkgs}`, DEPS); }   // dentro de um venv o --user falha

console.log('\npronto: dependencias em', DEPS);
if (process.platform === 'linux') console.log('Linux: se o Chromium reclamar de bibliotecas, rode  sudo npx playwright install-deps chromium');
