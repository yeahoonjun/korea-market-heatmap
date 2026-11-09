"""Capture a real NXT session from Naver into test fixtures (run while NXT pre/after-market is open).
Writes fixtures/quotes_<tag>.json (the dev Worker's /api/quotes + nx per row + head nxt, as AGENTS §3-8 specifies) and
fixtures/breadth_<tag>_<m>_<part>.json (rows [code, r, lim|0, nxr]). usage: capture_nxt.py <tag>"""
import sys, json, os, urllib.request
TAG = sys.argv[1] if len(sys.argv) > 1 else 'pre'
HM = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/'}


def get(url, hdr=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {}), timeout=30) as r:
        return json.load(r)


def num(v):
    try: return float(str(v).replace(',', ''))
    except Exception: return None


def nx_of(d):
    o = d.get('overMarketPriceInfo') or {}
    p = num(o.get('overPrice'))
    stop = ((o.get('tradeStopType') or {}).get('name') or '')
    if not p or stop not in ('', 'TRADING'): return None
    sign = -1 if ((o.get('compareToPreviousPrice') or {}).get('name') or '') in ('FALLING', 'LOWER_LIMIT') else 1
    s = 'after' if o.get('tradingSessionType') == 'AFTER_MARKET' else 'pre'
    return {'p': p, 'd': sign * abs(num(o.get('compareToPreviousClosePrice')) or 0), 'r': sign * abs(num(o.get('fluctuationsRatio')) or 0),
            's': s, 'o': 1 if o.get('overMarketStatus') == 'OPEN' else 0, 't': o.get('localTradedAt')}


def naver(codes):
    out = {}
    for i in range(0, len(codes), 300):
        j = get('https://polling.finance.naver.com/api/realtime/domestic/stock/' + ','.join(codes[i:i + 300]), UA)
        for d in j.get('datas') or []: out[d['itemCode']] = d
    return out


q = get(HM + 'api/quotes')
nv = naver([s['c'] for s in q['stocks']])
n = 0
for s in q['stocks']:
    x = nx_of(nv.get(s['c'], {}))
    if x: s['nx'] = x; n += 1
sess = [s['nx']['s'] for s in q['stocks'] if 'nx' in s]
q['nxt'] = {'session': max(set(sess), key=sess.count) if sess else None, 'open': any(s['nx']['o'] for s in q['stocks'] if 'nx' in s)}
json.dump(q, open(f'{OUT}/quotes_{TAG}.json', 'w'), ensure_ascii=False)
print('quotes', len(q['stocks']), 'nx', n, q['nxt'], q['asOf'])
for m in ['K', 'Q']:
    b1 = get(HM + f'api/breadth?m={m}&part=1')
    for part in range(1, b1['parts'] + 1):
        b = b1 if part == 1 else get(HM + f'api/breadth?m={m}&part={part}')
        nv = naver([r[0] for r in b['rows']])
        k = 0
        for r in b['rows']:
            x = nx_of(nv.get(r[0], {}))
            if x:
                while len(r) < 3: r.append(0)
                r.append(x['r']); k += 1
        json.dump(b, open(f'{OUT}/breadth_{TAG}_{m}_{part}.json', 'w'), ensure_ascii=False)
        print('breadth', m, part, len(b['rows']), 'nxr', k)
