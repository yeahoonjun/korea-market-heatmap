// Shared fakes for the 공공데이터포털 Worker tests (qa/datago/*.mjs): a fake clock, Workers-KV-like store with TTLs on that
// clock, caches.default, a fetch router for apis.data.go.kr, a console spy and a key-leak scanner. No network, no real key.
import assert from 'node:assert/strict';

export const KST = s => Date.parse(s + '+09:00');
export const clock = { t: KST('2026-11-16T14:00:00') };          // Monday
const realNow = Date.now;
Date.now = () => clock.t;
export const at = s => { clock.t = KST(s); };
export const advance = ms => { clock.t += ms; };

/* ── KV ── */
export function makeKV() {
  const m = new Map();
  const log = { gets: 0, puts: [] };
  const read = (k, type) => {
    const e = m.get(k);
    if (!e || (e.exp && e.exp <= clock.t)) return null;
    return type === 'json' ? JSON.parse(e.value) : e.value;
  };
  return {
    m, log,
    async get(key, type) { log.gets++; return read(key, type); },
    async put(key, value, opt) {
      assert.ok(!opt || !opt.expirationTtl || opt.expirationTtl >= 60, 'KV expirationTtl must be ≥ 60 s: ' + key);
      log.puts.push({ key, ttl: opt && opt.expirationTtl });
      m.set(key, { value: String(value), exp: opt && opt.expirationTtl ? clock.t + opt.expirationTtl * 1000 : null });
    },
    json(k) { return read(k, 'json'); },
    ttl(k) { const e = m.get(k); return e && e.exp ? Math.round((e.exp - clock.t) / 1000) : null; },
  };
}

/* ── caches.default (per test switchable) ── */
export const edge = { on: false, store: new Map(), puts: [] };
globalThis.caches = {
  default: {
    async match(req) {
      if (!edge.on) return undefined;
      const e = edge.store.get(req.url);
      return e && e.exp > clock.t ? e.res.clone() : undefined;
    },
    async put(req, res) {
      const m = /max-age=(\d+)/.exec(res.headers.get('cache-control') || '');
      edge.puts.push({ url: req.url, ttl: m ? +m[1] : 0 });
      if (edge.on && m) edge.store.set(req.url, { exp: clock.t + m[1] * 1000, res: res.clone() });
    },
  },
};

/* ── fetch router: handler(op, params, url, init) → {status?, body, ctype?} | Response | throws ── */
export const net = { calls: [], handler: null };
export const KEYS = {
  raw: 'Ab+cD/eF==QAKeyNotARealSecret0123456789xyz',       // "Decoding" spelling (base64: + / =)
  hex: '9f2c4e6a8b0d1f3e5a7c9b1d3f5e7a9c0b2d4f6e8a1c3e5b7d9f1a3c5e7b9d1f',
};
KEYS.enc = encodeURIComponent(KEYS.raw);                     // "Encoding" spelling (%2B %2F %3D)
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  const u = new URL(url);
  if (u.origin !== 'https://apis.data.go.kr') throw new Error('unexpected fetch ' + u.origin + u.pathname);
  const op = u.pathname.split('/').pop();
  const params = Object.fromEntries(u.searchParams);
  net.calls.push({ path: u.pathname, op, params, url, init });
  assert.ok(init.signal instanceof AbortSignal, 'every upstream call has a time limit');
  assert.match(init.headers['user-agent'], /panse/, 'honest UA');
  if (!net.handler) throw new Error('no handler for ' + u.pathname);
  const r = await net.handler(op, params, url, init);
  if (r instanceof Response) return r;
  const body = typeof r.body === 'string' ? r.body : JSON.stringify(r.body);
  return new Response(body, { status: r.status || 200, headers: { 'content-type': r.ctype || 'application/json;charset=UTF-8' } });
};
// the provider's JSON envelope
export const ok = (items, totalCount = items.length, extra = {}) => ({
  body: { response: { header: { resultCode: '00', resultMsg: 'NORMAL SERVICE.' }, body: { numOfRows: extra.numOfRows || items.length, pageNo: extra.pageNo || 1, totalCount, items: items.length === 0 ? '' : { item: items.length === 1 && extra.single ? items[0] : items } } } },
});
export const rc = (code, msg) => ({ body: { response: { header: { resultCode: code, resultMsg: msg } } } });
export const portalXml = (code, msg, status = 200) => ({ status, ctype: 'text/xml;charset=UTF-8',
  body: `<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>${msg}</returnAuthMsg><returnReasonCode>${code}</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>` });
export const gateway = (status, text) => ({ status, ctype: 'text/plain', body: text });
// page a list like the portal does
export function paged(all, params) {
  const n = +params.numOfRows || 10, p = +params.pageNo || 1;
  return ok(all.slice((p - 1) * n, p * n), all.length, { numOfRows: n, pageNo: p });
}

/* ── console spy ── */
export const logs = [];
for (const k of ['log', 'info', 'warn', 'error', 'debug']) {
  const orig = console[k].bind(console);
  console[k] = (...a) => { logs.push(a.map(x => (x instanceof Error ? x.stack || x.message : typeof x === 'string' ? x : JSON.stringify(x))).join(' ')); if (k === 'log' && process.env.DG_VERBOSE) orig(...a); };
  console['__' + k] = orig;
}
export const say = (...a) => console.__log(...a);

/* ── key leaks ── */
export function keyForms(...keys) {
  const out = new Set();
  for (const k of keys) { if (!k) continue; out.add(k); out.add(encodeURIComponent(k)); out.add(encodeURIComponent(k).toLowerCase()); try { out.add(decodeURIComponent(k)); } catch (e) { /* not encoded */ } }
  return [...out].filter(x => x.length >= 6);
}
export function assertNoKey(text, where, keys = [KEYS.raw, KEYS.enc, KEYS.hex]) {
  const s = String(text);
  for (const f of keyForms(...keys)) assert.ok(!s.includes(f), `key leaked into ${where}`);
}
export function scanKV(kv, where = 'KV') {
  for (const [k, v] of kv.m) { assertNoKey(k, where + ' key'); assertNoKey(v.value, where + ' value ' + k); }
}
export function scanLogs() { for (const l of logs) assertNoKey(l, 'console'); }

/* ── a tiny runner ── */
export function runner(title) {
  const results = [];
  return {
    async test(name, fn) {
      try { await fn(); results.push(['PASS', name]); } catch (e) { results.push(['FAIL', name, e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : String(e)]); }
    },
    done() {
      for (const [s, n, e] of results) say(`${s} ${n}${e ? '\n     ' + e : ''}`);
      const f = results.filter(r => r[0] === 'FAIL').length;
      say(`\n${title}: ${results.length - f}/${results.length} passed`);
      Date.now = realNow;
      process.exit(f ? 1 : 0);
    },
  };
}
export function ctxOf() {
  const pending = [];
  return { waitUntil: p => pending.push(p), async flush() { while (pending.length) await pending.shift(); } };
}
