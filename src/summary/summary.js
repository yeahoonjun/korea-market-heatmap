/* 오늘의 시장 요약 카드 (docs/standards/market-summary.md, AGENTS §3-34 — 사용자 2026-11-15 18:00 "b자리에 원래 a모양이었다가 상세 누르면 b모양").
   자리: PC · 태블릿은 옆 칸 맨 앞(태블릿은 한 줄 전체), 휴대폰은 지도 바로 다음 · 뉴스 카드 앞 — 지도는 움직이지 않아요.
   접힘(처음, 기억하지 않아요): 짧은 띠 — 장 단계 + 한 문장 / 오른 · 내린 막대 · 수 · 상한가 / 오른 업종 · 내린 업종.
   자세히: 그 자리에서 자라 표(지수 · 오른/내린 · 상/하한가 · 업종 · 외국인/기관 · 원/달러 · 미국) + 오늘 흐름 · 업종 · 테마 · 눈에 띄는 종목 ·
   수급 · 환율 · 금리 · 해외 · 공시 · 뉴스 + 글로 복사. 모양은 카드 바탕 판만 KH.spring 'open' / 'close'로 자라고 줄어요(design.md §7,
   design-references-full §7 P8 ⓐ) — 아래 내용은 한 번에 새 자리로(펼칠 땐 처음, 접을 땐 끝), 글자는 §6-4(나감 100ms → 60ms 뒤 들어옴).
   문장은 모두 규칙 템플릿(해요체)이에요 — LLM 호출 없음, 새 원천 없음, 조언 없음. 숫자는 지도 · 카드와 같은 저장소와 같은 파일을 써요.
   데이터: KH.index() · KH.stocks()/KH.quote() · 전 종목 등락(장 밖 close.json[lim 포함] + names.json, 장중 /api/breadth?m=K|Q) ·
   KH.loadData('flows' · 'themes' · 'names' · 'close') · /api/themes · /api/market · /api/world(index, commodity&with=fx,rates) ·
   KH.disclosures() · /api/news — 카드가 화면 근처(300px)에 오면 받아요. /api/news만은 ⌄ 키에 손이 갈 때부터(뉴스 카드와 겹치지 않게). 스냅샷(dist/)은 내장 데이터로, 해외 · 금리 · 공시 · 뉴스는 안내.
   점검용: 주소 ?summary_phase=pre|open|after|closed 는 장 단계 글자만 바꿔요(데이터는 그대로, qa/summary). */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function' || window.KHSummary) return;
const qs = new URLSearchParams(location.search);
const DEV_PHASE = ['pre', 'open', 'after', 'closed'].includes(qs.get('summary_phase')) ? qs.get('summary_phase') : null;

const h = KH.h, UI = KH.ui || {};
const LIVE = KH.MODE === 'live';
const MINUS = '−';
const phoneMQ = matchMedia('(max-width: 760px)');
const NF0 = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NF2 = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const put = (el, ...kids) => { el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false && k !== '')); return el; };
const rnd = (v, d) => +(+v).toFixed(d);
const sg = v => (v > 0 ? '+' : v < 0 ? MINUS : '');
const pct = (v, d = 2) => { if (v == null || !isFinite(v)) return '—'; const r = rnd(v, d); return sg(r) + Math.abs(r).toFixed(d) + '%'; };
const cls = (v, d = 2) => { const r = v == null || !isFinite(v) ? 0 : rnd(v, d); return r > 0 ? 'up' : r < 0 ? 'dn' : 'flat'; };
// 억원 → "6,364억" · "1.2조" (부호 있음 / 없음)
const eok = v => { const a = Math.abs(v); return a >= 10000 ? NF1.format(a / 10000) + '조' : NF0.format(Math.round(a)) + '억'; };
const amt = v => (Math.abs(v) < 0.5 ? '0억' : sg(v) + eok(v));
const pad = n => String(n).padStart(2, '0');
const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
const kstOf = ms => { const k = new Date(ms + 9 * 3600e3); return { dow: k.getUTCDay(), hm: k.getUTCHours() * 100 + k.getUTCMinutes(), hhmm: `${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`, day: `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}` }; };
const DOW = '일월화수목금토';
const dayLong = ymd => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(ymd || ''); if (!m) return ''; const w = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay(); return `${+m[2]}월 ${+m[3]}일 (${DOW[w]})`; };
const dayShort = ymd => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(ymd || ''); return m ? `${+m[2]}/${+m[3]}` : ''; };
const asOfMs = () => { const a = KH.asOf(); const t = a ? Date.parse(a) : NaN; return isFinite(t) ? t : null; };
const themeName = n => String(n || '').replace(/\s*\([^)]*\)\s*/g, ' ').replace(/\s+/g, ' ').trim() || String(n || '');
const motion = () => (typeof KH.motion === 'function' ? KH.motion() : 'standard');
const TXT_OUT = 100, TXT_GAP = 60;                                        // design.md §6-4: 글자 나감 100ms · 들어옴은 60ms 뒤

/* ───────── 장 단계: pre 장 전 · open 장중 · after 오늘 마감 · closed 휴장(주말 · 공휴일) ───────── */
function phase() {
  if (DEV_PHASE) return DEV_PHASE;
  const now = kstOf(nowMs()), st = KH.marketStatus ? KH.marketStatus() : {};
  if (now.dow === 0 || now.dow === 6) return 'closed';
  if (st.KOSPI === 'OPEN' || st.KOSDAQ === 'OPEN') return 'open';
  if (now.hm < 900) return 'pre';
  const a = asOfMs(), dd = a ? kstOf(a).day : null;
  if (dd === now.day) return now.hm < 1530 ? 'open' : 'after';
  return 'closed';                                   // a weekday with no trades today (공휴일)
}
const dataDay = () => { const a = asOfMs(); return a ? kstOf(a).day : null; };
const PILL = { pre: '장 전', open: '장중', after: '오늘 마감', closed: '휴장' };
function whenText(ph) {
  const a = asOfMs(), k = a ? kstOf(a) : null, d = dataDay();
  if (!LIVE) return d ? `${dayLong(d)} 15:30 종가 기준` : '스냅샷 기준';
  if (ph === 'open') return k ? `${k.hhmm} 기준` : '장중';
  if (ph === 'after') return '15:30 정규장 종가 기준';
  if (ph === 'pre') return d ? `${dayLong(d)} 마감 기준 · 9시에 시작해요` : '장 시작 전이에요';
  return d ? `${dayLong(d)} 마감 기준` : '마지막 거래일 기준';
}

/* ───────── 데이터 ───────── */
const D = {
  brd: { K: null, Q: null, src: null, at: 0, busy: false, fail: false, date: null },   // K/Q: [{c, r, lim}]
  names: null,                     // Map code → [name, 'K'|'Q']
  close: null,                     // close.json — 장 밖(장 전 · 마감 후 · 휴장)엔 업종 · 종목 줄도 KRX 정규장 종가로(문서 §3-0)
  flows: null, themesFile: null,
  themes: { j: null, at: 0, fail: false },
  market: { j: null, at: 0, fail: false },
  wIdx: { j: null, at: 0, fail: false },
  wMac: { j: null, at: 0, fail: false },
  news: { j: null, at: 0, fail: false },
};
async function getJSON(url, wait = 9000) {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), wait);
  try { const r = await fetch(url, { signal: ac.signal }); if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }
  finally { clearTimeout(t); }
}
const fast = () => ['open', 'pre'].includes(phase());
// slot.p = 받는 중인 약속(처음 펼칠 때 잠깐 기다리려고) · 처음 온 값은 곧바로 그려요(장중 15초 간격을 기다리지 않게)
function pull(slot, url, ttlFast, ttlSlow, force) {
  if (!LIVE) return null;
  const ttl = fast() ? ttlFast : ttlSlow;
  if (slot.busy || (!force && slot.at && Date.now() - slot.at < (slot.fail ? 60e3 : ttl))) return slot.p || null;
  slot.busy = true;
  const had = !!slot.j;
  slot.p = (async () => {
    try { slot.j = await getJSON(url); slot.fail = false; } catch (e) { slot.fail = true; }
    slot.busy = false; slot.at = Date.now(); slot.p = null;
    schedule(!had);
  })();
  return slot.p;
}
async function names() {
  if (D.names) return D.names;
  if (!LIVE) { D.names = new Map(KH.stocks().map(s => [s.c, [s.n, s.m]])); return D.names; }
  const j = await KH.loadData('names');
  if (j && j.n) D.names = new Map(Object.entries(j.n));
  return D.names;
}
async function closeFile() {
  if (!LIVE) return null;
  if (D.close) return D.close;
  const j = await KH.loadData('close');
  if (j && j.c) D.close = j;
  return D.close;
}
// 상 · 하한가: close.json의 네 번째 칸(빌드가 넣어요, "lim": true) · breadth 행의 lim · 시세 행의 원천 표시 limf(템플릿 norm — lim에는
// ±29.5% 어림이 섞여 있어요). 옛 close.json(표시 없음)에만 있는 종목만 ±29.5% 어림
const limGuess = r => (Math.abs(r) >= 29.5 ? Math.sign(r) : 0);
const flagOf = s => (s && (s.limf === 1 || s.limf === -1) ? s.limf : s && s.limf === 0 ? 0 : (s && s.lim) || 0);
// 전 종목 등락 — 등락 분포 카드와 같은 원천: 스냅샷 = 내장 전 종목, 장 밖 = close.json(+ names.json), 장중 = /api/breadth?m=K|Q
async function pullBreadth(force) {
  const b = D.brd;
  if (b.busy) return;
  const had = !!b.src;
  const own = () => { const K = [], Q = []; for (const s of KH.stocks()) (s.m === 'Q' ? Q : K).push({ c: s.c, r: +s.r || 0, lim: flagOf(s) }); return { K, Q }; };
  if (!LIVE) { if (!b.src) Object.assign(b, own(), { src: 'snapshot', date: dataDay() }); return; }
  const ph = phase(), useClose = ph !== 'open' && !DEV_PHASE;
  const ttl = ph === 'open' ? 60e3 : 600e3;
  if (!force && b.at && Date.now() - b.at < ttl && b.src) return;
  b.busy = true;
  try {
    if (useClose) {
      const [cj, nm] = await Promise.all([closeFile(), names()]);
      if (!cj || !cj.c || !nm) throw new Error('close');
      const exact = cj.lim === true, limOf = exact ? null : new Map(KH.stocks().map(s => [s.c, flagOf(s)]));
      const K = [], Q = [];
      for (const c in cj.c) {
        const x = cj.c[c], m = nm.get(c); if (!m || !(+x[0] > 0)) continue;
        const r = +x[2] || 0;
        const lim = exact ? (x[3] === 1 || x[3] === -1 ? x[3] : 0) : limOf.has(c) ? limOf.get(c) : limGuess(r);
        (m[1] === 'Q' ? Q : K).push({ c, r, lim });
      }
      Object.assign(b, { K, Q, src: 'close', exact, date: cj.date || null, fail: false });
    } else {
      const [k, q] = await Promise.all(['K', 'Q'].map(m => getJSON(`api/breadth?m=${m}`)));
      const conv = j => ((j && j.rows) || []).filter(x => Array.isArray(x) && isFinite(+x[1])).map(x => ({ c: String(x[0]), r: +x[1], lim: x[2] === 1 || x[2] === -1 ? x[2] : 0 }));
      Object.assign(b, { K: conv(k), Q: conv(q), src: 'breadth', exact: true, date: dataDay(), fail: false });
    }
  } catch (e) {
    b.fail = true;
    if (!b.src) Object.assign(b, own(), { src: 'stream', exact: true, date: dataDay() });   // the streamed 600 at least (labelled so)
  }
  b.busy = false; b.at = Date.now();
  schedule(!had);
}
// 카드가 화면 근처에 오면 받아 둬요 — 펼칠 때 표가 한 번에 다 차게("받는 중" 줄이 나중에 자라며 아래 내용이 또 밀리지 않게, P8 ⓐ).
// /api/news만은 "자세히"에 손이 갈 때(올림 · 포커스 · 누름)부터 — 뉴스 카드도 같은 주소를 받아서, 펼치지 않는 사람에겐 겹친 요청 0
let newsOn = false;
const TABLE = ['themes', 'market', 'wIdx', 'wMac', 'news'];
function refreshAll(force) {
  pullBreadth(force);
  if (LIVE && phase() !== 'open' && !D.close) closeFile().then(() => schedule(true));
  if (!D.flows) KH.loadData('flows').then(j => { if (j && j.f) { D.flows = j; schedule(true); } });
  if (!D.themesFile) KH.loadData('themes').then(j => { if (j && j.themes) { D.themesFile = j; schedule(true); } });
  if (LIVE) names().then(() => schedule(true));
  if (!LIVE) { if (!D.market.j) KH.loadData('market').then(j => { if (j && j.items) { D.market.j = j; schedule(true); } }); return; }
  pull(D.themes, 'api/themes', 60e3, 300e3, force);
  pull(D.market, 'api/market', 60e3, 300e3, force);
  pull(D.wIdx, 'api/world?kind=index', 120e3, 600e3, force);
  pull(D.wMac, 'api/world?kind=commodity&with=fx,rates', 120e3, 600e3, force);
  if (newsOn) pull(D.news, 'api/news', 180e3, 180e3, force);
}
function warm() { if (!newsOn && LIVE) { newsOn = true; pull(D.news, 'api/news', 180e3, 180e3, false); } }

/* ───────── 계산 (DOM 없이) ───────── */
// 장중: 지도와 같은 값(KH.quote — 고른 가격 기준). 장 밖: KRX 정규장 종가(close.json) — 지도가 NXT · 통합이어도 요약은 머리의 "… 종가 기준"과
// 같은 값이에요(지수도 KRX). 스냅샷은 행 그대로(15:30 종가). 보통주 · 시장별 시총 상위 300.
function rows(ph) {
  const all = KH.stocks().filter(s => /0$/.test(s.c));
  const top = [];
  for (const m of ['K', 'Q']) top.push(...all.filter(s => s.m === m).sort((a, b) => (b.cap || 0) - (a.cap || 0)).slice(0, 300));
  const fixed = LIVE && ph !== 'open' && D.close && D.close.c;
  return top.map(s => {
    const x = fixed ? D.close.c[s.c] : null;
    const q = !fixed && LIVE && typeof KH.quote === 'function' ? KH.quote(s.c) : null;
    const r = x ? +x[2] || 0 : q && isFinite(+q.r) ? +q.r : +s.r || 0;
    const lim = x && D.close.lim === true ? (x[3] === 1 || x[3] === -1 ? x[3] : 0) : flagOf(q || s);
    return { c: s.c, n: s.n, m: s.m, s: s.s, i: s.i, cap: +s.cap || 0, r, tv: +(q && q.tv != null ? q.tv : s.tv) || 0, lim };
  });
}
const median = a => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
function groupBy(list, key, minN, minCap) {
  const g = new Map();
  for (const x of list) { const k = x[key] || '기타'; if (k === '기타') continue; (g.get(k) || g.set(k, []).get(k)).push(x); }
  const out = [];
  for (const [k, xs] of g) {
    const cap = xs.reduce((a, x) => a + x.cap, 0);
    if (xs.length < minN || cap < minCap || !cap) continue;
    out.push({ name: k, r: xs.reduce((a, x) => a + x.r * x.cap, 0) / cap, n: xs.length, cap });
  }
  return out.sort((a, b) => b.r - a.r);
}
function model() {
  const ph = phase(), M = { ph, pill: PILL[ph], when: whenText(ph), live: ph === 'open' };
  if (!LIVE) M.pill = '스냅샷';
  const ix = KH.index() || {};
  const K = ix.KOSPI, Q = ix.KOSDAQ;
  M.idx = [K && { key: 'KOSPI', name: '코스피', v: +K.value, r: +K.ratio }, Q && { key: 'KOSDAQ', name: '코스닥', v: +Q.value, r: +Q.ratio }].filter(x => x && isFinite(x.v) && isFinite(x.r));
  M.headline = M.idx.length === 2 ? idxSentence(M.idx[0].r, M.idx[1].r, M.live) : '';
  const R = rows(ph);
  // 시가총액 가중: 두 지수 등락률을 시장별 시총(지도 600종목 합)으로 가중 — 탭 '전체'의 숫자와 같은 방식
  const capK = R.filter(x => x.m === 'K').reduce((a, x) => a + x.cap, 0), capQ = R.filter(x => x.m === 'Q').reduce((a, x) => a + x.cap, 0);
  if (M.idx.length === 2 && capK + capQ > 0) M.capW = (M.idx[0].r * capK + M.idx[1].r * capQ) / (capK + capQ);
  // 전 종목 등락
  const b = D.brd;
  if (b.src) {
    const all = [...(b.K || []), ...(b.Q || [])];
    const cnt = xs => { let up = 0, dn = 0, fl = 0, lu = 0, ld = 0, u10 = 0, d10 = 0; for (const x of xs) { const r = rnd(x.r, 2); r > 0 ? up++ : r < 0 ? dn++ : fl++; if (x.lim > 0) lu++; else if (x.lim < 0) ld++; if (x.r >= 10) u10++; else if (x.r <= -10) d10++; } return { up, dn, fl, n: xs.length, lu, ld, u10, d10 }; };
    M.br = Object.assign(cnt(all), { K: cnt(b.K || []), Q: cnt(b.Q || []), src: b.src, med: median(all.map(x => x.r)), fail: b.fail, date: b.date });
    M.br.say = breadthSentence(M.br, M.live);
    M.br.limUp = all.filter(x => x.lim > 0).map(x => x.c);
    if (M.capW != null && M.br.med != null) M.capSay = capSentence(M.capW, M.br.med, M.live);
  }
  // 업종(지도 600종목, 시총 가중, 2종목 · 3조 이상) · 테마(네이버 테마 등락률 = 테마 탭과 같은 값; 5종목 이상)
  const ind = groupBy(R, 'i', 2, 30000);
  M.indUp = ind.filter(x => x.r > 0).slice(0, 2);
  M.indDn = ind.filter(x => x.r < 0).slice(-2).reverse();
  const tf = D.themesFile && D.themesFile.themes ? new Map(D.themesFile.themes.map(t => [String(t.id), t])) : null;
  let th = null;
  if (LIVE && D.themes.j && Array.isArray(D.themes.j.themes)) {
    th = D.themes.j.themes.filter(t => isFinite(+t.ratio) && (!tf || ((tf.get(String(t.id)) || {}).codes || []).length >= 5)).map(t => ({ name: t.name, r: +t.ratio }));
  } else if (tf) {
    const by = new Map(R.map(x => [x.c, x]));
    if (!LIVE) for (const s of KH.stocks()) if (!by.has(s.c)) by.set(s.c, { r: +s.r || 0, cap: +s.cap || 0 });
    th = [];
    for (const t of tf.values()) {
      const xs = (t.codes || []).map(c => by.get(c)).filter(Boolean);
      const cap = xs.reduce((a, x) => a + x.cap, 0);
      if (xs.length >= 5 && cap > 0) th.push({ name: t.name, r: xs.reduce((a, x) => a + x.r * x.cap, 0) / cap });
    }
  }
  M.thUp = []; M.thDn = [];
  if (th) { th.sort((a, b) => b.r - a.r); M.thUp = th.filter(x => x.r > 0).slice(0, 2); M.thDn = th.filter(x => x.r < 0).slice(-2).reverse(); }
  // 눈에 띄는 종목: 시총 100위 안 가장 많이 오른 · 내린 종목, 거래대금 상위 2(20일 평균이 생기기 전엔 "급증"이라고 하지 않아요 — §3-34 ④), 상한가 이름
  const big = R.slice().sort((a, b) => b.cap - a.cap).slice(0, 100);
  if (big.length) {
    const hi = big.reduce((a, x) => (x.r > a.r ? x : a)), lo = big.reduce((a, x) => (x.r < a.r ? x : a));
    M.bigUp = hi.r > 0 ? hi : null; M.bigDn = lo.r < 0 ? lo : null;
  }
  M.tvTop = R.filter(x => x.tv > 0).sort((a, b) => b.tv - a.tv).slice(0, 2);
  const nm = D.names, capOf = new Map(R.map(x => [x.c, x.cap]));
  const nameOf = c => { const s = KH.stock(c); return (s && s.n) || (nm && nm.get(c) && nm.get(c)[0]) || null; };
  if (M.br) {
    const rOf = new Map([...(D.brd.K || []), ...(D.brd.Q || [])].map(x => [x.c, x.r]));
    M.limNames = M.br.limUp.filter(c => /0$/.test(c)).map(c => ({ c, n: nameOf(c), r: rOf.get(c), cap: capOf.get(c) || 0, onMap: capOf.has(c) })).filter(x => x.n)
      .sort((a, b) => b.cap - a.cap || a.n.localeCompare(b.n, 'ko'));
  }
  // 수급(매일 파일 flows.json — 장중에도 전 거래일 값 + 날짜, §3-34 ③): 종목별 순매수 × 그날 종가의 합(추정), 외국인 · 기관 · 개인 1일
  const F = D.flows;
  if (F && F.f && (nm || !LIVE)) {
    const mOf = c => { const s = KH.stock(c); if (s) return s.m; const x = nm && nm.get(c); return x ? x[1] : null; };
    const sum = { K: [0, 0, 0], Q: [0, 0, 0] };
    let fTop = null, fBot = null;
    for (const c in F.f) {
      const v = F.f[c], m = mOf(c); if (!m || !Array.isArray(v)) continue;
      for (let i = 0; i < 3; i++) sum[m][i] += +v[i] || 0;
      if (v[0] != null && (!fTop || v[0] > fTop.v)) fTop = { c, v: +v[0] };
      if (v[0] != null && (!fBot || v[0] < fBot.v)) fBot = { c, v: +v[0] };
    }
    M.flows = { date: F.asOf, sum, all: [0, 1, 2].map(i => sum.K[i] + sum.Q[i]), top: fTop && fTop.v > 0 ? Object.assign(fTop, { n: nameOf(fTop.c) }) : null, bot: fBot && fBot.v < 0 ? Object.assign(fBot, { n: nameOf(fBot.c) }) : null };
    M.flows.today = F.asOf === kstOf(nowMs()).day;
  }
  // 환율 · 금리 · 해외
  const mk = D.market.j && Array.isArray(D.market.j.items) ? new Map(D.market.j.items.map(x => [x.key, x])) : new Map();
  const wItems = j => { const m = new Map(); for (const g of (j && j.groups) || []) for (const x of g.items || []) m.set(x.key, x); return m; };
  const wi = wItems(D.wIdx.j), wm = wItems(D.wMac.j);
  M.fx = wm.get('FX_USDKRW') || mk.get('USDKRW') || null;
  M.us10 = wm.get('US10YT') || null; M.kr3 = wm.get('KR3YT') || null;
  const inx = wi.get('INX'), ixic = wi.get('IXIC'), sox = wi.get('SOX');
  // 미국: 우리 장 전 · 휴장엔 간밤 현물 지수 종가(장중이면 그 값), 우리 장중 · 장 뒤엔 미국 지수 선물(10분 지연)
  const usCash = ph === 'pre' || ph === 'closed' || (inx && inx.status === 'OPEN');
  if (usCash && inx) M.us = { label: inx.status === 'OPEN' ? '미국 장중' : '간밤 미국', items: [inx, ixic, sox].filter(Boolean).map(x => ({ name: x.name, r: +x.ratio })) };
  else if (mk.get('SPX_F')) M.us = { label: '미국 선물', items: [mk.get('SPX_F'), mk.get('NDX_F')].filter(Boolean).map(x => ({ name: x.name.replace(' 선물', ''), r: +x.ratio })), delayed: true };
  M.wti = wm.get('CLcv1') || mk.get('WTI') || null;
  M.macroFail = LIVE && D.market.fail && D.wMac.fail;
  // 공시 · 뉴스 — 공시 모듈이 이미 받은 목록(KH.disclosures)을 읽기만 해요(요청 0)
  if (typeof KH.disclosures === 'function') {
    const dj = KH.disclosures();
    if (dj && Array.isArray(dj.rows)) {
      const by = { 실적: 0, 주요: 0 };
      for (const r of dj.rows) if (r.k in by) by[r.k]++;
      const pick = dj.rows.filter(r => r.k === '실적' || r.k === '주요').map(r => Object.assign({}, r, { cap: capOf.get(r.c) || 0, nm: nameOf(r.c) })).filter(r => r.nm).sort((a, b) => b.cap - a.cap)[0] || null;
      M.disc = { date: dj.date, total: dj.rows.length, by, pick, today: dj.date === kstOf(nowMs()).day };
    }
  }
  if (D.news.j && Array.isArray(D.news.j.items) && D.news.j.items.length) M.news = D.news.j.items[0];
  return M;
}

/* ───────── 문장 규칙 (해요체 · 사실만 · 조언 없음 — 문서 §4) ───────── */
const dirOf = r => (Math.abs(r) < 0.05 ? 0 : Math.sign(r));
const mag = r => (Math.abs(r) >= 1 ? `${Math.floor(Math.abs(r))}% 넘게 ` : '');
function idxSentence(k, q, live) {
  const end = d => (d > 0 ? (live ? '오르고 있어요' : '올랐어요') : d < 0 ? (live ? '내리고 있어요' : '내렸어요') : (live ? '제자리예요' : '제자리였어요'));
  const mid = d => (d > 0 ? '오르고' : d < 0 ? '내리고' : '제자리이고');
  const a = dirOf(k), b = dirOf(q);
  if (a === b) return a === 0 ? `코스피 · 코스닥 모두 ${end(0)}` : `코스피 · 코스닥 모두 ${mag(Math.min(Math.abs(k), Math.abs(q)))}${end(a)}`;
  return `코스피는 ${a ? mag(k) : ''}${mid(a)} 코스닥은 ${b ? mag(q) : ''}${end(b)}`;
}
function breadthSentence(B, live) {
  const n = B.up + B.dn + B.fl; if (!n) return '';
  const su = B.up / n, sd = B.dn / n;
  const p = live ? '오르고 있어요' : '올랐어요', m = live ? '내리고 있어요' : '내렸어요';
  if (su >= 0.65) return `10개 중 ${Math.round(su * 10)}개꼴로 ${p}`;
  if (sd >= 0.65) return `10개 중 ${Math.round(sd * 10)}개꼴로 ${m}`;
  if (B.up >= B.dn * 1.2) return '오른 종목이 조금 더 많아요';
  if (B.dn >= B.up * 1.2) return '내린 종목이 조금 더 많아요';
  return '오른 종목과 내린 종목이 비슷해요';
}
function capSentence(capW, med, live) {
  const gap = capW - med, v = live ? '이고 있어요' : '였어요';
  if (Math.abs(gap) < 0.5) return `대형주와 중소형주가 비슷하게 움직${v}`;
  if (gap < 0) return capW < 0 ? (live ? '대형주가 더 많이 내리고 있어요' : '대형주가 더 많이 내렸어요') : (live ? '대형주가 덜 오르고 있어요' : '대형주가 덜 올랐어요');
  return capW > 0 ? (live ? '대형주가 더 많이 오르고 있어요' : '대형주가 더 많이 올랐어요') : (live ? '대형주가 덜 내리고 있어요' : '대형주가 덜 내렸어요');
}

/* ───────── 그리기 조각 ───────── */
const num = (v, d = 2) => h('b', { class: 'sm-n ' + cls(v, d), text: pct(v, d) });
// 종목 칩: 이름 + 숫자(등락률이나 금액), 누르면 지도 타일과 같은 빠른 보기
function stk(c, n, v, txt) {
  const b = h('button', { type: 'button', class: 'sm-stk', 'aria-label': `${n} ${txt || pct(v)} · 빠른 보기` },
    h('span', { class: 'sm-sn', text: n }), h('b', { class: 'sm-n ' + (txt ? cls(v, 0) : cls(v)), text: txt || pct(v) }));
  b.addEventListener('click', () => { if (typeof KH.quick === 'function') KH.quick(c, b); });
  return b;
}
const nv = (name, r, title) => h('span', { class: 'sm-nv', title: title || name }, h('span', { class: 'sm-nm', text: name }), num(r));
const sep = () => h('span', { class: 'sm-dot', 'aria-hidden': 'true', text: '·' });
const join = (items, s = sep) => items.flatMap((x, i) => (i ? [s(), x] : [x]));
function bar(B) {
  const p = typeof KH.palette === 'function' ? KH.palette() : { up: '#ef3e4a', flat: '#555', down: '#12a15b' };
  const n = B.up + B.dn + B.fl || 1;
  return h('span', { class: 'sm-bar', role: 'img', 'aria-label': `상승 ${NF0.format(B.up)} · 보합 ${NF0.format(B.fl)} · 하락 ${NF0.format(B.dn)}` },
    h('i', { style: `width:${B.up / n * 100}%;background:${p.up}` }), h('i', { style: `width:${B.fl / n * 100}%;background:${p.flat}` }), h('i', { style: `width:${B.dn / n * 100}%;background:${p.down}` }));
}
const scopeText = B => (B.src === 'stream' ? '시총 상위 600종목' : `전 종목 ${NF0.format(B.n)}`);
const later = txt => h('span', { class: 'sm-wait', text: txt });
const snapNote = what => h('span', { class: 'sm-wait' }, `${what}는 `, h('a', { href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '실시간 버전' }), '에서 볼 수 있어요');
const link = (url, text, title) => h('a', { class: 'sm-a', href: url, target: '_blank', rel: 'noopener', title: title || text, text });
const fxChg = x => sg(rnd(x.change, 1)) + NF1.format(Math.abs(+x.change));
const bpOf = x => (x.bp != null ? +x.bp : +x.change * 100);
const shortUS = n => ({ '나스닥 100': '나스닥', '나스닥 종합': '나스닥', '필라델피아 반도체': '반도체' })[n] || n;
const line = (...kids) => h('p', { class: 'sm-l' }, ...kids);
const say = t => (t ? h('p', { class: 'sm-say', text: t }) : null);
const sub = t => (t ? h('p', { class: 'sm-sub', text: t }) : null);
const kk = t => h('span', { class: 'sm-k', text: t });
// 꺾쇠 아이콘: 24 그리드 · 선 1.75 · currentColor (design.md §4)
const svgOf = (d, size) => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.75', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) s.setAttribute(k, v); s.innerHTML = d; return s; };
const chev = () => { const s = svgOf('<path d="m7 10 5 5 5-5"/>', 16); s.classList.add('sm-chev'); return s; };

/* 접힌 띠: 오른 · 내린 막대 + 수 + 상한가 / 업종 오른 · 내린 (휴대폰 · PC 같은 두 줄, 넘치면 이름만 줄여요).
   바뀐 칸만 바꾸게 칸마다 열쇠(data-k) — 숫자(data-num)는 방향 있게(커지면 아래에서 · 작아지면 위에서, P9), 이름은 위로 */
const kn = (k, v, text, c) => h('span', { class: c || null, 'data-k': k, 'data-v': String(v), 'data-num': '', text });
// 상 · 하한가 (사용자 2026-11-16 11:16 "상하한가 종목 수도 색깔과 필요하면 아이콘"): the map legend's swatch (a tile with the bar on top · at
// the bottom, --limsw · --lim-bar) + the count in 상승 · 하락 colour (0 stays neutral) — the same read as the 등락 분포 card and the dock
const lsw = d => h('i', { class: 'sm-lsw ' + d, 'aria-hidden': 'true' });
const limCls = (n, dir) => (n ? (dir > 0 ? 'up' : 'dn') : 'flat');
function band(M) {
  const B = M.br, phone = phoneMQ.matches;
  const l1 = h('div', { class: 'sm-b1', title: B ? `코스피 · 코스닥 ${scopeText(B)}` : null },
    B ? bar(B) : null,
    B ? h('b', { class: 'sm-n up' }, '상승 ', kn('up', B.up, NF0.format(B.up))) : later(LIVE ? '전 종목 등락을 받는 중…' : '—'),
    B ? sep() : null, B ? h('b', { class: 'sm-n dn' }, '하락 ', kn('dn', B.dn, NF0.format(B.dn))) : null,
    B && (B.lu || B.ld) ? sep() : null,
    // the folded band is tight (PC side card ~ 300px): colour only, the swatches live in 자세히
    B && (B.lu || B.ld) ? h('span', { class: 'sm-k' }, '상한가 ', kn('lu', B.lu, String(B.lu), 'sm-n ' + limCls(B.lu, 1)),
      B.ld && !phone ? ' · 하한가 ' : null, B.ld && !phone ? kn('ld', B.ld, String(B.ld), 'sm-n ' + limCls(B.ld, -1)) : null) : null);
  const ind = [['iu', M.indUp[0]], ['id', M.indDn[0]]].filter(x => x[1]);
  const l2 = h('div', { class: 'sm-b2' }, ind.length ? kk('업종') : null, ...join(ind.map(([k, x]) => h('span', { class: 'sm-nv', title: x.name },
    h('span', { class: 'sm-nm', 'data-k': k + 'n', text: x.name }), h('b', { class: 'sm-n ' + cls(x.r), 'data-k': k + 'v', 'data-v': String(x.r), 'data-num': '', text: pct(x.r) })))));
  return [l1, l2];
}
const bandShape = el => [...el.querySelectorAll('[data-k]')].map(x => x.dataset.k).join(',') + '|' + el.querySelectorAll('.sm-bar').length;
function swapNum(el, text, dir) {
  const cur = el.dataset.t != null ? el.dataset.t : el.textContent;
  if (cur === text) return;
  el.dataset.t = text;
  clearTimeout(el._sw);
  if (reduced() || document.hidden || !cur || !el.isConnected || el.closest('[hidden]')) { el.classList.remove('sm-sw', 'sm-swd'); el.textContent = text; return; }
  el.classList.add('sm-sw'); el.classList.toggle('sm-swd', dir < 0);
  el.replaceChildren(h('span', { class: 'o', 'aria-hidden': 'true', text: cur }), h('span', { class: 'n', text }));
  el._sw = setTimeout(() => { if (el.dataset.t === text) { el.classList.remove('sm-sw', 'sm-swd'); el.textContent = text; } }, 400);
}
function drawBand(M) {
  const fresh = band(M), cur = P.band, tmp = h('div', null, fresh);
  if (!cur.firstChild || bandShape(cur) !== bandShape(tmp)) { put(cur, fresh); return; }
  const ob = cur.querySelector('.sm-bar'), nb = tmp.querySelector('.sm-bar');
  if (ob && nb) ob.replaceWith(nb);
  const b1 = cur.querySelector('.sm-b1'), t1 = tmp.querySelector('.sm-b1');
  if (b1 && t1) b1.title = t1.title;
  for (const n of tmp.querySelectorAll('[data-k]')) {
    const o = cur.querySelector(`[data-k="${n.dataset.k}"]`);
    if (!o) continue;
    const text = n.textContent;
    if (n.dataset.num != null) {
      const dir = Math.sign((+n.dataset.v || 0) - (+o.dataset.v || 0));
      for (const c of ['up', 'dn', 'flat']) o.classList.toggle(c, n.classList.contains(c));
      o.dataset.v = n.dataset.v;
      swapNum(o, text, dir);
    } else if (o.textContent !== text) { swapText(o, text); if (o.parentElement) o.parentElement.title = text; }
  }
}

/* 펼친 표 — 한 줄에 사실 하나(라벨 | 값) */
function facts(M) {
  const F = [];
  const f = (key, label, note, ...v) => F.push({ key, label, note, v });
  for (const x of M.idx) f('idx', x.name, null, h('span', { class: 'sm-v', text: NF2.format(x.v) }), num(x.r));
  if (M.br) f('br', '오른 · 내린 종목', '두 시장', bar(M.br), h('b', { class: 'sm-n up', text: NF0.format(M.br.up) }), sep(), h('b', { class: 'sm-n dn', text: NF0.format(M.br.dn) }));
  else f('br', '오른 · 내린 종목', null, later(LIVE ? '받는 중…' : '—'));
  if (M.br && (M.br.lu || M.br.ld)) f('lim', '상한가 · 하한가', null, h('span', { class: 'sm-lim' }, lsw('u'), h('b', { class: 'sm-n ' + limCls(M.br.lu, 1), text: NF0.format(M.br.lu) })), sep(),
    h('span', { class: 'sm-lim' }, lsw('d'), h('b', { class: 'sm-n ' + limCls(M.br.ld, -1), text: NF0.format(M.br.ld) })));
  if (M.indUp[0]) f('indUp', '많이 오른 업종', null, nv(M.indUp[0].name, M.indUp[0].r));
  if (M.indDn[0]) f('indDn', '많이 내린 업종', null, nv(M.indDn[0].name, M.indDn[0].r));
  if (M.flows) f('flows', '외국인 · 기관', M.flows.today ? null : dayShort(M.flows.date), h('b', { class: 'sm-n ' + cls(M.flows.all[0], 0), text: amt(M.flows.all[0]) }), sep(), h('b', { class: 'sm-n ' + cls(M.flows.all[1], 0), text: amt(M.flows.all[1]) }));
  const wait = LIVE && !M.macroFail ? later('받는 중…') : null;
  if (M.fx) f('fx', '원/달러', null, h('span', { class: 'sm-v', text: NF1.format(+M.fx.value) }), h('b', { class: 'sm-n ' + cls(+M.fx.change, 1), text: fxChg(M.fx) }));
  else if (wait) f('fx', '원/달러', null, wait);
  if (M.us) f('us', M.us.label, null, ...join(M.us.items.slice(0, 2).map(x => nv(shortUS(x.name), x.r))));
  else if (wait) f('us', '미국', null, later('받는 중…'));
  // 장 전에는 간밤 해외 · 환율이 먼저
  if (M.ph === 'pre') F.sort((a, b) => (['us', 'fx'].includes(b.key) ? 1 : 0) - (['us', 'fx'].includes(a.key) ? 1 : 0));
  // 원/달러 · 미국 are 해외 · 지표 values: .pal-w gives them that side's 등락 colours (the template's 색상 per side, 2026-11-16)
  return h('dl', { class: 'sm-facts' }, F.map(x => h('div', { class: 'sm-f sm-f-' + x.key + (x.key === 'fx' || x.key === 'us' ? ' pal-w' : '') },
    h('dt', null, x.label, x.note ? h('small', { text: ' ' + x.note }) : null), h('dd', null, ...x.v))));
}

/* 자세히 — 덩어리마다 작은 제목 + 줄 */
const sec = (title, ...kids) => { const k = kids.flat(Infinity).filter(Boolean); return k.length ? h('section', { class: 'sm-sec' }, h('h3', { text: title }), ...k) : null; };
function secFlow(M) {
  const B = M.br;
  return sec('오늘 흐름',
    B ? say(B.say + (B.lu || B.ld ? ` · 상한가 ${B.lu} · 하한가 ${B.ld}` : '')) : null,
    M.capSay ? say(M.capSay) : null,
    M.capW != null && B ? line(kk('시총 가중'), num(M.capW), sep(), kk('종목 중간값'), num(B.med)) : null,
    B ? sub(`상승 : 하락 — 코스피 ${NF0.format(B.K.up)} : ${NF0.format(B.K.dn)} · 코스닥 ${NF0.format(B.Q.up)} : ${NF0.format(B.Q.dn)} · ${scopeText(B)}` + (B.src === 'stream' && B.fail ? ' · 전 종목은 불러오지 못했어요' : '')) : null);
}
function secSector(M) {
  return sec('업종 · 테마',
    M.indUp.length ? line(kk('오른 업종'), ...join(M.indUp.map(x => nv(x.name, x.r)))) : null,
    M.indDn.length ? line(kk('내린 업종'), ...join(M.indDn.map(x => nv(x.name, x.r)))) : null,
    M.thUp.length ? line(kk('오른 테마'), ...join(M.thUp.map(x => nv(themeName(x.name), x.r, x.name)))) : null,
    M.thDn.length ? line(kk('내린 테마'), ...join(M.thDn.map(x => nv(themeName(x.name), x.r, x.name)))) : null,
    M.thUp.length || M.indUp.length ? sub('업종은 지도 종목(시장별 시총 상위 300)의 시총 가중, 테마는 테마 탭과 같은 값') : null);
}
function secMovers(M) {
  const L = M.limNames || [];
  return sec('눈에 띄는 종목',
    L.length ? line(h('span', { class: 'sm-k sm-lim' }, lsw('u'), '상한가 ', h('b', { class: 'sm-n up', text: NF0.format(M.br.lu) })), ...L.slice(0, 2).map(x => (x.onMap ? stk(x.c, x.n, x.r) : h('span', { class: 'sm-off', text: x.n }))),
      L.length > 2 ? kk(`외 ${L.length - 2}`) : null) : null,
    M.bigUp || M.bigDn ? line(kk('시총 100위 안'), M.bigUp ? stk(M.bigUp.c, M.bigUp.n, M.bigUp.r) : null, M.bigDn ? stk(M.bigDn.c, M.bigDn.n, M.bigDn.r) : null) : null,
    M.tvTop.length ? line(kk('거래대금 상위'), ...M.tvTop.map(x => stk(x.c, x.n, 0, eok(x.tv)))) : null,
    M.br && (M.br.u10 || M.br.d10) ? sub(`10% 넘게 오른 종목 ${NF0.format(M.br.u10)} · 내린 종목 ${NF0.format(M.br.d10)}`) : null);
}
function secFlows(M) {
  if (!M.flows) return sec('수급', later(D.flows ? '계산하는 중…' : '수급 파일을 받는 중…'));
  const F = M.flows, who = ['외국인', '기관', '개인'];
  return sec('수급 (추정)',
    line(...join(F.all.map((v, i) => h('span', { class: 'sm-nv' }, h('span', { class: 'sm-nm', text: who[i] }), h('b', { class: 'sm-n ' + cls(v, 0), text: amt(v) }))))),
    F.bot && F.bot.n ? line(kk('외국인 순매도 1위'), stk(F.bot.c, F.bot.n, F.bot.v, amt(F.bot.v))) : null,
    F.top && F.top.n ? line(kk('외국인 순매수 1위'), stk(F.top.c, F.top.n, F.top.v, amt(F.top.v))) : null,
    sub(`${F.today ? '오늘' : dayShort(F.date)} · 코스피 · 코스닥 합 · 종목별 순매수 주식 수 × 종가를 더한 값이에요` + (F.today ? '' : ' · 매일 장 마감 뒤 새로 받아요')));
}
function secMacro(M) {
  if (!LIVE && !M.us10 && !M.us) return sec('환율 · 금리 · 해외', snapNote('금리 · 해외 지수'));
  if (!M.fx && !M.us && !M.us10) return sec('환율 · 금리 · 해외', later(M.macroFail ? '불러오지 못했어요 · 다음 갱신 때 다시 받아요' : '받는 중…'));
  const rate = (name, x) => h('span', { class: 'sm-nv' }, h('span', { class: 'sm-nm', text: name }), h('span', { class: 'sm-v', text: (+x.value).toFixed(2) + '%' }), h('b', { class: 'sm-n ' + cls(bpOf(x), 1), text: sg(rnd(bpOf(x), 1)) + Math.abs(bpOf(x)).toFixed(1) + 'bp' }));
  const r = [M.us10 && rate('미 국채 10년', M.us10), M.kr3 && rate('국고채 3년', M.kr3)].filter(Boolean);
  return palW(sec('환율 · 금리 · 해외',
    M.fx ? line(h('span', { class: 'sm-nv' }, h('span', { class: 'sm-nm', text: '원/달러' }), h('span', { class: 'sm-v', text: NF1.format(+M.fx.value) }), h('b', { class: 'sm-n ' + cls(+M.fx.change, 1), text: fxChg(M.fx) }))) : null,
    r.length ? line(...join(r)) : null,
    M.us ? line(kk(M.us.label), ...join(M.us.items.map(x => nv(shortUS(x.name), x.r)))) : null,
    M.wti ? line(nv('WTI', +M.wti.ratio)) : null,
    sub([M.fx ? '원/달러는 오르면 원화 약세' : null, M.us && M.us.delayed ? '미국 선물 10분 지연' : null, r.length ? '금리 변화는 bp(0.01%p)' : null].filter(Boolean).join(' · '))));
}
function secNews(M) {
  if (!LIVE) return sec('공시 · 뉴스', snapNote('공시 · 뉴스'));
  const d = M.disc, n = M.news;
  const src = n ? ({ einfomax: '연합인포맥스', hankyung: '한국경제', mk: '매일경제' }[n.src] || '') : '';
  const tt = n ? (String(n.t).slice(0, 10) === kstOf(nowMs()).day ? String(n.t).slice(11, 16) : dayShort(n.t)) : '';
  return sec('공시 · 뉴스',
    d ? line(kk(d.today ? '오늘 공시' : `${dayShort(d.date)} 공시`), h('b', { class: 'sm-v', text: `${NF0.format(d.total)}건` }), h('span', { class: 'sm-nm', text: `실적 ${d.by.실적} · 주요 ${d.by.주요}` })) : null,
    d && d.pick ? h('p', { class: 'sm-l sm-one' }, kk(d.pick.nm), link('https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + d.pick.r, d.pick.t, `${d.pick.nm} · ${d.pick.t} — DART, 새 탭에서 열려요`)) : null,
    n ? h('p', { class: 'sm-l sm-one' }, kk(`${tt} ${src}`), link(n.url, n.title, `${n.title} — ${src}, 새 탭에서 열려요`)) : null,
    !d && !n ? later(D.news.fail ? '뉴스를 불러오지 못했어요' : '받는 중…') : null);
}
// a section of 해외 · 지표 values (환율 · 금리 · 해외 — the 지표 tab's numbers): that side's 등락 colours
function palW(el) { if (el) el.classList.add('pal-w'); return el; }
const DETAIL = { flow: secFlow, sector: secSector, movers: secMovers, flows: secFlows, macro: secMacro, news: secNews };
const ORDER = { pre: ['macro', 'flow', 'sector', 'flows', 'movers', 'news'], open: ['flow', 'sector', 'movers', 'flows', 'macro', 'news'], after: ['flow', 'sector', 'movers', 'flows', 'macro', 'news'], closed: ['flow', 'sector', 'movers', 'flows', 'macro', 'news'] };
const fullBody = M => [h('p', { class: 'sm-when', text: M.when }), facts(M), ...ORDER[M.ph].map(k => DETAIL[k](M)).filter(Boolean)];

/* ───────── 글로 복사 — 카톡 등에 붙여 넣는 평문 ───────── */
function plain(M) {
  const L = [`판세 · 오늘 시장 요약 (${M.pill} · ${M.when})`];
  if (M.headline) L.push(M.headline);
  if (M.idx.length) L.push(M.idx.map(x => `${x.name} ${NF2.format(x.v)} (${pct(x.r)})`).join(' · '));
  if (M.br) L.push(`상승 ${NF0.format(M.br.up)} · 하락 ${NF0.format(M.br.dn)} — ${M.br.say}` + (M.br.lu || M.br.ld ? ` · 상한가 ${M.br.lu} · 하한가 ${M.br.ld}` : ''));
  if (M.indUp.length || M.indDn.length) L.push('업종: ' + [...M.indUp, ...M.indDn].map(x => `${x.name} ${pct(x.r)}`).join(' · '));
  if (M.flows) L.push(`수급(${M.flows.today ? '오늘' : dayShort(M.flows.date)}, 추정): 외국인 ${amt(M.flows.all[0])} · 기관 ${amt(M.flows.all[1])} · 개인 ${amt(M.flows.all[2])}`);
  if (M.fx) L.push(`원/달러 ${NF1.format(+M.fx.value)}원 (${fxChg(M.fx)})` + (M.us ? ` · ${M.us.label} ` + M.us.items.slice(0, 2).map(x => `${shortUS(x.name)} ${pct(x.r)}`).join(' · ') : ''));
  L.push('출처: 네이버 증권 외 · panse.pages.dev · 투자 판단의 근거로 쓰지 마세요.');
  return L.join('\n');
}
async function copyText(text) {
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* the fallback below */ }
  const ta = h('textarea', { class: 'sr', readonly: true, 'aria-hidden': 'true' }); ta.value = text;
  document.body.append(ta); ta.select();
  let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

/* ───────── 카드 ───────── */
let host = null, P = null, open = false;
let mv = null, tOut = 0, tIn = 0, hold = 0, pending = false;
const reduced = () => motion() === 'reduced';
const moving = () => !!mv || !!tOut || !!hold;
function place() {
  const side = document.querySelector('main.layout > .side'), lay = document.querySelector('main.layout'), news = document.getElementById('news');
  if (!side || !lay) return;
  if (phoneMQ.matches) { if (host.parentNode !== lay || host.nextSibling !== news) lay.insertBefore(host, news || null); }   // 지도 다음 · 뉴스 앞
  else if (host.parentNode !== side || side.firstElementChild !== host) side.insertBefore(host, side.firstChild);           // 옆 칸 맨 앞
}
function aria() {
  const say = open ? '오늘 시장 요약 접기' : '오늘 시장 요약 자세히';
  P.tog.setAttribute('aria-expanded', String(open)); P.tog.setAttribute('aria-label', say); P.tog.title = open ? '접기' : '자세히';
}
// 글자 (§6-4): out = 100ms 나감(위로 4px; 짧은 띠는 흐림 2px도), in = 'sm-go'를 붙이는 때부터 --c-fast 들어옴(아래에서 4px)
const textOut = el => { el.classList.remove('sm-in', 'sm-go'); el.classList.add('sm-out'); };
const textIn = (el, delay) => { el.classList.remove('sm-out', 'sm-go'); el.classList.add('sm-in'); clearTimeout(tIn); tIn = setTimeout(() => el.classList.add('sm-go'), delay); };
const textClear = (...els) => els.forEach(el => { el.classList.remove('sm-in', 'sm-go', 'sm-out', 'sm-abs', 'sm-stag'); for (const c of el.querySelectorAll('[style*="--d"]')) c.style.removeProperty('--d'); });
// 자리가 바뀌는 순간(펼칠 땐 처음, 접을 땐 끝) 스크롤 고정(앵커)이 화면을 밀지 않게
function noAnchor(fn) { document.documentElement.classList.add('sm-noanchor'); fn(); requestAnimationFrame(() => document.documentElement.classList.remove('sm-noanchor')); }

/* 펼침 · 접힘 (design-references-full §7 P8 ⓐ · design.md §7): 카드 바탕 판(.sm-skin)만 스프링으로 자라고 줄어요. 아래 내용(뉴스 카드 ·
   옆 카드 · 출처 줄)은 **한 번에** 새 자리로 — 펼칠 땐 처음에, 접을 땐 판이 다 줄어든 뒤에 — 그래서 판이 아래 내용과 겹치지 않고, 레이아웃은
   한 번만 바뀌어요(news.js refit도 한 번). 안 글자는 판이 25% 넘게 자라고 띠 글자가 나간 뒤(160ms) 들어와요. 길이는 크기 차이에 비례해
   자른 스프링: 600px를 1로 0.75~1.35배(강성 ÷ 배², 감쇠 ÷ 배 — 감쇠비 · 넘침은 그대로). */
function springFor(name, D) {
  const pr = KH.spring && typeof KH.spring.params === 'function' ? KH.spring.params(name) : null;
  if (!pr || !(pr.k > 0)) return { name };
  const f = Math.min(1.35, Math.max(0.75, Math.abs(D) / 600));
  return { k: pr.k / (f * f), c: pr.c / f };
}
function run(sp, frame, commit) {
  let done = false;
  const me = {};
  const finish = () => {
    if (done) return; done = true;
    if (me.h) me.h.stop();
    if (mv === me) mv = null;
    commit();
    if (pending) { pending = false; render(true); }
  };
  me.finish = finish; mv = me;
  frame(0);                                                            // 첫 그림부터 판 높이 · clip이 맞게(한 프레임도 빈 카드가 보이지 않게)
  if (!KH.spring || reduced()) { frame(1); finish(); return; }
  me.h = KH.spring.animate(Object.assign({ from: 0, to: 1, onUpdate: v => { if (!done) frame(v); }, onRest: finish }, sp));
}
// P3: 순차 등장은 이 세션에서 처음 펼칠 때 한 번만(화려하게), 앞이 길고 뒤로 갈수록 짧게 40 → 30 → 20ms, 전체 300ms 안. 다시 펼치면 함께.
function stagger(full) {
  let first = false;
  try { first = motion() === 'fancy' && !sessionStorage.getItem('khm.sm.stag'); if (first) sessionStorage.setItem('khm.sm.stag', '1'); } catch (e) { first = false; }
  if (!first) return;
  const kids = [...P.fbody.children, P.foot], gaps = [40, 30];
  let d = 0;
  kids.forEach((el, i) => { if (i) d = Math.min(300, d + (gaps[i - 1] || 20)); el.style.setProperty('--d', d + 'ms'); });
  full.classList.add('sm-stag');
}
function setOpen(want, focusTop, waited) {
  if (hold || want === open) return;
  // 처음 펼칠 때 표 원천이 아직 오는 중이면 꺾쇠만 먼저 돌리고 잠깐(≤ 450ms) 기다려요 — 받는 중 줄로 펼쳤다가 값이 와서 또 자라면
  // 아래 내용이 두 번 밀리니까(P8 ⓐ "한 번에"). 넘으면 그대로 펼쳐요
  if (want && LIVE && !waited) {
    warm();
    const wait = TABLE.map(k => D[k].p).filter(Boolean);
    if (wait.length) {
      P.tog.setAttribute('aria-expanded', 'true');
      let gone = false;
      const go = () => { if (gone) return; gone = true; clearTimeout(hold); hold = 0; put(P.fbody, fullBody(lastM = model())); lastDraw = Date.now(); setOpen(true, focusTop, true); };
      hold = setTimeout(go, 450);
      Promise.all(wait).then(go);
      return;
    }
  }
  if (mv) mv.finish();                                                 // 움직이던 것은 끝 상태로
  if (tOut) { clearTimeout(tOut); tOut = 0; textClear(P.full); P.grow.style.height = ''; }   // 접힐 때 글자만 나가던 중이면 펼친 그대로
  open = want; aria();
  const { grow, band: bd, full, fbody, skin } = P;
  clearTimeout(tIn);
  if (open) {
    if (!fbody.firstChild || Date.now() - lastDraw > 15000) put(fbody, fullBody(lastM = model()));   // 보통은 render가 미리 그려 둔 표 그대로
    if (reduced()) { noAnchor(() => { bd.hidden = true; full.hidden = false; textClear(bd, full); }); return; }
    const H0 = host.offsetHeight;
    let H1 = H0;
    noAnchor(() => {                                                   // 아래 내용은 여기서 한 번에 새 자리로
      bd.classList.add('sm-abs'); textOut(bd);                         // 띠는 흐름에서 빠져 그 자리에서 나가고
      full.hidden = false; full.classList.add('sm-in'); stagger(full);
      H1 = host.offsetHeight;
    });
    const D = H1 - H0, t0 = performance.now();
    let lastP = 0, shown = false;
    const showIn = () => { if (!shown) { shown = true; full.classList.add('sm-go'); } };
    tIn = setTimeout(() => { if (lastP >= 0.25) showIn(); }, TXT_OUT + TXT_GAP);
    host.classList.add('sm-anim');
    run(springFor('open', D), p => {
      lastP = p;
      skin.style.height = (H0 + p * D) + 'px';
      full.style.clipPath = `inset(0 0 ${Math.max(0, (1 - p) * D).toFixed(2)}px 0)`;
      if (p >= 0.25 && performance.now() - t0 >= TXT_OUT + TXT_GAP) showIn();
    }, () => {
      showIn();
      host.classList.remove('sm-anim'); skin.style.height = ''; full.style.clipPath = ''; bd.hidden = true;
      setTimeout(() => { if (open && !mv) textClear(bd, full); }, 400);   // 순차 등장이 다 들어온 뒤에 표시를 걷어요
    });
    return;
  }
  const after = () => {
    if (focusTop) P.tog.focus({ preventScroll: true });
    const r = host.getBoundingClientRect();
    if (focusTop && r.top < 0) host.scrollIntoView({ block: 'start', behavior: reduced() ? 'auto' : 'smooth' });
  };
  drawBand(lastM || model());
  if (reduced()) { noAnchor(() => { full.hidden = true; bd.hidden = false; textClear(bd, full); }); after(); return; }
  if (focusTop) P.tog.focus({ preventScroll: true });
  textClear(full); full.classList.remove('sm-stag');
  grow.style.height = grow.getBoundingClientRect().height + 'px';      // 자리는 그대로 두고
  textOut(full);                                                       // 닫힐 땐 안 글자가 다 함께 먼저 나가요(P3 ③)
  tOut = setTimeout(() => {
    tOut = 0;
    const H1 = host.offsetHeight, fullH = full.offsetHeight;
    bd.hidden = false; bd.classList.add('sm-abs');
    const D = fullH - bd.offsetHeight;
    full.style.visibility = 'hidden';                                  // 글자는 이미 나갔어요 — 큰 면을 프레임마다 다시 그리지 않게
    textIn(bd, TXT_GAP);
    host.classList.add('sm-anim');
    run(springFor('close', D), p => { skin.style.height = (H1 - p * D) + 'px'; }, () => {
      noAnchor(() => {                                                 // 판이 다 줄어든 뒤 아래 내용이 한 번에 올라와요
        host.classList.remove('sm-anim'); skin.style.height = ''; grow.style.height = ''; full.style.visibility = ''; full.hidden = true; textClear(bd, full);
      });
      after();
    });
  }, TXT_OUT);
}

/* 글로 복사 (P11): 키 크기는 그대로(글자 상자 = 가장 긴 글자), 아이콘이 복사 → 체크로 교차(살짝 돌며 .5 → 1, `fade`) + 글자 바꿈(§6-4),
   --c-dwell 뒤 처음으로. 클립보드는 사람이 누른 것(isTrusted)만. 완료 = 앰버 ✓ · 글자(design.md §2), 실패 = ! + 글자 */
const ICON = {
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M15 9V6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H9"/>',
  done: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  fail: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.4v.1"/>',
};
function copyKey() {
  const icons = Object.entries(ICON).map(([k, d]) => { const s = svgOf(d, 16); s.classList.add('sm-i', 'sm-i-' + k); return s; });
  const says = { idle: '글로 복사', done: '복사했어요', fail: '복사 못 했어요' };
  const labels = Object.entries(says).map(([k, t]) => h('span', { class: 'sm-kl' + (k === 'idle' ? ' on' : ''), 'data-l': k, 'aria-hidden': k === 'idle' ? null : 'true', text: t }));
  const b = h('button', { type: 'button', class: 'sm-copy', 'data-st': 'idle', 'aria-label': says.idle }, h('span', { class: 'sm-ci', 'aria-hidden': 'true' }, icons), h('span', { class: 'sm-kls' }, labels));
  let back = 0;
  const set = st => {
    b.dataset.st = st; b.setAttribute('aria-label', says[st]);
    for (const l of labels) { const on = l.dataset.l === st; l.classList.toggle('out', !on && l.classList.contains('on')); l.classList.toggle('on', on); l.toggleAttribute('aria-hidden', !on); }
  };
  b.addEventListener('click', async e => {
    if (!e.isTrusted) return;                                          // 보여 주기 · 스크립트 클릭은 클립보드를 건드리지 않아요
    const ok = await copyText(plain(model()));
    set(ok ? 'done' : 'fail');
    if (typeof UI.live === 'function') UI.live(ok ? '요약을 글로 복사했어요.' : '복사하지 못했어요.');
    clearTimeout(back);
    back = setTimeout(() => b.isConnected && set('idle'), (typeof UI.ms === 'function' && UI.ms('--c-dwell')) || 1120);
  });
  return b;
}

function mount() {
  host = h('section', { class: 'card msum', id: 'summary', 'aria-labelledby': 'sm-h' });
  const pill = h('span', { class: 'sm-pill' });
  const hl = h('p', { class: 'sm-hl' });
  const tog = h('button', { type: 'button', class: 'sm-tog', 'aria-controls': 'sm-more' }, chev());
  tog.addEventListener('click', () => setOpen(!open));
  for (const ev of ['pointerenter', 'pointerdown', 'focus']) tog.addEventListener(ev, warm, { passive: true });   // 손이 가면 뉴스를 미리
  const bd = h('div', { class: 'sm-band' });
  const fbody = h('div', { class: 'sm-fbody' });
  const fold = h('button', { type: 'button', class: 'sm-fold', 'aria-controls': 'sm-more' }, h('span', { text: '접기' }), chev());
  fold.addEventListener('click', () => setOpen(false, true));
  const foot = h('div', { class: 'sm-df' }, copyKey(), h('span', { class: 'sm-sub', text: '카톡 등에 붙여 넣을 수 있는 글이에요' }), fold);
  const full = h('div', { class: 'sm-full', id: 'sm-more', hidden: true }, fbody, foot);
  const grow = h('div', { class: 'sm-grow' }, bd, full);
  const skin = h('div', { class: 'sm-skin', 'aria-hidden': 'true' });
  put(host, skin, h('h2', { class: 'sr', id: 'sm-h', text: '오늘 시장 요약' }), h('div', { class: 'sm-hd' }, pill, hl, tog), grow);
  P = { pill, hl, tog, band: bd, full, fbody, foot, grow, skin, regions: [fbody] };
  aria();
  place();
  phoneMQ.addEventListener('change', () => { place(); render(true); });
}

/* ───────── 그리기 · 갱신 ───────── */
let visible = !('IntersectionObserver' in window), timer = 0, lastDraw = 0, lastM = null;
function swapText(el, text) {
  if (el.textContent === text) return;
  if (typeof UI.swap === 'function' && el.textContent) UI.swap(el, text); else el.textContent = text;
}
function render(now) {
  if (!P) return;
  if (moving()) { pending = true; return; }
  // 읽는 중(펼친 덩어리 안에 포커스)이면 다음에 — 자세히 · 접기 · 복사 키는 그대로라 상관없어요
  if (!now && P.regions.some(r => r.contains(document.activeElement))) { schedule(); return; }
  const M = lastM = model();
  lastDraw = Date.now();
  swapText(P.pill, M.pill);
  P.pill.className = 'sm-pill sm-ph-' + (LIVE ? M.ph : 'snap');
  P.pill.title = M.when;
  swapText(P.hl, M.headline || '오늘 시장');
  // 둘 다 그려 둬요 — 숨은 쪽(display:none)은 레이아웃 비용이 없고, 펼치거나 접는 순간 바로 쓸 수 있어요
  drawBand(M);
  put(P.fbody, fullBody(M));
}
// 장중에는 kh:data마다 숫자가 바뀌지만, 문장 · 순위는 15초에 한 번만 다시 써요(글자가 계속 흔들리지 않게)
// soon = 어느 원천이 처음 왔을 때(받는 중 → 값): 바로 그려요
let timerAt = 0;
function schedule(soon) {
  const gap = soon ? 0 : phase() === 'open' ? 15000 : 1500, wait = Math.max(120, gap - (Date.now() - lastDraw));
  if (timer) { if (Date.now() + wait >= timerAt) return; clearTimeout(timer); }
  timerAt = Date.now() + wait;
  timer = setTimeout(() => { timer = 0; if (!document.hidden) render(false); }, wait);
}

mount();
if (!visible) new IntersectionObserver(es => { const v = es[es.length - 1].isIntersecting; if (v && !visible) { visible = true; refreshAll(false); schedule(); } else visible = v; }, { rootMargin: '300px' }).observe(host);
for (const ev of ['kh:data', 'kh:basis', 'kh:palette', 'kh:theme', 'kh:watch']) document.addEventListener(ev, () => schedule());
document.addEventListener('kh:refresh', () => { refreshAll(true); schedule(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && visible) { refreshAll(false); schedule(); } });
// 30초마다: 받을 때가 된 원천 · 공시 모듈의 새 목록 · 기준 시각 글자
setInterval(() => { if (!document.hidden && visible) { refreshAll(false); schedule(); } }, 30000);
if (visible) refreshAll(false);
render(true);
window.KHSummary = { phase, model, plain, isOpen: () => open, moving, open: () => setOpen(true), close: () => setOpen(false), refresh: () => { refreshAll(true); render(true); } };
})();
