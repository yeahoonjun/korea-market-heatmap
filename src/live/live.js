/* 실시간 갱신 — the page side (docs/standards/realtime.md §7, AGENTS §3-23b; the hub is worker/src/live.js, LIVE since 2026-11-14).
   One WebSocket per page to GET api/live (the Durable Object hub that asks Naver every 3 s for the 600-stock stream — KOSPI top 300 +
   KOSDAQ top 300 — and sends only what changed). The module keeps the hub's /api/quotes-shaped body, applies the deltas exactly like the
   hub's diffRow/applyPatch pair, and hands the body to KH.feed — the same road the 10 s quotes poll takes (store, map, side cards, dock,
   ticker, flashes, 'kh:data'). While the stream is healthy the poll is paused (KH.pausePoll); whenever it is not, the poll is back
   within one interval. User decision 2026-11-14: nothing beyond the $5 Cloudflare plan → the page is polite:
   · one socket per page, never two attempts in flight; no socket in a hidden tab (closed after 30 s hidden, back when visible),
     on 해외 / 지표 or during 다시 보기 (closed after the same 30 s), under 전체 (2,700, polled), with 실시간 갱신 off, in the snapshot;
   · {t:'off'} is the end (the close event may never come, §7-3): closed / budget → not before retryAt (+0–60 s jitter), full · paused ·
     error → not before retryAt (+0–25 %), the same refusal again doubles the wait (≤ 30 min); the refusal survives a reload
     (localStorage khm.live.off);
   · a socket that drops, never opens (10 s) or goes silent (45 s; the hub beats every 15 s) → 1 · 2 · 4 · 8 · 15 · 30 s (±25 %), then
     every 5 min; the count resets after a stream that delivered data and stayed up 60 s.
   Status (#live-mark in #status, neutral colours — not a control, so no amber; no red / green): 실시간 · 연결하는 중 · 다시 연결하는 중 ·
   10초마다 갱신 · 시세 지연; hidden when the session is closed, the setting is off, under 전체 or 다시 보기. The words for screen readers
   change only with the state (aria-live polite, after 1.5 s so a passing state is not read out). window.KHLive.state() for debugging. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || KH.MODE !== 'live' || typeof KH.feed !== 'function' || typeof KH.pausePoll !== 'function' || typeof WebSocket !== 'function') return;
const statusEl = document.getElementById('status'), mark = document.getElementById('live-mark');
if (!statusEl || !mark) return;
const h = KH.h;

/* ───────── numbers (realtime.md §7-3, §12-2) ───────── */
const PROTO = 1;
const AWAY_MS = 30e3;          // hidden tab · 해외 / 지표 · 다시 보기: the socket stays this long, then closes
const SILENT_MS = 45e3;        // no message at all → the socket is dead (the hub sends a beat every 15 s when nothing changes)
const OPEN_MS = 10e3;          // a socket not open by then is dropped
const STALE_MS = 30e3;         // the hub's source failing ({t:'st', ok:false}) and no new value for this long → the poll comes back
const SNAP_WAIT_MS = 15e3;     // a snapshot asked for after a gap and not here by then → reconnect
const BACKOFF_S = [1, 2, 4, 8, 15, 30];   // after a failure (±25 %), then …
const SLOW_S = 300;            // … every 5 minutes
const HEALTHY_MS = 60e3;       // a stream that delivered data and stayed up this long resets the failure count
const POLL_LABEL_AFTER = 3;    // failures in a row before the label says 10초마다 갱신
const MAX_SENDS = 5;           // our own messages per socket (the hub closes a socket at 20)
const REPEAT_CAP_MS = 30 * 60e3;          // a refusal repeated (full · paused · error) waits at most this long
const MAX_ARM_MS = 6 * 3600e3;            // longer waits are re-armed in steps (setTimeout overflows past 24.8 days; sleep drift)
const MAX_RETRY_AHEAD = 32 * 86400e3;     // a retryAt further ahead than this is not believed
const MIN_GAP_MS = 2000;       // never two attempts closer than this, whatever asks (a user flicking the switch, a tab coming back)
const ANNOUNCE_MS = 1500;
const STORE_KEY = 'khm.live.off';

const now = () => (typeof KH.now === 'function' ? KH.now() : Date.now());   // server-corrected (src/extras) when available
const rnd = (a, b) => a + Math.random() * (b - a);
const pad = n => String(n).padStart(2, '0');
const hms = ms => { const k = new Date(ms + 9 * 3600e3); return `${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}:${pad(k.getUTCSeconds())}`; };
// a weekday between 08:59 and 16:35 KST: the session may be open (until the hub says, the label stays out of sight otherwise)
function likelyOpen() {
  const k = new Date(now() + 9 * 3600e3), wd = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
  return wd >= 1 && wd <= 5 && m >= 8 * 60 + 59 && m < 16 * 60 + 35;
}
// retryAt: ms (the hub) — or a "YYYY-MM-DD HH:MM:SS KST" text, just in case
function retryMs(v) {
  if (typeof v === 'number' && isFinite(v)) return v;
  const m = /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?/.exec(String(v || ''));
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 9, +m[5], +(m[6] || 0)) : NaN;
}

/* ───────── delta rules: the twin of worker/src/live_core.js applyPatch (realtime.md §5-3) ───────── */
function applyPatch(row, p) {
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

/* ───────── state ───────── */
const S = {
  on: true,
  ws: null, phase: 'idle',           // 'idle' | 'connecting' (socket not open) | 'open' (open, no data yet) | 'stream' (data flowing)
  epoch: null, v: 0, body: null, byCode: null, dirty: false,
  everHello: false, everData: false,
  fails: 0, nextAt: 0, lastTry: 0, retryT: 0, openT: 0, silentT: 0, staleT: 0, snapT: 0, awayT: 0,
  off: null, repeat: { reason: '', n: 0 },
  openedAt: 0, gotData: false, lastMsg: 0, lastData: 0, delayed: false, fallback: false, paused: false,
  sends: 0, snapAsked: false,
  connects: 0, snaps: 0, deltas: 0, beats: 0, feeds: 0, feedMs: 0, feedMax: 0, gaps: 0,
  painted: '', sayT: 0,
};
try {
  const o = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
  if (o && typeof o.until === 'number' && o.until > now() && o.until - now() < MAX_RETRY_AHEAD) S.off = o;
  else localStorage.removeItem(STORE_KEY);
} catch (e) { /* private mode: nothing remembered */ }

function setPaused(b) {
  if (S.paused === b) return;
  S.paused = b;
  KH.pausePoll(b);
}

/* ───────── what may happen now ───────── */
// a reason never to hold a socket (close at once)
function blocked() {
  if (!S.on) return 'setting';
  if (KH.scope && KH.scope() === 'all') return 'scope';
  if (S.off && now() < S.off.until) return 'off';
  return '';
}
// a reason not to open one (an open socket stays AWAY_MS)
function away() {
  if (document.hidden) return 'hidden';
  if (KH.replay && KH.replay()) return 'replay';
  const m = KH.market ? KH.market() : '';
  if (m === 'world' || m === 'cmdty') return 'world';
  return '';
}

function sync() {
  const b = blocked();
  if (b) {
    drop();
    clearTimeout(S.awayT); S.awayT = 0;
    if (b === 'off') arm(S.off.until - now()); else disarm();
    if (b !== 'off' && S.off && now() >= S.off.until) forgetOff();
    paint();
    return;
  }
  if (S.off) forgetOff();
  const a = away();
  if (a) {
    disarm();
    if (S.ws && !S.awayT) S.awayT = setTimeout(() => { S.awayT = 0; if (away()) { drop(); paint(); } }, AWAY_MS);
    paint();
    return;
  }
  clearTimeout(S.awayT); S.awayT = 0;
  if (!S.ws && !S.retryT) arm(S.nextAt - now());
  if (S.ws) feedNow();
  paint();
}
function arm(ms) {
  clearTimeout(S.retryT);
  S.retryT = setTimeout(() => { S.retryT = 0; if (S.nextAt > now() + 50 && !blocked()) { arm(S.nextAt - now()); return; } if (blocked() || away()) sync(); else connect(); },
    Math.max(0, Math.min(MAX_ARM_MS, ms)));
}
function disarm() { clearTimeout(S.retryT); S.retryT = 0; }
function forgetOff() { S.off = null; try { localStorage.removeItem(STORE_KEY); } catch (e) { } }

/* ───────── the socket ───────── */
function connect() {
  disarm();
  if (S.ws || blocked() || away()) { paint(); return; }
  const gap = S.lastTry + MIN_GAP_MS - Date.now();
  if (gap > 0) { arm(gap); return; }
  S.lastTry = Date.now();
  const u = new URL('api/live', location.href);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  u.hash = ''; u.search = '';
  u.searchParams.set('ch', 'top');
  if (S.epoch && S.v > 0 && S.body) { u.searchParams.set('epoch', S.epoch); u.searchParams.set('ver', String(S.v)); }   // resume (§4-2)
  let ws;
  try { ws = new WebSocket(u.toString()); }
  catch (e) { failed(); return; }
  S.ws = ws; S.phase = 'connecting'; S.connects++;
  S.openedAt = 0; S.gotData = false; S.sends = 0; S.snapAsked = false; S.delayed = false; S.fallback = false;
  S.openT = setTimeout(() => { if (S.ws === ws && ws.readyState === 0) { end(true); failed(); } }, OPEN_MS);
  ws.onopen = () => { if (S.ws !== ws) return; clearTimeout(S.openT); S.openedAt = Date.now(); S.phase = 'open'; heard(); paint(); };
  ws.onmessage = e => { if (S.ws === ws) onMessage(e.data); };
  ws.onclose = () => { if (S.ws !== ws) return; end(false); failed(); };
  ws.onerror = () => { /* the close event follows */ };
  paint();
}
// forget the socket (no failure): a socket still opening is closed once it opens, so it never logs "closed before established"
function end(hard) {
  const ws = S.ws;
  if (!ws) return;
  S.ws = null; S.phase = 'idle';
  for (const k of ['openT', 'silentT', 'staleT', 'snapT']) { clearTimeout(S[k]); S[k] = 0; }
  ws.onmessage = ws.onclose = ws.onerror = null;
  if (ws.readyState === 0 && !hard) ws.onopen = () => { try { ws.close(1000, 'bye'); } catch (e) { } };
  else { ws.onopen = null; try { ws.close(1000, 'bye'); } catch (e) { } }
  if (S.gotData && S.openedAt && Date.now() - S.openedAt >= HEALTHY_MS) S.fails = 0;
  S.delayed = false; S.fallback = false;
  setPaused(false);
}
// our choice (away, setting, 전체 …): not a failure; the next attempt may come at once
function drop() { if (S.ws) end(false); }
// the socket failed (dropped, never opened, silent, snapshot never came): back off, the poll is already back
function failed() {
  S.fails++;
  const s = S.fails <= BACKOFF_S.length ? BACKOFF_S[S.fails - 1] : SLOW_S;
  S.nextAt = now() + s * 1000 * rnd(0.75, 1.25);
  sync();
}
function heard() {
  S.lastMsg = Date.now();
  clearTimeout(S.silentT);
  const ws = S.ws;
  S.silentT = setTimeout(() => { if (S.ws === ws) { end(true); failed(); } }, SILENT_MS);
}
function send(obj) {
  if (!S.ws || S.ws.readyState !== 1) return false;
  if (S.sends >= MAX_SENDS) { end(true); failed(); return false; }
  S.sends++;
  try { S.ws.send(JSON.stringify(obj)); return true; } catch (e) { return false; }
}

/* ───────── messages (realtime.md §5-2) ───────── */
function onMessage(text) {
  heard();
  let m = null;
  try { m = JSON.parse(text); } catch (e) { return; }
  if (!m || typeof m.t !== 'string') return;
  if (m.t === 'hello') onHello(m);
  else if (m.t === 'snap') onSnap(m);
  else if (m.t === 'd') onDelta(m);
  else if (m.t === 'hb') onBeat(m);
  else if (m.t === 'st') onSource(m);
  else if (m.t === 'off') onOff(m);
}
function onHello(m) {
  S.everHello = true;
  if (m.proto !== PROTO) { refuse('proto', now() + 10 * 60e3); return; }   // a hub speaking another protocol: poll, ask again later
  if (m.epoch !== S.epoch) { S.epoch = m.epoch; S.v = 0; S.body = null; S.byCode = null; S.dirty = false; }   // versions of another life: wait for its snapshot
  S.phase = 'open';
  paint();
}
function onSnap(m) {
  const b = m.body;
  if (!b || !Array.isArray(b.stocks) || !b.stocks.length) return;
  clearTimeout(S.snapT); S.snapT = 0; S.snapAsked = false;
  S.epoch = m.epoch || S.epoch; S.v = +m.v || 0;
  S.body = b; S.byCode = new Map(b.stocks.map(r => [r.c, r]));
  S.snaps++;
  data();
}
function onDelta(m) {
  if (!S.body || m.b !== S.v) { S.gaps++; askSnap(); return; }      // a gap (or no body yet): the snapshot, never a guess
  const b = S.body;
  for (const p of m.rows || []) {
    if (!p || !p.c) continue;
    const r = S.byCode.get(p.c);
    if (r) applyPatch(r, p);
    else if (p.n) { const row = Object.assign({}, p); b.stocks.push(row); S.byCode.set(p.c, row); }   // a new code comes whole
    else { S.gaps++; askSnap(); return; }
  }
  if (m.ix) b.index = m.ix;
  if (m.ms) b.marketStatus = m.ms;
  if ('ah' in m) b.afterHours = m.ah;
  if (m.nxt) b.nxt = m.nxt;
  if (m.asOf) b.asOf = m.asOf;
  S.v = m.v;
  S.deltas++;
  data();
}
function onBeat(m) {
  S.beats++;
  if (S.body && m.v !== S.v) { S.gaps++; askSnap(); return; }
  if (!S.body) return;
  if (m.asOf && m.asOf !== S.body.asOf) { S.body.asOf = m.asOf; }
  fresh();
}
function onSource(m) {
  if (m.ok !== false) return;
  S.delayed = true;
  // the hub keeps the socket and retries (6 → 12 → 30 s); the values on screen are its last ones. 30 s without a new one → poll again
  clearTimeout(S.staleT);
  const left = STALE_MS - (Date.now() - (S.lastData || 0));
  if (left <= 0) fallBack(); else S.staleT = setTimeout(() => { if (S.delayed) fallBack(); }, left);
  paint();
}
function fallBack() { S.fallback = true; setPaused(false); paint(); }
function onOff(m) {
  const reason = ['closed', 'full', 'budget', 'paused', 'error'].includes(m.reason) ? m.reason : 'error';
  let at = retryMs(m.retryAt);
  if (!isFinite(at) || at < now()) at = now() + 15e3;
  refuse(reason, Math.min(at, now() + MAX_RETRY_AHEAD));
}
// {t:'off'} (or our own refusal): this socket is over now — not when (if) its close event comes
function refuse(reason, retryAt) {
  end(false);
  const wait = retryAt - now();
  let until;
  if (reason === 'closed' || reason === 'budget') until = retryAt + rnd(0, 60e3);
  else {
    S.repeat = S.repeat.reason === reason ? { reason, n: S.repeat.n + 1 } : { reason, n: 1 };
    const grown = Math.max(wait, 15e3) * 2 ** (S.repeat.n - 1) * rnd(1, 1.25);
    until = now() + Math.max(wait, Math.min(REPEAT_CAP_MS, grown));
  }
  S.off = { reason, retryAt, until };
  S.fails = 0; S.nextAt = 0;
  try { localStorage.setItem(STORE_KEY, JSON.stringify(S.off)); } catch (e) { }
  sync();
}
function askSnap() {
  if (S.snapAsked) return;
  S.snapAsked = true;
  if (!send({ t: 'snap' })) return;
  const ws = S.ws;
  clearTimeout(S.snapT);
  S.snapT = setTimeout(() => { if (S.ws === ws && S.snapAsked) { end(true); failed(); } }, SNAP_WAIT_MS);
}
// a snapshot or a delta was applied: the stream is the source now
function data() {
  S.gotData = true; S.everData = true; S.phase = 'stream';
  S.repeat = { reason: '', n: 0 };
  if (S.openedAt && Date.now() - S.openedAt >= HEALTHY_MS) S.fails = 0;
  S.dirty = true;
  fresh();
  feedNow();
}
function fresh() {
  S.lastData = Date.now();
  if (S.delayed || S.fallback) { S.delayed = false; S.fallback = false; clearTimeout(S.staleT); S.staleT = 0; }
  if (S.body) setPaused(true);
  paint();
}
// draw the body (not in a hidden tab: the deltas are kept and drawn once it is visible again)
function feedNow() {
  if (!S.dirty || !S.body || document.hidden) return;
  S.dirty = false;
  const t0 = performance.now();
  let ok = false;
  try { ok = KH.feed(S.body); } catch (e) { setTimeout(() => { throw e; }); }
  const ms = performance.now() - t0;
  if (ok) { S.feeds++; S.feedMs = ms; S.feedMax = Math.max(S.feedMax, ms); beat(); }
}

/* ───────── the status mark ───────── */
const L = {
  live: { long: '실시간', short: '실시간', say: '실시간으로 받고 있어요. 바뀐 종목만 바로 바뀌어요' },
  connecting: { long: '연결하는 중', short: '연결 중', say: '실시간 연결을 여는 중이에요' },
  reconnecting: { long: '다시 연결하는 중', short: '연결 중', say: '연결이 잠깐 끊겼어요. 다시 붙는 중이에요' },
  polling: { long: '10초마다 갱신', short: '10초', say: '실시간 연결이 안 돼서 10초마다 새로 받고 있어요' },
  delayed: { long: '시세 지연', short: '지연', say: '네이버 증권 시세를 받지 못해 다시 받는 중이에요' },
};
const OFF_SAY = {
  full: '실시간 연결이 가득 차서 10초마다 새로 받고 있어요. 잠시 뒤 다시 붙어 볼게요',
  budget: '오늘 실시간 사용량을 다 써서 10초마다 새로 받고 있어요',
  paused: '실시간 갱신이 잠시 꺼져 있어서 10초마다 새로 받고 있어요',
};
function labelState() {
  if (!S.on || (KH.scope && KH.scope() === 'all') || (KH.replay && KH.replay())) return '';
  if (S.off) return S.off.reason === 'closed' ? '' : 'polling';
  if (S.phase === 'stream') {
    if (!S.fallback) return S.delayed ? 'delayed' : 'live';
    return KH.polling && KH.polling().ok ? 'polling' : 'delayed';
  }
  if (!S.everHello && !likelyOpen()) return '';           // a weekend / night probe: no flash of "연결하는 중"
  if (!S.ws && away() === 'world') return 'polling';       // 해외 / 지표 after the grace: the 10 s poll feeds the ticker and the dock
  if (S.fails >= POLL_LABEL_AFTER) return 'polling';
  return S.everData ? 'reconnecting' : 'connecting';
}
// withTime: the tooltip ends with the last value's time (the words read out once do not: they would go stale)
function sayText(st, withTime = true) {
  if (st === 'polling' && S.off && OFF_SAY[S.off.reason]) return OFF_SAY[S.off.reason];
  if (withTime && (st === 'live' || st === 'delayed')) {
    const t = S.body && Date.parse(S.body.asOf);
    return L[st].say + (isFinite(t) ? ` · ${st === 'live' ? '마지막' : '마지막 값'} ${hms(t)}` : '');
  }
  return L[st].say;
}
const g = h('i', { class: 'lm-g', 'aria-hidden': 'true' });
const tLong = h('span', { class: 'lm-l', 'aria-hidden': 'true' }), tShort = h('span', { class: 'lm-s', 'aria-hidden': 'true' });
const sr = h('span', { class: 'sr', role: 'status', 'aria-live': 'polite' });
mark.replaceChildren(g, tLong, tShort, sr);
mark.addEventListener('pointerenter', () => { const st = mark.dataset.s; if (st && L[st]) mark.title = sayText(st); });
function paint() {
  const st = labelState();
  const key = st + '|' + (S.off ? S.off.reason : '');
  if (key === S.painted) return;
  S.painted = key;
  clearTimeout(S.sayT);
  if (!st) {
    if (!mark.hidden) { mark.hidden = true; statusEl.classList.remove('has-lm'); delete mark.dataset.s; sr.textContent = ''; }
    return;
  }
  mark.dataset.s = st;
  tLong.textContent = L[st].long; tShort.textContent = L[st].short;
  mark.title = sayText(st);
  if (mark.hidden) { mark.hidden = false; statusEl.classList.add('has-lm'); }
  // screen readers: only a state that lasts (a 0.4 s "연결하는 중" before "실시간" is not read out)
  S.sayT = setTimeout(() => { if (mark.dataset.s === st) { const t = '실시간 갱신: ' + sayText(st, false); if (sr.textContent !== t) sr.textContent = t; } }, ANNOUNCE_MS);
}
// 화려하게: the dot beats once per update (like the status dot did for the poll)
function beat() {
  if (mark.hidden || mark.dataset.s !== 'live' || !(KH.motion && KH.motion() === 'fancy')) return;
  g.classList.remove('beat'); void g.offsetWidth; g.classList.add('beat');
}

/* ───────── events ───────── */
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && S.ws && S.lastMsg && Date.now() - S.lastMsg > SILENT_MS) { end(true); failed(); return; }   // died while frozen
  sync();
});
document.addEventListener('kh:render', sync);              // 다시 보기 · 해외 / 지표 · 전체 (the template renders on each)
addEventListener('online', () => { if (!S.ws && !blocked() && !away() && S.nextAt - now() > 5000) { S.nextAt = now() + rnd(1000, 3000); arm(S.nextAt - now()); } });
addEventListener('pagehide', () => { drop(); disarm(); });   // let the page into the back-forward cache
addEventListener('pageshow', e => { if (e.persisted) sync(); });

KH.addSetting({
  key: 'live', label: '실시간 갱신', default: true,
  hint: '켜면 바뀐 종목만 바로 받아요. 끄면 10초마다 새로 받아요. 휴대폰 데이터는 켤 때가 더 적게 들어요.',
  onChange: v => { S.on = !!v; if (S.on) S.nextAt = 0; sync(); },
});

window.KHLive = {
  state: () => ({
    label: mark.hidden ? '' : mark.dataset.s || '', on: S.on, phase: S.phase, socket: S.ws ? S.ws.readyState : -1,
    epoch: S.epoch, v: S.v, rows: S.body ? S.body.stocks.length : 0, asOf: S.body ? S.body.asOf : null,
    fails: S.fails, nextAt: S.nextAt || null, off: S.off ? Object.assign({}, S.off) : null, away: away() || null, blocked: blocked() || null,
    paused: S.paused, delayed: S.delayed, fallback: S.fallback, retryArmed: !!S.retryT,
    connects: S.connects, snaps: S.snaps, deltas: S.deltas, beats: S.beats, gaps: S.gaps, sends: S.sends,
    feeds: S.feeds, feedMs: Math.round(S.feedMs * 10) / 10, feedMax: Math.round(S.feedMax * 10) / 10,
  }),
  row: code => { const r = S.byCode && S.byCode.get(String(code)); return r ? JSON.parse(JSON.stringify(r)) : null; },   // the hub's row as held
};
sync();
})();
