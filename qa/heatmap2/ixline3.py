"""§3-20 today's index line in the map header row (numbers, not eyeballing).
usage: ixline3.py [section…]   sections: live, states, poll, replay, snapshot, quality (default: all)
live / poll / replay: /api/quotes and /api/market answered from fixtures/ix_quotes.json.gz + ix_market.json (real captures, 11/10 13:02)
with the page clock at 13:02:50 KST; snapshot: dist/index.html as built (no embedded /api/market → no line) and a copy with a
synthetic <script id="kh-data-market"> of the snapshot's day; quality: the dev Worker harness as it is (real Naver) + the snapshot."""
import sys, os, json, gzip, copy, re, time
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, VIEWPORTS
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
V = dict(VIEWPORTS, d1024=dict(viewport={'width': 1024, 'height': 800}), d1440=dict(viewport={'width': 1440, 'height': 900}))
WANT = set(sys.argv[1:]) or {'live', 'states', 'poll', 'replay', 'snapshot', 'quality'}
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
SNAP = 'file:///home/claude/hm-heatmap/dist/index.html'
SHOTS = HERE + '/shots3/'
MK = json.load(open(HERE + '/fixtures/ix_market.json'))
Q = json.load(gzip.open(HERE + '/fixtures/ix_quotes.json.gz'))
CLOCK = '2026-11-10T13:02:50+09:00'
TOP = {'m390': 240, 'd1280': 191}            # map top before §3-20 (live); the snapshot's phone header is shorter (234)
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]
def fmt2(v): return f'{v:,.2f}'
def pct(v): return ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.2f}%'


def item(m, key): return next(x for x in m['items'] if x['key'] == key)


def mirror_kosdaq(m, q):
    """KOSDAQ below its previous close: spark and quote reflected around the base (so the line is the 하락 colour, under the dashed line)"""
    m, q = copy.deepcopy(m), copy.deepcopy(q)
    it = item(m, 'KOSDAQ'); base = it['value'] - it['change']
    it['spark'] = [[t, round(2 * base - v, 2)] for t, v in it['spark']]
    it['value'], it['change'], it['ratio'] = round(base - it['change'], 2), -it['change'], -it['ratio']
    x = q['index']['KOSDAQ']; x.update(value=round(base - x['change'], 2), change=-x['change'], ratio=-x['ratio'])
    return m, q


def fresh(b, vp, market='K', store=None, url=URL, mk=MK, q=Q, hook=None, wait=3000, mocked=True, clock=CLOCK):
    ctx = b.new_context(**V[vp], service_workers='block')
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    hold = {'n': 0, 'mk': 0}
    if mocked:
        pg.clock.set_fixed_time(clock)
        def on_q(r):
            if '?' in r.request.url: r.continue_(); return
            body = copy.deepcopy(q); hold['n'] += 1
            if hook: hook(body, hold['n'])
            r.fulfill(status=200, content_type='application/json', body=json.dumps(body, ensure_ascii=False))
        def on_m(r):
            hold['mk'] += 1; hold.setdefault('mt', []).append(time.time())
            r.fulfill(status=200, content_type='application/json', body=json.dumps(mk, ensure_ascii=False))
        pg.route('**/api/quotes*', on_q)
        pg.route('**/api/market', on_m)
    # tag the index line's own /api/market requests (the extras strip fetches the same path every 30 s)
    pg.add_init_script("(() => { const of = window.fetch; window.__mk = []; window.fetch = function (u) { if (String(u).includes('api/market')) window.__mk.push([performance.now(), (new Error().stack || '').includes('ixFetch')]); return of.apply(this, arguments); }; })()")
    pg.goto(url)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in dict({'market': market}, **(store or {})).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    hold['n'] = 0; hold['mk'] = 0; hold['mt'] = []
    pg.reload(); pg.wait_for_timeout(wait)
    return ctx, pg, log, hold


IX = """(() => { const e = document.getElementById('ixl'), sb = document.querySelector('.stagebar');
  if (!e) return { on: false, mode: '', label: null, lines: [], sbh: Math.round(sb.getBoundingClientRect().height), top: Math.round(document.getElementById('map').getBoundingClientRect().top), over: document.documentElement.scrollWidth - innerWidth, nul: false, drawin: false };
  const c = e.querySelector('.ixc');
  const on = !!e.isConnected && !e.hidden && e.getBoundingClientRect().width > 0;
  const lines = [...e.querySelectorAll('svg path.ln')].map(p => { const g = p.parentNode, nums = (p.getAttribute('d').match(/-?[\\d.]+/g) || []).map(Number);
    const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
    return { cls: g.getAttribute('class'), n: xs.length, xmax: Math.max(...xs), ymin: Math.min(...ys), ymax: Math.max(...ys), stroke: getComputedStyle(p).stroke }; });
  const bl = e.querySelector('svg .bl'), dt = [...e.querySelectorAll('svg .dt')].map(d => [+d.getAttribute('cx'), +d.getAttribute('cy')]);
  const r = e.getBoundingClientRect(), mr = document.getElementById('map').getBoundingClientRect();
  return { on, mode: sb.classList.contains('ix-bg') ? 'bg' : sb.classList.contains('ix-row') ? 'row' : e.closest('#crumbs') ? 'in' : '', label: e.getAttribute('aria-label'),
    v: e.querySelector('.ixv').innerText.replace(/\\s+/g, ' ').trim(), t: e.querySelector('.ixt').innerText.replace(/\\s+/g, ' ').trim(), lines, dt,
    y0: bl ? +bl.getAttribute('y1') : null, W: Math.round(c.clientWidth), H: Math.round(c.clientHeight), w: Math.round(r.width), h: Math.round(r.height),
    top: Math.round(mr.top), sbh: Math.round(sb.getBoundingClientRect().height), over: document.documentElement.scrollWidth - innerWidth,
    nul: /\\bnull\\b|undefined|NaN/.test(document.querySelector('.stagebar').innerText + ' ' + (e.getAttribute('aria-label') || '')),
    hint: !!document.querySelector('#crumbs .hint') && getComputedStyle(document.querySelector('#crumbs .hint')).display !== 'none',
    up: getComputedStyle(document.documentElement).getPropertyValue('--up-text').trim(), dn: getComputedStyle(document.documentElement).getPropertyValue('--dn-text').trim(),
    drawin: e.classList.contains('drawin') }; })()"""


def rgb(hexv):
    hexv = hexv.strip().lstrip('#')
    if len(hexv) == 3: hexv = ''.join(c * 2 for c in hexv)
    return 'rgb(%d, %d, %d)' % tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))


KP, KQ = Q['index']['KOSPI'], Q['index']['KOSDAQ']
NSP = len(item(MK, 'KOSPI')['spark'])

with sync_playwright() as p:
    b = launch(p)

    if 'live' in WANT:
        # where it goes and what it says, per width and tab
        want_mode = {'m360': 'bg', 'm390': 'bg', 't768': 'bg', 'd1024': 'row', 'd1280': 'in', 'd1440': 'in', 'd1920': 'in'}
        for vp in ['m360', 'm390', 't768', 'd1024', 'd1280', 'd1440', 'd1920']:
            for mkt in ['K', 'Q', 'ALL']:
                ctx, pg, log, hold = fresh(b, vp, mkt)
                r = pg.evaluate(IX)
                keys = {'K': ['KOSPI'], 'Q': ['KOSDAQ'], 'ALL': ['KOSPI', 'KOSDAQ']}[mkt]
                lab = ' · '.join(f"{'코스피' if k == 'KOSPI' else '코스닥'} 오늘 흐름, 지금 {fmt2(Q['index'][k]['value'])} ({pct(Q['index'][k]['ratio'])})" for k in keys)
                top_ok = (r['top'] == TOP[vp]) if vp in TOP else (r['top'] <= 191 + 40 if vp == 'd1024' else True)
                good = (r['on'] and r['mode'] == want_mode[vp] and r['label'] == lab and len(r['lines']) == len(keys) and all(l['n'] == NSP + 1 for l in r['lines'])
                        and all(l['cls'].split()[0] == 'up' for l in r['lines']) and top_ok and r['over'] == 0 and not r['nul'] and not errs(log))
                ok(f"{vp} {mkt}: {r['mode']} ({r['w']}×{r['h']}), {len(r['lines'])} line(s) of {NSP} bars + the quote, up colour, map top {r['top']}, label '{lab[:44]}…'", good,
                   {k: r[k] for k in ('on', 'mode', 'label', 'top', 'over', 'nul', 'v', 't')} | {'lines': [(l['cls'], l['n']) for l in r['lines']], 'errs': errs(log)[:2]})
                if mkt == 'K' and vp in ('d1280', 'd1920', 'd1024'):
                    ok(f"{vp} B labels: '{r['v']}' · '{r['t']}' (value / %, now / 15:30)", r['v'] == f"{fmt2(KP['value'])} {pct(KP['ratio'])}" and r['t'] == '13:02 / 15:30', (r['v'], r['t']))
                if mkt == 'ALL' and vp == 'd1440':
                    ok(f"d1440 전체 legend names both: '{r['v']}'", r['v'] == f"코스피 {fmt2(KP['value'])} {pct(KP['ratio'])} 코스닥 {fmt2(KQ['value'])} {pct(KQ['ratio'])}", r['v'])
                if vp in ('m390', 't768', 'd1280', 'd1920'): pg.screenshot(path=SHOTS + f'ix-{vp}-{mkt}.png', clip={'x': 0, 'y': max(0, r['top'] - 110), 'width': V[vp]['viewport']['width'], 'height': 150})
                if mkt == 'K' and vp == 'm390':
                    # x axis 09:00 → 15:30: the last point (13:02 = 242 min) sits at 242 / 390 of the width; dashed line = 전일 종가 below a rising line
                    xr = r['dt'][0][0] / r['W']
                    ok(f"m390 x axis fixed 09:00–15:30: the now dot at {xr:.3f} of the width (13:02 → {242 / 390:.3f}); line above the dashed 전일 종가 ({r['lines'][0]['ymax']} < {r['y0']})",
                       abs(xr - 242 / 390) < 0.02 and r['lines'][0]['ymax'] < r['y0'], (r['dt'], r['W'], r['y0']))
                    ok('m390 A: no added height (map top 240), the row text sits above the line (z-order), hint hidden', r['top'] == 240 and pg.evaluate(
                        "getComputedStyle(document.querySelector('.stagebar > .crumbs')).zIndex === '1' && getComputedStyle(document.getElementById('ixl')).pointerEvents === 'none'"), r)
                ctx.close()
        # colour = sign vs 전일 종가, the palette's colours; KOSDAQ mirrored below its base
        mk2, q2 = mirror_kosdaq(MK, Q)
        for pal in ['krg', 'krb']:
            ctx, pg, log, _ = fresh(b, 'd1440', 'ALL', mk=mk2, q=q2, store={'palette2': pal})
            r = pg.evaluate(IX)
            k1, k2 = r['lines']
            ok(f"palette {pal}: 코스피 line up colour {k1['stroke']} = --up-text, 코스닥 (below its close) dn colour {k2['stroke']} = --dn-text and under the dashed line",
               k1['cls'].startswith('up') and k2['cls'].startswith('dn') and k1['stroke'] == rgb(r['up']) and k2['stroke'] == rgb(r['dn']) and k2['ymin'] > r['y0'] - 0.5, (k1, k2, r['up'], r['dn'], r['y0']))
            ctx.close()
        # zoom keeps the index; 테마 · 관심 have none; hover (B) says the time and value
        ctx, pg, log, _ = fresh(b, 'd1280', 'Q')
        pg.click('#map .node.sec > .hd >> nth=0'); pg.wait_for_timeout(700)
        r = pg.evaluate(IX)
        ok(f"sector zoom ({pg.evaluate('document.getElementById(\"crumbs\").innerText').split(chr(10))[0][:30]}…): still the 코스닥 line", r['on'] and r['label'].startswith('코스닥 오늘 흐름') and r['top'] == 191, r['label'])
        c = pg.query_selector('#ixl .ixc').bounding_box()
        x = c['x'] + 4 + (c['width'] - 8) * (60 / 390)            # 10:00
        pg.mouse.move(x, c['y'] + c['height'] / 2); pg.wait_for_timeout(150)
        tip = pg.evaluate("(() => { const t = document.querySelector('#ixl .ixtip'); return t.hidden ? null : t.innerText.replace(/\\s+/g, ' '); })()")
        sp = item(MK, 'KOSDAQ')['spark']; base = KQ['value'] - KQ['change']
        v10 = next(v for t, v in sp if (t + 32400) // 60 % 1440 == 600)
        ok(f"hover at 10:00 → '{tip}'", tip and tip.startswith('10:00') and fmt2(v10) in tip and pct((v10 / base - 1) * 100) in tip, (tip, v10))
        pg.mouse.move(5, 5); pg.wait_for_timeout(100)
        ok('mouse out → tip hidden', pg.evaluate("document.querySelector('#ixl .ixtip').hidden"))
        for tab in ['THEME', 'WATCH']:
            pg.click(f'.tabs button[data-mkt="{tab}"]'); pg.wait_for_timeout(900)
            r = pg.evaluate(IX)
            ok(f'{tab}: no line, header row as before ({r["sbh"]} px, map top {r["top"]})', not r['on'] and r['sbh'] == 36 and (r['top'] == 191 or tab == 'WATCH'), (r['mode'], r['sbh']))
        pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(900)
        ok('back to 코스피: the line again', pg.evaluate(IX)['label'].startswith('코스피 오늘 흐름'))
        ok('live: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # 화려하게 draws the line in once; 기본 never
        for mo, want in [('fancy', True), ('standard', False)]:
            ctx, pg, log, _ = fresh(b, 'd1280', 'K', store={'motion': mo}, wait=0)
            seen = pg.evaluate("""new Promise(res => { let s = false; const t0 = performance.now(); (function f() { const e = document.getElementById('ixl'); if (e && e.classList.contains('drawin')) s = true;
              if (performance.now() - t0 < 4000) requestAnimationFrame(f); else res(s); })(); })""")
            ok(f"{mo}: draw-in {'seen' if seen else 'not seen'}, then static", seen == want and not pg.evaluate(IX)['drawin'], seen)
            ctx.close()

    if 'states' in WANT:
        # a whole day's spark (09:00 … 15:30, 79 bars) ending on the quote's close
        def fullday(day_ts):
            m, q = copy.deepcopy(MK), copy.deepcopy(Q)
            for k in ('KOSPI', 'KOSDAQ'):
                it = item(m, k); x = q['index'][k]; base = x['value'] - x['change']
                it['spark'] = [[day_ts + i * 300, round(base + (x['value'] - base) * i / 78, 2)] for i in range(79)]
                it.update(value=x['value'], change=x['change'], ratio=x['ratio'])
            q['marketStatus'] = {'KOSPI': 'CLOSE', 'KOSDAQ': 'CLOSE'}
            return m, q
        import datetime
        t1110 = int(datetime.datetime(2026, 11, 10, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
        m, q = fullday(t1110); q['asOf'] = '2026-11-10T16:10:00.000000+09:00'
        ctx, pg, log, _ = fresh(b, 'd1280', 'K', mk=m, q=q, clock='2026-11-10T16:10:00+09:00')
        r = pg.evaluate(IX)
        ok(f"after the close (16:10): the whole day to 15:30 ({r['lines'][0]['n'] if r['lines'] else 0} points), '{r['t']}', '{r['label']}'",
           r['on'] and r['lines'][0]['n'] == 79 and r['t'] == '15:30 종가' and r['label'] == f"코스피 오늘 흐름, 종가 {fmt2(KP['value'])} ({pct(KP['ratio'])})" and not errs(log), (r['lines'], r['t'], r['label']))
        ctx.close()
        # next morning before the open: the quotes still carry 11/10's index; the spark is 11/10's → that day, labelled with its date
        m, q = fullday(t1110); q['asOf'] = '2026-11-11T08:20:00.000000+09:00'
        ctx, pg, log, _ = fresh(b, 'm390', 'K', mk=m, q=q, clock='2026-11-11T08:20:00+09:00')
        r = pg.evaluate(IX)
        ok(f"next day 08:20: yesterday's line, '{r['label']}', map top {r['top']}", r['on'] and r['label'] == f"코스피 11월 10일 흐름, 종가 {fmt2(KP['value'])} ({pct(KP['ratio'])})" and r['top'] == 240 and not errs(log), (r['label'], r['top']))
        ctx.close()
        ctx, pg, log, _ = fresh(b, 'd1280', 'K', mk=m, q=q, clock='2026-11-11T08:20:00+09:00')
        r = pg.evaluate(IX)
        ok(f"next day 08:20 B right column '{r['t']}'", r['t'] == '11/10 종가', r['t'])
        ctx.close()
        # /api/market failing: no line, the row as before
        ctx = b.new_context(**V['d1280'], service_workers='block'); pg = ctx.new_page(); log = Log(); log.attach(pg)
        pg.clock.set_fixed_time(CLOCK)
        pg.route('**/api/quotes*', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(Q, ensure_ascii=False)) if '?' not in r.request.url else r.continue_())
        pg.route('**/api/market', lambda r: r.fulfill(status=503, content_type='application/json', body='{"error":"x"}'))
        pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1'); localStorage.setItem('khm.market', '\"K\"')")
        pg.reload(); pg.wait_for_timeout(3000)
        r = pg.evaluate(IX)
        hint = pg.evaluate("!!document.querySelector('#crumbs .hint') && getComputedStyle(document.querySelector('#crumbs .hint')).display !== 'none'")
        ok(f"/api/market 503: no line, the hint back, header row {r['sbh']} px (the strip above shrinks too: map top {r['top']}); only the 503s in the console",
           not r['on'] and hint and r['sbh'] == 36 and not [e for e in errs(log) if '503' not in e], (r['on'], r['sbh'], errs(log)[:2]))
        ctx.close()

    if 'poll' in WANT:
        # each quotes poll appends the live index as the latest point; /api/market again after 60 s
        def hook(body, n):
            for k in ('KOSPI', 'KOSDAQ'):
                x = body['index'][k]; base = x['value'] - x['change']
                v = round(x['value'] * (1 + 0.002 * n), 2); x.update(value=v, change=round(v - base, 2), ratio=round((v / base - 1) * 100, 2))
        ctx, pg, log, hold = fresh(b, 'd1280', 'K', hook=hook)
        n0 = hold['n']; l0 = pg.evaluate(IX)['label']
        while hold['n'] < n0 + 1: pg.wait_for_timeout(300)
        pg.wait_for_timeout(600)
        x = copy.deepcopy(Q['index']['KOSPI']); base = x['value'] - x['change']; v = round(x['value'] * (1 + 0.002 * hold['n']), 2)
        r = pg.evaluate(IX)
        ok(f"a poll moves the latest point: '{l0[-20:]}' → '{r['label'][-20:]}' (= poll {hold['n']}: {fmt2(v)})", fmt2(v) in r['label'] and r['v'].startswith(fmt2(v)) and r['lines'][0]['n'] == NSP + 1, r['label'])
        mine = lambda: [t for t, me in pg.evaluate("window.__mk") if me]
        pg.wait_for_timeout(max(0, int(63000 - (pg.evaluate("performance.now()") - (mine() or [0])[0]))))
        m = mine(); gaps = [round((m[i] - m[i - 1]) / 1000, 1) for i in range(1, len(m))]
        ok(f"the line's own /api/market: once at start, again after ~60 s (gaps {gaps}; the strip's 30 s fetches not counted)", len(m) == 2 and 58 <= gaps[0] <= 63, m)
        ok('poll: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    if 'replay' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1280', 'ALL')
        # today's replay: today's spark up to the frame + the frames' index %
        pg.evaluate("""() => { for (const [t, a, q] of [['1000', 4.1, 3.6], ['1005', 4.3, 3.7]]) KH.setReplay({ t, date: '2026-11-10', prices: new Map(), index: { KOSPI: a, KOSDAQ: q } }); }""")
        pg.wait_for_timeout(200)
        r = pg.evaluate(IX)
        sp = item(MK, 'KOSPI')['spark']; nb = sum(1 for t, v in sp if (t + 32400) // 60 % 1440 - 540 <= 65)
        xmax = 4 + (65 / 390) * (r['W'] - 8)
        ok(f"replay today 10:05: {nb} spark bars ≤ 10:05 (10:00, 10:05 from the frames), cut at 10:05, right '{r['t']}', '…다시 보기 흐름, 지금 …(+4.30%)'",
           r['lines'][0]['n'] == nb and abs(r['lines'][0]['xmax'] - xmax) < 1 and r['t'] == '10:05 / 15:30' and '코스피 10:05 다시 보기 흐름, 지금' in r['label'] and '(+4.30%)' in r['label'], (r['lines'], r['t'], r['label']))
        # an earlier day: only the frames seen (no level, % only)
        pg.evaluate("""() => { for (const [t, a, q] of [['0900', 0.5, -0.2], ['0905', 0.8, -0.6], ['0910', 0.2, -1.1], ['0915', -0.3, -1.4]]) KH.setReplay({ t, date: '2026-11-07', prices: new Map(), index: { KOSPI: a, KOSDAQ: q } }); }""")
        pg.wait_for_timeout(200)
        r = pg.evaluate(IX)
        ok(f"replay 11/07 09:15: 4 frame points per index, % only ('{r['v']}'), 코스피 dn (−0.30%), 코스닥 dn, no 'null'",
           [l['n'] for l in r['lines']] == [4, 4] and r['v'] == '코스피 −0.30% 코스닥 −1.40%' and r['lines'][0]['cls'].startswith('dn') and not r['nul'] and r['t'] == '09:15 / 15:30', (r['lines'], r['v'], r['t'], r['label']))
        pg.screenshot(path=SHOTS + 'ix-replay-d1280.png', clip={'x': 0, 'y': r['top'] - 60, 'width': 1280, 'height': 100})
        # a jump straight to 14:00 with the day's series in frame.ixs (optional extras field): the whole morning is drawn
        pg.evaluate("""() => { const s = (a) => Array.from({ length: 61 }, (_, i) => { const m = 540 + i * 5; return [String(Math.floor(m / 60)).padStart(2, '0') + String(m % 60).padStart(2, '0'), a * Math.sin(i / 9)]; });
          KH.setReplay({ t: '1400', date: '2026-11-06', prices: new Map(), index: { KOSPI: 1.2, KOSDAQ: -0.4 }, ixs: { KOSPI: s(1.5), KOSDAQ: s(-0.8) } }); }""")
        pg.wait_for_timeout(200)
        r = pg.evaluate(IX)
        ok(f"replay jump to 11/06 14:00 with frame.ixs: {[l['n'] for l in r['lines']]} points (09:00–14:00 every 5 min), the frame's own % last ('{r['v']}')",
           [l['n'] for l in r['lines']] == [61, 61] and r['v'] == '코스피 +1.20% 코스닥 −0.40%' and r['t'] == '14:00 / 15:30', (r['lines'], r['v'], r['t']))
        pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(200)
        r = pg.evaluate(IX)
        ok('replay off → the live line again', r['label'].startswith('코스피 오늘 흐름') and r['lines'][0]['n'] == NSP + 1, r['label'])
        ok('replay: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    if 'snapshot' in WANT:
        for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
            ctx, pg, log, _ = fresh(b, vp, 'K', url=SNAP, mocked=False, wait=1500)
            r = pg.evaluate(IX)
            ok(f'snapshot {vp}: no embedded /api/market → no line, header as before (map top {r["top"]}), overflow 0, console 0', not r['on'] and r['over'] == 0 and not errs(log)
               and (r['top'] == {'m390': 234, 'd1280': 191}.get(vp, r['top'])), (r['on'], r['top'], errs(log)[:2]))
            ctx.close()
        # a build that embeds the day's /api/market: a synthetic 11/09 spark ending at the snapshot's close
        snap = json.load(open('/home/claude/hm-heatmap/data/snapshot.json'))
        items = []
        import datetime
        for k in ('KOSPI', 'KOSDAQ'):
            x = snap['index'][k]; base = x['value'] - x['change']
            t0 = int(datetime.datetime(2026, 11, 9, 0, 0, tzinfo=datetime.timezone.utc).timestamp())      # 09:00 KST
            spk = [[t0 + i * 300, round(base + (x['value'] - base) * i / 78 + (base * 0.002 if i % 7 == 3 else 0), 2)] for i in range(79)]
            items.append({'key': k, 'name': k, 'value': x['value'], 'change': x['change'], 'ratio': x['ratio'], 'spark': spk})
        html = open('/home/claude/hm-heatmap/dist/index.html', encoding='utf-8').read()
        blk = '<script id="kh-data-market" type="application/json">' + json.dumps({'asOf': '2026-11-09T06:30:00Z', 'items': items, 'session': {'start': '0900', 'end': '1530'}}) + '</script>'
        tmp = '/tmp/hm2_snap_ix.html'
        open(tmp, 'w', encoding='utf-8').write(html.replace('</body>', blk + '</body>', 1) if '</body>' in html else html + blk)
        for vp in ['m390', 'd1280']:
            ctx, pg, log, _ = fresh(b, vp, 'ALL', url='file://' + tmp, mocked=False, wait=1500)
            r = pg.evaluate(IX)
            ok(f"snapshot + embedded market {vp}: {r['mode']} line of 11/09 to 15:30 ({[l['n'] for l in r['lines']]} points), '{r['label'][:40]}…', map top {r['top']}",
               r['on'] and [l['n'] for l in r['lines']] == [79, 79] and r['label'].startswith('코스피 11월 9일 흐름, 종가 5,018.85') and all(l['cls'].startswith('dn') for l in r['lines'])
               and r['top'] == {'m390': 234, 'd1280': 191}[vp] and not errs(log), (r['label'], r['lines'], r['top'], errs(log)[:2]))
            if vp == 'd1280': ok(f"snapshot B right column '{r['t']}' (that day, 종가)", r['t'] == '11/9 종가', r['t'])
            pg.screenshot(path=SHOTS + f'ix-snapemb-{vp}.png', clip={'x': 0, 'y': max(0, r['top'] - 110), 'width': V[vp]['viewport']['width'], 'height': 150})
            ctx.close()

    if 'quality' in WANT:
        for url, mode in [(URL, 'live'), (SNAP, 'snapshot')]:
            for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
                for mkt in ['K', 'ALL']:
                    ctx, pg, log, _ = fresh(b, vp, mkt, url=url, mocked=False, wait=4000 if mode == 'live' else 1500)
                    r = pg.evaluate(IX)
                    want_on = mode == 'live'
                    tb = {'live': {'m390': 240, 'd1280': 191}, 'snapshot': {'m390': 234, 'd1280': 191}}[mode]
                    ok(f"{mode} {vp} {mkt}: line {'on (' + r['mode'] + ')' if r['on'] else 'off'}, map top {r['top']}, overflow 0, console 0, no null text",
                       r['on'] == want_on and r['over'] == 0 and not errs(log) and not r['nul'] and r['top'] == tb.get(vp, r['top']), (r['on'], r['mode'], r['top'], r['over'], errs(log)[:2], r['label']))
                    if mode == 'live' and mkt == 'K' and vp in ('m390', 't768', 'd1280', 'd1920'):
                        pg.screenshot(path=SHOTS + f'ix-real-{vp}.png', clip={'x': 0, 'y': max(0, r['top'] - 110), 'width': V[vp]['viewport']['width'], 'height': 150})
                    ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
