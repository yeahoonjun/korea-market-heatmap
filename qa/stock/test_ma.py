#!/usr/bin/env python3
"""Moving averages + bar intervals on the stock page against a real (local) Worker.

    python3 scripts/build_page.py
    python3 -m http.server 8810 -d web &
    PORT=8811 NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8810/ node worker/dev/serve.mjs &
    python3 qa/stock/test_ma.py [BASE]      # default http://127.0.0.1:8811/

Needs network (Naver through the Worker). Covers: 005930 and a KOSDAQ stock, 6 intervals, 390 + 1280, lines complete at the first visible
bar, hand-calculated values, toggles remembered, hover values, four themes + contrast (>= 3:1), scroll-back, the old-Worker fallback
(iv= answered with 400), overflow 0, console errors 0. Screenshots → qa/shots/ma/.
"""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SHOTS = ROOT / 'qa/shots/ma'; SHOTS.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8811/'
CODES = ['005930', '196170']   # 삼성전자 (KOSPI), 알테오젠 (KOSDAQ)
TFS = ['1m', '5m', 'day', 'week', 'month', 'year']
THEMES = [('base', 'dark'), ('paper', 'light'), ('glass-dark', 'dark'), ('glass-light', 'light')]
FAILS, N = [], 0


def check(name, ok, detail=None):
    global N
    N += 1
    print(('PASS ' if ok else 'FAIL ') + name + ('' if detail is None else '  ' + json.dumps(detail, ensure_ascii=False)[:260]), flush=True)
    if not ok:
        FAILS.append(name)


def lum(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def open_page(b, w, code, route400=False):
    vp = dict(viewport={'width': w, 'height': 844 if w < 500 else 800}, is_mobile=w < 500, has_touch=w < 500, device_scale_factor=2)
    ctx = b.new_context(**vp); pg = ctx.new_page(); logs = []
    pg.on('console', lambda m: logs.append(m.type + ': ' + m.text) if m.type in ('error', 'warning') and 'Failed to load resource' not in m.text else None)
    pg.on('pageerror', lambda e: logs.append('pageerror ' + str(e)))
    reqs = []
    pg.on('request', lambda r: reqs.append(r.url) if '/chart?' in r.url else None)
    if route400:
        pg.route('**/chart?iv=*', lambda r: r.fulfill(status=400, content_type='application/json', body='{"error":"iv?"}'))
    pg.goto(BASE + '#s-' + code)
    pg.wait_for_selector('.sp-tfs button', timeout=25000); pg.wait_for_timeout(800)
    return ctx, pg, logs, reqs


def pick(pg, tf):
    pg.click(f'.sp-tfs button[data-tf="{tf}"]')
    pg.wait_for_function("() => { const m = document.querySelector('.sp-chartmsg'); return m && !m.classList.contains('on') && document.querySelector('.sp-chart').dataset.n }", timeout=20000)
    pg.wait_for_timeout(500)


def state(pg):
    return pg.evaluate("""() => { const c = document.querySelector('.sp-chart'); return { n: +c.dataset.n, ws: +c.dataset.ws, ma120: +c.dataset.ma120, back: c.dataset.back,
      ovf: document.documentElement.scrollWidth - innerWidth,
      chips: [...document.querySelectorAll('.sp-mac')].map(b => [b.dataset.n, b.getAttribute('aria-pressed'), b.querySelector('.n').textContent, b.querySelector('.v').textContent]),
      aria: c.getAttribute('aria-label') } }""")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    for code in CODES:
        for w in (390, 1280):
            ctx, pg, logs, reqs = open_page(b, w, code)
            for tf in TFS:
                pick(pg, tf)
                s = state(pg)
                tag = f'{code}_{w}_{tf}'
                check(f'{tag}_lines_complete_at_first_visible_bar', s['ma120'] <= s['ws'] or tf == 'year' or s['back'] == '0', s)   # a young stock (알테오젠 monthly) runs out of history before 120 bars
                check(f'{tag}_overflow_0', s['ovf'] == 0, s['ovf'])
                units = {'1m': '분', '5m': '분', 'day': '일', 'week': '주', 'month': '월', 'year': '년'}[tf]
                check(f'{tag}_labels_unit', [c[2] for c in s['chips']] == [f'{n}{units}' for n in (5, 20, 60, 120)], [c[2] for c in s['chips']])
            check(f'{code}_{w}_console_clean', not logs, logs)
            check(f'{code}_{w}_iv_form_used', any('iv=' in u for u in reqs) and not any('tf=' in u for u in reqs), reqs[:3])
            ctx.close()

    # ── hand calculation (iv path): last bar + a hovered bar, 일 ──
    ctx, pg, logs, reqs = open_page(b, 1280, '005930')
    pick(pg, 'day')
    j = json.loads(pg.evaluate("async () => JSON.stringify(await (await fetch('api/stock/005930/chart?iv=day&count=250&warm=119')).json())"))
    allb = j['pre'] + j['bars']; cl = [x['c'] for x in allb]
    check('api_pre_shape', len(j['pre']) == 119 and len(j['bars']) == 250 and j['pre'][-1]['t'] < j['bars'][0]['t'], {'pre': len(j['pre']), 'bars': len(j['bars'])})
    fmt = lambda v: f'{round(v):,}'
    ma = lambda n, i: sum(cl[i - n + 1:i + 1]) / n
    s = state(pg)
    last = len(cl) - 1
    check('ma_last_bar_matches_hand_calc', [c[3] for c in s['chips']] == [fmt(ma(n, last)) for n in (5, 20, 60, 120)], {'shown': [c[3] for c in s['chips']], 'want': [fmt(ma(n, last)) for n in (5, 20, 60, 120)]})
    box = pg.query_selector('.sp-chart').bounding_box()
    pg.mouse.move(box['x'] + box['width'] * 0.4, box['y'] + box['height'] * 0.4); pg.wait_for_timeout(300)
    d = pg.evaluate("() => document.querySelector('.sp-legend .sp-lg-t').textContent").split(' ')[0].replace('.', '-')
    idx = next(i for i, x in enumerate(allb) if x['t'] == d)
    hv = [c[3] for c in state(pg)['chips']]
    check('ma_hover_bar_matches_hand_calc', hv == [fmt(ma(n, idx)) for n in (5, 20, 60, 120)], {'date': d, 'shown': hv})
    # toggles remembered
    pg.click('.sp-mac[data-n="120"]'); pg.click('.sp-mac[data-n="60"]'); pg.wait_for_timeout(200)
    pg.reload(); pg.wait_for_selector('.sp-mac'); pg.wait_for_timeout(1500)
    check('ma_toggles_remembered', [c[1] for c in state(pg)['chips']] == ['true', 'true', 'false', 'false'] and json.loads(pg.evaluate("() => localStorage.getItem('khm.stock.ma')")) == {'day': [5, 20]}, state(pg)['chips'])
    check('interval_remembered', pg.evaluate("() => localStorage.getItem('khm.stock.iv')") == '"day"')
    pg.click('.sp-mac[data-n="120"]'); pg.click('.sp-mac[data-n="60"]')

    # ── scroll-back (日): drag to the left edge until older bars are loaded ──
    s0 = state(pg)
    for _ in range(6):
        pg.mouse.move(box['x'] + 100, box['y'] + 200); pg.mouse.down(); pg.mouse.move(box['x'] + box['width'] - 40, box['y'] + 200, steps=8); pg.mouse.up(); pg.wait_for_timeout(900)
    s1 = state(pg)
    check('scrollback_daily_loads_older', s1['n'] > s0['n'] and any('to=' in u for u in reqs), {'before': s0['n'], 'after': s1['n']})
    # 1m: only about 6 trading days exist → the note appears at the end
    pick(pg, '1m')
    for _ in range(14):
        pg.mouse.move(box['x'] + 60, box['y'] + 200); pg.mouse.down(); pg.mouse.move(box['x'] + box['width'] - 30, box['y'] + 200, steps=6); pg.mouse.up(); pg.wait_for_timeout(700)
    note = pg.evaluate("() => document.querySelector('.sp-chnote').textContent")
    check('scrollback_1m_ends_with_note', note == '더 이전 분봉은 없어요' and state(pg)['back'] == '0', {'note': note, 'state': state(pg)['n']})
    pg.screenshot(path=str(SHOTS / 'scrollback_1m_end.png'))
    check('scrollback_console_clean', not logs, logs)
    ctx.close()

    # ── old Worker (iv= answered 400): tf= fallback, no scroll-back, no errors ──
    ctx, pg, logs, reqs = open_page(b, 390, '005930', route400=True)
    for tf in TFS:
        pick(pg, tf); s = state(pg)
        check(f'oldworker_{tf}_draws_back_off', s['n'] > 0 and s['back'] == '0', s)
    check('oldworker_tf_form_used', any('tf=' in u for u in reqs), reqs[:4])
    check('oldworker_console_clean', not logs, logs)
    ctx.close()

    # ── themes: colours re-applied, contrast of each line against the chart ground >= 3:1 ──
    ctx, pg, logs, reqs = open_page(b, 1280, '005930')
    pick(pg, 'day')
    # the template of this worktree may not define the light tokens yet: set the values of docs/standards/themes.md §4 ourselves
    TOK = {
        'base': {},
        'paper': {'--page': '#f6e8da', '--panel': '#f6e8da', '--panel2': '#eddac7', '--fg': '#211a15', '--fg2': '#4a3f37', '--muted': '#6a5c51', '--faint': '#65584c', '--line': 'rgba(33,26,21,.2)', '--line2': 'rgba(33,26,21,.34)', '--card-bg': 'transparent', '--chip-bg': '#eddac7', '--chip-on': '#f7d68e'},
        'glass-dark': {'--page': '#0b0c10', '--card-bg': 'rgba(255,255,255,.045)', '--panel': 'rgba(255,255,255,.045)'},
        'glass-light': {'--page': '#e7eaf0', '--panel': 'rgba(255,255,255,.62)', '--fg': '#0f1115', '--fg2': '#353b44', '--muted': '#535a65', '--faint': '#555c67', '--line': 'rgba(15,17,21,.09)', '--line2': 'rgba(15,17,21,.15)', '--card-bg': 'rgba(255,255,255,.62)', '--chip-bg': 'rgba(15,17,21,.06)', '--chip-on': 'rgba(255,181,71,.3)'},
    }
    prev = []
    for th, tone in THEMES:
        pg.evaluate("([t, tone, tok, prev]) => { const d = document.documentElement; prev.forEach(k => d.style.removeProperty(k)); for (const k in tok) d.style.setProperty(k, tok[k]); d.dataset.theme = t; d.dataset.tone = tone; document.dispatchEvent(new CustomEvent('kh:theme')); }", [th, tone, TOK[th], prev])
        prev = list(TOK[th])
        pg.wait_for_timeout(500)
        r = pg.evaluate("""() => {
          const probe = document.createElement('span'); document.querySelector('.sp').append(probe);
          const rgb = v => { probe.style.color = v; return getComputedStyle(probe).color.match(/[\\d.]+/g).map(Number); };
          const cs = getComputedStyle(document.querySelector('.sp-chartwrap'));
          return { page: rgb(getComputedStyle(document.querySelector('.sp')).backgroundColor), card: rgb(cs.backgroundColor), ma: [5, 20, 60, 120].map(n => rgb(`var(--ma-${n})`)) }; }""")
        a_ = r['card'][3] if len(r['card']) > 3 else 1
        bg = [r['card'][i] * a_ + r['page'][i] * (1 - a_) for i in range(3)]   # the card over the page
        rs = [round(ratio(c[:3], bg), 2) for c in r['ma']]
        check(f'theme_{th}_ma_contrast_ge_3', min(rs) >= 3, {'bg': [round(x) for x in bg], 'ratios': rs})
        pg.screenshot(path=str(SHOTS / f'themes_{th}_1280.png'))
    check('themes_console_clean', not logs, logs)
    ctx.close()
    b.close()
print(f'\n{N - len(FAILS)}/{N} passed' + ('' if not FAILS else '  FAILED: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
