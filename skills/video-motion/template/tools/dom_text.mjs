// Texto VISÍVEL na tela ao longo do vídeo (usado por tools/check_text.py --dom).
//   node tools/dom_text.mjs [--step 0.1]
// Imprime na última linha um JSON { texts: [{ t, text }], errors: [...] } com cada texto
// distinto e o primeiro instante em que aparece (elemento exibido e opacidade acumulada > 2%).
import { chromium, startServer, openPage, loadCues } from './common.mjs';

const args = process.argv.slice(2);
const step = Number(args.includes('--step') ? args[args.indexOf('--step') + 1] : 0.1);
const CUES = loadCues();
const times = [];
for (let t = 0; t < CUES.duration; t += step) times.push(+t.toFixed(4));
for (const e of CUES.timeline || []) times.push(e.t + 0.3);
const { srv, url } = await startServer();
const browser = await chromium.launch();
const { page, errors } = await openPage(browser, url);
const seen = new Map();
for (const t of times.sort((a, b) => a - b)) {
  const texts = await page.evaluate((tt) => {
    window.__render(tt);
    const out = [];
    const walker = document.createTreeWalker(document.getElementById('stage'), NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const s = n.textContent.replace(/\s+/g, ' ').trim();
      if (!s) continue;
      let e = n.parentElement, op = 1, vis = true;
      while (e) {
        const cs = getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') { vis = false; break; }
        op *= parseFloat(cs.opacity || '1');
        e = e.parentElement;
      }
      if (vis && op > 0.02) out.push(s);
    }
    return out;
  }, t);
  for (const s of texts) if (!seen.has(s)) seen.set(s, t);
}
await browser.close();
srv.close();
console.log(JSON.stringify({ texts: [...seen].map(([text, t]) => ({ t, text })), errors }));
