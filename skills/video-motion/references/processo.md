# Processo detalhado e prompts-modelo

Tudo aqui supõe um projeto criado com `tools/new_project.py`. Caminhos relativos são da pasta
do projeto. `<PROJ>` = caminho absoluto do projeto; `<SKILL>` = pasta desta skill.

## Etapa 1. Briefing

Faça as perguntas do SKILL.md numa mensagem só, cada uma com uma sugestão de resposta,
para o usuário só dizer "ok" ou corrigir. Leia antes o kit (`hechos_verificados`, `cuidado`) e o
código ou a documentação do projeto para mostrar só funções que existem de verdade e não
prometer o que ainda está pendente.

## Etapa 2. Roteiro

- Tabela `tempo | o que aparece | texto na tela | som`, em trechos de 1,5 a 4 s.
- Gancho nos 2 primeiros segundos, quadro 0 já aceso.
- Para anúncio: dor, virada com a marca, solução espelhando cada dor, resultado real (ou plano B),
  marca e chamada. Estruturas prontas em `references/ideias.md`.
- Para música com batida: escolha bpm (120 a 128) e case cenas com compassos (`bars`).
- Liste embaixo as pendências: número autorizado, assets, oferta vigente, frase de fechamento.
- **Espere o OK.** Nenhuma cena é escrita antes disso.

## Etapa 3. Quadros-chave de estilo (só peças de marca)

1. Três direções bem diferentes (ex.: A neon noturno, B tipografia editorial, C produto em 3D).
2. Cada direção em `styleframes/<x>/`: `direcao.md` (paleta, tipografia, materiais, movimento,
   câmera, transições, som), `x.css`, `x.js` e `k1.html` a `k5.html` (5 momentos do roteiro).
3. Fotografe: `node tools/shoot.mjs styleframes/a/k1.html ... styleframes/a/k5.html --sheet styleframes/a/sheet.png`.
4. Mostre as 3 folhas lado a lado com 3 linhas de resumo cada. **Espere a escolha.**
5. Escreva `DIRECAO.md`: base escolhida, enxertos das outras, fio condutor (ex.: um ponto na cor da marca
   que vira cada elemento do produto e termina no logo), mundo, tipografia, cenas e donos, regras.

## Etapa 4. Construção por trechos

1. `roteiro.yaml`: cenas (com `bg`), `events` com TODOS os tempos de imagem e som, `words`,
   `data` (textos, nomes), `numeros_ok`. `python tools/make_cues.py` e leia cada AVISO (cenas que
   acabam antes da duração, evento colado em troca de fundo, cena fora do `index.html`).
2. Uma cena por arquivo `scenes/NN_nome.js`, com `registerScene({id, span, pre, post, build, render})`.
   Apague `scenes/10_exemplo.js` e a linha dele no `index.html` (ou crie com `--blank`) e ponha
   cada cena nova no `index.html`. Fundo global em `scenes/00_background.js` (uma camada por
   fundo; o claro entra por círculo).
3. Combine a continuidade: anote em `DIRECAO.md` o estado exato na fronteira (posição, escala,
   cor) de cada par de cenas vizinhas. Quem sai entrega, quem entra recebe igual.
4. Prévia de cada trecho: `node tools/preview.mjs --range 9:12:0.1 --sheet --out frames-preview/trecho2`.
   Olhe a folha, confira `errors.txt`, corrija, e só então vá ao próximo.
5. Áudio em `audio/make_audio.py` lendo os mesmos eventos de `cues.json`.
6. `python tools/check_text.py --dom` antes do render.

## Etapa 5. Render

```
node tools/render.mjs --workers 6            # 4 subquadros por padrão; --sub 8 para movimento muito rápido
node tools/assemble.mjs --cover 29.4
python tools/verify.py
```

Trechos: `render.mjs --from 9.375 --to 18.75` para validar uma parte sem pagar o vídeo todo.

## Etapa 6. Revisão adversária

Três revisores independentes, cada um tentando reprovar. Só entram na correção os achados
que outra pessoa (ou você) confirma olhando o quadro ou a medida.

## Etapa 7. Correção, entrega e limpeza

Corrija só o confirmado, rode de novo `render`, `assemble` e `verify`. Entregue MP4 (até
30 MB), `out/video_master.mkv` e capa PNG. Limpe `frames-preview/`, `out/segments/` e a
pasta de trabalho só depois de confirmar que os entregáveis estão no destino.

---

## Prompts-modelo dos agentes

Use como base; troque o que está entre `<>`. Todo prompt de agente começa com o bloco de
contexto e regras abaixo (copie inteiro, não resuma).

### Bloco comum (colar no começo de todo prompt)

```
Contexto: <marca e o que ela faz, em 1 ou 2 frases, a partir do kit>. Publico: <quem>.
Motor de video em <PROJ> (lib.js, main.js, brand/ com o kit de marca e window.BRAND, tools/).
Roteiro aprovado: <PROJ>/roteiro.yaml e cues.json.
Direcao aprovada: <PROJ>/DIRECAO.md (se houver).
Regras: texto no idioma do kit; sem travessao, meia-risca nem emoji (salvo se o kit liberar); nunca
citar fornecedores nem concorrentes de reglas.prohibidas (nem em comentarios de codigo); nenhum
numero fora de numeros_ok; so rotulos que existem no produto; cores e logo so de window.BRAND; nomes
ficticios; texto importante entre y 300 e 1500 e x 90 a 990 (story: y 250 a 1570); titulos,
palavras, baloes e legendas com 56 px ou mais (titulos 110 px ou mais); detalhes do celular
(barra de status, subtitulo, hora do balao) podem ser menores, nunca abaixo de 28 px.
Continuidade: quem sai so sai quando quem entra ja esta na tela. Nenhum evento a menos de
0,2 s de uma troca de fundo; saidas comecam NO evento seguinte (licoes 5, 9 e 10).
Tecnica: render e funcao pura do tempo t (nada de Date, Math.random, setTimeout, CSS
animation); aleatoriedade so com L.hash; tempos so de CUES (nunca numero magico de tempo).
Rode sempre pelo servidor local das tools (nunca abra por file://).
```

### Agente de quadros-chave (um por direção)

```
<bloco comum>
Tarefa: criar a direcao <A/B/C> "<nome curto>" em <PROJ>/styleframes/<x>/ para o roteiro
aprovado. Escreva direcao.md (paleta com hex, tipografia, materiais, movimento, camera,
transicoes, som, maximo 25 linhas), <x>.css, <x>.js e k1.html a k5.html, cada um um quadro
1080x1920 parado de um momento: k1 <momento>, k2 <momento>, k3 <momento>, k4 <momento>,
k5 <momento>. Use as fontes, as cores e o logo do kit (brand/brand.css e window.BRAND). Seja ousado e bem diferente das outras
direcoes: <resumo das outras duas>. Fotografe com
node tools/shoot.mjs styleframes/<x>/k1.html ... --sheet styleframes/<x>/sheet.png, olhe a
folha, corrija o que estiver feio ou ilegivel e repita. Nao edite nada fora de styleframes/<x>/.
Devolva: caminho da folha e 5 linhas descrevendo a direcao.
```

### Agente de cena (um por arquivo de cena)

```
<bloco comum>
Tarefa: escrever SO o arquivo <PROJ>/scenes/<NN_nome>.js, trecho <t0> a <t1> s (cenas
<ids> do roteiro). Conteudo: <descricao da tabela do roteiro para esse trecho>.
Continuidade: no instante <t0> o quadro deve comecar com <estado entregue pela cena anterior>;
em <t1> deve entregar <estado para a proxima cena>.
Eventos que voce deve respeitar (o audio cai neles): <lista de ids de events>.
Nao edite lib.js, main.js, index.html, roteiro.yaml nem outras cenas; se precisar de algo
novo no lib.js, escreva a funcao dentro da sua cena e me avise.
Verificacao obrigatoria antes de devolver:
  node tools/preview.mjs --range <t0>:<t1>:0.125 --sheet --out frames-preview/<nome>
  e tambem --range <t0-0.1>:<t0+0.1>:0.0167 e <t1-0.1>:<t1+0.1>:0.0167 (fronteiras).
Olhe as folhas: errors.txt vazio, nada cortado, texto legivel, sem pulo nas fronteiras,
movimento rapido sem copias separadas. Corrija e repita ate passar.
Devolva: arquivo editado, caminho das folhas e o que ficou pendente (se algo).
```

### Agente de áudio

```
<bloco comum>
Tarefa: escrever <PROJ>/audio/make_audio.py usando audio/synth.py (instrumentos, efeitos,
Mixer, mixdown, finish). Trilha: <estilo, bpm, tom, estrutura por compasso>. Efeitos: um por
evento de cues.json, conforme a coluna som do roteiro: <lista evento -> som>.
Todo tempo vem de cues.json (load_cues); nenhum tempo escrito a mao.
Mix: voz ou efeito principal em evidencia, ducking da musica nos impactos, respiro antes
dos drops. Impactos com camada de 100 a 250 Hz para o alto-falante de celular.
Rode python audio/make_audio.py ate passar: -14 LUFS integrado, true peak <= -1 dBTP,
todos os cues a 1 quadro ou menos, mix com passa-altos de 200 Hz ainda cheio.
Devolva: o loudness.txt resumido e a lista de cues com desvio.
```

### Agente de render e montagem

```
<bloco comum>
Tarefa: gerar o video final de <PROJ>. Antes: python tools/make_cues.py,
python tools/check_text.py --dom e um preview de 0 a <dur> a cada 0,5 s sem erros.
Depois: node tools/render.mjs --workers 6 (se a maquina engasgar, 4), node tools/assemble.mjs
--cover <t>, python tools/verify.py. Se algo falhar, NAO mexa nas cenas: devolva o erro exato,
o quadro e o comando. Confira que out/<slug>-<name>.mp4 tem ate 30 MB.
Devolva: caminhos do MP4, capa e master, e o resumo do verify.json.
```

### Agentes de revisão adversária (três, em paralelo)

Visual:
```
<bloco comum>
Voce e um diretor de motion exigente e seu trabalho e REPROVAR este video se puder.
Gere folhas com node tools/preview.mjs --range 0:<dur>:0.25 --sheet e, nas fronteiras de
cena e nos drops, a cada 1 quadro. Procure: texto cortado ou pequeno, colisao de elementos,
pulo de continuidade, fundo piscando, copias separadas em movimento rapido, serrilhado no
logo, quadro vazio, primeiro ou ultimo quadro ruim para capa, leitura ruim num celular.
Para cada achado: tempo exato, quadro salvo, o que esta errado, correcao sugerida, gravidade
(alta/media/baixa). Nao edite nada.
```

Regras:
```
<bloco comum>
Voce e o revisor juridico e de marca e seu trabalho e REPROVAR. Rode python tools/check_text.py --dom,
depois leia todo texto visivel nas folhas e todo texto dos arquivos de cena. Procure: travessao,
meia-risca, emoji, fornecedor, concorrente, numero fora de numeros_ok, rotulo que nao existe no
produto, promessa absoluta, item de reglas.cuidado do kit, nome real, avatar se passando por
cliente. Cruze funcoes e fatos mostrados com hechos_verificados do kit. Nao edite nada.
Devolva lista com tempo, texto exato, regra violada e correcao.
```

Áudio:
```
<bloco comum>
Voce e o engenheiro de som e seu trabalho e REPROVAR. Meça o MP4 final (nao so o master.wav)
com ffmpeg ebur128 normal e com highpass=f=200. Confira report.json e verify.json: desvio de
cada cue, desfase audio e imagem, cliques nas emendas, silencio no fim exato, estouro. Ouça
por medida os drops e impactos (pico e grave). Nao edite nada. Devolva medidas e achados.
```

Depois dos três: junte os achados, descarte o que não se confirma olhando o quadro ou a medida,
e mande a rodada de correção para o agente dono de cada arquivo.
