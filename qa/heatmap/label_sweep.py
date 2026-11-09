import sys; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import *
build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
vps = sys.argv[2].split(',') if len(sys.argv) > 2 else list(VIEWPORTS)
summary = {}
with sync_playwright() as p:
    b = launch(p)
    for vk in vps:
        mobile = VIEWPORTS[vk].get('has_touch', False)
        ctx, pg, log = new_page(b, vk, BUILDS[build], wait=3500 if build == 'live' else 1500)
        tot_vis = tot_over = 0; ex = []
        def chk(tag):
            global tot_vis, tot_over
            r = pg.evaluate(LABEL_CHECK_JS)
            tot_vis += r['visible']; tot_over += r['overflow']
            for e in r['examples'][:2]: ex.append((tag, e))
        for mkt in ('Q', 'K'):
            pg.click(f'.tabs button[data-mkt="{mkt}"]'); pg.wait_for_timeout(700)
            for size in ('cap', 'tv'):
                pg.click(f'.seg[data-key="sizeBy"] button[data-v="{size}"]'); pg.wait_for_timeout(700)
                for n in ((100, 300) if build == 'live' else (100, 300, 500)):
                    pg.click(f'.seg[data-key="topN"] button[data-v="{n}"]'); pg.wait_for_timeout(700)
                    chk(f'{mkt}/{size}/{n}/root')
                    secs = pg.evaluate("[...document.querySelectorAll('#map .sec')].map(e=>e.dataset.s)")
                    for s in secs[:4]:
                        pg.evaluate(f"[...document.querySelectorAll('#secs button')].find(b=>b.querySelector('.nm').firstChild.textContent==='{s}').click()"); pg.wait_for_timeout(650)
                        chk(f'{mkt}/{size}/{n}/{s}')
                        inds = pg.evaluate("[...document.querySelectorAll('#map .ind:not(.leaving)')].filter(e=>e.querySelector('.hd').style.display!=='none').map(e=>e.dataset.i)")
                        if inds:
                            pg.click(f'#map .ind[data-i="{inds[0]}"]:not(.leaving) .hd', force=True); pg.wait_for_timeout(650)
                            chk(f'{mkt}/{size}/{n}/{s}/{inds[0]}')
                        pg.keyboard.press('Escape'); pg.wait_for_timeout(100); pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
        summary[vk] = (tot_vis, tot_over)
        print(vk, 'visible labels checked', tot_vis, 'overflowing', tot_over)
        for t, e in ex[:6]: print('   ', t, dump(e)[:330])
        print('   console', log.console[:3])
        ctx.close()
    b.close()
