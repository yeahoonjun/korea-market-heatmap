"""Quick look: console errors + screenshots. usage: probe.py URL tag [hash] [width] [height]"""
import sys; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log
from playwright.sync_api import sync_playwright
url, tag = sys.argv[1], sys.argv[2]
hsh = sys.argv[3] if len(sys.argv) > 3 else ''
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1440
H = int(sys.argv[5]) if len(sys.argv) > 5 else 900
mob = W < 600
with sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={'width': W, 'height': H}, is_mobile=mob, has_touch=mob, device_scale_factor=2 if mob else 1)
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    pg.goto(url + hsh); pg.wait_for_timeout(4000 if 'http' in url else 1800)
    pg.screenshot(path=f'/home/claude/hm-heatmap/qa/heatmap2/shots/{tag}.png', full_page=mob)
    print('console', log.console[:8]); print('failed', [f for f in log.failed if 'favicon' not in f][:5])
    print(pg.evaluate("({tiles:document.querySelectorAll('#map .tile').length, crumbs:document.querySelector('#crumbs').textContent, legend:document.querySelector('#legend').textContent, sw:document.documentElement.scrollWidth, vw:innerWidth})"))
    b.close()
