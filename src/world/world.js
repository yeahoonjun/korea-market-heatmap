/* 해외 지수 · 원자재 tabs (AGENTS.md §3-4).
   window.KHWorld = { show(kind), hide(), layout(), shown() }   kind: 'index' | 'commodity'
   The template shows <div id="world"> (in place of the map + side cards) and calls show(); another tab calls hide().
   Data (live only): GET api/world?kind=…  every 30 s while shown and the browser tab is visible;
                     GET api/world/chart/{key}?tf=3m|1y for the detail sheet (daily closes; no intraday source exists).
   Uses window.KH (§3): MODE, LIVE_URL, colorOf, palette, fmt, h, market; listens to kh:palette. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function') return;          // the heatmap script did not boot
const h = KH.h;
const LIVE = KH.MODE === 'live';
const MINUS = '−';
const POLL_MS = 30000, RETRY_MS = 15000, TIMEOUT_MS = 12000;
const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
const narrowMQ = matchMedia('(max-width: 760px)');
const SVGNS = 'http://www.w3.org/2000/svg';
const NODATA = '#26282e';

const KINDS = {
  index: {
    title: '해외 지수', hash: 'world', noun: '지수',
    fail: '해외 지수를 불러오지 못했어요', empty: '지금 보여 줄 해외 지수가 없어요',
    snapTitle: '해외 지수는 실시간 버전에서 볼 수 있어요',
    snapBody: '미국·유럽·아시아 주요 지수와 미국 지수 선물을 30초마다 새로 받아 와요. 이 미리보기는 네트워크가 막혀 있어서 시세를 받을 수 없어요.',
  },
  commodity: {
    title: '원자재', hash: 'cmdty', noun: '원자재',
    fail: '원자재 시세를 불러오지 못했어요', empty: '지금 보여 줄 원자재 시세가 없어요',
    snapTitle: '원자재 시세는 실시간 버전에서 볼 수 있어요',
    snapBody: '원유·천연가스·금·은·구리·곡물 같은 원자재 선물 시세를 30초마다 새로 받아 와요. 이 미리보기는 네트워크가 막혀 있어서 시세를 받을 수 없어요.',
  },
};

/* tile size: headline markets bigger (size carries no data, the legend says so) */
const WEIGHT = {
  INX: 3, IXIC: 3, N225: 3, HSI: 3, GDAXI: 3, CLcv1: 3, GCcv1: 3,
  DJI: 2, NDX: 2, STOXX50E: 2, FTSE: 2, SSEC: 2, LCOcv1: 2, SIcv1: 2, HGcv1: 2,
  SOX: 1.6, FCHI: 1.6, TWII: 1.6, KOSPI: 1.6, EScv1: 1.6, NQcv1: 1.6, NGcv1: 1.6, BSESN: 1.4, CSI300: 1.3, TOPX: 1.3,
  Ccv1: 1.3, Scv1: 1.3, Wcv1: 1.3,
};
/* short names for small tiles (the full name stays in the detail, the tooltip and the screen-reader label) */
const SHORT = {
  DJI: '다우', IXIC: '나스닥', NDX: '나스닥 100', SOX: '반도체', DJT: '다우운송',
  EScv1: 'S&P 선물', NQcv1: '나스닥 선물', YMcv1: '다우 선물', RTYcv1: '러셀 선물',
  STOXX50E: '유로스톡스', GDAXI: 'DAX', FTSE: 'FTSE', FCHI: 'CAC 40', AEX: '네덜란드', IBEX: '스페인', FTMIB: '이탈리아',
  OMXS30: '스웨덴', BFX: '벨기에', PSI20: '포르투갈', ISEQ: '아일랜드', BUX: '헝가리',
  N225: '니케이', TOPX: '토픽스', SSEC: '상해', SZSC: '심천', CSI300: 'CSI 300', HSCE: '홍콩H', TWII: '대만', BSESN: '인도',
  VNI: '베트남', HNXI: '하노이', AXJO: '호주', JKSE: '인니', KLSE: '말레이', BVSP: '브라질', MXX: '멕시코', VIX: 'VIX',
  LCOcv1: '브렌트', RBcv1: '가솔린', NGcv1: '천연가스',
};
/* Naver unit codes → [long, short] */
const UNITS = {
  'USD/BBL': ['달러/배럴', '$/배럴'], 'USD/MMBTU': ['달러/MMBtu', '$/MMBtu'], 'USD/U GAL': ['달러/갤런', '$/갤런'], 'USD/GAL': ['달러/갤런', '$/갤런'],
  'USD/OZS': ['달러/트로이온스', '$/온스'], 'USD/OZ': ['달러/트로이온스', '$/온스'], 'USD/LBS': ['달러/파운드', '$/파운드'],
  'USC/BSH': ['센트/부셸', '¢/부셸'], 'USC/LBS': ['센트/파운드', '¢/파운드'], 'USD/TONNE': ['달러/톤', '$/톤'], 'USD/MT': ['달러/톤', '$/톤'],
};
const unitOf = it => { if (!it.unit) return null; const u = UNITS[String(it.unit).toUpperCase()]; return u || [String(it.unit), String(it.unit)]; };
/* exchange time zones → a place name for "지금 열린 시장" */
const CET = '유럽 중부';
const TZ_CITY = {
  EST5EDT: '뉴욕', 'America/New_York': '뉴욕', CST6CDT: '시카고', 'America/Chicago': '시카고',
  'Europe/London': '런던', 'Europe/Dublin': '런던', WET: '리스본', 'Europe/Lisbon': '리스본',
  CET, 'Europe/Paris': CET, 'Europe/Berlin': CET, 'Europe/Frankfurt': CET, 'Europe/Amsterdam': CET, 'Europe/Madrid': CET, 'Europe/Rome': CET,
  'Europe/Stockholm': CET, 'Europe/Brussels': CET, 'Europe/Budapest': CET, 'Europe/Zurich': CET, 'Europe/Vienna': CET, 'Europe/Copenhagen': CET, 'Europe/Oslo': CET, 'Europe/Warsaw': CET,
  'Asia/Tokyo': '도쿄', 'Asia/Shanghai': '중국', 'Asia/Hong_Kong': '홍콩', 'Asia/Taipei': '타이베이', 'Asia/Kolkata': '인도', 'Asia/Calcutta': '인도',
  'Asia/Ho_Chi_Minh': '베트남', 'Asia/Saigon': '베트남', 'Australia/Sydney': '시드니', 'Asia/Jakarta': '자카르타', 'Asia/Kuala_Lumpur': '쿠알라룸푸르',
  'Asia/Singapore': '싱가포르', 'America/Sao_Paulo': '상파울루', 'America/Mexico_City': '멕시코시티', 'America/Toronto': '토론토', 'Asia/Seoul': '서울',
};

/* ───────── small helpers ───────── */
const $ = (s, el = document) => el.querySelector(s);
// replaceChildren() does not flatten arrays or skip null like KH.h does
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
const sgn = v => v > 0 ? '+' : v < 0 ? MINUS : '';
const cls = v => (KH.fmt && KH.fmt.cls) ? KH.fmt.cls(v) : v > 0 ? 'up' : v < 0 ? 'dn' : 'flat';
const pct = v => v == null || !isFinite(v) ? '—' : (KH.fmt && KH.fmt.pct) ? KH.fmt.pct(v) : sgn(v) + Math.abs(v).toFixed(2) + '%';
const fixed = (v, dp) => Math.abs(v).toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const DP = new Map();                                    // sticky decimals per key (6.330 must not flip to 6.33)
function dpOf(it) {
  const dec = v => { if (v == null || !isFinite(v)) return 0; const s = String(Math.abs(v)); const i = s.indexOf('.'); return i < 0 || s.includes('e') ? 0 : s.length - i - 1; };
  const d = Math.max(2, Math.min(4, Math.max(dec(it.value), dec(it.change))));
  const was = DP.get(it.key) || 0;
  if (d > was) DP.set(it.key, d);
  return Math.max(d, was);
}
const valText = it => fixed(it.value, dpOf(it));
const chgText = it => it.change == null || !isFinite(it.change) ? '—' : sgn(it.change) + fixed(it.change, dpOf(it));
const isRef = it => !!it.ref;
const colorOf = it => isRef(it) ? '#30333b' : (it.ratio == null || !isFinite(it.ratio)) ? NODATA : KH.colorOf(it.ratio);
const weightOf = it => WEIGHT[it.key] || 1;
const delayText = it => it.delayed > 0 ? `${it.delayed}분 지연` : '실시간';
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const fmtKst = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false });
const fmtKstS = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const fmtKstDay = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
const pad = n => String(n).padStart(2, '0');

// "2026-11-09T09:58:46-05:00" → {y,mo,d,hh,mm, off (minutes east of UTC), date (Date)}
function parseLocal(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/.exec(String(iso || ''));
  if (!m) return null;
  let off = 0;
  if (m[7] && m[7] !== 'Z') { const s = m[7].replace(':', ''); off = (s[0] === '-' ? -1 : 1) * (+s.slice(1, 3) * 60 + +s.slice(3, 5)); }
  const date = new Date(iso);
  if (isNaN(date)) return null;
  return { y: +m[1], mo: +m[2], d: +m[3], hh: m[4], mm: m[5], off, date };
}
const tzOk = new Map();
function validTz(tz) {
  if (!tz) return false;
  if (!tzOk.has(tz)) { try { new Intl.DateTimeFormat('en-US', { timeZone: tz }); tzOk.set(tz, true); } catch (e) { tzOk.set(tz, false); } }
  return tzOk.get(tz);
}
// wall-clock parts of `date` in a market's time zone (IANA name when valid, else the UTC offset seen in tradedAt)
function wall(date, it) {
  if (validTz(it.tz)) {
    const p = {};
    for (const x of new Intl.DateTimeFormat('en-US', { timeZone: it.tz, year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, weekday: 'short' }).formatToParts(date)) p[x.type] = x.value;
    const wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(p.weekday);
    return { mo: +p.month, d: +p.day, hh: pad(+p.hour % 24), mm: p.minute, wd };
  }
  const L = parseLocal(it.tradedAt);
  const t = new Date(date.getTime() + (L ? L.off : 0) * 60000);
  return { mo: t.getUTCMonth() + 1, d: t.getUTCDate(), hh: pad(t.getUTCHours()), mm: pad(t.getUTCMinutes()), wd: t.getUTCDay() };
}
const cityOf = (it, g) => TZ_CITY[it.tz] || (it.tz && it.tz.includes('/') ? it.tz.split('/').pop().replace(/_/g, ' ') : g ? g.name : '');
function offText(it) {
  const L = parseLocal(it.tradedAt); if (!L) return '';
  const o = L.off, a = Math.abs(o);
  return 'UTC' + (o < 0 ? MINUS : '+') + Math.floor(a / 60) + (a % 60 ? ':' + pad(a % 60) : '');
}

async function getJSON(url, signal) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  const onAbort = () => ac.abort();
  if (signal) signal.addEventListener('abort', onAbort, { once: true });
  try {
    const res = await fetch(url, { cache: 'no-store', signal: ac.signal });
    const type = res.headers.get('content-type') || '';
    let body = null;
    if (type.includes('json')) { try { body = await res.json(); } catch (e) { /* not JSON */ } }
    if (!res.ok) { const err = new Error((body && body.error) || 'HTTP ' + res.status); err.status = res.status; err.json = !!body; throw err; }
    if (body == null) throw new Error('JSON이 아니에요');
    return body;
  } finally { clearTimeout(timer); if (signal) signal.removeEventListener('abort', onAbort); }
}

/* text measuring (canvas): widths at 1 px, digits measured as '0' because the tiles use tabular figures */
const ctx2d = document.createElement('canvas').getContext('2d');
const MW = new Map();
let family = '';
function tw(text, weight) {
  if (!family) family = getComputedStyle(document.body).fontFamily || 'sans-serif';
  const s = String(text).replace(/[0-9]/g, '0');
  const k = weight + '|' + s;
  let v = MW.get(k);
  if (v == null) { ctx2d.font = `${weight} 100px ${family}`; v = ctx2d.measureText(s).width / 100 * 1.04 + 0.02; MW.set(k, v); }
  return v;
}

/* ───────── state ───────── */
const S = {
  kind: null, shown: false,
  data: { index: null, commodity: null }, at: { index: 0, commodity: 0 }, err: { index: null, commodity: null },
  seq: 0, ac: null, timer: 0, busy: null, announced: {},
  focusKey: null, detail: null, chartRoute: true,
};
let root = null, els = null;

/* normalise one /api/world payload; throws on a wrong shape */
function normalise(j, kind) {
  if (!j || !Array.isArray(j.groups)) throw new Error('응답 모양이 달라요');
  const groups = [];
  for (const g of j.groups) {
    if (!g || !Array.isArray(g.items)) continue;
    const items = [];
    for (const x of g.items) {
      if (!x || x.key == null || x.value == null || !isFinite(+x.value)) continue;
      const it = {
        key: String(x.key), name: String(x.name || x.key), value: +x.value,
        change: x.change == null || !isFinite(+x.change) ? null : +x.change,
        ratio: x.ratio == null || !isFinite(+x.ratio) ? null : +x.ratio,
        status: x.status === 'OPEN' ? 'OPEN' : 'CLOSE', tradedAt: x.tradedAt || null,
        delayed: +x.delayed > 0 ? +x.delayed : 0, unit: x.unit || null, tz: x.tz || null,
        ref: !!(x.ref || g.ref), group: String(g.name || ''), gkey: String(g.key || ''),
      };
      items.push(it);
    }
    if (!items.length) continue;
    // biggest first inside a group (stable for equal weights), so the squarified layout puts headline tiles top-left
    const ordered = items.map((it, i) => [it, i]).sort((a, b) => weightOf(b[0]) - weightOf(a[0]) || a[1] - b[1]).map(a => a[0]);
    groups.push({ key: String(g.key || g.name), name: String(g.name || ''), items: ordered });
  }
  const all = groups.flatMap(g => g.items);
  return { asOf: j.asOf || null, kind, groups, all, byKey: new Map(all.map(it => [it.key, it])), charts: j.charts !== false };
}

/* ───────── DOM scaffold ───────── */
function scaffold() {
  root = document.getElementById('world');
  if (!root) return false;
  if (root.__kw && els && root.contains(els.map)) return true;
  root.classList.add('kw');
  root.replaceChildren();
  if (!LIVE) { root.__kw = true; els = { snap: true }; return true; }
  const map = h('div', { class: 'kw-map', role: 'group' });
  const bar = h('div', { class: 'kw-bar' }, h('h2', { class: 'kw-title' }), h('span', { class: 'kw-sum' }), h('span', { class: 'kw-time' }));
  const legend = h('div', { class: 'legend kw-legend' });
  const rank = h('div', { class: 'kw-rank' });
  const open = h('div', { class: 'kw-open' });
  const src = h('p', { class: 'kw-src' });
  const live = h('div', { class: 'sr', role: 'status', 'aria-live': 'polite' });
  root.append(
    h('section', { class: 'kw-stage' }, bar, map, legend),
    h('aside', { class: 'kw-side' },
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '많이 오른·내린' }), h('small', { class: 'kw-rank-sub' })), rank),
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '지금 열린 시장' }), h('small', { text: '현지 시각' })), open),
      src),
    live);
  els = { map, bar, legend, rank, open, src, live, tiles: new Map(), heads: new Map(), boxes: null, mapW: 0 };
  root.__kw = true;
  map.addEventListener('click', e => { const t = e.target.closest('.kw-tile'); if (t) openDetail(t.dataset.k, t); });
  map.addEventListener('keydown', onMapKey);
  map.addEventListener('focusin', e => { const t = e.target.closest('.kw-tile'); if (t) setRoving(t.dataset.k); });
  rank.addEventListener('click', e => { const b = e.target.closest('.kw-row'); if (b) openDetail(b.dataset.k, b); });
  new ResizeObserver(() => { if (S.shown && els.map.clientWidth !== els.mapW) schedRender(); }).observe(map);
  return true;
}
let rafR = 0;
const schedRender = () => { cancelAnimationFrame(rafR); rafR = requestAnimationFrame(() => { if (S.shown) render(); }); };

/* ───────── render ───────── */
function render() {
  if (!S.shown || !els) return;
  if (els.snap) return renderSnapshot();
  const K = KINDS[S.kind], d = S.data[S.kind], err = S.err[S.kind];
  $('.kw-title', els.bar).textContent = K.title;
  $('.kw-side', root).setAttribute('aria-label', `${K.title} 요약`);
  els.map.setAttribute('aria-label', `${K.title} 지도. 화살표로 옮기고 Enter로 자세히 봐요`);
  if (!d) {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(err ? msgBox(K.fail, errText(err), true) : msgBox('불러오는 중이에요…', `${K.title} 시세를 받아 오고 있어요.`, false, true));
    put($('.kw-sum', els.bar),);
    $('.kw-time', els.bar).replaceChildren();
    els.legend.replaceChildren();
    els.rank.replaceChildren(h('p', { class: 'kw-none', text: err ? '시세를 받지 못했어요' : '불러오는 중이에요…' }));
    els.open.replaceChildren(h('p', { class: 'kw-none', text: err ? '시세를 받지 못했어요' : '불러오는 중이에요…' }));
    renderSource(null);
    return;
  }
  if (!d.all.length) {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(msgBox(K.empty, '거래소 자료가 비어 있어요. 잠시 뒤 다시 받아 올게요.', true));
    els.rank.replaceChildren(h('p', { class: 'kw-none', text: '보여 줄 항목이 없어요' }));
    els.open.replaceChildren(h('p', { class: 'kw-none', text: '보여 줄 항목이 없어요' }));
    renderBar(d, err); els.legend.replaceChildren(); renderSource(d);
    return;
  }
  if (els.map.classList.contains('kw-msgmode')) { els.map.classList.remove('kw-msgmode'); els.map.replaceChildren(); }
  renderBar(d, err);
  renderMap(d);
  renderLegend(d);
  renderRank(d);
  renderOpen(d);
  renderSource(d);
  if (S.detail) fillDetail(false);
}
function errText(e) {
  if (!e) return '';
  if (e.name === 'AbortError') return '응답이 너무 늦어요. 잠시 뒤 다시 시도할게요.';
  if (e.status === 404 && !e.json) return '서버에 아직 이 기능이 없어요. 잠시 뒤 다시 시도할게요.';
  return e.status ? '서버가 시세를 받아 오지 못했어요. 15초 뒤 다시 시도할게요.' : '네트워크 연결을 확인해 주세요. 15초 뒤 다시 시도할게요.';
}
function msgBox(title, body, retry, busy) {
  return h('div', { class: 'kw-msg' + (busy ? ' busy' : '') }, h('b', { text: title }), body ? h('span', { text: body }) : null,
    retry ? h('button', { type: 'button', class: 'kw-retry', onclick: () => load(S.kind) }, '다시 시도') : null);
}

function renderBar(d, err) {
  let up = 0, dn = 0, fl = 0, open = 0;
  for (const it of d.all) { if (it.status === 'OPEN') open++; if (isRef(it) || it.ratio == null) continue; if (it.ratio > 0) up++; else if (it.ratio < 0) dn++; else fl++; }
  put($('.kw-sum', els.bar),
    h('span', {}, '오른 ', h('b', { class: 'up', text: String(up) })), h('span', { class: 'kw-dot', 'aria-hidden': 'true', text: '·' }),
    h('span', {}, '내린 ', h('b', { class: 'dn', text: String(dn) })),
    fl ? [h('span', { class: 'kw-dot', 'aria-hidden': 'true', text: '·' }), h('span', {}, '보합 ', h('b', { class: 'flat', text: String(fl) }))] : null,
    h('span', { class: 'kw-dot', 'aria-hidden': 'true', text: '·' }), h('span', { text: open ? `장중 ${open}` : '모두 마감' }));
  const t = $('.kw-time', els.bar);
  const at = d.asOf ? new Date(d.asOf) : new Date(S.at[S.kind]);
  if (err) t.replaceChildren(h('span', { class: 'kw-stale', text: `새로 받지 못했어요 · ${isNaN(at) ? '' : fmtKst.format(at) + ' 값'}` }));
  else t.replaceChildren(h('span', { text: isNaN(at) ? '' : `${fmtKst.format(at)} 기준` }));
}

/* ── layout: desktop = one squarified treemap of groups; phones = groups stacked in rows (small groups share a row) ── */
function computeLayout(d, W) {
  const narrow = W < 560;
  const HD = narrow ? 18 : 20, GAP = 3;
  const wsum = arr => arr.reduce((a, it) => a + weightOf(it), 0);
  const groups = d.groups.map(g => ({ g, wt: wsum(g.items) }));
  const tiles = [], heads = [];
  const packItems = (g, x, y, w, hh) => {
    const H = hh - g.hd;
    if (w <= 0 || H <= 0) return;
    const root = d3.hierarchy({ children: g.g.items.map(it => ({ it })) }).sum(n => n.it ? weightOf(n.it) : 0);
    d3.treemap().size([w, H]).round(true).paddingInner(1).tile(d3.treemapSquarify.ratio(1))(root);
    for (const l of root.leaves()) tiles.push({ it: l.data.it, g: g.g, x: x + l.x0, y: y + g.hd + l.y0, w: l.x1 - l.x0, h: l.y1 - l.y0 });
  };
  if (!narrow) {
    const H = mapHeightDesktop(d, W);
    const root = d3.hierarchy({ children: groups.map(g => ({ grp: g, children: g.g.items.map(it => ({ it })) })) }).sum(n => n.it ? weightOf(n.it) : 0);
    d3.treemap().size([W, H]).round(true).tile(d3.treemapSquarify.ratio(1))
      .paddingInner(n => n.depth === 0 ? GAP : 1)
      .paddingTop(n => { if (n.depth !== 1) return 0; const v = (n.x1 - n.x0 > 44 && n.y1 - n.y0 > 40) ? HD : 0; n.data.grp.hd = v; return v; })(root);
    for (const n of root.children || []) {
      const g = n.data.grp;
      heads.push({ g: g.g, x: n.x0, y: n.y0, w: n.x1 - n.x0, h: n.y1 - n.y0, hd: g.hd });
      for (const l of n.leaves()) tiles.push({ it: l.data.it, g: g.g, x: l.x0, y: l.y0, w: l.x1 - l.x0, h: l.y1 - l.y0 });
    }
    return { W, H, tiles, heads, narrow };
  }
  // phones: rows of groups; grow the area per weight unit until every tile is a comfortable tap target
  const T = 5.5, rows = [];
  let cur = null;
  for (const g of groups) {
    if (g.wt >= T) { if (cur) { rows.push(cur); cur = null; } rows.push([g]); continue; }
    (cur = cur || []).push(g);
    if (cur.reduce((a, x) => a + x.wt, 0) >= T) { rows.push(cur); cur = null; }
  }
  if (cur) rows.push(cur);
  // fewer items (원자재 17) get bigger tiles than the 41 indices
  let unit = 5000 * Math.max(1, Math.min(1.5, 40 / Math.max(1, d.all.length))), out = null;
  for (let tries = 0; tries < 7; tries++) {
    tiles.length = 0; heads.length = 0;
    let y = 0;
    for (const row of rows) {
      const rw = row.reduce((a, x) => a + x.wt, 0);
      const hh = Math.max(64, Math.round(rw * unit / W)) + HD;
      let x = 0;
      row.forEach((g, i) => {
        const w = i === row.length - 1 ? W - x : Math.round((W - GAP * (row.length - 1)) * g.wt / rw);
        g.hd = w > 40 ? HD : 0;
        heads.push({ g: g.g, x, y, w, h: hh, hd: g.hd });
        packItems(g, x, y, w, hh);
        x += w + GAP;
      });
      y += hh + GAP;
    }
    out = { W, H: y - GAP, tiles: tiles.slice(), heads: heads.slice(), narrow };
    const small = tiles.some(t => t.w < 46 || t.h < 44);
    if (!small) break;
    unit *= 1.18;
  }
  return out;
}
function mapHeightDesktop(d, W) {
  if (narrowMQ.matches) {                                 // a phone in landscape / small tablet: size by content
    const units = d.all.reduce((a, it) => a + weightOf(it), 0);
    return Math.max(380, Math.min(900, Math.round(units * 6400 / W + d.groups.length * 12)));
  }
  const top = els.map.getBoundingClientRect().top + scrollY;
  const lg = els.legend.offsetHeight || 30;
  return Math.max(480, Math.round(innerHeight - top - 14 - lg));
}

/* ── fitting a label into a tile: name (full or short, 1 or 2 lines), % line, value line, then the state chip ── */
const LH = { name: 1.08, pc: 0.8 * 1.08 + 0.08, v: 0.58 * 1.08 + 0.58 * 0.14 }, PADX = 8, GLYPH = 0.16;
function splitName(name) {
  const sp = [...name.matchAll(/ /g)].map(m => m.index);
  if (!sp.length) return null;
  let best = sp[0], bd = Infinity;
  for (const i of sp) { const dd = Math.abs(i - name.length / 2); if (dd < bd) { bd = dd; best = i; } }
  return [name.slice(0, best), name.slice(best + 1)];
}
function tileTexts(it, g) {
  const u = S.kind === 'commodity' ? unitOf(it) : null;
  const names = [it.name];
  const sh = SHORT[it.key];
  if (sh && sh !== it.name) names.push(sh);
  const v = valText(it);
  const vals = u ? [v + ' ' + u[1], v] : [v];
  return { names, pc: pct(it.ratio), vals };
}
function fit(T, w, hh, capH) {
  const W = w - PADX, H = hh - 4;
  const maxFs = Math.min(34, (capH || hh) * 0.3);
  const pcW = tw(T.pc, 500) * 0.8;
  let best = null;
  const consider = (cand, score) => { if (!best || score > best.score) best = Object.assign(cand, { score }); };
  T.names.forEach((name, ni) => {
    const splits = [[name]];
    const sp = splitName(name);
    if (sp) splits.push(sp);
    for (const parts of splits) {
      const nW = Math.max(...parts.map(p => tw(p, 600)));
      const nl = parts.length;
      const nameH = nl * LH.name;
      // level 1: name only, 2: + %, 3: + value
      const levels = [
        { lv: 1, wu: nW, hu: nameH },
        { lv: 2, wu: Math.max(nW, pcW), hu: nameH + LH.pc },
      ];
      T.vals.forEach((vt, vi) => levels.push({ lv: 3, vi, vt, wu: Math.max(nW, pcW, tw(vt, 500) * 0.58), hu: nameH + LH.pc + LH.v }));
      for (const L of levels) {
        const fs = Math.min(maxFs, W / L.wu, H / (L.hu + GLYPH));
        const min = L.lv === 3 ? 15.5 : L.lv === 2 ? 11.5 : 9.5;
        if (fs < min) continue;
        // richer first; full name and unit preferred unless they cost real size; one line preferred over two
        const score = L.lv * 1000 + fs * (ni === 0 ? 1.18 : 1) * (L.vi ? 1 : 1.12) * (nl === 1 ? 1.08 : 1);
        consider({ lv: L.lv, fs, parts, vt: L.vt || null, labW: L.wu * fs, labH: L.hu * fs }, score);
      }
    }
  });
  return best;                                           // null = no label
}
// chip candidates, longest first; the last one is a bare dot (amber = 장중, ring = 마감) for tiles too small for words
const CHIP_H = 15, CHIP_FS = 10.5, DOT = 13;
function chipCands(it) {
  const open = it.status === 'OPEN';
  const texts = !open ? ['마감'] : it.delayed ? [`장중 · ${it.delayed}분 지연`, `장중 · ${it.delayed}분`, '장중'] : ['장중'];
  return texts.map(t => ({ t, w: tw(t, 500) * CHIP_FS + 10 + (open ? 9 : 0), hgt: CHIP_H })).concat({ t: '', dot: true, w: DOT, hgt: DOT });
}
function placeTile(el, t) {
  const it = t.it;
  el.style.left = t.x + 'px'; el.style.top = t.y + 'px'; el.style.width = t.w + 'px'; el.style.height = t.h + 'px';
  const col = colorOf(it);
  el.style.backgroundColor = col;
  el.__col = col;
  el.classList.toggle('ref', isRef(it));
  el.classList.toggle('nod', !isRef(it) && it.ratio == null);
  const [chip, lab] = el.children;
  const [nm, pc, vv] = lab.children;
  const T = tileTexts(it, t.g);
  let L = fit(T, t.w, t.h);
  // the chip sits top-left; keep it clear of the centred label, else refit the label lower, else a shorter chip, else none
  const open = it.status === 'OPEN';
  let chipC = null;
  if (t.w >= 24 && t.h >= 20) {
    for (const c of chipCands(it)) {
      if (c.w > t.w - 6) continue;
      const clear = LL => !LL || (t.h - LL.labH) / 2 >= c.hgt + 5 || (t.w - LL.labW) / 2 >= c.w + 6;
      if (clear(L)) { chipC = c; break; }
      // room above and below the label, or (narrow label) beside it
      const min = L ? L.fs * (c.dot ? 0.6 : 0.68) : 0, lvMin = L ? Math.min(L.lv, 2) : 1;
      const L2 = fit(T, t.w, t.h - 2 * (c.hgt + 5), t.h);
      if (L2 && L && L2.lv >= lvMin && L2.fs >= min) { L = L2; chipC = c; break; }
      const L3 = t.w - 2 * (c.w + 6) > 24 ? fit(T, t.w - 2 * (c.w + 6), t.h, t.h) : null;
      if (L3 && L && L3.lv >= lvMin && L3.fs >= min) { L = L3; chipC = c; break; }
    }
  }
  chip.hidden = !chipC;
  if (chipC) { chip.textContent = chipC.t; chip.className = 'kw-chip ' + (open ? 'open' : 'close') + (chipC.dot ? ' dot' : ''); }
  el.__sub = '';
  if (!L) { lab.hidden = true; return; }
  lab.hidden = false;
  lab.style.fontSize = L.fs.toFixed(1) + 'px';
  if (L.parts.length > 1) nm.replaceChildren(L.parts[0], document.createElement('br'), L.parts[1]);
  else nm.textContent = L.parts[0];
  pc.hidden = L.lv < 2; pc.textContent = T.pc;
  vv.hidden = L.lv < 3; vv.textContent = L.vt || '';
  if (L.lv >= 2) el.__sub = T.pc;
}
function ariaOf(it) {
  const u = unitOf(it);
  return `${it.group ? it.group + ', ' : ''}${it.name} ${valText(it)}${u ? ' ' + u[0] : ''}, 전일 대비 ${chgText(it)} (${pct(it.ratio)}), ` +
    `${it.status === 'OPEN' ? '장중' : '마감'}, ${delayText(it)}${isRef(it) ? ', 참고 지표라 색칠하지 않았어요' : ''}`;
}
function renderMap(d) {
  const W = els.map.clientWidth;
  if (!W) return;
  els.mapW = W;
  const Lo = computeLayout(d, W);
  els.boxes = Lo;
  els.map.style.height = Lo.H + 'px';
  const seenT = new Set(), seenG = new Set();
  for (const g of Lo.heads) {
    seenG.add(g.g.key);
    let el = els.heads.get(g.g.key);
    if (!el) { el = h('div', { class: 'kw-gh', 'aria-hidden': 'true' }, h('span', { class: 't' }), h('span', { class: 's' }), h('span', { class: 'v' })); els.heads.set(g.g.key, el); els.map.append(el); }
    el.style.left = g.x + 'px'; el.style.top = g.y + 'px'; el.style.width = g.w + 'px'; el.style.height = g.hd + 'px';
    el.hidden = !g.hd;
    const vals = g.g.items.filter(it => !isRef(it) && it.ratio != null).map(it => it.ratio);
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    el.children[0].textContent = g.g.name;
    const vt = avg == null ? '' : pct(avg);
    let room = g.w - tw(g.g.name, 700) * 12 - 16;
    const vOn = vt && room >= tw(vt, 600) * 12 + 4;
    if (vOn) room -= tw(vt, 600) * 12 + 10;
    // the group's market state when every member shares it ("장중 · 15분 지연", "마감")
    const st = new Set(g.g.items.map(it => it.status)), dl = new Set(g.g.items.map(it => it.delayed));
    const stText = st.size !== 1 ? '' : st.has('OPEN') ? (dl.size === 1 ? (g.g.items[0].delayed ? `장중 · ${g.g.items[0].delayed}분 지연` : '장중 · 실시간') : '장중') : '마감';
    el.children[1].textContent = stText && room >= tw(stText, 500) * 11 + 6 ? stText : '';
    el.children[2].textContent = vOn ? vt : '';
    el.children[2].className = 'v ' + (avg == null ? 'flat' : cls(avg));
    el.title = avg == null ? g.g.name : `${g.g.name} · 단순 평균 ${vt}`;
    el.__sub = el.children[2].textContent;
  }
  for (const t of Lo.tiles) {
    seenT.add(t.it.key);
    let el = els.tiles.get(t.it.key);
    if (!el) {
      el = h('button', { type: 'button', class: 'kw-tile', 'data-k': t.it.key, tabindex: '-1' },
        h('span', { class: 'kw-chip', 'aria-hidden': 'true' }), h('span', { class: 'kw-lab', 'aria-hidden': 'true' }, h('span', { class: 'kw-nm' }), h('span', { class: 'kw-pc' }), h('span', { class: 'kw-v' })));
      els.tiles.set(t.it.key, el);
      els.map.append(el);
    }
    el.__t = t;
    el.setAttribute('aria-label', ariaOf(t.it));
    el.title = t.it.name;
    placeTile(el, t);
    el.classList.toggle('sel', !!(S.detail && S.detail.key === t.it.key));
  }
  for (const [k, el] of els.tiles) if (!seenT.has(k)) { el.remove(); els.tiles.delete(k); }
  for (const [k, el] of els.heads) if (!seenG.has(k)) { el.remove(); els.heads.delete(k); }
  // DOM order = reading order (group, then tile) so Tab / screen readers follow the map
  const order = Lo.tiles.map(t => els.tiles.get(t.it.key));
  order.forEach((el, i) => { if (els.map.children[i + Lo.heads.length] !== el) els.map.append(el); });
  if (!S.focusKey || !els.tiles.has(S.focusKey)) S.focusKey = Lo.tiles.length ? Lo.tiles[0].it.key : null;
  for (const [k, el] of els.tiles) el.tabIndex = k === S.focusKey ? 0 : -1;
}

/* roving focus: one tab stop for the map; arrows move to the nearest tile in that direction */
function setRoving(key) {
  if (!els.tiles.has(key)) return;
  S.focusKey = key;
  for (const [k, el] of els.tiles) el.tabIndex = k === key ? 0 : -1;
}
function onMapKey(e) {
  const cur = e.target.closest('.kw-tile');
  if (!cur || !els.boxes) return;
  const list = els.boxes.tiles;
  let next = null;
  if (e.key === 'Home') next = list[0];
  else if (e.key === 'End') next = list[list.length - 1];
  else if (/^Arrow/.test(e.key)) {
    const a = cur.__t, ax = a.x + a.w / 2, ay = a.y + a.h / 2;
    let bestS = Infinity;
    for (const b of list) {
      if (b === a) continue;
      const bx = b.x + b.w / 2, by = b.y + b.h / 2;
      let main, cross;
      if (e.key === 'ArrowRight') { if (b.x < a.x + a.w - 1) continue; main = b.x - (a.x + a.w); cross = Math.max(0, Math.max(a.y, b.y) < Math.min(a.y + a.h, b.y + b.h) ? 0 : Math.abs(by - ay)); }
      else if (e.key === 'ArrowLeft') { if (b.x + b.w > a.x + 1) continue; main = a.x - (b.x + b.w); cross = Math.max(a.y, b.y) < Math.min(a.y + a.h, b.y + b.h) ? 0 : Math.abs(by - ay); }
      else if (e.key === 'ArrowDown') { if (b.y < a.y + a.h - 1) continue; main = b.y - (a.y + a.h); cross = Math.max(a.x, b.x) < Math.min(a.x + a.w, b.x + b.w) ? 0 : Math.abs(bx - ax); }
      else { if (b.y + b.h > a.y + 1) continue; main = a.y - (b.y + b.h); cross = Math.max(a.x, b.x) < Math.min(a.x + a.w, b.x + b.w) ? 0 : Math.abs(bx - ax); }
      const s = main + cross * 2 + (e.key === 'ArrowRight' || e.key === 'ArrowLeft' ? Math.abs(by - ay) : Math.abs(bx - ax)) * 0.1;
      if (s < bestS) { bestS = s; next = b; }
    }
    if (!next) { e.preventDefault(); return; }
  } else return;
  e.preventDefault();
  const el = els.tiles.get(next.it.key);
  if (el) { setRoving(next.it.key); el.focus(); }
}

/* legend: colour scale as the heatmap draws it, the VIX note, what size means */
function rangeNow() {
  try { const hi = KH.colorOf(1000); for (const R of [1, 2, 3, 5, 10, 20, 30]) if (KH.colorOf(R) === hi) return R; } catch (e) { /* no colour scale */ }
  return null;
}
function renderLegend(d) {
  const P = (KH.palette && KH.palette().stops) || [];
  const R = rangeNow();
  const kids = [h('span', { class: 'lg' }, h('span', { class: 'k', text: '색' }), h('b', { text: '오늘 등락률' }),
    R ? h('span', { class: 'tk', text: `${MINUS}${R}%` }) : null,
    P.length ? h('span', { class: 'grad', style: `background:linear-gradient(90deg,${P.join(',')})`, 'aria-hidden': 'true' }) : null,
    R ? h('span', { class: 'tk', text: `+${R}%` }) : null)];
  if (d.all.some(isRef)) kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw kw-refsw' }), h('span', { text: 'VIX는 참고 지표라 색칠하지 않아요' })));
  kids.push(h('span', { class: 'lg' }, h('span', { class: 'kw-chip-l open', 'aria-hidden': 'true', text: '장중' }), h('span', { class: 'kw-chip-l close', 'aria-hidden': 'true', text: '마감' }),
    h('span', { class: 'sr', text: '타일 왼쪽 위 표시: 장중 또는 마감, 지연 시간' })));
  kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '대표 지수를 크게' }), h('span', { class: 'note', text: '시가총액과는 관계없어요' })));
  if (S.kind === 'commodity') kids[kids.length - 1] = h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '주요 품목을 크게' }), h('span', { class: 'note', text: '거래 규모와는 관계없어요' }));
  els.legend.replaceChildren(...kids);
}

/* side: biggest movers, open markets, source */
function rowBtn(it) {
  const u = unitOf(it);
  return h('button', { type: 'button', class: 'kw-row', 'data-k': it.key, 'aria-label': ariaOf(it) },
    h('i', { class: 'kw-sw', style: `background:${colorOf(it)}` }),
    h('span', { class: 'nm' }, it.name, h('small', { text: it.group })),
    h('span', { class: 'px', text: valText(it) + (u ? ' ' + u[1] : '') }),
    h('span', { class: 'v ' + cls(it.ratio), text: pct(it.ratio) }));
}
function renderRank(d) {
  const pool = d.all.filter(it => !isRef(it) && it.ratio != null);
  const ups = pool.filter(it => it.ratio > 0).sort((a, b) => b.ratio - a.ratio).slice(0, 5);
  const dns = pool.filter(it => it.ratio < 0).sort((a, b) => a.ratio - b.ratio).slice(0, 5);
  const sub = $('.kw-rank-sub', root);
  if (sub) sub.textContent = `${pool.length}개 중`;
  put(els.rank,
    h('div', { class: 'kw-rh', text: '많이 오른' }),
    ups.length ? ups.map(rowBtn) : h('p', { class: 'kw-none', text: '오른 곳이 없어요' }),
    h('div', { class: 'kw-rh second', text: '많이 내린' }),
    dns.length ? dns.map(rowBtn) : h('p', { class: 'kw-none', text: '내린 곳이 없어요' }));
}
function renderOpen(d) {
  const now = new Date();
  const byCity = new Map();
  let closed = 0;
  for (const g of d.groups) for (const it of g.items) {
    if (it.status !== 'OPEN') { closed++; continue; }
    const c = cityOf(it, g);
    const e = byCity.get(c) || byCity.set(c, { city: c, its: [], it }).get(c);
    e.its.push(it);
  }
  const rows = [...byCity.values()].map(e => {
    const w = wall(now, e.it);
    const names = e.its.map(it => SHORT[it.key] || it.name);
    const shown = names.slice(0, 4).join(' · ') + (names.length > 4 ? ` 외 ${names.length - 4}개` : '');
    return h('li', { class: 'kw-om' },
      h('div', { class: 'kw-om1' }, h('b', { text: e.city }), h('span', { class: 'kw-clock', text: `${WD[w.wd] || ''} ${w.hh}:${w.mm}` })),
      h('div', { class: 'kw-om2', text: shown, title: e.its.map(it => it.name).join(', ') }));
  });
  const kst = fmtKst.format(now);
  els.open.replaceChildren(
    rows.length ? h('ul', { class: 'kw-oml' }, rows)
      : h('p', { class: 'kw-none' }, '지금은 열린 시장이 없어요. 주말·휴장일이거나 장 시간이 아니라서 마지막 값을 보여 줘요.'),
    h('p', { class: 'kw-omf' }, `한국 ${kst} · `, closed ? `마감 ${closed}개는 마지막 값이에요` : '모두 장중이에요'));
}
function renderSource(d) {
  const kids = [h('span', {}, '출처: 네이버 증권 · 해외 지수와 원자재는 거래소별로 최대 20분 지연될 수 있어요.')];
  if (d && d.all.length) {
    const cnt = new Map();
    for (const it of d.all) cnt.set(it.delayed || 0, (cnt.get(it.delayed || 0) || 0) + 1);
    const parts = [...cnt].sort((a, b) => a[0] - b[0]).map(([k, n]) => `${k ? k + '분 지연' : '실시간'} ${n}개`);
    kids.push(h('span', {}, ` 지금 목록: ${parts.join(' · ')}.`));
    const at = d.asOf ? new Date(d.asOf) : null;
    if (at && !isNaN(at)) kids.push(h('span', {}, ` ${fmtKstS.format(at)}(한국 시각)에 받은 값이고, 30초마다 새로 받아요.`));
  }
  if (S.kind === 'commodity') kids.push(h('span', {}, ' 원자재는 근월물 선물 가격이에요.'));
  els.src.replaceChildren(...kids);
}

/* snapshot (artifact) mode: no network → a pointer to the live page */
function renderSnapshot() {
  const K = KINDS[S.kind];
  const url = (KH.LIVE_URL || 'https://kospimap.pages.dev/') + '#' + K.hash;
  root.replaceChildren(h('div', { class: 'kw-snap' },
    h('div', { class: 'kw-snap-in' },
      h('b', { text: K.snapTitle }),
      h('p', { text: K.snapBody }),
      h('a', { class: 'kw-snap-a', href: url, target: '_blank', rel: 'noopener' }, '실시간 버전 열기'))));
}

/* ───────── detail sheet ───────── */
let sheet = null, scrim = null;
function ensureSheet() {
  if (sheet) return;
  scrim = h('div', { class: 'kw-scrim', 'aria-hidden': 'true' });
  sheet = h('div', { class: 'kw-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'kw-dt', tabindex: '-1', hidden: true });
  document.body.append(scrim, sheet);
  scrim.addEventListener('click', () => closeDetail(true));
  sheet.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeDetail(true); return; }
    if (e.key === 'Tab') {
      const f = [...sheet.querySelectorAll('button,a[href]')].filter(b => b.offsetParent && !b.disabled);
      if (!f.length) return;
      if (e.shiftKey && (document.activeElement === f[0] || document.activeElement === sheet)) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  document.addEventListener('pointerdown', e => {
    if (!S.detail || sheet.contains(e.target) || e.target.closest('.kw-tile,.kw-row')) return;
    if (!narrowMQ.matches) closeDetail(false);
  }, true);
  addEventListener('resize', () => { if (S.detail && S.detail.chart) drawChart(); });
}
function openDetail(key, opener) {
  const d = S.data[S.kind];
  if (!d || !d.byKey.has(key)) return;
  ensureSheet();
  const same = S.detail && S.detail.key === key;
  S.detail = { key, kind: S.kind, opener: opener || null, tf: same ? S.detail.tf : '3m', chart: null };
  for (const [k, el] of els.tiles) el.classList.toggle('sel', k === key);
  fillDetail(true);
  sheet.hidden = false;
  sheet.classList.toggle('kw-noanim', reduceMQ.matches);
  if (narrowMQ.matches) scrim.classList.add('open');
  sheet.scrollTop = 0;
  sheet.focus({ preventScroll: true });
  loadChart();
}
function closeDetail(restore) {
  if (!S.detail || !sheet) return;
  const { key, opener } = S.detail;
  S.detail = null;
  sheet.hidden = true;
  scrim.classList.remove('open');
  if (els && els.tiles) for (const el of els.tiles.values()) el.classList.remove('sel');
  if (!restore || !S.shown) return;
  let target = opener && opener.isConnected ? opener : null;
  if (!target && opener && opener.classList.contains('kw-row')) target = els.rank.querySelector(`.kw-row[data-k="${CSS.escape(key)}"]`);
  if (!target) target = els.tiles.get(key);
  if (target) { if (target.classList.contains('kw-tile')) setRoving(key); target.focus({ preventScroll: false }); }
}
function fillDetail(full) {
  const D = S.detail, d = S.data[D.kind];
  const it = d && d.byKey.get(D.key);
  if (!it) return;
  const u = unitOf(it), L = parseLocal(it.tradedAt);
  const g = d.groups.find(x => x.items.includes(it));
  const city = cityOf(it, g);
  const lw = L ? wall(L.date, it) : null;
  const localTxt = L ? `${L.mo}월 ${L.d}일 (${WD[lw.wd]}) ${L.hh}:${L.mm}` : '—';
  const kstTxt = L ? fmtKstDay.format(L.date) : '—';
  const prev = it.change != null ? it.value - it.change : null;
  const head = h('div', { class: 'kw-dh' },
    h('div', { class: 'kw-path', text: [it.group, city && city !== it.group ? city : null].filter(Boolean).join(' · ') }),
    h('div', { class: 'kw-nmrow' }, h('i', { class: 'kw-sw', style: `background:${colorOf(it)}` }), h('b', { id: 'kw-dt', text: it.name }),
      h('span', { class: 'kw-st ' + (it.status === 'OPEN' ? 'open' : 'close'), text: it.status === 'OPEN' ? '장중' : '마감' })),
    h('div', { class: 'kw-px' }, h('b', { text: valText(it) }), u ? h('small', { text: u[0] }) : null,
      h('span', { class: cls(it.ratio), text: `${chgText(it)} (${pct(it.ratio)})` })),
    h('dl', { class: 'kw-meta' },
      h('dt', { text: '시세' }), h('dd', { text: `${it.status === 'OPEN' ? '장중' : '마감'} · ${delayText(it)}` }),
      h('dt', { text: '현지 거래 시각' }), h('dd', {}, localTxt, h('small', { text: ` ${city || ''} ${offText(it)}`.trimEnd() })),
      h('dt', { text: '한국 시각' }), h('dd', { text: kstTxt }),
      prev != null ? [h('dt', { text: '전일 종가' }), h('dd', { text: fixed(prev, dpOf(it)) + (u ? ' ' + u[1] : '') })] : null,
      h('dt', { text: '단위' }), h('dd', { text: u ? u[0] : (it.gkey === 'kr' || S.kind === 'index' ? '포인트' : '—') })),
    isRef(it) ? h('p', { class: 'kw-note', text: 'VIX는 S&P 500 옵션 가격으로 계산한 변동성 기대치예요. 오르면 시장 불안이 커졌다는 뜻이라 지도에서 색칠하지 않았어요.' }) : null,
    it.gkey === 'kr' ? h('p', { class: 'kw-note', text: '비교용으로 함께 보여 줘요. 종목 지도는 코스피·코스닥 탭에서 볼 수 있어요.' }) : null,
    S.kind === 'commodity' ? h('p', { class: 'kw-note', text: '근월물 선물 가격이에요. 거래소 시각 기준으로 하루가 바뀌어요.' }) : null);
  if (full || !sheet.firstChild) {
    const chartBox = h('div', { class: 'kw-chart' });
    sheet.replaceChildren(
      h('div', { class: 'kw-grab', 'aria-hidden': 'true' }),
      h('button', { type: 'button', class: 'kw-x', 'aria-label': '닫기', onclick: () => closeDetail(true) }, '×'),
      head, chartBox,
      h('p', { class: 'kw-dsrc', text: `출처: 네이버 증권 · ${delayText(it)} 시세` }));
  } else {
    sheet.replaceChild(head, $('.kw-dh', sheet));
    const src = $('.kw-dsrc', sheet); if (src) src.textContent = `출처: 네이버 증권 · ${delayText(it)} 시세`;
    if (S.detail.chart && S.detail.chart.bars) drawChart();   // its last point is the live value
  }
}

/* chart: /api/world/chart/{key}?tf=3m|1y (daily closes). A missing route (plain 404) hides charts for the session. */
const CH = new Map();                                    // key|tf → {at, bars} | {at, err, gone}
const TFS = [['3m', '3개월'], ['1y', '1년']];
async function loadChart() {
  const D = S.detail;
  if (!D) return;
  const box = $('.kw-chart', sheet);
  const d = S.data[D.kind];
  if (!S.chartRoute || (d && d.charts === false)) { box.replaceChildren(); box.hidden = true; return; }
  box.hidden = false;
  const k = D.key + '|' + D.tf;
  const c = CH.get(k);
  const fresh = c && (Date.now() - c.at < (c.err ? 15000 : 600000));
  if (fresh) { D.chart = c; drawChart(); return; }
  D.chart = { loading: true };
  drawChart();
  let res;
  try {
    const j = await getJSON(`api/world/chart/${encodeURIComponent(D.key)}?tf=${D.tf}`);
    const bars = (j && Array.isArray(j.bars) ? j.bars : []).filter(b => b && b.t != null && isFinite(+b.c)).map(b => ({ t: String(b.t), c: +b.c }));
    res = { at: Date.now(), bars };
  } catch (e) {
    if (e.status === 404 && !e.json) S.chartRoute = false;          // the Worker has no chart route at all
    res = { at: Date.now(), err: e, gone: e.status === 404 || e.status === 400 };
  }
  CH.set(k, res);
  if (!S.detail || S.detail.key !== D.key || S.detail.tf !== D.tf) return;
  if (!S.chartRoute) { box.replaceChildren(); box.hidden = true; return; }
  S.detail.chart = res;
  drawChart();
}
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const a in attrs || {}) el.setAttribute(a, attrs[a]);
  for (const k of kids) if (k) el.append(k);
  return el;
}
const shortDate = t => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t); return m ? `${+m[2]}월 ${+m[3]}일` : t; };
const shortDateY = t => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t); return m ? `${m[1].slice(2)}.${m[2]}.${m[3]}` : t; };
function drawChart() {
  const D = S.detail;
  if (!D || !sheet) return;
  const box = $('.kw-chart', sheet);
  if (!box || box.hidden) return;
  const it = S.data[D.kind] && S.data[D.kind].byKey.get(D.key);
  const seg = h('div', { class: 'seg kw-tf', role: 'group', 'aria-label': '차트 기간' }, TFS.map(([v, lab]) =>
    h('button', { type: 'button', 'aria-pressed': String(D.tf === v), onclick: () => { if (D.tf === v) return; D.tf = v; loadChart(); } }, lab)));
  const C = D.chart;
  const top = h('div', { class: 'kw-ctop' }, seg, h('span', { class: 'kw-cnote', text: '일봉 종가 · 마지막 점은 현재 값' }));
  if (!C || C.loading) { box.replaceChildren(top, h('div', { class: 'kw-cmsg', text: '차트를 불러오는 중이에요…' })); return; }
  if (C.err) {
    box.replaceChildren(top, h('div', { class: 'kw-cmsg' }, C.gone ? '이 항목은 차트 자료가 없어요.' : '차트를 불러오지 못했어요. ',
      C.gone ? null : h('button', { type: 'button', class: 'kw-retry sm', onclick: () => { CH.delete(D.key + '|' + D.tf); loadChart(); } }, '다시 시도')));
    return;
  }
  const bars = C.bars.slice();
  // the last point follows the live value: today's bar (or a new one when the daily source lags behind)
  const L = it && parseLocal(it.tradedAt);
  if (L && bars.length) {
    const day = `${L.y}-${pad(L.mo)}-${pad(L.d)}`, lastB = bars[bars.length - 1];
    if (lastB.t === day) { if (lastB.c !== it.value) bars[bars.length - 1] = { t: day, c: it.value }; }
    else if (lastB.t < day) bars.push({ t: day, c: it.value });
  }
  if (bars.length < 2) { box.replaceChildren(top, h('div', { class: 'kw-cmsg', text: '차트 자료가 아직 없어요.' })); return; }
  const W = Math.max(220, Math.round(box.clientWidth || 300)), H = 150, padL = 2, padR = 58, padT = 10, padB = 20;
  const cs = bars.map(b => b.c);
  const lo = Math.min(...cs), hi = Math.max(...cs), first = cs[0], last = cs[cs.length - 1];
  const x = i => padL + (i / (bars.length - 1)) * (W - padL - padR);
  const y = v => hi === lo ? padT + (H - padT - padB) / 2 : padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const line = bars.map((b, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(b.c).toFixed(1)).join('');
  const area = line + `L${x(bars.length - 1).toFixed(1)} ${H - padB}L${x(0).toFixed(1)} ${H - padB}Z`;
  const chg = (last / first - 1) * 100;
  const dirc = isRef(it || {}) ? 'flat' : cls(chg);
  const dp = it ? dpOf(it) : 2;
  const s = svg('svg', { class: 'kw-svg ' + dirc, viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': `${TFS.find(t => t[0] === D.tf)[1]} 차트: ${shortDate(bars[0].t)} ${fixed(first, dp)}에서 ${shortDate(bars[bars.length - 1].t)} ${fixed(last, dp)}, ${pct(chg)}. 최고 ${fixed(hi, dp)}, 최저 ${fixed(lo, dp)}` });
  s.append(
    svg('line', { class: 'kw-base', x1: padL, x2: W - padR, y1: y(first).toFixed(1), y2: y(first).toFixed(1) }),
    svg('path', { class: 'kw-area', d: area }),
    svg('path', { class: 'kw-line', d: line }),
    svg('text', { class: 'kw-yl', x: W - padR + 6, y: (y(hi) + 4).toFixed(1) }, document.createTextNode(fixed(hi, dp))),
    svg('text', { class: 'kw-yl', x: W - padR + 6, y: (y(lo) + 1).toFixed(1) }, document.createTextNode(fixed(lo, dp))),
    svg('text', { class: 'kw-xl', x: padL, y: H - 5 }, document.createTextNode(D.tf === '1y' ? shortDateY(bars[0].t) : shortDate(bars[0].t))),
    svg('text', { class: 'kw-xl', x: W - padR, y: H - 5, 'text-anchor': 'end' }, document.createTextNode(D.tf === '1y' ? shortDateY(bars[bars.length - 1].t) : shortDate(bars[bars.length - 1].t))));
  const cross = svg('line', { class: 'kw-cross', y1: padT, y2: H - padB, x1: -10, x2: -10 });
  const dot = svg('circle', { class: 'kw-cdot', r: 3, cx: x(bars.length - 1), cy: y(last) });
  s.append(cross, dot);
  const read = h('div', { class: 'kw-read' });
  const showAt = i => {
    const b = bars[i], r = (b.c / first - 1) * 100;
    read.replaceChildren(h('span', { text: D.tf === '1y' ? shortDateY(b.t) : shortDate(b.t) }), h('b', { text: fixed(b.c, dp) }),
      h('span', { class: isRef(it || {}) ? 'flat' : cls(r), text: i ? `${pct(r)} (기간 시작 대비)` : '기간 시작' }));
    dot.setAttribute('cx', x(i)); dot.setAttribute('cy', y(b.c));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i));
  };
  const reset = () => {
    read.replaceChildren(h('span', { text: `${TFS.find(t => t[0] === D.tf)[1]} 동안` }), h('b', { class: isRef(it || {}) ? 'flat' : cls(chg), text: pct(chg) }),
      h('span', { class: 'kw-hl', text: `최고 ${fixed(hi, dp)} · 최저 ${fixed(lo, dp)}` }));
    dot.setAttribute('cx', x(bars.length - 1)); dot.setAttribute('cy', y(last));
    cross.setAttribute('x1', -10); cross.setAttribute('x2', -10);
  };
  s.addEventListener('pointermove', e => {
    const r = s.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    const i = Math.max(0, Math.min(bars.length - 1, Math.round((px - padL) / (W - padL - padR) * (bars.length - 1))));
    showAt(i);
  });
  s.addEventListener('pointerleave', reset);
  reset();
  box.replaceChildren(top, read, s);
}

/* ───────── polling ───────── */
function schedule(ms) {
  clearTimeout(S.timer); S.timer = 0;
  if (!S.shown || !LIVE) return;
  S.timer = setTimeout(() => load(S.kind), ms);
}
async function load(kind) {
  clearTimeout(S.timer); S.timer = 0;
  if (!S.shown || S.kind !== kind || !LIVE || document.hidden) return;
  const seq = ++S.seq;
  if (S.ac) S.ac.abort();
  const ac = S.ac = new AbortController();
  S.busy = kind;
  if (!S.data[kind] && S.err[kind]) { S.err[kind] = null; render(); }   // a retry from the error box shows "loading" again
  let ok = false;
  try {
    const j = await getJSON('api/world?kind=' + kind, ac.signal);
    if (seq !== S.seq) return;
    S.data[kind] = normalise(j, kind);
    S.at[kind] = Date.now();
    S.err[kind] = null;
    ok = true;
  } catch (e) {
    if (seq !== S.seq) return;
    S.err[kind] = e;
  }
  S.busy = null;
  render();
  announce(kind, ok);
  schedule(ok ? POLL_MS : RETRY_MS);
}
function announce(kind, ok) {
  const K = KINDS[kind], key = kind + (ok ? ':ok' : ':err');
  if (S.announced[kind] === key) return;
  S.announced[kind] = key;
  const d = S.data[kind];
  els.live.textContent = ok ? (d && d.all.length ? `${K.title} ${d.all.length}개를 불러왔어요` : K.empty) : (d ? `${K.title}를 새로 받지 못했어요. 이전 값을 보여 줘요` : K.fail);
}
document.addEventListener('visibilitychange', () => {
  if (!S.shown || !LIVE) return;
  if (document.hidden) { clearTimeout(S.timer); S.timer = 0; S.seq++; S.busy = null; if (S.ac) S.ac.abort(); return; }
  const age = Date.now() - (S.at[S.kind] || 0);
  if (!S.data[S.kind] || age >= POLL_MS) load(S.kind); else schedule(POLL_MS - age);
});
document.addEventListener('kh:palette', () => {
  if (!S.shown || !els || els.snap) return;
  render();
  if (S.detail) drawChart();
});
addEventListener('resize', () => { if (S.shown) schedRender(); });
if (document.fonts) {
  const refit = () => { MW.clear(); family = ''; if (S.shown) schedRender(); };
  if (document.fonts.ready) document.fonts.ready.then(refit);
  document.fonts.addEventListener && document.fonts.addEventListener('loadingdone', refit);
}

/* ───────── public API ───────── */
function show(kind) {
  kind = kind === 'commodity' || kind === 'cmdty' ? 'commodity' : 'index';
  if (!scaffold()) return;
  const sameKind = S.kind === kind;
  if (!sameKind) { closeDetail(false); S.kind = kind; S.focusKey = null; if (els.tiles) { for (const el of els.tiles.values()) el.remove(); for (const el of els.heads.values()) el.remove(); els.tiles.clear(); els.heads.clear(); } }
  const was = S.shown;
  S.shown = true;
  if (!LIVE) { renderSnapshot(); return; }
  render();
  if (was && sameKind && (S.timer || S.busy === kind)) return;   // already polling / loading this kind
  const age = Date.now() - (S.at[kind] || 0);
  if (!S.data[kind] || age >= POLL_MS) load(kind); else schedule(POLL_MS - age);
}
function hide() {
  S.shown = false;
  clearTimeout(S.timer); S.timer = 0;
  S.seq++; S.busy = null;
  if (S.ac) S.ac.abort();
  closeDetail(false);
}
// the map as drawn now, in map pixels (same shape as KH.layout(), for saving an image)
function layout() {
  if (!S.shown || !els || els.snap || !els.boxes) return [];
  const out = [];
  for (const g of els.boxes.heads) {
    const el = els.heads.get(g.g.key);
    out.push({ kind: 'sector', x: g.x, y: g.y, w: g.w, h: g.h, color: '#000', label: g.hd ? g.g.name : '', sub: g.hd && el ? el.__sub || '' : '', hd: g.hd });
  }
  for (const t of els.boxes.tiles) {
    const el = els.tiles.get(t.it.key);
    out.push({ kind: 'tile', x: t.x, y: t.y, w: t.w, h: t.h, color: el ? el.__col : colorOf(t.it), label: t.it.name, sub: el ? el.__sub || '' : '', code: t.it.key });
  }
  return out;
}
window.KHWorld = { show, hide, layout, shown: () => S.shown ? S.kind : null };

// the template may have tried show() before this script existed (page opened at #world / #cmdty): start now
try {
  const m = typeof KH.market === 'function' ? KH.market() : null;
  const w = document.getElementById('world');
  if ((m === 'world' || m === 'cmdty') && w && !w.hidden) show(m === 'cmdty' ? 'commodity' : 'index');
} catch (e) { /* the template will call show() itself */ }
})();
