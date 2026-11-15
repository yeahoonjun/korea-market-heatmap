#!/usr/bin/env python3
"""Before / after screenshots for the 해외 · 지표 design-standard move (design.md §11 step 3 "해외 · 지표", AGENTS §3-31).

  python3 qa/world/shots_std.py <tag> [web_dir]     e.g.  before /tmp/main-web (git archive main web | tar -x)  ·  after (this tree's web/)

4 themes (기본 · 신문 · 글라스 어둡게 · 글라스 밝게) × 390 · 1440: 해외 목록, 해외 세계지도, 지표 목록 (환율 · 금리 · 증시 자금 on), and the
detail sheet (S&P 500, with its chart). Serves qa/world/mock_api.py (this tree's web/) on WORLD_SHOT_PORT (default 9041; 9040–9049)
with the world atlas from qa/world/fixtures, and stops it (fuser -k). Writes qa/shots/std_world/<tag>_<theme>_<w>_<scene>.png.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / 'qa/world'
TAG = sys.argv[1] if len(sys.argv) > 1 else 'after'
WEB = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / 'web')
PORT = int(os.environ.get('WORLD_SHOT_PORT', 9041))
assert 9040 <= PORT <= 9049, 'ports 9040–9049'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_world'
OUT.mkdir(parents=True, exist_ok=True)
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
ATLAS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json'
ATLAS = (HERE / 'fixtures/countries-110m.json').read_bytes()
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def start():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], env=dict(os.environ, WORLD_WEB=WEB), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + '__reset', timeout=1).read()
            NOPROXY.open(URL + '__mode?macro=on&funds=on', timeout=1).read()
            return
        except Exception:
            time.sleep(0.15)
    raise SystemExit('mock did not start')


def page(b, w, theme, hsh, view='list', motion='standard'):
    mobile = w <= 760
    ctx = b.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    st = {'khm.theme': json.dumps(theme), 'khm.motion': json.dumps(motion), 'khm.worldView': view, 'khm.tickerPaused': 'true'}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in st.items()) + '}catch(e){}')
    ctx.route(ATLAS_URL, lambda r: r.fulfill(status=200, body=ATLAS, headers={'content-type': 'application/json', 'access-control-allow-origin': '*'}))
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' else None)
    pg.goto(URL + '#' + hsh)
    sel = '#world .kw-gsvg' if view == 'map' else '#world .kw-lr'
    pg.wait_for_selector(sel, timeout=20000)
    pg.wait_for_timeout(1200)
    return ctx, pg, errs


def shot(pg, name):
    pg.screenshot(path=str(OUT / f'{TAG}_{name}.png'))


def run(b):
    errs_all = []
    for theme in THEMES:
        for w in (390, 1440):
            tag = f'{theme}_{w}'
            ctx, pg, errs = page(b, w, theme, 'world')
            shot(pg, f'{tag}_list')
            # the detail sheet: S&P 500 with its 3-month chart
            pg.click('#world .kw-lr[data-k="INX"]')
            pg.wait_for_selector('.kw-sheet:not([hidden]) .kw-svg', timeout=10000)
            pg.wait_for_timeout(900)
            shot(pg, f'{tag}_sheet')
            ctx.close(); errs_all += errs
            ctx, pg, errs = page(b, w, theme, 'world', view='map')
            shot(pg, f'{tag}_map')
            ctx.close(); errs_all += errs
            ctx, pg, errs = page(b, w, theme, 'cmdty')
            shot(pg, f'{tag}_cmdty')
            ctx.close(); errs_all += errs
            print(tag, 'ok', flush=True)
    print('console / page errors:', len(errs_all), errs_all[:4])


if __name__ == '__main__':
    start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(b)
            b.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
