/* 증시 캘린더 — the 일정 tab (AGENTS §3-33, docs/standards/calendar.md §5 A안 · §9-6).
   window.KHCal = { show(kind), hide(), isOn() }. The template calls show('calendar') when the 일정 tab (state.market 'CAL', #cal) opens and
   hands over <div id="calendar">; hide() when another tab opens. Data: GET /api/calendar?from&to (Worker calendar.js), fetched in
   14-day blocks (cached in memory, re-read every 30 min while shown). Phone: week strip + day list; ≥ 1280 px: month grid + 7-day list.
   Stars and badges are neutral (never the up/down colours); amber only for the chosen day, switched-on chips and focus.
   Each day lists 미국 first, then 한국 (user 2026-11-15 19:2x "미국 일정 한국일정 따로 분리하고 미국일정을 먼저"). Company details the
   Worker tags `minor` (금융위 주식권리일정 시한 …) — and 주총 of stocks neither watched nor on the map — stay behind the chip
   "기업 세부 일정" or a day's own "기업 세부 일정 N개 더 보기" (user 19:23 "그래 그게 맞고").
   Chips toggle in place (design.md §6 · §7: fill `fade` in / `close` out, the check fades in and the label slides over the box it
   always reserves, so a chip never changes width and its neighbours never move; press 1px). html[data-motion=reduced] → instant.
   Saved: localStorage khm.cal = {kinds:[…], hi:bool, weekly:bool, detail:bool} (weekly option expiries and company details hidden by default). */
(() => {
  'use strict';
  const KH = window.KH;
  if (!KH || window.KHCal) return;
  const h = KH.h;
  const KST = 9 * 3600e3, DAY = 86400e3;
  const KINDS = { us: '미국 지표', kr: '한국 지표', cb: '금리', mkt: '시장', corp: '기업' };   // 미국 first (user 2026-11-15)
  const RG = [['us', '미국'], ['kr', '한국']];
  const SRC = { bok: '한국은행 통계공표일정', kostat: '국가데이터처 보도계획', fred: 'FRED 발표 일정', manual: '직접 입력 (공지 확인)', rule: '규칙으로 계산', dart: '금융감독원 DART', fsc: '금융위원회 · 한국예탁결제원' };
  const WD = ['일', '월', '화', '수', '목', '금', '토'];
  const BLOCK = 14, EPOCH = Date.UTC(2024, 0, 1);         // a Monday: 14-day blocks line up with weeks
  const REFRESH_MS = 30 * 60e3;
  const nowMs = () => (typeof KH.now === 'function' ? KH.now() : Date.now());
  const today = () => new Date(nowMs() + KST).toISOString().slice(0, 10);
  const dUTC = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
  const addD = (s, n) => new Date(dUTC(s) + n * DAY).toISOString().slice(0, 10);
  const wday = s => new Date(dUTC(s)).getUTCDay();
  const monday = s => addD(s, -((wday(s) + 6) % 7));
  const label = s => `${+s.slice(5, 7)}월 ${+s.slice(8, 10)}일`;
  const reduced = () => document.documentElement.dataset.motion === 'reduced';
  const wide = () => matchMedia('(min-width: 1280px)').matches;
  const cssMs = n => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(n)) || 0;
  const svg = d => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.innerHTML = d; return s; };
  const IC = { l: '<path d="M15 6l-6 6 6 6"/>', r: '<path d="M9 6l6 6-6 6"/>', chev: '<path d="M9 6l6 6-6 6"/>', down: '<path d="M6 9l6 6 6-6"/>', up: '<path d="M6 15l6-6 6 6"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>' };

  // ── state
  const saved = (() => { try { return JSON.parse(localStorage.getItem('khm.cal') || '{}') || {}; } catch (e) { return {}; } })();
  const st = {
    on: false, day: null,
    kinds: new Set(Array.isArray(saved.kinds) && saved.kinds.length ? saved.kinds.filter(k => KINDS[k]) : Object.keys(KINDS)),
    hi: !!saved.hi, weekly: !!saved.weekly, detail: !!saved.detail,
    open: new Set(),         // days whose company details are opened in the list (this visit only)
    all: new Set(),          // days whose hidden rows were asked for from the empty-day line (this visit only)
    blocks: new Map(),       // blockStart → {at, body} | {at, err}
    pending: new Map(), timer: null, error: null, map: new Set(),
  };
  if (!st.kinds.size) Object.keys(KINDS).forEach(k => st.kinds.add(k));
  const save = () => { try { localStorage.setItem('khm.cal', JSON.stringify({ kinds: [...st.kinds], hi: st.hi, weekly: st.weekly, detail: st.detail })); } catch (e) { /* private mode */ } };
  const root = () => document.getElementById('calendar');

  // ── data: 14-day blocks
  const blockOf = d => { const n = Math.floor((dUTC(d) - EPOCH) / DAY / BLOCK); return new Date(EPOCH + n * BLOCK * DAY).toISOString().slice(0, 10); };
  function blocksFor(from, to) { const out = []; for (let b = blockOf(from); b <= to; b = addD(b, BLOCK)) out.push(b); return out; }
  async function loadBlock(b, force) {
    const have = st.blocks.get(b);
    if (!force && have && have.body && nowMs() - have.at < REFRESH_MS) return have;
    if (st.pending.has(b)) return st.pending.get(b);
    const p = (async () => {
      try {
        const r = await fetch(`api/calendar?from=${b}&to=${addD(b, BLOCK - 1)}`, { cache: 'no-store' });
        if (r.status === 404) throw Object.assign(new Error('none'), { code: 404 });
        if (!r.ok) throw new Error('http ' + r.status);
        const body = await r.json();
        const v = { at: nowMs(), body };
        st.blocks.set(b, v);
        return v;
      } catch (e) {
        const v = Object.assign({}, have || {}, { at: (have && have.at) || 0, err: e.code === 404 ? 'none' : 'fail' });
        st.blocks.set(b, v);
        return v;
      } finally { st.pending.delete(b); }
    })();
    st.pending.set(b, p);
    return p;
  }
  async function ensure(from, to, force) {
    const bs = blocksFor(from, to);
    const need = bs.filter(b => force || !st.blocks.has(b) || !st.blocks.get(b).body || nowMs() - st.blocks.get(b).at >= REFRESH_MS);
    if (!need.length) return;
    await Promise.all(need.map(b => loadBlock(b, force)));
    if (st.on) refresh();
  }
  const rangeNow = () => wide() ? (() => { const g = gridStart(); return [g, addD(g, 41 + 7)]; })() : [monday(st.day), addD(st.day, 6)];
  function bodiesIn(from, to) { return blocksFor(from, to).map(b => st.blocks.get(b)).filter(Boolean); }
  function eventsOn(d) {
    const out = [];
    for (const v of bodiesIn(d, d)) if (v.body) for (const e of v.body.events || []) if (e.d === d) out.push(e);
    return out;
  }
  function dayInfo(d) { for (const v of bodiesIn(d, d)) if (v.body && v.body.days && v.body.days[d]) return v.body.days[d]; return null; }

  // ── what a row is: region (미국 · 한국), importance, filters
  const regionOf = e => (e.rg ? e.rg === 'us' : e.k === 'us' || /^cb:fomc/.test(e.id || '')) ? 'us' : 'kr';
  const watched = c => !!(c && KH.watch && typeof KH.watch.has === 'function' && KH.watch.has(c));
  const onMap = c => !!c && (st.map.has(c) || !!(typeof KH.stock === 'function' && KH.stock(c)));
  // a company detail: the Worker's `minor` (or an old answer's nothing), and 주총 of a stock that is neither watched nor on the map
  const isMinor = e => e.k === 'corp' && (e.minor === true || (e.cls === 'agm' && !watched(e.c) && !onMap(e.c)));
  const starOf = e => isMinor(e) ? 1 : Math.min(3, (e.star || 1) + (e.k === 'corp' && watched(e.c) ? 1 : 0));
  const passBase = e => st.kinds.has(e.k) && (!e.weekly || st.weekly);
  const passHi = e => !st.hi || starOf(e) >= 2;
  const inFilter = e => passBase(e) && passHi(e) && (!isMinor(e) || st.detail);     // the strip's marks · the grid · counts
  const sortEv = (a, b) => (a.t || '00:00').localeCompare(b.t || '00:00') || starOf(b) - starOf(a);   // all-day first, as before
  const mainOn = d => eventsOn(d).filter(e => inFilter(e) && !isMinor(e)).sort(sortEv);
  const detailOn = d => eventsOn(d).filter(e => isMinor(e) && passBase(e) && passHi(e)).sort(sortEv);
  // why a row is hidden — the chip that hides it, in the chip row's order (the empty-day line names them, user 2026-11-15 19:51)
  function whyHidden(list) {
    const why = new Set();
    for (const e of list) {
      if (!st.kinds.has(e.k)) why.add('k:' + e.k);
      if (e.weekly && !st.weekly) why.add('weekly');
      if (st.hi && starOf(e) < 2) why.add('hi');
      if (isMinor(e) && !st.detail) why.add('detail');
    }
    return [...Object.keys(KINDS).filter(k => why.has('k:' + k)).map(k => `${KINDS[k]} 꺼짐`),
      why.has('hi') ? '★★ 이상만' : null, why.has('weekly') ? '위클리 만기' : null, why.has('detail') ? '기업 세부 일정' : null].filter(Boolean);
  }
  const loaded = (from, to) => bodiesIn(from, to).some(v => v.body);
  const failed = (from, to) => bodiesIn(from, to).find(v => v.err);

  // ── pieces
  const stars = n => h('span', { class: 'kc-stars sub' + n, role: 'img', 'aria-label': `중요도 ${n}/3` }, [1, 2, 3].map(i => h('i', { class: i <= n ? 'on' : '', text: '★' })));
  const timeNow = () => new Date(nowMs() + KST).toISOString().slice(11, 16);
  function isPast(e) { const t = today(); return e.d < t || (e.d === t && e.t && e.t < timeNow()); }
  function origShort(e) { return e.orig && e.orig.t ? `미국 ${e.orig.t}` : e.orig ? '미국 발표' : null; }
  function evRow(e) {
    const s = starOf(e), past = isPast(e), w = e.k === 'corp' && watched(e.c);
    const tm = e.t ? h('time', { class: 'tm num' }, e.t, origShort(e) ? h('small', { text: origShort(e) }) : null) : h('span', { class: 'tm all', text: '종일' });
    const sub = [KINDS[e.k], e.sub].filter(Boolean).join(' · ');
    const row = h('button', { type: 'button', class: 'kc-ev' + (past ? ' past' : ''), 'data-id': e.id,
      'aria-label': `${e.t || '종일'} ${e.n && !e.grp ? e.n + ' ' : ''}${e.title}${e.grp ? ' ' + e.sub : ''}, 중요도 ${s}, ${KINDS[e.k]}${w ? ', 관심종목' : ''}${e.value ? ', 발표값 ' + e.value.text : ''}${past ? ', 지남' : ''}` },
      tm,
      h('span', { class: 'bd' },
        h('span', { class: 't1' }, stars(s), e.n && !e.grp ? h('span', { class: 'co', text: e.n }) : null, w ? h('span', { class: 'kc-watch', text: '관심' }) : null, h('span', { class: 'ttl', text: e.title })),
        h('span', { class: 't2' }, e.value ? h('span', { class: 'val', text: e.value.text }) : null, h('span', { class: 'sub', text: sub }), e.tentative ? h('span', { class: 'kc-badge tent', text: '예정' }) : null)),
      svg(IC.chev));
    row.querySelector('svg:last-child').setAttribute('class', 'chev');
    row.addEventListener('click', () => openDetail(e, row));
    return row;
  }
  function dayHead(d) {
    const info = dayInfo(d);
    return h('div', { class: 'kc-dh' },
      h('span', {}, label(d), ' ', h('span', { class: 'wd', text: `(${WD[wday(d)]})` })),
      d === today() ? h('span', { class: 'tdy', text: '오늘' }) : null,
      info ? h('span', { class: 'kc-badge' + (info.kind === 'closed' ? ' closed' : '') + (info.tentative ? ' tent' : ''), text: info.note + (info.tentative ? ' · 예정' : '') }) : null);
  }
  // a day's company details: always the end of its 한국 group — a heading when the chip shows them all, else a toggle for this day
  const detId = d => 'kc-det-' + d;
  function detBox(d, list) { return h('div', { class: 'kc-det', id: detId(d), role: 'group', 'aria-label': `${label(d)} 기업 세부 일정` }, list.map(evRow)); }
  function detToggle(d, n, open) {
    return h('button', { type: 'button', class: 'kc-dmore', 'data-more': d, 'aria-expanded': open ? 'true' : 'false', 'aria-controls': detId(d), onclick: ev => toggleDay(d, ev.currentTarget) },
      h('span', { class: 'lab' }, h('span', { class: 'sw-n', text: open ? '기업 세부 일정 접기' : `기업 세부 일정 ${n}개 더 보기` })), svg(open ? IC.up : IC.down));
  }
  // a day: 미국 group → 한국 group (details at its end). st.all: a day whose hidden rows were asked for ("이 날 숨긴 일정 보기") shows
  // everything, whatever the chips say, until "이 날 다시 숨기기" (this visit only)
  function dayBlock(d) {
    const all = st.all.has(d), evs = eventsOn(d), info = dayInfo(d);
    const main = all ? evs.filter(e => !isMinor(e)).sort(sortEv) : mainOn(d), det = all ? evs.filter(isMinor).sort(sortEv) : detailOn(d);
    const sec = h('section', { class: 'kc-day', 'data-day': d, 'aria-label': `${label(d)} ${WD[wday(d)]}요일` }, dayHead(d));
    const showDet = det.length > 0 && (all || st.detail || main.length > 0);   // a day with nothing important: the line below offers it all
    for (const [rg, name] of RG) {
      const rows = main.filter(e => regionOf(e) === rg), extra = rg === 'kr' && showDet;
      if (!rows.length && !extra) continue;
      const grp = h('div', { class: 'kc-grp', 'data-rg': rg, role: 'group', 'aria-label': `${name} 일정` }, h('div', { class: 'kc-rg', 'aria-hidden': 'true', text: name }), rows.map(evRow));
      if (extra) {
        if (st.detail || all) grp.append(h('div', { class: 'kc-subh', text: `기업 세부 일정 ${det.length}개` }), detBox(d, det));
        else { grp.append(detToggle(d, det.length, st.open.has(d))); if (st.open.has(d)) grp.append(detBox(d, det)); }
      }
      sec.append(grp);
    }
    if (all && evs.length) sec.append(revealKey(d, evs.length, true));
    else if (!main.length && !showDet) {
      // nothing to show: say how many are hidden and by which chips, and offer them for this day (the chips stay as they are)
      const why = whyHidden(evs), closed = info && info.kind === 'closed';
      if (closed || !evs.length) sec.append(h('p', { class: 'kc-empty', text: closed ? '장이 쉬어요.' : '일정이 없어요.' }));
      if (evs.length) sec.append(h('p', { class: 'kc-empty kc-hid', text: `숨긴 일정 ${evs.length}개${why.length ? ` (${why.join(' · ')})` : ''}` }), revealKey(d, evs.length, false));
    }
    return sec;
  }
  function revealKey(d, n, open) {
    return h('button', { type: 'button', class: 'kc-dmore', 'data-reveal': d, 'aria-expanded': open ? 'true' : 'false', 'aria-label': `${label(d)} ${open ? '숨긴 일정 다시 숨기기' : `숨긴 일정 ${n}개 보기`}`,
      onclick: () => revealDay(d) }, h('span', { class: 'lab', text: open ? '이 날 다시 숨기기' : '이 날 숨긴 일정 보기' }), svg(open ? IC.up : IC.down));
  }
  function revealDay(d) {
    if (st.all.has(d)) st.all.delete(d); else st.all.add(d);
    const box = root(); if (!box) return;
    for (const old of box.querySelectorAll(`.kc-day[data-day="${d}"]`)) { const fresh = dayBlock(d); old.replaceWith(fresh); fadeIn(fresh); }
    const b = box.querySelector(`[data-reveal="${d}"]`); if (b) b.focus({ preventScroll: true });
  }
  function toggleDay(d, btn) {
    const open = !st.open.has(d);
    if (open) st.open.add(d); else st.open.delete(d);
    const grp = btn.parentNode, old = grp && grp.querySelector('.kc-det');
    if (old) old.remove();                                      // closing: the rows leave at once, together
    const det = detailOn(d);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const lab = btn.querySelector('.lab'), text = open ? '기업 세부 일정 접기' : `기업 세부 일정 ${det.length}개 더 보기`;
    if (KH.ui && typeof KH.ui.swap === 'function') KH.ui.swap(lab, text); else lab.textContent = text;
    btn.querySelector('svg').replaceWith(svg(open ? IC.up : IC.down));
    if (open && det.length) { const box = detBox(d, det); btn.after(box); fadeIn(box); }
  }
  function fadeIn(el) {                                         // design.md §6-2 fade: no delay before it starts, no stagger
    if (reduced() || !el) return;
    el.classList.add('kc-in'); void el.offsetWidth; el.classList.remove('kc-in');
  }

  // ── filter chips: toggled in place, so they can move (a rebuilt chip has no "before" to transition from)
  const CHIP_ON = { hi: () => st.hi, weekly: () => st.weekly, detail: () => st.detail };
  const chipOn = key => (KINDS[key] ? st.kinds.has(key) : CHIP_ON[key] ? CHIP_ON[key]() : false);
  function chipToggle(key) {
    if (KINDS[key]) { if (st.kinds.has(key)) { if (st.kinds.size > 1) st.kinds.delete(key); } else st.kinds.add(key); }
    else if (key === 'hi') st.hi = !st.hi;
    else if (key === 'weekly') st.weekly = !st.weekly;
    else if (key === 'detail') st.detail = !st.detail;
    save();
    const box = root();
    if (box) box.querySelectorAll('.kc-chip').forEach(b => b.setAttribute('aria-pressed', chipOn(b.dataset.chip) ? 'true' : 'false'));
    refresh();
  }
  function chips() {
    const mk = (key, text, title) => h('button', { type: 'button', class: 'kc-chip', 'data-chip': key, 'aria-pressed': chipOn(key) ? 'true' : 'false', title, onclick: () => chipToggle(key) },
      h('span', { class: 'kck', 'aria-hidden': 'true' }), h('span', { class: 'kcl', text }));
    return h('div', { class: 'kc-chips', role: 'group', 'aria-label': '보일 일정' },
      Object.entries(KINDS).map(([k, l]) => mk(k, l)),
      h('span', { class: 'kc-sep', 'aria-hidden': 'true' }),
      mk('hi', '★★ 이상만'),
      mk('weekly', '위클리 만기', '코스피200 위클리 옵션 만기(매주 월 · 목) — 기본은 숨겨요'),
      mk('detail', '기업 세부 일정', '주식권리일정의 통지 · 접수 시한, 명부폐쇄, 교부 · 상장일, 1% 미만 보호예수, 관심 · 지도 밖 종목의 주총 — 기본은 숨겨요'));
  }
  function marks(d) {
    const all = eventsOn(d).filter(inFilter), info = dayInfo(d);
    if (info && info.kind === 'closed') return h('span', { class: 'kc-marks', 'aria-hidden': 'true' }, h('b', { text: '휴' }));
    const hi = all.filter(e => starOf(e) >= 2).length, lo = all.length - hi;
    return h('span', { class: 'kc-marks', 'aria-hidden': 'true' }, [...Array(Math.min(3, hi))].map(() => h('i')), hi < 3 && lo ? h('i', { class: 'dim' }) : null);
  }
  function weekStrip() {
    const m = monday(st.day), t = today();
    const wk = h('div', { class: 'kc-wk', 'data-part': 'wk', role: 'group', 'aria-label': `${label(m)}부터 한 주` }, h('span', { class: 'kc-ind', 'aria-hidden': 'true' }));
    for (let i = 0; i < 7; i++) {
      const d = addD(m, i), info = dayInfo(d), n = eventsOn(d).filter(inFilter).length;
      wk.append(h('button', { type: 'button', class: [d === t ? 'today' : '', i >= 5 ? 'wkend' : '', info && info.kind === 'closed' ? 'closed' : ''].join(' ').trim() || null,
        'aria-pressed': d === st.day ? 'true' : 'false', 'data-d': d,
        'aria-label': `${label(d)} ${WD[wday(d)]}요일${d === t ? ', 오늘' : ''}${info ? ', ' + info.note : ''}, 일정 ${n}개`, onclick: () => pick(d) },
        h('span', { class: 'dw', text: d === t ? '오늘' : WD[wday(d)] }), h('span', { class: 'dnum num', text: String(+d.slice(8)) }), marks(d)));
    }
    wk.addEventListener('keydown', ev => {
      if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
      ev.preventDefault(); pick(addD(st.day, ev.key === 'ArrowLeft' ? -1 : 1), ev.repeat ? 'repeat' : 'key');
    });
    return wk;
  }
  // the raised marker under the chosen day: leading edge `lead`, trailing `trail` (KH.spring.edges, design.md §6-3 · §7 ①);
  // the first place, a resize and held arrow keys (design.md §8) set it at once
  function placeInd(animate) {
    const wk = root() && root().querySelector('.kc-wk'); if (!wk) return;
    const ind = wk.querySelector('.kc-ind'), cur = wk.querySelector('button[aria-pressed="true"]');
    if (!ind || !cur) return;
    const box = { left: cur.offsetLeft, width: cur.offsetWidth };
    if (KH.spring && typeof KH.spring.edges === 'function') {
      const ctl = KH.spring.edges(ind);
      if (animate && ctl.value() && !reduced()) ctl.to(box); else ctl.set(box);
    } else { ind.style.transform = `translateX(${box.left}px)`; ind.style.width = box.width + 'px'; }
  }
  const key = (cls, aria, ic, fn) => h('button', { type: 'button', class: cls, 'data-key': aria, 'aria-label': aria, onclick: fn }, svg(ic));
  const todayKey = () => h('button', { type: 'button', class: 'kc-tk', 'data-key': '오늘', onclick: () => pick(today()), text: '오늘' });
  function note(from, to) {
    const f = failed(from, to);
    const srcs = bodiesIn(from, to).map(v => v.body && v.body.sources).filter(Boolean)[0];
    const bad = srcs ? Object.entries(srcs).filter(([id, s]) => !s.off && s.ok === false && id !== 'vals').map(([, s]) => s.name) : [];
    const asOf = bodiesIn(from, to).map(v => v.body && v.body.asOf).filter(Boolean).sort().pop();
    const parts = ['시각은 모두 한국 시간이에요', asOf ? `${asOf.slice(11, 16)} 기준` : null].filter(Boolean);
    if (f && loaded(from, to)) parts.push('일부 날짜를 새로 받지 못했어요');
    if (bad.length) parts.push(`${bad.join(' · ')}을 새로 받지 못해 지난 일정을 보여 줘요`);
    return h('p', { class: 'kc-note', role: 'status' }, (f && loaded(from, to)) || bad.length ? h('span', { class: 'bang', 'aria-hidden': 'true', text: '!' }) : null, parts.join(' · ') + '.');
  }
  function message(from, to) {
    const f = failed(from, to);
    if (f && f.err === 'none') return h('div', { class: 'kc-msg', role: 'status' }, h('b', { text: '일정을 아직 준비하고 있어요' }), h('span', { text: '조금 뒤에 다시 열어 주세요.' }));
    if (f) return h('div', { class: 'kc-msg', role: 'status' }, h('b', { text: '일정을 불러오지 못했어요' }), h('span', { text: '네트워크를 확인한 뒤 다시 시도해 주세요.' }),
      h('button', { type: 'button', class: 'kc-tk', onclick: () => { ensure(from, to, true); draw(false); }, text: '다시 시도' }));
    return h('div', { class: 'kc-msg', role: 'status', 'aria-busy': 'true' }, h('span', { text: '일정을 불러오는 중이에요…' }));
  }

  // ── phone (and up to 1279 px): week strip + list
  function phone() {
    const m = monday(st.day), e = addD(m, 6), sameMonth = m.slice(5, 7) === e.slice(5, 7);
    const wrap = h('div', { class: 'kc-phone' },
      h('div', { class: 'kc-hd' },
        h('h2', {}, `${label(m)} – ${sameMonth ? +e.slice(8) + '일' : label(e)}`, h('small', { text: '한국 시간' })),
        key('kc-ik', '지난주', IC.l, () => pick(addD(st.day, -7))), key('kc-ik', '다음 주', IC.r, () => pick(addD(st.day, 7))), todayKey()),
      weekStrip(), chips());
    wrap.append(listFor(st.day, addD(st.day, 6), true));       // the chosen day and the six after it (a weekend still sees the week ahead)
    return wrap;
  }
  function listFor(from, to, withMore) {
    const list = h('div', { class: 'kc-list', 'data-part': 'list', 'aria-live': 'polite' });
    if (!loaded(from, to)) { list.append(message(from, to)); return list; }
    for (let d = from; d <= to; d = addD(d, 1)) list.append(dayBlock(d));
    if (withMore) list.append(h('div', { class: 'kc-more' }, h('button', { type: 'button', class: 'kc-tk', 'data-next': '1', onclick: () => pick(addD(st.day, 7), 'next'), text: '다음 7일 보기' })));
    list.append(note(from, to));
    return list;
  }
  // ── ≥ 1280: month grid + 7 days from the chosen one
  function gridStart() { const first = st.day.slice(0, 8) + '01'; return monday(first); }
  function gridLines(d) {            // the cell's three lines: the three most important, then 미국 first and in time order (§9-6)
    const top = eventsOn(d).filter(inFilter).sort((a, b) => starOf(b) - starOf(a) || sortEv(a, b));
    const three = top.slice(0, 3).sort((a, b) => (regionOf(a) === regionOf(b) ? 0 : regionOf(a) === 'us' ? -1 : 1) || sortEv(a, b));
    return { three, n: top.length };
  }
  function desk() {
    const [y, mo] = st.day.split('-').map(Number), g = gridStart();
    const step = n => { const o = new Date(Date.UTC(y, mo - 1 + n, 1)); pick(o.toISOString().slice(0, 10)); };
    const wrap = h('div', { class: 'kc-desk' },
      h('div', { class: 'kc-bar' }, h('h2', { text: `${y}년 ${mo}월` }),
        key('kc-ik', '지난달', IC.l, () => step(-1)), key('kc-ik', '다음 달', IC.r, () => step(1)), todayKey(), chips()));
    const grid = h('div', { class: 'kc-mg', role: 'grid', 'aria-label': `${y}년 ${mo}월` }, ['월', '화', '수', '목', '금', '토', '일'].map(x => h('div', { class: 'h', role: 'columnheader', text: x })));
    const t = today();
    let d = g;
    for (let w = 0; w < 6; w++) {
      for (let i = 0; i < 7; i++, d = addD(d, 1)) {
        const day = d, { three, n } = gridLines(d), info = dayInfo(d), out = +d.slice(5, 7) !== mo;
        const c = h('button', { type: 'button', role: 'gridcell', class: ['cell', out ? 'out' : '', d === t ? 'today' : '', d < t ? 'past' : '', i >= 5 ? 'wkend' : ''].join(' '),
          'aria-pressed': d === st.day ? 'true' : 'false', 'data-d': d, 'aria-label': `${label(d)} ${WD[wday(d)]}요일${info ? ', ' + info.note : ''}, 일정 ${n}개`, onclick: () => pick(day) },
          h('span', { class: 'top1' }, h('span', { class: 'dnum num', text: String(+d.slice(8)) }), info ? h('span', { class: 'cl', text: info.note }) : null),
          three.map(e => h('span', { class: 'line s' + starOf(e), 'data-rg': regionOf(e) }, stars(starOf(e)), h('span', { class: 'ttl', text: (e.n && !e.grp ? e.n + ' ' : '') + e.title }))),
          n > 3 ? h('span', { class: 'plus', text: `+${n - 3}개` }) : null);
        grid.append(c);
      }
      if (+d.slice(5, 7) !== mo && d > g) break;
    }
    grid.addEventListener('keydown', ev => {
      const map = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
      if (!(ev.key in map)) return;
      ev.preventDefault(); pick(addD(st.day, map[ev.key]), 'key');
    });
    wrap.append(h('div', { class: 'kc-card', 'data-part': 'grid' }, loaded(g, addD(g, 41)) ? grid : message(g, addD(g, 41))));
    wrap.append(sideFor());
    return wrap;
  }
  const sideFor = () => h('aside', { class: 'kc-card kc-side', 'data-part': 'side', 'aria-label': '고른 날부터 7일' },
    h('div', { class: 'kc-sideh' }, h('h3', { text: '고른 날부터 7일' }), h('span', { class: 'kc-badge', text: '한국 시간' })),
    listFor(st.day, addD(st.day, 6), false));

  // ── draw (everything) · refresh (only the parts that show data — the chips stay, so they animate and keep focus) · pick
  function snapshotNote() {
    return h('div', { class: 'kc-msg', role: 'status' }, h('b', { text: '증시 일정은 실시간 버전에서 볼 수 있어요' }),
      h('a', { class: 'kc-tk', href: (KH.LIVE_URL || 'https://panse.pages.dev/') + '#cal', target: '_blank', rel: 'noopener', text: '실시간 버전 열기' }));
  }
  const readMap = () => { try { st.map = new Set(typeof KH.mapCodes === 'function' ? KH.mapCodes() : []); } catch (e) { st.map = new Set(); } };
  function draw() {
    const box = root(); if (!box || !st.on) return;
    readMap();
    const y = scrollY, a = document.activeElement, ds = a && box.contains(a) && a.dataset ? a.dataset : {};
    box.replaceChildren(h('div', { class: 'kc' }, KH.MODE === 'snapshot' ? snapshotNote() : wide() ? desk() : phone()));
    footLine();
    if (KH.MODE === 'snapshot') return;
    placeInd(false);
    requestAnimationFrame(() => placeInd(false));             // once more after the tab has laid out (the box may have just unhidden)
    refocus(box, ds);
    if (Math.abs(scrollY - y) > 1) scrollTo(scrollX, y);
  }
  function refocus(box, ds) {
    let b = null;
    if (ds.d) b = box.querySelector(`[data-d="${ds.d}"][aria-pressed="true"]`) || box.querySelector(`[data-d="${ds.d}"]`);
    else if (ds.id) b = box.querySelector(`[data-id="${CSS.escape(ds.id)}"]`);
    else if (ds.more) b = box.querySelector(`[data-more="${ds.more}"]`);
    else if (ds.reveal) b = box.querySelector(`[data-reveal="${ds.reveal}"]`);
    else if (ds.chip) b = box.querySelector(`[data-chip="${ds.chip}"]`);
    else if (ds.next) b = box.querySelector('[data-next]');
    else if (ds.key) b = box.querySelector(`[data-key="${CSS.escape(ds.key)}"]`);
    if (b) b.focus({ preventScroll: true });
  }
  function refresh() {
    const box = root(); if (!box || !st.on) return;
    if (KH.MODE === 'snapshot' || !box.querySelector(wide() ? '.kc-desk' : '.kc-phone')) return draw();
    readMap();
    const y = scrollY, a = document.activeElement, ds = a && a.dataset ? a.dataset : {};
    const inPart = a && box.contains(a) && a.closest('[data-part]');
    const fresh = wide() ? desk() : phone();
    const parts = [...fresh.querySelectorAll('[data-part]')].filter(p => !p.parentElement.closest('[data-part]'));   // outermost only (the side holds a list)
    for (const part of parts) { const old = box.querySelector(`[data-part="${part.dataset.part}"]`); if (old) old.replaceWith(part); }
    placeInd(false);
    if (inPart) refocus(box, ds);
    if (Math.abs(scrollY - y) > 1) scrollTo(scrollX, y);
  }
  // how: 'key' (an arrow key) · 'repeat' (held) · 'next' (다음 7일 보기) · undefined (a tap or click)
  function pick(d, how) {
    if (!d) return;
    const kb = how === 'key' || how === 'repeat';
    const box = root();
    const [f, t] = (() => { const keep = st.day; st.day = d; const r = rangeNow(); st.day = keep; return r; })();
    const ready = loaded(f, t);
    const samePlace = box && ready && (wide() ? gridStart() === monday(d.slice(0, 8) + '01') && box.querySelector('.kc-mg') : monday(d) === monday(st.day) && box.querySelector('.kc-phone .kc-wk'));
    st.day = d;
    if (samePlace) {                         // same week strip / same month grid: move the marker, swap the list in place
      box.querySelectorAll(wide() ? '.kc-mg .cell' : '.kc-wk button').forEach(b => b.setAttribute('aria-pressed', b.dataset.d === d ? 'true' : 'false'));
      if (!wide()) placeInd(how !== 'repeat');
      if (kb) { const b = box.querySelector(`[data-d="${d}"]`); if (b) b.focus(); }
      const old = box.querySelector(wide() ? '.kc-side' : '.kc-phone .kc-list');
      if (old) { const fresh = wide() ? sideFor() : listFor(st.day, addD(st.day, 6), true); old.replaceWith(fresh); fadeIn(wide() ? fresh.querySelector('.kc-list') : fresh); }
      ensure(f, t);                          // a later day's seven can reach into the next 14-day block
      return;
    }
    draw();
    // ← on a Monday / → on a Sunday (or a month edge) redraws the strip: the old button is gone, so keep the keyboard on the new day
    if (kb) { const b = root() && root().querySelector(`[data-d="${d}"]`); if (b) b.focus({ preventScroll: true }); }
    if (how === 'next') {                    // the list starts again from its top: bring the week back into view, keep the key focused
      const hd = box && box.querySelector('.kc-hd'), pad = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
      if (hd && hd.getBoundingClientRect().top < pad) hd.scrollIntoView({ block: 'start' });   // html scroll-padding keeps it under the stuck header
      fadeIn(box && box.querySelector('.kc-phone .kc-list'));
      const nx = box && box.querySelector('[data-next]'); if (nx) nx.focus({ preventScroll: true });
    }
    ensure(f, t);
  }

  // ── detail (a <dialog>: phone = bottom sheet, wider = floating panel) — design.md §5 · §7 시트 · §8, user 2026-11-15 19:49 (떠 있는 창에
  // 움직임이 없다): opens with `open` from its closed pose, closes with `close` — a real exit: close() runs at once (the page is usable again,
  // focus goes back to the row) while CSS keeps the sheet and its backdrop in the top layer until the exit ends (transition-behavior:
  // allow-discrete on display · overlay); opening again mid-exit turns it around from where it is. Phone: drag the grip or the title
  // down to dismiss (6px to start, axis lock 6px, release speed from the last 100ms, past 35% of its height or a throw > 0.11px/ms,
  // rubber band .55 upward; the hand-off rides `settle` with the finger's speed — KH.spring). 줄이기: every length is 0.
  let dlg = null, opener = null, openerId = null, closeT = 0, leaving = false, drag = null, dragH = null;
  const DISCRETE = !!(window.CSS && CSS.supports && CSS.supports('transition-behavior', 'allow-discrete'));
  const sheetMode = () => !matchMedia('(min-width: 761px)').matches;
  const fmtPeriod = p => !p ? '' : /^\d{4}-\d{2}-\d{2}$/.test(p) ? (p.endsWith('-01') ? `${p.slice(0, 4)}년 ${+p.slice(5, 7)}월` : `${p.slice(0, 4)}년 ${+p.slice(5, 7)}월 ${+p.slice(8)}일`)
    : /^\d{6}$/.test(p) ? `${p.slice(0, 4)}년 ${+p.slice(4)}월` : /^\d{4}Q\d$/.test(p) ? `${p.slice(0, 4)}년 ${p.slice(5)}분기` : /^\d{8}$/.test(p) ? `${+p.slice(4, 6)}월 ${+p.slice(6)}일 기준` : p;
  function why(e, s) {
    if (e.k === 'cb') return '기준금리를 정하거나 그 논의를 공개하는 날이라 금리 · 환율 · 주가가 함께 움직일 수 있어요.';
    if (e.k === 'mkt' && e.star === 3) return '선물과 옵션 만기가 겹치는 날이에요(3 · 6 · 9 · 12월 둘째 목요일). 장 마감 무렵 거래가 몰릴 수 있어요.';
    if (e.weekly) return '코스피200 위클리 옵션의 마지막 거래일이에요. 매주 월 · 목이라 기본으로는 숨겨요.';
    if (e.k === 'corp' && isMinor(e)) return e.cls === 'agm' ? '주주총회예요. 관심종목과 지도에 있는 종목의 주총만 기본으로 보여 주고, 나머지는 "기업 세부 일정"에 있어요.'
      : '권리 행사 절차의 세부 일정이에요(통지 · 접수 시한, 명부폐쇄, 교부 · 상장일 같은 것). 기본으로는 숨기고 "기업 세부 일정"을 켜면 보여요.';
    if (e.k === 'corp' && e.pct != null) return `풀리는 주식이 상장주식의 ${e.pct}%예요. 별 기준: 10% 이상 ★★★ · 3% 이상 ★★ · 그 밖 ★, 1% 미만은 세부 일정으로 숨겨요.${watched(e.c) ? ' 관심종목이라 하나 더했어요.' : ''}`;
    if (e.k === 'corp' && e.exd) return `권리락은 기준일 전 영업일(${label(e.exd)})이에요. 그날부터 산 주식에는 새 주식이 배정되지 않아요.${watched(e.c) ? ' 관심종목이라 별을 하나 더했어요.' : ''}`;
    if (e.k === 'corp') return `회사 일정이에요.${watched(e.c) ? ' 관심종목이라 별을 하나 더했어요.' : ''}`;
    return ['', '참고용 발표로 분류했어요(자체 기준).', '자주 보는 발표로 분류했어요(자체 기준).', '시장 전체에 영향이 큰 발표로 분류했어요(자체 기준).'][s];
  }
  function srcNote(e) {
    if (e.src === 'fred') return e.orig && e.orig.t ? '날짜는 FRED, 시각은 따로 둔 표(미국 동부)' : '날짜는 FRED — 발표 시각은 확인 중이에요';
    if (e.src === 'bok') return '날짜 · 시각 모두 한국은행 공표일정';
    if (e.src === 'kostat') return '날짜 · 시각 모두 국가데이터처 보도계획';
    if (e.src === 'manual') return '한국은행 · 연준 · 거래소 공지를 보고 넣어 둬요';
    if (e.src === 'rule') return '정해진 규칙으로 계산해요';
    if (e.src === 'dart') return `OpenDART ${e.api || ''} 값`.trim();
    if (e.src === 'fsc') return '다음 영업일 13시 이후 반영';
    return '';
  }
  function origLong(e) {
    if (!e.orig) return null;
    const [, m, d] = e.orig.d.split('-').map(Number);
    if (!e.orig.t) return `미국 동부 ${m}월 ${d}일 발표 — 시각은 확인 중이에요`;
    const [hh, mm] = e.orig.t.split(':').map(Number);
    return `미국 동부 ${m}월 ${d}일 ${hh >= 12 ? '오후' : '오전'} ${((hh + 11) % 12) + 1}:${String(mm).padStart(2, '0')} 발표 → 한국 시간으로 바꿨어요`;
  }
  function makeDialog() {
    dlg = h('dialog', { class: 'kc-dlg', 'aria-labelledby': 'kc-dt' });
    dlg.addEventListener('cancel', ev => { ev.preventDefault(); closeDetail(); });
    dlg.addEventListener('click', ev => {             // the backdrop (a click on the dialog box itself but outside its rectangle)
      if (ev.target !== dlg || drag) return;
      const r = dlg.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) closeDetail();
    });
    dlg.addEventListener('transitionend', ev => { if (ev.target === dlg && ev.propertyName === 'transform' && !dlg.open) leaving = false; });
    // drag to dismiss (phone sheet only; the grip and the title row — touch-action:none there, the rest scrolls)
    dlg.addEventListener('pointerdown', ev => {
      if (!dlg.open || !dlg.classList.contains('on') || !sheetMode() || ev.button > 0) return;
      const zone = ev.target.closest('.kc-grab, .kc-sh'); if (!zone) return;
      if (dragH) { dragH.stop(); dragH = null; }
      drag = { id: ev.pointerId, zone, x0: ev.clientX, y0: ev.clientY, on: false, y: 0, h: dlg.offsetHeight, s: [] };
    });
    dlg.addEventListener('pointermove', ev => {
      const g = drag; if (!g || ev.pointerId !== g.id) return;
      const dx = ev.clientX - g.x0, dy = ev.clientY - g.y0;
      if (!g.on) {
        if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
        if (Math.abs(dx) > Math.abs(dy)) { drag = null; return; }          // sideways: not a dismiss
        g.on = true; dlg.classList.add('drag');
        try { g.zone.setPointerCapture(ev.pointerId); } catch (e) { /* the pointer is gone */ }
      }
      g.y = dy >= 0 ? dy : dy * 0.55;                                       // upward past the open pose: rubber band
      dlg.style.transform = `translateY(${g.y}px)`;
      g.s.push({ t: ev.timeStamp, y: g.y });
      while (g.s.length > 2 && ev.timeStamp - g.s[0].t > 100) g.s.shift();
    });
    const end = ev => {
      const g = drag; if (!g || ev.pointerId !== g.id) return;
      drag = null;
      if (!g.on) return;
      const win = g.s.filter(x => ev.timeStamp - x.t <= 100), a = win[0], b = win[win.length - 1];          // the last 100ms only:
      const v = win.length > 1 && b.t > a.t ? (b.y - a.y) / (b.t - a.t) : 0;                               // a finger that stopped → 0 (px/ms)
      const go = ev.type !== 'pointercancel' && (g.y > 0.35 * g.h || v > ((KH.spring && KH.spring.THROW) || 0.11));
      settleSheet(g.y, go ? g.h + 24 : 0, v, go);                          // (the lift is captured by the grip row: no button under it fires)
    };
    dlg.addEventListener('pointerup', end);
    dlg.addEventListener('pointercancel', end);
    document.body.append(dlg);
  }
  // after a drag: back to the open pose, or away (then closed) — `settle` with the finger's speed
  function settleSheet(from, to, vPxMs, away) {
    if (away) dlg.classList.remove('on');                                   // the backdrop fades with `close` meanwhile
    const done = () => {
      dragH = null;
      if (away) { closeDetail(false, true); dlg.style.transform = ''; dlg.classList.remove('drag'); }
      else { dlg.style.transform = ''; dlg.classList.remove('drag'); }
    };
    if (!KH.spring || typeof KH.spring.animate !== 'function' || reduced()) { dlg.style.transform = `translateY(${to}px)`; done(); return; }
    dragH = KH.spring.animate({ from, to, name: 'settle', velocity: vPxMs * 1000, onUpdate: y => { dlg.style.transform = `translateY(${y}px)`; }, onRest: done });
  }
  function openDetail(e, from) {
    opener = from || document.activeElement;
    openerId = opener && opener.dataset ? opener.dataset.id || null : null;
    clearTimeout(closeT);
    if (!dlg) makeDialog();
    if (dragH) { dragH.stop(); dragH = null; }
    drag = null; dlg.classList.remove('drag'); dlg.style.transform = '';
    const s = starOf(e), past = isPast(e);
    const when = e.t ? `${label(e.d)} (${WD[wday(e.d)]}) ${e.t}` : `${label(e.d)} (${WD[wday(e.d)]}) · 종일`;
    const names = e.grp && e.codes ? e.codes.map(c => { const r = KH.stock(c); return { c, n: (r && r.n) || c }; }) : null;
    // every piece goes through h() (which drops null) — native replaceChildren / append print null as the text "null"
    dlg.replaceChildren(h('div', { class: 'kc-dbody' },
      h('span', { class: 'kc-grab', 'aria-hidden': 'true' }),
      h('div', { class: 'kc-sh' }, h('h3', { id: 'kc-dt' }, e.n && !e.grp ? h('span', { class: 'co', text: `${e.n} · ${e.c}` }) : null, e.title), h('button', { type: 'button', class: 'kc-x', 'aria-label': '닫기', onclick: () => closeDetail() }, svg(IC.x))),
      h('dl', { class: 'kc-kv' },
        h('dt', { text: '언제' }), h('dd', { class: 'num' }, when, origLong(e) ? h('small', { text: origLong(e) }) : null),
        e.value ? [h('dt', { text: '발표값' }), h('dd', {}, e.value.text, e.value.p ? h('small', { text: `${fmtPeriod(e.value.p)} · ${e.value.src === 'ecos' ? '한국은행 ECOS' : 'FRED'}` }) : null)] : null,
        h('dt', { text: '중요도' }), h('dd', {}, stars(s), ' ', ['', '참고', '중요', '매우 중요'][s]),
        h('dt', { text: '분류' }), h('dd', {}, `${e.k === 'us' || e.k === 'kr' ? '' : regionOf(e) === 'us' ? '미국 · ' : '한국 · '}${KINDS[e.k] || ''}${isMinor(e) ? ' · 세부 일정' : ''}`, e.sub ? h('small', { text: e.sub }) : null),
        h('dt', { text: '출처' }), h('dd', {}, SRC[e.src] || e.src, h('small', { text: srcNote(e) })),
        h('dt', { text: '상태' }), h('dd', { text: e.tentative ? `예정 — ${e.tentative}` : past ? '지났어요' : '예정' })),
      names ? h('div', { class: 'kc-codes', role: 'list', 'aria-label': '종목' }, names.map(x => h('button', { type: 'button', role: 'listitem', onclick: () => { closeDetail(true); if (KH.openStock) KH.openStock(x.c, {}); }, text: x.n }))) : null,
      h('p', { class: 'kc-why', text: why(e, s) }),
      h('div', { class: 'kc-acts' },
        e.url ? h('a', { href: e.url, target: '_blank', rel: 'noopener' }, svg(IC.ext), e.src === 'dart' ? 'DART 원문' : '원천 보기') : null,
        e.c && !e.grp && typeof KH.openStock === 'function' ? h('button', { type: 'button', onclick: () => { closeDetail(true); KH.openStock(e.c, {}); }, text: '종목 페이지' }) : null),
      h('p', { class: 'foot', text: '시각은 한국 시간이에요. 원천이 일정을 바꾸면 다음 갱신 때 바뀌어요.' })));
    const midExit = leaving && !dlg.open;                          // still on screen, on its way out: turn it around from where it is
    if (!dlg.open) dlg.showModal();
    leaving = false;
    document.dispatchEvent(new CustomEvent('kh:worlddetail'));      // the phone dock hides while a sheet is open (template openWins)
    if (reduced() || midExit || dlg.classList.contains('on')) dlg.classList.add('on');
    else requestAnimationFrame(() => requestAnimationFrame(() => { if (dlg.open) dlg.classList.add('on'); }));   // open spring from the closed pose
    dlg.querySelector('.kc-x').focus();
  }
  function closeDetail(noFocus, dragged) {
    if (!dlg || !dlg.open) return;
    if (dragH && !dragged) { dragH.stop(); dragH = null; }
    drag = null;
    if (!dragged) { dlg.classList.remove('drag'); dlg.style.transform = ''; }
    dlg.classList.remove('on');                                   // close spring (shorter than open, design.md §6-2)
    clearTimeout(closeT);
    const shut = () => {
      if (dlg.classList.contains('on') || !dlg.open) return;
      dlg.close();
      document.dispatchEvent(new CustomEvent('kh:worlddetail'));
      if (!noFocus) {                                             // back to the row that opened it (found again if the list was redrawn)
        const el = opener && opener.isConnected ? opener : openerId && root() ? root().querySelector(`[data-id="${CSS.escape(openerId)}"]`) : null;
        if (el) el.focus({ preventScroll: true });
      }
    };
    if (DISCRETE || reduced() || dragged) {                        // CSS keeps it drawn through the exit; the page is usable at once
      leaving = !reduced() && !dragged;
      if (leaving) closeT = setTimeout(() => { leaving = false; }, cssMs('--sp-close-dur') + 60);
      shut();
    } else closeT = setTimeout(shut, cssMs('--sp-close-dur') + 30);   // older engines: stay modal until the exit ends
  }

  // ── footer line (above the disclaimer, §3-30): the template's renderFooter() puts <p id="foot-cal"> with footText() on the 일정 tab
  const FOOT = '일정: 한국은행 경제통계 공표일정 · 국가데이터처 보도계획 · 미국 지표는 FRED® 발표 일정(This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.) · 발표값은 한국은행 ECOS · FRED · 금통위 · FOMC · 휴장은 한국은행 · 연준 · 한국거래소 공지를 보고 직접 넣어요 · 회사 일정: 금융감독원 DART · 금융위원회(공공데이터포털). 시각은 모두 한국 시간이고, 일정은 원천 사정으로 바뀔 수 있어요.';
  function footLine() { const p = document.getElementById('foot-cal'); if (p && st.on) p.textContent = FOOT; }

  // ── lifecycle
  function onResize() { if (!st.on) return; const w = wide(); if (w !== st.wasWide) { st.wasWide = w; draw(); const [f, t] = rangeNow(); ensure(f, t); } else placeInd(false); }
  function show() {
    st.on = true; st.wasWide = wide();
    if (!st.day) st.day = today();
    draw();
    if (KH.MODE === 'snapshot') return;
    const [f, t] = rangeNow();
    ensure(f, t);
    clearInterval(st.timer);
    st.timer = setInterval(() => { if (!document.hidden && st.on) { const [a, b] = rangeNow(); ensure(a, b); } }, 60e3);
  }
  function hide() {
    st.on = false;
    clearInterval(st.timer); st.timer = null;
    clearTimeout(closeT);
    if (dlg && dlg.open) { dlg.classList.remove('on'); dlg.close(); }
  }
  addEventListener('resize', onResize);
  document.addEventListener('kh:watch', () => { if (st.on) refresh(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && st.on) { const [a, b] = rangeNow(); ensure(a, b); } });
  window.KHCal = { show, hide, isOn: () => st.on, detailOpen: () => !!(dlg && dlg.open), footText: () => FOOT };
})();
