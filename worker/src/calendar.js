// 증시 캘린더 — GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD[&kinds=kr,us,cb,mkt,corp]
// AGENTS §3-33 (user 2026-11-15 17:52: 화면 A · 국가데이터처 · 2027 금통위 예정 · 주총/IR 2단계 · 위클리 숨김 · 발표 뒤 값), design and
// sources (with URLs): docs/standards/calendar.md.
//
// Every upstream is read on a request (no cron of its own), at most at its own interval, and kept in KV (env.REPLAY) as the
// last good copy; a failed refresh keeps serving that copy (sources.<id>.ok:false + stale). The answer is assembled from those
// copies + the hand-entered tables below + rules (expiries, minutes) and edge-cached for CAL_TTL seconds.
//
//   kr   한국은행 통계공표일정 web page (one page = the whole year)           · 국가데이터처 보도계획 web page (one month a page)
//   us   FRED fred/release/dates (env.FRED_KEY, include_release_dates_with_no_data=true) — dates only; times from FRED_REL below
//   cb   금통위 · FOMC (hand-entered, 1 year ahead) + minutes by rule
//   mkt  KRX holidays / special days (hand-entered) + 코스피200 expiries by rule (weekly ones flagged `weekly`, the page hides them)
//   corp OpenDART 무상 · 유상증자 dates (env.DART_KEY): list.json B001/C001 per day → fricDecsn · pifricDecsn · estkRs
//        금융위 배당 · 보호예수 · 권리일정 (env.DATA_GO_KR_KEY): code ready, OFF until the shared data.go.kr helper is wired in
//        (configureCalendar({fsc})) and env.CAL_FSC === 'on' — see fscRefresh()
//   values after a release: ECOS KeyStatisticList (env.ECOS_KEY, one call) · FRED series/observations — text only, no colour
//
// Keys go into upstream URLs and nowhere else: errors are short fixed codes, KV/answers/logs never carry a URL.

const UA = 'Mozilla/5.0 (compatible; panse/1.0; +https://panse.pages.dev)';
const ORIGIN = 'https://panse.pages.dev';
const KST_MS = 9 * 3600e3, DAY_MS = 86400e3;
export const CAL_TTL = 300;                 // edge cache of an answer (s)
export const MAX_SPAN = 42;                 // days per request (a month grid = 6 weeks)
const FETCH_MS = 8000;
const LOCK_S = 90;                          // cross-isolate refresh lock (KV, ≥ 60 s)
const DART_DAY_CAP = 400;                   // our own daily ceiling for the calendar's OpenDART calls (key: ~20,000/day, §3-29 uses ~1,729)
const DART_BACK_DAYS = 60;                  // capital-increase filings older than this are not looked for
const DART_DAYS_PER_RUN = 6;                // backfill pace (days per refresh)

// ───────────────────────── hand-entered tables (sources: calendar.md §2-3 · §2-4) ─────────────────────────
// 금통위 통화정책방향 결정회의 — 2026: bok.or.kr 결정회의 목록; 2027: SBS Biz 2026-10-29 (BOK page still empty) → tentative
export const BOK_MEETINGS = [
  '2026-01-15', '2026-02-26', '2026-04-10', '2026-05-28', '2026-07-16', '2026-08-27', '2026-10-22', '2026-11-26',
].map(d => ({ d })).concat(['2027-01-14', '2027-02-25', '2027-04-09', '2027-05-27', '2027-07-15', '2027-08-26', '2027-10-15', '2027-11-25']
  .map(d => ({ d, tentative: '보도 기준 — 한국은행 공지 전' })));
// FOMC (federalreserve.gov fomccalendars, Last Update 2026-11-12): decision day = the meeting's 2nd day, statement 2:00 p.m. ET
export const FOMC = [
  ['2026-01-28', 0], ['2026-03-18', 1], ['2026-04-29', 0], ['2026-06-17', 1], ['2026-07-29', 0], ['2026-09-16', 1], ['2026-10-28', 0], ['2026-12-09', 1],
  ['2027-01-27', 0], ['2027-03-17', 0], ['2027-04-28', 0], ['2027-06-09', 0], ['2027-07-28', 0], ['2027-09-15', 0], ['2027-10-27', 0], ['2027-11-17', 0],
].map(([d, sep]) => ({ d, sep: !!sep, tentative: d >= '2027-01-01' ? '연준: 직전 회의에서 확정' : null }));
// KRX: closed days and special sessions (only what a source confirmed; calendar.md §2-4). Add the next year when KRX announces it.
export const KRX_DAYS = {
  '2026-05-01': { kind: 'closed', note: '휴장 · 노동절' },
  '2026-06-03': { kind: 'closed', note: '휴장 · 지방선거일' },
  '2026-07-17': { kind: 'closed', note: '휴장 · 제헌절' },
  '2026-11-19': { kind: 'special', note: '수능 · 정규장 10:00–16:30', open: '10:00', close: '16:30' },
  '2026-12-25': { kind: 'closed', note: '휴장 · 성탄절' },
  '2026-12-31': { kind: 'closed', note: '휴장 · 연말', tentative: '거래소 공지 전' },
  '2027-01-01': { kind: 'closed', note: '휴장 · 신정' },
  '2027-01-04': { kind: 'special', note: '첫 거래일 · 10:00 개장', open: '10:00', tentative: '거래소 공지 전' },
};
// FRED releases (release_id → title, ET time or null when unconfirmed, base star, value series for after the release)
// series value: u = FRED units transform, f = format (pct: signed %, rate: %, man: × mult → 만 단위, num)
export const FRED_REL = {
  10: { title: '미국 소비자물가(CPI)', et: '08:30', star: 3, vals: [{ s: 'CPIAUCSL', u: 'pc1', f: 'pct', l: '전년 대비' }] },
  50: { title: '미국 고용보고서', et: '08:30', star: 3, sub: '비농업 고용 · 실업률', vals: [{ s: 'PAYEMS', u: 'chg', f: 'man', m: 1000, sign: 1, l: '비농업 고용', unit: '명' }, { s: 'UNRATE', u: 'lin', f: 'rate', l: '실업률' }] },
  53: { title: '미국 GDP', et: '08:30', star: 2, vals: [{ s: 'A191RL1Q225SBEA', u: 'lin', f: 'rate', l: '성장률(연율)' }] },
  54: { title: '미국 개인소득 · 소비지출(PCE)', et: '08:30', star: 2, vals: [{ s: 'PCEPILFE', u: 'pc1', f: 'pct', l: '근원 PCE 전년 대비' }] },
  46: { title: '미국 생산자물가(PPI)', et: '08:30', star: 2, vals: [{ s: 'PPIFIS', u: 'pc1', f: 'pct', l: '전년 대비' }] },
  9: { title: '미국 소매판매', et: '08:30', star: 2, vals: [{ s: 'RSAFS', u: 'pch', f: 'pct', l: '전월 대비' }] },
  192: { title: '미국 구인 · 이직(JOLTS)', et: '10:00', star: 2, vals: [{ s: 'JTSJOL', u: 'lin', f: 'man', m: 1000, l: '구인', unit: '건' }] },
  13: { title: '미국 산업생산 · 설비가동률', et: null, star: 1, vals: [{ s: 'INDPRO', u: 'pch', f: 'pct', l: '전월 대비' }] },
  91: { title: '미국 미시간대 소비자심리', et: null, star: 1, vals: [{ s: 'UMCSENT', u: 'lin', f: 'num', l: '지수' }] },
  180: { title: '미국 주간 신규 실업수당 청구', et: '08:30', star: 1, vals: [{ s: 'ICSA', u: 'lin', f: 'man', m: 1, l: '청구', unit: '건' }] },
  27: { title: '미국 주택착공', et: '08:30', star: 1, vals: [{ s: 'HOUST', u: 'lin', f: 'man', m: 1000, l: '연율', unit: '호' }] },
  97: { title: '미국 신규주택판매', et: '10:00', star: 1, vals: [{ s: 'HSN1F', u: 'lin', f: 'man', m: 1000, l: '연율', unit: '호' }] },
  11: { title: '미국 고용비용지수(ECI)', et: '08:30', star: 1, vals: [{ s: 'ECIALLCIV', u: 'pch', f: 'pct', l: '전분기 대비' }] },
};
// FOMC value after the decision: the target range (FRED DFEDTARL · DFEDTARU)
const FOMC_VALS = [{ s: 'DFEDTARL', u: 'lin' }, { s: 'DFEDTARU', u: 'lin' }];
// 한국은행 / 국가데이터처 titles → star, and the ECOS KeyStatisticList names that carry the released value
export const KR_RULES = [
  { re: /국내총생산\(속보\)/, star: 3, ecos: ['경제성장률(실질, 계절조정 전기대비)'] },
  { re: /국민소득\(잠정\)/, star: 2, ecos: ['경제성장률(실질, 계절조정 전기대비)'] },
  { re: /국제수지\(잠정\)/, star: 2, ecos: ['경상수지'] },
  { re: /수출입물가지수/, star: 2, ecos: ['수출물가지수', '수입물가지수'] },
  { re: /소비자동향조사/, star: 2, ecos: ['소비자심리지수'] },
  { re: /기업경기조사/, star: 2, ecos: ['경제심리지수'] },
  { re: /가계신용/, star: 2, ecos: ['가계신용'] },
  { re: /생산자물가지수/, star: 1, ecos: ['생산자물가지수'] },
  { re: /통화 및 유동성/, star: 1, ecos: ['M2(광의통화, 평잔)'] },
  { re: /가중평균금리/, star: 1, ecos: ['예금은행 대출금리', '예금은행 수신금리'] },
  // 국가데이터처 (only these three are taken from its 보도계획)
  { re: /소비자물가동향/, star: 2, ecos: ['소비자물가지수'], kostat: true },
  { re: /고용동향/, star: 2, ecos: ['실업률', '고용률'], kostat: true },
  { re: /산업활동동향/, star: 2, ecos: ['전산업생산지수'], kostat: true },
];
const KOSTAT_KEEP = /^\d{4}년 \d{1,2}월(?: 및 연간)? (소비자물가동향|고용동향|산업활동동향)$/;

// ───────────────────────── small helpers ─────────────────────────
const pad = n => String(n).padStart(2, '0');
export const kstDate = ms => new Date(ms + KST_MS).toISOString().slice(0, 10);
const kstHm = ms => new Date(ms + KST_MS).toISOString().slice(11, 16);
const dUTC = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
export const addDays = (s, n) => new Date(dUTC(s) + n * DAY_MS).toISOString().slice(0, 10);
const wday = s => new Date(dUTC(s)).getUTCDay();
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const validDate = s => DATE_RE.test(s) && new Date(dUTC(s)).toISOString().slice(0, 10) === s;
// KST instant of a wall-clock time in America/New_York (DST from Intl, not a table)
export function etToKst(d, hm) {
  const [y, mo, da] = d.split('-').map(Number), [hh, mm] = hm.split(':').map(Number);
  for (const off of [4, 5]) {
    const t = Date.UTC(y, mo - 1, da, hh + off, mm);
    const p = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date(t));
    const g = k => +p.find(x => x.type === k).value;
    if (g('year') === y && g('month') === mo && g('day') === da && (g('hour') % 24) === hh && g('minute') === mm) return { d: kstDate(t), t: kstHm(t), ms: t };
  }
  const t = Date.UTC(y, mo - 1, da, hh + 5, mm);
  return { d: kstDate(t), t: kstHm(t), ms: t };
}
const kstMs = (d, hm) => dUTC(d) + ((+hm.slice(0, 2)) * 60 + (+hm.slice(3, 5))) * 60e3 - KST_MS;
class CalErr extends Error { constructor(code) { super(code); this.code = code; } }
// a fetch whose failures carry a short code only (never the URL — keys live in URLs)
async function getText(url, { timeout = FETCH_MS, accept = '*/*' } = {}) {
  let r;
  try { r = await fetch(url, { headers: { 'user-agent': UA, accept }, signal: AbortSignal.timeout(timeout) }); }
  catch (e) { throw new CalErr(e && e.name === 'TimeoutError' ? 'timeout' : 'network'); }
  if (!r.ok) throw new CalErr('http ' + r.status);
  return await r.text();
}
async function getJson(url, opt) {
  const t = await getText(url, { ...opt, accept: 'application/json' });
  try { return JSON.parse(t); } catch (e) { throw new CalErr('json'); }
}
const errCode = e => (e && e.code) || 'error';
const strip = s => String(s || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
function cells(trHtml) { const out = []; const re = /<td[^>]*>([\s\S]*?)<\/td>/g; let m; while ((m = re.exec(trHtml))) out.push(strip(m[1])); return out; }
function rows(html) { const out = []; const re = /<tr[^>]*>([\s\S]*?)<\/tr>/g; let m; while ((m = re.exec(html))) out.push(cells(m[1])); return out; }
// '2026년 11월 소비자동향조사 결과' → '11월 소비자동향조사 결과' (the year only goes when a month / quarter follows)
const shortTitle = t => t.replace(/^\d{4}년\s+(?=\d{1,2}월|\d\/4분기)/, '');
const hm = s => { const m = /^(\d{1,2}):(\d{2})$/.exec(s || ''); return m ? pad(+m[1]) + ':' + m[2] : null; };

// KV (env.REPLAY) — JSON values, never a key or URL inside
async function kvGet(env, k) { try { return env.REPLAY ? await env.REPLAY.get(k, 'json') : null; } catch (e) { return null; } }
async function kvPut(env, k, v, ttl) { try { if (env.REPLAY) await env.REPLAY.put(k, JSON.stringify(v), ttl ? { expirationTtl: Math.max(60, ttl) } : undefined); } catch (e) { /* the copy stays */ } }

// ───────────────────────── parsers (pure — unit-tested with saved pages) ─────────────────────────
// 한국은행 월간통계 공표일정: <tr><td>2026-11-18</td><td>12:00</td><td class="title">…title…</td><td class="tal">변경일시…</td></tr>
export function parseBok(html, year) {
  const out = [];
  for (const c of rows(html)) {
    if (c.length < 3 || !DATE_RE.test(c[0]) || !hm(c[1])) continue;
    if (year && c[0].slice(0, 4) !== String(year)) continue;           // the page falls back to this year for a year it has not got yet
    out.push({ d: c[0], t: hm(c[1]), title: shortTitle(c[2]), note: c[3] || '' });
  }
  return out;
}
// 국가데이터처 보도계획 (mods.go.kr/newsPln.es?mid=a10305000000&act=list&oa_mm=MM): <h3>2026년 12월 보도계획</h3> + rows 12.02.( 수 ) | 08:00 | title
export function parseKostat(html) {
  const h = /<h3>\s*(\d{4})년\s*(\d{1,2})월\s*보도계획\s*<\/h3>/.exec(html);
  if (!h) return null;
  const y = +h[1], mo = +h[2], out = [];
  for (const c of rows(html)) {
    const m = /^(\d{2})\.(\d{2})\./.exec(c[0] || '');
    if (!m || c.length < 3 || !hm(c[1])) continue;
    const title = c[2];
    if (!KOSTAT_KEEP.test(title)) continue;
    out.push({ d: `${y}-${m[1]}-${m[2]}`, t: hm(c[1]), title: shortTitle(title) });
  }
  return { y, mo, rows: out };
}
// any date written as 2026년 11월 16일 · 2026.11.16 · 2026-11-16 · 20261116 → ['2026-11-16', …] in order
export function datesIn(s) {
  const out = [], re = /(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*일?|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)/g;
  let m;
  while ((m = re.exec(String(s || '')))) {
    const d = m[1] ? `${m[1]}-${pad(m[2])}-${pad(m[3])}` : `${m[4]}-${m[5]}-${m[6]}`;
    if (validDate(d)) out.push(d);
  }
  return out;
}

// ───────────────────────── rules ─────────────────────────
const closedOn = d => KRX_DAYS[d] && KRX_DAYS[d].kind === 'closed';
const isTradingDay = d => wday(d) >= 1 && wday(d) <= 5 && !closedOn(d);
function shiftTrading(d, dir) { let x = d; for (let i = 0; i < 10 && !isTradingDay(x); i++) x = addDays(x, dir); return x; }
function secondThursday(y, mo) { let d = `${y}-${pad(mo)}-01`; let n = 0; for (;;) { if (wday(d) === 4 && ++n === 2) return d; d = addDays(d, 1); } }
// 코스피200 (global.krx.co.kr specs): futures & monthly options = 2nd Thursday (15:20 close); weekly: Monday (holiday → later),
// Thursday except the 2nd (holiday → earlier). A 2nd Thursday on a holiday: moved earlier and marked tentative (rule unconfirmed).
export function expiryEvents(from, to) {
  const out = [];
  let y = +from.slice(0, 4), mo = +from.slice(5, 7);
  for (let i = 0; i < 4; i++) {
    const st = secondThursday(y, mo), d = shiftTrading(st, -1), q = mo % 3 === 0;
    if (d >= from && d <= to) out.push({ id: `rule:exp:${d}`, d, t: '15:20', k: 'mkt', star: q ? 3 : 2, src: 'rule',
      title: q ? '선물 · 옵션 동시만기' : `옵션 만기 (${mo}월물)`, sub: q ? `코스피200 선물 · 옵션 ${mo}월물 마지막 거래일 · 15:20 마감` : '코스피200 옵션 월물 · 둘째 목요일',
      tentative: d !== st ? '휴장이라 앞당김 — 규칙 확인 필요' : undefined });
    mo++; if (mo > 12) { mo = 1; y++; }
  }
  for (let d = addDays(from, -7); d <= addDays(to, 7); d = addDays(d, 1)) {
    const wd = wday(d);
    if (wd === 1) { const x = shiftTrading(d, 1); if (x >= from && x <= to) out.push(wk(x, '월')); }
    if (wd === 4 && d !== secondThursday(+d.slice(0, 4), +d.slice(5, 7))) { const x = shiftTrading(d, -1); if (x >= from && x <= to) out.push(wk(x, '목')); }
  }
  return out;
  function wk(x, w) { return { id: `rule:wk${w === '월' ? 'm' : 't'}:${x}`, d: x, t: null, k: 'mkt', star: 1, src: 'rule', weekly: true, title: `위클리 옵션 만기 (${w})`, sub: `코스피200 ${w}요일물` }; }
}
function cbEvents(from, to) {
  const out = [];
  for (const m of BOK_MEETINGS) {
    if (m.d >= addDays(from, -30) && m.d <= to) {
      if (m.d >= from) out.push({ id: `cb:bok:${m.d}`, d: m.d, t: null, k: 'cb', star: 3, src: 'manual', title: '금통위 통화정책방향 결정', sub: '기준금리 결정', tentative: m.tentative || undefined, url: 'https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=' + m.d.slice(0, 4), val: { ecos: ['한국은행 기준금리'], after: m.d } });
      // 의사록: 회의일로부터 2주 경과 후 첫 화요일 (bok.or.kr note)
      let md = addDays(m.d, 15); while (wday(md) !== 2) md = addDays(md, 1);
      if (md >= from && md <= to) out.push({ id: `cb:bokmin:${md}`, d: md, t: null, k: 'cb', star: 2, src: 'rule', title: '금통위 의사록 공개', sub: `${+m.d.slice(5, 7)}월 ${+m.d.slice(8)}일 회의 · 2주 뒤 첫 화요일`, tentative: '규칙으로 계산' });
    }
  }
  for (const f of FOMC) {
    const k = etToKst(f.d, '14:00');
    if (k.d >= from && k.d <= to) out.push({ id: `cb:fomc:${f.d}`, d: k.d, t: k.t, k: 'cb', star: 3, src: 'manual', title: 'FOMC 금리 결정', sub: f.sep ? '경제전망(SEP) 함께' : undefined, orig: { d: f.d, t: '14:00', tz: 'America/New_York' }, tentative: f.tentative || undefined, url: 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm', at: k.ms, val: { fred: 'fomc' } });
    const md = addDays(f.d, 21), km = etToKst(md, '14:00');       // minutes: three weeks after the decision, 2:00 p.m. ET
    if (km.d >= from && km.d <= to) out.push({ id: `cb:fomcmin:${md}`, d: km.d, t: km.t, k: 'cb', star: 2, src: 'rule', title: 'FOMC 의사록', sub: '결정 3주 뒤', orig: { d: md, t: '14:00', tz: 'America/New_York' }, tentative: '규칙으로 계산' });
  }
  return out;
}

// ───────────────────────── sources: refreshers (each returns the KV snapshot it wrote) ─────────────────────────
const BOK_URL = (y, mo) => `https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldr.do?menuNo=200775&date=${y}-${pad(mo)}`;
const KOSTAT_URL = mo => `https://mods.go.kr/newsPln.es?mid=a10305000000&act=list&oa_mm=${pad(mo)}`;
export const SOURCES = {
  bok: { every: 20 * 3600e3, retry: 30 * 60e3 },
  kostat: { every: 20 * 3600e3, retry: 30 * 60e3 },
  fred: { every: 20 * 3600e3, retry: 30 * 60e3, key: 'FRED_KEY' },
  vals: { every: 30 * 60e3, retry: 15 * 60e3 },
  dart: { every: 30 * 60e3, retry: 15 * 60e3, key: 'DART_KEY' },
  fsc: { every: 3 * 3600e3, retry: 60 * 60e3, key: 'DATA_GO_KR_KEY' },
};

async function bokRefresh(env, now, prev) {
  const y = +kstDate(now).slice(0, 4), mo = +kstDate(now).slice(5, 7);
  const html = await getText(BOK_URL(y, mo));
  let list = parseBok(html, y);
  if (list.length < 20) throw new CalErr('parse');                  // the page changed shape: keep the last good copy
  if (mo >= 11) { try { list = list.concat(parseBok(await getText(BOK_URL(y + 1, 1)), y + 1)); } catch (e) { /* next year: later */ } }
  // keep last year's rows from the previous copy (a January page has no December)
  const keep = ((prev && prev.rows) || []).filter(r => r.d < `${y}-01-01` && r.d >= addDays(kstDate(now), -400));
  return { rows: keep.concat(list) };
}
async function kostatRefresh(env, now, prev) {
  const mo = +kstDate(now).slice(5, 7);
  const months = [mo]; if (mo < 12) months.push(mo + 1);              // the page only serves this year's months
  const got = [];
  for (const m of months) {
    const p = parseKostat(await getText(KOSTAT_URL(m)));
    if (!p) throw new CalErr('parse');
    got.push(p);
  }
  const fresh = new Set(got.map(p => `${p.y}-${pad(p.mo)}`));
  const keep = ((prev && prev.rows) || []).filter(r => !fresh.has(r.d.slice(0, 7)) && r.d >= addDays(kstDate(now), -400));
  return { rows: keep.concat(...got.map(p => p.rows)).sort((a, b) => a.d.localeCompare(b.d)) };
}
async function fredRefresh(env, now) {
  const key = env.FRED_KEY;
  if (!key) throw new CalErr('no key');
  const start = addDays(kstDate(now), -60), out = [];
  const ids = Object.keys(FRED_REL);
  const res = await Promise.allSettled(ids.map(id => getJson(`https://api.stlouisfed.org/fred/release/dates?release_id=${id}&file_type=json&realtime_start=${start}&realtime_end=9999-12-31&include_release_dates_with_no_data=true&sort_order=asc&limit=400&api_key=${encodeURIComponent(key)}`)));
  let ok = 0;
  res.forEach((r, i) => {
    if (r.status !== 'fulfilled') return;
    ok++;
    for (const x of (r.value && r.value.release_dates) || []) if (validDate(x.date) && x.date >= start) out.push({ rid: +ids[i], d: x.date });
  });
  if (!ok) throw new CalErr(res[0] && res[0].reason ? errCode(res[0].reason) : 'error');
  return { rows: out, partial: ok < ids.length ? ids.length - ok : undefined };
}

// values after a release: ECOS KeyStatisticList (one call, 101 rows) + FRED observations for releases that passed without a value
const fmtNum = (v, dp) => (+v).toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
export function fmtVal(spec, v) {
  if (v == null || v === '.' || !isFinite(+v)) return null;
  const n = +v;
  if (spec.f === 'pct') return `${spec.l} ${n > 0 ? '+' : n < 0 ? '−' : ''}${fmtNum(Math.abs(n), 1)}%`;
  if (spec.f === 'rate') return `${spec.l} ${fmtNum(n, 1)}%`;
  if (spec.f === 'num') return `${spec.l} ${fmtNum(n, 1)}`;
  if (spec.f === 'man') {
    const x = n * (spec.m || 1) / 1e4, s = spec.sign && x > 0 ? '+' : x < 0 ? '−' : '';
    return `${spec.l} ${s}${fmtNum(Math.abs(x), Math.abs(x) >= 100 ? 0 : 1)}만 ${spec.unit || ''}`.trim();
  }
  return String(n);
}
const PERIOD_RE = /(\d{4})년\s*(?:(\d{1,2})월|(\d)\/4분기|(\d)분기)/;
// the period a title talks about → ECOS CYCLE ('202610' | '2026Q3'); null when the title has none
export function periodOf(title, d) {
  const m = PERIOD_RE.exec(title || '');
  if (m) return m[2] ? m[1] + pad(m[2]) : m[1] + 'Q' + (m[3] || m[4]);
  const t = /^(\d{1,2})월 /.exec(title || ''), q = /^(\d)\/4분기/.exec(title || '');
  if (t && d) { const y = +d.slice(0, 4), mo = +t[1]; return (mo > +d.slice(5, 7) ? y - 1 : y) + pad(mo); }
  if (q && d) { const y = +d.slice(0, 4), n = +q[1]; return (n * 3 > +d.slice(5, 7) ? y - 1 : y) + 'Q' + n; }
  return null;
}
function ecosText(row) {
  const v = +row.DATA_VALUE; if (row.DATA_VALUE == null || row.DATA_VALUE === '' || !isFinite(v)) return null;
  const u = String(row.UNIT_NAME || '').trim(), n = v.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
  const val = u === '%' ? n + '%' : !u || u === 'None' ? n : /=/.test(u) ? `${n} (${u})` : `${n} ${u}`;
  return `${String(row.KEYSTAT_NAME || '').replace(/\(.*?\)/g, '').trim()} ${val}`;
}
async function valsRefresh(env, now, prev, ctx2) {
  const want = ctx2 && ctx2.want ? ctx2.want : { ecos: false, fred: [] };
  const out = { ecos: (prev && prev.ecos) || null, fred: Object.assign({}, (prev && prev.fred) || {}) };
  let any = false, fails = 0;
  if (want.ecos && env.ECOS_KEY) {
    try {
      const j = await getJson(`https://ecos.bok.or.kr/api/KeyStatisticList/${encodeURIComponent(env.ECOS_KEY)}/json/kr/1/120`);
      const r = j && j.KeyStatisticList && j.KeyStatisticList.row;
      if (!Array.isArray(r) || !r.length) throw new CalErr('ecos empty');
      out.ecos = { at: now, rows: r.map(x => ({ n: String(x.KEYSTAT_NAME || ''), c: String(x.CYCLE || ''), text: ecosText(x) })).filter(x => x.text) };
      any = true;
    } catch (e) { fails++; }
  }
  if (want.fred.length && env.FRED_KEY) {
    for (const job of want.fred.slice(0, 8)) {                                   // ≤ 8 release values per refresh
      try {
        const specs = job.rid === 'fomc' ? FOMC_VALS : FRED_REL[job.rid].vals;
        const got = [];
        for (const sp of specs) {
          const j = await getJson(`https://api.stlouisfed.org/fred/series/observations?series_id=${sp.s}&units=${sp.u}&sort_order=desc&limit=1&file_type=json&api_key=${encodeURIComponent(env.FRED_KEY)}`);
          const o = j && j.observations && j.observations[0];
          if (!o || o.value === '.') throw new CalErr('fred empty');
          got.push({ p: o.date, v: o.value });
        }
        const prevSame = Object.values(out.fred).find(x => x && x.rid === job.rid && x.d < job.d && x.p === got[0].p);
        if (job.rid !== 'fomc' && prevSame) continue;                           // FRED has not caught up with this release yet
        const text = job.rid === 'fomc' ? `목표 범위 ${fmtNum(+got[0].v, 2)}~${fmtNum(+got[1].v, 2)}%` : specs.map((sp, i) => fmtVal(sp, got[i].v)).filter(Boolean).join(' · ');
        out.fred[`${job.rid}:${job.d}`] = { rid: job.rid, d: job.d, p: got[0].p, text };
        any = true;
      } catch (e) { fails++; }
    }
    // keep 120 days
    for (const k of Object.keys(out.fred)) if (out.fred[k].d < addDays(kstDate(now), -120)) delete out.fred[k];
  }
  if (!any && fails) throw new CalErr('values');
  return out;
}

// OpenDART: 무상 · 유상증자 schedules. Per KST day: list.json B001 (주요사항보고서) and C001 (증권신고 지분증권), both markets.
const DART = 'https://opendart.fss.or.kr/api/';
const ymd = d => d.replace(/-/g, '');
async function dartJson(env, path, params, st) {
  if (st.calls >= st.cap) throw new CalErr('cap');
  st.calls++;
  const q = new URLSearchParams(params).toString();
  const j = await getJson(`${DART}${path}?crtfc_key=${encodeURIComponent(env.DART_KEY)}&${q}`, { timeout: 6000 });
  if (j.status === '013') return { list: [] };
  if (j.status !== '000') throw new CalErr('dart ' + String(j.status).replace(/\D/g, '').slice(0, 3));
  return j;
}
const CAP_RE = { fric: /주요사항보고서\(무상증자결정\)/, pifric: /주요사항보고서\(유무상증자결정\)/, estk: /증권신고서\(지분증권\)/ };
async function dartRefresh(env, now, prev) {
  if (!env.DART_KEY) throw new CalErr('no key');
  const cool = await kvGet(env, 'dart:cool');                        // §3-29: the 공시 배지's cool-down applies to the same key
  if (cool && cool.until && cool.until > now) throw new CalErr('cool');
  const today = kstDate(now), day = ymd(today);
  const callsKey = 'cal:dart:calls:' + day;
  const st = { calls: 0, cap: DART_DAY_CAP - (((await kvGet(env, callsKey)) || {}).n || 0) };
  const scanned = Object.assign({}, (prev && prev.scanned) || {});
  const filings = Object.assign({}, (prev && prev.filings) || {});       // rcept_no → {c, n, kind, rd, title}
  const evs = Object.assign({}, (prev && prev.evs) || {});               // rcept_no → [events]
  const days = [today];
  for (let i = 1, n = 0; i <= DART_BACK_DAYS && n < DART_DAYS_PER_RUN; i++) { const d = addDays(today, -i); if (!scanned[d] && wday(d) >= 1 && wday(d) <= 5) { days.push(d); n++; } }
  let err = null;
  try {
    for (const d of days) {
      for (const ty of ['B001', 'C001']) for (const cls of ['Y', 'K']) {
        for (let page = 1; page <= 3; page++) {
          const j = await dartJson(env, 'list.json', { bgn_de: ymd(d), end_de: ymd(d), pblntf_detail_ty: ty, corp_cls: cls, page_no: page, page_count: 100 }, st);
          for (const x of j.list || []) {
            const t = String(x.report_nm || '').replace(/\s+/g, ' ').trim();
            const kind = CAP_RE.pifric.test(t) ? 'pifric' : CAP_RE.fric.test(t) ? 'fric' : CAP_RE.estk.test(t) ? 'estk' : null;
            if (!kind || !/^\d{6}$/.test(x.stock_code || '') || filings[x.rcept_no]) continue;
            filings[x.rcept_no] = { c: x.stock_code, n: String(x.corp_name || '').trim(), corp: x.corp_code, kind, rd: x.rcept_dt, title: t };
          }
          if (!j.total_page || page >= +j.total_page) break;
        }
      }
      if (d !== today) scanned[d] = 1;
    }
    // details for filings not read yet (newest first)
    const todo = Object.keys(filings).filter(r => !evs[r]).sort().reverse().slice(0, 30);
    for (const r of todo) {
      const f = filings[r];
      const api = f.kind === 'fric' ? 'fricDecsn.json' : f.kind === 'pifric' ? 'pifricDecsn.json' : 'estkRs.json';
      const j = await dartJson(env, api, { corp_code: f.corp, bgn_de: ymd(addDays(`${f.rd.slice(0, 4)}-${f.rd.slice(4, 6)}-${f.rd.slice(6, 8)}`, -90)), end_de: f.rd }, st);   // bgn/end = 최초접수일: a 정정 sits under the first filing's day
      evs[r] = dartEvents(f, r, j);
    }
  } catch (e) { err = e; }
  await kvPut(env, callsKey, { n: (DART_DAY_CAP - st.cap) + st.calls }, 2 * 86400);
  // forget what is long past
  const old = addDays(today, -DART_BACK_DAYS - 5);
  for (const d of Object.keys(scanned)) if (d < old) delete scanned[d];
  for (const r of Object.keys(filings)) if (filings[r].rd < ymd(old)) { delete filings[r]; delete evs[r]; }
  if (err && !Object.keys(filings).length && !(prev && prev.evs)) throw err;
  return { scanned, filings, evs, partial: err ? errCode(err) : undefined, calls: st.calls };
}
// one filing's answer → events (pure, unit-tested)
export function dartEvents(f, rcept, j) {
  const out = [], base = { k: 'corp', src: 'dart', c: f.c, n: f.n, r: rcept, url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + rcept };
  const list = (j && j.list) || [];
  if (f.kind === 'fric' || f.kind === 'pifric') {
    const x = list.find(y => y.rcept_no === rcept) || list[list.length - 1];
    if (!x) return out;
    const p = f.kind === 'pifric' ? 'fric_' : '';
    const asstd = datesIn(x[p + 'nstk_asstd'])[0], lst = datesIn(x[p + 'nstk_lstprd'])[0], per = x[p + 'nstk_ascnt_ps_ostk'];
    const sub = per && isFinite(+String(per).replace(/,/g, '')) ? `1주당 ${+(+String(per).replace(/,/g, '')).toFixed(4)}주` : undefined;
    if (asstd) out.push({ ...base, id: `dart:${rcept}:asstd`, d: asstd, t: null, star: 2, title: '무상증자 신주배정기준일', sub, api: 'fricDecsn' });
    if (lst) out.push({ ...base, id: `dart:${rcept}:lst`, d: lst, t: null, star: 1, title: '무상증자 신주 상장', sub, api: 'fricDecsn' });
  } else {
    const groups = Array.isArray(j && j.group) ? j.group : [];
    const g = groups.find(x => /일반사항/.test(x.title || '')) || groups[0];
    const x = g && Array.isArray(g.list) ? (g.list.find(y => y.rcept_no === rcept) || g.list[0]) : null;
    if (!x) return out;
    const sbd = datesIn(x.sbd), pym = datesIn(x.pymd)[0], asstd = datesIn(x.asstd)[0];
    const sub = [sbd[1] && sbd[1] !== sbd[0] ? `청약 ~${+sbd[1].slice(5, 7)}/${+sbd[1].slice(8)}` : null, pym ? `납입 ${+pym.slice(5, 7)}/${+pym.slice(8)}` : null].filter(Boolean).join(' · ') || undefined;
    if (sbd[0]) out.push({ ...base, id: `dart:${rcept}:sbd`, d: sbd[0], t: null, star: 1, title: '유상증자 청약', sub, api: 'estkRs' });
    if (asstd) out.push({ ...base, id: `dart:${rcept}:asstd`, d: asstd, t: null, star: 1, title: '유상증자 배정기준일', api: 'estkRs' });
  }
  return out;
}

// 금융위 (data.go.kr) — 배당 · 보호예수 · 권리일정. OFF until the shared helper is wired: configureCalendar({ fsc: { list, codeOfCrno } })
// list(apiId 'divi'|'issu'|'rights', op, params) → Promise<items[]> (the helper counts calls, pages and keeps the key out of errors);
// codeOfCrno(env, crno) → Promise<'005930'|null>. Gate: env.CAL_FSC === 'on'.
const FSC = { list: null, codeOfCrno: null };
export function configureCalendar(o) { if (o && o.fsc) Object.assign(FSC, o.fsc); }
export const fscEnabled = env => env.CAL_FSC === 'on' && typeof FSC.list === 'function' && !!env.DATA_GO_KR_KEY;
const isinCode = isin => /^KR7(\d{6})\d{3}$/.test(isin || '') ? isin.slice(3, 9) : null;
async function fscRefresh(env, now) {
  if (!fscEnabled(env)) throw new CalErr('off');
  const basDt = ymd(expectedBasDt(now)), evs = [];
  const parts = await Promise.allSettled([
    FSC.list('divi', 'getDiviInfo_V2', { basDt }),
    FSC.list('issu', 'getLockUpRetuInfo_V3', { basDt }),
    FSC.list('rights', 'getRighExerReasSche_V2', { basDt }),
  ]);
  const [divi, lock, rights] = parts.map(p => p.status === 'fulfilled' && Array.isArray(p.value) ? p.value : null);
  if (!divi && !lock && !rights) throw new CalErr('fsc');
  for (const x of divi || []) evs.push(...fscDivEvents(x));
  const pctCache = new Map();
  for (const x of lock || []) {
    const c = isinCode(x.isinCd) || (/^A?\d{6}$/.test(x.itmsShrtnCd || '') ? x.itmsShrtnCd.slice(-6) : null), d = datesIn(x.rsrnDt)[0];
    if (!c || !d) continue;
    let pct = null;
    if (x.crno) {
      if (!pctCache.has(x.crno)) pctCache.set(x.crno, FSC.list('issu', 'getStocIssuStat_V3', { basDt, crno: x.crno }).then(r => r && r[0]).catch(() => null));
      const s = await pctCache.get(x.crno), tot = s && +(/우선/.test(x.scrsItmsKcdNm || '') ? s.pfstTisuCnt : s.onskTisuCnt);
      if (tot > 0 && +x.rsrnStckCnt > 0) pct = Math.round(+x.rsrnStckCnt / tot * 1000) / 10;
    }
    evs.push({ id: `fsc:lock:${c}:${d}:${x.lkupRegDt || ''}`, d, t: null, k: 'corp', src: 'fsc', api: 'getLockUpRetuInfo_V3', c, n: strip(x.stckIssuCmpyNm),
      star: pct == null ? 1 : pct >= 10 ? 3 : pct >= 3 ? 2 : 1, pct: pct == null ? undefined : pct,
      title: `보호예수 해제 ${fmtShares(+x.rsrnStckCnt)}`, sub: [pct != null ? `상장주식의 ${pct}%` : null, strip(x.stckLblHoldRcdNm) || null].filter(Boolean).join(' · ') || undefined });
  }
  for (const x of rights || []) {
    const c = FSC.codeOfCrno && x.crno ? await FSC.codeOfCrno(env, x.crno) : null;
    if (!c) continue;
    const why = strip(x.rgtExertRcdNm) || '권리', a = datesIn(x.nmlsLckSttgDt)[0], b = datesIn(x.nmlsLckEdDt)[0];
    if (a) evs.push({ id: `fsc:rights:${c}:${a}:${x.rgtExertRcd || ''}`, d: a, t: null, k: 'corp', src: 'fsc', api: 'getRighExerReasSche_V2', c, n: strip(x.stckIssuCmpyNm), star: 1,
      title: `${why} 명부폐쇄`, sub: b && b !== a ? `~${+b.slice(5, 7)}/${+b.slice(8)}` : undefined, why });
  }
  return { evs, basDt, partial: parts.some(p => p.status !== 'fulfilled') || undefined };
}
export function fscDivEvents(x) {
  const c = isinCode(x.isinCd); if (!c) return [];
  const amt = +String(x.stckGenrDvdnAmt || '').replace(/,/g, ''), n = strip(x.stckIssuCmpyNm), out = [];
  const pref = /우선/.test(x.scrsItmsKcdNm || '') ? ' (우선주)' : '';
  const sub = amt > 0 ? `1주당 ${amt.toLocaleString('ko-KR')}원${pref}` : pref.trim() || undefined;
  const bd = datesIn(x.dvdnBasDt)[0], pd = datesIn(x.cashDvdnPayDt)[0];
  if (bd) out.push({ id: `fsc:divrec:${c}:${bd}`, d: bd, t: null, k: 'corp', src: 'fsc', api: 'getDiviInfo_V2', c, n, star: 1, title: '배당 기준일', sub, grp: 'div-rec' });
  if (pd) out.push({ id: `fsc:divpay:${c}:${pd}`, d: pd, t: null, k: 'corp', src: 'fsc', api: 'getDiviInfo_V2', c, n, star: 1, title: '배당금 지급', sub, grp: 'div-pay' });
  return out;
}
const fmtShares = n => !(n > 0) ? '' : n >= 1e4 ? `${(n / 1e4).toLocaleString('ko-KR', { maximumFractionDigits: n >= 1e6 ? 0 : 1 })}만 주` : `${n.toLocaleString('ko-KR')}주`;
// the 금융위 basDt that should be loaded by now: the last weekday whose data is out (next business day 13:00 KST)
function expectedBasDt(now) {
  let d = kstDate(now - 13 * 3600e3);                  // before 13:00 → still yesterday's view
  d = addDays(d, -1);
  while (!isTradingDay(d)) d = addDays(d, -1);
  return d;
}

// ───────────────────────── refresh orchestration ─────────────────────────
const RUN = { bok: bokRefresh, kostat: kostatRefresh, fred: fredRefresh, vals: valsRefresh, dart: dartRefresh, fsc: fscRefresh };
const inflight = new Map();
export function calKey(id) { return 'cal:' + id; }
async function refreshOne(env, id, now, prev, extra) {
  if (inflight.has(id)) return inflight.get(id);
  const p = (async () => {
    const lock = await kvGet(env, 'cal:lock:' + id);
    if (lock && lock.until > now) return prev;
    await kvPut(env, 'cal:lock:' + id, { until: now + LOCK_S * 1000 }, LOCK_S);
    let snap;
    try {
      const body = await RUN[id](env, now, prev && prev.data, extra);
      snap = { at: now, ok: true, data: body, tried: now };
    } catch (e) {
      snap = Object.assign({}, prev || { data: null }, { ok: false, tried: now, err: errCode(e) });   // the last good data stays
      if (id !== 'fsc' || errCode(e) !== 'off') console.log(`calendar ${id}: ${errCode(e)}`);
    }
    await kvPut(env, calKey(id), snap, 400 * 86400);
    return snap;
  })().finally(() => inflight.delete(id));
  inflight.set(id, p);
  return p;
}
function due(id, snap, now) {
  const s = SOURCES[id];
  if (!snap) return true;
  if (snap.ok === false) return now - (snap.tried || 0) > s.retry;
  let every = s.every;
  if (id === 'dart') { const h = +kstHm(now).slice(0, 2), d = kstDate(now); if (!(isTradingDay(d) && h >= 7 && h < 20)) every = 3 * 3600e3; }
  return now - (snap.at || 0) > every;
}

// ───────────────────────── assemble ─────────────────────────
export function starKr(title) { const r = KR_RULES.find(x => x.re.test(title)); return r ? r.star : 1; }
function krRule(title) { return KR_RULES.find(x => x.re.test(title)) || null; }
export function buildEvents(from, to, snaps, now) {
  const ev = [];
  const push = e => { if (e.d >= from && e.d <= to) ev.push(Object.assign({}, e)); };
  const bok = snaps.bok && snaps.bok.data, kostat = snaps.kostat && snaps.kostat.data, fred = snaps.fred && snaps.fred.data;
  const vals = (snaps.vals && snaps.vals.data) || {}, dart = snaps.dart && snaps.dart.data, fsc = snaps.fsc && snaps.fsc.data;
  for (const [src, data] of [['bok', bok], ['kostat', kostat]]) for (const r of (data && data.rows) || []) {
    const rule = krRule(r.title);
    push({ id: `${src}:${r.d}:${r.title}`, d: r.d, t: r.t, k: 'kr', star: rule ? rule.star : 1, src, title: r.title, note: r.note || undefined,
      at: kstMs(r.d, r.t), val: rule && rule.ecos ? { ecos: rule.ecos, period: periodOf(r.title, r.d) } : undefined });
  }
  for (const r of (fred && fred.rows) || []) {
    const rel = FRED_REL[r.rid]; if (!rel) continue;
    const k = rel.et ? etToKst(r.d, rel.et) : { d: r.d, t: null, ms: dUTC(r.d) + DAY_MS };
    push({ id: `fred:${r.rid}:${r.d}`, d: k.d, t: k.t, k: 'us', star: rel.star, src: 'fred', rid: r.rid, title: rel.title, sub: rel.sub,
      orig: rel.et ? { d: r.d, t: rel.et, tz: 'America/New_York' } : { d: r.d, t: null, tz: 'America/New_York' }, at: k.ms, val: { fred: r.rid, d: r.d } });
  }
  cbEvents(from, to).forEach(push);
  expiryEvents(from, to).forEach(push);
  // corp: DART first, then 금융위 (dedupe: same stock · same day · same kind of thing)
  const seen = new Set();
  const latest = new Map();                       // an original filing and its 정정: the newest 접수번호 wins per stock · event
  for (const list of Object.values((dart && dart.evs) || {})) for (const e of list) { const k = e.c + '|' + e.title; if (!latest.has(k) || latest.get(k).r < e.r) latest.set(k, e); }
  for (const e of latest.values()) { push(e); seen.add(`${e.c}:${e.d}:${/무상/.test(e.title) ? 'fric' : 'x'}`); }
  for (const e of (fsc && fsc.evs) || []) {
    if (e.api === 'getRighExerReasSche_V2') {
      if (/무상/.test(e.why || '') && [-3, -2, -1, 0, 1, 2, 3].some(k => seen.has(`${e.c}:${addDays(e.d, k)}:fric`))) continue;
      if (/배당/.test(e.why || '') && (fsc.evs || []).some(x => x.grp === 'div-rec' && x.c === e.c && Math.abs(dUTC(x.d) - dUTC(e.d)) <= 3 * DAY_MS)) continue;
    }
    push(e);
  }
  // values after the release (text only — the page never colours them)
  for (const e of ev) {
    const v = e.val; delete e.val;
    if (!v) continue;
    if (v.ecos && vals.ecos && vals.ecos.rows) {
      const hit = v.ecos.map(n => vals.ecos.rows.find(x => x.n === n)).filter(x => x && (v.period ? x.c === v.period : v.after && x.c.length === 8 && x.c >= ymd(v.after)));
      if (hit.length && (!e.at || now >= e.at)) e.value = { text: hit.map(x => x.text).join(' · '), src: 'ecos', p: hit[0].c };
    } else if (v.fred != null && vals.fred) {
      const key = v.fred === 'fomc' ? `fomc:${e.orig.d}` : `${v.fred}:${v.d}`, x = vals.fred[key];
      if (x && x.text) e.value = { text: x.text, src: 'fred', p: x.p };
    }
    if (e.at == null) delete e.at;
  }
  ev.sort((a, b) => a.d.localeCompare(b.d) || (a.t || '').localeCompare(b.t || '') || b.star - a.star || a.id.localeCompare(b.id));
  for (const e of ev) delete e.at;
  return ev;
}
// what values are still missing for releases that already happened (feeds the vals refresher)
function valuesWanted(snaps, now) {
  const from = addDays(kstDate(now), -21), to = kstDate(now);
  const evs = buildEvents(from, to, Object.assign({}, snaps, { vals: snaps.vals }), now);
  const want = { ecos: false, fred: [] };
  for (const e of evs) {
    if (e.value) continue;
    const at = e.t ? kstMs(e.d, e.t) : dUTC(e.d) + DAY_MS - KST_MS, ago = now - at;
    // ECOS: from 10 min after, for 20 days (its 100 key figures carry their own period, matched per event)
    // FRED: from 60 min after (time to post), for 7 days — the newest observation belongs to the newest release only
    const ecosOk = ago >= 10 * 60e3 && ago <= 20 * DAY_MS, fredOk = ago >= 60 * 60e3 && ago <= 7 * DAY_MS;
    if (ecosOk && e.k === 'kr' && krRule(e.title) && krRule(e.title).ecos) want.ecos = true;
    if (ecosOk && e.id.startsWith('cb:bok:')) want.ecos = true;
    if (fredOk && e.src === 'fred') want.fred.push({ rid: e.rid, d: e.orig.d });
    if (fredOk && e.id.startsWith('cb:fomc:')) want.fred.push({ rid: 'fomc', d: e.orig.d });
  }
  // only the latest passed release of each series: FRED serves the newest observation, which belongs to that release alone
  const latest = new Map();
  for (const j of want.fred) if (!latest.has(j.rid) || latest.get(j.rid).d < j.d) latest.set(j.rid, j);
  want.fred = [...latest.values()].sort((a, b) => b.d.localeCompare(a.d));
  return want;
}
// many company rows of one kind on one day (결산 배당 기준일) → one group row; the page lists the codes when opened
export function groupCorp(events, max = 12) {
  const by = new Map();
  for (const e of events) if (e.k === 'corp' && e.grp) { const k = e.d + '|' + e.grp; by.set(k, (by.get(k) || 0) + 1); }
  const groups = [], out = [];
  const big = new Set([...by].filter(([, n]) => n > max).map(([k]) => k));
  const gl = new Map();
  for (const e of events) {
    const k = e.grp ? e.d + '|' + e.grp : null;
    if (k && big.has(k)) {
      if (!gl.has(k)) { const g = { id: `grp:${e.grp}:${e.d}`, d: e.d, t: null, k: 'corp', src: e.src, star: 2, title: e.title, grp: e.grp, n: 0, codes: [] }; gl.set(k, g); groups.push(g); out.push(g); }
      const g = gl.get(k); g.n++; g.codes.push(e.c);
    } else out.push(e);
  }
  for (const g of groups) g.sub = `${g.n}개 종목`;
  return out;
}
const SRC_NAME = { bok: '한국은행 통계공표일정', kostat: '국가데이터처 보도계획', fred: 'FRED 발표 일정', vals: '발표값(ECOS · FRED)', dart: 'OpenDART', fsc: '금융위원회' };

export async function buildAnswer(env, ctx, from, to, kinds, now) {
  const ids = Object.keys(SOURCES);
  const snaps = Object.fromEntries(await Promise.all(ids.map(async id => [id, await kvGet(env, calKey(id))])));
  // refresh what is due: the first ever copy is awaited (bounded), the rest runs after the answer
  const wait = [];
  for (const id of ids) {
    if (id === 'fsc' && !fscEnabled(env)) continue;
    if (SOURCES[id].key && !env[SOURCES[id].key]) continue;
    if (id === 'vals') continue;
    if (!due(id, snaps[id], now)) continue;
    const p = refreshOne(env, id, now, snaps[id]).then(s => { snaps[id] = s; });
    if (!snaps[id]) wait.push(p); else if (ctx && ctx.waitUntil) ctx.waitUntil(p);
  }
  if (wait.length) await Promise.race([Promise.allSettled(wait), new Promise(r => setTimeout(r, 9000))]);
  if ((env.ECOS_KEY || env.FRED_KEY) && due('vals', snaps.vals, now)) {
    const want = valuesWanted(snaps, now);
    if (want.ecos || want.fred.length) {
      const p = refreshOne(env, 'vals', now, snaps.vals, { want }).then(s => { snaps.vals = s; });
      if (ctx && ctx.waitUntil) ctx.waitUntil(p); else await p;
    }
  }
  let events = buildEvents(from, to, snaps, now);
  if (kinds) events = events.filter(e => kinds.has(e.k));
  events = groupCorp(events);
  const days = {};
  for (let d = from; d <= to; d = addDays(d, 1)) if (KRX_DAYS[d]) days[d] = Object.assign({}, KRX_DAYS[d]);
  const sources = {};
  for (const id of ids) {
    const s = snaps[id], off = (id === 'fsc' && !fscEnabled(env)) || (SOURCES[id].key && !env[SOURCES[id].key]);
    sources[id] = { name: SRC_NAME[id], ok: !!(s && s.ok !== false && s.data), at: s && s.at ? new Date(s.at + KST_MS).toISOString().slice(0, 16).replace('T', ' ') : null };
    if (off) sources[id].off = true;
    if (s && s.ok === false && !off) sources[id].err = s.err;
  }
  const stale = ids.some(id => !sources[id].off && sources[id].ok === false && id !== 'vals');
  return { asOf: new Date(now + KST_MS).toISOString().slice(0, 19) + '+09:00', from, to, tz: 'Asia/Seoul', days, events, sources, stale: stale || undefined, manual: '2026-11-15' };
}

// ───────────────────────── route ─────────────────────────
const KINDS = ['kr', 'us', 'cb', 'mkt', 'corp'];
function jsonRes(obj, status = 200, cache) {
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': ORIGIN, 'cache-control': cache || 'no-store' } });
}
export async function calendarRoute(request, env, ctx, url, nowMs) {
  env = env || {};
  const now = nowMs || Date.now(), today = kstDate(now);
  const q = url.searchParams;
  const mon = addDays(today, -((wday(today) + 6) % 7));
  const from = q.get('from') || mon, to = q.get('to') || addDays(from, 13);
  if (!validDate(from) || !validDate(to)) return jsonRes({ error: 'from · to는 YYYY-MM-DD 형식이어야 해요' }, 400);
  if (to < from) return jsonRes({ error: 'to가 from보다 빠를 수 없어요' }, 400);
  if ((dUTC(to) - dUTC(from)) / DAY_MS + 1 > MAX_SPAN) return jsonRes({ error: `한 번에 ${MAX_SPAN}일까지 받을 수 있어요` }, 400);
  if (from < addDays(today, -400) || to > addDays(today, 400)) return jsonRes({ error: '오늘 앞뒤 400일 안에서만 볼 수 있어요' }, 400);
  let kinds = null;
  if (q.get('kinds') != null) {
    const ks = q.get('kinds').split(',').map(s => s.trim()).filter(Boolean);
    if (!ks.length || !ks.every(k => KINDS.includes(k))) return jsonRes({ error: 'kinds는 kr, us, cb, mkt, corp 중에서 쉼표로 골라요' }, 400);
    kinds = new Set(ks);
  }
  const cacheKey = new Request(`https://panse-cal.internal/v1?from=${from}&to=${to}&k=${kinds ? [...kinds].sort().join(',') : 'all'}`);
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null;
  if (cache) { try { const hit = await cache.match(cacheKey); if (hit) return hit; } catch (e) { /* no cache */ } }
  let body;
  try { body = await buildAnswer(env, ctx, from, to, kinds, now); }
  catch (e) { console.log('calendar: ' + errCode(e)); return jsonRes({ error: '일정을 만들지 못했어요' }, 502); }
  const res = jsonRes(body, 200, `public, max-age=60, s-maxage=${CAL_TTL}, stale-while-revalidate=${CAL_TTL}`);
  if (cache) { try { const p = cache.put(cacheKey, res.clone()); if (ctx && ctx.waitUntil) ctx.waitUntil(p); } catch (e) { /* fine */ } }
  return res;
}
