// Dev shim for the world module (Playwright add_init_script). Emulates what src/template.html provides per AGENTS.md §3-4
// until the heatmap owner's change lands: tabs 해외 / 원자재 before ★관심, <div id="world" hidden> right after <main class="layout">,
// hash #world / #cmdty, KH.market() → 'world' | 'cmdty', main.layout hidden while a world tab is active,
// KHWorld.show(kind) / hide() calls, and the "module missing" fallback text.
// If the template already has #world (owner's change merged) the shim does nothing.
(() => {
  if (window.__kwShim) return;
  window.__kwShim = true;
  let real;
  Object.defineProperty(window, 'KH', {
    configurable: true,
    get() { return real; },
    set(v) { real = v; try { augment(v); } catch (e) { console.warn('world shim', e); } },
  });
  function augment(KH) {
    if (document.getElementById('world')) return;           // the real template hooks exist
    const tabs = document.querySelector('.tabs');
    const watchBtn = tabs.querySelector('[data-mkt="WATCH"]');
    const mk = (m, t) => { const b = document.createElement('button'); b.dataset.mkt = m; b.textContent = t; b.setAttribute('aria-pressed', 'false'); return b; };
    const bW = mk('WORLD', '해외'), bC = mk('CMDTY', '원자재');
    tabs.insertBefore(bW, watchBtn); tabs.insertBefore(bC, watchBtn);
    const main = document.querySelector('main.layout');
    const world = document.createElement('div');
    world.id = 'world'; world.hidden = true;
    main.after(world);
    let cur = null;                                           // 'WORLD' | 'CMDTY' | null
    const origMarket = KH.market;
    KH.market = () => cur === 'WORLD' ? 'world' : cur === 'CMDTY' ? 'cmdty' : origMarket();
    function activate(m, writeHash) {
      cur = m;
      main.hidden = true; main.style.display = 'none'; world.hidden = false;
      for (const b of tabs.querySelectorAll('button[data-mkt]')) b.setAttribute('aria-pressed', String(b.dataset.mkt === m));
      if (writeHash) location.hash = m === 'WORLD' ? 'world' : 'cmdty';
      if (window.KHWorld) window.KHWorld.show(m === 'WORLD' ? 'index' : 'commodity');
      else world.textContent = '해외·원자재 화면을 불러오지 못했어요. 새로 고침해 주세요.';
    }
    function deactivate() {
      if (!cur) return;
      cur = null;
      if (window.KHWorld) window.KHWorld.hide();
      world.hidden = true; main.hidden = false; main.style.display = '';
      window.dispatchEvent(new Event('resize'));
    }
    tabs.addEventListener('click', e => {
      const b = e.target.closest('button[data-mkt]');
      if (!b) return;
      if (b === bW || b === bC) { e.stopImmediatePropagation(); activate(b.dataset.mkt, true); return; }
      deactivate();
      // the template's setMarket() returns early for the market it already has: re-sync the pressed state
      setTimeout(() => { const m = origMarket(); for (const x of tabs.querySelectorAll('button[data-mkt]')) if (x === bW || x === bC) x.setAttribute('aria-pressed', 'false'); }, 0);
    }, true);
    addEventListener('hashchange', () => {
      const h = location.hash.slice(1);
      if (h === 'world' || h === 'cmdty') activate(h === 'world' ? 'WORLD' : 'CMDTY', false);
      else if (cur && h !== '') deactivate();
    });
    const h0 = location.hash.slice(1);
    if (h0 === 'world' || h0 === 'cmdty') activate(h0 === 'world' ? 'WORLD' : 'CMDTY', false);
  }
})();
