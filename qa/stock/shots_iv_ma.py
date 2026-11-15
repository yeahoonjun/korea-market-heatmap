#!/usr/bin/env python3
"""Screenshots for the 분 picker + 이동평균 legend (사용자 2026-11-14 08:10 · "이동평균선 … 개선") against the mock API.

    python3 scripts/build_page.py
    python3 qa/stock/shots_iv_ma.py [--before] [--port 8961]

Starts qa/stock/mock_api.py on the port (default 8961), shoots at 390×844 and 1440×900 in every theme, stops the server.
--before: only the chart header + 이동평균 row of the build in web/ (run it on unmodified main for the "before" pictures).
Output → qa/shots/stock_iv_ma/ (git-ignored).
"""
import pathlib, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / 'qa/shots/stock_iv_ma'; OUT.mkdir(parents=True, exist_ok=True)
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8961
BASE = f'http://127.0.0.1:{PORT}/'
BEFORE = '--before' in sys.argv
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
VPS = {390: dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
       1440: dict(viewport={'width': 1440, 'height': 900}, device_scale_factor=1)}
WAIT = "() => { const m = document.querySelector('.sp-chartmsg'); return m && !m.classList.contains('on') && document.querySelector('.sp-legend').textContent.length > 0 }"
WAIT_IV = "(n) => { const c = document.querySelector('.sp-chart'), m = document.querySelector('.sp-chartmsg'); return (c.getAttribute('aria-label') || '').includes(' ' + n + '봉 차트') && m && !m.classList.contains('on'); }"
OPEN = "() => { const m = document.querySelector('.sp-ivm'); return m.dataset.st === 'open' && !m.style.pointerEvents && !m.getAnimations().length; }"


def clip(pg, sel_top, sel_bottom, pad=8, extra=0):
    a = pg.query_selector(sel_top).bounding_box(); z = pg.query_selector(sel_bottom).bounding_box()
    vw = pg.viewport_size['width']
    x0 = max(0, min(a['x'], z['x']) - pad)
    x1 = min(vw, max(a['x'] + a['width'], z['x'] + z['width']) + pad)
    return {'x': x0, 'y': max(0, a['y'] - pad), 'width': x1 - x0, 'height': z['y'] + z['height'] - a['y'] + 2 * pad + extra}


def page(b, w, theme, store=None):
    ctx = b.new_context(**VPS[w])
    init = f"localStorage.setItem('khm.theme', JSON.stringify('{theme}'));"
    for k, v in (store or {}).items():
        init += f"localStorage.setItem('khm.{k}', {v!r});"
    ctx.add_init_script(f"try {{ if (!sessionStorage.getItem('__shot')) {{ sessionStorage.setItem('__shot', '1'); {init} }} }} catch (e) {{}}")
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(BASE + '#s-005930')
    pg.wait_for_function(WAIT, timeout=15000); pg.wait_for_timeout(700)
    return ctx, pg, errs


def shots_before(b):
    for theme in ('base', 'paper'):
        for w in VPS:
            ctx, pg, _ = page(b, w, theme, {'stock.iv': '"day"', 'stock.ma': '{"day":[5,20,60]}'})
            pg.mouse.move(2, 2)
            pg.screenshot(path=str(OUT / f'before_ma_{theme}_{w}.png'), clip=clip(pg, '.sp-tfbar', '.sp-ma', extra=60))
            ctx.close()


def shots_after(b):
    for theme in THEMES:
        for w in VPS:
            # the 분 picker open from 5분 (5분 checked, the box grown out of the tab)
            ctx, pg, errs = page(b, w, theme, {'stock.iv': '"5m"', 'stock.ma': '{"5m":[5,20,60]}'})
            pg.mouse.move(2, 2)
            pg.click('.sp-tfs [data-tf="min"]'); pg.wait_for_function(OPEN, timeout=5000); pg.wait_for_timeout(150)
            pg.screenshot(path=str(OUT / f'picker_open_{theme}_{w}.png'), clip=clip(pg, '.sp-tfbar', '.sp-ivm', extra=24))
            # a 30분 chart (picked in the menu)
            pg.click('.sp-ivm [data-iv="30m"]'); pg.wait_for_function(WAIT_IV, arg='30분', timeout=15000); pg.wait_for_timeout(900)
            pg.mouse.move(2, 2); pg.wait_for_timeout(200)
            pg.screenshot(path=str(OUT / f'chart_30m_{theme}_{w}.png'), clip=clip(pg, '.sp-tfbar', '.sp-chartwrap'))
            # the 이동평균 legend: on and off together (일봉: 5 · 20 · 60 on, 120 off)
            pg.click('.sp-tfs [data-tf="day"]'); pg.wait_for_function(WAIT_IV, arg='일', timeout=15000); pg.wait_for_timeout(500)
            on = pg.evaluate("() => [...document.querySelectorAll('.sp-mac')].map(b => b.getAttribute('aria-pressed'))")
            if on[3] == 'true':
                pg.click('.sp-mac[data-n="120"]')
            pg.mouse.move(2, 2); pg.wait_for_timeout(600)
            pg.screenshot(path=str(OUT / f'ma_row_{theme}_{w}.png'), clip=clip(pg, '.sp-tfbar', '.sp-ma', extra=60))
            if errs:
                print('page errors', theme, w, errs)
            ctx.close()


def mock(path):
    with urllib.request.urlopen(BASE + path.lstrip('/'), timeout=10) as r:
        return r.read()


if __name__ == '__main__':
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), '--port', str(PORT)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            (shots_before if BEFORE else shots_after)(b)
            b.close()
    finally:
        srv.terminate(); srv.wait(5)
    for f in sorted(OUT.glob('before_*.png' if BEFORE else '[!b]*.png')):
        print(f)
