// QA: worker/src/datago_funds.js + datago_routes.js — 증시 자금 for the 지표 tab (AGENTS §3-2 · §3-32 ①) through the real
// Worker router (worker/src/index.js). Fake fetch / KV / clock / edge cache (harness.mjs); no network, no real key.
//   node qa/datago/test_funds.mjs
import assert from 'node:assert/strict';
import { at, advance, clock, KST, makeKV, net, paged, rc, gateway, portalXml, KEYS, scanKV, scanLogs, runner, edge, assertNoKey, say } from './harness.mjs';
import { dgResetMemory, kstYmd, addDays, isWeekday } from '../../worker/src/datago.js';
import { fundsDue, FUNDS_KEY } from '../../worker/src/datago_funds.js';
import W from '../../worker/src/index.js';

const R = runner('funds route');
const env0 = (kv, extra = {}) => ({ REPLAY: kv, DATA_GO_KR_KEY: KEYS.raw, ...extra });
const OPS = { cap: 'getSecuritiesMarketTotalCapitalInfo', credit: 'getGrantingOfCreditBalanceInfo' };

/* ── a KOFIA-like history: business days 2025-09-01 … 2026-11-30, a deterministic walk ── */
const DAYS = [];
for (let d = '20250901'; d <= '20261130'; d = addDays(d, 1)) if (isWeekday(d) && d !== '20261009') DAYS.push(d);   // 한글날 (Fri 2026-10-09) closed
function val(i, base, amp) { return Math.round(base * (1 + amp * Math.sin(i / 9) + 0.0007 * i)); }
const ROWS = { cap: [], credit: [] };
DAYS.forEach((d, i) => {
  ROWS.cap.push({ basDt: d, invrDpsgAmt: String(val(i, 6.2e13, 0.05)), onbdDrvPrdTrRcAdvAmt: '41379416066284', toCstRpchCndBndSlgBal: '109523052899303',
    brkTrdUcolMny: String(val(i, 9.3e11, 0.2)), brkTrdUcolMnyVsOppsTrdAmt: String(val(i, 4.8e9, 0.4)), ucolMnyVsOppsTrdRlImpt: String((0.3 + (i % 7) / 10).toFixed(1)).replace(/^0/, '') });
  ROWS.credit.push({ basDt: d, crdTrFingWhl: String(val(i, 2.0e13, 0.06) + val(i, 0.7e13, 0.08)), crdTrFingScrs: String(val(i, 2.0e13, 0.06)), crdTrFingKosdaq: String(val(i, 0.7e13, 0.08)),
    crdTrLndrWhl: '31019254832', crdTrLndrScrs: '27994198130', crdTrLndrKosdaq: '3025056702', sbscCapLn: '0', dpsgScrtMogFing: '25408680581060' });
});
const pub = { cap: '20261113', credit: '20261113' };          // the last basDt each operation has opened
let fail = {};                                                // op id → () => response
const handler = (op, params) => {
  const id = Object.keys(OPS).find(k => OPS[k] === op);
  assert.ok(id, 'unexpected op ' + op);
  if (fail[id]) return fail[id]();
  assert.ok(/^\d{8}$/.test(params.beginBasDt) && /^\d{8}$/.test(params.endBasDt), 'a date range');
  const rows = ROWS[id].filter(r => r.basDt >= params.beginBasDt && r.basDt < params.endBasDt && r.basDt <= pub[id]);
  return paged(rows, params);
};
const reset = (t = '2026-11-16T14:00:00') => { dgResetMemory(); net.calls.length = 0; net.handler = handler; fail = {}; pub.cap = pub.credit = '20261113'; edge.on = false; edge.store.clear(); edge.puts.length = 0; at(t); };
async function get(env, path, colo) {
  const req = new Request('https://panse.pages.dev' + path);
  if (colo) Object.defineProperty(req, 'cf', { value: { colo } });
  const pending = [];
  const res = await W.fetch(req, env, { waitUntil: p => pending.push(p) });
  await Promise.all(pending);
  const text = await res.text();
  assertNoKey(text, 'response ' + path);
  for (const [k, v] of res.headers) assertNoKey(k + v, 'header');
  return { status: res.status, body: text ? JSON.parse(text) : null, cc: res.headers.get('cache-control'), cors: res.headers.get('access-control-allow-origin') };
}
const won = s => Math.round(+s / 1e8 * 100) / 100;
const row = (id, d) => ROWS[id].find(r => r.basDt === d);

await R.test('GET /api/funds: 7 items in order, 원 → 억원 (2 dp), % share, change / ratio vs the previous business day, dates, edge 1 h, CORS', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  const r = await get(env, '/api/funds');
  assert.equal(r.status, 200);
  assert.equal(r.cc, 'public, max-age=3600'); assert.equal(r.cors, 'https://panse.pages.dev');
  const b = r.body;
  assert.deepEqual(b.items.map(x => x.key), ['deposit', 'credit', 'creditKospi', 'creditKosdaq', 'unpaid', 'forced', 'forcedRatio']);
  assert.deepEqual(b.items.map(x => x.name), ['투자자예탁금', '신용융자 전체', '신용융자 코스피', '신용융자 코스닥', '위탁매매 미수금', '반대매매', '반대매매 비중']);
  assert.equal(b.basDt, '2026-11-13'); assert.equal(b.source, '금융투자협회'); assert.match(b.asOf, /^2026-11-16T14:00:00\+09:00$/);
  const c13 = row('cap', '20261113'), c12 = row('cap', '20261112');
  const dep = b.items[0];
  assert.equal(dep.unit, '억원'); assert.equal(dep.value, won(c13.invrDpsgAmt)); assert.equal(dep.prev, won(c12.invrDpsgAmt));
  assert.equal(dep.change, Math.round((won(c13.invrDpsgAmt) - won(c12.invrDpsgAmt)) * 100) / 100);
  assert.equal(dep.ratio, Math.round((won(c13.invrDpsgAmt) / won(c12.invrDpsgAmt) - 1) * 10000) / 100);
  assert.equal(dep.basDt, '2026-11-13'); assert.equal(dep.prevDt, '2026-11-12');
  const cr = b.items[1], k13 = row('credit', '20261113');
  assert.equal(cr.value, won(k13.crdTrFingWhl)); assert.equal(b.items[2].value, won(k13.crdTrFingScrs)); assert.equal(b.items[3].value, won(k13.crdTrFingKosdaq));
  const fr = b.items[6];
  assert.equal(fr.unit, '%'); assert.equal(fr.value, +c13.ucolMnyVsOppsTrdRlImpt); assert.equal(fr.change, Math.round((+c13.ucolMnyVsOppsTrdRlImpt - +c12.ucolMnyVsOppsTrdRlImpt) * 100) / 100);
  assert.ok(!('stale' in b) && !('partial' in b));
  // the two operations: one call each, 400 days back, endBasDt = tomorrow (exclusive), numOfRows ≤ 10000, json
  assert.deepEqual(net.calls.map(c => c.op).sort(), Object.values(OPS).sort());
  for (const c of net.calls) {
    assert.equal(c.path, '/1160100/service/GetKofiaStatisticsInfoService/' + c.op);
    assert.equal(c.params.beginBasDt, addDays('20261116', -400)); assert.equal(c.params.endBasDt, '20261117');
    assert.equal(c.params.numOfRows, '1000'); assert.equal(c.params.resultType, 'json');
  }
  assert.ok(kv.ttl(FUNDS_KEY) >= 10 * 86400 - 1);
  assert.equal(kv.json('datago:calls:kofia:20261116'), 2);
});
await R.test('a holiday in the series: the change on 2026-10-12 (Mon) is against 2026-10-08 (Thu, 한글날 closed)', async () => {
  reset('2026-10-13T14:00:00');
  pub.cap = pub.credit = '20261012';
  const b = (await get(env0(makeKV()), '/api/funds')).body;
  assert.equal(b.items[0].basDt, '2026-10-12'); assert.equal(b.items[0].prevDt, '2026-10-08');
});
await R.test('one operation fails: the other\'s new rows go in (partial), the failed one keeps its previous rows; soft error, no cool-down', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  await get(env, '/api/funds');
  at('2026-11-17T14:00:00'); dgResetMemory();
  pub.cap = pub.credit = '20261116';
  fail.credit = () => gateway(502, 'Error forwarding request to backend server');
  const b = (await get(env, '/api/funds')).body;
  assert.deepEqual(b.partial, ['credit']);
  assert.equal(b.items[0].basDt, '2026-11-16', '투자자예탁금 moved on');
  assert.equal(b.items[1].basDt, '2026-11-13', '신용융자 kept from the previous copy');
  assert.equal(b.basDt, '2026-11-16');
  const er = kv.json('datago:err:kofia');
  assert.equal(er.code, 'upstream'); assert.equal(er.partial, true); assert.equal(er.op, OPS.credit);
  assert.equal(kv.json('datago:cool:kofia'), null);
  // with no previous copy, the failed operation's items are simply absent
  reset(); const kv2 = makeKV();
  fail.credit = () => rc('10', 'INVALID_REQUEST_PARAMETER_ERROR');
  const b2 = (await get(env0(kv2), '/api/funds')).body;
  assert.deepEqual(b2.items.map(x => x.key), ['deposit', 'unpaid', 'forced', 'forcedRatio']);
});
await R.test('both fail: last copy with stale:true (edge 10 min) + cool-down; no copy at all → 503 {error, code}, not cached', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  await get(env, '/api/funds');
  at('2026-11-17T14:00:00'); dgResetMemory();
  fail.cap = fail.credit = () => portalXml('22', 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR');
  const r = await get(env, '/api/funds');
  assert.equal(r.status, 200); assert.equal(r.body.stale, true); assert.equal(r.cc, 'public, max-age=600'); assert.equal(r.body.basDt, '2026-11-13');
  assert.equal(kv.json('datago:cool:kofia').code, 'quota');
  reset();
  fail.cap = fail.credit = () => gateway(401, 'Unauthorized');
  const r2 = await get(env0(makeKV()), '/api/funds');
  assert.equal(r2.status, 503); assert.equal(r2.cc, 'no-store'); assert.equal(r2.body.code, 'key'); assert.ok(r2.body.error);
  const r3 = await get({ REPLAY: makeKV() }, '/api/funds');
  assert.equal(r3.status, 503); assert.equal(r3.body.code, 'nokey');
});
await R.test('due(): up to date → 6 h; behind on weekdays 13:00–20:00 → 30 min; behind otherwise → 3 h', () => {
  const s = (atS, dt) => ({ series: {}, at: KST(atS), opDt: { cap: dt, credit: dt } });
  // Tue 14:00: Monday's data should be out
  assert.equal(fundsDue(s('2026-11-17T13:40:00', '20261116'), KST('2026-11-17T19:00:00')), false, 'up to date, 5 h 20 old');
  assert.equal(fundsDue(s('2026-11-17T13:40:00', '20261116'), KST('2026-11-17T19:41:00')), true, 'up to date, 6 h');
  assert.equal(fundsDue(s('2026-11-17T13:40:00', '20261113'), KST('2026-11-17T14:05:00')), false, 'behind, 25 min');
  assert.equal(fundsDue(s('2026-11-17T13:40:00', '20261113'), KST('2026-11-17T14:11:00')), true, 'behind, 31 min');
  assert.equal(fundsDue(s('2026-11-17T20:30:00', '20261113'), KST('2026-11-17T22:00:00')), false, 'behind at night, 1.5 h');
  assert.equal(fundsDue(s('2026-11-17T20:30:00', '20261113'), KST('2026-11-17T23:31:00')), true, 'behind at night, 3 h');
  assert.equal(fundsDue(null, 0), true);
  assert.equal(fundsDue({ series: {}, at: KST('2026-11-17T13:40:00'), opDt: { cap: '20261116', credit: '20261113' } }, KST('2026-11-17T14:20:00')), true, 'one op behind = behind');
});
await R.test('chart: /api/funds/chart/{key}?tf=3m|1y — business-day closes, oldest first, 92 / 366 days; bad key / tf → 400', async () => {
  reset();
  const env = env0(makeKV());
  const a = await get(env, '/api/funds/chart/deposit?tf=3m');
  assert.equal(a.status, 200); assert.equal(a.cc, 'public, max-age=3600');
  assert.equal(a.body.key, 'deposit'); assert.equal(a.body.unit, '억원'); assert.equal(a.body.name, '투자자예탁금');
  const t = a.body.bars.map(x => x.t);
  assert.deepEqual(t, [...t].sort()); assert.equal(t[t.length - 1], '2026-11-13'); assert.ok(t[0] >= '2026-08-16' && t[0] <= '2026-08-18', t[0]);
  assert.equal(a.body.bars[a.body.bars.length - 1].c, won(row('cap', '20261113').invrDpsgAmt));
  const y = await get(env, '/api/funds/chart/forcedRatio?tf=1y');
  assert.ok(y.body.bars.length >= 245 && y.body.bars.length <= 262, String(y.body.bars.length)); assert.equal(y.body.unit, '%');
  assert.equal((await get(env, '/api/funds/chart/deposit')).body.tf, '3m');
  assert.equal((await get(env, '/api/funds/chart/nope?tf=3m')).status, 400);
  assert.equal((await get(env, '/api/funds/chart/deposit?tf=1d')).status, 400);
  assert.equal((await get(env, '/api/funds/what')).status, 404);
  assert.equal(net.calls.length, 2, 'every route reads the same snapshot');
});
await R.test('status: counters, cool-down, last error, snapshot ages — no key; warm=1 runs due() only', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  const s0 = (await get(env, '/api/datago/status')).body;
  assert.equal(s0.key, true); assert.equal(s0.snapshots.funds, null); assert.equal(s0.apis.kofia.calls, 0); assert.equal(s0.apis.kofia.cap, 300);
  assert.equal(s0.expectedBasDt, '2026-11-13');
  net.handler = (op, params) => (op === 'getItemInfo_V2' ? paged([{ basDt: params.basDt, srtnCd: 'A005930', isinCd: 'KR7005930003', itmsNm: '삼성전자', crno: '1301110006246', corpNm: '삼성전자(주)', mrktCtg: 'KOSPI' }], params) : handler(op, params));
  const s1 = (await get(env, '/api/datago/status?warm=1')).body;
  assert.equal(s1.snapshots.funds.basDt, '2026-11-13'); assert.equal(s1.snapshots.funds.points.deposit > 250, true);
  assert.equal(s1.snapshots.crno.n, 1); assert.equal(s1.apis.kofia.calls, 2); assert.equal(s1.apis.krx.calls, 1);
  assert.ok(!JSON.stringify(s1).includes('1301110006246'), 'the crno table itself is not published');
  const n = net.calls.length;
  await get(env, '/api/datago/status?warm=1');
  assert.equal(net.calls.length, n, 'nothing due → no calls');
  assert.equal((await get(env, '/api/datago/status')).cc, 'no-store');
});
await R.test('calls per day (simulated): a weekday, 2 colos, a request every 2 min through the 1 h edge cache; Monday\'s data opens 13:40', async () => {
  reset('2026-11-17T00:00:00');                     // Tuesday
  pub.cap = pub.credit = '20261113';
  edge.on = true;
  const kv = makeKV(), env = env0(kv);
  let seenAt = null;
  for (let t = KST('2026-11-17T00:00:00'); t < KST('2026-11-18T00:00:00'); t += 2 * 60e3) {
    clock.t = t;
    if (t >= KST('2026-11-17T13:40:00')) pub.cap = pub.credit = '20261116';
    for (const colo of ['ICN', 'NRT']) {
      const b = (await get(env, '/api/funds', colo)).body;
      if (!seenAt && b.basDt === '2026-11-16') seenAt = t;
    }
  }
  const calls = net.calls.length;
  say(`     upstream calls in 24 h: ${calls} (${calls / 2} refreshes); new day visible ${Math.round((seenAt - KST('2026-11-17T13:40:00')) / 60e3)} min after it opened`);
  assert.ok(calls <= 24, 'calls/day ' + calls);
  assert.ok(seenAt && seenAt - KST('2026-11-17T13:40:00') <= 90 * 60e3, 'visible within 90 min');
  assert.equal(kv.json('datago:calls:kofia:20261117'), calls);
});
await R.test('cap: env.DATAGO_CAP=2 → the second refresh of the day is refused before the network (stale copy, cool-down to midnight)', async () => {
  reset();
  const kv = makeKV(), env = env0(kv, { DATAGO_CAP: '2' });
  await get(env, '/api/funds');
  at('2026-11-16T21:00:00'); dgResetMemory();
  const r = await get(env, '/api/funds');
  assert.equal(net.calls.length, 2);
  assert.equal(r.body.stale, true);
  assert.equal(kv.json('datago:cool:kofia').code, 'cap');
});
await R.test('leaks: the key is in no response, KV key or value, or console line', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  fail.credit = () => rc('30', 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR ' + KEYS.raw);
  await get(env, '/api/funds');
  await get(env, '/api/funds/chart/deposit?tf=1y');
  await get(env, '/api/datago/status');
  scanKV(kv); scanLogs();
});

R.done();
