#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Folha de tempos UNICA do video. Cenas (JS) e audio (Python) leem o que este script
gera, entao um som sempre cai no quadro do evento.

Le um roteiro simples (roteiro.yaml ou roteiro.json na raiz do projeto) e gera:
  cues.json   lido pelo audio (Python) e pelas ferramentas
  cues.js     window.CUES = {...}, lido pelas cenas (index.html)

Uso:
  python tools/make_cues.py                 (usa roteiro.yaml, ou roteiro.json)
  python tools/make_cues.py outro.yaml
  python tools/make_cues.py --strict-grid   (erro se um evento nao cair na grade de semicolcheias)

FORMATO DO ROTEIRO (YAML; o mesmo em JSON):

  name: anuncio-dores          # vira o nome do MP4 (<slug da marca>-<name>.mp4)
  duration: 30                 # segundos (obrigatorio)
  fps: 60                      # opcional (60)
  bpm: 120                     # opcional: liga a grade musical
  offset: 0                    # opcional: segundo em que cai o tempo 0 da musica
  beats_per_bar: 4             # opcional (4)
  cover: 29.5                  # opcional: segundo do quadro da capa
  scenes:                      # em ordem; cada uma com start/end OU bars
    - {id: gancho, start: 0, end: 2.5}
    - {id: virada, bars: [1, 3]}          # do compasso 1 ao 3 (exclusivo); precisa de bpm
    - {id: final,  start: virada.end, end: 30, bg: claro}   # bg: escuro/marca/claro/blog
                               # (claro entra por circulo; centro opcional wipe: [540, 1150])
  words:                       # palavras na tela (a cena decide como animar)
    - {text: "Atende.", at: "bar 2"}
  events:                      # QUALQUER estrutura: tudo aqui dentro e tempo
    logo_in: "bar 3 + beat 1"
    pops: ["beat 0", "beat 2", 3.25]
    card: {enter: "gancho.start + 0.2", land: "8th 5"}
  data: {...}                  # livre, copiado sem mexer (textos, nomes, cores; aviso, aviso_y)
  numeros_ok: ["exemplo.com"] # lido pelo tools/check_text.py

EXPRESSOES DE TEMPO (resultado em segundos):
  2.5                numero = segundos
  "bar 3"            inicio do compasso 3 (0 = primeiro), a partir do offset
  "beat 5"           tempo 5 (seminima)
  "8th 3" / "16th 7" colcheia / semicolcheia
  "gancho.start"     inicio/fim de uma cena ja definida (tambem "gancho.end")
  "evento.x"         outro evento ja resolvido (ex.: "card.enter + 0.1")
  somas e subtracoes: "bar 2 + beat 1 - 0.05"
    (o 1o termo e um instante; os seguintes sao duracoes: "beat 1" depois do + vale 1 tempo)
  events so guarda TEMPOS (numeros, expressoes, listas e dicts deles); o resto vai em data.
  Toda folha vira referencia: "events.card.enter" ou so "card.enter" / "logo_in" / "pops[1]".
  dict: {bar: 2, beat: 1, s: -0.05}  (chaves bar, beat, 8th, 16th, s)

AVISOS (nao param o script): cenas que nao encostam, ultima cena antes do fim, capa fora das
cenas, evento a menos de 0,2 s de uma troca de fundo (o verify.py nao acharia), evento fora da
grade, cena fora do index.html. ERRO (sai com codigo 1): cena do index.html com sintaxe quebrada.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent
BG_GUARD = 0.2   # nenhum evento a menos disso de uma fronteira com troca de fundo


# ---------------------------------------------------------------- grade musical
class Grid:
    """Grade musical. Tudo em segundos a partir de `offset` (tempo 0 da musica)."""

    def __init__(self, bpm, offset=0.0, beats_per_bar=4):
        self.bpm = float(bpm)
        self.offset = float(offset)
        self.bpb = int(beats_per_bar)
        self.beat_s = 60.0 / self.bpm          # seminima
        self.bar_s = self.bpb * self.beat_s    # compasso

    def beat(self, n):
        return self.offset + n * self.beat_s

    def eighth(self, n):
        return self.offset + n * self.beat_s / 2

    def sixteenth(self, n):
        return self.offset + n * self.beat_s / 4

    def bar(self, n, beat=0.0):
        return self.offset + n * self.bar_s + beat * self.beat_s

    def snap(self, t, div=4):
        """Tempo mais proximo na grade de 1/div de tempo (div=4: semicolcheia)."""
        q = self.beat_s / div
        return self.offset + round((t - self.offset) / q) * q

    def on_grid(self, t, div=4, tol=1e-4):
        return abs(self.snap(t, div) - t) < tol

    def where(self, t):
        """'compasso.tempo' legivel (base 0), ex.: 3.2+0.125."""
        b = (t - self.offset) / self.beat_s
        bar_i = math.floor(b / self.bpb)
        beat_f = b - bar_i * self.bpb
        return f'{bar_i}.{beat_f:g}'


# ---------------------------------------------------------------- expressoes de tempo
UNIT = {'bar': 'bar', 'bars': 'bar', 'compasso': 'bar', 'beat': 'beat', 'beats': 'beat', 'tempo': 'beat',
        '8th': '8th', 'colcheia': '8th', '16th': '16th', 'semicolcheia': '16th', 's': 's', 'sec': 's'}
TERM = re.compile(r'\s*([+-])?\s*(?:(bars?|beats?|compasso|tempo|8th|colcheia|16th|semicolcheia)\s+(-?\d+(?:\.\d+)?)'
                  r'|(-?\d+(?:\.\d+)?)\s*(?:s|sec)?(?![\w.])'
                  r'|([A-Za-z_]\w*(?:\[\d+\])*(?:\.\w+(?:\[\d+\])*)*))\s*')


class Resolver:
    def __init__(self, grid, fps):
        self.grid = grid
        self.fps = fps
        self.refs = {}          # 'cena.start' -> s, 'evento.x' -> s

    def unit(self, u, n):
        if u in ('bar', 'beat', '8th', '16th') and self.grid is None:
            raise ValueError(f'"{u} {n}" precisa de bpm no roteiro')
        return {'bar': lambda: self.grid.bar(n), 'beat': lambda: self.grid.beat(n),
                '8th': lambda: self.grid.eighth(n), '16th': lambda: self.grid.sixteenth(n),
                's': lambda: float(n)}[u]()

    def expr(self, s, where):
        s = s.strip()
        pos, total, first = 0, 0.0, True
        while pos < len(s):
            m = TERM.match(s, pos)
            if not m or m.end() == pos:
                raise ValueError(f'{where}: nao entendi "{s}" perto de "{s[pos:]}"')
            sign = -1.0 if m.group(1) == '-' else 1.0
            if not first and m.group(1) is None:
                raise ValueError(f'{where}: falta + ou - em "{s}"')
            if m.group(2):
                u = UNIT[m.group(2)]
                n = float(m.group(3))
                # compasso/tempo sao relativos ao tempo 0 da musica: so o offset entra uma vez
                v = self.unit(u, n) - (self.grid.offset if not first else 0.0)
            elif m.group(4) is not None:
                v = float(m.group(4))
            else:
                ref = m.group(5)
                if ref not in self.refs:
                    raise ValueError(f'{where}: referencia "{ref}" nao existe (ainda). Disponiveis: '
                                     + ', '.join(sorted(self.refs)[:40]))
                v = self.refs[ref]
            total += sign * v
            first = False
            pos = m.end()
        return total

    def time(self, v, where):
        if isinstance(v, bool):
            raise ValueError(f'{where}: booleano nao e tempo')
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return self.expr(v, where)
        if isinstance(v, dict) and v and set(v) <= {'bar', 'beat', '8th', '16th', 's'}:
            if self.grid is None and set(v) - {'s'}:
                raise ValueError(f'{where}: {v} precisa de bpm')
            t = self.grid.offset if self.grid else 0.0
            if self.grid:
                t += v.get('bar', 0) * self.grid.bar_s + v.get('beat', 0) * self.grid.beat_s
                t += v.get('8th', 0) * self.grid.beat_s / 2 + v.get('16th', 0) * self.grid.beat_s / 4
            return t + float(v.get('s', 0))
        raise ValueError(f'{where}: tempo invalido {v!r}')

    def tree(self, v, path):
        """Resolve recursivamente (events). Registra cada folha como referencia 'events.caminho'."""
        if isinstance(v, dict) and not (v and set(v) <= {'bar', 'beat', '8th', '16th', 's'}):
            return {k: self.tree(x, f'{path}.{k}') for k, x in v.items()}
        if isinstance(v, list):
            return [self.tree(x, f'{path}[{i}]') for i, x in enumerate(v)]
        t = round(self.time(v, path), 6)
        short = path.split('.', 1)[1] if '.' in path else path
        self.refs[path] = t
        self.refs[short] = t
        return t


def flatten(v, path=''):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from flatten(x, f'{path}.{k}' if path else k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from flatten(x, f'{path}[{i}]')
    else:
        yield path, v


def load_roteiro(path):
    txt = path.read_text(encoding='utf-8')
    if path.suffix.lower() in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            sys.exit('instale PyYAML (pip install pyyaml) ou use roteiro.json')
        return yaml.safe_load(txt)
    return json.loads(txt)


def build(rot, strict_grid=False):
    warn = []
    dur = float(rot['duration'])
    fps = int(rot.get('fps', 60))
    grid = Grid(rot['bpm'], rot.get('offset', 0.0), rot.get('beats_per_bar', 4)) if rot.get('bpm') else None
    R = Resolver(grid, fps)

    scenes = []
    for i, sc in enumerate(rot.get('scenes') or []):
        sid = sc['id']
        if 'bars' in sc:
            if grid is None:
                raise ValueError(f'cena {sid}: bars precisa de bpm')
            a, b = grid.bar(sc['bars'][0]), grid.bar(sc['bars'][1])
        else:
            a = R.time(sc['start'], f'scenes.{sid}.start')
            b = R.time(sc['end'], f'scenes.{sid}.end')
        a, b = round(a, 6), round(b, 6)
        if b <= a:
            raise ValueError(f'cena {sid}: fim {b} <= inicio {a}')
        R.refs[f'{sid}.start'], R.refs[f'{sid}.end'] = a, b
        out = {'id': sid, 'start': a, 'end': b}
        for k, v in sc.items():
            if k not in ('id', 'start', 'end'):
                out[k] = v
        scenes.append(out)
    ids = [s['id'] for s in scenes]
    if len(set(ids)) != len(ids):
        raise ValueError('ids de cena repetidos')
    for s0, s1 in zip(scenes, scenes[1:]):
        if abs(s1['start'] - s0['end']) > 1e-6:
            warn.append(f'cenas {s0["id"]} e {s1["id"]} nao encostam ({s0["end"]} -> {s1["start"]})')
    if scenes and scenes[-1]['end'] > dur + 1e-6:
        warn.append(f'cena {scenes[-1]["id"]} passa da duracao ({scenes[-1]["end"]} > {dur})')
    if scenes and scenes[-1]['end'] < dur - 1e-6:
        warn.append(f'a ultima cena ({scenes[-1]["id"]}) termina em {scenes[-1]["end"]} s e o video tem {dur} s: '
                    f'de {scenes[-1]["end"]} a {dur} s so aparece o fundo (estenda as cenas ou reduza duration)')
    if 'cover' in rot and not (0 <= float(rot['cover']) < dur):
        warn.append(f'cover = {rot["cover"]} s fora do video (0 a {dur})')
    elif 'cover' in rot and scenes and float(rot['cover']) >= scenes[-1]['end']:
        warn.append(f'cover = {rot["cover"]} s cai depois da ultima cena (quadro so com fundo)')
    # fronteiras com troca de fundo: o cruzamento muda o quadro inteiro por 0,3 s
    bg_edges = [(s1['start'], s0['id'], s1['id']) for s0, s1 in zip(scenes, scenes[1:])
                if (s0.get('bg') or 'escuro') != (s1.get('bg') or 'escuro')]

    events = R.tree(rot.get('events') or {}, 'events')

    words = []
    for i, w in enumerate(rot.get('words') or []):
        w = dict(w)
        w['at'] = round(R.time(w['at'], f'words[{i}].at'), 6)
        if 'out' in w:
            w['out'] = round(R.time(w['out'], f'words[{i}].out'), 6)
        words.append(w)

    # linha do tempo plana (audio, conferencia de sincronia, relatorios)
    timeline = [{'name': f'events.{p}', 't': t} for p, t in flatten(events)]
    timeline += [{'name': f'words[{i}] {w["text"]}', 't': w['at']} for i, w in enumerate(words)]
    timeline.sort(key=lambda e: e['t'])
    for e in timeline:
        for tb, a_id, b_id in bg_edges:
            if abs(e['t'] - tb) < BG_GUARD - 1e-9:
                warn.append(f'{e["name"]} = {e["t"]} s a menos de {BG_GUARD} s da troca de fundo {a_id} -> {b_id} ({tb} s): '
                            'a troca muda o quadro inteiro e o verify.py nao acha o evento; afaste o evento')
        if not (0 <= e['t'] <= dur):
            warn.append(f'{e["name"]} = {e["t"]} s fora do video (0 a {dur})')
        if grid and not grid.on_grid(e['t']):
            msg = f'{e["name"]} = {e["t"]} s fora da grade de semicolcheias (mais perto: {grid.snap(e["t"]):.4f})'
            if strict_grid:
                raise ValueError(msg)
            warn.append(msg)

    cues = {
        'name': rot.get('name', 'video'),
        'duration': dur,
        'fps': fps,
        'frames': int(round(dur * fps)),
        'cover': float(rot['cover']) if 'cover' in rot else round(max(0.0, dur - 0.3), 3),
    }
    if grid:
        nb = int(math.floor((dur - grid.offset) / grid.beat_s + 1e-9)) + 1
        cues.update(bpm=grid.bpm, offset=grid.offset, beats_per_bar=grid.bpb, beat=round(grid.beat_s, 6), bar=round(grid.bar_s, 6),
                    beats=[round(grid.beat(n), 6) for n in range(nb) if grid.beat(n) >= 0])
    cues['scenes'] = scenes
    cues['words'] = words
    cues['events'] = events
    cues['timeline'] = timeline
    for k, v in rot.items():
        if k not in cues and k not in ('bpm', 'offset', 'beats_per_bar', 'scenes', 'words', 'events'):
            cues[k] = v
    return cues, warn, grid


def write(cues, root=ROOT):
    (root / 'cues.json').write_text(json.dumps(cues, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'cues.js').write_text('// GERADO por tools/make_cues.py a partir do roteiro: nao editar a mao.\nwindow.CUES = '
                                  + json.dumps(cues, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')


def check_index(root=ROOT):
    """Avisa cena em scenes/ que o index.html nao carrega (e vice-versa)."""
    out = []
    idx = root / 'index.html'
    if not idx.exists():
        return ['index.html nao existe']
    html = idx.read_text(encoding='utf-8')
    refs = set(re.findall(r'src="(scenes/[^"]+\.js)"', html))
    files = {f'scenes/{p.name}' for p in (root / 'scenes').glob('*.js') if not p.name.endswith('.example.js')}
    for f in sorted(files - refs):
        out.append(f'{f} existe mas o index.html nao carrega')
    for f in sorted(refs - files):
        out.append(f'index.html carrega {f}, que nao existe')
    # sintaxe de cada cena (arquivo meio editado quebra o render longe do problema)
    for f in sorted(files & refs):
        try:
            p = subprocess.run(['node', '--check', str(root / f)], capture_output=True, text=True, encoding='utf-8', errors='replace')
        except FileNotFoundError:
            break
        if p.returncode != 0:
            msg = next((l for l in p.stderr.splitlines() if 'Error' in l), p.stderr.strip()[:200])
            out.append(f'{f} tem erro de sintaxe: {msg}')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('roteiro', nargs='?')
    ap.add_argument('--strict-grid', action='store_true')
    a = ap.parse_args()
    if a.roteiro:
        path = Path(a.roteiro).resolve()
    else:
        path = next((ROOT / n for n in ('roteiro.yaml', 'roteiro.yml', 'roteiro.json') if (ROOT / n).exists()), None)
        if path is None:
            sys.exit('nao achei roteiro.yaml nem roteiro.json na raiz do projeto')
    try:
        cues, warn, grid = build(load_roteiro(path), a.strict_grid)
    except (ValueError, KeyError) as e:
        sys.exit(f'ERRO no roteiro {path.name}: {e}')
    write(cues)
    warn += check_index()
    print(f'cues.json + cues.js: {cues["name"]}, {cues["duration"]} s, {cues["fps"]} fps, {cues["frames"]} quadros'
          + (f', {grid.bpm:g} bpm (tempo {grid.beat_s:.4f} s, compasso {grid.bar_s:.4f} s)' if grid else ''))
    for s in cues['scenes']:
        print(f'  cena {s["id"]:14s} {s["start"]:8.3f} a {s["end"]:8.3f} s' + (f'  (compasso {grid.where(s["start"])})' if grid else ''))
    for e in cues['timeline']:
        print(f'  {e["t"]:8.3f} s  {e["name"]}' + (f'  [{grid.where(e["t"])}]' if grid else ''))
    for w in warn:
        print(('ERRO: ' if 'erro de sintaxe' in w else 'AVISO: ') + w)
    if any('erro de sintaxe' in w for w in warn):
        sys.exit(1)   # cues.json foi gravado, mas nao siga com cena quebrada


if __name__ == '__main__':
    main()
