#!/usr/bin/env python3
"""Before / after screenshots for the glass themes' new material (AGENTS §3-38 ④ 리퀴드 글라스 느낌(절제), ux/glass-liquid).

  python3 qa/std_template/glass_shots.py --tag before --web /path/to/old/web     # another build's web/
  python3 qa/std_template/glass_shots.py --tag after                              # this tree's web/

Serves the page with qa/float/mock_float.py on GLASS_QA_PORT (default 9081; 9080–9089 only), stops it with fuser -k.
Writes qa/shots/glass_liquid/<tag>_<w>_<theme>_<what>.png — glass-dark · glass-light × 390 × 844 (phone, DPR 2) · 1440 × 900:
  map    the header stuck over the map (tiles under the glass)
  tip    1440: a tooltip over the map · 390: the 표시 설정 sheet over the map
  pop    1440: the 색 기준 popover over the map · 390: the 가격 기준 · 관심 그룹 popover is a sheet, so the search sheet (🔍)
  sheet  the quick view (desktop: the floating sheet, phone: the bottom sheet) over the map
  dock   390: the phone dock (scrolled past the map) · 1440: the side cards (the card material)
Effect 줄이기 so nothing is caught half-way.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('GLASS_QA_PORT', 9081))
assert 9080 <= PORT <= 9089, 'ports 9080–9089'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/glass_liquid'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['glass-dark', 'glass-light']

BIG = "(() => { const t = [...document.querySelectorAll('#map .tile')].sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0]; const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + Math.min(r.height / 2, 80)]; })()"
# scroll so the map's first rows sit under the stuck header (the glass over tiles — the case the material is for)
# the quick view of the biggest tile (KH.quick — the same as pressing the tile)
QUICK = "(() => { const t = [...document.querySelectorAll('#map .tile')].sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0]; KH.quick(t.dataset.c); })()"
UNDER = "(() => { const m = document.getElementById('map').getBoundingClientRect().top + scrollY; scrollTo(0, Math.max(0, m - 40)); return scrollY; })()"


def start(web=None):
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    env = dict(os.environ)
    if web: env['FLOAT_WEB'] = str(web)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(80):
        try: NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception: time.sleep(0.1)
    raise SystemExit('mock did not start')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True)
    ap.add_argument('--web', help='serve this web/ directory instead of the tree\'s')
    ap.add_argument('--themes', default=','.join(THEMES))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    start(a.web)
    errs = []
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for w, h in ((390, 844), (1440, 900)):
                mobile = w <= 760
                for th in a.themes.split(','):
                    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
                    st = {'theme': th, 'motion': 'reduced', 'tickerPaused': True, 'market': 'K', 'set.glassBlur': 'on'}
                    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
                    pg = ctx.new_page()
                    pg.on('console', lambda m, t=f'{w}/{th}': errs.append(f'{t}: {m.text[:160]}') if m.type == 'error' else None)
                    pg.on('pageerror', lambda e, t=f'{w}/{th}': errs.append(f'{t}: {e}'))
                    pg.goto(URL); pg.wait_for_timeout(2400)
                    base = OUT / f'{a.tag}_{w}_{th}'
                    pg.evaluate(UNDER); pg.wait_for_timeout(500)
                    pg.screenshot(path=f'{base}_map.png')
                    if mobile:
                        pg.click('#setBtn', force=True); pg.wait_for_timeout(600)
                        pg.screenshot(path=f'{base}_tip.png')
                        pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
                        pg.evaluate("document.getElementById('map').scrollIntoView({block:'end'}); scrollBy(0, 400)"); pg.wait_for_timeout(700)
                        pg.screenshot(path=f'{base}_dock.png')
                        k = pg.query_selector('.dock.on .dk-k')
                        if k:
                            k.click(); pg.wait_for_timeout(600)
                            pg.keyboard.type('삼성'); pg.wait_for_timeout(500)
                            pg.screenshot(path=f'{base}_pop.png')
                            pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
                        pg.evaluate(UNDER); pg.wait_for_timeout(400)
                        pg.evaluate(QUICK); pg.wait_for_timeout(800)
                        pg.screenshot(path=f'{base}_sheet.png')
                    else:
                        xy = pg.evaluate(BIG)
                        pg.mouse.move(xy[0], xy[1]); pg.wait_for_timeout(600)
                        pg.screenshot(path=f'{base}_tip.png')
                        pg.mouse.move(5, 5); pg.wait_for_timeout(300)
                        pg.click('.ctl.dd[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(500)
                        pg.screenshot(path=f'{base}_pop.png')
                        pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
                        pg.evaluate(UNDER); pg.wait_for_timeout(300)
                        pg.evaluate(QUICK); pg.wait_for_timeout(800)
                        pg.screenshot(path=f'{base}_sheet.png')
                        pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
                        pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(300)
                        pg.screenshot(path=f'{base}_dock.png', full_page=True)
                    ctx.close()
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f'{a.tag}: shots in {OUT}', '· console errors:', len(errs))
    for e in errs[:10]: print('  ', e)


if __name__ == '__main__':
    main()
