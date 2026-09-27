"""Trilha de boca (lip sync) para o avatar: le um WAV de VOZ ISOLADA e gera, por
quadro (60 fps), quanto a boca abre, quanto estica ou arredonda e se os dentes
aparecem. O avatar (lib-avatar.js) so interpola essa trilha: tudo continua
funcao pura do tempo.

  python tools/lipsync.py audio/voz_trilha.wav --out audio/fala.json --js audio/fala.js --name fala
  python tools/lipsync.py audio/voz_trilha.wav --text "Oi! A IA atende seus clientes." --out ...

Regras de uso
  * Rode sobre a VOZ SOZINHA, ja posicionada na linha do tempo do video (mesmo
    inicio e mesma duracao do master). Musica ou efeitos sujam a trilha.
    Se a voz comeca em 0,7 s do video, gere um WAV com 0,7 s de silencio antes
    (ou use --offset 0.7, que desloca a trilha sem mexer no arquivo).
  * --text (recomendado): o texto exato falado. Com ele, o script converte o
    portugues em visemas (A, E, I, O, U, M/B/P, F/V, S/X/J, L/T/D/N/R) e alinha
    a sequencia ao audio por Viterbi (alinhamento forcado simples). Da boca
    fechada de verdade no "m/p/b", dentes no "s/f", bico no "o/u", e ainda o
    tempo de cada palavra (para legenda sincronizada).
  * Sem --text: so o audio. Abertura pela energia, forma pelas bandas de
    frequencia (F1 alto = boca aberta; F2 alto = boca esticada; chiado = dentes).

Como mede (por quadro, janela Hann de 40 ms centrada no quadro)
  * volume na faixa da fala (80 a 8000 Hz) em dB, normalizado entre o piso de
    ruido e o pico da fala;
  * F1 aproximado = centroide de 250 a 1200 Hz (mandibula: A > E,O > I,U);
  * F2 aproximado = centroide de 800 a 3000 Hz (labios: I,E esticados; O,U bico);
  * chiado = energia acima de 3500 Hz sobre o total (s, x, f);
  * graves = energia de 80 a 400 Hz sobre o total (m, n, b sonoros).
  --lead (padrao 0,03 s): a boca adianta o som um tiquinho, como na vida real;
  sem isso a boca parece atrasada.

Saida (JSON, e opcionalmente um .js que registra window.LIPSYNC[name]):
  fps, frames, duration, lead, offset, text
  open[]  0..1   abertura da boca
  wide[] -1..1   -1 bico (o/u), +1 esticada (i/e)
  teeth[] 0..1   dentes de cima a mostra
  vis     string com 1 caractere por quadro: . A E I O U M F S L
  words[] {w, t0, t1}  (so com --text)
  segs[]  {v, t0, t1}  trechos de visema, para conferir a olho
"""
import argparse, json, math, os, re, struct, sys, unicodedata

import numpy as np

# ── leitura de WAV (PCM 16/24/32 bits e float 32, sem scipy) ─────────────────


def read_wav(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        sys.exit(f'{path}: nao e WAV RIFF')
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b'fmt ':
            tag, ch, sr = struct.unpack('<HHI', body[:8])
            bits = struct.unpack('<H', body[14:16])[0]
            if tag == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                tag = struct.unpack('<H', body[24:26])[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b'data':
            raw = body
        pos += 8 + size + (size & 1)
    if not fmt or raw is None:
        sys.exit(f'{path}: faltam blocos fmt/data')
    tag, ch, sr, bits = fmt
    if tag == 3 and bits == 32:
        x = np.frombuffer(raw, '<f4').astype(np.float64)
    elif tag == 1 and bits == 16:
        x = np.frombuffer(raw, '<i2') / 32768.0
    elif tag == 1 and bits == 32:
        x = np.frombuffer(raw, '<i4') / 2147483648.0
    elif tag == 1 and bits == 24:
        b = np.frombuffer(raw[:len(raw) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / 8388608.0
    else:
        sys.exit(f'{path}: formato nao suportado (tag {tag}, {bits} bits)')
    x = x[:len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


# ── medidas por quadro ───────────────────────────────────────────────────────


def features(x, sr, fps, n_frames, lead, offset):
    win = int(round(0.040 * sr))
    nfft = 1 << (win - 1).bit_length()
    hann = np.hanning(win)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)

    def band(lo, hi):
        return (freqs >= lo) & (freqs < hi)

    b_sp, b_lo, b_hi = band(80, 8000), band(80, 400), band(3500, 8000)
    b_f1, b_f2 = band(250, 1200), band(800, 3000)
    pad = np.concatenate([np.zeros(win), x, np.zeros(win)])
    db = np.zeros(n_frames); lo = np.zeros(n_frames); hi = np.zeros(n_frames)
    f1 = np.zeros(n_frames); f2 = np.zeros(n_frames)
    for k in range(n_frames):
        tc = k / fps + lead - offset           # instante do audio que este quadro mostra
        c = int(round(tc * sr)) + win           # centro no vetor com margem
        a = c - win // 2
        if a < 0 or a + win > len(pad):
            db[k] = -120; continue
        seg = pad[a:a + win] * hann
        p = np.abs(np.fft.rfft(seg, nfft)) ** 2
        tot = p[b_sp].sum() + 1e-12
        db[k] = 10 * math.log10(tot / win + 1e-12)
        lo[k] = p[b_lo].sum() / tot
        hi[k] = p[b_hi].sum() / tot
        f1[k] = (p[b_f1] * freqs[b_f1]).sum() / (p[b_f1].sum() + 1e-12)
        f2[k] = (p[b_f2] * freqs[b_f2]).sum() / (p[b_f2].sum() + 1e-12)
    return db, lo, hi, f1, f2


def normalize(db, lo, hi, f1, f2):
    peak = np.percentile(db, 98)
    floor = peak - 42
    loud = np.clip((db - floor) / (peak - 6 - floor), 0, 1)
    voiced = np.clip((db - (peak - 30)) / 10, 0, 1)
    # F1/F2 so valem onde ha voz; fora disso ficam neutros (0,5)
    f1n = np.clip((f1 - 380) / (800 - 380), 0, 1)
    f2n = np.clip((f2 - 1150) / (1900 - 1150), 0, 1)
    f1n = 0.5 + (f1n - 0.5) * voiced
    f2n = 0.5 + (f2n - 0.5) * voiced
    fric = np.clip((hi - 0.08) / 0.45, 0, 1) * np.clip((db - floor) / 12, 0, 1)
    low = np.clip(lo, 0, 1)
    return loud, voiced, f1n, f2n, fric, low


def smooth_env(v, attack=0.65, release=0.4):
    """seguidor de envelope assimetrico (abre rapido, fecha um pouco mais devagar)"""
    out = np.zeros_like(v); s = 0.0
    for i, x in enumerate(v):
        s += (x - s) * (attack if x > s else release)
        out[i] = s
    return out


def blur3(v):
    p = np.concatenate([v[:1], v, v[-1:]])
    return 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]


# ── texto em portugues para visemas ─────────────────────────────────────────
# Formas: abertura maxima, esticada(+)/bico(-), dentes
SHAPE = {
    '.': (0.00, 0.0, 0.0),
    'A': (1.00, 0.15, 0.55),
    'E': (0.70, 0.60, 0.80),
    'I': (0.42, 0.95, 0.95),
    'O': (0.72, -0.70, 0.20),
    'U': (0.42, -1.00, 0.00),
    'M': (0.00, 0.05, 0.00),   # m, b, p: labios fechados
    'F': (0.12, 0.25, 1.00),   # f, v: labio de baixo encosta nos dentes
    'S': (0.20, 0.55, 1.00),   # s, z, x, ch, j: dentes quase juntos
    'L': (0.34, 0.20, 0.70),   # l, t, d, n, r, k, g: lingua trabalha, boca meio aberta
}
VOWEL = {'a': 'A', 'e': 'E', 'i': 'I', 'o': 'O', 'u': 'U'}


def strip_acc(ch):
    return unicodedata.normalize('NFD', ch)[0]


def word_visemes(word):
    """Aproximacao grafema a visema do portugues do Brasil (nao e fonetica completa)."""
    w = word.lower()
    out = []
    i, n = 0, len(w)
    nxt = lambda j: strip_acc(w[j]) if j < n else ''
    while i < n:
        ch = w[i]; b = strip_acc(ch); b2 = nxt(i + 1)
        if ch == 'ç':
            out.append('S'); i += 1; continue
        if b in VOWEL:
            v = VOWEL[b]
            last = i == n - 1 or (i == n - 2 and w[-1] == 's')
            if last and ch in 'eo' and n > 2:   # final atono: "time" = timi, "certo" = certu
                v = 'I' if ch == 'e' else 'U'
            out.append(v); i += 1; continue
        if b == 'y':
            out.append('I'); i += 1; continue
        if b == 'w':
            out.append('U'); i += 1; continue
        if b == 'h':
            i += 1; continue
        two = w[i:i + 2]
        if two in ('ch', 'sh', 'ss', 'sc', 'xc'):
            out.append('S'); i += 2; continue
        if two in ('lh', 'nh', 'rr'):
            out.append('L'); i += 2; continue
        if two in ('qu', 'gu') and nxt(i + 2) in ('e', 'i'):
            out.append('L'); i += 2; continue
        if b in 'mn':
            # m/n depois de vogal e antes de consoante ou no fim: vogal nasal, sem fechar
            prev_v = i > 0 and strip_acc(w[i - 1]) in VOWEL
            if prev_v and (b2 == '' or (b2 not in VOWEL and b2 != 'h')):
                i += 1; continue
            out.append('M' if b == 'm' else 'L'); i += 1; continue
        if b in 'pb':
            out.append('M'); i += 1; continue
        if b in 'fv':
            out.append('F'); i += 1; continue
        if b in 'szxj':
            out.append('S'); i += 1; continue
        if b == 'c':
            out.append('S' if b2 in ('e', 'i') else 'L'); i += 1; continue
        if b == 'g':
            out.append('S' if b2 in ('e', 'i') else 'L'); i += 1; continue
        if b.isalpha():
            out.append('L')
        i += 1
    return out


def text_units(text):
    """lista de estados: (visema, palavra_idx ou -1, opcional?)"""
    words = re.findall(r"[\wÀ-ÿ']+|[.,!?;:]", text)
    units, word_list = [('.', -1, True)], []
    for tok in words:
        if re.fullmatch(r'[.,!?;:]', tok):
            if units[-1][0] != '.':
                units.append(('.', -1, True))
            if word_list:
                word_list[-1]['w'] += tok
            continue
        wi = len(word_list)
        word_list.append({'w': tok})
        vs = word_visemes(tok) or ['A']
        if units[-1][0] != '.':
            units.append(('.', -1, True))      # pausa opcional entre palavras
        for v in vs:
            units.append((v, wi, False))
    if units[-1][0] != '.':
        units.append(('.', -1, True))
    return units, word_list


# alvo das medidas de audio para cada visema: (volume, F1, F2, chiado, graves)
AUDIO_T = {
    '.': (0.00, 0.5, 0.5, 0.0, 0.3),
    'A': (0.90, 0.95, 0.45, 0.0, 0.2),
    'E': (0.80, 0.55, 0.80, 0.0, 0.2),
    'I': (0.72, 0.15, 1.00, 0.1, 0.3),
    'O': (0.80, 0.55, 0.15, 0.0, 0.3),
    'U': (0.65, 0.15, 0.05, 0.0, 0.45),
    'M': (0.35, 0.20, 0.30, 0.0, 0.75),
    'F': (0.30, 0.50, 0.50, 0.7, 0.1),
    'S': (0.40, 0.50, 0.60, 1.0, 0.05),
    'L': (0.60, 0.40, 0.55, 0.1, 0.35),
}
W = np.array([3.0, 1.0, 1.2, 2.0, 0.8])
MIN_DUR = {'A': 3, 'E': 3, 'I': 2, 'O': 3, 'U': 2, 'M': 2, 'F': 2, 'S': 2, 'L': 1, '.': 1}


def align(units, feats, fps):
    """Viterbi esquerda-para-direita; cada visema vira uma corrente de MIN_DUR
    subestados; pausas '.' sao opcionais (podem ser puladas)."""
    loud, voiced, f1n, f2n, fric, low = feats
    X = np.stack([loud, f1n, f2n, fric, low], 1)            # (T, 5)
    T = len(loud)
    st_u, st_first, st_last = [], [], []
    for ui, (v, _, _) in enumerate(units):
        d = MIN_DUR[v]
        for j in range(d):
            st_u.append(ui); st_first.append(j == 0); st_last.append(j == d - 1)
    S = len(st_u)
    first_of = {}
    for s in range(S):
        if st_first[s]:
            first_of[st_u[s]] = s
    targ = np.array([AUDIO_T[units[u][0]] for u in st_u])  # (S, 5)
    em = (((X[:, None, :] - targ[None, :, :]) ** 2) * W).sum(2)  # (T, S)
    # silencio tem que ser silencio de verdade
    is_sil = np.array([units[u][0] == '.' for u in st_u])
    em[:, is_sil] += 6.0 * loud[:, None] ** 2
    INF = 1e18
    cost = np.full(S, INF); back = np.zeros((T, S), np.int32)
    cost[0] = em[0, 0]
    if units[0][2] and len(units) > 1:
        cost[first_of[1]] = em[0, first_of[1]]
    ADV = 0.15
    for t in range(1, T):
        new = np.full(S, INF); bp = np.zeros(S, np.int32)
        for s in range(S):
            best, arg = INF, s
            if st_last[s] and cost[s] < best:          # fica no mesmo (so no ultimo subestado)
                best, arg = cost[s], s
            if s > 0:
                c = cost[s - 1] + (ADV if st_last[s - 1] else 0)
                if c < best:
                    best, arg = c, s - 1
            if st_first[s]:                             # pula uma pausa opcional
                u = st_u[s]
                if u >= 2 and units[u - 1][2] and units[u - 1][0] == '.':
                    p = first_of[u - 1] - 1              # ultimo subestado antes da pausa
                    if p >= 0 and st_last[p] and cost[p] + ADV < best:
                        best, arg = cost[p] + ADV, p
            new[s] = best + em[t, s]; bp[s] = arg
        cost = new; back[t] = bp
    # termina no ultimo estado, ou no ultimo antes da pausa final opcional
    ends = [S - 1]
    if units[-1][2] and S >= 2:
        ends.append(first_of[len(units) - 1] - 1)
    s = min(ends, key=lambda e: cost[e])
    path = np.zeros(T, np.int32)
    for t in range(T - 1, -1, -1):
        path[t] = s; s = back[t, s]
    return np.array([st_u[s] for s in path])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('wav')
    ap.add_argument('--text', help='texto exato falado (portugues)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--js', help='grava tambem um .js com window.LIPSYNC[name]')
    ap.add_argument('--name', default='fala')
    ap.add_argument('--fps', type=int, default=60)
    ap.add_argument('--lead', type=float, default=0.03, help='boca adianta o som (s)')
    ap.add_argument('--offset', type=float, default=0.0, help='a voz comeca neste instante do video (s)')
    ap.add_argument('--duration', type=float, help='duracao do video (s); padrao = voz + offset')
    a = ap.parse_args()

    x, sr = read_wav(a.wav)
    dur = a.duration if a.duration else len(x) / sr + a.offset
    n = int(math.ceil(dur * a.fps)) + 1
    raw = features(x, sr, a.fps, n, a.lead, a.offset)
    loud, voiced, f1n, f2n, fric, low = normalize(*raw)
    env = smooth_env(loud)

    words = []
    if a.text:
        units, words = text_units(a.text)
        ui = align(units, (loud, voiced, f1n, f2n, fric, low), a.fps)
        vis = [units[u][0] for u in ui]
        for wi, w in enumerate(words):
            fr = np.where(np.array([units[u][1] for u in ui]) == wi)[0]
            w['t0'] = round(fr[0] / a.fps, 3) if len(fr) else None
            w['t1'] = round((fr[-1] + 1) / a.fps, 3) if len(fr) else None
    else:
        vis = []
        for k in range(n):
            if env[k] < 0.08:
                vis.append('.')
            elif fric[k] > 0.55:
                vis.append('S')
            elif f1n[k] > 0.62:
                vis.append('A')
            elif f2n[k] > 0.62:
                vis.append('I' if f1n[k] < 0.3 else 'E')
            elif f2n[k] < 0.35:
                vis.append('U' if f1n[k] < 0.3 else 'O')
            else:
                vis.append('E')

    op = np.zeros(n); wd = np.zeros(n); th = np.zeros(n)
    for k, v in enumerate(vis):
        mo, mw, mt = SHAPE[v]
        if v in 'M.':
            op[k] = 0.0
        elif v in 'FS':
            op[k] = mo * min(1.0, 0.4 + env[k])
        else:
            # volume manda na abertura; o visema limita e da o formato
            op[k] = min(mo, mo * 1.25 * env[k] ** 0.8)
        wd[k] = mw * (1 if v != '.' else 0)
        th[k] = mt * (0.3 + 0.7 * min(1, env[k] * 1.5)) if v not in '.M' else 0
    # coarticulacao: suaviza 1 quadro, mas mantem os labios colados no m/p/b
    op2, wd2, th2 = blur3(op), blur3(blur3(wd)), blur3(th)
    for k, v in enumerate(vis):
        if v == 'M':
            op2[k] = 0.0
    # sem saltos: a boca abre/fecha no maximo MAX_STEP por quadro. So REBAIXA os
    # vizinhos (ida e volta), entao o fechamento do m/p/b continua fechado e ganha rampa.
    MAX_STEP = 0.34
    for k in range(1, n):
        op2[k] = min(op2[k], op2[k - 1] + MAX_STEP)
    for k in range(n - 2, -1, -1):
        op2[k] = min(op2[k], op2[k + 1] + MAX_STEP)
    r = lambda arr: [round(float(v), 3) for v in arr]
    segs = []
    for k, v in enumerate(vis):
        if segs and segs[-1]['v'] == v:
            segs[-1]['t1'] = round((k + 1) / a.fps, 3)
        else:
            segs.append({'v': v, 't0': round(k / a.fps, 3), 't1': round((k + 1) / a.fps, 3)})
    out = {
        'fps': a.fps, 'frames': n, 'duration': round(dur, 3), 'lead': a.lead, 'offset': a.offset,
        'source': os.path.basename(a.wav), 'text': a.text or None,
        'open': r(op2), 'wide': r(wd2), 'teeth': r(th2), 'vis': ''.join(vis),
        'words': words, 'segs': segs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    if a.js:
        with open(a.js, 'w', encoding='utf-8') as f:
            f.write('// GERADO por tools/lipsync.py: nao editar a mao.\n')
            f.write('window.LIPSYNC = window.LIPSYNC || {};\n')
            f.write(f'window.LIPSYNC[{json.dumps(a.name)}] = ')
            json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
            f.write(';\n')
    spk = sum(1 for v in vis if v != '.')
    print(f'{a.out}: {n} quadros, {spk} com fala, visemas {len(segs)} trechos')
    if words:
        print('palavras:', ' '.join(f"{w['w']}@{w['t0']}" for w in words))


if __name__ == '__main__':
    main()
