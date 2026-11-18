// 컨센서스 스냅숏 — 개인 사이트 「왕이 될 상」용 비공개 보관 (AGENTS §3-41)
//
//   쌓기   평일 16:10~16:59 KST cron에서 하루 한 번: 원격 저장소 data/snapshot.json으로 시가총액 상위 100 보통주를 고르고,
//          종목마다 네이버 m.stock `finance/annual` · `finance/quarter`의 추정(E) 열과 `integration`의 consensusInfo(목표주가 평균 ·
//          투자의견 평균 · 기준일) · 추정 EPS · 추정 PER를 그대로 모아 KV REPLAY `cons:YYYYMMDD`(만료 없음)에 써요. 날짜는 받은
//          날(KST)이에요. `cons:days`(최신순 날짜 목록), `cons:done`(오늘 끝남), `cons:status`(마지막 결과), `cons:lock`(10분).
//          화면 요청은 네이버를 부르지 않아요 — 원천 호출은 하루 약 301번(스냅숏 1 + 100 × 3), 동시에 6개까지.
//   읽기   공개하지 않아요. 초대 토큰(머리 `X-Panse-Inv`, kis.js inviteOf)이 있어야 해요. 없거나 틀리면 403 {error:'forbidden'}.
//          GET /api/archive/consensus[?date=YYYY-MM-DD]  → 그날 스냅숏(없으면 가장 최근), 없으면 404
//          GET /api/archive/consensus/days               → {days, status}
//          GET /api/archive/consensus/probe?n=1..10      → dev 초대만 · KV에 쓰지 않고 지금 상위 n종목을 받아 봐요(배포 확인용)
//          모두 `cache-control: private, no-store`. Pages(_worker.js)를 거치지 않고 Worker 주소로 직접 불러요.
//   왜 비공개   증권사 컨센서스를 날마다 쌓은 기록은 지금 어디에도 공개되지 않은 새 자료예요. 공개 저장소 archive 브랜치에는
//          이미 공개된 판세 파일만 두고(scripts/archive_daily.py), 이건 §3-40 장중 수급처럼 초대한 사람만 읽어요.
//   한계   네이버는 올해(진행 중인 회계연도) 연간 추정과 다음 분기 추정 한두 칸만 줘요 — 내년 추정은 연초에 열이 바뀔 때부터.

import { inviteOf } from './kis.js';

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';   // index.js와 같은 값
const M_API = 'https://m.stock.naver.com/api';
const DEFAULT_ASSET_BASE = 'https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/';
export const CONS = { TOP_N: 100, CONC: 6, START: '1610', END: '1700', TIMEOUT: 8000, LOCK_TTL: 600, MAX_DAYS: 4000, PROBE_MAX: 10 };
// finance 행 제목 → 짧은 키. 단위는 네이버 그대로: 억원(rev · op · ni · cni) · %(opm · roe) · 원(eps · bps · dps) · 배(per · pbr)
export const ROWS = { '매출액': 'rev', '영업이익': 'op', '당기순이익': 'ni', '지배주주순이익': 'cni', '영업이익률': 'opm', 'ROE': 'roe',
  'EPS': 'eps', 'PER': 'per', 'BPS': 'bps', 'PBR': 'pbr', '주당배당금': 'dps' };

const pad = n => String(n).padStart(2, '0');
const kst = ms => new Date(ms + 9 * 3600e3);                       // read with getUTC* → KST wall clock
const ymd = d => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
const dash = s => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
const pn = v => {                                                  // "1,234" · "4.31배" · "45,565원" → number; 없음 → null
  if (v == null || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const m = String(v).replace(/,/g, '').match(/[-+]?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
};

export function dataBase(env) {
  if (env && env.DATA_BASE) return env.DATA_BASE.endsWith('/') ? env.DATA_BASE : env.DATA_BASE + '/';
  const a = (env && env.ASSET_BASE) || DEFAULT_ASSET_BASE;
  return a.replace(/web\/?$/, 'data/');
}

async function getJSON(url, ms = CONS.TIMEOUT) {
  const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' }, signal: AbortSignal.timeout(ms) });
  if (!r.ok) throw new Error(`${r.status} ${url.replace(/^https?:\/\/[^/]+/, '')}`);
  return r.json();
}

// 상위 n 보통주(코드 끝자리 0 — 우선주 제외) by cap, 두 시장 합쳐서
export function topCodes(snap, n = CONS.TOP_N) {
  const rows = (snap && Array.isArray(snap.stocks) ? snap.stocks : [])
    .filter(s => s && /^\d{5}0$/.test(String(s.c)) && Number(s.cap) > 0);
  rows.sort((a, b) => Number(b.cap) - Number(a.cap) || String(a.c).localeCompare(String(b.c)));
  return rows.slice(0, n).map(s => ({ c: String(s.c), n: s.n || '', m: s.m === 'Q' ? 'Q' : 'K' }));
}

// finance/{annual|quarter} 원본 → 추정 열만 [{k:'202612', rev, op, …}] (오래된 순)
export function estimateCols(raw) {
  const fi = (raw && raw.financeInfo) || {};
  const cols = (fi.trTitleList || []).filter(c => c && c.isConsensus === 'Y').map(c => String(c.key)).sort();
  if (!cols.length) return [];
  return cols.map(k => {
    const o = { k };
    for (const r of fi.rowList || []) {
      const key = ROWS[r && r.title];
      if (!key) continue;
      const x = r.columns && r.columns[k];
      const v = x ? pn(x.value) : null;
      if (v != null) o[key] = v;
    }
    return o;
  });
}

// integration 원본 → {tp, rec, cd, ceps, cper} (없는 값은 빼요)
export function consensusOf(raw) {
  const o = {};
  const ci = raw && raw.consensusInfo;
  if (ci) {
    const tp = pn(ci.priceTargetMean), rec = pn(ci.recommMean);
    if (tp != null) o.tp = tp;
    if (rec != null) o.rec = rec;
    if (ci.createDate) o.cd = String(ci.createDate).slice(0, 10);
  }
  for (const t of (raw && raw.totalInfos) || []) {
    if (t && t.code === 'cnsEps') { const v = pn(t.value); if (v != null) o.ceps = v; }
    if (t && t.code === 'cnsPer') { const v = pn(t.value); if (v != null) o.cper = v; }
  }
  return o;
}

async function oneStock(s) {
  const [a, q, g] = await Promise.allSettled([
    getJSON(`${M_API}/stock/${s.c}/finance/annual`),
    getJSON(`${M_API}/stock/${s.c}/finance/quarter`),
    getJSON(`${M_API}/stock/${s.c}/integration`),
  ]);
  const row = { n: s.n, m: s.m };
  if (a.status === 'fulfilled') row.a = estimateCols(a.value);
  if (q.status === 'fulfilled') row.q = estimateCols(q.value);
  if (g.status === 'fulfilled') Object.assign(row, consensusOf(g.value));
  const failed = [a, q, g].filter(x => x.status === 'rejected').length;
  return { row, failed, error: failed === 3 ? String(a.reason && a.reason.message || a.reason) : null };
}

async function pool(items, n, fn) {
  const out = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k], k); }
  }));
  return out;
}

// 상위 n종목을 지금 받아요. 쓰지는 않아요.
export async function collect(env, n = CONS.TOP_N, now = Date.now()) {
  const snap = await getJSON(dataBase(env) + 'snapshot.json', 15000);
  const list = topCodes(snap, n);
  if (!list.length) throw new Error('snapshot.json에 종목이 없어요');
  const got = await pool(list, CONS.CONC, oneStock);
  const c = {}, miss = [];
  let partial = 0;
  got.forEach((g, i) => {
    if (g.failed === 3) { miss.push(list[i].c); return; }
    if (g.failed) partial++;
    c[list[i].c] = g.row;
  });
  const k = kst(now);
  return {
    v: 1, asOf: dash(ymd(k)), at: `${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}`,
    src: '네이버 증권 (증권사 컨센서스)', capAsOf: snap && snap.asOf ? String(snap.asOf).slice(0, 10) : null,
    n: Object.keys(c).length, partial, miss,
    codes: list.map(x => x.c),                 // 시총 순위 순서(빠진 종목 포함) — `c`의 키 순서는 JSON이 숫자 코드를 앞으로 보내 순위가 아니에요
    c,
  };
}

async function setStatus(env, s) {
  try { await env.REPLAY.put('cons:status', JSON.stringify(s)); } catch (e) { /* status is best effort */ }
}

// cron이 매분 불러요. 할 때가 아니면 KV도 건드리지 않아요. 절대 던지지 않아요.
export async function consensusTick(env, now = Date.now()) {
  try {
    if (!env || !env.REPLAY || env.CONS === 'off') return 'off';
    const k = kst(now), wd = k.getUTCDay(), hm = pad(k.getUTCHours()) + pad(k.getUTCMinutes());
    if (wd < 1 || wd > 5 || hm < CONS.START || hm >= CONS.END) return 'not-due';
    const day = ymd(k);
    if ((await env.REPLAY.get('cons:done')) === day) return 'done';
    if (await env.REPLAY.get('cons:lock')) return 'locked';
    await env.REPLAY.put('cons:lock', String(now), { expirationTtl: CONS.LOCK_TTL });
    let snap;
    try {
      snap = await collect(env, CONS.TOP_N, now);
    } catch (e) {
      await setStatus(env, { at: now, day: dash(day), result: 'error', error: String(e && e.message || e).slice(0, 300) });
      console.error('consensus', e && e.message);
      return 'error';
    }
    if (snap.n < CONS.TOP_N / 2) {          // 절반도 못 받으면 쓰지 않고 10분 뒤(잠금이 풀리면) 다시
      await setStatus(env, { at: now, day: dash(day), result: 'error', error: `only ${snap.n} stocks`, miss: snap.miss.length });
      console.error('consensus: only', snap.n, 'stocks');
      return 'error';
    }
    await env.REPLAY.put('cons:' + day, JSON.stringify(snap));
    let days = [];
    try { days = (await env.REPLAY.get('cons:days', 'json')) || []; } catch (e) { days = []; }
    if (!Array.isArray(days)) days = [];
    days = [snap.asOf, ...days.filter(d => d !== snap.asOf)].slice(0, CONS.MAX_DAYS);
    await env.REPLAY.put('cons:days', JSON.stringify(days));
    await env.REPLAY.put('cons:done', day);
    await setStatus(env, { at: now, day: snap.asOf, result: 'wrote', n: snap.n, partial: snap.partial, miss: snap.miss.length });
    return 'wrote';
  } catch (e) {
    console.error('consensus tick', e && e.message);
    return 'error';
  }
}

export async function consensusRoute(request, env, url) {
  const out = (b, s = 200) => new Response(typeof b === 'string' ? b : JSON.stringify(b), {
    status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'private, no-store' } });
  if (request.method !== 'GET') return out({ error: 'GET만 돼요' }, 405);
  const inv = await inviteOf(request, env);
  if (!inv) return out({ error: 'forbidden' }, 403);
  const sub = url.pathname.replace(/^\/api\/archive\/consensus\/?/, '');
  if (sub === 'days') {
    const [days, status] = await Promise.all([env.REPLAY.get('cons:days', 'json'), env.REPLAY.get('cons:status', 'json')]);
    return out({ days: Array.isArray(days) ? days : [], status: status || null });
  }
  if (sub === 'probe') {
    if (!inv.dev) return out({ error: 'forbidden' }, 403);
    const n = Math.max(1, Math.min(CONS.PROBE_MAX, parseInt(url.searchParams.get('n') || '3', 10) || 3));
    try { return out(await collect(env, n)); } catch (e) { return out({ error: String(e && e.message || e).slice(0, 300) }, 502); }
  }
  if (sub !== '') return out({ error: '없는 경로예요' }, 404);
  const d = url.searchParams.get('date');
  if (d != null && !/^\d{4}-\d{2}-\d{2}$/.test(d)) return out({ error: 'date는 YYYY-MM-DD여야 해요' }, 400);
  let day = d ? d.replace(/-/g, '') : null;
  if (!day) {
    const days = await env.REPLAY.get('cons:days', 'json');
    day = Array.isArray(days) && days.length ? String(days[0]).replace(/-/g, '') : null;
  }
  const body = day ? await env.REPLAY.get('cons:' + day) : null;
  if (!body) return out({ error: '그날 스냅숏이 없어요' }, 404);
  return out(body);
}
