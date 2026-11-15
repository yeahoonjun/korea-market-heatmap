// QA: worker/src/datago_crno.js — 종목코드 ↔ 법인등록번호 from 금융위원회_KRX상장종목정보 getItemInfo_V2 (AGENTS §3-32 ⑥).
// Fake fetch / KV / clock (harness.mjs); no network, no real key.   node qa/datago/test_crno.mjs
import assert from 'node:assert/strict';
import { at, advance, makeKV, net, paged, portalXml, gateway, KEYS, scanKV, scanLogs, runner, ctxOf, assertNoKey } from './harness.mjs';
import { dgResetMemory } from '../../worker/src/datago.js';
import { crnoOf, crnoInfo, crnoTable, crnoDue, CRNO_KEY } from '../../worker/src/datago_crno.js';

const R = runner('crno map');
const env0 = (kv, extra = {}) => ({ REPLAY: kv, DATA_GO_KR_KEY: KEYS.raw, ...extra });
// a listing like the source: 2,900 common shares (no preferred), a few foreign companies without a crno
function listing(basDt, n = 2900) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const code = String(100000 + i * 7).slice(-6);
    out.push({ basDt, srtnCd: 'A' + code, isinCd: 'KR7' + code + '003', mrktCtg: i % 3 ? 'KOSDAQ' : 'KOSPI', itmsNm: '종목' + i, crno: String(1101110000000 + i), corpNm: '회사' + i + '(주)' });
  }
  out.push({ basDt, srtnCd: 'A005930', isinCd: 'KR7005930003', mrktCtg: 'KOSPI', itmsNm: '삼성전자', crno: '1301110006246', corpNm: '삼성전자(주)' });
  out.push({ basDt, srtnCd: 'A000880', isinCd: 'KR7000880005', mrktCtg: 'KOSPI', itmsNm: '한화', crno: '110111-0002959', corpNm: '(주)한화' });
  out.push({ basDt, srtnCd: 'A900140', isinCd: 'HK0000057197', mrktCtg: 'KOSPI', itmsNm: '엘브이엠씨홀딩스', crno: '', corpNm: 'LVMC Holdings' });
  out.push({ basDt, srtnCd: 'XBAD', isinCd: '', mrktCtg: 'KOSPI', itmsNm: '이상한 코드', crno: '', corpNm: '' });
  return out;
}
let days = {};                                   // basDt → listing; missing = no data that day
const handler = (op, params) => {
  assert.equal(op, 'getItemInfo_V2');
  assert.equal(params.resultType, 'json');
  assert.ok(params.basDt && /^\d{8}$/.test(params.basDt), 'one basDt per call');
  return paged(days[params.basDt] || [], params);
};
const reset = () => { dgResetMemory(); net.calls.length = 0; net.handler = handler; days = {}; at('2026-11-16T14:00:00'); };
const pathOk = () => net.calls.every(c => c.path === '/1160100/GetKrxListedInfoService_V2/getItemInfo_V2');

await R.test('first use: latest basDt by the 13:00 rule (Mon 14:00 → Fri 11-13), 2 pages of 2,000, A prefix stripped, KV datago:crno 10 days', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const kv = makeKV(), env = env0(kv);
  assert.equal(await crnoOf(env, '005930'), '1301110006246');
  assert.ok(pathOk());
  assert.deepEqual(net.calls.map(c => [c.params.basDt, c.params.numOfRows, c.params.pageNo]), [['20261113', '2000', '1'], ['20261113', '2000', '2']]);
  const s = kv.json(CRNO_KEY);
  assert.equal(s.basDt, '20261113'); assert.equal(s.n, 2903); assert.equal(s.withCrno, 2902);
  assert.ok(kv.ttl(CRNO_KEY) >= 10 * 86400 - 1);
  const i = await crnoInfo(env, '005930');
  assert.deepEqual(i, { code: '005930', crno: '1301110006246', isin: 'KR7005930003', name: '삼성전자', corp: '삼성전자(주)', market: 'KOSPI', basDt: '2026-11-13' });
  assert.equal(net.calls.length, 2, 'later lookups come from memory / KV');
});
await R.test('crno cleaned to 13 digits; foreign company → crno null; bad source code skipped; unknown / invalid code → null', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const env = env0(makeKV());
  assert.equal(await crnoOf(env, '000880'), '1101110002959');
  const lv = await crnoInfo(env, '900140');
  assert.equal(lv.crno, null); assert.equal(lv.isin, 'HK0000057197');
  assert.equal(await crnoOf(env, '999999'), null);
  assert.equal(await crnoOf(env, 'abc'), null);
  assert.equal(await crnoOf(env, null), null);
});
await R.test('preferred shares (not in the source) fall back to the common share: 005935 → 005930, 00088K → 000880, with `common`', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const env = env0(makeKV());
  const p = await crnoInfo(env, '005935');
  assert.equal(p.crno, '1301110006246'); assert.equal(p.common, '005930'); assert.equal(p.code, '005935');
  assert.equal(await crnoOf(env, '00088K'), '1101110002959');
  assert.equal((await crnoInfo(env, '005930')).common, undefined);
});
await R.test('walk back: Friday empty (holiday) → Thursday; each empty day costs one small call', async () => {
  reset();
  days['20261112'] = listing('20261112');
  const env = env0(makeKV());
  const t = await crnoTable(env);
  assert.equal(t.basDt, '2026-11-12');
  assert.deepEqual(net.calls.map(c => c.params.basDt), ['20261113', '20261112', '20261112']);
});
await R.test('nothing for 7 weekdays → no table (null), empty error recorded, API cools down 15 min', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  assert.equal(await crnoTable(env), null);
  assert.equal(net.calls.length, 7);
  assert.equal(kv.json('datago:err:krx').code, 'empty');
  assert.equal(kv.json('datago:cool:krx').code, 'empty');
  assert.equal(await crnoOf(env, '005930'), null);
  assert.equal(net.calls.length, 7, 'cooling: no more calls');
});
await R.test('once a day: same day, next morning, the weekend → no calls; next weekday after 13:10 → one refresh (background with ctx)', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const kv = makeKV(), env = env0(kv);
  await crnoTable(env);
  assert.equal(net.calls.length, 2);
  for (const t of ['2026-11-16T18:00:00', '2026-11-17T09:00:00', '2026-11-17T13:05:00']) { at(t); dgResetMemory(); await crnoOf(env, '005930'); }
  assert.equal(net.calls.length, 2);
  at('2026-11-17T13:20:00');
  days['20261116'] = listing('20261116', 2950);
  const ctx = ctxOf();
  const t = await crnoTable(env, ctx);
  assert.equal(t.basDt, '2026-11-13', 'the current table is served at once');
  await ctx.flush();
  assert.equal(kv.json(CRNO_KEY).basDt, '20261116');
  assert.equal(net.calls.length, 4);
  dgResetMemory();
  assert.equal((await crnoTable(env)).basDt, '2026-11-16');
  for (const t2 of ['2026-11-21T12:00:00', '2026-11-22T20:00:00']) { at(t2); dgResetMemory(); days['20261120'] = listing('20261120'); await crnoTable(env); }
  const weekend = net.calls.length;
  at('2026-11-23T10:00:00'); dgResetMemory(); await crnoTable(env);
  assert.equal(net.calls.length, weekend, 'Monday morning: Friday 13:10 is the last boundary');
  assert.ok(crnoDue({ m: {}, at: Date.parse('2026-11-20T13:00:00+09:00') }, Date.parse('2026-11-20T13:11:00+09:00')));
  assert.ok(!crnoDue({ m: {}, at: Date.parse('2026-11-20T13:12:00+09:00') }, Date.parse('2026-11-23T13:09:00+09:00')));
});
await R.test('a list less than half of the previous one is not trusted (old table stays, shape error)', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const kv = makeKV(), env = env0(kv);
  await crnoTable(env);
  at('2026-11-17T14:00:00'); dgResetMemory();
  days['20261116'] = listing('20261116', 900);
  const t = await crnoTable(env);
  assert.equal(t.basDt, '2026-11-13'); assert.equal(t.n, 2903);
  assert.equal(kv.json('datago:err:krx').code, 'shape');
});
await R.test('upstream key error with a table: the old one keeps answering; without a key: null and no call', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const kv = makeKV(), env = env0(kv);
  await crnoTable(env);
  at('2026-11-17T14:00:00'); dgResetMemory();
  net.handler = () => portalXml('30', 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR');
  assert.equal(await crnoOf(env, '005930'), '1301110006246');
  assert.equal(kv.json('datago:err:krx').code, 'key');
  dgResetMemory(); net.calls.length = 0;
  assert.equal(await crnoOf({ REPLAY: makeKV() }, '005930'), null);
  assert.equal(net.calls.length, 0);
});
await R.test('a gateway 429 quota → cool-down until midnight; no KV binding still works in memory', async () => {
  reset();
  const kv = makeKV(), env = env0(kv);
  net.handler = () => gateway(429, 'API token quota exceeded');
  assert.equal(await crnoTable(env), null);
  assert.equal(kv.json('datago:cool:krx').code, 'quota');
  assert.equal(kv.ttl('datago:cool:krx'), 10 * 3600);
  dgResetMemory(); net.handler = handler; days['20261113'] = listing('20261113');
  assert.equal(await crnoOf({ DATA_GO_KR_KEY: KEYS.raw }, '005930'), '1301110006246');
});
await R.test('the key is never in KV, results or the console', async () => {
  reset();
  days['20261113'] = listing('20261113');
  const kv = makeKV(), env = env0(kv);
  const t = await crnoTable(env);
  assertNoKey(JSON.stringify(t.get('005930')), 'info');
  scanKV(kv); scanLogs();
});

R.done();
