"""Mock /api/quotes + /api/breadth for the §3-8 session phases (Playwright routes), built from a real pre-market capture
(fixtures/quotes_pre.json, breadth_pre_*.json — capture_nxt.py, 2026-11-10 08:21 KST) and web/close.json (KRX closes of 11/09).

phases (name → what the quotes say; clock = the KST wall time the page is given with page.clock.set_fixed_time):
  pre      11/10 08:21  NXT 프리마켓 open (real capture): quotes p = 11/09 KRX close at 0 %, nx s:'pre' o:1 for 432 / 600
  gap      11/10 08:55  프리마켓 over, KRX not open yet: the same rows with o:0, head {session:'pre', open:false}
  after    11/09 17:40  NXT 애프터마켓 open: quotes = Naver's integrated price, nx s:'after' o:1, close.json is of that day
  night    11/09 21:30  after 20:00: nx o:0 (the after-market's last price), head {session:'after', open:false}
  stale    11/10 08:53  프리마켓 over by the clock, but Naver still says OPEN (o:1, head open) — 11/10 08:53 live probe
  regular  11/10 10:15  KRX open (marketStatus OPEN); nx rows stay in the response (pre, o:0) and must be ignored
  reg      11/10 10:15  KRX open and NXT 메인마켓 trading (nx s:'reg' o:1, head {session:'reg', open:true}) — 11/10 09:02 probe
  legacy   11/09 17:40  an older Worker: no nx, no head (after the close: KRX · 통합(Naver's integrated quote))
every nx gets v (shares) / tv (억원), as the Worker sends them from 11/10 (synthetic: a stable fraction of the price × a volume).
"""
import json, os, random, copy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..')) + '/'
FIX = HERE + '/fixtures/'
CLOSE = json.load(open(ROOT + 'web/close.json'))
PRE = json.load(open(FIX + 'quotes_pre.json'))
BR_PRE = {}
for m in ('K', 'Q'):
    part = 1
    while os.path.exists(f'{FIX}breadth_pre_{m}_{part}.json'):
        BR_PRE[(m, part)] = json.load(open(f'{FIX}breadth_pre_{m}_{part}.json')); part += 1

CLOCK = {'pre': '2026-11-10T08:21:30+09:00', 'gap': '2026-11-10T08:55:00+09:00', 'stale': '2026-11-10T08:53:00+09:00',
         'after': '2026-11-09T17:40:20+09:00', 'night': '2026-11-09T21:30:00+09:00', 'regular': '2026-11-10T10:15:00+09:00',
         'reg': '2026-11-10T10:15:05+09:00', 'legacy': '2026-11-09T17:40:20+09:00'}


def _r2(x): return round(x, 2)


def nxvol(q, rnd):
    """NXT volume / value on every nx (v shares, tv 억원), and KRX volume / value where the session has some"""
    for s in q['stocks']:
        x = s.get('nx')
        if x:
            x['v'] = rnd.randint(2, 400) * 1000
            x['tv'] = round(x['v'] * x['p'] / 1e8)


def build(phase):
    """→ (quotes dict, {(m, part): breadth dict})"""
    q, br = _build(phase)
    if phase != 'legacy': nxvol(q, random.Random(11 + len(phase)))
    return q, br


def _build(phase):
    q = copy.deepcopy(PRE)
    br = copy.deepcopy(BR_PRE)
    rnd = random.Random(7 + len(phase))
    C = CLOSE['c']
    if phase == 'pre':
        return q, br
    if phase == 'stale':
        q['asOf'] = '2026-11-10T08:53:00.000000+09:00'
        return q, br
    if phase == 'gap':
        q['asOf'] = '2026-11-10T08:55:00.000000+09:00'
        for s in q['stocks']:
            if s.get('nx'): s['nx']['o'] = 0
        q['nxt'] = {'session': 'pre', 'open': False}
        return q, br
    if phase in ('regular', 'reg'):
        q['asOf'] = '2026-11-10T10:15:00.000000+09:00'
        q['marketStatus'] = {'KOSPI': 'OPEN', 'KOSDAQ': 'OPEN'}
        for i, s in enumerate(q['stocks']):
            base = s['p']; r = _r2(rnd.uniform(-4, 4)); p = round(base * (1 + r / 100))
            s.update(p=p, d=p - base, r=_r2((p - base) / base * 100), v=rnd.randint(50, 5000) * 1000)
            s['tv'] = round(s['v'] * p / 1e8)
            x = s.get('nx')
            if not x: continue
            if phase == 'regular':
                x['o'] = 0
                continue
            # NXT 메인마켓: a price a few ticks off KRX's, traded seconds before the quotes' asOf
            np_ = round(p * (1 + rnd.uniform(-0.3, 0.3) / 100))
            x.update(p=np_, d=np_ - base, r=_r2((np_ - base) / base * 100), s='reg', o=1, t='2026-11-10T10:14:%02d.500000+09:00' % (i % 60))
        q['nxt'] = {'session': 'pre', 'open': False} if phase == 'regular' else {'session': 'reg', 'open': True}
        for key, b in br.items():
            for row in b['rows']:
                row[1] = _r2(rnd.uniform(-4, 4))
                if len(row) >= 4: row[3] = _r2(row[1] + rnd.uniform(-0.3, 0.3))
        return q, br
    # 11/09 evening: quotes of that day; the KRX close is close.json, the integrated quote and NXT move away from it
    day_t = '2026-11-09T17:40:12.000000+09:00' if phase in ('after', 'legacy') else '2026-11-09T19:59:58.000000+09:00'
    q['asOf'] = day_t
    q['marketStatus'] = {'KOSPI': 'CLOSE', 'KOSDAQ': 'CLOSE'}
    q['afterHours'] = phase in ('after', 'legacy')
    for s in q['stocks']:
        c = C.get(s['c'])
        if not c: continue
        kp, kd, kr = c
        base = kp - kd
        sn = SNAPROWS.get(s['c'])                          # that day's KRX volume / value (11/09 snapshot)
        if sn: s.update(v=sn.get('v', 0), tv=sn.get('tv', 0))
        nx = s.get('nx')
        if nx and phase != 'legacy':
            u = rnd.uniform(-2.5, 2.5) / 100
            p = round(kp * (1 + u)); d = p - base
            s['nx'] = {'p': p, 'd': d, 'r': _r2(d / base * 100) if base else 0, 's': 'after', 'o': 1 if phase == 'after' else 0, 't': day_t}
            s.update(p=p, d=d, r=s['nx']['r'])            # Naver's integrated price follows NXT
        else:
            s.pop('nx', None)
            p = round(kp * (1 + rnd.uniform(-1, 1) / 100)) if phase == 'legacy' and nx else kp
            s.update(p=p, d=p - base, r=_r2((p - base) / base * 100) if base else 0)
    if phase == 'legacy':
        q.pop('nxt', None)
    else:
        q['nxt'] = {'session': 'after', 'open': phase == 'after'}
    for key, b in br.items():
        for row in b['rows']:
            c = C.get(row[0])
            row[1] = _r2(c[2]) if c else row[1]
            if phase == 'legacy':
                del row[3:]
            elif len(row) >= 4:
                row[3] = _r2(rnd.uniform(-3, 3))
        b['asOf'] = day_t
    return q, br


SNAPROWS = {x['c']: x for x in json.load(open(ROOT + 'data/snapshot.json'))['stocks']}


def extra_row(code, phase):
    """a code outside the streamed 600 (/api/quotes?codes=): its 11/09 row from data/snapshot.json, no NXT; before 11/10's session
    the quote is that close at 0 %, after 11/09 15:30 it is the close with its move (close.json)"""
    x = SNAPROWS.get(code)
    if not x: return None
    row = {k: x[k] for k in ('c', 'n', 'm', 's', 'i', 'cap', 'p', 'd', 'r', 'tv', 'v') if k in x}
    if phase in ('pre', 'gap', 'stale', 'regular', 'reg'): row.update(d=0, r=0, tv=0, v=0)
    elif x.get('lim'): row['lim'] = x['lim']
    return row


_CACHE = {}


def built(phase):
    if phase not in _CACHE: _CACHE[phase] = build(phase)
    return _CACHE[phase]


def route(page, phase, *, quotes_hook=None):
    """Answer /api/quotes and /api/breadth from a phase's fixture. Returns a holder dict: set holder['phase'] to switch phases
    mid-test (the next request answers from the new one); quotes_hook(q) may edit each main quotes response."""
    hold = {'phase': phase, 'n': 0}

    def on_quotes(r):
        q, _ = built(hold['phase'])
        if '?codes=' in r.request.url:
            codes = r.request.url.split('codes=')[1].split('&')[0].split(',')
            have = {s['c']: s for s in q['stocks']}
            body = dict(q, stocks=[have[c] if c in have else extra_row(c, hold['phase']) for c in codes])
            body['stocks'] = [x for x in body['stocks'] if x]
        else:
            body = copy.deepcopy(q); hold['n'] += 1
            if quotes_hook: quotes_hook(body, hold['n'])
        r.fulfill(status=200, content_type='application/json', body=json.dumps(body, ensure_ascii=False))

    def on_breadth(r):
        _, br = built(hold['phase'])
        qs = dict(x.split('=') for x in r.request.url.split('?')[1].split('&'))
        b = br.get((qs.get('m'), int(qs.get('part', 1))))
        if not b: r.fulfill(status=400, content_type='application/json', body='{"error":"part"}'); return
        r.fulfill(status=200, content_type='application/json', body=json.dumps(b))
    page.route('**/api/quotes*', on_quotes)
    page.route('**/api/breadth*', on_breadth)
    return hold
