# Banco de formatos de vídeo (qualquer negócio)

Cada formato: objetivo, duração, estrutura em batidas, gancho dos 2 primeiros segundos. Ajuste o
conteúdo com o `hechos_verificados` do kit. Ideias próprias do negócio podem ficar em `ideias.md` dentro do kit.
Regra de ouro (aprendida com crítica real): **uma ideia por cena, texto parado 2 s ou mais**.

## 1. Dor e solução (anúncio 30 s)
Objetivo: conversão. Batidas: 3 cenas de dor do dia a dia (0 a 10 s) -> virada com a marca (10 a 12 s) ->
as MESMAS 3 cenas resolvidas (12 a 22 s) -> prova real (22 a 26 s) -> marca e chamada (26 a 30 s).
Gancho: o momento mais reconhecível da dor, já aceso no quadro 0. Cuidado: não encher de informação.

## 2. Lançamento de função (30 a 60 s, por capítulos)
Objetivo: mostrar UMA novidade com clareza. Capítulos: gancho com o jeito antigo (5 s) -> "Novidade" +
nome da função (5 s) -> demonstração lenta, passo a passo (10 a 15 s) -> comparação lado a lado
"Antes" x "Agora" (10 s cada, uma ou duas) -> onde o resultado aparece (5 s) -> marca e chamada (5 a 8 s).
Gancho: a dor que a função resolve. Funcionou muito bem em 60 s a 96 bpm (capítulo = 2 a 6 compassos).

## 3. Showcase de marca (15 a 30 s)
Objetivo: desejo e lembrança, quase sem texto. Um fio visual que atravessa o filme (um ponto, uma forma,
a cor da marca) + 2 drops musicais + loop (último quadro = primeiro). Sempre com 3 direções de quadros-chave.

## 4. Tutorial rápido (30 a 45 s)
Uma tarefa, 3 passos numerados na tela do produto recriada em código, cada passo com 1 frase curta.
Gancho: o resultado final mostrado primeiro, depois "como fazer em 3 passos".

## 5. Antes e depois (15 a 30 s)
Tela dividida, lado antigo apagado e lento, lado novo com a cor da marca. Sem números inventados: a
diferença aparece por imagem (pilha de mensagens x uma, página lenta x toque único).

## 6. Caso de cliente (30 s)
Só com número e nome autorizados por escrito. Estrutura: quem é (3 s) -> problema (5 s) -> o que mudou
(10 s) -> número real grande (5 s) -> marca. Sem autorização: use total real da plataforma ou tire a cena.

## 7. Por nicho (mesmo esqueleto, 3 a 5 variantes)
Troque só a cena de dor, os nomes e o vocabulário por público (ex.: loja, clínica, serviço). Barato: o
motor, o áudio e a marca ficam iguais.

## 8. Comparação sem citar concorrente
"Outros jeitos" genéricos (planilha, papel, app qualquer) x o produto. Nunca nome ou logo de concorrente.

## 9. Story de 8 a 15 s
Gancho (2 s) -> uma tela do produto (4 a 8 s) -> logo e site (2 a 3 s). Área útil y 250 a 1570.

## 10. Vinheta de marca (bumper de 6 s)
Logo animado + tagline + som assinatura. Serve para abrir e fechar outros vídeos.

## 11. Pergunta e resposta (série)
Uma dúvida frequente por vídeo (15 a 20 s): pergunta grande na tela, resposta em 2 frases, marca.

## 12. Data sazonal (Natal, Dia das Mães, Black Friday)
Esqueleto de dor e solução com a cor e os elementos da data, sem trocar a identidade da marca.

## 13. Convite para teste ou amostra grátis
Foco total na chamada: o que a pessoa recebe grátis, em 3 passos, e o botão. Confirmar a oferta vigente.

## 14. Avatar apresentando (30 s)
Personagem animado (lib-avatar.js) ou avatar realista de serviço como APRESENTADOR da marca, nunca como
cliente. Telas do produto em código ao lado. Ver `avatares.md`.

## 15. Emoção e presente (produtos afetivos)
Para produtos de emoção (presentes, homenagens): uma história curta em 3 momentos (quem, o momento, a
reação), tipografia editorial (fonte `editorial` do kit), música com crescendo, marca no fim.

## Variantes baratas
Mesmo projeto, troque só `data` do roteiro (textos, nomes, nicho) e renderize de novo. Duração e música só
mudam no `roteiro.yaml` + `make_audio.py`.
