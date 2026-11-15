#!/usr/bin/env python3
"""Before / after screenshots for the extras design-standard move (design.md §11 step 3 "extras", AGENTS §3-31).

  python3 qa/extras/shots_std.py <tag> [web_dir]        e.g.  before /tmp/sx-before-web   ·   after (this tree's web/)

4 themes (기본 · 신문 · 글라스 어둡게 · 글라스 밝게) × 390 · 1440, at a faked KST time: the header (clock · session bar · ticker · tools),
마감 동시호가 (15:20, the moment it starts and a second later), the world clock, the ticker picker, the replay player.
Serves qa/extras/mock_api.py (EXTRAS_WEB=web_dir) on EXTRAS_SHOT_PORT (default 9014; 9010–9019) and stops it (fuser -k).
Writes qa/shots/std_extras/<tag>_<theme>_<w>_<scene>.png.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
TAG = sys.argv[1] if len(sys.argv) > 1 else 'after'
WEB = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / 'web')
PORT = int(os.environ.get('EXTRAS_SHOT_PORT', 9014))
assert 9010 <= PORT <= 9019, 'ports 9010–9019'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_extras'
OUT.mkdir(parents=True, exist_ok=True)
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def start():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/extras/mock_api.py'), str(PORT)], env=dict(os.environ, EXTRAS_WEB=WEB),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + '__reset', timeout=1).read(); return
        except Exception:
            time.sleep(0.15)
    raise SystemExit('mock did not start')


def page_at(b, when, w, theme, motion='standard', paused=True):
    t0 = datetime.datetime.fromisoformat(when + '+09:00').timestamp() * 1000
    real0 = time.time()
    mobile = w <= 760
    ctx = b.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': paused}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.clock.install(time=t0 / 1000)
    pg.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', headers={'cache-control': 'no-store'},
                                                 body=json.dumps({'t': t0 + (time.time() - real0) * 1000})))
    pg.goto(URL)
    pg.wait_for_function('() => document.querySelectorAll("#map .tile").length > 50 && document.querySelector(".xc-btn") && document.querySelector("#strip .xs-item")', timeout=20000)
    pg.wait_for_timeout(1200)
    return ctx, pg, errs


def shot(pg, name, clip=None, full_top=None):
    path = OUT / f'{TAG}_{name}.png'
    if clip:
        pg.screenshot(path=str(path), clip=clip)
    else:
        vw, vh = pg.evaluate('[innerWidth, innerHeight]')
        pg.screenshot(path=str(path), clip={'x': 0, 'y': 0, 'width': vw, 'height': min(vh, full_top or vh)})


def run(b):
    errs_all = []
    for theme in THEMES:
        for w in (390, 1440):
            tag = f'{theme}_{w}'
            # ① the header at 10:30 (오전장): clock · session bar · ticker · tools, and the map's top edge
            ctx, pg, errs = page_at(b, '2026-11-13T10:30:05', w, theme)
            m = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top)")
            print(tag, 'map top', m, flush=True)
            shot(pg, f'{tag}_head', full_top=340 if w <= 760 else 300)
            # the session bar's note (hover / focus)
            pg.focus('.sb'); pg.wait_for_timeout(500)
            shot(pg, f'{tag}_sbtip', full_top=340 if w <= 760 else 300)
            pg.evaluate("document.activeElement.blur()"); pg.wait_for_timeout(300)
            # ② the world clock
            pg.evaluate("document.querySelector('#clock button').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 60, clientY: 30}))")
            pg.wait_for_timeout(900)
            shot(pg, f'{tag}_world', full_top=844 if w <= 760 else 520)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
            # ③ the ticker picker (표시 설정 › 티커 항목 고르기)
            pg.click('#setBtn' if w <= 760 else '#moreBtn'); pg.wait_for_timeout(800)
            if pg.evaluate("!!document.querySelector('.xk-open')"):
                pg.click('.xk-open'); pg.wait_for_timeout(1000)
                shot(pg, f'{tag}_picker')
                pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
            # ④ the replay player
            rb = pg.query_selector('#extras-tools [data-x="replay"]')
            if rb:
                rb.click(); pg.wait_for_function("() => document.querySelector('.rp-time') && document.querySelector('.rp-time').textContent === '09:00'", timeout=15000)
                pg.wait_for_timeout(900)
                pg.evaluate("document.activeElement.blur()")
                vw, vh = pg.evaluate('[innerWidth, innerHeight]')
                hh = 230 if w <= 760 else 200
                pg.screenshot(path=str(OUT / f'{TAG}_{tag}_replay.png'), clip={'x': 0, 'y': vh - hh, 'width': vw, 'height': hh})
                if w <= 760:
                    pg.click('.rp-more'); pg.wait_for_timeout(500)
                    pg.screenshot(path=str(OUT / f'{TAG}_{tag}_replay_more.png'), clip={'x': 0, 'y': vh - 300, 'width': vw, 'height': 300})
            errs_all += [f'{tag}: {e}' for e in errs]
            ctx.close()
            # ⑤ 마감 동시호가: 15:19:59.6 → the cue starts; one shot 300 ms in (the old glow's peak), one at rest
            ctx, pg, errs = page_at(b, '2026-11-13T15:19:58.9', w, theme)
            pg.wait_for_function("() => document.querySelector('.xc-btn').classList.contains('xc-auc')", timeout=8000)
            pg.wait_for_timeout(300)
            r = pg.evaluate("(() => { const b = document.querySelector('.xc-btn').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; })()")
            clip = {'x': max(0, r[0] - 30), 'y': max(0, r[1] - 20), 'width': r[2] + 60, 'height': r[3] + 40}
            shot(pg, f'{tag}_auc_start', clip=clip)
            pg.wait_for_timeout(1800)
            shot(pg, f'{tag}_auc_rest', clip=clip)
            errs_all += [f'{tag} auc: {e}' for e in errs]
            ctx.close()
    print('page errors:', errs_all or 0)


def main():
    start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(b)
            b.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)


if __name__ == '__main__':
    main()
