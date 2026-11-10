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
// localStorage can throw (private mode, blocked storage): the choice then lasts for this page only
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* not kept */ } },
};
const VIEW_KEY = 'khm.worldView', SORT_KEY = 'khm.worldSort';
const S = {
  kind: null, shown: false,
  data: { index: null, commodity: null }, at: { index: 0, commodity: 0 }, err: { index: null, commodity: null },
  seq: 0, ac: null, timer: 0, busy: null, announced: {},
  focusKey: null, detail: null, chartRoute: true,
  view: store.get(VIEW_KEY) === 'map' ? 'map' : 'list',          // 목록 is the default (AGENTS §3-4), shared by both tabs
  sort: store.get(SORT_KEY) === 'pct' ? 'pct' : 'group',
  listFocus: null,
};
let root = null, els = null;
// effect level (AGENTS §3-5): KH.motion() when the heatmap has it, else the OS setting decides between reduced and standard
function motion() {
  try { if (typeof KH.motion === 'function') { const m = KH.motion(); return m === 'reduced' || m === 'fancy' ? m : 'standard'; } } catch (e) { /* fall through */ }
  return reduceMQ.matches ? 'reduced' : 'standard';
}
const calm = () => motion() === 'reduced';
function syncMotion() {
  if (!root) return;
  const m = motion();
  root.classList.toggle('kw-fx', m === 'fancy');            // new effects (open-market pulse, map intro) only here
  root.classList.toggle('kw-rm', m === 'reduced');          // no transitions at all
  if (sheet) sheet.classList.toggle('kw-noanim', m === 'reduced');
}

/* normalise one /api/world payload; throws on a wrong shape */
function normalise(j, kind) {
  if (!j || !Array.isArray(j.groups)) throw new Error('응답 모양이 달라요');
  const groups = [], seen = new Set();
  let ix = 0;
  for (const g of j.groups) {
    if (!g || !Array.isArray(g.items)) continue;
    const items = [];
    for (const x of g.items) {
      if (!x || x.key == null || x.value == null || !isFinite(+x.value) || seen.has(String(x.key))) continue;
      seen.add(String(x.key));
      const it = {
        key: String(x.key), name: String(x.name || x.key), value: +x.value,
        change: x.change == null || !isFinite(+x.change) ? null : +x.change,
        ratio: x.ratio == null || !isFinite(+x.ratio) ? null : +x.ratio,
        status: x.status === 'OPEN' ? 'OPEN' : 'CLOSE', tradedAt: x.tradedAt || null,
        delayed: +x.delayed > 0 ? +x.delayed : 0, unit: x.unit || null, tz: x.tz || null,
        ref: !!(x.ref || g.ref), group: String(g.name || ''), gkey: String(g.key || ''), ix: ix++,
      };
      items.push(it);
    }
    if (!items.length) continue;
    // biggest first inside a group (stable for equal weights), so the squarified layout puts headline tiles top-left;
    // the list keeps the Worker's order (`list`)
    const ordered = items.map((it, i) => [it, i]).sort((a, b) => weightOf(b[0]) - weightOf(a[0]) || a[1] - b[1]).map(a => a[0]);
    groups.push({ key: String(g.key || g.name), name: String(g.name || ''), items: ordered, list: items });
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
  const list = h('div', { class: 'kw-list', role: 'group', hidden: true });
  const geo = h('div', { class: 'kw-geo', hidden: true });
  const note = h('p', { class: 'kw-gnote', role: 'status', hidden: true }, '세계지도를 불러오지 못해서 목록으로 보여 드려요. ',
    h('button', { type: 'button', class: 'kw-retry sm', onclick: () => { GEO.state = 'idle'; render(); } }, '다시 시도'));
  const seg = (name, label, opts) => h('div', { class: 'seg kw-seg', role: 'group', 'aria-label': label, 'data-kw': name },
    opts.map(([v, t]) => h('button', { type: 'button', 'data-v': v, 'aria-pressed': 'false' }, t)));
  const sortSeg = seg('sort', '정렬', [['group', '지역순'], ['pct', '등락률순']]);
  const viewSeg = seg('view', '보기', [['list', '목록'], ['map', '지도']]);
  const tools = h('div', { class: 'kw-tools' }, sortSeg, viewSeg);
  const bar = h('div', { class: 'kw-bar' }, h('h2', { class: 'kw-title' }), h('span', { class: 'kw-sum' }), h('span', { class: 'kw-time' }), tools);
  const legend = h('div', { class: 'legend kw-legend' });
  const rank = h('div', { class: 'kw-rank' });
  const open = h('div', { class: 'kw-open' });
  const src = h('p', { class: 'kw-src' });
  const live = h('div', { class: 'sr', role: 'status', 'aria-live': 'polite' });
  root.append(
    h('section', { class: 'kw-stage' }, bar, note, list, map, geo, legend),
    h('aside', { class: 'kw-side' },
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '많이 오른·내린' }), h('small', { class: 'kw-rank-sub' })), rank),
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '지금 열린 시장' }), h('small', { text: '현지 시각' })), open),
      src),
    live);
  els = { map, list, geo, note, bar, tools, sortSeg, viewSeg, legend, rank, open, src, live, tiles: new Map(), heads: new Map(), boxes: null, mapW: 0,
    rows: new Map(), listW: 0, listSig: '', g: null };
  root.__kw = true;
  map.addEventListener('click', e => { const t = e.target.closest('.kw-tile'); if (t) openDetail(t.dataset.k, t); });
  map.addEventListener('keydown', onMapKey);
  map.addEventListener('focusin', e => { const t = e.target.closest('.kw-tile'); if (t) setRoving(t.dataset.k); });
  list.addEventListener('click', e => { const r = e.target.closest('.kw-lr'); if (r) openDetail(r.dataset.k, r); });
  list.addEventListener('keydown', onListKey);
  list.addEventListener('focusin', e => { const r = e.target.closest('.kw-lr'); if (r) setListFocus(r.dataset.k); });
  rank.addEventListener('click', e => { const b = e.target.closest('.kw-row'); if (b) openDetail(b.dataset.k, b); });
  tools.addEventListener('click', e => {
    const b = e.target.closest('.kw-seg button[data-v]');
    if (!b) return;
    const k = b.parentElement.dataset.kw, v = b.dataset.v;
    if (k === 'view') setView(v); else if (k === 'sort') setSort(v);
  });
  new ResizeObserver(() => { if (S.shown && S.view === 'map' && els.map.clientWidth !== els.mapW) schedRender(); }).observe(map);
  new ResizeObserver(() => { if (S.shown && S.view === 'list' && els.list.clientWidth !== els.listW) schedRender(); }).observe(list);
  new ResizeObserver(() => { if (S.shown && S.mode === 'geo' && els.g && els.geo.clientWidth !== els.g.W) schedRender(); }).observe(geo);
  // the open-market pulse ('fancy') stops while the map is off screen or the browser tab is hidden
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { for (const e of es) S.offscreen = !e.isIntersecting; root.classList.toggle('kw-paused', document.hidden || !!S.offscreen); }).observe(geo);
  geo.addEventListener('click', onGeoClick);
  geo.addEventListener('keydown', onGeoKey);
  geo.addEventListener('focusin', e => { const b = e.target.closest('.kw-gb'); if (b) setGeoFocus(b.dataset.f); });
  return true;
}
function setView(v) {
  v = v === 'map' ? 'map' : 'list';
  if (v === 'map' && GEO.state === 'failed' && S.kind === 'index') { GEO.state = 'idle'; S.view = v; store.set(VIEW_KEY, v); render(); return; }   // try the world map again
  if (S.view === v) return;
  S.view = v;
  store.set(VIEW_KEY, v);
  render();
}
function setSort(v) {
  v = v === 'pct' ? 'pct' : 'group';
  if (S.sort === v) return;
  S.sort = v;
  store.set(SORT_KEY, v);
  render();
}
function syncTools(hasData, mode) {
  if (!els || !els.tools) return;
  // the pressed button says what is on screen (the list stands in when the world map could not load)
  const shown = mode === 'list' ? 'list' : mode === 'msg' ? S.view : 'map';
  for (const b of els.viewSeg.children) b.setAttribute('aria-pressed', String(b.dataset.v === shown));
  for (const b of els.sortSeg.children) b.setAttribute('aria-pressed', String(b.dataset.v === S.sort));
  els.sortSeg.children[0].textContent = S.kind === 'commodity' ? '종류순' : '지역순';
  els.sortSeg.hidden = mode !== 'list' || !hasData;
  els.viewSeg.hidden = S.kind === 'commodity';
}

let rafR = 0;
const schedRender = () => { cancelAnimationFrame(rafR); rafR = requestAnimationFrame(() => { if (S.shown) render(); }); };

/* ───────── render ───────── */
function render() {
  if (!S.shown || !els) return;
  if (els.snap) return renderSnapshot();
  syncMotion();
  const K = KINDS[S.kind], d = S.data[S.kind], err = S.err[S.kind];
  $('.kw-title', els.bar).textContent = K.title;
  $('.kw-side', root).setAttribute('aria-label', `${K.title} 요약`);
  els.map.setAttribute('aria-label', `${K.title} 지도. 화살표로 옮기고 Enter로 자세히 봐요`);
  els.list.setAttribute('aria-label', `${K.title} 목록. 위아래 화살표로 옮기고 Enter로 자세히 봐요`);
  const hasData = !!(d && d.all.length);
  // what the stage shows: a message box (loading / failure / empty), the list, the tile map, or — 해외 지수 in 지도 — the world map
  // 원자재 has no geography, so it is list-only (user 2026-11-10: "지도는 세계지도만"); 해외 지수 keeps 목록 · 지도(세계지도)
  const view = S.kind === 'commodity' ? 'list' : S.view;
  const wantGeo = hasData && view === 'map' && S.kind === 'index';
  if (wantGeo && GEO.state === 'idle') loadAtlas();
  const geoFailed = wantGeo && GEO.state === 'failed';
  const mode = !hasData ? 'msg' : view === 'list' || geoFailed ? 'list' : wantGeo ? (GEO.state === 'ready' ? 'geo' : 'geoload') : 'tiles';
  S.mode = mode;
  if (mode !== 'geo') { clearTimeout(nightT); nightT = 0; }
  syncTools(hasData, mode);
  els.list.hidden = mode !== 'list';
  els.geo.hidden = mode !== 'geo';
  els.map.hidden = mode === 'list' || mode === 'geo';
  els.note.hidden = !geoFailed;
  root.classList.toggle('kw-v-list', mode === 'list');
  root.classList.toggle('kw-v-geo', mode === 'geo');
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
  renderBar(d, err);
  if (mode === 'geoload') {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(msgBox('세계지도를 불러오는 중이에요…', '나라 경계 자료(Natural Earth)를 처음 한 번 받아 와요.', false, true));
  } else if (els.map.classList.contains('kw-msgmode')) { els.map.classList.remove('kw-msgmode'); els.map.replaceChildren(); }
  if (mode === 'list') renderList(d);
  else if (mode === 'geo') renderGeo(d);
  else if (mode === 'tiles') renderMap(d);
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
function computeLayout(d, W, Hfix) {
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
    const H = Hfix || mapHeightDesktop(d, W);
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
  if (S.mode === 'geo') {
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw', style: `background:${GEO_NONE};box-shadow:inset 0 0 0 1px var(--line2)` }), h('span', { text: '지수 없는 나라' })));
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'kw-sd open', 'aria-hidden': 'true' }), h('span', { text: '장중' }),
      h('i', { class: 'kw-sd close', 'aria-hidden': 'true' }), h('span', { text: '마감' })));
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw kw-nightsw', 'aria-hidden': 'true' }), h('span', { text: '어두운 쪽은 지금 밤' })));
    kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '나라 색' }), h('b', { text: '대표 지수 등락률' }), h('span', { class: 'note', text: '눌러서 그 나라 지수를 모두 봐요' })));
    els.legend.replaceChildren(...kids);
    return;
  }
  if (S.mode === 'list') {
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'kw-sd open', 'aria-hidden': 'true' }), h('span', { text: '장중' }),
      h('i', { class: 'kw-sd close', 'aria-hidden': 'true' }), h('span', { text: '마감' })));
    if (R) kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '막대' }), h('b', { text: `가운데가 0 · 끝이 ±${R}%` })));
    els.legend.replaceChildren(...kids);
    return;
  }
  kids.push(h('span', { class: 'lg' }, h('span', { class: 'kw-chip-l open', 'aria-hidden': 'true', text: '장중' }), h('span', { class: 'kw-chip-l close', 'aria-hidden': 'true', text: '마감' }),
    h('span', { class: 'sr', text: '타일 왼쪽 위 표시: 장중 또는 마감, 지연 시간' })));
  kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '대표 지수를 크게' }), h('span', { class: 'note', text: '시가총액과는 관계없어요' })));
  if (S.kind === 'commodity') kids[kids.length - 1] = h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '주요 품목을 크게' }), h('span', { class: 'note', text: '거래 규모와는 관계없어요' }));
  els.legend.replaceChildren(...kids);
}

/* ───────── list view (the default, AGENTS §3-4 "목록이 기본") ─────────
   Sections per group (or one ranked list), laid out in 1–3 columns by the list's width; rows are kept per key and
   updated in place on every refresh, so focus and scroll stay put. Wide rows are one line (name · state · value ·
   change · % chip · bar); narrow columns get a two-line row (name / state, value / change). */
const PLACE = {
  DJI: '뉴욕', INX: '뉴욕', IXIC: '뉴욕', NDX: '뉴욕', SOX: '뉴욕', DJT: '뉴욕', RUT: '뉴욕',
  EScv1: '시카고', NQcv1: '시카고', YMcv1: '시카고', RTYcv1: '시카고', VIX: '시카고',
  STOXX50E: '유로존', GDAXI: '프랑크푸르트', FTSE: '런던', FCHI: '파리', AEX: '암스테르담', IBEX: '마드리드', FTMIB: '밀라노',
  OMXS30: '스톡홀름', BFX: '브뤼셀', PSI20: '리스본', ISEQ: '더블린', BUX: '부다페스트',
  N225: '도쿄', TOPX: '도쿄', SSEC: '상하이', SZSC: '선전', CSI300: '상하이·선전', HSI: '홍콩', HSCE: '홍콩', TWII: '타이베이',
  BSESN: '뭄바이', VNI: '호찌민', HNXI: '하노이', AXJO: '시드니', JKSE: '자카르타', KLSE: '쿠알라룸푸르',
  BVSP: '상파울루', MXX: '멕시코시티', KOSPI: '서울', KOSDAQ: '서울',
};
// one-line rows: name (≥ NAME_MIN) · state 64 · value · change · chip 66 · bar 48, gaps 8, row padding 12, section 14 (CSS)
const NAME_MIN = 118, FIXED_W = 64 + 66 + 48 + 5 * 8 + 12 + 14, MIN_COL_C = 300, COL_GAP = 12;
const ROW_H = 36, ROW_HC = 52, HEAD_H = 42, SEC_PAD = 12;
const placeOf = it => PLACE[it.key] || cityOf(it, null) || '';
function listSub(it, flat) {
  const u = S.kind === 'commodity' ? unitOf(it) : null;
  if (flat) return [it.group, u ? u[1] : null].filter(Boolean).join(' · ');
  return u ? u[1] : placeOf(it);
}
function avgOf(items) {
  const v = items.filter(it => !isRef(it) && it.ratio != null).map(it => it.ratio);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
function stateOf(items) {
  let o = 0, c = 0;
  for (const it of items) if (it.status === 'OPEN') o++; else c++;
  if (o && c) return { open: true, text: `장중 ${o} · 마감 ${c}` };
  if (!o) return { open: false, text: '마감' };
  const dl = new Set(items.map(it => it.delayed));
  return { open: true, text: dl.size === 1 ? (items[0].delayed ? `장중 · ${items[0].delayed}분 지연` : '장중 · 실시간') : '장중' };
}
// text on a palette colour: white or black, whichever has more contrast (the worst case is 4.58:1)
const INK_DARK = '#000';
function rgbOf(c) {
  let m = /^#([0-9a-f]{6})$/i.exec(c);
  if (m) { const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  m = /^#([0-9a-f]{3})$/i.exec(c);
  if (m) return m[1].split('').map(x => parseInt(x + x, 16));
  m = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(c);
  return m ? [+m[1], +m[2], +m[3]] : null;
}
function luma(rgb) {
  const L = rgb.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * L[0] + 0.7152 * L[1] + 0.0722 * L[2];
}
const DARK_Y = luma(rgbOf(INK_DARK));
function inkOn(c) {
  const rgb = rgbOf(String(c || ''));
  if (!rgb) return '#fff';
  const y = luma(rgb);
  return 1.05 / (y + 0.05) >= (y + 0.05) / (DARK_Y + 0.05) ? '#fff' : INK_DARK;
}

// columns by width: as many one-line columns as fit (≤ 3), else two two-line columns (tablets), else one column
function listGeom(W, minWide) {
  for (const n of [3, 2]) if ((W - (n - 1) * COL_GAP) / n >= minWide) return { n, compact: false };
  if ((W - COL_GAP) / 2 >= MIN_COL_C) return { n: 2, compact: true };
  return { n: 1, compact: W < minWide };
}
// sections → columns with heights as even as possible. Contiguous runs keep the reading order; when that leaves one
// column much taller, the biggest sections are spread first (each column still lists its sections in the original order).
function distribute(secs, n, rowH) {
  const hs = secs.map(s => (s.head ? HEAD_H : 6) + s.items.length * rowH + SEC_PAD);
  const colH = idx => idx.reduce((a, i) => a + hs[i], 0) + Math.max(0, idx.length - 1) * COL_GAP;
  n = Math.min(n, secs.length);
  if (n <= 1) return [secs];
  let best = null;
  const rec = (start, left, acc) => {
    if (left === 1) {
      const cols = acc.concat([secs.map((s, i) => i).slice(start)]);
      const m = Math.max(...cols.map(colH));
      if (!best || m < best.m) best = { m, cols };
      return;
    }
    for (let end = start + 1; end <= secs.length - left + 1; end++) rec(end, left - 1, acc.concat([secs.map((s, i) => i).slice(start, end)]));
  };
  rec(0, n, []);
  const order = secs.map((s, i) => i).sort((a, b) => hs[b] - hs[a] || a - b);
  const cols = Array.from({ length: n }, () => []);
  for (const i of order) cols.reduce((m, c) => colH(c) < colH(m) ? c : m).push(i);
  cols.forEach(c => c.sort((a, b) => a - b));
  cols.sort((a, b) => a[0] - b[0]);
  const lpt = Math.max(...cols.map(colH));
  const pick = best && best.m <= lpt * 1.08 ? best.cols : cols;
  return pick.map(c => c.map(i => secs[i]));
}
function buildColumns(d, geo) {
  const rowH = geo.compact ? ROW_HC : ROW_H;
  if (S.sort !== 'pct') {
    const secs = d.groups.map(g => ({ key: g.key, name: g.name, head: true, items: g.list, ref: g.list.every(isRef), rank: 0 }));
    return distribute(secs, geo.n, rowH);
  }
  // 등락률순: one ranked list (missing values last, ties in the Worker's order), split evenly over the columns; VIX at the end
  const rv = it => it.ratio == null ? -Infinity : it.ratio;
  const main = d.all.filter(it => !isRef(it)).sort((a, b) => rv(b) - rv(a) || a.ix - b.ix);
  const refs = d.all.filter(isRef);
  const n = Math.max(1, Math.min(geo.n, Math.ceil(main.length / 4)));
  const per = Math.ceil(main.length / n);
  const cols = [];
  for (let c = 0; c < n; c++) {
    const items = main.slice(c * per, (c + 1) * per);
    if (!items.length) continue;
    const a = c * per + 1, b = c * per + items.length;
    cols.push([{ key: 'rank' + c, name: c === 0 ? `등락률 높은 순 · ${a}–${b}위` : `${a}–${b}위`, head: true, items, rank: a, flat: true }]);
  }
  if (refs.length) (cols[cols.length - 1] || (cols[0] = [])).push({ key: 'ref', name: '참고', head: true, items: refs, ref: true, flat: true });
  return cols;
}
function rowEl(it) {
  let el = els.rows.get(it.key);
  if (!el) {
    el = h('button', { type: 'button', class: 'kw-lr', 'data-k': it.key, tabindex: '-1' },
      h('span', { class: 'kw-ln', 'aria-hidden': 'true' }, h('span', { class: 'rk' }), h('span', { class: 'nm' }), h('span', { class: 'sub' })),
      h('span', { class: 'kw-ls', 'aria-hidden': 'true' }, h('i', { class: 'kw-sd' }), h('span', { class: 'st' }), h('span', { class: 'sub2' })),
      h('span', { class: 'kw-lv', 'aria-hidden': 'true' }),
      h('span', { class: 'kw-lc', 'aria-hidden': 'true' }),
      h('span', { class: 'kw-lp', 'aria-hidden': 'true' }, h('span', { class: 'kw-pchip' })),
      h('span', { class: 'kw-lb', 'aria-hidden': 'true' }, h('i')));
    el.addEventListener('animationend', e => e.target.classList.remove('kw-fl'));   // a moved row must not fade again
    els.rows.set(it.key, el);
  }
  return el;
}
function flash(el) {
  if (calm()) return;
  el.classList.remove('kw-fl');
  void el.offsetWidth;                                   // restart the fade when values change on consecutive refreshes
  el.classList.add('kw-fl');
}
function fillRow(el, it, sub, rank, R) {
  const [ln, ls, lv, lc, lp, lb] = el.children;
  const [rk, nm, sb] = ln.children;
  const ref = isRef(it), open = it.status === 'OPEN';
  rk.textContent = rank ? String(rank) : '';
  rk.hidden = !rank;
  if (nm.textContent !== it.name) nm.textContent = it.name;
  const subText = ref ? '참고' : sub || '';
  sb.textContent = subText;
  sb.hidden = !subText;
  sb.className = 'sub' + (ref ? ' tag' : '');
  ls.children[0].className = 'kw-sd ' + (open ? 'open' : 'close');
  ls.children[1].textContent = open ? (it.delayed ? `${it.delayed}분 지연` : '실시간') : '마감';
  ls.children[1].className = 'st' + (open && it.delayed ? ' dl' : '');
  ls.children[2].textContent = ref ? '' : sub || '';
  const v = valText(it), c = chgText(it), p = pct(it.ratio);
  const was = el.__vals;
  lv.textContent = v;
  lc.textContent = c;
  lc.className = 'kw-lc ' + (ref || it.change == null ? 'flat' : cls(it.change));
  const chip = lp.firstChild;
  chip.textContent = p;
  const col = ref ? null : colorOf(it);
  chip.style.backgroundColor = col || '';
  chip.style.color = col ? inkOn(col) : '';
  chip.className = 'kw-pchip' + (ref ? ' ref' : it.ratio == null ? ' nod' : '');
  // a short fade on values that changed since the last refresh (none under reduced motion)
  if (was && was.v !== v) flash(lv);
  if (was && was.p !== p) flash(chip);
  el.__col = col;
  const bar = lb.firstChild;
  const frac = it.ratio == null || !R ? 0 : Math.min(Math.abs(it.ratio) / R, 1) * 50;
  bar.style.width = frac.toFixed(2) + '%';
  bar.style.left = it.ratio >= 0 ? '50%' : '';
  bar.style.right = it.ratio < 0 ? '50%' : '';
  bar.style.backgroundColor = ref ? '' : col || '';
  bar.className = ref ? 'ref' : '';
  el.classList.toggle('ref', ref);
  el.__vals = { v, p };
  el.title = it.name;
  el.setAttribute('aria-label', ariaOf(it) + (rank ? `, ${rank}위` : ''));
  el.classList.toggle('sel', !!(S.detail && S.detail.key === it.key));
}
function fillHead(sec, hd) {
  const [t, s, a] = hd.children;
  t.textContent = sec.name;
  if (sec.flat && !sec.ref) { s.replaceChildren(); a.replaceChildren(); return; }
  const st = stateOf(sec.items);
  s.replaceChildren(h('i', { class: 'kw-sd ' + (st.open ? 'open' : 'close'), 'aria-hidden': 'true' }), st.text);
  if (sec.ref) { a.replaceChildren(h('small', { text: '색칠하지 않는 지표' })); return; }
  const avg = avgOf(sec.items);
  put(a, avg == null ? null : h('small', { text: '평균' }), avg == null ? null : h('b', { class: cls(avg), text: pct(avg) }));
}
function renderList(d) {
  const L = els.list;
  const W = L.clientWidth;
  if (!W) return;
  els.listW = W;
  // value / change columns: as wide as the widest text, so numbers line up across sections and columns
  let vw = 0, cw = 0;
  for (const it of d.all) { vw = Math.max(vw, tw(valText(it), 500)); cw = Math.max(cw, tw(chgText(it), 500)); }
  const geo = listGeom(W, NAME_MIN + FIXED_W + Math.ceil(vw * 13.5 + 4) + Math.ceil(cw * 12.5 + 4));
  const cols = buildColumns(d, geo);
  const fsV = geo.compact ? 14 : 13.5, fsC = geo.compact ? 12 : 12.5;
  L.style.setProperty('--kw-n', String(cols.length || 1));
  L.style.setProperty('--kw-vw', Math.ceil(vw * fsV + 4) + 'px');
  L.style.setProperty('--kw-cw', Math.ceil(cw * fsC + 4) + 'px');
  L.style.setProperty('--kw-vcw', Math.ceil(Math.max(vw * fsV, cw * fsC) + 4) + 'px');
  L.classList.toggle('compact', geo.compact);
  L.classList.toggle('flat', S.sort === 'pct');
  const sig = [S.kind, S.sort, geo.compact, cols.map(c => c.map(s => s.key + ':' + s.items.map(it => it.key).join(',')).join(';')).join('/')].join('|');
  const R = rangeNow();
  const subs = new Map();
  for (const col of cols) for (const sec of col) {
    // a place shared by every row of a section (미국 · 뉴욕) says nothing: leave it out
    const ss = sec.items.map(it => listSub(it, sec.flat));
    const same = !sec.flat && ss.length > 1 && ss.every(x => x === ss[0]) && S.kind !== 'commodity';
    sec.items.forEach((it, i) => subs.set(it.key, same ? '' : ss[i]));
  }
  if (sig !== els.listSig) {
    // structure changed (first draw, sort, width class, a new order in 등락률순): rebuild the shells, keep the row elements
    const ae = document.activeElement;
    const fk = ae && ae.classList && ae.classList.contains('kw-lr') && L.contains(ae) ? ae.dataset.k : null;
    const sy = scrollY;
    const keep = new Set(d.all.map(it => it.key));
    for (const [k, el] of els.rows) if (!keep.has(k)) { el.remove(); els.rows.delete(k); }
    L.replaceChildren(...cols.map(col => h('div', { class: 'kw-col' }, col.map(sec => {
      const id = `kw-sh-${S.kind}-${sec.key}`;
      const hd = h('h3', { class: 'kw-sh', id }, h('span', { class: 't' }), h('span', { class: 's' }), h('span', { class: 'a' }));
      const el = h('section', { class: 'kw-sec' + (sec.ref ? ' ref' : ''), 'data-g': sec.key, 'aria-labelledby': id }, hd,
        h('div', { class: 'kw-rows' }, sec.items.map(rowEl)));
      el.__sec = sec;
      return el;
    }))));
    els.listSig = sig;
    if (fk && els.rows.has(fk) && document.activeElement !== els.rows.get(fk)) els.rows.get(fk).focus({ preventScroll: true });
    if (scrollY !== sy) scrollTo(scrollX, sy);
  }
  // fill in place
  for (const secEl of L.querySelectorAll('.kw-sec')) {
    const old = secEl.__sec;
    const sec = cols.flat().find(s => s.key === old.key) || old;
    secEl.__sec = sec;
    fillHead(sec, secEl.firstChild);
    sec.items.forEach((it, i) => fillRow(els.rows.get(it.key), it, subs.get(it.key), sec.flat && !sec.ref ? sec.rank + i : 0, R));
  }
  if (!S.listFocus || !els.rows.has(S.listFocus)) S.listFocus = cols.length && cols[0][0] ? cols[0][0].items[0].key : null;
  for (const [k, el] of els.rows) el.tabIndex = k === S.listFocus ? 0 : -1;
  // a place or unit that would be cut is left out, so the name keeps its room (one layout read for all rows)
  if (!geo.compact) {
    const subEls = [...L.querySelectorAll('.kw-ln .sub:not(.tag)')];
    for (const x of subEls) x.classList.remove('cut');
    const cut = subEls.filter(x => !x.hidden && x.scrollWidth > x.clientWidth);
    for (const x of cut) x.classList.add('cut');
  }
}
function setListFocus(key) {
  if (!els.rows.has(key)) return;
  S.listFocus = key;
  for (const [k, el] of els.rows) el.tabIndex = k === key ? 0 : -1;
}
// one tab stop for the list; ↑/↓ row by row (across sections), ←/→ to the nearest row of the next column, Home/End
function onListKey(e) {
  const cur = e.target.closest('.kw-lr');
  if (!cur) return;
  const rows = [...els.list.querySelectorAll('.kw-lr')];
  const i = rows.indexOf(cur);
  let next = null;
  if (e.key === 'ArrowDown') next = rows[i + 1];
  else if (e.key === 'ArrowUp') next = rows[i - 1];
  else if (e.key === 'Home') next = rows[0];
  else if (e.key === 'End') next = rows[rows.length - 1];
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const cols = [...els.list.querySelectorAll('.kw-col')];
    const col = cols[cols.indexOf(cur.closest('.kw-col')) + (e.key === 'ArrowRight' ? 1 : -1)];
    if (col) {
      const y = cur.getBoundingClientRect().top;
      let bd = Infinity;
      for (const r of col.querySelectorAll('.kw-lr')) { const dd = Math.abs(r.getBoundingClientRect().top - y); if (dd < bd) { bd = dd; next = r; } }
    }
  } else return;
  e.preventDefault();
  if (next) { setListFocus(next.dataset.k); next.focus(); }
}

/* ───────── world map (해외 지수 · 지도, AGENTS §3-4) ─────────
   Countries filled with KH.colorOf(their representative index), Natural Earth projection, no Antarctica.
   Geometry: world-atlas 2.0.2 countries-110m (TopoJSON, Natural Earth, public domain), fetched from jsDelivr the first
   time the map view opens, checked with SRI. If it cannot be had, the list stands in with a note. */
const ATLAS = {
  url: 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json',
  sri: 'sha384-yOCJ+8ShBm8UDqtAVtAvxTDDf4gXo5edxl/YG0FmVC5OTmqVLl7utuVGBDEeZWHf',
};
const GEO = { state: 'idle', features: null, err: null };          // idle | loading | ready | failed
// representative index first (AGENTS list); `at` = where the label or leader line points (lon, lat);
// `col` = callout column for small or crowded countries, `big` = label inside the country
const COUNTRIES = [
  { id: '840', name: '미국', keys: ['INX', 'DJI', 'IXIC', 'NDX', 'SOX', 'DJT', 'RUT'], at: [-99, 39.5], big: true },
  { id: '484', name: '멕시코', keys: ['MXX'], at: [-102.5, 24], big: true },
  { id: '076', name: '브라질', keys: ['BVSP'], at: [-51.5, -10], big: true },
  { id: '372', name: '아일랜드', keys: ['ISEQ'], at: [-8, 53.2], col: 'atl' },
  { id: '826', name: '영국', keys: ['FTSE'], at: [-1.6, 52.6], col: 'atl' },
  { id: '528', name: '네덜란드', keys: ['AEX'], at: [5.6, 52.3], col: 'atl' },
  { id: '056', name: '벨기에', keys: ['BFX'], at: [4.6, 50.6], col: 'atl' },
  { id: '250', name: '프랑스', keys: ['FCHI'], at: [2.4, 46.8], col: 'atl' },
  { id: '620', name: '포르투갈', keys: ['PSI20'], at: [-8.1, 39.7], col: 'atl' },
  { id: '724', name: '스페인', keys: ['IBEX'], at: [-3.6, 40.2], col: 'atl' },
  { id: '752', name: '스웨덴', keys: ['OMXS30'], at: [15.5, 61], col: 'eur' },
  { id: '276', name: '독일', keys: ['GDAXI'], at: [10.4, 51], col: 'eur' },
  { id: '348', name: '헝가리', keys: ['BUX'], at: [19.3, 47.1], col: 'eur' },
  { id: '380', name: '이탈리아', keys: ['FTMIB'], at: [12.4, 43], col: 'eur' },
  { id: '356', name: '인도', keys: ['BSESN'], at: [78.5, 21.5], big: true },
  { id: '156', name: '중국', keys: ['SSEC', 'SZSC', 'CSI300'], at: [101, 32], big: true },
  { id: '410', name: '한국', keys: ['KOSPI', 'KOSDAQ'], at: [127.8, 36.4], col: 'kor' },
  { id: '392', name: '일본', keys: ['N225', 'TOPX'], at: [138.6, 36.4], col: 'pac' },
  { id: '158', name: '대만', keys: ['TWII'], at: [121, 23.7], col: 'pac' },
  { id: '344', name: '홍콩', keys: ['HSI', 'HSCE'], at: [114.17, 22.3], col: 'pac', marker: true },
  { id: '704', name: '베트남', keys: ['VNI', 'HNXI'], at: [106.3, 15.2], col: 'pac' },
  { id: '458', name: '말레이시아', keys: ['KLSE'], at: [101.8, 3.9], col: 'pac' },
  { id: '360', name: '인도네시아', keys: ['JKSE'], at: [113.6, -1], big: true },
  { id: '036', name: '호주', keys: ['AXJO'], at: [134, -25], big: true },
];
// callout columns: x from a meridian at a reference latitude, chips grow away from the map ('end' = to the left)
// (pac sits east of Japan's coast, so on narrower maps the clamped column still clears Honshu)
const GCOLS = { atl: { lon: -22, lat: 48, align: 'end' }, eur: { lon: 32, lat: 50, align: 'start' }, pac: { lon: 153, lat: 25, align: 'start' }, kor: { lon: 121.5, lat: 45, align: 'end', fixY: 44 } };
const GEO_NONE = '#1f2126', GCHIP_H = 21;

// TopoJSON → GeoJSON features (Polygon / MultiPolygon, quantized delta-encoded arcs), enough for world-atlas
function topoFeatures(topo, name) {
  const tf = topo.transform;
  const arcs = topo.arcs.map(a => {
    let x = 0, y = 0;
    return a.map(p => tf ? [(x += p[0]) * tf.scale[0] + tf.translate[0], (y += p[1]) * tf.scale[1] + tf.translate[1]] : [p[0], p[1]]);
  });
  const ring = ids => {
    const out = [];
    ids.forEach((i, k) => { const a = i < 0 ? arcs[~i].slice().reverse() : arcs[i]; for (let j = k ? 1 : 0; j < a.length; j++) out.push(a[j]); });
    return out;
  };
  const geom = g => g.type === 'Polygon' ? { type: 'Polygon', coordinates: g.arcs.map(ring) }
    : g.type === 'MultiPolygon' ? { type: 'MultiPolygon', coordinates: g.arcs.map(p => p.map(ring)) } : null;
  return topo.objects[name].geometries.map(g => ({ type: 'Feature', id: g.id == null ? null : String(g.id), properties: g.properties || {}, geometry: geom(g) }))
    .filter(f => f.geometry && f.id !== '010')                                       // no Antarctica
    .map(f => {
      if (f.id === '250' && f.geometry.type === 'MultiPolygon')                        // France without French Guiana (CAC 40 is Paris)
        f.geometry.coordinates = f.geometry.coordinates.filter(poly => poly[0][0][0] > -30);
      return f;
    });
}
async function loadAtlas() {
  if (GEO.state === 'loading' || GEO.state === 'ready') return;
  GEO.state = 'loading';
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);
  try {
    if (!window.d3 || typeof d3.geoNaturalEarth1 !== 'function') throw new Error('d3-geo가 없어요');
    const res = await fetch(ATLAS.url, { integrity: ATLAS.sri, mode: 'cors', credentials: 'omit', signal: ac.signal });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const topo = await res.json();
    if (!topo || !topo.objects || !topo.objects.countries) throw new Error('지도 자료 모양이 달라요');
    GEO.features = topoFeatures(topo, 'countries');
    GEO.state = 'ready';
  } catch (e) {
    GEO.state = 'failed';
    GEO.err = e;
  } finally { clearTimeout(timer); }
  if (S.shown) render();
}
function geoGroups(d) {
  const used = new Set(), cs = [];
  for (const c of COUNTRIES) {
    const items = c.keys.map(k => d.byKey.get(k)).filter(Boolean);
    items.forEach(it => used.add(it.key));
    if (items.length) cs.push({ c, items, rep: items[0] });
  }
  // every index the Worker files under 미국 belongs to the US
  const us = cs.find(x => x.c.id === '840');
  if (us) for (const it of d.all) if (it.gkey === 'us' && !used.has(it.key)) { us.items.push(it); used.add(it.key); }
  return { cs, off: d.all.filter(it => !used.has(it.key)) };
}
// one column of callouts: keep them in anchor order, at least CHIP_H + 3 apart, centred on their anchors, inside the map
function dodge(list, top, bottom) {
  const gap = GCHIP_H + 3;
  list.sort((a, b) => a.y0 - b.y0);
  let y = -Infinity;
  for (const it of list) { it.y = Math.max(it.y0, y + gap); y = it.y; }
  const shift = list.reduce((a, it) => a + it.y - it.y0, 0) / (list.length || 1);
  for (const it of list) it.y -= shift;
  if (list.length && list[0].y < top) { const s = top - list[0].y; for (const it of list) it.y += s; }
  y = -Infinity;
  for (const it of list) { it.y = Math.max(it.y, y + gap); y = it.y; }
  if (list.length && list[list.length - 1].y > bottom) { const s = list[list.length - 1].y - bottom; for (const it of list) it.y -= s; }
}
function geoProjection(W, narrow) {
  const P = d3.geoNaturalEarth1();
  let fit;
  if (narrow) {
    // phones: crop to where the indices are (the Americas to Japan), so the shapes are as big as the width allows
    P.rotate([-14, 0]);
    const pts = [];
    for (let lon = -126; lon <= 154; lon += 4) pts.push([lon, 66], [lon, -44]);
    fit = { type: 'MultiPoint', coordinates: pts };
  } else fit = { type: 'FeatureCollection', features: GEO.features };
  P.fitWidth(W, fit);
  const b = d3.geoPath(P).bounds(fit);
  const pad = narrow ? 4 : 8;
  P.translate([P.translate()[0], P.translate()[1] - b[0][1] + pad]);
  const H = Math.ceil(b[1][1] - b[0][1] + 2 * pad);
  P.clipExtent([[0, 0], [W, H]]);
  return { P, H };
}
const svgEl = (tag, attrs) => svg(tag, attrs);
const fx1 = v => v.toFixed(1);

/* day / night (AGENTS §3-5, docs/motion-brief.md (e)) — information, so drawn at every effect level, statically.
   Subsolar point from the low-precision almanac (good to ~0.01°, plenty at 110m); the night side is the 90° circle around
   the antisolar point, drawn as four nested caps (90 · 84 · 78 · 72° = sunset, civil, nautical, astronomical twilight) of
   12 % each, so the darkest part is ≈ 40 % and the countries' colours still read. Redrawn every minute (0.25°/min). */
const NIGHT_R = [90, 84, 78, 72];
const wrapLon = x => ((x % 360) + 540) % 360 - 180;
function subsolar(t) {
  const rad = Math.PI / 180, d = t / 864e5 - 10957.5;
  const g = (357.529 + 0.98560028 * d) * rad;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad;
  const e = (23.439 - 3.6e-7 * d) * rad;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)) / rad;
  const dec = Math.asin(Math.sin(e) * Math.sin(L)) / rad;
  const eqt = ((((q - ra) / 15) % 24) + 36) % 24 - 12;          // equation of time in hours, [−12, 12)
  const utc = (((t % 864e5) + 864e5) % 864e5) / 36e5;
  return [wrapLon(-15 * (utc - 12 + eqt)), dec];
}
function nightCentre(t) { const [lon, lat] = subsolar(t); return [wrapLon(lon + 180), -lat]; }
function drawNight() {
  const g = els && els.g;
  if (!g || !g.night.isConnected) return;
  const t = Date.now(), c = nightCentre(t), path = d3.geoPath(g.P);
  const cap = r => d3.geoCircle().center(c).radius(r).precision(2)();
  const kids = NIGHT_R.map(r => svgEl('path', { class: 'kw-gn', d: path(cap(r)) || '' }));
  // the terminator as a line (a polygon outline would also trace the map's edge where the cap is cut)
  kids.push(svgEl('path', { class: 'kw-gterm', d: path({ type: 'LineString', coordinates: cap(90).coordinates[0] }) || '' }));
  g.night.replaceChildren(...kids);
  g.night.dataset.lon = c[0].toFixed(2); g.night.dataset.lat = c[1].toFixed(2);
  g.nightMin = Math.floor(t / 60000);
}
let nightT = 0;
function schedNight() {
  clearTimeout(nightT); nightT = 0;
  if (!S.shown || S.mode !== 'geo' || document.hidden) return;
  nightT = setTimeout(() => { nightT = 0; drawNight(); schedNight(); }, 60000 - Date.now() % 60000 + 40);
}

function buildGeo(d, W, narrow, G, sig) {
  const ae = document.activeElement;
  const fk = ae && ae.classList && ae.classList.contains('kw-gb') && els.geo.contains(ae) ? ae.dataset.f : null;
  const { P, H } = geoProjection(W, narrow);
  const mid = !narrow && W < 880;
  const path = d3.geoPath(P);
  const byId = new Map(G.cs.map(x => [x.c.id, x]));
  const s = svgEl('svg', { class: 'kw-gsvg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, 'aria-hidden': 'true' });
  s.append(svgEl('path', { class: 'kw-gsea', d: path({ type: 'Sphere' }) }), svgEl('path', { class: 'kw-ggrat', d: path(d3.geoGraticule10()) }));
  // layers, bottom to top (motion brief (e)): fills → night → borders → open-market glow → selection / hover → leader lines → markers
  const land = svgEl('g', { class: 'kw-gland' });
  const paths = new Map(), dOf = new Map(), border = [];
  for (const f of GEO.features) {
    const dd = path(f);
    if (!dd) continue;
    border.push(dd);
    const x = byId.get(f.id);
    const p = svgEl('path', { class: 'kw-cp' + (x ? ' has' : ''), d: dd });
    if (x) { p.dataset.c = f.id; p.append(svgEl('title', {})); paths.set(f.id, p); dOf.set(f.id, dd); }
    land.append(p);
  }
  const layer = c => svgEl('g', { class: c });
  const night = layer('kw-gnight'), glow = layer('kw-gglow'), selG = layer('kw-gsel'), hov = layer('kw-ghov'), lines = layer('kw-glines'), marks = layer('kw-gmarks');
  glow.append(layer('kw-ggb'), layer('kw-ggl'));
  s.append(land, night, svgEl('path', { class: 'kw-gbord', d: border.join('') }), glow, selG, hov, lines, marks);
  const hovP = svgEl('path', {});
  hov.append(hovP);
  land.addEventListener('pointerover', e => { const p = e.target.closest('.kw-cp.has'); hovP.setAttribute('d', p ? dOf.get(p.dataset.c) || '' : ''); });
  land.addEventListener('pointerleave', () => hovP.setAttribute('d', ''));
  const labs = h('div', { class: 'kw-glabs' });
  const btns = new Map(), dots = new Map(), inLabs = [], colList = [];
  const cols = {};
  // a market marker: a 5 px dot (amber = open, hollow grey = closed) and, behind it, the ring that pulses in 'fancy'
  const delay = x => (((x.c.at[0] + 180) / 360) * 2.4).toFixed(2) + 's';       // west → east wave
  const addDot = (x, ax, ay, big) => {
    const pr = svgEl('circle', { class: 'kw-gp', cx: fx1(ax), cy: fx1(ay), r: big ? 4.5 : 2.5 });
    pr.style.animationDelay = delay(x);
    const dot = svgEl('circle', { class: big ? 'kw-gmk' : 'kw-gdot', cx: fx1(ax), cy: fx1(ay), r: big ? (narrow ? 3.5 : 4.5) : narrow ? 2.2 : 2.5 });
    dot.dataset.c = x.c.id;
    if (big) dot.append(svgEl('title', {}));
    marks.append(pr, dot);
    dots.set(x.c.id, { dot, pr });
  };
  for (const x of G.cs) {
    const [ax, ay] = P(x.c.at) || [NaN, NaN];
    if (!isFinite(ax) || ax < 0 || ax > W) continue;
    if (x.c.marker) addDot(x, ax, ay, true);                    // 홍콩: too small for the 110m map, a dot in its colour
    if (narrow) {
      // phones: the big markets carry a % on the map, the others a marker; the buttons under the map are the way in
      if (!x.c.big) { if (!x.c.marker) addDot(x, ax, ay, false); continue; }
      const b = h('span', { class: 'kw-gl in sm', 'data-c': x.c.id, 'aria-hidden': 'true', style: `--pd:${delay(x)}` }, h('i', { class: 'kw-sd' }), h('span', { class: 'p' }));
      labs.append(b); btns.set(x.c.id, b); inLabs.push({ el: b, x: ax, y: ay });
      continue;
    }
    if (x.c.big && !(mid && x.c.id === '360')) {
      const b = h('button', { type: 'button', class: 'kw-gb kw-gl in', 'data-c': x.c.id, 'data-f': 'c' + x.c.id, tabindex: '-1', style: `--pd:${delay(x)}` },
        h('span', { class: 'n' }, h('i', { class: 'kw-sd' }), h('span', { class: 't' })), h('span', { class: 'p' }));
      labs.append(b); btns.set(x.c.id, b); inLabs.push({ el: b, x: ax, y: ay });
      continue;
    }
    if (!x.c.marker) addDot(x, ax, ay, false);                  // the leader line starts at the market's marker
    // narrower maps: Korea (< 980 px, its chip would meet the European ones) and Indonesia (< 880 px) join the Pacific column
    const ck = (x.c.id === '410' && W < 980) || (mid && x.c.id === '360') ? 'pac' : x.c.col;
    const C = GCOLS[ck];
    (cols[ck] = cols[ck] || []).push({ x, ax, ay, y0: C.fixY != null ? P([C.lon, C.fixY])[1] : ay });
  }
  for (const k in cols) {
    const C = GCOLS[k];
    dodge(cols[k], GCHIP_H / 2 + 4, H - GCHIP_H / 2 - 4);
    const end = C.align === 'end';
    for (const it of cols[k]) {
      it.el = h('button', { type: 'button', class: 'kw-gb kw-gl chip' + (end ? ' end' : ''), 'data-c': it.x.c.id, 'data-f': 'c' + it.x.c.id, tabindex: '-1' },
        h('i', { class: 'kw-sd' }), h('span', { class: 't' }), h('span', { class: 'p' }));
      labs.append(it.el); btns.set(it.x.c.id, it.el);
    }
    colList.push({ x: P([C.lon, C.lat])[0], end, items: cols[k] });
  }
  // indices not tied to one country (US futures, Euro Stoxx 50, VIX): a small box beside the map
  const offBelow = narrow || mid;
  const off = h('div', { class: 'kw-goff' + (offBelow ? ' below' : '') }, h('div', { class: 'kw-goh', text: '나라에 묶이지 않는 지수' }),
    G.off.map(it => h('button', { type: 'button', class: 'kw-gb kw-go', 'data-k': it.key, 'data-f': 'k' + it.key, tabindex: '-1' },
      h('i', { class: 'kw-sd' }), h('span', { class: 't' }, it.name), h('span', { class: 'kw-pchip sm' }))));
  const mapBox = h('div', { class: 'kw-gmap', style: `height:${H}px;--gs:${Math.max(1, Math.min(1.22, W / 1150)).toFixed(3)}` }, s, labs, offBelow || !G.off.length ? null : off);
  // phones: every country as a tap target under the map
  const grid = narrow ? h('div', { class: 'kw-ggrid', role: 'group', 'aria-label': '나라별 대표 지수' }, G.cs.map(x =>
    h('button', { type: 'button', class: 'kw-gb kw-gc', 'data-c': x.c.id, 'data-f': 'c' + x.c.id, tabindex: '-1' },
      h('i', { class: 'sw' }), h('span', { class: 't' }, h('b', { text: x.c.name }), h('small')), h('span', { class: 'p' })))) : null;
  put(els.geo, mapBox, grid, offBelow && G.off.length ? off : null);
  els.geo.classList.toggle('narrow', narrow);
  const first = !els.g;
  els.g = { sig, W, H, P, narrow, paths, dOf, btns, dots, night, glow, selG, lines, inLabs, cols: colList, cs: G.cs, off: G.off, openSig: null, was: new Map(), nightMin: -1 };
  // 'fancy': the first time the map opens, countries → night → markers fade in (motion brief (e))
  if (first && motion() === 'fancy') {
    mapBox.classList.add('kw-gin');
    setTimeout(() => mapBox.classList.remove('kw-gin'), 1200);
  }
  if (fk) { const b = els.geo.querySelector(`.kw-gb[data-f="${CSS.escape(fk)}"]`); if (b) b.focus({ preventScroll: true }); }
}
function renderGeo(d) {
  const W = els.geo.clientWidth;
  if (!W || GEO.state !== 'ready') return;
  const narrow = W < 560;
  const G = geoGroups(d);
  const sig = [W, narrow, G.cs.map(x => x.c.id + ':' + x.items.map(i => i.key).join(',')).join(';'), G.off.map(i => i.key).join(',')].join('|');
  if (!els.g || els.g.sig !== sig || !els.geo.contains(els.g.night)) buildGeo(d, W, narrow, G, sig);
  const g = els.g;
  g.cs = G.cs; g.off = G.off;
  const selKey = S.detail && S.detail.key;
  const openIds = [];
  for (const x of G.cs) {
    const it = x.rep, col = colorOf(it), open = x.items.some(i => i.status === 'OPEN');
    if (open) openIds.push(x.c.id);
    const sel = !!selKey && x.items.some(i => i.key === selKey);
    const tip = `${x.c.name} · ${it.name} ${pct(it.ratio)}${x.items.length > 1 ? ` 외 ${x.items.length - 1}개` : ''} · ${open ? '장중' : '마감'}`;
    const p = g.paths.get(x.c.id);
    if (p) { p.style.fill = col; p.classList.toggle('open', open); p.classList.toggle('sel', sel); p.firstChild.textContent = tip; }
    const m = g.dots.get(x.c.id);
    if (m) {
      if (m.dot.classList.contains('kw-gmk')) { m.dot.style.fill = col; m.dot.firstChild.textContent = tip; }
      m.dot.classList.toggle('open', open); m.dot.classList.toggle('sel', sel);
      m.pr.classList.toggle('on', open);
      // a market that just opened rings three times first (only seen in 'fancy', where the rings move)
      if (open && g.was.get(x.c.id) === false) { m.pr.classList.add('just'); setTimeout(() => m.pr.classList.remove('just'), 2500); }
    }
    g.was.set(x.c.id, open);
    const aria = `${x.c.name} ${it.name} ${valText(it)}, ${pct(it.ratio)}, ${open ? '장중' : '마감'}${x.items.length > 1 ? `, 지수 ${x.items.length}개` : ''}`;
    const b = g.btns.get(x.c.id);
    if (b) {
      const t = b.querySelector('.t'), pp = b.querySelector('.p'), dot = b.querySelector('.kw-sd');
      if (t) t.textContent = x.c.name;
      pp.textContent = pct(it.ratio);
      if (b.classList.contains('chip')) { pp.className = 'p ' + (it.ratio == null ? 'flat' : cls(it.ratio)); b.style.setProperty('--c', col); }
      if (dot) dot.className = 'kw-sd ' + (open ? 'open' : 'close');
      b.classList.toggle('sel', sel);
      if (b.tagName === 'BUTTON') { b.setAttribute('aria-label', aria); b.title = tip; }
    }
    const c = els.geo.querySelector(`.kw-gc[data-c="${x.c.id}"]`);
    if (c) {
      c.querySelector('.sw').style.background = col;
      c.querySelector('small').textContent = `${shortIdx(x.c, it)}${open ? ' · 장중' : ''}`;
      const pp = c.querySelector('.p'); pp.textContent = pct(it.ratio); pp.className = 'p ' + (it.ratio == null ? 'flat' : cls(it.ratio));
      c.classList.toggle('sel', sel);
      c.setAttribute('aria-label', aria);
    }
  }
  // open markets: a static amber outline + soft glow, redrawn only when the set changes
  const osig = openIds.join(',');
  if (g.openSig !== osig) {
    g.openSig = osig;
    const [gb, gl] = g.glow.children;
    gb.replaceChildren(...openIds.filter(id => g.dOf.has(id)).map(id => svgEl('path', { d: g.dOf.get(id) })));
    gl.replaceChildren(...openIds.filter(id => g.dOf.has(id)).map(id => svgEl('path', { d: g.dOf.get(id), 'data-c': id })));
  }
  syncGeoSel();
  for (const b of els.geo.querySelectorAll('.kw-go')) {
    const it = d.byKey.get(b.dataset.k);
    if (!it) continue;
    const ref = isRef(it), col = ref ? null : colorOf(it), chip = b.querySelector('.kw-pchip');
    chip.textContent = pct(it.ratio);
    chip.className = 'kw-pchip sm' + (ref ? ' ref' : '');
    chip.style.backgroundColor = col || '';
    chip.style.color = col ? inkOn(col) : '';
    b.querySelector('.kw-sd').className = 'kw-sd ' + (it.status === 'OPEN' ? 'open' : 'close');
    b.classList.toggle('sel', selKey === it.key);
    b.setAttribute('aria-label', ariaOf(it));
  }
  placeLabels();
  if (g.nightMin !== Math.floor(Date.now() / 60000)) drawNight();
  schedNight();
  // roving focus over the map's buttons
  const fs = [...els.geo.querySelectorAll('.kw-gb')];
  if (!S.geoFocus || !fs.some(b => b.dataset.f === S.geoFocus)) S.geoFocus = fs.length ? fs[0].dataset.f : null;
  for (const b of fs) b.tabIndex = b.dataset.f === S.geoFocus ? 0 : -1;
  els.geo.setAttribute('aria-label', '해외 지수 세계지도. 나라마다 대표 지수의 등락률로 칠했고, 지금 밤인 쪽은 어둡게 했어요. 화살표로 옮기고 Enter로 자세히 봐요');
  els.geo.setAttribute('role', 'group');
}
// the selected country's outline sits above the night and the borders
function syncGeoSel() {
  const g = els && els.g;
  if (!g) return;
  const key = S.detail && S.detail.key;
  const hit = key ? g.cs.find(x => x.items.some(i => i.key === key)) : null;
  const dd = hit && g.dOf.get(hit.c.id);
  g.selG.replaceChildren(...(dd ? [svgEl('path', { d: dd })] : []));
}
// labels stay inside the map; a callout column moves in as a block so its widest chip fits; labels that would sit on
// each other (or on a chip, or on the side box) are nudged apart along the shorter overlap; then the leader lines
function placeLabels() {
  const g = els.g, W = g.W, H = g.H, GAP = 3;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // reads first (sizes), then the arithmetic, then the writes
  const ins = g.inLabs.map(L => ({ L, w: L.el.offsetWidth, h: L.el.offsetHeight }));
  const cols = g.cols.map(col => ({ col, ws: col.items.map(it => [it.el.offsetWidth, it.el.offsetHeight]) }));
  const offEl = els.geo.querySelector('.kw-gmap > .kw-goff');
  const fixed = [];
  if (offEl) fixed.push({ l: offEl.offsetLeft, t: offEl.offsetTop, r: offEl.offsetLeft + offEl.offsetWidth, b: offEl.offsetTop + offEl.offsetHeight });
  const chipPos = [];
  for (const { col, ws } of cols) {
    const maxW = Math.max(...ws.map(x => x[0]));
    const x = col.end ? Math.max(col.x, maxW + 4) : Math.min(col.x, W - maxW - 4);
    col.items.forEach((it, i) => {
      const [w, hh] = ws[i];
      chipPos.push({ it, x, end: col.end });
      fixed.push({ l: col.end ? x - w : x, r: col.end ? x : x + w, t: it.y - hh / 2, b: it.y + hh / 2 });
    });
  }
  for (const o of ins) { o.x = clamp(o.L.x, o.w / 2 + 3, W - o.w / 2 - 3); o.y = clamp(o.L.y, o.h / 2 + 2, H - o.h / 2 - 2); }
  const box = o => ({ l: o.x - o.w / 2, r: o.x + o.w / 2, t: o.y - o.h / 2, b: o.y + o.h / 2 });
  const over = (a, b) => [Math.min(a.r, b.r) - Math.max(a.l, b.l) + GAP, Math.min(a.b, b.b) - Math.max(a.t, b.t) + GAP];
  for (let pass = 0; pass < 24; pass++) {
    let moved = false;
    for (let i = 0; i < ins.length; i++) {
      const a = ins[i];
      const others = ins.filter((x, j) => j !== i).map(x => ({ o: x, r: box(x) })).concat(fixed.map(r => ({ o: null, r })));
      for (const { o, r } of others) {
        const A = box(a), [ox, oy] = over(A, r);
        if (ox <= GAP || oy <= GAP) continue;
        const share = o ? 0.5 : 1;                         // two labels both give way; a chip or the side box does not move
        const ac = [(A.l + A.r) / 2, (A.t + A.b) / 2], rc = [(r.l + r.r) / 2, (r.t + r.b) / 2];
        if (oy <= ox) { const s = (ac[1] <= rc[1] ? -1 : 1) * oy * share; a.y += s; if (o) o.y -= s; }
        else { const s = (ac[0] <= rc[0] ? -1 : 1) * ox * share; a.x += s; if (o) o.x -= s; }
        for (const z of o ? [a, o] : [a]) { z.x = clamp(z.x, z.w / 2 + 3, W - z.w / 2 - 3); z.y = clamp(z.y, z.h / 2 + 2, H - z.h / 2 - 2); }
        moved = true;
      }
    }
    if (!moved) break;
  }
  for (const o of ins) { o.L.el.style.left = o.x.toFixed(1) + 'px'; o.L.el.style.top = o.y.toFixed(1) + 'px'; }
  const kids = [];
  for (const { it, x, end } of chipPos) {
    it.el.style.left = x.toFixed(1) + 'px';
    it.el.style.top = it.y.toFixed(1) + 'px';
    // marker → elbow → the chip's near edge
    const ex = x + (end ? 1 : -1), elbow = x + (end ? 9 : -9);
    kids.push(svgEl('path', { class: 'kw-gld', d: `M${fx1(it.ax)} ${fx1(it.ay)}L${fx1(elbow)} ${fx1(it.y)}L${fx1(ex)} ${fx1(it.y)}` }));
  }
  g.lines.replaceChildren(...kids);
}
const shortIdx = (c, it) => it.name.startsWith(c.name + ' ') ? it.name.slice(c.name.length + 1) : it.name;
function setGeoFocus(f) {
  S.geoFocus = f;
  for (const b of els.geo.querySelectorAll('.kw-gb')) b.tabIndex = b.dataset.f === f ? 0 : -1;
}
function openCountry(id, opener) {
  const g = els.g;
  const x = g && g.cs.find(c => c.c.id === id);
  if (!x) return;
  openDetail(x.rep.key, opener || g.btns.get(id) || els.geo.querySelector(`.kw-gc[data-c="${id}"]`), x.items.map(i => i.key), x.c.name);
}
function onGeoClick(e) {
  const b = e.target.closest('.kw-gb');
  if (b) { if (b.dataset.c) openCountry(b.dataset.c, b); else if (b.dataset.k) openDetail(b.dataset.k, b, offPeers(b.dataset.k)); return; }
  const p = e.target.closest('.kw-cp.has, .kw-gmk, .kw-gdot');
  if (p) openCountry(p.dataset.c, null);
}
function offPeers(key) {
  const d = S.data[S.kind], it = d && d.byKey.get(key);
  if (!it || !els.g) return null;
  const same = els.g.off.filter(o => o.gkey === it.gkey).map(o => o.key);
  return same.length > 1 ? same : null;
}
// arrows: the nearest button in that direction (by the buttons' boxes); Home / End
function onGeoKey(e) {
  const cur = e.target.closest('.kw-gb');
  if (!cur) return;
  const fs = [...els.geo.querySelectorAll('.kw-gb')].filter(b => b.getClientRects().length);
  let next = null;
  if (e.key === 'Home') next = fs[0];
  else if (e.key === 'End') next = fs[fs.length - 1];
  else if (/^Arrow/.test(e.key)) {
    const a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
    let best = Infinity;
    for (const b of fs) {
      if (b === cur) continue;
      const r = b.getBoundingClientRect(), bx = r.left + r.width / 2, by = r.top + r.height / 2;
      const dx = bx - ax, dy = by - ay;
      const main = e.key === 'ArrowRight' ? dx : e.key === 'ArrowLeft' ? -dx : e.key === 'ArrowDown' ? dy : -dy;
      const cross = e.key === 'ArrowRight' || e.key === 'ArrowLeft' ? Math.abs(dy) : Math.abs(dx);
      if (main <= 2) continue;
      const sc = main + cross * 2.2;
      if (sc < best) { best = sc; next = b; }
    }
  } else return;
  e.preventDefault();
  if (next) { setGeoFocus(next.dataset.f); next.focus(); }
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
    if (!S.detail || sheet.contains(e.target) || e.target.closest('.kw-tile,.kw-row,.kw-lr,.kw-gb,.kw-cp.has,.kw-gmk,.kw-gdot')) return;
    if (!narrowMQ.matches) closeDetail(false);
  }, true);
  addEventListener('resize', () => { if (S.detail && S.detail.chart) drawChart(); });
}
// peers: the other indices of the same country (world map) — a switcher at the top of the sheet; place: its title
function openDetail(key, opener, peers, place) {
  const d = S.data[S.kind];
  if (!d || !d.byKey.has(key)) return;
  ensureSheet();
  const same = S.detail && S.detail.key === key;
  peers = peers && peers.length > 1 && peers.includes(key) ? peers : null;
  S.detail = { key, kind: S.kind, opener: opener || null, tf: same ? S.detail.tf : '3m', chart: null, peers, place: peers ? place || null : null };
  markSel(key);
  fillDetail(true);
  sheet.hidden = false;
  sheet.classList.toggle('kw-noanim', calm());
  if (narrowMQ.matches) scrim.classList.add('open');
  sheet.scrollTop = 0;
  sheet.focus({ preventScroll: true });
  loadChart();
}
function markSel(key) {
  for (const [k, el] of els.tiles) el.classList.toggle('sel', k === key);
  for (const [k, el] of els.rows) el.classList.toggle('sel', k === key);
  if (els.g) {
    const hit = key ? els.g.cs.find(x => x.items.some(i => i.key === key)) : null;
    for (const el of els.geo.querySelectorAll('.kw-cp.has, .kw-gmk, .kw-gdot, .kw-gl, .kw-gc')) el.classList.toggle('sel', !!hit && el.dataset.c === hit.c.id);
    for (const el of els.geo.querySelectorAll('.kw-go')) el.classList.toggle('sel', el.dataset.k === key);
    syncGeoSel();
  }
}
function closeDetail(restore) {
  if (!S.detail || !sheet) return;
  const { key, opener } = S.detail;
  S.detail = null;
  sheet.hidden = true;
  scrim.classList.remove('open');
  if (els && els.tiles) markSel(null);
  if (!restore || !S.shown) return;
  // back to the opener; if it is gone or hidden (the view changed meanwhile), to the same item in what is shown now
  const visible = el => el && el.isConnected && el.getClientRects().length > 0;
  let target = visible(opener) ? opener : null;
  if (!target && opener && opener.classList.contains('kw-row')) target = els.rank.querySelector(`.kw-row[data-k="${CSS.escape(key)}"]`);
  if (!visible(target) && S.mode === 'geo' && els.g) {
    const hit = els.g.cs.find(x => x.items.some(i => i.key === key));
    const cand = hit ? els.geo.querySelector(`.kw-gb[data-c="${hit.c.id}"]`) : els.geo.querySelector(`.kw-gb[data-k="${CSS.escape(key)}"]`);
    if (visible(cand)) target = cand;
  }
  if (!visible(target)) target = S.mode === 'list' && visible(els.rows.get(key)) ? els.rows.get(key) : visible(els.tiles.get(key)) ? els.tiles.get(key) : null;
  if (target) {
    if (target.classList.contains('kw-tile')) setRoving(key);
    if (target.classList.contains('kw-lr')) setListFocus(key);
    if (target.classList.contains('kw-gb')) setGeoFocus(target.dataset.f);
    target.focus({ preventScroll: false });
  }
}
function switchPeer(k) {
  const D = S.detail;
  if (!D || !D.peers || D.key === k) return;
  openDetail(k, D.opener, D.peers, D.place);
  const b = sheet.querySelector(`.kw-peers button[data-k="${CSS.escape(k)}"]`);
  if (b) b.focus({ preventScroll: true });
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
  // a country with several indices: one button each, the shown one pressed
  const peers = D.peers ? h('div', { class: 'kw-peers', role: 'group', 'aria-label': `${D.place || ''} 지수`.trim() },
    D.place ? h('b', { class: 'kw-peers-h', text: D.place }) : null,
    D.peers.map(k => { const p = d.byKey.get(k); return p ? h('button', { type: 'button', 'data-k': k, 'aria-pressed': String(k === D.key), onclick: () => switchPeer(k) },
      h('span', { class: 'n', text: p.name }), h('span', { class: 'v ' + (isRef(p) || p.ratio == null ? 'flat' : cls(p.ratio)), text: pct(p.ratio) })) : null; })) : null;
  if (full || !sheet.firstChild) {
    const chartBox = h('div', { class: 'kw-chart' });
    put(sheet,   // put(): peers is null for 원자재 — native replaceChildren would print "null"
      h('div', { class: 'kw-grab', 'aria-hidden': 'true' }),
      h('button', { type: 'button', class: 'kw-x', 'aria-label': '닫기', onclick: () => closeDetail(true) }, '×'),
      peers, head, chartBox,
      h('p', { class: 'kw-dsrc', text: `출처: 네이버 증권 · ${delayText(it)} 시세` }));
    sheet.classList.toggle('has-peers', !!peers);
  } else {
    const old = $('.kw-peers', sheet);
    if (old && peers) { const f = old.contains(document.activeElement) ? document.activeElement.dataset.k : null; sheet.replaceChild(peers, old); if (f) { const b = peers.querySelector(`button[data-k="${CSS.escape(f)}"]`); if (b) b.focus({ preventScroll: true }); } }
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
  root.classList.toggle('kw-paused', document.hidden || !!S.offscreen);
  if (document.hidden) { clearTimeout(S.timer); S.timer = 0; S.seq++; S.busy = null; if (S.ac) S.ac.abort(); clearTimeout(nightT); nightT = 0; return; }
  if (S.mode === 'geo') { drawNight(); schedNight(); }
  const age = Date.now() - (S.at[S.kind] || 0);
  if (!S.data[S.kind] || age >= POLL_MS) load(S.kind); else schedule(POLL_MS - age);
});
// the clock in the header refreshes everything at once (AGENTS §3-6): fetch now, keep view, scroll and focus
document.addEventListener('kh:refresh', () => { if (S.shown && LIVE && !document.hidden) load(S.kind); });
document.addEventListener('kh:motion', () => { if (S.shown && els && !els.snap) syncMotion(); });
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
  if (!sameKind) {
    closeDetail(false); S.kind = kind; S.focusKey = null; S.listFocus = null;
    if (els.tiles) { for (const el of els.tiles.values()) el.remove(); for (const el of els.heads.values()) el.remove(); els.tiles.clear(); els.heads.clear(); }
    if (els.rows) { els.list.replaceChildren(); els.rows.clear(); els.listSig = ''; }
  }
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
  clearTimeout(nightT); nightT = 0;
  S.seq++; S.busy = null;
  if (S.ac) S.ac.abort();
  closeDetail(false);
}
// the tile map in map pixels (same shape as KH.layout(), for "이미지로 저장"). In the list view it is the map the 지도
// view draws at this width, laid out off screen: the saved picture is a map either way (extras says "지도를 저장했어요").
function headSub(g) {
  const avg = avgOf(g.g.items);
  const vt = avg == null ? '' : pct(avg);
  return vt && g.w - tw(g.g.name, 700) * 12 - 16 >= tw(vt, 600) * 12 + 4 ? vt : '';
}
function layout() {
  if (!S.shown || !els || els.snap) return [];
  const d = S.data[S.kind];
  if (!d || !d.all.length) return [];
  const out = [];
  if (S.view === 'map' && els.boxes && !els.map.hidden) {
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
  const W = Math.round((els.list.clientWidth || els.map.clientWidth || root.clientWidth || 0));
  if (!W) return [];
  const Lo = computeLayout(d, W, Math.max(480, Math.min(760, Math.round(W * 0.6))));
  for (const g of Lo.heads) out.push({ kind: 'sector', x: g.x, y: g.y, w: g.w, h: g.h, color: '#000', label: g.hd ? g.g.name : '', sub: g.hd ? headSub(g) : '', hd: g.hd });
  for (const t of Lo.tiles) {
    const L = fit(tileTexts(t.it, t.g), t.w, t.h);
    out.push({ kind: 'tile', x: t.x, y: t.y, w: t.w, h: t.h, color: colorOf(t.it), label: t.it.name, sub: L && L.lv >= 2 ? pct(t.it.ratio) : '', code: t.it.key });
  }
  return out;
}
window.KHWorld = { show, hide, layout, shown: () => S.shown ? S.kind : null, view: () => S.view };

// the template may have tried show() before this script existed (page opened at #world / #cmdty): start now
try {
  const m = typeof KH.market === 'function' ? KH.market() : null;
  const w = document.getElementById('world');
  if ((m === 'world' || m === 'cmdty') && w && !w.hidden) show(m === 'cmdty' ? 'commodity' : 'index');
} catch (e) { /* the template will call show() itself */ }
})();
