#!/usr/bin/env python3
"""Mock Worker for the 가족 보기 / 오늘 잠정 checks (qa/flows/test_template_flows.py, AGENTS §3-40): qa/float/mock_float.py (web/ +
/api/quotes · market · world · time …) plus the invite and intraday-flows routes, with SYNTHETIC fixtures in the contract's shape.

  python3 qa/flows/mock_template_flows.py [port=9090]        (ports 9090–9094 — FLOWS_TPL_PORT)

Routes (header X-Panse-Inv: <token>, cache-control private, no-store — 403 {error:'forbidden'} when it is missing or unknown):
  GET  /api/inv/me              {n, own}
  GET  /api/inv                 own only: {items:[{id, n, at, own?}]}
  POST /api/inv {n}             own only: {id, token}     (n 1–12 chars, else 400)
  DELETE /api/inv/{id}          own only: {ok:true}       (the owner's own invite: 409)
  GET  /api/flows/live          {date, slot, slotNo, at, src, unit, rank, est, estSlot, estN} — est over the quotes' 600 (every 7th code
                                left out: "no data"), date = the test's "today"
  GET  /data/flows.json         web/flows.json with asOf = MODE['flowsAsOf'] when set (the evening file)
Test controls (not part of the contract):
  /__mode?today=YYYY-MM-DD&slot=on|null|r1|closed&flowsAsOf=YYYY-MM-DD|off&live=ok|fail|403&me=ok|fail|403&own=ok|fail&date=today|yesterday
         slot r1 = round 1 (09:30: 외국인 only, every 기관 est 0); closed = the Worker's 휴장 (closed:true, slot null)
  /__stats   {path: count} + 'hdr:<path>' = requests that carried the header      /__reset   counts, modes, invites back to default
  /__est     the est sent last ({code: [f, i]})
Tokens: OWNER = 'own_' + 28 × 'a' (n 예훈, own), FAMILY = 'fam_' + 28 × 'b' (n 엄마) — synthetic, not real invites.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('float_mock', ROOT / 'qa/float/mock_float.py')
F = importlib.util.module_from_spec(spec)
sys.modules['float_mock'] = F
spec.loader.exec_module(F)
W = F.W                                          # qa/world/mock_api.py (QUOTES, WEB, STATS …)

OWNER = 'own_' + 'a' * 28
FAMILY = 'fam_' + 'b' * 28
LOCK = threading.Lock()


def kst_today():
    return time.strftime('%Y-%m-%d', time.gmtime(time.time() + 9 * 3600))


def h12(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def fresh_invites():
    return {h12(OWNER): {'n': '예훈', 'own': 1, 'at': '2026-11-16', 'tok': OWNER},
            h12(FAMILY): {'n': '엄마', 'at': '2026-11-22', 'tok': FAMILY}}


DEFAULT = {'today': None, 'slot': 'on', 'flowsAsOf': 'off', 'live': 'ok', 'me': 'ok', 'own': 'ok', 'date': 'today'}
MODE = dict(DEFAULT)
INVITES = fresh_invites()
STATS = {}
LAST = {'est': {}}


def est_for(today):
    """[외국인 주, 기관 주] per streamed code — deterministic per day; every 7th code is missing (no data)"""
    rnd = random.Random('est' + today)
    out = {}
    for i, s in enumerate(W.QUOTES['stocks']):
        if i % 7 == 3 or not s.get('p'):
            continue
        cap_won = s['cap'] * 1e8
        f = round(cap_won * rnd.uniform(-0.003, 0.003) / s['p'])
        g = round(cap_won * rnd.uniform(-0.002, 0.002) / s['p'])
        out[s['c']] = [f, g]
    return out


def rank_rows(est, m, who, side):
    rows = []
    for s in W.QUOTES['stocks']:
        if s['m'] != m or s['c'] not in est:
            continue
        q = est[s['c']][0 if who == 'f' else 1]
        rows.append([s['c'], s['n'], round(q * s['p'] / 1e8, 1), q, s['p'], s.get('r', 0)])
    rows.sort(key=lambda r: -r[2] if side == 'buy' else r[2])
    return rows[:30]


def live_body():
    today = MODE['today'] or kst_today()
    date = today if MODE['date'] == 'today' else time.strftime('%Y-%m-%d', time.gmtime(time.mktime(time.strptime(today, '%Y-%m-%d')) - 86400))
    if MODE['slot'] in ('null', 'closed'):
        body = {'date': date, 'slot': None, 'slotNo': 0, 'at': None, 'src': '한국투자증권 가집계', 'unit': '억원', 'rank': {}, 'est': {}, 'estSlot': None, 'estN': 0}
        if MODE['slot'] == 'closed':
            body['closed'] = True
        return body
    est = est_for(today)
    if MODE['slot'] == 'r1':                         # round 1: 외국인 09:30 only — 기관종합 starts at 10:00
        est = {c: [v[0], 0] for c, v in est.items()}
        LAST['est'] = est
        rank = {m: {'f': {'buy': rank_rows(est, m, 'f', 'buy'), 'sell': rank_rows(est, m, 'f', 'sell')}, 'i': {'buy': [], 'sell': []}} for m in ('K', 'Q')}
        return {'date': date, 'slot': '09:30', 'slotNo': 1, 'at': '09:34', 'src': '한국투자증권 가집계', 'unit': '억원', 'rank': rank, 'est': est, 'estSlot': '09:30', 'estN': len(est)}
    LAST['est'] = est
    rank = {m: {w: {'buy': rank_rows(est, m, w, 'buy'), 'sell': rank_rows(est, m, w, 'sell')} for w in ('f', 'i')} for m in ('K', 'Q')}
    return {'date': date, 'slot': '14:30', 'slotNo': 4, 'at': '14:36', 'src': '한국투자증권 가집계', 'unit': '억원', 'rank': rank,
            'est': est, 'estSlot': '14:30', 'estN': len(est)}


class H(F.H):
    def count(self, path, hdr):
        with LOCK:
            STATS[path] = STATS.get(path, 0) + 1
            if hdr:
                STATS['hdr:' + path] = STATS.get('hdr:' + path, 0) + 1

    def who(self):
        tok = self.headers.get('X-Panse-Inv') or ''
        return INVITES.get(h12(tok)) if tok else None

    def private(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('cache-control', 'private, no-store')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def forbid(self):
        return self.private({'error': 'forbidden'}, 403)

    def gated(self, method):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        if not (path == '/api/inv' or path.startswith('/api/inv/') or path == '/api/flows/live' or path.startswith('/api/flows/live/')):
            return False
        self.count(f'{method} {path if not path.startswith("/api/inv/") or path == "/api/inv/me" else "/api/inv/{id}"}', bool(self.headers.get('X-Panse-Inv')))
        me = self.who()
        if path == '/api/inv/me':
            if MODE['me'] == 'fail':
                self.private({'error': 'upstream'}, 503); return True
            if MODE['me'] == '403' or not me:
                self.forbid(); return True
            self.private({'n': me['n'], 'own': bool(me.get('own'))}); return True
        if path == '/api/flows/live':
            if MODE['live'] == '403' or not me:
                self.forbid(); return True
            if MODE['live'] == 'fail':
                self.private({'error': 'upstream'}, 503); return True
            self.private(live_body()); return True
        if MODE['own'] == 'fail':                    # a KV error on the Worker: 503 before it knows who asks — never a reason to forget
            self.private({'error': 'upstream'}, 503); return True
        if not me or not me.get('own'):
            self.forbid(); return True
        if path == '/api/inv' and method == 'GET':
            items = [dict({'id': k[:12], 'n': v['n'], 'at': v['at']}, **({'own': 1} if v.get('own') else {})) for k, v in INVITES.items()]
            self.private({'items': items}); return True
        if path == '/api/inv' and method == 'POST':
            n = ''
            try:
                ln = int(self.headers.get('content-length') or 0)
                n = str(json.loads(self.rfile.read(ln) or b'{}').get('n') or '').strip()
            except Exception:
                n = ''
            if not n or len(n) > 12:
                self.private({'error': 'bad name'}, 400); return True
            tok = secrets.token_urlsafe(24)
            INVITES[h12(tok)] = {'n': n, 'at': MODE['today'] or kst_today(), 'tok': tok}
            self.private({'id': h12(tok)[:12], 'token': tok}); return True
        if path.startswith('/api/inv/') and method == 'DELETE':
            idv = urllib.parse.unquote(path.rsplit('/', 1)[1])
            for k, v in list(INVITES.items()):
                if k[:12] == idv:
                    if v.get('own'):
                        self.private({'error': 'cannot'}, 409); return True
                    del INVITES[k]
                    self.private({'ok': True}); return True
            self.private({'error': 'not found'}, 404); return True
        self.private({'error': 'method'}, 405)
        return True

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == '/__mode':
            MODE.update({k: v for k, v in q.items() if k in MODE})
            return self.send_json(MODE)
        if u.path == '/__stats':
            return self.send_json(STATS)
        if u.path == '/__est':
            return self.send_json(LAST['est'])
        if u.path == '/__reset':
            STATS.clear(); MODE.clear(); MODE.update(DEFAULT); INVITES.clear(); INVITES.update(fresh_invites())
            return self.send_json({'ok': True})
        if self.gated('GET'):
            return
        if u.path == '/data/flows.json' and MODE['flowsAsOf'] != 'off':
            d = json.loads((W.WEB / 'flows.json').read_text(encoding='utf-8'))
            d['asOf'] = MODE['flowsAsOf']
            return self.send_json(d)
        return super().do_GET()

    def do_POST(self):
        if not self.gated('POST'):
            self.send_json({'error': 'not mocked'}, 404)

    def do_DELETE(self):
        if not self.gated('DELETE'):
            self.send_json({'error': 'not mocked'}, 404)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9090
    assert 9090 <= port <= 9094, 'ports 9090–9094 (FLOWS_TPL_PORT)'
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
