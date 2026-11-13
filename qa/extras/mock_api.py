#!/usr/bin/env python3
"""Mock Worker for the extras module: serves web/ plus the §3-2 API shapes.

  python3 qa/extras/mock_api.py [port=8796]

Routes: /api/quotes, /api/market, /api/replay/dates, /api/replay?date=, /api/chart/<code>, /api/time, /api/world?kind=,
        /api/breadth, /api/themes, /data/<file> (= web/<file>), static files from web/ (index.html, manifest, sw.js, icons).
Test controls (not part of the contract):
  /__mode?market=ok|fail|empty&replay=ok|empty|fail|stale&world=ok|fail   switch failure modes
  /__stats                                                request counts per route
"""
import json
import pathlib
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa/live'))
from ws_mock import answer_live   # GET /api/live: {t:'off', reason:'closed'} like the real Worker outside the session
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

MODE = {'market': 'ok', 'replay': 'ok', 'world': 'ok'}
# /api/world?kind=index, trimmed to the world clock's representative indexes (+ two more): status as in the contract
WORLD = {'asOf': '2026-11-09T06:22:00Z', 'kind': 'index', 'groups': [
    {'key': 'us', 'name': '미국', 'items': [
        {'key': 'INX', 'name': 'S&P 500', 'value': 6800.1, 'change': -12.3, 'ratio': -0.18, 'status': 'CLOSE', 'tradedAt': '2026-11-08T16:00:00-05:00'},
        {'key': 'DJI', 'name': '다우존스', 'value': 47100.2, 'change': 50.1, 'ratio': 0.11, 'status': 'CLOSE', 'tradedAt': '2026-11-08T16:00:00-05:00'}]},
    {'key': 'eu', 'name': '유럽', 'items': [
        {'key': 'FTSE', 'name': '영국 FTSE 100', 'value': 9700.5, 'change': 20.0, 'ratio': 0.21, 'status': 'CLOSE', 'tradedAt': '2026-11-08T16:35:00Z'}]},
    {'key': 'asia', 'name': '아시아·태평양', 'items': [
        {'key': 'N225', 'name': '니케이 225', 'value': 50100.0, 'change': 300.0, 'ratio': 0.6, 'status': 'OPEN', 'tradedAt': '2026-11-09T15:20:00+09:00'},
        {'key': 'HSI', 'name': '항셍', 'value': 26000.0, 'change': -50.0, 'ratio': -0.19, 'status': 'OPEN', 'tradedAt': '2026-11-09T14:20:00+08:00'},
        {'key': 'SSEC', 'name': '상해종합', 'value': 4000.0, 'change': 8.0, 'ratio': 0.2, 'status': 'OPEN', 'tradedAt': '2026-11-09T14:20:00+08:00'}]}]}
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
        if path == '/api/live':
            return answer_live(self)
        if path == '/__mode':
            MODE.update({k: v for k, v in q.items() if k in MODE})
            return self.send_json(MODE)
        if path == '/__stats':
            return self.send_json(STATS)
        if path == '/__reset':
            STATS.clear(); MODE.update(market='ok', replay='ok', world='ok')
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
        if path == '/api/time':
            return self.send_json({'t': int(time.time() * 1000)})
        if path == '/api/world':
            if MODE['world'] == 'fail':
                return self.send_json({'error': '해외 시세를 불러오지 못했어요'}, 502)
            if q.get('kind', 'index') != 'index':
                return self.send_json({'asOf': WORLD['asOf'], 'kind': q.get('kind'), 'groups': []})
            return self.send_json(WORLD)
        if path == '/api/breadth':
            m = q.get('m', 'K')
            rows = [[x['c'], x['r']] for x in SNAP['stocks'] if x['m'] == m]
            return self.send_json({'m': m, 'part': int(q.get('part', 1) or 1), 'parts': 1, 'asOf': SNAP['asOf'], 'rows': rows})
        if path == '/api/themes':
            return self.send_json({'asOf': SNAP['asOf'], 'themes': []})
        if path.startswith('/data/') and (WEB / path[6:]).is_file() and '/' not in path[6:]:
            self.path = '/' + path[6:]
            return super().do_GET()
        if path.startswith('/api/chart/'):
            return self.send_json({'day': '20261109', 'points': []})
        if path == '/api/disclosures/today':        # 공시 (§3-29/§3-30): an empty, healthy day keeps the console quiet (qa/disclosure has the real cases)
            kst = time.gmtime(time.time() + 9 * 3600)
            z = {k: 0 for k in ('실적', '주요', '지분', '정기', '기타')}
            return self.send_json({'date': time.strftime('%Y-%m-%d', kst), 'asOf': time.strftime('%Y-%m-%dT%H:%M:%S+09:00', kst), 'rows': [],
                                   'counts': {'K': 0, 'Q': 0, 'total': 0, 'byKind': z, 'byKindMarket': {'K': dict(z), 'Q': dict(z)}}, 'since': '07:00'})
        if path == '/api/news':                    # src/news polls it once the card is near the screen (qa/news has the real fixtures)
            at = time.strftime('%Y-%m-%dT%H:%M:%S+09:00', time.gmtime(time.time() + 9 * 3600))
            return self.send_json({'asOf': at, 'items': [], 'sources': {k: {'ok': True, 'n': 0, 'at': at} for k in ('einfomax', 'hankyung', 'mk')}})
        if path.startswith('/api/') or path.startswith('/data/'):
            return self.send_json({'error': 'not mocked'}, 404)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8796
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
