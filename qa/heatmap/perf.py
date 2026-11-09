import sys, statistics; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import *
INIT = r"""
window.__lt = [];
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]); }).observe({ type: 'longtask', buffered: true }); } catch (e) {}
window.__frames = null;
window.__startFrames = () => { window.__frames = []; let last = performance.now(); const f = t => { if (!window.__frames) return; window.__frames.push(t - last); last = t; requestAnimationFrame(f); }; requestAnimationFrame(f); };
window.__stopFrames = () => { const f = window.__frames || []; window.__frames = null; return f; };
"""
def measure(pg, action, ms=1200):
    pg.evaluate("window.__lt = []; window.__startFrames(); window.__t0 = performance.now()")
    action()
    pg.wait_for_timeout(ms)
    fr = pg.evaluate("window.__stopFrames()")
    lt = pg.evaluate("window.__lt.filter(e => e[0] >= window.__t0 - 5)")
    fr = fr[1:] if fr else fr
    return {'longtasks_ms': [d for _, d in lt], 'frames': len(fr), 'max_frame_gap_ms': round(max(fr), 1) if fr else None,
            'frames_over_50ms': sum(1 for x in fr if x > 50), 'p90_frame_ms': round(sorted(fr)[int(len(fr) * .9)], 1) if fr else None}

with sync_playwright() as p:
    b = launch(p)
    for throttle in (1, 4):
        ctx = b.new_context(viewport={'width': 1920, 'height': 1080})
        ctx.add_init_script(INIT)
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)
        pg.goto(SNAP_URL)
        pg.evaluate("localStorage.setItem('khm.topN','500'); localStorage.setItem('khm.market','\"Q\"')")
        if throttle > 1: cdp.send('Emulation.setCPUThrottlingRate', {'rate': throttle})
        pg.reload(); pg.wait_for_timeout(2500)
        nav = pg.evaluate("(()=>{const n=performance.getEntriesByType('navigation')[0];return {dcl:Math.round(n.domContentLoadedEventEnd), load:Math.round(n.loadEventEnd)}})()")
        boot_lt = pg.evaluate("window.__lt")
        tiles = pg.evaluate("document.querySelectorAll('#map .tile').length")
        # time a full re-render: topN 500 -> 300 -> 500 (render with animation)
        r_zoom = measure(pg, lambda: pg.click('#map .sec[data-s="정보기술"] .hd'))
        r_out = measure(pg, lambda: pg.keyboard.press('Escape'))
        r_mkt = measure(pg, lambda: pg.click('.tabs button[data-mkt="K"]'))
        r_mkt2 = measure(pg, lambda: pg.click('.tabs button[data-mkt="ALL"]'))
        r_pal = measure(pg, lambda: pg.click('.seg[data-key="palette"] button[data-v="cvd"]'))
        r_size = measure(pg, lambda: pg.click('.seg[data-key="sizeBy"] button[data-v="tv"]'))
        # hover cost: move mouse across 40 tiles
        def hover():
            for i in range(40): pg.mouse.move(100 + i * 30, 400 + (i % 5) * 20)
        r_hover = measure(pg, hover, 300)
        print(f'--- CPU throttle x{throttle}: tiles={tiles} nav={nav} boot longtasks={boot_lt}')
        for k, v in [('sector zoom', r_zoom), ('zoom out', r_out), ('market Q->K', r_mkt), ('market K->ALL', r_mkt2), ('palette', r_pal), ('sizeBy tv', r_size), ('hover 40 moves', r_hover)]:
            print(f'  {k:<15} {dump(v)}')
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 1})
        pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k)")
        ctx.close()
    b.close()
