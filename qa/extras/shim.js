// Dev shim for the extras module (Playwright add_init_script).
// The template provides the §3-2 hooks now (#strip, #extras-tools, KH.layout, KH.setReplay, kh:render); the shim keeps them and
// only records what extras asks for (window.__shimReplay = {t, n} | null). Fallbacks for an older template stay below.
// It hooks the moment the template assigns window.KH (end of the heatmap script, before extras.js runs).
// window.__KH_SHIM = { noLayout, noReplay, noMounts } turns single hooks off to test feature detection.
(() => {
  if (window.__khShimInstalled) return;
  window.__khShimInstalled = true;
  const opt = () => window.__KH_SHIM || {};
  let real;
  Object.defineProperty(window, 'KH', {
    configurable: true,
    get() { return real; },
    set(v) { real = v; try { augment(v); } catch (e) { console.warn('shim', e); } },
  });

  function augment(KH) {
    if (!opt().noMounts) {
      const hdr = document.querySelector('header.top');
      if (hdr && !document.getElementById('strip')) { const d = document.createElement('div'); d.id = 'strip'; hdr.after(d); }
      const tools = document.querySelector('.tools');
      if (tools && !document.getElementById('extras-tools')) { const d = document.createElement('div'); d.id = 'extras-tools'; tools.append(d); }
    }
    const map = () => document.getElementById('map');
    const px = v => parseFloat(v) || 0;

    if (opt().noLayout) delete KH.layout;
    if (opt().noReplay) delete KH.setReplay;
    if (opt().noMounts) for (const id of ['strip', 'extras-tools']) { const el = document.getElementById(id); if (el) el.remove(); }
    // the template's own replay: keep it, record the frame extras sent
    if (!opt().noReplay && typeof KH.setReplay === 'function') {
      const real = KH.setReplay;
      KH.setReplay = (f, o) => { window.__shimReplay = f && f.prices ? { t: f.t, n: f.prices.size } : null; return real(f, o); };
    }
    if (!opt().noLayout && typeof KH.layout !== 'function') KH.layout = () => {
      const m = map();
      if (!m || m.hidden) return [];
      const out = [];
      for (const el of m.querySelectorAll('.node')) {
        if (el.classList.contains('leaving')) continue;
        const kind = el.classList.contains('tile') ? 'tile' : el.classList.contains('sec') ? 'sector' : 'ind';
        const box = { kind, x: px(el.style.left), y: px(el.style.top), w: px(el.style.width), h: px(el.style.height) };
        if (kind === 'tile') {
          const st = KH.stock(el.dataset.c);
          const pc = el.querySelector('.pc');
          box.color = el.style.backgroundColor;
          box.label = st ? st.n : el.querySelector('.nm').textContent;
          box.sub = pc ? pc.textContent : '';
          box.code = el.dataset.c;
        } else {
          const hd = el.querySelector('.hd');
          const shown = hd && hd.style.display !== 'none';
          box.color = kind === 'sector' ? '#000' : '#0d0e11';
          box.label = shown ? hd.children[0].textContent : '';
          box.sub = shown ? hd.children[1].textContent : '';
        }
        out.push(box);
      }
      return out;
    };

    if (!opt().noReplay && typeof KH.setReplay !== 'function') {
      let frame = null;
      const saved = new Map();   // code -> [bg, pctText]
      const apply = () => {
        const m = map();
        if (!m) return;
        for (const el of m.querySelectorAll('.tile')) {
          const c = el.dataset.c, pc = el.querySelector('.pc');
          if (frame) {
            if (!saved.has(c)) saved.set(c, [el.style.backgroundColor, pc ? pc.textContent : '']);
            const q = frame.prices.get(c);
            el.style.backgroundColor = q ? KH.colorOf(q.r) : '#2a2c33';
            if (pc) pc.textContent = q ? KH.fmt.pct(q.r, 1) : '';
          } else if (saved.has(c)) {
            const [bg, t] = saved.get(c);
            el.style.backgroundColor = bg;
            if (pc) pc.textContent = t;
          }
        }
        if (!frame) saved.clear();
        document.dispatchEvent(new CustomEvent('kh:render'));
      };
      KH.setReplay = f => { frame = f && f.prices ? f : null; window.__shimReplay = frame ? { t: frame.t, n: frame.prices.size } : null; apply(); };
      // live polls re-render the map after kh:data: put the replay colours back
      document.addEventListener('kh:data', () => { if (frame) setTimeout(() => { saved.clear(); apply(); }, 0); });
    }
  }
})();
