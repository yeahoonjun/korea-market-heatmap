// Naver-shaped upstream for the 실시간 갱신 prototype (docs/standards/realtime.md §8). LOCAL ONLY.
// workerd (`wrangler dev`) cannot reach Naver from this sandbox, so the hub polls this server instead.
//
//   NODE_USE_ENV_PROXY=1 node prototypes/realtime/upstream_mock.mjs [--port 8912] [--date 2026-11-12] [--speed 1] [--churn 0]
//   NODE_USE_ENV_PROXY=1 node prototypes/realtime/upstream_mock.mjs --live          # pass-through to Naver (market hours)
//
// Replay mode (default): one real Naver polling answer per channel is the base (row shape, names, NXT block, cap), and
// real 1-minute frames (the replay recorder's /api/replay?step=1, read once from the public Worker or --frames FILE) drive
// the prices: a stock moves from minute m to m+1 at its own second inside the minute, so a 3 s poll sees ~1/20 of that
// minute's movers — a LOWER bound on how many rows tick. --churn f adds a one-tick bounce to f of the rows per 3 s (upper
// bound knob for the size table). Volume grows on simulated trades so the slow keys change too.
//
//   GET /__codes?ch=top|all                   → {codes, meta:{code:{m,s,i}}} from web/universe.json
//   GET /api/realtime/domestic/stock/{codes}  → Naver shape
//   GET /api/realtime/domestic/index/KOSPI,KOSDAQ
//   GET /__stats                              → request counters, sim clock
import http from 'node:http';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url).pathname;
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const PORT = +arg('port', 8912);
const LIVE = arg('live', false) === true;
const DATE = arg('date', '2026-11-12');
const SPEED = +arg('speed', 1);
const CHURN = +arg('churn', 0);
const FRAMES = arg('frames', '');
const PUBLIC = 'https://korea-market-heatmap.ssslot.workers.dev';
const NAVER = 'https://polling.finance.naver.com';
const UA = 'Mozilla/5.0 (compatible; panse-proto/1.0; +https://panse.pages.dev)';

/* ── universe ── */
const U = JSON.parse(readFileSync(ROOT + 'web/universe.json', 'utf8'));
const ind = k => U.I[parseInt(k, 36)] || ['기타', '기타'];
const meta = {}, top = [], rest = [];
for (const m of ['K', 'Q']) for (let k = 0; k + 8 <= U[m].length; k += 8) { const c = U[m].slice(k, k + 6), [i, s] = ind(U[m].slice(k + 6, k + 8)); meta[c] = { m, s, i }; top.push(c); }
for (let k = 0; k + 9 <= U.X.length; k += 9) { const c = U.X.slice(k, k + 6), [i, s] = ind(U.X.slice(k + 6, k + 8)); meta[c] = { m: U.X[k + 8], s, i }; rest.push(c); }
const CODES = { top, all: [...new Set([...top, ...rest])] };

/* ── helpers ── */
// FNV-1a + murmur3 fmix32 (without the finaliser, keys that differ only in the last digit land next to each other)
const h01 = s => {
  let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
};
const tick = p => p < 2000 ? 1 : p < 5000 ? 5 : p < 20000 ? 10 : p < 50000 ? 50 : p < 200000 ? 100 : p < 500000 ? 500 : 1000;
const r2 = x => Math.round(x * 100) / 100;
const fmt = n => Math.round(n).toLocaleString('en-US');
const dir = d => d > 0 ? { code: '2', text: '상승', name: 'RISING' } : d < 0 ? { code: '5', text: '하락', name: 'FALLING' } : { code: '3', text: '보합', name: 'UNCHANGED' };
async function getJSON(url) { const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' } }); if (!r.ok) throw new Error(`${r.status} ${url.slice(0, 90)}`); return r.json(); }

/* ── base rows + frames (replay mode) ── */
const base = new Map();               // code → real Naver row (deep-copied per answer)
async function loadBase(codes) {
  const need = codes.filter(c => !base.has(c));
  for (let i = 0; i < need.length; i += 900) {
    const j = await getJSON(`${NAVER}/api/realtime/domestic/stock/${need.slice(i, i + 900).join(',')}`);
    for (const d of j.datas || []) base.set(d.itemCode, d);
  }
}
let F = null;                         // {codes, frames:[{t,p,r}], index:{KOSPI:[…]}, base:{KOSPI,KOSDAQ}}
const fidx = new Map();
async function loadFrames() {
  F = FRAMES ? JSON.parse(readFileSync(FRAMES, 'utf8')) : await getJSON(`${PUBLIC}/api/replay?date=${DATE}&step=1&from=0901&to=1100`);
  F.codes.forEach((c, i) => fidx.set(c, i));
  console.log(`frames ${F.date} ${F.frames[0].t}–${F.frames.at(-1).t} (${F.frames.length}) × ${F.codes.length} codes`);
}
const T0 = Date.now();
const simSec = () => ((Date.now() - T0) / 1000) * SPEED;                   // seconds after 09:01:00 of the replay day
const simIso = s => { const t = 9 * 3600 + 60 + Math.floor(s); const hh = String(Math.floor(t / 3600)).padStart(2, '0'), mm = String(Math.floor(t / 60) % 60).padStart(2, '0'), ss = String(t % 60).padStart(2, '0'); return `${F.date}T${hh}:${mm}:${ss}+09:00`; };

// the frame price of code c at sim second s (moves from frame m to m+1 at the code's own second of the minute)
function framePrice(c, s) {
  const i = fidx.get(c);
  if (i == null) return null;
  const n = F.frames.length, m = Math.min(n - 1, Math.floor(s / 60)), sec = s % 60;
  const cur = F.frames[m], nxt = F.frames[Math.min(n - 1, m + 1)];
  const moved = sec >= h01(c + ':phase') * 60;
  const f0 = F.frames[0];
  const pc = f0.p[i] / (1 + f0.r[i] / 100);                               // that day's previous close
  return { p: (moved ? nxt : cur).p[i], pc };
}
const state = new Map();              // code → {hi, lo, op, v, tv, nv, ntv, lastSec}
function rowAt(c, s) {
  const b = base.get(c);
  if (!b) return null;
  const bp = +b.closePriceRaw, bpc = bp - +b.compareToPreviousClosePriceRaw;
  const fp = framePrice(c, s);
  let p = fp ? fp.p : bp, pc = fp ? fp.pc : bpc;
  const bucket = Math.floor(s / 3);
  if (!fp && h01(c + ':' + bucket) < 0.05) p += tick(p) * (h01(c + ':d' + bucket) < 0.5 ? -1 : 1);   // codes without frames: a slow walk
  if (CHURN > 0 && h01(c + ':c' + bucket) < CHURN) p += tick(p) * (h01(c + ':cd' + bucket) < 0.5 ? -1 : 1);
  pc = Math.round(pc / tick(pc)) * tick(pc);                              // r has 2 decimals: snap the derived close to a tick
  const st = state.get(c) || { op: fp ? F.frames[0].p[fidx.get(c)] : +b.openPriceRaw || p, hi: 0, lo: Infinity, v: Math.round((+b.accumulatedTradingVolumeRaw || 1000) * 0.05), tv: 0, nv: 0, ntv: 0, lastSec: -1 };
  st.hi = Math.max(st.hi, p, st.op); st.lo = Math.min(st.lo, p, st.op);
  const sec = Math.floor(s);
  if (sec > st.lastSec) {                                                    // simulated trades since the last answer
    const liquid = (+b.accumulatedTradingValueRaw || 0) > 1e11;
    for (let k = Math.max(st.lastSec + 1, sec - 10); k <= sec; k++) {
      if (h01(c + ':t' + k) < (liquid ? 0.9 : 0.3)) { const q = Math.max(1, Math.round((+b.accumulatedTradingVolumeRaw || 1000) / 23400 * (0.5 + h01(c + ':q' + k)))); st.v += q; st.tv += q * p; st.nv += Math.round(q / 3); st.ntv += Math.round(q / 3) * p; }
    }
    st.lastSec = sec;
  }
  state.set(c, st);
  const d = p - pc, r = pc ? r2(d / pc * 100) : 0, iso = simIso(s);
  const shares = (+b.marketValueFullRaw || 0) / (bp || 1);
  const row = structuredClone(b);
  Object.assign(row, {
    closePrice: fmt(p), closePriceRaw: String(p), compareToPreviousClosePrice: fmt(d), compareToPreviousClosePriceRaw: String(d),
    compareToPreviousPrice: dir(d), fluctuationsRatio: r.toFixed(2), fluctuationsRatioRaw: r.toFixed(2),
    openPriceRaw: String(st.op), highPriceRaw: String(st.hi), lowPriceRaw: String(st.lo),
    accumulatedTradingVolumeRaw: String(st.v), accumulatedTradingValueRaw: String(st.tv), marketValueFullRaw: String(Math.round(shares * p)),
    marketStatus: 'OPEN', localTradedAt: iso,
  });
  if (row.overMarketPriceInfo) {
    let np = p;
    if (CHURN > 0 && h01(c + ':nx' + bucket) < CHURN / 2) np += tick(p) * (h01(c + ':nxd' + bucket) < 0.5 ? -1 : 1);   // NXT main market tracks KRX
    const nd = np - pc, nr = pc ? r2(nd / pc * 100) : 0;
    Object.assign(row.overMarketPriceInfo, {
      tradingSessionType: 'REGULAR_MARKET', overMarketStatus: 'OPEN', overPrice: fmt(np), compareToPreviousClosePrice: fmt(nd), fluctuationsRatio: nr.toFixed(2),
      compareToPreviousPrice: dir(nd), localTradedAt: iso, accumulatedTradingVolumeRaw: String(st.nv), accumulatedTradingValueRaw: String(st.ntv),
      openPrice: fmt(st.op), highPrice: fmt(Math.max(st.hi, np)), lowPrice: fmt(Math.min(st.lo, np)),
      tradeStopType: { code: '1', text: '운영.Trading', name: 'TRADING' },
    });
  }
  return row;
}
function indexAt(s) {
  const n = F.frames.length, m = Math.min(n - 1, Math.floor(s / 60)), f = (s % 60) / 60;
  return ['KOSPI', 'KOSDAQ'].map(k => {
    const a = F.index[k], v = r2(a[m] + (a[Math.min(n - 1, m + 1)] - a[m]) * f), b = F.base ? F.base[k] : a[0], d = r2(v - b);
    return { itemCode: k, stockName: k === 'KOSPI' ? '코스피' : '코스닥', closePriceRaw: String(v), compareToPreviousClosePriceRaw: String(d), fluctuationsRatioRaw: (b ? r2(d / b * 100) : 0).toFixed(2), compareToPreviousPrice: dir(d), marketStatus: 'OPEN', localTradedAt: simIso(s) };
  });
}

/* ── server ── */
const stats = { stock: 0, index: 0, codes: 0, bytes: 0, started: new Date().toISOString() };
const send = (res, status, body) => { const t = typeof body === 'string' ? body : JSON.stringify(body); stats.bytes += t.length; res.writeHead(status, { 'content-type': 'application/json;charset=UTF-8', 'cache-control': 'no-cache, no-store, max-age=0, must-revalidate' }); res.end(t); };
const stamp = () => { const k = new Date(Date.now() + 9 * 3600e3).toISOString(); return k.slice(0, 19).replace(/[-T:]/g, ''); };
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  try {
    if (url.pathname === '/__codes') { stats.codes++; const ch = url.searchParams.get('ch') === 'all' ? 'all' : 'top'; return send(res, 200, { codes: CODES[ch], meta: Object.fromEntries(CODES[ch].map(c => [c, meta[c]])) }); }
    if (url.pathname === '/__stats') return send(res, 200, { ...stats, live: LIVE, simSec: F ? Math.round(simSec()) : null, sim: F ? simIso(simSec()) : null, churn: CHURN, speed: SPEED });
    const m = url.pathname.match(/^\/api\/realtime\/domestic\/(stock|index)\/([A-Z0-9,]+)$/);
    if (!m) return send(res, 404, { error: 'not found' });
    stats[m[1]]++;
    if (LIVE) { const r = await fetch(NAVER + url.pathname, { headers: { 'user-agent': UA, accept: 'application/json' } }); return send(res, r.status, await r.text()); }
    const s = simSec();
    if (m[1] === 'index') return send(res, 200, { pollingInterval: 7000, time: stamp(), datas: indexAt(s) });
    const codes = m[2].split(',');
    await loadBase(codes);
    return send(res, 200, { pollingInterval: 7000, time: stamp(), datas: codes.map(c => rowAt(c, s)).filter(Boolean) });
  } catch (e) { console.error(e); send(res, 502, { error: String(e.message || e) }); }
}).listen(PORT, '127.0.0.1', async () => {
  if (!LIVE) { await loadFrames(); await loadBase(CODES.top); console.log(`base ${base.size} rows`); }
  console.log(`upstream mock on http://127.0.0.1:${PORT} (${LIVE ? 'live Naver pass-through' : `replay ${DATE} ×${SPEED}, churn ${CHURN}`})`);
});
