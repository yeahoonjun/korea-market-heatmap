#!/usr/bin/env python3
"""Fetch raw Naver responses once for the stock-page mock server (qa/stock/mock_api.py).

    python3 qa/stock/fetch_fixtures.py 005930 196170
    python3 qa/stock/fetch_fixtures.py --only news,disclosure 005930 196170     # refresh some files only
    DART_KEY=… python3 qa/stock/fetch_fixtures.py --only dart 005930 196170       # OpenDART list (key from the environment only)

Saves qa/stock/fixtures/raw/<code>/<name>.json. The mock server turns these into the AGENTS.md §3 shapes.
"""
import datetime as dt, json, os, pathlib, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent / 'fixtures' / 'raw'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
KST = dt.timezone(dt.timedelta(hours=9))


def get(url):
    req = urllib.request.Request(url, headers={'user-agent': UA, 'accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def main(codes, only=None):
    now = dt.datetime.now(KST)
    today = now.strftime('%Y%m%d')
    d = lambda days: (now - dt.timedelta(days=days)).strftime('%Y%m%d')
    ch = 'https://api.stock.naver.com/chart/domestic/item/{c}/'
    for c in codes:
        out = ROOT / c
        out.mkdir(parents=True, exist_ok=True)
        urls = {
            'integration': f'https://m.stock.naver.com/api/stock/{c}/integration',
            'basic': f'https://m.stock.naver.com/api/stock/{c}/basic',
            'polling': f'https://polling.finance.naver.com/api/realtime/domestic/stock/{c}',
            'askingPrice': f'https://m.stock.naver.com/api/stock/{c}/askingPrice',
            'trend': f'https://m.stock.naver.com/api/stock/{c}/trend?pageSize=60',
            'price_1': f'https://m.stock.naver.com/api/stock/{c}/price?pageSize=60&page=1',
            'price_2': f'https://m.stock.naver.com/api/stock/{c}/price?pageSize=60&page=2',
            'price_3': f'https://m.stock.naver.com/api/stock/{c}/price?pageSize=60&page=3',
            'minute': ch.format(c=c) + 'minute',
            'minute5': ch.format(c=c) + f'minute5?startDateTime={d(9)}000000&endDateTime={today}235959',
            'day_3m': ch.format(c=c) + f'day?startDateTime={d(95)}000000&endDateTime={today}235959',
            'day_1y': ch.format(c=c) + f'day?startDateTime={d(366)}000000&endDateTime={today}235959',
            'week_3y': ch.format(c=c) + f'week?startDateTime={d(3 * 366)}000000&endDateTime={today}235959',
            'month_10y': ch.format(c=c) + f'month?startDateTime={d(10 * 366)}000000&endDateTime={today}235959',
            'news': f'https://m.stock.naver.com/api/news/stock/{c}?pageSize=20',          # ENDPOINTS_EXTRA.md §2
            'disclosure': f'https://m.stock.naver.com/api/stock/{c}/disclosure?pageSize=20',   # ENDPOINTS_EXTRA.md §3
        }
        key = os.environ.get('DART_KEY')   # never written anywhere; the saved response carries no key
        corp = json.loads((ROOT.parent.parent.parent.parent / 'web/dart_corp.json').read_text(encoding='utf-8'))['map'].get(c)
        if key and corp:
            urls['dart'] = ('https://opendart.fss.or.kr/api/list.json?' + urllib.parse.urlencode(
                {'crtfc_key': key, 'corp_code': corp, 'bgn_de': (now - dt.timedelta(days=183)).strftime('%Y%m%d'),
                 'page_count': 40, 'sort': 'date', 'sort_mth': 'desc'}))
        for name, url in urls.items():
            if only and name not in only:
                continue
            try:
                j = get(url)
                (out / f'{name}.json').write_text(json.dumps(j, ensure_ascii=False), encoding='utf-8')
                n = len(j) if isinstance(j, list) else len(j.get('datas', j)) if isinstance(j, dict) else '?'
                print(c, name, 'ok', n)
            except Exception as e:
                print(c, name, 'FAIL', type(e).__name__)   # no URL in the message (it may hold the DART key)
            time.sleep(0.15)
    if not only:
        (ROOT / 'fetched_at.txt').write_text(now.isoformat(), encoding='utf-8')


if __name__ == '__main__':
    args = sys.argv[1:]
    only = None
    if '--only' in args:
        i = args.index('--only')
        only = set(args[i + 1].split(','))
        del args[i:i + 2]
    main(args or ['005930', '196170'], only)
