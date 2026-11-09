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
const TFS = [['1d', '1일'], ['5d', '5일'], ['3m', '3개월'], ['1y', '1년'], ['3y', '3년'], ['10y', '10년']];
const TF_NAME = Object.fromEntries(TFS);
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
  { key: 'inv', label: '투자자', show: () => (S.inv || S.invLoading ? renderInv() : loadInv()), reset: invReset },
  { key: 'daily', label: '일별 시세', show: () => (S.daily ? renderDaily() : loadDaily(1)), reset: dailyReset, summary: renderDailyNote },
  { key: 'news', label: '뉴스·공시', build: buildNews, show: newsShow, reset: newsReset },
];
const TAB = Object.fromEntries(TABS.map(t => [t.key, t]));
const OB_MS = 3000, SUMMARY_MS = 30000, INTRADAY_MS = 60000;
const KST = 9 * 3600;
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const MINUS = '−';
const PHASE = {
  open: { chip: '장 중', live: true },
  after: { chip: '시간외', live: true, note: '정규장이 끝나 NXT·시간외 거래 중이에요' },
  pre: { chip: '장 시작 전', live: true },
  closed: { chip: '장 마감' },
  weekend: { chip: '주말 휴장', note: '주말이라 장이 열리지 않아요. 마지막 거래일 시세예요' },
  holiday: { chip: '휴장', note: '오늘은 장이 열리지 않아요. 마지막 거래일 시세예요' },
  unknown: { chip: '' },
};
const POLL_PHASES = new Set(['open', 'after', 'pre', 'unknown']);
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

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
function hexRgba(hex, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}
const chevron = () => svg('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg('path', { d: 'M15 5l-7 7 7 7' }));
function skel(w, hgt) { return h('span', { class: 'sp-skel', style: `width:${w};height:${hgt || '1em'}` }); }
function msgBox(title, sub, retry) {
  return h('div', { class: 'sp-msgbox', role: 'status' },
    h('p', { class: 'sp-msg-t', text: title }),
    sub ? h('p', { class: 'sp-msg-s', text: sub }) : null,
    retry ? h('button', { type: 'button', class: 'sp-btn', onclick: retry, text: '다시 시도' }) : null);
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
  tf: TF_NAME[store.get('stockTf', '1d')] ? store.get('stockTf', '1d') : '1d',
  tab: TAB[store.get('stockTab', TABS[0].key)] ? store.get('stockTab', TABS[0].key) : TABS[0].key,
  sum: null, sumErr: null, phase: 'unknown',
  ob: null, obErr: null, obAt: null,              // 호가 tab
  inv: null, invErr: null, invLoading: false,     // 투자자 tab
  daily: null,                                    // 일별 시세 tab
  news: { news: null, disc: null },               // 뉴스·공시 tab: per list {loading, err} while fetching (rows live in newsCache)
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
  R.star = h('button', { class: 'sp-star', type: 'button', 'aria-label': '관심종목', 'aria-pressed': 'false', hidden: true, onclick: toggleWatch },
    svg('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true' }, svg('path', { d: 'M12 3.4l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6-4.4-4.2 6-.8z' })));
  R.head = h('header', { class: 'sp-head' }, h('div', { class: 'sp-head-in' }, R.back,
    h('div', { class: 'sp-id' }, R.name, h('div', { class: 'sp-sub' }, R.code, R.mkt, R.path)),
    h('div', { class: 'sp-quote', 'aria-live': 'polite' }, R.price, R.chg, R.lim),
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
  R.tfs = h('div', { class: 'sp-seg sp-tfs', role: 'group', 'aria-label': '차트 기간' },
    TFS.map(([k, label]) => h('button', { type: 'button', 'data-tf': k, 'aria-pressed': 'false', onclick: () => setTf(k), text: label })));
  R.period = h('div', { class: 'sp-period num' });
  R.chart = h('div', { class: 'sp-chart', role: 'img', 'aria-label': '가격 차트' });
  R.legend = h('div', { class: 'sp-legend num', 'aria-hidden': 'true' });
  R.chartMsg = h('div', { class: 'sp-chartmsg' });
  const chartcol = h('section', { class: 'sp-chartcol', 'aria-label': '가격 차트' },
    h('div', { class: 'sp-tfbar' }, R.tfs, R.period),
    h('div', { class: 'sp-chartwrap' }, R.chart, R.legend, R.chartMsg),
    R.peers);
  R.tabs = h('div', { class: 'sp-seg sp-tabs', role: 'tablist', 'aria-label': '시세 정보' });
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
    setTab(keys[i], true);
  });
  for (const t of TABS) if (t.build) t.build(R.panels[t.key]);
  R.body.append(chartcol, h('section', { class: 'sp-side', 'aria-label': TABS.map(t => t.label).join('·') }, h('div', { class: 'sp-tabwrap' }, R.tabs), ...Object.values(R.panels)));
  R.foot.append(h('p', {}, '데이터: 네이버 증권(비공식). 투자 판단의 근거로 쓰지 마세요. 차트: ',
    h('a', { href: 'https://www.tradingview.com/', target: '_blank', rel: 'noopener', text: 'TradingView Lightweight Charts™' }), '.'));
}

function buildSnapshot() {
  R.offline = h('div', { class: 'sp-offline' });
  R.body.append(R.offline, R.peers);
  R.foot.append(h('p', { text: `데이터: 네이버 증권. ${asOfLabel(KH.asOf())} 기준 스냅샷이라 시세가 바뀌지 않아요. 투자 판단의 근거로 쓰지 마세요.` }));
}

function measureHead() {
  if (root && !root.hidden) root.style.setProperty('--sp-hh', R.head.offsetHeight + 'px');
}

/* ───────────────── header ───────────────── */
function renderHead() {
  const st = KH.stock(S.code), s = S.sum;
  const name = (s && s.name) || (st && st.n) || (LIVE && !S.sumErr ? '' : S.code);
  R.name.replaceChildren(name || skel('6em', '0.9em'));
  R.code.textContent = name === S.code ? '' : S.code;
  const m = (s && s.market) || (st && st.m);
  R.mkt.textContent = m ? KH.MKT_NAME[m] || '' : '';
  R.path.textContent = st && st.s ? `${st.s} › ${st.i}` : '';
  R.path.hidden = !(st && st.s);
  let price = null, chg = null, ratio = null;
  if (s && isNum(s.price)) { price = +s.price; chg = +s.change; ratio = +s.ratio; }
  else if (st) { price = st.p; chg = st.d; ratio = st.r; }
  if (price == null) {
    R.price.replaceChildren(S.sumErr ? '—' : skel('5.2em', '0.85em'));
    R.chg.replaceChildren(S.sumErr ? '' : skel('6.5em', '0.8em'));
    R.chg.className = 'sp-chg num';
  } else {
    R.price.textContent = int(price);
    const arrow = chg > 0 ? '▲' : chg < 0 ? '▼' : '';
    R.chg.className = 'sp-chg num ' + cls(chg);
    R.chg.textContent = `${arrow}${isNum(chg) ? int(Math.abs(chg)) : ''}  ${pct(ratio)}`;
    R.chg.setAttribute('aria-label', `전일 대비 ${signed(chg)}원, ${pct(ratio)}`);
  }
  renderLim();
  renderStar();
  if (name) document.title = `${name} ${price != null ? int(price) : ''} ${price != null ? pct(ratio) : ''} · 한국 증시 히트맵`.replace(/\s+/g, ' ');
}

// 상한가·하한가: the quote row's lim (1/−1). Rows without lim (older data) or stocks outside the quote universe fall back to
// |등락률| ≥ 29.5 — a limit move can round to +29.87%, so never test ≥ 30 (data/ENDPOINTS_EXTRA.md §5).
function limitOf() {
  const st = KH.stock(S.code);
  if (st && st.lim != null) return st.lim === 1 || st.lim === -1 ? st.lim : 0;
  const r = st && isNum(st.r) ? +st.r : S.sum && S.sum.code === S.code && isNum(S.sum.ratio) ? +S.sum.ratio : null;
  return r == null ? 0 : r >= 29.5 ? 1 : r <= -29.5 ? -1 : 0;
}
function renderLim() {
  const lim = limitOf();
  R.lim.hidden = !lim;
  R.lim.className = 'sp-lim' + (lim > 0 ? ' up' : lim < 0 ? ' dn' : '');
  R.lim.textContent = lim > 0 ? '상한가' : lim < 0 ? '하한가' : '';
}

// 관심종목: KH.watch comes from the heatmap (AGENTS.md §3-2). Without it the star stays hidden.
const watchApi = () => (KH.watch && typeof KH.watch.has === 'function' && typeof KH.watch.toggle === 'function' ? KH.watch : null);
function renderStar() {
  const W = watchApi();
  R.star.hidden = !W || !S.code;
  if (R.star.hidden) return;
  const on = !!W.has(S.code);
  R.star.setAttribute('aria-pressed', String(on));
  R.star.title = on ? '관심종목에서 빼기' : '관심종목에 넣기';
}
function toggleWatch() {
  const W = watchApi();
  if (!W || !S.code) return;
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
    if (S.sum && S.sum.asOf) kids.push(h('span', { text: `네이버 증권 · ${asOfLabel(S.sum.asOf)} 기준` }));
    if (nxtApplies()) kids.push(h('span', { class: 'sp-nxt', title: '정규장(15:30)이 끝난 뒤의 가격이라 NXT와 시간외 거래가 섞여 있어요.', text: 'NXT·시간외 거래 포함' }));
    if (ph.note && S.phase !== 'after') kids.push(h('span', { class: 'sp-phase-note', text: ph.note }));
    if (!S.sum && !S.sumErr) kids.push(skel('14em', '0.9em'));
    if (S.sumErr) {
      kids.push(h('span', { class: 'sp-meta-err', role: 'status' }, S.sumErr.status === 404 ? '이 코드의 종목을 찾지 못했어요.' : '시세 요약을 불러오지 못했어요.',
        h('button', { type: 'button', class: 'sp-link', onclick: () => { S.sumErr = null; renderMeta(); renderStats(); loadSummary(); }, text: '다시 시도' })));
    }
  }
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
  if (!s) {
    R.stats.replaceChildren(...['시가총액', 'PER', 'PBR', '배당수익률', '외국인 보유율'].map(l => statItem(l, skel('4em', '0.9em'))), statItem('52주 최저·최고', skel('100%', '0.9em'), 'sp-rng'));
    return;
  }
  const lo = s.low52, hi = s.high52, p = s.price;
  let rng = '—';
  if (isNum(lo) && isNum(hi) && hi > lo) {
    const x = Math.max(0, Math.min(1, (p - lo) / (hi - lo)));
    rng = [h('span', { class: 'lo', text: int(lo) }),
      h('span', { class: 'track', role: 'img', 'aria-label': `52주 범위에서 현재가 위치 ${Math.round(x * 100)}%` }, h('i', { style: `left:${(x * 100).toFixed(1)}%` })),
      h('span', { class: 'hi', text: int(hi) })];
  }
  R.stats.replaceChildren(
    statItem('시가총액', isNum(s.marketCap) ? F.eok(+s.marketCap) : '—'),
    statItem('PER', fixed(s.per, 2, '배')),
    statItem('PBR', fixed(s.pbr, 2, '배')),
    statItem('배당수익률', fixed(s.dividendYield, 2, '%')),
    statItem('외국인 보유율', fixed(s.foreignRate, 2, '%')),
    statItem('52주 최저·최고', rng, 'sp-rng'));
}

function renderPeers() {
  const st = KH.stock(S.code);
  const list = st && st.s ? KH.stocks().filter(x => x.s === st.s && x.i === st.i && x.c !== st.c && x.c.slice(-1) === '0').sort((a, b) => b.cap - a.cap).slice(0, 12) : [];
  R.peers.hidden = !list.length;
  if (!list.length) { R.peers.replaceChildren(); return; }
  R.peers.replaceChildren(h('h2', { class: 'sp-peers-t', text: '같은 업종' }),
    h('div', { class: 'sp-peer-list' }, list.map(x => h('button', { type: 'button', class: 'sp-peer', onclick: () => open(x.c), 'aria-label': `${x.n} ${pct(x.r)} 보기` },
      h('span', { class: 'nm', text: x.n }), h('span', { class: 'num ' + cls(x.r), text: pct(x.r) })))));
}

function renderOffline() {
  const st = KH.stock(S.code);
  const href = KH.LIVE_URL + '#s-' + S.code;
  R.offline.replaceChildren(
    svg('svg', { class: 'sp-off-ic', viewBox: '0 0 48 48', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round' },
      svg('path', { d: 'M6 40h36' }), svg('path', { d: 'M12 30v-8M12 34v-2M20 26V12M20 30v-2M28 32V20M28 36v-2M36 22v-12M36 26v-2' })),
    h('h2', { text: st ? '차트·호가·투자자 정보는 실시간 버전에서 볼 수 있어요' : '이 종목은 스냅샷에 없어요' }),
    h('p', { text: st ? `이 화면은 ${asOfLabel(KH.asOf())} 기준 스냅샷이라 새 시세를 받아 오지 않아요. 일별 시세와 뉴스·공시도 실시간 버전에 있어요.` : `코드 ${S.code}의 시세는 실시간 버전에서 확인해 주세요.` }),
    h('a', { class: 'sp-btn pri', href, target: '_blank', rel: 'noopener', text: '실시간 버전에서 열기' }));
}

/* ───────────────── summary ───────────────── */
async function loadSummary(quiet) {
  const g = S.gen;
  clearTimeout(S.timers.sum);
  try {
    const j = await api('summary', 'sum');
    if (g !== S.gen) return;
    S.sum = j; S.sumErr = null;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return;
    if (!quiet || !S.sum) S.sumErr = e;
  }
  const before = S.phase;
  S.phase = phaseOf(S.sum);
  root.classList.toggle('sp-nf', !!(S.sumErr && S.sumErr.status === 404 && !KH.stock(S.code)));
  renderHead(); renderMeta(); renderStats();
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

const C = { chart: null, candles: null, vol: null, prevLine: null, bars: null, index: new Map(), tf: null, ref: null, cache: new Map() };
const timeKey = t => (t && typeof t === 'object' ? `${t.year}-${pad(t.month)}-${pad(t.day)}` : t);
function timeParts(t) {
  if (typeof t === 'number') { const d = new Date(t * 1000); return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), wd: d.getUTCDay(), hh: d.getUTCHours(), mm: d.getUTCMinutes() }; }
  const [y, m, d] = typeof t === 'string' ? t.split('-').map(Number) : [t.year, t.month, t.day];
  return { y, m, d, wd: new Date(Date.UTC(y, m - 1, d)).getUTCDay(), hh: 0, mm: 0 };
}
function timeLabel(t, tf) {
  const p = timeParts(t);
  switch (tf || C.tf) {
    case '1d': return `${p.m}월 ${p.d}일 ${pad(p.hh)}:${pad(p.mm)}`;
    case '5d': return `${p.m}월 ${p.d}일 (${WD[p.wd]}) ${pad(p.hh)}:${pad(p.mm)}`;
    case '3y': { const q = p.wd === 0 ? timeParts(new Date(Date.UTC(p.y, p.m - 1, p.d + 1)).toISOString().slice(0, 10)) : p; return `${q.y}.${pad(q.m)}.${pad(q.d)} 주`; }   // Naver weeks start on Sunday
    case '10y': return `${p.y}년 ${p.m}월`;
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
  const chart = L.createChart(R.chart, {
    autoSize: true,
    layout: { background: { type: L.ColorType.Solid, color: '#191a1f' }, textColor: '#8a8f99', fontSize: 11, fontFamily: font, attributionLogo: true,
      panes: { separatorColor: '#2b2d34', separatorHoverColor: 'rgba(255,255,255,.06)', enableResize: false } },
    grid: { vertLines: { color: 'rgba(255,255,255,.035)' }, horzLines: { color: 'rgba(255,255,255,.045)' } },
    crosshair: { mode: L.CrosshairMode.Normal,
      vertLine: { color: '#8a8f99', width: 1, style: L.LineStyle.Dashed, labelBackgroundColor: '#373a42' },
      horzLine: { color: '#8a8f99', width: 1, style: L.LineStyle.Dashed, labelBackgroundColor: '#373a42' } },
    rightPriceScale: { borderColor: '#2b2d34', scaleMargins: { top: 0.16, bottom: 0.06 } },
    timeScale: { borderColor: '#2b2d34', rightOffset: 2, fixLeftEdge: true, fixRightEdge: true, lockVisibleTimeRangeOnResize: true, tickMarkFormatter: tickLabel },
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
    renderLegend(i);
  });
  Object.assign(C, { chart, candles, vol, L });
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
const FLAT = '#8a8f99';
function candleData(bars) { return bars.map(b => b.c === b.o ? { time: b.time, open: b.o, high: b.h, low: b.l, close: b.c, color: FLAT, wickColor: FLAT } : { time: b.time, open: b.o, high: b.h, low: b.l, close: b.c }); }
function volData(bars) {
  const P = KH.palette(), up = hexRgba(P.up, 0.55), dn = hexRgba(P.down, 0.55), fl = hexRgba(FLAT, 0.45);
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
  } else if (kind === 'error') m.replaceChildren(msgBox('차트를 불러오지 못했어요.', errSub(err), () => loadChart(true)));
  else if (kind === 'lib') m.replaceChildren(msgBox('차트 도구를 불러오지 못했어요.', '네트워크 연결을 확인하고 다시 시도해 주세요.', () => loadChart(true)));
  else if (kind === 'empty') {
    const pre = (S.tf === '1d') && S.phase === 'pre';
    m.replaceChildren(msgBox(pre ? '오늘은 아직 거래가 없어요.' : '이 기간에는 거래 기록이 없어요.', pre ? '9시에 정규장이 열리면 차트가 그려져요.' : '다른 기간을 골라 보세요.'));
  }
}

async function loadChart(force) {
  const g = S.gen, tf = S.tf, code = S.code;
  const key = code + '|' + tf;
  if (C.code !== code) C.bars = null;   // old candles stay under a dim overlay only while the same stock changes period
  chartState('loading');
  try { await ensureChart(); } catch (e) { if (g === S.gen && tf === S.tf) chartState('lib'); return; }
  if (g !== S.gen || tf !== S.tf) return;
  const hit = C.cache.get(key);
  let j = !force && hit && Date.now() - hit.at < (tf === '1d' || tf === '5d' ? 20e3 : 600e3) ? hit.j : null;
  if (!j) {
    try { j = await api('chart?tf=' + tf, 'chart'); } catch (e) {
      if (aborted(e) || g !== S.gen || tf !== S.tf) return;
      C.bars = null; C.candles.setData([]); C.vol.setData([]); renderLegend(); renderPeriod();
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
function computeRefs() {
  const bars = C.bars || [];
  C.ref = C.intraday ? (sumRef() != null ? sumRef() : C.tf === '1d' ? C.base : null) : null;
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
  if (C.ref != null && C.bars && C.bars.length) C.prevLine = C.candles.createPriceLine({ price: C.ref, color: '#8a8f99', lineWidth: 1, lineStyle: C.L.LineStyle.Dashed, axisLabelVisible: true, title: '전일 종가', axisLabelColor: '#373a42', axisLabelTextColor: '#eef0f3' });
}
// the last-price label follows the day's change (as in the header), not the last candle's own colour
function lastColor() {
  const d = S.sum && S.sum.code === S.code && isNum(S.sum.change) ? +S.sum.change : null;
  if (d == null) return '';
  const P = KH.palette();
  return d > 0 ? P.up : d < 0 ? P.down : FLAT;
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

function setChartData(j, code, tf, keepRange) {
  const intraday = tf === '1d' || tf === '5d';
  const bars = sanitize(j && j.bars, intraday);
  const range = keepRange ? C.chart.timeScale().getVisibleLogicalRange() : null;
  C.code = code; C.tf = tf; C.bars = bars; C.intraday = intraday;
  C.base = isNum(j && j.prevClose) && +j.prevClose > 0 ? +j.prevClose : null;
  computeRefs();
  C.index = new Map(bars.map((b, i) => [b.time, i]));
  C.volCap = 0;
  if (intraday && bars.length > 40) {
    const v = bars.map(b => b.v).sort((a, b) => a - b), cap = v[Math.floor(v.length * 0.97)] * 1.8;
    if (cap > 0 && v[v.length - 1] > cap) C.volCap = cap;
  }
  if (C.prevLine) { C.candles.removePriceLine(C.prevLine); C.prevLine = null; }
  C.candles.applyOptions({ priceLineColor: lastColor() });
  C.chart.applyOptions({ timeScale: { timeVisible: intraday, secondsVisible: false } });
  if (!bars.length) {
    C.candles.setData([]); C.vol.setData([]);
    renderLegend(); renderPeriod(); chartState('empty');
    R.chart.setAttribute('aria-label', `${TF_NAME[tf]} 차트: 거래 기록이 없어요`);
    return;
  }
  const cdata = candleData(bars);
  if (tf === '1d' && S.phase === 'open') {
    // leave room for the rest of the regular session (until 15:30 KST)
    const last = bars[bars.length - 1].time, p = timeParts(last);
    const end = Date.UTC(p.y, p.m - 1, p.d, 15, 30) / 1000;
    for (let t = last + 60; t <= end; t += 60) cdata.push({ time: t });
  }
  C.candles.setData(cdata);
  C.vol.setData(volData(bars));
  drawRefLine();
  if (range) C.chart.timeScale().setVisibleLogicalRange(range); else C.chart.timeScale().fitContent();
  chartState('ok');
  renderLegend(); renderPeriod(); fitMargins();
  const first = bars[0], last = bars[bars.length - 1];
  R.chart.setAttribute('aria-label', `${R.name.textContent} ${TF_NAME[tf]} 차트. ${timeLabel(first.time, tf)} ${int(first.o)}원에서 ${timeLabel(last.time, tf)} ${int(last.c)}원까지, 봉 ${bars.length}개.`);
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
  if (C.tf === '1d' && C.ref != null) {
    const r = (last / C.ref - 1) * 100;
    R.period.replaceChildren(h('span', { text: `전일 종가 ${int(C.ref)} 대비 ` }), h('b', { class: cls(r), text: pct(r) }));
  } else {
    // from the close before the first bar (falls back to the first bar's open)
    const base = C.base != null ? C.base : bars[0].o, r = (last / base - 1) * 100;
    R.period.replaceChildren(h('span', { text: `${TF_NAME[C.tf]} 동안 ` }), h('b', { class: cls(r), text: pct(r) }));
  }
}
function applyColors() {
  if (!C.candles) return;
  const P = KH.palette();
  C.candles.applyOptions({ upColor: P.up, downColor: P.down, wickUpColor: P.up, wickDownColor: P.down, priceLineColor: lastColor() });
  if (C.bars && C.bars.length) C.vol.setData(volData(C.bars));
}
function scheduleIntraday() {
  clearTimeout(S.timers.chart);
  if (LIVE && S.open && document.visibilityState === 'visible' && S.tf === '1d' && (S.phase === 'open' || S.phase === 'after'))
    S.timers.chart = setTimeout(refreshIntraday, INTRADAY_MS);
}
async function refreshIntraday() {
  const g = S.gen, tf = S.tf, code = S.code;
  if (!C.chart || tf !== '1d') return;
  try {
    const j = await api('chart?tf=' + tf, 'chart');
    if (g !== S.gen || tf !== S.tf) return;
    C.cache.set(code + '|' + tf, { at: Date.now(), j });
    setChartData(j, code, tf, true);
  } catch (e) { /* keep the current picture; try again on the next tick */ }
  if (g === S.gen) scheduleIntraday();
}
function setTf(k) {
  if (!TF_NAME[k]) return;
  S.tf = k; store.set('stockTf', k);
  syncTf();
  loadChart();
}
function syncTf() { if (R.tfs) for (const b of R.tfs.children) b.setAttribute('aria-pressed', String(b.dataset.tf === S.tf)); }

/* ───────────────── tabs ───────────────── */
function setTab(k, focus) {
  if (!TAB[k]) k = TABS[0].key;
  S.tab = k; store.set('stockTab', k);
  for (const b of R.tabs.children) {
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
}

/* ── 호가 ── */
let obLoop = 0;
const obShouldPoll = () => LIVE && S.open && S.tab === 'ob' && document.visibilityState === 'visible';
const obPolling = () => obShouldPoll() && POLL_PHASES.has(S.phase);   // the book stands still once the market is shut
function obReset() { S.ob = null; S.obErr = null; S.obAt = null; }
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
async function obTick(id) {
  S.timers.ob = 0;
  if (id !== obLoop || !obShouldPoll()) return;
  S.timers.ob = -1;   // in flight
  try {
    const j = await api('orderbook', 'ob');
    if (id !== obLoop) return;
    S.ob = j; S.obErr = null; S.obAt = new Date();
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
    ob.msg.replaceChildren(S.obErr ? msgBox('호가를 불러오지 못했어요.', errSub(S.obErr) + (obPolling() ? ' 3초마다 다시 시도해요.' : ''), obStart)
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

/* ── 투자자 ── */
function invReset() { S.inv = null; S.invErr = null; S.invLoading = false; }
async function loadInv() {
  const g = S.gen;
  S.invLoading = true; S.invErr = null;
  renderInv();
  try {
    const j = await api('investors', 'inv');
    if (g !== S.gen) return;
    S.inv = Array.isArray(j.rows) ? j.rows : [];
  } catch (e) {
    if (aborted(e) || g !== S.gen) return;
    S.invErr = e;
  }
  S.invLoading = false;
  renderInv();
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
function netCell(v) { return h('td', { class: 'num ' + cls(v) }, h('span', { class: 'l', text: signed(v) }), h('span', { class: 's', text: signedCompact(v) })); }
function renderInv() {
  const P = R.panels.inv;
  if (S.invErr) { P.replaceChildren(msgBox('투자자별 매매를 불러오지 못했어요.', errSub(S.invErr), loadInv)); return; }
  if (!S.inv) { P.replaceChildren(h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '투자자 정보 불러오는 중' }, skel('100%', '96px'), Array.from({ length: 8 }, () => skel('100%', '26px')))); return; }
  const rows = S.inv;
  if (!rows.length) { P.replaceChildren(msgBox('투자자별 매매 기록이 없어요.', '새로 상장했거나 거래가 적은 종목일 수 있어요.')); return; }
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
  const today = kst(new Date()), lp = lastDate.split('-').map(Number);
  const isToday = lp[0] * 10000 + lp[1] * 100 + lp[2] === today.key;
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
  P.replaceChildren(card, note, h('table', { class: 'sp-tbl sp-inv-t' }, h('caption', { text: '날짜별 순매수 (단위: 주, 만 = 1만 주)' }), thead, tbody));
}

/* ── 일별 시세 ── */
function dailyReset() { S.daily = null; R.dailyTbody = null; }
async function loadDaily(page) {
  const g = S.gen;
  if (!S.daily) S.daily = { rows: [], page: 0, hasMore: false, loading: false, err: null };
  const D = S.daily;
  if (D.loading) return;
  D.loading = true; D.err = null;
  renderDaily();
  try {
    const j = await api('daily?page=' + page, 'daily');
    if (g !== S.gen) return;
    const rows = Array.isArray(j.rows) ? j.rows : [];
    const seen = new Set(D.rows.map(r => r.date));
    D.rows.push(...rows.filter(r => r && r.date && !seen.has(r.date)));
    D.page = page; D.hasMore = !!j.hasMore && rows.length > 0;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return;
    D.err = e;
  }
  D.loading = false;
  renderDaily();
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
    if (D.err) P.replaceChildren(msgBox('일별 시세를 불러오지 못했어요.', errSub(D.err), () => loadDaily(1)));
    else if (D.loading) P.replaceChildren(h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': '일별 시세 불러오는 중' }, Array.from({ length: 12 }, () => skel('100%', '26px'))));
    else P.replaceChildren(msgBox('일별 시세가 없어요.', '새로 상장한 종목이면 거래가 쌓인 뒤에 보여요.'));
    return;
  }
  if (!R.dailyTbody || !P.contains(R.dailyTbody)) {
    R.dailyTbody = h('tbody');
    R.dailyMore = h('button', { type: 'button', class: 'sp-btn sp-more', onclick: () => loadDaily(S.daily.page + 1) });
    R.dailyErr = h('p', { class: 'sp-inline-err', role: 'status' });
    R.dailyNote = h('p', { class: 'sp-note', text: '오늘 행은 KRX 정규장 기준이라 위 현재가(NXT·시간외 포함)와 다를 수 있어요.' });
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
  R.dailyMore.disabled = D.loading;
  R.dailyMore.textContent = D.loading ? '불러오는 중…' : D.err ? '다시 시도' : '더 보기';
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
async function loadNews(kind) {
  const code = S.code, g = S.gen, key = code + '|' + kind;
  const hit = newsCache.get(key);
  if ((hit && Date.now() - hit.at < NEWS_TTL) || (S.news[kind] && S.news[kind].loading)) return;
  S.news[kind] = { loading: true, err: null };
  try {
    const j = await api(NEWS_KIND[kind].path, 'nw-' + kind);
    if (g !== S.gen) return;
    newsCache.set(key, { at: Date.now(), rows: Array.isArray(j.rows) ? j.rows.filter(r => r && r.title) : [],
      source: j.source === 'dart' ? 'dart' : kind === 'disc' ? 'naver' : null });
    S.news[kind] = null;
  } catch (e) {
    if (aborted(e) || g !== S.gen) return;
    S.news[kind] = { loading: false, err: e };
  }
  if (S.tab === 'news') renderNews();
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
    seg: h('div', { class: 'sp-nwseg', role: 'group', 'aria-label': '뉴스·공시 고르기' },
      NEWS_KINDS.map(k => h('button', { type: 'button', 'data-kind': k.key, 'aria-pressed': 'false', onclick: () => setNewsKind(k.key) },
        h('span', { text: k.label }), h('small', { class: 'num' })))),
    filters: h('div', { class: 'sp-dfilt', role: 'group', 'aria-label': '공시 종류', hidden: true },
      DISC_FILTERS.map(f => h('button', { type: 'button', 'data-f': f, 'aria-pressed': 'false', onclick: () => setDiscFilter(f) },
        h('span', { text: f }), h('small', { class: 'num' })))),
    src: h('div', { class: 'sp-nw-src', hidden: true }),
    body: h('div', { class: 'sp-nw-body' }),
    note: h('p', { class: 'sp-note' }),
  };
  R.nw.srcText = h('span');
  R.nw.equity = h('button', { type: 'button', class: 'sp-switch', role: 'switch', 'aria-checked': 'false', onclick: () => setDiscEquity(!discEquity) },
    h('span', { class: 'sp-switch-t', text: '지분 공시 포함' }), h('i', { 'aria-hidden': 'true' }));
  R.nw.src.append(R.nw.srcText, R.nw.equity);
  panel.append(R.nw.seg, R.nw.filters, R.nw.src, R.nw.body, R.nw.note);
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
  if (d) meta.push(h('time', { datetime: d.toISOString(), title: fullTime(d), text: relTime(d, now) }));
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
  for (const b of R.nw.seg.children) {
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
    for (const b of R.nw.filters.children) {
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
  else if (st && st.err) body = msgBox(`${meta.label}를 불러오지 못했어요.`, errSub(st.err), () => { loadNews(kind); renderNews(); });
  else body = h('div', { class: 'sp-skel-rows', role: 'status', 'aria-label': `${meta.label} 불러오는 중` }, Array.from({ length: 6 }, () => skel('100%', '52px')));
  R.nw.body.replaceChildren(body);
  R.nw.note.textContent = meta.note;
  R.nw.note.hidden = !(rows && rows.length);
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

function show(code, opener) {
  build();
  const switching = S.open;
  S.gen++;
  stopAll();
  Object.assign(S, { code, sum: null, sumErr: null, phase: 'unknown' });
  for (const t of TABS) if (t.reset) t.reset();
  if (!switching) {
    S.opener = opener && opener !== document.body ? opener : null;
    S.prevTitle = document.title;
    root.hidden = false;
    document.documentElement.classList.add('sp-on');
    setInert(true);
    root.classList.remove('sp-in');
    if (!reduceMotion.matches) { void root.offsetWidth; root.classList.add('sp-in'); }
    S.open = true;
  }
  root.scrollTop = 0;
  root.classList.remove('sp-nf');
  renderHead(); renderMeta(); renderStats(); renderPeers();
  measureHead();
  root.focus({ preventScroll: true });
  if (!LIVE) { renderOffline(); return; }
  syncTf();
  if (C.chart && C.code !== code) { C.bars = null; C.candles.setData([]); C.vol.setData([]); renderLegend(); renderPeriod(); }
  loadSummary();
  loadChart();
  setTab(S.tab);
}

function hide() {
  if (!S.open) return;
  S.open = false;
  S.gen++;
  stopAll();
  root.hidden = true;
  root.classList.remove('sp-in');
  document.documentElement.classList.remove('sp-on');
  setInert(false);
  if (S.prevTitle) document.title = S.prevTitle;
  const o = S.opener;
  S.opener = null;
  if (o && o.isConnected && typeof o.focus === 'function') { try { o.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
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
  const target = '#s-' + code;
  if (location.hash !== target) {
    if (S.open) setHash(target, true);             // switching stocks keeps one history entry: back always returns to the map
    else { S.prevHash = HASH_RE.test(location.hash) ? '' : location.hash; S.pushed = setHash(target, false); }
  }
  if (!S.open || S.code !== code) show(code, opener);
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
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
  else if (e.key === '/') e.stopImmediatePropagation();
}, true);
document.addEventListener('visibilitychange', () => {
  if (!S.open || !LIVE) return;
  if (document.visibilityState === 'visible') { loadSummary(true); TAB[S.tab].show(R.panels[S.tab]); scheduleIntraday(); }
  else stopTimers();   // loads already in flight may finish; nothing new starts while hidden
});
document.addEventListener('kh:palette', () => { if (root) { applyColors(); if (S.open) renderPeers(); } });
document.addEventListener('kh:data', () => { if (S.open) { renderPeers(); renderHead(); } });   // 업종 path / provisional price arrive with the quotes
document.addEventListener('kh:watch', () => { if (S.open) renderStar(); });

window.KHStock = { open, close, isOpen: () => S.open };
onHash();
})();
