# Avatares falando e usando o produto

Pesquisa feita em 27/09/2026. Preços e termos mudam: confira a página oficial antes de assinar.
**[conf.]** = confirmado na página oficial; **[sec.]** = fonte secundária; **[NÃO CONFIRMADO]** = não checado.

Hardware desta máquina: NVIDIA Quadro P620 4 GB, i5-10400H, 16 GB RAM. Modelos realistas de
código aberto NÃO rodam bem aqui; só o avatar animado em código e a voz local no processador.

## Recomendação em 3 níveis

1. **Sem custo: avatar animado em código.** Personagem próprio em SVG (`lib-avatar.js`), boca
   pelo `lipsync.py`, voz pt-BR local (Kokoro-82M, vozes `pf_dora`, `pm_alex`, `pm_santa`,
   Apache-2.0, roda no processador; naturalidade [NÃO CONFIRMADO, não testado]). Serve para
   anúncios, tutoriais e séries. Resultado sempre igual, cara da marca, sem risco de imitar
   ninguém. Contra: parece desenho para parte do público.
2. **Custo baixo (uns US$ 10 a 30 por mês): HeyGen por API**, pago por uso, Avatar IV cerca de
   US$ 0,05/s (uns US$ 1,50 por tomada de 30 s) [sec.], com `output_format: "webm"` saindo com
   fundo transparente (VP9 com alfa, Avatar III, IV e V; os "Cinematic" não aceitam) [conf.].
   Voz da própria HeyGen ou ElevenLabs Starter (US$ 6/mês, licença comercial) [conf.]. Só avatar
   de estoque como "apresentador da marca", nunca como cliente. Plano grátis da HeyGen e da
   ElevenLabs proíbe uso comercial [conf.].
3. **Qualidade máxima:** gêmeo digital HeyGen Avatar V de alguém real do time (ex.: o fundador),
   com vídeo de consentimento gravado pela própria pessoa [conf.], voz clonada profissional,
   saída transparente em 4K e composição em sanduíche. Alternativa mais crível e com risco
   ético zero: **gravar a pessoa de verdade com o celular e fundo verde** e usar a mesma composição.

## Serviços realistas (resumo)

| Serviço | pt-BR | Fundo transparente | Observação |
|---|---|---|---|
| HeyGen | sim, pt-BR separado [sec.] | sim, webm VP9 [conf.] | melhor custo para nós; API sem crédito grátis desde fev/2026 [conf.] |
| Synthesia | sim [conf.] | [NÃO CONFIRMADO] | avatar de estoque NÃO pode endossar produto [conf.]: só com avatar pessoal (Creator US$ 89) |
| D-ID | sim [sec.] | [NÃO CONFIRMADO] | o mais caro por minuto; marca d'água no Trial e Lite [conf.] |
| Hedra Character-3 | [NÃO CONFIRMADO] | [NÃO CONFIRMADO], usar fundo verde | anima qualquer imagem: risco de imitar alguém fica do nosso lado |
| Azure TTS Avatar | vozes pt-BR [conf.] | sim, webm VP9 [conf.] | avatar personalizado com acesso restrito e consentimento |
| Captions / Mirage | [NÃO CONFIRMADO] | [NÃO CONFIRMADO] | "atores" estilo UGC: alto risco de parecer depoimento falso |
| Tavus, Colossyan | | | conversa em tempo real / treinamento; não recomendados |

Código aberto: MuseTalk 1.5 (MIT, único que talvez rode em 4 GB, lento aqui [NÃO CONFIRMADO]);
LatentSync e InfiniteTalk (Apache-2.0) só com GPU alugada (RTX 4090 uns US$ 0,34 a 0,69/h [sec.])
ou InfiniteTalk no fal.ai (US$ 6 a 12 por 30 s [conf.]). **Não usar**: Wav2Lip (proíbe uso
comercial), LivePortrait (InsightFace não comercial), Hallo3 (só inglês, licença presa),
EchoMimic V2 (projeto se diz só para pesquisa), edge-tts (serviço não oficial), pesos do XTTS
(não comerciais).

Vozes pt-BR: ElevenLabs (mais natural [sec.]), Azure Neural (Francisca, Thalita, Macerio, Luana,
Caio, Pedro [conf.]; 500 mil caracteres grátis por mês [conf.]; se o plano grátis vale para
produção [NÃO CONFIRMADO]), Google Chirp 3 HD, Kokoro local. Clonar voz exige consentimento.

## Nível 1 na prática: `lib-avatar.js` + `lipsync.py`

Passos:

1. **Voz primeiro.** Grave ou gere a voz final pt-BR como `audio/voz.wav` (48 kHz, 16 bits).
   A voz manda nos tempos: cenas, boca e gestos leem o tempo de cada palavra.
   (A demo usa TTS do Windows em voz es-ES só para testar a boca: não publicar.)
2. `python audio/make_audio.py`: põe a voz na linha do tempo e gera `voz_trilha.wav` (só a voz,
   já no tempo do vídeo) e `master.wav` (mix com trilha e efeitos, voz em evidência).
3. Boca, SEMPRE sobre a voz isolada e com o texto exato:
   ```
   python tools/lipsync.py audio/voz_trilha.wav --text "<fala exata>" --out audio/fala.json --js audio/fala.js --name fala --duration <s>
   ```
   Com `--text` fecha a boca em m/p/b e dá o tempo de cada palavra (legendas e gestos).
   Sem `--text` só usa o volume e não fecha em m/p/b. `--offset` desloca sem mexer no WAV;
   `--lead` (0,03 s) adianta a boca como na vida real.
4. Na cena (carregue `lib-avatar.js` depois do `lib.js` e `audio/fala.js` no `index.html`):
   ```js
   const F = LIPSYNC.fala, at = (i) => F.words[i].t0;   // início da palavra i da fala
   const av = L.makeAvatar(root, {
     x: 240, y: 700, scale: 1, lipsync: F, hair: 'cacheado',
     gestures: [{ type: 'wave', arm: 'R', at: 0.25, until: at(1) - 0.2 },
                { type: 'point', arm: 'R', at: at(1), until: at(9) - 0.05, angle: 122 },
                { type: 'phone', arm: 'L', at: at(9) - 0.1, until: 7 }],
     look: [{ at: 0, x: 0, y: 0 }, { at: 1.9, x: 0.8, y: -0.2 }],
     handPhone: { build(div) { /* tela do app com L.makeChat */ return (t) => {}; } },
   });
   // render(tl, t): av.render(t)
   ```
   Tempos dos gestos vêm das palavras (`LIPSYNC.fala.words[i].t0`), nunca escritos à mão.
   `L.lipAt`, `L.talkEnergy` e `L.wordAt` servem para legenda que acende a palavra falada.
5. Conferir a boca quadro a quadro: `node tools/preview.mjs --range 2.0:2.9:0.0333 --out frames-preview/boca`.
6. Render normal. O `tools/assemble.mjs` da demo aceita `--name`, `--dur` e `--cover`.

Limites: um ângulo só (frente), 3 gestos (`wave`, `point`, `phone`; novos entram em `POSES`),
sem outras emoções; boca aproximada (siglas, números e palavras estrangeiras saem piores; ruído
ou música na trilha de voz estragam o alinhamento). Antes de publicar a demo: tirar a etiqueta
"Protótipo de avatar em código, voz de teste" e trocar o botão "Assumir conversa", que não existe no app.

## Níveis 2 e 3 na prática: compor avatar gravado + telas em código

O ffmpeg do imageio tem `libvpx-vp9`, `chromakey`, `despill`, `overlay`, `alphamerge`,
`prores_ks` e `qtrle` (verificado).

1. **Avatar com alfa (webm VP9):** o decodificador vem ANTES do `-i`, senão perde a transparência.
   ```
   ffmpeg -i out/video_master.mkv -c:v libvpx-vp9 -i avatar.webm -filter_complex "[1:v]fps=60,scale=720:-1,format=yuva420p[av];[0:v][av]overlay=x=(W-w)/2:y=H-h-80:shortest=1[v]" -map "[v]" ...
   ```
2. **Fundo verde** (gravação real, Hedra, serviços sem alfa): `chromakey=0x00FF00:0.12:0.08,despill=type=green` e depois o overlay.
3. **Sanduíche** (tela do produto passa NA FRENTE do avatar): renderize duas passadas do motor,
   fundo e frente transparente (ProRes 4444 `yuva444p10le` ou qtrle). Ordem: fundo, avatar,
   frente. O `render.mjs` já trata quadros RGBA; falta só a saída com transparência.
4. **Não use `<video>` dentro do Playwright** (não garante o quadro exato). Se o avatar precisa
   interagir dentro da cena, extraia PNG com alfa por quadro e desenhe cada quadro como `<img>`.
5. **Voz primeiro:** o mesmo arquivo de voz gera o avatar no serviço, marca os tempos das cenas
   e entra no `master.wav`.

## Cuidados éticos e legais

- **Nunca depoimento falso.** Avatar ou ator de IA não se passa por cliente. CDC art. 37
  (publicidade enganosa) [não verificado]; guia do CONAR em vigor desde 01/06/2026: IA não tira
  a responsabilidade pela veracidade e pede transparência sobre o caráter sintético [sec.].
  Avatar é "apresentador da marca" ou "personagem ilustrativo", com aviso na tela.
- **Nunca clonar rosto ou voz sem consentimento escrito** (e gravado, no caso da HeyGen).
  Biometria é dado sensível na LGPD e o Código Civil art. 20 protege a imagem [não verificado].
  Não usar foto de banco de imagem nem imagem gerada por outra IA como base de clone.
- **Planos grátis** (HeyGen, ElevenLabs) proíbem uso comercial. Confira licença de todo modelo.
- **Telas do Instagram e do WhatsApp:** interface real em anúncio exige aprovação prévia da
  Meta (2 a 3 semanas) [conf.]. Desenhe a conversa com a interface do seu produto, cite as marcas
  de forma descritiva, logos só dos kits oficiais e sem destaque, sem sugerir parceria.
- **Rótulo de IA:** a Meta pode rotular sozinha; boa prática é deixar claro no vídeo que o
  apresentador é digital.

Fontes principais: heygen.com/pricing, developers.heygen.com (transparent-background-videos,
avatar-consent), synthesia.io (pricing, stock avatars), learn.microsoft.com (TTS avatar,
visemas, idiomas), elevenlabs.io/pricing, GitHub de cada modelo citado, meta.com/brand.
