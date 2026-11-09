import sys; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import *
with sync_playwright() as p:
    b = launch(p)
    for build in ('snapshot', 'live'):
        for vk in VIEWPORTS:
            ctx, pg, log = new_page(b, vk, BUILDS[build], wait=3000 if build == 'live' else 1200)
            r = []
            for view in ('map', 'table'):
                pg.click(f'.viewseg button[data-v="{view}"]'); pg.wait_for_timeout(300)
                r.append(pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.getElementById('tablewrap').scrollWidth - document.getElementById('tablewrap').clientWidth]"))
            ok = all(x[0] <= x[1] for x in r) and not log.console
            print(build, vk, 'OK' if ok else 'FAIL', r, log.console[:2])
            ctx.close()
    b.close()
