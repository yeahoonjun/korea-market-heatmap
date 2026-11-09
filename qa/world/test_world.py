#!/usr/bin/env python3
"""QA for src/world (해외 · 원자재 tabs) on the built pages.

  python3 scripts/build_page.py && python3 qa/world/test_world.py [--real]

Starts qa/world/mock_api.py on :8803 (serves web/ + /api/world*), injects qa/world/shim.js for the §3-4 template hooks
until they are merged, and writes screenshots to qa/shots/world/. --real also runs a smoke pass against the local Worker
(NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8803/ PORT=8802 node worker/dev/serve.mjs, started and stopped here).
Exit code 1 if any check fails.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHOTS = ROOT / 'qa/shots/world'
SHOTS.mkdir(parents=True, exist_ok=True)
PORT, REAL_PORT = 8803, 8802
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SHIM = (HERE / 'shim.js').read_text(encoding='utf-8')
FIX = {k: json.loads((HERE / f'fixtures/world_{k}.json').read_text(encoding='utf-8')) for k in ('index', 'commodity')}
COUNT = {k: sum(len(g['items']) for g in v['groups']) for k, v in FIX.items()}
WIDTHS = {360: 740, 390: 844, 768: 1024, 1280: 800, 1920: 1080}
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def api(path, base=LIVE):
    with NOPROXY.open(base.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


class Errors:
    def __init__(self):
        self.items, self.expected, self.expect_net = [], [], False

    def on_console(self, m):
        if m.type != 'error':
            return
        if self.expect_net and m.text.startswith('Failed to load resource'):
            self.expected.append(m.text)
        else:
            self.items.append(m.text[:160])

    def attach(self, page):
        page.on('console', self.on_console)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


ERR = Errors()


def open_page(browser, url, width=1440, height=900, mobile=False, reduced=False, clock=False):
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    ctx.add_init_script(SHIM)
    page = ctx.new_page()
    if clock:
        page.clock.install()
    ERR.attach(page)
    page.goto(url)
    return ctx, page


def wait_world(page, sel='#world .kw-tile', timeout=8000):
    page.wait_for_selector(sel, timeout=timeout)
    page.wait_for_timeout(350)


# ── page-side probes ──
LABELS_JS = r"""
() => {
  const out = []; let labs = 0, chips = 0, tiles = 0;
  const inside = (r, tr, tol) => r.left >= tr.left - tol && r.right <= tr.right + tol && r.top >= tr.top - tol && r.bottom <= tr.bottom + tol;
  const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
  for (const t of document.querySelectorAll('#world .kw-tile')) {
    tiles++;
    const tr = t.getBoundingClientRect();
    const lab = t.querySelector('.kw-lab'), chip = t.querySelector('.kw-chip');
    const rects = [];
    if (lab && !lab.hidden) {
      labs++;
      const w = document.createTreeWalker(lab, NodeFilter.SHOW_TEXT); let tn;
      while ((tn = w.nextNode())) {
        if (!tn.textContent.trim() || tn.parentElement.closest('[hidden]')) continue;
        const rg = document.createRange(); rg.selectNodeContents(tn);
        for (const rr of rg.getClientRects()) {
          rects.push(rr);
          if (!inside(rr, tr, 1.5)) out.push(`${t.dataset.k} '${tn.textContent}' [${rr.left.toFixed(0)},${rr.top.toFixed(0)},${rr.right.toFixed(0)},${rr.bottom.toFixed(0)}] tile [${tr.left.toFixed(0)},${tr.top.toFixed(0)},${tr.right.toFixed(0)},${tr.bottom.toFixed(0)}]`);
        }
      }
      for (const c of lab.children) if (!c.hidden && c.scrollWidth > c.clientWidth + 1) out.push(`${t.dataset.k} ${c.className} scrollW ${c.scrollWidth}>${c.clientWidth}`);
    }
    if (chip && !chip.hidden) {
      chips++;
      const cr = chip.getBoundingClientRect();
      if (!inside(cr, tr, 0.5)) out.push(`${t.dataset.k} chip outside`);
      for (const rr of rects) if (hit(cr, rr)) { out.push(`${t.dataset.k} chip overlaps '${chip.textContent}'`); break; }
    }
  }
  for (const g of document.querySelectorAll('#world .kw-gh:not([hidden])')) {
    const gr = g.getBoundingClientRect();
    for (const c of g.children) { if (!c.textContent) continue; const r = c.getBoundingClientRect(); if (r.right > gr.right + 1 || r.left < gr.left - 1) out.push(`header ${g.textContent} child outside`); }
    const t = g.children[0]; if (t.scrollWidth > t.clientWidth + 1) out.push(`header name truncated: ${t.textContent}`);
  }
  return { tiles, labs, chips, out };
}"""

COLORS_JS = r"""
(fix) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const bad = []; let n = 0;
  const items = new Map(); for (const g of fix.groups) for (const it of g.items) items.set(it.key, it);
  for (const t of document.querySelectorAll('#world .kw-tile')) {
    const it = items.get(t.dataset.k); if (!it) { bad.push('unknown ' + t.dataset.k); continue; }
    n++;
    const want = it.ref ? norm('#30333b') : norm(KH.colorOf(it.ratio));
    const got = norm(t.style.backgroundColor);
    if (want !== got) bad.push(`${it.key} ${got} != ${want}`);
    if (!!it.ref !== t.classList.contains('ref')) bad.push(`${it.key} ref class`);
  }
  return { n, bad };
}"""

TARGETS_JS = r"""
() => {
  const small = [];
  for (const el of document.querySelectorAll('#world .kw-tile, #world .kw-row, #world .kw-retry, .kw-sheet button, .kw-sheet a')) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (r.height < 40 || (r.width < 40)) small.push(`${el.className || el.tagName} ${el.dataset.k || el.textContent.trim().slice(0, 12)} ${r.width.toFixed(0)}x${r.height.toFixed(0)}`);
  }
  return small;
}"""


def kind_pass(browser, kind, width, height):
    mobile = width < 700
    hsh = '#world' if kind == 'index' else '#cmdty'
    ctx, page = open_page(browser, LIVE + hsh, width, height, mobile)
    try:
        wait_world(page)
        tag = f'{kind} {width}'
        n = page.evaluate("document.querySelectorAll('#world .kw-tile').length")
        check(f'{tag}: all items drawn', n == COUNT[kind], f'{n}/{COUNT[kind]}')
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f'{tag}: no horizontal overflow', ov <= 0, f'{ov}px')
        lab = page.evaluate(LABELS_JS)
        check(f'{tag}: labels / chips / headers inside', not lab['out'], '; '.join(lab['out'][:4]) or f"labels {lab['labs']}/{lab['tiles']}, chips {lab['chips']}/{lab['tiles']}")
        check(f'{tag}: every tile has a label', lab['labs'] == lab['tiles'], f"{lab['labs']}/{lab['tiles']}")
        check(f'{tag}: state chip on ≥ 90% of tiles', lab['chips'] >= 0.9 * lab['tiles'], f"{lab['chips']}/{lab['tiles']}")
        col = page.evaluate(COLORS_JS, FIX[kind])
        check(f'{tag}: tile colours = KH.colorOf(ratio), VIX grey', not col['bad'] and col['n'] == COUNT[kind], '; '.join(col['bad'][:3]))
        if mobile:
            small = page.evaluate(TARGETS_JS)
            check(f'{tag}: tap targets ≥ 40px', not small, '; '.join(small[:4]))
        side = page.evaluate("""() => { const s = document.querySelector('#world .kw-side').getBoundingClientRect(), m = document.querySelector('#world .kw-map').getBoundingClientRect();
            return { right: s.left >= m.right - 1, below: s.top >= m.bottom - 1 }; }""")
        check(f'{tag}: side panel {"below" if width <= 980 else "right of"} the map', side['below'] if width <= 980 else side['right'], str(side))
        if width in (1440, 768, 390, 1280, 360, 1920):
            page.screenshot(path=str(SHOTS / f'{kind}_{width}.png'), full_page=True)
    finally:
        ctx.close()


def keyboard_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        wait_world(page)
        stops = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].filter(t => t.tabIndex === 0).length")
        check('keyboard: one tab stop in the map (roving)', stops == 1, f'{stops}')
        page.focus('#world .kw-tile[tabindex="0"]')
        first = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowRight')
        right = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowDown')
        down = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowLeft'); page.keyboard.press('ArrowUp')
        back = page.evaluate('document.activeElement.dataset.k')
        check('keyboard: arrows move between tiles', first and right and right != first and down and down != right, f'{first}→{right}→{down}→{back}')
        moved = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].filter(t => t.tabIndex === 0).map(t => t.dataset.k)")
        check('keyboard: tab stop follows focus', moved == [back], str(moved))
        page.keyboard.press('Home')
        home = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowRight')
        tgt = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('Enter')
        page.wait_for_selector('.kw-sheet:not([hidden])', timeout=3000)
        info = page.evaluate("""() => ({ inSheet: document.querySelector('.kw-sheet').contains(document.activeElement),
            name: document.querySelector('#kw-dt').textContent, sel: document.querySelector('#world .kw-tile.sel')?.dataset.k,
            tileName: document.querySelector('#world .kw-tile.sel')?.title })""")
        check('detail: Enter opens it, focus inside, tile marked', info['inSheet'] and info['sel'] == tgt and info['name'] == info['tileName'], str(info))
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        check('detail: 3개월 chart drawn', page.evaluate("document.querySelectorAll('.kw-sheet .kw-svg path.kw-line').length") == 1)
        meta = page.evaluate("[...document.querySelectorAll('.kw-meta dt')].map(d => d.textContent)")
        check('detail: value · state · local time · KST · unit rows', all(k in meta for k in ('시세', '현지 거래 시각', '한국 시각', '단위')), str(meta))
        page.click('.kw-tf button:has-text("1년")')
        page.wait_for_function("document.querySelector('.kw-tf button[aria-pressed=\"true\"]').textContent === '1년' && !!document.querySelector('.kw-sheet svg.kw-svg')", timeout=5000)
        lab1y = page.evaluate("document.querySelector('.kw-sheet svg.kw-svg').getAttribute('aria-label')")
        check('detail: 1년 switch redraws', lab1y.startswith('1년'), lab1y[:40])
        page.focus('.kw-sheet .kw-x')
        trapped = True
        for _ in range(7):
            page.keyboard.press('Tab')
            trapped &= page.evaluate("document.querySelector('.kw-sheet').contains(document.activeElement)")
        check('detail: Tab stays inside the sheet', trapped)
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        after = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, k: document.activeElement.dataset.k, sel: document.querySelectorAll('#world .kw-tile.sel').length, still: !document.querySelector('main.layout') || true })")
        check('detail: Esc closes and focus returns to the tile', after['hidden'] and after['k'] == tgt and after['sel'] == 0, str(after))
        # Esc must not reach the heatmap (zoom-out etc.) and must not reopen anything
        page.keyboard.press('Tab')
        out = page.evaluate("!document.activeElement.classList.contains('kw-tile')")
        check('keyboard: Tab leaves the map after one stop', out, page.evaluate('document.activeElement.className'))
        # side list → detail → Esc back to the row
        page.click('#world .kw-row')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        check('side list: opens detail, Esc returns focus to the row', page.evaluate("document.activeElement.classList.contains('kw-row')"))
        # click outside closes on desktop
        page.click('#world .kw-tile')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.mouse.click(5, 300)
        page.wait_for_timeout(100)
        check('detail: click outside closes (desktop)', page.evaluate("document.querySelector('.kw-sheet').hidden"))
        # layout() for image saving
        lay = page.evaluate("KHWorld.layout()")
        tiles = [x for x in lay if x['kind'] == 'tile']
        mw, mh = page.evaluate("[document.querySelector('#world .kw-map').clientWidth, document.querySelector('#world .kw-map').clientHeight]")
        okb = all(0 <= t['x'] and t['x'] + t['w'] <= mw + 0.5 and 0 <= t['y'] and t['y'] + t['h'] <= mh + 0.5 for t in tiles)
        subs = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].map(t => [t.dataset.k, t.querySelector('.kw-pc').hidden || t.querySelector('.kw-lab').hidden ? '' : t.querySelector('.kw-pc').textContent])")
        subok = dict(subs) == {t['code']: t['sub'] for t in tiles}
        check('KHWorld.layout(): tiles + groups in map pixels, sub = shown %', len(tiles) == COUNT['index'] and okb and subok and sum(1 for x in lay if x['kind'] == 'sector') == len(FIX['index']['groups']), f'{len(tiles)} tiles, inBounds {okb}, sub {subok}')
        page.screenshot(path=str(SHOTS / 'kbd_1280.png'))
    finally:
        ctx.close()


def palette_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900)
    try:
        wait_world(page)
        before = page.evaluate("document.querySelector('#world .kw-tile[data-k=\"INX\"]').style.backgroundColor")
        page.click('.seg[data-key="palette"] button[data-v="global"]')
        page.wait_for_timeout(150)
        col = page.evaluate(COLORS_JS, FIX['index'])
        after = page.evaluate("document.querySelector('#world .kw-tile[data-k=\"INX\"]').style.backgroundColor")
        check('palette switch recolours tiles (초록 상승)', before != after and not col['bad'], f'{before} → {after}')
        sw = page.evaluate("[document.querySelector('#world .kw-row .kw-sw').style.background, document.querySelector('#world .kw-legend .grad').style.background]")
        check('palette switch recolours side swatches + legend', 'rgb' in sw[0] and '#f63538' in sw[1].lower() or 'rgb(246, 53, 56)' in sw[1], sw[1][:60])
        page.click('#rangeseg button[data-v="10"]')
        page.wait_for_timeout(150)
        col = page.evaluate(COLORS_JS, FIX['index'])
        tick = page.evaluate("[...document.querySelectorAll('#world .kw-legend .tk')].map(t => t.textContent)")
        check('range switch (±10%) recolours + legend ticks', not col['bad'] and tick == ['−10%', '+10%'], str(tick))
        page.click('.seg[data-key="palette"] button[data-v="krg"]')
        page.click('#rangeseg button[data-v="3"]')
    finally:
        ctx.close()


def states_pass(browser):
    ERR.expect_net = True
    try:
        for mode, text in (('fail', '해외 지수를 불러오지 못했어요'), ('html404', '서버에 아직 이 기능이 없어요'), ('empty', '지금 보여 줄 해외 지수가 없어요')):
            api(f'/__mode?world={mode}')
            ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
            try:
                page.wait_for_selector('#world .kw-msg', timeout=8000)
                page.wait_for_timeout(300)
                msg = page.evaluate("document.querySelector('#world .kw-msg').textContent")
                check(f'state {mode}: message', text in msg and page.evaluate("!!document.querySelector('#world .kw-retry')"), msg[:60])
                if mode == 'fail':
                    page.screenshot(path=str(SHOTS / 'fail_1280.png'))
                    api('/__mode?world=ok')
                    page.click('#world .kw-retry')
                    wait_world(page)
                    check('state fail → 다시 시도 loads', page.evaluate("document.querySelectorAll('#world .kw-tile').length") == COUNT['index'])
            finally:
                ctx.close()
        api('/__mode?world=ok')
        # loading message while the first answer is slow
        api('/__mode?world=slow')
        ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844, True)
        try:
            page.wait_for_selector('#world .kw-msg.busy', timeout=3000)
            check('state loading: message while waiting', '불러오는 중이에요' in page.evaluate("document.querySelector('#world .kw-msg').textContent"))
            wait_world(page)
        finally:
            ctx.close()
        api('/__mode?world=ok')
        # stale: data shown, then a refresh fails → keeps tiles, says so
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800, clock=True)
        try:
            wait_world(page)
            api('/__mode?world=fail')
            page.clock.run_for(31000)
            page.wait_for_selector('#world .kw-stale', timeout=5000)
            check('state stale: tiles kept + "새로 받지 못했어요"', page.evaluate("document.querySelectorAll('#world .kw-tile').length") == COUNT['index'],
                  page.evaluate("document.querySelector('#world .kw-stale').textContent"))
            api('/__mode?world=ok')
            page.clock.run_for(16000)
            page.wait_for_function("!document.querySelector('#world .kw-stale')", timeout=5000)
            check('state stale → recovers after 15 s retry', True)
        finally:
            ctx.close()
        # weekend: nothing open
        api('/__mode?world=closed')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
        try:
            wait_world(page)
            t = page.evaluate("document.querySelector('#world .kw-open').textContent")
            check('state closed (weekend): "지금은 열린 시장이 없어요"', '지금은 열린 시장이 없어요' in t and '모두 마감' in page.evaluate("document.querySelector('#world .kw-sum').textContent"), t[:40])
        finally:
            ctx.close()
        api('/__mode?world=ok')
        # chart route missing (plain 404): detail without chart, asked once per session
        api('/__mode?chart=none')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
        try:
            wait_world(page)
            c0 = api('/__stats').get('/api/world/chart', 0)
            page.click('#world .kw-tile[data-k="INX"]')
            page.wait_for_function("document.querySelector('.kw-sheet .kw-chart') && document.querySelector('.kw-sheet .kw-chart').hidden", timeout=5000)
            page.keyboard.press('Escape')
            page.click('#world .kw-tile[data-k="N225"]')
            page.wait_for_timeout(400)
            c1 = api('/__stats').get('/api/world/chart', 0)
            vis = page.evaluate("!document.querySelector('.kw-sheet').hidden && !!document.querySelector('.kw-sheet .kw-px b').textContent")
            check('chart route missing: detail shows values, chart hidden, probed once', vis and c1 - c0 == 1, f'chart calls {c1 - c0}')
        finally:
            ctx.close()
        api('/__mode?chart=fail')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
        try:
            wait_world(page)
            page.click('#world .kw-tile[data-k="GDAXI"]')
            page.wait_for_selector('.kw-sheet .kw-cmsg .kw-retry', timeout=5000)
            check('chart failure: message + 다시 시도', '차트를 불러오지 못했어요' in page.evaluate("document.querySelector('.kw-sheet .kw-cmsg').textContent"))
        finally:
            ctx.close()
    finally:
        api('/__reset')
        ERR.expect_net = False


def polling_pass(browser):
    api('/__reset')
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, clock=True)
    try:
        wait_world(page)
        n = lambda: api('/__stats').get('world:index', 0)
        a = n()
        page.clock.run_for(30500); page.wait_for_timeout(500)
        b = n()
        check('polling: every 30 s while shown', b - a == 1, f'{a}→{b}')
        page.click('.tabs button[data-mkt="K"]')
        page.wait_for_timeout(200)
        check('hide(): #world hidden, map back', page.evaluate("document.getElementById('world').hidden && KHWorld.shown() === null"))
        page.clock.run_for(95000); page.wait_for_timeout(400)
        c = n()
        check('polling: stops while another tab is shown', c == b, f'{b}→{c}')
        page.click('.tabs button[data-mkt="WORLD"]')
        page.wait_for_timeout(500)
        d = n()
        check('polling: back on the tab with old data → loads at once', d == c + 1, f'{c}→{d}')
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
        page.clock.run_for(95000); page.wait_for_timeout(400)
        e = n()
        check('polling: stops while the browser tab is hidden', e == d, f'{d}→{e}')
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(500)
        f = n()
        check('polling: visible again → refreshes', f == e + 1, f'{e}→{f}')
        # switching kinds: commodity tab shows commodities, detail closes
        page.click('#world .kw-tile')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_world(page, '#world .kw-tile[data-k="CLcv1"]')
        k = page.evaluate("({ n: document.querySelectorAll('#world .kw-tile').length, title: document.querySelector('#world .kw-title').textContent, sheet: document.querySelector('.kw-sheet').hidden })")
        check('tab switch 해외 → 원자재: commodity tiles, detail closed', k['n'] == COUNT['commodity'] and k['title'] == '원자재' and k['sheet'], str(k))
        units = page.evaluate("[...document.querySelectorAll('#world .kw-v')].filter(v => !v.hidden).map(v => v.textContent)")
        check('commodity tiles show units where they fit', any('$/' in u or '¢/' in u for u in units), ', '.join(units[:4]))
    finally:
        ctx.close()


def mobile_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 390, 844, True)
    try:
        wait_world(page)
        page.tap('#world .kw-tile[data-k="INX"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        page.wait_for_timeout(350)                       # the 0.2 s slide-in
        geo = page.evaluate("""() => { const r = document.querySelector('.kw-sheet').getBoundingClientRect();
            return { bottom: Math.round(r.bottom), vh: innerHeight, left: Math.round(r.left), w: Math.round(r.width), scrim: getComputedStyle(document.querySelector('.kw-scrim')).display }; }""")
        check('phone: detail is a bottom sheet with a scrim', geo['bottom'] == geo['vh'] and geo['left'] == 0 and geo['w'] == 390 and geo['scrim'] == 'block', str(geo))
        small = page.evaluate(TARGETS_JS)
        check('phone: sheet tap targets ≥ 40px', not small, '; '.join(small[:4]))
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check('phone: no overflow with the sheet open', ov <= 0, f'{ov}')
        page.screenshot(path=str(SHOTS / 'detail_390.png'))
        page.tap('.kw-scrim', position={'x': 50, 'y': 40})
        page.wait_for_timeout(150)
        check('phone: tapping the scrim closes', page.evaluate("document.querySelector('.kw-sheet').hidden"))
    finally:
        ctx.close()
    ctx, page = open_page(browser, LIVE + '#cmdty', 1440, 900)
    try:
        wait_world(page)
        page.click('#world .kw-tile[data-k="GCcv1"]')
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        page.screenshot(path=str(SHOTS / 'detail_cmdty_1440.png'))
        unit = page.evaluate("[...document.querySelectorAll('.kw-meta dd')].map(d => d.textContent)")
        check('commodity detail: unit in words', '달러/트로이온스' in unit, str(unit))
    finally:
        ctx.close()


def reduced_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, reduced=True)
    try:
        wait_world(page)
        page.click('#world .kw-tile')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        r = page.evaluate("({ anim: getComputedStyle(document.querySelector('.kw-sheet')).animationName, tr: getComputedStyle(document.querySelector('#world .kw-tile')).transitionDuration })")
        check('reduced motion: no sheet animation, no tile transition', r['anim'] == 'none' and set(r['tr'].replace(' ', '').split(',')) == {'0s'}, str(r))
    finally:
        ctx.close()


def boot_pass(browser):
    # page opened at #cmdty: the template calls show() before world.js exists → the module starts itself
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
    try:
        wait_world(page)
        check('boot at #cmdty: module self-starts (template called show() too early)', page.evaluate("KHWorld.shown()") == 'commodity')
    finally:
        ctx.close()


def snapshot_pass(browser):
    for hsh in ('world', 'cmdty'):
        ctx, page = open_page(browser, SNAP + '#' + hsh, 390 if hsh == 'cmdty' else 1280, 844 if hsh == 'cmdty' else 800, hsh == 'cmdty')
        try:
            page.wait_for_selector('#world .kw-snap', timeout=8000)
            a = page.evaluate("document.querySelector('#world .kw-snap a').href")
            t = page.evaluate("document.querySelector('#world .kw-snap').textContent")
            check(f'snapshot #{hsh}: "실시간 버전에서 볼 수 있어요" + link', a == f'https://kospimap.pages.dev/#{hsh}' and '실시간 버전에서 볼 수 있어요' in t, a)
            ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f'snapshot #{hsh}: no overflow', ov <= 0)
            page.screenshot(path=str(SHOTS / f'snapshot_{hsh}.png'))
        finally:
            ctx.close()


def real_pass(browser):
    log = open('/tmp/kw-real-worker.log', 'w')
    env = dict(__import__('os').environ, NODE_USE_ENV_PROXY='1', ASSET_BASE=LIVE, PORT=str(REAL_PORT))
    proc = None
    try:
        api('/api/world?kind=index', f'http://127.0.0.1:{REAL_PORT}')
    except Exception:
        proc = subprocess.Popen(['node', 'worker/dev/serve.mjs'], cwd=ROOT, env=env, stdout=log, stderr=log)
        for _ in range(40):
            try:
                api('/api/world?kind=index', f'http://127.0.0.1:{REAL_PORT}'); break
            except Exception:
                time.sleep(0.5)
    try:
        real = {k: api(f'/api/world?kind={k}', f'http://127.0.0.1:{REAL_PORT}') for k in ('index', 'commodity')}
        for kind, hsh in (('index', 'world'), ('commodity', 'cmdty')):
            want = sum(len(g['items']) for g in real[kind]['groups'])
            ctx, page = open_page(browser, f'http://127.0.0.1:{REAL_PORT}/#{hsh}', 1440, 900)
            try:
                wait_world(page, timeout=20000)
                n = page.evaluate("document.querySelectorAll('#world .kw-tile').length")
                lab = page.evaluate(LABELS_JS)
                page.click('#world .kw-tile')
                page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=20000)
                check(f'real Worker {kind}: tiles, labels inside, chart', abs(n - want) <= 2 and not lab['out'], f'{n} tiles (api {want}); ' + '; '.join(lab['out'][:2]))
                page.screenshot(path=str(SHOTS / f'real_{kind}_1440.png'))
            finally:
                ctx.close()
    finally:
        if proc:
            proc.terminate()


def main():
    mock = None
    try:
        api('/__reset')
    except Exception:
        mock = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                api('/__reset'); break
            except Exception:
                time.sleep(0.25)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for kind in ('index', 'commodity'):
                for w, hgt in list(WIDTHS.items()) + [(1440, 900)]:
                    kind_pass(browser, kind, w, hgt)
            keyboard_pass(browser)
            palette_pass(browser)
            mobile_pass(browser)
            reduced_pass(browser)
            boot_pass(browser)
            polling_pass(browser)
            states_pass(browser)
            snapshot_pass(browser)
            if '--real' in sys.argv:
                real_pass(browser)
            browser.close()
        check('console errors: 0 (outside failure-mode tests)', not ERR.items, '; '.join(ERR.items[:4]))
    finally:
        if mock:
            mock.terminate()
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed; expected network errors in failure tests: {len(ERR.expected)}')
    (SHOTS / 'results.json').write_text(json.dumps([{'name': n, 'ok': o, 'detail': d} for n, o, d in results], ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
