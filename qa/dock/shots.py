#!/usr/bin/env python3
"""Before / after screenshots for the phone dock (아래 막대) and its 🔍 search sheet on the design standard (design.md §11 ③ "… 아래 막대",
ux/std-dock, docs/standards/dock.md).

  python3 qa/dock/shots.py --tag before [--rev main]     # the web/ of a git rev (exported to a temp dir)
  python3 qa/dock/shots.py --tag after                    # this tree's web/

Serves the page with qa/float/mock_float.py on DOCK_SHOT_PORT (default 9061; 9060–9069 only), stops it with fuser -k. One Chrome.
Writes qa/shots/std_dock/<tag>_<w>_<theme>_<what>.png for the four themes × 360 × 780 · 390 × 844 (DPR 2, touch), effect 줄이기 so
nothing is caught half-way:
  dock   the screen once the map has gone by (the dock up, page 1: 지수 + 등락 분포)
  dockz  the bottom 96px of that screen (the dock itself)
  page2  the dock's page 2 (관심 + the other market's index), bottom 96px
  sheet  🔍 → the search sheet with "삼성" typed
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('DOCK_SHOT_PORT', 9061))
assert 9060 <= PORT <= 9069, 'ports 9060–9069'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_dock'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
SIZES = ((360, 780), (390, 844))
# a few watchlist names so page 2's 관심 cell has numbers
WATCH = {'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': ['005930', '000660', '035420', '005380']}], 'active': 'all'}


def export_web(rev):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='dockweb-'))
    tar = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', rev, 'web'], capture_output=True, check=True).stdout
    p = tmp / 'w.tar'; p.write_bytes(tar)
    with tarfile.open(p) as t:
        t.extractall(tmp)
    return tmp / 'web'


def start(web=None):
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    env = dict(os.environ)
    if web:
        env['FLOAT_WEB'] = str(web)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


REVEAL = """() => { const m = document.getElementById('map').getBoundingClientRect(); scrollTo(0, Math.round(m.bottom + scrollY - innerHeight + 72 + 24)); }"""
UP = "() => getComputedStyle(document.querySelector('.dock')).visibility === 'visible'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True)
    ap.add_argument('--rev')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    start(export_web(a.rev) if a.rev else None)
    errs, miss = [], []
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for w, h in SIZES:
                for th in THEMES:
                    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True, device_scale_factor=2)
                    st = {'theme': th, 'motion': 'reduced', 'tickerPaused': True, 'market': 'K', 'watchGroups': WATCH}
                    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
                    pg = ctx.new_page()
                    pg.on('console', lambda m, t=f'{w}/{th}': errs.append(f'{t}: {m.text[:160]}') if m.type == 'error' else None)
                    pg.on('pageerror', lambda e, t=f'{w}/{th}': errs.append(f'{t}: {e}'))
                    pg.goto(URL); pg.wait_for_timeout(2400)
                    pg.evaluate(REVEAL); pg.wait_for_timeout(700)
                    if not pg.evaluate(UP):
                        miss.append(f'{w}/{th}')
                    base = OUT / f'{a.tag}_{w}_{th}'
                    pg.screenshot(path=f'{base}_dock.png')
                    pg.screenshot(path=f'{base}_dockz.png', clip={'x': 0, 'y': h - 96, 'width': w, 'height': 96})
                    pg.evaluate("() => { const p = document.querySelector('.dk-pages'); p.scrollLeft = p.clientWidth; }")
                    pg.wait_for_timeout(500)
                    pg.screenshot(path=f'{base}_page2.png', clip={'x': 0, 'y': h - 96, 'width': w, 'height': 96})
                    pg.evaluate("() => { const p = document.querySelector('.dk-pages'); p.scrollLeft = 0; }")
                    pg.wait_for_timeout(300)
                    pg.click('.dk-k'); pg.wait_for_timeout(500)
                    pg.keyboard.type('삼성'); pg.wait_for_timeout(500)
                    pg.screenshot(path=f'{base}_sheet.png')
                    ctx.close()
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f'{a.tag}: shots in {OUT}', '· console errors:', len(errs), '· dock not up:', miss or 'none')
    for e in errs[:10]:
        print('  ', e)


if __name__ == '__main__':
    main()
