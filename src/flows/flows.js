/* 투자자별 순매수 카드 (AGENTS §3-40 계약 · 화면, 사용자 2026-11-16 15:25 "순매수 순매도 순위 만들건데" → 15:31 "나랑 가족만 볼수있도록").
   자리: 옆 칸 눈에 띄는 종목 카드 바로 다음(PC · 태블릿 · 휴대폰 모두 같은 순서) — 지도는 움직이지 않아요.
   머리: 시장 전체 3주체(/api/flows/market, 네이버 dealTrendInfo, 억원) — 지금 탭 시장(코스피 K · 코스닥 Q, 그 밖 탭은 둘 다), "HH:MM 기준",
     지난 값이면 ! (--fail-dot). 장중 · 카드가 화면 근처면 60초, 그 밖 10분마다.
   고르기: [외국인 · 기관 · 개인] × [순매수 · 순매도] (템플릿 .movers-tabs 세그먼트 — 표시는 KH.ui.seg), 목록 10줄 + 더보기 30줄(펼치는 목록,
     design.md §7 — 목록 상자만 `open`으로 자라고 아래는 한 번에, 새 줄은 25 % 뒤 §6-4로, 접을 땐 새 줄이 먼저 나가고 `close`).
   줄: 순위 · 오늘 캔들(KH.candleIcon(KH.ohlc)) · 이름(누르면 눈에 띄는 종목 카드와 같은 곳 — 종목 페이지, 없으면 빠른 보기) · 금액(억원 · 조,
     등락색) · 작은 등락률.
   원천: 모두에게 = flows.json 1일 칸([0] 외국인 · [1] 기관 · [2] 개인, 확정 — "M/D 확정"), 시장은 KH.stock(c).m 또는 names.json.
     초대 토큰이 있는 기기(KH.inv.has()) + KH.flowsLive.data().slot이 있고 flows.json asOf가 오늘이 아니면: 외국인 · 기관 = 오늘 잠정(rank,
     전체 · 그 밖 탭은 코스피 + 코스닥을 합쳐 다시 정렬), 개인은 확정 + "개인은 장 마감 뒤 저녁에 확정돼요". 잠정 자료는 카드가 화면 근처에
     올 때만 KH.flowsLive.want('card', true). 공개 기기엔 그 흔적이 없어요(글자 · 출처 줄 · 요청 모두).
   KH.inv · KH.flowsLive가 없는 템플릿(옛 빌드)이면 공개 기기처럼. 스냅샷(dist/)은 내장 flows.json 목록 + 시장 전체 줄은 실시간 버전 안내.
   window.KHFlows = {state(), market(maxAge?) → Promise<시장 전체 상태>, marketState(), render(), refresh()} — 요약 카드가 같은 시장 전체 값을
     따로 받지 않게 market()을 같이 써요. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function' || window.KHFlows) return;

const h = KH.h, UI = KH.ui || {};
const LIVE = KH.MODE === 'live';
const MINUS = '−';
const TOP = 10, MAX = 30;
const WHO = [['f', '외국인'], ['i', '기관'], ['p', '개인']], WHO_IX = { f: 0, i: 1, p: 2 }, WHO_NAME = Object.fromEntries(WHO);
const DIR = [['buy', '순매수'], ['sell', '순매도']];
const MKT = { K: '코스피', Q: '코스닥' };
const NF0 = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NF2 = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const put = (el, ...kids) => { el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false && k !== '')); return el; };
const sg = v => (v > 0 ? '+' : v < 0 ? MINUS : '');
const cls = v => (v > 0 ? 'up' : v < 0 ? 'dn' : 'flat');
// 억원 → "+1,234억" · "−1.2조" · 10억 아래는 소수 한 자리("+3.4억")
const eokAbs = a => (a >= 10000 ? NF1.format(a / 10000) + '조' : a >= 10 ? NF0.format(Math.round(a)) + '억' : NF1.format(a) + '억');
const amt = v => { const a = Math.abs(+v || 0); return (a < 0.05 ? '' : sg(v)) + eokAbs(a); };
const pctText = v => { const r = +(+v).toFixed(2); return sg(r) + NF2.format(Math.abs(r)) + '%'; };
const pad = n => String(n).padStart(2, '0');
const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
const kstOf = ms => { const k = new Date(ms + 9 * 3600e3); return { dow: k.getUTCDay(), hm: k.getUTCHours() * 100 + k.getUTCMinutes(), hhmm: `${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`, day: `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}` }; };
const DOW = '일월화수목금토';
const md = ymd => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(ymd || ''); return m ? `${+m[2]}/${+m[3]}` : ''; };
const mdw = ymd => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(ymd || ''); if (!m) return ''; const w = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay(); return `${+m[2]}/${+m[3]} (${DOW[w]})`; };
const today = () => kstOf(nowMs()).day;
const motion = () => (typeof KH.motion === 'function' ? KH.motion() : 'standard');
const store = {
  get(k, d) { try { const v = localStorage.getItem('khm.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('khm.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};

/* ───────── 장 · 탭 ───────── */
// 정규장 중: 시세가 OPEN이거나, 평일 09:00~15:30이고 시세가 오늘 것(휴장일이 아님)
function inSession() {
  const st = typeof KH.marketStatus === 'function' ? KH.marketStatus() || {} : {};
  if (st.KOSPI === 'OPEN' || st.KOSDAQ === 'OPEN') return true;
  const n = kstOf(nowMs());
  if (n.dow === 0 || n.dow === 6 || n.hm < 900 || n.hm >= 1530) return false;
  const a = Date.parse(KH.asOf() || '');
  return isFinite(a) && kstOf(a).day === n.day;
}
// 코스피 탭 → K, 코스닥 탭 → Q, 그 밖(전체 · 테마 · 관심) → 둘 다
const scope = () => { const m = typeof KH.market === 'function' ? KH.market() : 'ALL'; return m === 'K' || m === 'Q' ? m : 'KQ'; };

/* ───────── 가족(초대 토큰이 있는 기기) — 템플릿 KH.inv · KH.flowsLive, 없으면 공개 기기처럼 ───────── */
const inv = () => (LIVE && KH.inv && typeof KH.inv.has === 'function' ? KH.inv : null);
const fam = () => { try { const I = inv(); return !!(I && I.has()); } catch (e) { return false; } };
const liveApi = () => (fam() && KH.flowsLive && typeof KH.flowsLive.data === 'function' ? KH.flowsLive : null);
// 오늘 잠정을 보여 줄 수 있으면 그 자료(slot이 있고 오늘 것), 아니면 null. flows.json이 오늘 것이 되면 잠정을 그만 써요
function livePayload() {
  const L = liveApi();
  if (!L) return null;
  let p = null;
  try { p = L.data(); } catch (e) { p = null; }
  if (!p || p.closed || !p.slot || !p.rank || typeof p.rank !== 'object') return null;   // closed: 휴장일 — 잠정 없음
  const t = today();
  if (p.date && p.date !== t) return null;
  if (S.file && S.file.asOf === t) return null;
  return p;
}

/* ───────── 상태 ───────── */
const S = {
  who: WHO_IX[store.get('flowsWho', 'f')] != null ? store.get('flowsWho', 'f') : 'f',
  dir: store.get('flowsDir', 'buy') === 'sell' ? 'sell' : 'buy',
  more: false,                       // 더보기 (이 페이지에서만)
  file: null, fileFail: false, fileAt: 0,
  names: null, namesDone: !LIVE,     // Map code → [name, 'K'|'Q'] (names.json); done = tried (a failed load: the streamed rows' markets only)
  near: !('IntersectionObserver' in window),
  wanted: false,
};
// 시장 전체 (요약 카드도 같이 써요): j = 마지막 응답, at = 받은 때(Date.now), fail = 마지막 시도 실패, gone = 404(그 경로가 없는 옛 Worker)
const MK = { j: null, at: 0, fail: false, gone: false, busy: null, tries: 0, hold: false };

async function getJSON(url, wait = 9000) {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), wait);
  try {
    const r = await fetch(url, { signal: ac.signal });
    let body = null;
    try { body = await r.json(); } catch (e) { body = null; }
    return { status: r.status, ok: r.ok, body };
  } finally { clearTimeout(t); }
}
function marketTtl() { return MK.gone ? 600e3 : MK.fail ? 60e3 : inSession() && S.near ? 60e3 : 600e3; }
// maxAge(ms) 안에 받은 값이 있으면 그대로, 아니면 새로 받아요(같은 때 둘이 물으면 한 번만)
function market(maxAge) {
  if (!LIVE) return Promise.resolve(marketState());
  const age = maxAge == null ? marketTtl() : maxAge;
  if (MK.busy) return MK.busy;
  if (MK.at && Date.now() - MK.at < age) return Promise.resolve(marketState());
  MK.busy = (async () => {
    try {
      const r = await getJSON('api/flows/market');
      if (r.status === 404) { MK.gone = true; MK.fail = false; MK.j = null; }
      else if (r.ok && r.body && typeof r.body === 'object' && (r.body.K || r.body.Q)) { MK.j = r.body; MK.fail = false; MK.gone = false; }
      else MK.fail = true;
    } catch (e) { MK.fail = true; }
    MK.at = Date.now(); MK.busy = null; MK.tries++;
    soon();
    document.dispatchEvent(new CustomEvent('kh:flowsmarket', { detail: marketState() }));
    return marketState();
  })();
  return MK.busy;
}
// 장 시작 전엔 그날 date로 0 · 0 · 0이 와요(실측 11/23 08:45) — 0억이 아니라 "아직 집계 전"
const marketZero = (j, ms) => ms.every(m => !j[m] || ['personal', 'foreign', 'institutional'].every(k => !(+j[m][k])));
const marketState = () => ({ zero: !!(MK.j && marketZero(MK.j, ['K', 'Q'])), j: MK.j, at: MK.at, fail: MK.fail, gone: MK.gone, stale: !!(MK.j && MK.j.stale) || (MK.fail && !!MK.j), tried: MK.tries > 0 || !LIVE });

async function loadFile(force) {
  if (S.file && !force) return S.file;
  let j = null;
  if (force && LIVE) {             // 저녁 21:30 작업 뒤 새 파일(KH.loadData는 한 번 읽으면 기억해요)
    try { const r = await getJSON('data/flows.json?t=' + Math.floor(Date.now() / 600e3)); j = r.ok ? r.body : null; } catch (e) { j = null; }
  } else j = await KH.loadData('flows');
  if (j && j.f && typeof j.f === 'object') { S.file = j; S.fileFail = false; RANK.clear(); }
  else if (!S.file) S.fileFail = true;
  S.fileAt = Date.now();
  soon();
  return S.file;
}
async function loadNames() {
  if (S.names || !LIVE) return S.names;
  const j = await KH.loadData('names');
  if (j && j.n) S.names = new Map(Object.entries(j.n));
  S.namesDone = true; RANK.clear(); soon();
  return S.names;
}
const mktOf = c => { const s = KH.stock(c); if (s && (s.m === 'K' || s.m === 'Q')) return s.m; const x = S.names && S.names.get(c); return x ? x[1] : null; };
const nameOf = c => { const s = KH.stock(c); return (s && s.n) || (S.names && S.names.get(c) && S.names.get(c)[0]) || c; };

/* ───────── 순위 ───────── */
// 확정(flows.json): 시장 · 주체 · 방향마다 한 번만 정렬해 둬요(파일 · 이름표가 바뀌면 다시)
const RANK = new Map();
function fileRows(sc, who, dir) {
  const F = S.file;
  if (!F || (sc !== 'KQ' && !S.namesDone)) return null;   // a market's list waits for names.json (codes outside the stream)
  const key = `${sc}|${who}|${dir}`;
  if (RANK.has(key)) return RANK.get(key);
  const ix = WHO_IX[who], stale = F.stale || {}, out = [];
  for (const c in F.f) {
    const v = F.f[c];
    if (!Array.isArray(v) || stale[c] || v[ix] == null || !isFinite(+v[ix])) continue;
    const a = +v[ix];
    if (dir === 'buy' ? !(a > 0) : !(a < 0)) continue;
    if (sc !== 'KQ') { const m = mktOf(c); if (m !== sc) continue; }
    out.push({ c, a });
  }
  out.sort((x, y) => (dir === 'buy' ? y.a - x.a : x.a - y.a) || (x.c < y.c ? -1 : x.c > y.c ? 1 : 0));   // same amount: by code (fixed order)
  const top = out.slice(0, MAX);
  RANK.set(key, top);
  return top;
}
// 잠정(rank): 행 = [코드, 이름, 금액(억원), 수량, 현재가, 등락률]. 순매도 목록은 늘 −, 순매수는 늘 +(방향은 목록이 정해요)
function liveRows(p, sc, who, dir) {
  const ms = sc === 'KQ' ? ['K', 'Q'] : [sc], out = [];
  for (const m of ms) {
    const L = p.rank[m] && p.rank[m][who] && p.rank[m][who][dir];
    if (!Array.isArray(L)) continue;
    for (const r of L) {
      if (!Array.isArray(r) || !/^[0-9A-Z]{6}$/.test(String(r[0])) || !isFinite(+r[2])) continue;
      const a = Math.abs(+r[2]) * (dir === 'buy' ? 1 : -1);
      out.push({ c: String(r[0]), n: r[1] ? String(r[1]) : null, a, r: isFinite(+r[5]) && r[5] !== null && r[5] !== '' ? +r[5] : null, m });
    }
  }
  out.sort((x, y) => (dir === 'buy' ? y.a - x.a : x.a - y.a) || (x.c < y.c ? -1 : x.c > y.c ? 1 : 0));   // same amount: by code (fixed order)
  return out.slice(0, MAX);
}
// 지금 보여 줄 것: {src:'file'|'live', rows, p?, note?}
function pick() {
  const sc = scope(), p = S.who === 'p' ? null : livePayload();
  if (p) {
    const rows = liveRows(p, sc, S.who, S.dir);
    if (rows.length) return { src: 'live', rows, p, sc };
    // 기관 첫 입력(10:00) 전처럼 그 주체 · 방향 잠정이 아직 없으면 확정 목록 + 짧은 말(가족 기기에만)
    return { src: 'file', rows: fileRows(sc, S.who, S.dir), sc, note: `${WHO_NAME[S.who]} 잠정은 다음 입력분부터 보여요` };
  }
  const out = { src: 'file', rows: fileRows(sc, S.who, S.dir), sc };
  if (S.who === 'p' && livePayload()) out.note = '개인은 장 마감 뒤 저녁에 확정돼요';
  return out;
}

/* ───────── 그리기 ───────── */
let host = null, P = null;
const ICON_WARN = () => (typeof UI.icon === 'function' ? UI.icon('warn') : h('span', { class: 'fl-bang', 'aria-hidden': 'true', text: '!' }));
function segOf(label, items, cur, on) {
  const seg = h('div', { class: 'movers-tabs fl-seg', role: 'group', 'aria-label': label },
    items.map(([v, t]) => h('button', { type: 'button', 'data-v': v, 'aria-pressed': String(v === cur), text: t })));
  seg.addEventListener('click', e => { const b = e.target.closest('button[data-v]'); if (b && seg.contains(b)) on(b.dataset.v); });
  return seg;
}
function mount() {
  host = h('section', { class: 'card flows', id: 'flowsCard', 'aria-labelledby': 'fl-h' });
  const scopeEl = h('small', { class: 'fl-scope' });
  const mkt = h('div', { class: 'fl-mkt' });
  const who = segOf('투자자', WHO, S.who, v => { if (v === S.who) return; S.who = v; store.set('flowsWho', v); render(true); });
  const dir = segOf('순매수 · 순매도', DIR, S.dir, v => { if (v === S.dir) return; S.dir = v; store.set('flowsDir', v); render(true); });
  const lab = h('p', { class: 'fl-lab' });
  const list = h('div', { class: 'fl-list', role: 'list', 'aria-labelledby': 'fl-h' });
  const moreT = h('span', { class: 'fl-mt' });
  const more = h('button', { type: 'button', class: 'fl-more', 'aria-expanded': 'false', hidden: true }, moreT);
  more.addEventListener('click', () => toggleMore());
  const note = h('p', { class: 'fl-note', hidden: true });
  put(host, h('h2', null, h('span', { id: 'fl-h', text: '투자자별 순매수' }), ' ', scopeEl), mkt, h('div', { class: 'fl-ctl' }, who, dir), lab, list, more, note);
  P = { scopeEl, mkt, who, dir, lab, list, more, moreT, note };
  place();
  if (typeof UI.seg === 'function') { UI.seg(who); UI.seg(dir); }
}
// 옆 칸의 눈에 띄는 종목 카드 바로 다음(휴대폰도 옆 칸 안이라 같은 순서). 그 카드가 없는 옛 템플릿이면 옆 칸 끝
function place() {
  const mv = document.getElementById('moverCard'), side = document.querySelector('main.layout > .side');
  if (mv && mv.parentNode) { if (mv.nextElementSibling !== host) mv.after(host); }
  else if (side && host.parentNode !== side) side.append(host);
}

// 시장 전체 줄: 표 하나(열 = 외국인 · 기관 · 개인, 줄 = 그 탭의 시장), 머리 오른쪽 "HH:MM 기준"
function drawMarket() {
  const box = P.mkt;
  if (MK.hold) return;                                  // 다시 시도 키가 받는 중 · 받았어요를 보이는 동안은 그대로
  if (!LIVE) {
    put(box, h('p', { class: 'fl-wait' }, '시장 전체 수급은 ', h('a', { href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '실시간 버전' }), '에서 볼 수 있어요'));
    box.hidden = false; return;
  }
  const M = marketState();
  if (M.gone) { box.hidden = true; box.replaceChildren(); return; }   // 그 경로가 없는 옛 Worker: 줄 없이 목록만
  box.hidden = false;
  const sc = scope(), ms = sc === 'KQ' ? ['K', 'Q'] : [sc];
  const j = M.j;
  if (!j) {
    if (M.fail) put(box, h('p', { class: 'fl-fail', role: 'status' }, ICON_WARN(), h('span', { text: '시장 전체 수급을 불러오지 못했어요' }), retryKey()));
    else put(box, h('p', { class: 'fl-wait', role: 'status', text: '시장 전체 수급을 받는 중…' }));
    return;
  }
  const a = Date.parse(j.asOf || ''), k = isFinite(a) ? kstOf(a) : null;
  const when = j.date && j.date !== today() ? `${mdw(j.date)} 기준` : k ? `${k.hhmm} 기준` : '';
  const stale = M.stale;
  if (marketZero(j, ms)) {
    put(box, h('p', { class: 'fl-mh' }, h('span', { text: '시장 전체' })), h('p', { class: 'fl-wait', role: 'status', text: '아직 집계 전이에요 · 장이 열리면 들어와요' }));
    return;
  }
  const head = h('p', { class: 'fl-mh' }, h('span', { text: '시장 전체' }),
    h('span', { class: 'fl-at' + (stale ? ' stale' : ''), title: stale ? '새 값을 받지 못해 지난 값을 보여 줘요' : '네이버 증권 · 장중엔 그때까지 합한 값이에요' },
      stale ? ICON_WARN() : null, h('span', { text: when }), stale ? h('span', { class: 'sr', text: ' · 새 값을 받지 못했어요' }) : null));
  const rows = ms.map(m => {
    const x = j[m];
    const cell = key => { const v = x && isFinite(+x[key]) && x[key] !== null ? +x[key] : null; return h('td', { class: 'fl-v ' + (v == null ? 'flat' : cls(v)), text: v == null ? '—' : amt(v) }); };
    return h('tr', null, h('th', { scope: 'row', text: MKT[m] }), cell('foreign'), cell('institutional'), cell('personal'));
  });
  put(box, head, h('table', { class: 'fl-mt' }, h('caption', { class: 'sr', text: '시장 전체 투자자별 순매수 (억원)' }),
    h('thead', null, h('tr', null, h('td'), ...WHO.map(([, t]) => h('th', { scope: 'col', text: t })))), h('tbody', null, rows)));
}
function retryKey() {
  if (typeof UI.retry !== 'function') return null;
  return UI.retry({ cls: 'fl-rk', run: async () => { const s = await market(0); return s.j && !s.fail ? true : false; },
    onStart: () => { MK.hold = true; }, onFail: () => { MK.hold = false; }, render: () => { MK.hold = false; drawMarket(); },
    alive: () => { const ok = !!host && host.isConnected; if (!ok) MK.hold = false; return ok; } });
}

// 목록 머리 줄: 확정 "11/20 (금) 확정" · 잠정 "잠정 · 14:30 입력분" + 작은 출처
function drawLabel(pk) {
  const F = S.file, sc = pk.sc;
  const where = sc === 'KQ' ? '코스피 · 코스닥' : MKT[sc];
  if (pk.src === 'live') {
    put(P.lab, h('span', { class: 'fl-tag', text: `잠정 · ${pk.p.slot} 입력분` }), h('small', { class: 'fl-src', text: '한국투자증권 가집계' }));
    P.lab.title = `${where} · ${WHO_NAME[S.who]} ${S.dir === 'buy' ? '순매수' : '순매도'} 상위 · 입력 시각까지 누적한 잠정치예요` + (pk.p.at ? ` · ${pk.p.at}에 받았어요` : '');
    return;
  }
  put(P.lab, F && F.asOf ? h('span', { class: 'fl-tag', text: `${mdw(F.asOf)} 확정` }) : null, h('small', { class: 'fl-src', text: '금액 = 순매수 주식 수 × 그날 종가' }));
  P.lab.title = F && F.asOf ? `${where} · 네이버 증권 · 매일 장 마감 뒤 저녁에 받아요` : '';
}
const pctOf = (c, fallback) => {
  let q = null;
  try { q = typeof KH.quote === 'function' ? KH.quote(c) : null; } catch (e) { q = null; }
  if (q && isFinite(+q.r) && +q.p > 0) return +q.r;
  const s = KH.stock(c);
  if (s && isFinite(+s.r) && +s.p > 0) return +s.r;
  return fallback == null ? null : fallback;
};
function openStock(c, btn) {
  if (typeof KH.openStock === 'function' && KH.openStock(c, { opener: btn })) return;   // 눈에 띄는 종목 카드와 같은 곳(종목 페이지)
  if (typeof KH.quick === 'function') KH.quick(c, btn);
}
function rowEl(x, i) {
  const n = x.n || nameOf(x.c), r = pctOf(x.c, x.r);
  let o = null;
  try { o = typeof KH.ohlc === 'function' ? KH.ohlc(x.c) : null; } catch (e) { o = null; }
  const icon = typeof KH.candleIcon === 'function' ? KH.candleIcon(o) : h('span', { class: 'cdi none' });
  const label = `${i + 1}위 ${n}, ${WHO_NAME[S.who]} ${S.dir === 'buy' ? '순매수' : '순매도'} ${amt(x.a)}원` + (r == null ? '' : `, 등락률 ${pctText(r)}`) + ' · 종목 페이지';
  // 목록 항목은 감싸는 div(role="listitem") — 버튼에 listitem을 주면 버튼이라는 역할이 사라져요
  const b = h('button', { type: 'button', class: 'fl-r', 'data-c': x.c, 'aria-label': label },
    h('span', { class: 'fl-rk', 'aria-hidden': 'true', text: String(i + 1) }), icon, h('span', { class: 'nm', text: n }),
    h('b', { class: 'fl-a ' + cls(x.a), text: amt(x.a) }),
    h('small', { class: 'fl-p ' + (r == null ? 'flat' : cls(+r.toFixed(2))), text: r == null ? '—' : pctText(r) }));
  b.addEventListener('click', () => openStock(x.c, b));
  return h('div', { class: 'fl-li' + (i >= TOP ? ' fl-x' : ''), role: 'listitem' }, b);
}
let lastSig = '';
function drawList(pk, force) {
  const rows = pk.rows;
  const wait = rows == null;
  if (wait) {
    const failed = S.fileFail;
    put(P.list, h('p', { class: failed ? 'fl-fail' : 'fl-wait', role: 'status' }, failed ? ICON_WARN() : null,
      h('span', { text: failed ? '종목별 수급 자료를 불러오지 못했어요 · 잠시 뒤 다시 받아요' : '종목별 수급을 받는 중…' })));
    P.more.hidden = true; lastSig = ''; return;
  }
  if (!rows.length) {
    put(P.list, h('p', { class: 'fl-wait', role: 'status', text: `${WHO_NAME[S.who]} ${S.dir === 'buy' ? '순매수' : '순매도'} 종목이 없어요.` }));
    P.more.hidden = true; lastSig = ''; return;
  }
  const n = S.more ? Math.min(MAX, rows.length) : Math.min(TOP, rows.length);
  const shown = rows.slice(0, n);
  // 같은 줄(종목 · 금액 · 등락률 · 캔들)이면 다시 만들지 않아요 — 포커스 · 누르는 중인 줄이 그대로
  const sig = shown.map(x => `${x.c}:${x.a}:${pctOf(x.c, x.r)}:${JSON.stringify(typeof KH.ohlc === 'function' ? KH.ohlc(x.c) : null)}`).join('|') + `|${S.who}${S.dir}`;
  if (force || sig !== lastSig) {
    const fc = document.activeElement && P.list.contains(document.activeElement) ? document.activeElement.dataset.c : null;
    put(P.list, shown.map(rowEl));
    if (fc) { const b = P.list.querySelector(`[data-c="${fc}"]`); if (b) b.focus({ preventScroll: true }); }
    lastSig = sig;
  }
  const total = Math.min(MAX, rows.length);
  P.more.hidden = total <= TOP;
  const txt = S.more ? '접기' : `더보기 (${total}개)`;
  P.more.setAttribute('aria-expanded', String(S.more));
  if (P.moreT.textContent !== txt) P.moreT.textContent = txt;
}
function drawNote(pk) {
  const t = pk.note || '';
  if (P.note.textContent !== t) P.note.textContent = t;
  P.note.hidden = !t;
}
let renderT = 0;
function render(force) {
  if (!P) return;
  clearTimeout(renderT); renderT = 0;
  if (FOLD.run) { FOLD.pending = true; return; }
  const sc = scope();
  P.scopeEl.textContent = sc === 'KQ' ? '코스피 · 코스닥' : MKT[sc];
  for (const [seg, cur] of [[P.who, S.who], [P.dir, S.dir]]) for (const b of seg.children) b.setAttribute('aria-pressed', String(b.dataset.v === cur));
  drawMarket();
  const pk = pick();
  host.dataset.src = pk.src;
  drawLabel(pk);
  drawList(pk, force);
  drawNote(pk);
  footer(pk);
}
// 시세 · 탭이 바뀌는 대로 자주 오는 이벤트는 한 프레임에 한 번
function soon() { if (!renderT) renderT = setTimeout(() => { renderT = 0; render(false); }, 60); }

/* ───────── 더보기 · 접기 = 펼치는 목록 (design.md §7 · news.js fold · 종목 페이지 foldMove와 같은 규칙) ─────────
   펼칠 때: 레이아웃은 누르는 순간 한 번에 새 높이(아래 내용이 한 번만 움직여요), 목록 상자는 옛 높이로 잘린 채 `open`으로 열리고, 새 줄
   (.fl-x)은 상자가 25 % 열린 뒤 함께 §6-4로 들어와요. 접을 때: 새 줄이 먼저 함께 나가고(100ms) 상자가 높이를 지킨 채 `close`로 닫힌 뒤
   레이아웃이 한 번에 올라와요. 줄이기 · 숨은 페이지 · 스프링 엔진 없음 = 끝 상태 바로. 순차 등장 없음(자주 여는 것, §6-2). */
const FOLD = { run: null, pending: false };
const TX_OUT = 100, BLEED = 8;
const clipTo = b => `inset(-${BLEED}px -${BLEED}px ${Math.max(0, b).toFixed(1)}px -${BLEED}px)`;
function fold(box, want, apply, onEnd) {
  if (FOLD.run) FOLD.run.finish();
  const ok = KH.spring && typeof KH.spring.animate === 'function' && motion() !== 'reduced' && !document.hidden && box.isConnected && box.getClientRects().length > 0;
  if (!ok) { apply(want); if (onEnd) onEnd(); return; }
  const me = { done: false, h: null, t: 0, end: () => {} };
  const finish = () => {
    if (me.done) return; me.done = true; clearTimeout(me.t); if (me.h) me.h.stop();
    if (FOLD.run === me) FOLD.run = null;
    me.end(); if (onEnd) onEnd();
    if (FOLD.pending) { FOLD.pending = false; render(false); }
  };
  me.finish = finish; FOLD.run = me;
  const run = (name, frame) => { me.h = KH.spring.animate({ from: 0, to: 1, name, onUpdate: p => { if (!me.done) frame(p); }, onRest: finish }); };
  if (want) {
    const H0 = box.offsetHeight;
    apply(true);
    const D = box.offsetHeight - H0;
    me.end = () => { box.classList.remove('fl-fold-anim', 'fl-fold-in'); box.style.clipPath = ''; };
    if (!(D > 0)) { finish(); return; }
    box.classList.add('fl-fold-anim');
    let shown = false;
    const frame = p => { box.style.clipPath = clipTo((1 - p) * D); if (!shown && p >= 0.25) { shown = true; box.classList.add('fl-fold-in'); } };
    frame(0);
    run('open', frame);
    return;
  }
  const x = box.querySelector('.fl-x'), H1 = box.offsetHeight, D = x ? H1 - x.offsetTop : 0;
  box.style.height = H1 + 'px';
  box.classList.add('fl-fold-out');
  me.end = () => { box.classList.remove('fl-fold-out'); box.style.clipPath = ''; box.style.height = ''; apply(false); };
  if (!(D > 0)) { finish(); return; }
  me.t = setTimeout(() => { if (!me.done) run('close', p => { box.style.clipPath = clipTo(p * D); }); }, TX_OUT);
}
function toggleMore() {
  const want = !S.more, was = P.moreT.textContent;
  fold(P.list, want, w => {
    S.more = w; drawList(pick(), true);
    if (typeof UI.swap === 'function' && P.moreT.textContent !== was && motion() !== 'reduced') { const t = P.moreT.textContent; P.moreT.textContent = was; UI.swap(P.moreT, t, was); }
  }, want ? null : () => {
    // 접은 뒤: 카드 머리가 화면 위로 지나갔으면 머리로 돌아오고, 포커스는 그 키에(눈에 띄는 종목 카드와 같음)
    const r = host.getBoundingClientRect();
    if (r.top < 0) host.scrollIntoView({ block: 'start', behavior: motion() === 'reduced' ? 'auto' : 'smooth' });
    P.more.focus({ preventScroll: true });
  });
}

/* ───────── 페이지 아래 출처 줄 (공시 · 정책 자료 다음, © · 투자 유의 문구 위 — AGENTS §3-30) ───────── */
const footP = h('p', { id: 'foot-flows', hidden: true });
function footText(pk) {
  if (!host || !host.isConnected || host.hidden) return '';
  const base = '투자자별 순매수: 네이버 증권 (시장 전체는 장중 값, 종목별은 장 마감 뒤 확정)';
  return pk && pk.src === 'live' ? base + ' · 종목별 잠정: 한국투자증권 가집계' : base + '.';
}
let footLast = '';
function placeFoot() {
  const foot = document.getElementById('foot');
  if (!foot) return;
  const after = document.getElementById('foot-policy') || document.getElementById('foot-disc');
  if (!after || after.parentNode !== foot) { if (footP.parentNode) footP.remove(); return; }   // 해외 · 지표 · 일정: 이 줄 없음
  if (after.nextElementSibling !== footP) after.after(footP);
}
function footer(pk) {
  const t = footText(pk);
  footLast = t;
  if (footP.textContent !== t) footP.textContent = t;
  footP.hidden = !t;
  placeFoot();
}
const footEl = document.getElementById('foot');
if (footEl) new MutationObserver(() => placeFoot()).observe(footEl, { childList: true });

/* ───────── 받기 · 갱신 ───────── */
function want(on) {
  const L = KH.flowsLive;
  const ok = !!on && fam() && L && typeof L.want === 'function';
  if (ok === S.wanted) return;
  S.wanted = ok;
  try { if (L && typeof L.want === 'function') L.want('card', ok); } catch (e) { /* the template's own trouble */ }
}
function tick(force) {
  if (document.hidden && !force) return;
  if (!S.file || (force && LIVE)) loadFile(false);
  else if (LIVE && S.file.asOf !== today()) {
    // 저녁 작업(21:30) 뒤 그날 파일 — 평일 21:00 넘으면 10분마다(보이는 동안) 다시 물어요
    const n = kstOf(nowMs());
    if (n.dow > 0 && n.dow < 6 && n.hm >= 2100 && S.near && Date.now() - S.fileAt > 600e3) loadFile(true);
  }
  if (LIVE && !S.names) loadNames();
  if (LIVE) market(force ? 0 : marketTtl());
}
mount();
if ('IntersectionObserver' in window) new IntersectionObserver(es => {
  const v = es[es.length - 1].isIntersecting;
  if (v === S.near) return;
  S.near = v; want(v);
  if (v) { tick(false); render(false); }
}, { rootMargin: '300px' }).observe(host);
else want(true);
for (const ev of ['kh:render', 'kh:data', 'kh:basis', 'kh:flowslive']) document.addEventListener(ev, () => { place(); soon(); });
document.addEventListener('kh:inv', () => { want(S.near); RANK.clear(); render(true); });
document.addEventListener('kh:refresh', () => { tick(true); if (S.wanted && KH.flowsLive && typeof KH.flowsLive.refresh === 'function') { try { KH.flowsLive.refresh(); } catch (e) { /* ignore */ } } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(false); });
setInterval(() => tick(false), 15000);
tick(false);
render(true);
// 초대 토큰 확인(/api/inv/me)이 끝나면 한 번 더(템플릿은 kh:inv도 보내요)
{ const I = inv(); if (I && typeof I.ready === 'function') try { Promise.resolve(I.ready()).then(() => { want(S.near); render(true); }, () => {}); } catch (e) { /* ignore */ } }
window.KHFlows = {
  state: () => { const pk = pick(); return { scope: scope(), who: S.who, dir: S.dir, more: S.more, src: pk.src, rows: (pk.rows || []).map(x => ({ c: x.c, a: x.a })), near: S.near, wanted: S.wanted,
    session: inSession(), ttl: marketTtl(), market: marketState(), file: S.file ? S.file.asOf : null, foot: footLast }; },
  market: maxAge => market(maxAge),
  marketState,
  render: () => render(true),
  refresh: () => tick(true),
};
})();
