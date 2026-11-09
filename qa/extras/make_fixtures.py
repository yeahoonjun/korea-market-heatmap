#!/usr/bin/env python3
"""Build test fixtures for the extras module (market strip + replay).

  qa/extras/fixtures/market.json   /api/market built from real Naver data (data/ENDPOINTS_EXTRA.md §4)
  qa/extras/fixtures/replay.json   /api/replay days synthesized from data/snapshot.json (79 frames, 09:00-15:30)

Run: python3 qa/extras/make_fixtures.py        (needs network for the market fixture; replay is offline)
"""
import datetime as dt
import gzip
import json
import pathlib
import random
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent / 'fixtures'
OUT.mkdir(exist_ok=True)
KST = dt.timezone(dt.timedelta(hours=9))


def get(url):
    req = urllib.request.Request(url, headers={'user-agent': 'Mozilla/5.0', 'accept-encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        if r.headers.get('content-encoding') == 'gzip':
            body = gzip.decompress(body)
    return json.loads(body)


def num(s):
    if s is None:
        return None
    return float(str(s).replace(',', ''))


def kst_sec(ymdhms):
    d = dt.datetime.strptime(ymdhms[:12], '%Y%m%d%H%M').replace(tzinfo=KST)
    return int(d.timestamp())


def market():
    items = {}
    idx = get('https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ')
    for x in idx['datas']:
        bars = get(f"https://api.stock.naver.com/chart/domestic/index/{x['itemCode']}/minute5")
        day = bars[-1]['localDateTime'][:8]
        spark = [[kst_sec(b['localDateTime']), b['currentPrice']] for b in bars
                 if b['localDateTime'].startswith(day) and b['localDateTime'][8:12] <= '1530']
        items[x['itemCode']] = dict(key=x['itemCode'], name=x['stockName'], value=num(x['closePriceRaw']),
                                    change=num(x['compareToPreviousClosePriceRaw']), ratio=num(x['fluctuationsRatioRaw']), spark=spark)
    fx = get('https://api.stock.naver.com/marketindex/exchange/FX_USDKRW')['exchangeInfo']
    items['USDKRW'] = dict(key='USDKRW', name='원/달러', value=num(fx['closePrice']), change=num(fx['fluctuations']), ratio=num(fx['fluctuationsRatio']))
    fut = get('https://polling.finance.naver.com/api/realtime/worldstock/futures/EScv1,NQcv1')
    names = {'EScv1': ('SPX_F', 'S&P 500 선물'), 'NQcv1': ('NDX_F', '나스닥 100 선물')}
    for x in fut['datas']:
        k, n = names[x['reutersCode']]
        items[k] = dict(key=k, name=n, value=num(x['closePriceRaw']), change=num(x['compareToPreviousClosePriceRaw']),
                        ratio=num(x['fluctuationsRatioRaw']), delayed=10)
    en = get('https://polling.finance.naver.com/api/realtime/marketindex/energy/CLcv1')['datas'][0]
    items['WTI'] = dict(key='WTI', name='WTI', value=num(en['closePrice']), change=num(en['fluctuations']), ratio=num(en['fluctuationsRatio']))
    me = get('https://polling.finance.naver.com/api/realtime/marketindex/metals/GCcv1')['datas'][0]
    items['GOLD'] = dict(key='GOLD', name='국제 금', value=num(me['closePrice']), change=num(me['fluctuations']), ratio=num(me['fluctuationsRatio']))
    btc = get('https://m.stock.naver.com/front-api/cryptoEnd/detail?nfTicker=BTC&exchangeType=UPBIT')['result']
    items['BTC'] = dict(key='BTC', name='비트코인', value=num(btc['currentPrice']), change=num(btc['fluctuations']), ratio=num(btc['fluctuationsRatio']))
    order = ['KOSPI', 'KOSDAQ', 'USDKRW', 'SPX_F', 'NDX_F', 'WTI', 'GOLD', 'BTC']
    out = {'asOf': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'), 'items': [items[k] for k in order if k in items]}
    (OUT / 'market.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('market.json', len(out['items']), 'items', file=sys.stderr)


def bridge(rng, n, start, end, vol):
    """Brownian bridge from start to end over n points."""
    w = [0.0]
    for _ in range(n - 1):
        w.append(w[-1] + rng.gauss(0, vol))
    return [start + (end - start) * i / (n - 1) + (w[i] - w[-1] * i / (n - 1)) for i in range(n)]


def replay():
    snap = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
    codes = []
    for m in ('K', 'Q'):
        rows = sorted((x for x in snap['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x['cap'])[:300]
        codes += [x['c'] for x in rows]
    by = {x['c']: x for x in snap['stocks']}
    times = [f'{h:02d}{m:02d}' for h in range(9, 16) for m in range(0, 60, 5) if (h, m) <= (15, 30)]
    days = {}
    for di, date in enumerate(['2026-11-09', '2026-11-06', '2026-11-05']):
        rng = random.Random(7 + di)
        n = len(times)
        if di == 0:
            frames_n = n
        else:
            frames_n = n
        paths = {}
        for c in codes:
            s = by[c]
            end = s['r'] if di == 0 else max(-29.9, min(29.9, rng.gauss(0, 2.2)))
            paths[c] = bridge(rng, n, rng.gauss(0, 0.6), end, 0.35)
        frames = []
        for i, t in enumerate(times[:frames_n]):
            p, r = [], []
            for j, c in enumerate(codes):
                s = by[c]
                prev = s['p'] - s['d']
                rr = round(max(-29.99, min(29.99, paths[c][i])), 2)
                if di == 0 and i == n - 1:
                    rr = s['r']
                if j % 97 == 13 and i < 2:      # a few stocks without a quote in the first frames (null in the contract)
                    p.append(None); r.append(None); continue
                p.append(round(prev * (1 + rr / 100)))
                r.append(rr)
            frames.append({'t': t, 'p': p, 'r': r})
        ix = {}
        for k in ('KOSPI', 'KOSDAQ'):
            x = snap['index'][k]
            base = x['value'] - x['change']
            end = x['value'] if di == 0 else base * (1 + rng.gauss(0, 0.012))
            path = bridge(rng, n, base * (1 + rng.gauss(0, 0.003)), end, base * 0.0012)
            if di == 0:
                path[-1] = x['value']
            ix[k] = [round(v, 2) for v in path[:frames_n]]
        days[date] = {'date': date, 'codes': codes, 'frames': frames, 'index': ix}
    (OUT / 'replay.json').write_text(json.dumps(days, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('replay.json', {d: len(v['frames']) for d, v in days.items()}, file=sys.stderr)


if __name__ == '__main__':
    replay()
    if '--offline' not in sys.argv:
        market()
