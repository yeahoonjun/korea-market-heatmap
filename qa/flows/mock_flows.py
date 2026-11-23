#!/usr/bin/env python3
"""Mock Worker for the 투자자별 순매수 카드 (src/flows), the 요약 카드 date fix and 수급 line (src/summary) and the stock page's 오늘 잠정
block (src/stock) — qa/flows/test_flows_card.py. qa/stock/mock_api.py (web/ of this worktree + the stock page routes) plus:

  python3 qa/flows/mock_flows.py [port=9095]          (ports 9095–9099, env FLOWS_CARD_PORT in the test)

Everything here is SYNTHETIC (built from data/snapshot.json codes with a fixed hash — no real flows):
  /api/time                 {t} = the configured clock (now=…), so the page's server-time offset is ~0 under Playwright's fixed clock
  /api/quotes               top 300 × 2 of the snapshot, asOf = qasof, marketStatus = status (OPEN | CLOSE) for both markets
  /api/breadth?m=K|Q        every snapshot stock of that market [code, r, lim?] — lim 1 only for the codes in blim (today's 상한가)
  /data/flows.json          {asOf: fdate, unit, sw, f:{code: [외 1일, 기 1일, 개 1일, …]}, stale:{one code}} (fixture() below); fdate=none → 404
  /data/close.json          {date: cdate, asOf, lim:true, c:{code: [p, d, r, lim?]}} — lim 1 only for the codes in clim ("Friday's" 상한가)
  /api/flows/market         mk=ok|stale|fail|gone|slow|zero (zero: before the open — today's date, all 0) — {asOf: now, date: now's day, K:{personal, foreign, institutional}, Q:{…}} 억원
  /api/flows/live           X-Panse-Inv must be TOKEN (else 403) — the same payload the test's KH.flowsLive stub hands out (live_payload)
  /api/flows/live/stock/X   X-Panse-Inv must be TOKEN (else 403); est=ok|empty|fail|gone|none(503)|closed|stale — {code, date: now's day, slots:[{no, t, f, i}]}
  /api/inv/me               X-Panse-Inv must be TOKEN (else 403) → {n:'QA', own:false}
Controls (test only): /__config?now=ISO&qasof=ISO&status=OPEN&fdate=YYYY-MM-DD&cdate=YYYY-MM-DD&clim=c1,c2&blim=c3&mk=ok&est=ok
  (an empty value drops the key) · /__fstats request counts per family / flows route · /__freset · /__fixture → {flows, market, live}
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa/stock'))
import mock_api as base  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
TOKEN = 'qa-family-token-0123456789'
SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
ROWS = {x['c']: x for x in SNAP['stocks']}
TOP = []
for m in ('K', 'Q'):
    TOP += sorted((x for x in SNAP['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x.get('cap', 0))[:300]
FDEF = {'now': '2026-11-24T13:05:00+09:00', 'qasof': '2026-11-24T13:05:00+09:00', 'status': 'OPEN', 'fdate': '2026-11-23',
        'cdate': '2026-11-23', 'mk': 'ok', 'est': 'ok', 'clim': '', 'blim': ''}
FCONF = dict(FDEF)
FSTATS = {}
LOCK = threading.Lock()


def hv(c, salt):
    """a fixed pseudo-random number in [0, 1) per code and salt"""
    return int(hashlib.sha1(f'{c}:{salt}'.encode()).hexdigest()[:8], 16) / 2 ** 32


def fixture():
    """flows.json f: [외국인1일, 기관1일, 개인1일, 외5, 기5, 외20, 기20, 외연속일, 외연속금액, 기연속일, 기연속금액] in 억원 (synthetic)"""
    f = {}
    for c, x in ROWS.items():
        cap = max(1.0, float(x.get('cap') or 1))
        a = round((hv(c, 'f') - 0.5) * cap * 0.004, 1)
        b = round((hv(c, 'i') - 0.5) * cap * 0.003, 1)
        p = round(-(a + b) + (hv(c, 'p') - 0.5) * cap * 0.0005, 1)
        f[c] = [a, b, p, a * 3, b * 3, a * 9, b * 9, 1, a, -1, b]
    stale_code = sorted(ROWS)[5]
    return {'asOf': FCONF['fdate'], 'unit': '억원', 'sw': 20, 'f': f, 'stale': {stale_code: '2026-11-19'}}


def market_body():
    now = dt.datetime.fromisoformat(FCONF['now'])
    return {'asOf': now.isoformat(), 'date': now.strftime('%Y-%m-%d'),
            'K': {'personal': 12345.0, 'foreign': -9876.0, 'institutional': -2469.0},
            'Q': {'personal': -321.0, 'foreign': 456.0, 'institutional': -135.0}}


def live_payload(slot='13:20', slot_no=4):
    """the /api/flows/live shape (AGENTS §3-40): rank rows [code, name, 억원, 주, 현재가, 등락률] — K and Q, 외국인 · 기관 × 순매수 · 순매도"""
    now = dt.datetime.fromisoformat(FCONF['now'])
    rank = {}
    for m in ('K', 'Q'):
        xs = [x for x in TOP if x['m'] == m][:120]
        rank[m] = {}
        for who in ('f', 'i'):
            vals = sorted(((x, round((hv(x['c'], 'L' + who) - 0.5) * (2000 if m == 'K' else 300), 1)) for x in xs), key=lambda t: -t[1])
            row = lambda t: [t[0]['c'], t[0]['n'], t[1], int(t[1] * 1e8 / max(1, t[0]['p'])), t[0]['p'], t[0]['r']]
            rank[m][who] = {'buy': [row(t) for t in vals if t[1] > 0][:30], 'sell': [row(t) for t in sorted(vals, key=lambda t: t[1]) if t[1] < 0][:30]}
    return {'date': now.strftime('%Y-%m-%d'), 'slot': slot, 'slotNo': slot_no, 'at': '13:24', 'src': '한국투자증권 가집계', 'unit': '억원', 'rank': rank,
            'est': {}, 'estSlot': slot_no, 'estN': 0}


def est_body(code):
    now = dt.datetime.fromisoformat(FCONF['now'])
    slots = [{'no': 1, 't': '09:30', 'f': -564000, 'i': 0}, {'no': 2, 't': '10:00', 'f': -559000, 'i': 85000},
             {'no': 3, 't': '11:20', 'f': -1517000, 'i': 280000}, {'no': 4, 't': '13:20', 'f': 2077000, 'i': -193000}]
    return {'code': code, 'date': now.strftime('%Y-%m-%d'), 'slots': [] if FCONF.get('est') == 'empty' else slots}


def close_body():
    lim = set(filter(None, FCONF.get('clim', '').split(',')))
    c = {}
    for k, x in ROWS.items():
        if not x.get('p'):
            continue
        c[k] = [x['p'], x['d'], x['r']] + ([1] if k in lim else [])
    return {'date': FCONF['cdate'], 'asOf': FCONF['cdate'] + 'T15:30:00+09:00', 'lim': True, 'c': c}


def quotes_body():
    st = FCONF.get('status', 'CLOSE')
    out = [dict(x) for x in TOP]
    for x in out:
        x.pop('lim', None)
        if x.get('p'):   # today's candle (KH.ohlc needs op · hi · lo): open halfway back to the base, high / low 1 % around
            base_p = x['p'] - (x.get('d') or 0)
            op = round(base_p + (x.get('d') or 0) * 0.4)
            x.update(op=op, hi=round(max(op, x['p']) * 1.01), lo=round(min(op, x['p']) * 0.99))
    return {'asOf': FCONF['qasof'], 'source': '네이버 증권 (mock)', 'marketStatus': {'KOSPI': st, 'KOSDAQ': st}, 'afterHours': st != 'OPEN',
            'index': SNAP['index'], 'stocks': out}


class H(base.Handler):
    def fcount(self, k):
        with LOCK:
            FSTATS[k] = FSTATS.get(k, 0) + 1

    def invited(self):
        return self.headers.get('X-Panse-Inv') == TOKEN

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        path = u.path
        if path == '/__config':
            with LOCK:
                for k, v in q.items():
                    if v == '' and k in FDEF and FDEF[k] == '':
                        FCONF[k] = ''
                    elif v == '':
                        FCONF[k] = FDEF.get(k, '')
                    else:
                        FCONF[k] = v
            return self.send_json(dict(FCONF))
        if path == '/__freset':
            with LOCK:
                FSTATS.clear(); FCONF.clear(); FCONF.update(FDEF)
            return self.send_json({'ok': True})
        if path == '/__fstats':
            with LOCK:
                return self.send_json(dict(FSTATS))
        if path == '/__fixture':
            return self.send_json({'flows': fixture(), 'market': market_body(), 'live': live_payload(), 'close': {'date': FCONF['cdate']}, 'token': TOKEN})
        if path == '/api/time':
            return self.send_json({'t': int(dt.datetime.fromisoformat(FCONF['now']).timestamp() * 1000)})
        if path == '/api/quotes':
            return self.send_json(quotes_body())
        if path == '/api/breadth':
            m = q.get('m', 'K')
            lim = set(filter(None, FCONF.get('blim', '').split(',')))
            rows = [[c, x['r']] + ([1] if c in lim else []) for c, x in ROWS.items() if x.get('m') == m and x.get('r') is not None]
            return self.send_json({'m': m, 'part': 1, 'parts': 1, 'asOf': FCONF['qasof'], 'rows': rows})
        if path == '/data/flows.json':
            self.fcount('flows.json')
            if FCONF.get('fdate') == 'none':
                return self.send_json({'error': 'not built'}, 404)
            return self.send_json(fixture())
        if path == '/data/close.json':
            if FCONF.get('cdate') == 'none':
                return self.send_json({'error': 'not built'}, 404)
            return self.send_json(close_body())
        if path == '/api/flows/market':
            self.fcount('market')
            mk = FCONF.get('mk', 'ok')
            if mk == 'gone':
                return self.send_json({'error': 'not found'}, 404)
            if mk == 'fail':
                return self.send_json({'error': 'naver 503'}, 503)
            if mk == 'slow':
                time.sleep(4)
            body = market_body()
            if mk == 'zero':   # before the open (real 11/23 08:45): today's date, every value 0
                for m in ('K', 'Q'):
                    body[m] = {'personal': 0, 'foreign': 0, 'institutional': 0}
            if mk == 'stale':
                body['stale'] = True
                body['asOf'] = (dt.datetime.fromisoformat(FCONF['now']) - dt.timedelta(minutes=27)).isoformat()
            return self.send_json(body)
        if path == '/api/inv/me':
            self.fcount('inv')
            return self.send_json({'n': 'QA', 'own': False}) if self.invited() else self.send_json({'error': 'forbidden'}, 403)
        if path == '/api/flows/live':
            self.fcount('live')
            return self.send_json(live_payload()) if self.invited() else self.send_json({'error': 'forbidden'}, 403)
        if path.startswith('/api/flows/live/stock/'):
            self.fcount('live/stock')
            if not self.invited():
                return self.send_json({'error': 'forbidden'}, 403)
            est = FCONF.get('est', 'ok')
            if est == 'gone':
                return self.send_json({'error': 'not found'}, 404)
            if est == 'fail':
                return self.send_json({'error': 'kis 500'}, 502)
            if est == 'none':
                return self.send_json({'error': 'no copy'}, 503)
            body = est_body(path.rsplit('/', 1)[-1])
            if est == 'closed':
                body.update(closed=True, slots=[])
            if est == 'stale':
                body['stale'] = True
            return self.send_json(body)
        return super().do_GET()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9095
    assert 9095 <= port <= 9099, port
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'flows mock on http://127.0.0.1:{port}/', file=sys.stderr, flush=True)
    srv.serve_forever()
