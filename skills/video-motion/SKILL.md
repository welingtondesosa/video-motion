---
name: video-motion
description: Use para criar vídeos de motion graphics feitos em código (anúncios, showcases de marca, lançamentos de função, tutoriais, stories, avatares) para QUALQUER marca ou projeto, com o kit de marca dele (cores, fontes, logo e regras), do roteiro até o MP4 revisado com trilha e efeitos sintetizados.
---

# Vídeos de motion graphics em código, para qualquer marca

Vídeo vertical 1080x1920 a 60 fps feito inteiro em código: cenas em HTML/CSS/JS desenhadas quadro a
quadro (Playwright com motion blur), trilha e efeitos sintetizados em numpy, montagem no ffmpeg. Uma folha
de tempos única (`roteiro.yaml` -> `cues.json`) manda na imagem e no som. **A marca sai de um kit**
(`marca.yaml` + fontes + logo), então o mesmo motor serve para qualquer projeto.

`<SKILL>` abaixo = a pasta base desta skill (o caminho aparece quando a skill carrega: pode ser
`~/.claude/skills/video-motion` ou a pasta do plugin em `~/.claude/plugins/...`). Use sempre o caminho absoluto.

- Motor: `<SKILL>/template` (o `README.md` dele explica cada ferramenta).
- Kit de marca: fica em cada projeto, em `.claude/video-marca/` (formato em `references/kit-de-marca.md`).
- Kit de exemplo completo (marca fictícia, fontes livres): `<SKILL>/exemplo-kit/`.
- Python: nos comandos abaixo `python` = Python 3 (no macOS e no Linux, normalmente `python3`).

Responda no idioma do usuário. O texto DO VÍDEO vai no idioma do kit (`idioma`), salvo pedido diferente.

## 0. Primeira vez numa máquina

`node <SKILL>/template/tools/setup.mjs` instala Playwright + Chromium em `~/.video-motion/deps` (fora da
skill, então sobrevive a atualizações) e os pacotes de Python (numpy, soundfile, pyyaml, imageio-ffmpeg,
que já traz o ffmpeg). Precisa de Node 18+ e Python 3.10+. Só uma vez por máquina.
Se o projeto não tem kit e o usuário só quer testar, use `--kit <SKILL>/exemplo-kit`.

## 1. Se o projeto NÃO tem kit de marca

Monte o kit ANTES do roteiro (detalhes e modelo em `references/kit-de-marca.md`):
1. Leia a fonte de verdade do projeto: CSS global ou tokens (cores), carregamento de fontes, componente do
   logo, `llms.txt`/README (o que faz, preços, promessas verificáveis), concorrentes (blog, comparativos).
2. Crie `.claude/video-marca/marca.yaml`, copie as fontes para `fonts/` (baixe do Google Fonts se preciso,
   sempre arquivo local) e o logo e o ícone para `assets/`.
3. Liste em `reglas.prohibidas` concorrentes e fornecedores; em `hechos_verificados` só o que o projeto
   afirma de verdade; em `cuidado` as armadilhas (preço por mercado, produtos parecidos).
4. Teste: `new_project.py` com `--kit`, `preview.mjs` do demo, confira logo e cores e mostre ao usuário.

## 2. Fluxo padrão (não pule as esperas)

1. **Briefing** numa mensagem só, com sugestão em cada item: objetivo e onde vai rodar, público, formato e
   duração (ideias em `references/ideias.md`), UMA mensagem e a chamada final, e se existe número real
   autorizado, pessoa real que consentiu ou voz gravada (se não, plano B).
2. **Roteiro em tabela** `tempo | o que aparece | texto na tela | som` e **ESPERE O OK**.
   Regra de ritmo aprendida na prática: **uma ideia por cena, texto parado 2 s ou mais**. Um vídeo de 30 s
   com dez ideias não se entende. Em peças longas, capítulos de 5 a 15 s.
3. **Só peças de marca** (showcase, lançamento): 3 direções de quadros-chave (5 cada,
   `styleframes/<a|b|c>/k1..k5.html`, `node tools/shoot.mjs ... --sheet`) e **ESPERE A ESCOLHA**.
   A escolhida vai para `DIRECAO.md`, que vira a lei das cenas.
4. **Construção** por trechos com a folha de tempos única: `roteiro.yaml` (cenas, eventos, palavras, data)
   -> `python tools/make_cues.py` (leia cada AVISO); cada cena em `scenes/NN_nome.js`, listada no `index.html`;
   cores e logo vêm de `window.BRAND` (nunca cor fixa de outra marca). Prévia por trecho
   (`preview.mjs --range a:b:passo --sheet`) e corrija antes de seguir.
5. **Áudio**: `audio/make_audio.py` com `audio/synth.py`, sobre os MESMOS eventos.
6. **Render**: `node tools/render.mjs --workers 8`; `node tools/assemble.mjs`; `python tools/verify.py`.
7. **Revisão adversária** em três frentes (visual, regras de texto e marca, áudio e sincronia): cada uma
   tenta reprovar o vídeo. Detalhes em `references/processo.md`.
8. **Correção** só do que foi confirmado; render de novo; verificação de novo.
9. **Entrega**: MP4 H.264 (até 30 MB), master e capa PNG. Copiar para Downloads e apagar a pasta de trabalho
   só quando o usuário pedir, depois de confirmar que os entregáveis estão no destino. Se o Windows travar a
   pasta, feche os processos node/ffmpeg/chromium do render (ver lições).

## 3. Criar um projeto

```
cd <pasta do projeto da marca>
python <SKILL>/template/tools/new_project.py <pasta nova do vídeo> --name <slug> --duration 30 --bpm 96 [--blank] [--kit <pasta do kit>]
```
Sem `--kit`, usa `.claude/video-marca` da pasta atual. Copia o kit para `brand/` e gera `brand/brand.css`
(fontes VDisplay, VTexto e VSerif e a escala de cores do primário) e `brand/brand.js` (`window.BRAND`).
Editou o kit depois: rode `python tools/apply_brand.py` dentro do projeto.
Dentro do projeto: `make_cues.py` -> `preview.mjs` -> `audio/make_audio.py` -> `check_text.py --dom` ->
`render.mjs` -> `assemble.mjs` -> `verify.py`. Todo comando que falha sai com código 1: não siga adiante.

## 4. Regras que valem para todas as marcas

- Sem travessão nem meia-risca (—, –) nem emoji no texto do vídeo: reescreva a frase. O kit pode liberar
  (`reglas.permitir_guiones`, `reglas.permitir_emoji`), mas o padrão limpo lê melhor na tela.
- **Nenhum número inventado.** Só medidos ou publicados pelo projeto (`hechos_verificados`); de cliente, só com
  autorização por escrito. Libere cada número em `numeros_ok` do roteiro.
- Nada de fornecedores nem concorrentes na tela (`reglas.prohibidas` do kit + base do `check_text.py`).
- Sem promessa absoluta ("o único", "ninguém tem", "garantido") que não dê para provar.
- Não destacar logo de terceiros (redes, apps): como canal ou rótulo, nunca como protagonista.
- Pessoas e conversas: nomes fictícios e o aviso `reglas.aviso_encenado` do kit quando houver cena encenada.
  Avatar nunca se passa por cliente real; clone só com consentimento gravado (`references/avatares.md`).
- Preços e ofertas: confirme com o usuário que continuam valendo antes de pôr na tela.

## 5. Qualidade técnica (antes de entregar)

- [ ] `preview.mjs` e `render.mjs` sem erro de JS; quadros = duração x fps.
- [ ] Quadro 0 já aceso; último quadro limpo (capa ou loop).
- [ ] Texto importante entre y 300 e 1500 e x 90 a 990; títulos 100 px ou mais, textos 56 px ou mais
      (detalhe de interface nunca abaixo de 28 px).
- [ ] Fontes do kit carregadas (servidor local, nunca `file://`), sem fonte de sistema no lugar.
- [ ] Continuidade: nenhum quadro vazio entre cenas; fundo sem piscar (duas camadas, nunca trocar a cor numa só).
- [ ] Movimentos rápidos com desfoque direcional (4 subquadros deixam "cópias").
- [ ] `master.wav` em -14 LUFS, true peak até -1 dBTP; audível com passa-altas de 200 Hz (alto-falante de celular).
- [ ] Cues de áudio a 1 quadro ou menos. O `verify.py` pode acusar "imagem atrasada" quando o título anterior
      sai logo antes do novo: confira os quadros em volta do cue (limitação do detector).
- [ ] `check_text.py --dom` limpo e leitura humana das folhas de contato contra o kit.

## 6. Orquestração multiagente: quando vale

| Situação | Como | Custo relativo |
|---|---|---|
| Variante de um vídeo que já existe | sessão única, esforço médio | 1x |
| Anúncio novo de 15 a 60 s | sessão única, esforço alto; um subagente para a revisão | 2x a 3x |
| Peça de marca nova (showcase) ou marca nova sem kit | orquestração: 3 agentes de quadros-chave, depois 1 por cena + áudio, revisão em 3 frentes | 5x a 10x |

Prefira esforço **high** a **max**, etapas curtas e render por trecho: rodadas grandes já estouraram o limite de uso.

## 7. Referências

| Arquivo | Quando ler |
|---|---|
| `references/kit-de-marca.md` | formato do `marca.yaml` e como montar um kit a partir do código de um projeto |
| `references/ideias.md` | formatos de vídeo para qualquer negócio (estrutura, gancho, duração) |
| `references/processo.md` | passo a passo detalhado e prompts-modelo dos agentes |
| `references/licoes.md` | armadilhas que já aconteceram e como evitar (leia antes de começar) |
| `references/avatares.md` | avatares realistas e animados, vozes, custos, ética |
