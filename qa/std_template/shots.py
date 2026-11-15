#!/usr/bin/env python3
"""Before / after screenshots for the template's move to the design standard (roadmap 6, step template — ux/std-template).

  python3 qa/std_template/shots.py --tag before [--rev main]     # the web/ of a git rev (exported to a temp dir)
  python3 qa/std_template/shots.py --tag after                    # this tree's web/

Serves the page with qa/float/mock_float.py on STD_QA_PORT (default 9029; 9020–9029 only), stops it with fuser -k.
Writes qa/shots/std_template/<tag>_<w>_<theme>_<what>.png: 390 × 844 (phone, DPR 2) and 1440 × 900, the four themes —
top of the page, the full page, a tooltip over the biggest tile (1440) and the 표시 설정 sheet (390). Effect 줄이기 so nothing is
caught half-way.
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
PORT = int(os.environ.get('STD_QA_PORT', 9029))
assert 9020 <= PORT <= 9029, 'ports 9020–9029'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_template'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']


def export_web(rev):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='stdweb-'))
    tar = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', rev, 'web'], capture_output=True, check=True).stdout
    p = tmp / 'w.tar'; p.write_bytes(tar)
    with tarfile.open(p) as t: t.extractall(tmp)
    return tmp / 'web'


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
    ap.add_argument('--rev')
    ap.add_argument('--extra', default='{}', help='more khm.* keys as JSON, e.g. {"groupBy":"cap"}')
    a = ap.parse_args()
    extra = json.loads(a.extra)
    OUT.mkdir(parents=True, exist_ok=True)
    start(export_web(a.rev) if a.rev else None)
    errs = []
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for w, h in ((390, 844), (1440, 900)):
                mobile = w <= 760
                for th in THEMES:
                    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
                    st = {'theme': th, 'motion': 'reduced', 'tickerPaused': True, 'market': 'K'}
                    st.update(extra)
                    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
                    pg = ctx.new_page()
                    pg.on('console', lambda m, t=f'{w}/{th}': errs.append(f'{t}: {m.text[:160]}') if m.type == 'error' else None)
                    pg.on('pageerror', lambda e, t=f'{w}/{th}': errs.append(f'{t}: {e}'))
                    pg.goto(URL); pg.wait_for_timeout(2400)
                    base = OUT / f'{a.tag}_{w}_{th}'
                    pg.screenshot(path=f'{base}_top.png')
                    pg.screenshot(path=f'{base}_full.png', full_page=True)
                    if mobile:
                        pg.click('#setBtn'); pg.wait_for_timeout(500)
                        pg.screenshot(path=f'{base}_settings.png')
                    else:
                        box = pg.evaluate("(() => { const t = [...document.querySelectorAll('#map .tile')].sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0]; const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
                        pg.mouse.move(box[0], box[1]); pg.wait_for_timeout(500)
                        pg.screenshot(path=f'{base}_tip.png')
                        pg.mouse.move(5, 5)
                        pg.click('#moreBtn'); pg.wait_for_timeout(400)
                        pg.screenshot(path=f'{base}_more.png', clip={'x': 700, 'y': 0, 'width': 740, 'height': 640})
                    ctx.close()
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f'{a.tag}: shots in {OUT}', '· console errors:', len(errs))
    for e in errs[:10]: print('  ', e)


if __name__ == '__main__':
    main()
