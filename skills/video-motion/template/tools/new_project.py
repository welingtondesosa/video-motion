#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cria um projeto de video novo a partir deste template, pronto para comecar.

  python <template>/tools/new_project.py <pasta-destino> [--name anuncio-ia] [--duration 30] [--bpm 120] [--blank] [--force]

O que faz:
  - copia o template inteiro (motor, estilos da marca, fontes, logos, ferramentas, audio/synth.py)
  - transforma os exemplos em arquivos do projeto: roteiro.example.yaml -> roteiro.yaml,
    scenes/*.example.js -> scenes/*.js, audio/make_audio.example.py -> audio/make_audio.py
  - ajusta name/duration/bpm no roteiro, se passados (com --duration, a capa vai para duration - 0,3 s)
  - sem --blank: mantem o demo de 4 s (palavra + logo) como molde; com duracao maior o make_cues
    avisa que as cenas acabam antes. Troque as cenas do roteiro e apague scenes/10_exemplo.js
    (e a linha dele no index.html) quando escrever as suas.
  - --blank: projeto vazio: sem scenes/10_exemplo.js nem a linha no index.html, roteiro com uma
    cena so (cena1, 0 a duration), sem eventos nem palavras
  - roda tools/make_cues.py (cues.json e cues.js prontos: preview ja funciona)

Depois (dentro da pasta nova):
  python tools/make_cues.py                      roteiro -> cues.json/cues.js (sempre depois de mexer no roteiro)
  node tools/preview.mjs --range 0:4:0.25 --sheet   folha de contato para revisar
  python audio/make_audio.py                     trilha + efeitos, master -14 LUFS, conferencia dos cues
  python tools/check_text.py --dom               regras de texto da marca
  node tools/render.mjs --workers 6              video_master.mkv com motion blur
  node tools/assemble.mjs                        MP4 + capa em out/
  python tools/verify.py                         quadros, fps, loudness do MP4 e sincronia
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TEMPLATE = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'out', 'frames-preview', 'build', '__pycache__', 'node_modules', 'styleframes'}
SKIP_FILES = {'cues.json', 'cues.js', 'master.wav', 'mix.wav', 'loudness.txt', 'report.json', 'spectrogram.png', 'waveform.png'}


BLANK = '''scenes:                  # em ordem; cada uma com start/end ou bars; bg: escuro/marca/claro/blog
  - {{id: cena1, start: 0, end: {dur}, bg: escuro}}

events: {{}}               # so tempos (ex.: logo_in: "bar 3 + beat 1"); cada um vira referencia

words: []                # [{{text: "Atende.", at: palavra_in}}]

data:                    # livre (textos, cores); as cenas leem em CUES.data
  aviso: "Cenas e nomes ilustrativos"

numeros_ok: []           # numeros liberados no texto (so medidos ou autorizados por escrito)
'''


def ignore(d, names):
    return [n for n in names if n in SKIP_DIRS or n in SKIP_FILES]


def main():
    ap = argparse.ArgumentParser(description='Crea un proyecto de video a partir del template, con el kit de marca')
    ap.add_argument('dest')
    ap.add_argument('--name', help='slug del video (sale como <slug de la marca>-<name>.mp4)')
    ap.add_argument('--kit', help='carpeta del kit de marca (marca.yaml + archivos). Por defecto: .claude/video-marca del directorio actual')
    ap.add_argument('--duration', type=float)
    ap.add_argument('--bpm', type=float)
    ap.add_argument('--blank', action='store_true', help='sem as cenas de exemplo (roteiro com uma cena so)')
    ap.add_argument('--force', action='store_true', help='apaga a pasta destino se ja existir')
    a = ap.parse_args()
    dest = Path(a.dest).resolve()
    if dest == TEMPLATE or TEMPLATE in dest.parents:
        sys.exit('o destino nao pode ficar dentro do template')
    if dest.exists():
        if not a.force:
            sys.exit(f'{dest} ja existe (use --force para recriar)')
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE, dest, ignore=ignore)

    renames = [(dest / 'roteiro.example.yaml', dest / 'roteiro.yaml'),
               (dest / 'audio' / 'make_audio.example.py', dest / 'audio' / 'make_audio.py')]
    renames += [(p, p.with_name(p.name.replace('.example.js', '.js'))) for p in (dest / 'scenes').glob('*.example.js')]
    for src, dst in renames:
        if src.exists():
            src.rename(dst)
    (dest / 'tools' / 'new_project.py').unlink(missing_ok=True)   # o gerador fica so no template

    # KIT DE MARCA: copia a brand/ y genera brand.css + brand.js
    kit = Path(a.kit).resolve() if a.kit else (Path.cwd() / '.claude' / 'video-marca')
    if not (kit / 'marca.yaml').exists():
        sys.exit(f'ERRO: no encontre el kit de marca en {kit} (falta marca.yaml). Use --kit <carpeta>.')
    shutil.copytree(kit, dest / 'brand', dirs_exist_ok=True)
    pb = subprocess.run([sys.executable, str(dest / 'tools' / 'apply_brand.py')], capture_output=True, text=True, encoding='utf-8')
    print(pb.stdout.strip() or pb.stderr.strip())
    if pb.returncode != 0:
        sys.exit('ERRO: apply_brand fallo (ver arriba)')

    rot = dest / 'roteiro.yaml'
    txt = rot.read_text(encoding='utf-8')
    name = a.name or dest.name
    name = re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-') or 'video'
    txt = re.sub(r'(?m)^name:[ \t]*[^\s#]+', f'name: {name}', txt, count=1)
    if a.duration:
        txt = re.sub(r'(?m)^duration:[ \t]*[^\s#]+', f'duration: {a.duration:g}', txt, count=1)
        txt = re.sub(r'(?m)^cover:[ \t]*[^\s#]+', f'cover: {max(0.0, a.duration - 0.3):g}', txt, count=1)
    if a.bpm:
        txt = re.sub(r'(?m)^bpm:[ \t]*[^\s#]+', f'bpm: {a.bpm:g}', txt, count=1)
    if a.blank:
        dur = a.duration or 4
        txt = txt[:txt.index('scenes:')] + BLANK.format(dur=f'{dur:g}')
        (dest / 'scenes' / '10_exemplo.js').unlink(missing_ok=True)
        idx = dest / 'index.html'
        idx.write_text(re.sub(r'[ \t]*<script src="scenes/10_exemplo\.js"></script>\r?\n', '', idx.read_text(encoding='utf-8')),
                       encoding='utf-8')
    # textos del demo y aviso en el idioma de la marca (del kit)
    try:
        import yaml
        M = yaml.safe_load((kit / 'marca.yaml').read_text(encoding='utf-8')) or {}
        lang = M.get('idioma', 'es')
        av = ((M.get('reglas') or {}).get('aviso_encenado'))
        av = av.get(lang) if isinstance(av, dict) else av
        if av:
            txt = re.sub(r'(?m)^(\s*aviso:\s*).*$', lambda m: f'{m.group(1)}"{av}"', txt, count=1)
        tag = M.get('tagline')
        tag = tag.get(lang) if isinstance(tag, dict) else tag
        palabra = (tag or M.get('nombre') or 'Hola').split(',')[0].split('.')[0].strip() + '.'
        txt = txt.replace('"Atende."', f'"{palabra}"')
    except Exception as e:
        print('AVISO: no pude leer textos del kit:', e)
    rot.write_text(txt, encoding='utf-8')

    p = subprocess.run([sys.executable, str(dest / 'tools' / 'make_cues.py')], capture_output=True, text=True, encoding='utf-8')
    print(p.stdout.strip())
    if p.returncode != 0:
        print(p.stderr.strip())
        print('AVISO: make_cues falhou; ajuste o roteiro.yaml e rode de novo')
    print(f'\nprojeto criado em {dest}')
    print(__doc__[__doc__.index('Depois'):].rstrip())


if __name__ == '__main__':
    main()
