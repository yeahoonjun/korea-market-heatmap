// Cloudflare Worker: serves the heatmap page and proxies Naver Finance quotes
// so the browser can poll them (Naver sends no CORS headers, so the page can't call it directly).
//
//   GET /                 → the heatmap page (live mode)
//   GET /api/quotes       → top stocks of KOSPI + KOSDAQ by market cap, plus both indices
//   GET /api/chart/:code  → today's intraday prices for one stock (detail-panel sparkline)
//   GET /api/health       → {ok:true}
//
// Responses are cached at the edge for a few seconds, so many viewers cost Naver one request per window.

import PAGE from './page.js';
import UNIVERSE from './universe.js';   // top 300 per market with 업종/섹터, generated at build time

// decode "CCCCCCxx…" (code + base36 index into UNIVERSE.I) → Map(code → {m, i, s})
const STOCKS = new Map();
for (const m of ['K', 'Q']) {
  const str = UNIVERSE[m];
  for (let k = 0; k < str.length; k += 8) {
    const [i, s] = UNIVERSE.I[parseInt(str.slice(k + 6, k + 8), 36)];
    STOCKS.set(str.slice(k, k + 6), { m, i, s });
  }
}

const QUOTES_TTL = 8;                // seconds
const CHART_TTL = 30;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === '/' || path === '/index.html') {
        return new Response(PAGE, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=300' } });
      }
      if (path === '/api/health') return json({ ok: true });
      if (path === '/api/quotes') return edgeCached(request, ctx, 'quotes', QUOTES_TTL, getQuotes);
      const m = path.match(/^\/api\/chart\/([0-9A-Z]{6})$/);
      if (m) return edgeCached(request, ctx, 'chart-' + m[1], CHART_TTL, () => getChart(m[1]));
      return new Response('Not found', { status: 404 });
    } catch (err) {
      return json({ error: String(err && err.message || err) }, 502);
    }
  },
};

/* ── helpers ─────────────────────────────── */
function json(body, status = 200, maxAge = 0) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': maxAge ? `public, max-age=${maxAge}` : 'no-store',
      'access-control-allow-origin': '*',
    },
  });
}
async function edgeCached(request, ctx, key, ttl, produce) {
  const cache = caches.default;
  const cacheKey = new Request(new URL('/__cache/' + key, request.url).toString());
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  const body = await produce();
  const res = json(body, 200, ttl);
  ctx.waitUntil(cache.put(cacheKey, res.clone()));
  return res;
}
// Build fresh headers: Naver answers 403 to any foreign Origin, so the viewer's headers must not be forwarded.
async function naver(url) {
  const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (!r.ok) throw new Error(`naver ${r.status} ${url}`);
  return r.json();
}
const num = v => {
  if (v == null) return 0;
  const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/,/g, ''));
  return Number.isFinite(n) ? n : 0;
};

/* ── /api/quotes ─────────────────────────────── */
// One polling call returns live rows for up to 1000 codes; we send the top 300 per market
// (from the build-time snapshot) to keep the response small and CPU time low on the free plan.
async function getQuotes() {
  const codes = [...STOCKS.keys()];
  const [live, idx] = await Promise.all([
    naver(`https://polling.finance.naver.com/api/realtime/domestic/stock/${codes.join(',')}`),
    naver('https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ').catch(() => null),
  ]);
  const stocks = [];
  let asOf = '', stockOpen = false;
  for (const s of live.datas || []) {
    const meta = STOCKS.get(s.itemCode);
    if (!meta) continue;
    if (s.marketStatus === 'OPEN') stockOpen = true;
    if (s.localTradedAt && s.localTradedAt > asOf) asOf = s.localTradedAt;
    stocks.push({
      c: s.itemCode,
      n: s.stockName,
      m: meta.m,
      s: meta.s,
      i: meta.i,
      cap: Math.round(num(s.marketValueFullRaw) / 1e8),          // 원 → 억원
      p: num(s.closePriceRaw),
      d: num(s.compareToPreviousClosePriceRaw),
      r: num(s.fluctuationsRatioRaw),
      tv: Math.round(num(s.accumulatedTradingValueRaw) / 1e8),  // 원 → 억원
      v: num(s.accumulatedTradingVolumeRaw),
    });
  }
  const index = {}, marketStatus = {};
  for (const x of (idx && idx.datas) || []) {
    index[x.itemCode] = { value: num(x.closePriceRaw), change: num(x.compareToPreviousClosePriceRaw), ratio: num(x.fluctuationsRatioRaw) };
    marketStatus[x.itemCode] = x.marketStatus;               // regular-session status
  }
  const regularOpen = Object.values(marketStatus).includes('OPEN');
  return {
    asOf,
    source: '네이버 증권 (polling.finance.naver.com)',
    marketStatus,
    afterHours: !regularOpen && stockOpen,                   // NXT/시간외 prices are moving after 15:30
    index,
    stocks,
  };
}

/* ── /api/chart/:code ─────────────────────────────── */
// 5-minute bars of the latest trading day, regular session only (09:00–15:30).
async function getChart(code) {
  const raw = await naver(`https://api.stock.naver.com/chart/domestic/item/${code}/minute5`);
  const rows = Array.isArray(raw) ? raw : (raw && raw.priceInfos) || [];
  if (!rows.length) return { day: null, points: [] };
  const day = String(rows[rows.length - 1].localDateTime).slice(0, 8);
  const points = rows
    .filter(r => String(r.localDateTime).startsWith(day) && String(r.localDateTime).slice(8, 12) <= '1530')
    .map(r => [String(r.localDateTime).slice(8, 12), num(r.currentPrice)]);
  return { day, points };
}
