// 실시간 갱신 허브의 순수 부품 점검 (worker/src/live_core.js, docs/standards/realtime.md §5 · §12). 네트워크·Workers 없이 Node만.
//   node qa/worker/test_live_core.mjs        → 실패가 있으면 종료 코드 1
import assert from 'node:assert/strict';
import { LIVE_POLL_MS, LIMITS, UNIT, kst, nextOpen, nextKstMidnight, nextKstMonth, sessionState, newGuard, roll, charge, overBudget, diffRow, applyPatch, cloneRow } from '../../worker/src/live_core.js';

let pass = 0, fail = 0;
const t = (name, fn) => { try { fn(); pass++; console.log('  ok  ', name); } catch (e) { fail++; console.log('  FAIL', name, '\n       ', e.message); } };
const K = s => Date.parse(s + '+09:00');            // KST wall time → ms
const iso = ms => new Date(ms + 9 * 3600e3).toISOString().slice(0, 19).replace('T', ' ');

console.log('budget limits vs Workers Paid included usage (pricing pages, Last updated Nov 13, 2026)');
t('one constant for the upstream interval, 3 s', () => assert.equal(LIVE_POLL_MS, 3000));
t('DO requests: 31 days at the daily cap stay ≤ 62 % of 1,000,000 (any billing-month alignment)', () => assert.ok(31 * LIMITS.dayDoReq <= 620000));
t('DO requests: the monthly belt is ≤ 60 % of 1,000,000', () => assert.ok(LIMITS.monthDoReq <= 600000));
t('DO duration: monthly awake cap ≤ 200,000 GB-s (half of 400,000) at 128 MB', () => assert.ok(LIMITS.monthAwakeMs / 1000 * 0.125 <= 200000));
t('DO duration: even 31 days of a hub awake the whole longest session (09:00–16:32) is ≤ 30 % of 400,000 GB-s', () => assert.ok(31 * (7.5 * 3600 + 120) * 0.125 <= 0.3 * 400000));
t('alarms on the longest session day (09:00–16:32 at 3 s) fit the daily cap with room for 50 pages', () => {
  const alarms = Math.ceil((7.5 * 3600 + 120) / (LIVE_POLL_MS / 1000));     // 9,040
  assert.ok(alarms + LIMITS.dayConnects + LIMITS.maxSockets * LIMITS.socketMsgs / UNIT <= LIMITS.dayDoReq, `${alarms} alarms`);
});
t('max sockets is a family-size number', () => assert.ok(LIMITS.maxSockets <= 50));

console.log('KST clock and session window');
t('kst(): 2026-11-16 09:00 KST is Monday, hm 900', () => { const k = kst(K('2026-11-16T09:00:00')); assert.equal(k.wd, 1); assert.equal(k.hm, 900); assert.equal(k.day, '20261116'); assert.equal(k.date, '2026-11-16'); });
t('closed before 09:00, open at 09:00', () => { assert.equal(sessionState(K('2026-11-16T08:59:59'), '1530'), 'closed'); assert.equal(sessionState(K('2026-11-16T09:00:00'), '1530'), 'open'); });
t('1530 day: open through the 2-minute grace, closed at 15:32', () => { assert.equal(sessionState(K('2026-11-16T15:31:59'), '1530'), 'open'); assert.equal(sessionState(K('2026-11-16T15:32:00'), '1530'), 'closed'); });
t('1630 day (수능 · first trading day): open at 16:20, closed at 16:32', () => { assert.equal(sessionState(K('2026-11-19T16:20:00'), '1630'), 'open'); assert.equal(sessionState(K('2026-11-19T16:32:00'), '1630'), 'closed'); });
t('unknown end time = the longest day (the hub learns it on the first poll)', () => { assert.equal(sessionState(K('2026-11-16T16:00:00'), null), 'open'); assert.equal(sessionState(K('2026-11-16T16:32:00'), null), 'closed'); });
t('weekends are closed', () => { assert.equal(sessionState(K('2026-11-14T11:00:00'), null), 'closed'); assert.equal(sessionState(K('2026-11-15T11:00:00'), null), 'closed'); });
t('nextOpen: Saturday → Monday 09:00', () => assert.equal(iso(nextOpen(K('2026-11-14T02:46:00'))), '2026-11-16 09:00:00'));
t('nextOpen: Friday after the close → Monday 09:00', () => assert.equal(iso(nextOpen(K('2026-11-20T15:40:00'))), '2026-11-23 09:00:00'));
t('nextOpen: Monday 08:00 → the same day 09:00; Monday 09:00 → Tuesday (strictly after)', () => { assert.equal(iso(nextOpen(K('2026-11-16T08:00:00'))), '2026-11-16 09:00:00'); assert.equal(iso(nextOpen(K('2026-11-16T09:00:00'))), '2026-11-17 09:00:00'); });
t('next KST midnight / month start', () => { assert.equal(iso(nextKstMidnight(K('2026-11-16T23:59:59'))), '2026-11-17 00:00:00'); assert.equal(iso(nextKstMonth(K('2026-11-30T23:00:00'))), '2026-12-01 00:00:00'); assert.equal(iso(nextKstMonth(K('2026-12-31T10:00:00'))), '2027-01-01 00:00:00'); });

console.log('budget guard');
t('roll(): a new KST day clears day counters, keeps month; a new month clears both', () => {
  const g = newGuard(K('2026-11-16T10:00:00'));
  charge(g, 100 * UNIT, 5000); g.dConn = 7; g.dPolls = 3; g.mPolls = 3;
  roll(g, K('2026-11-17T00:00:01'));
  assert.equal(g.dU, 0); assert.equal(g.dConn, 0); assert.equal(g.dAwake, 0); assert.equal(g.mU, 100 * UNIT); assert.equal(g.mAwake, 5000); assert.equal(g.mPolls, 3);
  roll(g, K('2026-12-01T00:00:01'));
  assert.equal(g.mU, 0); assert.equal(g.mAwake, 0); assert.equal(g.mPolls, 0);
});
t('day boundary is KST midnight, not UTC midnight', () => { const g = newGuard(K('2026-11-16T08:59:00')); charge(g, UNIT); roll(g, K('2026-11-16T09:30:00')); assert.equal(g.dU, UNIT); });
t('under the limits: no trip', () => { const g = newGuard(K('2026-11-16T10:00:00')); charge(g, (LIMITS.dayDoReq - 1) * UNIT); assert.equal(overBudget(g, LIMITS, K('2026-11-16T10:00:00')), null); });
t('dayDoReq reached: trip until the next KST midnight', () => { const now = K('2026-11-16T10:00:00'), g = newGuard(now); charge(g, LIMITS.dayDoReq * UNIT); const o = overBudget(g, LIMITS, now); assert.equal(o.why, 'dayDoReq'); assert.equal(iso(o.until), '2026-11-17 00:00:00'); });
t('incoming messages count 1/20: 20 messages = 1 request', () => { const g = newGuard(0); for (let i = 0; i < 20; i++) charge(g, 1); assert.equal(g.dU, UNIT); });
t('dayConnects reached: trip (a reconnect loop stops here)', () => { const now = K('2026-11-16T10:00:00'), g = newGuard(now); g.dConn = LIMITS.dayConnects; assert.equal(overBudget(g, LIMITS, now).why, 'dayConnects'); });
t('dayAwakeMs reached: trip', () => { const now = K('2026-11-16T10:00:00'), g = newGuard(now); charge(g, 0, LIMITS.dayAwakeMs); assert.equal(overBudget(g, LIMITS, now).why, 'dayAwakeMs'); });
t('monthDoReq reached: trip until the next KST month, even on a fresh day', () => { const now = K('2026-11-20T10:00:00'), g = newGuard(now); g.mU = LIMITS.monthDoReq * UNIT; const o = overBudget(g, LIMITS, now); assert.equal(o.why, 'monthDoReq'); assert.equal(iso(o.until), '2026-12-01 00:00:00'); });
t('monthAwakeMs reached: trip until the next month', () => { const now = K('2026-11-20T10:00:00'), g = newGuard(now); g.mAwake = LIMITS.monthAwakeMs; assert.equal(overBudget(g, LIMITS, now).why, 'monthAwakeMs'); });
t('an expired trip is cleared by roll()', () => { const now = K('2026-11-16T10:00:00'), g = newGuard(now); g.trip = { why: 'dayDoReq', until: K('2026-11-17T00:00:00') }; roll(g, K('2026-11-17T00:00:00')); assert.equal(g.trip, null); });
t('simulated normal day (10 family pages, 3 reconnects each an hour, 6.5 h): no trip, < 50 % of the daily cap', () => {
  const g = newGuard(K('2026-11-16T09:00:00'));
  const alarms = 6.5 * 3600 / 3, connects = 10 * 3 * 6.5;
  charge(g, (alarms + connects) * UNIT + connects /* closes */, alarms * 1200);   // ~1.2 s awake per tick (Naver wait)
  g.dConn = connects;
  assert.equal(overBudget(g, LIMITS, K('2026-11-16T15:30:00')), null);
  assert.ok(g.dU / UNIT < LIMITS.dayDoReq / 2, `${g.dU / UNIT} requests`);
});
t('simulated worst month: every trading day at the daily cap still trips the monthly belt before 1,000,000', () => {
  const g = newGuard(K('2026-11-02T09:00:00'));
  let day = 0, tripped = null;
  for (let d = 2; d <= 30 && !tripped; d++) {
    const now = K(`2026-11-${String(d).padStart(2, '0')}T12:00:00`);
    roll(g, now);
    charge(g, LIMITS.dayDoReq * UNIT); day++;
    tripped = overBudget(g, LIMITS, now);
    if (tripped && tripped.why === 'dayDoReq') tripped = null;     // the day cap ends that day; keep going
  }
  assert.ok(g.mU / UNIT <= 620000, `${g.mU / UNIT}`);
  assert.ok(!tripped || tripped.why === 'monthDoReq');
});

console.log('delta rules (diffRow / applyPatch round trip)');
// synthetic /api/quotes rows (no network): 600 rows with every optional key present or absent at random
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const row = i => {
  const p = 1000 + Math.round(rnd() * 500000), d = Math.round((rnd() - 0.5) * p / 20);
  const r = { c: String(100000 + i).slice(-6), n: '종목' + i, m: i % 2 ? 'K' : 'Q', s: '섹터', i: '업종', cap: 1000 + i, p, d, r: Math.round(d / (p - d) * 10000) / 100, tv: Math.round(rnd() * 5000), v: Math.round(rnd() * 1e7) };
  if (rnd() < 0.9) { r.op = p - 100; r.hi = p + 200; r.lo = p - 300; }
  if (rnd() < 0.02) r.lim = 1;
  if (rnd() < 0.8) r.nx = { p, d, r: r.r, s: 'reg', o: 1, t: '2026-11-16T10:00:00+09:00', v: 100, tv: 1, op: p, hi: p, lo: p };
  return r;
};
const rows = Array.from({ length: 600 }, (_, i) => row(i));
const FAST = ['p', 'd', 'r', 'lim', 'op', 'hi', 'lo'], SLOW = ['cap', 'tv', 'v'], NXF = ['p', 'd', 'r', 's', 'o', 'op', 'hi', 'lo'], NXS = ['v', 'tv', 't'];
function mutate(o) {
  const n = cloneRow(o);
  for (const k of [...FAST, ...SLOW]) if (rnd() < 0.3) { if (rnd() < 0.1) delete n[k]; else n[k] = Math.round((n[k] || 1000) * (1 + (rnd() - 0.5) / 50)); }
  if (rnd() < 0.05) delete n.nx;
  else if (n.nx) { for (const k of [...NXF, ...NXS]) if (rnd() < 0.3) { if (rnd() < 0.1) delete n.nx[k]; else n.nx[k] = typeof n.nx[k] === 'string' ? n.nx[k] + 'x' : Math.round((n.nx[k] || 1000) * (1 + (rnd() - 0.5) / 50)); } }
  else if (rnd() < 0.1) n.nx = { p: n.p, d: n.d, r: n.r, s: 'reg', o: 1, t: 'T', v: 1, tv: 1 };
  return n;
}
const sortKeys = x => x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map(k => [k, sortKeys(x[k])])) : x;
const eq = (a, b) => JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b));
t('slow tick: applyPatch(old, diffRow(old, new, true)) === new (12,000 pairs)', () => {
  let bad = 0;
  for (let k = 0; k < 20; k++) for (const o of rows) { const n = mutate(o); if (!eq(applyPatch(cloneRow(o), diffRow(o, n, true) || { c: o.c }), n)) bad++; }
  assert.equal(bad, 0);
});
t('fast tick: FAST keys from new, SLOW keys from old (12,000 pairs)', () => {
  let bad = 0;
  for (let k = 0; k < 20; k++) for (const o of rows) {
    const n = mutate(o), got = applyPatch(cloneRow(o), diffRow(o, n, false) || { c: o.c }), want = cloneRow(o);
    for (const f of FAST) { if (f in n) want[f] = n[f]; else delete want[f]; }
    if (!o.nx || !n.nx) { if (n.nx) want.nx = cloneRow(n.nx); else delete want.nx; }
    else for (const f of NXF) { if (f in n.nx) want.nx[f] = n.nx[f]; else delete want.nx[f]; }
    if (!eq(got, want)) bad++;
  }
  assert.equal(bad, 0);
});
t('no change → no patch', () => { for (const o of rows.slice(0, 50)) assert.equal(diffRow(o, cloneRow(o), true), null); });
t('a price tick is a small patch {c, p, d, r}', () => { const o = rows[0], n = cloneRow(o); n.p += 100; n.d += 100; n.r += 0.05; delete n.nx; const o2 = cloneRow(o); delete o2.nx; assert.deepEqual(Object.keys(diffRow(o2, n, false)).sort(), ['c', 'd', 'p', 'r']); });

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
