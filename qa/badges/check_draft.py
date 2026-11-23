#!/usr/bin/env python3
"""drafts/badges.html 점검: 콘솔 오류 0 · 가로 넘침 0(360 · 390 · 1440 × 네 테마) · 안마다 표식 수 · 비교 스크린샷.

usage: python3 qa/badges/check_draft.py   (포트 BADGES_QA_PORT, 기본 9120 — 9120~9124)
스크린샷은 qa/shots/badges/ (저장소에 올리지 않아요)."""
import http.server, os, pathlib, socketserver, sys, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('BADGES_QA_PORT', '9120'))
SHOTS = ROOT / 'qa/shots/badges'
SHOTS.mkdir(parents=True, exist_ok=True)

class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(ROOT / 'drafts'), **k)
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(('127.0.0.1', PORT), Q)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{PORT}/badges.html'

OVER = """() => {
  const vw = document.documentElement.clientWidth, out = [];
  if (document.documentElement.scrollWidth > vw) out.push('page ' + document.documentElement.scrollWidth + ' > ' + vw);
  // 잘림 · 넘김 상자 밖으로 그려진 요소 (overflow-x:clip로 가려진 넘침도 잡게)
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect(); if (!r.width || r.right <= vw + 0.5) continue;
    let p = el.parentElement, clipped = false;
    while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o !== 'visible') { clipped = true; break; } p = p.parentElement; }
    if (!clipped) out.push((el.id || el.className || el.tagName) + ' right ' + Math.round(r.right));
  }
  // 카드 안(잘리는 상자)에서 카드 밖으로 나간 것 — 표는 자기 상자 안에서 넘겨 보니 빼요
  for (const vb of document.querySelectorAll('.vb')) {
    const R = vb.getBoundingClientRect();
    for (const el of vb.querySelectorAll('*')) {
      if (el.closest('.tablewrap')) continue;
      const r = el.getBoundingClientRect(); if (r.width && r.right > R.right + 1) out.push('card ' + (el.className || el.tagName) + ' +' + Math.round(r.right - R.right));
    }
  }
  return out.slice(0, 8);
}"""
STATS = """() => {
  const q = s => document.querySelectorAll(s).length;
  return { A: q('#phones .bmA'), B: q('#phones .bmB'), C: q('#phones .bmQ'), folds: q('#phones .tile .dm'), tiles: q('#phones .tile'),
    labOver: [...document.querySelectorAll('#phones .tile .lab:not([hidden])')].filter(l => { const t = l.parentElement.getBoundingClientRect(), r = l.getBoundingClientRect(); return r.width > t.width + 1 || r.height > t.height + 1; }).length,
    aria: document.querySelector('#phones .tile[data-c="012450"]').getAttribute('aria-label') };
}"""
fails = 0
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    for W, H in [(360, 780), (390, 844), (1440, 900)]:
        pg = b.new_page(viewport={'width': W, 'height': H})
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(URL); pg.wait_for_timeout(400)
        for th in ['base', 'paper', 'glass-dark', 'glass-light']:
            pg.click(f'#d-theme [data-v="{th}"]'); pg.wait_for_timeout(150)
            for v in ['A', 'B', 'C']:
                pg.click(f'#d-pcv [data-v="{v}"]'); pg.wait_for_timeout(60)
                ov = pg.evaluate(OVER)
                if ov: fails += 1; print(f'FAIL overflow {W} {th} {v}:', ov)
            st = pg.evaluate(STATS)
            if st['labOver']: fails += 1; print(f'FAIL label overflow {W} {th}:', st['labOver'])
        # 밝게: 칩 하나 누르면 흐려지는 타일이 생겨요
        pg.click('#phones .lgc[data-k="hi"]'); pg.wait_for_timeout(80)
        dim = pg.evaluate("() => document.querySelectorAll('#phones .tile.mdim').length")
        if not dim: fails += 1; print('FAIL lit chip did not dim')
        # PC 툴팁: 타일에 올리면 바뀌어요
        if W == 1440:
            pg.click('#d-theme [data-v="base"]'); pg.click('#d-pcv [data-v="A"]'); pg.wait_for_timeout(150)
            pg.hover('#pcfw .tile[data-c="079550"]'); pg.wait_for_timeout(80)
            nm = pg.evaluate("() => document.querySelector('#pcfw .tip .nmrow b').textContent")
            if nm != 'LIG넥스원': fails += 1; print('FAIL tooltip follow', nm)
            pg.mouse.move(5, 5)
        print(W, 'stats', pg.evaluate(STATS), 'console errors', len(errs))
        if errs: fails += 1; print('  ', errs[:5])
        pg.close()
    # 비교 시트 (1440, 기본 · 글라스 밝게)
    pg = b.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=1)
    pg.goto(URL); pg.wait_for_timeout(500)
    pg.add_style_tag(content='.dbar{position:static}'); pg.mouse.move(2, 2)
    for th in ['base', 'glass-light', 'paper', 'glass-dark']:
        pg.click(f'#d-theme [data-v="{th}"]'); pg.wait_for_timeout(250)
        pg.screenshot(path=str(SHOTS / f'sheet-1440-{th}.png'), full_page=True)
    pg.click('#d-theme [data-v="base"]'); pg.wait_for_timeout(200)
    for v in ['A', 'B', 'C']:
        pg.click(f'#d-pcv [data-v="{v}"]'); pg.wait_for_timeout(150)
        pg.locator('#pcfw').screenshot(path=str(SHOTS / f'pc-{v}.png'))
    pg.locator('#phones').screenshot(path=str(SHOTS / 'phones-base.png'))
    pg.locator('#cards').screenshot(path=str(SHOTS / 'cards-base.png'))
    pg.close()
    pg = b.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=2)
    pg.goto(URL); pg.wait_for_timeout(500)
    pg.add_style_tag(content='.dbar{position:static}')
    pg.screenshot(path=str(SHOTS / 'sheet-390.png'), full_page=True)
    b.close()
srv.shutdown()
print('FAIL' if fails else 'OK', fails)
sys.exit(1 if fails else 0)
