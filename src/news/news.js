/* 시장 뉴스 패널 (docs/standards/news.md · AGENTS §3-27) — C안 (사용자 2026-11-13 23:14 "너 추천대로 c안으로 하는게 낫겠다").
   window.KHNews = { show(), hide(), refresh() → Promise<boolean> }
   Mount: the template's <section class="card news" id="news" hidden>, the last cell of main.layout. PC (> 980): the map column's second
   grid row, stretched to the side column's end — the list fills it (whole rows, min 5; two columns from a 1200 px card). Tablet: 8 rows.
   Phone (≤ 760): the last card, 5 rows + 더보기. 더보기 → up to 30 per tab.
   Rows: time · outlet (text badge) · headline (one link, new tab) · stock chips (name + today's % = the map's value) for names found in
   the headline (src/news/match.js); hovering / focusing a row lights those tiles on the map (KH.hover), a chip opens the quick view
   (KH.quick). Only headline · time · outlet · link — never a body, summary, image or logo.
   Data (live): GET api/news (Worker, §2-2) while the card is on screen or within 400 px and the browser tab is visible: every 3 min,
   3 → 6 → 12 → 15 min after failures, at once on kh:refresh; "오래됨" 15 min after the last answer. A list that arrives while the
   pointer / focus is in the card waits until it leaves (rows never move under a finger). Tabs = the outlets that have items (Q3).
   Snapshot (dist/): a note + LIVE_URL link, never baked articles.
   Feed tabs (disclosure.md §6, C안): another module may add a tab to this card — KHNews.addTab({key, label, count?, pane, list, at?,
   render(L), onShow?, onHide?}) → the card head becomes a title tablist (시장 뉴스 · 오늘 공시, ←/→, remembered in khm.feedTab), the
   news controls move to a second row like the other tab's, and the card keeps one height: the PC fill (whole rows, min 5, two columns
   from 1200 px) is measured on the tab shown and handed to it as L = {measure, base, two, phone}. Only the tab shown polls its data. */
(() => {
'use strict';
const KH = window.KH, M = window.KHNewsMatch;
const root = document.getElementById('news');
if (!KH || typeof KH.h !== 'function' || !root) return;
const h = KH.h, UI = KH.ui || {};
const LIVE = KH.MODE === 'live';
const SRC = { einfomax: '연합인포맥스', hankyung: '한국경제', mk: '매일경제' };
const SRC_ORDER = ['einfomax', 'hankyung', 'mk'];
const MIN_ROWS = 5, MAX_ROWS = 30, TAB_ROWS = 8, PHONE_ROWS = 5, TWO_COL_W = 1200;
const POLL_MS = 180e3, MAX_WAIT_MS = 15 * 60e3, STALE_MS = 15 * 60e3, TIMEOUT_MS = 12e3;
const narrowMQ = matchMedia('(max-width: 760px)'), deskMQ = matchMedia('(min-width: 981px)');
const MINUS = '−';
const pct = v => (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v).toFixed(2) + '%';
const cls = v => (v > 0 ? 'up' : v < 0 ? 'dn' : 'flat');
const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
const pad = n => String(n).padStart(2, '0');
const kstDay = ms => { const k = new Date(ms + 9 * 3600e3); return `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}`; };
// 오늘(KST)이면 HH:MM, 아니면 M/D (앞 0 없음)
const timeText = t => (t.slice(0, 10) === kstDay(nowMs()) ? t.slice(11, 16) : `${+t.slice(5, 7)}/${+t.slice(8, 10)}`);
// native append / replaceChildren print "null" for a null child — every list goes through this filter
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
const icon = name => (typeof UI.icon === 'function' ? UI.icon(name) : null);
const motion = () => (typeof KH.motion === 'function' ? KH.motion() : document.documentElement.dataset.motion || 'standard');

root.setAttribute('aria-labelledby', 'news-h');

/* ───────── feed tabs: 시장 뉴스 (this module) + tabs other modules add (오늘 공시) ───────── */
const FT = { list: [{ key: 'news', label: '시장 뉴스' }], cur: 'news' };
const ftKey = (() => { try { return JSON.parse(localStorage.getItem('khm.feedTab')); } catch (e) { return null; } })();
const curExt = () => (FT.cur === 'news' ? null : FT.list.find(t => t.key === FT.cur) || null);
const labelOf = t => String(typeof t.label === 'function' ? t.label() : t.label);
const h2 = h('h2', { id: 'news-h', text: '시장 뉴스' });
const ttl = h('div', { class: 'nw-tt', role: 'tablist', id: 'news-h', 'aria-label': '지도 아래 패널' });
const at = h('span', { class: 'nw-at' });
const hd = h('div', { class: 'nw-hd' });
const newsPane = h('div', { class: 'nw-pane', id: 'news-p-news' });
const newsSub = h('div', { class: 'nw-sub' });
function renderTT() {
  if (FT.list.length < 2) return;
  if (ttl.children.length !== FT.list.length || [...ttl.children].some((b, i) => b.dataset.k !== FT.list[i].key))
    put(ttl, FT.list.map(t => h('button', { type: 'button', role: 'tab', id: 'news-t-' + t.key, 'data-k': t.key, 'aria-controls': t.key === 'news' ? newsPane.id : t.pane.id },
      h('span', { class: 'nw-tl' }), h('span', { class: 'nw-tn' }))));
  for (const b of ttl.children) {
    const t = FT.list.find(x => x.key === b.dataset.k), on = t.key === FT.cur;
    b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1;
    const lab = labelOf(t), n = typeof t.count === 'function' ? String(t.count() || '') : '';
    if (b.firstChild.textContent !== lab) b.firstChild.textContent = lab;
    if (b.lastChild.textContent !== n) b.lastChild.textContent = n;
  }
}
// the card's parts in place: one tab → the news card as it always was (h2 · outlet tabs · chip · time in one row); two or more → the
// title tablist and the time on top, each tab's own row (outlet tabs · chip / 공시 종류 · 지도 종목만) under it
let arrangeNews = () => {};
function arrange() {
  const multi = FT.list.length > 1, hasNews = !!FT.list.length && FT.list[0].key === 'news';
  root.classList.toggle('multi', multi || !hasNews);          // a lone other tab (no 시장 뉴스 on this Worker) keeps its own row too
  root.setAttribute('aria-labelledby', 'news-h');
  if (multi) { put(hd, ttl, at); renderTT(); }
  else { h2.textContent = FT.list.length ? labelOf(FT.list[0]) : '시장 뉴스'; put(hd, h2, at); }
  if (hasNews) arrangeNews(multi);
  for (const t of FT.list) {
    const on = t.key === FT.cur, pane = t.key === 'news' ? newsPane : t.pane;
    pane.hidden = multi && !on;
    if (multi) { pane.setAttribute('role', 'tabpanel'); pane.setAttribute('aria-labelledby', 'news-t-' + t.key); }
    else { pane.removeAttribute('role'); pane.removeAttribute('aria-labelledby'); }
  }
  put(root, hd, FT.list.map(t => (t.key === 'news' ? newsPane : t.pane)));
}
let onSelect = () => {};
function select(key, user) {
  const t = FT.list.find(x => x.key === key);
  if (!t || key === FT.cur) return;
  const was = curExt();
  FT.cur = key;
  if (user) { try { localStorage.setItem('khm.feedTab', JSON.stringify(key)); } catch (e) { /* private mode */ } }
  root.dataset.feed = key;
  if (was && typeof was.onHide === 'function') was.onHide();
  arrange();
  onSelect(t);
  if (t.key !== 'news' && typeof t.onShow === 'function') t.onShow();
}
ttl.addEventListener('click', e => { const b = e.target.closest('button[role="tab"]'); if (b) select(b.dataset.k, true); });
ttl.addEventListener('keydown', e => {
  const keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'first', End: 'last' };
  if (!(e.key in keys)) return;
  e.preventDefault();
  const i = FT.list.findIndex(t => t.key === FT.cur), d = keys[e.key];
  const j = d === 'first' ? 0 : d === 'last' ? FT.list.length - 1 : (i + d + FT.list.length) % FT.list.length;
  select(FT.list[j].key, true);
  const b = ttl.querySelector(`[data-k="${FT.list[j].key}"]`); if (b) b.focus();
});
function addTab(spec) {
  if (!spec || !spec.key || spec.key === 'news' || !spec.pane || FT.list.some(t => t.key === spec.key)) return false;
  if (!spec.pane.id) spec.pane.id = 'news-p-' + spec.key;
  spec.pane.classList.add('nw-pane');
  FT.list.push(spec);
  if (ftKey === spec.key) { FT.cur = spec.key; root.dataset.feed = spec.key; }
  arrange();
  onSelect(FT.list.find(t => t.key === FT.cur));
  if (FT.cur === spec.key && typeof spec.onShow === 'function') spec.onShow();
  return true;
}
function removeTab(key) {
  const i = FT.list.findIndex(t => t.key === key);
  if (i < 0 || key === 'news') return;
  const [t] = FT.list.splice(i, 1);
  t.pane.remove();
  if (FT.cur === key && typeof t.onHide === 'function') t.onHide();
  if (!FT.list.length) { root.hidden = true; return; }          // nothing left (시장 뉴스 was gone too)
  if (FT.cur === key) { FT.cur = FT.list[0].key; root.dataset.feed = FT.cur; }
  arrange();
  onSelect(FT.list.find(x => x.key === FT.cur));
}
root.dataset.feed = 'news';

/* ───────── snapshot: a note in the card's place (no articles in the build — 시점 · 저작권) ───────── */
if (!LIVE) {
  root.classList.add('is-snap');
  put(newsPane, h('div', { class: 'nw-list is-msg' }, h('div', { class: 'nw-msg' },
    h('b', { text: '뉴스는 실시간 버전에서 볼 수 있어요' }),
    h('small', { text: '언론사 RSS의 시장 뉴스 제목을 3분마다 새로 받아 와요. 이 미리보기는 네트워크가 막혀 있어요.' }),
    h('a', { href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '실시간 버전 열기' }))));
  onSelect = () => { put(at); };
  arrange();
  root.hidden = false;
  window.KHNews = { show() { root.hidden = false; }, hide() { root.hidden = true; }, refresh: () => Promise.resolve(false),
    addTab, removeTab, select: k => select(k, false), tab: () => FT.cur, update() { renderTT(); }, relayout() {} };
  return;
}

/* ───────── state ───────── */
const S = {
  data: null, next: null,   // the list drawn · one that waits while the reader is in the card
  okAt: 0, lastTry: 0, tries: 0, loading: true, busy: null, timer: 0,
  tab: 'all', only: false, open: false,
  n: MIN_ROWS, two: false, measure: false, shown: 0,
  visible: false, near: !('IntersectionObserver' in window), ptr: false, hov: '',
};

/* ───────── headline names → map stocks (match.js), rebuilt only when the names change ───────── */
let IDX = null, IDX_KEY = '';
const MK = new Map();                                    // url → {text, marks}
function ensureIdx() {
  if (!M) return false;
  const rows = (KH.stocks() || []).filter(r => r && r.c && r.n && /0$/.test(r.c));   // common shares (§3-1: preferred shares are off the map)
  let key = String(rows.length);
  for (const r of rows) key += '|' + r.c + r.n;
  if (IDX && key === IDX_KEY) return false;
  IDX_KEY = key; IDX = M.build(rows.map(r => ({ c: r.c, n: r.n }))); MK.clear();
  return true;
}
function matchOf(it) {
  let m = MK.get(it.url);
  if (!m) { m = IDX ? M.match(it.title, IDX) : { text: it.title, marks: [] }; MK.set(it.url, m); }
  return m;
}
// a chip's numbers: the quote in the chosen price basis (= what the map draws), the name from the row
function quoteOf(code) {
  const st = KH.stock(code);
  if (!st) return null;
  const q = typeof KH.quote === 'function' ? KH.quote(code) : null;
  const r = Number(q && q.r != null ? q.r : st.r);
  return { n: st.n, r: Number.isFinite(r) ? r : 0 };
}
const codesOf = it => [...new Set(matchOf(it).marks.flatMap(x => x.codes))].filter(c => quoteOf(c));

/* ───────── DOM ───────── */
const tabs = h('div', { class: 'movers-tabs nw-tabs', role: 'group', 'aria-label': '언론사' });
const onlyBtn = h('button', { type: 'button', class: 'nw-only', 'aria-pressed': 'false' },
  h('i', { class: 'nw-ck', 'aria-hidden': 'true' }), '지도 종목 기사만', h('span', { class: 'nw-n' }));
const note = h('div', { class: 'nw-note', hidden: true });
const list = h('ol', { class: 'nw-list', 'aria-labelledby': 'news-h' });
const more = typeof UI.akey === 'function' ? UI.akey('nw-kbtn nw-more', { idle: '더보기 (30개)', less: '접기' }, 'idle')
  : h('button', { type: 'button', class: 'nw-kbtn nw-more', text: '더보기' });
more.setAttribute('aria-expanded', 'false');
const credit = h('small');
const newsFt = h('div', { class: 'nw-ft' }, more, credit);
// one tab: the outlet tabs and the chip sit in the head row (as before); several: in this tab's own row under the title tabs
arrangeNews = multi => {
  if (multi) { put(newsSub, tabs, onlyBtn); put(newsPane, newsSub, note, list, newsFt); }
  else { put(newsPane, note, list, newsFt); hd.insertBefore(tabs, at); hd.insertBefore(onlyBtn, at); }
  list.setAttribute('aria-labelledby', multi ? 'news-t-news' : 'news-h');
};
arrange();
root.dataset.tab = 'all';

/* ───────── helpers ───────── */
const outletsWithItems = () => (S.data ? SRC_ORDER.filter(k => S.data.items.some(x => x.src === k)) : []);
function listFor(tab = S.tab, only = S.only) {
  let a = S.data ? S.data.items : [];
  if (tab !== 'all') a = a.filter(x => x.src === tab);
  if (only) a = a.filter(x => codesOf(x).length);
  return a;
}
const staleNow = () => !!S.data && S.tries > 0 && Date.now() - S.okAt > STALE_MS;   // failing, and the last answer is 15 min old (elapsed: device clock)
function retryKey(sm) {
  if (typeof UI.retry !== 'function') return null;
  return UI.retry({ cls: 'nw-kbtn' + (sm ? ' sm' : ''), run: () => load({ silent: true }), render: () => render() });
}
const reading = () => S.ptr || root.contains(document.activeElement);

/* ───────── head: "HH:MM 기준" · 불러오는 중 · 받은 목록 없음 · 오래됨 ───────── */
let staleSpan = null;
function staleText() { const m = Math.max(15, Math.round((Date.now() - S.okAt) / 60000)); return `${timeText(S.data.asOf)} 기준 · ${m}분째 못 받았어요`; }
function renderHead() {
  const ext = curExt();
  if (ext) { staleSpan = null; at.classList.remove('stale'); put(at, typeof ext.at === 'function' ? ext.at(at) : null); return; }
  if (S.loading && !S.data) { at.classList.remove('stale'); staleSpan = null; put(at, icon('spin'), h('span', { text: '불러오는 중' })); return; }
  if (!S.data) { at.classList.remove('stale'); staleSpan = null; put(at, h('span', { text: '받은 목록 없음' })); return; }
  if (staleNow()) {
    if (staleSpan && staleSpan.isConnected && at.classList.contains('stale')) { staleSpan.textContent = staleText(); return; }
    at.classList.add('stale');
    staleSpan = h('span', { text: staleText() });
    put(at, icon('warn'), staleSpan, retryKey(true));
    return;
  }
  at.classList.remove('stale'); staleSpan = null;
  put(at, h('span', { text: `${timeText(S.data.asOf)} 기준` }));
}

/* ───────── tabs: 전체 + the outlets that have items (fresh or the last good copy) ───────── */
let tabKeys = '';
function renderTabs(none) {
  const outs = S.data ? outletsWithItems() : SRC_ORDER;
  if (S.tab !== 'all' && !outs.includes(S.tab)) { S.tab = 'all'; root.dataset.tab = 'all'; }
  const keys = ['all', ...outs].join();
  if (keys !== tabKeys) {
    tabKeys = keys;
    put(tabs, ['all', ...outs].map(k => h('button', { type: 'button', 'data-k': k, 'aria-pressed': String(k === S.tab) })));
  }
  for (const b of tabs.children) {
    const k = b.dataset.k, src = S.data && S.data.sources ? S.data.sources[k] : null;
    const kids = [k === 'all' ? '전체' : SRC[k]];
    if (src && src.stale) kids.push(h('span', { class: 'nw-bad', 'aria-hidden': 'true', text: '!' }), h('span', { class: 'sr', text: ' (새 기사를 받지 못했어요)' }));
    put(b, kids);
    b.setAttribute('aria-pressed', String(k === S.tab));
    if (none) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled');
  }
}

/* ───────── rows ───────── */
function titleLink(it, m) {
  const t = m.text;
  const a = h('a', { href: it.url, target: '_blank', rel: 'noopener', 'aria-label': `${t} — ${SRC[it.src]}, 새 탭에서 열려요` });
  let p = 0;
  for (const x of m.marks) { a.append(t.slice(p, x.i), h('mark', { text: t.slice(x.i, x.j) })); p = x.j; }
  a.append(t.slice(p));
  return a;
}
function chip(code) {
  const q = quoteOf(code);
  if (!q) return null;
  return h('button', { type: 'button', class: 'nw-chip', 'data-c': code, 'aria-label': `${q.n} ${pct(q.r)} · 빠른 보기` },
    q.n, h('b', { class: cls(q.r), text: pct(q.r) }));
}
function row(it, k, grow) {
  const m = matchOf(it), codes = codesOf(it), phone = narrowMQ.matches, cap = phone ? 3 : 2;
  const anim = grow && k >= S.shown;
  return h('li', { class: 'nw-row' + (anim ? ' in' : ''), style: anim ? `--d:${Math.min(8, k - S.shown) * 20}ms` : null, 'data-codes': codes.length ? codes.join(',') : null },
    h('time', { datetime: it.t, text: timeText(it.t) }),
    h('span', { class: 'nw-src', text: SRC[it.src] }),
    h('span', { class: 'nw-tt', title: m.text }, titleLink(it, m)),
    h('span', { class: 'nw-stk' }, codes.slice(0, cap).map(chip),
      !phone && codes.length > cap ? h('span', { class: 'nw-moren', 'aria-hidden': 'true', title: codes.slice(cap).map(c => (KH.stock(c) || {}).n).join(', '), text: `+${codes.length - cap}` }) : null));
}
const skel = n => Array.from({ length: n }, (_, k) => h('li', { class: 'nw-row skel', 'aria-hidden': 'true' },
  h('time', {}, h('i', { class: 'nw-sk', style: 'width:32px' })), h('span', {}, h('i', { class: 'nw-sk', style: 'width:52px' })),
  h('span', { class: 'nw-tt', style: `--w:${(k * 37) % 30}%` }, h('i', { class: 'nw-sk' }))));
function msg(title, sub, retry) {
  return h('li', { class: 'nw-msg' }, h('b', { text: title }), sub ? h('small', { text: sub }) : null, retry ? retryKey(false) : null);
}

/* ───────── render ───────── */
function baseRows() { return narrowMQ.matches ? PHONE_ROWS : deskMQ.matches ? S.n : TAB_ROWS; }
// what another tab draws with: the same rows, columns and phone / tablet rules as the news list
const extLayout = measure => ({ measure: !!measure, base: baseRows(), two: deskMQ.matches && S.two && !measure, phone: narrowMQ.matches, rowsMax: MAX_ROWS });
function renderExt(ext, measure) { renderTT(); renderHead(); ext.render(extLayout(measure)); }
function render(o = {}) {
  const d = S.data, phone = narrowMQ.matches, two = deskMQ.matches && S.two && !S.measure;
  const none = !d || !d.items.length;
  root.dataset.tab = S.tab;
  renderHead();
  renderTabs(none);
  // the only-chip: off look when there is nothing to filter (controls §5-12)
  if (none) onlyBtn.setAttribute('aria-disabled', 'true'); else onlyBtn.removeAttribute('aria-disabled');
  onlyBtn.querySelector('.nw-n').textContent = d ? String(listFor(S.tab, true).length) : '';
  // an outlet failed this time and its last good list is shown: one line (전체 탭 · 그 언론사 탭)
  const stale = d ? SRC_ORDER.filter(k => d.sources[k] && d.sources[k].stale && d.items.some(x => x.src === k) && (S.tab === 'all' || S.tab === k)) : [];
  note.hidden = !stale.length;
  if (stale.length) {
    const ats = stale.map(k => d.sources[k].at).filter(Boolean).sort();
    put(note, icon('warn'), h('span', {}, `${stale.map(k => SRC[k]).join(' · ')} 새 기사를 받지 못했어요`,
      ats.length ? h('span', { class: 'nw-wide', text: ` · ${timeText(ats[0])}에 받은 목록이에요` }) : null),
      staleNow() ? null : retryKey(true));      // 오래됨이면 다시 시도는 머리에 하나만
  }
  // the list
  const all = listFor(), base = baseRows();
  const shown = S.measure ? 0 : S.open ? Math.min(MAX_ROWS, all.length) : base;
  const perCol = n => (two ? Math.ceil(n / 2) : n);
  list.classList.toggle('c2', two);
  list.style.setProperty('--nw-r', String(perCol(Math.max(shown, base))));
  list.style.minHeight = phone ? '' : S.measure ? '0px' : `calc(var(--nw-rh) * ${perCol(base)})`;
  let kids;
  if (S.measure) kids = [];
  else if (!d && S.loading) kids = skel(base);
  else if (!d) kids = [msg('뉴스를 불러오지 못했어요', '세 언론사 모두 응답이 없었어요. 잠시 뒤 다시 눌러 주세요.', true)];
  else if (!all.length) kids = [msg(S.only ? '지도 종목이 나오는 기사가 아직 없어요' : '아직 새 기사가 없어요', S.only ? '' : '3분마다 다시 확인해요.', false)];
  else kids = all.slice(0, shown).map((it, k) => row(it, k, o.grow));
  put(list, kids);
  list.classList.toggle('is-msg', kids.length === 1 && kids[0].classList.contains('nw-msg'));
  if (!S.measure) S.shown = d ? Math.min(shown, all.length) : 0;
  // 더보기 (N개) / 접기 — at the first row count the key keeps its place, hidden
  const total = Math.min(MAX_ROWS, all.length);
  const lab = more.querySelector('.kl[data-l="idle"]');
  if (lab) lab.textContent = `더보기 (${total}개)`;
  if (more.dataset.st !== 'less') more.setAttribute('aria-label', `더보기 (${total}개)`);
  more.hidden = !(d && (total > base || S.open));
  // the outlets credited are the ones shown (Q3: a failing outlet without a copy is not named)
  const outs = outletsWithItems().map(k => SRC[k]);
  credit.textContent = (outs.length ? `${outs.join(' · ')} RSS — ` : '') + '제목과 시각만 보여 드려요. 원문은 언론사 사이트에서 새 탭으로 열려요.';
  const fn = document.getElementById('foot-news');   // the template's footer line (re-attached on every footer redraw)
  if (fn) { fn.textContent = outs.length ? `시장 뉴스: ${outs.join(' · ')} RSS (제목 · 링크만)` : ''; fn.hidden = !outs.length; }
  if (S.hov && !list.querySelector('.nw-row[data-codes]:hover')) setHover(null);
}

/* ───────── PC fill: the card is stretched to the side column's end; whole rows that fit, at least 5 ───────── */
function fit() {
  if (root.hidden) return;
  const ext = curExt();
  if (!deskMQ.matches) { S.two = false; if (ext) renderExt(ext); else render(); return; }
  S.two = root.clientWidth >= TWO_COL_W;
  const rh = parseFloat(getComputedStyle(root).getPropertyValue('--nw-rh')) || 32;
  if (ext) {
    renderExt(ext, true);
    const r = Math.max(MIN_ROWS, Math.floor((ext.list.clientHeight + 0.5) / rh));
    S.n = S.two ? r * 2 : r;
    renderExt(ext);
    return;
  }
  S.measure = true; render();
  const r = Math.max(MIN_ROWS, Math.floor((list.clientHeight + 0.5) / rh));
  S.measure = false; S.n = S.two ? r * 2 : r;
  render();
}
const stage = document.querySelector('main.layout > .stage'), side = document.querySelector('main.layout > .side');
let fitKey = '', fitRaf = 0;
function layoutKey() {
  return [FT.cur, deskMQ.matches, narrowMQ.matches, root.clientWidth, stage ? stage.offsetHeight : 0,
    side ? [...side.children].map(c => c.offsetHeight).join(',') : ''].join('|');
}
function refit(force) {
  cancelAnimationFrame(fitRaf);
  fitRaf = requestAnimationFrame(() => {
    if (root.hidden || !root.offsetParent) return;
    const k = layoutKey();
    if (!force && k === fitKey) return;
    fitKey = k; fit(); fitKey = layoutKey();
  });
}
if ('ResizeObserver' in window) {
  const ro = new ResizeObserver(() => refit());
  ro.observe(root);
  if (stage) ro.observe(stage);
  if (side) for (const c of side.children) ro.observe(c);
}
for (const mq of [narrowMQ, deskMQ]) mq.addEventListener('change', () => refit(true));

/* ───────── data ───────── */
async function getJSON(url) {
  const ac = new AbortController(), timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { cache: 'no-store', signal: ac.signal });
    if (!res.ok) { const e = new Error('HTTP ' + res.status); e.status = res.status; throw e; }
    return await res.json();
  } finally { clearTimeout(timer); }
}
const T_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\+09:00$/;
function accept(j) {
  if (!j || !Array.isArray(j.items) || typeof j.asOf !== 'string' || !T_RE.test(j.asOf)) return null;
  const items = j.items.filter(x => x && SRC[x.src] && typeof x.title === 'string' && x.title && typeof x.t === 'string' && T_RE.test(x.t)
    && typeof x.url === 'string' && /^https:\/\//.test(x.url)).map(x => ({ src: x.src, title: x.title, url: x.url, t: x.t }));
  const sources = {};
  for (const k of SRC_ORDER) { const s = j.sources && j.sources[k]; sources[k] = s && typeof s === 'object' ? { ok: !!s.ok, n: +s.n || 0, at: typeof s.at === 'string' ? s.at : null, stale: !!s.stale } : { ok: false, n: 0, at: null, stale: false }; }
  return { asOf: j.asOf, items, sources };
}
function apply(data) { S.data = data; S.next = null; ensureIdx(); render(); }
function load(o = {}) {
  if (S.busy) return S.busy;
  clearTimeout(S.timer); S.timer = 0;
  S.lastTry = Date.now();
  S.busy = (async () => {
    let data = null, missing = false;
    try { data = accept(await getJSON('api/news')); } catch (e) { data = null; missing = e && e.status === 404; }
    S.loading = false; S.busy = null;
    // 404 = a Worker without /api/news (the page went out first): no card at all — the layout is the one without news — until a reload
    if (missing && !S.data) { S.gone = true; goneNews(); return false; }
    if (data) {
      S.tries = 0; S.okAt = Date.now();
      if (o.silent) { S.data = data; S.next = null; ensureIdx(); }   // 다시 시도: its ✓ shows first, then its render() draws
      else if (S.data && reading()) S.next = data;                    // rows never move under the reader
      else apply(data);
    } else {
      S.tries++;
      if (!o.silent) render();
    }
    schedule();
    return !!data;
  })();
  return S.busy;
}
const active = () => S.visible && S.near && !document.hidden && !root.hidden && !S.gone && FT.cur === 'news';
function schedule() {
  clearTimeout(S.timer); S.timer = 0;
  if (!active() || S.busy) return;
  const wait = S.tries ? Math.min(MAX_WAIT_MS, POLL_MS * 2 ** (S.tries - 1)) : POLL_MS;   // 3 → 6 → 12 → 15 분
  const due = S.lastTry ? S.lastTry + wait - Date.now() : 0;
  if (due <= 0) { load(); return; }
  S.timer = setTimeout(() => load(), due);
}

/* ───────── events ───────── */
tabs.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b || b.getAttribute('aria-disabled') === 'true' || b.dataset.k === S.tab) return;
  S.tab = b.dataset.k;
  render();
});
onlyBtn.addEventListener('click', () => {
  if (onlyBtn.getAttribute('aria-disabled') === 'true') return;
  S.only = !S.only;
  onlyBtn.setAttribute('aria-pressed', String(S.only));
  render();
});
more.addEventListener('click', () => {
  S.open = !S.open;
  if (typeof UI.state === 'function') UI.state(more, S.open ? 'less' : 'idle');
  more.setAttribute('aria-expanded', String(S.open));
  render({ grow: S.open });
  if (!S.open && narrowMQ.matches) {                     // 휴대폰: 접으면 카드 머리로 (§3-14와 같아요)
    const top = root.getBoundingClientRect().top, stuck = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--stuck-h')) || 0;
    if (top < stuck) scrollBy({ top: top - stuck - 8, behavior: motion() === 'reduced' ? 'auto' : 'smooth' });
  }
  more.focus({ preventScroll: true });
});
list.addEventListener('click', e => {
  const c = e.target.closest('.nw-chip');
  if (!c) return;
  e.preventDefault();
  if (typeof KH.quick === 'function') KH.quick(c.dataset.c, c);
  else if (window.KHStock) window.KHStock.open(c.dataset.c, { opener: c });
});
// a row with map stocks lights them on the map (mouse and keyboard; not on phones)
function setHover(li) {
  const codes = li && li.dataset.codes ? li.dataset.codes.split(',') : null, key = codes ? codes.join() : '';
  if (key === S.hov) return;
  S.hov = key;
  if (typeof KH.hover === 'function') KH.hover(codes);
}
list.addEventListener('pointerover', e => { if (narrowMQ.matches || e.pointerType === 'touch') return; setHover(e.target.closest('.nw-row')); });
list.addEventListener('pointerleave', () => setHover(null));
list.addEventListener('focusin', e => { if (!narrowMQ.matches) setHover(e.target.closest('.nw-row')); });
list.addEventListener('focusout', e => { if (!e.relatedTarget || !list.contains(e.relatedTarget)) setHover(null); });
// reading: a list that arrived meanwhile is drawn once the pointer and the focus have left the card
const flush = () => { if (S.next && !reading()) apply(S.next); };
root.addEventListener('pointerenter', () => { S.ptr = true; });
root.addEventListener('pointerleave', () => { S.ptr = false; flush(); });
root.addEventListener('focusout', () => setTimeout(flush, 0));
// quotes: the chips' % follow the map; a new name list re-matches the headlines
document.addEventListener('kh:data', () => {
  if (!S.data || root.hidden) return;
  if (ensureIdx()) { if (!reading()) render(); return; }
  for (const b of list.querySelectorAll('.nw-chip[data-c]')) {
    const q = quoteOf(b.dataset.c), v = b.querySelector('b');
    if (!q || !v) continue;
    const t = pct(q.r);
    if (v.textContent !== t) { v.textContent = t; v.className = cls(q.r); b.setAttribute('aria-label', `${q.n} ${t} · 빠른 보기`); }
  }
});
document.addEventListener('kh:refresh', () => { if (!S.gone && !root.hidden && root.offsetParent && !document.hidden && FT.cur === 'news') load(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(S.timer); S.timer = 0; } else schedule(); });
if ('IntersectionObserver' in window) {
  new IntersectionObserver(es => { for (const e of es) S.near = e.isIntersecting; schedule(); }, { rootMargin: '400px 0px' }).observe(root);
}
setInterval(() => { if (S.visible && S.data && !document.hidden && staleNow()) renderHead(); }, 30e3);   // "N분째" counts on

/* ───────── API ───────── */
function show() {
  if (S.gone && FT.list.length < 2) return;
  root.hidden = false; S.visible = true;
  if (typeof UI.seg === 'function') UI.seg(tabs);
  ensureIdx(); render(); renderTT(); refit(true); schedule();
}
function hide() {
  root.hidden = true; S.visible = false;
  clearTimeout(S.timer); S.timer = 0;
  setHover(null);
}
// a Worker without /api/news (404): no 시장 뉴스 — the card stays only when another tab has something to show
function goneNews() {
  const fn = document.getElementById('foot-news'); if (fn) fn.hidden = true;
  if (FT.list.length < 2) { hide(); return; }
  FT.list.shift();
  if (FT.cur === 'news') { FT.cur = FT.list[0].key; root.dataset.feed = FT.cur; }
  newsPane.remove();
  arrange(); onSelect(curExt());
}
onSelect = t => {
  if (!t || t.key === 'news') { render(); refit(true); schedule(); return; }
  clearTimeout(S.timer); S.timer = 0;
  setHover(null);
  renderExt(t); refit(true);
};
window.KHNews = { show, hide, refresh: () => load(),
  addTab, removeTab, select: k => select(k, false), tab: () => FT.cur,
  // a tab's label / count / head line changed (no list redraw)
  update() { renderTT(); if (curExt()) renderHead(); },
  // the tab's content changed size or rule (a state message, the phone): fill again
  relayout: () => refit(true) };
show();
})();
