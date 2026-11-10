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
//   GET /api/stock/:code/news          → latest 20 news items
//   GET /api/stock/:code/disclosures   → latest 20 disclosures
//   GET /api/quotes?codes=c1,c2,…      → same shape for the given codes (≤ 300)
//   GET /api/themes                    → theme list with ratio / up / flat / down
//   GET /api/market                    → market strip (indices + spark, USDKRW, US futures, WTI, gold, BTC)
//   GET /api/world?kind=index|commodity, /api/world/chart/:key?tf=3m|1y → world indices / futures / commodities (AGENTS §3-4)
//   GET /api/replay/dates, /api/replay?date=YYYY-MM-DD → intraday replay frames recorded in KV (env.REPLAY, one key per frame)
//   GET /api/stock/:code/finance?period=annual|quarter → financial statements (cols oldest→newest)
//   GET /api/stock/:code/research      → broker reports (target / opinion parsed from the preview) + consensus
//   GET /data/{themes,periods,flows,names,close}.json, PWA files → static from ASSET_BASE (whitelist)
//   scheduled()                        → cron: appends a replay frame every 5 min on weekdays 09:00 → session end (stockExchangeType.endTime) KST
//   GET /api/health                    → {ok:true}
// Contract: AGENTS.md §3, sources and pitfalls: data/ENDPOINTS_DETAIL.md.
// The Worker has no build-generated modules: page and stock universe come from ASSET_BASE.

const DEFAULT_ASSET_BASE = 'https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/';
const QUOTES_TTL = 8;                // seconds
const CHART_TTL = 30;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const CODE_RE = /^[0-9A-Z]{6}$/;
const ORIGIN = 'https://kospimap.pages.dev';
const TFS = ['1d', '5d', '3m', '1y', '3y', '10y'];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    env = env || {};
    let m;
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { 'access-control-allow-origin': ORIGIN, 'access-control-allow-methods': 'GET, OPTIONS', vary: 'origin' } });
      if (path === '/' || path === '/index.html') return await getPage(request, env, ctx);
      if (path === '/api/health') return json({ ok: true });
      if (path === '/api/quotes') {
        const raw = url.searchParams.get('codes');
        if (raw == null) return await edgeCached(request, ctx, 'quotes', QUOTES_TTL, () => getQuotes(env));
        const codes = [...new Set(raw.split(',').map(x => x.trim().toUpperCase()))].sort();
        if (!codes.length || codes.length > 300 || !codes.every(c => CODE_RE.test(c))) return fail(400, 'codes는 6자 종목 코드를 쉼표로 이어 300개까지 보낼 수 있어요');
        return await edgeCached(request, ctx, 'quotes-' + codes.join(','), QUOTES_TTL, () => getQuotes(env, codes));
      }
      if (path === '/api/breadth') {
        const mk = url.searchParams.get('m'), pr = url.searchParams.get('part') || '1';
        if (mk !== 'K' && mk !== 'Q') return fail(400, 'm은 K 또는 Q여야 해요');
        if (!/^\d{1,2}$/.test(pr) || +pr < 1) return fail(400, 'part는 1 이상의 정수여야 해요');
        const k = kstNow(), hhmm = pad(k.getUTCHours()) + pad(k.getUTCMinutes()), wd = k.getUTCDay();
        const live = wd >= 1 && wd <= 5 && hhmm >= '0900' && hhmm < lastEndTime;
        return await edgeCached(request, ctx, `breadth-${mk}-${+pr}`, live ? 30 : 600, () => getBreadth(env, mk, +pr));
      }
      if (path === '/api/world') {
        const kind = url.searchParams.get('kind') || '';
        if (kind !== 'index' && kind !== 'commodity') return fail(400, 'kind는 index 또는 commodity여야 해요');
        return await edgeCached(request, ctx, 'world-' + kind, 30, () => getWorld(kind));
      }
      m = path.match(/^\/api\/world\/chart\/([^/]+)$/);
      if (m) {
        const item = WORLD_BY_KEY.get(m[1]);
        if (!item) return fail(400, '알 수 없는 항목이에요');
        const tf = url.searchParams.get('tf') || '3m';
        if (tf !== '3m' && tf !== '1y') return fail(400, 'tf는 3m 또는 1y여야 해요 (해외 분봉 원천이 없어요)');
        return await edgeCached(request, ctx, `wch-${item.key}-${tf}`, 600, () => getWorldChart(item, tf));
      }
      if (path === '/api/themes') return await edgeCached(request, ctx, 'themes', 30, () => getThemes());
      if (path === '/api/market') return await edgeCached(request, ctx, 'market', 30, () => getMarket());
      if (path === '/api/replay/dates') return await edgeCached(request, ctx, 'replay-dates', 60, () => getReplayDates(env));
      if (path === '/api/replay') {
        const d = url.searchParams.get('date') || '';
        if (d && !/^\d{4}-\d{2}-\d{2}$/.test(d)) return fail(400, 'date는 YYYY-MM-DD 형식이어야 해요');
        const past = d && d.replace(/-/g, '') < ymd(kstNow());           // a finished day never changes
        return await edgeCached(request, ctx, 'replay-' + (d || 'latest'), past ? 3600 : 60, () => getReplay(env, d));
      }
      if (ASSETS[path]) return await getAsset(request, env, ctx, path);
      m = path.match(/^\/api\/chart\/([^/]+)$/);
      if (m) {
        if (!CODE_RE.test(m[1])) return fail(400, '종목 코드가 올바르지 않아요');
        return await edgeCached(request, ctx, 'chart-' + m[1], CHART_TTL, () => getChart(m[1]));
      }
      m = path.match(/^\/api\/stock\/([^/]+)\/(summary|chart|orderbook|investors|daily|news|disclosures|finance|research)$/);
      if (m) {
        const code = m[1], kind = m[2];
        if (!CODE_RE.test(code)) return fail(400, '종목 코드가 올바르지 않아요');
        if (kind === 'summary') return await edgeCached(request, ctx, `sum-${code}`, 30, () => getSummary(code));
        if (kind === 'orderbook') return await edgeCached(request, ctx, `ob-${code}`, 2, () => getOrderbook(code));
        if (kind === 'research') return await edgeCached(request, ctx, `res-${code}`, 1800, () => getResearch(code));
        if (kind === 'finance') {
          const period = url.searchParams.get('period') || 'annual';
          if (period !== 'annual' && period !== 'quarter') return fail(400, 'period는 annual 또는 quarter여야 해요');
          return await edgeCached(request, ctx, `fin-${code}-${period}`, 21600, () => getFinance(code, period));
        }
        if (kind === 'news') return await edgeCached(request, ctx, `news-${code}`, 300, () => getNews(code));
        if (kind === 'disclosures') return await edgeCached(request, ctx, `dis-${code}`, 300, () => getDisclosures(code, env));
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
  async scheduled(event, env, ctx) {
    await recordFrame(event, env || {});
  },
};

/* ── helpers ─────────────────────────────── */
function json(body, status = 200, maxAge = 0) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': maxAge ? `public, max-age=${maxAge}` : 'no-store',
      'access-control-allow-origin': ORIGIN,
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
let lastEndTime = '1530';               // session end seen in the latest polling data
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
    // X: every other listed stock (not streamed) — 9 chars each: code + base36 index into I + market — so
    // /api/quotes?codes= (watchlist, themes) can still give them a sector instead of 기타.
    const extra = new Map();
    const xs = U.X || '';
    for (let k = 0; k + 9 <= xs.length; k += 9) {
      const [i, s] = U.I[parseInt(xs.slice(k + 6, k + 8), 36)];
      extra.set(xs.slice(k, k + 6), { m: xs[k + 8], i, s });
    }
    universeMem = { at: now, map, extra };
    return map;
  } catch (e) {
    if (universeMem) return universeMem.map;      // stale beats nothing
    throw e;
  }
}

/* ── NXT (overMarketPriceInfo) ─────────────────────────────── */
// → {p, d, r, s:'pre'|'reg'|'after', o:1|0, t} | null (no overPrice, unknown session or trading halted). Read-only: no extra calls.
function nxtOf(i) {
  if (!i || i.overPrice == null || i.overPrice === '') return null;
  const st = i.tradingSessionType === 'PRE_MARKET' ? 'pre' : i.tradingSessionType === 'AFTER_MARKET' ? 'after' : i.tradingSessionType === 'REGULAR_MARKET' ? 'reg' : null;
  const ts = i.tradeStopType && i.tradeStopType.name;
  if (!st || (ts && ts !== 'TRADING')) return null;
  const p = pn(i.overPrice);
  if (p == null) return null;
  return { p, d: sgn(i.compareToPreviousClosePrice, i.compareToPreviousPrice) ?? 0, r: sgn(i.fluctuationsRatio, i.compareToPreviousPrice) ?? 0, s: st, o: i.overMarketStatus === 'OPEN' ? 1 : 0, t: i.localTradedAt || null, v: pn(i.accumulatedTradingVolumeRaw ?? i.accumulatedTradingVolume), tv: i.accumulatedTradingValueRaw != null && i.accumulatedTradingValueRaw !== '' ? Math.round(num(i.accumulatedTradingValueRaw) / 1e8) : parseEok(i.accumulatedTradingValue) };
}

/* ── /api/quotes ─────────────────────────────── */
// One polling call returns live rows for up to 1000 codes; we send the top 300 per market
// (from ASSET_BASE/universe.json) to keep the response small and CPU time low on the free plan.
// `only` (array of codes) → those codes instead of the universe; stocks outside the universe get s/i '기타'.
async function getQuotes(env, only) { return (await quotesCore(env, only)).body; }
async function quotesCore(env, only) {
  const STOCKS = only ? await getUniverse(env).catch(() => new Map()) : await getUniverse(env);
  const codes = only || (universeMem.codes || (universeMem.codes = [...STOCKS.keys()]));
  const [live, idx] = await Promise.all([
    naver(`https://polling.finance.naver.com/api/realtime/domestic/stock/${codes.join(',')}`),
    naver('https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ').catch(() => null),
  ]);
  const stocks = [];
  let asOf = '', stockOpen = false, endTime = '', nxOpen = '', nxSess = '';
  for (const s of live.datas || []) {
    let meta = STOCKS.get(s.itemCode) || (only && universeMem && universeMem.extra && universeMem.extra.get(s.itemCode));
    if (!meta) {
      if (!only) continue;
      const ex = s.stockExchangeType && s.stockExchangeType.code;
      meta = { m: ex === 'KQ' ? 'Q' : 'K', s: '기타', i: '기타' };
    }
    if (s.marketStatus === 'OPEN') stockOpen = true;
    if (!endTime && s.stockExchangeType && s.stockExchangeType.endTime) endTime = String(s.stockExchangeType.endTime);
    if (s.localTradedAt && s.localTradedAt > asOf) asOf = s.localTradedAt;
    const limName = s.compareToPreviousPrice && s.compareToPreviousPrice.name;
    const row = {
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
    };
    if (limName === 'UPPER_LIMIT') row.lim = 1;
    else if (limName === 'LOWER_LIMIT') row.lim = -1;
    if (s.overMarketPriceInfo) {
      const nx = nxtOf(s.overMarketPriceInfo);
      if (nx) { row.nx = nx; if (nx.o) nxOpen = nx.s; else if (!nxSess) nxSess = nx.s; }
    }
    stocks.push(row);
  }
  const index = {}, marketStatus = {};
  for (const x of (idx && idx.datas) || []) {
    index[x.itemCode] = { value: num(x.closePriceRaw), change: num(x.compareToPreviousClosePriceRaw), ratio: num(x.fluctuationsRatioRaw) };
    marketStatus[x.itemCode] = x.marketStatus;               // regular-session status
  }
  if (!Object.keys(marketStatus).length) {                  // index call failed → judge the regular session by the KST clock
    const k = kstNow(), hhmm = pad(k.getUTCHours()) + pad(k.getUTCMinutes()), wd = k.getUTCDay();
    const st = stockOpen && wd >= 1 && wd <= 5 && hhmm >= '0900' && hhmm < (endTime || '1530') ? 'OPEN' : 'CLOSE';
    marketStatus.KOSPI = marketStatus.KOSDAQ = st;
  }
  const regularOpen = Object.values(marketStatus).includes('OPEN');
  return {
    endTime: /^\d{4}$/.test(endTime) ? (lastEndTime = endTime) : '1530',
    body: {
      asOf,
      source: '네이버 증권 (polling.finance.naver.com)',
      marketStatus,
      afterHours: !regularOpen && stockOpen,                 // NXT/시간외 prices are moving after the regular session
      nxt: { session: nxOpen || nxSess || null, open: !!nxOpen },
      index,
      stocks,
    },
  };
}

/* ── /api/breadth ─────────────────────────────── */
// All stocks of one market (universe K/Q top 300 + every X entry of that market, preferreds included), sorted by code,
// chunked by 600 → one polling call per request. Rows are tiny: [code, ratio, lim?].
const BREADTH_CHUNK = 600;
async function getBreadth(env, m, part) {
  await getUniverse(env);
  const U = universeMem;
  if (!U.byMkt) {
    U.byMkt = { K: [], Q: [] };
    for (const [c, v] of U.map) U.byMkt[v.m].push(c);
    for (const [c, v] of U.extra) if (U.byMkt[v.m]) U.byMkt[v.m].push(c);
    for (const k of ['K', 'Q']) U.byMkt[k] = [...new Set(U.byMkt[k])].sort();
  }
  const all = U.byMkt[m], parts = Math.max(1, Math.ceil(all.length / BREADTH_CHUNK));
  if (part > parts) throw new HttpError(400, `part는 1~${parts} 범위여야 해요`);
  const codes = all.slice((part - 1) * BREADTH_CHUNK, part * BREADTH_CHUNK);
  const live = await naver(`https://polling.finance.naver.com/api/realtime/domestic/stock/${codes.join(',')}`);
  let asOf = '', seenEnd = false;
  const rows = [];
  for (const s of live.datas || []) {
    if (s.localTradedAt && s.localTradedAt > asOf) asOf = s.localTradedAt;
    const row = [s.itemCode, num(s.fluctuationsRatioRaw)];
    const ln = s.compareToPreviousPrice && s.compareToPreviousPrice.name;
    if (ln === 'UPPER_LIMIT') row.push(1); else if (ln === 'LOWER_LIMIT') row.push(-1);
    const nx = s.overMarketPriceInfo && nxtOf(s.overMarketPriceInfo);
    if (nx) { if (row.length < 3) row.push(0); row.push(nx.r); }
    rows.push(row);
    if (!seenEnd && s.stockExchangeType && /^\d{4}$/.test(s.stockExchangeType.endTime)) { seenEnd = true; lastEndTime = s.stockExchangeType.endTime; }
  }
  return { m, part, parts, asOf, rows };
}

/* ── /api/world, /api/world/chart ─────────────────────────────── */
// Only codes Naver actually answers (probed 2026-11-09). One polling call per source → ≤ 3 subrequests per kind.
// src: polling path after /realtime/. Index codes keep Reuters form; item key = code without the leading dot.
const POLL = 'https://polling.finance.naver.com/api/realtime/';
const WORLD_CFG = {
  index: [
    { key: 'us', name: '미국', src: 'worldstock/index', items: [['.DJI', '다우존스'], ['.INX', 'S&P 500'], ['.IXIC', '나스닥 종합'], ['.NDX', '나스닥 100'], ['.SOX', '필라델피아 반도체'], ['.DJT', '다우운송']] },
    { key: 'usf', name: '미국 선물', src: 'worldstock/futures', items: [['EScv1', 'S&P 500 선물'], ['NQcv1', '나스닥 100 선물'], ['YMcv1', '다우 선물'], ['RTYcv1', '러셀 2000 선물']] },
    { key: 'eu', name: '유럽', src: 'worldstock/index', items: [['.STOXX50E', '유로스톡스 50'], ['.GDAXI', '독일 DAX'], ['.FTSE', '영국 FTSE 100'], ['.FCHI', '프랑스 CAC 40'], ['.AEX', '네덜란드 AEX'], ['.IBEX', '스페인 IBEX 35'], ['.FTMIB', '이탈리아 FTSE MIB'], ['.OMXS30', '스웨덴 OMXS 30'], ['.BFX', '벨기에 BEL 20'], ['.PSI20', '포르투갈 PSI 20'], ['.ISEQ', '아일랜드 ISEQ'], ['.BUX', '헝가리 BUX']] },
    { key: 'asia', name: '아시아·태평양', src: 'worldstock/index', items: [['.N225', '니케이 225'], ['.TOPX', '토픽스'], ['.SSEC', '상해종합'], ['.SZSC', '심천종합'], ['.CSI300', 'CSI 300'], ['.HSI', '항셍'], ['.HSCE', '홍콩H'], ['.TWII', '대만 가권'], ['.BSESN', '인도 SENSEX'], ['.VNI', '호치민 VN'], ['.HNXI', '하노이 HNX'], ['.AXJO', '호주 ASX 200'], ['.JKSE', '인도네시아 IDX'], ['.KLSE', '말레이시아 KLCI']] },
    { key: 'am', name: '중남미', src: 'worldstock/index', items: [['.BVSP', '브라질 BOVESPA'], ['.MXX', '멕시코 IPC']] },
    { key: 'kr', name: '한국 (비교용)', src: 'domestic/index', items: [['KOSPI', '코스피'], ['KOSDAQ', '코스닥']] },
    { key: 'ref', name: '참고', src: 'worldstock/index', items: [['.VIX', 'VIX 변동성', { ref: true }]] },
  ],
  commodity: [
    { key: 'energy', name: '에너지', src: 'marketindex/energy', items: [['CLcv1', 'WTI'], ['LCOcv1', '브렌트유'], ['NGcv1', '천연가스'], ['RBcv1', 'RBOB 가솔린'], ['HOcv1', '난방유']] },
    { key: 'metals', name: '금속', src: 'marketindex/metals', items: [['GCcv1', '금'], ['SIcv1', '은'], ['HGcv1', '구리'], ['PLcv1', '백금'], ['PAcv1', '팔라듐']] },
    { key: 'agri', name: '농산물', src: 'marketindex/agricultural', items: [['Ccv1', '옥수수'], ['Scv1', '대두'], ['Wcv1', '소맥'], ['KCcv1', '커피'], ['SBcv1', '설탕'], ['CCcv1', '코코아'], ['CTcv1', '면화']] },
  ],
};
const WORLD_BY_KEY = new Map();
for (const kind of Object.keys(WORLD_CFG)) for (const g of WORLD_CFG[kind]) for (const [code, name, extra] of g.items) WORLD_BY_KEY.set(code.replace(/^\./, ''), { key: code.replace(/^\./, ''), code, name, src: g.src, ref: !!(extra && extra.ref) });
async function getWorld(kind) {
  const groups = WORLD_CFG[kind];
  const bySrc = new Map();
  for (const g of groups) { const a = bySrc.get(g.src) || bySrc.set(g.src, []).get(g.src); for (const it of g.items) if (!a.includes(it[0])) a.push(it[0]); }
  const got = new Map();                                              // src → Map(code → raw)
  await Promise.all([...bySrc].map(async ([src, codes]) => {
    try {
      const r = await naver(`${POLL}${src}/${codes.join(',')}`);
      const mm = new Map();
      for (const x of r.datas || []) mm.set(x.reutersCode || x.itemCode, x);
      got.set(src, mm);
    } catch (_) { /* this source is dropped, the rest is returned */ }
  }));
  const out = [];
  for (const g of groups) {
    const mm = got.get(g.src);
    if (!mm) continue;
    const items = [];
    for (const [code, name, extra] of g.items) {
      const x = mm.get(code);
      if (!x) continue;
      const value = pn(x.closePriceRaw != null && x.closePriceRaw !== '' ? x.closePriceRaw : x.closePrice);
      if (value == null) continue;
      const dir = x.compareToPreviousPrice || x.fluctuationsType;
      const ex = x.stockExchangeType || {};
      const it = {
        key: code.replace(/^\./, ''), name, value,
        change: sgn(x.compareToPreviousClosePriceRaw != null && x.compareToPreviousClosePriceRaw !== '' ? x.compareToPreviousClosePriceRaw : (x.compareToPreviousClosePrice != null ? x.compareToPreviousClosePrice : x.fluctuations), dir) ?? 0,
        ratio: sgn(x.fluctuationsRatioRaw != null && x.fluctuationsRatioRaw !== '' ? x.fluctuationsRatioRaw : x.fluctuationsRatio, dir) ?? 0,
        status: x.marketStatus === 'OPEN' ? 'OPEN' : 'CLOSE',
        tradedAt: x.localTradedAt || null,
      };
      if (ex.delayTime > 0) it.delayed = ex.delayTime;
      if (x.unit) it.unit = x.unit;
      if (ex.zoneId) it.tz = ex.zoneId;
      if (extra && extra.ref) it.ref = true;
      items.push(it);
    }
    if (items.length) out.push({ key: g.key, name: g.name, items });
  }
  if (!out.length) throw new Error('world: every source failed');
  return { asOf: new Date().toISOString(), kind, groups: out };
}
// Daily closes only: Naver has no intraday source for foreign indices / commodities (chart/foreign/*/minute* answer []).
async function getWorldChart(item, tf) {
  const from = tf === '3m' ? kstDaysAgo(0, 3) : kstDaysAgo(0, 0, 1);
  const cutoff = ymd(from);
  let rows;
  if (item.src.startsWith('marketindex/')) {
    const cat = item.src.split('/')[1];
    const pages = await Promise.all(Array.from({ length: tf === '3m' ? 2 : 5 }, (_, i) => naver(`https://api.stock.naver.com/marketindex/${cat}/${item.code}/prices?page=${i + 1}&pageSize=60`).catch(e => { if (i === 0) throw e; return []; })));
    rows = pages.flat().map(r => ({ d: String(r.localTradedAt || '').slice(0, 10).replace(/-/g, ''), c: pn(r.closePrice) }));
  } else {
    const kindPath = item.src === 'worldstock/futures' ? 'foreign/futures' : item.src === 'domestic/index' ? 'domestic/index' : 'foreign/index';
    const raw = await naver(`https://api.stock.naver.com/chart/${kindPath}/${item.code}/day?startDateTime=${cutoff}000000&endDateTime=${ymd(kstNow())}235959`);
    rows = (Array.isArray(raw) ? raw : []).map(r => ({ d: String(r.localDate), c: pn(r.closePrice) }));
  }
  const seen = new Set(), bars = [];
  for (const r of rows.sort((a, b) => a.d.localeCompare(b.d))) {
    if (r.d < cutoff || r.c == null || seen.has(r.d) || !/^\d{8}$/.test(r.d)) continue;
    seen.add(r.d);
    bars.push({ t: dash(r.d), c: r.c });
  }
  return { key: item.key, tf, bars };
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
  // The daily chart is split-adjusted whatever Naver's /integration answers to this egress → 52-week range comes from it.
  const [b, g, days, poll] = await Promise.all([
    naver(`https://m.stock.naver.com/api/stock/${code}/basic`),
    naver(`https://m.stock.naver.com/api/stock/${code}/integration`),
    naver(`https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${ymd(kstDaysAgo(7, 0, 1))}000000&endDateTime=${ymd(kstNow())}235959`).catch(() => null),
    naver(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`).catch(() => null),   // /basic's overMarketPriceInfo has no volume
  ]);
  let hi = null, lo = null;
  const cut = ymd(kstDaysAgo(364));
  for (const r of Array.isArray(days) ? days : []) {
    if (String(r.localDate) < cut) continue;
    const h = pn(r.highPrice), l = pn(r.lowPrice);
    if (h != null && (hi == null || h > hi)) hi = h;
    if (l != null && l > 0 && (lo == null || l < lo)) lo = l;
  }
  const fromChart = hi != null && lo != null;
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
    high52: fromChart ? hi : pn(t.highPriceOf52WeeksAdjusted ?? t.highPriceOf52Weeks),     // fallback: integration values (adjusted when Naver provides them)
    low52: fromChart ? lo : pn(t.lowPriceOf52WeeksAdjusted ?? t.lowPriceOf52Weeks),
    range52: fromChart ? 'chart' : 'naver',
    marketCap: parseEok(t.marketValue),
    foreignRate: pn(t.foreignRate),
    asOf: b.localTradedAt || null,
    open: pn(t.openPrice),
    high: pn(t.highPrice),
    low: pn(t.lowPrice),
    prevClose: pn(t.lastClosePrice),
    volume: pn(t.accumulatedTradingVolume),
    tradingValue: parseEok(t.accumulatedTradingValue),
    cnsPer: pn(t.cnsPer),
    cnsEps: pn(t.cnsEps),
    dps: pn(t.dividend),
    peers: peersOf(g, b.itemCode || code),
    nxt: nxtOf((poll && poll.datas && poll.datas[0] && poll.datas[0].overMarketPriceInfo) || b.overMarketPriceInfo),
  };
}

// 같은 업종 비교: marketValue is in 백만원 (SK하이닉스 "814,498,986" = 814조 → 억원 = ÷100)
function peersOf(g, self) {
  const out = [];
  for (const x of g.industryCompareInfo || []) {
    if (!x || x.itemCode === self || !x.itemCode) continue;
    const mv = pn(x.marketValue);
    out.push({
      code: x.itemCode,
      name: x.stockName || null,
      market: x.sosok === '1' ? 'Q' : 'K',
      price: pn(x.closePrice),
      ratio: sgn(x.fluctuationsRatio, x.compareToPreviousPrice),
      cap: mv == null ? null : Math.round(mv / 100),
    });
    if (out.length >= 6) break;
  }
  return out;
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



/* ── shared parsing ─────────────────────────────── */
// signed change / ratio: trust the sign in the string, fall back on the direction object (code 4/5 = down, 1/2 = up)
const sgn = (v, dir) => {
  const n = pn(v);
  if (n == null) return null;
  const code = dir && String(dir.code != null ? dir.code : '');
  return (code === '4' || code === '5') ? -Math.abs(n) : (code === '1' || code === '2') ? Math.abs(n) : n;
};
const ENTITIES = { quot: '"', amp: '&', lt: '<', gt: '>', apos: "'", nbsp: ' ', lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”', hellip: '…', middot: '·' };
function decodeEntities(str) {
  return String(str == null ? '' : str).replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (all, e) => {
    if (e[0] === '#') {
      const cp = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      try { return String.fromCodePoint(cp); } catch (_) { return all; }
    }
    const v = ENTITIES[e.toLowerCase()];
    return v == null ? all : v;
  });
}

/* ── /api/themes ─────────────────────────────── */
// Naver's theme list is sorted by the live change rate, so rows can slip across page boundaries between calls.
// Fetch the 3 pages in parallel, union by id, and re-walk (at most twice) until totalCount unique themes are in.
async function getThemes() {
  const byNo = new Map();
  let total = 0;
  const walk = async (pages) => {
    const res = await Promise.all(pages.map(pg => naver(`https://m.stock.naver.com/api/stocks/theme?page=${pg}&pageSize=100`)));
    for (const r of res) {
      total = Math.max(total, r.totalCount || 0);
      for (const g of r.groups || []) byNo.set(g.no, g);
    }
  };
  await walk([1, 2, 3]);
  for (let k = 0; k < 2 && byNo.size < total; k++) await walk([1, 2, 3]);
  const themes = [...byNo.values()].map(g => ({
    id: g.no,
    name: g.name,
    ratio: pn(g.changeRate),
    up: g.riseCount == null ? null : +g.riseCount,
    flat: g.steadyCount == null ? null : +g.steadyCount,
    down: g.fallCount == null ? null : +g.fallCount,
  }));
  if (!themes.length) throw new Error('themes empty');
  return { asOf: new Date().toISOString(), themes };
}

/* ── /api/market ─────────────────────────────── */
// 9 upstream calls. Every item is independent: a failing one is dropped, the rest is returned.
async function getMarket() {
  const j = u => naver(u);
  const idxP = j('https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ');
  const sparkP = code => j(`https://api.stock.naver.com/chart/domestic/index/${code}/minute5`).then(rows => {
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) return null;
    const day = String(list[list.length - 1].localDateTime).slice(0, 8);
    return list.filter(r => String(r.localDateTime).startsWith(day) && String(r.localDateTime).slice(8, 12) <= '1530')
      .map(r => [kstSec(String(r.localDateTime)), pn(r.currentPrice)]);
  }).catch(() => null);
  const kosS = sparkP('KOSPI'), kqS = sparkP('KOSDAQ');
  const fxP = j('https://api.stock.naver.com/marketindex/exchange/FX_USDKRW');
  const futP = j('https://polling.finance.naver.com/api/realtime/worldstock/futures/EScv1,NQcv1');
  const enP = j('https://polling.finance.naver.com/api/realtime/marketindex/energy/CLcv1');
  const meP = j('https://polling.finance.naver.com/api/realtime/marketindex/metals/GCcv1');
  const btcP = j('https://m.stock.naver.com/front-api/cryptoEnd/detail?nfTicker=BTC&exchangeType=UPBIT');
  const delay = x => { const d = x && x.stockExchangeType && x.stockExchangeType.delayTime; return d > 0 ? d : undefined; };
  const out = {};
  let session = null;
  const put = (key, name, value, change, ratio, extra) => {
    if (value == null || !Number.isFinite(value)) return;
    out[key] = Object.assign({ key, name, value, change: change == null ? 0 : change, ratio: ratio == null ? 0 : ratio }, extra || {});
  };
  const settle = async (p, fn) => { try { fn(await p); } catch (_) { /* drop this item */ } };
  await Promise.all([
    settle(Promise.all([idxP, kosS, kqS]), ([idx, a, b]) => {
      const sp = { KOSPI: a, KOSDAQ: b };
      for (const x of idx.datas || []) {
        const se = x.stockExchangeType;
        if (!session && se && /^\d{4}$/.test(se.startTime) && /^\d{4}$/.test(se.endTime)) session = { start: se.startTime, end: se.endTime };
        if (x.itemCode !== 'KOSPI' && x.itemCode !== 'KOSDAQ') continue;
        const ex = sp[x.itemCode] && sp[x.itemCode].length ? { spark: sp[x.itemCode] } : {};
        put(x.itemCode, x.stockName, pn(x.closePriceRaw), sgn(x.compareToPreviousClosePriceRaw, x.compareToPreviousPrice), sgn(x.fluctuationsRatioRaw, x.compareToPreviousPrice), ex);
      }
    }),
    settle(fxP, r => { const x = r.exchangeInfo; put('USDKRW', '원/달러', pn(x.closePrice), sgn(x.fluctuations, x.fluctuationsType), sgn(x.fluctuationsRatio, x.fluctuationsType)); }),
    settle(futP, r => {
      const names = { EScv1: ['SPX_F', 'S&P 500 선물'], NQcv1: ['NDX_F', '나스닥 100 선물'] };
      for (const x of r.datas || []) {
        const k = names[x.reutersCode];
        if (k) put(k[0], k[1], pn(x.closePriceRaw), sgn(x.compareToPreviousClosePriceRaw, x.compareToPreviousPrice), sgn(x.fluctuationsRatioRaw, x.compareToPreviousPrice), { delayed: delay(x) || 10 });
      }
    }),
    settle(enP, r => { const x = (r.datas || [])[0]; put('WTI', 'WTI', pn(x.closePriceRaw || x.closePrice), sgn(x.fluctuations, x.fluctuationsType), sgn(x.fluctuationsRatio, x.fluctuationsType), { delayed: delay(x) }); }),
    settle(meP, r => { const x = (r.datas || [])[0]; put('GOLD', '국제 금', pn(x.closePriceRaw || x.closePrice), sgn(x.fluctuations, x.fluctuationsType), sgn(x.fluctuationsRatio, x.fluctuationsType), { delayed: delay(x) }); }),
    settle(btcP, r => { const x = r.result; put('BTC', '비트코인', pn(x.currentPrice), sgn(x.fluctuations, { code: x.fluctuationsType === 'FALLING' ? 5 : x.fluctuationsType === 'RISING' ? 2 : '' }), sgn(x.fluctuationsRatio, { code: x.fluctuationsType === 'FALLING' ? 5 : x.fluctuationsType === 'RISING' ? 2 : '' })); }),
  ]);
  const items = ['KOSPI', 'KOSDAQ', 'USDKRW', 'SPX_F', 'NDX_F', 'WTI', 'GOLD', 'BTC'].filter(k => out[k]).map(k => out[k]);
  if (!items.length) throw new Error('market: every source failed');
  return session ? { asOf: new Date().toISOString(), items, session } : { asOf: new Date().toISOString(), items };
}

/* ── /api/stock/:code/news, /disclosures ─────────────────────────────── */
async function getNews(code) {
  const raw = await naver(`https://m.stock.naver.com/api/news/stock/${code}?pageSize=20`);
  const arts = (Array.isArray(raw) ? raw : []).flatMap(c => (c && c.items) || []);
  const rows = arts.map(a => {
    const d = String(a.datetime || '');
    return {
      title: decodeEntities(a.title || a.titleFull),
      press: a.officeName || null,
      datetime: /^\d{12}/.test(d) ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}T${d.slice(8, 10)}:${d.slice(10, 12)}:00+09:00` : null,
      url: a.mobileNewsUrl || (a.officeId && a.articleId ? `https://n.news.naver.com/mnews/article/${a.officeId}/${a.articleId}` : null),
    };
  });
  rows.sort((x, y) => (y.datetime || '').localeCompare(x.datetime || ''));
  return { rows: rows.slice(0, 20) };
}
// 공시: OpenDART when the DART_KEY secret is set and the stock has a corp_code (web/dart_corp.json),
// otherwise — or when DART fails — Naver's feed (which also carries KRX market notices).
async function getDisclosures(code, env) {
  if (env && env.DART_KEY) {
    try {
      const corp = (await getDartCorp(env)).get(code);
      if (corp) return await getDartList(corp, env.DART_KEY);
    } catch (e) { /* fall back to Naver */ }
  }
  const raw = await naver(`https://m.stock.naver.com/api/stock/${code}/disclosure?pageSize=20`);
  const rows = (Array.isArray(raw) ? raw : []).map(r => {
    const d = String(r.datetime || '');
    return {
      title: decodeEntities(r.title),
      datetime: d ? (/[zZ]|[+-]\d\d:?\d\d$/.test(d) ? d : d + '+09:00') : null,
      url: `https://m.stock.naver.com/domestic/stock/${code}/notice/${r.disclosureId}`,
    };
  });
  rows.sort((x, y) => (y.datetime || '').localeCompare(x.datetime || ''));
  return { source: 'naver', rows: rows.slice(0, 20) };
}
let dartCorpMem = null;
async function getDartCorp(env) {
  if (dartCorpMem && Date.now() - dartCorpMem.at < 6 * 3600e3) return dartCorpMem.map;
  const r = await fetch(assetBase(env) + 'dart_corp.json');
  if (!r.ok) throw new Error('dart_corp ' + r.status);
  const j = await r.json();                                   // {"005930":"00126380", …}
  dartCorpMem = { at: Date.now(), map: new Map(Object.entries(j.map || j)) };
  return dartCorpMem.map;
}
// 공시 종류 (report_nm 기준): 정기 · 실적 · 주요 · 지분 · 기타
function dartKind(name) {
  const n = String(name || '');
  if (/사업보고서|반기보고서|분기보고서/.test(n)) return '정기';
  if (/실적|손익구조|매출액/.test(n)) return '실적';
  if (/소유상황보고서|대량보유|최대주주등소유주식|특정증권등/.test(n)) return '지분';
  if (/주요사항|단일판매|공급계약|유상증자|무상증자|감자|자기주식|합병|분할|전환사채|신주인수권|교환사채|배당|최대주주변경|소송|영업정지|타법인주식|유형자산|투자판단|조회공시|상장/.test(n)) return '주요';
  return '기타';
}
// DART remarks (rm): 유=유가증권시장본부 소관, 코=코스닥, 채=채권상장, 넥=코넥스, 공=공정위, 연=연결, 정=정정, 철=철회
async function getDartList(corp, key) {
  const from = ymd(kstDaysAgo(0, 6));
  const u = `https://opendart.fss.or.kr/api/list.json?crtfc_key=${encodeURIComponent(key)}&corp_code=${corp}&bgn_de=${from}&page_count=40&sort=date&sort_mth=desc`;
  const r = await fetch(u, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (!r.ok) throw new Error('dart ' + r.status);
  const j = await r.json();
  if (j.status === '013') return { source: 'dart', rows: [] };          // no filings in range
  if (j.status !== '000') throw new Error('dart status ' + j.status);
  const rows = (j.list || []).map(x => ({
    title: String(x.report_nm || '').replace(/\s+/g, ' ').trim(),
    kind: dartKind(x.report_nm),
    datetime: null,
    date: /^\d{8}$/.test(x.rcept_dt) ? dash(x.rcept_dt) : null,
    filer: x.flr_nm || null,
    note: x.rm || '',
    url: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${x.rcept_no}`,
  }));
  return { source: 'dart', rows };
}

/* ── /api/stock/:code/finance, /research ─────────────────────────────── */
const FIN_UNIT = {
  '매출액': '억원', '영업이익': '억원', '당기순이익': '억원', '지배주주순이익': '억원', '비지배주주순이익': '억원',
  '영업이익률': '%', '순이익률': '%', 'ROE': '%', '부채비율': '%', '당좌비율': '%', '유보율': '%',
  'EPS': '원', 'BPS': '원', '주당배당금': '원', 'PER': '배', 'PBR': '배',
};
async function getFinance(code, period) {
  const raw = await naver(`https://m.stock.naver.com/api/stock/${code}/finance/${period}`);
  const fi = (raw && raw.financeInfo) || {};
  const cols = (fi.trTitleList || []).map(c => ({ key: String(c.key), label: String(c.title || c.key).replace(/\.$/, ''), estimate: c.isConsensus === 'Y' }));
  cols.sort((a, b) => a.key.localeCompare(b.key));              // oldest → newest
  const rows = (fi.rowList || []).map(r => ({
    title: r.title,
    unit: FIN_UNIT[r.title] || null,
    values: cols.map(c => { const x = r.columns && r.columns[c.key]; return x ? pn(x.value) : null; }),
  }));
  if (!cols.length && !rows.length) throw new HttpError(404, '종목을 찾을 수 없어요');   // unknown code answers 200 with empty lists
  return { period, cols, rows };
}

// "목표주가 37만원", "목표주가를 40만원으로", "TP 40만원", "목표가 472,000원", "목표주가를 35만원에서 40만원으로 상향" (→ the new one)
const TARGET_RE = /(?:목표\s*주가|목표\s*가|목표\s*주가\s*는|\bTP\b|\bTarget\s*Price\b)\s*[:：]?\s*(?:[을를은는]\s*)?(?:약\s*)?(\d[\d,]*(?:\.\d+)?)\s*(만\s*원|원)/gi;
const MONEY_RE = /^\s*에서\s*(?:약\s*)?(\d[\d,]*(?:\.\d+)?)\s*(만\s*원|원)/;
function toWon(num, unit) {
  const n = parseFloat(String(num).replace(/,/g, ''));
  if (!Number.isFinite(n)) return null;
  const won = /만/.test(unit) ? Math.round(n * 10000) : Math.round(n);
  return won >= 1000 && won <= 10000000 ? won : null;           // not sure → null
}
function parseTarget(text) {
  const t = String(text || '');
  TARGET_RE.lastIndex = 0;
  let m;
  while ((m = TARGET_RE.exec(t))) {
    let w = toWon(m[1], m[2]);
    const next = MONEY_RE.exec(t.slice(m.index + m[0].length));
    if (next) w = toWon(next[1], next[2]) ?? w;
    if (w != null) return w;
  }
  return null;
}
const OPINION_TOK = 'Strong\\s*Buy|Trading\\s*Buy|Market\\s*perform|Outperform|Underperform|Buy|Hold|Neutral|Sell|매수|매도|중립';
const OPINION_CTX = new RegExp('(?:투자\\s*의견|의견|Rating)\\s*[:：]?\\s*(?:은|는|을|를)?\\s*[\'"‘“]?\\s*(' + OPINION_TOK + ')', 'i');
const OPINION_ANY = new RegExp('(?<![A-Za-z순])(' + OPINION_TOK + ')(?![A-Za-z])', 'i');
function parseOpinion(text) {
  const t = String(text || '');
  const m = OPINION_CTX.exec(t) || OPINION_ANY.exec(t);
  return m ? m[1].replace(/\s+/g, ' ').trim() : null;
}
async function getResearch(code) {
  const [list, g] = await Promise.all([
    naver(`https://m.stock.naver.com/api/research/stock/${code}?pageSize=20`),
    naver(`https://m.stock.naver.com/api/stock/${code}/integration`).catch(e => { if (e && e.status === 404) throw e; return null; }),
  ]);
  const ci = g && g.consensusInfo;
  const tm = ci ? pn(ci.priceTargetMean) : null, om = ci ? pn(ci.recommMean) : null;
  const consensus = ci && (tm != null || om != null) ? { targetMean: tm, opinionMean: om, date: ci.createDate || null } : null;
  const rows = (Array.isArray(list) ? list : []).map(r => ({
    date: r.writeDate || null,
    broker: r.brokerName || null,
    title: decodeEntities(r.title),
    target: parseTarget(r.previewContent),
    opinion: parseOpinion(r.previewContent),
    url: `https://m.stock.naver.com/research/company/${r.researchId}`,
  }));
  return { consensus, rows };
}

/* ── static assets (whitelist, binary-safe) ─────────────────────────────── */
const JSON_T = 'application/json; charset=utf-8';
const ASSETS = {
  '/data/themes.json': { file: 'themes.json', type: JSON_T, ttl: 600, cors: true },
  '/data/periods.json': { file: 'periods.json', type: JSON_T, ttl: 600, cors: true },
  '/data/flows.json': { file: 'flows.json', type: JSON_T, ttl: 600, cors: true },
  '/data/names.json': { file: 'names.json', type: JSON_T, ttl: 600, cors: true },
  '/data/close.json': { file: 'close.json', type: JSON_T, ttl: 600, cors: true },
  '/manifest.webmanifest': { file: 'manifest.webmanifest', type: 'application/manifest+json', ttl: 3600 },
  '/sw.js': { file: 'sw.js', type: 'text/javascript; charset=utf-8', ttl: 3600, extra: { 'service-worker-allowed': '/' } },
  '/icon.svg': { file: 'icon.svg', type: 'image/svg+xml', ttl: 3600 },
  '/icon-192.png': { file: 'icon-192.png', type: 'image/png', ttl: 3600 },
  '/icon-512.png': { file: 'icon-512.png', type: 'image/png', ttl: 3600 },
  '/apple-touch-icon.png': { file: 'apple-touch-icon.png', type: 'image/png', ttl: 3600 },
};
async function getAsset(request, env, ctx, path) {
  const spec = ASSETS[path];
  const cache = caches.default;
  const cacheKey = new Request(new URL('/__cache/asset-' + spec.file, request.url).toString());
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  const r = await fetch(assetBase(env) + spec.file);
  if (!r.ok) return fail(r.status === 404 ? 404 : 502, r.status === 404 ? '아직 만들어지지 않은 파일이에요' : '원본을 불러오지 못했어요');
  const headers = { 'content-type': spec.type, 'cache-control': `public, max-age=${spec.ttl}`, ...(spec.cors ? { 'access-control-allow-origin': ORIGIN } : {}), ...(spec.extra || {}) };
  const res = new Response(await r.arrayBuffer(), { headers });
  ctx.waitUntil(cache.put(cacheKey, res.clone()));
  return res;
}

/* ── intraday replay (KV env.REPLAY) ─────────────────────────────── */
// KV free plan: 1,000 list ops/day → this code never calls list().
// replay:days           → ["20261109", …] newest first, ≤ 40 (no TTL)
// replay:YYYYMMDD:codes → ["005930",…] (written with the day's first frame)
// replay:YYYYMMDD:HHMM  → {p:[int|null,…], r:[2-decimals|null,…], i:[KOSPI, KOSDAQ], b:[prev closes], e:'1530'}   (~10 KB each, TTL 40 days)
const REPLAY_TTL = 40 * 86400;
const DAYS_KEY = 'replay:days';
async function getReplayDates(env) {
  if (!env.REPLAY) throw new HttpError(503, '리플레이 저장소가 연결되지 않았어요');
  const days = await env.REPLAY.get(DAYS_KEY, 'json');
  return { dates: (Array.isArray(days) ? days : []).filter(d => /^\d{8}$/.test(d)).map(dash) };
}
// every 5-minute key of a day: 09:00 → 16:30 (the longest session end); keys past the real end simply don't exist
const FRAME_TS = (() => { const a = []; for (let m = 540; m <= 990; m += 5) a.push(pad(Math.floor(m / 60)) + pad(m % 60)); return a; })();
async function getReplay(env, date) {
  if (!env.REPLAY) throw new HttpError(503, '리플레이 저장소가 연결되지 않았어요');
  if (!date) {
    date = (await getReplayDates(env)).dates[0];
    if (!date) throw new HttpError(404, '기록된 날이 아직 없어요');
  }
  const day = date.replace(/-/g, '');
  const codes = await env.REPLAY.get(`replay:${day}:codes`, 'json');
  if (!codes) throw new HttpError(404, '그날 기록이 없어요');
  const vals = [];
  for (let i = 0; i < FRAME_TS.length; i += 20) vals.push(...await Promise.all(FRAME_TS.slice(i, i + 20).map(t => env.REPLAY.get(`replay:${day}:${t}`, 'json'))));
  const frames = [], ix = { KOSPI: [], KOSDAQ: [] };
  let base = null;                                                     // previous close of each index (from the first frame that has it)
  FRAME_TS.forEach((t, n) => {
    const f = vals[n];
    if (!f) return;
    frames.push({ t, p: f.p, r: f.r });
    ix.KOSPI.push(f.i ? f.i[0] : null);
    ix.KOSDAQ.push(f.i ? f.i[1] : null);
    if (!base && f.b) base = { KOSPI: f.b[0], KOSDAQ: f.b[1] };
  });
  return { date, codes, frames, index: ix, base };
}

// Cron entry. event.scheduledTime (ms) is the cron's nominal time; the dev harness passes a fake one.
// Outside 09:00–16:30 KST or on weekends it returns before touching KV or the network.
async function recordFrame(event, env) {
  if (!env.REPLAY) return { skipped: 'no-kv' };
  const at = new Date((event && event.scheduledTime) || Date.now());
  const k = new Date(at.getTime() + 9 * 3600e3);                       // KST wall clock via getUTC*
  const wd = k.getUTCDay(), mins = k.getUTCHours() * 60 + k.getUTCMinutes();
  if (wd < 1 || wd > 5 || mins < 540 || mins > 990) return { skipped: 'outside-hours' };
  const bucket = mins - (mins % 5);
  const t = pad(Math.floor(bucket / 60)) + pad(bucket % 60);
  const day = ymd(k), fkey = `replay:${day}:${t}`, ckey = `replay:${day}:codes`;
  if (await env.REPLAY.get(fkey)) return { skipped: 'duplicate', t };
  if (t > '1530') {                                                    // a normal day ended at 15:30: its frame says so → no fetch needed
    const f = await env.REPLAY.get(`replay:${day}:1530`, 'json');
    if (f && (f.e || '1530') <= '1530') return { skipped: 'after-end', t };
  }
  const { body: q, endTime } = await quotesCore(env);
  if (t > endTime) return { skipped: 'after-end', t };
  const closed = q.marketStatus.KOSPI !== 'OPEN' && q.marketStatus.KOSDAQ !== 'OPEN';
  // Holiday guard: both indices CLOSE. The last frame (endTime) is allowed when the data is stamped today (the close may already have flipped).
  if (closed && !(t === endTime && (q.asOf || '').slice(0, 10) === dash(day))) return { skipped: 'closed', t };
  let codes = await env.REPLAY.get(ckey, 'json');
  if (!codes) {
    codes = q.stocks.map(s => s.c);
    await env.REPLAY.put(ckey, JSON.stringify(codes), { expirationTtl: REPLAY_TTL });
  }
  const days = await env.REPLAY.get(DAYS_KEY, 'json');
  if (!Array.isArray(days) || !days.includes(day)) {
    const next = [...new Set([day, ...(Array.isArray(days) ? days : [])])].sort().reverse().slice(0, 40);
    await env.REPLAY.put(DAYS_KEY, JSON.stringify(next));
  }
  const by = new Map(q.stocks.map(s => [s.c, s]));
  const ix = x => (q.index[x] ? round2(q.index[x].value) : null);
  const bx = x => (q.index[x] ? round2(q.index[x].value - q.index[x].change) : null);
  await env.REPLAY.put(fkey, JSON.stringify({
    p: codes.map(c => (by.has(c) ? Math.round(by.get(c).p) : null)),
    r: codes.map(c => (by.has(c) ? round2(by.get(c).r) : null)),
    i: [ix('KOSPI'), ix('KOSDAQ')],
    b: [bx('KOSPI'), bx('KOSDAQ')],
    e: endTime,
  }), { expirationTtl: REPLAY_TTL });
  return { wrote: t };
}
