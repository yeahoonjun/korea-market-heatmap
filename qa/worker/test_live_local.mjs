// 실시간 갱신 — 로컬 workerd(`wrangler dev`) 통합 점검 (docs/standards/realtime.md §13). 서버 셋은 이 스크립트가 띄우고 끕니다:
//   ① web/ 정적 서버(ASSET_BASE, 8914)  ② 네이버 모양 흉내 서버(prototypes/realtime/upstream_mock.mjs, 8912)
//   ③ npx wrangler dev -c worker/wrangler.toml (8911, 검사기 8913, 저장소 상태는 매번 새 임시 폴더)
//
//   node qa/worker/test_live_local.mjs [--frames /path/to/replay-1min.json]
//
// 단계 open: LIVE_DEV_OPEN=1, LIVE_LIMITS {maxSockets:4, dayConnects:12} — 426/400/403, hello → 스냅숏 600행 → 델타, 이어 받기,
//            소켓 상한(5번째 'full', 6번째는 Worker 문지기가 허브를 부르지 않고 'full'), 하루 연결 상한 → 'budget'으로 모두 닫힘.
// 단계 closed: LIVE_DEV_OPEN 없음 — 주말·밤이면 Worker가 허브 없이 'closed' + 다음 개장 시각.
// The mock needs Naver once for its base rows (Node + NODE_USE_ENV_PROXY=1) and 1-minute frames (--frames FILE, or the public
// Worker's /api/replay once). Uses the `ws` package that ships with wrangler (worker/node_modules or WS_MODULES).
import { spawn, execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ROOT = new URL('../../', import.meta.url).pathname;
const MOD = process.env.WS_MODULES || (existsSync(ROOT + 'worker/node_modules/ws') ? ROOT + 'worker/node_modules/' : '/home/claude/heatmap/worker/node_modules/');
const WebSocket = createRequire(MOD)('ws');
const WRANGLER = MOD + '.bin/wrangler';
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i < 0 ? d : process.argv[i + 1]; };
const FRAMES = arg('frames', '');
const P = { web: 8914, mock: 8912, dev: 8911, insp: 8913 };
const procs = [];
let pass = 0, fail = 0;
const ok = (name, cond, extra = '') => { if (cond) { pass++; console.log('  ok  ', name, extra); } else { fail++; console.log('  FAIL', name, extra); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function start(cmd, args, env, tag) {
  const p = spawn(cmd, args, { env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
  let log = '';
  p.stdout.on('data', d => { log += d; }); p.stderr.on('data', d => { log += d; });
  procs.push(p);
  return { p, log: () => log, tag };
}
async function waitFor(url, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { const r = await fetch(url); if (r.status < 500) return true; } catch (e) { /* not yet */ } await sleep(500); }
  return false;
}
function stopAll() { for (const p of procs) { try { process.kill(-p.pid, 'SIGTERM'); } catch (e) { } } procs.length = 0; }
process.on('exit', stopAll);
process.on('SIGINT', () => { stopAll(); process.exit(130); });

// one WebSocket: collects messages; resolves `opened` on open or on an HTTP refusal
function sock(url, origin = `http://127.0.0.1:${P.dev}`) {
  const s = { msgs: [], close: null, status: null };
  const ws = new WebSocket(url, { origin });
  s.ws = ws;
  s.opened = new Promise(res => {
    ws.on('open', () => res(true));
    ws.on('unexpected-response', (req, r) => { s.status = r.statusCode; res(false); });
    ws.on('error', () => res(false));
  });
  ws.on('message', b => { try { s.msgs.push(JSON.parse(b.toString())); } catch (e) { } });
  ws.on('close', (code, reason) => { s.close = { code, reason: reason.toString() }; });
  s.next = async (pred, ms = 15000) => { const end = Date.now() + ms; while (Date.now() < end) { const m = s.msgs.find(pred); if (m) return m; await sleep(50); } return null; };
  return s;
}
const live = (host = '127.0.0.1', q = '') => `ws://${host}:${P.dev}/api/live${q}`;
const state = async () => (await fetch(`http://127.0.0.1:${P.dev}/api/live/state`)).json();

async function devServer(vars) {
  const persist = mkdtempSync(join(tmpdir(), 'live-state-'));
  const args = ['dev', '-c', ROOT + 'worker/wrangler.toml', '--port', String(P.dev), '--ip', '127.0.0.1', '--inspector-port', String(P.insp), '--persist-to', persist, '--show-interactive-dev-session=false'];
  for (const [k, v] of Object.entries(vars)) args.push('--var', `${k}:${v}`);
  const d = start(WRANGLER, args, {}, 'wrangler');
  const up = await waitFor(`http://127.0.0.1:${P.dev}/api/health`, 90000);
  if (!up) { console.log(d.log().slice(-3000)); throw new Error('wrangler dev did not come up'); }
  return d;
}

try { execSync(`fuser -k ${P.web}/tcp ${P.mock}/tcp ${P.dev}/tcp ${P.insp}/tcp`, { stdio: 'ignore' }); } catch (e) { }
start('python3', ['-m', 'http.server', String(P.web), '--bind', '127.0.0.1', '-d', ROOT + 'web'], {}, 'web');
const mockArgs = [ROOT + 'prototypes/realtime/upstream_mock.mjs', '--port', String(P.mock), '--churn', '0.3'];
if (FRAMES) mockArgs.push('--frames', FRAMES);
const mock = start('node', mockArgs, { NODE_USE_ENV_PROXY: '1' }, 'mock');
if (!(await waitFor(`http://127.0.0.1:${P.web}/universe.json`)) || !(await waitFor(`http://127.0.0.1:${P.mock}/__stats`))) { console.log(mock.log()); throw new Error('helpers did not start'); }
for (let i = 0; i < 60 && !/upstream mock on/.test(mock.log()); i++) await sleep(500);   // base rows + frames loaded

const common = { NAVER_POLL_BASE: `http://127.0.0.1:${P.mock}`, ASSET_BASE: `http://127.0.0.1:${P.web}/`, LIVE_ORIGINS: `http://127.0.0.1:${P.dev},http://localhost:${P.dev}` };

/* ── phase open ── */
console.log('phase open (LIVE_DEV_OPEN=1, maxSockets 4, dayConnects 12)');
let dev = await devServer({ ...common, LIVE_DEV_OPEN: '1', LIVE_LIMITS: JSON.stringify({ maxSockets: 4, dayConnects: 12 }) });
{
  const r1 = await fetch(`http://127.0.0.1:${P.dev}/api/live`);
  ok('no Upgrade → 426', r1.status === 426);
  const r2 = await fetch(`http://127.0.0.1:${P.dev}/api/live?ch=all`);
  ok('ch=all → 400 (one hub only)', r2.status === 400);
  const bad = sock(live(), 'https://evil.example');
  await bad.opened;
  ok('foreign Origin → 403', bad.status === 403);

  const A = sock(live());
  ok('connects', await A.opened);
  const hello = await A.next(m => m.t === 'hello');
  ok('hello', !!hello && hello.proto === 1 && hello.poll === 3000, hello ? `epoch ${hello.epoch}` : '');
  const snap = await A.next(m => m.t === 'snap', 20000);
  const b = snap && snap.body;
  ok('snapshot = /api/quotes shape, 600 rows', !!b && Array.isArray(b.stocks) && b.stocks.length === 600 && !!b.index && b.stocks.every(r => r.c && r.n && r.m && r.s && r.i && r.p > 0), b ? `${b.stocks.length} rows, ${JSON.stringify(snap).length} chars` : '');
  const d1 = await A.next(m => m.t === 'd', 15000);
  ok('deltas arrive', !!d1 && d1.b === snap.v && d1.v === snap.v + 1, d1 ? `${d1.rows.length} rows changed` : '');
  // resume
  const v = Math.max(...A.msgs.filter(m => m.t === 'd' || m.t === 'snap').map(m => m.v));
  A.ws.close(); await sleep(3500);
  const R = sock(live('127.0.0.1', `?epoch=${hello.epoch}&ver=${v}`));
  await R.opened;
  const rd = await R.next(m => m.t === 'd', 10000);
  ok('resume: missed deltas, no snapshot', !!rd && !R.msgs.some(m => m.t === 'snap') && rd.b === v, rd ? `from v${v}` : '');
  // socket cap
  const more = [sock(live()), sock(live()), sock(live())];
  await Promise.all(more.map(s => s.opened)); await Promise.all(more.map(s => s.next(m => m.t === 'hello', 5000)));
  const s1 = await state();
  ok('4 sockets on the hub', s1.sockets === 4, `sockets ${s1.sockets}`);
  const F = sock(live());
  await F.opened;
  const off = await F.next(m => m.t === 'off', 5000);
  for (let i = 0; i < 50 && !F.close; i++) await sleep(100);
  ok("5th page: {t:'off', reason:'full'} + close 4003", !!off && off.reason === 'full' && F.close && F.close.code === 4003, off ? `retry ${new Date(off.retryAt).toISOString()}` : '');
  const ref1 = (await state()).refused;
  const F2 = sock(live()); await F2.opened; const off2 = await F2.next(m => m.t === 'off', 5000);
  const ref2 = (await state()).refused;
  ok("6th page: 'full' from the Worker's gate — no Durable Object request", !!off2 && off2.reason === 'full' && ref2 === ref1, `hub refusals ${ref1} → ${ref2}`);
  // daily connection cap → budget trip (a different host = a different gate key, so the 'full' memory above does not answer)
  for (const s of [R, ...more]) s.ws.close();
  await sleep(1500);
  let tripped = null, n = 0;
  const keep = sock(live('localhost'), `http://localhost:${P.dev}`);
  await keep.opened; await keep.next(m => m.t === 'hello', 5000);
  for (; n < 20 && !tripped; n++) {
    const s = sock(live('localhost'), `http://localhost:${P.dev}`);
    await s.opened;
    const m = await s.next(x => x.t === 'hello' || x.t === 'off', 5000);
    if (m && m.t === 'off') tripped = m; else s.ws.close();
    await sleep(150);
  }
  ok("daily connection cap: new page gets {t:'off', reason:'budget'}", !!tripped && tripped.reason === 'budget', tripped ? `after ${n} more connects, retry ${new Date(tripped.retryAt).toISOString()}` : '');
  const kOff = await keep.next(m => m.t === 'off', 5000);
  for (let i = 0; i < 50 && !keep.close; i++) await sleep(100);
  // the hub closes with 4003; under `wrangler dev` the client sees the close frame (readyState CLOSING) but the local proxy keeps
  // the TCP connection, so the 'close' event may not fire — the page must treat {t:'off'} itself as the end (realtime.md §7-3)
  ok("pages already connected are told 'budget' and the hub closes them", !!kOff && kOff.reason === 'budget' && (keep.close ? keep.close.code === 4003 : keep.ws.readyState >= 2), `readyState ${keep.ws.readyState}, close ${JSON.stringify(keep.close)}`);
  const s2 = await state();
  ok('state: trip recorded, polling stopped (no alarm), 0 sockets', s2.guard.trip && s2.guard.trip.why === 'dayConnects' && s2.sockets === 0, JSON.stringify(s2.guard.trip));
  console.log('       guard', JSON.stringify(s2.guard));
}
stopAll(); await sleep(1500);
for (const p of [P.dev, P.insp]) { try { execSync(`fuser -k ${p}/tcp`, { stdio: 'ignore' }); } catch (e) { } }

/* ── phase closed (real clock) ── */
console.log('phase closed (real KST clock)');
start('python3', ['-m', 'http.server', String(P.web), '--bind', '127.0.0.1', '-d', ROOT + 'web'], {}, 'web');
dev = await devServer(common);
{
  const now = Date.now(), k = new Date(now + 9 * 3600e3), wd = k.getUTCDay(), hm = k.getUTCHours() * 100 + k.getUTCMinutes();
  const inSession = wd >= 1 && wd <= 5 && hm >= 900 && hm < 1632;
  const C = sock(live());
  await C.opened;
  const m = await C.next(x => x.t === 'off' || x.t === 'hello', 8000);
  if (inSession) ok('(in session now — closed check skipped)', true);
  else ok("outside the session: {t:'off', reason:'closed'} with the next opening", !!m && m.t === 'off' && m.reason === 'closed' && new Date(m.retryAt + 9 * 3600e3).getUTCHours() === 9, m && m.retryAt ? `retry ${new Date(m.retryAt + 9 * 3600e3).toISOString().slice(0, 16)} KST` : '');
  const st = await state();
  ok('state route answers without starting the hub', st.sockets === 0 && st.polls === 0, `doRequests today ${st.guard.doRequests.today}`);
}
stopAll();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
