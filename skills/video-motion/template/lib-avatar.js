// Avatar animado em código (SVG vetorial, estilo motion design). Carregue DEPOIS do lib.js:
//   <script src="lib.js"></script><script src="lib-avatar.js"></script>
// Personagem estilizado e fictício (cabeça grande, formas simples), não imita ninguém.
// REGRA DE OURO do lib.js vale aqui: tudo é função pura do tempo. Piscadas, respiração,
// balanço e gestos saem de fórmulas e de L.hash; a boca lê a trilha do tools/lipsync.py.
//
// const av = L.makeAvatar(parent, {
//   x, y, scale,                       // posição (px do quadro) do canto sup. esq. da caixa 600x1000
//   lipsync: LIPSYNC.fala,             // trilha do lipsync.py (tempo GLOBAL do vídeo)
//   palette: { skin, skinShade, hair, shirt, shirtShade, lip, cheek },  // opcional
//   hair: 'coque' | 'curto' | 'cacheado',                                // opcional
//   gestures: [                        // opcional; cada braço faz um gesto por vez
//     { type: 'wave',  arm: 'R', at: 0.2, until: 1.6 },          // acenar
//     { type: 'point', arm: 'R', at: 1.8, until: 3.6, angle: 100 },  // apontar (graus, 90 = horizontal pra fora)
//     { type: 'phone', arm: 'L', at: 4.0, until: 6.5 },          // segurar o celular na frente do peito
//   ],
//   look: [{ at: 0, x: 0, y: 0 }, { at: 1.9, x: 0.8, y: -0.2 }],  // olhar (-1..1), troca em 0,14 s
//   handPhone: { build(div) { ...; return (t) => {} } },  // tela do celular da mão (DOM do lib.js)
//   blinkSeed: 3, extraBlinks: [2.1],  // piscadas determinísticas + extras em tempos fixos
//   smile: 0.7,                        // sorriso de repouso 0..1
// });
// av.render(t)  // t = tempo global
// Braços: 'L' = lado esquerdo DO QUADRO, 'R' = lado direito do quadro.
(function () {
  const L = window.L;
  const { clamp, lerp, seg, ease } = L;
  const TAU = Math.PI * 2;
  let uid = 0;

  /** abertura/forma da boca da trilha no instante t (interpola entre quadros) */
  L.lipAt = (track, t) => {
    if (!track) return { open: 0, wide: 0, teeth: 0 };
    const f = t * track.fps, i = Math.floor(f), p = f - i, n = track.frames;
    if (i < 0 || i >= n - 1) return { open: 0, wide: 0, teeth: 0 };
    return {
      open: lerp(track.open[i], track.open[i + 1], p),
      wide: lerp(track.wide[i], track.wide[i + 1], p),
      teeth: lerp(track.teeth[i], track.teeth[i + 1], p),
    };
  };
  /** média da abertura em [t - win, t]: "está falando" suave, pra cabeça e sobrancelhas */
  L.talkEnergy = (track, t, win = 0.3) => {
    if (!track) return 0;
    let s = 0; const k = 10;
    for (let j = 0; j < k; j++) s += L.lipAt(track, t - (j / (k - 1)) * win).open;
    return s / k;
  };
  /** palavra falada no instante t (para legenda): índice em track.words ou -1 */
  L.wordAt = (track, t) => {
    if (!track || !track.words) return -1;
    for (let i = track.words.length - 1; i >= 0; i--) if (track.words[i].t0 != null && t >= track.words[i].t0) return i;
    return -1;
  };

  const PAL = {
    skin: '#E2A67C', skinShade: '#C98A62', hair: '#2A1C18', hairHi: '#4A3129',
    shirt: '#2C8247', shirtShade: '#226B38', collar: '#1A5C2E',
    lip: '#8E3B3B', mouth: '#4A1320', tongue: '#E07A80', cheek: '#F08A7E', eye: '#1E1717', brow: '#2A1C18',
  };

  // ângulos: 0 = braço pra baixo, 90 = horizontal pra fora, 180 = pra cima, negativo = pra dentro
  const POSES = {
    idle: { a1: 9, a2: 4, hand: 'relaxed' },
    wave: { a1: 128, a2: 168, hand: 'open' },
    point: { a1: 96, a2: 104, hand: 'point' },
    phone: { a1: 18, a2: -108, hand: 'phone' },
  };
  const UP = 150, FORE = 136; // comprimentos (unidades do SVG 600x1000)

  L.makeAvatar = (parent, opts = {}) => {
    const n = ++uid;
    const P = Object.assign({}, PAL, opts.palette || {});
    const hairStyle = opts.hair || 'coque';
    const smile0 = opts.smile != null ? opts.smile : 0.7;
    const track = opts.lipsync || null;
    const gestures = (opts.gestures || []).slice().sort((a, b) => a.at - b.at);
    const looks = (opts.look || [{ at: 0, x: 0, y: 0 }]).slice().sort((a, b) => a.at - b.at);
    const seed = opts.blinkSeed != null ? opts.blinkSeed : 1;
    const extraBlinks = opts.extraBlinks || [];
    const W = 600, H = 1000, sc = opts.scale || 1;

    const box = L.el('div', '', parent);
    L.css(box, { position: 'absolute', left: `${opts.x || 0}px`, top: `${opts.y || 0}px`, width: `${W * sc}px`, height: `${H * sc}px` });

    const hairBack = {
      coque: `<circle cx="300" cy="150" r="62" fill="${P.hair}"/><path d="M168 300 C160 200 220 132 300 132 C380 132 440 200 432 300 L432 372 C420 330 410 300 404 280 L196 280 C190 300 180 330 168 372 Z" fill="${P.hair}"/>`,
      curto: `<path d="M172 300 C164 196 226 128 300 128 C374 128 436 196 428 300 L420 318 C414 270 400 240 380 228 L220 228 C200 240 186 270 180 318 Z" fill="${P.hair}"/>`,
      cacheado: `<g fill="${P.hair}">${[[190, 240, 58], [236, 176, 62], [300, 150, 66], [364, 176, 62], [410, 240, 58], [176, 316, 46], [424, 316, 46], [300, 196, 70]].map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}"/>`).join('')}</g>`,
    }[hairStyle];
    const hairFront = {
      coque: `<path d="M180 262 C186 186 246 150 306 152 C360 154 404 180 418 238 C384 214 330 206 292 220 C250 234 214 238 180 262 Z" fill="${P.hair}"/><path d="M262 172 C300 160 344 166 372 184" fill="none" stroke="${P.hairHi}" stroke-width="7" stroke-linecap="round" opacity=".7"/>`,
      curto: `<path d="M178 258 C182 184 240 146 304 148 C366 150 414 186 420 250 C398 222 360 206 320 214 C300 196 262 196 232 214 C212 226 194 240 178 258 Z" fill="${P.hair}"/><path d="M250 170 C286 158 330 160 360 176" fill="none" stroke="${P.hairHi}" stroke-width="7" stroke-linecap="round" opacity=".7"/>`,
      cacheado: `<g fill="${P.hair}">${[[208, 214, 40], [254, 188, 42], [300, 180, 44], [346, 188, 42], [392, 214, 40]].map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}"/>`).join('')}</g>`,
    }[hairStyle];

    const svgNS = 'http://www.w3.org/2000/svg';
    box.innerHTML = `
<svg xmlns="${svgNS}" viewBox="0 0 ${W} ${H}" width="${W * sc}" height="${H * sc}" style="display:block;overflow:visible">
  <defs>
    <clipPath id="mclip${n}"><path data-k="mclip"/></clipPath>
    <linearGradient id="shirtg${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${P.shirt}"/><stop offset="1" stop-color="${P.shirtShade}"/></linearGradient>
  </defs>
  <g data-k="all">
    <ellipse cx="300" cy="996" rx="230" ry="18" fill="#000" opacity=".18"/>
    <g data-k="torso">
      <path d="M150 1000 L158 600 C160 548 196 516 250 506 L350 506 C404 516 440 548 442 600 L450 1000 Z" fill="url(#shirtg${n})"/>
      <path d="M252 506 L300 566 L348 506 Z" fill="${P.skinShade}"/>
      <path d="M244 504 L300 574 L356 504" fill="none" stroke="${P.collar}" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="372" cy="640" r="23" fill="#fff" opacity=".96"/>
      <image href="${(window.BRAND && window.BRAND.logo && window.BRAND.logo.icono) ? "brand/" + window.BRAND.logo.icono : ""}" x="354" y="622" width="36" height="36"/>
    </g>
    <g data-k="headwrap">
      <path d="M268 420 L268 512 C284 528 316 528 332 512 L332 420 Z" fill="${P.skinShade}"/>
      <g data-k="head">
        <g data-k="hairback">${hairBack}</g>
        <g data-k="ears">
          <circle cx="178" cy="306" r="25" fill="${P.skinShade}"/><circle cx="422" cy="306" r="25" fill="${P.skinShade}"/>
        </g>
        <path d="M176 290 C176 196 232 154 300 154 C368 154 424 196 424 290 C424 382 370 444 300 444 C230 444 176 382 176 290 Z" fill="${P.skin}"/>
        <g data-k="face">
          <circle cx="226" cy="358" r="22" fill="${P.cheek}" opacity=".32"/>
          <circle cx="374" cy="358" r="22" fill="${P.cheek}" opacity=".32"/>
          <g data-k="browL"><path d="M228 262 Q248 250 268 258" fill="none" stroke="${P.brow}" stroke-width="10" stroke-linecap="round"/></g>
          <g data-k="browR"><path d="M332 258 Q352 250 372 262" fill="none" stroke="${P.brow}" stroke-width="10" stroke-linecap="round"/></g>
          <g data-k="eyeL"><ellipse cx="248" cy="304" rx="14" ry="18" fill="${P.eye}"/><circle cx="253" cy="297" r="4.5" fill="#fff"/></g>
          <g data-k="eyeR"><ellipse cx="352" cy="304" rx="14" ry="18" fill="${P.eye}"/><circle cx="357" cy="297" r="4.5" fill="#fff"/></g>
          <path d="M296 322 Q304 344 292 350" fill="none" stroke="${P.skinShade}" stroke-width="7" stroke-linecap="round"/>
          <g data-k="mouth" transform="translate(300 386)">
            <path data-k="mfill" fill="${P.mouth}"/>
            <g clip-path="url(#mclip${n})">
              <ellipse data-k="tongue" cx="0" cy="20" rx="22" ry="12" fill="${P.tongue}"/>
              <rect data-k="teeth" x="-60" y="-40" width="120" height="0" fill="#fff"/>
            </g>
            <path data-k="mline" fill="none" stroke="${P.lip}" stroke-width="5.5" stroke-linejoin="round" stroke-linecap="round"/>
          </g>
        </g>
        <g data-k="hairfront">${hairFront}</g>
      </g>
    </g>
    <g data-k="armL"></g>
    <g data-k="armR"></g>
  </g>
</svg>`;
    const svg = box.firstElementChild;
    const q = (k) => svg.querySelector(`[data-k="${k}"]`);
    const E = {
      all: q('all'), torso: q('torso'), headwrap: q('headwrap'), head: q('head'), face: q('face'), ears: q('ears'),
      hairfront: q('hairfront'), hairback: q('hairback'), browL: q('browL'), browR: q('browR'), eyeL: q('eyeL'), eyeR: q('eyeR'),
      mfill: q('mfill'), mclip: q('mclip'), mline: q('mline'), teeth: q('teeth'), tongue: q('tongue'),
    };

    // ── braços ────────────────────────────────────────────────────────────
    const mk = (tag, attrs, parentEl) => {
      const e = document.createElementNS(svgNS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      parentEl.appendChild(e);
      return e;
    };
    const arms = {};
    for (const side of ['L', 'R']) {
      const g = q(`arm${side}`);
      const sx = side === 'L' ? -1 : 1;
      const upper = mk('line', { stroke: P.shirt, 'stroke-width': 58, 'stroke-linecap': 'round' }, g);
      const fore = mk('line', { stroke: P.skin, 'stroke-width': 44, 'stroke-linecap': 'round' }, g);
      const sleeve = mk('circle', { r: 31, fill: P.shirtShade }, g); // barra da manga no cotovelo
      const hand = mk('g', {}, g);
      // mão em coordenadas locais: origem no pulso, +y ao longo do antebraço, polegar em -x
      const relaxed = mk('g', {}, hand);
      mk('ellipse', { cx: 0, cy: 24, rx: 25, ry: 29, fill: P.skin }, relaxed);
      mk('ellipse', { cx: -20, cy: 16, rx: 9, ry: 15, fill: P.skinShade, transform: 'rotate(24 -20 16)' }, relaxed);
      const open = mk('g', {}, hand);
      for (const [fx, len, rot] of [[-18, 58, -26], [-6, 66, -9], [7, 64, 8], [19, 54, 25]]) {
        mk('rect', { x: fx - 8, y: 30, width: 16, height: len, rx: 8, fill: P.skin, transform: `rotate(${rot} ${fx} 36)` }, open);
      }
      mk('ellipse', { cx: 0, cy: 30, rx: 29, ry: 28, fill: P.skin }, open);
      mk('rect', { x: -42, y: 4, width: 16, height: 44, rx: 8, fill: P.skin, transform: 'rotate(-58 -32 26)' }, open);
      mk('path', { d: 'M-8 26 Q2 36 14 30', fill: 'none', stroke: P.skinShade, 'stroke-width': 4, 'stroke-linecap': 'round', opacity: 0.8 }, open);
      const point = mk('g', {}, hand);
      mk('rect', { x: -2, y: 30, width: 16, height: 58, rx: 8, fill: P.skin }, point);
      mk('circle', { cx: 0, cy: 26, r: 26, fill: P.skin }, point);
      mk('path', { d: 'M-16 18 Q-2 30 8 34', fill: 'none', stroke: P.skinShade, 'stroke-width': 5, 'stroke-linecap': 'round' }, point);
      // celular na mão: a mão fica no desenho do aparelho (de pé), a palma e os dedos
      // atrás dele, o polegar na frente, na borda de baixo à esquerda
      const phone = mk('g', {}, hand);
      const dev = mk('g', {}, phone);
      mk('ellipse', { cx: 22, cy: 206, rx: 36, ry: 40, fill: P.skinShade }, dev);
      for (const fy of [150, 178, 206]) mk('ellipse', { cx: 152, cy: fy, rx: 13, ry: 12, fill: P.skinShade }, dev);
      mk('rect', { x: 0, y: 0, width: 150, height: 290, rx: 24, fill: '#141416' }, dev);
      const scr = mk('g', {}, dev);
      let screenRender = null;
      if (opts.handPhone && opts.handPhone.build && side === (opts.handPhone.arm || 'L')) {
        // tela real do app (DOM do lib.js) dentro de um foreignObject
        const fo = mk('foreignObject', { x: 0, y: 0, width: 380, height: 760, transform: 'translate(7 7) scale(0.358)' }, scr);
        const div = document.createElement('div');
        L.css(div, { width: '380px', height: '760px', position: 'relative', overflow: 'hidden', borderRadius: '48px', background: '#fff' });
        fo.appendChild(div);
        screenRender = opts.handPhone.build(div) || null;
      } else {
        mk('rect', { x: 7, y: 7, width: 136, height: 276, rx: 18, fill: '#fff' }, scr);
        mk('rect', { x: 7, y: 7, width: 136, height: 44, rx: 18, fill: P.shirtShade }, scr);
        mk('rect', { x: 16, y: 66, width: 80, height: 26, rx: 12, fill: '#EEF0F2' }, scr);
        mk('rect', { x: 46, y: 104, width: 88, height: 40, rx: 12, fill: '#F5F3FF', stroke: '#DDD6FE', 'stroke-width': 2 }, scr);
        mk('rect', { x: 70, y: 152, width: 64, height: 14, rx: 7, fill: 'rgba(139,92,246,.25)' }, scr);
        mk('rect', { x: 60, y: 178, width: 74, height: 26, rx: 12, fill: '#226B38' }, scr);
      }
      mk('rect', { x: 59, y: 12, width: 32, height: 9, rx: 4.5, fill: '#050505' }, dev);
      const thumb = mk('rect', { x: -10, y: 158, width: 20, height: 52, rx: 10, fill: P.skin, transform: 'rotate(24 0 210)' }, dev);
      arms[side] = { sx, upper, fore, sleeve, hand, relaxed, open, point, phone, dev, thumb, screenRender };
    }

    // ── tempo: piscadas, olhar, gestos ────────────────────────────────────
    const blinkShape = (d) => (d < 0 || d > 0.2 ? 0 : d < 0.07 ? ease.inQuad(d / 0.07) : d < 0.1 ? 1 : 1 - ease.outQuad((d - 0.1) / 0.1));
    const blinkAt = (t) => {
      let v = 0;
      let b = 0.6 + L.hash(seed * 7.3) * 1.6, i = 0;
      while (b <= t + 0.01 && i < 400) {
        v = Math.max(v, blinkShape(t - b));
        if (L.hash(seed * 13.1 + i * 3.7) < 0.2) v = Math.max(v, blinkShape(t - b - 0.28)); // piscada dupla
        b += 2.3 + L.hash(seed * 3.1 + i * 1.9) * 2.4;
        i++;
      }
      for (const e of extraBlinks) v = Math.max(v, blinkShape(t - e));
      return v;
    };
    const lookAt = (t) => {
      let x = looks[0].x || 0, y = looks[0].y || 0;
      for (let i = 1; i < looks.length; i++) {
        const k = looks[i];
        const p = ease.inOutCubic(seg(t, k.at, k.at + 0.14));
        if (p <= 0) break;
        x = lerp(x, k.x || 0, p); y = lerp(y, k.y || 0, p);
      }
      return { x, y };
    };
    const IN = 0.42, OUT = 0.38;
    const armPose = (side, t) => {
      let a1 = POSES.idle.a1, a2 = POSES.idle.a2;
      const hw = { relaxed: 1, open: 0, point: 0, phone: 0 };
      let phoneW = 0;
      for (const g of gestures) {
        if ((g.arm || (g.type === 'phone' ? 'L' : 'R')) !== side) continue;
        if (t < g.at) continue;
        // entrada com mola (passa um pouco do ponto), saída suave
        const win = clamp(L.spring(t - g.at, 1.9, 0.62), 0, 1.12);
        const wout = g.until != null ? 1 - ease.inOutCubic(seg(t, g.until - OUT, g.until)) : 1;
        const w = win * wout;
        if (w <= 0) continue;
        const pose = POSES[g.type];
        let b1 = pose.a1, b2 = pose.a2;
        if (g.type === 'point' && g.angle != null) { b1 = g.angle - 6; b2 = g.angle + 4; }
        if (g.type === 'wave') {
          const ph = (t - g.at) * (g.rate || 2.3) * TAU;
          b2 += 20 * Math.sin(ph); b1 += 4 * Math.sin(ph + 0.8);
        }
        if (g.type === 'point') { const d = t - g.at - 0.35; b2 += d > 0 ? 3 * Math.sin(d * 1.3 * TAU) * Math.exp(-d * 0.8) : 0; }
        if (g.type === 'phone') { b2 += 2 * Math.sin((t - g.at) * 0.9 * TAU); phoneW = Math.max(phoneW, ease.outCubic(clamp((w - 0.35) / 0.55))); }
        a1 = lerp(a1, b1, w); a2 = lerp(a2, b2, w);
        const hp = clamp(w / 0.6);
        for (const k in hw) hw[k] = lerp(hw[k], k === pose.hand ? 1 : 0, hp);
      }
      return { a1, a2, hw, phoneW };
    };

    // ── boca ──────────────────────────────────────────────────────────────
    const mouthPath = (o, w, s) => {
      const hwid = 36 * (1 + 0.2 * Math.max(0, w) - 0.36 * Math.max(0, -w)) * (1 - 0.12 * o * Math.max(0, -w));
      const Hm = 60 * o;
      const k = lerp(0.52, 0.95, Math.max(0, -w));         // bico: curva mais redonda
      const cy = -9 * s;                                     // cantos sobem com o sorriso
      const top = (-Hm * 0.3) / 0.75;
      const bot = (Hm * 0.7 + 2.2 + 3 * s) / 0.75;
      const d = `M${-hwid} ${cy} C${-hwid * k} ${top} ${hwid * k} ${top} ${hwid} ${cy} C${hwid * k} ${bot} ${-hwid * k} ${bot} ${-hwid} ${cy} Z`;
      return { d, hwid, topY: 0.25 * cy + 0.75 * top, botY: 0.25 * cy + 0.75 * bot };
    };

    const api = {
      box, svg,
      render(t) {
        const breath = Math.sin((t / 3.8) * TAU);
        const talk = L.talkEnergy(track, t, 0.35);
        const lk = lookAt(t);
        // corpo e cabeça
        E.torso.setAttribute('transform', `translate(300 1000) scale(1 ${1 + 0.008 * breath}) translate(-300 -1000)`);
        const sway = 1.6 * Math.sin(t * 0.19 * TAU + 0.3) + 0.9 * Math.sin(t * 0.43 * TAU + 1.7);
        const tilt = sway + 2.2 * talk * Math.sin(t * 0.9 * TAU) + lk.x * 3;
        const hy = -3 * breath - 7 * talk + 2 * Math.sin(t * 2.1 * TAU) * talk;
        E.headwrap.setAttribute('transform', `translate(0 ${hy}) rotate(${tilt} 300 500)`);
        // "virada" da cabeça: rosto anda com o olhar, orelhas e cabelo de trás no sentido oposto
        const fx = lk.x * 12, fy = lk.y * 7;
        E.face.setAttribute('transform', `translate(${fx} ${fy})`);
        E.hairfront.setAttribute('transform', `translate(${fx * 0.45} ${fy * 0.3})`);
        E.ears.setAttribute('transform', `translate(${-fx * 0.35} 0)`);
        E.hairback.setAttribute('transform', `translate(${-fx * 0.25} 0)`);
        // olhos (piscada) e pupilas
        const bl = blinkAt(t);
        const ex = lk.x * 5, ey = lk.y * 4;
        E.eyeL.setAttribute('transform', `translate(${ex} ${ey}) translate(248 304) scale(1 ${Math.max(0.08, 1 - bl)}) translate(-248 -304)`);
        E.eyeR.setAttribute('transform', `translate(${ex} ${ey}) translate(352 304) scale(1 ${Math.max(0.08, 1 - bl)}) translate(-352 -304)`);
        const brow = -9 * clamp(talk * 1.8 - 0.2) + 3 * bl;
        E.browL.setAttribute('transform', `translate(0 ${brow})`);
        E.browR.setAttribute('transform', `translate(0 ${brow - 1.5 * clamp(talk * 2)}) rotate(${-3 * clamp(talk * 2)} 352 258)`);
        // boca
        const m = L.lipAt(track, t);
        const s = smile0 * (1 - 0.55 * clamp(m.open * 1.4));
        const mp = mouthPath(m.open, m.wide, s);
        E.mfill.setAttribute('d', mp.d); E.mclip.setAttribute('d', mp.d); E.mline.setAttribute('d', mp.d);
        E.teeth.setAttribute('y', String(mp.topY - 2));
        E.teeth.setAttribute('height', String(Math.max(0, 15 * m.teeth)));
        E.tongue.setAttribute('cy', String(mp.botY - 5));
        E.tongue.setAttribute('rx', String(mp.hwid * 0.62));
        E.tongue.setAttribute('ry', String(4 + 12 * m.open));
        // braços
        for (const side of ['L', 'R']) {
          const A = arms[side], sx = A.sx;
          const pose = armPose(side, t);
          const shX = 300 + sx * 132, shY = 560 - 3 * breath;
          const r1 = (pose.a1 * Math.PI) / 180, r2 = (pose.a2 * Math.PI) / 180;
          const elX = shX + sx * Math.sin(r1) * UP, elY = shY + Math.cos(r1) * UP;
          const wrX = elX + sx * Math.sin(r2) * FORE, wrY = elY + Math.cos(r2) * FORE;
          for (const [e, x1, y1, x2, y2] of [[A.upper, shX, shY, elX, elY], [A.fore, elX, elY, wrX, wrY]]) {
            e.setAttribute('x1', x1); e.setAttribute('y1', y1); e.setAttribute('x2', x2); e.setAttribute('y2', y2);
          }
          A.sleeve.setAttribute('cx', lerp(shX, elX, 0.82)); A.sleeve.setAttribute('cy', lerp(shY, elY, 0.82));
          const phi = -sx * pose.a2;
          A.hand.setAttribute('transform', `translate(${wrX} ${wrY}) rotate(${phi}) scale(${sx} 1)`);
          const vis = (e, o) => { e.setAttribute('opacity', String(clamp(o))); e.style.display = o > 0.01 ? '' : 'none'; };
          vis(A.relaxed, pose.hw.relaxed); vis(A.open, pose.hw.open); vis(A.point, pose.hw.point);
          // celular: fica em pé na tela, mesmo com o antebraço inclinado
          const pw = pose.phoneW;
          vis(A.phone, pose.hw.phone > 0.01 ? Math.max(pose.hw.phone, 0.001) : 0);
          if (pose.hw.phone > 0.01) {
            const ps = (0.55 + 0.45 * pw) * (opts.handPhoneScale || 1);
            // desfaz a rotação da mão (e o espelho) para o aparelho ficar de pé, levemente inclinado
            A.dev.setAttribute('transform', `scale(${sx} 1) rotate(${-phi - 7 * sx}) translate(${-22 * ps} ${-200 * ps}) scale(${ps})`);
            A.dev.setAttribute('opacity', String(clamp(pw * 1.4)));
            if (A.screenRender) A.screenRender(t);
          }
        }
      },
    };
    return api;
  };
})();
