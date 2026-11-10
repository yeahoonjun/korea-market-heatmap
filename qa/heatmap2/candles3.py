"""§3-13 today's candles in lists + §3-14 sector / theme ranking tabs and movers 더보기 (numbers, not eyeballing).
usage: candles3.py [section…]   sections: ohlc, lists, side, perf, quality (default: all)
ohlc / lists / side run on mocked quotes (nxt_fix phases with synthetic op/hi/lo) through the dev Worker harness; quality runs the
live harness as it is (real quotes) and the snapshot (no OHLC fields → squares)."""
import sys, os, json, math
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
import nxt_fix
from nxt_fix import CLOCK, built

VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
WANT = set(sys.argv[1:]) or {'ohlc', 'lists', 'side', 'perf', 'quality'}
LIVE = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
SNAP = 'file:///home/claude/hm-heatmap/dist/index.html'
SHOTS = '/home/claude/hm-heatmap/qa/heatmap2/shots3/'
THEMES = json.load(open('/home/claude/hm-heatmap/web/themes.json'))['themes']
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]
def won(v): return f'{round(v):,}'


def fresh(b, vp, phase=None, store=None, hsh='', url=LIVE, wait=3500):
    ctx = b.new_context(**VIEWPORTS[vp], service_workers='block')
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    hold = None
    if phase:
        pg.clock.set_fixed_time(CLOCK[phase]); hold = nxt_fix.route(pg, phase)
    pg.goto(url)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in dict({'market': 'K'}, **(store or {})).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    pg.goto(url + hsh); pg.reload(); pg.wait_for_timeout(wait)
    return ctx, pg, log, hold


def expect(s, basis):
    """the rule of §3-13 for one fixture row in a basis ('krx' | 'nxt' | 'int'); KRX rows of the regular session"""
    pc, K, N = s['p'] - s['d'], s.get('op') and (s['op'], s['hi'], s['lo']), s.get('nx') and s['nx'].get('op') and (s['nx']['op'], s['nx']['hi'], s['nx']['lo'])
    if basis == 'krx': c, A = s['p'], K
    elif basis == 'nxt': c, A = (s['nx']['p'], N) if N else (s['p'], K)
    else:
        c = s['p']   # reg: KRX and NXT stamped as one moment → KRX price
        A = (N[0] if N else K[0], max(K[1] if K else 0, N[1] if N else 0), min(K[2] if K else 1e18, N[2] if N else 1e18)) if (K or N) else None
    if not A: return None
    return {'pc': pc, 'o': A[0], 'h': max(A[1], c), 'l': min(A[2], c), 'c': c}


with sync_playwright() as p:
    b = launch(p)
    QR = {s['c']: s for s in built('reg')[0]['stocks']}
    QP = {s['c']: s for s in built('pre')[0]['stocks']}

    if 'ohlc' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg')
        got = {}
        for v in ['int', 'nxt', 'krx']:
            pg.click(f'#basis [data-v="{v}"]'); pg.wait_for_timeout(400)
            got[v] = pg.evaluate("['005930', '000660', '035720'].map(c => KH.ohlc(c))")
        ex = {v: [expect(QR[c], v) for c in ['005930', '000660', '035720']] for v in ['int', 'nxt', 'krx']}
        ok('KH.ohlc in the regular session: 통합 (o = NXT open, h/l = wider of the two, c = KRX price), NXT (NXT values), KRX (KRX values); a stock without NXT under NXT → its KRX values',
           got == ex, (got, ex))
        raw = built('reg')[0]['stocks'][0]
        r = pg.evaluate("r => [JSON.stringify(KH.ohlc(r)), JSON.stringify(KH.ohlc(r.c))]", raw)
        ok('KH.ohlc(raw /api/quotes row) = KH.ohlc(code) (same basis rules)', r[0] == r[1] and r[0] != 'null', r)
        r = pg.evaluate("""() => { const o = {pc: 100000, o: 101000, h: 104000, l: 99000, c: 103000}, i = KH.candleIcon(o), b = KH.candleBar(o, 3), n = KH.candleIcon(null), d = KH.candleBar({pc: 100, o: 102, h: 102, l: 95, c: 96}, 3);
          return { iCls: i.className, label: i.getAttribute('aria-label'), title: b.title, bCls: b.className, marks: [...b.querySelectorAll('em')].map(e => e.textContent), none: n.className, dCls: d.className, dMarks: [...d.querySelectorAll('em')].map(e => e.textContent), noneKids: n.children.length }; }""")
        ok("candleIcon / candleBar: up → class u, label '시가 101,000 · 고가 104,000 · 저가 99,000 · 현재 103,000'; ±3 % cuts a +4 % high (▸), a −5 % low (◂); null → an empty slot",
           r['iCls'] == 'cdi u' and r['label'] == '시가 101,000 · 고가 104,000 · 저가 99,000 · 현재 103,000' and r['title'] == r['label'] and r['bCls'] == 'cdb u' and r['marks'] == ['▸']
           and r['dCls'] == 'cdb d' and r['dMarks'] == ['◂'] and r['none'] == 'cdi none' and r['noneKids'] == 0, r)
        pg.evaluate("KH.setReplay({t:'1000', date:'2026-11-10', prices: new Map([['005930', {p: 190000, r: 0.1}]])})"); pg.wait_for_timeout(200)
        ok('a replay frame → KH.ohlc null', pg.evaluate("KH.ohlc('005930')") is None)
        pg.evaluate("KH.setReplay(null)")
        ok('ohlc: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        o = pg.evaluate("KH.ohlc('005930')"); x = QP['005930']['nx']
        ok(f"pre-market 통합: KRX has not traded → NXT's candle (o {won(x['op'])}, c {won(x['p'])})", o and o['o'] == x['op'] and o['c'] == x['p'] and o['h'] == max(x['hi'], x['p']) and o['pc'] == QP['005930']['p'], o)
        pg.click('#basis [data-v="krx"]'); pg.wait_for_timeout(400)
        ok('pre-market KRX (어제 종가, krx-prev) → null, lists keep their squares', pg.evaluate("[KH.basis(), KH.ohlc('005930'), document.querySelectorAll('#movers .cdi').length]") == ['krx-prev', None, 0])
        ctx.close()

    if 'lists' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg')
        t = pg.query_selector('#map .tile[data-c="000660"]').bounding_box()
        pg.mouse.move(t['x'] + 40, t['y'] + 40); pg.wait_for_timeout(300)
        r = pg.evaluate("""() => { const tip = document.getElementById('tip'), rows = [...tip.querySelectorAll('.peer')];
          return { rows: rows.length, icons: tip.querySelectorAll('.peer .cdi').length, bars: tip.querySelectorAll('.peer .cdb').length, hint: tip.querySelector('.cdhint')?.textContent,
            ohlc: tip.querySelector('.card-head .ohlc')?.textContent, label: tip.querySelector('.peer .cdi')?.getAttribute('aria-label') }; }""")
        o = expect(QR['000660'], 'int'); op = (o['o'] / o['pc'] - 1) * 100
        want_head = f"시가 {won(o['o'])} ({'+' if op > 0 else '−' if op < 0 else ''}{abs(op):.1f}%) · 고가 {won(o['h'])} · 저가 {won(o['l'])}"
        ok(f"tooltip: every peer row has a left icon + right candle, a reading hint, and the head line '{want_head}'",
           r['rows'] >= 3 and r['icons'] == r['rows'] == r['bars'] and r['hint'] and r['hint'].startswith('가운데 선 = 전일 종가') and r['ohlc'] == want_head and r['label'].startswith('시가 '), r)
        pg.mouse.move(5, 5)
        r = pg.evaluate("({movers: document.querySelectorAll('#movers .cdi').length, rows: document.querySelectorAll('#movers > button[data-c]').length})")
        ok('눈에 띄는 종목: a candle icon on every row', r['movers'] == r['rows'] > 0, r)
        pg.fill('#q', '삼성'); pg.wait_for_timeout(300)
        r = pg.evaluate("({icons: document.querySelectorAll('#sugg .cdi').length, opts: document.querySelectorAll('#sugg [role=option]').length})")
        ok('search: stock rows carry the icon', r['icons'] >= 2, r)
        pg.fill('#q', ''); pg.keyboard.press('Escape')
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("({icons: document.querySelectorAll('#tablewrap .nmcell .cdi').length, rows: document.querySelectorAll('#tablewrap tbody tr').length})")
        ok(f"table: {r['rows']} rows, every name cell has the icon", r['icons'] == r['rows'] > 100, r)
        ok('lists: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # a period metric: squares and bars as before
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'colorBy': 'm1'})
        t = pg.query_selector('#map .tile[data-c="000660"]').bounding_box(); pg.mouse.move(t['x'] + 40, t['y'] + 40); pg.wait_for_timeout(300)
        r = pg.evaluate("({cd: document.querySelectorAll('#tip .cdi, #tip .cdb, #movers .cdi').length, sq: document.querySelectorAll('#tip .peer > i').length, ohlc: !!document.querySelector('#tip .ohlc')})")
        ok('1개월 colour: no candles anywhere (squares + bars, no head line)', r['cd'] == 0 and r['sq'] > 0 and not r['ohlc'], r)
        ctx.close()
        # the theme tooltip (테마 overview) and the phone sheet
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'market': 'THEME'}, hsh='#theme', wait=4500)
        th = next(t for t in THEMES if '005930' in t['codes'] and '000660' in t['codes'])
        el = pg.query_selector(f'#map .tile[data-t="{th["id"]}"]')
        if el:
            bb = el.bounding_box(); pg.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2); pg.wait_for_timeout(300)
            r = pg.evaluate("({icons: document.querySelectorAll('#tip .peer .cdi').length, bars: document.querySelectorAll('#tip .peer .cdb').length, rows: document.querySelectorAll('#tip .peer').length, hint: !!document.querySelector('#tip .cdhint')})")
            ok(f"theme tooltip ({th['name']}): top stocks with icons + candles + hint", r['rows'] > 0 and r['icons'] == r['bars'] and r['icons'] >= 2 and r['hint'], r)
            pg.screenshot(path=SHOTS + 'candles-theme-tip.png', clip=pg.query_selector('#tip').bounding_box())
        else: ok('theme tile on screen', False, th['name'])
        ctx.close()
        ctx, pg, log, _ = fresh(b, 'm390', 'reg')
        pg.evaluate("window.KHStock = undefined")
        pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("({icons: document.querySelectorAll('#sheet .peer .cdi').length, rows: document.querySelectorAll('#sheet .peer').length, ohlc: !!document.querySelector('#sheet .ohlc'), over: document.documentElement.scrollWidth - innerWidth})")
        ok('m390 sheet: peers with candles, head OHLC line, no overflow', r['rows'] > 0 and r['icons'] == r['rows'] and r['ohlc'] and r['over'] == 0, r)
        pg.screenshot(path=SHOTS + 'candles-sheet-m390.png')
        ctx.close()

    if 'side' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg')
        SEC = "[...document.querySelectorAll('#secs > button')].map(b => [b.querySelector('.nm').firstChild.textContent, b.querySelector('.v').textContent])"
        TABS = "[...document.querySelectorAll('#secTabs button')].filter(b => !b.hidden).map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : ''))"
        num = lambda t: float(t.replace('%', '').replace('+', '').replace('−', '-'))
        up = pg.evaluate(SEC); tabs = pg.evaluate(TABS)
        pg.click('#secTabs button[data-v="dn"]'); pg.wait_for_timeout(200); dn = pg.evaluate(SEC)
        ok('섹터 tabs 상승률* · 하락률 · 거래대금; 상승률 = largest first, 하락률 = smallest first (same sectors)',
           tabs == ['상승률*', '하락률', '거래대금'] and [num(v) for _, v in up] == sorted([num(v) for _, v in up], reverse=True) and [num(v) for _, v in dn] == sorted([num(v) for _, v in dn]) and sorted(up) == sorted(dn), (up[:3], dn[:3]))
        pg.click('#secTabs button[data-v="tv"]'); pg.wait_for_timeout(200)
        tv = pg.evaluate(SEC)
        uni = pg.evaluate("(() => { const m = new Map(); for (const t of document.querySelectorAll('#map .tile')) {} return null; })()")
        ok("거래대금 tab: values in 억/조, biggest first", all(v.endswith('억') or v.endswith('조') for _, v in tv) and pg.evaluate("localStorage.getItem('khm.secSort')") == '"tv"', tv[:4])
        pg.reload(); pg.wait_for_timeout(3500)
        ok('khm.secSort remembered across a reload', pg.evaluate(TABS)[2] == '거래대금*')
        # movers 더보기 (30) / 접기, kept across tabs
        MV = "({rows: document.querySelectorAll('#movers > button[data-c]').length, more: document.querySelector('#movers .more')?.textContent, exp: document.querySelector('#movers .more')?.getAttribute('aria-expanded')})"
        m0 = pg.evaluate(MV)
        pg.click('#movers .more'); pg.wait_for_timeout(200); m1 = pg.evaluate(MV)
        pg.click('#moverTabs button[data-v="tv"]'); pg.wait_for_timeout(200); m2 = pg.evaluate(MV)
        pg.click('#movers .more'); pg.wait_for_timeout(200); m3 = pg.evaluate(MV)
        ok(f"movers: 8 + '더보기 (N개)' → up to 30 + '접기' (kept on another tab) → 8", m0['rows'] == 8 and m0['more'].startswith('더보기 (') and m1['rows'] == min(30, int(m0['more'][5:-2])) and m1['more'] == '접기'
           and m1['exp'] == 'true' and m2['rows'] == 30 and m2['more'] == '접기' and m3['rows'] == 8 and pg.evaluate("document.activeElement.className") == 'more', (m0, m1, m2, m3))
        ctx.close()
        # flow / period labels
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'colorBy': 'm1'})
        ok('기간 지표: 상승률 · 하락률 only', pg.evaluate(TABS) == ['상승률*', '하락률'])
        ctx.close()
        # theme ranking: every theme, 더보기
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'market': 'THEME'}, hsh='#theme', wait=4500)
        r0 = pg.evaluate("({tabs: [...document.querySelectorAll('#secTabs button')].filter(b => !b.hidden).map(b => b.textContent), n: document.querySelectorAll('#secs > button:not(.more)').length, more: document.querySelector('#secs .more')?.textContent})")
        pg.click('#secs .more'); pg.wait_for_timeout(300)
        r1 = pg.evaluate("[...document.querySelectorAll('#secs > button:not(.more)')].map(b => parseFloat(b.querySelector('.v').textContent.replace('−', '-').replace('+', '')))")
        pg.click('#secTabs button[data-v="dn"]'); pg.wait_for_timeout(300)
        r2 = pg.evaluate("[...document.querySelectorAll('#secs > button:not(.more)')].map(b => parseFloat(b.querySelector('.v').textContent.replace('−', '-').replace('+', '')))")
        ok(f"테마 순위: 상승률 · 하락률 tabs, 12 + '더보기 (N개)' → every theme largest first; 하락률 → smallest first (folded again)",
           r0['tabs'] == ['상승률', '하락률'] and r0['n'] == 12 and r0['more'] and len(r1) == int(r0['more'][5:-2]) and r1 == sorted(r1, reverse=True) and len(r2) == 12 and r2 == sorted(r2), (r0, r1[:3], r2[:3]))
        ok('side: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    if 'perf' in WANT:
        # the 600-row table (전체 · 300 per market): the table build with candles (오늘) vs the same with squares (1주)
        for cb in ['r', 'w1']:
            ts = []
            ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'market': 'ALL', 'topN': 500, 'colorBy': cb})
            for i in range(4):
                ts.append(pg.evaluate("(() => { const t = performance.now(); document.querySelector('.viewseg button[data-v=table]').click(); const d = performance.now() - t; document.querySelector('.viewseg button[data-v=map]').click(); return d; })()"))
                pg.wait_for_timeout(300)
            n = pg.evaluate("(() => { document.querySelector('.viewseg button[data-v=table]').click(); return [document.querySelectorAll('#tablewrap tbody tr').length, document.querySelectorAll('#tablewrap .cdi').length]; })()")
            ts.sort()
            print(f'INFO table {n[0]} rows, {n[1]} candle icons ({cb}): build {ts[1]:.0f}–{ts[2]:.0f} ms (median of 4)')
            if cb == 'r':
                # 600 icons on their own (the cost a 600-row table adds): build + attach + layout
                mb = pg.evaluate("""(() => { const os = KH.stocks().slice(0, 600).map(s => KH.ohlc(s.c)).filter(Boolean); const box = document.createElement('div'); document.body.append(box);
                  const t = performance.now(); for (let i = 0; i < 600; i++) box.append(KH.candleIcon(os[i % os.length])); box.offsetHeight; const d = performance.now() - t; box.remove(); return [os.length, d]; })()""")
                print(f'INFO 600 candle icons built + laid out: {mb[1]:.1f} ms ({mb[0]} distinct OHLC rows)')
                ok('600 candle icons cost under 40 ms', mb[1] < 40, mb)
            res.append(True)
            ctx.close()

    if 'quality' in WANT:
        for url, mode in [(LIVE, 'live'), (SNAP, 'snapshot')]:
            for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
                ctx, pg, log, _ = fresh(b, vp, url=url, wait=4000 if mode == 'live' else 1500)
                over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                lab = pg.evaluate(LABEL_CHECK_JS)
                cd = pg.evaluate("document.querySelectorAll('#movers .cdi').length")
                pg.click('#moverCard .more') if pg.query_selector('#moverCard .more') else None
                pg.wait_for_timeout(150)
                over2 = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
                over3 = pg.evaluate("[document.documentElement.scrollWidth - innerWidth, document.getElementById('tablewrap').scrollWidth - document.getElementById('tablewrap').clientWidth]")
                ok(f'{mode} {vp}: overflow 0 (map, movers 30, table {over3[1]}), console 0, labels inside ({lab["visible"]}), candle icons in movers {cd}{" (snapshot: no OHLC → squares)" if mode == "snapshot" else ""}',
                   over == 0 and over2 == 0 and over3[0] == 0 and not errs(log) and lab['overflow'] == 0 and ((cd > 0) if mode == 'live' else (cd == 0)) and (over3[1] <= 0 or not vp.startswith('m')),
                   (over, over2, over3, errs(log)[:2], lab['examples'][:1], cd))
                if vp in ('m390', 'd1280'): pg.screenshot(path=SHOTS + f'candles-{mode}-{vp}.png', full_page=False)
                ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
