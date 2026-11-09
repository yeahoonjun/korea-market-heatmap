import sys; sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *
with sync_playwright() as p:
    b = launch(p)
    for build, url in BUILDS.items():
        ctx, pg, log = new_page(b, 'd1280', url, wait=3000)
        print(build, 'd3?', pg.evaluate('typeof d3'), 'font:', pg.evaluate("document.fonts.check('12px \"IBM Plex Sans KR\"')"), pg.evaluate("getComputedStyle(document.body).fontFamily"))
        print(' status:', pg.inner_text('#status'), '| crumbs:', pg.inner_text('#crumbs').replace('\n',' '))
        print(' nodes:', pg.evaluate(NODE_COUNT_JS))
        print(' console:', log.console[:10]); print(' failed:', log.failed[:10])
        print(' reqs:', [r[:80] for r in log.reqs if not r.startswith('data:')][:12])
        ctx.close()
    b.close()
