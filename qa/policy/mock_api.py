#!/usr/bin/env python3
"""Mock Worker for the 정책 자료 tab: the news mock (qa/news/mock_api.py — web/, /api/news, /api/disclosures/today, quiet stubs) plus
/api/policy (docs/standards/policy-feeds.md §4).

  python3 qa/policy/mock_api.py [port=8970]

/api/policy answers qa/policy/fixtures/policy.json (the real worker/src/policy.js output over the sanitized KDI feed + a small fake
gazette whose titles say "(시험)"; node qa/policy/make_fixture.mjs), its dates shifted so the newest day is today (KST) whenever the
test runs.
Test controls (not part of the contract), on top of the news mock's:
  /__mode?policy=ok|stale|nogb|nokdi|empty|fail|none|slow|yesterday
     stale: 관보 failed this time, its last copy rides along (ok:false, stale:true, at 2 h ago); nogb: 관보 failed with no copy (no 관보
     rows); nokdi: the same for KDI; empty: both answered with no rows; fail: 502 {error, sources}; none: 404 (a Worker without the
     route); slow: 2.5 s; yesterday: the newest day is yesterday (rows read M/D)
  /__stats   request counts per route (shared with the news mock)        /__reset   counts + every mode back to default
"""
import importlib.util
import json
import pathlib
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location('news_mock', ROOT / 'qa/news/mock_api.py')
news = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(news)

POLICY = json.loads((HERE / 'fixtures/policy.json').read_text(encoding='utf-8'))
KST = timezone(timedelta(hours=9))
PMODE = {'policy': 'ok'}


def policy_body(mode):
    d = json.loads(json.dumps(POLICY))
    now = datetime.now(KST)
    newest = max(date.fromisoformat(x['t']) for x in d['items'])
    shift = now.date() - newest - (timedelta(days=1) if mode == 'yesterday' else timedelta(0))
    for x in d['items']:
        x['t'] = (date.fromisoformat(x['t']) + shift).isoformat()
    d['asOf'] = news.iso(now)
    for s in d['sources'].values():
        s['at'] = news.iso(now - timedelta(minutes=3))
    if mode == 'stale':
        d['sources']['gwanbo'].update({'ok': False, 'stale': True, 'error': 'http 500', 'at': news.iso(now - timedelta(hours=2))})
    if mode in ('nogb', 'nokdi'):
        k = 'gwanbo' if mode == 'nogb' else 'kdi'
        d['items'] = [x for x in d['items'] if x['src'] != k]
        d['sources'][k] = {'ok': False, 'n': 0, 'at': None, 'error': 'http 401 gw 30' if k == 'gwanbo' else 'timeout'}
    if mode == 'empty':
        d['items'] = []
        for s in d['sources'].values():
            s['n'] = 0
    return d


class H(news.H):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == '/__mode':
            if 'policy' in q:
                PMODE['policy'] = q['policy']
            news.MODE.update({k: v for k, v in q.items() if k in news.MODE})
            return self.send_json(dict(news.MODE, **PMODE))
        if u.path == '/__reset':
            PMODE['policy'] = 'ok'
            return super().do_GET()
        if u.path == '/api/policy':
            with news.LOCK:
                news.STATS[u.path] = news.STATS.get(u.path, 0) + 1
            mode = PMODE['policy']
            if mode == 'none':
                return self.send_body(b'{"error":"not found"}', 404)
            if mode == 'fail':
                return self.send_json({'error': '정책 자료를 불러오지 못했어요', 'sources': {'kdi': {'ok': False, 'n': 0, 'at': None, 'error': 'timeout'}, 'gwanbo': {'ok': False, 'n': 0, 'at': None, 'error': 'network'}}}, 502)
            if mode == 'slow':
                time.sleep(2.5)
            return self.send_json(policy_body(mode))
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8970
    srv = news.ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'policy mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
