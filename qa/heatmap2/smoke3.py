"""quick probe: console errors, overflow, map top, status/basis per viewport, both builds. usage: smoke3.py [snapshot|live] [vp…]"""
import os; HM_BASE = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')   # dev Worker (harness) port
import sys, json
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, VIEWPORTS
from playwright.sync_api import sync_playwright
build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
vps = sys.argv[2:] or ['m360', 'm390', 't768', 'd1280', 'd1920']
URL = HM_BASE if build == 'live' else 'file:///home/claude/hm-heatmap/dist/index.html'
ICON = "#extras-tools .xt-btn{width:40px!important;height:40px!important;padding:0!important}#extras-tools .xt-btn span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}"
with sync_playwright() as p:
    b = launch(p)
    for vp in vps:
        ctx = b.new_context(**(VIEWPORTS.get(vp) or dict(viewport={'width': 1440, 'height': 900}))); pg = ctx.new_page(); log = Log(); log.attach(pg)
        pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k)"); pg.reload()
        pg.wait_for_timeout(4000 if build == 'live' else 1500)
        if vp.startswith('m'): pg.add_style_tag(content=ICON); pg.wait_for_timeout(300)
        r = pg.evaluate("""() => ({
          over: document.documentElement.scrollWidth - innerWidth,
          mapTop: Math.round(document.getElementById('map').getBoundingClientRect().top),
          status: document.getElementById('status').innerText.replace(/\\n/g,' | '),
          basis: !document.getElementById('basis').hidden,
          tabsOver: (t => t.scrollWidth - t.clientWidth)(document.querySelector('.tabs')),
          rows: [...new Set([...document.querySelectorAll('.top > *, .tools > *, .stagebar > *')].filter(e=>e.offsetParent).map(e => Math.round(e.getBoundingClientRect().top)))],
          scope: document.getElementById('breadthScope').textContent, note: document.getElementById('histNote').textContent,
        })""")
        print(build, vp, json.dumps(r, ensure_ascii=False))
        pg.screenshot(path=f'/home/claude/hm-heatmap/qa/heatmap2/shots3/{build}-{vp}.png')
        errs = [c for c in log.console if 'error' in c]
        if errs or [f for f in log.failed if 'HTTP 4' in f or 'HTTP 5' in f]: print('  ERR', errs[:4], log.failed[:4])
        ctx.close()
