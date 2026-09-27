// Motor: registra cenas e desenha o quadro de qualquer instante t (segundos).
// Cada cena: registerScene({ id, pre, post, build(root), render(tl, t) })
//   id    = id em CUES.scenes (define start/end)
//   pre   = segundos antes do start em que a cena já aparece (transição)
//   post  = segundos depois do end em que ainda aparece
//   tl    = tempo local (t - start); t = tempo global
// Uma cena pode ocupar um GRUPO de ids: registerScene({ id:'dores', span:['hook','dor3'], ... })
(function () {
  const scenes = [];
  const layers = []; // camadas globais (fundo, aviso), sempre renderizadas
  window.registerScene = (s) => scenes.push(s);
  window.registerLayer = (l) => layers.push(l);

  const byId = Object.fromEntries(CUES.scenes.map((s) => [s.id, s]));
  function bounds(s) {
    const ids = s.span || [s.id, s.id];
    for (const id of ids) {
      if (!byId[id]) throw new Error(`registerScene: cena "${id}" nao existe no roteiro (cues.js). Cenas: ${Object.keys(byId).join(', ')}`);
    }
    return { start: byId[ids[0]].start, end: byId[ids[1]].end };
  }

  async function init() {
    const stage = document.getElementById('stage');
    // Camadas globais atrás (z baixo), cenas no meio, camadas "top" por cima.
    for (const l of layers) {
      l.el = L.el('div', 'layer', stage);
      l.el.style.zIndex = String(l.z != null ? l.z : 0);
      l.build(l.el);
    }
    for (const s of scenes) {
      const b = bounds(s);
      s.start = b.start; s.end = b.end;
      s.el = L.el('div', 'layer', stage);
      s.el.style.zIndex = String(s.z != null ? s.z : 10);
      s.el.dataset.scene = s.id;
      s.build(s.el);
    }
    await document.fonts.ready;
    // Garante imagens decodificadas antes do 1º quadro.
    await Promise.all(Array.from(document.images).map((im) => (im.decode ? im.decode().catch(() => {}) : Promise.resolve())));
    // Mede balões (depende das fontes carregadas).
    window.__render(0);
    window.__render(0);
  }

  window.__render = (t) => {
    for (const l of layers) l.render(t);
    for (const s of scenes) {
      const vis = t >= s.start - (s.pre || 0) && t < s.end + (s.post || 0);
      s.el.style.display = vis ? '' : 'none';
      if (vis) s.render(t - s.start, t);
    }
  };

  window.__ready = new Promise((res) => {
    window.addEventListener('load', () => { init().then(res); });
  });
})();
