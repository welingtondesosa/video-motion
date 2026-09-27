// Biblioteca compartilhada das cenas. REGRA DE OURO: tudo é função pura do
// tempo. render(t) deve dar SEMPRE o mesmo quadro para o mesmo t, em qualquer
// ordem (o renderizador pula no tempo e grava subquadros pro motion blur).
// Nada de CSS transition/animation, setTimeout, Math.random ou Date.
(function () {
  const L = {};

  // ── Matemática e easing ───────────────────────────────────────────────
  L.clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  L.lerp = (a, b, p) => a + (b - a) * p;
  /** progresso 0..1 de t entre a e b */
  L.seg = (t, a, b) => (b === a ? (t >= b ? 1 : 0) : L.clamp((t - a) / (b - a)));
  L.ease = {
    linear: (p) => p,
    inQuad: (p) => p * p,
    outQuad: (p) => 1 - (1 - p) * (1 - p),
    inCubic: (p) => p * p * p,
    outCubic: (p) => 1 - Math.pow(1 - p, 3),
    inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    outQuint: (p) => 1 - Math.pow(1 - p, 5),
    inOutQuint: (p) => (p < 0.5 ? 16 * p ** 5 : 1 - Math.pow(-2 * p + 2, 5) / 2),
    outExpo: (p) => (p === 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    inExpo: (p) => (p === 0 ? 0 : Math.pow(2, 10 * p - 10)),
    outBack: (p, s = 1.70158) => 1 + (s + 1) * Math.pow(p - 1, 3) + s * Math.pow(p - 1, 2),
    outElastic: (p) => (p === 0 || p === 1 ? p : Math.pow(2, -10 * p) * Math.sin((p * 10 - 0.75) * (2 * Math.PI) / 3) + 1),
  };
  /** mola amortecida analítica: 0 → 1 com overshoot (freq em Hz, zeta 0..1) */
  L.spring = (t, freq = 3, zeta = 0.45) => {
    if (t <= 0) return 0;
    const w = 2 * Math.PI * freq;
    const wd = w * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w * t) * (Math.cos(wd * t) + (zeta * w / wd) * Math.sin(wd * t));
  };
  /** entrada com mola a partir de t0 */
  L.springIn = (t, t0, freq, zeta) => L.spring(t - t0, freq, zeta);
  /** pseudo-aleatório determinístico (sem Math.random) */
  L.hash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  /** tremor determinístico em px, amplitude a, frequência f */
  L.shake = (t, a, f = 28, seed = 1) => ({
    x: a * (Math.sin(t * f * 6.283 + seed) * 0.6 + Math.sin(t * f * 1.7 * 6.283 + seed * 3) * 0.4),
    y: a * (Math.cos(t * f * 5.1 + seed * 2) * 0.6 + Math.sin(t * f * 2.3 * 6.283 + seed) * 0.4),
  });
  /** decai de 1 a 0 depois de um pulso em t0 (duração d) */
  L.pulse = (t, t0, d) => (t < t0 || t > t0 + d ? 0 : 1 - (t - t0) / d);

  // ── DOM ────────────────────────────────────────────────────────────────
  L.el = (tag, cls, parent, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  };
  L.css = (e, obj) => { for (const k in obj) e.style[k] = obj[k]; return e; };
  /** aplica transform/opacity de uma vez; filtros opcionais */
  L.tf = (e, { x = 0, y = 0, s = 1, sx, sy, r = 0, o, blur, origin } = {}) => {
    const scx = sx != null ? sx : s, scy = sy != null ? sy : s;
    e.style.transform = `translate3d(${x}px, ${y}px, 0) rotate(${r}deg) scale(${scx}, ${scy})`;
    if (o != null) e.style.opacity = String(L.clamp(o));
    if (blur != null) e.style.filter = blur > 0.05 ? `blur(${blur}px)` : 'none';
    if (origin) e.style.transformOrigin = origin;
    return e;
  };
  L.show = (e, v) => { e.style.display = v ? '' : 'none'; };

  // ── Ícones (SVG simplificados; WhatsApp e Instagram só como canal) ──────
  L.icon = {
    whatsapp: `<svg viewBox="0 0 88 88"><circle cx="44" cy="44" r="44" fill="#25D366"/><path fill="#fff" d="M44 18c-14.4 0-26 11.4-26 25.5 0 4.9 1.4 9.5 3.9 13.4L18 70l13.5-3.6c3.7 2 8 3.1 12.5 3.1 14.4 0 26-11.4 26-25.5S58.4 18 44 18zm0 46.6c-4 0-7.8-1.1-11-3l-.8-.5-8 2.1 2.1-7.6-.5-.8c-2.1-3.3-3.2-7.1-3.2-11.2C22.6 32 32.2 22.6 44 22.6S65.4 32 65.4 43.6 55.8 64.6 44 64.6z"/><path fill="#fff" d="M55.6 49.4c-.6-.3-3.8-1.9-4.4-2.1-.6-.2-1-.3-1.4.3-.4.6-1.6 2-2 2.4-.4.4-.7.5-1.3.2-.6-.3-2.7-1-5.1-3.1-1.9-1.7-3.2-3.7-3.5-4.3-.4-.6 0-1 .3-1.3l1-1.1c.3-.4.4-.6.6-1 .2-.4.1-.8 0-1.1-.1-.3-1.4-3.4-1.9-4.6-.5-1.2-1-1-1.4-1h-1.2c-.4 0-1.1.2-1.7.8-.6.6-2.2 2.1-2.2 5.2s2.3 6 2.6 6.4c.3.4 4.5 6.8 10.8 9.5 1.5.7 2.7 1 3.6 1.3 1.5.5 2.9.4 4 .3 1.2-.2 3.8-1.5 4.3-3 .5-1.5.5-2.8.4-3-.1-.3-.5-.4-1.1-.7z"/></svg>`,
    instagram: `<svg viewBox="0 0 88 88"><defs><linearGradient id="igg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#F0A441"/><stop offset=".55" stop-color="#C94B8F"/><stop offset="1" stop-color="#8A3FB0"/></linearGradient></defs><rect width="88" height="88" rx="24" fill="url(#igg)"/><rect x="20" y="20" width="48" height="48" rx="15" fill="none" stroke="#fff" stroke-width="5.5"/><circle cx="44" cy="44" r="11.5" fill="none" stroke="#fff" stroke-width="5.5"/><circle cx="58.5" cy="29.5" r="3.6" fill="#fff"/></svg>`,
    email: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="24" fill="#4B5563"/><rect x="18" y="26" width="52" height="36" rx="6" fill="none" stroke="#fff" stroke-width="5"/><path d="M20 30l24 18 24-18" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/></svg>`,
    bot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>`,
    bell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="M4 2C2.8 3.7 2 5.7 2 8M22 8c0-2.3-.8-4.3-2-6"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`,
    ticks: (color) => `<svg viewBox="0 0 40 26"><path d="M2 14l7 7L22 5" fill="none" stroke="${color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 17l4 4L36 5" fill="none" stroke="${color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    moon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`,
    bolt: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>`,
    battery: (pct, color) => `<svg viewBox="0 0 54 26" width="54" height="26"><rect x="1.5" y="1.5" width="46" height="23" rx="6" fill="none" stroke="currentColor" stroke-width="2.6" opacity=".5"/><rect x="49.5" y="8" width="3.5" height="10" rx="1.5" fill="currentColor" opacity=".5"/><rect x="5" y="5" width="${Math.max(3, 39 * pct / 100)}" height="16" rx="3" fill="${color}"/></svg>`,
    plane: `<svg viewBox="0 0 120 100"><defs><linearGradient id="plg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#0E9788"/><stop offset=".5" stop-color="#30CD97"/><stop offset="1" stop-color="#A0E537"/></linearGradient></defs><path d="M4 46 116 4 78 96 58 62z" fill="url(#plg)"/><path d="M58 62 116 4 44 56z" fill="#0E6B5C" opacity=".55"/><path d="M58 62 64 84 78 96z" fill="#0B5B4F" opacity=".7"/></svg>`,
  };

  // ── Componentes ────────────────────────────────────────────────────────
  /**
   * Celular. Retorna { root, screen, status, setTime(text), setBattery(pct, color, label) }
   * battery: nível desenhado no ícone (padrão 64). batteryLabel: true escreve também "64%".
   * Padrão SEM número: todo dígito na tela precisa estar em numeros_ok (check_text --dom cobra).
   * battery: false esconde a bateria inteira.
   */
  L.makePhone = (parent, { x, y, w = 760, h = 1360, dark = false, time = '', battery = 64, batteryLabel = false } = {}) => {
    const root = L.el('div', 'phone', parent);
    L.css(root, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
    const screen = L.el('div', 'screen', root);
    if (dark) screen.style.background = '#0d1117';
    L.el('div', 'notch', root);
    const status = L.el('div', 'statusbar', screen);
    if (dark) status.style.color = '#fff';
    const timeEl = L.el('span', '', status, time);
    const batt = L.el('span', 'batt', status);
    const api = {
      root, screen, status,
      setTime: (txt) => { if (timeEl.textContent !== txt) timeEl.textContent = txt; },
      setBattery: (pct, color = '#34C759', label = batteryLabel) => {
        const key = `${pct}${color}${label}`;
        if (batt.dataset.k !== key) { batt.dataset.k = key; batt.innerHTML = `${label ? `${pct}% ` : ''}${L.icon.battery(pct, color)}`; }
      },
    };
    if (battery === false) batt.style.display = 'none';
    else api.setBattery(battery);
    return api;
  };

  L.AVATAR_COLORS = ['#F59E0B', '#EC4899', '#3B82F6', '#8B5CF6', '#10B981', '#EF4444', '#06B6D4', '#F97316'];
  L.avatar = (parent, name, idx = 0, size = 96) => {
    const a = L.el('div', 'avatar', parent, name.slice(0, 1).toUpperCase());
    L.css(a, { background: L.AVATAR_COLORS[idx % L.AVATAR_COLORS.length], width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.42)}px` });
    return a;
  };

  /** Cabeçalho de conversa dentro da tela */
  L.makeChatHead = (screen, { name, sub = 'online', idx = 0 }) => {
    const head = L.el('div', 'chathead', screen);
    const av = L.avatar(head, name, idx);
    const col = L.el('div', '', head);
    const who = L.el('div', 'who', col, name);
    const subEl = L.el('div', 'sub', col, sub);
    return {
      head, av, who, subEl,
      setName: (n, i = idx) => { if (who.textContent !== n) { who.textContent = n; av.textContent = n[0]; av.style.background = L.AVATAR_COLORS[i % L.AVATAR_COLORS.length]; } },
    };
  };

  /**
   * Conversa com balões que empilham de baixo pra cima.
   * messages: [{ side:'in'|'out'|'ai', text, at, time?, ticks?:(t)=>color|null, chip?:'ai'|null, out?:number }]
   * area: {top, bottom} em px dentro da tela. render(t) posiciona tudo.
   * chipH: espaço do selo acima do balão (padrão: altura medida do selo + 14 px).
   * Mede com todos os balões visíveis (balão escondido mediria 0), na 1ª render ou em measure().
   */
  L.makeChat = (screen, { top = 250, bottom, messages, chipH = null }) => {
    const H = bottom;
    const items = messages.map((m) => {
      const wrap = L.el('div', '', screen);
      L.css(wrap, { position: 'absolute', left: '0', right: '0', top: '0' });
      let chipEl = null;
      if (m.chip === 'ai') {
        chipEl = L.el('div', 'chip ai', wrap, `${L.icon.bot}${L.chipText('ai')}`);
        L.css(chipEl, { position: 'absolute', right: '34px', top: '0' });
      }
      const b = L.el('div', `bubble ${m.side}`, wrap);
      const txt = L.el('div', '', b, m.text);
      let tickEl = null;
      if (m.time || m.side !== 'in') {
        const meta = L.el('div', 'meta', b);
        if (m.time) L.el('span', '', meta, m.time);
        if (m.side !== 'in') tickEl = L.el('span', 'ticks', meta, L.icon.ticks('#9CA3AF'));
      }
      return { m, wrap, b, chipEl, tickEl, txt, h: 0, ch: 0 };
    });
    const measure = () => {
      // tudo visível na hora de medir (o celular e o chat podem estar escondidos no quadro atual)
      const hidden = [];
      for (let e = screen; e && e !== document.body; e = e.parentElement) {
        if (e.style.display === 'none') { hidden.push(e); e.style.display = ''; }
      }
      const prev = items.map((it) => it.wrap.style.display);
      for (const it of items) it.wrap.style.display = '';
      for (const it of items) {
        it.ch = it.chipEl ? (chipH != null ? chipH : it.chipEl.offsetHeight + 14) : 0;
        if (it.chipEl) it.b.style.top = `${it.ch}px`;
        it.h = it.b.offsetHeight + it.ch;
      }
      items.forEach((it, i) => { it.wrap.style.display = prev[i]; });
      for (const e of hidden) e.style.display = 'none';
    };
    const gap = 22;
    return {
      items,
      measure,
      render(t) {
        if (!items[0].h) measure();   // 1ª render já vem depois das fontes (main.js espera document.fonts)
        let yb = H - 26;
        for (let i = items.length - 1; i >= 0; i--) {
          const it = items[i];
          const p = L.seg(t, it.m.at, it.m.at + 0.38);
          if (t < it.m.at || (it.m.out != null && t >= it.m.out + 0.3)) { it.wrap.style.display = 'none'; continue; }
          it.wrap.style.display = '';
          const sp = L.clamp(L.springIn(t, it.m.at, 2.6, 0.62), 0, 1.2);
          const grow = L.ease.outCubic(p);
          const hEff = it.h * grow;
          const y = yb - it.h;
          yb = yb - hEff - gap * grow;
          const exitP = it.m.out != null ? L.seg(t, it.m.out, it.m.out + 0.3) : 0;
          const side = it.m.side === 'in' ? 'left bottom' : 'right bottom';
          L.tf(it.wrap, { y: y + (1 - grow) * 40, o: Math.min(1, p * 2.2) * (1 - exitP) });
          L.tf(it.b, { s: 0.82 + 0.18 * sp, origin: side });
          if (it.chipEl) L.tf(it.chipEl, { s: 0.82 + 0.18 * sp, origin: 'right bottom' });
          if (it.tickEl && it.m.ticks) {
            const c = it.m.ticks(t) || '#9CA3AF';
            if (it.tickEl.dataset.c !== c) { it.tickEl.dataset.c = c; it.tickEl.innerHTML = L.icon.ticks(c); }
          }
          if (y + it.h < top) it.wrap.style.display = 'none';
        }
      },
    };
  };

  /** Cartão de notificação (tela escura) */
  L.makeNotif = (parent, { channel = 'whatsapp', name = 'Cliente', when = 'agora', lines = [0.92, 0.64] } = {}) => {
    const n = L.el('div', 'notif', parent);
    L.el('div', 'ico', n, L.icon[channel]);
    const txt = L.el('div', 'txt', n);
    L.el('div', 'name', txt, name);
    const ls = L.el('div', 'lines', txt);
    for (const w of lines) L.css(L.el('i', '', ls), { width: `${Math.round(w * 100)}%` });
    L.el('div', 'when', n, when);
    return n;
  };

  /** Texto dos selos do app: vem do kit (textos.selo_ia / textos.selo_humano), senao o padrao. */
  L.chipText = (kind) => {
    const T = (window.BRAND && window.BRAND.textos) || {};
    return kind === 'ai' ? (T.selo_ia || 'IA atendendo') : (T.selo_humano || 'Pediu atendente');
  };
  /** Selo do app */
  L.makeChip = (parent, kind) => L.el('div', `chip ${kind}`, parent, kind === 'ai' ? `${L.icon.bot}${L.chipText('ai')}` : `${L.icon.bell}${L.chipText('human')}`);

  /**
   * Título em linhas, cada linha entra de baixo com leve desfoque.
   * lines: [{ text, at, size=120, color='#fff', cls='display', weight }]
   */
  L.makeHeadline = (parent, { y, lines, align = 'center', x = 90, w = 900 }) => {
    const box = L.el('div', '', parent);
    L.css(box, { position: 'absolute', left: `${x}px`, top: `${y}px`, width: `${w}px`, textAlign: align });
    const els = lines.map((ln) => {
      const e = L.el('div', ln.cls || 'display', box, ln.text);
      L.css(e, { fontSize: `${ln.size || 120}px`, color: ln.color || '#fff', whiteSpace: 'nowrap', willChange: 'transform' });
      if (ln.weight) e.style.fontWeight = ln.weight;
      if (ln.mt != null) e.style.marginTop = `${ln.mt}px`;
      return { e, ln };
    });
    return {
      box, els,
      render(t, outAt) {
        for (const { e, ln } of els) {
          const p = L.ease.outQuint(L.seg(t, ln.at, ln.at + 0.45));
          const o = outAt != null ? 1 - L.seg(t, outAt, outAt + 0.25) : 1;
          L.tf(e, { y: (1 - p) * 70, o: p * o, blur: (1 - p) * 10 });
        }
      },
    };
  };

  /**
   * Palavra cinética centralizada que entra com mola no instante `at` (e sai em `out`, opcional).
   * opts: { y=900, size=220, color='#fff', cls='display', from=0.55 (escala inicial), freq=3, zeta=0.42, rise=90 }
   * render(t) usa tempo GLOBAL. A mola começa exatamente em `at`: quadro de `at` já mostra o 1º movimento.
   */
  L.makeWord = (parent, text, { y = 900, size = 220, color = '#fff', cls = 'display', at = 0, out = null,
    from = 0.55, freq = 3, zeta = 0.42, rise = 90 } = {}) => {
    const e = L.el('div', cls, parent, text);
    L.css(e, { position: 'absolute', left: '0', width: '1080px', top: `${y}px`, textAlign: 'center',
      fontSize: `${size}px`, color, whiteSpace: 'nowrap', willChange: 'transform' });
    return {
      el: e,
      render(t) {
        if (t < at) { e.style.opacity = '0'; return; }
        const sp = L.springIn(t, at, freq, zeta);
        const o = Math.min(1, (t - at) / 0.08) * (out != null ? 1 - L.seg(t, out, out + 0.25) : 1);
        L.tf(e, { y: (1 - sp) * rise, s: from + (1 - from) * sp, o, blur: Math.max(0, (1 - Math.min(1, sp)) * 8), origin: '50% 60%' });
      },
    };
  };

  /** Logo completo (ícone PNG + palavra vetorial do SVG oficial) */
  /**
   * Logo de la marca, armado desde el kit (window.BRAND.logo, ver brand/marca.yaml):
   *   icono: archivo del isotipo (svg/png) · icono_escala: tamano relativo a height (1.1)
   *   palabra: { imagen | imagen_oscuro | imagen_claro }  o  { texto, peso, tracking, color_oscuro, color_claro, degradado }
   * dark = true: logo sobre fondo oscuro. Devuelve { box, icon, word } (box en position absolute).
   */
  L.makeLogo = (parent, { height = 150, dark = true } = {}) => {
    const B = (window.BRAND && window.BRAND.logo) || {};
    const box = L.el('div', '', parent);
    L.css(box, { position: 'absolute', display: 'flex', alignItems: 'center', gap: `${Math.round(height * (B.separacion || 0.16))}px` });
    let icon = null;
    if (B.icono) {
      icon = L.el('img', '', box);
      icon.src = `brand/${B.icono}`;
      const sz = Math.round(height * (B.icono_escala || 1.1));
      L.css(icon, { width: `${sz}px`, height: `${sz}px` });
    }
    const P = B.palabra || {};
    let word = null;
    const imgSrc = dark ? (P.imagen_oscuro || P.imagen) : (P.imagen_claro || P.imagen);
    if (imgSrc) {
      word = L.el('img', '', box);
      word.src = `brand/${imgSrc}`;
      L.css(word, { height: `${height}px`, width: 'auto' });
    } else if (P.texto) {
      word = L.el('div', 'display', box, P.texto);
      L.css(word, { fontSize: `${height}px`, lineHeight: '1', fontWeight: String(P.peso || 900), whiteSpace: 'nowrap',
        letterSpacing: P.tracking || '-0.025em', color: dark ? (P.color_oscuro || '#fff') : (P.color_claro || '#111') });
      if (P.degradado) {
        L.css(word, { backgroundImage: `linear-gradient(90deg, ${P.degradado.join(', ')})`, WebkitBackgroundClip: 'text', color: 'transparent' });
      }
    }
    return { box, icon, word, img: word };
  };

  window.L = L;
})();
