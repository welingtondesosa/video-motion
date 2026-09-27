#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Confere o MP4 final contra o roteiro (cues.json) e o master de audio. Rode depois do assemble.

  python tools/verify.py [--mp4 out/<marca>-x.mp4]

Mede:
  - video: quadros (tem que ser duration*fps), fps, resolucao 1080x1920, duracao
  - audio do MP4 (AAC): loudness integrada (-14 LUFS +-0,5) e true peak (<= -1 dBTP), numero de amostras
  - sincronia do audio: deslocamento do audio do MP4 em relacao ao audio/master.wav (correlacao cruzada)
    somado ao desvio de cada cue medido no master (audio/report.json)
  - sincronia da imagem: para cada evento da linha do tempo (cues.timeline), o quadro em que a imagem
    MAIS muda de repente (salto no numero de pixels que mudam) numa janela de +-6 quadros do cue.
    Tem que ser o quadro do cue ou o seguinte (a mola comeca no cue; o 1o quadro ja mostra movimento).
Grava out/verify.json e sai com codigo 1 se algo falhar.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'audio'))
import synth as S  # noqa: E402

FF = str(S.FFMPEG)


def run(args, **kw):
    return subprocess.run([FF, '-hide_banner', '-nostats', *args], capture_output=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mp4')
    ap.add_argument('--win', type=int, default=6, help='janela de busca da imagem (+- quadros)')
    a = ap.parse_args()
    C = json.loads((ROOT / 'cues.json').read_text(encoding='utf-8'))
    fps, dur = int(C['fps']), float(C['duration'])
    mp4 = Path(a.mp4) if a.mp4 else Path(json.loads((ROOT / 'out' / 'last.json').read_text(encoding='utf-8'))['mp4'])
    res = dict(mp4=str(mp4), checks=[])
    fails = []

    def check(name, ok, value):
        res['checks'].append(dict(name=name, ok=bool(ok), value=value))
        print(f'  [{"ok" if ok else "FALHOU"}] {name}: {value}')
        if not ok:
            fails.append(name)

    print(f'== {mp4.name} ==')
    info = run(['-i', str(mp4)], text=True, encoding='utf-8', errors='replace').stderr
    vs = re.search(r'Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) fps', info)
    au = re.search(r'Audio: (\w+).*?, (\d+) Hz, (\w+)', info)
    cnt = run(['-i', str(mp4), '-map', '0:v:0', '-c', 'copy', '-f', 'null', '-'], text=True, encoding='utf-8', errors='replace').stderr
    frames = int(re.findall(r'frame=\s*(\d+)', cnt)[-1])
    check('quadros', frames == int(round(dur * fps)), f'{frames} (esperado {int(round(dur * fps))})')
    check('fps', vs and abs(float(vs.group(4)) - fps) < 0.01, vs.group(4) if vs else '?')
    check('resolucao', vs and (vs.group(2), vs.group(3)) == ('1080', '1920'), f'{vs.group(2)}x{vs.group(3)}' if vs else '?')
    check('codecs', vs and au and vs.group(1) == 'h264' and au.group(1) == 'aac', f'{vs.group(1) if vs else "?"} + {au.group(1) if au else "?"} {au.group(2) if au else ""} Hz')

    # ---- audio do MP4
    raw = run(['-i', str(mp4), '-map', '0:a:0', '-f', 'f32le', '-ac', '2', '-ar', str(S.SR), '-']).stdout
    x = np.frombuffer(raw, dtype='<f4').reshape(-1, 2).T.astype(float)
    check('amostras de audio', abs(x.shape[1] - dur * S.SR) <= 1024, f'{x.shape[1]} (= {x.shape[1] / S.SR:.4f} s; esperado {int(dur * S.SR)})')
    tmp = ROOT / 'out' / '_verify_audio.wav'
    import soundfile as sf
    sf.write(tmp, x.T, S.SR, subtype='FLOAT')
    _, v = S.ebur128_summary(tmp)
    _, vhp = S.ebur128_summary(tmp, 'highpass=f=200')
    tmp.unlink()
    check('loudness do MP4', abs(v['I'] - S.TARGET_LUFS) <= 0.5, f'{v["I"]:.1f} LUFS (com passa-altas 200 Hz: {vhp["I"]:.1f})')
    check('true peak do MP4', v['TP'] <= -1.0, f'{v["TP"]:.1f} dBTP')
    res['audio'] = dict(lufs=v['I'], true_peak=v['TP'], lufs_hp200=vhp['I'], samples=int(x.shape[1]))

    # deslocamento do audio do MP4 contra o master.wav
    m, _ = sf.read(ROOT / 'audio' / 'master.wav', always_2d=True)
    m = m.T.mean(axis=0)
    y = x.mean(axis=0)[:m.size]
    L = S.nextpow2(2 * m.size)
    xc = np.fft.irfft(np.fft.rfft(y, L) * np.conj(np.fft.rfft(m, L)), L)
    lim = S.SR // 10
    cand = np.concatenate([xc[:lim], xc[-lim:]])
    k = int(np.argmax(cand))
    lag = k if k < lim else k - 2 * lim
    off_ms = 1000 * lag / S.SR
    check('audio do MP4 x master.wav', abs(off_ms) <= 2.0, f'{off_ms:+.2f} ms')
    rep = ROOT / 'audio' / 'report.json'
    audio_rows = []
    if rep.exists():
        R = json.loads(rep.read_text(encoding='utf-8'))
        for c in R['cues']:
            audio_rows.append((c['t'], c['label'], c['dev_ms'] + abs(off_ms)))
        worst = max((r[2] for r in audio_rows), default=0.0)
        check('cues de audio (master + deslocamento do MP4)', worst <= 1000 / fps + 0.01 and R['cues_ok'] == R['cues_total'],
              f'{R["cues_ok"]}/{R["cues_total"]} dentro de 1 quadro, pior {worst:.1f} ms')

    # ---- imagem: salto de mudanca por quadro
    W, H = 270, 480
    rawv = run(['-i', str(mp4), '-map', '0:v:0', '-vf', f'scale={W}:{H},format=gray', '-f', 'rawvideo', '-']).stdout
    fr = np.frombuffer(rawv, dtype=np.uint8).reshape(-1, H, W).astype(np.int16)
    chg = np.zeros(fr.shape[0])
    chg[1:] = (np.abs(np.diff(fr, axis=0)) > 6).reshape(fr.shape[0] - 1, -1).sum(axis=1)
    vis = []
    for ev in C.get('timeline', []):
        cf = int(round(ev['t'] * fps))
        a0, a1 = max(1, cf - a.win), min(len(chg) - 1, cf + a.win)
        # 1o quadro que rompe com os 3 anteriores: > 3x a mediana deles + 50 px e > 10% do pico logo depois do cue
        # (a mola acelera, entao o MAIOR salto vem depois; o que interessa e onde a mudanca COMECA)
        peak_after = chg[cf:min(len(chg), cf + a.win + 1)].max() if cf < len(chg) else 0
        bf = None
        for f in range(a0, a1 + 1):
            base = float(np.median(chg[max(0, f - 3):f])) if f > 0 else 0.0
            if chg[f] > 3 * base + 50 and chg[f] > 0.1 * peak_after:
                bf = f
                break
        if bf is None:
            bf = a1
        d = bf - cf
        vis.append(dict(t=ev['t'], name=ev['name'], cue_frame=cf, visual_frame=bf, delta=d, pixels=int(chg[bf])))
        print(f'     {ev["t"]:7.3f} s  quadro do cue {cf:4d}  imagem muda no quadro {bf:4d} ({d:+d})  '
              f'{int(chg[bf])} px mudaram (mediana dos 3 anteriores: {int(np.median(chg[max(0, bf - 3):bf])) if bf else 0})  {ev["name"]}')
    if vis:
        ok = all(0 <= v_['delta'] <= 1 for v_ in vis)
        check('imagem no quadro do cue', ok, f'{sum(0 <= v_["delta"] <= 1 for v_ in vis)}/{len(vis)} eventos no quadro do cue ou no seguinte')
    for t, lab, dev in audio_rows:
        print(f'     {t:7.3f} s  audio: desvio {dev:.1f} ms  {lab}')
    res['visual'] = vis
    res['audio_cues'] = [dict(t=t, label=l, dev_ms=d) for t, l, d in audio_rows]
    res['ok'] = not fails
    (ROOT / 'out' / 'verify.json').write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('TUDO OK' if not fails else 'FALHOU: ' + ', '.join(fails))
    sys.exit(0 if not fails else 1)


if __name__ == '__main__':
    main()
