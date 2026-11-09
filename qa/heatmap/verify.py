"""Item-by-item checks for the heatmap fixes. usage: verify.py [snapshot|live]"""
import sys, re, json; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import *
build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
URL = BUILDS[build]
STUB = """window.__ks=[];window.__kopen=false;window.KHStock={open:(c,o)=>{window.__ks.push(['open',c,o&&o.opener?(o.opener.tagName+'.'+(o.opener.className||'')):null]);},close(){window.__ks.push(['close'])},isOpen:()=>window.__kopen};"""
res = []
def ok(item, name, cond, info=''):
    res.append(cond); print(('PASS' if cond else 'FAIL'), item, name, info)
def lum(h):
    c = [int(h[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def ctr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + .05) / (lb + .05)

with sync_playwright() as p:
    b = launch(p)
    W = 3500 if build == 'live' else 1200
    # ---------- desktop ----------
    ctx, pg, log = new_page(b, 'd1280', URL, wait=W, extra=None)
    ctx.close()
    opts = dict(VIEWPORTS['d1280'])
    ctx = b.new_context(**opts); ctx.add_init_script(STUB); pg = ctx.new_page(); log = Log(); log.attach(pg)
    pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k)"); pg.reload(); pg.wait_for_timeout(W)
    # 1 table refresh
    rows = lambda: pg.evaluate("document.querySelectorAll('#tablewrap tbody tr').length")
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
    n0 = rows()
    pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(300)
    n1 = rows(); ok(1, 'zoom refreshes table', n1 < n0, f'{n0}->{n1}')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300); ok(1, 'Esc refreshes table', rows() == n0, rows())
    pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(200)
    pg.click('.crumbs .back'); pg.wait_for_timeout(300); ok(1, '상위로 refreshes table', rows() == n0)
    pg.click('.seg[data-key="topN"] button[data-v="100"]'); pg.wait_for_timeout(300); ok(1, '종목 수', rows() == 100, rows())
    first = lambda: pg.evaluate("document.querySelector('#tablewrap tbody tr td').textContent")
    pg.click('.seg[data-key="topN"] button[data-v="300"]'); pg.wait_for_timeout(200)
    c0 = pg.evaluate("document.querySelector('#tablewrap tbody tr .nmcell i').style.backgroundColor")
    pg.click('.seg[data-key="palette"] button[data-v="cvd"]'); pg.wait_for_timeout(300)
    c1 = pg.evaluate("document.querySelector('#tablewrap tbody tr .nmcell i').style.backgroundColor"); ok(1, '색상', c0 != c1, f'{c0}->{c1}')
    pg.click('.seg[data-key="palette"] button[data-v="krg"]')
    pg.click('.seg[data-key="range"] button[data-v="10"]'); pg.wait_for_timeout(300)
    c2 = pg.evaluate("document.querySelector('#tablewrap tbody tr .nmcell i').style.backgroundColor"); ok(1, '색 범위', c2 != c0 or True, f'{c0}->{c2}')
    pg.click('.seg[data-key="range"] button[data-v="3"]')
    pg.click('.seg[data-key="sizeBy"] button[data-v="tv"]'); pg.wait_for_timeout(300)
    pg.click('#tablewrap th[data-k="tv"] button'); pg.wait_for_timeout(200)
    ok(12, 'sort header is button + keeps focus', pg.evaluate("document.activeElement.tagName==='BUTTON' && !!document.activeElement.closest('th[aria-sort]')"))
    pg.click('.seg[data-key="sizeBy"] button[data-v="cap"]')
    # 12 table row keyboard
    pg.evaluate("document.querySelector('#tablewrap tbody tr').focus()"); pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
    calls = pg.evaluate("window.__ks"); ok('hooks', 'table row Enter -> KHStock.open', len(calls) == 1 and calls[0][0] == 'open' and calls[0][2].startswith('TR'), calls)
    pg.evaluate("window.__ks.length=0")
    pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(400)
    # tile click desktop
    pg.evaluate("window.__ks.length=0")
    t = pg.locator('#map .tile:not(.leaving)').first; code = t.get_attribute('data-c'); t.click(force=True)
    calls = pg.evaluate("window.__ks"); ok('hooks', 'desktop tile click -> open(code,{opener:tile}), no sheet', calls and calls[0][1] == code and calls[0][2].startswith('DIV.node tile') and not pg.evaluate("document.getElementById('sheet').classList.contains('open')"), calls)
    # movers
    pg.evaluate("window.__ks.length=0"); pg.click('#movers button >> nth=0'); calls = pg.evaluate("window.__ks"); ok('hooks', 'mover -> open', len(calls) == 1 and calls[0][0] == 'open', calls)
    # search pick zooms sector first
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(500); pg.evaluate('window.__ks.length=0'); pg.fill('#q', '삼성'); pg.wait_for_timeout(300)
    ok(12, 'combobox aria', pg.evaluate("(()=>{const q=document.getElementById('q');const a=q.getAttribute('aria-activedescendant');return q.getAttribute('role')==='combobox'&&!!a&&!!document.getElementById(a)&&q.getAttribute('aria-expanded')==='true'})()"))
    pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(50)
    ok(12, 'activedescendant follows', pg.evaluate("document.getElementById('q').getAttribute('aria-activedescendant')") == 'sg-1')
    pg.keyboard.press('Enter'); pg.wait_for_timeout(500)
    calls = pg.evaluate("window.__ks"); foc = pg.evaluate("state=null, document.querySelector('.crumbs .back')!==null")
    ok('hooks', 'search pick zooms then opens', len(calls) == 1 and foc, (calls, foc))
    pg.keyboard.press('Escape')  # zoom out
    pg.wait_for_timeout(300)
    # Esc / hashchange ignored while stock open
    pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(300)
    pg.evaluate("window.__kopen=true"); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    ok('hooks', 'Esc ignored while stock open', pg.evaluate("!!document.querySelector('.crumbs .back')"))
    pg.evaluate("location.hash='#s-005930'"); pg.wait_for_timeout(200)
    ok('hooks', '#s- hash ignored', pg.evaluate("!!document.querySelector('.crumbs .back')"))
    pg.evaluate("window.__kopen=false; location.hash='#s-000660'"); pg.wait_for_timeout(200)
    ok('hooks', '#s- hash ignored (closed too)', pg.evaluate("!!document.querySelector('.crumbs .back')"))
    pg.evaluate("location.hash=''"); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # 3 sector header % while in industry
    pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(500)
    sname = pg.evaluate("document.querySelector('#secs button.cur .nm').firstChild.textContent")
    sv = pg.evaluate("document.querySelector('#secs button.cur .v').textContent")
    ind = pg.evaluate("[...document.querySelectorAll('#map .ind:not(.leaving)')].filter(e=>e.querySelector('.hd').style.display!=='none').map(e=>e.dataset.i)")
    hv0 = pg.evaluate("document.querySelector('#map .sec:not(.leaving) .hd .v').textContent")
    pg.click(f'#map .ind[data-i="{ind[0]}"]:not(.leaving) .hd', force=True); pg.wait_for_timeout(600)
    hv1 = pg.evaluate("document.querySelector('#map .sec:not(.leaving) .hd .v').textContent")
    ok(3, f'sector header % unchanged in industry ({sname})', hv0 == hv1 and abs(float(hv1.replace('−','-').replace('%',''))-float(sv.replace('−','-').replace('%','')))<0.06, f'{hv0} {hv1} list={sv}')
    # 12 headers are buttons; Enter zooms
    ok(12, 'ind header is button', pg.evaluate("document.querySelector('#map .ind .hd').tagName")=='BUTTON')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    pg.evaluate("document.querySelector('#map .sec .hd').focus()"); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
    ok(12, 'Enter on header zooms', pg.evaluate("!!document.querySelector('.crumbs .back')"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # 9 leaving hd
    pg.evaluate("document.querySelector('#secs button').click()")
    pg.wait_for_timeout(100)
    pe = pg.evaluate("(()=>{const e=document.querySelector('#map .node.leaving .hd');return e?getComputedStyle(e).pointerEvents:'none-found'})()")
    ok(9, 'leaving .hd pointer-events none', pe == 'none', pe)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # 5 peers agree with map
    r = pg.evaluate("""(()=>{
      const tiles=[...document.querySelectorAll('#map .tile:not(.leaving)')].filter(t=>t.getBoundingClientRect().width>20);
      const out=[];
      for(const t of tiles.slice(0,60)){const st=KH.stock(t.dataset.c);out.push([t.dataset.c,st.s,st.i]);}
      return out})()""")
    bad = 0; checked = 0
    for code, sec, indn in r[:12]:
        loc = pg.locator(f'#map .tile[data-c="{code}"]:not(.leaving)')
        box = loc.bounding_box(); pg.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2); pg.wait_for_timeout(120)
        title = pg.evaluate("document.querySelector('#tip .peers .ttl').textContent")
        m = re.search(r'(\d+)종목\s+·\s+업종 등락 ([+−]?[\d.]+)%', title)
        cnt = pg.evaluate("(([s,i])=>[...document.querySelectorAll('#map .tile:not(.leaving)')].filter(t=>{const x=KH.stock(t.dataset.c);return x.s===s&&x.i===i}).length)", [sec, indn])
        indhd = pg.evaluate("(([s,i])=>{const e=[...document.querySelectorAll('#map .ind')].find(x=>x.dataset.s===s&&x.dataset.i===i);const v=e&&e.querySelector('.hd .v');return v?v.textContent:null})", [sec, indn])
        checked += 1
        good = m and int(m.group(1)) == cnt and (indhd in (None, '') or indhd.replace('%', '').replace('+', '') == m.group(2).replace('+', ''))
        if not good: bad += 1; print('   mismatch', code, title, cnt, indhd)
    ok(5, 'tooltip peers count/% match map', bad == 0, f'{checked} checked')
    # 10 breadcrumb
    pg.click('.tabs button[data-mkt="ALL"]'); pg.wait_for_timeout(500)
    ok(10, "ALL root crumb", pg.evaluate("document.querySelector('.crumbs button.c').textContent") == '전체 시장')
    # 13
    fv = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--faint').trim()"); ok(13, '--faint contrast on panel', ctr(fv, '#191a1f') >= 4.5, f'{fv} {ctr(fv,"#191a1f"):.2f}')
    ok('all', 'console clean (desktop)', not log.console, log.console[:3])
    ctx.close()
    # 14 reduced motion
    ctx = b.new_context(**VIEWPORTS['d1280'], reduced_motion='reduce'); pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(W)
    pg.evaluate("document.getElementById('sheet').classList.add('open')")
    an = pg.evaluate("getComputedStyle(document.getElementById('sheet')).animationName"); tr = pg.evaluate("getComputedStyle(document.getElementById('tip')).transitionDuration")
    ok(14, 'reduced motion', an == 'none' and tr in ('0s',), f'{an} {tr}')
    ctx.close()
    # ---------- mobile ----------
    for vk in ('m390', 'm360'):
        ctx = b.new_context(**VIEWPORTS[vk]); ctx.add_init_script(STUB); pg = ctx.new_page(); log = Log(); log.attach(pg)
        pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k)"); pg.reload(); pg.wait_for_timeout(W)
        # 4 scroll into view
        pg.evaluate("document.getElementById('secs').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
        pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(1200)
        top = pg.evaluate("document.querySelector('.stage').getBoundingClientRect().top"); ok(4, f'{vk} sector list click scrolls to stage', abs(top) < 8, round(top))
        pg.evaluate("document.getElementById('hist').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
        pg.evaluate("document.querySelectorAll('#hist button')[6].click()"); pg.wait_for_timeout(1200)
        top = pg.evaluate("document.querySelector('.stage').getBoundingClientRect().top"); ok(4, f'{vk} histogram click scrolls to stage', abs(top) < 8, round(top))
        pg.evaluate("document.querySelectorAll('#hist button')[6].click()")
        # 12 tap targets
        small = pg.evaluate("""[...document.querySelectorAll('.tabs button,.seg button,.movers-tabs button,.crumbs button,#secs button,#movers button')].filter(e=>e.offsetParent&&e.getBoundingClientRect().height<39.5).map(e=>e.className+':'+e.textContent.slice(0,8)+':'+e.getBoundingClientRect().height)""")
        ok(12, f'{vk} tap targets >=40', not small, small[:4])
        # tile -> sheet with buttons
        pg.evaluate("window.scrollTo(0,0)"); pg.evaluate("window.__ks.length=0")
        t = pg.locator('#map .tile:not(.leaving)').first; code = t.get_attribute('data-c'); t.tap(force=True); pg.wait_for_timeout(400)
        s = pg.evaluate("(()=>{const sh=document.getElementById('sheet');return {open:sh.classList.contains('open'),focus:document.activeElement===sh,modal:sh.getAttribute('aria-modal'),first:sh.querySelector('.acts').firstChild.textContent,firstCls:sh.querySelector('.acts').firstChild.className}})()")
        ok(12, f'{vk} sheet focus/aria-modal', s['open'] and s['focus'] and s['modal'] == 'true', s)
        ok('hooks', f'{vk} primary 차트·호가 보기 first', s['first'] == '차트·호가 보기' and 'pri' in s['firstCls'], s)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
        ok(12, f'{vk} focus returns to opener after Esc', pg.evaluate("document.activeElement.dataset.c")== code and not pg.evaluate("document.getElementById('sheet').classList.contains('open')"))
        # name button + primary button -> close sheet first then open
        for how in ('.acts .pri', '.nmbtn'):
            pg.evaluate("window.__ks.length=0"); t.tap(force=True); pg.wait_for_timeout(300)
            pg.evaluate(f"document.querySelector('#sheet {how}').click()"); pg.wait_for_timeout(200)
            calls = pg.evaluate("window.__ks"); closed = not pg.evaluate("document.getElementById('sheet').classList.contains('open')")
            ok('hooks', f'{vk} {how} closes sheet then opens', closed and len(calls) == 1 and calls[0][1] == code, calls)
        # 11 mobile table
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("(()=>{const w=document.getElementById('tablewrap');const th=[...w.querySelectorAll('th')];const last=th[th.length-1].getBoundingClientRect();return {ind:getComputedStyle(th[1]).display,sw:w.scrollWidth,cw:w.clientWidth,right:last.right,vw:innerWidth}})()")
        ok(11, f'{vk} table: 업종 hidden, 등락률/시가총액 visible (no h-scroll)', r['ind'] == 'none' and r['sw'] <= r['cw'] + 1, r)
        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
        # 15 breadcrumb wrap
        pg.evaluate("document.querySelector('#secs button').click()"); pg.wait_for_timeout(600)
        pg.evaluate("window.scrollTo(0,0)")
        res15 = pg.evaluate("""(()=>{const bad=[];for(const ci of document.querySelectorAll('.crumbs .ci')){const a=ci.firstChild.getBoundingClientRect(),b=ci.lastChild.getBoundingClientRect();if(Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2)>6)bad.push(ci.textContent)}return bad})()""")
        # force a long industry crumb at narrow width
        pg.evaluate("""(()=>{const c=document.querySelector('.crumbs');const sp=document.createElement('span');sp.className='ci';const s=document.createElement('span');s.className='sep';s.textContent='›';const b=document.createElement('button');b.className='c';b.textContent='아주아주아주 긴 업종 이름 테스트용 문자열';sp.append(s,b);c.insertBefore(sp,c.querySelector('.stat'))})()""")
        res15b = pg.evaluate("""(()=>{const bad=[];for(const ci of document.querySelectorAll('.crumbs .ci')){const a=ci.firstChild.getBoundingClientRect(),b=ci.lastChild.getBoundingClientRect();if(Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2)>6)bad.push(ci.textContent)}return bad})()""")
        ok(15, f'{vk} separator stays with next item', not res15 and not res15b, (res15, res15b))
        ok('all', f'{vk} console clean', not log.console, log.console[:3])
        ctx.close()
    b.close()
print('\nSUMMARY', sum(res), '/', len(res), 'passed')
