// 증시 자금 (AGENTS §3-32 ①, docs/standards/datago.md §5) — 금융위원회_금융투자협회종합통계정보 for the 지표 tab.
//
//   GET /api/funds                         → {asOf, basDt, source, items:[{key, name, value, change, ratio, unit, basDt, prev, prevDt}], stale?, partial?}
//   GET /api/funds/chart/{key}?tf=3m|1y    → {key, name, tf, unit, bars:[{t:'YYYY-MM-DD', c}]}   (business days, oldest first)
//
// Two operations, each asked once per refresh for the last 400 days (beginBasDt … endBasDt, endBasDt is exclusive):
//   getSecuritiesMarketTotalCapitalInfo (증시자금추이)  → 투자자예탁금 · 위탁매매 미수금 · 반대매매(금액) · 반대매매 비중
//   getGrantingOfCreditBalanceInfo       (신용공여잔고추이) → 신용융자 전체 · 코스피(유가증권) · 코스닥
// Money is 원 upstream → 억원 here (2 decimals); 반대매매 비중 is % (change in %p). change / ratio = against the previous row,
// i.e. the previous business day. Nothing here says up is good or bad: the page colours by direction only.
//
// Caching: KV REPLAY `datago:funds` (the series, about 35 KB, 10 days) is the shared last-good copy; the routes are edge-cached
// 1 h (10 min while stale). A refresh is due when the snapshot is 6 h old, or — when it is behind the business day that should
// be out by now (expectedBasDt) — 30 min old on weekdays 13:00–20:00 KST and 3 h old otherwise. If one operation fails, the
// other's new rows still go in (`partial`, the failed one keeps its previous rows); if both fail, the last copy is served with
// stale:true and the API cools down (datago.js).
import { DG_APIS, DgErr, dgSnapshot, dgEdge, dgJson, expectedBasDt, kstParts, kstYmd, addDays, dashYmd, kstIso } from './datago.js';

export const FUNDS_KEY = 'datago:funds';
const FUNDS_TTL_S = 10 * 86400;
const HISTORY_DAYS = 400;
const OPS = {
  cap: { op: 'getSecuritiesMarketTotalCapitalInfo', fields: { deposit: 'invrDpsgAmt', unpaid: 'brkTrdUcolMny', forced: 'brkTrdUcolMnyVsOppsTrdAmt', forcedRatio: 'ucolMnyVsOppsTrdRlImpt' } },
  credit: { op: 'getGrantingOfCreditBalanceInfo', fields: { credit: 'crdTrFingWhl', creditKospi: 'crdTrFingScrs', creditKosdaq: 'crdTrFingKosdaq' } },
};
// the order on screen; unit '억원' = money (원 ÷ 1e8), '%' = a share
export const FUNDS_ITEMS = [
  { key: 'deposit', name: '투자자예탁금', unit: '억원' },
  { key: 'credit', name: '신용융자 전체', unit: '억원' },
  { key: 'creditKospi', name: '신용융자 코스피', unit: '억원' },
  { key: 'creditKosdaq', name: '신용융자 코스닥', unit: '억원' },
  { key: 'unpaid', name: '위탁매매 미수금', unit: '억원' },
  { key: 'forced', name: '반대매매', unit: '억원' },
  { key: 'forcedRatio', name: '반대매매 비중', unit: '%' },
];
const ITEM = new Map(FUNDS_ITEMS.map(d => [d.key, d]));
const r2 = v => Math.round(v * 100) / 100;
const num = x => {
  if (x == null || x === '') return null;
  const v = +String(x).replace(/,/g, '').trim();
  return isFinite(v) ? v : null;
};

export function fundsDue(snap, now) {
  if (!snap || !snap.series || !snap.at) return true;
  const age = now - snap.at;
  const exp = expectedBasDt(now);
  const dts = Object.values(snap.opDt || {});
  const behind = !dts.length || dts.some(d => !d || d < exp);
  if (!behind) return age >= 6 * 3600e3;
  const k = kstParts(now);
  const window = k.wd >= 1 && k.wd <= 5 && k.hm >= 1300 && k.hm < 2000;
  return age >= (window ? 30 * 60e3 : 3 * 3600e3);
}

function rowsToSeries(items, fields) {
  const by = {};
  for (const f of Object.keys(fields)) by[f] = new Map();
  let last = '';
  for (const it of items) {
    const d = String(it && it.basDt != null ? it.basDt : '').replace(/\D/g, '');
    if (!/^\d{8}$/.test(d)) continue;
    let any = false;
    for (const [key, field] of Object.entries(fields)) {
      const v = num(it[field]);
      if (v == null || v < 0) continue;
      by[key].set(d, ITEM.get(key).unit === '%' ? r2(v) : r2(v / 1e8));
      any = true;
    }
    if (any && d > last) last = d;
  }
  const out = {};
  for (const [key, m] of Object.entries(by)) out[key] = [...m].sort((a, b) => (a[0] < b[0] ? -1 : 1));
  return { series: out, last };
}

async function fundsBuild(prev, run, now) {
  const today = kstYmd(now);
  const params = { beginBasDt: addDays(today, -HISTORY_DAYS), endBasDt: addDays(today, 1) };   // endBasDt: "작은" — exclusive
  const ids = Object.keys(OPS);
  const got = await Promise.allSettled(ids.map(id => run.list(OPS[id].op, params, { numOfRows: 1000, maxPages: 3 })));
  const series = {}, opDt = {}, partial = [];
  let firstErr = null;
  ids.forEach((id, i) => {
    const g = got[i];
    let err = null;
    if (g.status === 'fulfilled') {
      const { series: s, last } = rowsToSeries(g.value.items, OPS[id].fields);
      if (last && !g.value.partial) { Object.assign(series, s); opDt[id] = last; return; }
      err = new DgErr(last ? 'shape' : 'empty', { op: OPS[id].op });
    } else err = g.reason instanceof DgErr ? g.reason : new DgErr('internal', { op: OPS[id].op });
    firstErr = firstErr || err;
    // this operation failed: its rows stay as they were in the previous copy (if any)
    if (prev && prev.series && prev.opDt && prev.opDt[id]) {
      for (const key of Object.keys(OPS[id].fields)) if (prev.series[key]) series[key] = prev.series[key];
      opDt[id] = prev.opDt[id];
    }
    partial.push(id);
    run.errors.push(err);
  });
  if (partial.length === ids.length || !Object.keys(opDt).length) throw firstErr || new DgErr('empty');
  const basDt = Object.values(opDt).sort().pop();
  return { v: 1, basDt, opDt, series, ...(partial.length ? { partial } : {}) };
}
export const FUNDS_SPEC = { api: DG_APIS.kofia, key: FUNDS_KEY, ttlS: FUNDS_TTL_S, due: fundsDue, build: fundsBuild, memMs: 60e3 };

export function fundsBody(snap, res = {}) {
  const items = [];
  for (const d of FUNDS_ITEMS) {
    const s = snap.series && snap.series[d.key];
    if (!Array.isArray(s) || !s.length) continue;
    const [t1, v1] = s[s.length - 1];
    const p = s.length > 1 ? s[s.length - 2] : null;
    items.push({
      key: d.key, name: d.name, value: v1,
      change: p ? r2(v1 - p[1]) : null,
      ratio: p && p[1] ? r2((v1 / p[1] - 1) * 100) : null,
      unit: d.unit, basDt: dashYmd(t1), prev: p ? p[1] : null, prevDt: p ? dashYmd(p[0]) : null,
    });
  }
  const partial = res.partial || snap.partial;
  return {
    asOf: kstIso(snap.at), basDt: snap.basDt ? dashYmd(snap.basDt) : null, source: '금융투자협회', items,
    ...(res.stale ? { stale: true } : {}), ...(partial && partial.length ? { partial } : {}),
  };
}
function chartBody(snap, key, tf, now) {
  const d = ITEM.get(key);
  const s = (snap.series && snap.series[key]) || [];
  const cut = addDays(kstYmd(now), tf === '1y' ? -366 : -92);
  return { key, name: d.name, tf, unit: d.unit, bars: s.filter(x => x[0] >= cut).map(([t, c]) => ({ t: dashYmd(t), c })) };
}
const NO_DATA = '증시 자금 자료를 아직 받지 못했어요';

export async function fundsRoute(request, env, ctx, url) {
  const path = url.pathname;
  if (path === '/api/funds') {
    return dgEdge(request, ctx, 'funds', async () => {
      const res = await dgSnapshot(env, ctx, FUNDS_SPEC);
      if (!res.snap || !res.snap.series) return { status: 503, body: { error: NO_DATA, code: res.error || 'empty' } };
      return { body: fundsBody(res.snap, res), ttl: res.stale ? 600 : 3600 };
    });
  }
  const m = /^\/api\/funds\/chart\/([^/]+)$/.exec(path);
  if (m) {
    const key = m[1];
    if (!ITEM.has(key)) return dgJson({ error: '알 수 없는 항목이에요' }, 400);
    const tf = url.searchParams.get('tf') || '3m';
    if (tf !== '3m' && tf !== '1y') return dgJson({ error: 'tf는 3m 또는 1y여야 해요' }, 400);
    return dgEdge(request, ctx, `funds-ch-${key}-${tf}`, async () => {
      const res = await dgSnapshot(env, ctx, FUNDS_SPEC);
      if (!res.snap || !res.snap.series) return { status: 503, body: { error: NO_DATA, code: res.error || 'empty' } };
      return { body: chartBody(res.snap, key, tf, Date.now()), ttl: res.stale ? 600 : 3600 };
    });
  }
  return dgJson({ error: '없는 경로예요' }, 404);
}
