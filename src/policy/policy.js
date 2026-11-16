/* 정책 자료 (docs/standards/policy-feeds.md · AGENTS §3-27) — 사용자 2026-11-15 16:25 "Kdi만 가져와야겠다" + 관보 API 승인:
   KDI 경제정보센터 경제정책자료 RSS · 행정안전부 관보 목록(공공데이터포털)의 제목 · 날짜 · 기관만, 누르면 원문이 새 탭.
   Where: a third title tab "정책 자료" of the news card (KHNews.addTab, after 시장 뉴스 · 오늘 공시); its own row = source filter chips
   전체 · KDI · 관보 (pill chips: filters only — design.md §7), rows = date · source badge · headline (one link) · agency (· 편집구분),
   the news card's fill (L: rows to the side column's end, two columns from 1200 px, phone 5 + 더보기 30).
   Data (live): GET api/policy while this tab is shown, the card is on screen (400 px) and the page is visible — every 10 min, after
   failures 2 → 4 → 8 → 10 min, at once on kh:refresh; "오래됨" after 30 min of failures. A list that arrives while the pointer / focus
   is in the pane waits until it leaves. A Worker without the route (404): no tab. Snapshot (dist/): the tab says
   "정책 자료는 실시간 버전에서 볼 수 있어요".
   Footer: <p id="foot-policy"> right after the 공시 line (above ©, the disclaimer stays last — AGENTS §3-30), kept there across the
   template's footer redraws by watching #foot (the template is not changed).
   Design (design.md, approved): --fs-* / --space-* / --r-* / --h-* tokens only, no red / green (no price data here), amber only for the
   chosen chip and focus; the failure mark is --fail-dot. 더보기 · 접기 = the card's fold (KHNews.fold, as 시장 뉴스 · 오늘 공시 — no
   40 ms stagger any more, ux/std-wrapup); chip counts that move with a new answer swap in place (KH.ui.swap); ↻ in the card head asks
   this tab again (spec refresh · freshAt). */
(() => {
'use strict';
const KH = window.KH;
if (!KH || typeof KH.h !== 'function') return;
const News = window.KHNews;
if (!News || typeof News.addTab !== 'function') return;
const h = KH.h, UI = KH.ui || {};
const LIVE = KH.MODE === 'live';
const SRC = { kdi: 'KDI', gwanbo: '관보' };
const SRC_LONG = { kdi: 'KDI 경제정보센터', gwanbo: '행정안전부 관보' };
const SRC_ORDER = ['kdi', 'gwanbo'];
const FILTERS = [['all', '전체'], ['kdi', 'KDI'], ['gwanbo', '관보']];
const MAX_ROWS = 30, POLL_MS = 10 * 60e3, MAX_WAIT = 10 * 60e3, STALE_MS = 30 * 60e3, TIMEOUT_MS = 15e3;
const narrowMQ = matchMedia('(max-width: 760px)');
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(k => k != null && k !== false));
const icon = name => (typeof UI.icon === 'function' ? UI.icon(name) : null);
const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
const pad = n => String(n).padStart(2, '0');
const kstDay = ms => { const k = new Date(ms + 9 * 3600e3); return `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}`; };
const md = ymd => `${+ymd.slice(5, 7)}/${+ymd.slice(8, 10)}`;
const dateText = ymd => (ymd === kstDay(nowMs()) ? '오늘' : md(ymd));
function asOfText(iso) {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(iso || '');
  if (!m) return '';
  return m[1] === kstDay(nowMs()) ? m[2] : `${md(m[1])} ${m[2]}`;
}
const motion = () => (typeof KH.motion === 'function' ? KH.motion() : document.documentElement.dataset.motion || 'standard');
// a count that moved with a new answer changes in place, the way it went (design.md §6-4 · P9 — KH.ui.swap); the first draw and a
// filter change write it at once (P4)
const numOf = t => { const m = /[+−-]?\d[\d,]*\.?\d*/.exec(String(t || '').replace(/−/g, '-')); return m ? parseFloat(m[0].replace(/,/g, '')) : NaN; };
function swapNum(el, text, quiet) {
  if (!el) return;
  text = String(text);
  const was = el.textContent;
  if (was === text) return;
  const sw = typeof UI.swap === 'function';
  if (quiet || !was || !text || !sw) { if (sw && el.childElementCount) UI.swap(el, text, text); el.textContent = text; return; }
  const a = numOf(was), b = numOf(text);
  UI.swap(el, text, was, isFinite(a) && isFinite(b) ? Math.sign(b - a) : 0);
}
const card = document.getElementById('news');
const msgLi = (title, sub, extra) => h('li', { class: 'pl-msg' }, h('b', { text: title }), sub ? h('small', { text: sub }) : null, extra || null);

/* ───────── snapshot: the tab says where to see it (nothing baked into the build) ───────── */
if (!LIVE) {
  const pane = h('div', { class: 'pl-pane is-snap' }, h('ol', { class: 'pl-list is-msg' }, msgLi('정책 자료는 실시간 버전에서 볼 수 있어요',
    'KDI 경제정보센터 · 행정안전부 관보의 새 자료 제목을 10분마다 받아 와요. 이 미리보기는 네트워크가 막혀 있어요.',
    h('a', { href: KH.LIVE_URL, target: '_blank', rel: 'noopener', text: '실시간 버전 열기' }))));
  News.addTab({ key: 'policy', label: '정책 자료', pane, list: pane.firstChild, render() {} });
  return;
}

/* ───────── state ───────── */
const S = {
  data: null, okAt: 0, lastTry: 0, tries: 0, loading: true, busy: null, timer: 0, gone: false,
  f: 'all', open: false, pending: false, swapLater: false, ptr: false, near: !('IntersectionObserver' in window), tabbed: false,
  L: { measure: false, base: 5, two: false, phone: narrowMQ.matches, rowsMax: MAX_ROWS },
};

/* ───────── DOM ───────── */
const chips = h('div', { class: 'pl-chips', role: 'group', 'aria-label': '출처' },
  FILTERS.map(([k, t]) => h('button', { type: 'button', class: 'pl-chip', 'data-k': k, 'aria-pressed': String(k === S.f) },
    h('i', { class: 'pl-ck', 'aria-hidden': 'true' }), h('span', { text: t }), h('span', { class: 'pl-n' }))));
const note = h('div', { class: 'pl-note', hidden: true });
const list = h('ol', { class: 'pl-list', 'aria-labelledby': 'news-t-policy' });
const more = typeof UI.akey === 'function' ? UI.akey('pl-kbtn pl-more', { idle: '더보기 (30개)', less: '접기' }, 'idle')
  : h('button', { type: 'button', class: 'pl-kbtn pl-more', text: '더보기' });
more.setAttribute('aria-expanded', 'false');
const credit = h('small', { text: 'KDI 경제정보센터 경제정책자료 RSS · 행정안전부 관보(공공데이터포털) — 제목 · 날짜 · 기관만 보여 드려요. 원문은 새 탭으로 열려요.' });
const pane = h('div', { class: 'pl-pane', id: 'news-p-policy', 'data-f': S.f }, h('div', { class: 'pl-sub' }, chips), note, list, h('div', { class: 'pl-ft' }, more, credit));

/* ───────── helpers ───────── */
const has = k => !!S.data && S.data.items.some(x => x.src === k);
const listFor = (f = S.f) => (!S.data ? [] : f === 'all' ? S.data.items : S.data.items.filter(x => x.src === f));
const staleNow = () => !!S.data && S.tries > 0 && Date.now() - S.okAt > STALE_MS;   // failing, and the last answer is 30 min old
const reading = () => S.ptr || pane.contains(document.activeElement);
function retryKey(sm) {
  if (typeof UI.retry !== 'function') return null;
  return UI.retry({ cls: 'pl-kbtn' + (sm ? ' sm' : ''), run: () => load({ silent: true }), render: () => renderPanel({ force: true }) });
}
const warn = () => { const i = icon('warn'); if (i && i.classList) i.classList.add('pl-warn'); return i; };

/* ───────── rows ───────── */
// rows past the first row count are .nw-x: they come in / leave together with the 더보기 fold (KHNews.fold — policy.css)
function row(x, k, base) {
  const side = [x.org, x.kind].filter(Boolean).join(' · ');
  return h('li', { class: 'pl-row' + (k >= base ? ' nw-x' : ''), 'data-src': x.src },
    h('time', { class: 'pl-tm', datetime: x.t, text: dateText(x.t) }),
    h('span', { class: 'pl-src', text: SRC[x.src] }),
    h('span', { class: 'pl-tt', title: x.title + (side ? ` — ${side}` : '') },
      h('a', { href: x.url, target: '_blank', rel: 'noopener', 'aria-label': `${x.title} — ${SRC_LONG[x.src]}${side ? ', ' + side : ''}, 새 탭에서 열려요` }, x.title)),
    h('span', { class: 'pl-org', text: side }));
}
const skel = n => Array.from({ length: n }, (_, k) => h('li', { class: 'pl-row skel', 'aria-hidden': 'true' },
  h('time', { class: 'pl-tm' }, h('i', { class: 'pl-sk', style: 'width:32px' })), h('span', {}, h('i', { class: 'pl-sk', style: 'width:28px' })),
  h('span', { class: 'pl-tt' }, h('i', { class: 'pl-sk', style: `width:${55 + (k * 37) % 30}%` })), h('span', {})));
function emptyMsg() {
  const src = S.data.sources;
  if (S.f === 'gwanbo' && !src.gwanbo.ok) return msgLi('관보를 불러오지 못했어요', '공공데이터포털이 답하지 않았어요. 잠시 뒤 다시 눌러 주세요.', retryKey(false));
  if (S.f === 'kdi' && !src.kdi.ok) return msgLi('KDI 자료를 불러오지 못했어요', 'KDI 경제정보센터가 답하지 않았어요. 잠시 뒤 다시 눌러 주세요.', retryKey(false));
  if (S.f === 'gwanbo') return msgLi('최근 관보에 경제 부처 고시 · 공고가 없어요', '재정경제부 · 금융위원회 · 한국은행 · 산업통상부 같은 시장과 관련된 기관 것만 골라 보여 드려요.');
  if (S.f === 'kdi') return msgLi('KDI 새 자료가 아직 없어요', '10분마다 다시 확인해요.');
  return msgLi('아직 정책 자료가 없어요', '10분마다 다시 확인해요.');
}

/* ───────── render ───────── */
function renderChips(none, swap) {
  for (const b of chips.children) {
    const k = b.dataset.k, n = !S.data ? '' : String(listFor(k).length);
    b.setAttribute('aria-pressed', String(k === S.f));
    const off = none || (k !== 'all' && !has(k));
    if (off) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled');
    swapNum(b.querySelector('.pl-n'), n, !swap);
  }
}
function renderNote() {
  const d = S.data;
  const bad = d ? SRC_ORDER.filter(k => !d.sources[k].ok && (S.f === 'all' || S.f === k)) : [];
  // a source shown from its last good list · one that has nothing (with 전체 only — its own filter says it in the list)
  const stale = bad.filter(k => d.sources[k].stale && has(k)), lost = bad.filter(k => !has(k) && S.f === 'all');
  note.hidden = !(stale.length || lost.length);
  if (note.hidden) { put(note); return; }
  const ats = stale.map(k => d.sources[k].at).filter(Boolean).sort();
  const parts = [];
  if (stale.length) parts.push(`${stale.map(k => SRC[k]).join(' · ')} 새 자료를 받지 못했어요`);
  if (lost.length) parts.push(`${lost.map(k => SRC[k]).join(' · ')}를 불러오지 못했어요`);
  put(note, warn(), h('span', {}, parts.join(' · '), stale.length && ats.length ? h('span', { class: 'pl-wide', text: ` · ${asOfText(ats[0])}에 받은 목록이에요` }) : null),
    staleNow() ? null : retryKey(true));
}
function renderPanel(o = {}) {
  if (!S.tabbed) return;
  const L = S.L, d = S.data;
  if (!o.force && reading() && list.querySelector('.pl-row:not(.skel)')) { S.pending = true; S.swapLater = S.swapLater || !!o.swap; return; }
  const swap = !!o.swap || S.swapLater;
  S.pending = false; S.swapLater = false;
  pane.dataset.f = S.f;
  const none = !d || !d.items.length;
  renderChips(none, swap);
  renderNote();
  const all = listFor(), base = L.base;
  const shown = L.measure ? 0 : S.open ? Math.min(MAX_ROWS, all.length) : base;
  const perCol = n => (L.two ? Math.ceil(n / 2) : n);
  list.classList.toggle('c2', !!L.two);
  list.style.setProperty('--nw-r', String(perCol(Math.max(shown, base))));
  list.style.minHeight = L.phone ? '' : L.measure ? '0px' : `calc(var(--nw-rh) * ${perCol(base)})`;
  let kids;
  if (L.measure) kids = [];
  else if (!d && S.loading) kids = skel(base);
  else if (!d) kids = [msgLi('정책 자료를 불러오지 못했어요', 'KDI 경제정보센터 · 공공데이터포털 모두 답하지 않았어요. 잠시 뒤 다시 눌러 주세요.', retryKey(false))];
  else if (!all.length) kids = [emptyMsg()];
  else kids = all.slice(0, shown).map((x, k) => row(x, k, base));
  put(list, kids);
  list.classList.toggle('is-msg', kids.length === 1 && kids[0].classList.contains('pl-msg'));
  const total = Math.min(MAX_ROWS, all.length);
  const lab = more.querySelector('.kl[data-l="idle"]');
  if (lab) lab.textContent = `더보기 (${total}개)`;
  if (more.dataset.st !== 'less') more.setAttribute('aria-label', `더보기 (${total}개)`);
  more.hidden = !(d && (total > base || S.open));
  renderFoot();
}
// the card head while this tab is shown: "17:39 기준" · 불러오는 중 · 받은 목록 없음 · 오래됨
function atKids() {
  const d = S.data;
  if (!d && S.loading) return [icon('spin'), h('span', { text: '불러오는 중' })];
  if (!d) return h('span', { text: '받은 목록 없음' });
  if (staleNow()) {
    const m = Math.max(30, Math.round((Date.now() - S.okAt) / 60000));
    return [warn(), h('span', { text: `${asOfText(d.asOf)} 기준 · ${m}분째 못 받았어요` }), retryKey(true)];
  }
  return atTime(asOfText(d.asOf));
}
const atTime = t => (typeof News.atTime === 'function' ? News.atTime(t) : h('span', { text: `${t} 기준` }));

/* ───────── the footer credit line (right after 공시, above ©) ───────── */
const footP = h('p', { id: 'foot-policy', hidden: true });
function footText() {
  if (S.gone || !S.tabbed) return '';
  const outs = S.data ? SRC_ORDER.filter(has) : SRC_ORDER;
  if (!outs.length) return '';
  return `정책 자료: ${outs.map(k => (k === 'kdi' ? 'KDI 경제정보센터 RSS' : '행정안전부 관보')).join(' · ')} (제목 · 링크만)`;
}
function placeFoot() {
  const foot = document.getElementById('foot'), disc = document.getElementById('foot-disc');
  if (!foot) return;
  if (!disc || disc.parentNode !== foot) { if (footP.parentNode) footP.remove(); return; }   // 해외 · 지표 tabs: no feed lines there
  if (disc.nextElementSibling !== footP) disc.after(footP);
}
function renderFoot() {
  const t = footText();
  if (footP.textContent !== t) footP.textContent = t;
  footP.hidden = !t;
  placeFoot();
}
const footEl = document.getElementById('foot');
if (footEl) new MutationObserver(() => placeFoot()).observe(footEl, { childList: true });

/* ───────── the tab ───────── */
const tabSpec = {
  key: 'policy', pane, list, label: '정책 자료',
  at: atKids,
  // ↻ (the news card head's key): at once, drawn even with the pointer in the pane (the reader asked). null = the route is gone (404)
  async refresh() { const ok = await load({ now: true }); if (S.gone) return null; if (S.pending) renderPanel({ force: true }); return ok; },
  freshAt: () => S.okAt,
  // also when this tab became the shown one without a select() (시장 뉴스 gone on an old Worker → the next tab takes over)
  render(L) { S.L = L; renderPanel({ force: true }); if (!S.data && !S.busy && News.tab() === 'policy') schedule(); },
  onShow() { schedule(); },
  onHide() { clearTimeout(S.timer); S.timer = 0; },
};
function addTab() {
  if (S.tabbed || S.gone) return;
  S.tabbed = true;
  News.addTab(tabSpec);
  renderFoot();
}
function gone() {
  S.gone = true; S.data = null;
  clearTimeout(S.timer); S.timer = 0;
  if (S.tabbed && typeof News.removeTab === 'function') News.removeTab('policy');
  S.tabbed = false;
  renderFoot();
}
const newsUpdate = () => { if (S.tabbed && typeof News.update === 'function') News.update(); };
const newsRelayout = () => { if (S.tabbed && typeof News.relayout === 'function') News.relayout(); };

/* ───────── data ───────── */
const D_RE = /^\d{4}-\d{2}-\d{2}$/, T_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\+09:00$/;
const str = (v, max) => (typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : null);
function accept(j) {
  if (!j || typeof j !== 'object' || !Array.isArray(j.items) || typeof j.asOf !== 'string' || !T_RE.test(j.asOf)) return null;
  const items = [];
  for (const x of j.items) {
    if (!x || !SRC[x.src] || !str(x.title, 300) || typeof x.url !== 'string' || !/^https:\/\//.test(x.url) || !D_RE.test(x.t || '')) continue;
    const it = { src: x.src, title: str(x.title, 300), url: x.url, t: x.t };
    const org = str(x.org, 40), kind = str(x.kind, 16);
    if (org) it.org = org;
    if (kind) it.kind = kind;
    items.push(it);
  }
  const sources = {};
  for (const k of SRC_ORDER) {
    const s = j.sources && j.sources[k];
    sources[k] = s && typeof s === 'object' ? { ok: !!s.ok, n: +s.n || 0, at: typeof s.at === 'string' ? s.at : null, stale: !!s.stale } : { ok: false, n: 0, at: null, stale: false };
  }
  return { asOf: j.asOf, items, sources };
}
async function getJSON() {
  const ac = new AbortController(), timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch('api/policy', { cache: 'no-store', signal: ac.signal });
    if (!res.ok) { const e = new Error('HTTP ' + res.status); e.status = res.status; throw e; }
    return await res.json();
  } finally { clearTimeout(timer); }
}
function load(o = {}) {
  if (S.busy) return S.busy;
  clearTimeout(S.timer); S.timer = 0;
  S.lastTry = Date.now();
  S.busy = (async () => {
    let d = null, status = 0;
    try { d = accept(await getJSON()); } catch (e) { status = (e && e.status) || -1; }
    S.loading = false; S.busy = null;
    // 404 = a Worker without /api/policy (the page went out first): no tab until a reload
    if (status === 404 && !S.data) { gone(); return false; }
    if (d) {
      S.tries = 0; S.okAt = Date.now(); S.data = d;     // a filter whose source came back empty stays: its message says why
      if (!o.silent) { renderPanel({ swap: true, force: !!o.now }); newsUpdate(); }
    } else {
      S.tries++;
      if (!o.silent) { renderPanel({ force: !S.data }); newsUpdate(); }
    }
    schedule();
    return !!d;
  })();
  return S.busy;
}
const active = () => S.tabbed && !S.gone && !document.hidden && S.near && card && !card.hidden && News.tab() === 'policy';
function schedule() {
  clearTimeout(S.timer); S.timer = 0;
  if (!active() || S.busy) return;
  const wait = S.tries ? Math.min(MAX_WAIT, 120e3 * 2 ** (S.tries - 1)) : POLL_MS;   // 2 → 4 → 8 → 10 분
  const due = S.lastTry ? S.lastTry + wait - Date.now() : 0;
  if (due <= 0) { load(); return; }
  S.timer = setTimeout(() => load(), due);
}

/* ───────── events ───────── */
chips.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b || b.getAttribute('aria-disabled') === 'true' || b.dataset.k === S.f) return;
  S.f = b.dataset.k;
  renderPanel({ force: true });
});
// 휴대폰: 접으면 카드 머리로 (§3-14와 같아요)
function headBack() {
  if (!narrowMQ.matches || !card) return;
  const top = card.getBoundingClientRect().top, stuck = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--stuck-h')) || 0;
  if (top < stuck) scrollBy({ top: top - stuck - 8, behavior: motion() === 'reduced' ? 'auto' : 'smooth' });
}
// 더보기 · 접기 = the card's fold, the same as 시장 뉴스 · 오늘 공시 (design.md §7 · §12 ①, KHNews.fold): only the list's box grows on
// `open` and what is below moves once; the new rows (.nw-x) come in together a quarter of the way; closing — they leave first, the box
// closes on `close`, then the page comes up once. No stagger (§6-2: a list one opens often).
more.addEventListener('click', () => {
  const want = !S.open;
  if (typeof UI.state === 'function') UI.state(more, want ? 'less' : 'idle');
  more.setAttribute('aria-expanded', String(want));
  const apply = w => { S.open = w; renderPanel({ force: true }); };
  if (typeof News.fold === 'function') News.fold(list, want, apply, { onEnd: want ? null : headBack });
  else { apply(want); if (!want) headBack(); }
  more.focus({ preventScroll: true });
});
const flush = () => { if (S.pending && !reading()) renderPanel(); };
pane.addEventListener('pointerenter', () => { S.ptr = true; });
pane.addEventListener('pointerleave', () => { S.ptr = false; flush(); });
pane.addEventListener('focusout', () => setTimeout(flush, 0));
narrowMQ.addEventListener('change', () => newsRelayout());
document.addEventListener('kh:refresh', () => { if (active()) load(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(S.timer); S.timer = 0; } else schedule(); });
if ('IntersectionObserver' in window && card) {
  new IntersectionObserver(es => { for (const e of es) S.near = e.isIntersecting; schedule(); }, { rootMargin: '400px 0px' }).observe(card);
}
// "N분째" counts on while the head shows it
setInterval(() => { if (S.tabbed && !document.hidden && staleNow() && News.tab() === 'policy') newsUpdate(); }, 30e3);

window.KHPolicy = { refresh: () => load(), state: () => (S.gone ? 'gone' : !S.data ? (S.loading ? 'loading' : 'error') : staleNow() ? 'stale' : 'ok') };
addTab();
})();
