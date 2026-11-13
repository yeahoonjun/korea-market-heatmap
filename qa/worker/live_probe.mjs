// 실시간 허브 한 번 들여다보기 (docs/standards/realtime.md §13): WebSocket 하나로 N초 동안 받은 것을 요약하고 /api/live/state를 보여 줘요.
//   node qa/worker/live_probe.mjs [https://panse.pages.dev] [--secs 20]
// 장 밖이면 {t:'off', reason:'closed', retryAt}만 와요 — 그것만으로도 Pages 서비스 바인딩을 지나 업그레이드가 통과한다는 확인이에요.
// 페이지 하나와 같은 무게(연결 1번 = Worker 요청 1 + DO 요청 1, 장 밖이면 DO 요청 0).
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url).pathname;
const MOD = process.env.WS_MODULES || (existsSync(ROOT + 'worker/node_modules/ws') ? ROOT + 'worker/node_modules/' : '/home/claude/heatmap/worker/node_modules/');
const WebSocket = createRequire(MOD)('ws');
const base = (process.argv.slice(2).find(a => /^https?:\/\//.test(a)) || 'https://panse.pages.dev').replace(/\/+$/, '');
const i = process.argv.indexOf('--secs'), secs = i > 0 ? +process.argv[i + 1] : 20;
const wsUrl = base.replace(/^http/, 'ws') + '/api/live';
const kst = ms => new Date(ms + 9 * 3600e3).toISOString().slice(0, 19).replace('T', ' ') + ' KST';

const sum = { opened: false, status: null, extensions: '', hello: null, snapRows: null, snapChars: 0, deltas: 0, deltaRows: [], hb: 0, off: null, st: 0, lag: [], close: null };
const ws = new WebSocket(wsUrl, { origin: 'https://panse.pages.dev' });
ws.on('open', () => { sum.opened = true; sum.extensions = ws.extensions; });
ws.on('unexpected-response', (q, r) => { sum.status = r.statusCode; });
ws.on('error', e => { sum.error = e.message; });
ws.on('close', (code, reason) => { sum.close = { code, reason: reason.toString() }; });
ws.on('message', b => {
  const m = JSON.parse(b.toString());
  if (m.t === 'hello') sum.hello = { epoch: m.epoch, v: m.v, poll: m.poll };
  else if (m.t === 'snap') { sum.snapRows = m.body.stocks.length; sum.snapChars = b.length; sum.asOf = m.body.asOf; }
  else if (m.t === 'd') { sum.deltas++; sum.deltaRows.push(m.rows.length); sum.lag.push(Date.now() - m.at); sum.asOf = m.asOf; }
  else if (m.t === 'hb') sum.hb++;
  else if (m.t === 'st') sum.st++;
  else if (m.t === 'off') { sum.off = { reason: m.reason, retryAt: m.retryAt && kst(m.retryAt) }; ws.close(); }   // the page ends here too
});
await new Promise(r => setTimeout(r, secs * 1000));
try { ws.close(); } catch (e) { }
const med = a => a.length ? [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)] : null;
console.log(JSON.stringify({ url: wsUrl, ...sum, deltaRows: undefined, deltaRowsMedian: med(sum.deltaRows), lagMsMedian: med(sum.lag), lag: undefined }, null, 1));
try {
  const r = await fetch(base + '/api/live/state');
  const s = await r.json();
  console.log('state', r.status, JSON.stringify({ session: s.session, sockets: s.sockets, polls: s.polls, fails: s.fails, lastErr: s.lastErr, killSwitch: s.killSwitch, guard: s.guard }, null, 1));
} catch (e) { console.log('state: ' + e.message); }
process.exit(0);
