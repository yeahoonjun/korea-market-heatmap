#!/usr/bin/env python3
"""Mock Worker for the extras module: serves web/ plus the §3-2 API shapes.

  python3 qa/extras/mock_api.py [port=8796]

Routes: /api/quotes, /api/market, /api/replay/dates, /api/replay?date=, /api/chart/<code>,
        static files from web/ (index.html, manifest, sw.js, icons).
Test controls (not part of the contract):
  /__mode?market=ok|fail|empty&replay=ok|empty|fail|stale   switch failure modes
  /__stats                                                request counts per route
"""
import json
import pathlib
import subprocess
import sys
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEB = ROOT / 'web'
FIX = HERE / 'fixtures'
if not (FIX / 'replay.json').exists():
    subprocess.run([sys.executable, str(HERE / 'make_fixtures.py'), '--offline'], check=True)

SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
MARKET = json.loads((FIX / 'market.json').read_text(encoding='utf-8'))
REPLAY = json.loads((FIX / 'replay.json').read_text(encoding='utf-8'))

QUOTES = {k: v for k, v in SNAP.items() if k != 'stocks'}
QUOTES['afterHours'] = False
rows = []
for m in ('K', 'Q'):
    rows += sorted((x for x in SNAP['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x['cap'])[:300]
QUOTES['stocks'] = rows

MODE = {'market': 'ok', 'replay': 'ok'}
STATS = {}
LOCK = threading.Lock()


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('access-control-allow-origin', '*')
        self.send_header('cache-control', 'no-store')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.split('?')[0] == '/sw.js':
            self.send_header('service-worker-allowed', '/')
        super().end_headers()

    def guess_type(self, path):
        if str(path).endswith('.webmanifest'):
            return 'application/manifest+json'
        return super().guess_type(path)

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
            STATS.clear(); MODE.update(market='ok', replay='ok')
            return self.send_json({'ok': True})
        if path == '/api/quotes':
            return self.send_json(QUOTES)
        if path == '/api/market':
            if MODE['market'] == 'fail':
                return self.send_json({'error': '시장 지표를 불러오지 못했어요'}, 502)
            if MODE['market'] == 'empty':
                return self.send_json({'asOf': MARKET['asOf'], 'items': []})
            return self.send_json(MARKET)
        if path == '/api/replay/dates':
            if MODE['replay'] == 'fail':
                return self.send_json({'error': '리플레이 저장소가 연결되지 않았어요'}, 503)
            if MODE['replay'] == 'empty':
                return self.send_json({'dates': []})
            extra = ['2026-11-10'] if MODE['replay'] == 'stale' else []   # listed, but the record is gone (404)
            return self.send_json({'dates': extra + sorted(REPLAY, reverse=True)})
        if path == '/api/replay':
            if MODE['replay'] in ('fail', '500'):
                return self.send_json({'error': '리플레이를 불러오지 못했어요'}, 503)
            if MODE['replay'] == 'empty':
                return self.send_json({'error': '기록된 날이 아직 없어요'}, 404)
            d = q.get('date') or max(REPLAY)
            if d not in REPLAY:
                return self.send_json({'error': '그날 기록이 없어요'}, 404)
            return self.send_json(REPLAY[d])
        if path.startswith('/api/chart/'):
            return self.send_json({'day': '20261109', 'points': []})
        if path.startswith('/api/') or path.startswith('/data/'):
            return self.send_json({'error': 'not mocked'}, 404)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8796
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
