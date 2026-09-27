#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Biblioteca de sintese de audio para os videos (numpy puro, sem banco de sons).
Motor de audio generico: trilha e efeitos sintetizados sobre a mesma folha de tempos do video.

Fluxo tipico (ver make_audio.example.py):
    import synth as S
    C  = S.load_cues()                  # ../cues.json (gerado por tools/make_cues.py)
    G  = S.grid(C)                      # grade musical (None se o roteiro nao tem bpm)
    mx = S.Mixer(C['duration'])
    mx.hit('sfx', S.pop(1200, 'p1'), 0.5, 'palavra (pop)', (800, 3000), gain_db=-6, send={'room': 0.12})
    mx.add('music', S.kick('k0'), G.beat(0), -4)
    total, stems = S.mixdown(mx, fade_out=(C['duration'] - 0.4, C['duration']))
    S.finish(mx, total, stems, C)       # master -14 LUFS, TP <= -1 dBTP, relatorio, conferencia dos cues

Regras que a biblioteca garante:
  - todo som comeca e termina em zero (edges): nada de estalo
  - tudo deterministico (rng_for(rotulo)): rodar de novo da o mesmo arquivo
  - master: premaster (-14 LUFS, limitador true peak -2 dBTP, 4x) -> ffmpeg loudnorm 2 passadas linear=true
    -> alinhado amostra a amostra -> cortado em duration*48000 amostras exatas, ultimos 5 ms em zero
  - relatorio: ebur128 do master e com passa-altas 200 Hz (alto-falante de celular), loudnorm,
    conferencia de cada cue marcado (filtro casado + ataque de energia), tolerancia 1 quadro (16,7 ms a 60 fps)

Barramentos: qualquer nome. Por padrao o mixdown aplica ducking em 'music', 'music2' e 'amb'
e bombeamento (sidechain do bumbo, mx.pump) em 'music2'. Efeitos vao em 'sfx', 'trans' etc.
Envios de reverb: 'room', 'hall', 'plate', 'dark'; 'delay' = ping-pong de 3 semicolcheias.
"""
import json
import sys
import math
import re
import subprocess
import time
import zlib
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os

import numpy as np
import soundfile as sf

SR = 48000
TAU = 2 * np.pi
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROBE_LEN = 0.06     # molde do filtro casado (primeiros 60 ms de cada som marcado)
PREMASTER_TP = -2.0  # teto de true peak do premaster; o alvo do master e <= -1 dBTP (margem para o AAC)
TARGET_LUFS = -14.0


def _find_ffmpeg():
    if os.environ.get('FFMPEG'):
        return Path(os.environ['FFMPEG'])
    try:
        import imageio_ffmpeg
        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001
        return Path('ffmpeg')


FFMPEG = _find_ffmpeg()


# ---------------------------------------------------------------- cues e grade
def load_cues(path=None):
    return json.loads(Path(path or ROOT / 'cues.json').read_text(encoding='utf-8'))


class Grid:
    """Grade musical (mesma do tools/make_cues.py). beat/eighth/sixteenth/bar -> segundos."""

    def __init__(self, bpm, offset=0.0, beats_per_bar=4):
        self.bpm, self.offset, self.bpb = float(bpm), float(offset), int(beats_per_bar)
        self.beat_s = 60.0 / self.bpm
        self.bar_s = self.bpb * self.beat_s
        self.step = self.beat_s / 4   # semicolcheia

    def beat(self, n):
        return self.offset + n * self.beat_s

    def eighth(self, n):
        return self.offset + n * self.beat_s / 2

    def sixteenth(self, n):
        return self.offset + n * self.step

    def bar(self, n, beat=0.0):
        return self.offset + n * self.bar_s + beat * self.beat_s

    def steps(self, t0, t1):
        """Indices de semicolcheia s com t0 <= sixteenth(s) < t1."""
        a = math.ceil((t0 - self.offset) / self.step - 1e-9)
        b = math.ceil((t1 - self.offset) / self.step - 1e-9)
        return range(a, b)


def grid(cues):
    return Grid(cues['bpm'], cues.get('offset', 0.0), cues.get('beats_per_bar', 4)) if cues.get('bpm') else None


# ---------------------------------------------------------------- utilidades de DSP
def ns(t):
    return int(round(t * SR))


def tv(n):
    return np.arange(n) / SR


def rng_for(label):
    return np.random.default_rng(zlib.crc32(label.encode('utf-8')))


def undb(d):
    return 10.0 ** (d / 20.0)


def todb(x):
    return 20 * np.log10(np.maximum(x, 1e-12))


def nextpow2(n):
    return 1 << int(math.ceil(math.log2(max(2, n))))


def rise(n):
    """Meio cosseno 0 -> 1 em n amostras (comeca exatamente em 0)."""
    if n <= 0:
        return np.zeros(0)
    return 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)


def edges(x, fin=0.0005, fout=0.004):
    """Garante inicio e fim em zero: nada de estalo por truncamento."""
    x = np.array(x, dtype=float, copy=True)
    n = x.shape[-1]
    a, b = min(ns(fin), n // 2), min(ns(fout), n // 2)
    if a > 0:
        x[..., :a] *= rise(a)
    if b > 0:
        x[..., n - b:] *= rise(b)[::-1]
    return x


def peak(x):
    return float(np.max(np.abs(x))) if np.size(x) else 0.0


def npk(x, p=1.0):
    m = peak(x)
    return x * (p / m) if m > 0 else x


def nrms(x, r=1.0):
    m = float(np.sqrt(np.mean(np.square(x))))
    return x * (r / m) if m > 0 else x


def phase(freq, n):
    """Fase acumulada (ciclos) para frequencia escalar ou vetor."""
    if np.isscalar(freq):
        return np.arange(n) * (float(freq) / SR)
    f = np.asarray(freq, float)
    return np.concatenate(([0.0], np.cumsum(f[:-1]))) / SR


def pan_gains(p):
    """Pan de potencia constante; centro = ganho 1 em cada canal."""
    th = (np.clip(np.asarray(p, float), -1, 1) + 1) * np.pi / 4
    return np.sqrt(2) * np.cos(th), np.sqrt(2) * np.sin(th)


def smoothstep(u):
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def stereo(x, pan=0.0):
    x = np.asarray(x, float)
    if x.ndim == 2:
        return x
    gl, gr = pan_gains(pan)
    return np.stack([x * gl, x * gr])


# magnitudes de filtros (fase zero, aplicadas por FFT)
def m_lp(f, fc, order=2):
    return 1.0 / np.sqrt(1.0 + (np.asarray(f) / fc) ** (2 * order))


def m_hp(f, fc, order=2):
    x = (np.asarray(f) / fc) ** (2 * order)
    return np.sqrt(x / (1.0 + x))


def m_band(f, lo, hi, order=2):
    return m_hp(f, lo, order) * m_lp(f, hi, order)


def m_bp(f, fc, q=1.0):
    x = np.maximum(np.asarray(f), 1e-6) / fc
    return (x / q) / np.sqrt((1 - x * x) ** 2 + (x / q) ** 2)


def m_glog(f, fc, sig_oct):
    return np.exp(-0.5 * (np.log2(np.maximum(np.asarray(f), 1e-3) / fc) / sig_oct) ** 2)


def ffilt(x, mag, pad=None):
    """Filtro de fase zero via FFT (x mono ou (c, n))."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    nfft = nextpow2(n + (pad if pad is not None else max(8192, n // 2)))
    X = np.fft.rfft(x, nfft, axis=-1)
    f = np.fft.rfftfreq(nfft, 1 / SR)
    H = mag(f) if callable(mag) else mag
    return np.fft.irfft(X * H, nfft, axis=-1)[..., :n]


def minphase_H(mag, nfft):
    """Resposta de fase minima com a mesma magnitude (cepstro): causal, sem pre-eco."""
    f = np.fft.rfftfreq(nfft, 1 / SR)
    logm = np.log(np.maximum(mag(f), 1e-7))
    cep = np.fft.irfft(logm, nfft)
    w = np.zeros(nfft)
    w[0] = 1.0
    w[1:nfft // 2] = 2.0
    w[nfft // 2] = 1.0
    return np.exp(np.fft.rfft(cep * w, nfft))


def ffilt_mp(x, mag, pad=None):
    """Filtro de fase minima via FFT (transientes: nada de energia antes do ataque)."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    nfft = nextpow2(n + (pad if pad is not None else max(8192, n // 2)))
    return np.fft.irfft(np.fft.rfft(x, nfft, axis=-1) * minphase_H(mag, nfft), nfft, axis=-1)[..., :n]


def fconv(x, h):
    """Convolucao por FFT: x (n,) ou (c,n) com h (m,) ou (c,m)."""
    n = x.shape[-1] + h.shape[-1] - 1
    nfft = nextpow2(n)
    return np.fft.irfft(np.fft.rfft(x, nfft, axis=-1) * np.fft.rfft(h, nfft, axis=-1), nfft, axis=-1)[..., :n]


def shaped_noise(n, shape, r, nfft=1024, hop=None):
    """Ruido com espectro variavel no tempo (STFT com fase aleatoria).
    shape(t[:,None], f[None,:]) -> magnitude; t em segundos a partir do inicio."""
    hop = hop or nfft // 4
    q = nfft // hop
    nfr = (n + nfft) // hop + 2
    tc = (np.arange(nfr) * hop - nfft / 2) / SR
    f = np.fft.rfftfreq(nfft, 1 / SR)
    M = shape(tc[:, None], f[None, :]) * np.ones((nfr, f.size))
    Z = (r.standard_normal(M.shape) + 1j * r.standard_normal(M.shape)) * M
    win = np.hanning(nfft + 1)[:-1]
    fr = np.fft.irfft(Z, nfft, axis=1) * win
    Y = np.zeros((nfr + q, hop))
    F = fr.reshape(nfr, q, hop)
    for j in range(q):
        Y[j:j + nfr] += F[:, j, :]
    return Y.reshape(-1)[nfft:nfft + n]


def burst(n, tau, band, r):
    """Rajada de ruido filtrado com decaimento exponencial (transiente)."""
    t = tv(n)
    return npk(ffilt(r.standard_normal(n), lambda f: m_band(f, band[0], band[1], 2)) * np.exp(-t / tau))


def modal(t, modes):
    """Soma de senoides amortecidas [(freq, tau, amp)] com fase 0 (comeca em zero)."""
    x = np.zeros_like(t)
    for f, tau, a in modes:
        x += a * np.sin(TAU * f * t) * np.exp(-t / tau)
    return x


def wavetable(amps, phases, size=4096):
    x = np.arange(size) / size
    tab = np.zeros(size)
    for k, (a, p) in enumerate(zip(amps, phases), start=1):
        tab += a * np.sin(TAU * k * x + p)
    return tab


def wt_play(tab, freq, n, ph0=0.0):
    ph = (phase(freq, n) + ph0) % 1.0
    idx = ph * tab.size
    i0 = idx.astype(np.int64)
    fr = idx - i0
    return tab[i0 % tab.size] * (1 - fr) + tab[(i0 + 1) % tab.size] * fr


def saw_amps(f0, fc, kmax=48, fmax=15000.0, order=2):
    K = int(max(1, min(kmax, fmax // f0)))
    k = np.arange(1, K + 1)
    return (1.0 / k) / np.sqrt(1 + (k * f0 / fc) ** (2 * order))


NOTE = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}


def nf(name):
    """'C6' -> 1046,50 Hz (A4 = 440 Hz, temperamento igual)."""
    m = re.fullmatch(r'([A-G]#?)(-?\d)', name)
    midi = 12 * (int(m.group(2)) + 1) + NOTE[m.group(1)]
    return 440.0 * 2 ** ((midi - 69) / 12)


# Acordes prontos (DO maior). bass = fundamental grave, pad = voicing, arp = notas do pluck.
CHORDS = {
    'C': dict(bass='C2', pad=('C3', 'G3', 'C4', 'E4', 'G4'), arp=('E5', 'G5', 'C6')),
    'G': dict(bass='G1', pad=('D3', 'G3', 'B3', 'D4', 'G4'), arp=('D5', 'G5', 'B5')),
    'Am': dict(bass='A1', pad=('E3', 'A3', 'C4', 'E4', 'A4'), arp=('C5', 'E5', 'A5')),
    'F': dict(bass='F1', pad=('C3', 'F3', 'A3', 'C4', 'F4'), arp=('C5', 'F5', 'A5')),
    'Em': dict(bass='E2', pad=('E3', 'G3', 'B3', 'E4', 'G4'), arp=('E5', 'G5', 'B5')),
    'Dm': dict(bass='D2', pad=('D3', 'A3', 'D4', 'F4', 'A4'), arp=('D5', 'F5', 'A5')),
}
MAJOR_CHORD = ('C4', 'E4', 'G4', 'C5', 'E5', 'G5')


# ---------------------------------------------------------------- reverbs (IR sintetica)
def make_ir(t60, t60_hi, lp, hp=120.0, pre=0.01, label='ir', length=None):
    r = rng_for(label)
    length = length or min(4.0, 1.15 * t60 + 0.15)
    n = ns(length)

    def shape(tc, f):
        u = np.clip(np.log2(np.maximum(f, 1) / 400) / np.log2(8000 / 400), 0, 1)
        T = t60 * (1 - u) + t60_hi * u
        return np.exp(-6.9078 * np.maximum(tc, 0) / T) * m_lp(f, lp, 2) * m_hp(f, hp, 1)

    ir = np.stack([shaped_noise(n, shape, r), shaped_noise(n, shape, r)])
    ir[:, :ns(0.006)] *= rise(ns(0.006))
    er = np.zeros_like(ir)
    for dt, g in ((0.0071, 0.5), (0.0113, 0.38), (0.0167, 0.3), (0.0229, 0.22), (0.0311, 0.16)):
        er[0, ns(dt)] += g
        er[1, ns(dt * 1.09)] += g
    ir = ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True)) + 0.35 * er
    ir = np.concatenate([np.zeros((2, ns(pre))), ir], axis=1)
    nfft = nextpow2(ir.shape[1])
    S = np.fft.rfft(ir, nfft, axis=1)
    k = max(3, int(20.0 / (SR / nfft)))
    pw = np.stack([np.convolve(np.abs(S[c]) ** 2, np.ones(k) / k, mode='same') for c in range(2)]) + 1e-20
    S *= np.sqrt(pw.mean(axis=0, keepdims=True) / pw)
    fb = np.fft.rfftfreq(nfft, 1 / SR)
    w = np.clip((fb - 200.0) / 100.0, 0, 1)  # graves da reverb em mono
    S = w * S + (1 - w) * S.mean(axis=0, keepdims=True)
    ir = np.fft.irfft(S, nfft, axis=1)[:, :ir.shape[1]]
    return ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))


IR_SPECS = {
    'room': (0.42, 0.22, 6500, 150, 0.004),
    'hall': (1.6, 0.7, 10000, 180, 0.018),
    'plate': (1.0, 0.55, 12000, 250, 0.006),
    'dark': (2.2, 0.5, 3500, 140, 0.008),
}


# ---------------------------------------------------------------- mesa de mixagem
class Mixer:
    """Barramentos estereo do tamanho exato do video. Tudo em segundos."""

    def __init__(self, duration):
        self.duration = float(duration)
        self.n = int(round(self.duration * SR))
        self.bus = {}
        self.sends = {}
        self.duck = []       # (t, profundidade dB, ataque, sustentacao, soltura)
        self.pump = []       # tempos do bumbo (bombeamento de 'music2')
        self.events = []     # cues para a conferencia
        self.probes = {}     # (rotulo, t) -> (molde seco mono, barramento)
        self.edge_max = 0.0  # maior |amostra| nas bordas de um som / pico dele (tem que ser ~0)

    def get(self, name):
        if name not in self.bus:
            self.bus[name] = np.zeros((2, self.n))
        return self.bus[name]

    def add(self, name, x, t, gain_db=0.0, pan=0.0, send=None, probe=None):
        """Soma o som x (mono ou (2,n)) no barramento `name` a partir de t segundos."""
        x = stereo(x, pan) * undb(gain_db)
        if probe:
            self.probes[(probe, round(float(t), 5))] = (x.mean(axis=0)[:ns(PROBE_LEN)].copy(), name)
        pk = peak(x)
        if pk > 0:
            self.edge_max = max(self.edge_max, float(np.max(np.abs(x[:, [0, -1]]))) / pk)
        i0 = ns(t)
        a, b = max(0, i0), min(self.n, i0 + x.shape[1])
        if b <= a:
            return
        seg = x[:, a - i0:b - i0]
        self.get(name)[:, a:b] += seg
        for ir, g in (send or {}).items():
            key = (name, ir)
            if key not in self.sends:
                self.sends[key] = np.zeros(self.n)
            self.sends[key][a:b] += seg.mean(axis=0) * g

    def mark(self, t, label, band, kind='onset', span=None, probe=None, mband=None, bus=None):
        """Evento para a conferencia. kind: onset | tick | tone | range (span=(a,b)).
        probe = rotulo de um som adicionado com probe= (filtro casado); mband = faixa do filtro casado."""
        self.events.append(dict(t=float(t), label=label, band=tuple(band), kind=kind, span=span, probe=probe or label,
                                mband=mband, bus=bus))

    def hit(self, bus, x, t, label, band, gain_db=0.0, pan=0.0, send=None, kind='onset', mband=None, duck=None):
        """add + mark com filtro casado, num passo so. duck=(dB, ataque, sustentacao, soltura) abaixa a musica."""
        self.add(bus, x, t, gain_db, pan, send, probe=label)
        self.mark(t, label, band, kind=kind, probe=label, mband=mband, bus=bus)
        if duck:
            self.duck.append((float(t),) + tuple(duck))


def duck_curve(events, n):
    g = np.zeros(n)
    t = tv(n)
    for (tt, depth, att, hold, rel) in events:
        a, b = max(0, ns(tt - att)), min(n, ns(tt + hold + rel))
        if b <= a:
            continue
        x = t[a:b]
        e = np.where(x < tt, smoothstep((x - (tt - att)) / att), np.where(x < tt + hold, 1.0, 1 - smoothstep((x - tt - hold) / rel)))
        g[a:b] = np.minimum(g[a:b], -depth * e)
    return undb(g)


def pump_curve(times, n, depth_db=3.0, rel=0.18):
    g = np.zeros(n)
    for tt in times:
        a = ns(tt)
        b = min(n, a + ns(rel))
        if a >= n or b <= a:
            continue
        k = np.arange(b - a) / (b - a)
        att = min(ns(0.004), b - a)
        e = np.ones(b - a)
        e[:att] = rise(att)
        e *= (1 - smoothstep(k))
        g[a:b] = np.minimum(g[a:b], -depth_db * e)
    return undb(g)


def mixdown(mx, duck_buses=('music', 'music2', 'amb'), pump_buses=('music2',), pump_db=3.0, bus_gain=None,
            hp_hz=30.0, fade_in=0.003, fade_out=None, silences=(), cuts=None, delay_s=0.375):
    """Reverbs e delay dos envios, ducking/bombeamento, ganhos, cortes secos, passa-altas, silencios e fades.
    fade_out=(inicio, fim) em s; silences=[(a, b)] zera o master nesse trecho (com rampa de 220 ms antes);
    cuts={'bed': t} corta um barramento seco em t (rampa de 8 ms). Devolve (total, stems)."""
    N = mx.n
    irs = {}
    for (bus, name), snd in list(mx.sends.items()):
        if name == 'delay':  # ping-pong com cauda curta, filtrado
            y = np.zeros((2, N))
            snd_f = ffilt(snd, lambda f: m_band(f, 300, 6000, 1))
            for k, (g, ch) in enumerate(((0.45, 1), (0.22, 0), (0.1, 1), (0.045, 0)), start=1):
                d = ns(delay_s * k)
                if d < N:
                    y[ch, d:] += g * snd_f[:N - d]
        else:
            if name not in irs:
                irs[name] = make_ir(*IR_SPECS[name], label='ir_' + name)
            y = fconv(snd, irs[name])[:, :N]
        mx.get(bus)[:] += y
    duck = duck_curve(mx.duck, N)
    pump = pump_curve(mx.pump, N, pump_db)
    for b in duck_buses:
        if b in mx.bus:
            mx.bus[b] *= duck[None, :]
    for b in pump_buses:
        if b in mx.bus:
            mx.bus[b] *= pump[None, :]
    for b, gdb in (bus_gain or {}).items():
        if b in mx.bus:
            mx.bus[b] *= undb(gdb)
    for b, tc in (cuts or {}).items():
        if b in mx.bus:
            c = np.ones(N)
            k = ns(tc)
            c[k:k + ns(0.008)] = rise(ns(0.008))[::-1][:max(0, min(ns(0.008), N - k))]
            c[k + ns(0.008):] = 0.0
            mx.bus[b] *= c[None, :]
    if not mx.bus:
        raise ValueError('nenhum som no mixer')
    total = sum(mx.bus[b] for b in mx.bus)
    if hp_hz:
        total = ffilt_mp(total, lambda f: m_hp(f, hp_hz, 4), pad=SR)
    mx.hp_hz = hp_hz
    gate = np.ones(N)
    if fade_in:
        gate[:ns(fade_in)] = rise(ns(fade_in))
    for a, b in silences:
        fa, fb = max(0, ns(a - 0.22)), ns(a)
        gate[fa:fb] *= rise(fb - fa)[::-1]
        gate[fb:ns(b)] = 0.0
    if fade_out:
        f0, f1 = fade_out
        t = tv(N)
        fa = ns(f0)
        gate[fa:] *= np.clip(1 - (t[fa:] - f0) / (f1 - f0), 0, 1) ** 2.5
    gate[N - ns(0.005):] = 0.0
    mx.silences = list(silences)
    total = total * gate[None, :]
    stems = {b: mx.bus[b] * gate[None, :] for b in mx.bus}
    return total, stems


# ---------------------------------------------------------------- efeitos
def pop(freq, label, tau=0.042, glide=0.62, bright=0.28, click=0.1, attack=0.0007, soft=0.0, tail=0.0, dur=None):
    """Pop de notificacao: senoide com subida rapida de altura (gota), harmonico e clique.
    soft 0..1 escurece (pops macios de IA); tail desliza a altura no fim."""
    r = rng_for(label)
    dur = dur or max(0.12, 6 * tau)
    n = ns(dur)
    t = tv(n)
    f = freq * (1 - (1 - glide) * np.exp(-t / 0.0065))
    if tail:
        f = f * (1 + tail * smoothstep((t - 0.03) / 0.09))
    ph = phase(f, n)
    x = np.sin(TAU * ph) + bright * np.sin(2 * TAU * ph) * np.exp(-t / (0.45 * tau))
    env = np.exp(-t / tau)
    na = max(2, ns(attack))
    env[:na] *= rise(na)
    x = x * env
    if click > 0:
        x = x + click * burst(n, 0.0005, (2500, 12000), r)
    if soft > 0:
        x = ffilt_mp(x, lambda fr: m_lp(fr, 3200 * (1 - soft) + 1100 * soft, 2))
    return edges(npk(x), 0.0002, 0.006)


# alturas e pan por canal (pops de notificacao "fora do tom", como no anuncio)
CHANNEL_POP = {
    'whatsapp': dict(freq=1210.0, glide=0.62, bright=0.25, pan=-0.75),
    'instagram': dict(freq=1415.0, glide=0.55, bright=0.32, pan=0.75),
    'email': dict(freq=1015.0, glide=0.6, bright=0.22, pan=0.0),
}


def channel_pop(label, channel='whatsapp', freq=None, tau=0.042):
    """Pop do canal (e-mail = blip duplo). Devolve (som estereo, pan sugerido ja aplicado)."""
    sp = CHANNEL_POP[channel]
    p = stereo(pop(freq or sp['freq'], label, tau=tau, glide=sp['glide'], bright=sp['bright']), sp['pan'])
    if channel == 'email':
        p2 = pop((freq or sp['freq']) * 1.12, label + 'b', tau=tau * 0.8, glide=sp['glide'], bright=sp['bright'])
        k = ns(0.048)
        out = np.zeros((2, max(p.shape[1], k + p2.size)))
        out[:, :p.shape[1]] += p
        out[:, k:k + p2.size] += 0.7 * p2
        p = out
    return p


def vibration(dur, f0=152.0, rattle=1.0, wood=1.0, hum=1.0, label='vib'):
    """Celular vibrando na madeira: motor (~150 Hz) + batidas do aparelho excitando a madeira + chocalho."""
    r = rng_for(label)
    n = ns(dur + 0.09)
    t = tv(n)
    A = np.ones(n)
    na = ns(0.016)
    A[:na] = rise(na)
    k = ns(dur)
    A[k:] = np.exp(-(t[k:] - dur) / 0.016)
    wob = 1 + 0.011 * np.sin(TAU * 6.3 * t + r.uniform(0, TAU)) + 0.004 * np.sin(TAU * 17.1 * t + r.uniform(0, TAU))
    f = f0 * (0.72 + 0.28 * A) * wob
    ph = phase(f, n)
    s = np.sin(TAU * ph)
    hum_sig = (np.tanh(2.4 * s) / np.tanh(2.4) + 0.3 * np.sin(2 * TAU * ph + 0.7)) * A
    idx = np.nonzero(np.diff(np.floor(ph)) > 0)[0] + 1
    exc = np.zeros(n)
    exc[idx] = r.uniform(0.5, 1.0, idx.size) * A[idx]
    idx2 = np.clip(idx + (0.5 * SR / f[idx] * r.uniform(0.8, 1.2, idx.size)).astype(int), 0, n - 1)
    exc[idx2] += r.uniform(0.15, 0.45, idx.size) * A[idx2]
    ir = modal(tv(ns(0.05)), [(175, 0.022, 1.0), (315, 0.018, 0.8), (540, 0.014, 0.75), (880, 0.011, 0.6),
                              (1330, 0.008, 0.5), (1990, 0.006, 0.42), (2870, 0.0045, 0.33), (4150, 0.0035, 0.25),
                              (6050, 0.0025, 0.15)])
    body = fconv(exc, ir)[:n]
    frac = ph - np.floor(ph)
    nz = ffilt(r.standard_normal(n), lambda fr: m_band(fr, 1400, 5500, 2)) * np.exp(-frac * 7.0) * A
    out = hum * 0.5 * nrms(hum_sig) + wood * 0.8 * nrms(body) + rattle * 0.35 * nrms(nz)
    return edges(npk(out), 0.0003, 0.004)


def whoosh(dur, f0, f1, label, peak_at=0.7, bw=0.8, a_pow=2.0, d_pow=1.5, flutter=0.0, nfft=1024):
    """Whoosh: ruido com banda varrendo de f0 a f1, envelope com pico em peak_at (fracao da duracao).
    Para um whoosh que CHEGA num evento em t: comece em t - dur*peak_at... ou use peak_at alto e termine 60 ms antes."""
    r = rng_for(label)
    n = ns(dur)

    def shape(tc, f):
        u = np.clip(tc / dur, 0, 1)
        return m_glog(f, f0 * (f1 / f0) ** u, bw) * m_hp(f, 70, 2)

    x = shaped_noise(n, shape, r, nfft)
    t = tv(n)
    u = t / dur
    env = np.where(u < peak_at, (u / peak_at) ** a_pow, ((1 - u) / (1 - peak_at)) ** d_pow)
    if flutter:
        env = env * (1 + flutter * np.sin(TAU * 31 * t + r.uniform(0, TAU)))
    return edges(npk(x * env), 0.001, 0.004)


def riser(dur, label, f0=500.0, f1=7000.0, tone=('C4', 'G4'), tone_db=-9.0):
    """Riser que sobe ate o fim (termina no pico): ruido varrendo + tom subindo 1 oitava. Coloque-o terminando
    ~60 ms antes do impacto (respiro: a pancada sobe mais no alto-falante do celular)."""
    rz = whoosh(dur, f0, f1, label, peak_at=0.97, bw=0.9, a_pow=2.2, d_pow=0.3)
    rt = tv(rz.size)
    ton = np.zeros(rz.size)
    for i, nm in enumerate(tone):
        ton += (1.0 if i == 0 else 0.4) * np.sin(TAU * phase(nf(nm) * 2 ** (rt / dur), rz.size))
    ton *= (rt / dur) ** 2.2
    return edges(npk(rz) + undb(tone_db) * npk(ton), 0.01, 0.012)


def reverse_riser(dur, label, notes=('C5', 'E5', 'G5', 'C6')):
    """Riser reverso: cauda de reverb ao contrario (ruido que abre) + acorde de sino invertido."""
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    tau = dur / 4.2

    def shape(tc, f):
        u = np.clip(tc / dur, 0, 1)
        return m_lp(f, 700 * 18 ** u, 2) * m_hp(f, 220, 2)

    nz = nrms(shaped_noise(n, shape, r, 1024)) * np.exp((t - dur) / tau)
    ton = np.zeros(n)
    for nm in notes:
        fr = nf(nm)
        ton += np.sin(TAU * fr * t + r.uniform(0, TAU)) + 0.25 * np.sin(TAU * 2 * fr * t)
    ton = ton * np.exp((t - dur) / (tau * 1.35))
    return edges(npk(0.8 * npk(nz) + 0.4 * npk(ton)), 0.002, 0.008)


def impact(label, f_hi=90.0, f_lo=45.0, tau_p=0.055, tau_a=0.5, dur=1.8,
           mids=((118, 0.16, 1.0), (172, 0.12, 0.8), (236, 0.09, 0.6), (331, 0.06, 0.4)), mid_gain=0.6, trans_gain=0.6, drive=2.2):
    """Impacto grave: corpo 45-60 Hz + camada de 100 a 250 Hz (e o que aparece no alto-falante do celular) + transiente."""
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / tau_p)
    sub = np.sin(TAU * phase(f, n)) * np.exp(-t / tau_a)
    sub[:ns(0.002)] *= rise(ns(0.002))
    sat = np.tanh(drive * (sub + 0.25 * sub ** 2)) / np.tanh(drive)
    thud = npk(ffilt(r.standard_normal(n), lambda fr: m_band(fr, 95, 260, 2)) * np.exp(-t / 0.06))
    mid = npk(modal(t, mids)) + 0.55 * thud
    mid[:ns(0.001)] *= rise(ns(0.001))
    trans = npk(burst(n, 0.0025, (900, 6000), r) + 0.5 * npk(modal(t, [(1150, 0.006, 1.0), (2300, 0.003, 0.5)])))
    x = npk(sat) + mid_gain * npk(mid) + trans_gain * trans
    x = ffilt_mp(x, lambda fr: m_hp(fr, 28, 3))
    return edges(npk(x), 0.0003, 0.03)


def clock_tick(kind='tick', label='tick', pitch=1.0):
    """Tique de relogio: 'tick', 'tock' ou 'clunk' (parada)."""
    r = rng_for(label)
    n = ns(0.05)
    t = tv(n)
    modes = {
        'tick': [(2780, 0.0075, 1.0), (4220, 0.005, 0.55), (6350, 0.0032, 0.35), (1320, 0.004, 0.35)],
        'tock': [(1980, 0.0085, 1.0), (3120, 0.0055, 0.5), (4870, 0.0035, 0.3), (930, 0.005, 0.4)],
        'clunk': [(1450, 0.02, 1.0), (2300, 0.012, 0.6), (650, 0.03, 0.7), (3900, 0.006, 0.3)],
    }[kind]
    j = r.uniform(0.985, 1.015) * pitch
    x = npk(modal(t, [(f * j, tau, a) for f, tau, a in modes])) + 0.45 * burst(n, 0.0006, (2000, 14000), r)
    return edges(npk(x), 0.0001, 0.004)


def ding(freq, label, tau=0.75, dur=None):
    """Ding de acerto: sino claro (fundamental exata + parciais) com leve batimento."""
    r = rng_for(label)
    dur = dur or 6 * tau
    n = ns(dur)
    t = tv(n)
    x = np.zeros(n)
    for ratio, a, tt in ((1.0, 1.0, tau), (2.0, 0.3, tau * 0.5), (3.0, 0.09, tau * 0.28), (4.18, 0.055, tau * 0.16), (5.43, 0.03, tau * 0.1)):
        x += a * np.sin(TAU * freq * ratio * t) * np.exp(-t / tt)
    x += 0.16 * np.sin(TAU * (freq + 1.9) * t) * np.exp(-t / (0.9 * tau))
    x[:ns(0.0012)] *= rise(ns(0.0012))
    x = x + 0.1 * burst(n, 0.0012, (5000, 16000), r)
    return edges(npk(x), 0.0001, 0.05)


def bell(label, notes=('C6', 'E6', 'G6'), tau=0.9, strum=0.012, spread=0.35):
    """Sino (acorde de dings, levemente arpejado e aberto no estereo). Devolve (2, n)."""
    parts = [ding(nf(nm), f'{label}{i}', tau=tau) for i, nm in enumerate(notes)]
    k = ns(strum)
    out = np.zeros((2, max(p.size for p in parts) + k * len(parts)))
    for i, p in enumerate(parts):
        pan = 0.0 if len(parts) == 1 else -spread + 2 * spread * i / (len(parts) - 1)
        out[:, i * k:i * k + p.size] += stereo(p, pan) * undb(-2.0 * i)
    return edges(npk(out), 0.0001, 0.05)


def tinkle(freq, label, tau=0.08):
    n = ns(tau * 6)
    t = tv(n)
    x = np.sin(TAU * freq * t) * np.exp(-t / tau) + 0.22 * np.sin(TAU * 2.01 * freq * t) * np.exp(-t / (0.4 * tau))
    x[:ns(0.0008)] *= rise(ns(0.0008))
    return edges(npk(x), 0.0001, 0.01)


def snap(label):
    """Snap de encaixe (trava)."""
    r = rng_for(label)
    n = ns(0.04)
    t = tv(n)
    x = npk(modal(t, [(2350, 0.0045, 1.0), (3900, 0.0025, 0.5), (760, 0.004, 0.35)])) + 0.7 * burst(n, 0.0006, (2500, 12000), r)
    return edges(npk(x), 0.0001, 0.004)


def blip(freq, label, tau=0.006):
    """Blip curto (contadores, odometro)."""
    r = rng_for(label)
    n = ns(0.035)
    t = tv(n)
    x = np.sin(TAU * freq * t) * np.exp(-t / tau)
    x[:ns(0.0004)] *= rise(ns(0.0004))
    return edges(npk(x + 0.12 * burst(n, 0.0004, (2500, 10000), r)), 0.0001, 0.004)


def check_blip(freq, label, tau=0.03):
    """Blip suave de 'respondida' (check verde): tonal e sem estalo."""
    r = rng_for(label)
    n = ns(0.18)
    t = tv(n)
    x = np.sin(TAU * freq * t) * np.exp(-t / tau) + 0.2 * np.sin(TAU * 2 * freq * t) * np.exp(-t / (0.45 * tau))
    x[:ns(0.0015)] *= rise(ns(0.0015))
    return edges(npk(x + 0.03 * burst(n, 0.0004, (3000, 9000), r)), 0.0001, 0.01)


def soft_click(label):
    """Clique suave de botao."""
    r = rng_for(label)
    n = ns(0.09)
    t = tv(n)
    x = npk(modal(t, [(520, 0.016, 0.8), (1380, 0.007, 0.6), (2650, 0.004, 0.5), (3900, 0.0025, 0.3)])) + 0.3 * burst(n, 0.0009, (1500, 8000), r)
    x[:ns(0.0006)] *= rise(ns(0.0006))
    return edges(npk(ffilt_mp(x, lambda f: m_lp(f, 7000, 2))), 0.0002, 0.006)


def glass_tap(label):
    """Toque no vidro da tela."""
    r = rng_for(label)
    n = ns(0.05)
    t = tv(n)
    x = npk(modal(t, [(1250, 0.006, 1.0), (2550, 0.003, 0.45), (380, 0.008, 0.5)])) + 0.35 * burst(n, 0.0008, (1500, 8000), r)
    return edges(npk(x), 0.0002, 0.005)


def key_tap(label, pitch=1.0):
    """Tecla do teclado do celular."""
    r = rng_for(label)
    n = ns(0.035)
    t = tv(n)
    j = r.uniform(0.93, 1.07) * pitch
    x = 0.8 * burst(n, 0.0011, (2200, 7000), r) + modal(t, [(1780 * j, 0.0035, 0.45), (3350 * j, 0.002, 0.25), (520 * j, 0.005, 0.3)])
    return edges(npk(x), 0.0001, 0.004)


def thump(f_hi, f_lo, tau_p, tau_a, dur, label, drive=2.4, lp=1000.0):
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / tau_p)
    env = np.exp(-t / tau_a)
    env[:ns(0.004)] *= rise(ns(0.004))
    x = np.sin(TAU * phase(f, n)) * env
    nz = npk(ffilt(r.standard_normal(n), lambda fr: m_lp(fr, 220, 2)) * np.exp(-t / 0.03))
    knock = npk(modal(t, [(f_lo * 3.6, 0.028, 1.0), (f_lo * 7.0, 0.018, 0.8), (f_lo * 10.0, 0.012, 0.55)])
                + 0.5 * burst(n, 0.01, (250, 700), r))
    knock[:ns(0.003)] *= rise(ns(0.003))
    x = np.tanh(drive * (x + 0.22 * nz * env + 0.9 * knock)) / np.tanh(drive)
    x = ffilt_mp(x, lambda fr: m_lp(fr, lp, 2) * m_hp(fr, 32, 2))
    return edges(npk(x), 0.001, 0.012)


def heartbeat(bpm, label, strength=1.0):
    """Batida de coracao (tum-tum) para tensao."""
    lub = thump(78, 47, 0.018, 0.075, 0.34, label + 'l')
    dub = thump(96, 58, 0.015, 0.06, 0.3, label + 'd') * 0.72
    gap = 0.30 if bpm < 80 else 0.25
    out = np.zeros(ns(gap) + dub.size)
    out[:lub.size] += lub
    out[ns(gap):ns(gap) + dub.size] += dub
    return out * strength


def crickets(dur, label):
    """Grilos (noite calma). Devolve (2, n)."""
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    out = np.zeros((2, n))
    for pan in (-0.65, 0.15, 0.7):
        fc = r.uniform(4300, 5200)
        env = np.zeros(n)
        tt = r.uniform(0.0, 0.5)
        period = r.uniform(0.7, 1.05)
        while tt < dur:
            for p in range(3):
                k0, kl = ns(tt + p * 0.034), ns(0.014)
                if k0 + kl < n:
                    env[k0:k0 + kl] += np.sin(np.pi * np.arange(kl) / kl) ** 2
            tt += period * r.uniform(0.9, 1.1)
        out += stereo((np.sin(TAU * fc * t) + 0.25 * np.sin(TAU * 2 * fc * t)) * env * r.uniform(0.6, 1.0), pan)
    return out


def air(dur, label):
    """Ar de ambiente (ruido rosa escuro, estereo)."""
    r = rng_for(label)
    n = ns(dur)

    def shape(tc, f):
        return m_lp(f, 1100, 1) * m_hp(f, 90, 2) / np.sqrt(np.maximum(f, 20) / 100)

    x = np.stack([shaped_noise(n, shape, r, 2048), shaped_noise(n, shape, r, 2048)])
    return npk(x * (1 + 0.25 * np.sin(TAU * 0.23 * tv(n) + 1.0)))


# ---------------------------------------------------------------- instrumentos
def kick(label, f_hi=175.0, f_lo=49.0, tau_p=0.03, tau_a=0.23, dur=0.5, click=0.22, drive=1.6):
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / tau_p)
    x = np.sin(TAU * phase(f, n)) * np.exp(-t / tau_a)
    x[:ns(0.001)] *= rise(ns(0.001))
    x = np.tanh(drive * x) / np.tanh(drive)
    x = x + click * (burst(n, 0.0012, (1500, 9000), r) + 0.6 * np.sin(TAU * 3200 * t) * np.exp(-t / 0.0012))
    return edges(npk(x), 0.0001, 0.03)


def clap(label):
    r = rng_for(label)
    n = ns(0.45)
    t = tv(n)
    nz = ffilt(r.standard_normal(n), lambda f: m_bp(f, 1350, 0.9) * m_hp(f, 650, 2))
    env = np.zeros(n)
    for off, a in ((0.0, 0.75), (0.0085, 0.85), (0.017, 0.8), (0.026, 1.0)):
        k = ns(off)
        env[k:] += a * np.exp(-(t[k:] - off) / 0.0055)
    k = ns(0.026)
    env[k:] += 0.45 * np.exp(-(t[k:] - 0.026) / 0.085)
    body = np.sin(TAU * phase(205 * (1 + 0.3 * np.exp(-t / 0.01)), n)) * np.exp(-t / 0.045)
    return edges(npk(npk(nz * env) + 0.3 * body), 0.0002, 0.02)


HAT_FREQS = (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)


def hat(label, open_=False):
    """Chimbal fechado (ou aberto com open_=True)."""
    r = rng_for(label)
    n = ns(0.32 if open_ else 0.09)
    t = tv(n)
    metal = np.zeros(n)
    for f0 in HAT_FREQS:
        f = f0 * 1.7 * r.uniform(0.995, 1.005)
        p0 = r.uniform(0, 1)
        m = 1
        while m * f < 20000:
            metal += np.sin(TAU * m * (f * t + p0)) / m
            m += 2
    metal = ffilt(metal, lambda fr: m_bp(fr, 9500, 0.9) * m_hp(fr, 6500, 2))
    noise = ffilt(r.standard_normal(n), lambda fr: m_hp(fr, 7500, 2))
    env = np.exp(-t / (0.11 if open_ else 0.022))
    env[:ns(0.0004)] *= rise(ns(0.0004))
    return edges(npk((0.55 * nrms(metal) + 0.45 * nrms(noise)) * env), 0.0001, 0.01)


def bass_note(f0, dur, fc0=1500.0, fc1=300.0, tau_f=0.09, sub=0.55, drive=1.5, rel=0.03, attack=0.004):
    n = ns(dur + rel)
    t = tv(n)
    fc = fc1 + (fc0 - fc1) * np.exp(-t / tau_f)
    K = int(min(40, 8000 / f0))
    x = np.zeros(n)
    for k in range(1, K + 1):
        x += (1.0 / k) / np.sqrt(1 + (k * f0 / fc) ** 4) * np.sin(TAU * k * f0 * t)
    x += sub * np.sin(TAU * f0 * t)
    env = np.ones(n)
    env[:ns(attack)] = rise(ns(attack))
    k0 = ns(dur)
    env[k0:] = np.exp(-(t[k0:] - dur) / (rel / 4))
    x = np.tanh(drive * x * env) / np.tanh(drive)
    return edges(x, 0.0002, 0.008)


def pluck(f0, label, dur=0.6, tau0=0.36, bright=1.0, attack=0.0015, detune_c=0.0):
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    f = f0 * 2 ** (detune_c / 1200)
    K = int(min(28, 14000 / f))
    x = np.zeros(n)
    for k in range(1, K + 1):
        tau_k = tau0 / (1 + 0.55 * (k - 1) / bright)
        x += (1.0 / k ** 1.2) * np.sin(TAU * k * f * t + r.uniform(0, TAU)) * np.exp(-t / tau_k)
    x[:ns(attack)] *= rise(ns(attack))
    return edges(x, 0.0001, 0.03)


def pluck_st(f0, label, **kw):
    """Pluck estereo (desafinado +-4 cents)."""
    return np.stack([pluck(f0, label + 'L', detune_c=-4, **kw), pluck(f0, label + 'R', detune_c=4, **kw)])


def pad_chord(names, dur, label, attack=0.25, release=0.5, fc=1500.0, detune=7.0, hp=140.0):
    """Pad de serras desafinadas (tabela de onda), largo no estereo. Devolve (2, n)."""
    r = rng_for(label)
    n = ns(dur + release)
    out = np.zeros((2, n))
    for nm in names:
        f0 = nf(nm)
        for ch, dcs in ((0, (-detune, detune * 0.4)), (1, (-detune * 0.5, detune))):
            for dc in dcs:
                f = f0 * 2 ** (dc / 1200)
                amps = saw_amps(f, fc, kmax=32)
                out[ch] += wt_play(wavetable(amps, r.uniform(0, TAU, amps.size)), f, n, r.uniform())
    env = np.ones(n)
    na = ns(attack)
    env[:na] = rise(na)
    k0 = ns(dur)
    env[k0:] = rise(n - k0)[::-1]
    out = ffilt_mp(out * env, lambda f: m_hp(f, hp, 2))
    return edges(out, 0.0005, 0.01)


def stab(names, dur, label, fc0=6000.0, fc1=900.0, tau_f=0.22, tau_a=0.65, detune=9.0):
    """Acorde cheio com filtro abrindo e fechando (impactos musicais). Devolve (2, n)."""
    r = rng_for(label)
    n = ns(dur)
    t = tv(n)
    fc = fc1 + (fc0 - fc1) * np.exp(-t / tau_f)
    out = np.zeros((2, n))
    for nm in names:
        f0 = nf(nm)
        for ch, dc in ((0, -detune), (1, detune)):
            f = f0 * 2 ** (dc / 1200)
            K = int(min(30, 12000 / f))
            for k in range(1, K + 1):
                out[ch] += (1.0 / k) / np.sqrt(1 + (k * f / fc) ** 4) * np.sin(TAU * k * f * t + r.uniform(0, TAU))
    env = np.exp(-t / tau_a)
    env[:ns(0.003)] *= rise(ns(0.003))
    out = ffilt_mp(out * env, lambda f: m_hp(f, 110, 2))
    return edges(npk(out), 0.0002, 0.05)


def crash(dur, label, decay=0.55, hp=3200.0):
    """Prato. Devolve (2, n)."""
    r = rng_for(label)
    n = ns(dur)

    def shape(tc, f):
        T = decay * (1.4 - 0.75 * np.clip(np.log2(np.maximum(f, 1) / 3000) / 2.5, 0, 1))
        return np.exp(-np.maximum(tc, 0) / T) * m_hp(f, hp, 2) * m_lp(f, 15000, 1)

    x = np.stack([shaped_noise(n, shape, r), shaped_noise(n, shape, r)])
    x[:, :ns(0.0015)] *= rise(ns(0.0015))
    return edges(npk(x), 0.0001, 0.05)


# ---------------------------------------------------------------- composicoes prontas
def glow(mx, t, label, gain_db=0.0, bus='trans'):
    """Brilho: chiado agudo curto + cascata de brilhos em DO pentatonico, espalhados no estereo."""
    r = rng_for(label + 'sizzle')
    n = ns(0.5)
    tt = tv(n)
    sz = ffilt(r.standard_normal((2, n)), lambda f: m_band(f, 5500, 16000, 2)) * np.exp(-tt / 0.07)
    sz[:, :ns(0.0008)] *= rise(ns(0.0008))
    mx.add(bus, edges(npk(sz), 0.0001, 0.02), t, -13.0 + gain_db, 0.0, {'hall': 0.25})
    rs = rng_for(label + 'sp')
    pent = [nf(x) for x in ('C7', 'E7', 'G7', 'A7', 'C8', 'D8')]
    for k in range(10):
        mx.add(bus, tinkle(pent[rs.integers(len(pent))], f'{label}sp{k}', tau=0.07), t + 0.03 + 0.5 * (k / 9) ** 1.5,
               -27.0 + gain_db - 1.2 * k, rs.uniform(-0.8, 0.8), {'hall': 0.4})


def logo_hit(mx, t, label='logo', big=False, bus='trans', gain_db=0.0, mark=True):
    """Impacto brilhante com grave (entrada do logo): bumbo grande, camada de 100 a 250 Hz, prato, sinos em DO maior
    e brilho. Com mark=True registra 3 cues: impacto (60-8000 Hz), no celular (>200 Hz) e brilho (4-14 kHz)."""
    g = gain_db
    mx.add(bus, kick(label + 'k', f_hi=210, f_lo=47, tau_a=0.33, dur=0.9, click=0.3, drive=1.9), t, -3.0 + g, probe=label + '.hit')
    mx.add(bus, impact(label + 'i', f_hi=110, f_lo=55, tau_a=0.3, dur=1.0,
                       mids=((131, 0.14, 1.0), (196, 0.1, 0.7), (262, 0.07, 0.4)), mid_gain=0.8, trans_gain=0.5, drive=1.8),
           t, -5.5 + g, 0.0, {'dark': 0.15})
    mx.add(bus, crash(2.4, label + 'c', decay=0.7), t, -10.0 + (2 if big else 0) + g, 0.0, {'hall': 0.2}, probe=label + '.crash')
    for i, nm in enumerate(('C6', 'E6', 'G6', 'C7')):
        mx.add(bus, ding(nf(nm), f'{label}bell{i}', tau=0.6), t + 0.004 * i, -21.0 - 2 * i + g, (-0.4, 0.4, -0.15, 0.2)[i], {'hall': 0.35})
    glow(mx, t, label, g, bus)
    if mark:
        mx.mark(t, f'{label} (impacto)', (60, 8000), probe=label + '.hit', bus=bus)
        mx.mark(t, f'{label} no celular (>200 Hz)', (200, 8000), probe=label + '.hit', bus=bus)
        mx.mark(t, f'{label} (brilho)', (4000, 14000), probe=label + '.crash', bus=bus)


def groove(mx, G, t0, t1, chords=('C', 'G', 'Am', 'F'), bars_per_chord=1, level=0.0, kick_skip=(), hats=True, bass=True,
           plucks=True, pad=True, clap_on=True, label='gr'):
    """Groove pop pronto na grade G, de t0 a t1: bumbo 4 no chao, palmas 2 e 4, chimbais, baixo no contratempo,
    plucks em tresillo e pad seguindo os acordes. kick_skip = tempos (s) sem bumbo (ex.: onde ja ha um impacto)."""
    kicks = [kick(f'{label}k{i}') for i in range(2)]
    claps = [clap(f'{label}cl{i}') for i in range(3)]
    hc = [hat(f'{label}hc{i}') for i in range(4)]
    ho = [hat(f'{label}ho{i}', True) for i in range(3)]
    hr = rng_for(label + 'hum')
    spc = 16 * bars_per_chord * G.bpb // 4   # semicolcheias por acorde

    def chord_at(s):
        return chords[(s // spc) % len(chords)]

    steps = list(G.steps(t0, t1))
    for s in steps:
        t = G.sixteenth(s)
        b = s % (4 * G.bpb)
        ch = chord_at(s)
        if b % 4 == 0 and not any(abs(t - k) < 1e-4 for k in kick_skip):
            mx.add('music', kicks[(s // 4) % 2], t, -4.0 + level)
            mx.pump.append(t)
        if clap_on and b in (4, 12):
            mx.add('music', claps[(s // 4) % 3], t + hr.uniform(-0.002, 0.002), -13.0 + level, 0.0, {'plate': 0.35})
        if hats:
            vel = (0.0, -9.0, -2.0, -9.0)[b % 4]
            jt = hr.uniform(-0.003, 0.003)
            if b % 4 == 2:
                mx.add('music', ho[(s // 2) % 3], t + jt, -21.0 + vel + level, 0.25, {'plate': 0.08})
            else:
                mx.add('music', hc[s % 4], t + jt, -23.0 + vel + level, 0.3)
        if bass and b % 4 == 2:
            root = nf(CHORDS[ch]['bass']) * (2 if b % 8 == 6 else 1)
            mx.add('music', bass_note(root, min(0.17, G.step * 2 * 0.9)), t, -9.0 + level)
        hs = s % 8
        if plucks and hs in (0, 3, 6):
            notes = CHORDS[ch]['arp']
            order = (0, 1, 2) if (s // 8) % 2 == 0 else (2, 1, 0)
            nm = notes[order[(0, 3, 6).index(hs)]]
            mx.add('music2', pluck_st(nf(nm), f'{label}pl{s}', dur=0.55, tau0=0.3), t, -20.0 + (-1.5 if hs else 0.0) + level, 0.0,
                   {'hall': 0.25, 'delay': 0.3})
    if pad and steps:
        s = steps[0]
        while s <= steps[-1]:
            e = s + 1
            while e <= steps[-1] and chord_at(e) == chord_at(s):
                e += 1
            ta = G.sixteenth(s)
            dur = min(G.sixteenth(e), t1) - ta
            mx.add('music2', pad_chord(CHORDS[chord_at(s)]['pad'], dur, f'{label}pad{s}', attack=0.08, release=0.35, fc=1600.0),
                   ta, -21.0 + level, 0.0, {'hall': 0.25})
            s = e


# ---------------------------------------------------------------- medicao (BS.1770) e master
KW1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
KW2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def biquad_mag(ba, f):
    b, a = ba
    z1 = np.exp(-1j * TAU * np.asarray(f) / SR)
    z2 = z1 * z1
    return np.abs((b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2))


def k_weight(x):
    return ffilt(x, lambda f: biquad_mag(KW1, f) * biquad_mag(KW2, f))


def blocks_ms(x, win=0.4, hop=0.1, weighted=True):
    y = k_weight(x) if weighted else x
    p = np.square(y).sum(axis=0)
    cs = np.concatenate(([0.0], np.cumsum(p)))
    W, H = ns(win), ns(hop)
    starts = np.arange(0, y.shape[1] - W + 1, H)
    return starts / SR, (cs[starts + W] - cs[starts]) / W


def lufs_of(ms):
    return -0.691 + 10 * np.log10(np.maximum(ms, 1e-20))


def integrated(x):
    _, ms = blocks_ms(x)
    L = lufs_of(ms)
    g = ms[L > -70]
    rel = lufs_of(g.mean()) - 10
    return float(lufs_of(ms[(L > -70) & (L > rel)].mean()))


def upsample4(x):
    n = x.shape[-1]
    X = np.fft.rfft(x, axis=-1)
    Y = np.zeros(X.shape[:-1] + (2 * n + 1,), complex)
    Y[..., :X.shape[-1]] = X
    return np.fft.irfft(Y, 4 * n, axis=-1) * 4


def tp_per_sample(x):
    return np.abs(upsample4(x)).max(axis=0).reshape(-1, 4).max(axis=1)


def true_peak_db(x):
    return float(todb(tp_per_sample(x).max()))


def tp_limiter(x, ceiling_db, look=0.0015, release=0.12):
    from numpy.lib.stride_tricks import sliding_window_view
    c = undb(ceiling_db)
    g = np.minimum(1.0, c / np.maximum(tp_per_sample(x), 1e-12))
    if g.min() >= 1.0:
        return x, 0.0
    L = max(2, ns(look))
    gmin = sliding_window_view(np.concatenate([g, np.ones(L - 1)]), L).min(axis=1)
    arr = np.concatenate([np.ones(L - 1), gmin])
    cs = np.concatenate(([0.0], np.cumsum(arr)))
    s = (cs[L:L + g.size] - cs[:g.size]) / L
    rc = math.exp(-1.0 / (release * SR))
    out = np.empty_like(s)
    prev = 1.0
    for i, v in enumerate(s.tolist()):
        prev = v if v < prev else v + (prev - v) * rc
        out[i] = prev
    return x * out[None, :], float(todb(out.min()))


def premaster(mix, target=TARGET_LUFS, ceil=PREMASTER_TP):
    """Leva o mix a -14 LUFS com true peak <= -2 dBTP (o loudnorm fica so com o ajuste linear fino)."""
    g = target - integrated(mix)
    y, gr = None, 0.0
    for _ in range(6):
        y, gr = tp_limiter(mix * undb(g), ceil)
        err = target - integrated(y)
        if abs(err) < 0.03:
            break
        g += err
    tp = true_peak_db(y)
    if tp > ceil + 0.05:
        y, _ = tp_limiter(y, ceil - (tp - ceil) - 0.05)
    return y, g, gr


def ff(args, check=True):
    p = subprocess.run([str(FFMPEG), '-hide_banner', '-nostats', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError(p.stderr[-3000:])
    return p.stderr


def last_json(txt):
    return json.loads(txt[txt.rfind('{'):txt.rfind('}') + 1])


def ebur128_summary(path, pre=''):
    af = (pre + ',' if pre else '') + 'ebur128=peak=true:framelog=quiet'
    txt = ff(['-i', str(path), '-af', af, '-f', 'null', '-'])
    k = txt.rfind('Summary:')
    summ = txt[k:].strip() if k >= 0 else txt[-1500:]

    def grab(key):
        m = re.search(key + r':\s+(-?[\d.]+|-inf)', summ)
        return float(m.group(1)) if m and m.group(1) != '-inf' else float('-inf')

    return summ, dict(I=grab('I'), LRA=grab('LRA'), TP=grab('Peak'), thr=grab('Threshold'))


def loudnorm_apply(src, dst_float, meas, target=TARGET_LUFS):
    lra = max(7.0, math.ceil(float(meas['input_lra']) + 1.0))
    af = ('loudnorm=I={I}:TP=-1:LRA={lra}:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:'
          'measured_thresh={input_thresh}:offset={target_offset}:linear=true:print_format=json,aresample=48000').format(I=target, lra=lra, **meas)
    return last_json(ff(['-i', str(src), '-af', af, '-c:a', 'pcm_f32le', '-ar', '48000', '-y', str(dst_float)])), af


def loudnorm_two_pass(src, dst_float, target=TARGET_LUFS):
    """Passada 1 mede, passada 2 aplica (linear). Se a passada 2 medir a entrada diferente (~0,05 LU,
    a passada 1 roda no modo dinamico), reaplica com essa medicao refinada."""
    p1 = last_json(ff(['-i', str(src), '-af', f'loudnorm=I={target}:TP=-1:LRA=20:print_format=json', '-f', 'null', '-']))
    p2, af = loudnorm_apply(src, dst_float, p1, target)
    runs = [('passada 1 (medicao)', p1, None), ('passada 2 (aplicacao linear)', p2, af)]
    if p2['normalization_type'] == 'linear' and abs(float(p2['output_i']) - target) > 0.02:
        p3, af3 = loudnorm_apply(src, dst_float, p2, target)
        runs.append(('passada 2 refeita com a medicao da propria passada 2', p3, af3))
    return runs


# ---------------------------------------------------------------- conferencia dos cues
SEARCH_MAX = 0.04  # busca +-40 ms (2,4 quadros): o teste de 1 quadro nao passa por construcao


def band_energy_ms(x, lo, hi):
    m = x.mean(axis=0) if x.ndim == 2 else x
    y = ffilt_mp(m, lambda f: m_band(f, lo, hi, 4))
    H = ns(0.001)
    return np.square(y[:y.size // H * H]).reshape(-1, H).mean(axis=1)


def smooth_db(e, lo):
    w = int(np.clip(round(1000.0 / lo), 3, 21))
    E = 10 * np.log10(e + 1e-14)
    return np.convolve(E, np.ones(w) / w, mode='same'), max(3, w // 2)


def onset_at(Es, h, t, search=0.015):
    k = int(round(t * 1000))
    s_ = int(round(search * 1000))
    a, b = max(h + 1, k - s_), min(Es.size - h - 1, k + s_ + 1)
    if b <= a:
        return t
    D = Es[a + h:b + h] - Es[a - h:b - h]
    return (a + int(np.argmax(D))) / 1000


def tone_freq(x, t, lo, hi):
    m = x.mean(axis=0) if x.ndim == 2 else x
    seg = m[ns(t + 0.01):ns(t + 0.41)]
    seg = seg * np.hanning(seg.size)
    sp = np.abs(np.fft.rfft(seg, 1 << 20))
    fr = np.fft.rfftfreq(1 << 20, 1 / SR)
    sel = np.nonzero((fr > lo) & (fr < hi))[0]
    i = sel[np.argmax(sp[sel])]
    a, b, c = np.log(sp[i - 1:i + 2] + 1e-20)
    return fr[i] + 0.5 * (a - c) / (a - 2 * b + c) * (fr[1] - fr[0])


def search_windows(events):
    """+-40 ms, ou 75% da distancia ao vizinho mais proximo com faixa sobreposta (sequencias densas)."""
    pts = [e for e in events if e['kind'] != 'range']
    out = {}
    for e in pts:
        lo, hi = e['band']
        gap = 1.0
        for g in pts:
            dt = abs(g['t'] - e['t'])
            if dt > 1e-6 and g['band'][0] < hi and lo < g['band'][1]:
                gap = min(gap, dt)
        out[id(e)] = float(np.clip(0.75 * gap, 0.01, SEARCH_MAX))
    return out


def match_lag(x, tmpl, t, band, search):
    """Filtro casado: onde o molde seco aparece em x perto de t (+-search). Devolve (desvio s, correlacao 0..1)."""
    m = x.mean(axis=0) if x.ndim == 2 else x
    L = tmpl.size
    i0 = ns(t)
    a = max(0, i0 - ns(search))
    b = min(m.size, i0 + ns(search) + L)
    lo, hi = band

    def H(f):
        return m_band(f, lo, hi, 2)

    segf = ffilt(m[a:b], H, pad=8192)
    tf = ffilt(tmpl, H, pad=8192)
    c = np.correlate(segf, tf, mode='valid')
    cs = np.concatenate(([0.0], np.cumsum(segf ** 2)))
    e = np.sqrt(np.maximum(cs[L:] - cs[:-L], 1e-30) * np.sum(tf ** 2))
    rho = c / e[:c.size]
    k = int(np.argmax(rho))
    return (a + k - i0) / SR, float(rho[k])


def check_events(x, events, stems=None, probes=None, fps=60, hp_hz=30.0):
    """Confere cada cue no master e no barramento de origem: filtro casado com o molde do som e ataque de energia
    na faixa do evento. ok = desvio <= 1 quadro."""
    frame = 1.0 / fps
    rows = []
    cache, scache = {}, {}
    probes = probes or {}
    win = search_windows(events)
    for ev in sorted(events, key=lambda e: e['t']):
        lo, hi = ev['band']
        key = (round(lo), round(hi))
        if key not in cache:
            cache[key] = smooth_db(band_energy_ms(x, lo, hi), lo)
        Es, h = cache[key]
        k = int(round(ev['t'] * 1000))
        row = dict(label=ev['label'], t=ev['t'], kind=ev['kind'])
        if ev['kind'] == 'range':
            a, b = int(ev['span'][0] * 1000), int(ev['span'][1] * 1000)
            kp = a + int(np.argmax(Es[a:b]))
            base = np.mean(Es[max(0, a - 60):a - 5]) if a > 70 else np.min(Es[a:b])
            row.update(peak=kp / 1000, rise=float(Es[kp] - base), ok=True)
            rows.append(row)
            continue
        sw = win[id(ev)]
        row['win'] = sw
        row['onset'] = onset_at(Es, h, ev['t'], sw)
        row['rise'] = float(np.max(Es[k:k + 60]) - np.mean(Es[max(0, k - 60):max(1, k - 8)])) if k > 10 else float('nan')
        pr = probes.get((ev['probe'], round(ev['t'], 5)))
        bus = (pr[1],) if pr is not None else ((ev['bus'],) if ev.get('bus') else ())
        mband = ev.get('mband') or ((4000.0, 16000.0) if ev['kind'] == 'tone' else (lo, hi))
        if stems is not None and bus:
            src = sum(stems[b] for b in bus if b in stems)
            skey = (bus, key)
            if skey not in scache:
                scache[skey] = smooth_db(band_energy_ms(src, lo, hi), lo)
            Ss, hs = scache[skey]
            row['onset_stem'] = onset_at(Ss, hs, ev['t'], sw)
            if ev['kind'] == 'tone':
                row['freq'] = tone_freq(src, ev['t'], lo, hi)
            if pr is not None:
                row['mf_stem'] = match_lag(src, pr[0], ev['t'], mband, sw)
        if pr is not None:
            tmpl = ffilt_mp(pr[0], lambda f: m_hp(f, hp_hz, 4)) if hp_hz else pr[0]
            row['mf'] = match_lag(x, tmpl, ev['t'], mband, sw)
        lags = [abs(row['onset'] - ev['t'])]
        if 'mf' in row:
            lags = [abs(row['mf'][0])] + ([abs(row['mf_stem'][0])] if 'mf_stem' in row else [])
        row['dev'] = max(lags)
        row['ok'] = row['dev'] <= frame + 1e-9
        row['conf'] = row['mf_stem'][1] if 'mf_stem' in row else None
        rows.append(row)
    return rows


def cue_report(rows, fps=60):
    frame = 1.0 / fps
    out = []
    pts = [r for r in rows if r['kind'] != 'range']
    mf = [r for r in pts if 'mf' in r]
    mfs = [r for r in mf if 'mf_stem' in r]
    n_ok = sum(1 for r in pts if r['ok'])

    def mx_ms(vals):
        return 1000 * max(vals) if vals else float('nan')

    out.append(f'  {len(pts)} eventos pontuais ({len(mf)} com filtro casado); dentro de 1 quadro ({1000 * frame:.1f} ms): {n_ok} de {len(pts)}')
    out.append(f'  maior desvio: filtro casado no master {mx_ms([abs(r["mf"][0]) for r in mf]):.1f} ms, '
               f'no stem {mx_ms([abs(r["mf_stem"][0]) for r in mfs]):.1f} ms; '
               f'ataque de energia no master {mx_ms([abs(r["onset"] - r["t"]) for r in pts]):.0f} ms')
    if mfs:
        out.append(f'  correlacao do filtro casado: stem minima {min(r["mf_stem"][1] for r in mfs):.2f}, '
                   f'master minima {min(r["mf"][1] for r in mf):.2f} (1 = som identico ao molde)')
    for r in pts:
        if not r['ok']:
            out.append(f'  FORA DE 1 QUADRO: {r["t"]:.4f} s {r["label"]}')
    for r in pts:
        if r.get('conf') is not None and r['conf'] < 0.35:
            out.append(f'  correlacao baixa no stem ({r["conf"]:.2f}, som encoberto por outro na mesma faixa): {r["t"]:.4f} s {r["label"]}')
    out.append('     cue(s) janela | casado master  | casado stem   | ataque master stem | subida  freq      evento')
    for r in rows:
        if r['kind'] == 'range':
            out.append(f'  {r["t"]:9.4f}  trecho: pico de energia na faixa em {r["peak"]:.3f} s ({r["rise"]:+.1f} dB)  {r["label"]}')
            continue
        cm = f'{1000 * r["mf"][0]:+5.1f}ms {r["mf"][1]:.2f}' if 'mf' in r else '      -      '
        cs = f'{1000 * r["mf_stem"][0]:+5.1f}ms {r["mf_stem"][1]:.2f}' if 'mf_stem' in r else '      -      '
        om = f'{1000 * (r["onset"] - r["t"]):+4.0f}ms'
        os_ = f'{1000 * (r["onset_stem"] - r["t"]):+4.0f}ms' if 'onset_stem' in r else '    -'
        fq = f'{r["freq"]:7.1f}Hz' if 'freq' in r else ''
        out.append(f'  {r["t"]:9.4f} {1000 * r["win"]:4.0f}ms | {cm} | {cs} | {om} {os_}    | {r["rise"]:+5.1f}dB {fq:9s} '
                   f'{r["label"]}{"" if r["ok"] else "  <-- FORA"}')
    return out


def scene_loudness(x, cues):
    ts, ms = blocks_ms(x)
    rel = integrated(x)
    out = []
    for sc in cues.get('scenes', []):
        sel = (ts + 0.2 >= sc['start']) & (ts + 0.2 < sc['end'])
        if sel.any():
            out.append(f'  {sc["id"]:14s} {sc["start"]:6.2f}-{sc["end"]:6.2f}s  media {lufs_of(ms[sel].mean()) - rel:+6.1f} LU  '
                       f'pico momentaneo {lufs_of(ms[sel].max()) - rel:+6.1f} LU')
    return out


def hit_contrast(x, times):
    """Pancadas no alto-falante de celular: energia 200-8000 Hz nos 100 ms depois / nos 150 ms antes."""
    m = ffilt(x.mean(axis=0), lambda f: m_band(f, 200, 8000, 2))
    out = []
    for lab, t in times:
        if t < 0.16:
            continue
        pre = np.mean(m[ns(t - 0.15):ns(t - 0.003)] ** 2)
        post = np.mean(m[ns(t):ns(t + 0.1)] ** 2)
        out.append(f'  {t:6.2f} s  {10 * np.log10(post / pre):+5.1f} dB  {lab}')
    return out


def annotated_pngs(x, events, cues, out_spec, out_wave):
    """Espectrograma e forma de onda 1920 px com os cues (verde) e o inicio das cenas (branco)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    W, Hh = 1920, 1080
    dur = x.shape[1] / SR
    m = x.mean(axis=0)
    nfft, hop = 2048, max(1, x.shape[1] // W)
    win = np.hanning(nfft)
    pad = np.concatenate([np.zeros(nfft // 2), m, np.zeros(nfft)])
    frames = np.stack([pad[i * hop:i * hop + nfft] * win for i in range(W)])
    S = np.abs(np.fft.rfft(frames, axis=1))
    fr = np.fft.rfftfreq(nfft, 1 / SR)
    fl = np.geomspace(25, 20000, Hh)
    img = np.empty((Hh, W))
    for j in range(W):
        img[:, j] = np.interp(fl, fr, S[j])
    D = np.clip((20 * np.log10(img / (nfft / 4) + 1e-9) + 100) / 100, 0, 1)[::-1]
    rgb = np.stack([np.clip(1.5 * D - 0.2, 0, 1), np.clip(2.2 * D - 1.1, 0, 1), np.clip(0.7 * D + 0.25 * np.sin(D * 3), 0, 1)], axis=-1)
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    for i, ev in enumerate(sorted(events, key=lambda e: e['t'])):
        xpx = int(ev['t'] / dur * W)
        col = (120, 180, 255) if ev['kind'] == 'tick' else (80, 255, 120)
        dr.line([(xpx, 0), (xpx, Hh)], fill=col, width=1)
        if ev['kind'] != 'tick':
            dr.text((xpx + 2, 4 + 12 * (i % 60)), ev['label'][:34], fill=col)
    for sc in cues.get('scenes', []):
        xpx = int(sc['start'] / dur * W)
        dr.line([(xpx, Hh - 30), (xpx, Hh)], fill=(255, 255, 255), width=3)
        dr.text((xpx + 3, Hh - 26), sc['id'], fill=(255, 255, 255))
    for f in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
        y = int(Hh - 1 - np.interp(np.log(f), np.log(fl), np.arange(Hh)))
        dr.text((3, y - 6), f'{f} Hz', fill=(200, 200, 200))
    im.save(out_spec)
    wv = Image.new('RGB', (W, 540), (12, 12, 12))
    dr = ImageDraw.Draw(wv)
    for ch in range(2):
        seg = np.abs(x[ch, :W * hop]).reshape(W, hop).max(axis=1)
        mid = 135 + 270 * ch
        for j in range(W):
            h = int(np.sqrt(seg[j]) * 125)
            dr.line([(j, mid - h), (j, mid + h)], fill=(92, 204, 127))
    for ev in events:
        xpx = int(ev['t'] / dur * W)
        dr.line([(xpx, 0), (xpx, 540)], fill=(255, 210, 60) if ev['kind'] != 'tick' else (90, 140, 255), width=1)
    for sc in cues.get('scenes', []):
        xpx = int(sc['start'] / dur * W)
        dr.line([(xpx, 0), (xpx, 540)], fill=(255, 255, 255), width=2)
        dr.text((xpx + 3, 3), sc['id'], fill=(255, 255, 255))
    wv.save(out_wave)


# ---------------------------------------------------------------- final: master + relatorio
def finish(mx, total, stems, cues, out_dir=None, title=None, quick=False, hits=None, extra_lines=None):
    """Gera no out_dir (padrao: pasta audio/):
         mix.wav (pico -1 dBFS), master.wav (-14 LUFS, TP <= -1 dBTP, duracao exata),
         loudness.txt, report.json, spectrogram.png, waveform.png, build/ (stems, premaster, imagens com cues).
    hits = [(rotulo, t)] pancadas para medir no alto-falante de celular (padrao: eventos com 'impacto' no rotulo).
    quick=True: so mix + premaster + conferencia interna (sem ffmpeg). Devolve dict com as medidas."""
    t_start = time.time()
    out = Path(out_dir or HERE)
    build = out / 'build'
    build.mkdir(parents=True, exist_ok=True)
    fps = int(cues.get('fps', 60))
    N = mx.n
    hp_hz = getattr(mx, 'hp_hz', 30.0)

    sf.write(out / 'mix.wav', npk(total, undb(-1.0)).T, SR, subtype='PCM_24')
    pk_total = peak(total) or 1.0
    for b, x in stems.items():
        sf.write(build / f'stem_{b}.wav', (x * undb(-1.0) / pk_total).T, SR, subtype='FLOAT')

    y, g, gr = premaster(total)
    print(f'premaster: ganho {g:+.2f} dB, limitador {gr:.2f} dB, {integrated(y):.2f} LUFS, TP {true_peak_db(y):.2f} dBTP')
    if quick:
        rows = check_events(y, mx.events, stems, mx.probes, fps, hp_hz)
        print('\n'.join(cue_report(rows, fps)))
        return dict(rows=rows)

    pre_path = build / 'premaster.wav'
    sf.write(pre_path, y.T.astype(np.float32), SR, subtype='FLOAT')
    ln_path = build / 'loudnorm_out.wav'
    runs = loudnorm_two_pass(pre_path, ln_path)
    z, zsr = sf.read(ln_path, always_2d=True)
    z = z.T
    assert zsr == SR
    # alinhamento amostra a amostra com o premaster (o reamostrador nao pode atrasar o som)
    a, b = y.mean(axis=0), z.mean(axis=0)[:y.shape[1]]
    L = nextpow2(2 * a.size)
    xc = np.fft.irfft(np.fft.rfft(b, L) * np.conj(np.fft.rfft(a, L)), L)
    lim = 4800
    cand = np.concatenate([xc[:lim], xc[-lim:]])
    k = int(np.argmax(np.abs(cand)))
    lag = k if k < lim else k - 2 * lim
    if lag > 0:
        z = z[:, lag:]
    elif lag < 0:
        z = np.concatenate([np.zeros((2, -lag)), z], axis=1)
    if z.shape[1] < N:
        z = np.concatenate([z, np.zeros((2, N - z.shape[1]))], axis=1)
    z = z[:, :N]
    for s0, s1 in getattr(mx, 'silences', []):
        z[:, ns(s0):ns(s1)] = 0.0
    z[:, N - ns(0.005):] = 0.0
    master_path = out / 'master.wav'
    sf.write(master_path, z.T, SR, subtype='PCM_24')

    master, _ = sf.read(master_path, always_2d=True)
    master = master.T
    summ_full, v_full = ebur128_summary(master_path)
    summ_hp, v_hp = ebur128_summary(master_path, 'highpass=f=200')
    rows = check_events(master, mx.events, stems, mx.probes, fps, hp_hz)
    info = sf.info(master_path)
    hits = hits if hits is not None else [(e['label'], e['t']) for e in mx.events if 'impacto' in e['label']]

    rep = []
    rep.append(f'{title or cues.get("name", "video")}: relatorio de loudness e conferencia do audio')
    rep.append(f'gerado em {time.strftime("%Y-%m-%d %H:%M:%S")}')
    rep.append('')
    rep.append('== MASTER (master.wav) ==')
    rep.append(f'  formato: {info.samplerate} Hz, {info.channels} canais, {info.subtype}, {info.frames} amostras = '
               f'{info.frames / info.samplerate:.6f} s (esperado {N} = {cues["duration"]:.6f} s)')
    rep.append(f'  Integrado: {v_full["I"]:.1f} LUFS   True peak: {v_full["TP"]:.1f} dBTP   LRA: {v_full["LRA"]:.1f} LU')
    rep.append(f'  pico de amostra: {todb(peak(master)):.2f} dBFS; ultimos 5 ms: pico {peak(master[:, N - ns(0.005):]):.1e}')
    rep.append('  ebur128 (ffmpeg):')
    rep += ['    ' + ln for ln in summ_full.splitlines()]
    rep.append('')
    rep.append('== MASTER com passa-altas de 200 Hz (simula alto-falante de celular) ==')
    rep.append(f'  Integrado {v_hp["I"]:.1f} LUFS ({v_hp["I"] - v_full["I"]:+.1f} LU)   True peak {v_hp["TP"]:.1f} dBTP   LRA {v_hp["LRA"]:.1f} LU')
    rep += ['    ' + ln for ln in summ_hp.splitlines()]
    rep.append('')
    rep.append('== loudnorm (duas passadas, linear=true) ==')
    for name, js, afx in runs:
        rep.append(f'  {name}: ' + json.dumps(js, ensure_ascii=False))
        if afx:
            rep.append(f'    filtro: {afx}')
    rep.append(f'  alinhamento loudnorm x premaster: {lag} amostras (corrigido)')
    rep.append(f'  premaster: ganho {g:+.2f} dB, reducao maxima do limitador {gr:.2f} dB')
    rep.append('')
    rep.append('== Loudness por cena (relativo ao integrado) ==')
    rep += scene_loudness(master, cues)
    if hits:
        rep.append('== Pancadas no alto-falante de celular (200-8000 Hz: 100 ms depois / 150 ms antes) ==')
        rep += hit_contrast(master, hits)
    rep.append('== Estalos, DC e mono ==')
    rep.append(f'  bordas dos sons: maior |amostra| no inicio/fim de um som = {mx.edge_max:.1e} do pico dele')
    rep.append(f'  DC: L {master[0].mean():+.2e}  R {master[1].mean():+.2e}')
    mono = np.repeat(master.mean(axis=0)[None, :], 2, axis=0)
    corr = float(np.sum(master[0] * master[1]) / np.sqrt(np.sum(master[0] ** 2) * np.sum(master[1] ** 2) + 1e-30))
    rep.append(f'  mono (celular de 1 alto-falante): {integrated(mono) - integrated(master):+.2f} LU; correlacao L/R {corr:.2f}')
    if extra_lines:
        rep.append('')
        rep += extra_lines
    rep.append('')
    rep.append(f'== Conferencia dos cues (master e barramento de origem; tolerancia 1 quadro = {1000 / fps:.1f} ms) ==')
    rep += cue_report(rows, fps)
    (out / 'loudness.txt').write_text('\n'.join(rep) + '\n', encoding='utf-8')

    ff(['-i', str(master_path), '-lavfi', 'showspectrumpic=s=1920x1080:legend=1:fscale=log:start=20:stop=20000:scale=log:color=intensity',
        '-frames:v', '1', '-update', '1', '-y', str(out / 'spectrogram.png')])
    ff(['-i', str(master_path), '-lavfi', 'showwavespic=s=1920x1080:split_channels=1:scale=sqrt:colors=0x5CCC7F|0x30CD97',
        '-frames:v', '1', '-update', '1', '-y', str(out / 'waveform.png')])
    annotated_pngs(master, mx.events, cues, build / 'spectrogram_cues.png', build / 'waveform_cues.png')

    pts = [r for r in rows if r['kind'] != 'range']
    summary = dict(
        lufs=v_full['I'], true_peak=v_full['TP'], lra=v_full['LRA'], lufs_hp200=v_hp['I'],
        samples=info.frames, expected_samples=N, seconds=info.frames / info.samplerate,
        cues_total=len(pts), cues_ok=sum(1 for r in pts if r['ok']),
        cue_max_dev_ms=round(1000 * max((r['dev'] for r in pts), default=0.0), 2),
        cues=[dict(t=r['t'], label=r['label'], dev_ms=round(1000 * r['dev'], 2), ok=r['ok']) for r in pts],
        loudnorm=runs[-1][1].get('normalization_type'), seconds_to_build=round(time.time() - t_start, 1),
    )
    ok = abs(v_full['I'] - TARGET_LUFS) <= 0.5 and v_full['TP'] <= -1.0 and summary['cues_ok'] == summary['cues_total'] and info.frames == N
    summary['ok'] = bool(ok)
    (out / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('\n'.join(rep[3:7]))
    print('\n'.join(cue_report(rows, fps)[:3]))
    print('AUDIO OK' if ok else 'AUDIO COM PROBLEMA: ver loudness.txt')
    return summary
