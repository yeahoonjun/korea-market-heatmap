// 공공데이터포털(apis.data.go.kr) 공용 도우미 — AGENTS §3-32, docs/standards/datago.md
//
// One service key for every approved API: the Worker secret env.DATA_GO_KR_KEY. It goes into the upstream URL and nowhere
// else — never into errors, KV, responses or logs. Errors carry a short code (DgErr.code) and a fixed message; the URL is
// never kept, and every string that is stored passes through scrub() as well.
//
// The 금융위원회 APIs are not realtime: they are loaded once a day, usually after 13:00 KST of the next business day. So a
// route never calls them per request: it keeps a snapshot in KV (REPLAY), refreshes it when its own due() says so, and
// serves the last good copy (stale) when a refresh fails.
//
//   const run = new DgRun(env, DG_APIS.kofia)      one refresh: counts calls, checks the daily cap, written by finish()
//   await run.call(op, params, {numOfRows, pageNo}) → {items, total, pageNo, numOfRows}   one page (resultType=json always)
//   await run.list(op, params, {numOfRows, maxPages}) → {items, total, pages}             every page (numOfRows ≤ 10000)
//   await dgSnapshot(env, ctx, spec)  → {snap, stale, error?, partial?}  KV last-good copy + due() + cool-down + error record
//   dgParse(status, contentType, text) → {items, total}   the data.go.kr envelopes (JSON, XML, gateway text); throws DgErr
//
// Error envelopes handled (활용가이드 "OpenAPI 에러 코드정리"):
//   · new gateway (2025~): HTTP 401 Unauthorized · 403 Forbidden · 404 API not found · 429 API rate limit / token quota
//     exceeded · 5xx Error forwarding / receiving / Unexpected error — plain text (or JSON / XML wrapping those words)
//   · classic portal: XML <OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</…> (12 · 20 · 22 · 30 · 31 · 32 · 99),
//     often with HTTP 200
//   · provider: {response:{header:{resultCode, resultMsg}, body:{items:{item:[…]|{…}|''}, numOfRows, pageNo, totalCount}}}
//     resultCode 00 = ok, 03 = no data (→ []), anything else → DgErr

export const DG_HOST = 'https://apis.data.go.kr';
export const DG_TIMEOUT_MS = 8000;
export const DG_MAX_ROWS = 10000;                 // 활용가이드: numOfRows above 10,000 is cut to 10,000
export const DG_UA = 'Mozilla/5.0 (compatible; panse/1.0; +https://panse.pages.dev)';
const CALLS_TTL_S = 2 * 86400, ERR_TTL_S = 3 * 86400, ERR_EVERY_MS = 30 * 60e3;
const MAX_CALLS_PER_RUN = 20;                     // a runaway paging loop stops here
const ORIGIN = 'https://panse.pages.dev';

// Approved APIs (§3-32). `cap` = our own daily ceiling per API, far below the portal's (development accounts: 10,000 a day per
// API); env.DATAGO_CAP can only lower it (dgCap). A route that needs another approved API adds it here (or passes its own object).
export const DG_APIS = {
  kofia: { id: 'kofia', path: '/1160100/service/GetKofiaStatisticsInfoService', name: '금융위원회_금융투자협회종합통계정보', cap: 300 },
  krx: { id: 'krx', path: '/1160100/GetKrxListedInfoService_V2', name: '금융위원회_KRX상장종목정보', cap: 100 },
  lend: { id: 'lend', path: '/1160100/GetStocLendBorrInfoService_V2', name: '금융위원회_주식대차정보', cap: 1000 },
  issu: { id: 'issu', path: '/1160100/GetStocIssuInfoService_V3', name: '금융위원회_주식발행정보', cap: 1000 },
  divi: { id: 'divi', path: '/1160100/GetStocDiviInfoService_V2', name: '금융위원회_주식배당정보', cap: 1000 },
  corp: { id: 'corp', path: '/1160100/service/GetCorpBasicInfoService_V2', name: '금융위원회_기업기본정보', cap: 1000 },
  rights: { id: 'rights', path: '/1160100/GetStocRighScheService_V2', name: '금융위원회_주식권리일정정보', cap: 200 },   // 증시 캘린더 (calendar.js, AGENTS §3-33)
};

/* ── errors ─────────────────────────────── */
const DG_MSG = {
  nokey: '공공데이터포털 키가 없어요', cap: '오늘 호출 한도에 닿았어요', cool: '잠시 쉬는 중이에요',
  timeout: '응답이 너무 늦어요', network: '연결하지 못했어요', http: 'HTTP 오류', upstream: '기관 서버 오류',
  key: '인증키 오류', forbidden: '활용 신청이 확인되지 않아요', notfound: 'API를 찾지 못했어요',
  quota: '오늘 호출 허용량을 넘었어요', rate: '요청이 몰렸어요', param: '요청 변수 오류', status: '결과 코드 오류',
  json: '응답을 읽지 못했어요', empty: '자료가 없어요', shape: '응답 모양이 달라요', internal: '처리하다 실패했어요',
};
export class DgErr extends Error {
  constructor(code, extra = {}) {
    super(DG_MSG[code] || DG_MSG.internal);
    this.name = 'DgErr';
    this.code = DG_MSG[code] ? code : 'internal';
    if (extra.status) this.status = extra.status;            // upstream HTTP status
    if (extra.resultCode) this.resultCode = String(extra.resultCode).slice(0, 12);
    if (extra.msg) this.msg = String(extra.msg).slice(0, 80);   // resultMsg / returnAuthMsg (scrubbed again when stored)
    if (extra.op) this.op = extra.op;
  }
}
// How long every colo leaves an API alone after a failure (KV datago:cool:<api>). quota / cap: until the next KST midnight
// (the portal resets daily). Missing key: no cool-down (nothing was called).
const COOL_S = { key: 3600, forbidden: 3600, notfound: 3600, param: 3600, rate: 600 };
const COOL_DEFAULT_S = 900;
function coolSeconds(code, now) {
  if (code === 'quota' || code === 'cap') return Math.max(60, Math.ceil((nextKstMidnight(now) - now) / 1000));
  return COOL_S[code] || COOL_DEFAULT_S;
}

/* ── the key ─────────────────────────────── */
// The portal hands out the same key in two spellings: "Encoding" (already URL-encoded: %2B %2F %3D) and "Decoding" (raw:
// + / =); newer keys are plain hex. Whatever was pasted into the secret, decode it once here and encode it exactly once in
// the URL — a pre-encoded key encoded again (%252B) is the classic SERVICE_KEY_IS_NOT_REGISTERED_ERROR.
export function dgKey(env) {
  const v = env && env.DATA_GO_KR_KEY;
  if (typeof v !== 'string') return null;
  let k = v.trim();
  if (!k) return null;
  if (/%[0-9A-Fa-f]{2}/.test(k)) { try { k = decodeURIComponent(k); } catch (e) { /* not valid percent-encoding: use as given */ } }
  return k;
}
// every spelling of the key that could end up in a string → '[key]'; plus any serviceKey=… query value
export function scrub(s, env) {
  let out = String(s == null ? '' : s);
  const raw = env && typeof env.DATA_GO_KR_KEY === 'string' ? env.DATA_GO_KR_KEY.trim() : '';
  if (raw) {
    const k = dgKey(env) || raw;
    const forms = new Set([raw, k, encodeURIComponent(k), encodeURIComponent(raw)]);
    for (const f of forms) if (f && f.length >= 6) out = out.split(f).join('[key]');
  }
  return out.replace(/serviceKey=[^&\s"'<>]*/gi, 'serviceKey=[key]');
}

/* ── one request ─────────────────────────────── */
const OP_RE = /^[A-Za-z][A-Za-z0-9_]{1,80}$/, PARAM_RE = /^[A-Za-z][A-Za-z0-9_]{0,40}$/;
const RESERVED = new Set(['servicekey', 'resulttype']);
function dgUrl(api, op, params, key) {
  if (!api || typeof api.path !== 'string' || !OP_RE.test(op)) throw new DgErr('param', { op });
  let q = 'serviceKey=' + encodeURIComponent(key) + '&resultType=json';
  for (const [k, v] of Object.entries(params || {})) {
    if (v == null || v === '') continue;
    if (!PARAM_RE.test(k) || RESERVED.has(k.toLowerCase())) throw new DgErr('param', { op });
    q += '&' + k + '=' + encodeURIComponent(String(v));
  }
  return DG_HOST + api.path + '/' + op + '?' + q;
}
async function dgFetch(url, timeoutMs) {
  try {
    const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': DG_UA }, signal: AbortSignal.timeout(timeoutMs) });
    const text = await r.text();                     // the body read is inside the same time limit
    return { status: r.status, ctype: (r.headers && r.headers.get('content-type')) || '', text };
  } catch (e) {
    // never e.message: some runtimes put the request URL (and with it the key) into fetch errors
    throw new DgErr(e && (e.name === 'TimeoutError' || e.name === 'AbortError') ? 'timeout' : 'network');
  }
}

/* ── envelopes ─────────────────────────────── */
// resultCode / returnReasonCode → our code. 00 is fine, 03 = NODATA_ERROR (an empty answer, not a failure).
const RC = {
  '00': 'ok', '0': 'ok', '000': 'ok', '0000': 'ok', 'INFO-000': 'ok', 'NORMAL_SERVICE': 'ok',
  '03': 'nodata', 'INFO-200': 'nodata',
  '1': 'upstream', '01': 'upstream', '02': 'upstream', '4': 'upstream', '04': 'upstream', '05': 'upstream', '99': 'upstream',
  '10': 'param', '11': 'param', '12': 'notfound', '20': 'forbidden', '21': 'key', '22': 'quota',
  '30': 'key', '31': 'key', '32': 'key', '33': 'key',
};
const AUTH_MSG = /SERVICE_KEY|SERVICEKEY|DEADLINE_HAS_EXPIRED|UNREGISTERED_IP|인증키|인증에 실패|Unauthorized/i;
function codeOf(rc, msg) {
  const c = String(rc == null ? '' : rc).trim();
  const m = String(msg || '');
  if (/LIMITED_NUMBER_OF_SERVICE_REQUESTS|quota exceeded/i.test(m)) return 'quota';
  if (RC[c] === 'ok') return 'ok';
  if (AUTH_MSG.test(m)) return 'key';
  if (/SERVICE_ACCESS_DENIED|Forbidden/i.test(m)) return 'forbidden';
  if (/NO_OPENAPI_SERVICE|API not found/i.test(m)) return 'notfound';
  if (/rate limit/i.test(m)) return 'rate';
  return RC[c] || (c ? 'status' : 'shape');
}
// the gateway's own words (plain text, or wrapped in a little JSON / XML)
function gatewayCode(text) {
  const t = String(text || '');
  if (/quota exceeded/i.test(t)) return 'quota';
  if (/rate limit exceeded/i.test(t)) return 'rate';
  if (/Unauthorized/i.test(t)) return 'key';
  if (/Forbidden/i.test(t)) return 'forbidden';
  if (/API not found/i.test(t)) return 'notfound';
  if (/Error forwarding request|Error receiving response|Unexpected error/i.test(t)) return 'upstream';
  return null;
}
const XML_ENT = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" };
function xmlText(s) {
  return String(s).replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === '#' ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : +e.slice(1)) : XML_ENT[e.toLowerCase()] || m)
    .trim();
}
function xmlTag(t, name) { const m = new RegExp('<' + name + '>([\\s\\S]*?)</' + name + '>').exec(t); return m ? xmlText(m[1]) : null; }
function xmlItems(t) {
  const out = [];
  const re = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = re.exec(t))) {
    const o = {};
    const fr = /<([A-Za-z][\w]*)>([\s\S]*?)<\/\1>/g;
    let f;
    while ((f = fr.exec(m[1]))) o[f[1]] = xmlText(f[2]);
    out.push(o);
  }
  return out;
}
function asItems(x) {
  if (Array.isArray(x)) return x.filter(v => v && typeof v === 'object');
  if (x && typeof x === 'object') {
    if ('item' in x) return asItems(x.item);
    return [x];
  }
  return [];                                       // '' (no rows), null, missing
}
const fail = (code, extra) => { throw new DgErr(code, extra); };
export function dgParse(status, ctype, text) {
  const t = String(text == null ? '' : text).trim();
  const head = t.slice(0, 4000);
  // classic portal error: XML, usually with HTTP 200
  if (/<OpenAPI_ServiceResponse/i.test(head)) {
    const rc = xmlTag(t, 'returnReasonCode'), am = xmlTag(t, 'returnAuthMsg') || xmlTag(t, 'errMsg');
    fail(codeOf(rc, am) === 'ok' ? 'upstream' : codeOf(rc, am), { status, resultCode: rc, msg: am });
  }
  if (!(status >= 200 && status < 300)) {
    const g = gatewayCode(head);
    const code = status === 401 ? 'key' : status === 403 ? 'forbidden' : status === 404 ? (g === 'notfound' || !g ? 'notfound' : g)
      : status === 429 ? (g === 'quota' ? 'quota' : 'rate') : g || (status >= 500 ? 'upstream' : 'http');
    fail(code, { status });
  }
  if (t[0] === '{' || t[0] === '[') {
    let j;
    try { j = JSON.parse(t); } catch (e) { fail('json', { status }); }
    const resp = j && j.response ? j.response : j;
    const hd = (resp && resp.header) || (resp && resp.cmmMsgHeader) || resp || {};
    const rc = hd.resultCode != null ? hd.resultCode : hd.returnReasonCode;
    const msg = hd.resultMsg || hd.returnAuthMsg || hd.errMsg || '';
    if (rc == null && !(resp && resp.body)) fail(gatewayCode(t) || 'shape', { status });
    const code = rc == null ? 'ok' : codeOf(rc, msg);
    if (code === 'nodata') return { items: [], total: 0 };
    if (code !== 'ok') fail(code, { status, resultCode: rc, msg });
    const body = (resp && resp.body) || {};
    const items = asItems(body.items);
    const total = isFinite(+body.totalCount) && body.totalCount !== '' && body.totalCount != null ? +body.totalCount : items.length;
    return { items, total };
  }
  if (t[0] === '<') {
    // a provider answer in XML (resultType ignored): header + flat <item> elements
    const rc = xmlTag(t, 'resultCode'), msg = xmlTag(t, 'resultMsg');
    if (rc == null) fail(gatewayCode(head) || 'shape', { status });
    const code = codeOf(rc, msg);
    if (code === 'nodata') return { items: [], total: 0 };
    if (code !== 'ok') fail(code, { status, resultCode: rc, msg });
    const items = xmlItems(t);
    const tc = xmlTag(t, 'totalCount');
    return { items, total: tc != null && isFinite(+tc) && tc !== '' ? +tc : items.length };
  }
  fail(gatewayCode(head) || 'json', { status });
}

/* ── KST calendar (weekdays only — no holiday table: a holiday just looks like a day without data) ── */
const KST_MS = 9 * 3600e3;
const p2 = n => String(n).padStart(2, '0');
export function kstParts(ms) {
  const d = new Date(ms + KST_MS);
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), hh: d.getUTCHours(), mi: d.getUTCMinutes(), wd: d.getUTCDay(), hm: d.getUTCHours() * 100 + d.getUTCMinutes() };
}
export const kstYmd = ms => { const k = kstParts(ms); return `${k.y}${p2(k.mo)}${p2(k.d)}`; };
export const dashYmd = s => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
// KST midnight of the given KST date (YYYYMMDD) as epoch ms
export const kstDayStart = ymd => Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8)) - KST_MS;
export const addDays = (ymd, n) => kstYmd(kstDayStart(ymd) + n * 86400e3 + 12 * 3600e3);
export const isWeekday = ymd => { const wd = new Date(kstDayStart(ymd) + KST_MS).getUTCDay(); return wd >= 1 && wd <= 5; };
export function prevWeekday(ymd) { let d = addDays(ymd, -1); while (!isWeekday(d)) d = addDays(d, -1); return d; }
export function nextKstMidnight(now) { return kstDayStart(addDays(kstYmd(now), 1)); }
// the most recent weekday HH:MM (KST) at or before `now`, as epoch ms
export function lastWeekdayAt(now, hm) {
  let d = kstYmd(now);
  const at = day => kstDayStart(day) + (Math.floor(hm / 100) * 60 + hm % 100) * 60e3;
  for (let i = 0; i < 10; i++, d = addDays(d, -1)) if (isWeekday(d) && at(d) <= now) return at(d);
  return at(d);
}
// The latest business day whose data should be out by now, by the FSC rule "opened after 13:00 of the next business day"
// (Friday's data on Monday): find the latest weekday 13:00 at or before now, the answer is the weekday before it.
export function expectedBasDt(now, hm = 1300) {
  return prevWeekday(kstYmd(lastWeekdayAt(now, hm)));
}
export const kstIso = ms => { const k = kstParts(ms); const s = new Date(ms + KST_MS).getUTCSeconds(); return `${k.y}-${p2(k.mo)}-${p2(k.d)}T${p2(k.hh)}:${p2(k.mi)}:${p2(s)}+09:00`; };

/* ── KV (REPLAY) — every access tolerates a missing binding or a failing KV ── */
async function kvGet(env, key, type) {
  const kv = env && env.REPLAY;
  if (!kv || typeof kv.get !== 'function') return null;
  try { return await kv.get(key, type); } catch (e) { return null; }
}
async function kvPut(env, key, value, ttlS) {
  const kv = env && env.REPLAY;
  if (!kv || typeof kv.put !== 'function') return false;
  try { await kv.put(key, value, { expirationTtl: Math.max(60, Math.ceil(ttlS)) }); return true; } catch (e) { return false; }
}
const callsKey = (id, day) => `datago:calls:${id}:${day}`;
const coolKey = id => `datago:cool:${id}`;
const errKey = id => `datago:err:${id}`;

/* ── daily call counter (approximate across colos: KV is last-write-wins, isolates keep a floor) ── */
const MEM_CALLS = new Map();                        // calls key → count this isolate knows of
// env.DATAGO_CAP (a number) can only lower every API's cap; "0" stops all calls (a kill switch that keeps serving the KV copies)
export function dgCap(env, api) {
  const raw = env && env.DATAGO_CAP;
  const lim = raw == null || String(raw).trim() === '' ? NaN : +raw;
  return Math.max(0, Math.min(api.cap || 1000, isFinite(lim) && lim >= 0 ? Math.floor(lim) : Infinity));
}
async function callsRead(env, id, day) {
  const v = +(await kvGet(env, callsKey(id, day))) || 0;
  return Math.max(v, MEM_CALLS.get(callsKey(id, day)) || 0);
}

/* ── one refresh ─────────────────────────────── */
export class DgRun {
  constructor(env, api, opt = {}) {
    this.env = env || {};
    this.api = api;
    this.key = dgKey(this.env);
    this.day = kstYmd(Date.now());
    this.calls = 0;
    this.base = null;
    this.errors = [];                               // non-fatal failures (one op of several), recorded by dgSnapshot
    this.timeoutMs = opt.timeoutMs || DG_TIMEOUT_MS;
    this.maxCalls = Math.min(opt.maxCalls || MAX_CALLS_PER_RUN, MAX_CALLS_PER_RUN);
    this.cap = dgCap(this.env, api);
  }
  async budget() {
    if (!this.key) throw new DgErr('nokey');
    if (this.base == null) this.base = await callsRead(this.env, this.api.id, this.day);
    if (this.base + this.calls >= this.cap || this.calls >= this.maxCalls) throw new DgErr('cap');
  }
  // one page → {items, total, pageNo, numOfRows}
  async call(op, params = {}, opt = {}) {
    await this.budget();
    const numOfRows = Math.max(1, Math.min(DG_MAX_ROWS, Math.floor(+opt.numOfRows || +params.numOfRows || 100)));
    const pageNo = Math.max(1, Math.floor(+opt.pageNo || +params.pageNo || 1));
    const url = dgUrl(this.api, op, { ...params, numOfRows, pageNo }, this.key);
    this.calls++;
    MEM_CALLS.set(callsKey(this.api.id, this.day), this.base + this.calls);
    try {
      const r = await dgFetch(url, opt.timeoutMs || this.timeoutMs);
      const { items, total } = dgParse(r.status, r.ctype, r.text);
      return { items, total, pageNo, numOfRows };
    } catch (e) {
      if (e instanceof DgErr) { e.op = e.op || op; if (e.msg) e.msg = scrub(e.msg, this.env); throw e; }
      throw new DgErr('internal', { op });
    }
  }
  // every page (stops at maxPages; `partial` when the total was not reached)
  async list(op, params = {}, opt = {}) {
    const numOfRows = Math.max(1, Math.min(DG_MAX_ROWS, Math.floor(+opt.numOfRows || 1000)));
    const maxPages = Math.max(1, Math.min(opt.maxPages || 5, 20));
    const items = [];
    let total = 0, pages = 0;
    for (let pageNo = 1; pageNo <= maxPages; pageNo++) {
      const r = await this.call(op, params, { ...opt, numOfRows, pageNo });
      pages++;
      total = r.total;
      items.push(...r.items);
      if (!r.items.length || items.length >= total || r.items.length < numOfRows) break;
    }
    return { items, total, pages, partial: items.length < total };
  }
  async finish() {
    if (!this.calls) return;
    const k = callsKey(this.api.id, this.day);
    const n = (this.base || 0) + this.calls;
    MEM_CALLS.set(k, Math.max(n, MEM_CALLS.get(k) || 0));
    await kvPut(this.env, k, String(n), CALLS_TTL_S);
  }
}

/* ── failures: cool-down for every colo + a diagnostics record (like news:err) ── */
const MEM_COOL = new Map();                         // api id → {code, until}
async function coolGet(env, id, now) {
  const m = MEM_COOL.get(id);
  if (m && m.until > now) return m;
  const v = await kvGet(env, coolKey(id), 'json');
  if (v && +v.until > now) { MEM_COOL.set(id, v); return v; }
  return null;
}
export async function dgNote(env, api, err, now = Date.now()) {
  const code = err && err.code ? err.code : 'internal';
  if (code === 'nokey') return;                     // configuration, not an upstream failure: nothing to cool down
  const s = coolSeconds(code, now);
  const until = now + s * 1000;
  MEM_COOL.set(api.id, { code, until });
  const rec = { at: kstIso(now), api: api.id, code, ...(err.op ? { op: String(err.op).slice(0, 60) } : {}),
    ...(err.status ? { status: err.status } : {}), ...(err.resultCode ? { resultCode: err.resultCode } : {}), ...(err.msg ? { msg: err.msg } : {}), coolUntil: kstIso(until) };
  const safe = scrub(JSON.stringify(rec), env);
  await kvPut(env, coolKey(api.id), JSON.stringify({ code, until }), s);
  const old = await kvGet(env, errKey(api.id), 'json');
  if (old && old.code === code && now - Date.parse(old.at) < ERR_EVERY_MS) return;
  await kvPut(env, errKey(api.id), safe, ERR_TTL_S);
}

/* ── the snapshot pattern ─────────────────────────────── */
// spec = { api, key (KV key), ttlS, due(snap, now) → bool, build(prev, run, now) → object, memMs?, background?, timeoutMs?, maxCalls? }
// build() returns the new snapshot body ({basDt, …}; `at` is added here); it throws DgErr to keep the previous copy, or
// returns {…, partial:[ops]} after calling run.errors.push(err) for the parts that failed (the rest is new).
const MEM_SNAP = new Map(), INFLIGHT = new Map();
export async function dgSnapshot(env, ctx, spec) {
  env = env || {};
  const now = Date.now();
  const m = MEM_SNAP.get(spec.key);
  let snap = m && now - m.readAt < (spec.memMs || 60e3) ? m.snap : null;
  if (!snap) {
    snap = await kvGet(env, spec.key, 'json');
    if (snap && typeof snap !== 'object') snap = null;
    MEM_SNAP.set(spec.key, { snap, readAt: now });
  }
  if (snap && !spec.due(snap, now)) return { snap, stale: false };
  if (!dgKey(env)) return { snap, stale: !!snap, error: 'nokey' };
  const cool = await coolGet(env, spec.api.id, now);
  if (cool) return { snap, stale: !!snap, error: cool.code, cool: true };
  const go = () => dgRefresh(env, spec, snap);
  if (snap && spec.background && ctx && typeof ctx.waitUntil === 'function') { ctx.waitUntil(go()); return { snap, stale: false, refreshing: true }; }
  return go();
}
function dgRefresh(env, spec, prev) {
  if (INFLIGHT.has(spec.key)) return INFLIGHT.get(spec.key);
  const p = (async () => {
    const run = new DgRun(env, spec.api, spec);
    try {
      const body = await spec.build(prev, run, Date.now());
      const snap = { ...body, at: Date.now() };
      await kvPut(env, spec.key, JSON.stringify(snap), spec.ttlS || 10 * 86400);
      MEM_SNAP.set(spec.key, { snap, readAt: Date.now() });
      if (run.errors.length) await dgNoteSoft(env, spec.api, run.errors[0]);
      return { snap, stale: false, ...(body.partial && body.partial.length ? { partial: body.partial } : {}) };
    } catch (e) {
      const err = e instanceof DgErr ? e : new DgErr('internal');      // a bug in build(): never echo its message
      await dgNote(env, spec.api, err);
      return { snap: prev, stale: !!prev, error: err.code };
    } finally {
      try { await run.finish(); } catch (e) { /* counter is best effort */ }
      INFLIGHT.delete(spec.key);
    }
  })();
  INFLIGHT.set(spec.key, p);
  return p;
}
// a part failed but the snapshot was renewed: record it, no cool-down (the next due() retries anyway)
async function dgNoteSoft(env, api, err) {
  const now = Date.now();
  const rec = { at: kstIso(now), api: api.id, code: err.code || 'internal', partial: true, ...(err.op ? { op: String(err.op).slice(0, 60) } : {}),
    ...(err.status ? { status: err.status } : {}), ...(err.resultCode ? { resultCode: err.resultCode } : {}), ...(err.msg ? { msg: err.msg } : {}) };
  const old = await kvGet(env, errKey(api.id), 'json');
  if (old && old.code === rec.code && now - Date.parse(old.at) < ERR_EVERY_MS) return;
  await kvPut(env, errKey(api.id), scrub(JSON.stringify(rec), env), ERR_TTL_S);
}

/* ── status (no secrets: counters, cool-downs, the last error record, snapshot ages) ── */
export async function dgApiStatus(env, api, now = Date.now()) {
  const day = kstYmd(now);
  const [calls, cool, err] = await Promise.all([callsRead(env, api.id, day), kvGet(env, coolKey(api.id), 'json'), kvGet(env, errKey(api.id), 'json')]);
  return { name: api.name, calls, cap: dgCap(env, api), cool: cool && +cool.until > now ? { code: cool.code, until: kstIso(+cool.until) } : null, lastError: err || null };
}
export async function dgPeek(env, key) { return kvGet(env, key, 'json'); }
// a new isolate (tests: qa/datago/*.mjs) — module memory only; KV stays
export function dgResetMemory() { MEM_CALLS.clear(); MEM_COOL.clear(); MEM_SNAP.clear(); INFLIGHT.clear(); }

/* ── responses (same headers as index.js json()) ─────────────────────────────── */
export function dgJson(body, status = 200, maxAge = 0, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': maxAge ? `public, max-age=${maxAge}` : 'no-store',
      'access-control-allow-origin': ORIGIN,
      ...extra,
    },
  });
}
// edge cache (Cache API) for a produced JSON body: produce() → {body, ttl} (ttl 0 → not cached)
export async function dgEdge(request, ctx, key, produce) {
  const cache = typeof caches !== 'undefined' && caches.default;
  const cacheKey = new Request(new URL('/__cache/' + key, request.url).toString());
  if (cache) { const hit = await cache.match(cacheKey); if (hit) return hit; }
  const { body, ttl, status = 200 } = await produce();
  const res = dgJson(body, status, status === 200 ? ttl : 0);
  if (cache && status === 200 && ttl > 0) {
    const put = cache.put(cacheKey, res.clone());
    if (ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(put); else await put;
  }
  return res;
}
