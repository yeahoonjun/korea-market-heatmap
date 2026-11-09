#!/usr/bin/env python3
"""Mock Worker for the 해외 · 원자재 tabs: serves web/ plus /api/world* (AGENTS.md §3-4) and quiet stubs for the other /api calls.

  python3 qa/world/mock_api.py [port=8803]

Routes: /api/world?kind=index|commodity, /api/world/chart/<key>?tf=3m|1y (1d / unknown key → 400 like the Worker),
        /api/quotes, /api/market, /api/replay/dates, /api/breadth, /api/themes, /data/<name>.json, static files from web/.
Test controls (not part of the contract):
  /__mode?world=ok|fail|empty|closed|slow|html404&chart=ok|none|fail   switch failure modes
  /__stats   request counts per route        /__reset   counts + modes back to default
"""
import json
import pathlib
import random
import sys
import threading
import time
import urllib.parse
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEB = ROOT / 'web'
FIX = HERE / 'fixtures'
WORLD = {k: json.loads((FIX / f'world_{k}.json').read_text(encoding='utf-8')) for k in ('index', 'commodity')}
CHARTS = json.loads((FIX / 'charts.json').read_text(encoding='utf-8'))
KEYS = {it['key']: it for d in WORLD.values() for g in d['groups'] for it in g['items']}
MARKET_P = ROOT / 'qa/extras/fixtures/market.json'
MARKET = json.loads(MARKET_P.read_text(encoding='utf-8')) if MARKET_P.exists() else {'asOf': None, 'items': []}

SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
QUOTES = {k: v for k, v in SNAP.items() if k != 'stocks'}
QUOTES['afterHours'] = False
rows = []
for m in ('K', 'Q'):
    rows += sorted((x for x in SNAP['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x['cap'])[:300]
QUOTES['stocks'] = rows

DEFAULT = {'world': 'ok', 'chart': 'ok'}
MODE = dict(DEFAULT)
STATS = {}
LOCK = threading.Lock()


def synth_chart(key, days):
    """Deterministic random walk ending at the item's current value (keys without a recorded chart)."""
    it = KEYS[key]
    rnd = random.Random(key)
    end = date.today()
    out, v = [], it['value']
    d = end
    while len(out) < days:
        if d.weekday() < 5:
            out.append([d.isoformat(), round(v, 4)])
            v = v / (1 + rnd.gauss(0.0004, 0.011))
        d -= timedelta(days=1)
    return out[::-1]


def chart(key, tf):
    rows = CHARTS.get(key) or synth_chart(key, 252)
    cut = (date.today() - timedelta(days=92 if tf == '3m' else 366)).isoformat()
    return {'key': key, 'tf': tf, 'bars': [{'t': t, 'c': c} for t, c in rows if t >= cut]}


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
            k = path if not path.startswith('/api/world/chart/') else '/api/world/chart'
            STATS[k] = STATS.get(k, 0) + 1
            if path == '/api/world':
                STATS['world:' + q.get('kind', '')] = STATS.get('world:' + q.get('kind', ''), 0) + 1
        if path == '/__mode':
            MODE.update({k: v for k, v in q.items() if k in MODE})
            return self.send_json(MODE)
        if path == '/__stats':
            return self.send_json(STATS)
        if path == '/__reset':
            STATS.clear(); MODE.clear(); MODE.update(DEFAULT)
            return self.send_json({'ok': True})
        if path == '/api/world':
            kind = q.get('kind')
            if kind not in WORLD:
                return self.send_json({'error': 'kind는 index 또는 commodity여야 해요'}, 400)
            mode = MODE['world']
            if mode == 'fail':
                return self.send_json({'error': '해외 시세를 불러오지 못했어요'}, 502)
            if mode == 'html404':
                return self.send_body(b'Not found', 404, 'text/plain')
            if mode == 'slow':
                time.sleep(2.5)
            d = json.loads(json.dumps(WORLD[kind]))
            d['asOf'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            if mode == 'empty':
                d['groups'] = []
            if mode == 'closed':
                for g in d['groups']:
                    for it in g['items']:
                        it['status'] = 'CLOSE'
            return self.send_json(d)
        if path.startswith('/api/world/chart/'):
            key = urllib.parse.unquote(path.rsplit('/', 1)[1])
            if MODE['chart'] == 'none':
                return self.send_body(b'Not found', 404, 'text/plain')
            if MODE['chart'] == 'fail':
                return self.send_json({'error': '차트를 불러오지 못했어요'}, 502)
            if key not in KEYS:
                return self.send_json({'error': '알 수 없는 항목이에요'}, 400)
            tf = q.get('tf') or '3m'
            if tf not in ('3m', '1y'):
                return self.send_json({'error': 'tf는 3m 또는 1y여야 해요 (해외 분봉 원천이 없어요)'}, 400)
            return self.send_json(chart(key, tf))
        if path == '/api/quotes':
            return self.send_json(QUOTES)
        if path == '/api/market':
            return self.send_json(MARKET)
        if path == '/api/replay/dates':
            return self.send_json({'dates': []})
        if path == '/api/themes':
            return self.send_json({'asOf': None, 'themes': []})
        if path == '/api/breadth':
            return self.send_json({'m': q.get('m'), 'part': 1, 'parts': 1, 'asOf': None, 'rows': []})
        if path.startswith('/data/'):
            f = WEB / path[len('/data/'):]
            if f.suffix == '.json' and f.exists():
                return self.send_body(f.read_bytes())
            return self.send_json({'error': '아직 만들어지지 않은 파일이에요'}, 404)
        if path.startswith('/api/'):
            return self.send_json({'error': 'not mocked'}, 404)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8803
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'world mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
