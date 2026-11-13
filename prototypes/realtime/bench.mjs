// Bench for the 실시간 갱신 prototype (docs/standards/realtime.md §8): N WebSocket clients against `wrangler dev`,
// message sizes (JSON chars, standalone deflate, real wire bytes with permessage-deflate), lag, resume.
//
//   node prototypes/realtime/bench.mjs [--url ws://127.0.0.1:8911/api/live?ch=top] [--n 20] [--secs 60] [--resume]
//
// Uses the `ws` package that ships with wrangler/miniflare (worker/node_modules) — nothing extra to install.
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import zlib from 'node:zlib';

// worker/node_modules of this checkout (after `npm ci --prefix worker`), or WS_MODULES=/path/to/node_modules/
const REPO_MODULES = new URL('../../worker/node_modules/', import.meta.url).pathname;
const MODULES = process.env.WS_MODULES || (existsSync(REPO_MODULES + 'ws') ? REPO_MODULES : '/home/claude/heatmap/worker/node_modules/');
const WebSocket = createRequire(MODULES)('ws');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const URL0 = arg('url', 'ws://127.0.0.1:8911/api/live?ch=top');
const N = +arg('n', 20), SECS = +arg('secs', 60), RESUME = arg('resume', false) === true;
const ORIGIN = arg('origin', 'http://127.0.0.1:8911');

const pct = (a, p) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p / 100 * s.length))]; };
const med = a => pct(a, 50);
const clients = [];

function open(i, url) {
  return new Promise(resolve => {
    const c = clients[i] || (clients[i] = { i, msgs: 0, chars: 0, wireStart: 0, wire: 0, types: {}, deltas: [], deltaRows: [], deflate: [], lag: [], snap: null, ext: '', epoch: null, v: 0, resumed: null });
    const ws = new WebSocket(url, { origin: ORIGIN, perMessageDeflate: true });
    c.ws = ws;
    ws.on('open', () => { c.ext = ws.extensions || ''; c.wireStart = ws._socket.bytesRead; resolve(); });
    ws.on('message', (buf) => {
      const text = buf.toString('utf8');
      const m = JSON.parse(text);
      c.msgs++; c.chars += text.length; c.types[m.t] = (c.types[m.t] || 0) + 1;
      if (m.t === 'snap') { c.epoch = m.epoch; c.v = m.v; c.snap = { chars: text.length, deflate: zlib.deflateRawSync(text).length, gzipBody: zlib.gzipSync(JSON.stringify(m.body)).length, rows: m.body.stocks.length }; if (c.resumeAt) c.resumed = 'snapshot'; }
      if (m.t === 'd') {
        if (c.resumeAt && c.resumed == null) c.resumed = 'deltas';
        if (m.b !== c.v && c.v) c.gap = (c.gap || 0) + 1;
        c.v = m.v; c.deltas.push(text.length); c.deltaRows.push(m.rows.length); c.deflate.push(zlib.deflateRawSync(text).length); c.lag.push(Date.now() - m.at);
      }
    });
    ws.on('close', () => { c.wire += ws._socket ? ws._socket.bytesRead - c.wireStart : 0; });
    ws.on('error', e => { c.err = String(e.message || e); resolve(); });
  });
}

const t0 = Date.now();
await Promise.all(Array.from({ length: N }, (_, i) => open(i, URL0)));
console.log(`${N} clients connected in ${Date.now() - t0} ms, extension: "${clients[0].ext}"`);
if (RESUME) {
  setTimeout(() => { const c = clients[0]; c.ws.close(1000, 'bench'); c.resumeAt = Date.now(); console.log(`client 0 closed at v${c.v}`); }, Math.min(20, SECS / 3) * 1000);
  setTimeout(async () => { const c = clients[0]; const u = new URL(URL0); u.searchParams.set('epoch', c.epoch); u.searchParams.set('ver', c.v); await open(0, u.toString()); console.log(`client 0 resumed from v${c.v}`); }, (Math.min(20, SECS / 3) + 6) * 1000);
}
await new Promise(r => setTimeout(r, SECS * 1000));
for (const c of clients) { c.wire += c.ws._socket ? c.ws._socket.bytesRead - c.wireStart : 0; c.wireStart = c.ws._socket ? c.ws._socket.bytesRead : 0; c.ws.terminate(); }
await new Promise(r => setTimeout(r, 300));

const all = clients.filter(c => !c.err);
const d = all.flatMap(c => c.deltas), dr = all.flatMap(c => c.deltaRows), df = all.flatMap(c => c.deflate), lag = all.flatMap(c => c.lag);
const c0 = all[1] || all[0];
const out = {
  clients: all.length, errors: clients.filter(c => c.err).map(c => c.err).slice(0, 3), secs: SECS, extension: c0.ext,
  snapshot: c0.snap,
  perClient: { msgs: c0.msgs, types: c0.types, jsonChars: c0.chars, wireBytes: c0.wire, wirePerMin: Math.round(c0.wire / (SECS / 60)) },
  delta: { count: c0.deltas.length, rowsMedian: med(dr), rowsP95: pct(dr, 95), charsMedian: med(d), charsP95: pct(d, 95), deflateMedian: med(df), deflateP95: pct(df, 95) },
  lagMs: { median: med(lag), p95: pct(lag, 95) },
  gaps: all.reduce((s, c) => s + (c.gap || 0), 0),
  resume: RESUME ? clients[0].resumed : undefined,
};
console.log(JSON.stringify(out, null, 1));
