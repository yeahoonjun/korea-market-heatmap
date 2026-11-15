#!/usr/bin/env python3
"""Pixel comparison: this worktree's build vs another revision's build (default main) — the main screen must not change.

  python3 qa/ui/compare_main.py            (build first: python3 scripts/build_page.py)

For a change that should be invisible (e.g. src/ui/spring.js, KH.spring — nothing uses it yet). The base revision is exported with
`git archive` into a temp folder and built there (no worktree is touched). Compared: dist/index.html (snapshot, file://) and
web/index.html (live, each build behind its own qa/news/mock_api.py on ports SPRING_CMP_PORTS, default 8941 · 8942), at 390×844
and 1440×900, effect 화려하게 (default) and 줄이기, viewport and full page. Date is frozen to one instant for every load
(page.clock.set_fixed_time, and /api/time answers it), the live page's /api answers are recorded on the base load and replayed to the
new one (the mock dates news · disclosures from the real clock), the ticker is paused, each viewport shot is taken once two in a
row agree (late layout settles), and since two loads of the same build are not always alike (a header row a few px apart, a few
raster px), a case passes when the new build's picture equals one of the base build's (up to 4 interleaved loads each), screenshots use animations="disabled"; under 화려하게 the analog clock face is masked (its second hand sweeps from a server offset
with ms of round-trip jitter — two loads of the same build differ there). Exit 1 if any other pixel differs by more than 2/255 (raster noise, as in qa/disclosure/test_disclosure.py).
Env: SPRING_CMP_BASE (git rev, default main).
"""
import io
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE_REV = os.environ.get('SPRING_CMP_BASE', 'main')
PORTS = [int(p) for p in os.environ.get('SPRING_CMP_PORTS', '8941,8942').split(',')]
assert all(8940 <= p <= 8949 for p in PORTS), 'ports 8940–8949'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SIZES = [(390, 844), (1440, 900)]
MOTIONS = ['fancy', 'reduced']
ROUNDS = 4
OUT = pathlib.Path(os.environ['SPRING_CMP_OUT']) if os.environ.get('SPRING_CMP_OUT') else None   # differing pairs saved here


def build_base():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='spring_base_'))
    arc = subprocess.run(['git', 'archive', '--format=tar', BASE_REV], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(arc)) as tf:
        tf.extractall(tmp, filter='data')
    r = subprocess.run([sys.executable, 'scripts/build_page.py'], cwd=tmp, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rev = subprocess.run(['git', 'rev-parse', '--short', BASE_REV], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return tmp, rev


def serve(web, port):
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    p = subprocess.Popen([sys.executable, str(ROOT / 'qa/news/mock_api.py'), str(port)], env=dict(os.environ, MOCK_WEB=str(web)),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(f'http://127.0.0.1:{port}/__reset', timeout=2).read()
            return p
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f'mock on {port} did not start')


def shoot(br, url, w, h, motion, frozen, tape):
    mobile = w < 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    ctx.clock.set_fixed_time(frozen)
    t_ms = int(frozen.timestamp() * 1000)

    def api(route):
        # the live clock syncs to /api/time (AGENTS §3-17): answer the frozen instant, or the clock · session bar follow the real time.
        # Every other /api answer is recorded on the base load and replayed to the new one: the mock builds news · disclosure times
        # from the real clock at request time, so two loads seconds apart can differ (a 30-minute "new" dot flips) — data, not build.
        u = urllib.parse.urlsplit(route.request.url)
        key = u.path + '?' + u.query
        if u.path == '/api/time':
            return route.fulfill(status=200, content_type='application/json', body='{"t":%d}' % t_ms)
        if key not in tape:
            r = route.fetch()
            tape[key] = (r.status, {k: v for k, v in r.headers.items() if k.lower() in ('content-type', 'etag', 'x-as-of', 'cache-control')}, r.body())
        st, hd, body = tape[key]
        route.fulfill(status=st, headers=hd, body=body)
    ctx.route('**/api/**', api)
    ctx.add_init_script("try{localStorage.setItem('khm.tickerPaused','true');localStorage.setItem('khm.motion',%r)}catch(e){}" % ('"' + motion + '"'))
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' else None)
    pg.goto(url)
    pg.evaluate('document.fonts.ready.then(() => 1)')
    pg.wait_for_timeout(2600)
    pg.mouse.move(1, 1)
    # settled: the same picture twice in a row (late layout — fonts, data cards — can still move a row by a few px at 2.6 s)
    view = pg.screenshot(animations='disabled')
    for _ in range(8):
        pg.wait_for_timeout(400)
        again = pg.screenshot(animations='disabled')
        if again == view:
            break
        view = again
    full = pg.screenshot(animations='disabled', full_page=True)
    spring = pg.evaluate('typeof (window.KH && KH.spring && KH.spring.animate)')
    # 화려하게: the analog second hand sweeps on rAF from the server offset, which carries half a round trip of jitter (ms) —
    # the only part of the screen that differs between two loads of the same build, so it is masked (the hour/minute hands too)
    mask = pg.evaluate("() => [...document.querySelectorAll('svg.xa')].map(e => e.getBoundingClientRect()).filter(r => r.width)"
                       ".map(r => [Math.floor(r.left) - 2, Math.floor(r.top + scrollY) - 2, Math.ceil(r.right) + 2, Math.ceil(r.bottom + scrollY) + 2])") if motion == 'fancy' else []
    ctx.close()
    return {'view': view, 'full': full, 'mask': mask}, errs, spring


def diff(a, b, mask=()):
    a, b = Image.open(io.BytesIO(a)).convert('RGB'), Image.open(io.BytesIO(b)).convert('RGB')
    if a.size != b.size:
        return ('size', a.size, b.size)
    for box in mask:
        a.paste((0, 0, 0), tuple(box)); b.paste((0, 0, 0), tuple(box))
    d = ImageChops.difference(a, b).convert('L')
    hist = d.histogram()
    n = sum(hist[1:])
    if n and OUT:
        OUT.mkdir(parents=True, exist_ok=True)
        k = len(list(OUT.glob('*_base.png')))
        a.save(OUT / f'{k}_base.png'); b.save(OUT / f'{k}_new.png')
    return (n, max((i for i, v in enumerate(hist) if v), default=0), a.size, d.getbbox())


def main():
    base, rev = build_base()
    frozen = datetime.now(timezone.utc).replace(microsecond=0)
    srv = [serve(base / 'web', PORTS[0]), serve(ROOT / 'web', PORTS[1])]
    bad = exact = 0
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            pages = [('snapshot', (base / 'dist/index.html').as_uri(), (ROOT / 'dist/index.html').as_uri()),
                     ('live', f'http://127.0.0.1:{PORTS[0]}/', f'http://127.0.0.1:{PORTS[1]}/')]
            shoot(br, pages[0][2], 1440, 900, 'reduced', frozen, {})   # warm-up: the browser's first load can raster differently
            for label, u_base, u_new in pages:
                for w, h in SIZES:
                    for motion in MOTIONS:
                        # the page itself is not perfectly repeatable (two loads of one build can land a header row a few px apart,
                        # or differ by a few raster px), so a case passes when the new build's picture equals one the base build
                        # produced: up to ROUNDS loads of each, interleaved, stop at the first equal pair
                        tape, B, N, found, errs, kinds = {}, [], [], None, [], set()
                        for rnd in range(ROUNDS):
                            sb, eb, kb = shoot(br, u_base, w, h, motion, frozen, tape)
                            sn, en, kn = shoot(br, u_new, w, h, motion, frozen, tape)
                            B.append(sb); N.append(sn); errs += eb + en; kinds.add((kb, kn))
                            for b in B:
                                for nw in N:
                                    mask = b['mask'] + nw['mask']
                                    res = {k: diff(b[k], nw[k], mask) for k in ('view', 'full')}
                                    if all(isinstance(r[0], int) and r[1] <= 2 for r in res.values()):
                                        found = res; break
                                if found:
                                    break
                            if found:
                                break
                        ok = bool(found) and not errs and kinds == {('undefined', 'function')}
                        bad += not ok
                        exact += ok and all(r[0] == 0 for r in found.values())
                        bb = [diff(B[0][k], b[k], B[0]['mask'] + b['mask'])[:2] for b in B[1:] for k in ('view',)]
                        res = found or {k: diff(B[-1][k], N[-1][k], B[-1]['mask'] + N[-1]['mask']) for k in ('view', 'full')}
                        print(('PASS ' if ok else 'FAIL ') + f'{label} {w}x{h} {motion}: loads {len(B)}+{len(N)} · differing px view {res["view"][0]} '
                              f'(max step {res["view"][1]}), full {res["full"][0]} (max step {res["full"][1]}) {res["full"][2] if len(res["full"]) > 2 else ""}'
                              + (f' · base vs base {bb}' if bb else '') + f' · console errors {len(errs)} · KH.spring base/new {sorted(kinds)}'
                              + (f' · masked analog clock {B[0]["mask"]}' if B[0]['mask'] else '')
                              + (f' · where view {res["view"][3]} full {res["full"][3]}' if not ok and len(res['view']) > 3 else ''), flush=True)
                        if errs:
                            print('   ', errs[:4])
            br.close()
    finally:
        for s in srv:
            s.terminate(); s.wait(5)
        for port in PORTS:
            subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    total = len(SIZES) * len(MOTIONS) * 2
    print(f'{"OK" if not bad else "DIFFERS"}: vs {BASE_REV} ({rev}) — {total - bad}/{total} same ({exact} pixel-identical, {total - bad - exact} within 2/255 raster noise)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
