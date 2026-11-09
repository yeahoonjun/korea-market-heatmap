#!/usr/bin/env python3
"""QA for src/map3d (3D 지도, AGENTS.md §3-5, docs/motion-brief.md f) on the built pages.

  python3 scripts/build_page.py && python3 qa/map3d/test_map3d.py [--no-live] [--quick]

Chrome runs WebGL on SwiftShader (--use-gl=swiftshader). Until the template's 지도 · 3D · 표 hook lands, qa/map3d/shim.js puts
<div id="map3d"> over #map (same rect, #map stays laid out) and calls KH3D.show(). Snapshot = dist/index.html; live = web/
served by `python3 -m http.server 8805 -d web` + the local Worker on 8804 (both started and stopped here, by PID).
Screenshots → qa/shots/map3d/. Exit code 1 if any check fails.

Headless SwiftShader prints "GL Driver Message … GPU stall due to ReadPixels" for every WebGL canvas it composites (a plain
clearColor page does it too); those driver notices are filtered, everything else on the console counts.
"""
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHOTS = ROOT / 'qa/shots/map3d'
SHOTS.mkdir(parents=True, exist_ok=True)
SNAP = (ROOT / 'dist/index.html').as_uri()
SHIM = (HERE / 'shim.js').read_text(encoding='utf-8')
STATIC_PORT, WORKER_PORT = 8805, 8804
LIVE = f'http://127.0.0.1:{WORKER_PORT}/'
GL = ['--no-sandbox', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist']
NOGL = ['--no-sandbox', '--disable-gpu', '--disable-webgl', '--disable-3d-apis']
VIEWPORTS = {390: dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
             768: dict(viewport={'width': 768, 'height': 1024}),
             1440: dict(viewport={'width': 1440, 'height': 900}),
             1920: dict(viewport={'width': 1920, 'height': 1080})}
DRIVER = re.compile(r'GL Driver Message|GPU stall due to ReadPixels')
THREE_GLOB = '**/three@0.149.0/build/three.min.js'
QUICK = '--quick' in sys.argv

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' else ''), flush=True)


class Console:
    def __init__(self, page):
        self.items = []
        page.on('console', lambda m: self.items.append(f'{m.type}: {m.text}') if m.type in ('error', 'warning') and not DRIVER.search(m.text) else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))

    def take(self):
        out, self.items = self.items, []
        return out


def open_page(browser, w, url, motion=None):
    ctx = browser.new_context(**VIEWPORTS[w])
    page = ctx.new_page()
    con = Console(page)
    page.goto(url)
    page.wait_for_function('() => window.KH && window.KH3D && document.querySelector("#map .tile")', timeout=30000)
    if motion:
        page.evaluate(f"() => {{ window.KH.motion = () => '{motion}'; }}")
    page.add_script_tag(content=SHIM)
    return ctx, page, con


def turn_on(page):
    ok = page.evaluate('() => window.__m3d.on()')
    if ok:
        page.wait_for_function('() => KH3D.qa.inspect().instances > 0 && !KH3D.qa.inspect().flying && !KH3D.qa.inspect().tweening', timeout=20000)
        page.wait_for_timeout(250)
    return ok


def inspect(page):
    return page.evaluate('() => KH3D.qa.inspect()')


def rgb(s):
    s = s.strip()
    m = re.match(r'^#([0-9a-f]{6})$', s, re.I)
    if m:
        return [int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)]
    m = re.match(r'^#([0-9a-f]{3})$', s, re.I)
    if m:
        return [int(c * 2, 16) for c in m.group(1)]
    return [round(float(v)) for v in re.findall(r'[\d.]+', s)[:3]]


def core_checks(page, tag, w):
    """Counts, colours (buffer + pixels), picking, labels, overflow."""
    info = inspect(page)
    n_layout = page.evaluate("() => KH.layout().filter(n => n.kind === 'tile' && n.w > 0 && n.h > 0).length")
    check(f'{tag}: instances == tiles == layout tiles', info['instances'] == info['tiles'] == n_layout and n_layout > 0,
          f"{info['instances']}/{info['tiles']}/{n_layout}")
    check(f'{tag}: three r149 loaded', info['three'] == '149')
    cols = page.evaluate('() => KH3D.qa.colors()')
    bad = [c for c in cols if max(abs(a - b) for a, b in zip(rgb(c['tile']), c['gl'])) > 1]
    check(f'{tag}: instance colours == 2D tile colours', not bad, f'{len(cols) - len(bad)}/{len(cols)}')
    # rendered pixels of the top faces, straight down, overlays hidden; the 12 biggest tiles
    page.evaluate("() => { KH3D.qa.topDown(); document.querySelector('#map3d .m3-labels').style.visibility = 'hidden'; }")
    page.wait_for_timeout(200)
    big = page.evaluate("""() => KH.layout().filter(n => n.kind === 'tile' && n.code).sort((a, b) => b.w * b.h - a.w * a.h).slice(0, 12)
                              .map(t => ({k: t.code, color: t.color}))""")
    pts = page.evaluate("""big => { const cv = document.querySelector('#map3d canvas').getBoundingClientRect();
        return big.map(b => { const a = KH3D.qa.anchor(b.k); return a ? [a.x - cv.left + 3, a.y - cv.top + 3] : [0, 0]; }); }""", big)
    px = page.evaluate('pts => KH3D.qa.pixels(pts)', pts)
    diffs = [max(abs(a - b) for a, b in zip(rgb(bg['color']), p)) for bg, p in zip(big, px)]
    check(f'{tag}: rendered top faces == 2D colours (top-down)', diffs and max(diffs) <= 3, f'max Δ {max(diffs) if diffs else "-"} over {len(diffs)}')
    picks = page.evaluate("""big => big.map(b => { const a = KH3D.qa.anchor(b.k); return a ? KH3D.qa.pick(a.x, a.y) === b.k : false; })""", big)
    check(f'{tag}: picking (top-down) returns the right code', all(picks), f'{sum(picks)}/{len(picks)}')
    page.evaluate("() => { document.querySelector('#map3d .m3-labels').style.visibility = ''; document.querySelector('#map3d .m3-ctl .reset').click(); }")
    page.wait_for_function('() => KH3D.qa.inspect().atHome && !KH3D.qa.inspect().flying', timeout=5000)
    page.wait_for_timeout(300)
    # picking at the home (tilted) view: every visible stock label sits on its own, unoccluded top face
    lab = page.evaluate("""() => [...document.querySelectorAll('#map3d .m3-lab:not([hidden])')].map(e => {
        const r = e.getBoundingClientRect(); return {k: e.dataset.k, x: r.left + r.width / 2, y: r.top + r.height / 2}; })""")
    ok = [page.evaluate('([x, y]) => KH3D.qa.pick(x, y)', [l['x'], l['y']]) == l['k'] for l in lab]
    check(f'{tag}: picking (tilted) under each stock label', lab and sum(ok) >= len(ok) - 1, f'{sum(ok)}/{len(ok)} labels')
    # layout: no horizontal overflow, overlays inside #map3d, labels do not overlap each other
    lay = page.evaluate("""() => {
      const root = document.getElementById('map3d').getBoundingClientRect();
      const inside = e => { const r = e.getBoundingClientRect(); return r.left >= root.left - 1 && r.right <= root.right + 1 && r.top >= root.top - 1 && r.bottom <= root.bottom + 1; };
      const labs = [...document.querySelectorAll('#map3d .m3-lab:not([hidden]), #map3d .m3-sec:not([hidden])')];
      const rs = labs.map(e => e.getBoundingClientRect());
      let over = 0;
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], b = rs[j];
        if (a.left < b.right - 2 && a.right > b.left + 2 && a.top < b.bottom - 2 && a.bottom > b.top + 2) over++;
      }
      return { sw: document.documentElement.scrollWidth, iw: innerWidth, labels: labs.length, outside: labs.filter(e => !inside(e)).length, over,
               hud: inside(document.querySelector('#map3d .m3-hud')), ctl: inside(document.querySelector('#map3d .m3-ctl')),
               cv: [Math.round(root.width), Math.round(root.height)], canvas: [document.querySelector('#map3d canvas').clientWidth, document.querySelector('#map3d canvas').clientHeight] };
    }""")
    check(f'{tag}: no horizontal overflow', lay['sw'] <= lay['iw'], f"{lay['sw']} ≤ {lay['iw']}")
    check(f'{tag}: labels / legend / buttons inside #map3d, no label overlaps', lay['outside'] == 0 and lay['over'] == 0 and lay['hud'] and lay['ctl'],
          f"{lay['labels']} labels, {lay['outside']} outside, {lay['over']} overlaps")
    check(f'{tag}: canvas fills #map3d', lay['cv'] == lay['canvas'], f"{lay['cv']} vs {lay['canvas']}")
    btn = page.evaluate("() => [...document.querySelectorAll('#map3d .m3-btn')].map(b => Math.min(b.offsetWidth, b.offsetHeight))")
    if w <= 760 or VIEWPORTS[w].get('has_touch'):
        check(f'{tag}: buttons ≥ 40 px on touch / narrow', min(btn) >= 40, f'{min(btn)}px')
    return info


def desktop_interactions(page, con, tag):
    big = page.evaluate("() => KH.layout().filter(n => n.kind === 'tile' && n.code).sort((a, b) => b.w * b.h - a.w * a.h)[0]")
    a = page.evaluate('k => KH3D.qa.anchor(k)', big['code'])
    page.mouse.move(a['x'] - 40, a['y'] - 40)
    page.mouse.move(a['x'], a['y'], steps=4)
    page.wait_for_timeout(250)
    tip = page.evaluate("() => { const t = document.querySelector('.m3-tip'); return t ? {show: t.classList.contains('show'), text: t.textContent} : null; }")
    check(f'{tag}: hover shows the tooltip for the box', tip and tip['show'] and big['label'] in tip['text'], (tip or {}).get('text', '')[:40])
    page.mouse.click(a['x'], a['y'])
    page.wait_for_timeout(600)
    opened = page.evaluate('() => !!(window.KHStock && KHStock.isOpen())')
    check(f'{tag}: click opens KHStock for the box', opened, page.evaluate('() => location.hash'))
    if opened:
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)
        check(f'{tag}: Esc closes the stock page, focus back on the 3D canvas',
              page.evaluate("() => !KHStock.isOpen() && document.activeElement === document.querySelector('#map3d canvas')"))
    page.mouse.move(5, 5)
    # double click on a box → fly to its sector; Esc → home; Esc at home → the view switch
    a = page.evaluate('k => KH3D.qa.anchor(k)', big['code'])
    page.mouse.dblclick(a['x'], a['y'])
    page.wait_for_timeout(900)
    i = inspect(page)
    check(f'{tag}: double click zooms to the sector', i['cam']['dist'] < i['fitDist'] * 0.95 and not page.evaluate('() => KHStock.isOpen()'),
          f"dist {i['cam']['dist']:.0f} vs fit {i['fitDist']:.0f}")
    page.focus('#map3d canvas')
    page.keyboard.press('Escape')
    page.wait_for_timeout(900)
    check(f'{tag}: Esc returns to the home view', inspect(page)['atHome'])
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)
    check(f'{tag}: Esc at home moves focus to the view switch', page.evaluate("() => !!document.activeElement.closest('.viewseg')"))
    page.focus('#map3d canvas')
    az0 = inspect(page)['goal']['az']
    page.keyboard.press('ArrowLeft')
    az1 = inspect(page)['goal']['az']
    check(f'{tag}: ← turns 10°', abs((az1 - az0) * 180 / 3.14159265 - 10) < 0.01, f'{(az1 - az0) * 57.2958:.2f}°')
    d0 = inspect(page)['goal']['dist']
    cv = page.evaluate("() => { const r = document.querySelector('#map3d canvas').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
    page.mouse.move(*cv)
    page.mouse.wheel(0, -300)
    page.wait_for_timeout(200)
    check(f'{tag}: wheel zooms in', inspect(page)['goal']['dist'] < d0)
    page.mouse.move(cv[0], cv[1])
    page.mouse.down()
    page.mouse.move(cv[0] + 120, cv[1] + 30, steps=6)
    page.mouse.up()
    page.wait_for_timeout(150)
    check(f'{tag}: drag turns the map within ±45°', abs(inspect(page)['goal']['az']) <= 45 / 57.2958 + 1e-6)
    page.click('#map3d .m3-ctl .reset')
    page.wait_for_timeout(300)
    # colour range ±5 → the range the heights use follows; palette change → colours still match
    page.click('#rangeseg button:nth-child(2)')
    page.wait_for_timeout(400)
    check(f'{tag}: height range follows the colour range tool (±5)', inspect(page)['range'] == 5, inspect(page)['range'])
    pal = page.evaluate("() => [...document.querySelectorAll('#palseg button')].map(b => b.dataset.v)")
    page.evaluate("v => document.querySelector(`#palseg button[data-v='${v}']`).click()", pal[-1])
    page.wait_for_timeout(400)
    cols = page.evaluate('() => KH3D.qa.colors()')
    bad = [c for c in cols if max(abs(a - b) for a, b in zip(rgb(c['tile']), c['gl'])) > 1]
    check(f'{tag}: palette change ({pal[-1]}) → colours still match', not bad, f'{len(cols) - len(bad)}/{len(cols)}')
    page.evaluate("v => document.querySelector(`#palseg button[data-v='${v}']`).click()", pal[0])
    page.click('#rangeseg button:nth-child(1)')
    page.wait_for_timeout(300)
    # hidden tab: no frames while hidden
    f0 = page.evaluate("""async () => {
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
      document.dispatchEvent(new Event('visibilitychange'));
      const f = KH3D.qa.inspect().frames;
      KH3D.qa.view({az: 0.3});
      await new Promise(r => setTimeout(r, 400));
      const g = KH3D.qa.inspect().frames;
      delete document.hidden;
      document.dispatchEvent(new Event('visibilitychange'));
      await new Promise(r => setTimeout(r, 300));
      return [f, g, KH3D.qa.inspect().frames];
    }""")
    check(f'{tag}: no rendering while the tab is hidden, resumes after', f0[0] == f0[1] and f0[2] > f0[1], f0)
    # frame time while turning (SwiftShader = CPU rasteriser; JS + GL submit per frame)
    sp = page.evaluate('() => KH3D.qa.spin(2000)')
    st = sp['stats']
    check(f'{tag}: stats() exposes the last 60 frame times', st['frames'] > 0 and len(st['last60']) == st['frames'],
          f"{sp['fps']:.0f} fps on SwiftShader, avg {st['avgMs']} ms, p95 {st['p95Ms']} ms, {st['calls']} draw calls, {st['triangles']} tris")
    page.click('#map3d .m3-ctl .reset')
    page.wait_for_timeout(300)
    # theme overview: theme tiles have no code — still one box per tile
    page.evaluate("() => { location.hash = '#theme'; }")
    page.wait_for_timeout(1500)
    i = inspect(page)
    n_layout = page.evaluate("() => KH.layout().filter(n => n.kind === 'tile' && n.w > 0 && n.h > 0).length")
    check(f'{tag}: theme overview → instances == tiles', i['instances'] == n_layout and n_layout > 0, f"{i['instances']}/{n_layout}")
    page.evaluate("() => { location.hash = '#kosdaq'; }")
    page.wait_for_timeout(1200)
    # hide() frees the GPU; show() again works
    r = page.evaluate("""async () => {
      const cv = document.querySelector('#map3d canvas'); const gl = cv.getContext('webgl2') || cv.getContext('webgl');
      await KH3D.hide();
      return { lost: gl.isContextLost(), kids: document.getElementById('map3d').children.length, tip: !!document.querySelector('.m3-tip'),
               built: KH3D.qa.inspect().built, on: KH3D.isOn() };
    }""")
    check(f'{tag}: hide() loses the WebGL context and removes everything', r['lost'] and r['kids'] == 0 and not r['tip'] and not r['built'] and not r['on'], r)
    page.evaluate('() => window.__m3d.off()')
    ok = turn_on(page)
    check(f'{tag}: show() again after hide()', ok and inspect(page)['instances'] > 0)


def motion_checks(browser):
    tag = 'snapshot 1440 fancy'
    ctx, page, con = open_page(browser, 1440, SNAP, motion='fancy')
    page.evaluate("() => { window.__poses = []; const t0 = performance.now(); const tick = () => { const i = KH3D.qa.inspect(); if (i.cam) window.__poses.push([performance.now() - t0, i.cam.polar, i.tweening, i.flying]); if (performance.now() - t0 < 6000) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }")
    ok = turn_on(page)
    poses = page.evaluate('() => window.__poses')
    first = poses[0] if poses else None
    check(f'{tag}: entry starts at the flat 2D view (polar 0) and tilts to 32°', first and first[1] < 0.01 and abs(inspect(page)['cam']['polar'] - 32 / 57.2958) < 1e-3,
          f'first polar {first[1] if first else None:.4f}, frames {len(poses)}')
    page.click('#rangeseg button:nth-child(2)')
    page.wait_for_timeout(60)
    check(f'{tag}: data change tweens heights', inspect(page)['tweening'])
    page.wait_for_timeout(900)
    page.click('#rangeseg button:nth-child(1)')
    page.wait_for_timeout(700)
    fl = page.evaluate('''async () => {
      const codes = KH.layout().filter(n => n.kind === 'tile' && n.code).slice(0, 3).map(n => n.code);
      for (const c of codes) KH.stock(c).p += 5;          // three prices tick, nothing else changes
      document.dispatchEvent(new CustomEvent('kh:data'));
      await new Promise(r => setTimeout(r, 60));
      const a = KH3D.qa.inspect().flashes;
      await new Promise(r => setTimeout(r, 1200));
      for (const c of codes) KH.stock(c).p -= 5;
      return [a, KH3D.qa.inspect().flashes];
    }''')
    check(f'{tag}: price ticks pulse the top faces (and end)', fl == [3, 0], fl)
    t = page.evaluate('async () => { const t = performance.now(); const p = KH3D.hide(); const mid = KH3D.qa.inspect().leaving; await p; return [performance.now() - t, mid]; }')
    check(f'{tag}: hide() folds back (promise resolves after the fold)', t[1] and t[0] >= 300, f'{t[0]:.0f} ms')
    check(f'{tag}: console clean', not con.take())
    ctx.close()
    tag = 'snapshot 1440 standard'
    ctx, page, con = open_page(browser, 1440, SNAP, motion='standard')
    page.evaluate('() => window.__m3d.on()')
    page.wait_for_function('() => KH3D.qa.inspect().instances > 0', timeout=20000)
    i = inspect(page)
    check(f'{tag}: no entry animation, final pose at once', not i['tweening'] and not i['flying'] and abs(i['cam']['polar'] - 32 / 57.2958) < 1e-3)
    page.click('#rangeseg button:nth-child(2)')
    page.wait_for_timeout(60)
    check(f'{tag}: no height tween', not inspect(page)['tweening'])
    fl = page.evaluate('''async () => {
      const c = KH.layout().find(n => n.kind === 'tile' && n.code).code;
      KH.stock(c).p += 5; document.dispatchEvent(new CustomEvent('kh:data'));
      await new Promise(r => setTimeout(r, 60)); KH.stock(c).p -= 5;
      return KH3D.qa.inspect().flashes; }''')
    check(f'{tag}: no tick pulses', fl == 0, fl)
    t = page.evaluate('async () => { const p = KH3D.hide(); const i = KH3D.qa.inspect(); await p; return [i.built, i.leaving]; }')
    check(f'{tag}: hide() tears down at once (no fold)', t == [False, False], t)
    check(f'{tag}: console clean', not con.take())
    ctx.close()


def reduced_check(browser):
    tag = 'snapshot 1440 reduced'
    ctx, page, con = open_page(browser, 1440, SNAP, motion='reduced')
    turn_on(page)
    page.focus('#map3d canvas')
    page.keyboard.press('ArrowLeft')
    i = inspect(page)
    check(f'{tag}: camera jumps (no follow smoothing)', i['cam']['az'] == i['goal']['az'] and not i['flying'])
    page.keyboard.press('0')
    i = inspect(page)
    check(f'{tag}: home without a flight', i['atHome'] and not i['flying'])
    check(f'{tag}: console clean', not (m := con.take()), m[:2])
    ctx.close()


def touch_checks(browser):
    """Phone: sideways swipe turns, vertical swipe leaves the page its scroll (touch-action: pan-y), pinch zooms, tap opens."""
    tag = 'snapshot 390 touch'
    ctx, page, con = open_page(browser, 390, SNAP)
    turn_on(page)
    cdp = ctx.new_cdp_session(page)

    def centre():
        r = page.evaluate("() => document.querySelector('#map3d canvas').getBoundingClientRect().toJSON()")
        return r['x'] + r['width'] / 2, r['y'] + r['height'] / 2

    def swipe(pts):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [dict(x=x, y=y, id=k) for k, (x, y) in enumerate(pts[0])]})
        for step in pts[1:]:
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [dict(x=x, y=y, id=k) for k, (x, y) in enumerate(step)]})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        page.wait_for_timeout(350)

    cx, cy = centre()
    g0 = inspect(page)['goal']
    swipe([[(cx - 50 + 10 * i, cy + i)] for i in range(11)])
    g1, sy = inspect(page)['goal'], page.evaluate('() => scrollY')
    check(f'{tag}: sideways swipe turns the map, page stays', g1['az'] != g0['az'] and sy == 0, f"az {g0['az']:.3f}→{g1['az']:.3f}")
    swipe([[(cx + i * 0.4, cy + 100 - 25 * i)] for i in range(11)])
    g2, sy = inspect(page)['goal'], page.evaluate('() => scrollY')
    check(f'{tag}: vertical swipe scrolls the page, map untouched', g2['az'] == g1['az'] and g2['polar'] == g1['polar'] and sy > 0, f'scrollY {sy}')
    page.evaluate('() => scrollTo(0, 0)'); page.wait_for_timeout(1200); page.evaluate('() => scrollTo(0, 0)'); page.wait_for_timeout(300)
    cx, cy = centre()
    swipe([[(cx - 30 - 4 * i, cy), (cx + 30 + 4 * i, cy)] for i in range(9)])
    check(f'{tag}: pinch zooms in', inspect(page)['goal']['dist'] < g2['dist'] * 0.8, f"{g2['dist']:.0f}→{inspect(page)['goal']['dist']:.0f}")
    page.tap('#map3d .m3-ctl .reset')
    page.wait_for_timeout(400)
    check(f'{tag}: reset button → home view', inspect(page)['atHome'])
    big = page.evaluate("() => KH.layout().filter(n => n.kind === 'tile' && n.code).sort((a, b) => b.w * b.h - a.w * a.h)[0].code")
    a = page.evaluate('k => KH3D.qa.anchor(k)', big)
    page.touchscreen.tap(a['x'], a['y'])
    page.wait_for_timeout(700)
    check(f'{tag}: tap opens the stock page', page.evaluate('() => KHStock.isOpen()') and big in page.evaluate('() => location.hash'), big)
    check(f'{tag}: console clean', not (m := con.take()), m[:2])
    ctx.close()


def perf_check(browser):
    """Phone-sized canvas, 전체 market with 500 tiles, CPU slowed 4× (motion brief budget: ≤ 4 ms JS per frame)."""
    tag = 'perf 390 전체·500 CPU×4'
    ctx = browser.new_context(**VIEWPORTS[390])
    page = ctx.new_page()
    con = Console(page)
    page.goto(SNAP + '#all')
    page.evaluate("() => { localStorage.setItem('khm.topN', '500'); }")
    page.reload()
    page.wait_for_function('() => window.KH3D && document.querySelector("#map .tile")', timeout=30000)
    page.add_script_tag(content=SHIM)
    turn_on(page)
    n = inspect(page)['instances']
    cdp = ctx.new_cdp_session(page)
    out = {}
    for rate in (1, 4):
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': rate})
        out[rate] = page.evaluate('() => KH3D.qa.spin(3000)')['stats']
    cdp.send('Emulation.setCPUThrottlingRate', {'rate': 1})
    a, b = out[1], out[4]
    # SwiftShader rasterises on the CPU in the GPU process, so under throttling renderer.render() mostly waits on the command
    # buffer; the label pass (pure JS) is the part that scales with the CPU and is held to the brief's 4 ms budget
    check(f'{tag}: per-frame JS within budget', n >= 400 and a['avgMs'] <= 1.5 and b['labelsAvgMs'] <= 4,
          f"{n} boxes · CPU×1 avg {a['avgMs']} ms (p95 {a['p95Ms']}, labels {a['labelsAvgMs']}, render {a['renderAvgMs']}) · "
          f"CPU×4 labels {b['labelsAvgMs']} ms, render+GL wait {b['renderAvgMs']} ms · tier {a['tier']} dpr {a['dpr']} · {a['calls']} calls")
    page.screenshot(path=str(SHOTS / 'perf_390_all500.png'))
    check(f'{tag}: console clean', not (m := con.take()), m[:2])
    ctx.close()


def fallback_checks(p):
    # 1) no WebGL at all
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=NOGL)
    ctx, page, con = open_page(b, 1440, SNAP)
    page.evaluate("() => { window.__ev = null; document.addEventListener('kh:3d-unavailable', e => { window.__ev = e.detail; }); }")
    ok = page.evaluate('() => window.__m3d.on()')
    ev = page.evaluate('() => window.__ev')
    txt = page.evaluate("() => document.getElementById('map3d').innerText")
    check('no WebGL: show() → false + kh:3d-unavailable (webgl) + Korean message', ok is False and ev and ev['reason'] == 'webgl' and 'WebGL' in txt, txt.replace('\n', ' ')[:60])
    check('no WebGL: three.js never requested, console clean', not page.evaluate("() => !!document.querySelector('script[data-kh=three]')") and not con.take())
    page.screenshot(path=str(SHOTS / 'fallback_nowebgl.png'))
    ctx.close(); b.close()
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=GL)
    # 2) script blocked, 3) script tampered (SRI)
    for name, handler in (('blocked', lambda r: r.abort()),
                          ('tampered', lambda r: r.fulfill(status=200, content_type='application/javascript', headers={'access-control-allow-origin': '*'},
                                                           body='window.THREE={};/* not the real file */'))):
        ctx = b.new_context(**VIEWPORTS[1440])
        page = ctx.new_page()
        con = Console(page)
        page.route(THREE_GLOB, handler)
        page.goto(SNAP)
        page.wait_for_function('() => window.KH3D && document.querySelector("#map .tile")', timeout=30000)
        page.add_script_tag(content=SHIM)
        page.evaluate("() => { window.__ev = null; document.addEventListener('kh:3d-unavailable', e => { window.__ev = e.detail; }); }")
        ok = page.evaluate('() => window.__m3d.on()')
        ev = page.evaluate('() => window.__ev')
        txt = page.evaluate("() => document.getElementById('map3d').innerText")
        noise = [m for m in con.take() if not re.search(r'Failed to load resource|integrity|three', m)]
        check(f'script {name}: show() → false + kh:3d-unavailable (script) + message', ok is False and ev and ev['reason'] == 'script' and '불러오지 못했어요' in txt,
              txt.replace('\n', ' ')[:50])
        check(f'script {name}: no errors besides the browser’s own load/SRI notice', not noise, noise[:2])
        ctx.close()
    b.close()


def start_live():
    procs = []
    procs.append(subprocess.Popen([sys.executable, '-m', 'http.server', str(STATIC_PORT), '--bind', '127.0.0.1', '-d', str(ROOT / 'web')],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    env = dict(os.environ, NODE_USE_ENV_PROXY='1', ASSET_BASE=f'http://127.0.0.1:{STATIC_PORT}/', PORT=str(WORKER_PORT))
    procs.append(subprocess.Popen(['node', 'worker/dev/serve.mjs'], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open(LIVE, timeout=2) as r:
                if r.status == 200:
                    return procs
        except Exception:
            time.sleep(0.5)
    return procs


def stop(procs):
    for pr in procs:
        if pr.poll() is None:
            pr.send_signal(signal.SIGTERM)
            try:
                pr.wait(5)
            except subprocess.TimeoutExpired:
                pr.kill()


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=GL)
        widths = [1440, 390] if QUICK else [390, 768, 1440, 1920]
        for w in widths:
            tag = f'snapshot {w}'
            ctx, page, con = open_page(b, w, SNAP)
            ok = turn_on(page)
            check(f'{tag}: show() resolves true', ok)
            if ok:
                page.screenshot(path=str(SHOTS / f'snap_{w}.png'))
                core_checks(page, tag, w)
                if w == 1440:
                    desktop_interactions(page, con, tag)
            check(f'{tag}: console clean', not (msgs := con.take()), msgs[:3])
            ctx.close()
        motion_checks(b)
        reduced_check(b)
        touch_checks(b)
        perf_check(b)
        b.close()
        fallback_checks(p)
        if '--no-live' not in sys.argv:
            procs = start_live()
            try:
                b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=GL)
                for w in (1440, 390):
                    tag = f'live {w}'
                    ctx = b.new_context(**VIEWPORTS[w])
                    page = ctx.new_page()
                    con = Console(page)
                    page.goto(LIVE)
                    page.wait_for_function('() => window.KH && KH.stocks().length > 0 && document.querySelector("#map .tile")', timeout=45000)
                    page.add_script_tag(content=SHIM)
                    ok = turn_on(page)
                    check(f'{tag}: show() resolves true (three from jsDelivr with SRI)', ok)
                    if ok:
                        page.screenshot(path=str(SHOTS / f'live_{w}.png'))
                        core_checks(page, tag, w)
                        # a quote poll re-renders the 2D map → kh:data/kh:render → the 3D instances follow
                        page.evaluate("() => { window.__kd = 0; document.addEventListener('kh:data', () => window.__kd++); }")
                        page.wait_for_function('() => window.__kd > 0', timeout=80000)   # closed market: the page polls every 60 s
                        page.wait_for_timeout(400)
                        n = page.evaluate("() => KH.layout().filter(n => n.kind === 'tile' && n.w > 0 && n.h > 0).length")
                        check(f'{tag}: after a live poll instances == tiles', inspect(page)['instances'] == n, n)
                    msgs = [m for m in con.take() if 'map3d' in m or 'KH3D' in m or 'three' in m.lower() or 'pageerror' in m]
                    check(f'{tag}: no 3D-related console errors', not msgs, msgs[:3])
                    ctx.close()
                b.close()
            finally:
                stop(procs)
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed')
    (SHOTS / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
