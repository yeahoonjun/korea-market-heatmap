// 증시 캘린더 Worker 점검 — node qa/worker/test_calendar.mjs
// Fake fetch · KV · clock; no network, no real keys. Fixtures: qa/calendar/fixtures (trimmed real pages, 2026-11-15).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  calendarRoute, parseBok, parseKostat, etToKst, expiryEvents, datesIn, dartEvents, periodOf, groupCorp, fmtVal,
  fscDivEvents, starKr, BOK_MEETINGS,
} from '../../worker/src/calendar.js';
import { dgResetMemory } from '../../worker/src/datago.js';

const FIX = new URL('../calendar/fixtures/', import.meta.url);
const BOK_HTML = readFileSync(new URL('bok_2026.html', FIX), 'utf8');
const KOSTAT = { 11: readFileSync(new URL('kostat_11.html', FIX), 'utf8'), 12: readFileSync(new URL('kostat_12.html', FIX), 'utf8') };
const SECRETS = { FRED_KEY: 'FREDSECRETkey0123456789abcdef0', DART_KEY: 'DARTSECRET4567890123456789012345678901234', ECOS_KEY: 'ECOSSECRET789XYZ', DATA_GO_KR_KEY: 'DATAGOSECRET%2B000' };
let pass = 0, fail = 0;
async function t(name, fn) {
  try { await fn(); pass++; console.log('PASS', name); }
  catch (e) { fail++; console.log('FAIL', name, '\n   ', e && e.stack ? e.stack.split('\n').slice(0, 3).join('\n    ') : e); }
}
const KST = iso => Date.parse(iso);

// ── fakes
class FakeKV {
  constructor() { this.m = new Map(); this.puts = 0; }
  async get(k, type) { const v = this.m.get(k); if (v == null) return null; return type === 'json' ? JSON.parse(v) : v; }
  async put(k, v) { this.puts++; this.m.set(k, String(v)); }
  dump() { return [...this.m].map(([k, v]) => k + '=' + v).join('\n'); }
}
const CALLS = [];
// 공공데이터포털 (금융위): UP.dg = 'empty' (resultCode 03 for every day) | 'data' (rows on basDt 20261113, the code table) ;
// UP.dgDeny = Set of service names answering the new gateway's 403 (a key not approved for that API)
const DG = {
  getDiviInfo_V2: [{ basDt: '20261113', isinCd: 'KR7900002003', crno: '1101110000002', stckIssuCmpyNm: '가나전자', dvdnBasDt: '20261130', cashDvdnPayDt: '20261218', stckGenrDvdnAmt: '361', scrsItmsKcdNm: '보통주' }],
  getLockUpRetuInfo_V3: [{ basDt: '20261113', isinCd: 'KR7900007009', crno: '1101110000007', stckIssuCmpyNm: '자차바이오', rsrnDt: '20261130', rsrnStckCnt: '21500000', scrsItmsKcdNm: '보통주', stckLblHoldRcdNm: '최대주주', lkupRegDt: '20251130' }],
  getStocIssuStat_V3: [{ basDt: '20261113', crno: '1101110000007', isinCd: 'KR7900007009', onskTisuCnt: '116847826', pfstTisuCnt: '0' }],
  getRighExerReasSche_V2: [
    { basDt: '20261113', crno: '1101110000002', stckIssuCmpyNm: '가나전자', stckIssuRcdNm: '현금배당', rgtExertRcd: '01', rgtExertRcdNm: '기준일', rgtExertSttgDt: '20261130', nmlsLckSttgDt: '20261201', nmlsLckEdDt: '20261205' },
    { basDt: '20261113', crno: '1101110000009', stckIssuCmpyNm: '마바증권', stckIssuRcdNm: '유상증자', rgtExertRcd: '01', rgtExertRcdNm: '기준일', rgtExertSttgDt: '20261127', nmlsLckSttgDt: '20261128', nmlsLckEdDt: '' },
    { basDt: '20261113', crno: '', scrsIssuMnbdCd: '90001', stckIssuCmpyNm: '사아', stckIssuRcdNm: '임시총회', rgtExertRcd: '01', rgtExertRcdNm: '기준일', rgtExertSttgDt: '20261204', nmlsLckSttgDt: '' },
    { basDt: '20261113', crno: '1101119999999', stckIssuCmpyNm: '비상장회사', stckIssuRcdNm: '정기총회', rgtExertRcdNm: '기준일', rgtExertSttgDt: '20261204' }],
  getItemInfo_V2: [['900002', '1101110000002'], ['900007', '1101110000007'], ['900009', '1101110000009'], ['900010', '1101110000010'], ['900015', '1101110000010']]
    .map(([c, crno]) => ({ basDt: '20261113', srtnCd: 'A' + c, isinCd: 'KR7' + c + '003', crno, itmsNm: 'x' + c, corpNm: 'x' + c, mrktCtg: 'KOSDAQ' })),
};
function dataGoKr(u) {
  const op = u.pathname.split('/').pop(), svc = u.pathname.split('/').slice(-2)[0];
  if ((UP.dgDeny || new Set()).has(svc)) return Promise.resolve(new Response('Forbidden', { status: 403, headers: { 'content-type': 'text/plain' } }));
  const day = u.searchParams.get('basDt');
  let rows = UP.dg === 'data' && (op === 'getItemInfo_V2' || day === '20261113') ? (DG[op] || []) : [];
  if (op === 'getStocIssuStat_V3') rows = rows.filter(r => r.crno === u.searchParams.get('crno'));
  const body = rows.length ? { response: { header: { resultCode: '00', resultMsg: 'NORMAL SERVICE.' }, body: { numOfRows: +u.searchParams.get('numOfRows'), pageNo: 1, totalCount: rows.length, items: { item: rows } } } }
    : { response: { header: { resultCode: '03', resultMsg: 'NODATA_ERROR' }, body: { numOfRows: 10, pageNo: 1, totalCount: 0, items: '' } } };
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } }));
}
const UP = { fail: new Set(), dartStatus: '000', cpi: ['2026-10-01', '3.0'], dg: 'empty' };
function fakeFetch(url) {
  const u = new URL(String(url));
  CALLS.push(u);
  const ok = (body, ctype = 'application/json') => Promise.resolve(new Response(typeof body === 'string' ? body : JSON.stringify(body), { status: 200, headers: { 'content-type': ctype } }));
  const host = u.hostname;
  if (UP.fail.has(host)) return Promise.reject(new TypeError('connect failed to ' + u.href));   // the message carries the URL (and key): must not leak
  if (host === 'www.bok.or.kr') return ok(u.searchParams.get('date').startsWith('2027') ? BOK_HTML : BOK_HTML, 'text/html');
  if (host === 'mods.go.kr') return ok(KOSTAT[+u.searchParams.get('oa_mm')] || '<h3>2026년 1월 보도계획</h3>', 'text/html');
  if (host === 'api.stlouisfed.org' && u.pathname.endsWith('/release/dates')) {
    const id = +u.searchParams.get('release_id');
    if (UP.fredBad === id) return Promise.resolve(new Response('bad', { status: 500 }));
    const map = { 10: ['2026-11-10', '2026-12-10'], 50: ['2026-11-06', '2026-12-04'], 53: ['2026-11-25'], 9: ['2026-11-17'], 13: ['2026-11-17'] };
    return ok({ release_dates: (map[id] || []).map(date => ({ release_id: id, date })) });
  }
  if (host === 'api.stlouisfed.org' && u.pathname.endsWith('/series/observations')) {
    const s = u.searchParams.get('series_id');
    const v = { CPIAUCSL: UP.cpi, PAYEMS: ['2026-11-01', '119'], UNRATE: ['2026-11-01', '4.4'], DFEDTARL: ['2026-12-10', '3.50'], DFEDTARU: ['2026-12-10', '3.75'] }[s] || ['2026-10-01', '1.0'];
    return ok({ observations: [{ date: v[0], value: v[1] }] });
  }
  if (host === 'ecos.bok.or.kr') return ok({ KeyStatisticList: { row: [
    { CLASS_NAME: '심리지표', KEYSTAT_NAME: '소비자심리지수', DATA_VALUE: '105.4', CYCLE: '202611', UNIT_NAME: null },
    { CLASS_NAME: '시장금리', KEYSTAT_NAME: '한국은행 기준금리', DATA_VALUE: '2.75', CYCLE: '20261126', UNIT_NAME: '%' },
    { CLASS_NAME: '물가', KEYSTAT_NAME: '소비자물가지수', DATA_VALUE: '120.73', CYCLE: '202610', UNIT_NAME: '2020=100' },
  ] } });
  if (host === 'opendart.fss.or.kr') {
    if (UP.dartStatus !== '000') return ok({ status: UP.dartStatus, message: 'x' });
    const p = u.pathname.split('/').pop();
    if (p === 'list.json') {
      const ty = u.searchParams.get('pblntf_detail_ty'), cls = u.searchParams.get('corp_cls'), d = u.searchParams.get('bgn_de');
      if (ty === 'B001' && cls === 'K' && d === '20261113') return ok({ status: '000', total_page: 1, list: [
        { rcept_no: '20261113000111', corp_code: '00999001', corp_name: '테스트바이오', stock_code: '900001', report_nm: '주요사항보고서(무상증자결정)', rcept_dt: '20261113' },
        { rcept_no: '20261113000112', corp_code: '00999002', corp_name: '비상장', stock_code: '', report_nm: '주요사항보고서(무상증자결정)', rcept_dt: '20261113' },
        { rcept_no: '20261113000113', corp_code: '00999003', corp_name: '다른공시', stock_code: '900003', report_nm: '주요사항보고서(자기주식취득결정)', rcept_dt: '20261113' }] });
      if (ty === 'C001' && cls === 'Y' && d === '20261112') return ok({ status: '000', total_page: 1, list: [
        { rcept_no: '20261112000222', corp_code: '00999004', corp_name: '테스트증권', stock_code: '900004', report_nm: '[발행조건확정]증권신고서(지분증권)', rcept_dt: '20261112' }] });
      return ok({ status: '013', message: '조회된 데이타가 없습니다.' });
    }
    if (p === 'fricDecsn.json') return ok({ status: '000', list: [{ rcept_no: '20261113000111', nstk_asstd: '2026년 12월 01일', nstk_lstprd: '2026년 12월 22일', nstk_ascnt_ps_ostk: '1' }] });
    if (p === 'estkRs.json') return ok({ status: '000', group: [{ title: '일반사항', list: [{ rcept_no: '20261112000222', sbd: '2026년 11월 26일 ~ 2026년 11월 27일', pymd: '2026년 12월 03일', asstd: '2026년 11월 10일' }] }] });
    return ok({ status: '013' });
  }
  if (host === 'apis.data.go.kr') return dataGoKr(u);
  return Promise.resolve(new Response('not mocked', { status: 404 }));
}
globalThis.fetch = fakeFetch;
const logs = [];
const origLog = console.log;
console.log = (...a) => { const s = a.join(' '); if (/^(PASS|FAIL|\s)/.test(s)) origLog(...a); else logs.push(s); };
console.error = (...a) => logs.push(a.join(' '));

const env0 = () => Object.assign({ REPLAY: new FakeKV() }, SECRETS);
const ctx0 = () => { const ps = []; return { ps, waitUntil(p) { ps.push(p); }, async drain() { while (ps.length) await ps.shift(); } }; };
// the shared data.go.kr helper reads Date.now(): follow the test's clock; a new env = a new isolate for the helper's memory
let FAKE_NOW = null, LAST_ENV = null;
const realNow = Date.now;
Date.now = () => (FAKE_NOW == null ? realNow() : FAKE_NOW);
async function call(env, ctx, qs, nowIso) {
  FAKE_NOW = KST(nowIso);
  if (env !== LAST_ENV) { dgResetMemory(); LAST_ENV = env; }
  const url = new URL('https://x/api/calendar' + qs);
  const res = await calendarRoute(new Request(url), env, ctx, url, KST(nowIso));
  const text = await res.text();
  return { res, text, body: (() => { try { return JSON.parse(text); } catch (e) { return null; } })() };
}
const noSecret = s => Object.values(SECRETS).every(k => !String(s).includes(k) && !String(s).includes(encodeURIComponent(k)));

// ── pure parts
await t('parseBok: 2026 rows from the trimmed page', () => {
  const r = parseBok(BOK_HTML, 2026);
  assert.ok(r.length >= 120, 'rows ' + r.length);
  assert.deepEqual(r.find(x => x.d === '2026-11-18'), { d: '2026-11-18', t: '12:00', title: '3/4분기 가계신용(잠정)', note: '' });
  assert.ok(r.find(x => x.d === '2026-11-20' && x.t === '06:00' && x.title === '10월 생산자물가지수(잠정)'));
  assert.ok(r.some(x => /변경일시/.test(x.note)), 'a 변경일시 note survives');
  assert.ok(r.find(x => x.title === '2024년 상세자금순환표'), 'a yearly title keeps its year');
  assert.equal(parseBok(BOK_HTML, 2027).length, 0, 'a year the page has not got → nothing');
});
await t('parseKostat: only 소비자물가 · 고용 · 산업활동', () => {
  const p = parseKostat(KOSTAT[12]);
  assert.equal(p.y, 2026); assert.equal(p.mo, 12);
  assert.deepEqual(p.rows.map(r => r.d + ' ' + r.t + ' ' + r.title), ['2026-12-02 08:00 11월 소비자물가동향', '2026-12-16 08:00 11월 고용동향', '2026-12-30 08:00 11월 산업활동동향', '2026-12-31 08:00 12월 및 연간 소비자물가동향']);
  assert.equal(parseKostat('<p>nothing</p>'), null);
});
await t('etToKst: DST from Intl', () => {
  assert.deepEqual([etToKst('2026-12-09', '14:00').d, etToKst('2026-12-09', '14:00').t], ['2026-12-10', '04:00']);
  assert.deepEqual([etToKst('2026-10-28', '14:00').d, etToKst('2026-10-28', '14:00').t], ['2026-10-29', '03:00']);
  assert.deepEqual([etToKst('2027-03-17', '14:00').d, etToKst('2027-03-17', '14:00').t], ['2027-03-18', '03:00']);
  assert.deepEqual([etToKst('2026-12-10', '08:30').d, etToKst('2026-12-10', '08:30').t], ['2026-12-10', '22:30']);
  assert.deepEqual([etToKst('2026-07-02', '08:30').d, etToKst('2026-07-02', '08:30').t], ['2026-07-02', '21:30']);
});
await t('expiries: 2nd Thursday, quarterly star 3, weekly flagged, holidays shift', () => {
  const e = expiryEvents('2026-12-01', '2026-12-31');
  const q = e.find(x => x.d === '2026-12-10' && !x.weekly);
  assert.ok(q && q.star === 3 && q.title === '선물 · 옵션 동시만기' && q.t === '15:20');
  assert.ok(!e.some(x => x.weekly && x.d === '2026-12-10'), 'no weekly on the monthly expiry');
  assert.ok(e.find(x => x.weekly && x.d === '2026-12-30' && /목/.test(x.title)), 'Thursday 12-31 (closed) → 12-30');
  assert.ok(e.find(x => x.weekly && x.d === '2026-12-28' && /월/.test(x.title)));
  assert.ok(e.every(x => x.weekly ? x.star === 1 : true));
  const nov = expiryEvents('2026-11-01', '2026-11-30').find(x => !x.weekly);
  assert.equal(nov.d, '2026-11-12'); assert.equal(nov.star, 2); assert.match(nov.title, /11월물/);
  const may = expiryEvents('2026-05-01', '2026-05-31').filter(x => x.weekly && /월/.test(x.title)).map(x => x.d);
  assert.ok(!may.includes('2026-05-01'));
});
await t('datesIn · periodOf · fmtVal · starKr', () => {
  assert.deepEqual(datesIn('2026년 11월 26일 ~ 2026년 11월 27일'), ['2026-11-26', '2026-11-27']);
  assert.deepEqual(datesIn('2026.12.3 / 20261205 / 2026-02-30'), ['2026-12-03', '2026-12-05']);
  assert.equal(periodOf('3/4분기 가계신용(잠정)', '2026-11-18'), '2026Q3');
  assert.equal(periodOf('4/4분기 및 연간 실질 국내총생산(속보)', '2027-01-22'), '2026Q4');
  assert.equal(periodOf('12월 소비자동향조사 결과', '2026-12-24'), '202612');
  assert.equal(periodOf('12월 및 연간 소비자물가동향', '2027-01-03'), '202612');
  assert.equal(periodOf('상세자금순환표', '2026-01-08'), null);
  assert.equal(fmtVal({ f: 'pct', l: '전년 대비' }, '2.94'), '전년 대비 +2.9%');
  assert.equal(fmtVal({ f: 'man', m: 1000, sign: 1, l: '비농업 고용', unit: '명' }, '119'), '비농업 고용 +11.9만 명');
  assert.equal(fmtVal({ f: 'man', m: 1, l: '청구', unit: '건' }, '228000'), '청구 22.8만 건');
  assert.equal(fmtVal({ f: 'rate', l: '실업률' }, '.'), null);
  assert.equal(starKr('4/4분기 및 연간 실질 국내총생산(속보)'), 3);
  assert.equal(starKr('11월 고용동향'), 2);
  assert.equal(starKr('9월 통화 및 유동성'), 1);
});
await t('dartEvents: 무상 (incl. 유무상 prefix) and 유상 (estkRs)', () => {
  const f = { c: '900001', n: 'A', kind: 'fric' };
  const e = dartEvents(f, 'R1', { list: [{ rcept_no: 'R1', nstk_asstd: '2026.12.01', nstk_lstprd: '2026년 12월 22일', nstk_ascnt_ps_ostk: '0.5' }] });
  assert.deepEqual(e.map(x => [x.d, x.title, x.star]), [['2026-12-01', '무상증자 신주배정기준일', 2], ['2026-12-22', '무상증자 신주 상장', 1]]);
  assert.equal(e[0].sub, '1주당 0.5주');
  const p = dartEvents({ c: '900002', n: 'B', kind: 'pifric' }, 'R2', { list: [{ rcept_no: 'R2', fric_nstk_asstd: '2026-12-05' }] });
  assert.equal(p[0].d, '2026-12-05');
  const s = dartEvents({ c: '900004', n: 'C', kind: 'estk' }, 'R3', { group: [{ title: '일반사항', list: [{ rcept_no: 'R3', sbd: '2026년 11월 26일 ~ 2026년 11월 27일', pymd: '2026년 12월 03일', asstd: '2026년 11월 10일' }] }] });
  assert.deepEqual(s.map(x => x.title), ['유상증자 청약', '유상증자 배정기준일']);
  assert.equal(s[0].sub, '청약 ~11/27 · 납입 12/3');
  assert.deepEqual(dartEvents(f, 'R9', { list: [] }), []);
});
await t('groupCorp: >12 same-day dividends → one row', () => {
  const evs = Array.from({ length: 15 }, (_, i) => ({ id: 'x' + i, d: '2026-12-31', k: 'corp', grp: 'div-rec', c: String(900100 + i), title: '배당 기준일', src: 'fsc', star: 1 }));
  const g = groupCorp(evs.concat([{ id: 'y', d: '2026-12-30', k: 'corp', grp: 'div-rec', c: '900999', title: '배당 기준일', star: 1 }]));
  assert.equal(g.length, 2); assert.equal(g[0].n, 15); assert.equal(g[0].sub, '15개 종목'); assert.equal(g[0].codes.length, 15);
});
await t('2027 금통위 are tentative (press-based)', () => {
  assert.ok(BOK_MEETINGS.filter(m => m.d >= '2027').every(m => m.tentative));
  assert.ok(BOK_MEETINGS.filter(m => m.d < '2027').every(m => !m.tentative));
});

// ── route
await t('route: validation', async () => {
  const env = env0(), ctx = ctx0();
  for (const [qs, re] of [['?from=2026-13-01', /형식/], ['?from=2026-11-01&to=2026-12-31', /42일/], ['?from=2026-11-20&to=2026-11-19', /빠를/], ['?kinds=kr,xx', /kinds/], ['?from=2030-01-01&to=2030-01-02', /400일/]]) {
    const r = await call(env, ctx, qs, '2026-11-16T09:12:00+09:00');
    assert.equal(r.res.status, 400, qs); assert.match(r.body.error, re);
  }
});
let ENV, CTX;
await t('route: first answer builds every source (awaited) — kr · us · cb · mkt · corp', async () => {
  ENV = env0(); CTX = ctx0(); CALLS.length = 0;
  const r = await call(ENV, CTX, '?from=2026-11-09&to=2026-12-20', '2026-11-16T09:12:00+09:00');
  await CTX.drain();
  assert.equal(r.res.status, 200);
  const b = r.body, ev = id => b.events.find(e => e.id === id);
  assert.match(r.res.headers.get('cache-control'), /s-maxage=300/);
  assert.ok(ev('bok:2026-11-18:3/4분기 가계신용(잠정)'), 'BOK row');
  assert.equal(ev('kostat:2026-12-02:11월 소비자물가동향').t, '08:00');
  const cpi = ev('fred:10:2026-12-10');
  assert.deepEqual([cpi.d, cpi.t, cpi.star, cpi.orig.t], ['2026-12-10', '22:30', 3, '08:30']);
  const ip = ev('fred:13:2026-11-17'); assert.equal(ip.t, null, 'unconfirmed time → date only');
  const fomc = ev('cb:fomc:2026-12-09'); assert.deepEqual([fomc.d, fomc.t, fomc.sub], ['2026-12-10', '04:00', '경제전망(SEP) 함께']);
  assert.ok(ev('cb:bok:2026-11-26') && ev('cb:bokmin:2026-12-15') && ev('cb:fomcmin:2026-11-18'));
  assert.ok(ev('rule:exp:2026-12-10') && ev('rule:exp:2026-11-12'));
  assert.ok(b.events.some(e => e.weekly), 'weekly expiries are in the answer, flagged');
  const fr = b.events.filter(e => e.src === 'dart');
  assert.deepEqual(fr.map(e => e.d + ' ' + e.title).sort(), ['2026-11-10 유상증자 배정기준일', '2026-11-26 유상증자 청약', '2026-12-01 무상증자 신주배정기준일'].sort());
  assert.equal(b.days['2026-11-19'].kind, 'special');
  assert.deepEqual(b.sources.fsc.parts, { divi: 'ok', lock: 'ok', rights: 'ok' }, 'FSC through the shared helper (no rows that day)');
  const dg = CALLS.filter(u => u.hostname === 'apis.data.go.kr');
  for (const op of ['getDiviInfo_V2', 'getLockUpRetuInfo_V3', 'getRighExerReasSche_V2']) {
    const n = dg.filter(u => u.pathname.endsWith(op)).length;
    assert.ok(n >= 1 && n <= 10, op + ' ' + n + ' calls (≤ 10 business days back, one page each)');
  }
  assert.ok(b.events.every((e, i, a) => i === 0 || a[i - 1].d <= e.d), 'sorted by day');
  assert.ok(b.sources.bok.ok && b.sources.kostat.ok && b.sources.fred.ok && b.sources.dart.ok);
});
await t('route: OpenDART budget — 4 list calls a day + details, backfill ≤ 6 weekdays a run', async () => {
  const dart = CALLS.filter(u => u.hostname === 'opendart.fss.or.kr');
  const lists = dart.filter(u => u.pathname.endsWith('list.json'));
  assert.equal(lists.length, 4 * 7, 'today + 6 backfill days × B001/C001 × Y/K');
  assert.equal(dart.length - lists.length, 2, 'two detail calls');
  const calls = JSON.parse(ENV.REPLAY.m.get('cal:dart:calls:20261116')).n;
  assert.equal(calls, dart.length);
});
await t('route: a second request inside the intervals calls no upstream', async () => {
  CALLS.length = 0;
  const r = await call(ENV, CTX, '?from=2026-11-16&to=2026-11-29', '2026-11-16T09:20:00+09:00');
  await CTX.drain();
  assert.equal(r.res.status, 200);
  assert.equal(CALLS.length, 0, CALLS.map(u => u.hostname).join(','));
});
await t('route: values after the release (ECOS · FRED), text only', async () => {
  CALLS.length = 0; UP.cpi = ['2026-11-01', '2.9'];         // FRED has the November CPI after the 12-10 release
  const now = '2026-12-11T10:00:00+09:00';
  // the sources are due again (20 h) — the stale copies are served and refreshed after; values come once wanted
  let r = await call(ENV, CTX, '?from=2026-11-23&to=2026-12-13', now); await CTX.drain();
  r = await call(ENV, CTX, '?from=2026-11-23&to=2026-12-13', '2026-12-11T10:01:00+09:00'); await CTX.drain();
  const ev = id => r.body.events.find(e => e.id === id);
  assert.deepEqual(ev('cb:bok:2026-11-26').value, { text: '한국은행 기준금리 2.75%', src: 'ecos', p: '20261126' });
  assert.equal(ev('fred:10:2026-12-10').value.text, '전년 대비 +2.9%');
  assert.equal(ev('cb:fomc:2026-12-09').value.text, '목표 범위 3.50~3.75%');
  assert.ok(!ev('bok:2026-11-24:11월 소비자동향조사 결과') || ev('bok:2026-11-24:11월 소비자동향조사 결과').value.text === '소비자심리지수 105.4');
  assert.ok(r.body.events.every(e => !e.value || typeof e.value.text === 'string'));
});
await t('values: FRED only within 7 days of a release (and from 60 min after)', async () => {
  const env = env0(), ctx = ctx0();
  CALLS.length = 0;
  await call(env, ctx, '?from=2026-12-14&to=2026-12-27', '2026-12-21T10:00:00+09:00'); await ctx.drain();
  const obs = CALLS.filter(u => u.pathname.endsWith('/series/observations')).map(u => u.searchParams.get('series_id'));
  assert.ok(!obs.includes('CPIAUCSL'), 'CPI of 12-10 is 11 days old');
  CALLS.length = 0;
  const env2 = env0(), ctx2 = ctx0();
  await call(env2, ctx2, '?from=2026-12-07&to=2026-12-20', '2026-12-10T23:00:00+09:00'); await ctx2.drain();   // CPI 22:30 KST, 30 min ago
  const obs2 = CALLS.filter(u => u.pathname.endsWith('/series/observations')).map(u => u.searchParams.get('series_id'));
  assert.ok(!obs2.includes('CPIAUCSL'), 'not before FRED had time to post');
});
await t('secrets: never in answers, KV or logs (also when fetch errors carry the URL)', async () => {
  UP.fail.add('api.stlouisfed.org'); UP.fail.add('ecos.bok.or.kr'); UP.fredBad = 10;
  const env = env0(), ctx = ctx0();
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-16T09:12:00+09:00'); await ctx.drain();
  UP.fail.clear(); UP.fredBad = null;
  assert.ok(noSecret(r.text), 'answer');
  assert.ok(noSecret(env.REPLAY.dump()), 'KV');
  assert.ok(noSecret(logs.join('\n')), 'logs');
  assert.ok(noSecret(ENV.REPLAY.dump()), 'KV of the earlier run');
  assert.equal(r.body.sources.fred.ok, false); assert.equal(r.body.sources.fred.err, 'network');
});
await t('failure keeps the last good copy (stale)', async () => {
  const env = env0(), ctx = ctx0();
  await call(env, ctx, '?from=2026-11-16&to=2026-11-29', '2026-11-16T09:12:00+09:00'); await ctx.drain();
  UP.fail.add('www.bok.or.kr');
  const r1 = await call(env, ctx, '?from=2026-11-16&to=2026-11-30', '2026-11-17T09:12:00+09:00'); await ctx.drain();
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-11-28', '2026-11-17T09:13:00+09:00'); await ctx.drain();
  UP.fail.clear();
  assert.ok(r1.body.events.some(e => e.src === 'bok'));
  assert.equal(r.body.sources.bok.ok, false); assert.equal(r.body.stale, true);
  assert.ok(r.body.events.some(e => e.src === 'bok'), 'rows still there');
});
await t('OpenDART: cool-down (§3-29) and the daily cap stop the calls', async () => {
  const env = env0(), ctx = ctx0();
  await env.REPLAY.put('dart:cool', JSON.stringify({ until: KST('2026-11-16T10:00:00+09:00') }));
  CALLS.length = 0;
  let r = await call(env, ctx, '?from=2026-11-16&to=2026-11-29', '2026-11-16T09:12:00+09:00'); await ctx.drain();
  assert.ok(!CALLS.some(u => u.hostname === 'opendart.fss.or.kr'));
  assert.equal(r.body.sources.dart.err, 'cool');
  const env2 = env0(), ctx2 = ctx0();
  await env2.REPLAY.put('cal:dart:calls:20261116', JSON.stringify({ n: 400 }));
  CALLS.length = 0;
  r = await call(env2, ctx2, '?from=2026-11-16&to=2026-11-29', '2026-11-16T09:12:00+09:00'); await ctx2.drain();
  assert.ok(!CALLS.some(u => u.hostname === 'opendart.fss.or.kr'));
  assert.equal(r.body.sources.dart.err, 'cap');
});
await t('kinds filter', async () => {
  const r = await call(ENV, CTX, '?from=2026-11-16&to=2026-11-29&kinds=us,cb', '2026-11-16T09:30:00+09:00');
  assert.ok(r.body.events.length && r.body.events.every(e => e.k === 'us' || e.k === 'cb'));
});
await t('no keys: 공개 원천만, sources off', async () => {
  const env = { REPLAY: new FakeKV() }, ctx = ctx0();
  CALLS.length = 0;
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-11-29', '2026-11-16T09:12:00+09:00'); await ctx.drain();
  assert.equal(r.res.status, 200);
  assert.ok(r.body.sources.fred.off && r.body.sources.dart.off && r.body.sources.fsc.off);
  assert.ok(!CALLS.some(u => u.hostname === 'api.stlouisfed.org' || u.hostname === 'opendart.fss.or.kr' || u.hostname === 'apis.data.go.kr'));
  assert.ok(r.body.events.some(e => e.src === 'bok') && r.body.events.some(e => e.k === 'cb'));
});
await t('FSC through the shared helper: 배당 · 보호예수 % · 권리일정 (crno → code, dedupe), once a day', async () => {
  UP.dg = 'data';
  const env = env0(), ctx = ctx0();
  CALLS.length = 0;
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-16T14:00:00+09:00'); await ctx.drain();
  const fsc = r.body.events.filter(e => e.src === 'fsc');
  assert.ok(fsc.find(e => e.title === '배당 기준일' && e.d === '2026-11-30' && e.sub === '1주당 361원'));
  assert.ok(fsc.find(e => e.title === '배당금 지급' && e.d === '2026-12-18'));
  const lock = fsc.find(e => /보호예수/.test(e.title));
  assert.deepEqual([lock.d, lock.c, lock.pct, lock.star, lock.title], ['2026-11-30', '900007', 18.4, 3, '보호예수 해제 2,150만 주']);
  assert.ok(!fsc.some(e => e.c === '900002' && e.api === 'getRighExerReasSche_V2'), 'the 현금배당 기준일 row is the dividend already shown');
  const ri = fsc.find(e => e.c === '900009');
  assert.deepEqual([ri.d, ri.title, ri.sub], ['2026-11-27', '유상증자 기준일', '명부폐쇄 11/28']);
  assert.ok(fsc.find(e => e.c === '900010' && e.title === '임시총회 기준일' && e.d === '2026-12-04'), 'no crno: issuer code + 0 when that code is listed');
  assert.ok(!fsc.some(e => /비상장/.test(e.n || '')), 'a crno without a listed code is dropped');
  assert.equal(r.body.sources.fsc.ok, true);
  assert.deepEqual(r.body.sources.fsc.parts, { divi: 'ok', lock: 'ok', rights: 'ok' });
  const dg = CALLS.filter(u => u.hostname === 'apis.data.go.kr');
  assert.ok(dg.every(u => u.searchParams.get('resultType') === 'json'));
  assert.equal(dg.filter(u => u.pathname.endsWith('getStocIssuStat_V3')).length, 1, 'one 발행현황 call for the one lock-up');
  assert.ok(+(await env.REPLAY.get('datago:calls:rights:20261116')) >= 1, 'counted against the rights API cap');
  // a second request the same afternoon: nothing is due
  CALLS.length = 0;
  await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-16T16:00:00+09:00'); await ctx.drain();
  assert.ok(!CALLS.some(u => u.hostname === 'apis.data.go.kr'), CALLS.map(u => u.pathname).join(','));
  // the next business day after 13:00: one new basDt per API, the earlier rows stay
  const r2 = await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-17T13:30:00+09:00'); await ctx.drain();
  const r3 = await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-17T13:31:00+09:00');
  const asked = CALLS.filter(u => u.hostname === 'apis.data.go.kr' && !u.pathname.endsWith('getItemInfo_V2')).map(u => u.searchParams.get('basDt'));
  assert.deepEqual([...new Set(asked)], ['20261116'], asked.join(','));
  assert.ok(r3.body.events.some(e => e.c === '900007' && /보호예수/.test(e.title)));
  assert.ok(noSecret(r.text) && noSecret(r3.text) && noSecret(env.REPLAY.dump()) && noSecret(logs.join('\n')));
  UP.dg = 'empty';
});
await t('FSC: a key not approved for 주식권리일정 (403) stops that part only — no stale, no secret', async () => {
  UP.dg = 'data'; UP.dgDeny = new Set(['GetStocRighScheService_V2']);
  const env = env0(), ctx = ctx0();
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-12-20', '2026-11-16T14:00:00+09:00'); await ctx.drain();
  UP.dg = 'empty'; UP.dgDeny = null;
  assert.equal(r.body.sources.fsc.parts.rights, 'forbidden');
  assert.equal(r.body.sources.fsc.ok, true);
  assert.equal(r.body.stale, undefined);
  assert.ok(r.body.events.some(e => e.src === 'fsc' && /보호예수/.test(e.title)) && !r.body.events.some(e => e.api === 'getRighExerReasSche_V2'));
  const cool = JSON.parse(await env.REPLAY.get('datago:cool:rights'));
  assert.equal(cool.code, 'forbidden');
  assert.ok(noSecret(env.REPLAY.dump()) && noSecret(r.text));
});
await t('FSC: CAL_FSC=off switches the three parts off', async () => {
  const env = Object.assign(env0(), { CAL_FSC: 'off' }), ctx = ctx0();
  CALLS.length = 0;
  const r = await call(env, ctx, '?from=2026-11-16&to=2026-11-29', '2026-11-16T14:00:00+09:00'); await ctx.drain();
  assert.equal(r.body.sources.fsc.off, true);
  assert.ok(!CALLS.some(u => u.hostname === 'apis.data.go.kr'));
});
await t('fscDivEvents: 우선주 · isin → code', () => {
  const e = fscDivEvents({ isinCd: 'KR7005935002', stckIssuCmpyNm: '삼성전자', dvdnBasDt: '20261231', stckGenrDvdnAmt: '1,445', scrsItmsKcdNm: '우선주' });
  assert.deepEqual([e[0].c, e[0].sub], ['005935', '1주당 1,445원 (우선주)']);
  assert.deepEqual(fscDivEvents({ isinCd: 'US0000000000' }), []);
});

console.log = origLog;
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
