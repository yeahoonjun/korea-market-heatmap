// 정책 자료 — GET /api/policy (docs/standards/policy-feeds.md, AGENTS §3-2 · §3-27).
// User 2026-11-15 16:25 "Kdi만 가져와야겠다" + the 관보 API approval: two sources only —
//   kdi     KDI 경제정보센터 경제정책자료 RSS  https://eiec.kdi.re.kr/policy/rss.do?rss_type=material
//   gwanbo  행정안전부 관보 목록 정보 (공공데이터포털)  https://apis.data.go.kr/1741000/ApiTotalService/getApiTotalList
//
// → {asOf, items:[{src:'kdi'|'gwanbo', title, url, t:'YYYY-MM-DD', org?, kind?}], sources:{kdi:{…}, gwanbo:{…}}}
//   Only headline · link · date · issuing agency (· the gazette's 편집구분) leave the Worker — never a body, description, summary,
//   개정이유 or file. t is a KST date (neither source gives a time). Newest day first; inside a day the two sources alternate so
//   the 전체 view never buries one of them. ≤ 30 per source.
//   sources.<src> = {ok, n, at, error?, stale?} (+ gwanbo: scanned = the gazette rows read for today, before the filter).
//   No item at all and no source answered → 502 {error, sources} (no-store).
// Fetching (news.md §2-3 rules): an honest User-Agent, 6 s per upstream call, no retry inside a request; a failure rests the source
// (KV policy:cool:<src>) so a failing upstream is asked at most every few minutes; the last good copy (KV policy:last:<src>)
// rides along as {ok:false, stale:true}. Each source also has a shared freshness gate: a copy in KV younger than its interval
// (KDI 20 min · 관보 30 min, nights / weekends longer) is served as it is, so all data centres together call each upstream about
// once per interval. Edge cache 600 s (120 s while a source is failing).
// Diagnostics: KV policy:err:<src> {at, colo, error, status?, code?} for 3 days, at most once per 30 min.
//
// The 공공데이터포털 key is the Worker secret env.DATA_GO_KR_KEY. It is put into the request URL in gbPage() and nowhere else:
// errors are fixed words + numbers built here (never an exception message, an upstream message or a URL), nothing is logged,
// and a last scrub removes the key (raw and encoded) from anything this module writes or returns.

const ORIGIN = 'https://panse.pages.dev';
const UA = 'PanseNewsBot/1.0 (+https://panse.pages.dev)';            // the same honest bot name as /api/news (news.md §2-3)
const RSS_ACCEPT = 'application/rss+xml, application/xml;q=0.9, */*;q=0.5';
const TIMEOUT_MS = 6000;
export const POLICY = {
  EDGE_S: 600, EDGE_BAD_S: 120, SWR_S: 600,
  PER_SRC: 30, TITLE_MAX: 200,
  ERR_S: 3 * 86400, ERR_EVERY_MS: 30 * 60e3,
  KDI_LAST_S: 86400, KDI_FRESH_DAY_MS: 20 * 60e3, KDI_FRESH_NIGHT_MS: 60 * 60e3,
  GB_LAST_S: 8 * 86400, GB_FRESH_DAY_MS: 30 * 60e3, GB_FRESH_NIGHT_MS: 120 * 60e3,
  GB_PAGE: 100, GB_MAX_PAGES: 5, GB_BACK_DAYS: 7, GB_BACK_PER_RUN: 3, GB_DAY_MAX: 1500, GB_BUDGET_MS: 10500,
  COOL_FAIL_S: 300, COOL_BLOCK_S: 900, COOL_NOTRSS_S: 1800, COOL_KEY_S: 1800, COOL_QUOTA_S: 3600,
};
export const KDI_URL = 'https://eiec.kdi.re.kr/policy/rss.do?rss_type=material';
export const GB_URL = 'https://apis.data.go.kr/1741000/ApiTotalService/getApiTotalList';
const KDI_HOST = 'eiec.kdi.re.kr';
const GB_SITE = 'https://gwanbo.go.kr';
const GB_HOSTS = new Set(['gwanbo.go.kr', 'www.gwanbo.go.kr', 'open.gwanbo.go.kr']);
export const GB_FALLBACK_URL = 'https://gwanbo.go.kr/user/search/searchDaily.do';   // 전자관보 일자별 관보 (data.go.kr 15087197)
// 관보 filter for a market dashboard (policy-feeds.md §4): the issuing agency is one of the economy / finance / trade / tax bodies,
// and the entry is not a personnel notice (인사). One place to widen or narrow it.
export const GB_ORG_RE = /재정경제부|기획재정부|기획예산처|금융위원회|증권선물위원회|금융감독원|한국은행|산업통상|공정거래위원회|국세청|관세청/;
export const GB_SKIP_KIND_RE = /인사/;

/* ── route ─────────────────────────────── */
export async function policyRoute(request, env, ctx) {
  const secret = keyOf(env);
  try {
    if (request.method !== 'GET' && request.method !== 'HEAD') return json({ error: 'GET으로만 받을 수 있어요' }, 405, 'no-store');
    const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null;
    const cacheKey = new Request(new URL('/__cache/policy-v1', request.url).toString());
    const hit = cache && await cache.match(cacheKey);
    if (hit) return hit;
    const body = await policyCore(env, ctx, { colo: (request.cf && request.cf.colo) || null });
    const anyOk = Object.values(body.sources).some(s => s.ok);
    if (!body.items.length && !anyOk) {
      return json(scrub({ error: '정책 자료를 불러오지 못했어요', sources: body.sources }, secret), 502, 'no-store');
    }
    const allOk = Object.values(body.sources).every(s => s.ok);
    const ttl = allOk ? POLICY.EDGE_S : POLICY.EDGE_BAD_S;
    const res = json(scrub(body, secret), 200, `public, s-maxage=${ttl}, stale-while-revalidate=${POLICY.SWR_S}`);
    if (cache) {
      const put = cache.put(cacheKey, res.clone()).catch(() => {});
      if (ctx && ctx.waitUntil) ctx.waitUntil(put);
    }
    return res;
  } catch (e) {
    return json({ error: '정책 자료를 만들지 못했어요' }, 502, 'no-store');   // never the exception text (it could carry a URL)
  }
}
function json(body, status, cc) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': cc, 'access-control-allow-origin': ORIGIN } });
}

export async function policyCore(env, ctx, where = {}) {
  env = env || {};
  const kv = env.REPLAY && typeof env.REPLAY.get === 'function' ? env.REPLAY : null;
  const now = Date.now();
  const io = { kv, ctx, now, colo: where.colo || null, secret: keyOf(env) };
  const [k, g] = await Promise.allSettled([kdiOne(io), gbOne(io, env)]);
  const v = r => (r.status === 'fulfilled' ? r.value : { ok: false, error: 'error', items: [] });
  const kd = v(k), gb = v(g);
  const meta = (x, extra) => ({ ok: !!x.ok, n: x.items.length, at: x.at || null, ...(x.ok ? {} : { error: x.error || 'error' }), ...(x.stale ? { stale: true } : {}), ...extra });
  const sources = { kdi: meta(kd), gwanbo: meta(gb, Number.isFinite(gb.scanned) ? { scanned: gb.scanned } : {}) };
  return { asOf: kstIso(now), items: mergeItems(kd.items, gb.items), sources };
}

// newest day first; inside one day KDI and 관보 take turns (KDI first), each in its own order
export function mergeItems(kdi, gb) {
  const days = new Map();
  const add = (list, src) => { for (const x of list || []) { let d = days.get(x.t); if (!d) days.set(x.t, d = { kdi: [], gwanbo: [] }); d[src].push(x); } };
  add(kdi, 'kdi'); add(gb, 'gwanbo');
  const out = [], seen = new Set();
  for (const t of [...days.keys()].sort().reverse()) {
    const d = days.get(t);
    for (let i = 0; i < Math.max(d.kdi.length, d.gwanbo.length); i++) {
      for (const x of [d.kdi[i], d.gwanbo[i]]) {
        if (!x || seen.has(x.url + '\u0001' + x.title)) continue;
        seen.add(x.url + '\u0001' + x.title);
        out.push(x);
      }
    }
  }
  return out;
}

/* ── KV helpers ─────────────────────────────── */
async function kvGet(kv, key, type) {
  if (!kv) return null;
  try { return await kv.get(key, type); } catch (e) { return null; }
}
function kvPut(io, key, value, ttl) {
  if (!io.kv) return;
  let p;
  try { p = Promise.resolve(io.kv.put(key, scrubText(value, io.secret), { expirationTtl: Math.max(60, ttl) })).catch(() => {}); } catch (e) { return; }
  if (io.ctx && io.ctx.waitUntil) io.ctx.waitUntil(p);
}
// KV policy:err:<src>, 3 days — read first, so a source writes at most once per 30 minutes
function errNote(io, src, rec) {
  if (!io.kv || typeof io.kv.put !== 'function') return;
  const p = (async () => {
    const old = await kvGet(io.kv, 'policy:err:' + src, 'json');
    if (old && io.now - Date.parse(old.at) < POLICY.ERR_EVERY_MS) return;
    await io.kv.put('policy:err:' + src, scrubText(JSON.stringify({ at: kstIso(io.now), colo: io.colo, ...rec }), io.secret), { expirationTtl: POLICY.ERR_S });
  })().catch(() => {});
  if (io.ctx && io.ctx.waitUntil) io.ctx.waitUntil(p);
}
const validCopy = last => !!(last && typeof last.at === 'string' && !isNaN(Date.parse(last.at)));

/* ── KDI 경제정보센터 경제정책자료 RSS ─────────────────────────────── */
// RSS 2.0, UTF-8, 100 items, <pubDate> empty on every item (2026-11-15). The date and the agency come from the first words of
// <description> ("재정경제부는 ’26.11.13.(금) …") — read here, never sent on.
async function kdiOne(io) {
  const [cool, last] = await Promise.all([kvGet(io.kv, 'policy:cool:kdi'), kvGet(io.kv, 'policy:last:kdi', 'json')]);
  const hasLast = validCopy(last) && Array.isArray(last.items) && last.items.length > 0;
  const fallback = error => (hasLast ? { ok: false, error, stale: true, at: last.at, items: last.items } : { ok: false, error, items: [] });
  if (cool) return fallback('cool-down');
  if (hasLast && io.now - Date.parse(last.at) < kdiFreshMs(io.now)) return { ok: true, at: last.at, items: last.items };
  const r = await getText(KDI_URL, { 'user-agent': UA, accept: RSS_ACCEPT }, TIMEOUT_MS);
  let error = r.error, items = null;
  if (r.ok) {
    if (!/<rss\b|<channel\b/i.test(r.text.slice(0, 2000))) error = 'not rss';
    else {
      items = parseKdi(r.text, io.now);
      if (!items.length) error = 'no items';
    }
  }
  if (error) {
    const coolS = r.status === 403 || r.status === 429 ? POLICY.COOL_BLOCK_S : error === 'not rss' ? POLICY.COOL_NOTRSS_S : POLICY.COOL_FAIL_S;
    kvPut(io, 'policy:cool:kdi', String(io.now), coolS);
    errNote(io, 'kdi', { error, ...(r.status ? { status: r.status } : {}) });
    return fallback(error);
  }
  const at = kstIso(io.now);
  kvPut(io, 'policy:last:kdi', JSON.stringify({ at, items }), POLICY.KDI_LAST_S);   // every fetch: its `at` is the shared freshness gate
  return { ok: true, at, items };
}
function kdiFreshMs(now) { return workHours(now, 7, 20) ? POLICY.KDI_FRESH_DAY_MS : POLICY.KDI_FRESH_NIGHT_MS; }

export function parseKdi(xml, now) {
  const today = kstDate(now), out = [], seen = new Set();
  let prev = null;
  for (const b of xml.match(/<item\b[\s\S]*?<\/item>/gi) || []) {
    const title = cleanText(tagText(b, 'title'), POLICY.TITLE_MAX);
    const url = kdiUrl(tagText(b, 'link'));
    if (!title || !url || seen.has(url)) continue;
    seen.add(url);
    const m = kdiMeta(tagText(b, 'description'));
    // the date the release states; one in the future ("’26.11.16.(월)부터 …") or none → the item above it (the feed is newest first)
    const t = m.d && m.d <= today ? m.d : prev || today;
    prev = t;
    out.push({ src: 'kdi', title, url, t, ...(m.org ? { org: m.org } : {}) });
    if (out.length >= POLICY.PER_SRC) break;
  }
  return out;
}
// "재정경제부는 ’26.11.13.(금) …" → {org:'재정경제부', d:'2026-11-13'}; "해양수산부와 우주항공청, 기후에너지환경부는 …" → org '해양수산부 외 2곳'
export function kdiMeta(desc) {
  const s = cleanText(desc, 400);
  const DT = "[’'‘`]?\\s*(\\d{4}|\\d{2})\\s*\\.\\s*(\\d{1,2})\\s*\\.\\s*(\\d{1,2})\\s*\\.";
  let m = new RegExp("^([^\\s’'\"‘“「『(\\[][^’'\"‘“「『\\n]{0,40}?)\\s*(?:은|는)\\s*" + DT).exec(s);
  let org = null, y, mo, d;
  if (m) {
    [, org, y, mo, d] = m;
    const parts = org.split(/(?:와|과)\s+|\s*,\s*|\s*·\s*/).map(x => x.trim()).filter(x => x.length >= 2);
    org = !parts.length || [...org].length > 34 ? null : parts.length > 1 ? `${parts[0]} 외 ${parts.length - 1}곳` : parts[0];
  } else if ((m = new RegExp(DT).exec(s.slice(0, 120)))) [, y, mo, d] = m;
  const yy = y ? (y.length === 2 ? 2000 + +y : +y) : 0;
  const ok = yy >= 2000 && +mo >= 1 && +mo <= 12 && +d >= 1 && +d <= 31;
  return { org: org ? cleanText(org, 30) : null, d: ok ? `${yy}-${pad(+mo)}-${pad(+d)}` : null };
}
function kdiUrl(raw) {
  let u;
  try { u = new URL(String(raw || '').trim()); } catch (e) { return null; }
  if ((u.protocol !== 'https:' && u.protocol !== 'http:') || u.hostname.toLowerCase() !== KDI_HOST || u.username || u.password) return null;
  const num = u.searchParams.get('num');
  if (u.pathname !== '/policy/materialView.do' || !num || !/^\d{1,12}$/.test(num)) return null;
  return `https://${KDI_HOST}/policy/materialView.do?num=${num}`;
}

/* ── 행정안전부 관보 목록 정보 (공공데이터포털 15109157) ─────────────────────────────── */
// getApiTotalList?serviceKey&pageNo&pageSize&reqFrom&reqTo(YYYYMMDD)&type=1(json) → {response:{resultCode, resultMsg, totalCount,
// pageSize, pageNo, items:{item:[{cntntSeqNo, cntntSj, ofcttBookNm, hopePblictDt, cmplatSeNm, themaSe, pblcnInstNm, basisLawNm,
// crtnYn, rvsnRsnMainCn, pdfFilePath}]}}} (the portal's own Swagger, 2026-11-15). One query per KST day: today on every refresh, a
// past day until it has been read once after it ended (then it is done — kept in the snapshot), at most 7 days back, only as many
// as it takes to fill 30 rows.
async function gbOne(io, env) {
  const [cool, last] = await Promise.all([kvGet(io.kv, 'policy:cool:gwanbo'), kvGet(io.kv, 'policy:last:gwanbo', 'json')]);
  const snap = validCopy(last) && last.days && typeof last.days === 'object' ? last : null;
  const fallback = error => {
    const items = snap ? gbItems(snap.days) : [];
    return snap && items.length ? { ok: false, error, stale: true, at: snap.at, items } : { ok: false, error, items: [] };
  };
  if (!io.secret) return fallback('no key');
  if (cool) return fallback('cool-down');
  const today = kstYmd(io.now);
  if (snap && io.now - Date.parse(snap.at) < gbFreshMs(io.now)) return { ok: true, at: snap.at, items: gbItems(snap.days), scanned: dayTotal(snap, today) };
  const used = snap && snap.calls && snap.calls.d === today ? +snap.calls.n || 0 : 0;
  if (used >= POLICY.GB_DAY_MAX) return fallback('budget');
  const run = { key: io.secret, calls: 0, until: Date.now() + POLICY.GB_BUDGET_MS, max: POLICY.GB_DAY_MAX - used };
  const res = await gbRefresh(run, snap, io.now);
  const calls = { d: today, n: used + run.calls };
  if (!res.ok) {
    const coolS = res.kind === 'key' ? POLICY.COOL_KEY_S : res.kind === 'quota' ? POLICY.COOL_QUOTA_S : POLICY.COOL_FAIL_S;
    kvPut(io, 'policy:cool:gwanbo', String(io.now), coolS);
    errNote(io, 'gwanbo', { error: res.error, ...(res.status ? { status: res.status } : {}), ...(res.code ? { code: res.code } : {}) });
    if (snap) kvPut(io, 'policy:last:gwanbo', JSON.stringify({ ...snap, calls }), POLICY.GB_LAST_S);   // keep the day's call count
    return fallback(res.error);
  }
  const at = kstIso(io.now);
  kvPut(io, 'policy:last:gwanbo', JSON.stringify({ at, days: res.days, calls }), POLICY.GB_LAST_S);
  return { ok: true, at, items: gbItems(res.days), scanned: res.days[today] ? res.days[today].total : 0 };
}
function gbFreshMs(now) { return workHours(now, 6, 20) ? POLICY.GB_FRESH_DAY_MS : POLICY.GB_FRESH_NIGHT_MS; }
const dayTotal = (snap, ymd) => (snap.days[ymd] && Number.isFinite(snap.days[ymd].total) ? snap.days[ymd].total : 0);

async function gbRefresh(run, snap, now) {
  const today = kstYmd(now), oldest = kstYmd(now - POLICY.GB_BACK_DAYS * 86400e3);
  const days = {};
  if (snap) for (const [d, v] of Object.entries(snap.days)) if (/^\d{8}$/.test(d) && d >= oldest && d < today && v && Array.isArray(v.items)) days[d] = v;
  const t = await gbDay(run, today);
  if (!t.ok) return t;
  days[today] = { items: t.items, total: t.total, done: false };
  // past days: done ones count as they are; the first not-done ones (nearest first, ≤ 3 a run) are read now — after they ended
  let have = t.items.length;
  const want = [];
  for (let i = 1; i <= POLICY.GB_BACK_DAYS && have < POLICY.PER_SRC && want.length < POLICY.GB_BACK_PER_RUN; i++) {
    const d = kstYmd(now - i * 86400e3);
    if (!days[d] || !days[d].done) want.push(d);
    if (days[d]) have += days[d].items.length;          // a day read while it was today can only grow when read again
  }
  const got = await Promise.all(want.map(d => gbDay(run, d)));
  got.forEach((r, i) => { if (r.ok) days[want[i]] = { items: r.items, total: r.total, done: true }; });   // a failed past day waits for the next run
  return { ok: true, days };
}
// newest day first, inside a day the gazette's own number (newest last in the issue → first here); ≤ 30
function gbItems(days) {
  const out = [];
  for (const d of Object.keys(days || {}).sort().reverse()) for (const x of days[d].items || []) { out.push(x); if (out.length >= POLICY.PER_SRC) return out; }
  return out;
}
async function gbDay(run, ymd) {
  const p1 = await gbPage(run, ymd, 1);
  if (!p1.ok) return p1;
  let rows = p1.rows;
  // the page size the portal really used (if it caps pageSize below 100, the next pages follow its size)
  const per = rows.length > 0 && rows.length < POLICY.GB_PAGE && p1.total > rows.length ? rows.length : POLICY.GB_PAGE;
  const pages = Math.min(POLICY.GB_MAX_PAGES, Math.ceil(p1.total / per));
  if (pages > 1 && rows.length) {
    const rest = await Promise.all(Array.from({ length: pages - 1 }, (_, i) => gbPage(run, ymd, i + 2)));
    const bad = rest.find(r => !r.ok);
    if (bad) return bad;
    for (const r of rest) rows = rows.concat(r.rows);
  }
  const items = [], seen = new Set();
  for (const x of rows) {
    const it = gbItem(x, ymd);
    if (!it || seen.has(it.id)) continue;
    seen.add(it.id);
    items.push(it);
  }
  items.sort((a, b) => String(b.id).localeCompare(String(a.id), 'en', { numeric: true }));
  return { ok: true, total: Math.max(p1.total, rows.length), items: items.map(({ id, ...x }) => x) };
}
// one row → an item, or null when the market filter (GB_ORG_RE, not 인사) leaves it out
export function gbItem(x, ymd) {
  if (!x || typeof x !== 'object') return null;
  const org = cleanText(x.pblcnInstNm, 30), kind = cleanText(x.cmplatSeNm, 12);
  if (!org || !GB_ORG_RE.test(org) || (kind && GB_SKIP_KIND_RE.test(kind))) return null;
  const title = cleanText(x.cntntSj, POLICY.TITLE_MAX);
  if (!title) return null;
  const t = gbDate(x.hopePblictDt) || `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;
  const id = String(x.cntntSeqNo == null ? '' : x.cntntSeqNo).replace(/[^\w.-]/g, '').slice(0, 40) || title;
  return { id, src: 'gwanbo', title, url: gbUrl(x.pdfFilePath), t, org, ...(kind ? { kind } : {}) };
}
// '2026-11-13' · '2026.11.13' · '2026. 11. 13.' · '20261113' → '2026-11-13'
export function gbDate(raw) {
  const s = String(raw == null ? '' : raw).trim();
  const m = /^(\d{4})(\d{2})(\d{2})$/.exec(s) || /^(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})/.exec(s);
  if (!m || +m[2] < 1 || +m[2] > 12 || +m[3] < 1 || +m[3] > 31) return null;
  return `${m[1]}-${pad(+m[2])}-${pad(+m[3])}`;
}
// 관보PDF원문링크 → the official gazette site (https, gwanbo.go.kr hosts only); anything else → the site's 일자별 관보 page
export function gbUrl(raw) {
  const s = String(raw == null ? '' : raw).replace(/[\u0000-\u001f\s]+/g, '');
  if (!s) return GB_FALLBACK_URL;
  let u;
  try { u = /^[a-z][a-z0-9+.-]*:/i.test(s) ? new URL(s) : new URL(s.startsWith('/') ? s : '/' + s, GB_SITE); } catch (e) { return GB_FALLBACK_URL; }
  if ((u.protocol !== 'https:' && u.protocol !== 'http:') || !GB_HOSTS.has(u.hostname.toLowerCase()) || u.username || u.password) return GB_FALLBACK_URL;
  u.protocol = 'https:'; u.hash = '';
  return u.href;
}
// one page. The key goes into this URL and nowhere else; the outcome is built from status numbers and fixed words only.
async function gbPage(run, ymd, page) {
  if (run.calls >= run.max) return { ok: false, error: 'budget', kind: 'quota' };
  const left = run.until - Date.now();
  if (left < 1000) return { ok: false, error: 'timeout' };
  run.calls++;
  const qs = `serviceKey=${encodeKey(run.key)}&pageNo=${page}&pageSize=${POLICY.GB_PAGE}&reqFrom=${ymd}&reqTo=${ymd}&type=1`;
  const r = await getText(GB_URL + '?' + qs, { 'user-agent': UA, accept: 'application/json, application/xml;q=0.5' }, Math.min(TIMEOUT_MS, left));
  if (r.error && !r.text) return { ok: false, error: r.error, ...(r.status ? { status: r.status } : {}), kind: gbKind(r.status, null) };
  const text = r.text || '';
  if (/^\s*</.test(text)) {                                  // the portal gateway answers in XML whatever `type` says (key / quota errors)
    const code = xmlCode(text), gw = code && code !== '00' && code !== '0' ? code : '';
    const error = [r.ok ? '' : 'http ' + r.status, gw ? 'gw ' + gw : r.ok ? 'not json' : ''].filter(Boolean).join(' ');
    return { ok: false, error, ...(r.status ? { status: r.status } : {}), ...(gw ? { code: gw } : {}), kind: gbKind(r.status, gw) };
  }
  if (!r.ok) return { ok: false, error: 'http ' + r.status, status: r.status, kind: gbKind(r.status, null) };
  let j;
  try { j = JSON.parse(text); } catch (e) { return { ok: false, error: 'not json', status: r.status }; }
  const resp = j && typeof j === 'object' ? (j.response && typeof j.response === 'object' ? j.response : j) : {};
  const head = resp.header && typeof resp.header === 'object' ? resp.header : resp;
  const body = resp.body && typeof resp.body === 'object' ? resp.body : resp;
  const code = safeCode(head.resultCode);
  if (code === '10' || code === '03' || code === '3') return { ok: true, total: 0, rows: [] };    // 조회결과 없음 / NODATA
  if (code && code !== '00' && code !== '0') return { ok: false, error: 'api ' + code, code, kind: gbKind(r.status, code) };
  const items = body.items;
  const item = items && typeof items === 'object' && !Array.isArray(items) ? items.item : items;
  const rows = Array.isArray(item) ? item : item && typeof item === 'object' ? [item] : [];
  const total = Number.isFinite(+body.totalCount) ? +body.totalCount : rows.length;
  return { ok: true, total, rows };
}
// key / quota failures rest longer (the portal's codes: 20 접근 거부 · 30 등록되지 않은 키 · 31 기한 만료 · 32 등록되지 않은 IP ·
// 304/305 게이트웨이 키; 22 하루 한도 넘음)
function gbKind(status, code) {
  if (status === 429 || code === '22') return 'quota';
  if (status === 401 || status === 403 || ['20', '30', '31', '32', '304', '305'].includes(code)) return 'key';
  return 'other';
}
const xmlCode = text => safeCode((/<returnReasonCode>\s*([^<]{1,12}?)\s*<\/returnReasonCode>/i.exec(text) || /<resultCode>\s*([^<]{1,12}?)\s*<\/resultCode>/i.exec(text) || [])[1]);
const safeCode = v => { const s = String(v == null ? '' : v).trim(); return /^\d{1,4}$/.test(s) ? s : ''; };
// a decoded key (+ / =) is percent-encoded once; the portal's "Encoding" key (already %XX) goes as it is
const encodeKey = k => (/%[0-9A-Fa-f]{2}/.test(k) ? k : encodeURIComponent(k));
const keyOf = env => (env && typeof env.DATA_GO_KR_KEY === 'string' ? env.DATA_GO_KR_KEY.trim() : '');

/* ── shared helpers ─────────────────────────────── */
// one GET, no retry → {ok, status, text?, error?}; the error is 'timeout' · 'network' · 'http N' (never an exception message)
async function getText(url, headers, ms) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms);
  let status = 0;
  try {
    const r = await fetch(url, { headers, redirect: 'follow', signal: ac.signal });
    status = r.status;
    const text = await r.text();
    return r.ok ? { ok: true, status, text } : { ok: false, status, text, error: 'http ' + status };
  } catch (e) {
    return { ok: false, status, error: (e && e.name === 'AbortError') || ac.signal.aborted ? 'timeout' : 'network' };
  } finally { clearTimeout(timer); }
}
// the text of the first <name>…</name>: CDATA kept as it is, the rest XML-unescaped
function tagText(block, name) {
  const m = new RegExp('<' + name + '(?:\\s[^>]*)?>([\\s\\S]*?)</' + name + '\\s*>', 'i').exec(block);
  if (!m) return '';
  const raw = m[1], re = /<!\[CDATA\[([\s\S]*?)\]\]>/g;
  let out = '', i = 0, c;
  while ((c = re.exec(raw))) { out += xmlUnescape(raw.slice(i, c.index)) + c[1]; i = re.lastIndex; }
  return out + xmlUnescape(raw.slice(i));
}
const ENT = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'", nbsp: ' ', middot: '·', hellip: '…', lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”', ndash: '–', mdash: '—', lsaquo: '‹', rsaquo: '›', laquo: '«', raquo: '»' };
function xmlUnescape(s) {
  return String(s).replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (all, e) => {
    if (e[0] === '#') {
      const cp = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      try { return String.fromCodePoint(cp); } catch (_) { return all; }
    }
    const v = ENT[e.toLowerCase()];
    return v == null ? all : v;
  });
}
// entities once more (feeds that escape twice) → tags to text → invisible characters out → one space → trimmed → ≤ max characters
export function cleanText(raw, max) {
  if (raw == null || typeof raw === 'object') return '';
  let t = xmlUnescape(String(raw));
  t = t.replace(/<\/?[A-Za-z][^>]*>/g, '');
  t = t.replace(/[﻿​-‍⁠\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '').replace(/\s+/g, ' ').trim();
  const cps = Array.from(t);
  return cps.length > max ? cps.slice(0, max).join('').trim() : t;
}
// the key never leaves: remove it (raw · percent-encoded · URL-encoded) from anything returned or stored
function scrubText(s, secret) {
  s = String(s);
  if (!secret) return s;
  for (const k of new Set([secret, encodeKey(secret), encodeURIComponent(secret)])) if (k && k.length >= 4) s = s.split(k).join('***');
  return s;
}
const scrub = (obj, secret) => (secret ? JSON.parse(scrubText(JSON.stringify(obj), secret)) : obj);

const pad = n => String(n).padStart(2, '0');
function kstParts(ms) { const k = new Date(ms + 9 * 3600e3); return { y: k.getUTCFullYear(), m: k.getUTCMonth() + 1, d: k.getUTCDate(), h: k.getUTCHours(), wd: k.getUTCDay() }; }
export function kstDate(ms) { const p = kstParts(ms); return `${p.y}-${pad(p.m)}-${pad(p.d)}`; }
export function kstYmd(ms) { const p = kstParts(ms); return `${p.y}${pad(p.m)}${pad(p.d)}`; }
function workHours(ms, from, to) { const p = kstParts(ms); return p.wd >= 1 && p.wd <= 5 && p.h >= from && p.h < to; }
export function kstIso(ms) {
  const k = new Date(ms + 9 * 3600e3);
  return `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}T${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}:${pad(k.getUTCSeconds())}+09:00`;
}
