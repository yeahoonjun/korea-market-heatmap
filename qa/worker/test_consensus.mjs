// QA: worker/src/consensus.js — 「왕이 될 상」 컨센서스 스냅숏 (AGENTS §3-41) through the real router and scheduled().
// Fake clock / KV from qa/datago/harness.mjs; a fake raw.githubusercontent (data/snapshot.json) and m.stock.naver.com here, fed
// by the trimmed real answers of 2026-11-19 (qa/worker/fixtures/consensus_naver.json). No network, no real token.
//   node qa/worker/test_consensus.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { at, advance, makeKV, runner } from '../datago/harness.mjs';
import { CONS, topCodes, estimateCols, consensusOf, dataBase, consensusTick } from '../../worker/src/consensus.js';
import { sha256hex } from '../../worker/src/kis.js';
import W from '../../worker/src/index.js';

const R = runner('consensus');
const FX = JSON.parse(readFileSync(new URL('./fixtures/consensus_naver.json', import.meta.url), 'utf8'));

/* ── fake upstreams ── */
const N = 120;                                         // 120 common stocks + preferred ones that must be skipped
const stocks = [];
for (let i = 0; i < N; i++) stocks.push({ c: String(100000 + i * 10).padStart(6, '0'), n: 'S' + i, m: i % 3 ? 'K' : 'Q', cap: 1e6 - i * 100 });
stocks.push({ c: '005935', n: '삼성전자우', m: 'K', cap: 9e9 });          // preferred: biggest cap, still skipped
stocks.push({ c: '005930', n: '삼성전자', m: 'K', cap: 8e9 });
stocks.push({ c: '000660', n: 'SK하이닉스', m: 'K', cap: 7e9 });
const SNAP = { asOf: '2026-11-18T15:30:00+09:00', stocks };
const net = { calls: [], failCodes: new Set(), snapFail: false, slow: 0 };
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  net.calls.push(url);
  assert.ok(init.signal instanceof AbortSignal, 'every upstream call has a time limit');
  if (url === 'https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/data/snapshot.json') {
    if (net.snapFail) return new Response('nope', { status: 500 });
    return new Response(JSON.stringify(SNAP), { status: 200 });
  }
  const m = url.match(/^https:\/\/m\.stock\.naver\.com\/api\/stock\/(\d{6})\/(finance\/annual|finance\/quarter|integration)$/);
  if (!m) throw new Error('unexpected fetch ' + url);
  assert.match(init.headers['user-agent'], /Mozilla/);
  if (net.failCodes.has(m[1])) return new Response('{}', { status: 503 });
  const src = FX[m[1]] || FX['005930'];
  const body = m[2] === 'finance/annual' ? src.annual : m[2] === 'finance/quarter' ? src.quarter : src.integration;
  return new Response(JSON.stringify(body), { status: 200 });
};

const TOKEN = 'invTokenForTests_0123456789abcdef', DEV = 'devTokenForTests_0123456789abcdef';
async function envWithInvites() {
  const kv = makeKV();
  await kv.put('inv:' + await sha256hex(TOKEN), JSON.stringify({ n: '가족', at: '2026-11-19' }));
  await kv.put('inv:' + await sha256hex(DEV), JSON.stringify({ n: 'dev', dev: 1, at: '2026-11-19' }));
  kv.log.gets = 0; kv.log.puts = [];
  return { REPLAY: kv };
}
const req = (path, tok, method = 'GET') => new Request('https://w.example' + path, { method, headers: tok ? { 'x-panse-inv': tok } : {} });
const call = async (env, path, tok, method) => { const r = await W.fetch(req(path, tok, method), env, { waitUntil() {} }); return { r, j: await r.json() }; };

/* ── parsing ── */
await R.test('topCodes: common stocks only, by cap, both markets', () => {
  const t = topCodes(SNAP, 100);
  assert.equal(t.length, 100);
  assert.equal(t[0].c, '005930');
  assert.equal(t[1].c, '000660');
  assert.ok(!t.some(x => x.c === '005935'), 'preferred skipped');
  assert.ok(t.some(x => x.m === 'Q') && t.some(x => x.m === 'K'));
  assert.deepEqual(topCodes({}, 5), []);
});
await R.test('estimateCols: only the E columns, mapped rows, numbers', () => {
  const a = estimateCols(FX['005930'].annual);
  assert.equal(a.length, 1);
  assert.equal(a[0].k, '202612');
  for (const k of ['rev', 'op', 'ni', 'eps', 'per', 'bps']) assert.equal(typeof a[0][k], 'number', k);
  const q = estimateCols(FX['005930'].quarter);
  assert.ok(q.length >= 1 && q.every(x => /^\d{6}$/.test(x.k)));
  assert.deepEqual(estimateCols({}), []);
  assert.deepEqual(estimateCols({ financeInfo: { trTitleList: [{ key: '202512', isConsensus: 'N' }], rowList: [] } }), []);
});
await R.test('consensusOf: target · opinion · date · estimated EPS/PER', () => {
  const o = consensusOf(FX['000660'].integration);
  assert.equal(o.tp, 3001905);
  assert.equal(o.rec, 4);
  assert.equal(o.cd, '2026-11-17');
  assert.equal(typeof o.ceps, 'number');
  assert.equal(typeof o.cper, 'number');
  assert.deepEqual(consensusOf(null), {});
});
await R.test('dataBase: data/ next to web/, override', () => {
  assert.equal(dataBase({}), 'https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/data/');
  assert.equal(dataBase({ ASSET_BASE: 'http://127.0.0.1:8791/web/' }), 'http://127.0.0.1:8791/data/');
  assert.equal(dataBase({ DATA_BASE: 'http://x/d' }), 'http://x/d/');
});

/* ── the daily tick ── */
await R.test('outside 16:10–16:59 on a weekday, and on weekends: no KV, no network', async () => {
  const env = await envWithInvites();
  net.calls = [];
  for (const t of ['2026-11-19T09:30:00', '2026-11-19T16:09:00', '2026-11-19T17:00:00', '2026-11-21T16:30:00', '2026-11-22T16:30:00']) {
    at(t);
    assert.equal(await consensusTick(env), 'not-due', t);
  }
  assert.equal(env.REPLAY.log.gets, 0);
  assert.equal(net.calls.length, 0);
  assert.equal(await consensusTick({}), 'off');
  assert.equal(await consensusTick({ REPLAY: env.REPLAY, CONS: 'off' }), 'off');
});
await R.test('16:10 Thursday: one snapshot, then done for the day', async () => {
  const env = await envWithInvites();
  net.calls = []; net.failCodes = new Set(['100000']); net.snapFail = false;
  at('2026-11-19T16:10:00');
  assert.equal(await consensusTick(env), 'wrote');
  assert.equal(net.calls.length, 1 + CONS.TOP_N * 3, 'snapshot + 3 calls per stock');
  const snap = env.REPLAY.json('cons:20261119');
  assert.equal(snap.asOf, '2026-11-19');
  assert.equal(snap.at, '16:10');
  assert.equal(snap.capAsOf, '2026-11-18');
  assert.equal(snap.n, CONS.TOP_N - 1);
  assert.deepEqual(snap.miss, ['100000']);
  assert.equal(snap.codes.length, CONS.TOP_N);
  assert.deepEqual(snap.codes.slice(0, 2), ['005930', '000660'], 'rank order kept');
  assert.ok(snap.codes.includes('100000'), 'missed stocks keep their rank slot');
  assert.equal(snap.c['005930'].n, '삼성전자');
  assert.equal(snap.c['005930'].a[0].k, '202612');
  assert.equal(typeof snap.c['000660'].tp, 'number');
  assert.equal(env.REPLAY.ttl('cons:20261119'), null, 'kept forever');
  assert.deepEqual(env.REPLAY.json('cons:days'), ['2026-11-19']);
  assert.equal(env.REPLAY.json('cons:status').result, 'wrote');
  net.calls = [];
  advance(60e3);
  assert.equal(await consensusTick(env), 'done');
  assert.equal(net.calls.length, 0);
  at('2026-11-20T16:30:00');
  assert.equal(await consensusTick(env), 'wrote');
  assert.deepEqual(env.REPLAY.json('cons:days'), ['2026-11-20', '2026-11-19']);
  net.failCodes = new Set();
});
await R.test('snapshot fetch fails: no data, status error, retry after the 10-minute lock', async () => {
  const env = await envWithInvites();
  net.snapFail = true;
  at('2026-11-19T16:12:00');
  assert.equal(await consensusTick(env), 'error');
  assert.equal(env.REPLAY.json('cons:20261119'), null);
  assert.equal(env.REPLAY.json('cons:status').result, 'error');
  assert.notEqual(env.REPLAY.m.get('cons:done') && env.REPLAY.json('cons:done'), 20261119);
  advance(60e3);
  assert.equal(await consensusTick(env), 'locked');
  net.snapFail = false;
  advance(10 * 60e3);
  assert.equal(await consensusTick(env), 'wrote');
});
await R.test('fewer than half the stocks: nothing written', async () => {
  const env = await envWithInvites();
  net.failCodes = new Set(topCodes(SNAP, 100).slice(0, 60).map(x => x.c));
  at('2026-11-19T16:20:00');
  assert.equal(await consensusTick(env), 'error');
  assert.equal(env.REPLAY.json('cons:20261119'), null);
  assert.match(env.REPLAY.json('cons:status').error, /only 40/);
  net.failCodes = new Set();
});

/* ── reading: invite only ── */
await R.test('routes: 403 without a valid invite, data with one', async () => {
  const env = await envWithInvites();
  at('2026-11-19T16:10:00');
  await consensusTick(env);
  for (const p of ['/api/archive/consensus', '/api/archive/consensus/days', '/api/archive/consensus/probe']) {
    const a = await call(env, p);
    assert.equal(a.r.status, 403, p);
    assert.deepEqual(a.j, { error: 'forbidden' });
    const b = await call(env, p, 'wrongTokenWrongToken_0123456789');
    assert.equal(b.r.status, 403, p + ' wrong token');
  }
  const d = await call(env, '/api/archive/consensus/days', TOKEN);
  assert.equal(d.r.status, 200);
  assert.deepEqual(d.j.days, ['2026-11-19']);
  assert.equal(d.r.headers.get('cache-control'), 'private, no-store');
  assert.equal(d.r.headers.get('access-control-allow-origin'), null, 'not for browsers on other sites');
  const l = await call(env, '/api/archive/consensus', TOKEN);
  assert.equal(l.r.status, 200);
  assert.equal(l.j.asOf, '2026-11-19');
  const g = await call(env, '/api/archive/consensus?date=2026-11-19', TOKEN);
  assert.equal(g.j.n, CONS.TOP_N);
  assert.equal((await call(env, '/api/archive/consensus?date=2026-11-18', TOKEN)).r.status, 404);
  assert.equal((await call(env, '/api/archive/consensus?date=20261119', TOKEN)).r.status, 400);
  assert.equal((await call(env, '/api/archive/consensus/nope', TOKEN)).r.status, 404);
  assert.equal((await call(env, '/api/archive/consensus', TOKEN, 'POST')).r.status, 405);
});
await R.test('probe: dev invite only, n ≤ 10, writes nothing', async () => {
  const env = await envWithInvites();
  at('2026-11-19T01:00:00');
  assert.equal((await call(env, '/api/archive/consensus/probe?n=3', TOKEN)).r.status, 403, 'family invite is not dev');
  net.calls = [];
  const p = await call(env, '/api/archive/consensus/probe?n=50', DEV);
  assert.equal(p.r.status, 200);
  assert.equal(p.j.n, CONS.PROBE_MAX);
  assert.equal(net.calls.length, 1 + CONS.PROBE_MAX * 3);
  assert.ok(!env.REPLAY.log.puts.some(x => x.key.startsWith('cons:')), 'probe writes nothing');
});

/* ── scheduled(): the recorder and the tick side by side ── */
await R.test('scheduled() runs the tick and never throws', async () => {
  const env = await envWithInvites();
  at('2026-11-19T16:15:00');
  const waits = [];
  await W.scheduled({ scheduledTime: Date.now(), cron: '* 0-7 * * 2-6' }, env, { waitUntil: p => waits.push(p) });
  await Promise.all(waits);
  assert.ok(env.REPLAY.json('cons:20261119'), 'snapshot written from the cron');
  net.snapFail = true;
  at('2026-11-20T16:15:00');
  await W.scheduled({ scheduledTime: Date.now(), cron: '* 0-7 * * 2-6' }, env, { waitUntil() {} });   // no throw
  net.snapFail = false;
});

await R.done();
