// Worker /api/news unit checks (docs/standards/news.md §2-2 · §2-3) — no network: the outlets are stubbed with the
// sanitized fixtures in qa/news/fixtures (title · link · pubDate only, as the outlets wrote them on 2026-11-13).
//   node qa/news/worker_test.mjs            exit 1 on any failure
import { readFileSync } from 'node:fs';

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
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url;
  const key = Object.keys(URLS).find(k => URLS[k] === url);
  if (!key) throw new Error('unexpected upstream ' + url);
  const hd = new Headers(init.headers || {});
  calls.push({ key, ua: hd.get('user-agent'), accept: hd.get('accept') });
  const b = behave[key] || 'ok';
  if (typeof b === 'function') return b(init);
  if (b === 'ok') return new Response(FIX(key), { status: 200, headers: { 'content-type': 'application/xml' } });
  if (b === 'net') throw new TypeError('fetch failed');
  if (b === 'hang') return new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
  if (b === 'html') return new Response('<!doctype html><title>blocked</title>', { status: 200, headers: { 'content-type': 'text/html' } });
  if (typeof b === 'number') return new Response('no', { status: b });
  if (typeof b === 'string') return new Response(b, { status: 200, headers: { 'content-type': 'application/xml' } });
  throw new Error('bad behaviour');
};

const worker = (await import('../../worker/src/index.js')).default;
let env = { REPLAY: makeKV() };
const waits = [];
const ctx = { waitUntil: p => waits.push(p) };
async function hit(fresh = true) {
  if (fresh) cacheStore = new Map();
  calls = [];
  const r = await worker.fetch(new Request('https://panse.pages.dev/api/news'), env, ctx);
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

globalThis.fetch = realFetch;
const bad = results.filter(r => !r[1]);
console.log(`\n${results.length - bad.length}/${results.length} passed`);
process.exit(bad.length ? 1 : 0);
