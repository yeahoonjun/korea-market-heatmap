"""Synthetic scenes for qa/badges/test_badges.py (AGENTS §3-41): /api/quotes (the top 300 × 2 of data/snapshot.json with KRX op · hi ·
lo · tv), web/marks.json, web/flows.json, web/alerts.json and today's 공시 rows — every badge rule has a stock that should and one that
should not light. The day S is the KST weekday the test runs on (or the last one), PREV the weekday before it."""
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
KST = dt.timezone(dt.timedelta(hours=9))
SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))


def weekday_before(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


TODAY = dt.datetime.now(KST).date()
S = TODAY if TODAY.weekday() < 5 else weekday_before(TODAY)
PREV = weekday_before(S)
OLD = weekday_before(PREV)
iso = lambda d: d.isoformat()
md = lambda d: f'{d.month}/{d.day}'
LONG_AGO = iso(S - dt.timedelta(days=200))


def top_rows():
    out = []
    for m in ('K', 'Q'):
        out += sorted((x for x in SNAP['stocks'] if x.get('m') == m and x['c'].endswith('0')), key=lambda x: -x.get('cap', 0))[:300]
    return [dict(r) for r in out]


ROWS = top_rows()
BY = {r['c']: r for r in ROWS}
K300 = [r['c'] for r in ROWS if r['m'] == 'K']

# who is who (codes from the top 300 of 코스피; the small ones sit near the end — small tiles)
HI = '005930'        # 신고가 · 급증 5.3× (tier 2) · 외국인 9일 → the plate [hi, v2, 외], plus a 공시 fold
LO = '000660'        # 신저가 · 기관 7일 → [lo, 기]
V1 = '402340'        # 급증 3.2× (tier 1)
V3 = '373220'        # 급증 12× (tier 3) + 외국인 · 기관 8일 → [v3, 외기]
NOV = '006400'       # 2.9× → none
DROP = '207940'      # 급증 3.5× + 외국인 7일 → [막대 1, 외]: on 1280 its price line sits 5px over the bottom, so it gives way to the plate
SMALLTV = '009150'   # ratio 5× but tv < 10억 → none
RIGHTS = '105560'    # lo < lo52 but the base price < lo52 (권리락) → no 신저가
STALE = '005380'     # hi > hi52 but the row is stale → none
YOUNG = '068270'     # listed 3 days ago, hi > hi52 → none
LISTED = '032830'    # listed 60 days ago, hi > hi52 → "상장 후 신고가"
SELL = '028260'      # 외국인 −8일 → 연속 순매도 chip only (no plate)
FLOW5 = '055550'     # 외국인 +5일 → a tooltip line only
FLOW20 = '012330'    # 기관 +20 (sw) → "20일 이상"
ALERT = '015760'     # 투자주의 → 시장 경보 chip only
NXHI = '035420'      # NXT high > hi52 but KRX high below → no 신고가 (the facts are KRX)
LIMU = '086790'      # 상한가 + 신고가 + 급증 → the 상 · 하 chip and the plate side by side (big enough) — or the chip gives way
PACE = '316140'      # 2.5× so far at 13:05 → no badge, a pace line "이 속도면 하루 4배쯤"
EVE_VOL = '000270'   # evening: tv20 holds today (111 = (19·100 + 320) / 20) → 320 / 100 = 3.2× after the back-out (raw 2.88×)
SMALL_VOL = [c for c in K300[40:160] if c != '000100']   # ~120 mid-size and small tiles with 1 · 2 · 3 kinds — the plate ladder
SMALL_DISC = SMALL_VOL[::4]                                 # a 공시 fold on a quarter of them (coexistence)


def krx(r, hi=None, lo=None):
    p = r['p']
    r['op'] = r.get('op') or p
    r['hi'] = hi if hi is not None else max(p, round(p * 1.01))
    r['lo'] = lo if lo is not None else min(p, round(p * 0.99))
    return r


def quotes(hm='13:05', status='OPEN', nx=True):
    rows = [krx(dict(r)) for r in ROWS]
    by = {r['c']: r for r in rows}
    def move(c, pct):                                # today's change (so the base price = p − d sits inside the 52-week band)
        r = by[c]; r['d'] = round(r['p'] * pct); r['r'] = round(r['d'] / (r['p'] - r['d']) * 100, 2)
    for c in (HI, LISTED, STALE, YOUNG, NXHI):
        move(c, 0.03)
        if c != NXHI:
            by[c]['hi'] = round(by[c]['p'] * 1.05)
    move(LO, -0.03)
    by[LO]['lo'] = round(by[LO]['p'] * 0.95)
    by[RIGHTS]['lo'] = round(by[RIGHTS]['p'] * 0.95)
    by[RIGHTS]['d'] = by[RIGHTS]['p'] * 0.3          # base = p − d far under lo52: the bars' basis moved overnight (권리락)
    by[LIMU].update(r=29.95, d=round(by[LIMU]['p'] * 0.2305), lim=1, hi=by[LIMU]['p'])
    for c, tv in ((HI, 530), (V1, 320), (V3, 1200), (NOV, 290), (LIMU, 600), (PACE, 250), (EVE_VOL, 320), (DROP, 350)):
        by[c]['tv'] = tv
    by[SMALLTV]['tv'] = 8
    for i, c in enumerate(SMALL_VOL):                # 1 · 2 · 3 kinds by turns (급증 · + 외국인 · + 신고가) — the plate ladder
        by[c]['tv'] = max(by[c].get('tv') or 0, 10) * (3.5 if i % 3 == 0 else 6 if i % 3 == 1 else 11)
        if i % 3 == 2:
            move(c, 0.03)
            by[c]['hi'] = round(by[c]['p'] * 1.05)
    if nx:
        r = by[NXHI]
        r['nx'] = {'p': r['p'], 'd': r['d'], 'r': r['r'], 's': 'reg', 'o': 1, 't': f'{iso(S)}T{hm}:00+09:00', 'v': 1000, 'tv': 10, 'op': r['p'], 'hi': round(r['p'] * 1.08), 'lo': r['lo']}
    return {'asOf': f'{iso(S)}T{hm}:00+09:00', 'source': '네이버 증권 (mock)', 'marketStatus': {'KOSPI': status, 'KOSDAQ': status},
            'afterHours': False, 'index': SNAP['index'], 'stocks': rows}


def marks(asof, eve=False):
    """every top-600 row quiet (tv20 = its tv, a wide 52-week band), the badge stocks set to light (or not)"""
    c, stale = {}, {}
    for r in ROWS:
        tv = r.get('tv') or 0
        c[r['c']] = [max(tv, 1), round(r['p'] * 1.3), round(r['p'] * 0.6), iso(S - dt.timedelta(days=90)), iso(S - dt.timedelta(days=120))]
    for code in (HI, LISTED, STALE, YOUNG, NXHI):
        c[code][1] = round(BY[code]['p'] * 1.02)                 # today's KRX high (×1.05) is above it
    c[LIMU][1] = round(BY[LIMU]['p'] * 0.98)                   # 상한가 = today's high, above it
    c[NXHI][1] = round(BY[NXHI]['p'] * 1.03)                   # KRX high ×1.01 under it; the NXT high ×1.08 above it
    c[LO][2] = round(BY[LO]['p'] * 0.97)
    c[RIGHTS][2] = round(BY[RIGHTS]['p'] * 0.97)
    for code, tv20 in ((HI, 100), (V1, 100), (V3, 100), (NOV, 100), (SMALLTV, 1.6), (LIMU, 100), (PACE, 100), (EVE_VOL, 111), (DROP, 100)):
        c[code][0] = tv20
    for i, code in enumerate(SMALL_VOL):
        c[code][0] = max(BY[code].get('tv') or 0, 10)
        if i % 3 == 2:
            c[code][1] = round(BY[code]['p'] * 1.02)
            if eve:
                c[code][1] = round(BY[code]['p'] * 1.05); c[code][3] = iso(S)
    c[HI][3] = '2026-10-02'
    c[LO][4] = '2026-08-04'
    c[YOUNG].append(iso(S - dt.timedelta(days=3)))
    c[LISTED].append(iso(S - dt.timedelta(days=60)))
    c[EVE_VOL].append(LONG_AGO)                                  # listed long ago: a full 20 sessions
    stale[STALE] = iso(weekday_before(PREV))
    if eve:                                                      # the 16:40 file of S: today is inside the window
        c[HI][1] = round(BY[HI]['p'] * 1.05); c[HI][3] = iso(S)
        c[LO][2] = round(BY[LO]['p'] * 0.95); c[LO][4] = iso(S)
        c[LISTED][3] = iso(S)
        for code in (STALE, YOUNG, NXHI):
            c[code][1] = round(BY[code]['p'] * 1.05)
        c[LIMU][1] = BY[LIMU]['p']; c[LIMU][3] = iso(S)
    return {'asOf': asof, 'unit': '억원', 'tvn': 20, 'from': iso(S - dt.timedelta(days=364)), 'c': c, 'stale': stale}


def flows(asof):
    f = {}
    for r in ROWS:                                   # a small 1 · 5 · 20-day net buy for every stock (the 외국인 · 기관 size maps draw)
        f[r['c']] = [5.0, 3.0, -2.0, 10.0, 6.0, 20.0, 12.0, 1, 1.0, -1, -1.0]
    def put(code, fd=None, fa=0, idays=None, ia=0):
        v = f[code]
        if fd is not None:
            v[7], v[8] = fd, fa
        if idays is not None:
            v[9], v[10] = idays, ia
    put(HI, 9, 1240.5)
    put(LO, idays=7, ia=205.3)
    put(V3, 8, 380.0, 8, 310.2)
    put(SELL, -8, -880.4)
    put(FLOW5, 5, 86.1)
    put(FLOW20, idays=20, ia=1420.7)
    put(LIMU, 7, 640.0)
    put(DROP, 7, 210.0)
    for i, code in enumerate(SMALL_VOL):
        if i % 3:
            put(code, 7 + i % 5, 12.5)
    return {'asOf': asof, 'unit': '억원', 'sw': 20, 'f': f}


def alerts(asof):
    return {'asOf': asof, 'at': '07:50', 'n': 2701, 'c': {ALERT: {'a': 'caution'}, '000100': {'adm': 1}}}


def disc():
    n = dt.datetime.now(KST)
    rows, seq = [], 0
    for code in [HI, V1] + SMALL_DISC:
        seq += 1
        rows.append({'c': code, 't': '단일판매 · 공급계약체결', 'k': '주요', 'r': f'{n.strftime("%Y%m%d")}{900000 - seq:06d}', 's': (n - dt.timedelta(minutes=90)).strftime('%H:%M')})
    return rows


def scene(kind='next'):
    """next: the session (13:05, OPEN), files of PREV · eve: 16:50 CLOSE, marks of S · old: files a weekday too old · 404: no marks ·
    pre: 08:30 (KRX not open yet) · none: no marks, no flows, no alerts (the map without badges, for comparisons)"""
    if kind == 'eve':
        return {'quotes': quotes('16:50', 'CLOSE', nx=False), 'marks': marks(iso(S), eve=True), 'flows': flows(iso(S)), 'alerts': alerts(iso(S)), 'disc': disc()}
    if kind == 'old':
        return {'quotes': quotes(), 'marks': marks(iso(OLD)), 'flows': flows(iso(OLD)), 'alerts': alerts(iso(S)), 'disc': disc()}
    if kind == '404':
        return {'quotes': quotes(), 'marks': None, 'flows': flows(iso(PREV)), 'alerts': alerts(iso(S)), 'disc': disc()}
    if kind == 'pre':
        return {'quotes': quotes('08:30', 'CLOSE', nx=False), 'marks': marks(iso(PREV)), 'flows': flows(iso(PREV)), 'alerts': alerts(iso(S)), 'disc': disc()}
    if kind == 'early':                                          # 09:20: the session open, the pace not yet (it starts at 09:30)
        return {'quotes': quotes('09:20', 'OPEN'), 'marks': marks(iso(PREV)), 'flows': flows(iso(PREV)), 'alerts': alerts(iso(S)), 'disc': disc()}
    if kind == 'none':
        return {'quotes': quotes(), 'marks': None, 'flows': None, 'alerts': None, 'disc': disc()}
    return {'quotes': quotes(), 'marks': marks(iso(PREV)), 'flows': flows(iso(PREV)), 'alerts': alerts(iso(S)), 'disc': disc()}
