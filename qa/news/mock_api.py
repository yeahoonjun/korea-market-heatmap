#!/usr/bin/env python3
"""Mock Worker for the 시장 뉴스 panel: serves web/ plus /api/news (docs/standards/news.md §2-2) and quiet stubs for the other /api calls.

  python3 qa/news/mock_api.py [port=8851]

/api/news answers qa/news/fixtures/news.json (the real Worker's output over the sanitized 2026-11-13 feeds), its times shifted so the
newest item is 4 minutes old (the page reads "today" whenever the test runs).
/api/disclosures/today (공시 배지, AGENTS §3-2/§3-29) answers rows built from data/snapshot.json at request time (KST now): map stocks of
both markets + some outside the map, every kind, times relative to now (a few within 30 min after `since` = new, one at `since`, some
without `s`); fixed cases: 삼성전자 실적 new + 주요 at since + 지분 ×4 same title, POSCO홀딩스 주요 ×2 + 정기, SK하이닉스 지분 only,
NAVER [기재정정] (n), 현대차 filer (f).
Test controls (not part of the contract):
  /__mode?news=ok|partial|stale|fail|empty|slow|drift|morning|html404   partial: 연합인포맥스 failed with no copy (no tab);
        stale: 연합인포맥스 failed, its last copy rides along; fail: 502 {error, sources}; drift: every answer adds one new headline on top;
        morning: every item is from yesterday (M/D)
  /__mode?disc=ok|busy|holiday|empty|fail|slow|none|stale|etag|drift|nosince   busy: 1,260 rows (837 정기, like 11/13); holiday: the
        latest weekday's list (date ≠ today, no since); empty: today, no rows; fail: 503 {error}; none: 404 (a Worker without the
        route); stale: stale:true, asOf 20 min ago; etag: weak ETag + 304 on If-None-Match (x-as-of), cache-control no-cache;
        drift: every answer adds one new 주요 row (s = now) on top; nosince: today without `since` (no dot at all)
  /__stats   request counts per route        /__reset   counts + modes back to default
"""
import json
import pathlib
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEB = pathlib.Path(__import__('os').environ['MOCK_WEB']) if __import__('os').environ.get('MOCK_WEB') else ROOT / 'web'   # MOCK_WEB: another build's web/ (a baseline)
NEWS = json.loads((HERE / 'fixtures/news.json').read_text(encoding='utf-8'))
MARKET_P = ROOT / 'qa/extras/fixtures/market.json'
MARKET = json.loads(MARKET_P.read_text(encoding='utf-8')) if MARKET_P.exists() else {'asOf': None, 'items': []}
SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
QUOTES = {k: v for k, v in SNAP.items() if k != 'stocks'}
QUOTES['afterHours'] = False
rows = []
for m in ('K', 'Q'):
    rows += sorted((x for x in SNAP['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x['cap'])[:300]
QUOTES['stocks'] = rows
QUOTES_ALL = dict(QUOTES, stocks=[x for x in SNAP['stocks']])      # /api/quotes?scope=all (종목 수 전체)

KST = timezone(timedelta(hours=9))
DEFAULT = {'news': 'ok', 'disc': 'ok'}
MODE = dict(DEFAULT)
STATS = {}
LOCK = threading.Lock()
DRIFT = {'n': 0}


def iso(dt):
    return dt.astimezone(KST).strftime('%Y-%m-%dT%H:%M:%S+09:00')


def news_body(mode):
    d = json.loads(json.dumps(NEWS))
    now = datetime.now(KST)
    newest = max(datetime.fromisoformat(x['t']) for x in d['items'])
    shift = (now - timedelta(minutes=4)) - newest
    if mode == 'morning':
        shift -= timedelta(days=1)
    for x in d['items']:
        x['t'] = iso(datetime.fromisoformat(x['t']) + shift)
    d['asOf'] = iso(now)
    for s in d['sources'].values():
        s['at'] = iso(now)
    if mode == 'partial':
        d['items'] = [x for x in d['items'] if x['src'] != 'einfomax']
        d['sources']['einfomax'] = {'ok': False, 'n': 0, 'at': None, 'error': 'http 403'}
    if mode == 'stale':
        d['sources']['einfomax'] = {'ok': False, 'n': d['sources']['einfomax']['n'], 'at': iso(now - timedelta(minutes=42)), 'error': 'timeout', 'stale': True}
    if mode == 'empty':
        d['items'] = []
        for s in d['sources'].values():
            s['n'] = 0
    if mode == 'drift':
        DRIFT['n'] += 1
        n = DRIFT['n']                                      # newest first, as the Worker sorts: 새 기사 n, n − 1, …
        d['items'] = [{'src': 'hankyung', 'title': f'[시험] 새 기사 {n - k} — 삼성전자 신고가', 'url': f'https://www.hankyung.com/article/test-{n - k}',
                       't': iso(now - timedelta(seconds=30 * k))} for k in range(n)] + d['items']
    return d


# ── 공시 (disclosures/today) fixtures ──
BYC = {x['c']: x for x in SNAP['stocks']}
UNI = json.loads((ROOT / 'web/universe.json').read_text(encoding='utf-8'))
MAPK = [UNI['K'][i:i + 6] for i in range(0, len(UNI['K']), 8)]
MAPQ = [UNI['Q'][i:i + 6] for i in range(0, len(UNI['Q']), 8)]
OFFMAP = [UNI['X'][i:i + 6] for i in range(0, len(UNI['X']), 9) if UNI['X'][i:i + 6].endswith('0')]
TITLES = {
    '실적': ['연결재무제표기준영업(잠정)실적(공정공시)', '매출액또는손익구조30%(대규모법인은15%)이상변동', '영업(잠정)실적(공정공시)'],
    '주요': ['단일판매ㆍ공급계약체결', '현금ㆍ현물배당결정', '자기주식취득결정', '유상증자결정', '타법인주식및출자증권취득결정'],
    '정기': ['분기보고서 (2026.09)', '반기보고서 (2026.06)'],
    '지분': ['임원ㆍ주요주주특정증권등소유상황보고서', '주식등의대량보유상황보고서(일반)'],
    '기타': ['기업설명회(IR)개최(안내공시)', '특수관계인과의내부거래', '투자판단관련주요경영사항'],
}
DRIFT_D = {'n': 0}
ETAG_D = {'asOf': None}


def hm(m):
    m = max(0, min(1439, int(m)))
    return f'{m // 60:02d}:{m % 60:02d}'


def disc_body(mode):
    now = datetime.now(KST)
    nm = now.hour * 60 + now.minute
    day = now
    if mode == 'holiday':                       # the latest weekday before today
        day = now - timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    ymd = day.strftime('%Y%m%d')
    since_m = max(0, nm - 150)
    rows, seq = [], [0]

    def add(c, k, t, s=None, n=None, f=None):
        seq[0] += 1
        o = {'c': c, 't': t, 'k': k}
        if n: o['n'] = n
        o['r'] = f'{ymd}{900000 - seq[0]:06d}'           # newest first: the first added gets the largest number
        if s is not None: o['s'] = hm(s)
        if f: o['f'] = f
        rows.append(o)
    if mode in ('empty',):
        pass
    else:
        # fixed cases (newest first)
        add('005930', '실적', TITLES['실적'][0], nm - 5)
        add('005490', '주요', TITLES['주요'][1], nm - 12)
        add('035420', '주요', TITLES['주요'][0], nm - 20, n='기재정정')
        add('005380', '지분', TITLES['지분'][1], nm - 40, f='국민연금공단')
        add('005490', '주요', TITLES['주요'][2], nm - 50)
        add('005490', '정기', TITLES['정기'][0], nm - 60)
        for _ in range(4):
            add('005930', '지분', TITLES['지분'][0], nm - 70)
        add('000660', '지분', TITLES['지분'][0], nm - 80)
        add('000660', '지분', TITLES['지분'][1], nm - 85)
        add('005930', '주요', TITLES['주요'][1], since_m)          # seen when watching began: no dot
        kinds = ['실적', '주요', '정기', '정기', '지분', '정기', '지분', '기타', '주요', '정기', '지분', '실적']
        skip = {'005930', '005490', '000660', '035420', '005380'}
        pool = [c for c in MAPK[:220] + MAPQ[:160] if c not in skip]
        if mode == 'busy':
            pool = pool * 4
        for i, c in enumerate(pool):
            if mode != 'busy' and i % 3 == 2:
                continue
            k = kinds[i % len(kinds)]
            if mode == 'busy' and i % 3:
                k = '정기'
            s = None if i % 17 == 0 else (nm - 3 - i % 6 if i < 6 else nm - 35 - (i * 7) % max(1, nm - since_m - 40))
            add(c, k, TITLES[k][i % len(TITLES[k])], s)
        for i, c in enumerate(OFFMAP[:60 if mode != 'busy' else 300]):
            k = kinds[(i + 3) % len(kinds)]
            add(c, k, TITLES[k][i % len(TITLES[k])], nm - 30 - i % 90)
        if mode == 'drift':
            DRIFT_D['n'] += 1
            for j in range(DRIFT_D['n']):
                c = MAPK[40 + j]
                o = {'c': c, 't': f'단일판매ㆍ공급계약체결 (시험 {DRIFT_D["n"] - j})', 'k': '주요', 'r': f'{ymd}{950000 + DRIFT_D["n"] - j:06d}', 's': hm(nm)}
                rows.insert(0, o)
    # the receipt number grows with the time it was first seen (as on the real feed); rows without s sit among the oldest
    drift_rows = [o for o in rows if o['r'][8:9] == '9' and int(o['r'][8:]) >= 950000]
    rest = [o for o in rows if o not in drift_rows]
    rest.sort(key=lambda o: (o.get('s') or '00:00', o['r']), reverse=True)
    for i, o in enumerate(rest):
        o['r'] = f'{ymd}{900000 - i:06d}'
    rows = sorted(drift_rows, key=lambda o: o['r'], reverse=True) + rest
    zero = lambda: {k: 0 for k in ('실적', '주요', '지분', '정기', '기타')}
    counts = {'K': 0, 'Q': 0, 'total': 0, 'byKind': zero(), 'byKindMarket': {'K': zero(), 'Q': zero()}}
    for o in rows:
        m = BYC.get(o['c'], {}).get('m', 'K')
        counts[m] += 1; counts['total'] += 1; counts['byKind'][o['k']] += 1; counts['byKindMarket'][m][o['k']] += 1
    as_of = now - timedelta(minutes=20) if mode == 'stale' else now - timedelta(seconds=20)
    body = {'date': day.strftime('%Y-%m-%d'), 'asOf': iso(as_of), 'rows': rows, 'counts': counts}
    if mode not in ('holiday', 'nosince'):
        body['since'] = hm(since_m)
    if mode == 'stale':
        body['stale'] = True
    return body


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):
        pass

    def send_body(self, body, status=200, ctype='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('content-type', ctype)
        self.send_header('cache-control', 'no-store')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200):
        self.send_body(json.dumps(obj, ensure_ascii=False).encode(), status)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path
        with LOCK:
            STATS[path] = STATS.get(path, 0) + 1
        if path == '/__mode':
            MODE.update({k: v for k, v in q.items() if k in MODE})
            return self.send_json(MODE)
        if path == '/__stats':
            return self.send_json(STATS)
        if path == '/__reset':
            STATS.clear(); MODE.clear(); MODE.update(DEFAULT); DRIFT['n'] = 0; DRIFT_D['n'] = 0
            return self.send_json({'ok': True})
        if path == '/api/news':
            mode = MODE['news']
            if mode == 'fail':
                return self.send_json({'error': '세 언론사 모두 뉴스를 불러오지 못했어요', 'sources': {k: {'ok': False, 'n': 0, 'at': None, 'error': 'timeout'} for k in ('einfomax', 'hankyung', 'mk')}}, 502)
            if mode == 'html404':
                return self.send_body(b'Not found', 404, 'text/plain')
            if mode == 'slow':
                time.sleep(2.5)
            return self.send_json(news_body(mode))
        if path == '/api/disclosures/today':
            mode = MODE['disc']
            if mode == 'none' or MODE['news'] == 'html404':      # news html404 = a Worker older than both routes
                return self.send_body(b'{"error":"not found"}', 404) if mode == 'none' else self.send_body(b'Not found', 404, 'text/plain')
            if mode == 'none':
                return self.send_body(b'{"error":"not found"}', 404)
            if mode == 'fail':
                return self.send_json({'error': 'DART_KEY가 없어요'}, 503)
            if mode == 'slow':
                time.sleep(2.5)
            body = disc_body(mode)
            if mode == 'etag':
                import hashlib
                rest = {k: v for k, v in body.items() if k != 'asOf'}
                tag = 'W/"' + hashlib.sha1(json.dumps(rest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12] + '"'
                inm = self.headers.get('If-None-Match') or ''
                if any(x.strip().replace('W/', '') == tag.replace('W/', '') for x in inm.split(',') if x.strip()):
                    with LOCK:
                        STATS['304'] = STATS.get('304', 0) + 1
                    self.send_response(304)
                    self.send_header('etag', tag); self.send_header('x-as-of', body['asOf']); self.send_header('cache-control', 'no-cache')
                    self.end_headers()
                    return
                raw = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header('content-type', 'application/json; charset=utf-8'); self.send_header('etag', tag)
                self.send_header('x-as-of', body['asOf']); self.send_header('cache-control', 'no-cache'); self.send_header('content-length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
                return
            return self.send_json(body)
        if path == '/api/quotes':
            return self.send_json(QUOTES_ALL if q.get('scope') == 'all' else QUOTES)
        if path.startswith('/api/chart/'):                 # the quick view's 오늘 흐름 (not part of the news contract)
            return self.send_json({'points': []})
        if path == '/api/market':
            return self.send_json(MARKET)
        if path == '/api/time':
            return self.send_json({'t': int(time.time() * 1000)})
        if path == '/api/replay/dates':
            return self.send_json({'dates': []})
        if path == '/api/themes':
            return self.send_json({'asOf': None, 'themes': []})
        if path == '/api/breadth':
            return self.send_json({'m': q.get('m'), 'part': 1, 'parts': 1, 'asOf': None, 'rows': []})
        if path == '/api/world':
            return self.send_json({'asOf': None, 'kind': q.get('kind'), 'groups': []})
        if path.startswith('/data/'):
            f = WEB / path[len('/data/'):]
            if f.suffix == '.json' and f.exists():
                return self.send_body(f.read_bytes())
            return self.send_json({'error': '아직 만들어지지 않은 파일이에요'}, 404)
        if path.startswith('/api/'):
            return self.send_json({'error': 'not mocked'}, 404)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8851
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'news mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
