#!/usr/bin/env python3
"""Before / after screenshots for the 뉴스 · 공시 design-standard move (design.md §11 step 3 "뉴스 · 공시", AGENTS §3-31).

  python3 qa/news/shots_std.py <tag> [web_dir]     e.g.  before /tmp/nd-before-web (git archive <rev> web | tar -x)  ·  after (this tree's web/)

4 themes (기본 · 신문 · 글라스 어둡게 · 글라스 밝게) × 390 · 1440, one Chrome at a time:
  news   — the card on 시장 뉴스 (mock news=stale: one outlet's last copy → the tab's ! and the note line), element shot of #news
  more   — 더보기 open (30 rows), element shot
  disc   — the 오늘 공시 tab (kind tabs · 지도 종목만 · the map switch · rows), element shot
  on     — the map switch on: the viewport with the dimmed map above the tab (1440) / the tab (390)
  tip    — 1440: the map tooltip of 삼성전자 with its 공시 block; 390: the quick view (bottom sheet) from a 공시 row's chip
Serves qa/news/mock_api.py (MOCK_WEB = web_dir) on NEWS_SHOT_PORT (default 9053; 9050–9059) and stops it (fuser -k).
Writes qa/shots/std_news/<tag>_<theme>_<w>_<scene>.png (gitignored) and prints console / page errors.
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
HERE = ROOT / 'qa/news'
TAG = sys.argv[1] if len(sys.argv) > 1 else 'after'
WEB = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / 'web')
PORT = int(os.environ.get('NEWS_SHOT_PORT', 9053))
assert 9050 <= PORT <= 9059, 'ports 9050–9059'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_news'
OUT.mkdir(parents=True, exist_ok=True)
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SETTLE = "() => Promise.race([Promise.all(document.getAnimations().map(a => a.finished.catch(() => 0))), new Promise(r => setTimeout(r, 2500))])"


def mock(path):
    return NOPROXY.open(URL + path.lstrip('/'), timeout=5).read()


def start():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], env=dict(os.environ, MOCK_WEB=WEB), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            mock('__reset'); return
        except Exception:
            time.sleep(0.15)
    raise SystemExit('mock did not start')


def page(b, w, theme):
    mobile = w <= 760
    ctx = b.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    st = {'khm.theme': json.dumps(theme), 'khm.motion': json.dumps('standard'), 'khm.tickerPaused': 'true', 'khm.market': json.dumps('K'), 'khm.feedTab': json.dumps('news')}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=20000)
    pg.wait_for_timeout(900)
    return ctx, pg, errs


def settle(pg, ms=250):
    pg.mouse.move(2, 2)
    pg.wait_for_timeout(ms)
    pg.evaluate(SETTLE)


def card(pg, name):
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})")
    settle(pg)
    pg.locator('#news').screenshot(path=str(OUT / f'{TAG}_{name}.png'))


def run(b):
    errs_all = []
    for theme in THEMES:
        for w in (390, 1440):
            tag = f'{theme}_{w}'
            mock('__reset'); mock('__mode?news=stale&disc=ok')
            ctx, pg, errs = page(b, w, theme)
            card(pg, f'{tag}_news')
            pg.click('#news .nw-more'); pg.wait_for_timeout(900)
            card(pg, f'{tag}_more')
            pg.click('#news .nw-more'); pg.wait_for_timeout(900)
            pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})")
            pg.click('#news-t-disc')
            pg.wait_for_selector('#news .dc-row:not(.skel)', timeout=10000)
            card(pg, f'{tag}_disc')
            # the switch on: the dimmed map above the tab (PC) — the tab row in the middle of the screen
            (pg.tap if w <= 760 else pg.click)('#news .dc-lit'); pg.wait_for_timeout(500)
            pg.evaluate("(() => { const s = document.querySelector('#news-p-disc .dc-sub'); scrollTo(0, Math.max(0, s.getBoundingClientRect().top + scrollY - innerHeight * (innerWidth > 760 ? .62 : .35))); })()")
            settle(pg, 400)
            pg.screenshot(path=str(OUT / f'{TAG}_{tag}_on.png'))
            (pg.tap if w <= 760 else pg.click)('#news .dc-lit'); pg.wait_for_timeout(400)
            if w > 760:
                pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(200)
                r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + Math.min(40, r.width / 2), r.y + Math.min(30, r.height / 2)]; })()")
                pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(700)
                pg.evaluate(SETTLE)
                pg.screenshot(path=str(OUT / f'{TAG}_{tag}_tip.png'))
            else:
                pg.evaluate("document.querySelector('#news .dc-row .dc-chip').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
                pg.tap('#news .dc-row .dc-chip'); pg.wait_for_timeout(800)
                pg.evaluate(SETTLE)
                pg.screenshot(path=str(OUT / f'{TAG}_{tag}_tip.png'))
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
