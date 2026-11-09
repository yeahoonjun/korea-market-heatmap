#!/usr/bin/env python3
"""Mock of the Worker API for the stock page (AGENTS.md §3 shapes), built from real Naver responses.
Shapes and semantics were compared with the live Worker (korea-market-heatmap.ssslot.workers.dev) on 2026-11-09:
chart.prevClose = close before the first bar, interval '1m|5m|1d|1w|1mo', orderbook.asOf in UTC, 404 {error} for unknown codes.

    python3 qa/stock/mock_api.py            # http://127.0.0.1:8792/  (serves web/ + /api/...)

Fixtures: qa/stock/fixtures/raw/<code>/*.json (fetch with qa/stock/fetch_fixtures.py).
Codes
  005930, 196170   real data
  other codes in data/snapshot.json   005930's data scaled to that stock's price (so peer links work); no news
  999980           summary only; chart/orderbook/investors/daily/news/disclosures come back empty
  999990           every endpoint answers 502 {error}
  anything else    404 {error}
Control (test helpers, not part of the contract)
  /__stats                       request counts per route  {"orderbook": 3, ...} and per full path
  /__reset                       clear counts and config
  /__config?delay=800&fail=chart,orderbook&status=OPEN&asof=2026-11-09T10:30:00%2B09:00&dsrc=naver
"""
import datetime as dt, html, json, pathlib, random, re, sys, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = HERE / 'fixtures' / 'raw'
WEB = ROOT / 'web'
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8792
KST = dt.timezone(dt.timedelta(hours=9))

LOCK = threading.Lock()
STATS = {}
CONFIG = {}


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = re.sub(r'[^0-9.+\-]', '', str(v))
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def raw(code, name):
    p = RAW / code / f'{name}.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def ymd(s):
    s = str(s)
    return f'{s[0:4]}-{s[4:6]}-{s[6:8]}'


# ── transforms: Naver → AGENTS.md §3 ───────────────────────────────
def summary(code):
    integ, basic, poll = raw(code, 'integration'), raw(code, 'basic'), raw(code, 'polling')
    info = {t['code']: t['value'] for t in integ['totalInfos']}
    p = poll['datas'][0]
    ex = (basic.get('stockExchangeType') or {}).get('code')
    out = {
        'code': code, 'name': integ['stockName'], 'market': 'K' if ex == 'KS' else 'Q',
        'price': num(p['closePriceRaw']), 'change': num(p['compareToPreviousClosePriceRaw']), 'ratio': num(p['fluctuationsRatioRaw']),
        'marketStatus': 'CLOSE',
        'per': num(info.get('per')), 'eps': num(info.get('eps')), 'pbr': num(info.get('pbr')), 'bps': num(info.get('bps')),
        'dividendYield': num(info.get('dividendYieldRatio')),
        'high52': num(info.get('highPriceOf52Weeks')), 'low52': num(info.get('lowPriceOf52Weeks')),
        'marketCap': round(num(p['marketValueFullRaw']) / 1e8), 'foreignRate': num(info.get('foreignRate')),
        'asOf': p['localTradedAt'][:19] + '+09:00',
    }
    if CONFIG.get('status'):
        out['marketStatus'] = CONFIG['status']
    if CONFIG.get('asof'):
        out['asOf'] = CONFIG['asof']
    return out


def minute_bars(rows):
    bars = []
    for r in rows:
        s = r['localDateTime']
        t = dt.datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), tzinfo=KST)
        bars.append({'t': int(t.timestamp()), 'o': num(r['openPrice']), 'h': num(r['highPrice']), 'l': num(r['lowPrice']),
                     'c': num(r['currentPrice']), 'v': num(r['accumulatedTradingVolume'])})
    return bars


def period_bars(rows):
    return [{'t': ymd(r['localDate']), 'o': num(r['openPrice']), 'h': num(r['highPrice']), 'l': num(r['lowPrice']),
             'c': num(r['closePrice']), 'v': num(r['accumulatedTradingVolume'])} for r in rows]


def close_before(code, ymd8):
    """Close of the last day bar before YYYYMMDD (integrated KRX+NXT close, like the real Worker)."""
    for name in ('day_3m', 'day_1y'):
        prior = [r for r in raw(code, name) if r['localDate'] < ymd8]
        if prior:
            return num(prior[-1]['closePrice'])
    return None


def chart(code, tf):
    # Same as the real Worker (checked with curl on 2026-11-09): prevClose is the close of the bar *before the
    # first bar shown* — for 1d that is the previous day's integrated close, not the KRX 기준가 the summary uses.
    if tf == '1d':
        rows = raw(code, 'minute')
        return {'tf': tf, 'interval': '1m', 'prevClose': close_before(code, rows[0]['localDateTime'][:8]), 'bars': minute_bars(rows)}
    if tf == '5d':
        rows = raw(code, 'minute5')
        days = sorted({r['localDateTime'][:8] for r in rows})[-5:]
        return {'tf': tf, 'interval': '5m', 'prevClose': close_before(code, days[0]),
                'bars': minute_bars([r for r in rows if r['localDateTime'][:8] in days])}
    if tf == '3m':
        rows = raw(code, 'day_3m')
        return {'tf': tf, 'interval': '1d', 'prevClose': close_before(code, rows[0]['localDate']), 'bars': period_bars(rows)}
    name, interval = {'1y': ('day_1y', '1d'), '3y': ('week_3y', '1w'), '10y': ('month_10y', '1mo')}[tf]
    rows = raw(code, name)
    return {'tf': tf, 'interval': interval, 'prevClose': num(rows[0]['closePrice']), 'bars': period_bars(rows[1:])}


def orderbook(code):
    j = raw(code, 'askingPrice')
    jit = lambda q: max(1, int(q * random.uniform(0.85, 1.15)))   # make each poll visibly different
    asks = [{'price': num(x['price']), 'qty': jit(num(x['count']))} for x in reversed(j['sellInfo'])]   # best (lowest) ask first
    bids = [{'price': num(x['price']), 'qty': jit(num(x['count']))} for x in j['buyInfos']]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')   # real Worker: UTC with ms
    return {'asks': asks, 'bids': bids, 'totalAsk': jit(num(j['totalSell'])), 'totalBid': jit(num(j['totalBuy'])),
            'prevClose': num(j['lastClosePrice']), 'asOf': now}


def investors(code):
    rows = []
    for r in raw(code, 'trend'):
        close, chg = num(r['closePrice']), num(r['compareToPreviousClosePrice'])
        base = close - chg
        rows.append({'date': ymd(r['bizdate']), 'close': close, 'ratio': round(chg / base * 100, 2) if base else 0,
                     'individual': num(r['individualPureBuyQuant']), 'foreign': num(r['foreignerPureBuyQuant']),
                     'institution': num(r['organPureBuyQuant']), 'foreignHoldRatio': num(r['foreignerHoldRatio'])})
    return {'rows': rows}


def daily(code, page):
    j = raw(code, f'price_{page}') or []
    rows = [{'date': r['localTradedAt'], 'close': num(r['closePrice']), 'change': num(r['compareToPreviousClosePrice']),
             'ratio': num(r['fluctuationsRatio']), 'open': num(r['openPrice']), 'high': num(r['highPrice']),
             'low': num(r['lowPrice']), 'volume': num(r['accumulatedTradingVolume'])} for r in j]
    return {'page': page, 'rows': rows, 'hasMore': raw(code, f'price_{page + 1}') is not None}


def news(code):
    # ENDPOINTS_EXTRA.md §2: clusters of 1 article; datetime YYYYMMDDHHmm KST; titles carry HTML entities (decoded here, as the Worker does)
    rows = []
    for cl in raw(code, 'news') or []:
        for a in cl.get('items', []):
            t = a['datetime']
            rows.append({'title': html.unescape(a.get('titleFull') or a['title']), 'press': a.get('officeName'),
                         'datetime': f'{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[8:10]}:{t[10:12]}:00+09:00', 'url': a.get('mobileNewsUrl')})
    return {'rows': rows[:20]}


def dart_kind(name):
    # same rules as the Worker's dartKind (worker/src/index.js)
    n = str(name or '')
    if re.search(r'사업보고서|반기보고서|분기보고서', n): return '정기'
    if re.search(r'실적|손익구조|매출액', n): return '실적'
    if re.search(r'소유상황보고서|대량보유|최대주주등소유주식|특정증권등', n): return '지분'
    if re.search(r'주요사항|단일판매|공급계약|유상증자|무상증자|감자|자기주식|합병|분할|전환사채|신주인수권|교환사채|배당|최대주주변경|소송|영업정지|타법인주식|유형자산|투자판단|조회공시|상장', n): return '주요'
    return '기타'


def disclosures(code):
    # AGENTS.md §3-2: OpenDART when the Worker has a key and a corp_code (date only, kind, filer, note), else Naver.
    # /__config?dsrc=naver forces the Naver path. Naver datetimes stay zone-less (KST) so the page's parsing is exercised.
    dart = raw(code, 'dart')
    if dart and CONFIG.get('dsrc') != 'naver':
        rows = [{'title': re.sub(r'\s+', ' ', x['report_nm']).strip(), 'kind': dart_kind(x['report_nm']), 'datetime': None,
                 'date': f"{x['rcept_dt'][0:4]}-{x['rcept_dt'][4:6]}-{x['rcept_dt'][6:8]}", 'filer': x.get('flr_nm') or None,
                 'note': x.get('rm') or '', 'url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x['rcept_no']}"} for x in dart.get('list', [])]
        return {'source': 'dart', 'rows': rows}
    return {'source': 'naver', 'rows': [{'title': html.unescape(d['title']), 'datetime': d['datetime'],
                                         'url': f'https://m.stock.naver.com/domestic/stock/{code}/notice/{d["disclosureId"]}'} for d in (raw(code, 'disclosure') or [])[:20]]}


def quotes():
    snap = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
    out = []
    for m in ('K', 'Q'):
        rows = sorted((x for x in snap['stocks'] if x.get('m') == m and x['c'].endswith('0')), key=lambda x: -x.get('cap', 0))[:300]
        out += rows
    out = [dict(r, lim=1 if r.get('r', 0) >= 29.5 else -1) if abs(r.get('r', 0)) >= 29.5 else r for r in out]   # Worker: lim only when at the limit
    return {'asOf': dt.datetime.now(KST).replace(microsecond=0).isoformat(), 'source': '네이버 증권 (mock)',
            'marketStatus': snap['marketStatus'], 'afterHours': True, 'index': snap['index'], 'stocks': out}


EMPTY = {
    'summary': lambda: {'code': '999980', 'name': '데이터없음', 'market': 'Q', 'price': 1000, 'change': 0, 'ratio': 0.0,
                        'marketStatus': 'CLOSE', 'per': None, 'eps': None, 'pbr': None, 'bps': None, 'dividendYield': None,
                        'high52': None, 'low52': None, 'marketCap': 120, 'foreignRate': None, 'asOf': '2026-11-09T15:30:00+09:00'},
    'chart': lambda tf: {'tf': tf, 'interval': 'day', 'prevClose': 1000, 'bars': []},
    'orderbook': lambda: {'asks': [], 'bids': [], 'totalAsk': 0, 'totalBid': 0, 'prevClose': 1000, 'asOf': None},
    'investors': lambda: {'rows': []},
    'daily': lambda page: {'page': page, 'rows': [], 'hasMore': False},
    'news': lambda: {'rows': []},
    'disclosures': lambda: {'source': 'dart', 'rows': []},
}

SNAP_ROWS = {r['c']: r for r in json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))['stocks']}
PRICE_KEYS = {'o', 'h', 'l', 'c', 'price', 'close', 'change', 'open', 'high', 'low', 'prevClose'}


def scaled(body, f):
    """Multiply every price-like field by f (whole won)."""
    if isinstance(body, list):
        return [scaled(x, f) for x in body]
    if isinstance(body, dict):
        return {k: (round(v * f) if k in PRICE_KEYS and isinstance(v, (int, float)) else scaled(v, f)) for k, v in body.items()}
    return body


def alias_summary(code):
    r = SNAP_ROWS[code]
    return {'code': code, 'name': r['n'], 'market': r['m'], 'price': r['p'], 'change': r['d'], 'ratio': r['r'], 'marketStatus': CONFIG.get('status', 'CLOSE'),
            'per': None, 'eps': None, 'pbr': None, 'bps': None, 'dividendYield': None, 'high52': None, 'low52': None,
            'marketCap': r['cap'], 'foreignRate': None, 'asOf': CONFIG.get('asof', '2026-11-09T15:30:00+09:00')}


ROUTE = re.compile(r'^/api/stock/([0-9A-Z]{6})/(summary|chart|orderbook|investors|daily|news|disclosures)$')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, body, status=200):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('access-control-allow-origin', '*')
        self.send_header('cache-control', 'no-store')
        self.send_header('content-length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def count(self, key):
        with LOCK:
            STATS[key] = STATS.get(key, 0) + 1

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        path = u.path
        if path == '/__stats':
            with LOCK:
                return self.send_json(dict(STATS))
        if path == '/__reset':
            with LOCK:
                STATS.clear(); CONFIG.clear()
            return self.send_json({'ok': True})
        if path == '/__config':
            with LOCK:
                for k, v in q.items():
                    if v == '':
                        CONFIG.pop(k, None)
                    else:
                        CONFIG[k] = v
            return self.send_json(dict(CONFIG))
        if re.match(r'^/data/(themes|periods|flows)\.json$', path):   # Worker serves web/*.json here
            self.path = path[len('/data'):]
            return super().do_GET()
        if path.startswith('/api/'):
            delay = int(CONFIG.get('delay', 0) or 0)
            if delay:
                time.sleep(delay / 1000)
            return self.api(path, q)
        return super().do_GET()

    def api(self, path, q):
        if path == '/api/quotes':
            self.count('quotes')
            return self.send_json(quotes())
        # the heatmap's own routes (AGENTS.md §3-2), just enough for a clean console; not what these tests check
        if path == '/api/market':
            idx = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8')).get('index', {})
            items = [{'key': k, 'name': {'KOSPI': '코스피', 'KOSDAQ': '코스닥'}[k], 'value': v['value'], 'change': v['change'], 'ratio': v['ratio']}
                     for k, v in idx.items() if k in ('KOSPI', 'KOSDAQ')]
            return self.send_json({'asOf': dt.datetime.now(KST).replace(microsecond=0).isoformat(), 'items': items})
        if path == '/api/themes':
            return self.send_json({'asOf': dt.datetime.now(KST).replace(microsecond=0).isoformat(), 'themes': []})
        if path == '/api/replay/dates':
            return self.send_json({'dates': []})
        m = ROUTE.match(path)
        if not m:
            return self.send_json({'error': 'not found'}, 404)
        code, kind = m.groups()
        self.count(kind)
        self.count(f'{kind}:{code}')
        if kind in (CONFIG.get('fail') or '').split(','):
            return self.send_json({'error': f'naver 503 (mock fail {kind})'}, 502)
        if code == '999990':
            return self.send_json({'error': 'naver 500 (mock)'}, 502)
        tf = q.get('tf', '1d')
        page = int(q.get('page', '1') or 1)
        if kind == 'chart' and tf not in ('1d', '5d', '3m', '1y', '3y', '10y'):
            return self.send_json({'error': 'bad tf'}, 400)
        if code == '999980':
            f = EMPTY[kind]
            return self.send_json(f(tf) if kind == 'chart' else f(page) if kind == 'daily' else f())
        if not (RAW / code).exists():
            if code not in SNAP_ROWS:
                return self.send_json({'error': f'unknown code {code}'}, 404)
            base = summary('005930')['price'] or 1
            f = (SNAP_ROWS[code]['p'] or base) / base
            fn = {'summary': lambda: alias_summary(code), 'chart': lambda: scaled(chart('005930', tf), f), 'orderbook': lambda: scaled(orderbook('005930'), f),
                  'investors': lambda: scaled(investors('005930'), f), 'daily': lambda: scaled(daily('005930', page), f),
                  'news': lambda: {'rows': []}, 'disclosures': lambda: {'source': 'naver', 'rows': []}}[kind]
            return self.send_json(fn())
        try:
            body = {'summary': lambda: summary(code), 'chart': lambda: chart(code, tf), 'orderbook': lambda: orderbook(code),
                    'investors': lambda: investors(code), 'daily': lambda: daily(code, page),
                    'news': lambda: news(code), 'disclosures': lambda: disclosures(code)}[kind]()
        except Exception as e:   # noqa: BLE001
            return self.send_json({'error': repr(e)}, 500)
        return self.send_json(body)


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'mock api on http://127.0.0.1:{PORT}/', flush=True)
    srv.serve_forever()
