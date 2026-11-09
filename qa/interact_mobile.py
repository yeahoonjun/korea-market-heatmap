import sys
sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *

BUILD = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
VK = sys.argv[2] if len(sys.argv) > 2 else 'm390'
URL = BUILDS[BUILD]
WAIT = 3500 if BUILD == 'live' else 1500
R = {}
crumbs = lambda pg: pg.inner_text('#crumbs').replace('\n', ' ')
is_open = lambda pg: pg.evaluate("document.querySelector('#sheet').classList.contains('open')")
scrim_open = lambda pg: pg.evaluate("document.querySelector('#scrim').classList.contains('open')")

def step(name, fn, pg):
    try:
        R[name] = fn(pg)
    except Exception as e:
        R[name] = 'EXC ' + repr(e)[:250]
    print(f'[{name}] {dump(R[name])}', flush=True)

def s_tabs(pg):
    pg.locator('.tabs button[data-mkt="K"]').tap(); pg.wait_for_timeout(700)
    a = (pg.evaluate('location.hash'), crumbs(pg)[:30])
    pg.locator('.tabs button[data-mkt="Q"]').tap(); pg.wait_for_timeout(700)
    return a, crumbs(pg)[:30]

def s_tile_sheet(pg):
    out = {}
    t = pg.locator('#map .tile:not(.leaving)').first
    code = t.get_attribute('data-c')
    t.tap(); pg.wait_for_timeout(700 if BUILD == 'snapshot' else 2000)
    out['code'] = code
    out['sheet_open'] = is_open(pg); out['scrim'] = scrim_open(pg)
    out['tip_shown'] = pg.evaluate("document.querySelector('#tip').classList.contains('show')")
    out['sheet_rect'] = pg.evaluate("(()=>{const r=document.querySelector('#sheet').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,innerWidth,innerHeight].map(Math.round)})()")
    out['sheet_scroll'] = pg.evaluate("(()=>{const s=document.querySelector('#sheet');return [s.scrollHeight,s.clientHeight]})()")
    out['acts_visible'] = pg.evaluate("(()=>{const a=document.querySelector('#sheet .acts').getBoundingClientRect();return a.bottom<=innerHeight+1})()")
    out['spark'] = pg.evaluate("(()=>{const s=document.querySelector('#spark');return s?s.innerText:null})()")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_{VK}_sheet.png')
    # close via scrim tap (top of screen, above the sheet)
    pg.touchscreen.tap(20, 60); pg.wait_for_timeout(400)
    out['closed_by_scrim'] = not is_open(pg) and not scrim_open(pg)
    out['tab_changed_by_scrim_tap?'] = crumbs(pg)[:20]
    # close via X
    t.tap(); pg.wait_for_timeout(500)
    pg.locator('#sheet .x').tap(); pg.wait_for_timeout(300)
    out['closed_by_x'] = not is_open(pg)
    # 업종 확대
    pg.locator('#map .tile:not(.leaving)').first.tap(); pg.wait_for_timeout(500)
    pg.locator('#sheet .acts .sec2').tap(); pg.wait_for_timeout(800)
    out['industry_zoom_btn'] = (crumbs(pg)[:60], is_open(pg), scrim_open(pg))
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(600)
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(600)
    out['after_back_x2'] = crumbs(pg)[:30]
    return out

def s_zoom(pg):
    out = {}
    pg.locator('#map .sec[data-s="정보기술"] .hd').tap(); pg.wait_for_timeout(800)
    out['sector'] = crumbs(pg)[:60]
    inds = pg.locator('#map .ind:not(.leaving) .hd').first
    inds.tap(); pg.wait_for_timeout(800)
    out['industry'] = crumbs(pg)[:80]
    out['crumbs_height'] = pg.evaluate("Math.round(document.querySelector('#crumbs').getBoundingClientRect().height)")
    out['labels'] = pg.evaluate(LABEL_CHECK_JS)['overflow']
    pg.screenshot(path=f'{SHOTS}/{BUILD}_{VK}_zoomI_tap.png')
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(600)
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(600)
    out['back'] = crumbs(pg)[:30]
    return out

def s_search(pg):
    out = {}
    pg.locator('#q').tap(); pg.keyboard.type('셀트'); pg.wait_for_timeout(400)
    out['sugg'] = pg.eval_on_selector_all('#sugg button', 'e=>e.map(b=>b.innerText.replace(/\\n/g," "))')[:3]
    out['sugg_rect'] = pg.evaluate("(()=>{const r=document.querySelector('#sugg').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom].map(Math.round)})()")
    out['sugg_row_overflow'] = pg.evaluate("[...document.querySelectorAll('#sugg button')].filter(b=>b.scrollWidth>b.clientWidth+1).length")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_{VK}_search.png')
    pg.locator('#sugg button').first.tap(); pg.wait_for_timeout(900)
    out['after_tap_pick'] = (crumbs(pg)[:60], is_open(pg), scrim_open(pg), pg.input_value('#q'))
    pg.touchscreen.tap(20, 60); pg.wait_for_timeout(300)
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(600)
    return out

def s_hist(pg):
    out = {}
    pg.locator('#hist button').nth(8).tap(); pg.wait_for_timeout(400)
    out['dim'] = pg.evaluate("[document.querySelectorAll('#map .tile.dim').length, document.querySelectorAll('#map .tile').length]")
    pg.locator('#hist button').nth(8).tap(); pg.wait_for_timeout(300)
    out['cleared'] = pg.evaluate("document.querySelectorAll('#map .tile.dim').length")
    return out

def s_sectorlist(pg):
    out = {}
    pg.locator('#secs button').nth(1).tap(); pg.wait_for_timeout(800)
    out['zoom'] = crumbs(pg)[:50]
    out['scrolled_to_map?'] = pg.evaluate("Math.round(document.querySelector('#map').getBoundingClientRect().top)")
    pg.locator('#crumbs .back').tap(); pg.wait_for_timeout(700)
    out['dims_after_back(sticky hover?)'] = pg.evaluate("document.querySelectorAll('#map .tile.dim').length")
    return out

def s_movers(pg):
    pg.locator('#moverTabs button[data-v="dn"]').tap(); pg.wait_for_timeout(200)
    pg.locator('#movers button').first.tap(); pg.wait_for_timeout(600)
    r = dict(open=is_open(pg), scrim=scrim_open(pg), sheet_top=pg.evaluate("Math.round(document.querySelector('#sheet').getBoundingClientRect().top)"))
    pg.touchscreen.tap(20, 30); pg.wait_for_timeout(300)
    return r

def s_controls(pg):
    out = {}
    out['ctls_scroll'] = pg.evaluate("(()=>{const c=document.querySelector('.ctls');return [c.scrollWidth,c.clientWidth]})()")
    out['seg_btn_heights'] = pg.evaluate("[...new Set([...document.querySelectorAll('.seg button,.movers-tabs button,#crumbs button')].map(b=>Math.round(b.getBoundingClientRect().height)))]")
    pg.locator('.seg[data-key="palette"] button[data-v="cvd"]').tap(); pg.wait_for_timeout(400)
    out['palette_tap'] = pg.evaluate("document.querySelector('.seg[data-key=\"palette\"] button[aria-pressed=\"true\"]').dataset.v")
    pg.locator('.seg[data-key="palette"] button[data-v="krg"]').tap(); pg.wait_for_timeout(300)
    pg.locator('.seg[data-key="view"] button[data-v="table"]').tap(); pg.wait_for_timeout(500)
    out['table'] = pg.evaluate("(()=>{const w=document.querySelector('#tablewrap');return {rows:w.querySelectorAll('tbody tr').length, scrollW:w.scrollWidth, clientW:w.clientWidth}})()")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_{VK}_table.png')
    pg.locator('.seg[data-key="view"] button[data-v="map"]').tap(); pg.wait_for_timeout(500)
    return out

with sync_playwright() as p:
    b = launch(p)
    ctx, pg, log = new_page(b, VK, URL, wait=WAIT)
    for name, fn in [('tabs', s_tabs), ('tile_sheet', s_tile_sheet), ('zoom', s_zoom), ('search', s_search), ('hist', s_hist),
                     ('sector_list', s_sectorlist), ('movers', s_movers), ('controls', s_controls)]:
        step(name, fn, pg)
    print('CONSOLE', log.console[:10]); print('FAILED', log.failed[:10])
    ctx.close(); b.close()
