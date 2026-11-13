// 판세 실시간 갱신 시안 — Worker + Durable Object `MarketHub` (docs/standards/realtime.md §5). LOCAL ONLY: `npx wrangler dev`.
//
//   GET /                      → demo page (client.html): applies snap + deltas, flashes, 연결 상태 표시
//   GET /api/live?ch=top|all   → WebSocket (Upgrade only). Optional &epoch=…&ver=… = resume: missed deltas instead of a snapshot
//   GET /api/live/state?ch=…   → hub counters (JSON) — for the bench and the doc's numbers
//
// One hub per channel (`top` = universe K + Q top 300 each, `all` = every listed stock), placed in Asia-Pacific.
// The hub polls the Naver-shaped upstream on an alarm (3 s in the regular session), keeps the rows *as the clients hold
// them*, and broadcasts only the keys that changed. Outgoing WebSocket messages are free on Durable Objects; incoming ones
// are billed 20:1, so the client sends nothing in steady state.
import { DurableObject } from 'cloudflare:workers';
import CLIENT_HTML from './client.html';

const PROTO = 1;
const CHANNELS = {
  top: { pollMs: 3000 },          // the default map (600 rows)
  all: { pollMs: 5000 },          // 종목 수 전체 (~2,700 rows, 3 upstream chunks + index per tick)
};
const RING = 40;                  // deltas kept for resume (≈ 2 min at 3 s)
const SLOW_EVERY = 10;            // volume / value / cap / NXT time: every 10th tick (≈ 30 s) — env SLOW_EVERY overrides
// env PIGGYBACK = '1': a row that moved also carries its changed slow keys (fresher volume, ~2× bigger deltas — §8 table)
const HB_MS = 15000;              // a quiet stream still sends a heartbeat this often (the page's liveness check: 45 s)
const MAX_SOCKETS = 5000;         // beyond this the hub answers 503 and the page keeps polling
const POLL_MAX = 900;             // codes per upstream call (Naver: ≤ 1000)
const FAST = ['p', 'd', 'r', 'lim', 'op', 'hi', 'lo'];
const SLOW = ['cap', 'tv', 'v'];
const NX_FAST = ['p', 'd', 'r', 's', 'o', 'op', 'hi', 'lo'];
const NX_SLOW = ['v', 'tv', 't'];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/' || url.pathname === '/client.html') {
      return new Response(CLIENT_HTML, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
    }
    const ch = url.searchParams.get('ch') || 'top';
    if (url.pathname === '/api/live' || url.pathname === '/api/live/state') {
      if (!Object.prototype.hasOwnProperty.call(CHANNELS, ch)) return json({ error: 'ch는 top 또는 all이에요' }, 400);
      if (url.pathname === '/api/live/state') return json(await hub(env, ch).state());
      // validate here: an invalid request must not cost a Durable Object request
      if ((request.headers.get('upgrade') || '').toLowerCase() !== 'websocket') return json({ error: 'WebSocket 연결만 받아요' }, 426);
      const origin = request.headers.get('origin');
      if (origin && !allowedOrigin(origin, env)) return json({ error: '허용되지 않은 출처예요' }, 403);
      return hub(env, ch).fetch(request);
    }
    return new Response('Not found', { status: 404 });
  },
};

const hub = (env, ch) => env.MARKET.get(env.MARKET.idFromName(ch), { locationHint: 'apac' });
const allowedOrigin = (o, env) => String(env.ORIGINS || '').split(',').map(s => s.trim()).includes(o);
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });

export class MarketHub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ch = null;
    this.rows = null;             // Map code → row exactly as every client holds it (/api/quotes row shape)
    this.order = [];              // snapshot order (upstream order)
    this.meta = null;             // {asOf, source, marketStatus, afterHours, nxt, index}
    this.ver = 0;
    this.epoch = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);   // a new hub instance = a new epoch
    this.ring = [];               // [{v, text}] last RING deltas
    this.snap = null;             // {v, text}: one serialisation per version (a reconnect storm costs one stringify)
    this.tick = 0;
    this.lastSent = 0;
    this.backoff = 0;
    this.codes = null;            // {list, meta: Map code → {m, s, i}}
    this.stats = { polls: 0, fails: 0, upstreamMs: 0, cpuMs: 0, lastErr: null, lastBytes: 0, lastRows: 0, sent: 0, sentBytes: 0, snaps: 0, startedAt: Date.now() };
    // 'ping' → 'pong' without waking the object (the page does not need it; kept for manual checks)
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
  }

  // ── WebSocket upgrade (the Worker already checked Upgrade + Origin) ──
  async fetch(request) {
    const url = new URL(request.url);
    if (!this.ch) {
      this.ch = url.searchParams.get('ch') || 'top';
      await this.ctx.storage.put('ch', this.ch);        // an evicted hub's alarm must know its channel
    }
    if (this.ctx.getWebSockets().length >= MAX_SOCKETS) return new Response('busy', { status: 503 });
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ at: Date.now() });
    server.send(JSON.stringify(this.hello()));
    if (this.rows) {
      const ep = url.searchParams.get('epoch'), since = Number(url.searchParams.get('ver'));
      const missed = ep === this.epoch && since > 0 ? this.since(since) : null;
      if (missed) for (const t of missed) server.send(t);
      else this.sendSnap(server);
    }
    await this.wake();
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws, message) {
    // optional: {t:'resume', epoch, v} (same as the URL form) or {t:'snap'}. Anything else is ignored.
    let m = null;
    try { m = JSON.parse(typeof message === 'string' ? message : new TextDecoder().decode(message)); } catch (e) { return; }
    if (!m || !this.rows) return;
    if (m.t === 'resume') {
      const missed = m.epoch === this.epoch && m.v > 0 ? this.since(m.v) : null;
      if (missed) for (const t of missed) ws.send(t); else this.sendSnap(ws);
    } else if (m.t === 'snap') this.sendSnap(ws);
  }
  async webSocketClose() { /* auto-reply to Close is on (compat ≥ 2026-04-07); the alarm notices an empty room */ }
  async webSocketError() { }

  // ── the poll loop ──
  async wake() {
    const a = await this.ctx.storage.getAlarm();
    if (a == null) await this.ctx.storage.setAlarm(Date.now());
  }
  async alarm() {
    this.ch ??= (await this.ctx.storage.get('ch')) || 'top';
    if (!this.ctx.getWebSockets().length) return;       // nobody listening: stop (the next connection wakes the hub)
    const t0 = Date.now();
    let ok = true;
    try {
      const body = await this.poll();
      const c0 = Date.now();
      this.ingest(body);
      this.stats.cpuMs = Date.now() - c0;               // wall time of diff + broadcast (Date.now only advances across I/O in production)
      this.backoff = 0;
    } catch (e) {
      ok = false;
      this.stats.fails++;
      this.stats.lastErr = String((e && e.message) || e).slice(0, 200);
      this.backoff = Math.min(30000, Math.max(this.pollMs() * 2, this.backoff * 2));
      this.broadcast(JSON.stringify({ t: 'st', ok: false, msg: '시세를 받지 못했어요', retryMs: this.backoff, at: Date.now() }));
    }
    await this.ctx.storage.setAlarm(Math.max(t0 + (ok ? this.pollMs() : this.backoff), Date.now() + 250));
  }
  // KST phase → interval. Regular session: the channel's interval; NXT-only hours: ≥ 5 s; closed: 60 s.
  phase() {
    if (this.env.FORCE_LIVE === '1') return 'live';
    const k = new Date(Date.now() + 9 * 3600e3), wd = k.getUTCDay(), hm = k.getUTCHours() * 100 + k.getUTCMinutes();
    if (wd === 0 || wd === 6) return 'closed';
    if (hm >= 900 && hm < 1530) return 'live';
    if ((hm >= 800 && hm < 900) || (hm >= 1530 && hm < 2000)) return 'nxt';
    return 'closed';
  }
  pollMs() {
    const base = Number(this.env.POLL_MS) || CHANNELS[this.ch || 'top'].pollMs;
    const ph = this.phase();
    return ph === 'live' ? base : ph === 'nxt' ? Math.max(base, 5000) : 60000;
  }

  // ── upstream (Naver shape) → /api/quotes body ──
  async poll() {
    const up = this.env.UPSTREAM;
    if (!this.codes) {
      const r = await fetch(`${up}/__codes?ch=${this.ch}`);
      if (!r.ok) throw new Error('codes ' + r.status);
      const j = await r.json();
      this.codes = { list: j.codes, meta: new Map(Object.entries(j.meta)) };
    }
    const list = this.codes.list, n = Math.max(1, Math.ceil(list.length / POLL_MAX)), size = Math.ceil(list.length / n);
    const get = async u => { const r = await fetch(u, { headers: { accept: 'application/json' } }); if (!r.ok) throw new Error(`upstream ${r.status}`); return r.json(); };
    const t0 = Date.now();
    const [chunks, idx] = await Promise.all([
      Promise.all(Array.from({ length: n }, (_, k) => get(`${up}/api/realtime/domestic/stock/${list.slice(k * size, (k + 1) * size).join(',')}`))),
      get(`${up}/api/realtime/domestic/index/KOSPI,KOSDAQ`).catch(() => null),
    ]);
    this.stats.upstreamMs = Date.now() - t0;
    this.stats.polls++;
    return quotesBody(chunks.flatMap(c => (c && c.datas) || []), idx, this.codes.meta);
  }

  ingest(body) {
    const slow = this.tick++ % (Number(this.env.SLOW_EVERY) || SLOW_EVERY) === 0, pig = this.env.PIGGYBACK === '1';
    const now = Date.now();
    if (!this.rows) {                                     // first data of this instance: everyone gets a snapshot
      this.rows = new Map(body.stocks.map(r => [r.c, structuredClone(r)]));
      this.order = body.stocks.map(r => r.c);
      this.meta = metaOf(body);
      this.ver = 1;
      this.ring = [];
      for (const ws of this.ctx.getWebSockets()) this.sendSnap(ws);
      return;
    }
    const rows = [];
    for (const n of body.stocks) {
      const o = this.rows.get(n.c);
      if (!o) { const c = structuredClone(n); this.rows.set(n.c, c); this.order.push(n.c); rows.push(c); continue; }
      const p = diffRow(o, n, slow, pig);
      if (p) { applyPatch(o, p); rows.push(p); }
    }
    const m = metaOf(body), extra = {};
    if (!same(m.index, this.meta.index)) extra.ix = m.index;
    if (!same(m.marketStatus, this.meta.marketStatus)) extra.ms = m.marketStatus;
    if (m.afterHours !== this.meta.afterHours) extra.ah = m.afterHours;
    if (!same(m.nxt, this.meta.nxt)) extra.nxt = m.nxt;
    this.meta = m;
    if (!rows.length && !Object.keys(extra).length) {
      if (now - this.lastSent >= HB_MS) this.broadcast(JSON.stringify({ t: 'hb', v: this.ver, at: now, asOf: m.asOf }));
      return;
    }
    const text = JSON.stringify({ t: 'd', v: this.ver + 1, b: this.ver, at: now, asOf: m.asOf, rows, ...extra });
    this.ver++;
    this.ring.push({ v: this.ver, text });
    if (this.ring.length > RING) this.ring.shift();
    this.stats.lastBytes = text.length;
    this.stats.lastRows = rows.length;
    this.broadcast(text);
  }

  // texts of the deltas after version v, or null when they are no longer all in the ring
  since(v) {
    if (v === this.ver) return [];
    const i = this.ring.findIndex(x => x.v === v + 1);
    return i < 0 ? null : this.ring.slice(i).map(x => x.text);
  }
  hello() {
    return { t: 'hello', proto: PROTO, ch: this.ch, epoch: this.epoch, v: this.ver, poll: this.pollMs(), phase: this.phase(), now: Date.now() };
  }
  sendSnap(ws) {
    if (!this.snap || this.snap.v !== this.ver) {
      this.snap = { v: this.ver, text: JSON.stringify({ t: 'snap', ch: this.ch, epoch: this.epoch, v: this.ver, at: Date.now(), body: { ...this.meta, stocks: this.order.map(c => this.rows.get(c)) } }) };
    }
    this.stats.snaps++;
    try { ws.send(this.snap.text); } catch (e) { try { ws.close(1011, 'send failed'); } catch (_) { } }
  }
  broadcast(text) {
    let n = 0;
    for (const ws of this.ctx.getWebSockets()) {
      try { ws.send(text); n++; } catch (e) { try { ws.close(1011, 'send failed'); } catch (_) { } }
    }
    this.lastSent = Date.now();
    this.stats.sent += n;
    this.stats.sentBytes += n * text.length;
  }
  async state() {
    this.ch ??= (await this.ctx.storage.get('ch')) || null;
    return { ch: this.ch, epoch: this.epoch, v: this.ver, sockets: this.ctx.getWebSockets().length, rows: this.rows ? this.rows.size : 0, phase: this.phase(), pollMs: this.pollMs(), alarm: await this.ctx.storage.getAlarm(), ...this.stats };
  }
}

/* ── delta rules (the page's applyPatch must stay identical: realtime.md §5-3) ── */
// patch = {c, …only the keys that changed}; null = key removed; nx is merged key by key (null = NXT gone).
// FAST keys every tick; SLOW keys every SLOW_EVERY-th tick (and, with pig, together with a row that moved anyway).
export function diffRow(o, n, slow, pig = false) {
  let p = null;
  const put = (k, v) => { (p ||= { c: n.c })[k] = v === undefined ? null : v; };
  for (const k of FAST) if (o[k] !== n[k]) put(k, n[k]);
  const on = o.nx || null, nn = n.nx || null;
  if (!on || !nn) { if (on !== nn) put('nx', nn); }
  else {
    let q = null;
    for (const k of NX_FAST) if (on[k] !== nn[k]) (q ||= {})[k] = nn[k] === undefined ? null : nn[k];
    if (slow || (pig && (q || p))) for (const k of NX_SLOW) if (on[k] !== nn[k]) (q ||= {})[k] = nn[k] === undefined ? null : nn[k];
    if (q) put('nx', q);
  }
  if (slow || (pig && p)) for (const k of SLOW) if (o[k] !== n[k]) put(k, n[k]);
  return p;
}
export function applyPatch(row, p) {
  for (const k in p) {
    if (k === 'c') continue;
    const v = p[k];
    if (k === 'nx') {
      if (v === null) delete row.nx;
      else { const nx = row.nx || (row.nx = {}); for (const j in v) { if (v[j] === null) delete nx[j]; else nx[j] = v[j]; } }
    } else if (v === null) delete row[k];
    else row[k] = v;
  }
  return row;
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const metaOf = b => ({ asOf: b.asOf, source: b.source, marketStatus: b.marketStatus, afterHours: b.afterHours, nxt: b.nxt, index: b.index });

/* ── Naver polling rows → /api/quotes rows (same rules as worker/src/index.js quotesCore / nxtOf / ohlcInto) ── */
const num = v => { if (v == null) return 0; const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/,/g, '')); return Number.isFinite(n) ? n : 0; };
const pn = v => { if (v == null) return null; if (typeof v === 'number') return Number.isFinite(v) ? v : null; const m = String(v).replace(/,/g, '').match(/[-+]?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null; };
const sgn = (v, dir) => { const n = pn(v); if (n == null) return null; const c = dir && String(dir.code != null ? dir.code : ''); return (c === '4' || c === '5') ? -Math.abs(n) : (c === '1' || c === '2') ? Math.abs(n) : n; };
function parseEok(v) { if (v == null) return null; const s = String(v).replace(/,/g, ''); const jo = s.match(/(\d+)\s*조/), eok = s.match(/(\d+)\s*억/); if (!jo && !eok) return pn(s) == null ? null : Math.round(pn(s) / 1e8); return (jo ? +jo[1] * 10000 : 0) + (eok ? +eok[1] : 0); }
function ohlcInto(row, op, hi, lo) { if (op > 0 && hi > 0 && lo > 0 && lo <= hi) { row.op = op; row.hi = hi; row.lo = lo; } }
function nxtOf(i) {
  if (!i || i.overPrice == null || i.overPrice === '') return null;
  const st = i.tradingSessionType === 'PRE_MARKET' ? 'pre' : i.tradingSessionType === 'AFTER_MARKET' ? 'after' : i.tradingSessionType === 'REGULAR_MARKET' ? 'reg' : null;
  const ts = i.tradeStopType && i.tradeStopType.name;
  if (!st || (ts && ts !== 'TRADING')) return null;
  const p = pn(i.overPrice);
  if (p == null) return null;
  const x = { p, d: sgn(i.compareToPreviousClosePrice, i.compareToPreviousPrice) ?? 0, r: sgn(i.fluctuationsRatio, i.compareToPreviousPrice) ?? 0, s: st, o: i.overMarketStatus === 'OPEN' ? 1 : 0, t: i.localTradedAt || null, v: pn(i.accumulatedTradingVolumeRaw ?? i.accumulatedTradingVolume), tv: i.accumulatedTradingValueRaw != null && i.accumulatedTradingValueRaw !== '' ? Math.round(num(i.accumulatedTradingValueRaw) / 1e8) : parseEok(i.accumulatedTradingValue) };
  ohlcInto(x, pn(i.openPrice), pn(i.highPrice), pn(i.lowPrice));
  return x;
}
function quotesBody(datas, idx, meta) {
  const stocks = [];
  let asOf = '', stockOpen = false, nxOpen = '', nxSess = '';
  for (const s of datas) {
    const mt = meta.get(s.itemCode) || { m: 'K', s: '기타', i: '기타' };
    if (s.marketStatus === 'OPEN') stockOpen = true;
    if (s.localTradedAt && s.localTradedAt > asOf) asOf = s.localTradedAt;
    const lim = s.compareToPreviousPrice && s.compareToPreviousPrice.name;
    const row = { c: s.itemCode, n: s.stockName, m: mt.m, s: mt.s, i: mt.i, cap: Math.round(num(s.marketValueFullRaw) / 1e8), p: num(s.closePriceRaw), d: num(s.compareToPreviousClosePriceRaw), r: num(s.fluctuationsRatioRaw), tv: Math.round(num(s.accumulatedTradingValueRaw) / 1e8), v: num(s.accumulatedTradingVolumeRaw) };
    ohlcInto(row, num(s.openPriceRaw), num(s.highPriceRaw), num(s.lowPriceRaw));
    if (lim === 'UPPER_LIMIT') row.lim = 1; else if (lim === 'LOWER_LIMIT') row.lim = -1;
    if (s.overMarketPriceInfo) { const nx = nxtOf(s.overMarketPriceInfo); if (nx) { row.nx = nx; if (nx.o) nxOpen = nx.s; else if (!nxSess) nxSess = nx.s; } }
    stocks.push(row);
  }
  const index = {}, marketStatus = {};
  for (const x of (idx && idx.datas) || []) {
    index[x.itemCode] = { value: num(x.closePriceRaw), change: num(x.compareToPreviousClosePriceRaw), ratio: num(x.fluctuationsRatioRaw) };
    marketStatus[x.itemCode] = x.marketStatus;
  }
  const regularOpen = Object.values(marketStatus).includes('OPEN');
  return { asOf, source: '네이버 증권 (polling.finance.naver.com)', marketStatus, afterHours: !regularOpen && stockOpen, nxt: { session: nxOpen || nxSess || null, open: !!nxOpen }, index, stocks };
}
