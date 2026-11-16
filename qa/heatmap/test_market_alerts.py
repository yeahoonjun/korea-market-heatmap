#!/usr/bin/env python3
"""시장 경보 배지 (AGENTS §3-37 ⓐ — 투자주의 · 투자경고 · 투자위험 · 관리종목 · 거래정지, 중립 배지, "한국거래소 지정 · 기준 시각").

  python3 scripts/build_page.py && python3 qa/heatmap/test_market_alerts.py [--shots DIR]

Live checks run the built web/ behind qa/stock/mock_api.py on ALERTS_QA_PORT (default 9060; 9060–9069 only — fuser -k frees it) with
d3 / Pretendard / /api/time served from the repo, /data/alerts.json answered by the test (a fake file: today's date, or 404, or old)
and /api/quotes passed through with hx:1 added to one row (거래정지 from the quotes, not the file). The snapshot (dist/index.html)
is checked for the alerts embedded at build time.
What is checked:
  · the file → KH.alerts.info() (fresh, count), the order of several (거래정지 → 투자위험 → 투자경고 → 관리종목 → 투자주의 → 그 밖):
    2 badges + "외 N" in the tooltip · quick view · stock page head, 1 + "외 N" in the table · search; the note line "외 1: 관리종목 ·
    한국거래소 지정 · M/D HH:MM 기준" under the tooltip / quick-view head and in the stock page's meta line
  · the shape steps (l1 ring · l2 fill · l3 solid ink · adm bar), an unknown alert string → "시장 경보"
  · hx:1 on a quotes row → 거래정지 with "시세 HH:MM 기준" even when the file does not list the stock
  · the tile's and the table row's aria-label tail ", 거래정지, 투자경고, 관리종목"; a stock without alerts gets no tail, no element
  · no data (404, an old Worker without the file) → no badge from the file, hx still shows; an old file (before the weekday before
    today) → hidden; the weekday before today → shown
  · neutral: badge colours carry no hue (max − min channel ≤ 40, never the 등락 / amber colours); text contrast ≥ 4.5:1 against the
    pixels behind it (glass: the real see-through panel)
  · four themes × 360 · 1280: the tooltip (1280) / quick view, the table, the stock page head and the search list fit (no overflow of the
    page, the card head, the table box, the stock head); console errors 0
Screenshots go to --shots (default /tmp) as alerts_*.png. Exit code 1 if any check fails.
"""
import argparse
import base64
import datetime as dt
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
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
SNAP = (ROOT / 'dist/index.html').as_uri()
PORT = int(os.environ.get('ALERTS_QA_PORT', 9060))
assert 9060 <= PORT <= 9069, 'ports 9060–9069 (default 9060)'
LIVE = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
KST = dt.timezone(dt.timedelta(hours=9))

ap = argparse.ArgumentParser()
ap.add_argument('--shots', default=os.environ.get('ALERTS_SHOTS', '/tmp'))
ARGS = ap.parse_args()
SHOTS = pathlib.Path(ARGS.shots)
SHOTS.mkdir(parents=True, exist_ok=True)

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{str(detail)[:400]}]' if detail != '' and not ok else ''), flush=True)


def weekday_before(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


TODAY = dt.datetime.now(KST).date()
PREV = weekday_before(TODAY)
OLD = weekday_before(PREV)
HX = '035420'       # NAVER: halted by the quotes only
FAKE_C = {
    '005930': {'a': 'warning', 'adm': 1, 'stop': 1},   # three: 거래정지 · 투자경고 + 외 1 (관리종목)
    '000660': {'a': 'caution'},
    '373220': {'a': 'risk'},
    '207940': {'adm': 1},
    '005380': {'a': 'marketAlertSomethingNew'},          # an unknown string → 시장 경보
    '012340': {'a': 'warning', 'adm': 1, 'stop': 1},   # 뉴인텍: outside the streamed 600 (search via names.json)
}


def fake(day, at='07:50'):
    return {'asOf': day.isoformat(), 'at': at, 'n': 2701, 'c': FAKE_C}


def md(d):
    return f'{d.month}/{d.day}'


D3 = (ROOT / 'src/vendor/d3-7.9.0.min.js').read_bytes()
FONT_CSS = ("@font-face{font-family:'Pretendard Variable';font-weight:45 920;font-style:normal;font-display:swap;src:url(data:font/woff2;base64,"
            + base64.b64encode((ROOT / 'src/fonts/PretendardVariable-subset.woff2').read_bytes()).decode() + ") format('woff2-variations')}").encode()


class Errors:
    def __init__(self):
        self.items = []

    def attach(self, page, tag):
        page.on('pageerror', lambda e: self.items.append(f'{tag} pageerror: {e}'))
        page.on('console', lambda m: self.items.append(f'{tag} console: {m.text[:120]} {(m.location or {}).get("url", "")}') if m.type == 'error' and not self.expected(m) else None)

    @staticmethod
    def expected(m):
        # the mock answers 404 for close.json (by design) and the 404 / old-Worker case of this test asks for alerts.json on purpose
        loc = (m.location or {}).get('url', '')
        return 'Failed to load resource' in m.text and any(k in loc for k in ('/data/close.json', '/data/alerts.json', '/api/breadth', '/api/policy', '/api/calendar', '/api/funds'))


ERR = Errors()


def context(browser, w, alerts='today', hx=True):
    """alerts: 'today' | 'prev' | 'old' | '404'; hx: add hx:1 to the HX row of every quotes answer"""
    opts = dict(viewport={'width': w, 'height': 740 if w < 760 else 800})
    if w < 760:
        opts.update(is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx = browser.new_context(**opts)
    hdr = {'access-control-allow-origin': '*'}
    ctx.route('https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js', lambda r: r.fulfill(status=200, body=D3, headers={**hdr, 'content-type': 'application/javascript'}))
    ctx.route('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@*/**', lambda r: r.fulfill(status=200, body=FONT_CSS, headers={**hdr, 'content-type': 'text/css'}))
    # the quick view's 오늘 흐름 (/api/chart/<code>) — qa/stock/mock_api.py leaves it 404; the same quiet answer as qa/float/mock_float.py
    ctx.route('**/api/chart/*', lambda r: r.fulfill(status=200, body=json.dumps({'code': r.request.url.rsplit('/', 1)[-1], 'points': []}), headers={'content-type': 'application/json'}))
    ctx.route('**/api/time', lambda r: r.fulfill(status=200, body=json.dumps({'t': int(time.time() * 1000)}), headers={'content-type': 'application/json', 'cache-control': 'no-store'}))

    def al(route):
        if alerts == '404':
            return route.fulfill(status=404, body='{"error":"not found"}', headers={'content-type': 'application/json'})
        day = {'today': TODAY, 'prev': PREV, 'old': OLD}[alerts]
        route.fulfill(status=200, body=json.dumps(fake(day)), headers={'content-type': 'application/json', 'cache-control': 'no-store'})
    ctx.route('**/data/alerts.json', al)

    def quotes(route):
        res = route.fetch()
        try:
            j = res.json()
            for row in j.get('stocks', []):
                if hx and row.get('c') == HX:
                    row['hx'] = 1
                # the file's 거래정지 stocks really halted: volume 0 (a row with KRX volume today reads as resumed — 사용자 13:15)
                if row.get('c') in HALTED and not RESUMED.get('on'):
                    row['v'] = 0
            route.fulfill(response=res, body=json.dumps(j, ensure_ascii=False), headers={**res.headers, 'content-type': 'application/json'})
        except Exception:
            route.fulfill(response=res)
    ctx.route('**/api/quotes*', quotes)
    return ctx


HALTED = {c for c, v in FAKE_C.items() if v.get('stop')}
RESUMED = {'on': False}


def open_page(browser, w, theme='base', market='K', tag='', wait=1800, **kw):
    ctx = context(browser, w, **kw)
    pg = ctx.new_page()
    ERR.attach(pg, tag or f'{theme} {w}')
    pg.goto(LIVE)
    pg.evaluate("""s => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);
      localStorage.setItem('khm.theme', JSON.stringify(s.t)); localStorage.setItem('khm.market', JSON.stringify(s.m)); }""", {'t': theme, 'm': market})
    pg.reload()
    pg.wait_for_function("() => window.KH && KH.stocks().length > 0", timeout=15000)
    pg.wait_for_timeout(wait)
    return ctx, pg


# in-page: what a box shows
HELP = r"""() => {
  if (window.__al) return;
  const tags = box => { const t = box && box.querySelector('.altags'); return t ? { al: t.dataset.al, labels: [...t.querySelectorAll('.altag')].map(x => x.textContent),
    cls: [...t.querySelectorAll('.altag')].map(x => x.className.replace('altag ', '')), more: (t.querySelector('.almore [aria-hidden]') || {}).textContent || '',
    moreSr: (t.querySelector('.almore .sr') || {}).textContent || '' } : null; };
  const note = box => { const n = box && box.querySelector('.alnote'); return n ? n.textContent : null; };
  const over = el => !el ? null : Math.max(0, el.scrollWidth - el.clientWidth);
  const words = box => { const t = box && box.querySelector('.alsm'); return t ? { al: t.dataset.al, text: t.textContent } : null; };
  window.__al = { tags, note, over, words };
}"""


def help_(pg):
    pg.evaluate(HELP)


def hover_tile(pg, code):
    pg.evaluate("c => { const t = document.querySelector(`.tile[data-c=\"${c}\"]`); t && t.scrollIntoView({block: 'center'}); }", code)
    pg.wait_for_timeout(150)
    box = pg.evaluate("c => { const t = document.querySelector(`.tile[data-c=\"${c}\"]`); if (!t) return null; const r = t.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }", code)
    if not box:
        return False
    pg.mouse.move(box[0] - 3, box[1] - 3)
    pg.mouse.move(box[0], box[1])
    try:
        pg.wait_for_function("c => document.querySelector('#tip.show') && document.querySelector('#tip .card-head small') && document.querySelector('#tip .card-head small').textContent === c", arg=code, timeout=3000)
    except Exception:
        return False
    pg.wait_for_timeout(250)
    return True


def to_table(pg):
    pg.click('.viewseg button[data-v="table"]')
    pg.wait_for_timeout(700)


def to_map(pg):
    pg.click('.viewseg button[data-v="map"]')
    pg.wait_for_timeout(500)


def search(pg, q):
    """type into the visible search box (#q) and return the options' parts"""
    vis = pg.evaluate("() => { const q = document.querySelector('#q'); return !!(q && q.getClientRects().length && q.getBoundingClientRect().width > 20); }")
    if vis:
        pg.fill('#q', '')
        pg.type('#q', q, delay=20)
        pg.wait_for_timeout(500)
        return pg.evaluate("() => [...document.querySelectorAll('#sugg [role=option]')].map(o => ({t: o.textContent, tags: __al.words(o)}))"), '#sugg'
    pg.evaluate("() => { const k = document.querySelector('.dk-k'); if (k) k.click(); }")
    pg.wait_for_timeout(500)
    pg.fill('#dkq', q)
    pg.wait_for_timeout(500)
    return pg.evaluate("() => [...document.querySelectorAll('#dksugg [role=option]')].map(o => ({t: o.textContent, tags: __al.words(o)}))"), '#dksugg'


def lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def parse_rgb(s):
    import re
    n = [float(x) for x in re.findall(r'[\d.]+', s)]
    return n[:3] + [n[3] if len(n) > 3 else 1.0]


def badge_contrast(pg, sel):
    """text colour (computed, opaque tokens) vs the pixels just inside each badge's padding (what is really behind the text)"""
    from PIL import Image
    import io
    boxes = pg.evaluate("""sel => [...document.querySelectorAll(sel + ' .altag')].filter(b => b.getClientRects().length).map(b => {
      const r = b.getBoundingClientRect(), cs = getComputedStyle(b); return {x: r.x, y: r.y, w: r.width, h: r.height, color: cs.color, k: b.dataset.k}; })""", sel)
    if not boxes:
        return []
    png = pg.screenshot()
    im = Image.open(io.BytesIO(png)).convert('RGB')
    sx = im.width / pg.viewport_size['width']
    out = []
    for bx in boxes:
        x, y = int((bx['x'] + 4.5) * sx), int((bx['y'] + bx['h'] / 2) * sx)
        bg = im.getpixel((min(x, im.width - 1), min(y, im.height - 1)))
        fg = parse_rgb(bx['color'])
        if fg[3] < 1:   # composite on the sampled background
            fg = [fg[i] * fg[3] + bg[i] * (1 - fg[3]) for i in range(3)]
        out.append((bx['k'], round(contrast(fg, bg), 2)))
    return out


BASE_SEARCH = {}


def run_live(browser):
    # ── 1280, base: every place + order + shapes ──
    ctx, pg = open_page(browser, 1280, tag='base 1280')
    help_(pg)
    info = pg.evaluate("() => KH.alerts.info()")
    check('file → KH.alerts.info() (today, fresh, 6 codes)', info and info['fresh'] and info['count'] == len(FAKE_C) and info['asOf'] == TODAY.isoformat() and info['when'] == f'{md(TODAY)} 07:50', info)
    of = pg.evaluate("() => ['005930', '000660', '373220', '207940', '005380', '035420', '000270'].map(c => [c, KH.alerts.of(c)])")
    of = dict(of)
    check('order: 거래정지 → 투자경고 → 관리종목 (three on one stock)', of['005930'] and of['005930']['keys'] == ['stop', 'warning', 'adm'], of['005930'])
    # the file still says 거래정지, but today's quotes show KRX volume and no hx → trading again: the halt badge goes (사용자 13:15)
    RESUMED['on'] = True
    rctx, rpg = open_page(browser, 1280, tag='resumed 1280')
    rk = rpg.evaluate("() => KH.alerts.of('005930')")
    check('거래정지 in the file + volume today, no hx → resumed: 투자경고 · 관리종목 stay, 거래정지 goes', rk and rk['keys'] == ['warning', 'adm'], rk)
    rctx.close()
    RESUMED['on'] = False
    check('names: 투자주의 · 투자위험 · 관리종목 · unknown → 시장 경보', [of[c]['labels'] for c in ('000660', '373220', '207940', '005380')] == [['투자주의'], ['투자위험'], ['관리종목'], ['시장 경보']], of)
    check('hx:1 on a quotes row → 거래정지 from the quotes (live, not the file)', of['035420'] and of['035420']['keys'] == ['stop'] and of['035420']['live'] and not of['035420']['file'], of['035420'])
    check('a stock without alerts → null', of['000270'] is None, of['000270'])
    # tooltip
    ok = hover_tile(pg, '005930')
    t = pg.evaluate("() => [__al.tags(document.querySelector('#tip .card-head .nmrow')), __al.note(document.querySelector('#tip .card-head'))]") if ok else [None, None]
    check('tooltip: 거래정지 · 투자경고 + 외 1 next to the name (after 상·하한가 slot)', t[0] and t[0]['labels'] == ['거래정지', '투자경고'] and t[0]['more'] == '외 1' and t[0]['moreSr'] == '관리종목', t)
    check('tooltip: note "외 1: 관리종목 · 한국거래소 지정 · M/D 07:50 기준"', t[1] and '외 1: 관리종목' in t[1] and f'한국거래소 지정 · {md(TODAY)} 07:50 기준' in t[1], t[1])
    check('tooltip: shape steps l3 (거래정지) · l2 (투자경고)', t[0] and t[0]['cls'] == ['l3', 'l2'], t[0])
    pg.screenshot(path=str(SHOTS / 'alerts_tip_base_1280.png'))
    ok = hover_tile(pg, HX)
    t = pg.evaluate("() => [__al.tags(document.querySelector('#tip .card-head .nmrow')), __al.note(document.querySelector('#tip .card-head'))]") if ok else [None, None]
    qhm = pg.evaluate("() => { const a = KH.asOf(); return a ? new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).format(new Date(a)) : ''; }")
    check('tooltip (hx only): 거래정지 + "한국거래소 지정 · 시세 HH:MM 기준"', t[0] and t[0]['labels'] == ['거래정지'] and t[1] and f'시세 {qhm} 기준' in t[1], [t, qhm])
    ok = hover_tile(pg, '000270')
    check('tooltip: a stock without alerts has no badge · no note', ok and pg.evaluate("() => !document.querySelector('#tip .altags') && !document.querySelector('#tip .alnote')"))
    pg.mouse.move(2, 2)
    # tile aria-label
    aria = pg.evaluate("() => ['005930', '000660', HX, '000270'].map(c => { const t = document.querySelector(`.tile[data-c=\"${c}\"]`); return t ? t.getAttribute('aria-label') : null; })".replace('HX', f"'{HX}'"))
    check('tile aria-label tail ", 거래정지, 투자경고, 관리종목" · ", 투자주의" · hx ", 거래정지" · none without', aria[0] and aria[0].endswith(', 거래정지, 투자경고, 관리종목') and aria[1] and aria[1].endswith(', 투자주의')
          and aria[2] and aria[2].endswith(', 거래정지') and aria[3] and '투자' not in aria[3] and '거래정지' not in aria[3], aria)
    check('map tiles carry no new mark (decision: no tile drawing this round)', pg.evaluate("() => !document.querySelector('.tile .altags, .tile .altag')"))
    # quick view
    pg.evaluate("() => KH.quick('005930')"); pg.wait_for_timeout(500)
    q = pg.evaluate("() => [__al.tags(document.querySelector('#sheet .card-head .nmrow')), __al.note(document.querySelector('#sheet .card-head')), __al.over(document.querySelector('#sheet .card-head'))]")
    check('quick view: same badges + note, head fits', q[0] and q[0]['labels'] == ['거래정지', '투자경고'] and q[0]['more'] == '외 1' and q[1] and f'{md(TODAY)} 07:50 기준' in q[1] and q[2] == 0, q)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # table
    to_table(pg)
    tb = pg.evaluate("""() => { const row = [...document.querySelectorAll('.list tbody tr')].find(r => r.querySelector('small') && r.querySelector('small').textContent === '005930');
      const r2 = [...document.querySelectorAll('.list tbody tr')].find(r => r.querySelector('small') && r.querySelector('small').textContent === '000270');
      return row ? [__al.tags(row), row.getAttribute('aria-label'), r2 && !r2.querySelector('.altags'), !!(row.querySelector('.dmsw, .altags'))] : null; }""")
    check('table: one badge 거래정지 + 외 2 in the name cell, aria tail', tb and tb[0] and tb[0]['labels'] == ['거래정지'] and tb[0]['more'] == '외 2' and tb[1].endswith(', 거래정지, 투자경고, 관리종목') and tb[2], tb)
    to_map(pg)
    # search
    opts, where = search(pg, '삼성전자')
    first = next((o for o in opts if '005930' in o['t']), None)
    check('search: 삼성전자 row → small words "거래정지 외 2" next to the name (order kept)', first and first['tags'] and first['tags']['al'] == 'stop warning adm' and first['tags']['text'].startswith('거래정지 외 2'), [where, opts[:2]])
    plain = next((o for o in opts if '005930' not in o['t']), None)
    check('search: rows without alerts have no badge', plain is None or plain['tags'] is None, plain)
    opts, where = search(pg, '뉴인텍')
    ext = next((o for o in opts if '012340' in o['t']), None)
    check('search beyond the stream (names.json): 뉴인텍 → "거래정지 외 2"', ext and ext['tags'] and ext['tags']['text'].startswith('거래정지 외 2'), [where, opts[:2]])
    pg.fill('#q', '') if where == '#sugg' else None
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    # stock page
    pg.evaluate("() => KHStock.open('005930')"); pg.wait_for_timeout(1200)
    sp = pg.evaluate("() => [__al.tags(document.querySelector('.sp-al')), document.querySelector('.sp-meta').textContent, __al.over(document.querySelector('.sp-head-in'))]")
    check('stock page head: 거래정지 · 투자경고 + 외 1 by the quote', sp[0] and sp[0]['labels'] == ['거래정지', '투자경고'] and sp[0]['more'] == '외 1', sp)
    check('stock page meta: "외 1: 관리종목 · 한국거래소 지정 · M/D 07:50 기준", head fits', sp[1] and '외 1: 관리종목' in sp[1] and f'한국거래소 지정 · {md(TODAY)} 07:50 기준' in sp[1] and sp[2] == 0, sp)
    pg.screenshot(path=str(SHOTS / 'alerts_stock_base_1280.png'), clip={'x': 0, 'y': 0, 'width': 1280, 'height': 160})
    # the quote box is aria-live: the badges are not redrawn by every quote
    n0 = pg.evaluate("() => { window.__alN = 0; new MutationObserver(m => { window.__alN += m.length; }).observe(document.querySelector('.sp-al'), {childList: true, subtree: true}); return 0; }")
    pg.evaluate("() => KH.refresh()"); pg.wait_for_timeout(1200)
    check('stock page: a new quote does not redraw the same badges (aria-live box)', pg.evaluate("() => window.__alN") == 0, pg.evaluate("() => window.__alN"))
    pg.evaluate("() => KHStock.open('000270')"); pg.wait_for_timeout(800)
    check('stock page: a stock without alerts → no badge, no note', pg.evaluate("() => document.querySelector('.sp-al').hidden && !/한국거래소 지정/.test(document.querySelector('.sp-meta').textContent)"))
    pg.evaluate("() => KHStock.close()"); pg.wait_for_timeout(300)
    ctx.close()

    # ── no file / old Worker ──
    ctx, pg = open_page(browser, 1280, alerts='404', tag='404')
    r = pg.evaluate(f"() => [KH.alerts.info(), KH.alerts.of('005930'), KH.alerts.of('{HX}'), document.querySelectorAll('.altags').length]")
    check('404 (no file / old Worker): no badge from the file, info() null, hx still 거래정지', r[0] is None and r[1] is None and r[2] and r[2]['keys'] == ['stop'], r)
    ctx.close()
    ctx, pg = open_page(browser, 1280, alerts='404', hx=False, tag='404 old quotes')
    r = pg.evaluate(f"() => [KH.alerts.of('{HX}'), [...document.querySelectorAll('.tile')].filter(t => /, (거래정지|투자주의|투자경고|투자위험|관리종목|시장 경보)(,|$)/.test(t.getAttribute('aria-label') || '')).length]")
    check('404 + quotes without hx (an older Worker): nothing at all', r[0] is None and r[1] == 0, r)
    ctx.close()
    # ── old / the weekday before ──
    ctx, pg = open_page(browser, 1280, alerts='old', tag='old')
    r = pg.evaluate(f"() => [KH.alerts.info(), KH.alerts.of('005930'), KH.alerts.of('{HX}')]")
    check(f'old file ({OLD}, before the weekday before today): hidden (fresh false), hx kept', r[0] and not r[0]['fresh'] and r[1] is None and r[2] and r[2]['keys'] == ['stop'], r)
    ok = hover_tile(pg, '005930')
    check('old file: the tooltip shows no badge, no note', ok and pg.evaluate("() => !document.querySelector('#tip .altags') && !document.querySelector('#tip .alnote')"))
    ctx.close()
    ctx, pg = open_page(browser, 1280, alerts='prev', tag='prev')
    r = pg.evaluate("() => [KH.alerts.info(), KH.alerts.of('005930')]")
    check(f'file from the weekday before ({PREV}): shown with its date', r[0] and r[0]['fresh'] and r[1] and r[1]['when'] == f'{md(PREV)} 07:50', r)
    ctx.close()


def run_themes(browser):
    ov, neutral, contr = {}, {}, {}
    for th in THEMES:
        for w in (360, 1280):
            # baseline: the same search with no alerts (the list may already overflow — an older issue; alerts must add none)
            bctx, bpg = open_page(browser, w, theme=th, alerts='404', hx=False, tag=f'baseline {th} {w}', wait=900)
            help_(bpg)
            _, where = search(bpg, '삼성전자')
            BASE_SEARCH[(th, w)] = bpg.evaluate(f"() => __al.over(document.querySelector('{where}'))")
            bctx.close()
            ctx, pg = open_page(browser, w, theme=th, tag=f'{th} {w}', wait=1400)
            help_(pg)
            o = {}
            if w == 1280:
                hover_tile(pg, '005930')
                o['tip'] = pg.evaluate("() => { const t = document.querySelector('#tip'); const r = t.getBoundingClientRect(); return [__al.over(t.querySelector('.card-head')), r.right <= innerWidth + 0.5 && r.left >= -0.5 ? 0 : 1]; }")
                contr[f'{th} {w} tip'] = badge_contrast(pg, '#tip')
                if th in ('glass-dark', 'glass-light'):
                    pg.screenshot(path=str(SHOTS / f'alerts_tip_{th}_1280.png'))
                pg.mouse.move(2, 2); pg.wait_for_timeout(300)
            pg.evaluate("() => KH.quick('005930')"); pg.wait_for_timeout(600)
            o['sheet'] = pg.evaluate("() => __al.over(document.querySelector('#sheet .card-head'))")
            contr[f'{th} {w} sheet'] = badge_contrast(pg, '#sheet')
            for c in ('000660', '207940'):         # 투자주의 (ring only) · 관리종목 (ring + bar)
                pg.evaluate("c => KH.quick(c)", c); pg.wait_for_timeout(450)
                contr[f'{th} {w} sheet {c}'] = badge_contrast(pg, '#sheet')
            pg.evaluate("() => KH.quick('005930')"); pg.wait_for_timeout(450)
            cols = pg.evaluate("""() => { const up = getComputedStyle(document.documentElement).getPropertyValue('--up-text'), n = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
              const bad = [n(up), n(getComputedStyle(document.documentElement).getPropertyValue('--dn-text')), n(getComputedStyle(document.documentElement).getPropertyValue('--acc'))];
              return {bad, got: [...document.querySelectorAll('#sheet .altag')].flatMap(b => { const s = getComputedStyle(b); return [s.color, s.backgroundColor]; })}; }""")
            neutral[f'{th} {w}'] = cols
            pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
            if w == 360:
                pg.screenshot(path=str(SHOTS / f'alerts_page_{th}_360.png'))
            to_table(pg)
            # phones (≤ 430px) swipe the table sideways with the 종목 column frozen (사용자 2026-11-16 12:55) — the box scrolls on purpose;
            # what must fit is the frozen name cell (its badges inside it) and the page
            o['table'] = pg.evaluate("() => w <= 430 ? __al.over(document.querySelector('.tablewrap tbody td:first-child')) : __al.over(document.querySelector('.tablewrap'))".replace('w <= 430', 'true' if w <= 430 else 'false'))
            to_map(pg)
            opts, where = search(pg, '삼성전자')
            o['search'] = max(0, pg.evaluate(f"() => __al.over(document.querySelector('{where}'))") - BASE_SEARCH.get((th, w), 0))
            o['search_tag'] = bool(next((x for x in opts if x['tags']), None))
            pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
            if where == '#sugg':
                pg.fill('#q', '')
            pg.evaluate("() => KHStock.open('005930')"); pg.wait_for_timeout(1100)
            o['stock'] = pg.evaluate("() => [__al.over(document.querySelector('.sp-head-in')), (() => { const a = document.querySelector('.sp-al'), r = a.getBoundingClientRect(); return a.hidden ? 1 : (r.right <= innerWidth + 0.5 ? 0 : 1); })(), __al.over(document.querySelector('.sp-meta'))]")
            contr[f'{th} {w} stock'] = badge_contrast(pg, '.sp-al')
            if w == 360:
                pg.screenshot(path=str(SHOTS / f'alerts_stock_{th}_360.png'), clip={'x': 0, 'y': 0, 'width': 360, 'height': 180})
            pg.evaluate("() => KHStock.close()"); pg.wait_for_timeout(300)
            o['page'] = pg.evaluate("() => document.documentElement.scrollWidth - innerWidth")
            ov[f'{th} {w}'] = o
            ctx.close()
    bad = {k: v for k, v in ov.items() if v.get('tip', [0, 0]) != [0, 0] or v['sheet'] or v['table'] or v['search'] or v['stock'] != [0, 0, 0] or v['page'] > 0 or not v['search_tag']}
    check('4 themes × 360 · 1280: tooltip · quick view · table · stock head fit, search adds no overflow, page overflow 0', not bad, bad or '')
    print('      search list overflow without alerts (older, baseline):', {f'{k[0]} {k[1]}': v for k, v in BASE_SEARCH.items()})

    def chroma(s):
        r = parse_rgb(s)
        return 0 if r[3] == 0 else max(r[:3]) - min(r[:3])
    nb = {k: v['got'] for k, v in neutral.items() if not v['got'] or any(chroma(c) > 40 or c in v['bad'] for c in v['got'])}
    check('neutral: badge text · fill carry no hue (≤ 40), never the 등락 / amber colours', not nb, nb or '')
    cb = {k: v for k, v in contr.items() if not v or any(c < 4.5 for _, c in v)}
    check('contrast ≥ 4.5:1 for every badge text over what is behind it (4 themes, glass see-through)', not cb, cb or '')
    print('      contrast min per place:', {k: min(c for _, c in v) for k, v in contr.items() if v})


def run_snapshot(browser):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    pg = ctx.new_page()
    ERR.attach(pg, 'snapshot')
    pg.goto(SNAP)
    pg.wait_for_timeout(1500)
    web = json.loads((ROOT / 'web/alerts.json').read_text(encoding='utf-8'))
    info = pg.evaluate("() => KH.alerts.info()")
    check('snapshot: the build embeds web/alerts.json (kh-data-alerts) and reads it', info and info['count'] == len(web['c']) and info['asOf'] == web['asOf'], info)
    ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    srv = subprocess.Popen([sys.executable, str(ROOT / 'qa/stock/mock_api.py'), '--port', str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                NOPROXY.open(LIVE + '__reset', timeout=2).read(); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            try:
                for fn in (run_live, run_themes, run_snapshot):
                    try:
                        fn(browser)
                    except Exception as e:
                        check(f'{fn.__name__} ran to the end', False, f'{type(e).__name__}: {str(e).splitlines()[0][:300]}')
            finally:
                browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            pass
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    check('console errors 0', not ERR.items, ERR.items[:8])
    n = sum(1 for _, ok, _ in results if ok)
    print(f'\n{n}/{len(results)} passed')
    sys.exit(0 if n == len(results) else 1)


if __name__ == '__main__':
    main()
