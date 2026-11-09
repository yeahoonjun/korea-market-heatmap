#!/usr/bin/env python3
"""End-to-end checks for the stock page (src/stock) against the mock API.

    python3 scripts/build_page.py && python3 qa/stock/test_stock.py      [--extra-only: just 뉴스·공시 / 관심종목 / 상·하한가]

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
LIVE_URL = 'https://korea-market-heatmap.ssslot.workers.dev/'
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
        self.pg.on('console', lambda m: self.console.append(f'{m.type}: {m.text}') if m.type in ('error', 'warning') else None)
        self.pg.on('pageerror', lambda e: self.console.append(f'pageerror: {e}'))
        self.pg.on('request', lambda r: self.reqs.append((time.time(), r.url)))
        if url:
            self.pg.goto(url)

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
    for tf in ['1d', '5d', '3m', '1y', '3y', '10y']:
        since = time.time()
        pg.click(f'.sp-tfs button[data-tf="{tf}"]')
        P.wait_chart()
        pg.wait_for_timeout(250)
        info = P.ev("() => ({ legend: document.querySelector('.sp-legend').textContent, aria: document.querySelector('.sp-chart').getAttribute('aria-label'), canvases: document.querySelectorAll('.sp-chart canvas').length, pressed: document.querySelector('.sp-tfs [aria-pressed=true]').dataset.tf })")
        info['req'] = P.count(f'chart?tf={tf}', since)
        tfs[tf] = info
        pg.screenshot(path=str(SHOTS / f'live390_tf_{tf}.png'))
    check('all_6_timeframes_render', all(v['legend'] and v['canvases'] >= 3 and v['pressed'] == k and '봉' in v['aria'] for k, v in tfs.items()), {k: v['aria'][-40:] for k, v in tfs.items()})
    # KST even though the browser is in New York: the first 1d bar is 09:00
    pg.click('.sp-tfs button[data-tf="1d"]'); P.wait_chart()
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
    pg.click('.sp-tfs button[data-tf="5d"]'); P.wait_chart(); pg.wait_for_timeout(200)
    p5 = P.ev("() => document.querySelector('.sp-period').textContent")
    # 5일: from the close before the window (11/02) to the last bar, not from the first bar's open
    j5 = mock('/api/stock/005930/chart?tf=5d')
    want = '%.2f%%' % abs((j5['bars'][-1]['c'] / j5['prevClose'] - 1) * 100)
    check('period_base_5d_is_close_before_window', p5.startswith('5일 동안') and p5.endswith(want), {'shown': p5, 'want': want, 'prevClose': j5['prevClose']})
    P.pg.set_viewport_size({'width': 390, 'height': 844})
    pg.click('.sp-tfs button[data-tf="1d"]'); P.wait_chart(); pg.wait_for_timeout(200)
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
    check('empty_states', '거래 기록이 없어요' in em['chart'] and '호가가 없어요' in em['ob'] and '기록이 없어요' in em['inv'] and '일별 시세가 없어요' in em['daily'], em)
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
        for tab in ('ob', 'inv', 'daily', 'news'):
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
        s = P.ev("() => ({ open: KHStock.isOpen(), name: document.getElementById('sp-name').textContent, price: document.querySelector('.sp-price').textContent, href: document.querySelector('.sp-offline a').href, text: document.querySelector('.sp-offline h2').textContent, chart: !!document.querySelector('.sp-chart') })")
        s['api'] = [u for _, u in P.reqs if 'api/' in u]
        s['lwc'] = [u for _, u in P.reqs if 'lightweight' in u]
        s['overflow'] = P.ev(OVERFLOW_JS)
        if w in (390, 1440):
            P.pg.screenshot(path=str(SHOTS / f'snap{w}.png'))
            ok = (s['open'] and s['name'] == '삼성전자' and s['price'] and s['href'] == LIVE_URL + '#s-005930' and '실시간 버전에서 볼 수 있어요' in s['text']
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
  // stand-in for the heatmap's KH.watch (AGENTS.md §3-2) until it lands on main
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
})"""
LIM_JS = "() => { const l = document.querySelector('.sp-lim'); return l.hidden ? '' : l.textContent + '|' + l.className + '|' + getComputedStyle(l).color; }"


def run_extra(b):
    """뉴스·공시 tab, 관심종목 star, 상한가/하한가 badge (AGENTS.md §3-2)."""
    import re
    # ── news: fetched only when the tab opens, both lists, cached 5 minutes per code ──
    mock('/__reset')
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
          and ds['times'][0] == '3일 전' and ds['times'][-1] == '7월 31일' and '시장조치' in ds['note'],
          {'rows': ds['rows'], 'tags': ds['tags'], 'times': [ds['times'][0], ds['times'][-1]], 'link0': ds['links'][0][0]})
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

    # ── 관심종목 star ──
    P = Page(b, 390, BASE)
    pg = P.pg
    pg.wait_for_timeout(600)
    P.ev("() => KHStock.open('005930')"); pg.wait_for_timeout(400)
    hidden_without = P.ev("() => document.querySelector('.sp-star').hidden && getComputedStyle(document.querySelector('.sp-star')).display === 'none'")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
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
    check('watch_star', ok, {'hidden_without_api': hidden_without, 'off': st0, 'on': st1, 'external_toggle': st2, 'keyboard': st3})
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
                if '--extra-only' not in sys.argv:
                    run(browser)
                run_extra(browser)
            finally:
                browser.close()
    finally:
        srv.terminate()
        srv.wait(5)
    passed = sum(1 for v in R.values() if v['ok'])
    print(f'\n{passed}/{len(R)} passed' + (f'  FAILED: {FAILS}' if FAILS else ''))
    if '--extra-only' not in sys.argv:
        (HERE / 'results.json').write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if FAILS else 0)
