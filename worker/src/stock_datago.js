// 종목 페이지 공공데이터포털 (AGENTS §3 종목 페이지 API · §3-32 ②④⑤, docs/standards/datago.md §5-2) — index.js hands over
//   GET /api/stock/{code}/lending    대차잔고 (금융위원회_주식대차정보 getStLendAndBorrItemRank_V2), 약 60영업일, 오래된 순
//   GET /api/stock/{code}/corp       기업 기본 (금융위원회_기업기본정보 getCorpOutline_V2 · getAffiliate_V2 · getConsSubsComp_V2)
//   GET /api/stock/{code}/dividend   배당 내역 (금융위원회_주식배당정보 getDiviInfo_V2 — the calendar's DG_APIS.divi)
//
// The FSC loads these once a day (대차 · 배당: after 13:00 of the next business day, 기업기본: 13:00 the same day), so nothing here
// calls upstream per request. Everything goes through the shared helper (datago.js: key in the URL only, daily caps, cool-down,
// error records, KV last-good):
//   · 대차: the per-stock operation (getStItemLendAndBorrStatu_V2) can only be filtered by isinCdNm (a name; the 활용가이드 sample
//     shows an ISIN — ambiguous) and has no 금액. The rank operation takes basDt alone and returns every stock of that day with
//     대차잔액. So one shared table: one call a day for all stocks (KV `sdg:lend:d:<YYYYMMDD>` — one line per stock, index
//     `sdg:lend:idx`), filled back to 60 business days a few days per refresh. A stock's series is cut from those day strings once
//     per new day (KV `sdg:lend:<code>`). Upstream calls do not grow with the number of stocks viewed.
//   · 기업 · 배당: per company (법인등록번호 from datago_crno.js; a preferred share uses its common share's), KV
//     `sdg:corp:<code>` · `sdg:divi:<code>` (code = the common share), refreshed at most once per KST day, and only when a new
//     13:10 publication exists since the last try. A failed refresh with an older copy keeps that copy (stale) and is not retried
//     the same day for that company; without a copy the API's cool-down decides when to try again.
// No crno (ETF, ETN, foreign company, unknown code) → 404 {error:'정보 없음'}. No key / no table yet and nothing cached → 503.
import { DG_APIS, DgErr, dgSnapshot, dgNote, dgEdge, dgJson, dgKey, expectedBasDt, lastWeekdayAt, prevWeekday, kstYmd, kstIso, dashYmd } from './datago.js';
import { crnoTable } from './datago_crno.js';

const CODE_RE = /^[0-9A-Z]{6}$/;
const V = 1;
const EDGE_TTL = 3600, EDGE_STALE_TTL = 600, EDGE_REFRESH_TTL = 120;
const SOURCE = '금융위원회';
const crnoDigits = v => String(v == null ? '' : v).replace(/\D/g, '');
const isinCode = isin => { const m = /^KR7([0-9A-Z]{6})[0-9A-Z]{3}$/.exec(String(isin || '').trim().toUpperCase()); return m ? m[1] : null; };
const ymd8 = v => { const s = String(v == null ? '' : v).replace(/\D/g, ''); return s.length === 8 && +s.slice(4, 6) >= 1 && +s.slice(4, 6) <= 12 && +s.slice(6) >= 1 ? s : null; };
const dash = v => { const s = ymd8(v); return s ? dashYmd(s) : null; };
const num = v => { const s = String(v == null ? '' : v).replace(/,/g, '').trim(); return s !== '' && isFinite(+s) ? +s : null; };
const XML_ENT = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'", nbsp: ' ' };
// the portal's text: "&amp;cr;" / "&cr;" line breaks, entities, NULL placeholders → one clean line
function clean(v, max = 200) {
  let s = String(v == null ? '' : v);
  for (let i = 0; i < 2 && /&amp;/i.test(s); i++) s = s.replace(/&amp;/gi, '&');
  s = s.replace(/&(cr|lf);/gi, ' ').replace(/[\r\n\t]+/g, ' ')
    .replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === '#' ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : +e.slice(1)) : XML_ENT[e.toLowerCase()] || m)
    .replace(/\s+/g, ' ').trim();
  if (/^(null|none|-|n\/a)$/i.test(s)) return '';
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

/* ── KV (REPLAY) — tolerant like datago.js ── */
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

/* ── shared answers ── */
const notFound = () => ({ status: 404, body: { error: '정보 없음' } });
function unavailable(env, code) {
  const c = !dgKey(env) ? 'nokey' : code || 'wait';
  return { status: 503, body: { error: c === 'nokey' ? '공공데이터포털 키가 없어요' : c === 'wait' ? '아직 자료를 받는 중이에요' : '자료를 받지 못했어요', code: c } };
}
const ttlOf = (stale, refreshing) => (stale ? EDGE_STALE_TTL : refreshing ? EDGE_REFRESH_TTL : EDGE_TTL);

// stock code → {info, cc} (cc = the common share: one copy per company) | an answer
async function companyOf(env, ctx, code) {
  const t = await crnoTable(env, ctx);
  if (!t) return { answer: unavailable(env, 'crno') };
  const info = t.get(code);
  if (!info || !info.crno) return { answer: notFound() };
  return { info, cc: info.common || code };
}

/* ── per-company snapshots (기업 · 배당) ─────────────────────────────── */
// at most once per KST day per company, and only when a newer 13:10 publication exists than the last try
export function companyDue(snap, now, crno) {
  if (!snap || snap.v !== V || snap.crno !== crno || (!snap.okAt && !snap.err)) return true;
  if (kstYmd(snap.at || 0) === kstYmd(now)) return false;
  return (snap.at || 0) < lastWeekdayAt(now, 1310);
}
// build() for one company: success → the new body + okAt; failure with an older copy → that copy + err (the helper writes it with
// a new `at`, so the company is not asked again today; dgNote cools the API down and keeps the error record); no copy → throw
function guarded(api, crno, fetchIt) {
  return async (prev, run, now) => {
    try {
      const body = await fetchIt(run, crno, now);
      return { v: V, crno, okAt: Date.now(), ...body };
    } catch (e) {
      const err = e instanceof DgErr ? e : new DgErr('internal');
      if (prev && prev.v === V && prev.crno === crno && prev.okAt) {
        await dgNote(run.env, api, err);
        const { at, ...keep } = prev;
        return { ...keep, err: err.code };
      }
      throw err;
    }
  };
}
const companySpec = (api, kind, cc, crno, fetchIt, maxCalls) => ({
  api, key: `sdg:${kind}:${cc}`, ttlS: 10 * 86400, memMs: 10 * 60e3, background: true, maxCalls,
  due: (snap, now) => companyDue(snap, now, crno), build: guarded(api, crno, fetchIt),
});
const PAGE = 1000;
// every row of this company: the first page and, when there are more, the last one too — whichever way the portal sorts, the
// newest rows are in one of them (both pages are filtered by crno: the filter is the portal's)
async function companyRows(run, op, crno) {
  const first = await run.call(op, { crno }, { numOfRows: PAGE });
  let items = first.items;
  const pages = Math.ceil((first.total || 0) / PAGE);
  if (pages > 1 && first.items.length >= PAGE) {
    const last = await run.call(op, { crno }, { numOfRows: PAGE, pageNo: Math.min(pages, 10000) });
    items = items.concat(last.items);
  }
  return { items: items.filter(x => x && (crnoDigits(x.crno) === crno || x.crno == null || x.crno === '')), total: first.total };
}
// the latest basDt group of a list that keeps one group per 기준일 (계열회사 · 종속기업)
function latestGroup(items) {
  let best = null;
  for (const x of items) { const d = ymd8(x.basDt); if (d && (!best || d > best)) best = d; }
  return { basDt: best, items: best ? items.filter(x => ymd8(x.basDt) === best) : items };
}

/* 기업 기본 */
const CORP_MAX_NAMES = 300;
async function corpFetch(run, crno) {
  const o = await run.call('getCorpOutline_V2', { crno }, { numOfRows: 10 });
  const x = o.items.find(i => crnoDigits(i.crno) === crno) || (o.items.length === 1 && !crnoDigits(o.items[0].crno) ? o.items[0] : null);
  const outline = x ? {
    name: clean(x.corpNm, 120) || null,
    ceo: clean(x.enpRprFnm, 120) || null,
    established: dash(x.enpEstbDt),
    listed: dash(x.enpXchgLstgDt) || dash(x.enpKosdaqLstgDt) || dash(x.enpKrxLstgDt),
    employees: (n => (n != null && n > 0 ? Math.round(n) : null))(num(x.enpEmpeCnt)),
    industry: clean(x.sicNm, 120) || null,
    business: clean(x.enpMainBizNm, 200) || null,
    settleMonth: (m => (m >= 1 && m <= 12 ? m : null))(num(clean(x.enpStacMm))),
    address: [clean(x.enpBsadr, 200), clean(x.enpDtadr, 120).replace(/^,\s*/, '')].filter(Boolean).join(' ') || null,
    homepage: homeUrl(x.enpHmpgUrl),
    opened: ymd8(x.lastOpegDt),
  } : null;
  const partial = [];
  const part = async (key, op, map) => {
    try {
      const r = await companyRows(run, op, crno), g = latestGroup(r.items);
      const seen = new Set(), list = [];
      for (const it of g.items) { const v = map(it); if (v && v.name && !seen.has(v.name)) { seen.add(v.name); list.push(v); } }
      return { basDt: g.basDt, count: list.length, items: list };
    } catch (e) {
      if (!(e instanceof DgErr && e.code === 'cap')) run.errors.push(e instanceof DgErr ? e : new DgErr('internal'));
      partial.push(key);
      return null;
    }
  };
  const ko = (a, b) => a.name.localeCompare(b.name, 'ko');
  const aff = await part('affiliates', 'getAffiliate_V2', it => ({ name: clean(it.afilCmpyNm, 100), listed: /^y/i.test(clean(it.lstgYn)) }));
  if (aff) aff.items = aff.items.sort((a, b) => (b.listed - a.listed) || ko(a, b)).slice(0, CORP_MAX_NAMES);
  const sub = await part('subsidiaries', 'getConsSubsComp_V2', it => ({ name: clean(it.sbrdEnpNm, 100), main: /해당|^y/i.test(clean(it.mainSbrdEnpYnCtt)) && !/미해당|비해당/.test(clean(it.mainSbrdEnpYnCtt)) }));
  if (sub) sub.items = sub.items.sort((a, b) => (b.main - a.main) || ko(a, b)).slice(0, CORP_MAX_NAMES);
  return { outline, affiliates: aff, subsidiaries: sub, ...(partial.length ? { partial } : {}) };
}
function homeUrl(v) {
  let s = clean(v, 200).replace(/\s+/g, '');
  if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s.replace(/^\/+/, '');
  try { const u = new URL(s); return /^https?:$/.test(u.protocol) && /\./.test(u.hostname) ? u.href : null; } catch (e) { return null; }
}
async function corpProduce(env, ctx, code) {
  const who = await companyOf(env, ctx, code);
  if (who.answer) return who.answer;
  const r = await dgSnapshot(env, ctx, companySpec(DG_APIS.corp, 'corp', who.cc, who.info.crno, corpFetch, 8));
  const s = r.snap;
  if (!s || s.v !== V || !s.okAt) return unavailable(env, r.error);
  const stale = !!(r.stale || s.err);
  const o = s.outline || {};
  const { opened, ...outline } = o;
  const basDt = dash(opened) || dash((s.subsidiaries && s.subsidiaries.basDt) || (s.affiliates && s.affiliates.basDt)) || null;
  const lst = g => (g ? { basDt: dash(g.basDt), count: g.count, items: g.items } : null);
  return { ttl: ttlOf(stale, r.refreshing), body: {
    code, name: o.name || who.info.corp || null, basDt, source: SOURCE, asOf: kstIso(s.okAt),
    outline: s.outline ? outline : null, affiliates: lst(s.affiliates), subsidiaries: lst(s.subsidiaries),
    ...(s.partial && s.partial.length ? { partial: s.partial } : {}), ...(stale ? { stale: true } : {}),
  } };
}

/* 배당 */
const DIVI_KEEP = 120, DIVI_YEARS = 6, DIVI_SHOW = 20;
async function diviFetch(run, crno) {
  const r = await companyRows(run, 'getDiviInfo_V2', crno);
  const best = new Map();
  let basDt = null;
  for (const x of r.items) {
    const b = ymd8(x.dvdnBasDt);
    if (!b) continue;
    const d = ymd8(x.basDt);
    if (d && (!basDt || d > basDt)) basDt = d;
    const row = { i: clean(x.isinCd, 12).toUpperCase(), k: clean(x.scrsItmsKcdNm, 20), r: clean(x.stckDvdnRcdNm, 30), b, p: ymd8(x.cashDvdnPayDt), h: ymd8(x.stckHndvDt),
      a: num(x.stckGenrDvdnAmt), g: num(x.stckGrdnDvdnAmt), cr: num(x.stckGenrCashDvdnRt), sr: num(x.stckGenrDvdnRt), d };
    const key = `${row.i || row.k}|${b}|${row.r}`, old = best.get(key);
    if (!old || (row.d || '') >= (old.d || '')) best.set(key, row);              // the same dividend loaded again: the newest load wins
  }
  const rows = [...best.values()].sort((a, b) => b.b.localeCompare(a.b)).slice(0, DIVI_KEEP);
  return { basDt, rows };
}
async function diviProduce(env, ctx, code) {
  const who = await companyOf(env, ctx, code);
  if (who.answer) return who.answer;
  const r = await dgSnapshot(env, ctx, companySpec(DG_APIS.divi, 'divi', who.cc, who.info.crno, diviFetch, 4));
  const s = r.snap;
  if (!s || s.v !== V || !s.okAt) return unavailable(env, r.error);
  const stale = !!(r.stale || s.err);
  const all = Array.isArray(s.rows) ? s.rows : [];
  // this share only: by ISIN when the rows carry one, else by kind (보통주 for a code ending in 0, 우선주 otherwise)
  const byIsin = all.filter(x => isinCode(x.i) === code);
  const anyIsin = all.some(x => isinCode(x.i));
  const pref = code[5] !== '0';
  const mine = anyIsin ? byIsin : all.filter(x => (pref ? /우선/ : /보통/).test(x.k || ''));
  const since = String(+kstYmd(Date.now()).slice(0, 4) - DIVI_YEARS) + '0101';
  const rows = mine.filter(x => x.b >= since).slice(0, DIVI_SHOW).map(x => ({
    recordDate: dashYmd(x.b), payDate: x.p ? dashYmd(x.p) : null, amount: x.a, kind: x.k || null, reason: x.r || null,
    ...(x.h ? { stockDate: dashYmd(x.h) } : {}), ...(x.g > 0 ? { extraAmount: x.g } : {}),
    ...(x.cr != null ? { cashRate: x.cr } : {}), ...(x.sr > 0 ? { stockRate: x.sr } : {}),
  }));
  return { ttl: ttlOf(stale, r.refreshing), body: {
    code, basDt: s.basDt ? dashYmd(s.basDt) : null, source: SOURCE, asOf: kstIso(s.okAt), rows, ...(stale ? { stale: true } : {}),
  } };
}

/* ── 대차잔고: one shared table ─────────────────────────────── */
export const LEND_OP = 'getStLendAndBorrItemRank_V2';
export const LEND_IDX = 'sdg:lend:idx';
export const lendDayKey = d => 'sdg:lend:d:' + d;
const LEND_DAYS = 60;                 // business days with data, for a ~60-day line
const LEND_SCAN = 90;                 // weekdays looked back for them (holidays, days the FSC skipped)
const LEND_FIRST = 3, LEND_PER_RUN = 8;
const LEND_GAP_MS = 2 * 60e3;         // backfill: a few days per refresh, refreshes at least this far apart
const LEND_EMPTY_RETRY_MS = 2 * 3600e3;
const LEND_DAY_TTL_S = 150 * 86400, LEND_IDX_TTL_S = 150 * 86400, LEND_CODE_TTL_S = 4 * 86400;
const LEND_ROWS = 4000;               // ≈ 2,800 stocks a day: one page

// the weekdays still to fetch, newest first: never seen, or seen empty recently enough that it may just have been late
export function lendWant(snap, now) {
  const days = (snap && snap.days) || {}, zero = (snap && snap.zero) || {};
  const out = [];
  let have = 0, d = expectedBasDt(now, 1310);
  for (let i = 0; i < LEND_SCAN && have < LEND_DAYS; i++, d = prevWeekday(d)) {
    if (!(d in days)) { out.push(d); have++; continue; }                        // counted as if it has rows: a holiday shows up next time
    if (days[d] > 0) { have++; continue; }
    if (i < 3 && now - (zero[d] || 0) > LEND_EMPTY_RETRY_MS) out.push(d);
  }
  return out;
}
export function lendDue(snap, now) {
  if (!snap || snap.v !== V || !snap.days) return true;
  return lendWant(snap, now).length > 0 && now - (snap.at || 0) >= LEND_GAP_MS;
}
// one day of the rank list → '\n'-separated lines "key,잔고주수,잔고금액,체결,상환,리콜" (key = 6-char code, else the ISIN)
const lendKey = v => {
  const s = String(v == null ? '' : v).trim().toUpperCase();
  if (/^A?[0-9A-Z]{6}$/.test(s)) return s.slice(-6);
  return isinCode(s) || (/^[A-Z]{2}[0-9A-Z]{10}$/.test(s) ? s : null);
};
const n0 = v => { const x = num(v); return x == null ? '' : String(Math.round(x)); };
export function lendDayText(items) {
  const rows = new Map();
  for (const x of items) {
    const k = lendKey(x.isinCd);
    if (!k || num(x.lnbRmanStckCnt) == null || /채권/.test(String(x.lnbScrtDcdNm || ''))) continue;   // bonds lent are not a stock's 잔고
    const stock = String(x.lnbScrtDcd || '').trim() === '21' || /주식/.test(String(x.lnbScrtDcdNm || ''));
    if (rows.has(k) && !(stock && !rows.get(k).stock)) continue;               // one line per stock (a 주식 row wins)
    rows.set(k, { stock, line: [k, n0(x.lnbRmanStckCnt), n0(x.lnbBal), n0(x.lnbCclStckCnt), n0(x.rdptStckCnt != null ? x.rdptStckCnt : x.lnbRdptStckCnt), n0(x.rcalRdptStckCnt)].join(',') });
  }
  return { text: rows.size ? '\n' + [...rows.values()].map(r => r.line).join('\n') + '\n' : '', n: rows.size };
}
function lendLine(text, key) {
  if (!text) return null;
  const i = text.indexOf('\n' + key + ',');
  if (i < 0) return null;
  const f = text.slice(i + 1, text.indexOf('\n', i + 1)).split(',');
  const v = j => (f[j] === '' || f[j] == null ? null : +f[j]);
  return { shares: v(1), amount: v(2), lent: v(3), repaid: v(4), recall: v(5) };
}
async function lendBuild(prev, run, now) {
  const days = { ...((prev && prev.days) || {}) }, zero = { ...((prev && prev.zero) || {}) };
  const want = lendWant(prev, now).slice(0, prev && prev.days ? LEND_PER_RUN : LEND_FIRST);
  let got = 0;
  for (const d of want) {
    let r;
    try {
      r = await run.list(LEND_OP, { basDt: d }, { numOfRows: LEND_ROWS, maxPages: 2 });
      if (r.partial) throw new DgErr('shape', { op: LEND_OP });                  // paging stopped short: that day is not whole
    } catch (e) {
      if (!got) throw e;                                                        // nothing new: keep the copy, the helper cools down
      if (!(e instanceof DgErr && e.code === 'cap')) run.errors.push(e instanceof DgErr ? e : new DgErr('internal'));
      break;                                                                    // the rest next time
    }
    const { text, n } = lendDayText(r.items);
    if (n && !(await kvPut(run.env, lendDayKey(d), text, LEND_DAY_TTL_S))) { if (!got) throw new DgErr('internal'); break; }
    if (n) { DAY_MEM.delete(d); delete zero[d]; } else zero[d] = Date.now();
    days[d] = n;
    got++;
  }
  // keep the index to the scan window (day strings expire on their own)
  let floor = expectedBasDt(now, 1310);
  for (let i = 0; i < LEND_SCAN + 10; i++) floor = prevWeekday(floor);
  for (const k of Object.keys(days)) if (k < floor) { delete days[k]; delete zero[k]; }
  const latest = Object.keys(days).filter(k => days[k] > 0).sort().pop() || null;
  return { v: V, basDt: latest, days, zero };
}
export const LEND_SPEC = { api: DG_APIS.lend, key: LEND_IDX, ttlS: LEND_IDX_TTL_S, due: lendDue, build: lendBuild, background: true, memMs: 60e3, maxCalls: 20 };

// day strings in isolate memory (≈ 130 KB each): rebuilding many stocks' series in one isolate reads KV once per day
const DAY_MEM = new Map(), DAY_MEM_MAX = 64;
async function lendDay(env, d) {
  if (DAY_MEM.has(d)) { const t = DAY_MEM.get(d); DAY_MEM.delete(d); DAY_MEM.set(d, t); return t; }
  const t = await kvGet(env, lendDayKey(d), 'text');
  if (typeof t === 'string' && t) { DAY_MEM.set(d, t); if (DAY_MEM.size > DAY_MEM_MAX) DAY_MEM.delete(DAY_MEM.keys().next().value); }
  return typeof t === 'string' ? t : null;
}
export function lendResetMemory() { DAY_MEM.clear(); }

async function lendProduce(env, ctx, code) {
  const r = await dgSnapshot(env, ctx, LEND_SPEC);
  const idx = r.snap;
  const dates = idx && idx.v === V && idx.days ? Object.keys(idx.days).filter(d => idx.days[d] > 0).sort().slice(-LEND_DAYS) : [];
  if (!dates.length) return unavailable(env, r.error);
  const last = dates[dates.length - 1];
  const ck = 'sdg:lend:' + code;
  let c = await kvGet(env, ck, 'json');
  if (!(c && c.v === V && c.last === last && c.n === dates.length && Array.isArray(c.rows))) {
    const texts = await Promise.all(dates.map(d => lendDay(env, d)));
    const cut = key => dates.map((d, i) => { const x = lendLine(texts[i], key); return x && x.shares != null ? { date: dashYmd(d), ...x } : null; }).filter(Boolean);
    let rows = cut(code), key = code;
    if (!rows.length) {                                                         // a foreign company: its lines carry the ISIN
      const t = await crnoTable(env, ctx), info = t && t.get(code);
      if (info && info.isin && !isinCode(info.isin)) { rows = cut(info.isin.toUpperCase()); key = info.isin; }
      if (!rows.length && t && !(info && info.crno)) return notFound();         // not a company we know (ETF, ETN …) and never lent
    }
    c = { v: V, last, n: dates.length, key, rows };
    if (texts.every(Boolean)) await kvPut(env, ck, JSON.stringify(c), LEND_CODE_TTL_S);   // a day string missing (KV lag): build again next time
  }
  const rows = c.rows.map(x => ({ date: x.date, shares: x.shares, amount: x.amount, lent: x.lent, repaid: x.repaid, ...(x.recall ? { recall: x.recall } : {}) }));
  const L = rows[rows.length - 1], P = rows[rows.length - 2];
  const latest = L ? { date: L.date, shares: L.shares, amount: L.amount, prevDate: P ? P.date : null,
    change: P ? L.shares - P.shares : null, ratio: P && P.shares > 0 ? Math.round((L.shares / P.shares - 1) * 10000) / 100 : null } : null;
  const stale = !!r.stale;
  return { ttl: ttlOf(stale, r.refreshing), body: {
    code, basDt: dashYmd(last), source: SOURCE, asOf: kstIso(idx.at || Date.now()), days: dates.length, rows, latest, ...(stale ? { stale: true } : {}),
  } };
}

/* ── the route ─────────────────────────────── */
const PRODUCE = { lending: lendProduce, corp: corpProduce, dividend: diviProduce };
export async function stockDatagoRoute(request, env, ctx, code, kind) {
  env = env || {};
  if (!CODE_RE.test(String(code || ''))) return dgJson({ error: '종목 코드가 올바르지 않아요' }, 400);
  const produce = PRODUCE[kind];
  if (!produce) return dgJson({ error: 'not found' }, 404);
  return dgEdge(request, ctx, `sdg-${kind}-${code}`, async () => {
    try { return await produce(env, ctx, code); }
    catch (e) { return { status: 500, body: { error: '처리하다 실패했어요' } }; }   // never e.message (it could carry a URL)
  });
}
