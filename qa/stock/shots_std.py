#!/usr/bin/env python3
"""Before / after screenshots for the stock-page design-standard move (design.md §11 step 3 "종목 페이지", AGENTS §3-31).

  python3 qa/stock/shots_std.py <tag>        e.g.  before  ·  after        (serves this tree's web/ through qa/stock/mock_api.py)

4 themes (기본 · 신문 · 글라스 어둡게 · 글라스 밝게) × 390 · 1440: the page top (header · stats · interval tabs · 이동평균 · chart), the 분 picker
open, and the tabs 호가 · 종목 정보 · 투자자 · 뉴스·공시 (공시). Port STOCK_SHOT_PORT (default 9031; 9030–9039), stopped with fuser -k.
Writes qa/shots/std_stock/<tag>_<theme>_<w>_<scene>.png and prints console errors per page.
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
TAG = sys.argv[1] if len(sys.argv) > 1 else 'after'
PORT = int(os.environ.get('STOCK_SHOT_PORT', 9031))
assert 9030 <= PORT <= 9039, 'ports 9030–9039'
URL = f'http://127.0.0.1:{PORT}/'
OUT = ROOT / 'qa/shots/std_stock'
OUT.mkdir(parents=True, exist_ok=True)
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ONLY = [a for a in sys.argv[2:] if not a.startswith('-')]


def start():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/stock/mock_api.py'), '--port', str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + '__reset', timeout=1).read(); return
        except Exception:
            time.sleep(0.15)
    raise SystemExit('mock did not start')


def shoot(b, theme, w):
    mobile = w <= 760
    ctx = b.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    st = {'theme': theme, 'motion': 'standard', 'stockTab': 'ob', 'stock.iv': 'day', 'stockNewsKind': 'disc'}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    pg.goto(URL)
    pg.wait_for_timeout(700)
    pg.evaluate("() => KHStock.open('005930')")
    pg.wait_for_function("() => { const m = document.querySelector('.sp-chartmsg'); return m && !m.classList.contains('on') && document.querySelector('.sp-legend').textContent.length > 0 }", timeout=15000)
    pg.wait_for_selector('.sp-q span:not(:empty)', timeout=8000)
    pg.wait_for_timeout(500)
    name = lambda s: str(OUT / f'{TAG}_{theme}_{w}_{s}.png')
    pg.screenshot(path=name('top'))
    # the 분 picker, open
    pg.click('.sp-tfs [data-tf="min"]'); pg.wait_for_timeout(700)
    pg.screenshot(path=name('ivm'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # the ☆ group picker (the template's popover, KH.watch.pick) — needs a second group
    pg.evaluate("() => { try { if (KH.watch.groups().length < 2) KH.watch.createGroup('반도체'); } catch (e) {} }")
    pg.click('.sp-star'); pg.wait_for_timeout(700)
    pg.screenshot(path=name('star'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    for tab, sel in (('ob', '.sp-q span:not(:empty)'), ('info', '#sp-p-info .sp-fin-col .b'), ('inv', '#sp-p-inv .sp-today'), ('news', '#sp-p-news .sp-nw-list, #sp-p-news .sp-msgbox')):
        pg.click(f'#sp-t-{tab}')
        pg.wait_for_selector(sel, timeout=8000)
        pg.wait_for_timeout(500)
        if mobile:
            pg.evaluate("() => { const r = document.getElementById('kh-stock'); r.scrollTop = document.querySelector('.sp-tabwrap').offsetTop - 70; }")
            pg.wait_for_timeout(300)
        pg.screenshot(path=name(tab))
    ctx.close()
    return errs


def main():
    start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for theme in THEMES:
                if ONLY and theme not in ONLY:
                    continue
                for w in (390, 1440):
                    e = shoot(b, theme, w)
                    print(theme, w, 'errors:', e[:3])
            b.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)


if __name__ == '__main__':
    main()
