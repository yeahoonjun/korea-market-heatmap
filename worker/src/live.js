// 실시간 갱신 (로드맵 2번, AGENTS §3-23b · docs/standards/realtime.md): Durable Object 허브 `MarketHub` 하나가 정규장 동안
// 상위 600종목(코스피 300 + 코스닥 300 — /api/quotes와 같은 줄기)을 LIVE_POLL_MS마다 받아 바뀐 칸만 WebSocket으로 밀어 줘요.
// 페이지가 연결하지 못하거나 거절되면 지금의 10초 폴링이 그대로 대신해요.
//
//   GET /api/live[?ch=top][&epoch=…&ver=…]  WebSocket only. Refusals ({t:'off', reason, retryAt} then close 4003) come from the
//                                            Worker when it can (clock, kill switch, a refusal the hub gave recently in this data
//                                            center) so they cost no Durable Object request.
//   GET /api/live/state                      hub counters + budget guard (JSON, edge-cached 60 s per data center)
//
// Budget (user 2026-11-14: nothing beyond the $5 Workers Paid base): see live_core.js LIMITS and realtime.md §12. The hub keeps
// its counters in its own storage (no KV writes); the Worker remembers refusals in the Cache API (free); the only KV access is a
// read of the kill-switch key `live:off`.
//
// No `import … from 'cloudflare:workers'`: a plain class keeps index.js importable by the Node test harnesses (qa/worker/*).
import { LIVE_POLL_MS, LIMITS, GATE_TTL, RING, SLOW_EVERY, HB_MS, UNIT, kst, nextOpen, sessionState, newGuard, roll, charge, overBudget, diffRow, applyPatch, cloneRow, sameJson } from './live_core.js';

const PROTO = 1;
const ORIGINS = ['https://panse.pages.dev', 'https://korea-market-heatmap.ssslot.workers.dev'];
const KILL_KEY = 'live:off';                       // REPLAY KV: any value = realtime off (pages poll); delete the key to turn it back on
let SOURCE = null;                                 // (env, ms) → {endTime, body}: quotesCore of index.js (same rows as /api/quotes)
export function configureLive(source) { SOURCE = source; }

const limitsOf = env => { try { return env && env.LIVE_LIMITS ? { ...LIMITS, ...JSON.parse(env.LIVE_LIMITS) } : LIMITS; } catch (e) { return LIMITS; } };   // tests only (wrangler dev --var)
const devOpen = env => !!(env && env.LIVE_DEV_OPEN === '1');                   // tests only: treat every hour as the session
const originOk = (o, env) => ORIGINS.includes(o) || String((env && env.LIVE_ORIGINS) || '').split(',').map(s => s.trim()).filter(Boolean).includes(o);
const hubOf = env => env.MARKET.get(env.MARKET.idFromName('top'), { locationHint: 'apac' });
const jsonRes = (body, status = 200, maxAge = 0) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': maxAge ? `public, max-age=${maxAge}` : 'no-store', 'access-control-allow-origin': 'https://panse.pages.dev' } });

/* ── Worker side ─────────────────────────────── */
export async function liveRoute(request, env, ctx, url) {
  const ch = url.searchParams.get('ch') || 'top';
  if (ch !== 'top') return jsonRes({ error: 'ch는 top만 있어요' }, 400);           // one hub, one name: no stray Durable Objects
  if (!env.MARKET) return jsonRes({ error: '이 배포에는 실시간 허브가 없어요' }, 503);
  if (url.pathname === '/api/live/state') return stateRoute(request, env, ctx);
  if (request.method !== 'GET') return jsonRes({ error: 'GET만 받아요' }, 405);
  if ((request.headers.get('upgrade') || '').toLowerCase() !== 'websocket') return jsonRes({ error: 'WebSocket 연결만 받아요' }, 426);
  const origin = request.headers.get('origin');
  if (origin && !originOk(origin, env)) return jsonRes({ error: '허용되지 않은 출처예요' }, 403);
  const now = Date.now();
  if (!devOpen(env) && sessionState(now, null) !== 'open') return offSocket('closed', nextOpen(now));   // weekends, nights: no DO request
  const gate = await gateGet(request);
  if (gate) return offSocket(gate.reason, gate.retryAt);
  if (await killed(env)) return offSocket('paused', now + GATE_TTL.paused * 1000);
  let res;
  try { res = await hubOf(env).fetch(request); }
  catch (e) { ctx.waitUntil(gatePut(request, 'error', now + GATE_TTL.error * 1000)); return offSocket('error', now + GATE_TTL.error * 1000); }
  if (res.status === 101) return res;
  let j = null;
  try { j = await res.json(); } catch (e) { /* not JSON */ }
  const reason = (j && j.reason) || 'error', retryAt = (j && Number(j.retryAt)) || now + GATE_TTL.error * 1000;
  ctx.waitUntil(gatePut(request, reason, retryAt));
  return offSocket(reason, retryAt);
}
async function killed(env) {
  if (!env.REPLAY) return false;
  try { return !!(await env.REPLAY.get(KILL_KEY, { cacheTtl: 60 })); } catch (e) { return false; }
}
// accept, say why, close — the page reads the reason (an HTTP error status would reach it only as a bare 1006)
function offSocket(reason, retryAt) {
  const body = { t: 'off', reason, retryAt, at: Date.now() };
  if (typeof WebSocketPair === 'undefined') return jsonRes(body, 503);
  const [client, server] = Object.values(new WebSocketPair());
  server.accept();
  server.send(JSON.stringify(body));
  server.close(4003, reason);
  return new Response(null, { status: 101, webSocket: client });
}
// refusals remembered per data center (Cache API: free, no KV)
const gateKey = request => new Request(new URL('/__cache/live-gate', request.url).toString());
async function gateGet(request) {
  try {
    if (typeof caches === 'undefined') return null;
    const hit = await caches.default.match(gateKey(request));
    if (!hit) return null;
    const j = await hit.json();
    return j && j.retryAt > Date.now() ? j : null;
  } catch (e) { return null; }
}
async function gatePut(request, reason, retryAt) {
  const ttl = Math.max(5, Math.min(GATE_TTL[reason] || GATE_TTL.error, Math.ceil((retryAt - Date.now()) / 1000)));
  try {
    if (typeof caches === 'undefined') return;
    await caches.default.put(gateKey(request), new Response(JSON.stringify({ reason, retryAt }), { headers: { 'content-type': 'application/json', 'cache-control': `public, max-age=${ttl}` } }));
  } catch (e) { /* the gate is an optimisation; the hub still counts and refuses */ }
}
async function stateRoute(request, env, ctx) {
  const key = new Request(new URL('/__cache/live-state', request.url).toString());
  const cache = typeof caches !== 'undefined' && !devOpen(env) ? caches.default : null;   // tests read it fresh
  if (cache) { try { const hit = await cache.match(key); if (hit) return hit; } catch (e) { /* miss */ } }
  let body;
  try {
    const r = await hubOf(env).fetch(new Request('https://hub/__state'));
    body = await r.json();
  } catch (e) { return jsonRes({ error: '허브 상태를 읽지 못했어요' }, 502); }
  body.killSwitch = await killed(env);
  // while the guard has tripped, this data center asks the hub at most every 10 minutes (each ask is a DO request)
  const res = jsonRes(body, 200, body.guard && body.guard.trip ? GATE_TTL.budget : 60);
  if (cache) ctx.waitUntil(cache.put(key, res.clone()).catch(() => {}));
  return res;
}

/* ── the hub ─────────────────────────────── */
export class MarketHub {
  constructor(state, env) {
    this.state = state;
    this.env = env || {};
    this.lim = limitsOf(this.env);
    this.rows = null;             // Map code → row exactly as every connected page holds it (/api/quotes row shape)
    this.order = [];
    this.meta = null;             // {asOf, source, marketStatus, afterHours, nxt, index}
    this.ver = 0;
    this.epoch = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    this.ring = [];               // [{v, text}]
    this.snap = null;             // {v, text}: one serialisation per version
    this.tick = 0;
    this.lastSent = 0;
    this.lastPollAt = 0;
    this.backoff = 0;
    this.stats = { polls: 0, fails: 0, upstreamMs: 0, lastErr: null, lastBytes: 0, lastRows: 0, sent: 0, snaps: 0, startedAt: Date.now() };
    this.g = null;
    try { state.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong')); } catch (e) { /* older runtime */ }
    state.blockConcurrencyWhile(async () => { this.g = (await state.storage.get('guard')) || newGuard(Date.now()); });
  }

  // every handler: roll the day, charge what Cloudflare bills for this event, persist once at the end
  begin(units) { const t = Date.now(); roll(this.g, t); charge(this.g, units); return t; }
  async finish(t0) {
    const now = Date.now();
    charge(this.g, 0, Math.max(1, now - t0));        // handler wall time = the duration proxy
    this.tripped(now);                                 // a limit reached by this event shuts the hub now, not on the next one
    await this.state.storage.put('guard', this.g);    // one SQLite row per event (≤ ~20k a day of the 50M a month included)
  }
  refuse(reason, retryAt) { this.stats.refused = (this.stats.refused || 0) + 1; return new Response(JSON.stringify({ reason, retryAt }), { status: 503, headers: { 'content-type': 'application/json' } }); }

  // an active trip, or a new one when a limit has just been reached (then every socket is told and closed, polling stops)
  tripped(now) {
    if (this.g.trip && now < this.g.trip.until) return this.g.trip;
    const o = overBudget(this.g, this.lim, now);
    if (!o) return null;
    this.g.trip = { why: o.why, until: o.until, at: now };
    this.g.trips = (this.g.trips || 0) + 1;
    console.error(`live: budget guard tripped (${o.why}) until ${new Date(o.until).toISOString()}`);
    this.shutdown('budget', o.until);
    return this.g.trip;
  }
  closedNow(now) {
    if (devOpen(this.env)) return false;
    const day = kst(now).day;
    if (this.g.closedDay === day) return true;
    return sessionState(now, this.g.endDay === day ? this.g.endTime : null) !== 'open';
  }
  shutdown(reason, retryAt) {
    const text = JSON.stringify({ t: 'off', reason, retryAt, at: Date.now() });
    for (const ws of this.state.getWebSockets()) { try { ws.send(text); ws.close(4003, reason); } catch (e) { /* gone */ } }
    this.state.storage.deleteAlarm().catch(() => {});
  }

  async fetch(request) {
    const url = new URL(request.url);
    const t0 = this.begin(UNIT);
    try {
      if (url.pathname === '/__state') return jsonRes(this.status(t0));
      if (this.tripped(t0)) return this.refuse('budget', this.g.trip.until);
      if (this.closedNow(t0)) return this.refuse('closed', nextOpen(t0));
      if (this.state.getWebSockets().length >= this.lim.maxSockets) return this.refuse('full', t0 + 5 * 60e3);
      if ((request.headers.get('upgrade') || '').toLowerCase() !== 'websocket') return this.refuse('error', t0 + 15e3);
      this.g.dConn++;
      if (this.tripped(t0)) return this.refuse('budget', this.g.trip.until);
      const [client, server] = Object.values(new WebSocketPair());
      this.state.acceptWebSocket(server);
      server.serializeAttachment({ at: t0, n: 0 });
      server.send(JSON.stringify(this.hello(t0)));
      if (this.rows && t0 - this.lastPollAt > 10 * 60e3) { this.rows = null; this.ring = []; this.snap = null; }   // idle > 10 min: wait for a fresh snapshot
      if (this.rows) {
        const ep = url.searchParams.get('epoch'), since = Number(url.searchParams.get('ver'));
        const missed = ep === this.epoch && since > 0 ? this.since(since) : null;
        if (missed) for (const t of missed) server.send(t); else this.sendSnap(server);
      }
      if ((await this.state.storage.getAlarm()) == null) await this.state.storage.setAlarm(Date.now());
      return new Response(null, { status: 101, webSocket: client });
    } finally { await this.finish(t0); }
  }

  async webSocketMessage(ws, message) {
    const t0 = this.begin(1);                              // incoming messages bill 20 : 1
    try {
      this.g.dMsgs++;
      let a = null;
      try { a = ws.deserializeAttachment() || { n: 0 }; } catch (e) { a = { n: 0 }; }
      a.n = (a.n || 0) + 1;
      try { ws.serializeAttachment(a); } catch (e) { /* closing */ }
      if (a.n > this.lim.socketMsgs) { try { ws.close(4008, 'too many messages'); } catch (e) { } return; }
      let m = null;
      try { m = JSON.parse(typeof message === 'string' ? message : new TextDecoder().decode(message)); } catch (e) { return; }
      if (!m || !this.rows) return;
      if (m.t === 'resume') {
        const missed = m.epoch === this.epoch && m.v > 0 ? this.since(m.v) : null;
        if (missed) for (const t of missed) ws.send(t); else this.sendSnap(ws);
      } else if (m.t === 'snap') this.sendSnap(ws);
    } finally { await this.finish(t0); }
  }
  async webSocketClose() { const t0 = this.begin(1); await this.finish(t0); }    // counted like a message (conservative)
  async webSocketError() { const t0 = this.begin(1); await this.finish(t0); }

  async alarm() {
    const t0 = this.begin(UNIT);
    try {
      if (this.tripped(t0)) return;
      if (!this.state.getWebSockets().length) return;              // nobody listening: stop (the next page wakes the hub)
      if (this.closedNow(t0)) { this.shutdown('closed', nextOpen(t0)); return; }
      if (this.tick % 20 === 0 && await killed(this.env)) { this.shutdown('paused', t0 + GATE_TTL.paused * 1000); return; }
      let ok = true;
      try {
        if (!SOURCE) throw new Error('live source not configured');
        const { endTime, body } = await SOURCE(this.env, 8000);
        this.stats.polls++; this.stats.upstreamMs = Date.now() - t0; this.lastPollAt = Date.now();
        this.g.dPolls++; this.g.mPolls++;
        const k = kst(t0);
        if (/^\d{4}$/.test(endTime || '')) { this.g.endTime = endTime; this.g.endDay = k.day; }
        if (!devOpen(this.env) && isHoliday(body, t0)) { this.g.closedDay = k.day; this.shutdown('closed', nextOpen(t0)); return; }
        this.ingest(body);
        this.backoff = 0;
      } catch (e) {
        ok = false;
        this.stats.fails++;
        this.stats.lastErr = String((e && e.message) || e).replace(/([0-9A-Z]{6},){2,}[0-9A-Z]{6}/g, m => `{${m.split(',').length} codes}`).slice(0, 200);
        this.backoff = Math.min(30000, Math.max(LIVE_POLL_MS * 2, this.backoff * 2));
        this.broadcast(JSON.stringify({ t: 'st', ok: false, msg: '시세를 받지 못했어요', retryMs: this.backoff, at: Date.now() }));
      }
      if (this.closedNow(Date.now())) { this.shutdown('closed', nextOpen(Date.now())); return; }
      await this.state.storage.setAlarm(Math.max(t0 + (ok ? LIVE_POLL_MS : this.backoff), Date.now() + 250));
    } finally { await this.finish(t0); }
  }

  ingest(body) {
    const slow = this.tick++ % SLOW_EVERY === 0;
    const now = Date.now();
    if (!this.rows) {                                      // first data of this instance: everyone gets a snapshot
      this.rows = new Map(body.stocks.map(r => [r.c, cloneRow(r)]));
      this.order = body.stocks.map(r => r.c);
      this.meta = metaOf(body);
      this.ver = 1;
      this.ring = [];
      for (const ws of this.state.getWebSockets()) this.sendSnap(ws);
      return;
    }
    const rows = [];
    for (const n of body.stocks) {
      const o = this.rows.get(n.c);
      if (!o) { const c = cloneRow(n); this.rows.set(n.c, c); this.order.push(n.c); rows.push(c); continue; }
      const p = diffRow(o, n, slow);
      if (p) { applyPatch(o, p); rows.push(p); }
    }
    const m = metaOf(body), extra = {};
    if (!sameJson(m.index, this.meta.index)) extra.ix = m.index;
    if (!sameJson(m.marketStatus, this.meta.marketStatus)) extra.ms = m.marketStatus;
    if (m.afterHours !== this.meta.afterHours) extra.ah = m.afterHours;
    if (!sameJson(m.nxt, this.meta.nxt)) extra.nxt = m.nxt;
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
  since(v) {
    if (v === this.ver) return [];
    const i = this.ring.findIndex(x => x.v === v + 1);
    return i < 0 ? null : this.ring.slice(i).map(x => x.text);
  }
  hello(now) { return { t: 'hello', proto: PROTO, ch: 'top', epoch: this.epoch, v: this.ver, poll: LIVE_POLL_MS, now }; }
  sendSnap(ws) {
    if (!this.snap || this.snap.v !== this.ver) {
      this.snap = { v: this.ver, text: JSON.stringify({ t: 'snap', ch: 'top', epoch: this.epoch, v: this.ver, at: Date.now(), body: { ...this.meta, stocks: this.order.map(c => this.rows.get(c)) } }) };
    }
    this.stats.snaps++;
    try { ws.send(this.snap.text); } catch (e) { try { ws.close(1011, 'send failed'); } catch (_) { } }
  }
  broadcast(text) {
    for (const ws of this.state.getWebSockets()) {
      try { ws.send(text); this.stats.sent++; } catch (e) { try { ws.close(1011, 'send failed'); } catch (_) { } }
    }
    this.lastSent = Date.now();
  }
  status(now) {
    const g = this.g, L = this.lim;
    return {
      ch: 'top', epoch: this.epoch, v: this.ver, sockets: this.state.getWebSockets().length, rows: this.rows ? this.rows.size : 0,
      pollMs: LIVE_POLL_MS, session: this.closedNow(now) ? 'closed' : 'open', ...this.stats,
      guard: {
        day: g.day, month: g.month, trip: g.trip, trips: g.trips || 0,
        doRequests: { today: Math.ceil(g.dU / UNIT), dayLimit: L.dayDoReq, month: Math.ceil(g.mU / UNIT), monthLimit: L.monthDoReq },
        connects: { today: g.dConn, dayLimit: L.dayConnects }, maxSockets: L.maxSockets,
        awakeMs: { today: g.dAwake, dayLimit: L.dayAwakeMs, month: g.mAwake, monthLimit: L.monthAwakeMs },
        upstreamPolls: { today: g.dPolls, month: g.mPolls }, messagesToday: g.dMsgs,
      },
    };
  }
}

const metaOf = b => ({ asOf: b.asOf, source: b.source, marketStatus: b.marketStatus, afterHours: b.afterHours, nxt: b.nxt, index: b.index });
// a weekday without trading: after 09:05 both indices still CLOSE and the newest KRX trade is from another day (§4-5)
function isHoliday(body, now) {
  const k = kst(now);
  if (k.hm < 905) return false;
  const st = Object.values((body && body.marketStatus) || {});
  return st.length > 0 && st.every(s => s === 'CLOSE') && String((body && body.asOf) || '').slice(0, 10) !== k.date;
}
