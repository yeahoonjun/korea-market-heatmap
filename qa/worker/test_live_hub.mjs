// 실시간 허브 MarketHub 동작 점검 — 가짜 DO 상태 · 가짜 소켓 · 가짜 시계로 Node에서 (docs/standards/realtime.md §13).
// 독립 리뷰(2026-11-14) 지적: 새 epoch, 저장 실패, 폴링 중 연결, 빈 응답, 10:00 개장일 · 휴장 판단, 테스트용 변수 제한.
//   node qa/worker/test_live_hub.mjs
import { MarketHub, configureLive, liveRoute } from '../../worker/src/live.js';
import { LIMITS, HOLIDAY_LATCH_MS, IDLE_RESET_MS } from '../../worker/src/live_core.js';

let pass = 0, fail = 0;
const ok = (name, cond, extra = '') => { if (cond) { pass++; console.log('  ok  ', name, extra); } else { fail++; console.log('  FAIL', name, extra); } };
const K = s => Date.parse(s + '+09:00');
let NOW = K('2026-11-16T10:00:00');                 // Monday
const realNow = Date.now; Date.now = () => NOW;

/* ── fakes: WebSocketPair, 101 responses, DO state ── */
class FakeSock {
  constructor() { this.sent = []; this.closed = null; this.att = null; }
  accept() { this.accepted = true; }
  send(t) { if (this.closed) throw new Error('closed'); this.sent.push(JSON.parse(t)); }
  close(code, reason) { if (!this.closed) this.closed = { code, reason }; }
  serializeAttachment(a) { this.att = JSON.parse(JSON.stringify(a)); }
  deserializeAttachment() { return this.att; }
}
globalThis.WebSocketPair = function () { const c = new FakeSock(), s = new FakeSock(); return { 0: c, 1: s }; };
globalThis.WebSocketRequestResponsePair = class { };
const R = globalThis.Response;
globalThis.Response = class extends R {
  constructor(body, init = {}) {
    if (init.status === 101) { super(null, { status: 200 }); Object.defineProperty(this, 'status', { value: 101 }); this.webSocket = init.webSocket; }
    else super(body, init);
  }
};
function fakeState() {
  const store = new Map(), sockets = [];
  const st = {
    putFails: false, alarm: null, setAlarms: 0, sockets,
    storage: {
      async get(k) { return store.has(k) ? JSON.parse(JSON.stringify(store.get(k))) : undefined; },
      async put(k, v) { if (st.putFails) throw new Error('disk full'); store.set(k, JSON.parse(JSON.stringify(v))); },
      async getAlarm() { return st.alarm; }, async setAlarm(t) { st.setAlarms++; st.alarm = t; }, async deleteAlarm() { st.alarm = null; },
    },
    acceptWebSocket(ws) { sockets.push(ws); },
    getWebSockets() { return sockets.filter(s => !s.closed); },
    setWebSocketAutoResponse() { },
    blockConcurrencyWhile(fn) { st.ready = fn(); return st.ready; },
  };
  return st;
}
async function newHub(env = {}) { const st = fakeState(); const hub = new MarketHub(st, env); await st.ready; return { hub, st }; }
const req = (q = '', host = 'panse.pages.dev') => new Request(`https://${host}/api/live${q}`, { headers: { upgrade: 'websocket' } });
const reqLocal = (q = '') => new Request(`http://127.0.0.1:8911/api/live${q}`, { headers: { upgrade: 'websocket' } });
async function connect(hub, r = req()) { const res = await hub.fetch(r); return { res, sock: res.webSocket ? hub.state.sockets[hub.state.sockets.length - 1] : null, body: res.status === 101 ? null : await res.json() }; }

/* ── a controllable upstream (the quotesCore answer) ── */
const rows = Array.from({ length: 600 }, (_, i) => ({ c: String(100000 + i).slice(-6), n: 'n' + i, m: i < 300 ? 'K' : 'Q', s: 's', i: 'i', cap: 1000, p: 10000 + i, d: 10, r: 0.1, tv: 1, v: 1 }));
let SRC = { startTime: '0900', endTime: '1530', status: 'OPEN', asOfDay: '2026-11-16', priced: 600, bump: 0, wait: null };
configureLive(async () => {
  if (SRC.wait) await SRC.wait;
  return {
    endTime: SRC.endTime, startTime: SRC.startTime,
    body: { asOf: `${SRC.asOfDay}T10:00:00+09:00`, source: 'test', marketStatus: { KOSPI: SRC.status, KOSDAQ: SRC.status }, afterHours: false, nxt: { session: null, open: false }, index: { KOSPI: { value: 1, change: 0, ratio: 0 } },
      stocks: rows.map((r, i) => ({ ...r, p: i < SRC.priced ? r.p + SRC.bump : 0 })) },
  };
});
const tick = async hub => { hub.state.alarm = null; await hub.alarm(); };   // the runtime consumes the alarm before calling alarm()

console.log('new epoch whenever rows restart (review 3)');
{
  const { hub } = await newHub();
  const a = await connect(hub);
  await tick(hub);
  const snap1 = a.sock.sent.find(m => m.t === 'snap');
  SRC.bump = 100; NOW += 3000; await tick(hub);
  const d = a.sock.sent.find(m => m.t === 'd');
  ok('first data → snapshot v1, then a delta v2', snap1 && snap1.v === 1 && d && d.v === 2 && d.b === 1);
  ok('the hello before any data already names the epoch of the first snapshot', a.sock.sent[0].t === 'hello' && a.sock.sent[0].epoch === snap1.epoch);
  a.sock.close(1000);
  NOW += IDLE_RESET_MS + 60e3;                                    // idle more than 10 minutes, no polls
  const b = await connect(hub, req(`?epoch=${snap1.epoch}&ver=2`));
  ok('resume after an idle reset: no deltas against the dropped rows', !b.sock.sent.some(m => m.t === 'd') && !b.sock.sent.some(m => m.t === 'snap'));
  SRC.bump = 50; await tick(hub);
  const snap2 = b.sock.sent.find(m => m.t === 'snap');
  ok('the next poll starts a NEW epoch with a snapshot (v1)', !!snap2 && snap2.epoch !== snap1.epoch && snap2.v === 1, snap2 ? `${snap1.epoch} → ${snap2.epoch}` : '');
  ok("the reconnecting page's hello already carried that new epoch", b.sock.sent[0].t === 'hello' && b.sock.sent[0].epoch === snap2.epoch && b.sock.sent[0].v === 0);
  const c = await connect(hub, req(`?epoch=${snap1.epoch}&ver=1`));
  ok('a page still holding the old epoch gets a snapshot, not deltas', c.sock.sent.some(m => m.t === 'snap' && m.epoch === snap2.epoch) && !c.sock.sent.some(m => m.t === 'd'));
}

console.log('failed counter write keeps the 101 (review 4)');
{
  const { hub, st } = await newHub();
  st.putFails = true;
  const errs = []; const ce = console.error; console.error = (...a) => errs.push(a.join(' '));
  let threw = null, res = null;
  try { res = (await connect(hub)).res; } catch (e) { threw = e; }
  console.error = ce;
  ok('connect returns 101 although storage.put throws', !threw && res && res.status === 101 && st.sockets.length === 1);
  ok('the failure is counted and logged', hub.stats.saveErrors >= 1 && errs.some(e => /could not save/.test(e)));
}

console.log('connect while a poll is running does not schedule a second alarm (nit)');
{
  const { hub, st } = await newHub();
  await connect(hub); await tick(hub);
  let release; SRC.wait = new Promise(r => { release = r; });
  st.alarm = null; const running = hub.alarm();                    // poll in flight, alarm consumed
  await new Promise(r => setTimeout(r, 5));
  const before = st.setAlarms;
  await connect(hub);
  ok('no setAlarm from the connect', st.setAlarms === before, `setAlarm calls ${before} → ${st.setAlarms}`);
  release(); SRC.wait = null; await running;
  ok('the running alarm reschedules itself once', st.setAlarms === before + 1 && st.alarm != null);
}

console.log('an empty / price-0 answer never becomes the snapshot (nit)');
{
  const { hub } = await newHub();
  const a = await connect(hub);
  SRC.priced = 200; await tick(hub);
  ok('200 priced rows of 600: no snapshot, counted as a failure', !a.sock.sent.some(m => m.t === 'snap') && hub.stats.fails === 1 && /thin answer/.test(hub.stats.lastErr), hub.stats.lastErr);
  ok('pages are told the answer failed (st)', a.sock.sent.some(m => m.t === 'st' && m.ok === false));
  SRC.priced = 600; await tick(hub);
  ok('the next good answer is the snapshot', a.sock.sent.some(m => m.t === 'snap'));
}

console.log('10:00-open day (수능 · first trading day) and holidays (review 2)');
{
  NOW = K('2026-11-19T09:10:00');                                  // Thursday 2026-11-19, 수능
  SRC = { startTime: '1000', endTime: '1630', status: 'CLOSE', asOfDay: '2026-11-18', priced: 600, bump: 0, wait: null };
  const { hub } = await newHub();
  const a = await connect(hub);
  ok('09:10, start not known yet → accepted', a.res.status === 101);
  await tick(hub);
  const off = a.sock.sent.find(m => m.t === 'off');
  ok("first poll learns start 10:00 → 'closed' until 10:00 today, no holiday latch", !!off && off.reason === 'closed' && off.retryAt === K('2026-11-19T10:00:00') && !hub.g.closedUntil, off ? new Date(off.retryAt + 9 * 3600e3).toISOString().slice(11, 16) + ' KST' : '');
  const b = await connect(hub);
  ok("09:15 connect → refused 'closed' with retryAt 10:00", b.res.status === 503 && b.body.reason === 'closed' && b.body.retryAt === K('2026-11-19T10:00:00'));
  NOW = K('2026-11-19T10:02:00');                                  // open; indices still CLOSE and yesterday's trades for a minute
  const c = await connect(hub);
  await tick(hub);
  ok('10:02 (before start + 5 min): never a holiday, streaming', c.res.status === 101 && c.sock.sent.some(m => m.t === 'snap') && !c.sock.sent.some(m => m.t === 'off'));
  NOW = K('2026-11-19T10:06:00'); await tick(hub);
  const off2 = c.sock.sent.find(m => m.t === 'off');
  ok('10:06 still CLOSE + no trade today → latched for 30 minutes only', !!off2 && off2.reason === 'closed' && hub.g.closedUntil === NOW + HOLIDAY_LATCH_MS && off2.retryAt === hub.g.closedUntil);
  NOW += HOLIDAY_LATCH_MS + 1000; SRC.status = 'OPEN'; SRC.asOfDay = '2026-11-19';
  const d = await connect(hub);
  await tick(hub);
  ok('after 30 minutes the hub re-checks and streams again', d.res.status === 101 && hub.closedUntil(NOW) === null && !d.sock.sent.some(m => m.t === 'off'));
  NOW = K('2026-11-19T16:20:00'); await tick(hub);
  ok('a 16:30 day stays open at 16:20', hub.closedUntil(NOW) === null);
}
{
  NOW = K('2026-11-17T09:06:00');                                  // an ordinary Tuesday that turns out to be a holiday
  SRC = { startTime: '0900', endTime: '1530', status: 'CLOSE', asOfDay: '2026-11-16', priced: 600, bump: 0, wait: null };
  const { hub } = await newHub();
  const a = await connect(hub);
  await tick(hub);
  const off = a.sock.sent.find(m => m.t === 'off');
  ok('holiday at 09:06 → latched 30 minutes (not the whole day)', !!off && hub.g.closedUntil === NOW + HOLIDAY_LATCH_MS);
  SRC.status = 'OPEN';
}

console.log('test-only overrides cannot loosen anything (nit)');
{
  const { hub } = await newHub({ LIVE_LIMITS: JSON.stringify({ maxSockets: 500, dayDoReq: 1e9, dayConnects: 3 }) });
  ok('LIVE_LIMITS: larger numbers are clamped to the defaults, smaller ones taken', hub.lim.maxSockets === LIMITS.maxSockets && hub.lim.dayDoReq === LIMITS.dayDoReq && hub.lim.dayConnects === 3);
  const { hub: h2 } = await newHub({ LIVE_LIMITS: 'not json' });
  ok('LIVE_LIMITS garbage → defaults', h2.lim === LIMITS || JSON.stringify(h2.lim) === JSON.stringify(LIMITS));
  NOW = K('2026-11-14T03:00:00');                                  // Saturday
  SRC = { startTime: '0900', endTime: '1530', status: 'OPEN', asOfDay: '2026-11-14', priced: 600, bump: 0, wait: null };
  const { hub: h3 } = await newHub({ LIVE_DEV_OPEN: '1' });
  const prod = await connect(h3, req());
  ok('LIVE_DEV_OPEN through a public host on Saturday → still closed', prod.res.status === 503 && prod.body.reason === 'closed');
  const local = await connect(h3, reqLocal());
  ok('LIVE_DEV_OPEN through 127.0.0.1 → open (tests)', local.res.status === 101);
  // Worker side: LIVE_ORIGINS only for local hosts
  let hubCalls = 0;
  const env = { LIVE_ORIGINS: 'https://evil.example', MARKET: { idFromName: () => 'id', get: () => ({ fetch: async () => { hubCalls++; return new Response(JSON.stringify({ reason: 'full', retryAt: NOW + 300e3 }), { status: 503 }); } }) } };
  const ctx = { waitUntil() { } };
  const mk = host => new Request(`https://${host}/api/live`, { headers: { upgrade: 'websocket', origin: 'https://evil.example' } });
  NOW = K('2026-11-16T10:00:00');
  const r1 = await liveRoute(mk('panse.pages.dev'), env, ctx, new URL(`https://panse.pages.dev/api/live`));
  ok('LIVE_ORIGINS ignored on the public host → 403', r1.status === 403 && hubCalls === 0);
  const r2 = await liveRoute(mk('127.0.0.1'), env, ctx, new URL(`http://127.0.0.1:8911/api/live`));
  ok('LIVE_ORIGINS honoured on 127.0.0.1 (reaches the hub)', r2.status === 101 && hubCalls === 1);
}

console.log('kill switch is remembered in the refusal gate (nit)');
{
  const cache = new Map();
  globalThis.caches = { default: {
    async match(r) { const e = cache.get(r.url); return e ? new R(e.body, { headers: e.headers }) : undefined; },
    async put(r, res) { cache.set(r.url, { body: await res.text(), headers: Object.fromEntries(res.headers) }); },
  } };
  let kvReads = 0, hubCalls = 0;
  const env = { REPLAY: { get: async () => { kvReads++; return '1'; } }, MARKET: { idFromName: () => 'id', get: () => ({ fetch: async () => { hubCalls++; return new Response('x', { status: 500 }); } }) } };
  const waits = []; const ctx = { waitUntil(p) { waits.push(p); } };
  const mk = () => new Request('https://panse.pages.dev/api/live', { headers: { upgrade: 'websocket', origin: 'https://panse.pages.dev' } });
  NOW = K('2026-11-16T10:00:00');
  const a = await liveRoute(mk(), env, ctx, new URL('https://panse.pages.dev/api/live')); await Promise.all(waits);
  const stored = [...cache.values()].map(e => JSON.parse(e.body))[0];
  ok("first connect: KV says off → 'paused', stored in the gate for 60 s", a.status === 101 && kvReads === 1 && hubCalls === 0 && stored && stored.reason === 'paused' && stored.retryAt === NOW + 60e3 && /max-age=60/.test([...cache.values()][0].headers['cache-control']));
  NOW += 10e3;
  await liveRoute(mk(), env, ctx, new URL('https://panse.pages.dev/api/live'));
  ok('second connect within 60 s: answered from the gate, no KV read', kvReads === 1 && hubCalls === 0);
  NOW += 60e3;
  await liveRoute(mk(), env, ctx, new URL('https://panse.pages.dev/api/live'));
  ok('after 60 s: KV read again', kvReads === 2);
  delete globalThis.caches;
}

console.log('/api/live/state is cached 10 minutes outside the session (nit)');
{
  const { hub } = await newHub();
  let doCalls = 0;
  const env = { MARKET: { idFromName: () => 'id', get: () => ({ fetch: async r => { doCalls++; return hub.fetch(r); } }) } };
  const ctx = { waitUntil() { } };
  const st = () => new Request('https://panse.pages.dev/api/live/state');
  NOW = K('2026-11-14T11:00:00');                                  // Saturday
  const a = await liveRoute(st(), env, ctx, new URL('https://panse.pages.dev/api/live/state'));
  const ja = await a.json();
  ok('Saturday: session closed → max-age=600', ja.session !== 'open' && /max-age=600/.test(a.headers.get('cache-control')) && doCalls === 1, a.headers.get('cache-control'));
  NOW = K('2026-11-16T10:00:00');                                  // Monday in session
  const b = await liveRoute(st(), env, ctx, new URL('https://panse.pages.dev/api/live/state'));
  ok('Monday 10:00: open → max-age=60', /max-age=60$/.test(b.headers.get('cache-control')), b.headers.get('cache-control'));
}

Date.now = realNow;
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
