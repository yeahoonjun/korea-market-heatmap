import json, urllib.request, gzip, time
def get(url, proxy=True):
    h = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}
    op = urllib.request.build_opener() if proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = op.open(urllib.request.Request(url, headers=h), timeout=30); b = r.read()
    if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
    return json.loads(b)
codes = ['005930', '000660', '247540', '196170', '035420', '086520', '012450']
for rnd in range(2):
    t0 = time.time()
    q = get('http://127.0.0.1:8788/api/quotes', proxy=False)
    t1 = time.time()
    pl = {d['itemCode']: d for d in get('https://polling.finance.naver.com/api/realtime/domestic/stock/' + ','.join(codes))['datas']}
    t2 = time.time()
    print(f'round {rnd}: quotes asOf={q["asOf"]} afterHours={q["afterHours"]} status={q["marketStatus"]} n={len(q["stocks"])} fetched {t1-t0:.1f}s, naver {t2-t1:.1f}s')
    by = {s['c']: s for s in q['stocks']}
    for c in codes:
        s = by.get(c); d = pl.get(c)
        if not s: print('  ', c, 'missing in /api/quotes'); continue
        exp = dict(p=float(d['closePriceRaw']), d=float(d['compareToPreviousClosePriceRaw']), r=float(d['fluctuationsRatioRaw']),
                   cap=round(float(d['marketValueFullRaw'])/1e8), tv=round(float(d['accumulatedTradingValueRaw'])/1e8), v=float(d['accumulatedTradingVolumeRaw']))
        diffs = {k: (s[k], exp[k]) for k in exp if abs(s[k] - exp[k]) > (0.006 if k == 'r' else 0.5)}
        print(f"   {c} {s['n'][:8]:<8} p={s['p']} d={s['d']} r={s['r']} cap={s['cap']} tv={s['tv']} v={s['v']} | naver t={d['localTradedAt'][11:19]} sess={d.get('marketSessionType')} {'MATCH' if not diffs else 'DIFF '+json.dumps(diffs)}")
    # consistency checks over whole quotes payload
    bad = [s for s in q['stocks'] if s['p'] - s['d'] and abs(s['d']/(s['p']-s['d'])*100 - s['r']) > 0.0051]
    print('  r != d/(p-d) rows:', len(bad), [ (s['c'], s['p'], s['d'], s['r']) for s in bad[:5]])
    zero = [s for s in q['stocks'] if not s['p'] or not s['cap']]
    print('  zero p/cap rows:', len(zero), [(s['c'], s['n']) for s in zero[:5]])
    from collections import Counter
    print('  markets:', Counter(s['m'] for s in q['stocks']), 'pref:', sum(1 for s in q['stocks'] if s['c'][-1] != '0'))
    if rnd == 0: time.sleep(9)
# live cap-weighted
def gc(l):
    a = b = 0
    for s in l:
        if s['cap']: a += s['cap']; b += s['cap']/(1+s['r']/100)
    return (a/b-1)*100
for m in 'KQ':
    l = sorted([s for s in q['stocks'] if s['m']==m and s['c'][-1]=='0' and s['cap']>0], key=lambda s:-s['cap'])[:300]
    print(f'live {m} top300 gc = {gc(l):+.3f}% (n={len(l)})')
# snapshot vs live cap ratio for shares sanity
snap = {s['c']: s for s in json.load(open('/home/claude/heatmap/qa/snapshot_in_dist.json'))['stocks']}
for c in ['005930','000660','247540','196170']:
    a = snap[c]; b = by[c]
    print(f'  {c} snap cap/p={a["cap"]*1e8/a["p"]:.0f} live cap/p={b["cap"]*1e8/b["p"]:.0f} snap tv={a["tv"]} live tv={b["tv"]}')
