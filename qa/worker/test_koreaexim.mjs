// QA: worker/src/koreaexim.js — 수출입은행 고시 /api/koreaexim?kind=fx|rate (AGENTS §3-27 끝 · §3-2) through the real router
// (worker/src/index.js). Fake clock / KV / edge cache from qa/datago/harness.mjs, a fake oapi.koreaexim.go.kr here. Fixtures follow
// the probe's real answer of 2026-11-16 11:32 KST (comma numbers as text, cur_unit 'JPY(100)', 'EURIBOR1개월', 'TIBOR 1개월',
// int_r null / '0' in the swap lists, tona_list empty). No network, no real key.
//   node qa/worker/test_koreaexim.mjs
import assert from 'node:assert/strict';
import { at, advance, clock, KST, makeKV, edge, runner, logs, keyForms, ctxOf, say } from '../datago/harness.mjs';
import { KX, kxResetMemory, parseFx, parseRate, kxTtl } from '../../worker/src/koreaexim.js';
import W from '../../worker/src/index.js';

const R0 = runner('koreaexim');
const R = { test: (name, fn) => R0.test(name, async () => { try { await fn(); } catch (e) { if (process.env.KX_DEBUG) say(name + ': ' + (e && e.message)); throw e; } }), done: () => R0.done() };
const FXKEY = 'kxFxKey+/=NotReal0123456789abcdef', RATEKEY = 'kxRateKey%NotReal9876543210fedcba';
const env0 = (kv, extra = {}) => ({ REPLAY: kv, KOREAEXIM_FX_KEY: FXKEY, KOREAEXIM_RATE_KEY: RATEKEY, ...extra });

/* ── fixtures: one posting per business day; the value moves a little with the date ── */
const n = (v, dp = 2) => v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: dp });
const dayIx = d => Math.round((Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8)) - Date.UTC(2026, 10, 1)) / 86400e3);
const CUR = [['AED', '아랍에미리트 디르함', 363.1], ['AUD', '호주 달러', 903.98], ['CNH', '위안화', 199.78], ['EUR', '유로', 1470.14],
  ['GBP', '영국 파운드', 1762.42], ['IDR(100)', '인도네시아 루피아', 7.33], ['JPY(100)', '일본 옌', 834.37], ['KRW', '한국 원', 1],
  ['USD', '미국 달러', 1333.7], ['BHD', '바레인 디나르', 3536.73]];
function fxRows(d) {
  const k = 1 + dayIx(d) * 0.001;
  return CUR.map(([u, nm, b]) => {
    const base = u === 'KRW' ? 1 : Math.round(b * k * 100) / 100;
    return { result: 1, cur_unit: u, ttb: u === 'KRW' ? '0' : n(base * 0.99), tts: u === 'KRW' ? '0' : n(base * 1.01), deal_bas_r: n(base), bkpr: n(Math.floor(base), 0),
      yy_efee_r: '0', ten_dd_efee_r: '0', kftc_bkpr: n(Math.floor(base), 0), kftc_deal_bas_r: n(base), cur_nm: nm };
  });
}
const NULLS = { sofr_list: null, estr_list: null, euribor_list: null, tona_list: null, tibor_list: null, swapRfr_list: null, libor_list: null, swap_list: null, cirr_list: null, new_cirr_list: null };
const rrow = (cur, nm, r) => ({ result: 1, cur_fund: cur, sfln_intrc_nm: nm, int_r: r, ...NULLS });
let withTona = false;
function rateObj(d) {
  const s = dayIx(d) * 0.001;
  const f = (v, dp = 3) => String(+(v + s).toFixed(dp));
  return {
    result: 1,
    sofr_list: [rrow('USD', 'SOFR 익일물', f(3.9))], estr_list: [rrow('EUR', 'ESTR 익일물', f(2.443))],
    euribor_list: [rrow('EUR', 'EURIBOR1개월', f(2.479)), rrow('EUR', 'EURIBOR3개월', f(2.766)), rrow('EUR', 'EURIBOR6개월', f(3.023)), rrow('EUR', 'EURIBOR12개월', f(3.293))],
    tona_list: withTona ? [rrow('JPY', 'TONA 익일물', f(0.477))] : [],
    tibor_list: [rrow('JPY', 'TIBOR 1개월', f(1.41982, 5)), rrow('JPY', 'TIBOR 3개월', f(1.78673, 5)), rrow('JPY', 'TIBOR 6개월', f(1.92591, 5)), rrow('JPY', 'TIBOR 12개월', f(1.63391, 5))],
    swapRfr_list: [rrow('USD', 'SWAP금리(RFR) 6개월', '4.3695')], libor_list: [],
    swap_list: [rrow('USD', 'SWAP금리 6개월', '0'), rrow('EUR', 'SWAP금리 6개월', null)], cirr_list: [], new_cirr_list: [rrow('USD', null, '5.84')],
  };
}
const EMPTY_RATE = { result: 1, sofr_list: [], estr_list: [], euribor_list: [], tona_list: [], tibor_list: [], swapRfr_list: [], libor_list: [], swap_list: [], cirr_list: [], new_cirr_list: [] };

/* ── the fake source ── */
let postHm = 660;                     // minutes after KST midnight: today's posting appears from then on (null = not today)
let fail = null;                      // () → Response | throws, for every call
const calls = [];
const HOLIDAYS = new Set(['20261111']);
function hasPosting(d) {
  if (HOLIDAYS.has(d)) return false;
  const wd = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8))).getUTCDay();
  if (wd === 0 || wd === 6) return false;
  const today = new Date(clock.t + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
  if (d > today) return false;
  if (d === today) { const k = new Date(clock.t + 9 * 3600e3); return postHm != null && k.getUTCHours() * 60 + k.getUTCMinutes() >= postHm; }
  return true;
}
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  const u = new URL(url);
  assert.equal(u.origin, 'https://oapi.koreaexim.go.kr', 'only the koreaexim host');
  const kind = u.pathname.endsWith('/exchangeJSON') ? 'fx' : u.pathname.endsWith('/internationalJSON') ? 'rate' : null;
  assert.ok(kind, 'path ' + u.pathname);
  const p = Object.fromEntries(u.searchParams);
  assert.equal(p.authkey, kind === 'fx' ? FXKEY : RATEKEY, 'the right key for the right API');
  assert.equal(p.data, kind === 'fx' ? 'AP01' : 'AP03');
  assert.match(p.searchdate, /^\d{8}$/);
  assert.ok(init.signal instanceof AbortSignal, 'a time limit');
  assert.match(init.headers['user-agent'], /Panse/, 'honest UA');
  calls.push({ kind, date: p.searchdate, t: clock.t });
  if (fail) { const r = fail(kind, p, url); if (r) return r; }
  const body = hasPosting(p.searchdate) ? (kind === 'fx' ? fxRows(p.searchdate) : rateObj(p.searchdate)) : kind === 'fx' ? [] : EMPTY_RATE;
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json;charset=UTF-8' } });
};

let kv = makeKV();
function reset(t = '2026-11-16T12:00:00') {
  kxResetMemory(); kv = makeKV(); calls.length = 0; fail = null; withTona = false; postHm = 660;
  edge.on = false; edge.store.clear(); edge.puts.length = 0; at(t);
  KX.DAY_MAX = 120; KX.WALK_MAX = 6;
}
async function get(path, env = env0(kv), method = 'GET') {
  const ctx = ctxOf();
  const res = await W.fetch(new Request('https://panse.pages.dev' + path, { method }), env, ctx);
  await ctx.flush();
  const text = await res.text();
  let body = null; try { body = JSON.parse(text); } catch (e) { /* not JSON */ }
  return { status: res.status, cc: res.headers.get('cache-control') || '', text, body };
}
const fx = (env) => get('/api/koreaexim?kind=fx', env);
const rate = (env) => get('/api/koreaexim?kind=rate', env);
const KEYFORMS = keyForms(FXKEY, RATEKEY);
function noKey(text, where) { for (const f of KEYFORMS) assert.ok(!String(text).includes(f), 'key leaked into ' + where); }
function scanAll(extra = []) {
  for (const [k, v] of kv.m) { noKey(k, 'KV key'); noKey(v.value, 'KV ' + k); }
  for (const l of logs) noKey(l, 'console');
  for (const t of extra) noKey(t, 'response');
}

/* ── parsers ── */
await R.test('parseFx: comma numbers, JPY(100) per 100, KRW left out, [] = empty day, result 3 → auth', () => {
  const p = parseFx(fxRows('20261116'));
  const usd = p.items.find(x => x.code === 'USD'), jpy = p.items.find(x => x.code === 'JPY');
  assert.equal(p.items.length, CUR.length - 1);
  assert.ok(!p.items.some(x => x.code === 'KRW'));
  assert.ok(usd.base > 1300 && usd.base < 1400 && typeof usd.base === 'number');
  assert.equal(jpy.per, 100); assert.equal(p.items.find(x => x.code === 'IDR').per, 100); assert.equal(usd.per, 1);
  assert.ok(usd.tts > usd.base && usd.ttb < usd.base);
  assert.equal(p.items.find(x => x.code === 'BHD').base > 3500, true, '"3,536.73" with a thousands comma');
  assert.deepEqual(parseFx([]), { empty: true });
  assert.deepEqual(parseFx(null), { empty: true });
  assert.throws(() => parseFx([{ result: 3, cur_unit: null }]), e => e.code === 'auth');
  assert.throws(() => parseFx([{ result: 4 }]), e => e.code === 'limit');
  assert.throws(() => parseFx([{ result: 2 }]), e => e.code === 'data');
  assert.throws(() => parseFx({ hello: 1 }), e => e.code === 'shape');
});
await R.test('parseRate: five benchmark lists, tenors from the names, null / 0 dropped, TONA only when sent, order', () => {
  const p = parseRate(rateObj('20261116'));
  assert.deepEqual(p.items.map(x => x.key), ['SOFRON', 'ESTRON', 'EURIBOR1M', 'EURIBOR3M', 'EURIBOR6M', 'EURIBOR12M', 'TIBOR1M', 'TIBOR3M', 'TIBOR6M', 'TIBOR12M']);
  const t1 = p.items.find(x => x.key === 'TIBOR1M');
  assert.equal(t1.tenor, '1개월'); assert.equal(t1.months, 1); assert.equal(t1.cur, 'JPY'); assert.ok(Math.abs(t1.value - 1.43482) < 1e-9);
  assert.equal(p.items[0].tenor, '익일'); assert.equal(p.items[0].cur, 'USD');
  assert.ok(!p.items.some(x => /SWAP|CIRR/.test(x.key)), 'swap / CIRR lists are not part of it');
  withTona = true;
  assert.equal(parseRate(rateObj('20261116')).items[2].key, 'TONAON');
  withTona = false;
  assert.deepEqual(parseRate(EMPTY_RATE), { empty: true });
  assert.deepEqual(parseRate({ ...EMPTY_RATE, sofr_list: [rrow('USD', 'SOFR 익일물', null)] }), { empty: true }, 'a row without a value is no value');
  assert.deepEqual(parseRate([]), { empty: true });
  assert.throws(() => parseRate({ result: 3 }), e => e.code === 'auth');
  assert.throws(() => parseRate([{ result: 3 }]), e => e.code === 'auth');
  assert.throws(() => parseRate({ foo: [] }), e => e.code === 'shape');
});

/* ── the route ── */
await R.test('posted today (Mon 12:00): today\'s values, Friday as prev (one walk call), bp · change, numbers as numbers', async () => {
  reset();
  const r = await fx();
  assert.equal(r.status, 200);
  const b = r.body;
  assert.equal(b.kind, 'fx'); assert.equal(b.source, '한국수출입은행');
  assert.equal(b.date, '2026-11-16'); assert.equal(b.today, true); assert.equal(b.firstSeen, '12:00'); assert.equal(b.exact, false, 'nobody saw it empty: the posting time is unknown');
  assert.ok(!b.waiting && !b.stale);
  assert.equal(b.prev.date, '2026-11-13', 'the weekend is skipped without a call');
  assert.deepEqual(calls.map(c => c.date), ['20261116', '20261113']);
  const usd = b.items.find(x => x.code === 'USD');
  assert.equal(typeof usd.change, 'number');
  assert.ok(Math.abs(usd.change - (usd.base - b.prev.items.find(x => x.code === 'USD').base)) < 0.006);
  const q = await rate();
  assert.equal(q.status, 200);
  const e3 = q.body.items.find(x => x.key === 'EURIBOR3M');
  assert.ok(Math.abs(e3.bp - 0.3) < 1e-9, `3 days × 0.001 = 0.3bp, got ${e3.bp}`);
  assert.equal(q.body.prev.date, '2026-11-13');
  scanAll([r.text, q.text]);
});
await R.test('a day\'s copy is never asked again (same isolate and a new one)', async () => {
  reset();
  await fx(); await rate();
  const n0 = calls.length;
  advance(3 * 3600e3);
  await fx(); await rate();
  kxResetMemory();                                       // a new isolate: KV only
  await fx(); await rate();
  assert.equal(calls.length, n0);
});
await R.test('before the posting: Friday + waiting, checks every 5 min from 10:30, exact firstSeen when it appears', async () => {
  reset('2026-11-16T10:40:00');
  postHm = 11 * 60 + 2;
  let r = await fx();
  assert.equal(r.body.date, '2026-11-13'); assert.equal(r.body.today, false); assert.equal(r.body.waiting, true); assert.ok(!r.body.stale);
  assert.equal(r.body.firstSeen, null, 'Friday was fetched later: no first-seen time');
  assert.equal(r.body.prev.date, '2026-11-12');
  assert.deepEqual(calls.map(c => c.date), ['20261116', '20261113', '20261112']);
  at('2026-11-16T10:44:00'); await fx();
  assert.equal(calls.length, 3, 'within 5 min: no call');
  at('2026-11-16T10:46:00'); await fx();
  assert.equal(calls.length, 4, 'after 5 min: asked again (still empty)');
  at('2026-11-16T10:51:00'); await fx();
  at('2026-11-16T10:56:00'); await fx();
  at('2026-11-16T11:01:30'); await fx();
  at('2026-11-16T11:06:40'); r = await fx();
  assert.equal(r.body.today, true); assert.equal(r.body.firstSeen, '11:06'); assert.equal(r.body.exact, true, 'empty 5 min before → the posting time is known');
  assert.equal(r.body.prev.date, '2026-11-13');
  const n1 = calls.length;
  at('2026-11-16T15:00:00'); await fx();
  assert.equal(calls.length, n1);
});
await R.test('a late first look is not exact (empty seen long before)', async () => {
  reset('2026-11-16T10:35:00');
  await fx();
  at('2026-11-16T13:20:00');
  const r = await fx();
  assert.equal(r.body.today, true); assert.equal(r.body.firstSeen, '13:20'); assert.equal(r.body.exact, false);
});
await R.test('early morning: never before 08:00, then once an hour to 10:30', async () => {
  reset('2026-11-16T06:00:00');
  let r = await fx();
  assert.ok(!calls.some(c => c.date === '20261116'), 'not asked at 06:00');
  assert.equal(r.body.waiting, true); assert.equal(r.body.date, '2026-11-13');
  at('2026-11-16T07:59:00'); await fx();
  assert.ok(!calls.some(c => c.date === '20261116'), 'not asked at 07:59');
  at('2026-11-16T08:00:00'); await fx();
  assert.equal(calls.filter(c => c.date === '20261116').length, 1, 'asked at 08:00');
  at('2026-11-16T08:40:00'); await fx();
  at('2026-11-16T08:59:00'); await fx();
  assert.equal(calls.filter(c => c.date === '20261116').length, 1, 'hourly');
  at('2026-11-16T09:01:00'); await fx();
  assert.equal(calls.filter(c => c.date === '20261116').length, 2);
});
await R.test('weekend: no call for Saturday · Sunday, Friday shown, not waiting, not stale', async () => {
  reset('2026-11-21T15:00:00');
  const r = await fx();
  assert.equal(r.body.date, '2026-11-20'); assert.equal(r.body.today, false); assert.ok(!r.body.waiting && !r.body.stale);
  assert.ok(!calls.some(c => c.date === '20261121' || c.date === '20261122'));
  at('2026-11-22T09:00:00'); kxResetMemory();
  const n0 = calls.length;
  await fx();
  assert.equal(calls.length, n0, 'Sunday: everything from KV');
});
await R.test('a weekday holiday in the walk: remembered as empty, never asked again', async () => {
  reset('2026-11-12T09:00:00');                          // Thu before the posting; Wed 11-11 is a holiday here
  let r = await rate();
  assert.equal(r.body.date, '2026-11-10'); assert.equal(r.body.prev.date, '2026-11-09');
  assert.deepEqual(calls.map(c => c.date), ['20261112', '20261111', '20261110', '20261109']);
  assert.equal(kv.json('kxim:d:rate:20261111').empty, true);
  kxResetMemory();
  at('2026-11-12T09:30:00');
  r = await rate();
  assert.equal(calls.length, 4, 'holiday and both copies from KV');
});
await R.test('the walk stops at WALK_MAX unknown days and goes on with the next request', async () => {
  reset('2026-11-16T09:00:00');
  KX.WALK_MAX = 1;
  fail = (kind, p) => (p.searchdate === '20261113' ? new Response('[]', { status: 200 }) : null);   // Friday "empty" too
  let r = await fx();
  assert.equal(r.status, 503, 'nothing found within one call');
  r = await fx();
  assert.equal(r.status, 200); assert.equal(r.body.date, '2026-11-12');
});
await R.test('auth error (result 3): last copy served stale, 60 min cool-down, record without the key', async () => {
  reset('2026-11-13T15:00:00');
  await fx();                                            // Friday's copy
  at('2026-11-16T12:00:00'); kxResetMemory();
  fail = () => new Response(JSON.stringify([{ result: 3, cur_unit: null, ttb: null }]), { status: 200 });
  let r = await fx();
  assert.equal(r.status, 200); assert.equal(r.body.date, '2026-11-13'); assert.equal(r.body.stale, true);
  const cool = kv.json('kxim:cool:fx');
  assert.equal(cool.code, 'auth'); assert.equal(Math.round((cool.until - clock.t) / 60e3), 60);
  const rec = kv.json('kxim:err:fx');
  assert.equal(rec.code, 'auth'); assert.equal(rec.result, 3); assert.equal(rec.date, '20261116');
  const n0 = calls.length;
  at('2026-11-16T12:30:00'); r = await fx();
  assert.equal(calls.length, n0, 'cooling down: no call'); assert.equal(r.body.stale, true);
  at('2026-11-16T13:01:00'); fail = null; r = await fx();
  assert.equal(r.body.today, true); assert.ok(!r.body.stale);
  scanAll([r.text]);
});
await R.test('nothing in KV + auth error → 503 {code:auth}, not edge-cached', async () => {
  reset(); edge.on = true;
  fail = () => new Response(JSON.stringify([{ result: 3 }]), { status: 200 });
  const r = await fx();
  assert.equal(r.status, 503); assert.equal(r.body.code, 'auth'); assert.match(r.cc, /no-store/);
  assert.equal(edge.store.size, 0);
});
await R.test('daily limit (result 4) cools down until KST midnight', async () => {
  reset('2026-11-16T12:00:00');
  fail = (kind) => new Response(JSON.stringify(kind === 'fx' ? [{ result: 4 }] : { result: 4 }), { status: 200 });
  await fx(); await rate();
  for (const k of ['fx', 'rate']) {
    const c = kv.json('kxim:cool:' + k);
    assert.equal(c.code, 'limit'); assert.equal(c.until, KST('2026-11-17T00:00:00'));
  }
});
await R.test('network · timeout · HTTP 500 · HTML: 10 min cool-down, the URL (with the key) never kept', async () => {
  for (const [name, f, code] of [
    ['network', (k, p, url) => { throw new TypeError('fetch failed: ' + url); }, 'network'],
    ['timeout', () => { throw new DOMException('The operation timed out: ' + FXKEY, 'TimeoutError'); }, 'timeout'],
    ['http', () => new Response('oops ' + FXKEY, { status: 500 }), 'http'],
    ['html', (k, p, url) => new Response('<html>' + url + '</html>', { status: 200, headers: { 'content-type': 'text/html' } }), 'json'],
  ]) {
    reset(); fail = f;
    const r = await fx();
    assert.equal(r.status, 503, name); assert.equal(r.body.code, code, name);
    const c = kv.json('kxim:cool:fx');
    assert.equal(c.code, code); assert.equal(Math.round((c.until - clock.t) / 60e3), 10, name);
    scanAll([r.text]);
  }
});
await R.test('no key: 503 {code:nokey}, no call, no cool-down', async () => {
  reset();
  const r = await fx(env0(kv, { KOREAEXIM_FX_KEY: undefined }));
  assert.equal(r.status, 503); assert.equal(r.body.code, 'nokey'); assert.equal(calls.length, 0);
  assert.equal(kv.json('kxim:cool:fx'), null);
  const q = await rate(env0(kv, { KOREAEXIM_FX_KEY: undefined }));
  assert.equal(q.status, 200, 'the other kind is not affected');
});
await R.test('daily cap: at most DAY_MAX upstream calls per kind and KST day, then stale (and the counter is in KV)', async () => {
  reset('2026-11-16T10:30:00');
  postHm = null;                                         // a holiday-like Monday: never posted
  KX.DAY_MAX = 6;
  let last;
  for (let i = 0; i < 40; i++) { last = await fx(); advance(5 * 60e3 + 1000); }
  const today = calls.filter(c => c.kind === 'fx').length;
  assert.ok(today <= 6, 'calls ' + today);
  assert.equal(+kv.m.get('kxim:n:fx:20261116').value, today);
  assert.equal(last.status, 200); assert.equal(last.body.date, '2026-11-13'); assert.equal(last.body.stale, true);
});
await R.test('a realistic weekday: ≤ 12 calls per kind (posting at 11:00, a visit every 30 s all day)', async () => {
  reset('2026-11-16T00:00:30'); edge.on = true;
  for (let t = clock.t; t < KST('2026-11-16T23:59:00'); t += 30e3) { at(new Date(t + 9 * 3600e3).toISOString().slice(0, 19)); await fx(); await rate(); }
  const f = calls.filter(c => c.kind === 'fx').length, r = calls.filter(c => c.kind === 'rate').length;
  say(`     a weekday at one visit per 30 s: fx ${f} calls · rate ${r} calls`);
  assert.ok(f <= 12 && r <= 12, `fx ${f} rate ${r}`);
});
await R.test('edge TTL: today 600 s, waiting 10:30–14:00 120 s, otherwise 300 s, never past midnight', async () => {
  assert.equal(kxTtl({ today: true }, KST('2026-11-16T12:00:00')), 600);
  assert.equal(kxTtl({ today: false }, KST('2026-11-16T10:45:00')), 120);
  assert.equal(kxTtl({ today: false }, KST('2026-11-16T08:00:00')), 300);
  assert.equal(kxTtl({ today: false }, KST('2026-11-21T12:00:00')), 300, 'Saturday');
  assert.equal(kxTtl({ today: true }, KST('2026-11-16T23:58:00')), 120);
  reset(); edge.on = true;
  const r = await fx();
  assert.match(r.cc, /max-age=600/);
  const n0 = calls.length;
  await fx();
  assert.equal(calls.length, n0);
});
await R.test('KV lag: a copy another colo already wrote keeps its earlier firstSeen', async () => {
  reset('2026-11-16T11:10:00');
  kv.m.set('kxim:st:fx', { value: JSON.stringify({ day: '20261116', emptyAt: KST('2026-11-16T11:00:00') }), exp: null });
  const other = { items: parseFx(fxRows('20261116')).items, seen: KST('2026-11-16T11:05:00'), exact: true };
  const realGet = kv.get;
  let hidden = true;
  kv.get = async (k, t) => (hidden && k === 'kxim:d:fx:20261116' ? (hidden = false, null) : realGet.call(kv, k, t));   // the first read misses it
  kv.m.set('kxim:d:fx:20261116', { value: JSON.stringify(other), exp: null });
  const r = await fx();
  kv.get = realGet;
  assert.equal(r.body.firstSeen, '11:05'); assert.equal(r.body.exact, true);
});
await R.test('TONA appears in rate items only when the source sends it', async () => {
  reset(); withTona = true;
  const r = await rate();
  assert.ok(r.body.items.some(x => x.key === 'TONAON' && x.family === 'TONA' && x.cur === 'JPY'));
});
await R.test('validation: kind missing / wrong → 400, POST → 405; probe still answers without the key in it', async () => {
  reset();
  assert.equal((await get('/api/koreaexim')).status, 400);
  assert.equal((await get('/api/koreaexim?kind=swap')).status, 400);
  assert.equal((await get('/api/koreaexim?kind=fx', env0(kv), 'POST')).status, 405);
  const p = await get('/api/koreaexim/probe');
  assert.equal(p.status, 200); assert.equal(p.body.fx.ok, true); assert.equal(p.body.rate.ok, true);
  assert.ok(kv.m.has('kxim:calls:20261116') && !kv.m.has('kxim:n:fx:20261116'), 'the probe keeps its own counter');
  fail = (k, q, url) => { throw new TypeError('connect failed ' + url); };
  const p2 = await get('/api/koreaexim/probe?d=20261113');
  assert.equal(p2.body.fx.ok, false);
  scanAll([p.text, p2.text]);
});
await R.test('nothing with the key anywhere: KV, console, every response of this run', async () => { scanAll(); });

R.done();
