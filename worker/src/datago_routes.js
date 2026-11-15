// 공공데이터포털 routes (AGENTS §3-2 · §3-32, docs/standards/datago.md) — index.js hands these paths over in one line:
//   GET /api/funds, /api/funds/chart/{key}?tf=3m|1y   증시 자금 (datago_funds.js)
//   GET /api/datago/status[?warm=1]                   counters, cool-downs, last error records, snapshot ages (no-store) —
//                                                      apis kofia · krx · lend · corp · divi, snapshots funds · crno · lend.
//                                                      warm=1 first runs the snapshots' own due() checks (it never forces a
//                                                      fetch that due() would not make) — handy right after a deploy.
// Nothing here returns the key, a URL with it, or the 법인등록번호 table itself (KRX: no redistribution).
import { DG_APIS, dgApiStatus, dgPeek, dgSnapshot, dgJson, dgKey, kstIso, expectedBasDt, dashYmd } from './datago.js';
import { FUNDS_SPEC, FUNDS_KEY, fundsRoute } from './datago_funds.js';
import { CRNO_SPEC, CRNO_KEY } from './datago_crno.js';
import { LEND_IDX } from './stock_datago.js';

const ymdOrNull = s => (typeof s === 'string' && /^\d{8}$/.test(s) ? dashYmd(s) : null);

export async function datagoRoute(request, env, ctx, url) {
  env = env || {};
  if (url.pathname === '/api/datago/status') {
    if (url.searchParams.get('warm') === '1') {
      await Promise.all([dgSnapshot(env, ctx, FUNDS_SPEC), dgSnapshot(env, null, CRNO_SPEC)]);
    }
    const now = Date.now();
    const [kofia, krx, lend, corp, divi, funds, crno, lendIdx] = await Promise.all([
      dgApiStatus(env, DG_APIS.kofia, now), dgApiStatus(env, DG_APIS.krx, now),
      dgApiStatus(env, DG_APIS.lend, now), dgApiStatus(env, DG_APIS.corp, now), dgApiStatus(env, DG_APIS.divi, now),   // 종목 페이지 (stock_datago.js)
      dgPeek(env, FUNDS_KEY), dgPeek(env, CRNO_KEY), dgPeek(env, LEND_IDX)]);
    return dgJson({
      now: kstIso(now), key: !!dgKey(env), expectedBasDt: dashYmd(expectedBasDt(now)),
      apis: { kofia, krx, lend, corp, divi },
      snapshots: {
        funds: funds && funds.series ? { basDt: ymdOrNull(funds.basDt), at: funds.at ? kstIso(funds.at) : null,
          opDt: Object.fromEntries(Object.entries(funds.opDt || {}).map(([k, v]) => [k, ymdOrNull(v)])),
          points: Object.fromEntries(Object.entries(funds.series).map(([k, v]) => [k, Array.isArray(v) ? v.length : 0])),
          ...(funds.partial ? { partial: funds.partial } : {}) } : null,
        crno: crno && crno.m ? { basDt: ymdOrNull(crno.basDt), at: crno.at ? kstIso(crno.at) : null, n: crno.n, withCrno: crno.withCrno } : null,
        // 대차잔고 공용 표: 받은 영업일 수 · 가장 최근 basDt · 빈 날(휴일 · 늦게 열림) 수
        lend: lendIdx && lendIdx.days ? { basDt: ymdOrNull(lendIdx.basDt), at: lendIdx.at ? kstIso(lendIdx.at) : null,
          days: Object.values(lendIdx.days).filter(n => n > 0).length, empty: Object.values(lendIdx.days).filter(n => !(n > 0)).length,
          rows: lendIdx.basDt ? lendIdx.days[lendIdx.basDt] : 0 } : null,
      },
    });
  }
  return fundsRoute(request, env, ctx, url);
}
