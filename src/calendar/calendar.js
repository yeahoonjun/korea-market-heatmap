/* 증시 캘린더 — the 일정 tab (AGENTS §3-33, docs/standards/calendar.md §5 A안).
   window.KHCal = { show(kind), hide(), isOn() }. The template calls show('calendar') when the 일정 tab (state.market 'CAL', #cal) opens and
   hands over <div id="calendar">; hide() when another tab opens. Data: GET /api/calendar?from&to (Worker calendar.js), fetched in
   14-day blocks (cached in memory, re-read every 30 min while shown). Phone: week strip + day list; ≥ 1280 px: month grid + 7-day list.
   Stars and badges are neutral (never the up/down colours); amber only for the chosen day, switched-on chips and focus.
   Saved: localStorage khm.cal = {kinds:[…], hi:bool, weekly:bool} (weekly option expiries hidden by default, user 2026-11-15). */
(() => {
  'use strict';
  const KH = window.KH;
  if (!KH || window.KHCal) return;
  const h = KH.h;
  const KST = 9 * 3600e3, DAY = 86400e3;
  const KINDS = { kr: '한국 지표', us: '미국 지표', cb: '금리', mkt: '시장', corp: '기업' };
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
  const svg = d => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.innerHTML = d; return s; };
  const IC = { l: '<path d="M15 6l-6 6 6 6"/>', r: '<path d="M9 6l6 6-6 6"/>', chev: '<path d="M9 6l6 6-6 6"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', ck: '<path d="M5 12.5l4.2 4L19 7"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>' };

  // ── state
  const saved = (() => { try { return JSON.parse(localStorage.getItem('khm.cal') || '{}') || {}; } catch (e) { return {}; } })();
  const st = {
    on: false, day: null,
    kinds: new Set(Array.isArray(saved.kinds) && saved.kinds.length ? saved.kinds.filter(k => KINDS[k]) : Object.keys(KINDS)),
    hi: !!saved.hi, weekly: !!saved.weekly,
    blocks: new Map(),       // blockStart → {at, body} | {at, err}
    pending: new Map(), timer: null, lastIdx: -1, error: null,
  };
  const save = () => { try { localStorage.setItem('khm.cal', JSON.stringify({ kinds: [...st.kinds], hi: st.hi, weekly: st.weekly })); } catch (e) { /* private mode */ } };
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
    if (st.on) draw(false);
  }
  const rangeNow = () => wide() ? (() => { const g = gridStart(); return [g, addD(g, 41 + 7)]; })() : [monday(st.day), addD(st.day, 6)];
  function bodiesIn(from, to) { return blocksFor(from, to).map(b => st.blocks.get(b)).filter(Boolean); }
  function eventsOn(d) {
    const out = [];
    for (const v of bodiesIn(d, d)) if (v.body) for (const e of v.body.events || []) if (e.d === d) out.push(e);
    return out;
  }
  function dayInfo(d) { for (const v of bodiesIn(d, d)) if (v.body && v.body.days && v.body.days[d]) return v.body.days[d]; return null; }
  const watched = c => !!(c && KH.watch && typeof KH.watch.has === 'function' && KH.watch.has(c));
  const starOf = e => Math.min(3, (e.star || 1) + (e.k === 'corp' && watched(e.c) ? 1 : 0));
  const visible = e => st.kinds.has(e.k) && (!e.weekly || st.weekly) && (!st.hi || starOf(e) >= 2);
  const sortEv = (a, b) => (a.t || '00:00').localeCompare(b.t || '00:00') || starOf(b) - starOf(a);
  const shown = d => eventsOn(d).filter(visible).sort(sortEv);
  const hiddenCount = d => eventsOn(d).filter(e => !e.weekly || st.weekly).length - shown(d).length;
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
  function dayBlock(d) {
    const list = shown(d), info = dayInfo(d);
    const sec = h('section', { class: 'kc-day', 'aria-label': `${label(d)} ${WD[wday(d)]}요일` }, dayHead(d));
    if (list.length) list.forEach(e => sec.append(evRow(e)));
    else {
      const hid = hiddenCount(d);
      sec.append(h('p', { class: 'kc-empty', text: info && info.kind === 'closed' ? '장이 쉬어요.' : hid ? `고른 조건에 맞는 일정이 없어요 · 숨긴 일정 ${hid}개` : '일정이 없어요.' }));
    }
    return sec;
  }
  function chips() {
    const mk = (text, on, fn, title) => h('button', { type: 'button', class: 'kc-chip', 'aria-pressed': on ? 'true' : 'false', title, onclick: () => { fn(); save(); draw(false); } },
      h('span', { class: 'kck' }, svg(IC.ck)), text);
    return h('div', { class: 'kc-chips', role: 'group', 'aria-label': '보일 일정' },
      ...Object.entries(KINDS).map(([k, l]) => mk(l, st.kinds.has(k), () => { if (st.kinds.has(k)) { if (st.kinds.size > 1) st.kinds.delete(k); } else st.kinds.add(k); })),
      h('span', { class: 'kc-sep', 'aria-hidden': 'true' }),
      mk('★★ 이상만', st.hi, () => { st.hi = !st.hi; }),
      mk('위클리 만기', st.weekly, () => { st.weekly = !st.weekly; }, '코스피200 위클리 옵션 만기(매주 월 · 목) — 기본은 숨겨요'));
  }
  function marks(d) {
    const all = eventsOn(d).filter(e => !e.weekly || st.weekly), info = dayInfo(d);
    if (info && info.kind === 'closed') return h('span', { class: 'kc-marks', 'aria-hidden': 'true' }, h('b', { text: '휴' }));
    const hi = all.filter(e => starOf(e) >= 2).length, lo = all.length - hi;
    return h('span', { class: 'kc-marks', 'aria-hidden': 'true' }, [...Array(Math.min(3, hi))].map(() => h('i')), hi < 3 && lo ? h('i', { class: 'dim' }) : null);
  }
  function weekStrip() {
    const m = monday(st.day), t = today();
    const wk = h('div', { class: 'kc-wk', role: 'group', 'aria-label': `${label(m)}부터 한 주` }, h('span', { class: 'kc-ind', 'aria-hidden': 'true' }));
    for (let i = 0; i < 7; i++) {
      const d = addD(m, i), info = dayInfo(d), n = eventsOn(d).filter(visible).length;
      wk.append(h('button', { type: 'button', class: [d === t ? 'today' : '', i >= 5 ? 'wkend' : '', info && info.kind === 'closed' ? 'closed' : ''].join(' ').trim() || null,
        'aria-pressed': d === st.day ? 'true' : 'false', 'data-d': d,
        'aria-label': `${label(d)} ${WD[wday(d)]}요일${d === t ? ', 오늘' : ''}${info ? ', ' + info.note : ''}, 일정 ${n}개`, onclick: () => pick(d) },
        h('span', { class: 'dw', text: d === t ? '오늘' : WD[wday(d)] }), h('span', { class: 'dnum num', text: String(+d.slice(8)) }), marks(d)));
    }
    wk.addEventListener('keydown', ev => {
      if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
      ev.preventDefault(); pick(addD(st.day, ev.key === 'ArrowLeft' ? -1 : 1), true);
    });
    return wk;
  }
  function placeInd(animate) {
    const wk = root() && root().querySelector('.kc-wk'); if (!wk) return;
    const ind = wk.querySelector('.kc-ind'), cur = wk.querySelector('button[aria-pressed="true"]');
    if (!ind || !cur) return;
    const btns = [...wk.querySelectorAll('button')], idx = btns.indexOf(cur);
    ind.classList.toggle('now', !animate || reduced());
    ind.classList.toggle('rev', idx < st.lastIdx);
    ind.style.left = cur.offsetLeft + 'px'; ind.style.width = cur.offsetWidth + 'px';
    st.lastIdx = idx;
  }
  const key = (cls, aria, ic, fn) => h('button', { type: 'button', class: cls, 'aria-label': aria, onclick: fn }, svg(ic));
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
        key('kc-ik', '지난주', IC.l, () => pick(addD(st.day, -7))), key('kc-ik', '다음 주', IC.r, () => pick(addD(st.day, 7))),
        h('button', { type: 'button', class: 'kc-tk', onclick: () => pick(today()), text: '오늘' })),
      weekStrip(), chips());
    wrap.append(listFor(st.day, addD(st.day, 6), true));       // the chosen day and the six after it (a weekend still sees the week ahead)
    return wrap;
  }
  function listFor(from, to, withMore) {
    const list = h('div', { class: 'kc-list', 'aria-live': 'polite' });
    if (!loaded(from, to)) { list.append(message(from, to)); return list; }
    for (let d = from; d <= to; d = addD(d, 1)) list.append(dayBlock(d));
    if (withMore) list.append(h('div', { class: 'kc-more' }, h('button', { type: 'button', class: 'kc-tk', onclick: () => pick(addD(st.day, 7)), text: '다음 7일 보기' })));
    list.append(note(from, to));
    return list;
  }
  // ── ≥ 1280: month grid + 7 days from the chosen one
  function gridStart() { const first = st.day.slice(0, 8) + '01'; return monday(first); }
  function desk() {
    const [y, mo] = st.day.split('-').map(Number), g = gridStart();
    const step = n => { const o = new Date(Date.UTC(y, mo - 1 + n, 1)); pick(o.toISOString().slice(0, 10)); };
    const wrap = h('div', { class: 'kc-desk' },
      h('div', { class: 'kc-bar' }, h('h2', { text: `${y}년 ${mo}월` }),
        key('kc-ik', '지난달', IC.l, () => step(-1)), key('kc-ik', '다음 달', IC.r, () => step(1)),
        h('button', { type: 'button', class: 'kc-tk', onclick: () => pick(today()), text: '오늘' }), chips()));
    const grid = h('div', { class: 'kc-mg', role: 'grid', 'aria-label': `${y}년 ${mo}월` }, ['월', '화', '수', '목', '금', '토', '일'].map(x => h('div', { class: 'h', role: 'columnheader', text: x })));
    const t = today();
    let d = g;
    for (let w = 0; w < 6; w++) {
      for (let i = 0; i < 7; i++, d = addD(d, 1)) {
        const day = d, list = shown(d).sort((a, b) => starOf(b) - starOf(a)), info = dayInfo(d), out = +d.slice(5, 7) !== mo;
        const c = h('button', { type: 'button', role: 'gridcell', class: ['cell', out ? 'out' : '', d === t ? 'today' : '', d < t ? 'past' : '', i >= 5 ? 'wkend' : ''].join(' '),
          'aria-pressed': d === st.day ? 'true' : 'false', 'data-d': d, 'aria-label': `${label(d)} ${WD[wday(d)]}요일${info ? ', ' + info.note : ''}, 일정 ${list.length}개`, onclick: () => pick(day) },
          h('span', { class: 'top1' }, h('span', { class: 'dnum num', text: String(+d.slice(8)) }), info ? h('span', { class: 'cl', text: info.note }) : null));
        list.slice(0, 3).forEach(e => c.append(h('span', { class: 'line s' + starOf(e) }, stars(starOf(e)), h('span', { class: 'ttl', text: (e.n && !e.grp ? e.n + ' ' : '') + e.title }))));
        if (list.length > 3) c.append(h('span', { class: 'plus', text: `+${list.length - 3}개` }));
        grid.append(c);
      }
      if (+d.slice(5, 7) !== mo && d > g) break;
    }
    grid.addEventListener('keydown', ev => {
      const map = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
      if (!(ev.key in map)) return;
      ev.preventDefault(); pick(addD(st.day, map[ev.key]), true);
    });
    wrap.append(h('div', { class: 'kc-card' }, loaded(g, addD(g, 41)) ? grid : message(g, addD(g, 41))));
    const side = h('aside', { class: 'kc-card kc-side', 'aria-label': '고른 날부터 7일' },
      h('div', { class: 'kc-sideh' }, h('h3', { text: '고른 날부터 7일' }), h('span', { class: 'kc-badge', text: '한국 시간' })),
      listFor(st.day, addD(st.day, 6), false));
    wrap.append(side);
    return wrap;
  }

  // ── draw · pick
  function snapshotNote() {
    return h('div', { class: 'kc-msg', role: 'status' }, h('b', { text: '증시 일정은 실시간 버전에서 볼 수 있어요' }),
      h('a', { class: 'kc-tk', href: (KH.LIVE_URL || 'https://panse.pages.dev/') + '#cal', target: '_blank', rel: 'noopener', text: '실시간 버전 열기' }));
  }
  function draw(animate) {
    const box = root(); if (!box || !st.on) return;
    const y = scrollY, focusD = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.d : null;
    const focusEv = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.id : null;
    box.replaceChildren(h('div', { class: 'kc' }, KH.MODE === 'snapshot' ? snapshotNote() : wide() ? desk() : phone()));
    footLine();
    if (KH.MODE === 'snapshot') return;
    requestAnimationFrame(() => placeInd(animate));
    if (focusD) { const b = box.querySelector(`[data-d="${focusD}"][aria-pressed="true"]`) || box.querySelector(`[data-d="${focusD}"]`); if (b) b.focus({ preventScroll: true }); }
    else if (focusEv) { const b = box.querySelector(`[data-id="${CSS.escape(focusEv)}"]`); if (b) b.focus({ preventScroll: true }); }
    if (Math.abs(scrollY - y) > 1) scrollTo(scrollX, y);
  }
  function pick(d, kb) {
    if (!d) return;
    const sameWeek = monday(d) === monday(st.day) && !wide();
    st.day = d;
    const [f, t] = rangeNow();
    const ready = loaded(f, t);
    if (sameWeek && ready) {
      const box = root(), list = box && box.querySelector('.kc-phone .kc-list');
      box.querySelectorAll('.kc-wk button').forEach(b => b.setAttribute('aria-pressed', b.dataset.d === d ? 'true' : 'false'));
      placeInd(true);
      if (kb) { const b = box.querySelector(`.kc-wk button[data-d="${d}"]`); if (b) b.focus(); }
      if (list && !reduced()) { list.classList.add('fading'); setTimeout(() => { swapList(); }, 120); }
      else swapList();
      return;
    }
    draw(false);
    ensure(f, t);
  }
  function swapList() {
    const box = root(), old = box && box.querySelector('.kc-phone .kc-list'); if (!old) return draw(false);
    const fresh = listFor(st.day, addD(st.day, 6), true);
    if (!reduced()) fresh.classList.add('fading');
    old.replaceWith(fresh);
    requestAnimationFrame(() => fresh.classList.remove('fading'));
  }

  // ── detail (a <dialog>: phone = bottom sheet, wider = floating panel)
  let dlg = null, opener = null;
  const fmtPeriod = p => !p ? '' : /^\d{4}-\d{2}-\d{2}$/.test(p) ? (p.endsWith('-01') ? `${p.slice(0, 4)}년 ${+p.slice(5, 7)}월` : `${p.slice(0, 4)}년 ${+p.slice(5, 7)}월 ${+p.slice(8)}일`)
    : /^\d{6}$/.test(p) ? `${p.slice(0, 4)}년 ${+p.slice(4)}월` : /^\d{4}Q\d$/.test(p) ? `${p.slice(0, 4)}년 ${p.slice(5)}분기` : /^\d{8}$/.test(p) ? `${+p.slice(4, 6)}월 ${+p.slice(6)}일 기준` : p;
  function why(e, s) {
    if (e.k === 'cb') return '기준금리를 정하거나 그 논의를 공개하는 날이라 금리 · 환율 · 주가가 함께 움직일 수 있어요.';
    if (e.k === 'mkt' && e.star === 3) return '선물과 옵션 만기가 겹치는 날이에요(3 · 6 · 9 · 12월 둘째 목요일). 장 마감 무렵 거래가 몰릴 수 있어요.';
    if (e.weekly) return '코스피200 위클리 옵션의 마지막 거래일이에요. 매주 월 · 목이라 기본으로는 숨겨요.';
    if (e.k === 'corp' && e.pct != null) return `풀리는 주식이 상장주식의 ${e.pct}%예요. 별 기준: 10% 이상 ★★★ · 3% 이상 ★★ · 그 밖 ★.${watched(e.c) ? ' 관심종목이라 하나 더했어요.' : ''}`;
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
  function openDetail(e, from) {
    opener = from || document.activeElement;
    if (!dlg) {
      dlg = h('dialog', { class: 'kc-dlg', 'aria-labelledby': 'kc-dt' });
      dlg.addEventListener('cancel', ev => { ev.preventDefault(); closeDetail(); });
      dlg.addEventListener('click', ev => { if (ev.target === dlg) closeDetail(); });
      document.body.append(dlg);
    }
    const s = starOf(e), past = isPast(e);
    const when = e.t ? `${label(e.d)} (${WD[wday(e.d)]}) ${e.t}` : `${label(e.d)} (${WD[wday(e.d)]}) · 종일`;
    const names = e.grp && e.codes ? e.codes.map(c => { const r = KH.stock(c); return { c, n: (r && r.n) || c }; }) : null;
    dlg.replaceChildren(...[       // native replaceChildren prints null as "null" — keep only real nodes
      h('span', { class: 'kc-grab', 'aria-hidden': 'true' }),
      h('div', { class: 'kc-sh' }, h('h3', { id: 'kc-dt' }, e.n && !e.grp ? h('span', { class: 'co', text: `${e.n} · ${e.c}` }) : null, e.title), h('button', { type: 'button', class: 'kc-x', 'aria-label': '닫기', onclick: closeDetail }, svg(IC.x))),
      h('dl', { class: 'kc-kv' },
        h('dt', { text: '언제' }), h('dd', { class: 'num' }, when, origLong(e) ? h('small', { text: origLong(e) }) : null),
        e.value ? [h('dt', { text: '발표값' }), h('dd', {}, e.value.text, e.value.p ? h('small', { text: `${fmtPeriod(e.value.p)} · ${e.value.src === 'ecos' ? '한국은행 ECOS' : 'FRED'}` }) : null)] : null,
        h('dt', { text: '중요도' }), h('dd', {}, stars(s), ' ', ['', '참고', '중요', '매우 중요'][s]),
        h('dt', { text: '분류' }), h('dd', {}, KINDS[e.k], e.sub ? h('small', { text: e.sub }) : null),
        h('dt', { text: '출처' }), h('dd', {}, SRC[e.src] || e.src, h('small', { text: srcNote(e) })),
        h('dt', { text: '상태' }), h('dd', { text: e.tentative ? `예정 — ${e.tentative}` : past ? '지났어요' : '예정' })),
      names ? h('div', { class: 'kc-codes', role: 'list', 'aria-label': '종목' }, names.map(x => h('button', { type: 'button', role: 'listitem', onclick: () => { closeDetail(true); if (KH.openStock) KH.openStock(x.c, {}); }, text: x.n }))) : null,
      h('p', { class: 'kc-why', text: why(e, s) }),
      h('div', { class: 'kc-acts' },
        e.url ? h('a', { href: e.url, target: '_blank', rel: 'noopener' }, svg(IC.ext), e.src === 'dart' ? 'DART 원문' : '원천 보기') : null,
        e.c && !e.grp && typeof KH.openStock === 'function' ? h('button', { type: 'button', onclick: () => { closeDetail(true); KH.openStock(e.c, {}); }, text: '종목 페이지' }) : null),
      h('p', { class: 'foot', text: '시각은 한국 시간이에요. 원천이 일정을 바꾸면 다음 갱신 때 바뀌어요.' })].filter(Boolean));
    if (!dlg.open) dlg.showModal();
    document.dispatchEvent(new CustomEvent('kh:worlddetail'));      // the phone dock hides while a sheet is open (template openWins)
    requestAnimationFrame(() => requestAnimationFrame(() => dlg.classList.add('on')));
    dlg.querySelector('.kc-x').focus();
  }
  function closeDetail(noFocus) {
    if (!dlg || !dlg.open) return;
    dlg.classList.remove('on');
    const done = () => { if (!dlg.classList.contains('on') && dlg.open) dlg.close(); document.dispatchEvent(new CustomEvent('kh:worlddetail')); };
    if (reduced()) done(); else setTimeout(done, 260);
    if (!noFocus && opener && opener.isConnected) opener.focus({ preventScroll: true });
  }

  // ── footer line (above the disclaimer, §3-30): the template's renderFooter() puts <p id="foot-cal"> with footText() on the 일정 tab
  const FOOT = '일정: 한국은행 경제통계 공표일정 · 국가데이터처 보도계획 · 미국 지표는 FRED® 발표 일정(This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.) · 발표값은 한국은행 ECOS · FRED · 금통위 · FOMC · 휴장은 한국은행 · 연준 · 한국거래소 공지를 보고 직접 넣어요 · 회사 일정: 금융감독원 DART · 금융위원회(공공데이터포털). 시각은 모두 한국 시간이고, 일정은 원천 사정으로 바뀔 수 있어요.';
  function footLine() { const p = document.getElementById('foot-cal'); if (p && st.on) p.textContent = FOOT; }

  // ── lifecycle
  function onResize() { if (!st.on) return; const w = wide(); if (w !== st.wasWide) { st.wasWide = w; draw(false); const [f, t] = rangeNow(); ensure(f, t); } else placeInd(false); }
  function show() {
    st.on = true; st.wasWide = wide();
    if (!st.day) st.day = today();
    draw(false);
    if (KH.MODE === 'snapshot') return;
    const [f, t] = rangeNow();
    ensure(f, t);
    clearInterval(st.timer);
    st.timer = setInterval(() => { if (!document.hidden && st.on) { const [a, b] = rangeNow(); ensure(a, b); } }, 60e3);
  }
  function hide() {
    st.on = false;
    clearInterval(st.timer); st.timer = null;
    if (dlg && dlg.open) { dlg.classList.remove('on'); dlg.close(); }
  }
  addEventListener('resize', onResize);
  document.addEventListener('kh:watch', () => { if (st.on) draw(false); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && st.on) { const [a, b] = rangeNow(); ensure(a, b); } });
  window.KHCal = { show, hide, isOn: () => st.on, detailOpen: () => !!(dlg && dlg.open), footText: () => FOOT };
})();
