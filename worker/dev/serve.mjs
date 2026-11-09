// Usage: NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8791/ node worker/dev/serve.mjs   (PORT default 8790)
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

const PORT = Number(process.env.PORT) || 8790;
const env = { ASSET_BASE: process.env.ASSET_BASE };
http.createServer(async (req, res) => {
  try {
    const r = await worker.fetch(new Request('http://127.0.0.1:' + PORT + req.url), env, { waitUntil() {} });
    res.writeHead(r.status, Object.fromEntries(r.headers));
    res.end(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    res.writeHead(500, { 'content-type': 'text/plain' });
    res.end(String(e && e.stack || e));
  }
}).listen(PORT, () => console.log('worker dev on http://127.0.0.1:' + PORT));
