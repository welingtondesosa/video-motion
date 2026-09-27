# Lições: armadilhas que já aconteceram

Cada item: o que aconteceu, por que, e o que fazer. Leia antes de começar um vídeo novo.

## Render e imagem

1. **Quadros RGBA fazendo o ffmpeg reiniciar filtros e perder trechos.** O Chrome às vezes grava
   o PNG com alfa (RGBA) em vez de RGB; a troca de formato no meio do fluxo fazia o ffmpeg
   reconfigurar o filtro (`tmix` do motion blur) e jogar fora quadros. O vídeo ficava curto e
   com saltos. **Faça:** use o `render.mjs` do template (usa `-reinit_filter 0` e normaliza todo quadro com
   `format=gbrp` antes do `tmix` e confere o número de quadros). Se o total não bater com
   duração x fps, não monte o MP4.
2. **Fontes bloqueadas em `file://`.** Aberta direto do disco, a página não carrega as woff2
   e cai na fonte do sistema sem dar erro visível. **Faça:** sempre pelo servidor local das tools
   (`preview`, `render`, `shoot` já sobem um). Desconfie de qualquer título "com cara de Arial".
3. **4 subquadros viram cópias separadas em movimento muito rápido.** O motion blur médio de 4
   amostras mostra 4 fantasmas nítidos quando algo anda muitos pixels por quadro (avião,
   palavras voando, chicotes de câmera). **Faça:** desfoque direcional no próprio objeto
   (`filter: blur` só no eixo do movimento, ou cópias em degrau desenhadas de propósito), ou
   `render.mjs --sub 8` no trecho. Confira a fronteira com prévia a cada quadro.
4. **Fundo piscando ou cinza sujo ao trocar de cor.** Animar a cor de uma camada só passa por
   tons intermediários sujos e pisca com o blur de subquadros. E cruzar escuro com claro por
   opacidade passa por um cinza chapado (no ensaio do story, 2,0 a 2,1 s saíram cinza e vazios).
   **Faça:** use o `00_background.js` do template: cada fundo é uma camada; entre fundos escuros
   (escuro, marca, blog) cruza opacidade; o **claro entra e sai por círculo** (centro opcional
   `wipe: [x, y]` na cena), por cima da vinheta. Melhor ainda: um elemento grande na frente
   (celular, cartão) cobrindo a troca.
5. **Cenas vizinhas sem combinar continuidade.** Cada agente fez sua cena bonita, mas no corte
   o objeto pulava de lugar, tamanho ou cor. **Faça:** anotar no `DIRECAO.md` o estado exato
   de cada fronteira (posição, escala, cor, o que continua na tela) e pedir a cada agente a
   prévia quadro a quadro de 0,1 s antes e depois das suas fronteiras. Em vídeo curto sem
   `DIRECAO.md`, a regra é: **quem sai só sai quando quem entra já está na tela** (no story, as
   palavras saem no mesmo `phone_in` em que o celular sobe; o celular só cai no `logo_in`).
   Nenhum quadro só com fundo entre duas cenas.
6. **`L.makeChat` media os balões com o celular escondido (altura 0).** Mensagens cortadas ou
   sumidas quando o celular entrava depois do início. **Corrigido no `lib.js`:** a medição
   agora mostra celular e balões na hora de medir. O selo do chat tem altura medida (ou
   `chipH`), não mais 64 px fixos.

## Tempo e áudio

7. **Eventos de áudio e de imagem com agendas diferentes.** O som tinha seus próprios tempos
   escritos à mão e a imagem outros; qualquer ajuste descasava tudo. **Faça:** uma lista única
   de eventos no `roteiro.yaml` -> `cues.json`; cenas e `make_audio.py` só leem dali. Mudou um
   tempo, roda `make_cues.py` e as duas pontas acompanham. `verify.py` confere o casamento.
8. **Mix bom no fone e sumido no celular.** Impacto só de grave some no alto-falante pequeno.
   **Faça:** camada de 100 a 250 Hz nos impactos e medir sempre também com passa-altos de 200 Hz.
9. **`verify.py` reprova por movimento que sobrou.** Uma mola ainda assentando (menos de 1 px)
    do elemento anterior muda pixels e o verify vê a "mudança" alguns quadros ANTES do cue. No
    ensaio: `makeWord` padrão (freq 3, zeta 0,42) com a 2ª palavra 0,5 s depois deu -6 e -3
    quadros; a mola do celular (2,4 / 0,72) derrubou o evento 0,75 s depois. **Faça:** 0,7 s ou
    mais depois de uma mola padrão, ou mola firme (freq 4 ou mais, zeta 0,7 ou mais), ou curva
    que termina (`L.ease.outQuint(L.seg(t, a, a + 0.55))`). Nada começa a mexer entre dois
    eventos: saídas começam NO evento seguinte (ex.: `out: E.phone_in`).
10. **Evento colado numa troca de fundo nunca passa no `verify.py`.** A troca (0,3 s centrada na
    fronteira) muda o quadro inteiro. **Faça:** nenhum evento a menos de 0,2 s de uma fronteira
    em que `bg` muda (`make_cues.py` avisa). Com o mesmo `bg` dos dois lados pode.

## Sessão e agentes

11. **Sessão estourando o limite de uso em rodadas grandes.** Muitos agentes em esforço máximo
   renderizando e revisando tudo de uma vez esgotaram o uso no meio do trabalho. **Faça:**
   etapas curtas (um trecho por vez), render intermediário por trecho (`--from/--to`), esforço
   high em vez de max, e revisão adversária só no fim de cada etapa.
12. **Agentes interrompidos deixam arquivos meio editados.** Um agente parou no meio e a cena
    ficou com sintaxe quebrada; o render seguinte falhou longe do problema. **Faça:** depois de
    qualquer interrupção, rode `python tools/make_cues.py` (faz `node --check` em cada cena do
    `index.html` e sai com código 1 se uma quebrar) e uma prévia rápida (`errors.txt` vazio;
    o `preview.mjs` sai com 1 se houver erro de JS). Na mão, um arquivo por vez:
    `for f in scenes/*.js; do node --check "$f" || exit 1; done` (bash). Atenção:
    `node --check scenes/*.js` só confere o PRIMEIRO arquivo (os outros viram argumentos).
    Confira também quadros e arquivos soltos em `out/`.
13. **Dois agentes no mesmo arquivo.** Edições se sobrescrevem. **Faça:** cada agente é dono
    de um arquivo; `roteiro.yaml`, `lib.js` e `index.html` são só do orquestrador.
14. **Pasta de trabalho travada no Windows.** Não dá para apagar porque um node, ffmpeg ou
    navegador do render ficou aberto. **Faça:** encerrar esses processos (PowerShell:
    `Get-Process node, ffmpeg*, chrome* -ErrorAction SilentlyContinue | Stop-Process -Force`,
    conferindo antes que não há outro trabalho do usuário rodando) e só então apagar.

## Verdade e marca

15. **Número de cliente exige autorização.** O roteiro do anúncio dependia de um número de
    cliente que tinha dois valores anotados diferentes, de mês parcial, sem autorização.
    **Faça:** sem autorização por escrito citando número e mês, a cena sai (plano B) ou usa um
    total real da plataforma, medido de novo em mês fechado e descrito exatamente ("mensagens
    enviadas pelo WhatsApp em 1 mês", não "atendimentos" nem "vendas"). Arredonde só para baixo.
16. **Rótulo que não existe no app.** A demo do avatar mostrou o botão "Assumir conversa", que
    não existe. **Faça:** todo texto dentro de uma tela recriada precisa existir no código do
    app (procure no código do projeto); o resto vira grafismo fora da moldura.
17. **Logo errado.** Um arquivo de logo antigo do site trazia texto com erro de digitação.
    **Faça:** só os arquivos do kit de marca (`brand/`), conferidos com o usuário.
18. **Número escondido na interface.** O celular do `lib.js` escrevia "64%" na bateria e o
    `check_text --dom` reprovava todo vídeo com celular. **Corrigido:** a bateria é só ícone;
    `batteryLabel: true` volta o número (liberar em `numeros_ok`), `battery: false` esconde.
19. **Voz de teste esquecida.** A demo usa TTS do Windows (voz espanhola) e uma etiqueta de
    protótipo. **Faça:** nunca publicar com voz de teste; voz final pt-BR de serviço com
    licença comercial ou pessoa real que consentiu.
