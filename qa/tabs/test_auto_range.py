#!/usr/bin/env python3
"""§3-27 색 범위 자동 — QA on the built pages.

  python3 scripts/build_page.py && python3 qa/tabs/test_auto_range.py [--base REV|PATH] [--shots DIR]

Snapshot checks run on dist/index.html (file://). Live checks start qa/world/mock_api.py on AUTO_RANGE_PORT (default 8831; it serves
this worktree's web/ + /api/quotes from data/snapshot.json + /api/world from qa/world/fixtures) and serve d3 / Pretendard from the repo
instead of the CDNs. --base: the page the manual-range picture must still match pixel for pixel (a git rev whose dist/index.html is
used, default: the merge base with main; or a path to an index.html). Screenshots go to --shots (default /tmp) as auto_range_*.png.
Exit code 1 if any check fails.
"""
import argparse
import base64
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STEPS = [1, 2, 3, 4, 5, 7, 10, 15, 20, 30]
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
SNAP = (ROOT / 'dist/index.html').as_uri()
PORT = int(os.environ.get('AUTO_RANGE_PORT', 8831))
LIVE = f'http://127.0.0.1:{PORT}/'
VP = {360: 740, 390: 844, 768: 1024, 1280: 800, 1920: 1080}
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ap = argparse.ArgumentParser()
ap.add_argument('--base', default=None)
ap.add_argument('--shots', default=os.environ.get('AUTO_RANGE_SHOTS', '/tmp'))
ARGS = ap.parse_args()
SHOTS = pathlib.Path(ARGS.shots)
SHOTS.mkdir(parents=True, exist_ok=True)

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


# ── expected values, computed here from the same data the pages draw ──
def p95(vals):
    a = sorted(abs(v) for v in vals if v is not None)
    if not a:
        return None
    i = (len(a) - 1) * 0.95
    lo = math.floor(i)
    hi = min(len(a) - 1, lo + 1)
    return a[lo] + (a[hi] - a[lo]) * (i - lo)


def step_of(p):
    return next((s for s in STEPS if s >= p - 1e-9), STEPS[-1])


SNAPDATA = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))


def market_top(m, n):
    pool = [s for s in SNAPDATA['stocks'] if (m == 'ALL' or s['m'] == m) and s['c'].endswith('0') and s.get('cap', 0) > 0]
    pool.sort(key=lambda s: -s['cap'])
    return [s['r'] for s in pool[:n]]


EXP = {f'{m}:{n}': p95(market_top(m, n)) for m in ('K', 'Q', 'ALL') for n in (100, 300)}
WFIX = {k: json.loads((ROOT / f'qa/world/fixtures/world_{k}.json').read_text(encoding='utf-8')) for k in ('index', 'commodity')}
EXP['WORLD'] = p95([it['ratio'] for g in WFIX['index']['groups'] for it in g['items'] if not it.get('ref') and it.get('ratio') is not None])
EXP['CMDTY'] = p95([it['ratio'] for g in WFIX['commodity']['groups'] for it in g['items'] if not it.get('ref') and it.get('ratio') is not None])
print('expected p95 → step:', {k: (round(v, 3), step_of(v)) for k, v in EXP.items()}, flush=True)

# ── browser helpers ──
D3 = (ROOT / 'src/vendor/d3-7.9.0.min.js').read_bytes()
FONT_CSS = ("@font-face{font-family:'Pretendard Variable';font-weight:45 920;font-style:normal;font-display:swap;src:url(data:font/woff2;base64,"
            + base64.b64encode((ROOT / 'src/fonts/PretendardVariable-subset.woff2').read_bytes()).decode() + ") format('woff2-variations')}").encode()


class Errors:
    def __init__(self):
        self.items = []

    def attach(self, page, tag):
        page.on('pageerror', lambda e: self.items.append(f'{tag} pageerror: {e}'))
        page.on('console', lambda m: self.items.append(f'{tag} console: {m.text[:160]}') if m.type == 'error' else None)


ERR = Errors()


def context(browser, w, live):
    opts = dict(viewport={'width': w, 'height': VP.get(w, 900)})
    if w <= 760:
        opts.update(is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx = browser.new_context(**opts)
    if live:
        hdr = {'access-control-allow-origin': '*'}
        ctx.route('https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js', lambda r: r.fulfill(status=200, body=D3, headers={**hdr, 'content-type': 'application/javascript'}))
        ctx.route('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@*/**', lambda r: r.fulfill(status=200, body=FONT_CSS, headers={**hdr, 'content-type': 'text/css'}))
        ctx.route('**/api/time', lambda r: r.fulfill(status=200, body=json.dumps({'t': int(time.time() * 1000)}), headers={'content-type': 'application/json', 'cache-control': 'no-store'}))
    return ctx


def open_page(browser, w, url, storage=None, live=False, tag='', wait=1400):
    ctx = context(browser, w, live)
    pg = ctx.new_page()
    ERR.attach(pg, tag or f'{w}')
    pg.goto(url)
    pg.evaluate("""s => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);
      for (const [k, v] of Object.entries(s || {})) localStorage.setItem(k, JSON.stringify(v)); }""", storage or {})
    pg.reload()
    pg.wait_for_timeout(wait)
    return ctx, pg


INFO = """() => { const lg = document.querySelector(document.documentElement.classList.contains('is-world') ? '#world .kw-legend' : '#legend');
  const ra = lg && lg.querySelector('.rauto');
  return { ri: KH.rangeInfo(), rauto: ra ? ra.textContent : null, ticks: lg ? [...lg.querySelectorAll('.tk')].map(t => t.textContent) : [],
    seg: [...document.querySelectorAll('#rangeseg button')].map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : '')),
    store: { range: localStorage.getItem('khm.range'), rangeW: localStorage.getItem('khm.rangeW') },
    ov: document.documentElement.scrollWidth - innerWidth }; }"""
MINUS = '−'


def go(pg, mkt, wait=900):
    pg.click(f'.tabs button[data-mkt="{mkt}"]')
    pg.wait_for_timeout(wait)


def press_range(pg, v):
    # 1280+: the toolbar shows the control; below that it lives in the 표시 설정 sheet (open it, press, close)
    vis = pg.evaluate("() => { const b = document.querySelector('#rangeseg'); return !!(b && b.getClientRects().length && b.getBoundingClientRect().width); }")
    if not vis:
        pg.click('#setBtn')
        pg.wait_for_timeout(350)
    pg.click(f'#rangeseg button[data-v="{v}"]')
    pg.wait_for_timeout(300)
    if not vis:
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)


def legend_ok(i, value):
    return i['rauto'] == f'자동 ±{value}%' and i['ticks'][:1] == [f'{MINUS}{value}%'] and (f'+{value}%' in i['ticks'])


def snapshot_checks(b):
    # 1 · fresh profile: 자동 is the default, the p95 of the 코스닥 top 300 is rounded up, the legend says so
    ctx, pg = open_page(b, 1280, SNAP, tag='snap1280')
    i = pg.evaluate(INFO)
    exp = EXP['Q:300']
    check('fresh profile → 자동 is the default', i['ri']['pick'] == 'auto' and i['ri']['auto'] and i['seg'][0] == '자동*' and i['store']['range'] is None, json.dumps(i['seg'], ensure_ascii=False))
    check('p95 of 코스닥 top 300 matches (snapshot)', abs(i['ri']['p95'] - exp) < 0.01, f"page {i['ri']['p95']:.4f} · expected {exp:.4f}")
    check('rounded up to the step ladder', i['ri']['value'] == step_of(exp), f"{exp:.3f} → {i['ri']['value']} (expected {step_of(exp)})")
    check('legend shows "자동 ±N%" and the ends', legend_ok(i, i['ri']['value']), f"{i['rauto']} · {i['ticks']}")
    # the scale is clamped at ±value: the end colour from there on, not before (d3 gives rgb() strings, so compare scale outputs)
    sc = pg.evaluate("""v => { const hi = KH.colorOf(1000), lo = KH.colorOf(-1000);
      return {top: KH.colorOf(v) === hi, bot: KH.colorOf(-v) === lo, inside: KH.colorOf(v * 0.9) !== hi && KH.colorOf(-v * 0.9) !== lo}; }""", i['ri']['value'])
    check('colour scale ends at the auto value', all(sc.values()), json.dumps(sc))
    for m, key in (('K', 'K:300'), ('ALL', 'ALL:300')):
        go(pg, m)
        j = pg.evaluate(INFO)
        check(f'{m} tab: own auto value', j['ri']['scope'] == key and j['ri']['value'] == step_of(EXP[key]) and legend_ok(j, j['ri']['value']),
              f"{j['ri']['scope']} p95 {j['ri']['p95']:.3f} → {j['ri']['value']}")
    # 2 · hysteresis + one 상한가 among flat items (the snapshot's 해외 tab draws nothing, so the feed is ours alone)
    go(pg, 'WORLD')
    seq = [[3.9, 4], [4.1, 5], [3.9, 5], [3.5, 5], [3.3, 4], [3.5, 4], [4.0, 4], [4.01, 5], [0.5, 1], [0, 1], [31, 30], [25, 30], [24, 30], [16.9, 20]]
    got = pg.evaluate("""seq => { let ev = 0; const on = () => ev++; document.addEventListener('kh:palette', on);
      const out = seq.map(([x]) => { const e0 = ev; const v = KH.feedRange('index', Array(20).fill(x)); return [v, ev - e0]; });
      document.removeEventListener('kh:palette', on); return out; }""", seq)
    vals = [g[0] for g in got]
    want = [s[1] for s in seq]
    check('hysteresis: up at once, down only 15 % under the lower step', vals == want, f'got {vals} want {want}')
    moved = [vals[k] != (vals[k - 1] if k else None) for k in range(len(vals))]
    ev_ok = all((g[1] > 0) == mv for g, mv in zip(got[1:], moved[1:]))
    check("'kh:palette' only when the step moves", ev_ok, str([g[1] for g in got]))
    go(pg, 'CMDTY')
    one = pg.evaluate("() => KH.feedRange('commodity', [...Array(39).fill(1), 30])")
    check('one limit-up among ±1 % items does not wash out the scale', one == 1, f'value {one}')
    ctx.close()

    # 3 · manual choices are kept apart: 국내 (khm.range) · 해외 · 원자재 (khm.rangeW)
    for w in (1280, 390):
        ctx, pg = open_page(b, w, SNAP, tag=f'snapmem{w}')
        press_range(pg, '5')
        a = pg.evaluate(INFO)
        go(pg, 'WORLD')
        bw = pg.evaluate(INFO)
        press_range(pg, '3')
        c = pg.evaluate(INFO)
        go(pg, 'Q')
        d = pg.evaluate(INFO)
        pg.reload()
        pg.wait_for_timeout(1200)
        e = pg.evaluate(INFO)
        go(pg, 'WORLD')
        f = pg.evaluate(INFO)
        press_range(pg, 'auto')
        g = pg.evaluate(INFO)
        ok = (a['store'] == {'range': '5', 'rangeW': None} and bw['ri']['pick'] == 'auto' and c['store'] == {'range': '5', 'rangeW': '3'}
              and d['ri']['pick'] == 5 and d['ri']['value'] == 5 and d['rauto'] is None and d['ticks'][:1] == [f'{MINUS}5%']
              and e['ri']['pick'] == 5 and f['ri']['pick'] == 3 and g['store']['rangeW'] == '"auto"' and g['store']['range'] == '5')
        check(f'{w}: 국내 and 해외·원자재 remember their own manual choice', ok,
              f"국내 {a['store']} · 해외 {bw['ri']['pick']}→{c['store']} · back {d['ri']['pick']}/{d['rauto']} · reload {e['ri']['pick']}/{f['ri']['pick']} · 자동 {g['store']}")
        ctx.close()

    # 4 · a saved manual choice from before 자동 stays; 해외 starts on 자동
    ctx, pg = open_page(b, 1280, SNAP, storage={'khm.range': 10}, tag='snapsaved')
    i = pg.evaluate(INFO)
    go(pg, 'WORLD')
    j = pg.evaluate(INFO)
    check('an already saved ±10 % stays manual; 해외 is 자동', i['ri']['pick'] == 10 and i['ri']['value'] == 10 and i['rauto'] is None and i['seg'][3] == '±10%*'
          and j['ri']['pick'] == 'auto', f"국내 {i['ri']['pick']} {i['seg']} · 해외 {j['ri']['pick']}")
    ctx.close()


def base_html():
    if ARGS.base and pathlib.Path(ARGS.base).exists():
        return pathlib.Path(ARGS.base).as_uri()
    rev = ARGS.base
    try:
        if not rev:
            rev = subprocess.run(['git', 'merge-base', 'HEAD', 'main'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        html = subprocess.run(['git', 'show', f'{rev}:dist/index.html'], cwd=ROOT, capture_output=True, check=True).stdout
    except Exception as e:      # no git / no main: skip
        print('base page unavailable:', e)
        return None
    out = pathlib.Path(tempfile.gettempdir()) / f'auto_range_base_{rev[:10]}.html'
    out.write_bytes(html)
    return out.as_uri()


def pixel_checks(b):
    # with a manual ±3 % (the old default) the base theme draws exactly what it drew before: map, legend, side cards
    base = base_html()
    if not base:
        check('manual ±3 %: base theme pixel-identical to the base page', False, 'no base page')
        return
    shots = {}
    for tag, url in (('base', base), ('new', SNAP)):
        ctx, pg = open_page(b, 1280, url, storage={'khm.range': 3}, tag='px' + tag, wait=1800)
        shots[tag] = {sel: pg.locator(sel).screenshot(animations='disabled') for sel in ('#map', '#legend', '.side')}
        ctx.close()
    for sel in ('#map', '#legend', '.side'):
        a, c = shots['base'][sel], shots['new'][sel]
        detail = f'{len(a)} vs {len(c)} bytes'
        if sel == '.side' and a != c:
            # .side starts right under the toolbar: the drop shadow of the keys after 색 범위 (they sit a few px further right now)
            # spills into its top rows — compare from 12 px down, which is all side-panel paint
            try:
                import io
                from PIL import Image, ImageChops
                ia, ic = (Image.open(io.BytesIO(x)).convert('RGB') for x in (a, c))
                crop = lambda im: im.crop((0, 12, im.width, im.height))
                box = ImageChops.difference(crop(ia), crop(ic)).getbbox() if ia.size == ic.size else 'size'
                detail = f'below the toolbar shadow: diff {box}'
                a = c if box is None else a
            except ImportError:
                detail += ' (PIL missing)'
        check(f'manual ±3 %: {sel} pixel-identical to the base page', a == c, detail)


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    proc = subprocess.Popen([sys.executable, str(ROOT / 'qa/world/mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            NOPROXY.open(LIVE + '__reset', timeout=1).read()
            return proc
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise SystemExit(f'mock on :{PORT} did not start')


def live_checks(b):
    # 5 · 코스닥 → 해외 → 원자재 → 코스닥 on the live page (mock Worker): each tab its own auto value, legends follow
    for w in (1280, 390):
        n = 300 if w >= 761 else 100
        ctx, pg = open_page(b, w, LIVE, live=True, tag=f'live{w}', wait=2600)
        q = pg.evaluate(INFO)
        key = f'Q:{n}'
        check(f'live {w}: 코스닥 auto = p95 of top {n} rounded up', q['ri']['scope'] == key and abs(q['ri']['p95'] - EXP[key]) < 0.01
              and q['ri']['value'] == step_of(EXP[key]) and legend_ok(q, q['ri']['value']), f"{q['ri']} {q['rauto']}")
        check(f'live {w}: 국내 no horizontal overflow', q['ov'] == 0, f"{q['ov']}px")
        pg.screenshot(path=str(SHOTS / f'auto_range_{w}_kosdaq.png'), full_page=w >= 761)
        if w < 761:
            pg.locator('#legend').scroll_into_view_if_needed()
            pg.wait_for_timeout(200)
            pg.screenshot(path=str(SHOTS / f'auto_range_{w}_kosdaq_legend.png'))
            pg.evaluate('() => scrollTo(0, 0)')
            pg.click('#setBtn')
            pg.wait_for_timeout(400)
            sh = pg.evaluate("""() => { const s = document.querySelector('#rangeseg'); const r = s.getBoundingClientRect();
              return {w: Math.round(r.width), sw: s.scrollWidth, cw: s.clientWidth, right: Math.round(r.right), vw: innerWidth,
                      h: Math.min(...[...s.children].map(b => b.getBoundingClientRect().height))}; }""")
            pg.screenshot(path=str(SHOTS / f'auto_range_{w}_sheet.png'))
            check(f'live {w}: 표시 설정 sheet — the four range keys fit, tall enough to tap', sh['sw'] <= sh['cw'] + 1 and sh['right'] <= sh['vw'] and sh['h'] >= 32, json.dumps(sh))
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(300)
        go(pg, 'WORLD', 1800)
        wv = pg.evaluate(INFO)
        rows = pg.evaluate("() => document.querySelectorAll('#world .kw-lr').length")
        check(f'live {w}: 해외 gets its own auto value', wv['ri']['scope'] == 'WORLD' and abs(wv['ri']['p95'] - EXP['WORLD']) < 0.01
              and wv['ri']['value'] == step_of(EXP['WORLD']) and wv['ri']['value'] != q['ri']['value'] and rows > 0,
              f"코스닥 ±{q['ri']['value']} → 해외 ±{wv['ri']['value']} (p95 {wv['ri']['p95']:.3f}, {rows} rows)")
        check(f'live {w}: 해외 legend shows "자동 ±N%"', legend_ok(wv, wv['ri']['value']), f"{wv['rauto']} · {wv['ticks']}")
        chip = pg.evaluate("""() => { const d = [...document.querySelectorAll('#world .kw-lr')].map(r => r.querySelector('.kw-pchip')).filter(Boolean)[0];
          return d ? getComputedStyle(d).backgroundColor : null; }""")
        check(f'live {w}: 해외 no horizontal overflow', wv['ov'] == 0, f"{wv['ov']}px · chip {chip}")
        pg.screenshot(path=str(SHOTS / f'auto_range_{w}_world.png'), full_page=w >= 761)
        go(pg, 'CMDTY', 1800)
        cv = pg.evaluate(INFO)
        check(f'live {w}: 원자재 auto value', cv['ri']['scope'] == 'CMDTY' and cv['ri']['value'] == step_of(EXP['CMDTY']) and legend_ok(cv, cv['ri']['value']),
              f"p95 {cv['ri']['p95']:.3f} → ±{cv['ri']['value']}")
        go(pg, 'Q', 1200)
        q2 = pg.evaluate(INFO)
        check(f'live {w}: back on 코스닥 the scale returns', q2['ri']['value'] == q['ri']['value'] and legend_ok(q2, q2['ri']['value']), f"±{q2['ri']['value']}")
        # a poll with the same data must not move the step (no flicker): count kh:palette over a refresh
        ev = pg.evaluate("""async () => { let n = 0; const on = () => n++; document.addEventListener('kh:palette', on);
          await KH.refresh(); await new Promise(r => setTimeout(r, 600)); document.removeEventListener('kh:palette', on); return n; }""")
        check(f'live {w}: a refresh with the same data keeps the step (no kh:palette)', ev == 0, f'{ev} events')
        ctx.close()
    # 6 · other widths: no overflow on 국내 and 해외
    for w in (360, 768, 1920):
        ctx, pg = open_page(b, w, LIVE, live=True, tag=f'live{w}', wait=2200)
        a = pg.evaluate(INFO)
        go(pg, 'WORLD', 1500)
        c = pg.evaluate(INFO)
        check(f'live {w}: no horizontal overflow (국내 · 해외)', a['ov'] == 0 and c['ov'] == 0, f"{a['ov']} · {c['ov']}")
        ctx.close()


def theme_checks(b):
    # 7 · all four themes: the tag renders, reads (contrast vs the page), nothing overflows, the toolbar stays one line at 1280
    for th in THEMES:
        for w in (1280, 390):
            ctx, pg = open_page(b, w, LIVE, storage={'khm.theme': th}, live=True, tag=f'{th}{w}', wait=2400)
            r = pg.evaluate("""() => { const ra = document.querySelector('#legend .rauto'); if (!ra) return null;
              const b = ra.getBoundingClientRect();
              const rgb = s => { const c = document.createElement('canvas').getContext('2d'); c.fillStyle = s; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data].slice(0, 3); };
              const L = c => { const f = v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; const [r, g, bb] = c.map(f); return .2126 * r + .7152 * g + .0722 * bb; };
              const fg = rgb(getComputedStyle(ra).color), bg = rgb(getComputedStyle(document.documentElement).getPropertyValue('--page').trim() || '#000');
              const a = L(fg), z = L(bg);
              return { w: Math.round(b.width), h: Math.round(b.height), text: ra.textContent, contrast: +((Math.max(a, z) + .05) / (Math.min(a, z) + .05)).toFixed(2),
                       theme: document.documentElement.dataset.theme, tools: Math.round(document.querySelector('.tools').getBoundingClientRect().height),
                       map: Math.round(document.querySelector('#map').getBoundingClientRect().top + scrollY), ov: document.documentElement.scrollWidth - innerWidth }; }""")
            ok = bool(r) and r['theme'] == th and r['w'] > 30 and r['h'] >= 14 and r['contrast'] >= 4.5 and r['ov'] == 0 and (w < 1280 or r['tools'] <= 48)
            check(f'theme {th} {w}: legend tag renders and reads', ok, json.dumps(r, ensure_ascii=False))
            if w == 1280:
                pg.screenshot(path=str(SHOTS / f'auto_range_theme_{th}.png'), full_page=True)
            ctx.close()


def main():
    proc = start_mock()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            snapshot_checks(b)
            pixel_checks(b)
            live_checks(b)
            theme_checks(b)
            b.close()
    finally:
        proc.kill()
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check('no console errors', not ERR.items, '; '.join(ERR.items[:6]))
    bad = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed · screenshots in {SHOTS}/auto_range_*.png')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
