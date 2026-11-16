/* 해외 지수 · 원자재 tabs (AGENTS.md §3-4).
   window.KHWorld = { show(kind), hide(), layout(), shown(), view(), openDetail(key, opts), detailOpen(), zones() }   kind: 'index' | 'commodity'
   The template shows <div id="world"> (in place of the map + side cards) and calls show(); another tab calls hide().
   Data (live only): GET api/world?kind=…  every 30 s while shown and the browser tab is visible (지표 = kind=commodity&with=fx,rates);
                     GET api/world/chart/{key}?tf=3m|1y for the detail sheet (daily closes; no intraday source exists).
                     지표 also: GET api/funds (증시 자금, 금융투자협회 — once a day upstream, asked here at most every 10 min) and
                     api/funds/chart/{key}?tf=3m|1y; an older Worker without the route → the group is simply absent (AGENTS §3-32).
                     지표 also: GET api/koreaexim?kind=fx|rate (수출입은행 고시 — once a business day, asked here at most every 10 min):
                     two small tables inside the 환율 and 금리 cards (AGENTS §3-27 끝).
   Uses window.KH (§3): MODE, LIVE_URL, colorOf, palette, fmt, h, market; listens to kh:palette.
   등락 색상 (2026-11-16): everything here is a 해외 · 지표 value, so colours ask KH.colorOf(r, 'world') / KH.palette('world') (an older
   template ignores the argument) and the boxes carry .pal-w (#world from the template, the detail sheet here). The one exception: a
   코스피 / 코스닥 sheet opened from the ticker or the dock (openDetail(key, {scope: 'kr'})) is a 국내 value and keeps 국내 colours. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function') return;          // the heatmap script did not boot
const h = KH.h;
const LIVE = KH.MODE === 'live';
const MINUS = '−';
const POLL_MS = 30000, RETRY_MS = 15000, TIMEOUT_MS = 12000;
const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
const narrowMQ = matchMedia('(max-width: 760px)');
const SVGNS = 'http://www.w3.org/2000/svg';
// theme colours (themes.md §15-4): read from the CSS tokens, cached until the theme or palette changes (restyle())
let TOK = null;
const tokVal = (cs, name, fb) => (cs.getPropertyValue(name) || '').trim() || fb;
function tok() {
  if (TOK) return TOK;
  const cs = getComputedStyle(document.getElementById('world') || document.documentElement);
  const de = document.documentElement;
  const theme = typeof KH.theme === 'function' ? KH.theme() : de.dataset.theme;
  TOK = {
    nodata: tokVal(cs, '--nodata', '#26282e'), ref: tokVal(cs, '--kw-ref', '#30333b'), sec: tokVal(cs, '--sec-bg', '#000'),
    // light themes (paper, glass light): tile and chip text is black or white, whichever reads better on the tile, with no shadow
    light: de.dataset.tone ? de.dataset.tone === 'light' : theme === 'paper' || theme === 'glass-light',
  };
  return TOK;
}

const CM_NAME = (KH.MKT_NAME && KH.MKT_NAME.CMDTY) || '지표';
const KINDS = {
  index: {
    title: '해외 지수', hash: 'world', noun: '지수',
    fail: '해외 지수를 불러오지 못했어요', empty: '지금 보여 줄 해외 지수가 없어요',
    snapTitle: '해외 지수는 실시간 버전에서 볼 수 있어요',
    snapBody: '미국·유럽·아시아 주요 지수와 미국 지수 선물을 30초마다 새로 받아 와요. 이 미리보기는 네트워크가 막혀 있어서 시세를 받을 수 없어요.',
  },
  // the 지표 tab: 원자재 + 환율 + 금리 (AGENTS §3-28). Its name is the template's MKT_NAME.CMDTY — one place for the tab button,
  // this module and extras (user 2026-11-13 23:20: "지표"). Copy below avoids a particle right after the name.
  commodity: {
    title: CM_NAME, hash: 'cmdty', noun: CM_NAME,
    fail: `${CM_NAME} 탭의 시세를 불러오지 못했어요`, empty: '지금 보여 줄 원자재·환율·금리 시세가 없어요',
    snapTitle: `${CM_NAME} 탭은 실시간 버전에서 볼 수 있어요`,
    snapBody: '원유·금·곡물 같은 원자재 선물과 환율·국채 금리를 30초마다, 증시 자금(금융투자협회)과 수출입은행 고시는 하루 한 번 새로 받아 와요. 이 미리보기는 네트워크가 막혀 있어서 시세를 받을 수 없어요.',
  },
};
// what each tab asks the Worker for: the 지표 tab adds 환율 · 금리 (an older Worker ignores `with` and the groups are simply absent)
const WORLD_Q = { index: 'kind=index', commodity: 'kind=commodity&with=fx,rates' };
const worldUrl = kind => 'api/world?' + WORLD_Q[kind];

/* tile size: headline markets bigger (size carries no data, the legend says so) */
const WEIGHT = {
  INX: 3, IXIC: 3, N225: 3, HSI: 3, GDAXI: 3, CLcv1: 3, GCcv1: 3,
  DJI: 2, NDX: 2, STOXX50E: 2, FTSE: 2, SSEC: 2, LCOcv1: 2, SIcv1: 2, HGcv1: 2,
  SOX: 1.6, FCHI: 1.6, TWII: 1.6, KOSPI: 1.6, EScv1: 1.6, NQcv1: 1.6, NGcv1: 1.6, BSESN: 1.4, CSI300: 1.3, TOPX: 1.3,
  Ccv1: 1.3, Scv1: 1.3, Wcv1: 1.3,
};
/* short names for small tiles (the full name stays in the detail, the tooltip and the screen-reader label) */
const SHORT = {
  DJI: '다우', IXIC: '나스닥', NDX: '나스닥 100', SOX: '반도체', DJT: '다우운송',
  EScv1: 'S&P 선물', NQcv1: '나스닥 선물', YMcv1: '다우 선물', RTYcv1: '러셀 선물',
  STOXX50E: '유로스톡스', GDAXI: 'DAX', FTSE: 'FTSE', FCHI: 'CAC 40', AEX: '네덜란드', IBEX: '스페인', FTMIB: '이탈리아',
  OMXS30: '스웨덴', BFX: '벨기에', PSI20: '포르투갈', ISEQ: '아일랜드', BUX: '헝가리',
  N225: '니케이', TOPX: '토픽스', SSEC: '상해', SZSC: '심천', CSI300: 'CSI 300', HSCE: '홍콩H', TWII: '대만', BSESN: '인도',
  VNI: '베트남', HNXI: '하노이', AXJO: '호주', JKSE: '인니', KLSE: '말레이', BVSP: '브라질', MXX: '멕시코', VIX: 'VIX',
  LCOcv1: '브렌트', RBcv1: '가솔린', NGcv1: '천연가스',
  FX_JPYKRW: '원/엔', KR1YT: '국고채 1년', KR3YT: '국고채 3년', KR10YT: '국고채 10년',
  US2YT: '미 국채 2년', US10YT: '미 국채 10년', US30YT: '미 국채 30년', JP10YT: '일 국채 10년',
};
/* 환율 · 금리 (AGENTS §3-28): the groups the Worker adds with `with=fx,rates` */
const MACRO_NOTE = { fx: '오르면 원화 약세', rates: '변화는 bp(0.01%p)', funds: '색은 늘고 준 것만' };   // beside the section title
const FX_SUB = { DXY: '오르면 달러 강세', USDJPY: '오르면 엔화 약세' };                    // rows the section note does not cover
const FX_UNIT = {
  FX_USDKRW: '원 (1달러당)', FX_JPYKRW: '원 (100엔당)', FX_EURKRW: '원 (1유로당)', FX_CNYKRW: '원 (1위안당)',
  DXY: '포인트 (1973년 3월 = 100)', USDJPY: '엔 (1달러당)',
};
const FX_NOTE = {
  DXY: '유로·엔·파운드 등 6개 통화에 견준 달러 가치예요. 오르면 달러 강세예요.',
  USDJPY: '1달러를 사는 데 드는 엔이에요. 오르면 엔화 약세예요.',
};
const KRW_NOTE = '오르면 원화 약세예요. 같은 외화를 사는 데 원화가 더 든다는 뜻이고, 빨강·초록은 숫자의 오르내림만 나타내요.';
const RATE_NOTE = '값은 연 수익률(%)이고 변화는 bp(1bp = 0.01%p)로 보여 줘요. 빨강·초록은 금리의 오르내림이에요.';
/* 증시 자금 (AGENTS §3-32 ①, docs/standards/datago.md §6): 금융투자협회 daily statistics from GET api/funds, merged into the 지표 tab
   as one more group after 환율 · 금리 (row keys 'fd:<key>'). Values come in 억원 (or % for the share) and are shown as 조원 / 억원;
   the change is against the previous business day. Red / green = the number went up / down, nothing more — a rising 신용융자
   is not "good" or "bad" here, exactly like a yield. */
const FUNDS_URL = 'api/funds', FUNDS_POLL_MS = 10 * 60e3, FUNDS_RETRY_MS = 2 * 60e3, FUND_PFX = 'fd:';
const FUNDS = { data: null, tried: 0, gone: false, busy: null, chartGone: false };
const FUND_SRC = '금융투자협회 · 하루 한 번(전 영업일 기준)';
const FUND_SUB = { forced: '하루 금액', forcedRatio: '미수금 대비' };
const FUND_NOTE = {
  deposit: '증권 계좌에 맡겨 둔 돈이에요(장내파생상품 거래예수금은 빼요). 흔히 고객예탁금이라고 불러요.',
  credit: '증권사가 주식을 살 돈으로 빌려준 신용거래융자의 잔고예요. 코스피와 코스닥을 더한 값이에요.',
  creditKospi: '신용거래융자 잔고 가운데 유가증권시장(코스피) 몫이에요.',
  creditKosdaq: '신용거래융자 잔고 가운데 코스닥 몫이에요.',
  unpaid: '주식을 사고 결제일까지 내지 않은 돈(위탁매매 미수금)이에요.',
  forced: '미수금을 갚지 못해 증권사가 주식을 처분한 반대매매 금액이에요. 그날 하루의 금액이에요.',
  forcedRatio: '위탁매매 미수금 가운데 실제로 반대매매된 금액의 비중이에요.',
};
const FUND_COLOR_NOTE = ' 빨강·초록은 전 영업일보다 늘었는지 줄었는지만 나타내요. 늘었다고 좋거나 나쁘다는 뜻은 아니에요.';
/* Naver unit codes → [long, short] */
const UNITS = {
  'USD/BBL': ['달러/배럴', '$/배럴'], 'USD/MMBTU': ['달러/MMBtu', '$/MMBtu'], 'USD/U GAL': ['달러/갤런', '$/갤런'], 'USD/GAL': ['달러/갤런', '$/갤런'],
  'USD/OZS': ['달러/트로이온스', '$/온스'], 'USD/OZ': ['달러/트로이온스', '$/온스'], 'USD/LBS': ['달러/파운드', '$/파운드'],
  'USC/BSH': ['센트/부셸', '¢/부셸'], 'USC/LBS': ['센트/파운드', '¢/파운드'], 'USD/TONNE': ['달러/톤', '$/톤'], 'USD/MT': ['달러/톤', '$/톤'],
  KRW: ['원', '원'], JPY: ['엔', '엔'],
};
// rates carry their unit in the value ("3.756%")
const unitOf = it => { if (!it.unit || isRate(it) || isFund(it)) return null;   // 증시 자금 carries 조원 / 억원 in its value text
  const u = UNITS[String(it.unit).toUpperCase()]; return u || [String(it.unit), String(it.unit)]; };
/* exchange time zones → a place name for "지금 열린 시장" */
const CET = '유럽 중부';
const TZ_CITY = {
  EST5EDT: '뉴욕', 'America/New_York': '뉴욕', CST6CDT: '시카고', 'America/Chicago': '시카고',
  'Europe/London': '런던', 'Europe/Dublin': '런던', WET: '리스본', 'Europe/Lisbon': '리스본',
  CET, 'Europe/Paris': CET, 'Europe/Berlin': CET, 'Europe/Frankfurt': CET, 'Europe/Amsterdam': CET, 'Europe/Madrid': CET, 'Europe/Rome': CET,
  'Europe/Stockholm': CET, 'Europe/Brussels': CET, 'Europe/Budapest': CET, 'Europe/Zurich': CET, 'Europe/Vienna': CET, 'Europe/Copenhagen': CET, 'Europe/Oslo': CET, 'Europe/Warsaw': CET,
  'Asia/Tokyo': '도쿄', 'Asia/Shanghai': '중국', 'Asia/Hong_Kong': '홍콩', 'Asia/Taipei': '타이베이', 'Asia/Kolkata': '인도', 'Asia/Calcutta': '인도',
  'Asia/Ho_Chi_Minh': '베트남', 'Asia/Saigon': '베트남', 'Australia/Sydney': '시드니', 'Asia/Jakarta': '자카르타', 'Asia/Kuala_Lumpur': '쿠알라룸푸르',
  'Asia/Singapore': '싱가포르', 'America/Sao_Paulo': '상파울루', 'America/Mexico_City': '멕시코시티', 'America/Toronto': '토론토', 'Asia/Seoul': '서울',
};

/* ───────── small helpers ───────── */
const $ = (s, el = document) => el.querySelector(s);
// replaceChildren() does not flatten arrays or skip null like KH.h does
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
const sgn = v => v > 0 ? '+' : v < 0 ? MINUS : '';
const cls = v => (KH.fmt && KH.fmt.cls) ? KH.fmt.cls(v) : v > 0 ? 'up' : v < 0 ? 'dn' : 'flat';
const pct = v => v == null || !isFinite(v) ? '—' : (KH.fmt && KH.fmt.pct) ? KH.fmt.pct(v) : sgn(v) + Math.abs(v).toFixed(2) + '%';
const fixed = (v, dp) => Math.abs(v).toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const DP = new Map();                                    // sticky decimals per key (6.330 must not flip to 6.33)
function dpOf(it) {
  if (isRate(it)) return 3;                              // yields: 3.756% (Naver sends 4 decimals for some, the 4th is noise)
  const dec = v => { if (v == null || !isFinite(v)) return 0; const s = String(Math.abs(v)); const i = s.indexOf('.'); return i < 0 || s.includes('e') ? 0 : s.length - i - 1; };
  const d = Math.max(2, Math.min(4, Math.max(dec(it.value), dec(it.change))));
  const was = DP.get(it.key) || 0;
  if (d > was) DP.set(it.key, d);
  return Math.max(d, was);
}
const isFx = it => it.gkey === 'fx', isRate = it => it.gkey === 'rates', isFund = it => it.gkey === 'funds';
const isMacro = it => isFx(it) || isRate(it) || isFund(it);
const isFundPct = it => isFund(it) && it.unit === '%';
// 억원 → "99.81조원" · "9,303억원" · "47.9억원"; signed: "+1,234억원" (a change that rounds to zero has no sign)
function eokText(v, signed) {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  const [txt, zero] = a >= 10000 ? [fixed(a / 10000, 2) + '조원', Math.round(a / 100) === 0] : a >= 100 ? [Math.round(a).toLocaleString('ko-KR') + '억원', false] : [fixed(a, 1) + '억원', Math.round(a * 10) === 0];
  return (signed ? (zero ? '' : sgn(v)) : v < 0 ? MINUS : '') + txt;
}
// a share in %: as many decimals as the source sends (1, sometimes 2); its change in %p
const fundDp = it => { const dec = v => { if (v == null || !isFinite(v)) return 0; const s = String(Math.abs(v)); const i = s.indexOf('.'); return i < 0 ? 0 : s.length - i - 1; }; return Math.max(1, Math.min(2, Math.max(dec(it.value), dec(it.change)))); };
const pctpText = (v, dp) => { if (v == null || !isFinite(v)) return '—'; const r = +v.toFixed(dp); return (r ? sgn(r) : '') + fixed(r, dp) + '%p'; };
const fundVal = it => isFundPct(it) ? fixed(it.value, fundDp(it)) + '%' : eokText(it.value);
const fundChg = it => isFundPct(it) ? pctpText(it.change, fundDp(it)) : eokText(it.change, true);
// "11월 13일" from 'YYYY-MM-DD'; with the weekday: "11월 13일 (금)"
const mdText = (iso, wd) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || '')); if (!m) return ''; const t = `${+m[2]}월 ${+m[3]}일`; return wd ? `${t} (${WD[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()]})` : t; };
const mdShort = iso => { const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(String(iso || '')); return m ? `${m[1]}.${m[2]}` : ''; };
// bp = 0.01%p, one decimal ("+2.3bp"); a change that rounds to 0.0 has no sign
const bpOf = it => it.bp != null && isFinite(it.bp) ? it.bp : it.change != null && isFinite(it.change) ? Math.round(it.change * 10000) / 100 : null;
const bpText = v => { if (v == null || !isFinite(v)) return '—'; const r = Math.round(v * 10) / 10; return sgn(r) + Math.abs(r).toFixed(1) + 'bp'; };
const valText = it => isFund(it) ? fundVal(it) : fixed(it.value, dpOf(it)) + (isRate(it) ? '%' : '');
const chgText = it => isFund(it) ? fundChg(it) : isRate(it) ? bpText(bpOf(it)) : it.change == null || !isFinite(it.change) ? '—' : sgn(it.change) + fixed(it.change, dpOf(it));
// the coloured chip: % change, or bp for a yield, or %p for a share (증시 자금 반대매매 비중)
const chipText = it => isRate(it) ? bpText(bpOf(it)) : isFundPct(it) ? fundChg(it) : pct(it.ratio);
// rows whose chip already carries the change: the change column stays empty (the same number twice says nothing)
const chipIsChange = it => isRate(it) || isFundPct(it);
const isRef = it => !!it.ref;
const isFut = it => it.gkey === 'usf';                 // 미국 선물: listed under 미국, never part of its average
/* 색 범위 자동 · 구역마다 (AGENTS §3-27, 사용자 2026-11-16 13:04 "지표탭에서 등락률 자동 계산은 환율 금리 증시자금 에너지 금속 농산물 등
   각 구역별 계산이 필요할거같아"): on the 지표 tab under 자동 every group (환율 · 금리 · 증시 자금 · 에너지 · 금속 · 농산물 — whatever
   groups the Worker sends) takes its own range, measured on its own rows with the template's one rule (KH.autoRange: p95 → the zone
   step table, hysteresis per zone). 환율 moves ±0.3 % a day and 원자재 ±3 %, so one range for the tab left 환율 · 금리 grey.
   금리 is coloured by its bp change (the number its chip shows) on the bp table; the others by their %. 해외 (지수) stays on the
   tab's range: regions move alike.
   후속 (사용자 2026-11-16 13:42 "1. 추천대로 2. 추천대로 3. 추천대로"):
   ① a picked ±3 · ±5 · ±10 % keeps one range for the tab — except 금리, which keep their own bp 자동 range (the chip reads bp; on the
     yield's % change against ±R they were all but grey). The legend and the 금리 head say "±Nbp 자동".
   ② 증시 자금's 반대매매 rows (금액 forced · 비중 forcedRatio, ±20~30 % a day) are a zone of their own, so 예탁금 · 신용융자 · 미수금
     are not washed out by them. One group on screen, two ranges ("증시 자금 ±3% · 반대매매 ±30%").
   ③ the same 지표 row is the same colour wherever this module draws it: a sheet the ticker opens on any tab colours on these zones
     too (measured on the 지표 data with the same keys — the 지표 tab need not have been opened; a picked range there = the 지표 tab's
     pick, KH.rangeInfo().picks.world). The ticker's and the summary card's own numbers carry direction colours only.
   Z = {auto, pick, zones: Map zone key → {key, group, name, value (±R), unit '%'|'bp', p95}} — the 지표 data's ranges (null: no 지표
   data yet, or an older template). Zone keys = the group keys, plus 'forced' (반대매매). */
const FORCED = new Set(['forced', 'forcedRatio']);
const zoneKeyOf = it => isFund(it) && FORCED.has(it.fkey) ? 'forced' : it.gkey;
const ZONE_NAME = { forced: '반대매매' };
let Z = null;
const zoneNum = it => isRate(it) ? bpOf(it) : it.ratio;         // what a zone colours: a yield's bp, every other row's %
const zoneOf = (it, scope) => Z && scope !== 'kr' && it && it.cm && !isRef(it) ? Z.zones.get(zoneKeyOf(it)) || null : null;
// the number behind an item's colour (and its bar) and the range it sits on: its zone's (a yield's bp); under a picked range a 지표
// row sits on that pick — the 지표 tab's range, also in a sheet opened on another tab; anything else: R null = KH.colorOf's own range
function colRange(it, scope) {
  const z = zoneOf(it, scope);
  if (z) return { v: zoneNum(it), R: z.value, z };
  return { v: it.ratio, R: Z && !Z.auto && Z.pick > 0 && it && it.cm && scope !== 'kr' ? Z.pick : null, z: null };
}
const rTxt = v => { const a = Math.abs(v); return String(+(a >= 10 ? a.toFixed(0) : a >= 1 ? a.toFixed(1) : a.toFixed(2))); };   // the template's fmtR
const zoneTxt = z => `±${rTxt(z.value)}${z.unit === 'bp' ? 'bp' : '%'}`;
// what the zone's tag says: "±0.3%", and under a picked range (only 금리 keep a zone) "±7bp 자동"
const zoneTag = z => zoneTxt(z) + (Z && !Z.auto ? ' 자동' : '');
const colorOf = (it, scope) => {
  if (isRef(it)) return tok().ref;
  const c = colRange(it, scope);
  if (c.v == null || !isFinite(c.v)) return tok().nodata;
  return c.R ? KH.colorOf(c.v, { scope: scope || 'world', range: c.R }) : KH.colorOf(c.v, scope || 'world');
};
// the detail sheet's side: 'world', or 'kr' for a 국내 index opened from the ticker / the dock
const dScope = () => (S.detail && S.detail.scope === 'kr' ? 'kr' : 'world');
const weightOf = it => WEIGHT[it.key] || 1;
const dlText = m => m >= 60 && m % 60 === 0 ? `${m / 60}시간 지연` : `${m}분 지연`;
const delayText = it => it.eod ? '하루 한 번 종가' : it.delayed > 0 ? dlText(it.delayed) : '실시간';
const WD = ['일', '월', '화', '수', '목', '금', '토'];
const fmtKst = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false });
const fmtKstS = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const fmtKstDay = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
const pad = n => String(n).padStart(2, '0');

// "2026-11-09T09:58:46-05:00" → {y,mo,d,hh,mm, off (minutes east of UTC), date (Date)}
function parseLocal(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/.exec(String(iso || ''));
  if (!m) return null;
  let off = 0;
  if (m[7] && m[7] !== 'Z') { const s = m[7].replace(':', ''); off = (s[0] === '-' ? -1 : 1) * (+s.slice(1, 3) * 60 + +s.slice(3, 5)); }
  const date = new Date(iso);
  if (isNaN(date)) return null;
  return { y: +m[1], mo: +m[2], d: +m[3], hh: m[4], mm: m[5], off, date };
}
const tzOk = new Map();
function validTz(tz) {
  if (!tz) return false;
  if (!tzOk.has(tz)) { try { new Intl.DateTimeFormat('en-US', { timeZone: tz }); tzOk.set(tz, true); } catch (e) { tzOk.set(tz, false); } }
  return tzOk.get(tz);
}
// wall-clock parts of `date` in a market's time zone (IANA name when valid, else the UTC offset seen in tradedAt)
function wall(date, it) {
  if (validTz(it.tz)) {
    const p = {};
    for (const x of new Intl.DateTimeFormat('en-US', { timeZone: it.tz, year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, weekday: 'short' }).formatToParts(date)) p[x.type] = x.value;
    const wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(p.weekday);
    return { mo: +p.month, d: +p.day, hh: pad(+p.hour % 24), mm: p.minute, wd };
  }
  const L = parseLocal(it.tradedAt);
  const t = new Date(date.getTime() + (L ? L.off : 0) * 60000);
  return { mo: t.getUTCMonth() + 1, d: t.getUTCDate(), hh: pad(t.getUTCHours()), mm: pad(t.getUTCMinutes()), wd: t.getUTCDay() };
}
const cityOf = (it, g) => TZ_CITY[it.tz] || (it.tz && it.tz.includes('/') ? it.tz.split('/').pop().replace(/_/g, ' ') : g ? g.name : '');
function offText(it) {
  const L = parseLocal(it.tradedAt); if (!L) return '';
  const o = L.off, a = Math.abs(o);
  return 'UTC' + (o < 0 ? MINUS : '+') + Math.floor(a / 60) + (a % 60 ? ':' + pad(a % 60) : '');
}

async function getJSON(url, signal) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  const onAbort = () => ac.abort();
  if (signal) signal.addEventListener('abort', onAbort, { once: true });
  try {
    const res = await fetch(url, { cache: 'no-store', signal: ac.signal });
    const type = res.headers.get('content-type') || '';
    let body = null;
    if (type.includes('json')) { try { body = await res.json(); } catch (e) { /* not JSON */ } }
    if (!res.ok) { const err = new Error((body && body.error) || 'HTTP ' + res.status); err.status = res.status; err.json = !!body; throw err; }
    if (body == null) throw new Error('JSON이 아니에요');
    return body;
  } finally { clearTimeout(timer); if (signal) signal.removeEventListener('abort', onAbort); }
}

/* text measuring (canvas): widths at 1 px, digits measured as '0' because the tiles use tabular figures */
const ctx2d = document.createElement('canvas').getContext('2d');
const MW = new Map();
let family = '';
function tw(text, weight) {
  if (!family) family = getComputedStyle(document.body).fontFamily || 'sans-serif';
  const s = String(text).replace(/[0-9]/g, '0');
  const k = weight + '|' + s;
  let v = MW.get(k);
  if (v == null) { ctx2d.font = `${weight} 100px ${family}`; v = ctx2d.measureText(s).width / 100 * 1.04 + 0.02; MW.set(k, v); }
  return v;
}

/* ───────── state ───────── */
// localStorage can throw (private mode, blocked storage): the choice then lasts for this page only
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* not kept */ } },
};
const VIEW_KEY = 'khm.worldView', SORT_KEY = 'khm.worldSort';
const S = {
  kind: null, shown: false,
  data: { index: null, commodity: null }, at: { index: 0, commodity: 0 }, err: { index: null, commodity: null },
  seq: 0, ac: null, timer: 0, busy: null, announced: {},
  focusKey: null, detail: null, chartRoute: true,
  view: store.get(VIEW_KEY) === 'map' ? 'map' : 'list',          // 목록 is the default (AGENTS §3-4), shared by both tabs
  sort: store.get(SORT_KEY) === 'pct' ? 'pct' : 'group',
  listFocus: null,
};
let root = null, els = null;
// effect level (AGENTS §3-5): KH.motion() when the heatmap has it, else the OS setting decides between reduced and standard
function motion() {
  try { if (typeof KH.motion === 'function') { const m = KH.motion(); return m === 'reduced' || m === 'fancy' ? m : 'standard'; } } catch (e) { /* fall through */ }
  return reduceMQ.matches ? 'reduced' : 'standard';
}
const calm = () => motion() === 'reduced';
function syncMotion() {
  if (!root) return;
  const m = motion();
  // 화려하게 only: the map's first-opening sequence, a market that just opened fading in, the sheet's number roll. The lengths
  // themselves are the template's --sp-* tokens, which html[data-motion="reduced"] sets to 0 (one switch, design.md §6-3) — the
  // classes only say which level this module drew for
  root.classList.toggle('kw-fx', m === 'fancy');
  root.classList.toggle('kw-rm', m === 'reduced');
  if (sheet) sheet.classList.toggle('kw-noanim', m === 'reduced');
}
/* a value written in place (design.md §6-4, P4 · P9): the template's KH.ui.swap — the old text leaves, the new one comes in from below
   when the number rose and from above when it fell. Only a real change moves: the first write, a redraw with the same text or a
   different item (quiet) is written at once. `num` = the number the text stands for (its direction), null = a label (goes up) */
function swapTo(el, text, num, quiet) {
  text = String(text);
  const was = el.__kwT, wasN = el.__kwN;
  el.__kwT = text; el.__kwN = num;
  if (!UI || typeof UI.swap !== 'function') { if (el.textContent !== text) el.textContent = text; return; }
  if (was === text && el.textContent === text) return;
  if (quiet || was == null) { UI.swap(el, text, text); return; }     // from === text: written at once (a running swap ends first)
  const dir = num != null && wasN != null && isFinite(num) && isFinite(wasN) ? Math.sign(num - wasN) : 0;
  UI.swap(el, text, was, dir);
}

/* living controls (docs/standards/controls.md): the template's KH.ui — segments with one raised indicator (seg), the shared
   다시 시도 key (retry: the message stays while it works, ring "받는 중" → ✓ "받았어요" held --c-slow → the content, or ! "아직 안 돼요 ·
   다시" until the next press). failedW: areas whose last retry failed, so a message drawn again keeps the !. */
const UI = KH.ui && typeof KH.ui.retry === 'function' ? KH.ui : null;
const uiSeg = el => { if (UI && typeof UI.seg === 'function') UI.seg(el); return el; };
const uiSpin = () => (UI && typeof UI.icon === 'function' ? UI.icon('spin') : null);
const uiWarn = () => (UI && typeof UI.icon === 'function' ? UI.icon('warn') : h('span', { 'aria-hidden': 'true', text: '!' }));
/* the one close icon (design.md §4 · §5): SVG ×, 1.75px on screen whatever its box, round caps, currentColor */
const closeIcon = () => svg('svg', { viewBox: '0 0 20 20', width: '16', height: '16', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' },
  svg('path', { d: 'M5 5l10 10M15 5 5 15', 'stroke-width': '1.75', 'vector-effect': 'non-scaling-stroke' }));
const failedW = new Set();
function retryKey(area, run, done, cls, alive) {
  cls = 'kw-retry' + (cls ? ' ' + cls : '');
  if (UI) return UI.retry({ cls, run, render: done, alive, fail: failedW.has(area), onStart: () => failedW.delete(area), onFail: () => failedW.add(area) });
  return h('button', { type: 'button', class: cls, onclick: async () => { if (await run()) done(); } }, '다시 시도');
}

/* normalise one /api/world payload; throws on a wrong shape */
function normalise(j, kind) {
  if (!j || !Array.isArray(j.groups)) throw new Error('응답 모양이 달라요');
  const groups = [], seen = new Set();
  let ix = 0;
  for (const g of j.groups) {
    if (!g || !Array.isArray(g.items)) continue;
    const items = [];
    for (const x of g.items) {
      if (!x || x.key == null || x.value == null || !isFinite(+x.value) || seen.has(String(x.key))) continue;
      seen.add(String(x.key));
      const it = {
        key: String(x.key), name: String(x.name || x.key), value: +x.value,
        change: x.change == null || !isFinite(+x.change) ? null : +x.change,
        ratio: x.ratio == null || !isFinite(+x.ratio) ? null : +x.ratio,
        status: x.status === 'OPEN' ? 'OPEN' : 'CLOSE', tradedAt: x.tradedAt || null,
        delayed: +x.delayed > 0 ? +x.delayed : 0, unit: x.unit || null, tz: x.tz || null,
        ref: !!(x.ref || g.ref), group: String(g.name || ''), gkey: String(g.key || ''), ix: ix++,
        // 환율 · 금리 (§3-28): bp = change in 0.01%p, eod = a daily close (달러/엔), calc = computed cross, via = who quotes it
        bp: x.bp == null || !isFinite(+x.bp) ? null : +x.bp, eod: !!x.eod, calc: !!x.calc, via: x.via ? String(x.via) : null,
        cm: kind === 'commodity',                          // a 지표 row: its colour range is the 지표 tab's (구역마다), wherever it shows
      };
      items.push(it);
    }
    if (!items.length) continue;
    // biggest first inside a group (stable for equal weights), so the squarified layout puts headline tiles top-left;
    // the list keeps the Worker's order (`list`)
    const ordered = items.map((it, i) => [it, i]).sort((a, b) => weightOf(b[0]) - weightOf(a[0]) || a[1] - b[1]).map(a => a[0]);
    groups.push({ key: String(g.key || g.name), name: String(g.name || ''), items: ordered, list: items });
  }
  const all = groups.flatMap(g => g.items);
  return { asOf: j.asOf || null, kind, groups, all, byKey: new Map(all.map(it => [it.key, it])), charts: j.charts !== false };
}

/* 증시 자금: /api/funds → items shaped like the others (gkey 'funds'), or null when there is nothing to show */
const numOr = v => v == null || v === '' || !isFinite(+v) ? null : +v;
function fundItems(j) {
  if (!j || !Array.isArray(j.items)) return null;
  const items = [], seen = new Set();
  for (const x of j.items) {
    if (!x || typeof x.key !== 'string' || !/^[A-Za-z]{1,24}$/.test(x.key) || seen.has(x.key) || numOr(x.value) == null) continue;
    seen.add(x.key);
    items.push({
      key: FUND_PFX + x.key, fkey: x.key, name: String(x.name || x.key), value: +x.value, change: numOr(x.change), ratio: numOr(x.ratio),
      unit: x.unit === '%' ? '%' : '억원', basDt: /^\d{4}-\d{2}-\d{2}$/.test(x.basDt) ? x.basDt : null,
      prev: numOr(x.prev), prevDt: /^\d{4}-\d{2}-\d{2}$/.test(x.prevDt) ? x.prevDt : null,
      status: 'CLOSE', tradedAt: null, delayed: 0, tz: null, ref: false, group: '증시 자금', gkey: 'funds', bp: null, eod: false, calc: false, via: '금융투자협회',
      cm: true,
    });
  }
  if (!items.length) return null;
  const basDt = /^\d{4}-\d{2}-\d{2}$/.test(j.basDt) ? j.basDt : items.map(it => it.basDt).filter(Boolean).sort().pop() || null;
  return { asOf: j.asOf || null, basDt, stale: !!j.stale, items };
}
// put the 증시 자금 group at the end of the 지표 data (after 환율 · 금리), or take it away; d is changed in place
function withFunds(d) {
  if (!d || d.kind !== 'commodity') return d;
  d.groups = d.groups.filter(g => g.key !== 'funds');
  const F = FUNDS.data;
  if (F) {
    let ix = d.groups.reduce((m, g) => Math.max(m, ...g.items.map(it => it.ix)), -1);
    const items = F.items.map(it => Object.assign({}, it, { ix: ++ix }));
    d.groups.push({ key: 'funds', name: '증시 자금', items, list: items, basDt: F.basDt });
  }
  d.all = d.groups.flatMap(g => g.items);
  d.byKey = new Map(d.all.map(it => [it.key, it]));
  return d;
}
// at most every 10 min while the 지표 tab is shown (the Worker caches an hour; the source changes once a day). 404 = a Worker
// without the route: stop asking for this page. Other failures keep the last good values.
function loadFunds(force) {
  if (!LIVE || FUNDS.gone || FUNDS.busy) return FUNDS.busy;
  const now = Date.now();
  if (!force && now - FUNDS.tried < (FUNDS.data ? FUNDS_POLL_MS : FUNDS_RETRY_MS)) return null;
  FUNDS.tried = now;
  FUNDS.busy = (async () => {
    try {
      FUNDS.data = fundItems(await getJSON(FUNDS_URL));
      FUNDS.err = null;
    } catch (e) {
      if (e.status === 404) { FUNDS.gone = true; FUNDS.data = null; }
      FUNDS.err = e;
    } finally { FUNDS.busy = null; }
    const d = S.data.commodity;
    if (d) {
      const had = d.groups.some(g => g.key === 'funds');
      withFunds(d);
      if ((had || FUNDS.data) && S.shown && S.kind === 'commodity' && els && !els.snap) render();
    }
  })();
  return FUNDS.busy;
}

/* 수출입은행 고시 (AGENTS §3-27 끝 · §3-2, 사용자 2026-11-16 11:33 "그래 추천대로"): GET api/koreaexim?kind=fx|rate. The bank posts
   once a business day (before 11:32 on 2026-11-16, the minute unknown); the Worker keeps one copy per posting day. Two small
   tables in the 지표 tab, not clickable (a row's title is the only extra):
   ① inside the 환율 card, below its rows — 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안: 매매기준율 · 송금 보낼 때(tts) · 받을 때(ttb),
      the numbers to look at when changing or sending money. No change is shown, so no colour.
   ③ inside the 금리 card, below the 국채 rows under its own heading "기준금리 · 은행간 금리" — SOFR · ESTR (· TONA when it is sent)
      overnight, EURIBOR · TIBOR 1 · 3 · 6 · 12개월, %; the change in bp against the previous posting when the Worker has one
      (colour = up / down only, like a yield).
   Asked at most every 10 min while the 지표 tab is shown (2 min after a failure); 404 = a Worker without the route → absent for this
   page. A failure without any value shows one muted line in that table's place; nothing else waits for it. */
const KXIM_POLL_MS = 10 * 60e3, KXIM_RETRY_MS = 2 * 60e3;
const KXIM = { fx: null, rate: null, err: { fx: null, rate: null }, tried: 0, gone: false, busy: null, hm: {} };
const KX_FX = [['USD', '원/달러'], ['JPY', '원/엔(100엔)'], ['EUR', '원/유로'], ['CNH', '원/위안']];
const KX_CUR = { USD: '달러', EUR: '유로', JPY: '엔' };
const KX_SEC = { fx: 'fx', rates: 'rate' };               // list section → the table it carries
const isoDay = s => (/^\d{4}-\d{2}-\d{2}$/.test(String(s || '')) ? String(s) : null);
const posNum = v => (v == null || v === '' || !isFinite(+v) || +v <= 0 ? null : +v);
function kxNorm(j, kind) {
  if (!j || !Array.isArray(j.items) || !isoDay(j.date)) return null;
  let items;
  if (kind === 'fx') {
    const by = new Map(j.items.filter(x => x && typeof x.code === 'string').map(x => [x.code, x]));
    items = KX_FX.map(([code, name]) => { const x = by.get(code); const base = x && posNum(x.base); return base ? { code, name, base, tts: posNum(x.tts), ttb: posNum(x.ttb) } : null; }).filter(Boolean);
  } else {
    items = j.items.filter(x => x && /^[A-Z]{3,8}$/.test(x.family) && typeof x.tenor === 'string' && x.value != null && isFinite(+x.value)).slice(0, 16).map(x => ({
      key: String(x.key || x.family + x.tenor), family: x.family, cur: KX_CUR[x.cur] || '', tenor: x.tenor.slice(0, 8), value: +x.value,
      raw: /^-?\d+(\.\d+)?$/.test(String(x.raw || '')) ? String(x.raw) : null, name: String(x.name || '').slice(0, 40), bp: x.bp == null || !isFinite(+x.bp) ? null : +x.bp,
    }));
  }
  if (!items.length) return null;
  return {
    items, date: j.date, today: j.today === true, waiting: j.waiting === true, stale: j.stale === true,
    firstSeen: /^\d{2}:\d{2}$/.test(String(j.firstSeen || '')) ? j.firstSeen : null, exact: j.exact === true,
  };
}
// both tables at once, at most every 10 min (2 min after a failure); a value that came stays when a later ask fails
function loadKxim(force) {
  if (!LIVE || KXIM.gone || KXIM.busy) return KXIM.busy;
  const now = Date.now();
  const d = S.data.commodity;
  if (!d || !d.groups.some(g => KX_SEC[g.key])) return null;   // an older Worker without 환율 · 금리: nowhere to put them
  const failed = !!(KXIM.err.fx || KXIM.err.rate);
  if (!force && now - KXIM.tried < (failed ? KXIM_RETRY_MS : KXIM_POLL_MS)) return null;
  KXIM.tried = now;
  KXIM.busy = (async () => {
    const was = JSON.stringify([KXIM.fx, KXIM.rate, !!KXIM.err.fx, !!KXIM.err.rate]);
    await Promise.all(['fx', 'rate'].map(async kind => {
      try {
        const v = kxNorm(await getJSON('api/koreaexim?kind=' + kind), kind);
        KXIM[kind] = v; KXIM.err[kind] = null;
      } catch (e) {
        if (e.status === 404) KXIM.gone = true;
        KXIM.err[kind] = e;
      }
    }));
    if (KXIM.gone) { KXIM.fx = KXIM.rate = null; }
    KXIM.busy = null;
    const changed = was !== JSON.stringify([KXIM.fx, KXIM.rate, !!KXIM.err.fx, !!KXIM.err.rate]);
    if (changed && S.shown && S.kind === 'commodity' && els && !els.snap) render();
  })();
  return KXIM.busy;
}
// what a table's place holds: 'data' · 'fail' (nothing came, the last ask failed) · null (hidden: not asked yet, an older Worker, empty)
const kxState = kind => (KXIM[kind] ? 'data' : !KXIM.gone && KXIM.err[kind] ? 'fail' : null);
// its height for the column balance (distribute): the last measured one for this kind and row style, else an estimate
function kxHeight(secKey, compact) {
  const kind = KX_SEC[secKey], st = kind && S.kind === 'commodity' ? kxState(kind) : null;
  if (!st) return 0;
  const m = KXIM.hm[kind + (compact ? ':c' : '') + ':' + st];
  if (m) return m;
  if (st === 'fail') return 70;
  const n = KXIM[kind].items.length;
  return 16 + 26 + 22 + n * (compact ? 30 : 26) + (compact ? 48 : 34);
}
const kxWhen = v => (v.today ? (v.firstSeen ? (v.exact ? `오늘 ${v.firstSeen} 고시` : `오늘 고시 · ${v.firstSeen} 확인`) : '오늘 고시') : `${mdText(v.date, true)} 고시`);
const kxFixed = (v, dp) => (v == null ? '—' : (v < 0 ? MINUS : '') + fixed(v, dp));
function kxHead(kind, v) {
  const id = 'kw-kx-' + kind;
  const meta = ['하루 한 번', kind === 'rate' ? '수출입은행' : null, v ? kxWhen(v) : null].filter(Boolean).join(' · ');
  const warn = v && v.stale ? h('span', { class: 'kw-kxw', title: '수출입은행에서 새 값을 확인하지 못했어요' }, uiWarn(), h('span', { class: 'sr', text: '새 값을 확인하지 못했어요' })) : null;
  return h('div', { class: 'kw-kxh' }, h('h5', { class: 'kw-kxt', id }, kind === 'fx' ? '수출입은행 고시' : '기준금리 · 은행간 금리'), h('span', { class: 'kw-kxm' }, meta, warn));
}
function kxFxTable(v) {
  return h('table', { class: 'kw-kxtb kw-kxf', 'aria-labelledby': 'kw-kx-fx' },
    h('thead', {}, h('tr', {}, h('th', { scope: 'col', class: 'nm' }, h('span', { class: 'sr', text: '통화' })),
      h('th', { scope: 'col', text: '매매기준율' }), h('th', { scope: 'col', text: '송금 보낼 때' }), h('th', { scope: 'col', text: '송금 받을 때' }))),
    h('tbody', {}, v.items.map(it => h('tr', { 'data-k': it.code, title: `${it.name} · 매매기준율 ${kxFixed(it.base, 2)}원 · 송금 보낼 때 ${kxFixed(it.tts, 2)}원 · 받을 때 ${kxFixed(it.ttb, 2)}원` },
      h('th', { scope: 'row', class: 'nm', text: it.name }), h('td', { text: kxFixed(it.base, 2) }), h('td', { text: kxFixed(it.tts, 2) }), h('td', { text: kxFixed(it.ttb, 2) })))));
}
function kxRateTable(v) {
  const hasBp = v.items.some(it => it.bp != null);
  const fams = [];
  for (const it of v.items) { const f = fams[fams.length - 1]; if (f && f.family === it.family) f.items.push(it); else fams.push({ family: it.family, cur: it.cur, items: [it] }); }
  return h('table', { class: 'kw-kxtb kw-kxr' + (hasBp ? '' : ' nobp'), 'aria-labelledby': 'kw-kx-rate' },
    h('thead', {}, h('tr', {}, h('th', { scope: 'col', class: 'nm' }, h('span', { class: 'sr', text: '이름' })), h('th', { scope: 'col', class: 'tn', text: '기간' }),
      h('th', { scope: 'col', text: '금리' }), hasBp ? h('th', { scope: 'col', text: '변화' }) : null)),
    fams.map(f => h('tbody', { 'data-f': f.family }, f.items.map((it, i) => {
      const bp = it.bp == null ? null : Math.round(it.bp * 10) / 10;
      return h('tr', { 'data-k': it.key, title: `${it.name || f.family + ' ' + it.tenor} · ${it.raw != null ? it.raw : kxFixed(it.value, 3)}%` },
        i === 0 ? h('th', { scope: 'rowgroup', class: 'nm', rowspan: String(f.items.length) }, f.family, f.cur ? h('small', { text: f.cur }) : null) : null,
        h('td', { class: 'tn', text: it.tenor }),
        h('td', { text: kxFixed(it.value, 3) + '%' }),
        hasBp ? h('td', { class: 'bp ' + (bp == null ? 'flat' : cls(bp)), text: bp == null ? '' : bpText(bp) }) : null);
    }))));
}
function kxNote(kind, v) {
  const t = kind === 'fx' ? ['환전 · 송금할 때 참고하는 은행 고시값이에요. 실제로 적용되는 환율은 은행과 우대율마다 달라요.']
    : ['익일은 하루짜리 기준금리, 1~12개월은 은행끼리 빌려주는 기간별 금리예요.', v.items.some(it => it.bp != null) ? '변화는 전 영업일 고시 대비 bp(1bp = 0.01%p)로 보여 줘요.' : null];
  if (v.waiting) t.push('오늘 고시는 아직 나오지 않았어요.');
  if (v.stale) t.push('새 값을 확인하지 못해 지난 값을 보여 줘요.');
  return h('p', { class: 'kw-kxn', text: t.filter(Boolean).join(' ') });
}
// fill one table's place (only when what it shows changed); returns true when its height moved off the one distribute used
function fillKx(box, kind, compact) {
  const st = kxState(kind), v = KXIM[kind];
  const sig = JSON.stringify([st, v, compact]);
  if (box.__sig !== sig) {
    box.__sig = sig;
    box.hidden = !st;
    if (!st) box.replaceChildren();
    else if (st === 'fail') put(box, kxHead(kind, null), h('p', { class: 'kw-kxn kw-stale' }, uiWarn(), kind === 'fx' ? '수출입은행 고시 환율을 불러오지 못했어요' : '수출입은행 고시 금리를 불러오지 못했어요'));
    else put(box, kxHead(kind, v), kind === 'fx' ? kxFxTable(v) : kxRateTable(v), kxNote(kind, v));
  }
  if (!st) return false;
  const k = kind + (compact ? ':c' : '') + ':' + st, used = kxHeight(kind === 'fx' ? 'fx' : 'rates', compact);
  const hgt = box.offsetHeight + parseFloat(getComputedStyle(box).marginTop || 0);
  KXIM.hm[k] = hgt;
  return Math.abs(hgt - used) > 12;
}

/* ───────── DOM scaffold ───────── */
function scaffold() {
  root = document.getElementById('world');
  if (!root) return false;
  if (root.__kw && els && root.contains(els.map)) return true;
  root.classList.add('kw');
  root.replaceChildren();
  if (!LIVE) { root.__kw = true; els = { snap: true }; return true; }
  const map = h('div', { class: 'kw-map', role: 'group' });
  const list = h('div', { class: 'kw-list', role: 'group', hidden: true });
  const geo = h('div', { class: 'kw-geo', hidden: true });
  // the world map could not load: the list stands in; 다시 시도 fetches the atlas again (the note stays until the map is in)
  const note = h('p', { class: 'kw-gnote', role: 'status', hidden: true }, '세계지도를 불러오지 못해서 목록으로 보여 드려요. ',
    retryKey('geo', async () => { GEO.state = 'idle'; await loadAtlas(true); return GEO.state === 'ready'; }, () => render(), 'sm',
      () => S.shown && S.kind === 'index' && S.view === 'map'));
  const seg = (name, label, opts) => uiSeg(h('div', { class: 'seg kw-seg', role: 'group', 'aria-label': label, 'data-kw': name },
    opts.map(([v, t]) => h('button', { type: 'button', 'data-v': v, 'aria-pressed': 'false' }, t))));
  const sortSeg = seg('sort', '정렬', [['group', '지역순'], ['pct', '등락률순']]);
  const viewSeg = seg('view', '보기', [['list', '목록'], ['map', '지도']]);
  const tools = h('div', { class: 'kw-tools' }, sortSeg, viewSeg);
  const bar = h('div', { class: 'kw-bar' }, h('h2', { class: 'kw-title' }), h('span', { class: 'kw-sum' }), h('span', { class: 'kw-time' }), tools);
  const legend = h('div', { class: 'legend kw-legend' });
  const rank = h('div', { class: 'kw-rank' });
  const open = h('div', { class: 'kw-open' });
  const src = h('p', { class: 'kw-src' });
  const live = h('div', { class: 'sr', role: 'status', 'aria-live': 'polite' });
  root.append(
    h('section', { class: 'kw-stage' }, bar, note, list, map, geo, legend),
    h('aside', { class: 'kw-side' },
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '많이 오른·내린' }), h('small', { class: 'kw-rank-sub' })), rank),
      h('section', { class: 'card kw-card' }, h('h2', {}, h('span', { text: '지금 열린 시장' }), h('small', { text: '현지 시각' })), open),
      src),
    live);
  els = { map, list, geo, note, bar, tools, sortSeg, viewSeg, legend, rank, open, src, live, tiles: new Map(), heads: new Map(), boxes: null, mapW: 0,
    rows: new Map(), listW: 0, listSig: '', g: null };
  root.__kw = true;
  map.addEventListener('click', e => { const t = e.target.closest('.kw-tile'); if (t) openDetail(t.dataset.k, t); });
  map.addEventListener('keydown', onMapKey);
  map.addEventListener('focusin', e => { const t = e.target.closest('.kw-tile'); if (t) setRoving(t.dataset.k); });
  list.addEventListener('click', e => { const r = e.target.closest('.kw-lr'); if (r) openDetail(r.dataset.k, r); });
  list.addEventListener('keydown', onListKey);
  list.addEventListener('focusin', e => { const r = e.target.closest('.kw-lr'); if (r) setListFocus(r.dataset.k); });
  rank.addEventListener('click', e => { const b = e.target.closest('.kw-row'); if (b) openDetail(b.dataset.k, b); });
  tools.addEventListener('click', e => {
    const b = e.target.closest('.kw-seg button[data-v]');
    if (!b) return;
    const k = b.parentElement.dataset.kw, v = b.dataset.v;
    if (k === 'view') setView(v); else if (k === 'sort') setSort(v);
  });
  new ResizeObserver(() => { if (S.shown && S.view === 'map' && els.map.clientWidth !== els.mapW) schedRender(); }).observe(map);
  new ResizeObserver(() => { if (S.shown && S.view === 'list' && els.list.clientWidth !== els.listW) schedRender(); }).observe(list);
  new ResizeObserver(() => { if (S.shown && S.mode === 'geo' && els.g && els.geo.clientWidth !== els.g.W) schedRender(); }).observe(geo);
  geo.addEventListener('click', onGeoClick);
  geo.addEventListener('keydown', onGeoKey);
  geo.addEventListener('focusin', e => { const b = e.target.closest('.kw-gb'); if (b) setGeoFocus(b.dataset.f); });
  return true;
}
function setView(v) {
  v = v === 'map' ? 'map' : 'list';
  if (v === 'map' && GEO.state === 'failed' && S.kind === 'index') { GEO.state = 'idle'; S.view = v; store.set(VIEW_KEY, v); render(); return; }   // try the world map again
  if (S.view === v) return;
  S.view = v;
  store.set(VIEW_KEY, v);
  render();
}
function setSort(v) {
  v = v === 'pct' ? 'pct' : 'group';
  if (S.sort === v) return;
  S.sort = v;
  store.set(SORT_KEY, v);
  render();
}
function syncTools(hasData, mode) {
  if (!els || !els.tools) return;
  // the pressed button says what is on screen (the list stands in when the world map could not load)
  const shown = mode === 'list' ? 'list' : mode === 'msg' ? S.view : 'map';
  for (const b of els.viewSeg.children) b.setAttribute('aria-pressed', String(b.dataset.v === shown));
  for (const b of els.sortSeg.children) b.setAttribute('aria-pressed', String(b.dataset.v === S.sort));
  els.sortSeg.children[0].textContent = S.kind === 'commodity' ? '종류순' : '지역순';
  els.sortSeg.hidden = mode !== 'list' || !hasData;
  els.viewSeg.hidden = S.kind === 'commodity';
}

let rafR = 0;
const schedRender = () => { cancelAnimationFrame(rafR); rafR = requestAnimationFrame(() => { if (S.shown) render(); }); };

/* 구역마다: the ranges of the 지표 data (see Z) — measured before anything takes a colour. Zone key = the group's (fx · rates · funds ·
   energy · metals · agri …) or 'forced' (증시 자금's 반대매매 rows), kept apart from the tabs' by the template ('CMDTY:' + key, the same
   keys whoever measures); values = the rows' zoneNum (reference rows left out); a zone of yields (every row a rate) is a bp zone.
   pick: the 해외 · 지표 side's range choice — 'auto' → every zone; a number → the bp zones only (금리, 후속 ①), the rest on the pick. */
function worldPick() {
  try {
    const ri = typeof KH.rangeInfo === 'function' ? KH.rangeInfo() : null;
    if (!ri) return null;
    if (ri.picks && ri.picks.world != null) return ri.picks.world;
    return S.shown && S.kind === 'commodity' ? ri.pick : null;       // an older template: only the tab itself knows its pick
  } catch (e) { return null; }
}
function measureZones(d) {
  if (!d || d.kind !== 'commodity' || !d.all.length || typeof KH.autoRange !== 'function') return null;
  const pick = worldPick();
  if (pick !== 'auto' && !(+pick > 0)) return null;
  const auto = pick === 'auto', zones = new Map();
  // in the list's order: 환율 · 금리 · 증시 자금 first (shown first since 2026-11-14), then 원자재 as the Worker sends them
  for (const g of d.groups.slice().sort((a, b) => (MACRO_NOTE[b.key] ? 1 : 0) - (MACRO_NOTE[a.key] ? 1 : 0))) {
    const parts = new Map();                                // zone key → its rows, in the group's order (증시 자금 · 반대매매)
    for (const it of g.list || g.items) {
      if (isRef(it)) continue;
      const zk = zoneKeyOf(it);
      if (!parts.has(zk)) parts.set(zk, []);
      parts.get(zk).push(it);
    }
    for (const [zk, items] of parts) {
      const unit = items.every(isRate) ? 'bp' : '%';
      if (!auto && unit !== 'bp') continue;
      let r = null;
      try { r = KH.autoRange('CMDTY:' + zk, items.map(zoneNum), unit); } catch (e) { r = null; }
      if (r && r.value > 0) zones.set(zk, { key: zk, group: g.key, name: ZONE_NAME[zk] || g.name || zk, value: +r.value, unit, p95: r.p95 });
    }
  }
  return { auto, pick: auto ? null : +pick, zones };
}
// the zones a 지표 row is drawn on outside the 지표 tab's own render (a sheet the ticker opens on 해외 · 국내 tabs): the same measure
const syncZones = () => { Z = measureZones(S.data.commodity); };
const zoneList = () => Z ? [...Z.zones.values()] : [];
// the 지표 tab draws its zones now (legend · heads · captions); a sheet elsewhere colours on Z without showing them
const zonesShown = () => !!(Z && S.shown && S.kind === 'commodity');

/* ───────── render ───────── */
function render() {
  if (!S.shown || !els) return;
  if (els.snap) return renderSnapshot();
  syncMotion();
  const K = KINDS[S.kind], d = S.data[S.kind], err = S.err[S.kind];
  $('.kw-title', els.bar).textContent = K.title;
  $('.kw-side', root).setAttribute('aria-label', `${K.title} 요약`);
  els.map.setAttribute('aria-label', `${K.title} 지도. 화살표로 옮기고 Enter로 자세히 봐요`);
  els.list.setAttribute('aria-label', `${K.title} 목록. 위아래 화살표로 옮기고 Enter로 자세히 봐요`);
  const hasData = !!(d && d.all.length);
  // what the stage shows: a message box (loading / failure / empty), the list, the tile map, or — 해외 지수 in 지도 — the world map
  // 원자재 has no geography, so it is list-only (user 2026-11-10: "지도는 세계지도만"); 해외 지수 keeps 목록 · 지도(세계지도)
  const view = S.kind === 'commodity' ? 'list' : S.view;
  const wantGeo = hasData && view === 'map' && S.kind === 'index';
  if (wantGeo && GEO.state === 'idle') loadAtlas();
  const geoFailed = wantGeo && GEO.state === 'failed';
  const mode = !hasData ? 'msg' : view === 'list' || geoFailed ? 'list' : wantGeo ? (GEO.state === 'ready' ? 'geo' : 'geoload') : 'tiles';
  S.mode = mode;
  if (mode !== 'geo') { clearTimeout(nightT); nightT = 0; }
  syncTools(hasData, mode);
  els.list.hidden = mode !== 'list';
  els.geo.hidden = mode !== 'geo';
  els.map.hidden = mode === 'list' || mode === 'geo';
  els.note.hidden = !geoFailed;
  root.classList.toggle('kw-v-list', mode === 'list');
  root.classList.toggle('kw-v-geo', mode === 'geo');
  if (!d) {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(err ? msgBox(K.fail, errText(err), true) : msgBox('불러오는 중이에요…', `${K.title} 시세를 받아 오고 있어요.`, false, true));
    const sum = $('.kw-sum', els.bar); sum.__sig = ''; put(sum);
    $('.kw-time', els.bar).replaceChildren();
    els.legend.replaceChildren();
    els.rank.replaceChildren(h('p', { class: 'kw-none', text: err ? '시세를 받지 못했어요' : '불러오는 중이에요…' }));
    els.open.replaceChildren(h('p', { class: 'kw-none', text: err ? '시세를 받지 못했어요' : '불러오는 중이에요…' }));
    renderSource(null);
    return;
  }
  if (!d.all.length) {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(msgBox(K.empty, '거래소 자료가 비어 있어요. 잠시 뒤 다시 받아 올게요.', true));
    els.rank.replaceChildren(h('p', { class: 'kw-none', text: '보여 줄 항목이 없어요' }));
    els.open.replaceChildren(h('p', { class: 'kw-none', text: '보여 줄 항목이 없어요' }));
    renderBar(d, err); els.legend.replaceChildren(); renderSource(d);
    return;
  }
  // §3-27 색 범위 자동: hand the template what this tab draws (VIX is a reference, never coloured) before anything takes a colour
  // 증시 자금 is a day-old statistic, not today's move: it does not set the tab's range (the ticker and other boxes still colour on
  // it). 구역마다 (지표): every zone's own range first (Z — under a picked range only 금리); the template is told them under 자동
  // for the 자동 key's name
  if (S.kind === 'commodity') Z = measureZones(d);
  if (typeof KH.feedRange === 'function') {
    const zs = S.kind === 'commodity' && Z && Z.auto ? zoneList().map(z => ({ key: z.key, name: z.name, value: z.value, unit: z.unit })) : null;
    try { KH.feedRange(S.kind, d.all.filter(it => !isRef(it) && !isFund(it)).map(it => it.ratio), zs); } catch (e) { /* fixed range */ }
  }
  renderBar(d, err);
  if (mode === 'geoload') {
    els.tiles.clear(); els.heads.clear(); els.boxes = null;
    els.map.style.height = '';
    els.map.classList.add('kw-msgmode');
    els.map.replaceChildren(msgBox('세계지도를 불러오는 중이에요…', '나라 경계 자료(Natural Earth)를 처음 한 번 받아 와요.', false, true));
  } else if (els.map.classList.contains('kw-msgmode')) { els.map.classList.remove('kw-msgmode'); els.map.replaceChildren(); }
  if (mode === 'list') renderList(d);
  else if (mode === 'geo') renderGeo(d);
  else if (mode === 'tiles') renderMap(d);
  renderLegend(d);
  renderRank(d);
  renderOpen(d);
  renderSource(d);
  if (S.detail) fillDetail(false);
}
function errText(e) {
  if (!e) return '';
  if (e.name === 'AbortError') return '응답이 너무 늦어요. 잠시 뒤 다시 시도할게요.';
  if (e.status === 404 && !e.json) return '서버에 아직 이 기능이 없어요. 잠시 뒤 다시 시도할게요.';
  return e.status ? '서버가 시세를 받아 오지 못했어요. 15초 뒤 다시 시도할게요.' : '네트워크 연결을 확인해 주세요. 15초 뒤 다시 시도할게요.';
}
// retry: 다시 시도 fetches this kind again; the message stays until the answer is in (busy: the ring while the first answer comes)
function msgBox(title, body, retry, busy) {
  const kind = S.kind;
  return h('div', { class: 'kw-msg' + (busy ? ' busy' : '') }, h('b', {}, title, busy ? uiSpin() : null), body ? h('span', { text: body }) : null,
    retry ? retryKey('data:' + kind, () => load(kind, true), () => render(), '', () => S.shown && S.kind === kind) : null);
}

function renderBar(d, err) {
  let up = 0, dn = 0, fl = 0, open = 0;
  // 지표: the counts are the commodities' (a yield or a won rate going up is not the same kind of "오른"), and say so
  const mixed = d.all.some(isMacro);
  for (const it of d.all) { if (isMacro(it)) continue; if (it.status === 'OPEN') open++; if (isRef(it) || it.ratio == null) continue; if (it.ratio > 0) up++; else if (it.ratio < 0) dn++; else fl++; }
  // the counts are kept per element and swap in place when a refresh changes them (§6-4: a count that grew comes in from below);
  // a new shape (another tab, 보합 appears) is drawn at once
  const sum = $('.kw-sum', els.bar), sig = [S.kind, mixed, !!fl].join('|');
  const dot = () => h('span', { class: 'kw-dot', 'aria-hidden': 'true', text: '·' });
  if (sum.__sig !== sig) {
    sum.__sig = sig;
    put(sum,
      mixed ? h('span', { class: 'kw-sumk', text: '원자재' }) : null,
      h('span', {}, '오른 ', h('b', { class: 'up', 'data-n': 'up' })), dot(),
      h('span', {}, '내린 ', h('b', { class: 'dn', 'data-n': 'dn' })),
      fl ? [dot(), h('span', {}, '보합 ', h('b', { class: 'flat', 'data-n': 'fl' }))] : null,
      dot(), h('span', { 'data-n': 'open' }));
  }
  const n = k => sum.querySelector(`[data-n="${k}"]`);
  swapTo(n('up'), String(up), up);
  swapTo(n('dn'), String(dn), dn);
  if (fl) swapTo(n('fl'), String(fl), fl);
  swapTo(n('open'), open ? `장중 ${open}` : '모두 마감', open);
  const t = $('.kw-time', els.bar);
  const at = d.asOf ? new Date(d.asOf) : new Date(S.at[S.kind]);
  // a refresh that failed: ! + words (design.md §2 --fail-dot), the last good time
  if (err) t.replaceChildren(h('span', { class: 'kw-stale' }, uiWarn(), `새로 받지 못했어요 · ${isNaN(at) ? '' : fmtKst.format(at) + ' 값'}`));
  else t.replaceChildren(h('span', { text: isNaN(at) ? '' : `${fmtKst.format(at)} 기준` }));
}

/* ── layout: desktop = one squarified treemap of groups; phones = groups stacked in rows (small groups share a row) ── */
function computeLayout(d, W, Hfix) {
  const narrow = W < 560;
  const HD = narrow ? 18 : 20, GAP = 3;
  const wsum = arr => arr.reduce((a, it) => a + weightOf(it), 0);
  const groups = d.groups.map(g => ({ g, wt: wsum(g.items) }));
  const tiles = [], heads = [];
  const packItems = (g, x, y, w, hh) => {
    const H = hh - g.hd;
    if (w <= 0 || H <= 0) return;
    const root = d3.hierarchy({ children: g.g.items.map(it => ({ it })) }).sum(n => n.it ? weightOf(n.it) : 0);
    d3.treemap().size([w, H]).round(true).paddingInner(1).tile(d3.treemapSquarify.ratio(1))(root);
    for (const l of root.leaves()) tiles.push({ it: l.data.it, g: g.g, x: x + l.x0, y: y + g.hd + l.y0, w: l.x1 - l.x0, h: l.y1 - l.y0 });
  };
  if (!narrow) {
    const H = Hfix || mapHeightDesktop(d, W);
    const root = d3.hierarchy({ children: groups.map(g => ({ grp: g, children: g.g.items.map(it => ({ it })) })) }).sum(n => n.it ? weightOf(n.it) : 0);
    d3.treemap().size([W, H]).round(true).tile(d3.treemapSquarify.ratio(1))
      .paddingInner(n => n.depth === 0 ? GAP : 1)
      .paddingTop(n => { if (n.depth !== 1) return 0; const v = (n.x1 - n.x0 > 44 && n.y1 - n.y0 > 40) ? HD : 0; n.data.grp.hd = v; return v; })(root);
    for (const n of root.children || []) {
      const g = n.data.grp;
      heads.push({ g: g.g, x: n.x0, y: n.y0, w: n.x1 - n.x0, h: n.y1 - n.y0, hd: g.hd });
      for (const l of n.leaves()) tiles.push({ it: l.data.it, g: g.g, x: l.x0, y: l.y0, w: l.x1 - l.x0, h: l.y1 - l.y0 });
    }
    return { W, H, tiles, heads, narrow };
  }
  // phones: rows of groups; grow the area per weight unit until every tile is a comfortable tap target
  const T = 5.5, rows = [];
  let cur = null;
  for (const g of groups) {
    if (g.wt >= T) { if (cur) { rows.push(cur); cur = null; } rows.push([g]); continue; }
    (cur = cur || []).push(g);
    if (cur.reduce((a, x) => a + x.wt, 0) >= T) { rows.push(cur); cur = null; }
  }
  if (cur) rows.push(cur);
  // fewer items (원자재 17) get bigger tiles than the 41 indices
  let unit = 5000 * Math.max(1, Math.min(1.5, 40 / Math.max(1, d.all.length))), out = null;
  for (let tries = 0; tries < 7; tries++) {
    tiles.length = 0; heads.length = 0;
    let y = 0;
    for (const row of rows) {
      const rw = row.reduce((a, x) => a + x.wt, 0);
      const hh = Math.max(64, Math.round(rw * unit / W)) + HD;
      let x = 0;
      row.forEach((g, i) => {
        const w = i === row.length - 1 ? W - x : Math.round((W - GAP * (row.length - 1)) * g.wt / rw);
        g.hd = w > 40 ? HD : 0;
        heads.push({ g: g.g, x, y, w, h: hh, hd: g.hd });
        packItems(g, x, y, w, hh);
        x += w + GAP;
      });
      y += hh + GAP;
    }
    out = { W, H: y - GAP, tiles: tiles.slice(), heads: heads.slice(), narrow };
    const small = tiles.some(t => t.w < 46 || t.h < 44);
    if (!small) break;
    unit *= 1.18;
  }
  return out;
}
function mapHeightDesktop(d, W) {
  if (narrowMQ.matches) {                                 // a phone in landscape / small tablet: size by content
    const units = d.all.reduce((a, it) => a + weightOf(it), 0);
    return Math.max(380, Math.min(900, Math.round(units * 6400 / W + d.groups.length * 12)));
  }
  const top = els.map.getBoundingClientRect().top + scrollY;
  const lg = els.legend.offsetHeight || 30;
  return Math.max(480, Math.round(innerHeight - top - 14 - lg));
}

/* ── fitting a label into a tile: name (full or short, 1 or 2 lines), % line, value line, then the state chip ── */
const LH = { name: 1.08, pc: 0.8 * 1.08 + 0.08, v: 0.58 * 1.08 + 0.58 * 0.14 }, PADX = 8, GLYPH = 0.16;
function splitName(name) {
  const sp = [...name.matchAll(/ /g)].map(m => m.index);
  if (!sp.length) return null;
  let best = sp[0], bd = Infinity;
  for (const i of sp) { const dd = Math.abs(i - name.length / 2); if (dd < bd) { bd = dd; best = i; } }
  return [name.slice(0, best), name.slice(best + 1)];
}
function tileTexts(it, g) {
  const u = S.kind === 'commodity' ? unitOf(it) : null;
  const names = [it.name];
  const sh = SHORT[it.key];
  if (sh && sh !== it.name) names.push(sh);
  const v = valText(it);
  const vals = u ? [v + ' ' + u[1], v] : [v];
  return { names, pc: chipText(it), vals };
}
function fit(T, w, hh, capH) {
  const W = w - PADX, H = hh - 4;
  const maxFs = Math.min(34, (capH || hh) * 0.3);
  const pcW = tw(T.pc, 500) * 0.8;
  let best = null;
  const consider = (cand, score) => { if (!best || score > best.score) best = Object.assign(cand, { score }); };
  T.names.forEach((name, ni) => {
    const splits = [[name]];
    const sp = splitName(name);
    if (sp) splits.push(sp);
    for (const parts of splits) {
      const nW = Math.max(...parts.map(p => tw(p, 600)));
      const nl = parts.length;
      const nameH = nl * LH.name;
      // level 1: name only, 2: + %, 3: + value
      const levels = [
        { lv: 1, wu: nW, hu: nameH },
        { lv: 2, wu: Math.max(nW, pcW), hu: nameH + LH.pc },
      ];
      T.vals.forEach((vt, vi) => levels.push({ lv: 3, vi, vt, wu: Math.max(nW, pcW, tw(vt, 500) * 0.58), hu: nameH + LH.pc + LH.v }));
      for (const L of levels) {
        const fs = Math.min(maxFs, W / L.wu, H / (L.hu + GLYPH));
        const min = L.lv === 3 ? 15.5 : L.lv === 2 ? 11.5 : 9.5;
        if (fs < min) continue;
        // richer first; full name and unit preferred unless they cost real size; one line preferred over two
        const score = L.lv * 1000 + fs * (ni === 0 ? 1.18 : 1) * (L.vi ? 1 : 1.12) * (nl === 1 ? 1.08 : 1);
        consider({ lv: L.lv, fs, parts, vt: L.vt || null, labW: L.wu * fs, labH: L.hu * fs }, score);
      }
    }
  });
  return best;                                           // null = no label
}
// chip candidates, longest first; the last one is a bare dot (--live = 장중, ring = 마감) for tiles too small for words
const CHIP_H = 15, CHIP_FS = 11, DOT = 13;                // --fs-xs in a 15px chip (world.css .kw-chip)
function chipCands(it) {
  const open = it.status === 'OPEN';
  const texts = !open ? ['마감'] : it.delayed ? [`장중 · ${dlText(it.delayed)}`, `장중 · ${dlText(it.delayed).replace(' 지연', '')}`, '장중'] : ['장중'];
  return texts.map(t => ({ t, w: tw(t, 500) * CHIP_FS + 10 + (open ? 9 : 0), hgt: CHIP_H })).concat({ t: '', dot: true, w: DOT, hgt: DOT });
}
function placeTile(el, t) {
  const it = t.it;
  el.style.left = t.x + 'px'; el.style.top = t.y + 'px'; el.style.width = t.w + 'px'; el.style.height = t.h + 'px';
  const col = colorOf(it);
  el.style.backgroundColor = col;
  el.style.color = inkFor(col);
  el.__col = col;
  el.classList.toggle('ref', isRef(it));
  el.classList.toggle('nod', !isRef(it) && it.ratio == null);
  const [chip, lab] = el.children;
  const [nm, pc, vv] = lab.children;
  const T = tileTexts(it, t.g);
  let L = fit(T, t.w, t.h);
  // the chip sits top-left; keep it clear of the centred label, else refit the label lower, else a shorter chip, else none
  const open = it.status === 'OPEN';
  let chipC = null;
  if (t.w >= 24 && t.h >= 20) {
    for (const c of chipCands(it)) {
      if (c.w > t.w - 6) continue;
      const clear = LL => !LL || (t.h - LL.labH) / 2 >= c.hgt + 5 || (t.w - LL.labW) / 2 >= c.w + 6;
      if (clear(L)) { chipC = c; break; }
      // room above and below the label, or (narrow label) beside it
      const min = L ? L.fs * (c.dot ? 0.6 : 0.68) : 0, lvMin = L ? Math.min(L.lv, 2) : 1;
      const L2 = fit(T, t.w, t.h - 2 * (c.hgt + 5), t.h);
      if (L2 && L && L2.lv >= lvMin && L2.fs >= min) { L = L2; chipC = c; break; }
      const L3 = t.w - 2 * (c.w + 6) > 24 ? fit(T, t.w - 2 * (c.w + 6), t.h, t.h) : null;
      if (L3 && L && L3.lv >= lvMin && L3.fs >= min) { L = L3; chipC = c; break; }
    }
  }
  chip.hidden = !chipC;
  if (chipC) { chip.textContent = chipC.t; chip.className = 'kw-chip ' + (open ? 'open' : 'close') + (chipC.dot ? ' dot' : ''); }
  el.__sub = '';
  if (!L) { lab.hidden = true; return; }
  lab.hidden = false;
  lab.style.fontSize = L.fs.toFixed(1) + 'px';
  if (L.parts.length > 1) nm.replaceChildren(L.parts[0], document.createElement('br'), L.parts[1]);
  else nm.textContent = L.parts[0];
  pc.hidden = L.lv < 2; pc.textContent = T.pc;
  vv.hidden = L.lv < 3; vv.textContent = L.vt || '';
  if (L.lv >= 2) el.__sub = T.pc;
}
function ariaOf(it) {
  if (isFund(it)) {
    const pctU = isFundPct(it), up = it.change > 0, dn = it.change < 0;
    const mv = it.change == null ? '' : `, 전 영업일보다 ${up || dn ? fundChg(it).replace(/^[+−]/, '') + (pctU ? (up ? ' 올랐어요' : ' 내렸어요') : (up ? ' 늘었어요' : ' 줄었어요')) : '그대로예요'}`
      + (!pctU && it.ratio != null && (up || dn) ? ` (${pct(it.ratio)})` : '');
    return `증시 자금, ${it.name} ${valText(it)}${mv}, ${mdText(it.basDt, true) || '날짜 모름'} 기준, 금융투자협회`;
  }
  const u = unitOf(it);
  const chg = isRate(it) ? `${chgText(it)}` : `${chgText(it)} (${pct(it.ratio)})`;
  return `${it.group ? it.group + ', ' : ''}${it.name} ${valText(it)}${u ? ' ' + u[0] : ''}, 전일 대비 ${chg}, ` +
    `${it.status === 'OPEN' ? '장중' : '마감'}, ${delayText(it)}${isRef(it) ? ', 참고 지표라 색칠하지 않았어요' : ''}${it.calc ? ', 계산값' : ''}`;
}
function renderMap(d) {
  const W = els.map.clientWidth;
  if (!W) return;
  els.mapW = W;
  const Lo = computeLayout(d, W);
  els.boxes = Lo;
  els.map.style.height = Lo.H + 'px';
  const seenT = new Set(), seenG = new Set();
  for (const g of Lo.heads) {
    seenG.add(g.g.key);
    let el = els.heads.get(g.g.key);
    if (!el) { el = h('div', { class: 'kw-gh', 'aria-hidden': 'true' }, h('span', { class: 't' }), h('span', { class: 's' }), h('span', { class: 'v' })); els.heads.set(g.g.key, el); els.map.append(el); }
    el.style.left = g.x + 'px'; el.style.top = g.y + 'px'; el.style.width = g.w + 'px'; el.style.height = g.hd + 'px';
    el.hidden = !g.hd;
    const vals = g.g.items.filter(it => !isRef(it) && it.ratio != null).map(it => it.ratio);
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    el.children[0].textContent = g.g.name;
    const vt = avg == null ? '' : pct(avg);
    let room = g.w - tw(g.g.name, 700) * 12 - 16;
    const vOn = vt && room >= tw(vt, 600) * 12 + 4;
    if (vOn) room -= tw(vt, 600) * 12 + 10;
    // the group's market state when every member shares it ("장중 · 15분 지연", "마감")
    const st = new Set(g.g.items.map(it => it.status)), dl = new Set(g.g.items.map(it => it.delayed));
    const stText = st.size !== 1 ? '' : st.has('OPEN') ? (dl.size === 1 ? (g.g.items[0].delayed ? `장중 · ${dlText(g.g.items[0].delayed)}` : '장중 · 실시간') : '장중') : '마감';
    el.children[1].textContent = stText && room >= tw(stText, 500) * 11 + 6 ? stText : '';
    el.children[2].textContent = vOn ? vt : '';
    el.children[2].className = 'v ' + (avg == null ? 'flat' : cls(avg));
    el.title = avg == null ? g.g.name : `${g.g.name} · 단순 평균 ${vt}`;
    el.__sub = el.children[2].textContent;
  }
  for (const t of Lo.tiles) {
    seenT.add(t.it.key);
    let el = els.tiles.get(t.it.key);
    if (!el) {
      el = h('button', { type: 'button', class: 'kw-tile', 'data-k': t.it.key, tabindex: '-1' },
        h('span', { class: 'kw-chip', 'aria-hidden': 'true' }), h('span', { class: 'kw-lab', 'aria-hidden': 'true' }, h('span', { class: 'kw-nm' }), h('span', { class: 'kw-pc' }), h('span', { class: 'kw-v' })));
      els.tiles.set(t.it.key, el);
      els.map.append(el);
    }
    el.__t = t;
    el.setAttribute('aria-label', ariaOf(t.it));
    el.title = t.it.name;
    placeTile(el, t);
    el.classList.toggle('sel', !!(S.detail && S.detail.key === t.it.key));
  }
  for (const [k, el] of els.tiles) if (!seenT.has(k)) { el.remove(); els.tiles.delete(k); }
  for (const [k, el] of els.heads) if (!seenG.has(k)) { el.remove(); els.heads.delete(k); }
  // DOM order = reading order (group, then tile) so Tab / screen readers follow the map
  const order = Lo.tiles.map(t => els.tiles.get(t.it.key));
  order.forEach((el, i) => { if (els.map.children[i + Lo.heads.length] !== el) els.map.append(el); });
  if (!S.focusKey || !els.tiles.has(S.focusKey)) S.focusKey = Lo.tiles.length ? Lo.tiles[0].it.key : null;
  for (const [k, el] of els.tiles) el.tabIndex = k === S.focusKey ? 0 : -1;
}

/* roving focus: one tab stop for the map; arrows move to the nearest tile in that direction */
function setRoving(key) {
  if (!els.tiles.has(key)) return;
  S.focusKey = key;
  for (const [k, el] of els.tiles) el.tabIndex = k === key ? 0 : -1;
}
function onMapKey(e) {
  const cur = e.target.closest('.kw-tile');
  if (!cur || !els.boxes) return;
  const list = els.boxes.tiles;
  let next = null;
  if (e.key === 'Home') next = list[0];
  else if (e.key === 'End') next = list[list.length - 1];
  else if (/^Arrow/.test(e.key)) {
    const a = cur.__t, ax = a.x + a.w / 2, ay = a.y + a.h / 2;
    let bestS = Infinity;
    for (const b of list) {
      if (b === a) continue;
      const bx = b.x + b.w / 2, by = b.y + b.h / 2;
      let main, cross;
      if (e.key === 'ArrowRight') { if (b.x < a.x + a.w - 1) continue; main = b.x - (a.x + a.w); cross = Math.max(0, Math.max(a.y, b.y) < Math.min(a.y + a.h, b.y + b.h) ? 0 : Math.abs(by - ay)); }
      else if (e.key === 'ArrowLeft') { if (b.x + b.w > a.x + 1) continue; main = a.x - (b.x + b.w); cross = Math.max(a.y, b.y) < Math.min(a.y + a.h, b.y + b.h) ? 0 : Math.abs(by - ay); }
      else if (e.key === 'ArrowDown') { if (b.y < a.y + a.h - 1) continue; main = b.y - (a.y + a.h); cross = Math.max(a.x, b.x) < Math.min(a.x + a.w, b.x + b.w) ? 0 : Math.abs(bx - ax); }
      else { if (b.y + b.h > a.y + 1) continue; main = a.y - (b.y + b.h); cross = Math.max(a.x, b.x) < Math.min(a.x + a.w, b.x + b.w) ? 0 : Math.abs(bx - ax); }
      const s = main + cross * 2 + (e.key === 'ArrowRight' || e.key === 'ArrowLeft' ? Math.abs(by - ay) : Math.abs(bx - ax)) * 0.1;
      if (s < bestS) { bestS = s; next = b; }
    }
    if (!next) { e.preventDefault(); return; }
  } else return;
  e.preventDefault();
  const el = els.tiles.get(next.it.key);
  if (el) { setRoving(next.it.key); el.focus(); }
}

/* legend: colour scale as the heatmap draws it, the VIX note, what size means */
// KH.range() is the range the colours use (§3-27: 자동 steps such as ±4 / ±7 % too); older templates: probe the scale
function rangeNow() {
  try { if (typeof KH.range === 'function') { const R = +KH.range(); if (R > 0) return R; } } catch (e) { /* fall back */ }
  try { const hi = KH.colorOf(1000, 'world'); for (const R of [1, 2, 3, 5, 10, 20, 30]) if (KH.colorOf(R, 'world') === hi) return R; } catch (e) { /* no colour scale */ }
  return null;
}
const rangeIsAuto = () => { try { return typeof KH.rangeInfo === 'function' && !!KH.rangeInfo().auto; } catch (e) { return false; } };
function renderLegend(d) {
  const P = (KH.palette && KH.palette('world').stops) || [];
  const R = rangeNow();
  const grad = P.length ? h('span', { class: 'grad', style: `background:linear-gradient(90deg,${P.join(',')})`, 'aria-hidden': 'true' }) : null;
  // 구역마다 (지표 under 자동): the ends differ per zone, so the bar has no ±N ticks; what each zone uses is listed once here (the
  // saved picture's legend reads this row — its tile map has no zone tags) and beside every group's name in the list.
  // A picked range (후속 ①): the tab's −R · +R as before, and a 구역 범위 row naming the zones that keep their own (금리 "±7bp 자동")
  const zon = zonesShown() ? zoneList() : [];
  const zs = zon.length && Z.auto ? zon : null, own = zon.length && !Z.auto ? zon : null;
  const zrow = list => h('span', { class: 'lg kw-lgz', title: own ? '금리는 칩 글자가 bp라서 고른 범위와 따로, bp 변화로 자동 범위를 써요' : null },
    h('span', { class: 'k', text: '구역 범위' }), list.map(z => h('span', { class: 'kw-lgzi' }, z.name + ' ', h('b', { text: zoneTxt(z) }), own ? ' 자동' : null)));
  const kids = zs ? [
    h('span', { class: 'lg' }, h('span', { class: 'k', text: '색' }), h('b', { text: '오르내림' }),
      h('span', { class: 'rauto', title: `구역마다 그 구역 값의 95%가 들어가게 맞춰요 · 금리는 bp 변화로 색칠해요 · ${zs.map(z => z.name + ' ' + zoneTxt(z)).join(' · ')}`, text: '자동 · 구역마다' }),
      grad, h('span', { class: 'note', text: '양 끝 = 구역 범위' })),
    zrow(zs),
  ] : [h('span', { class: 'lg' }, h('span', { class: 'k', text: '색' }), h('b', { text: '오늘 등락률' }),
    R && rangeIsAuto() ? h('span', { class: 'rauto', title: `화면 등락률의 95%가 들어가게 맞춰요 · 지금 ±${R}%`, text: `자동 ±${R}%` }) : null,
    R ? h('span', { class: 'tk', text: `${MINUS}${R}%` }) : null,
    grad,
    R ? h('span', { class: 'tk', text: `+${R}%` }) : null)];
  if (own) kids.push(zrow(own));
  if (d.all.some(isRef)) kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw kw-refsw' }), h('span', { text: 'VIX는 참고 지표라 색칠하지 않아요' })));
  if (S.mode === 'geo') {
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw kw-nonesw' }), h('span', { text: '지수 없는 나라' })));
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'kw-sd open', 'aria-hidden': 'true' }), h('span', { text: '장중' }),
      h('i', { class: 'kw-sd close', 'aria-hidden': 'true' }), h('span', { text: '마감' })));
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'sw kw-nightsw', 'aria-hidden': 'true' }), h('span', { text: '어두운 쪽은 지금 밤' })));
    kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '나라 색' }), h('b', { text: '대표 지수 등락률' }), h('span', { class: 'note', text: '눌러서 그 나라 지수를 모두 봐요' })));
    els.legend.replaceChildren(...kids);
    return;
  }
  if (S.mode === 'list') {
    kids.push(h('span', { class: 'lg' }, h('i', { class: 'kw-sd open', 'aria-hidden': 'true' }), h('span', { text: '장중' }),
      h('i', { class: 'kw-sd close', 'aria-hidden': 'true' }), h('span', { text: '마감' })));
    if (zs) kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '막대' }), h('b', { text: '가운데가 0 · 끝이 구역 범위' })));
    else if (R) kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '막대' }), h('b', { text: `가운데가 0 · 끝이 ±${R}%` + (own ? own.map(z => ` · ${z.name} ${zoneTxt(z)}`).join('') : '') })));
    els.legend.replaceChildren(...kids);
    return;
  }
  kids.push(h('span', { class: 'lg' }, h('span', { class: 'kw-chip-l open', 'aria-hidden': 'true', text: '장중' }), h('span', { class: 'kw-chip-l close', 'aria-hidden': 'true', text: '마감' }),
    h('span', { class: 'sr', text: '타일 왼쪽 위 표시: 장중 또는 마감, 지연 시간' })));
  kids.push(h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '대표 지수를 크게' }), h('span', { class: 'note', text: '시가총액과는 관계없어요' })));
  if (S.kind === 'commodity') kids[kids.length - 1] = h('span', { class: 'lg right' }, h('span', { class: 'k', text: '크기' }), h('b', { text: '주요 품목을 크게' }), h('span', { class: 'note', text: '거래 규모와는 관계없어요' }));
  els.legend.replaceChildren(...kids);
}

/* ───────── list view (the default, AGENTS §3-4 "목록이 기본") ─────────
   Sections per group (or one ranked list), laid out in 1–3 columns by the list's width; rows are kept per key and
   updated in place on every refresh, so focus and scroll stay put. Wide rows are one line (name · state · value ·
   change · % chip · bar); narrow columns get a two-line row (name / state, value / change). */
const PLACE = {
  DJI: '뉴욕', INX: '뉴욕', IXIC: '뉴욕', NDX: '뉴욕', SOX: '뉴욕', DJT: '뉴욕', RUT: '뉴욕',
  EScv1: '시카고', NQcv1: '시카고', YMcv1: '시카고', RTYcv1: '시카고', VIX: '시카고',
  STOXX50E: '유로존', GDAXI: '프랑크푸르트', FTSE: '런던', FCHI: '파리', AEX: '암스테르담', IBEX: '마드리드', FTMIB: '밀라노',
  OMXS30: '스톡홀름', BFX: '브뤼셀', PSI20: '리스본', ISEQ: '더블린', BUX: '부다페스트',
  N225: '도쿄', TOPX: '도쿄', SSEC: '상하이', SZSC: '선전', CSI300: '상하이·선전', HSI: '홍콩', HSCE: '홍콩', TWII: '타이베이',
  BSESN: '뭄바이', VNI: '호찌민', HNXI: '하노이', AXJO: '시드니', JKSE: '자카르타', KLSE: '쿠알라룸푸르',
  BVSP: '상파울루', MXX: '멕시코시티', KOSPI: '서울', KOSDAQ: '서울',
};
// one-line rows: name (≥ NAME_MIN) · state 64 · value · change · chip 66 · bar 48, gaps 8, row padding 12, section 14 (CSS)
// the value / change cells' type (world.css: .kw-lr --fs-md · .kw-lc --fs-sm · two-line rows' value --fs-lg)
const FS_V = 13, FS_C = 12, FS_VC = 14;
const NAME_MIN = 118, FIXED_W = 64 + 66 + 48 + 5 * 8 + 12 + 14, MIN_COL_C = 300, COL_GAP = 12;
const ROW_H = 36, ROW_HC = 44, HEAD_H = 41, SEC_PAD = 12;      // --h-row rows (two-line rows 44 on phones), the head = --h-row + rule + --space-2
const placeOf = it => PLACE[it.key] || cityOf(it, null) || '';
function listSub(it, flat) {
  if (isFund(it)) return FUND_SUB[it.fkey] || '';
  if (isMacro(it)) return FX_SUB[it.key] || '';                 // the section note covers 원/○; 계산값 sits in the state column
  const u = S.kind === 'commodity' ? unitOf(it) : null;
  if (!flat && isFut(it)) return '선물';
  if (flat) return [it.group, u ? u[1] : null].filter(Boolean).join(' · ');
  return u ? u[1] : placeOf(it);
}
function avgOf(items) {
  const v = items.filter(it => !isRef(it) && it.ratio != null).map(it => it.ratio);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
function stateOf(items) {
  let o = 0, c = 0;
  for (const it of items) if (it.status === 'OPEN') o++; else c++;
  if (o && c) return { open: true, text: `장중 ${o} · 마감 ${c}` };
  if (!o) return { open: false, text: '마감' };
  const dl = new Set(items.map(it => it.delayed));
  return { open: true, text: dl.size === 1 ? (items[0].delayed ? `장중 · ${dlText(items[0].delayed)}` : '장중 · 실시간') : '장중' };
}
// text on a palette colour: white or black, whichever has more contrast (the worst case is 4.58:1)
const INK_DARK = '#000';
function rgbOf(c) {
  let m = /^#([0-9a-f]{6})$/i.exec(c);
  if (m) { const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  m = /^#([0-9a-f]{3})$/i.exec(c);
  if (m) return m[1].split('').map(x => parseInt(x + x, 16));
  m = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(c);
  return m ? [+m[1], +m[2], +m[3]] : null;
}
function luma(rgb) {
  const L = rgb.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * L[0] + 0.7152 * L[1] + 0.0722 * L[2];
}
const DARK_Y = luma(rgbOf(INK_DARK));
function inkOn(c) {
  const rgb = rgbOf(String(c || ''));
  if (!rgb) return '#fff';
  const y = luma(rgb);
  return 1.05 / (y + 0.05) >= (y + 0.05) / (DARK_Y + 0.05) ? '#fff' : INK_DARK;
}
// text on a tile / country: dark themes keep the white label with its shadow (the CSS default, '' here); light themes pick
// black or white per colour (themes.md §8: at least 4.58:1 for every palette) and drop the shadow
function inkFor(c) { return tok().light ? inkOn(c) : ''; }
function labInk(el, col) {
  if (!tok().light || !col) { el.style.color = ''; el.style.textShadow = ''; return; }
  const k = inkOn(col);
  el.style.color = k;
  el.style.textShadow = k === '#fff' ? '0 0 2px rgba(0,0,0,.45)' : '0 0 2px rgba(255,255,255,.55)';
}

// columns by width: as many one-line columns as fit (≤ 3), else two two-line columns (tablets), else one column
function listGeom(W, minWide) {
  for (const n of [3, 2]) if ((W - (n - 1) * COL_GAP) / n >= minWide) return { n, compact: false };
  if ((W - COL_GAP) / 2 >= MIN_COL_C) return { n: 2, compact: true };
  return { n: 1, compact: W < minWide };
}
// sections → columns with heights as even as possible. Contiguous runs keep the reading order; when that leaves one
// column much taller, the biggest sections are spread first (each column still lists its sections in the original order).
function distribute(secs, n, rowH) {
  const hs = secs.map(s => (s.head ? HEAD_H : 6) + s.items.length * rowH + SEC_PAD + (s.key === 'funds' ? 24 : 0) + kxHeight(s.key, rowH === ROW_HC));
  const colH = idx => idx.reduce((a, i) => a + hs[i], 0) + Math.max(0, idx.length - 1) * COL_GAP;
  n = Math.min(n, secs.length);
  if (n <= 1) return [secs];
  let best = null;
  const rec = (start, left, acc) => {
    if (left === 1) {
      const cols = acc.concat([secs.map((s, i) => i).slice(start)]);
      const m = Math.max(...cols.map(colH));
      if (!best || m < best.m) best = { m, cols };
      return;
    }
    for (let end = start + 1; end <= secs.length - left + 1; end++) rec(end, left - 1, acc.concat([secs.map((s, i) => i).slice(start, end)]));
  };
  rec(0, n, []);
  const order = secs.map((s, i) => i).sort((a, b) => hs[b] - hs[a] || a - b);
  const cols = Array.from({ length: n }, () => []);
  for (const i of order) cols.reduce((m, c) => colH(c) < colH(m) ? c : m).push(i);
  cols.forEach(c => c.sort((a, b) => a - b));
  cols.sort((a, b) => a[0] - b[0]);
  const lpt = Math.max(...cols.map(colH));
  const pick = best && best.m <= lpt * 1.08 ? best.cols : cols;
  return pick.map(c => c.map(i => secs[i]));
}
/* 지역순 sections. A future belongs with its country's index and VIX is the US VIX (사용자 2026-11-13 22:26), so on the index
   tab the Worker's 미국 선물 and 참고 groups are folded into 미국 here (the Worker keeps its groups): cash indices first, then
   the futures ("선물" tag), then VIX last (a grey 참고 row). `cash` = the coloured indices — the only rows the 미국 header's
   average and 장중/마감 summary use; futures trade almost around the clock and VIX is not a price index. */
function regionSections(d) {
  const secs = d.groups.map(g => ({ key: g.key, name: g.name, head: true, items: g.list, cash: g.list, ref: g.list.every(isRef), rank: 0 }));
  if (S.kind !== 'index') return secs;
  const us = secs.find(s => s.key === 'us');
  if (!us) return secs;
  const fold = secs.filter(s => s.key === 'usf' || s.key === 'ref');
  us.items = us.items.concat(...fold.filter(s => s.key === 'usf').map(s => s.items), ...fold.filter(s => s.key === 'ref').map(s => s.items));
  return secs.filter(s => !fold.includes(s));
}
/* blocks of columns. The 지표 tab with 환율 · 금리 (§3-28) has two captioned blocks — 원자재 (에너지 · 금속 · 농산물, or their
   등락률순 ranking) and 환율 · 금리 (shown first since 2026-11-14; always by group: a yield's bp and a currency's % do not rank against a commodity's %).
   Every other case is one block without a caption, laid out exactly as before. */
function buildColumns(d, geo) {
  const rowH = geo.compact ? ROW_HC : ROW_H;
  const secs = regionSections(d);
  const macro = secs.filter(s => MACRO_NOTE[s.key]);
  // 구역마다 + 등락률순: the ranked rows mix 에너지 · 금속 · 농산물, so the block gets its caption to carry each group's range (an older
  // Worker without 환율 · 금리 too; nothing changes under a picked range)
  if (!macro.length && Z && Z.auto && S.sort === 'pct' && S.kind === 'commodity') return [{ key: 'cm', title: '원자재', cols: ranked(d.all, geo) }];
  if (!macro.length) return [{ key: 'all', title: null, cols: S.sort !== 'pct' ? distribute(secs, geo.n, rowH) : ranked(d.all, geo) }];
  const base = secs.filter(s => !MACRO_NOTE[s.key]);
  // 환율 · 금리를 원자재보다 먼저 — 사용자 2026-11-14 02:11 "지표 순서도 환율/금리를 원자재보다 먼저 보이게"
  const blocks = [{ key: 'mx', title: macro.map(s => s.name).join(' · '), cols: distribute(macro, geo.n, rowH) }];
  if (base.length) blocks.push({ key: 'cm', title: '원자재', cols: S.sort !== 'pct' ? distribute(base, geo.n, rowH) : ranked(d.all.filter(it => !isMacro(it)), geo) });
  return blocks;
}
// 등락률순: one ranked list (missing values last, ties in the Worker's order), split evenly over the columns; VIX at the end
function ranked(all, geo) {
  const rv = it => it.ratio == null ? -Infinity : it.ratio;
  const main = all.filter(it => !isRef(it)).sort((a, b) => rv(b) - rv(a) || a.ix - b.ix);
  const refs = all.filter(isRef);
  const n = Math.max(1, Math.min(geo.n, Math.ceil(main.length / 4)));
  const per = Math.ceil(main.length / n);
  const cols = [];
  for (let c = 0; c < n; c++) {
    const items = main.slice(c * per, (c + 1) * per);
    if (!items.length) continue;
    const a = c * per + 1, b = c * per + items.length;
    cols.push([{ key: 'rank' + c, name: c === 0 ? `등락률 높은 순 · ${a}–${b}위` : `${a}–${b}위`, head: true, items, rank: a, flat: true }]);
  }
  if (refs.length) (cols[cols.length - 1] || (cols[0] = [])).push({ key: 'ref', name: '참고', head: true, items: refs, ref: true, flat: true });
  return cols;
}
function rowEl(it) {
  let el = els.rows.get(it.key);
  if (!el) {
    el = h('button', { type: 'button', class: 'kw-lr', 'data-k': it.key, tabindex: '-1' },
      h('span', { class: 'kw-ln', 'aria-hidden': 'true' }, h('span', { class: 'rk' }), h('span', { class: 'nm' }), h('span', { class: 'sub' })),
      h('span', { class: 'kw-ls', 'aria-hidden': 'true' }, h('i', { class: 'kw-sd' }), h('span', { class: 'st' }), h('span', { class: 'sub2' })),
      h('span', { class: 'kw-lv', 'aria-hidden': 'true' }),
      h('span', { class: 'kw-lc', 'aria-hidden': 'true' }),
      h('span', { class: 'kw-lp', 'aria-hidden': 'true' }, h('span', { class: 'kw-pchip' }, h('span', { class: 'kw-pt' }))),
      h('span', { class: 'kw-lb', 'aria-hidden': 'true' }, h('i')));
    els.rows.set(it.key, el);
  }
  return el;
}
// the number a chip's text stands for (its direction when it changes): bp for a yield, %p for a share, else the % change
const chipNum = it => isRate(it) ? bpOf(it) : isFundPct(it) ? it.change : it.ratio;
function fillRow(el, it, sub, rank, R) {
  const [ln, ls, lv, lc, lp, lb] = el.children;
  const [rk, nm, sb] = ln.children;
  const ref = isRef(it), open = it.status === 'OPEN';
  rk.textContent = rank ? String(rank) : '';
  rk.hidden = !rank;
  if (nm.textContent !== it.name) nm.textContent = it.name;
  const subText = ref ? '참고' : sub || '';
  sb.textContent = subText;
  sb.hidden = !subText;
  sb.className = 'sub' + (ref || (isFut(it) && !rank) ? ' tag' : '');
  ls.children[0].className = 'kw-sd ' + (open ? 'open' : 'close');
  ls.children[0].hidden = isFund(it);                    // 증시 자금 does not trade: its state column is the business day it is for
  // 달러/엔 = a cross of two 하나은행 rates (§3-28): "계산값" where the others say 실시간 (the dot still says 장중 / 마감)
  ls.children[1].textContent = isFund(it) ? mdShort(it.basDt) : it.calc ? '계산값' : open ? (it.delayed ? dlText(it.delayed) : '실시간') : '마감';
  ls.children[1].className = 'st' + (open && it.delayed ? ' dl' : '');
  ls.children[2].textContent = ref ? '' : sub || '';
  // a yield: the chip carries its change in bp, the change column stays empty (the same number twice says nothing); same for a share in %
  const v = valText(it), c = chipIsChange(it) ? '' : chgText(it), p = chipText(it);
  // values that changed since the last refresh swap in place (KH.ui.swap, design.md §6-4: up from below, down from above); the
  // first fill of a row and a redraw with the same numbers are written at once (P4). Colours and bars land at once (data, no tween)
  swapTo(lv, v, it.value);
  lc.className = 'kw-lc ' + (ref || it.change == null ? 'flat' : cls(it.change));   // before the swap: it adds its own class
  swapTo(lc, c, it.change);
  const chip = lp.firstChild;
  swapTo(chip.firstChild, p, chipNum(it));
  const col = ref ? null : colorOf(it);
  // 구역마다: the chip's colour and the bar both read the zone's number (a yield's bp) on the zone's range; else the % on the tab's
  const cr = colRange(it), bv = cr.v, bR = cr.R || R;
  chip.style.backgroundColor = col || '';
  chip.style.color = col ? inkOn(col) : '';
  chip.className = 'kw-pchip' + (ref ? ' ref' : bv == null ? ' nod' : '');
  el.__col = col;
  const bar = lb.firstChild;
  const frac = bv == null || !isFinite(bv) || !bR ? 0 : Math.min(Math.abs(bv) / bR, 1) * 50;
  bar.style.width = frac.toFixed(2) + '%';
  bar.style.left = bv >= 0 ? '50%' : '';
  bar.style.right = bv < 0 ? '50%' : '';
  bar.style.backgroundColor = ref ? '' : col || '';
  bar.className = ref ? 'ref' : '';
  el.classList.toggle('ref', ref);
  el.title = it.name;
  el.setAttribute('aria-label', ariaOf(it) + (rank ? `, ${rank}위` : ''));
  el.classList.toggle('sel', !!(S.detail && S.detail.key === it.key));
}
// 구역마다: the zone's range beside its name, small, in the legend's "자동 ±N%" tag look (thin ring, no amber); a ranked section (등락률순)
// mixes groups, so its block caption carries them instead (fillZoneCaption)
const zoneTitle = z => Z && !Z.auto
  ? `자동 · 금리는 칩 글자가 bp라서 고른 범위와 따로, bp 변화의 95%가 들어가게 맞춘 색 범위 ${zoneTxt(z)}`
  : `자동 · ${z.key === 'forced' ? '반대매매 두 줄(금액 · 비중)' : '이 구역'} 값의 95%가 들어가게 맞춘 색 범위 ${zoneTxt(z)}${z.unit === 'bp' ? ' (금리는 bp 변화로 색칠해요)' : ''}`;
function fillZoneTag(el, z, name) {
  const t = z ? (name ? `${z.name} ` : '') + zoneTag(z) : '';
  if (el.__t !== t) { el.__t = t; el.replaceChildren(...(z ? [h('span', { class: 'sr', text: '색 범위 ' }), t] : [])); }
  if (z) el.title = zoneTitle(z); else el.removeAttribute('title');
  el.hidden = !z;
}
function fillHead(sec, hd) {
  const [t, rg, rg2, s, a] = hd.children;
  t.textContent = sec.name;
  // the section's zones in its rows' order: one for most groups, two for 증시 자금 ("±3%" · "반대매매 ±30%" — 후속 ②); the first
  // goes without its name (the head says it), the next one names itself. Only while the 지표 tab draws them
  const zs = zonesShown() && !sec.flat ? [...new Set(sec.items.filter(it => !isRef(it)).map(it => zoneOf(it)).filter(Boolean))] : [];
  fillZoneTag(rg, zs[0] || null);
  fillZoneTag(rg2, zs[1] || null, true);
  a.classList.toggle('note', !!MACRO_NOTE[sec.key]);
  if (sec.flat && !sec.ref) { s.replaceChildren(); a.replaceChildren(); return; }
  const cash = sec.cash || sec.items;                    // 미국: only the cash indices speak for the section
  if (sec.key === 'funds') {
    // a day-old statistic: the business day it is for, instead of 장중 / 마감
    const dt = sec.items.map(it => it.basDt).filter(Boolean).sort().pop();
    s.replaceChildren(dt ? `${mdText(dt, true)} 기준` : '');
  } else {
    const st = stateOf(cash);
    s.replaceChildren(h('i', { class: 'kw-sd ' + (st.open ? 'open' : 'close'), 'aria-hidden': 'true' }), st.text);
  }
  if (sec.ref) { a.replaceChildren(h('small', { text: '색칠하지 않는 지표' })); return; }
  // 환율 · 금리: an average of unlike things says nothing — the section says how to read it instead (§3-28)
  if (MACRO_NOTE[sec.key]) { a.replaceChildren(h('small', { class: 'kw-shn', text: MACRO_NOTE[sec.key] })); return; }
  const avg = avgOf(cash);
  put(a, avg == null ? null : h('small', { text: cash.length < sec.items.length ? '지수 평균' : '평균' }), avg == null ? null : h('b', { class: cls(avg), text: pct(avg) }));
}
// 등락률순 under 구역마다: the 원자재 caption lists each group's range ("에너지 ±3%"), in the groups' order; empty otherwise
function fillZoneCaption(L, d) {
  for (const bt of L.querySelectorAll('.kw-bt')) {
    const box = bt.querySelector('.kw-btz');
    if (!box) continue;
    const want = zonesShown() && Z.auto && S.sort === 'pct' && bt.dataset.b === 'cm'
      ? [...new Set(d.all.filter(it => !isMacro(it) && !isRef(it)).map(it => zoneKeyOf(it)))].map(k => Z.zones.get(k)).filter(Boolean) : [];
    const sig = want.map(z => z.name + zoneTag(z)).join('|');
    if (box.__sig !== sig) {
      box.__sig = sig;
      box.replaceChildren(...want.map(z => { const el = h('span', { class: 'kw-rg' }); fillZoneTag(el, z, true); return el; }));
    }
    box.hidden = !want.length;
  }
}
function renderList(d) {
  const L = els.list;
  const W = L.clientWidth;
  if (!W) return;
  els.listW = W;
  // value / change columns: as wide as the widest text, so numbers line up across sections and columns
  let vw = 0, cw = 0;
  for (const it of d.all) { vw = Math.max(vw, tw(valText(it), 500)); if (!chipIsChange(it)) cw = Math.max(cw, tw(chgText(it), 500)); }   // a yield's change column is empty
  const geo = listGeom(W, NAME_MIN + FIXED_W + Math.ceil(vw * FS_V + 4) + Math.ceil(cw * FS_C + 4));
  const blocks = buildColumns(d, geo);
  const cols = blocks.flatMap(b => b.cols);
  const fsV = geo.compact ? FS_VC : FS_V, fsC = FS_C;
  L.style.setProperty('--kw-n', String(Math.max(1, ...blocks.map(b => b.cols.length))));
  L.style.setProperty('--kw-vw', Math.ceil(vw * fsV + 4) + 'px');
  L.style.setProperty('--kw-cw', Math.ceil(cw * fsC + 4) + 'px');
  L.style.setProperty('--kw-vcw', Math.ceil(Math.max(vw * fsV, cw * fsC) + 4) + 'px');
  L.classList.toggle('compact', geo.compact);
  L.classList.toggle('flat', S.sort === 'pct');
  const sig = [S.kind, S.sort, geo.compact, blocks.map(b => b.key + '=' + b.cols.map(c => c.map(s => s.key + ':' + s.items.map(it => it.key).join(',')).join(';')).join('/')).join('#')].join('|');
  const R = rangeNow();
  const subs = new Map();
  for (const col of cols) for (const sec of col) {
    // a place shared by every row of a section (미국 · 뉴욕) says nothing: leave it out
    const ss = sec.items.map(it => listSub(it, sec.flat));
    const base = ss.filter((x, i) => !isFut(sec.items[i]) && !isRef(sec.items[i]));
    const same = !sec.flat && base.length > 1 && base.every(x => x === base[0]) && S.kind !== 'commodity';
    sec.items.forEach((it, i) => subs.set(it.key, same && !isFut(it) ? '' : ss[i]));
  }
  if (sig !== els.listSig) {
    // structure changed (first draw, sort, width class, a new order in 등락률순): rebuild the shells, keep the row elements
    const ae = document.activeElement;
    const fk = ae && ae.classList && ae.classList.contains('kw-lr') && L.contains(ae) ? ae.dataset.k : null;
    const sy = scrollY;
    const keep = new Set(d.all.map(it => it.key));
    for (const [k, el] of els.rows) if (!keep.has(k)) { el.remove(); els.rows.delete(k); }
    // a captioned block (지표: 원자재 / 환율 · 금리) spans the grid row; its sections' headings sit one level below the caption
    L.replaceChildren(...blocks.flatMap(b => [
      b.title ? h('h3', { class: 'kw-bt', 'data-b': b.key }, h('span', { class: 'kw-btt', text: b.title }), h('span', { class: 'kw-btz', hidden: true })) : null,
      ...b.cols.map(col => h('div', { class: 'kw-col', 'data-b': b.key }, col.map(sec => {
        const id = `kw-sh-${S.kind}-${sec.key}`;
        const hd = h(b.title ? 'h4' : 'h3', { class: 'kw-sh', id }, h('span', { class: 't' }), h('span', { class: 'kw-rg', hidden: true }), h('span', { class: 'kw-rg', hidden: true }),
          h('span', { class: 's' }), h('span', { class: 'a' }));
        const el = h('section', { class: 'kw-sec' + (sec.ref ? ' ref' : ''), 'data-g': sec.key, 'aria-labelledby': id }, hd,
          h('div', { class: 'kw-rows' }, sec.items.map(rowEl)),
          sec.key === 'funds' ? h('p', { class: 'kw-fsrc', text: FUND_SRC }) : null,
          KX_SEC[sec.key] && S.kind === 'commodity' ? h('div', { class: 'kw-kx', 'data-kx': KX_SEC[sec.key], hidden: true }) : null);   // 수출입은행 고시
        el.__sec = sec;
        return el;
      })))]).filter(Boolean));
    els.listSig = sig;
    if (fk && els.rows.has(fk) && document.activeElement !== els.rows.get(fk)) els.rows.get(fk).focus({ preventScroll: true });
    if (scrollY !== sy) scrollTo(scrollX, sy);
  }
  // fill in place
  fillZoneCaption(L, d);
  let kxMoved = false;
  for (const secEl of L.querySelectorAll('.kw-sec')) {
    const old = secEl.__sec;
    const sec = cols.flat().find(s => s.key === old.key) || old;
    secEl.__sec = sec;
    fillHead(sec, secEl.firstChild);
    sec.items.forEach((it, i) => fillRow(els.rows.get(it.key), it, subs.get(it.key), sec.flat && !sec.ref ? sec.rank + i : 0, R));
    const kx = secEl.querySelector(':scope > .kw-kx');
    if (kx && fillKx(kx, kx.dataset.kx, geo.compact)) kxMoved = true;
  }
  if (kxMoved && !els.kxRe) { els.kxRe = true; schedRender(); } else if (!kxMoved) els.kxRe = false;   // the columns balance on the measured height (once)
  if (!S.listFocus || !els.rows.has(S.listFocus)) S.listFocus = cols.length && cols[0][0] ? cols[0][0].items[0].key : null;
  for (const [k, el] of els.rows) el.tabIndex = k === S.listFocus ? 0 : -1;
  // a place or unit that would be cut is left out, so the name keeps its room (one layout read for all rows)
  if (!geo.compact) {
    const subEls = [...L.querySelectorAll('.kw-ln .sub:not(.tag)')];
    for (const x of subEls) x.classList.remove('cut');
    const cut = subEls.filter(x => !x.hidden && x.scrollWidth > x.clientWidth);
    for (const x of cut) x.classList.add('cut');
  }
}
function setListFocus(key) {
  if (!els.rows.has(key)) return;
  S.listFocus = key;
  for (const [k, el] of els.rows) el.tabIndex = k === key ? 0 : -1;
}
// one tab stop for the list; ↑/↓ row by row (across sections), ←/→ to the nearest row of the next column, Home/End
function onListKey(e) {
  const cur = e.target.closest('.kw-lr');
  if (!cur) return;
  const rows = [...els.list.querySelectorAll('.kw-lr')];
  const i = rows.indexOf(cur);
  let next = null;
  if (e.key === 'ArrowDown') next = rows[i + 1];
  else if (e.key === 'ArrowUp') next = rows[i - 1];
  else if (e.key === 'Home') next = rows[0];
  else if (e.key === 'End') next = rows[rows.length - 1];
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const here = cur.closest('.kw-col');
    const cols = [...els.list.querySelectorAll('.kw-col')].filter(c => c.dataset.b === here.dataset.b);   // within its block
    const col = cols[cols.indexOf(here) + (e.key === 'ArrowRight' ? 1 : -1)];
    if (col) {
      const y = cur.getBoundingClientRect().top;
      let bd = Infinity;
      for (const r of col.querySelectorAll('.kw-lr')) { const dd = Math.abs(r.getBoundingClientRect().top - y); if (dd < bd) { bd = dd; next = r; } }
    }
  } else return;
  e.preventDefault();
  if (next) { setListFocus(next.dataset.k); next.focus(); }
}

/* ───────── world map (해외 지수 · 지도, AGENTS §3-4) ─────────
   Countries filled with KH.colorOf(their representative index), Natural Earth projection, no Antarctica.
   Geometry: world-atlas 2.0.2 countries-110m (TopoJSON, Natural Earth, public domain), fetched from jsDelivr the first
   time the map view opens, checked with SRI. If it cannot be had, the list stands in with a note. */
const ATLAS = {
  url: 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json',
  sri: 'sha384-yOCJ+8ShBm8UDqtAVtAvxTDDf4gXo5edxl/YG0FmVC5OTmqVLl7utuVGBDEeZWHf',
};
const GEO = { state: 'idle', features: null, err: null };          // idle | loading | ready | failed
// representative index first (AGENTS list); `at` = where the label or leader line points (lon, lat);
// `col` = callout column for small or crowded countries, `big` = label inside the country
const COUNTRIES = [
  { id: '840', name: '미국', keys: ['INX', 'DJI', 'IXIC', 'NDX', 'SOX', 'DJT', 'RUT'], at: [-99, 39.5], big: true },
  { id: '484', name: '멕시코', keys: ['MXX'], at: [-102.5, 24], big: true },
  { id: '076', name: '브라질', keys: ['BVSP'], at: [-51.5, -10], big: true },
  { id: '372', name: '아일랜드', keys: ['ISEQ'], at: [-8, 53.2], col: 'atl' },
  { id: '826', name: '영국', keys: ['FTSE'], at: [-1.6, 52.6], col: 'atl' },
  { id: '528', name: '네덜란드', keys: ['AEX'], at: [5.6, 52.3], col: 'atl' },
  { id: '056', name: '벨기에', keys: ['BFX'], at: [4.6, 50.6], col: 'atl' },
  { id: '250', name: '프랑스', keys: ['FCHI'], at: [2.4, 46.8], col: 'atl' },
  { id: '620', name: '포르투갈', keys: ['PSI20'], at: [-8.1, 39.7], col: 'atl' },
  { id: '724', name: '스페인', keys: ['IBEX'], at: [-3.6, 40.2], col: 'atl' },
  { id: '752', name: '스웨덴', keys: ['OMXS30'], at: [15.5, 61], col: 'eur' },
  { id: '276', name: '독일', keys: ['GDAXI'], at: [10.4, 51], col: 'eur' },
  { id: '348', name: '헝가리', keys: ['BUX'], at: [19.3, 47.1], col: 'eur' },
  { id: '380', name: '이탈리아', keys: ['FTMIB'], at: [12.4, 43], col: 'eur' },
  { id: '356', name: '인도', keys: ['BSESN'], at: [78.5, 21.5], big: true },
  { id: '156', name: '중국', keys: ['SSEC', 'SZSC', 'CSI300'], at: [101, 32], big: true },
  { id: '410', name: '한국', keys: ['KOSPI', 'KOSDAQ'], at: [127.8, 36.4], col: 'kor' },
  // 유로스톡스 50 has no single country: a chip of its own in the Europe callout column (사용자 2026-11-13 22:26), its leader
  // line ending in the middle of the euro area; no country is painted for it (no map path with this id)
  { id: 'EZ', name: '유로존', keys: ['STOXX50E'], at: [8.6, 49.4], col: 'eur', area: true },
  { id: '392', name: '일본', keys: ['N225', 'TOPX'], at: [138.6, 36.4], col: 'pac' },
  { id: '158', name: '대만', keys: ['TWII'], at: [121, 23.7], col: 'pac' },
  { id: '344', name: '홍콩', keys: ['HSI', 'HSCE'], at: [114.17, 22.3], col: 'pac', marker: true },
  { id: '704', name: '베트남', keys: ['VNI', 'HNXI'], at: [106.3, 15.2], col: 'pac' },
  { id: '458', name: '말레이시아', keys: ['KLSE'], at: [101.8, 3.9], col: 'pac' },
  { id: '360', name: '인도네시아', keys: ['JKSE'], at: [113.6, -1], big: true },
  { id: '036', name: '호주', keys: ['AXJO'], at: [134, -25], big: true },
];
// callout columns: x from a meridian at a reference latitude, chips grow away from the map ('end' = to the left)
// (pac sits east of Japan's coast, so on narrower maps the clamped column still clears Honshu)
const GCOLS = { atl: { lon: -22, lat: 48, align: 'end' }, eur: { lon: 32, lat: 50, align: 'start' }, pac: { lon: 153, lat: 25, align: 'start' }, kor: { lon: 121.5, lat: 45, align: 'end', fixY: 44 } };
const GCHIP_H = 21;

// TopoJSON → GeoJSON features (Polygon / MultiPolygon, quantized delta-encoded arcs), enough for world-atlas
function topoFeatures(topo, name) {
  const tf = topo.transform;
  const arcs = topo.arcs.map(a => {
    let x = 0, y = 0;
    return a.map(p => tf ? [(x += p[0]) * tf.scale[0] + tf.translate[0], (y += p[1]) * tf.scale[1] + tf.translate[1]] : [p[0], p[1]]);
  });
  const ring = ids => {
    const out = [];
    ids.forEach((i, k) => { const a = i < 0 ? arcs[~i].slice().reverse() : arcs[i]; for (let j = k ? 1 : 0; j < a.length; j++) out.push(a[j]); });
    return out;
  };
  const geom = g => g.type === 'Polygon' ? { type: 'Polygon', coordinates: g.arcs.map(ring) }
    : g.type === 'MultiPolygon' ? { type: 'MultiPolygon', coordinates: g.arcs.map(p => p.map(ring)) } : null;
  return topo.objects[name].geometries.map(g => ({ type: 'Feature', id: g.id == null ? null : String(g.id), properties: g.properties || {}, geometry: geom(g) }))
    .filter(f => f.geometry && f.id !== '010')                                       // no Antarctica
    .map(f => {
      if (f.id === '250' && f.geometry.type === 'MultiPolygon')                        // France without French Guiana (CAC 40 is Paris)
        f.geometry.coordinates = f.geometry.coordinates.filter(poly => poly[0][0][0] > -30);
      return f;
    });
}
async function loadAtlas(quiet) {
  if (GEO.state === 'loading' || GEO.state === 'ready') return;
  GEO.state = 'loading';
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);
  try {
    if (!window.d3 || typeof d3.geoNaturalEarth1 !== 'function') throw new Error('d3-geo가 없어요');
    const res = await fetch(ATLAS.url, { integrity: ATLAS.sri, mode: 'cors', credentials: 'omit', signal: ac.signal });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const topo = await res.json();
    if (!topo || !topo.objects || !topo.objects.countries) throw new Error('지도 자료 모양이 달라요');
    GEO.features = topoFeatures(topo, 'countries');
    GEO.state = 'ready';
  } catch (e) {
    GEO.state = 'failed';
    GEO.err = e;
  } finally { clearTimeout(timer); }
  if (S.shown && !quiet) render();          // quiet: the 다시 시도 key shows ✓ first, then draws
}
function geoGroups(d) {
  const used = new Set(), cs = [];
  for (const c of COUNTRIES) {
    const items = c.keys.map(k => d.byKey.get(k)).filter(Boolean);
    items.forEach(it => used.add(it.key));
    if (items.length) cs.push({ c, items, rep: items[0] });
  }
  // every index the Worker files under 미국 belongs to the US: cash indices first, then the futures, then VIX (a reference row)
  const us = cs.find(x => x.c.id === '840'), ez = cs.find(x => x.c.id === 'EZ');
  const add = (x, pick) => { if (x) for (const it of d.all) if (pick(it) && !used.has(it.key)) { x.items.push(it); used.add(it.key); } };
  add(us, it => it.gkey === 'us');
  add(us, isFut);
  add(us, it => isRef(it) && /VIX/i.test(it.key + it.name));
  add(ez, it => it.gkey === 'eu');                                  // a euro-area index the table does not know yet
  // side box 미국 선물 및 변동성 지수 (사용자 2026-11-13 22:32): the futures and VIX stay in a box beside the map; they are also
  // listed in the US sheet. 유로스톡스 50 sits with Europe (the 유로존 chip). Anything else unplaced is still on the list.
  return { cs, off: d.all.filter(it => isFut(it) || (isRef(it) && /VIX/i.test(it.key + it.name))) };
}
// one column of callouts: keep them in anchor order, at least CHIP_H + 3 apart, centred on their anchors, inside the map
function dodge(list, top, bottom) {
  const gap = GCHIP_H + 3;
  list.sort((a, b) => a.y0 - b.y0);
  let y = -Infinity;
  for (const it of list) { it.y = Math.max(it.y0, y + gap); y = it.y; }
  const shift = list.reduce((a, it) => a + it.y - it.y0, 0) / (list.length || 1);
  for (const it of list) it.y -= shift;
  if (list.length && list[0].y < top) { const s = top - list[0].y; for (const it of list) it.y += s; }
  y = -Infinity;
  for (const it of list) { it.y = Math.max(it.y, y + gap); y = it.y; }
  if (list.length && list[list.length - 1].y > bottom) { const s = list[list.length - 1].y - bottom; for (const it of list) it.y -= s; }
}
function geoProjection(W, narrow) {
  const P = d3.geoNaturalEarth1();
  let fit;
  if (narrow) {
    // phones: crop to where the indices are (the Americas to Japan), so the shapes are as big as the width allows
    P.rotate([-14, 0]);
    const pts = [];
    for (let lon = -126; lon <= 154; lon += 4) pts.push([lon, 66], [lon, -44]);
    fit = { type: 'MultiPoint', coordinates: pts };
  } else fit = { type: 'FeatureCollection', features: GEO.features };
  P.fitWidth(W, fit);
  const b = d3.geoPath(P).bounds(fit);
  const pad = narrow ? 4 : 8;
  P.translate([P.translate()[0], P.translate()[1] - b[0][1] + pad]);
  const H = Math.ceil(b[1][1] - b[0][1] + 2 * pad);
  P.clipExtent([[0, 0], [W, H]]);
  return { P, H };
}
const svgEl = (tag, attrs) => svg(tag, attrs);
const fx1 = v => v.toFixed(1);

/* day / night (AGENTS §3-5, docs/motion-brief.md (e)) — information, so drawn at every effect level, statically.
   Subsolar point from the low-precision almanac (good to ~0.01°, plenty at 110m); the night side is the 90° circle around
   the antisolar point, drawn as four nested caps (90 · 84 · 78 · 72° = sunset, civil, nautical, astronomical twilight) of
   12 % each, so the darkest part is ≈ 40 % and the countries' colours still read. Redrawn every minute (0.25°/min). */
const NIGHT_R = [90, 84, 78, 72];
const wrapLon = x => ((x % 360) + 540) % 360 - 180;
function subsolar(t) {
  const rad = Math.PI / 180, d = t / 864e5 - 10957.5;
  const g = (357.529 + 0.98560028 * d) * rad;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad;
  const e = (23.439 - 3.6e-7 * d) * rad;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)) / rad;
  const dec = Math.asin(Math.sin(e) * Math.sin(L)) / rad;
  const eqt = ((((q - ra) / 15) % 24) + 36) % 24 - 12;          // equation of time in hours, [−12, 12)
  const utc = (((t % 864e5) + 864e5) % 864e5) / 36e5;
  return [wrapLon(-15 * (utc - 12 + eqt)), dec];
}
function nightCentre(t) { const [lon, lat] = subsolar(t); return [wrapLon(lon + 180), -lat]; }
function drawNight() {
  const g = els && els.g;
  if (!g || !g.night.isConnected) return;
  const t = Date.now(), c = nightCentre(t), path = d3.geoPath(g.P);
  const cap = r => d3.geoCircle().center(c).radius(r).precision(2)();
  const kids = NIGHT_R.map(r => svgEl('path', { class: 'kw-gn', d: path(cap(r)) || '' }));
  // the terminator as a line (a polygon outline would also trace the map's edge where the cap is cut)
  kids.push(svgEl('path', { class: 'kw-gterm', d: path({ type: 'LineString', coordinates: cap(90).coordinates[0] }) || '' }));
  g.night.replaceChildren(...kids);
  g.night.dataset.lon = c[0].toFixed(2); g.night.dataset.lat = c[1].toFixed(2);
  g.nightMin = Math.floor(t / 60000);
}
let nightT = 0;
function schedNight() {
  clearTimeout(nightT); nightT = 0;
  if (!S.shown || S.mode !== 'geo' || document.hidden) return;
  nightT = setTimeout(() => { nightT = 0; drawNight(); schedNight(); }, 60000 - Date.now() % 60000 + 40);
}

function buildGeo(d, W, narrow, G, sig) {
  const ae = document.activeElement;
  const fk = ae && ae.classList && ae.classList.contains('kw-gb') && els.geo.contains(ae) ? ae.dataset.f : null;
  const { P, H } = geoProjection(W, narrow);
  const mid = !narrow && W < 880;
  const path = d3.geoPath(P);
  const byId = new Map(G.cs.map(x => [x.c.id, x]));
  const s = svgEl('svg', { class: 'kw-gsvg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, 'aria-hidden': 'true' });
  s.append(svgEl('path', { class: 'kw-gsea', d: path({ type: 'Sphere' }) }), svgEl('path', { class: 'kw-ggrat', d: path(d3.geoGraticule10()) }));
  // layers, bottom to top: fills → night → borders → open markets (a flat --live outline) → selection / hover → leader lines → markers
  const land = svgEl('g', { class: 'kw-gland' });
  const paths = new Map(), dOf = new Map(), border = [];
  for (const f of GEO.features) {
    const dd = path(f);
    if (!dd) continue;
    border.push(dd);
    const x = byId.get(f.id);
    const p = svgEl('path', { class: 'kw-cp' + (x ? ' has' : ''), d: dd });
    if (x) { p.dataset.c = f.id; p.append(svgEl('title', {})); paths.set(f.id, p); dOf.set(f.id, dd); }
    land.append(p);
  }
  const layer = c => svgEl('g', { class: c });
  const night = layer('kw-gnight'), openG = layer('kw-gopen'), selG = layer('kw-gsel'), hov = layer('kw-ghov'), lines = layer('kw-glines'), marks = layer('kw-gmarks');
  s.append(land, night, svgEl('path', { class: 'kw-gbord', d: border.join('') }), openG, selG, hov, lines, marks);
  const hovP = svgEl('path', {});
  hov.append(hovP);
  // the hover outline follows a mouse only (design.md §8: no hover look left behind by a finger)
  land.addEventListener('pointerover', e => { if (e.pointerType && e.pointerType !== 'mouse') return; const p = e.target.closest('.kw-cp.has'); hovP.setAttribute('d', p ? dOf.get(p.dataset.c) || '' : ''); });
  land.addEventListener('pointerleave', () => hovP.setAttribute('d', ''));
  const labs = h('div', { class: 'kw-glabs' });
  const btns = new Map(), dots = new Map(), inLabs = [], colList = [];
  const cols = {};
  // a market marker: a 5 px dot (--live = open, hollow grey = closed) — flat, nothing pulses (design.md §10 ③)
  const addDot = (x, ax, ay, big) => {
    const dot = svgEl('circle', { class: big ? 'kw-gmk' : 'kw-gdot', cx: fx1(ax), cy: fx1(ay), r: big ? (narrow ? 3.5 : 4.5) : narrow ? 2.2 : 2.5 });
    dot.dataset.c = x.c.id;
    if (big) dot.append(svgEl('title', {}));
    marks.append(dot);
    dots.set(x.c.id, { dot });
  };
  for (const x of G.cs) {
    const [ax, ay] = P(x.c.at) || [NaN, NaN];
    if (!isFinite(ax) || ax < 0 || ax > W) continue;
    if (x.c.marker) addDot(x, ax, ay, true);                    // 홍콩: too small for the 110m map, a dot in its colour
    if (narrow) {
      // phones: the big markets carry a % on the map, the others a marker; the buttons under the map are the way in
      if (!x.c.big) { if (!x.c.marker && !x.c.area) addDot(x, ax, ay, false); continue; }
      const b = h('span', { class: 'kw-gl in sm', 'data-c': x.c.id, 'aria-hidden': 'true' }, h('i', { class: 'kw-sd' }), h('span', { class: 'p' }));
      labs.append(b); btns.set(x.c.id, b); inLabs.push({ el: b, x: ax, y: ay });
      continue;
    }
    if (x.c.big && !(mid && x.c.id === '360')) {
      const b = h('button', { type: 'button', class: 'kw-gb kw-gl in', 'data-c': x.c.id, 'data-f': 'c' + x.c.id, tabindex: '-1' },
        h('span', { class: 'n' }, h('i', { class: 'kw-sd' }), h('span', { class: 't' })), h('span', { class: 'p' }));
      labs.append(b); btns.set(x.c.id, b); inLabs.push({ el: b, x: ax, y: ay });
      continue;
    }
    if (!x.c.marker) addDot(x, ax, ay, false);                  // the leader line starts at the market's marker
    // narrower maps: Korea (< 980 px, its chip would meet the European ones) and Indonesia (< 880 px) join the Pacific column
    const ck = (x.c.id === '410' && W < 980) || (mid && x.c.id === '360') ? 'pac' : x.c.col;
    const C = GCOLS[ck];
    (cols[ck] = cols[ck] || []).push({ x, ax, ay, y0: C.fixY != null ? P([C.lon, C.fixY])[1] : ay });
  }
  for (const k in cols) {
    const C = GCOLS[k];
    dodge(cols[k], GCHIP_H / 2 + 4, H - GCHIP_H / 2 - 4);
    const end = C.align === 'end';
    for (const it of cols[k]) {
      it.el = h('button', { type: 'button', class: 'kw-gb kw-gl chip' + (end ? ' end' : ''), 'data-c': it.x.c.id, 'data-f': 'c' + it.x.c.id, tabindex: '-1' },
        h('i', { class: 'kw-sd' }), h('span', { class: 't' }), h('span', { class: 'p' }));
      labs.append(it.el); btns.set(it.x.c.id, it.el);
    }
    colList.push({ x: P([C.lon, C.lat])[0], end, items: cols[k] });
  }
  // US futures and VIX: a small box beside the map (below it on narrow maps)
  const offBelow = narrow || mid;
  const off = h('div', { class: 'kw-goff' + (offBelow ? ' below' : '') }, h('div', { class: 'kw-goh', text: '미국 선물 및 변동성 지수' }),
    G.off.map(it => h('button', { type: 'button', class: 'kw-gb kw-go', 'data-k': it.key, 'data-f': 'k' + it.key, tabindex: '-1' },
      h('i', { class: 'kw-sd' }), h('span', { class: 't' }, it.name), h('span', { class: 'kw-pchip sm' }, h('span', { class: 'kw-pt' })))));
  const mapBox = h('div', { class: 'kw-gmap', style: `height:${H}px;--gs:${Math.max(1, Math.min(1.22, W / 1150)).toFixed(3)}` }, s, labs, offBelow || !G.off.length ? null : off);
  // phones: every country as a tap target under the map
  const grid = narrow ? h('div', { class: 'kw-ggrid', role: 'group', 'aria-label': '나라별 대표 지수' }, G.cs.map(x =>
    h('button', { type: 'button', class: 'kw-gb kw-gc', 'data-c': x.c.id, 'data-f': 'c' + x.c.id, tabindex: '-1' },
      h('i', { class: 'sw' }), h('span', { class: 't' }, h('b', { text: x.c.name }), h('small')), h('span', { class: 'p' })))) : null;
  put(els.geo, mapBox, grid, offBelow && G.off.length ? off : null);
  els.geo.classList.toggle('narrow', narrow);
  const first = !els.g;
  els.g = { sig, W, H, P, narrow, paths, dOf, btns, dots, night, openG, selG, lines, inLabs, cols: colList, cs: G.cs, off: G.off, openSig: null, was: new Map(), just: new Set(), nightMin: -1 };
  // 화려하게: the first time the map opens, countries → night → markers fade in, 40 → 30 ms apart (design.md §6-2, a rare first appearance)
  if (first && motion() === 'fancy') {
    mapBox.classList.add('kw-gin');
    setTimeout(() => mapBox.classList.remove('kw-gin'), 1200);
  }
  if (fk) { const b = els.geo.querySelector(`.kw-gb[data-f="${CSS.escape(fk)}"]`); if (b) b.focus({ preventScroll: true }); }
}
function renderGeo(d) {
  const W = els.geo.clientWidth;
  if (!W || GEO.state !== 'ready') return;
  const narrow = W < 560;
  const G = geoGroups(d);
  const sig = [W, narrow, G.cs.map(x => x.c.id + ':' + x.items.map(i => i.key).join(',')).join(';'), G.off.map(i => i.key).join(',')].join('|');
  if (!els.g || els.g.sig !== sig || !els.geo.contains(els.g.night)) buildGeo(d, W, narrow, G, sig);
  const g = els.g;
  g.cs = G.cs; g.off = G.off;
  const selKey = S.detail && S.detail.key;
  const openIds = [];
  for (const x of G.cs) {
    const it = x.rep, col = colorOf(it), open = cashOf(x.items).some(i => i.status === 'OPEN');   // futures trade all but round the clock: they do not make 미국 "open"
    if (open) openIds.push(x.c.id);
    const sel = !!selKey && x.items.some(i => i.key === selKey);
    const tip = `${x.c.name} · ${it.name} ${pct(it.ratio)}${x.items.length > 1 ? ` 외 ${x.items.length - 1}개` : ''} · ${open ? '장중' : '마감'}`;
    const p = g.paths.get(x.c.id);
    if (p) { p.style.fill = col; p.classList.toggle('open', open); p.classList.toggle('sel', sel); p.firstChild.textContent = tip; }
    const m = g.dots.get(x.c.id);
    if (m) {
      if (m.dot.classList.contains('kw-gmk')) { m.dot.style.fill = col; m.dot.firstChild.textContent = tip; }
      m.dot.classList.toggle('open', open); m.dot.classList.toggle('sel', sel);
    }
    if (open && g.was.get(x.c.id) === false) g.just.add(x.c.id);   // it opened since the last answer (화려하게: its outline fades in once)
    g.was.set(x.c.id, open);
    const aria = `${x.c.name} ${it.name} ${valText(it)}, ${pct(it.ratio)}, ${open ? '장중' : '마감'}${x.items.length > 1 ? `, 항목 ${x.items.length}개` : ''}`;
    const b = g.btns.get(x.c.id);
    if (b) {
      if (b.classList.contains('in')) labInk(b, col);
      const t = b.querySelector('.t'), pp = b.querySelector('.p'), dot = b.querySelector('.kw-sd');
      if (t) t.textContent = x.c.name;
      if (b.classList.contains('chip')) { pp.className = 'p ' + (it.ratio == null ? 'flat' : cls(it.ratio)); b.style.setProperty('--c', col); }
      swapTo(pp, pct(it.ratio), it.ratio);                 // a refresh that moved the % swaps it in place (§6-4)
      if (dot) dot.className = 'kw-sd ' + (open ? 'open' : 'close');
      b.classList.toggle('sel', sel);
      if (b.tagName === 'BUTTON') { b.setAttribute('aria-label', aria); b.title = tip; }
    }
    const c = els.geo.querySelector(`.kw-gc[data-c="${x.c.id}"]`);
    if (c) {
      c.querySelector('.sw').style.background = col;
      c.querySelector('small').textContent = `${shortIdx(x.c, it)}${open ? ' · 장중' : ''}`;
      const pp = c.querySelector('.p'); pp.className = 'p ' + (it.ratio == null ? 'flat' : cls(it.ratio)); swapTo(pp, pct(it.ratio), it.ratio);
      c.classList.toggle('sel', sel);
      c.setAttribute('aria-label', aria);
    }
  }
  // open markets: a flat 1.5px --live outline (no blur, no pulse — design.md §10 ③), redrawn only when the set changes; a market
  // that just opened fades in once in 화려하게 (a real change, P4), the others stay as they are
  const osig = openIds.join(',');
  if (g.openSig !== osig) {
    g.openSig = osig;
    g.openG.replaceChildren(...openIds.filter(id => g.dOf.has(id)).map(id => svgEl('path', { d: g.dOf.get(id), 'data-c': id, class: g.just.has(id) ? 'in' : '' })));
  }
  g.just.clear();
  syncGeoSel();
  for (const b of els.geo.querySelectorAll('.kw-go')) {
    const it = d.byKey.get(b.dataset.k);
    if (!it) continue;
    const ref = isRef(it), col = ref ? null : colorOf(it), chip = b.querySelector('.kw-pchip');
    swapTo(chip.firstChild, pct(it.ratio), it.ratio);
    chip.className = 'kw-pchip sm' + (ref ? ' ref' : '');
    chip.style.backgroundColor = col || '';
    chip.style.color = col ? inkOn(col) : '';
    b.querySelector('.kw-sd').className = 'kw-sd ' + (it.status === 'OPEN' ? 'open' : 'close');
    b.classList.toggle('sel', selKey === it.key);
    b.setAttribute('aria-label', ariaOf(it));
  }
  placeLabels();
  if (g.nightMin !== Math.floor(Date.now() / 60000)) drawNight();
  schedNight();
  // roving focus over the map's buttons
  const fs = [...els.geo.querySelectorAll('.kw-gb')];
  if (!S.geoFocus || !fs.some(b => b.dataset.f === S.geoFocus)) S.geoFocus = fs.length ? fs[0].dataset.f : null;
  for (const b of fs) b.tabIndex = b.dataset.f === S.geoFocus ? 0 : -1;
  els.geo.setAttribute('aria-label', '해외 지수 세계지도. 나라마다 대표 지수의 등락률로 칠했고, 지금 밤인 쪽은 어둡게 했어요. 화살표로 옮기고 Enter로 자세히 봐요');
  els.geo.setAttribute('role', 'group');
}
// the selected country's outline sits above the night and the borders
function syncGeoSel() {
  const g = els && els.g;
  if (!g) return;
  const key = S.detail && S.detail.key;
  const hit = key ? g.cs.find(x => x.items.some(i => i.key === key)) : null;
  const dd = hit && g.dOf.get(hit.c.id);
  g.selG.replaceChildren(...(dd ? [svgEl('path', { d: dd })] : []));
}
// labels stay inside the map; a callout column moves in as a block so its widest chip fits; labels that would sit on
// each other (or on a chip, or on the side box) are nudged apart along the shorter overlap; then the leader lines
function placeLabels() {
  const g = els.g, W = g.W, H = g.H, GAP = 3;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // reads first (sizes), then the arithmetic, then the writes
  const ins = g.inLabs.map(L => ({ L, w: L.el.offsetWidth, h: L.el.offsetHeight }));
  const cols = g.cols.map(col => ({ col, ws: col.items.map(it => [it.el.offsetWidth, it.el.offsetHeight]) }));
  const offEl = els.geo.querySelector('.kw-gmap > .kw-goff');
  const fixed = [];
  if (offEl) fixed.push({ l: offEl.offsetLeft, t: offEl.offsetTop, r: offEl.offsetLeft + offEl.offsetWidth, b: offEl.offsetTop + offEl.offsetHeight });
  const chipPos = [];
  for (const { col, ws } of cols) {
    const maxW = Math.max(...ws.map(x => x[0]));
    const x = col.end ? Math.max(col.x, maxW + 4) : Math.min(col.x, W - maxW - 4);
    col.items.forEach((it, i) => {
      const [w, hh] = ws[i];
      chipPos.push({ it, x, end: col.end });
      fixed.push({ l: col.end ? x - w : x, r: col.end ? x : x + w, t: it.y - hh / 2, b: it.y + hh / 2 });
    });
  }
  for (const o of ins) { o.x = clamp(o.L.x, o.w / 2 + 3, W - o.w / 2 - 3); o.y = clamp(o.L.y, o.h / 2 + 2, H - o.h / 2 - 2); }
  const box = o => ({ l: o.x - o.w / 2, r: o.x + o.w / 2, t: o.y - o.h / 2, b: o.y + o.h / 2 });
  const over = (a, b) => [Math.min(a.r, b.r) - Math.max(a.l, b.l) + GAP, Math.min(a.b, b.b) - Math.max(a.t, b.t) + GAP];
  for (let pass = 0; pass < 24; pass++) {
    let moved = false;
    for (let i = 0; i < ins.length; i++) {
      const a = ins[i];
      const others = ins.filter((x, j) => j !== i).map(x => ({ o: x, r: box(x) })).concat(fixed.map(r => ({ o: null, r })));
      for (const { o, r } of others) {
        const A = box(a), [ox, oy] = over(A, r);
        if (ox <= GAP || oy <= GAP) continue;
        const share = o ? 0.5 : 1;                         // two labels both give way; a chip or the side box does not move
        const ac = [(A.l + A.r) / 2, (A.t + A.b) / 2], rc = [(r.l + r.r) / 2, (r.t + r.b) / 2];
        if (oy <= ox) { const s = (ac[1] <= rc[1] ? -1 : 1) * oy * share; a.y += s; if (o) o.y -= s; }
        else { const s = (ac[0] <= rc[0] ? -1 : 1) * ox * share; a.x += s; if (o) o.x -= s; }
        for (const z of o ? [a, o] : [a]) { z.x = clamp(z.x, z.w / 2 + 3, W - z.w / 2 - 3); z.y = clamp(z.y, z.h / 2 + 2, H - z.h / 2 - 2); }
        moved = true;
      }
    }
    if (!moved) break;
  }
  for (const o of ins) { o.L.el.style.left = o.x.toFixed(1) + 'px'; o.L.el.style.top = o.y.toFixed(1) + 'px'; }
  const kids = [];
  for (const { it, x, end } of chipPos) {
    it.el.style.left = x.toFixed(1) + 'px';
    it.el.style.top = it.y.toFixed(1) + 'px';
    // marker → elbow → the chip's near edge
    const ex = x + (end ? 1 : -1), elbow = x + (end ? 9 : -9);
    kids.push(svgEl('path', { class: 'kw-gld', d: `M${fx1(it.ax)} ${fx1(it.ay)}L${fx1(elbow)} ${fx1(it.y)}L${fx1(ex)} ${fx1(it.y)}` }));
  }
  g.lines.replaceChildren(...kids);
}
const cashOf = items => { const c = items.filter(i => !isFut(i) && !isRef(i)); return c.length ? c : items; };
const shortIdx = (c, it) => it.name.startsWith(c.name + ' ') ? it.name.slice(c.name.length + 1) : it.name;
function setGeoFocus(f) {
  S.geoFocus = f;
  for (const b of els.geo.querySelectorAll('.kw-gb')) b.tabIndex = b.dataset.f === f ? 0 : -1;
}
function openCountry(id, opener) {
  const g = els.g;
  const x = g && g.cs.find(c => c.c.id === id);
  if (!x) return;
  openDetail(x.rep.key, opener || g.btns.get(id) || els.geo.querySelector(`.kw-gc[data-c="${id}"]`), x.items.map(i => i.key), x.c.name);
}
function onGeoClick(e) {
  const b = e.target.closest('.kw-gb');
  if (b) { if (b.dataset.c) openCountry(b.dataset.c, b); else if (b.dataset.k) openDetail(b.dataset.k, b, offPeers(b.dataset.k)); return; }
  const p = e.target.closest('.kw-cp.has, .kw-gmk, .kw-gdot');
  if (p) openCountry(p.dataset.c, null);
}
function offPeers(key) {
  const d = S.data[S.kind], it = d && d.byKey.get(key);
  if (!it || !els.g) return null;
  const same = els.g.off.filter(o => o.gkey === it.gkey).map(o => o.key);
  return same.length > 1 ? same : null;
}
// arrows: the nearest button in that direction (by the buttons' boxes); Home / End
function onGeoKey(e) {
  const cur = e.target.closest('.kw-gb');
  if (!cur) return;
  const fs = [...els.geo.querySelectorAll('.kw-gb')].filter(b => b.getClientRects().length);
  let next = null;
  if (e.key === 'Home') next = fs[0];
  else if (e.key === 'End') next = fs[fs.length - 1];
  else if (/^Arrow/.test(e.key)) {
    const a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
    let best = Infinity;
    for (const b of fs) {
      if (b === cur) continue;
      const r = b.getBoundingClientRect(), bx = r.left + r.width / 2, by = r.top + r.height / 2;
      const dx = bx - ax, dy = by - ay;
      const main = e.key === 'ArrowRight' ? dx : e.key === 'ArrowLeft' ? -dx : e.key === 'ArrowDown' ? dy : -dy;
      const cross = e.key === 'ArrowRight' || e.key === 'ArrowLeft' ? Math.abs(dy) : Math.abs(dx);
      if (main <= 2) continue;
      const sc = main + cross * 2.2;
      if (sc < best) { best = sc; next = b; }
    }
  } else return;
  e.preventDefault();
  if (next) { setGeoFocus(next.dataset.f); next.focus(); }
}

/* side: biggest movers, open markets, source */
function rowBtn(it) {
  const u = unitOf(it);
  return h('button', { type: 'button', class: 'kw-row', 'data-k': it.key, 'aria-label': ariaOf(it) },
    h('i', { class: 'kw-sw', style: `background:${colorOf(it)}` }),
    h('span', { class: 'nm' }, it.name, h('small', { text: it.group })),
    h('span', { class: 'px', text: valText(it) + (u ? ' ' + u[1] : '') }),
    h('span', { class: 'v ' + cls(it.ratio), text: pct(it.ratio) }));
}
function renderRank(d) {
  const pool = d.all.filter(it => !isRef(it) && !isMacro(it) && it.ratio != null);   // 지표: the commodities only (§3-28)
  const ups = pool.filter(it => it.ratio > 0).sort((a, b) => b.ratio - a.ratio).slice(0, 5);
  const dns = pool.filter(it => it.ratio < 0).sort((a, b) => a.ratio - b.ratio).slice(0, 5);
  const sub = $('.kw-rank-sub', root);
  if (sub) sub.textContent = d.all.some(isMacro) ? `원자재 ${pool.length}개 중` : `${pool.length}개 중`;
  put(els.rank,
    h('div', { class: 'kw-rh', text: '많이 오른' }),
    ups.length ? ups.map(rowBtn) : h('p', { class: 'kw-none', text: '오른 곳이 없어요' }),
    h('div', { class: 'kw-rh second', text: '많이 내린' }),
    dns.length ? dns.map(rowBtn) : h('p', { class: 'kw-none', text: '내린 곳이 없어요' }));
}
function renderOpen(d) {
  const now = new Date();
  const byCity = new Map();
  let closed = 0;
  for (const g of d.groups) for (const it of g.items) {
    if (isFund(it)) continue;                            // 증시 자금 is not a market that opens
    if (it.status !== 'OPEN') { closed++; continue; }
    const c = cityOf(it, g);
    const e = byCity.get(c) || byCity.set(c, { city: c, its: [], it }).get(c);
    e.its.push(it);
  }
  const rows = [...byCity.values()].map(e => {
    const w = wall(now, e.it);
    const names = e.its.map(it => SHORT[it.key] || it.name);
    const shown = names.slice(0, 4).join(' · ') + (names.length > 4 ? ` 외 ${names.length - 4}개` : '');
    return h('li', { class: 'kw-om' },
      h('div', { class: 'kw-om1' }, h('b', { text: e.city }), h('span', { class: 'kw-clock', text: `${WD[w.wd] || ''} ${w.hh}:${w.mm}` })),
      h('div', { class: 'kw-om2', text: shown, title: e.its.map(it => it.name).join(', ') }));
  });
  const kst = fmtKst.format(now);
  els.open.replaceChildren(
    rows.length ? h('ul', { class: 'kw-oml' }, rows)
      : h('p', { class: 'kw-none' }, '지금은 열린 시장이 없어요. 주말·휴장일이거나 장 시간이 아니라서 마지막 값을 보여 줘요.'),
    h('p', { class: 'kw-omf' }, `한국 ${kst} · `, closed ? `마감 ${closed}개는 마지막 값이에요` : '모두 장중이에요'));
}
function renderSource(d) {
  const fxr = it => isFx(it) || isRate(it);
  const kids = [h('span', {}, S.kind === 'commodity' && d && d.all.some(fxr) ? '출처: 네이버 증권 · 거래소·기관마다 시세가 늦게 올 수 있어요.'
    : '출처: 네이버 증권 · 해외 지수와 원자재는 거래소별로 최대 20분 지연될 수 있어요.')];
  if (d && d.all.length) {
    const cnt = new Map();
    for (const it of d.all) { if (isFund(it)) continue; const k = it.eod ? -1 : it.delayed || 0; cnt.set(k, (cnt.get(k) || 0) + 1); }
    const parts = [...cnt].sort((a, b) => (a[0] < 0) - (b[0] < 0) || a[0] - b[0]).map(([k, n]) => `${k < 0 ? '하루 한 번 종가' : k ? dlText(k) : '실시간'} ${n}개`);
    kids.push(h('span', {}, ` 지금 목록: ${parts.join(' · ')}.`));
    const at = d.asOf ? new Date(d.asOf) : null;
    if (at && !isNaN(at)) kids.push(h('span', {}, ` ${fmtKstS.format(at)}(한국 시각)에 받은 값이고, 30초마다 새로 받아요.`));
  }
  if (S.kind === 'commodity') kids.push(h('span', {}, ' 원자재는 근월물 선물 가격이에요.'));
  if (S.kind === 'commodity' && d && d.all.some(fxr)) {
    const fxs = d.all.filter(isFx), eod = fxs.find(it => it.eod), calc = fxs.find(it => it.calc);
    kids.push(h('span', {}, ' 원/달러·원/엔·원/유로·원/위안은 하나은행 고시 환율, 금리는 레피니티브 기준이에요.'
      + (eod ? ' 달러/엔은 하루 한 번 바뀌는 종가예요.' : '') + (calc ? ' 달러/엔은 원/달러와 원/엔으로 계산한 값이에요.' : '')));
  }
  const fg = S.kind === 'commodity' && d && d.groups.find(g => g.key === 'funds');
  if (fg) kids.push(h('span', { class: 'kw-src-fd' }, ` 증시 자금은 금융투자협회 통계(금융위원회 공공데이터포털)로 하루 한 번, 전 영업일 값으로 바뀌어요${fg.basDt ? ` — 지금 ${mdText(fg.basDt, true)} 자료` : ''}.`));
  // 수출입은행 고시 (AGENTS §3-27 끝): "한국수출입은행 · 하루 한 번" with the posting day on screen
  const kx = S.kind === 'commodity' && d && d.groups.some(g => KX_SEC[g.key]) ? (KXIM.fx || KXIM.rate) : null;
  if (kx) kids.push(h('span', { class: 'kw-src-kx' }, ` 수출입은행 고시 환율 · 금리: 한국수출입은행 · 하루 한 번, 지금 ${mdText(kx.date, true)} 고시예요.`));
  els.src.replaceChildren(...kids);
}

/* snapshot (artifact) mode: no network → a pointer to the live page */
function renderSnapshot() {
  const K = KINDS[S.kind];
  const url = (KH.LIVE_URL || 'https://panse.pages.dev/') + '#' + K.hash;
  root.replaceChildren(h('div', { class: 'kw-snap' },
    h('div', { class: 'kw-snap-in' },
      h('b', { text: K.snapTitle }),
      h('p', { text: K.snapBody }),
      h('a', { class: 'kw-snap-a', href: url, target: '_blank', rel: 'noopener' }, '실시간 버전 열기'))));
}

/* ───────── detail sheet ───────── */
let sheet = null, scrim = null;
function ensureSheet() {
  if (sheet) return;
  scrim = h('div', { class: 'kw-scrim', 'aria-hidden': 'true' });
  sheet = h('div', { class: 'kw-sheet pal-w', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'kw-dt', tabindex: '-1', hidden: true });
  document.body.append(scrim, sheet);
  scrim.addEventListener('click', () => closeDetail(true));
  // phones: drag the grip or the head down to dismiss (the template's KH.ui.sheetDrag, design.md §8)
  if (KH.ui && typeof KH.ui.sheetDrag === 'function') KH.ui.sheetDrag(sheet, { zone: '.kw-grab, .kw-dh', on: () => !!S.detail && narrowMQ.matches, close: () => closeDetail(true), scrim: () => scrim });
  sheet.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeDetail(true); return; }
    if (e.key === 'Tab') {
      const f = [...sheet.querySelectorAll('button,a[href]')].filter(b => b.offsetParent && !b.disabled);
      if (!f.length) return;
      if (e.shiftKey && (document.activeElement === f[0] || document.activeElement === sheet)) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  document.addEventListener('pointerdown', e => {
    if (!S.detail || sheet.contains(e.target) || e.target.closest('.kw-tile,.kw-row,.kw-lr,.kw-gb,.kw-cp.has,.kw-gmk,.kw-gdot')) return;
    if (!narrowMQ.matches) closeDetail(false);
  }, true);
  addEventListener('resize', () => { if (S.detail && S.detail.chart) drawChart(); });
}
// peers: the other indices of the same country (world map) — a switcher at the top of the sheet; place: its title
function openDetail(key, opener, peers, place, kindArg, today, scope) {
  const kind = kindArg || S.kind;
  const d = S.data[kind];
  if (!d || !d.byKey.has(key)) return;
  ensureSheet();
  const same = S.detail && S.detail.key === key;
  peers = peers && peers.length > 1 && peers.includes(key) ? peers : null;
  S.detail = { key, kind, opener: opener || null, tf: same ? S.detail.tf : '3m', chart: null, peers, place: peers ? place || null : null, today: today || null,
    scope: scope === 'kr' && (key === 'KOSPI' || key === 'KOSDAQ') ? 'kr' : 'world' };
  sheet.classList.toggle('pal-w', S.detail.scope === 'world');
  markSel(key);
  fillDetail(true);
  sheet.hidden = false;
  sheet.classList.toggle('kw-noanim', calm());
  if (narrowMQ.matches) scrim.classList.add('open');
  sheet.scrollTop = 0;
  sheet.focus({ preventScroll: true });
  detailEvent(true);
  loadChart();
}
// the bottom bar and the ticker hide / hold while a sheet is open: they can listen instead of polling KHWorld.detailOpen()
function detailEvent(open) { document.dispatchEvent(new CustomEvent('kh:worlddetail', { detail: { open } })); }
function markSel(key) {
  if (!els || !els.tiles) return;          // opened from the ticker before the 해외 tab was ever shown
  for (const [k, el] of els.tiles) el.classList.toggle('sel', k === key);
  for (const [k, el] of els.rows) el.classList.toggle('sel', k === key);
  if (els.g) {
    const hit = key ? els.g.cs.find(x => x.items.some(i => i.key === key)) : null;
    for (const el of els.geo.querySelectorAll('.kw-cp.has, .kw-gmk, .kw-gdot, .kw-gl, .kw-gc')) el.classList.toggle('sel', !!hit && el.dataset.c === hit.c.id);
    for (const el of els.geo.querySelectorAll('.kw-go')) el.classList.toggle('sel', el.dataset.k === key);
    syncGeoSel();
  }
}
function closeDetail(restore) {
  if (!S.detail || !sheet) return;
  const { key, opener } = S.detail;
  S.detail = null;
  sheet.hidden = true;
  scrim.classList.remove('open');
  if (els && els.tiles) markSel(null);
  detailEvent(false);
  if (!restore) return;
  // back to the opener; if it is gone or hidden (the view changed meanwhile), to the same item in what is shown now
  const visible = el => el && el.isConnected && el.getClientRects().length > 0;
  if (!S.shown) {
    // opened from another tab (ticker, the bottom bar's index cell): the opener is all there is to go back to. A bar that hid
    // itself while the sheet was open needs a frame or two to show again, so wait for it
    const go = n => { if (visible(opener)) { try { opener.focus({ preventScroll: true }); } catch (e) { /* ignore */ } } else if (n > 0 && opener && opener.isConnected) requestAnimationFrame(() => go(n - 1)); };
    go(4);
    return;
  }
  let target = visible(opener) ? opener : null;
  if (!target && opener && opener.classList.contains('kw-row')) target = els.rank.querySelector(`.kw-row[data-k="${CSS.escape(key)}"]`);
  if (!visible(target) && S.mode === 'geo' && els.g) {
    const hit = els.g.cs.find(x => x.items.some(i => i.key === key));
    const cand = hit ? els.geo.querySelector(`.kw-gb[data-c="${hit.c.id}"]`) : els.geo.querySelector(`.kw-gb[data-k="${CSS.escape(key)}"]`);
    if (visible(cand)) target = cand;
  }
  if (!visible(target)) target = S.mode === 'list' && visible(els.rows.get(key)) ? els.rows.get(key) : visible(els.tiles.get(key)) ? els.tiles.get(key) : null;
  if (target) {
    if (target.classList.contains('kw-tile')) setRoving(key);
    if (target.classList.contains('kw-lr')) setListFocus(key);
    if (target.classList.contains('kw-gb')) setGeoFocus(target.dataset.f);
    target.focus({ preventScroll: false });
  }
}
function switchPeer(k) {
  const D = S.detail;
  if (!D || !D.peers || D.key === k) return;
  openDetail(k, D.opener, D.peers, D.place, null, null, D.scope);
  const b = sheet.querySelector(`.kw-peers button[data-k="${CSS.escape(k)}"]`);
  if (b) b.focus({ preventScroll: true });
}
function fillDetail(full) {
  const D = S.detail, d = S.data[D.kind];
  const it = d && d.byKey.get(D.key);
  if (!it) return;
  // 후속 ③: a 지표 row opened while the 지표 tab is not drawing (the ticker on 해외 · 국내 tabs) colours on the 지표 data's zones —
  // measured here with the same keys and rule (the 지표 tab's own render measures them otherwise)
  if (it.cm && !(S.shown && S.kind === 'commodity')) syncZones();
  const u = unitOf(it), L = parseLocal(it.tradedAt);
  const g = d.groups.find(x => x.items.includes(it));
  const city = cityOf(it, g);
  const lw = L ? wall(L.date, it) : null;
  // a daily close (달러/엔, §3-28) has a date and no meaningful time
  const localTxt = !L ? '—' : it.eod ? `${L.mo}월 ${L.d}일 (${WD[lw.wd]}) 종가` : `${L.mo}월 ${L.d}일 (${WD[lw.wd]}) ${L.hh}:${L.mm}`;
  const kstTxt = L ? fmtKstDay.format(L.date) : '—';
  const prev = it.change != null ? it.value - it.change : null;
  const rate = isRate(it), fx = isFx(it);
  const unitTxt = rate ? '연 %' : fx ? FX_UNIT[it.key] || (u ? u[0] : '—') : u ? u[0] : (it.gkey === 'kr' || D.kind === 'index' ? '포인트' : '—');
  const chgLine = rate ? `${chgText(it)} (${it.change == null ? '—' : sgn(it.change) + fixed(it.change, 3) + '%p'})` : `${chgText(it)} (${pct(it.ratio)})`;
  const note = isRef(it) ? 'VIX는 S&P 500 옵션 가격으로 계산한 변동성 기대치예요. 오르면 시장 불안이 커졌다는 뜻이라 지도에서 색칠하지 않았어요.'
    : it.gkey === 'kr' ? '비교용으로 함께 보여 줘요. 종목 지도는 코스피·코스닥 탭에서 볼 수 있어요.'
    : rate ? RATE_NOTE
    : fx ? (FX_NOTE[it.key] || KRW_NOTE) + (it.eod ? ' 레피니티브 종가라 하루에 한 번 바뀌어요.' : '')
      + (it.calc ? ' 원/달러를 1엔당 원화로 나눈 계산값이고, 차트는 레피니티브 일봉 종가예요.' : '')
    : D.kind === 'commodity' ? '근월물 선물 가격이에요. 거래소 시각 기준으로 하루가 바뀌어요.' : null;
  const head = isFund(it) ? fundHead(it) : h('div', { class: 'kw-dh', 'data-k': it.key },
    h('div', { class: 'kw-path', text: [it.group, city && city !== it.group ? city : null].filter(Boolean).join(' · ') }),
    h('div', { class: 'kw-nmrow' }, h('i', { class: 'kw-sw', style: `background:${colorOf(it, dScope())}` }), h('b', { id: 'kw-dt', text: it.name }),
      h('span', { class: 'kw-st ' + (it.status === 'OPEN' ? 'open' : 'close'), text: it.status === 'OPEN' ? '장중' : '마감' })),
    h('div', { class: 'kw-px' }, bigNum(valText(it), it.value), u ? h('small', { text: u[0] }) : null,
      h('span', { class: 'kw-pc2 ' + (rate ? cls(it.change) : cls(it.ratio)), text: chgLine })),
    h('dl', { class: 'kw-meta' },
      h('dt', { text: '시세' }), h('dd', { text: `${it.status === 'OPEN' ? '장중' : '마감'} · ${delayText(it)}${it.calc ? ' · 계산값' : ''}` }),
      h('dt', { text: it.eod ? '기준일' : '현지 거래 시각' }), h('dd', {}, localTxt, it.eod ? null : h('small', { text: ` ${city || ''} ${offText(it)}`.trimEnd() })),
      it.eod ? null : [h('dt', { text: '한국 시각' }), h('dd', { text: kstTxt })],
      prev != null ? [h('dt', { text: '전일 종가' }), h('dd', { text: fixed(prev, dpOf(it)) + (rate ? '%' : u ? ' ' + u[1] : '') })] : null,
      h('dt', { text: '단위' }), h('dd', { text: unitTxt }),
      it.via ? [h('dt', { text: '기준' }), h('dd', { text: it.via })] : null),
    note ? h('p', { class: 'kw-note', text: note }) : null);
  { const pc = head.querySelector('.kw-pc2'); if (pc) { pc.__kwT = pc.textContent; pc.__kwN = chgNum(it); } }
  // a country with several indices: one button each, the shown one pressed
  const peers = D.peers ? h('div', { class: 'kw-peers', role: 'group', 'aria-label': `${D.place || ''} 지수`.trim() },
    D.place ? h('b', { class: 'kw-peers-h', text: D.place }) : null,
    D.peers.map(k => { const p = d.byKey.get(k); return p ? h('button', { type: 'button', 'data-k': k, 'aria-pressed': String(k === D.key), onclick: () => switchPeer(k) },
      h('span', { class: 'n', text: p.name }), h('span', { class: 'v ' + (isRef(p) || p.ratio == null ? 'flat' : cls(p.ratio)), text: pct(p.ratio) })) : null; })) : null;
  if (full || !sheet.firstChild) {
    const chartBox = h('div', { class: 'kw-chart' });
    put(sheet,   // put(): peers is null for 원자재 — native replaceChildren would print "null"
      h('div', { class: 'kw-grab', 'aria-hidden': 'true' }),
      h('button', { type: 'button', class: 'kw-x', 'aria-label': '닫기', onclick: () => closeDetail(true) }, closeIcon()),
      peers, head, todayBox(D.today, it), chartBox,
      h('p', { class: 'kw-dsrc', text: srcLine(it) }));
    sheet.classList.toggle('has-peers', !!peers);
  } else {
    const old = $('.kw-peers', sheet);
    if (old && peers) { const f = old.contains(document.activeElement) ? document.activeElement.dataset.k : null; sheet.replaceChild(peers, old); if (f) { const b = peers.querySelector(`button[data-k="${CSS.escape(f)}"]`); if (b) b.focus({ preventScroll: true }); } }
    const oldHead = $('.kw-dh', sheet);
    // the same item again (a refresh while the sheet is open): its number and change line stay and move to the new values — the big
    // number rolls in 화려하게, swaps otherwise (design.md §6-2 · §6-4); the rest of the head is redrawn at once
    if (oldHead && oldHead.dataset.k === head.dataset.k) {
      const ob = $('.kw-px b', oldHead), nb = $('.kw-px b', head), oc = $('.kw-pc2', oldHead), nc = $('.kw-pc2', head);
      if (ob && nb) { const t = nb.__kwT, n = nb.__kwN; nb.replaceWith(ob); setBigNum(ob, t, n); }
      if (oc && nc) { const t = nc.textContent; oc.className = nc.className; nc.replaceWith(oc); swapTo(oc, t, chgNum(it)); }
    }
    sheet.replaceChild(head, oldHead);
    const src = $('.kw-dsrc', sheet); if (src) src.textContent = srcLine(it);
    if (S.detail.chart && S.detail.chart.bars) drawChart();   // its last point is the live value
  }
}

/* the sheet's big number (design.md §3 결정 ③): the whole part at --fs-num, the decimals and the unit one step smaller (.kw-pf) —
   "6,846" + ".51", "3" + ".756%", "99" + ".81조원". Two cells, so 화려하게 rolls each one's changed digits (KH.ui.roll: changed digits
   only, the short way, the rightmost first, no overshoot) and 기본 swaps them (KH.ui.swap, the way the value went); 줄이기 at once */
const splitNum = t => { const m = /^(.*?)(\.\d+)?([^\d.]*)$/.exec(String(t)); return m ? [m[1], (m[2] || '') + (m[3] || '')] : [String(t), '']; };
function bigNum(text, num) {
  const [a, b] = splitNum(text);
  const el = h('b', {}, h('span', { class: 'kw-pi', text: a }), h('span', { class: 'kw-pf', text: b }));
  el.__kwT = text; el.__kwN = num;
  return el;
}
function setBigNum(el, text, num) {
  if (!el || text == null || el.__kwT === text) return;
  const wasN = el.__kwN;
  el.__kwT = text; el.__kwN = num;
  const dir = num != null && wasN != null && isFinite(num) && isFinite(wasN) ? Math.sign(num - wasN) : 0;
  const [a, b] = splitNum(text), [pi, pf] = el.children;
  const roll = motion() === 'fancy' && UI && typeof UI.roll === 'function';
  for (const [cell, t] of [[pi, a], [pf, b]]) {
    if (cell.textContent === t) continue;
    if (roll) UI.roll(cell, t, dir);
    else if (UI && typeof UI.swap === 'function') UI.swap(cell, t, cell.textContent, dir);
    else cell.textContent = t;
  }
}
// the number a sheet's change line stands for (its direction): bp for a yield, else the change
const chgNum = it => isRate(it) ? bpOf(it) : it.change;
// 증시 자금 in the sheet: the business day it is for, the one before, units, where it comes from; no 장중 / 마감
function fundHead(it) {
  const pctU = isFundPct(it);
  const chgLine = pctU ? fundChg(it) : `${fundChg(it)}${it.ratio != null ? ` (${pct(it.ratio)})` : ''}`;
  return h('div', { class: 'kw-dh', 'data-k': it.key },
    h('div', { class: 'kw-path', text: '증시 자금 · 금융투자협회' }),
    h('div', { class: 'kw-nmrow' }, h('i', { class: 'kw-sw', style: `background:${colorOf(it, dScope())}` }), h('b', { id: 'kw-dt', text: it.name }),
      h('span', { class: 'kw-st close', text: '하루 한 번' })),
    h('div', { class: 'kw-px' }, bigNum(valText(it), it.value), h('span', { class: 'kw-pc2 ' + (it.change == null ? 'flat' : cls(it.change)), text: chgLine })),
    h('dl', { class: 'kw-meta' },
      h('dt', { text: '기준일' }), h('dd', { text: mdText(it.basDt, true) || '—' }),
      it.prev != null ? [h('dt', { text: '전 영업일' }), h('dd', {}, valText(Object.assign({}, it, { value: it.prev })), it.prevDt ? h('small', { text: ` ${mdText(it.prevDt, true)}` }) : null)] : null,
      h('dt', { text: '단위' }), h('dd', { text: pctU ? '% (미수금 대비)' : '조원 · 억원 (원 단위 자료를 줄여 보여 줘요)' }),
      h('dt', { text: '갱신' }), h('dd', { text: '하루 한 번 · 보통 다음 영업일 오후에 올라와요' }),
      h('dt', { text: '기준' }), h('dd', { text: '금융투자협회 (금융위원회 공공데이터)' })),
    h('p', { class: 'kw-note', text: (FUND_NOTE[it.fkey] || '') + FUND_COLOR_NOTE }));
}
// the chart of a computed 달러/엔 comes from another source than its headline value: say so
const srcLine = it => isFund(it) ? `출처: 금융투자협회 · 금융위원회 공공데이터포털 · ${FUND_SRC.split(' · ')[1]}`
  : `출처: 네이버 증권${it.via ? ` (${it.via})` : ''} · ${delayText(it)}${it.eod ? '' : ' 시세'}${it.calc ? ' · 차트는 레피니티브 종가' : ''}`;
// 코스피 / 코스닥 opened from the ticker: today's intraday line ({pts:[[unix s, value]], base}) above the daily chart
function todayBox(T, it) {
  if (!T || !Array.isArray(T.pts) || T.pts.length < 2) return null;
  const pts = T.pts.filter(p => isFinite(+p[0]) && isFinite(+p[1]));
  if (pts.length < 2) return null;
  const W = 300, H = 64, day0 = Math.floor((pts[0][0] + 32400) / 86400) * 86400 - 32400, a = day0 + 9 * 3600, b = day0 + 15.5 * 3600;
  const base = isFinite(+T.base) ? +T.base : pts[0][1];
  const vs = pts.map(p => +p[1]).concat([base]), lo = Math.min(...vs), hi = Math.max(...vs);
  const x = t => 2 + Math.max(0, Math.min(1, (t - a) / (b - a))) * (W - 4);
  const y = v => hi === lo ? H / 2 : 4 + (1 - (v - lo) / (hi - lo)) * (H - 8);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + x(p[0]).toFixed(1) + ' ' + y(p[1]).toFixed(1)).join('');
  const L = pts[pts.length - 1], c = cls(L[1] - base);
  const g = svg('svg', { class: 'kw-today-svg ' + c, viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', 'aria-hidden': 'true' },
    svg('line', { class: 'kw-tb', x1: 0, x2: W, y1: y(base).toFixed(1), y2: y(base).toFixed(1) }),
    svg('path', { class: 'kw-tl', d }),
    svg('circle', { class: 'kw-td', cx: x(L[0]).toFixed(1), cy: y(L[1]).toFixed(1), r: 3 }));
  return h('div', { class: 'kw-today' }, h('div', { class: 'kw-ctop' }, h('b', { text: '오늘 흐름' }), h('span', { class: 'kw-cnote', text: '09:00 → 15:30 · 점선은 전일 종가' })), g);
}

/* chart: /api/world/chart/{key}?tf=3m|1y (daily closes). A missing route (plain 404) hides charts for the session. */
const CH = new Map();                                    // key|tf → {at, bars} | {at, err, gone}
const TFS = [['3m', '3개월'], ['1y', '1년']];
async function loadChart() {
  const D = S.detail;
  if (!D) return;
  const box = $('.kw-chart', sheet);
  const d = S.data[D.kind];
  const fund = D.key.startsWith(FUND_PFX);
  if ((fund ? FUNDS.chartGone : !S.chartRoute) || (d && d.charts === false && !fund)) { box.replaceChildren(); box.hidden = true; return; }
  box.hidden = false;
  const k = D.key + '|' + D.tf;
  const c = CH.get(k);
  const fresh = c && (Date.now() - c.at < (c.err ? 15000 : 600000));
  if (fresh) { D.chart = c; drawChart(); return; }
  D.chart = { loading: true };
  drawChart();
  const res = await fetchChart(D.key, D.tf);
  if (!S.detail || S.detail.key !== D.key || S.detail.tf !== D.tf) return;
  if (fund ? FUNDS.chartGone : !S.chartRoute) { box.replaceChildren(); box.hidden = true; return; }
  S.detail.chart = res;
  drawChart();
}
async function fetchChart(key, tf) {
  let res;
  try {
    const fund = key.startsWith(FUND_PFX);
    const j = await getJSON(fund ? `api/funds/chart/${encodeURIComponent(key.slice(FUND_PFX.length))}?tf=${tf}` : `api/world/chart/${encodeURIComponent(key)}?tf=${tf}`);
    const bars = (j && Array.isArray(j.bars) ? j.bars : []).filter(b => b && b.t != null && isFinite(+b.c)).map(b => ({ t: String(b.t), c: +b.c }));
    res = { at: Date.now(), bars };
  } catch (e) {
    if (e.status === 404 && key.startsWith(FUND_PFX)) FUNDS.chartGone = true;   // 증시 자금 without its chart route
    else if (e.status === 404 && !e.json) S.chartRoute = false;      // the Worker has no chart route at all
    res = { at: Date.now(), err: e, gone: e.status === 404 || e.status === 400 };
  }
  CH.set(key + '|' + tf, res);
  return res;
}
// 다시 시도 under a failed chart: the message stays while it works; ✓ then the chart, or ! (KH.ui.retry)
function chartRetry(D) {
  const k = D.key, tf = D.tf, same = () => !!S.detail && S.detail.key === k && S.detail.tf === tf;
  return retryKey('chart:' + k + '|' + tf, async () => {
    CH.delete(k + '|' + tf);
    const res = await fetchChart(k, tf);
    if (!same()) return null;
    if (k.startsWith(FUND_PFX) ? FUNDS.chartGone : !S.chartRoute) { const box = $('.kw-chart', sheet); if (box) { box.replaceChildren(); box.hidden = true; } return null; }
    S.detail.chart = res;
    return !res.err;
  }, () => drawChart(), 'sm', same);
}
// the 기간 segment lives as long as the sheet: KH.ui.seg slides its indicator from one period to the other
let tfSeg = null;
function tfSegment(D) {
  if (!tfSeg) {
    tfSeg = uiSeg(h('div', { class: 'seg kw-tf', role: 'group', 'aria-label': '차트 기간' }, TFS.map(([v, lab]) =>
      h('button', { type: 'button', 'data-v': v, 'aria-pressed': 'false', onclick: () => { const X = S.detail; if (!X || X.tf === v) return; X.tf = v; loadChart(); } }, lab))));
  }
  for (const b of tfSeg.children) b.setAttribute('aria-pressed', String(D.tf === b.dataset.v));
  return tfSeg;
}
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const a in attrs || {}) el.setAttribute(a, attrs[a]);
  for (const k of kids) if (k) el.append(k);
  return el;
}
const shortDate = t => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t); return m ? `${+m[2]}월 ${+m[3]}일` : t; };
const shortDateY = t => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t); return m ? `${m[1].slice(2)}.${m[2]}.${m[3]}` : t; };
function drawChart() {
  const D = S.detail;
  if (!D || !sheet) return;
  const box = $('.kw-chart', sheet);
  if (!box || box.hidden) return;
  const it = S.data[D.kind] && S.data[D.kind].byKey.get(D.key);
  const seg = tfSegment(D);
  const C = D.chart;
  // the segment moves into the new top row: a focused period button keeps the focus
  const keep = seg.contains(document.activeElement) ? document.activeElement : null;
  const put2 = (...kids) => { box.replaceChildren(...kids); if (keep && !keep.isConnected) return; if (keep && document.activeElement !== keep) keep.focus({ preventScroll: true }); };
  const fund = !!it && isFund(it);
  const top = h('div', { class: 'kw-ctop' }, seg, h('span', { class: 'kw-cnote', text: fund ? '영업일마다 · 금융투자협회' : it && it.calc ? '레피니티브 일봉 종가 · 마지막 점은 계산값' : '일봉 종가 · 마지막 점은 현재 값' }));
  if (!C || C.loading) { put2(top, h('div', { class: 'kw-cmsg', text: '차트를 불러오는 중이에요…' })); return; }
  if (C.err) {
    put2(top, h('div', { class: 'kw-cmsg' }, C.gone ? '이 항목은 차트 자료가 없어요.' : '차트를 불러오지 못했어요. ', C.gone ? null : chartRetry(D)));
    return;
  }
  const bars = C.bars.slice();
  // the last point follows the live value: today's bar (or a new one when the daily source lags behind)
  const L = it && parseLocal(it.tradedAt);
  const day = L ? `${L.y}-${pad(L.mo)}-${pad(L.d)}` : fund ? it.basDt : null;     // 증시 자금: the list's business day
  if (day && bars.length) {
    const lastB = bars[bars.length - 1];
    if (lastB.t === day) { if (lastB.c !== it.value) bars[bars.length - 1] = { t: day, c: it.value }; }
    else if (lastB.t < day) bars.push({ t: day, c: it.value });
  }
  if (bars.length < 2) { put2(top, h('div', { class: 'kw-cmsg', text: '차트 자료가 아직 없어요.' })); return; }
  const W = Math.max(220, Math.round(box.clientWidth || 300)), H = 150, padL = 2, padR = fund && !isFundPct(it) ? 74 : 58, padT = 10, padB = 20;
  const cs = bars.map(b => b.c);
  const lo = Math.min(...cs), hi = Math.max(...cs), first = cs[0], last = cs[cs.length - 1];
  const x = i => padL + (i / (bars.length - 1)) * (W - padL - padR);
  const y = v => hi === lo ? padT + (H - padT - padB) / 2 : padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const line = bars.map((b, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(b.c).toFixed(1)).join('');
  const area = line + `L${x(bars.length - 1).toFixed(1)} ${H - padB}L${x(0).toFixed(1)} ${H - padB}Z`;
  // a yield (§3-28): levels in %, moves in bp — "기간 동안 +32.0bp", not a % of a %; 증시 자금's share (%) moves in %p
  const rate = !!it && isRate(it), share = !!it && isFundPct(it);
  const chg = share ? last - first : first ? (last / first - 1) * 100 : 0;
  const dirc = isRef(it || {}) ? 'flat' : cls(chg);
  const dp = it ? dpOf(it) : 2;
  const fv = v => fund ? valText(Object.assign({}, it, { value: v })) : fixed(v, dp) + (rate ? '%' : '');
  // 증시 자금: money moves in % of the start, a share in %p
  const mv = (a, b) => rate ? bpText((b - a) * 100) : share ? pctpText(b - a, fundDp(it)) : !a ? '—' : pct((b / a - 1) * 100);
  const s = svg('svg', { class: 'kw-svg ' + dirc, viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': `${TFS.find(t => t[0] === D.tf)[1]} 차트: ${shortDate(bars[0].t)} ${fv(first)}에서 ${shortDate(bars[bars.length - 1].t)} ${fv(last)}, ${mv(first, last)}. 최고 ${fv(hi)}, 최저 ${fv(lo)}` });
  s.append(
    svg('line', { class: 'kw-base', x1: padL, x2: W - padR, y1: y(first).toFixed(1), y2: y(first).toFixed(1) }),
    svg('path', { class: 'kw-area', d: area }),
    svg('path', { class: 'kw-line', d: line }),
    svg('text', { class: 'kw-yl', x: W - padR + 6, y: (y(hi) + 4).toFixed(1) }, document.createTextNode(fv(hi))),
    svg('text', { class: 'kw-yl', x: W - padR + 6, y: (y(lo) + 1).toFixed(1) }, document.createTextNode(fv(lo))),
    svg('text', { class: 'kw-xl', x: padL, y: H - 5 }, document.createTextNode(D.tf === '1y' ? shortDateY(bars[0].t) : shortDate(bars[0].t))),
    svg('text', { class: 'kw-xl', x: W - padR, y: H - 5, 'text-anchor': 'end' }, document.createTextNode(D.tf === '1y' ? shortDateY(bars[bars.length - 1].t) : shortDate(bars[bars.length - 1].t))));
  const cross = svg('line', { class: 'kw-cross', y1: padT, y2: H - padB, x1: -10, x2: -10 });
  const dot = svg('circle', { class: 'kw-cdot', r: 3, cx: x(bars.length - 1), cy: y(last) });
  s.append(cross, dot);
  const read = h('div', { class: 'kw-read' });
  const showAt = i => {
    const b = bars[i], r = share ? b.c - first : first ? (b.c / first - 1) * 100 : 0;
    read.replaceChildren(h('span', { text: D.tf === '1y' ? shortDateY(b.t) : shortDate(b.t) }), h('b', { text: fv(b.c) }),
      h('span', { class: isRef(it || {}) ? 'flat' : cls(r), text: i ? `${mv(first, b.c)} (기간 시작 대비)` : '기간 시작' }));
    dot.setAttribute('cx', x(i)); dot.setAttribute('cy', y(b.c));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i));
  };
  const reset = () => {
    read.replaceChildren(h('span', { text: `${TFS.find(t => t[0] === D.tf)[1]} 동안` }), h('b', { class: isRef(it || {}) ? 'flat' : cls(chg), text: mv(first, last) }),
      h('span', { class: 'kw-hl', text: `최고 ${fv(hi)} · 최저 ${fv(lo)}` }));
    dot.setAttribute('cx', x(bars.length - 1)); dot.setAttribute('cy', y(last));
    cross.setAttribute('x1', -10); cross.setAttribute('x2', -10);
  };
  s.addEventListener('pointermove', e => {
    const r = s.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    const i = Math.max(0, Math.min(bars.length - 1, Math.round((px - padL) / (W - padL - padR) * (bars.length - 1))));
    showAt(i);
  });
  s.addEventListener('pointerleave', reset);
  reset();
  put2(top, read, s);
}

/* ───────── polling ───────── */
function schedule(ms) {
  clearTimeout(S.timer); S.timer = 0;
  if (!S.shown || !LIVE) return;
  S.timer = setTimeout(() => load(S.kind), ms);
}
// → true (arrived) · false (failed) · null (superseded). quiet (the 다시 시도 key): the message stays while it works and nothing is
// drawn here — the key shows ✓ and then draws, or ! and the message stays
async function load(kind, quiet) {
  clearTimeout(S.timer); S.timer = 0;
  if (!S.shown || S.kind !== kind || !LIVE || document.hidden) return null;
  const seq = ++S.seq;
  if (S.ac) S.ac.abort();
  const ac = S.ac = new AbortController();
  S.busy = kind;
  if (!quiet && !S.data[kind] && S.err[kind]) { S.err[kind] = null; render(); }   // the automatic retry shows "loading" again
  let ok = false;
  try {
    const j = await getJSON(worldUrl(kind), ac.signal);
    if (seq !== S.seq) return null;
    S.data[kind] = withFunds(normalise(j, kind));
    if (kind === 'commodity') { loadFunds(); loadKxim(); }
    S.at[kind] = Date.now();
    S.err[kind] = null;
    failedW.delete('data:' + kind);
    ok = true;
  } catch (e) {
    if (seq !== S.seq) return null;
    S.err[kind] = e;
  }
  S.busy = null;
  if (!quiet) render();
  announce(kind, ok);
  schedule(ok ? POLL_MS : RETRY_MS);
  return ok;
}
function announce(kind, ok) {
  const K = KINDS[kind], key = kind + (ok ? ':ok' : ':err');
  if (S.announced[kind] === key) return;
  S.announced[kind] = key;
  const d = S.data[kind];
  els.live.textContent = ok ? (d && d.all.length ? `${K.title} ${d.all.length}개를 불러왔어요` : K.empty) : (d ? `${K.title}를 새로 받지 못했어요. 이전 값을 보여 줘요` : K.fail);
}
document.addEventListener('visibilitychange', () => {
  if (!S.shown || !LIVE) return;
  if (document.hidden) { clearTimeout(S.timer); S.timer = 0; S.seq++; S.busy = null; if (S.ac) S.ac.abort(); clearTimeout(nightT); nightT = 0; return; }
  if (S.mode === 'geo') { drawNight(); schedNight(); }
  const age = Date.now() - (S.at[S.kind] || 0);
  if (!S.data[S.kind] || age >= POLL_MS) load(S.kind); else schedule(POLL_MS - age);
});
// the clock in the header refreshes everything at once (AGENTS §3-6): fetch now, keep view, scroll and focus
document.addEventListener('kh:refresh', () => { if (S.shown && LIVE && !document.hidden) load(S.kind); });
document.addEventListener('kh:motion', () => { if (S.shown && els && !els.snap) syncMotion(); });
// the palette or the theme changed: re-read the colours and redraw what is on screen (the data stays; nothing is fetched)
let restylePending = false;
function restyle() {
  TOK = null;
  if (restylePending) return;
  restylePending = true;
  queueMicrotask(() => {
    restylePending = false;
    TOK = null;
    if (S.shown && els && !els.snap) {
      render();
      if (els.g && S.mode === 'geo') drawNight();
    }
    if (S.detail && sheet) {
      fillDetail(false);                                  // the colour chip beside the name (and the chart, when it is drawn); the rest reads CSS
    }
  });
}
document.addEventListener('kh:palette', restyle);
document.addEventListener('kh:theme', restyle);
addEventListener('resize', () => { if (S.shown) schedRender(); });
if (document.fonts) {
  const refit = () => { MW.clear(); family = ''; if (S.shown) schedRender(); };
  if (document.fonts.ready) document.fonts.ready.then(refit);
  document.fonts.addEventListener && document.fonts.addEventListener('loadingdone', refit);
}

/* ───────── public API ───────── */
function show(kind) {
  kind = kind === 'commodity' || kind === 'cmdty' ? 'commodity' : 'index';
  if (!scaffold()) return;
  const sameKind = S.kind === kind;
  if (!sameKind) {
    closeDetail(false); S.kind = kind; S.focusKey = null; S.listFocus = null;
    if (els.tiles) { for (const el of els.tiles.values()) el.remove(); for (const el of els.heads.values()) el.remove(); els.tiles.clear(); els.heads.clear(); }
    if (els.rows) { els.list.replaceChildren(); els.rows.clear(); els.listSig = ''; }
  }
  const was = S.shown;
  S.shown = true;
  if (!LIVE) { renderSnapshot(); return; }
  render();
  if (was && sameKind && (S.timer || S.busy === kind)) return;   // already polling / loading this kind
  const age = Date.now() - (S.at[kind] || 0);
  if (!S.data[kind] || age >= POLL_MS) load(kind); else { schedule(POLL_MS - age); if (kind === 'commodity') { loadFunds(); loadKxim(); } }
}
function hide() {
  S.shown = false;
  clearTimeout(S.timer); S.timer = 0;
  clearTimeout(nightT); nightT = 0;
  S.seq++; S.busy = null;
  if (S.ac) S.ac.abort();
  closeDetail(false);
}
// the tile map in map pixels (same shape as KH.layout(), for "이미지로 저장"). In the list view it is the map the 지도
// view draws at this width, laid out off screen: the saved picture is a map either way (extras says "지도를 저장했어요").
function headSub(g) {
  const avg = avgOf(g.g.items);
  const vt = avg == null ? '' : pct(avg);
  return vt && g.w - tw(g.g.name, 700) * 12 - 16 >= tw(vt, 600) * 12 + 4 ? vt : '';
}
function layout() {
  if (!S.shown || !els || els.snap) return [];
  const d = S.data[S.kind];
  if (!d || !d.all.length) return [];
  const out = [];
  if (S.view === 'map' && els.boxes && !els.map.hidden) {
    for (const g of els.boxes.heads) {
      const el = els.heads.get(g.g.key);
      out.push({ kind: 'sector', x: g.x, y: g.y, w: g.w, h: g.h, color: tok().sec, label: g.hd ? g.g.name : '', sub: g.hd && el ? el.__sub || '' : '', hd: g.hd });
    }
    for (const t of els.boxes.tiles) {
      const el = els.tiles.get(t.it.key);
      out.push({ kind: 'tile', x: t.x, y: t.y, w: t.w, h: t.h, color: el ? el.__col : colorOf(t.it), label: t.it.name, sub: el ? el.__sub || '' : '', code: t.it.key });
    }
    return out;
  }
  const W = Math.round((els.list.clientWidth || els.map.clientWidth || root.clientWidth || 0));
  if (!W) return [];
  const Lo = computeLayout(d, W, Math.max(480, Math.min(760, Math.round(W * 0.6))));
  for (const g of Lo.heads) out.push({ kind: 'sector', x: g.x, y: g.y, w: g.w, h: g.h, color: tok().sec, label: g.hd ? g.g.name : '', sub: g.hd ? headSub(g) : '', hd: g.hd });
  for (const t of Lo.tiles) {
    const L = fit(tileTexts(t.it, t.g), t.w, t.h);
    out.push({ kind: 'tile', x: t.x, y: t.y, w: t.w, h: t.h, color: colorOf(t.it), label: t.it.name, sub: L && L.lv >= 2 ? chipText(t.it) : '', code: t.it.key });
  }
  return out;
}
// the ticker (src/extras) opens an item's sheet from any tab: the data is fetched here when the 해외 tab never loaded it
async function openDetailKey(key, opts) {
  opts = opts || {};
  key = String(key);
  const find = () => ['index', 'commodity'].find(k => S.data[k] && S.data[k].byKey.has(key));
  let kind = find();
  if (!kind && LIVE) {
    await Promise.all(['index', 'commodity'].map(async k => {
      if (S.data[k]) return;
      try { S.data[k] = withFunds(normalise(await getJSON(worldUrl(k)), k)); S.at[k] = Date.now(); } catch (e) { /* the other kind may still have it */ }
    }));
    kind = find();
  }
  if (!kind) return false;
  openDetail(key, opts.opener || null, null, null, kind, opts.today, opts.scope);
  return !!S.detail;
}
// zones() → the ranges 지표 rows colour on now, wherever they show (the 지표 tab, or a sheet the ticker opened on another tab):
// {zone key: {name, value (±R), unit '%'|'bp', p95, group}} — keys = the group keys + 'forced' (증시 자금's 반대매매, group 'funds');
// under a picked range only the bp zones (금리); null before any 지표 data or with an older template — for QA (the colours:
// KH.colorOf(a yield's bp or the row's %, {scope: 'world', range: value}))
const zonesApi = () => Z && Z.zones.size ? Object.fromEntries(zoneList().map(z => [z.key, { name: z.name, value: z.value, unit: z.unit, p95: z.p95, group: z.group }])) : null;
window.KHWorld = { show, hide, layout, shown: () => S.shown ? S.kind : null, view: () => S.view, openDetail: openDetailKey, detailOpen: () => !!S.detail,
  zones: zonesApi };

// the template may have tried show() before this script existed (page opened at #world / #cmdty): start now
try {
  const m = typeof KH.market === 'function' ? KH.market() : null;
  const w = document.getElementById('world');
  if ((m === 'world' || m === 'cmdty') && w && !w.hidden) show(m === 'cmdty' ? 'commodity' : 'index');
} catch (e) { /* the template will call show() itself */ }
})();
