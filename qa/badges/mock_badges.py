#!/usr/bin/env python3
"""Mock Worker for the map-badge checks (qa/badges/test_badges.py, AGENTS §3-41): the built web/ + a scene the test posts.

  python3 qa/badges/mock_badges.py [port=9125]        (ports 9125–9129; BADGES_WEB=<dir> serves another build's web/)

POST /__scene {quotes: /api/quotes body (the top 600), all?: [rows] (scope=all adds these), marks?: marks.json body | null (404),
               flows?: flows.json body | null, alerts?: alerts.json body | null, disc?: [rows of /api/disclosures/today]}
GET  /__log   the paths that met no stub (a page load should leave it empty)
Everything else the page asks for at boot gets a quiet, healthy answer (no console errors): /api/time · market · themes · news ·
disclosures/today · flows/market · breadth · world · policy · funds · koreaexim · calendar · replay/dates · chart/<code> · live
(WebSocket 'off: closed'), /data/<name>.json from web/ unless the scene has it (close.json: 404 — the live quotes stay what is drawn).
"""
import datetime as dt
import json
import os
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'qa/live'))
from ws_mock import answer_live   # noqa: E402

WEB = pathlib.Path(os.environ.get('BADGES_WEB') or ROOT / 'web')
KST = dt.timezone(dt.timedelta(hours=9))
LOCK = threading.Lock()
SCENE = {}
UNKNOWN = []


def now_kst():
    return dt.datetime.now(KST).replace(microsecond=0)


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header('cache-control', 'no-store')
        super().end_headers()

    def send_body(self, body, status=200, ctype='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('content-type', ctype)
        self.send_header('access-control-allow-origin', '*')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200):
        self.send_body(json.dumps(obj, ensure_ascii=False).encode(), status)

    def do_POST(self):
        if self.path.startswith('/__scene'):
            n = int(self.headers.get('content-length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            with LOCK:
                SCENE.clear(); SCENE.update(body); UNKNOWN.clear()
            return self.send_json({'ok': True})
        return self.send_json({'error': 'no'}, 404)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        p = u.path
        if p == '/__log':
            return self.send_json(UNKNOWN)
        if p == '/api/live':
            return answer_live(self)
        if p == '/api/quotes':
            base = SCENE.get('quotes') or {'asOf': None, 'marketStatus': {}, 'index': {}, 'stocks': []}
            rows = list(base.get('stocks', []))
            if q.get('scope') == 'all':
                rows += SCENE.get('all') or []
            elif q.get('codes'):
                want = set(q['codes'].split(','))
                pool = {r['c']: r for r in rows + (SCENE.get('all') or [])}
                rows = [pool[c] for c in want if c in pool]
            return self.send_json(dict(base, stocks=rows))
        if p.startswith('/data/'):
            name = p[len('/data/'):]
            key = name[:-5] if name.endswith('.json') else name
            if key in ('marks', 'flows', 'alerts') and key in SCENE:
                v = SCENE[key]
                return self.send_json(v) if v is not None else self.send_json({'error': 'not built'}, 404)
            f = WEB / name
            if name == 'close.json' or not f.exists() or f.suffix != '.json':
                return self.send_json({'error': 'not built'}, 404)
            return self.send_body(f.read_bytes())
        n = now_kst()
        if p == '/api/time':
            return self.send_json({'t': int(time.time() * 1000)})
        if p == '/api/market':
            idx = (SCENE.get('quotes') or {}).get('index') or {}
            return self.send_json({'asOf': n.isoformat(), 'items': [{'key': k, 'name': {'KOSPI': '코스피', 'KOSDAQ': '코스닥'}[k], **v} for k, v in idx.items() if k in ('KOSPI', 'KOSDAQ')]})
        if p == '/api/themes':
            return self.send_json({'asOf': n.isoformat(), 'themes': []})
        if p == '/api/news':
            return self.send_json({'asOf': n.isoformat(), 'items': [{'src': 'mk', 'title': '코스피, 외국인 매수에 상승 출발', 'url': 'https://www.mk.co.kr/', 't': (n - dt.timedelta(minutes=12)).isoformat()}],
                                   'sources': {'mk': {'ok': True, 'n': 1, 'at': n.isoformat()}}})
        if p == '/api/disclosures/today':
            rows = SCENE.get('disc') or []
            kinds = {k: 0 for k in ('실적', '주요', '지분', '정기', '기타')}
            for r in rows:
                kinds[r['k']] = kinds.get(r['k'], 0) + 1
            return self.send_json({'date': n.strftime('%Y-%m-%d'), 'asOf': n.isoformat(), 'rows': rows, 'since': '07:00',
                                   'counts': {'K': len(rows), 'Q': 0, 'total': len(rows), 'byKind': kinds, 'byKindMarket': {'K': dict(kinds), 'Q': {k: 0 for k in kinds}}}})
        if p == '/api/flows/market':
            return self.send_json({'asOf': n.isoformat(), 'date': n.strftime('%Y-%m-%d'), 'K': {'personal': 0, 'foreign': 0, 'institutional': 0}, 'Q': {'personal': 0, 'foreign': 0, 'institutional': 0}})
        if p == '/api/breadth':
            mk = q.get('m', 'K')
            rows = [[r['c'], r['r']] for r in (SCENE.get('quotes') or {}).get('stocks', []) if r.get('m') == mk]
            return self.send_json({'m': mk, 'part': 1, 'parts': 1, 'asOf': n.isoformat(), 'rows': rows})
        if p == '/api/world':
            return self.send_json({'asOf': None, 'kind': q.get('kind'), 'groups': []})
        if p == '/api/policy':
            return self.send_json({'asOf': None, 'items': [], 'sources': {}})
        if p == '/api/funds':
            return self.send_json({'asOf': None, 'basDt': None, 'source': '금융투자협회', 'items': []})
        if p == '/api/koreaexim':
            return self.send_json({'asOf': None, 'kind': q.get('kind'), 'date': None, 'items': [], 'prev': None})
        if p == '/api/calendar':
            return self.send_json({'asOf': None, 'from': q.get('from'), 'to': q.get('to'), 'tz': 'Asia/Seoul', 'days': {}, 'events': [], 'sources': {}, 'manual': True})
        if p == '/api/replay/dates':
            return self.send_json({'dates': []})
        if p.startswith('/api/chart/'):
            return self.send_json({'code': p.rsplit('/', 1)[-1], 'points': []})
        if p.startswith('/api/'):
            with LOCK:
                UNKNOWN.append(p)
            return self.send_json({'error': 'not mocked'}, 404)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9125
    assert 9125 <= port <= 9129, 'ports 9125–9129'
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
