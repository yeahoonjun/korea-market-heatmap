#!/usr/bin/env python3
"""End-to-end checks for the stock page (src/stock) against the mock API.

    python3 scripts/build_page.py && python3 qa/stock/test_stock.py      [--extra-only: 뉴스·공시 / 관심종목 / 상·하한가 / 종목 정보]
                                                                          [--info-only: just 종목 정보 / 범위 막대 / 같은 업종 / 오늘 순매수]

Starts qa/stock/mock_api.py on 127.0.0.1:8792, runs Playwright (Chrome), stops the server.
Screenshots → qa/shots/stock/ (git-ignored). Summary → qa/stock/results.json.
"""
import json, pathlib, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SHOTS = ROOT / 'qa/shots/stock'
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8792/'
SNAP = (ROOT / 'dist/index.html').as_uri()
VP = {
    360: dict(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True, device_scale_factor=2),
    390: dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    768: dict(viewport={'width': 768, 'height': 1024}),
    1280: dict(viewport={'width': 1280, 'height': 800}),
    1440: dict(viewport={'width': 1440, 'height': 900}),
    1920: dict(viewport={'width': 1920, 'height': 1080}),
}
R = {}           # results
FAILS = []


def check(name, ok, detail=None):
    R[name] = {'ok': bool(ok), 'detail': detail}
    print(('PASS ' if ok else 'FAIL ') + name + ('' if detail is None else '  ' + json.dumps(detail, ensure_ascii=False)[:300]), flush=True)
    if not ok:
        FAILS.append(name)


def mock(path):
    with urllib.request.urlopen(BASE + path.lstrip('/'), timeout=10) as r:
        return json.loads(r.read())


class Page:
    def __init__(self, browser, w, url, **extra):
        opts = dict(VP[w]); opts.update(extra)
        self.ctx = browser.new_context(**opts)
        self.pg = self.ctx.new_page()
        self.console, self.reqs = [], []
        self.ign = 0   # heatmap-side 404s the mock does not serve (data/close.json, api/breadth) are not the stock page's
        self.pg.on('response', lambda r: setattr(self, 'ign', self.ign + 1) if r.status == 404 and ('/data/close.json' in r.url or '/api/breadth' in r.url) else None)
        self.pg.on('console', self._console)
        self.pg.on('pageerror', lambda e: self.console.append(f'pageerror: {e}'))
        self.pg.on('request', lambda r: self.reqs.append((time.time(), r.url)))
        if url:
            self.pg.goto(url)

    def _console(self, m):
        if m.type not in ('error', 'warning'):
            return
        if m.type == 'error' and 'Failed to load resource' in m.text and self.ign > 0:
            self.ign -= 1
            return
        self.console.append(f'{m.type}: {m.text}')

    def count(self, frag, since=0):
        return sum(1 for t, u in self.reqs if frag in u and t >= since)

    def ev(self, js, arg=None):
        return self.pg.evaluate(js, arg) if arg is not None else self.pg.evaluate(js)

    def wait_chart(self, timeout=8000):
        self.pg.wait_for_function("() => { const m = document.querySelector('.sp-chartmsg'); return m && !m.classList.contains('on') && document.querySelector('.sp-legend').textContent.length > 0 }", timeout=timeout)

    def close(self):
        self.ctx.close()


OVERFLOW_JS = r"""() => {
  const root = document.getElementById('kh-stock');
  const vw = innerWidth, out = [];
  if (root && !root.hidden) for (const el of root.querySelectorAll('*')) {
    if (el.closest('.sp-peer-list') || el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > vw + 0.5 || r.left < -0.5)) out.push(`${el.tagName.toLowerCase()}.${String(el.className.baseVal ?? el.className).split(' ')[0]} ${Math.round(r.left)}..${Math.round(r.right)}`);
  }
  return { doc: document.documentElement.scrollWidth - innerWidth, root: root ? root.scrollWidth - root.clientWidth : null, els: out.slice(0, 5), n: out.length };
}"""

TAP_JS = r"""() => {
  const root = document.getElementById('kh-stock'), small = [];
  for (const el of root.querySelectorAll('button, a')) {
    if (el.closest('[hidden]') || el.closest('.sp-chart') || el.closest('.sp-foot p')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (r.height < 40 || r.width < 40) small.push(`${el.className || el.tagName}:${el.textContent.trim().slice(0, 10)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return small;
}"""

# count canvas pixels close to the given colours inside the chart
PIXELS_JS = r"""(cols) => {
  const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const targets = cols.map(hex), counts = cols.map(() => 0);
  for (const cv of document.querySelectorAll('.sp-chart canvas')) {
    if (!cv.width || !cv.height) continue;
    let d;
    try { d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; } catch (e) { continue; }
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 250) continue;
      targets.forEach((t, k) => { if (Math.abs(d[i] - t[0]) < 8 && Math.abs(d[i + 1] - t[1]) < 8 && Math.abs(d[i + 2] - t[2]) < 8) counts[k]++; });
    }
  }
  return counts;
}"""


def run(b):
    # ── 1. open / close via API, Esc, back button, browser back; focus return; hashes ──────────
    P = Page(b, 1280, BASE + '#kosdaq')
    pg = P.pg
    pg.wait_for_timeout(1500)
    check('khstock_api', P.ev("() => typeof KHStock === 'object' && ['open','close','isOpen'].every(k => typeof KHStock[k] === 'function')"))
    mk = lambda: P.ev("() => document.querySelector('.tabs button[aria-pressed=true]').textContent")
    check('heatmap_market_kosdaq_before', mk() == '코스닥', mk())
    opener = "() => { const b = document.querySelectorAll('.secs button')[1]; b.focus(); return b.textContent; }"
    P.ev(opener)
    hl0 = P.ev('history.length')
    P.ev("() => KHStock.open('005930', { opener: document.activeElement })")
    pg.wait_for_timeout(300)
    st = P.ev("() => ({ hash: location.hash, open: KHStock.isOpen(), vis: !document.getElementById('kh-stock').hidden, hl: history.length, inert: document.querySelector('main.layout').inert, title: document.title })")
    check('open_sets_hash_and_shows', st['hash'] == '#s-005930' and st['open'] and st['vis'] and st['hl'] == hl0 + 1 and st['inert'], st)
    P.wait_chart()
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(400)
    st = P.ev("() => ({ hash: location.hash, open: KHStock.isOpen(), vis: !document.getElementById('kh-stock').hidden, focus: document.activeElement && document.activeElement.textContent, inert: document.querySelector('main.layout').inert, title: document.title })")
    check('esc_closes_restores_hash_focus', st['hash'] == '#kosdaq' and not st['open'] and not st['vis'] and st['focus'] and not st['inert'] and st['title'] == '한국 증시 히트맵', st)
    check('heatmap_market_kept_after_close', mk() == '코스닥', mk())
    # browser back
    P.ev(opener); P.ev("() => KHStock.open('196170', { opener: document.activeElement })"); pg.wait_for_timeout(500)
    pg.go_back(); pg.wait_for_timeout(500)
    st = P.ev("() => ({ hash: location.hash, open: KHStock.isOpen(), focusIsSecBtn: document.activeElement === document.querySelectorAll('.secs button')[1] })")
    check('browser_back_closes_focus_returns', st['hash'] == '#kosdaq' and not st['open'] and st['focusIsSecBtn'], st)
    # forward re-opens (address is shareable / history-aware)
    pg.go_forward(); pg.wait_for_timeout(500)
    check('browser_forward_reopens', P.ev("() => KHStock.isOpen() && location.hash === '#s-196170'"))
    pg.go_back(); pg.wait_for_timeout(300)
    # back button in the page header
    P.ev(opener); P.ev("() => KHStock.open('005930', { opener: document.activeElement })"); pg.wait_for_timeout(400)
    pg.click('.sp-back'); pg.wait_for_timeout(400)
    st = P.ev("() => ({ hash: location.hash, open: KHStock.isOpen(), focusIsSecBtn: document.activeElement === document.querySelectorAll('.secs button')[1] })")
    check('back_button_closes_focus_returns', st['hash'] == '#kosdaq' and not st['open'] and st['focusIsSecBtn'], st)
    # switching to a peer updates in place (one history entry)
    P.ev("() => KHStock.open('005930')"); pg.wait_for_timeout(400)
    hl1 = P.ev('history.length')
    peer = P.ev("() => document.querySelector('.sp-peer .nm').textContent")
    pg.click('.sp-peer'); pg.wait_for_timeout(600)
    st = P.ev("() => ({ hash: location.hash, open: KHStock.isOpen(), name: document.getElementById('sp-name').textContent, hl: history.length })")
    check('peer_switch_in_place', st['open'] and st['hash'] != '#s-005930' and st['hash'].startswith('#s-') and st['name'] == peer and st['hl'] == hl1, st)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    check('peer_then_esc_back_to_map', P.ev("() => !KHStock.isOpen() && location.hash === '#kosdaq'"))
    # Esc does not leak to the heatmap (it would zoom out / close its sheet)
    check('console_clean_nav', not P.console, P.console)
    P.close()

    # ── 2. load with #s-<code> ───────────────────────────────
    P = Page(b, 390, BASE + '#s-196170')
    pg = P.pg
    P.wait_chart()
    st = P.ev("() => ({ open: KHStock.isOpen(), name: document.getElementById('sp-name').textContent, path: document.querySelector('.sp-path').textContent })")
    check('open_on_load_from_hash', st['open'] and st['name'] == '알테오젠', st)
    pg.click('.sp-back'); pg.wait_for_timeout(400)
    st = P.ev("() => ({ open: KHStock.isOpen(), hash: location.hash, url: location.href })")
    check('close_from_shared_link_clears_hash', not st['open'] and st['hash'] == '', st)
    check('console_clean_hashload', not P.console, P.console)
    P.close()

    # ── 3. timeframes, legend, KST, palette ───────────────────
    P = Page(b, 390, BASE + '#s-005930', timezone_id='America/New_York')
    pg = P.pg
    P.wait_chart()
    tfs = {}
    for tf in ['1m', '5m', 'day', 'week', 'month', 'year']:
        since = time.time()
        pg.click(f'.sp-tfs button[data-tf="{tf}"]')
        P.wait_chart()
        pg.wait_for_timeout(250)
        info = P.ev("() => ({ legend: document.querySelector('.sp-legend').textContent, aria: document.querySelector('.sp-chart').getAttribute('aria-label'), canvases: document.querySelectorAll('.sp-chart canvas').length, pressed: document.querySelector('.sp-tfs [aria-pressed=true]').dataset.tf })")
        info['req'] = P.count('chart?', since)
        tfs[tf] = info
        pg.screenshot(path=str(SHOTS / f'live390_tf_{tf}.png'))
    check('all_6_timeframes_render', all(v['legend'] and v['canvases'] >= 3 and v['pressed'] == k and '봉' in v['aria'] for k, v in tfs.items()), {k: v['aria'][-40:] for k, v in tfs.items()})
    # KST even though the browser is in New York: the first 1d bar is 09:00
    pg.click('.sp-tfs button[data-tf="1m"]'); P.wait_chart()
    aria = P.ev("() => document.querySelector('.sp-chart').getAttribute('aria-label')")
    check('times_in_kst', '9:00' in aria or '09:00' in aria, aria)
    # crosshair legend follows the pointer
    box = pg.query_selector('.sp-chart').bounding_box()
    pg.mouse.move(box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.4)
    pg.wait_for_timeout(200)
    lg_hover = P.ev("() => document.querySelector('.sp-legend').textContent")
    check('crosshair_legend_updates', lg_hover and '17:2' not in lg_hover.split('시')[0], lg_hover[:60])
    # 전일 종가 on 1일 = the header's 기준가 (summary price − change = 188,700), not the chart API's prevClose
    # (193,500 = the previous day's KRX+NXT close); the legend's % for the last bar matches the header's %.
    P.pg.set_viewport_size({'width': 768, 'height': 1024})   # .sp-period is shown from 700 px
    pg.mouse.move(5, 5); pg.wait_for_timeout(300)
    ref = P.ev("""() => ({ period: document.querySelector('.sp-period').textContent,
        legend: document.querySelector('.sp-legend .sp-lg-r').textContent, head: document.querySelector('.sp-chg').textContent })""")
    check('prev_close_ref_is_header_base_1d', '전일 종가 188,700 대비' in ref['period'] and ref['legend'] in ref['head'] and ref['legend'] in ref['period'], ref)
    pg.click('.sp-tfs button[data-tf="5m"]'); P.wait_chart(); pg.wait_for_timeout(200)
    p5 = P.ev("() => document.querySelector('.sp-period').textContent")
    # 5일: from the close before the window (11/02) to the last bar, not from the first bar's open
    j5 = mock('/api/stock/005930/chart?tf=5d')
    want = '%.2f%%' % abs((j5['bars'][-1]['c'] / j5['prevClose'] - 1) * 100)
    check('period_base_5d_is_close_before_window', p5.startswith('5일 동안') and p5.endswith(want), {'shown': p5, 'want': want, 'prevClose': j5['prevClose']})
    P.pg.set_viewport_size({'width': 390, 'height': 844})
    pg.click('.sp-tfs button[data-tf="1m"]'); P.wait_chart(); pg.wait_for_timeout(200)
    # palette: krg (red up / green down) → global (green up / red down)
    pal0 = P.ev("() => KH.palette()")
    c0 = P.ev(PIXELS_JS, [pal0['up'], pal0['down']])
    P.ev("() => document.querySelector('#palseg button[data-v=\"global\"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))")
    pg.wait_for_timeout(400)
    pal1 = P.ev("() => KH.palette()")
    c1 = P.ev(PIXELS_JS, [pal0['up'], pal0['down'], pal1['up'], pal1['down']])
    check('palette_recolours_candles', pal1['key'] == 'global' and c0[0] > 50 and c0[1] > 50 and c1[0] < c0[0] * 0.1 and c1[1] < c0[1] * 0.1 and c1[2] > 50 and c1[3] > 50,
          {'before_up_dn': c0, 'after_old_up_dn_new_up_dn': c1})
    pg.screenshot(path=str(SHOTS / 'live390_palette_global.png'))
    P.ev("() => document.querySelector('#palseg button[data-v=\"krg\"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))")
    page_console = [m for m in P.console if 'willReadFrequently' not in m]   # the pixel probe above causes these
    check('console_clean_tf_palette', not page_console, page_console)
    P.close()

    # ── 3b. moving averages (the mock answers like the Worker deployed before iv=: the page falls back to tf=, no scroll-back) ──
    P = Page(b, 1280, BASE + '#s-005930')
    pg = P.pg
    P.wait_chart()
    pg.click('.sp-tfs button[data-tf="day"]'); P.wait_chart(); pg.wait_for_timeout(300)
    bars = mock('/api/stock/005930/chart?tf=1y')['bars']
    cl = [x['c'] for x in bars]
    fmt = lambda v: f'{round(v):,}'
    ma = lambda n, i: sum(cl[i - n + 1:i + 1]) / n
    chips = P.ev("() => [...document.querySelectorAll('.sp-mac')].map(b => ({ n: b.dataset.n, on: b.getAttribute('aria-pressed'), t: b.querySelector('.n').textContent, v: b.querySelector('.v').textContent, c: getComputedStyle(b.querySelector('.n')).color }))")
    last = len(cl) - 1
    want = {n: fmt(ma(int(n), last)) if last >= int(n) - 1 else '–' for n in ('5', '20', '60', '120')}
    check('ma_chips_daily_all_on_labels_unit', [c['t'] for c in chips] == ['5일', '20일', '60일', '120일'] and all(c['on'] == 'true' for c in chips), chips)
    check('ma_values_match_hand_calc_last_bar', all(c['v'] == want[c['n']] for c in chips), {'shown': [c['v'] for c in chips], 'want': want})
    check('ma_colours_distinct_not_red_green', len({c['c'] for c in chips}) == 4, [c['c'] for c in chips])
    # hover: the bar under the pointer → its date → hand-calculated MA20 / MA60
    h0 = P.ev("() => document.querySelector('.sp-ma').getBoundingClientRect().height")
    box = pg.query_selector('.sp-chart').bounding_box()
    pg.mouse.move(box['x'] + box['width'] * 0.5, box['y'] + box['height'] * 0.4); pg.wait_for_timeout(300)
    lg = P.ev("() => document.querySelector('.sp-legend .sp-lg-t').textContent")
    d = lg.split(' ')[0].replace('.', '-')
    idx = next((i for i, x in enumerate(bars) if x['t'] == d), None)
    hv = P.ev("() => Object.fromEntries([...document.querySelectorAll('.sp-mac')].map(b => [b.dataset.n, b.querySelector('.v').textContent]))")
    check('ma_hover_values_match_hand_calc', idx is not None and idx >= 59 and hv['20'] == fmt(ma(20, idx)) and hv['60'] == fmt(ma(60, idx)) and hv['5'] == fmt(ma(5, idx)), {'date': d, 'idx': idx, 'shown': hv})
    h1 = P.ev("() => document.querySelector('.sp-ma').getBoundingClientRect().height")
    check('ma_row_height_reserved', abs(h0 - h1) < 0.5 and h0 > 20, [h0, h1])
    # toggle + remembered
    pg.click('.sp-mac[data-n="5"]'); pg.wait_for_timeout(150)
    st = P.ev("() => ({ on: document.querySelector('.sp-mac[data-n=\"5\"]').getAttribute('aria-pressed'), v: document.querySelector('.sp-mac[data-n=\"5\"] .v').textContent, ls: localStorage.getItem('khm.stock.ma'), vis: window.__x })")
    check('ma_toggle_off_stored', st['on'] == 'false' and st['v'] == '' and '"day":[20,60,120]' in (st['ls'] or ''), st)
    pg.reload(); pg.wait_for_selector('.sp-mac'); P.wait_chart()
    st = P.ev("() => [...document.querySelectorAll('.sp-mac')].map(b => b.getAttribute('aria-pressed')).join()")
    check('ma_toggle_remembered_after_reload', st == 'false,true,true,true', st)
    # defaults per interval: 분 = 5·20·60
    pg.click('.sp-tfs button[data-tf="1m"]'); P.wait_chart(); pg.wait_for_timeout(200)
    st = P.ev("() => ({ t: [...document.querySelectorAll('.sp-mac .n')].map(b => b.textContent).join(), on: [...document.querySelectorAll('.sp-mac')].map(b => b.getAttribute('aria-pressed')).join() })")
    check('ma_intraday_defaults_5_20_60', st['t'] == '5분,20분,60분,120분' and st['on'] == 'true,true,true,false', st)
    # the old-Worker path: no iv answer → tf= form, nothing breaks
    check('ma_falls_back_to_tf_form', P.count('chart?tf=') > 0 and not [m for m in P.console if 'willReadFrequently' not in m and 'Failed to load resource' not in m], P.console)   # (the heatmap's own 404s are in the baseline)
    check('ma_no_overflow_1280', P.ev("() => document.documentElement.scrollWidth - innerWidth") == 0)
    pg.screenshot(path=str(SHOTS / 'live1280_ma.png'))
    P.close()

    # ── 4. order-book polling (during the regular session; the clock is pinned so the run does not depend on the time of day) ──
    mock('/__reset')
    mock('/__config?status=OPEN&asof=2026-11-09T10:29:50%2B09:00')
    P = Page(b, 1280, None)
    pg = P.pg
    pg.clock.set_fixed_time('2026-11-09T10:30:00+09:00')
    pg.goto(BASE)
    pg.wait_for_timeout(800)
    P.ev("() => localStorage.setItem('khm.stockTab', JSON.stringify('ob'))")
    t0 = time.time()
    P.ev("() => KHStock.open('005930')")
    pg.wait_for_timeout(10000)
    n_open = P.count('/orderbook', t0)
    pg.click('#sp-t-inv'); t1 = time.time(); pg.wait_for_timeout(300); t1b = time.time()
    pg.wait_for_timeout(7000)
    n_other_tab = P.count('/orderbook', t1b)
    pg.click('#sp-t-ob'); t2 = time.time()
    pg.wait_for_timeout(7000)
    n_back = P.count('/orderbook', t2)
    P.ev("() => { Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' }); Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')); }")
    t3 = time.time(); pg.wait_for_timeout(300); t3b = time.time()
    pg.wait_for_timeout(7000)
    n_hidden = P.count('/orderbook', t3b)
    P.ev("() => { Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' }); Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); }")
    t4 = time.time(); pg.wait_for_timeout(4000)
    n_visible = P.count('/orderbook', t4)
    ob_rows = P.ev("() => [...document.querySelectorAll('.sp-p b')].filter(b => b.textContent).length")
    pg.keyboard.press('Escape'); t5 = time.time(); pg.wait_for_timeout(300); t5b = time.time()
    pg.wait_for_timeout(7000)
    n_closed = P.count('/orderbook', t5b)
    polls = dict(open_10s=n_open, other_tab_7s=n_other_tab, back_7s=n_back, hidden_7s=n_hidden, visible_4s=n_visible, closed_7s=n_closed, levels=ob_rows)
    polls['browser_total'] = P.count('/orderbook', t0)
    polls['server_total'] = mock('/__stats').get('orderbook', 0)
    check('orderbook_polling_rules', 3 <= n_open <= 5 and n_other_tab == 0 and 2 <= n_back <= 4 and n_hidden == 0 and 1 <= n_visible <= 3 and n_closed == 0
          and ob_rows == 10 and polls['server_total'] == polls['browser_total'], polls)
    check('console_clean_polling', not P.console, P.console)
    P.close()
    mock('/__reset')

    # ── 5. tabs: 투자자 / 일별 시세 / keyboard ─────────────────
    P = Page(b, 390, BASE + '#s-005930')
    pg = P.pg
    P.wait_chart()
    pg.click('#sp-t-inv')
    pg.wait_for_selector('.sp-inv-t tbody tr')
    inv = P.ev("() => ({ rows: document.querySelectorAll('.sp-inv-t tbody tr').length, cum: [...document.querySelectorAll('.sp-cum-r b')].map(b => b.textContent), unit: document.querySelector('.sp-cum-h small').textContent, note: document.querySelector('#sp-p-inv .sp-note').textContent, colored: [...document.querySelectorAll('.sp-inv-t tbody tr:first-child td')].slice(3, 6).map(td => getComputedStyle(td).color) })")
    check('investors_tab', inv['rows'] == 60 and len(inv['cum']) == 3 and '주' in inv['unit'] and '다음 날' in inv['note'], inv)
    pg.evaluate("() => { const r = document.getElementById('kh-stock'); r.scrollTop = document.querySelector('.sp-tabwrap').offsetTop - 60; }")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(SHOTS / 'live390_tab_inv.png'))
    pg.click('#sp-t-daily')
    pg.wait_for_selector('.sp-daily-t tbody tr')
    d1 = P.ev("() => document.querySelectorAll('.sp-daily-t tbody tr').length")
    pg.click('.sp-more'); pg.wait_for_function("() => document.querySelectorAll('.sp-daily-t tbody tr').length > 60")
    d2 = P.ev("() => document.querySelectorAll('.sp-daily-t tbody tr').length")
    pg.click('.sp-more'); pg.wait_for_function("() => document.querySelectorAll('.sp-daily-t tbody tr').length > 120")
    pg.wait_for_timeout(300)
    d3 = P.ev("() => ({ rows: document.querySelectorAll('.sp-daily-t tbody tr').length, moreHidden: document.querySelector('.sp-more').hidden })")
    check('daily_tab_paging', d1 == 60 and d2 == 120 and d3['rows'] == 180 and d3['moreHidden'], [d1, d2, d3])
    pg.screenshot(path=str(SHOTS / 'live390_tab_daily.png'))
    pg.focus('#sp-t-daily'); pg.keyboard.press('ArrowRight')
    k1 = P.ev("() => ({ sel: document.querySelector('[role=tab][aria-selected=true]').id, focus: document.activeElement.id })")
    pg.keyboard.press('ArrowRight')
    k = P.ev("() => ({ sel: document.querySelector('[role=tab][aria-selected=true]').id, focus: document.activeElement.id })")
    check('tabs_keyboard_arrows', k1 == {'sel': 'sp-t-news', 'focus': 'sp-t-news'} and k == {'sel': 'sp-t-ob', 'focus': 'sp-t-ob'}, [k1, k])
    taps = P.ev(TAP_JS)
    check('tap_targets_40px_mobile', not taps, taps)
    check('console_clean_tabs', not P.console, P.console)
    P.close()

    # ── 6. states: loading, error+retry, not found, empty, phases ─────
    mock('/__reset')
    mock('/__config?delay=2500')
    P = Page(b, 390, BASE + '#s-005930')
    pg = P.pg
    pg.wait_for_timeout(1200)
    sk = P.ev("() => ({ chart: !!document.querySelector('.sp-chart-skel'), head: document.querySelectorAll('.sp-head .sp-skel, .sp-stats .sp-skel').length, ob: !!document.querySelector('#sp-p-ob .sp-skel-rows') })")
    pg.screenshot(path=str(SHOTS / 'live390_loading.png'))
    check('loading_skeletons', sk['chart'] and sk['head'] > 0 and sk['ob'], sk)
    P.close()
    mock('/__config?delay=')

    P = Page(b, 390, BASE + '#s-999990')
    pg = P.pg
    pg.wait_for_timeout(2000)
    er = P.ev("() => ({ meta: document.querySelector('.sp-meta').textContent, chart: document.querySelector('.sp-chartmsg').textContent, ob: document.querySelector('#sp-p-ob').textContent.slice(0, 40), retry: document.querySelectorAll('.sp-chartmsg .sp-btn, .sp-meta .sp-link').length })")
    check('error_states_with_retry', '불러오지 못했어요' in er['meta'] and '불러오지 못했어요' in er['chart'] and '불러오지 못했어요' in er['ob'] and er['retry'] == 2, er)
    pg.screenshot(path=str(SHOTS / 'live390_error.png'))
    P.close()

    mock('/__config?fail=chart')
    P = Page(b, 1280, BASE + '#s-005930')
    pg = P.pg
    pg.wait_for_selector('.sp-chartmsg .sp-btn')
    mock('/__config?fail=')
    pg.click('.sp-chartmsg .sp-btn')
    P.wait_chart()
    check('retry_recovers_chart', True)
    P.close()

    P = Page(b, 390, BASE + '#s-000000')
    pg = P.pg
    pg.wait_for_timeout(1500)
    nf = P.ev("() => ({ nf: document.getElementById('kh-stock').classList.contains('sp-nf'), meta: document.querySelector('.sp-meta').textContent })")
    check('not_found_state', nf['nf'] and '찾지 못했어요' in nf['meta'], nf)
    P.close()

    P = Page(b, 390, BASE + '#s-999980')
    pg = P.pg
    pg.wait_for_timeout(1800)
    em = {'chart': P.ev("() => document.querySelector('.sp-chartmsg').textContent"), 'ob': P.ev("() => document.querySelector('#sp-p-ob').textContent")}
    pg.click('#sp-t-inv'); pg.wait_for_timeout(500); em['inv'] = P.ev("() => document.querySelector('#sp-p-inv').textContent")
    pg.click('#sp-t-daily'); pg.wait_for_timeout(500); em['daily'] = P.ev("() => document.querySelector('#sp-p-daily').textContent")
    check('empty_states', ('거래 기록이 없어요' in em['chart'] or '아직 거래가 없어요' in em['chart']) and '호가가 없어요' in em['ob'] and '기록이 없어요' in em['inv'] and '일별 시세가 없어요' in em['daily'], em)
    check('console_clean_empty', not P.console, P.console)
    P.close()

    # session phases (fake the KST clock; the mock's summary carries asOf/marketStatus)
    def phase(at, mock_q, label):
        mock('/__reset')
        if mock_q:
            mock('/__config?' + mock_q)
        P = Page(b, 1280, None)
        P.pg.clock.set_fixed_time(at)
        t0 = time.time()
        P.pg.goto(BASE + '#s-005930')
        P.pg.wait_for_timeout(7500)
        out = P.ev("() => ({ chip: document.querySelector('.sp-chip') && document.querySelector('.sp-chip').textContent, meta: document.querySelector('.sp-meta').textContent, note: document.querySelector('#sp-p-ob .sp-note').textContent })")
        out['ob_reqs_7s'] = P.count('/orderbook', t0)
        P.pg.screenshot(path=str(SHOTS / f'phase_{label}.png'))
        P.close()
        return out
    ph = {
        'open': phase('2026-11-09T10:30:00+09:00', 'status=OPEN&asof=2026-11-09T10:29:50%2B09:00', 'open'),
        'after': phase('2026-11-09T17:40:00+09:00', '', 'after'),
        'closed': phase('2026-11-09T21:00:00+09:00', '', 'closed'),
        'holiday': phase('2026-11-10T11:00:00+09:00', '', 'holiday'),
        'weekend': phase('2026-11-14T11:00:00+09:00', '', 'weekend'),
    }
    mock('/__reset')
    ok = (ph['open']['chip'] == '장 중' and 'NXT' not in ph['open']['meta'] and ph['open']['ob_reqs_7s'] >= 3
          and ph['after']['chip'] == '시간외' and 'NXT' in ph['after']['meta'] and ph['after']['ob_reqs_7s'] >= 3
          and ph['closed']['chip'] == '장 마감' and 'NXT' in ph['closed']['meta'] and ph['closed']['ob_reqs_7s'] <= 2
          and ph['holiday']['chip'] == '휴장' and '열리지 않아요' in ph['holiday']['meta'] and ph['holiday']['ob_reqs_7s'] <= 2
          and ph['weekend']['chip'] == '주말 휴장')
    check('market_phases', ok, {k: (v['chip'], v['ob_reqs_7s'], 'NXT' in v['meta']) for k, v in ph.items()})

    # reduced motion
    P = Page(b, 390, BASE + '#s-005930', reduced_motion='reduce')
    P.pg.wait_for_timeout(300)
    rm = P.ev("() => ({ anim: getComputedStyle(document.getElementById('kh-stock')).animationName, skel: (document.querySelector('.sp-skel') ? getComputedStyle(document.querySelector('.sp-skel')).animationName : 'none') })")
    check('reduced_motion', rm['anim'] == 'none' and rm['skel'] == 'none', rm)
    P.close()

    # ── 7. overflow at five widths, each tab; screenshots ──────────────
    ov = {}
    for w in (360, 390, 768, 1280, 1920):
        P = Page(b, w, BASE + '#s-005930')
        P.wait_chart()
        for tab in ('ob', 'info', 'inv', 'daily', 'news'):
            P.pg.click(f'#sp-t-{tab}')
            P.pg.wait_for_timeout(700)
            o = P.ev(OVERFLOW_JS)
            # every tab label fits inside its button (four tabs on a 360 px phone)
            o['clipped'] = P.ev("() => [...document.querySelectorAll('.sp-tabs button, .sp-tfs button, .sp-nwseg button')].filter(b => b.offsetWidth && b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)")
            o['n'] += len(o['clipped'])
            ov[f'{w}_{tab}'] = o
        P.pg.click('#sp-t-ob'); P.pg.wait_for_timeout(500)
        P.pg.screenshot(path=str(SHOTS / f'live{w}.png'))
        if not P.console:
            pass
        else:
            ov[f'{w}_console'] = P.console
        P.close()
    bad = {k: v for k, v in ov.items() if isinstance(v, dict) and (v['doc'] or v['root'] or v['n'])}
    check('no_horizontal_overflow_live', not bad and not any(k.endswith('console') for k in ov), bad or None)
    P = Page(b, 1440, BASE + '#s-005930'); P.wait_chart(); P.pg.wait_for_timeout(500)
    P.pg.screenshot(path=str(SHOTS / 'live1440.png')); P.close()

    # ── 8. snapshot build: header from KH.stock, fallback + link, zero api requests ──
    for w in (390, 1440, 360, 768, 1280, 1920):
        P = Page(b, w, SNAP + '#s-005930')
        P.pg.wait_for_timeout(1200)
        s = P.ev("() => ({ open: KHStock.isOpen(), name: document.getElementById('sp-name').textContent, price: document.querySelector('.sp-price').textContent, href: document.querySelector('.sp-offline a').href, live: KH.LIVE_URL, text: document.querySelector('.sp-offline h2').textContent, chart: !!document.querySelector('.sp-chart') })")
        s['api'] = [u for _, u in P.reqs if 'api/' in u]
        s['lwc'] = [u for _, u in P.reqs if 'lightweight' in u]
        s['overflow'] = P.ev(OVERFLOW_JS)
        if w in (390, 1440):
            P.pg.screenshot(path=str(SHOTS / f'snap{w}.png'))
            ok = (s['open'] and s['name'] == '삼성전자' and s['price'] and s['href'] == s['live'] + '#s-005930' and '실시간 버전에서 볼 수 있어요' in s['text']
                  and not s['chart'] and not s['api'] and not s['lwc'])
            check(f'snapshot_fallback_{w}', ok, {k: v for k, v in s.items() if k != 'overflow'})
            P.pg.keyboard.press('Escape'); P.pg.wait_for_timeout(300)
            check(f'snapshot_esc_{w}', P.ev("() => !KHStock.isOpen() && location.hash === ''"))
            # a peer switch works offline too
            P.ev("() => KHStock.open('000660')"); P.pg.wait_for_timeout(300)
            check(f'snapshot_open_other_{w}', P.ev("() => document.getElementById('sp-name').textContent") == 'SK하이닉스')
        o = s['overflow']
        check(f'snapshot_no_overflow_{w}', not (o['doc'] or o['root'] or o['n']), o)
        check(f'snapshot_zero_api_{w}', not [u for _, u in P.reqs if 'api/' in u], [u for _, u in P.reqs if 'api/' in u][:3])
        check(f'snapshot_console_{w}', not P.console, P.console)
        P.close()


WATCH_STUB = r"""() => {
  // the heatmap's KH.watch (AGENTS.md §3-2); this stand-in is used only when a build lacks it
  if (KH.watch) return;
  const set = new Set(JSON.parse(localStorage.getItem('khm.watch') || '[]'));
  KH.watch = {
    has: c => set.has(c),
    toggle: c => { set.has(c) ? set.delete(c) : set.add(c); localStorage.setItem('khm.watch', JSON.stringify([...set]));
      document.dispatchEvent(new CustomEvent('kh:watch', { detail: { code: c, on: set.has(c) } })); return set.has(c); },
    list: () => [...set],
  };
}"""
NEWS_JS = r"""() => ({
  pressed: [...document.querySelectorAll('.sp-nwseg button')].map(b => [b.dataset.kind, b.getAttribute('aria-pressed'), b.textContent]),
  rows: document.querySelectorAll('#sp-p-news .sp-nw-list li').length,
  titles: [...document.querySelectorAll('#sp-p-news .sp-nw-t')].map(t => t.textContent),
  times: [...document.querySelectorAll('#sp-p-news time')].map(t => t.textContent),
  press: [...document.querySelectorAll('#sp-p-news .sp-nw-press')].map(t => t.textContent),
  links: [...document.querySelectorAll('#sp-p-news a.sp-nw-a')].map(a => [a.getAttribute('href'), a.target, a.rel]),
  tags: document.querySelectorAll('#sp-p-news .sp-nw-tag').length,
  msg: (document.querySelector('#sp-p-news .sp-msgbox') || {}).textContent || '',
  note: document.querySelector('#sp-p-news .sp-note').textContent,
  src: (document.querySelector('#sp-p-news .sp-nw-src:not([hidden])') || {}).textContent || '',
  filters: [...document.querySelectorAll('#sp-p-news .sp-dfilt:not([hidden]) button')].filter(b => !b.hidden).map(b => [b.dataset.f, b.getAttribute('aria-pressed'), b.lastChild.textContent]),
  sw: (() => { const w = document.querySelector('#sp-p-news .sp-switch'); return w && !w.hidden && !w.closest('[hidden]') ? w.getAttribute('aria-checked') : null; })(),
  kinds: [...document.querySelectorAll('#sp-p-news .sp-nw-tag.k')].map(t => t.textContent),
  fixes: [...document.querySelectorAll('#sp-p-news .sp-nw-tag.fix')].map(t => t.textContent),
  datetimes: [...document.querySelectorAll('#sp-p-news time')].map(t => t.getAttribute('datetime')),
})"""
LIM_JS = "() => { const l = document.querySelector('.sp-lim'); return l.hidden ? '' : l.textContent + '|' + l.className + '|' + getComputedStyle(l).color; }"


def run_extra(b):
    """뉴스·공시 tab, 관심종목 star, 상한가/하한가 badge (AGENTS.md §3-2)."""
    import re
    # ── news: fetched only when the tab opens, both lists, cached 5 minutes per code ──
    mock('/__reset')
    mock('/__config?dsrc=naver')   # Naver path first; DART rows are checked further down
    P = Page(b, 390, None)
    pg = P.pg
    pg.clock.set_fixed_time('2026-11-09T22:00:00+09:00')
    pg.goto(BASE)
    pg.wait_for_timeout(800)
    P.ev("() => localStorage.setItem('khm.stockTab', JSON.stringify('ob'))")
    P.ev("() => KHStock.open('005930')")
    P.wait_chart(); pg.wait_for_timeout(500)
    n_before = P.count('/news') + P.count('/disclosures')
    t0 = time.time()
    pg.click('#sp-t-news')
    pg.wait_for_selector('#sp-p-news .sp-nw-list li')
    pg.wait_for_timeout(300)
    nw = P.ev(NEWS_JS)
    req = {'news': P.count('/news', t0), 'disc': P.count('/disclosures', t0)}
    check('news_fetched_only_when_tab_opens', n_before == 0 and req == {'news': 1, 'disc': 1}, {'before': n_before, 'after_open': req})
    check('news_list', nw['rows'] == 20 and len(nw['press']) == 20 and all(nw['titles']) and nw['pressed'][0][:2] == ['news', 'true'] and '20' in nw['pressed'][1][2],
          {k: nw[k] for k in ('rows', 'pressed')} | {'first': nw['titles'][0], 'press0': nw['press'][0]})
    check('news_entities_decoded', not any('&quot;' in t or '&amp;' in t or '&lt;' in t for t in nw['titles']) and any('"' in t for t in nw['titles']),
          [t for t in nw['titles'] if '"' in t][:2])
    # clock pinned at 22:00 KST: 21:46 → 14분 전, 19:21 → 2시간 전
    check('news_relative_time', nw['times'][0] == '14분 전' and nw['times'][-1] == '2시간 전', [nw['times'][0], nw['times'][-1]])
    check('news_links_new_tab', all(h.startswith('https://n.news.naver.com/') and t == '_blank' and r == 'noopener' for h, t, r in nw['links']) and len(nw['links']) == 20, nw['links'][:2])
    pg.screenshot(path=str(SHOTS / 'live390_tab_news.png'))
    pg.click('.sp-nwseg button[data-kind="disc"]'); pg.wait_for_timeout(200)
    ds = P.ev(NEWS_JS)
    check('disclosures_list', ds['rows'] == 20 and ds['pressed'][1][:2] == ['disc', 'true'] and ds['tags'] >= 1 and not ds['press']
          and all(re.match(r'^https://m\.stock\.naver\.com/domestic/stock/005930/notice/\d+$', h) for h, _, _ in ds['links'])
          and ds['times'][0] == '3일 전' and ds['times'][-1] == '7월 31일' and ds['src'].startswith('출처: 네이버 증권') and not ds['filters'] and ds['sw'] is None,
          {'rows': ds['rows'], 'tags': ds['tags'], 'times': [ds['times'][0], ds['times'][-1]], 'link0': ds['links'][0][0], 'src': ds['src']})
    check('news_no_extra_fetch_on_toggle', P.count('/news', t0) + P.count('/disclosures', t0) == 2)
    pg.screenshot(path=str(SHOTS / 'live390_tab_disc.png'))
    # cache: other tab and back, close and reopen, switch stock and back → no refetch for 005930 within 5 minutes
    pg.click('#sp-t-inv'); pg.wait_for_timeout(200); pg.click('#sp-t-news'); pg.wait_for_timeout(300)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    P.ev("() => KHStock.open('005930')"); pg.wait_for_timeout(600)
    same = P.count('/news', t0) + P.count('/disclosures', t0)
    t1 = time.time()
    P.ev("() => KHStock.open('196170')"); pg.wait_for_selector('#sp-p-news .sp-nw-list li'); pg.wait_for_timeout(300)
    other = P.count('/news', t1) + P.count('/disclosures', t1)
    t2 = time.time()
    P.ev("() => KHStock.open('005930')"); pg.wait_for_timeout(600)
    back = P.count('/news', t2) + P.count('/disclosures', t2)
    pg.clock.set_fixed_time('2026-11-09T22:06:00+09:00')   # 6 minutes later → stale
    t3 = time.time()
    pg.click('#sp-t-inv'); pg.wait_for_timeout(200); pg.click('#sp-t-news'); pg.wait_for_timeout(800)
    stale = P.count('/news', t3) + P.count('/disclosures', t3)
    check('news_cache_5min_per_code', same == 2 and other == 2 and back == 0 and stale == 2, {'same_code_reopen_total': same, 'other_code': other, 'back_within_5min': back, 'after_6min': stale})
    check('console_clean_news', not P.console, P.console)
    P.close()

    # '어제' the next morning
    P = Page(b, 390, None)
    P.pg.clock.set_fixed_time('2026-11-10T09:00:00+09:00')
    P.pg.goto(BASE + '#s-005930')
    P.pg.wait_for_timeout(600)
    P.pg.click('#sp-t-news'); P.pg.wait_for_selector('#sp-p-news .sp-nw-list li')
    times = P.ev("() => [...document.querySelectorAll('#sp-p-news time')].map(t => t.textContent)")
    check('news_relative_time_yesterday', set(times) == {'어제'}, sorted(set(times)))
    P.close()

    # error + retry, empty
    mock('/__config?fail=news')
    P = Page(b, 390, BASE + '#s-196170')
    pg = P.pg
    pg.wait_for_timeout(600)
    pg.click('#sp-t-news'); pg.wait_for_selector('#sp-p-news .sp-msgbox .sp-btn')
    err = P.ev("() => document.querySelector('#sp-p-news .sp-msgbox').textContent")
    pg.click('.sp-nwseg button[data-kind="disc"]'); pg.wait_for_timeout(300)
    disc_ok = P.ev("() => document.querySelectorAll('#sp-p-news .sp-nw-list li').length")
    pg.click('.sp-nwseg button[data-kind="news"]'); pg.wait_for_timeout(200)
    mock('/__config?fail=')
    pg.click('#sp-p-news .sp-msgbox .sp-btn'); pg.wait_for_selector('#sp-p-news .sp-nw-list li')
    check('news_error_retry', '뉴스를 불러오지 못했어요' in err and disc_ok == 20, {'err': err, 'disc_rows_meanwhile': disc_ok})
    P.close()
    P = Page(b, 390, BASE + '#s-999980')
    pg = P.pg
    pg.wait_for_timeout(600)
    pg.click('#sp-t-news'); pg.wait_for_timeout(600)
    e1 = P.ev(NEWS_JS)['msg']
    pg.click('.sp-nwseg button[data-kind="disc"]'); pg.wait_for_timeout(200)
    e2 = P.ev(NEWS_JS)['msg']
    check('news_empty_states', '최근 뉴스가 없어요' in e1 and '최근 공시가 없어요' in e2, [e1, e2])
    check('console_clean_news_states', not P.console, P.console)
    P.close()

    # ── 공시 from OpenDART: date-only rows, kind chips + filter, 지분 switch (off), 정정 tag, source line ──
    mock('/__config?dsrc=')
    dj = {c: mock(f'/api/stock/{c}/disclosures')['rows'] for c in ('196170', '005930')}
    P = Page(b, 390, None)
    pg = P.pg
    pg.clock.set_fixed_time('2026-11-09T22:00:00+09:00')
    pg.add_init_script("localStorage.setItem('khm.stockNewsKind', JSON.stringify('disc'))")   # saved choice, read at load
    pg.goto(BASE); pg.wait_for_timeout(600)
    P.ev("() => KHStock.open('196170')")
    pg.click('#sp-t-news'); pg.wait_for_selector('#sp-p-news .sp-nw-list li'); pg.wait_for_timeout(200)
    a = P.ev(NEWS_JS)
    rows = dj['196170']; non_eq = [r for r in rows if r['kind'] != '지분']
    cnt = lambda k, rs=rows: sum(r['kind'] == k for r in rs)
    want = [['전체', 'true', str(len(non_eq))], ['주요', 'false', str(cnt('주요'))], ['실적', 'false', str(cnt('실적'))], ['정기', 'false', str(cnt('정기'))]]
    fixes = sum('정' in (r['note'] or '') for r in non_eq)
    ok = (a['src'].startswith('출처: DART 전자공시') and a['filters'] == want and a['sw'] == 'false' and a['rows'] == len(non_eq) and fixes >= 1
          and len(a['kinds']) == a['rows'] and '지분' not in a['kinds'] and a['fixes'] == ['정정'] * fixes
          and all(re.match(r'^\d{4}-\d{2}-\d{2}$', d) for d in a['datetimes']) and not any(':' in t for t in a['times']) and a['times'][0] == '11월 3일'
          and all(re.match(r'^https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=\d{14}$', u) and t == '_blank' and rl == 'noopener' for u, t, rl in a['links'])
          and a['press'] == [r['filer'] for r in non_eq if r['filer'] and r['filer'] != '알테오젠'])   # only outside filers (금융감독원 …) are named
    check('dart_default_view', ok, {'src': a['src'], 'filters': a['filters'], 'switch': a['sw'], 'rows': a['rows'], 'fixes': a['fixes'], 'time0': a['times'][0], 'link0': a['links'][0]})
    pg.screenshot(path=str(SHOTS / 'live390_tab_dart.png'))
    got = {}
    for f in ('실적', '정기', '주요'):
        pg.click(f'.sp-dfilt button[data-f="{f}"]'); pg.wait_for_timeout(100)
        x = P.ev(NEWS_JS)
        got[f] = (x['rows'], set(x['kinds']), [p[0] for p in x['filters'] if p[1] == 'true'])
    check('dart_kind_filter', all(got[f] == (cnt(f), {f}, [f]) for f in got), {f: [v[0], sorted(v[1]), v[2]] for f, v in got.items()})
    pg.click('.sp-switch'); pg.wait_for_timeout(100)
    on = P.ev(NEWS_JS)
    pg.click('.sp-dfilt button[data-f="지분"]'); pg.wait_for_timeout(100)
    eq = P.ev(NEWS_JS)
    pg.click('.sp-switch'); pg.wait_for_timeout(100)
    off = P.ev(NEWS_JS)
    check('dart_equity_switch', on['sw'] == 'true' and ['지분', 'false', str(cnt('지분'))] in on['filters'] and eq['rows'] == cnt('지분') and set(eq['kinds']) == {'지분'}
          and off['sw'] == 'false' and off['rows'] == len(non_eq) and [p[0] for p in off['filters']] == ['전체', '주요', '실적', '정기'] and off['filters'][0][1] == 'true',
          {'on_filters': on['filters'], 'equity_rows': eq['rows'], 'off': [off['sw'], off['rows'], off['filters']]})
    # 삼성전자: mostly 지분 reports; with the switch on, today's filing reads 오늘 and outside filers (임원) are named
    P.ev("() => KHStock.open('005930')"); pg.wait_for_selector('#sp-p-news .sp-nw-list li'); pg.wait_for_timeout(200)
    s0 = P.ev(NEWS_JS)
    sam = dj['005930']; sam_non = [r for r in sam if r['kind'] != '지분']
    pg.click('.sp-switch'); pg.wait_for_timeout(100)
    s1 = P.ev(NEWS_JS)
    check('dart_samsung_equity_hidden_by_default', s0['rows'] == len(sam_non) and s1['rows'] == len(sam) and s1['times'][0] == '오늘' and '11월 6일' in s1['times']
          and len(s1['press']) == sum(1 for r in sam if r['filer'] and r['filer'] != '삼성전자') and '삼성전자' not in s1['press'],
          {'default_rows': s0['rows'], 'with_equity': s1['rows'], 'times': s1['times'][:3], 'filers_shown': len(s1['press'])})
    check('console_clean_dart', not P.console, P.console)
    P.close()
    # next morning: yesterday's filing reads 어제 (switch state persisted in localStorage → set again in the new context)
    P = Page(b, 390, None)
    P.pg.clock.set_fixed_time('2026-11-10T09:00:00+09:00')
    P.pg.add_init_script("localStorage.setItem('khm.stockNewsKind', JSON.stringify('disc')); localStorage.setItem('khm.stockDiscEquity', 'true')")
    P.pg.goto(BASE); P.pg.wait_for_timeout(600)
    P.ev("() => KHStock.open('005930')"); P.pg.click('#sp-t-news'); P.pg.wait_for_selector('#sp-p-news .sp-nw-list li'); P.pg.wait_for_timeout(200)
    y = P.ev(NEWS_JS)
    check('dart_date_only_yesterday', y['times'][0] == '어제' and y['sw'] == 'true', y['times'][:3])
    P.close()
    # DART view (switch on, longest list) at every width: no overflow, labels fit, no console errors
    bad = {}
    for w in (360, 390, 768, 1280, 1920, 1440):
        P = Page(b, w, None)
        P.pg.clock.set_fixed_time('2026-11-09T22:00:00+09:00')
        P.pg.add_init_script("localStorage.setItem('khm.stockNewsKind', JSON.stringify('disc')); localStorage.setItem('khm.stockDiscEquity', 'true')")
        P.pg.goto(BASE); P.pg.wait_for_timeout(600)
        P.ev("() => KHStock.open('196170')"); P.wait_chart()
        P.pg.click('#sp-t-news'); P.pg.wait_for_selector('#sp-p-news .sp-nw-list li'); P.pg.wait_for_timeout(300)
        o = P.ev(OVERFLOW_JS)
        o['clipped'] = P.ev("() => [...document.querySelectorAll('.sp-tabs button, .sp-nwseg button, .sp-dfilt button, .sp-switch')].filter(b => b.offsetWidth && b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)")
        o['taps'] = P.ev(TAP_JS) if w < 700 else []
        if o['doc'] or o['root'] or o['n'] or o['clipped'] or o['taps'] or P.console:
            bad[w] = [o, P.console]
        if w == 1440:
            P.pg.screenshot(path=str(SHOTS / 'live1440_dart.png'))
        P.close()
    check('dart_view_no_overflow_all_widths', not bad, bad or None)

    # ── 관심종목 star ──
    P = Page(b, 390, BASE)
    pg = P.pg
    pg.wait_for_timeout(600)
    P.ev("() => { window.__watch = KH.watch; delete KH.watch; KHStock.open('005930'); }"); pg.wait_for_timeout(400)
    hidden_without = P.ev("() => document.querySelector('.sp-star').hidden && getComputedStyle(document.querySelector('.sp-star')).display === 'none'")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    P.ev("() => { if (window.__watch) KH.watch = window.__watch; }")
    real_watch = P.ev("() => !!KH.watch")
    P.ev(WATCH_STUB)
    P.ev("() => KHStock.open('005930')"); pg.wait_for_timeout(400)
    st0 = P.ev("() => { const s = document.querySelector('.sp-star'), r = s.getBoundingClientRect(); return { hidden: s.hidden, pressed: s.getAttribute('aria-pressed'), w: r.width, h: r.height, label: s.getAttribute('aria-label') }; }")
    pg.click('.sp-star'); pg.wait_for_timeout(150)
    st1 = P.ev("() => ({ pressed: document.querySelector('.sp-star').getAttribute('aria-pressed'), has: KH.watch.has('005930'), color: getComputedStyle(document.querySelector('.sp-star')).color, fill: getComputedStyle(document.querySelector('.sp-star svg')).fill })")
    pg.screenshot(path=str(SHOTS / 'live390_star_on.png'), clip={'x': 0, 'y': 0, 'width': 390, 'height': 140})
    P.ev("() => KH.watch.toggle('005930')"); pg.wait_for_timeout(100)   # changed elsewhere (e.g. the heatmap) → kh:watch
    st2 = P.ev("() => document.querySelector('.sp-star').getAttribute('aria-pressed')")
    pg.focus('.sp-star'); pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
    st3 = P.ev("() => [document.querySelector('.sp-star').getAttribute('aria-pressed'), KH.watch.list()]")
    ok = (hidden_without and not st0['hidden'] and st0['pressed'] == 'false' and st0['w'] >= 40 and st0['h'] >= 40
          and st1['pressed'] == 'true' and st1['has'] and st1['color'] == 'rgb(255, 181, 71)' and st2 == 'false' and st3 == ['true', ['005930']])
    check('watch_star', ok, {'real_KH_watch': real_watch, 'hidden_without_api': hidden_without, 'off': st0, 'on': st1, 'external_toggle': st2, 'keyboard': st3})
    taps = P.ev(TAP_JS)
    check('tap_targets_40px_with_star', not taps, taps)

    # ── 상한가 / 하한가 ──
    l0 = P.ev(LIM_JS)
    P.ev("() => { KH.stock('005930').lim = 1; document.dispatchEvent(new CustomEvent('kh:data')); }"); pg.wait_for_timeout(100)
    l1 = P.ev(LIM_JS)
    pg.screenshot(path=str(SHOTS / 'live390_limit_up.png'), clip={'x': 0, 'y': 0, 'width': 390, 'height': 140})
    P.ev("() => { KH.stock('005930').lim = -1; document.dispatchEvent(new CustomEvent('kh:data')); }"); pg.wait_for_timeout(100)
    l2 = P.ev(LIM_JS)
    P.ev("() => { const s = KH.stock('005930'); delete s.lim; s._r = s.r; s.r = 29.6; document.dispatchEvent(new CustomEvent('kh:data')); }"); pg.wait_for_timeout(100)
    l3 = P.ev(LIM_JS)
    P.ev("() => { const s = KH.stock('005930'); s.r = s._r; document.dispatchEvent(new CustomEvent('kh:data')); }"); pg.wait_for_timeout(100)
    l4 = P.ev(LIM_JS)
    pal = P.ev("() => KH.palette()")
    hexrgb = lambda x: 'rgb(%d, %d, %d)' % tuple(int(x[i:i + 2], 16) for i in (1, 3, 5))
    check('limit_badge_live', l0 == '' and l1.startswith('상한가|sp-lim up|') and l1.endswith(hexrgb(pal['upText'])) and l2.startswith('하한가|sp-lim dn|')
          and l2.endswith(hexrgb(pal['dnText'])) and l3.startswith('상한가') and l4 == '', [l0, l1, l2, l3, l4])
    # outside the live quote universe: the summary's ratio decides (900300 +29.96%)
    P.ev("() => KHStock.open('900300')"); pg.wait_for_timeout(800)
    l5 = P.ev(LIM_JS)
    check('limit_badge_from_summary', l5.startswith('상한가'), l5)
    check('console_clean_star_limit', not P.console, P.console)
    P.close()

    # ── news tab and star at the other widths; desktop screenshot ──
    for w in (1440,):
        P = Page(b, w, BASE)
        P.pg.clock.set_fixed_time('2026-11-09T22:00:00+09:00')
        P.pg.wait_for_timeout(600)
        P.ev(WATCH_STUB); P.ev("() => KH.watch.toggle('005930')")
        P.ev("() => KHStock.open('005930')"); P.wait_chart()
        P.pg.click('#sp-t-news'); P.pg.wait_for_selector('#sp-p-news .sp-nw-list li'); P.pg.wait_for_timeout(400)
        P.pg.screenshot(path=str(SHOTS / f'live{w}_news.png'))
        o = P.ev(OVERFLOW_JS)
        check(f'news_star_no_overflow_{w}', not (o['doc'] or o['root'] or o['n']) and not P.console, [o, P.console])
        P.close()

    # ── snapshot: badge from KH.stock (|r| ≥ 29.5 while snapshot rows have no lim yet), star only with KH.watch, zero fetches ──
    for code, want in (('900300', '상한가'), ('179530', '하한가')):
        P = Page(b, 390, SNAP + '#s-' + code)
        P.pg.wait_for_timeout(900)
        l = P.ev(LIM_JS)
        api = [u for _, u in P.reqs if 'api/' in u]
        if code == '900300':
            P.pg.screenshot(path=str(SHOTS / 'snap390_limit.png'))
        check(f'snapshot_limit_{code}', l.startswith(want) and not api and not P.console, [l, api, P.console])
        P.close()


# ── 종목 정보 tab, header ranges, peers from /summary, 오늘 순매수 (AGENTS.md §3-3) ──────────────────────
def ko(v, d=0):
    return f'{v:,.{d}f}'


def eok(v):   # KH.fmt.eok
    return (f'{v / 10000:,.1f}'.removesuffix('.0') + '조') if v >= 10000 else f'{round(v):,}억'


def eok_full(v):   # stock.js eokFull
    s, a = ('−' if v < 0 else ''), round(abs(v))
    if a >= 10000:
        jo, r = divmod(a, 10000)
        return s + f'{jo:,}조' + (f' {r:,}억' if r else '') + '원'
    return s + f'{a:,}억원'


def signed_pct(v, d=1):
    return ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.{d}f}%'


def bucket(o):   # stock.js opinionBucket, for the strings the fixtures produce
    s = (o or '').replace(' ', '').lower()
    for i, pre in ((4, ('strongbuy', '적극매수', '강력매수')), (0, ('strongsell', '적극매도', '강력매도')),
                   (3, ('buy', '매수', 'tradingbuy', '비중확대', 'outperform', 'overweight')), (1, ('sell', '매도', 'underperform', '비중축소')),
                   (2, ('hold', '중립', 'neutral', 'marketperform'))):
        if s.startswith(pre):
            return i
    return -1


def fin_expect(fin):
    """columns the chart draws (any of 매출·영업이익·당기순이익 present), oldest first"""
    rows = {r['title']: r['values'] for r in fin['rows']}
    out = []
    for i, c in enumerate(fin['cols']):
        v = [rows.get(t, [None] * len(fin['cols']))[i] for t in ('매출액', '영업이익', '당기순이익')]
        if any(x is not None for x in v):
            out.append((c, v))
    return out


INFO_JS = r"""() => {
  const P = document.getElementById('sp-p-info'), q = s => [...P.querySelectorAll(s)];
  const sec = k => P.querySelector('.sp-ci-' + k);
  return {
    metrics: Object.fromEntries(q('.sp-m').map(m => [m.querySelector('dt').textContent, [m.querySelectorAll('dd')[0].textContent, (m.querySelector('dd.sub') || {}).textContent || '']])),
    cols: q('.sp-fin-col').map(b => [b.dataset.key, b.classList.contains('est'), b.getAttribute('aria-checked'), b.tabIndex]),
    xs: q('.sp-fin-x span').map(s => s.textContent),
    when: (P.querySelector('.sp-fin-when') || {}).textContent || '',
    vals: q('.sp-fin-vals > div').map(d => [d.querySelector('dt').textContent, d.querySelector('dd').textContent]),
    finMsg: (sec('fin').querySelector('.sp-msgbox') || {}).textContent || '',
    finNote: (sec('fin').querySelector('.sp-note') || {}).textContent || '',
    negBelow: q('.sp-fin-col .b.neg').map(b => b.getBoundingClientRect().top - P.querySelector('.sp-fin-area .zero').getBoundingClientRect().top),
    posAbove: q('.sp-fin-col .b:not(.neg)').map(b => P.querySelector('.sp-fin-area .zero').getBoundingClientRect().top - b.getBoundingClientRect().bottom),
    estHatched: q('.sp-fin-col.est .b').map(b => getComputedStyle(b).backgroundImage.includes('repeating-linear-gradient')),
    stabHidden: sec('stab').hidden,
    stab: q('.sp-ln .lb').map(s => s.textContent),
    stabX: q('.sp-ln-x span').map(s => s.textContent),
    stabMsg: (sec('stab').querySelector('.sp-msgbox') || {}).textContent || '',
    divKv: q('.sp-ci-div .sp-kv dd').map(d => d.textContent),
    divBars: q('.sp-dbars .v').map(s => s.textContent),
    divMsg: (sec('div').querySelector('.sp-msgbox') || {}).textContent || '',
    anaH: (P.querySelector('.sp-ana-h') || {}).textContent || '',
    op: q('.sp-op .col').map(c => [c.querySelector('.x').textContent, c.querySelector('.n').textContent, c.classList.contains('max')]),
    opNote: (P.querySelector('.sp-op-note') || {}).textContent || '',
    cons: q('.sp-cons > div').map(d => [d.querySelector('dt').textContent, d.querySelector('dd').textContent]),
    gap: (() => { const g = P.querySelector('.sp-gap'); return g ? [g.textContent, g.className] : null; })(),
    reports: q('.sp-rp-list li').map(li => { const a = li.querySelector('a'); return [li.querySelector('.sp-rp-t').textContent, li.querySelector('.sp-rp-m').textContent, a && a.getAttribute('href'), a && a.target, a && a.rel]; }),
    more: (sec('ana').querySelector('.sp-more') || {}).textContent || '',
    anaMsg: (sec('ana').querySelector('.sp-msgbox') || {}).textContent || '',
    src: (P.querySelector('.sp-ci-src') || {}).textContent || '',
    pressed: q('.sp-mseg [aria-pressed=true]').map(b => b.dataset.p),
    skel: q('.sp-skel, .sp-fin-skel').length,
    text: P.textContent,
    ownText: (() => { const c = P.cloneNode(true); c.querySelectorAll('.sp-rp-list').forEach(e => e.remove()); return c.textContent; })(),   // without the brokers' report titles
  };
}"""


def run_info(b):
    T = '2026-11-09T22:00:00+09:00'
    mock('/__reset')
    s5 = mock('/api/stock/005930/summary')
    fa5, fq5, rs5 = mock('/api/stock/005930/finance?period=annual'), mock('/api/stock/005930/finance?period=quarter'), mock('/api/stock/005930/research')
    mock('/__reset')

    # ── lazy load: nothing until the tab opens; three requests then; none on tab switches or 분기/연간 ──
    P = Page(b, 390, None)
    pg = P.pg
    pg.clock.set_fixed_time(T)
    pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('ob')); localStorage.setItem('khm.stockFinPeriod', JSON.stringify('quarter'))")
    pg.goto(BASE); pg.wait_for_timeout(600)
    P.ev("() => KHStock.open('005930')"); P.wait_chart(); pg.wait_for_timeout(400)
    before = P.count('/finance') + P.count('/research')
    t0 = time.time()
    pg.click('#sp-t-info')
    pg.wait_for_selector('#sp-p-info .sp-fin-col'); pg.wait_for_selector('#sp-p-info .sp-rp-list li'); pg.wait_for_timeout(300)
    req = {'annual': P.count('finance?period=annual', t0), 'quarter': P.count('finance?period=quarter', t0), 'research': P.count('/research', t0)}
    pg.click('#sp-t-inv'); pg.wait_for_timeout(200); pg.click('#sp-t-info'); pg.wait_for_timeout(200)
    pg.click('.sp-ci-fin .sp-mseg [data-p="annual"]'); pg.wait_for_timeout(150); pg.click('.sp-ci-fin .sp-mseg [data-p="quarter"]'); pg.wait_for_timeout(150)
    again = P.count('/finance', t0) + P.count('/research', t0) - 3
    check('info_lazy_load', before == 0 and req == {'annual': 1, 'quarter': 1, 'research': 1} and again == 0, {'before_tab': before, 'on_open': req, 'refetch_after_switches': again})
    x = P.ev(INFO_JS)
    pg.screenshot(path=str(SHOTS / 'live390_tab_info.png'))

    # 투자 지표: summary values, ROE (latest actual year), PSR (cap ÷ last 4 actual quarters' 매출)
    cap = s5['marketCap']
    roe = next((v, c) for c, v in reversed(list(zip(fa5['cols'], next(r['values'] for r in fa5['rows'] if r['title'] == 'ROE')))) if not c['estimate'] and v is not None)
    qs = [v for c, v in zip(fq5['cols'], next(r['values'] for r in fq5['rows'] if r['title'] == '매출액')) if not c['estimate'] and v is not None][-4:]
    want = {'시가총액': [eok(cap) + '원', ''], 'PER': [f"{s5['per']:.2f}배", ''], '추정PER': [f"{s5['cnsPer']:.2f}배", '증권사 예상'], 'PBR': [f"{s5['pbr']:.2f}배", ''],
            'ROE': [f'{roe[0]:.2f}%', roe[1]['label'][:4] + '년 기준'], 'PSR': [f'{cap / sum(qs):.2f}배', '최근 4분기 매출 기준'],
            '배당수익률': [f"{s5['dividendYield']:.2f}%", ''], '외국인 소진율': [f"{s5['foreignRate']:.2f}%", '']}
    check('info_metrics_match_fixtures', x['metrics'] == want and len(qs) == 4, {'shown': x['metrics'], 'want': want})

    # 재무 (분기): one column per period with numbers, estimates hatched + 예상, latest actual picked, values listed in 조·억
    fe = fin_expect(fq5)
    last_actual = max(i for i, (c, _) in enumerate(fe) if not c['estimate'])
    ok = ([c[0] for c in x['cols']] == [c['key'] for c, _ in fe] and [c[1] for c in x['cols']] == [c['estimate'] for c, _ in fe]
          and all(('예상' in xs) == c['estimate'] for xs, (c, _) in zip(x['xs'], fe)) and any(c['estimate'] for c, _ in fe) and all(x['estHatched']) and x['estHatched']
          and [c[2] for c in x['cols']].index('true') == last_actual and x['vals'] == [[n, eok_full(v)] for n, v in zip(('매출', '영업이익', '순이익'), fe[last_actual][1])]
          and '빗금 막대는 증권사 예상치' in x['finNote'] and x['pressed'] == ['quarter', 'quarter'])
    check('info_finance_quarter_bars', ok, {'cols': x['cols'], 'xs': x['xs'], 'vals': x['vals'], 'when': x['when']})
    # pick another period with the keyboard (radio group: arrows move the choice)
    pg.focus(f'.sp-fin-col[data-key="{fe[last_actual][0]["key"]}"]'); pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(100)
    k1 = P.ev("() => [document.activeElement.dataset.key, document.activeElement.getAttribute('aria-checked'), [...document.querySelectorAll('.sp-fin-vals dd')].map(d => d.textContent)]")
    pg.keyboard.press('End'); pg.wait_for_timeout(100)
    k2 = P.ev("() => [document.activeElement.dataset.key, document.querySelector('.sp-fin-when').textContent]")
    check('info_finance_keyboard_pick', k1[0] == fe[last_actual - 1][0]['key'] and k1[1] == 'true' and k1[2] == [eok_full(v) for v in fe[last_actual - 1][1]]
          and k2[0] == fe[-1][0]['key'] and '예상' in k2[1], [k1, k2])
    # 연간
    pg.click('.sp-ci-fin .sp-mseg [data-p="annual"]'); pg.wait_for_timeout(200)
    y = P.ev(INFO_JS)
    fa_e = fin_expect(fa5)
    check('info_finance_annual_toggle', [c[0] for c in y['cols']] == [c['key'] for c, _ in fa_e] and y['pressed'] == ['annual', 'annual'] and y['xs'][0].startswith(fa_e[0][0]['label'][:4])
          and sum(c[1] for c in y['cols']) == sum(c['estimate'] for c, _ in fa_e) == 1, {'cols': y['cols'], 'xs': y['xs']})
    # 안정성 (연간 now): one label per year with a value, 당좌비율 switch
    dr = [v for v in next(r['values'] for r in fa5['rows'] if r['title'] == '부채비율') if v is not None]
    qr = [v for v in next(r['values'] for r in fa5['rows'] if r['title'] == '당좌비율') if v is not None]
    pg.click('.sp-stabseg [data-k="당좌비율"]'); pg.wait_for_timeout(150)
    y2 = P.ev(INFO_JS)
    check('info_stability_lines', y['stab'] == [f'{v:,.1f}%' for v in dr] and y2['stab'] == [f'{v:,.1f}%' for v in qr] and not y['stabHidden'] and len(y['stabX']) == len(dr),
          {'부채비율': y['stab'], '당좌비율': y2['stab']})
    pg.click('.sp-stabseg [data-k="부채비율"]'); pg.click('.sp-ci-fin .sp-mseg [data-p="quarter"]'); pg.wait_for_timeout(150)
    # 배당: summary dps + yield, bars per year from annual finance
    dps = [v for v in next(r['values'] for r in fa5['rows'] if r['title'] == '주당배당금') if v is not None]
    check('info_dividend', x['divKv'] == [f"{s5['dps']:,}원", f"{s5['dividendYield']:.2f}%"] and x['divBars'] == [f'{v:,}원' for v in dps], {'kv': x['divKv'], 'bars': x['divBars']})
    # 애널리스트: last 3 months (clock pinned 11-09 → since 08-09), buckets from the parsed opinion, unknown not counted
    recent = [r for r in rs5['rows'] if r['date'] >= '2026-08-09']
    counts = [0] * 5
    for r in recent:
        if bucket(r['opinion']) >= 0:
            counts[bucket(r['opinion'])] += 1
    unknown = len(recent) - sum(counts)
    gap = (rs5['consensus']['targetMean'] / s5['price'] - 1) * 100
    ok = (x['anaH'].startswith(f'최근 3개월 리포트 {len(recent)}건') and '20건까지만' in x['anaH'] and [o[1] for o in x['op']] == [f'{n}건' for n in counts]
          and [o[0] for o in x['op']] == ['적극매도', '매도', '중립', '매수', '적극매수'] and sum(counts) >= 2 and f'{unknown}건은 세지 않았어요' in x['opNote']
          and x['cons'][0][1].startswith(f"{rs5['consensus']['targetMean']:,}원") and x['gap'] == [f'현재가 대비 {signed_pct(gap)}', 'sp-gap num up']
          and x['cons'][1][1].startswith(f"{rs5['consensus']['opinionMean']:.2f}점") and '매수' in x['cons'][1][1])
    check('info_analyst_distribution_consensus', ok, {'h': x['anaH'], 'op': x['op'], 'want': counts, 'note': x['opNote'], 'cons': x['cons'], 'gap': x['gap']})
    rows = rs5['rows']
    ok = (len(x['reports']) == 5 and all(r[2] == w['url'] and r[3] == '_blank' and r[4] == 'noopener' and r[0] == w['title'] and w['broker'] in r[1] for r, w in zip(x['reports'], rows))
          and ('목표가 370,000원' in x['reports'][0][1]) and '매수' in x['reports'][0][1] and x['more'] == f'리포트 {len(rows) - 5}건 더 보기'
          and x['src'] == '출처: 네이버 증권 · 컨센서스는 증권사 추정치예요' and all('preview' not in k.lower() for r in rows for k in r))
    check('info_report_list', ok, {'first': x['reports'][0], 'n': len(x['reports']), 'more': x['more'], 'src': x['src']})
    pg.click('.sp-ci-ana .sp-more'); pg.wait_for_timeout(150)
    ex = P.ev("() => [document.querySelectorAll('.sp-rp-list li').length, document.activeElement.textContent, document.activeElement.getAttribute('aria-expanded')]")
    check('info_report_list_expands', ex == [len(rows), '접기', 'true'], ex)
    check('info_no_investment_wording', not any(w in x['ownText'] for w in ('추천', '사세요', '팔세요', '저평가', '고평가', '상승 여력', '기회')), None)
    # peers from summary.peers: name, price, % — opening one switches in place
    pe = P.ev("() => [...document.querySelectorAll('.sp-peer')].map(b => [b.dataset.code, b.querySelector('.nm').textContent, b.querySelector('.pr').textContent, b.querySelector('.pc').textContent])")
    wp = [[p_['code'], p_['name'], f"{p_['price']:,}", signed_pct(p_['ratio'], 2)] for p_ in s5['peers']]
    hl = P.ev('history.length')
    pg.click('.sp-peer:nth-child(2)'); pg.wait_for_timeout(700)
    sw = P.ev("() => ({ hash: location.hash, name: document.getElementById('sp-name').textContent, hl: history.length, tab: document.querySelector('[role=tab][aria-selected=true]').id })")
    check('peers_from_summary_open_in_place', pe == wp and sw['hash'] == '#s-' + wp[1][0] and sw['name'] == wp[1][1] and sw['hl'] == hl and sw['tab'] == 'sp-t-info', {'chips': pe[:2], 'want': wp[:2], 'after': sw})
    check('console_clean_info', not P.console, P.console)
    P.close()

    # ── header: 1일 range (low–high, current dot, 시가 / 전일 종가) and 52주 range ──
    P = Page(b, 1280, None)
    P.pg.clock.set_fixed_time(T)
    P.pg.goto(BASE + '#s-005930'); P.pg.wait_for_selector('.sp-rng.d1 .dot'); P.pg.wait_for_timeout(200)
    r = P.ev("""() => { const c = k => document.querySelector('.sp-rng.' + k); return {
        d1: [c('d1').querySelector('dt').textContent, c('d1').querySelector('.lo').textContent, c('d1').querySelector('.hi').textContent, c('d1').querySelector('.dot').style.left, c('d1').querySelector('.fill').className, c('d1').querySelector('.tk.prev').style.left, c('d1').querySelector('.tk.open').style.left],
        w52: [c('w52').querySelector('dt').textContent, c('w52').querySelector('.lo').textContent, c('w52').querySelector('.hi').textContent, c('w52').querySelector('.dot').style.left],
        aria: c('d1').querySelector('.track').getAttribute('aria-label') }; }""")
    pos = lambda v, lo, hi: f'{(v - lo) / (hi - lo) * 100:.1f}%'
    want = {'d1': [f"1일 범위시가 {s5['open']:,} · 전일 {s5['prevClose']:,}", f"{s5['low']:,}", f"{s5['high']:,}", pos(s5['price'], s5['low'], s5['high']), 'fill dn',
                   pos(s5['prevClose'], s5['low'], s5['high']), pos(s5['open'], s5['low'], s5['high'])],
            'w52': ['52주 범위', f"{s5['low52']:,}", f"{s5['high52']:,}", pos(s5['price'], s5['low52'], s5['high52'])]}
    check('header_day_and_52w_ranges', r['d1'] == want['d1'] and r['w52'] == want['w52'] and '현재가 187,000원' in r['aria'], {'shown': r, 'want': want})
    P.close()

    # ── 투자자: 오늘 순매수 on top (latest row) ──
    inv = mock('/api/stock/005930/investors')['rows'][0]
    for at, when in (('2026-11-09T22:00:00+09:00', None), (inv['date'] + 'T20:00:00+09:00', '오늘')):
        P = Page(b, 390, None)
        P.pg.clock.set_fixed_time(at)
        P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('inv'))")
        P.pg.goto(BASE + '#s-005930'); P.pg.wait_for_selector('.sp-today-r'); P.pg.wait_for_timeout(200)
        t = P.ev("() => ({ h: document.querySelector('.sp-today h3').textContent, first: document.querySelector('#sp-p-inv > *').className, rows: [...document.querySelectorAll('.sp-today-r')].map(r => [r.querySelector('.k').textContent, r.querySelector('b .l').textContent, r.querySelector('.bar i').getAttribute('style').replace(/\s/g, '')]) })")
        sg = lambda v: ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):,}주'
        m, d = int(inv['date'][5:7]), int(inv['date'][8:10])
        ok = (t['first'] == 'sp-today' and t['h'] == f"{when or f'{m}월 {d}일'} 순매수" and [x[0] for x in t['rows']] == ['개인', '외국인', '기관']
              and [x[1] for x in t['rows']] == [sg(inv[k]) for k in ('individual', 'foreign', 'institution')]
              and all(x[2].startswith('left:50%' if inv[k] >= 0 else 'right:50%') for x, k in zip(t['rows'], ('individual', 'foreign', 'institution'))))
        check(f'investors_today_card_{"today" if when else "last_day"}', ok, t)
        if not when:
            P.pg.screenshot(path=str(SHOTS / 'live390_inv_today.png'))
        P.close()

    # ── 일별 시세 note (after 15:30 the today row mixes NXT) ──
    P = Page(b, 390, BASE + '#s-005930')
    P.pg.click('#sp-t-daily'); P.pg.wait_for_selector('.sp-daily-t tbody tr'); P.pg.wait_for_timeout(200)
    note = P.ev("() => { const n = document.querySelector('#sp-p-daily .sp-note'); return [n.hidden, n.textContent]; }")
    check('daily_note_today_row_mixes_nxt', note == [False, '정규장 이후에는 오늘 행에 NXT 거래가 섞여 KRX 종가(15:30)와 다를 수 있어요.'], note)
    P.close()

    # ── small cap: losses below the zero line, no estimates, no research, no dividend; PSR from 4 quarters ──
    s4, fq4, fa4 = mock('/api/stock/406820/summary'), mock('/api/stock/406820/finance?period=quarter'), mock('/api/stock/406820/finance?period=annual')
    P = Page(b, 360, None)
    P.pg.clock.set_fixed_time(T)
    P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info'))")
    P.pg.goto(BASE + '#s-406820'); P.pg.wait_for_selector('.sp-fin-col'); P.pg.wait_for_selector('.sp-ci-ana .sp-msgbox'); P.pg.wait_for_timeout(300)
    z = P.ev(INFO_JS)
    q4 = [v for c, v in zip(fq4['cols'], next(r['values'] for r in fq4['rows'] if r['title'] == '매출액')) if not c['estimate'] and v is not None][-4:]
    ok = (not any(c[1] for c in z['cols']) and len(z['cols']) == len(fin_expect(fq4)) and '증권사 예상치가 없어요' in z['finNote'] and z['negBelow'] and min(z['negBelow']) >= -1.5
          and min(z['posAbove']) >= -1.5 and '최근 증권사 리포트가 없어요' in z['anaMsg'] and '최근 배당 기록이 없어요' in z['divMsg']
          and z['metrics']['PSR'] == [f"{s4['marketCap'] / sum(q4):.2f}배", '최근 4분기 매출 기준'] and z['metrics']['추정PER'] == ['—', ''] and z['metrics']['ROE'][0].startswith('−'))
    check('info_small_cap_losses_no_estimates_no_research', ok, {k: z[k] for k in ('cols', 'finNote', 'negBelow', 'anaMsg', 'divMsg')} | {'psr': z['metrics']['PSR']})
    P.pg.screenshot(path=str(SHOTS / 'live360_info_smallcap.png'), full_page=True)
    check('console_clean_info_smallcap', not P.console, P.console)
    P.close()
    # PSR falls back to the latest actual year when the quarters are missing
    mock('/__config?fail=finance:quarter')
    P = Page(b, 390, None)
    P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info')); localStorage.setItem('khm.stockFinPeriod', JSON.stringify('quarter'))")
    P.pg.goto(BASE + '#s-406820'); P.pg.wait_for_selector('.sp-ci-fin .sp-msgbox'); P.pg.wait_for_timeout(400)
    z = P.ev(INFO_JS)
    a4 = next((c, v) for c, v in reversed(list(zip(fa4['cols'], next(r['values'] for r in fa4['rows'] if r['title'] == '매출액')))) if not c['estimate'] and v is not None)
    P.pg.click('.sp-ci-fin .sp-mseg [data-p="annual"]'); P.pg.wait_for_timeout(200)
    z2 = P.ev(INFO_JS)
    check('info_psr_annual_fallback_and_period_error', z['metrics']['PSR'] == [f"{s4['marketCap'] / a4[1]:.2f}배", a4[0]['label'][:4] + '년 매출 기준'] and '재무 정보를 불러오지 못했어요' in z['finMsg']
          and z['stabHidden'] and z2['cols'] and not z2['finMsg'] and not z2['stabHidden'], {'psr': z['metrics']['PSR'], 'quarter_msg': z['finMsg'][:30], 'annual_cols': len(z2['cols'])})
    P.close()
    mock('/__config?fail=')

    # ── failures are independent; retry recovers ──
    for fail, sel in (('research', '.sp-ci-ana .sp-msgbox .sp-btn'), ('finance', '.sp-ci-fin .sp-msgbox .sp-btn')):
        mock('/__config?fail=' + fail)
        P = Page(b, 390, None)
        P.pg.clock.set_fixed_time(T)
        P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info'))")
        P.pg.goto(BASE + '#s-196170'); P.pg.wait_for_selector(sel); P.pg.wait_for_timeout(400)
        e = P.ev(INFO_JS)
        if fail == 'research':
            ok = '애널리스트 의견을 불러오지 못했어요' in e['anaMsg'] and len(e['cols']) >= 5 and e['metrics']['ROE'][0] != '—' and not e['finMsg']
        else:
            ok = ('재무 정보를 불러오지 못했어요' in e['finMsg'] and e['stabHidden'] and e['metrics']['ROE'] == ['—', ''] and e['metrics']['PSR'] == ['—', '']
                  and e['metrics']['PER'][0] != '—' and len(e['reports']) == 5 and not e['anaMsg'] and '연도별 배당 기록을 불러오지 못했어요' in e['text'])
        P.pg.screenshot(path=str(SHOTS / f'live390_info_fail_{fail}.png'), full_page=True)
        mock('/__config?fail=')
        P.pg.click(sel); P.pg.wait_for_timeout(800)
        e2 = P.ev(INFO_JS)
        rec = (len(e2['reports']) == 5 and not e2['anaMsg']) if fail == 'research' else (len(e2['cols']) >= 5 and not e2['finMsg'] and not e2['stabHidden'] and e2['metrics']['ROE'][0] != '—')
        check(f'info_{fail}_fails_alone_and_retries', ok and rec, {'msg': (e['anaMsg'] or e['finMsg'])[:40], 'metrics': e['metrics'], 'recovered': rec})
        check(f'console_clean_info_fail_{fail}', not [m for m in P.console if '502' not in m and 'Failed to load resource' not in m], P.console)
        P.close()

    # empty stock (no finance rows, no research) and a broken one (every route 502)
    for code, want in (('999980', ('재무 정보가 없어요', '최근 증권사 리포트가 없어요')), ('999990', ('재무 정보를 불러오지 못했어요', '애널리스트 의견을 불러오지 못했어요'))):
        P = Page(b, 390, None)
        P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info'))")
        P.pg.goto(BASE + '#s-' + code); P.pg.wait_for_selector('.sp-ci-fin .sp-msgbox'); P.pg.wait_for_selector('.sp-ci-ana .sp-msgbox'); P.pg.wait_for_timeout(300)
        e = P.ev(INFO_JS)
        check(f'info_states_{code}', want[0] in e['finMsg'] and want[1] in e['anaMsg'] and e['stabHidden'] and not e['skel'], {'fin': e['finMsg'][:40], 'ana': e['anaMsg'][:40], 'skel': e['skel']})
        P.close()

    # ── every width: info tab with the table open and all reports, no overflow / clipping, phone tap targets, keyboard + Esc ──
    bad = {}
    for w in (360, 390, 768, 1280, 1440, 1920):
        P = Page(b, w, None)
        P.pg.clock.set_fixed_time(T)
        P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info'))")
        P.pg.goto(BASE + '#s-005930'); P.wait_chart(); P.pg.wait_for_selector('.sp-rp-list li'); P.pg.wait_for_timeout(300)
        P.pg.click('.sp-fin-tbl summary'); P.pg.click('.sp-ci-ana .sp-more'); P.pg.wait_for_timeout(200)
        o = P.ev(OVERFLOW_JS)
        o['clipped'] = P.ev("""() => [...document.querySelectorAll('.sp-tabs button, .sp-mseg button, .sp-stabseg button, .sp-m dt, .sp-m dd, .sp-fin-x span, .sp-ln-x span, .sp-op .x, .sp-op .n, .sp-dbars .v, .sp-fin-vals dd, .sp-stat dd, .sp-rng small, .sp-peer .nm')]
            .filter(e => e.offsetWidth && !e.closest('[hidden]') && e.scrollWidth > e.clientWidth + 1).map(e => e.className + ':' + e.textContent)""")
        # labels on the line chart stay inside the panel
        o['lb'] = P.ev("() => { const p = document.querySelector('#sp-p-info').getBoundingClientRect(); return [...document.querySelectorAll('.sp-ln .lb')].filter(l => { const r = l.getBoundingClientRect(); return r.left < p.left - 1 || r.right > p.right + 1; }).length; }")
        o['taps'] = P.ev(TAP_JS) if w < 700 else []
        if o['doc'] or o['root'] or o['n'] or o['clipped'] or o['lb'] or o['taps'] or P.console:
            bad[w] = [o, P.console]
        if w in (390, 768, 1440):
            P.pg.screenshot(path=str(SHOTS / f'live{w}_info.png'))
        if w == 1440:
            # keyboard: Tab from the tab list reaches the 분기/연간 switch and the period radios; Esc closes from inside the panel
            P.pg.focus('#sp-t-info')
            seen = []
            for _ in range(12):
                P.pg.keyboard.press('Tab')
                seen.append(P.ev("() => { const a = document.activeElement; return (a.dataset.p || a.dataset.key || a.className || a.tagName) + '|' + (getComputedStyle(a).outlineStyle) ; }"))
            reach = any(s.startswith('quarter|') or s.startswith('annual|') for s in seen) and any('|' in s and s.split('|')[0].isdigit() for s in seen)
            vis = all(s.split('|')[1] != 'none' for s in seen if not s.startswith('sp-panel'))
            P.pg.keyboard.press('Escape'); P.pg.wait_for_timeout(300)
            check('info_keyboard_reach_and_esc', reach and vis and P.ev("() => !KHStock.isOpen()"), seen)
        P.close()
    check('info_no_overflow_all_widths', not bad, bad or None)

    # reduced motion: the finance skeleton does not pulse
    mock('/__config?delay=1500')
    P = Page(b, 390, None, reduced_motion='reduce')
    P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('info'))")
    P.pg.goto(BASE + '#s-196170'); P.pg.wait_for_selector('.sp-fin-skel i', timeout=4000)
    an = P.ev("() => getComputedStyle(document.querySelector('.sp-fin-skel i')).animationName")
    check('info_reduced_motion', an == 'none', an)
    P.close()
    mock('/__config?delay=')

    # snapshot: no requests; the offline card points at the live page for 종목 정보 too
    P = Page(b, 390, SNAP + '#s-005930')
    P.pg.wait_for_timeout(900)
    t = P.ev("() => document.querySelector('.sp-offline').textContent")
    check('snapshot_mentions_info', '종목 정보' in t and '실시간 버전에서 볼 수 있어요' in t and not [u for _, u in P.reqs if 'api/' in u] and not P.console, t[:120])
    P.close()


def run_motion(b):
    """KH.motion() effects (AGENTS.md §3-5): odometer, order-book flash, bars growing in, tab cross-fade. fancy only."""
    mock('/__reset')
    base = mock('/api/stock/005930/summary')
    def mk(w, mode):   # the real KH.motion(): the level comes from localStorage khm.motion
        P = Page(b, w, None)
        P.pg.add_init_script(f"localStorage.setItem('khm.motion', JSON.stringify('{mode}'))")
        P.pg.goto(BASE)
        return P

    REFRESH = "() => document.dispatchEvent(new Event('visibilitychange'))"
    HEAD = "() => { const r = e => { const b = document.querySelector(e).getBoundingClientRect(); return [b.width, b.height]; }; return { price: document.querySelector('.sp-price').textContent, chg: document.querySelector('.sp-chg').textContent, cols: document.querySelectorAll('.sp-price .od-c, .sp-chg .od-c').length, sepCols: [...document.querySelectorAll('.od-c')].filter(c => /[,.%▲▼+−\\s]/.test(c.textContent)).length, dirs: [...new Set([...document.querySelectorAll('.od-s')].map(s => s.className.replace('od-s ', '')))], pw: r('.sp-price'), cw: r('.sp-chg') }; }"

    NOISE = lambda P: [m for m in P.console if 'Failed to load resource' not in m]   # heatmap-side 404s (close.json, breadth) are not the stock page's

    def wait_price(P, prev):
        P.pg.wait_for_function("(v) => document.querySelector('.sp-price').dataset.v !== v", arg=prev, timeout=4000); P.pg.wait_for_timeout(60)

    def opened(w, mode):
        P = mk(w, mode)
        P.pg.wait_for_timeout(500)
        assert P.ev("() => KH.motion()") == mode
        P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.wait_for_timeout(400)
        return P

    # ── 1. odometer: only in fancy ──
    res = {}
    for mode in ('standard', 'reduced', 'fancy'):
        mock('/__config?bump=')
        P = opened(1280, mode)
        h0 = P.ev(HEAD)
        pv = P.ev("() => document.querySelector('.sp-price').dataset.v")
        mock('/__config?bump=700'); P.ev(REFRESH); wait_price(P, pv)
        mid = P.ev(HEAD)
        P.pg.wait_for_timeout(700)
        end = P.ev(HEAD)
        pv = P.ev("() => document.querySelector('.sp-price').dataset.v")
        mock('/__config?bump=-900'); P.ev(REFRESH); wait_price(P, pv)
        mid2 = P.ev(HEAD)
        P.pg.wait_for_timeout(700)
        end2 = P.ev(HEAD)
        res[mode] = dict(h0=h0, mid=mid, end=end, mid2=mid2, end2=end2, err=NOISE(P))
        P.close()
    want = lambda d: f"{base['price'] + d:,}"
    for mode in ('standard', 'reduced'):
        r = res[mode]
        check(f'motion_{mode}_no_roll', r['mid']['cols'] == 0 and r['mid2']['cols'] == 0 and r['mid']['price'] == want(700) and r['end2']['price'] == want(-900 + 700 + 0) or (r['mid']['cols'] == 0 and r['mid2']['cols'] == 0 and r['mid']['price'] != r['h0']['price']), {k: r[k]['cols'] for k in ('mid', 'mid2')})
    f = res['fancy']
    up_ok = f['mid']['cols'] > 0 and f['mid']['dirs'] == ['up'] and f['end']['cols'] == 0
    dn_ok = f['mid2']['cols'] > 0 and f['mid2']['dirs'] == ['dn'] and f['end2']['cols'] == 0
    check('motion_fancy_odometer_up_down', up_ok and dn_ok, {'mid': f['mid']['dirs'], 'mid2': f['mid2']['dirs'], 'cols': [f['mid']['cols'], f['mid2']['cols']]})
    check('motion_fancy_text_is_final_text_and_separators_stay', f['mid']['price'] == f['end']['price'] and f['mid']['chg'] == f['end']['chg'] and f['mid']['sepCols'] == 0 and f['mid2']['sepCols'] == 0, {'mid': f['mid']['price'], 'end': f['end']['price']})
    dw = max(abs(f['mid']['pw'][0] - f['end']['pw'][0]), abs(f['mid']['cw'][0] - f['end']['cw'][0]), abs(f['mid2']['pw'][0] - f['end2']['pw'][0]), abs(f['mid2']['cw'][0] - f['end2']['cw'][0]))
    dh = max(abs(f['mid']['pw'][1] - f['end']['pw'][1]), abs(f['mid']['cw'][1] - f['end']['cw'][1]))
    check('motion_fancy_header_width_stable', dw < 1.5 and dh < 1.5, {'dw': dw, 'dh': dh})
    check('motion_no_console_errors_odometer', all(not res[m]['err'] for m in res), {m: res[m]['err'] for m in res})

    # ── 2. order book flash ──
    out = {}
    for mode in ('standard', 'fancy'):
        mock('/__config?bump=&obfix=1')
        P = mk(1280, mode); P.pg.wait_for_timeout(500)
        P.pg.add_init_script("localStorage.setItem('khm.stockTab', JSON.stringify('ob'))")
        P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.click('#sp-t-ob'); P.pg.wait_for_selector('.sp-q span:not(:empty)'); P.pg.wait_for_timeout(500)
        first = P.ev("() => document.querySelectorAll('#sp-p-ob [data-fl]').length")
        mock('/__config?obfix=2'); P.ev(REFRESH)
        if mode == 'fancy': P.pg.wait_for_selector('#sp-p-ob .sp-q[data-fl=up]', state='attached', timeout=5000)
        else: P.pg.wait_for_timeout(600)
        mid = P.ev("() => [document.querySelectorAll('#sp-p-ob .sp-q[data-fl=up]').length, document.querySelectorAll('#sp-p-ob .sp-q[data-fl=dn]').length, document.querySelectorAll('#sp-p-ob .sp-q:not([data-fl])').length]")
        P.pg.wait_for_timeout(900)
        end = P.ev("() => document.querySelectorAll('#sp-p-ob [data-fl]').length")
        mock('/__config?obfix=1'); P.ev(REFRESH)
        if mode == 'fancy': P.pg.wait_for_selector('#sp-p-ob .sp-q[data-fl=dn]', state='attached', timeout=5000)
        else: P.pg.wait_for_timeout(600)
        down = P.ev("() => document.querySelectorAll('#sp-p-ob .sp-q[data-fl=dn]').length")
        out[mode] = dict(first=first, mid=mid, end=end, down=down, err=NOISE(P))
        P.close()
    check('motion_ob_flash_fancy', out['fancy']['first'] == 0 and out['fancy']['mid'][0] > 0 and out['fancy']['mid'][1] == 0 and out['fancy']['end'] == 0 and out['fancy']['down'] > 0, out['fancy'])
    check('motion_ob_no_flash_standard', out['standard']['mid'][:2] == [0, 0] and out['standard']['down'] == 0, out['standard'])
    check('motion_no_console_errors_ob', not out['fancy']['err'] and not out['standard']['err'], out)
    mock('/__config?obfix=')

    # ── 3. bars grow once per session; tab cross-fade ──
    r3 = {}
    for mode in ('standard', 'fancy'):
        P = mk(1280, mode); P.pg.wait_for_timeout(500)
        P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.wait_for_timeout(300)
        P.pg.click('#sp-t-inv')
        fade = P.ev("() => document.getElementById('sp-p-inv').getAnimations().length")
        P.pg.wait_for_selector('#sp-p-inv .sp-today .bar i'); P.pg.wait_for_timeout(60)
        grow1 = P.ev("() => document.querySelectorAll('#sp-p-inv [data-grow]').length")
        P.pg.wait_for_timeout(1300)
        done = P.ev("() => document.querySelectorAll('#sp-p-inv [data-grow]').length")
        P.pg.click('#sp-t-ob'); P.pg.wait_for_timeout(100); P.pg.click('#sp-t-inv'); P.pg.wait_for_timeout(60)
        grow2 = P.ev("() => document.querySelectorAll('#sp-p-inv [data-grow]').length")
        P.pg.click('#sp-t-info'); P.pg.wait_for_selector('#sp-p-info .sp-fin-col .b'); P.pg.wait_for_timeout(60)
        gi = P.ev("() => document.querySelectorAll('#sp-p-info [data-grow]').length")
        r3[mode] = dict(fade=fade, grow1=grow1, done=done, grow2=grow2, info=gi, err=NOISE(P))
        P.close()
    check('motion_bars_grow_first_time_fancy', r3['fancy']['grow1'] > 0 and r3['fancy']['done'] == 0 and r3['fancy']['grow2'] == 0 and r3['fancy']['info'] > 0, r3['fancy'])
    check('motion_bars_static_in_standard', r3['standard']['grow1'] == 0 and r3['standard']['info'] == 0, r3['standard'])
    check('motion_tab_fade_fancy_only', r3['fancy']['fade'] > 0 and r3['standard']['fade'] == 0, {m: r3[m]['fade'] for m in r3})
    check('motion_no_console_errors_bars', not r3['fancy']['err'] and not r3['standard']['err'], r3)

    # ── 4. overflow 0 at the five widths while a roll is running ──
    ov = {}
    for w in (360, 390, 768, 1280, 1440):
        mock('/__config?bump=')
        P = opened(w, 'fancy')
        pv = P.ev("() => document.querySelector('.sp-price').dataset.v"); mock('/__config?bump=2300'); P.ev(REFRESH); P.pg.wait_for_selector('.sp-price .od-c', state='attached', timeout=5000)
        roll = P.ev("() => document.querySelectorAll('.od-c').length"); o = P.ev(OVERFLOW_JS)
        ov[w] = {'doc': o['doc'], 'root': o['root'], 'n': o['n'], 'roll': roll, 'err': NOISE(P)}
        P.close()
    check('motion_overflow_zero_during_roll', all(v['doc'] <= 0 and v['root'] <= 0 and v['n'] == 0 and v['roll'] > 0 and not v['err'] for v in ov.values()), ov)
    mock('/__reset')


def run_nxt(b):
    """NXT line under the header price (AGENTS.md §3-8)."""
    mock('/__reset')
    base = mock('/api/stock/005930/summary'); prev = base['price'] - base['change']
    NX = "() => { const n = document.querySelector('.sp-nxt'); const b = n.getBoundingClientRect(); return { hidden: n.hidden, text: n.textContent, cls: n.className, right: b.right, vw: innerWidth, color: getComputedStyle(n.querySelector('.pv')).color, up: getComputedStyle(document.documentElement).getPropertyValue('--up-text').trim() }; }"
    REFRESH = "() => document.dispatchEvent(new Event('visibilitychange'))"

    def go(w, cfg, motion='standard'):
        mock('/__reset'); mock('/__config?' + cfg)
        P = Page(b, w, None); P.pg.add_init_script(f"localStorage.setItem('khm.motion', JSON.stringify('{motion}'))"); P.pg.goto(BASE); P.pg.wait_for_timeout(500)
        P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.wait_for_timeout(300)
        return P
    r = {}
    for k, cfg in (('pre', 'nxt=pre'), ('after', 'nxt=after'), ('preclosed', 'nxt=preclosed'), ('afterclosed', 'nxt=afterclosed'), ('none', '')):
        P = go(1280, cfg or 'x=1'); r[k] = P.ev(NX); r[k]['err'] = P.console[:]; P.close()
    np_ = int(round(prev * 1.0611, -2)); pc = f"{(np_ - prev) / prev * 100:+.2f}%".replace('-', '−')
    ok = (not r['pre']['hidden'] and r['pre']['text'] == f"NXT 프리마켓 {np_:,} {pc} · 08:12" and 'up' in r['pre']['cls']
          and r['after']['text'].startswith('NXT 애프터마켓 ') and r['preclosed']['text'].startswith('NXT 프리마켓 마감 ') and r['afterclosed']['text'].startswith('NXT 애프터 종가 ') and r['none']['hidden'])
    check('nxt_line_texts_and_hidden_without_nxt', ok, {k: r[k]['text'] for k in r})
    check('nxt_up_colour_from_palette', r['pre']['color'] != '' and r['pre']['up'] != '' and r['pre']['color'] != 'rgb(0, 0, 0)', {'c': r['pre']['color'], 'v': r['pre']['up']})
    # refresh with the summary poll
    P = go(1280, 'nxt=pre'); mock(f'/__config?nxtp={int(prev * 0.97)}'); P.ev(REFRESH)
    P.pg.wait_for_function("() => document.querySelector('.sp-nxt').classList.contains('dn')", timeout=5000)
    t = P.ev(NX)['text']; P.close()
    check('nxt_line_refreshes_with_summary', '−' in t and t.startswith('NXT 프리마켓'), t)
    # roll only in fancy
    roll = {}
    for m in ('standard', 'fancy'):
        P = go(1280, 'nxt=pre', m); mock(f'/__config?nxtp={int(prev * 1.08)}'); P.ev(REFRESH)
        try:
            P.pg.wait_for_selector('.sp-nxt .od-c', state='attached', timeout=1500 if m == 'fancy' else 800); roll[m] = True
        except Exception:
            roll[m] = False
        P.close()
    check('nxt_roll_fancy_only', roll == {'standard': False, 'fancy': True}, roll)
    # fits at all widths, no overflow
    ov = {}
    for w in (360, 390, 768, 1280, 1440):
        P = go(w, 'nxt=pre'); o = P.ev(OVERFLOW_JS); n = P.ev(NX)
        ov[w] = {'doc': o['doc'], 'root': o['root'], 'n': o['n'], 'inside': n['right'] <= n['vw'], 'err': P.console[:]}; P.close()
    check('nxt_no_overflow_all_widths', all(v['doc'] <= 0 and v['root'] <= 0 and v['n'] == 0 and v['inside'] and not v['err'] for v in ov.values()), ov)
    check('nxt_no_console_errors', not any(r[k]['err'] for k in r), None)
    mock('/__reset')


STUB_GROUPS = r"""(init) => {
  const st = { groups: init.map(g => ({ id: g[0], name: g[1], codes: [...g[2]] })), n: 100 };
  const fire = () => document.dispatchEvent(new CustomEvent('kh:watch', { detail: { codes: [...new Set(st.groups.flatMap(g => g.codes))], groups: st.groups.length } }));
  const W = KH.watch || (KH.watch = {});
  Object.assign(W, {
    has: c => st.groups.some(g => g.codes.includes(c)),
    list: id => [...new Set(st.groups.filter(g => !id || g.id === id).flatMap(g => g.codes))],
    toggle: (c, id) => { if (W.has(c)) st.groups.forEach(g => { g.codes = g.codes.filter(x => x !== c); }); else st.groups[0].codes.push(c); fire(); },
    groups: () => st.groups.map(g => ({ id: g.id, name: g.name, count: g.codes.length })),
    groupsOf: c => st.groups.filter(g => g.codes.includes(c)).map(g => g.id),
    add: (c, id) => { const g = st.groups.find(x => x.id === id); if (g && !g.codes.includes(c)) g.codes.push(c); fire(); },
    remove: (c, id) => { st.groups.forEach(g => { if (!id || g.id === id) g.codes = g.codes.filter(x => x !== c); }); fire(); },
    setGroups: (c, ids) => { st.groups.forEach(g => { g.codes = g.codes.filter(x => x !== c); if (ids.includes(g.id)) g.codes.push(c); }); fire(); },
    createGroup: name => { const id = 'g' + (++st.n); st.groups.push({ id, name: name.slice(0, 12), codes: [] }); fire(); return id; },
  });
  window.__wst = st; fire();
}"""


def run_groups(b):
    """관심종목 group picker on the ☆ (AGENTS.md §3-11), with KH.watch stubbed per the contract."""
    mock('/__reset')
    res = {}
    for w in (360, 390, 768, 1280, 1440):
        P = Page(b, w, BASE); P.pg.wait_for_timeout(500)
        P.ev(STUB_GROUPS, [['base', '기본', []]])
        P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.wait_for_timeout(300)
        r = {}
        # single 기본 group: instant toggle, no picker
        P.pg.click('.sp-star'); P.pg.wait_for_timeout(100)
        r['single'] = P.ev("() => [!!document.querySelector('.sp-gp'), document.querySelector('.sp-star').getAttribute('aria-pressed'), __wst.groups[0].codes.length]")
        P.pg.click('.sp-star'); P.pg.wait_for_timeout(100)
        # a second group appears -> picker
        P.ev("() => KH.watch.createGroup('반도체')"); P.pg.wait_for_timeout(100)
        P.pg.click('.sp-star'); P.pg.wait_for_selector('.sp-gp')
        r['rows'] = P.ev("() => [...document.querySelectorAll('.sp-gp-row')].map(x => x.textContent)")
        r['focus_in'] = P.ev("() => document.querySelector('.sp-gp').contains(document.activeElement)")
        P.pg.keyboard.press('Space'); P.pg.wait_for_timeout(100)
        r['checked'] = P.ev("() => [__wst.groups.map(g => g.codes.length), document.querySelector('.sp-star').getAttribute('aria-pressed')]")
        # new group inline
        P.pg.click('.sp-gp-add'); P.pg.fill('.sp-gp-in', '배당주'); P.pg.keyboard.press('Enter'); P.pg.wait_for_timeout(150)
        r['new'] = P.ev("() => [__wst.groups.map(g => g.name + ':' + g.codes.length), [...document.querySelectorAll('.sp-gp-row input')].map(i => i.checked)]")
        o = P.ev(OVERFLOW_JS)
        r['sheet'] = P.ev("() => document.querySelector('.sp-gp').classList.contains('sp-gp-sheet')")
        r['inview'] = P.ev("() => { const b = document.querySelector('.sp-gp').getBoundingClientRect(); return b.left >= -0.5 && b.right <= innerWidth + 0.5 && b.top >= 0 && b.bottom <= innerHeight + 0.5; }")
        # uncheck all -> star empty; Esc closes the picker only and returns focus to the star
        P.pg.uncheck('.sp-gp-row input >> nth=0'); P.pg.uncheck('.sp-gp-row input >> nth=2') if P.ev("() => document.querySelectorAll('.sp-gp-row input')[2].checked") else None
        r['empty'] = P.ev("() => document.querySelector('.sp-star').getAttribute('aria-pressed')")
        P.pg.keyboard.press('Escape'); P.pg.wait_for_timeout(100)
        r['esc'] = P.ev("() => [!document.querySelector('.sp-gp'), KHStock.isOpen(), document.activeElement.classList.contains('sp-star')]")
        r['err'] = P.console[:]; r['ov'] = [o['doc'], o['root'], o['n']]
        res[w] = r; P.close()
    ok = all(r['single'] == [False, 'true', 1] and r['rows'] == ['기본0', '반도체0'] and r['focus_in'] and r['checked'][0] == [1, 0] and r['checked'][1] == 'true'
             and r['new'][0] == ['기본:1', '반도체:0', '배당주:1'] and r['new'][1] == [True, False, True] and r['empty'] == 'false' and r['esc'] == [True, True, True] for r in res.values())
    check('groups_picker_flow_all_widths', ok, {w: {k: r[k] for k in ('single', 'rows', 'checked', 'new', 'empty', 'esc')} for w, r in list(res.items())[:2]})
    check('groups_picker_sheet_on_phones_popover_otherwise', all(r['sheet'] == (w < 700) and r['inview'] for w, r in res.items()), {w: [r['sheet'], r['inview']] for w, r in res.items()})
    check('groups_no_overflow_no_console_errors', all(r['ov'] == [0, 0, 0] or (r['ov'][0] <= 0 and r['ov'][1] <= 0 and r['ov'][2] == 0) for r in res.values()) and not any(r['err'] for r in res.values()), {w: [r['ov'], r['err']] for w, r in res.items()})
    # no groups API: today's instant toggle
    P = Page(b, 390, BASE); P.pg.wait_for_timeout(500)
    P.ev("() => { const s = new Set(); const W = KH.watch || (KH.watch = {}); for (const k of ['groups', 'groupsOf', 'setGroups', 'createGroup']) delete W[k]; Object.assign(W, { has: c => s.has(c), toggle: c => { s.has(c) ? s.delete(c) : s.add(c); document.dispatchEvent(new CustomEvent('kh:watch')); } }); document.dispatchEvent(new CustomEvent('kh:watch')); }")
    P.ev("() => KHStock.open('005930')"); P.wait_chart(); P.pg.click('.sp-star'); P.pg.wait_for_timeout(100)
    check('groups_missing_api_keeps_instant_toggle', P.ev("() => [!document.querySelector('.sp-gp'), document.querySelector('.sp-star').getAttribute('aria-pressed')]") == [True, 'true'])
    P.close()


if __name__ == '__main__':
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py')], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            try:
                if '--motion-only' in sys.argv:
                    run_motion(browser)
                elif '--nxt-only' in sys.argv:
                    run_nxt(browser)
                elif '--groups-only' in sys.argv:
                    run_groups(browser)
                elif '--info-only' in sys.argv:
                    run_info(browser)
                else:
                    if '--extra-only' not in sys.argv:
                        run(browser)
                    run_extra(browser)
                    run_info(browser)
                    run_motion(browser)
                    run_nxt(browser)
                    run_groups(browser)
            finally:
                browser.close()
    finally:
        srv.terminate()
        srv.wait(5)
    passed = sum(1 for v in R.values() if v['ok'])
    print(f'\n{passed}/{len(R)} passed' + (f'  FAILED: {FAILS}' if FAILS else ''))
    if '--extra-only' not in sys.argv and '--info-only' not in sys.argv and '--motion-only' not in sys.argv and '--nxt-only' not in sys.argv and '--groups-only' not in sys.argv:
        (HERE / 'results.json').write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if FAILS else 0)
