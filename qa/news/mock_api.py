#!/usr/bin/env python3
"""Mock Worker for the 시장 뉴스 panel: serves web/ plus /api/news (docs/standards/news.md §2-2) and quiet stubs for the other /api calls.

  python3 qa/news/mock_api.py [port=8851]

/api/news answers qa/news/fixtures/news.json (the real Worker's output over the sanitized 2026-11-13 feeds), its times shifted so the
newest item is 4 minutes old (the page reads "today" whenever the test runs).
Test controls (not part of the contract):
  /__mode?news=ok|partial|stale|fail|empty|slow|drift|morning|html404   partial: 연합인포맥스 failed with no copy (no tab);
        stale: 연합인포맥스 failed, its last copy rides along; fail: 502 {error, sources}; drift: every answer adds one new headline on top;
        morning: every item is from yesterday (M/D)
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
WEB = ROOT / 'web'
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

KST = timezone(timedelta(hours=9))
DEFAULT = {'news': 'ok'}
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
            STATS.clear(); MODE.clear(); MODE.update(DEFAULT); DRIFT['n'] = 0
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
        if path == '/api/quotes':
            return self.send_json(QUOTES)
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
