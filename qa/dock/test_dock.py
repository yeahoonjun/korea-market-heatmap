#!/usr/bin/env python3
"""The phone dock (아래 막대) and its 🔍 search sheet on the design standard (design.md §2 – §8, docs/standards/dock.md, ux/std-dock).

  python3 qa/dock/test_dock.py [page] [motion] [sheet] [rules]      (no argument = all four)

Serves the live build (web/) with qa/float/mock_float.py on DOCK_QA_PORT (default 9060; 9060–9069 only), one Chrome, stops the mock
with fuser -k. Checks:
page    four themes × 360 × 780 · 390 × 844 (touch, DPR 2): hidden on the first screen; up once the map has gone by (never over it — the
        map's bottom ≥ 8px above the dock); panel 56 · gap 8 · sides 8; cells 44, 🔍 44 × 44; the swipe area ≥ 12px from both screen
        edges; no light: the dock has no backdrop blur, no gradient, no zero-offset blurred shadow (glow) — in the glass themes no blur
        either, but ④ 리퀴드 글라스 (AGENTS §3-38) gives the dock itself the card sheen and the 1.25px ring (no part inside it); the
        glass themes keep their material on the search sheet (--sheet-bg's sheen = a gradient, the 1px inset edge, the blur) while
        기본 · 신문 have none; type on the seven steps (≥ 11px); no amber but the ★ (켜짐) and the focus ring; the 🔍 and × icons
        1.75px (non-scaling); every number in the cells whole (the mover's name gives way first, dock.md §4); the sheet's rows
        --h-row (44) with --r-row corners; nothing wider than the screen.
motion  the dock comes up with `open` + `fade` and leaves with `close` (spring curves, not the old beziers); 줄이기 → at once; 화려하게
        the cells rise 4px 40 ms apart the session's first time only; a new index value → 기본 KH.ui.swap (from below when it rose),
        화려하게 KH.ui.roll (drums, the text = the value); the same value again → nothing moves; a tab switch (another index in the cell)
        → written at once; new counts move the 등락 분포 bar with `value`; ← → flip the page with KH.spring (snapping off while it
        moves, the page and its dot land), a held key → at once; the 🔍 key sinks 1px with --key-dn while pressed.
sheet   🔍 → the sheet comes up (`open`), focus in the box, the page stays where it was read; "삼성" → rows; one highlight plate under
        the highlighted row, ↓ moves it with `hl` (mid-way, then on the row), a held ↓ puts it there at once; Esc → closed, focus back
        on 🔍, the page still where it was; × closes; drag the grip down → dismissed.
rules   what dock.md decided stays: shows only after the map, hides while a sheet is open and comes back; page 1 = 지수 + 등락 분포,
        page 2 = 관심 + the other market's index, 2 dots; 막대 내용 끔 → a 56 × 56 panel with 🔍 only; 돋보기 왼쪽 → the key on the left
        and the swipe area still ≥ 12px from the edge; the footer keeps 72px of room under the page.
Console errors 0 over all. Exit 1 on a fail. Timing samples are loose (a busy machine): re-run a failing timing check once.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('DOCK_QA_PORT', 9060))
assert 9060 <= PORT <= 9069 or 9080 <= PORT <= 9089, 'ports 9060–9069 (or 9080–9089: ux/glass-liquid)'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
SIZES = ((360, 780), (390, 844))
WATCH = {'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': ['005930', '000660', '035420', '005380']}], 'active': 'all'}
FAILS, PASSES, ERRS = [], [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w=390, h=844, theme='base', motion='standard', extra=None, wait=2200, routes=None):
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2)
    for pat, body in (routes or {}).items():
        ctx.route(pat, (lambda b: lambda r: r.fulfill(status=200, content_type='application/json', body=b))(body))   # one-argument handler
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': 'K', 'watchGroups': WATCH}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{motion}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_timeout(wait)
    return ctx, pg


# scroll so the map's bottom sits `past` px above the dock's line (innerHeight − 72); negative = not yet past
SCROLL = """past => { const m = document.getElementById('map').getBoundingClientRect(); scrollTo(0, Math.max(0, Math.round(m.bottom + scrollY - innerHeight + 72 + past))); }"""
UP = "() => getComputedStyle(document.querySelector('.dock')).visibility === 'visible' && document.querySelector('.dock').classList.contains('on')"


def reveal(pg, past=24, wait=900):
    pg.evaluate(SCROLL, past)
    pg.wait_for_timeout(wait)
    return pg.evaluate(UP)


GEO = r"""() => {
  const d = document.querySelector('.dock'), r = d.getBoundingClientRect(), map = document.getElementById('map').getBoundingClientRect();
  const cells = [...d.querySelectorAll('.dk-pg')[0].querySelectorAll('.dk-c')].map(c => Math.round(c.getBoundingClientRect().height));
  const k = d.querySelector('.dk-k').getBoundingClientRect(), pw = d.querySelector('.dk-pages').getBoundingClientRect();
  return { h: Math.round(r.height), gap: Math.round(innerHeight - r.bottom), left: Math.round(r.left), right: Math.round(innerWidth - r.right),
    cells, key: [Math.round(k.width), Math.round(k.height)], swipeL: Math.round(pw.left), swipeR: Math.round(innerWidth - pw.right),
    mapGap: Math.round(r.top - map.bottom), aria: d.getAttribute('aria-hidden') };
}"""

# computed look of the dock and the sheet: light / gradient / glow / blur / type / amber / icons
LOOK = r"""() => {
  const d = document.querySelector('.dock'), cs = getComputedStyle(d), rs = getComputedStyle(document.documentElement);
  const probe = document.createElement('i'); document.body.append(probe);
  const rgb = v => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const amber = new Set([rgb(rs.getPropertyValue('--acc').trim()), rgb(rs.getPropertyValue('--acc-fill').trim()), rgb('#ffb547')]);
  probe.remove();
  const glow = v => (v || '').split(/,(?![^(]*\))/).some(l => { if (/inset/.test(l)) return false; const n = (l.match(/-?[\d.]+px/g) || []).map(parseFloat); return n.length >= 3 && n[0] === 0 && n[1] === 0 && n[2] > 0; });
  const all = [d, ...d.querySelectorAll('*')].filter(e => !(e instanceof SVGElement) || e.tagName === 'svg');
  const fs = new Set(), amb = [], grads = [], glows = [];
  for (const e of all) {
    const c = getComputedStyle(e);
    if (e.textContent.trim() && !(e instanceof SVGElement)) fs.add(parseFloat(c.fontSize));
    for (const p of ['color', 'backgroundColor', 'borderTopColor']) if (amber.has(c[p]) && !e.matches('.st') && !(p === 'borderTopColor' && c.borderTopWidth === '0px')) amb.push((e.className.baseVal ?? e.className) + ' ' + p);
    if (/gradient/.test(c.backgroundImage)) grads.push(e.className);
    if (glow(c.boxShadow)) glows.push(e.className);
  }
  const ic = sel => { const s = document.querySelector(sel); if (!s) return null; const ps = [...s.querySelectorAll('path,circle')]; return ps.map(p => [p.getAttribute('stroke-width') || s.getAttribute('stroke-width'), p.getAttribute('vector-effect')]); };
  const sh = document.querySelector('.ssheet');
  const ss = sh ? (() => { const c = getComputedStyle(sh); return { blur: c.backdropFilter, bg: c.backgroundImage, sh: c.boxShadow }; })() : null;
  return { blur: cs.backdropFilter, bg: cs.backgroundImage, glow: glow(cs.boxShadow), fs: [...fs].sort((a, b) => a - b), amb, grads, glows,
    key: ic('.dk-k svg'), x: ic('.ss-x svg'), ssIcon: ic('.ss-top .search svg'), ss };
}"""

OVER = r"""() => {
  const vw = innerWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break; } p = p.parentElement; }
    if (!clipped && getComputedStyle(e).visibility !== 'hidden') out.push((e.id ? '#' + e.id : String(e.className.baseVal ?? e.className).split(' ')[0] || e.tagName) + ' ' + Math.round(r.right));
  }
  return out.slice(0, 8);
}"""

SCALE = {11, 12, 13, 14, 16, 20, 26}
# numbers cut by an ellipsis (both pages are laid out; page 2 only scrolled aside)
CUT = r"""() => [...document.querySelectorAll('.dk-c .val:not(.dk-empty), .dk-c .p, .dk-c .mvp, .dk-c .cnt:not([hidden]), .dk-n > span')]
  .filter(e => e.textContent && e.scrollWidth > e.clientWidth + .5).map(e => e.closest('.dk-c').dataset.k + ' ' + e.className + ' ' + e.textContent)"""


def page(br):
    for w, h in SIZES:
        for th in THEMES:
            # 유리 흐림 켜기: headless Chrome trips the glass's frame watchdog (data-blur off = the opaque fallback, design.md §5)
            ctx, pg = open_page(br, w, h, theme=th, extra={'set.glassBlur': 'on'} if th.startswith('glass') else None)
            tag = f'{w} {th}'
            first = pg.evaluate("() => ({ vis: getComputedStyle(document.querySelector('.dock')).visibility, aria: document.querySelector('.dock').getAttribute('aria-hidden') })")
            check(f'page [{tag}]: hidden on the first screen (visibility hidden, aria-hidden)', first == {'vis': 'hidden', 'aria': 'true'}, first)
            up = reveal(pg)
            g = pg.evaluate(GEO)
            check(f'page [{tag}]: up once the map has gone by, never over it (map bottom {g["mapGap"]}px above)', up and g['mapGap'] >= 8 and g['aria'] == 'false', (up, g))
            check(f'page [{tag}]: panel 56 · gap 8 · sides 8 · cells 44 · 🔍 44 × 44', (g['h'], g['gap'], g['left'], g['right']) == (56, 8, 8, 8) and g['cells'] == [44, 44] and g['key'] == [44, 44], g)
            check(f'page [{tag}]: the swipe area ≥ 12px from both screen edges ({g["swipeL"]} · {g["swipeR"]})', g['swipeL'] >= 12 and g['swipeR'] >= 12, g)
            cut = pg.evaluate(CUT)
            check(f'page [{tag}]: every number in the cells is whole (no ellipsis — the mover\'s name gives way first)', not cut, cut)
            pg.click('.dk-k'); pg.wait_for_timeout(600)
            pg.keyboard.type('삼성'); pg.wait_for_timeout(400)
            lk = pg.evaluate(LOOK)
            ss = lk['ss']
            if th.startswith('glass'):
                # ④ 리퀴드 글라스 (AGENTS §3-38): the dock is thick glass to look at — the card sheen in its fill and the 1.25px ring, no blur
                ring = pg.evaluate("() => { const a = getComputedStyle(document.querySelector('.dock'), '::after'); return a.backgroundImage.slice(0, 30) + ' ' + a.paddingTop; }")
                check(f'page [{tag}]: the glass dock (④) — no blur, no glow, the card sheen on the dock only (radial), the 1.25px ring',
                      lk['blur'] == 'none' and lk['bg'].startswith('radial-gradient') and not lk['glow'] and len(lk['grads']) == 1 and str(lk['grads'][0]).split()[0] == 'dock' and not lk['glows'] and ring.startswith('linear-gradient(135deg') and ring.endswith('1.25px'), (lk, ring))
                check(f'page [{tag}]: glass material kept on the search sheet — the sheen (gradient), the 1px inset edge, the blur',
                      ss and 'blur(' in ss['blur'] and 'gradient' in ss['bg'] and 'inset' in ss['sh'], ss)
            else:
                check(f'page [{tag}]: no light on the dock — no blur, no gradient, no glow (dock and every part)', lk['blur'] == 'none' and lk['bg'] == 'none' and not lk['glow'] and not lk['grads'] and not lk['glows'], lk)
                check(f'page [{tag}]: the search sheet is flat (no gradient, no blur)', ss and ss['bg'] == 'none' and ss['blur'] == 'none', ss)
            check(f'page [{tag}]: type on the seven steps, nothing under 11px {lk["fs"]}', set(lk['fs']) <= SCALE and min(lk['fs']) >= 11, lk['fs'])
            check(f'page [{tag}]: no amber in the dock but the ★ (켜짐)', not lk['amb'], lk['amb'])
            ok_ic = lambda v: v and all(sw == '1.75' and ve == 'non-scaling-stroke' for sw, ve in v)
            check(f'page [{tag}]: 🔍 · the sheet\'s 🔍 · × drawn 1.75px (non-scaling)', ok_ic(lk['key']) and ok_ic(lk['x']) and ok_ic(lk['ssIcon']), (lk['key'], lk['x'], lk['ssIcon']))
            rows = pg.evaluate("() => [...document.querySelectorAll('.ss-list > button')].slice(0, 3).map(b => [Math.round(b.getBoundingClientRect().height), getComputedStyle(b).borderTopLeftRadius])")
            r_row = pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--r-row').trim()")
            check(f'page [{tag}]: sheet rows --h-row 44 with --r-row corners ({r_row})', rows and all(x == [44, r_row] for x in rows), rows)
            ov = pg.evaluate(OVER)
            check(f'page [{tag}]: nothing past the screen edge (dock up, sheet open)', not ov, ov)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
            ov = pg.evaluate(OVER)
            check(f'page [{tag}]: nothing past the screen edge (sheet closed)', not ov, ov)
            ctx.close()


TRANS = """() => { const c = getComputedStyle(document.querySelector('.dock')); return { prop: c.transitionProperty, dur: c.transitionDuration, ease: c.transitionTimingFunction }; }"""
TOK = """n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()"""
TY = "() => { const t = getComputedStyle(document.querySelector('.dock')).transform; return t === 'none' ? 0 : +t.split(',')[5].replace(')', ''); }"

OLD_CLOSE = json.dumps({'date': '2020-01-02', 'asOf': '2020-01-02T15:30:00+09:00', 'lim': True, 'c': {}})
FEED = r"""async ({dv, flip}) => {
  const q = await (await fetch('/api/quotes')).json();
  if (dv) { q.index.KOSPI.value = +q.index.KOSPI.value + dv; q.index.KOSPI.change = +q.index.KOSPI.change + dv; q.index.KOSPI.ratio = +q.index.KOSPI.ratio + dv / 50; }
  if (flip) { let n = 0; for (const s of q.stocks) { if (n >= flip) break; if (s.m === 'K' && +s.r < 0) { s.r = Math.abs(+s.r) + 0.5; s.d = Math.abs(+s.d) + 1; n++; } } }
  q.asOf = new Date(Date.now() + (window.__feedN = (window.__feedN || 0) + 1) * 60000).toISOString();
  return KH.feed(q);
}"""
VAL = r"""() => { const v = document.querySelector('.dk-c[data-k="ix"] .val'); const an = v.getAnimations({ subtree: true });
  return { text: v.textContent, sw: v.classList.contains('sw-go'), drums: v.querySelectorAll('.rc').length, n: an.length,
    inn: an.map(a => (a.effect.getKeyframes()[0] || {}).transform).filter(Boolean) }; }"""


def motion(br):
    # ── up / away: spring curves; 기본 moves, 줄이기 lands at once ──
    # (an older day's close.json: the 등락 분포 counts come from the map's own quotes, so a fed quote moves them)
    ctx, pg = open_page(br, routes={'**/data/close.json': OLD_CLOSE})
    off = pg.evaluate(TRANS)
    reveal(pg, wait=60)
    on = pg.evaluate(TRANS)
    toks = {n: pg.evaluate(TOK, n) for n in ('--sp-open-dur', '--sp-fade-dur', '--sp-close-dur')}
    check('motion: away = `close` (transform · opacity), up = `open` (transform) + `fade` (opacity) — spring linear() curves',
          'linear(' in off['ease'] and 'linear(' in on['ease'] and 'cubic-bezier' not in on['ease'] + off['ease']
          and on['dur'].split(', ')[:2] == [f"{float(toks['--sp-open-dur'][:-2]) / 1000:g}s", f"{float(toks['--sp-fade-dur'][:-2]) / 1000:g}s"]
          and off['dur'].split(', ')[0] == f"{float(toks['--sp-close-dur'][:-2]) / 1000:g}s", (off, on, toks))
    ys = []
    pg.evaluate(SCROLL, -200); pg.wait_for_timeout(700)
    t0 = time.time(); pg.evaluate(SCROLL, 24)
    for t in (40, 120, 700):
        pg.wait_for_timeout(max(0, int(t - (time.time() - t0) * 1000))); ys.append(pg.evaluate(TY))
    check(f'motion: 기본 — the dock rises (moving at 40 · 120 ms, in place by 700 ms) {[round(y, 1) for y in ys]}', ys[0] > 1 and ys[1] < ys[0] + .01 and abs(ys[2]) < .5, ys)
    # page flip by key: KH.spring lead, snapping off while it moves, page and dot land
    pg.evaluate("() => { const c = document.querySelectorAll('.dk-pg')[0].querySelectorAll('.dk-c'); c[c.length - 1].focus(); }")
    fl = pg.evaluate(r"""async () => { const P = document.querySelector('.dk-pages'), w = P.clientWidth, out = { w };
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
      await new Promise(r => setTimeout(r, 60)); out.mid = P.scrollLeft; out.flip = P.classList.contains('dk-flip'); out.snapMid = getComputedStyle(P).scrollSnapType;
      await new Promise(r => setTimeout(r, 800)); out.end = P.scrollLeft; out.flipEnd = P.classList.contains('dk-flip'); out.snapEnd = getComputedStyle(P).scrollSnapType;
      out.dots = [...document.querySelectorAll('.dk-dots i')].map(i => i.classList.contains('on')); out.focus = document.activeElement.dataset.k;
      return out; }""")
    check(f'motion: → flips the page with KH.spring (mid-way at 60 ms, snapping off) and lands on page 2 with its dot', 0 < fl['mid'] < fl['w'] and fl['flip'] and fl['snapMid'] == 'none'
          and abs(fl['end'] - fl['w']) < 1 and not fl['flipEnd'] and 'mandatory' in fl['snapEnd'] and fl['dots'] == [False, True] and fl['focus'] == 'watch', fl)
    held = pg.evaluate(r"""() => { const P = document.querySelector('.dk-pages'); document.querySelectorAll('.dk-pg')[1].querySelector('.dk-c').focus();
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true, repeat: true })); return { sl: P.scrollLeft, flip: P.classList.contains('dk-flip') }; }""")
    check('motion: a held ← flips at once (no spring)', held['sl'] == 0 and not held['flip'], held)
    # 🔍 pressed: 1px down, --key-dn, darker
    pg.focus('.dk-k'); pg.keyboard.down('Space'); pg.wait_for_timeout(50)
    pr = pg.evaluate("() => { const k = document.querySelector('.dk-k'), c = getComputedStyle(k); return { t: c.transform, sh: c.boxShadow, f: c.filter, cls: k.className }; }")
    pg.keyboard.up('Space'); pg.wait_for_timeout(600)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    check('motion: the 🔍 key sinks 1px while pressed (--key-dn, the theme\'s press filter)', pr['t'] == 'matrix(1, 0, 0, 1, 0, 1)' and pr['f'] != 'none', pr)
    # values: the first draw sat at once; a new index value swaps from below (기본); the same value again moves nothing
    pg.wait_for_timeout(300)
    v0 = pg.evaluate(VAL)
    check('motion: the first draw sits at once (no swap, no drum)', not v0['sw'] and v0['n'] == 0, v0)
    pg.evaluate(FEED, {'dv': 12.34, 'flip': 0}); pg.wait_for_timeout(40)
    v1 = pg.evaluate(VAL)
    check(f'motion: 기본 — a risen index value swaps in from below ({v0["text"]} → {v1["text"]})', v1['sw'] and v1['drums'] == 0 and v1['n'] == 2 and 'translateY(4px)' in v1['inn'] and v1['text'] != v0['text'], v1)
    pg.wait_for_timeout(500)
    pg.evaluate(FEED, {'dv': 12.34, 'flip': 0}); pg.wait_for_timeout(40)     # = the same index value again (the feed adds to the mock's base)
    v2 = pg.evaluate(VAL)
    check('motion: the same value again → nothing moves', not v2['sw'] and v2['n'] == 0 and v2['text'] == v1['text'], v2)
    # 등락 분포: new counts swap; the bar's parts follow with `value`
    br_ = pg.evaluate(r"""() => ({ up: document.querySelector('.dk-c[data-k="brd"] .dk-n .up').textContent, tr: getComputedStyle(document.querySelector('.dk-c[data-k="brd"] .dk-bar i')).transitionProperty,
      ease: getComputedStyle(document.querySelector('.dk-c[data-k="brd"] .dk-bar i')).transitionTimingFunction })""")
    pg.evaluate(FEED, {'dv': 12.34, 'flip': 25}); pg.wait_for_timeout(60)
    br2 = pg.evaluate(r"""() => { const c = document.querySelector('.dk-c[data-k="brd"]'), u = c.querySelector('.dk-n .up'); const bars = [...c.querySelectorAll('.dk-bar i')].flatMap(i => i.getAnimations());
      return { up: u.textContent, sw: u.classList.contains('sw-go'), inn: u.getAnimations({ subtree: true }).map(a => (a.effect.getKeyframes()[0] || {}).transform).filter(Boolean),
        bars: bars.map(a => a.transitionProperty) }; }""")
    check(f'motion: new 등락 분포 counts swap the way they went ({br_["up"]} → {br2["up"]}) and the bar follows with `value`',
          br2['up'] != br_['up'] and br2['sw'] and 'translateY(4px)' in br2['inn'] and 'flex-grow' in br_['tr'] and 'linear(' in br_['ease'] and 'flex-grow' in br2['bars'], (br_, br2))
    # a tab switch puts another index in the cell (탭 따라): at once
    pg.wait_for_timeout(600)
    pg.evaluate("() => document.querySelector('.tabs button[data-mkt=\"Q\"]').click()"); pg.wait_for_timeout(200)
    reveal(pg, wait=700)
    v3 = pg.evaluate(VAL)
    nm = pg.evaluate("() => document.querySelector('.dk-c[data-k=\"ix\"] .nm').textContent")
    check(f'motion: a tab switch (코스닥 in the cell) writes the value at once', nm == '코스닥' and not v3['sw'] and v3['n'] == 0, (nm, v3))
    ctx.close()

    # ── 줄이기: up at once ──
    ctx, pg = open_page(br, motion='reduced')
    pg.evaluate(SCROLL, 24); pg.wait_for_timeout(80)
    r = pg.evaluate("() => { const d = document.querySelector('.dock'), c = getComputedStyle(d); return { on: d.classList.contains('on'), op: c.opacity, t: c.transform, dur: c.transitionDuration }; }")
    check('motion: 줄이기 — up at once (every length 0)', r['on'] and r['op'] == '1' and r['t'] == 'none' and set(r['dur'].split(', ')) == {'0s'}, r)
    ctx.close()

    # ── 화려하게: the cells rise the session's first time only; a new value rolls on drums ──
    ctx, pg = open_page(br, motion='fancy')
    pg.evaluate(SCROLL, 24); pg.wait_for_timeout(60)
    a1 = pg.evaluate("() => [...document.querySelectorAll('.dk-pg')[0].querySelectorAll('.dk-c')].map(c => c.getAnimations().map(a => [a.animationName, a.effect.getTiming().delay]))")
    pg.wait_for_timeout(700)
    pg.evaluate(SCROLL, -200); pg.wait_for_timeout(700)
    pg.evaluate(SCROLL, 24); pg.wait_for_timeout(60)
    a2 = pg.evaluate("() => [...document.querySelectorAll('.dk-pg')[0].querySelectorAll('.dk-c')].flatMap(c => c.getAnimations().map(a => a.animationName))")
    check('motion: 화려하게 — the cells rise 4px, 40 ms apart, the first time up; not again in the session',
          [x[0][0] if x else None for x in a1] == ['dkRise', 'dkRise'] and [x[0][1] for x in a1] == [0, 40] and not a2, (a1, a2))
    pg.wait_for_timeout(700)
    pg.evaluate(FEED, {'dv': 0.11, 'flip': 0}); pg.wait_for_timeout(40)
    v = pg.evaluate(VAL)
    check(f'motion: 화려하게 — a new index value rolls the changed digits (the text = the value: {v["text"]})', v['drums'] >= 1 and not v['sw'], v)
    ctx.close()


PLATE = r"""() => { const hl = document.querySelector('.ss-hl'), b = document.querySelector('.ss-list > button[aria-selected="true"]');
  if (!hl || !b) return null; const a = hl.getBoundingClientRect(), r = b.getBoundingClientRect();
  return { dy: Math.round(a.top - r.top), dh: Math.round(a.height - r.height), id: b.id, act: document.getElementById('dkq').getAttribute('aria-activedescendant'),
    op: getComputedStyle(hl).opacity, ease: getComputedStyle(hl).transitionTimingFunction }; }"""


def sheet(br):
    ctx, pg = open_page(br)
    reveal(pg)
    y0 = pg.evaluate('scrollY')
    pg.evaluate("document.querySelector('.dk-k').click()")
    tr = []
    for t in (30, 700):
        pg.wait_for_timeout(t if not tr else t - 30)
        tr.append(pg.evaluate("() => { const t = getComputedStyle(document.querySelector('.ssheet')).translate; return t === 'none' ? 0 : parseFloat(t.split(' ')[1] || 0); }"))
    st = pg.evaluate("() => ({ focus: document.activeElement.id, y: scrollY, dock: document.querySelector('.dock').classList.contains('on') })")
    check(f'sheet: 🔍 → up from the bottom edge (`open`: {tr}), focus in the box, the page stays where it was, the dock steps aside',
          tr[0] > 5 and abs(tr[1]) < 1 and st['focus'] == 'dkq' and abs(st['y'] - y0) < 2 and not st['dock'], (tr, st, y0))
    pg.keyboard.type('삼성'); pg.wait_for_timeout(400)
    p0 = pg.evaluate(PLATE)
    n = pg.evaluate("() => document.querySelectorAll('.ss-list > button').length")
    check(f'sheet: "삼성" → {n} rows, one plate under the highlighted row (row 1), aria-activedescendant on it',
          n >= 3 and p0 and p0['dy'] == 0 and p0['dh'] == 0 and p0['id'] == 'dksg-0' and p0['act'] == 'dksg-0' and p0['op'] == '1' and 'linear(' in p0['ease'], p0)
    mid = pg.evaluate(r"""async () => { document.getElementById('dkq').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
      await new Promise(r => setTimeout(r, 50)); const hl = document.querySelector('.ss-hl').getBoundingClientRect(), b0 = document.getElementById('dksg-0').getBoundingClientRect(), b1 = document.getElementById('dksg-1').getBoundingClientRect();
      return { at: Math.round(hl.top), r0: Math.round(b0.top), r1: Math.round(b1.top) }; }""")
    pg.wait_for_timeout(600)
    p1 = pg.evaluate(PLATE)
    check(f'sheet: ↓ moves the plate with `hl` (mid-way at 50 ms {mid}, then on row 2)', mid['r0'] < mid['at'] < mid['r1'] and p1['dy'] == 0 and p1['id'] == 'dksg-1' and p1['act'] == 'dksg-1', (mid, p1))
    held = pg.evaluate(r"""() => { document.getElementById('dkq').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, repeat: true }));
      const hl = document.querySelector('.ss-hl').getBoundingClientRect(), b = document.getElementById('dksg-2').getBoundingClientRect(); return Math.round(hl.top - b.top); }""")
    check('sheet: a held ↓ puts the plate on its row at once', held == 0, held)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(700)
    st = pg.evaluate("() => ({ focus: document.activeElement.className, y: scrollY, d: getComputedStyle(document.querySelector('.ssheet')).display, dock: document.querySelector('.dock').classList.contains('on') })")
    check('sheet: Esc → closed, focus back on 🔍, the page still where it was, the dock back', st['d'] == 'none' and 'dk-k' in st['focus'] and abs(st['y'] - y0) < 2 and st['dock'], (st, y0))
    pg.evaluate("document.querySelector('.dk-k').click()"); pg.wait_for_timeout(600)
    pg.click('.ss-x'); pg.wait_for_timeout(700)
    d = pg.evaluate("() => getComputedStyle(document.querySelector('.ssheet')).display")
    check('sheet: × closes it', d == 'none', d)
    pg.evaluate("document.querySelector('.dk-k').click()"); pg.wait_for_timeout(700)
    g = pg.evaluate("() => { const r = document.querySelector('.ssheet .grab').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
    cdp = ctx.new_cdp_session(pg)
    x, y = g
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    for i in range(1, 9):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y + 45 * i}]}); pg.wait_for_timeout(12)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    pg.wait_for_timeout(900)
    k = pg.evaluate("() => ({ d: getComputedStyle(document.querySelector('.ssheet')).display, s: getComputedStyle(document.querySelector('.ss-scrim')).display })")
    check('sheet: drag the grip down → dismissed (sheet and scrim gone)', k == {'d': 'none', 's': 'none'}, k)
    ctx.close()


def rules(br):
    ctx, pg = open_page(br)
    hid = reveal(pg, past=-30, wait=800)
    check('rules: not up while the map still reaches the dock\'s line', not hid)
    up = reveal(pg)
    lay = pg.evaluate("() => [...document.querySelectorAll('.dk-pg')].map(p => [...p.querySelectorAll('.dk-c')].map(c => c.dataset.k + (c.dataset.key ? ':' + c.dataset.key : '')))")
    dots = pg.evaluate("() => document.querySelectorAll('.dk-dots i').length")
    check(f'rules: page 1 = 지수 + 등락 분포, page 2 = 관심 + the other index, 2 dots {lay}', up and lay == [['ix:KOSPI', 'brd'], ['watch', 'ix2:KOSDAQ']] and dots == 2, lay)
    pg.click('#setBtn'); pg.wait_for_timeout(700)
    hidden = pg.evaluate("() => !document.querySelector('.dock').classList.contains('on')")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(900)
    back = pg.evaluate(UP)
    check('rules: hides while a sheet (표시 설정) is open, back after it closes', hidden and back, (hidden, back))
    room = pg.evaluate("() => parseFloat(getComputedStyle(document.querySelector('footer')).paddingBottom)")
    check(f'rules: the footer keeps the dock\'s room under the page (24 + 72 = {room})', room >= 96, room)
    ctx.close()
    ctx, pg = open_page(br, extra={'set.dock': False})
    reveal(pg)
    k = pg.evaluate("() => { const d = document.querySelector('.dock'), r = d.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), right: Math.round(innerWidth - r.right), pw: getComputedStyle(d.querySelector('.dk-pw')).display, key: !!d.querySelector('.dk-k').offsetWidth }; }")
    check('rules: 막대 내용 끔 → a 56 × 56 panel with 🔍 only, on the right', k == {'w': 56, 'h': 56, 'right': 8, 'pw': 'none', 'key': True}, k)
    ctx.close()
    ctx, pg = open_page(br, extra={'set.dockSide': 'left'})
    reveal(pg)
    s = pg.evaluate("() => { const k = document.querySelector('.dk-k').getBoundingClientRect(), p = document.querySelector('.dk-pages').getBoundingClientRect(); return { keyL: Math.round(k.left), pagesL: Math.round(p.left), pagesR: Math.round(innerWidth - p.right) }; }")
    check(f'rules: 돋보기 왼쪽 → the key on the left, the swipe area ≥ 12px from the edge {s}', s['keyL'] < s['pagesL'] and s['pagesR'] >= 12, s)
    ctx.close()


def main():
    parts = set(sys.argv[1:]) or {'page', 'motion', 'sheet', 'rules'}
    start_mock()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for name, fn in (('page', page), ('motion', motion), ('sheet', sheet), ('rules', rules)):
                if name in parts:
                    fn(br)
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check(f'console errors: {len(ERRS)}', not ERRS, ERRS[:6])
    print(f'\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks passed')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
