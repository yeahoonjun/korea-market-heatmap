// Worker /api/news unit checks (docs/standards/news.md §2-2 · §2-3) — no network: the outlets are stubbed with the
// sanitized fixtures in qa/news/fixtures (title · link · pubDate only, as the outlets wrote them on 2026-11-13).
//   node qa/news/worker_test.mjs            exit 1 on any failure
// §7 (relay, news.md §2-6): a fake MARKET binding hands the Worker's stub calls to REAL MarketHub instances (fake DO state);
// an AsyncLocalStorage tag tells the fetch stub whether a call was made inside the relay instance or by the Worker itself.
import { readFileSync } from 'node:fs';
import { AsyncLocalStorage } from 'node:async_hooks';

const HERE = new URL('.', import.meta.url);
const FIX = k => readFileSync(new URL(`fixtures/${k}.xml`, HERE), 'utf8');
const URLS = {
  einfomax: 'https://news.einfomax.co.kr/rss/allArticle.xml',
  hankyung: 'https://www.hankyung.com/feed/finance',
  mk: 'https://www.mk.co.kr/rss/50200011/',
};
const HOSTS = { einfomax: 'news.einfomax.co.kr', hankyung: 'www.hankyung.com', mk: 'www.mk.co.kr' };

// ── stubs: caches.default (honours s-maxage / max-age), KV (TTL + op log), fetch (per-outlet behaviour) ──
let cacheStore = new Map();
globalThis.caches = { default: {
  async match(req) { const e = cacheStore.get(req.url); if (!e || Date.now() > e.exp) return undefined; return e.res.clone(); },
  async put(req, res) { const cc = res.headers.get('cache-control') || ''; const m = /s-maxage=(\d+)/.exec(cc) || /max-age=(\d+)/.exec(cc); if (m) cacheStore.set(req.url, { exp: Date.now() + m[1] * 1000, res: res.clone() }); },
} };
function makeKV() {
  const m = new Map(), log = [];
  return { _m: m, log,
    async get(k, type) { log.push(['get', k]); const e = m.get(k); if (!e || (e.exp && e.exp < Date.now())) return null; return type === 'json' ? JSON.parse(e.v) : e.v; },
    async put(k, v, o) { log.push(['put', k, o && o.expirationTtl]); m.set(k, { v: String(v), exp: o && o.expirationTtl ? Date.now() + o.expirationTtl * 1000 : null }); },
  };
}
let behave = {}, calls = [];
const als = new AsyncLocalStorage();                 // 'relay' inside the relay instance, undefined for the Worker's own fetches
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  const key = Object.keys(URLS).find(k => URLS[k] === url);
  if (!key) throw new Error('unexpected upstream ' + url);
  const hd = new Headers(init.headers || {});
  const where = als.getStore() || 'direct';
  calls.push({ key, ua: hd.get('user-agent'), accept: hd.get('accept'), where });
  const b = behave[key + '@' + where] ?? behave[key] ?? 'ok';
  // 매일경제 sits behind Cloudflare: its cf-ray names the data centre the request came through (relay IAD, Worker ICN)
  const h = t => ({ 'content-type': t, ...(key === 'mk' ? { 'cf-ray': '8e0f1a2b3c4d5e6f-' + (where === 'relay' ? 'IAD' : 'ICN') } : {}) });
  if (typeof b === 'function') return b(init);
  if (b === 'ok') return new Response(FIX(key), { status: 200, headers: h('application/xml') });
  if (b === 'net') throw new TypeError('fetch failed');
  if (b === 'hang') return new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
  if (b === 'html') return new Response('<!doctype html><title>blocked</title>', { status: 200, headers: h('text/html') });
  if (typeof b === 'number') return new Response('no', { status: b, headers: h('text/plain') });
  if (typeof b === 'string') return new Response(b, { status: 200, headers: h('application/xml') });
  throw new Error('bad behaviour');
};

const worker = (await import('../../worker/src/index.js')).default;
const { MarketHub, RELAY_DAY_MAX, RELAY_NAME } = await import('../../worker/src/live.js');
const { LIMITS } = await import('../../worker/src/live_core.js');
let env = { REPLAY: makeKV() };
const waits = [];
const ctx = { waitUntil: p => waits.push(p) };
async function hit(fresh = true, colo = null) {
  if (fresh) cacheStore = new Map();
  calls = [];
  const req = new Request('https://panse.pages.dev/api/news');
  if (colo) Object.defineProperty(req, 'cf', { value: { colo } });
  const r = await worker.fetch(req, env, ctx);
  await Promise.all(waits.splice(0));
  const body = await r.json();
  return { r, body };
}

const results = [];
const check = (name, ok, detail = '') => { results.push([name, !!ok]); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? `  [${detail}]` : '')); };
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$/;
const INVIS = /[﻿​-‍⁠]/;

// 1 · all three answer
{
  behave = {};
  const { r, body } = await hit();
  check('all ok → 200', r.status === 200, r.status);
  check('cache-control = public, s-maxage=180, stale-while-revalidate=120', r.headers.get('cache-control') === 'public, s-maxage=180, stale-while-revalidate=120', r.headers.get('cache-control'));
  check('access-control-allow-origin like the other /api/*', r.headers.get('access-control-allow-origin') === 'https://panse.pages.dev');
  check('content-type json', /application\/json/.test(r.headers.get('content-type')));
  check('one request per outlet', calls.length === 3 && new Set(calls.map(c => c.key)).size === 3, calls.map(c => c.key).join());
  check('honest User-Agent (not a browser)', calls.every(c => c.ua === 'PanseNewsBot/1.0 (+https://panse.pages.dev)'), calls[0] && calls[0].ua);
  check('accept header', calls.every(c => c.accept === 'application/rss+xml, application/xml;q=0.9, */*;q=0.5'));
  check('asOf KST ISO', ISO.test(body.asOf), body.asOf);
  const per = k => body.items.filter(x => x.src === k).length;
  check('≤ 30 per outlet', ['einfomax', 'hankyung', 'mk'].every(k => per(k) > 0 && per(k) <= 30), ['einfomax', 'hankyung', 'mk'].map(per).join('/'));
  check('sources ok + n + at', ['einfomax', 'hankyung', 'mk'].every(k => body.sources[k].ok === true && body.sources[k].n === per(k) && ISO.test(body.sources[k].at) && !('error' in body.sources[k])), JSON.stringify(body.sources));
  check('item keys are exactly src · title · url · t (no body, description, image, author)', body.items.every(x => Object.keys(x).sort().join() === 'src,t,title,url'));
  check('t is KST ISO', body.items.every(x => ISO.test(x.t)));
  check('sorted newest first', body.items.every((x, i, a) => i === 0 || a[i - 1].t >= x.t));
  check('urls unique', new Set(body.items.map(x => x.url)).size === body.items.length);
  check('urls https on the outlet host', body.items.every(x => { const u = new URL(x.url); return u.protocol === 'https:' && u.hostname === HOSTS[x.src]; }));
  check('titles: no invisible characters, no entities, ≤ 200, trimmed', body.items.every(x => !INVIS.test(x.title) && !/&(?:quot|amp|lt|gt|#\d+);/.test(x.title) && [...x.title].length <= 200 && x.title === x.title.trim() && !/\s{2}/.test(x.title)));
  const gold = body.items.find(x => x.url.endsWith('idxno=4444733'));
  check('연합인포맥스 double-escaped title decoded', gold && gold.title === '골드만 "내년 말 S&P 500지수 8,700 전망…하이퍼스케일러 투자 매력적"', gold && gold.title);
  check('연합인포맥스 zone-less pubDate read as KST', gold && gold.t === '2026-11-13T22:03:19+09:00', gold && gold.t);
  const hk = body.items.find(x => x.url === 'https://www.hankyung.com/article/2026111347546');
  check('한국경제 CDATA title with "]]" kept', hk && hk.title.endsWith('[분석+]'), hk && hk.title);
  check('한국경제 +0900 pubDate', hk && hk.t === '2026-11-13T22:00:04+09:00', hk && hk.t);
  const mk = body.items.find(x => x.url === 'https://www.mk.co.kr/news/stock/12208451');
  check('매일경제 +09:00 pubDate', mk && mk.t === '2026-11-13T22:36:44+09:00', mk && mk.t);
  const bomFix = FIX('hankyung').includes('﻿');
  check('fixture really carries a BOM title (and it is gone)', bomFix && body.items.filter(x => x.src === 'hankyung').every(x => !x.title.startsWith('﻿')));
  // edge cache: a second hit within 180 s fetches nothing
  const again = await hit(false);
  check('edge cache: second request makes no upstream call', calls.length === 0 && again.r.status === 200 && again.body.items.length === body.items.length, calls.length);
  check('last good copy written per outlet (KV news:last:<src>, 6 h)', ['einfomax', 'hankyung', 'mk'].every(k => env.REPLAY.log.some(l => l[0] === 'put' && l[1] === 'news:last:' + k && l[2] === 21600)));
  const puts = env.REPLAY.log.filter(l => l[0] === 'put').length;
  await hit();
  check('unchanged lists are not rewritten (KV writes stay rare)', env.REPLAY.log.filter(l => l[0] === 'put').length === puts);
}

// 2 · title cleaning, url filter, date parsing on a crafted feed
{
  const long = '가'.repeat(250);
  const items = [
    ['<![CDATA[﻿  삼성전자,​ 신고가 \n  경신 ]]>', 'https://www.mk.co.kr/news/stock/1', 'Fri, 13 Nov 2026 22:36:44 +09:00'],
    ['&lt;b&gt;굵은&lt;/b&gt; 글자 &amp;amp; 엔티티 &#8230; &#x2026; &middot;', 'https://www.mk.co.kr/news/stock/2', 'Fri, 13 Nov 2026 13:36:44 GMT'],
    ['<![CDATA[<속보> 코스피 &quot;하락&quot; <em>마감</em>]]>', 'https://www.mk.co.kr/news/stock/3', 'Fri, 13 Nov 2026 22:36:44 KST'],
    [long, 'https://www.mk.co.kr/news/stock/4', '13 Nov 26 22:36 +0900'],
    ['http 링크', 'http://www.mk.co.kr/news/stock/5', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['다른 도메인', 'https://evil.example.com/www.mk.co.kr', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['하위 도메인', 'https://m.mk.co.kr/news/stock/7', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['자바스크립트', 'javascript:alert(1)', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['상대 주소', '/news/stock/9', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['계정 붙은 주소', 'https://user:pw@www.mk.co.kr/news/stock/10', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['날짜 없음', 'https://www.mk.co.kr/news/stock/11', ''],
    ['날짜 엉망', 'https://www.mk.co.kr/news/stock/12', '어제 저녁'],
    ['먼 미래', 'https://www.mk.co.kr/news/stock/13', 'Fri, 13 Nov 2099 22:36:44 +0900'],
    ['ISO Z', 'https://www.mk.co.kr/news/stock/14', '2026-11-13T12:00:00Z'],
    ['', 'https://www.mk.co.kr/news/stock/15', 'Fri, 13 Nov 2026 22:36:44 +0900'],
    ['같은 주소 두 번', 'https://www.mk.co.kr/news/stock/1', 'Fri, 13 Nov 2026 23:00:00 +0900'],
    ['EST 시각', 'https://www.mk.co.kr/news/stock/16#frag', 'Fri, 13 Nov 2026 08:00:00 EST'],
  ];
  const xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>' + items.map(([t, l, d]) => `<item><title>${t}</title><link>${l}</link><pubDate>${d}</pubDate><description>본문 요약은 내보내지 않아요</description></item>`).join('') + '</channel></rss>';
  behave = { mk: xml, einfomax: 500, hankyung: 500 };
  env = { REPLAY: makeKV() };
  const { r, body } = await hit();
  const by = u => body.items.find(x => x.url === 'https://www.mk.co.kr/news/stock/' + u);
  check('crafted feed → 200 (one outlet ok)', r.status === 200, r.status);
  check('BOM · zero-width · spaces cleaned', by(1) && by(1).title === '삼성전자, 신고가 경신', by(1) && JSON.stringify(by(1).title));
  check('escaped tags → text only, entities decoded', by(2) && by(2).title === '굵은 글자 & 엔티티 … … ·', by(2) && by(2).title);
  check('<속보> kept, real tags dropped, &quot; decoded', by(3) && by(3).title === '<속보> 코스피 "하락" 마감', by(3) && by(3).title);
  check('200-character cut', by(4) && [...by(4).title].length === 200, by(4) && [...by(4).title].length);
  check('http · other host · subdomain · javascript: · relative · credentials dropped', [5, 6, 7, 8, 9, 10].every(n => !body.items.some(x => x.title === items[n - 1][0])) && !body.items.some(x => /evil|m\.mk|user/.test(x.url)));
  check('missing / unreadable / far-future dates dropped', !by(11) && !by(12) && !by(13));
  check('empty title dropped', !by(15));
  check('duplicate url kept once (first)', body.items.filter(x => x.url.endsWith('/stock/1')).length === 1);
  check('GMT → KST', by(2) && by(2).t === '2026-11-13T22:36:44+09:00', by(2) && by(2).t);
  check('KST zone name', by(3) && by(3).t === '2026-11-13T22:36:44+09:00', by(3) && by(3).t);
  check('2-digit year, no seconds, +0900', by(4) && by(4).t === '2026-11-13T22:36:00+09:00', by(4) && by(4).t);
  check('ISO Z → KST', by(14) && by(14).t === '2026-11-13T21:00:00+09:00', by(14) && by(14).t);
  check('EST → KST, #fragment dropped from url', by(16) && by(16).t === '2026-11-13T22:00:00+09:00', by(16) && by(16).t);
  check('no description leaks', !JSON.stringify(body).includes('본문 요약'));
  check('failing outlets flagged', body.sources.einfomax.ok === false && body.sources.einfomax.error === 'http 500' && body.sources.einfomax.n === 0 && body.sources.einfomax.at === null);
  check('500 starts no cool-down', !env.REPLAY.log.some(l => l[0] === 'put' && l[1].startsWith('news:cool:')));
}

// 3 · cool-down on 403 / 429, no retry in the same request
{
  env = { REPLAY: makeKV() };
  behave = { einfomax: 403, hankyung: 429, mk: 'ok' };
  const a = await hit();
  check('one outlet ok, two blocked → 200', a.r.status === 200 && a.body.sources.mk.ok && a.body.items.every(x => x.src === 'mk'));
  check('no retry in the same request', a.body && calls.filter(c => c.key === 'einfomax').length === 1 && calls.filter(c => c.key === 'hankyung').length === 1, calls.map(c => c.key).join());
  check('403 → news:cool:einfomax 15 min', env.REPLAY.log.some(l => l[0] === 'put' && l[1] === 'news:cool:einfomax' && l[2] === 900));
  check('429 → news:cool:hankyung 15 min', env.REPLAY.log.some(l => l[0] === 'put' && l[1] === 'news:cool:hankyung' && l[2] === 900));
  check('blocked outlets flagged http 403 / 429', a.body.sources.einfomax.error === 'http 403' && a.body.sources.hankyung.error === 'http 429');
  behave = {};                                   // they would answer now — but they are resting
  const b = await hit();
  check('cooling outlets are not fetched (cache expired)', calls.length === 1 && calls[0].key === 'mk', calls.map(c => c.key).join());
  check('cooling flagged as cool-down', b.body.sources.einfomax.error === 'cool-down' && b.body.sources.hankyung.error === 'cool-down');
  for (const k of ['news:cool:einfomax', 'news:cool:hankyung']) env.REPLAY._m.get(k).exp = Date.now() - 1;   // 15 min later
  const c = await hit();
  check('after the cool-down they are fetched again', calls.length === 3 && c.body.sources.einfomax.ok && c.body.sources.hankyung.ok);
}

// 4 · one outlet fails → stale copy rides along; all fail → 502 (or 200 stale when copies exist)
{
  env = { REPLAY: makeKV() };
  behave = {};
  const good = await hit();
  const einN = good.body.sources.einfomax.n, einAt = good.body.sources.einfomax.at;
  behave = { einfomax: 'net', hankyung: 'ok', mk: 'ok' };
  const a = await hit();
  check('one outlet down → 200', a.r.status === 200);
  check('its last good copy rides along (stale, n, at of that copy)', a.body.sources.einfomax.ok === false && a.body.sources.einfomax.stale === true && a.body.sources.einfomax.n === einN && a.body.sources.einfomax.at === einAt && a.body.sources.einfomax.error === 'network', JSON.stringify(a.body.sources.einfomax));
  check('stale items included', a.body.items.filter(x => x.src === 'einfomax').length === einN);
  behave = { einfomax: 'html', hankyung: 'ok', mk: 'ok' };
  const h = await hit();
  check('an HTML page instead of RSS is a failure (not rss)', h.body.sources.einfomax.ok === false && h.body.sources.einfomax.error === 'not rss');
  behave = { einfomax: 503, hankyung: 'net', mk: 'html' };
  const b = await hit();
  check('all fail but copies exist → 200 with every source stale', b.r.status === 200 && ['einfomax', 'hankyung', 'mk'].every(k => b.body.sources[k].stale && !b.body.sources[k].ok));
  env = { REPLAY: makeKV() };
  const c = await hit();
  check('all fail, no copies → 502', c.r.status === 502, c.r.status);
  check('502 body = {error, sources}', typeof c.body.error === 'string' && c.body.sources && Object.keys(c.body.sources).length === 3 && !('items' in c.body));
  check('502 is not cached', c.r.headers.get('cache-control') === 'no-store' && cacheStore.size === 0);
  check('502 keeps CORS header', c.r.headers.get('access-control-allow-origin') === 'https://panse.pages.dev');
  env = {};                                      // no KV binding at all: still works
  behave = { einfomax: 'net' };
  const d = await hit();
  check('no KV binding → still 200, failing outlet without copy', d.r.status === 200 && d.body.sources.einfomax.ok === false && !d.body.sources.einfomax.stale);
}

// 5 · timeout: 6 s per outlet, the others are not held back
{
  env = { REPLAY: makeKV() };
  behave = { einfomax: 'hang' };
  const t0 = Date.now();
  const a = await hit();
  const dt = Date.now() - t0;
  check('hanging outlet → timeout after ~6 s', a.r.status === 200 && a.body.sources.einfomax.error === 'timeout' && dt >= 5900 && dt < 8000, dt + ' ms');
}

// 6 · other routes untouched
{
  const r = await worker.fetch(new Request('https://panse.pages.dev/api/health'), {}, ctx);
  check('/api/health still answers', r.status === 200);
}

// 7 · 매일경제 through the relay (news.md §2-6): a separate MarketHub instance 'news-relay' (locationHint enam)
function fakeState(name) {
  const store = new Map(), log = [];
  const st = { id: { name }, log, store, sockets: [],
    storage: {
      async get(k) { log.push(['get', k]); return store.has(k) ? JSON.parse(JSON.stringify(store.get(k))) : undefined; },
      async put(k, v) { log.push(['put', k]); store.set(k, JSON.parse(JSON.stringify(v))); },
      async getAlarm() { log.push(['getAlarm']); return null; }, async setAlarm() { log.push(['setAlarm']); }, async deleteAlarm() { log.push(['deleteAlarm']); },
    },
    acceptWebSocket(ws) { log.push(['acceptWebSocket']); st.sockets.push(ws); }, getWebSockets() { return st.sockets; },
    setWebSocketAutoResponse() { }, blockConcurrencyWhile(fn) { st.ready = fn(); return st.ready; },
  };
  return st;
}
function fakeMarket() {
  const M = { hubs: {}, gets: [], doCalls: [], mode: 'ok',
    async inst(name) { if (!M.hubs[name]) { M.hubs[name] = new MarketHub(fakeState(name), {}); } await M.hubs[name].state.ready; return M.hubs[name]; },
    idFromName(name) { return { name }; },
    get(id, opts) {
      M.gets.push({ name: id.name, hint: opts && opts.locationHint });
      return { async fetch(req) {
        const u = new URL(req.url); M.doCalls.push({ name: id.name, path: u.pathname + u.search });
        if (M.mode === 'throw') throw new Error('Durable Object unavailable');
        if (M.mode === 'hang') return new Promise(() => { });
        const h = await M.inst(id.name);
        return als.run('relay', () => h.fetch(req));
      } };
    },
  };
  return M;
}
const mkCalls = () => calls.filter(c => c.key === 'mk');
const kvPuts = (kv, k) => kv.log.filter(l => l[0] === 'put' && l[1] === k);
const errRec = (kv, k) => { const e = kv._m.get('news:err:' + k); return e ? JSON.parse(e.v) : null; };
const ageKey = (kv, k, ms) => { const e = kv._m.get(k); const j = JSON.parse(e.v); j.at = new Date(Date.parse(j.at) - ms + 9 * 3600e3).toISOString().slice(0, 19) + '+09:00'; e.v = JSON.stringify(j); };
const gateUrl = 'https://panse.pages.dev/__cache/news-relay-gate';
const dropNewsCache = () => cacheStore.delete('https://panse.pages.dev/__cache/news-v1');
{
  const M = fakeMarket();
  const top = await M.inst('top');                                    // the realtime hub, as it exists on the account
  const topLog0 = top.state.log.length, topG0 = JSON.stringify(top.g), topStats0 = JSON.stringify({ ...top.stats, startedAt: 0 });
  env = { REPLAY: makeKV(), MARKET: M };
  behave = {};
  // a · relay path
  const a = await hit(true, 'ICN');
  const relay = M.hubs[RELAY_NAME];
  check('relay outlet: the Worker asks the DO stub "news-relay" with locationHint enam (never "top")', M.gets.length === 1 && M.gets[0].name === 'news-relay' && M.gets[0].hint === 'enam' && !M.gets.some(g => g.name === 'top'), JSON.stringify(M.gets));
  check('one internal call: GET /__relay/news?src=mk (an outlet key, not a URL)', M.doCalls.length === 1 && M.doCalls[0].path === '/__relay/news?src=mk', JSON.stringify(M.doCalls));
  check('매일경제 fetched once, from inside the relay, with the honest UA / accept', mkCalls().length === 1 && mkCalls()[0].where === 'relay' && mkCalls()[0].ua === 'PanseNewsBot/1.0 (+https://panse.pages.dev)' && mkCalls()[0].accept === 'application/rss+xml, application/xml;q=0.9, */*;q=0.5', JSON.stringify(mkCalls()));
  check('non-relay outlets untouched: fetched directly by the Worker, once each', ['einfomax', 'hankyung'].every(k => calls.filter(c => c.key === k).length === 1 && calls.find(c => c.key === k).where === 'direct'));
  check('relay answer → 200, sources.mk {ok, n:30, via:"relay"}, others without via', a.r.status === 200 && a.body.sources.mk.ok && a.body.sources.mk.n === 30 && a.body.sources.mk.via === 'relay' && !('via' in a.body.sources.einfomax) && !('via' in a.body.sources.hankyung), JSON.stringify(a.body.sources));
  check('relay items keep the public shape (src · title · url · t only)', a.body.items.filter(x => x.src === 'mk').length === 30 && a.body.items.every(x => Object.keys(x).sort().join() === 'src,t,title,url'));
  const lastMk = JSON.parse(env.REPLAY._m.get('news:last:mk').v);
  check('last good copy says how it came: via relay, egress IAD (the outlet CDN saw eastern US)', lastMk.via === 'relay' && lastMk.egress === 'IAD', JSON.stringify({ via: lastMk.via, egress: lastMk.egress }));
  check('a good relay fetch leaves no news:err record', !env.REPLAY.log.some(l => l[0] === 'put' && l[1].startsWith('news:err:')));
  check('relay instance: own counter key "relay" only — no guard write, no alarm, no socket', relay.state.store.has('relay') && relay.state.store.get('relay').n === 1 && !relay.state.log.some(l => (l[0] === 'put' && l[1] === 'guard') || /Alarm|acceptWebSocket/.test(l[0])) && relay.state.sockets.length === 0, JSON.stringify(relay.state.log));
  check('relay instance budget guard not charged (dU 0, dConn 0)', relay.g.dU === 0 && relay.g.dConn === 0 && relay.g.dAwake === 0);
  // b · a copy younger than the edge-cache TTL is served without a DO call
  const b = await hit(true, 'NRT');
  check('fresh last copy (< 180 s): no DO call, no upstream fetch for 매일경제', M.doCalls.length === 1 && mkCalls().length === 0, `doCalls ${M.doCalls.length}, mk ${mkCalls().length}`);
  check('… and it is served as ok via relay with its own time', b.body.sources.mk.ok && b.body.sources.mk.via === 'relay' && b.body.sources.mk.n === 30 && b.body.sources.mk.at === lastMk.at);
  // c · older copy → DO again; the relay reuses its answer for 60 s (several data centres at once)
  ageKey(env.REPLAY, 'news:last:mk', 200e3);
  const c = await hit(true, 'ICN');
  check('copy older than 180 s → relay called again', M.doCalls.length === 2 && c.body.sources.mk.ok && c.body.sources.mk.via === 'relay', M.doCalls.length);
  check('relay memo (60 s): the second call reaches the outlet 0 times', mkCalls().length === 0 && relay.state.store.get('relay').n === 2, `mk ${mkCalls().length}`);
  // the hub stays exactly as it was
  check('realtime hub "top" untouched: no storage op, same guard, same stats', top.state.log.length === topLog0 && JSON.stringify(top.g) === topG0 && JSON.stringify({ ...top.stats, startedAt: 0 }) === topStats0 && top.state.sockets.length === 0, `log ${topLog0} → ${top.state.log.length}`);
  check('hub budget counters still zero (DO requests today 0)', top.g.dU === 0 && top.g.mU === 0 && top.status(Date.now()).guard.doRequests.today === 0);
}
{
  // d · the relay itself fails → direct from this data centre; diagnostics note it
  const M = fakeMarket(); M.mode = 'throw';
  env = { REPLAY: makeKV(), MARKET: M };
  behave = {};
  const d = await hit(true, 'ICN');
  check('relay unreachable → 매일경제 fetched directly once, still ok (no via)', mkCalls().length === 1 && mkCalls()[0].where === 'direct' && d.body.sources.mk.ok && !('via' in d.body.sources.mk), JSON.stringify(d.body.sources.mk));
  const e1 = errRec(env.REPLAY, 'mk');
  check('news:err:mk {at, colo ICN, path relay, error "relay unreachable", fallback "direct ok"}, 3-day TTL', e1 && ISO.test(e1.at) && e1.colo === 'ICN' && e1.path === 'relay' && e1.error === 'relay unreachable' && e1.fallback === 'direct ok' && kvPuts(env.REPLAY, 'news:err:mk')[0][2] === 259200, JSON.stringify(e1));
  const lastD = JSON.parse(env.REPLAY._m.get('news:last:mk').v);
  check('last copy from the fallback says via direct, egress ICN', lastD.via === 'direct' && lastD.egress === 'ICN');
  // e · the outlet fails AT the relay (5xx) → direct
  const M2 = fakeMarket();
  env = { REPLAY: makeKV(), MARKET: M2 };
  behave = { 'mk@relay': 500 };
  const e = await hit(true, 'ICN');
  check('relay saw http 500 → then one direct fetch (relay first)', mkCalls().map(c => c.where).join() === 'relay,direct' && e.body.sources.mk.ok, mkCalls().map(c => c.where).join());
  const e2 = errRec(env.REPLAY, 'mk');
  check('… noted with status 500 and the relay egress IAD', e2 && e2.path === 'relay' && e2.error === 'http 500' && e2.status === 500 && e2.egress === 'IAD' && e2.fallback === 'direct ok', JSON.stringify(e2));
  check('a 500 at the relay starts no cool-down', !env.REPLAY.log.some(l => l[0] === 'put' && l[1] === 'news:cool:mk'));
  // f · relay and direct both fail → the last good copy
  behave = {};
  await hit(true, 'ICN');                                             // a good copy exists now (via relay, memo aside)
  ageKey(env.REPLAY, 'news:last:mk', 200e3);
  M2.hubs[RELAY_NAME].relayMemo = null;
  const kvF = env.REPLAY;
  kvF._m.delete('news:err:mk');
  behave = { 'mk@relay': 'net', 'mk@direct': 503 };
  const f = await hit(true, 'ICN');
  check('fallback order relay → direct → last copy', mkCalls().map(c => c.where).join() === 'relay,direct' && f.body.sources.mk.ok === false && f.body.sources.mk.stale === true && f.body.sources.mk.n === 30 && f.body.sources.mk.error === 'http 503' && !('via' in f.body.sources.mk), JSON.stringify(f.body.sources.mk));
  const e3 = errRec(kvF, 'mk');
  check('both failed: news:err:mk path direct (http 503) + relay {error network}', e3 && e3.path === 'direct' && e3.error === 'http 503' && e3.status === 503 && e3.relay && e3.relay.error === 'network' && e3.colo === 'ICN', JSON.stringify(e3));
}
{
  // g · 403 at the relay: the outlet rests 15 min, and is NOT tried from the local data centre (no working around a block)
  const M = fakeMarket();
  env = { REPLAY: makeKV(), MARKET: M };
  behave = { 'mk@relay': 403 };
  const g = await hit(true, 'ICN');
  check('relay saw 403 → no direct try, news:cool:mk 15 min', mkCalls().map(c => c.where).join() === 'relay' && kvPuts(env.REPLAY, 'news:cool:mk').length === 1 && kvPuts(env.REPLAY, 'news:cool:mk')[0][2] === 900 && g.body.sources.mk.error === 'http 403', mkCalls().map(c => c.where).join());
  const g1 = errRec(env.REPLAY, 'mk');
  check('… noted: path relay, status 403, egress IAD', g1 && g1.path === 'relay' && g1.status === 403 && g1.egress === 'IAD' && !g1.fallback, JSON.stringify(g1));
  behave = {};
  const n0 = M.doCalls.length;
  await hit(true, 'ICN');
  check('while it rests: no DO call, no fetch from anywhere', M.doCalls.length === n0 && mkCalls().length === 0);
}
{
  // h · news:err:<src> is written at most once per 30 min per outlet (read before write)
  const M = fakeMarket(); M.mode = 'throw';
  env = { REPLAY: makeKV(), MARKET: M };
  behave = { 'mk@direct': 500, einfomax: 500 };
  await hit(true, 'ICN');
  const kv = env.REPLAY;
  check('first failure → one news:err:mk and one news:err:einfomax (non-relay outlets get a record too)', kvPuts(kv, 'news:err:mk').length === 1 && kvPuts(kv, 'news:err:einfomax').length === 1 && errRec(kv, 'einfomax').path === 'direct' && errRec(kv, 'einfomax').status === 500 && !errRec(kv, 'einfomax').relay);
  await hit(true, 'ICN'); await hit(true, 'ICN');
  check('two more failures within 30 min → no more writes', kvPuts(kv, 'news:err:mk').length === 1 && kvPuts(kv, 'news:err:einfomax').length === 1, `${kvPuts(kv, 'news:err:mk').length}/${kvPuts(kv, 'news:err:einfomax').length}`);
  ageKey(kv, 'news:err:mk', 31 * 60e3);
  await hit(true, 'ICN');
  check('31 min later → written again (once)', kvPuts(kv, 'news:err:mk').length === 2 && kvPuts(kv, 'news:err:einfomax').length === 1);
  check('the public answer carries nothing new (no colo, path, egress)', !/"colo"|"path"|"egress"|"fallback"/.test(JSON.stringify((await hit(true, 'ICN')).body)));
}
{
  // i · the DO hangs: the Worker waits 7 s, then fetches directly; the whole answer stays inside the page's 12 s
  const M = fakeMarket(); M.mode = 'hang';
  env = { REPLAY: makeKV(), MARKET: M };
  behave = {};
  const t0 = Date.now();
  const i = await hit(true, 'ICN');
  const dt = Date.now() - t0;
  check('hung relay → direct after ~7 s, answer < 11 s', i.body.sources.mk.ok && mkCalls().map(c => c.where).join() === 'direct' && dt >= 6900 && dt < 11000 && errRec(env.REPLAY, 'mk').error === 'relay timeout', dt + ' ms');
}
{
  // j · the relay's day cap: 503 'relay budget' → remembered per data centre (Cache API) → no more DO calls there
  const M = fakeMarket();
  env = { REPLAY: makeKV(), MARKET: M };
  behave = {};
  const relay = await M.inst(RELAY_NAME);
  const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
  relay.rc = { day, n: RELAY_DAY_MAX };
  const j1 = await hit(true, 'ICN');
  check(`relay at its day cap (${RELAY_DAY_MAX}) → 매일경제 direct, ok`, M.doCalls.length === 1 && mkCalls().map(c => c.where).join() === 'direct' && j1.body.sources.mk.ok && errRec(env.REPLAY, 'mk').error === 'relay budget');
  const gate = cacheStore.get(gateUrl);
  check('the refusal is remembered in the Cache API until the next KST midnight', !!gate && gate.exp > Date.now() + 50e3 && gate.exp <= Date.now() + 86400e3 + 1000);
  check('a refused request does not write the counter', relay.state.log.filter(l => l[0] === 'put').length === 0 && relay.rc.n === RELAY_DAY_MAX);
  ageKey(env.REPLAY, 'news:last:mk', 200e3);
  dropNewsCache();
  await hit(false, 'ICN');
  check('next miss in that data centre: no DO call at all (gate), direct again', M.doCalls.length === 1 && mkCalls().map(c => c.where).join() === 'direct', `doCalls ${M.doCalls.length}`);
}
{
  // k · the relay route itself: only allow-listed outlet keys, GET only, only on the relay instance
  const M = fakeMarket();
  const relay = await M.inst(RELAY_NAME), top = await M.inst('top');
  calls = [];
  const ask = (h, q, init) => als.run('relay', () => h.fetch(new Request('https://news-relay.internal/__relay/news' + q, init)));
  const bad = [];
  for (const q of ['?src=einfomax', '?src=hankyung', '?src=evil', '?src=https%3A%2F%2Fevil.example%2F', '?src=MK', '?src=mk%2F..', '']) {
    const r = await ask(relay, q); bad.push(r.status);
  }
  check('unknown / non-relay outlet keys and URLs → 400', bad.every(s => s === 400), bad.join());
  const p = await ask(relay, '?src=mk', { method: 'POST' });
  check('POST → 405', p.status === 405);
  const t = await ask(top, '?src=mk');
  check('the relay path on the "top" instance → 404 (and the hub counts nothing)', t.status === 404 && top.g.dU === 0 && !top.state.log.some(l => l[0] === 'put'));
  check('none of these reached an outlet or the counter', calls.length === 0 && !relay.state.store.has('relay'));
  const okr = await ask(relay, '?src=mk');
  const oj = await okr.json();
  check('allow-listed key → {ok, status 200, items, egress}', okr.status === 200 && oj.ok === true && oj.status === 200 && Array.isArray(oj.items) && oj.items.length === 30 && oj.egress === 'IAD');
}
{
  // l · the relay's cap keeps the account inside the $5 plan together with the hub's caps (realtime.md §12)
  // hub: 31 days at its day cap + its refusal re-checks after a trip (realtime.md §12-2: +90,000); relay: 31 days at its cap +
  // one gate re-check per data centre per day (10 data centres)
  const doMonth = LIMITS.dayDoReq * 31 + 90000 + RELAY_DAY_MAX * 31 + 10 * 31;
  const gbs = LIMITS.monthAwakeMs / 1000 * 0.125 + RELAY_DAY_MAX * 31 * 7 * 0.125;   // worst: every relay call awake the full 7 s wait
  check(`DO requests at both caps ≤ 80 % of 1,000,000 (${(doMonth / 1e4).toFixed(1)} %)`, doMonth <= 800000);
  check(`DO GB-s at both caps ≤ 65 % of 400,000 (${(gbs / 4000).toFixed(1)} %)`, gbs <= 260000);
}

globalThis.fetch = realFetch;
const bad = results.filter(r => !r[1]);
console.log(`\n${results.length - bad.length}/${results.length} passed`);
process.exit(bad.length ? 1 : 0);
