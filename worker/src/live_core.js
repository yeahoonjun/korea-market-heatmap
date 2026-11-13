// 실시간 갱신 허브의 순수 부품 (docs/standards/realtime.md §5 · §12): 델타 규칙, KST 시계, 예산 안전장치.
// Workers API를 쓰지 않아요 — qa/worker/test_live_core.mjs가 Node에서 그대로 불러 점검해요.

/* ── the one tunable the user chose (2026-11-14): how often the hub asks Naver during the regular session ── */
export const LIVE_POLL_MS = 3000;   // the weekday measurement (prototypes/realtime/measure_upstream.py) may change only this number

/* ── hard limits: the hub must stay inside the Workers Paid included usage ($5, nothing more) under every condition ──
   Durable Objects included per month: 1,000,000 requests, 400,000 GB-s (pricing page, Last updated Nov 13, 2026).
   Daily caps are alignment-proof: 31 days × dayDoReq = 620,000 requests (62 %) whatever day the billing month starts. */
export const LIMITS = {
  maxSockets: 50,                 // family & friends; the 51st page gets {t:'off', reason:'full'} and keeps polling
  dayDoReq: 20000,                // DO requests the hub counts per KST day (fetch / alarm / internal state = 1, incoming WS message or close = 1/20)
  monthDoReq: 600000,             // per KST calendar month — a belt over the daily cap
  dayConnects: 2000,              // WebSocket connections accepted per KST day (a reconnect loop trips this first)
  dayAwakeMs: 8 * 3600e3,         // hub handler wall time per KST day — duration proxy (one session is ≤ 7.5 h)
  monthAwakeMs: 1.6e9,            // = 200,000 GB-s at 128 MB, half the included 400,000
  socketMsgs: 20,                 // messages a page may send on one socket before it is closed (the page normally sends none)
};
// test-only overrides (wrangler dev --var LIVE_LIMITS:{…}) can only TIGHTEN: each number is min(override, default), so a stray
// production variable can never loosen a cap
export function limitsFrom(json) {
  let o = null;
  try { o = json ? JSON.parse(json) : null; } catch (e) { o = null; }
  if (!o || typeof o !== 'object') return LIMITS;
  const out = { ...LIMITS };
  for (const k of Object.keys(LIMITS)) { const v = Number(o[k]); if (Number.isFinite(v) && v > 0) out[k] = Math.min(v, LIMITS[k]); }
  return out;
}
export const IDLE_RESET_MS = 10 * 60e3;   // a hub idle this long throws its rows away: the next page waits for a fresh snapshot
export const HOLIDAY_LATCH_MS = 30 * 60e3; // a weekday that looks like a holiday is re-checked after this (수능 / first day open at 10:00)
export const MIN_PRICED = 300;            // an answer with fewer priced rows than half the 600-row stream is not data (recorder rule)
// seconds a data center remembers a refusal, so refused pages cost no Durable Object request (Cache API, no KV)
export const GATE_TTL = { full: 30, closed: 600, budget: 600, paused: 60, error: 15 };
export const RING = 40;             // deltas kept for resume (≈ 2 min at 3 s)
export const SLOW_EVERY = 10;       // volume / value / cap / NXT trade time: every 10th tick (≈ 30 s)
export const HB_MS = 15000;         // a quiet stream still sends a heartbeat this often (the page reconnects after 45 s of silence)
export const GRACE_MS = 120e3;      // keep polling 2 minutes after the close so the closing prices reach the pages
export const UNIT = 20;             // billing units per DO request (incoming WS messages bill 20 : 1)

/* ── KST clock ── */
const p2 = n => String(n).padStart(2, '0');
// → {day:'YYYYMMDD', month:'YYYYMM', wd (0 = Sunday), hm (HHMM as a number), sod (seconds of the KST day), date:'YYYY-MM-DD'}
export function kst(ms) {
  const d = new Date(ms + 9 * 3600e3);
  const Y = d.getUTCFullYear(), M = d.getUTCMonth() + 1, D = d.getUTCDate();
  return { day: `${Y}${p2(M)}${p2(D)}`, month: `${Y}${p2(M)}`, date: `${Y}-${p2(M)}-${p2(D)}`, wd: d.getUTCDay(), hm: d.getUTCHours() * 100 + d.getUTCMinutes(), sod: d.getUTCHours() * 3600 + d.getUTCMinutes() * 60 + d.getUTCSeconds() };
}
const kstDayStart = ms => { const d = new Date(ms + 9 * 3600e3); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - 9 * 3600e3; };
export const nextKstMidnight = ms => kstDayStart(ms) + 86400e3;
export function nextKstMonth(ms) { const d = new Date(ms + 9 * 3600e3); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) - 9 * 3600e3; }
// the next weekday 09:00 KST strictly after ms (holidays unknown: the hub finds them, §4-5)
export function nextOpen(ms) {
  for (let i = 0; i < 8; i++) {
    const t = kstDayStart(ms) + i * 86400e3 + 9 * 3600e3, wd = kst(t).wd;
    if (wd >= 1 && wd <= 5 && t > ms) return t;
  }
  return ms + 86400e3;
}
const hmSec = hm => (+hm.slice(0, 2)) * 3600 + (+hm.slice(2)) * 60;
const isHm = v => /^\d{4}$/.test(v || '');
// 'open' from the session start to the session end (+ GRACE) on weekdays. startTime / endTime 'HHMM' from the quotes
// (stockExchangeType: 0900 / 1530, or 1000 / 1630 on 수능 and the year's first trading day). Unknown today → 09:00 and the
// longest day (the first poll tells the hub).
export function sessionState(ms, endTime, startTime) {
  const k = kst(ms);
  if (k.wd === 0 || k.wd === 6) return 'closed';
  const start = hmSec(isHm(startTime) ? startTime : '0900');
  const end = hmSec(isHm(endTime) ? endTime : '1630') + GRACE_MS / 1000;
  return k.sod >= start && k.sod < end ? 'open' : 'closed';
}
// when a refused page should come back: today's start if it is still ahead (a 10:00 day), else the next weekday 09:00
export function openAt(ms, startTime) {
  const k = kst(ms);
  if (k.wd >= 1 && k.wd <= 5 && isHm(startTime) && k.sod < hmSec(startTime)) return kstDayStart(ms) + hmSec(startTime) * 1000;
  return nextOpen(ms);
}
// a weekday without trading: 5 minutes after the start both indices are still CLOSE and the newest KRX trade is from another
// day. Before start + 5 min it is never a holiday (a 10:00 day must not latch at 09:05).
export function isHoliday(body, ms, startTime) {
  const k = kst(ms);
  if (k.sod < hmSec(isHm(startTime) ? startTime : '0900') + 300) return false;
  const st = Object.values((body && body.marketStatus) || {});
  return st.length > 0 && st.every(x => x === 'CLOSE') && String((body && body.asOf) || '').slice(0, 10) !== k.date;
}
// a usable answer: at least MIN_PRICED rows with a price (an empty or price-0 answer must never become the snapshot)
export function validBody(body) {
  const rows = (body && Array.isArray(body.stocks)) ? body.stocks : [];
  return rows.filter(r => r && r.p > 0).length >= MIN_PRICED;
}

/* ── budget guard (persisted in the hub's own storage — no KV) ── */
export function newGuard(ms) {
  const k = kst(ms);
  return { v: 1, day: k.day, month: k.month, dU: 0, mU: 0, dConn: 0, dAwake: 0, mAwake: 0, dPolls: 0, mPolls: 0, dMsgs: 0, trip: null, endTime: null, endDay: null, closedDay: null, trips: 0 };
}
// KST day / month rollover; an expired trip is cleared
export function roll(g, ms) {
  const k = kst(ms);
  if (g.month !== k.month) { g.month = k.month; g.mU = 0; g.mAwake = 0; g.mPolls = 0; }
  if (g.day !== k.day) { g.day = k.day; g.dU = 0; g.dConn = 0; g.dAwake = 0; g.dPolls = 0; g.dMsgs = 0; }
  if (g.trip && ms >= g.trip.until) g.trip = null;
  return g;
}
export function charge(g, units, awakeMs = 0) { g.dU += units; g.mU += units; g.dAwake += awakeMs; g.mAwake += awakeMs; }
// → {why, until} when a limit is reached (month limits first: they last longer), else null
export function overBudget(g, lim, ms) {
  if (g.mU >= lim.monthDoReq * UNIT) return { why: 'monthDoReq', until: nextKstMonth(ms) };
  if (g.mAwake >= lim.monthAwakeMs) return { why: 'monthAwakeMs', until: nextKstMonth(ms) };
  if (g.dU >= lim.dayDoReq * UNIT) return { why: 'dayDoReq', until: nextKstMidnight(ms) };
  if (g.dConn >= lim.dayConnects) return { why: 'dayConnects', until: nextKstMidnight(ms) };
  if (g.dAwake >= lim.dayAwakeMs) return { why: 'dayAwakeMs', until: nextKstMidnight(ms) };
  return null;
}

/* ── delta rules: the page's applyPatch must stay identical (realtime.md §5-3) ──
   patch = {c, …only the keys that changed}; null = key removed; nx is merged key by key (null = NXT gone, a new nx comes whole).
   FAST keys every tick, SLOW keys every SLOW_EVERY-th tick. The hub keeps rows exactly as the pages hold them. */
const FAST = ['p', 'd', 'r', 'lim', 'op', 'hi', 'lo'];
const SLOW = ['cap', 'tv', 'v'];
const NX_FAST = ['p', 'd', 'r', 's', 'o', 'op', 'hi', 'lo'];
const NX_SLOW = ['v', 'tv', 't'];
export function diffRow(o, n, slow) {
  let p = null;
  const put = (k, v) => { (p ||= { c: n.c })[k] = v === undefined ? null : v; };
  for (const k of FAST) if (o[k] !== n[k]) put(k, n[k]);
  const on = o.nx || null, nn = n.nx || null;
  if (!on || !nn) { if (on !== nn) put('nx', nn); }
  else {
    let q = null;
    for (const k of NX_FAST) if (on[k] !== nn[k]) (q ||= {})[k] = nn[k] === undefined ? null : nn[k];
    if (slow) for (const k of NX_SLOW) if (on[k] !== nn[k]) (q ||= {})[k] = nn[k] === undefined ? null : nn[k];
    if (q) put('nx', q);
  }
  if (slow) for (const k of SLOW) if (o[k] !== n[k]) put(k, n[k]);
  return p;
}
export function applyPatch(row, p) {
  for (const k in p) {
    if (k === 'c') continue;
    const v = p[k];
    if (k === 'nx') {
      if (v === null) delete row.nx;
      else { const nx = row.nx || (row.nx = {}); for (const j in v) { if (v[j] === null) delete nx[j]; else nx[j] = v[j]; } }
    } else if (v === null) delete row[k];
    else row[k] = v;
  }
  return row;
}
// structuredClone where the runtime has it (Workers, Node ≥ 17); rows are plain JSON
export const cloneRow = r => (typeof structuredClone === 'function' ? structuredClone(r) : JSON.parse(JSON.stringify(r)));
export const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);
