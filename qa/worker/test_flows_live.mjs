// 장중 수급 순위 Worker 쪽 (AGENTS §3-40) — worker/src/flows.js · inv.js · kis.js를 가짜 시계 · KV · KIS · 네이버로.
//   node qa/worker/test_flows_live.mjs      exit 0 = 모두 통과
// 네트워크 · 진짜 키 없이 돌아요. KIS · 네이버 응답 모양은 data/ENDPOINTS_KIS.md의 실측 그대로, 값은 지어낸 것.
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const UNIVERSE = readFileSync(new URL('web/universe.json', ROOT), 'utf8');
const U = JSON.parse(UNIVERSE);
const CODES = [];
for (const m of ['K', 'Q']) for (let k = 0; k + 8 <= U[m].length; k += 8) CODES.push(U[m].slice(k, k + 6));

let pass = 0, failed = 0;
const check = (name, ok, detail) => {
  if (ok) { pass++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail !== undefined ? '  → ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 600) : '')); }
};
const section = s => console.log('\n' + s);

/* ── fake clock · cache · KV ─────────────────────────────── */
const realNow = Date.now;
let NOW = Date.parse('2026-11-23T08:00:00+09:00');
Date.now = () => NOW;
const kst = s => Date.parse(s + ':00+09:00');
const cacheStore = new Map();
globalThis.caches = { default: {
  async match(req) { const e = cacheStore.get(req.url); if (!e) return undefined; if (e.exp < NOW) { cacheStore.delete(req.url); return undefined; } return e.res.clone(); },
  async put(req, res) { const m = /max-age=(\d+)/.exec(res.headers.get('cache-control') || ''); cacheStore.set(req.url, { res: res.clone(), exp: NOW + (m ? +m[1] : 0) * 1000, ttl: m ? +m[1] : 0 }); },
  async delete(req) { return cacheStore.delete(req.url); },
} };
function makeKV() {
  const m = new Map(), log = [], fail = { get: null, put: null };
  const live = k => { const e = m.get(k); if (!e) return null; if (e.exp && e.exp <= NOW) { m.delete(k); return null; } return e.v; };
  return {
    m, log, fail,
    async get(k, type) { if (fail.get) throw new Error(fail.get); log.push('get:' + k); const v = live(k); return v == null ? null : type === 'json' ? JSON.parse(v) : v; },
    async put(k, v, o) { if (fail.put) throw new Error(fail.put); log.push('put:' + k); m.set(k, { v: String(v), exp: o && o.expirationTtl ? NOW + o.expirationTtl * 1000 : 0 }); },
    async delete(k) { log.push('del:' + k); m.delete(k); },
    json(k) { const v = live(k); return v == null ? null : JSON.parse(v); },
    puts(prefix = '') { return log.filter(x => x.startsWith('put:' + prefix)).length; },
    all() { return [...m.entries()].map(([k, e]) => k + '=' + e.v).join('\n'); },
  };
}

/* ── fake upstream ─────────────────────────────── */
const KEY = 'FAKEAPPKEY-PSsecret-0123456789abcdefghij', SECRET = 'FAKESECRET-zyxwvutsrq-9876543210ZYXWV';
let tokSeq = 0, curTok = null;
const inj = {};
const resetInj = () => Object.assign(inj, { round: 0, yesterday: false, rankEmpty: false, tradedAt: null, naverFail: false, r2fail: new Set(), rateEvery: 0, keyInMsg: false, zeroLatest: false, uniFail: false,
  dealFail: { KOSPI: false, KOSDAQ: false }, tokenFail: false, allPerm: false });
resetInj();
let calls = {}, kisStarts = [], kisTotal = 0, tokIssues = 0, rateN = 0;
const count = k => { calls[k] = (calls[k] || 0) + 1; };
const num36 = c => parseInt(c, 36);
const fv = (c, r) => ((num36(c) % 997) - 498) * 100 + r * 7;
const iv = (c, r) => (r === 1 ? 0 : ((num36(c) % 613) - 306) * 50 + r);
const sgn = n => (n < 0 ? '-' : '') + String(Math.abs(n)).padStart(17, '0');
const kisJson = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'content-type': 'application/json' } });
globalThis.fetch = async (input, init = {}) => {
  const u = new URL(typeof input === 'string' ? input : input.url);
  const h = new Headers(init.headers || {});
  if (u.host === 'assets.test' && u.pathname === '/universe.json') { count('universe'); return new Response(UNIVERSE); }
  if (u.host === 'openapi.koreainvestment.com:9443') {
    if (u.pathname === '/oauth2/tokenP') {
      tokIssues++; count('token');
      const b = JSON.parse(init.body);
      if (inj.tokenFail || b.appkey !== KEY || b.appsecret !== SECRET) return kisJson({ error_code: 'EGW00103', error_description: `유효하지 않은 AppKey입니다 ${b.appkey}` }, 403);
      curTok = 'FAKETOKEN.' + (++tokSeq) + '.eyJhbGciOiJSUzI1NiJ9-abcdefghijklmnop';
      return kisJson({ access_token: curTok, token_type: 'Bearer', expires_in: 86400 });
    }
    kisTotal++; kisStarts.push(performance.now()); count('kis');
    if (h.get('appkey') !== KEY || h.get('appsecret') !== SECRET || h.get('custtype') !== 'P') return kisJson({ rt_cd: '1', msg_cd: 'EGW00103', msg1: 'bad key' }, 500);
    if (h.get('authorization') !== 'Bearer ' + curTok) return kisJson({ rt_cd: '1', msg_cd: 'EGW00123', msg1: '기간이 만료된 token 입니다.' }, 500);
    if (inj.rateEvery && ++rateN % inj.rateEvery === 0) return kisJson({ rt_cd: '1', msg_cd: 'EGW00201', msg1: '초당 거래건수를 초과하였습니다.' }, 500);
    if (inj.allPerm) return kisJson({ rt_cd: '1', msg_cd: 'OPSQ0002', msg1: `없는 서비스 코드 ${inj.keyInMsg ? KEY + ' ' + curTok : ''}` });
    const q = u.searchParams;
    if (u.pathname.endsWith('/foreign-institution-total')) {
      count('r1'); count('r1:' + q.get('FID_INPUT_ISCD') + ':' + q.get('FID_ETC_CLS_CODE') + ':' + q.get('FID_RANK_SORT_CLS_CODE'));
      if (h.get('tr_id') !== 'FHPTJ04400000' || q.get('FID_COND_MRKT_DIV_CODE') !== 'V' || q.get('FID_COND_SCR_DIV_CODE') !== '16449' || q.get('FID_DIV_CLS_CODE') !== '1') return kisJson({ rt_cd: '1', msg_cd: 'X', msg1: 'bad params' });
      if (inj.rankEmpty) return kisJson({ rt_cd: '0', msg_cd: 'MCA00000', msg1: '정상처리 되었습니다.', output: [] });
      const base = q.get('FID_INPUT_ISCD') === '0001' ? CODES.slice(0, 300) : CODES.slice(300);
      const sell = q.get('FID_RANK_SORT_CLS_CODE') === '1', who = q.get('FID_ETC_CLS_CODE');
      const output = base.slice(0, 30).map((c, k) => {
        const amt = (sell ? -1 : 1) * (30381 - k * 500) * (who === '1' ? 1 : 2);
        return { hts_kor_isnm: 'N' + c, mksc_shrn_iscd: c, stck_prpr: String(161600 - k), prdy_vrss_sign: sell ? '5' : '2', prdy_vrss: '100', prdy_ctrt: sell ? '-1.23' : '0.45', acml_vol: '1000',
          ntby_qty: sgn((sell ? -1 : 1) * (188000 - k)), frgn_ntby_qty: sgn((sell ? -1 : 1) * (188000 - k)), orgn_ntby_qty: sgn((sell ? -1 : 1) * (99000 - k)),
          frgn_ntby_tr_pbmn: who === '1' ? sgn(amt) : '000000000000000100', orgn_ntby_tr_pbmn: who === '2' ? sgn(amt) : '000000000000000200' };
      });
      return kisJson({ rt_cd: '0', msg_cd: 'MCA00000', msg1: '정상처리 되었습니다.', output });
    }
    if (u.pathname.endsWith('/investor-trend-estimate')) {
      count('r2');
      const c = q.get('MKSC_SHRN_ISCD');
      if (h.get('tr_id') !== 'HHPTJ04160200') return kisJson({ rt_cd: '1', msg_cd: 'X', msg1: 'bad tr' });
      if (inj.r2fail.has(c)) return new Response('upstream boom', { status: 502 });
      const R = inj.yesterday ? 5 : inj.round, off = inj.yesterday ? 111 : 0;
      const output2 = [];
      if (inj.zeroLatest && c === '005930') output2.push({ bsop_hour_gb: String(R + 1), frgn_fake_ntby_qty: sgn(0), orgn_fake_ntby_qty: sgn(0), sum_fake_ntby_qty: sgn(0) });
      for (let r = R; r >= 1; r--) output2.push({ bsop_hour_gb: String(r), frgn_fake_ntby_qty: sgn(fv(c, r) + off), orgn_fake_ntby_qty: sgn(iv(c, r) + off), sum_fake_ntby_qty: sgn(fv(c, r) + iv(c, r)) });
      return kisJson({ rt_cd: '0', msg_cd: 'MCA00000', msg1: '정상처리 되었습니다.', output1: [], output2 });
    }
    return kisJson({ rt_cd: '1', msg_cd: 'X', msg1: 'unknown path' }, 404);
  }
  if (u.host === 'polling.finance.naver.com' && u.pathname === '/api/realtime/domestic/stock/005930') {
    count('naverOpen');
    if (inj.naverFail) return new Response('{}', { status: 500 });
    const at = inj.tradedAt || new Date(NOW + 9 * 3600e3 - 20e3).toISOString().slice(0, 19) + '+09:00';
    return Response.json({ datas: [{ itemCode: '005930', localTradedAt: at, marketStatus: 'OPEN' }] });
  }
  if (u.host === 'm.stock.naver.com' && /^\/api\/index\/(KOSPI|KOSDAQ)\/integration$/.test(u.pathname)) {
    const ix = u.pathname.split('/')[3]; count('deal:' + ix);
    if (inj.dealFail[ix]) return new Response('{}', { status: 503 });
    const v = ix === 'KOSPI' ? ['+13,477', '-13,769', '-4,592'] : ['-1,205', '+987', '+12'];
    return Response.json({ dealTrendInfo: { bizdate: new Date(NOW + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, ''), personalValue: v[0], foreignValue: v[1], institutionalValue: v[2] }, programTrendInfo: {} });
  }
  throw new Error('test: unexpected fetch ' + u);
};

/* ── modules ─────────────────────────────── */
const worker = (await import(new URL('worker/src/index.js', ROOT).href)).default;
const flows = await import(new URL('worker/src/flows.js', ROOT).href);
const kis = await import(new URL('worker/src/kis.js', ROOT).href);
const { KF } = flows;
KF.GAP_MS = 0;                                      // 속도 규칙은 6절에서 따로 재요
const coldIsolate = () => { flows.flowsResetMemory(); kis.kisResetMemory(); };
const newEnv = (keys = true) => ({ ASSET_BASE: 'https://assets.test/', REPLAY: makeKV(), ...(keys ? { KIS_APP_KEY: KEY, KIS_APP_SECRET: SECRET } : {}) });
const allLogs = [];
async function fire(env, at, { via = 'tick' } = {}) {
  const ms = kst(at);
  NOW = ms + 3000;
  calls = {};
  const before = kisTotal;
  const oe = console.error, ol = console.log;
  const errs = [];
  console.error = (...a) => { errs.push(a.join(' ')); allLogs.push(a.join(' ')); };
  let res, threw = null;
  try {
    if (via === 'scheduled') { console.log = (...a) => allLogs.push(a.join(' ')); const p = []; await worker.scheduled({ scheduledTime: ms, cron: '* 0-7 * * 2-6' }, env, { waitUntil: x => p.push(x) }); await Promise.all(p); }
    else res = await flows.flowsTick({ scheduledTime: ms }, env);
  } catch (e) { threw = e; }
  finally { console.error = oe; console.log = ol; }
  return { res, threw, kis: kisTotal - before, errs };
}
const ctx = { waitUntil() {} };
async function req(env, path, { method = 'GET', tok, body } = {}) {
  const headers = {};
  if (tok) headers['x-panse-inv'] = tok;
  if (body != null) headers['content-type'] = 'application/json';
  const r = await worker.fetch(new Request('https://panse.pages.dev' + path, { method, headers, body: body == null ? undefined : JSON.stringify(body) }), env, ctx);
  const text = await r.text();
  let j = null; try { j = JSON.parse(text); } catch (e) {}
  return { s: r.status, j, text, cc: r.headers.get('cache-control') };
}
const sha = async s => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, '0')).join('');
const OWNER = 'ownerTokenABCDEFGHIJ0123456789_-xyz', DEV = 'devTokenABCDEFGHIJKL0123456789_-abc';
async function seedInvites(env) {
  await env.REPLAY.put('inv:' + await sha(OWNER), JSON.stringify({ n: '나', own: 1, at: '2026-11-16' }));
  await env.REPLAY.put('inv:' + await sha(DEV), JSON.stringify({ n: 'dev', dev: 1, at: '2026-11-16' }));
}
const st = (env, day = '20261123') => env.REPLAY.json('kisflow:' + day);

/* ── 1. 할 때가 아니면 아무것도 안 해요 ─────────────────────────────── */
section('1. off / weekend / outside hours');
{
  coldIsolate(); resetInj();
  let env = newEnv(false);
  let r = await fire(env, '2026-11-23T09:34');
  check('no KIS keys → off, no KV op, no fetch', r.res === 'off' && env.REPLAY.log.length === 0 && Object.keys(calls).length === 0, { r: r.res, log: env.REPLAY.log, calls });
  env = newEnv();
  r = await fire(env, '2026-11-22T10:04');
  check('Sunday → weekend, no KV op', r.res === 'weekend' && env.REPLAY.log.length === 0, r.res);
  for (const t of ['09:00', '09:33', '16:30']) {
    r = await fire(env, '2026-11-23T' + t);
    check(`${t} → not-due, no KV op, no fetch`, r.res === 'not-due' && env.REPLAY.log.length === 0 && !Object.keys(calls).length, { r: r.res, log: env.REPLAY.log });
  }
  r = await fire({ ...env, KISFLOW: 'off' }, '2026-11-23T09:34');
  check('KISFLOW=off → off', r.res === 'off' && env.REPLAY.log.length === 0);
}

/* ── 2. 평일 하루 (회차 5개 + 늦은 회차 + 마지막 확인) ─────────────────────────────── */
section('2. a normal day (Mon 2026-11-23)');
const ENV = newEnv();
await seedInvites(ENV);
let dayKis = 0, maxRun = 0;
{
  coldIsolate(); resetInj();
  const env = ENV;
  const track = r => { dayKis += r.kis; maxRun = Math.max(maxRun, r.kis); return r; };
  // before the first input: 09:34 probe sees nothing yet
  let r = track(await fire(env, '2026-11-23T09:34'));
  check('09:34, round not in yet → probe only (1 KIS call), no state write', r.res === 'same' && r.kis === 1 && env.REPLAY.puts('kisflow:') === 0, { res: r.res, kis: r.kis });
  check('token issued once, kept in KV kis:tok', tokIssues === 1 && env.REPLAY.json('kis:tok') && env.REPLAY.json('kis:tok').t === curTok);
  r = track(await fire(env, '2026-11-23T09:35'));
  check('09:35 → idle (next check +8 min), no KIS call', r.res === 'idle' && r.kis === 0, r.res);
  inj.round = 1;
  r = track(await fire(env, '2026-11-23T09:42'));
  let s = st(env);
  check('09:42: round 1 found → rank written at once', r.res === 'round' && s && s.rankNo === 1 && s.rankAt === '09:42', { res: r.res, s: s && { rankNo: s.rankNo, no: s.no } });
  check('round 1 = foreign only: 4 rank calls, K/Q × buy/sell', calls.r1 === 4 && calls['r1:0001:1:0'] === 1 && calls['r1:1001:1:1'] === 1 && !calls['r1:0001:2:0'], calls);
  check('this run ≤ 150 KIS calls', r.kis <= 150, r.kis);
  let live = await req(env, '/api/flows/live', { tok: OWNER });
  check('/api/flows/live: slot 09:30 · slotNo 1, est not ready yet', live.s === 200 && live.j.slot === '09:30' && live.j.slotNo === 1 && live.j.estSlot === null && live.j.estN === 0 && live.j.at === '09:42', live.j && { slot: live.j.slot, est: live.j.estSlot, n: live.j.estN });
  const row = live.j.rank.K.f.buy[0];
  check('rank row = [code, name, 억원 1 decimal, qty, price, ratio]', row[0] === CODES[0] && row[1] === 'N' + CODES[0] && row[2] === 303.8 && row[3] === 188000 && row[4] === 161600 && row[5] === 0.45, row);
  const srow = live.j.rank.Q.f.sell[0];
  check('sell row: negative amount · qty, ratio −1.23', srow[2] === -303.8 && srow[3] === -188000 && srow[5] === -1.23, srow);
  check('institutional lists empty at round 1', live.j.rank.K.i.buy.length === 0 && live.j.rank.Q.i.sell.length === 0);
  check('family route headers private, no-store', live.cc === 'private, no-store', live.cc);
  let runs = 1;
  for (const t of ['09:43', '09:44', '09:45', '09:46', '09:47']) { r = track(await fire(env, '2026-11-23T' + t)); if (r.kis) runs++; }
  s = st(env);
  check('② pass done over several minutes (≤ 150 calls each)', s.job === null && s.estNo === 1 && s.estN === 600 && maxRun <= 150 && runs >= 4, { job: !!s.job, estNo: s.estNo, n: s.estN, maxRun, runs });
  check('est values = round-1 row per stock', s.est[CODES[7]][0] === fv(CODES[7], 1) && s.est[CODES[7]][1] === 0 && s.est['005930'][0] === fv('005930', 1));
  check('round 1 KV writes ≤ 6', env.REPLAY.puts('kisflow:') <= 6, env.REPLAY.puts('kisflow:'));
  live = await req(env, '/api/flows/live', { tok: OWNER });
  check('/api/flows/live after the pass: estSlot 09:30 · estN 600', live.j.estSlot === '09:30' && live.j.estN === 600 && Object.keys(live.j.est).length === 600, { estSlot: live.j.estSlot, estN: live.j.estN });
  r = track(await fire(env, '2026-11-23T09:50'));
  check('after the pass: idle, no call', r.res === 'idle' && r.kis === 0, r.res);
  // round 2 on time
  inj.round = 2;
  r = track(await fire(env, '2026-11-23T10:04'));
  check('10:04: round 2 → 8 rank calls', r.res === 'round' && calls.r1 === 8 && st(env).rankNo === 2, { res: r.res, r1: calls.r1 });
  for (let m = 5; m <= 12; m++) track(await fire(env, `2026-11-23T10:${String(m).padStart(2, '0')}`));
  s = st(env);
  check('round 2 est done, inst values present', s.estNo === 2 && s.est[CODES[9]][1] === iv(CODES[9], 2), { estNo: s.estNo });
  // round 3 late: not in at 11:24, in by 11:32
  r = track(await fire(env, '2026-11-23T11:24'));
  check('11:24, round 3 late → probe only, no write', r.res === 'same' && r.kis === 1, { res: r.res, kis: r.kis });
  for (const t of ['11:25', '11:28', '11:31']) { r = track(await fire(env, '2026-11-23T' + t)); check(`${t} → idle between checks`, r.res === 'idle' && r.kis === 0, r.res); }
  inj.round = 3;
  r = track(await fire(env, '2026-11-23T11:32'));
  check('11:32 retry (+12 min) finds round 3', r.res === 'round' && st(env).rankNo === 3, r.res);
  for (let m = 33; m <= 40; m++) track(await fire(env, `2026-11-23T11:${m}`));
  inj.round = 4;
  for (let m = 24; m <= 32; m++) track(await fire(env, `2026-11-23T13:${m}`));
  inj.round = 5;
  for (let m = 34; m <= 42; m++) track(await fire(env, `2026-11-23T14:${m}`));
  s = st(env);
  check('rounds 3–5 ingested (rank 14:30, est 14:30)', s.rankNo === 5 && s.estNo === 5 && s.estN === 600, { rankNo: s.rankNo, estNo: s.estNo });
  // final 15:40: same numbers → ranks refreshed, no second pass
  r = track(await fire(env, '2026-11-23T15:40'));
  s = st(env);
  check('15:40 final: probe + 8 rank calls only, final marked', r.res === 'final' && r.kis === 9 && s.final === 1 && s.rankAt === '15:40', { res: r.res, kis: r.kis, final: s.final });
  r = track(await fire(env, '2026-11-23T15:48'));
  check('15:48 after final → idle', r.res === 'idle' && r.kis === 0, r.res);
  check(`day total KIS calls ≈ 3,050 (got ${dayKis}) ≤ 4,000`, dayKis >= 3000 && dayKis <= 3200, dayKis);
  check(`day KV writes to kisflow:* ≤ 80 (got ${env.REPLAY.puts('kisflow:')})`, env.REPLAY.puts('kisflow:') <= 40);
  check('token issued once for the whole day', tokIssues === 1, tokIssues);
  check('state counter n = calls made', s.n === dayKis, { n: s.n, dayKis });
  // scheduled() in index.js runs the tick too (and the recorder) without throwing
  r = await fire(env, '2026-11-23T15:56', { via: 'scheduled' });
  check('index.js scheduled() resolves with the flows tick inside', !r.threw, r.threw && String(r.threw));
}

/* ── 3. 전날 남은 값 · 휴장 ─────────────────────────────── */
section('3. yesterday\'s rows, holidays');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  inj.yesterday = true;                                // KIS still shows Monday's 5 rounds on Tuesday morning
  let r = await fire(env, '2026-11-24T09:34');
  check('09:34 with 5 rounds in ② (yesterday) → not taken as today', r.res === 'same' && !st(env, '20261124'), { res: r.res });
  r = await fire(env, '2026-11-24T10:04');
  check('10:04 still yesterday\'s 5 rounds → nothing', r.res === 'same' && !st(env, '20261124'), r.res);
  inj.yesterday = false; inj.round = 0; inj.zeroLatest = true;      // a zero row for 005930 = not entered yet
  r = await fire(env, '2026-11-24T10:12');
  check('10:12: 005930 row 0 · 0 → not taken as round 1', r.res === 'same' && !st(env, '20261124'), r.res);
  inj.zeroLatest = false; inj.round = 2;
  r = await fire(env, '2026-11-24T10:20');
  check('today\'s round 2 appears → taken', r.res === 'round' && st(env, '20261124').rankNo === 2, r.res);

  coldIsolate(); resetInj();
  const h = newEnv();
  inj.tradedAt = '2026-12-30T15:30:00+09:00'; inj.yesterday = true;
  r = await fire(h, '2026-12-31T09:34');
  check('holiday 09:34: Naver says no trade today → wait (before 10:30), no KIS call', r.res === 'not-open-yet' && r.kis === 0 && !tokIssues || r.res === 'not-open-yet' && r.kis === 0, { res: r.res, kis: r.kis });
  r = await fire(h, '2026-12-31T10:36');
  check('holiday 10:36 → closed for the day (1 write)', r.res === 'closed' && st(h, '20261231').closed === 'naver' && h.REPLAY.puts('kisflow:') === 1, { res: r.res });
  r = await fire(h, '2026-12-31T11:24');
  check('…then every minute just "closed", no KIS call, no write', r.res === 'closed' && r.kis === 0 && h.REPLAY.puts('kisflow:') === 1, r.res);
  const owner = await req(h, '/api/flows/live', { tok: OWNER });
  check('(no invites in this env) → 403', owner.s === 403);
  await seedInvites(h);
  const lv = await req(h, '/api/flows/live', { tok: OWNER });
  check('live on a holiday: slot null, empty rank, closed:true', lv.j.slot === null && lv.j.rank.K.f.buy.length === 0 && lv.j.closed === true, lv.j);

  coldIsolate(); resetInj();
  const e2 = newEnv();
  inj.naverFail = true; inj.round = 1; inj.rankEmpty = true;
  r = await fire(e2, '2026-11-25T09:34');
  check('Naver down + ① all empty on the first round → closed (empty)', r.res === 'closed' && st(e2, '20261125').closed === 'empty', r.res);
  check('…no ② pass started', !st(e2, '20261125').job && (calls.r2 || 0) === 1, calls);

  coldIsolate(); resetInj();
  const e3 = newEnv();
  inj.tradedAt = '2026-11-18T15:30:00+09:00'; inj.round = 0;     // 수능 day: opens 10:00 — no trade yet at 09:34
  r = await fire(e3, '2026-11-19T09:34');
  check('late opening (수능): before 10:30 no trade today is not a holiday', r.res === 'not-open-yet' && !st(e3, '20261119'), r.res);
  inj.tradedAt = null; inj.round = 2;
  r = await fire(e3, '2026-11-19T10:04');
  check('…opens, round 2 taken at 10:04', r.res === 'round' && st(e3, '20261119').rankNo === 2, r.res);
}

/* ── 4. 한도 ─────────────────────────────── */
section('4. budget caps');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  const save = KF.DAY_MAX;
  KF.DAY_MAX = 300;
  inj.round = 1;
  let total = 0, last;
  for (let m = 34; m <= 50; m++) { last = await fire(env, `2026-11-26T09:${m}`); total += last.kis; }
  const s = st(env, '20261126');
  check('daily cap: calls stop at DAY_MAX (300)', total <= 300 && s.n <= 300 && last.res === 'cap', { total, n: s.n, res: last.res });
  check('…est not replaced by a partial pass', s.estNo === 0 && s.rankNo === 1, { estNo: s.estNo });
  KF.DAY_MAX = save;

  coldIsolate(); resetInj();
  const e2 = newEnv();
  inj.round = 1; inj.rateEvery = 37;                  // KIS answers EGW00201 now and then
  let runs = 0, worst = 0;
  for (let m = 34; m <= 50; m++) { const r = await fire(e2, `2026-11-26T09:${m}`); if (r.kis) runs++; worst = Math.max(worst, r.kis); }
  const s2 = st(e2, '20261126');
  check('EGW00201 stops the run; requeued codes finish later (est 600)', s2.estNo === 1 && s2.estN === 600 && worst <= 150, { estN: s2.estN, worst, runs });
  check('…the rate-limit error is kept, scrubbed', s2.err && /EGW00201/.test(s2.err.code), s2.err);

  coldIsolate(); resetInj();
  const e3 = newEnv();
  inj.round = 1;
  inj.r2fail = new Set(CODES.slice(100, 110));
  for (let m = 34; m <= 50; m++) await fire(e3, `2026-11-26T09:${m}`);
  const s3 = st(e3, '20261126');
  check('10 stocks failing twice → est 590 (retried once, then dropped)', s3.estNo === 1 && s3.estN === 590 && !s3.est[CODES[105]], { estN: s3.estN });

  coldIsolate(); resetInj();
  const e4 = newEnv();
  inj.round = 1; inj.allPerm = true; inj.keyInMsg = true;
  let r = await fire(e4, '2026-11-26T09:34');
  check('every call refused → probe error recorded, scrubbed', r.res === 'probe-failed' && st(e4, '20261126') && st(e4, '20261126').err.code === 'probe-OPSQ0002' && !e4.REPLAY.all().includes(KEY) && !JSON.stringify(st(e4, '20261126')).includes(curTok) && r.errs.every(l => !l.includes(KEY) && !l.includes(curTok)), { res: r.res, err: st(e4, '20261126') && st(e4, '20261126').err });
}

/* ── 5. 토큰 ─────────────────────────────── */
section('5. token reuse / lock / day cap');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  NOW = kst('2026-11-27T09:00');
  const before = tokIssues;
  const toks = await Promise.all([kis.kisToken(env), kis.kisToken(env), kis.kisToken(env)]);
  check('3 concurrent kisToken() in one isolate → one issue', tokIssues - before === 1 && toks.every(t => t === toks[0]), tokIssues - before);
  coldIsolate();
  await kis.kisToken(env);
  check('a cold isolate reuses KV kis:tok (no new issue)', tokIssues - before === 1);
  // invalid token answer → one fresh issue, after the 70 s lock
  NOW += 80e3; coldIsolate();
  curTok = 'FAKETOKEN.rotated-by-kis-xxxxxxxxxxxx';     // KIS forgot our token
  inj.round = 1;
  const r1 = await kis.kisGet(env, '/uapi/domestic-stock/v1/quotations/investor-trend-estimate', 'HHPTJ04160200', { MKSC_SHRN_ISCD: '005930' });
  check('EGW00123 → token re-issued once, call succeeds', r1.status === 200 && r1.j.rt_cd === '0' && tokIssues - before === 2, { s: r1.status, n: tokIssues - before });
  // lock: no token in KV and the lock is set → no issue, tick waits
  const e2 = newEnv();
  coldIsolate();
  NOW = kst('2026-11-27T09:34') + 1000;
  await e2.REPLAY.put('kis:toklock', '1', { expirationTtl: 70 });
  let r = await fire(e2, '2026-11-27T09:34');
  check('token lock held → no issue, probe skipped this minute', r.res === 'probe-failed' && tokIssues - before === 2 && r.kis === 0, { res: r.res });
  r = await fire(e2, '2026-11-27T09:42');                // lock expired (70 s)
  check('next check after the lock → issued and round taken', r.res === 'round' && tokIssues - before === 3, { res: r.res });
  // day cap: 3 issues per KST day
  const e3 = newEnv();
  await e3.REPLAY.put('kis:tokday', JSON.stringify({ day: '2026-11-27', n: 3 }));
  coldIsolate();
  let err = null; try { await kis.kisToken(e3); } catch (e) { err = e.message; }
  check('4th issue in a day refused (kis-token-daycap)', err === 'kis-token-daycap', err);
  // bad keys → cool down 30 min, scrubbed
  const e4 = newEnv();
  e4.KIS_APP_KEY = KEY.replace('FAKE', 'BADX');
  coldIsolate();
  r = await fire(e4, '2026-11-27T09:34');
  const s4 = st(e4, '20261127');
  check('bad keys → cool-down 30 min, error kept without the key', r.res === 'probe-failed' && s4 && s4.cool > NOW + 25 * 60e3 && !JSON.stringify(s4).includes(e4.KIS_APP_KEY) && !JSON.stringify(s4).includes(SECRET), s4 && s4.err);
  r = await fire(e4, '2026-11-27T09:42');
  check('…while cooling: no call', r.res === 'cool' && r.kis === 0, r.res);
}

/* ── 6. 초당 10번 ─────────────────────────────── */
section('6. ≤ 10 KIS calls per second');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  KF.GAP_MS = 110; const save = KF.CALLS_PER_RUN; KF.CALLS_PER_RUN = 25;
  inj.round = 1; kisStarts = [];
  await fire(env, '2026-11-30T09:34');
  let worst = 0;
  for (let i = 0; i < kisStarts.length; i++) { let n = 0; for (let j = i; j < kisStarts.length && kisStarts[j] - kisStarts[i] < 1000; j++) n++; worst = Math.max(worst, n); }
  check(`25 calls paced: at most ${worst} in any 1 s window (≤ 10)`, kisStarts.length === 25 && worst <= 10, { n: kisStarts.length, worst });
  KF.GAP_MS = 0; KF.CALLS_PER_RUN = save;
}

/* ── 7. 초대 ─────────────────────────────── */
section('7. invites');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  await seedInvites(env);
  NOW = kst('2026-11-23T12:00');
  for (const p of ['/api/flows/live', '/api/flows/live/stock/005930', '/api/inv/me', '/api/inv']) {
    const a = await req(env, p), b = await req(env, p, { tok: 'notAValidTokenButLongEnough123' }), c = await req(env, p, { tok: 'short' });
    check(`${p}: no / wrong / malformed token → 403 {error:'forbidden'}`, [a, b, c].every(x => x.s === 403 && x.j.error === 'forbidden' && x.cc === 'private, no-store'), [a.s, b.s, c.s]);
  }
  let r = await req(env, '/api/inv/me', { tok: OWNER });
  check('/api/inv/me owner → {n:"나", own:true}', r.s === 200 && r.j.n === '나' && r.j.own === true, r.j);
  r = await req(env, '/api/inv/me', { tok: DEV });
  check('/api/inv/me dev → own:false', r.s === 200 && r.j.own === false, r.j);
  check('dev invite cannot list', (await req(env, '/api/inv', { tok: DEV })).s === 403);
  const slotKeys = e => [...e.REPLAY.m.keys()].filter(k => /^inv:s:\d+$/.test(k));
  check('no list yet (no inv:s:* slots)', slotKeys(env).length === 0);
  r = await req(env, '/api/inv', { tok: OWNER });
  check('GET /api/inv builds the index lazily: owner only, no dev', r.s === 200 && r.j.items.length === 1 && r.j.items[0].n === '나' && r.j.items[0].own === true && r.j.items[0].id === (await sha(OWNER)).slice(0, 12), r.j);
  check('…and stores it in one slot', slotKeys(env).length === 1 && env.REPLAY.json(slotKeys(env)[0]).own === 1);
  r = await req(env, '/api/inv', { method: 'POST', tok: OWNER, body: { n: '엄마' } });
  const mom = r.j;
  check('POST {n:"엄마"} → {id, token}', r.s === 200 && /^[0-9a-f]{12}$/.test(mom.id) && /^[A-Za-z0-9_-]{32}$/.test(mom.token) && r.cc === 'private, no-store', r.j);
  check('server keeps only the hash', !env.REPLAY.all().includes(mom.token) && env.REPLAY.json('inv:' + await sha(mom.token)).n === '엄마');
  r = await req(env, '/api/inv/me', { tok: mom.token });
  check('new token works: {n:"엄마", own:false}', r.s === 200 && r.j.n === '엄마' && r.j.own === false, r.j);
  check('family can read /api/flows/live', (await req(env, '/api/flows/live', { tok: mom.token })).s === 200);
  check('family cannot list / create', (await req(env, '/api/inv', { tok: mom.token })).s === 403 && (await req(env, '/api/inv', { method: 'POST', tok: mom.token, body: { n: 'x' } })).s === 403);
  r = await req(env, '/api/inv', { tok: OWNER });
  check('list: 나 · 엄마, no token in it', r.j.items.length === 2 && r.j.items[1].n === '엄마' && !r.j.items[1].own && !r.text.includes(mom.token), r.j);
  for (const [n, why] of [['', 'empty'], ['   ', 'blank'], ['가나다라마바사아자차카타파', '13 chars'], [12, 'number']]) {
    r = await req(env, '/api/inv', { method: 'POST', tok: OWNER, body: { n } });
    check(`POST name ${why} → 400`, r.s === 400, r.s);
  }
  r = await req(env, '/api/inv', { method: 'POST', tok: OWNER, body: { n: '가나다라마바사아자차카타' } });
  check('12 Korean characters OK', r.s === 200, r.j);
  r = await req(env, '/api/inv/' + (await sha(OWNER)).slice(0, 12), { method: 'DELETE', tok: OWNER });
  check('DELETE yourself → 409', r.s === 409, r.j);
  check('DELETE bad id → 400, unknown → 404', (await req(env, '/api/inv/xyz', { method: 'DELETE', tok: OWNER })).s === 400 && (await req(env, '/api/inv/abcdefabcdef', { method: 'DELETE', tok: OWNER })).s === 404);
  check('PUT /api/inv → 405, POST /api/inv/me → 405', (await req(env, '/api/inv', { method: 'PUT', tok: OWNER })).s === 405 && (await req(env, '/api/inv/me', { method: 'POST', tok: OWNER })).s === 405);
  r = await req(env, '/api/inv/' + mom.id, { method: 'DELETE', tok: OWNER });
  check('DELETE 엄마 → {ok:true}', r.s === 200 && r.j.ok === true, r.j);
  check('…her token is now refused everywhere', (await req(env, '/api/inv/me', { tok: mom.token })).s === 403 && (await req(env, '/api/flows/live', { tok: mom.token })).s === 403);
  check('…and she is gone from the list', (await req(env, '/api/inv', { tok: OWNER })).j.items.length === 2);
  // a second owner: owners may switch each other off, never the last one / themselves
  const OWNER2 = 'owner2TokenABCDEFGHIJ0123456789_-q';
  await env.REPLAY.put('inv:' + await sha(OWNER2), JSON.stringify({ n: '나2', own: 1, at: '2026-11-23' }));
  await req(env, '/api/inv', { tok: OWNER2 });           // joins the index
  r = await req(env, '/api/inv/' + (await sha(OWNER)).slice(0, 12), { method: 'DELETE', tok: OWNER2 });
  check('second owner switches the first off (one owner left)', r.s === 200);
  r = await req(env, '/api/inv/' + (await sha(OWNER2)).slice(0, 12), { method: 'DELETE', tok: OWNER2 });
  check('…cannot switch off itself (the last owner) → 409', r.s === 409);
  // max 20
  let last;
  for (let i = 0; i < 25; i++) last = await req(env, '/api/inv', { method: 'POST', tok: OWNER2, body: { n: '가족' + i } });
  check('list holds at most 20 → 409 after', last.s === 409 && slotKeys(env).length === 20, { s: last.s, n: slotKeys(env).length });
  check('…no orphan record left by the refused POST', [...env.REPLAY.m.keys()].filter(k => /^inv:[0-9a-f]{64}$/.test(k)).length === 20 + 1, [...env.REPLAY.m.keys()].filter(k => /^inv:[0-9a-f]{64}$/.test(k)).length);   // 20 listed + dev
}

/* ── 7b. 초대 — KV 오류 · 옛 목록 옮기기 · 겹친 쓰기 · 스스로 고침 ─────────────────────────────── */
section('7b. invites: KV errors, migration, overlapping writes, self-heal');
{
  const env = newEnv();
  await seedInvites(env);
  NOW = kst('2026-11-23T12:00');
  env.REPLAY.fail.get = 'KV GET failed: 503';
  for (const p of ['/api/inv/me', '/api/inv', '/api/flows/live', '/api/flows/live/stock/005930', '/api/archive/consensus/days']) {
    const r = await req(env, p, { tok: OWNER });
    check(`${p}: KV read error → 503 {error:'unavailable'} (not 403)`, r.s === 503 && r.j && r.j.error === 'unavailable', { s: r.s, j: r.j });
  }
  env.REPLAY.fail.get = null;
  check('…a missing record is still 403', (await req(env, '/api/inv/me', { tok: 'neverIssuedTokenABCDEFGHIJ0123' })).s === 403);
  let flaky = 0;                                       // one failed read, then fine → retried once, no 503
  const g0 = env.REPLAY.get.bind(env.REPLAY);
  env.REPLAY.get = async (k, t) => { if (flaky++ === 0) throw new Error('blip'); return g0(k, t); };
  check('one KV blip → retried, 200', (await req(env, '/api/inv/me', { tok: OWNER })).s === 200);
  env.REPLAY.get = g0;

  // the old single list (live since 11/23) moves into slots once
  const MOM = 'momTokenABCDEFGHIJKLMNOP0123456789', DAD = 'dadTokenABCDEFGHIJKLMNOP0123456789';
  await env.REPLAY.put('inv:' + await sha(MOM), JSON.stringify({ n: '엄마', at: '2026-11-23' }));
  await env.REPLAY.put('inv:' + await sha(DAD), JSON.stringify({ n: '아빠', at: '2026-11-23' }));
  await env.REPLAY.put('inv:index', JSON.stringify([{ h: await sha(OWNER), n: '나', at: '2026-11-16', own: 1 }, { h: await sha(MOM), n: '엄마', at: '2026-11-23' }, { h: await sha(DAD), n: '아빠', at: '2026-11-23' }]));
  let r = await req(env, '/api/inv', { tok: OWNER });
  check('old inv:index migrated: 3 items, list deleted', r.s === 200 && r.j.items.map(x => x.n).join() === '나,엄마,아빠' && !env.REPLAY.m.has('inv:index'), r.j);
  // overlapping writes no longer drop entries
  const [a, b, c] = await Promise.all([
    req(env, '/api/inv', { method: 'POST', tok: OWNER, body: { n: '언니' } }),
    req(env, '/api/inv', { method: 'POST', tok: OWNER, body: { n: '동생' } }),
    req(env, '/api/inv/' + (await sha(DAD)).slice(0, 12), { method: 'DELETE', tok: OWNER }),
  ]);
  r = await req(env, '/api/inv', { tok: OWNER });
  const names = r.j.items.map(x => x.n).sort().join();
  check('two POSTs + a DELETE at once → both new listed, the deleted one gone', a.s === 200 && b.s === 200 && c.s === 200 && names === ['나', '엄마', '언니', '동생'].sort().join(), { names, s: [a.s, b.s, c.s] });
  // a slot whose record vanished (crash between the two deletes) is cleaned on the next list
  await env.REPLAY.delete('inv:' + await sha(MOM));
  r = await req(env, '/api/inv', { tok: OWNER });
  check('GET heals a slot whose record is gone', !r.j.items.some(x => x.n === '엄마') && r.j.items.length === 3, r.j.items.map(x => x.n));
}

/* ── 7c. 회차 받기 — 유니버스 실패 · 네이버 없음 · 확인된 날의 빈 ① ─────────────────────────────── */
section('7c. rounds: universe failure, Naver silent, empty ① on a confirmed day');
{
  flows.configureFlows({ codes: async () => { if (inj.uniFail) throw new Error('universe 503'); return CODES; } });
  coldIsolate(); resetInj();
  const env = newEnv();
  inj.round = 1; inj.uniFail = true;
  let r = await fire(env, '2026-12-01T09:34');
  let s = st(env, '20261201');
  check('universe fails → round not taken (no 0 → 1), no ① calls, error kept', r.res === 'no-universe' && s.no === 0 && s.seen === 1 && !calls.r1 && s.err.code === 'universe', { res: r.res, no: s && s.no, r1: calls.r1 });
  inj.uniFail = false;
  r = await fire(env, '2026-12-01T09:35');
  s = st(env, '20261201');
  check('…next minute retried (seen > no): round 1 taken, ① + job', r.res === 'round' && s.no === 1 && s.rankNo === 1 && !!s.job, { res: r.res });

  // Naver silent + KIS still shows the last trading day's final rows → not today
  coldIsolate(); resetInj();
  const e2 = newEnv();
  inj.naverFail = true; inj.yesterday = true;
  const yRows = [1, 2, 3, 4, 5].map(no => ({ no, f: fv('005930', no) + 111, i: iv('005930', no) + 111 }));
  await e2.REPLAY.put('kisflow:last', JSON.stringify({ day: '20261230', rows: yRows }));
  r = await fire(e2, '2026-12-31T14:34');
  check('Naver silent, 5 rows = last stored day → not taken as today', r.res === 'not-today' && !st(e2, '20261231') && !calls.r1, { res: r.res });
  await e2.REPLAY.delete('kisflow:last');
  coldIsolate();
  r = await fire(e2, '2026-12-31T14:42');
  check('Naver silent, nothing to compare, 5 rows → skipped too', r.res === 'not-today' && !st(e2, '20261231'), r.res);
  inj.yesterday = false; inj.round = 5;
  await e2.REPLAY.put('kisflow:last', JSON.stringify({ day: '20261230', rows: yRows }));
  coldIsolate();
  r = await fire(e2, '2026-12-31T14:50');
  check('Naver silent, rows differ from the last day → taken', r.res === 'round' && st(e2, '20261231').no === 5, r.res);
  check('…and today\'s rows become the new kisflow:last', (e2.REPLAY.json('kisflow:last') || {}).day === '20261231');

  // Naver confirmed trading: an all-empty ① on round 1 is not a holiday
  coldIsolate(); resetInj();
  const e3 = newEnv();
  inj.round = 1; inj.rankEmpty = true;
  r = await fire(e3, '2026-12-02T09:34');
  s = st(e3, '20261202');
  check('Naver says traded today + ① empty → not closed, job runs', r.res === 'round' && !s.closed && !!s.job && s.rankNo === 1, { res: r.res, closed: s && s.closed });

  // weekends say closed:true (≠ "before 09:30")
  const e4 = newEnv(); await seedInvites(e4);
  NOW = kst('2026-11-28T10:00');
  r = await req(e4, '/api/flows/live', { tok: OWNER });
  check('Saturday /api/flows/live → closed:true, slot null', r.j.closed === true && r.j.slot === null, r.j);
  NOW = kst('2026-11-30T09:00');
  r = await req(e4, '/api/flows/live', { tok: OWNER });
  check('Monday 09:00 → no closed (before the first round)', !('closed' in r.j) && r.j.slot === null, r.j);
  NOW = kst('2026-11-29T10:00');
  r = await req(e4, '/api/flows/live/stock/005930', { tok: OWNER });
  check('Sunday stock route → slots [] + closed:true', r.j.closed === true && r.j.slots.length === 0, r.j);
}

/* ── 8. 종목 경로 ─────────────────────────────── */
section('8. /api/flows/live/stock/{code}');
{
  coldIsolate(); resetInj();
  const env = newEnv();
  await seedInvites(env);
  inj.round = 3;
  NOW = kst('2026-11-23T11:40');
  let before = kisTotal;
  let r = await req(env, '/api/flows/live/stock/000660', { tok: OWNER });
  check('first call → one KIS call, slots oldest first', r.s === 200 && kisTotal - before === 1 && r.j.code === '000660' && r.j.date === '2026-11-23' && r.j.slots.length === 3 && r.j.slots[0].no === 1 && r.j.slots[0].t === '09:30' && r.j.slots[2].t === '11:20' && r.j.slots[2].f === fv('000660', 3) && r.j.slots[2].i === iv('000660', 3), r.j);
  check('private, no-store', r.cc === 'private, no-store');
  before = kisTotal; NOW += 60e3;
  r = await req(env, '/api/flows/live/stock/000660', { tok: OWNER });
  check('within 3 min (same isolate) → no KIS call', kisTotal === before && r.j.slots.length === 3);
  coldIsolate();
  r = await req(env, '/api/flows/live/stock/000660', { tok: OWNER });
  check('within 3 min (cold isolate) → KV copy, no KIS call', kisTotal === before && r.j.slots.length === 3);
  NOW = kst('2026-11-23T13:30'); inj.round = 4;
  r = await req(env, '/api/flows/live/stock/000660', { tok: OWNER });
  check('after 3 min → fresh call (4 slots)', kisTotal === before + 1 && r.j.slots.length === 4, r.j);
  inj.r2fail = new Set(['000660']); NOW += 4 * 60e3;
  r = await req(env, '/api/flows/live/stock/000660', { tok: OWNER });
  check('KIS fails → last copy + stale:true', r.s === 200 && r.j.stale === true && r.j.slots.length === 4, r.j);
  r = await req(env, '/api/flows/live/stock/035720', { tok: OWNER });
  check('…and a stock without a copy during the cool-down → 503', r.s === 503 && r.j.error, r);
  inj.r2fail = new Set();
  check('bad code → 400 (0126Z0 style codes are fine)', (await req(env, '/api/flows/live/stock/12345', { tok: OWNER })).s === 400 && (await req(env, '/api/flows/live/stock/abc123', { tok: OWNER })).s === 400);
  before = kisTotal; NOW = kst('2026-11-28T11:00');
  r = await req(env, '/api/flows/live/stock/005930', { tok: OWNER });
  check('Saturday → slots [] without a KIS call', r.s === 200 && r.j.slots.length === 0 && r.j.closed === true && kisTotal === before, r.j);
  coldIsolate(); inj.yesterday = true; NOW = kst('2026-11-30T09:25');
  r = await req(env, '/api/flows/live/stock/005930', { tok: OWNER });
  check('Monday 09:25 with yesterday\'s 5 rounds → slots []', r.s === 200 && r.j.slots.length === 0, r.j);
  inj.yesterday = false;
  NOW = kst('2026-11-30T09:10'); before = kisTotal;
  r = await req(env, '/api/flows/live/stock/005930', { tok: OWNER });
  check('before 09:20 → slots [] without a call', r.j.slots.length === 0 && kisTotal === before);
  const e2 = newEnv(); await seedInvites(e2);
  await e2.REPLAY.put('kisflow:20261231', JSON.stringify({ day: '20261231', closed: 'naver' }));
  NOW = kst('2026-12-31T11:00'); before = kisTotal;
  r = await req(e2, '/api/flows/live/stock/005930', { tok: OWNER });
  check('holiday (state closed) → slots [] + closed, no call', r.j.slots.length === 0 && r.j.closed === true && kisTotal === before, r.j);
}

/* ── 9. 아직 없는 날 · /api/flows/live 모양 ─────────────────────────────── */
section('9. /api/flows/live before anything');
{
  coldIsolate();
  const env = newEnv(); await seedInvites(env);
  NOW = kst('2026-12-01T08:59');
  const r = await req(env, '/api/flows/live', { tok: OWNER });
  const j = r.j;
  check('slot null · slotNo 0 · empty rank skeleton · est {} · date today', r.s === 200 && j.date === '2026-12-01' && j.slot === null && j.slotNo === 0 && j.at === null && j.estSlot === null && j.estN === 0 && Object.keys(j.est).length === 0 &&
    ['K', 'Q'].every(m => ['f', 'i'].every(w => Array.isArray(j.rank[m][w].buy) && !j.rank[m][w].buy.length && Array.isArray(j.rank[m][w].sell))) && j.src === '한국투자증권 가집계' && j.unit === '억원', j);
  check('no dev block for a non-dev invite', !('run' in j));
  const d = await req(env, '/api/flows/live', { tok: DEV });
  check('dev invite gets a small run block', d.j && 'run' in d.j);
  check('POST /api/flows/live → 405', (await req(env, '/api/flows/live', { method: 'POST', tok: OWNER })).s === 405);
}

/* ── 10. /api/flows/market ─────────────────────────────── */
section('10. /api/flows/market');
{
  coldIsolate(); resetInj(); cacheStore.clear();
  const env = newEnv(false);
  NOW = kst('2026-11-23T10:00');
  let r = await req(env, '/api/flows/market');
  check('public (no invite), parses "+13,477" → 13477', r.s === 200 && r.j.K.personal === 13477 && r.j.K.foreign === -13769 && r.j.K.institutional === -4592 && r.j.Q.personal === -1205 && r.j.Q.institutional === 12, r.j);
  check('date from bizdate, asOf ISO', r.j.date === '2026-11-23' && /^\d{4}-\d{2}-\d{2}T/.test(r.j.asOf) && !r.j.stale);
  const e = cacheStore.get('https://panse.pages.dev/__cache/flows-market');
  check('edge cache 60 s in the session', e && e.ttl === 60 && r.cc === 'public, max-age=60', e && e.ttl);
  check('KV last copy written', env.REPLAY.json('flows:mkt') && env.REPLAY.json('flows:mkt').body.K.personal === 13477);
  const deal0 = calls['deal:KOSPI'];
  r = await req(env, '/api/flows/market');
  check('second hit served from the edge cache', calls['deal:KOSPI'] === deal0);
  cacheStore.clear(); NOW = kst('2026-11-23T20:00');
  r = await req(env, '/api/flows/market');
  check('evening → 10 min edge cache', cacheStore.get('https://panse.pages.dev/__cache/flows-market').ttl === 600, r.cc);
  cacheStore.clear(); inj.dealFail = { KOSPI: true, KOSDAQ: true };
  r = await req(env, '/api/flows/market');
  check('both fail → last KV copy + stale:true', r.s === 200 && r.j.stale === true && r.j.K.personal === 13477, r.j);
  cacheStore.clear(); inj.dealFail = { KOSPI: false, KOSDAQ: true };
  r = await req(env, '/api/flows/market');
  check('KOSDAQ fails → Q from the same-day copy, stale', r.s === 200 && r.j.Q && r.j.Q.personal === -1205 && r.j.stale === true, r.j);
  const e2 = newEnv(false); cacheStore.clear(); inj.dealFail = { KOSPI: true, KOSDAQ: true };
  r = await req(e2, '/api/flows/market');
  check('nothing at all → 503, not cached', r.s === 503 && !cacheStore.has('https://panse.pages.dev/__cache/flows-market'), r.s);
  check('dealOf: missing block → null', flows.dealOf({}) === null && flows.dealOf({ dealTrendInfo: { bizdate: '20261116', personalValue: '+13,477' } }).v.foreign === null);
}

/* ── 11. 키 · 토큰이 어디에도 없어요 ─────────────────────────────── */
section('11. scrub');
{
  const stores = [ENV].map(e => e.REPLAY.all()).join('\n');
  const tok = (ENV.REPLAY.json('kis:tok') || {}).t;
  const without = stores.split(tok).join('');                     // kis:tok itself is the token's one home
  check('KV (except kis:tok) has no app key / secret / access token', !stores.includes(KEY) && !stores.includes(SECRET) && !without.includes(tok));
  check('console output has no app key / secret / token', !allLogs.some(l => l.includes(KEY) || l.includes(SECRET) || /FAKETOKEN/.test(l)), allLogs.filter(l => l.includes(KEY) || /FAKETOKEN/.test(l)).slice(0, 3));
  const lv = await req(ENV, '/api/flows/live', { tok: DEV });
  check('live response (dev) has no key / token', !lv.text.includes(KEY) && !lv.text.includes(SECRET) && !/FAKETOKEN/.test(lv.text));
  check('kisScrub removes key, secret, token', !kis.kisScrub(`x ${KEY} ${SECRET} ${curTok}`, { KIS_APP_KEY: KEY, KIS_APP_SECRET: SECRET }, curTok).match(/FAKE/));
}

/* ── 12. Pages가 그대로 넘겨요 ─────────────────────────────── */
section('12. Pages _worker.js passes header + method + body through');
{
  const pages = (await import(new URL('worker/pages/panse_worker.js', ROOT).href)).default;
  let seen = null;
  const env = { API: { fetch: async r => { seen = { m: r.method, h: r.headers.get('x-panse-inv'), b: await r.text(), u: r.url }; return new Response('ok'); } } };
  await pages.fetch(new Request('https://panse.pages.dev/api/inv', { method: 'POST', headers: { 'x-panse-inv': OWNER, 'content-type': 'application/json' }, body: '{"n":"엄마"}' }), env);
  check('POST + X-Panse-Inv + body unchanged', seen && seen.m === 'POST' && seen.h === OWNER && seen.b === '{"n":"엄마"}' && seen.u.endsWith('/api/inv'), seen);
  await pages.fetch(new Request('https://panse.pages.dev/api/inv/abcdefabcdef', { method: 'DELETE', headers: { 'x-panse-inv': OWNER } }), env);
  check('DELETE unchanged', seen.m === 'DELETE' && seen.h === OWNER);
}

console.log(`\nflows live: ${pass}/${pass + failed} passed`);
Date.now = realNow;
process.exit(failed ? 1 : 0);
