// Usage: NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8791/ node worker/dev/serve.mjs   (PORT default 8790)
// Dev-only extras (never part of the Worker):
//   GET /__dev/scheduled?at=2026-11-10T10:05[&open=1]  fires worker.scheduled() with a fake clock (KST wall time unless a zone is given).
//                                                       open=1 makes the index call report OPEN so the holiday guard lets the frame through.
//   GET /__dev/kv[?prefix=replay:]                     lists the in-memory KV (key + byte size)
//   GET /__dev/count?reset=1                           upstream fetch counter since the last reset (per hostname+path)
import http from 'node:http';
import worker from '../src/index.js';

// minimal caches.default: Map keyed by URL, honours max-age
const store = new Map();
globalThis.caches = {
  default: {
    async match(req) {
      const e = store.get(req.url);
      if (!e) return undefined;
      if (Date.now() > e.exp) { store.delete(req.url); return undefined; }
      return e.res.clone();
    },
    async put(req, res) {
      const m = /max-age=(\d+)/.exec(res.headers.get('cache-control') || '');
      if (m) store.set(req.url, { exp: Date.now() + m[1] * 1000, res: res.clone() });
    },
  },
};

// in-memory KV mock (get / put / list / delete), same surface the Worker uses
let kvStats = { ops: 0, parsedBytes: 0, putBytes: 0 };
function makeKV() {
  const m = new Map();                       // key → { value: string, exp: ms|null }
  const live = () => { const now = Date.now(); for (const [k, v] of m) if (v.exp && v.exp < now) m.delete(k); };
  return {
    _m: m,
    async get(key, opt) {
      live(); kvStats.ops++;
      const e = m.get(key);
      if (!e) return null;
      kvStats.parsedBytes += e.value.length;
      const type = typeof opt === 'string' ? opt : opt && opt.type;
      return type === 'json' ? JSON.parse(e.value) : e.value;
    },
    async put(key, value, opt) {
      kvStats.ops++; kvStats.putBytes += String(value).length;
      m.set(key, { value: String(value), exp: opt && opt.expirationTtl ? Date.now() + opt.expirationTtl * 1000 : null });
    },
    async delete(key) { m.delete(key); },
    async list(opt = {}) {
      live(); kvStats.ops++;
      const names = [...m.keys()].filter(k => k.startsWith(opt.prefix || '')).sort();
      const start = opt.cursor ? names.findIndex(n => n > opt.cursor) : 0;
      const limit = opt.limit || 1000;
      const slice = start < 0 ? [] : names.slice(start, start + limit);
      const complete = start < 0 || start + limit >= names.length;
      return { keys: slice.map(name => ({ name })), list_complete: complete, cursor: complete ? undefined : slice[slice.length - 1] };
    },
  };
}

// upstream fetch counter (+ optional forced-OPEN index for scheduled tests)
const realFetch = globalThis.fetch;
let counts = {}, forceOpen = false;
globalThis.fetch = async (input, init) => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  const key = u.host + u.pathname.replace(/\/[0-9A-Z]{6}(,[0-9A-Z]{6})+$/, '/{codes}');
  counts[key] = (counts[key] || 0) + 1;
  const r = await realFetch(input, init);
  if (forceOpen && u.pathname.includes('/realtime/domestic/index/')) {
    const j = await r.json();
    for (const x of j.datas || []) x.marketStatus = 'OPEN';
    return new Response(JSON.stringify(j), { status: r.status, headers: { 'content-type': 'application/json' } });
  }
  return r;
};

const PORT = Number(process.env.PORT) || 8790;
const env = { ASSET_BASE: process.env.ASSET_BASE, REPLAY: makeKV() };
http.createServer(async (req, res) => {
  try {
    const u = new URL('http://127.0.0.1:' + PORT + req.url);
    const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (u.pathname === '/__dev/scheduled') {
      const at = u.searchParams.get('at') || '';
      const ms = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(at) ? at : at + '+09:00');
      if (!Number.isFinite(ms)) return send(400, { error: 'at=YYYY-MM-DDTHH:mm (KST) required' });
      forceOpen = u.searchParams.get('open') === '1';
      counts = {}; kvStats = { ops: 0, parsedBytes: 0, putBytes: 0 };
      try {
        const pending = [];
        await worker.scheduled({ scheduledTime: ms, cron: '*/5 0-6 * * 1-5', type: 'scheduled' }, env, { waitUntil: p => pending.push(p) });
        await Promise.all(pending);
      } finally { forceOpen = false; }
      return send(200, { fired: new Date(ms).toISOString(), upstream: Object.keys(counts).length ? Object.values(counts).reduce((a, b) => a + b, 0) : 0, kv: kvStats, kvKeys: [...env.REPLAY._m.keys()] });
    }
    if (u.pathname === '/__dev/kv') {
      const out = [...env.REPLAY._m].filter(([k]) => k.startsWith(u.searchParams.get('prefix') || '')).map(([k, v]) => ({ key: k, bytes: v.value.length }));
      return send(200, out);
    }
    if (u.pathname === '/__dev/kvstats') { const c = kvStats; if (u.searchParams.get('reset')) kvStats = { ops: 0, parsedBytes: 0, putBytes: 0 }; return send(200, c); }
    if (u.pathname === '/__dev/count') {
      const c = counts;
      if (u.searchParams.get('reset')) counts = {};
      return send(200, c);
    }
    const r = await worker.fetch(new Request(u.toString()), env, { waitUntil() {} });
    res.writeHead(r.status, Object.fromEntries(r.headers));
    res.end(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    res.writeHead(500, { 'content-type': 'text/plain' });
    res.end(String(e && e.stack || e));
  }
}).listen(PORT, () => console.log('worker dev on http://127.0.0.1:' + PORT));
