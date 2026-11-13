#!/usr/bin/env python3
"""QA for src/extras (market strip, save image, PWA, replay) in both builds.

  python3 scripts/build_page.py && python3 qa/extras/test_extras.py

Starts qa/extras/mock_api.py on :8796 (live build = web/), injects qa/extras/shim.js for the template hooks that are
not merged yet, and writes screenshots + exported PNGs to qa/shots/extras/. Exit code 1 if any check fails.
"""
import base64
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHOTS = ROOT / 'qa/shots/extras'
SHOTS.mkdir(parents=True, exist_ok=True)
PORT = int(__import__('os').environ.get('EXTRAS_QA_PORT', 8796))      # EXTRAS_QA_PORT: another worktree's mock may own 8796
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SHIM = (HERE / 'shim.js').read_text(encoding='utf-8')
WIDTHS = {360: 740, 390: 844, 768: 1024, 1280: 800, 1920: 1080}
IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def api(path):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(LIVE.rstrip('/') + path, timeout=5) as r:
        return json.loads(r.read())


class Errors:
    """Console errors. While .expect_net is set (failure-mode tests), 'Failed to load resource' lines go to .expected."""
    def __init__(self):
        self.items, self.expected, self.expect_net = [], [], False

    def on_console(self, m):
        if m.type != 'error':
            return
        if self.expect_net and m.text.startswith('Failed to load resource'):
            self.expected.append(m.text)
        else:
            self.items.append(f'{m.type}: {m.text}')

    def attach(self, page):
        page.on('console', self.on_console)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


ERR = Errors()


def open_page(browser, url, width=1440, height=900, mobile=False, ua=None, shim_opts=None, init=None, reduced=False, clock=False):
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if ua:
        opts['user_agent'] = ua
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    if shim_opts is not None:
        ctx.add_init_script(f'window.__KH_SHIM = {json.dumps(shim_opts)};')
    ctx.add_init_script(SHIM)
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    if clock:
        page.clock.install()
    ERR.attach(page)
    reqs = []
    page.on('request', lambda r: reqs.append(r.url))
    page.goto(url)
    page.wait_for_function('() => document.querySelectorAll("#map .tile").length > 50', timeout=15000)
    page.wait_for_timeout(600)
    return ctx, page, reqs


OVERFLOW_JS = '() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bw: document.body.scrollWidth})'


def main():
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                api('/__reset'); break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(b)
            b.close()
    finally:
        srv.terminate()
        srv.wait()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} checks passed')
    for n, _, d in failed:
        print('  FAILED:', n, d)
    sys.exit(1 if failed else 0)


def run(b):
    # ── 1. strip, live ──
    api('/__reset')
    ctx, pg, reqs = open_page(b, LIVE)
    # the ticker repeats its list to loop: the first copy is the strip's content
    keys = pg.evaluate('() => [...document.querySelector("#strip .xs-list").querySelectorAll(".xs-item")].map(e => e.dataset.k)')
    check('strip live: 8 items in contract order', keys == ['KOSPI', 'KOSDAQ', 'USDKRW', 'SPX_F', 'NDX_F', 'WTI', 'GOLD', 'BTC'], str(keys))
    sparks = pg.evaluate('() => [...document.querySelector("#strip .xs-list").querySelectorAll(".xs-item")].filter(e => e.querySelector(".xs-spark path")).map(e => e.dataset.k)')
    check('strip live: sparklines only on KOSPI/KOSDAQ', sparks == ['KOSPI', 'KOSDAQ'], str(sparks))
    delayed = pg.evaluate('() => [...document.querySelector("#strip .xs-list").querySelectorAll(".xs-d")].map(e => e.closest(".xs-item").dataset.k + ":" + e.textContent)')
    check('strip live: futures marked 10분 지연', delayed == ['SPX_F:10분 지연', 'NDX_F:10분 지연'], str(delayed))
    txt = pg.inner_text('#strip')
    check('strip live: no NaN/undefined', not re.search(r'NaN|undefined|null', txt))
    colors = pg.evaluate('''() => { const up = getComputedStyle(document.documentElement).getPropertyValue('--up-text').trim();
      const r = [...document.querySelectorAll('#strip .xs-r')].map(e => [e.textContent, getComputedStyle(e).color]); return {up, r}; }''')
    up_rgb = pg.evaluate('''() => { const d = document.createElement('i'); d.style.color = 'var(--up-text)'; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }''')
    dn_rgb = pg.evaluate('''() => { const d = document.createElement('i'); d.style.color = 'var(--dn-text)'; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }''')
    good = all((c == up_rgb) if t.startswith('+') else (c == dn_rgb) for t, c in colors['r'])
    check('strip live: up/down colours from --up-text/--dn-text', good, str(colors['r'][:3]))
    check('strip live: #idx hidden while strip shows indices', pg.evaluate('() => getComputedStyle(document.getElementById("idx")).display') == 'none')
    pg.screenshot(path=str(SHOTS / 'live_1440.png'))
    # palette switch recolours the strip (CSS vars)
    pg.click('#palseg button[data-v="cvd"]')
    pg.wait_for_timeout(200)
    c2 = pg.evaluate('() => getComputedStyle(document.querySelector("#strip .xs-r.xs-up")).color')
    check('strip live: follows palette change', c2 != up_rgb, c2)
    pg.click('#palseg button[data-v="krg"]')
    ctx.close()

    # refresh every 30 s, only while visible (fake clock)
    api('/__reset')
    ctx, pg, reqs = open_page(b, LIVE, clock=True)
    n0 = sum('/api/market' in u for u in reqs)
    pg.clock.run_for(31000); pg.wait_for_timeout(300)
    n1 = sum('/api/market' in u for u in reqs)
    check('strip live: refreshes after 30 s', n0 >= 1 and n1 > n0, f'{n0}->{n1}')   # the template's index line (§3-20) reads /api/market too
    pg.evaluate('''() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'}); document.dispatchEvent(new Event('visibilitychange')); }''')
    pg.clock.run_for(95000); pg.wait_for_timeout(300)
    n2 = sum('/api/market' in u for u in reqs)
    check('strip live: no fetch while hidden', n2 == n1, f'{n1}->{n2}')
    pg.evaluate('''() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'}); document.dispatchEvent(new Event('visibilitychange')); }''')
    pg.wait_for_timeout(400)
    n3 = sum('/api/market' in u for u in reqs)
    check('strip live: fetches at once when visible again', n3 > n2, f'{n2}->{n3}')
    # failure after data: keep values, mark stale
    ERR.expect_net = True
    api('/__mode?market=fail')
    pg.clock.run_for(31000); pg.wait_for_timeout(400)
    st = pg.evaluate('() => ({items: document.querySelector("#strip .xs-list").querySelectorAll(".xs-item").length, t: document.querySelector("#strip .xs-t").textContent})')
    check('strip live: failed refresh keeps values + says so', st['items'] == 8 and '갱신 실패' in st['t'], json.dumps(st, ensure_ascii=False))
    ctx.close()

    api('/__mode?market=fail')
    ctx, pg, _ = open_page(b, LIVE)
    m = pg.inner_text('#strip')
    check('strip live: network failure message', '불러오지 못했어요' in m, m)
    ctx.close()
    api('/__mode?market=empty')
    ctx, pg, _ = open_page(b, LIVE)
    m = pg.inner_text('#strip')
    check('strip live: empty data message', '아직 없어요' in m, m)
    check('strip live: #idx stays when strip has no indices', pg.evaluate('() => getComputedStyle(document.getElementById("idx")).display') != 'none')
    ctx.close()
    api('/__reset')
    ERR.expect_net = False

    # ── 2. strip, snapshot ──
    ctx, pg, reqs = open_page(b, SNAP)
    keys = pg.eval_on_selector_all('#strip .xs-item', 'els => els.map(e => e.dataset.k)')
    check('strip snapshot: only KOSPI/KOSDAQ', keys == ['KOSPI', 'KOSDAQ'], str(keys))
    vals = pg.eval_on_selector_all('#strip .xs-v', 'els => els.map(e => e.textContent)')
    snap = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))['index']
    check('strip snapshot: values from page data', vals == [f"{snap['KOSPI']['value']:,.2f}", f"{snap['KOSDAQ']['value']:,.2f}"], str(vals))
    check('strip snapshot: no network requests from extras', not [u for u in reqs if '/api/' in u or 'manifest' in u or 'sw.js' in u], str([u for u in reqs if not u.startswith('file:') and not u.startswith('data:')][:5]))
    check('snapshot: no replay/install buttons', pg.eval_on_selector_all('#extras-tools button', 'els => els.map(e => e.dataset.x)') == ['image'])
    check('snapshot: no PWA tags', pg.evaluate('() => !document.querySelector("link[rel=manifest], link[rel=apple-touch-icon], meta[name=apple-mobile-web-app-capable]")'))
    check('snapshot: no service worker', pg.evaluate('() => !navigator.serviceWorker || navigator.serviceWorker.controller === null'))
    pg.screenshot(path=str(SHOTS / 'snap_1440.png'))
    ctx.close()
    # snapshot without index data → strip hidden
    src = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
    noidx = re.sub(r'"index":\{"KOSPI":\{[^}]*\},"KOSDAQ":\{[^}]*\}\}', '"index":{}', src, count=1)
    tmp = ROOT / 'qa/shots/extras/_noindex.html'
    tmp.write_text(noidx, encoding='utf-8')
    ctx, pg, _ = open_page(b, tmp.as_uri())
    check('strip snapshot: hidden when page has no index', noidx != src and pg.evaluate('() => document.getElementById("strip").hidden'))
    ctx.close()
    tmp.unlink()

    # ── 3. PWA ──
    ctx, pg, reqs = open_page(b, LIVE)
    tags = pg.evaluate('''() => ({m: document.querySelector('link[rel=manifest]')?.getAttribute('href'), a: document.querySelector('link[rel=apple-touch-icon]')?.getAttribute('href'),
      t: document.querySelector('meta[name=theme-color]')?.content, c: document.querySelector('meta[name=apple-mobile-web-app-capable]')?.content})''')
    check('pwa live: manifest/apple-touch-icon/theme-color/capable', tags == {'m': '/manifest.webmanifest', 'a': '/apple-touch-icon.png', 't': '#131418', 'c': 'yes'}, str(tags))
    reg = pg.evaluate('async () => { const r = await navigator.serviceWorker.ready; return `${r.scope} ${r.active && r.active.scriptURL}`; }')
    check('pwa live: /sw.js registered with scope /', reg == f'{LIVE} {LIVE}sw.js', reg)
    check('pwa live: no install button without a prompt (desktop Chrome)', not pg.query_selector('#extras-tools .xt-install'))
    # Android/desktop: beforeinstallprompt → button → prompt()
    pg.evaluate('''() => { const e = new Event('beforeinstallprompt', {cancelable: true}); window.__prompted = 0;
      e.prompt = () => { window.__prompted++; return Promise.resolve(); }; e.userChoice = Promise.resolve({outcome: 'accepted'}); window.dispatchEvent(e); }''')
    btn = pg.query_selector('#extras-tools .xt-install')
    check('pwa live: beforeinstallprompt shows 앱으로 설치', btn is not None and '앱으로 설치' in btn.inner_text())
    btn.click(); pg.wait_for_timeout(200)
    check('pwa live: button calls prompt() and hides after accept', pg.evaluate('() => window.__prompted') == 1 and not pg.query_selector('#extras-tools .xt-install'))
    pg.evaluate('''() => { const e = new Event('beforeinstallprompt', {cancelable: true}); e.prompt = () => Promise.resolve(); e.userChoice = new Promise(() => {}); window.dispatchEvent(e); window.dispatchEvent(new Event('appinstalled')); }''')
    check('pwa live: appinstalled hides the button', not pg.query_selector('#extras-tools .xt-install'))
    ctx.close()
    # iOS Safari hint
    ctx, pg, _ = open_page(b, LIVE, 390, 844, mobile=True, ua=IPHONE_UA)
    btn = pg.query_selector('#extras-tools .xt-install')
    check('pwa iOS Safari: 홈 화면에 추가 hint button', btn is not None and '홈 화면에 추가' in btn.inner_text())
    btn.click(); pg.wait_for_timeout(250)
    dlg = pg.query_selector('dialog.xp[open]')
    check('pwa iOS Safari: steps dialog', dlg is not None and '공유' in dlg.inner_text())
    pg.screenshot(path=str(SHOTS / 'live_390_ios_hint.png'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    check('pwa iOS Safari: Esc closes, focus returns', not pg.query_selector('dialog.xp') and pg.evaluate('() => document.activeElement.classList.contains("xt-install")'))
    ctx.close()
    ctx, pg, _ = open_page(b, LIVE, 390, 844, mobile=True, ua=IPHONE_UA, init="Object.defineProperty(navigator, 'standalone', {get: () => true});")
    check('pwa iOS: no hint when already installed (standalone)', not pg.query_selector('#extras-tools .xt-install'))
    ctx.close()
    ctx, pg, _ = open_page(b, SNAP, 390, 844, mobile=True, ua=IPHONE_UA)
    check('pwa snapshot iOS: no hint', not pg.query_selector('#extras-tools .xt-install'))
    ctx.close()

    # ── 4. save image ──
    ctx, pg, _ = open_page(b, LIVE)
    with pg.expect_download() as dl:
        pg.click('#extras-tools [data-x=image]')
    d = dl.value
    out = SHOTS / 'export_live_1440.png'
    d.save_as(str(out))
    ok, info = png_ok(out)
    check('image live: <a download> PNG', d.suggested_filename.startswith('heatmap-kosdaq-') and d.suggested_filename.endswith('.png') and ok, f'{d.suggested_filename} {info}')
    # zoomed into a sector + KOSPI: title carries the path
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(700)
    pg.click('#map .sec .hd'); pg.wait_for_timeout(900)
    with pg.expect_download() as dl:
        pg.click('#extras-tools [data-x=image]')
    dl.value.save_as(str(SHOTS / 'export_live_zoom.png'))
    check('image live: KOSPI zoomed export', dl.value.suggested_filename.startswith('heatmap-kospi-'), dl.value.suggested_filename)
    # table view → nothing to draw → message, no download
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
    pg.click('#extras-tools [data-x=image]'); pg.wait_for_timeout(300)
    check('image live: table view explains instead of failing', '지도 보기' in (pg.evaluate("() => [...document.querySelectorAll('.kbub, .xt-toast')].map(e => e.textContent).join(' ')") or ''))   # controls stage 2: result bubble (.kbub) replaced the toast
    ctx.close()
    ctx, pg, _ = open_page(b, SNAP, 390, 844, mobile=True)
    pg.click('#extras-tools [data-x=image]')
    pg.wait_for_selector('dialog.xi[open] img', timeout=5000)
    src = pg.get_attribute('dialog.xi img', 'src')
    out = SHOTS / 'export_snap_390.png'
    out.write_bytes(base64.b64decode(src.split(',', 1)[1]))
    ok, info = png_ok(out)
    txt = pg.inner_text('dialog.xi')
    check('image snapshot: dialog with PNG + long-press note', src.startswith('data:image/png') and ok and '길게 눌러' in txt, info)
    pg.screenshot(path=str(SHOTS / 'snap_390_image_dialog.png'))
    ov = pg.evaluate(OVERFLOW_JS)
    check('image snapshot 390: no overflow with dialog', ov['sw'] <= ov['cw'], str(ov))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    check('image snapshot: Esc closes, focus returns', not pg.query_selector('dialog.xi') and pg.evaluate('() => document.activeElement.dataset.x') == 'image')
    ctx.close()
    ctx, pg, _ = open_page(b, SNAP)
    pg.click('#extras-tools [data-x=image]')
    pg.wait_for_selector('dialog.xi[open] img', timeout=5000)
    src = pg.get_attribute('dialog.xi img', 'src')
    (SHOTS / 'export_snap_1440.png').write_bytes(base64.b64decode(src.split(',', 1)[1]))
    pg.screenshot(path=str(SHOTS / 'snap_1440_image_dialog.png'))
    ctx.close()

    # ── 5. replay ──
    api('/__reset')
    ctx, pg, reqs = open_page(b, LIVE)
    before = pg.evaluate('() => [...document.querySelectorAll("#map .tile")].slice(0, 40).map(e => e.style.backgroundColor)')
    pg.click('#extras-tools [data-x=replay]')
    pg.wait_for_function('() => document.querySelector(".rp-time") && document.querySelector(".rp-time").textContent === "09:00"', timeout=5000)
    pg.wait_for_timeout(200)
    st = pg.evaluate('() => ({opts: [...document.querySelectorAll(".rp-date option")].map(o => o.value), shim: window.__shimReplay, exp: document.querySelector("[data-x=replay]").getAttribute("aria-expanded"), idx: document.querySelector(".rp-idx").innerText})')
    check('replay: dates from /api/replay/dates', st['opts'] == ['2026-11-09', '2026-11-06', '2026-11-05'], str(st['opts']))
    check('replay: first frame sent to KH.setReplay', st['shim'] and st['shim']['t'] == '0900' and st['shim']['n'] > 590, str(st['shim']))
    check('replay: KOSPI/KOSDAQ shown at the frame', '코스피' in st['idx'] and '코스닥' in st['idx'] and re.search(r'\d,\d{3}\.\d\d', st['idx']), st['idx'])
    check('replay: today shows % vs previous close (from strip)', '%' in st['idx'], st['idx'])
    after = pg.evaluate('() => [...document.querySelectorAll("#map .tile")].slice(0, 40).map(e => e.style.backgroundColor)')
    check('replay: map recoloured', after != before)
    pg.screenshot(path=str(SHOTS / 'live_1440_replay.png'))
    pg.click('.rp-speed button:last-of-type')   # speeds are ms per frame now (1000/500/250…); the last is the fastest
    pg.keyboard.press('Space')
    pg.wait_for_timeout(1700)
    t1 = pg.text_content('.rp-time')
    check('replay: Space plays at 4× (frames advance)', t1 not in ('09:00', '09:05') and pg.get_attribute('.rp-play', 'aria-label') == '멈춤', t1)
    pg.keyboard.press('Space'); pg.wait_for_timeout(600)
    t2 = pg.text_content('.rp-time'); pg.wait_for_timeout(600)
    check('replay: Space pauses', t2 == pg.text_content('.rp-time') and pg.get_attribute('.rp-play', 'aria-label') == '재생', t2)
    pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(100)
    t3 = pg.text_content('.rp-time')
    pg.keyboard.press('ArrowLeft'); pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(100)
    t4 = pg.text_content('.rp-time')
    mins = lambda t: int(t[:2]) * 60 + int(t[3:])
    check('replay: ←/→ step one frame', mins(t3) - mins(t2) == 5 and mins(t3) - mins(t4) == 10, f'{t2} {t3} {t4}')
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 90; el.dispatchEvent(new Event("input", {bubbles: true})); }')   # minutes since 09:00 (§3-15 grid)
    pg.wait_for_timeout(150)
    check('replay: slider seeks to 10:30', pg.text_content('.rp-time') == '10:30' and pg.evaluate('() => window.__shimReplay.t') == '1030')
    # play to the end at 4× → stops on 15:30
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 370; el.dispatchEvent(new Event("input", {bubbles: true})); }')
    pg.click('.rp-play')
    try:
        pg.wait_for_function('() => document.querySelector(".rp-play").getAttribute("aria-label") === "재생"', timeout=6000)   # stops one beat after the last scene
    except Exception:
        pass
    check('replay: stops at 15:30', pg.text_content('.rp-time') == '15:30' and pg.get_attribute('.rp-play', 'aria-label') == '재생', pg.text_content('.rp-time'))
    # image during replay carries the frame time
    with pg.expect_download() as dl:
        pg.click('#extras-tools [data-x=image]')
    dl.value.save_as(str(SHOTS / 'export_live_replay.png'))
    check('image during replay: file named by frame', dl.value.suggested_filename.endswith('20261109-1530.png'), dl.value.suggested_filename)
    pg.select_option('.rp-date', '2026-11-06'); pg.wait_for_timeout(500)
    st = pg.evaluate('() => ({t: document.querySelector(".rp-time").textContent, sel: document.querySelector(".rp-date").selectedOptions[0].textContent, day: document.querySelector(".rp-day").textContent, idx: document.querySelector(".rp-idx").innerText, shim: window.__shimReplay})')
    check('replay: date switch loads that day', st['t'] == '09:00' and '11월 6일' in st['sel'] and st['day'] == '1/79장면' and st['shim']['t'] == '0900', json.dumps(st, ensure_ascii=False))
    check('replay: past day without base shows value only', '%' not in st['idx'], st['idx'])
    for w in WIDTHS:
        pg.set_viewport_size({'width': w, 'height': WIDTHS[w]}); pg.wait_for_timeout(900)   # the map and the ticker re-lay out after a short debounce
        ov = pg.evaluate(OVERFLOW_JS)
        rp = pg.evaluate('() => { const r = document.querySelector(".rp-player").getBoundingClientRect(); return [r.left, r.right]; }')
        check(f'replay open {w}: no overflow, player inside viewport', ov['sw'] <= ov['cw'] and rp[0] >= -0.5 and rp[1] <= w + 0.5, f'{ov} {rp}')
    pg.set_viewport_size({'width': 1440, 'height': 900}); pg.wait_for_timeout(200)
    pg.click('#q'); pg.keyboard.type('삼성'); pg.keyboard.press('Space')
    check('replay: Space in the search box types, does not play', pg.input_value('#q') == '삼성 ' and pg.get_attribute('.rp-play', 'aria-label') == '재생')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    check('replay: Esc in the search box leaves the player open', not pg.evaluate('() => document.querySelector(".rp-player").hidden'))
    pg.focus('.rp-speed button[data-v="1000"]'); pg.keyboard.press('Space'); pg.wait_for_timeout(250)   # data-v = ms per scene (1× = 1000)
    check('replay: Space on a focused button toggles play only (no click)', pg.get_attribute('.rp-play', 'aria-label') == '멈춤' and pg.get_attribute('.rp-speed button[data-v="1000"]', 'aria-pressed') == 'false')
    pg.keyboard.press('Space'); pg.wait_for_timeout(100)
    pg.focus('[data-x=replay]')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    restored = pg.evaluate('() => [...document.querySelectorAll("#map .tile")].slice(0, 40).map(e => e.style.backgroundColor)')
    st = pg.evaluate('() => ({shim: window.__shimReplay, hidden: document.querySelector(".rp-player").hidden, focus: document.activeElement.dataset.x, crumbs: !!document.querySelector("#crumbs .c")})')
    check('replay: Esc closes → setReplay(null), live colours back, focus to button', st['shim'] is None and st['hidden'] and st['focus'] == 'replay' and restored == before, str(st))
    ctx.close()
    # mobile player
    ctx, pg, _ = open_page(b, LIVE, 390, 844, mobile=True)
    pg.click('#extras-tools [data-x=replay]')
    pg.wait_for_function('() => document.querySelector(".rp-time") && document.querySelector(".rp-time").textContent === "09:00"', timeout=5000)
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 110; el.dispatchEvent(new Event("input", {bubbles: true})); }')
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(SHOTS / 'live_390_replay.png'))
    pg.tap('.rp-more'); pg.wait_for_timeout(200)            # phones: date and speed sit behind ⋯
    tap = pg.evaluate('() => [".rp-play", ".rp-speed button", ".rp-date", ".rp-x", "#extras-tools button"].map(s => { const r = document.querySelector(s).getBoundingClientRect(); return [s, Math.round(r.width), Math.round(r.height)]; })')
    check('replay 390: tap targets ≥ 40px', all(min(wd, ht) >= 40 for _, wd, ht in tap), str(tap))
    pg.tap('.rp-x'); pg.wait_for_timeout(200)
    check('replay 390: close button returns to live', pg.evaluate('() => window.__shimReplay') is None)
    ctx.close()
    # no recordings / failure
    ERR.expect_net = True
    api('/__mode?replay=empty')
    ctx, pg, _ = open_page(b, LIVE)
    pg.click('#extras-tools [data-x=replay]'); pg.wait_for_timeout(500)
    m = pg.inner_text('.rp-player')
    check('replay: no recordings → explains 09:00 + 5분', '다음 거래일 09:00' in m and '5분' in m, m.replace('\n', ' / '))
    pg.screenshot(path=str(SHOTS / 'live_1440_replay_empty.png'))
    pg.keyboard.press('Escape'); ctx.close()
    api('/__mode?replay=fail')
    ctx, pg, _ = open_page(b, LIVE)
    pg.click('#extras-tools [data-x=replay]'); pg.wait_for_timeout(500)
    m = pg.inner_text('.rp-player')
    check('replay: failure → message + retry', '불러오지 못했어요' in m and pg.query_selector('.rp-retry') is not None, m.replace('\n', ' / '))
    api('/__reset')
    pg.click('.rp-retry'); pg.wait_for_timeout(600)
    check('replay: retry recovers', pg.text_content('.rp-time') == '09:00')
    pg.keyboard.press('Escape'); ctx.close()
    api('/__mode?replay=stale')
    ctx, pg, _ = open_page(b, LIVE)
    pg.click('#extras-tools [data-x=replay]'); pg.wait_for_timeout(700)
    st = pg.evaluate('() => ({sel: document.querySelector(".rp-date").value, t: document.querySelector(".rp-time").textContent})')
    check('replay: newest date gone (404) → falls back to the next day', st == {'sel': '2026-11-09', 't': '09:00'}, str(st))
    pg.select_option('.rp-date', '2026-11-10'); pg.wait_for_timeout(500)
    st = pg.evaluate('() => ({sel: document.querySelector(".rp-date").value, day: document.querySelector(".rp-day").textContent, body: !document.querySelector(".rp-main").hidden, shim: window.__shimReplay})')
    check('replay: picking a missing day says so and keeps the player', st['sel'] == '2026-11-09' and '기록이 없어요' in st['day'] and st['body'] and st['shim'] is not None, json.dumps(st, ensure_ascii=False))
    pg.keyboard.press('Escape'); ctx.close()
    api('/__reset')
    ERR.expect_net = False

    # ── 6. missing hooks → features off, no errors ──
    for opts, url in (({'noLayout': True, 'noReplay': True}, LIVE), ({'noMounts': True}, LIVE), ({'noMounts': True, 'noLayout': True, 'noReplay': True}, SNAP)):
        n_err = len(ERR.items)
        ctx, pg, _ = open_page(b, url, shim_opts=opts)
        btns = pg.eval_on_selector_all('#extras-tools button', 'els => els.map(e => e.dataset.x)')
        pg.wait_for_timeout(300)
        check(f'missing hooks {opts}: no buttons, no errors', btns == [] and len(ERR.items) == n_err, f'{btns} {ERR.items[n_err:]}')
        ctx.close()

    # reduced motion: player has no animation
    ctx, pg, _ = open_page(b, LIVE, reduced=True)
    pg.click('#extras-tools [data-x=replay]'); pg.wait_for_timeout(300)
    check('reduced motion: player animation off', pg.evaluate('() => getComputedStyle(document.querySelector(".rp-player")).animationName') == 'none')
    ctx.close()

    # ── 8. clock: ring tip, session arc, countdown, world clock, closing-auction glow (사용자 2026-11-13 20:19) ──
    run_clock(b)

    # ── 7. overflow, both builds, 5 widths + screenshots ──
    for name, url in (('snap', SNAP), ('live', LIVE)):
        for w, hgt in WIDTHS.items():
            ctx, pg, _ = open_page(b, url, w, hgt, mobile=w < 700)
            ov = pg.evaluate(OVERFLOW_JS)
            strip = pg.evaluate('() => { const s = document.getElementById("strip"); return [s.scrollWidth, s.clientWidth]; }')
            check(f'overflow {name} {w}: page 0', ov['sw'] <= ov['cw'] and ov['bw'] <= ov['cw'], str(ov))
            if w >= 1280:
                check(f'strip {name} {w}: one row, no scrolling', strip[0] <= strip[1], str(strip))
            if w in (390, 768, 1280):
                pg.screenshot(path=str(SHOTS / f'{name}_{w}.png'))
            if name == 'live' and w == 768:
                pg.click('#extras-tools [data-x=replay]')
                pg.wait_for_function('() => document.querySelector(".rp-time") && document.querySelector(".rp-time").textContent === "09:00"', timeout=5000)
                pg.screenshot(path=str(SHOTS / 'live_768_replay.png'))
            ctx.close()
    ctx, pg, _ = open_page(b, LIVE, 1440, 900)
    pg.screenshot(path=str(SHOTS / 'live_1440.png'))
    ctx.close()
    ctx, pg, _ = open_page(b, SNAP, 390, 844, mobile=True)
    pg.screenshot(path=str(SHOTS / 'snap_390.png'))
    ctx.close()

    check('console errors: 0', not ERR.items, '; '.join(ERR.items[:5]))
    print(f'(expected network errors during failure-mode tests: {len(ERR.expected)})')


# ───────── clock (§3-6, §3-17 + the five improvements of 2026-11-13 20:19) ─────────
MAP_TOP = {360: 240, 390: 240, 768: 250, 1280: 207, 1920: 207}
CLOCK_JS = '''() => { const q = s => document.querySelector(s), r = el => { if (!el) return null; const b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
  const sec = q('.xc-sec'), btn = q('.xc-btn'), pop = q('#xwc');
  return {map: Math.round(q('#map').getBoundingClientRect().top), hdr: Math.round(q('header.top').getBoundingClientRect().height), tabs: r(q('.tabs')),
    sec: sec ? sec.textContent : null, secShown: !!sec && getComputedStyle(sec).display !== 'none', cd: !!sec && sec.classList.contains('xc-cd'),
    live: !!(sec && sec.closest('[aria-live]')), aria: btn.getAttribute('aria-label'), title: btn.title, desc: (q('#ck-desc') || {}).textContent || '',
    auc: btn.classList.contains('xc-auc'), glow: q('.xc-glo').classList.contains('run'), glowAnim: getComputedStyle(q('.xc-glo')).animationName,
    exp: btn.hasAttribute('data-world') ? 'true' : 'false', ks: btn.getAttribute('aria-keyshortcuts'),
    pop: !!pop && !pop.hidden, popBox: pop && !pop.hidden ? r(pop) : null,
    rows: pop ? [...pop.querySelectorAll('.xwc-r')].map(e => [e.dataset.k, e.querySelector('.xwc-t').textContent, e.querySelector('.xwc-st').textContent]) : [],
    note: pop ? pop.querySelector('.xwc-n').textContent : '', focus: document.activeElement === pop ? 'pop' : document.activeElement === btn ? 'clock' : (document.activeElement || {}).tagName,
    refreshes: window.__refresh || 0, sel: String(getSelection()),
    arc: [...document.querySelectorAll('.xa-arc path')].map(e => [e.getAttribute('class'), e.getAttribute('stroke'), +e.getAttribute('stroke-opacity'), e.getAttribute('d')]),
    sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth}; }'''
HIDE_JS = '''() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
  Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'}); document.dispatchEvent(new Event('visibilitychange')); }'''
CD = '\u2212'


def open_clock(b, when, width=1280, url=None, ms=None, end=None, reduced=False, motion=None, dsf=None):
    """The page at a faked KST wall time (page.clock); /api/time answers the same fake time, so the §3-17 offset stays 0.
    ms: the quotes' marketStatus (OPEN during a session: all CLOSE then means a holiday); end: /api/market session.end."""
    import datetime
    t0 = datetime.datetime.fromisoformat(when + '+09:00').timestamp() * 1000
    clk = {'t0': t0, 'real0': time.time(), 'adv': 0}
    mobile = width < 700
    ctx = b.new_context(viewport={'width': width, 'height': WIDTHS.get(width, 900)}, device_scale_factor=dsf or (2 if mobile else 1), is_mobile=mobile, has_touch=mobile,
                        reduced_motion='reduce' if reduced else 'no-preference')
    ctx.add_init_script(SHIM)
    if motion:
        ctx.add_init_script(f"try {{ localStorage.setItem('khm.motion', {json.dumps(json.dumps(motion))}); }} catch (e) {{}}")
    ctx.add_init_script("window.__refresh = 0; document.addEventListener('kh:refresh', () => window.__refresh++);")
    page = ctx.new_page()
    ERR.attach(page)
    reqs = []
    page.on('request', lambda r: reqs.append(r.url))
    page.clock.install(time=t0 / 1000)
    page.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', headers={'cache-control': 'no-store'},
                                                   body=json.dumps({'t': clk['t0'] + (time.time() - clk['real0']) * 1000 + clk['adv']})))
    if ms:
        def quotes(r):
            res = r.fetch(); j = res.json(); j['marketStatus'] = {'KOSPI': ms, 'KOSDAQ': ms}
            r.fulfill(response=res, body=json.dumps(j, ensure_ascii=False))
        page.route('**/api/quotes*', quotes)
    if end:
        def market(r):
            res = r.fetch(); j = res.json(); j['session'] = {'start': '0900', 'end': end}
            r.fulfill(response=res, body=json.dumps(j, ensure_ascii=False))
        page.route('**/api/market*', market)
    page.goto(url or LIVE)
    page.wait_for_function('() => document.querySelectorAll("#map .tile").length > 50 && document.querySelector(".xc-btn")', timeout=15000)
    page.wait_for_timeout(900)

    def advance(ms_):
        clk['adv'] += ms_
        page.clock.run_for(ms_)
    return ctx, page, reqs, advance


def touch_long_press(pg, ms=650):
    cdp = pg.context.new_cdp_session(pg)
    x, y = pg.evaluate('() => { const b = document.querySelector(".xc-btn").getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }')
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    pg.wait_for_timeout(ms)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    pg.wait_for_timeout(400)


def zoom_face(pg, path, pad=6):
    r = pg.evaluate('() => { const b = document.querySelector(".xc-btn").getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }')
    pg.screenshot(path=path, clip={'x': max(0, r[0] - pad), 'y': max(0, r[1] - pad), 'width': r[2] + 2 * pad, 'height': r[3] + 2 * pad})


def run_clock(b):
    import math
    api('/__reset')
    # ① second-hand tip: a hollow red ring, the shaft stops in its stroke; ② the session arc at 10:00 (past strong, the rest faint)
    ctx, pg, _, adv = open_clock(b, '2026-11-13T10:00:05', 1280, ms='OPEN', motion='standard')
    tip = pg.evaluate('''() => { const t = document.querySelector('.xa-sh .xa-tip'), sh = document.querySelector('.xa-sh .xa-shaft');
      const discs = [...document.querySelectorAll('.xa-sh circle')].filter(c => c.getAttribute('fill') === '#e5231b');
      return {fill: t.getAttribute('fill'), stroke: t.getAttribute('stroke'), cy: +t.getAttribute('cy'), r: +t.getAttribute('r'), sw: +t.getAttribute('stroke-width'),
        shaftTop: +sh.getAttribute('y'), shaftW: +sh.getAttribute('width'), discs: discs.length, cap: !!document.querySelector('.xa-wig > circle[r="2.8"]'),
        tail: document.querySelectorAll('.xa-sh rect').length}; }''')
    hole_bottom = tip['cy'] + tip['r'] - tip['sw'] / 2
    check('clock ① tip: hollow red ring (no disc), shaft 2.6 ends inside the ring stroke, tail + cap kept',
          tip['fill'] == 'none' and tip['stroke'] == '#e5231b' and tip['discs'] == 0 and tip['shaftW'] == 2.6
          and hole_bottom <= tip['shaftTop'] <= tip['cy'] + tip['r'] + tip['sw'] / 2 and tip['tail'] == 2 and tip['cap'], json.dumps(tip))
    st = pg.evaluate(CLOCK_JS)
    cols = {a[1] for a in st['arc']}
    past = [a for a in st['arc'] if a[0] == 'xa-a-past']
    check('clock ② arc 10:00: 09–10 sky strong, the rest faint; only sky / amber / deep orange',
          cols == {'#5cc0f2', '#ffb547', '#ee7a2c'} and len(past) == 1 and past[0][1] == '#5cc0f2' and past[0][2] == 1
          and all(a[2] < 0.5 for a in st['arc'] if a[0] == 'xa-a-left'), json.dumps(st['arc'])[:300])
    start_pt = st['arc'][0][3].split('A')[0]
    check("clock ② arc starts at the 9 o'clock spot of the rim (r 48.25, outside the ticks)", start_pt == 'M1.75 50.00', start_pt)
    check('clock ③ 10:00: no countdown, the slot shows seconds', not st['cd'] and re.fullmatch(r'\d\d', st['sec'] or ''), str(st['sec']))
    check('clock ④ title / description / aria-keyshortcuts name the world-clock shortcut', 'Shift+F10' in st['title'] and 'Shift+F10' in st['desc'] and st['ks'] == 'Shift+F10', st['title'])
    tabs_1000 = st['tabs']
    ctx.close()

    # ③ countdown before the open (08:55) and before the close (15:22); ⑤ the auction outline; nothing moves
    for w in (390, 1280):
        ctx, pg, _, adv = open_clock(b, '2026-11-13T08:55:10', w)
        st = pg.evaluate(CLOCK_JS)
        check(f'clock ③ {w} 08:55: "−0m:ss" to the open in the seconds slot, aria once a minute (no live region)',
              st['cd'] and st['secShown'] and re.fullmatch(CD + r'0[45]:\d\d', st['sec'] or '') and '개장까지 5분' in st['aria'] and not st['live'], f"{st['sec']} | {st['aria']}")
        ctx.close()
        ctx, pg, _, adv = open_clock(b, '2026-11-13T15:22:18', w, ms='OPEN')
        st = pg.evaluate(CLOCK_JS)
        check(f'clock ③ {w} 15:22: countdown to the close, aria "장 마감까지 8분"',
              st['cd'] and st['secShown'] and re.fullmatch(CD + r'07:[34]\d', st['sec'] or '') and '장 마감까지 8분' in st['aria'], f"{st['sec']} | {st['aria']}")
        check(f'clock ⑤ {w} 15:22: steady amber outline during 마감 동시호가', st['auc'], str(st['auc']))
        past = {a[1] for a in st['arc'] if a[0] == 'xa-a-past'}
        check(f'clock ② {w} 15:22: sky + amber + deep orange past, the last minutes faint',
              past == {'#5cc0f2', '#ffb547', '#ee7a2c'} and st['arc'][-1][0] == 'xa-a-left', json.dumps(st['arc'])[:200])
        check(f'clock {w} 15:22: map top {MAP_TOP[w]} unchanged, no overflow', st['map'] == MAP_TOP[w] and st['sw'] <= st['cw'], f"map {st['map']} sw {st['sw']}")
        if w == 1280:
            check('clock ③ 1280: the tabs beside the clock stay put while it counts down', st['tabs'] == tabs_1000, f'{tabs_1000} → {st["tabs"]}')
            pg.screenshot(path=str(SHOTS / 'clock_1280_1522.png'), clip={'x': 0, 'y': 0, 'width': 1280, 'height': 150})
        else:
            pg.screenshot(path=str(SHOTS / 'clock_390_1522.png'), clip={'x': 0, 'y': 0, 'width': 390, 'height': 120})
        ctx.close()

    # the analog face ×6 (ring tip + arc) at 15:22, for eyes
    for w in (1280, 390):
        ctx, pg, _, adv = open_clock(b, '2026-11-13T15:22:18', w, ms='OPEN', dsf=6)
        zoom_face(pg, str(SHOTS / f'clock_face_{w}.png'))
        ctx.close()

    # ⑤ the glow as 마감 동시호가 starts (기본); 줄이기: outline only, the countdown still ticks as plain text
    ctx, pg, _, adv = open_clock(b, '2026-11-13T15:19:45', 1280, ms='OPEN', motion='standard')
    st0 = pg.evaluate(CLOCK_JS)
    adv(15000); pg.wait_for_timeout(150)
    st1 = pg.evaluate(CLOCK_JS)
    check('clock ⑤ 15:20 (기본): one amber glow as the auction starts, then the steady outline',
          not st0['auc'] and st1['auc'] and st1['glow'] and st1['glowAnim'] == 'xcGlow', f"{st0['auc']} → {st1['auc']} {st1['glowAnim']}")
    ctx.close()
    ctx, pg, _, adv = open_clock(b, '2026-11-13T15:19:45', 1280, ms='OPEN', reduced=True)
    adv(15000); pg.wait_for_timeout(150)
    st1 = pg.evaluate(CLOCK_JS)
    t1 = st1['sec']
    adv(2000); pg.wait_for_timeout(150)
    t2 = pg.evaluate(CLOCK_JS)['sec']
    check('clock ⑤ 15:20 (줄이기): outline only, no glow animation', st1['auc'] and st1['glowAnim'] == 'none', st1['glowAnim'])
    check('clock ③ 줄이기: the countdown is plain text, still every second', st1['cd'] and t1 != t2 and re.fullmatch(CD + r'0\d:\d\d', t2 or ''), f'{t1} → {t2}')
    ctx.close()

    # weekend: a grey arc, no countdown; a 16:30 close day: arc and countdown follow /api/market session
    ctx, pg, _, adv = open_clock(b, '2026-11-14T08:55:00', 1280)
    st = pg.evaluate(CLOCK_JS)
    check('clock ② Saturday: one grey faint arc, no countdown at 08:55', [a[0] for a in st['arc']] == ['xa-a-hol'] and st['arc'][0][2] < 0.7 and not st['cd'], json.dumps(st['arc'])[:160])
    ctx.close()
    ctx, pg, _, adv = open_clock(b, '2026-11-19T16:22:30', 1280, ms='OPEN', end='1630')
    st = pg.evaluate(CLOCK_JS)
    x = 50 + 48.25 * math.sin(math.radians(135)); y = 50 - 48.25 * math.cos(math.radians(135))
    check('clock ② ③ 16:30 close day: the arc ends at 4:30, countdown + outline at 16:22',
          st['arc'][-1][3].endswith(f'{x:.2f} {y:.2f}') and st['cd'] and (st['sec'] or '').startswith(CD + '07:') and st['auc'] and '장 마감까지 8분' in st['aria'], f"{st['arc'][-1][3]} {st['sec']}")
    ctx.close()

    # hidden tab: the clock's timers stop
    ctx, pg, _, adv = open_clock(b, '2026-11-13T10:00:05', 1280, ms='OPEN')
    pg.evaluate(HIDE_JS)
    s0 = pg.evaluate(CLOCK_JS)['sec']; adv(5000); pg.wait_for_timeout(100)
    s1 = pg.evaluate(CLOCK_JS)['sec']
    check('clock: hidden tab = no clock timers (the seconds stand still)', s0 == s1, f'{s0} {s1}')
    ctx.close()

    # ④ world clock, desktop: right-click, Shift+F10, the context-menu key, a long press; Esc / outside press close it; a tap refreshes
    api('/__reset')
    ctx, pg, _, adv = open_clock(b, '2026-11-13T15:22:18', 1280, ms='OPEN')
    pg.click('.xc-btn', button='right'); pg.wait_for_timeout(500)
    st = pg.evaluate(CLOCK_JS)
    want = {k: pg.evaluate(f'() => new Intl.DateTimeFormat("en-GB", {{timeZone: "{tz}", hour: "2-digit", minute: "2-digit", hourCycle: "h23"}}).format(new Date(KH.now()))')
            for k, tz in (('INX', 'America/New_York'), ('FTSE', 'Europe/London'), ('N225', 'Asia/Tokyo'), ('HSI', 'Asia/Hong_Kong'), ('SSEC', 'Asia/Shanghai'))}
    got = {k: t for k, t, _ in st['rows']}
    stat = {k: v for k, _, v in st['rows']}
    check('clock ④ right-click: 뉴욕 · 런던 · 도쿄 · 홍콩 · 상해 local times, focus in the popover',
          st['pop'] and st['exp'] == 'true' and got == want and st['focus'] == 'pop', f'{got} vs {want}')
    check('clock ④ open / closed from /api/world, note names 네이버 증권',
          stat == {'INX': '마감', 'FTSE': '마감', 'N225': '장중', 'HSI': '장중', 'SSEC': '장중'} and '네이버 증권' in st['note'], f"{stat} {st['note']}")
    check('clock ④ right-click: no refresh, no text selection', st['refreshes'] == 0 and not st['sel'], f"{st['refreshes']} {st['sel']!r}")
    pg.screenshot(path=str(SHOTS / 'clock_1280_world.png'), clip={'x': 0, 'y': 0, 'width': 640, 'height': 360})
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ Esc closes, focus back on the clock', not st['pop'] and st['exp'] == 'false' and st['focus'] == 'clock', st['focus'])
    pg.keyboard.press('Shift+F10'); pg.wait_for_timeout(200)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ Shift+F10 on the focused clock opens it', st['pop'] and st['focus'] == 'pop', st['focus'])
    pg.keyboard.press('Tab'); pg.wait_for_timeout(80)
    check('clock ④ Tab reaches the × key inside', pg.evaluate('() => document.activeElement.classList.contains("xwc-x")'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    pg.keyboard.press('ContextMenu'); pg.wait_for_timeout(200)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ the context-menu key opens it too', st['pop'] and st['focus'] == 'pop', str(st['pop']))
    pg.mouse.click(800, 40); pg.wait_for_timeout(250)          # empty header space (a tile would open the stock page)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ outside press closes it', not st['pop'] and st['exp'] == 'false', st['focus'])
    r0 = st['refreshes']
    pg.hover('.xc-btn'); pg.mouse.down(); pg.wait_for_timeout(700); pg.mouse.up(); pg.wait_for_timeout(300)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ long press (700 ms) opens it, no refresh', st['pop'] and st['refreshes'] == r0, f"{st['pop']} {st['refreshes']}")
    pg.click('.xc-btn'); pg.wait_for_timeout(300)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ the clock pressed while it is open closes it (no refresh)', not st['pop'] and st['refreshes'] == r0, f"{st['pop']} {st['refreshes']}")
    pg.click('.xc-btn'); pg.wait_for_timeout(900)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ a short tap still refreshes (KH.refresh → kh:refresh)', not st['pop'] and st['refreshes'] == r0 + 1, str(st['refreshes']))
    ctx.close()

    # phones: a long touch opens a bottom sheet — no refresh, no selection
    ctx, pg, _, adv = open_clock(b, '2026-11-13T15:22:18', 390, ms='OPEN')
    touch_long_press(pg)
    pg.wait_for_timeout(300)
    st = pg.evaluate(CLOCK_JS)
    box = st['popBox'] or [0, 0, 0, 0]
    check('clock ④ 390 long touch: bottom sheet, no refresh, no selection',
          st['pop'] and box[0] == 8 and abs(box[1] + box[3] - (WIDTHS[390] - 8)) <= 2 and st['refreshes'] == 0 and not st['sel'], f"{box} {st['refreshes']} {st['sel']!r}")
    pg.screenshot(path=str(SHOTS / 'clock_390_world.png'))
    ov = pg.evaluate(OVERFLOW_JS)
    check('clock ④ 390 sheet: no overflow', ov['sw'] <= ov['cw'], str(ov))
    pg.touchscreen.tap(260, 30); pg.wait_for_timeout(400)       # empty header space
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ 390 outside tap closes it', not st['pop'], str(st['pop']))
    ctx.close()

    # failure: the times stay, the note says the state could not be read
    ERR.expect_net = True
    api('/__mode?world=fail')
    ctx, pg, _, adv = open_clock(b, '2026-11-13T15:22:18', 1280, ms='OPEN')
    pg.click('.xc-btn', button='right'); pg.wait_for_timeout(600)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ /api/world failing: times stay, the note says so',
          st['pop'] and all(re.fullmatch(r'\d\d:\d\d', t) for _, t, _ in st['rows']) and '불러오지 못했어요' in st['note'], st['note'])
    ctx.close()
    api('/__reset')
    ERR.expect_net = False

    # snapshot: the device clock; the popover names the live version; no network
    ctx, pg, reqs, adv = open_clock(b, '2026-11-13T15:22:18', 1280, url=SNAP)
    pg.click('.xc-btn', button='right'); pg.wait_for_timeout(400)
    st = pg.evaluate(CLOCK_JS)
    check('clock ④ snapshot: times + "실시간 버전에서 볼 수 있어요", no requests',
          st['pop'] and '실시간 버전에서 볼 수 있어요' in st['note'] and all(re.fullmatch(r'\d\d:\d\d', t) for _, t, _ in st['rows'])
          and not [u for u in reqs if '/api/' in u], st['note'])
    check('clock snapshot: device clock, countdown at 15:22', st['cd'] and (st['sec'] or '').startswith(CD + '07:'), str(st['sec']))
    ctx.close()

    # five widths: the countdown + outline (15:22) against the same session without them (10:00) — same header, same map top,
    # overflow 0 (the template's own status row is shorter in session than after hours at 768, so compare like with like)
    for w in WIDTHS:
        tops = []
        for when in ('2026-11-13T10:00:05', '2026-11-13T15:22:18'):
            ctx, pg, _, adv = open_clock(b, when, w, ms='OPEN')
            st = pg.evaluate(CLOCK_JS)
            tops.append((st['hdr'], st['map'], st['tabs'][0], st['sw'] <= st['cw']))
            ctx.close()
        check(f'clock {w}: countdown + outline move nothing (header, map top, tabs), overflow 0', tops[0] == tops[1] and tops[1][3], str(tops))


def png_ok(path):
    data = pathlib.Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return False, 'not png'
    w = int.from_bytes(data[16:20], 'big'); h = int.from_bytes(data[20:24], 'big')
    return w > 400 and h > 400, f'{w}x{h} {len(data) // 1024}KB'


if __name__ == '__main__':
    main()
