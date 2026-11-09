"""Horizontal overflow, tile label overflow and console errors for every main view at 360/390/768/1280/1920.
usage: sweep.py [snapshot|live]   (also writes 390 and 1440 screenshots of the main views to qa/heatmap2/shots/)"""
import sys, json
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
LIVE = build == 'live'
URL = 'http://127.0.0.1:8798/' if LIVE else 'file:///home/claude/hm-heatmap/dist/index.html'
WAIT = 3800 if LIVE else 1400
SHOTS = '/home/claude/hm-heatmap/qa/heatmap2/shots/'
WATCH = ['005930', '000660', '035420', '005380', '900300', '179530', '247540', '196170', '068270', '105560', '323990', '035720']
VIEWS = [  # name, hash, localStorage
    ('market', '#kosdaq', {}),
    ('theme', '#theme', {}),
    ('theme-drill', '#theme-12', {}),
    ('watch', '#watch', {'watch': WATCH}),
    ('period', '#kospi', {'colorBy': 'm3'}),
    ('flow', '#all', {'sizeBy': 'fgn', 'flowWin': 5}),
    ('theme-flow', '#theme', {'sizeBy': 'inst', 'flowWin': 20}),
    ('watch-empty', '#watch', {}),
]
VPS = dict(VIEWPORTS); VPS['d1440'] = dict(viewport={'width': 1440, 'height': 900})
bad = 0; total = 0
with sync_playwright() as p:
    b = launch(p)
    for vk in ('m360', 'm390', 't768', 'd1280', 'd1440', 'd1920'):
        ctx = b.new_context(**VPS[vk]); pg = ctx.new_page(); log = Log(); log.attach(pg)
        pg.goto(URL)
        for name, hsh, st in VIEWS:
            js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);"
            for k, v in st.items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
            pg.evaluate(js); pg.goto(URL + hsh); pg.reload(); pg.wait_for_timeout(WAIT)
            r = pg.evaluate("({sw: document.documentElement.scrollWidth, vw: innerWidth, bw: document.body.scrollWidth})")
            lab = pg.evaluate(LABEL_CHECK_JS)
            tiles = pg.evaluate("document.querySelectorAll('#map .tile:not(.leaving)').length")
            # table view too (no page overflow)
            pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
            rt = pg.evaluate("(()=>{const w=document.getElementById('tablewrap');return {sw:document.documentElement.scrollWidth, tsw:w.scrollWidth, tcw:w.clientWidth, rows:w.querySelectorAll('tbody tr').length}})()")
            pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(250)
            cons = [c for c in log.console]; log.console.clear()
            fails = []
            if r['sw'] > r['vw']: fails.append(f"h-overflow {r['sw']}>{r['vw']}")
            if rt['sw'] > r['vw']: fails.append(f"table page overflow {rt['sw']}")
            if vk.startswith('m') and rt['tsw'] > rt['tcw'] + 1: fails.append(f"table h-scroll {rt['tsw']}>{rt['tcw']}")
            if lab['overflow']: fails.append(f"label overflow {lab['overflow']} {lab['examples'][:2]}")
            if cons: fails.append(f'console {cons[:2]}')
            if name != 'watch-empty' and tiles == 0: fails.append('no tiles')
            total += 1; bad += bool(fails)
            print(('FAIL' if fails else 'ok  '), vk, name, f"tiles={tiles} labels={lab['visible']} rows={rt['rows']}", '; '.join(fails))
            if vk in ('m390', 'd1440') and name in ('market', 'theme', 'theme-drill', 'watch', 'period', 'flow', 'watch-empty'):
                pg.evaluate("window.scrollTo(0,0)")
                pg.screenshot(path=f'{SHOTS}{build}-{vk}-{name}.png', full_page=False)
        ctx.close()
    b.close()
print(f'\nSWEEP {total - bad} / {total} clean ({build})')
