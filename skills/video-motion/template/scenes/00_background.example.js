// Fundo global contínuo + aviso fixo. Camada z 0 (atrás de tudo) e z 60 (aviso por cima).
//
// Cada cena escolhe o fundo no roteiro com `bg` (padrão: escuro):
//   scenes:
//     - {id: dor,    start: 0, end: 10, bg: escuro}   fondo_oscuro do kit com brilho frio de tela
//     - {id: virada, start: 10, end: 20, bg: marca}   tons escuros do primário do kit, círculos respirando
//     - {id: final,  start: 20, end: 30, bg: claro}   branco descendo para fondo_claro do kit
//     - {id: prova,  start: 20, end: 24, bg: blog}    degradê médio do primário do kit
// A troca dura 0,3 s centrada na fronteira (sem piscar: cada modo é uma camada própria, nunca
// uma cor trocando numa camada só). Entre fundos escuros (escuro, marca, blog) é cruzamento de
// opacidade. O CLARO entra e sai por um CÍRCULO a partir do centro: cruzar preto com branco por
// opacidade passaria por um cinza sujo e vazio. Centro opcional por cena: `wipe: [x, y]` em px.
// A troca muda o quadro inteiro: não ponha evento a menos de 0,2 s de uma fronteira com troca
// de fundo (o make_cues avisa) e deixe um elemento na tela "carregando" a troca.
//
// Aviso "Cenas e nomes ilustrativos": se CUES.data.aviso existir. Intervalo opcional em
// CUES.data.aviso_de / CUES.data.aviso_ate (s). Fica em top 248 px, faixa livre das interfaces
// do Reels/TikTok. Story (topo 250 px e base 350 px ocupados pela interface): use
// CUES.data.aviso_y (ex.: 1500) para descer o aviso.
(function () {
  const C = CUES;
  // colores del kit de marca (brand/brand.js): K = colores de marca.yaml, V = derivados
  const K = (window.BRAND && window.BRAND.colores) || {};
  const V = (window.BRAND && window.BRAND.colores_derivados) || {};
  const MODES = ['escuro', 'verde', 'claro', 'blog'];
  const ALIAS = { marca: 'verde', brand: 'verde' }; // bg: marca = fundo na cor da marca (nome antigo: verde)
  const XF = 0.3; // duração do cruzamento
  const layers = {};
  let circlesBox, circles = [], vignette;
  const RMAX = Math.hypot(1080, 1920); // raio que cobre o quadro a partir de qualquer centro

  const modeAt = (t) => {
    // peso de cada modo em t: cruzamento linear de XF centrado em cada fronteira
    const w = Object.fromEntries(MODES.map((m) => [m, 0]));
    const sc = C.scenes;
    if (!sc.length) { w.escuro = 1; return w; }
    for (let i = 0; i < sc.length; i++) {
      const s = sc[i];
      const a = i === 0 ? -1e9 : s.start - XF / 2;
      const b = i === sc.length - 1 ? 1e9 : s.end + XF / 2;
      const inP = i === 0 ? 1 : L.seg(t, a, a + XF);
      const outP = i === sc.length - 1 ? 0 : L.seg(t, b - XF, b);
      const k = Math.min(inP, 1 - outP);
      const bg = ALIAS[s.bg] || s.bg;
      const m = bg && MODES.includes(bg) ? bg : 'escuro';
      if (k > 0) { w[m] += k; if (m === 'claro' && k < 1) w.wipe = s.wipe || [540, 960]; }
    }
    return w;
  };

  registerLayer({
    z: 0,
    build(root) {
      layers.escuro = L.el('div', 'layer', root);
      layers.escuro.style.background = `radial-gradient(ellipse 620px 900px at 50% 58%, ${K.fondo_oscuro_2 || '#10161f'} 0%, ${K.fondo_oscuro} 70%)`;
      layers.verde = L.el('div', 'layer', root);
      layers.verde.style.background = `linear-gradient(160deg, ${V.g950}, ${V.g800})`;
      layers.blog = L.el('div', 'layer', root);
      layers.blog.style.background = `linear-gradient(135deg, ${(K.degradado || [V.g750, V.primario]).join(', ')})`;
      // Círculos brancos translúcidos (4% e 5%), como nas capas do blog: só nos fundos verdes.
      circlesBox = L.el('div', 'layer', root);
      const spec = [
        { x: -180, y: 180, r: 520, o: 0.05, ph: 0.0 },
        { x: 720, y: 520, r: 420, o: 0.04, ph: 1.3 },
        { x: 560, y: 1380, r: 640, o: 0.05, ph: 2.1 },
        { x: -260, y: 1180, r: 380, o: 0.04, ph: 3.4 },
        { x: 820, y: -120, r: 300, o: 0.04, ph: 4.2 },
      ];
      for (const c of spec) {
        const e = L.el('div', 'abs', circlesBox);
        L.css(e, { left: `${c.x}px`, top: `${c.y}px`, width: `${c.r * 2}px`, height: `${c.r * 2}px`, borderRadius: '50%', background: '#fff' });
        circles.push({ e, ...c });
      }
      vignette = L.el('div', 'layer', root);
      vignette.style.background = 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.55) 100%)';
      // claro POR CIMA da vinheta e dos círculos: o disco que entra é branco limpo, sem cinza
      layers.claro = L.el('div', 'layer', root);
      layers.claro.style.background = `linear-gradient(180deg, #FFFFFF 0%, ${K.fondo_claro} 60%, ${V['fondo-claro-2']} 100%)`;
    },
    render(t) {
      const w = modeAt(t);
      // escuro por baixo sempre opaco; os outros por cima com o próprio peso
      layers.escuro.style.opacity = '1';
      for (const m of ['verde', 'blog']) layers[m].style.opacity = String(L.clamp(w[m]));
      // claro: círculo que cresce (entrada) ou encolhe (saída); nunca meio-transparente
      const c = L.clamp(w.claro);
      layers.claro.style.opacity = c > 0.001 ? '1' : '0';
      if (c > 0.001 && c < 0.999) {
        const [cx, cy] = w.wipe || [540, 960];
        layers.claro.style.clipPath = `circle(${(RMAX * L.ease.inOutCubic(c)).toFixed(1)}px at ${cx}px ${cy}px)`;
      } else layers.claro.style.clipPath = 'none';
      const g = L.clamp(w.verde + w.blog);
      circlesBox.style.opacity = String(g);
      if (g > 0.001) {
        for (const c of circles) {
          L.tf(c.e, { y: 18 * Math.sin(t * 0.55 + c.ph * 1.7), s: 1 + 0.06 * Math.sin(t * 1.1 + c.ph), o: c.o });
        }
      }
      // vinheta: cheia no escuro, leve no verde; o claro fica por cima dela
      vignette.style.opacity = String(L.clamp(0.55 + 0.45 * w.escuro));
    },
  });

  const D = C.data || {};
  if (D.aviso) {
    let disc;
    const from = D.aviso_de != null ? D.aviso_de : 0.3;
    const to = D.aviso_ate != null ? D.aviso_ate : C.duration;
    registerLayer({
      z: 60,
      build(root) {
        disc = L.el('div', 'disclaimer', root, D.aviso);
        if (D.aviso_y != null) disc.style.top = `${D.aviso_y}px`;
      },
      render(t) {
        disc.style.opacity = String(L.seg(t, from, from + 0.4) * (1 - L.seg(t, to - 0.3, to)));
        // no fundo claro o aviso fica escuro
        const cl = modeAt(t).claro;
        disc.style.color = cl > 0.5 ? 'rgba(10,10,10,0.62)' : 'rgba(255,255,255,0.76)';
        disc.style.textShadow = cl > 0.5 ? 'none' : '0 2px 12px rgba(0,0,0,0.35)';
      },
    });
  }
})();
