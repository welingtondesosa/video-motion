# Motor de vídeo (template genérico, a marca vem do kit)

Vídeo vertical 1080x1920 feito em código: cenas em HTML/CSS/JS desenhadas quadro a quadro
(Playwright), trilha e efeitos sintetizados em numpy, montagem com ffmpeg. Tudo sai de um
roteiro único, então cada som cai no quadro do evento.

## Começar um vídeo

```
python <SKILL>/template/tools/new_project.py <pasta> --name anuncio-ia --duration 30 --bpm 120 [--kit <pasta do kit>]
```

Cria a pasta com o demo de 4 s funcionando (palavra com mola + logo); com `--blank`, sem o demo
(roteiro com uma cena só). Sem `--blank`, apague `scenes/10_exemplo.js` e a linha dele no
`index.html` quando escrever as suas cenas. Dentro dela:

| passo | comando | sai |
|---|---|---|
| 1. tempos | `python tools/make_cues.py` | cues.json + cues.js a partir do roteiro.yaml |
| 2. cenas | editar `scenes/*.js` e a lista no `index.html` | |
| 3. revisar | `node tools/preview.mjs --range 0:30:0.5 --sheet` | frames-preview/last/sheet.png (com o tempo de cada quadro) |
| 4. áudio | `python audio/make_audio.py` | audio/master.wav (-14 LUFS, TP <= -1), loudness.txt, report.json |
| 5. texto | `python tools/check_text.py --dom` | acusa travessão, emoji, marca proibida, número |
| 6. render | `node tools/render.mjs --workers 6` | out/video_master.mkv (motion blur 4 subquadros) |
| 7. MP4 | `node tools/assemble.mjs` | out/<slug da marca>-<name>.mp4 + capa |
| 8. conferir | `python tools/verify.py` | quadros, fps, loudness do MP4, sincronia imagem e som |

## Peças

- `roteiro.yaml`: duração, bpm, cenas (`start/end` ou `bars`, `bg`: escuro/marca/claro/blog, `wipe`),
  `events` (só tempos: `"bar 2 + beat 1"`, `"logo_in + 0.1"`, `{bar: 2, 16th: 3}`), `words`, `data`,
  `numeros_ok`. Formato completo no topo de `tools/make_cues.py`.
- `lib.js`: easing, mola, celular (bateria só ícone; `batteryLabel`, `battery: false`), conversa
  (`chipH`), notificação, selos do app (texto do kit em `textos.selo_ia` e `textos.selo_humano`, 44 px), título, `makeWord`
  (palavra com mola), `makeLogo`. Regra: render é função pura de t.
- `scenes/00_background.js`: fundo global (escuro, marca, blog cruzam opacidade; claro entra por
  círculo) e o aviso (`data.aviso`, `aviso_de`, `aviso_ate`, `aviso_y`).
- `brand/` (cópia do kit de marca: `marca.yaml`, fontes, logo) com `brand.css` e `brand.js` gerados por `tools/apply_brand.py`.
- `main.js`: `registerScene({id, pre, post, build, render(tl, t)})` e `registerLayer`.
- `styles.css`: estilos base; fontes e cores vêm de `brand/brand.css` (apelidos VDisplay, VTexto, VSerif).
- `audio/synth.py`: instrumentos (bumbo, palmas, chimbal, baixo, pad, pluck, acordes/stab, prato,
  `groove` pronto), efeitos (pop e pop por canal, vibração, whoosh, riser, riser reverso, impacto com
  camada 100 a 250 Hz, tique, ding, sino, brilho, snap, blip, cliques, coração, grilos, ar),
  `logo_hit`, `Mixer` (pan, envios de reverb, ducking, bombeamento), `mixdown`, `finish`
  (premaster + loudnorm 2 passadas linear + relatório + conferência de cada cue em até 1 quadro).
- `lib-avatar.js` + `tools/lipsync.py`: avatar animado em SVG com boca sincronizada à voz (ver cabeçalhos).

## Regras de texto (o check_text cobra)

Português do Brasil; sem travessão, meia-risca ou emoji; nunca citar fornecedores nem concorrentes;
nenhum número inventado (só medido, e de cliente só com autorização por escrito; liberar em
`numeros_ok`); só rótulos que existem no app; nomes fictícios.
