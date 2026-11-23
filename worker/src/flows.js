// 장중 수급 순위 — Worker 쪽 (AGENTS §3-40, 사용자 2026-11-16 15:25 "장중 당일 개인 외국인 기관 수급 … 순매수 순매도 순위" ·
// 15:31 "나랑 가족만 볼수있도록" → 2026-11-22 15:18 "장중 수급 + 요약 버그"). 원천 실측 data/ENDPOINTS_KIS.md.
//
//   GET /api/flows/market            모두 — 네이버 m.stock `index/{KOSPI,KOSDAQ}/integration`의 dealTrendInfo(시장 전체 3주체, 억원)
//                                    → {asOf, date, K:{personal, foreign, institutional}|null, Q:{…}|null, stale?}. 엣지 캐시 평일
//                                    09:00~15:40 60초 · 그 밖 10분. 실패하면 KV `flows:mkt` 마지막 값 + stale:true, 없으면 503.
//   GET /api/flows/live              초대만 — 한국투자 가집계 순위 ①과 종목별 추정 ②의 최신 회차(아래 `kisflow:<날짜>`에서 읽기만,
//                                    KIS를 부르지 않아요). 오늘 값이 아직 없으면 slot:null · 빈 rank · est.
//   GET /api/flows/live/stock/{code} 초대만 — ②를 그때 불러 {code, date, slots:[{no, t, f, i}]}(오래된 순). KV 사본 3분.
//   가족 경로는 모두 `cache-control: private, no-store`, 초대가 없거나 틀리면 403 {error:'forbidden'}.
//
// 받는 때 (scheduled → flowsTick, 평일 매분 cron 안에서): 입력 회차 1 = 09:30(외국인만) · 2 = 10:00 · 3 = 11:20 · 4 = 13:20 ·
//   5 = 14:30. 회차는 시계만 믿지 않고 삼성전자(005930) ②의 output2 회차(bsop_hour_gb)로 알아요 — 입력 시각 + 4분부터 8분마다
//   확인(+4 · +12 · +20 …), 15:40 · 15:48 · 15:56에 마지막 확인. 새 회차가 보이면 ① 8번(코스피 · 코스닥 × 외국인 · 기관 ×
//   순매수 · 순매도, 금액 정렬; 1회차는 외국인 4번만)을 받아 순위를 곧바로 쓰고, ②를 유니버스 상위 300 × 2에 몇 분에 나눠
//   (한 번에 KIS 150번까지, 초당 10번 안, 동시 3) 받아 다 모이면 est로 바꿔요. 진행은 같은 KV 키 하나에 두어요.
//   시계보다 앞선 회차(예: 09:34에 5회차 = 전날 남은 값)는 오늘 값으로 보지 않아요. 휴장: 네이버 시세의 오늘 체결이 없거나
//   (10:30 뒤에야 판단 — 수능 날은 10:00에 열어요) 첫 회차 ①이 모두 비면 그날은 멈춰요.
//   한도: KIS 하루 3,600번(예약) + 400번(종목 경로) = 4,000번 안, 평소 약 3,050번. KV 쓰기 하루 약 30번(회차마다 5번 안팎).
//   토큰은 kis.js가 KV `kis:tok`에 두고 다시 써요(하루 1번 발급).
//
// 키와 접근 토큰은 응답 · KV · 로그 어디에도 남지 않아요 — 남기는 오류 글자는 모두 kisScrub()을 거쳐요.

import { kisGet, kisReady, kisScrub, inviteOf } from './kis.js';

export const KF = {
  ROUNDS: [null, { t: '09:30', m: 570 }, { t: '10:00', m: 600 }, { t: '11:20', m: 680 }, { t: '13:20', m: 800 }, { t: '14:30', m: 870 }],
  FIRST: 4, EVERY: 8, EARLY: 10,             // 입력 시각 + 4분에 첫 확인, 그 뒤 8분마다; 시계보다 10분까지 이른 회차는 받아요
  START_M: 574, FINAL_M: 940, PROBE_END_M: 960, JOB_END_M: 989,   // 09:34 · 15:40 · 16:00 · 16:29 (KST 분)
  OPEN_DECIDE_M: 630,                        // 10:30 전에는 "오늘 체결 없음"을 휴장으로 보지 않아요
  CALLS_PER_RUN: 150, GAP_MS: 110, CONC: 3, RUN_MS: 45000,
  DAY_MAX: 3600, OD_MAX: 400, TTL_S: 3 * 86400, MIN_EST: 0.5,
  STOCK_FRESH_MS: 180e3, STOCK_TTL_S: 86400, OD_COOL_MS: 60e3,
  COOL_AUTH_MS: 30 * 60e3, COOL_DEAD_MS: 15 * 60e3, ERR_EVERY_MS: 15 * 60e3, JOB_MAX_MS: 50 * 60e3,
  MKT_TIMEOUT: 6000, MKT_PUT_MS: 15 * 60e3, MKT_TTL_S: 3 * 86400,
  PROBE: '005930',
};
const R1 = '/uapi/domestic-stock/v1/quotations/foreign-institution-total', TR1 = 'FHPTJ04400000';
const R2 = '/uapi/domestic-stock/v1/quotations/investor-trend-estimate', TR2 = 'HHPTJ04160200';
const MK = { K: '0001', Q: '1001' }, WHO = { f: '1', i: '2' }, SIDE = { buy: '0', sell: '1' };
const ORIGIN = 'https://panse.pages.dev';
const SRC = '한국투자증권 가집계';
const CODE_RE = /^[0-9A-Z]{6}$/;           // 유니버스에 0126Z0 같은 영문 섞인 코드가 있어요

const pad = n => String(n).padStart(2, '0');
const kstOf = ms => {
  const d = new Date(ms + 9 * 3600e3);
  const h = d.getUTCHours(), mi = d.getUTCMinutes();
  return { day: `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`, mins: h * 60 + mi, wd: d.getUTCDay(), hm: `${pad(h)}:${pad(mi)}` };
};
const dash = s => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
const perf = () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
const sleep = ms => new Promise(r => setTimeout(r, ms));
// KIS 숫자는 글자예요("-00000000002132000", "+13", "1.23") → 숫자, 없음 · 빈 글자 → null
export const kn = v => {
  if (v == null) return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const s = String(v).replace(/,/g, '').trim();
  if (!/^[-+]?\d+(\.\d+)?$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};
const r1 = x => Math.round(x * 10) / 10;

// 회차 계산 (KST 분): 지금 확인할 회차 · 시계로 있을 수 있는 가장 늦은 회차
export const expectedRound = mins => { let r = 0; for (let i = 1; i <= 5; i++) if (KF.ROUNDS[i].m + KF.FIRST <= mins) r = i; return r; };
export const clockMax = mins => { let r = 0; for (let i = 1; i <= 5; i++) if (KF.ROUNDS[i].m - KF.EARLY <= mins) r = i; return r; };
const label = no => (no >= 1 && no <= 5 ? KF.ROUNDS[no].t : null);

// ② 응답 → {no, rows:[{no, f, i}]} (오래된 순). no = 가장 늦은 회차(bsop_hour_gb, 없으면 줄 수)
export function parseEst(j) {
  const out = j && Array.isArray(j.output2) ? j.output2 : [];
  const rows = [];
  out.forEach((x, k) => {
    if (!x || typeof x !== 'object') return;
    let no = kn(x.bsop_hour_gb);
    if (!(no >= 1 && no <= 5)) no = out.length - k;       // 최신 회차가 먼저
    const f = kn(x.frgn_fake_ntby_qty), i = kn(x.orgn_fake_ntby_qty);
    if (no >= 1 && no <= 5 && (f != null || i != null) && !rows.some(r => r.no === no)) rows.push({ no, f: f || 0, i: i || 0 });
  });
  rows.sort((a, b) => a.no - b.no);
  return { no: rows.length ? rows[rows.length - 1].no : 0, rows };
}
// ① 응답 → 행 [코드, 이름, 금액(억원 소수 1), 수량(주), 현재가, 등락률]
export function parseRank(j, who) {
  const out = j && Array.isArray(j.output) ? j.output : [];
  const amtK = who === 'f' ? 'frgn_ntby_tr_pbmn' : 'orgn_ntby_tr_pbmn', qtyK = who === 'f' ? 'frgn_ntby_qty' : 'orgn_ntby_qty';
  const rows = [];
  for (const x of out) {
    if (!x || typeof x !== 'object') continue;
    const c = String(x.mksc_shrn_iscd || '').trim();
    if (!CODE_RE.test(c)) continue;
    const amt = kn(x[amtK]), qty = kn(x[qtyK] != null ? x[qtyK] : x.ntby_qty);
    let ratio = kn(x.prdy_ctrt);
    const sg = String(x.prdy_vrss_sign || '');
    if (ratio != null) ratio = sg === '4' || sg === '5' ? -Math.abs(ratio) : sg === '1' || sg === '2' ? Math.abs(ratio) : ratio;
    rows.push([c, String(x.hts_kor_isnm || '').trim().slice(0, 40), amt == null ? null : r1(amt / 100), qty, kn(x.stck_prpr), ratio]);
  }
  return rows;
}
const rankKeys = no => {
  const ks = [];
  for (const m of ['K', 'Q']) for (const w of no === 1 ? ['f'] : ['f', 'i']) for (const s of ['buy', 'sell']) ks.push(`${m}.${w}.${s}`);
  return ks;
};
const emptyRank = () => ({ K: { f: { buy: [], sell: [] }, i: { buy: [], sell: [] } }, Q: { f: { buy: [], sell: [] }, i: { buy: [], sell: [] } } });

/* ───────── 그날 상태 (KV `kisflow:<YYYYMMDD>`, 3일) ───────── */
const sKey = day => `kisflow:${day}`;
let MEM = { day: '', st: null, probeAt: 0, open: null, unsaved: 0 };
let RUNNING = false;
let GATE_AT = 0;
const OD_MEM = new Map();   // code → 종목 경로 사본(이 isolate)
let OD_COOL = 0;
let MKT_MEM = null;
let CONF = { naver: null, codes: null };
export function configureFlows(c) { CONF = { ...CONF, ...c }; }
export function flowsResetMemory() { MEM = { day: '', st: null, probeAt: 0, open: null, unsaved: 0 }; RUNNING = false; GATE_AT = 0; OD_MEM.clear(); OD_COOL = 0; MKT_MEM = null; }

const blank = day => ({ v: 1, day, seq: 0, n: 0, no: 0, seen: 0, rankNo: 0, rankAt: null, rank: null, rnext: null, estNo: 0, est: null, estN: 0, estAt: null, job: null });
async function loadState(env, day) {
  let kv = null, bad = false;
  try { kv = await env.REPLAY.get(sKey(day), 'json'); } catch (e) { bad = true; }
  let st = kv && typeof kv === 'object' && kv.day === day ? kv : null;
  if (MEM.day === day && MEM.st && (!st || (MEM.st.seq || 0) > (st.seq || 0))) st = JSON.parse(JSON.stringify(MEM.st));   // KV는 다른 곳에 늦게 닿아요
  if (!st && bad) return null;          // 읽기가 실패했는데 아는 값도 없으면 덮어쓰지 않게 이번 분은 쉬어요
  st = st || blank(day);
  if (MEM.day === day && MEM.unsaved) st.n = (st.n || 0) + MEM.unsaved;   // 쓰지 않고 끝난 확인(같은 회차)도 하루 계수에 넣어요
  return st;
}
async function saveState(env, st) {
  st.seq = (st.seq || 0) + 1;
  MEM = { ...MEM, day: st.day, st: JSON.parse(JSON.stringify(st)), unsaved: 0 };
  try { await env.REPLAY.put(sKey(st.day), JSON.stringify(st), { expirationTtl: KF.TTL_S }); return true; }
  catch (e) { console.error('kisflow save', kisScrub(e && e.message, env)); return false; }
}
function noteErr(env, st, code, msg, now) {
  const m = kisScrub(msg || code, env);
  console.error(`kisflow ${st.day} ${code}: ${m}`);
  const prev = st.err;
  if (prev && prev.code === code && now - (prev.ms || 0) < KF.ERR_EVERY_MS) return false;
  st.err = { at: kstOf(now).hm, ms: now, code, msg: m.slice(0, 200) };
  return true;
}

/* ───────── KIS 부르기 (초당 10번 안 · 실행마다 150번 · 하루 상한) ───────── */
async function gate() {
  const t = perf(), at = Math.max(t, GATE_AT);
  GATE_AT = at + KF.GAP_MS;
  if (at > t) await sleep(at - t);
}
// 결과 kind: ok | empty-ok(ok) | rate | transient | perm | stop(토큰 · 키)
async function kisCall(env, path, tr, params) {
  await gate();
  try {
    const r = await kisGet(env, path, tr, params);
    if (r.status === 200 && r.j && String(r.j.rt_cd) === '0') return { kind: 'ok', j: r.j };
    if (/EGW00201/.test(r.code)) return { kind: 'rate', code: r.code, msg: r.msg };
    if (r.status >= 500 || !r.j) return { kind: 'transient', code: 'http' + r.status, msg: r.msg || r.text || '' };
    return { kind: 'perm', code: r.code || 'http' + r.status, msg: r.msg };
  } catch (e) {
    const m = String(e && e.message || e);
    if (/kis-token-cooldown/.test(m)) return { kind: 'stop', code: 'token-wait', msg: m };
    if (/kis-token|kis-no-key/.test(m)) return { kind: 'stop', code: /daycap/.test(m) ? 'token-daycap' : 'token', msg: m, cool: true };
    return { kind: 'transient', code: e && (e.name === 'AbortError' || e.name === 'TimeoutError') ? 'timeout' : 'network', msg: m };
  }
}
class Run {
  constructor(env, st, now) { this.env = env; this.st = st; this.now = now; this.left = KF.CALLS_PER_RUN; this.t0 = perf(); this.stop = null; this.ok = 0; this.calls = 0; this.dirty = false; }
  room() { return !this.stop && this.left > 0 && this.st.n < KF.DAY_MAX && perf() - this.t0 < KF.RUN_MS; }
  async call(path, tr, params) {
    if (!this.room()) return { kind: 'skip' };
    this.left--; this.st.n++; this.calls++; this.dirty = true;
    const r = await kisCall(this.env, path, tr, params);
    if (r.kind === 'ok') this.ok++;
    else if (r.kind === 'stop' || r.kind === 'rate') {
      if (!this.stop) this.stop = r.code;
      if (r.cool) this.st.cool = this.now + KF.COOL_AUTH_MS;
      noteErr(this.env, this.st, r.code, r.msg, this.now);
    } else if (r.kind === 'perm' || r.kind === 'transient') this.lastFail = r;
    return r;
  }
}

/* ① 순위: 회차 no의 빠진 목록만 받아요. 다 모이면 순위를 바꿔요. */
async function fetchRanks(run, no) {
  const st = run.st;
  if (!st.rnext || st.rnext.no !== no) st.rnext = { no, at: null, got: {} };
  const want = rankKeys(no).filter(k => !st.rnext.got[k]);
  for (const k of want) {
    if (!run.room()) break;
    const [m, w, s] = k.split('.');
    const r = await run.call(R1, TR1, { FID_COND_MRKT_DIV_CODE: 'V', FID_COND_SCR_DIV_CODE: '16449', FID_INPUT_ISCD: MK[m], FID_DIV_CLS_CODE: '1', FID_RANK_SORT_CLS_CODE: SIDE[s], FID_ETC_CLS_CODE: WHO[w] });
    if (r.kind === 'ok') st.rnext.got[k] = parseRank(r.j, w);
    else if (r.kind === 'perm' || r.kind === 'transient') noteErr(run.env, st, 'rank-' + r.code, r.msg, run.now);
  }
  if (rankKeys(no).every(k => st.rnext.got[k])) swapRank(st, run.now);
}
function swapRank(st, now) {
  const x = st.rnext;
  if (!x) return;
  const rank = emptyRank(), same = st.rank && st.rankNo === x.no;
  for (const k of rankKeys(x.no)) {                                // 같은 회차에서 못 받은 목록은 지난 값 그대로, 새 회차면 빈 채로
    const [m, w, s] = k.split('.');
    rank[m][w][s] = x.got[k] || (same && st.rank[m] && st.rank[m][w] && st.rank[m][w][s]) || [];
  }
  st.rank = rank; st.rankNo = x.no; st.rankAt = kstOf(now).hm; st.rnext = null;
}
// 그 회차 ① 목록을 모두 받았는데 모두 비었는지(첫 회차에서만 봐요 — 휴장)
function rankEmpty(st, no) {
  if (st.rnext && st.rnext.no === no) return rankKeys(no).every(k => st.rnext.got[k] && !st.rnext.got[k].length);
  if (st.rankNo !== no || !st.rank) return false;
  return rankKeys(no).every(k => { const [m, w, s] = k.split('.'); return !st.rank[m][w][s].length; });
}

/* ② 종목별 추정: 일을 이어서 해요 */
function newJob(no, codes, probe, final, now) {
  const job = { no, codes, next: 0, retry: [], phase: 0, got: {}, miss: 0, at: now, final: !!final };
  const row = probe && probe.rows.find(r => r.no === no);
  if (row && codes.includes(KF.PROBE)) job.got[KF.PROBE] = [row.f, row.i];
  return job;
}
async function workJob(run, mins) {
  const st = run.st, job = st.job;
  if (st.rnext) await fetchRanks(run, st.rnext.no);
  const cap = clockMax(mins);
  const take = () => {
    while (run.room()) {
      if (job.phase === 0) {
        if (job.next >= job.codes.length) { job.phase = 1; continue; }
        const c = job.codes[job.next++];
        if (job.got[c]) continue;
        return c;
      }
      if (!job.retry.length) return null;
      return job.retry.shift();
    }
    return null;
  };
  let tried = 0, good = 0;
  const one = async c => {
    const phase = job.phase;
    const r = await run.call(R2, TR2, { MKSC_SHRN_ISCD: c });
    tried++;
    if (r.kind === 'ok') {
      good++;
      const p = parseEst(r.j);
      if (p.no > cap) return;                                    // 전날 남은 값 — 오늘 것으로 보지 않아요
      if (p.no > st.seen) st.seen = p.no;
      const row = p.rows.find(x => x.no === job.no);
      if (row) job.got[c] = [row.f, row.i]; else job.miss++;
      return;
    }
    if (r.kind === 'perm') { job.miss++; return; }
    if (r.kind === 'transient' && phase === 1) { job.miss++; return; }
    if (!job.retry.includes(c)) job.retry.push(c);               // 잠깐 실패 · 한도 · 토큰 기다림 → 나중에 한 번 더
  };
  await Promise.all(Array.from({ length: KF.CONC }, async () => { for (let c = take(); c; c = take()) await one(c); }));
  if (tried >= 10 && !good && !run.stop) {                      // 모두 실패: 잠깐 쉬어요
    st.cool = run.now + KF.COOL_DEAD_MS;
    noteErr(run.env, st, 'est-dead', run.lastFail ? `${run.lastFail.code} ${run.lastFail.msg || ''}` : 'no answer', run.now);
  }
  const done = job.phase === 1 && !job.retry.length;
  const old = run.now - job.at > KF.JOB_MAX_MS;
  if (done || old || mins > KF.JOB_END_M) finishJob(run, old && !done ? 'job-timeout' : null);
}
function finishJob(run, why) {
  const st = run.st, job = st.job, n = Object.keys(job.got).length;
  if (n >= job.codes.length * KF.MIN_EST) { st.est = job.got; st.estNo = job.no; st.estN = n; st.estAt = kstOf(run.now).hm; }
  else noteErr(run.env, st, 'est-few', `${n}/${job.codes.length}${why ? ' ' + why : ''}`, run.now);
  if (st.rnext) swapRank(st, run.now);                          // 끝까지 못 받은 목록은 빈 채로
  if (job.final) st.final = 1;
  st.job = null;
  run.dirty = true;
}

async function naverOpen(day, mins) {
  if (!CONF.naver) return null;
  try {
    const j = await CONF.naver(`https://polling.finance.naver.com/api/realtime/domestic/stock/${KF.PROBE}`, 6000);
    const x = j && Array.isArray(j.datas) ? j.datas[0] : null;
    const at = x && String(x.localTradedAt || '');
    if (!at) return null;
    if (at.slice(0, 10) === dash(day)) return true;
    return mins >= KF.OPEN_DECIDE_M ? false : 'wait';          // 수능 · 첫 거래일은 10:00에 열어요
  } catch (e) { return null; }                                   // 네이버가 안 되면 판단하지 않고 KIS 쪽 규칙(시계 · 빈 ①)만
}

// 그날 마지막으로 받아들인 삼성전자 ② 줄 — 다음 날 네이버가 답하지 않을 때 "전날 값이 아직 남아 있는지" 비교해요
// (KV `kisflow:last` = {day, rows:[{no, f, i}]}, 30일, 회차마다 한 번)
const sameRows = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => x.no === b[i].no && x.f === b[i].f && x.i === b[i].i);
async function saveLast(env, day, p) {
  try { await env.REPLAY.put('kisflow:last', JSON.stringify({ day, rows: p.rows }), { expirationTtl: 30 * 86400 }); } catch (e) { /* 덤이에요 */ }
}
// 네이버로 오늘 체결을 확인하지 못했을 때, ② 줄이 오늘 것이라는 근거: 지난 거래일의 마지막 줄과 다르면 오늘 것.
// 비교할 것이 없으면 5회차(하루를 다 채운 전날 값과 모양이 같아요)만 받지 않아요.
async function todayEvidence(env, day, p) {
  let last = null;
  try { last = await env.REPLAY.get('kisflow:last', 'json'); } catch (e) { last = null; }
  if (last && last.day && last.day !== day && Array.isArray(last.rows)) return !sameRows(last.rows, p.rows);
  return p.no < 5;
}

async function universeCodes(env) {
  const c = CONF.codes ? await CONF.codes(env) : null;
  if (!Array.isArray(c) || c.length < 100) throw new Error('universe codes');
  return [...new Set(c.filter(x => CODE_RE.test(x)))];
}

// cron이 매분 불러요. 할 때가 아니면 KV · 네트워크를 건드리지 않아요. 절대 던지지 않아요.
export async function flowsTick(event, env) {
  try {
    if (!env || !env.REPLAY || env.KISFLOW === 'off' || !kisReady(env)) return 'off';
    const k = kstOf((event && event.scheduledTime) || Date.now());
    if (k.wd < 1 || k.wd > 5) return 'weekend';
    if (k.mins < KF.START_M || k.mins > KF.JOB_END_M) return 'not-due';
    if (RUNNING) return 'busy';
    RUNNING = true;
    try { return await tick(env, k); } finally { RUNNING = false; }
  } catch (e) {
    console.error('kisflow tick', kisScrub(e && e.message, env));
    return 'error';
  }
}

async function tick(env, k) {
  const now = Date.now();
  if (MEM.day !== k.day) MEM = { day: k.day, st: null, probeAt: 0, open: null, unsaved: 0 };
  const st = await loadState(env, k.day);
  if (!st) return 'kv-error';
  if (st.closed) return 'closed';
  if (st.cool && st.cool > now) return 'cool';
  if (st.n >= KF.DAY_MAX) return 'cap';
  const run = new Run(env, st, now);
  let res = 'idle';
  if (st.job) {
    await workJob(run, k.mins);
    res = st.job ? 'job' : 'job-done';
  } else {
    if (k.mins >= KF.PROBE_END_M) return 'idle';
    const final = k.mins >= KF.FINAL_M && !st.final;
    const r = expectedRound(k.mins);
    let due = false;
    if (st.seen > st.no) due = true;                                 // 지난 일 중에 더 새 회차를 봤어요
    else if (final) due = (k.mins - KF.FINAL_M) % KF.EVERY === 0 || (MEM.day === k.day && MEM.probeAt && now - MEM.probeAt >= 10 * 60e3);
    else if (r > st.no) {
      const d = k.mins - KF.ROUNDS[r].m;
      due = (d - KF.FIRST) % KF.EVERY === 0 || (MEM.day === k.day && MEM.probeAt > 0 && now - MEM.probeAt >= 10 * 60e3);
    }
    if (!due) return 'idle';
    if (!(MEM.day === k.day && MEM.open === true) && st.open !== true) {
      const o = await naverOpen(k.day, k.mins);
      if (o === false) { st.closed = 'naver'; await saveState(env, st); return 'closed'; }
      if (o === 'wait') { MEM.probeAt = now; return 'not-open-yet'; }
      if (o === true) { MEM.open = true; st.open = true; }
    }
    const openKnown = st.open === true || (MEM.day === k.day && MEM.open === true);
    MEM.probeAt = now;
    const pr = await run.call(R2, TR2, { MKSC_SHRN_ISCD: KF.PROBE });
    if (pr.kind !== 'ok') {
      if (pr.kind === 'perm' || pr.kind === 'transient') noteErr(env, st, 'probe-' + pr.code, pr.msg, now);
      if ((st.err && st.err.ms === now) || st.cool > now) { await saveState(env, st); return 'probe-failed'; }   // 오류 기록은 15분에 한 번만 써요
      return unsaved(run, 'probe-failed');
    }
    let p = parseEst(pr.j);
    if (p.no > clockMax(k.mins)) p = { no: 0, rows: [] };            // 시계보다 앞선 회차 = 전날 값
    while (p.rows.length && !p.rows[p.rows.length - 1].f && !p.rows[p.rows.length - 1].i) p.rows.pop();   // 삼성전자가 0 · 0 = 아직 입력 전
    p.no = p.rows.length ? p.rows[p.rows.length - 1].no : 0;
    if (p.no > st.seen) st.seen = p.no;
    if (p.no > st.no && !openKnown && !st.no && !(await todayEvidence(env, k.day, p))) {
      return unsaved(run, 'not-today');                            // 네이버 답이 없고 전날 마지막 값과 같거나 비교할 것이 없어요
    }
    if (p.no > st.no) {                                              // 새 회차
      let codes;                                                     // 유니버스가 먼저 — 실패하면 회차를 올리지 않고 다음 분에 다시(seen > no)
      try { codes = await universeCodes(env); } catch (e) { noteErr(env, st, 'universe', e && e.message, now); await saveState(env, st); return 'no-universe'; }
      st.no = p.no;
      const first = !st.rankNo && !st.estNo;
      await fetchRanks(run, p.no);
      // 첫 회차 ①이 모두 비면 휴장 — 네이버가 오늘 체결을 확인해 준 날은 그렇게 보지 않아요
      if (first && !openKnown && rankEmpty(st, p.no)) { st.closed = 'empty'; st.rnext = null; await saveState(env, st); return 'closed'; }
      await saveLast(env, k.day, p);
      st.job = newJob(p.no, codes, p, k.mins >= KF.FINAL_M, now);
      await workJob(run, k.mins);
      res = 'round';
    } else if (final && p.no > 0) {                                  // 마지막 확인: 순위를 마감 값으로, 바뀐 게 있으면 ②도 다시
      st.rnext = null;
      await fetchRanks(run, p.no);
      const row = p.rows.find(x => x.no === p.no), mine = st.est && st.est[KF.PROBE];
      const differs = !mine || !row || mine[0] !== row.f || mine[1] !== row.i;
      if (differs) await saveLast(env, k.day, p);
      if (st.estNo < p.no || differs) {
        let codes;
        try { codes = await universeCodes(env); } catch (e) { noteErr(env, st, 'universe', e && e.message, now); await saveState(env, st); return 'no-universe'; }
        st.job = newJob(p.no, codes, p, true, now);
        await workJob(run, k.mins);
      } else { if (st.rnext) swapRank(st, now); st.final = 1; }
      res = 'final';
    } else if (final && k.mins + KF.EVERY >= KF.PROBE_END_M) { st.final = 1; res = 'final-none'; }
    else if (st.seen > st.no) { st.seen = st.no; res = 'same'; }     // 다른 종목이 앞서 보였지만 아직 — 매분 확인하지 않게
    else return unsaved(run, 'same');
  }
  if (run.dirty || res !== 'idle') await saveState(env, st);
  return res;
}
function unsaved(run, res) {
  if (run.calls) MEM.unsaved = (MEM.unsaved || 0) + run.calls;
  return res;
}

/* ───────── 경로 ───────── */
const priv = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'private, no-store' } });

export function liveView(st, day, dev, { weekend = false } = {}) {
  const has = st && st.day === day;
  const body = {
    date: dash(day),
    slot: has ? label(st.rankNo) : null,
    slotNo: has ? st.rankNo || 0 : 0,
    at: has ? st.rankAt || null : null,
    src: SRC, unit: '억원',
    rank: has && st.rank ? st.rank : emptyRank(),
    est: has && st.est ? st.est : {},
    estSlot: has ? label(st.estNo) : null,
    estN: has ? st.estN || 0 : 0,
  };
  if ((has && st.closed) || weekend) body.closed = true;         // 주말 · 휴장 = 오늘은 장이 없어요(09:30 전과 구분)
  if (dev) body.run = has ? { n: st.n, no: st.no, seen: st.seen, final: !!st.final, cool: st.cool || null, err: st.err || null,
    job: st.job ? { no: st.job.no, next: st.job.next, total: st.job.codes.length, got: Object.keys(st.job.got).length, retry: st.job.retry.length, miss: st.job.miss } : null } : null;
  return body;
}

async function liveRoute(request, env, inv) {
  const k = kstOf(Date.now());
  let st = null;
  try { st = await env.REPLAY.get(sKey(k.day), 'json'); } catch (e) { st = null; }
  if (MEM.day === k.day && MEM.st && (!st || (MEM.st.seq || 0) > (st.seq || 0))) st = MEM.st;
  return priv(liveView(st, k.day, !!inv.dev, { weekend: k.wd < 1 || k.wd > 5 }));
}

// ② 한 종목 그때 받기 — KV 사본 `kisflow:st:<code>` 3분(오래된 사본은 실패할 때 stale로), 하루 400번(`kisflow:od:<날짜>`)
async function stockRoute(request, env, code) {
  if (!CODE_RE.test(code)) return priv({ error: '종목 코드가 올바르지 않아요' }, 400);
  const now = Date.now(), k = kstOf(now), date = dash(k.day);
  const none = { code, date, slots: [] };
  if (k.wd < 1 || k.wd > 5) return priv({ ...none, closed: true });    // 주말
  if (!clockMax(k.mins)) return priv(none);                           // 09:20 전: 오늘 값이 아직 있을 수 없어요
  let st = null;
  try { st = await env.REPLAY.get(sKey(k.day), 'json'); } catch (e) { st = null; }
  if (st && st.closed) return priv({ ...none, closed: true });
  const ck = `kisflow:st:${code}`;
  let copy = OD_MEM.get(code) || null;
  if (!copy || now - copy.ms >= KF.STOCK_FRESH_MS) {
    try { const kv = await env.REPLAY.get(ck, 'json'); if (kv && (!copy || kv.ms > copy.ms)) copy = kv; } catch (e) { /* 사본은 덤이에요 */ }
  }
  if (copy && copy.date !== date) copy = null;
  if (copy && now - copy.ms < KF.STOCK_FRESH_MS) return priv({ code, date, slots: copy.slots });
  const stale = msg => (copy ? priv({ code, date, slots: copy.slots, stale: true }) : priv({ error: msg }, 503));
  if (!kisReady(env)) return stale('한국투자 키가 없어요');
  if (OD_COOL > now) return stale('잠시 뒤에 다시 받아요');
  const nk = `kisflow:od:${k.day}`;
  let used = 0;
  try { used = +(await env.REPLAY.get(nk)) || 0; } catch (e) { used = 0; }
  if (used >= KF.OD_MAX) return stale('오늘 종목 조회 한도를 다 썼어요');
  const r = await kisCall(env, R2, TR2, { MKSC_SHRN_ISCD: code });
  const writes = [env.REPLAY.put(nk, String(used + 1), { expirationTtl: 2 * 86400 }).catch(() => {})];
  if (r.kind !== 'ok') {
    if (r.kind !== 'perm') OD_COOL = now + KF.OD_COOL_MS;
    console.error(`kisflow stock ${code} ${r.code}: ${kisScrub(r.msg, env)}`);
    await Promise.all(writes);
    if (r.kind === 'perm') return copy ? stale('') : priv(none);
    return stale('한국투자 응답을 받지 못했어요');
  }
  let p = parseEst(r.j);
  if (p.no > clockMax(k.mins)) p = { no: 0, rows: [] };                // 시계보다 앞선 회차 = 전날 값
  const slots = p.rows.map(x => ({ no: x.no, t: label(x.no), f: x.f, i: x.i }));
  const next = { ms: now, date, slots };
  OD_MEM.set(code, next);
  if (OD_MEM.size > 300) OD_MEM.delete(OD_MEM.keys().next().value);
  writes.push(env.REPLAY.put(ck, JSON.stringify(next), { expirationTtl: KF.STOCK_TTL_S }).catch(() => {}));
  await Promise.all(writes);
  return priv({ code, date, slots });
}

/* /api/flows/market — 공개 */
export function dealOf(j) {
  const d = j && j.dealTrendInfo;
  if (!d || typeof d !== 'object') return null;
  const v = { personal: kn(d.personalValue), foreign: kn(d.foreignValue), institutional: kn(d.institutionalValue) };
  if (v.personal == null && v.foreign == null && v.institutional == null) return null;
  return { v, date: /^\d{8}$/.test(String(d.bizdate || '')) ? String(d.bizdate) : null };
}
export function marketTtl(now) {
  const k = kstOf(now);
  return k.wd >= 1 && k.wd <= 5 && k.mins >= 540 && k.mins < 940 ? 60 : 600;
}
async function marketBody(env) {
  const now = Date.now();
  const get = ix => CONF.naver(`https://m.stock.naver.com/api/index/${ix}/integration`, KF.MKT_TIMEOUT).then(dealOf, () => null);
  const [K, Q] = await Promise.all([get('KOSPI'), get('KOSDAQ')]);
  let copy = null;
  try { copy = await env.REPLAY.get('flows:mkt', 'json'); } catch (e) { copy = null; }
  if (!K && !Q) {
    if (copy && copy.body) return { status: 200, body: { ...copy.body, stale: true }, ttl: 60 };
    return { status: 503, body: { error: '시장 수급을 받지 못했어요' }, ttl: 0 };
  }
  const date = [K, Q].map(x => x && x.date).filter(Boolean).sort().pop() || kstOf(now).day;
  const body = { asOf: new Date(now).toISOString(), date: dash(date), K: K ? K.v : null, Q: Q ? Q.v : null };
  if ((!K || !Q) && copy && copy.body && copy.body.date === body.date) {   // 한쪽만 실패: 같은 날의 지난 값으로 채우고 stale
    if (!K && copy.body.K) { body.K = copy.body.K; body.stale = true; }
    if (!Q && copy.body.Q) { body.Q = copy.body.Q; body.stale = true; }
  }
  if (K && Q) {
    const known = MKT_MEM && MKT_MEM.ms > ((copy && copy.ms) || 0) ? MKT_MEM : copy;
    if (!known || known.body.date !== body.date || now - known.ms >= KF.MKT_PUT_MS) {
      const rec = { ms: now, body };
      MKT_MEM = rec;
      try { await env.REPLAY.put('flows:mkt', JSON.stringify(rec), { expirationTtl: KF.MKT_TTL_S }); } catch (e) { /* 다음에 다시 */ }
    }
  }
  return { status: 200, body, ttl: body.stale ? 60 : marketTtl(now) };
}
async function marketRoute(request, env, ctx) {
  const cache = typeof caches !== 'undefined' ? caches.default : null;
  const key = new Request(new URL('/__cache/flows-market', request.url).toString());
  if (cache) { const hit = await cache.match(key).catch(() => null); if (hit) return hit; }
  const { status, body, ttl } = await marketBody(env);
  const res = new Response(JSON.stringify(body), { status, headers: {
    'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': ORIGIN,
    'cache-control': ttl ? `public, max-age=${ttl}` : 'no-store' } });
  if (cache && ttl && status === 200 && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(key, res.clone()).catch(() => {}));
  return res;
}

export async function flowsRoute(request, env, ctx, url) {
  env = env || {};
  if (request.method !== 'GET') return priv({ error: 'GET만 돼요' }, 405);
  const path = url.pathname;
  if (path === '/api/flows/market') return marketRoute(request, env, ctx);
  let inv;
  try { inv = await inviteOf(request, env); }
  catch (e) { if (e && e.status === 503) return priv({ error: 'unavailable' }, 503); throw e; }   // KV 오류 ≠ 초대 없음
  if (!inv) return priv({ error: 'forbidden' }, 403);
  if (path === '/api/flows/live') return liveRoute(request, env, inv);
  const m = path.match(/^\/api\/flows\/live\/stock\/([^/]+)$/);
  if (m) return stockRoute(request, env, m[1]);
  return priv({ error: '없는 경로예요' }, 404);
}
