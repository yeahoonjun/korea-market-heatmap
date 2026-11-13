// QA: GET /api/disclosures/today (공시 배지 서버, AGENTS §3-29) against a fake KV, a fake clock and a mocked fetch
// that replays OpenDART list.json-shaped pages. No network, no real key.
//   node qa/worker/test_disclosures_today.mjs
// Each scenario imports a fresh copy of worker/src/index.js (?i=N) so module memory starts empty, like a new isolate.
import assert from 'node:assert/strict';

const SRC = new URL('../../worker/src/index.js', import.meta.url).href;
const KEY = 'fake-test-key-not-a-secret';
const ASSET = 'https://assets.test/web/';
const KST = s => Date.parse(s + '+09:00');

/* ── fake clock ── */
let clock = KST('2026-11-13T10:00:00');
Date.now = () => clock;

/* ── caches.default (per test switchable) ── */
let cacheOn = false;
const cacheStore = new Map(), cachePuts = [];
globalThis.caches = {
  default: {
    async match(req) {
      if (!cacheOn) return undefined;
      const e = cacheStore.get(req.url);
      return e && e.exp > clock ? e.res.clone() : undefined;
    },
    async put(req, res) {
      cachePuts.push({ url: req.url, status: res.status });
      const m = /max-age=(\d+)/.exec(res.headers.get('cache-control') || '');
      if (m && cacheOn) cacheStore.set(req.url, { exp: clock + m[1] * 1000, res: res.clone() });
    },
  },
};

/* ── fake KV (single + bulk get like Workers KV, TTL on the fake clock) ── */
function makeKV() {
  const m = new Map();
  const log = { gets: 0, puts: [] };
  const read = (k, type) => {
    const e = m.get(k);
    if (!e || (e.exp && e.exp <= clock)) return null;
    return type === 'json' ? JSON.parse(e.value) : e.value;
  };
  return {
    m, log,
    async get(key, type) {
      if (Array.isArray(key)) { log.gets += key.length; return new Map(key.map(k => [k, read(k, type)])); }
      log.gets++;
      return read(key, type);
    },
    async put(key, value, opt) {
      log.puts.push({ key, ttl: opt && opt.expirationTtl });
      m.set(key, { value: String(value), exp: opt && opt.expirationTtl ? clock + opt.expirationTtl * 1000 : null });
    },
    json(k) { return read(k, 'json'); },
  };
}

/* ── universe fixture: KOSPI 1xxxxx (200 in K, 100 in X), KOSDAQ 2xxxxx (150 in Q, 50 in X) ── */
const kospi = Array.from({ length: 300 }, (_, i) => '1' + String(i).padStart(5, '0'));
const kosdaq = Array.from({ length: 200 }, (_, i) => '2' + String(i).padStart(5, '0'));
const UNIVERSE = {
  K: kospi.slice(0, 200).map(c => c + '00').join(''),
  Q: kosdaq.slice(0, 150).map(c => c + '00').join(''),
  X: kospi.slice(200).map(c => c + '00K').join('') + kosdaq.slice(150).map(c => c + '00Q').join(''),
  I: [['반도체와반도체장비', '정보기술']],
};

/* ── OpenDART fixtures ── */
// db[YYYYMMDD][Y|K] = items newest first (rcept_no grows with time). onPage(p, db) can mutate db before a page is served.
let db = {}, onPage = null, dartImpl = null, seq = 0;
const calls = [];
const TITLES = ['분기보고서 (2026.09)', '주식등의대량보유상황보고서(일반)', '연결재무제표기준영업(잠정)실적(공정공시)',
  '임원ㆍ주요주주특정증권등소유상황보고서', '기업설명회(IR)개최(안내공시)', '단일판매ㆍ공급계약체결'];
function item(day, cls, code, extra = {}) {
  seq++;
  const name = extra.corp_name || '회사' + code;
  return {
    corp_code: String(10000000 + seq), corp_name: name, stock_code: code, corp_cls: cls,
    report_nm: extra.report_nm || TITLES[seq % TITLES.length], rcept_no: day + String(seq).padStart(6, '0'),
    flr_nm: extra.flr_nm || name, rcept_dt: day, rm: extra.rm || '',
  };
}
// n items for one market/day, oldest first in creation, returned newest first
function many(day, cls, n, pick) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(item(day, cls, pick(i)));
  return out.reverse();
}
const addTop = (day, cls, items) => { db[day] = db[day] || {}; db[day][cls] = [...items.slice().reverse(), ...(db[day][cls] || [])]; };
function serve(p) {
  const list = (db[p.bgn_de] && db[p.bgn_de][p.corp_cls]) || [];
  if (!list.length) return { status: '013', message: '조회된 데이타가 없습니다.' };
  const n = +p.page_count, page = +p.page_no, tp = Math.ceil(list.length / n);
  if (page > tp) return { status: '013', message: '조회된 데이타가 없습니다.' };
  return { status: '000', message: '정상', page_no: page, page_count: n, total_count: list.length, total_page: tp, list: list.slice((page - 1) * n, page * n) };
}
globalThis.fetch = async (input, init) => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  if (u.href === ASSET + 'universe.json') return new Response(JSON.stringify(UNIVERSE));
  if (u.origin === 'https://opendart.fss.or.kr' && u.pathname === '/api/list.json') {
    const p = Object.fromEntries(u.searchParams);
    calls.push({ day: p.bgn_de, cls: p.corp_cls, page: +p.page_no });
    assert.equal(p.crtfc_key, KEY);
    assert.equal(p.bgn_de, p.end_de, 'one day per call');
    assert.ok(p.corp_cls === 'Y' || p.corp_cls === 'K');
    assert.equal(p.page_count, '100');
    assert.ok(init && init.signal instanceof AbortSignal, 'every upstream call has a timeout signal');
    assert.match(init.headers['user-agent'], /panse/);
    if (onPage) onPage(p, db);
    const r = dartImpl ? await dartImpl(p) : serve(p);
    return r instanceof Response ? r : new Response(JSON.stringify(r), { headers: { 'content-type': 'application/json' } });
  }
  throw new Error('unexpected fetch ' + u.origin + u.pathname);
};

/* ── harness ── */
let nInst = 0;
const fresh = async () => (await import(SRC + '?i=' + (++nInst))).default;
const env0 = kv => ({ ASSET_BASE: ASSET, REPLAY: kv, DART_KEY: KEY });
async function hit(W, env, colo) {
  const req = new Request('https://panse.pages.dev/api/disclosures/today');
  if (colo) Object.defineProperty(req, 'cf', { value: { colo } });
  const pending = [];
  const res = await W.fetch(req, env, { waitUntil: p => pending.push(p) });
  await Promise.all(pending);
  const text = await res.text();
  assert.ok(!text.includes(KEY), 'key never in a response');
  return { status: res.status, body: JSON.parse(text), cc: res.headers.get('cache-control') };
}
const since = () => calls.splice(0).length;              // upstream calls since the last check
const at = s => { clock = KST(s); };
const noKeyInKV = kv => { for (const [k, v] of kv.m) assert.ok(!v.value.includes(KEY) && !k.includes(KEY), 'key never in KV: ' + k); };
function reset() { db = {}; onPage = null; dartImpl = null; calls.length = 0; cacheOn = false; cacheStore.clear(); cachePuts.length = 0; }

const results = [];
async function test(name, fn) {
  reset();
  try { await fn(); results.push(['PASS', name]); }
  catch (e) { results.push(['FAIL', name, e && e.stack || e]); }
}

/* ── fixtures of a busy Friday (2026-11-13) ── */
const FRI = '20261113', THU = '20261112', WED = '20261111', TUE = '20261110', SAT = '20261114', MON = '20261116';
function busyFriday() {
  // KOSPI (Y): 250 filings — 235 of universe stocks, 10 of a code outside the universe, 5 without a stock code
  const y = many(FRI, 'Y', 235, i => kospi[i % 300]);
  for (let i = 0; i < 10; i++) y.splice(i * 20, 0, item(FRI, 'Y', '999990'));
  for (let i = 0; i < 5; i++) y.splice(i * 30 + 7, 0, item(FRI, 'Y', ' '));
  // special rows (newest)
  const specials = [
    item(FRI, 'Y', kospi[1], { report_nm: '[기재정정]주요사항보고서(자기주식취득결정)' }),
    item(FRI, 'Y', kospi[2], { report_nm: '주식등의대량보유상황보고서(일반)', flr_nm: '국민연금공단' }),
    item(FRI, 'Y', kospi[3], { report_nm: '분기보고서  (2026.09) ', rm: '정' }),
    item(FRI, 'Y', kospi[4], { report_nm: '유상증자결정', rm: '유철' }),
  ];
  db[FRI] = { Y: [...specials.reverse(), ...y], K: many(FRI, 'K', 130, i => kosdaq[i % 200]) };
  return { y: db[FRI].Y.length, k: db[FRI].K.length };
}

/* ═════════ scenarios ═════════ */

await test('busy day: full first sync, filter, shape, kinds, notes, filer, first seen, KV', async () => {
  const kv = makeKV(), W = await fresh();
  const n = busyFriday();
  assert.deepEqual(n, { y: 254, k: 130 });
  at('2026-11-13T10:00:00');
  const r = await hit(W, env0(kv));
  assert.equal(r.status, 200);
  assert.equal(r.cc, 'public, max-age=30');
  const b = r.body;
  assert.deepEqual(Object.keys(b), ['date', 'asOf', 'rows', 'counts', 'since']);
  assert.equal(b.date, '2026-11-13');
  assert.equal(b.asOf, '2026-11-13T10:00:00+09:00');
  assert.equal(b.since, '10:00');
  assert.equal(b.stale, undefined);
  // 254 Y − 10 outside universe − 5 without code = 239; K all 130 in universe
  assert.deepEqual(b.counts, { K: 239, Q: 130, total: 369 });
  assert.equal(b.rows.length, 369);
  const rs = b.rows.map(x => x.r);
  assert.deepEqual(rs, rs.slice().sort().reverse(), 'newest first');
  assert.equal(new Set(rs).size, rs.length, 'no duplicates');
  for (const x of b.rows) {
    assert.match(x.c, /^[0-9A-Z]{6}$/);
    assert.ok(['정기', '실적', '주요', '지분', '기타'].includes(x.k), x.k);
    assert.equal(x.s, '10:00');
    assert.ok(Object.keys(x).every(k => ['c', 't', 'k', 'n', 'r', 's', 'f'].includes(k)));
  }
  const by = t => b.rows.find(x => x.t === t);
  assert.deepEqual(by('주요사항보고서(자기주식취득결정)'), { c: kospi[1], t: '주요사항보고서(자기주식취득결정)', k: '주요', n: '기재정정', r: b.rows.find(x => x.n === '기재정정').r, s: '10:00' });
  assert.equal(b.rows.find(x => x.f).f, '국민연금공단');
  assert.equal(b.rows.find(x => x.f).k, '지분');
  assert.equal(b.rows.filter(x => x.f).length, 1, 'filer only when it differs from the company');
  assert.equal(b.rows.find(x => x.c === kospi[3] && x.n).t, '분기보고서 (2026.09)', 'whitespace collapsed');
  assert.equal(b.rows.find(x => x.c === kospi[3] && x.n).n, '정정본 있음');
  assert.equal(b.rows.find(x => x.c === kospi[4] && x.n).n, '철회');
  assert.ok(!b.rows.some(x => x.c === '999990'), 'outside universe dropped');
  // calls: Y 3 pages (1, then 2+3 in one batch), K 2 pages
  const c = calls.splice(0);
  assert.equal(c.length, 5);
  assert.deepEqual(c.filter(x => x.cls === 'Y').map(x => x.page).sort(), [1, 2, 3]);
  assert.deepEqual(c.filter(x => x.cls === 'K').map(x => x.page).sort(), [1, 2]);
  const snap = kv.json('dart:today');
  assert.equal(snap.date, FRI);
  assert.equal(snap.calls, 5);
  assert.deepEqual(snap.mk.Y.x.length, 15, 'filtered-out Y filings remembered for counting');
  const seen = kv.json('dart:seen:' + FRI);
  assert.equal(Object.keys(seen).length, 369);
  assert.ok(Object.values(seen).every(v => v === '10:00'));
  assert.equal(kv.log.puts.find(p => p.key === 'dart:today').ttl, 8 * 86400);
  noKeyInKV(kv);

  // +30 s: memory snapshot, no upstream
  at('2026-11-13T10:00:30');
  assert.equal((await hit(W, env0(kv))).body.rows.length, 369);
  assert.equal(since(), 0);

  // +61 s: 3 new KOSPI + 1 new KOSDAQ filing on top → page 1 of each market only
  at('2026-11-13T10:01:01');
  addTop(FRI, 'Y', [item(FRI, 'Y', kospi[10]), item(FRI, 'Y', kospi[11]), item(FRI, 'Y', kospi[250])]);
  addTop(FRI, 'K', [item(FRI, 'K', kosdaq[160])]);
  const r2 = (await hit(W, env0(kv))).body;
  assert.equal(since(), 2, 'incremental: page 1 per market');
  assert.equal(r2.rows.length, 373);
  assert.deepEqual(r2.rows.slice(0, 4).map(x => x.s), ['10:01', '10:01', '10:01', '10:01']);
  assert.equal(r2.rows.filter(x => x.s === '10:00').length, 369, 'older rows keep their first-seen time');
  assert.equal(r2.since, '10:00');
  assert.equal(Object.keys(kv.json('dart:seen:' + FRI)).length, 373);

  // 120 new KOSPI filings in a minute → Y pages 1–2 (stops before 3–4), K page 1
  at('2026-11-13T10:02:05');
  addTop(FRI, 'Y', Array.from({ length: 120 }, (_, i) => item(FRI, 'Y', kospi[i])));
  const r3 = (await hit(W, env0(kv))).body;
  const c3 = calls.splice(0);
  assert.deepEqual(c3.map(x => x.cls + x.page).sort(), ['K1', 'Y1', 'Y2']);
  assert.equal(r3.rows.length, 493);
  assert.equal(r3.rows.filter(x => x.s === '10:02').length, 120);

  // page shift while paging: 5 more arrive between page 1 and page 2 → page 2 repeats rows of page 1 (deduped);
  // the 5 late ones are caught by the next refresh
  at('2026-11-13T10:03:10');
  addTop(FRI, 'Y', Array.from({ length: 101 }, (_, i) => item(FRI, 'Y', kospi[i + 20])));
  let shifted = false;
  onPage = p => { if (p.corp_cls === 'Y' && p.page_no === '2' && !shifted) { shifted = true; addTop(FRI, 'Y', Array.from({ length: 5 }, (_, i) => item(FRI, 'Y', kospi[i + 40]))); } };
  const r4 = (await hit(W, env0(kv))).body;
  assert.equal(new Set(r4.rows.map(x => x.r)).size, r4.rows.length, 'no duplicate rcept_no after a page shift');
  assert.equal(r4.rows.length, 493 + 101);
  calls.length = 0;
  onPage = null;
  at('2026-11-13T10:04:11');
  const r5 = (await hit(W, env0(kv))).body;
  assert.equal(r5.rows.length, 493 + 106, 'late arrivals picked up next time');
  assert.equal(since(), 2);

  // DART glitch: KOSPI answers 013 for a day that had filings → treated as a failure of that market (rows kept, stale)
  at('2026-11-13T10:05:15');
  addTop(FRI, 'K', [item(FRI, 'K', kosdaq[5])]);
  dartImpl = p => (p.corp_cls === 'Y' ? { status: '013', message: '조회된 데이타가 없습니다.' } : serve(p));
  const r6 = (await hit(W, env0(kv))).body;
  assert.equal(r6.stale, true);
  assert.equal(r6.rows.length, 493 + 106 + 1, 'KOSPI rows kept, KOSDAQ updated');
  assert.equal(r6.date, '2026-11-13');
  dartImpl = null;
  at('2026-11-13T10:06:20');
  const r7 = (await hit(W, env0(kv))).body;
  assert.equal(r7.stale, undefined, 'recovers on the next good refresh');
  noKeyInKV(kv);
});

await test('Saturday: today 013 → falls back to Friday (final), only today is probed afterwards; seen map of Friday applied', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  // Friday's stamps from when it was "today" (two rows), recorded by an earlier day
  const fr = db[FRI].Y.filter(x => /^1/.test(x.stock_code)).slice(0, 2).map(x => x.rcept_no);
  await kv.put('dart:seen:' + FRI, JSON.stringify({ [fr[0]]: '15:42', [fr[1]]: '15:40' }), { expirationTtl: 8 * 86400 });
  at('2026-11-14T10:00:00');
  const b = (await hit(W, env0(kv))).body;
  const c = calls.splice(0);
  assert.deepEqual(c.filter(x => x.day === SAT).map(x => x.cls).sort(), ['K', 'Y'], 'today probed first');
  assert.equal(c.filter(x => x.day === FRI).length, 5);
  assert.equal(b.date, '2026-11-13');
  assert.equal(b.since, undefined, 'no since for a past day');
  assert.equal(b.rows.length, 369);
  assert.equal(b.rows.find(x => x.r === fr[0]).s, '15:42');
  assert.equal(b.rows.filter(x => x.s).length, 2, 'no invented first-seen times for a past day');
  assert.equal(kv.json('dart:today').final, true);
  // within 5 min (off-hours TTL 300 s) nothing; after it only the two probes of Saturday
  at('2026-11-14T10:04:59');
  await hit(W, env0(kv));
  assert.equal(since(), 0);
  at('2026-11-14T10:05:01');
  const b2 = (await hit(W, env0(kv))).body;
  const c2 = calls.splice(0);
  assert.deepEqual(c2.map(x => x.day + x.cls).sort(), [SAT + 'K', SAT + 'Y']);
  assert.equal(b2.date, '2026-11-13');
  assert.equal(b2.asOf, '2026-11-14T10:05:01+09:00', 'asOf = last successful check');
});

await test('Monday holiday then Thursday after a Wednesday holiday: walk back ≤ 4 days, empty days remembered', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-16T10:00:00');                      // Mon (holiday: nothing filed)
  const b = (await hit(W, env0(kv))).body;
  assert.equal(b.date, '2026-11-13');
  const c = calls.splice(0);
  assert.equal(c.filter(x => x.day === MON).length, 2);
  assert.equal(c.filter(x => x.day !== MON && x.day !== FRI).length, 0, 'weekend days are not asked');
  // a quiet weekday after 10:00 is treated as a holiday → 5-minute refresh
  at('2026-11-16T10:02:00');
  await hit(W, env0(kv));
  assert.equal(since(), 0);

  const kv2 = makeKV(), W2 = await fresh();
  db = {};
  db[TUE] = { Y: many(TUE, 'Y', 30, i => kospi[i]), K: many(TUE, 'K', 20, i => kosdaq[i]) };
  at('2026-11-12T06:30:00');                      // Thu before filings start; Wed was a holiday
  const t = (await hit(W2, env0(kv2))).body;
  assert.equal(t.date, '2026-11-10');
  assert.deepEqual(calls.splice(0).map(x => x.day + x.cls + x.page).sort(), [TUE + 'K1', TUE + 'Y1', WED + 'K1', WED + 'Y1', THU + 'K1', THU + 'Y1']);
  assert.deepEqual(kv2.json('dart:today').empty, [WED]);
  at('2026-11-12T06:35:01');
  await hit(W2, env0(kv2));
  assert.deepEqual(calls.splice(0).map(x => x.day).sort(), [THU, THU], 'Wednesday not asked again');
  // someone keeps the page open: a check every 5 min (TTL 300 s before 07:00, 60 s after)
  for (let m = 40; m <= 90; m += 5) { clock = KST('2026-11-12T06:00:00') + m * 60e3 + 1000; await hit(W2, env0(kv2)); }
  calls.length = 0;
  // first filing of Thursday at 07:31 → the day switches to Thursday; the watch began 06:30 (continuous), so s is real
  at('2026-11-12T07:31:02');
  addTop(THU, 'Y', [item(THU, 'Y', kospi[7], { report_nm: '연결재무제표기준영업(잠정)실적(공정공시)' })]);
  const t3 = (await hit(W2, env0(kv2))).body;
  assert.equal(t3.date, '2026-11-12');
  assert.equal(t3.rows.length, 1);
  assert.equal(t3.rows[0].s, '07:31');
  assert.equal(t3.rows[0].k, '실적');
  assert.equal(t3.since, '06:30', 'watched since the first check of the day');
});

await test('020 rate limit → stale snapshot, 10-minute cool-down shared through KV, then recovery', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-13T11:00:00');
  await hit(W, env0(kv));
  calls.length = 0;
  at('2026-11-13T11:01:01');
  dartImpl = () => ({ status: '020', message: '요청 제한을 초과하였습니다.' });
  const r = await hit(W, env0(kv));
  assert.equal(r.status, 200);
  assert.equal(r.body.stale, true);
  assert.equal(r.body.rows.length, 369);
  assert.equal(r.body.asOf, '2026-11-13T11:00:00+09:00', 'asOf stays at the last good check');
  assert.ok(since() <= 2);
  const cool = kv.json('dart:cool');
  assert.equal(cool.why, 'rate');
  assert.equal(cool.until, KST('2026-11-13T11:11:01'));
  // another isolate (fresh module, same KV) during the cool-down: no upstream calls
  dartImpl = null;
  const W2 = await fresh();
  at('2026-11-13T11:05:00');
  const r2 = await hit(W2, env0(kv));
  assert.equal(r2.body.stale, true);
  assert.equal(since(), 0);
  at('2026-11-13T11:10:59');
  await hit(W, env0(kv));
  assert.equal(since(), 0);
  at('2026-11-13T11:11:02');
  const r3 = await hit(W, env0(kv));
  assert.equal(r3.body.stale, undefined);
  assert.equal(since(), 2);
});

await test('network error / timeout: no snapshot → 502 not cached + back-off; with snapshot → stale', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  cacheOn = true;
  at('2026-11-13T12:00:00');
  dartImpl = () => { throw new TypeError('fetch failed'); };
  const r = await hit(W, env0(kv));
  assert.equal(r.status, 502);
  assert.equal(r.cc, 'no-store');
  assert.ok(r.body.error);
  assert.ok(!cachePuts.some(p => p.url.includes('dis-today')), 'errors are never edge-cached');
  assert.equal(since(), 2);
  assert.equal(kv.json('dart:cool').why, 'network');
  at('2026-11-13T12:00:10');
  const r2 = await hit(W, env0(kv));
  assert.equal(r2.status, 503);
  assert.equal(since(), 0, 'backs off instead of hammering a failing upstream');
  dartImpl = null;
  at('2026-11-13T12:01:01');
  const r3 = await hit(W, env0(kv));
  assert.equal(r3.status, 200);
  assert.equal(r3.body.rows.length, 369);
  calls.length = 0;
  // timeout with a snapshot
  cacheOn = false;
  at('2026-11-13T12:02:02');
  dartImpl = () => { throw new DOMException('The operation was aborted due to timeout', 'TimeoutError'); };
  const r4 = await hit(W, env0(kv));
  assert.equal(r4.status, 200);
  assert.equal(r4.body.stale, true);
  assert.equal(kv.json('dart:cool').why, 'timeout');
  assert.equal(kv.json('dart:today').err, 'timeout');
  // HTTP 500 and a bad body are failures too
  dartImpl = () => new Response('oops', { status: 500 });
  at('2026-11-13T12:03:03');
  assert.equal((await hit(W, env0(kv))).body.stale, true);
  assert.equal(kv.json('dart:cool').why, 'http');
  dartImpl = () => new Response('<html>', { status: 200 });
  at('2026-11-13T12:04:04');
  assert.equal((await hit(W, env0(kv))).body.stale, true);
  assert.equal(kv.json('dart:cool').why, 'json');
  noKeyInKV(kv);
});

await test('key error 010 → 30-minute cool-down; missing DART_KEY → 503 without calls', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-13T13:00:00');
  dartImpl = () => ({ status: '010', message: '등록되지 않은 키입니다.' });
  const r = await hit(W, env0(kv));
  assert.equal(r.status, 502);
  assert.equal(kv.json('dart:cool').why, 'key');
  assert.equal(kv.json('dart:cool').until, KST('2026-11-13T13:30:00'));
  const W2 = await fresh(), kv2 = makeKV();
  calls.length = 0;
  const r2 = await hit(W2, { ASSET_BASE: ASSET, REPLAY: kv2 });
  assert.equal(r2.status, 503);
  assert.equal(since(), 0);
  const r3 = await hit(W2, { ASSET_BASE: ASSET, DART_KEY: KEY });
  assert.equal(r3.status, 503, 'no KV binding');
});

await test('two colos sharing KV: the writer polls, a follower waits TTL + 2 min', async () => {
  const kv = makeKV(), A = await fresh(), B = await fresh();
  busyFriday();
  at('2026-11-13T12:00:00');
  await hit(A, env0(kv), 'ICN');
  assert.equal(kv.json('dart:today').by, 'ICN');
  calls.length = 0;
  at('2026-11-13T12:01:30');
  const b1 = (await hit(B, env0(kv), 'NRT')).body;
  assert.equal(since(), 0, 'follower serves the leader snapshot (age 90 s)');
  assert.equal(b1.rows.length, 369);
  at('2026-11-13T12:03:01');
  await hit(B, env0(kv), 'NRT');
  assert.equal(since(), 2, 'leader silent for 181 s → follower takes over');
  assert.equal(kv.json('dart:today').by, 'NRT');
  at('2026-11-13T12:03:30');
  await hit(A, env0(kv), 'ICN');
  assert.equal(since(), 0, 'old leader now follows');
});

await test('refresh intervals: 60 s weekday 07–19, 300 s evening, 600 s past the soft call budget, none past the hard one', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-13T20:00:00');
  await hit(W, env0(kv), 'ICN');
  calls.length = 0;
  at('2026-11-13T20:01:01');
  await hit(W, env0(kv), 'ICN');
  assert.equal(since(), 0);
  at('2026-11-13T20:05:01');
  await hit(W, env0(kv), 'ICN');
  assert.equal(since(), 2);
  // soft budget: 4,000 calls today → 10 minutes
  const s = kv.json('dart:today');
  await kv.put('dart:today', JSON.stringify({ ...s, calls: 4000 }), { expirationTtl: 8 * 86400 });
  const W2 = await fresh();
  at('2026-11-13T20:10:02');
  await hit(W2, env0(kv), 'ICN');
  assert.equal(since(), 0, 'within 600 s');
  at('2026-11-13T20:15:02');
  await hit(W2, env0(kv), 'ICN');
  assert.equal(since(), 2);
  // hard budget: 8,000 → stale, no calls
  const s2 = kv.json('dart:today');
  await kv.put('dart:today', JSON.stringify({ ...s2, calls: 8000 }), { expirationTtl: 8 * 86400 });
  const W3 = await fresh();
  at('2026-11-13T20:40:00');
  const r = await hit(W3, env0(kv), 'ICN');
  assert.equal(since(), 0);
  assert.equal(r.body.stale, true);
  // the counter starts again the next KST day
  at('2026-11-14T00:30:00');
  await hit(W3, env0(kv), 'ICN');
  assert.ok(since() > 0);
  assert.equal(kv.json('dart:today').callsDay, SAT);
});

await test('midnight: yesterday (not final) is finished once, then only today is probed', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-13T23:59:00');
  await hit(W, env0(kv));
  assert.equal(kv.json('dart:today').final, false);
  calls.length = 0;
  addTop(FRI, 'K', [item(FRI, 'K', kosdaq[3])]);  // a late filing before midnight
  at('2026-11-14T00:05:00');
  const b = (await hit(W, env0(kv))).body;
  assert.deepEqual(calls.splice(0).map(x => x.day + x.cls + x.page).sort(), [FRI + 'K1', FRI + 'Y1', SAT + 'K1', SAT + 'Y1']);
  assert.equal(b.date, '2026-11-13');
  assert.equal(b.rows.length, 370);
  assert.equal(b.rows[0].s, undefined, 'a filing first seen after its day ended gets no time');
  assert.equal(kv.json('dart:today').final, true);
  at('2026-11-14T00:10:01');
  await hit(W, env0(kv));
  assert.deepEqual(calls.splice(0).map(x => x.day).sort(), [SAT, SAT]);
});

await test('a pause > 15 min restarts `since`, so rows found after the pause are not shown as new', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  at('2026-11-13T09:00:00');
  await hit(W, env0(kv));
  at('2026-11-13T09:10:00');
  addTop(FRI, 'Y', [item(FRI, 'Y', kospi[30])]);
  const b1 = (await hit(W, env0(kv))).body;
  assert.equal(b1.since, '09:00');
  assert.equal(b1.rows[0].s, '09:10');
  at('2026-11-13T09:40:00');
  addTop(FRI, 'Y', [item(FRI, 'Y', kospi[31])]);
  const b2 = (await hit(W, env0(kv))).body;
  assert.equal(b2.since, '09:40');
  assert.equal(b2.rows[0].s, '09:40');
});

await test('edge cache: a second request within 30 s never reaches the handler', async () => {
  const kv = makeKV(), W = await fresh();
  busyFriday();
  cacheOn = true;
  at('2026-11-13T14:00:00');
  await hit(W, env0(kv));
  const gets = kv.log.gets;
  calls.length = 0;
  at('2026-11-13T14:00:20');
  const r = await hit(W, env0(kv));
  assert.equal(r.body.asOf, '2026-11-13T14:00:00+09:00');
  assert.equal(kv.log.gets, gets, 'no KV read');
  assert.equal(since(), 0);
});

await test('total_count the pages never deliver: one full pass, then page 1 only (no paging loop)', async () => {
  const kv = makeKV(), W = await fresh();
  db[FRI] = { Y: many(FRI, 'Y', 150, i => kospi[i]), K: many(FRI, 'K', 10, i => kosdaq[i]) };
  dartImpl = p => { const r = serve(p); if (r.status === '000' && p.corp_cls === 'Y') { r.total_count += 40; r.total_page = 2; } return r; };
  at('2026-11-13T15:00:00');
  await hit(W, env0(kv));
  assert.equal(since(), 3);
  assert.equal(kv.json('dart:today').mk.Y.gap, 40);
  at('2026-11-13T15:01:01');
  await hit(W, env0(kv));
  assert.equal(since(), 2, 'no endless paging');
});

// Workers KV as documented: one last-write-wins store; each colo serves what it last read (or wrote) from a local
// cache for `ttl` ms (default cacheTtl 60 s) — so other colos see a write up to 60 s late, misses are cached too.
function makeCachedKV(ttl) {
  const global = new Map(), local = new Map();          // local: colo → Map(key → {e, at})
  let colo = '';
  const stats = { puts: 0, gets: 0 };
  const read = (k, type) => {
    const mine = local.get(colo) || new Map();
    local.set(colo, mine);
    let c = mine.get(k);
    if (!c || clock - c.at >= ttl) { c = { e: global.get(k) || null, at: clock }; mine.set(k, c); }
    const e = c.e;
    if (!e || (e.exp && e.exp <= clock)) return null;
    return type === 'json' ? JSON.parse(e.value) : e.value;
  };
  return {
    stats, set colo(c) { colo = c; },
    async get(key, type) {
      if (Array.isArray(key)) { stats.gets += key.length; return new Map(key.map(k => [k, read(k, type)])); }
      stats.gets++;
      return read(key, type);
    },
    async put(key, value, opt) {
      stats.puts++;
      const e = { value: String(value), exp: opt && opt.expirationTtl ? clock + opt.expirationTtl * 1000 : null };
      global.set(key, e);
      const mine = local.get(colo) || new Map();
      local.set(colo, mine);
      mine.set(key, { e, at: clock });
    },
  };
}
async function simulateDay(colos) {
  db = {};
  calls.length = 0;
  const kv = makeCachedKV(60e3);
  const ws = [];
  for (const c of colos) ws.push([c, await fresh()]);
  // a busy weekday: 2 filings a minute per market 07:00–19:00, a burst of 150 KOSPI filings at 16:00, 20 at night
  const t0 = KST('2026-11-13T00:00:00');
  for (let s = 0; s < 86400; s += 30) {
    clock = t0 + s * 1000;
    const min = s / 60;
    if (s % 60 === 0) {
      if (min >= 420 && min < 1140) { addTop(FRI, 'Y', [item(FRI, 'Y', kospi[min % 300]), item(FRI, 'Y', kospi[(min + 7) % 300])]); addTop(FRI, 'K', [item(FRI, 'K', kosdaq[min % 200]), item(FRI, 'K', kosdaq[(min + 3) % 200])]); }
      if (min === 960) addTop(FRI, 'Y', Array.from({ length: 150 }, (_, i) => item(FRI, 'Y', kospi[i])));
      if (min % 72 === 0 && (min < 420 || min >= 1140)) addTop(FRI, 'K', [item(FRI, 'K', kosdaq[min % 200])]);
    }
    for (const [c, W] of ws) { kv.colo = c; const r = await hit(W, { ASSET_BASE: ASSET, REPLAY: kv, DART_KEY: KEY }, c); assert.equal(r.status, 200); }
  }
  const total = calls.length;
  const listed = (db[FRI].Y || []).length + (db[FRI].K || []).length;
  calls.length = 0;
  return { total, listed, kvPuts: kv.stats.puts };
}
await test('budget: 24 h busy weekday, every colo asking every 30 s (edge-cache misses), KV cacheTtl 60 s', async () => {
  const one = await simulateDay(['ICN']);
  const three = await simulateDay(['ICN', 'NRT', 'HKG']);
  console.log(`      1 colo: ${one.total} upstream calls/day (${one.listed} listed filings), ${one.kvPuts} KV writes`);
  console.log(`      3 colos: ${three.total} upstream calls/day, ${three.kvPuts} KV writes`);
  assert.ok(one.total < 2500, 'one colo well under 5,000');
  assert.ok(three.total < 3500, 'three colos stay well under 5,000');
});

/* ── report ── */
let fail = 0;
for (const [st, name, err] of results) {
  console.log(`${st}  ${name}`);
  if (err) { fail++; console.log(String(err).split('\n').slice(0, 6).map(l => '      ' + l).join('\n')); }
}
console.log(`\n${results.length - fail}/${results.length} passed`);
process.exit(fail ? 1 : 0);
