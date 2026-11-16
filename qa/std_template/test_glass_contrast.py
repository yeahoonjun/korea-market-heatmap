#!/usr/bin/env python3
"""The glass themes' 등락 numbers stay readable over the worst tile (AGENTS §3-38 ④ 리퀴드 글라스 느낌(절제), ux/glass-liquid).

  python3 qa/std_template/test_glass_contrast.py [contrast] [pixels] [--web DIR] [--report]      (no part = both)

contrast  the live build behind qa/float/mock_float.py on GLASS_QA_PORT (default 9083; 9080–9089 only), 글라스 어둡게 · 밝게 × the four
          palettes × 1440 · 390, blur on (khm.set.glassBlur = on), the header stuck over the map. What the page draws is read from it —
          the glass panel's fill (background-color), its sheen (the radial --gl-sheen: its alpha where the text sits), the backdrop
          filter's saturate() · brightness(), every translucent background between the text and the panel (the tab tray, the selected
          tab's pill, the number plate, a highlighted row), the text colour — and composited over each tile colour the palette can paint
          (its seven stops, 12 steps between each, + the map floor): the drafts/glass.html worst() method — a wide flat tile is the case
          where the blur cannot mix anything in. Checked ≥ 4.5:1:
            header   the 코스피 · 코스닥 · 전체 tab numbers on the tray, the selected tab's name and number on its pill
            tooltip  (1440) every 등락 number in it (head change · NXT · OHLC % · peers), its secondary words (path · list title · hint)
            sheet    the quick view (1440 floating, 390 bottom sheet): the same
          --report prints every worst value and does not fail (use it on an older build: --web /path/to/old/web).
pixels    기본 · 신문 must not change: this build vs main's web/ (git archive) — 390 × 844 and 1440 × 900, the top of the page, the
          header stuck over the map, a tooltip (1440) / the quick view (390); time frozen (page.clock + /api/time), 줄이기, ticker
          paused; a case passes when the new picture equals one of up to three loads of the base (two loads of one build are not
          always alike). Each build behind its own mock (GLASS_QA_PORT and the next port).
Exit 1 on a fail. Chrome runs one page at a time. Ports are stopped with fuser -k.
"""
import argparse
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('GLASS_QA_PORT', 9083))
assert 9080 <= PORT <= 9088, 'ports 9080–9089 (this one and the next)'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PALETTES = ['krg', 'krb', 'global', 'cvd']
FAILS, PASSES, ERRS = [], [], []
REPORT = False


def check(name, ok, detail=''):
    if REPORT:
        print('     ' + name + (f'  — {str(detail)[:300]}' if detail else ''))
        return
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'))


def start(port, web=None):
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    time.sleep(0.3)
    env = dict(os.environ)
    if web: env['FLOAT_WEB'] = str(web)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(80):
        try: NOPROXY.open(f'http://127.0.0.1:{port}/api/time', timeout=1).read(); return
        except Exception: time.sleep(0.1)
    raise SystemExit('mock did not start')


def stop(port):
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)


# ───────────────────────── colour ─────────────────────────
def rgba(s):
    """'rgb(1, 2, 3)' / 'rgba(1, 2, 3, .5)' / 'color(srgb …)' → [r, g, b, a] (0–255, alpha 0–1)"""
    m = re.match(r'color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*/\s*([\d.]+))?\)', s)
    if m:
        return [float(m.group(i)) * 255 for i in (1, 2, 3)] + [float(m.group(4)) if m.group(4) else 1.0]
    v = [float(x) for x in re.findall(r'[\d.]+', s)]
    return v[:3] + [v[3] if len(v) > 3 else 1.0]


def filt(rgb, sat, bri):
    r, g, b = (v / 255 for v in rgb)
    s = sat
    R = (.213 + .787 * s) * r + (.715 - .715 * s) * g + (.072 - .072 * s) * b
    G = (.213 - .213 * s) * r + (.715 + .285 * s) * g + (.072 - .072 * s) * b
    B = (.213 - .213 * s) * r + (.715 - .715 * s) * g + (.072 + .928 * s) * b
    return [max(0, min(255, max(0, min(1, v)) * bri * 255)) for v in (R, G, B)]


def over(f, c):
    return [f[3] * f[i] + (1 - f[3]) * c[i] for i in range(3)]


def lum(rgb):
    f = lambda v: (v / 255) / 12.92 if v / 255 <= .04045 else (((v / 255) + .055) / 1.055) ** 2.4
    r, g, b = map(f, rgb)
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    A, B = lum(a), lum(b)
    return (max(A, B) + .05) / (min(A, B) + .05)


def mix(a, b, t):
    return [x * (1 - t) + y * t for x, y in zip(a, b)]


def ramp(stops, n=12):
    out = []
    for i in range(len(stops) - 1):
        for k in range(n):
            out.append(mix(stops[i], stops[i + 1], k / n))
    out.append(stops[-1])
    return out


def bf(s):
    """backdrop-filter string → (saturate, brightness)"""
    sat = re.search(r'saturate\(([\d.]+)\)', s or '')
    bri = re.search(r'brightness\(([\d.]+)\)', s or '')
    return (float(sat.group(1)) if sat else 1.0, float(bri.group(1)) if bri else 1.0)


def worst(tiles, panel, layers, text):
    """the lowest contrast of text over: tile (→ a scrim) → backdrop filter → panel fill → sheen → layers (outer → inner)"""
    sat, bri = bf(panel['filter'])
    fill = rgba(panel['fill'])
    low = 99.0
    for t in tiles:
        for u in panel.get('under') or []:
            t = over(rgba(u), t)
        c = filt(t, sat, bri) if panel['filter'] not in ('none', '') else t
        c = over(fill, c)
        if panel.get('sheen'):
            c = over([255, 255, 255, panel['sheen']], c)
        for l in layers:
            c = over(rgba(l), c)
        low = min(low, contrast(rgba(text)[:3], c))
    return low


# ───────────────────────── contrast ─────────────────────────
# the panel under an element: its fill, sheen alpha at the element (radial-gradient(130% 70% at 25% 0%, a, 0 60%)), backdrop filter;
# the translucent backgrounds between the element and the panel (outer → inner); the selected tab's pill (a ::before of the scroller)
PROBE = r"""(sel) => {
  const out = [];
  const sheenAt = (img, box, r) => {
    const m = /radial-gradient\(130% 70% at 25% 0%, rgba\(255, 255, 255, ([\d.]+)\), rgba\(255, 255, 255, 0\) 60%\)/.exec(img || '');
    if (!m) return 0;
    const x = r.left + r.width / 2 - box.left, y = r.top + r.height / 2 - box.top;
    const d = Math.hypot((x - .25 * box.width) / (1.3 * box.width), y / (.7 * box.height));
    return Math.max(0, +m[1] * (1 - d / .6));
  };
  const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden' && e.textContent.trim(); };
  for (const [kind, panelSel, pseudo, textSel] of sel) {
    const panel = document.querySelector(panelSel);
    if (!panel) { out.push({ kind, missing: panelSel }); continue; }
    const pcs = getComputedStyle(panel, pseudo || null), box = panel.getBoundingClientRect();
    // a scrim under a phone sheet tints the tiles before the glass sees them
    const sc = kind.startsWith('sheet') && document.querySelector('.scrim'), scs = sc && getComputedStyle(sc);
    const under = scs && scs.display !== 'none' && +scs.opacity > 0 ? [scs.backgroundColor] : [];
    for (const el of panel.querySelectorAll(textSel)) {
      if (!visible(el)) continue;
      // inner → outer: the element, its ancestors up to the panel; the selected tab's pill (the scroller's ::before) sits between the
      // button and the scroller
      const btn = el.closest('.tabs button'), on = !!(btn && btn.getAttribute('aria-pressed') === 'true');
      const inner = [];
      for (let p = el; p && p !== panel; p = p.parentElement) {
        const bg = getComputedStyle(p).backgroundColor;
        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') inner.push(bg);
        if (on && p === btn && !btn.classList.contains('tpin')) {
          const pill = getComputedStyle(btn.parentElement, '::before');
          if (pill.opacity !== '0' && pill.content !== 'none' && pill.backgroundColor !== 'rgba(0, 0, 0, 0)') inner.push(pill.backgroundColor);
        }
      }
      const layers = inner.reverse();
      const r = el.getBoundingClientRect();
      out.push({ kind, text: el.textContent.trim().slice(0, 24), cls: String(el.className), color: getComputedStyle(el).color, layers,
        panel: { fill: pcs.backgroundColor, filter: pcs.backdropFilter || pcs.webkitBackdropFilter || 'none', sheen: sheenAt(pcs.backgroundImage, box, r), under },
        sel: on });
    }
  }
  return out;
}"""

TILES = r"""() => { const p = KH.palette(), probe = document.createElement('i'); document.body.append(probe);
  const rgb = v => { probe.style.color = v; return getComputedStyle(probe).color; };
  const out = { stops: p.stops.map(rgb), floor: rgb(getComputedStyle(document.documentElement).getPropertyValue('--map-bg').trim()), up: rgb(p.upText), dn: rgb(p.dnText) };
  probe.remove(); return out; }"""
BIG = "(() => { const t = [...document.querySelectorAll('#map .tile')].sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0]; const r = t.getBoundingClientRect(); return { c: t.dataset.c, x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 60) }; })()"
UNDER = "(() => { const m = document.getElementById('map').getBoundingClientRect().top + scrollY; scrollTo(0, Math.max(0, m - 40)); return scrollY; })()"
NUMS = ':is(.up,.dn):not(.limtag)'
HEAD2 = '.status :is(.txt,.tshort,.badge), .brand .ttl, .idx > div > span'
SECONDARY = ':is(.card-head .path,.peers .ttl,.tiphint,.card-head .meta > span,.card-head .nmrow small,.card-head .mrow)'


def open_page(br, port, w, theme, palette, extra=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': theme, 'motion': 'reduced', 'tickerPaused': True, 'market': 'K', 'set.glassBlur': 'on', 'palette2': palette}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{palette}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(f'http://127.0.0.1:{port}/')
    pg.wait_for_timeout(2000)
    return ctx, pg


def contrast_part(br, port):
    tot = {}
    for theme in ('glass-dark', 'glass-light'):
        for pal in PALETTES:
            for w in (1440, 390):
                ctx, pg = open_page(br, port, w, theme, pal)
                T = pg.evaluate(TILES)
                tiles = ramp([rgba(s)[:3] for s in T['stops']]) + [rgba(T['floor'])[:3]]
                pg.evaluate(UNDER); pg.wait_for_timeout(400)
                stuck = pg.evaluate("document.querySelector('header.top').classList.contains('is-stuck')")
                rows = pg.evaluate(PROBE, [['tab', 'header.top', '::before', '.tabs-sc > button[data-mkt] :is(.tn,.tp)'], ['head-2nd', 'header.top', '::before', HEAD2]])
                if w == 1440:
                    # the 실시간 badge (the mock's session is closed — set the class the live feed sets)
                    pg.evaluate("(() => { const s = document.getElementById('status'), b = s.querySelector('.badge'); s.classList.add('live'); s.classList.remove('err', 'replay', 'has-basis', 'has-blab'); if (!b.textContent.trim()) b.textContent = '실시간'; })()")
                    rows += pg.evaluate(PROBE, [['head-live', 'header.top', '::before', '.status .badge']])
                    pg.evaluate("document.getElementById('status').classList.remove('live')")
                    b = pg.evaluate(BIG)
                    pg.mouse.move(b['x'], b['y']); pg.wait_for_timeout(500)
                    rows += pg.evaluate(PROBE, [['tip', '.tip', None, NUMS], ['tip-2nd', '.tip', None, SECONDARY]])
                    pg.mouse.move(3, 3); pg.wait_for_timeout(300)
                b = pg.evaluate(BIG)
                pg.evaluate(f"KH.quick({json.dumps(b['c'])})"); pg.wait_for_timeout(700)
                rows += pg.evaluate(PROBE, [['sheet', '.sheet', None, NUMS], ['sheet-2nd', '.sheet', None, SECONDARY]])
                ctx.close()
                for r in rows:
                    if r.get('missing'):
                        continue
                    k = r['kind']
                    if k == 'tab':
                        k = 'tab-sel' if r['sel'] else ('tab-num' if 'tp' in r['cls'] else 'tab-name')
                        if k == 'tab-name':
                            continue       # the unselected names are not 등락 numbers (reported only)
                    v = worst(tiles, r['panel'], r['layers'], r['color'])
                    key = (theme, k)
                    if key not in tot or v < tot[key][0]:
                        tot[key] = (v, f'{w} {pal} "{r["text"]}" layers={r["layers"]} panel={r["panel"]}')
                check(f'contrast [{theme} {pal} {w}]: the header was stuck over the map while measuring', stuck)
    for (theme, k), (v, where) in sorted(tot.items()):
        need = 4.5
        check(f'contrast [{theme}] {k}: worst {v:.2f}:1 over the palettes\' tiles (≥ {need})', v >= need, where)
        if REPORT:
            print(f'       {theme:12s} {k:10s} {v:.2f}  {where[:160]}')
    return tot


# ───────────────────────── pixels (기본 · 신문) ─────────────────────────
def export_web(rev):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='glassweb-'))
    tar = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', rev, 'web'], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(tmp)
    return tmp / 'web'


FIXED = 1763080500000    # 2026-11-14 09:35 KST — every load the same instant


def shoot(br, port, w, theme, scene):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': theme, 'motion': 'reduced', 'tickerPaused': True, 'market': 'K'}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    ctx.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'t': FIXED})))
    pg = ctx.new_page()
    pg.clock.set_fixed_time(FIXED / 1000)
    pg.goto(f'http://127.0.0.1:{port}/'); pg.wait_for_timeout(2200)
    if scene in ('stuck', 'tip', 'sheet'):
        pg.evaluate(UNDER); pg.wait_for_timeout(400)
    if scene == 'tip':
        b = pg.evaluate(BIG); pg.mouse.move(b['x'], b['y']); pg.wait_for_timeout(500)
    if scene == 'sheet':
        b = pg.evaluate(BIG); pg.evaluate(f"KH.quick({json.dumps(b['c'])})"); pg.wait_for_timeout(700)
    png = pg.screenshot(animations='disabled')
    ctx.close()
    return png


def same(a, b):
    from PIL import Image, ImageChops
    A, B = Image.open(io.BytesIO(a)).convert('RGB'), Image.open(io.BytesIO(b)).convert('RGB')
    if A.size != B.size:
        return False, 'size'
    d = ImageChops.difference(A, B)
    ext = max(x[1] for x in d.getextrema())
    return ext <= 2, ext


def pixels_part(br, port, ref):
    start(port + 1, ref)
    try:
        for theme in ('base', 'paper'):
            for w in (390, 1440):
                for scene in ('top', 'stuck', 'tip' if w == 1440 else 'sheet'):
                    new = shoot(br, port, w, theme, scene)
                    ok, det = False, None
                    for _ in range(3):
                        ok, det = same(shoot(br, port + 1, w, theme, scene), new)
                        if ok:
                            break
                    check(f'pixels [{theme} {w} {scene}]: the same picture as main (max channel difference ≤ 2)', ok, det)
    finally:
        stop(port + 1)


def main():
    global REPORT
    ap = argparse.ArgumentParser()
    ap.add_argument('parts', nargs='*')
    ap.add_argument('--web', help='measure another build\'s web/ (e.g. main\'s, for the before numbers)')
    ap.add_argument('--ref', default='main', help='the git rev whose web/ the pixel part compares with')
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    REPORT = a.report
    parts = set(a.parts or ['contrast', 'pixels'])
    from playwright.sync_api import sync_playwright
    start(PORT, a.web)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            if 'contrast' in parts:
                contrast_part(br, PORT)
            if 'pixels' in parts:
                pixels_part(br, PORT, export_web(a.ref))
            br.close()
    finally:
        stop(PORT)
    check(f'console errors: {len(ERRS)}', not ERRS, ERRS[:6])
    if not REPORT:
        print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
        sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
