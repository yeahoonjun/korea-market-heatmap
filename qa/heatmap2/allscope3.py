"""§3-15 ② 종목 수 전체: /api/quotes?scope=all (every listed stock), 15 s refresh, map of every stock; first draw / refresh timing on a
360 px phone. usage: allscope3.py [section…]   sections: mock, timing, quality (default: all)
mock: quotes answered from fixtures/quotes_all.json.gz (a real scope=all response, 11/10 10:47) with the page clock in the session;
timing / quality: the dev Worker harness as it is (real Naver)."""
import sys, os, json, gzip, time
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
WANT = set(sys.argv[1:]) or {'mock', 'timing', 'quality'}
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
SNAP = 'file:///home/claude/hm-heatmap/dist/index.html'
HERE = os.path.dirname(os.path.abspath(__file__))
ALL = json.load(gzip.open(HERE + '/fixtures/quotes_all.json.gz'))
TOP = dict(ALL, stocks=[s for s in ALL['stocks'] if s['m'] == 'K'][:300] + [s for s in ALL['stocks'] if s['m'] == 'Q'][:300])
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]
def mapcount(m): return sum(1 for s in ALL['stocks'] if (m == 'ALL' or s['m'] == m) and s['c'][-1] == '0' and s.get('cap', 0) > 0)


def fresh(b, vp, store=None, mock=False, url=URL, wait=4000):
    ctx = b.new_context(**VIEWPORTS[vp], service_workers='block')
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    reqs = []
    if mock:
        pg.clock.set_fixed_time('2026-11-10T10:47:20+09:00')
        def on_q(r):
            u = r.request.url
            if '?codes=' in u: r.continue_(); return
            reqs.append((time.time(), 'all' if 'scope=all' in u else 'top'))
            r.fulfill(status=200, content_type='application/json', body=json.dumps(ALL if 'scope=all' in u else TOP, ensure_ascii=False))
        pg.route('**/api/quotes*', on_q)
    pg.goto(url)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in dict({'market': 'K'}, **(store or {})).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    reqs.clear()
    pg.reload(); pg.wait_for_timeout(wait)
    return ctx, pg, log, reqs


SEG = "[...document.querySelectorAll('.seg[data-key=\"topN\"] button')].map(b => b.dataset.v + (b.getAttribute('aria-pressed') === 'true' ? '*' : ''))"
TILES = "document.querySelectorAll('#map .tile').length"

with sync_playwright() as p:
    b = launch(p)

    if 'mock' in WANT:
        ctx, pg, log, reqs = fresh(b, 'd1440', mock=True)
        ok('live 종목 수: 100 · 200 · 300* · 전체 (500 is snapshot-only)', pg.evaluate(SEG) == ['100', '200', '300*', 'all'], pg.evaluate(SEG))
        n0 = len(reqs)
        pg.click('.seg[data-key="topN"] button[data-v="all"]'); pg.wait_for_timeout(2500)
        kinds = [k for _, k in reqs[n0:]]
        ok(f"전체 → the next quotes come from scope=all at once; 코스피 map = {mapcount('K')} tiles (every common stock with a cap), stored",
           kinds[:1] == ['all'] and pg.evaluate(TILES) == mapcount('K') and pg.evaluate("localStorage.getItem('khm.topN')") == '"all"', (kinds, pg.evaluate(TILES)))
        pg.click('.tabs button[data-mkt="ALL"]'); pg.wait_for_timeout(1500)
        ok(f"전체 tab: both markets, {mapcount('ALL')} tiles; crumbs say so", pg.evaluate(TILES) == mapcount('ALL') and f"{mapcount('ALL'):,}종목" in pg.evaluate("document.getElementById('crumbs').innerText"), pg.evaluate(TILES))
        lab = pg.evaluate(LABEL_CHECK_JS)
        ok(f'labels inside on the full map ({lab["visible"]} labels shown, small tiles colour only)', lab['overflow'] == 0 and lab['visible'] < pg.evaluate(TILES) / 2, lab['examples'][:1])
        # the 15 s refresh
        # measured from the last quotes request: none for 11 s, the next one by 16.5 s
        pg.wait_for_timeout(16500)
        t0 = reqs[-1][0]; n1 = len(reqs)
        pg.wait_for_timeout(max(0, int((t0 + 11 - time.time()) * 1000))); a = len(reqs) - n1
        pg.wait_for_timeout(max(0, int((t0 + 16.5 - time.time()) * 1000))); b2 = len(reqs) - n1
        gaps = [round(reqs[i][0] - reqs[i - 1][0], 1) for i in range(max(1, len(reqs) - 2), len(reqs))]
        ok(f'refresh every 15 s in 전체 (none within 11 s, one by 17 s; last gaps {gaps})', a == 0 and b2 == 1 and all(k == 'all' for _, k in reqs[n1:]), (a, b2, gaps))
        pg.click('.seg[data-key="topN"] button[data-v="300"]'); pg.wait_for_timeout(1500)
        ok('back to 300: the next quotes are the top-300 stream again, map 300', reqs[-1][1] == 'top' and pg.evaluate(TILES) == 300, (reqs[-3:], pg.evaluate(TILES)))
        ok('mock: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # the snapshot: 전체 = every embedded stock
        ctx, pg, log, _ = fresh(b, 'd1440', store={'topN': 'all'}, url=SNAP, wait=2500)
        n = pg.evaluate(TILES)
        ok(f'snapshot 전체: 100 · 200 · 300 · 500 · 전체*, {n} tiles (> 500)', pg.evaluate(SEG) == ['100', '200', '300', '500', 'all*'] and n > 500 and not errs(log), (pg.evaluate(SEG), n, errs(log)[:2]))
        ctx.close()

    if 'timing' in WANT:
        # a 360 px phone: first draw (response → map drawn) and a refresh (KH.refresh: network, then parse + data + map + side cards)
        for thr in [1, 4]:
            for m in ['K', 'ALL']:
                ctx, pg, log, _ = fresh(b, 'm360', store={'topN': 'all', 'market': m}, wait=200)
                if thr > 1:
                    cdp = ctx.new_cdp_session(pg); cdp.send('Emulation.setCPUThrottlingRate', {'rate': thr})
                    pg.reload()
                pg.wait_for_function(f"document.querySelectorAll('#map .tile').length > {mapcount(m) * 0.9}", timeout=60000)
                first = pg.evaluate("""(() => { const r = performance.getEntriesByType('resource').filter(e => e.name.includes('scope=all')).pop();
                  return { resp: r ? Math.round(r.responseEnd) : null, net: r ? Math.round(r.responseEnd - r.startTime) : null, size: r ? r.encodedBodySize : null, now: Math.round(performance.now()) }; })()""")
                pg.wait_for_timeout(1500)
                refs = []
                for i in range(3):
                    refs.append(pg.evaluate("""async () => { const t0 = performance.now(); await KH.refresh(); const t1 = performance.now();
                      const r = performance.getEntriesByType('resource').filter(e => e.name.includes('scope=all')).pop();
                      return { total: Math.round(t1 - t0), net: Math.round(r.responseEnd - r.startTime), after: Math.round(t1 - r.responseEnd) }; }"""))
                    pg.wait_for_timeout(800)
                refs.sort(key=lambda r: r['after'])
                tiles = pg.evaluate(TILES)
                print(f"INFO m360 CPU×{thr} {m} {tiles} tiles: first draw — response {first['net']} ms ({(first['size'] or 0) // 1024} KB), map drawn ≤ {first['now'] - first['resp']} ms after it; "
                      f"refresh (median of 3) — network {refs[1]['net']} ms, parse + redraw {refs[1]['after']} ms")
                ok(f'm360 CPU×{thr} {m}: drawn, console 0', tiles > mapcount(m) * 0.9 and not errs(log), errs(log)[:2])
                ctx.close()

    if 'quality' in WANT:
        for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
            ctx, pg, log, _ = fresh(b, vp, store={'topN': 'all', 'market': 'ALL'}, wait=6000)
            over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
            lab = pg.evaluate(LABEL_CHECK_JS)
            n = pg.evaluate(TILES)
            ok(f'live 전체·전체 {vp}: {n} tiles, overflow 0, console 0, labels inside ({lab["visible"]})', n > 2000 and over == 0 and not errs(log) and lab['overflow'] == 0, (n, over, errs(log)[:2], lab['examples'][:1]))
            if vp in ('m390', 'd1280'): pg.screenshot(path=HERE + f'/shots3/allscope-{vp}.png')
            ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
