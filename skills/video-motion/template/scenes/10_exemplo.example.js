// Cenas de EXEMPLO do roteiro de demonstração (roteiro.example.yaml): uma palavra que entra
// com mola e o logo que pousa. Servem de molde: apague ou reescreva.
//
// REGRA DE OURO: render é função pura do tempo (sem transition, setTimeout, Math.random, Date).
// Todo instante vem de CUES (roteiro), nunca escrito à mão aqui: o áudio lê os mesmos números.
(function () {
  const C = CUES;
  const E = C.events;

  // Cena "palavra": cada palavra do roteiro cuja entrada cai nesta cena.
  let words = [];
  registerScene({
    id: 'palavra',
    post: 0.3, // continua visível 0,3 s depois do fim (sai durante a transição)
    build(root) {
      const sc = C.scenes.find((s) => s.id === 'palavra');
      words = C.words
        .filter((w) => w.at >= sc.start && w.at < sc.end)
        // tamanho cabe na largura útil (900 px): palavra longa fica menor, curta fica em 230 px
        .map((w) => L.makeWord(root, w.text, { at: w.at, out: sc.end - 0.45, y: 840,  // sai antes do logo (0,2 s de folga)
          size: Math.min(230, Math.floor(1800 / Math.max(1, w.text.length))) }));
    },
    render(tl, t) {
      for (const w of words) w.render(t);
    },
  });

  // Cena "logo": o logo cai no quadro exato de logo_in (mesmo tempo do impacto no áudio).
  let logo;
  registerScene({
    id: 'logo',
    pre: 0.05,
    build(root) {
      logo = L.makeLogo(root, { height: 132, dark: true });
      L.css(logo.box, { left: '0', width: '1080px', top: '880px', justifyContent: 'center' });
    },
    render(tl, t) {
      const sp = L.springIn(t, E.logo_in, 2.4, 0.5);
      L.tf(logo.box, { y: (1 - sp) * -160, s: 0.7 + 0.3 * sp, o: t < E.logo_in ? 0 : Math.min(1, (t - E.logo_in) / 0.06) });
    },
  });
})();
