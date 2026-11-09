"""Heatmap review fixes + §3-3/§3-4 checks (numbers, not eyeballing). usage: verify3.py [snapshot|live]
table on phones, 정규장 종가/NXT 포함, replay player vs map, full-market 등락 분포, search beyond the stream, d3 guard, compact phone
header, keyboard tiles, tap targets, 상/하한가 edges, hidden-tab polling, world tabs (stub KHWorld), leftovers."""
import os; HM_BASE = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')   # dev Worker (harness) port
import sys, json, re, urllib.request
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright

build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
LIVE = build == 'live'
URL = HM_BASE if LIVE else 'file:///home/claude/hm-heatmap/dist/index.html'
ROOT = '/home/claude/hm-heatmap/'
CLOSE = json.load(open(ROOT + 'web/close.json'))
NAMES = json.load(open(ROOT + 'web/names.json'))['n']
SNAP = {s['c']: s for s in json.load(open(ROOT + 'data/snapshot.json'))['stocks']}
WAIT = 4000 if LIVE else 1300
# the extras owner is turning the tool buttons into 40×40 icons on phones; until that lands, emulate it for the header numbers
ICON = "@media (max-width:760px){#extras-tools .xt-btn{width:40px!important;height:40px!important;padding:0!important}#extras-tools .xt-btn span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}"
TIMERS = """(() => { const st = window.setTimeout, ct = window.clearTimeout; window.__tm = new Map();
  window.setTimeout = function (fn, ms, ...a) { const id = st(function () { window.__tm.delete(id); return typeof fn === 'function' ? fn.apply(this, arguments) : null; }, ms, ...a); window.__tm.set(id, (fn && fn.name) || ''); return id; };
  window.clearTimeout = function (id) { window.__tm.delete(id); return ct(id); }; })();"""
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def api(path):
    with urllib.request.urlopen(HM_BASE + path, timeout=30) as r:
        return json.load(r)


def pnum(t):
    return float(t.replace('−', '-').replace('%', '').replace('+', '').replace(',', '').strip())


def fresh(b, vp, store=None, hsh='', init=(), routes=None, wait=WAIT):
    # service workers off when a test rewrites responses (the PWA worker would answer from its cache)
    ctx = b.new_context(**VIEWPORTS[vp], **({'service_workers': 'block'} if routes else {}))
    for s in init: ctx.add_init_script(s)
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    for pat, fn in (routes or {}).items(): pg.route(pat, fn)
    pg.goto(URL)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);"
    for k, v in (store or {}).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    pg.goto(URL + hsh); log.mark = len(log.reqs); pg.reload(); pg.wait_for_timeout(wait)
    if vp.startswith('m'): pg.add_style_tag(content=ICON); pg.wait_for_timeout(250)
    return ctx, pg, log


def errs(log):
    return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]


with sync_playwright() as p:
    b = launch(p)
    # ───── 0 every viewport: overflow, console, labels, map top ─────
    for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
        ctx, pg, log = fresh(b, vp)
        over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
        lab = pg.evaluate(LABEL_CHECK_JS)
        top = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top)")
        ok(f'{vp}: overflow 0, console errors 0, tile labels inside ({lab["visible"]} labels)', over == 0 and not errs(log) and lab['overflow'] == 0, (over, errs(log)[:2], lab['examples'][:2]))
        if vp == 'm390':
            # the template's own budget (clock off); the extras clock in the title spot adds its height above 40 px (reported, not counted)
            ctx2, pg2, _ = fresh(b, vp, store={'set.clock': False})
            top2 = pg2.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top)"); ctx2.close()
            ok('m390: map top ≤ 232 (ticker strip present, clock off)', top2 <= 232, top2)
            print('INFO m390 map top with the clock on:', top, '(clock row', pg.evaluate("Math.round(document.getElementById('clock').getBoundingClientRect().height)"), 'px)')
        ctx.close()

    # ───── 1 table view on phones ─────
    for vp in ['m360', 'm390']:
        ctx, pg, log = fresh(b, vp, store={'market': 'K'})
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("""() => { const hs = [...document.querySelectorAll('#tablewrap th')].filter(t => t.offsetParent).map(t => t.textContent);
          const cells = [...document.querySelectorAll('#tablewrap tbody tr')].slice(0, 40).map(tr => { const n = tr.querySelector('.nmt'); const r = n.getBoundingClientRect();
            return { w: r.width, lines: Math.round(r.height / parseFloat(getComputedStyle(n).lineHeight)), clipped: n.scrollHeight > n.clientHeight + 1, name: n.textContent }; });
          const fs = parseFloat(getComputedStyle(document.querySelector('#tablewrap .nmt')).fontSize);
          return { hs, minW: Math.min(...cells.map(c => c.w)), fs, maxLines: Math.max(...cells.map(c => c.lines)), clipped: cells.filter(c => c.clipped).map(c => c.name),
                   over: document.getElementById('tablewrap').scrollWidth - document.getElementById('tablewrap').clientWidth }; }""")
        ok(f'{vp} table: 거래대금 dropped, name ≥ 5.5em, ≤ 2 lines, no sideways scroll', '거래대금' not in ''.join(r['hs']) and r['minW'] >= 5.5 * r['fs'] and r['maxLines'] <= 2 and r['over'] <= 0 and not r['clipped'], r)
        # 7-column tables (period colour) also drop 시가총액
        pg.evaluate("localStorage.setItem('khm.colorBy', JSON.stringify('m1'))"); pg.reload(); pg.wait_for_timeout(WAIT)
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(600)
        hs = pg.evaluate("[...document.querySelectorAll('#tablewrap th')].filter(t => t.offsetParent).map(t => t.textContent)")
        over = pg.evaluate("document.getElementById('tablewrap').scrollWidth - document.getElementById('tablewrap').clientWidth")
        ok(f'{vp} period table: 종목·현재가·1개월·오늘, no sideways scroll', hs[:4] == ['종목', '현재가', '1개월', '오늘'] and len(hs) == 4 and over <= 0, (hs, over))
        if vp == 'm360': pg.screenshot(path=ROOT + 'qa/heatmap2/shots3/table-m360.png')
        ctx.close()
    # theme table keeps its value column on phones
    ctx, pg, log = fresh(b, 'm390', hsh='#theme')
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(500)
    hs = pg.evaluate("[...document.querySelectorAll('#tablewrap th')].filter(t => t.offsetParent).map(t => t.textContent)")
    ok('m390 theme table shows 테마 + 등락률', hs[:2] == ['테마', '등락률'], hs)
    ctx.close()

    # ───── 2 정규장 종가 / NXT 포함 (live) ─────
    if LIVE:
        q = {s['c']: s for s in api('api/quotes')['stocks']}
        ss = q['005930']
        ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'})
        st = pg.evaluate("({hidden: document.getElementById('basis').hidden, pressed: document.querySelector('#basis [aria-pressed=\"true\"]')?.dataset.v, status: document.getElementById('status').innerText})")
        lab = pg.evaluate("document.querySelector('#map .tile[data-c=\"005930\"]').getAttribute('aria-label')")
        c = CLOSE['c']['005930']
        ok('after 15:30 with close.json of that day: toggle shown, 정규장 종가 by default', not st['hidden'] and st['pressed'] == 'krx', st)
        ok(f"정규장 종가: 삼성전자 tile % = close.json {c[2]}", abs(pnum(lab.split(' ')[-1]) - c[2]) < 0.006, (lab, c))
        # table / tooltip / side / layout px follow
        pg.hover('#map .tile[data-c="005930"]'); pg.wait_for_timeout(250)
        tipPx = pg.evaluate("document.querySelector('#tip .card-head .px b').textContent")
        ok('tooltip price = 종가', int(tipPx.replace(',', '')) == c[0], (tipPx, c[0]))
        lay = [n for n in pg.evaluate("KH.layout()") if n.get('code') == '005930'][0]
        ok('KH.layout() tile px = 종가 (for the saved image)', lay.get('px', '').replace(',', '') == str(c[0]), lay)
        pg.mouse.move(5, 5)
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
        row = pg.evaluate("[...document.querySelector('#tablewrap tr[data-c=\"005930\"]').children].map(td => td.textContent)")
        ok('table 현재가 / 등락률 = 종가', int(row[2].replace(',', '')) == c[0] and abs(pnum(row[3]) - c[2]) < 0.006, row[:4])
        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
        # size by cap follows the price (cap × p_close / p_live)
        w1 = pg.evaluate("(() => { const L = KH.layout().filter(n => n.kind === 'tile'); const a = L.find(n => n.code === '005930'), b = L.find(n => n.code === '000660'); return a.w * a.h / (b.w * b.h); })()")
        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(900)
        lab2 = pg.evaluate("document.querySelector('#map .tile[data-c=\"005930\"]').getAttribute('aria-label')")
        st2 = pg.evaluate("({pressed: document.querySelector('#basis [aria-pressed=\"true\"]')?.dataset.v, nxt: document.querySelector('#basis [data-v=\"nxt\"] .bl').textContent})")
        ok(f"NXT 포함: 삼성전자 tile % = live quote {ss['r']}", abs(pnum(lab2.split(' ')[-1]) - ss['r']) < 0.006 and st2['pressed'] == 'nxt', (lab2, st2))
        ok('NXT button reads "NXT 포함 · HH:MM 기준"', re.fullmatch(r'NXT 포함 · \d\d:\d\d 기준', st2['nxt']), st2)
        w2 = pg.evaluate("(() => { const L = KH.layout().filter(n => n.kind === 'tile'); const a = L.find(n => n.code === '005930'), b = L.find(n => n.code === '000660'); return a.w * a.h / (b.w * b.h); })()")
        cs, ch = CLOSE['c']['005930'][0] / ss['p'], CLOSE['c']['000660'][0] / q['000660']['p']
        ok('tile area ratio follows the basis (cap × p_shown / p_live)', abs((w1 / w2) / (cs / ch) - 1) < 0.04, (round(w1, 4), round(w2, 4), round(cs / ch, 4)))
        pg.screenshot(path=ROOT + 'qa/heatmap2/shots3/nxt-d1280.png')
        ctx.close()
        # phones: a short time stays visible
        ctx, pg, log = fresh(b, 'm390')
        vis = pg.evaluate("[...document.querySelectorAll('#status *')].filter(e => e.offsetParent && /\\d\\d:\\d\\d/.test(e.textContent) && !e.children.length).map(e => e.textContent)")
        # (while the session is live and the clock is on, the clock in the title spot is the time on a phone)
        ok('m390: a HH:MM is visible in the header', vis, vis)
        ctx.close()
        # no close.json for that day → plain "NXT 포함 · HH:MM 기준" badge, no toggle
        ctx, pg, log = fresh(b, 'm390', routes={'**/data/close.json': lambda r: r.fulfill(status=404, body='{}')})
        st = pg.evaluate("({hidden: document.getElementById('basis').hidden, badge: document.querySelector('#status .badge').textContent, vis: getComputedStyle(document.querySelector('#status .badge')).display})")
        ok('close.json 404 → no toggle, badge "NXT 포함 · HH:MM 기준" visible on a phone', st['hidden'] and re.fullmatch(r'NXT 포함 · \d\d:\d\d 기준', st['badge']) and st['vis'] != 'none', st)
        n404 = len([u for u in log.reqs if 'close.json' in u]); pg.wait_for_timeout(6000)
        ok('close.json 404 is not retried in a loop (one request per page load, none after)', len([u for u in log.reqs if 'close.json' in u]) == n404 == 3, n404)
        ctx.close()

    # ───── 3 full-market 등락 분포 ─────
    def dist(pg):
        return pg.evaluate("({scope: document.getElementById('breadthScope').textContent, lab: document.getElementById('breadthLab').textContent, note: document.getElementById('histNote').textContent})")
    for mk, name in [('K', '코스피'), ('Q', '코스닥')]:
        ctx, pg, log = fresh(b, 'd1280', store={'market': mk})
        d = dist(pg)
        if LIVE:
            rs = [x for x in CLOSE['c'] if NAMES.get(x, [0, ''])[1] == mk]
            up = sum(1 for x in rs if CLOSE['c'][x][2] > 0); dn = sum(1 for x in rs if CLOSE['c'][x][2] < 0)
        else:
            rs = [x for x in SNAP.values() if x['m'] == mk]
            up = sum(1 for x in rs if x['r'] > 0); dn = sum(1 for x in rs if x['r'] < 0)
        ok(f'{name} 등락 분포 = 전 종목 {len(rs)} (상승 {up} · 하락 {dn})', d['scope'] == f'{name} 전 종목 {len(rs):,}' and f'상승 {up:,}' in d['lab'] and f'하락 {dn:,}' in d['lab'], d)
        # a bucket click says how many of its stocks are on the map
        pg.click('#hist button:nth-child(1)'); pg.wait_for_timeout(250)
        d2 = dist(pg); dimmed = pg.evaluate("document.querySelectorAll('#map .tile.dim').length")
        ok(f'{name} bucket click: "이 구간 N종목 중 지도에 M종목" + map dims', re.search(r'이 구간 [\d,]+종목 중 지도에 [\d,]+종목', d2['note']) and dimmed > 0, (d2['note'], dimmed))
        ctx.close()
    if LIVE:
        # NXT 포함 → /api/breadth parts (1-based); partial and total failure
        bK = [api('api/breadth?m=K&part=1')]; bK += [api(f'api/breadth?m=K&part={i}') for i in range(2, bK[0]['parts'] + 1)]
        rowsK = [r for x in bK for r in x['rows']]
        ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'})
        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(2500)
        d = dist(pg); up = sum(1 for r in rowsK if r[1] > 0)
        reqs = sorted(set(u.split('?')[1] for u in log.reqs if 'api/breadth' in u))
        ok(f'NXT 포함: 코스피 전 종목 {len(rowsK)} from /api/breadth parts 1..{bK[0]["parts"]}', d['scope'] == f'코스피 전 종목 {len(rowsK):,}' and f'상승 {up:,}' in d['lab'] and 'm=K&part=0' not in reqs, (d, reqs))
        ctx.close()
        ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'}, routes={'**/api/breadth?m=K&part=2': lambda r: r.abort()})
        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(2500)
        d = dist(pg)
        ok('one part fails → counts what arrived + "일부만 반영"', '일부만 반영' in d['scope'] and '일부 묶음' in d['note'], d)
        ctx.close()
        ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'}, routes={'**/api/breadth*': lambda r: r.fulfill(status=502, body='{"error":"x"}')})
        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(2500)
        d = dist(pg)
        ok('every part fails → map stocks + says so', d['scope'].startswith('코스피 지도 ') and '불러오지 못해 지도 종목' in d['note'], d)
        ctx.close()
    # period colour: every stock with data; zoom keeps its own scope
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'K', 'colorBy': 'm1'})
    pg.wait_for_timeout(1200)
    d = dist(pg)
    ok('1개월 colour: scope = stocks with data, labelled', re.fullmatch(r'코스피 [\d,]+종목', d['scope']) and '데이터가 있는 종목만' in d['note'], d)
    pg.click('#secs button:nth-child(1)'); pg.wait_for_timeout(700)
    d = dist(pg)
    ok('sector zoom keeps the zoomed scope', not d['scope'].startswith('코스피'), d)
    ctx.close()

    # ───── 5 search beyond the map ─────
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'Q'})
    for qtxt, code, name in [('삼성전자우', '005935', '삼성전자우'), ('005935', '005935', '삼성전자우'), ('현대차2우B', '005387', '현대차2우B')]:
        pg.fill('#q', ''); pg.focus('#q'); pg.type('#q', qtxt, delay=20); pg.wait_for_timeout(900)
        opts = pg.evaluate("[...document.querySelectorAll('#sugg [role=option]')].map(o => o.textContent)")
        ok(f'search "{qtxt}" (on 코스닥) offers {name}', opts and name in opts[0] and code in opts[0], opts[:3])
    pg.keyboard.press('Enter'); pg.wait_for_timeout(1200)
    ok('picking a stock outside the map opens its stock page', pg.evaluate("!!(window.KHStock && KHStock.isOpen())") and '005387' in pg.evaluate("location.hash"), pg.evaluate("location.hash"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    pg.fill('#q', ''); pg.type('#q', '123456', delay=10); pg.wait_for_timeout(500)
    opts = pg.evaluate("[...document.querySelectorAll('#sugg [role=option]')].map(o => o.textContent)")
    ok('a typed 6-character code always offers its stock', opts and '123456' in opts[0], opts[:2])
    # live: names.json once per page load — at the first search focus, or at boot when 정규장 종가's full-market 등락 분포 needs it
    nm = [u for u in log.reqs[log.mark:] if 'names.json' in u]
    ok('names.json loaded once (search focus, or 정규장 종가 등락 분포)' if LIVE else 'snapshot: no names.json request', len(nm) == 1 if LIVE else not [u for u in log.reqs if 'names.json' in u], nm)
    ctx.close()

    # ───── 6 d3 blocked ─────
    if LIVE:
        ctx, pg, log = fresh(b, 'd1280', routes={'**/d3.min.js': lambda r: r.abort()})
        msg = pg.evaluate("document.getElementById('map').innerText")
        pe = [c for c in log.console if c.startswith('pageerror')]
        ok('d3 blocked → message in the map, no script errors', 'd3' in msg and '새로 고침' in msg and not pe, (msg[:60], pe[:2]))
        ctx.close()

    # ───── 3 replay: legend chip class, player never covers the map + legend ─────
    for vp in ['d1280', 'm390']:
        ctx, pg, log = fresh(b, vp, store={'market': 'K'})
        pg.evaluate("KH.setReplay({t:'0905', date:'2026-11-09', prices:new Map([['005930',{p:180000,r:-4.5}]])})"); pg.wait_for_timeout(300)
        chip = pg.evaluate("(() => { const e = document.querySelector('#legend .lg-replay'); return e ? [e.textContent, getComputedStyle(e).position] : null; })()")
        ok(f'{vp}: replay legend chip .lg-replay (static, not the player style)', chip and chip[1] == 'static' and not pg.evaluate("document.querySelector('#legend .rp')"), chip)
        pg.evaluate("KH.setReplay(null)")
        if LIVE:
            pg.click('#extras-tools [data-x="replay"]'); pg.wait_for_timeout(3500)
            r = pg.evaluate("""() => { const pl = document.querySelector('#replay-player, section.rp, .rp-player'); const m = document.getElementById('map').getBoundingClientRect(), l = document.getElementById('legend').getBoundingClientRect();
              const p = pl && !pl.hidden ? pl.getBoundingClientRect() : null; return { player: p && [Math.round(p.top), Math.round(p.bottom)], map: [Math.round(m.top), Math.round(m.bottom)], legend: Math.round(l.bottom), rp: getComputedStyle(document.documentElement).getPropertyValue('--rp-h') }; }""")
            ok(f'{vp}: replay player open → map + legend end above it', r['player'] and r['legend'] <= r['player'][0] + 1, r)
            pg.screenshot(path=ROOT + f'qa/heatmap2/shots3/replay-{vp}.png')
            pg.click('#extras-tools [data-x="replay"]'); pg.wait_for_timeout(700)
            r2 = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().height)")
            ok(f'{vp}: player closed → map height restored', r2 > r['map'][1] - r['map'][0], (r2, r['map']))
        ctx.close()
    # the quick-view sheet closes when a replay starts / stops, not on every frame
    ctx, pg, log = fresh(b, 'm390', store={'market': 'K'})
    pg.evaluate("KH.setReplay({t:'0905', prices:new Map()})")
    pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(300)
    pg.evaluate("KH.setReplay({t:'0910', prices:new Map([['005930',{p:181000,r:-4}]])})"); pg.wait_for_timeout(200)
    o1 = pg.evaluate("document.getElementById('sheet').classList.contains('open')")
    px = pg.evaluate("document.querySelector('#sheet .card-head .px b').textContent")
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(200)
    o2 = pg.evaluate("document.getElementById('sheet').classList.contains('open')")
    ok('sheet stays open across replay frames (and shows the frame price), closes when the replay stops', o1 and px == '181,000' and not o2, (o1, px, o2))
    ctx.close()

    # ───── 9 keyboard ─────
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'})
    n0 = pg.evaluate("document.querySelectorAll('#map .tile[tabindex=\"0\"]').length")
    pg.evaluate("document.querySelector('#map .tile[tabindex=\"0\"]').focus()")
    g0 = pg.evaluate("(() => { const r = document.activeElement.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, document.activeElement.dataset.c]; })()")
    pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(100)
    g1 = pg.evaluate("(() => { const r = document.activeElement.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, document.activeElement.dataset.c]; })()")
    pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(100)
    g2 = pg.evaluate("(() => { const r = document.activeElement.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, document.activeElement.dataset.c]; })()")
    ring = pg.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineColor, s.outlineWidth]; })()")
    n1 = pg.evaluate("document.querySelectorAll('#map .tile[tabindex=\"0\"]').length")
    tipOn = pg.evaluate("document.getElementById('tip').classList.contains('show')")
    ok('one tabbable tile; → moves right, ↓ moves down', n0 == 1 == n1 and g1[0] >= g0[2] - 2 and g2[1] >= g1[3] - 2, (n0, n1, g0, g1, g2))
    ok('focused tile: amber ring + tooltip', ring[0] == 'solid' and ring[1] == 'rgb(255, 181, 71)' and tipOn, (ring, tipOn))
    pg.keyboard.press('Enter'); pg.wait_for_timeout(900)
    ok('Enter opens the stock page', pg.evaluate("!!(window.KHStock && KHStock.isOpen())") and g2[4] in pg.evaluate("location.hash"), pg.evaluate("location.hash"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
    ok('Esc returns focus to the tile', pg.evaluate("document.activeElement.dataset.c") == g2[4], pg.evaluate("document.activeElement.className"))
    ctx.close()

    # ───── 10 tap targets on phones ─────
    ctx, pg, log = fresh(b, 'm390', store={'market': 'K'})
    sz = pg.evaluate("""() => { const m = s => [...document.querySelectorAll(s)].filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect(); return [s, Math.round(r.width), Math.round(r.height)]; });
      return [...m('#q'), ...m('.viewseg button'), ...m('.tabs button'), ...m('#basis button'), ...m('#setBtn')]; }""")
    pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(300)
    sz += pg.evaluate("[...document.querySelectorAll('#sheet .acts > *, #sheet .x, #sheet .wstar')].map(e => { const r = e.getBoundingClientRect(); return ['sheet ' + (e.className || e.tagName), Math.round(r.width), Math.round(r.height)]; })")
    small = [x for x in sz if x[1] < 40 or x[2] < 40]
    ok(f'm390 tap targets ≥ 40×40 ({len(sz)} checked)', not small, small)
    ctx.close()

    # ───── 11 상/하한가 marks ─────
    # 관심종목 map: two giants and three limit stocks (live: 정규장 종가 rows from close.json carry the limit moves)
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'WATCH', 'watch': ['000250', '008930', '267270', '222800', '138930', '012750', '900300', '179530', '267850']})
    r = pg.evaluate("""() => [...document.querySelectorAll('#map .tile.limu, #map .tile.limd')].map(t => { const g = t.getBoundingClientRect(), be = getComputedStyle(t, '::before');
      return { c: t.dataset.c, w: Math.round(g.width), h: Math.round(g.height), aria: t.getAttribute('aria-label'), bar: be.content !== 'none' ? be.height : null, chip: !t.querySelector('.lim').hidden }; })""")
    if r:
        ok(f'limit tiles ({len(r)}): edge bar on every one, aria says 상한가/하한가', all(x['bar'] == '3px' and ('상한가' in x['aria'] or '하한가' in x['aria']) for x in r), r[:3])
        r = [x for x in r if x['w'] >= 1 and x['h'] >= 1]
        smallest = min(r, key=lambda x: x['w'] * x['h'])
        ok(f"smallest limit tile {smallest['w']}×{smallest['h']} still marked", smallest['bar'] == '3px', smallest)
        pg.hover(f"#map .tile[data-c=\"{max(r, key=lambda x: x['w'] * x['h'])['c']}\"]"); pg.wait_for_timeout(200)
        pg.screenshot(path=ROOT + f'qa/heatmap2/shots3/limits-{build}.png')
        ok('tooltip names it', '상한가' in pg.evaluate("document.getElementById('tip').innerText") or '하한가' in pg.evaluate("document.getElementById('tip').innerText"))
        leg = pg.evaluate("document.getElementById('legend').innerText")
        ok('legend explains the edge marks', '상한가' in leg or '하한가' in leg, leg[-60:])
    else:
        ok('limit tiles present to check', False, 'none on this map')
    ctx.close()

    # ───── 15 hidden tab stops polling (live) ─────
    if LIVE:
        ctx, pg, log = fresh(b, 'd1280', init=[TIMERS])
        pend = lambda: pg.evaluate("[...window.__tm.values()].filter(n => n === 'poll').length")
        a = pend()
        pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
        b0 = pend(); n0 = len([u for u in log.reqs if u.endswith('api/quotes')])
        pg.wait_for_timeout(1500)
        pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_timeout(1500)
        n1 = len([u for u in log.reqs if u.endswith('api/quotes')]); c1 = pend()
        ok('hidden: no poll timer; visible: fetches at once and resumes', a == 1 and b0 == 0 and n1 == n0 + 1 and c1 == 1, (a, b0, n0, n1, c1))
        ctx.close()

    # ───── world tabs (stub KHWorld; and missing) ─────
    # spy on the real src/world module (wraps show / hide when it installs itself)
    STUB = """Object.defineProperty(window, 'KHWorld', { configurable: true, get() { return undefined; }, set(v) {
      const log = k => (window.__ws = window.__ws || []).push(k);
      const w = Object.assign({}, v, { show(k) { log('show:' + k); return v.show(k); }, hide() { log('hide'); return v.hide(); } });
      Object.defineProperty(window, 'KHWorld', { value: w, writable: true, configurable: true }); } });"""
    GONE = "Object.defineProperty(window, 'KHWorld', { configurable: false, get() { return undefined; }, set(v) {} });"
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'}, init=[STUB])
    pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(400)
    w = pg.evaluate("""() => ({ ws: window.__ws, m: KH.market(), hash: location.hash, world: !document.getElementById('world').hidden && document.getElementById('world').getBoundingClientRect().width,
      stage: getComputedStyle(document.querySelector('main.layout')).display, side: getComputedStyle(document.querySelector('.side')).display === 'none' || !document.querySelector('.side').offsetParent ? 'none' : 'shown',
      tools: ['sizeBy','colorBy','topN','range','palette'].map(k => getComputedStyle(document.querySelector('.ctl[data-ctl="' + k + '"]')).display), basis: document.getElementById('basis').hidden })""")
    pg.wait_for_timeout(2500)
    w['kids'] = pg.evaluate("document.getElementById('world').children.length")
    pg.screenshot(path=ROOT + f'qa/heatmap2/shots3/world-d1280-{build}.png')
    ok('해외: KHWorld.show("index"), #world fills the area, map/side and stock tools hidden, palette/range kept', w['ws'] == ['show:index'] and w['m'] == 'world' and w['hash'] == '#world' and w['world'] > 1200 and w['kids'] > 0
       and w['stage'] == w['side'] == 'none' and w['tools'][:3] == ['none'] * 3 and 'none' not in w['tools'][3:] and w['basis'], w)
    rng = pg.evaluate("[...document.querySelectorAll('#rangeseg button')].map(b => b.textContent)")
    ok('range control shows the day ranges there', rng == ['±3%', '±5%', '±10%'], rng)
    pg.click('.tabs button[data-mkt="CMDTY"]'); pg.wait_for_timeout(300)
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(1200)
    w = pg.evaluate("({ws: window.__ws, m: KH.market(), hash: location.hash, tiles: document.querySelectorAll('#map .tile').length, world: document.getElementById('world').hidden})")
    ok('원자재 → commodity, back to 코스피 → hide() and the map redraws', w['ws'] == ['show:index', 'show:commodity', 'hide'] and w['m'] == 'K' and w['hash'] == '#kospi' and w['tiles'] > 100 and w['world'], w)
    ok('world tabs: console errors 0', not errs(log), errs(log)[:3])
    ctx.close()
    ctx, pg, log = fresh(b, 'm390', hsh='#cmdty')
    pg.wait_for_timeout(2500)
    w = pg.evaluate("({m: KH.market(), kids: document.getElementById('world').children.length, layout: getComputedStyle(document.querySelector('main.layout')).display, over: document.documentElement.scrollWidth - innerWidth})")
    pg.screenshot(path=ROOT + f'qa/heatmap2/shots3/world-m390-{build}.png')
    ok('m390 boot on #cmdty: the real module draws, main.layout hidden, no overflow, console errors 0', w['m'] == 'cmdty' and w['kids'] > 0 and w['layout'] == 'none' and w['over'] == 0 and not errs(log), (w, errs(log)[:3]))
    ctx.close()
    def no_world(route):
        # the module failed to load: serve the page without the src/world <script>
        r = route.fetch(); body = r.text()
        body = re.sub(r'<script>(?:(?!</script>).)*?window\.KHWorld\s*=(?:(?!</script>).)*</script>', '', body, flags=re.S)
        route.fulfill(response=r, body=body)
    # (live only: a file:// page cannot be rewritten, and blocking the global alone still lets the module self-start)
    ctx, pg, log = fresh(b, 'm360', hsh='#cmdty', routes={HM_BASE: no_world}) if LIVE else fresh(b, 'm360', hsh='#kospi')
    if not LIVE: pg.evaluate("location.hash = 'cmdty'"); pg.wait_for_timeout(600)
    w = pg.evaluate("""() => { const t = document.querySelector('.tabs'), a = t.querySelector('[aria-pressed="true"]'), tr = t.getBoundingClientRect(), ar = a.getBoundingClientRect();
      return { msg: document.getElementById('world').innerText, active: a.dataset.mkt, inView: ar.left >= tr.left - 1 && ar.right <= tr.right + 1, scroll: t.scrollWidth > t.clientWidth, over: document.documentElement.scrollWidth - innerWidth }; }""")
    ok('m360 #cmdty ' + ('without KHWorld: fallback message; ' if LIVE else '(hash change): ') + 'tab row scrolls with 원자재 in view; no overflow',
       ('원자재 화면을 불러오지 못했어요' in w['msg'] if LIVE else w['msg'].strip() != '') and w['active'] == 'CMDTY' and w['inView'] and w['over'] == 0, w if not w['inView'] or w['over'] else w['msg'][:60])
    ok('#cmdty boot: console errors 0', not errs(log), errs(log)[:3])
    ctx.close()

    # ───── 17 leftovers ─────
    if not LIVE:
        ctx, pg, log = fresh(b, 'd1280')
        a = pg.evaluate("(() => { const a = [...document.querySelectorAll('#foot a')].find(x => x.textContent === '실시간 버전 열기'); return a ? a.href : null; })()")
        ok('snapshot footer links the live page', a == 'https://kospimap.pages.dev/', a)
        ok('no Worker deploy text in the footer', 'Worker' not in pg.evaluate("document.getElementById('foot').innerText"))
        ctx.close()
    src = open(ROOT + 'src/template.html', encoding='utf-8').read()
    ok('st.nodata gone', 'nodata' not in re.sub(r'--nodata|nodsw|\.nod\b', '', src).replace('NODATA', ''), [m.start() for m in re.finditer('nodata', src)][:5])
    b.close()

print(f'\n{sum(res)}/{len(res)} passed ({build})')
