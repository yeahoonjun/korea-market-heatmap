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
};
const icon = (d, fill) => svg('svg', { viewBox: '0 0 20 20', width: '18', height: '18', 'aria-hidden': 'true', fill: fill ? 'currentColor' : 'none',
  stroke: fill ? 'none' : 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg('path', { d }));

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
  const def = STRIP[it.key] || { label: it.name || it.key, dp: 2 };
  const v = +it.value, c = +it.change, r = +it.ratio;
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
  return h('div', { class: 'xs-item', role: 'listitem', 'data-k': it.key, title: desc, 'aria-label': desc }, kids);
}

/* ── ticker: [viewport (mask) > track > N copies of the item list] + fixed tail + pause button ── */
const tk = { sig: '', list: null, track: null, vp: null, tail: null, ro: null, W: 0, dur: 0 };
let tkPaused = false;
try { tkPaused = localStorage.getItem('khm.tickerPaused') === '1'; } catch (e) { /* storage blocked */ }
const tkOn = () => stripEl.classList.contains('xs-tk');

function stripTail() {
  if (LIVE) {
    const at = strip.asOf ? new Date(strip.asOf) : null;
    const t = at && !isNaN(at) ? fmtHM.format(at) : '';
    return h('span', { class: 'xs-t' + (strip.failed ? ' xs-stale' : ''), title: strip.failed ? '최근 갱신에 실패해서 마지막으로 받은 값이에요' : '30초마다 갱신해요' },
      h('span', { text: strip.failed ? '갱신 실패' : '네이버 증권' }), h('span', { text: `${t} 기준` }));
  }
  if (KH.LIVE_URL) return h('a', { class: 'xs-live', href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '환율·미국 선물은 실시간 버전에서 볼 수 있어요' });
  return null;
}
function tkCopy() {
  const c = tk.list.cloneNode(true);
  c.removeAttribute('role'); c.removeAttribute('aria-label');
  c.setAttribute('aria-hidden', 'true'); c.setAttribute('inert', ''); c.inert = true;
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
function tkButton() {
  const btn = h('button', { type: 'button', class: 'xs-pp', 'aria-pressed': String(tkPaused) });
  const draw = () => {
    btn.setAttribute('aria-pressed', String(tkPaused));
    const l = tkPaused ? '시장 띠 다시 움직이기' : '시장 띠 멈추기';
    btn.setAttribute('aria-label', l); btn.title = l;
    btn.replaceChildren(icon(tkPaused ? ICON.play : ICON.pause, true));
    stripEl.classList.toggle('xs-off', tkPaused);
  };
  btn.addEventListener('click', () => {
    tkPaused = !tkPaused;
    try { localStorage.setItem('khm.tickerPaused', tkPaused ? '1' : '0'); } catch (e) { /* ignore */ }
    draw();
  });
  draw();
  return btn;
}
function buildTicker(kids) {
  tk.list = h('div', { class: 'xs-list', role: 'list', 'aria-label': '시장 지표' }, kids);
  tk.track = h('div', { class: 'xs-track' }, tk.list);
  tk.vp = h('div', { class: 'xs-vp' }, tk.track);
  tk.tail = stripTail();
  tk.W = 0;
  const hold = on => () => stripEl.classList.toggle('xs-hold', on);
  tk.vp.addEventListener('pointerdown', hold(true));
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) tk.vp.addEventListener(ev, hold(false));
  stripEl.classList.add('xs-tk'); stripEl.classList.remove('xs-hold', 'xs-scroll', 'xs-end');
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
  const t = stripTail();
  if (tk.tail && t) { tk.tail.replaceWith(t); tk.tail = t; }
  tkSize(false);
}

function renderStrip() {
  if (!stripEl) return;
  const items = strip.items;
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
    const list = h('div', { class: 'xs-list', role: 'list', 'aria-label': '시장 지표' }, kids);
    const tail = stripTail();
    stripEl.hidden = false;
    stripEl.replaceChildren(list, ...(tail ? [tail] : []));
  }
  // the header's own 코스피/코스닥 readout (#idx) duplicates the strip
  document.documentElement.classList.toggle('xs-on', items.some(it => it.key === 'KOSPI' || it.key === 'KOSDAQ'));
  stripOverflow();
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
  } catch (e) {
    strip.failed = true;
  }
  strip.busy = false;
  strip.at = Date.now();
  renderStrip();
  strip.timer = setTimeout(pollStrip, 30000);
}

function initStrip() {
  if (!stripEl) return;
  stripEl.classList.add('xs');
  if (LIVE) {
    renderStrip();
    pollStrip();
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
  return h('button', Object.assign({ type: 'button', class: 'xt-btn', 'data-x': key, title: label, onclick: onClick }, extra || {}), icon(ICON[key]), h('span', { text: label }));
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
    return { m, title: m === 'world' ? '해외 지수' : '원자재', when: fmtHM.format(d) + ' 기준' };
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

function drawMap(nodes) {
  const pal = has('palette') ? KH.palette() : {};
  const upC = pal.upText || '#ff5c66', dnC = pal.dnText || '#2fd67a';
  const fam = getComputedStyle(document.body).fontFamily || 'sans-serif';
  const minX = Math.min(...nodes.map(n => n.x)), minY = Math.min(...nodes.map(n => n.y));
  const N = nodes.map(n => Object.assign({}, n, { x: n.x - minX, y: n.y - minY }));
  const W = Math.ceil(Math.max(...N.map(n => n.x + n.w))), MH = Math.ceil(Math.max(...N.map(n => n.y + n.h)));
  const pad = W < 520 ? 10 : 14;
  const cnv = document.createElement('canvas');
  const ctx = cnv.getContext('2d');
  // header: title + time on the left, source on the right; wraps to two lines on narrow maps
  const { title, when } = titleParts();
  const src = '출처: 네이버 증권';
  const tSize = W < 520 ? 14 : 16, mSize = W < 520 ? 11.5 : 12.5;
  ctx.font = `700 ${tSize}px ${fam}`; const tW = ctx.measureText(title).width;
  ctx.font = `500 ${mSize}px ${fam}`; const wW = ctx.measureText(when).width, sW = ctx.measureText(src).width;
  const oneLine = pad + tW + 12 + wW + 24 + sW + pad <= W;
  const TH = oneLine ? Math.round(tSize * 2.6) : Math.round(tSize * 1.9 + mSize * 1.9);
  const H = TH + MH;
  let s = Math.min(3, Math.max(2, window.devicePixelRatio || 1));
  while (W * H * s * s > 16e6 && s > 1) s -= 0.25;                     // stay under the iOS canvas area limit
  cnv.width = Math.round(W * s); cnv.height = Math.round(H * s);
  ctx.scale(s, s);
  ctx.fillStyle = '#131418'; ctx.fillRect(0, 0, W, TH);
  ctx.fillStyle = '#000'; ctx.fillRect(0, TH, W, MH);
  ctx.textBaseline = 'middle';
  if (oneLine) {
    const cy = TH / 2;
    ctx.textAlign = 'left';
    ctx.font = `700 ${tSize}px ${fam}`; ctx.fillStyle = '#eef0f3'; ctx.fillText(title, pad, cy);
    ctx.font = `500 ${mSize}px ${fam}`; ctx.fillStyle = '#bcc0c8'; ctx.fillText(when, pad + tW + 12, cy);
    ctx.textAlign = 'right'; ctx.fillStyle = '#8a8f99'; ctx.fillText(src, W - pad, cy);
  } else {
    const y1 = tSize * 1.15, y2 = tSize * 1.9 + mSize * 0.75;
    ctx.textAlign = 'left';
    ctx.font = `700 ${tSize}px ${fam}`; ctx.fillStyle = '#eef0f3'; ctx.fillText(ellipsize(ctx, title, W - 2 * pad), pad, y1);
    ctx.font = `500 ${mSize}px ${fam}`; ctx.fillStyle = '#bcc0c8'; ctx.fillText(ellipsize(ctx, when, W - 2 * pad - sW - 16), pad, y2);
    ctx.textAlign = 'right'; ctx.fillStyle = '#8a8f99'; ctx.fillText(src, W - pad, y2);
  }
  ctx.translate(0, TH);
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
  for (const n of tiles) { ctx.fillStyle = n.color || '#383c46'; ctx.fillRect(n.x, n.y, n.w, n.h); }
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
      ctx.fillStyle = d > 0 ? upC : d < 0 ? dnC : '#8a8f99';
      ctx.fillText(sub, g.x + 5 + textW + 6, cy);
    }
    ctx.restore();
  };
  for (const g of inds) header(g, hdOf(g, tiles), 10.5, 500, '#0d0e11', '#a6abb5');
  for (const g of secs) header(g, hdOf(g, inds.length ? inds : tiles), 12, 700, '#000', '#f2f3f5');
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
    ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = 2 * s; ctx.shadowOffsetY = 1 * s;
    ctx.fillStyle = '#fff';
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
  return cnv;
}

let saving = false;
async function saveImage(ev) {
  if (saving) return;
  const btn = ev && ev.currentTarget;
  let nodes = [];
  const wt = isWorldTab();
  try { nodes = ((wt ? (window.KHWorld && typeof window.KHWorld.layout === 'function' ? window.KHWorld.layout() : []) : KH.layout()) || []).filter(n => n && isFinite(n.x) && isFinite(n.y) && n.w > 0 && n.h > 0); } catch (e) { nodes = []; }
  if (!nodes.some(n => n.kind === 'tile')) { toast(wt ? '지도 탭에서만 저장할 수 있어요' : '저장할 지도가 없어요. 지도 보기에서 다시 눌러 주세요.'); return; }
  saving = true;
  if (btn) btn.setAttribute('aria-busy', 'true');
  try {
    const fam = getComputedStyle(document.body).fontFamily;
    if (document.fonts && document.fonts.load) {
      await Promise.race([Promise.all([document.fonts.load(`700 16px ${fam}`, '가A1'), document.fonts.load(`500 12px ${fam}`, '가A1')]), new Promise(r => setTimeout(r, 1500))]).catch(() => {});
    }
    const cnv = drawMap(nodes);
    const name = fileName(titleParts().m);
    if (LIVE) {
      const blob = await new Promise(res => cnv.toBlob(res, 'image/png'));
      if (!blob) throw new Error('toBlob');
      const url = URL.createObjectURL(blob);
      const a = h('a', { href: url, download: name, hidden: true });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      toast('지도를 이미지로 저장했어요.');
    } else {
      showImageDialog(cnv.toDataURL('image/png'), name, cnv.width, cnv.height, btn);
    }
  } catch (e) {
    toast('이미지를 만들지 못했어요. 잠시 뒤 다시 시도해 주세요.');
  } finally {
    saving = false;
    if (btn) btn.removeAttribute('aria-busy');
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
  headTag('meta', { name: 'theme-color', content: '#131418' });
  headTag('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' });
  headTag('meta', { name: 'mobile-web-app-capable', content: 'yes' });
  headTag('meta', { name: 'apple-mobile-web-app-title', content: '증시 히트맵' });
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
const SESSION = { s0: 9 * 60, s1: 15 * 60 + 30, slots: 78 };
const slotOfT = t => { const m = hmMin(t); return isFinite(m) ? Math.round((m - SESSION.s0) / 5) : 0; };
function setSession(frames) {
  const mins = frames.map(f => hmMin(f.t)).filter(isFinite);
  const first = mins.length ? Math.min(...mins) : 9 * 60, last = mins.length ? Math.max(...mins) : 15 * 60 + 30;
  const late = first >= 10 * 60;
  const s0 = Math.min(late ? 10 * 60 : 9 * 60, Math.floor(first / 5) * 5);
  const s1 = Math.max(late ? 16 * 60 + 30 : 15 * 60 + 30, Math.ceil(last / 5) * 5);
  Object.assign(SESSION, { s0, s1, slots: (s1 - s0) / 5 });
}
const replay = { open: false, el: null, btn: null, dates: null, date: null, day: null, cache: new Map(), i: -1, playing: false, speed: 1, timer: 0, req: 0, frameT: null, raf: 0 };
function rpTicks() {
  const ui = replay.ui, { s0, s1, slots } = SESSION;
  const marks = [s0];
  for (let m = Math.ceil((s0 + 1) / 60) * 60; m < s1; m += 60) marks.push(m);
  if (s1 - marks[marks.length - 1] < 40) marks.pop();          // the last hour mark would crowd the closing time
  marks.push(s1);
  ui.ticks.replaceChildren(...marks.map((m, k) => h('span', { class: k % 2 && k < marks.length - 1 ? 'o' : null, style: `left:${((m - s0) / 5 / slots) * 100}%`, text: minLabel(m) })));
  ui.slider.max = slots;
}
function rpSetH() {
  const R = replay;
  const px = R.open && R.el && !R.el.hidden ? Math.round(R.el.offsetHeight + (parseFloat(getComputedStyle(R.el).bottom) || 0)) : 0;
  document.documentElement.style.setProperty('--rp-h', px + 'px');
}

function rpBuild() {
  const R = replay;
  const ui = R.ui = {};
  ui.play = h('button', { type: 'button', class: 'rp-play', 'aria-label': '재생', onclick: () => togglePlay() }, icon(ICON.play, true));
  ui.time = h('div', { class: 'rp-time', 'aria-live': 'off', text: '--:--' });
  ui.day = h('div', { class: 'rp-day', text: '' });
  ui.idx = h('div', { class: 'rp-idx' });
  ui.date = h('select', { class: 'rp-date', 'aria-label': '날짜', onchange: e => loadDay(e.target.value, false) });
  ui.speed = h('div', { class: 'rp-speed', role: 'group', 'aria-label': '재생 속도' }, [1, 2, 4].map(v =>
    h('button', { type: 'button', 'data-v': v, 'aria-pressed': String(v === R.speed), text: `${v}×`, 'aria-label': `${v}배속`, onclick: () => setSpeed(v) })));
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
  rpTicks();
  new ResizeObserver(rpSetH).observe(R.el);
  addEventListener('resize', rpSetH);
}
function rpState(kind, text, retry) {
  const ui = replay.ui;
  ui.body.hidden = kind !== 'ready';
  ui.msg.hidden = kind === 'ready';
  ui.msg.replaceChildren(ui.label(), h('p', { text }));
  if (retry) ui.msg.append(h('button', { type: 'button', class: 'rp-retry', onclick: retry, text: '다시 시도' }));
  ui.note.textContent = kind === 'ready' ? `5분마다 기록한 시세예요. 정규장(${minLabel(SESSION.s0)}~${minLabel(SESSION.s1)}) 기준 · 네이버 증권` : kind === 'empty' ? '5분마다 기록한 시세예요. 네이버 증권' : '';
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
  } catch (e) {
    if (!R.open) return;
    rpState('error', '기록된 날짜를 불러오지 못했어요. 네트워크를 확인하고 다시 시도해 주세요.', loadDates);
    return;
  }
  if (!R.open) return;
  if (!R.dates.length) { rpState('empty', '아직 기록된 날이 없어요. 다음 거래일 09:00부터 5분마다 기록돼서, 장이 열린 뒤에 다시 볼 수 있어요.'); return; }
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
      day = { date: j.date || date, codes: j.codes.map(String), frames: j.frames.filter(f => f && f.t != null && Array.isArray(f.p) && Array.isArray(f.r)), index: j.index || {}, base: j.base || j.prev || null };
      day.frames.sort((a, b) => hmMin(a.t) - hmMin(b.t));
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
  if (!day.frames.length) { fail(`${dayLabel(date)}에는 아직 기록된 장면이 없어요. 장이 열리면 5분마다 쌓여요.`); return; }
  R.date = date; R.day = day;
  setSession(day.frames);
  rpTicks();
  rpState('ready');
  const first = slotOfT(day.frames[0].t), last = slotOfT(day.frames[day.frames.length - 1].t);
  R.ui.slider.style.setProperty('--rec0', (first / SESSION.slots * 100) + '%');
  R.ui.slider.style.setProperty('--rec1', (last / SESSION.slots * 100) + '%');
  showFrame(0);
}
function indexBase(day, key) {
  if (day.base && isFinite(+day.base[key])) return +day.base[key];
  // today's previous close is known from the strip (value − change)
  const it = strip.items && strip.items.find(x => x.key === key);
  if (it && it.spark && it.spark.length && isFinite(+it.change) && kstYmd(new Date(it.spark[0][0] * 1000)) === day.date) return +it.value - +it.change;
  return NaN;
}
function showFrame(i) {
  const R = replay, day = R.day;
  if (!day) return;
  i = Math.max(0, Math.min(day.frames.length - 1, i));
  R.i = i;
  const f = day.frames[i];
  R.frameT = hhmm(f.t);
  const prices = new Map();
  for (let j = 0; j < day.codes.length; j++) {
    const p = f.p[j], r = f.r[j];
    if (p == null || r == null || !isFinite(p) || !isFinite(r)) continue;
    prices.set(day.codes[j], { p: +p, r: +r });
  }
  R.prices = prices;
  cancelAnimationFrame(R.raf);
  R.raf = requestAnimationFrame(() => { try { KH.setReplay({ t: String(f.t), date: day.date, prices }); } catch (e) { /* map keeps its last frame */ } });
  const ui = R.ui, sl = slotOfT(f.t);
  ui.time.textContent = R.frameT;
  ui.slider.value = sl;
  ui.slider.setAttribute('aria-valuetext', `${dayLabel(day.date)} ${R.frameT}`);
  ui.slider.style.setProperty('--pos', (sl / SESSION.slots * 100) + '%');
  ui.idx.replaceChildren(...['KOSPI', 'KOSDAQ'].map(k => {
    const arr = day.index[k];
    const v = Array.isArray(arr) ? +(Array.isArray(arr[i]) ? arr[i][0] : arr[i] && typeof arr[i] === 'object' ? arr[i].value : arr[i]) : NaN;
    const label = k === 'KOSPI' ? '코스피' : '코스닥';
    if (!isFinite(v) || arr[i] == null) return h('div', { class: 'rp-ix' }, h('span', { class: 'rp-k', text: label }), h('span', { class: 'rp-v', text: '—' }));
    const base = indexBase(day, k);
    const kids = [h('span', { class: 'rp-k', text: label }), h('span', { class: 'rp-v', text: fixed(v, 2) })];
    if (isFinite(base) && base) kids.push(h('span', { class: 'rp-r ' + dir(v - base), text: pct((v / base - 1) * 100) }));
    return h('div', { class: 'rp-ix' }, kids);
  }));
  const lastT = hhmm(day.frames[day.frames.length - 1].t);
  ui.day.textContent = `${i + 1}/${day.frames.length}장면${hmMin(lastT) < SESSION.s1 ? ` · ${lastT}까지 기록` : ''}`;
}
function seekSlot(sl) {
  const day = replay.day;
  if (!day) return;
  let best = 0;
  for (let i = 0; i < day.frames.length; i++) if (slotOfT(day.frames[i].t) <= sl) best = i;
  showFrame(best);
}
function step(d) { pause(); showFrame(replay.i + d); }
function setPlayIcon() {
  const ui = replay.ui;
  ui.play.replaceChildren(icon(replay.playing ? ICON.pause : ICON.play, true));
  ui.play.setAttribute('aria-label', replay.playing ? '멈춤' : '재생');
}
function tick() {
  const R = replay;
  if (!R.playing || !R.day) return;
  if (R.i >= R.day.frames.length - 1) { pause(); return; }
  showFrame(R.i + 1);
  R.timer = setTimeout(tick, 1000 / R.speed);
}
function play() {
  const R = replay;
  if (!R.day || R.playing) return;
  if (R.i >= R.day.frames.length - 1) showFrame(0);
  R.playing = true; setPlayIcon();
  R.timer = setTimeout(tick, 1000 / R.speed);
}
function pause() {
  const R = replay;
  clearTimeout(R.timer);
  if (!R.playing) return;
  R.playing = false;
  if (R.ui) setPlayIcon();
}
function togglePlay() { replay.playing ? pause() : play(); }
function setSpeed(v) {
  const R = replay;
  R.speed = v;
  for (const b of R.ui.speed.children) b.setAttribute('aria-pressed', String(+b.dataset.v === v));
  if (R.playing) { clearTimeout(R.timer); R.timer = setTimeout(tick, 1000 / v); }
}
function closeReplay() {
  const R = replay;
  if (!R.open) return;
  pause();
  R.open = false; R.frameT = null; R.prices = null; R.req++;
  cancelAnimationFrame(R.raf);
  try { KH.setReplay(null); } catch (e) { /* nothing to undo */ }
  R.el.hidden = true;
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

/* ═════════════ boot ═════════════ */
function initTools() {
  if (!toolsEl) return;
  toast('');                                               // create the live region up front so the first message is announced
  toolsEl.classList.add('xt');
  if (has('layout')) toolsEl.append(toolButton('image', '이미지로 저장', saveImage));
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
initTools();
initPWA();
document.addEventListener('keydown', rpKeys);
// Space on a focused button would also "click" it on keyup: swallow that when the player took the keydown
document.addEventListener('keyup', e => { if (spaceTaken && (e.key === ' ' || e.code === 'Space')) { e.preventDefault(); spaceTaken = false; } });
})();
