#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trilha + efeitos do video, sintetizados com audio/synth.py a partir de ../cues.json.
EXEMPLO do roteiro de demonstracao (palavra entrando + logo). Copie para make_audio.py e adapte:
cada evento visual que merece som vira um mx.hit(...) no MESMO tempo do cue.

Uso:  python audio/make_audio.py           (master + relatorio + conferencia)
      python audio/make_audio.py --quick   (so mix + conferencia interna, sem ffmpeg)

Saidas em audio/: master.wav (-14 LUFS, TP <= -1 dBTP, duracao exata), mix.wav, loudness.txt,
report.json, spectrogram.png, waveform.png, build/ (stems e imagens com os cues marcados).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth as S  # noqa: E402

C = S.load_cues()
G = S.grid(C)                 # None se o roteiro nao tiver bpm
EV = C['events']
DUR = C['duration']

# Niveis (dB): a mixagem inteira se ajusta aqui.
LV = {'music': -2.0, 'pop': -6.0, 'whoosh': -14.0, 'riser': -19.0, 'logo': 0.0}


def score(mx):
    logo_t = EV.get('logo_in')

    # 1) Musica: groove pronto na grade (bumbo, palmas, chimbais, baixo, plucks, pad). Sem bumbo onde o logo bate.
    if G:
        S.groove(mx, G, 0.0, DUR, chords=('C', 'F'), level=LV['music'], kick_skip=[logo_t] if logo_t else ())

    # 2) Cada palavra: whoosh curto que CHEGA nela + pop no quadro exato em que ela entra.
    for i, w in enumerate(C['words']):
        t = w['at']
        d = 0.22
        if t - d > 0:
            mx.add('sfx', S.whoosh(d - 0.02, 900, 4200, f'w{i}', peak_at=0.9, a_pow=1.6, d_pow=0.6), t - d, LV['whoosh'], 0.0)
        mx.hit('sfx', S.pop(S.nf('G5'), f'pop{i}', tau=0.05, glide=0.6), t, f'words[{i}] {w["text"]} (pop)', (500, 3000),
               gain_db=LV['pop'], send={'room': 0.15}, duck=(4.0, 0.01, 0.06, 0.15))

    # 3) Logo: riser que termina 60 ms antes (respiro) + impacto brilhante com camada 100-250 Hz.
    if logo_t:
        r0 = max(0.0, logo_t - 1.0)
        mx.add('trans', S.riser(logo_t - 0.06 - r0, 'riser'), r0, LV['riser'], 0.0, {'hall': 0.15})
        S.logo_hit(mx, logo_t, 'logo', big=True, gain_db=LV['logo'])
        mx.duck.append((logo_t - 0.08, 9.0, 0.12, 0.07, 0.01))   # pre-drop: a musica cai logo antes da pancada
        mx.duck.append((logo_t, 6.0, 0.01, 0.4, 0.6))
        mx.add('music', S.stab(S.MAJOR_CHORD, 1.6, 'logostab', tau_a=0.7), logo_t, -12.0, 0.0, {'hall': 0.3})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    mx = S.Mixer(DUR)
    score(mx)
    total, stems = S.mixdown(mx, fade_out=(DUR - 0.5, DUR))
    res = S.finish(mx, total, stems, C, quick=a.quick)
    if not a.quick and not res['ok']:
        sys.exit(1)


if __name__ == '__main__':
    main()
