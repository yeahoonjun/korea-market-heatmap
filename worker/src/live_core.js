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
// 'open' from 09:00 to the session end (+ GRACE) on weekdays. endTime 'HHMM' from the quotes (1530, or 1630 on 수능 / the
// year's first trading day); null = not known yet today → assume the longest day (the first poll tells the hub).
export function sessionState(ms, endTime) {
  const k = kst(ms);
  if (k.wd === 0 || k.wd === 6) return 'closed';
  const e = /^\d{4}$/.test(endTime || '') ? endTime : '1630';
  const end = (+e.slice(0, 2)) * 3600 + (+e.slice(2)) * 60 + GRACE_MS / 1000;
  return k.sod >= 9 * 3600 && k.sod < end ? 'open' : 'closed';
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
