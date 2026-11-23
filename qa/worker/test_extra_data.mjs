// QA: 추가 기능 데이터 (AGENTS §3-37 ⓐ ①) through the real router (worker/src/index.js) — fake fetch / edge cache, no network.
//   ⓐ /data/alerts.json (시장 경보, made by the daily job) and the quotes row key `hx:1` (거래정지 only)
//   ① /data/theme_why/<id>.json (테마 편입 이유, one file per theme)
//   ② /data/marks.json (거래 급증 · 신고가 기준 — roadmap §3-23c ②, made by the daily job with periods)
//   node qa/worker/test_extra_data.mjs          → exit 1 on any failure
// Each scenario imports a fresh copy of the module (?i=N) so module memory (universe cache) starts empty.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

//   WORKER_MODULE=worker/dist/worker.js node qa/worker/test_extra_data.mjs   — the same checks on the bundle
const SRC = process.env.WORKER_MODULE ? pathToFileURL(process.env.WORKER_MODULE).href : new URL('../../worker/src/index.js', import.meta.url).href;
const ROOT = new URL('../../', import.meta.url);
const UNIVERSE = readFileSync(new URL('web/universe.json', ROOT), 'utf8');
const U = JSON.parse(UNIVERSE);
const TOP = [];
for (const m of ['K', 'Q']) for (let k = 0; k + 8 <= U[m].length; k += 8) TOP.push(U[m].slice(k, k + 6));
const ASSET = 'https://assets.test/web/';
const ORIGIN = 'https://panse.pages.dev';

let pass = 0, fail = 0;
const t = async (name, fn) => { try { await fn(); pass++; console.log('  ok  ', name); } catch (e) { fail++; console.log('  FAIL', name, '\n       ', e.message); } };

/* ── edge cache ── */
const cacheStore = new Map();
globalThis.caches = { default: {
  async match(req) { const e = cacheStore.get(req.url); return e ? e.clone() : undefined; },
  async put(req, res) { cacheStore.set(req.url, res.clone()); },
  async delete(req) { return cacheStore.delete(req.url); },
} };

/* ── upstream: ASSET_BASE files + Naver polling (rows shaped like the 2026-11-16 measurement, data/ENDPOINTS_EXTRA.md §9) ── */
const files = new Map([
  ['universe.json', UNIVERSE],
  ['alerts.json', JSON.stringify({ asOf: '2026-11-16', at: '07:51', n: 2701, c: { '079550': { a: 'caution' }, '181710': { a: 'warning' }, '001570': { adm: 1, stop: 1 } } })],
  ['theme_why/576.json', JSON.stringify({ asOf: '2026-11-13', r: { '393210': '퓨리오사AI 투자 이력 부각.' } })],
  ['marks.json', JSON.stringify({ asOf: '2026-11-20', unit: '억원', tvn: 20, from: '2025-11-24', c: { '005930': [37795.3, 374500, 96200, '2026-06-19', '2025-11-24'] } })],
]);
const fetched = [];
// per-code status for the polling rows: [tradableStatus, tradableStatusCode, tradeStopType.name] (undefined = key absent)
const STATUS = new Map([
  [TOP[0], ['halt', 'eventHalt01', 'HALTED']],                       // 거래정지 → hx:1
  [TOP[1], ['stop', 'afterMarketOperationHalt', 'HALTED']],          // VI-like pause after hours → not a halt
  [TOP[2], ['sessionRestricted', 'afterMarketRestricted', 'TRADING']],
  [TOP[3], [undefined, undefined, 'HALTED']],                        // no tradableStatus at all → tradeStopType decides
  [TOP[4], [undefined, undefined, 'TRADING']],
  [TOP[5], ['HALT', 'eventHalt01', 'HALTED']],                       // case / spacing tolerant
]);
function row(c, i) {
  const [ts, tsc, stop] = STATUS.get(c) || ['tradable', 'ok', 'TRADING'];
  const r = {
    itemCode: c, stockName: 'S' + c, closePriceRaw: String(10000 + i), compareToPreviousClosePriceRaw: '0', fluctuationsRatioRaw: '0.00',
    marketValueFullRaw: '1000000000000', accumulatedTradingValueRaw: '0', accumulatedTradingVolumeRaw: '0', openPriceRaw: '', highPriceRaw: '', lowPriceRaw: '',
    marketStatus: 'CLOSE', localTradedAt: '2026-11-13T20:00:00+09:00', stockExchangeType: { code: 'KS', startTime: '0900', endTime: '1530' },
    compareToPreviousPrice: { code: '3', name: 'UNCHANGED' }, tradeStopType: { code: stop === 'HALTED' ? '2' : '1', name: stop },
  };
  if (ts !== undefined) { r.tradableStatus = ts; r.tradableStatusCode = tsc; }
  return r;
}
globalThis.fetch = async (input) => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  fetched.push(u.href);
  if (u.href.startsWith(ASSET)) {
    const f = decodeURIComponent(u.href.slice(ASSET.length));
    return files.has(f) ? new Response(files.get(f)) : new Response('404: Not Found', { status: 404 });
  }
  if (u.host === 'polling.finance.naver.com' && u.pathname.startsWith('/api/realtime/domestic/stock/')) {
    const codes = u.pathname.split('/').pop().split(',');
    return Response.json({ datas: codes.map((c, i) => row(c, i)) });
  }
  if (u.host === 'polling.finance.naver.com' && u.pathname.startsWith('/api/realtime/domestic/index/')) {
    return Response.json({ datas: [{ itemCode: 'KOSPI', marketStatus: 'CLOSE', closePriceRaw: '1', compareToPreviousClosePriceRaw: '0', fluctuationsRatioRaw: '0' },
      { itemCode: 'KOSDAQ', marketStatus: 'CLOSE', closePriceRaw: '1', compareToPreviousClosePriceRaw: '0', fluctuationsRatioRaw: '0' }] });
  }
  throw new Error('test: unexpected fetch ' + u.href);
};

let iso = 0;
async function call(path, env = { ASSET_BASE: ASSET }) {
  const W = (await import(SRC + '?i=' + (++iso))).default;
  const pending = [];
  const res = await W.fetch(new Request('https://panse.pages.dev' + path), env, { waitUntil: p => pending.push(p) });
  await Promise.all(pending);
  return res;
}

console.log('ⓐ /data/alerts.json — static from ASSET_BASE like the other daily files');
await t('200, JSON content type, 10-minute cache, CORS to panse.pages.dev, body as committed', async () => {
  const r = await call('/data/alerts.json');
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-type'), /^application\/json/);
  assert.equal(r.headers.get('cache-control'), 'public, max-age=600');
  assert.equal(r.headers.get('access-control-allow-origin'), ORIGIN);
  const j = await r.json();
  assert.deepEqual(j.c['079550'], { a: 'caution' });
  assert.equal(j.at, '07:51');
});
await t('a second request is served from the edge cache (no new upstream fetch)', async () => {
  const before = fetched.filter(u => u.endsWith('/alerts.json')).length;
  const r = await call('/data/alerts.json');
  assert.equal(r.status, 200);
  assert.equal(fetched.filter(u => u.endsWith('/alerts.json')).length, before);
});
await t('missing upstream file → 404 {error}, not cached', async () => {
  const keep = files.get('alerts.json'); files.delete('alerts.json'); cacheStore.clear();
  try {
    const r = await call('/data/alerts.json');
    assert.equal(r.status, 404);
    assert.ok((await r.json()).error);
    assert.ok(![...cacheStore.keys()].some(k => k.includes('alerts')), 'a 404 must not be cached');
  } finally { files.set('alerts.json', keep); }
});

console.log('② /data/marks.json — static from ASSET_BASE like alerts.json');
await t('200, JSON, 10-minute cache, CORS, body as committed; missing → 404 not cached', async () => {
  const r = await call('/data/marks.json');
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-type'), /^application\/json/);
  assert.equal(r.headers.get('cache-control'), 'public, max-age=600');
  assert.equal(r.headers.get('access-control-allow-origin'), ORIGIN);
  assert.deepEqual((await r.json()).c['005930'], [37795.3, 374500, 96200, '2026-06-19', '2025-11-24']);
  const keep = files.get('marks.json'); files.delete('marks.json'); cacheStore.clear();
  try {
    const m = await call('/data/marks.json');
    assert.equal(m.status, 404);
    assert.ok(![...cacheStore.keys()].some(k => k.includes('marks')), 'a 404 must not be cached');
  } finally { files.set('marks.json', keep); }
});

console.log('① /data/theme_why/<id>.json — one file per theme');
await t('known id → 200 + JSON + 10-minute cache + CORS, read from web/theme_why/<id>.json', async () => {
  const r = await call('/data/theme_why/576.json');
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-type'), /^application\/json/);
  assert.equal(r.headers.get('cache-control'), 'public, max-age=600');
  assert.equal(r.headers.get('access-control-allow-origin'), ORIGIN);
  assert.equal((await r.json()).r['393210'], '퓨리오사AI 투자 이력 부각.');
  assert.ok(fetched.includes(ASSET + 'theme_why/576.json'));
});
await t('unknown id → 404 from upstream (not cached)', async () => {
  const r = await call('/data/theme_why/9999.json');
  assert.equal(r.status, 404);
});
await t('only 1–5 digit ids without a leading zero reach upstream (no traversal, no other names)', async () => {
  const before = fetched.length;
  for (const p of ['/data/theme_why/0576.json', '/data/theme_why/123456.json', '/data/theme_why/abc.json', '/data/theme_why/..%2Funiverse.json',
    '/data/theme_why/576.json/x', '/data/theme_why/', '/data/theme_why/576.JSON', '/data/theme_why/-1.json']) {
    const r = await call(p);
    assert.equal(r.status, 404, p);
  }
  assert.equal(fetched.length, before, 'none of them may fetch anything');
});

console.log('ⓐ /api/quotes rows: hx:1 only for 거래정지');
const rowsOf = async path => { cacheStore.clear(); const r = await call(path); assert.equal(r.status, 200); return new Map((await r.json()).stocks.map(s => [s.c, s])); };
await t('tradableStatus halt → hx:1; stop / sessionRestricted / tradable → no hx key', async () => {
  const m = await rowsOf('/api/quotes');
  assert.equal(m.get(TOP[0]).hx, 1);
  assert.ok(!('hx' in m.get(TOP[1])), 'afterMarketOperationHalt (stop) is not a halt');
  assert.ok(!('hx' in m.get(TOP[2])), 'sessionRestricted is not a halt');
  assert.ok(!('hx' in m.get(TOP[10])), 'tradable');
  assert.equal(m.get(TOP[5]).hx, 1, 'HALT in another case');
});
await t('no tradableStatus: tradeStopType HALTED → hx:1, TRADING → none', async () => {
  const m = await rowsOf('/api/quotes');
  assert.equal(m.get(TOP[3]).hx, 1);
  assert.ok(!('hx' in m.get(TOP[4])));
});
await t('exactly the halted rows carry hx (two halt rows + one tradeStopType fallback), the other keys are unchanged', async () => {
  const m = await rowsOf('/api/quotes');
  assert.equal(m.size, TOP.length);
  assert.deepEqual([...m.values()].filter(s => s.hx).map(s => s.c).sort(), [TOP[0], TOP[3], TOP[5]].sort());
  const keys = new Set(Object.keys(m.get(TOP[10])));
  for (const k of ['c', 'n', 'm', 's', 'i', 'cap', 'p', 'd', 'r', 'tv', 'v']) assert.ok(keys.has(k), k);
});
await t('?codes= and ?scope=all rows carry the same key', async () => {
  const a = await rowsOf(`/api/quotes?codes=${TOP[0]},${TOP[1]}`);
  assert.equal(a.get(TOP[0]).hx, 1);
  assert.ok(!('hx' in a.get(TOP[1])));
  const all = await rowsOf('/api/quotes?scope=all');
  assert.equal(all.get(TOP[0]).hx, 1);
});
await t('breadth rows stay [code, ratio, lim?, nxr?] (no hx)', async () => {
  cacheStore.clear();
  const r = await call('/api/breadth?m=K&part=1');
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.ok(j.rows.every(x => Array.isArray(x) && x.length <= 4 && typeof x[0] === 'string'));
  assert.ok(j.rows.every(x => x.length === 2), 'no limit / NXT in these fixtures → two cells');
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
