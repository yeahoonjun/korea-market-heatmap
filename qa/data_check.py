import json, random, urllib.request, time, gzip, sys
sys.path.insert(0, '/home/claude/heatmap/qa')
SNAP = json.load(open('/home/claude/heatmap/qa/snapshot_in_dist.json'))
S = SNAP['stocks']
UA = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}
def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    b = r.read()
    if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
    return json.loads(b)

def gc(lst):
    now = before = 0
    for s in lst:
        if not s['cap']: continue
        now += s['cap']; before += s['cap'] / (1 + s['r'] / 100)
    return (now / before - 1) * 100 if before else 0

def uni(m, n, key='cap', stocks=S):
    l = [s for s in stocks if (m == 'ALL' or s['m'] == m) and s[key] > 0 and s['c'][-1] == '0']
    l.sort(key=lambda s: -s[key])
    return l[:n]

print('== (b) cap-weighted change, snapshot ==')
for m in ('K', 'Q', 'ALL'):
    for n in (100, 200, 300, 500):
        u = uni(m, n)
        print(f'  {m} top{n}: {gc(u):+.4f}%  n={len(u)} cap={sum(s["cap"] for s in u)/1e4:.1f}조')
# tv sizing
for m in ('K','Q'):
    print(f'  {m} top300 by tv: {gc(uni(m,300,"tv")):+.4f}%')

print('== (c) sector headers, KOSDAQ top300 ==')
from collections import defaultdict
u = uni('Q', 300)
secs = defaultdict(list); inds = defaultdict(list)
for s in u: secs[s['s']].append(s); inds[(s['s'], s['i'])].append(s)
for k, v in sorted(secs.items(), key=lambda kv: -sum(s['cap'] for s in kv[1])):
    print(f'  {k}: {gc(v):+.3f}% n={len(v)}')
print('  반도체와반도체장비 (Q300):', f"{gc(inds[('정보기술','반도체와반도체장비')]):+.3f}%", len(inds[('정보기술','반도체와반도체장비')]))
uk = uni('K', 300); secsK = defaultdict(list)
for s in uk: secsK[s['s']].append(s)
print('  KOSPI300 sectors:', {k: round(gc(v), 3) for k, v in secsK.items()})

print('== (a) 10 random stocks vs Naver 15:30 bar ==')
random.seed(7)
K = [s for s in S if s['m'] == 'K']; Q = [s for s in S if s['m'] == 'Q']
pick = random.sample(K, 4) + random.sample(Q, 4) + [x for x in S if x['c'] in ('005930', '247540')]
codes = [s['c'] for s in pick]
poll = {d['itemCode']: d for d in get('https://polling.finance.naver.com/api/realtime/domestic/stock/' + ','.join(codes))['datas']}
rows = []
for s in pick:
    try:
        bars = get(f'https://api.stock.naver.com/chart/domestic/item/{s["c"]}/minute')
    except Exception as e:
        print('  ', s['c'], 'chart error', e); continue
    if isinstance(bars, dict): bars = bars.get('priceInfos', [])
    day = str(bars[-1]['localDateTime'])[:8] if bars else None
    reg = [b for b in bars if str(b['localDateTime']).startswith(day) and str(b['localDateTime'])[8:12] <= '1530']
    last = reg[-1] if reg else None
    pl = poll.get(s['c'])
    base = float(pl['closePriceRaw']) - float(pl['compareToPreviousClosePriceRaw']) if pl else None
    p = last['currentPrice'] if last else None
    d = p - base if (p and base) else None
    r = d / base * 100 if d is not None else None
    ok = p == s['p'] and d == s['d'] and abs(r - s['r']) < 0.0051
    rr = s['d'] / (s['p'] - s['d']) * 100
    print(f"  {s['c']} {s['n'][:10]:<10} {s['m']} snap p={s['p']} d={s['d']} r={s['r']} | naver 15:30bar={p} ({str(last['localDateTime'])[8:12] if last else '-'}) base={base} d={d} r={r and round(r,2)} | d/(p-d)={rr:.3f} {'OK' if ok else 'MISMATCH'}")
