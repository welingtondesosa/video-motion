#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Varre o texto que o cliente vai ver e acusa o que as regras da marca proibem:
  - travessao (U+2014), meia-risca (U+2013) e parentes (U+2012, U+2015), tambem como &mdash; / \\u2014
    (o kit libera com reglas.permitir_guiones: true)
  - emoji (o kit libera com reglas.permitir_emoji: true)
  - marcas proibidas: base de fornecedores (OpenAI, Amazon, Supabase, Stripe...) + as do KIT
    (brand/marca.yaml -> reglas.prohibidas: concorrentes e fornecedores próprios da marca)
  - numeros: todo digito em texto de tela precisa estar liberado em `numeros_ok` no roteiro
    (so numero medido, e de cliente so com autorizacao por escrito)

Onde olha:
  estatico: literais de string dos scenes/*.js (sem comentarios), index.html e os textos do roteiro
            (words, data, qualquer string fora de events); nos lib*.js so travessao, emoji e marca
            (numero em biblioteca e codigo; o que ela escreve na tela o --dom pega)
  --dom     tambem renderiza a pagina de 0,1 em 0,1 s e confere o texto VISIVEL de verdade
            (pega texto montado em tempo de execucao, ex.: contadores)

Uso:  python tools/check_text.py [--dom] [--step 0.1]
Sai com codigo 1 se achar algo. Marca extra: `marcas_extra: [...]` no roteiro.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent

# Base para cualquier marca: proveedores de infraestructura e IA que nunca van en pantalla.
# Cada KIT suma los suyos (competidores, proveedores propios) en brand/marca.yaml -> reglas.prohibidas.
BRANDS = [
    'Amazon', 'AWS', 'OpenAI', 'ChatGPT', 'GPT-4', 'GPT', 'Groq', 'Supabase', 'Cloudflare', 'Stripe', 'Anthropic',
    'Claude', 'Gemini', 'Twilio', 'Vercel', 'Netlify', 'Firebase', 'Google Cloud', 'Azure', 'Whisper', 'ElevenLabs',
    'Replicate', 'Resend', 'Postmark', 'Midjourney',
]


def kit_rules():
    f = ROOT / 'brand' / 'marca.yaml'
    if not f.exists():
        return {}
    try:
        import yaml
        m = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    return m.get('reglas') or {}


def kit_brands():
    return list(kit_rules().get('prohibidas') or [])


# Travessao e emoji: proibidos por padrao (texto limpo, sem cara de texto gerado).
# O kit pode liberar: reglas.permitir_guiones: true / reglas.permitir_emoji: true
ALLOW_DASHES = bool(kit_rules().get('permitir_guiones'))
ALLOW_EMOJI = bool(kit_rules().get('permitir_emoji'))
DASHES = re.compile(r'[‒–—―]|&mdash;|&ndash;|\\u201[2345]|&#821[12];')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF'
                   '\U0000FE0F\U0000200D\U00002300-\U000023FF\U0001F900-\U0001F9FF←-⇿✅✨]')
CODE_HINT = re.compile(r'(\d(px|deg|rem|em|vh|vw|ms|fr)\b)|#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?|var|url|calc|translate3?d?|translate[XY]|'
                       r'scale[XY]?|rotate|blur|linear-gradient|radial-gradient|cubic-bezier|drop-shadow|inset|repeat|minmax)\(')
FILE_LIKE = re.compile(r'^[\w\-./:@]+\.(png|svg|jpe?g|webp|gif|js|mjs|css|json|mp4|webm|woff2?|ttf|html|wav)$', re.I)


def js_strings(src):
    """Literais de string de um JS (sem comentarios). Template: ${...} vira espaco."""
    out, i, n = [], 0, len(src)
    line = 1
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1
        if src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            line += src[i:j].count('\n') if j > 0 else 0
            i = n if j < 0 else j + 2
            continue
        if c in '\'"`':
            q, j, buf, depth = c, i + 1, [], 0
            start_line = line
            while j < n:
                d = src[j]
                if d == '\\':
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if q == '`' and src.startswith('${', j):
                    depth, k = 1, j + 2
                    while k < n and depth:
                        depth += {'{': 1, '}': -1}.get(src[k], 0)
                        k += 1
                    buf.append(' ')
                    j = k
                    continue
                if d == q:
                    break
                if d == '\n':
                    line += 1
                    if q != '`':
                        break
                buf.append(d)
                j += 1
            out.append((start_line, ''.join(buf)))
            i = j + 1
            continue
        # regex literal simples: pula /.../ depois de ( , = : [ ! & | ? { } ; return
        i += 1
    return out


def strip_tags(s):
    return re.sub(r'<[^>]*>', ' ', s)


def looks_code(s):
    t = s.strip()
    if not t:
        return True
    if re.fullmatch(r'([-+]?[\d.]+(e-?\d+)?(%|px|deg|em|rem|s|ms|vh|vw|fr)?\s*)+', t):
        return True  # valores de estilo ('0', '1.5', '50% 60%', '0 12px')
    if CODE_HINT.search(t) or FILE_LIKE.match(t) or re.match(r'^(https?:)?//', t):
        return True
    if re.fullmatch(r'[A-Za-z_$][\w$-]*', t):
        return True  # identificador/atributo ('x1', 'stop-color')
    if re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz\d\s.,-]+', t) and re.search(r'[MmLlCcQqAaZz]', t):
        return True  # dados de caminho SVG ('M-8 26 Q2 36 14 30')
    return False


def load_roteiro():
    for n in ('roteiro.yaml', 'roteiro.yml', 'roteiro.json'):
        p = ROOT / n
        if p.exists():
            if p.suffix == '.json':
                return p, json.loads(p.read_text(encoding='utf-8'))
            import yaml
            return p, yaml.safe_load(p.read_text(encoding='utf-8'))
    return None, {}


# chaves que sao TEMPO, id ou config (nunca aparecem na tela): nao entram na conferencia de texto
SKIP_TOP = ('events', 'numeros_ok', 'marcas_extra', 'name')
SKIP_WORD = ('at', 'out')                                      # words[].at / .out: "bar 2", "palavra1_in"
SKIP_SCENE = ('id', 'start', 'end', 'bars', 'bg', 'wipe')     # scenes[]: tempos, id e fundo


def walk_strings(v, path=''):
    if isinstance(v, dict):
        for k, x in v.items():
            if path == '' and k in SKIP_TOP:
                continue
            if re.fullmatch(r'words\[\d+\]', path) and k in SKIP_WORD:
                continue
            if re.fullmatch(r'scenes\[\d+\]', path) and k in SKIP_SCENE:
                continue
            yield from walk_strings(x, f'{path}.{k}' if path else k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from walk_strings(x, f'{path}[{i}]')
    elif isinstance(v, str):
        yield path, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dom', action='store_true', help='confere tambem o texto visivel renderizado')
    ap.add_argument('--step', type=float, default=0.1)
    a = ap.parse_args()
    rpath, rot = load_roteiro()
    allow = sorted([str(x) for x in (rot.get('numeros_ok') or [])], key=len, reverse=True)
    brands = BRANDS + kit_brands() + list(rot.get('marcas_extra') or [])
    brand_re = re.compile(r'(?<![\w@.-])(' + '|'.join(re.escape(b) for b in sorted(brands, key=len, reverse=True)) + r')(?![\w-])', re.I)
    found = []

    def scan(where, text, human=None, numbers=True):
        t = strip_tags(text)
        if not ALLOW_DASHES and DASHES.search(text):
            found.append((where, 'TRAVESSAO/MEIA-RISCA', text))
        if not ALLOW_EMOJI and EMOJI.search(t):
            found.append((where, 'EMOJI', text))
        ms = sorted({m.group(1) for m in brand_re.finditer(t)})
        if ms:
            found.append((where, 'MARCA PROIBIDA ' + ', '.join(f'"{b}"' for b in ms), text))
        if numbers and re.search(r'\d', t):
            is_human = (not looks_code(t)) if human is None else human
            if is_human:
                rest = t
                for ok in allow:
                    rest = rest.replace(ok, ' ')
                if re.search(r'\d', rest):
                    found.append((where, 'NUMERO (liberar em numeros_ok so se for medido/autorizado)', text))

    files = sorted(p for p in (ROOT / 'scenes').glob('*.js') if not p.name.endswith('.example.js')) + sorted(ROOT.glob('lib*.js'))
    for f in files:
        is_lib = f.parent == ROOT   # bibliotecas: numero em string e codigo; o texto delas na tela o --dom confere
        for ln, s in js_strings(f.read_text(encoding='utf-8')):
            scan(f'{f.relative_to(ROOT)}:{ln}', s, numbers=not is_lib)
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    for m in re.finditer(r'<title>(.*?)</title>', html, re.S):
        scan('index.html <title>', m.group(1))
    if rpath:
        for p, s in walk_strings(rot):
            scan(f'{rpath.name} {p}', s, human=True)

    n_dom = 0
    if a.dom:
        p = subprocess.run(['node', str(ROOT / 'tools' / 'dom_text.mjs'), '--step', str(a.step)], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        if p.returncode != 0:
            print(p.stdout, p.stderr)
            sys.exit('falha no dom_text.mjs')
        dom = json.loads(p.stdout.strip().splitlines()[-1])
        n_dom = len(dom['texts'])
        for item in dom['texts']:
            scan(f'tela {item["t"]:.2f} s', item['text'], human=True)
        for e in dom['errors']:
            found.append(('pagina', 'ERRO JS', e))

    print(f'check_text: {len(files)} arquivos JS, roteiro {rpath.name if rpath else "-"}'
          + (f', {n_dom} textos visiveis distintos na tela' if a.dom else '') + f'; numeros liberados: {allow or "nenhum"}')
    for where, kind, text in found:
        print(f'  {kind}: {where}: {text.strip()[:120]!r}')
    print('TEXTO OK' if not found else f'{len(found)} problema(s)')
    sys.exit(1 if found else 0)


if __name__ == '__main__':
    main()
