"""Heatmap v2 checks (numbers, not eyeballing). usage: verify2.py [snapshot|live]
themes overview / drill-down, period colours, flow sizes, limit chips, watchlist, KH hooks (loadData, watch, layout, setReplay, kh:render)."""
import os; HM_BASE = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')   # dev Worker (harness) port
import sys, json, re, math, urllib.request
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright

build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
LIVE = build == 'live'
URL = HM_BASE if LIVE else 'file:///home/claude/hm-heatmap/dist/index.html'
ROOT = '/home/claude/hm-heatmap/'
THEMES = json.load(open(ROOT + 'web/themes.json'))
PERIODS = json.load(open(ROOT + 'web/periods.json'))
FLOWS = json.load(open(ROOT + 'web/flows.json'))
SNAP = {s['c']: s for s in json.load(open(ROOT + 'data/snapshot.json'))['stocks']}
WAIT = 3500 if LIVE else 1300
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, info if not cond or len(str(info)) < 160 else str(info)[:160])


def api(path):
    with urllib.request.urlopen(HM_BASE + path, timeout=20) as r:
        return json.load(r)


def pnum(t):
    t = t.replace('−', '-').replace('%', '').replace('+', '').replace(',', '').strip()
    return float(t)


def amt_text(v):
    a = abs(v); s = '' if a < 0.5 else ('+' if v > 0 else '−')
    if a >= 10000:
        x = round(a / 10000, 1)
        return s + (f'{x:,.1f}'.rstrip('0').rstrip('.') if x % 1 else f'{int(x):,}') + '조'
    return s + f'{round(a):,}' + '억'


def fresh(b, vp, store=None, hsh='', init=None):
    ctx = b.new_context(**VIEWPORTS[vp])
    ctx.add_init_script("document.addEventListener('kh:watch',e=>(window.__kw=window.__kw||[]).push(e.detail));document.addEventListener('kh:render',e=>(window.__kr=(window.__kr||0)+1));")
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    pg.goto(URL)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);"
    for k, v in (store or {}).items():
        js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    pg.goto(URL + hsh)
    pg.reload()
    pg.wait_for_timeout(WAIT)
    return ctx, pg, log


with sync_playwright() as p:
    b = launch(p)
    # ───── 1 theme overview: 265 tiles, sizes by theme cap ─────
    ctx, pg, log = fresh(b, 'd1280', hsh='#theme')
    n = pg.evaluate("document.querySelectorAll('#map .tile.th:not(.leaving)').length")
    ok('theme overview tiles = 265', n == 265 == len(THEMES['themes']), n)
    # area ∝ cap for the 3 biggest themes (flat map, 2px gaps)
    lay = pg.evaluate("KH.layout()")
    ths = sorted([t for t in lay if t['kind'] == 'tile'], key=lambda t: -t['w'] * t['h'])[:3]
    caps = {t['name']: t['cap'] for t in THEMES['themes']}
    r1 = (ths[0]['w'] * ths[0]['h']) / (ths[2]['w'] * ths[2]['h']); r2 = caps[ths[0]['label']] / caps[ths[2]['label']]
    ok('theme tile area ∝ theme cap', abs(r1 / r2 - 1) < 0.05, f'{r1:.3f} vs {r2:.3f}')
    # colour: live = /api/themes ratio, snapshot = cap-weighted member change
    if LIVE:
        lt = {t['id']: t['ratio'] for t in api('api/themes')['themes']}
        bad = []
        for tid in [228, 12, 8]:
            txt = pg.evaluate(f"(()=>{{const e=document.querySelector('#map .tile.th[data-t=\"{tid}\"]');return e?e.getAttribute('aria-label'):null}})()")
            m = re.search(r'테마 ([+−]?[\d.]+)%', txt or '')
            if not m or abs(pnum(m.group(1)) - lt[tid]) > 0.006: bad.append((tid, txt, lt[tid]))
        ok('theme colour value = /api/themes ratio (3 themes)', not bad, bad)
    else:
        bad = []
        for t in THEMES['themes'][:3]:
            now = before = 0
            for c in t['codes']:
                s = SNAP.get(c)
                if s and s['cap']: now += s['cap']; before += s['cap'] / (1 + s['r'] / 100)
            exp = (now / before - 1) * 100
            txt = pg.evaluate(f"document.querySelector('#map .tile.th[data-t=\"{t['id']}\"]').getAttribute('aria-label')")
            m = re.search(r'테마 ([+−]?[\d.]+)%', txt)
            if not m or abs(pnum(m.group(1)) - exp) > 0.006: bad.append((t['id'], txt, round(exp, 3)))
        ok('theme colour = cap-weighted member change (3 themes)', not bad, bad)
    ok('side panel switches to 테마 순위', pg.evaluate("document.getElementById('secTitle').textContent") == '테마 순위' and pg.evaluate("document.querySelectorAll('#secs button').length") == 12)
    # keyboard: Enter on a theme tile drills down; Esc returns
    pg.evaluate("document.querySelector('#map .tile.th[data-t=\"228\"]').focus()"); pg.keyboard.press('Enter'); pg.wait_for_timeout(WAIT)
    crumbs = pg.evaluate("document.getElementById('crumbs').textContent")
    ok('Enter on theme → 테마 › name, #theme-228', '테마›국내 상장 중국기업' in crumbs.replace(' ', '').replace('국내상장중국기업', '국내 상장 중국기업') or ('테마' in crumbs and '국내 상장 중국기업' in crumbs) and pg.evaluate("location.hash") == '#theme-228', (crumbs[:60], pg.evaluate("location.hash")))
    # ───── 2 drill-down members + live prices ─────
    members = next(t for t in THEMES['themes'] if t['id'] == 228)['codes']
    tiles = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.leaving)')].map(e=>e.dataset.c)")
    if LIVE:
        q = {s['c']: s for s in api('api/quotes?codes=' + ','.join(members))['stocks']}
        expect = [c for c in members if q.get(c) and (q[c]['cap'] > 0)]
        ok('drill-down shows every member with a quote', sorted(tiles) == sorted(expect), (len(tiles), len(expect)))
        got = pg.evaluate(f"{json.dumps(members)}.map(c=>{{const s=KH.stock(c);return s?[c,s.p,s.r]:null}})")
        bad = [g for g in got if g and abs(g[1] - q[g[0]]['p']) > 0]
        ok('member prices = /api/quotes?codes= (live)', not bad and len([g for g in got if g]) == len(expect), bad[:3])
        reqs = [u for u in log.reqs if 'api/quotes?codes=' in u]
        ok('fetched via /api/quotes?codes= (≤300 codes)', reqs and all(len(u.split('codes=')[1].split(',')) <= 300 for u in reqs), len(reqs))
        # table view prices
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
        rows = pg.evaluate("[...document.querySelectorAll('#tablewrap tbody tr')].map(tr=>[tr.dataset.c, tr.children[2].textContent])")
        bad = [r for r in rows if int(r[1].replace(',', '')) != q[r[0]]['p']]
        ok('table 현재가 = live quote', rows and not bad, bad[:3])
        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
    else:
        expect = [c for c in members if c in SNAP and SNAP[c]['cap'] > 0]
        ok('drill-down shows every member in the snapshot', sorted(tiles) == sorted(expect), (len(tiles), len(expect)))
    # limit chip in the drill-down (900300 is limit-up today)
    chip = pg.evaluate("(()=>{const e=document.querySelector('#map .tile[data-c=\"900300\"] .lim');return e?[e.hidden,e.textContent]:null})()")
    ok('limit chip 상 on 900300 in theme 228', chip == [False, '상'], chip)
    ok('side shows 테마 순위 with rank', '위 /' in pg.evaluate("document.getElementById('secSub').textContent"))
    # search in the theme tab lists themes; picking one opens it
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    pg.fill('#q', '반도체'); pg.wait_for_timeout(250)
    sug = pg.evaluate("[...document.querySelectorAll('#sugg button')].map(b=>b.textContent)")
    ok('theme search suggests themes', sug and all('종목' in x for x in sug), sug[:3])
    pg.keyboard.press('Enter'); pg.wait_for_timeout(WAIT)
    ok('picking a theme opens it', pg.evaluate("location.hash").startswith('#theme-') and pg.evaluate("!!document.querySelector('#crumbs .back')"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    ok('Esc returns to theme overview', pg.evaluate("location.hash") == '#theme' and pg.evaluate("document.querySelectorAll('#map .tile.th:not(.leaving)').length") == 265)
    ok('console clean (themes)', not log.console, log.console[:3])
    ctx.close()

    # ───── 3 period colours: p / base − 1 ─────
    ctx, pg, log = fresh(b, 'd1280', store={'colorBy': 'm1', 'market': 'K'})
    codes = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.leaving)')].slice(0,40).map(e=>e.dataset.c)")
    pick = [c for c in codes if PERIODS['c'].get(c) and PERIODS['c'][c][1]][:3]
    bad = []
    for c in pick:
        p_now = pg.evaluate(f"KH.stock('{c}').p")
        exp = (p_now / PERIODS['c'][c][1] - 1) * 100
        lab = pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{c}\"]').getAttribute('aria-label')")
        got = pnum(re.search(r'([+−]?[\d.]+)%', lab).group(1))
        col = pg.evaluate(f"""(()=>{{const pal=KH.palette().stops, R=20;
          const sc=d3.scaleLinear().domain([-R,-R*2/3,-R/3,0,R/3,R*2/3,R]).range(pal).interpolate(d3.interpolateLab).clamp(true);
          const want=sc({exp}); const el=document.querySelector('#map .tile[data-c="{c}"]');
          const a=getComputedStyle(el).backgroundColor, b2=d3.color(want)+'';
          return [a, b2]}})()""")
        if abs(got - exp) > 0.006 or col[0] != col[1]: bad.append((c, round(exp, 3), got, col))
    ok(f'1개월 colour + label = p/base−1 for {len(pick)} stocks', len(pick) == 3 and not bad, bad or pick)
    ok('legend names the metric + base date', '1개월 수익률' in pg.evaluate("document.getElementById('legend').textContent") and '종가 대비' in pg.evaluate("document.getElementById('legend').textContent"))
    hist_total = pg.evaluate("[...document.querySelectorAll('#hist .cnt')].reduce((a,e)=>a+ +e.textContent,0)")
    tiles_n = pg.evaluate("document.querySelectorAll('#map .tile:not(.leaving)').length")
    nod = pg.evaluate("document.querySelectorAll('#map .tile.nod:not(.leaving)').length")
    ok('histogram counts tiles with data (metric-aware)', hist_total == tiles_n - nod, (hist_total, tiles_n, nod))
    ok('dist title follows metric', pg.evaluate("document.getElementById('distTitle').textContent") == '1개월 수익률 분포')
    # tooltip: metric + today's %
    c0 = pick[0]
    box = pg.locator(f'#map .tile[data-c="{c0}"]').bounding_box(); pg.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2); pg.wait_for_timeout(200)
    tt = pg.evaluate("document.getElementById('tip').textContent")
    ok('tooltip shows 1개월 return and today %', '1개월 수익률' in tt and '오늘' in tt, tt[:120])
    # missing base → grey 데이터 없음 (a stock whose base is null)
    nb = [c for c, v in PERIODS['c'].items() if v[1] is None and c in SNAP]
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
    cells = pg.evaluate("[...document.querySelectorAll('#tablewrap thead th')].map(t=>t.textContent)")
    ok('table adds the 1개월 column', '1개월' in cells and '오늘' in cells, cells)
    tv = pg.evaluate(f"(()=>{{const tr=document.querySelector('#tablewrap tr[data-c=\"{pick[1]}\"]');return tr?tr.children[3].textContent:null}})()")
    exp1 = (pg.evaluate(f"KH.stock('{pick[1]}').p") / PERIODS['c'][pick[1]][1] - 1) * 100
    ok('table 1개월 cell = p/base−1 (2 dp)', tv and abs(pnum(tv) - exp1) < 0.006, (tv, round(exp1, 3)))
    ctx.close()
    # range presets per metric
    ctx, pg, log = fresh(b, 'd1280', store={'colorBy': 'ytd'})
    ok('period range presets ±10/±20/±50', pg.evaluate("[...document.querySelectorAll('#rangeseg button')].map(b=>b.textContent).join(' ')") == '±10% ±20% ±50%')
    ctx.close()

    # ───── 4 flow sizes ─────
    ctx, pg, log = fresh(b, 'd1280', store={'sizeBy': 'fgn', 'flowWin': 5}, hsh='#theme-12')
    pg.wait_for_timeout(WAIT)
    lay = [t for t in pg.evaluate("KH.layout()") if t['kind'] == 'tile']
    lay.sort(key=lambda t: -t['w'] * t['h'])
    top = lay[:3]
    a = [abs(FLOWS['f'][t['code']][3]) for t in top]
    r_area = (top[0]['w'] * top[0]['h']) / (top[2]['w'] * top[2]['h']); r_amt = a[0] / a[2]
    ok('flow tile area ∝ |외국인 5일| (3 stocks, theme map)', abs(r_area / r_amt - 1) < 0.06, (round(r_area, 3), round(r_amt, 3), [t['code'] for t in top]))
    bad = [(t['code'], t['sub'], amt_text(FLOWS['f'][t['code']][3])) for t in top if t['sub'] != amt_text(FLOWS['f'][t['code']][3])]
    ok('flow tile label = flows.json amount', not bad, bad)
    # colour = direction: buy → up side, sell → down side
    # colour = net buying ÷ market cap on the palette scale (5일 default range ±1 %): buy → up end, sell → down end
    fl = {c: FLOWS['f'][c][3] for c in [t['code'] for t in lay]}
    dirs = pg.evaluate("""((fl)=>{const pal=KH.palette(), R=1;const sc=d3.scaleLinear().domain([-R,-R*2/3,-R/3,0,R/3,R*2/3,R]).range(pal.stops).interpolate(d3.interpolateLab).clamp(true);
      const out=[];for(const t of KH.layout()){if(t.kind!=='tile')continue;const s=KH.stock(t.code);const v=fl[t.code]/s.cap*100;
      const want=v===0?pal.flat:sc(v);out.push([t.code,t.sub,d3.color(t.color)+'',d3.color(want)+'', v>=R/3?'buy':v<=-R/3?'sell':'']);}return out})""", fl)
    wrong = [d for d in dirs if d[2] != d[3]]
    ends = [d for d in dirs if d[4] == 'buy' and d[2] == d3_up] if False else []
    ok(f'flow colour = scale(amount ÷ cap) for {len(dirs)} tiles', dirs and not wrong, wrong[:3])
    big_buy = [d for d in dirs if d[4] == 'buy']; big_sell = [d for d in dirs if d[4] == 'sell']
    ok('strong net buy sits on the up side, net sell on the down side', all(d[1].startswith('+') for d in big_buy) and all(d[1].startswith('−') for d in big_sell), (len(big_buy), len(big_sell)))
    leg = pg.evaluate("document.getElementById('legend').textContent")
    ok('flow legend says 순매수/순매도 + asOf', '순매수' in leg and '순매도' in leg and '11월 9일 기준' in leg, leg)
    ctx.close()
    # market map in flow mode: excluded count matches flows.json
    ctx, pg, log = fresh(b, 'd1280', store={'sizeBy': 'inst', 'flowWin': 20, 'market': 'K', 'topN': 300})
    leg = pg.evaluate("document.getElementById('legend').textContent")
    if LIVE:
        pool = [s for s in api('api/quotes')['stocks'] if s['m'] == 'K' and s['c'].endswith('0') and s['cap'] > 0]
    else:
        pool = [s for s in SNAP.values() if s['m'] == 'K' and s['c'].endswith('0') and s['cap'] > 0]
    nod = sum(1 for s in pool if not FLOWS['f'].get(s['c']) or not FLOWS['f'][s['c']][6])
    m = re.search(r'데이터 없는 (\d+)종목', leg)
    ok('flow mode says how many were left out', (m and int(m.group(1)) == nod) or (nod == 0 and not m), (m.group(1) if m else None, nod))
    tl = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.leaving)')].map(e=>e.dataset.c)")
    want = sorted([s for s in pool if FLOWS['f'].get(s['c']) and FLOWS['f'][s['c']][6]], key=lambda s: -abs(FLOWS['f'][s['c']][6]))[:300]
    ok('flow map = top 300 by |기관 20일|', sorted(tl) == sorted(s['c'] for s in want), (len(tl), len(want)))
    ok('colour metric control disabled in flow mode', pg.evaluate("document.querySelector('.ctl[data-ctl=colorBy]').classList.contains('off')") and not pg.evaluate("document.querySelector('.ctl[data-ctl=flowWin]').hidden"))
    ctx.close()

    # ───── 5 limit chips via the watchlist ─────
    limits = [c for c, s in SNAP.items() if s.get('lim') and c.endswith('0')]
    if LIVE:
        q = api('api/quotes?codes=' + ','.join(limits))['stocks']
        limits_live = {s['c']: s.get('lim', 0) for s in q}
    ctx, pg, log = fresh(b, 'd1280', store={'watch': limits}, hsh='#watch')
    pg.wait_for_timeout(WAIT)
    got = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.leaving)')].map(e=>{const l=e.querySelector('.lim');const r=e.getBoundingClientRect();return [e.dataset.c, l&&!l.hidden?l.textContent:'', Math.round(r.width), Math.round(r.height)]})")
    want = {c: ('상' if (limits_live[c] if LIVE else SNAP[c]['lim']) > 0 else '하') for c in limits if (limits_live.get(c) if LIVE else True)}
    bad = [g for g in got if (g[1] and want.get(g[0]) != g[1]) or (not g[1] and want.get(g[0]) and g[2] >= 100 and g[3] >= 100)]
    shown = sum(1 for g in got if g[1])
    ok(f'limit chips: {shown}/{len(want)} limit stocks chipped, every tile ≥100×100 has one, none wrong', len(got) == len(limits) and not bad and shown >= len(want) - 2, (len(got), bad, [g for g in got if not g[1]]))
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
    tags = pg.evaluate("[...document.querySelectorAll('#tablewrap .limtag')].map(e=>e.textContent)")
    ok('table shows 상한가/하한가 tags', len(tags) == len(want) and set(tags) <= {'상한가', '하한가'}, tags)
    ok('KH.stock(c).lim kept on rows', pg.evaluate(f"KH.stock('{limits[0]}').lim") in (1, -1))
    ctx.close()

    # ───── 6 watchlist: add / remove / persist ─────
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'})
    t = pg.locator('#map .tile:not(.leaving)').first
    code = t.get_attribute('data-c'); bx = t.bounding_box()
    pg.mouse.move(bx['x'] + bx['width'] / 2, bx['y'] + bx['height'] / 2); pg.wait_for_timeout(150)
    star_vis = pg.evaluate("!document.querySelector('.tstar').hidden")
    tt = pg.evaluate("document.getElementById('tip').textContent")
    sb = pg.locator('.tstar').bounding_box(); pg.mouse.move(sb['x'] + 8, sb['y'] + 8); pg.mouse.click(sb['x'] + 8, sb['y'] + 8); pg.wait_for_timeout(200)
    ok('hover ☆ on tile adds to watchlist', star_vis and pg.evaluate("KH.watch.list()") == [code] and pg.evaluate("KH.watch.has(arguments[0])" if False else f"KH.watch.has('{code}')"), (star_vis, pg.evaluate("KH.watch.list()")))
    ok('tooltip shows the star state', '관심' in pg.evaluate("document.getElementById('tip').textContent") and '☆' in tt)
    ok('kh:watch fired with detail', pg.evaluate("JSON.stringify(window.__kw)") == json.dumps([{'code': code, 'on': True, 'list': [code]}]).replace(' ', ''), pg.evaluate("JSON.stringify(window.__kw)"))
    ok('stored in localStorage khm.watch', json.loads(pg.evaluate("localStorage.getItem('khm.watch')")) == [code])
    pg.evaluate("KH.watch.toggle('000660')" if code != '000660' else "KH.watch.toggle('005930')")
    pg.reload(); pg.wait_for_timeout(WAIT)
    ok('persists across reload', len(pg.evaluate("KH.watch.list()")) == 2 and code in pg.evaluate("KH.watch.list()"))
    pg.click('.tabs button[data-mkt="WATCH"]'); pg.wait_for_timeout(WAIT if LIVE else 600)
    wt = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.leaving)')].map(e=>e.dataset.c)")
    ok('★관심 view shows the watched stocks (#watch)', sorted(wt) == sorted(pg.evaluate("KH.watch.list()")) and pg.evaluate("location.hash") == '#watch', wt)
    ok('grouped by sector (sector nodes, no industry level)', pg.evaluate("document.querySelectorAll('#map .sec:not(.leaving)').length") >= 1 and pg.evaluate("document.querySelectorAll('#map .ind:not(.leaving)').length") == 0)
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
    pg.click(f'#tablewrap tr[data-c="{code}"] .wbtn'); pg.wait_for_timeout(400)
    ok('table ☆ removes', code not in pg.evaluate("KH.watch.list()") and not pg.evaluate(f"!!document.querySelector('#tablewrap tr[data-c=\"{code}\"]')"))
    pg.evaluate("KH.watch.toggle(KH.watch.list()[0])"); pg.wait_for_timeout(300)
    pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(400)
    ok('empty state text', '타일에서 ☆를 눌러 추가해요' in pg.evaluate("document.querySelector('#map .map-empty').textContent"))
    ok('console clean (watch)', not log.console, log.console[:3])
    ctx.close()
    # mobile: sheet star
    ctx, pg, log = fresh(b, 'm390', store={'market': 'K'})
    t = pg.locator('#map .tile:not(.leaving)').first; code = t.get_attribute('data-c'); t.tap(force=True); pg.wait_for_timeout(300)
    pg.evaluate("document.querySelector('#sheet .wstar').click()"); pg.wait_for_timeout(200)
    ok('m390 sheet ☆ adds', pg.evaluate("KH.watch.list()") == [code] and pg.evaluate("document.querySelector('#sheet .wstar').getAttribute('aria-pressed')") == 'true')
    hgt = pg.evaluate("document.querySelector('#sheet .wstar').getBoundingClientRect().height")
    ok('m390 sheet star tap target ≥ 40', hgt >= 39.5, hgt)
    ctx.close()

    # ───── 7 hooks ─────
    ctx, pg, log = fresh(b, 'd1280', store={'market': 'K'})
    ok('KH.loadData themes/periods/flows', pg.evaluate("Promise.all(['themes','periods','flows'].map(n=>KH.loadData(n))).then(a=>[a[0].themes.length, Object.keys(a[1].c).length, Object.keys(a[2].f).length])") == [265, len(PERIODS['c']), len(FLOWS['f'])])
    ok('KH.loadData memoised (same object)', pg.evaluate("Promise.all([KH.loadData('themes'),KH.loadData('themes')]).then(([a,b])=>a===b)"))
    ok('KH.loadData unknown → null', pg.evaluate("KH.loadData('nope').then(x=>x===null)"))
    ok('KH.index()', pg.evaluate("(()=>{const x=KH.index();return !!(x&&x.KOSPI&&isFinite(x.KOSPI.value))})()"))
    ok('KH.market()', pg.evaluate("KH.market()") == 'K')
    lay = pg.evaluate("KH.layout()")
    kinds = {k: sum(1 for x in lay if x['kind'] == k) for k in ('sector', 'ind', 'tile')}
    dom = pg.evaluate("[document.querySelectorAll('#map .sec:not(.leaving)').length,document.querySelectorAll('#map .ind:not(.leaving)').length,document.querySelectorAll('#map .tile:not(.leaving)').length]")
    hidden_ok = all((x['label'] == '' and x['sub'] == '') if x['hd'] == 0 else bool(x['label']) for x in lay if x['kind'] != 'tile')
    ok('KH.layout() mirrors the DOM (+code, hd)', [kinds['sector'], kinds['ind'], kinds['tile']] == dom and all(x.get('code') for x in lay if x['kind'] == 'tile') and hidden_ok, (kinds, dom))
    ok('KH.layout() tile sub = text shown', all(x['sub'] in ('—',) or re.match(r'^[+−]?\d+\.\d+%$', x['sub']) for x in lay if x['kind'] == 'tile'))
    # replay
    r0 = pg.evaluate("window.__kr")
    big = sorted([x for x in lay if x['kind'] == 'tile'], key=lambda x: -x['w'] * x['h'])
    c1, c2 = big[0]['code'], big[1]['code']
    area0 = big[0]['w'] * big[0]['h']
    sec_before = pg.evaluate("document.querySelector('#map .sec:not(.leaving) .hd .v').textContent")
    # frame A: every 코스피 stock at +5 % except c2 → sector headers / side panels follow it
    pg.evaluate("""((c2)=>{const m=new Map();for(const s of KH.stocks()){if(s.m!=='K'||s.c===c2)continue;const prev=s.p-s.d;m.set(s.c,{p:prev*1.05,r:5});}
      KH.setReplay({t:'1030',date:'2026-11-09',prices:m})})""", c2)
    pg.wait_for_timeout(200)
    sec2 = pg.evaluate("KH.stock(arguments[0]).s" if False else f"KH.stock('{c2}').s")
    hdr = pg.evaluate("""((s2)=>[...document.querySelectorAll('#map .sec:not(.leaving)')].filter(e=>e.dataset.s!==s2).map(e=>e.querySelector('.hd .v').textContent).filter(Boolean))""", sec2)
    ok('sector headers follow the frame (+5.0%)', hdr and all(x == '+5.0%' for x in hdr), hdr[:5])
    side = pg.evaluate("document.getElementById('wavg').textContent")
    ok('side panels follow the frame', 3.5 < pnum(side) <= 5.0, side)
    ok('histogram follows the frame', pg.evaluate("document.querySelectorAll('#hist .cnt')[8].textContent") != '0')
    # frame B: c1 at +25 %, c2 missing (keeps live)
    pg.evaluate("""(([c1,c2])=>{const m=new Map();for(const s of KH.stocks()){if(s.m!=='K'||s.c===c2)continue;m.set(s.c,{p:s.p,r:s.r});}
      const s1=KH.stock(c1);m.set(c1,{p:Math.round((s1.p-s1.d)*1.25),r:25});KH.setReplay({t:'1035',date:'2026-11-09',prices:m})})""", [c1, c2])
    pg.wait_for_timeout(200)
    lab1 = pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{c1}\"]').getAttribute('aria-label')")
    lab2 = pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{c2}\"]').getAttribute('aria-label')")
    live2 = pg.evaluate(f"KH.fmt.pct(KH.stock('{c2}').r)")
    ok('setReplay overrides p/r (label)', '+25.00%' in lab1, lab1)
    ok('codes missing from the frame keep live values', live2 in lab2, (lab2, live2))
    ok('리플레이 HH:MM visible (status + legend)', pg.evaluate("document.querySelector('#status .badge').textContent") == '리플레이 10:35' and '리플레이 10:35' in pg.evaluate("document.getElementById('legend').textContent"))
    ok('kh:render fired', pg.evaluate("window.__kr") > r0)
    lay2 = {x.get('code'): x for x in pg.evaluate("KH.layout()") if x['kind'] == 'tile'}
    ok('size follows cap × p_frame / p_now', lay2[c1]['w'] * lay2[c1]['h'] > area0 * 1.05, (area0, lay2[c1]['w'] * lay2[c1]['h']))
    # survives a re-render (resize) and a poll-like data event
    pg.set_viewport_size({'width': 1300, 'height': 820}); pg.wait_for_timeout(400)
    if LIVE:
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(2500)
    ok('overlay survives re-render / poll', '+25.00%' in pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{c1}\"]').getAttribute('aria-label')"))
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(200)
    ok('setReplay(null) restores live', '+25.00%' not in pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{c1}\"]').getAttribute('aria-label')") and '리플레이' not in pg.evaluate("document.querySelector('#status .badge').textContent"))
    ok('console clean (hooks)', not log.console, log.console[:3])
    ctx.close()
    b.close()
print(f'\nSUMMARY {sum(res)} / {len(res)} passed ({build})')
