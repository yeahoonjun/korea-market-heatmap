// 한국수출입은행 Open API — 지표 탭 "수출입은행 고시" (AGENTS §3-27 끝 · §3-2, 사용자 2026-11-16 11:33 "그래 추천대로").
//
//   GET /api/koreaexim?kind=fx|rate → {asOf, kind, source, date, today, firstSeen, exact, waiting?, stale?, items, prev}
//     kind=fx    환율 exchangeJSON(data=AP01, secret KOREAEXIM_FX_KEY): items [{code, per, name, base, tts, ttb, change?}] —
//                통화마다 매매기준율(deal_bas_r) · 송금 보낼 때(tts) · 받을 때(ttb), 원. JPY(100) · IDR(100) → per 100, KRW 뺌.
//     kind=rate  국제금리 internationalJSON(data=AP03, secret KOREAEXIM_RATE_KEY): items [{key, family, cur, tenor, months,
//                name, value, raw, bp?}] — SOFR · ESTR · TONA(값이 올 때만) 익일물 + EURIBOR · TIBOR 1 · 3 · 6 · 12개월, 연 %.
//     date       보여 주는 고시일(YYYY-MM-DD, KST) — 오늘 값이 아직 없으면(주말 · 휴일 · 고시 전) 가장 최근 영업일.
//     today      date가 KST 오늘인지.  waiting = 오늘이 평일인데 마지막 확인 때 오늘 값이 아직 없었음.
//     firstSeen  이 Worker가 그날 처음 값을 본 시각 'HH:MM'(KST, 그날 본 것만 — 나중에 거슬러 받은 날은 null). API가 고시
//                시각을 주지 않아요. exact = 그 직전 15분 안에 빈 응답을 봤음 → firstSeen ≈ 고시 시각.
//     prev       그 앞 영업일 값 {date, items} | null — rate의 bp(0.01%p)와 fx의 change(원)는 prev가 있을 때만.
//     stale      새 값을 확인하려던 시도가 실패했거나(쉬는 중 · 하루 상한 · 키 없음) 지난 사본만 있어서 보여 주는 값.
//   GET /api/koreaexim/probe[?d=YYYYMMDD] → {asOf, date, fx:{…}, rate:{…}}   확인용(2026-11-15 20:12 "그래 그렇게하면 되겠네")
//
// 호출 아끼기: 고시일마다 KV REPLAY `kxim:d:<kind>:<YYYYMMDD>` 사본(40일, 빈 지난날은 빈 표시) — 그날 값이 있으면 다시
// 부르지 않아요. 오늘 값이 없을 때만 평일 10:30 전 60분 · 10:30~14:00 5분 · 그 뒤 30분 간격으로 다시 확인(마지막 빈 확인
// `kxim:st:<kind>`), 주말은 부르지 않아요. 지난날은 한 번 받으면 끝(주말은 건너뜀). 원천 호출은 종류마다 KST 하루 120번까지
// (`kxim:n:<kind>:<날짜>`, 확인용 probe의 60번 `kxim:calls:*`과 따로), 한 요청에서 지난날 6번까지. 실패하면 쉬어요
// (`kxim:cool:<kind>`: 인증 · DATA 코드 오류 60분, 하루 한도 → KST 자정까지, 그 밖 10분), 기록 `kxim:err:<kind>`(3일, 키 없음).
// 가장 최근 사본 `kxim:last:<kind>`는 원천이 막혀도 내줄 값(stale). 엣지 캐시: 오늘 값 10분 · 고시를 기다리는 10:30~14:00
// 2분 · 그 밖 5분(언제나 KST 자정까지만). 하나도 없으면 503 {error, code}(캐시 안 함).
// 키는 응답 · KV · 로그 어디에도 남지 않아요 — URL은 fetch에만 쓰고 버리고, 남기는 글자는 scrub()을 거쳐요.
import { kstParts, kstYmd, dashYmd, addDays, isWeekday, kstIso, nextKstMidnight, dgEdge, dgJson } from './datago.js';

const BASE = 'https://oapi.koreaexim.go.kr/site/program/financial/';
const APIS = { fx: { path: 'exchangeJSON', data: 'AP01', key: 'KOREAEXIM_FX_KEY' }, rate: { path: 'internationalJSON', data: 'AP03', key: 'KOREAEXIM_RATE_KEY' } };
const UA = 'PanseBot/1.0 (+https://panse.pages.dev)';
const RESULT = { 1: '성공', 2: 'DATA 코드 오류', 3: '인증 코드 오류', 4: '하루 한도 초과' };
const RESULT_CODE = { 2: 'data', 3: 'auth', 4: 'limit' };
const secretsOf = env => Object.values(APIS).map(a => env && env[a.key]).filter(k => typeof k === 'string' && k.length >= 6);
const scrub = (s, secrets) => { let t = String(s == null ? '' : s); for (const k of secrets) if (k) t = t.split(k).join('***').split(encodeURIComponent(k)).join('***'); return t.replace(/authkey=[^&\s"'<>]*/gi, 'authkey=***'); };

/* ───────── 정식 경로 /api/koreaexim?kind=fx|rate ───────── */
export const KX = {
  DAY_MAX: 120, WALK_MAX: 6, BACK_DAYS: 10, EXACT_MS: 15 * 60e3, TIMEOUT_MS: 8000,
  DAY_TTL_S: 40 * 86400, ST_TTL_S: 2 * 86400, ERR_TTL_S: 3 * 86400,
};
const dayKey = (kind, ymd) => `kxim:d:${kind}:${ymd}`;
const stKey = kind => `kxim:st:${kind}`;
const nKey = (kind, day) => `kxim:n:${kind}:${day}`;
const coolKey = kind => `kxim:cool:${kind}`;
const errKey = kind => `kxim:err:${kind}`;
const lastKey = kind => `kxim:last:${kind}`;

class KxErr extends Error { constructor(code, extra = {}) { super(code); this.code = code; Object.assign(this, extra); } }

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

// a day copy never changes once written (values, or "nothing that day" for a past day): this isolate keeps them
const MEM_DAY = new Map(), MEM_N = new Map(), MEM_COOL = new Map(), INFLIGHT = new Map();
const MEM_DAY_MAX = 80;
function memDay(k, v) { MEM_DAY.delete(k); MEM_DAY.set(k, v); if (MEM_DAY.size > MEM_DAY_MAX) MEM_DAY.delete(MEM_DAY.keys().next().value); }
export function kxResetMemory() { MEM_DAY.clear(); MEM_N.clear(); MEM_COOL.clear(); INFLIGHT.clear(); }

async function dayGet(env, kind, ymd) {
  const k = dayKey(kind, ymd);
  if (MEM_DAY.has(k)) return MEM_DAY.get(k);
  const v = await kvGet(env, k, 'json');
  const ok = v && typeof v === 'object' && (Array.isArray(v.items) || v.empty === true) ? v : null;
  if (ok) memDay(k, ok);
  return ok;
}
async function dayPut(env, kind, ymd, copy) {
  memDay(dayKey(kind, ymd), copy);
  await kvPut(env, dayKey(kind, ymd), JSON.stringify(copy), KX.DAY_TTL_S);
  if (copy.items) {
    const last = await kvGet(env, lastKey(kind), 'json');
    if (!last || !(last.date >= ymd)) await kvPut(env, lastKey(kind), JSON.stringify({ date: ymd }), KX.DAY_TTL_S);
  }
}

/* numbers come as text with thousands commas ("1,333.7"); null / '' → null */
const num = v => {
  if (v == null) return null;
  const s = String(v).replace(/,/g, '').trim();
  if (!s || !/^[-+]?\d+(\.\d+)?$/.test(s)) return null;
  const n = +s;
  return isFinite(n) ? n : null;
};
const resultErr = c => new KxErr(RESULT_CODE[c] || 'result', { result: c });

// 환율: [{result, cur_unit:'USD'|'JPY(100)', cur_nm, ttb, tts, deal_bas_r, bkpr, kftc_*}] — [] on a day without a posting
export function parseFx(j) {
  if (j == null || (Array.isArray(j) && !j.length)) return { empty: true };
  if (!Array.isArray(j)) { if (typeof j === 'object' && j.result != null && +j.result !== 1) throw resultErr(+j.result); throw new KxErr('shape'); }
  const bad = j.map(x => (x && typeof x === 'object' ? +x.result : NaN)).find(c => c !== 1);
  if (bad !== undefined) throw resultErr(bad);
  const items = [], seen = new Set();
  for (const x of j) {
    const m = /^([A-Z]{3})(?:\s*\((\d+)\))?$/.exec(String(x.cur_unit || '').trim());
    if (!m || m[1] === 'KRW' || seen.has(m[1])) continue;
    const base = num(x.deal_bas_r);
    if (base == null || base <= 0) continue;
    seen.add(m[1]);
    const tts = num(x.tts), ttb = num(x.ttb);
    items.push({ code: m[1], per: m[2] ? +m[2] : 1, name: String(x.cur_nm || m[1]).trim().slice(0, 40), base, tts: tts > 0 ? tts : null, ttb: ttb > 0 ? ttb : null });
  }
  if (!items.length) throw new KxErr('shape');
  return { items };
}

// 국제금리: {result, sofr_list:[{cur_fund, sfln_intrc_nm:'SOFR 익일물', int_r:'3.9'}], estr_list, euribor_list ('EURIBOR1개월' …),
// tona_list, tibor_list ('TIBOR 1개월' …), swapRfr_list, swap_list, libor_list, cirr_list, new_cirr_list}. Only the five benchmark
// lists are kept. int_r null / '' / 0 = no value (the source sends 0 for a missing swap rate). An empty day: every list empty.
const FAMILIES = [['sofr_list', 'SOFR'], ['estr_list', 'ESTR'], ['tona_list', 'TONA'], ['euribor_list', 'EURIBOR'], ['tibor_list', 'TIBOR']];
const FAM_CUR = { SOFR: 'USD', ESTR: 'EUR', TONA: 'JPY', EURIBOR: 'EUR', TIBOR: 'JPY' };
function tenorOf(name) {
  if (/익일|O\/?N\b|overnight/i.test(name)) return { tenor: '익일', months: 0 };
  let m = /(\d{1,2})\s*개월/.exec(name);
  if (m && +m[1] >= 1 && +m[1] <= 24) return { tenor: `${+m[1]}개월`, months: +m[1] };
  m = /(\d{1,2})\s*(?:년|Y\b)/i.exec(name);
  if (m && +m[1] >= 1 && +m[1] <= 2) return { tenor: `${+m[1] * 12}개월`, months: +m[1] * 12 };
  m = /(\d{1,2})\s*M\b/i.exec(name);
  if (m && +m[1] >= 1 && +m[1] <= 24) return { tenor: `${+m[1]}개월`, months: +m[1] };
  return null;
}
export function parseRate(j) {
  if (j == null || (Array.isArray(j) && !j.length)) return { empty: true };
  if (Array.isArray(j)) {                      // an error answer shaped like the 환율 one
    const bad = j.map(x => (x && typeof x === 'object' ? +x.result : NaN)).find(c => c !== 1);
    if (bad !== undefined && isFinite(bad)) throw resultErr(bad);
    throw new KxErr('shape');
  }
  if (typeof j !== 'object') throw new KxErr('shape');
  if (j.result != null && +j.result !== 1) throw resultErr(+j.result);
  if (!FAMILIES.some(([l]) => l in j)) throw new KxErr('shape');
  const items = [], seen = new Set();
  FAMILIES.forEach(([list, family], fi) => {
    const rows = Array.isArray(j[list]) ? j[list] : [];
    for (const x of rows) {
      if (!x || typeof x !== 'object') continue;
      const value = num(x.int_r);
      if (value == null || value === 0 || Math.abs(value) > 50) continue;
      const name = String(x.sfln_intrc_nm || '').trim();
      const t = tenorOf(name) || (family === 'SOFR' || family === 'ESTR' || family === 'TONA' ? { tenor: '익일', months: 0 } : null);
      if (!t) continue;
      const key = family + (t.months ? t.months + 'M' : 'ON');
      if (seen.has(key)) continue;
      seen.add(key);
      const cur = /^[A-Z]{3}$/.test(String(x.cur_fund || '').trim()) ? String(x.cur_fund).trim() : FAM_CUR[family];
      items.push({ key, family, cur, tenor: t.tenor, months: t.months, name: name.slice(0, 40) || `${family} ${t.tenor}`, value, raw: String(x.int_r).replace(/,/g, '').trim(), fi });
    }
  });
  items.sort((a, b) => a.fi - b.fi || a.months - b.months);
  for (const it of items) delete it.fi;
  return items.length ? { items } : { empty: true };
}

/* daily call counter (approximate across colos: KV is last-write-wins; this isolate keeps a floor) */
async function callsRead(env, kind, day) {
  const k = nKey(kind, day);
  const v = +(await kvGet(env, k)) || 0;
  return Math.max(v, MEM_N.get(k) || 0);
}
async function coolGet(env, kind, now) {
  const m = MEM_COOL.get(kind);
  if (m && m.until > now) return m;
  const v = await kvGet(env, coolKey(kind), 'json');
  if (v && +v.until > now) { MEM_COOL.set(kind, v); return v; }
  return null;
}
function coolSeconds(code, now) {
  if (code === 'limit') return Math.max(60, Math.ceil((nextKstMidnight(now) - now) / 1000));
  if (code === 'auth' || code === 'data') return 3600;
  return 600;
}
async function note(env, kind, err, now, ymd) {
  const code = err && err.code ? err.code : 'internal';
  if (code === 'nokey' || code === 'cap') return;          // configuration / our own cap: nothing to cool down
  const s = coolSeconds(code, now), until = now + s * 1000;
  MEM_COOL.set(kind, { code, until });
  await kvPut(env, coolKey(kind), JSON.stringify({ code, until }), s);
  const rec = { at: kstIso(now), kind, code, date: ymd, ...(err.status ? { status: err.status } : {}), ...(err.result != null ? { result: err.result } : {}), coolUntil: kstIso(until) };
  await kvPut(env, errKey(kind), scrub(JSON.stringify(rec), secretsOf(env)), KX.ERR_TTL_S);
}

// one upstream call for one day → {items} | {empty:true}; throws KxErr (never with the URL or the key in it)
async function upstream(env, kind, ymd) {
  const api = APIS[kind], key = env[api.key];
  if (typeof key !== 'string' || !key.trim()) throw new KxErr('nokey');
  const url = `${BASE}${api.path}?authkey=${encodeURIComponent(key.trim())}&searchdate=${ymd}&data=${api.data}`;
  let r, text;
  try {
    r = await fetch(url, { signal: AbortSignal.timeout(KX.TIMEOUT_MS), headers: { 'user-agent': UA, accept: 'application/json' } });
    text = await r.text();
  } catch (e) {
    throw new KxErr(e && (e.name === 'TimeoutError' || e.name === 'AbortError') ? 'timeout' : 'network');
  }
  if (!r.ok) throw new KxErr('http', { status: r.status });
  let j;
  try { j = JSON.parse(text); } catch (e) { throw new KxErr('json', { status: r.status }); }
  return kind === 'fx' ? parseFx(j) : parseRate(j);
}

// a request's budget: upstream calls this request may still make (cool-down, daily cap, walk limit)
class Run {
  constructor(env, kind, now) { this.env = env; this.kind = kind; this.now = now; this.day = kstYmd(now); this.calls = 0; this.base = null; this.err = null; this.blocked = null; }
  async fetchDay(ymd) {
    if (this.err || this.blocked) return null;
    const cool = await coolGet(this.env, this.kind, this.now);
    if (cool) { this.blocked = cool.code; return null; }
    if (this.base == null) this.base = await callsRead(this.env, this.kind, this.day);
    if (this.base + this.calls >= KX.DAY_MAX) { this.blocked = 'cap'; return null; }
    this.calls++;
    MEM_N.set(nKey(this.kind, this.day), Math.max(this.base + this.calls, MEM_N.get(nKey(this.kind, this.day)) || 0));
    try {
      return await upstream(this.env, this.kind, ymd);
    } catch (e) {
      const err = e instanceof KxErr ? e : new KxErr('internal');
      if (err.code === 'nokey') this.blocked = 'nokey'; else this.err = err;
      await note(this.env, this.kind, err, this.now, ymd);
      return null;
    }
  }
  async finish() {
    if (!this.calls) return;
    const k = nKey(this.kind, this.day), n = (this.base || 0) + this.calls;
    MEM_N.set(k, Math.max(n, MEM_N.get(k) || 0));
    await kvPut(this.env, k, String(n), KX.ST_TTL_S);
  }
  get failed() { return this.err ? this.err.code : this.blocked; }
}

// how long an empty "today" answer stands before asking again (weekdays): the posting is around 11:00 KST
const todayEvery = hm => (hm < 1030 ? 60 : hm < 1400 ? 5 : 30) * 60e3;

// the latest posting day before `from` with values: KV copies first, then the source (weekends skipped, empty days remembered)
async function walkBack(run, from, walk) {
  const { env, kind } = run;
  let d = from;
  for (let i = 0; i < KX.BACK_DAYS; i++) {
    d = addDays(d, -1);
    if (!isWeekday(d)) continue;
    const c = await dayGet(env, kind, d);
    if (c && c.items) return { date: d, copy: c };
    if (c && c.empty) continue;
    if (walk.n >= KX.WALK_MAX) return null;               // an unknown day: stop here rather than skip over it
    walk.n++;
    const got = await run.fetchDay(d);
    if (!got) return null;
    if (got.items) { const copy = { items: got.items, seen: null, exact: false }; await dayPut(env, kind, d, copy); return { date: d, copy }; }
    await dayPut(env, kind, d, { empty: true, at: run.now });
  }
  return null;
}

const hhmm = ms => { const k = kstParts(ms); return `${String(k.hh).padStart(2, '0')}:${String(k.mi).padStart(2, '0')}`; };
const r2 = v => Math.round(v * 100) / 100;
function withPrev(kind, items, prev) {
  if (!prev) return items;
  if (kind === 'rate') {
    const p = new Map(prev.copy.items.map(it => [it.key, it.value]));
    return items.map(it => (p.has(it.key) ? { ...it, bp: r2((it.value - p.get(it.key)) * 100) } : it));
  }
  const p = new Map(prev.copy.items.map(it => [it.code, it.base]));
  return items.map(it => (p.has(it.code) ? { ...it, change: r2(it.base - p.get(it.code)) } : it));
}

export async function kxServe(env, kind, now = Date.now()) {
  env = env || {};
  const run = new Run(env, kind, now);
  const today = run.day, k = kstParts(now), walk = { n: 0 };
  let latest = null, ld = null, waiting = false, wantedToday = false;
  try {
    const tc = await dayGet(env, kind, today);
    if (tc && tc.items) { latest = tc; ld = today; }
    else if (isWeekday(today)) {
      const st = await kvGet(env, stKey(kind), 'json');
      const lastEmpty = st && st.day === today ? +st.emptyAt || 0 : 0;
      if (now - lastEmpty >= todayEvery(k.hm)) {
        wantedToday = true;
        const got = await run.fetchDay(today);
        if (got && got.items) {
          // KV may lag between colos: keep a copy another colo already wrote (its firstSeen is the earlier one)
          const again = await kvGet(env, dayKey(kind, today), 'json');
          const copy = again && Array.isArray(again.items) ? again
            : { items: got.items, seen: now, exact: !!lastEmpty && now - lastEmpty <= KX.EXACT_MS };
          await dayPut(env, kind, today, copy);
          latest = copy; ld = today;
        } else if (got && got.empty) {
          await kvPut(env, stKey(kind), JSON.stringify({ day: today, emptyAt: now }), KX.ST_TTL_S);
          waiting = true;
        }
      } else waiting = true;
    }
    let fromLast = false;
    if (!latest) {
      const f = await walkBack(run, today, walk);
      if (f) { latest = f.copy; ld = f.date; }
    }
    if (!latest) {                                          // the source is out of reach: the most recent copy there is
      const last = await kvGet(env, lastKey(kind), 'json');
      const c = last && /^\d{8}$/.test(last.date) ? await dayGet(env, kind, last.date) : null;
      if (c && c.items) { latest = c; ld = last.date; fromLast = true; }
    }
    if (!latest) {
      const code = run.failed || 'nodata';
      return { status: 503, body: { error: code === 'nokey' ? '수출입은행 키가 없어요' : '수출입은행 고시를 아직 받지 못했어요', code } };
    }
    const prev = await walkBack(run, ld, walk);
    const isToday = ld === today;
    const seenThatDay = latest.seen && kstYmd(latest.seen) === ld;
    // stale: an older day because today could not be checked (error · cool-down · cap · no key), or a copy the walk could not confirm
    const stale = !isToday && (fromLast || (wantedToday && !waiting));
    const body = {
      asOf: kstIso(now), kind, source: '한국수출입은행', date: dashYmd(ld), today: isToday,
      firstSeen: seenThatDay ? hhmm(latest.seen) : null, exact: !!(seenThatDay && latest.exact),
      ...(waiting && !isToday ? { waiting: true } : {}),
      ...(stale ? { stale: true } : {}),
      items: withPrev(kind, latest.items, prev),
      prev: prev ? { date: dashYmd(prev.date), items: prev.copy.items } : null,
    };
    return { status: 200, body };
  } finally {
    try { await run.finish(); } catch (e) { /* the counter is best effort */ }
  }
}

// edge seconds: today's values 10 min, waiting for the posting (weekdays 10:30–14:00) 2 min, otherwise 5 min — never past midnight
export function kxTtl(body, now) {
  const k = kstParts(now);
  const toMidnight = Math.floor((nextKstMidnight(now) - now) / 1000);
  const win = k.wd >= 1 && k.wd <= 5 && k.hm >= 1030 && k.hm < 1400;
  const base = body.today ? 600 : win ? 120 : 300;
  return Math.max(5, Math.min(base, toMidnight));
}

async function serveOnce(env, kind) {
  if (INFLIGHT.has(kind)) return INFLIGHT.get(kind);
  const p = kxServe(env, kind).finally(() => INFLIGHT.delete(kind));
  INFLIGHT.set(kind, p);
  return p;
}

/* ───────── 확인용 /api/koreaexim/probe (그대로, AGENTS §3-27 끝) ─────────
   GET /api/koreaexim/probe[?d=YYYYMMDD] → {asOf, date, fx:{…}, rate:{…}} — 같은 날짜는 KV `kxim:probe:<날짜>`에 10분, 하루 원천
   호출은 KV `kxim:calls:<오늘>`로 60번까지만(넘으면 429). 정식 경로와 계수가 따로예요. */
const TTL = 600, DAY_MAX = 60;
const kstDay = (ms = Date.now()) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'access-control-allow-origin': 'https://panse.pages.dev' },
});

async function one(env, api, date, secrets) {
  const key = env[api.key];
  if (!key) return { ok: false, error: 'no key' };
  const url = `${BASE}${api.path}?authkey=${encodeURIComponent(key)}&searchdate=${date}&data=${api.data}`;
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 8000), t0 = Date.now();
  try {
    const r = await fetch(url, { signal: ac.signal, headers: { 'user-agent': UA, accept: 'application/json' } });
    const text = await r.text();
    const out = { http: r.status, ms: Date.now() - t0, bytes: text.length };
    let rows;
    try { rows = JSON.parse(text); } catch (e) { return { ok: false, ...out, error: 'JSON 아님', head: scrub(text.slice(0, 160), secrets) }; }
    if (rows && !Array.isArray(rows) && typeof rows === 'object') {   // 국제금리: {result, sofr_list:[…], estr_list:[…], euribor_list, tona_list, tibor_list, swapRfr_list, …}
      const lists = {};
      for (const [k, v] of Object.entries(rows)) if (/_list$/.test(k) && Array.isArray(v)) lists[k] = { n: v.length, rows: v.slice(0, 12) };
      const n = Object.values(lists).reduce((a, x) => a + x.n, 0);
      return { ok: r.ok && rows.result === 1 && n > 0, ...out, n, result: [`${rows.result} ${RESULT[rows.result] || ''}`.trim()], lists };
    }
    if (!Array.isArray(rows)) return { ok: false, ...out, error: '배열 아님', head: scrub(JSON.stringify(rows).slice(0, 160), secrets) };
    const codes = [...new Set(rows.map(x => x && x.result))];
    return {
      ok: r.ok && rows.length > 0 && codes.every(c => c === 1), ...out, n: rows.length,
      result: codes.map(c => `${c} ${RESULT[c] || ''}`.trim()),
      fields: rows[0] ? Object.keys(rows[0]) : [],
      rows: rows.slice(0, 40),   // 환율 23개 안팎 · 국제금리 몇 줄 — 값만, 키 없음
    };
  } catch (e) {
    return { ok: false, error: e && e.name === 'AbortError' ? '시간 초과(8초)' : scrub((e && e.message) || e, secrets) };
  } finally { clearTimeout(t); }
}

async function probeRoute(request, env, ctx, url) {
  const d = url.searchParams.get('d');
  if (d && !/^\d{8}$/.test(d)) return json({ error: 'd는 YYYYMMDD' }, 400);
  const date = d || kstDay(), today = kstDay();
  const kv = env.REPLAY, cKey = `kxim:probe:${date}`, nKey0 = `kxim:calls:${today}`;
  const secrets = secretsOf(env);
  if (kv) {
    const hit = await kv.get(cKey, 'json').catch(() => null);
    if (hit && Date.now() - hit.at < TTL * 1000) return json({ ...hit.body, cached: true });
  }
  const used = kv ? +(await kv.get(nKey0).catch(() => null)) || 0 : 0;
  if (used >= DAY_MAX) return json({ error: `오늘 확인 한도(${DAY_MAX}번)를 다 썼어요` }, 429);
  const [fx, rate] = await Promise.all([one(env, APIS.fx, date, secrets), one(env, APIS.rate, date, secrets)]);
  const body = { asOf: new Date().toISOString(), date, fx, rate };
  if (kv) {
    const w = [kv.put(nKey0, String(used + 2), { expirationTtl: 2 * 86400 })];
    if (fx.ok || rate.ok) w.push(kv.put(cKey, JSON.stringify({ at: Date.now(), body }), { expirationTtl: TTL }));
    ctx.waitUntil(Promise.all(w).catch(() => {}));
  }
  return json(body);
}

export async function koreaeximRoute(request, env, ctx, url) {
  env = env || {};
  if (request.method !== 'GET') return json({ error: 'GET으로만 받을 수 있어요' }, 405);
  if (url.pathname === '/api/koreaexim/probe') return probeRoute(request, env, ctx, url);
  const kind = url.searchParams.get('kind') || '';
  if (kind !== 'fx' && kind !== 'rate') return dgJson({ error: 'kind는 fx 또는 rate여야 해요' }, 400);
  return dgEdge(request, ctx, 'kxim-' + kind, async () => {
    const now = Date.now();
    const { status, body } = await serveOnce(env, kind);
    return { status, body, ttl: status === 200 ? kxTtl(body, now) : 0 };
  });
}
