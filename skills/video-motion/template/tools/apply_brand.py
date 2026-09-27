#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica el KIT DE MARCA del proyecto (brand/marca.yaml + archivos) al motor.

Genera:
  brand/brand.css   fuentes (VDisplay = titulos, VTexto = texto, VSerif = editorial opcional)
                    y variables de color (:root) que usan styles.css, lib.js y las escenas
  brand/brand.js    window.BRAND = {...marca.yaml, colores derivados}: las escenas leen de aca

Uso:  python tools/apply_brand.py            (lo corre tools/new_project.py --kit solo)

Formato de brand/marca.yaml: ver references/kit-de-marca.md de la skill (y el ejemplo kit-ejemplo/).
Las rutas de archivos del kit son relativas a brand/.
"""
import colorsys
import json
import sys
from pathlib import Path

import yaml

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / 'brand'


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb2hex(r, g, b):
    return '#%02X%02X%02X' % tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))


def tone(h, l_target, s_mul=1.0):
    """Mismo matiz del color con otra luminosidad (0..1): arma la escala de tonos de la marca."""
    r, g, b = hex2rgb(h)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return rgb2hex(*colorsys.hls_to_rgb(hh, l_target, min(1.0, ss * s_mul)))


def rgba(h, a):
    r, g, b = hex2rgb(h)
    return f'rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {a})'


FMT = {'.woff2': 'woff2', '.woff': 'woff', '.ttf': 'truetype', '.otf': 'opentype'}


def font_faces(alias, spec):
    """spec: {familia, archivos: {peso: ruta}}. peso puede ser "400 700" (fuente variable)."""
    out = []
    for peso, ruta in (spec.get('archivos') or {}).items():
        p = BRAND / ruta
        if not p.exists():
            sys.exit(f'ERRO: fuente no encontrada: brand/{ruta}')
        out.append(f"@font-face {{ font-family: '{alias}'; font-weight: {peso}; font-display: block; "
                   f"src: url('{ruta}') format('{FMT.get(p.suffix.lower(), 'truetype')}'); }}")
    return out


def main():
    f = BRAND / 'marca.yaml'
    if not f.exists():
        sys.exit('ERRO: falta brand/marca.yaml (el kit de marca). Cree el proyecto con --kit <carpeta del kit>.')
    M = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
    C = M.get('colores') or {}
    for k in ('primario', 'fondo_oscuro', 'fondo_claro', 'tinta'):
        if k not in C:
            sys.exit(f'ERRO: marca.yaml sin colores.{k}')
    P = C['primario']
    S2 = C.get('secundario', P)
    grad = C.get('degradado') or [P, S2]
    deriv = {
        # escala del primario (el motor usaba los nombres g950..g400 para la marca: se mantienen)
        'g950': tone(P, 0.12), 'g900': tone(P, 0.16), 'g800': tone(P, 0.24), 'g750': tone(P, 0.28),
        'g700': tone(P, 0.34), 'g600': P, 'g400': tone(P, 0.66),
        'l50': C['fondo_claro'], 'l100': C.get('fondo_claro_2', tone(P, 0.94, 0.6)), 'l200': tone(P, 0.86, 0.7),
    }
    fuentes = M.get('fuentes') or {}
    css = ['/* GENERADO por tools/apply_brand.py a partir de brand/marca.yaml: no editar a mano. */']
    if 'titulos' in fuentes:
        css += font_faces('VDisplay', fuentes['titulos'])
    if 'texto' in fuentes:
        css += font_faces('VTexto', fuentes['texto'])
    if 'editorial' in fuentes:
        css += font_faces('VSerif', fuentes['editorial'])
    root = {
        'black': C['fondo_oscuro'], 'ink': C['tinta'],
        'grad-logo': f"linear-gradient(90deg, {', '.join(grad)})",
        'primario': P, 'secundario': S2, 'acento': C.get('acento', S2),
        'fondo-oscuro': C['fondo_oscuro'], 'fondo-oscuro-2': C.get('fondo_oscuro_2', tone(P, 0.1)),
        'fondo-claro': C['fondo_claro'], 'fondo-claro-2': deriv['l100'],
        'grad': f"linear-gradient(135deg, {', '.join(grad)})",
        # burbuja "out" (respuesta del cliente) y conversacion: tonos de la marca
        'ai-bg': tone(P, 0.97, 0.8), 'ai-border': tone(P, 0.88, 0.7),
        'ai-chip-bg': rgba(P, 0.15), 'ai-chip-text': tone(P, 0.45),
    }
    for k, v in deriv.items():
        root[k] = v
    css.append(':root {\n' + '\n'.join(f'  --{k}: {v};' for k, v in root.items()) + '\n}')
    t = fuentes.get('titulos') or {}
    if t.get('tracking'):
        css.append(f".display, .display-800 {{ letter-spacing: {t['tracking']}; }}")
    if 'editorial' in fuentes:
        css.append(".serif { font-family: 'VSerif', serif; font-weight: 400; }")
    (BRAND / 'brand.css').write_text('\n'.join(css) + '\n', encoding='utf-8')

    M['colores_derivados'] = root
    (BRAND / 'brand.js').write_text('// GENERADO por tools/apply_brand.py: no editar a mano.\nwindow.BRAND = '
                                    + json.dumps(M, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    print(f"marca aplicada: {M.get('nombre', '?')} (slug {M.get('slug', '?')}), primario {P}, "
          f"fuentes {', '.join(k for k in ('titulos', 'texto', 'editorial') if k in fuentes)}")


if __name__ == '__main__':
    main()
