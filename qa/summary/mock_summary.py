#!/usr/bin/env python3
"""Mock Worker for the 오늘의 시장 요약 카드 (docs/standards/market-summary.md, qa/summary/test_summary.py): qa/news/mock_api.py plus the
routes the card reads.

  python3 qa/summary/mock_summary.py [port=8980]        (ports 8980–8989)

Everything qa/news/mock_api.py answers (web/, /api/quotes = the 2026-11-13 close, /api/news, /api/disclosures/today, …) and:
  /api/market     web/market.json (the same 11/13 close as data/snapshot.json — the news mock serves an 11/09 fixture)
  /api/breadth    ?m=K|Q[&part=N]: every stock of that market from data/snapshot.json as [code, r, lim?] (part 1 = all, parts 1)
  /api/themes     {asOf, themes:[{id, name, ratio, up, flat, down}]} — each theme's plain average of its stocks' r in the snapshot
  /api/world      ?kind=index → qa/summary/fixtures/world.json "index"; ?kind=commodity[&with=fx,rates] → "commodity" (예시 값, 실측 아님)
Disclosures start in the news mock's 'holiday' mode (the latest weekday's list), like a weekend; /__mode?disc=… still switches it.
"""
import json
import pathlib
import sys
import urllib.parse
from http.server import ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa/news'))
import mock_api as base  # noqa: E402

base.DEFAULT['disc'] = 'holiday'
base.MODE['disc'] = 'holiday'
MARKET = json.loads((ROOT / 'web/market.json').read_text(encoding='utf-8'))
WORLD = json.loads((HERE / 'fixtures/world.json').read_text(encoding='utf-8'))
SNAP = base.SNAP
BY_M = {m: [x for x in SNAP['stocks'] if x['m'] == m] for m in ('K', 'Q')}
R = {x['c']: x for x in SNAP['stocks']}
THEMES_SRC = json.loads((ROOT / 'web/themes.json').read_text(encoding='utf-8'))


def themes_body():
    out = []
    for t in THEMES_SRC['themes']:
        xs = [R[c] for c in t['codes'] if c in R]
        if not xs:
            continue
        rs = [x['r'] for x in xs]
        out.append({'id': t['id'], 'name': t['name'], 'ratio': round(sum(rs) / len(rs), 2),
                    'up': sum(1 for v in rs if v > 0), 'flat': sum(1 for v in rs if v == 0), 'down': sum(1 for v in rs if v < 0)})
    return {'asOf': SNAP['asOf'], 'themes': out}


THEMES = themes_body()


class H(base.H):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path
        if path == '/api/market':
            return self.send_json(MARKET)
        if path == '/api/breadth':
            m = q.get('m')
            if m not in BY_M:
                return self.send_json({'error': 'm'}, 400)
            rows = [[x['c'], x['r']] + ([x['lim']] if x.get('lim') else []) for x in BY_M[m]]
            return self.send_json({'m': m, 'part': 1, 'parts': 1, 'asOf': SNAP['asOf'], 'rows': rows})
        if path == '/api/themes':
            return self.send_json(THEMES)
        if path == '/api/world':
            kind = q.get('kind')
            if kind == 'index':
                return self.send_json(WORLD['index'])
            if kind == 'commodity':
                body = json.loads(json.dumps(WORLD['commodity']))
                want = set((q.get('with') or '').split(','))
                body['groups'] = [g for g in body['groups'] if g['key'] not in ('fx', 'rates') or g['key'] in want]
                return self.send_json(body)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8980
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'summary mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
