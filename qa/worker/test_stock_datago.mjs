// QA: worker/src/stock_datago.js — 종목 페이지 공공데이터포털 (AGENTS §3 종목 페이지 API · §3-32 ②④⑤): /api/stock/{code}/lending ·
// corp · dividend through the real router (worker/src/index.js). Fake fetch / KV / clock / edge cache from qa/datago/harness.mjs;
// fixtures follow the 활용가이드 response examples (field names, YYYYMMDD strings, numbers as strings, items.item). No network, no key.
//   node qa/worker/test_stock_datago.mjs
import assert from 'node:assert/strict';
import { at, advance, clock, KST, makeKV, net, paged, ok, gateway, KEYS, scanKV, scanLogs, runner, edge, assertNoKey } from '../datago/harness.mjs';
import { dgResetMemory, DG_APIS, addDays, isWeekday } from '../../worker/src/datago.js';
import { lendResetMemory, lendWant, companyDue, LEND_IDX, lendDayKey } from '../../worker/src/stock_datago.js';
import W from '../../worker/src/index.js';

const R = runner('stock datago routes');
const env0 = (kv, extra = {}) => ({ REPLAY: kv, DATA_GO_KR_KEY: KEYS.raw, ...extra });

/* ── the 법인등록번호 table (datago_crno.js copy in KV, fresh so it never refreshes here) ── */
const CRNO = {
  '005930': ['1301110006246', 'KR7005930003', '삼성전자', '삼성전자(주)', 'KOSPI'],
  '000660': ['1101110085251', 'KR7000660001', 'SK하이닉스', 'SK하이닉스(주)', 'KOSPI'],
  '035720': ['1101110017990', 'KR7035720002', '카카오', '(주)카카오', 'KOSPI'],
  '900110': ['', 'HK0000057197', '딥커머스', '딥커머스리미티드', 'KOSDAQ'],          // foreign company: no Korean crno
};
function seedCrno(kv) {
  kv.m.set('datago:crno', { value: JSON.stringify({ v: 1, at: KST('2027-01-01T00:00:00'), basDt: '20261113', n: 4, withCrno: 3, m: CRNO }), exp: null });
}

/* ── 대차: a rank list per business day (getStLendAndBorrItemRank_V2, 활용가이드 1) ── */
const HOLI = new Set(['20261009', '20261005', '20261006', '20261007']);             // 추석 · 한글날: no rows
const DAYS = [];
for (let d = '20260601'; d <= '20261130'; d = addDays(d, 1)) if (isWeekday(d) && !HOLI.has(d)) DAYS.push(d);
const sh = (i, base) => Math.round(base * (1 + 0.1 * Math.sin(i / 5)) + i * 1000);
const LEND = new Map();
DAYS.forEach((d, i) => LEND.set(d, [
  { basDt: d, isinCd: '005930', lnbScrtDcd: '21', lnbScrtDcdNm: '주식', isinCdNm: '삼성전자', lnbCclStckCnt: String(1000 + i), rcalRdptStckCnt: '0', rdptStckCnt: String(900 + i), lnbRmanStckCnt: String(sh(i, 6.4e7)), lnbBal: String(sh(i, 6.4e7) * 70000) + '.000' },
  { basDt: d, isinCd: 'KR7000660001', lnbScrtDcd: '21', lnbScrtDcdNm: '주식', isinCdNm: 'SK하이닉스', lnbCclStckCnt: '5', rcalRdptStckCnt: '1', rdptStckCnt: '7', lnbRmanStckCnt: String(sh(i, 1.2e7)), lnbBal: String(sh(i, 1.2e7) * 180000) },
  { basDt: d, isinCd: 'A005935', lnbScrtDcd: '21', lnbScrtDcdNm: '주식', isinCdNm: '삼성전자우', lnbCclStckCnt: '0', rcalRdptStckCnt: '0', rdptStckCnt: '0', lnbRmanStckCnt: String(sh(i, 2e5)), lnbBal: '' },
  { basDt: d, isinCd: 'HK0000057197', lnbScrtDcd: '21', lnbScrtDcdNm: '주식', isinCdNm: '딥커머스리미티드', lnbCclStckCnt: '0', rcalRdptStckCnt: '0', rdptStckCnt: '0', lnbRmanStckCnt: '146605', lnbBal: '1000' },
  { basDt: d, isinCd: '069500', lnbScrtDcd: '21', lnbScrtDcdNm: '주식', isinCdNm: 'KODEX 200', lnbCclStckCnt: '0', rcalRdptStckCnt: '0', rdptStckCnt: '0', lnbRmanStckCnt: '5000', lnbBal: '0' },
  { basDt: d, isinCd: 'KR6000001231', lnbScrtDcd: '31', lnbScrtDcdNm: '채권', isinCdNm: '어떤 채권', lnbRmanStckCnt: '7' },
]));
const lendRow = (d, code) => LEND.get(d).find(x => x.isinCd.endsWith(code) || x.isinCd === 'KR7' + code + (code === '000660' ? '001' : ''));
let pubLend = '20261113';

/* ── 기업기본 · 배당 (by crno) ── */
const SAMSUNG = '1301110006246';
const OUTLINE = { [SAMSUNG]: { crno: SAMSUNG, corpNm: '삼성전자(주)', corpEnsnNm: 'SAMSUNG ELECTRONICS CO,.LTD', enpRprFnm: '전영현, 노태문', corpDcdNm: '주식회사', bzno: '1248100998',
  enpOzpno: '443742', enpBsadr: '경기도 수원시 영통구 삼성로 129', enpDtadr: ', (매탄동)', enpHmpgUrl: 'www.samsung.com/sec', enpTlno: '0312000114', sicNm: '통신 및 방송 장비 제조업',
  enpEstbDt: '19690113', enpStacMm: '12', enpXchgLstgDt: '19750611', enpKosdaqLstgDt: '', smenpYn: 'N', enpEmpeCnt: '125000', empeAvgCnwkTermCtt: '', enpPn1AvgSlryAmt: '0',
  enpMainBizNm: '반도체&amp;cr;스마트폰 등 제조', fstOpegDt: '20250401', lastOpegDt: '20261113' } };
const AFF = [
  ...['삼성물산(주)', '삼성SDI(주)', '삼성디스플레이(주)'].map((n, i) => ({ basDt: '20250501', crno: SAMSUNG, afilCmpyNm: n, afilCmpyCrno: '11011100' + i, lstgYn: i === 2 ? 'N' : 'Y' })),
  ...['삼성물산(주)', '삼성SDI(주)', '삼성디스플레이(주)', '세메스&amp;cr;(주)'].map((n, i) => ({ basDt: '20260501', crno: SAMSUNG, afilCmpyNm: n, afilCmpyCrno: '11011100' + i, lstgYn: i >= 2 ? 'N' : 'Y' })),
];
const SUBS = [];                                     // 1,200 rows of last year's report + 300 of this year's: two pages of 1,000
for (let i = 0; i < 1200; i++) SUBS.push({ basDt: '20250304', crno: SAMSUNG, sbrdEnpNm: `옛 종속 ${i}`, mainSbrdEnpYnCtt: '미해당' });
for (let i = 0; i < 300; i++) SUBS.push({ basDt: '20260304', crno: SAMSUNG, sbrdEnpNm: i === 0 ? 'VINA FOAM&amp;cr;CO.LTD' : `종속 ${String(i).padStart(3, '0')}`, sbrdEnpEstbDt: '19961005',
  sbrdEnpAdr: 'Khu Pho&amp;cr;Vietnam', sbrdEnpMainBizCtt: '제조', dntRltBsisCtt: '지분율(50%&amp;cr;초과)기준', mainSbrdEnpYnCtt: i % 50 === 1 ? '해당' : '미해당' });
const DIVI = [];
for (let y = 2018; y <= 2026; y++) for (const q of ['0331', '0630', '0930', '1231']) {
  const b = `${y}${q}`;
  if (b > '20260930') continue;
  for (const [isin, kind, amt] of [['KR7005930003', '보통주', y >= 2021 ? 361 : 354], ['KR7005935002', '우선주', y >= 2021 ? 361 : 354]]) {
    const pay = addDays(b, 45);
    for (const load of [addDays(b, 30), addDays(b, 60)]) DIVI.push({ basDt: load, crno: SAMSUNG, isinCd: isin, stckIssuCmpyNm: '삼성전자', dvdnBasDt: b, cashDvdnPayDt: pay, stckHndvDt: '',
      isinCdNm: '삼성전자', stckDvdnRcd: '02', stckDvdnRcdNm: '현금배당', scrsItmsKcd: kind === '보통주' ? '0101' : '0201', scrsItmsKcdNm: kind,
      stckGenrDvdnAmt: String(load === addDays(b, 60) ? amt + (q === '1231' ? 1000 : 0) : amt), stckGrdnDvdnAmt: '0', stckGenrCashDvdnRt: '7.2', stckGenrDvdnRt: '0', stckParPrc: '100', stckStacMd: '12' });
  }
}
const ROWS = { getCorpOutline_V2: p => (OUTLINE[p.crno] ? [OUTLINE[p.crno]] : []), getAffiliate_V2: p => AFF.filter(x => x.crno === p.crno),
  getConsSubsComp_V2: p => SUBS.filter(x => x.crno === p.crno), getDiviInfo_V2: p => DIVI.filter(x => x.crno === p.crno) };
let fail = {};                                        // op → () => response
const handler = (op, params) => {
  if (fail[op]) return fail[op]();
  if (op === 'getStLendAndBorrItemRank_V2') {
    assert.ok(/^\d{8}$/.test(params.basDt), 'basDt');
    return paged(params.basDt <= pubLend && LEND.has(params.basDt) ? LEND.get(params.basDt) : [], params);
  }
  assert.ok(ROWS[op], 'unexpected op ' + op);
  assert.match(params.crno, /^\d{13}$/, 'by 법인등록번호');
  return paged(ROWS[op](params), params);
};
const reset = (t = '2026-11-16T14:00:00') => { dgResetMemory(); lendResetMemory(); net.calls.length = 0; net.handler = handler; fail = {}; pubLend = '20261113'; edge.on = false; edge.store.clear(); edge.puts.length = 0; at(t); };
async function get(env, path) {
  const pending = [];
  const res = await W.fetch(new Request('https://panse.pages.dev' + path), env, { waitUntil: p => pending.push(p) });
  await Promise.all(pending);
  const text = await res.text();
  assertNoKey(text, 'response ' + path);
  return { status: res.status, body: text ? JSON.parse(text) : null, cc: res.headers.get('cache-control'), cors: res.headers.get('access-control-allow-origin') };
}
const calls = op => net.calls.filter(c => !op || c.op === op);

/* ── 대차잔고 ── */
await R.test('lending: first request reads 3 newest business days (basDt, numOfRows 4000, json) → rows oldest first, 주수 · 금액 · 체결 · 상환, change vs the day before; KV day strings + per-stock copy', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const r = await get(env, '/api/stock/005930/lending');
  assert.equal(r.status, 200); assert.equal(r.cc, 'public, max-age=3600'); assert.equal(r.cors, 'https://panse.pages.dev');
  assert.deepEqual(calls().map(c => c.params.basDt), ['20261113', '20261112', '20261111']);
  for (const c of calls()) {
    assert.equal(c.path, '/1160100/GetStocLendBorrInfoService_V2/getStLendAndBorrItemRank_V2');
    assert.equal(c.params.numOfRows, '4000'); assert.equal(c.params.resultType, 'json'); assert.ok(!('crno' in c.params));
  }
  const b = r.body;
  assert.equal(b.code, '005930'); assert.equal(b.basDt, '2026-11-13'); assert.equal(b.source, '금융위원회'); assert.equal(b.days, 3);
  assert.deepEqual(b.rows.map(x => x.date), ['2026-11-11', '2026-11-12', '2026-11-13']);
  const x13 = lendRow('20261113', '005930'), x12 = lendRow('20261112', '005930');
  assert.equal(b.rows[2].shares, +x13.lnbRmanStckCnt); assert.equal(b.rows[2].amount, Math.round(+x13.lnbBal)); assert.equal(b.rows[2].lent, +x13.lnbCclStckCnt); assert.equal(b.rows[2].repaid, +x13.rdptStckCnt);
  assert.deepEqual(b.latest, { date: '2026-11-13', shares: +x13.lnbRmanStckCnt, amount: Math.round(+x13.lnbBal), prevDate: '2026-11-12',
    change: x13.lnbRmanStckCnt - x12.lnbRmanStckCnt, ratio: Math.round((x13.lnbRmanStckCnt / x12.lnbRmanStckCnt - 1) * 10000) / 100 });
  assert.ok(kv.m.has(lendDayKey('20261113')) && kv.ttl(lendDayKey('20261113')) >= 149 * 86400);
  assert.ok(kv.json('sdg:lend:005930')); assert.ok(kv.json(LEND_IDX).days['20261113'] === 6 - 1, 'the bond row has no stock key → 5 lines');
  assert.equal(kv.json('datago:calls:lend:20261116'), 3);
});

await R.test('lending: backfill a few days per refresh (≥ 2 min apart, in the background) to 60 business days, holidays recorded; then nothing until the next 13:10', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  await get(env, '/api/stock/005930/lending');
  let runs = 0;
  for (let i = 0; i < 20; i++) {
    const before = calls().length;
    await get(env, '/api/stock/005930/lending');                       // within 2 min: no refresh
    assert.equal(calls().length, before, 'no refresh inside the gap');
    advance(2 * 60e3);
    await get(env, '/api/stock/005930/lending');
    if (calls().length === before) break;
    assert.ok(calls().length - before <= 8, 'at most 8 days per refresh');
    runs++;
  }
  assert.ok(runs >= 7 && runs <= 9, 'runs ' + runs);
  const idx = kv.json(LEND_IDX);
  assert.equal(Object.values(idx.days).filter(n => n > 0).length, 60);
  assert.equal(idx.days['20261009'], 0, '한글날 known empty');
  const r = await get(env, '/api/stock/005930/lending');
  assert.equal(r.body.rows.length, 60); assert.equal(r.body.days, 60);
  const want = DAYS.filter(d => d <= '20261113').slice(-60).map(d => d.slice(0, 4) + '-' + d.slice(4, 6) + '-' + d.slice(6));
  assert.deepEqual(r.body.rows.map(x => x.date), want, 'the 60 business days, oldest first');
  const total = calls().length;
  assert.ok(total <= 70, 'one-time backfill ≈ 60 + holidays: ' + total);
  // the next morning: nothing new is out yet → no call; after 13:10 → one call for Monday
  at('2026-11-17T10:00:00'); await get(env, '/api/stock/000660/lending'); assert.equal(calls().length, total);
  pubLend = '20261116';
  at('2026-11-17T14:00:00'); await get(env, '/api/stock/000660/lending');
  assert.deepEqual(calls().slice(total).map(c => c.params.basDt), ['20261116']);
  advance(3 * 60e3);
  const r2 = await get(env, '/api/stock/000660/lending');
  assert.equal(r2.body.basDt, '2026-11-16'); assert.equal(r2.body.rows.length, 60); assert.equal(r2.body.rows[59].date, '2026-11-16');
  assert.equal(calls().length, total + 1, 'many stocks, one table: no per-stock calls');
  assert.ok(lendWant(kv.json(LEND_IDX), clock.t).length === 0);
});

await R.test('lending: code keys — short code, KR7 ISIN, A-prefix (preferred), foreign ISIN via the crno table; ETF never in the crno table but lent → served; unknown code → 404 정보 없음; known company never lent → 200 []', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  for (const c of ['000660', '005935', '900110', '069500']) {
    const r = await get(env, `/api/stock/${c}/lending`);
    assert.equal(r.status, 200, c); assert.ok(r.body.rows.length === 3, c);
  }
  assert.equal((await get(env, '/api/stock/005935/lending')).body.rows[2].amount, null, '잔고 금액 missing → null');
  assert.equal((await get(env, '/api/stock/900110/lending')).body.rows[0].shares, 146605);
  const nf = await get(env, '/api/stock/123450/lending');
  assert.equal(nf.status, 404); assert.deepEqual(nf.body, { error: '정보 없음' }); assert.equal(nf.cc, 'no-store');
  const none = await get(env, '/api/stock/035720/lending');
  assert.equal(none.status, 200); assert.deepEqual(none.body.rows, []); assert.equal(none.body.latest, null);
  assert.equal(calls().length, 3, 'all of that from the same 3 day strings');
  assert.equal((await get(env, '/api/stock/abc123/lending')).status, 400);
});

await R.test('lending: upstream error on a due refresh → the old table answers, then stale:true while the API cools down (15 min), error record without the key; edge cache 10 min when stale', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  await get(env, '/api/stock/005930/lending');
  advance(3 * 60e3);
  fail.getStLendAndBorrItemRank_V2 = () => gateway(502, 'Error forwarding request to backend server ' + 'serviceKey=' + KEYS.enc);
  const a = await get(env, '/api/stock/005930/lending');                   // served from the copy while the background refresh fails
  assert.equal(a.status, 200); assert.ok(!a.body.stale);
  const b = await get(env, '/api/stock/005930/lending');
  assert.equal(b.status, 200); assert.equal(b.body.stale, true); assert.equal(b.cc, 'public, max-age=600'); assert.equal(b.body.rows.length, 3);
  assert.equal(kv.json('datago:cool:lend').code, 'upstream'); assert.equal(kv.json('datago:err:lend').code, 'upstream');
  const n = calls().length;
  await get(env, '/api/stock/005930/lending'); assert.equal(calls().length, n, 'cooling: no call');
  scanKV(kv); scanLogs();
});

await R.test('lending: no key and no table → 503 {code:nokey} (no call); DATAGO_CAP=0 → 503 cap before the network; edge cache serves a repeat', async () => {
  reset();
  const kv = makeKV();
  const r = await get({ REPLAY: kv }, '/api/stock/005930/lending');
  assert.equal(r.status, 503); assert.equal(r.body.code, 'nokey'); assert.equal(r.cc, 'no-store'); assert.equal(calls().length, 0);
  const c = await get(env0(makeKV(), { DATAGO_CAP: '0' }), '/api/stock/005930/lending');
  assert.equal(c.status, 503); assert.equal(c.body.code, 'cap'); assert.equal(calls().length, 0);
  reset(); edge.on = true;
  const kv2 = makeKV(), env = env0(kv2); seedCrno(kv2);
  await get(env, '/api/stock/005930/lending');
  const gets = kv2.log.gets;
  const e = await get(env, '/api/stock/005930/lending');
  assert.equal(e.status, 200); assert.equal(kv2.log.gets, gets, 'edge hit: no KV read');
  assert.ok(edge.puts.some(p => /__cache\/sdg-lending-005930$/.test(p.url) && p.ttl === 3600));
});

await R.test('lending: the newest business day opens late (empty) → kept as empty, asked again only after 2 h; the line still ends at the day before', async () => {
  reset();
  pubLend = '20261112';
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const r = await get(env, '/api/stock/005930/lending');
  assert.deepEqual(calls().map(c => c.params.basDt), ['20261113', '20261112', '20261111']);
  assert.equal(r.body.basDt, '2026-11-12'); assert.equal(kv.json(LEND_IDX).days['20261113'], 0);
  advance(3 * 60e3); await get(env, '/api/stock/005930/lending');               // backfill goes on, 11-13 is not asked again yet
  assert.ok(!calls().slice(3).some(c => c.params.basDt === '20261113'));
  pubLend = '20261113';
  advance(2 * 3600e3); await get(env, '/api/stock/005930/lending');
  assert.ok(calls().some((c, i) => i >= 3 && c.params.basDt === '20261113'), '2 h later: asked again');
  advance(3 * 60e3);
  assert.equal((await get(env, '/api/stock/005930/lending')).body.basDt, '2026-11-13');
});

/* ── 기업 기본 ── */
await R.test('corp: three operations by crno (no basDt); outline fields cleaned (&amp;cr;, address, homepage URL); latest 계열회사 · 종속기업 group (first + last page), listed / main first', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const r = await get(env, '/api/stock/005930/corp');
  assert.equal(r.status, 200); assert.equal(r.cc, 'public, max-age=3600');
  const ops = calls().map(c => c.op + ':' + c.params.pageNo);
  assert.deepEqual(ops, ['getCorpOutline_V2:1', 'getAffiliate_V2:1', 'getConsSubsComp_V2:1', 'getConsSubsComp_V2:2']);
  for (const c of calls()) { assert.equal(c.path, '/1160100/service/GetCorpBasicInfoService_V2/' + c.op); assert.equal(c.params.crno, SAMSUNG); assert.ok(!('basDt' in c.params)); }
  const b = r.body;
  assert.equal(b.code, '005930'); assert.equal(b.name, '삼성전자(주)'); assert.equal(b.basDt, '2026-11-13'); assert.equal(b.source, '금융위원회');
  assert.deepEqual(b.outline, { name: '삼성전자(주)', ceo: '전영현, 노태문', established: '1969-01-13', listed: '1975-06-11', employees: 125000, industry: '통신 및 방송 장비 제조업',
    business: '반도체 스마트폰 등 제조', settleMonth: 12, address: '경기도 수원시 영통구 삼성로 129 (매탄동)', homepage: 'http://www.samsung.com/sec' });
  assert.equal(b.affiliates.basDt, '2026-05-01'); assert.equal(b.affiliates.count, 4);
  assert.deepEqual(b.affiliates.items.map(x => [x.name, x.listed]), [['삼성물산(주)', true], ['삼성SDI(주)', true], ['삼성디스플레이(주)', false], ['세메스 (주)', false]]);
  assert.equal(b.subsidiaries.basDt, '2026-03-04'); assert.equal(b.subsidiaries.count, 300);
  assert.equal(b.subsidiaries.items[0].main, true); assert.ok(b.subsidiaries.items.some(x => x.name === 'VINA FOAM CO.LTD'));
  assert.ok(!JSON.stringify(b).includes('&'), 'no entities left'); assert.ok(!JSON.stringify(b).includes(SAMSUNG), 'the crno is not published');
  assert.ok(kv.json('sdg:corp:005930').okAt);
});

await R.test('corp: once per KST day per company — the preferred share uses the common share copy; morning copy is not refreshed that afternoon; next morning yes (background), then not again that day', async () => {
  reset('2026-11-16T10:00:00');
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  await get(env, '/api/stock/005930/corp');
  const n = calls().length;
  assert.equal((await get(env, '/api/stock/005935/corp')).body.code, '005935'); assert.equal(calls().length, n, 'preferred → same company copy');
  at('2026-11-16T14:00:00'); await get(env, '/api/stock/005930/corp'); assert.equal(calls().length, n, 'same day: no call');
  at('2026-11-17T09:00:00');
  const r = await get(env, '/api/stock/005930/corp');
  assert.equal(r.status, 200); assert.equal(r.cc, 'public, max-age=120', 'served while refreshing: short edge TTL');
  assert.equal(calls().length, 2 * n, 'a new publication since the copy → one refresh');
  at('2026-11-17T15:00:00'); await get(env, '/api/stock/005930/corp'); assert.equal(calls().length, 2 * n);
  assert.equal(companyDue(kv.json('sdg:corp:005930'), KST('2026-11-18T13:20:00'), SAMSUNG), true);
  assert.equal(companyDue(kv.json('sdg:corp:005930'), KST('2026-11-18T13:00:00'), SAMSUNG), true, 'Tue 09:00 copy predates Tue 13:10');
  assert.equal(companyDue({ ...kv.json('sdg:corp:005930'), crno: '1' }, clock.t, SAMSUNG), true, 'another crno');
});

await R.test('corp: ETF / unknown / foreign (no crno) → 404 {error:정보 없음} without a call; one list failing → partial; all failing with a copy → stale, not retried that day; without a copy → 503', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  for (const c of ['069500', '900110', '123450']) { const r = await get(env, `/api/stock/${c}/corp`); assert.equal(r.status, 404, c); assert.deepEqual(r.body, { error: '정보 없음' }); }
  assert.equal(calls().length, 0);
  fail.getAffiliate_V2 = () => gateway(500, 'Unexpected error');
  const p = await get(env, '/api/stock/005930/corp');
  assert.equal(p.status, 200); assert.deepEqual(p.body.partial, ['affiliates']); assert.equal(p.body.affiliates, null); assert.equal(p.body.subsidiaries.count, 300);
  assert.equal(kv.json('datago:err:corp').partial, true);
  // next day: everything fails
  fail = { getCorpOutline_V2: () => gateway(503, 'Error receiving response from backend server') };
  at('2026-11-17T14:00:00');
  await get(env, '/api/stock/005930/corp');                                   // old copy while the refresh fails in the background
  const n = calls().length;
  const s = await get(env, '/api/stock/005930/corp');
  assert.equal(s.status, 200); assert.equal(s.body.stale, true); assert.equal(s.cc, 'public, max-age=600'); assert.equal(s.body.outline.employees, 125000);
  at('2026-11-17T18:00:00'); await get(env, '/api/stock/005930/corp'); assert.equal(calls().length, n, 'not again today (cool-down over, copy tried today)');
  const k = await get(env, '/api/stock/000660/corp');                         // no copy at all
  assert.equal(k.status, 503); assert.equal(k.body.code, 'upstream');
  scanKV(kv); scanLogs();
});

/* ── 배당 ── */
await R.test('dividend: getDiviInfo_V2 by crno — reloads of the same dividend collapse (newest load wins), this share only (ISIN), newest first, last 6 years, max 20; preferred share from the same copy', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const r = await get(env, '/api/stock/005930/dividend');
  assert.equal(r.status, 200);
  assert.deepEqual(calls().map(c => c.op + ':' + c.params.pageNo + ':' + c.params.numOfRows), ['getDiviInfo_V2:1:1000']);
  assert.equal(calls()[0].path, '/1160100/GetStocDiviInfoService_V2/getDiviInfo_V2'); assert.equal(calls()[0].params.crno, SAMSUNG);
  const b = r.body;
  assert.equal(b.source, '금융위원회'); assert.equal(b.basDt, '2026-11-29', 'the newest load date');
  assert.equal(b.rows.length, 20);
  assert.equal(b.rows[0].recordDate, '2026-09-30'); assert.equal(b.rows[0].payDate, '2026-11-14'); assert.equal(b.rows[0].amount, 361);
  assert.equal(b.rows[0].kind, '보통주'); assert.equal(b.rows[0].reason, '현금배당'); assert.equal(b.rows[0].cashRate, 7.2);
  assert.equal(b.rows.find(x => x.recordDate === '2025-12-31').amount, 1361, 'the later load of the same dividend');
  assert.ok(b.rows.every(x => x.kind === '보통주'));
  assert.ok(b.rows.every((x, i) => !i || x.recordDate < b.rows[i - 1].recordDate));
  const p = await get(env, '/api/stock/005935/dividend');
  assert.equal(calls().length, 1); assert.ok(p.body.rows.length && p.body.rows.every(x => x.kind === '우선주'));
  assert.equal((await get(env, '/api/stock/069500/dividend')).status, 404);
});

await R.test('dividend: more rows than one page → the last page too (either sort order); a refresh that fails keeps the copy (stale)', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const pad = [];
  for (let i = 0; i < 1100; i++) pad.push({ ...DIVI[0], basDt: '20190101', stckGenrDvdnAmt: '1' });   // old reloads first, the real ones after
  const ROWS0 = ROWS.getDiviInfo_V2;
  ROWS.getDiviInfo_V2 = p => [...pad, ...ROWS0(p)];
  try {
    const r = await get(env, '/api/stock/005930/dividend');
    assert.deepEqual(calls().map(c => c.params.pageNo), ['1', '2']);
    assert.equal(r.body.rows[0].recordDate, '2026-09-30');
  } finally { ROWS.getDiviInfo_V2 = ROWS0; }
  at('2026-11-17T14:00:00');
  fail.getDiviInfo_V2 = () => ({ body: { response: { header: { resultCode: '99', resultMsg: 'UNKNOWN_ERROR' } } } });
  await get(env, '/api/stock/005930/dividend');
  const s = await get(env, '/api/stock/005930/dividend');
  assert.equal(s.body.stale, true); assert.equal(s.body.rows[0].recordDate, '2026-09-30');
});

/* ── caps · status · the rest ── */
await R.test('caps: lend 200 · corp 600 (divi 1000 shared with the calendar); /api/datago/status lists lend · corp · divi + the lend table, no secrets', async () => {
  assert.equal(DG_APIS.lend.cap, 200); assert.equal(DG_APIS.corp.cap, 600); assert.equal(DG_APIS.divi.cap, 1000);
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  await get(env, '/api/stock/005930/lending'); await get(env, '/api/stock/005930/corp');
  const s = await get(env, '/api/datago/status');
  assert.equal(s.status, 200);
  assert.equal(s.body.apis.lend.calls, 3); assert.equal(s.body.apis.lend.cap, 200);
  assert.equal(s.body.apis.corp.calls, 4); assert.equal(s.body.apis.corp.cap, 600); assert.equal(s.body.apis.divi.cap, 1000);
  assert.deepEqual({ ...s.body.snapshots.lend, at: null }, { basDt: '2026-11-13', at: null, days: 3, empty: 0, rows: 5 });
  scanKV(kv); scanLogs();
});

await R.test('route shape: unknown sub-route stays with the old router (404), lowercase code → 400, JSON content type, CORS on errors', async () => {
  reset();
  const kv = makeKV(), env = env0(kv); seedCrno(kv);
  const bad = await get(env, '/api/stock/00593a/corp');
  assert.equal(bad.status, 400); assert.equal(bad.cors, 'https://panse.pages.dev');
  const res = await W.fetch(new Request('https://panse.pages.dev/api/stock/005930/dividend'), env, { waitUntil() {} });
  assert.match(res.headers.get('content-type'), /application\/json/);
});

R.done();
