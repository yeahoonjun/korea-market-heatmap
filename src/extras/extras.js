/* Extras: market strip, save as image, install as app (PWA), intraday replay.
   Contract: AGENTS.md §3 (window.KH) and §3-2 (KH.layout, KH.setReplay, #strip, #extras-tools, kh:render,
   Worker /api/market, /api/replay/dates, /api/replay). Every hook is feature-detected: a missing one hides its feature. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function') return;          // the heatmap script did not boot
const h = KH.h;
const LIVE = KH.MODE === 'live';
const MINUS = '−';
const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
const narrowMQ = matchMedia('(max-width: 760px)');
const $ = (s, el = document) => el.querySelector(s);
const has = name => typeof KH[name] === 'function';
const SVGNS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs || {}) el.setAttribute(k, attrs[k]);
  for (const kid of kids) if (kid) el.append(kid);
  return el;
}
const ICON = {
  image: 'M3 5.5A2.5 2.5 0 0 1 5.5 3h9A2.5 2.5 0 0 1 17 5.5v9a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 3 14.5zM3.5 13l3.8-3.6 3 2.8 2.2-2 4 3.6M12.5 7.2h.01',
  replay: 'M10 3.5a6.5 6.5 0 1 1-6.1 4.3M3.5 3.8v4.2h4.2M10 6.8V10l2.4 1.6',
  install: 'M10 3v9m0 0-3.5-3.5M10 12l3.5-3.5M4 13.5v1A2.5 2.5 0 0 0 6.5 17h7a2.5 2.5 0 0 0 2.5-2.5v-1',
  play: 'M6.5 4.6v10.8a.6.6 0 0 0 .9.5l8.6-5.4a.6.6 0 0 0 0-1L7.4 4.1a.6.6 0 0 0-.9.5z',
  pause: 'M6 4.5h2.6v11H6zM11.4 4.5H14v11h-2.6z',
  close: 'M5 5l10 10M15 5 5 15',
  up: 'M10 15.5v-11M5.5 9 10 4.5 14.5 9',
  down: 'M10 4.5v11M5.5 11l4.5 4.5 4.5-4.5',
};
const icon = (d, fill) => svg('svg', { viewBox: '0 0 20 20', width: '18', height: '18', 'aria-hidden': 'true', fill: fill ? 'currentColor' : 'none',
  stroke: fill ? 'none' : 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg('path', { d }));

/* ───────── themes (docs/standards/themes.md): the role tokens of <html data-theme · data-tone>, read when they are needed ───────── */
const rootEl = document.documentElement;
const lightTone = () => rootEl.dataset.tone === 'light';
const tok = (name, d) => { const v = getComputedStyle(rootEl).getPropertyValue(name).trim(); return v || d; };
const rgbParts = c => {
  const m = /^rgba?\(([^)]+)\)/i.exec(c || ''), x = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(c || '').trim());
  if (m) return m[1].split(/[\s,\/]+/).slice(0, 3).map(Number);
  if (x) { const v = x[1].length === 3 ? x[1].replace(/./g, '$&$&') : x[1]; return [0, 2, 4].map(i => parseInt(v.slice(i, i + 2), 16)); }
  return null;
};
// black or white, whichever reads better on the tile colour (the template's data-labs="auto", light themes)
const inkOn = col => {
  const c = rgbParts(col);
  if (!c) return '#000';
  const L = c.map(x => { x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }).reduce((s, x, i) => s + x * [.2126, .7152, .0722][i], 0);
  return (L + .05) / .05 >= 1.05 / (L + .05) ? '#000' : '#fff';
};
const withAlpha = (col, a) => { const c = rgbParts(col); return c ? `rgba(${c[0]},${c[1]},${c[2]},${a})` : col; };

/* ───────── living controls (docs/standards/controls.md): the template's KH.ui helpers and --c-* tokens, used when present ───────── */
const UI = KH.ui && typeof KH.ui.state === 'function' && typeof KH.ui.bubble === 'function' ? KH.ui : null;
const tokMs = (name, d) => (UI && typeof UI.ms === 'function' ? UI.ms(name) : d);          // '줄이기' sets --c-fast/base/switch to 0
// one label (or icon) per state, stacked in one cell; KH.ui.state(el, st) shows the one whose data-l names st (the box keeps the widest)
const kl = (st, kids, tag) => h(tag || 'span', { class: 'kl' + (st === 'idle' ? ' on' : ''), 'data-l': st }, kids);
const uiIcon = name => (UI && typeof UI.icon === 'function' ? UI.icon(name) : null);
function setState(el, st) {
  if (!el) return;
  if (UI) { UI.state(el, st); return; }
  el.dataset.st = st;
  for (const x of el.querySelectorAll('.kl')) x.classList.toggle('on', x.matches(`[data-l~="${st}"]`));
}

/* ───────── formatting ───────── */
const sgn = v => v > 0 ? '+' : v < 0 ? MINUS : '';
const fixed = (v, dp) => Math.abs(v).toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const pct = v => (KH.fmt && KH.fmt.pct) ? KH.fmt.pct(v) : sgn(v) + Math.abs(v).toFixed(2) + '%';
const dir = v => v > 0 ? 'xs-up' : v < 0 ? 'xs-dn' : 'xs-flat';
const KST = 'Asia/Seoul';
const fmtHM = new Intl.DateTimeFormat('ko-KR', { timeZone: KST, hour: '2-digit', minute: '2-digit', hour12: false });
const fmtStamp = new Intl.DateTimeFormat('ko-KR', { timeZone: KST, month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
const fmtDay = new Intl.DateTimeFormat('ko-KR', { timeZone: 'UTC', month: 'long', day: 'numeric', weekday: 'short' });
const dayLabel = ymd => { const [y, m, d] = ymd.split('-').map(Number); return fmtDay.format(new Date(Date.UTC(y, m - 1, d))); };
const hhmm = t => String(t).replace(/^(\d\d):?(\d\d)$/, '$1:$2');
const kstYmd = d => new Intl.DateTimeFormat('en-CA', { timeZone: KST, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);

async function getJSON(url, ms = 12000) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms);
  try {
    const res = await fetch(url, { cache: 'no-store', signal: ac.signal });
    let body = null;
    try { body = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) { const err = new Error((body && body.error) || 'HTTP ' + res.status); err.status = res.status; throw err; }
    return body;
  } finally { clearTimeout(timer); }
}

/* ───────── toast (polite live region) ───────── */
let toastEl = null, toastTimer = 0;
function toast(msg) {
  if (!toastEl) { toastEl = h('div', { class: 'xt-toast', role: 'status', 'aria-live': 'polite' }); document.body.append(toastEl); }
  toastEl.textContent = msg;
  if (!msg) return;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 3200);
}

/* ═════════════ 1. Market strip ═════════════ */
const STRIP = {
  KOSPI: { label: '코스피', dp: 2, chg: true },
  KOSDAQ: { label: '코스닥', dp: 2, chg: true },
  USDKRW: { label: '원/달러', dp: 2, chg: true, unit: '원' },
  SPX_F: { label: 'S&P500 선물', dp: 2 },
  NDX_F: { label: '나스닥100 선물', dp: 2 },
  WTI: { label: 'WTI', dp: 2, unit: '달러/배럴' },
  GOLD: { label: '금', dp: 2, unit: '달러/온스', full: '국제 금' },
  BTC: { label: '비트코인', dp: 0, unit: '원', full: '비트코인(업비트)' },
};
const stripEl = document.getElementById('strip');
const strip = { items: null, asOf: null, at: 0, timer: 0, failed: false, busy: false };

function sparkSvg(spark, base) {
  const pts = (spark || []).filter(p => Array.isArray(p) && isFinite(p[0]) && isFinite(p[1]));
  if (pts.length < 2) return null;
  const W = 46, H = 26;
  const t0 = pts[0][0];
  const day0 = Math.floor((t0 + 32400) / 86400) * 86400 - 32400;     // 00:00 KST of the first bar
  let a = day0 + 9 * 3600, b = day0 + 15.5 * 3600;                   // x axis = the regular session 09:00–15:30
  if (pts[pts.length - 1][0] > b || t0 < a) { a = Math.min(a, t0); b = Math.max(b, pts[pts.length - 1][0]); }
  const tl = pts[pts.length - 1][0];
  if ((tl - t0) < (b - a) * 0.4) { a = t0; b = tl; }                  // early in the session: stretch the few points over the width
  const ys = pts.map(p => p[1]);
  if (isFinite(base)) ys.push(base);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const x = t => ((t - a) / (b - a)) * W;
  const y = v => hi === lo ? H / 2 : H - 1.5 - ((v - lo) / (hi - lo)) * (H - 3);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + x(p[0]).toFixed(1) + ' ' + y(p[1]).toFixed(1)).join('');
  const last = pts[pts.length - 1][1];
  const ref = isFinite(base) ? base : pts[0][1];
  const el = svg('svg', { class: 'xs-spark ' + dir(last - ref), viewBox: `0 0 ${W} ${H}`, width: W, height: H, 'aria-hidden': 'true' });
  if (isFinite(base)) el.append(svg('line', { x1: 0, x2: W, y1: y(base).toFixed(1), y2: y(base).toFixed(1), class: 'xs-base' }));
  el.append(svg('path', { d, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.4', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  el.append(svg('circle', { cx: Math.min(W - 2, Math.max(2, x(pts[pts.length - 1][0]))).toFixed(1), cy: y(last).toFixed(1), r: '2', fill: 'currentColor' }));
  return el;
}

// 101,655,000 → "1억 166만" (the strip is tight; the tooltip keeps the full number)
function krwShort(v) {
  const man = Math.round(Math.abs(v) / 1e4);
  if (man < 1e4) return man.toLocaleString('ko-KR') + '만';
  const eok = Math.floor(man / 1e4), rest = man % 1e4;
  return eok.toLocaleString('ko-KR') + '억' + (rest ? ' ' + rest.toLocaleString('ko-KR') + '만' : '');
}
function stripItem(it) {
  const def = it.def || STRIP[it.key] || { label: it.name || it.key, dp: 2 };
  const v = +it.value, c = +it.change, r = +it.ratio;
  if (it.none) {          // a picked item whose data did not arrive: grey "—" (§3-22)
    const d = `${def.label} 시세를 불러오지 못했어요`;
    return h('div', { class: 'xs-item xs-none', role: 'button', tabindex: '0', 'data-k': it.key, title: d, 'aria-label': d },
      h('span', { class: 'xs-txt' }, h('span', { class: 'xs-l1' }, h('span', { class: 'xs-k', text: def.label })), h('span', { class: 'xs-l2' }, h('span', { class: 'xs-v', text: '—' }))));
  }
  if (it.value == null || !isFinite(v)) return null;
  // two lines: name (+ change or delay) on top, value + % below; indices get a sparkline on the right
  const top = [h('span', { class: 'xs-k', text: def.label })];
  if (def.chg && isFinite(c)) top.push(h('span', { class: 'xs-c ' + dir(c), text: sgn(c) + fixed(c, def.dp) }));
  if (it.delayed) top.push(h('span', { class: 'xs-d', text: `${it.delayed}분 지연` }));
  const bot = [h('span', { class: 'xs-v', text: it.key === 'BTC' && v >= 1e8 ? krwShort(v) : fixed(v, def.dp) })];
  if (isFinite(r)) bot.push(h('span', { class: 'xs-r ' + dir(r), text: pct(r) }));
  const kids = [h('span', { class: 'xs-txt' }, h('span', { class: 'xs-l1' }, top), h('span', { class: 'xs-l2' }, bot))];
  const sp = it.spark ? sparkSvg(it.spark, isFinite(c) ? v - c : NaN) : null;
  if (sp) kids.push(sp);
  const name = def.full || def.label;
  const desc = `${name} ${fixed(v, def.dp)}${def.unit ? ' ' + def.unit : ''}` +
    (isFinite(c) ? `, 전일 대비 ${sgn(c)}${fixed(c, def.dp)}` : '') + (isFinite(r) ? ` (${pct(r)})` : '') +
    (it.delayed ? `, ${it.delayed}분 지연 시세` : '');
  return h('div', { class: 'xs-item', role: 'button', tabindex: '0', 'aria-haspopup': 'dialog', 'data-k': it.key, title: desc + ' · 누르면 자세히 봐요', 'aria-label': desc }, kids);
}

/* ── §3-22 ticker: what flows, what a tap opens, how it pauses ── */
const TKI_KEY = 'khm.tickerItems';
const TK_WORLD = { SPX_F: 'EScv1', NDX_F: 'NQcv1', WTI: 'CLcv1', GOLD: 'GCcv1', KOSPI: 'KOSPI', KOSDAQ: 'KOSDAQ', USDKRW: 'FX_USDKRW' };   // strip key → /api/world key
const TK_SEARCH = { USDKRW: '원달러 환율', BTC: '비트코인 시세' };
const tkn = id => (String(id).includes(':') ? String(id) : 'm:' + id);
function tkiGet() {
  try { const a = JSON.parse(localStorage.getItem(TKI_KEY)); return Array.isArray(a) && a.length && a.every(x => typeof x === 'string') ? a.map(tkn) : null; } catch (e) { return null; }
}
function tkiSave(a) {
  try { if (a && a.length) localStorage.setItem(TKI_KEY, JSON.stringify(a)); else localStorage.removeItem(TKI_KEY); } catch (e) { /* kept for this page only */ }
  tkiMem = a && a.length ? a.slice() : null;
  document.dispatchEvent(new CustomEvent('kh:tkitems'));
}
let tkiMem = undefined;
const tkIds = () => (tkiMem !== undefined ? tkiMem : (tkiMem = tkiGet()));
const tkx = { w: new Map(), q: new Map(), names: new Map(), groups: new Map() };            // world key → item, code → quote row
const watchCodes = gid => { try { return has('watch') || (KH.watch && KH.watch.list) ? (KH.watch.list(gid === 'all' ? undefined : gid) || []).map(String) : []; } catch (e) { return []; } };
function tkCodes(ids) {
  const out = [];
  for (const id of ids) {
    if (id.startsWith('s:')) out.push(id.slice(2));
    else if (id.startsWith('g:')) out.push(...watchCodes(id.slice(2)));
  }
  return [...new Set(out)];
}
// the data the picked items need beyond /api/market (every poll, 30 s)
const tkWorldWanted = ids => ids.some(x => x.startsWith('w:'));
async function tkAux(force) {
  const ids = Array.isArray(force) ? force : (tkIds() || []);
  if (force !== true && !tkIds() && !Array.isArray(force)) return;
  if (!LIVE) return;
  const jobs = [];
  if (force === true || tkWorldWanted(ids)) {
    jobs.push(Promise.all(['index', 'commodity'].map(k => getJSON('api/world?kind=' + k).then(j => {
      for (const g of (j && j.groups) || []) for (const it of g.items || []) if (it && it.key != null) { tkx.w.set(String(it.key), it); tkx.names.set(String(it.key), it.name); }
      tkx.groups.set(k, ((j && j.groups) || []).map(g => ({ key: g.key, name: g.name, items: (g.items || []).map(i => ({ key: String(i.key), name: i.name })) })));
      return true;
    }).catch(() => false))));
  }
  // §3-24 stock items read the heatmap's quote store (KH.quote: one row per code, the chosen price basis); only codes the store does
  // not hold are fetched here, and what comes back feeds the store (KH.quotes.put) so the map, tabs and stock page see it too
  const tracked = c => { try { return !!(KH.quotes && typeof KH.quotes.tracked === 'function' && KH.quotes.tracked(c)); } catch (e) { return false; } };
  const codes = tkCodes(ids).filter(c => !tracked(c));               // the heatmap keeps the main stream and its theme / 관심 codes fresh
  for (let i = 0; i < codes.length; i += 300) {
    const part = codes.slice(i, i + 300);
    jobs.push(getJSON('api/quotes?codes=' + part.join(',')).then(j => {
      const rows = (j && j.stocks) || [];
      for (const r of rows) { tkx.q.set(String(r.c), r); tkx.names.set('s:' + r.c, r.n); }
      try { if (KH.quotes && typeof KH.quotes.put === 'function') KH.quotes.put(rows, j && j.asOf); } catch (e) { /* the ticker keeps its own copy */ }
    }).catch(() => { /* "—" */ }));
  }
  await Promise.all(jobs);
}
function tkStockItem(code) {
  let q = null;
  try { q = has('quote') ? KH.quote(code) : null; } catch (e) { q = null; }
  const r = q || tkx.q.get(code), nm = (r && r.n) || tkx.names.get('s:' + code) || code;
  if (!r || r.p == null || !isFinite(+r.p)) return { key: 's:' + code, name: nm, none: true, def: { label: nm, dp: 0 } };
  if (r.n) tkx.names.set('s:' + code, r.n);
  return { key: 's:' + code, name: nm, value: +r.p, change: +r.d, ratio: +r.r, def: { label: nm, dp: 0, unit: '원', full: nm } };
}
// 코스피 / 코스닥 items: the quotes' index (the tabs' numbers, every poll) when it is newer than /api/market's; the spark stays
function tkIndexItem(it) {
  if (!it || (it.key !== 'KOSPI' && it.key !== 'KOSDAQ') || !has('index') || !has('asOf')) return it;
  try {
    const x = (KH.index() || {})[it.key], qa = Date.parse(KH.asOf()), ma = Date.parse(strip.asOf);
    if (!x || !isFinite(+x.value) || !(+x.value > 0) || !(qa >= ma || !isFinite(ma))) return it;
    return Object.assign({}, it, { value: +x.value, change: +x.change, ratio: +x.ratio });
  } catch (e) { return it; }
}
function tkSource() {
  const ids = tkIds();
  if (!ids || !strip.items) return strip.items && strip.items.map(tkIndexItem);     // the Worker's own set, in its order
  const byKey = new Map(strip.items.map(i => [i.key, tkIndexItem(i)]));
  const out = [], seen = new Set();
  const push = it => { if (!seen.has(it.key)) { seen.add(it.key); out.push(it); } };
  for (const id of ids) {
    if (id.startsWith('m:')) { const k = id.slice(2); push(byKey.get(k) || { key: k, name: (STRIP[k] || {}).label || k, none: true, def: { label: (STRIP[k] || {}).label || k, dp: 2 } }); }
    else if (id.startsWith('w:')) {
      const k = id.slice(2), it = tkx.w.get(k), nm = (it && it.name) || tkx.names.get(k) || k;
      push(it && it.value != null ? { key: id, name: nm, value: +it.value, change: +it.change, ratio: +it.ratio, def: { label: nm, dp: 2, full: nm } } : { key: id, name: nm, none: true, def: { label: nm, dp: 2 } });
    } else if (id.startsWith('s:')) push(tkStockItem(id.slice(2)));
    else if (id.startsWith('g:')) for (const c of watchCodes(id.slice(2))) push(tkStockItem(c));
  }
  return out;
}

// pause: only while a finger / button is down (+2 s), while a detail window is open, or by the ⏸ button (persistent)
const tkHold = { down: false, detail: false, timer: 0, moved: false, held: false };
function tkHoldApply() {
  const held = tkHold.down || tkHold.detail || !!tkHold.timer;
  stripEl.classList.toggle('xs-hold', held);
  if (tkHold.held && !held) tkResume();
  tkHold.held = held;
}
// the loop picks its speed up again over --c-slow (ease-out) instead of jumping to it; '줄이기': at once
let tkRampRaf = 0;
function tkAnim() { try { return tk.track && tk.track.getAnimations ? tk.track.getAnimations()[0] || null : null; } catch (e) { return null; } }
function tkRate(a, r) { try { if (a.updatePlaybackRate) a.updatePlaybackRate(r); else a.playbackRate = r; } catch (e) { /* keeps its speed */ } }
function tkResume() {
  cancelAnimationFrame(tkRampRaf);
  const a = tkAnim();
  if (!a) return;
  const dur = motion() === 'reduced' ? 0 : tokMs('--c-slow', 560);
  if (!(dur > 0) || document.hidden) { tkRate(a, 1); return; }
  const t0 = performance.now();
  const go = now => { const k = Math.min(1, (now - t0) / dur); tkRate(a, Math.max(0.05, 1 - Math.pow(1 - k, 3))); if (k < 1) tkRampRaf = requestAnimationFrame(go); };
  tkRate(a, 0.05);
  tkRampRaf = requestAnimationFrame(go);
}
function tkRelease() {
  if (!tkHold.down) return;
  tkHold.down = false;
  clearTimeout(tkHold.timer);
  tkHold.timer = setTimeout(() => { tkHold.timer = 0; tkHoldApply(); }, 2000);
  tkHoldApply();
}
function tkBindPointer(vp) {
  let x0 = 0, id = null, anim = null, startX = 0, dx = 0, glide = 0, pts = [];
  const curX = () => { try { return new DOMMatrix(getComputedStyle(tk.track).transform).m41; } catch (e) { return 0; } };
  // drag = scrub: the loop's time follows the finger (negative x runs forward)
  const scrub = d => {
    if (!anim || !tk.W) return;
    const p = ((((-(x0 + d)) % tk.W) + tk.W) % tk.W) / tk.W;
    try { anim.currentTime = p * tk.dur * 1000; } catch (err) { /* stays put */ }
  };
  vp.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    cancelAnimationFrame(glide); cancelAnimationFrame(tkRampRaf);
    tkHold.down = true; tkHold.moved = false; clearTimeout(tkHold.timer); tkHold.timer = 0; tkHoldApply();
    id = e.pointerId; startX = e.clientX; x0 = curX(); dx = 0; pts = [[e.timeStamp, e.clientX]];
    anim = tkAnim();
  });
  vp.addEventListener('pointermove', e => {
    if (!tkHold.down || e.pointerId !== id) return;
    const d = e.clientX - startX;
    pts.push([e.timeStamp, e.clientX]); if (pts.length > 8) pts.shift();
    if (!tkHold.moved && Math.abs(d) < 8) return;
    if (!tkHold.moved) { tkHold.moved = true; stripEl.classList.add('xs-drag'); }      // a drag, not a press: the item under the finger rises again
    dx = d; scrub(dx);
  });
  const up = e => {
    if (id == null || (e && e.pointerId !== id)) return;
    id = null;
    // a flick glides on and comes to rest over --c-slow (ease-out, a third of the release speed × the time); '줄이기' stops where it was let go
    if (tkHold.moved && motion() !== 'reduced' && pts.length > 1) {
      const last = pts[pts.length - 1], first = pts.find(q => last[0] - q[0] <= 100) || pts[0];
      const v = last[0] > first[0] ? (last[1] - first[1]) / (last[0] - first[0]) : 0;          // px per ms
      const T = tokMs('--c-slow', 560);
      if (Math.abs(v) > 0.3 && T > 0) {
        const base = dx, D = v * T / 3, t0 = performance.now();
        const step = n => { const k = Math.min(1, (n - t0) / T); dx = base + D * (1 - Math.pow(1 - k, 3)); scrub(dx); if (k < 1) glide = requestAnimationFrame(step); };
        glide = requestAnimationFrame(step);
      }
    }
    setTimeout(() => stripEl.classList.remove('xs-drag'), 0);
    tkRelease();
  };
  vp.addEventListener('pointerup', up);
  vp.addEventListener('pointercancel', up);
  vp.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') up(e); });
}

// tap / Enter → the item's detail
let tkWatch = 0, tkOpener = null;
function tkDetailOpen() {
  const k = window.KHStock, w = window.KHWorld;
  return !!((k && k.isOpen && k.isOpen()) || (w && w.detailOpen && w.detailOpen()) || document.querySelector('dialog.xk-info[open]'));
}
function tkDetailHold(on) {
  tkHold.detail = on; tkHoldApply();
  clearInterval(tkWatch); tkWatch = 0;
  if (!on) return;
  const t0 = Date.now();
  tkWatch = setInterval(() => {
    if (Date.now() - t0 < 1200 || tkDetailOpen()) return;           // the sheet / page needs a moment to appear
    tkDetailHold(false);
    const op = tkOpener && tkOpener.isConnected ? tkOpener : tkOpener && stripEl.querySelector(`.xs-list:first-child .xs-item[data-k="${CSS.escape(tkOpener.dataset.k)}"]`);
    tkOpener = null;
    if (op && op.focus && document.activeElement === document.body) { try { op.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
  }, 250);
}
function tkInfo(id, name, it, opener) {
  const k = id.slice(2);
  const url = id.startsWith('s:') ? `https://m.stock.naver.com/domestic/stock/${encodeURIComponent(k)}` : `https://m.search.naver.com/search.naver?query=${encodeURIComponent(TK_SEARCH[k] || name)}`;
  const vtxt = it && it.value != null ? `${fixed(+it.value, (it.def && it.def.dp != null ? it.def.dp : 2))}${isFinite(+it.ratio) ? ' (' + pct(+it.ratio) + ')' : ''}` : '';
  makeDialog('xk-info', name, opener, [
    h('h2', { class: 'xd-h', text: name }),
    vtxt ? h('p', { class: 'xk-v ' + dir(+it.ratio), text: vtxt }) : null,
    h('p', { class: 'xd-p', text: '이 항목은 앱 안에 자세한 화면이 없어요. 네이버 증권에서 볼 수 있어요.' }),
    h('a', { class: 'xk-link', href: url, target: '_blank', rel: 'noopener', text: '네이버 증권에서 보기' }),
  ].filter(Boolean));
}
async function tkOpen(rawId, el) {
  const id = tkn(rawId), key = id.slice(2);
  const src = (tkSource() || []).find(i => tkn(i.key) === id) || null;
  const name = (src && (src.name || (src.def && src.def.label))) || (STRIP[key] || {}).label || key;
  tkOpener = el; tkDetailHold(true);
  try {
    if (id.startsWith('s:')) {
      if (window.KHStock && window.KHStock.open) { window.KHStock.open(key, { opener: el }); return; }
      tkInfo(id, name, src, el); return;
    }
    const wk = id.startsWith('w:') ? key : TK_WORLD[key];
    if (wk && window.KHWorld && typeof window.KHWorld.openDetail === 'function') {
      let today = null;
      if (id.startsWith('m:') && (key === 'KOSPI' || key === 'KOSDAQ')) {
        const it = (strip.items || []).find(x => x.key === key);
        if (it && Array.isArray(it.spark) && it.spark.length > 1) today = { pts: it.spark.map(p => [+p[0], +p[1]]), base: isFinite(+it.change) ? +it.value - +it.change : null };
      }
      const ok = await window.KHWorld.openDetail(wk, { opener: el, today });
      if (ok) return;
    }
    tkInfo(id.startsWith('m:') || id.startsWith('w:') ? id : 'm:' + key, name, src, el);
  } catch (e) { tkDetailHold(false); }
}
function tkBindClicks() {
  stripEl.addEventListener('click', e => {
    const it = e.target.closest && e.target.closest('.xs-item');
    if (!it || !stripEl.contains(it)) return;
    if (tkHold.moved) { tkHold.moved = false; return; }               // that was a drag, not a tap
    tkOpen(it.dataset.k, it);
  });
  stripEl.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const it = e.target.closest && e.target.closest('.xs-item');
    if (!it || e.target !== it) return;
    if (!e.repeat) it.classList.add('is-press');                       // the key look while the key is down (the template lifts it on keyup / blur)
    e.preventDefault(); tkOpen(it.dataset.k, it);
  });
}

/* ── §3-22 picker: 표시 설정 → 티커 항목 (bottom sheet on phones) ── */
const TK_FIXED = {
  dom: [['m:KOSPI', '코스피'], ['m:KOSDAQ', '코스닥']],
  fx: [['m:USDKRW', '원/달러']],
  fut: [['m:SPX_F', 'S&P 500 선물'], ['m:NDX_F', '나스닥 100 선물']],
  cr: [['m:BTC', '비트코인']],
};
const TK_CATS = [['dom', '국내 지수'], ['wi', '해외 지수'], ['fx', '환율'], ['fut', '선물'], ['cm', '원자재'], ['cr', '가상자산'], ['st', '개별 종목'], ['wl', '관심종목']];
const tkDefaultIds = () => (strip.items || []).map(i => 'm:' + i.key);
function tkLabel(id) {
  if (id.startsWith('m:')) { const k = id.slice(2), f = Object.values(TK_FIXED).flat().find(x => x[0] === id); return f ? f[1] : (STRIP[k] || {}).label || k; }
  if (id.startsWith('w:')) return tkx.names.get(id.slice(2)) || id.slice(2);
  if (id.startsWith('s:')) return tkx.names.get(id) || id.slice(2);
  if (id.startsWith('g:')) { const g = id.slice(2); if (g === 'all') return '관심종목 전체'; try { const x = (KH.watch.groups() || []).find(y => y.id === g); return x ? `관심종목 · ${x.name}` : '관심종목 그룹'; } catch (e) { return '관심종목'; } }
  return id;
}
function tkPicker(opener) {
  let list = (tkIds() || tkDefaultIds()).slice();
  let cat = 'dom', names = null, q = '';
  const say = t => (UI ? UI.live(t) : toast(t));
  const commit = () => { tkiSave(list); tk.sig = ''; renderStrip(); tkAux().then(() => renderStrip()).catch(() => {}); };
  const has_ = id => list.includes(id);
  const body = h('div', { class: 'xk-body' });
  const catName = k => (TK_CATS.find(c => c[0] === k) || [k, k])[1];
  // 분류 = a segment (controls.md §5-4): deep tray, one raised indicator that slides (KH.ui.seg), the row scrolls sideways on phones
  const cats = h('div', { class: 'xk-cats seg', role: 'group', 'aria-label': '분류' },
    TK_CATS.map(([k, l]) => h('button', { type: 'button', class: 'xk-cat', 'data-c': k, 'aria-pressed': String(cat === k), onclick: e => pickCat(k, e.currentTarget) }, l)));
  const pane = h('div', { class: 'xk-pane', role: 'group', 'aria-label': catName(cat) });
  const selBox = h('div', { class: 'xk-selbox' });
  // 추가 ↔ 추가됨 = a toggle chip at the end of its row (§5-7): fill + ring, a check that grows in, the label swapped in its box
  const chip = on => h('span', { class: 'xk-chk', 'aria-hidden': 'true', 'data-st': on ? 'on' : 'off' }, h('i', { class: 'xk-ck' }),
    h('span', { class: 'klb' }, h('span', { class: 'kl' + (on ? '' : ' on'), 'data-l': 'off' }, '추가'), h('span', { class: 'kl' + (on ? ' on' : ''), 'data-l': 'on' }, '추가됨')));
  const pick = (id, label, sub) => h('button', { type: 'button', class: 'xk-row', 'data-id': id, 'aria-pressed': String(has_(id)), onclick: () => toggle(id) },
    h('span', { class: 'xk-nm', text: label }), sub ? h('small', { text: sub }) : null, chip(has_(id)));
  // rows change in place (the chip moves; focus stays on the row)
  const syncRows = () => {
    for (const b of pane.querySelectorAll('.xk-row[data-id]')) {
      const on = has_(b.dataset.id);
      if (b.getAttribute('aria-pressed') === String(on)) continue;
      b.setAttribute('aria-pressed', String(on));
      setState(b.querySelector('.xk-chk'), on ? 'on' : 'off');
    }
  };
  const toggle = (id, fromSel) => {
    const i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    commit(); drawSel(); syncRows(); syncReset();
    if (fromSel) {          // the ✕ of a row that is gone: focus the ✕ now in its place (or the 분류 row when the list is empty)
      const rm = selBox.querySelectorAll('.xk-rm');
      const nx = rm[Math.min(i, rm.length - 1)] || cats.querySelector('[aria-pressed="true"]');
      if (nx) nx.focus();
    }
  };
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    commit(); drawSel(); syncReset();
    const b = selBox.querySelector(`.xk-sel li:nth-child(${j + 1}) button[data-mv="${d}"]`);
    if (b && !b.disabled) b.focus(); else { const o = selBox.querySelector(`.xk-sel li:nth-child(${j + 1}) button[data-mv="${-d}"]`); if (o) o.focus(); }
  };
  function drawSel() {
    selBox.replaceChildren(
      h('h3', { class: 'xk-h3' }, '지금 흐르는 항목 ', h('small', { text: `${list.length}개` })),
      list.length ? h('ol', { class: 'xk-sel' }, list.map((id, i) => h('li', {},
        h('span', { class: 'xk-nm', text: tkLabel(id) }),
        // ↑ ↓ ✕ = keys without a surface (§5-1), dimmed at the ends (§5-12)
        h('button', { type: 'button', class: 'xk-mv', 'data-mv': '-1', 'aria-label': `${tkLabel(id)} 위로`, title: '위로', disabled: i === 0, onclick: () => move(i, -1) }, icon(ICON.up)),
        h('button', { type: 'button', class: 'xk-mv', 'data-mv': '1', 'aria-label': `${tkLabel(id)} 아래로`, title: '아래로', disabled: i === list.length - 1, onclick: () => move(i, 1) }, icon(ICON.down)),
        h('button', { type: 'button', class: 'xk-mv xk-rm', 'aria-label': `${tkLabel(id)} 빼기`, title: '빼기', onclick: () => toggle(id, true) }, icon(ICON.close))))) : h('p', { class: 'xd-p', text: '비어 있어요. 아래에서 골라 주세요. 모두 빼면 기본 구성으로 돌아가요.' }));
  }
  function drawPane() {
    const rows = [];
    pane.setAttribute('aria-label', catName(cat));
    if (cat === 'wi') {
      const gs = (tkx.groups.get('index') || []).filter(g => ['us', 'eu', 'asia', 'am', 'ref'].includes(g.key));
      if (!gs.length) rows.push(h('p', { class: 'xd-p', text: tkx.groups.size ? '목록을 불러오지 못했어요.' : '목록을 불러오는 중이에요…' }));
      for (const g of gs) { rows.push(h('h4', { class: 'xk-h4', text: g.name })); for (const it of g.items) rows.push(pick('w:' + it.key, it.name)); }
    } else if (cat === 'fut') {
      for (const [id, n] of TK_FIXED.fut) rows.push(pick(id, n));
      const g = (tkx.groups.get('index') || []).find(x => x.key === 'usf');
      for (const it of (g ? g.items : [])) if (!['EScv1', 'NQcv1'].includes(it.key)) rows.push(pick('w:' + it.key, it.name));
    } else if (cat === 'cm') {
      rows.push(pick('m:WTI', 'WTI'), pick('m:GOLD', '국제 금'));
      for (const g of tkx.groups.get('commodity') || []) { const its = g.items.filter(i => !['CLcv1', 'GCcv1'].includes(i.key)); if (its.length) { rows.push(h('h4', { class: 'xk-h4', text: g.name })); for (const it of its) rows.push(pick('w:' + it.key, it.name)); } }
      if (!tkx.groups.get('commodity')) rows.push(h('p', { class: 'xd-p', text: '다른 원자재 목록을 불러오는 중이에요…' }));
    } else if (cat === 'st') {
      const inp = h('input', { type: 'search', class: 'xk-q', placeholder: '종목명·코드로 찾기', value: q, 'aria-label': '종목 검색', autocomplete: 'off', oninput: e => { q = e.target.value; drawResults(); } });
      const res = h('div', { class: 'xk-res' });
      pane.replaceChildren(inp, res);
      const drawResults = () => {
        const t = q.trim().toLowerCase();
        if (!t) { res.replaceChildren(h('p', { class: 'xd-p', text: '이름이나 코드를 입력하면 종목이 나와요.' })); return; }
        if (!names) { res.replaceChildren(h('p', { class: 'xd-p', text: '종목 목록을 불러오는 중이에요…' })); return; }
        const hit = [];
        for (const c in names) { const n = names[c][0]; if (n.toLowerCase().includes(t) || c.includes(t)) { hit.push(c); if (hit.length >= 30) break; } }
        res.replaceChildren(...(hit.length ? hit.map(c => { tkx.names.set('s:' + c, names[c][0]); return pick('s:' + c, names[c][0], c); }) : [h('p', { class: 'xd-p', text: '찾는 종목이 없어요.' })]));
      };
      if (!names) { const done = j => { names = (j && j.n) || {}; if (cat === 'st') drawResults(); }; try { Promise.resolve(KH.loadData('names')).then(done, () => done(null)); } catch (e) { done(null); } }
      drawResults();
      return;
    } else if (cat === 'wl') {
      let gs = []; try { gs = KH.watch.groups() || []; } catch (e) { /* none */ }
      rows.push(pick('g:all', '관심종목 전체', '모든 그룹의 종목이 차례로 흘러요'));
      for (const g of gs) rows.push(pick('g:' + g.id, g.name, `${g.count}종목`));
      if (!gs.length) rows.push(h('p', { class: 'xd-p', text: '관심종목이 아직 없어요. ★관심 탭에서 종목에 별을 달아 보세요.' }));
    } else for (const [id, n] of TK_FIXED[cat] || []) rows.push(pick(id, n));
    pane.replaceChildren(...rows);
  }
  function pickCat(k, b) {
    if (cat === k) return;
    cat = k;
    for (const x of cats.children) x.setAttribute('aria-pressed', String(x.dataset.c === k));
    drawPane();
    try { b.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: motion() === 'reduced' ? 'auto' : 'smooth' }); } catch (e) { /* stays */ }
  }
  // 기본값으로 = two presses (controls.md §5-11): the first arms it (dark amber + ! "한 번 더 누르면 되돌려요", a bar that runs out in
  // --c-arm), the second within that time does it (✓ "되돌렸어요" for --c-dwell); a second press within 0.4 s is a slip and is ignored
  const reset = h('button', { type: 'button', class: 'xk-reset', 'data-st': 'idle', 'aria-label': '기본값으로', onclick: () => onReset() },
    h('span', { class: 'klb' }, kl('idle', '기본값으로'), kl('arm', [uiIcon('warn'), '한 번 더 누르면 되돌려요']), kl('done', [uiIcon('check'), '되돌렸어요'])),
    h('i', { class: 'xk-arm', 'aria-hidden': 'true' }));
  let armT = 0, armAt = 0;
  const toIdle = () => { setState(reset, 'idle'); syncReset(); };
  function syncReset() { if ((reset.dataset.st || 'idle') === 'idle') reset.setAttribute('aria-disabled', String(!tkIds())); }
  function onReset() {
    const st = reset.dataset.st || 'idle';
    if (st === 'done' || (st === 'idle' && reset.getAttribute('aria-disabled') === 'true')) return;
    if (st !== 'arm') {
      setState(reset, 'arm'); armAt = performance.now();
      clearTimeout(armT); armT = setTimeout(toIdle, tokMs('--c-arm', 4000) || 4000);
      say('한 번 더 누르면 기본 구성으로 되돌려요');
      return;
    }
    if (performance.now() - armAt < 400) return;
    clearTimeout(armT);
    list = tkDefaultIds(); tkiSave(null); tk.sig = ''; renderStrip(); drawSel(); syncRows();
    setState(reset, 'done'); say('기본 구성으로 되돌렸어요');
    armT = setTimeout(toIdle, tokMs('--c-dwell', 1120) || 1120);
  }
  body.append(selBox, cats, pane);
  const dlg = makeDialog('xk', '티커 항목', opener, [
    h('h2', { class: 'xd-h', text: '티커 항목' }),
    h('p', { class: 'xd-p', text: '위쪽 시장 띠에 흐를 항목을 고르고 순서를 바꿔요. 이 기기에만 저장돼요.' }),
    body,
    h('div', { class: 'xk-foot' }, reset, h('button', { type: 'button', class: 'xk-done', onclick: () => dlg.close(), text: '완료' })),
  ]);
  dlg.addEventListener('close', () => clearTimeout(armT));
  drawSel(); drawPane(); syncReset();
  if (UI && typeof UI.seg === 'function') UI.seg(cats);
  tkAux(true).then(() => { if (dlg.isConnected) { drawSel(); if (cat === 'wi' || cat === 'fut' || cat === 'cm') drawPane(); } }).catch(() => {});
}
function initTickerSetting() {
  if (!LIVE || !has('addSetting')) return;
  try {
    KH.addSetting({ key: 'tickerEdit', label: '티커 항목', default: true });
    const row = document.querySelector('[data-set="tickerEdit"]');
    if (!row) return;
    const sum = h('small', { class: 'hint' });
    const btn = h('button', { type: 'button', class: 'xk-open', onclick: e => tkPicker(e.currentTarget) }, '고르기');
    const upd = () => { const a = tkIds(); sum.textContent = a ? `직접 고른 ${a.length}개` : '기본 구성'; };
    row.replaceChildren(h('div', { class: 'xk-setrow' }, h('span', { text: '티커 항목' }), btn), sum);
    row.classList.add('xk-set'); upd();
    document.addEventListener('kh:tkitems', upd);
  } catch (e) { /* the picker is optional */ }
}

/* ── ticker: [viewport (mask) > track > N copies of the item list] + fixed tail + pause button ── */
const tk = { sig: '', list: null, track: null, vp: null, tail: null, ro: null, W: 0, dur: 0 };
let tkPaused = false;
try { tkPaused = localStorage.getItem('khm.tickerPaused') === '1'; } catch (e) { /* storage blocked */ }
const tkOn = () => stripEl.classList.contains('xs-tk');

// the "네이버 증권 · HH:MM 기준" item is normally hidden: it shows only when the data lags the corrected clock by more than
// 2 minutes (after the close, holidays, weekends: "15:30 기준") or when the last refresh failed
function dataAsOf() {
  try { if (has('asOf')) { const a = KH.asOf(); const d = a ? new Date(a) : null; if (d && !isNaN(d)) return d; } } catch (e) { /* fall back to the strip */ }
  const d = strip.asOf ? new Date(strip.asOf) : null;
  return d && !isNaN(d) ? d : null;
}
function stripTail() {
  if (LIVE) {
    const at = dataAsOf();
    const lag = at ? nowMs() - at.getTime() : 0;
    if (!strip.failed && !(lag > 120000)) return null;
    const t = at ? fmtHM.format(at) : '';
    return h('span', { class: 'xs-t' + (strip.failed ? ' xs-stale' : ''), title: strip.failed ? '최근 갱신에 실패해서 마지막으로 받은 값이에요' : '시세 기준 시각이 지금보다 늦어요(장 마감 뒤·휴장 포함)' },
      h('span', { text: strip.failed ? '갱신 실패' : '네이버 증권' }), h('span', { text: t ? `${t} 기준` : '' }));
  }
  if (KH.LIVE_URL) return h('a', { class: 'xs-live', href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '환율·미국 선물은 실시간 버전에서 볼 수 있어요' });
  return null;
}
// add / replace / remove the tail in place (ticker or static layout); the track's animation is never touched
function syncTail() {
  if (!stripEl || stripEl.hidden || !LIVE) return;
  const t = stripTail();
  if (tkOn()) {
    if (tk.tail && t) { tk.tail.replaceWith(t); tk.tail = t; }
    else if (tk.tail && !t) { tk.tail.remove(); tk.tail = null; }
    else if (!tk.tail && t) { tk.vp.after(t); tk.tail = t; }
    else return;
    tkSize(false);                                                 // the viewport got wider/narrower: only ever add copies, so the loop never jumps
  } else {
    const cur = stripEl.querySelector('.xs-t');
    if (cur && t) cur.replaceWith(t); else if (cur) cur.remove(); else if (t && stripEl.querySelector('.xs-list')) stripEl.append(t);
    stripOverflow();
  }
}
function tkCopy() {
  const c = tk.list.cloneNode(true);
  c.removeAttribute('role'); c.removeAttribute('aria-label');
  c.setAttribute('aria-hidden', 'true');
  for (const it of c.children) { it.removeAttribute('tabindex'); it.removeAttribute('role'); }      // taps work on the copies, the keyboard only meets the originals
  return c;
}
// measure one loop period W; full=true (build / resize) also sets copies and duration, otherwise only --xs-shift
function tkSize(full) {
  if (!tk.list || !tk.list.isConnected) return;
  const W = tk.list.getBoundingClientRect().width, vw = tk.vp.clientWidth;
  if (!(W > 0)) return;
  const need = Math.max(2, Math.ceil(vw / W) + 1);
  let n = tk.track.children.length;
  while (n < need) { tk.track.append(tkCopy()); n++; }
  if (full) while (n > need) { tk.track.lastChild.remove(); n--; }
  if (Math.abs(W - tk.W) > 0.01) { tk.W = W; tk.track.style.setProperty('--xs-shift', (-W).toFixed(2) + 'px'); }
  if (full) {
    tk.dur = W / (narrowMQ.matches ? 38 : 45);
    tk.track.style.setProperty('--xs-dur', tk.dur.toFixed(2) + 's');
  }
}
// ⏸ ↔ ▶: both shapes drawn once and swapped in place (controls.md §5-9); paused = held down with the amber ring (--key-on)
function tkButton() {
  const btn = h('button', { type: 'button', class: 'xs-pp', 'aria-pressed': String(tkPaused) },
    h('i', { class: 'xs-ppi', 'aria-hidden': 'true' }, icon(ICON.pause, true), icon(ICON.play, true)));
  const draw = () => {
    btn.setAttribute('aria-pressed', String(tkPaused));
    const l = tkPaused ? '시장 띠 다시 움직이기' : '시장 띠 멈추기';
    btn.setAttribute('aria-label', l); btn.title = l;
    stripEl.classList.toggle('xs-off', tkPaused);
  };
  btn.addEventListener('click', () => {
    tkPaused = !tkPaused;
    try { localStorage.setItem('khm.tickerPaused', tkPaused ? '1' : '0'); } catch (e) { /* ignore */ }
    draw();
    if (!tkPaused && !tkHold.held) tkResume();
  });
  draw();
  return btn;
}
function buildTicker(kids) {
  tk.list = h('div', { class: 'xs-list', role: 'group', 'aria-label': '시장 지표' }, kids);
  tk.track = h('div', { class: 'xs-track' }, tk.list);
  tk.vp = h('div', { class: 'xs-vp' }, tk.track);
  tk.tail = stripTail();
  tk.W = 0;
  tkBindPointer(tk.vp);
  stripEl.classList.add('xs-tk'); stripEl.classList.remove('xs-scroll', 'xs-end'); tkHoldApply();
  stripEl.hidden = false;
  stripEl.replaceChildren(...[tk.vp, tk.tail, tkButton()].filter(Boolean));
  tkSize(true);
  if (tk.ro) tk.ro.disconnect();
  if (typeof ResizeObserver === 'function') { tk.ro = new ResizeObserver(() => tkSize(false)); tk.ro.observe(tk.list); }   // fonts / in-place value changes
}
// 30 s refresh: touch only the nodes, never the track's animation
function updateTicker(kids) {
  const fresh = new Map(kids.map(k => [k.dataset.k, k]));
  for (const list of tk.track.children) {
    for (const node of list.children) {
      const f = fresh.get(node.dataset.k);
      if (!f) continue;
      node.className = f.className;
      node.title = f.title; node.setAttribute('aria-label', f.getAttribute('aria-label'));
      node.replaceChildren(...[...f.childNodes].map(c => c.cloneNode(true)));
    }
  }
  syncTail();
  tkSize(false);
}


/* ── odometer: when a strip value changes and effects are 'fancy', the changed digits roll like a counter ── */
const motion = () => { try { if (has('motion')) { const m = KH.motion(); if (m === 'reduced' || m === 'standard' || m === 'fancy') return m; } } catch (e) { /* default below */ } return reduceMQ.matches ? 'reduced' : 'standard'; };
const stripPrev = new Map();                                   // key → { v, r, vt, rt } from the previous render
function rollText(el, oldT, newT, up) {
  // The text is always written first, so the final state never depends on an animation: each changed digit gets an
  // aria-hidden "old digit" overlay that slides out while the real new digit slides in; everything is removed again on a timer.
  el.textContent = newT; el._want = newT;
  if (!oldT || oldT === newT) return;
  const a = [...oldT], b = [...newT];
  const kids = [], movers = [];
  b.forEach((ch, i) => {
    const o = a[a.length - (b.length - i)];
    if (o === undefined || o === ch || !/[0-9]/.test(ch) || !/[0-9]/.test(o)) { kids.push(document.createTextNode(ch)); return; }
    const nw = h('span', { class: 'od-n', text: ch }), ol = h('span', { class: 'od-o', 'aria-hidden': 'true', text: o });
    kids.push(h('span', { class: 'od' }, nw, ol));
    movers.push([nw, ol]);
  });
  if (!movers.length) return;
  el.replaceChildren(...kids);
  const dist = up ? 1 : -1;
  let k = movers.length;
  for (const [nw, ol] of movers) {
    const delay = --k * 45, o = { duration: 480, delay, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'backwards' };
    try {
      nw.animate([{ transform: `translateY(${dist * 100}%)`, opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }], o);
      ol.animate([{ transform: 'translateY(0)', opacity: 1 }, { transform: `translateY(${-dist * 100}%)`, opacity: 0 }], Object.assign({}, o, { fill: 'both' }));
    } catch (e) { /* static digits are fine */ }
  }
  el._want = newT;
  const settle = () => { if (el._want === newT) el.textContent = newT; };
  setTimeout(settle, 480 + movers.length * 45 + 80);
}
function rollChanged(items) {
  const lvl = motion();
  const seen = new Set();
  for (const it of items || []) {
    const v = +it.value, r = +it.ratio, key = it.key;
    seen.add(key);
    if (String(key).includes(':')) continue;
    const prev = stripPrev.get(key);
    const cur = { v, r };
    stripPrev.set(key, cur);
    if (!prev || lvl !== 'fancy' || document.hidden || !stripEl) continue;
    if (isFinite(v) && isFinite(prev.v) && v !== prev.v) {
      const def = STRIP[key] || { dp: 2 };
      const oldT = key === 'BTC' && prev.v >= 1e8 ? krwShort(prev.v) : fixed(prev.v, def.dp);
      for (const el of stripEl.querySelectorAll(`.xs-item[data-k="${key}"] .xs-v`)) rollText(el, oldT, el.textContent, v > prev.v);
    }
    if (isFinite(r) && isFinite(prev.r) && r !== prev.r) {
      for (const el of stripEl.querySelectorAll(`.xs-item[data-k="${key}"] .xs-r`)) rollText(el, pct(prev.r), el.textContent, r > prev.r);
    }
  }
}

function renderStrip() {
  if (!stripEl) return;
  const items = tkSource();
  const kids = [];
  if (items && items.length) {
    for (const it of items) { const el = stripItem(it); if (el) kids.push(el); }
  }
  if (!kids.length) {
    tk.sig = '';
    stripEl.classList.remove('xs-tk', 'xs-hold');
    if (tk.ro) { tk.ro.disconnect(); tk.ro = null; }
    if (!LIVE) { stripEl.hidden = true; document.documentElement.classList.remove('xs-on'); return; }
    const msg = items && !items.length ? '시장 지표가 아직 없어요.' : strip.failed ? '시장 지표를 불러오지 못했어요. 30초 뒤 다시 시도해요.' : '시장 지표를 불러오는 중이에요…';
    stripEl.hidden = false;
    stripEl.replaceChildren(h('div', { class: 'xs-msg', role: 'status', text: msg }));
    stripOverflow();
    document.documentElement.classList.remove('xs-on');
    return;
  }
  const animate = kids.length >= 3 && !reduceMQ.matches;
  const sig = animate ? kids.map(k => k.dataset.k).join(',') : '';
  if (animate && sig === tk.sig && tkOn() && tk.track && tk.track.isConnected) {
    updateTicker(kids);
  } else if (animate) {
    tk.sig = sig;
    buildTicker(kids);
  } else {
    tk.sig = '';
    stripEl.classList.remove('xs-tk', 'xs-hold');
    if (tk.ro) { tk.ro.disconnect(); tk.ro = null; }
    const list = h('div', { class: 'xs-list', role: 'group', 'aria-label': '시장 지표' }, kids);
    const tail = stripTail();
    stripEl.hidden = false;
    stripEl.replaceChildren(list, ...(tail ? [tail] : []));
  }
  // the header's own 코스피/코스닥 readout (#idx) duplicates the strip
  document.documentElement.classList.toggle('xs-on', (strip.items || []).some(it => it.key === 'KOSPI' || it.key === 'KOSDAQ'));
  stripOverflow();
  rollChanged(items);
}
function stripOverflow() {
  if (!stripEl || stripEl.hidden) return;
  if (tkOn()) {        // the ticker moves by itself: no scroll region
    stripEl.classList.remove('xs-scroll', 'xs-end');
    stripEl.removeAttribute('tabindex'); stripEl.removeAttribute('role'); stripEl.removeAttribute('aria-label');
    return;
  }
  const over = stripEl.scrollWidth > stripEl.clientWidth + 1;
  stripEl.classList.toggle('xs-scroll', over);
  stripEl.classList.toggle('xs-end', !over || stripEl.scrollLeft + stripEl.clientWidth >= stripEl.scrollWidth - 2);
  // a scrollable strip must be reachable by keyboard: make it a focusable, labelled region only then
  if (over) { stripEl.tabIndex = 0; stripEl.setAttribute('role', 'region'); stripEl.setAttribute('aria-label', '시장 지표, 옆으로 넘겨 보세요'); }
  else { stripEl.removeAttribute('tabindex'); stripEl.removeAttribute('role'); stripEl.removeAttribute('aria-label'); }
}

function snapshotIndex() {
  // KH has no index getter in the §3 contract: use one if the template adds it, else the page's own snapshot JSON
  try { if (has('index')) { const x = KH.index(); if (x) return x; } } catch (e) { /* fall through */ }
  try { const s = document.getElementById('snapshot'); if (s) return JSON.parse(s.textContent).index || null; } catch (e) { /* none */ }
  return null;
}

async function pollStrip() {
  clearTimeout(strip.timer);
  if (document.hidden) return;                 // resumes on visibilitychange
  if (strip.busy) return;
  strip.busy = true;
  try {
    const j = await getJSON('api/market');
    if (!j || !Array.isArray(j.items)) throw new Error('bad shape');
    strip.items = j.items; strip.asOf = j.asOf || new Date().toISOString(); strip.failed = false;
    strip.session = j.session && /^\d{4}$/.test(j.session.start) && /^\d{4}$/.test(j.session.end) ? j.session : null;
  } catch (e) {
    strip.failed = true;
  }
  if (!strip.failed) { try { await tkAux(); } catch (e) { /* those items show "—" */ } }
  strip.busy = false;
  strip.at = Date.now();
  renderStrip();
  strip.timer = setTimeout(pollStrip, 30000);
}

function initStrip() {
  if (!stripEl) return;
  stripEl.classList.add('xs');
  tkBindClicks();
  if (LIVE) {
    renderStrip();
    pollStrip();
    setInterval(() => { if (!document.hidden) syncTail(); }, 15000);        // the minute passes without a poll changing anything
    // every quotes poll (and every store update): stock / index items follow the heatmap's numbers at once
    document.addEventListener('kh:data', () => { if (strip.items && !tkHold.down) renderStrip(); else syncTail(); });
    document.addEventListener('kh:basis', () => { if (strip.items) renderStrip(); });          // KRX · NXT · 통합 picked: stock items follow
    document.addEventListener('kh:watch', () => { const a = tkIds(); if (a && a.some(x => x.startsWith('g:'))) tkAux().then(() => renderStrip()).catch(() => {}); });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { clearTimeout(strip.timer); return; }
      const age = Date.now() - strip.at;
      if (age >= 30000) pollStrip(); else { clearTimeout(strip.timer); strip.timer = setTimeout(pollStrip, 30000 - age); }
    });
  } else {
    const ix = snapshotIndex();
    strip.items = ix ? ['KOSPI', 'KOSDAQ'].filter(k => ix[k] && isFinite(+ix[k].value)).map(k => ({ key: k, value: ix[k].value, change: ix[k].change, ratio: ix[k].ratio })) : [];
    renderStrip();
  }
  stripEl.addEventListener('scroll', () => stripEl.classList.toggle('xs-end', stripEl.scrollLeft + stripEl.clientWidth >= stripEl.scrollWidth - 2), { passive: true });
  let rz = 0;
  addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (tkOn()) tkSize(true); stripOverflow(); }, 150); });
  const rm = () => renderStrip();            // motion preference flipped: rebuild as ticker or static strip
  if (reduceMQ.addEventListener) reduceMQ.addEventListener('change', rm); else if (reduceMQ.addListener) reduceMQ.addListener(rm);
}

/* ═════════════ tools row ═════════════ */
const toolsEl = document.getElementById('extras-tools');
function toolButton(key, label, onClick, extra) {
  return h('button', Object.assign({ type: 'button', class: 'xt-btn', 'data-x': key, title: label, onclick: onClick }, extra || {}), icon(ICON[key]), h('span', { class: 'xt-l', text: label }));
}
/* 이미지로 저장 = an async key (controls.md §5-3): picture → ring → ✓ / ! in the icon's place, the label box (shown from 1600 px)
   says the same; the box keeps its widest label, so nothing beside it moves. Icon-only keys say the result in a bubble under
   the key (no layout) and every result is announced once. aria-label stays "이미지로 저장". */
const IMG_SAY = { idle: '이미지로 저장', work: '만드는 중', done: '저장했어요', fail: '실패 · 다시' };
function imageKey() {
  if (!UI) return toolButton('image', IMG_SAY.idle, saveImage);
  const ic = h('i', { class: 'klb xt-ic', 'aria-hidden': 'true' }, kl('idle', icon(ICON.image), 'i'), kl('work', uiIcon('spin'), 'i'), kl('done', uiIcon('check'), 'i'), kl('fail', uiIcon('warn'), 'i'));
  const lab = h('span', { class: 'xt-l klb' }, Object.entries(IMG_SAY).map(([st, t]) => kl(st, t)));
  return h('button', { type: 'button', class: 'xt-btn xt-async', 'data-x': 'image', 'data-st': 'idle', 'data-busy': 'work', 'data-keep-label': true,
    title: IMG_SAY.idle, 'aria-label': IMG_SAY.idle, onclick: saveImage }, ic, lab);
}
const iconOnly = b => { const l = b && b.querySelector('.xt-l'); return !l || l.getBoundingClientRect().width < 2; };
// a word from a tool key: a bubble under the key (always for a reason; for a result only when the key shows no label) + aria-live
function keySay(btn, text, kind, reason) {
  if (!UI) { toast(text); return; }
  if (btn && btn.isConnected && (reason || iconOnly(btn))) UI.bubble(btn, text, kind); else UI.live(text);
}

/* ═════════════ 2. Save as image ═════════════ */
function currentMarket() {
  try { if (has('market')) { const m = KH.market(); if (m) return m; } } catch (e) { /* fall through */ }
  const b = $('.tabs button[aria-pressed="true"]');
  return b ? b.dataset.mkt || 'K' : 'K';
}
const isWorldTab = () => { const m = currentMarket(); return m === 'world' || m === 'cmdty'; };
function titleParts() {
  const m = currentMarket();
  if (m === 'world' || m === 'cmdty') {
    const d = new Date();
    return { m, title: m === 'world' ? '해외 지수' : (KH.MKT_NAME && KH.MKT_NAME.CMDTY) || '지표', when: fmtHM.format(d) + ' 기준' };
  }
  const name = (KH.MKT_NAME && KH.MKT_NAME[m]) || '';
  const crumbs = [...document.querySelectorAll('#crumbs .c')].map(b => b.textContent.trim()).filter(Boolean);
  const path = crumbs.slice(1).join(' › ');
  let when = '';
  if (replay.frameT && replay.date) when = `${dayLabel(replay.date)} ${hhmm(replay.frameT)} 리플레이`;
  else { const a = KH.asOf && KH.asOf(); const d = a ? new Date(a) : null; when = d && !isNaN(d) ? fmtStamp.format(d) + ' 기준' : ''; }
  return { m, title: `${name ? name + ' ' : ''}히트맵${path ? ' · ' + path : ''}`, when };
}
function fileName(m) {
  const tag = { K: 'kospi', Q: 'kosdaq', ALL: 'all', world: 'world', cmdty: 'commodity' }[m] || 'map';
  let stamp;
  if (replay.frameT && replay.date) stamp = replay.date.replace(/-/g, '') + '-' + String(replay.frameT).replace(':', '');
  else {
    const a = KH.asOf && KH.asOf(); const d = a ? new Date(a) : new Date();
    const p = new Intl.DateTimeFormat('en-CA', { timeZone: KST, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(isNaN(d) ? new Date() : d);
    const g = t => (p.find(x => x.type === t) || {}).value || '';
    stamp = `${g('year')}${g('month')}${g('day')}-${g('hour')}${g('minute')}`;
  }
  return `heatmap-${tag}-${stamp}.png`;
}

// split a long name like the screen does: at a space, at a Korean/Latin boundary, or mid-word for all-Korean names
const isHangul = ch => { const c = ch.codePointAt(0); return c >= 0xAC00 && c <= 0xD7A3; };
function splitName(name) {
  const sp = name.indexOf(' ');
  if (sp > 0 && sp < name.length - 1) return [name.slice(0, sp), name.slice(sp + 1)];
  const chars = [...name];
  if (chars.length < 3) return null;
  if (chars.every(isHangul)) { const cut = Math.ceil(chars.length / 2); return [chars.slice(0, cut).join(''), chars.slice(cut).join('')]; }
  let best = -1, bestD = Infinity;
  for (let i = 1; i < chars.length; i++) if (isHangul(chars[i]) !== isHangul(chars[i - 1])) { const d = Math.abs(i - chars.length / 2); if (d < bestD) { bestD = d; best = i; } }
  return best > 0 ? [chars.slice(0, best).join(''), chars.slice(best).join('')] : null;
}
function ellipsize(ctx, text, max) {
  if (ctx.measureText(text).width <= max) return text;
  const chars = [...text];
  while (chars.length > 1) { chars.pop(); const t = chars.join('') + '…'; if (ctx.measureText(t).width <= max) return t; }
  return '';
}
const subDir = s => /^\s*[+]/.test(s || '') ? 1 : /^\s*[-−]/.test(s || '') ? -1 : 0;

function tileLabel(ctx, fam, n) {
  // same sizing rules as the screen (src/template.html paintTile), measured with the canvas instead of a glyph table
  const name = String(n.label || ''), sub = String(n.sub || '');
  const w = n.w, hh = n.h, W = w - 6;
  if (!name || w < 18 || hh < 13) return null;
  const per = (t, wt) => { ctx.font = `${wt} 100px ${fam}`; return Math.max(ctx.measureText(t).width / 100, 0.5); };
  let fs = Math.min(hh * 0.3, W / per(name, 600), 40);
  let parts = null, ell = false;
  const sp = (name.length >= 5 || fs < 12) ? splitName(name) : null;
  if (sp) { const fs2 = Math.min(hh * 0.23, W / Math.max(per(sp[0], 600), per(sp[1], 600)), 40); if (fs2 > fs * 1.3 && fs2 >= 8.5) { fs = fs2; parts = sp; } }
  if (fs < 8.5 && !parts) { const fh = Math.min(hh * 0.32, 11); if (fh >= 9 && W / fh >= 3.2) { fs = fh; ell = true; } }
  if (isFinite(+n.fs) && +n.fs > 0) fs = +n.fs;
  if (fs < 8) return null;
  const nameLines = parts ? 2 : 1;
  let showSub = false;
  if (sub) {
    const fsSub = Math.min(fs, W / (per(sub, 500) * 0.74));
    showSub = fsSub >= 8 && hh >= fsSub * (nameLines * 1.1 + 1.0);
    if (showSub) fs = fsSub;
  }
  let price = '';
  if (showSub && hh >= fs * (nameLines * 1.1 + 1.75) && fs >= 15 && w >= 70) price = priceText(n);
  return { fs, lines: parts || [name], ell, showSub, price };
}
// third line on big tiles: the node's own text if the layout gives one, else the replay frame's or the live price
function priceText(n) {
  if (n.px != null && n.px !== '') return String(n.px);
  if (!n.code) return '';
  const q = replay.prices && replay.prices.get(n.code);
  const st = !q && has('stock') ? KH.stock(n.code) : null;
  const v = q ? q.p : st ? st.p : NaN;
  return isFinite(v) && v > 0 ? Math.round(v).toLocaleString('ko-KR') : '';
}


/* ── the screen's chrome, read from its DOM (nothing in the template changes) ── */
const rgbOf = el => getComputedStyle(el).color;
function readChrome(world) {
  const { title: t0, when } = titleParts();
  const out = { title: t0, stat: null, ix: null, legend: [], footer: (when ? when + ' · ' : '') + '네이버 증권' };
  if (!world) {
    const crumbs = [...document.querySelectorAll('#crumbs .c')].map(b => b.textContent.trim()).filter(Boolean);
    if (crumbs.length) out.title = crumbs.join(' › ');
    const st = document.querySelector('#crumbs .stat'), b = st && st.querySelector('b');
    if (st && b && st.firstChild) out.stat = { n: String(st.firstChild.textContent).trim(), pct: b.textContent.trim(), color: rgbOf(b) };
    // the row as shown, piece by piece (a market root reads "코스피 지수 +3.70%" or "코스피 +x · 코스닥 +y", desktop "300종목 · 시총 …"):
    // text and labels muted, the coloured numbers bold; pieces the screen hides (시총 on phones) left out, screen-reader labels kept
    if (st) {
      const parts = [];
      for (const nd of st.childNodes) {
        if (nd.nodeType === 3) { if (nd.textContent.trim()) parts.push({ t: nd.textContent.replace(/\s+/g, ' ') }); continue; }
        if (nd.nodeType !== 1 || (!nd.classList.contains('sr') && getComputedStyle(nd).display === 'none')) continue;
        const t = nd.textContent.replace(/\s+/g, ' ');
        if (t.trim()) parts.push(nd.tagName === 'B' ? { t, c: rgbOf(nd), b: true } : { t });
      }
      if (parts.length) out.stat = Object.assign(out.stat || {}, { parts });
    }
    out.ix = readIxLine();
  }
  out.legend = readLegend(document.querySelector(world ? '.kw-legend' : '#legend'));
  return out;
}
// the index line the template already drew (§3-20): its path data and the colours it resolved to
function readIxLine() {
  const el = document.querySelector('.stagebar .ixl');
  const svg = el && !el.hidden && el.querySelector('svg');
  if (!svg || !svg.viewBox || !svg.viewBox.baseVal || svg.viewBox.baseVal.width < 20) return null;
  const vb = svg.viewBox.baseVal, g = [];
  for (const grp of svg.querySelectorAll(':scope > g')) {
    const ln = grp.querySelector('path.ln'), dt = grp.querySelector('circle.dt');
    if (!ln) continue;
    g.push({ d: ln.getAttribute('d'), color: getComputedStyle(ln).stroke, k2: grp.classList.contains('k2'), dot: dt ? [+dt.getAttribute('cx'), +dt.getAttribute('cy')] : null });
  }
  const bl = svg.querySelector('line.bl');
  // the labels the template keeps for style B (display:none in A): value / %, per index with its name when there are two, and the time
  const rows = [];
  const multi = el.querySelectorAll('.ixv .ixr');
  if (multi.length) multi.forEach(r => { const sp = r.querySelectorAll(':scope > span'), pc = sp[sp.length - 1]; rows.push({ name: (r.querySelector('i') || {}).textContent || '', val: (r.querySelector('b') || {}).textContent || '', pct: pc ? pc.textContent : '', color: pc ? rgbOf(pc) : IMG.fg }); });
  else { const v = el.querySelector('.ixv'); if (v) { const b = v.querySelector('b'), pc = v.querySelector('span'); rows.push({ name: '', val: b ? b.textContent : '', pct: pc ? pc.textContent : '', color: pc ? rgbOf(pc) : IMG.fg }); } }
  const tt = el.querySelector('.ixt'), tb = tt && tt.querySelector('b'), ts = tt && tt.querySelector('span');
  return g.length ? { w: vb.width, h: vb.height, g, y0: bl ? +bl.getAttribute('y1') : null, rows, time: tb ? tb.textContent : '', sub: ts ? ts.textContent : '' } : null;
}
// style B, the PC way, in a row of its own under the header: value · % on the left, the line (dashed 전일 종가, a tick at the latest point) in the middle, time / 15:30 or 종가 on the right
function ixRowHeight(ix) { return ix ? (ix.g.length > 1 ? 46 : 36) : 0; }
function drawIxRow(ctx, ix, fam, W, y0, pad) {
  const CH = ixRowHeight(ix), small = W < 520, fs = small ? 11.5 : 12.5;
  ctx.save(); ctx.translate(0, y0);
  ctx.fillStyle = IMG.ihd; ctx.fillRect(0, 0, W, CH);
  ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const rows = ix.rows.length ? ix.rows : [];
  const rowH = CH / Math.max(1, rows.length);
  let lw = 0;
  const meas = r => { ctx.font = `500 ${fs - 1}px ${fam}`; const nm = r.name ? ctx.measureText(r.name).width + 5 : 0; ctx.font = `700 ${fs}px ${fam}`; const v = ctx.measureText(r.val).width; ctx.font = `600 ${fs}px ${fam}`; return { nm, v, p: ctx.measureText(r.pct).width }; };
  rows.forEach(r => { const m = meas(r); r.m = m; lw = Math.max(lw, m.nm + m.v + 6 + m.p); });
  ctx.font = `700 ${fs}px ${fam}`; const tw = Math.max(ctx.measureText(ix.time).width, (ctx.font = `500 ${fs - 1}px ${fam}`, ctx.measureText(ix.sub).width));
  const px0 = pad + lw + 12, px1 = W - pad - tw - 12;
  rows.forEach((r, i) => {
    const cy = rowH * i + rowH / 2; let x = pad;
    if (r.name) { ctx.font = `500 ${fs - 1}px ${fam}`; ctx.fillStyle = IMG.muted; ctx.fillText(r.name, x, cy); x += r.m.nm; }
    ctx.font = `700 ${fs}px ${fam}`; ctx.fillStyle = IMG.fg; ctx.fillText(r.val, x, cy); x += r.m.v + 6;
    ctx.font = `600 ${fs}px ${fam}`; ctx.fillStyle = r.color; ctx.fillText(r.pct, x, cy);
  });
  ctx.textAlign = 'right';
  ctx.font = `700 ${fs}px ${fam}`; ctx.fillStyle = IMG.fg; ctx.fillText(ix.time, W - pad, CH / 2 - (ix.sub ? 7 : 0));
  if (ix.sub) { ctx.font = `500 ${fs - 1}px ${fam}`; ctx.fillStyle = IMG.muted; ctx.fillText(ix.sub, W - pad, CH / 2 + 8); }
  if (px1 - px0 > 40) {
    const sx = (px1 - px0) / ix.w, sy = (CH - 8) / ix.h, m = new DOMMatrix([sx, 0, 0, sy, px0, 4]);
    const ly = ix.y0 == null ? CH / 2 : 4 + ix.y0 * sy;
    ctx.save();
    ctx.setLineDash([3, 4]); ctx.strokeStyle = IMG.ink28; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(px0, ly); ctx.lineTo(px1, ly); ctx.stroke(); ctx.setLineDash([]);
    ix.g.forEach(g => {
      const path = new Path2D(); path.addPath(new Path2D(g.d), m);
      ctx.globalAlpha = g.k2 ? .7 : 1; ctx.strokeStyle = g.color; ctx.lineWidth = 1.7; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke(path);
      if (g.dot) {
        const dx = px0 + g.dot[0] * sx, dy = 4 + g.dot[1] * sy;
        ctx.globalAlpha = .35; ctx.beginPath(); ctx.moveTo(dx, 2); ctx.lineTo(dx, CH - 2); ctx.lineWidth = 1; ctx.stroke();   // "now"
        ctx.globalAlpha = 1; ctx.fillStyle = g.color; ctx.beginPath(); ctx.arc(dx, dy, 3, 0, 7); ctx.fill();
      }
    });
    ctx.restore();
  }
  ctx.restore();
}
// the legend row as atoms per group: {t,font,color} text | {grad:[colors]} | {box:color,lim} | pill for the 리플레이 chip
function readLegend(el) {
  const groups = [];
  if (!el) return groups;
  const walk = (node, atoms) => {
    for (const c of node.childNodes) {
      if (c.nodeType === 3) { const t = c.textContent.trim(); if (t) atoms.push({ t, w: 400 }); continue; }
      if (c.nodeType !== 1 || c.hidden || c.getAttribute('aria-hidden') === 'true' && !/\b(grad|sw|limsw)\b/.test(c.className)) continue;
      const cl = c.classList;
      if (cl.contains('grad')) { const m = (c.style.background || c.style.backgroundImage || '').match(/linear-gradient\(\s*[^,]+,(.*)\)\s*$/); atoms.push({ grad: m ? m[1].split(/,(?![^(]*\))/).map(x => x.trim()) : ['#444', '#aaa'] }); }
      else if (cl.contains('sw') || cl.contains('limsw')) atoms.push({ box: getComputedStyle(c).backgroundColor, lim: cl.contains('u') ? 1 : cl.contains('d') ? -1 : 0, hatch: cl.contains('nxsw') || cl.contains('nodsw') });
      else if (c.children.length) walk(c, atoms);
      else { const t = c.textContent.trim(); if (t) atoms.push({ t, w: parseInt(getComputedStyle(c).fontWeight, 10) || 400, color: rgbOf(c) }); }
    }
  };
  for (const g of el.children) {
    const atoms = []; walk(g, atoms);
    if (atoms.length) { const pill = g.classList.contains('lg-replay'), gs = pill ? getComputedStyle(g) : null;
    groups.push({ atoms, right: g.classList.contains('right'), pill, color: rgbOf(g), pillBd: gs && gs.borderTopColor, pillBg: gs && gs.backgroundColor }); }
  }
  return groups;
}
function layoutLegend(ctx, fam, groups, W, pad) {
  if (!groups.length) return { h: 0, draw() {} };
  const GX = W < 600 ? 14 : 18, GAP = 7, RH = 18, FS = 12;
  const wide = W >= 600;
  const measure = a => { if (a.grad) return 140; if (a.box) return a.lim ? 12 : 10; ctx.font = `${a.w} ${FS}px ${fam}`; return ctx.measureText(a.t).width; };
  const gw = g => g.atoms.reduce((n, a, i) => n + measure(a) + (i ? GAP : 0), 0) + (g.pill ? 14 : 0);
  const rows = []; let cur = null;
  for (const g of groups) {
    const w = gw(g);
    if (!cur || cur.w + GX + w > W - 2 * pad) { cur = { items: [], w: 0 }; rows.push(cur); }
    cur.items.push({ g, w }); cur.w += (cur.items.length > 1 ? GX : 0) + w;
  }
  const h = 8 + rows.length * RH + (rows.length - 1) * 4 + 4;
  const draw = (c, y0) => {
    rows.forEach((r, ri) => {
      const cy = y0 + 8 + ri * (RH + 4) + RH / 2;
      let x = pad;
      r.items.forEach(({ g, w }, ii) => {
        if (g.right && wide && ii === r.items.length - 1) x = Math.max(x, W - pad - w);
        let ax = x + (g.pill ? 7 : 0);
        if (g.pill) { c.strokeStyle = g.pillBd || IMG.accBd; c.fillStyle = g.pillBg || IMG.accSoft; c.lineWidth = 1; c.beginPath(); c.roundRect(x + .5, cy - 9, w - 1, 18, 5); c.fill(); c.stroke(); }
        g.atoms.forEach((a, i) => {
          if (i) ax += GAP;
          if (a.grad) {
            const gr = c.createLinearGradient(ax, 0, ax + 140, 0);
            a.grad.forEach((col, k) => gr.addColorStop(k / Math.max(1, a.grad.length - 1), col));
            c.fillStyle = gr; c.beginPath(); c.roundRect(ax, cy - 4, 140, 8, 2); c.fill(); ax += 140;
          } else if (a.box) {
            const bw = a.lim ? 12 : 10;
            c.fillStyle = a.box; c.beginPath(); c.roundRect(ax, cy - 5, bw, 10, a.lim ? 1 : 2); c.fill();
            if (a.hatch) { c.strokeStyle = IMG.ink30; c.lineWidth = 1; c.strokeRect(ax + .5, cy - 4.5, bw - 1, 9); }
            if (a.lim) { c.fillStyle = IMG.limBar; c.fillRect(ax, a.lim > 0 ? cy - 5 : cy + 2, bw, 3); }
            ax += bw;
          } else {
            c.font = `${a.w} ${FS}px ${fam}`; c.textAlign = 'left'; c.textBaseline = 'middle';
            c.fillStyle = g.pill ? (g.color || IMG.acc) : (a.color || g.color || IMG.muted); c.fillText(a.t, ax, cy + .5); ax += c.measureText(a.t).width;
          }
        });
        x += w + GX;
      });
    });
  };
  return { h, draw };
}

// the screen's colours at the moment of saving (docs/standards/themes.md §15-2): a light theme gives a light image
let IMG = null;
function imgTheme() {
  const cs = getComputedStyle(rootEl), g = (n, d) => cs.getPropertyValue(n).trim() || d, light = lightTone();
  const fg = g('--fg', '#eef0f3'), muted = g('--muted', '#8a8f99');
  const rule = g('--rule', '');
  return {
    light, labs: light ? 'auto' : 'halo',   // light tone: black or white per tile (node.ink when the template gives it); dark: white with a shadow
    page: g('--page', '#131418'), map: g('--map-bg', '#000'), fg, muted, nodata: g('--nodata', '#383c46'),
    sec: g('--sec-bg', '#000'), secFg: g('--sec-fg', '#f2f3f5'), ihd: g('--ihd-bg', '#0d0e11'), ihdFg: g('--ihd-fg', '#a6abb5'),
    rule: /^(|transparent|rgba\(0,\s*0,\s*0,\s*0\))$/.test(rule) ? '' : rule,
    acc: g('--acc', '#ffb547'), accBd: g('--acc-bd', 'rgba(255,181,71,.45)'), accSoft: g('--acc-soft', 'rgba(255,181,71,.12)'),
    limBar: g('--lim-bar', '#fff'),
    ink28: light ? withAlpha(fg, .28) : 'rgba(255,255,255,.28)', ink30: light ? withAlpha(fg, .3) : 'rgba(255,255,255,.3)',
  };
}
function drawMap(nodes, wt) {
  IMG = imgTheme();
  const pal = has('palette') ? KH.palette() : {};
  const upC = pal.upText || '#ff5c66', dnC = pal.dnText || '#2fd67a';
  const fam = getComputedStyle(document.body).fontFamily || 'sans-serif';
  const minX = Math.min(...nodes.map(n => n.x)), minY = Math.min(...nodes.map(n => n.y));
  const N = nodes.map(n => Object.assign({}, n, { x: n.x - minX, y: n.y - minY }));
  const W = Math.ceil(Math.max(...N.map(n => n.x + n.w))), MH = Math.ceil(Math.max(...N.map(n => n.y + n.h)));
  const pad = W < 520 ? 10 : 14;
  const cnv = document.createElement('canvas');
  const ctx = cnv.getContext('2d');
  // the screen's own header row (title, today's index line behind it, N종목 · ±%), the whole map, the legend row, a small footer
  const chrome = readChrome(wt);
  const tSize = W < 520 ? 14 : 16, TH = Math.round(tSize * 2.4);
  ctx.font = `500 12px ${fam}`;
  const lg = layoutLegend(ctx, fam, chrome.legend, W, pad);
  const FH = 24, XH = ixRowHeight(chrome.ix), HT = TH + XH;
  const H = HT + MH + lg.h + FH;
  let s = Math.min(3, Math.max(2, window.devicePixelRatio || 1));
  while (W * H * s * s > 16e6 && s > 1) s -= 0.25;                     // stay under the canvas area limit (iOS ≈ 16.7M px)
  cnv.width = Math.round(W * s); cnv.height = Math.round(H * s);
  ctx.scale(s, s);
  ctx.fillStyle = IMG.page; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = IMG.map; ctx.fillRect(0, HT, W, MH);
  ctx.textBaseline = 'middle';
  if (chrome.ix) drawIxRow(ctx, chrome.ix, fam, W, TH, pad);
  {
    const cy = TH / 2;
    let right = W - pad;
    ctx.textAlign = 'right';
    if (chrome.stat && chrome.stat.parts) {
      const fs = W < 520 ? 12 : 13;
      for (const p of chrome.stat.parts.slice().reverse()) {
        ctx.font = `${p.b ? 600 : 500} ${fs}px ${fam}`;
        ctx.fillStyle = p.c || IMG.muted; ctx.fillText(p.t, right, cy);
        right -= ctx.measureText(p.t).width;
      }
      right -= 12;
    } else if (chrome.stat) {
      ctx.font = `600 ${W < 520 ? 12 : 13}px ${fam}`;
      const pw = ctx.measureText(chrome.stat.pct).width;
      ctx.fillStyle = chrome.stat.color; ctx.fillText(chrome.stat.pct, right, cy);
      ctx.fillStyle = IMG.muted; ctx.font = `500 ${W < 520 ? 12 : 13}px ${fam}`; ctx.fillText(chrome.stat.n + ' · ', right - pw, cy);
      right -= pw + ctx.measureText(chrome.stat.n + ' · ').width + 12;
    }
    ctx.textAlign = 'left';
    ctx.font = `700 ${tSize}px ${fam}`;
    ctx.fillStyle = IMG.fg; ctx.fillText(ellipsize(ctx, chrome.title, Math.max(40, right - pad)), pad, cy);
  }
  ctx.translate(0, HT);
  // group headers: the header height is the gap between a group's top and its first child (d3 paddingTop), unless given
  const tiles = N.filter(n => n.kind === 'tile'), inds = N.filter(n => n.kind === 'ind'), secs = N.filter(n => n.kind === 'sector');
  const inside = (c, p) => c.x >= p.x - 0.5 && c.y >= p.y - 0.5 && c.x + c.w <= p.x + p.w + 0.5 && c.y + c.h <= p.y + p.h + 0.5;
  const hdOf = (g, kids) => {
    if (isFinite(+g.hd)) return +g.hd;
    let top = Infinity;
    for (const k of kids) if (inside(k, g)) top = Math.min(top, k.y);
    const v = top === Infinity ? 0 : top - g.y;
    return v >= 9 && v <= 30 ? v : 0;
  };
  for (const n of tiles) { ctx.fillStyle = n.color || IMG.nodata; ctx.fillRect(n.x, n.y, n.w, n.h); }
  const header = (g, H, size, weight, bg, fg) => {
    if (!H || !g.label) return;
    ctx.fillStyle = bg; ctx.fillRect(g.x, g.y, g.w, H);
    ctx.save();
    ctx.beginPath(); ctx.rect(g.x, g.y, g.w, H); ctx.clip();
    ctx.textAlign = 'left';
    const label = String(g.label), sub = String(g.sub || '');
    const cy = g.y + H / 2 + 0.5, room = g.w - 10;
    ctx.font = `600 ${size}px ${fam}`;
    const subW = sub ? ctx.measureText(sub).width : 0;
    ctx.font = `${weight} ${size}px ${fam}`;
    const withSub = !!sub && ctx.measureText(label).width + 6 + subW <= room;
    const text = ellipsize(ctx, label, withSub ? room - subW - 6 : room);
    const textW = ctx.measureText(text).width;
    ctx.fillStyle = fg; ctx.fillText(text, g.x + 5, cy);
    if (withSub) {
      const d = subDir(sub);
      ctx.font = `600 ${size}px ${fam}`;
      ctx.fillStyle = d > 0 ? upC : d < 0 ? dnC : IMG.muted;
      ctx.fillText(sub, g.x + 5 + textW + 6, cy);
    }
    ctx.restore();
  };
  for (const g of inds) header(g, hdOf(g, tiles), 10.5, 500, IMG.ihd, IMG.ihdFg);
  for (const g of secs) header(g, hdOf(g, inds.length ? inds : tiles), 12, 700, IMG.sec, IMG.secFg);
  // tile labels
  ctx.textAlign = 'center';
  for (const n of tiles) {
    const L = tileLabel(ctx, fam, n);
    if (!L) continue;
    const { fs, lines, ell, showSub, price } = L;
    const lh = fs * 1.08, subFs = fs * 0.74, pxFs = fs * 0.52;
    const total = lines.length * lh + (showSub ? subFs * 1.08 + fs * 0.12 : 0) + (price ? pxFs * 1.08 + pxFs * 0.3 : 0);
    let y = n.y + (n.h - total) / 2 + lh / 2;
    const cx = n.x + n.w / 2;
    ctx.save();
    ctx.beginPath(); ctx.rect(n.x, n.y, n.w, n.h); ctx.clip();
    if (IMG.labs !== 'auto') { ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = 2 * s; ctx.shadowOffsetY = 1 * s; }   // dark themes: white type with a soft halo
    ctx.fillStyle = IMG.labs === 'auto' ? (n.ink || inkOn(n.color)) : '#fff';
    ctx.font = `600 ${fs.toFixed(1)}px ${fam}`;
    for (const line of lines) { ctx.fillText(ell ? ellipsize(ctx, line, n.w - 6) : line, cx, y); y += lh; }
    if (showSub) {
      y += fs * 0.12 - lh / 2 + subFs * 1.08 / 2;
      ctx.font = `500 ${subFs.toFixed(1)}px ${fam}`;
      ctx.globalAlpha = 0.96;
      ctx.fillText(String(n.sub), cx, y);
      if (price) {
        y += subFs * 1.08 / 2 + pxFs * 0.3 + pxFs * 1.08 / 2;
        ctx.font = `500 ${pxFs.toFixed(1)}px ${fam}`;
        ctx.globalAlpha = 0.78;
        ctx.fillText(ellipsize(ctx, price, n.w - 6), cx, y);
      }
    }
    ctx.restore();
  }
  if (IMG.rule) { ctx.strokeStyle = IMG.rule; ctx.lineWidth = 1; ctx.strokeRect(.5, .5, W - 1, MH - 1); }   // paper: the map's 1px ink edge
  ctx.translate(0, MH);
  lg.draw(ctx, 0);
  ctx.translate(0, lg.h);
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  ctx.font = `500 10.5px ${fam}`; ctx.fillStyle = IMG.muted;
  ctx.fillText(ellipsize(ctx, chrome.footer, W - 2 * pad), pad, FH / 2 - 1);
  return cnv;
}

let saving = false, saveT = 0;
async function saveImage(ev) {
  if (saving) return;
  const btn = ev && ev.currentTarget;
  const async_ = !!(btn && btn.classList.contains('xt-async'));
  clearTimeout(saveT);
  if (async_ && btn.dataset.st !== 'idle') setState(btn, 'idle');              // ✓ still showing, or ! waiting for this press
  let nodes = [];
  const wt = isWorldTab();
  try { nodes = ((wt ? (window.KHWorld && typeof window.KHWorld.layout === 'function' ? window.KHWorld.layout() : []) : KH.layout()) || []).filter(n => n && isFinite(n.x) && isFinite(n.y) && n.w > 0 && n.h > 0); } catch (e) { nodes = []; }
  if (!nodes.some(n => n.kind === 'tile')) { keySay(btn, wt ? '지도 탭에서만 저장할 수 있어요' : '지도 보기에서 저장할 수 있어요', 'fail', true); return; }
  saving = true;
  if (async_) setState(btn, 'work'); else if (btn) btn.setAttribute('aria-busy', 'true');
  let st = 'idle';
  try {
    const fam = getComputedStyle(document.body).fontFamily;
    if (document.fonts && document.fonts.load) {
      await Promise.race([Promise.all([document.fonts.load(`700 16px ${fam}`, '가A1'), document.fonts.load(`500 12px ${fam}`, '가A1')]), new Promise(r => setTimeout(r, 1500))]).catch(() => {});
    }
    const cnv = drawMap(nodes, wt);
    const name = fileName(titleParts().m);
    if (LIVE) {
      const blob = await new Promise(res => cnv.toBlob(res, 'image/png'));
      if (!blob) throw new Error('toBlob');
      const url = URL.createObjectURL(blob);
      const a = h('a', { href: url, download: name, hidden: true });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      st = 'done';
      keySay(btn, '지도를 이미지로 저장했어요', 'done');
    } else {
      showImageDialog(cnv.toDataURL('image/png'), name, cnv.width, cnv.height, btn);      // the preview is the result
    }
  } catch (e) {
    st = 'fail';
    keySay(btn, '이미지를 만들지 못했어요 · 다시 눌러 주세요', 'fail');
  } finally {
    saving = false;
    if (async_) {
      setState(btn, st);
      // ✓ stays --c-dwell, then the key is itself again; ! stays until the next press (that press tries again)
      if (st === 'done') saveT = setTimeout(() => setState(btn, 'idle'), tokMs('--c-dwell', 1120) || 1120);
    } else if (btn) btn.removeAttribute('aria-busy');
  }
}

function makeDialog(cls, label, opener, kids) {
  const dlg = h('dialog', { class: 'xd ' + cls, 'aria-label': label });
  const close = () => dlg.close();
  dlg.append(h('button', { type: 'button', class: 'xd-x', 'aria-label': '닫기', onclick: close }, icon(ICON.close)), ...kids);
  dlg.addEventListener('click', e => { if (e.target === dlg) close(); });        // click on the backdrop
  dlg.addEventListener('close', () => { dlg.remove(); if (opener && opener.isConnected) opener.focus(); });
  document.body.append(dlg);
  if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  return dlg;
}
function showImageDialog(src, name, pw, ph, opener) {
  const touch = matchMedia('(pointer: coarse)').matches;
  const how = touch ? '이미지를 길게 눌러 저장해 주세요.' : '이미지에서 오른쪽 버튼을 눌러 "이미지를 다른 이름으로 저장"을 골라 주세요.';
  makeDialog('xi', '이미지로 저장', opener, [
    h('h2', { class: 'xd-h', text: '이미지로 저장' }),
    h('p', { class: 'xd-p', text: `미리보기 화면에서는 파일을 바로 내려받을 수 없어요. ${how}` }),
    h('div', { class: 'xi-frame' }, h('img', { src, alt: `${titleParts().title} 이미지`, width: pw, height: ph, draggable: 'true', title: name })),
  ]);
}

/* ═════════════ 3. PWA (live only) ═════════════ */
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
function headTag(tag, attrs) {
  const key = attrs.rel ? `${tag}[rel="${attrs.rel}"]` : `${tag}[name="${attrs.name}"]`;
  if (document.head.querySelector(key)) return;
  const el = document.createElement(tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  document.head.append(el);
}
let installBtn = null, deferredPrompt = null;
function initPWA() {
  if (!LIVE) return;
  headTag('link', { rel: 'manifest', href: '/manifest.webmanifest' });
  headTag('link', { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' });
  headTag('meta', { name: 'theme-color', content: tok('--page', '#131418') });
  headTag('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' });
  headTag('meta', { name: 'mobile-web-app-capable', content: 'yes' });
  headTag('meta', { name: 'apple-mobile-web-app-title', content: '판세' });
  headTag('meta', { name: 'apple-mobile-web-app-status-bar-style', content: 'black' });
  const secure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if ('serviceWorker' in navigator && secure && /^https?:$/.test(location.protocol)) {
    const reg = () => navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { /* app install is optional */ });
    if (document.readyState === 'complete') reg(); else addEventListener('load', reg, { once: true });
  }
  if (standalone()) return;
  const ua = navigator.userAgent;
  const iOS = /iP(hone|ad|od)/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const safari = iOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
  if (safari) showInstall('홈 화면에 추가', iosHint);
  addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    deferredPrompt = e;
    showInstall('앱으로 설치', async () => {
      const p = deferredPrompt;
      if (!p) return;
      deferredPrompt = null;
      try { p.prompt(); const r = await p.userChoice; if (r && r.outcome === 'accepted') hideInstall(); } catch (err) { /* dismissed */ }
    });
  });
  addEventListener('appinstalled', () => { deferredPrompt = null; hideInstall(); });
  const sm = matchMedia('(display-mode: standalone)');
  if (sm.addEventListener) sm.addEventListener('change', () => { if (sm.matches) hideInstall(); });
}
function showInstall(label, onClick) {
  if (!toolsEl || standalone()) return;
  hideInstall();
  installBtn = toolButton('install', label, onClick, { class: 'xt-btn xt-install' });
  toolsEl.append(installBtn);
}
function hideInstall() { if (installBtn) { installBtn.remove(); installBtn = null; } }
function iosHint(ev) {
  const share = svg('svg', { viewBox: '0 0 20 20', width: '16', height: '16', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'xp-share' },
    svg('path', { d: 'M10 2.8v9.4M6.6 6.1 10 2.8l3.4 3.3M6.5 9H5.2A1.2 1.2 0 0 0 4 10.2v5.6A1.2 1.2 0 0 0 5.2 17h9.6a1.2 1.2 0 0 0 1.2-1.2v-5.6A1.2 1.2 0 0 0 14.8 9h-1.3' }));
  makeDialog('xp', '홈 화면에 추가', ev && ev.currentTarget, [
    h('h2', { class: 'xd-h', text: '홈 화면에 추가' }),
    h('ol', { class: 'xp-steps' },
      h('li', {}, 'Safari 아래쪽(아이패드는 위쪽) ', h('b', {}, '공유 ', share), ' 버튼을 눌러요.'),
      h('li', {}, '목록에서 ', h('b', { text: '홈 화면에 추가' }), '를 골라요.'),
      h('li', {}, '홈 화면의 아이콘으로 열면 앱처럼 전체 화면으로 볼 수 있어요.')),
  ]);
}

/* ═════════════ 4. Replay (live only) ═════════════ */
const hmMin = t => { const m = String(t).replace(':', '').match(/^(\d\d)(\d\d)$/); return m ? +m[1] * 60 + +m[2] : NaN; };
const minLabel = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
// the slider's range follows the day's real frames: 09:00 … max(15:30, last frame); sessions that open at 10:00 or later
// (수능 day, first trading day) run 10:00 … 16:30
const SESSION = { s0: 9 * 60, s1: 15 * 60 + 30, slots: 390 };          // slider units are minutes
const slotOfT = t => { const m = hmMin(t); return isFinite(m) ? Math.round(m - SESSION.s0) : 0; };
function setSession(frames) {
  const mins = frames.map(f => hmMin(f.t)).filter(isFinite);
  const first = mins.length ? Math.min(...mins) : 9 * 60, last = mins.length ? Math.max(...mins) : 15 * 60 + 30;
  const late = first >= 10 * 60;
  const s0 = Math.min(late ? 10 * 60 : 9 * 60, Math.floor(first / 5) * 5);
  const s1 = Math.max(late ? 16 * 60 + 30 : 15 * 60 + 30, Math.ceil(last / 5) * 5);
  Object.assign(SESSION, { s0, s1, slots: s1 - s0 });
}
const replay = { open: false, el: null, btn: null, dates: null, date: null, day: null, cache: new Map(), i: -1, playing: false, delay: 500, mode: 5, timer: 0, req: 0, minute: new Set(), fillTok: 0, frameT: null, raf: 0 };
function rpTicks() {
  const ui = replay.ui, { s0, s1, slots } = SESSION;
  const marks = [s0];
  for (let m = Math.ceil((s0 + 1) / 60) * 60; m < s1; m += 60) marks.push(m);
  if (s1 - marks[marks.length - 1] < 40) marks.pop();          // the last hour mark would crowd the closing time
  marks.push(s1);
  ui.ticks.replaceChildren(...marks.map((m, k) => h('span', { class: k % 2 && k < marks.length - 1 ? 'o' : null, style: `left:${((m - s0) / slots) * 100}%`, text: minLabel(m) })));
  ui.slider.max = slots;
}
function rpSetH() {
  const R = replay;
  const px = R.open && R.el && !R.el.hidden ? Math.round(R.el.offsetHeight + (parseFloat(getComputedStyle(R.el).bottom) || 0)) : 0;
  document.documentElement.style.setProperty('--rp-h', px + 'px');
}

// playback speed = the pause between scenes. 5-minute days: 1× 2× 4× (default 2×, faster than the old 1×);
// 1-minute days have ~391 scenes, so the choices are seconds per scene (default 0.25 s: about 100 s a day)
const SPEEDS = {
  5: { def: 500, opts: [[1000, '1×', '1배속'], [500, '2×', '2배속'], [250, '4×', '4배속']] },
  1: { def: 250, opts: [[1000, '1초', '한 장면에 1초'], [500, '0.5초', '한 장면에 0.5초'], [250, '0.25초', '한 장면에 0.25초'], [120, '0.12초', '한 장면에 0.12초']] },
};
function rpSpeedUI(mode) {
  const R = replay, sp = SPEEDS[mode];
  if (R.mode === mode && R.ui.speed.children.length) return;
  R.mode = mode;
  R.delay = R.userDelay && sp.opts.some(o => o[0] === R.userDelay) ? R.userDelay : sp.def;
  R.ui.speed.replaceChildren(...sp.opts.map(([ms, label, aria]) => h('button', { type: 'button', 'data-v': ms, 'aria-pressed': String(ms === R.delay), text: label, 'aria-label': aria, onclick: () => setSpeed(ms) })));
}
function rpBuild() {
  const R = replay;
  const ui = R.ui = {};
  // ▶ ↔ ⏸ change in place (rotate · scale · opacity, controls.md §5-9): both shapes are drawn once, the button's data-on picks one
  ui.play = h('button', { type: 'button', class: 'rp-play', 'aria-label': '재생', onclick: () => togglePlay() },
    h('i', { class: 'rp-pi', 'aria-hidden': 'true' }, icon(ICON.play, true), icon(ICON.pause, true)));
  ui.time = h('div', { class: 'rp-time', 'aria-live': 'off', text: '--:--' });
  ui.day = h('div', { class: 'rp-day', text: '' });
  ui.idx = h('div', { class: 'rp-idx' });
  ui.date = h('select', { class: 'rp-date', 'aria-label': '날짜', onchange: e => loadDay(e.target.value, false) });
  ui.speed = h('div', { class: 'rp-speed seg', role: 'group', 'aria-label': '재생 속도' });     // a segment: one raised indicator (KH.ui.seg)
  ui.slider = h('input', { type: 'range', class: 'rp-slider', min: 0, max: SESSION.slots, step: 1, value: 0, 'aria-label': '시각' });
  ui.slider.addEventListener('input', () => { pause(); seekSlot(+ui.slider.value); });
  ui.ticks = h('div', { class: 'rp-ticks', 'aria-hidden': 'true' });
  ui.more = h('button', { type: 'button', class: 'rp-more', 'aria-label': '날짜·속도 설정', 'aria-expanded': 'false', 'aria-controls': 'rp-set', title: '날짜·속도 설정',
    onclick: () => { const on = !R.el.classList.contains('rp-more-on'); R.el.classList.toggle('rp-more-on', on); ui.more.setAttribute('aria-expanded', String(on)); } },
    h('span', { 'aria-hidden': 'true', text: '⋯' }));
  ui.msg = h('div', { class: 'rp-msg', role: 'status' });
  ui.note = h('div', { class: 'rp-note' });
  ui.close = h('button', { type: 'button', class: 'rp-x', 'aria-label': '리플레이 닫기', onclick: () => closeReplay() }, icon(ICON.close));
  const label = () => h('div', { class: 'rp-hd' }, h('span', { text: '장중 리플레이' }), h('span', { class: 'rp-badge', text: '지난 시세' }));
  ui.label = label;
  ui.set = h('div', { class: 'rp-set', id: 'rp-set' }, ui.date, ui.day, ui.speed);
  ui.body = h('div', { class: 'rp-main' },
    ui.play,
    h('div', { class: 'rp-when' }, label(), ui.time),
    h('div', { class: 'rp-track' }, ui.slider, ui.ticks),
    ui.more, ui.idx, ui.set);
  R.el = h('section', { class: 'rp-player', id: 'replay-player', role: 'region', 'aria-label': '장중 리플레이', hidden: true }, ui.close, ui.msg, ui.body, ui.note);
  document.body.append(R.el);
  rpTicks(); rpSpeedUI(5);
  if (UI && typeof UI.seg === 'function') UI.seg(ui.speed);         // placed once the player shows (the template's ResizeObserver)
  new ResizeObserver(rpSetH).observe(R.el);
  addEventListener('resize', rpSetH);
}
function rpState(kind, text, retry) {
  const ui = replay.ui;
  ui.body.hidden = kind !== 'ready';
  ui.msg.hidden = kind === 'ready';
  ui.msg.replaceChildren(ui.label(), h('p', { text }));
  if (retry) ui.msg.append(h('button', { type: 'button', class: 'rp-retry', onclick: retry, text: '다시 시도' }));
  ui.note.textContent = kind === 'ready' ? `${replay.day && replay.day.minute ? '1분' : '5분'}마다 기록한 시세예요. 정규장(${minLabel(SESSION.s0)}~${minLabel(SESSION.s1)}) 기준 · 네이버 증권` : kind === 'empty' ? `${replay.minute && replay.minute.size > 0 ? '1분' : '5분'}마다 기록한 시세예요. 네이버 증권` : '';
  if (kind === 'ready' && !narrowMQ.matches) ui.note.textContent += ' · 스페이스 재생/멈춤, ←/→ 한 칸씩';
}

async function openReplay(ev) {
  const R = replay;
  if (isWorldTab()) return;
  if (R.open) { closeReplay(); return; }
  if (!R.el) rpBuild();
  R.open = true;
  R.btn = (ev && ev.currentTarget) || R.btn;
  if (R.btn) R.btn.setAttribute('aria-expanded', 'true');
  R.el.hidden = false;
  document.documentElement.classList.add('rp-open');
  rpSetH();
  R.ui.close.focus();
  await loadDates();
}
async function loadDates() {
  const R = replay;
  rpState('loading', '기록된 날짜를 불러오는 중이에요…');
  try {
    const j = await getJSON('api/replay/dates');
    R.dates = (j && Array.isArray(j.dates) ? j.dates : []).filter(d => /^\d{4}-\d\d-\d\d$/.test(d));
    R.minute = new Set((j && Array.isArray(j.minute) ? j.minute : []).filter(d => /^\d{4}-\d\d-\d\d$/.test(d)));
  } catch (e) {
    if (!R.open) return;
    rpState('error', '기록된 날짜를 불러오지 못했어요. 네트워크를 확인하고 다시 시도해 주세요.', loadDates);
    return;
  }
  if (!R.open) return;
  if (!R.dates.length) { rpState('empty', '아직 기록된 날이 없어요. 다음 거래일 09:00부터 1분마다 기록돼서, 장이 열린 뒤에 다시 볼 수 있어요.'); return; }
  R.ui.date.replaceChildren(...R.dates.map(d => h('option', { value: d, text: dayLabel(d) })));
  R.ui.date.value = R.dates.includes(R.date) ? R.date : R.dates[0];
  await loadDay(R.ui.date.value, true);
}
async function loadDay(date, fallback) {
  const R = replay;
  pause();
  const id = ++R.req;
  // switching dates while a day is on screen: keep the player, report progress and problems on the count line
  const inline = !!(R.day && !R.ui.body.hidden);
  const fail = msg => {
    if (inline) { R.ui.day.textContent = msg; R.ui.date.value = R.date; return; }
    rpState('empty', msg);
  };
  let day = R.cache.get(date);
  if (!day) {
    if (inline) R.ui.day.textContent = '불러오는 중이에요…';
    else rpState('loading', `${dayLabel(date)} 기록을 불러오는 중이에요…`);
    try {
      const j = await getJSON('api/replay?date=' + encodeURIComponent(date), 20000);
      if (!j || !Array.isArray(j.codes) || !Array.isArray(j.frames)) throw new Error('bad shape');
      day = { date: j.date || date, codes: j.codes.map(String), byT: new Map(), frames: [], base: j.base || j.prev || null, minute: R.minute.has(j.date || date), fill: { done: new Set(), tries: {}, busy: false } };
      ingest(day, j.codes, j.frames, j.index);
      R.cache.set(date, day);
    } catch (e) {
      if (id !== R.req || !R.open) return;
      if (e.status === 404) {
        // the newest key may have expired between the two calls: fall back to the next recorded day
        const next = fallback && R.dates[R.dates.indexOf(date) + 1];
        if (next) { R.ui.date.value = next; loadDay(next, true); return; }
        fail(`${dayLabel(date)}에는 기록이 없어요.`);
      } else if (inline) fail('기록을 불러오지 못했어요. 다시 골라 주세요.');
      else rpState('error', '기록을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.', () => loadDay(date, fallback));
      return;
    }
  }
  if (id !== R.req || !R.open) return;
  if (!day.frames.length) { fail(`${dayLabel(date)}에는 아직 기록된 장면이 없어요. 장이 열리면 1분마다 쌓여요.`); return; }
  R.date = date; R.day = day;
  setSession(day.frames);
  rpTicks();
  rpState('ready');
  rpSpeedUI(day.minute ? 1 : 5);
  rpBand();
  showFrame(0);
  startFill(day);
}
function indexBase(day, key) {
  if (day.base && isFinite(+day.base[key])) return +day.base[key];
  // today's previous close is known from the strip (value − change)
  const it = strip.items && strip.items.find(x => x.key === key);
  if (it && it.spark && it.spark.length && isFinite(+it.change) && kstYmd(new Date(it.spark[0][0] * 1000)) === day.date) return +it.value - +it.change;
  return NaN;
}
// the day's whole index series in % vs the previous close, [['HHMM', pct], …]: built once per day, rebuilt only after new frames arrived
function dayIxs(day) {
  if (day.ixs && day.ixsN === day.frames.length) return day.ixs;
  const out = {};
  for (const k of ['KOSPI', 'KOSDAQ']) {
    const base = indexBase(day, k), a = [];
    if (isFinite(base) && base) for (const f of day.frames) {
      const e = f.ix && f.ix[k], v = e == null ? NaN : +(Array.isArray(e) ? e[0] : typeof e === 'object' ? e.value : e);
      if (isFinite(v)) a.push([String(f.t), (v / base - 1) * 100]);
    }
    out[k] = a;
  }
  day.ixs = out; day.ixsN = day.frames.length;
  return out;
}
// how: 'step' (←/→) or 'play' (a scene of playback) may roll the time's changed digits ('화려하게', KH.ui.roll); a drag or a new day
// writes it at once
function showFrame(i, how) {
  const R = replay, day = R.day;
  if (!day) return;
  i = Math.max(0, Math.min(day.frames.length - 1, i));
  const prevMin = R.curMin;
  R.i = i;
  const f = day.frames[i];
  R.frameT = hhmm(f.t); R.curMin = hmMin(f.t);
  const prices = new Map();
  for (let j = 0; j < day.codes.length; j++) {
    const p = f.p[j], r = f.r[j];
    if (p == null || r == null || !isFinite(p) || !isFinite(r)) continue;
    prices.set(day.codes[j], { p: +p, r: +r });
  }
  R.prices = prices;
  // the frame's index change in % (same numbers as the panel below) travels with the frame for the §3-16 tab numbers
  const ixr = {};
  for (const k of ['KOSPI', 'KOSDAQ']) {
    const e = f.ix && f.ix[k], v = e == null ? NaN : +(Array.isArray(e) ? e[0] : typeof e === 'object' ? e.value : e), base = indexBase(day, k);
    if (isFinite(v) && isFinite(base) && base) ixr[k] = (v / base - 1) * 100;
  }
  const ixs = dayIxs(day);
  cancelAnimationFrame(R.raf);
  // 'fancy' timelapse: while playing, the map tweens from frame to frame (the template ignores the option when it can't)
  const tw = R.playing && motion() === 'fancy' ? Math.round(R.delay * 0.92) : 0;
  R.raf = requestAnimationFrame(() => { try { KH.setReplay({ t: String(f.t), date: day.date, prices, index: ixr, ixs }, tw ? { tween: tw } : undefined); } catch (e) { /* map keeps its last frame */ } });
  const ui = R.ui, sl = slotOfT(f.t);
  // a scene shorter than the roll (fast playback) is written at once: digits that never settle say nothing
  const roll = UI && typeof UI.roll === 'function' && (how === 'step' || (how === 'play' && R.delay >= 400)) && isFinite(prevMin) && prevMin !== R.curMin;
  if (roll) UI.roll(ui.time, R.frameT, R.curMin > prevMin ? 1 : -1); else ui.time.textContent = R.frameT;
  bigUpdate();
  ui.slider.value = sl;
  ui.slider.setAttribute('aria-valuetext', `${dayLabel(day.date)} ${R.frameT}`);
  ui.slider.style.setProperty('--pos', (sl / SESSION.slots * 100) + '%');
  ui.idx.replaceChildren(...['KOSPI', 'KOSDAQ'].map(k => {
    const e = f.ix && f.ix[k];
    const v = e == null ? NaN : +(Array.isArray(e) ? e[0] : typeof e === 'object' ? e.value : e);
    const label = k === 'KOSPI' ? '코스피' : '코스닥';
    if (!isFinite(v)) return h('div', { class: 'rp-ix' }, h('span', { class: 'rp-k', text: label }), h('span', { class: 'rp-v', text: '—' }));
    const base = indexBase(day, k);
    const kids = [h('span', { class: 'rp-k', text: label }), h('span', { class: 'rp-v', text: fixed(v, 2) })];
    if (isFinite(base) && base) kids.push(h('span', { class: 'rp-r ' + dir(v - base), text: pct((v / base - 1) * 100) }));
    return h('div', { class: 'rp-ix' }, kids);
  }));
  const lastT = hhmm(day.frames[day.frames.length - 1].t);
  rpCount();
}

/* big time readout over a corner of the map while the timelapse plays ('fancy' only) */
function bigUpdate() {
  const R = replay;
  const want = R.open && R.playing && R.day && motion() === 'fancy' && !document.hidden;
  if (!want) { if (R.big) R.big.classList.remove('on'); return; }
  const map = document.getElementById('map'), stage = map && map.closest('.stage');
  if (!map || !stage || !map.offsetParent) { if (R.big) R.big.classList.remove('on'); return; }
  if (!R.big) { R.big = h('div', { class: 'rp-big', 'aria-hidden': 'true' }, h('b', { class: 'rp-big-t' }), h('span', { class: 'rp-big-d' })); }
  if (R.big.parentNode !== stage) stage.append(R.big);
  R.big.style.right = (stage.offsetWidth - (map.offsetLeft + map.offsetWidth) + 12) + 'px';
  R.big.style.bottom = (stage.offsetHeight - (map.offsetTop + map.offsetHeight) + 8) + 'px';
  R.big.firstChild.textContent = R.frameT || '';
  R.big.lastChild.textContent = dayLabel(R.day.date);
  R.big.classList.add('on');
}

/* ── frames: one Map per day keyed by minute; 5-minute skeleton first, 1-minute chunks merged in behind it ── */
function ingest(day, codes, frames, index) {
  const same = codes.length === day.codes.length && codes.every((c, k) => String(c) === day.codes[k]);
  const remap = same ? null : codes.map(c => day.codes.indexOf(String(c)));
  let added = 0;
  (frames || []).forEach((f, n) => {
    if (!f || f.t == null || !Array.isArray(f.p) || !Array.isArray(f.r)) return;
    const m = hmMin(f.t);
    if (!isFinite(m) || day.byT.has(m)) return;                       // keep what is there (the same frame as the 5-minute one)
    let p = f.p, r = f.r;
    if (remap) { p = day.codes.map(() => null); r = day.codes.map(() => null); remap.forEach((to, k) => { if (to >= 0) { p[to] = f.p[k]; r[to] = f.r[k]; } }); }
    const ix = {};
    for (const k of ['KOSPI', 'KOSDAQ']) { const a = index && index[k]; if (Array.isArray(a) && a[n] != null) ix[k] = a[n]; }
    day.byT.set(m, { t: String(f.t), p, r, ix });
    added++;
  });
  day.frames = [...day.byT.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1]);
  return added;
}
// grey band under the slider = 5-minute coverage; the lighter band on top = ranges that have 1-minute frames
function rpBand() {
  const R = replay, day = R.day, ui = R.ui;
  if (!day || !day.frames.length) return;
  const S = SESSION.slots, pc = v => (v / S * 100).toFixed(2) + '%';
  ui.slider.style.setProperty('--rec0', pc(slotOfT(day.frames[0].t)));
  ui.slider.style.setProperty('--rec1', pc(slotOfT(day.frames[day.frames.length - 1].t)));
  const mins = [...day.byT.keys()].sort((a, b) => a - b);
  const runs = [];
  for (const m of mins) {
    const last = runs[runs.length - 1];
    if (last && m - last[1] <= 1) last[1] = m; else runs.push([m, m]);
  }
  const fine = runs.filter(r => r[1] - r[0] >= 2);                   // 5-minute frames alone never make a run
  let g = 'linear-gradient(transparent,transparent)';
  if (fine.length) {
    const st = [`transparent 0 ${pc(fine[0][0] - SESSION.s0)}`];
    fine.forEach((r, k) => {
      const a = pc(r[0] - SESSION.s0), b = pc(r[1] - SESSION.s0);
      st.push(`var(--xe-fine) ${a} ${b}`, `transparent ${b} ${k < fine.length - 1 ? pc(fine[k + 1][0] - SESSION.s0) : '100%'}`);
    });
    g = `linear-gradient(90deg,${st.join(',')})`;
  }
  ui.slider.style.setProperty('--m1', g);
}
function rpCount() {
  const R = replay, day = R.day;
  if (!day || !R.ui) return;
  const lastT = hhmm(day.frames[day.frames.length - 1].t);
  const f = day.fill;
  let note = hmMin(lastT) < SESSION.s1 ? ` · ${lastT}까지 기록` : '';
  if (day.minute) note += f.done.size >= f.total ? ' · 1분 단위' : f.stalled ? ' · 1분 기록 일부만' : ` · 1분 기록 불러오는 중 ${f.done.size}/${f.total || '…'}`;
  R.ui.day.textContent = `${R.i + 1}/${day.frames.length}장면${note}`;
}

/* ── 1-minute chunks (<= 120 frames per call), the one nearest the current position first ── */
const CHUNK = 120;
function fillChunks() {
  const out = [];
  for (let a = SESSION.s0; a <= SESSION.s1; a += CHUNK) out.push([a, Math.min(a + CHUNK - 1, SESSION.s1)]);
  return out;
}
async function startFill(day) {
  const R = replay;
  if (!day.minute) return;
  const f = day.fill, tok = ++R.fillTok;
  if (f.busy) { f.busy = false; }
  f.busy = true;
  const chunks = fillChunks();
  f.total = chunks.length;
  const today = kstYmd(new Date()) === day.date;
  const nowMin = today ? kstNow().min : 1e9;
  const alive = () => R.open && R.day === day && tok === R.fillTok;
  rpCount();
  for (;;) {
    if (!alive()) { f.busy = false; return; }
    if (document.hidden) { await new Promise(r => { const on = () => { if (!document.hidden) { document.removeEventListener('visibilitychange', on); r(); } }; document.addEventListener('visibilitychange', on); }); continue; }
    const cur = isFinite(R.curMin) ? R.curMin : SESSION.s0;
    // the unfinished chunk nearest to where the viewer is
    let best = -1, bd = Infinity;
    chunks.forEach(([a, b], k) => {
      if (f.done.has(k) || (f.tries[k] || 0) >= 2) return;
      const d = cur < a ? a - cur : cur > b ? cur - b : 0;
      if (d < bd) { bd = d; best = k; }
    });
    if (best < 0) break;
    const [a, b] = chunks[best];
    try {
      const j = await getJSON(`api/replay?date=${encodeURIComponent(day.date)}&step=1&from=${minLabel(a).replace(':', '')}&to=${minLabel(b).replace(':', '')}`, 20000);
      if (!alive()) { f.busy = false; return; }
      if (!j || !Array.isArray(j.frames)) throw new Error('bad shape');
      const cmin = R.curMin;
      ingest(day, Array.isArray(j.codes) ? j.codes.map(String) : day.codes, j.frames, j.index);
      if (R.i >= 0 && isFinite(cmin)) { const ni = day.frames.findIndex(x => hmMin(x.t) === cmin); if (ni >= 0) R.i = ni; }
      if (!(today && b > nowMin - 2)) f.done.add(best);             // today's last chunk keeps growing: it stays open
      else f.tries[best] = 2;
      rpBand(); rpCount();
      if (!R.playing && R.day === day) showFrame(R.i);   // re-send the day's index line with the new frames
    } catch (e) {
      if (!alive()) { f.busy = false; return; }
      f.tries[best] = (f.tries[best] || 0) + 1;
      await new Promise(r => setTimeout(r, 1500));
    }
  }
  f.busy = false;
  f.stalled = f.done.size < f.total && !today;
  if (alive()) rpCount();
}
function seekSlot(sl) {
  const day = replay.day;
  if (!day) return;
  let best = 0;
  for (let i = 0; i < day.frames.length; i++) if (slotOfT(day.frames[i].t) <= sl) best = i;
  showFrame(best);
}
function step(d) { pause(); showFrame(replay.i + d, 'step'); }
function setPlayIcon() {
  const ui = replay.ui;
  ui.play.toggleAttribute('data-on', replay.playing);
  ui.play.setAttribute('aria-label', replay.playing ? '멈춤' : '재생');
}
function tick() {
  const R = replay;
  if (!R.playing || !R.day) return;
  if (R.i >= R.day.frames.length - 1) { pause(); return; }
  showFrame(R.i + 1, 'play');
  R.timer = setTimeout(tick, R.delay);
}
function play() {
  const R = replay;
  if (!R.day || R.playing) return;
  if (R.i >= R.day.frames.length - 1) showFrame(0);
  R.playing = true; setPlayIcon(); bigUpdate();
  R.timer = setTimeout(tick, R.delay);
}
function pause() {
  const R = replay;
  clearTimeout(R.timer);
  if (!R.playing) return;
  R.playing = false;
  if (R.ui) setPlayIcon();
  bigUpdate();
}
function togglePlay() { replay.playing ? pause() : play(); }
function setSpeed(v) {
  const R = replay;
  R.delay = R.userDelay = v;
  for (const b of R.ui.speed.children) b.setAttribute('aria-pressed', String(+b.dataset.v === v));
  if (R.playing) { clearTimeout(R.timer); R.timer = setTimeout(tick, v); }
}
function closeReplay() {
  const R = replay;
  if (!R.open) return;
  pause();
  R.open = false; R.frameT = null; R.prices = null; R.req++; R.fillTok++;
  cancelAnimationFrame(R.raf);
  try { KH.setReplay(null); } catch (e) { /* nothing to undo */ }
  R.el.hidden = true;
  if (R.big) R.big.classList.remove('on');
  document.documentElement.classList.remove('rp-open');
  rpSetH();
  if (R.btn) { R.btn.setAttribute('aria-expanded', 'false'); R.btn.focus(); }
}
let spaceTaken = false;
function rpKeys(e) {
  const R = replay;
  spaceTaken = false;
  if (!R.open || e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
  // anything layered above the player (dialogs, the heatmap's detail sheet, the stock page) keeps its own keys
  if (document.querySelector('dialog[open], #sheet.open')) return;
  if (window.KHStock && typeof window.KHStock.isOpen === 'function' && window.KHStock.isOpen()) return;
  const t = e.target;
  const textField = t && (t.isContentEditable || t.tagName === 'TEXTAREA' || (t.tagName === 'INPUT' && t.type !== 'range'));
  if (textField) return;                                   // e.g. Esc in the search box clears the search
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeReplay(); return; }
  if (t && t.tagName === 'SELECT') return;                 // the date picker uses arrows and Space itself
  if (!R.day || !R.ui || R.ui.body.hidden) return;
  if (e.key === ' ' || e.code === 'Space') { e.preventDefault(); e.stopPropagation(); spaceTaken = true; if (!e.repeat) togglePlay(); }
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); step(e.key === 'ArrowLeft' ? -1 : 1); }
}

/* ═════════════ 5. Clock + session progress (#clock, §3-6) ═════════════ */
const clockEl = document.getElementById('clock');
const getSet = (k, d) => {
  try { if (has('getSetting')) { const v = KH.getSetting(k); if (v != null) return v; } } catch (e) { /* storage fallback */ }
  try { const v = localStorage.getItem('khm.set.' + k); if (v != null) return v === 'true' ? true : v === 'false' ? false : v; } catch (e) { /* default */ }
  return d;
};
/* server time (§3-17): offset = server − (local send time + RTT/2), NTP style; the sample with the shortest round trip wins */
const tsync = { off: 0, pend: null, rtt: Infinity, ok: false, rev: 0, timer: 0, busy: false };
const nowMs = () => Date.now() + tsync.off;
if (!has('now')) KH.now = nowMs;
async function timeSample() {
  const t0 = Date.now(), p0 = performance.now();
  const j = await getJSON('api/time', 5000);
  const rtt = performance.now() - p0;
  if (!j || !isFinite(+j.t)) throw new Error('bad shape');
  return { off: +j.t - (t0 + rtt / 2), rtt };
}
function timeAdopt(sm, first) {
  const diff = Math.abs(sm.off - tsync.off);
  tsync.rtt = sm.rtt; tsync.ok = true; tsync.rev++;
  if (first || diff > 2000) { tsync.off = sm.off; tsync.pend = null; ckRender(); }    // big jump: snap now
  else tsync.pend = sm.off;                                                          // small change: from the next second on
}
async function timeSync(initial) {
  if (!LIVE || tsync.busy) return;
  tsync.busy = true;
  try {
    if (initial) {
      let best = null;
      for (let k = 0; k < 3; k++) { try { const sm = await timeSample(); if (!best || sm.rtt < best.rtt) best = sm; } catch (e) { /* try the next one */ } }
      if (best) timeAdopt(best, true);
    } else {
      const sm = await timeSample();
      // a much slower round trip is not trusted, unless the clock is clearly off (then the old offset is worse than a noisy one)
      if (!tsync.ok || sm.rtt <= tsync.rtt * 2 + 40 || Math.abs(sm.off - tsync.off) > 2000) timeAdopt(sm, !tsync.ok);
    }
  } catch (e) { /* offset stays as it was (0 if there never was a sample) */ }
  tsync.busy = false;
}
function timeLine() {
  if (!tsync.ok) return '';
  const d = Math.abs(tsync.off) / 1000;
  return d < 0.1 ? '서버 시각 기준 · 이 기기와 같아요' : `서버 시각 기준 · 이 기기와 ${d.toFixed(1)}초 차이`;
}
const kstNow = () => {
  const d = new Date(nowMs() + 9 * 36e5);                       // KST wall clock, whatever the viewer's time zone is
  const h24 = d.getUTCHours(), m = d.getUTCMinutes(), s = d.getUTCSeconds();
  return { dow: d.getUTCDay(), h: h24, m, s, ms: d.getUTCMilliseconds(), min: h24 * 60 + m, date: d.toISOString().slice(0, 10) };
};
const two = n => String(n).padStart(2, '0');
const hm2m = t => +String(t).slice(0, 2) * 60 + +String(t).slice(2, 4);
// the clock's session arc keeps these in every theme (사용자 2026-11-13 19:45 ⑤); the session bar's hues are the theme's --sb-* tokens
const PH_FIX = { pre: '#6f78e6', am: '#5cc0f2', pm: '#ffb547', auc: '#ee7a2c', nxt: '#a97bf2', night: '#4a5f9c' };
const PH_TOK = { pre: '--sb-dawn', am: '--sb-am', pm: '--sb-pm', auc: '--sb-close', nxt: '--sb-after', night: '--sb-night' };
const PH = Object.assign({}, PH_FIX);
function phRead() { for (const k in PH_TOK) PH[k] = tok(PH_TOK[k], PH_FIX[k]); }
phRead();
const PHN = { pre: '장 시작 전', am: '오전장', pm: '오후장', auc: '마감 동시호가', nxt: 'NXT 애프터마켓', night: '밤·휴장' };
const ck = { on: false, style: 'digital', cells: [], timer: 0, raf: 0, busy: false, shown: '', lastMin: -1, key: '' };

function ckSession() {
  const s = strip.session;
  const a = s ? hm2m(s.start) : 9 * 60, b = s ? hm2m(s.end) : 15 * 60 + 30;
  return b > a ? { start: a, end: b } : { start: 9 * 60, end: 15 * 60 + 30 };
}
// phase from the KST clock. Holiday: weekend, or a weekday whose quotes carry no record from today once the session is under way
function ckPhase(n) {
  const { start, end } = ckSession();
  const mid = Math.min(start + 180, Math.round((start + end) / 2)), auc = end - 10, nxtEnd = 20 * 60;
  const t = n.min + n.s / 60;
  let hol = n.dow === 0 || n.dow === 6;
  if (!hol && LIVE && t >= start + 10) {
    try {
      let ms = null;
      if (has('marketStatus')) ms = KH.marketStatus();
      if (ms && typeof ms === 'object') { const v = Object.values(ms); hol = t < end && v.length > 0 && v.every(x => x === 'CLOSE'); }
      else if (has('asOf')) { const a = KH.asOf(); const d = a ? new Date(a) : null; if (d && !isNaN(d) && kstYmd(d) < n.date) hol = true; }
    } catch (e) { /* unknown: not a holiday */ }
  }
  const seg = { start, mid, auc, end };
  if (hol) return { key: 'night', text: '휴장', fill: 0, mode: 'solid', seg };
  if (t < 8 * 60) return { key: 'night', text: '장 시작 전', fill: 0, mode: 'solid', seg };
  if (t < start) {
    const left = Math.ceil(start - t);
    return { key: 'pre', text: t >= start - 30 ? `장 시작 전 · ${left}분 남음` : '장 시작 전', fill: (t - 8 * 60) / (start - 8 * 60), mode: 'solid', seg };
  }
  if (t < end) {
    const f = (t - start) / (end - start);
    const key = t >= auc ? 'auc' : t >= mid ? 'pm' : 'am';
    return { key, text: t >= auc ? '마감 동시호가' : `정규장 ${Math.min(99, Math.floor(f * 100))}%`, fill: f, mode: 'reg', seg, pct: Math.floor(f * 100) };
  }
  if (t < nxtEnd) return { key: 'nxt', text: '장 마감 · NXT 20:00까지', fill: (t - end) / (nxtEnd - end), mode: 'solid', seg };
  return { key: 'night', text: '장 마감', fill: 0, mode: 'solid', seg };
}

/* clean digital digit: a plain tabular numeral; 'fancy' slides the old one up and out and the new one in (<= 220 ms) */
function flapCell(ch) {
  const el = h('span', { class: 'xdg' }, h('i', { text: ch }));
  el.cur = ch; el.want = ch; el.busy = false;
  return el;
}
async function slideOnce(cell, to) {
  const old = cell.firstChild;
  const nw = h('i', { class: 'xdg-n', text: to });
  cell.append(nw);
  const dur = 220, ease = 'cubic-bezier(.2,.7,.2,1)';
  try {
    old.style.position = 'absolute'; old.style.left = '0'; old.style.right = '0';
    old.animate([{ transform: 'translateY(0)', opacity: 1 }, { transform: 'translateY(-45%)', opacity: 0 }], { duration: dur, easing: ease, fill: 'forwards' });
    await nw.animate([{ transform: 'translateY(45%)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }], { duration: dur, easing: ease, fill: 'both' }).finished;
  } catch (e) { /* cancelled: settle below */ }
  old.remove();
  nw.className = ''; nw.getAnimations().forEach(x => x.cancel());
  cell.cur = to;
}
async function cellSet(cell, ch, force) {
  cell.want = ch;
  if (cell.busy) return;
  cell.busy = true;
  try {
    while (cell.cur !== cell.want || force) {
      const lvl = motion(), to = cell.want;
      if (lvl !== 'fancy' || document.hidden) {
        cell.firstChild.textContent = to; cell.cur = to;
        if (force && lvl === 'standard') { cell.classList.remove('xdg-blink'); void cell.offsetWidth; cell.classList.add('xdg-blink'); }
      } else await slideOnce(cell, to);
      force = false;
    }
  } finally { cell.busy = false; }
}

const XA_ARC_R = 48.25, XA_ARC_W = 3.5;     // the rim band between the face (r 46.5) and the dial's edge (r 50)
function ckAnalogSvg() {
  const S = (t, a, ...k) => svg(t, a, ...k);
  const root = S('svg', { viewBox: '0 0 100 100', class: 'xa', 'aria-hidden': 'true', focusable: 'false' });
  // the dark rim (r 46.5 → 50) carries the KRX session arc (ckArc): outside the ticks, so hands and ticks read as before
  const arc = S('g', { class: 'xa-arc', fill: 'none', 'stroke-width': XA_ARC_W, 'stroke-linecap': 'butt' });
  root.append(S('circle', { cx: 50, cy: 50, r: 50, fill: '#2a2c33' }), arc, S('circle', { cx: 50, cy: 50, r: 46.5, fill: '#f4f1e8' }), S('circle', { cx: 50, cy: 50, r: 41.6, fill: 'none', stroke: '#d9d5c8', 'stroke-width': 0.5 }));
  root._arc = arc;
  for (let i = 0; i < 60; i++) {
    const a = i * 6 * Math.PI / 180, big = i % 5 === 0, r1 = 45, r2 = big ? 36.5 : 42.6;
    if (big) root.append(S('line', { x1: 50 + Math.sin(a) * r1, y1: 50 - Math.cos(a) * r1, x2: 50 + Math.sin(a) * r2, y2: 50 - Math.cos(a) * r2, stroke: '#17181c', 'stroke-width': i % 15 === 0 ? 3.8 : 2.8, 'stroke-linecap': 'butt' }));
    else root.append(S('circle', { cx: 50 + Math.sin(a) * 43.6, cy: 50 - Math.cos(a) * 43.6, r: 0.8, fill: '#6b6a64' }));
  }
  const gw = S('g', { class: 'xa-wig' });
  const hh = S('g', { class: 'xa-g xa-hh' }, S('polygon', { points: '47.2,57 52.8,57 51.9,27 48.1,27', fill: '#17181c' }), S('rect', { class: 'xa-in', x: 49.2, y: 33, width: 1.6, height: 15, fill: '#f4f1e8', opacity: 0.9 }));
  const mh = S('g', { class: 'xa-g xa-mh' }, S('polygon', { points: '47.6,58 52.4,58 51.5,10 48.5,10', fill: '#17181c' }), S('rect', { class: 'xa-in', x: 49.35, y: 17, width: 1.3, height: 24, fill: '#f4f1e8', opacity: 0.9 }));
  // second hand: red (사용자 14:21) ending in a hollow ring, not the railway clock's solid disc (사용자 2026-11-13 20:19). The shaft
  // stops inside the ring's stroke, so the ring's middle shows the face; ring stroke 2.8 + hole 7.2 still read on the 38px phone dial
  const SEC = '#e5231b';
  const sh = S('g', { class: 'xa-g xa-sh' }, S('rect', { class: 'xa-shaft', x: 48.7, y: 24.6, width: 2.6, height: 37.4, rx: 0.6, fill: SEC }), S('rect', { x: 48.3, y: 56, width: 3.4, height: 11, rx: 0.8, fill: SEC }),
    S('circle', { class: 'xa-tip', cx: 50, cy: 19.5, r: 5, fill: 'none', stroke: SEC, 'stroke-width': 2.8 }));
  gw.append(hh, mh, sh, S('circle', { cx: 50, cy: 50, r: 2.8, fill: SEC, stroke: '#17181c', 'stroke-width': 0.7 }));
  root.append(gw);
  root._h = hh; root._m = mh; root._s = sh; root._w = gw;
  return root;
}
function ckAnalogSet(n, sweep) {
  const a = ck.analog; if (!a) return;
  const lvl = motion();
  const mAng = n.m * 6, hAng = (n.h % 12) * 30 + n.m * 0.5;
  const tr = (el, ang, t) => { el.style.transition = t || 'none'; el.style.transform = `rotate(${ang}deg)`; };
  const first = ck.mAng == null;
  const minuteMoved = ck.mAng !== mAng;
  const mt = lvl === 'reduced' || first ? 'none' : 'transform .38s cubic-bezier(.3,1.7,.5,1)';
  if (minuteMoved) { tr(a._m, mAng, mt); tr(a._h, hAng, mt); ck.mAng = mAng; }
  a._s.style.display = lvl === 'reduced' ? 'none' : '';
  if (lvl === 'standard') tr(a._s, n.s * 6, n.s === 0 || first ? 'none' : 'transform .14s cubic-bezier(.4,2.2,.5,1)');
  else if (lvl === 'fancy' && !sweep) { const f = Math.min(1, (n.s + n.ms / 1000) / 58.5); tr(a._s, f * 360, 'none'); }
}
/* §3-6 + 사용자 2026-11-13 20:19: the KRX regular session as an arc on the dial's rim — 09:00 (the 9 o'clock spot) → the close
   (3:30, or 4:30 on a 1630 day, from /api/market session). The session bar's hues: 오전 sky, 오후 amber, 마감 동시호가 deep orange
   (never red / green); the part already past is strong, what is left faint. Weekends and holidays: one grey faint arc (the window
   is shown, nothing in it is coming). Redrawn only when the minute, the session or the holiday state changes. */
function ckArc(n, ph) {
  const g = ck.analog && ck.analog._arc; if (!g) return;
  const { start, mid, auc, end } = ph.seg, hol = ph.text === '휴장', t = n.min;
  const sig = [start, mid, auc, end, hol ? 'h' : t].join();
  if (g._sig === sig) return;
  g._sig = sig;
  const P = th => { const a = th * Math.PI / 180; return `${(50 + XA_ARC_R * Math.sin(a)).toFixed(2)} ${(50 - XA_ARC_R * Math.cos(a)).toFixed(2)}`; };
  const ang = m => m / 60 * 30;                                   // minutes since 00:00 → degrees clockwise from 12 (unbounded)
  const path = (a, b, color, op, cls) => {
    if (b - a < 0.25) return null;
    const t0 = ang(a), t1 = ang(b);
    return svg('path', { class: cls, d: `M${P(t0)}A${XA_ARC_R} ${XA_ARC_R} 0 ${t1 - t0 > 180 ? 1 : 0} 1 ${P(t1)}`, stroke: color, 'stroke-opacity': op });
  };
  const out = [];
  if (hol) out.push(path(start, end, '#8d929c', 0.55, 'xa-a-hol'));
  else for (const [a, b, c] of [[start, mid, PH_FIX.am], [mid, auc, PH_FIX.pm], [auc, end, PH_FIX.auc]]) {
    out.push(path(a, Math.min(b, Math.max(a, t)), c, 1, 'xa-a-past'), path(Math.max(a, Math.min(b, t)), b, c, 0.32, 'xa-a-left'));
  }
  g.replaceChildren(...out.filter(Boolean));
}
/* 사용자 2026-11-13 20:19: the last ten minutes before the open (08:50 → 09:00) and before the close (15:20 → close) count down in the
   seconds slot, "−09:42" — from the corrected clock (kstNow, §3-17). Not on weekends / holidays. → {kind, secs, text, min} | null */
function ckCountdown(n, ph) {
  if (ph.text === '휴장' || n.dow === 0 || n.dow === 6) return null;
  const { start, end } = ph.seg, now = n.min * 60 + n.s;
  let kind = null, target = 0;
  if (now >= (start - 10) * 60 && now < start * 60) { kind = 'open'; target = start * 60; }
  else if (now >= (end - 10) * 60 && now < end * 60) { kind = 'close'; target = end * 60; }
  if (!kind) return null;
  const secs = target - now;
  return { kind, secs, min: Math.ceil(secs / 60), text: `${MINUS}${two(Math.floor(secs / 60))}:${two(secs % 60)}` };
}
function ckSweep() {
  cancelAnimationFrame(ck.raf);
  if (!ck.on || !ck.analog || motion() !== 'fancy' || document.hidden) return;
  const frame = () => {
    const n = kstNow();
    // the station-clock way: the hand sweeps in 58.5 s, waits at 12, and the minute hand drops when it restarts
    const f = Math.min(1, (n.s + n.ms / 1000) / 58.5);
    ck.analog._s.style.transition = 'none'; ck.analog._s.style.transform = `rotate(${f * 360}deg)`;
    ck.raf = requestAnimationFrame(frame);
  };
  ck.raf = requestAnimationFrame(frame);
}

function ckBuild() {
  const narrow = matchMedia('(max-width: 760px)').matches;
  let want = getSet('clockStyle', 'both');   // 기본 둘 다 (사용자 2026-11-10 13:58)
  if (want === 'flap') want = 'digital';
  const style = want === 'both' ? 'both' : want === 'analog' && !narrow ? 'analog' : 'digital';   // phones: analog alone gives way to the flap digits
  ck.style = style; ck.cells = []; ck.analog = null; ck.mAng = null; ck.shown = '';
  const face = h('span', { class: 'xc-face xc-' + style });
  if (style !== 'digital') { ck.analog = ckAnalogSvg(); face.append(ck.analog); }
  ck.dig = null;
  if (style === 'analog') {
    // analog alone: HH:MM beside the dial, the countdown under it (same column: the clock keeps its width)
    ck.dig = h('span', { class: 'xc-dig', text: '' });
    ck.sec = h('span', { class: 'xc-sec', text: '' });
    face.append(h('span', { class: 'xc-dcol' }, ck.dig, ck.sec));
  } else {
    const n = kstNow();
    const cells = [...(two(n.h) + two(n.m))].map(flapCell);
    ck.cells = cells;
    ck.sec = h('span', { class: 'xc-sec', text: two(n.s) });
    face.append(h('span', { class: 'xc-digits' }, cells[0], cells[1], h('span', { class: 'xc-colon', text: ':' }), cells[2], cells[3]), ck.sec);
  }
  // while the refresh runs: a 14px ring just right of the digits (absolute: the clock keeps its size); the result is a bubble
  const ring = uiIcon('spin');
  if (ring) ring.classList.add('xc-ring');
  // 마감 동시호가: a thin amber outline (steady) and, as it starts, one glow (xc-glo, absolute: no layout)
  ck.glo = h('span', { class: 'xc-glo', 'aria-hidden': 'true' });
  // its press refreshes, so no aria-haspopup / aria-expanded: the world clock is its context menu (described in #ck-desc, Shift+F10)
  ck.btn = h('button', { type: 'button', class: 'xc-btn', 'aria-keyshortcuts': 'Shift+F10', onclick: ckTap }, face, ck.glo, ring);
  ckPressHooks(ck.btn);
  ck.desc = h('span', { id: 'ck-desc', class: 'xc-sr' });
  ck.wasAuc = undefined;
  clockEl.replaceChildren(ck.btn, ck.desc);
}

function ckRender(instant) {
  if (!ck.on || !clockEl) return;
  if (tsync.pend != null) { tsync.off = tsync.pend; tsync.pend = null; }
  const n = kstNow(), lvl = motion();
  const t = two(n.h) + two(n.m);
  const ph = ckPhase(n), cd = ckCountdown(n, ph);
  ck.cdNow = cd;
  if (ck.cells.length) ck.cells.forEach((c, i) => cellSet(c, t[i]));
  // the seconds slot: the seconds (none under 줄이기, which ticks once a minute), or the countdown — plain text at every effect
  // level, like the seconds it replaces (a roll every second would be motion that never stops beside the map); never announced:
  // the label below says it once a minute
  ck.btn.classList.toggle('xc-cdon', !!cd);
  if (ck.sec) {
    ck.sec.classList.toggle('xc-cd', !!cd);
    if (cd) ck.sec.dataset.kind = cd.kind; else delete ck.sec.dataset.kind;
    const txt = cd ? cd.text : ck.cells.length && lvl !== 'reduced' ? two(n.s) : '';
    if (ck.sec.textContent !== txt) ck.sec.textContent = txt;
  }
  if (ck.analog) { ckAnalogSet(n); ckArc(n, ph); }
  if (ck.dig) ck.dig.textContent = `${two(n.h)}:${two(n.m)}`;
  ckAuction(n, ph, lvl);
  const cdTxt = cd ? `${cd.kind === 'open' ? '개장' : '장 마감'}까지 ${cd.min}분` : '';
  if (ck.lastMin !== n.min || ck.lastTxt !== ph.text || ck.lastRev !== tsync.rev || ck.lastCd !== cdTxt) {
    ck.lastMin = n.min; ck.lastTxt = ph.text; ck.lastRev = tsync.rev; ck.lastCd = cdTxt;
    ck.btn.setAttribute('aria-label', `판세 · 지금 ${two(n.h)}:${two(n.m)}${cdTxt ? ' · ' + cdTxt : ''} · 눌러서 새로고침`);
    const tl = timeLine();
    ck.btn.title = `${cdTxt || ph.text} · 눌러서 새로고침\n길게 누르거나 오른쪽 클릭하면 세계 시각 (Shift+F10)${tl ? '\n' + tl : ''}`;
    ck.desc.textContent = `${tl ? tl + '. ' : ''}길게 누르거나 Shift+F10을 누르면 세계 시각을 보여 줘요.`;
    ck.btn.setAttribute('aria-describedby', 'ck-desc');
  }
  if (wc.open) wcRender();
  sbRender(n, ph, lvl);
}
/* 마감 동시호가 (end − 10 → end): a steady thin amber outline the whole time; as it starts (seen within its first minute) one amber
   glow of 1.2 s — 기본 · 화려하게 only, 줄이기 = the outline alone. Fixed colours: the clock looks the same in every theme. */
function ckAuction(n, ph, lvl) {
  const on = ph.key === 'auc';
  ck.btn.classList.toggle('xc-auc', on);
  if (on && ck.wasAuc === false && lvl !== 'reduced' && !document.hidden && n.min * 60 + n.s - ph.seg.auc * 60 < 60) {
    ck.glo.classList.remove('run'); void ck.glo.offsetWidth; ck.glo.classList.add('run');
  }
  if (!on) ck.glo.classList.remove('run');
  ck.wasAuc = on;
}

/* ── session bar (#session-bar): a thick underline along the header's bottom edge, 08:00 → 20:00, with a sun / moon riding it ── */
const sbEl = document.getElementById('session-bar');
const SB0 = 8 * 60, SB1 = 20 * 60;
const sb = { built: false, sig: '', tipT: 0 };
const fmtLeft = m => { m = Math.max(1, Math.ceil(m)); const hh = Math.floor(m / 60), mm = m % 60; return hh ? `${hh}시간${mm ? ' ' + mm + '분' : ''}` : `${mm}분`; };
function sbIcon(kind) {
  const S = (t, a, ...k) => svg(t, a, ...k);
  const root = S('svg', { viewBox: '0 0 20 20', width: 22, height: 22, class: 'sb-svg sb-' + kind, 'aria-hidden': 'true', focusable: 'false' });
  const ray = (ang, r1, r2, cx, cy) => { const a = ang * Math.PI / 180; return S('line', { x1: (cx + Math.cos(a) * r1).toFixed(2), y1: (cy + Math.sin(a) * r1).toFixed(2), x2: (cx + Math.cos(a) * r2).toFixed(2), y2: (cy + Math.sin(a) * r2).toFixed(2), style: 'stroke:var(--xe-ray)', 'stroke-width': 1.5, 'stroke-linecap': 'round' }); };
  if (kind === 'moon') {
    root.append(S('path', { d: 'M12.6 2.6a7.6 7.6 0 1 0 4.8 12.9A6.3 6.3 0 0 1 12.6 2.6z', style: 'fill:var(--xe-moon)' }), S('circle', { cx: 15.2, cy: 4.6, r: 0.9, style: 'fill:var(--xe-moon)' }));
  } else if (kind === 'rise') {
    root.append(S('g', { class: 'sb-rays' }, ...[180, 215, 250, 290, 325, 360].map(a => ray(a, 7.6, 10, 10, 14))),
      S('path', { d: 'M3.8 14a6.2 6.2 0 0 1 12.4 0z', style: 'fill:var(--xe-sun)' }), S('line', { x1: 1, y1: 14.6, x2: 19, y2: 14.6, style: 'stroke:var(--xe-ray)', 'stroke-width': 1.3, 'stroke-linecap': 'round' }));
  } else {
    root.append(S('g', { class: 'sb-rays' }, ...[0, 45, 90, 135, 180, 225, 270, 315].map(a => ray(a, 6.6, 9.2, 10, 10))), S('circle', { cx: 10, cy: 10, r: 4.6, style: 'fill:var(--xe-sun)' }));
  }
  return root;
}
// the phase the pill names (§3-24): label, icon, colour, and the phase's own progress (the number the tooltip uses)
function sbPhase(n, ph) {
  const t = n.min + n.s / 60, { start, end } = ph.seg;
  if (ph.text === '휴장') return { id: 'hol', label: '휴장', icon: 'caloff', color: lightTone() ? tok('--muted', '#535a65') : '#a3a9b6' };
  if (t < start) return { id: 'pre', label: '장 전', icon: 'glass', color: PH.pre, pct: t >= 8 * 60 ? Math.min(99, Math.floor(ph.fill * 100)) : null };
  if (t < end) return ph.key === 'auc' ? { id: 'auc', label: '마감 동시호가', icon: 'bell', color: PH.auc, pct: null }
    : { id: 'reg', label: '장 중', icon: 'candle', color: PH[ph.key], pct: ph.pct };
  if (t < SB1) return { id: 'nxt', label: '애프터마켓', icon: 'moon', color: lightTone() ? PH.nxt : '#b99cf7', pct: Math.min(99, Math.floor(ph.fill * 100)) };
  return { id: 'end', label: '장 마감', icon: 'lock', color: lightTone() ? PH.night : '#8f9fd8' };
}
function sbPhaseIcon(kind) {
  const S = (t, a, ...k) => svg(t, a, ...k);
  const root = S('svg', { viewBox: '0 0 12 12', class: 'sb-pi sb-pi-' + kind, 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
  if (kind === 'glass') root.append(S('path', { d: 'M3 1.4h6M3 10.6h6M3.7 1.4c0 2.3 1.3 2.9 2.3 4.6-1 1.7-2.3 2.3-2.3 4.6M8.3 1.4c0 2.3-1.3 2.9-2.3 4.6 1 1.7 2.3 2.3 2.3 4.6' }));
  else if (kind === 'candle') root.append(S('path', { d: 'M3.4 1.2v9.6M8.6 2.2v8.2' }), S('rect', { x: 2.2, y: 3.2, width: 2.4, height: 4.4, rx: .4, fill: 'currentColor' }), S('rect', { x: 7.4, y: 4.2, width: 2.4, height: 3.4, rx: .4 }));
  else if (kind === 'bell') root.append(S('g', { class: 'sb-bell' }, S('path', { d: 'M6 1.5c-1.9 0-3 1.4-3 3.2v1.9L1.9 8.4h8.2L9 6.6V4.7C9 2.9 7.9 1.5 6 1.5z', fill: 'currentColor', 'fill-opacity': '.25' }), S('path', { d: 'M4.9 9.8a1.2 1.2 0 0 0 2.2 0' })));
  else if (kind === 'moon') root.append(S('path', { d: 'M7.3 1.3a4.7 4.7 0 1 0 3.5 7.9A3.9 3.9 0 0 1 7.3 1.3z', fill: 'currentColor', stroke: 'none' }));
  else if (kind === 'lock') root.append(S('rect', { x: 2.4, y: 5.3, width: 7.2, height: 5.3, rx: 1.2, fill: 'currentColor', 'fill-opacity': '.25' }), S('path', { d: 'M4 5.3V3.9a2 2 0 0 1 4 0v1.4' }));
  else root.append(S('rect', { x: 1.7, y: 2.4, width: 8.6, height: 7.8, rx: 1.3 }), S('path', { d: 'M1.7 4.9h8.6M4 1.3v2M8 1.3v2M1.2 11l9.6-9.6' }));
  return root;
}
function sbBuild() {
  sb.segs = h('div', { class: 'sb-segs' });
  sb.fill = h('div', { class: 'sb-fill' });
  sb.track = h('div', { class: 'sb-track' }, sb.segs, sb.fill);
  sb.cap = h('span', { class: 'sb-cap' });
  sb.pi = h('span', { class: 'sb-picon' });
  sb.pt = h('span', { class: 'sb-pt' });
  sb.pp = h('span', { class: 'sb-pp' });
  sb.ico = h('div', { class: 'sb-pill' }, sb.cap, sb.pi, sb.pt, sb.pp);
  // the note repeats the bar's aria-valuetext: hidden from screen readers (it changes every minute and would be read out each time)
  sb.tip = h('div', { class: 'sb-tip', 'aria-hidden': 'true' });
  sb.box = h('div', { class: 'sb', role: 'progressbar', tabindex: 0, 'aria-valuemin': 0, 'aria-valuemax': 100 }, sb.track, sb.ico, sb.tip);
  const show = () => { sbTip(true); };
  sb.box.addEventListener('mouseenter', show);
  sb.box.addEventListener('focus', show);
  sb.box.addEventListener('click', show);
  sb.box.addEventListener('mouseleave', () => sbTip(false));
  sb.box.addEventListener('blur', () => sbTip(false));
  sb.box.addEventListener('keydown', e => { if (e.key === 'Escape' && sb.tip.classList.contains('on')) { e.stopPropagation(); sbTip(false); } });
  sbEl.replaceChildren(sb.box);
  sb.built = true;
  if (typeof ResizeObserver === 'function') new ResizeObserver(() => sbFit(true)).observe(sb.box);
}
function sbTip(on) {
  clearTimeout(sb.tipT);
  if (!on) { sb.tip.classList.remove('on'); return; }
  sb.tip.classList.add('on');
  const bw = sb.box.clientWidth, cx = isFinite(sb.cx) ? sb.cx : parseFloat(sb.ico.style.left) || 0, tw = sb.tip.offsetWidth;
  sb.tip.style.left = Math.max(4, Math.min(bw - tw - 4, cx - tw / 2)) + 'px';
  sb.tipT = setTimeout(() => sb.tip.classList.remove('on'), 4000);
}
// the pill sits centred on the bar's position, clamped inside the bar; too wide → drop the words, then the % → icon only (never taller)
function sbFit(resized) {
  if (!sb.built || !sb.pos && sb.pos !== 0) return;
  const bw = sb.box.clientWidth;
  if (!bw) return;
  const p = sb.ico;
  // a new width puts the pill in place at once ('화려하게' glides it second by second; across a resize it would sweep past the edge)
  if (resized) p.style.transition = 'none';
  let mode = 'full';
  for (const m of ['full', 'short', 'icon']) {
    mode = m;
    p.dataset.mode = m;
    if (p.offsetWidth <= bw * (m === 'icon' ? 1 : 0.5)) break;
  }
  const w = p.offsetWidth;
  sb.cx = Math.max(w / 2, Math.min(bw - w / 2, sb.pos * bw));
  p.style.left = sb.cx.toFixed(1) + 'px';
}
function sbRender(n, ph, lvl) {
  if (!sbEl) return;
  if (!sb.built) sbBuild();
  const { start, mid, auc, end } = ph.seg, T = SB1 - SB0, t = n.min + n.s / 60;
  const pc = v => ((v - SB0) / T * 100).toFixed(2);
  const hol = ph.text === '휴장';
  const sig = [start, mid, auc, end].join();
  if (sig !== sb.sig) {
    sb.sig = sig;
    const parts = [[SB0, start, PH.pre, 'lo'], [start, mid, PH.am], [mid, auc, PH.pm], [auc, end, PH.auc], [end, SB1, PH.nxt, 'lo']];
    const rest = Math.round((parseFloat(tok('--sb-rest', '')) || 0.24) * 100);   // the not-yet-reached part: the hue at --sb-rest
    const mk = (alpha) => parts.map(([a, b, c, lo]) => h('i', { class: lo ? 'lo' : '', style: `left:${pc(a)}%;width:${(pc(b) - pc(a)).toFixed(2)}%;background:${alpha ? `color-mix(in srgb,${c} ${rest}%,transparent)` : c}` }));
    sb.segs.replaceChildren(...mk(true));
    sb.fillSegs = mk(false);
    sb.fill.replaceChildren(...sb.fillSegs);
    sb.box.dataset.title = `장 시작 전 08:00~${minLabel(start)} · 오전장 ~${minLabel(mid)} · 오후장 ~${minLabel(auc)} · 마감 동시호가 ~${minLabel(end)} · NXT ~20:00`;
  }
  const pos = Math.max(0, Math.min(1, (t - SB0) / T));
  const done = hol ? 0 : pos;
  const night = t < SB0 || t >= 18 * 60;
  const kind = night ? 'moon' : t < 12 * 60 ? 'rise' : 'sun';
  const smooth = lvl === 'fancy';
  sb.fill.style.transition = sb.ico.style.transition = smooth ? 'clip-path 1s linear, left 1s linear' : 'none';
  sb.fill.style.clipPath = `inset(0 ${(100 - done * 100).toFixed(2)}% 0 0)`;
  sb.pos = pos;
  const pp = sbPhase(n, ph);
  if (sb.kind !== kind) { sb.kind = kind; sb.cap.replaceChildren(sbIcon(kind)); }
  const dup = pp.icon === 'moon' && kind === 'moon', sigP = pp.id + (dup ? '+' : '');
  const textP = pp.label, pctP = pp.pct != null ? pp.pct + '%' : '';
  if (sb.phase !== sigP) {
    const first = sb.phase === undefined;
    sb.phase = sigP;
    if (dup) sb.pi.replaceChildren(); else sb.pi.replaceChildren(sbPhaseIcon(pp.icon));
    sb.ico.style.setProperty('--pc', pp.color);
    sb.ico.dataset.ph = pp.id;
    if (!first && lvl === 'fancy') { try { sb.ico.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: 360, easing: 'ease-out' }); } catch (e) { /* static is fine */ } }
  }
  if (sb.pt.textContent !== textP) sb.pt.textContent = textP;
  if (sb.pp.textContent !== pctP) sb.pp.textContent = pctP;
  sb.ico.classList.toggle('sb-fancy', lvl === 'fancy');
  sb.ico.classList.toggle('sb-live', lvl === 'fancy' && pp.id === 'reg');
  sb.ico.classList.toggle('sb-ring', lvl === 'fancy' && pp.id === 'auc');
  sbFit();
  sb.box.classList.toggle('sb-hol', hol);
  // tooltip text: the phase and what is left of it
  let tip = ph.text;
  if (!hol) {
    if (t >= start && t < end) tip = `${ph.key === 'auc' ? '마감 동시호가' : '정규장 ' + ph.pct + '%'} · ${minLabel(end)} 마감까지 ${fmtLeft(end - t)}`;
    else if (t >= 8 * 60 && t < start) tip = `장 시작 전 · ${minLabel(start)} 개장까지 ${fmtLeft(start - t)}`;
    else if (t >= end && t < SB1) tip = `장 마감 · NXT 20:00까지 ${fmtLeft(SB1 - t)}`;
  }
  if (sb.tip.textContent !== tip) { sb.tip.textContent = tip; }
  sb.box.setAttribute('aria-valuenow', Math.round(done * 100));
  sb.box.setAttribute('aria-valuetext', `${pp.label}${pp.pct != null ? ' ' + pp.pct + '%' : ''}, ${tip}`);
  sb.box.setAttribute('aria-label', '장 진행');
  sb.box.title = sb.box.dataset.title ? `${tip}\n${sb.box.dataset.title}` : tip;
}

// Where the bar goes depends on the layout, not on a breakpoint: when the tab row wrapped under the clock row, the bar sits
// between the two rows; when they share a row (desktop), it hangs under the header with a gap below the tabs.
function sbPlace() {
  const root = document.documentElement, hd = document.querySelector('header.top');
  if (!sbEl || !hd || sbEl.hidden || !root.classList.contains('has-clock')) { root.classList.remove('sb-mid'); return; }
  const tabs = hd.querySelector('.tabs'), brand = hd.querySelector('.brand');
  const mid = !!(tabs && brand && tabs.offsetParent && tabs.offsetTop >= brand.offsetTop + brand.offsetHeight - 2);
  root.classList.toggle('sb-mid', mid);
  if (!mid) { root.style.removeProperty('--sb-mt'); root.style.removeProperty('--sb-top'); return; }
  const cs = getComputedStyle(root), sbh = parseFloat(cs.getPropertyValue('--sbh')) || 6;
  const rowGap = parseFloat(getComputedStyle(hd).rowGap) || 0;
  const above = 5, below = 7;                                    // gaps; the 20px icon may reach into them but not onto the text
  root.style.setProperty('--sb-mt', Math.max(0, Math.round(above + sbh + below - rowGap)) + 'px');
  root.style.setProperty('--sb-top', (tabs.offsetTop - below) + 'px');
}
function ckSchedule() {
  clearTimeout(ck.timer);
  if (!ck.on || document.hidden) return;
  const lvl = motion();
  const now = nowMs();                                            // aligned to the corrected second (§3-17)
  // 줄이기 ticks once a minute, except while a countdown runs (its seconds are plain text, not motion)
  const per = lvl === 'reduced' && !ck.cdNow ? 60000 : 1000;
  ck.timer = setTimeout(() => { ckRender(); ckSchedule(); }, per - (((now % per) + per) % per) + 20);
}
async function ckClick() {
  if (ck.busy) return;
  ck.busy = true;
  ck.btn.setAttribute('aria-busy', 'true'); ck.btn.classList.add('xc-busy');
  const lvl = motion();
  if (lvl !== 'reduced') {
    ck.cells.forEach((c, i) => setTimeout(() => cellSet(c, c.cur, true), i * 60));
    if (ck.analog) { ck.analog._w.classList.remove('xa-do'); void ck.analog._w.getBoundingClientRect(); ck.analog._w.classList.add('xa-do'); }
  }
  const t0 = Date.now();
  let ok = false;
  try {
    if (LIVE) {                                              // the snapshot has nothing to refetch
      if (has('refresh')) ok = (await KH.refresh()) !== false;
      else { await pollStrip(); ok = !strip.failed; }
    }
  } catch (e) { ok = false; /* the next poll will try again */ }
  const left = 700 - (Date.now() - t0);
  if (left > 0) await new Promise(r => setTimeout(r, left));
  ck.busy = false;
  if (ck.btn) { ck.btn.removeAttribute('aria-busy'); ck.btn.classList.remove('xc-busy'); }
  ckRender();
  // the result under the clock (controls.md §5-3): ✓ new quotes, ! why not and what to do; the snapshot says what it is
  if (UI && ck.btn && ck.btn.isConnected) {
    if (!LIVE) UI.bubble(ck.btn, '미리보기는 고정된 시세예요');
    else if (ok) UI.bubble(ck.btn, '새 시세를 받았어요', 'done');
    else UI.bubble(ck.btn, '못 받았어요 · 다시 눌러 주세요', 'fail');
  }
}
/* a tap refreshes (KH.refresh); a long press (500 ms, no refresh), right-click, the context-menu key or Shift+F10 opens the world
   clock. No Android context menu, no text selection (CSS: user-select / touch-callout none on .xc-btn). */
const LONG_MS = 500;
function ckTap(e) {
  if (ck.lpFired) { ck.lpFired = false; e.preventDefault(); return; }     // the click that ends a long press
  if (wc.open) { wcClose(true); return; }                                 // the clock pressed again closes the world clock
  ckClick();
}
function ckPressHooks(btn) {
  let t = 0, x0 = 0, y0 = 0;
  const cancel = () => { clearTimeout(t); t = 0; };
  btn.addEventListener('pointerdown', e => {
    ck.lpFired = false;
    if (e.button !== 0) return;
    x0 = e.clientX; y0 = e.clientY;
    cancel();
    t = setTimeout(() => { t = 0; ck.lpFired = true; ck.ctxAt = performance.now(); wcOpen(); }, LONG_MS);
  });
  btn.addEventListener('pointermove', e => { if (t && Math.hypot(e.clientX - x0, e.clientY - y0) > 10) cancel(); });
  for (const ev of ['pointercancel', 'pointerleave']) btn.addEventListener(ev, cancel);
  // the finger lifts after a long press: the touch sequence may put focus back on the clock — the open dialog keeps it
  btn.addEventListener('pointerup', () => {
    cancel();
    if (!ck.lpFired) return;
    if (wc.open) setTimeout(() => { if (wc.open) wc.el.focus({ preventScroll: true }); }, 0);
    setTimeout(() => { ck.lpFired = false; }, 400);                       // no click came (touch): the next Enter still refreshes
  });
  btn.addEventListener('contextmenu', e => {
    e.preventDefault();                                                    // Android's long-press menu, the desktop menu
    cancel();
    if (performance.now() - (ck.ctxAt || 0) < 1000) return;                // already opened by the long press or the key
    if (e.pointerType === 'touch' || (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents)) ck.lpFired = true;
    if (wc.open) wcClose(true); else wcOpen();
  });
  btn.addEventListener('keydown', e => {
    if (e.key === 'Escape' && wc.open) { e.preventDefault(); wcClose(true); return; }
    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
      e.preventDefault();
      ck.ctxAt = performance.now();
      if (wc.open) wcClose(true); else wcOpen();
    }
  });
}

/* ── world clock (long press on the clock): 뉴욕 · 런던 · 도쿄 · 홍콩 · 상해 — local time (Intl, timeZone) from the corrected clock and
   whether that market is open, from /api/world?kind=index (the representative index's status, 네이버 증권; fetched on open, 30 s
   cache). Desktop: a popover under the clock; phones: a bottom sheet. Esc · outside tap · × close it, focus back on the clock.
   The snapshot shows the times and says the market state is in the live version. */
const WC = [
  { key: 'INX', city: '뉴욕', idx: 'S&P 500', tz: 'America/New_York' },
  { key: 'FTSE', city: '런던', idx: 'FTSE 100', tz: 'Europe/London' },
  { key: 'N225', city: '도쿄', idx: '니케이 225', tz: 'Asia/Tokyo' },
  { key: 'HSI', city: '홍콩', idx: '항셍', tz: 'Asia/Hong_Kong' },
  { key: 'SSEC', city: '상해', idx: '상해종합', tz: 'Asia/Shanghai' },
];
const wc = { open: false, el: null, rows: null, at: 0, okAt: 0, data: null, busy: false, err: false, sig: '' };
const wcFmt = new Map();
function wcParts(tz, ms) {
  let f = wcFmt.get(tz);
  if (!f) { try { f = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }); } catch (e) { return null; } wcFmt.set(tz, f); }
  const o = {}; for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { ymd: `${o.year}-${o.month}-${o.day}`, hm: `${o.hour === '24' ? '00' : o.hour}:${o.minute}` };
}
function wcBuild() {
  const title = h('h3', { id: 'xwc-h', class: 'xwc-h', text: '세계 시각' });
  const x = h('button', { type: 'button', class: 'xwc-x', 'aria-label': '닫기', onclick: () => wcClose(true) }, icon(ICON.close));
  wc.rows = WC.map(c => {
    const r = { c, t: h('span', { class: 'xwc-t' }), d: h('span', { class: 'xwc-d' }), st: h('span', { class: 'xwc-st' }) };
    r.el = h('li', { class: 'xwc-r', 'data-k': c.key },
      h('span', { class: 'xwc-c' }, h('b', { text: c.city }), h('small', { text: c.idx })),
      h('span', { class: 'xwc-tm' }, r.d, r.t), r.st);
    return r;
  });
  wc.note = h('p', { class: 'xwc-n' });
  wc.el = h('div', { id: 'xwc', class: 'xwc', role: 'dialog', 'aria-labelledby': 'xwc-h', tabindex: '-1', hidden: true },
    h('div', { class: 'xwc-hd' }, title, x), h('ul', { class: 'xwc-l' }, wc.rows.map(r => r.el)), wc.note);
  wc.el.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); wcClose(true); } });
  // Tab out closes it (focus moving back to the clock does not: the press that follows decides)
  wc.el.addEventListener('focusout', e => { const t = e.relatedTarget; if (t && !wc.el.contains(t) && t !== ck.btn) wcClose(false); });
  document.body.append(wc.el);
}
function wcOpen() {
  if (!ck.btn || !ck.btn.isConnected) return;
  if (!wc.el) wcBuild();
  wc.open = true; wc.sig = '';
  wc.el.hidden = false;
  wc.el.classList.toggle('xwc-sheet', narrowMQ.matches);
  ck.btn.dataset.world = '';
  wcRender();
  wcPlace();
  wc.el.focus({ preventScroll: true });
  const lvl = motion();
  if (lvl !== 'reduced') {
    try {
      const sheet = narrowMQ.matches;
      const k = lvl === 'fancy' ? (sheet ? [{ transform: 'translateY(100%)' }, { transform: 'none' }] : [{ opacity: 0, transform: 'translateY(8px) scale(.985)' }, { opacity: 1, transform: 'none' }])
        : [{ opacity: 0 }, { opacity: 1 }];
      wc.el.animate(k, { duration: lvl === 'fancy' ? (sheet ? 480 : 240) : 120, easing: 'cubic-bezier(.2,.7,.2,1)' });
    } catch (e) { /* static is fine */ }
  }
  if (LIVE && Date.now() - wc.at > 30000) wcFetch();
}
function wcPlace() {
  if (!wc.open) return;
  if (narrowMQ.matches) { wc.el.style.left = wc.el.style.top = ''; return; }
  const r = ck.btn.getBoundingClientRect(), pw = wc.el.offsetWidth, phh = wc.el.offsetHeight;
  let top = r.bottom + 8;
  if (top + phh > innerHeight - 8) top = Math.max(8, innerHeight - phh - 8);
  wc.el.style.left = Math.round(Math.min(Math.max(8, r.left), innerWidth - pw - 8)) + 'px';
  wc.el.style.top = Math.round(top) + 'px';
}
function wcClose(restore) {
  if (!wc.open) return;
  wc.open = false;
  wc.el.hidden = true;
  if (ck.btn) delete ck.btn.dataset.world;
  if (restore && ck.btn && ck.btn.isConnected) ck.btn.focus({ preventScroll: true });
}
async function wcFetch() {
  if (wc.busy) return;
  wc.busy = true; wc.err = false; wc.sig = '';
  if (wc.open) wcRender();
  try {
    const j = await getJSON('api/world?kind=index', 8000);
    const m = new Map();
    for (const g of (j && j.groups) || []) for (const it of g.items || []) if (it && it.key) m.set(it.key, it.status === 'OPEN' ? 'OPEN' : 'CLOSE');
    wc.data = m; wc.at = Date.now(); wc.okAt = nowMs();
  } catch (e) { wc.err = true; wc.at = Date.now() - 20000; }        // try again in 10 s, while it is open
  wc.busy = false; wc.sig = '';
  if (wc.open) wcRender();
}
function wcRender() {
  if (!wc.el || !wc.open) return;
  if (LIVE && !wc.busy && Date.now() - wc.at > 30000) { wcFetch(); return; }
  const ms = nowMs(), seoul = kstNow().date;
  const sig = [Math.floor(ms / 60000), wc.busy, wc.err, wc.at].join();
  if (sig === wc.sig) return;
  wc.sig = sig;
  for (const r of wc.rows) {
    const p = wcParts(r.c.tz, ms);
    r.t.textContent = p ? p.hm : '—';
    r.d.textContent = !p || p.ymd === seoul ? '' : p.ymd < seoul ? '어제' : '내일';
    const s = LIVE && wc.data ? wc.data.get(r.c.key) : null;
    r.el.dataset.st = s ? s.toLowerCase() : '';
    r.st.textContent = !LIVE ? '' : s === 'OPEN' ? '장중' : s === 'CLOSE' ? '마감' : wc.busy ? '확인 중' : '—';
  }
  if (!LIVE) {
    if (!wc.note.childNodes.length) {
      const a = typeof KH.LIVE_URL === 'string' ? KH.LIVE_URL : null;
      wc.note.append('장중·마감은 실시간 버전에서 볼 수 있어요.', ...(a ? [' ', h('a', { href: a, target: '_blank', rel: 'noopener', text: '실시간 버전 열기' })] : []));
    }
  } else if (wc.err && !wc.data) wc.note.textContent = '장중·마감을 불러오지 못했어요. 잠시 뒤 다시 확인할게요.';
  else wc.note.textContent = `장중·마감은 네이버 증권 기준이에요${wc.okAt ? ` · ${fmtHM.format(new Date(wc.okAt))} 확인` : ''}.`;
}
// outside press closes it; once the press is over, focus goes back to the clock unless what was pressed took it (a key, a tile)
document.addEventListener('pointerdown', e => {
  if (!wc.open || wc.el.contains(e.target) || (ck.btn && ck.btn.contains(e.target))) return;
  wcClose(false);
  addEventListener('pointerup', () => setTimeout(() => {
    const a = document.activeElement;
    if ((!a || a === document.body || a === wc.el) && ck.btn && ck.btn.isConnected) ck.btn.focus({ preventScroll: true });
  }, 60), { once: true, capture: true });
}, true);
addEventListener('resize', () => { if (!wc.open) return; wc.el.classList.toggle('xwc-sheet', narrowMQ.matches); wcPlace(); });
addEventListener('scroll', () => { if (wc.open) wcPlace(); }, { passive: true });

function ckApply() {
  if (!clockEl) return;
  const on = getSet('clock', true) !== false && getSet('clock', true) !== 'false';
  ck.on = on;
  wcClose(false);
  document.documentElement.classList.toggle('has-clock', on);
  clockEl.hidden = !on;
  if (sbEl) sbEl.hidden = !on;
  requestAnimationFrame(sbPlace);
  clearTimeout(ck.timer); cancelAnimationFrame(ck.raf);
  if (!on) { clockEl.replaceChildren(); return; }
  ck.sig = '';
  ckBuild();
  ckRender();
  ckSchedule();
  ckSweep();
}
function initClock() {
  if (!clockEl) return;
  initTickerSetting();
  if (has('addSetting')) {
    try {
      KH.addSetting({ key: 'clock', label: '시계·장 진행률', hint: '서버 시각으로 맞춘 한국 시각(KST)이에요. 시계를 누르면 새로고침해요.', default: true, onChange: () => ckApply() });
      KH.addSetting({ key: 'clockStyle', label: '시계 모양', options: [{ v: 'digital', label: '숫자' }, { v: 'analog', label: '아날로그' }, { v: 'both', label: '둘 다' }], default: 'both', onChange: () => ckApply() });
    } catch (e) { /* settings are optional */ }
  }
  ckApply();
  timeSync(true);
  setInterval(() => { if (!document.hidden) timeSync(false); }, 10 * 60 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearTimeout(ck.timer); cancelAnimationFrame(ck.raf); return; }
    timeSync(false);
    ckRender(); ckSchedule(); ckSweep();
  });
  document.addEventListener('kh:motion', () => { ckRender(); ckSchedule(); ckSweep(); });
  const hd = document.querySelector('header.top');
  if (hd && window.ResizeObserver) new ResizeObserver(() => sbPlace()).observe(hd);
  addEventListener('resize', sbPlace);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(sbPlace);
  matchMedia('(max-width: 760px)').addEventListener('change', () => ckApply());
  document.addEventListener('kh:refresh', () => { if (LIVE) pollStrip(); });
}

/* ═════════════ boot ═════════════ */
function initTools() {
  if (!toolsEl) return;
  if (!UI) toast('');                                      // no KH.ui (older template): the toast region, made up front so the first message is announced
  toolsEl.classList.add('xt');
  if (has('layout')) toolsEl.append(imageKey());
  if (LIVE && has('setReplay')) {
    const rb = toolButton('replay', '리플레이', openReplay, { 'aria-expanded': 'false' });
    toolsEl.append(rb);
    // replay only makes sense on the domestic maps: dim it on the 해외 / 원자재 tabs
    const sync = () => {
      const off = isWorldTab();
      if (off) { if (replay.open) closeReplay(); rb.setAttribute('aria-disabled', 'true'); rb.title = '국내 지도 탭에서 쓸 수 있어요'; }
      else { rb.removeAttribute('aria-disabled'); rb.title = '리플레이'; }
    };
    document.addEventListener('kh:render', sync);
    addEventListener('hashchange', sync);
    document.addEventListener('click', e => { if (e.target.closest && e.target.closest('.tabs')) setTimeout(sync, 0); });
    sync();
  }
}
initStrip();
initClock();
initTools();
initPWA();
document.addEventListener('keydown', rpKeys);
document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
addEventListener('resize', () => { if (replay.big && replay.big.classList.contains('on')) bigUpdate(); });
document.addEventListener('kh:motion', () => bigUpdate());
// a theme change (docs/standards/themes.md): the session bar's hues, the browser's top colour; everything else follows the CSS tokens
document.addEventListener('kh:theme', () => {
  phRead();
  const m = document.querySelector('meta[name="theme-color"]'), c = tok('--page', '');
  if (m && c) m.setAttribute('content', c);
  sb.sig = ''; sb.phase = undefined;                       // the segments and the pill's --pc are drawn again with the new hues
  if (ck.on) ckRender();
});
// Space on a focused button would also "click" it on keyup: swallow that when the player took the keydown
document.addEventListener('keyup', e => { if (spaceTaken && (e.key === ' ' || e.code === 'Space')) { e.preventDefault(); spaceTaken = false; } });
})();
