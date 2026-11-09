// Cloudflare Worker: serves the heatmap page and proxies Naver Finance so the browser can poll it
// (Naver sends no CORS headers and 403s any foreign Origin, so the page can't call it directly).
//
//   GET /, /index.html                 → web/index.html fetched from env.ASSET_BASE (edge-cached 120 s)
//   GET /api/quotes                    → top stocks of KOSPI + KOSDAQ by market cap, plus both indices
//   GET /api/chart/:code               → today's intraday prices for one stock (heatmap sparkline)
//   GET /api/stock/:code/summary       → quote + key ratios
//   GET /api/stock/:code/chart?tf=…    → candles (1d 5d 3m 1y 3y 10y)
//   GET /api/stock/:code/orderbook     → 5-level order book, best price first
//   GET /api/stock/:code/investors     → investor net buying, latest 60 days
//   GET /api/stock/:code/daily?page=N  → daily price table, 60 rows per page
//   GET /api/health                    → {ok:true}
// Contract: AGENTS.md §3, sources and pitfalls: data/ENDPOINTS_DETAIL.md.
// The Worker has no build-generated modules: page and stock universe come from ASSET_BASE.

const DEFAULT_ASSET_BASE = 'https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/';
const QUOTES_TTL = 8;                // seconds
const CHART_TTL = 30;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const CODE_RE = /^[0-9A-Z]{6}$/;
const TFS = ['1d', '5d', '3m', '1y', '3y', '10y'];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    env = env || {};
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET, OPTIONS' } });
      if (path === '/' || path === '/index.html') return await getPage(request, env, ctx);
      if (path === '/api/health') return json({ ok: true });
      if (path === '/api/quotes') return await edgeCached(request, ctx, 'quotes', QUOTES_TTL, () => getQuotes(env));
      let m = path.match(/^\/api\/chart\/([^/]+)$/);
      if (m) {
        if (!CODE_RE.test(m[1])) return fail(400, '종목 코드가 올바르지 않아요');
        return await edgeCached(request, ctx, 'chart-' + m[1], CHART_TTL, () => getChart(m[1]));
      }
      m = path.match(/^\/api\/stock\/([^/]+)\/(summary|chart|orderbook|investors|daily)$/);
      if (m) {
        const code = m[1], kind = m[2];
        if (!CODE_RE.test(code)) return fail(400, '종목 코드가 올바르지 않아요');
        if (kind === 'summary') return await edgeCached(request, ctx, `sum-${code}`, 30, () => getSummary(code));
        if (kind === 'orderbook') return await edgeCached(request, ctx, `ob-${code}`, 2, () => getOrderbook(code));
        if (kind === 'investors') return await edgeCached(request, ctx, `inv-${code}`, 600, () => getInvestors(code));
        if (kind === 'chart') {
          const tf = url.searchParams.get('tf') || '1d';
          if (!TFS.includes(tf)) return fail(400, 'tf는 ' + TFS.join(', ') + ' 중 하나여야 해요');
          return await edgeCached(request, ctx, `cht-${code}-${tf}`, tf === '1d' || tf === '5d' ? 20 : 600, () => getStockChart(code, tf));
        }
        const raw = url.searchParams.get('page') || '1';
        const page = /^\d{1,3}$/.test(raw) ? parseInt(raw, 10) : 0;
        if (page < 1) return fail(400, 'page는 1 이상의 정수여야 해요');
        return await edgeCached(request, ctx, `day-${code}-${page}`, 60, () => getDaily(code, page));
      }
      return new Response('Not found', { status: 404 });
    } catch (err) {
      if (err && err.status) return fail(err.status, err.message);
      return fail(502, String(err && err.message || err));
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
const fail = (status, message) => json({ error: message }, status);
class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }

async function edgeCached(request, ctx, key, ttl, produce) {
  const cache = caches.default;
  const cacheKey = new Request(new URL('/__cache/' + key, request.url).toString());
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  const body = await produce();          // throws on failure → never cached
  const res = json(body, 200, ttl);
  ctx.waitUntil(cache.put(cacheKey, res.clone()));
  return res;
}
// Build fresh headers: Naver answers 403 to any foreign Origin, so the viewer's headers must not be forwarded.
async function naver(url) {
  const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (r.status >= 400 && r.status < 500 && r.status !== 429 && r.status !== 403) throw new HttpError(404, '종목을 찾을 수 없어요');
  if (!r.ok) throw new Error(`naver ${r.status} ${url}`);
  return r.json();
}
// legacy: missing → 0 (used by /api/quotes, whose shape is fixed)
const num = v => {
  if (v == null) return 0;
  const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/,/g, ''));
  return Number.isFinite(n) ? n : 0;
};
// strict: "1,234", "+858,557", "8.38배", "0.89%" → number; missing / "N/A" → null
const pn = v => {
  if (v == null) return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const m = String(v).replace(/,/g, '').match(/[-+]?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
};
// "1,092조 6,695억" → 억원
function parseEok(v) {
  if (v == null) return null;
  const s = String(v).replace(/,/g, '');
  const jo = s.match(/(\d+)\s*조/), eok = s.match(/(\d+)\s*억/);
  if (!jo && !eok) return pn(s) == null ? null : Math.round(pn(s) / 1e8);
  return (jo ? +jo[1] * 10000 : 0) + (eok ? +eok[1] : 0);
}
// change string is already signed ("-2,100") but fall back on the direction code (4 하한, 5 하락) if it is not
function signedChange(change, dir) {
  const n = pn(change);
  if (n == null) return null;
  const code = dir && String(dir.code);
  return (code === '4' || code === '5') ? -Math.abs(n) : (code === '1' || code === '2') ? Math.abs(n) : n;
}
const round2 = x => Math.round(x * 100) / 100;
const kstNow = () => new Date(Date.now() + 9 * 3600e3);     // read with getUTC* → KST wall clock
const pad = n => String(n).padStart(2, '0');
const ymd = d => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
const dash = s => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
function kstDaysAgo(days, months = 0, years = 0) {
  const d = kstNow();
  d.setUTCFullYear(d.getUTCFullYear() - years);
  d.setUTCMonth(d.getUTCMonth() - months);
  d.setUTCDate(d.getUTCDate() - days);
  return d;
}

/* ── page (static) ─────────────────────────────── */
const assetBase = env => {
  const b = (env && env.ASSET_BASE) || DEFAULT_ASSET_BASE;
  return b.endsWith('/') ? b : b + '/';
};
async function edgeText(request, ctx, key, ttl, fetchText) {
  const cache = caches.default;
  const cacheKey = new Request(new URL('/__cache/' + key, request.url).toString());
  const hit = await cache.match(cacheKey);
  if (hit) return hit.text();
  const text = await fetchText();
  ctx.waitUntil(cache.put(cacheKey, new Response(text, { headers: { 'cache-control': `public, max-age=${ttl}` } })));
  return text;
}
async function getPage(request, env, ctx) {
  try {
    const html = await edgeText(request, ctx, 'page', 120, async () => {
      const r = await fetch(assetBase(env) + 'index.html');
      if (!r.ok) throw new Error('asset ' + r.status);
      return r.text();
    });
    return new Response(html, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=60' } });
  } catch (e) {
    return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>잠시 후 다시 열어 주세요</title>' +
      '<body style="font:16px/1.6 sans-serif;background:#131418;color:#eee;padding:48px 24px"><h1 style="font-size:20px">화면을 불러오지 못했어요</h1><p>잠시 후 다시 열어 주세요.</p></body>',
      { status: 503, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
  }
}

/* ── stock universe (ASSET_BASE/universe.json) ─────────────────────────────── */
// {K, Q, I}: K/Q = 8 chars per stock = 6-char code + 2-char base36 index into I ([업종, 섹터]).
let universeMem = null;                 // { at, map }
async function getUniverse(env) {
  const now = Date.now();
  if (universeMem && now - universeMem.at < 600e3) return universeMem.map;
  const base = assetBase(env);
  const cache = caches.default;
  const cacheKey = new Request(base + 'universe.json#edge');
  try {
    let res = await cache.match(cacheKey);
    if (!res) {
      const r = await fetch(base + 'universe.json');
      if (!r.ok) throw new Error('universe ' + r.status);
      res = new Response(await r.text(), { headers: { 'cache-control': 'public, max-age=3600' } });
      await cache.put(cacheKey, res.clone());
    }
    const U = await res.json();
    const map = new Map();
    for (const m of ['K', 'Q']) {
      const str = U[m] || '';
      for (let k = 0; k + 8 <= str.length; k += 8) {
        const [i, s] = U.I[parseInt(str.slice(k + 6, k + 8), 36)];
        map.set(str.slice(k, k + 6), { m, i, s });
      }
    }
    universeMem = { at: now, map };
    return map;
  } catch (e) {
    if (universeMem) return universeMem.map;      // stale beats nothing
    throw e;
  }
}

/* ── /api/quotes ─────────────────────────────── */
// One polling call returns live rows for up to 1000 codes; we send the top 300 per market
// (from ASSET_BASE/universe.json) to keep the response small and CPU time low on the free plan.
async function getQuotes(env) {
  const STOCKS = await getUniverse(env);
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

/* ── /api/stock/:code/summary ─────────────────────────────── */
// basic (price, status) + integration (ratios) fetched in parallel.
async function getSummary(code) {
  const [b, g] = await Promise.all([
    naver(`https://m.stock.naver.com/api/stock/${code}/basic`),
    naver(`https://m.stock.naver.com/api/stock/${code}/integration`),
  ]);
  const t = {};
  for (const x of g.totalInfos || []) t[x.code] = x.value;
  const ex = b.stockExchangeType || {};
  // Regular-session status only: Naver reports OPEN also during NXT after-market, so gate it on KST 09:00–15:30.
  const k = kstNow(), hhmm = pad(k.getUTCHours()) + pad(k.getUTCMinutes());
  const regular = b.marketStatus === 'OPEN' && hhmm >= (ex.startTime || '0900') && hhmm < (ex.endTime || '1530');
  return {
    code: b.itemCode || code,
    name: b.stockName || g.stockName || null,
    market: b.sosok === '1' ? 'Q' : 'K',
    price: pn(b.closePrice),
    change: signedChange(b.compareToPreviousClosePrice, b.compareToPreviousPrice),
    ratio: pn(b.fluctuationsRatio),
    marketStatus: regular ? 'OPEN' : 'CLOSE',
    per: pn(t.per),
    eps: pn(t.eps),
    pbr: pn(t.pbr),
    bps: pn(t.bps),
    dividendYield: pn(t.dividendYieldRatio),
    high52: pn(t.highPriceOf52Weeks),
    low52: pn(t.lowPriceOf52Weeks),
    marketCap: parseEok(t.marketValue),
    foreignRate: pn(t.foreignRate),
    asOf: b.localTradedAt || null,
  };
}

/* ── /api/stock/:code/chart ─────────────────────────────── */
// tf → [naver interval, range start]. prevClose = close of the bar just before the first bar shown.
const kstSec = s => Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8), +s.slice(8, 10), +s.slice(10, 12), +(s.slice(12, 14) || 0)) / 1000 - 9 * 3600;
async function getStockChart(code, tf) {
  const base = `https://api.stock.naver.com/chart/domestic/item/${code}/`;
  const end = ymd(kstNow()) + '235959';
  const q = (from) => `?startDateTime=${ymd(from)}000000&endDateTime=${end}`;
  if (tf === '1d' || tf === '5d') {
    const interval = tf === '1d' ? 'minute' : 'minute5';
    const [rows, days] = await Promise.all([
      naver(base + interval + q(kstDaysAgo(tf === '1d' ? 9 : 12))),
      naver(base + 'day' + q(kstDaysAgo(20))),
    ]);
    const all = Array.isArray(rows) ? rows : [];
    const dayKeys = [...new Set(all.map(r => String(r.localDateTime).slice(0, 8)))].sort().slice(tf === '1d' ? -1 : -5);
    const keep = new Set(dayKeys);
    const bars = all.filter(r => keep.has(String(r.localDateTime).slice(0, 8))).map(r => ({
      t: kstSec(String(r.localDateTime)), o: pn(r.openPrice), h: pn(r.highPrice), l: pn(r.lowPrice), c: pn(r.currentPrice), v: pn(r.accumulatedTradingVolume),
    }));
    const prior = (Array.isArray(days) ? days : []).filter(d => dayKeys.length && String(d.localDate) < dayKeys[0]);
    return { tf, interval: tf === '1d' ? '1m' : '5m', prevClose: prior.length ? pn(prior[prior.length - 1].closePrice) : null, bars };
  }
  const [interval, from] = {
    '3m': ['day', kstDaysAgo(10, 3)],
    '1y': ['day', kstDaysAgo(10, 0, 1)],
    '3y': ['week', kstDaysAgo(10, 0, 3)],
    '10y': ['month', kstDaysAgo(35, 0, 10)],
  }[tf];
  const rows = await naver(base + interval + q(from));
  const list = Array.isArray(rows) ? rows : [];
  const cutoff = ymd({ '3m': kstDaysAgo(0, 3), '1y': kstDaysAgo(0, 0, 1), '3y': kstDaysAgo(0, 0, 3), '10y': kstDaysAgo(0, 0, 10) }[tf]);
  let first = list.findIndex(r => String(r.localDate) >= cutoff);
  if (first < 0) first = list.length;
  const bars = list.slice(first).map(r => ({
    t: weekStart(String(r.localDate), interval), o: pn(r.openPrice), h: pn(r.highPrice), l: pn(r.lowPrice), c: pn(r.closePrice), v: pn(r.accumulatedTradingVolume),
  }));
  return { tf, interval: { day: '1d', week: '1w', month: '1mo' }[interval], prevClose: first > 0 ? pn(list[first - 1].closePrice) : null, bars };
}
// Naver stamps weekly bars with the Sunday that starts the week; show the Monday (first trading day) instead.
function weekStart(s, interval) {
  if (interval !== 'week') return dash(s);
  const d = new Date(Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)));
  if (d.getUTCDay() === 0) d.setUTCDate(d.getUTCDate() + 1);
  return dash(ymd(d));
}

/* ── /api/stock/:code/orderbook ─────────────────────────────── */
async function getOrderbook(code) {
  const o = await naver(`https://m.stock.naver.com/api/stock/${code}/askingPrice`);
  const lvl = x => ({ price: pn(x.price), qty: pn(x.count) });
  return {
    asks: (o.sellInfo || []).map(lvl).reverse(),       // Naver lists the highest ask first → best (lowest) ask first
    bids: (o.buyInfos || []).map(lvl),                 // already best (highest) bid first
    totalAsk: pn(o.totalSell),
    totalBid: pn(o.totalBuy),
    prevClose: pn(o.lastClosePrice),
    asOf: new Date().toISOString(),                    // Naver gives no timestamp: this is the fetch time
  };
}

/* ── /api/stock/:code/investors ─────────────────────────────── */
async function getInvestors(code) {
  const rows = await naver(`https://m.stock.naver.com/api/stock/${code}/trend?pageSize=60`);
  return {
    rows: (Array.isArray(rows) ? rows : []).map(r => {
      const close = pn(r.closePrice), ch = signedChange(r.compareToPreviousClosePrice, r.compareToPreviousPrice);
      const prev = close != null && ch != null ? close - ch : null;
      return {
        date: dash(String(r.bizdate)),
        close,
        ratio: prev ? round2(ch / prev * 100) : null,   // derived: change / previous close
        individual: pn(r.individualPureBuyQuant),
        foreign: pn(r.foreignerPureBuyQuant),
        institution: pn(r.organPureBuyQuant),
        foreignHoldRatio: pn(r.foreignerHoldRatio),
      };
    }),
  };
}

/* ── /api/stock/:code/daily ─────────────────────────────── */
async function getDaily(code, page) {
  const rows = await naver(`https://m.stock.naver.com/api/stock/${code}/price?pageSize=60&page=${page}`);
  const list = Array.isArray(rows) ? rows : [];
  return {
    page,
    rows: list.map(r => ({
      date: String(r.localTradedAt).slice(0, 10),
      close: pn(r.closePrice),
      change: signedChange(r.compareToPreviousClosePrice, r.compareToPreviousPrice),
      ratio: pn(r.fluctuationsRatio),
      open: pn(r.openPrice),
      high: pn(r.highPrice),
      low: pn(r.lowPrice),
      volume: pn(r.accumulatedTradingVolume),
    })),
    hasMore: list.length >= 60,
  };
}

