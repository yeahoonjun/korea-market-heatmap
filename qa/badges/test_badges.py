#!/usr/bin/env python3
"""지도 배지 (AGENTS §3-41 A안 · drafts/badges.html A): 52주 신고가 · 신저가 · 거래 급증 · 연속 순매수 on the map plate, the legend chips
(+ 연속 순매도 · 시장 경보), the tooltip / quick-view lines, the table marks and the aria tails.

  python3 scripts/build_page.py && python3 qa/badges/test_badges.py [--only=rules,plate,legend,lit,views,themes,perf,snapshot] [--shots DIR]

The built web/ runs behind qa/badges/mock_badges.py on BADGES_QA_PORT (default 9125; 9125–9129 only) with the scenes of
qa/badges/scenes.py posted to /__scene: /api/quotes (top 300 × 2 with KRX op · hi · lo · tv; one NXT row), /data/marks.json,
/data/flows.json, /data/alerts.json and today's 공시 rows. d3 and the web font come from the repo (routes), so nothing leaves the box.
What is checked:
  rules    the session ('next' — the file of the weekday before): 신고가 · 신저가 against hi52 · lo52 with KRX highs (an NXT high above
           does not count), 급증 tiers 3 · 5 · 10× (2.9× and a 10억-under stock: none), a stale row · a week-old listing · a base price
           outside the band (권리락): no 신고 · 신저, "상장 후 신고가", 연속 순매수 외 · 기 · 외기 (7+) on the plate, 순매도 and 경보 as
           kinds only, aria tails; the evening ('eve' — the file of today): hiDate = asOf, the 급증 back-out ((20·tv20 − tv) / 19);
           an old file / no file / before 09:00 / a replay of the day / of another day
  plate    every plate on 1280 · 360 maps: inside its tile at the bottom-left (3px up over a 하한가 bar), size 9 · 11 · 13 · 14 and count
           1 · 2 · 3 by the short side (12 · 20 · 40), the planned items in priority order, never over the 공시 fold or the 상 · 하 chip,
           the price / 시총 line never under it (and dropped for it — compared with the map without badges), neutral ink, KH.layout()
  legend   chip counts = the map's stocks (KH.marks.badge over KH.mapCodes()), zero chips hidden, a chip lights only those stocks (.mdim
           on the rest, union of chips, AND with search and the 공시 switch, the table keeps only those rows), the chips let go off the
           stock maps (해외) and are not remembered, a focused chip keeps focus over a quotes refresh
  lit      a lit chip puts THAT kind's mark in front on every lit stock's plate (연속 순매도 = 외 · 기 in inverted neutral ink + a down
           tick, 시장 경보 = the --g-al diamond), tiles too small for a plate get a 2–6px corner square, nothing left blank, unlit plates
           unchanged, the table and aria follow, chips off → normal; counts: chip = lit = this map, "· N종목 밝게 · 지도 밖 M" (종목 수 · zoom)
  views    tooltip lines (wording of the draft, the pace line, the note), the phone quick view (a 수급 line opens the stock page's
           투자자 tab), the table marks (two + "외 N", their own line under 430px), the tile / row aria tails before the 공시 tail
  themes   four themes × 360 · 1280: no element past the screen, the chip line fits, plate and chip ink neutral; map top 390 × 844 247,
           1280 · 1440 207; console errors 0 (a 404 for close.json — by design — aside)
  perf     render time with badges vs without (600 tiles, and 2,700 under 전체)
  snapshot dist/index.html: marks embedded when web/marks.json exists (then the snapshot's own day is the evening rule)
Screenshots go to --shots (default /tmp/badges_shots). Exit 1 on a fail.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import scenes as SC   # noqa: E402

PORT = int(os.environ.get('BADGES_QA_PORT', 9125))
assert 9125 <= PORT <= 9129, 'ports 9125–9129 (default 9125)'
URL = f'http://127.0.0.1:{PORT}/'
NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
ONLY = set(next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--only=')), 'rules,plate,legend,lit,views,themes,perf,snapshot').split(','))
SHOTS = pathlib.Path(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--shots' and i + 1 < len(sys.argv)), '/tmp/badges_shots'))
SHOTS.mkdir(parents=True, exist_ok=True)
D3 = (ROOT / 'src/vendor/d3-7.9.0.min.js').read_bytes()
FONT = (ROOT / 'src/fonts/PretendardVariable-subset.woff2').read_bytes()
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  [{str(detail)[:500]}]'), flush=True)


def post_scene(kind, extra=None):
    body = SC.scene(kind)
    if extra:
        body.update(extra)
    NP.open(urllib.request.Request(URL + '__scene', data=json.dumps(body).encode(), method='POST', headers={'content-type': 'application/json'})).read()


ERRS = []


def open_page(br, w, h, theme='base', market='K', store=None, wait=2600, tag=''):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    ctx.route('https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js', lambda r: r.fulfill(status=200, body=D3, headers={'content-type': 'application/javascript'}))
    ctx.route('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@*/**', lambda r: r.fulfill(status=200, body=b"@font-face{font-family:'Pretendard Variable';src:url(/__font.woff2)}", headers={'content-type': 'text/css'}))
    ctx.route('**/__font.woff2', lambda r: r.fulfill(status=200, body=FONT, headers={'content-type': 'font/woff2'}))
    st = {'theme': theme, 'motion': 'reduced', 'tickerPaused': True, 'market': market}
    st.update(store or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    t = tag or f'{w}/{theme}/{market}'

    def on_console(m):
        if m.type != 'error':
            return
        loc = (m.location or {}).get('url', '')
        if 'Failed to load resource' in m.text and any(k in loc for k in ('/data/close.json', '/data/marks.json', '/data/flows.json', '/data/alerts.json')):
            return    # close.json: 404 by design (the live quotes stay what is drawn); marks / flows / alerts: the 404 scenes
        ERRS.append(f'{t}: {m.text[:160]} {loc}')
    pg.on('console', on_console)
    pg.on('pageerror', lambda e: ERRS.append(f'{t} pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_timeout(wait)
    return ctx, pg


def tile_center(pg, code):
    return pg.evaluate(f"(() => {{ const e = document.querySelector('#map .tile[data-c=\"{code}\"]'); if (!e) return null; const r = e.getBoundingClientRect(); return [r.x + Math.min(r.width / 2, 40), r.y + Math.min(r.height / 2, 30)]; }})()")


def badge(pg, code):
    """KH.marks.badge(code): the map's facts — null for a stock with no kind (a short streak or a pace is tooltip text only)"""
    return pg.evaluate(f"KH.marks.badge('{code}')")


def tip_text(pg, code):
    c = tile_center(pg, code)
    if not c:
        return None
    pg.mouse.move(c[0], c[1]); pg.wait_for_timeout(450)
    t = pg.evaluate("(() => { const s = document.querySelector('#tip.show .sg'); return s ? s.innerText.replace(/\\s+/g, ' ').trim() : null; })()")
    pg.mouse.move(2, 2); pg.wait_for_timeout(250)
    return t


# ───────────────────────── rules ─────────────────────────
def rules(br):
    post_scene('next')
    ctx, pg = open_page(br, 1440, 900)
    info = pg.evaluate('KH.marks.badgeInfo()')
    check('next: the file of the weekday before counts (mode next, flows of PREV, session S)', info['mode'] == 'next' and info['flows'] == SC.iso(SC.PREV) and info['session'] == SC.iso(SC.S) and info['shown'], info)
    B = {c: badge(pg, c) for c in (SC.HI, SC.LO, SC.V1, SC.V3, SC.NOV, SC.SMALLTV, SC.RIGHTS, SC.STALE, SC.YOUNG, SC.LISTED, SC.SELL, SC.FLOW5, SC.FLOW20, SC.ALERT, SC.NXHI, SC.LIMU, SC.PACE)}
    P = {c: [g['k'] + str(g.get('tier', '')) + g.get('who', '') for g in (b or {}).get('plate', [])] for c, b in B.items()}
    K = {c: sorted((b or {}).get('kinds', [])) for c, b in B.items()}
    check('next: 신고가 + 급증 5.3× (tier 2) + 외국인 9일 → the plate [신고, 막대 2, 외] in that order', P[SC.HI] == ['hi', 'vol2', 'flow외'], P[SC.HI])
    check('next: 신저가 + 기관 7일 → [신저, 기]', P[SC.LO] == ['lo', 'flow기'], P[SC.LO])
    check('next: 급증 tiers — 3.2× → 막대 1, 12× → 막대 3 (+ 외 · 기 8일 → 외기)', P[SC.V1] == ['vol1'] and P[SC.V3] == ['vol3', 'flow외기'], (P[SC.V1], P[SC.V3]))
    check('next: 2.9× → no badge; 5× but under 10억 → no badge', not K[SC.NOV] and not K[SC.SMALLTV], (K[SC.NOV], K[SC.SMALLTV]))
    check('next: no 신고 · 신저 for a stale row, a listing 3 days old, a base price under lo52 (권리락 day)', not K[SC.STALE] and not K[SC.YOUNG] and not K[SC.RIGHTS], (K[SC.STALE], K[SC.YOUNG], K[SC.RIGHTS]))
    check('next: the facts are KRX — an NXT high above hi52 does not make a 신고가', not K[SC.NXHI], K[SC.NXHI])
    check('next: a listing 60 days old → "상장 후 신고가"', K[SC.LISTED] == ['hi'] and '상장 후 신고가' in B[SC.LISTED]['aria'], B[SC.LISTED])
    check('next: 연속 순매도 8일 → kind sell only (no plate); 시장 경보 → kind alert only', K[SC.SELL] == ['sell'] and not P[SC.SELL] and K[SC.ALERT] == ['alert'] and not P[SC.ALERT], (B[SC.SELL], B[SC.ALERT]))
    check('next: 5일 연속 → no plate (a line only); 기관 20 = sw → "20일 이상"', not P[SC.FLOW5] and P[SC.FLOW20] == ['flow기'] and '기관 20일 이상 연속 순매수' in B[SC.FLOW20]['aria'], (B[SC.FLOW5], B[SC.FLOW20]))
    check('next: aria tail = the plate kinds in words', B[SC.HI]['aria'] == ', 52주 신고가, 거래대금 20일 평균의 5.3배, 외국인 9일 연속 순매수'
          and B[SC.V3]['aria'] == ', 거래대금 20일 평균의 12.0배, 외국인 8일 연속 순매수, 기관 8일 연속 순매수', (B[SC.HI]['aria'], B[SC.V3]['aria']))
    t = tip_text(pg, SC.HI)
    check('next: tooltip lines — 52주 신고가 (이전 고가 · date), 거래대금 지금까지 … · 이 속도면 하루 N배쯤, 외국인 9일 연속 순매수 · 누적, the note',
          t and '52주 신고가 (이전 고가 186,762원 · 10/2)' in t and '거래대금 지금까지 20일 평균의 5.3배 · 이 속도면 하루 8배쯤' in t
          and '외국인 9일 연속 순매수 · 누적 1,241억' in t and f'수급 {SC.md(SC.PREV)}까지 확정 · 시세 KRX 13:05 기준' in t, t)
    t = tip_text(pg, SC.PACE)
    check('next: under 3× so far but on pace → "거래대금 지금까지 20일 평균의 2.5배 · 이 속도면 하루 4배쯤" (text, no badge)',
          t == '거래대금 지금까지 20일 평균의 2.5배 · 이 속도면 하루 4배쯤 시세 KRX 13:05 기준' and not K[SC.PACE], t)
    t = tip_text(pg, SC.SELL)
    check('next: 순매도 line "외국인 8일 연속 순매도 · 누적 880억" (with its sell mark) + note', t and t.endswith(f'외국인 8일 연속 순매도 · 누적 880억 수급 {SC.md(SC.PREV)}까지 확정'), t)
    t = tip_text(pg, SC.FLOW5)
    check('next: a 5-day streak is a line without a mark', t == f'외국인 5일 연속 순매수 · 누적 86억 수급 {SC.md(SC.PREV)}까지 확정', t)
    # same-day replay: 연속 수급 only; another day: nothing
    pg.evaluate(f"KH.setReplay({{t: '1100', date: '{SC.iso(SC.S)}', prices: {{}}}})"); pg.wait_for_timeout(300)
    r1 = pg.evaluate("[KH.marks.badgeInfo().replay, KH.marks.badge('" + SC.HI + "'), [...document.querySelectorAll('#map .tile .bm')].length, [...document.querySelectorAll('#bgl .lgc:not([hidden])')].map(b => b.dataset.k)]")
    check('replay of the day: only 연속 수급 stays (no 신고 · 급증 — a frame has no high or value)', r1[0] == 'same' and [g['k'] for g in r1[1]['plate']] == ['flow'] and sorted(r1[3]) == ['alert', 'buy', 'sell'], r1)
    pg.evaluate(f"KH.setReplay({{t: '1100', date: '{SC.iso(SC.OLD)}', prices: {{}}}})"); pg.wait_for_timeout(300)
    r2 = pg.evaluate("[KH.marks.badgeInfo().replay, KH.marks.badge('" + SC.HI + "'), document.querySelectorAll('#map .tile .bm').length, document.getElementById('bgl').hidden, document.getElementById('map').querySelector('.tile[data-c=\"" + SC.HI + "\"]').getAttribute('aria-label')]")
    check('replay of another day: no badge, no plate, no chip line, no aria tail', r2[0] == 'other' and r2[1] is None and r2[2] == 0 and r2[3] and '신고가' not in r2[4], r2)
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(300)
    check('replay off: the plates come back', pg.evaluate("document.querySelectorAll('#map .tile .bm').length") > 0)
    ctx.close()

    post_scene('early')
    ctx, pg = open_page(br, 1440, 900)
    t1, t2 = tip_text(pg, SC.HI), tip_text(pg, SC.PACE)
    check('09:20: no pace yet — "거래대금 지금까지 20일 평균의 5.3배 · 지금까지 530억", and no line for a stock under 3×',
          t1 and '거래대금 지금까지 20일 평균의 5.3배 · 지금까지 530억' in t1 and '속도' not in t1 and t2 is None, (t1, t2))
    ctx.close()

    post_scene('eve')
    ctx, pg = open_page(br, 1440, 900)
    info = pg.evaluate('KH.marks.badgeInfo()')
    B = {c: badge(pg, c) for c in (SC.HI, SC.LO, SC.EVE_VOL, SC.STALE, SC.YOUNG, SC.NXHI, SC.LISTED)}
    check('eve: the file of today → mode eve; 신고가 · 신저가 = hiDate · loDate = asOf', info['mode'] == 'eve' and 'hi' in B[SC.HI]['kinds'] and 'lo' in B[SC.LO]['kinds']
          and not (B[SC.STALE] or {}).get('kinds') and not (B[SC.YOUNG] or {}).get('kinds') and 'hi' not in (B[SC.NXHI] or {}).get('kinds', []) and '상장 후 신고가' in B[SC.LISTED]['aria'], (info, B))
    check('eve: 급증 against the 19 days before today — 320 vs tv20 111 (today inside) = 3.2× (raw 2.9×)', B[SC.EVE_VOL] and B[SC.EVE_VOL]['plate'] == [{'k': 'vol', 'tier': 1}] and '3.2배' in B[SC.EVE_VOL]['aria'], B[SC.EVE_VOL])
    t = tip_text(pg, SC.HI)
    check('eve: tooltip "52주 신고가 (오늘 고가 …원)", "거래대금 20일 평균의 …배 · 오늘 530억", no pace', t and '52주 신고가 (오늘 고가 192,255원)' in t and '· 오늘 530억' in t and '속도' not in t, t)
    ctx.close()

    post_scene('old')
    ctx, pg = open_page(br, 1440, 900)
    info = pg.evaluate('KH.marks.badgeInfo()')
    check('old files (two weekdays back): no 신고 · 신저 · 급증 · 수급 — only 시장 경보 (its own fresh file)', info['mode'] is None and info['flows'] is None
          and {k: v for k, v in info['counts'].items() if v} == {'alert': 2} and pg.evaluate("document.querySelectorAll('#map .tile .bm').length") == 0, info)
    ctx.close()

    post_scene('404')
    ctx, pg = open_page(br, 1440, 900)
    info = pg.evaluate('KH.marks.badgeInfo()')
    b = badge(pg, SC.HI)
    check('no marks.json (404): no 신고 · 신저 · 급증; 연속 수급 still on the plate', info['marks'] is None and info['mode'] is None and b['plate'] == [{'k': 'flow', 'who': '외'}]
          and pg.evaluate("[...document.querySelectorAll('#bgl .lgc')].filter(b => !b.hidden).map(b => b.dataset.k).sort().join()") == 'alert,buy,sell', (info, b))
    ctx.close()

    post_scene('pre')
    ctx, pg = open_page(br, 1440, 900)
    info = pg.evaluate('KH.marks.badgeInfo()')
    b = badge(pg, SC.HI)
    check('before 09:00 (KRX not open yet): no 신고 · 신저 · 급증; 연속 수급 (through the day before) stays', info['pre'] and info['mode'] is None and info['flows'] == SC.iso(SC.PREV) and b['plate'] == [{'k': 'flow', 'who': '외'}], (info, b))
    ctx.close()


# ───────────────────────── plate geometry ─────────────────────────
PLATE_JS = r"""() => {
  const out = [], map = document.getElementById('map').getBoundingClientRect();
  const R = e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const hit = (a, b) => a && b && a.x < b.r - 0.5 && b.x < a.r - 0.5 && a.y < b.b - 0.5 && b.y < a.b - 0.5;
  for (const t of document.querySelectorAll('#map .tile[data-c]')) {
    const bm = t.querySelector(':scope > .bm');
    const g = t.__g || [0, 0, t.offsetWidth, t.offsetHeight], w = g[2], hh = g[3], m = Math.min(w, hh);
    const b = KH.marks.badge(t.dataset.c), plan = b ? b.plate : [];
    const dm = t.querySelector(':scope > .dm'), lim = t.querySelector(':scope > .lim:not([hidden])');
    const px = t.querySelector('.lab:not([hidden]) .px:not([hidden])'), mc = t.querySelector('.lab:not([hidden]) .mc:not([hidden])');
    const fold = dm ? parseFloat(dm.style.getPropertyValue('--s')) || 0 : 0;
    // the A rules, written again here: size and how many by the short side, then as many as fit left of the fold
    let exp = [], s = 0;
    if (plan.length && m >= 12) {
      s = m < 20 ? 9 : m < 40 ? 11 : m < 64 ? 13 : 14; const max = m < 20 ? 1 : m < 40 ? 2 : 3, pad = s >= 13 ? 2 : 1, gap = pad, fs = Math.round(s * 0.76);
      let width = pad * 2; const room = w - (fold ? fold + 2 : 0) - 2;
      for (const x of plan) { if (exp.length >= max) break; const add = (x.k === 'flow' ? Math.ceil(fs * 0.98 * x.who.length) : s - 2) + (exp.length ? gap : 0); if (width + add > room) break; exp.push(x); width += add; }
    }
    if (!bm && !exp.length) continue;
    const tr = R(t), br = bm ? R(bm) : null, kids = bm ? [...bm.children].map(k => k.tagName === 'B' ? 'flow' + k.textContent : (k.style.getPropertyValue('--m').match(/--g-(\w+)/) || [])[1]) : [];
    const want = exp.map(x => x.k === 'flow' ? 'flow' + x.who : x.k === 'vol' ? 'v' + x.tier : x.k);
    const cs = bm ? getComputedStyle(bm) : null;
    out.push({ c: t.dataset.c, w, hh, m, s, size: br ? Math.round(br.h) : 0, n: kids.length, kids, want, limd: t.classList.contains('limd'),
      inside: !br || (br.x >= tr.x - 0.5 && br.r <= tr.r + 0.5 && br.y >= tr.y - 0.5 && br.b <= tr.b + 0.5),
      corner: !br || (Math.abs(br.x - tr.x) < 0.6 && Math.abs(tr.b - br.b - (t.classList.contains('limd') ? 3 : 0)) < 0.6),
      fold: hit(br, dm ? R(dm) : null), chip: hit(br, lim ? R(lim) : null), px: hit(br, px ? R(px) : null) || hit(br, mc ? R(mc) : null),
      ink: cs ? [cs.backgroundColor, cs.color] : null, pxShown: !!px });
  }
  const L = KH.layout().filter(t => t.badges);
  return { tiles: out, layout: L.map(t => [t.code, t.badges.s, t.badges.items.length, t.badges.w, t.badges.lift]) };
}"""


def plate(br):
    for (w, h) in ((1280, 800), (360, 740), (768, 1024)):
        post_scene('next')
        ctx, pg = open_page(br, w, h, store={'topN': 300})
        d = pg.evaluate(PLATE_JS)
        T = d['tiles']
        drawn = [t for t in T if t['n']]
        check(f'{w}: plates drawn ({len(drawn)} tiles; sizes {sorted({t["size"] for t in drawn})})', len(drawn) >= 5, len(drawn))
        bad = [t for t in T if t['kids'] != t['want']]
        check(f'{w}: every plate = the A plan (size by the short side, 12 → 1 · 20 → 2 · 40 → 3, priority order, room left of the fold)', not bad, bad[:4])
        bad = [t for t in drawn if t['size'] != t['s']]
        check(f'{w}: plate height 9 · 11 · 13 · 14 by the short side', not bad, [(t['c'], t['m'], t['size'], t['s']) for t in bad[:4]])
        ladder = {}
        for t in drawn:
            ladder.setdefault('<20' if t['m'] < 20 else '<40' if t['m'] < 40 else '40+', set()).add(t['n'])
        check(f'{w}: count ladder by short side (seen) {dict((k, sorted(v)) for k, v in sorted(ladder.items()))} — never more than 1 · 2 · 3',
              max(ladder.get('<20', {0})) <= 1 and max(ladder.get('<40', {0})) <= 2 and max(ladder.get('40+', {0})) <= 3, ladder)
        check(f'{w}: no plate under 12px', all(t['m'] >= 12 for t in drawn))
        bad = [t['c'] for t in drawn if not t['inside'] or not t['corner']]
        check(f'{w}: plates inside their tile at the bottom-left corner (3px up over a 하한가 bar)', not bad, bad[:6])
        bad = [t['c'] for t in drawn if t['fold']]
        nfold = pg.evaluate("[...document.querySelectorAll('#map .tile > .bm')].filter(b => b.parentElement.querySelector(':scope > .dm')).length")
        check(f'{w}: no plate over the 공시 fold ({nfold} tiles carry both)', not bad and nfold >= 1, (bad[:6], nfold))
        bad = [t['c'] for t in drawn if t['chip']]
        check(f'{w}: no plate over the 상 · 하 chip', not bad, bad)
        bad = [t['c'] for t in drawn if t['px']]
        check(f'{w}: the price / 시총 line never under the plate', not bad, bad[:6])
        bad = [t for t in drawn if t['ink'] != ['rgba(0, 0, 0, 0.62)', 'rgb(255, 255, 255)']]
        check(f'{w}: plate ink neutral (the 상 · 하 chip\'s --badge-bg · --badge-fg)', not bad, [t['ink'] for t in bad[:3]])
        lay = {c: (s, n, ww, lift) for c, s, n, ww, lift in d['layout']}
        bad = [t['c'] for t in drawn if t['c'] not in lay or lay[t['c']][0] != t['size'] or lay[t['c']][1] != t['n']]
        check(f'{w}: KH.layout() tiles carry the plate as drawn (badges {{s, items, w, lift}}) for the image save', not bad and len(lay) == len(drawn), bad[:4])
        shown_with = {t['c']: t['pxShown'] for t in T}
        withp = {t['c'] for t in drawn}
        pg.screenshot(path=str(SHOTS / f'plate_{w}.png'))
        ctx.close()
        post_scene('none')
        ctx, pg = open_page(br, w, h, store={'topN': 300})
        before = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#map .tile[data-c]')].map(t => [t.dataset.c, !!t.querySelector('.lab:not([hidden]) .px:not([hidden])')]))")
        nob = pg.evaluate("document.querySelectorAll('#map .tile .bm').length")
        ctx.close()
        dropped = [c for c in withp if before.get(c) and not shown_with.get(c)]
        kept = [c for c in withp if before.get(c) and shown_with.get(c)]
        check(f'{w}: without badges no plate; with them the price line goes only for a plate (dropped {len(dropped)}, kept {len(kept)})', nob == 0, (nob, dropped[:5]))
        if w == 1280:
            check(f'1280: {SC.DROP}\'s price line (5px over the bottom, without badges) gives way to its plate — the 상 · 하 chip rule',
                  SC.DROP in dropped and SC.DROP in withp, (dropped, kept))


# ───────────────────────── legend chips ─────────────────────────
def legend(br):
    post_scene('next')
    ctx, pg = open_page(br, 1440, 900)
    d = pg.evaluate("""() => {
      const cnt = {hi: 0, lo: 0, vol: 0, buy: 0, sell: 0, alert: 0};
      for (const c of KH.mapCodes()) { const b = KH.marks.badge(c); if (b) for (const k of b.kinds) cnt[k]++; }
      const chips = Object.fromEntries([...document.querySelectorAll('#bgl .lgc')].map(b => [b.dataset.k, b.hidden ? 0 : +b.querySelector('.n').textContent.replace(/,/g, '')]));
      return { cnt, chips, labels: [...document.querySelectorAll('#bgl .lgc')].map(b => b.getAttribute('aria-label')), order: [...document.querySelectorAll('#bgl .lgc')].map(b => b.dataset.k) };
    }""")
    check('legend: chip counts = the map\'s stocks with that kind', d['cnt'] == d['chips'] and all(d['cnt'].values()), d)
    check('legend: chips 신고가 · 신저가 · 거래 급증 · 연속 순매수 · 연속 순매도 · 시장 경보, named "… 종목만 지도에서 밝게, N종목"',
          d['order'] == ['hi', 'lo', 'vol', 'buy', 'sell', 'alert'] and d['labels'][0] == f"신고가 종목만 지도에서 밝게, 이 지도에서 {d['chips']['hi']}종목", d['labels'])
    lit_js = """() => { const t = [...document.querySelectorAll('#map .tile[data-c]')]; return { dim: t.filter(e => e.classList.contains('mdim')).map(e => e.dataset.c), all: t.map(e => e.dataset.c),
      lit: document.querySelector('#bgl .lit').textContent, pressed: [...document.querySelectorAll('#bgl .lgc[aria-pressed="true"]')].map(b => b.dataset.k) }; }"""
    pg.click('#bgl .lgc[data-k="hi"]'); pg.wait_for_timeout(250)
    s = pg.evaluate(lit_js)
    want = {c for c in s['all'] if 'hi' in ((badge(pg, c) or {}).get('kinds') or [])}
    check(f'chip 신고가: only those {len(want)} stocks stay bright (.mdim on the rest), "· N종목 밝게"', set(s['all']) - set(s['dim']) == want and s['pressed'] == ['hi'] and s['lit'] == f'· {len(want)}종목 밝게', (len(want), s['lit'], s['pressed']))
    pg.click('#bgl .lgc[data-k="sell"]'); pg.wait_for_timeout(250)
    s = pg.evaluate(lit_js)
    want2 = {c for c in s['all'] if {'hi', 'sell'} & set((badge(pg, c) or {}).get('kinds') or [])}
    check('chips 신고가 + 연속 순매도: any of them stays bright (a 순매도 stock is not drawn on the plate but lights)', set(s['all']) - set(s['dim']) == want2 and SC.SELL in want2, (len(want2),))
    # AND with search: 삼성 → the search dims the others (.dim), the chips keep .mdim on theirs
    pg.fill('#q', '삼성'); pg.wait_for_timeout(400)
    a = pg.evaluate(f"(() => {{ const g = c => document.querySelector('#map .tile[data-c=\"' + c + '\"]'); return [g('{SC.HI}').className, g('{SC.SELL}').className, g('{SC.LO}').className, g('{SC.NOV}').className]; }})()")
    check('AND with search: 삼성전자 (신고가, matches) bright · 삼성물산 (순매도, matches) bright · SK하이닉스 (no match) dim · 삼성SDI (match, no kind) mdim',
          'dim' not in a[0].split() and 'mdim' not in a[0].split() and 'mdim' not in a[1].split() and 'dim' not in a[1].split() and 'dim' in a[2].split() and 'mdim' in a[3].split(), a)
    pg.fill('#q', ''); pg.wait_for_timeout(300)
    # AND with the 공시 switch: only stocks with a filing and a pressed kind stay bright
    pg.evaluate("KH.marks.only('disc')"); pg.wait_for_timeout(200)
    s = pg.evaluate(lit_js)
    disc = set(pg.evaluate("[...(KH.marks.get('disc') || new Map()).keys()]"))
    check('AND with the 공시 switch (KH.marks.only): bright = a filing and a pressed kind', set(s['all']) - set(s['dim']) == (want2 & disc), (sorted(set(s['all']) - set(s['dim'])), sorted(want2 & disc)))
    pg.evaluate("KH.marks.only(null)"); pg.wait_for_timeout(200)
    # the table keeps only those rows
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(500)
    rows = pg.evaluate("[...document.querySelectorAll('#tablewrap tbody tr[data-c]')].map(r => r.dataset.c)")
    check('table view: only the rows of the pressed kinds', set(rows) == want2, (len(rows), len(want2)))
    pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(500)
    # a focused chip keeps the focus over a quotes refresh (chips are written in place)
    pg.focus('#bgl .lgc[data-k="vol"]')
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(900)
    check('a focused chip keeps focus over a quotes refresh', pg.evaluate("document.activeElement && document.activeElement.dataset.k") == 'vol')
    # 전체 keeps them (the same stocks are on that map); 해외 lets go; back on 코스피 nothing is dimmed
    pg.click('.tabs button[data-mkt="ALL"]'); pg.wait_for_timeout(700)
    keep = pg.evaluate("KH.marks.litKinds()")
    pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(700)
    gone = pg.evaluate("[KH.marks.litKinds(), document.getElementById('bgl').hidden]")
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(900)
    back = pg.evaluate("[KH.marks.litKinds(), document.querySelectorAll('#map .tile.mdim').length, [...document.querySelectorAll('#bgl .lgc[aria-pressed=\"true\"]')].length]")
    check('chips: kept on 코스피 → 전체, let go on 해외 (line hidden), nothing dimmed back on 코스피', sorted(keep) == ['hi', 'sell'] and gone == [[], True] and back == [[], 0, 0], (keep, gone, back))
    pg.click('#bgl .lgc[data-k="vol"]'); pg.wait_for_timeout(200)
    ctx.close()
    ctx, pg = open_page(br, 1440, 900)
    check('chips are not remembered (a reload starts with none pressed, nothing dimmed)', pg.evaluate("[KH.marks.litKinds().length, document.querySelectorAll('#map .tile.mdim').length]") == [0, 0])
    ctx.close()


# ───────────────────────── lit chips → marks on every lit stock (사용자 2026-11-23 "배지 표시가 다 안나오는데?") ─────────────────────────
LIT_JS = r"""(k) => {
  const key = g => g.k === 'flow' ? 'flow' + g.who : g.k === 'sell' ? 'sell' + g.who : g.k === 'vol' ? 'v' + g.tier : g.k;
  const out = { lit: 0, plate: 0, tick: 0, none: [], front: [], tickBad: [], unlitOdd: [] };
  for (const t of document.querySelectorAll('#map .tile[data-c]')) {
    const b = KH.marks.badge(t.dataset.c), has = !!b && b.kinds.includes(k);
    const bm = t.querySelector(':scope > .bm'), bk = t.querySelector(':scope > .bmk'), g = t.__g, m = Math.min(g[2], g[3]);
    const kids = bm ? [...bm.children].map(x => x.tagName === 'B' ? (x.classList.contains('sl') ? 'sell' : 'flow') + x.textContent : (x.style.getPropertyValue('--m').match(/--g-(\w+)/) || [])[1]) : [];
    if (!has) { if (bk || kids.some(x => x === 'al' || /^sell/.test(x))) out.unlitOdd.push(t.dataset.c); continue; }
    out.lit++;
    if (bm) { out.plate++; const want = key(b.now[0]); if (kids[0] !== want || !(k === 'buy' ? /^flow/.test(want) : k === 'sell' ? /^sell/.test(want) : k === 'alert' ? want === 'al' : k === 'vol' ? /^v\d/.test(want) : want === k)) out.front.push([t.dataset.c, kids, want]); }
    else if (bk) {
      out.tick++;
      const r = bk.getBoundingClientRect(), tr = t.getBoundingClientRect(), s = r.width, dm = t.querySelector(':scope > .dm');
      const dr = dm && dm.getBoundingClientRect(), over = dr && r.right > dr.left + 0.5 && r.bottom > dr.top + 0.5;
      if (s < 2 || s > 6 || r.left < tr.left - 0.5 || r.bottom > tr.bottom + 0.5 || r.right > tr.right + 0.5 || over || getComputedStyle(bk).backgroundColor !== 'rgb(255, 255, 255)') out.tickBad.push([t.dataset.c, s]);
    } else if (m >= 3) out.none.push([t.dataset.c, Math.round(g[2]), Math.round(g[3])]);
  }
  return out;
}"""


def lit(br):
    post_scene('next')
    for (w, h) in ((1280, 800), (360, 740)):
        ctx, pg = open_page(br, w, h)
        for k in ('hi', 'lo', 'vol', 'buy', 'sell', 'alert'):
            pg.evaluate(f"KH.marks.lit(['{k}'])"); pg.wait_for_timeout(150)
            r = pg.evaluate(LIT_JS, k)
            check(f'{w} lit {k}: every lit stock shows it — {r["plate"]} plates with {k} in front, {r["tick"]} corner ticks (of {r["lit"]}); none left blank, unlit plates unchanged',
                  r['lit'] > 0 and not r['none'] and not r['front'] and not r['tickBad'] and not r['unlitOdd'], {x: r[x][:4] for x in ('none', 'front', 'tickBad', 'unlitOdd')})
            if w == 360 and k == 'vol':
                check('360 lit 거래 급증: tiles too small for a plate get the corner tick', r['tick'] >= 3, r['tick'])
                pg.screenshot(path=str(SHOTS / 'lit_vol_360.png'))
            if w == 1280 and k == 'sell':
                ink = pg.evaluate(f"(() => {{ const b = document.querySelector('#map .tile[data-c=\"{SC.SELL}\"] .bm > b.sl'); if (!b) return null; const c = getComputedStyle(b), a = getComputedStyle(b, '::after'); return [b.textContent, c.backgroundColor, c.color, a.borderTopStyle, a.borderTopColor]; }})()")
                check('1280 lit 연속 순매도: the 외 letters in inverted neutral ink with a down tick (white box, black ink — no green)',
                      ink and ink[0] == '외' and ink[1] == 'rgb(255, 255, 255)' and ink[2] == 'rgb(0, 0, 0)' and ink[3] == 'solid' and ink[4] == 'rgb(0, 0, 0)', ink)
                al = pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{SC.SELL}\"]').getAttribute('aria-label')")
                check('lit 연속 순매도: the tile aria tail says it (", 외국인 8일 연속 순매도")', ', 외국인 8일 연속 순매도' in al, al)
                pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(500)
                tm = pg.evaluate(f"(() => {{ const m = document.querySelector('#tablewrap tr[data-c=\"{SC.SELL}\"] .mks'); return m ? [m.firstElementChild.className, m.textContent] : null; }})()")
                check('lit 연속 순매도: the table row shows the sell mark first', tm and 'sl' in tm[0].split() and tm[1].startswith('외'), tm)
                pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(500)
                pg.screenshot(path=str(SHOTS / 'lit_sell_1280.png'))
            if w == 1280 and k == 'alert':
                pg.screenshot(path=str(SHOTS / 'lit_alert_1280.png'))
        pg.evaluate("KH.marks.lit(null)"); pg.wait_for_timeout(150)
        off = pg.evaluate("[document.querySelectorAll('#map .tile .bmk').length, document.querySelectorAll('#map .tile .bm > b.sl').length, [...document.querySelectorAll('#map .tile .bm > i')].filter(i => /--g-al/.test(i.style.getPropertyValue('--m'))).length, document.querySelector('#map .tile[data-c=\"" + SC.SELL + "\"]').getAttribute('aria-label')]")
        check(f'{w} chips off: plates back to normal — no tick, no sell or alert mark, no 순매도 aria words', off[:3] == [0, 0, 0] and '순매도' not in off[3], off)
        ctx.close()
    # the chip marks for 연속 순매도 · 시장 경보 (the marks a lit chip draws)
    ctx, pg = open_page(br, 1280, 800)
    cm = pg.evaluate("['sell', 'alert'].map(k => { const m = document.querySelector('#bgl .lgc[data-k=\"' + k + '\"] .bmc'); return m ? [m.className, m.textContent, m.querySelector('i') ? m.querySelector('i').style.getPropertyValue('--m') : ''] : null; })")
    check('legend: the 연속 순매도 chip carries the sell mark, 시장 경보 the alert diamond', cm[0] and 'sl' in cm[0][0].split() and cm[0][1] == '외' and cm[1] and '--g-al' in cm[1][2], cm)
    # counts: chips = this map; a lit chip says how many more there are off it (종목 수 · zoom)
    ctx.close()
    for top, zoom in ((300, None), (100, None), (300, '정보기술')):
        ctx, pg = open_page(br, 1280, 800, store={'topN': top})
        if zoom:
            pg.evaluate(f"(() => {{ const b = document.querySelector('#map .sec[data-s=\"{zoom}\"] .hd'); if (b) b.click(); }})()"); pg.wait_for_timeout(700)
        pg.click('#bgl .lgc[data-k="vol"]'); pg.wait_for_timeout(400)
        d = pg.evaluate("""() => { const map = new Set(KH.mapCodes()), focus = [...document.querySelectorAll('#map .tile[data-c]')].map(t => t.dataset.c), on = new Set(focus);
          const has = c => { const b = KH.marks.badge(c); return !!b && b.kinds.includes('vol'); };
          const pool = KH.stocks().filter(s => s.m === 'K' && s.c.slice(-1) === '0');
          return { info: KH.marks.badgeInfo(), text: document.querySelector('#bgl .lit').textContent, chip: +document.querySelector('#bgl .lgc[data-k="vol"] .n').textContent.replace(/,/g, ''),
            onMap: focus.filter(has).length, off: pool.filter(s => !on.has(s.c) && has(s.c)).length }; }""")
        want = f"· {d['onMap']}종목 밝게" + (f" · 지도 밖 {d['off']}" if d['off'] else '')
        check(f'counts {top}{" · " + zoom + " 확대" if zoom else ""}: chip = lit = the tiles on this map ({d["onMap"]}); "지도 밖" = the rest of the market\'s stocks ({d["off"]}) — "{d["text"]}"',
              d['chip'] == d['onMap'] == d['info']['litN'] and d['info']['litOff'] == d['off'] and d['text'] == want and ((top == 300 and not zoom) == (d['off'] == 0)), d)
        ctx.close()


# ───────────────────────── tooltip · quick view · table · aria ─────────────────────────
def views(br):
    post_scene('next')
    ctx, pg = open_page(br, 1440, 900)
    al = pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{SC.HI}\"]').getAttribute('aria-label')")
    check('tile aria-label: the badge tail before the 공시 tail', ', 52주 신고가, 거래대금 20일 평균의 5.3배, 외국인 9일 연속 순매수, 오늘 공시 1건' in al, al)
    c = tile_center(pg, SC.HI); pg.mouse.move(c[0], c[1]); pg.wait_for_timeout(450)
    tip = pg.evaluate("(() => { const t = document.getElementById('tip'), sg = t.querySelector('.sg'), dsc = t.querySelector('.dsc'), head = t.querySelector('.card-head'); return { order: sg && dsc ? !!(sg.compareDocumentPosition(dsc) & 4) : null, after: sg ? sg.previousElementSibling === head : null, marks: sg ? sg.querySelectorAll('.sgr .mk .bmc').length : 0, rows: sg ? sg.querySelectorAll('.sgr').length : 0 }; })()")
    check('tooltip: the badge block right under the head, above the 공시 block; marks on the three plate lines', tip == {'order': True, 'after': True, 'marks': 3, 'rows': 3}, tip)
    pg.locator('#tip').screenshot(path=str(SHOTS / 'tip_1440.png'))
    pg.mouse.move(2, 2); pg.wait_for_timeout(300)
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(600)
    t = pg.evaluate(f"""(() => {{ const r = c => document.querySelector('#tablewrap tr[data-c="' + c + '"]');
      const m = c => {{ const x = r(c); const k = x && x.querySelector('.mks'); return k ? [k.querySelectorAll('.bmc').length, (k.querySelector('.almore') || {{}}).textContent || ''] : null; }};
      return {{ hi: m('{SC.HI}'), lo: m('{SC.LO}'), v1: m('{SC.V1}'), nov: m('{SC.NOV}'), sell: m('{SC.SELL}'), aria: r('{SC.HI}').getAttribute('aria-label'), title: r('{SC.HI}').querySelector('.mks').title }}; }})()""")
    check('table: two marks + "외 1" for three, two for two, one for one, none for none / 순매도 only', t['hi'] == [2, '외 1'] and t['lo'] == [2, ''] and t['v1'] == [1, ''] and t['nov'] is None and t['sell'] is None, t)
    check('table: row aria-label tail (badges before 공시) and the marks\' title', ', 52주 신고가, 거래대금 20일 평균의 5.3배, 외국인 9일 연속 순매수, 오늘 공시 1건' in t['aria']
          and t['title'] == '52주 신고가 · 거래대금 20일 평균의 5.3배 · 외국인 9일 연속 순매수', t)
    pg.screenshot(path=str(SHOTS / 'table_1440.png'))
    ctx.close()
    # phones: the table marks get their own line; the quick view's 수급 line opens the 투자자 tab
    ctx, pg = open_page(br, 390, 844)
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(600)
    g = pg.evaluate(f"""(() => {{ const x = document.querySelector('#tablewrap tr[data-c="{SC.HI}"]'), n = x.querySelector('.nmt').getBoundingClientRect(), k = x.querySelector('.mks').getBoundingClientRect(), cell = x.querySelector('td').getBoundingClientRect();
      return [k.top >= n.bottom - 1, k.right <= cell.right + 0.5, k.left >= cell.left]; }})()""")
    check('390 table: the marks sit on their own line under the name, inside the cell', g == [True, True, True], g)
    pg.screenshot(path=str(SHOTS / 'table_390.png'))
    pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(600)
    pg.evaluate(r"""() => { window.__open = []; const K = window.KHStock; if (K) K.open = (c, opts) => { window.__open.push([c, opts && opts.tab, (new Error().stack || '').split('\n').slice(2, 5).join(' | ')]); return true; }; }""")
    c = tile_center(pg, SC.HI)
    pg.evaluate(f"document.querySelector('#map .tile[data-c=\"{SC.HI}\"]').scrollIntoView({{block: 'center'}})"); pg.wait_for_timeout(300)
    c = tile_center(pg, SC.HI)
    pg.mouse.click(c[0], c[1]); pg.wait_for_timeout(700)
    q = pg.evaluate("(() => { const s = document.querySelector('#sheet.open .sg'); if (!s) return null; const b = s.querySelector('button.sgr.act'); return { text: s.innerText.replace(/\\s+/g, ' ').trim(), act: s.querySelectorAll('button.sgr.act').length, label: b && b.getAttribute('aria-label'), h: b && b.getBoundingClientRect().height }; })()")
    check('quick view: the lines + the 수급 line as a 44px button "… — 종목 페이지 투자자 탭"', q and q['act'] == 1 and q['label'] == '외국인 9일 연속 순매수 누적 1,241억 — 종목 페이지 투자자 탭' and q['h'] >= 43.5 and '투자자 ›' in q['text'], q)
    pg.locator('#sheet').screenshot(path=str(SHOTS / 'quick_390.png'))
    pg.click('#sheet button.sgr.act'); pg.wait_for_timeout(400)
    op = pg.evaluate("window.__open")
    check('quick view: the 수급 line opens the stock page on 투자자 (KHStock.open(code, {tab: "inv"}))', [x[:2] for x in op] == [[SC.HI, 'inv']], op)
    ctx.close()


# ───────────────────────── themes × widths · map top · console ─────────────────────────
OVER = r"""() => {
  const vw = innerWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break; } p = p.parentElement; }
    if (!clipped) out.push((e.id || e.className || e.tagName).toString().slice(0, 40) + ' ' + Math.round(r.right));
  }
  return out.slice(0, 6);
}"""


def themes(br):
    post_scene('next')
    for th in THEMES:
        for (w, h) in ((360, 740), (1280, 800)):
            ctx, pg = open_page(br, w, h, theme=th)
            o = pg.evaluate(OVER)
            g = pg.evaluate("""() => { const b = document.getElementById('bgl'), r = b.getBoundingClientRect(), cs = [...b.querySelectorAll('.lgc:not([hidden])')];
              const mk = b.querySelector('.lgc .bmc'), m = mk ? getComputedStyle(mk) : null;
              return { shown: !b.hidden, right: Math.max(...cs.map(c => c.getBoundingClientRect().right)), w: innerWidth, chips: cs.length, h: Math.round(Math.max(...cs.map(c => c.getBoundingClientRect().height))),
                ink: m ? [m.backgroundColor, m.color] : null, plates: document.querySelectorAll('#map .tile .bm').length }; }""")
            check(f'{th} {w}: no element past the screen, the chip line fits ({g["chips"]} chips, {g["h"]}px), mark ink neutral, plates drawn',
                  not o and g['shown'] and g['right'] <= g['w'] and g['chips'] == 6 and g['ink'] == ['rgba(0, 0, 0, 0.62)', 'rgb(255, 255, 255)'] and g['plates'] > 0, (o, g))
            if th in ('base', 'glass-light'):
                pg.screenshot(path=str(SHOTS / f'map_{th}_{w}.png'), full_page=False)
                pg.evaluate("document.getElementById('bgl').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
                pg.locator('#legend').screenshot(path=str(SHOTS / f'legend_{th}_{w}.png'))
                pg.locator('#bgl').screenshot(path=str(SHOTS / f'chips_{th}_{w}.png'))
            ctx.close()
    for (w, h, top) in ((390, 844, 247), (1280, 800, 207), (1440, 900, 207)):
        ctx, pg = open_page(br, w, h)
        t = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY)")
        check(f'map top {w}×{h} = {top} (the chips sit under the map)', t == top, t)
        if w == 1440:
            fit = pg.evaluate("[Math.round(document.getElementById('bgl').getBoundingClientRect().bottom), innerHeight]")
            check('1440: the map still fits the screen with the chip line (its bottom within the viewport + 0)', fit[0] <= fit[1], fit)
        ctx.close()
    # the colour / size modes: badges are facts about the stock, so they stay under 기간 수익률 colours and 외국인 순매수 sizes
    for store, name in (({'colorBy': 'm1'}, '1개월 수익률 colours'), ({'sizeBy': 'fgn'}, '외국인 순매수 sizes')):
        ctx, pg = open_page(br, 1280, 800, store=store)
        n = pg.evaluate("[document.querySelectorAll('#map .tile .bm').length, document.getElementById('bgl').hidden, KH.marks.badgeInfo().shown]")
        check(f'{name}: the plates and chips stay ({n[0]} plates)', n[0] > 0 and n[1] is False and n[2], n)
        ctx.close()
    # the theme overview has no stock tiles: no plate, no chip line
    ctx, pg = open_page(br, 1280, 800, market='THEME')
    n = pg.evaluate("[document.querySelectorAll('#map .tile .bm').length, document.getElementById('bgl').hidden]")
    check('테마 overview: no plate, no chip line', n == [0, True], n)
    ctx.close()
    unk = json.loads(NP.open(URL + '__log').read())
    check('mock: every request the page made had an answer', not unk, unk[:6])


# ───────────────────────── performance ─────────────────────────
PERF_JS = """async () => { const t = []; for (let i = 0; i < 7; i++) { const a = performance.now(); KH.setReplay(null); t.push(performance.now() - a); await new Promise(r => requestAnimationFrame(() => setTimeout(r, 30))); }
  t.sort((a, b) => a - b); return { med: +t[3].toFixed(1), tiles: document.querySelectorAll('#map .tile').length, plates: document.querySelectorAll('#map .tile .bm').length }; }"""


def perf(br):
    """the badge code's own time per render (CDP sampling profile, 20 renders) on 300 and 2,700 tiles, and the wall time with vs
    without badges (medians — noisy: GC and the segment indicators move them by ±10 ms); the badge block reads no layout"""
    src = (ROOT / 'src/template.html').read_text(encoding='utf-8')
    blk = src[src.index('/* ───────────────── 지도 배지 (AGENTS §3-41 A안'):src.index('function bgFlowsAgain')]
    reads = [k for k in ('getBoundingClientRect', 'offsetWidth', 'offsetHeight', 'clientWidth', 'clientHeight', 'getComputedStyle', 'scrollWidth') if k in blk]
    check('perf: the badge code reads no layout (plates are built from the numbers the treemap already has)', not reads, reads)
    mine = {'bgCalc', 'badgeOf', 'tileBadge', 'bgCtx', 'bgOn', 'bgLegend', 'bgSyncChips', 'planPlate', 'paintPlate', 'badgeAria', 'alertKeys', 'bgLitHas', 'bgKinds', 'bgItems', 'bgItemOf', 'bgTick', 'bgPool'}
    allrows = [SC.krx(dict(r)) for r in SC.SNAP['stocks'] if r['c'] not in SC.BY]
    out = {}
    for kind in ('next', 'none'):
        for top in (300, 'all'):
            post_scene(kind, {'all': allrows})
            ctx, pg = open_page(br, 1440, 900, market='ALL', store={'topN': top}, wait=4000)
            wall = pg.evaluate(PERF_JS)
            cdp = ctx.new_cdp_session(pg)
            cdp.send('Profiler.enable'); cdp.send('Profiler.setSamplingInterval', {'interval': 100}); cdp.send('Profiler.start')
            pg.evaluate("async () => { for (let i = 0; i < 20; i++) { KH.setReplay(null); await new Promise(r => setTimeout(r, 10)); } }")
            prof = cdp.send('Profiler.stop')['profile']
            nodes = {n['id']: n['callFrame']['functionName'] for n in prof['nodes']}
            own = sum(d for sid, d in zip(prof['samples'], prof['timeDeltas']) if nodes[sid] in mine) / 1000 / 20
            out[(kind, top)] = dict(wall, own=round(own, 2))
            ctx.close()
    a, b, c, d = out[('next', 300)], out[('none', 300)], out[('next', 'all')], out[('none', 'all')]
    print(f'      {a["tiles"]} tiles: badge code {a["own"]} ms / render ({a["plates"]} plates; {b["own"]} ms with no badge data) · wall {a["med"]} vs {b["med"]} ms')
    print(f'      {c["tiles"]} tiles: badge code {c["own"]} ms / render ({c["plates"]} plates; {d["own"]} ms with no badge data) · wall {c["med"]} vs {d["med"]} ms')
    check(f'perf: the badge code costs ≤ 1.5 ms on {a["tiles"]} tiles and ≤ 5 ms on {c["tiles"]} (one Map lookup per tile; facts once per data version)',
          a['own'] <= 1.5 and c['own'] <= 5 and c['tiles'] > 2000, out)


# ───────────────────────── snapshot ─────────────────────────
def snapshot(br):
    html = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
    has = 'id="kh-data-marks"' in html
    if not (ROOT / 'web/marks.json').exists():
        check('snapshot: no web/marks.json yet → nothing embedded (the daily job writes it at 16:40)', not has)
        return
    check('snapshot: marks.json embedded (build_page.py DATA_FILES)', has)
    ctx = br.new_context(viewport={'width': 1440, 'height': 900})
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: ERRS.append(f'snapshot pageerror: {e}'))
    pg.goto((ROOT / 'dist/index.html').as_uri()); pg.wait_for_timeout(2500)
    info = pg.evaluate('KH.marks.badgeInfo()')
    snap_day = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))['asOf'][:10]
    mdate = json.loads((ROOT / 'web/marks.json').read_text(encoding='utf-8'))['asOf']
    want = 'eve' if mdate == snap_day else 'next' if mdate < snap_day else None
    check(f'snapshot: the marks rule from its own day (snapshot {snap_day}, marks {mdate} → {want}); counts {info["counts"]}', info['mode'] == want and info['shown'], info)
    pg.screenshot(path=str(SHOTS / 'snapshot_1440.png'))
    ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_badges.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                NP.open(URL + 'api/time', timeout=1).read(); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for name, fn in (('rules', rules), ('plate', plate), ('legend', legend), ('lit', lit), ('views', views), ('themes', themes), ('perf', perf), ('snapshot', snapshot)):
                if name in ONLY:
                    print(f'── {name}', flush=True)
                    fn(br)
            br.close()
        check(f'console errors 0 ({len(ERRS)})', not ERRS, ERRS[:6])
    finally:
        srv.terminate()
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed · shots in {SHOTS}')
    for n in bad:
        print('  FAIL', n)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
