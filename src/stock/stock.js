/* 종목 페이지: 히트맵 위에 뜨는 전체 화면 페이지. 계약은 AGENTS.md §3 (window.KHStock).
 *
 * 차트: TradingView Lightweight Charts™ v5.2.1 — Copyright (c) 2026 TradingView, Inc. — Apache License 2.0
 *       https://www.tradingview.com/  (실시간 모드에서 처음 열 때 jsDelivr에서 불러와요.
 *       라이선스가 요구하는 출처 표시는 차트의 TradingView 로고와 하단 링크로 해요.)
 */
(() => {
'use strict';
const KH = window.KH;
if (!KH || window.KHStock) return;

/* ───────────────── config ───────────────── */
const LIVE = KH.MODE === 'live';
const LWC_VERSION = '5.2.1';
const LWC_SRC = `https://cdn.jsdelivr.net/npm/lightweight-charts@${LWC_VERSION}/dist/lightweight-charts.standalone.production.js`;
const LWC_SRI = 'sha384-KkYqTZlM13Zya6fVUF3IGCBOQ1ehFeJVVgxaVvD/0MebineF9EI8Jkd3NnWNChqN';
const CODE_RE = /^[0-9A-Z]{6}$/;
const HASH_RE = /^#s-([0-9A-Z]{6})$/;
/* The chart's tabs are bar intervals (사용자 2026-11-13 22:38). 분 is one tab with a picker of minute intervals (사용자 2026-11-14 08:10
 * "1분봉 5분봉 있는게 아니라 분봉으로 통합하고 누르면 1분봉 5분봉 10분봉 30분봉 60분봉 선택 가능하게"): tabs 분 · 일 · 주 · 월 · 년.
 * `tf` below is one interval key (1m … 60m, day, week, month, year); the choice is remembered in khm.stock.iv (old '1m' / '5m' stay valid). */
const MINS = [['1m', '1분'], ['5m', '5분'], ['10m', '10분'], ['30m', '30분'], ['60m', '60분']];
const TFS = [...MINS, ['day', '일'], ['week', '주'], ['month', '월'], ['year', '년']];
const TF_TABS = [['min', '분'], ['day', '일'], ['week', '주'], ['month', '월'], ['year', '년']];
const TF_NAME = Object.fromEntries(TFS);
const MIN_TF = new Set(MINS.map(x => x[0]));
const isMin = tf => MIN_TF.has(tf);
const IV_UNIT = { '1m': '분', '5m': '분', '10m': '분', '30m': '분', '60m': '분', day: '일', week: '주', month: '월', year: '년' };   // what "5" means in 5-bar average
const IV_BARS = { '1m': '1분봉', '5m': '5분봉', '10m': '10분봉', '30m': '30분봉', '60m': '60분봉', day: '일봉', week: '주봉', month: '월봉', year: '연봉' };
// the tf= form (a Worker without iv=); 10분 · 30분 · 60분 group its 5-minute bars here
const IV_OLD = { '1m': '1d', '5m': '5d', '10m': '5d', '30m': '5d', '60m': '5d', day: '1y', week: '3y', month: '10y', year: '10y' };
const IV_REQ = { '1m': ['1m', 900], '5m': ['5m', 800], '10m': ['10m', 400], '30m': ['30m', 140], '60m': ['60m', 70],
  day: ['day', 250], week: ['week', 260], month: ['month', 240], year: ['month', 480] };   // iv, bars asked for
const IV_GROUP = { '10m': 10, '30m': 30, '60m': 60 };   // minutes per bar the Worker groups from 5-minute bars (groupBars)
const IV_RANGE = { '1m': '오늘', '5m': '5일', '10m': '3일', '30m': '5일', '60m': '5일', day: '6개월', week: '3년', month: '10년', year: '전체 기간' };   // the default visible window
const IV_DAYS = { '1m': 1, '5m': 5, '10m': 3, '30m': 5, '60m': 5 };   // trading days in that window (minute intervals)
const IV_MONTHS = { day: 6, week: 36, month: 120 };
const MA_N = [5, 20, 60, 120];
const MA_DEF = { '1m': [5, 20, 60], '5m': [5, 20, 60], '10m': [5, 20, 60], '30m': [5, 20, 60], '60m': [5, 20],
  day: [5, 20, 60, 120], week: [5, 20, 60, 120], month: [5, 20, 60, 120], year: [5, 20] };
const WARM = 119;   // bars before the window, so the 120-bar average is complete at the first visible bar
/* Tabs beside/under the chart. To add one (e.g. 뉴스·공시) add an entry here; nothing else has to change.
 *   key, label    id suffix (#sp-t-<key>, #sp-p-<key>) and the visible name
 *   build(panel)  once, when the page is first built                                  (optional)
 *   show(panel)   whenever the tab becomes visible (also when the browser tab comes back): load or render
 *   hide()        when another tab is picked, the document is hidden or the page closes: stop timers (optional)
 *   reset()       when the page switches to another stock: drop that stock's data       (optional)
 *   summary(phaseChanged)  after /summary refreshes (current price, market phase)       (optional)
 * Fetch through api(path, key) with a key of the tab's own, so switching and closing abort it. */
const TABS = [
  { key: 'ob', label: '호가', build: buildOb, show: () => { renderOb(); obStart(); }, hide: obStop, reset: obReset, summary: obSummary },
  { key: 'info', label: '종목 정보', build: buildInfo, show: infoShow, reset: infoReset, summary: infoSummary },
  { key: 'inv', label: '투자자', show: () => { loadEst(false); return S.inv || S.invLoading ? renderInv() : loadInv(); }, reset: invReset },
  { key: 'daily', label: '일별 시세', show: () => (S.daily ? renderDaily() : loadDaily(1)), reset: dailyReset, summary: renderDailyNote },
  { key: 'news', label: '뉴스·공시', build: buildNews, show: newsShow, reset: newsReset },
];
const TAB = Object.fromEntries(TABS.map(t => [t.key, t]));
const OB_MS = 3000, SUMMARY_MS = 30000, INTRADAY_MS = 60000;
const KST = 9 * 3600;
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const MINUS = '−';
const PHASE = {
  open: { chip: '실시간', live: true },
  after: { chip: '시간외', live: true, note: '정규장이 끝나 NXT·시간외 거래 중이에요' },
  pre: { chip: '장 시작 전', live: true },
  closed: { chip: '장 마감' },
  weekend: { chip: '주말 휴장', note: '주말이라 장이 열리지 않아요. 마지막 거래일 시세예요' },
  holiday: { chip: '휴장', note: '오늘은 장이 열리지 않아요. 마지막 거래일 시세예요' },
  unknown: { chip: '' },
};
const POLL_PHASES = new Set(['open', 'after', 'pre', 'unknown']);
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
/* Effect levels (AGENTS.md §3-5, design.md §6-3): 줄이기 = end states only · 기본 = press, indicator moves, text swaps, open / close ·
 * 화려하게 = + digit rolls, the 호가 ring, the tab fade. A heatmap without KH.motion counts as 'standard'. Every length and curve is a spring
 * token of the template's :root (--sp-<name>, --sp-<name>-dur — spring() below) or a --c-* press token; none is written here. */
const motion = () => { try { const m = KH.motion && KH.motion(); return m === 'fancy' || m === 'reduced' ? m : 'standard'; } catch (e) { return 'standard'; } };
// the level comes from KH.motion() only; the OS media query is a fallback for a heatmap that has none
const reducedNow = () => (typeof KH.motion === 'function' ? motion() === 'reduced' : reduceMotion.matches);
const fancy = () => motion() === 'fancy' && document.visibilityState === 'visible';

/* ───────────────── helpers ───────────────── */
const h = KH.h, F = KH.fmt;
const NS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  el.append(...kids);
  return el;
}
const isNum = v => v != null && v !== '' && isFinite(v);
const pad = n => String(n).padStart(2, '0');
const int = v => (isNum(v) ? F.int(+v) : '—');
const pct = (v, d = 2) => (isNum(v) ? F.pct(+v, d) : '—');
const cls = v => (isNum(v) ? F.cls(+v) : 'flat');
const fixed = (v, d, unit) => (isNum(v) ? (v < 0 ? MINUS : '') + Math.abs(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d }) + unit : '—');
// 주식 수·거래량: 1.2억 / 2,783만 / 9,999
function compact(v) {
  if (!isNum(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? MINUS : '';
  if (a >= 1e8) return s + (a / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: a >= 1e10 ? 0 : 1 }) + '억';
  if (a >= 1e4) return s + (a / 1e4).toLocaleString('ko-KR', { maximumFractionDigits: a >= 1e6 ? 0 : 1 }) + '만';
  return s + Math.round(a).toLocaleString('ko-KR');
}
const signed = v => (!isNum(v) ? '—' : (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(Math.round(v)).toLocaleString('ko-KR'));
const signedCompact = v => (!isNum(v) ? '—' : (v > 0 ? '+' : '') + compact(v));
const store = {
  get(k, d) { try { const v = localStorage.getItem('khm.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('khm.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
// KST calendar parts of a Date
function kst(d) {
  const k = new Date(d.getTime() + KST * 1000);
  return { y: k.getUTCFullYear(), m: k.getUTCMonth() + 1, d: k.getUTCDate(), wd: k.getUTCDay(), hh: k.getUTCHours(), mm: k.getUTCMinutes(), ss: k.getUTCSeconds(),
    hm: k.getUTCHours() * 100 + k.getUTCMinutes(), key: k.getUTCFullYear() * 10000 + (k.getUTCMonth() + 1) * 100 + k.getUTCDate() };
}
const toDate = v => { const d = v ? new Date(v) : null; return d && !isNaN(d) ? d : null; };
function asOfLabel(v) {
  const d = toDate(v);
  if (!d) return '';
  const p = kst(d);
  return `${p.m}월 ${p.d}일 (${WD[p.wd]}) ${pad(p.hh)}:${pad(p.mm)}`;
}
function clock(v) { const d = toDate(v) || new Date(); const p = kst(d); return `${pad(p.hh)}:${pad(p.mm)}:${pad(p.ss)}`; }
// 'YYYY-MM-DD' → 2026.11.06 / 11.06 (older years keep the year)
function dateCell(s) {
  const [y, m, d] = String(s).split('-');
  const short = +y === kst(new Date()).y ? `${m}.${d}` : `${y.slice(2)}.${m}.${d}`;
  return [h('span', { class: 'l', text: `${y}.${m}.${d}` }), h('span', { class: 's', text: short })];
}
/* ───────────────── theme colours (docs/standards/themes.md) ─────────────────
 * The page is coloured by CSS tokens (stock.css); the chart canvas cannot read them, so the strings it needs come from here: a probe
 * element resolves var() / color-mix() to rgb, and applyChartTheme() hands them to lightweight-charts again on every kh:theme. */
let probeEl = null;
function cssColor(value) {   // any CSS colour (var() and color-mix() included) → [r, g, b, a 0..1], or null
  try {
    if (!probeEl) { probeEl = document.createElement('span'); probeEl.setAttribute('aria-hidden', 'true'); probeEl.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none'; }
    const host = root || document.body;
    if (probeEl.parentNode !== host) host.append(probeEl);
    probeEl.style.color = '';
    probeEl.style.color = value;
    const c = getComputedStyle(probeEl).color;
    let m = /^rgba?\(([^)]+)\)$/.exec(c);
    if (m) { const v = m[1].split(/[\s,\/]+/).filter(Boolean).map(x => (/%$/.test(x) ? parseFloat(x) / 100 : parseFloat(x))); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; }
    m = /^color\(srgb ([^)]+)\)$/.exec(c);
    if (m) { const v = m[1].split(/[\s\/]+/).filter(Boolean).map(x => (/%$/.test(x) ? parseFloat(x) / 100 : parseFloat(x))); return [v[0] * 255, v[1] * 255, v[2] * 255, v.length > 3 ? v[3] : 1]; }
  } catch (e) { /* fall through */ }
  return null;
}
const rgbStr = (c, a) => { const k = a == null ? c[3] : a; const r = Math.round(c[0]), g = Math.round(c[1]), b = Math.round(c[2]); return k >= 1 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${+k.toFixed(3)})`; };
// a token (or any colour) as a string the chart accepts; `dflt` is today's dark-theme value for a page that defines no token yet
const tokColor = (name, dflt) => cssColor(`var(${name}, ${dflt})`) || cssColor(dflt) || [128, 128, 128, 1];
const over = (c, bg) => [c[0] * c[3] + bg[0] * (1 - c[3]), c[1] * c[3] + bg[1] * (1 - c[3]), c[2] * c[3] + bg[2] * (1 - c[3]), 1];   // a translucent colour laid on an opaque one
// the same colour at another strength — palette stops (hex) and tokens alike
function hexRgba(color, a) { const c = cssColor(color); return c ? rgbStr(c, a) : color; }
const themeId = () => { try { return (KH.theme && KH.theme()) || document.documentElement.dataset.theme || 'base'; } catch (e) { return 'base'; } };
const isLight = () => { const t = document.documentElement.dataset.tone; return t ? t === 'light' : /^(paper|glass-light)$/.test(themeId()); };
let CH = null;   // the chart's colours for the theme in use
function chartColors() {
  const light = isLight();
  const page = tokColor('--page', '#131418'), muted = tokColor('--muted', '#8a8f99'), fg = tokColor('--fg', '#eef0f3'), fg2 = tokColor('--fg2', '#bcc0c8');
  const line = tokColor('--line', '#2b2d34'), line2 = tokColor('--line2', '#373a42');
  const tag = light ? fg2 : over(line2, over(page, [0, 0, 0, 1]));   // crosshair / 전일 종가 labels: opaque, so the label text keeps its contrast
  // moving averages: pink · sky · violet · grey, never the up/down hues nor the interface amber (stock.css --ma-*; the fallback is the dark-tone value, or the light one on a light tone)
  const maD = { 5: '#ff80c4', 20: '#5cc8ff', 60: '#b99cff', 120: '#c4c8ce' }, maL = { 5: '#b01f78', 20: '#0b6498', 60: '#6a3fd0', 120: '#474b52' };
  const ma = {};
  for (const n of MA_N) ma[n] = rgbStr(tokColor(`--ma-${n}`, (light ? maL : maD)[n]), 1);
  return {
    light, ma, flat: rgbStr(muted, 1), text: rgbStr(muted, 1), line: rgbStr(line), sep: rgbStr(line), sepHover: rgbStr(fg, .06),
    gridV: rgbStr(fg, light ? .07 : .035), gridH: rgbStr(fg, light ? .09 : .045),
    tagBg: rgbStr(tag, 1), tagFg: rgbStr(light ? page : fg, 1),
  };
}
const chc = () => CH || (CH = chartColors());
// icons (design.md §4 · §12 ④): the hand-drawn set, one stroke on screen — 1.75 px, non-scaling (stock.css .sp-ic), round ends, currentColor
const chevron = () => svg('svg', { class: 'sp-ic', viewBox: '0 0 24 24', 'aria-hidden': 'true' }, svg('path', { d: 'M15 5l-7 7 7 7' }));
const caret = () => svg('svg', { class: 'cr sp-ic', viewBox: '0 0 10 10', 'aria-hidden': 'true' }, svg('path', { d: 'M2.5 4l2.5 2.5L7.5 4' }));
function skel(w, hgt) { return h('span', { class: 'sp-skel', style: `width:${w};height:${hgt || '1em'}` }); }
// retry: a key from retryKey() (or a plain function: a plain 다시 시도 key)
function msgBox(title, sub, retry) {
  return h('div', { class: 'sp-msgbox', role: 'status' },
    h('p', { class: 'sp-msg-t', text: title }),
    sub ? h('p', { class: 'sp-msg-s', text: sub }) : null,
    retry ? (retry.nodeType ? retry : h('button', { type: 'button', class: 'sp-btn', onclick: retry, text: '다시 시도' })) : null);
}
/* ───────────────── living controls (docs/standards/controls.md): the template's KH.ui helpers and --c-* tokens, when present ───────────────── */
const UI = KH.ui && typeof KH.ui.state === 'function' ? KH.ui : null;
const uiIcon = n => (UI && typeof UI.icon === 'function' ? UI.icon(n) : null);
const uiSeg = el => { if (UI && typeof UI.seg === 'function') UI.seg(el); };
const cMs = (name, d) => (UI && typeof UI.ms === 'function' ? UI.ms(name) : d);          // '줄이기' sets --c-fast/base/switch to 0
const say = t => { if (UI && typeof UI.live === 'function') UI.live(t); };
/* 고르기 표시 (design.md §6-3 · §7 · §8): one indicator element per segment / tab row / underline row (.sp-ind), moved by KH.spring.edges —
   both edges on `lead` (its default since ② 단단한 이동, AGENTS §3-38): it keeps its shape on the way, no stretch. The first placement,
   a resize, held arrow keys (§8) and 줄이기 put it there at once; a pick on another line of a wrapped row fades it in there (P5). Without
   KH.spring the template's ::before indicator does it (KH.ui.seg). line: the underline row (a 2px bar along the bottom). */
const SEGS = new Map();   // row → {ind, line, top, quick}
const segButtons = row => [...row.children].filter(b => b.tagName === 'BUTTON');
function spSeg(row, line) {
  if (!(KH.spring && typeof KH.spring.edges === 'function')) { uiSeg(row); return; }
  const ind = h('i', { class: 'sp-ind', 'aria-hidden': 'true' });
  row.prepend(ind);
  row.classList.add('sp-ix');
  if (line) row.classList.add('sp-ix-line');
  SEGS.set(row, { ind, line: !!line, top: null, quick: false });
  new MutationObserver(() => segPlace(row)).observe(row, { subtree: true, attributes: true, attributeFilter: ['aria-pressed', 'aria-selected', 'hidden'] });
  if ('ResizeObserver' in window) { const ro = new ResizeObserver(() => segPlace(row, true)); ro.observe(row); for (const b of segButtons(row)) ro.observe(b); }
  segPlace(row, true);
}
function segPlace(row, now) {
  const st = SEGS.get(row);
  if (!st) return;
  const b = segButtons(row).find(x => !x.hidden && (x.getAttribute('aria-pressed') === 'true' || x.getAttribute('aria-selected') === 'true'));
  if (!b || !b.offsetWidth) { delete row.dataset.on; st.top = null; return; }   // nothing picked, or not laid out (a hidden panel): placed when it shows
  const box = { left: b.offsetLeft, width: b.offsetWidth }, top = b.offsetTop, ctl = KH.spring.edges(st.ind);
  const shown = row.dataset.on != null && st.top != null, moved = shown && Math.abs(top - st.top) > 1;
  if (!st.line) { st.ind.style.top = top + 'px'; st.ind.style.height = b.offsetHeight + 'px'; }
  if (!shown || moved || now || st.quick || !motionOk() || !ctl.value()) ctl.set(box); else ctl.to(box);
  if (moved) { const f = spring('fade', 270); if (f.dur) st.ind.animate([{ opacity: 0 }, { opacity: 1 }], { duration: f.dur, easing: f.easing }); }
  st.quick = false; st.top = top;
  row.dataset.on = '';
}
// held arrow keys (design.md §8): the next placement of that row is at once
const segQuick = row => { const st = SEGS.get(row); if (st) st.quick = true; };
function setState(el, st) {
  if (!el) return;
  if (UI) { UI.state(el, st); return; }
  el.dataset.st = st;
  for (const x of el.querySelectorAll('.kl')) x.classList.toggle('on', x.matches(`[data-l~="${st}"]`));
}
// an async key (§5-3): the template's KH.ui.akey — one label per state stacked in one box (the key keeps its longest label); 'work'
// carries the ring, 'done' ✓, 'fail' ! (KH.ui.state switches them). Without KH.ui: the idle label only.
function asyncKey(cls, says, st) {
  if (UI && typeof UI.akey === 'function') return UI.akey(cls, says, st);
  return h('button', { type: 'button', class: cls, 'data-st': st || 'idle', text: says[st || 'idle'] });
}
/* 다시 시도 (§5-3): the template's KH.ui.retry, shared with the 해외 tab — the message stays while it works (ring "받는 중"), then ✓
   "받았어요" for --c-slow before the content comes in, or ! "아직 안 돼요 · 다시" until the next press. run() → true / false / null (no
   longer wanted). A result for another stock (S.gen moved on) is dropped. failed: the areas whose last retry failed, so a message
   drawn again keeps the !. */
const failed = new Set();
function retryKey(area, run, render, cls) {
  cls = cls || 'sp-btn sp-retry';
  let g = S.gen;
  if (UI && typeof UI.retry === 'function') {
    return UI.retry({ cls, run, render, fail: failed.has(area), alive: () => g === S.gen,
      onStart: () => { g = S.gen; failed.delete(area); }, onFail: () => failed.add(area) });
  }
  return h('button', { type: 'button', class: cls, onclick: async () => { g = S.gen; const r = await run(); if (g === S.gen && r) render(); }, text: '다시 시도' });
}
function errSub(e) {
  if (e && e.status === 404) return '이 종목의 정보를 찾지 못했어요.';
  if (e && e.status) return `서버가 응답하지 않아요 (${e.status}). 잠시 뒤 다시 시도해 주세요.`;
  return '네트워크 연결을 확인하고 다시 시도해 주세요.';
}

/* ───────────────── state ───────────────── */
const S = {
  open: false, code: null, opener: null, pushed: false, prevHash: '', prevTitle: '',
  gen: 0,
  tf: TF_NAME[store.get('stock.iv', 'day')] ? store.get('stock.iv', 'day') : 'day',
  ivMin: isMin(store.get('stock.ivMin', '')) ? store.get('stock.ivMin', '') : null,   // the last minute interval picked (the picker's focus when 분 is not on)
  tab: TAB[store.get('stockTab', TABS[0].key)] ? store.get('stockTab', TABS[0].key) : TABS[0].key,
  sum: null, sumErr: null, phase: 'unknown',
  ob: null, obErr: null, obAt: null,              // 호가 tab
  inv: null, invErr: null, invLoading: false,     // 투자자 tab
  est: null,                                      //   its 오늘 잠정 block (가족 기기만, AGENTS §3-40): {code, st:'load'|'ok'|'fail'|'none', at, j}
  daily: null,                                    // 일별 시세 tab
  news: { news: null, disc: null },               // 뉴스·공시 tab: per list {loading, err} while fetching (rows live in newsCache)
  ci: { fa: null, fq: null, res: null },          // 종목 정보 tab: per source {loading, err} while fetching (data lives in ciCache)
  ciSel: {}, resAll: false, finTbl: false,        //   picked period per 분기/연간, report list expanded, 표로 보기 open
  timers: { sum: 0, chart: 0, ob: 0 },
};
const ctrls = {};
function abort(key) { if (ctrls[key]) { ctrls[key].abort(); ctrls[key] = null; } }
function abortAll() { for (const k in ctrls) abort(k); }
async function api(path, key) {
  abort(key);
  const ac = new AbortController();
  ctrls[key] = ac;
  const res = await fetch(`api/stock/${encodeURIComponent(S.code)}/${path}`, { cache: 'no-store', signal: ac.signal });
  let body = null;
  try { body = await res.json(); } catch (e) { /* not JSON */ }
  if (ctrls[key] === ac) ctrls[key] = null;
  if (!res.ok || !body) { const err = new Error((body && body.error) || 'HTTP ' + res.status); err.status = res.status; throw err; }
  return body;
}
const aborted = e => e && e.name === 'AbortError';

// regular session state, from the summary's time and the KST clock
function phaseOf(sum) {
  const at = sum && toDate(sum.asOf);
  if (!at) return 'unknown';
  const now = kst(new Date()), a = kst(at);
  if (a.key === now.key) {
    if (now.hm < 900) return 'pre';
    if (now.hm < 1530) return sum.marketStatus == null || sum.marketStatus === 'OPEN' ? 'open' : 'closed';
    if (now.hm < 2000) return 'after';
    return 'closed';
  }
  if (now.wd === 0 || now.wd === 6) return 'weekend';
  if (now.hm < 800) return 'closed';
  if (now.hm < 905) return 'pre';
  return 'holiday';
}
// prices stamped after 15:30 include NXT and KRX after-hours trades
function nxtApplies() {
  const at = LIVE && S.sum && toDate(S.sum.asOf);
  return !!at && kst(at).hm > 1530;
}

/* ───────────────── DOM ───────────────── */
let root = null;
const R = {};
function build() {
  if (root) return;
  R.back = h('button', { class: 'sp-back', type: 'button', 'aria-label': '히트맵으로 돌아가기', title: '히트맵으로 돌아가기 (Esc)', onclick: () => close() },
    chevron(), h('span', { class: 'sp-back-t', text: '히트맵' }));
  R.name = h('h1', { class: 'sp-name', id: 'sp-name', tabindex: '-1' });
  R.code = h('span', { class: 'sp-code num' });
  R.mkt = h('span', { class: 'sp-mkt' });
  R.path = h('span', { class: 'sp-path' });
  R.price = h('div', { class: 'sp-price num' });
  R.chg = h('div', { class: 'sp-chg num' });
  R.lim = h('span', { class: 'sp-lim', hidden: true });
  R.al = h('span', { class: 'sp-al', hidden: true });                     // 시장 경보 (AGENTS §3-37 ⓐ): the template's neutral badges
  R.nxt = h('div', { class: 'sp-nxt num', hidden: true }, h('span', { class: 'k' }), ' ', h('span', { class: 'pv' }), ' ', h('span', { class: 'pr' }), h('span', { class: 't' }));
  R.star = h('button', { class: 'sp-star', type: 'button', 'aria-label': '관심종목', 'aria-pressed': 'false', hidden: true, onclick: toggleWatch },
    svg('svg', { class: 'sp-ic', viewBox: '0 0 24 24', 'aria-hidden': 'true' }, svg('path', { d: 'M12 3.4l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6-4.4-4.2 6-.8z' })));
  R.head = h('header', { class: 'sp-head' }, h('div', { class: 'sp-head-in' }, R.back,
    h('div', { class: 'sp-id' }, R.name, h('div', { class: 'sp-sub' }, R.code, R.mkt, R.path)),
    h('div', { class: 'sp-quote', 'aria-live': 'polite' }, R.price, R.chg, R.lim, R.al, R.nxt),
    R.star));
  R.meta = h('div', { class: 'sp-meta' });
  R.stats = h('dl', { class: 'sp-stats' });
  R.body = h('div', { class: 'sp-body' });
  R.peers = h('section', { class: 'sp-peers', 'aria-label': '같은 업종 종목' });
  R.foot = h('footer', { class: 'sp-foot' });
  R.main = h('div', { class: 'sp-main' }, R.meta, R.stats, R.body, R.foot);
  root = h('div', { class: 'sp' + (LIVE ? '' : ' sp-snap'), id: 'kh-stock', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'sp-name', tabindex: '-1', hidden: true }, R.head, R.main);
  if (LIVE) buildLive(); else buildSnapshot();
  document.body.append(root);
  addEventListener('resize', measureHead);
}

function buildLive() {
  // segments (docs/standards/controls.md §5-4): the template's deep tray (.seg) + one raised indicator that slides (KH.ui.seg)
  // design.md §7 segment: 분 · 일 · 주 · 월 · 년; the indicator moves in one piece on `lead` (stock.css)
  R.tfs = h('div', { class: 'sp-seg sp-tfs seg', role: 'group', 'aria-label': '차트 간격' },
    TF_TABS.map(([k, label]) => k === 'min'
      ? (R.minBtn = h('button', { type: 'button', class: 'sp-tfmin', 'data-tf': k, 'aria-pressed': 'false', 'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-controls': 'sp-ivm',
          onclick: () => ivMenu(IVM.st !== 'open'), onkeydown: ivBtnKey }, h('span', { class: 't' }, h('span', { class: 'tn', text: label })), caret()))
      : h('button', { type: 'button', 'data-tf': k, 'aria-pressed': 'false', onclick: () => setTf(k), text: label })));
  spSeg(R.tfs);
  // 분's picker (design.md §7 팝오버): a menu of radio items that grows out of the tab. It lives in .sp-tfbar, outside the segment's tray,
  // so nothing clips it: the box (.sp-ivm) changes size, the items sit in a fixed-width layer (.sp-ivm-in) with the highlight plate
  R.ivmHl = h('i', { class: 'sp-ivm-hl', 'aria-hidden': 'true' });
  R.ivmIn = h('div', { class: 'sp-ivm-in', role: 'none' }, R.ivmHl,
    ...MINS.map(([k, label]) => h('button', { type: 'button', role: 'menuitemradio', 'data-iv': k, 'aria-checked': 'false', tabindex: '-1', onclick: () => pickMin(k) },
      h('span', { class: 't', text: label }), svg('svg', { class: 'ck sp-ic', viewBox: '0 0 16 16', 'aria-hidden': 'true' }, svg('path', { d: 'M3.5 8.5l3 3 6-6.5' })))));
  R.ivm = h('div', { class: 'sp-ivm', id: 'sp-ivm', role: 'menu', 'aria-label': '분봉 간격', hidden: true, onkeydown: ivMenuKey }, R.ivmIn);
  ivWire();
  R.period = h('div', { class: 'sp-period num' });
  R.chart = h('div', { class: 'sp-chart', role: 'img', 'aria-label': '가격 차트' });
  R.legend = h('div', { class: 'sp-legend num', 'aria-hidden': 'true' });
  R.chartMsg = h('div', { class: 'sp-chartmsg' });
  R.note = h('div', { class: 'sp-chnote', role: 'status', 'aria-live': 'polite' });
  R.mac = {};
  // 이동평균 (사용자 2026-11-14 "이동평균선 5일 20일 60일 120일 저 버튼들 레이아웃과 디자인 개선이 필요해보여"): design.md §7 legend toggle —
  // a short line in the MA colour, the period, the value under the crosshair (tabular, one reserved width). On = filled line + --fg,
  // off = hollow line + --muted (no opacity dimming); the value stays in its place either way, so nothing moves when one is toggled.
  R.ma = h('div', { class: 'sp-ma', role: 'group', 'aria-label': '이동평균' },
    h('span', { class: 'sp-ma-t', 'aria-hidden': 'true', text: '이동평균' }),
    ...MA_N.map(n => {
      const v = h('span', { class: 'v num' }), nm = h('span', { class: 'n' });
      R.mac[n] = { v, nm, btn: h('button', { type: 'button', class: 'sp-mac', 'data-n': String(n), 'aria-pressed': 'false', style: `--mc: var(--ma-${n})`, onclick: () => toggleMa(n) },
        h('i', { class: 'sw', 'aria-hidden': 'true' }), nm, v) };
      return R.mac[n].btn;
    }));
  syncMaChips();
  addEventListener('resize', fitMa);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitMa, () => {});
  const chartcol = h('section', { class: 'sp-chartcol', 'aria-label': '가격 차트' },
    h('div', { class: 'sp-tfbar' }, R.tfs, R.ivm, R.period),
    R.ma,
    h('div', { class: 'sp-chartwrap' }, R.chart, R.legend, R.note, R.chartMsg),
    R.peers);
  R.tabs = h('div', { class: 'sp-seg sp-tabs seg', role: 'tablist', 'aria-label': '시세 정보' });
  R.panels = {};
  for (const { key: k, label } of TABS) {
    R.tabs.append(h('button', { type: 'button', role: 'tab', id: 'sp-t-' + k, 'aria-controls': 'sp-p-' + k, 'aria-selected': 'false', tabindex: '-1', 'data-tab': k, onclick: () => setTab(k), text: label }));
    R.panels[k] = h('div', { class: 'sp-panel', id: 'sp-p-' + k, role: 'tabpanel', 'aria-labelledby': 'sp-t-' + k, tabindex: '0', hidden: true });
  }
  R.tabs.addEventListener('keydown', e => {
    const keys = TABS.map(t => t.key);
    let i = keys.indexOf(S.tab);
    if (e.key === 'ArrowRight') i = (i + 1) % keys.length;
    else if (e.key === 'ArrowLeft') i = (i - 1 + keys.length) % keys.length;
    else if (e.key === 'Home') i = 0;
    else if (e.key === 'End') i = keys.length - 1;
    else return;
    e.preventDefault();
    if (e.repeat) segQuick(R.tabs);
    setTab(keys[i], true);
  });
  spSeg(R.tabs);
  for (const t of TABS) if (t.build) t.build(R.panels[t.key]);
  R.body.append(chartcol, h('section', { class: 'sp-side', 'aria-label': TABS.map(t => t.label).join('·') }, h('div', { class: 'sp-tabwrap' }, R.tabs), ...Object.values(R.panels)));
  R.foot.append(h('p', {}, '데이터: 네이버 증권(비공식). 차트: ',
    h('a', { href: 'https://www.tradingview.com/', target: '_blank', rel: 'noopener', text: 'TradingView Lightweight Charts™' }), '.'),
    h('p', { text: '대차잔고 · 배당 내역 · 기업 정보: 금융위원회(공공데이터포털), 하루 한 번.' }),
    h('p', { class: 'sp-disclaim', text: '투자 판단의 근거로 쓰지 마세요.' }));   // 사용자 2026-11-14 11:59: 항상 맨 아래 줄
}

function buildSnapshot() {
  R.offline = h('div', { class: 'sp-offline' });
  R.body.append(R.offline, R.peers);
  R.foot.append(h('p', { text: `데이터: 네이버 증권. ${asOfLabel(KH.asOf())} 기준 스냅샷이라 시세가 바뀌지 않아요.` }),
    h('p', { class: 'sp-disclaim', text: '투자 판단의 근거로 쓰지 마세요.' }));   // 사용자 2026-11-14 11:59: 항상 맨 아래 줄
}

function measureHead() {
  if (root && !root.hidden) root.style.setProperty('--sp-hh', R.head.offsetHeight + 'px');
}

/* ───────────────── header ───────────────── */
/* 머리 숫자 (design.md §3 ③ · §6-2 P10 · §6-4 P9): the price, the change and the NXT line's numbers are two parts each — the integer
   part (.hn-i) and the decimals (.hn-d, ".23%"), which the header's big numbers set one type step smaller (stock.css). 화려하게 rolls the
   changed digits on the template's drum (KH.ui.roll: the short way round, the rightmost first 40 ms apart, the `roll` spring, a 14 % mask)
   — the decimals first, the integer part as many 40 ms steps later as the decimals had changed digits, so the whole number still goes
   right to left; 기본 swaps the text the way the value went (KH.ui.swap: up from below, down from above). A change of length (9,990 →
   10,010) swaps in 화려하게 too. 줄이기, a hidden tab, the first paint of a stock and an unchanged value write at once (P4). The element's
   text is the value at every moment (dataset.v as well). */
const ROLL_GAP = 40;
const numSplit = t => { const i = t.lastIndexOf('.'); return i < 0 ? [t, ''] : [t.slice(0, i), t.slice(i)]; };
function numParts(el) {
  let I = el.querySelector(':scope > .hn-i'), D = el.querySelector(':scope > .hn-d');
  if (!I || !D) { I = h('span', { class: 'hn-i' }); D = h('span', { class: 'hn-d' }); el.replaceChildren(I, D); }
  return [I, D];
}
// a part written at once: whatever rolls or swaps in it stops where it should end
function numWrite(el, t) {
  for (const a of el.getAnimations({ subtree: true })) { try { a.cancel(); } catch (e) { /* gone */ } }
  el.classList.remove('sw-go', 'sw-b'); delete el.dataset.was;
  if (el.textContent !== t || el.childElementCount) el.textContent = t;
}
const rollDigits = (a, b) => { let n = 0; for (let i = 0; i < b.length; i++) if (a[i] !== b[i] && /\d/.test(a[i] || '') && /\d/.test(b[i])) n++; return n; };
function numSettle(el) {
  if (!el) return;
  clearTimeout(el._hnT);
  const [I, D] = numParts(el), [ti, td] = numSplit(el.dataset.v || I.textContent + D.textContent);
  numWrite(I, ti); numWrite(D, td);
}
function headNum(el, text, dir) {
  const [I, D] = numParts(el), [ti, td] = numSplit(text);
  const was = el.dataset.v;
  if (was === text && I.textContent === ti && D.textContent === td) return;   // the same value again: a running roll goes on
  clearTimeout(el._hnT);
  el.dataset.v = text;
  D.hidden = !td;
  const wi = I.textContent, wd = D.textContent, m = motion();
  if (was == null || !dir || m === 'reduced' || document.hidden || !el.isConnected || !el.getClientRects().length || !UI) { numWrite(I, ti); numWrite(D, td); return; }
  if (m === 'fancy' && typeof UI.roll === 'function' && wi.length === ti.length && wd.length === td.length) {
    UI.roll(D, td, dir);
    const lag = rollDigits(wd, td) * ROLL_GAP;
    if (lag && wi !== ti) { el._hnT = setTimeout(() => { el._hnT = 0; if (el.dataset.v === text) UI.roll(I, ti, dir); }, lag); } else UI.roll(I, ti, dir);
    return;
  }
  if (typeof UI.swap === 'function') { UI.swap(I, ti, wi, dir); UI.swap(D, td, wd, dir); return; }
  numWrite(I, ti); numWrite(D, td);
}
let headPrev = null;   // {code, price} of the last quote drawn, to tell which way it moved
const headQuote = () => { try { const q = LIVE && typeof KH.quote === 'function' ? KH.quote(S.code) : null; return q && isNum(q.p) && q.p > 0 ? q : null; } catch (e) { return null; } };
// the summary feeds the heatmap's quote store (taken only when it is fresher than the row held): its price, change, day candle, volume, NXT
function feedStore(j) {
  if (!LIVE || !j || !isNum(j.price) || !(+j.price > 0) || !KH.quotes || typeof KH.quotes.put !== 'function') return;
  const nx = j.nxt && isNum(j.nxt.p) ? j.nxt : null;
  try {
    KH.quotes.put([{ c: String(j.code || S.code), partial: true, p: +j.price, d: +j.change || 0, r: +j.ratio || 0, t: j.asOf || null,
      op: j.open, hi: j.high, lo: j.low, v: j.volume, tv: j.tradingValue, nx }], j.asOf);
  } catch (e) { /* the page still draws from its summary */ }
}
function renderHead() {
  const st = KH.stock(S.code), s = S.sum;
  const name = (s && s.name) || (st && st.n) || (LIVE && !S.sumErr ? '' : S.code);
  R.name.replaceChildren(name || skel('6em', '0.9em'));
  R.name.classList.toggle('long', !!name && [...name].length > 7);      // phones: 8+ characters (삼성바이오로직스, 한화에어로스페이스) fit at 16 px
  R.code.textContent = name === S.code ? '' : S.code;
  const m = (s && s.market) || (st && st.m);
  R.mkt.textContent = m ? KH.MKT_NAME[m] || '' : '';
  R.path.textContent = st && st.s ? `${st.s} › ${st.i}` : '';
  R.path.hidden = !(st && st.s);
  let price = null, chg = null, ratio = null;
  // §3-24 the headline is the heatmap's row for this code in the chosen price basis (KRX · NXT · 통합) — the same number the map, the
  // ★관심 tab and the ticker show; the summary only fills in when the heatmap holds no row (snapshot, a stock outside every list)
  const q = headQuote();
  if (q) { price = q.p; chg = q.d; ratio = q.r; }
  else if (s && isNum(s.price)) { price = +s.price; chg = +s.change; ratio = +s.ratio; }
  else if (st) { price = st.p; chg = st.d; ratio = st.r; }
  if (price == null) {
    clearTimeout(R.price._hnT); clearTimeout(R.chg._hnT); delete R.price.dataset.v; delete R.chg.dataset.v; headPrev = null;
    R.price.replaceChildren(S.sumErr ? '—' : skel('5.2em', '0.85em'));
    R.chg.replaceChildren(S.sumErr ? '' : skel('6.5em', '0.8em'));
    R.chg.className = 'sp-chg num';
  } else {
    const arrow = chg > 0 ? '▲' : chg < 0 ? '▼' : '';
    const dir = headPrev && headPrev.code === S.code && isNum(headPrev.price) ? Math.sign(price - headPrev.price) : 0;
    headPrev = { code: S.code, price };
    R.chg.className = 'sp-chg num ' + cls(chg);
    headNum(R.price, int(price), dir);
    headNum(R.chg, `${arrow}${isNum(chg) ? int(Math.abs(chg)) : ''}  ${pct(ratio)}`, dir);
    R.chg.setAttribute('aria-label', `전일 대비 ${signed(chg)}원, ${pct(ratio)}`);
  }
  renderLim();
  renderAl();
  renderNxt();
  renderStar();
  if (name) document.title = `${name} ${price != null ? int(price) : ''} ${price != null ? pct(ratio) : ''} · 판세`.replace(/\s+/g, ' ');
}

// 상한가·하한가: the quote row's lim (1/−1). Rows without lim (older data) or stocks outside the quote universe fall back to
// |등락률| ≥ 29.5 — a limit move can round to +29.87%, so never test ≥ 30 (data/ENDPOINTS_EXTRA.md §5).
function limitOf() {
  const st = KH.stock(S.code);
  if (st && st.lim != null) return st.lim === 1 || st.lim === -1 ? st.lim : 0;
  const r = st && isNum(st.r) ? +st.r : S.sum && S.sum.code === S.code && isNum(S.sum.ratio) ? +S.sum.ratio : null;
  return r == null ? 0 : r >= 29.5 ? 1 : r <= -29.5 ? -1 : 0;
}
// NXT line (AGENTS.md §3-8): summary.nxt {p,d,r,s:'pre'|'after',o:1|0,t}; null/missing = the stock has no NXT trading, no line
let nxtPrev = null;
// the NXT session windows (KST): 프리 08:00–08:50, 메인 09:00–15:20, 애프터 15:30–20:00 — the heatmap's rule (§3-10)
function nxWindow(sess) {
  const now = kst(new Date()), w = { pre: [800, 850], reg: [900, 1520], after: [1530, 2000] }[sess];
  return !!w && now.wd >= 1 && now.wd <= 5 && now.hm >= w[0] && now.hm < w[1];
}
function renderNxt() {
  // the other venue under the headline: NXT normally; KRX when the headline itself is an NXT price (NXT, or 통합 while NXT traded last)
  const q = headQuote(), st = KH.stock(S.code), n = R.nxt;
  const own = st && st.nx && isNum(st.nx.p) ? st.nx : null;
  let x = own || (S.sum && S.sum.code === S.code && S.sum.nxt && isNum(S.sum.nxt.p) ? S.sum.nxt : null), krx = false;
  if (q && q.venue === 'NXT' && st && isNum(st.p)) { x = { p: st.p, d: st.d, r: st.r, t: null }; krx = true; }
  n.hidden = !x;
  if (!x) { nxtPrev = null; return; }
  const K = n.querySelector('.k'), PV = n.querySelector('.pv'), PR = n.querySelector('.pr'), T = n.querySelector('.t');
  // label: just the venue. The session (Naver's tradingSessionType → Worker s: pre · reg · after) and whether it is trading go in the
  // tooltip; "trading" = Naver's OPEN flag and the KST clock inside that session's window, the map's rule (§3-10: Naver leaves OPEN on
  // for a while after a session ends)
  const c = cls(+x.d), sess = { pre: '프리마켓', reg: '메인마켓', after: '애프터마켓' }[x.s] || '';
  n.className = 'sp-nxt num ' + c;
  K.textContent = krx ? 'KRX' : 'NXT';
  const live = !krx && !!x.o && nxWindow(x.s);
  n.title = krx ? 'KRX(한국거래소) 시세' : `NXT(넥스트레이드)${sess ? ' ' + sess : ''} · ${live ? '거래 중' : '마감'}`;
  const d = toDate(x.t), tm = d ? clock(d).slice(0, 5) : '';
  const dir = nxtPrev && nxtPrev.code === S.code ? Math.sign(+x.p - nxtPrev.p) : 0;
  nxtPrev = { code: S.code, p: +x.p };
  const pv = int(x.p), pr = pct(x.r);
  headNum(PV, pv, dir); headNum(PR, pr, dir);
  T.textContent = tm ? ` · ${tm}` : '';
  if (tm) n.title += ` · ${tm}`;                       // phones ≤ 430 px hide the time on the line
  n.setAttribute('aria-label', `${krx ? 'KRX' : n.title} ${pv}원 ${pr}${tm ? ' ' + tm : ''}`);
}
function renderLim() {
  const lim = limitOf();
  R.lim.hidden = !lim;
  R.lim.className = 'sp-lim' + (lim > 0 ? ' up' : lim < 0 ? ' dn' : '');
  R.lim.textContent = lim > 0 ? '상한가' : lim < 0 ? '하한가' : '';
}

// 시장 경보 (AGENTS §3-37 ⓐ): KH.alerts.tags (투자주의 · 경고 · 위험 · 관리종목 · 거래정지, 2 + "외 N"); the 기준 시각 goes in the meta
// line. Redrawn only when what it says changes — the quote box is aria-live and the quotes arrive every few seconds.
const alertsApi = () => (KH.alerts && typeof KH.alerts.tags === 'function' && typeof KH.alerts.of === 'function' ? KH.alerts : null);
function renderAl() {
  const A = alertsApi(), el = A && S.code ? A.tags(S.code, { max: 2 }) : null;
  const sig = el ? `${S.code}|${el.dataset.al}|${[...el.querySelectorAll('[title]')].map(x => x.title).join('|')}` : '';
  if (R.al.dataset.sig === sig) return;
  R.al.dataset.sig = sig;
  R.al.hidden = !el;
  R.al.replaceChildren(...(el ? [el] : []));
}
function alertMeta() {
  const A = alertsApi(), a = A && S.code ? A.of(S.code) : null;
  if (!a) return null;
  const rest = a.labels.slice(2);
  return h('span', { class: 'sp-alnote' }, rest.length ? `외 ${rest.length}: ${rest.join(' · ')} · ` : '', A.note(S.code));
}

// 관심종목: KH.watch comes from the heatmap (AGENTS.md §3-2). Without it the star stays hidden.
const watchApi = () => (KH.watch && typeof KH.watch.has === 'function' && typeof KH.watch.toggle === 'function' ? KH.watch : null);
function renderStar() {
  const W = watchApi();
  R.star.hidden = !W || !S.code;
  if (R.star.hidden) return;
  const on = !!W.has(S.code);
  R.star.setAttribute('aria-pressed', String(on));
  R.star.title = usePicker() ? '관심 그룹 고르기' : on ? '관심종목에서 빼기' : '관심종목에 넣기';
  R.star.setAttribute('aria-haspopup', usePicker() ? 'dialog' : 'false');
}
// 관심 그룹 (AGENTS.md §3-11): with KH.watch.groups() and more than the single 기본 group, ☆ opens a picker; otherwise it toggles instantly
const groupsApi = () => { const W = watchApi(); return W && ['groups', 'groupsOf', 'setGroups', 'createGroup'].every(k => typeof W[k] === 'function') ? W : null; };
const usePicker = () => { const W = groupsApi(); if (!W) return false; try { return W.groups().length > 1; } catch (e) { return false; } };
/* The 관심 그룹 picker is the template's (KH.watch.pick, §3-11): one implementation for the map's ☆, the tooltip and this page — rows
   with check boxes and counts (ticks apply at once), ＋ 새 그룹에 담기, 완료; a bottom sheet up to 760px; Esc · a tap outside · Tab
   out closes it and focus goes back to ☆. Opened from here it moves into this dialog (the rest of the page is inert) and sits above
   it. 'sp-gp' tags its parts for the stock page's tests. */
const pickApi = () => { const W = groupsApi(); return W && typeof W.pick === 'function' ? W : null; };
const pickOpen = () => { const W = pickApi(); return !!(W && typeof W.pickOpen === 'function' && W.pickOpen()); };
const pickClose = restore => { const W = pickApi(); if (W && typeof W.pickClose === 'function') W.pickClose(restore); };
function gpName() { const st = KH.stock(S.code); return (S.sum && S.sum.code === S.code && S.sum.name) || (st && st.n) || S.code; }
function toggleWatch() {
  const W = watchApi();
  if (!W || !S.code) return;
  if (usePicker() && pickApi()) { W.pick(S.code, R.star, { name: gpName(), cls: 'sp-gp' }); renderStar(); return; }
  W.toggle(S.code);
  renderStar();
}

function chip(text, live) { return h('span', { class: 'sp-chip' + (live ? ' live' : '') }, h('i', { 'aria-hidden': 'true' }), text); }

function renderMeta() {
  const kids = [];
  if (!LIVE) {
    kids.push(chip('스냅샷'), h('span', { text: `네이버 증권 · ${asOfLabel(KH.asOf())} 기준` }));
  } else {
    const ph = PHASE[S.phase] || PHASE.unknown;
    if (ph.chip) kids.push(chip(ph.chip, ph.live));
    const q = headQuote(), at = q && isFinite(q.ts) ? new Date(q.ts).toISOString() : S.sum && S.sum.asOf;   // the headline's own time
    if (at) kids.push(h('span', { text: `네이버 증권 · ${asOfLabel(at)} 기준` }));
    if (nxtApplies()) kids.push(h('span', { class: 'sp-nxt', title: '정규장(15:30)이 끝난 뒤의 가격이라 NXT와 시간외 거래가 섞여 있어요.', text: 'NXT·시간외 거래 포함' }));
    if (ph.note && S.phase !== 'after') kids.push(h('span', { class: 'sp-phase-note', text: ph.note }));
    if (!S.sum && !S.sumErr) kids.push(skel('14em', '0.9em'));
    if (S.sumErr) {
      kids.push(h('span', { class: 'sp-meta-err', role: 'status' }, S.sumErr.status === 404 ? '이 코드의 종목을 찾지 못했어요.' : '시세 요약을 불러오지 못했어요.',
        retryKey('sum', async () => { const r = await fetchSummary(false); if (r === false) scheduleSummary(); return r; }, applySummary, 'sp-link sp-retry')));
    }
  }
  const al = alertMeta();
  if (al) kids.push(al);
  R.meta.replaceChildren(...kids);
}

function statItem(label, value, extra) { return h('div', { class: 'sp-stat' + (extra ? ' ' + extra : '') }, h('dt', { text: label }), h('dd', { class: 'num' }, value)); }

function renderStats() {
  if (!LIVE) {
    const st = KH.stock(S.code);
    R.stats.hidden = !st;
    if (!st) return;
    R.stats.replaceChildren(
      statItem('시가총액', F.eok(st.cap)), statItem('거래대금', F.eok(st.tv)),
      statItem('거래량', compact(st.v) + '주'), statItem('전일 종가', int(st.p - st.d)));
    return;
  }
  const s = S.sum;
  R.stats.hidden = !s && !!S.sumErr;
  const lbl = [['시가총액'], ['PER'], ['PBR'], ['배당수익률', 'sp-st-dy'], ['외국인 소진율', 'sp-st-fr']];
  if (!s) {
    R.stats.replaceChildren(...lbl.map(([l, c]) => statItem(l, skel('4em', '0.9em'), c)),
      rangeItem('1일 범위', null, skel('100%', '0.9em'), 'd1'), rangeItem('52주 범위', null, skel('100%', '0.9em'), 'w52'));
    return;
  }
  const p = isNum(s.price) ? +s.price : null;
  const prev = isNum(s.prevClose) && +s.prevClose > 0 ? +s.prevClose : sumRef();
  const open = isNum(s.open) && +s.open > 0 ? +s.open : null;
  const d1 = rangeBar('1일', s.low, s.high, p, { ref: prev, open, base: prev });
  const w52 = rangeBar('52주', s.low52, s.high52, p, { base: prev });
  // 시가 in the colour of its move from 전일 종가 (사용자 2026-11-16 10:46 "색상이 들어가야지"); 전일 is the base, so neutral
  const legend = [open != null ? h('span', { class: 'k-open' }, '시가 ', h('b', { class: prev != null ? cls(open - prev) : 'flat', text: int(open) })) : null,
    prev != null ? h('span', { class: 'k-prev', text: `전일 ${int(prev)}` }) : null].filter(Boolean);
  R.stats.replaceChildren(
    statItem('시가총액', isNum(s.marketCap) ? F.eok(+s.marketCap) : '—'),
    statItem('PER', fixed(s.per, 2, '배')),
    statItem('PBR', fixed(s.pbr, 2, '배')),
    statItem('배당수익률', fixed(s.dividendYield, 2, '%'), 'sp-st-dy'),
    statItem('외국인 소진율', fixed(s.foreignRate, 2, '%'), 'sp-st-fr'),
    rangeItem('1일 범위', legend.length && d1 ? legend : null, d1 || '—', 'd1'),
    rangeItem('52주 범위', null, w52 || '—', 'w52'));
}
// 1일·52주 범위: low ─ track (current price dot; on 1일 the move from 전일 종가 is filled and 시가 is a notch) ─ high.
// A price outside the range (NXT after 15:30 against a KRX-only high/low) pins the dot to the end.
function rangeItem(label, legend, value, kind) {
  return h('div', { class: 'sp-stat sp-rng ' + kind },
    h('dt', {}, h('span', { text: label }), legend ? h('small', { class: 'num' }, legend.flatMap((x, i) => (i ? [h('span', { class: 'sr', text: ' · ' }), x] : [x]))) : null),
    h('dd', { class: 'num' }, value));
}
function rangeBar(name, lo, hi, p, { ref, open, base }) {
  if (!isNum(lo) || !isNum(hi) || +lo <= 0 || +hi < +lo || p == null) return null;
  lo = +lo; hi = +hi;
  const pos = v => (hi > lo ? Math.max(0, Math.min(1, (v - lo) / (hi - lo))) : 0.5);
  const at = v => (pos(v) * 100).toFixed(1) + '%';
  const track = h('span', { class: 'track', role: 'img',
    'aria-label': `${name} 최저 ${int(lo)}원, 최고 ${int(hi)}원, 현재가 ${int(p)}원은 아래에서 ${Math.round(pos(p) * 100)}% 위치${ref != null ? `, 전일 종가 ${int(ref)}원` : ''}${open != null ? `, 시가 ${int(open)}원` : ''}` });
  if (ref != null && hi > lo) {
    const a = pos(ref), b = pos(p);
    track.append(h('b', { class: 'fill ' + cls(p - ref), style: `left:${(Math.min(a, b) * 100).toFixed(1)}%;width:${(Math.abs(b - a) * 100).toFixed(1)}%` }),
      h('em', { class: 'tk prev', style: `left:${at(ref)}`, title: `전일 종가 ${int(ref)}` }));
  }
  if (open != null) track.append(h('em', { class: 'tk open', style: `left:${at(open)}`, title: `시가 ${int(open)}` }));
  // colour (사용자 2026-11-16 10:46): 최저 · 최고 and the current-price dot in the colour of their move from 전일 종가 (base) — the
  // Korean apps' 저가 파랑 · 고가 빨강 read, in the user's palette; no base → neutral
  const tone = v => (base != null && base > 0 ? cls(v - base) : 'flat');
  track.append(h('i', { class: 'dot ' + tone(p), style: `left:${at(p)}` }));
  return [h('span', { class: 'lo ' + tone(lo), text: int(lo) }), track, h('span', { class: 'hi ' + tone(hi), text: int(hi) })];
}

// 같은 업종: Naver's 동일업종 list from /summary (peers, AGENTS.md §3-3) once it is there; until then, in the snapshot and
// when the summary has none, the heatmap's own 업종 (largest first).
function peerItems() {
  const s = S.sum;
  if (LIVE && s && s.code === S.code && Array.isArray(s.peers)) {
    const list = s.peers.filter(x => x && CODE_RE.test(String(x.code || '')) && x.code !== S.code && x.name).slice(0, 6)
      .map(x => ({ c: String(x.code), n: String(x.name), p: isNum(x.price) ? +x.price : null, r: isNum(x.ratio) ? +x.ratio : null }));
    if (list.length) return list;
  }
  const st = KH.stock(S.code);
  return st && st.s ? KH.stocks().filter(x => x.s === st.s && x.i === st.i && x.c !== st.c && x.c.slice(-1) === '0').sort((a, b) => b.cap - a.cap).slice(0, 12)
    .map(x => ({ c: x.c, n: x.n, p: isNum(x.p) ? +x.p : null, r: isNum(x.r) ? +x.r : null })) : [];
}
// §3-13: a vertical mini candle (today's open/high/low/now) in the 10px slot left of the name. On the map: KH.ohlc(code);
// otherwise the raw /api/quotes row fetched for it (R.peerRows). Nothing is drawn without the helpers or without a value.
function peerCandle(slot, code) {
  let el = null;
  try {
    if (typeof KH.ohlc === 'function' && typeof KH.candleIcon === 'function') {
      const o = KH.stock(code) ? KH.ohlc(code) : R.peerRows && R.peerRows.has(code) ? KH.ohlc(R.peerRows.get(code)) : null;
      el = o ? KH.candleIcon(o) : null;
    }
  } catch (e) { el = null; }
  if (el) { if (slot.firstChild !== el) slot.replaceChildren(el); } else slot.replaceChildren();
}
// peers that are not on the map: their rows come from /api/quotes?codes= once per opened stock (live only, at most 6)
async function peerFetchRows(list) {
  if (!LIVE || typeof KH.ohlc !== 'function' || typeof KH.candleIcon !== 'function') return;
  const code = S.code;
  const want = list.filter(x => !KH.stock(x.c)).map(x => x.c).slice(0, 6);
  if (!want.length) return;
  const key = code + '|' + want.join();
  if (R.peerRowsFor === key) return;
  R.peerRowsFor = key;
  if (R.peerRowsCode !== code) { R.peerRows = null; R.peerRowsCode = code; }
  const ac = new AbortController(), killer = setTimeout(() => ac.abort(), 8000);
  try {
    const res = await fetch('api/quotes?codes=' + want.join(','), { cache: 'no-store', signal: ac.signal });
    if (!res.ok) return;
    const raw = await res.json();
    if (S.code !== code) return;
    R.peerRows = new Map(((raw && raw.stocks) || []).filter(x => x && x.c).map(x => [String(x.c), x]));
    try { if (KH.quotes && typeof KH.quotes.put === 'function') KH.quotes.put((raw && raw.stocks) || [], raw && raw.asOf); } catch (e) { /* the list keeps its own rows */ }
    if (S.open && R.peerList) peerItems().forEach((x, i) => { const b = R.peerList.children[i]; if (b && b.dataset.code === x.c) peerCandle(b.children[0], x.c); });
  } catch (e) { /* no icons for these; the list itself is fine */ } finally { clearTimeout(killer); }
}
function peerFill(b, x) {
  peerCandle(b.children[0], x.c);
  b.children[2].textContent = x.p != null ? int(x.p) : '';
  b.children[3].className = 'num pc ' + cls(x.r);
  b.children[3].textContent = pct(x.r);
  b.setAttribute('aria-label', `${x.n}${x.p != null ? ` ${int(x.p)}원` : ''} ${pct(x.r)} 보기`);
}
function renderPeers() {
  const list = peerItems();
  R.peers.hidden = !list.length;
  const key = list.map(x => x.c).join(',');
  if (!list.length) { R.peers.replaceChildren(); R.peerKey = ''; return; }
  if (key === R.peerKey && R.peerList && R.peers.contains(R.peerList)) {   // same stocks: new numbers in place (keeps focus)
    list.forEach((x, i) => peerFill(R.peerList.children[i], x));
    return;
  }
  R.peerKey = key;
  R.peerList = h('div', { class: 'sp-peer-list' }, list.map(x => {
    const b = h('button', { type: 'button', class: 'sp-peer', 'data-code': x.c, onclick: () => open(x.c) },
      h('span', { class: 'pk', 'aria-hidden': 'true' }), h('span', { class: 'nm', text: x.n }), h('span', { class: 'num pr' }), h('span', { class: 'num pc' }));
    peerFill(b, x);
    return b;
  }));
  R.peers.replaceChildren(h('h2', { class: 'sp-peers-t', text: '같은 업종' }), R.peerList);
  peerFetchRows(list);
}

function renderOffline() {
  const st = KH.stock(S.code);
  const href = KH.LIVE_URL + '#s-' + S.code;
  R.offline.replaceChildren(
    svg('svg', { class: 'sp-off-ic sp-ic', viewBox: '0 0 48 48', 'aria-hidden': 'true' },
      svg('path', { d: 'M6 40h36' }), svg('path', { d: 'M12 30v-8M12 34v-2M20 26V12M20 30v-2M28 32V20M28 36v-2M36 22v-12M36 26v-2' })),
    h('h2', { text: st ? '차트·호가·투자자 정보는 실시간 버전에서 볼 수 있어요' : '이 종목은 스냅샷에 없어요' }),
    h('p', { text: st ? `이 화면은 ${asOfLabel(KH.asOf())} 기준 스냅샷이라 새 시세를 받아 오지 않아요. 종목 정보(재무·애널리스트 의견), 일별 시세, 뉴스·공시도 실시간 버전에 있어요.` : `코드 ${S.code}의 시세는 실시간 버전에서 확인해 주세요.` }),
    h('a', { class: 'sp-btn pri', href, target: '_blank', rel: 'noopener', text: '실시간 버전에서 열기' }));
}

/* ───────────────── summary ───────────────── */
// → true (arrived) / false (failed) / null (another stock, aborted)
async function fetchSummary(quiet) {
  const g = S.gen;
  clearTimeout(S.timers.sum);
  try {
    const j = await api('summary', 'sum');
    if (g !== S.gen) return null;
    S.sum = j; S.sumErr = null; failed.delete('sum');
    feedStore(j);
    return true;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    if (!quiet || !S.sum) S.sumErr = e;
    return false;
  }
}
async function loadSummary(quiet) {
  if ((await fetchSummary(quiet)) === null) return;
  applySummary();
}
function applySummary() {
  const before = S.phase;
  S.phase = phaseOf(S.sum);
  root.classList.toggle('sp-nf', !!(S.sumErr && S.sumErr.status === 404 && !KH.stock(S.code)));
  renderHead(); renderMeta(); renderStats(); renderPeers();
  syncChartRef();
  if (before !== S.phase) scheduleIntraday();
  for (const t of TABS) if (t.summary) t.summary(before !== S.phase);
  scheduleSummary();
}
function scheduleSummary() {
  clearTimeout(S.timers.sum);
  if (LIVE && S.open && document.visibilityState === 'visible' && (PHASE[S.phase] || {}).live) S.timers.sum = setTimeout(() => loadSummary(true), SUMMARY_MS);
}

/* ───────────────── chart ───────────────── */
let lwcPromise = null;
function loadLWC() {
  if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
  if (lwcPromise) return lwcPromise;
  lwcPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = LWC_SRC; s.async = true; s.crossOrigin = 'anonymous'; s.integrity = LWC_SRI;
    s.onload = () => (window.LightweightCharts ? resolve(window.LightweightCharts) : reject(new Error('Lightweight Charts missing')));
    s.onerror = () => { s.remove(); lwcPromise = null; reject(new Error('Lightweight Charts load failed')); };
    document.head.append(s);
  });
  return lwcPromise;
}

const C = { chart: null, candles: null, vol: null, ma: null, prevLine: null, bars: null, index: new Map(), tf: null, ref: null, cache: new Map(), ws: 0, warm: 0, canBack: false, more: true, iv: false };
const timeKey = t => (t && typeof t === 'object' ? `${t.year}-${pad(t.month)}-${pad(t.day)}` : t);
function timeParts(t) {
  if (typeof t === 'number') { const d = new Date(t * 1000); return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), wd: d.getUTCDay(), hh: d.getUTCHours(), mm: d.getUTCMinutes() }; }
  const [y, m, d] = typeof t === 'string' ? t.split('-').map(Number) : [t.year, t.month, t.day];
  return { y, m, d, wd: new Date(Date.UTC(y, m - 1, d)).getUTCDay(), hh: 0, mm: 0 };
}
function timeLabel(t, tf) {
  const p = timeParts(t);
  switch (tf || C.tf) {
    case '1m': case '5m': case '10m': case '30m': case '60m': return `${p.m}월 ${p.d}일 (${WD[p.wd]}) ${pad(p.hh)}:${pad(p.mm)}`;
    case 'week': { const q = p.wd === 0 ? timeParts(new Date(Date.UTC(p.y, p.m - 1, p.d + 1)).toISOString().slice(0, 10)) : p; return `${q.y}.${pad(q.m)}.${pad(q.d)} 주`; }   // Naver weeks start on Sunday
    case 'month': return `${p.y}년 ${p.m}월`;
    case 'year': return `${p.y}년`;
    default: return `${p.y}.${pad(p.m)}.${pad(p.d)} (${WD[p.wd]})`;
  }
}
function tickLabel(t, type) {
  const p = timeParts(t);
  if (type === 0) return `${p.y}년`;
  if (type === 1) return `${p.m}월`;
  if (type === 2) return `${p.m}/${p.d}`;
  return `${pad(p.hh)}:${pad(p.mm)}`;
}

async function ensureChart() {
  if (C.chart) return;
  const L = await loadLWC();
  if (C.chart) return;
  const font = getComputedStyle(document.body).fontFamily;
  const K = chc();
  const chart = L.createChart(R.chart, {
    autoSize: true,
    layout: { background: { type: L.ColorType.Solid, color: 'rgba(0,0,0,0)' }, textColor: K.text, fontSize: 11, fontFamily: font, attributionLogo: true,   // transparent: the .sp-chartwrap card is the ground
      panes: { separatorColor: K.sep, separatorHoverColor: K.sepHover, enableResize: false } },
    grid: { vertLines: { color: K.gridV }, horzLines: { color: K.gridH } },
    crosshair: { mode: L.CrosshairMode.Normal,
      vertLine: { color: K.text, width: 1, style: L.LineStyle.Dashed, labelBackgroundColor: K.tagBg },
      horzLine: { color: K.text, width: 1, style: L.LineStyle.Dashed, labelBackgroundColor: K.tagBg } },
    rightPriceScale: { borderColor: K.line, scaleMargins: { top: 0.16, bottom: 0.06 } },
    timeScale: { borderColor: K.line, rightOffset: 2, fixLeftEdge: true, fixRightEdge: true, lockVisibleTimeRangeOnResize: true, tickMarkFormatter: tickLabel },
    localization: { locale: 'ko-KR', timeFormatter: t => timeLabel(t) },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: false }, axisDoubleClickReset: true },
  });
  const P = KH.palette();
  const candles = chart.addSeries(L.CandlestickSeries, {
    upColor: P.up, downColor: P.down, wickUpColor: P.up, wickDownColor: P.down, borderVisible: false,
    priceFormat: { type: 'custom', formatter: p => F.int(Math.round(p)), minMove: 1 }, priceLineStyle: L.LineStyle.Dotted,
    autoscaleInfoProvider: base => {
      const r = base();
      if (r && C.ref != null) { r.priceRange.minValue = Math.min(r.priceRange.minValue, C.ref); r.priceRange.maxValue = Math.max(r.priceRange.maxValue, C.ref); }
      return r;
    },
  });
  const ma = {};
  for (const n of MA_N) ma[n] = { series: chart.addSeries(L.LineSeries, { color: K.ma[n], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, visible: false, title: '' }), vals: [] };
  const vol = chart.addSeries(L.HistogramSeries, { priceFormat: { type: 'custom', formatter: v => compact(v), minMove: 1 }, priceLineVisible: false, lastValueVisible: false,
    // opening and closing auctions dwarf the 1-minute bars; clip them so the rest stays readable (the legend shows the real number)
    autoscaleInfoProvider: base => { const r = base(); if (r && C.volCap) r.priceRange.maxValue = Math.min(r.priceRange.maxValue, C.volCap); return r; } }, 1);
  vol.priceScale().applyOptions({ scaleMargins: { top: 0.18, bottom: 0 } });
  const panes = chart.panes();
  panes[0].setStretchFactor(4);
  if (panes[1]) panes[1].setStretchFactor(1);
  new ResizeObserver(() => { cancelAnimationFrame(C.raf); C.raf = requestAnimationFrame(fitMargins); }).observe(R.chart);
  chart.subscribeCrosshairMove(param => {
    const i = param && param.point && param.time != null ? C.index.get(timeKey(param.time)) : undefined;
    renderLegend(i); renderMa(i);
  });
  chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
  Object.assign(C, { chart, candles, vol, ma, L });
  applyMaVisibility();
}

function sanitize(raw, intraday) {
  const out = new Map();
  for (const b of raw || []) {
    if (!b || !isNum(b.c)) continue;
    const t = intraday ? (isNum(b.t) ? +b.t + KST : null) : (/^\d{4}-\d{2}-\d{2}$/.test(b.t) ? b.t : null);
    if (t == null) continue;
    const c = +b.c, o = isNum(b.o) && +b.o > 0 ? +b.o : c;
    const hi = Math.max(isNum(b.h) && +b.h > 0 ? +b.h : c, o, c), lo = Math.min(isNum(b.l) && +b.l > 0 ? +b.l : c, o, c);
    out.set(t, { time: t, o, h: hi, l: lo, c, v: isNum(b.v) ? +b.v : 0 });
  }
  return [...out.values()].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}
function candleData(bars) { const FLAT = chc().flat; return bars.map(b => b.c === b.o ? { time: b.time, open: b.o, high: b.h, low: b.l, close: b.c, color: FLAT, wickColor: FLAT } : { time: b.time, open: b.o, high: b.h, low: b.l, close: b.c }); }
function candleSet(bars, tf) {
  const cdata = candleData(bars);
  if (tf === '1m' && S.phase === 'open') {
    // leave room for the rest of the regular session (until 15:30 KST)
    const last = bars[bars.length - 1].time, p = timeParts(last);
    const end = Date.UTC(p.y, p.m - 1, p.d, 15, 30) / 1000;
    for (let t = last + 60; t <= end; t += 60) cdata.push({ time: t });
  }
  return cdata;
}
function volData(bars) {
  const P = KH.palette(), up = hexRgba(P.up, 0.55), dn = hexRgba(P.down, 0.55), fl = hexRgba(chc().flat, 0.45);
  return bars.map(b => ({ time: b.time, value: b.v, color: b.c > b.o ? up : b.c < b.o ? dn : fl }));
}

function chartState(kind, err) {
  const m = R.chartMsg;
  m.className = 'sp-chartmsg';
  if (kind === 'ok') { m.replaceChildren(); return; }
  m.classList.add('on');
  if (kind === 'loading') {
    if (C.bars && C.bars.length) { m.classList.add('dim'); m.replaceChildren(h('span', { class: 'sp-loading-t', role: 'status', text: '불러오는 중…' })); }
    else { m.classList.add('skel'); m.replaceChildren(h('div', { class: 'sp-chart-skel', role: 'status', 'aria-label': '차트 불러오는 중' }, Array.from({ length: 28 }, (_, i) => h('i', { style: `height:${18 + Math.round(Math.abs(Math.sin(i * 1.7)) * 46)}%` })))); }
  } else if (kind === 'error') m.replaceChildren(msgBox('차트를 불러오지 못했어요.', errSub(err), retryKey('chart', chartFetch, () => loadChart())));
  else if (kind === 'lib') m.replaceChildren(msgBox('차트 도구를 불러오지 못했어요.', '네트워크 연결을 확인하고 다시 시도해 주세요.', retryKey('chart', chartFetch, () => loadChart())));
  else if (kind === 'empty') {
    const pre = (S.tf === '1m') && S.phase === 'pre';
    m.replaceChildren(msgBox(pre ? '오늘은 아직 거래가 없어요.' : '이 기간에는 거래 기록이 없어요.', pre ? '9시에 정규장이 열리면 차트가 그려져요.' : '다른 기간을 골라 보세요.'));
  }
}

/* Bars come from `chart?iv=…&count=N&warm=119[&to=…]` (AGENTS §3). A Worker that does not know iv= (a 400, or the old tf-shaped answer)
 * is remembered for the session and every interval then uses the old tf= form: no scroll-back, lines simply start later.
 * 10분 · 30분 · 60분 (the Worker groups 5-minute bars): a Worker from before them answers 400 to iv=10m — the page and the Worker deploy
 * minutes apart — so that is remembered too and those intervals take its 5-minute bars (iv=5m, or tf=5d) and group them here, with the
 * same groupBars as the Worker. Scroll-back still works then (to= on the 5-minute bars). */
let IV_OK = null, IV_GROUPED = null;   // null: not known yet
async function fetchIv(iv, count, warm, to) {   // → the answer (marked _iv), or null when this Worker does not know `iv`
  try {
    const j = await api(`chart?iv=${iv}&count=${count}&warm=${warm}` + (to ? `&to=${to}` : ''), 'chart');
    if (j && Array.isArray(j.bars) && j.iv === iv) { j._iv = true; return j; }
    return null;   // answered in the old shape
  } catch (e) {
    if (aborted(e) || !(e && (e.status === 400 || e.status === 404))) throw e;
    return null;
  }
}
async function fetchBars(tf, o) {
  o = o || {};
  const warm = o.warm != null ? o.warm : (tf === 'year' ? 0 : WARM);
  const [iv, count] = IV_REQ[tf], n = IV_GROUP[iv], want = o.count || count;
  if (IV_OK !== false) {
    if (!n || IV_GROUPED !== false) {
      const j = await fetchIv(iv, want, warm, o.to);
      if (j) { IV_OK = true; if (n) IV_GROUPED = true; return j; }
      if (n) IV_GROUPED = false; else IV_OK = false;
    }
    if (n && IV_OK !== false) {
      const j5 = await fetchIv('5m', Math.min(1500, (want + warm + 1) * n / 5), 0, o.to);
      if (j5) { IV_OK = true; return regroup(j5, iv, n, want, warm); }
      IV_OK = false;
    }
  }
  if (o.to) return { bars: [], more: false, _iv: false };
  const j = await api('chart?tf=' + IV_OLD[tf] + '&warm=' + warm, 'chart');
  j._iv = false;
  return n ? regroup(j, iv, n, want, warm) : j;
}
/* 5-minute bars → n-minute bars: the same rules as the Worker's groupBars (worker/src/index.js) — Naver stamps a bar with its first minute;
 * buckets on the clock grid from 09:00 KST; the closing print (15:30, 16:30 on a late day) closes the last regular bucket; after-hours
 * buckets start at the session end. `bars`: {t: unix s, o, h, l, c, v}. */
function groupBars(bars, n) {
  const late = new Set(), out = [];
  bars = bars.filter(b => b && isNum(b.c) && isNum(b.t)).sort((a, b) => a.t - b.t);
  for (const b of bars) { const k = b.t + KST, m = Math.floor((k % 86400) / 60); if (m === 920 || m === 925) late.add(Math.floor(k / 86400)); }
  let cur = null;
  for (const b of bars) {
    const k = b.t + KST, day = Math.floor(k / 86400), m = Math.floor((k % 86400) / 60), end = late.has(day) ? 990 : 930;
    const s = m < end ? m - (m % n) : m === end ? (end - 1) - ((end - 1) % n) : Math.max(end, m - (m % n));
    const t = day * 86400 + s * 60 - KST;
    const c = +b.c, o = isNum(b.o) ? +b.o : c, hi = Math.max(isNum(b.h) ? +b.h : c, o, c), lo = Math.min(isNum(b.l) ? +b.l : c, o, c);
    if (cur && cur.t === t) { cur.h = Math.max(cur.h, hi); cur.l = Math.min(cur.l, lo); cur.c = c; cur.v += isNum(b.v) ? +b.v : 0; }
    else { cur = { t, o, h: hi, l: lo, c, v: isNum(b.v) ? +b.v : 0 }; out.push(cur); }
  }
  return out;
}
// an answer of 5-minute bars → the shape the Worker gives for `iv` (count bars, up to `warm` of pre, prevClose, more)
function regroup(j, iv, n, count, warm) {
  const src = (j.pre || []).concat(j.bars || []);
  const g = groupBars(src, n);
  const first = src.filter(b => b && isNum(b.c) && isNum(b.t)).reduce((a, b) => Math.min(a, b.t), Infinity);
  // the first bucket may have lost its start to the window edge: drop it unless nothing older exists
  const cut = g.length > 1 && first !== g[0].t && (j.more !== false || !j._iv) ? g.shift() : null;
  const bars = g.slice(Math.max(0, g.length - count)), rest = g.slice(0, Math.max(0, g.length - count));
  const out = { iv, interval: iv, bars, more: !!j._iv && (j.more !== false || rest.length > warm), _iv: !!j._iv, _grouped: true,
    prevClose: rest.length ? rest[rest.length - 1].c : cut ? cut.c : isNum(j.prevClose) ? +j.prevClose : null };
  if (warm) out.pre = rest.slice(-warm);
  return out;
}
// the retry key's fetch: the chart tool and this interval's bars into the cache, nothing drawn (loadChart() then draws from the cache)
async function chartFetch() {
  const g = S.gen, tf = S.tf, code = S.code;
  try { await ensureChart(); } catch (e) { return g === S.gen ? false : null; }
  if (g !== S.gen || tf !== S.tf) return null;
  try {
    const j = await fetchBars(tf);
    if (g !== S.gen || tf !== S.tf) return null;
    C.cache.set(code + '|' + tf, { at: Date.now(), j });
    failed.delete('chart');
    return true;
  } catch (e) { return aborted(e) || g !== S.gen ? null : false; }
}
function clearSeries() {
  C.bars = null; C.index = new Map(); C.candles.setData([]); C.vol.setData([]);
  for (const n of MA_N) C.ma[n].series.setData([]);
  showNote('');
  renderLegend(); renderMa(); renderPeriod();
}
async function loadChart(force) {
  const g = S.gen, tf = S.tf, code = S.code;
  const key = code + '|' + tf;
  if (C.code !== code) C.bars = null;   // old candles stay under a dim overlay only while the same stock changes interval
  chartState('loading');
  try { await ensureChart(); } catch (e) { if (g === S.gen && tf === S.tf) chartState('lib'); return; }
  if (g !== S.gen || tf !== S.tf) return;
  const hit = C.cache.get(key);
  let j = !force && hit && Date.now() - hit.at < (isMin(tf) ? 20e3 : 600e3) ? hit.j : null;
  if (!j) {
    try { j = await fetchBars(tf); } catch (e) {
      if (aborted(e) || g !== S.gen || tf !== S.tf) return;
      clearSeries();
      chartState('error', e); return;
    }
    if (g !== S.gen || tf !== S.tf) return;
    C.cache.set(key, { at: Date.now(), j });
  }
  setChartData(j, code, tf, false);
  scheduleIntraday();
}

/* References.
 * 전일 종가 (the dashed line on 1일·5일, and the base of the 1일 change) is the KRX 기준가 that the header and the order
 * book use: price − change from /summary. The chart API's prevClose is the close of the bar *before the first bar*
 * (for 1d the previous day's KRX+NXT close, which can differ from 기준가), so it only serves as the period's base. */
function sumRef() {
  const s = S.sum;
  return s && s.code === S.code && isNum(s.price) && isNum(s.change) && +s.price - +s.change > 0 ? +s.price - +s.change : null;
}
const dayOf = t => Math.floor(t / 86400);   // intraday times are KST-shifted seconds
function lastDayStart(bars, days) {   // index of the first bar of the last `days` (default 1) trading days
  let i = bars.length - 1, d = dayOf(bars[i].time), n = days || 1;
  for (; i > 0; i--) { const e = dayOf(bars[i - 1].time); if (e !== d) { if (--n <= 0) break; d = e; } }
  return i;
}
function computeRefs() {
  const bars = C.bars || [];
  const ld = C.intraday && bars.length ? lastDayStart(bars) : 0;
  C.ref = C.intraday ? (sumRef() != null ? sumRef() : C.tf === '1m' ? (ld > 0 ? bars[ld - 1].c : C.base) : null) : null;
  // the legend's % per bar: intraday → that day's previous close (today's = 전일 종가); otherwise → the previous bar
  const refs = new Array(bars.length);
  const lastDay = C.intraday && bars.length ? dayOf(bars[bars.length - 1].time) : null;
  let day = null, ref = C.base;
  for (let i = 0; i < bars.length; i++) {
    if (!C.intraday) { refs[i] = i ? bars[i - 1].c : C.base; continue; }
    const d = dayOf(bars[i].time);
    if (d !== day) { day = d; ref = i ? bars[i - 1].c : C.base; }
    refs[i] = d === lastDay && C.ref != null ? C.ref : ref;
  }
  C.refs = refs;
}
function drawRefLine() {
  if (C.prevLine) { C.candles.removePriceLine(C.prevLine); C.prevLine = null; }
  if (C.ref != null && C.bars && C.bars.length) C.prevLine = C.candles.createPriceLine({ price: C.ref, color: chc().flat, lineWidth: 1, lineStyle: C.L.LineStyle.Dashed, axisLabelVisible: true, title: '전일 종가', axisLabelColor: chc().tagBg, axisLabelTextColor: chc().tagFg });
}
// the last-price label follows the day's change (as in the header), not the last candle's own colour
function lastColor() {
  const d = S.sum && S.sum.code === S.code && isNum(S.sum.change) ? +S.sum.change : null;
  if (d == null) return '';
  const P = KH.palette();
  return d > 0 ? P.up : d < 0 ? P.down : chc().flat;
}
// /summary arrived or changed after the candles: move the 전일 종가 line and the legend onto 기준가
function syncChartRef() {
  if (!C.chart || C.code !== S.code) return;
  C.candles.applyOptions({ priceLineColor: lastColor() });
  if (!C.bars || !C.bars.length) return;
  const before = C.ref;
  computeRefs();
  if (C.ref !== before) drawRefLine();
  renderLegend(); renderPeriod();
}

/* ── bars → everything drawn ──
 * C.bars holds every loaded bar: `pre` (warm-up, only so the averages are complete) + the window + whatever scroll-back added. The
 * visible range starts at the window (C.ws), so the lines are complete from the first visible bar and the user can still drag left. */
function toYears(bars) {   // monthly → yearly: first open, highest high, lowest low, last close, summed volume
  const m = new Map();
  for (const b of bars) {
    const y = String(b.time).slice(0, 4), a = m.get(y);
    if (!a) m.set(y, { time: y + '-01-01', o: b.o, h: b.h, l: b.l, c: b.c, v: b.v });
    else { a.h = Math.max(a.h, b.h); a.l = Math.min(a.l, b.l); a.c = b.c; a.v += b.v; }
  }
  return [...m.values()];
}
function mergeBars(a, b) {   // by time; b wins
  const m = new Map();
  for (const x of a) m.set(x.time, x);
  for (const x of b) m.set(x.time, x);
  return [...m.values()].sort((x, y) => (x.time < y.time ? -1 : x.time > y.time ? 1 : 0));
}
function windowStart(bars, tf) {   // first index of the default visible window
  if (!bars.length) return 0;
  if (isMin(tf)) return lastDayStart(bars, IV_DAYS[tf]);
  if (tf === 'year') return 0;
  const last = String(bars[bars.length - 1].time).split('-').map(Number);
  const cut = new Date(Date.UTC(last[0], last[1] - 1 - IV_MONTHS[tf], last[2])).toISOString().slice(0, 10);
  const i = bars.findIndex(b => b.time >= cut);
  return i < 0 ? 0 : i;
}
function computeMa() {
  const bars = C.bars || [];
  for (const n of MA_N) {
    const vals = new Array(bars.length).fill(null), data = [];
    let sum = 0;
    for (let i = 0; i < bars.length; i++) {
      sum += bars[i].c;
      if (i >= n) sum -= bars[i - n].c;
      if (i >= n - 1) { vals[i] = sum / n; data.push({ time: bars[i].time, value: vals[i] }); }
    }
    C.ma[n].vals = vals;
    C.ma[n].series.setData(data);
  }
}
// state for the QA scripts: bars loaded, first visible bar, first bar where the 120-bar average exists
function markChart() {
  if (!R.chart || !C.ma) return;
  R.chart.dataset.n = String(C.bars ? C.bars.length : 0); R.chart.dataset.ws = String(C.ws);
  R.chart.dataset.ma120 = String(C.ma[120].vals.findIndex(v => v != null)); R.chart.dataset.back = C.canBack ? '1' : '0';
}
function setChartData(j, code, tf, keepRange) {
  const intraday = isMin(tf);
  const range = keepRange ? C.chart.timeScale().getVisibleLogicalRange() : null;
  let pre = sanitize(j && j.pre, intraday), win = sanitize(j && j.bars, intraday);
  const same = keepRange && C.code === code && C.tf === tf && C.bars && C.bars.length;
  const oldLen = same ? C.bars.length : 0;
  let all = pre.concat(win);
  if (tf === 'year') all = toYears(all);
  if (same) all = mergeBars(C.bars, all);   // a refresh keeps what scroll-back already loaded
  const grown = same ? all.length - oldLen : 0;
  if (!same) { C.warm = tf === 'year' ? 0 : pre.length; C.more = j && j.more !== false; C.canBack = !!(j && j._iv && tf !== 'year' && C.more); C.iv = !!(j && j._iv); C.noteOk = C.iv && j.more === false; }
  C.code = code; C.tf = tf; C.bars = all; C.intraday = intraday;
  C.ws = same ? C.ws : windowStart(all, tf);
  C.base = same ? C.base : (pre.length || tf === 'year' ? null : (isNum(j && j.prevClose) && +j.prevClose > 0 ? +j.prevClose : null));
  computeRefs();
  C.index = new Map(all.map((b, i) => [b.time, i]));
  C.volCap = 0;
  if (intraday && all.length > 40) {
    const v = all.map(b => b.v).sort((a, b) => a - b), cap = v[Math.floor(v.length * 0.97)] * 1.8;
    if (cap > 0 && v[v.length - 1] > cap) C.volCap = cap;
  }
  if (C.prevLine) { C.candles.removePriceLine(C.prevLine); C.prevLine = null; }
  C.candles.applyOptions({ priceLineColor: lastColor() });
  C.chart.applyOptions({ timeScale: { timeVisible: intraday, secondsVisible: false } });
  if (!all.length) {
    clearSeries(); chartState('empty');
    R.chart.setAttribute('aria-label', `${TF_NAME[tf]} 차트: 거래 기록이 없어요`);
    return;
  }
  const cs = candleSet(all, tf);
  C.candles.setData(cs);
  C.vol.setData(volData(all));
  computeMa(); markChart(); syncMaChips();
  drawRefLine();
  if (range) C.chart.timeScale().setVisibleLogicalRange({ from: range.from, to: range.to });
  else C.chart.timeScale().setVisibleLogicalRange({ from: C.ws - 0.5, to: cs.length - 1 + 2 });
  chartState('ok');
  renderLegend(); renderMa(); renderPeriod(); fitMargins();
  const first = all[C.ws], last = all[all.length - 1];
  R.chart.setAttribute('aria-label', `${R.name.textContent} ${TF_NAME[tf]}봉 차트. ${timeLabel(first.time, tf)} ${int(first.o)}원에서 ${timeLabel(last.time, tf)} ${int(last.c)}원까지, 봉 ${all.length - C.ws}개.`);
  void grown;
}

/* scroll-back: when the left edge of the loaded bars (past the warm-up) comes near, load the bars before them and prepend */
function showNote(t) { if (R.note && R.note.textContent !== t) { R.note.textContent = t; R.note.classList.toggle('on', !!t); } }
function onRange(r) {
  if (!r || !C.bars || !C.bars.length) return;
  if (C.canBack && !C.loadingOlder && r.from < C.warm + 25) loadOlder();
  else if (!C.canBack && C.noteOk && !C.loadingOlder) showNote(r.from < 2 ? (C.intraday ? '더 이전 분봉은 없어요' : '더 이전 기록은 없어요') : '');
}
function toParam(time) {   // a loaded bar's time → the `to` of the request for the bars before it
  const p = timeParts(time);
  return C.intraday ? `${p.y}${pad(p.m)}${pad(p.d)}${pad(p.hh)}${pad(p.mm)}` : `${p.y}${pad(p.m)}${pad(p.d)}`;
}
async function loadOlder() {
  if (C.loadingOlder || !C.canBack || !C.bars || !C.bars.length || Date.now() < (C.backAt || 0)) return;
  const g = S.gen, tf = S.tf, code = S.code;
  C.loadingOlder = true; showNote('이전 기록 불러오는 중…');
  try {
    const j = await fetchBars(tf, { to: toParam(C.bars[0].time) });
    if (g !== S.gen || tf !== S.tf || C.code !== code) return;
    if (!j._iv) { C.canBack = false; showNote(''); return; }
    const intraday = C.intraday, pre = sanitize(j.pre, intraday), win = sanitize(j.bars, intraday);
    const len = C.bars.length, all = mergeBars(C.bars, pre.concat(win)), k = all.length - len;
    C.more = j.more !== false;
    if (!k || !C.more) { C.canBack = false; C.noteOk = true; }
    if (!k) { showNote(intraday ? '더 이전 분봉은 없어요' : '더 이전 기록은 없어요'); return; }
    const range = C.chart.timeScale().getVisibleLogicalRange();
    C.warm = C.more ? pre.length : 0;
    C.bars = all; C.ws += k;
    computeRefs();
    C.index = new Map(all.map((b, i) => [b.time, i]));
    const cs = candleSet(all, tf);
    C.candles.setData(cs); C.vol.setData(volData(all)); computeMa(); markChart(); syncMaChips(); drawRefLine();
    if (range) C.chart.timeScale().setVisibleLogicalRange({ from: range.from + k, to: range.to + k });
    showNote(''); renderLegend(); renderMa();
  } catch (e) {
    if (!aborted(e)) C.backAt = Date.now() + 5000;   // try again a little later; the picture stays as it is
    showNote('');
  } finally { C.loadingOlder = false; }
}

/* moving averages: which lines are on (per interval; the default is in MA_DEF), the chips, the values under the crosshair */
function maOn(tf) { const v = store.get('stock.ma', null); const a = v && typeof v === 'object' ? v[tf] : null; return Array.isArray(a) ? a : MA_DEF[tf] || []; }
function syncMaChips() {
  if (!R.mac) return;
  const on = maOn(S.tf), unit = IV_UNIT[S.tf];
  R.ma.setAttribute('aria-label', `이동평균, ${IV_BARS[S.tf]} 기준`);
  // the values keep one width while the crosshair moves (the widest price of the loaded bars, tabular digits)
  const top = C.bars && C.bars.length && C.code === S.code ? C.bars.reduce((a, b) => Math.max(a, b.h), 0) : 0;
  const w = top ? F.int(Math.round(top)) : '00,000', dg = w.replace(/\D/g, '').length;
  R.ma.style.setProperty('--ma-vw', `calc(${dg}ch + ${w.length - dg} * .3em)`);
  for (const n of MA_N) {
    const m = R.mac[n], o = on.includes(n);
    m.btn.setAttribute('aria-pressed', String(o));
    m.btn.setAttribute('aria-label', `${n}${unit} 이동평균 선`);   // the state is aria-pressed (켜짐 / 꺼짐), the value is read from the text
    m.btn.title = `${n}${unit} 이동평균 선 ${o ? '끄기' : '켜기'}`;
    if (m.nm.textContent !== n + unit) m.nm.textContent = n + unit;
  }
  fitMa();
}
// the four items stay on one line; where they cannot (a narrow phone, 7-digit prices) each puts its value under its name (.stack).
// The widths only change with the reserved value width, the labels and the screen, so this runs on those, not on every crosshair move.
function fitMa() {
  if (!R.ma || !R.ma.isConnected) return;
  const cs = MA_N.map(n => R.mac[n].btn);
  R.ma.classList.remove('stack');
  if (cs[cs.length - 1].offsetTop > cs[0].offsetTop + 2) R.ma.classList.add('stack');
}
function applyMaVisibility() {
  if (!C.ma) return;
  const on = maOn(S.tf);
  for (const n of MA_N) C.ma[n].series.applyOptions({ visible: on.includes(n) });
}
function toggleMa(n) {
  const on = maOn(S.tf), next = on.includes(n) ? on.filter(x => x !== n) : on.concat(n).sort((a, b) => a - b);
  const v = store.get('stock.ma', null);
  store.set('stock.ma', Object.assign({}, v && typeof v === 'object' ? v : {}, { [S.tf]: next }));
  syncMaChips(); applyMaVisibility(); renderMa();
}
function renderMa(i) {
  if (!R.mac) return;
  const bars = C.bars;
  const idx = bars && bars.length && C.code === S.code ? (i != null && bars[i] ? i : bars.length - 1) : -1;
  for (const n of MA_N) {   // a line that is off keeps its value (muted): the row never changes width when one is toggled
    const v = idx >= 0 && C.ma ? C.ma[n].vals[idx] : null;
    const t = idx < 0 ? '' : v == null ? '–' : F.int(Math.round(v));
    if (R.mac[n].v.textContent !== t) R.mac[n].v.textContent = t;
  }
}

function renderLegend(i) {
  const bars = C.bars;
  if (!R.legend) return;
  if (!bars || !bars.length) { R.legend.replaceChildren(); return; }
  if (i == null || !bars[i]) i = bars.length - 1;
  const b = bars[i];
  const ref = C.refs && C.refs[i] != null ? C.refs[i] : null;
  const r = ref ? (b.c / ref - 1) * 100 : null;
  const kv = (k, v, c) => h('span', { class: 'kv' }, h('em', { text: k }), h('b', { class: c || '', text: v }));
  R.legend.replaceChildren(
    h('span', { class: 'sp-lg-t', text: timeLabel(b.time) }),
    ...(C.tf === 'year' && i === bars.length - 1 && String(b.time).slice(0, 4) === String(kst(new Date()).y) ? [h('span', { class: 'sp-lg-live', text: '진행 중' })] : []),
    r != null ? h('b', { class: 'sp-lg-r ' + cls(r), title: C.intraday ? '전일 종가 대비' : '직전 봉 종가 대비', text: pct(r) }) : null,
    h('span', { class: 'sp-lg-ohlc' }, kv('시', int(b.o)), kv('고', int(b.h)), kv('저', int(b.l)), kv('종', int(b.c), cls(b.c - (ref || b.o)))),
    kv('거래량', compact(b.v), 'vol'));
}
// keep the top of the candles clear of the legend (it wraps to two lines on phones)
function fitMargins() {
  if (!C.chart || !R.legend) return;
  const pane = C.chart.panes()[0], ph = pane && pane.getHeight ? pane.getHeight() : 0;
  if (!ph) return;
  const top = Math.min(0.3, Math.max(0.08, (R.legend.offsetHeight + 16) / ph));
  if (Math.abs(top - (C.top || 0)) > 0.01) { C.top = top; C.candles.priceScale().applyOptions({ scaleMargins: { top, bottom: 0.06 } }); }
}
function renderPeriod() {
  const bars = C.bars;
  if (!R.period) return;
  if (!bars || !bars.length) { R.period.replaceChildren(); return; }
  const last = bars[bars.length - 1].c;
  if (C.tf === '1m' && C.ref != null) {
    const r = (last / C.ref - 1) * 100;
    R.period.replaceChildren(h('span', { text: `전일 종가 ${int(C.ref)} 대비 ` }), h('b', { class: cls(r), text: pct(r) }));
  } else {
    // from the close before the window's first bar (falls back to the first bar's open)
    const base = C.ws > 0 ? bars[C.ws - 1].c : C.base != null ? C.base : bars[C.ws].o, r = (last / base - 1) * 100;
    R.period.replaceChildren(h('span', { text: `${IV_RANGE[C.tf]} 동안 ` }), h('b', { class: cls(r), text: pct(r) }));
  }
}
// kh:palette (data colours) and kh:theme (everything else): hand the chart its colours again, no reload. The flat candles carry their
// own colour per bar, so the series is set again too (same bars, the visible range kept).
function applyColors() {
  CH = null;
  if (!C.candles) return;
  const K = chc(), P = KH.palette();
  C.chart.applyOptions({
    layout: { textColor: K.text, panes: { separatorColor: K.sep, separatorHoverColor: K.sepHover } },
    grid: { vertLines: { color: K.gridV }, horzLines: { color: K.gridH } },
    crosshair: { vertLine: { color: K.text, labelBackgroundColor: K.tagBg }, horzLine: { color: K.text, labelBackgroundColor: K.tagBg } },
    rightPriceScale: { borderColor: K.line }, timeScale: { borderColor: K.line },
  });
  C.candles.applyOptions({ upColor: P.up, downColor: P.down, wickUpColor: P.up, wickDownColor: P.down, priceLineColor: lastColor() });
  for (const n of MA_N) C.ma[n].series.applyOptions({ color: K.ma[n] });
  if (C.bars && C.bars.length) {
    const range = C.chart.timeScale().getVisibleLogicalRange();
    C.candles.setData(candleSet(C.bars, C.tf));
    C.vol.setData(volData(C.bars));
    drawRefLine();
    if (range) C.chart.timeScale().setVisibleLogicalRange(range);
  }
}
function scheduleIntraday() {
  clearTimeout(S.timers.chart);
  if (LIVE && S.open && document.visibilityState === 'visible' && isMin(S.tf) && (S.phase === 'open' || S.phase === 'after'))   // every minute interval follows the session
    S.timers.chart = setTimeout(refreshIntraday, INTRADAY_MS);
}
async function refreshIntraday() {
  const g = S.gen, tf = S.tf, code = S.code;
  if (!C.chart || !isMin(tf)) return;
  try {
    const j = await fetchBars(tf, { count: Math.min(400, IV_REQ[tf][1]), warm: 0 });   // only the newest bars; they are merged into what is loaded
    if (g !== S.gen || tf !== S.tf) return;
    setChartData(j, code, tf, true);
  } catch (e) { /* keep the current picture; try again on the next tick */ }
  if (g === S.gen) scheduleIntraday();
}
function setTf(k) {
  if (!TF_NAME[k]) return;
  ivMenu(false);
  S.tf = k; store.set('stock.iv', k);
  if (isMin(k)) { S.ivMin = k; store.set('stock.ivMin', k); }
  syncTf(); syncMaChips(); applyMaVisibility(); showNote('');
  loadChart();
}
function syncTf() {
  if (!R.tfs) return;
  const min = isMin(S.tf);
  for (const b of segButtons(R.tfs)) b.setAttribute('aria-pressed', String(b.dataset.tf === (min ? 'min' : S.tf)));
  // 분 reads the minute interval that is on ("5분") + a small caret, else "분" + caret; the label changes in place (design.md §6-4)
  swapText(R.minBtn.firstChild, min ? TF_NAME[S.tf] : '분');
  R.minBtn.setAttribute('aria-label', `${min ? IV_BARS[S.tf] : '분봉'}, 간격 고르기`);
  for (const b of ivItems()) b.setAttribute('aria-checked', String(b.dataset.iv === S.tf));
}

/* motion (design.md §6): the spring tokens of the template's :root (--sp-<name> = a linear() curve, --sp-<name>-dur); '줄이기' sets every
 * length to 0 and a hidden tab draws the end state, so both get dur 0 here = no animation at all. */
// one reduce switch (design.md §6-3): html[data-motion] — the template sets it from KH.motion(); either saying 'reduced' is enough
const motionOk = () => !document.hidden && document.documentElement.dataset.motion !== 'reduced' && (typeof KH.motion !== 'function' || KH.motion() !== 'reduced');
const rootVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function spring(name, fbMs) {
  const e = rootVar(`--sp-${name}`), d = parseFloat(rootVar(`--sp-${name}-dur`));
  const easing = e && window.CSS && CSS.supports('transition-timing-function', e) ? e : 'cubic-bezier(.22,1,.36,1)';
  return { easing, dur: motionOk() ? (Number.isFinite(d) ? d : fbMs) : 0 };
}
const TX = { out: 100, gap: 60, in: 180 };   // design.md §6-4: text out 100 ms → 60 ms → in 180 ms (opacity, 2 px blur, 4 px)
/* a label that changes inside its shape (§6-4): the old text (a ::before, so textContent is the new label at every moment) leaves upward
 * with a 2 px blur, the new one comes in from 4 px below 60 ms later — stock.css .sp-tfmin .t.go. 줄이기 / hidden tab: at once. */
function swapText(box, text) {
  const tn = box && box.firstChild;
  if (!tn) return;
  const old = tn.textContent;
  if (old === text) return;
  tn.textContent = text;
  box.classList.remove('go');
  if (!old || !motionOk() || !box.isConnected) { delete box.dataset.was; return; }
  box.dataset.was = old; void box.offsetWidth; box.classList.add('go');
}

/* 분's picker (design.md §7 팝오버 · 고르기): the box grows out of the 분 tab with `open` — from the tab's rect and corner to its own (left ·
 * top · width · height · radius), fading in with `fade`; the items come in once it has grown 25 % (§6-4 in: 180 ms); a highlight plate
 * glides to the hovered (fine pointer) or keyboard-focused item with `hl`. Closing: the items leave first (§6-4 out: 100 ms), then the
 * box shrinks back into the tab with `close`. Menu button + menuitemradio: click / Enter / Space / ↓ opens on the checked item (or the
 * last minute pick), ↑ on the last; ↑ ↓ ← → Home End move, Enter / Space pick; Esc, Tab and a tap outside close, and focus goes back to
 * 분. Below the tab, inside the bar (a 360 px phone never clips it), above it when the screen has no room below. */
const IVM = { st: 'closed', anims: [] };   // st: closed | open | closing
const ivItems = () => (R.ivmIn ? [...R.ivmIn.querySelectorAll('[role="menuitemradio"]')] : []);
function ivWire() {
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  for (const it of ivItems()) {
    // a real move of a mouse (not the box growing under a pointer that rests on 분): the plate follows, the keys go on from there
    it.addEventListener('pointermove', e => {
      if (e.pointerType !== 'mouse' || !fine.matches || IVM.st !== 'open' || R.ivmIn.dataset.hl != null && document.activeElement === it) return;
      ivHl(it, true);
      if (document.activeElement !== it) it.focus({ preventScroll: true });
    });
    it.addEventListener('focus', () => { if (IVM.st === 'open' && it.matches(':focus-visible')) ivHl(it, true); });
  }
  R.ivmIn.addEventListener('pointerleave', e => {
    if (e.pointerType !== 'mouse' || IVM.st !== 'open') return;
    const a = document.activeElement;
    ivHl(a && R.ivmIn.contains(a) && a.matches(':focus-visible') ? a : null, true);
  });
  // will-change only while the plate moves (§6-5: a box with no text)
  const pl = R.ivmHl, off = e => { if (e.propertyName === 'transform') pl.style.willChange = ''; };
  pl.addEventListener('transitionrun', e => { if (e.propertyName === 'transform') pl.style.willChange = 'transform'; });
  pl.addEventListener('transitionend', off); pl.addEventListener('transitioncancel', off);
  const t = R.minBtn.firstChild;
  t.addEventListener('animationend', e => { if (e.target === t.firstChild) { t.classList.remove('go'); delete t.dataset.was; } });
}
function ivHl(it, glide) {
  const pl = R.ivmHl;
  if (!it) { delete R.ivmIn.dataset.hl; return; }
  const snap = !glide || R.ivmIn.dataset.hl == null;   // appearing: in place (fading in), not from where it was last
  if (snap) pl.style.transition = 'opacity var(--sp-fade-dur) var(--sp-fade)';
  pl.style.height = it.offsetHeight + 'px';
  pl.style.transform = `translateY(${it.offsetTop}px)`;
  R.ivmIn.dataset.hl = '';
  if (snap) { void pl.offsetWidth; pl.style.transition = ''; }
}
function ivMenu(open, focusBtn, at) { if (open) ivOpen(at); else ivClose(focusBtn); }
function ivFocus(at) {
  const items = ivItems();
  if (!items.length) return;
  const i = at === 'last' ? items.length - 1 : Math.max(0, items.findIndex(b => b.dataset.iv === (isMin(S.tf) ? S.tf : S.ivMin || '5m')));
  items[i].focus({ preventScroll: true });
  if (items[i].matches(':focus-visible')) ivHl(items[i], false);
}
// geometry in the bar's box (.sp-tfbar is the menu's containing block): the tab, the open menu, the box as it is drawn right now
const px = v => parseFloat(v) || 0;
function ivTab() {
  const bar = R.ivm.parentNode.getBoundingClientRect(), b = R.minBtn.getBoundingClientRect();
  return { l: b.left - bar.left, t: b.top - bar.top, w: b.width, h: b.height, r: Math.min(px(getComputedStyle(R.minBtn).borderTopLeftRadius), b.height / 2), o: 0 };
}
function ivGeom() {
  const m = R.ivm, inn = R.ivmIn, bar = m.parentNode.getBoundingClientRect(), b = R.minBtn.getBoundingClientRect();
  for (const k of ['left', 'top', 'width', 'height', 'borderRadius']) m.style[k] = '';
  inn.style.width = 'max-content';
  const w = Math.min(bar.width, Math.max(Math.ceil(inn.offsetWidth), Math.ceil(b.width), px(rootVar('--space-8')) * 4)), hgt = Math.ceil(inn.offsetHeight);
  const gap = px(rootVar('--space-3')) || 6, below = innerHeight - b.bottom - gap, above = b.top - gap;
  const up = hgt > below && above > below;   // no room under the tab (a short screen, the bar near the bottom): open upward
  return { l: Math.round(Math.max(0, Math.min(b.left - bar.left, bar.width - w))), t: Math.round(up ? b.top - bar.top - gap - hgt : b.bottom - bar.top + gap),
    w, h: hgt, r: px(getComputedStyle(m).borderTopLeftRadius), o: 1, up };
}
function ivNow() {
  const m = R.ivm, bar = m.parentNode.getBoundingClientRect(), r = m.getBoundingClientRect(), cs = getComputedStyle(m);
  return { l: r.left - bar.left, t: r.top - bar.top, w: r.width, h: r.height, r: px(cs.borderTopLeftRadius), o: +cs.opacity };
}
const ivK = g => ({ left: g.l + 'px', top: g.t + 'px', width: g.w + 'px', height: g.h + 'px', borderRadius: g.r + 'px' });
function ivSet(g) {
  const m = R.ivm;
  m.style.left = g.l + 'px'; m.style.top = g.t + 'px'; m.style.width = g.w + 'px'; m.style.height = g.h + 'px';
  R.ivmIn.style.width = g.w + 'px';   // the items keep their final layout while the box grows around them (nothing reflows)
  m.classList.toggle('up', !!g.up);
}
function ivStop() { for (const a of IVM.anims) { try { a.cancel(); } catch (e) { /* gone */ } } IVM.anims = []; clearTimeout(IVM.pe); if (R.ivm) R.ivm.style.pointerEvents = ''; }
function ivOpen(at) {
  if (!R.ivm) return;
  if (IVM.st === 'open') { ivFocus(at); return; }
  const m = R.ivm, from = IVM.st === 'closing' ? ivNow() : null;
  ivStop();
  m.hidden = false; m.inert = false; IVM.st = 'open'; m.dataset.st = 'open';
  R.minBtn.setAttribute('aria-expanded', 'true');
  document.addEventListener('pointerdown', ivOutside, true);
  addEventListener('resize', ivOnResize);
  const g = ivGeom();
  ivSet(g);
  delete R.ivmIn.dataset.hl;
  ivFocus(at);
  const sp = spring('open', 454), fd = spring('fade', 405);
  m.style.pointerEvents = '';
  if (!sp.dur) return;
  const a = from || ivTab();
  // while the box still lies over 분 it lets presses through, so a quick second press on the tab closes it instead of picking an item
  m.style.pointerEvents = 'none';
  clearTimeout(IVM.pe); IVM.pe = setTimeout(() => { if (IVM.st === 'open') m.style.pointerEvents = ''; }, Math.round(sp.dur * 0.35));
  IVM.anims = [
    m.animate([ivK(a), ivK(g)], { duration: sp.dur, easing: sp.easing }),
    m.animate([{ opacity: a.o }, { opacity: 1 }], { duration: fd.dur, easing: fd.easing }),
    // the items wait until the box has grown 25 % (the `open` curve passes .25 at ~11 % of its length)
    R.ivmIn.animate([{ opacity: 0, filter: 'blur(2px)', transform: 'translateY(4px)' }, { opacity: 1, filter: 'blur(0px)', transform: 'translateY(0px)' }],
      { duration: TX.in, delay: Math.round(sp.dur * 0.11), easing: fd.easing, fill: 'backwards' }),
  ];
}
function ivClose(focusBack, instant) {
  if (!R.ivm) return;
  if (IVM.st !== 'open') {
    if (IVM.st === 'closing' && instant) ivEnd();
    if (focusBack && IVM.st !== 'open' && R.minBtn.isConnected) R.minBtn.focus({ preventScroll: true });
    return;
  }
  const m = R.ivm, cur = ivNow(), co = +getComputedStyle(R.ivmIn).opacity;
  ivStop();
  IVM.st = 'closing'; m.dataset.st = 'closing';
  R.minBtn.setAttribute('aria-expanded', 'false');
  document.removeEventListener('pointerdown', ivOutside, true);
  removeEventListener('resize', ivOnResize);
  if (focusBack || m.contains(document.activeElement)) R.minBtn.focus({ preventScroll: true });
  m.inert = true;   // nothing in it can be pressed or focused while it shrinks away
  const sp = spring('close', 254);
  if (instant || !sp.dur) { ivEnd(); return; }
  const to = ivTab();
  IVM.anims = [
    R.ivmIn.animate([{ opacity: co, filter: 'blur(0px)', transform: 'translateY(0px)' }, { opacity: 0, filter: 'blur(2px)', transform: 'translateY(-4px)' }],
      { duration: TX.out, easing: sp.easing, fill: 'forwards' }),
    m.animate([ivK(cur), ivK(to)], { duration: sp.dur, delay: TX.out, easing: sp.easing, fill: 'forwards' }),
    m.animate([{ opacity: cur.o }, { opacity: 0 }], { duration: Math.round(sp.dur * 0.6), delay: TX.out + Math.round(sp.dur * 0.4), easing: sp.easing, fill: 'forwards' }),
  ];
  IVM.anims[1].finished.then(() => { if (IVM.st === 'closing') ivEnd(); }, () => { /* cancelled: reopened */ });
}
function ivEnd() {
  ivStop();
  const m = R.ivm;
  m.hidden = true; m.inert = false; IVM.st = 'closed'; delete m.dataset.st;
  delete R.ivmIn.dataset.hl;
}
function ivOnResize() { if (IVM.st !== 'open') return; ivStop(); ivSet(ivGeom()); const a = document.activeElement; if (R.ivmIn.dataset.hl != null && R.ivmIn.contains(a)) ivHl(a, false); }
// a press outside closes it; focus goes back to 분 unless the press lands on something that takes focus itself (the page's own box,
// which takes it on a press anywhere, does not count)
function ivOutside(e) {
  if (R.ivm.contains(e.target) || R.minBtn.contains(e.target)) return;
  const back = R.ivm.contains(document.activeElement);
  ivClose(false);
  if (!back) return;
  document.addEventListener('click', ivRefocus, true);
  clearTimeout(IVM.rf); IVM.rf = setTimeout(() => document.removeEventListener('click', ivRefocus, true), 1500);
}
function ivRefocus() {
  document.removeEventListener('click', ivRefocus, true);
  const a = document.activeElement;
  if (S.open && (!a || a === document.body || a === root)) R.minBtn.focus({ preventScroll: true });
}
function ivBtnKey(e) {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); ivOpen(e.key === 'ArrowUp' ? 'last' : null); }
}
function ivMenuKey(e) {
  if (IVM.st !== 'open') return;
  const items = ivItems(), i = items.indexOf(document.activeElement);
  let j = null;
  if (e.key === 'ArrowDown' || e.key === 'ArrowRight') j = (i + 1) % items.length;
  else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') j = (i - 1 + items.length) % items.length;
  else if (e.key === 'Home') j = 0;
  else if (e.key === 'End') j = items.length - 1;
  else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); ivClose(true); return; }
  else if (e.key === 'Tab') { e.preventDefault(); ivClose(true); return; }
  else return;
  e.preventDefault();
  items[j].focus({ preventScroll: true });   // (its focus handler moves the plate)
}
function pickMin(k) {
  ivClose(true);
  setTf(k);
}

/* 펼치는 목록 (design.md §7 · §12 ①: 리포트 더 보기 · 재무 표로 보기): only the list's box grows (`open`) — a clip that opens over the new
 * rows — and the content below moves once: at the start when opening, after the box has shrunk (`close`) when closing. The new rows come
 * in once the box is a quarter open (§6-4 in) and leave first, together, when it closes (§6-4 out). Rows that come and go carry
 * .sp-fold-x; apply(want) draws the list in its new state (closing: at the end, so nothing jumps under the reader). 줄이기 / no
 * KH.spring / not laid out: at once. (기업 정보's lists have their own plate, corpToggle — the same rule with a visible plate.) */
const FOLDS = new WeakMap();
function foldMove(box, want, apply, onEnd) {
  const prev = FOLDS.get(box);
  if (prev) prev.finish();
  const ok = KH.spring && typeof KH.spring.animate === 'function' && motionOk() && box.isConnected && box.getClientRects().length > 0;
  if (!ok) { apply(want); if (onEnd) onEnd(); return; }
  const me = { done: false, h: null, t: 0, end: () => {} };
  const finish = () => { if (me.done) return; me.done = true; clearTimeout(me.t); if (me.h) me.h.stop(); FOLDS.delete(box); me.end(); if (onEnd) onEnd(); };
  me.finish = finish; FOLDS.set(box, me);
  const run = (name, frame) => { me.h = KH.spring.animate({ from: 0, to: 1, name, onUpdate: p => { if (!me.done) frame(p); }, onRest: finish }); };
  if (want) {
    const H0 = box.offsetHeight;
    apply(true);                                       // the layout takes its new height here, once
    const D = box.offsetHeight - H0;
    me.end = () => { box.classList.remove('sp-fold-anim', 'sp-fold-fadein'); box.style.clipPath = ''; };
    if (!(D > 0)) { finish(); return; }
    box.classList.add('sp-fold-anim');
    let shown = false;
    const frame = p => { box.style.clipPath = `inset(0 0 ${Math.max(0, (1 - p) * D).toFixed(1)}px 0)`; if (!shown && p >= 0.25) { shown = true; box.classList.add('sp-fold-fadein'); } };
    frame(0);
    run('open', frame);
    return;
  }
  const H1 = box.offsetHeight, x = box.querySelector('.sp-fold-x'), D = H1 - (x ? Math.max(0, x.offsetTop) : 0);
  box.style.height = H1 + 'px';                        // held until the box has shrunk; then the layout comes up once
  box.classList.add('sp-fold-out');
  me.end = () => { box.classList.remove('sp-fold-out'); box.style.clipPath = ''; box.style.height = ''; apply(false); };
  if (!(D > 0)) { finish(); return; }
  me.t = setTimeout(() => { if (!me.done) run('close', p => { box.style.clipPath = `inset(0 0 ${(p * D).toFixed(1)}px 0)`; }); }, TX.out);
}
// after a list folded away, its key may sit under the sticky header: bring it back to the middle
function keepInView(el) {
  if (!el || !el.isConnected) return;
  const r = el.getBoundingClientRect();
  if (r.top < (parseFloat(getComputedStyle(root).getPropertyValue('--sp-hh')) || 0) + 50) el.scrollIntoView({ block: 'center' });
}

/* ───────────────── tabs ───────────────── */
/* The 시세 정보 tabs are a real tablist (aria-selected); KH.ui.seg reads aria-selected too and moves the raised indicator (build()). */
function setTab(k, focus) {
  if (!TAB[k]) k = TABS[0].key;
  const from = S.tab, slide = fancy() && S.open && from !== k && R.panels[from] && !R.panels[from].hidden;
  S.tab = k; store.set('stockTab', k);
  for (const b of segButtons(R.tabs)) {
    const on = b.dataset.tab === k;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
    if (on && focus) b.focus();
  }
  for (const t of TABS) {
    R.panels[t.key].hidden = t.key !== k;
    if (t.key !== k && t.hide) t.hide();
  }
  TAB[k].show(R.panels[k]);
  // 화려하게: the new tab's content comes in on `fade` from 4 px below (all of it at once — no stagger on a frequent switch, design.md §6-2)
  if (slide) { const f = spring('fade', 270); if (f.dur) R.panels[k].animate([{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }], { duration: f.dur, easing: f.easing }); }
}

/* ── 호가 ── */
let obLoop = 0;
const obShouldPoll = () => LIVE && S.open && S.tab === 'ob' && document.visibilityState === 'visible';
const obPolling = () => obShouldPoll() && POLL_PHASES.has(S.phase);   // the book stands still once the market is shut
function obReset() { S.ob = null; S.obErr = null; S.obAt = null; if (R.ob) R.ob.prev = null; }
function obSummary(phaseChanged) {
  if (S.ob) renderOb();   // current-price marker, % and notes follow the summary
  if (!phaseChanged || !obShouldPoll()) return;
  if (POLL_PHASES.has(S.phase)) { if (!S.timers.ob) obStart(); }
  else if (S.timers.ob > 0) { clearTimeout(S.timers.ob); S.timers.ob = 0; }
}
function obStart() {
  obStop();
  if (!obShouldPoll()) return;
  obTick(++obLoop);
}
function obStop() { obLoop++; clearTimeout(S.timers.ob); S.timers.ob = 0; abort('ob'); }
// the retry key's fetch: the polling stops while the key works; a failure picks the 3-second retries up again (they draw the message)
async function obOnce() {
  obStop();
  const id = obLoop;
  try {
    const j = await api('orderbook', 'ob');
    if (id !== obLoop) return null;
    S.ob = j; S.obErr = null; S.obAt = new Date(); failed.delete('ob');
    return true;
  } catch (e) {
    if (aborted(e) || id !== obLoop) return null;
    S.obErr = e;
    if (obPolling()) S.timers.ob = setTimeout(() => obTick(id), OB_MS);
    return false;
  }
}
async function obTick(id) {
  S.timers.ob = 0;
  if (id !== obLoop || !obShouldPoll()) return;
  S.timers.ob = -1;   // in flight
  try {
    const j = await api('orderbook', 'ob');
    if (id !== obLoop) return;
    S.ob = j; S.obErr = null; S.obAt = new Date(); failed.delete('ob');
  } catch (e) {
    if (aborted(e) || id !== obLoop) return;
    S.obErr = e;
  }
  renderOb();
  S.timers.ob = 0;
  if (id === obLoop && obPolling()) S.timers.ob = setTimeout(() => obTick(id), OB_MS);
}

function buildOb(panel) {
  const grid = h('div', { class: 'sp-ob-grid', role: 'table', 'aria-label': '5단계 호가: 매도 잔량, 가격, 매수 잔량' });
  const rows = [];
  for (let i = 0; i < 10; i++) {
    const ask = i < 5, side = ask ? 'ask' : 'bid';
    const q = h('div', { class: 'sp-q ' + side, style: `grid-row:${i + 1}`, role: 'cell' }, h('i', { class: 'bar' }), h('span'));
    const p = h('div', { class: 'sp-p ' + side, style: `grid-row:${i + 1}`, role: 'cell' }, h('b'), h('small'));
    grid.append(q, p);
    rows.push({ q, p });
  }
  const info1 = h('div', { class: 'sp-ob-info top' }), info2 = h('div', { class: 'sp-ob-info bot' });
  grid.append(info1, info2);
  R.ob = { grid, rows, info1, info2, msg: h('div', { class: 'sp-ob-msg' }), note: h('p', { class: 'sp-note' }) };
  panel.append(R.ob.msg, grid, R.ob.note);
}
function obInfo(label, value, c, sub) { return h('div', {}, h('span', { text: label }), h('b', { class: 'num ' + (c || ''), text: value }), sub ? h('small', { text: sub }) : null); }
// a cell whose value changed: a flat ring in the tick's colour that fades (stock.css [data-fl]::before — no wash, no glow, the map's
// tick flash): dir 1 = rose (--up-text), −1 = fell (--dn-text), 0 = neutral (a new price level). The ring's animation ends it.
function flash(el, dir) {
  if (!el.__flEnd) { el.__flEnd = e => { if (e.animationName === 'spFl') delete el.dataset.fl; }; el.addEventListener('animationend', el.__flEnd); el.addEventListener('animationcancel', el.__flEnd); }
  delete el.dataset.fl; void el.offsetWidth;   // the same cell again: the ring starts over
  el.dataset.fl = dir > 0 ? 'up' : dir < 0 ? 'dn' : 'new';
}
function renderOb() {
  const o = S.ob, ob = R.ob;
  if (!ob) return;
  const asks = o ? (o.asks || []).filter(x => x && isNum(x.price)).slice(0, 5) : [];
  const bids = o ? (o.bids || []).filter(x => x && isNum(x.price)).slice(0, 5) : [];
  const has = asks.length + bids.length > 0;
  ob.grid.hidden = !has;
  ob.msg.hidden = has && !S.obErr;
  if (!o) {
    ob.note.replaceChildren();
    ob.msg.replaceChildren(S.obErr ? msgBox('호가를 불러오지 못했어요.', errSub(S.obErr) + (obPolling() ? ' 3초마다 다시 시도해요.' : ''), retryKey('ob', obOnce, () => { renderOb(); if (obPolling()) { const id = obLoop; S.timers.ob = setTimeout(() => obTick(id), OB_MS); } }))
      : h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '호가 불러오는 중' }, Array.from({ length: 10 }, () => skel('100%', '28px'))));
    return;
  }
  if (!has) {
    ob.msg.replaceChildren(msgBox('지금은 호가가 없어요.', '거래가 멈췄거나 장이 열리지 않은 시간일 수 있어요.'));
    ob.note.replaceChildren();
    return;
  }
  if (S.obErr) ob.msg.replaceChildren(h('p', { class: 'sp-inline-err', role: 'status', text: '연결이 잠시 끊겼어요. 마지막으로 받은 호가예요.' }));
  const pc = isNum(o.prevClose) && +o.prevClose > 0 ? +o.prevClose : S.sum && isNum(S.sum.price) ? S.sum.price - S.sum.change : null;
  const cur = S.sum && isNum(S.sum.price) ? +S.sum.price : null;
  const ladder = [];
  for (let i = 4; i >= 0; i--) ladder.push(asks[i] || null);
  for (let i = 0; i < 5; i++) ladder.push(bids[i] || null);
  const max = Math.max(1, ...ladder.filter(Boolean).map(l => +l.qty || 0));
  // where the current price sits: on a level (boxed) or between levels (a line)
  let markIdx = -1, markPos = '', outside = '';
  if (cur != null && !ladder.some(l => l && +l.price === cur)) {
    const prices = ladder.filter(Boolean).map(l => +l.price);
    if (cur > Math.max(...prices)) outside = '보이는 호가보다 높아요';
    else if (cur < Math.min(...prices)) outside = '보이는 호가보다 낮아요';
    else { markIdx = ladder.findIndex(l => l && +l.price < cur); markPos = 'top'; }
  }
  const first = !(ob.prev && ob.prev.code === S.code);   // the first draw of a stock: no flash, and the 잔량 bars are set, not grown (P4)
  const pv = fancy() && !first ? ob.prev.cells : null;
  if (first) { ob.grid.classList.add('now'); requestAnimationFrame(() => requestAnimationFrame(() => ob.grid.classList.remove('now'))); }
  ob.prev = { code: S.code, cells: ladder.map(l => (l ? { price: +l.price, qty: +l.qty || 0 } : null)) };
  ladder.forEach((l, i) => {
    const { q, p } = ob.rows[i];
    const side = i < 5 ? 'ask' : 'bid';
    q.firstChild.style.width = l ? Math.max(1, (+l.qty || 0) / max * 100).toFixed(1) + '%' : '0';
    q.lastChild.textContent = l ? int(l.qty) : '';
    p.firstChild.textContent = l ? int(l.price) : '';
    const r = l && pc ? (+l.price / pc - 1) * 100 : null;
    p.lastChild.textContent = r == null ? '' : pct(r);
    p.className = `sp-p ${side}${l && pc ? ' ' + cls(+l.price - pc) : ''}${l && cur != null && +l.price === cur ? ' cur' : ''}`;
    if (i === markIdx) p.dataset.mark = markPos; else delete p.dataset.mark;
    p.setAttribute('aria-label', l ? `${side === 'ask' ? '매도' : '매수'} ${int(l.price)}원 ${pct(r)}, 잔량 ${int(l.qty)}주` : '');
    const o = pv && pv[i], nw = ob.prev.cells[i];
    if (o && nw) {
      if (o.price !== nw.price) flash(p, 0);
      else if (o.qty !== nw.qty) flash(q, nw.qty > o.qty ? 1 : -1);
    }
  });
  const ta = +o.totalAsk || 0, tb = +o.totalBid || 0, share = ta + tb ? ta / (ta + tb) * 100 : 50;
  const s = S.sum;
  ob.info1.replaceChildren(
    obInfo('전일 종가', int(pc)),
    obInfo('현재가', cur != null ? int(cur) : '—', s ? cls(s.change) : '', outside),
    obInfo('등락률', s ? pct(s.ratio) : '—', s ? cls(s.ratio) : ''));
  ob.info2.replaceChildren(
    obInfo('매도 잔량', int(ta)), obInfo('매수 잔량', int(tb)),
    h('div', { class: 'sp-ob-ratio', role: 'img', 'aria-label': `매도 ${Math.round(share)}%, 매수 ${Math.round(100 - share)}%` },
      h('i', { class: 'a', style: `width:${share.toFixed(1)}%` }), h('i', { class: 'b' })));
  const notes = [`5단계 호가 · ${obPolling() ? '3초마다 갱신 · ' : ''}${clock(o.asOf || S.obAt)} 기준`];
  if (S.phase === 'after') notes.push('정규장이 끝나 시간외 호가예요. 현재가(NXT 포함)와 떨어져 있을 수 있어요.');
  else if (S.phase === 'closed' || S.phase === 'holiday' || S.phase === 'weekend') notes.push('장이 열리지 않아 마지막 호가가 멈춰 있어요.');
  notes.push('잔량 합계에는 보이지 않는 호가까지 들어 있어요.');
  ob.note.textContent = notes.join(' ');
}

/* (막대 첫 진입 — bars growing from zero the first time a tab drew them — went with design.md §6-2 P4 · P17c: data does not move on its first
   paint, and a period switch cross-fades instead of regrowing; ux/std-stock) */

/* ── 투자자 ── */
function invReset() { S.inv = null; S.invErr = null; S.invLoading = false; S.est = null; R.est = null; }
/* 오늘 잠정 (AGENTS §3-40 — 가족 기기만): "오늘" 카드 아래 작은 덩어리 "오늘 잠정 · 한국투자증권 가집계", 입력 회차마다 한 줄(09:30 · 10:00 ·
   11:20 · 13:20 · 14:30 — 외국인 · 기관 순매수 주식 수, 입력 시각까지 누적, 등락색). 투자자 탭을 열 때 KH.inv.fetch('/api/flows/live/stock/'
   + code)로 한 번(같은 종목은 1분 안 다시 묻지 않아요). 초대 토큰이 없는 기기 · 스냅샷 · 403 · 404(옛 Worker)는 흔적 없이 아무것도
   그리지 않아요. 그날 확정 행이 이미 있으면(저녁 21:30 뒤) 잠정은 빼요. */
const invApi = () => (LIVE && KH.inv && typeof KH.inv.has === 'function' && typeof KH.inv.fetch === 'function' ? KH.inv : null);
const famOn = () => { try { const I = invApi(); return !!(I && I.has()); } catch (e) { return false; } };
async function loadEst(force) {
  if (!famOn() || !S.code) { if (S.est) { S.est = null; paintEst(); } return null; }
  const code = S.code, g = S.gen, old = S.est && S.est.code === code ? S.est : null;
  if (!force && old && (old.st === 'load' || Date.now() - old.at < 60e3)) return null;
  S.est = { code, st: 'load', at: Date.now(), j: old ? old.j : null };
  paintEst();
  let st = 'fail', j = null;
  try {
    const r = await KH.inv.fetch('/api/flows/live/stock/' + encodeURIComponent(code));
    if (r.status === 403 || r.status === 404) st = 'none';                 // 초대가 꺼졌거나 그 경로가 없는 옛 Worker: 흔적 없이
    else if (r.ok) { try { j = await r.json(); } catch (e) { j = null; } st = j && j.closed ? 'none' : j && Array.isArray(j.slots) ? 'ok' : 'fail'; }   // closed: 휴장일 — 덩어리 없이
  } catch (e) { st = 'fail'; }
  if (g !== S.gen || S.code !== code) return null;
  S.est = { code, st, at: Date.now(), j };
  paintEst();
  return st === 'ok';
}
const EST_T = { 1: '09:30', 2: '10:00', 3: '11:20', 4: '13:20', 5: '14:30' };
function estBox() {
  if (!famOn() || !S.est || S.est.code !== S.code || S.est.st === 'none') return null;
  const E = S.est, j = E.j;
  // 그날 확정(저녁 매일 작업 · 네이버)이 이미 들어왔으면 잠정은 빼요
  if (j && j.date && Array.isArray(S.inv) && S.inv[0] && S.inv[0].date === j.date) return null;
  const today = kst(new Date()).key, dk = j && j.date ? +j.date.replace(/-/g, '') : today;
  const lp = j && j.date ? j.date.split('-').map(Number) : null;
  const when = !j || dk === today ? '오늘 잠정' : `${lp[1]}월 ${lp[2]}일 잠정`;
  const head = h('div', { class: 'sp-cum-h' }, h('h3', { text: when }), h('small', { text: '한국투자증권 가집계' }));
  let body;
  if (E.st === 'load' && !j) body = h('div', { class: 'sp-est-w', role: 'status', 'aria-label': '잠정 회차 불러오는 중' }, skel('100%', '18px'), skel('70%', '18px'));
  else if (E.st === 'fail' && !j) body = h('p', { class: 'sp-est-f', role: 'status' }, uiIcon('warn'), h('span', { text: '잠정 회차를 불러오지 못했어요' }),
    retryKey('est', () => loadEst(true), () => paintEst()));
  else if (!j.slots.length) body = h('p', { class: 'sp-est-e', text: '아직 입력분이 없어요 · 외국인은 09:30, 기관은 10:00부터 들어와요' });
  else {
    const cell = (v, none) => (none || !isNum(v) ? h('td', { class: 'num flat', text: '—' })
      : h('td', { class: 'num ' + cls(v) }, h('span', { class: 'l', text: signed(v) + '주' }), h('span', { class: 's', text: signedCompact(v) + '주' })));
    const rows = j.slots.slice().sort((a, b) => (+a.no || 0) - (+b.no || 0)).map(x => {
      const t = x.t || EST_T[x.no] || '';
      // 09:30 회차엔 기관이 아직 입력되지 않아 0으로 와요(data/ENDPOINTS_KIS.md ②) — 값이 아니라 "아직"이라 — 로
      return h('tr', null, h('th', { scope: 'row', text: t }), cell(x.f), cell(x.i, (t === '09:30' || +x.no === 1) && !+x.i));
    });
    body = h('table', { class: 'sp-est-t' }, h('caption', { class: 'sr', text: `${when} 순매수 회차별 (단위: 주)` }),
      h('thead', null, h('tr', null, h('th', { scope: 'col', text: '입력' }), h('th', { scope: 'col', text: '외국인' }), h('th', { scope: 'col', text: '기관' }))),
      h('tbody', null, rows));
  }
  const stale = (E.st === 'fail' && j) || (j && j.stale);   // 지난 사본(stale:true) · 다시 받다 실패
  return h('section', { class: 'sp-est', 'aria-label': `${when} · 한국투자증권 가집계` }, head, body,
    h('p', { class: 'sp-cum-sub' }, stale ? [uiIcon('warn'), ' 새 회차를 받지 못했어요 · '] : null, '입력 시각까지 누적한 잠정치예요 · 개인은 장 마감 뒤 확정돼요'));
}
// 이미 그려진 투자자 탭이면 "오늘" 카드 바로 아래 자리만 바꿔요(탭 전체를 다시 그리지 않아요)
function paintEst() {
  const P = R.panels && R.panels.inv;
  if (!P || !P.isConnected) return;
  const el = estBox(), cur = R.est && R.est.isConnected && P.contains(R.est) ? R.est : null;
  if (cur && el) cur.replaceWith(el); else if (cur) cur.remove();
  else if (el) { const t = P.querySelector(':scope > .sp-today'); if (!t) return; t.after(el); }
  R.est = el;
}
// quiet (the retry key): no loading picture, nothing drawn at the end → true / false / null
async function loadInv(quiet) {
  const g = S.gen;
  if (!quiet) { S.invLoading = true; S.invErr = null; renderInv(); }
  try {
    const j = await api('investors', 'inv');
    if (g !== S.gen) return null;
    S.inv = Array.isArray(j.rows) ? j.rows : []; S.invErr = null; failed.delete('inv');
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    S.invErr = e;
  }
  S.invLoading = false;
  if (!quiet) renderInv();
  return !S.invErr;
}
const GROUPS = [['individual', '개인'], ['foreign', '외국인'], ['institution', '기관']];
function sparkline(series, lo, hi) {
  const W = 100, H = 28, n = series.length;
  const y = v => (hi === lo ? H / 2 : H - 2 - (v - lo) / (hi - lo) * (H - 4));
  const x = i => (n < 2 ? W / 2 : i / (n - 1) * W);
  const d = series.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join('');
  return svg('svg', { class: 'sp-spark', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', 'aria-hidden': 'true' },
    svg('line', { x1: 0, x2: W, y1: y(0).toFixed(1), y2: y(0).toFixed(1), class: 'zero' }),
    svg('path', { d }));
}
// "오늘" (or the latest day with data): net buying per group as bars from a centre line, buys right, sells left
function todayCard(r, when) {
  const vals = GROUPS.map(([k]) => (isNum(r[k]) ? +r[k] : null));
  const max = Math.max(1, ...vals.filter(v => v != null).map(Math.abs));
  return h('section', { class: 'sp-today', 'aria-label': `${when} 투자자별 순매수` },
    h('div', { class: 'sp-cum-h' }, h('h3', { text: `${when} 순매수` }), h('small', { text: '단위: 주' })),
    GROUPS.map(([, label], i) => {
      const v = vals[i], w = v == null ? 0 : Math.max(v ? 1 : 0, Math.abs(v) / max * 50);
      return h('div', { class: 'sp-today-r' },
        h('span', { class: 'k', text: label }),
        h('b', { class: 'num ' + cls(v) }, h('span', { class: 'l', text: v == null ? '—' : signed(v) + '주' }), h('span', { class: 's', text: v == null ? '—' : signedCompact(v) + '주' })),
        h('span', { class: 'bar', 'aria-hidden': 'true' }, h('i', { class: cls(v), style: (v >= 0 ? 'left' : 'right') + `:50%;width:${w.toFixed(1)}%` })));
    }));
}
function netCell(v) { return h('td', { class: 'num ' + cls(v) }, h('span', { class: 'l', text: signed(v) }), h('span', { class: 's', text: signedCompact(v) })); }
function renderInv() {
  const P = R.panels.inv;
  if (S.invErr) { P.replaceChildren(msgBox('투자자별 매매를 불러오지 못했어요.', errSub(S.invErr), retryKey('inv', () => loadInv(true), renderInv))); return; }
  if (!S.inv) { P.replaceChildren(h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '투자자 정보 불러오는 중' }, skel('100%', '96px'), Array.from({ length: 8 }, () => skel('100%', '26px')))); return; }
  const rows = S.inv;
  if (!rows.length) { P.replaceChildren(msgBox('투자자별 매매 기록이 없어요.', '새로 상장했거나 거래가 적은 종목일 수 있어요.')); return; }
  const today = kst(new Date()), lp = rows[0].date.split('-').map(Number);
  const isToday = lp[0] * 10000 + lp[1] * 100 + lp[2] === today.key;
  const recent = rows.slice(0, 20).reverse();
  const cum = GROUPS.map(([k]) => { let a = 0; return recent.map(r => (a += isNum(r[k]) ? +r[k] : 0)); });
  const all = cum.flat().concat(0), lo = Math.min(...all), hi = Math.max(...all);
  const lastDate = rows[0].date;
  const card = h('section', { class: 'sp-cum', 'aria-label': `최근 ${recent.length}거래일 누적 순매수` },
    h('div', { class: 'sp-cum-h' }, h('h3', { text: `최근 ${recent.length}거래일 누적 순매수` }), h('small', { text: '단위: 주' })),
    GROUPS.map(([, label], gi) => {
      const total = cum[gi][cum[gi].length - 1];
      return h('div', { class: 'sp-cum-r ' + cls(total) }, h('span', { class: 'k', text: label }), sparkline(cum[gi], lo, hi),
        h('b', { class: 'num ' + cls(total) }, h('span', { class: 'l', text: signed(total) + '주' }), h('span', { class: 's', text: signedCompact(total) + '주' })));
    }),
    h('p', { class: 'sp-cum-sub', text: `${recent[0].date.replace(/-/g, '.')} ~ ${lastDate.replace(/-/g, '.')}` }));
  const note = h('p', { class: 'sp-note' }, `순매수는 산 주식 수에서 판 주식 수를 뺀 값(주)이에요. 투자자별 집계는 장이 끝난 뒤 나와서 오늘 기록은 저녁이나 다음 날 아침에 들어와요.${isToday ? '' : ` 마지막 기록은 ${+lp[1]}월 ${+lp[2]}일이에요.`}`);
  const thead = h('thead', {}, h('tr', {},
    h('th', { scope: 'col', text: '날짜' }), h('th', { scope: 'col', text: '종가' }), h('th', { scope: 'col', class: 'c-pct', text: '등락률' }),
    h('th', { scope: 'col', text: '개인' }), h('th', { scope: 'col', text: '외국인' }), h('th', { scope: 'col', text: '기관' }),
    h('th', { scope: 'col' }, h('span', { class: 'l', text: '외국인 보유율' }), h('span', { class: 's', text: '외인 보유' }))));
  const tbody = h('tbody', {}, rows.map(r => h('tr', {},
    h('td', { class: 'num' }, dateCell(r.date)),
    h('td', { class: 'num' }, int(r.close), h('small', { class: 's sub ' + cls(r.ratio), text: pct(r.ratio) })),
    h('td', { class: 'num c-pct ' + cls(r.ratio), text: pct(r.ratio) }),
    netCell(r.individual), netCell(r.foreign), netCell(r.institution),
    h('td', { class: 'num', text: fixed(r.foreignHoldRatio, 2, '%') }))));
  R.est = estBox();
  P.replaceChildren(todayCard(rows[0], isToday ? '오늘' : `${lp[1]}월 ${lp[2]}일`), ...(R.est ? [R.est] : []), card, note, h('table', { class: 'sp-tbl sp-inv-t' }, h('caption', { text: '날짜별 순매수 (단위: 주, 만 = 1만 주)' }), thead, tbody));
}

/* ── 일별 시세 ── */
function dailyReset() { S.daily = null; R.dailyTbody = null; }
// quiet (the retry key, 60일 더 보기): the message / rows stay as they are while it works, nothing drawn at the end → true / false / null
async function loadDaily(page, quiet) {
  const g = S.gen;
  if (!S.daily) S.daily = { rows: [], page: 0, hasMore: false, loading: false, err: null };
  const D = S.daily;
  if (D.loading) return null;
  D.loading = true;
  if (!quiet) { D.err = null; renderDaily(); }
  try {
    const j = await api('daily?page=' + page, 'daily');
    if (g !== S.gen) return null;
    const rows = Array.isArray(j.rows) ? j.rows : [];
    const seen = new Set(D.rows.map(r => r.date));
    D.rows.push(...rows.filter(r => r && r.date && !seen.has(r.date)));
    D.page = page; D.hasMore = !!j.hasMore && rows.length > 0; D.err = null; failed.delete('daily');
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    D.err = e;
  }
  D.loading = false;
  if (!quiet) renderDaily();
  return !D.err;
}
/* 60일 더 보기 (§5-3): ring "불러오는 중" → the rows go in, ✓ "60일 더 불러왔어요" for --c-dwell; ! "못 불러왔어요 · 다시" (the reason
   stays on the line above). The key keeps one width; on the last page it goes away. */
const MORE_SAY = { idle: '60일 더 보기', work: '불러오는 중', done: '60일 더 불러왔어요', fail: '못 불러왔어요 · 다시' };
async function dailyMore() {
  const b = R.dailyMore, g = S.gen;
  if (!b || b.dataset.st === 'work' || !S.daily) return;
  clearTimeout(R.dailyMoreT);
  setState(b, 'work');
  const r = await loadDaily(S.daily.page + 1, true);
  if (g !== S.gen) return;
  if (r == null) { setState(b, 'idle'); return; }
  setState(b, r ? 'done' : 'fail');
  renderDaily();
  if (r) { say('60일 더 불러왔어요.'); R.dailyMoreT = setTimeout(() => { if (b.dataset.st === 'done') setState(b, 'idle'); }, cMs('--c-dwell', 1120) || 1120); }
  else say('더 불러오지 못했어요.');
}
function dailyRow(r) {
  return h('tr', {},
    h('td', { class: 'num' }, dateCell(r.date)),
    h('td', { class: 'num', text: int(r.close) }),
    h('td', { class: 'num c-chg ' + cls(r.change), text: signed(r.change) }),
    h('td', { class: 'num c-pct2 ' + cls(r.ratio) }, pct(r.ratio), h('small', { class: 's sub', text: signed(r.change) })),
    h('td', { class: 'num c-o', text: int(r.open) }), h('td', { class: 'num c-o', text: int(r.high) }), h('td', { class: 'num c-o', text: int(r.low) }),
    h('td', { class: 'num c-hl' }, h('span', { text: int(r.high) }), h('small', { text: int(r.low) })),
    h('td', { class: 'num' }, h('span', { class: 'l', text: int(r.volume) }), h('span', { class: 's', text: compact(r.volume) })));
}
function renderDailyNote() {
  if (!R.dailyNote) return;
  R.dailyNote.hidden = !nxtApplies();
}
function renderDaily() {
  const P = R.panels.daily, D = S.daily;
  if (!D) return;
  if (!D.rows.length) {
    if (D.err) P.replaceChildren(msgBox('일별 시세를 불러오지 못했어요.', errSub(D.err), retryKey('daily', () => loadDaily(1, true), renderDaily)));
    else if (D.loading) P.replaceChildren(h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '일별 시세 불러오는 중' }, Array.from({ length: 12 }, () => skel('100%', '26px'))));
    else P.replaceChildren(msgBox('일별 시세가 없어요.', '새로 상장한 종목이면 거래가 쌓인 뒤에 보여요.'));
    return;
  }
  if (!R.dailyTbody || !P.contains(R.dailyTbody)) {
    R.dailyTbody = h('tbody');
    R.dailyMore = asyncKey('sp-btn sp-more', MORE_SAY);
    R.dailyMore.addEventListener('click', dailyMore);
    R.dailyErr = h('p', { class: 'sp-inline-err', role: 'status' });
    R.dailyNote = h('p', { class: 'sp-note', text: '정규장 이후에는 오늘 행에 NXT 거래가 섞여 KRX 종가(15:30)와 다를 수 있어요.' });
    const thead = h('thead', {}, h('tr', {}, [['날짜', ''], ['종가', ''], ['전일 대비', 'c-chg'], ['등락률', 'c-pct2'], ['시가', 'c-o'], ['고가', 'c-o'], ['저가', 'c-o'], ['고가·저가', 'c-hl'], ['거래량', '']]
      .map(([t, c]) => h('th', { scope: 'col', class: c, text: t }))));
    P.replaceChildren(R.dailyNote, h('table', { class: 'sp-tbl sp-daily-t' }, h('caption', { text: '일별 시세 (가격: 원, 거래량: 주)' }), thead, R.dailyTbody), R.dailyErr, R.dailyMore);
    R.dailyCount = 0;
  }
  renderDailyNote();
  if (R.dailyCount < D.rows.length) { R.dailyTbody.append(...D.rows.slice(R.dailyCount).map(dailyRow)); R.dailyCount = D.rows.length; }
  R.dailyErr.hidden = !D.err;
  R.dailyErr.textContent = D.err ? '더 불러오지 못했어요. ' + errSub(D.err) : '';
  R.dailyMore.hidden = !D.hasMore && !D.err;
}

/* ── 뉴스·공시 ── */
// Both lists load when the tab opens and stay cached per stock for 5 minutes (also across closing and reopening the page).
// 공시 comes from OpenDART (date only, kind, filer, 비고) or, when the Worker has no DART access, from Naver (with time).
const NEWS_KINDS = [
  { key: 'news', label: '뉴스', path: 'news', empty: '최근 뉴스가 없어요.', emptySub: '거래가 적거나 새로 상장한 종목이면 기사가 드물어요.',
    note: '네이버 증권에 모인 종목 뉴스예요. 비슷한 기사는 하나만 보여요. 누르면 새 탭에서 열려요.' },
  { key: 'disc', label: '공시', path: 'disclosures', empty: '최근 공시가 없어요.', emptySub: '최근에 낸 공시가 없는 종목이에요.', note: '누르면 새 탭에서 열려요.' },
];
const NEWS_KIND = Object.fromEntries(NEWS_KINDS.map(k => [k.key, k]));
const NEWS_TTL = 5 * 60e3;
const newsCache = new Map();   // `${code}|${kind}` → {at, rows, source}
let newsKind = NEWS_KIND[store.get('stockNewsKind', 'news')] ? store.get('stockNewsKind', 'news') : 'news';
const MARKET_NOTICE = /가격제한폭|확대요건|투자주의|투자경고|투자위험|단기과열|매매거래정지|공매도 과열/;
// DART kinds (Worker: 정기·실적·주요·지분·기타). 지분 reports (임원·주요주주 소유상황 등) swamp big caps, so they stay out
// of 전체 — and their chip stays hidden — until "지분 공시 포함" is switched on.
const DISC_FILTERS = ['전체', '주요', '실적', '정기', '지분'];
let discFilter = DISC_FILTERS.includes(store.get('stockDiscFilter', '전체')) ? store.get('stockDiscFilter', '전체') : '전체';
let discEquity = store.get('stockDiscEquity', false) === true;
const DART_NOTE = { 정: '정정', 철: '철회' };   // 비고 letters worth a tag; 연·유·코·채·넥·공 are not shown

function newsReset() { S.news = { news: null, disc: null }; }
function newsShow() { for (const k of NEWS_KINDS) loadNews(k.key); renderNews(); }
function setNewsKind(k) { newsKind = k; store.set('stockNewsKind', k); renderNews(); }
function setDiscFilter(f) { discFilter = f; store.set('stockDiscFilter', f); renderNews(); }
function setDiscEquity(on) {
  discEquity = on; store.set('stockDiscEquity', on);
  if (!on && discFilter === '지분') { discFilter = '전체'; store.set('stockDiscFilter', '전체'); }
  renderNews();
}
// quiet (the retry key): the error stays on screen while it works, nothing drawn at the end → true / false / null
async function loadNews(kind, quiet) {
  const code = S.code, g = S.gen, key = code + '|' + kind;
  const hit = newsCache.get(key);
  if (hit && Date.now() - hit.at < NEWS_TTL) return true;
  if (S.news[kind] && S.news[kind].loading) return null;
  const prev = S.news[kind];
  S.news[kind] = quiet && prev ? { loading: true, err: prev.err } : { loading: true, err: null };
  try {
    const j = await api(NEWS_KIND[kind].path, 'nw-' + kind);
    if (g !== S.gen) return null;
    newsCache.set(key, { at: Date.now(), rows: Array.isArray(j.rows) ? j.rows.filter(r => r && r.title) : [],
      source: j.source === 'dart' ? 'dart' : kind === 'disc' ? 'naver' : null });
    S.news[kind] = null; failed.delete('news:' + kind);
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    S.news[kind] = { loading: false, err: e };
  }
  if (!quiet && S.tab === 'news') renderNews();
  return !S.news[kind];
}

// Worker datetimes are ISO in KST; a value without a zone (Naver 공시) or Naver's YYYYMMDDHHmm is read as KST too
function parseKst(v) {
  if (!v) return null;
  let s = String(v).trim();
  const c = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?$/.exec(s);
  if (c) s = `${c[1]}-${c[2]}-${c[3]}T${c[4]}:${c[5]}:${c[6] || '00'}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += 'T00:00:00';
  s = s.replace(' ', 'T').replace(/T(\d{2}:\d{2})(?=$|[+-]|Z)/, 'T$1:00');
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += '+09:00';
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
const dayDiff = (a, n) => Math.round((Date.UTC(n.y, n.m - 1, n.d) - Date.UTC(a.y, a.m - 1, a.d)) / 864e5);
const dayLabel = (a, n) => (a.y === n.y ? `${a.m}월 ${a.d}일` : `${a.y}.${pad(a.m)}.${pad(a.d)}`);
function relTime(d, now) {
  const sec = (now - d) / 1000, a = kst(d), n = kst(now);
  if (sec < 60 && sec > -300) return '방금';
  if (sec >= 60 && sec < 3600) return Math.floor(sec / 60) + '분 전';
  if (sec > 0 && a.key === n.key) return Math.floor(sec / 3600) + '시간 전';
  const days = dayDiff(a, n);
  if (days === 1) return '어제';
  if (days > 1 && days < 7) return days + '일 전';
  return dayLabel(a, n);
}
// date-only rows (DART 접수일): 오늘 / 어제 / 11월 6일 — never a made-up clock time
function relDate(ymd, now) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(ymd || ''));
  if (!m) return null;
  const a = { y: +m[1], m: +m[2], d: +m[3] }, n = kst(now), days = dayDiff(a, n);
  return days === 0 ? '오늘' : days === 1 ? '어제' : dayLabel(a, n);
}
const fullTime = d => { const p = kst(d); return `${p.y}년 ${p.m}월 ${p.d}일 (${WD[p.wd]}) ${pad(p.hh)}:${pad(p.mm)}`; };
const fullDate = ymd => { const [y, m, d] = ymd.split('-').map(Number); return `${y}년 ${m}월 ${d}일 (${WD[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}) 접수`; };
const safeUrl = u => (typeof u === 'string' && /^https?:\/\//i.test(u) ? u : null);
const bareName = v => String(v || '').replace(/\(주\)|㈜|주식회사|\s/g, '');

function buildNews(panel) {
  R.nw = {
    seg: h('div', { class: 'sp-nwseg sp-seg seg', role: 'group', 'aria-label': '뉴스·공시 고르기' },
      NEWS_KINDS.map(k => h('button', { type: 'button', 'data-kind': k.key, 'aria-pressed': 'false', onclick: () => setNewsKind(k.key) },
        h('span', { text: k.label }), h('small', { class: 'num' })))),
    // 공시 종류: an underline row (§5-6) — the template's segment indicator drawn as a 2px amber bar that slides
    filters: h('div', { class: 'sp-dfilt seg', role: 'group', 'aria-label': '공시 종류', hidden: true },
      DISC_FILTERS.map(f => h('button', { type: 'button', 'data-f': f, 'aria-pressed': 'false', onclick: () => setDiscFilter(f) },
        h('span', { text: f }), h('small', { class: 'num' })))),
    src: h('div', { class: 'sp-nw-src', hidden: true }),
    body: h('div', { class: 'sp-nw-body' }),
    note: h('p', { class: 'sp-note' }),
  };
  R.nw.srcText = h('span');
  // the template's one switch (§5-8: .swbtn + .swt, 44 × 26, knob on `lead` in one piece, the knob can be dragged with KH.ui.sw)
  R.nw.equity = h('button', { type: 'button', class: 'sp-switch swbtn', role: 'switch', 'aria-checked': 'false', onclick: () => setDiscEquity(!discEquity) },
    h('span', { class: 'sp-switch-t', text: '지분 공시 포함' }), h('span', { class: 'swt', 'aria-hidden': 'true' }));
  if (UI && typeof UI.sw === 'function') UI.sw(R.nw.equity);
  R.nw.src.append(R.nw.srcText, R.nw.equity);
  panel.append(R.nw.seg, R.nw.filters, R.nw.src, R.nw.body, R.nw.note);
  spSeg(R.nw.seg); spSeg(R.nw.filters, true);
}
function tag(text, cls) { return h('span', { class: 'sp-nw-tag' + (cls ? ' ' + cls : ''), text }); }
function newsRow(r, kind, now) {
  const url = safeUrl(r.url), meta = [];
  if (kind === 'disc') {
    if (r.kind) meta.push(tag(String(r.kind), 'k'));
    for (const ch of new Set(String(r.note || ''))) if (DART_NOTE[ch]) meta.push(tag(DART_NOTE[ch], 'fix'));
    if (!r.kind && MARKET_NOTICE.test(r.title)) meta.push(tag('시장조치'));
    const own = bareName((S.sum && S.sum.name) || (KH.stock(S.code) || {}).n);
    if (r.filer && bareName(r.filer) !== own) meta.push(h('span', { class: 'sp-nw-press', text: String(r.filer) }));
  } else if (r.press) meta.push(h('span', { class: 'sp-nw-press', text: String(r.press) }));
  const d = parseKst(r.datetime), rd = !d && relDate(r.date, now);
  // 공시 배지 (disclosure.md §4-3): a DART row the map's feed has seen today shows that time (and the new dot) instead of "오늘"
  const seen = kind === 'disc' && !d && rd === '오늘' && url && window.KHDisc && typeof window.KHDisc.info === 'function'
    ? window.KHDisc.info((/rcpNo=(\d{14})/.exec(url) || [])[1]) : null;
  if (d) meta.push(h('time', { datetime: d.toISOString(), title: fullTime(d), text: relTime(d, now) }));
  else if (seen && seen.s && seen.date === r.date) meta.push(h('time', { class: 'sp-nw-seen', datetime: `${r.date}T${seen.s}`, title: `${fullDate(r.date)} · 판세가 ${seen.s}에 처음 봤어요` },
    seen.isNew ? [h('i', { class: 'sp-nw-dot', 'aria-hidden': 'true' }), h('span', { class: 'sp-vh', text: '새 공시 ' })] : null, seen.s));
  else if (rd) meta.push(h('time', { datetime: r.date, title: fullDate(r.date), text: rd }));
  const kids = [h('span', { class: 'sp-nw-t', text: String(r.title) }), h('span', { class: 'sp-nw-m' }, meta)];
  return h('li', {}, url
    ? h('a', { class: 'sp-nw-a', href: url, target: '_blank', rel: 'noopener' }, kids, h('span', { class: 'sp-vh', text: ' (새 탭)' }))
    : h('div', { class: 'sp-nw-a' }, kids));
}
// 공시 rows after the kind filter and the 지분 switch (Naver rows have no kind and are all shown)
function discRows(hit) {
  if (hit.source !== 'dart') return hit.rows;
  if (discFilter !== '전체') return hit.rows.filter(r => r.kind === discFilter);
  return discEquity ? hit.rows : hit.rows.filter(r => r.kind !== '지분');
}
function renderNews() {
  if (!R.nw) return;
  const kind = newsKind, meta = NEWS_KIND[kind], now = new Date();
  for (const b of segButtons(R.nw.seg)) {
    const k = b.dataset.kind, hk = newsCache.get(S.code + '|' + k);
    b.setAttribute('aria-pressed', String(k === kind));
    b.lastChild.textContent = hk ? String(k === 'disc' ? discRows(hk).length : hk.rows.length) : '';
  }
  const hit = newsCache.get(S.code + '|' + kind), st = S.news[kind];
  const dart = kind === 'disc' && hit && hit.source === 'dart';
  // 공시: filters (DART only) and the source line
  R.nw.filters.hidden = !(dart && hit.rows.length);
  R.nw.src.hidden = !(kind === 'disc' && hit);
  if (kind === 'disc' && hit) {
    R.nw.srcText.textContent = dart ? '출처: DART 전자공시 · 최근 6개월 · 접수일 기준' : '출처: 네이버 증권 · 거래소 시장조치 안내도 함께 나와요';
    R.nw.equity.hidden = !(dart && hit.rows.some(r => r.kind === '지분'));
    R.nw.equity.setAttribute('aria-checked', String(discEquity));
  }
  if (dart) {
    if (!discEquity && discFilter === '지분') discFilter = '전체';
    for (const b of segButtons(R.nw.filters)) {
      const f = b.dataset.f, n = f === '전체' ? hit.rows.filter(r => discEquity || r.kind !== '지분').length : hit.rows.filter(r => r.kind === f).length;
      b.hidden = f === '지분' && !discEquity;
      b.setAttribute('aria-pressed', String(f === discFilter));
      b.lastChild.textContent = String(n);
    }
  }
  let body;
  const rows = hit ? (kind === 'disc' ? discRows(hit) : hit.rows) : null;
  if (rows && rows.length) body = h('ul', { class: 'sp-nw-list' }, rows.map(r => newsRow(r, kind, now)));
  else if (hit && hit.rows.length) {   // the filter left nothing
    const onlyEquity = !discEquity && discFilter === '전체' && hit.rows.every(r => r.kind === '지분');
    body = msgBox(onlyEquity ? '최근 6개월 공시가 모두 지분 공시예요.' : `최근 6개월 동안 ${discFilter} 공시가 없어요.`, onlyEquity ? "'지분 공시 포함'을 켜면 볼 수 있어요." : '다른 종류를 골라 보세요.');
  } else if (hit) body = msgBox(meta.empty, meta.emptySub);
  else if (st && st.err) body = msgBox(`${meta.label}를 불러오지 못했어요.`, errSub(st.err), retryKey('news:' + kind, () => loadNews(kind, true), renderNews));
  else body = h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': `${meta.label} 불러오는 중` }, Array.from({ length: 6 }, () => skel('100%', '52px')));
  R.nw.body.replaceChildren(body);
  R.nw.note.textContent = meta.note;
  R.nw.note.hidden = !(rows && rows.length);
}

/* ── 종목 정보: 투자 지표 · 재무 · 안정성 · 배당 · 애널리스트 의견 (AGENTS.md §3-3) ── */
// Three sources load when the tab opens (finance annual + quarter, research) and stay cached per stock for 10 minutes;
// each fails on its own. 투자 지표 mixes /summary (PER, PBR, …) with finance (ROE, PSR).
const CI_SRC = { fa: 'finance?period=annual', fq: 'finance?period=quarter', res: 'research' };
const CI_TTL = 10 * 60e3;
const ciCache = new Map();   // `${code}|${kind}` → {at, j}
let finPeriod = store.get('stockFinPeriod', 'quarter') === 'annual' ? 'annual' : 'quarter';
let stabKey = store.get('stockStab', '부채비율') === '당좌비율' ? '당좌비율' : '부채비율';
const FIN_SERIES = [{ label: '매출', titles: ['매출액'] }, { label: '영업이익', titles: ['영업이익'] }, { label: '순이익', titles: ['당기순이익', '지배주주순이익'] }];
const STAB = {
  부채비율: '자본 대비 부채의 비율이에요.',
  당좌비율: '유동부채 대비 당좌자산(재고를 뺀 유동자산)의 비율이에요.',
};
const OPINIONS = ['적극매도', '매도', '중립', '매수', '적극매수'];
const RES_SHOW = 5, RES_MONTHS = 3;

function infoReset() {
  S.ci = { fa: null, fq: null, res: null }; S.ciSel = {}; S.resAll = false;
  if (R.ci) for (const k of ['met', 'fin', 'stab', 'div', 'ana']) R.ci[k].sig = null;
  sdgReset();
}
function infoShow() { for (const k in CI_SRC) loadCi(k); renderInfo(); sdgObserve(); }
function infoSummary() {
  if (!R.ci || S.tab !== 'info') return;
  renderMetrics(); renderDiv(); renderTargetGap();
}
// quiet (the retry keys): the section keeps its error while it works (ciState stays 'err'), nothing drawn at the end → true / false / null
async function loadCi(kind, force, quiet) {
  const code = S.code, g = S.gen, key = code + '|' + kind, hit = ciCache.get(key);
  if (!force && hit && Date.now() - hit.at < CI_TTL) return true;
  if (S.ci[kind] && S.ci[kind].loading) return null;
  const prev = S.ci[kind];
  S.ci[kind] = quiet && prev ? { loading: true, err: prev.err } : { loading: true, err: null };
  try {
    const j = await api(CI_SRC[kind], 'ci-' + kind);
    if (g !== S.gen) return null;
    ciCache.set(key, { at: Date.now(), j: j && typeof j === 'object' ? j : {} });
    S.ci[kind] = null;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    S.ci[kind] = { loading: false, err: e };
  }
  if (!quiet && S.tab === 'info') renderInfo();
  return ciState(kind) === 'ok';
}
const ciHit = k => ciCache.get(S.code + '|' + k) || null;
const ciData = k => { const x = ciHit(k); return x ? x.j : null; };
// 'ok' (data, even if a refresh is under way or failed) / 'err' / 'loading'
const ciState = k => (ciData(k) ? 'ok' : S.ci[k] && S.ci[k].err ? 'err' : 'loading');
const ciSig = (...k) => k.map(x => { const t = ciHit(x); return x + ':' + ciState(x) + ':' + (t ? t.at : ''); }).join('|');
// the retry keys of 재무 (both periods) and 애널리스트 의견
function ciRetry(area, ...kinds) {
  return retryKey(area, () => Promise.all(kinds.map(k => loadCi(k, true, true))).then(r => (r.includes(null) ? null : r.every(Boolean))), renderInfo);
}

// finance helpers: cols oldest first; values in cols order; '-' arrives as null
const finCols = fin => (fin && Array.isArray(fin.cols) ? fin.cols.filter(c => c && c.key != null) : []);
function finRow(fin, ...titles) {
  const rows = fin && Array.isArray(fin.rows) ? fin.rows : [];
  for (const t of titles) {
    const r = rows.find(x => x && x.title === t);
    if (r && Array.isArray(r.values)) return finCols(fin).map((_, i) => (isNum(r.values[i]) ? +r.values[i] : null));
  }
  return null;
}
function latestActual(fin, title) {
  const cols = finCols(fin), v = finRow(fin, title);
  if (!v) return null;
  for (let i = cols.length - 1; i >= 0; i--) if (!cols[i].estimate && v[i] != null) return { v: v[i], col: cols[i] };
  return null;
}
// '2026.06' → {y: 2026, m: 6}
function ym(col) { const m = /^(\d{4})\D?(\d{1,2})/.exec(String((col && (col.label || col.key)) || '')); return m ? { y: +m[1], m: +m[2] } : null; }
function periodLong(col, period) {
  const p = ym(col);
  if (!p) return String(col.label || col.key);
  return period === 'annual' && p.m === 12 ? `${p.y}년` : `${String(p.y).slice(2)}년 ${p.m}월`;
}
function periodShort(col, period) {
  const p = ym(col);
  if (!p) return String(col.label || col.key);
  return period === 'annual' && p.m === 12 ? String(p.y) : `${String(p.y).slice(2)}.${pad(p.m)}`;
}
// 억원 → 171조 4,995억원 / 1,065억원 / −67억원
function eokFull(v) {
  if (!isNum(v)) return '—';
  const sg = v < 0 ? MINUS : '', a = Math.round(Math.abs(v));
  if (a >= 10000) { const jo = Math.floor(a / 10000), r = a % 10000; return sg + jo.toLocaleString('ko-KR') + '조' + (r ? ' ' + r.toLocaleString('ko-KR') + '억' : '') + '원'; }
  return sg + a.toLocaleString('ko-KR') + '억원';
}
// 억원 → 171.5조 / 1,065억 (tables)
function eokShort(v) {
  if (!isNum(v)) return '—';
  const sg = v < 0 ? MINUS : '', a = Math.abs(v);
  return sg + (a >= 10000 ? (a / 10000).toLocaleString('ko-KR', { maximumFractionDigits: 1 }) + '조' : Math.round(a).toLocaleString('ko-KR') + '억');
}

// ROE: the latest actual year. PSR: 시가총액 ÷ the last 4 actual quarters' 매출 (else the latest actual year's 매출).
function roeOf() { return latestActual(ciData('fa'), 'ROE'); }
function psrOf() {
  const cap = S.sum && S.sum.code === S.code && isNum(S.sum.marketCap) ? +S.sum.marketCap : null;
  if (!cap) return null;
  const q = ciData('fq'), qv = finRow(q, '매출액');
  if (qv) {
    const act = finCols(q).map((c, i) => [c, qv[i]]).filter(([c, v]) => !c.estimate && v != null).slice(-4);
    const sum = act.reduce((a, [, v]) => a + v, 0);
    if (act.length === 4 && sum > 0) return { v: cap / sum, basis: '최근 4분기 매출 기준' };
  }
  const a = latestActual(ciData('fa'), '매출액');
  return a && a.v > 0 ? { v: cap / a.v, basis: `${periodLong(a.col, 'annual')} 매출 기준` } : null;
}

function buildInfo(panel) {
  const sec = (key, title, extra) => {
    const id = 'sp-ci-' + key;
    const body = h('div', { class: 'sp-ci-body' });
    const el = h('section', { class: 'sp-ci sp-ci-' + key, 'aria-labelledby': id }, h('div', { class: 'sp-ci-hd' }, h('h3', { id, text: title }), extra || null), body);
    return { el, body, sig: null };
  };
  const periodSeg = () => { const g = h('div', { class: 'sp-mseg seg', role: 'group', 'aria-label': '재무 기간' },
    [['quarter', '분기'], ['annual', '연간']].map(([k, l]) => h('button', { type: 'button', 'data-p': k, 'aria-pressed': 'false', onclick: () => setFinPeriod(k), text: l }))); spSeg(g); return g; };
  R.ci = {
    met: sec('met', '투자 지표'),
    fin: sec('fin', '재무', periodSeg()),
    stab: sec('stab', '안정성', periodSeg()),
    div: sec('div', '배당'),
    ana: sec('ana', '애널리스트 의견'),
  };
  R.ci.stabSeg = h('div', { class: 'sp-seg sp-stabseg seg', role: 'group', 'aria-label': '안정성 지표' },
    Object.keys(STAB).map(k => h('button', { type: 'button', 'data-k': k, 'aria-pressed': 'false', onclick: () => setStab(k), text: k })));
  spSeg(R.ci.stabSeg);
  R.ci.stabBody = h('div');
  R.ci.stab.body.append(R.ci.stabSeg, R.ci.stabBody);
  R.ci.stab.body = R.ci.stabBody;
  // 공공데이터포털 (금융위원회): 배당 내역은 배당 칸 아래, 대차잔고 · 기업 정보는 네이버 묶음(과 그 출처 줄) 뒤 — 블록마다 자기 출처 줄
  R.ci.lend = sec('lend', '대차잔고');
  R.ci.corp = sec('corp', '기업 정보');
  R.ci.lend.el.dataset.sdg = 'lend'; R.ci.corp.el.dataset.sdg = 'corp';
  R.ci.lend.el.classList.add('sp-sdg'); R.ci.corp.el.classList.add('sp-sdg');
  { const body = h('div', { class: 'sp-dvx-body' }), el = h('div', { class: 'sp-dvx', 'data-sdg': 'dvx' }, body); R.ci.dvx = { el, body, sig: null }; R.ci.div.el.append(el); }
  panel.append(R.ci.met.el, R.ci.fin.el, R.ci.stab.el, R.ci.div.el, R.ci.ana.el,
    h('p', { class: 'sp-note sp-ci-src', text: '출처: 네이버 증권 · 컨센서스는 증권사 추정치예요' }),
    R.ci.lend.el, R.ci.corp.el);
}
function setFinPeriod(k) { finPeriod = k; store.set('stockFinPeriod', k); renderFin(); renderStab(); }
function setStab(k) { stabKey = k; store.set('stockStab', k); renderStab(); }
function renderInfo() {
  if (!R.ci) return;
  renderMetrics(); renderFin(); renderStab(); renderDiv(); renderAna(); sdgRenderAll();
}
const ciSkel = (n, hgt) => h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '불러오는 중' }, Array.from({ length: n }, () => skel('100%', hgt)));

/* 투자 지표 */
function metric(label, value, sub) {
  return h('div', { class: 'sp-m' }, h('dt', { text: label }), h('dd', { class: 'num' }, value), sub ? h('dd', { class: 'sub', text: sub }) : null);
}
function renderMetrics() {
  const s = S.sum && S.sum.code === S.code ? S.sum : null;
  const wait = skel('3.6em', '1em');
  const faWait = ciState('fa') === 'loading', fqWait = ciState('fq') === 'loading';
  const roe = faWait ? null : roeOf(), psr = faWait || fqWait ? null : psrOf();
  const v = (x, fmt) => (!s ? (S.sumErr ? '—' : wait) : fmt(x));
  R.ci.met.body.replaceChildren(h('dl', { class: 'sp-mgrid' },
    metric('시가총액', v(s && s.marketCap, x => (isNum(x) ? F.eok(+x) + '원' : '—'))),
    metric('PER', v(s && s.per, x => fixed(x, 2, '배'))),
    metric('추정PER', v(s && s.cnsPer, x => fixed(x, 2, '배')), s && isNum(s.cnsPer) ? '증권사 예상' : ''),
    metric('PBR', v(s && s.pbr, x => fixed(x, 2, '배'))),
    metric('ROE', faWait ? wait : roe ? fixed(roe.v, 2, '%') : '—', roe ? `${periodLong(roe.col, 'annual')} 기준` : ''),
    metric('PSR', !s || faWait || fqWait ? (S.sumErr ? '—' : wait) : psr ? fixed(psr.v, 2, '배') : '—', psr ? psr.basis : ''),
    metric('배당수익률', v(s && s.dividendYield, x => fixed(x, 2, '%'))),
    // 주당배당금 right after 배당수익률 (사용자 2026-11-16 10:47) — /summary dps, else the last annual 결산 (같은 값을 아래 배당 칸도 써요)
    dpsMetric(s, v),
    metric('외국인 소진율', v(s && s.foreignRate, x => fixed(x, 2, '%')))));
}

function dpsMetric(s, v) {
  const fa = ciState('fa') === 'ok' ? ciData('fa') : null, last = fa ? latestActual(fa, '주당배당금') : null;
  if (s && isNum(s.dps)) return metric('주당배당금', +s.dps > 0 ? int(+s.dps) + '원' : '—', last && +s.dps === last.v ? `${periodLong(last.col, 'annual')} 결산` : '');
  if (!s) return metric('주당배당금', v(null, () => '—'));
  return metric('주당배당금', last && last.v > 0 ? int(last.v) + '원' : ciState('fa') === 'loading' ? skel('3.6em', '1em') : '—', last && last.v > 0 ? `${periodLong(last.col, 'annual')} 결산` : '');
}

/* 재무: grouped bars per period, estimates hatched, zero line with losses below */
function syncSegs() {
  for (const b of R.panels.info.querySelectorAll('.sp-mseg [data-p]')) b.setAttribute('aria-pressed', String(b.dataset.p === finPeriod));
  for (const b of segButtons(R.ci.stabSeg)) b.setAttribute('aria-pressed', String(b.dataset.k === stabKey));
}
function finView(fin) {
  const ser = FIN_SERIES.map(x => finRow(fin, ...x.titles) || []);
  const opm = finRow(fin, '영업이익률') || [], npm = finRow(fin, '순이익률') || [];
  const out = [];
  finCols(fin).forEach((c, i) => {
    const v = ser.map(a => (a[i] != null ? a[i] : null));
    if (v.some(x => x != null)) out.push({ c, v, opm: opm[i] != null ? opm[i] : null, npm: npm[i] != null ? npm[i] : null });
  });
  return out;
}
function renderFin() {
  syncSegs();
  const k = finPeriod === 'annual' ? 'fa' : 'fq', st = ciState(k), F0 = R.ci.fin;
  const sig = finPeriod + '|' + ciSig(k);
  if (F0.sig === sig) return;
  F0.sig = sig;
  if (st === 'loading') { F0.body.replaceChildren(h('div', { class: 'sp-fin-skel', role: 'status', 'aria-label': '재무 정보 불러오는 중' }, Array.from({ length: 18 }, (_, i) => h('i', { style: `height:${20 + Math.round(Math.abs(Math.sin(i * 1.3)) * 60)}%` })))); return; }
  if (st === 'err') { F0.body.replaceChildren(msgBox('재무 정보를 불러오지 못했어요.', errSub(S.ci[k].err), ciRetry('ci:fin', 'fa', 'fq'))); return; }
  const fin = ciData(k), list = finView(fin), period = finPeriod;
  if (!list.length) { F0.body.replaceChildren(msgBox('재무 정보가 없어요.', '새로 상장했거나 실적을 내지 않는 종목일 수 있어요.')); return; }
  const hasEst = list.some(x => x.c.estimate), estCols = finCols(fin).some(c => c.estimate);
  const all = list.flatMap(x => x.v).filter(v => v != null);
  const max = Math.max(0, ...all), min = Math.min(0, ...all), span = max - min || 1;
  const z = (max / span) * 100;   // zero line, % from the top of the bar area
  const pc = v => ((Math.abs(v) / span) * 100).toFixed(2) + '%';
  const unitName = period === 'annual' ? '연간' : '분기';
  const cols = list.map((x, i) => {
    const name = periodLong(x.c, period) + (x.c.estimate ? ' 예상' : '');
    const b = h('button', { type: 'button', role: 'radio', class: 'sp-fin-col' + (x.c.estimate ? ' est' : ''), 'data-key': x.c.key, tabindex: '-1',
      'aria-label': `${name}: ` + FIN_SERIES.map((s, j) => `${s.label} ${eokFull(x.v[j])}`).join(', '), onclick: () => pickFin(i, true) },
      h('span', { class: 'grp', 'aria-hidden': 'true' }, x.v.map((v, j) => h('span', { class: 'slot' },
        v == null ? null : h('i', { class: 'b s' + j + (v < 0 ? ' neg' : ''), style: v < 0 ? `top:${z.toFixed(2)}%;height:${pc(v)}` : `bottom:${(100 - z).toFixed(2)}%;height:${pc(v)}` })))));
    return b;
  });
  const radios = h('div', { class: 'sp-fin-cols', role: 'radiogroup', 'aria-label': `${unitName} 실적 기간` }, cols);
  radios.addEventListener('keydown', e => {
    let i = list.findIndex(x => x.c.key === F0.cur);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = Math.min(list.length - 1, i + 1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = Math.max(0, i - 1);
    else if (e.key === 'Home') i = 0;
    else if (e.key === 'End') i = list.length - 1;
    else return;
    e.preventDefault();
    pickFin(i, true, true);
  });
  const xs = h('div', { class: 'sp-fin-x', 'aria-hidden': 'true' }, list.map(x => h('span', {}, periodLong(x.c, period), x.c.estimate ? h('small', { text: '예상' }) : null)));
  const legend = h('div', { class: 'sp-fin-lg', 'aria-hidden': 'true' }, FIN_SERIES.map((s, j) => h('span', {}, h('i', { class: 'dot s' + j }), s.label)),
    hasEst ? h('span', {}, h('i', { class: 'dot hatch' }), '예상') : null);
  F0.vals = h('div', { class: 'sp-fin-sel', 'aria-live': 'polite' });
  F0.list = list; F0.cols = cols; F0.xs = xs; F0.period = period;
  // 표로 보기 (§7 펼치는 목록): the summary drives it, so the table's box can grow and shrink (foldMove) instead of jumping
  const tblBox = h('div', { class: 'sp-fold-box' });
  const tbl = h('details', { class: 'sp-fin-tbl', open: S.finTbl, ontoggle: e => { S.finTbl = e.currentTarget.open; } },
    h('summary', { text: '표로 보기', onclick: e => { e.preventDefault(); const want = !S.finTbl; S.finTbl = want; foldMove(tblBox, want, w => { tbl.open = w; }); } }),
    tblBox);
  tblBox.append(h('table', { class: 'sp-tbl sp-fin-t sp-fold-x' },
      h('caption', { text: `${unitName} 실적 (금액: 조·억원, 이익률: %)` }),
      h('thead', {}, h('tr', {}, ['기간', '매출', '영업이익', '순이익', '영업이익률'].map(t => h('th', { scope: 'col', text: t })))),
      h('tbody', {}, list.slice().reverse().map(x => h('tr', {},
        h('th', { scope: 'row' }, periodShort(x.c, period), x.c.estimate ? h('small', { text: '예상' }) : null),
        x.v.map(v => h('td', { class: v != null && v < 0 ? 'neg' : '', text: eokShort(v) })),
        h('td', { text: x.opm != null ? fixed(x.opm, 1, '%') : '—' }))))));
  F0.body.replaceChildren(legend,
    h('div', { class: 'sp-fin' }, h('div', { class: 'sp-fin-plot' },
      h('div', { class: 'sp-fin-area' }, h('i', { class: 'gl', style: 'top:0' }), h('i', { class: 'gl', style: 'top:50%' }), h('i', { class: 'zero', style: `top:${z.toFixed(2)}%` }), radios)), xs),
    F0.vals,
    h('p', { class: 'sp-note' }, hasEst ? '빗금 막대는 증권사 예상치(컨센서스)예요. ' : estCols ? '증권사 예상치가 없어요. ' : '', '막대를 누르면 그 기간 숫자를 볼 수 있어요.'),
    tbl);
  // keep the period the reader picked; otherwise the latest actual one
  let sel = list.findIndex(x => x.c.key === S.ciSel[period]);
  if (sel < 0) { sel = list.map(x => !x.c.estimate).lastIndexOf(true); if (sel < 0) sel = list.length - 1; }
  pickFin(sel, false);
}
function pickFin(i, user, focus) {
  const F0 = R.ci.fin, x = F0.list && F0.list[i];
  if (!x) return;
  F0.cur = x.c.key;
  if (user) S.ciSel[F0.period] = x.c.key;
  F0.cols.forEach((b, j) => { b.setAttribute('aria-checked', String(j === i)); b.tabIndex = j === i ? 0 : -1; b.classList.toggle('on', j === i); });
  [...F0.xs.children].forEach((el, j) => el.classList.toggle('on', j === i));
  if (focus) F0.cols[i].focus();
  F0.vals.replaceChildren(
    h('p', { class: 'sp-fin-when' }, h('b', { text: periodLong(x.c, F0.period) }), x.c.estimate ? h('span', { class: 'sp-tag', text: '예상' }) : h('span', { text: F0.period === 'annual' ? '연간 실적' : '분기 실적' })),
    h('dl', { class: 'sp-fin-vals' }, FIN_SERIES.map((s, j) => h('div', {}, h('dt', {}, h('i', { class: 'dot s' + j + (x.c.estimate ? ' hatch' : '') }), s.label), h('dd', { class: 'num', text: eokFull(x.v[j]) })))),
    x.opm != null || x.npm != null ? h('p', { class: 'sp-fin-m num' }, [x.opm != null ? `영업이익률 ${fixed(x.opm, 1, '%')}` : null, x.npm != null ? `순이익률 ${fixed(x.npm, 1, '%')}` : null].filter(Boolean).join(' · ')) : null);
}

/* 안정성: 부채비율 / 당좌비율 line with a label on every point */
function lineChart(pts, period, fmt, label) {
  // the domain hugs the data (every point carries its own label), never below 0 for positive ratios
  const n = pts.length, vs = pts.map(p => p.v), mn = Math.min(...vs), mx = Math.max(...vs);
  const pad = Math.max(mx - mn, Math.abs(mx) * 0.15, 1);
  const lo = mn >= 0 ? Math.max(0, mn - pad * 0.8) : mn - pad * 0.3, hi = mx + pad * 0.2;
  const X = i => ((i + 0.5) / n) * 100, Y = v => 24 + (1 - (v - lo) / (hi - lo)) * 64;
  const segs = [];
  for (let i = 1; i < n; i++) segs.push(svg('line', { x1: X(i - 1), y1: Y(pts[i - 1].v), x2: X(i), y2: Y(pts[i].v), class: pts[i].c.estimate || pts[i - 1].c.estimate ? 'est' : '' }));
  return h('figure', { class: 'sp-ln', role: 'img', 'aria-label': `${label}: ` + pts.map(p => `${periodLong(p.c, period)}${p.c.estimate ? ' 예상' : ''} ${fmt(p.v)}`).join(', ') },
    h('div', { class: 'plot' },
      svg('svg', { viewBox: '0 0 100 100', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, svg('line', { x1: 0, x2: 100, y1: Y(lo), y2: Y(lo), class: 'base' }), ...segs),
      pts.map((p, i) => h('span', { class: 'pt' + (p.c.estimate ? ' est' : ''), style: `left:${X(i).toFixed(2)}%;top:${Y(p.v).toFixed(2)}%` })),
      pts.map((p, i) => h('span', { class: 'lb num' + (i === n - 1 ? ' last' : ''), style: `left:${X(i).toFixed(2)}%;top:${Y(p.v).toFixed(2)}%`, text: fmt(p.v) }))),
    h('div', { class: 'sp-ln-x', 'aria-hidden': 'true' }, pts.map(p => h('span', {}, periodLong(p.c, period), p.c.estimate ? h('small', { text: '예상' }) : null))));
}
function renderStab() {
  syncSegs();
  const k = finPeriod === 'annual' ? 'fa' : 'fq', st = ciState(k), B = R.ci.stab;
  const sig = finPeriod + '|' + stabKey + '|' + ciSig(k);
  if (B.sig === sig) return;
  B.sig = sig;
  const fin = ciData(k), v = st === 'ok' ? finRow(fin, stabKey) : null;
  const pts = v ? finCols(fin).map((c, i) => ({ c, v: v[i] })).filter(p => p.v != null) : [];
  const any = st === 'ok' && Object.keys(STAB).some(t => (finRow(fin, t) || []).some(x => x != null));
  B.el.hidden = st === 'err' || (st === 'ok' && !any);   // the 재무 section above already says what went wrong
  if (st === 'loading') { B.body.replaceChildren(ciSkel(1, '150px')); return; }
  if (!pts.length) { B.body.replaceChildren(msgBox(`${stabKey} 기록이 없어요.`, '다른 지표나 기간을 골라 보세요.')); return; }
  B.body.replaceChildren(lineChart(pts, finPeriod, x => fixed(x, 1, '%'), stabKey), h('p', { class: 'sp-note', text: STAB[stabKey] }));
}

/* 배당: 주당배당금 by year (annual finance) + 배당수익률 (summary) */
function renderDiv() {
  const st = ciState('fa'), s = S.sum && S.sum.code === S.code ? S.sum : null, D = R.ci.div;
  const sig = ciSig('fa') + '|' + (s ? `${s.dps}|${s.dividendYield}` : S.sumErr ? 'err' : '');
  if (D.sig === sig) return;
  D.sig = sig;
  if (st === 'loading' && !s) { D.body.replaceChildren(ciSkel(3, '28px')); return; }
  const fa = ciData('fa'), dv = st === 'ok' ? finRow(fa, '주당배당금') : null;
  const pts = dv ? finCols(fa).map((c, i) => ({ c, v: dv[i] })).filter(p => p.v != null && p.v >= 0) : [];
  const last = latestActual(fa, '주당배당금');
  const dps = s && isNum(s.dps) ? +s.dps : last ? last.v : null;
  const yld = s && isNum(s.dividendYield) ? +s.dividendYield : null;
  if (st !== 'loading' && !pts.some(p => p.v > 0) && !(dps > 0) && !(yld > 0)) {
    D.body.replaceChildren(msgBox('최근 배당 기록이 없어요.', '최근 결산에서 배당하지 않았거나 정보가 없는 종목이에요.'));
    return;
  }
  const max = Math.max(1, ...pts.map(p => p.v));
  D.body.replaceChildren(
    h('dl', { class: 'sp-kv' },
      h('div', {}, h('dt', {}, '1주당 배당금', last ? h('small', { text: `${periodLong(last.col, 'annual')} 결산` }) : null), h('dd', { class: 'num', text: dps != null ? int(dps) + '원' : '—' })),
      h('div', {}, h('dt', {}, '배당수익률', h('small', { text: '주당배당금 ÷ 현재가' })), h('dd', { class: 'num', text: fixed(yld, 2, '%') }))),
    st === 'loading' ? ciSkel(1, '96px')
      : pts.length ? h('figure', { class: 'sp-dbars', role: 'img', 'aria-label': '연도별 주당배당금: ' + pts.map(p => `${periodLong(p.c, 'annual')}${p.c.estimate ? ' 예상' : ''} ${int(p.v)}원`).join(', ') },
        pts.map(p => h('div', { class: 'col' + (p.c.estimate ? ' est' : '') },
          h('span', { class: 'v num', text: int(p.v) + '원' }),
          h('span', { class: 'well' }, h('i', { style: `height:${Math.max(p.v > 0 ? 3 : 0, (p.v / max) * 100).toFixed(1)}%` })),
          h('span', { class: 'x' }, periodShort(p.c, 'annual'), p.c.estimate ? h('small', { text: '예상' }) : null))))
        : st === 'err' ? h('p', { class: 'sp-inline-err', text: '연도별 배당 기록을 불러오지 못했어요.' }) : null);
}

/* 애널리스트 의견: last 3 months' opinions, consensus target, report list */
function opinionBucket(o) {
  const s = String(o || '').replace(/\s+/g, '').toLowerCase();
  if (!s) return -1;
  if (/^(strongbuy|적극매수|강력매수)/.test(s)) return 4;
  if (/^(strongsell|적극매도|강력매도)/.test(s)) return 0;
  if (/^(buy|매수|tradingbuy|단기매수|outperform|overweight|비중확대|accumulate|add|시장수익률상회)/.test(s)) return 3;
  if (/^(sell|매도|underperform|underweight|비중축소|reduce|시장수익률하회)/.test(s)) return 1;
  if (/^(hold|중립|neutral|marketperform|보유|시장수익률|equalweight|marketweight|inline)/.test(s)) return 2;
  return -1;
}
function monthsAgo(n) { const t = kst(new Date()); return new Date(Date.UTC(t.y, t.m - 1 - n, t.d)).toISOString().slice(0, 10); }
function shortDate(ymd) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(ymd || ''));
  if (!m) return '';
  return +m[1] === kst(new Date()).y ? `${+m[2]}월 ${+m[3]}일` : `${m[1].slice(2)}.${m[2]}.${m[3]}`;
}
function renderTargetGap() {
  const el = R.ci && R.ci.gap, t = el && +el.dataset.t;
  if (!el || !t) return;
  const p = S.sum && S.sum.code === S.code && isNum(S.sum.price) ? +S.sum.price : null;
  el.hidden = p == null;
  if (p == null) return;
  const r = (t / p - 1) * 100;
  el.className = 'sp-gap num ' + cls(r);
  el.textContent = `현재가 대비 ${pct(r, 1)}`;
}
function renderAna() {
  const st = ciState('res'), A = R.ci.ana;
  const sig = ciSig('res') + '|' + S.resAll;
  if (A.sig === sig) return;
  A.sig = sig;
  R.ci.gap = null;
  if (st === 'loading') { A.body.replaceChildren(ciSkel(4, '40px')); return; }
  if (st === 'err') { A.body.replaceChildren(msgBox('애널리스트 의견을 불러오지 못했어요.', errSub(S.ci.res.err), ciRetry('ci:res', 'res'))); return; }
  const j = ciData('res'), rows = (Array.isArray(j.rows) ? j.rows : []).filter(r => r && r.title);
  const cons = j.consensus && typeof j.consensus === 'object' ? j.consensus : null;
  const tgt = cons && isNum(cons.targetMean) && +cons.targetMean > 0 ? +cons.targetMean : null;
  const om = cons && isNum(cons.opinionMean) && +cons.opinionMean >= 1 ? +cons.opinionMean : null;
  if (!rows.length && tgt == null && om == null) {
    A.body.replaceChildren(msgBox('최근 증권사 리포트가 없어요.', '증권사 분석이 드문 종목이에요. 리포트가 나오면 여기에 보여요.'));
    return;
  }
  const kids = [];
  // opinion spread over the last 3 months
  const cutoff = monthsAgo(RES_MONTHS), recent = rows.filter(r => String(r.date || '') >= cutoff);
  const counts = [0, 0, 0, 0, 0];
  let unknown = 0;
  for (const r of recent) { const b = opinionBucket(r.opinion); if (b < 0) unknown++; else counts[b]++; }
  const counted = recent.length - unknown, capped = rows.length >= 20 && String(rows[rows.length - 1].date || '') >= cutoff;
  const top = Math.max(...counts);
  kids.push(h('p', { class: 'sp-ana-h' }, h('b', { text: `최근 ${RES_MONTHS}개월 리포트 ${recent.length}건` }), capped ? h('small', { text: '최근 20건까지만 셌어요' }) : null));
  if (!recent.length) kids.push(h('p', { class: 'sp-ana-empty', text: `최근 ${RES_MONTHS}개월 동안 나온 리포트가 없어요.` }));
  else if (!counted) kids.push(h('p', { class: 'sp-ana-empty', text: `최근 ${RES_MONTHS}개월 리포트 ${recent.length}건에서 투자의견을 찾지 못했어요.` }));
  else {
    kids.push(h('figure', { class: 'sp-op', role: 'img', 'aria-label': '의견 분포: ' + OPINIONS.map((o, i) => `${o} ${counts[i]}건`).join(', ') },
      OPINIONS.map((o, i) => h('div', { class: 'col' + (counts[i] && counts[i] === top ? ' max' : '') + (counts[i] ? '' : ' zero') },
        h('span', { class: 'n num', text: `${counts[i]}건` }),
        h('span', { class: 'well' }, h('i', { style: `height:${counts[i] ? Math.max(8, (counts[i] / top) * 100).toFixed(1) : 0}%` })),
        h('span', { class: 'x', text: o })))));
    if (unknown) kids.push(h('p', { class: 'sp-note sp-op-note', text: `의견을 찾지 못한 리포트 ${unknown}건은 세지 않았어요.` }));
  }
  // consensus
  if (tgt != null || om != null) {
    const gap = tgt != null ? h('span', { class: 'sp-gap num', 'data-t': String(tgt) }) : null;
    R.ci.gap = gap;
    const when = cons.date ? shortDate(cons.date) + ' 기준 · ' : '';
    kids.push(h('dl', { class: 'sp-kv sp-cons' },
      tgt != null ? h('div', {}, h('dt', {}, '평균 목표주가', h('small', { text: `${when}증권사 평균` })), h('dd', {}, h('span', { class: 'num', text: int(tgt) + '원' }), gap)) : null,
      om != null ? h('div', {}, h('dt', {}, '평균 투자의견', h('small', { text: '1 적극매도 ~ 5 적극매수' })),
        h('dd', {}, h('span', { class: 'num', text: `${om.toFixed(2)}점` }), h('span', { class: 'sp-tag', text: OPINIONS[Math.max(0, Math.min(4, Math.round(om) - 1))] }))) : null));
  }
  // reports — 더 보기 ↔ 접기 (design.md §7 펼치는 목록): the list's box grows / shrinks (foldMove); the key stays, its label swaps in place
  // (§6-4) and its chevron turns (stock.css .sp-fold)
  if (rows.length) {
    const reportRow = (r, extra) => {
      const url = safeUrl(r.url), b = opinionBucket(r.opinion);
      const meta = [h('time', { datetime: String(r.date || ''), text: shortDate(r.date) }), r.broker ? h('span', { class: 'br', text: String(r.broker) }) : null,
        isNum(r.target) && +r.target > 0 ? h('span', { class: 'num', text: `목표가 ${int(r.target)}원` }) : null,
        r.opinion ? h('span', { class: 'sp-tag', text: b >= 0 ? OPINIONS[b] : String(r.opinion) }) : null];
      const kidsA = [h('span', { class: 'sp-rp-t', text: String(r.title) }), h('span', { class: 'sp-rp-m' }, meta)];
      return h('li', { class: extra ? 'sp-fold-x' : null }, url ? h('a', { class: 'sp-rp', href: url, target: '_blank', rel: 'noopener' }, kidsA, h('span', { class: 'sp-vh', text: ' (새 탭)' })) : h('div', { class: 'sp-rp' }, kidsA));
    };
    const list = h('ul', { class: 'sp-rp-list', id: 'sp-rp-list' }), box = h('div', { class: 'sp-fold-box' }, list);
    const fill = all => list.replaceChildren(...(all ? rows : rows.slice(0, RES_SHOW)).map((r, i) => reportRow(r, i >= RES_SHOW)));
    const label = () => (S.resAll ? '접기' : `리포트 ${rows.length - RES_SHOW}건 더 보기`);
    fill(S.resAll);
    kids.push(h('h4', { class: 'sp-rp-h' }, '리포트', h('small', { class: 'num', text: String(rows.length) })), box,
      rows.length > RES_SHOW ? h('button', { type: 'button', class: 'sp-btn sp-more sp-fold', 'aria-expanded': String(S.resAll), 'aria-controls': 'sp-rp-list',
        onclick: e => {
          const btn = e.currentTarget, t = btn.querySelector('.mt'), was = t.textContent;
          S.resAll = !S.resAll; A.sig = ciSig('res') + '|' + S.resAll;
          btn.setAttribute('aria-expanded', String(S.resAll));
          if (UI && typeof UI.swap === 'function') UI.swap(t, label(), was); else t.textContent = label();
          foldMove(box, S.resAll, fill, S.resAll ? null : () => keepInView(btn));
        } }, h('span', { class: 'mt', text: label() })) : null,
      h('p', { class: 'sp-note', text: '리포트 본문은 증권사 원문에서 볼 수 있어요. 누르면 새 탭에서 열려요.' }));
  } else kids.push(h('p', { class: 'sp-ana-empty', text: '최근 리포트 목록이 없어요.' }));
  A.body.replaceChildren(...kids);
  renderTargetGap();
}

/* ── 공공데이터포털 (금융위원회): 대차잔고 · 배당 내역 · 기업 정보 (AGENTS.md §3 · §3-32 ②④⑤) ──
   /api/stock/{code}/lending · dividend · corp — 하루 한 번 바뀌는 자료라 종목마다 30분 기억해요. 블록이 화면 근처(아래 300px)에 오면 그때 받아요
   (IntersectionObserver — 탭이 숨으면 교차하지 않아요). 404(옛 Worker, 또는 ETF처럼 자료가 없는 종목)는 그 블록을 숨겨요. 대차잔고 증감은
   가격이 아니라서 빨강·초록 없이 중립색 글자로만(AGENTS §4: 빨강·초록은 등락에만). */
const SDG_SRC = { lending: 'lending', dividend: 'dividend', corp: 'corp' };
const SDG_TTL = 30 * 60e3;
const SDG_SOURCE = '금융위원회 · 공공데이터포털, 하루 한 번';
const SDG_NAMES = 8, SDG_DIV_ROWS = 8;
const sdgCache = new Map();   // `${code}|${kind}` → {at, j} | {at, gone: true}
const SDG = { st: {}, near: new Set(), io: null, open: {}, mv: null };
const sdgKey = k => S.code + '|' + k;
const sdgHit = k => { const x = sdgCache.get(sdgKey(k)); return x && Date.now() - x.at < SDG_TTL ? x : null; };
// 'gone' (404: hide) · 'ok' · 'err' · 'loading' · 'idle' (not near the viewport yet)
function sdgState(k) {
  const x = sdgHit(k);
  if (x) return x.gone ? 'gone' : 'ok';
  if (SDG.st[k] && SDG.st[k].err) return 'err';
  return SDG.st[k] && SDG.st[k].loading ? 'loading' : 'idle';
}
const sdgSig = k => { const x = sdgHit(k); return k + ':' + sdgState(k) + ':' + (x ? x.at : '') + ':' + (SDG.st[k] && SDG.st[k].err ? SDG.st[k].err.status || 'n' : ''); };
function sdgReset() {
  SDG.st = {}; SDG.near = new Set(); SDG.open = {};
  if (SDG.mv) { SDG.mv.finish(); SDG.mv = null; }
  if (R.ci) for (const k of ['lend', 'dvx', 'corp']) if (R.ci[k]) R.ci[k].sig = null;
}
async function sdgLoad(k, force, quiet) {
  const code = S.code, g = S.gen;
  if (!force && sdgHit(k)) return true;
  if (SDG.st[k] && SDG.st[k].loading) return null;
  const prev = SDG.st[k];
  SDG.st[k] = quiet && prev ? { loading: true, err: prev.err } : { loading: true, err: null };
  if (!quiet) sdgRender(k);
  try {
    const j = await api(SDG_SRC[k], 'sdg-' + k);
    if (g !== S.gen) return null;
    sdgCache.set(code + '|' + k, { at: Date.now(), j: j && typeof j === 'object' ? j : {} });
    SDG.st[k] = null;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return null;
    if (e && e.status === 404) { sdgCache.set(code + '|' + k, { at: Date.now(), gone: true }); SDG.st[k] = null; }
    else SDG.st[k] = { loading: false, err: e };
  }
  if (!quiet && S.tab === 'info') sdgRender(k);
  return sdgState(k) === 'ok' || sdgState(k) === 'gone';
}
// a block near the viewport (or already shown) asks for its data once per stock
function sdgNear(k) {
  if (!S.open || S.tab !== 'info' || SDG.near.has(k)) return;
  SDG.near.add(k);
  loadSdgFor(k);
}
const SDG_OF = { lend: 'lending', dvx: 'dividend', corp: 'corp' };
function loadSdgFor(blk) { const k = SDG_OF[blk]; if (sdgState(k) === 'idle') sdgLoad(k); else sdgRender(k); }
function sdgObserve() {
  if (!R.ci || !R.ci.lend) return;
  const els = [R.ci.lend.el, R.ci.dvx.el, R.ci.corp.el];
  if (typeof IntersectionObserver !== 'function') { for (const e of els) sdgNear(e.dataset.sdg); return; }
  // the scroller is the panel on wide screens (≥ 1100px, the side card scrolls) and the page itself below that: observe in it, so the
  // 300px look-ahead is real (with the viewport as root, the scroller's clip would cut it off)
  const scrolls = el => el && /^(auto|scroll)$/.test(getComputedStyle(el).overflowY);
  const box = scrolls(R.panels.info) ? R.panels.info : scrolls(root) ? root : null;
  if (!SDG.io || SDG.ioRoot !== box) {
    if (SDG.io) SDG.io.disconnect();
    SDG.ioRoot = box;
    SDG.io = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) sdgNear(e.target.dataset.sdg); }, { root: box, rootMargin: '0px 0px 300px 0px' });
  }
  SDG.io.disconnect();                    // a fresh first callback for each element (switching stocks with the tab already open)
  for (const e of els) SDG.io.observe(e);
}
const SDG_BLK = { lending: 'lend', dividend: 'dvx', corp: 'corp' };
function sdgRender(k) { if (!R.ci || !R.ci.lend) return; ({ lending: renderLend, dividend: renderDvx, corp: renderCorp })[k](); }
function sdgRenderAll() { for (const k in SDG_SRC) sdgRender(k); }
function sdgRetry(k) {
  return retryKey('sdg:' + k, () => sdgLoad(k, true, true), () => sdgRender(k));
}
// "11월 13일 (금)" this year, "2025년 11월 13일" otherwise
function sdgDay(d) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(d || ''));
  if (!m) return '';
  const wd = WD[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
  return +m[1] === kst(new Date()).y ? `${+m[2]}월 ${+m[3]}일 (${wd})` : `${m[1]}년 ${+m[2]}월 ${+m[3]}일`;
}
const longDate = d => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(d || '')); return m ? `${m[1]}년 ${+m[2]}월 ${+m[3]}일` : '—'; };
const dotDate = d => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(d || '')); return m ? `${m[1]}.${m[2]}.${m[3]}` : '—'; };
// 64,123,456 → 6,412만 주 · 1.23억 주 · 12,345주 (signed: +12.3만 주)
function sharesText(v, signed) {
  if (!isNum(v)) return '—';
  const sg = signed ? (v > 0 ? '+' : v < 0 ? MINUS : '') : v < 0 ? MINUS : '', a = Math.abs(+v);
  if (a >= 1e8) return sg + (a / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 2 }) + '억 주';
  if (a >= 1e4) return sg + (a / 1e4).toLocaleString('ko-KR', { maximumFractionDigits: a >= 1e6 ? 0 : 1 }) + '만 주';
  return sg + Math.round(a).toLocaleString('ko-KR') + '주';
}
// 원 → 1.23조원 · 4,481억원 · 3,200만원
function wonText(v) {
  if (!isNum(v)) return '—';
  const a = Math.abs(+v), sg = v < 0 ? MINUS : '';
  if (a >= 1e12) return sg + (a / 1e12).toLocaleString('ko-KR', { maximumFractionDigits: 2 }) + '조원';
  if (a >= 1e8) return sg + Math.round(a / 1e8).toLocaleString('ko-KR') + '억원';
  if (a >= 1e4) return sg + Math.round(a / 1e4).toLocaleString('ko-KR') + '만원';
  return sg + Math.round(a).toLocaleString('ko-KR') + '원';
}
function sdgSrc(j, lead) {
  return h('p', { class: 'sp-sdg-src' }, lead ? lead + ' · ' : '', SDG_SOURCE, j && j.stale ? h('span', { class: 'st', text: ' · 새로 받지 못해 지난 자료예요' }) : null);
}
// not near the viewport yet: an empty place (no skeleton, nothing announced — nothing is loading)
const sdgIdle = k => h('div', { class: 'sp-sdg-idle sp-sdg-idle-' + k, 'aria-hidden': 'true' });
function sdgWait(k, title) {
  return h('div', { class: 'sp-skel-rows sp-sdg-wait', role: 'status', 'aria-label': `${title} 불러오는 중` },
    k === 'lend' ? [skel('9em', '26px'), skel('100%', '64px')] : Array.from({ length: k === 'dvx' ? 3 : 5 }, () => skel('100%', '32px')));
}
function sdgFail(k, title) {
  const e = SDG.st[SDG_OF[k]] && SDG.st[SDG_OF[k]].err;
  const wait = e && e.status === 503;
  return msgBox(wait ? `${title} 자료를 아직 받는 중이에요.` : `${title}를 불러오지 못했어요.`,
    wait ? '금융위원회 자료는 하루 한 번 들어와요. 잠시 뒤 다시 볼 수 있어요.' : errSub(e), sdgRetry(SDG_OF[k]));
}

/* 대차잔고: 마지막 값 + 전 영업일 대비 + 60영업일 선 */
function renderLend() {
  const B = R.ci.lend, sig = sdgSig('lending');
  if (B.sig === sig) return;
  B.sig = sig;
  const st = sdgState('lending');
  B.el.hidden = st === 'gone';
  if (st === 'gone') return;
  if (st === 'idle') { B.body.replaceChildren(sdgIdle('lend')); return; }
  if (st === 'loading') { B.body.replaceChildren(sdgWait('lend', '대차잔고')); return; }
  if (st === 'err') { B.body.replaceChildren(sdgFail('lend', '대차잔고')); return; }
  const j = sdgHit('lending').j, rows = (Array.isArray(j.rows) ? j.rows : []).filter(r => r && isNum(r.shares) && r.date);
  if (!rows.length) {
    B.body.replaceChildren(msgBox('최근 대차잔고 기록이 없어요.', '최근 60영업일 동안 빌려준 주식이 없었던 종목이에요.'), sdgSrc(j, j.basDt ? sdgDay(j.basDt) + ' 기준' : ''));
    return;
  }
  const L = rows[rows.length - 1], P0 = rows.length > 1 ? rows[rows.length - 2] : null;
  const chg = P0 ? L.shares - P0.shares : null, ratio = P0 && P0.shares > 0 ? (L.shares / P0.shares - 1) * 100 : null;
  const chgText = chg == null ? '전 영업일 자료가 없어요' : chg === 0 ? '전 영업일과 같아요' : `전 영업일보다 ${sharesText(chg, true)}${ratio != null ? ` (${pct(ratio, 2)})` : ''}`;
  const kv = [['잔고 금액', isNum(L.amount) && L.amount > 0 ? wonText(L.amount) : null], ['그날 빌려줌', isNum(L.lent) ? sharesText(L.lent) : null], ['그날 갚음', isNum(L.repaid) ? sharesText(L.repaid) : null]]
    .filter(x => x[1] != null);
  B.body.replaceChildren(h('div', { class: 'sp-lb' },
    h('div', { class: 'sp-lb-hd' },
      h('p', { class: 'sp-lb-v' }, h('b', { class: 'num', text: sharesText(L.shares) }), h('span', { class: 'num chg', text: chgText })),
      kv.length ? h('dl', { class: 'sp-lb-kv' }, kv.map(([t, v]) => h('div', {}, h('dt', { text: t }), h('dd', { class: 'num', text: v })))) : null),
    rows.length > 1 ? lendLine(rows) : null,
    h('p', { class: 'sp-note', text: '빌려 간 주식 중 아직 갚지 않은 수량이에요. 늘고 줄어든 것만 보여 줄 뿐 좋고 나쁨을 뜻하지 않아요.' }),
    sdgSrc(j, sdgDay(L.date) + ' 기준')));
}
// a small line of the days the API has (oldest → newest), the newest point marked; neutral series colour (not up / down)
function lendLine(rows) {
  const n = rows.length, vs = rows.map(r => +r.shares), mn = Math.min(...vs), mx = Math.max(...vs), span = mx - mn || Math.max(1, mx * 0.02);
  const X = i => (n === 1 ? 50 : (i / (n - 1)) * 100), Y = v => 4 + (1 - (v - mn) / span) * 52;
  const line = vs.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(2)} ${Y(v).toFixed(2)}`).join(' ');
  const hiI = vs.indexOf(mx), loI = vs.indexOf(mn);
  const label = `대차잔고 ${n}영업일: ${sdgDay(rows[0].date)} ${sharesText(vs[0])}에서 ${sdgDay(rows[n - 1].date)} ${sharesText(vs[n - 1])}, 가장 많았던 날 ${sdgDay(rows[hiI].date)} ${sharesText(mx)}, 가장 적었던 날 ${sdgDay(rows[loI].date)} ${sharesText(mn)}`;
  return h('figure', { class: 'sp-lb-fig', role: 'img', 'aria-label': label },
    h('div', { class: 'plot' },
      svg('svg', { viewBox: '0 0 100 60', preserveAspectRatio: 'none', 'aria-hidden': 'true' },
        svg('path', { class: 'area', d: `${line} L100 60 L0 60 Z` }), svg('path', { class: 'ln', d: line })),
      h('span', { class: 'pt', style: `left:${X(n - 1).toFixed(2)}%;top:${(Y(vs[n - 1]) / 60 * 100).toFixed(2)}%` })),
    h('div', { class: 'sp-lb-x', 'aria-hidden': 'true' }, h('span', { text: shortDate(rows[0].date) }), h('span', { class: 'mid num', text: `최고 ${sharesText(mx)} · 최저 ${sharesText(mn)}` }), h('span', { text: shortDate(rows[n - 1].date) })));
}

/* 배당 내역: 기준일 · 지급일 · 1주당 배당금 (배당 칸 아래) */
function renderDvx() {
  const B = R.ci.dvx, sig = sdgSig('dividend');
  if (B.sig === sig) return;
  B.sig = sig;
  const st = sdgState('dividend');
  B.el.hidden = st === 'gone';
  if (st === 'gone') return;
  const head = h('h4', { class: 'sp-dvx-h' }, '배당 내역', h('small', { text: '금융위원회 자료' }));
  if (st === 'idle') { B.body.replaceChildren(head, sdgIdle('dvx')); return; }
  if (st === 'loading') { B.body.replaceChildren(head, sdgWait('dvx', '배당 내역')); return; }
  if (st === 'err') {
    const e = SDG.st.dividend.err;
    B.body.replaceChildren(head, h('p', { class: 'sp-inline-err', role: 'status', text: e && e.status === 503 ? '배당 내역 자료를 아직 받는 중이에요. 잠시 뒤 다시 볼 수 있어요.' : '배당 내역을 불러오지 못했어요.' }), sdgRetry('dividend'));
    return;
  }
  const j = sdgHit('dividend').j, all = (Array.isArray(j.rows) ? j.rows : []).filter(r => r && r.recordDate);
  const lead = j.basDt ? sdgDay(j.basDt) + ' 자료' : '';
  if (!all.length) { B.body.replaceChildren(head, h('p', { class: 'sp-dvx-empty', text: '최근 몇 년 동안 금융위원회 배당 자료에 이 종목 기록이 없어요.' }), sdgSrc(j, lead)); return; }
  const rows = all.slice(0, SDG_DIV_ROWS);
  const amt = r => {
    const kids = [];
    if (isNum(r.amount) && r.amount > 0) kids.push(int(r.amount) + '원');
    else if (isNum(r.stockRate) && r.stockRate > 0) kids.push(`주식 ${fixed(r.stockRate, 2, '%').replace(/\.?0+%$/, '%')}`);
    else kids.push('—');
    if (r.reason && r.reason !== '현금배당') kids.push(h('small', { text: r.reason }));
    if (isNum(r.extraAmount) && r.extraAmount > 0) kids.push(h('small', { text: `차등 ${int(r.extraAmount)}원` }));
    return kids;
  };
  B.body.replaceChildren(head,
    h('table', { class: 'sp-tbl sp-dvx-t' },
      h('caption', { class: 'sp-vh', text: '최근 배당 기준일 · 지급일 · 1주당 배당금' }),
      h('thead', {}, h('tr', {}, h('th', { scope: 'col', text: '기준일' }), h('th', { scope: 'col', text: '지급일' }), h('th', { scope: 'col', text: '1주당' }))),
      h('tbody', {}, rows.map(r => h('tr', {}, h('td', { text: dotDate(r.recordDate) }), h('td', { text: r.payDate ? dotDate(r.payDate) : '—' }), h('td', { class: 'num' }, amt(r)))))),
    h('p', { class: 'sp-note', text: `배당 기준일은 금융위원회 자료 기준이에요. 회사 공시와 다를 수 있어요.${all.length > rows.length ? ` 최근 ${rows.length}건만 보여요.` : ''}` }),
    sdgSrc(j, lead));
}

/* 기업 정보: 대표자 · 설립일 · 종업원 수 … + 계열회사 · 종속기업(길면 "모두 보기" — 판만 자라요, design.md §7 펼치는 카드) */
function renderCorp() {
  const B = R.ci.corp, sig = sdgSig('corp');
  if (B.sig === sig) return;
  B.sig = sig;
  const st = sdgState('corp');
  B.el.hidden = st === 'gone';
  if (st === 'gone') return;
  if (st === 'idle') { B.body.replaceChildren(sdgIdle('corp')); return; }
  if (st === 'loading') { B.body.replaceChildren(sdgWait('corp', '기업 정보')); return; }
  if (st === 'err') { B.body.replaceChildren(sdgFail('corp', '기업 정보')); return; }
  const j = sdgHit('corp').j, o = j.outline && typeof j.outline === 'object' ? j.outline : null;
  const aff = j.affiliates && Array.isArray(j.affiliates.items) ? j.affiliates : null, sub = j.subsidiaries && Array.isArray(j.subsidiaries.items) ? j.subsidiaries : null;
  const lead = j.basDt ? sdgDay(j.basDt) + ' 공개 자료' : '';
  if (!o && !(aff && aff.count) && !(sub && sub.count)) {
    B.body.replaceChildren(msgBox('기업 정보가 없어요.', '금융위원회 기업기본정보에 이 회사 자료가 아직 없어요.'), sdgSrc(j, lead));
    return;
  }
  const rows = [];
  const add = (t, v, cls) => { if (v != null && v !== '') rows.push(h('div', { class: cls || null }, h('dt', { text: t }), h('dd', {}, v))); };
  if (o) {
    add('대표자', o.ceo);
    add('설립일', o.established ? longDate(o.established) : null, 'num');
    add('상장일', o.listed ? longDate(o.listed) : null, 'num');
    add('종업원 수', isNum(o.employees) ? int(o.employees) + '명' : null, 'num');
    add('결산월', isNum(o.settleMonth) ? `${o.settleMonth}월` : null);
    add('업종', o.industry, 'wide');
    add('주요 사업', o.business, 'wide');
    add('주소', o.address, 'wide');
    const url = safeUrl(o.homepage);
    if (url) add('홈페이지', h('a', { class: 'sp-cp-link', href: url, target: '_blank', rel: 'noopener' }, url.replace(/^https?:\/\//, '').replace(/\/$/, ''), h('span', { class: 'sp-vh', text: ' (새 탭)' })), 'wide');
  }
  const kids = [h('dl', { class: 'sp-cp-kv' }, rows)];
  if (aff && aff.count) kids.push(corpList('aff', '계열회사', aff, x => (x.listed ? '상장' : null)));
  if (sub && sub.count) kids.push(corpList('sub', '종속기업', sub, x => (x.main ? '주요' : null)));
  if (j.partial && j.partial.length) kids.push(h('p', { class: 'sp-inline-err', text: `${j.partial.map(p => (p === 'affiliates' ? '계열회사' : '종속기업')).join(' · ')} 목록은 이번에 받지 못했어요.` }));
  kids.push(sdgSrc(j, lead));
  B.body.replaceChildren(...kids);
}
function corpNames(key, g, tagOf, all) {
  const items = all ? g.items : g.items.slice(0, SDG_NAMES);
  return items.map((x, i) => { const t = tagOf(x); return h('li', { class: i >= SDG_NAMES ? 'x' : null }, String(x.name), t ? h('span', { class: 'sp-tag', text: t }) : null); });
}
function corpList(key, title, g, tagOf) {
  const id = 'sp-cp-' + key, open = !!SDG.open[key], more = g.items.length > SDG_NAMES;
  const list = h('ul', { class: 'sp-cp-names', id }, corpNames(key, g, tagOf, open));
  const skin = h('i', { class: 'sp-cp-skin', 'aria-hidden': 'true' });
  const grow = h('div', { class: 'sp-cp-grow' }, skin, list);
  const label = () => (SDG.open[key] ? '접기' : `${title} ${g.items.length}개 모두 보기`);
  const btn = more ? h('button', { type: 'button', class: 'sp-btn sp-fold sp-cp-more', 'aria-expanded': String(open), 'aria-controls': id,
    onclick: e => corpToggle(key, g, tagOf, grow, list, skin, e.currentTarget, label) }, h('span', { class: 'mt', text: label() })) : null;
  const capped = g.count > g.items.length ? h('small', { text: `${g.items.length}개까지 보여요` }) : null;
  return h('section', { class: 'sp-cp-sec', 'aria-labelledby': id + '-h' },
    h('h4', { class: 'sp-cp-h', id: id + '-h' }, title, h('b', { class: 'num', text: `${int(g.count)}개` }), g.basDt ? h('small', { text: shortDate(g.basDt) + ' 기준' }) : null, capped),
    grow, btn);
}
// design.md §7 펼치는 카드: the list's plate (.sp-cp-skin) grows with `open` / shrinks with `close`; the content below moves once —
// at the start when opening, after the plate when closing (no height animation of the layout). New names fade in after 25 %.
function corpToggle(key, g, tagOf, grow, list, skin, btn, label) {
  if (SDG.mv) SDG.mv.finish();
  const want = !SDG.open[key], was = btn.textContent;
  SDG.open[key] = want;
  btn.setAttribute('aria-expanded', String(want));
  const swapLabel = () => { const t = btn.querySelector('.mt'); if (UI && typeof UI.swap === 'function' && t) UI.swap(t, label(), was); else if (t) t.textContent = label(); };
  const springOk = KH.spring && typeof KH.spring.animate === 'function' && !reducedNow();
  if (!springOk) { list.replaceChildren(...corpNames(key, g, tagOf, want)); swapLabel(); return; }
  const me = { done: false };
  const finish = () => { if (me.done) return; me.done = true; if (me.h) me.h.stop(); if (SDG.mv === me) SDG.mv = null; me.end(); };
  me.finish = finish; SDG.mv = me;
  const run = (name, from, to, frame) => { me.h = KH.spring.animate({ from, to, name, onUpdate: v => { if (!me.done) frame(v); }, onRest: finish }); };
  if (want) {
    const H0 = grow.offsetHeight;
    list.replaceChildren(...corpNames(key, g, tagOf, true));               // the layout takes its new height here, once
    const H1 = grow.offsetHeight, D = H1 - H0;
    swapLabel();
    grow.classList.add('sp-cp-anim');
    let shown = false;
    me.end = () => { grow.classList.remove('sp-cp-anim', 'sp-cp-fadein'); grow.classList.add('sp-cp-in'); skin.style.height = ''; list.style.clipPath = ''; };
    const frame = p => {
      skin.style.height = (H0 + p * D).toFixed(1) + 'px';
      list.style.clipPath = `inset(0 0 ${Math.max(0, (1 - p) * D).toFixed(1)}px 0)`;
      if (!shown && p >= 0.25) { shown = true; grow.classList.add('sp-cp-fadein'); }
    };
    frame(0);
    run('open', 0, 1, frame);
    return;
  }
  // closing: the extra names leave first (together), then the plate shrinks, then the layout comes up once
  const H1 = grow.offsetHeight;
  grow.style.height = H1 + 'px';
  grow.classList.remove('sp-cp-in', 'sp-cp-fadein');
  grow.classList.add('sp-cp-out');
  swapLabel();
  let H0 = H1;
  me.end = () => {
    grow.classList.remove('sp-cp-anim', 'sp-cp-out');
    list.replaceChildren(...corpNames(key, g, tagOf, false));
    grow.style.height = ''; skin.style.height = ''; list.style.clipPath = '';
    const r = btn.getBoundingClientRect();
    if (r.top < (parseFloat(getComputedStyle(root).getPropertyValue('--sp-hh')) || 0) + 50) btn.scrollIntoView({ block: 'center' });
  };
  const t = setTimeout(() => {
    if (me.done) return;
    const probe = list.cloneNode(false); probe.replaceChildren(...corpNames(key, g, tagOf, false));
    probe.style.cssText = 'position:absolute;visibility:hidden;left:0;right:0;top:0'; grow.append(probe);
    H0 = probe.offsetHeight + (grow.offsetHeight - list.offsetHeight); probe.remove();
    const D = H1 - H0;
    grow.classList.add('sp-cp-anim');
    run('close', 0, 1, p => { skin.style.height = (H1 - p * D).toFixed(1) + 'px'; list.style.clipPath = `inset(0 0 ${(p * D).toFixed(1)}px 0)`; });
  }, 100);
  const end0 = me.end;
  me.end = () => { clearTimeout(t); end0(); };
}

/* ───────────────── open / close ───────────────── */
let inerted = [];
function setInert(on) {
  if (on) {
    for (const el of document.body.children) {
      if (el === root || /^(SCRIPT|STYLE|LINK|TEMPLATE)$/.test(el.tagName) || el.inert) continue;
      el.inert = true; inerted.push(el);
    }
  } else { for (const el of inerted) el.inert = false; inerted = []; }
}
function stopTimers() {
  if (LIVE) for (const t of TABS) if (t.hide) t.hide();
  clearTimeout(S.timers.sum); clearTimeout(S.timers.chart);
  S.timers.sum = S.timers.chart = 0;
}
function stopAll() { stopTimers(); abortAll(); }

// the phone's bottom bar hides while the page is open (themes.md §15-3): kh:stock {open}, once per open / close, not on a stock switch
function announce(open) { try { document.dispatchEvent(new CustomEvent('kh:stock', { detail: { open } })); } catch (e) { /* a listener must not break the page */ } }

function show(code, opener) {
  pickClose(false); ivClose(false, true);
  build();
  const switching = S.open;
  S.gen++;
  stopAll();
  Object.assign(S, { code, sum: null, sumErr: null, phase: 'unknown' });
  failed.clear();
  for (const t of TABS) if (t.reset) t.reset();
  if (!switching) {
    S.opener = opener && opener !== document.body ? opener : null;
    S.openerAt = S.opener ? openerAt(S.opener) : null;
    S.prevTitle = document.title;
    root.hidden = false;
    document.documentElement.classList.add('sp-on');
    setInert(true);
    root.classList.remove('sp-in');
    if (!reducedNow()) { void root.offsetWidth; root.classList.add('sp-in'); }
    S.open = true;
    announce(true);
  }
  root.scrollTop = 0;
  root.classList.remove('sp-nf');
  renderHead(); renderMeta(); renderStats(); renderPeers();
  measureHead();
  root.focus({ preventScroll: true });
  if (!LIVE) { renderOffline(); return; }
  syncTf();
  if (C.chart && C.code !== code) clearSeries();
  loadSummary();
  loadChart();
  setTab(S.tab);
}

function hide() {
  if (!S.open) return;
  pickClose(false); ivClose(false, true);
  S.open = false;
  S.gen++;
  stopAll();
  root.hidden = true;
  root.classList.remove('sp-in');
  document.documentElement.classList.remove('sp-on');
  setInert(false);
  if (S.prevTitle) document.title = S.prevTitle;
  announce(false);
  let o = S.opener;
  if (o && !o.isConnected) o = openerAgain(S.openerAt);   // the heatmap drew its list again while the page was open
  S.opener = null; S.openerAt = null;
  if (o && o.isConnected && typeof o.focus === 'function') { try { o.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
}
/* where the opener was (a path of child positions from the nearest id) and what it said (letters only: the numbers in a sector row change
 * with every quote), so focus can go back to the same row when the heatmap has replaced its elements meanwhile (AGENTS §5) */
const openerWords = el => (el.getAttribute('aria-label') || el.textContent || '').replace(/[\d\s.,%+\-−▲▼]/g, '').slice(0, 40);
function openerAt(el) {
  const path = [];
  let e = el;
  for (; e && e.parentElement && e !== document.body && !e.id; e = e.parentElement) path.unshift([...e.parentElement.children].indexOf(e) + 1);
  return e && (e.id || e === document.body) ? { root: e.id || null, path, tag: el.tagName, words: openerWords(el) } : null;
}
function openerAgain(at) {
  if (!at) return null;
  let e = at.root ? document.getElementById(at.root) : document.body;
  for (const i of at.path) e = e && e.children[i - 1];
  return e && e.tagName === at.tag && openerWords(e) === at.words && e.offsetParent !== null ? e : null;
}

function setHash(hash, replace) {
  const url = location.pathname + location.search + hash;
  try {
    if (replace) history.replaceState(history.state, '', url);
    else history.pushState(history.state, '', url);
    return true;
  } catch (e) {
    try { if (replace) location.replace(hash || '#'); else location.hash = hash; } catch (e2) { /* sandboxed */ }
    return false;
  }
}

function open(code, opts) {
  code = String(code || '').trim().toUpperCase();
  if (!CODE_RE.test(code)) return false;
  const opener = (opts && opts.opener) || document.activeElement;
  // a caller may ask for a tab (공시 배지 "공시 모두 보기" → {tab: 'news', newsKind: 'disc'}, disclosure.md §4-2)
  const wantTab = opts && TAB[opts.tab] ? opts.tab : null, wantKind = opts && NEWS_KIND[opts.newsKind] ? opts.newsKind : null;
  if (wantKind) { newsKind = wantKind; store.set('stockNewsKind', wantKind); }
  if (wantTab) { S.tab = wantTab; store.set('stockTab', wantTab); }
  const target = '#s-' + code;
  if (location.hash !== target) {
    if (S.open) setHash(target, true);             // switching stocks keeps one history entry: back always returns to the map
    else { S.prevHash = HASH_RE.test(location.hash) ? '' : location.hash; S.pushed = setHash(target, false); }
  }
  if (!S.open || S.code !== code) show(code, opener);
  else if (wantTab && R.tabs) setTab(wantTab);
  return true;
}

function close() {
  if (!S.open) return;
  const pushed = S.pushed;
  S.pushed = false;
  hide();
  if (HASH_RE.test(location.hash)) {
    if (pushed) history.back();                    // undo our own entry, so browser back/forward stay natural
    else setHash(S.prevHash || '', true);          // opened from a shared link: just drop the hash
  }
}

function onHash() {
  const m = HASH_RE.exec(location.hash);
  if (m) { if (!S.open || S.code !== m[1]) { if (!S.open) S.prevHash = ''; show(m[1], S.open ? null : document.activeElement); } }
  else if (S.open) { S.pushed = false; hide(); }
}

addEventListener('hashchange', onHash);
addEventListener('popstate', onHash);
// capture phase: the page owns Esc and '/' while it is open (the heatmap would otherwise zoom out / focus its search)
addEventListener('keydown', e => {
  if (!S.open) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); if (IVM.st === 'open') ivClose(true); else if (pickOpen()) pickClose(true); else close(); }
  else if (e.key === '/') e.stopImmediatePropagation();
}, true);
document.addEventListener('visibilitychange', () => {
  if (!S.open || !LIVE) return;
  if (document.visibilityState === 'visible') { loadSummary(true); TAB[S.tab].show(R.panels[S.tab]); scheduleIntraday(); }
  else stopTimers();   // loads already in flight may finish; nothing new starts while hidden
});
const recolour = () => { if (root) { applyColors(); if (S.open) renderPeers(); } };
document.addEventListener('kh:palette', recolour);
document.addEventListener('kh:theme', recolour);
document.addEventListener('kh:data', () => { if (S.open) { renderPeers(); renderHead(); if (LIVE) renderMeta(); } });
document.addEventListener('kh:basis', () => { if (S.open) renderHead(); });   // the headline is the row in the chosen basis   // 업종 path / provisional price arrive with the quotes
// a change of effect level ends whatever rolls or swaps in the header at its end value (design.md §6-3)
document.addEventListener('kh:motion', () => { if (R.price) for (const el of [R.price, R.chg, R.nxt.querySelector('.pv'), R.nxt.querySelector('.pr')]) numSettle(el); });
document.addEventListener('kh:watch', () => { if (S.open) renderStar(); });
document.addEventListener('kh:inv', () => { if (S.open && S.tab === 'inv') { if (famOn()) loadEst(true); else { S.est = null; paintEst(); } } });   // 가족 보기를 켜고 끔
document.addEventListener('kh:alerts', () => { if (S.open) { renderAl(); renderMeta(); } });   // the picker keeps its own ticks and counts in step

window.KHStock = { open, close, isOpen: () => S.open };
onHash();
})();
