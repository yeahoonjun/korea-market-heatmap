// QA: 10분 · 30분 · 60분봉 (/api/stock/:code/chart?iv=10m|30m|60m, AGENTS §3; 사용자 2026-11-14 08:10 "분봉으로 통합하고 누르면
// 1분봉 5분봉 10분봉 30분봉 60분봉 선택 가능하게"). The Worker groups Naver's 5-minute bars; this checks the grouping (boundaries, the
// closing print, after-hours, a late day, gaps, the partial last bucket, volume sums), `to` paging, `count`, `warm`/`pre`, `more`, and
// that the result equals Naver's own minute10/30/60 wherever the grid is the same (real rows of 2026-11-13).
// No network: fetch is mocked.   node qa/worker/test_chart_group.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const SRC = new URL('../../worker/src/index.js', import.meta.url).href;
const REAL = JSON.parse(readFileSync(new URL('./fixtures/naver_minute_005930_20261113.json', import.meta.url), 'utf8'));
const KST = s => Date.parse(s + '+09:00');
const sec = (d, hm) => KST(`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}T${hm.slice(0, 2)}:${hm.slice(2, 4)}:00`) / 1000;
const hmOf = t => { const k = new Date((t + 32400) * 1000); return String(k.getUTCHours()).padStart(2, '0') + String(k.getUTCMinutes()).padStart(2, '0'); };
const dayOf = t => new Date((t + 32400) * 1000).toISOString().slice(0, 10).replace(/-/g, '');

let clock = KST('2026-11-12T10:22:00');
Date.now = () => clock;
globalThis.caches = { default: { async match() { return undefined; }, async put() {} } };

/* ── synthetic 5-minute rows (Naver shape) ── */
let seq = 0;
function row(d, hm) {
  const i = seq++, o = 1000 + (i % 37) * 3, c = o + ((i % 3) - 1) * 2;
  return { localDateTime: d + hm + '00', openPrice: o, highPrice: Math.max(o, c) + 3, lowPrice: Math.min(o, c) - 2, currentPrice: c, accumulatedTradingVolume: 100 + i };
}
const range = (from, to, step = 5) => { const out = []; for (let m = +from.slice(0, 2) * 60 + +from.slice(2); m <= +to.slice(0, 2) * 60 + +to.slice(2); m += step) out.push(String(Math.floor(m / 60)).padStart(2, '0') + String(m % 60).padStart(2, '0')); return out; };
const D1 = '20261109', D2 = '20261110', D3 = '20261111', D4 = '20261112';   // normal · illiquid (gaps) · late day (10:00–16:30) · today (09:00–10:20, in progress)
const SYN = [
  ...range('0900', '1515').map(hm => row(D1, hm)), row(D1, '1530'), ...range('1540', '1955').map(hm => row(D1, hm)),
  ...['0900', '0925', '1040', '1510', '1530', '1605'].map(hm => row(D2, hm)),
  ...range('1000', '1615').map(hm => row(D3, hm)), row(D3, '1630'), ...range('1640', '1955').map(hm => row(D3, hm)),
  ...range('0900', '1020').map(hm => row(D4, hm)),
];

let rows = SYN;
const calls = [];
globalThis.fetch = async input => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  calls.push(u.pathname);
  const m = u.pathname.match(/^\/chart\/domestic\/item\/(\w{6})\/(\w+)$/);
  if (u.hostname === 'api.stock.naver.com' && m) return new Response(JSON.stringify(m[2] === 'minute5' ? rows : []), { headers: { 'content-type': 'application/json' } });
  throw new Error('unexpected fetch ' + u.href);
};
const W = (await import(SRC)).default;
async function chart(q) {
  const res = await W.fetch(new Request('https://panse.pages.dev/api/stock/005930/chart?' + q), {}, { waitUntil() {} });
  return { status: res.status, body: await res.json(), cc: res.headers.get('cache-control') };
}

// a plain reference: the 5-minute rows of one bucket → the expected bar
function agg(list) {
  return { o: list[0].openPrice, h: Math.max(...list.map(r => r.highPrice)), l: Math.min(...list.map(r => r.lowPrice)), c: list[list.length - 1].currentPrice, v: list.reduce((a, r) => a + r.accumulatedTradingVolume, 0) };
}
const pick = (d, hms) => SYN.filter(r => r.localDateTime.startsWith(d) && hms.includes(r.localDateTime.slice(8, 12)));
const strip = b => ({ o: b.o, h: b.h, l: b.l, c: b.c, v: b.v });

const results = [];
async function test(name, fn) {
  rows = SYN; calls.length = 0;
  try { await fn(); results.push(['PASS', name]); } catch (e) { results.push(['FAIL', name, (e && e.stack) || e]); }
}
const all = async iv => (await chart(`iv=${iv}&count=1500`)).body.bars;

await test('shape: iv, interval, oldest first, minute5 upstream, 20 s edge cache, 400 for an unknown interval', async () => {
  for (const iv of ['10m', '30m', '60m']) {
    const r = await chart(`iv=${iv}&count=1500`);
    assert.equal(r.status, 200);
    assert.equal(r.body.iv, iv); assert.equal(r.body.interval, iv);
    assert.equal(r.cc, 'public, max-age=20');
    const ts = r.body.bars.map(b => b.t);
    assert.deepEqual(ts, ts.slice().sort((a, b) => a - b)); assert.equal(new Set(ts).size, ts.length);
    for (const b of r.body.bars) { assert.ok(b.l <= Math.min(b.o, b.c) && b.h >= Math.max(b.o, b.c)); assert.deepEqual(Object.keys(b), ['t', 'o', 'h', 'l', 'c', 'v']); }
    assert.equal(r.body.more, false); assert.equal(r.body.prevClose, null); assert.equal(r.body.pre, undefined);
  }
  assert.ok(calls.length && calls.every(p => p.endsWith('/minute5')), calls.join());
  const bad = await chart('iv=15m');
  assert.equal(bad.status, 400); assert.match(bad.body.error, /10m, 30m, 60m/);
  for (const iv of ['1m', '5m', 'day']) assert.equal((await chart(`iv=${iv}&count=3`)).status, 200);   // the old intervals still answer
});

await test('normal day: 60m = 09:00…15:00 (15:00 closes with the 15:30 print), after-hours 15:30 · 16:00 … 19:00', async () => {
  const b = (await all('60m')).filter(x => dayOf(x.t) === D1);
  assert.deepEqual(b.map(x => hmOf(x.t)), ['0900', '1000', '1100', '1200', '1300', '1400', '1500', '1530', '1600', '1700', '1800', '1900']);
  assert.deepEqual(strip(b[0]), agg(pick(D1, range('0900', '0955'))));
  assert.deepEqual(strip(b[6]), agg(pick(D1, ['1500', '1505', '1510', '1515', '1530'])), 'last regular bar ends with the closing print');
  assert.equal(b[6].c, pick(D1, ['1530'])[0].currentPrice, 'its close = the KRX close');
  assert.deepEqual(strip(b[7]), agg(pick(D1, ['1540', '1545', '1550', '1555'])), 'after-hours bucket from 15:30 (partial)');
  assert.deepEqual(strip(b[8]), agg(pick(D1, range('1600', '1655'))));
  assert.deepEqual(strip(b[11]), agg(pick(D1, range('1900', '1955'))));
});

await test('normal day: 30m and 10m boundaries', async () => {
  const b30 = (await all('30m')).filter(x => dayOf(x.t) === D1);
  assert.deepEqual(b30.map(x => hmOf(x.t)), [...range('0900', '1500', 30), ...range('1530', '1930', 30)]);
  assert.deepEqual(strip(b30[1]), agg(pick(D1, range('0930', '0955'))));
  assert.deepEqual(strip(b30[12]), agg(pick(D1, ['1500', '1505', '1510', '1515', '1530'])));
  assert.deepEqual(strip(b30[13]), agg(pick(D1, ['1540', '1545', '1550', '1555'])));
  const b10 = (await all('10m')).filter(x => dayOf(x.t) === D1);
  assert.deepEqual(b10.map(x => hmOf(x.t)), [...range('0900', '1520', 10), ...range('1540', '1950', 10)]);
  const last = b10[range('0900', '1520', 10).length - 1];
  assert.equal(hmOf(last.t), '1520'); assert.deepEqual(strip(last), agg(pick(D1, ['1530'])), '10m: the closing print is the 15:20 bar (the closing auction)');
  assert.deepEqual(strip(b10[1]), agg(pick(D1, ['0910', '0915'])));
});

await test('volume sums and price range are kept per day and interval', async () => {
  for (const iv of ['10m', '30m', '60m']) {
    const b = await all(iv);
    for (const d of [D1, D2, D3, D4]) {
      const src = SYN.filter(r => r.localDateTime.startsWith(d)), g = b.filter(x => dayOf(x.t) === d);
      assert.equal(g.reduce((a, x) => a + x.v, 0), src.reduce((a, r) => a + r.accumulatedTradingVolume, 0), iv + ' ' + d);
      assert.equal(Math.max(...g.map(x => x.h)), Math.max(...src.map(r => r.highPrice)));
      assert.equal(Math.min(...g.map(x => x.l)), Math.min(...src.map(r => r.lowPrice)));
      assert.equal(g[0].o, src[0].openPrice); assert.equal(g[g.length - 1].c, src[src.length - 1].currentPrice);
    }
  }
});

await test('gaps (an illiquid day): empty buckets are skipped, bars land in their own bucket', async () => {
  const b30 = (await all('30m')).filter(x => dayOf(x.t) === D2);
  assert.deepEqual(b30.map(x => hmOf(x.t)), ['0900', '1030', '1500', '1600']);
  assert.deepEqual(strip(b30[0]), agg(pick(D2, ['0900', '0925'])));
  assert.deepEqual(strip(b30[2]), agg(pick(D2, ['1510', '1530'])));
  const b60 = (await all('60m')).filter(x => dayOf(x.t) === D2);
  assert.deepEqual(b60.map(x => hmOf(x.t)), ['0900', '1000', '1500', '1600']);
});

await test('late day (trades at 15:20–15:29 → session 10:00–16:30): the 16:30 print closes 16:00, after-hours from 16:30', async () => {
  const b60 = (await all('60m')).filter(x => dayOf(x.t) === D3);
  assert.deepEqual(b60.map(x => hmOf(x.t)), ['1000', '1100', '1200', '1300', '1400', '1500', '1600', '1630', '1700', '1800', '1900']);
  assert.deepEqual(strip(b60[5]), agg(pick(D3, range('1500', '1555'))), '15:00–15:59 is a normal bucket that day');
  assert.deepEqual(strip(b60[6]), agg(pick(D3, ['1600', '1605', '1610', '1615', '1630'])));
  const b10 = (await all('10m')).filter(x => dayOf(x.t) === D3);
  assert.ok(b10.some(x => hmOf(x.t) === '1520') && b10.some(x => hmOf(x.t) === '1530') && !b10.some(x => hmOf(x.t) === '1630'));
});

await test('today in progress: the last bucket is partial', async () => {
  const b = (await all('60m')).filter(x => dayOf(x.t) === D4);
  assert.deepEqual(b.map(x => hmOf(x.t)), ['0900', '1000']);
  assert.deepEqual(strip(b[1]), agg(pick(D4, range('1000', '1020'))));
  const b30 = (await all('30m')).filter(x => dayOf(x.t) === D4);
  assert.deepEqual(b30.map(x => hmOf(x.t)), ['0900', '0930', '1000']);
});

await test('count · warm · pre · prevClose · more count grouped bars', async () => {
  const full = await all('30m');
  const r = (await chart('iv=30m&count=5&warm=3')).body;
  assert.equal(r.bars.length, 5); assert.equal(r.pre.length, 3);
  assert.deepEqual(r.bars, full.slice(-5)); assert.deepEqual(r.pre, full.slice(-8, -5));
  assert.equal(r.prevClose, full[full.length - 6].c); assert.equal(r.more, true);
  const big = (await chart(`iv=30m&count=${full.length - 2}&warm=2`)).body;
  assert.equal(big.more, false, 'count + warm = everything → no more'); assert.equal(big.pre.length, 2);
  const r0 = (await chart('iv=60m&count=4&warm=0')).body;
  assert.equal(r0.pre, undefined); assert.equal(r0.bars.length, 4);
  const w = (await chart('iv=10m&count=10&warm=120')).body;
  assert.equal(w.pre.length, 120); assert.ok(w.pre[119].t < w.bars[0].t);
});

await test('to: whole buckets before it (a cut mid-bucket keeps the bucket whole), 8-digit day, paging walks back without gaps', async () => {
  const full = await all('60m');
  const r = (await chart('iv=60m&count=3&to=' + D2 + '1000')).body;
  assert.ok(r.bars.every(b => b.t < sec(D2, '1000')));
  assert.deepEqual(r.bars.map(b => [dayOf(b.t), hmOf(b.t)]), [[D1, '1800'], [D1, '1900'], [D2, '0900']]);
  const mid = (await chart('iv=60m&count=2&to=' + D1 + '1015')).body;
  assert.deepEqual(mid.bars.map(b => hmOf(b.t)), ['0900', '1000']);
  assert.deepEqual(strip(mid.bars[1]), agg(pick(D1, range('1000', '1055'))), 'the 10:00 bucket is whole although to=10:15');
  const day = (await chart('iv=30m&count=1500&to=' + D3)).body;
  assert.ok(day.bars.length && day.bars.every(b => b.t < sec(D3, '0000')) && day.more === false);
  assert.deepEqual(day.bars, (await all('30m')).filter(b => b.t < sec(D3, '0000')));
  // the page's scroll-back: to = the start of the oldest bar it has
  for (const iv of ['10m', '30m', '60m']) {
    const want = await all(iv);
    let got = [], to = null, n = 0;
    for (;;) {
      const p = (await chart(`iv=${iv}&count=7&warm=4` + (to ? '&to=' + to : ''))).body;
      if (p.pre && p.pre.length && p.bars.length) assert.equal(p.pre[p.pre.length - 1].c, p.prevClose);
      got = (p.more ? [] : p.pre || []).concat(p.bars, got);   // at the end `pre` holds the oldest bars (the page shows them then)
      if (!p.more || !p.bars.length || ++n > 200) break;
      const k = new Date((p.bars[0].t + 32400) * 1000);
      to = k.toISOString().slice(0, 16).replace(/[-T:]/g, '');
    }
    assert.deepEqual(got, want, iv + ' paging = the whole list');
  }
});

await test('equals Naver minute10/30/60 (real 005930 rows, 2026-11-13) except the closing print and after-hours start', async () => {
  rows = REAL.minute5;
  const t = x => sec(x.localDateTime.slice(0, 8), x.localDateTime.slice(8, 12));
  // Naver's grid differs only where the closing print sits: its 10m 15:30 bar (ours 15:20), its 30m 15:00 (no print) and 15:30 (print +
  // after-hours), its 60m 15:00 (15:00–15:59 incl. after-hours). Every other bucket must be identical.
  const DIFF = { '10m': ['1530'], '30m': ['1500', '1530'], '60m': ['1500'] };
  for (const [iv, key] of [['10m', 'minute10'], ['30m', 'minute30'], ['60m', 'minute60']]) {
    const ours = new Map((await all(iv)).map(b => [b.t, b]));
    let same = 0;
    for (const x of REAL[key]) {
      const hm = x.localDateTime.slice(8, 12);
      if (DIFF[iv].includes(hm)) continue;
      const b = ours.get(t(x));
      assert.ok(b, iv + ' ' + hm);
      assert.deepEqual(strip(b), { o: x.openPrice, h: x.highPrice, l: x.lowPrice, c: x.currentPrice, v: x.accumulatedTradingVolume }, iv + ' ' + hm);
      same++;
    }
    assert.equal(same, REAL[key].length - DIFF[iv].length, iv + ' compared');
    const close = [...ours.values()].find(b => hmOf(b.t) === { '10m': '1520', '30m': '1500', '60m': '1500' }[iv]);
    assert.equal(close.c, REAL.minute5.find(x => x.localDateTime.endsWith('153000')).currentPrice, iv + ' last regular bar closes at the KRX close');
    assert.equal([...ours.values()].reduce((a, b) => a + b.v, 0), REAL.minute5.reduce((a, r) => a + r.accumulatedTradingVolume, 0));
  }
});

let fails = 0;
for (const [st, name, err] of results) { console.log(st + ' ' + name); if (err) { fails++; console.log(String(err).split('\n').slice(0, 6).join('\n')); } }
console.log(`\n${results.length - fails}/${results.length} passed`);
process.exit(fails ? 1 : 0);
