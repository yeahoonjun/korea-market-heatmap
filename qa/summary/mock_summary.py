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


# /data/marks.json fixture (AGENTS §3-2 web/marks.json) built from the snapshot: /__marks?mode=ok|prev|stale|none|missing
#   ok      asOf = the snapshot day, the 3 biggest 시총-top stocks at 4.2 · 3.5 · 3.04× their tv20 (a 4th at 2.9×, 7 stocks with hiDate = asOf and 4 with loDate = asOf
#   prev    asOf = the weekday before (compare mode: needs the stocks' today highs/lows — the snapshot has none, so the 52주 fact hides, the surge line stays)
#   stale   asOf two weekdays before → both hide;  none: ok but every tv = 2 × tv20 (nobody qualifies);  missing: 404
import datetime as _dt
MARKS_MODE = {'m': 'stale'}   # default: an out-of-date file (the older tests: 거래대금 상위, no 52주, no 404 in the console); qa/summary/test_summary.py switches it
SNAP_DAY = SNAP['asOf'][:10]


def _prev_weekday(ymd):
    d = _dt.date.fromisoformat(ymd)
    while True:
        d -= _dt.timedelta(days=1)
        if d.weekday() < 5:
            return d.isoformat()


MARK_PLAN = {'surge': [(4.2, 0), (3.5, 1), (3.04, 2), (2.9, 3)], 'hi': 7, 'lo': 4}


def marks_body(mode):
    if mode == 'missing':
        return None
    day = {'ok': SNAP_DAY, 'none': SNAP_DAY, 'prev': _prev_weekday(SNAP_DAY), 'stale': _prev_weekday(_prev_weekday(SNAP_DAY))}[mode]
    ranked = sorted((x for x in SNAP['stocks'] if x['c'].endswith('0') and x.get('tv')), key=lambda x: -x['cap'])
    # the card's pool = per market top 300 by cap; take plan stocks from the biggest of KOSPI
    top = [x for x in ranked if x['m'] == 'K'][:40]
    mult = {top[i]['c']: k for k, i in MARK_PLAN['surge']}
    c = {}
    for x in SNAP['stocks']:
        k = mult.get(x['c'], 1.0)
        tv20 = x['tv'] / (2.0 if mode == 'none' else k) if x.get('tv') else None
        c[x['c']] = [tv20, 100000, 50000, '2026-01-02', '2026-01-03']
    codes = [x['c'] for x in SNAP['stocks']]
    for i, cd in enumerate(codes[:MARK_PLAN['hi']]):
        c[cd][3] = day
    for cd in codes[100:100 + MARK_PLAN['lo']]:
        c[cd][4] = day
    return {'asOf': day, 'unit': '억원', 'tvn': 20, 'from': '2025-11-24', 'c': c}, mult


class H(base.H):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path
        if path == '/__marks':
            MARKS_MODE['m'] = q.get('mode', 'ok')
            return self.send_json({'mode': MARKS_MODE['m']})
        if path == '/data/marks.json':
            b = marks_body(MARKS_MODE['m'])
            return self.send_json({'error': 'missing'}, 404) if b is None else self.send_json(b[0])
        if path == '/__marks_plan':
            b = marks_body('ok')
            return self.send_json({'names': {R[c]['n']: k for c, k in b[1].items()}, 'hi': MARK_PLAN['hi'], 'lo': MARK_PLAN['lo'], 'day': SNAP_DAY})
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
