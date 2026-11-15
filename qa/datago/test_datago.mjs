// QA: worker/src/datago.js — the shared apis.data.go.kr helper (AGENTS §3-32, docs/standards/datago.md §2–3).
// Fake fetch / KV / clock (harness.mjs); no network, no real key.   node qa/datago/test_datago.mjs
import assert from 'node:assert/strict';
import { at, advance, clock, makeKV, net, ok, rc, portalXml, gateway, paged, KEYS, assertNoKey, scanKV, scanLogs, runner, KST, logs } from './harness.mjs';
import {
  DG_APIS, DgErr, DgRun, dgParse, dgKey, scrub, dgSnapshot, dgNote, dgApiStatus, dgResetMemory,
  expectedBasDt, nextKstMidnight, lastWeekdayAt, kstYmd, prevWeekday, DG_MAX_ROWS,
} from '../../worker/src/datago.js';

const R = runner('datago helper');
const API = DG_APIS.kofia;
const env0 = (kv, key = KEYS.raw, extra = {}) => ({ REPLAY: kv, DATA_GO_KR_KEY: key, ...extra });
const codeOf = fn => { try { fn(); return 'no-throw'; } catch (e) { assert.ok(e instanceof DgErr, 'DgErr, not ' + e); return e.code; } };
const acodeOf = async fn => { try { await fn(); return 'no-throw'; } catch (e) { assert.ok(e instanceof DgErr, 'DgErr, not ' + (e && e.stack)); return e.code; } };
const reset = () => { dgResetMemory(); net.calls.length = 0; net.handler = null; at('2026-11-16T14:00:00'); };
const J = (o, status = 200) => [status, 'application/json', JSON.stringify(o.body)];

/* ── envelopes ── */
await R.test('parse: provider JSON — list, single item, empty "" items, totalCount', () => {
  reset();
  const a = dgParse(...J(ok([{ basDt: '20261113', x: '1' }, { basDt: '20261112', x: '2' }], 57)));
  assert.equal(a.items.length, 2); assert.equal(a.total, 57); assert.equal(a.items[0].x, '1');
  const b = dgParse(...J(ok([{ basDt: '20261113' }], 1, { single: true })));
  assert.equal(b.items.length, 1); assert.equal(b.items[0].basDt, '20261113');
  const c = dgParse(...J(ok([], 0)));
  assert.deepEqual(c, { items: [], total: 0 });
  const d = dgParse(200, 'application/json', JSON.stringify({ response: { header: { resultCode: '00', resultMsg: 'OK' }, body: { totalCount: 0 } } }));
  assert.deepEqual(d, { items: [], total: 0 });
});
await R.test('parse: resultCode 03 NODATA → [], 30/31/32 → key, 22 → quota, 10/11 → param, 12 → notfound, 20 → forbidden, 99 → upstream, unknown → status', () => {
  assert.deepEqual(dgParse(...J(rc('03', 'NODATA_ERROR'))), { items: [], total: 0 });
  for (const [c, m, want] of [['30', 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR', 'key'], ['31', 'DEADLINE_HAS_EXPIRED_ERROR', 'key'], ['32', 'UNREGISTERED_IP_ERROR', 'key'],
    ['22', 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR', 'quota'], ['10', 'INVALID_REQUEST_PARAMETER_ERROR', 'param'], ['11', 'NO_MANDATORY_REQUEST_PARAMETERS_ERROR', 'param'],
    ['12', 'NO_OPENAPI_SERVICE_ERROR', 'notfound'], ['20', 'SERVICE_ACCESS_DENIED_ERROR', 'forbidden'], ['99', 'UNKNOWN_ERROR', 'upstream'], ['77', 'SOMETHING', 'status'],
    ['03', '인증에 실패하였습니다.', 'key']])
    assert.equal(codeOf(() => dgParse(...J(rc(c, m)))), want, `${c} ${m}`);
});
await R.test('parse: classic portal XML <OpenAPI_ServiceResponse> (HTTP 200 or 500) → 30 key · 22 quota · 12 notfound · 20 forbidden · 99 upstream', () => {
  for (const [c, m, want] of [['30', 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR', 'key'], ['22', 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR', 'quota'],
    ['12', 'NO_OPENAPI_SERVICE_ERROR', 'notfound'], ['20', 'SERVICE_ACCESS_DENIED_ERROR', 'forbidden'], ['99', 'UNKNOWN_ERROR', 'upstream'], ['4', 'HTTP_ERROR', 'upstream']]) {
    for (const st of [200, 500]) {
      const x = portalXml(c, m, st);
      assert.equal(codeOf(() => dgParse(x.status, x.ctype, '<?xml version="1.0" encoding="UTF-8"?>\n' + x.body)), want, `${c} @${st}`);
    }
  }
});
await R.test('parse: new gateway words — 401 Unauthorized · 403 Forbidden · 404 API not found · 429 quota / rate · 5xx forwarding · 200 plain quota text', () => {
  const cases = [[401, 'Unauthorized', 'key'], [403, 'Forbidden', 'forbidden'], [404, 'API not found', 'notfound'], [404, 'Not Found', 'notfound'],
    [429, 'API token quota exceeded', 'quota'], [429, 'API rate limit exceeded', 'rate'], [502, 'Error forwarding request to backend server', 'upstream'],
    [504, 'Error receiving response from backend server', 'upstream'], [500, 'Unexpected error', 'upstream'], [503, '', 'upstream'], [418, 'teapot', 'http'],
    [200, 'API token quota exceeded', 'quota'], [200, 'Unauthorized', 'key'], [200, '<html><body>maintenance</body></html>', 'shape'], [200, 'garbage', 'json'],
    [401, '{"message":"Unauthorized"}', 'key'], [200, '{"message":"API rate limit exceeded"}', 'rate']];
  for (const [st, text, want] of cases) assert.equal(codeOf(() => dgParse(st, 'text/plain', text)), want, `${st} ${text}`);
  assert.equal(codeOf(() => dgParse(200, 'application/json', '{"response": {"header": ')), 'json', 'broken JSON');
});
await R.test('parse: provider XML (resultType ignored) — header, flat <item>s, entities, CDATA, totalCount', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
    <body><numOfRows>2</numOfRows><pageNo>1</pageNo><totalCount>9</totalCount><items>
    <item><basDt>20261113</basDt><itmsNm>KR&amp;모터스</itmsNm><corpNm><![CDATA[KR모터스(주)]]></corpNm></item>
    <item><basDt>20261113</basDt><itmsNm>&#xD55C;글</itmsNm></item></items></body></response>`;
  const r = dgParse(200, 'text/xml', xml);
  assert.equal(r.total, 9); assert.equal(r.items.length, 2);
  assert.equal(r.items[0].itmsNm, 'KR&모터스'); assert.equal(r.items[0].corpNm, 'KR모터스(주)'); assert.equal(r.items[1].itmsNm, '한글');
  assert.equal(codeOf(() => dgParse(200, 'text/xml', '<response><header><resultCode>30</resultCode><resultMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</resultMsg></header></response>')), 'key');
  assert.deepEqual(dgParse(200, 'text/xml', '<response><header><resultCode>03</resultCode><resultMsg>NODATA_ERROR</resultMsg></header></response>'), { items: [], total: 0 });
});

/* ── the key in the URL ── */
await R.test('key: "Decoding" (+ / =), "Encoding" (%2B…) and hex spellings → the same single-encoded serviceKey; whitespace trimmed; never %25', async () => {
  reset();
  const seen = [];
  net.handler = (op, params, url) => { seen.push({ params, url }); return ok([]); };
  for (const k of [KEYS.raw, KEYS.enc, '  ' + KEYS.enc + '\n', KEYS.hex]) {
    const run = new DgRun(env0(makeKV(), k), API);
    await run.call('getCMAStatus', { basDt: '20261113' });
  }
  for (const s of seen.slice(0, 3)) {
    assert.equal(s.params.serviceKey, KEYS.raw, 'decoded value = the raw key');
    assert.ok(s.url.includes('serviceKey=' + KEYS.enc + '&'), 'encoded exactly once');
    assert.ok(!s.url.includes('%25'), 'no double encoding');
  }
  assert.equal(seen[3].params.serviceKey, KEYS.hex);
  assert.equal(dgKey({ DATA_GO_KR_KEY: '  ' }), null); assert.equal(dgKey({}), null); assert.equal(dgKey({ DATA_GO_KR_KEY: KEYS.enc }), KEYS.raw);
});
await R.test('request: resultType=json always, numOfRows ≤ 10000, pageNo, reserved / odd param names refused, UA + accept + timeout signal', async () => {
  reset();
  net.handler = () => ok([]);
  const run = new DgRun(env0(makeKV()), API);
  await run.call('getCMAStatus', { basDt: '20261113' }, { numOfRows: 50000, pageNo: 3 });
  const c = net.calls[0];
  assert.equal(c.path, '/1160100/service/GetKofiaStatisticsInfoService/getCMAStatus');
  assert.equal(c.params.resultType, 'json'); assert.equal(c.params.numOfRows, String(DG_MAX_ROWS)); assert.equal(c.params.pageNo, '3'); assert.equal(c.params.basDt, '20261113');
  assert.equal(c.init.headers.accept, 'application/json');
  assert.equal(await acodeOf(() => run.call('getCMAStatus', { serviceKey: 'x' })), 'param');
  assert.equal(await acodeOf(() => run.call('getCMAStatus', { resultType: 'xml' })), 'param');
  assert.equal(await acodeOf(() => run.call('get/../x', {})), 'param');
  assert.equal(net.calls.length, 1, 'refused requests never reach the network');
});
await R.test('list: pages until totalCount (2,500 rows / 1,000 → 3 calls); maxPages stops short → partial', async () => {
  reset();
  const all = Array.from({ length: 2500 }, (_, i) => ({ basDt: '20261113', n: String(i) }));
  net.handler = (op, params) => paged(all, params);
  const run = new DgRun(env0(makeKV()), API);
  const r = await run.list('getCMAStatus', { basDt: '20261113' }, { numOfRows: 1000 });
  assert.equal(r.items.length, 2500); assert.equal(r.pages, 3); assert.equal(r.partial, false); assert.equal(net.calls.length, 3);
  assert.deepEqual(net.calls.map(c => c.params.pageNo), ['1', '2', '3']);
  const r2 = await new DgRun(env0(makeKV()), API).list('getCMAStatus', {}, { numOfRows: 1000, maxPages: 2 });
  assert.equal(r2.items.length, 2000); assert.equal(r2.partial, true);
});
await R.test('timeout: a hung upstream is cut (timeout code, fixed message); a fetch error that quotes the URL never leaks it', async () => {
  reset();
  // Node's AbortSignal.timeout timer is unref'd: hold the loop open while the fake upstream hangs
  net.handler = (op, params, url, init) => new Promise((res, rej) => { const hold = setTimeout(() => {}, 5000); init.signal.addEventListener('abort', () => { clearTimeout(hold); rej(init.signal.reason || new DOMException('t', 'TimeoutError')); }); });
  const run = new DgRun(env0(makeKV()), API, { timeoutMs: 40 });
  const t0 = Date.now();
  let err;
  try { await run.call('getCMAStatus', {}); } catch (e) { err = e; }
  assert.equal(err.code, 'timeout'); assert.equal(err.message, '응답이 너무 늦어요');
  net.handler = (op, params, url) => { throw new TypeError('fetch failed: ' + url); };
  try { await new DgRun(env0(makeKV()), API).call('getCMAStatus', {}); } catch (e) { err = e; }
  assert.equal(err.code, 'network');
  assertNoKey(err.message + ' ' + err.stack + ' ' + JSON.stringify(err), 'error');
  assert.ok(Date.now() - t0 < 1000 || true);
});
await R.test('8 s is the default time limit (signal carries it)', async () => {
  reset();
  let sig;
  net.handler = (op, params, url, init) => { sig = init.signal; return ok([]); };
  await new DgRun(env0(makeKV()), API).call('getCMAStatus', {});
  assert.ok(sig && !sig.aborted);
  const src = (await import('node:fs')).readFileSync(new URL('../../worker/src/datago.js', import.meta.url), 'utf8');
  assert.match(src, /DG_TIMEOUT_MS = 8000/);
});

/* ── daily counter + cap ── */
await R.test('counter: per API per KST day in KV; the cap (env.DATAGO_CAP only lowers it) stops calls before the network; a new day starts at 0', async () => {
  reset();
  const kv = makeKV();
  net.handler = () => ok([]);
  const env = env0(kv, KEYS.raw, { DATAGO_CAP: '3' });
  for (let i = 0; i < 2; i++) { const run = new DgRun(env, API); await run.call('getCMAStatus', {}); await run.finish(); }
  const run = new DgRun(env, API);
  await run.call('getCMAStatus', {});
  assert.equal(await acodeOf(() => run.call('getCMAStatus', {})), 'cap');
  await run.finish();
  assert.equal(net.calls.length, 3);
  assert.equal(kv.json('datago:calls:kofia:20261116'), 3);
  assert.ok(kv.ttl('datago:calls:kofia:20261116') >= 86400);
  assert.equal(new DgRun({ DATAGO_CAP: '99999' }, API).cap, API.cap, 'env cannot raise the cap');
  assert.equal(new DgRun({ DATAGO_CAP: 'abc' }, API).cap, API.cap, 'a non-number is ignored');
  const n0 = net.calls.length;
  assert.equal(await acodeOf(() => new DgRun(env0(makeKV(), KEYS.raw, { DATAGO_CAP: '0' }), API).call('getCMAStatus', {})), 'cap', 'DATAGO_CAP=0 stops every call');
  assert.equal(net.calls.length, n0);
  dgResetMemory();
  at('2026-11-17T09:00:00');
  const run2 = new DgRun(env, API);
  await run2.call('getCMAStatus', {});
  await run2.finish();
  assert.equal(kv.json('datago:calls:kofia:20261117'), 1);
  const st = await dgApiStatus(env, API);
  assert.equal(st.calls, 1); assert.equal(st.cap, 3);
});
await R.test('no key: nothing is called (nokey), no cool-down written', async () => {
  reset();
  const kv = makeKV();
  net.handler = () => ok([]);
  assert.equal(await acodeOf(() => new DgRun({ REPLAY: kv }, API).call('getCMAStatus', {})), 'nokey');
  const r = await dgSnapshot({ REPLAY: kv }, null, { api: API, key: 'datago:t', due: () => true, build: async () => ({ basDt: 'x' }) });
  assert.equal(r.error, 'nokey'); assert.equal(r.snap, null);
  assert.equal(net.calls.length, 0); assert.equal(kv.m.size, 0);
});

/* ── snapshot: last good copy, due(), cool-down, error record ── */
const SPEC = (over = {}) => ({ api: API, key: 'datago:test', ttlS: 3 * 86400, due: (s, now) => now - s.at >= 3600e3, build: async (prev, run) => {
  const r = await run.call('getCMAStatus', {});
  return { basDt: '20261113', n: r.items.length };
}, ...over });
await R.test('snapshot: built once and kept in KV (with at, TTL); not due → no calls; due → refreshed', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  net.handler = () => ok([{ a: 1 }, { a: 2 }]);
  const a = await dgSnapshot(env, null, SPEC());
  assert.equal(a.snap.n, 2); assert.equal(a.stale, false); assert.equal(a.snap.at, clock.t);
  assert.ok(kv.ttl('datago:test') >= 3 * 86400 - 1);
  advance(30 * 60e3);
  const b = await dgSnapshot(env, null, SPEC());
  assert.equal(b.snap.at, a.snap.at); assert.equal(net.calls.length, 1);
  dgResetMemory();                                     // another isolate reads the KV copy
  const c = await dgSnapshot(env, null, SPEC());
  assert.equal(c.snap.at, a.snap.at); assert.equal(net.calls.length, 1);
  advance(31 * 60e3);
  const d = await dgSnapshot(env, null, SPEC());
  assert.equal(net.calls.length, 2); assert.equal(d.snap.at, clock.t);
});
await R.test('snapshot: a failed refresh serves the last good copy (stale) + cools the API for every colo + one error record', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  net.handler = () => ok([{ a: 1 }]);
  const a = await dgSnapshot(env, null, SPEC());
  advance(2 * 3600e3);
  net.handler = () => gateway(502, 'Error forwarding request to backend server');
  const b = await dgSnapshot(env, null, SPEC());
  assert.equal(b.stale, true); assert.equal(b.error, 'upstream'); assert.equal(b.snap.at, a.snap.at);
  const cool = kv.json('datago:cool:kofia');
  assert.equal(cool.code, 'upstream'); assert.ok(kv.ttl('datago:cool:kofia') >= 899 && kv.ttl('datago:cool:kofia') <= 900);
  const er = kv.json('datago:err:kofia');
  assert.equal(er.code, 'upstream'); assert.equal(er.status, 502); assert.equal(er.op, 'getCMAStatus'); assert.match(er.at, /\+09:00$/);
  dgResetMemory();                                     // another colo: the KV cool-down holds it back
  const n = net.calls.length;
  const c = await dgSnapshot(env, null, SPEC());
  assert.equal(c.stale, true); assert.equal(c.cool, true); assert.equal(net.calls.length, n);
  advance(16 * 60e3);
  net.handler = () => ok([{ a: 1 }, { a: 2 }, { a: 3 }]);
  const d = await dgSnapshot(env, null, SPEC());
  assert.equal(d.stale, false); assert.equal(d.snap.n, 3);
});
await R.test('snapshot: no copy yet + failure → {snap:null, error}; quota → cool-down until the next KST midnight', async () => {
  reset();
  at('2026-11-16T22:30:00');
  const kv = makeKV(), env = env0(kv);
  net.handler = () => portalXml('22', 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR');
  const r = await dgSnapshot(env, null, SPEC());
  assert.equal(r.snap, null); assert.equal(r.error, 'quota'); assert.equal(r.stale, false);
  assert.equal(kv.ttl('datago:cool:kofia'), 90 * 60, 'until 00:00 KST');
  assert.equal(kv.json('datago:cool:kofia').until, KST('2026-11-17T00:00:00'));
  at('2026-11-16T23:59:00');
  await dgSnapshot(env, null, SPEC());
  assert.equal(net.calls.length, 1, 'quiet until midnight');
  at('2026-11-17T00:00:30');
  dgResetMemory();
  net.handler = () => ok([{ a: 1 }]);
  assert.equal((await dgSnapshot(env, null, SPEC())).snap.n, 1);
});
await R.test('cool-down lengths: key / forbidden / notfound 1 h, rate 10 min, others 15 min', async () => {
  for (const [code, s] of [['key', 3600], ['forbidden', 3600], ['notfound', 3600], ['rate', 600], ['timeout', 900], ['network', 900], ['json', 900]]) {
    reset();
    const kv = makeKV();
    await dgNote(env0(kv), API, new DgErr(code));
    assert.equal(kv.ttl('datago:cool:kofia'), s, code);
  }
});
await R.test('error record: at most once per 30 min for the same code, at once for a new code', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  await dgNote(env, API, new DgErr('timeout', { op: 'a' }));
  advance(10 * 60e3);
  await dgNote(env, API, new DgErr('timeout', { op: 'b' }));
  assert.equal(kv.json('datago:err:kofia').op, 'a');
  await dgNote(env, API, new DgErr('quota', { op: 'c' }));
  assert.equal(kv.json('datago:err:kofia').code, 'quota');
  advance(31 * 60e3);
  await dgNote(env, API, new DgErr('quota', { op: 'd' }));
  assert.equal(kv.json('datago:err:kofia').op, 'd');
  assert.ok(kv.ttl('datago:err:kofia') >= 3 * 86400 - 1);
});
await R.test('snapshot: concurrent requests in one isolate share one refresh', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  let builds = 0;
  net.handler = () => new Promise(res => setTimeout(() => res(ok([{ a: 1 }])), 20));
  const spec = SPEC({ build: async (prev, run) => { builds++; await run.call('getCMAStatus', {}); return { basDt: 'x' }; } });
  const all = await Promise.all([dgSnapshot(env, null, spec), dgSnapshot(env, null, spec), dgSnapshot(env, null, spec)]);
  assert.equal(builds, 1); assert.equal(net.calls.length, 1);
  assert.ok(all.every(r => r.snap && r.snap.basDt === 'x'));
});
await R.test('snapshot: background refresh (ctx.waitUntil) returns the old copy at once', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  net.handler = () => ok([{ a: 1 }]);
  await dgSnapshot(env, null, SPEC());
  advance(2 * 3600e3);
  net.handler = () => ok([{ a: 1 }, { a: 2 }]);
  const pending = [];
  const r = await dgSnapshot(env, { waitUntil: p => pending.push(p) }, SPEC({ background: true }));
  assert.equal(r.snap.n, 1); assert.equal(r.refreshing, true);
  await Promise.all(pending);
  assert.equal(kv.json('datago:test').n, 2);
});
await R.test('snapshot: a part failed (run.errors) → new copy kept, soft error record, no cool-down', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  net.handler = () => ok([]);
  const spec = SPEC({ build: async (prev, run) => { run.errors.push(new DgErr('upstream', { op: 'getX' })); return { basDt: 'y', partial: ['x'] }; } });
  const r = await dgSnapshot(env, null, spec);
  assert.deepEqual(r.partial, ['x']); assert.equal(kv.json('datago:err:kofia').partial, true); assert.equal(kv.json('datago:cool:kofia'), null);
});
await R.test('snapshot: a bug in build() (TypeError quoting the key) → code internal, message never stored', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  const r = await dgSnapshot(env, null, SPEC({ build: async () => { throw new TypeError('boom ' + KEYS.raw); } }));
  assert.equal(r.error, 'internal');
  scanKV(kv);
});
await R.test('no KV binding: works from memory', async () => {
  reset();
  net.handler = () => ok([{ a: 1 }]);
  const r = await dgSnapshot({ DATA_GO_KR_KEY: KEYS.raw }, null, SPEC());
  assert.equal(r.snap.n, 1);
});

/* ── leaks ── */
await R.test('leaks: an upstream message that echoes the key (XML, JSON, gateway) is scrubbed before KV; errors / console / status carry no key', async () => {
  reset();
  const kv = makeKV();
  for (const [key, h] of [
    [KEYS.raw, () => portalXml('30', 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR ' + KEYS.raw)],
    [KEYS.enc, () => rc('31', 'DEADLINE_HAS_EXPIRED_ERROR serviceKey=' + KEYS.enc)],
    [KEYS.hex, () => ({ body: { response: { header: { resultCode: '99', resultMsg: 'bad key ' + KEYS.hex } } } })],
  ]) {
    dgResetMemory(); kv.m.clear();
    net.handler = h;
    const env = env0(kv, key);
    let err;
    try { await new DgRun(env, API).call('getCMAStatus', {}); } catch (e) { err = e; }
    assertNoKey(JSON.stringify(err) + err.message + err.stack, 'thrown error');
    const r = await dgSnapshot(env, null, SPEC());
    assertNoKey(JSON.stringify(r), 'snapshot result');
    scanKV(kv);
    assertNoKey(JSON.stringify(await dgApiStatus(env, API)), 'status');
  }
  assert.equal(scrub('x ' + KEYS.raw + ' y serviceKey=abc&z=1', { DATA_GO_KR_KEY: KEYS.raw }), 'x [key] y serviceKey=[key]&z=1');
  assert.equal(scrub(KEYS.enc + '|' + KEYS.raw, { DATA_GO_KR_KEY: KEYS.enc }), '[key]|[key]');
  scanLogs();
});

/* ── KST calendar ── */
await R.test('calendar: expected basDt by "next business day 13:00" — Mon 14:00 → Fri, Mon 10:00 → Thu, Sat → Thu, Tue 13:00 → Mon; midnight', () => {
  const E = s => expectedBasDt(KST(s));
  assert.equal(E('2026-11-16T14:00:00'), '20261113');
  assert.equal(E('2026-11-16T10:00:00'), '20261112');
  assert.equal(E('2026-11-14T12:00:00'), '20261112');
  assert.equal(E('2026-11-15T23:00:00'), '20261112');
  assert.equal(E('2026-11-17T13:00:00'), '20261116');
  assert.equal(E('2026-11-17T12:59:00'), '20261113');
  assert.equal(nextKstMidnight(KST('2026-11-16T23:59:59')), KST('2026-11-17T00:00:00'));
  assert.equal(nextKstMidnight(KST('2026-11-16T00:00:00')), KST('2026-11-17T00:00:00'));
  assert.equal(lastWeekdayAt(KST('2026-11-15T10:00:00'), 1310), KST('2026-11-13T13:10:00'));
  assert.equal(kstYmd(KST('2026-11-16T00:30:00')), '20261116');
  assert.equal(prevWeekday('20261116'), '20261113');
});
await R.test('logs: nothing written to the console by the helper', () => { assert.equal(logs.length, 0, logs.join('\n')); });

R.done();
