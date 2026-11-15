#!/usr/bin/env python3
"""Mock Worker for the floating-window checks (qa/float/test_float.py): qa/world/mock_api.py (web/ + /api/world · quotes · market …)
plus quiet answers for the routes it leaves as 404 — /api/time, /api/calendar (an empty, healthy range), /api/policy, /api/chart/<code> — so the console
stays clean on every tab.

  python3 qa/float/mock_float.py [port=8970]      (ports 8970–8979; FLOAT_WEB=<dir> serves another build's web/)
"""
import importlib.util
import json
import os
import pathlib
import sys
import time
import urllib.parse
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('world_mock', ROOT / 'qa/world/mock_api.py')
W = importlib.util.module_from_spec(spec)
sys.modules['world_mock'] = W
spec.loader.exec_module(W)
if os.environ.get('FLOAT_WEB'):                  # another build's web/ (a baseline to compare with)
    W.WEB = pathlib.Path(os.environ['FLOAT_WEB'])


class H(W.H):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == '/api/time':
            return self.send_json({'t': int(time.time() * 1000)})
        if u.path == '/api/calendar':
            return self.send_json({'asOf': None, 'from': q.get('from'), 'to': q.get('to'), 'tz': 'Asia/Seoul', 'days': {}, 'events': [], 'sources': {}, 'manual': True})
        if u.path.startswith('/api/chart/'):              # the quick view's 오늘 흐름
            return self.send_json({'code': u.path.rsplit('/', 1)[-1], 'points': []})
        if u.path == '/api/policy':
            return self.send_json({'asOf': None, 'items': [], 'sources': {}})
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8970
    assert 8970 <= port <= 8979 or 9010 <= port <= 9029, 'ports 8970–8979 (or 9010–9029: the design-standard agents)'
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
