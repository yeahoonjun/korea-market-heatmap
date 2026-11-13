/* 공시 배지 (docs/standards/disclosure.md · AGENTS §3-29 server, §3-30 screen) — C안 (사용자 2026-11-14 01:44 "C안으로 할게",
   01:46 "나머지는 추천대로": 지도 표시 기본 실적 · 주요, 목록은 지도 종목만으로 시작; "새로운 공시에 '새'로 표기보다는 시간 앞 초록색
   동그라미" → 새 공시는 글자 대신 시각 앞의 작은 점 — 색은 --new-dot 한 토큰(파랑: 초록은 하락, 앰버는 컨트롤이라서)).
   window.KHDisc = { refresh() → Promise<boolean>, rows(code) → [row], info(rcpNo) → {s, isNew} | null }; KH.disclosures(code?).
   What it draws (all from GET api/disclosures/today, never a body / summary / number pulled out of a filing):
   · tiles: a folded bottom-right corner (KH.marks 'disc') on stocks with a filing of the kinds chosen in 표시 설정 (기본 실적 · 주요),
     a bigger corner when one of them is new (first seen within 30 min and after the server started watching: s > since);
   · the map-header chip "공시 26" (#stage-tools): on → only those stocks stay bright (KH.marks.only), not remembered;
   · the legend item "공시 26종목 · 큰 귀퉁이 = 30분 안"; the tooltip / quick-view block (KH.cardExtra): up to 3 filings, DART links
     in the quick view + "공시 모두 보기" (the stock page's 뉴스·공시 › 공시);
   · the "오늘 공시" tab of the news card (KHNews.addTab): kind tabs, 지도 종목만, stock chips (quick view), row hover lights the tile;
   · two settings (공시 보기 · 지도에 표시할 종류) and the footer credit.
   Data: while the setting is on, the page is visible and a stock map is shown — every 60 s on weekdays 07:00–19:00 KST, else 5 min;
   failures back off 1 → 2 → 4 → 5 min, "오래됨" after 5 min of failures. The Worker's weak ETag goes back as If-None-Match: a 304
   keeps the list and takes the time from x-as-of. A Worker without the route (404): nothing of this shows. Snapshot (dist/): the tab says
   "실시간 버전에서 볼 수 있어요", nothing else. */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function') return;
const h = KH.h, UI = KH.ui || {};
const LIVE = KH.MODE === 'live';
const KINDS = ['실적', '주요', '정기', '지분', '기타'];
const KTABS = [['main', '실적·주요'], ['정기', '정기'], ['지분', '지분'], ['기타', '기타'], ['all', '전체']];
const NEW_MIN = 30, STALE_MS = 5 * 60e3, TIMEOUT_MS = 12e3, MAX_ROWS = 30, MAX_WAIT = 5 * 60e3;
const DART = r => 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + r;
const narrowMQ = matchMedia('(max-width: 760px)'), hoverMQ = matchMedia('(hover: hover) and (pointer: fine)');
const MINUS = '−';
const pct = v => (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v).toFixed(2) + '%';
const cls = v => (v > 0 ? 'up' : v < 0 ? 'dn' : 'flat');
// native append / replaceChildren print "null" for a null child — every list goes through this filter
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
const icon = name => (typeof UI.icon === 'function' ? UI.icon(name) : null);
const live = text => { if (typeof UI.live === 'function') UI.live(text); };
const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
const pad = n => String(n).padStart(2, '0');
const WD = ['일', '월', '화', '수', '목', '금', '토'];
// KST wall clock of an instant: {date 'YYYY-MM-DD', min (minutes from 00:00), wd (0 = 일), hm 'HH:MM'}
function kstOf(ms) {
  const k = new Date(ms + 9 * 3600e3);
  return { date: `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}`, min: k.getUTCHours() * 60 + k.getUTCMinutes(), wd: k.getUTCDay(), hm: `${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}` };
}
const toMin = s => +s.slice(0, 2) * 60 + +s.slice(3, 5);
const ymdParts = ymd => ymd.split('-').map(Number);
const dayLong = ymd => { const [y, m, d] = ymdParts(ymd); return `${m}월 ${d}일 (${WD[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]})`; };
const dayShort = ymd => { const [, m, d] = ymdParts(ymd); return `${m}/${d}`; };
// "17:39 기준" from the ISO asOf (another day: "11/13 17:39")
function asOfText(iso) {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(iso || '');
  if (!m) return '';
  return m[1] === kstOf(nowMs()).date ? m[2] : `${dayShort(m[1])} ${m[2]}`;
}
const isoMs = iso => { const t = Date.parse(iso || ''); return isNaN(t) ? 0 : t; };

/* ───────── state ───────── */
const S = {
  on: true, kinds: new Set(['실적', '주요']), ready: false,
  data: null, etag: '', okAt: 0, lastTry: 0, tries: 0, loading: true, err: false, busy: null, timer: 0, gone: false,
  view: [], byCode: new Map(), marks: new Map(), markSig: '', fresh: new Set(), seen: '', rp: null, rpKey: '',
  mapSet: new Set(), mapKey: '',
  kt: 'main', only: true, open: false, L: { measure: false, base: 5, two: false, phone: narrowMQ.matches, rowsMax: MAX_ROWS },
  shown: 0, pending: false, ptr: false, hov: '', chipOn: false, lgKey: '', tabbed: false, names: null, namesBusy: false,
};
const today = () => kstOf(nowMs()).date;
const isToday = () => !!S.data && S.data.date === today();
const dayWord = () => (!S.data || isToday() ? '오늘' : `${ymdParts(S.data.date)[1]}월 ${ymdParts(S.data.date)[2]}일`);
const worldTab = () => { const m = typeof KH.market === 'function' ? KH.market() : ''; return m === 'world' || m === 'cmdty'; };
// 새 = today's filing, first seen after the server started watching (s > since), within 30 minutes of now (a replay of today: of its time)
function isNew(x) {
  const d = S.data;
  if (!d || !x.s || !d.since || x.s <= d.since || d.date !== today()) return false;
  const now = S.rp && S.rp.kind === 'same' ? toMin(S.rp.hm) : kstOf(nowMs()).min;
  const age = now - toMin(x.s);
  return age >= 0 && age <= NEW_MIN;
}
// same stock · same title → one row "· 4건" (임원 소유상황 보고서 여러 건)
function merge(list) {
  const out = [], seen = new Map();
  for (const x of list) {
    const key = x.c + '|' + x.t;
    const g = seen.get(key);
    if (g) { g.n++; if (!g.isNew && isNew(x)) g.isNew = true; continue; }
    const m = Object.assign({}, x, { n: 1, isNew: isNew(x) });
    seen.set(key, m); out.push(m);
  }
  return out;
}
// the server's tag ("기재정정", "철회", "정정본 있음", "발행조건확정") as a short dashed badge
const noteText = n => (!n ? '' : /정정$/.test(n) ? '정정' : n === '발행조건확정' ? '확정' : n.length > 6 ? n.slice(0, 6) : n);
const nameOf = c => { const st = KH.stock(c); if (st && st.n) return st.n; const x = S.names && S.names[c]; return x ? x[0] : c; };
const mktOf = c => { const st = KH.stock(c); const m = st ? st.m : S.names && S.names[c] ? S.names[c][1] : ''; return m === 'Q' ? '코스닥' : m === 'K' ? '코스피' : ''; };
function quoteOf(code) {
  const st = KH.stock(code);
  if (!st) return null;
  const q = typeof KH.quote === 'function' ? KH.quote(code) : null;
  const r = Number(q && q.r != null ? q.r : st.r);
  return { n: st.n, r: Number.isFinite(r) ? r : 0 };
}
function needNames() {
  if (S.names || S.namesBusy || typeof KH.loadData !== 'function') return;
  S.namesBusy = true;
  KH.loadData('names').then(j => { S.names = j && j.n ? j.n : {}; S.namesBusy = false; renderPanel({ force: true }); }, () => { S.namesBusy = false; });
}
const kindLabel = () => KINDS.filter(k => S.kinds.has(k)).join('·');
const dot = () => [h('i', { class: 'dc-dot', 'aria-hidden': 'true' }), h('span', { class: 'sr', text: '새 공시 ' })];
function timeEl(x) {
  const t = x.s || (S.data && S.data.date !== today() ? dayShort(S.data.date) : '오늘');
  return h('time', { class: 'dc-tm', datetime: S.data ? S.data.date + (x.s ? 'T' + x.s : '') : null }, x.isNew ? dot() : null, t);
}

/* ───────── snapshot: the tab says where to see it; no chip, no corners, no rows in the build ───────── */
if (!LIVE) {
  const pane = h('div', { class: 'dc-pane' }, h('ol', { class: 'nw-list is-msg' }, h('li', { class: 'nw-msg' },
    h('b', { text: '공시는 실시간 버전에서 볼 수 있어요' }),
    h('small', { text: '이 화면은 정해진 시점의 스냅샷이라 새 공시를 받지 않아요.' }),
    h('a', { href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '실시간 버전 열기' }))));
  if (window.KHNews && typeof window.KHNews.addTab === 'function') window.KHNews.addTab({ key: 'disc', label: '오늘 공시', pane, list: pane.firstChild, render() {} });
  window.KHDisc = { refresh: () => Promise.resolve(false), rows: () => [], info: () => null };
  KH.disclosures = () => null;
  return;
}

/* ───────── the map-header chip: [corner] 공시 26 — on → only those stocks stay bright ───────── */
const chip = h('button', { type: 'button', class: 'dc-hchip', 'aria-pressed': 'false' });
chip.addEventListener('click', () => {
  if (chip.getAttribute('aria-disabled') === 'true') return;
  setChip(!S.chipOn, true);
});
function setChip(on, say) {
  S.chipOn = !!on;
  chip.setAttribute('aria-pressed', String(S.chipOn));
  if (typeof KH.marks === 'object' && KH.marks) KH.marks.only(S.chipOn ? 'disc' : null);
  if (say) live(S.chipOn ? `공시 있는 ${mapCount()}종목만 밝게 보여요.` : '모든 종목을 다시 보여요.');
}
const mapCount = () => { let n = 0; for (const c of S.marks.keys()) if (S.mapSet.has(c)) n++; return n; };
// shown: live, setting on, a stock map (not 해외 · 지표, not the theme overview), not replaying another day
const chipWanted = () => S.on && !S.gone && !worldTab() && S.mapSet.size > 0 && !(S.rp && S.rp.kind === 'other');
const staleNow = () => !!S.data && ((S.tries > 0 && Date.now() - S.okAt > STALE_MS) || (S.data.stale && nowMs() - isoMs(S.data.asOf) > STALE_MS));
function renderChip() {
  const slot = document.getElementById('stage-tools');
  if (!chipWanted()) { if (S.chipOn) setChip(false); if (chip.isConnected) chip.remove(); return; }
  if (slot && chip.parentNode !== slot) slot.append(chip);
  const sw = h('i', { class: 'dmsw', 'aria-hidden': 'true' }), ck = h('i', { class: 'ck', 'aria-hidden': 'true' });
  chip.removeAttribute('title');
  if (!S.data && S.loading) {
    put(chip, ck, icon('spin'), h('span', { text: '공시' }));
    chip.setAttribute('aria-disabled', 'true'); chip.setAttribute('aria-label', '공시 불러오는 중');
  } else if (!S.data) {
    put(chip, ck, sw, h('span', { text: '공시' }), h('b', { class: 'dc-bad', 'aria-hidden': 'true', text: '!' }));
    chip.setAttribute('aria-disabled', 'true'); chip.title = '공시를 불러오지 못했어요'; chip.setAttribute('aria-label', '공시를 불러오지 못했어요');
  } else {
    const n = mapCount(), stale = staleNow(), rp = S.rp && S.rp.kind === 'same';
    put(chip, ck, sw, h('span', { text: '공시' }), h('span', { class: 'dc-n', text: String(n) }), stale ? h('b', { class: 'dc-bad', 'aria-hidden': 'true', text: '!' }) : null);
    if (n) chip.removeAttribute('aria-disabled'); else chip.setAttribute('aria-disabled', 'true');
    chip.setAttribute('aria-label', `${isToday() ? '' : dayWord() + ' '}공시 있는 종목만 밝게, ${n}종목${stale ? ' · 몇 분째 새 공시를 받지 못했어요' : ''}${rp ? ` · ${S.rp.hm}까지` : ''}`);
    if (rp) chip.title = `다시 보기 — ${S.rp.hm}까지 들어온 공시`;
    else if (!isToday()) chip.title = `${dayLong(S.data.date)} 공시`;
    if (!n && S.chipOn) setChip(false);
  }
  if (S.chipOn && chip.getAttribute('aria-disabled') === 'true') setChip(false);
}

/* ───────── the legend item: [corner] 공시 26종목 · [big corner] 큰 귀퉁이 = 30분 안 ───────── */
function legendEls() {
  if (!S.on || S.gone || worldTab() || !S.mapSet.size) return null;
  if (S.rp && S.rp.kind === 'other') return h('span', { class: 'lg note dc-lg', text: '다시 보기 중에는 오늘 공시만 보여요' });
  const sw = () => h('i', { class: 'dmsw', 'aria-hidden': 'true' });
  if (!S.data) return h('span', { class: 'lg dc-lg' }, sw(), '공시 ', h('b', { text: S.loading ? '…' : '—' }));
  const n = mapCount();
  if (!n) return null;
  return [h('span', { class: 'lg dc-lg', title: isToday() ? null : `${dayLong(S.data.date)} 공시` }, sw(), isToday() ? '공시 ' : `${dayShort(S.data.date)} 공시 `, h('b', {}, String(n), h('span', { class: 'u', text: '종목' }))),
    h('span', { class: 'lg dc-lg2' }, h('i', { class: 'dmsw big', 'aria-hidden': 'true' }), '큰 귀퉁이 = 30분 안')];
}
function renderLegend() {
  const n = mapCount(), key = [S.on, S.gone, worldTab(), S.mapSet.size > 0, S.rp ? S.rp.kind : '', !!S.data, S.loading, n, S.data ? S.data.date : ''].join('|');
  if (key === S.lgKey) return;
  S.lgKey = key;
  if (typeof KH.legendRefresh === 'function') KH.legendRefresh();
}

/* ───────── the tooltip / quick-view block (KH.cardExtra): up to 3 filings of the marked kinds ───────── */
function block(st, how) {
  if (!S.on || S.gone || !S.data) return null;
  const all = S.byCode.get(st.c);
  if (!all || !all.length) return null;
  const tip = how === 'tip';
  const rows = merge(all), marked = rows.filter(x => S.kinds.has(x.k)), top = marked.slice(0, 3);
  const moreN = marked.slice(3).reduce((a, x) => a + x.n, 0);
  const cnt = {};
  for (const x of all) if (!S.kinds.has(x.k)) cnt[x.k] = (cnt[x.k] || 0) + 1;
  const rest = KINDS.filter(k => cnt[k]).map(k => `${k} ${cnt[k]}`);
  const head = h('div', { class: 'dsc-h' }, h('b', { text: `${dayWord()} 공시` }), `${all.length}건`,
    top.some(x => x.isNew) ? h('span', { class: 'r' }, h('i', { class: 'dc-dot', 'aria-hidden': 'true' }), `${NEW_MIN}분 안`) : null);
  const row = x => {
    const label = x.t + (x.n > 1 ? ` · ${x.n}건` : '');
    const note = noteText(x.nt);
    const kids = [h('span', { class: 'dk' }, h('span', { class: 'dc-kb', text: x.k }), note ? h('span', { class: 'dc-kb fix', text: note }) : null),
      h('span', { class: 'tt', text: label }), timeEl(x)];
    if (tip) return h('div', { class: 'dr', title: label }, kids);
    return h('a', { class: 'dr', href: DART(x.r), target: '_blank', rel: 'noopener', 'data-fk': 'r' + x.r,
      'aria-label': `${x.isNew ? '새 공시 · ' : ''}${label}${note ? ` (${note})` : ''} — DART, 새 탭에서 열려요` }, kids);
  };
  const out = [head, top.map(row)];
  const extra = [moreN > 0 ? `${kindLabel()} ${moreN}건 더` : null, ...rest].filter(Boolean);
  if (extra.length) out.push(h('div', { class: 'dsc-more' }, top.length ? '그 밖에 ' : '', h('b', { text: extra.join(' · ') }), top.length ? '' : ' — 지도에 표시하지 않는 종류예요'));
  if (tip) { if (hoverMQ.matches) out.push(h('div', { class: 'dsc-hint', text: '누르면 종목 페이지 › 뉴스·공시에서 모두 볼 수 있어요' })); }
  else out.push(h('div', { class: 'dall' }, h('button', { type: 'button', class: 'dc-all', 'data-fk': 'all', onclick: ev => openAll(st.c, ev.currentTarget) }, `공시 모두 보기 (${all.length})`)));
  return h('div', { class: 'dsc' + (tip ? '' : ' dsc-q') }, out);
}
function openAll(code, opener) {
  const o = { opener, tab: 'news', newsKind: 'disc' };
  if (typeof KH.openStock === 'function') KH.openStock(code, o);
  else if (window.KHStock) window.KHStock.open(code, o);
}

/* ───────── the "오늘 공시" tab of the news card ───────── */
const ktabs = h('div', { class: 'seg dc-ktabs', role: 'group', 'aria-label': '공시 종류' },
  KTABS.map(([k, t]) => h('button', { type: 'button', 'data-k': k, 'aria-pressed': String(k === S.kt) }, h('span', { text: t }), h('small', { class: 'num' }))));
const onlyBtn = h('button', { type: 'button', class: 'nw-only dc-only', 'aria-pressed': 'true' },
  h('i', { class: 'nw-ck', 'aria-hidden': 'true' }), '지도 종목만', h('span', { class: 'nw-n' }));
const list = h('ol', { class: 'nw-list dc-list', 'aria-labelledby': 'news-t-disc' });
const more = typeof UI.akey === 'function' ? UI.akey('nw-kbtn nw-more', { idle: '더보기 (30개)', less: '접기' }, 'idle')
  : h('button', { type: 'button', class: 'nw-kbtn nw-more', text: '더보기' });
more.setAttribute('aria-expanded', 'false');
const credit = h('small', { text: '공시: 금융감독원 DART (OpenDART) — 제목 · 종류만 보여 드려요. 시각은 판세가 처음 본 때예요. 원문은 DART에서 새 탭으로 열려요.' });
const pane = h('div', { class: 'dc-pane', id: 'news-p-disc' }, h('div', { class: 'nw-sub dc-sub' }, ktabs, onlyBtn), list, h('div', { class: 'nw-ft' }, more, credit));
if (typeof UI.seg === 'function') UI.seg(ktabs);

function listFor(kt = S.kt, only = S.only) {
  let a = S.view;
  if (only) a = a.filter(x => S.mapSet.has(x.c));
  if (kt === 'main') a = a.filter(x => x.k === '실적' || x.k === '주요');
  else if (kt === 'mark') a = a.filter(x => S.kinds.has(x.k));
  else if (kt !== 'all') a = a.filter(x => x.k === kt);
  return merge(a);
}
function retryKey(sm) {
  if (typeof UI.retry !== 'function') return null;
  return UI.retry({ cls: 'nw-kbtn' + (sm ? ' sm' : ''), run: () => load({ silent: true }), render: () => refreshAll() });
}
function msg(title, sub, extra) {
  return h('li', { class: 'nw-msg' }, h('b', { text: title }), sub ? h('small', { text: sub }) : null, extra || null);
}
const skel = n => Array.from({ length: n }, (_, k) => h('li', { class: 'dc-row skel', 'aria-hidden': 'true' },
  h('time', { class: 'dc-tm' }, h('i', { class: 'nw-sk', style: 'width:34px' })), h('span', { class: 'dc-cc' }, h('i', { class: 'nw-sk', style: 'width:90px' })),
  h('span', { class: 'dc-k' }, h('i', { class: 'nw-sk', style: 'width:28px' })), h('span', { class: 'nw-tt dc-tt' }, h('i', { class: 'nw-sk', style: `width:${50 + (k * 37) % 35}%` }))));
function stockChip(c) {
  const q = quoteOf(c);
  if (q) return h('button', { type: 'button', class: 'nw-chip dc-chip', 'data-c': c, 'aria-label': `${q.n} ${pct(q.r)} · 빠른 보기` },
    h('span', { class: 'dc-cn', text: q.n }), h('b', { class: cls(q.r), text: pct(q.r) }));
  const n = nameOf(c), m = mktOf(c);
  return h('button', { type: 'button', class: 'dc-chipx', 'data-c': c, 'data-x': '1', 'aria-label': `${n}${m ? ' ' + m : ''} · 종목 페이지` },
    h('span', { class: 'dc-cn', text: n }), m ? h('small', { text: m }) : null);
}
function row(x, k, grow) {
  const note = noteText(x.nt), name = nameOf(x.c), anim = grow && k >= S.shown;
  const label = `${name} ${x.t}${x.n > 1 ? ` (${x.n}건)` : ''}${note ? ` (${note})` : ''}`;
  const tt = [x.t, x.n > 1 ? h('span', { class: 'dc-x', text: `${x.n}건` }) : null];
  return h('li', { class: 'dc-row' + (anim ? ' in' : ''), style: anim ? `--d:${Math.min(8, k - S.shown) * 20}ms` : null, 'data-c': x.c },
    timeEl(x), h('span', { class: 'dc-cc' }, stockChip(x.c)),
    h('span', { class: 'dc-k' }, h('span', { class: 'dc-kb', text: x.k }), note ? h('span', { class: 'dc-kb fix', text: note }) : null),
    h('span', { class: 'nw-tt dc-tt', title: x.t + (x.f ? ` · 제출인 ${x.f}` : '') },
      h('a', { href: DART(x.r), target: '_blank', rel: 'noopener', 'aria-label': `${x.isNew ? '새 공시 · ' : ''}${label} — DART, 새 탭에서 열려요` }, tt)));
}
const reading = () => S.ptr || pane.contains(document.activeElement);
function emptyMsg() {
  const k = kstOf(nowMs()), weekend = k.wd === 0 || k.wd === 6;
  if (weekend) return msg('오늘은 휴장일이라 공시가 거의 없어요', '지난 거래일 공시는 종목 페이지의 뉴스·공시 탭에 있어요.');
  if (k.min < 600) return msg('아직 오늘 공시가 없어요', '보통 아침 7시쯤부터 들어와요 · 1분마다 확인해요.');
  return msg('아직 공시가 없어요', '1분마다 확인해요.');
}
function renderPanel(o = {}) {
  if (!S.tabbed) return;
  const L = S.L, d = S.data, none = !d || !S.view.length;
  if (!o.force && reading() && list.querySelector('.dc-row:not(.skel)')) { S.pending = true; return; }
  S.pending = false;
  pane.dataset.k1 = ['정기', '지분', '기타'].includes(S.kt) ? '1' : '0';
  for (const b of ktabs.children) {
    b.setAttribute('aria-pressed', String(b.dataset.k === S.kt));
    if (none) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled');
    const t = none ? '' : String(listFor(b.dataset.k).length), sm = b.querySelector('small');
    if (sm.textContent !== t) sm.textContent = t;
  }
  if (none) onlyBtn.setAttribute('aria-disabled', 'true'); else onlyBtn.removeAttribute('aria-disabled');
  onlyBtn.setAttribute('aria-pressed', String(S.only));
  onlyBtn.querySelector('.nw-n').textContent = none ? '' : String(new Set(S.view.filter(x => S.mapSet.has(x.c)).map(x => x.c)).size);
  const all = d ? listFor() : [], base = L.base;
  const shown = L.measure ? 0 : S.open ? Math.min(MAX_ROWS, all.length) : base;
  const perCol = n => (L.two ? Math.ceil(n / 2) : n);
  list.classList.toggle('c2', L.two);
  list.style.setProperty('--nw-r', String(perCol(Math.max(shown, base))));
  list.style.minHeight = L.phone ? '' : L.measure ? '0px' : `calc(var(--nw-rh) * ${perCol(base)})`;
  let kids;
  if (L.measure) kids = [];
  else if (!d && S.loading) kids = skel(base);
  else if (!d) kids = [msg('공시를 불러오지 못했어요', 'DART 응답이 없었어요. 잠시 뒤 다시 눌러 주세요.', retryKey(false))];
  else if (!S.view.length) kids = [S.rp && S.rp.kind === 'same' ? msg(`${S.rp.hm}까지 들어온 공시가 없어요`, '다시 보기를 끝내면 지금 공시가 보여요.') : emptyMsg()];
  else if (!all.length) {
    const kn = KTABS.find(x => x[0] === S.kt)[1], past = !isToday();
    kids = [msg(S.only ? `지도 종목의 ${kn} 공시가 ${past ? '' : '아직 '}없어요` : `${past ? '' : '아직 '}이 종류 공시가 없어요`, S.only ? "'지도 종목만'을 끄면 상장사 전체를 볼 수 있어요." : '')];
  } else {
    if (!S.only && all.slice(0, shown).some(x => !KH.stock(x.c))) needNames();
    kids = all.slice(0, shown).map((x, k) => row(x, k, o.grow));
  }
  put(list, kids);
  list.classList.toggle('is-msg', kids.length === 1 && kids[0].classList.contains('nw-msg'));
  if (!L.measure) S.shown = d ? Math.min(shown, all.length) : 0;
  const total = Math.min(MAX_ROWS, all.length);
  const lab = more.querySelector('.kl[data-l="idle"]');
  if (lab) lab.textContent = `더보기 (${total}개)`;
  if (more.dataset.st !== 'less') more.setAttribute('aria-label', `더보기 (${total}개)`);
  more.hidden = !(d && (total > base || S.open));
  if (S.hov && !list.querySelector('.dc-row:hover')) setHover(null);
}
// the head of the card while this tab is shown: "17:39 기준" · 불러오는 중 · 받은 목록 없음 · 오래됨 · 다시 보기
function atKids(atEl) {
  const d = S.data;
  if (!d && S.loading) return [icon('spin'), h('span', { text: '불러오는 중' })];
  if (!d) return h('span', { text: '받은 목록 없음' });
  if (S.rp && S.rp.kind === 'same') return h('span', { text: `다시 보기 중 · ${S.rp.hm}까지 들어온 공시만` });
  if (S.rp) return h('span', { text: '다시 보기 중 · 지금 공시예요' });
  if (staleNow()) {
    atEl.classList.add('stale');
    const since = S.tries > 0 ? S.okAt : isoMs(d.asOf), m = Math.max(5, Math.round((Date.now() - since) / 60000));
    return [icon('warn'), h('span', { text: `${asOfText(d.asOf)} 기준 · ${m}분째 못 받았어요` }), retryKey(true)];
  }
  return h('span', { text: `${asOfText(d.asOf)} 기준` });
}
const tabSpec = {
  key: 'disc', pane, list,
  label: () => (!S.data || isToday() ? '오늘 공시' : `${dayLong(S.data.date)} 공시`),
  count: () => (S.data ? String(listFor('mark', true).length) : ''),
  at: atKids,
  render(L) { S.L = L; renderPanel({ force: true }); },
};
function addTab() {
  if (S.tabbed || !window.KHNews || typeof window.KHNews.addTab !== 'function') return;
  S.tabbed = true;
  window.KHNews.addTab(tabSpec);
}
function removeTab() {
  if (!S.tabbed) return;
  S.tabbed = false; setHover(null);
  if (window.KHNews && typeof window.KHNews.removeTab === 'function') window.KHNews.removeTab('disc');
}
const newsUpdate = () => { if (S.tabbed && window.KHNews && typeof window.KHNews.update === 'function') window.KHNews.update(); };
const newsRelayout = () => { if (S.tabbed && window.KHNews && typeof window.KHNews.relayout === 'function') window.KHNews.relayout(); };

ktabs.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b || b.getAttribute('aria-disabled') === 'true' || b.dataset.k === S.kt) return;
  S.kt = b.dataset.k; renderPanel({ force: true });
});
onlyBtn.addEventListener('click', () => {
  if (onlyBtn.getAttribute('aria-disabled') === 'true') return;
  S.only = !S.only; renderPanel({ force: true });
});
more.addEventListener('click', () => {
  S.open = !S.open;
  if (typeof UI.state === 'function') UI.state(more, S.open ? 'less' : 'idle');
  more.setAttribute('aria-expanded', String(S.open));
  renderPanel({ force: true, grow: S.open });
  if (!S.open && narrowMQ.matches) {                   // 휴대폰: 접으면 카드 머리로 (§3-14와 같아요)
    const card = document.getElementById('news'), top = (card || pane).getBoundingClientRect().top;
    const stuck = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--stuck-h')) || 0;
    if (top < stuck) scrollBy({ top: top - stuck - 8, behavior: (typeof KH.motion === 'function' ? KH.motion() : '') === 'reduced' ? 'auto' : 'smooth' });
  }
  more.focus({ preventScroll: true });
});
list.addEventListener('click', e => {
  const c = e.target.closest('.dc-chip, .dc-chipx');
  if (!c) return;
  e.preventDefault();
  if (c.dataset.x) openAll(c.dataset.c, c);                   // not on the map: no quote, so the stock page (its 공시 list)
  else if (typeof KH.quick === 'function') KH.quick(c.dataset.c, c);
  else openAll(c.dataset.c, c);
});
// a row lights its stock on the map (mouse and keyboard; not on phones)
function setHover(li) {
  const code = li && li.dataset.c && KH.stock(li.dataset.c) ? li.dataset.c : '';
  if (code === S.hov) return;
  S.hov = code;
  if (typeof KH.hover === 'function') KH.hover(code ? [code] : null);
}
list.addEventListener('pointerover', e => { if (narrowMQ.matches || e.pointerType === 'touch') return; setHover(e.target.closest('.dc-row')); });
list.addEventListener('pointerleave', () => setHover(null));
list.addEventListener('focusin', e => { if (!narrowMQ.matches) setHover(e.target.closest('.dc-row')); });
list.addEventListener('focusout', e => { if (!e.relatedTarget || !list.contains(e.relatedTarget)) setHover(null); });
// reading: a list that arrived meanwhile is drawn once the pointer and the focus have left the pane
const flush = () => { if (S.pending && !reading()) renderPanel(); };
pane.addEventListener('pointerenter', () => { S.ptr = true; });
pane.addEventListener('pointerleave', () => { S.ptr = false; flush(); });
pane.addEventListener('focusout', () => setTimeout(flush, 0));

/* ───────── derive: the rows of the moment (a replay of today: those seen by its time) → corners, chip, legend, lists ───────── */
function replayState() {
  const rp = typeof KH.replay === 'function' ? KH.replay() : null;
  if (!rp) return null;
  const t = String(rp.t || '');
  const date = rp.date || today();
  if (S.data && date === S.data.date && /^\d{3,4}$/.test(t)) { const p = t.padStart(4, '0'); return { kind: 'same', hm: p.slice(0, 2) + ':' + p.slice(2) }; }
  return { kind: 'other' };
}
function derive() {
  const d = S.data;
  S.rp = replayState();
  S.rpKey = S.rp ? S.rp.kind + (S.rp.hm || '') : '';
  let rows = d ? d.rows : [];
  if (S.rp && S.rp.kind === 'same') rows = rows.filter(x => x.s && x.s <= S.rp.hm);
  S.view = rows.map(x => Object.assign({}, x, { nt: x.n, n: 1 }));   // n = the merge count from here on; nt = the server's tag
  for (const x of S.view) x.isNew = isNew(x);
  const by = new Map();
  for (const x of S.view) { let a = by.get(x.c); if (!a) by.set(x.c, a = []); a.push(x); }   // newest first, as the server sorts
  S.byCode = by;
  const marks = new Map(), show = S.on && !!d && !(S.rp && S.rp.kind === 'other');
  let sig = '';
  if (show) for (const [c, a] of by) {
    const mk = a.filter(x => S.kinds.has(x.k));
    if (!mk.length) continue;
    const nw = mk.some(x => x.isNew), word = dayWord();
    marks.set(c, { size: nw ? 'new' : 'n', label: `, ${word} 공시 ${a.length}건${nw ? ', 새 공시 있음' : ''}`, title: `${word} 공시 ${a.length}건`, fresh: S.fresh.has(c) });
    sig += c + (nw ? '+' : '') + a.length + ';';
  }
  S.marks = marks;
  if ((sig !== S.markSig || S.fresh.size) && typeof KH.marks === 'object' && KH.marks) { S.markSig = sig; KH.marks.set('disc', marks.size ? marks : null); }
  S.fresh = new Set();
  if (!show && S.chipOn) setChip(false);
  refreshAll();
}
function refreshAll() {
  renderChip(); renderLegend(); renderPanel(); newsUpdate(); renderFoot(); settingCounts();
  if (typeof KH.cardExtra === 'object' && KH.cardExtra) KH.cardExtra.refresh();
}
function settingCounts() {
  if (typeof KH.settingState !== 'function') return;
  const counts = {};
  for (const k of KINDS) counts[k] = 0;
  const per = new Map();
  for (const x of S.view) if (S.mapSet.has(x.c)) { let s = per.get(x.k); if (!s) per.set(x.k, s = new Set()); s.add(x.c); }
  for (const [k, s] of per) counts[k] = s.size;
  KH.settingState('discKinds', { counts: S.data ? counts : {}, disabled: !S.on });
}
function renderFoot() {
  const p = document.getElementById('foot-disc');
  if (!p) return;
  const on = S.on && !S.gone && !worldTab();
  p.textContent = on ? '공시: 금융감독원 DART (제목 · 링크만)' : '';
  p.hidden = !on;
}
function syncMap() {
  const codes = typeof KH.mapCodes === 'function' ? KH.mapCodes() : [];
  const key = codes.length + '|' + codes.slice(0, 3).join() + '|' + codes.slice(-3).join();
  if (key === S.mapKey) return false;
  S.mapKey = key; S.mapSet = new Set(codes);
  return true;
}

/* ───────── data ───────── */
const D_RE = /^\d{4}-\d{2}-\d{2}$/, S_RE = /^\d{2}:\d{2}$/, R_RE = /^\d{14}$/, C_RE = /^[0-9A-Z]{6}$/;
function accept(j) {
  if (!j || typeof j !== 'object' || !Array.isArray(j.rows) || !D_RE.test(j.date || '')) return null;
  const rows = [];
  for (const x of j.rows) {
    if (!x || !C_RE.test(String(x.c)) || typeof x.t !== 'string' || !x.t.trim() || !R_RE.test(String(x.r))) continue;
    rows.push({ c: String(x.c), t: x.t.trim(), k: KINDS.includes(x.k) ? x.k : '기타', n: typeof x.n === 'string' && x.n ? x.n : null,
      r: String(x.r), s: S_RE.test(x.s || '') ? x.s : null, f: typeof x.f === 'string' && x.f ? x.f : null });
  }
  rows.sort((a, b) => (a.r < b.r ? 1 : a.r > b.r ? -1 : 0));
  return { date: j.date, asOf: typeof j.asOf === 'string' ? j.asOf : null, since: S_RE.test(j.since || '') ? j.since : null, stale: !!j.stale, rows };
}
// the Worker's weak ETag (AGENTS §3-29): we send the last one back, a 304 means "nothing new" (no body; the check time comes in x-as-of)
async function getJSON() {
  const ac = new AbortController(), timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch('api/disclosures/today', { cache: 'no-store', signal: ac.signal, headers: S.etag && S.data ? { 'If-None-Match': S.etag } : {} });
    const xa = res.headers.get('x-as-of'), asOf = xa && /^\d{4}-\d{2}-\d{2}T/.test(xa) ? xa : null;
    if (res.status === 304 && S.data) return { same: true, asOf };
    if (!res.ok) { const e = new Error('HTTP ' + res.status); e.status = res.status; throw e; }
    const j = await res.json();
    if (j && asOf) j.asOf = asOf;
    if (j) j.__etag = res.headers.get('etag') || '';
    return j;
  } finally { clearTimeout(timer); }
}
function setData(d) {
  const prev = S.seen;
  let max = '';
  for (const x of d.rows) if (x.r > max) max = x.r;
  if (prev && (!S.data || S.data.date === d.date)) for (const x of d.rows) if (x.r > prev && S.kinds.has(x.k)) S.fresh.add(x.c);
  S.seen = max || prev;
  S.data = d;
  derive();
}
function load(o = {}) {
  if (S.busy) return S.busy;
  clearTimeout(S.timer); S.timer = 0;
  S.lastTry = Date.now();
  S.busy = (async () => {
    let d = null, status = 0, same = null;
    try { const j = await getJSON(); if (j && j.same) same = j; else { d = accept(j); if (d) S.etag = j.__etag || ''; } } catch (e) { status = (e && e.status) || -1; }
    S.loading = false; S.busy = null;
    // 404 = a Worker without the route (the page went out first): no tab, no chip, no corners — until a reload
    if (status === 404 && !S.data) { gone(); return false; }
    if (same) {                                            // 304: the same list — only its time moves on (and 새 may have run out)
      S.tries = 0; S.okAt = Date.now(); S.err = false;
      if (same.asOf) S.data.asOf = same.asOf;
      derive(); schedule();
      return true;
    }
    if (d) { S.tries = 0; S.okAt = Date.now(); S.err = false; setData(d); }
    else { S.tries++; S.err = !S.data; if (!o.silent) refreshAll(); else { renderChip(); renderLegend(); } }
    schedule();
    return !!d;
  })();
  return S.busy;
}
const polling = () => S.on && !S.gone && !document.hidden && !worldTab();
// every 60 s on weekdays 07:00–19:00 KST (the server checks DART every minute then), else 5 min; failures 1 → 2 → 4 → 5 min
function interval() { const k = kstOf(nowMs()); return k.wd >= 1 && k.wd <= 5 && k.min >= 420 && k.min < 1140 ? 60e3 : 300e3; }
function schedule() {
  clearTimeout(S.timer); S.timer = 0;
  if (!polling() || S.busy) return;
  const wait = S.tries ? Math.min(MAX_WAIT, 60e3 * 2 ** (S.tries - 1)) : interval();
  const due = S.lastTry ? S.lastTry + wait - Date.now() : 0;
  if (due <= 0) { load(); return; }
  S.timer = setTimeout(() => load(), due);
}
function gone() {
  S.gone = true; S.data = null;
  clearTimeout(S.timer); S.timer = 0;
  if (S.chipOn) setChip(false);
  if (typeof KH.marks === 'object' && KH.marks) KH.marks.set('disc', null);
  S.markSig = '';
  removeTab();
  refreshAll();
}

/* ───────── settings: 공시 보기 · 지도에 표시할 종류 (표시 설정 › 화면) ───────── */
function onToggle() {
  if (!S.ready) return;
  if (S.on) {
    if (!S.gone) addTab();
    S.loading = !S.data;
    derive();
    schedule();
  } else {
    clearTimeout(S.timer); S.timer = 0;
    if (S.chipOn) setChip(false);
    if (typeof KH.marks === 'object' && KH.marks) KH.marks.set('disc', null);
    S.markSig = '';
    removeTab();
    refreshAll();
  }
}
if (typeof KH.addSetting === 'function') {
  KH.addSetting({ key: 'disc', label: '공시 보기', default: true,
    hint: 'DART 전자공시를 1분마다 확인해서 지도 타일 귀퉁이 · 공시 칩 · 목록으로 보여 줘요. 끄면 모두 사라지고 받지도 않아요.',
    onChange: v => { S.on = !!v; onToggle(); } });
  KH.addSetting({ key: 'discKinds', label: '지도에 표시할 종류', multi: true, min: 1, default: ['실적', '주요'],
    options: KINDS.map(k => ({ v: k, label: k })),
    hint: '정기(분기보고서 등)와 지분(임원 소유 보고 등) 공시는 하루 수백 건이라 기본으로 꺼 뒀어요. 목록과 툴팁에는 언제나 모든 종류가 나와요.',
    onChange: v => { S.kinds = new Set(Array.isArray(v) ? v : ['실적', '주요']); if (S.ready) derive(); } });
}

/* ───────── wiring ───────── */
if (typeof KH.legendItem === 'function') KH.legendItem('disc', legendEls);
if (typeof KH.cardExtra === 'object' && KH.cardExtra) KH.cardExtra.add('disc', block);
document.addEventListener('kh:render', () => {
  const moved = syncMap(), rp = replayState(), rk = rp ? rp.kind + (rp.hm || '') : '';
  if (rk !== S.rpKey) { derive(); schedule(); return; }
  if (moved) { renderChip(); renderLegend(); renderPanel(); newsUpdate(); settingCounts(); }
  else renderChip();
  renderFoot();
  schedule();
});
document.addEventListener('kh:data', () => {
  if (syncMap()) { renderChip(); renderLegend(); renderPanel(); newsUpdate(); settingCounts(); return; }
  // the chips' % follow the map
  for (const b of list.querySelectorAll('.dc-chip[data-c]')) {
    const q = quoteOf(b.dataset.c), v = b.querySelector('b');
    if (!q || !v) continue;
    const t = pct(q.r);
    if (v.textContent !== t) { v.textContent = t; v.className = cls(q.r); b.setAttribute('aria-label', `${q.n} ${t} · 빠른 보기`); }
  }
});
document.addEventListener('kh:refresh', () => { if (polling()) load(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(S.timer); S.timer = 0; } else schedule(); });
narrowMQ.addEventListener('change', () => renderLegend());
// 새 lasts 30 minutes: the corners and dots follow the clock between answers too (once a minute, while visible)
setInterval(() => { if (S.data && S.on && !document.hidden) { const before = S.markSig; derive(); if (before === S.markSig) renderChip(); } }, 60e3);

/* ───────── API ───────── */
const info = r => { r = String(r || ''); const x = S.data && S.data.rows.find(y => y.r === r); return x ? { s: x.s, isNew: isNew(x), date: S.data.date } : null; };
window.KHDisc = { refresh: () => load(), rows: code => (S.byCode.get(String(code)) || []).map(x => ({ c: x.c, t: x.t, k: x.k, n: x.nt, r: x.r, s: x.s, f: x.f, isNew: x.isNew })), info };
KH.disclosures = code => {
  if (code != null) return window.KHDisc.rows(code);
  return S.data ? { date: S.data.date, asOf: S.data.asOf, since: S.data.since, stale: S.data.stale, rows: S.data.rows.slice(), state: staleNow() ? 'stale' : 'ok' }
    : { state: S.gone ? 'gone' : S.loading ? 'loading' : 'error' };
};

S.ready = true;
syncMap();
if (S.on) addTab();
refreshAll();
schedule();
})();
