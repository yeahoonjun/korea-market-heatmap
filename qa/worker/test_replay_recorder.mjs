// Replay recorder (worker/src/index.js scheduled() → recordFrame) with a fake KV, a fake clock and a scripted upstream.
// Offline: Naver polling and universe.json are synthesised here (universe = web/universe.json of this checkout).
//   node qa/worker/test_replay_recorder.mjs            exit 0 = all pass, 1 = a recorder check failed,
//                                                      2 = recorder fine but wrangler.toml's cron misses a KRX weekday
//   WORKER_MODULE=worker/dist/worker.js node qa/worker/test_replay_recorder.mjs   — the same checks on the bundle
// Each "isolate" is a fresh import of the Worker module (?iso=N), so module memory (recMem, universeMem, statusMem,
// kvBulk) starts empty exactly like a new Cloudflare isolate; KV and the edge cache are shared like in production.
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const UNIVERSE = readFileSync(new URL('web/universe.json', ROOT), 'utf8');
const TOML = readFileSync(new URL('worker/wrangler.toml', ROOT), 'utf8');
const U = JSON.parse(UNIVERSE);
const CODES = [];
for (const m of ['K', 'Q']) for (let k = 0; k + 8 <= U[m].length; k += 8) CODES.push(U[m].slice(k, k + 6));
const ORIGIN = 'https://panse.pages.dev';
const CRON_OK = '* 0-7 * * MON-FRI';

/* ── harness ─────────────────────────────── */
let pass = 0, failed = 0;
const check = (name, ok, detail) => {
  if (ok) { pass++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail !== undefined ? '  → ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)) : '')); }
};
const section = s => console.log('\n' + s);

// fake clock (the Worker reads Date.now(); scheduled times come from the event)
const realNow = Date.now;
let NOW = realNow();
Date.now = () => NOW;
const kst = s => Date.parse(s + (s.length === 16 ? ':00' : '') + '+09:00');
const kstIso = ms => new Date(ms + 9 * 3600e3).toISOString().slice(0, 19) + '+09:00';

// edge cache (shared, like one colo)
const cacheStore = new Map();
globalThis.caches = { default: {
  async match(req) { const e = cacheStore.get(req.url); return e ? e.clone() : undefined; },
  async put(req, res) { cacheStore.set(req.url, res.clone()); },
  async delete(req) { return cacheStore.delete(req.url); },
} };

// upstream script
const inj = {};
const resetInj = () => Object.assign(inj, { stock: 'ok', index: 'ok', universe: 'ok', stockStatus: 'OPEN', indexStatus: 'OPEN', tradedAt: null, end: '1530', zeroFrac: 0 });
resetInj();
let calls = {};
const count = k => { calls[k] = (calls[k] || 0) + 1; };
const hang = init => new Promise((_, rej) => {
  const s = init && init.signal;
  if (!s) return setTimeout(() => rej(new Error('test: upstream hung and no timeout signal was passed')), 3000);
  s.addEventListener('abort', () => rej(s.reason || new Error('aborted')));
});
function stockRows(codes) {
  const at = inj.tradedAt || kstIso(NOW - 20e3);
  return codes.map((c, i) => ({
    itemCode: c, stockName: 'S' + c,
    closePriceRaw: i < codes.length * inj.zeroFrac ? '0' : String(10000 + i * 10),
    compareToPreviousClosePriceRaw: '100', fluctuationsRatioRaw: '1.01', marketValueFullRaw: '1000000000000',
    accumulatedTradingValueRaw: '100000000', accumulatedTradingVolumeRaw: '1000', openPriceRaw: '9900', highPriceRaw: '10100', lowPriceRaw: '9800',
    marketStatus: inj.stockStatus, localTradedAt: at,
    stockExchangeType: { code: 'KS', startTime: '0900', endTime: inj.end },
    compareToPreviousPrice: { code: '2', name: 'RISING' },
  }));
}
globalThis.fetch = async (input, init = {}) => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  if (u.host === 'assets.test' && u.pathname === '/universe.json') {
    count('universe');
    if (inj.universe === 500) return new Response('upstream error', { status: 500 });
    if (inj.universe === 'garbage') return new Response('<html>429 Too Many Requests</html>', { status: 200 });
    if (inj.universe === 'hang') return hang(init);
    return new Response(UNIVERSE);
  }
  if (u.host === 'polling.finance.naver.com' && u.pathname.startsWith('/api/realtime/domestic/stock/')) {
    count('stock');
    if (inj.stock === 500) return new Response('{}', { status: 500 });
    if (inj.stock === 'hang') return hang(init);
    const codes = u.pathname.split('/').pop().split(',');
    return Response.json({ pollingInterval: 70000, datas: inj.stock === 'empty' ? [] : stockRows(codes) });
  }
  if (u.host === 'polling.finance.naver.com' && u.pathname.startsWith('/api/realtime/domestic/index/')) {
    count('index');
    if (inj.index === 500) return new Response('{}', { status: 500 });
    return Response.json({ datas: [
      { itemCode: 'KOSPI', marketStatus: inj.indexStatus, closePriceRaw: '5290.53', compareToPreviousClosePriceRaw: '-52.20', fluctuationsRatioRaw: '-0.98' },
      { itemCode: 'KOSDAQ', marketStatus: inj.indexStatus, closePriceRaw: '699.66', compareToPreviousClosePriceRaw: '3.13', fluctuationsRatioRaw: '0.45' },
    ] });
  }
  throw new Error('test: unexpected fetch ' + u);
};

// fake KV: bulk get (array → Map) like Workers KV, single get, put; failure injection; op log
function makeKV() {
  const m = new Map(), log = [], fail = { get: null, put: null, putKey: null };
  const val = (k, type) => (m.has(k) ? (type === 'json' ? JSON.parse(m.get(k)) : m.get(k)) : null);
  return {
    m, log, fail,
    async get(k, type) {
      if (fail.get) throw new Error(fail.get);
      if (Array.isArray(k)) { log.push('bulk:' + k.length); return new Map(k.map(x => [x, val(x, type)])); }
      log.push('get:' + k); return val(k, type);
    },
    async put(k, v) {
      if (fail.put && (!fail.putKey || fail.putKey.test(k))) throw new Error(fail.put);
      log.push('put:' + k); m.set(k, String(v));
    },
    json(k) { return m.has(k) ? JSON.parse(m.get(k)) : null; },
    puts() { return log.filter(x => x.startsWith('put:')).map(x => x.slice(4)); },
  };
}

let iso = 0;
const MODULE = process.env.WORKER_MODULE || 'worker/src/index.js';   // WORKER_MODULE=worker/dist/worker.js tests the bundle
const isolate = async () => (await import(new URL(MODULE + '?iso=' + (++iso), ROOT).href)).default;
const logs = { error: [], log: [] };
async function fire(w, env, at, cron = CRON_OK) {
  const ms = kst(at);
  NOW = ms + 3000;                                     // the handler runs a few seconds after the nominal minute
  env.REPLAY.log.length = 0; calls = {};
  const oe = console.error, ol = console.log;
  logs.error = []; logs.log = [];
  console.error = (...a) => logs.error.push(a.join(' '));
  console.log = (...a) => logs.log.push(a.join(' '));
  const pending = [];
  let threw = null;
  const t0 = realNow();
  const keep = setInterval(() => {}, 1000);            // AbortSignal.timeout timers are unref'd in Node; keep the loop alive
  try { await w.scheduled({ scheduledTime: ms, cron, type: 'scheduled' }, env, { waitUntil: p => pending.push(p) }); await Promise.all(pending); }
  catch (e) { threw = e; }
  finally { clearInterval(keep); console.error = oe; console.log = ol; }
  return { threw, ms: realNow() - t0 };
}
const newEnv = () => ({ ASSET_BASE: 'https://assets.test/', REPLAY: makeKV() });
const frame = (env, day, t) => env.REPLAY.json(`replay:${day}:${t}`);
const status = env => env.REPLAY.json('replay:status');

/* ── 1. open-market minutes write ─────────────────────────────── */
section('1. open market (Fri 2026-11-13, the day that was lost)');
{
  resetInj(); cacheStore.clear();
  const w = await isolate(), env = newEnv();
  let r = await fire(w, env, '2026-11-13T10:05');
  check('scheduled() resolves', !r.threw, r.threw && String(r.threw));
  const codes = env.REPLAY.json('replay:20261113:codes');
  check('codes key written (600, universe order)', Array.isArray(codes) && codes.length === 600 && codes.join() === CODES.join(), codes && codes.length);
  const f = frame(env, '20261113', '1005');
  check('frame 1005 written, aligned to codes', f && f.p.length === 600 && f.r.length === 600 && f.p.every(x => x > 0) && f.e === '1530', f && { n: f.p.length, e: f.e });
  check('frame carries index + previous close', f && f.i[0] === 5290.53 && f.i[1] === 699.66 && f.b[0] === 5342.73 && f.b[1] === 696.53, f && { i: f.i, b: f.b });
  check('replay:days lists the day', (env.REPLAY.json('replay:days') || []).includes('20261113'));
  check('5-minute grid minute does not touch replay:minute', !env.REPLAY.m.has('replay:minute'));
  let st = status(env);
  check('status: wrote 1005', st && st.result === 'wrote' && st.t === '1005' && st.day === '2026-11-13' && st.lastWrote === '1005' && st.errors === 0 && st.rows === 600 && st.cron === CRON_OK, st);
  check('first minute = 1 KV batch read', env.REPLAY.log.filter(x => x.startsWith('bulk:') || x.startsWith('get:')).length === 1, env.REPLAY.log);
  check('upstream: 1 stock call + 1 index call + universe', calls.stock === 1 && calls.index === 1 && calls.universe === 1, calls);

  r = await fire(w, env, '2026-11-13T10:06');
  check('off-grid minute 1006 written', !!frame(env, '20261113', '1006'));
  check('replay:minute lists the day', (env.REPLAY.json('replay:minute') || []).includes('20261113'));
  check('same outcome within 5 min → no status write', !env.REPLAY.puts().includes('replay:status'), env.REPLAY.puts());
  check('steady minute = frame (+ minute list once) only', env.REPLAY.puts().filter(k => k !== 'replay:minute').join() === 'replay:20261113:1006', env.REPLAY.puts());
  await fire(w, env, '2026-11-13T10:07');
  check('steady minute 1007: exactly one put', env.REPLAY.puts().join() === 'replay:20261113:1007', env.REPLAY.puts());
  await fire(w, env, '2026-11-13T10:11');
  st = status(env);
  check('heartbeat after ≥5 min: status rewritten (t 1011, since kept)', st.t === '1011' && st.result === 'wrote' && st.since === kst('2026-11-13T10:05') + 3000 && st.lastWrote === '1011', st);

  // a second invocation for the same minute (retry) is a duplicate: no fetch, no status write
  await fire(w, env, '2026-11-13T10:11');
  check('duplicate minute: no upstream call, no write', !calls.stock && env.REPLAY.puts().length === 0, { calls, puts: env.REPLAY.puts() });
}

/* ── 2. skips with the right reason ─────────────────────────────── */
section('2. skips');
{
  resetInj(); cacheStore.clear();
  const w = await isolate(), env = newEnv();
  for (const [at, why] of [['2026-11-13T08:59', 'before 09:00'], ['2026-11-13T16:31', 'after 16:30'], ['2026-11-14T10:00', 'Saturday'], ['2026-11-15T10:00', 'Sunday']]) {
    await fire(w, env, at);
    check(`outside hours (${why}): no KV op, no fetch`, env.REPLAY.log.length === 0 && Object.keys(calls).length === 0, { log: env.REPLAY.log, calls });
  }
  check('outside hours leave no status', !env.REPLAY.m.has('replay:status'));

  // after the end: 15:30 written (index already CLOSE, data stamped today), 15:31 answered from the 15:30 frame without a fetch
  inj.indexStatus = 'CLOSE'; inj.stockStatus = 'CLOSE'; inj.tradedAt = '2026-11-13T15:30:00+09:00';
  await fire(w, env, '2026-11-13T15:30');
  check('15:30 frame written although the indices already say CLOSE', !!frame(env, '20261113', '1530'));
  await fire(w, env, '2026-11-13T15:31');
  let st = status(env);
  check('15:31 → skipped:after-end, no upstream call', st.result === 'skipped:after-end' && st.t === '1531' && !calls.stock, { st, calls });
  check('after-end status keeps lastWrote 1530', st.lastWrote === '1530', st);
  await fire(w, env, '2026-11-13T15:32');
  check('same skip within 5 min → no status write', env.REPLAY.puts().length === 0, env.REPLAY.puts());

  // after the end known only from the data (no 15:30 frame that day)
  resetInj(); inj.indexStatus = 'CLOSE'; inj.tradedAt = '2026-11-16T15:30:00+09:00';
  await fire(w, env, '2026-11-16T15:35');
  st = status(env);
  check('15:35 with endTime 1530 in the data → skipped:after-end', st.result === 'skipped:after-end' && st.day === '2026-11-16' && !env.REPLAY.m.has('replay:20261116:1535'), st);

  // 수능 day: endTime 1630
  resetInj(); inj.end = '1630';
  await fire(w, env, '2026-11-19T16:00');
  check('endTime 1630 (수능): 16:00 written with e=1630', frame(env, '20261119', '1600') && frame(env, '20261119', '1600').e === '1630');
  await fire(w, env, '2026-11-19T16:30');
  check('endTime 1630: 16:30 written', !!frame(env, '20261119', '1630'));

  // holiday: indices CLOSE, last trade stamped the previous trading day → nothing recorded, not even at 15:30
  resetInj(); inj.indexStatus = 'CLOSE'; inj.stockStatus = 'CLOSE'; inj.tradedAt = '2026-12-30T15:30:00+09:00';
  for (const t of ['0905', '1200', '1530']) await fire(w, env, `2026-12-31T${t.slice(0, 2)}:${t.slice(2)}`);
  st = status(env);
  check('holiday → skipped:closed all day (09:05, 12:00, 15:30)', st.result === 'skipped:closed' && ![...env.REPLAY.m.keys()].some(k => k.startsWith('replay:20261231')), { st, keys: [...env.REPLAY.m.keys()].filter(k => k.includes('20261231')) });
  check('holiday never enters replay:days', !(env.REPLAY.json('replay:days') || []).includes('20261231'));

  // index status stuck at CLOSE on a trading day, but trades are stamped this minute → recorded (used to skip all day)
  resetInj(); inj.indexStatus = 'CLOSE';
  await fire(w, env, '2026-11-20T10:00');
  check('index stuck CLOSE + fresh trades → written', !!frame(env, '20261120', '1000'));

  // a nonsense endTime in the data must not skip the day
  resetInj(); inj.end = '0900';
  await fire(w, env, '2026-11-20T10:01');
  check('endTime "0900" ignored (treated as 1530) → written', frame(env, '20261120', '1001') && frame(env, '20261120', '1001').e === '1530');
}

/* ── 3. one failing minute never blocks the next ─────────────────────────────── */
section('3. failures lose one minute only');
{
  resetInj(); cacheStore.clear();
  const w = await isolate(), env = newEnv();
  await fire(w, env, '2026-11-13T10:19');

  inj.stock = 500;
  let r = await fire(w, env, '2026-11-13T10:20');
  let st = status(env);
  check('Naver 5xx (twice) → no frame, scheduled() still resolves', !r.threw && !frame(env, '20261113', '1020'));
  check('Naver 5xx → status error with a short message', st.result === 'error' && /naver 500/.test(st.error) && !/\d{6},\d{6}/.test(st.error) && st.errors === 1, st);
  check('Naver 5xx → console.error logged', logs.error.some(l => /replay recorder 20261113 1020: naver 500/.test(l)), logs.error);
  check('chunk retried once', calls.stock === 2, calls);
  inj.stock = 'ok';
  await fire(w, env, '2026-11-13T10:21');
  st = status(env);
  check('next minute 1021 written', !!frame(env, '20261113', '1021'));
  check('status back to wrote, lastError + errors kept for the day', st.result === 'wrote' && st.errors === 1 && st.lastError && st.lastError.t === '1020', st);

  inj.stock = 'hang';
  env.REPLAY_TIMEOUT_MS = 150;
  r = await fire(w, env, '2026-11-13T10:22');
  st = status(env);
  check('hung upstream → aborted by the recorder timeout', st.result === 'error' && r.ms < 2500 && !frame(env, '20261113', '1022'), { st, ms: r.ms });
  delete env.REPLAY_TIMEOUT_MS; inj.stock = 'ok';
  await fire(w, env, '2026-11-13T10:23');
  check('next minute after a hang written', !!frame(env, '20261113', '1023'));

  inj.stock = 'empty';
  await fire(w, env, '2026-11-13T10:24');
  st = status(env);
  check('empty polling answer → error, no frame of nulls', st.result === 'error' && /0\/600 codes priced/.test(st.error) && !frame(env, '20261113', '1024'), st);
  inj.stock = 'ok'; inj.zeroFrac = 0.7;
  await fire(w, env, '2026-11-13T10:25');
  check('70 % zero prices → error, no frame', status(env).result === 'error' && !frame(env, '20261113', '1025'), status(env));
  inj.zeroFrac = 0.1;
  await fire(w, env, '2026-11-13T10:26');
  const f = frame(env, '20261113', '1026');
  check('10 % zero prices → frame with null for those rows', f && f.p.filter(x => x === null).length === 60 && f.r.filter(x => x === null).length === 60, f && f.p.filter(x => x === null).length);
  inj.zeroFrac = 0;

  env.REPLAY.fail.put = 'KV PUT failed: 429 Too Many Requests'; env.REPLAY.fail.putKey = /:1027$/;
  await fire(w, env, '2026-11-13T10:27');
  st = status(env);
  check('KV put 429 on the frame → error naming the key', st.result === 'error' && /KV put failed: 1027: KV PUT failed: 429/.test(st.error), st);
  env.REPLAY.fail.put = null; env.REPLAY.fail.putKey = null;
  await fire(w, env, '2026-11-13T10:28');
  check('next minute 1028 written', !!frame(env, '20261113', '1028'));

  env.REPLAY.fail.put = 'KV unavailable';                 // every put, the status put too
  r = await fire(w, env, '2026-11-13T10:29');
  check('all KV puts failing → scheduled() resolves, both errors logged', !r.threw && logs.error.length === 2 && /replay status/.test(logs.error[1]), logs.error);
  env.REPLAY.fail.put = null;
  await fire(w, env, '2026-11-13T10:30');
  check('next minute 1030 written', !!frame(env, '20261113', '1030'));

  env.REPLAY.fail.get = 'KV GET failed: 503';
  await fire(w, env, '2026-11-13T10:31');
  check('KV reads failing, warm isolate (knows the codes) → frame still written', !!frame(env, '20261113', '1031'));
  const w2 = await isolate();
  await fire(w2, env, '2026-11-13T10:32');
  check('KV reads failing, cold isolate → no frame (codes unknown), no list rewrite', !frame(env, '20261113', '1032') && !env.REPLAY.puts().includes('replay:days'), env.REPLAY.puts());
  check('…and its error is logged', logs.error.some(l => /KV read failed/.test(l)), logs.error);
  env.REPLAY.fail.get = null;
  await fire(w2, env, '2026-11-13T10:33');
  check('cold isolate, reads back → 1033 written', !!frame(env, '20261113', '1033'));
  check('replay:days intact after the read failures', (env.REPLAY.json('replay:days') || []).includes('20261113'));

  inj.index = 500;                                       // index call down: the regular session is judged by the clock + stock status
  await fire(w, env, '2026-11-13T10:34');
  const fi = frame(env, '20261113', '1034');
  check('index call 5xx → frame written with null indices', fi && fi.i[0] === null && fi.b[0] === null, fi && fi.i);
  inj.index = 'ok';
}

/* ── 4. first minute of a day: partial writes, bad stored codes ─────────────────────────────── */
section('4. day start');
{
  resetInj(); cacheStore.clear();
  const w = await isolate(), env = newEnv();
  env.REPLAY.fail.put = 'KV PUT failed'; env.REPLAY.fail.putKey = /:codes$/;
  await fire(w, env, '2026-11-16T09:00');
  check('codes put fails, frame put works → error, no codes key', status(env).result === 'error' && !env.REPLAY.m.has('replay:20261116:codes') && !!frame(env, '20261116', '0900'), status(env));
  env.REPLAY.fail.put = null; env.REPLAY.fail.putKey = null;
  await fire(w, env, '2026-11-16T09:01');
  check('next minute writes the codes key again', (env.REPLAY.json('replay:20261116:codes') || []).length === 600 && !!frame(env, '20261116', '0901'));

  env.REPLAY.m.set('replay:20261117:codes', '[]');        // a corrupt (empty) list must not wedge the day
  const w2 = await isolate();
  await fire(w2, env, '2026-11-17T09:00');
  check('empty stored code list → replaced, frame has 600 rows', (env.REPLAY.json('replay:20261117:codes') || []).length === 600 && frame(env, '20261117', '0900').p.length === 600);

  await fire(w2, env, '2026-11-17T15:30');
  await fire(w2, env, '2026-11-18T09:00');                // the isolate's memory of yesterday is not reused
  check('day rollover: new day gets its own codes key + frame', env.REPLAY.m.has('replay:20261118:codes') && !!frame(env, '20261118', '0900'));
  check('day rollover: status errors reset to 0', status(env).errors === 0 && status(env).day === '2026-11-18', status(env));
}

/* ── 5. universe.json ─────────────────────────────── */
section('5. universe.json');
{
  resetInj(); cacheStore.clear();
  const env = newEnv();
  let w = await isolate();
  inj.universe = 500;
  await fire(w, env, '2026-11-16T10:00');
  check('cold isolate + universe 500 → error that minute', status(env).result === 'error' && /universe 500/.test(status(env).error), status(env));
  inj.universe = 'ok';
  await fire(w, env, '2026-11-16T10:01');
  check('universe back → next minute written', !!frame(env, '20261116', '1001'));

  cacheStore.clear(); w = await isolate();
  inj.universe = 'garbage';
  await fire(w, env, '2026-11-16T10:02');
  check('cold isolate + non-JSON universe (200) → error', status(env).result === 'error', status(env));
  check('bad universe body not cached', ![...cacheStore.keys()].some(k => k.includes('universe.json')));
  inj.universe = 'ok';
  await fire(w, env, '2026-11-16T10:03');
  check('universe fixed → next minute written (no hour-long wedge)', !!frame(env, '20261116', '1003'));

  inj.universe = 500; cacheStore.clear();
  await fire(w, env, '2026-11-16T10:20');                // > 10 min later: universeMem is due for a refresh, the fetch fails
  check('warm isolate + universe 500 → stale universe used, frame written', !!frame(env, '20261116', '1020'));
  inj.universe = 'hang'; cacheStore.clear(); w = await isolate();
  const r = await fire(w, env, '2026-11-16T10:21');
  check('universe fetch hanging → bounded (≤ 15 s timeout), minute errors', status(env).result === 'error' && r.ms < 16000, { st: status(env), ms: r.ms });
  inj.universe = 'ok';
}

/* ── 6. GET /api/replay/status ─────────────────────────────── */
section('6. /api/replay/status');
{
  resetInj(); cacheStore.clear();
  const w = await isolate(), env = newEnv();
  const get = async () => {
    const res = await w.fetch(new Request('https://panse.pages.dev/api/replay/status'), env, { waitUntil() {} });
    return { res, body: await res.json() };
  };
  NOW = kst('2026-11-16T08:00');
  let { res, body } = await get();
  check('no status yet → 200, result null + server time', res.status === 200 && body.result === null && body.now === NOW && body.due === false, body);
  for (const t of ['10:25', '10:26', '10:27', '10:28', '10:29']) await fire(w, env, '2026-11-16T' + t);
  NOW = kst('2026-11-16T10:30') + 10e3;
  ({ res, body } = await get());
  check('headers: no-store + CORS origin', res.headers.get('cache-control') === 'no-store' && res.headers.get('access-control-allow-origin') === ORIGIN, Object.fromEntries(res.headers));
  check('shape', ['v', 'at', 'day', 't', 'result', 'since', 'lastWrote', 'errors', 'cron', 'now', 'nowKst', 'atKst', 'ageSec', 'due', 'recent', 'stale'].every(k => k in body), Object.keys(body));
  check('values while recording', body.result === 'wrote' && body.day === '2026-11-16' && body.t === '1025' && body.lastWrote === '1025' && body.nowKst === '2026-11-16 10:30:10' && body.due === true && body.stale === false && Object.keys(body.recent).join() === '1025,1026,1027,1028,1029' && Object.values(body.recent).every(Boolean), body);
  NOW = kst('2026-11-16T10:45');
  ({ body } = await get());
  check('no frame in the last 5 minutes on a weekday → stale', body.due === true && body.stale === true && body.ageSec > 900, body);
  NOW = kst('2026-11-14T12:00');
  ({ body } = await get());
  check('weekend → due false, stale false, recent null', body.due === false && body.stale === false && body.recent === null, body);
  const opt = await w.fetch(new Request('https://panse.pages.dev/api/replay/status', { method: 'OPTIONS' }), env, { waitUntil() {} });
  check('OPTIONS preflight as other /api routes', opt.status === 204 && opt.headers.get('access-control-allow-origin') === ORIGIN);
  const none = await w.fetch(new Request('https://panse.pages.dev/api/replay/status'), { ASSET_BASE: 'https://assets.test/' }, { waitUntil() {} });
  check('no KV binding → 503 {error}', none.status === 503 && (await none.json()).error);
}

/* ── 7. the cron in wrangler.toml (Cloudflare: day of week 1 = Sunday … 7 = Saturday) ─────────────────────────────── */
section('7. wrangler.toml cron covers every KRX weekday (Cloudflare day-of-week numbering)');
const DOW = { SUN: 1, MON: 2, TUE: 3, WED: 4, THU: 5, FRI: 6, SAT: 7 };
function field(spec, lo, hi, names) {
  const out = new Set();
  for (let part of spec.split(',')) {
    let step = 1;
    if (part.includes('/')) { const [a, b] = part.split('/'); part = a; step = +b; }
    const v = s => (names && names[s.toUpperCase()]) || +s;
    let [a, b] = part === '*' ? [lo, hi] : part.split('-').map(v);
    if (b === undefined) b = part.includes('/') ? hi : a;
    for (let x = a; x <= b; x += step) out.add(x);
  }
  return out;
}
const crons = ((TOML.match(/^crons\s*=\s*\[([^\]]*)\]/m) || [])[1] || '').match(/"[^"]+"/g)?.map(s => s.slice(1, -1)) || [];
const fires = (cron, ms) => {
  const [mi, h, dom, mon, dow] = cron.trim().split(/\s+/), d = new Date(ms);
  return field(mi, 0, 59).has(d.getUTCMinutes()) && field(h, 0, 23).has(d.getUTCHours()) && field(dom, 1, 31).has(d.getUTCDate())
    && field(mon, 1, 12).has(d.getUTCMonth() + 1) && field(dow, 1, 7, DOW).has(d.getUTCDay() + 1);
};
let cronBad = false;
for (const [day, name] of [['2026-11-16', 'Mon'], ['2026-11-17', 'Tue'], ['2026-11-18', 'Wed'], ['2026-11-19', 'Thu'], ['2026-11-20', 'Fri']]) {
  const miss = ['09:00', '12:00', '15:30', '16:30'].filter(t => !crons.some(c => fires(c, kst(`${day}T${t}`))));
  if (miss.length) cronBad = true;
  console.log(`  ${miss.length ? 'FAIL' : 'ok  '} ${name} ${day}: ${miss.length ? 'no cron at ' + miss.join(', ') + ' KST' : 'fires 09:00–16:30 KST'}  (${crons.join(' | ')})`);
}
const sunday = crons.some(c => fires(c, kst('2026-11-15T10:00')));
console.log(`  ${sunday ? 'note' : 'ok  '} Sunday: ${sunday ? 'fires (wasted invocations; the recorder skips them)' : 'does not fire'}`);
check('fixture: CRON_OK covers Mon–Fri and not Sunday', ['2026-11-16', '2026-11-20'].every(d => fires(CRON_OK, kst(d + 'T09:00'))) && !fires(CRON_OK, kst('2026-11-15T10:00')) && !fires('* 0-7 * * 1-5', kst('2026-11-13T10:00')));

Date.now = realNow;
console.log(`\n${pass} passed, ${failed} failed${cronBad ? ' · wrangler.toml cron misses a KRX weekday — use "' + CRON_OK + '"' : ''}`);
process.exit(failed ? 1 : cronBad ? 2 : 0);
