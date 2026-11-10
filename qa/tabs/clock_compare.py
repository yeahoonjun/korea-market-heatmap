"""Map top at 390×844 per clock mode: this build vs a base build (live + snapshot). Usage: clock_compare.py BASE_LIVE BASE_SNAP"""
import json, sys
sys.path.insert(0, '/home/claude/hm-tabs/qa')
from common import launch, VIEWPORTS
from playwright.sync_api import sync_playwright
BUILDS = {'new-live': 'http://127.0.0.1:8812/', 'new-snap': 'file:///home/claude/hm-tabs/dist/index.html',
          'base-live': sys.argv[1], 'base-snap': sys.argv[2]}
G = {"v": 1, "groups": [{"id": "g0", "name": "기본", "codes": ["005930", "000660", "035420"]}], "active": "all"}
res = {}
with sync_playwright() as p:
    b = launch(p)
    for bk, url in BUILDS.items():
        for style, on in (('digital', True), ('analog', True), ('both', True), ('off', False)):
            ctx = b.new_context(**VIEWPORTS['m390']); pg = ctx.new_page(); pg.goto(url)
            pg.evaluate("""([s, on, g]) => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);
              localStorage.setItem('khm.set.clockStyle', JSON.stringify(s)); localStorage.setItem('khm.set.clock', JSON.stringify(on));
              localStorage.setItem('khm.market', JSON.stringify('K')); localStorage.setItem('khm.watchGroups', JSON.stringify(g)); }""", [style if on else 'digital', on, G])
            pg.reload(); pg.wait_for_timeout(2500)
            res.setdefault(bk, {})[style] = pg.evaluate("() => Math.round(document.querySelector('#map').getBoundingClientRect().top + scrollY)")
            ctx.close()
    b.close()
for k, v in res.items(): print(k, json.dumps(v))
for kind in ('live', 'snap'):
    print(kind, 'delta', {s: res[f'new-{kind}'][s] - res[f'base-{kind}'][s] for s in res[f'new-{kind}']})
