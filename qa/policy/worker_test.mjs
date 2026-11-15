// Worker /api/policy unit checks (docs/standards/policy-feeds.md) — no network, no real key: KDI is the sanitized fixture
// qa/policy/fixtures/kdi.xml (title · link · the first words of each description, taken 2026-11-15), the gazette API is a fake that
// answers like the portal's Swagger (response.items.item[] with cntntSj · pblcnInstNm · cmplatSeNm · hopePblictDt · pdfFilePath …),
// caches.default and KV are in-memory, Date.now is a fake clock.
//   node qa/policy/worker_test.mjs            exit 1 on any failure
import { readFileSync } from 'node:fs';

const HERE = new URL('.', import.meta.url);
const KDI_XML = readFileSync(new URL('fixtures/kdi.xml', HERE), 'utf8');
const KEY = 'Ab+cd/EF==SECRETkey123';                       // a fake "decoding" key with + / = (never a real one)
const KEY_ENC = 'Ab%2Bcd%2FEF%3D%3DSECRETkey123';
const MARK = 'SECRETkey123';                               // any trace of the key contains this
const BODY_MARK = 'BODY-개정이유-본문';                      // the gazette's 개정이유 · KDI descriptions must never come out

// ── fake clock ──
const realNow = Date.now.bind(Date);
let NOW = Date.parse('2026-11-15T08:00:00Z');                // 일 17:00 KST
Date.now = () => NOW;
const at = (iso) => { NOW = Date.parse(iso); };

// ── capture everything that could carry the key: console, responses, KV values ──
const outputs = [];
const say = console.log.bind(console);                     // the checks' own lines (not captured)
for (const k of ['log', 'info', 'warn', 'error', 'debug']) {
  const orig = console[k].bind(console);
  console[k] = (...a) => { outputs.push(a.map(String).join(' ')); orig(...a); };
}
let sentKey = 0;

// ── stubs ──
let cacheStore = new Map();
globalThis.caches = { default: {
  async match(req) { const e = cacheStore.get(req.url); if (!e || Date.now() > e.exp) return undefined; return e.res.clone(); },
  async put(req, res) { const cc = res.headers.get('cache-control') || ''; const m = /s-maxage=(\d+)/.exec(cc); if (m) cacheStore.set(req.url, { exp: Date.now() + m[1] * 1000, res: res.clone() }); },
} };
function makeKV() {
  const m = new Map(), log = [];
  return { _m: m, log,
    async get(k, type) { log.push(['get', k]); const e = m.get(k); if (!e || (e.exp && e.exp < Date.now())) return null; return type === 'json' ? JSON.parse(e.v) : e.v; },
    async put(k, v, o) { log.push(['put', k, o && o.expirationTtl]); outputs.push(String(v)); m.set(k, { v: String(v), exp: o && o.expirationTtl ? Date.now() + o.expirationTtl * 1000 : null }); },
  };
}

const KDI_URL = 'https://eiec.kdi.re.kr/policy/rss.do?rss_type=material';
const GB_URL = 'https://apis.data.go.kr/1741000/ApiTotalService/getApiTotalList';
const ORGS = ['재정경제부', '금융위원회', '한국은행', '산업통상부', '공정거래위원회', '국세청', '관세청', '기획예산처', '국토교통부', '보건복지부', '행정안전부', '국방부', '산림청'];
const KINDS = ['고시', '공고', '부령', '대통령령', '훈령', '인사', '고시'];
const IN = /재정경제부|기획재정부|기획예산처|금융위원회|증권선물위원회|금융감독원|한국은행|산업통상|공정거래위원회|국세청|관세청/;
const pad = (n, w = 2) => String(n).padStart(w, '0');
// rows of one gazette day (weekdays only)
const DAY_N = { 20261111: 80, 20261112: 120, 20261113: 230, 20261116: 150, 20261117: 40 };
function gazetteRows(ymd) {
  const n = DAY_N[ymd] || 0, out = [];
  for (let i = 0; i < n; i++) {
    const org = ORGS[i % ORGS.length], kind = KINDS[(i * 3) % KINDS.length];
    const dt = i % 3 === 0 ? `${ymd.slice(0, 4)}. ${ymd.slice(4, 6)}. ${ymd.slice(6)}.` : i % 3 === 1 ? `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6)}` : ymd;
    out.push({ cntntSeqNo: `${ymd}${pad(i, 5)}`, cntntSj: `${org}${kind} 제2026-${i}호 (시험 ${ymd}-${i}) &amp; 「자본시장법」`, ofcttBookNm: '정호', hopePblictDt: dt,
      cmplatSeNm: kind, themaSe: '경제', pblcnInstNm: org, basisLawNm: '행정절차법', crtnYn: '아니요', rvsnRsnMainCn: BODY_MARK + ' ' + 'x'.repeat(300),
      pdfFilePath: i % 11 === 5 ? 'http://gwanbo.go.kr/ezpdf/' + ymd + '/' + i + '.pdf' : i % 13 === 7 ? 'https://evil.example.com/x.pdf' : i % 17 === 9 ? '' : `/ezpdf/customLayout.jsp?viewPath=/data/${ymd}/${i}.pdf` });
  }
  return out;
}
function gbJson(sp, opts = {}) {
  const ymd = sp.get('reqFrom'), page = +sp.get('pageNo'), size = +sp.get('pageSize');
  const all = gazetteRows(ymd), rows = all.slice((page - 1) * size, page * size);
  if (!all.length && opts.code10) return { response: { resultCode: '10', resultMsg: 'NODATA_ERROR' } };
  const item = opts.single && rows.length ? rows[0] : rows;
  return { response: { resultCode: '00', resultMsg: 'NORMAL SERVICE.', totalCount: String(opts.single ? Math.min(1, all.length) : all.length), pageSize: String(size), pageNo: String(page), items: all.length ? { item } : '' } };
}
const gwXml = (code, msg) => `<?xml version="1.0" encoding="UTF-8"?>\n<OpenAPI_ServiceResponse>\n<cmmMsgHeader>\n  <errMsg>${msg}</errMsg>\n  <returnAuthMsg>${msg}</returnAuthMsg>\n  <returnReasonCode>${code}</returnReasonCode>\n</cmmMsgHeader>\n</OpenAPI_ServiceResponse>`;

let kdiB = 'ok', gbB = 'ok', calls = [];
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  if (url.includes(MARK)) sentKey++;
  const hd = new Headers(init.headers || {});
  const c = { url, ua: hd.get('user-agent'), accept: hd.get('accept') };
  calls.push(c);
  const hang = () => new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted ' + url), { name: 'AbortError' }))));
  if (url === KDI_URL) {
    c.src = 'kdi';
    const b = kdiB;
    if (typeof b === 'function') return b(init);
    if (b === 'ok') return new Response(KDI_XML, { status: 200, headers: { 'content-type': 'application/xml; charset=utf-8' } });
    if (b === 'blocked') return new Response('<h2 align=center>?????? ??? ????!!!</h2>', { status: 200, headers: { 'content-type': 'text/html' } });
    if (b === 'net') throw new TypeError('fetch failed');
    if (b === 'hang') return hang();
    if (typeof b === 'number') return new Response('no', { status: b });
    if (typeof b === 'string') return new Response(b, { status: 200, headers: { 'content-type': 'application/xml' } });
  }
  if (url.startsWith(GB_URL + '?')) {
    c.src = 'gwanbo';
    const sp = new URL(url).searchParams;
    c.day = sp.get('reqFrom'); c.page = sp.get('pageNo');
    const b = gbB;
    if (typeof b === 'function') return b(sp, init, url);
    if (b === 'ok') return Response.json(gbJson(sp));
    if (b === 'single') return Response.json(gbJson(sp, { single: true }));
    if (b === 'code10') return Response.json(gbJson(sp, { code10: true }));
    if (b === 'net') throw new TypeError('fetch failed: ' + url);           // an error text that carries the URL (and so the key)
    if (b === 'hang') return hang();
    if (b === 'gw30') return new Response(gwXml(30, 'SERVICE_KEY_IS_NOT_REGISTERED_ERROR ' + sp.get('serviceKey')), { status: 401, headers: { 'content-type': 'application/xml' } });
    if (b === 'gw22') return new Response(gwXml(22, 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR'), { status: 200, headers: { 'content-type': 'application/xml' } });
    if (b === 'h429') return new Response('', { status: 429 });
    if (b === 'api303') return Response.json({ response: { resultCode: '303', resultMsg: 'bad param serviceKey=' + sp.get('serviceKey') } });
    if (b === 'notjson') return new Response('{oops', { status: 200 });
    if (b === 'h500') return new Response('error ' + url, { status: 500 });
  }
  throw new Error('unexpected upstream ' + url);
};

const worker = (await import('../../worker/src/index.js')).default;
const P = await import('../../worker/src/policy.js');
let env = { REPLAY: makeKV(), DATA_GO_KR_KEY: KEY };
const waits = [];
const ctx = { waitUntil: p => waits.push(p) };
async function hit(o = {}) {
  if (o.fresh !== false) cacheStore = new Map();
  calls = [];
  const req = new Request('https://panse.pages.dev/api/policy', { method: o.method || 'GET' });
  if (o.colo) Object.defineProperty(req, 'cf', { value: { colo: o.colo } });
  const r = await worker.fetch(req, env, ctx);
  await Promise.all(waits.splice(0));
  const text = await r.text();
  outputs.push(text, JSON.stringify([...r.headers]));
  let body = null; try { body = JSON.parse(text); } catch (e) { /* not json */ }
  return { r, body, text };
}
const reset = () => { env = { REPLAY: makeKV(), DATA_GO_KR_KEY: KEY }; kdiB = 'ok'; gbB = 'ok'; cacheStore = new Map(); };
const gbCalls = () => calls.filter(c => c.src === 'gwanbo');
const kdiCalls = () => calls.filter(c => c.src === 'kdi');
const kvPuts = (k) => env.REPLAY.log.filter(l => l[0] === 'put' && (!k || l[1] === k));

const results = [];
const check = (name, ok, detail = '') => { results.push([name, !!ok]); say((ok ? 'PASS ' : 'FAIL ') + name + (detail !== '' ? `  [${detail}]` : '')); };
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$/, DAY = /^\d{4}-\d{2}-\d{2}$/;

// 1 · Sunday evening: KDI (fixture) + the gazette (today and Saturday empty → back to Fri / Thu)
{
  reset(); at('2026-11-15T08:00:00Z');
  const { r, body } = await hit();
  check('200', r.status === 200, r.status);
  check('cache-control public, s-maxage=600, stale-while-revalidate=600', r.headers.get('cache-control') === 'public, s-maxage=600, stale-while-revalidate=600', r.headers.get('cache-control'));
  check('access-control-allow-origin like the other /api/*', r.headers.get('access-control-allow-origin') === 'https://panse.pages.dev');
  check('content-type json', /application\/json/.test(r.headers.get('content-type')));
  check('asOf KST ISO', ISO.test(body.asOf), body.asOf);
  check('KDI fetched once, honest UA + RSS accept', kdiCalls().length === 1 && kdiCalls()[0].ua === 'PanseNewsBot/1.0 (+https://panse.pages.dev)' && /rss\+xml/.test(kdiCalls()[0].accept));
  check('gazette: honest UA too', gbCalls().length > 0 && gbCalls().every(c => c.ua === 'PanseNewsBot/1.0 (+https://panse.pages.dev)'));
  const g = gbCalls();
  check('gazette query shape: type=1 · pageSize=100 · reqFrom=reqTo (one day) · https portal endpoint', g.every(c => /[?&]type=1(&|$)/.test(c.url) && /[?&]pageSize=100&/.test(c.url) && new URL(c.url).searchParams.get('reqFrom') === new URL(c.url).searchParams.get('reqTo') && c.url.startsWith('https://apis.data.go.kr/1741000/ApiTotalService/getApiTotalList?')));
  check('serviceKey percent-encoded once', g.every(c => c.url.includes('serviceKey=' + KEY_ENC + '&')));
  const days = [...new Set(g.map(c => c.day))];
  check('days read: today (일) → 토 · 금 · 목 (≤ 3 past days a run, nearest first)', days.join() === '20261115,20261114,20261113,20261112', days.join());
  check('금요일 230 rows → pages 1 · 2 · 3', g.filter(c => c.day === '20261113').map(c => c.page).sort().join() === '1,2,3');
  const kd = body.items.filter(x => x.src === 'kdi'), gb = body.items.filter(x => x.src === 'gwanbo');
  check('≤ 30 per source', kd.length === 30 && gb.length === 30, `${kd.length}/${gb.length}`);
  check('sources ok · n · at', body.sources.kdi.ok && body.sources.kdi.n === 30 && ISO.test(body.sources.kdi.at) && body.sources.gwanbo.ok && body.sources.gwanbo.n === 30 && ISO.test(body.sources.gwanbo.at), JSON.stringify(body.sources));
  check('gazette scanned = today\'s rows read (일요일 0)', body.sources.gwanbo.scanned === 0, body.sources.gwanbo.scanned);
  check('item keys ⊆ src · title · url · t · org · kind', body.items.every(x => Object.keys(x).every(k => ['src', 'title', 'url', 't', 'org', 'kind'].includes(k))), JSON.stringify(body.items[0]));
  check('t is a KST date', body.items.every(x => DAY.test(x.t)));
  check('newest day first', body.items.every((x, i, a) => i === 0 || a[i - 1].t >= x.t));
  const d13 = body.items.filter(x => x.t === '2026-11-13').map(x => x.src).slice(0, 6).join();
  check('inside a day the sources take turns (KDI first)', d13 === 'kdi,gwanbo,kdi,gwanbo,kdi,gwanbo', d13);
  check('KDI url = https://eiec.kdi.re.kr/policy/materialView.do?num=N', kd.every(x => /^https:\/\/eiec\.kdi\.re\.kr\/policy\/materialView\.do\?num=\d+$/.test(x.url)));
  const first = kd.find(x => x.url.endsWith('num=289491'));
  check('KDI first item: title · org 재정경제부 · 2026-11-13 (from the description)', first && first.title === '2026년 11월 최근 경제동향' && first.org === '재정경제부' && first.t === '2026-11-13', JSON.stringify(first));
  const fut = kd.find(x => x.url.endsWith('num=289493'));
  check('KDI "’26.11.16.(월)부터" (future) → the date of the item above it', fut && fut.t === '2026-11-13' && fut.org === '고용노동부', JSON.stringify(fut));
  check('KDI two agencies → "과학기술정보통신부 외 1곳"', P.kdiMeta('과학기술정보통신부와 기후에너지환경부는 ’26.11.13.(금) …').org === '과학기술정보통신부 외 1곳');
  check('KDI 정부는 → org 정부', (kd.find(x => x.url.endsWith('num=289508')) || {}).org === '정부');
  check('KDI 한국은행은 → org 한국은행 (은 inside the name)', (kd.find(x => x.url.endsWith('num=289523')) || {}).org === '한국은행');
  check('gazette: only market agencies, never 인사', gb.every(x => IN.test(x.org) && x.kind !== '인사'), [...new Set(gb.map(x => x.org))].join(','));
  check('gazette: org + kind present', gb.every(x => x.org && x.kind));
  check('gazette: newest gazette number first inside a day', (() => { const f = gb.filter(x => x.t === '2026-11-13').map(x => +x.title.match(/-(\d+)\)/)[1]); return f.every((v, i) => i === 0 || f[i - 1] > v); })());
  check('gazette: links on the official site (https gwanbo.go.kr)', gb.every(x => { const u = new URL(x.url); return u.protocol === 'https:' && ['gwanbo.go.kr', 'www.gwanbo.go.kr', 'open.gwanbo.go.kr'].includes(u.hostname); }));
  check('gazette: title entities decoded (&amp; → &)', gb.every(x => !/&amp;/.test(x.title)) && gb.some(x => x.title.includes(' & ')));
  check('no 개정이유 in the answer', !JSON.stringify(body).includes(BODY_MARK));
  check('KV: last copies written (KDI 24 h · 관보 8 days)', kvPuts('policy:last:kdi').some(l => l[2] === 86400) && kvPuts('policy:last:gwanbo').some(l => l[2] === 8 * 86400));
  const snap = JSON.parse(env.REPLAY._m.get('policy:last:gwanbo').v);
  check('snapshot: past days done, today not, call count kept', snap.days['20261113'].done && snap.days['20261112'].done && snap.days['20261114'].done && !snap.days['20261115'].done && snap.calls.d === '20261115' && snap.calls.n === g.length, JSON.stringify(snap.calls));
  check('snapshot holds no 개정이유', !env.REPLAY._m.get('policy:last:gwanbo').v.includes(BODY_MARK));
  // edge cache
  const again = await hit({ fresh: false });
  check('edge cache: a second request calls nothing', calls.length === 0 && again.r.status === 200 && again.body.items.length === body.items.length, calls.length);
  // another data centre (no edge copy) within the freshness window: the KV copies are served, nothing upstream
  at('2026-11-15T08:10:00Z');
  const other = await hit({ colo: 'NRT' });
  check('freshness gate: another data centre 10 min later calls nothing (KV copies)', calls.length === 0 && other.body.items.length === 60 && other.body.sources.gwanbo.ok && other.body.sources.kdi.ok, calls.map(c => c.src).join());
  // nights / weekends: KDI 60 min, 관보 120 min
  at('2026-11-15T08:59:00Z');
  await hit();
  check('일요일: KDI still fresh at 59 min, 관보 too', calls.length === 0, calls.map(c => c.src).join());
  at('2026-11-15T09:01:00Z');
  await hit();
  check('일요일: KDI again after 60 min, 관보 not yet (120 min)', kdiCalls().length === 1 && gbCalls().length === 0, calls.map(c => c.src).join());
  at('2026-11-15T10:01:00Z');
  await hit();
  const g2 = gbCalls();
  check('관보 after 120 min: today only — done days are not read again (금요일 alone fills 30)', [...new Set(g2.map(c => c.day))].join() === '20261115', [...new Set(g2.map(c => c.day))].join());
}

// 2 · day rollover (a day read while it was today is read once more after it ended, when it is needed), weekday windows
{
  reset(); at('2026-11-13T09:00:00Z');                        // 금 18:00 KST
  await hit();
  check('금요일 저녁: today only (3 pages, ≥ 30 rows → no past day)', gbCalls().map(c => c.day + '/' + c.page).sort().join() === '20261113/1,20261113/2,20261113/3', gbCalls().map(c => c.day + '/' + c.page).join());
  at('2026-11-14T00:30:00Z');                                 // 토 09:30 KST
  await hit();
  check('토요일 아침: today (empty) + 금요일 finished once (3 pages) — its known rows fill 30, so no 목 · 수', gbCalls().map(c => c.day + '/' + c.page).sort().join() === '20261113/1,20261113/2,20261113/3,20261114/1', gbCalls().map(c => c.day + '/' + c.page).join());
  at('2026-11-14T03:00:00Z');                                 // 토 12:00 KST (150 min later: weekend window 120)
  await hit();
  check('토요일 낮: today only (금요일 done)', gbCalls().map(c => c.day).join() === '20261114', gbCalls().map(c => c.day).join());
  at('2026-11-16T01:30:00Z');                                 // 월 10:30 KST
  const { body } = await hit();
  const g = gbCalls();
  check('월요일: today read (2 pages), enough rows → no past day', g.length === 2 && g.every(c => c.day === '20261116'), g.map(c => c.day + '/' + c.page).join());
  check('월요일 scanned = 150', body.sources.gwanbo.scanned === 150, body.sources.gwanbo.scanned);
  check('월요일 gazette rows first (2026-11-16)', body.items.filter(x => x.src === 'gwanbo')[0].t === '2026-11-16');
  at('2026-11-16T01:55:00Z');
  await hit();
  check('평일: 관보 fresh for 30 min, KDI for 20 → KDI only at 25 min', kdiCalls().length === 1 && gbCalls().length === 0, calls.map(c => c.src).join());
  at('2026-11-16T02:01:00Z');
  await hit();
  const g3 = gbCalls();
  check('평일 31 min: 관보 today again only (≥ 30 rows: no past day)', g3.length === 2 && g3.every(c => c.day === '20261116'), g3.map(c => c.day + '/' + c.page).join());
}

// 3 · gazette shapes: one item as an object, code 10, pdf links, dates
{
  reset(); at('2026-11-13T03:00:00Z'); gbB = 'single';
  const { body } = await hit();
  check('items.item as a single object → one row a day (금 · 목 · 수)', body.sources.gwanbo.ok && body.items.filter(x => x.src === 'gwanbo').length === 3, body.sources.gwanbo.n);
  reset(); at('2026-11-15T08:00:00Z'); gbB = 'code10';
  const b2 = (await hit()).body;
  check('resultCode 10 (no data) on empty days is not a failure', b2.sources.gwanbo.ok, JSON.stringify(b2.sources.gwanbo));
  // a portal that caps pageSize at 10: the next pages follow its size (230 rows → pages 1..5 of 10 = the 5-page cap)
  reset(); at('2026-11-13T03:00:00Z');
  gbB = (sp) => { const ymd = sp.get('reqFrom'), page = +sp.get('pageNo'), all = gazetteRows(ymd), rows = all.slice((page - 1) * 10, page * 10);
    return Response.json({ response: { resultCode: '00', totalCount: String(all.length), pageSize: '10', pageNo: String(page), items: all.length ? { item: rows } : '' } }); };
  const cap = await hit();
  const fri = gbCalls().filter(c => c.day === '20261113').map(c => +c.page).sort((x, y) => x - y).join();
  check('portal caps pageSize (10): pages follow its size, ≤ 5 pages a day', fri === '1,2,3,4,5' && cap.body.sources.gwanbo.ok, fri);
  check('gbUrl: relative path → https://gwanbo.go.kr/…', P.gbUrl('/ezpdf/a.pdf?x=1') === 'https://gwanbo.go.kr/ezpdf/a.pdf?x=1');
  check('gbUrl: http on the site → https', P.gbUrl('http://www.gwanbo.go.kr/a.pdf') === 'https://www.gwanbo.go.kr/a.pdf');
  check('gbUrl: other host · javascript: · empty → 일자별 관보 page', [P.gbUrl('https://evil.example.com/a.pdf'), P.gbUrl('javascript:alert(1)'), P.gbUrl(''), P.gbUrl(null), P.gbUrl('https://u:p@gwanbo.go.kr/a')].every(u => u === P.GB_FALLBACK_URL));
  check('gbDate: 4 formats', ['2026-11-13', '2026.11.13', '2026. 11. 13.', '20261113'].every(s => P.gbDate(s) === '2026-11-13') && P.gbDate('2026.13.01') === null && P.gbDate('') === null);
  check('gbItem: filter keeps 금융위원회 고시, drops 보건복지부 · 인사 · empty org', !!P.gbItem({ cntntSj: 'a', pblcnInstNm: '금융위원회', cmplatSeNm: '고시' }, '20261113') && !P.gbItem({ cntntSj: 'a', pblcnInstNm: '보건복지부', cmplatSeNm: '고시' }, '20261113')
    && !P.gbItem({ cntntSj: 'a', pblcnInstNm: '재정경제부', cmplatSeNm: '인사' }, '20261113') && !P.gbItem({ cntntSj: 'a', pblcnInstNm: '', cmplatSeNm: '고시' }, '20261113'));
  check('gbItem: no date → the day asked', P.gbItem({ cntntSj: 'a', pblcnInstNm: '한국은행', cmplatSeNm: '공고' }, '20261113').t === '2026-11-13');
}

// 4 · KDI parsing on a crafted feed
{
  const xml = '<?xml version="1.0"?><rss version="2.0"><channel>' + [
    ['﻿  첫 &amp;amp; 자료 &lt;b&gt;굵게&lt;/b&gt;  ', 'https://eiec.kdi.re.kr/policy/materialView.do?num=11', '<![CDATA[금융위원회는 ’26.11.13.(금) DESC-BODY-MARKER 본문]]>'],
    ['http 링크', 'http://eiec.kdi.re.kr/policy/materialView.do?num=12', '한국은행은 2026.11.12. 발표했다'],
    ['다른 도메인', 'https://evil.example.com/policy/materialView.do?num=13', '재정경제부는 ’26.11.13.'],
    ['다른 경로', 'https://eiec.kdi.re.kr/policy/other.do?num=14', '재정경제부는 ’26.11.13.'],
    ['번호 없음', 'https://eiec.kdi.re.kr/policy/materialView.do', '재정경제부는 ’26.11.13.'],
    ['날짜 없는 설명', 'https://eiec.kdi.re.kr/policy/materialView.do?num=15', '보도자료입니다'],
    ['같은 주소', 'https://eiec.kdi.re.kr/policy/materialView.do?num=11', '재정경제부는 ’26.11.13.'],
    ['', 'https://eiec.kdi.re.kr/policy/materialView.do?num=16', '재정경제부는 ’26.11.13.'],
    ['긴 주체', 'https://eiec.kdi.re.kr/policy/materialView.do?num=17', '오늘 아침 일찍 열린 아주 긴 이름의 회의에서 여러 관계자들이 모여 논의한 결과는 ’26.11.11. 발표'],
  ].map(([t, l, d]) => `<item><title>${t}</title><link>${l}</link><description>${d}</description><pubDate></pubDate></item>`).join('') + '</channel></rss>';
  const items = P.parseKdi(xml, Date.parse('2026-11-15T08:00:00Z'));
  check('KDI: dropped other host · other path · no num · duplicate · empty title', items.map(x => x.url.split('=').pop()).join() === '11,12,15,17', items.map(x => x.url.split('=').pop()).join());
  check('KDI: title cleaned (BOM · double entity · tags · spaces)', items[0].title === '첫 & 자료 굵게', items[0].title);
  check('KDI: http link upgraded to https', items[1].url === 'https://eiec.kdi.re.kr/policy/materialView.do?num=12');
  check('KDI: 4-digit year "2026.11.12."', items[1].t === '2026-11-12' && items[1].org === '한국은행', JSON.stringify(items[1]));
  check('KDI: no date → the item above', items[2].t === '2026-11-12' && !items[2].org, JSON.stringify(items[2]));
  check('KDI: a long subject is not an agency', !items[3].org && items[3].t === '2026-11-11', JSON.stringify(items[3]));
  check('KDI: the description never leaves (only org/t)', !JSON.stringify(items).includes('DESC-BODY-MARKER'));
  check('kdiMeta: 3 agencies', P.kdiMeta('해양수산부와 우주항공청, 기후에너지환경부는 ’26.11.13.(금) …').org === '해양수산부 외 2곳');
  check('kdiMeta: typo "’26.11.11..(수)"', P.kdiMeta('농림축산식품부는 ’26.11.11..(수)부터 …').d === '2026-11-11');
  // the whole fixture parses: 100 items, 30 kept, every one with a date and an agency
  const all = P.parseKdi(KDI_XML, Date.parse('2026-11-15T08:00:00Z'));
  check('fixture: 30 items, each with t and org', all.length === 30 && all.every(x => DAY.test(x.t) && x.org), all.filter(x => !x.org).map(x => x.url).join());
}

// 5 · failures, cool-downs, last good copies
{
  reset(); at('2026-11-16T01:30:00Z');
  await hit();                                                  // good copies of both
  at('2026-11-16T02:31:00Z'); kdiB = 403; gbB = 'h500';
  const { r, body } = await hit();
  check('both fail with copies → 200, stale, items still there', r.status === 200 && body.sources.kdi.stale && body.sources.gwanbo.stale && body.items.length === 60, JSON.stringify(body.sources));
  check('a failing source: shorter edge cache (120 s)', r.headers.get('cache-control') === 'public, s-maxage=120, stale-while-revalidate=600', r.headers.get('cache-control'));
  check('errors are plain words: KDI http 403 · 관보 http 500', body.sources.kdi.error === 'http 403' && body.sources.gwanbo.error === 'http 500', `${body.sources.kdi.error} / ${body.sources.gwanbo.error}`);
  check('KDI 403 → rests 15 min (policy:cool:kdi)', kvPuts('policy:cool:kdi').some(l => l[2] === 900));
  check('관보 5xx → rests 5 min', kvPuts('policy:cool:gwanbo').some(l => l[2] === 300));
  check('err notes written (3 days)', kvPuts('policy:err:kdi').some(l => l[2] === 259200) && kvPuts('policy:err:gwanbo').some(l => l[2] === 259200));
  const note = JSON.parse(env.REPLAY._m.get('policy:err:gwanbo').v);
  check('err note shape {at, colo, error, status}', ISO.test(note.at) && note.error === 'http 500' && note.status === 500 && 'colo' in note && !('url' in note), JSON.stringify(note));
  at('2026-11-16T02:33:00Z');
  await hit();
  check('while resting: nothing upstream', calls.length === 0, calls.map(c => c.src).join());
  // err note at most once per 30 min
  at('2026-11-16T02:40:00Z');
  const before = kvPuts('policy:err:gwanbo').length;
  await hit();
  check('err note not rewritten within 30 min', kvPuts('policy:err:gwanbo').length === before);

  // no copies at all → 502 no-store
  reset(); at('2026-11-16T01:30:00Z'); kdiB = 'net'; gbB = 'net';
  const f = await hit();
  check('both fail, no copy → 502 {error, sources}, no-store', f.r.status === 502 && f.r.headers.get('cache-control') === 'no-store' && f.body.error && f.body.sources.kdi.error === 'network' && f.body.sources.gwanbo.error === 'network', f.text.slice(0, 160));
  check('502 is not edge-cached', !cacheStore.size);

  reset(); kdiB = 'blocked';
  const bl = await hit();
  check('KDI "정상적인 접근이 아닙니다" page → not rss, rests 30 min', bl.body.sources.kdi.error === 'not rss' && kvPuts('policy:cool:kdi').some(l => l[2] === 1800), bl.body.sources.kdi.error);
  check('one source down, the other fine → 200 with the other', bl.r.status === 200 && bl.body.items.every(x => x.src === 'gwanbo') && bl.body.items.length === 30);

  reset(); gbB = 'gw30';
  const k30 = await hit();
  check('portal 401 + XML code 30 (key not registered) → "http 401 gw 30", rests 30 min', k30.body.sources.gwanbo.error === 'http 401 gw 30' && kvPuts('policy:cool:gwanbo').some(l => l[2] === 1800), k30.body.sources.gwanbo.error);
  reset(); gbB = 'gw22';
  const k22 = await hit();
  check('XML code 22 (daily limit) → "gw 22", rests 60 min', k22.body.sources.gwanbo.error === 'gw 22' && kvPuts('policy:cool:gwanbo').some(l => l[2] === 3600), k22.body.sources.gwanbo.error);
  reset(); gbB = 'h429';
  const k429 = await hit();
  check('HTTP 429 → rests 60 min', k429.body.sources.gwanbo.error === 'http 429' && kvPuts('policy:cool:gwanbo').some(l => l[2] === 3600));
  reset(); gbB = 'api303';
  const a303 = await hit();
  check('resultCode 303 → "api 303" (upstream message dropped)', a303.body.sources.gwanbo.error === 'api 303', a303.body.sources.gwanbo.error);
  reset(); gbB = 'notjson';
  check('broken JSON → "not json"', (await hit()).body.sources.gwanbo.error === 'not json');

  reset(); delete env.DATA_GO_KR_KEY;
  const nk = await hit();
  check('no key → gazette {ok:false, error:"no key"}, no portal call, KDI still served', nk.r.status === 200 && nk.body.sources.gwanbo.error === 'no key' && !gbCalls().length && nk.body.items.length === 30, JSON.stringify(nk.body.sources.gwanbo));

  // budget: the day's call count in the snapshot
  reset(); at('2026-11-16T01:30:00Z');
  await hit();
  const s = JSON.parse(env.REPLAY._m.get('policy:last:gwanbo').v);
  s.calls.n = P.POLICY.GB_DAY_MAX; s.at = '2026-11-16T09:00:00+09:00';
  env.REPLAY._m.set('policy:last:gwanbo', { v: JSON.stringify(s), exp: null });
  at('2026-11-16T03:00:00Z');
  const bu = await hit();
  check(`daily cap (${P.POLICY.GB_DAY_MAX} calls) → "budget", no portal call, the copy as stale`, bu.body.sources.gwanbo.error === 'budget' && bu.body.sources.gwanbo.stale && !gbCalls().length, JSON.stringify(bu.body.sources.gwanbo));
  at('2026-11-17T01:30:00Z');
  await hit();
  check('the cap resets with the KST day', gbCalls().length > 0);

  // timeouts: 6 s per call, no retry
  reset(); at('2026-11-16T01:30:00Z'); kdiB = 'hang';
  const t0 = realNow();
  const hg = await hit();
  const took = realNow() - t0;
  check('KDI hangs → "timeout" after ~6 s, no retry', hg.body.sources.kdi.error === 'timeout' && took >= 5800 && took < 8000 && kdiCalls().length === 1, `${took} ms`);
}

// 6 · the key never leaks
{
  // encodings
  reset(); env.DATA_GO_KR_KEY = KEY_ENC;
  await hit();
  check('an already-encoded key goes as it is (no %25…)', gbCalls().every(c => c.url.includes('serviceKey=' + KEY_ENC + '&') && !c.url.includes('%25')));
  reset(); env.DATA_GO_KR_KEY = '  ' + KEY + '\n';
  await hit();
  check('key trimmed', gbCalls().every(c => c.url.includes('serviceKey=' + KEY_ENC + '&')));
  // an upstream that echoes the key in its error body / message, and a fetch error whose text carries the URL
  for (const b of ['gw30', 'api303', 'h500', 'net']) { reset(); gbB = b; at('2026-11-16T05:00:00Z'); await hit(); }
  // a crash inside the route never prints the exception
  reset(); env.REPLAY = { get() { throw new Error('kv down ' + KEY); }, put() { throw new Error('kv down ' + KEY); } };
  const crash = await hit();
  check('KV that throws: still answers (KV is optional)', crash.r.status === 200, crash.r.status);
  const leaks = outputs.filter(s => s.includes(MARK) || s.includes(KEY_ENC));
  check(`key never in a response, header, KV value or console line (${outputs.length} outputs checked)`, leaks.length === 0, leaks[0] && leaks[0].slice(0, 120).replace(MARK, '[KEY]'));
  check('…and it really went to the portal (the check is not vacuous)', sentKey > 0, sentKey);
  const bodies = outputs.join('\n');
  check('no URL of the portal in any output', !bodies.includes('apis.data.go.kr'));
  check('no 개정이유 text in any output', !bodies.includes(BODY_MARK));
}

// 7 · the router
{
  reset();
  const h = await worker.fetch(new Request('https://panse.pages.dev/api/health'), env, ctx);
  check('/api/health untouched', h.status === 200 && (await h.json()).ok === true);
  const post = await hit({ method: 'POST' });
  check('POST /api/policy → 405', post.r.status === 405);
  const m = P.mergeItems([{ src: 'kdi', title: 'a', url: 'u1', t: '2026-11-13' }, { src: 'kdi', title: 'b', url: 'u2', t: '2026-11-13' }, { src: 'kdi', title: 'c', url: 'u3', t: '2026-11-12' }],
    [{ src: 'gwanbo', title: 'x', url: 'g', t: '2026-11-14' }, { src: 'gwanbo', title: 'y', url: 'g', t: '2026-11-13' }]);
  check('mergeItems: day order + turns + same fallback url kept for different titles', m.map(x => x.title).join('') === 'xaybc', m.map(x => x.title).join(''));
}

const bad = results.filter(r => !r[1]);
console.log(`\n${results.length - bad.length}/${results.length} passed`);
for (const [n] of bad) console.log('  FAIL', n);
process.exit(bad.length ? 1 : 0);
