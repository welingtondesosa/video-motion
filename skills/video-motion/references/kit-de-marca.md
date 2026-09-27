# Kit de marca (`.claude/video-marca/` em cada projeto)

```
.claude/video-marca/
  marca.yaml          obrigatório
  fonts/              arquivos de fonte LOCAIS (.woff2, .ttf, .otf)
  assets/             logo, ícone, camadas (svg/png), fotos liberadas
  ideias.md           opcional: ideias de vídeo próprias do negócio
```

O `new_project.py` copia tudo para `brand/` do projeto de vídeo e o `apply_brand.py` gera `brand.css` e
`brand.js`. Os caminhos dentro do `marca.yaml` são relativos à pasta do kit.
(As chaves do `marca.yaml` estão em espanhol porque o motor foi escrito assim; o conteúdo pode ser em qualquer idioma.)
Um kit completo de exemplo, com fontes livres (SIL OFL), está em `exemplo-kit/` na pasta da skill.

## marca.yaml

```yaml
nombre: Aurora                   # (marca fictícia do exemplo-kit/)
slug: aurora                     # prefixo do MP4 (aurora-<name>.mp4)
sitio: aurora.example
idioma: pt-BR                    # idioma do texto na tela por padrão (pt-BR, es, en...)
idiomas: [pt-BR, es, en]
tagline: {pt-BR: "Pão quentinho, na hora certa.", es: "..."}
cta: {pt-BR: "Peça pelo site", es: "Pide en la web"}

colores:                         # obrigatórios: primario, tinta, fondo_oscuro, fondo_claro
  primario: "#E4572E"            # gera a escala g950..g400 (fundo `bg: marca` do motor)
  secundario: "#F3A712"
  acento: "#F3A712"
  tinta: "#1B1B1E"               # texto sobre fundo claro
  fondo_oscuro: "#141216"
  fondo_oscuro_2: "#241C1E"      # brilho do fundo escuro
  fondo_claro: "#FBF6EF"
  fondo_claro_2: "#F3EADF"
  degradado: ["#E4572E", "#F3A712"]

fuentes:                         # apelidos no motor: titulos=VDisplay (.display), texto=VTexto (.sans), editorial=VSerif (.serif)
  titulos: {familia: Bricolage Grotesque, tracking: -0.03em, archivos: {"400 800": fonts/BricolageGrotesque.woff2}}
  texto:   {familia: Inter, archivos: {"400 800": fonts/Inter.woff2}}      # "400 800" = fonte variável
  editorial: {familia: Instrument Serif, archivos: {400: fonts/InstrumentSerif.woff2}}   # opcional
  # fontes estáticas: um arquivo por peso, ex.: {700: fonts/X-Bold.ttf, 900: fonts/X-Black.ttf}

logo:
  icono: assets/icone.svg        # símbolo
  icono_escala: 1.0              # tamanho relativo à altura da palavra
  separacion: 0.16
  palabra:                       # texto com a fonte dos títulos...
    texto: aurora
    peso: 800
    tracking: -0.03em
    color_oscuro: "#FBF6EF"
    color_claro: "#1B1B1E"
    # degradado: ["#..", "#.."]  # opcional: palavra no degradê
  # ...ou imagem:  palabra: {imagen_oscuro: assets/palavra-branca.svg, imagen_claro: assets/palavra-preta.svg}

textos:                          # opcional: rótulos dos selos das telas recriadas (lib.js)
  selo_ia: "IA atendendo"
  selo_humano: "Pediu atendente"

reglas:
  prohibidas: [concorrentes e fornecedores]    # somam-se à base do check_text
  permitir_guiones: false        # true libera travessão e meia-risca no texto do vídeo
  permitir_emoji: false          # true libera emoji
  aviso_encenado: {pt-BR: "Cenas e nomes ilustrativos"}
  rotulos_reales: [rótulos da interface que podem aparecer do jeito que são]
  hechos_verificados: [o que o projeto afirma publicamente e pode ser dito]
  cuidado: [armadilhas: preço por mercado, produtos parecidos, promessas proibidas]
```

Nas cenas: `window.BRAND` (o yaml inteiro) e `window.BRAND.colores_derivados` (escala e variáveis).
No CSS: `var(--primario)`, `var(--secundario)`, `var(--acento)`, `var(--grad)`, `var(--fondo-oscuro)`,
`var(--fondo-claro)`, `var(--ink)`, e a escala `--g950` a `--g400` e `--l50` a `--l200`.
`L.makeLogo(parent, {height, dark})` monta o logo do kit.

## Como montar um kit a partir do código do projeto

1. **Cores**: CSS global ou tokens do Tailwind (`globals.css`, `tailwind.config`, `:root`). Primário = a cor dos
   botões e destaques; degradê se a marca tiver um de assinatura.
2. **Fontes**: veja como o site carrega (`next/font`, `@font-face`, Google Fonts). Copie os arquivos locais do
   projeto; se vierem do Google Fonts, baixe o `.woff2` do subset latin (com os acentos) usando um User-Agent
   de Chrome. O render nunca depende de internet.
3. **Logo**: o componente do logo (SVG inline ou arquivo). Recorte o viewBox ao conteúdo. Se a palavra for texto
   com a fonte da marca, use `palabra.texto`.
   **Licença:** só inclua fontes que você pode usar e redistribuir (Google Fonts são SIL OFL; fontes
   compradas costumam proibir redistribuição, então não publique o kit com elas).
4. **Fatos e cuidados**: `llms.txt`, README, página de preços, FAQ. Só o que o projeto afirma.
5. **Proibidas**: fornecedores da stack (README) e concorrentes (comparativos do blog).
6. Teste com o demo (`new_project.py` sem `--blank` e `preview.mjs --range 0:4:0.5 --sheet`) e mostre ao usuário.
