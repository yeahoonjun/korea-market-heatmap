import sys; sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *
res = {}
with sync_playwright() as p:
    b = launch(p)
    for build, url in BUILDS.items():
        for vk, opts in VIEWPORTS.items():
            ctx, pg, log = new_page(b, vk, url, wait=3500 if build == 'live' else 1500)
            mobile = opts.get('has_touch', False)
            key = f'{build}_{vk}'
            r = {}
            pg.screenshot(path=f'{SHOTS}/{key}_view.png')
            pg.screenshot(path=f'{SHOTS}/{key}_full.png', full_page=True)
            r['overview'] = pg.evaluate(LABEL_CHECK_JS)
            r['nodes0'] = pg.evaluate(NODE_COUNT_JS)
            # horizontal overflow of the document
            r['docOverflowX'] = pg.evaluate('document.documentElement.scrollWidth - innerWidth')
            # zoom into biggest sector
            sec = pg.locator('#map .sec:not(.leaving) .hd').first
            secname = sec.evaluate('e => e.parentElement.dataset.s')
            (sec.tap() if mobile else sec.click())
            pg.wait_for_timeout(900)
            r['sector'] = secname
            r['sectorZoom'] = pg.evaluate(LABEL_CHECK_JS)
            pg.screenshot(path=f'{SHOTS}/{key}_zoomS.png')
            ind = pg.locator('#map .ind:not(.leaving) .hd').first
            if ind.count():
                indname = ind.evaluate('e => e.parentElement.dataset.i')
                (ind.tap() if mobile else ind.click())
                pg.wait_for_timeout(900)
                r['industry'] = indname
                r['indZoom'] = pg.evaluate(LABEL_CHECK_JS)
                pg.screenshot(path=f'{SHOTS}/{key}_zoomI.png')
            r['console'] = log.console; r['failed'] = log.failed
            res[key] = r
            print(key, dump({k: (v if not isinstance(v, dict) or 'examples' not in v else {kk: vv for kk, vv in v.items() if kk != 'examples'}) for k, v in r.items()}))
            ctx.close()
    b.close()
json.dump(res, open('/home/claude/heatmap/qa/shots_result.json', 'w'), ensure_ascii=False, indent=1)
