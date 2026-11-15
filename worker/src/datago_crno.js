// 종목코드 ↔ 법인등록번호 (AGENTS §3-32 ⑥, docs/standards/datago.md §4) — 금융위원회_KRX상장종목정보 getItemInfo_V2.
//
// For the routes that need a 법인등록번호 (crno) to ask the other FSC APIs (대차 · 기업기본 · 배당 · 보호예수 …):
//   await crnoOf(env, '005930', ctx)    → '1301110006246' | null
//   await crnoInfo(env, '005935', ctx)  → {code, crno, isin, name, corp, market, basDt, common?} | null
//   await crnoTable(env, ctx)           → {basDt, at, n, get(code)} | null      (many codes in one request)
// Pass ctx: when the daily refresh is due, the table you get is the current one and the refresh runs in ctx.waitUntil.
// Without ctx a due refresh is awaited (≤ 8 upstream calls).
//
// The table lives in KV REPLAY `datago:crno` ({v, at, basDt, n, withCrno, m:{code:[crno, isin, itmsNm, corpNm, mrktCtg]}},
// about 250 KB, 10 days), fetched at most once per weekday after 13:10 KST (the FSC opens a business day's list after 13:00 of
// the next one). The basDt asked for is the latest that should be out (expectedBasDt); an empty day (holiday) walks back a
// weekday at a time, up to 7. A list less than half the size of the previous one is not trusted (the old table stays).
//
// Preferred shares are not in the source (활용가이드): a code whose last character is not 0 falls back to its common share
// (first five characters + '0', e.g. 005935 → 005930, 00088K → 000880) — same company, same crno — and says `common`.
// Foreign companies have no Korean crno: crno null.
// 공공누리 4유형 + KRX 재배포 금지: the table is used inside the Worker only — no route publishes it.
import { DG_APIS, DgErr, dgSnapshot, expectedBasDt, lastWeekdayAt, prevWeekday, dashYmd } from './datago.js';

export const CRNO_KEY = 'datago:crno';
const CRNO_TTL_S = 10 * 86400;
const CRNO_AFTER_HM = 1310;
const CRNO_BACK = 7;
const CRNO_PAGE = 2000;
const CODE_RE = /^[0-9A-Z]{6}$/;
const OP = 'getItemInfo_V2';

// at most once per weekday, after that weekday's 13:10 KST (the first table any time)
export function crnoDue(snap, now) {
  if (!snap || !snap.m || !snap.at) return true;
  return snap.at < lastWeekdayAt(now, CRNO_AFTER_HM);
}
async function crnoBuild(prev, run, now) {
  let day = expectedBasDt(now);
  for (let i = 0; i < CRNO_BACK; i++, day = prevWeekday(day)) {
    const r = await run.list(OP, { basDt: day }, { numOfRows: CRNO_PAGE, maxPages: 4 });
    if (!r.items.length) continue;                                   // nothing loaded for that day (holiday, not yet opened)
    if (r.partial) throw new DgErr('shape', { op: OP });             // paging stopped short: keep the previous table
    const m = {};
    let n = 0, withCrno = 0;
    for (const it of r.items) {
      const code = String(it.srtnCd == null ? '' : it.srtnCd).trim().replace(/^A/, '');
      if (!CODE_RE.test(code)) continue;
      const crno = String(it.crno == null ? '' : it.crno).replace(/\D/g, '');
      const ok = crno.length === 13;
      m[code] = [ok ? crno : '', String(it.isinCd || '').trim(), String(it.itmsNm || '').trim(), String(it.corpNm || '').trim(), String(it.mrktCtg || '').trim()];
      n++;
      if (ok) withCrno++;
    }
    if (!n) throw new DgErr('shape', { op: OP });
    if (prev && prev.n && n < prev.n * 0.5) throw new DgErr('shape', { op: OP });
    return { v: 1, basDt: day, n, withCrno, m };
  }
  throw new DgErr('empty', { op: OP });
}
export const CRNO_SPEC = { api: DG_APIS.krx, key: CRNO_KEY, ttlS: CRNO_TTL_S, due: crnoDue, build: crnoBuild, background: true, memMs: 10 * 60e3 };

function infoOf(snap, code) {
  code = String(code == null ? '' : code).trim().toUpperCase();
  if (!CODE_RE.test(code) || !snap || !snap.m) return null;
  let hit = snap.m[code], common = null;
  if (!hit && code[5] !== '0') { common = code.slice(0, 5) + '0'; hit = snap.m[common]; }
  if (!hit) return null;
  const [crno, isin, name, corp, market] = hit;
  return { code, crno: crno || null, isin: isin || null, name: name || null, corp: corp || null, market: market || null,
    basDt: snap.basDt ? dashYmd(snap.basDt) : null, ...(common ? { common } : {}) };
}
export async function crnoTable(env, ctx) {
  const { snap } = await dgSnapshot(env, ctx, CRNO_SPEC);
  if (!snap || !snap.m) return null;
  return { basDt: snap.basDt ? dashYmd(snap.basDt) : null, at: snap.at, n: snap.n, get: code => infoOf(snap, code) };
}
export async function crnoInfo(env, code, ctx) {
  const t = await crnoTable(env, ctx);
  return t ? t.get(code) : null;
}
export async function crnoOf(env, code, ctx) {
  const i = await crnoInfo(env, code, ctx);
  return i ? i.crno : null;
}
