import sys, traceback
sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *

BUILD = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
URL = BUILDS[BUILD]
WAIT = 3500 if BUILD == 'live' else 1200
R = {}

def T(name):
    def deco(fn):
        def run(pg, log):
            try:
                out = fn(pg, log)
            except Exception as e:
                out = 'EXC ' + repr(e)[:300]
            R[name] = out
            print(f'[{name}] {dump(out)}', flush=True)
        run.__name__ = name
        return run
    return deco

crumbs = lambda pg: pg.inner_text('#crumbs').replace('\n', ' ')
nodes = lambda pg: pg.evaluate(NODE_COUNT_JS)
def settle(pg, ms=800): pg.wait_for_timeout(ms)
def click_tab(pg, m): pg.click(f'.tabs button[data-mkt="{m}"]'); settle(pg)
def seg(pg, key, v): pg.click(f'.seg[data-key="{key}"] button[data-v="{v}"]'); settle(pg)

@T('market_tabs_and_hash')
def t1(pg, log):
    out = {'init': (pg.evaluate('location.hash'), crumbs(pg))}
    click_tab(pg, 'K'); out['K'] = (pg.evaluate('location.hash'), crumbs(pg), nodes(pg)['tiles'])
    click_tab(pg, 'ALL'); out['ALL'] = (pg.evaluate('location.hash'), crumbs(pg), nodes(pg)['tiles'])
    pg.go_back(); settle(pg); out['back1'] = (pg.evaluate('location.hash'), crumbs(pg))
    pg.go_back(); settle(pg); out['back2_to_initial_nohash'] = (pg.evaluate('location.hash'), crumbs(pg))
    pg.go_forward(); settle(pg); out['fwd'] = (pg.evaluate('location.hash'), crumbs(pg))
    pg.evaluate("location.hash='#kosdaq'"); settle(pg); out['set#kosdaq'] = crumbs(pg)
    return out

@T('direct_hash_load')
def t2(pg, log):
    pg.goto(URL + '#all'); settle(pg, WAIT)
    a = crumbs(pg)
    pg.goto(URL + '#kospi'); pg.reload(); settle(pg, WAIT)
    b = crumbs(pg)
    pg.goto(URL + '#bogus'); pg.reload(); settle(pg, WAIT)
    return {'#all': a, '#kospi': b, '#bogus': crumbs(pg), 'tabs': pg.eval_on_selector_all('.tabs button', 'e=>e.map(b=>b.textContent+":"+b.getAttribute("aria-pressed"))')}

@T('controls')
def t3(pg, log):
    pg.goto(URL + '#kosdaq'); settle(pg, WAIT)
    out = {}
    for n in ([100, 200, 300] + ([500] if BUILD == 'snapshot' else [])):
        seg(pg, 'topN', n); out[f'top{n}'] = nodes(pg)
    seg(pg, 'topN', 300)
    pg.hover('.tile'); c0 = pg.eval_on_selector('.tile[data-c="196170"]', 'e=>e.style.backgroundColor')
    cs = [c0]
    for pal in ('krb', 'global', 'cvd'):
        seg(pg, 'palette', pal); cs.append(pg.eval_on_selector('.tile[data-c="196170"]', 'e=>e.style.backgroundColor'))
    out['alteogen(-16%)_colors krg/krb/global/cvd'] = cs
    out['palette_buttons'] = pg.eval_on_selector_all('#palseg button', 'e=>e.map(b=>b.dataset.v+":"+b.textContent)')
    out['wavg color var'] = pg.evaluate("getComputedStyle(document.querySelector('#wavg')).color")
    seg(pg, 'palette', 'krg')
    for r in (5, 10, 3):
        seg(pg, 'range', r); out[f'range{r}_axis'] = pg.inner_text('#histAxis').replace('\n', ' ')
    seg(pg, 'sizeBy', 'tv'); out['tv'] = (nodes(pg), pg.inner_text('#foot')[:60])
    seg(pg, 'sizeBy', 'cap')
    # preferred excluded
    out['preferred_tiles'] = pg.evaluate("[...document.querySelectorAll('#map .tile')].map(e=>e.dataset.c).filter(c=>!c.endsWith('0'))")
    return out

@T('kospi_wavg_and_headers')
def t4(pg, log):
    out = {}
    for m in ('K', 'Q', 'ALL'):
        click_tab(pg, m)
        out[m] = {'wavg': pg.inner_text('#wavg'), 'stat': pg.inner_text('#crumbs .stat'),
                  'secHeaders': pg.evaluate("Object.fromEntries([...document.querySelectorAll('#map .sec:not(.leaving)')].map(e=>[e.dataset.s, e.querySelector('.hd .v').textContent]))"),
                  'sideSecs': pg.eval_on_selector_all('#secs button', 'e=>e.slice(0,4).map(b=>b.innerText.replace(/\\n/g," "))')}
    return out

@T('zoom_and_crumbs')
def t5(pg, log):
    click_tab(pg, 'Q')
    out = {}
    pg.click('#map .sec[data-s="정보기술"] .hd'); settle(pg)
    out['sector'] = (crumbs(pg), nodes(pg), pg.inner_text('#wavg'), pg.inner_text('#breadthScope'))
    pg.click('#map .ind[data-i="반도체와반도체장비"] .hd'); settle(pg)
    out['industry'] = (crumbs(pg), nodes(pg), pg.inner_text('#wavg'))
    out['industry_zoom_headers'] = pg.evaluate("[...document.querySelectorAll('#map .sec:not(.leaving) .hd, #map .ind:not(.leaving) .hd')].map(h=>h.innerText.replace(/\\n/g,' '))")
    pg.click('#crumbs .back'); settle(pg); out['back'] = crumbs(pg)
    pg.keyboard.press('Escape'); settle(pg); out['esc'] = crumbs(pg)
    # crumb button to sector
    pg.click('#map .sec[data-s="헬스케어"] .hd'); settle(pg)
    pg.click('#map .ind:not(.leaving) .hd'); settle(pg)
    pg.click('#crumbs button.c >> nth=1'); settle(pg); out['crumb_to_sector'] = crumbs(pg)
    pg.click('#crumbs button.c >> nth=0'); settle(pg); out['crumb_to_root'] = (crumbs(pg), nodes(pg))
    return out

@T('tooltip')
def t6(pg, log):
    out = {}
    el = pg.locator('#map .tile[data-c="196170"]')
    bb = el.bounding_box()
    pg.mouse.move(bb['x'] + 10, bb['y'] + 10); pg.mouse.move(bb['x'] + 20, bb['y'] + 20); settle(pg, 300)
    out['shown'] = pg.evaluate("document.querySelector('#tip').classList.contains('show')")
    out['text'] = pg.inner_text('#tip').replace('\n', ' | ')[:300]
    out['tipRect'] = pg.evaluate("(()=>{const r=document.querySelector('#tip').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,innerWidth,innerHeight].map(Math.round)})()")
    # bottom-right tile → tooltip should stay within viewport
    tiles = pg.evaluate("[...document.querySelectorAll('#map .tile')].map(e=>{const r=e.getBoundingClientRect();return [e.dataset.c,r.right,r.bottom,r.width,r.height]}).filter(x=>x[2]<innerHeight-5).sort((a,b)=>(b[1]+b[2])-(a[1]+a[2]))[0]")
    pg.mouse.move(tiles[1] - 3, tiles[2] - 3); pg.mouse.move(tiles[1] - 2, tiles[2] - 2); settle(pg, 300)
    out['tipRect_bottomright'] = pg.evaluate("(()=>{const r=document.querySelector('#tip').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,innerWidth,innerHeight].map(Math.round)})()")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_d1280_tooltip.png')
    # peer industry % in tooltip vs header on map
    pg.mouse.move(bb['x'] + 25, bb['y'] + 25); settle(pg, 200)
    out['tip_ind_pct'] = pg.inner_text('#tip .peers .ttl')
    out['map_ind_hdr'] = pg.evaluate("(()=>{const e=document.querySelector('#map .ind[data-i=\"생물공학\"] .hd');return e&&e.innerText.replace(/\\n/g,' ')})()")
    out['tip_peers'] = pg.eval_on_selector_all('#tip .peer .nm', 'e=>e.map(x=>x.textContent)')
    pg.mouse.move(2, 2); settle(pg, 200)
    out['hidden_after_leave'] = not pg.evaluate("document.querySelector('#tip').classList.contains('show')")
    return out

@T('sheet')
def t7(pg, log):
    out = {}
    pg.click('#map .tile[data-c="196170"]'); settle(pg, 1500)
    out['open'] = pg.evaluate("document.querySelector('#sheet').classList.contains('open')")
    out['sel'] = pg.evaluate("[...document.querySelectorAll('#map .tile.sel')].map(e=>e.dataset.c)")
    out['text'] = pg.inner_text('#sheet').replace('\n', ' | ')[:260]
    out['naver_href'] = pg.get_attribute('#sheet a.pri', 'href')
    out['spark'] = pg.evaluate("(()=>{const s=document.querySelector('#spark');return s?{svg:!!s.querySelector('svg'),note:s.innerText}:null})()")
    out['rect'] = pg.evaluate("(()=>{const r=document.querySelector('#sheet').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom].map(Math.round)})()")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_d1280_sheet.png')
    out['focus_in_sheet'] = pg.evaluate("document.querySelector('#sheet').contains(document.activeElement)")
    pg.click('#sheet .acts button.sec2'); settle(pg)
    out['after_zoom_btn'] = (crumbs(pg), pg.evaluate("document.querySelector('#sheet').classList.contains('open')"))
    pg.keyboard.press('Escape'); settle(pg); pg.keyboard.press('Escape'); settle(pg)
    return out

@T('esc_order')
def t8(pg, log):
    out = {}
    pg.click('#map .sec[data-s="정보기술"] .hd'); settle(pg)
    pg.click('#hist button >> nth=8'); settle(pg, 300)
    pg.click('#map .tile:not(.leaving) >> nth=0'); settle(pg, 500)
    st = lambda: dict(sheet=pg.evaluate("document.querySelector('#sheet').classList.contains('open')"),
                      bucket=pg.evaluate("[...document.querySelectorAll('#hist button')].findIndex(b=>b.getAttribute('aria-pressed')==='true')"),
                      dims=pg.evaluate("document.querySelectorAll('#map .tile.dim').length"), crumbs=crumbs(pg)[:40])
    out['0'] = st()
    for i in range(1, 4):
        pg.keyboard.press('Escape'); settle(pg, 600); out[str(i)] = st()
    return out

@T('search')
def t9(pg, log):
    out = {}
    click_tab(pg, 'Q')
    pg.click('body', position={'x': 5, 'y': 5})
    pg.keyboard.press('/'); out['slash_focus'] = pg.evaluate("document.activeElement.id")
    pg.keyboard.type('에코'); settle(pg, 300)
    out['sugg'] = pg.eval_on_selector_all('#sugg button', 'e=>e.map(b=>b.innerText.replace(/\\n/g," "))')
    out['dimmed_while_typing'] = pg.evaluate("[document.querySelectorAll('#map .tile.dim').length, document.querySelectorAll('#map .tile').length]")
    pg.keyboard.press('ArrowDown'); pg.keyboard.press('ArrowDown'); pg.keyboard.press('ArrowUp')
    out['selected_idx'] = pg.evaluate("[...document.querySelectorAll('#sugg button')].findIndex(b=>b.getAttribute('aria-selected')==='true')")
    pg.keyboard.press('Enter'); settle(pg, 900)
    out['after_enter'] = (crumbs(pg), pg.evaluate("document.querySelector('#sheet').classList.contains('open')"), pg.evaluate("[...document.querySelectorAll('#map .tile.sel')].map(e=>e.dataset.c)"))
    pg.keyboard.press('Escape'); settle(pg, 300); pg.keyboard.press('Escape'); settle(pg, 600)
    # stock outside top-N: 마녀공장 (rank 302 common) and 리메드 (rank ~800)
    for name, code in (('마녀공장', '439090'), ('리메드', '302550'), ('삼성전자우', '005935')):
        click_tab(pg, 'K' if code == '005935' else 'Q')
        pg.fill('#q', name); settle(pg, 300)
        sug = pg.eval_on_selector_all('#sugg button', 'e=>e.map(b=>b.innerText.replace(/\\n/g," "))')
        pg.keyboard.press('Enter'); settle(pg, 900)
        out['pick_' + name] = dict(sugg=sug[:2], crumbs=crumbs(pg), tile=pg.evaluate(f"(()=>{{const e=document.querySelector('#map .tile[data-c=\"{code}\"]:not(.leaving)');if(!e)return null;const r=e.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height),e.classList.contains('sel')]}})()"),
                                   sheet=pg.evaluate("document.querySelector('#sheet').classList.contains('open')"))
        pg.screenshot(path=f'{SHOTS}/{BUILD}_d1280_pick_{code}.png')
        pg.keyboard.press('Escape'); settle(pg, 300)
    pg.fill('#q', 'zzzz'); settle(pg, 300); out['no_match'] = pg.inner_text('#sugg')
    pg.keyboard.press('Escape'); settle(pg, 300)
    out['esc_clears'] = (pg.input_value('#q'), pg.evaluate("document.querySelectorAll('#map .tile.dim').length"))
    return out

@T('hist_buckets')
def t10(pg, log):
    out = {}
    click_tab(pg, 'K'); click_tab(pg, 'Q')
    pg.click('#hist button >> nth=0'); settle(pg, 300)
    out['b0'] = pg.evaluate("[document.querySelectorAll('#map .tile.dim').length, document.querySelectorAll('#map .tile:not(.dim)').length, document.querySelector('#hist button').innerText]")
    pg.click('#hist button >> nth=4'); settle(pg, 300)
    out['b4'] = pg.evaluate("[document.querySelectorAll('#map .tile:not(.dim)').length, document.querySelectorAll('#hist button')[4].innerText]")
    out['titles'] = pg.eval_on_selector_all('#hist button', 'e=>e.map(b=>b.title)')
    pg.click('#hist button >> nth=4'); settle(pg, 300)
    out['cleared'] = pg.evaluate("document.querySelectorAll('#map .tile.dim').length")
    return out

@T('sector_list')
def t11(pg, log):
    out = {}
    pg.hover('#secs button >> nth=2'); settle(pg, 300)
    out['hover'] = pg.evaluate("[document.querySelector('#map .sec.hot')?.dataset.s, document.querySelectorAll('#map .tile.dim').length, document.querySelectorAll('#map .tile').length]")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_d1280_sectorhover.png')
    pg.click('#secs button >> nth=2'); settle(pg)
    out['click'] = (crumbs(pg), pg.evaluate("document.querySelectorAll('#map .tile.dim').length"))
    # hover while zoomed: should not dim
    pg.hover('#secs button >> nth=0'); settle(pg, 300)
    out['hover_while_zoomed'] = pg.evaluate("document.querySelectorAll('#map .tile.dim').length")
    pg.keyboard.press('Escape'); settle(pg)
    pg.mouse.move(5, 5)
    return out

@T('movers')
def t12(pg, log):
    out = {}
    for v in ('up', 'dn', 'tv'):
        pg.click(f'#moverTabs button[data-v="{v}"]'); settle(pg, 200)
        out[v] = pg.eval_on_selector_all('#movers button', 'e=>e.map(b=>b.innerText.replace(/\\n/g," "))')[:4]
    pg.click('#movers button >> nth=0'); settle(pg, 400)
    out['click_opens_sheet'] = pg.evaluate("document.querySelector('#sheet').classList.contains('open')")
    pg.keyboard.press('Escape'); settle(pg, 300)
    pg.click('#moverTabs button[data-v="up"]')
    return out

@T('table_view')
def t13(pg, log):
    out = {}
    click_tab(pg, 'Q')
    seg(pg, 'view', 'table')
    rows = lambda: pg.evaluate("document.querySelectorAll('#tablewrap tbody tr').length")
    out['rows'] = rows()
    out['first'] = pg.inner_text('#tablewrap tbody tr >> nth=0').replace('\t', ' ')
    pg.click('#tablewrap th >> nth=3'); settle(pg, 200)
    out['sort_r_desc'] = pg.eval_on_selector_all('#tablewrap tbody tr td:nth-child(4)', 'e=>e.slice(0,3).map(x=>x.textContent)')
    pg.click('#tablewrap th >> nth=3'); settle(pg, 200)
    out['sort_r_asc'] = pg.eval_on_selector_all('#tablewrap tbody tr td:nth-child(4)', 'e=>e.slice(0,3).map(x=>x.textContent)')
    pg.click('#tablewrap th >> nth=0'); settle(pg, 200)
    out['sort_name'] = pg.eval_on_selector_all('#tablewrap tbody tr td:nth-child(1)', 'e=>e.slice(0,3).map(x=>x.innerText)')
    pg.fill('#q', '바이오'); settle(pg, 300)
    out['search_rows'] = rows()
    pg.keyboard.press('Tab')  # leave search
    pg.click('#hist button >> nth=0'); settle(pg, 300)
    out['search+bucket_rows'] = rows()
    out['search+bucket_sample'] = pg.eval_on_selector_all('#tablewrap tbody tr', 'e=>e.slice(0,3).map(x=>x.innerText.replace(/\\t|\\n/g," "))')
    pg.click('#hist button >> nth=0'); settle(pg, 300)
    pg.fill('#q', ''); settle(pg, 300)
    out['cleared_rows'] = rows()
    # zoom via sector list while in table view
    pg.click('#secs button >> nth=0'); settle(pg, 500)
    out['after_sector_click'] = dict(crumbs=crumbs(pg), rows=rows(), wanted=pg.inner_text('#crumbs .stat'))
    pg.keyboard.press('Escape'); settle(pg, 500)
    out['after_esc'] = dict(crumbs=crumbs(pg), rows=rows())
    seg(pg, 'topN', 100)
    out['after_topN100'] = dict(stat=pg.inner_text('#crumbs .stat'), rows=rows())
    seg(pg, 'palette', 'cvd')
    out['swatch_after_palette'] = pg.eval_on_selector('#tablewrap tbody tr .nmcell i', 'e=>e.style.background')
    seg(pg, 'palette', 'krg'); seg(pg, 'topN', 300)
    pg.click('#tablewrap tbody tr >> nth=0'); settle(pg, 400)
    out['row_click_sheet'] = pg.evaluate("document.querySelector('#sheet').classList.contains('open')")
    pg.screenshot(path=f'{SHOTS}/{BUILD}_d1280_table.png')
    pg.keyboard.press('Escape'); settle(pg, 300)
    click_tab(pg, 'K')
    out['market_switch_in_table'] = dict(stat=pg.inner_text('#crumbs .stat'), rows=rows())
    seg(pg, 'view', 'map')
    out['back_to_map'] = nodes(pg)
    return out

@T('switch_market_while_zoomed_or_sheet')
def t14(pg, log):
    out = {}
    click_tab(pg, 'Q')
    pg.click('#map .sec[data-s="정보기술"] .hd'); settle(pg)
    pg.click('#map .tile:not(.leaving) >> nth=0'); settle(pg, 400)
    click_tab(pg, 'K')
    out['after'] = dict(crumbs=crumbs(pg), nodes=nodes(pg), sheet=pg.evaluate("document.querySelector('#sheet').classList.contains('open')"), sel=pg.evaluate("document.querySelectorAll('#map .tile.sel').length"))
    return out

@T('sizeBy_tv_while_zoomed')
def t15(pg, log):
    out = {}
    click_tab(pg, 'Q')
    pg.click('#map .sec[data-s="헬스케어"] .hd'); settle(pg)
    pg.click('#map .ind[data-i="생물공학"] .hd'); settle(pg)
    seg(pg, 'sizeBy', 'tv'); settle(pg, 400)
    out['tv'] = dict(crumbs=crumbs(pg), nodes=nodes(pg), lab=pg.evaluate(LABEL_CHECK_JS)['overflow'])
    seg(pg, 'sizeBy', 'cap'); settle(pg, 400)
    out['cap'] = dict(crumbs=crumbs(pg), nodes=nodes(pg))
    pg.keyboard.press('Escape'); settle(pg); pg.keyboard.press('Escape'); settle(pg)
    return out

@T('resize_mid_zoom')
def t16(pg, log):
    out = {}
    pg.click('#map .sec[data-s="정보기술"] .hd'); pg.wait_for_timeout(120)
    pg.set_viewport_size({'width': 1000, 'height': 700}); settle(pg, 900)
    out['after'] = dict(nodes=nodes(pg), lab=pg.evaluate(LABEL_CHECK_JS)['overflow'],
                        outOfBounds=pg.evaluate("(()=>{const m=document.querySelector('#map').getBoundingClientRect();return [...document.querySelectorAll('#map .node')].filter(e=>{const r=e.getBoundingClientRect();return r.right>m.right+1||r.bottom>m.bottom+1}).length})()"))
    pg.screenshot(path=f'{SHOTS}/{BUILD}_resize_mid_zoom.png')
    pg.set_viewport_size({'width': 1280, 'height': 800}); settle(pg, 500)
    pg.keyboard.press('Escape'); settle(pg)
    return out

@T('rapid_clicks')
def t17(pg, log):
    out = {}
    click_tab(pg, 'Q')
    expect0 = nodes(pg)
    # rapid: zoom in, out, in, other sector... each 60ms apart
    for i in range(6):
        pg.click('#map .sec[data-s="정보기술"]:not(.leaving) .hd', force=True); pg.wait_for_timeout(60)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(60)
    settle(pg, 1000)
    out['after_rapid_in_out'] = dict(now=nodes(pg), expected=expect0)
    # ghost header click: zoom into 정보기술 then click where 헬스케어 header was within 150ms
    hb = pg.locator('#map .sec[data-s="헬스케어"] .hd').bounding_box()
    pg.click('#map .sec[data-s="정보기술"] .hd'); pg.wait_for_timeout(80)
    pg.mouse.click(hb['x'] + 10, hb['y'] + hb['height'] / 2); settle(pg, 900)
    out['click_on_fading_header_within_80ms'] = crumbs(pg)
    pg.keyboard.press('Escape'); settle(pg); pg.keyboard.press('Escape'); settle(pg)
    # spam a sector header 8 times
    for i in range(8):
        pg.click('#map .sec[data-s="정보기술"] .hd', force=True); pg.wait_for_timeout(40)
    settle(pg, 1000)
    out['spam_same_header'] = nodes(pg)
    pg.keyboard.press('Escape'); settle(pg, 1000)
    out['final'] = nodes(pg)
    return out

@T('persist')
def t18(pg, log):
    seg(pg, 'palette', 'cvd'); seg(pg, 'range', 5); seg(pg, 'topN', 200); seg(pg, 'sizeBy', 'tv'); click_tab(pg, 'K')
    pg.goto(URL); settle(pg, WAIT)
    out = pg.eval_on_selector_all('.seg[data-key] button[aria-pressed="true"]', 'e=>e.map(b=>b.closest(".seg").dataset.key+"="+b.dataset.v)')
    hashm = pg.evaluate('location.hash')
    res = dict(pressed=out, hash=hashm, crumbs=crumbs(pg), ls=pg.evaluate("Object.fromEntries(Object.keys(localStorage).filter(k=>k.startsWith('khm.')).map(k=>[k,localStorage[k]]))"))
    pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k)")
    pg.goto(URL); settle(pg, WAIT)
    return res

with sync_playwright() as p:
    b = launch(p)
    ctx, pg, log = new_page(b, 'd1280', URL, wait=WAIT)
    for fn in (t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12, t13, t14, t15, t16, t17, t18):
        fn(pg, log)
    print('CONSOLE', log.console[:20])
    print('FAILED', log.failed[:20])
    ctx.close()
    # reduced motion
    ctx, pg, log = new_page(b, 'd1280', URL, wait=WAIT, extra={'reduced_motion': 'reduce'})
    pg.click('#map .sec[data-s="정보기술"] .hd'); pg.wait_for_timeout(50)
    rm = dict(anim_class=pg.evaluate("document.querySelector('#map').classList.contains('anim')"),
              leaving_after_50ms=pg.evaluate("document.querySelectorAll('#map .leaving').length"),
              transition=pg.evaluate("getComputedStyle(document.querySelector('#map .tile')).transitionDuration"),
              pulse=pg.evaluate("getComputedStyle(document.querySelector('#status .dot')).animationName"),
              sheet_anim=None)
    pg.click('#map .tile >> nth=0'); pg.wait_for_timeout(30)
    rm['sheet_anim'] = pg.evaluate("getComputedStyle(document.querySelector('#sheet')).animationName")
    rm['tip_transition'] = pg.evaluate("getComputedStyle(document.querySelector('#tip')).transitionDuration")
    print('[reduced_motion]', dump(rm))
    ctx.close()
    b.close()
json.dump(R, open(f'/home/claude/heatmap/qa/desktop_{BUILD}.json', 'w'), ensure_ascii=False, indent=1)
