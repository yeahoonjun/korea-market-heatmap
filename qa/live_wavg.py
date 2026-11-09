import sys, json, urllib.request; sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *
def gc(l):
    a = b = 0
    for s in l:
        if s['cap']: a += s['cap']; b += s['cap'] / (1 + s['r'] / 100)
    return (a / b - 1) * 100
with sync_playwright() as p:
    br = launch(p)
    ctx, pg, log = new_page(br, 'd1280', LIVE_URL, storage_clear=True, wait=0)
    payload = []
    pg.on('response', lambda r: payload.append(r) if r.url.endswith('api/quotes') else None)
    pg.reload(); pg.wait_for_timeout(4000)
    q = json.loads(payload[-1].body())
    out = {}
    for m in ('Q', 'K'):
        pg.click(f'.tabs button[data-mkt="{m}"]'); pg.wait_for_timeout(700)
        l = sorted([s for s in q['stocks'] if s['m'] == m and s['c'][-1] == '0' and s['cap'] > 0], key=lambda s: -s['cap'])[:300]
        secs = {}
        for s in l: secs.setdefault(s['s'], []).append(s)
        page_secs = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#map .sec:not(.leaving)')].map(e=>[e.dataset.s, e.querySelector('.hd .v').textContent]))")
        print(m, 'page wavg', pg.inner_text('#wavg'), 'stat', pg.inner_text('#crumbs .stat'), '| computed from same payload', f'{gc(l):+.2f}%')
        print('   sector headers page vs computed:', {k: (page_secs.get(k), f'{gc(v):+.1f}%') for k, v in list(secs.items())[:5]})
    ctx.close(); br.close()
