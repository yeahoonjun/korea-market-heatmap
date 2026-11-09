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
PORT = 8796
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
    keys = pg.eval_on_selector_all('#strip .xs-item', 'els => els.map(e => e.dataset.k)')
    check('strip live: 8 items in contract order', keys == ['KOSPI', 'KOSDAQ', 'USDKRW', 'SPX_F', 'NDX_F', 'WTI', 'GOLD', 'BTC'], str(keys))
    sparks = pg.eval_on_selector_all('#strip .xs-item', 'els => els.filter(e => e.querySelector(".xs-spark path")).map(e => e.dataset.k)')
    check('strip live: sparklines only on KOSPI/KOSDAQ', sparks == ['KOSPI', 'KOSDAQ'], str(sparks))
    delayed = pg.eval_on_selector_all('#strip .xs-d', 'els => els.map(e => e.closest(".xs-item").dataset.k + ":" + e.textContent)')
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
    check('strip live: refreshes after 30 s', n0 == 1 and n1 == 2, f'{n0}->{n1}')
    pg.evaluate('''() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'}); document.dispatchEvent(new Event('visibilitychange')); }''')
    pg.clock.run_for(95000); pg.wait_for_timeout(300)
    n2 = sum('/api/market' in u for u in reqs)
    check('strip live: no fetch while hidden', n2 == n1, f'{n1}->{n2}')
    pg.evaluate('''() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'}); document.dispatchEvent(new Event('visibilitychange')); }''')
    pg.wait_for_timeout(400)
    n3 = sum('/api/market' in u for u in reqs)
    check('strip live: fetches at once when visible again', n3 == n2 + 1, f'{n2}->{n3}')
    # failure after data: keep values, mark stale
    ERR.expect_net = True
    api('/__mode?market=fail')
    pg.clock.run_for(31000); pg.wait_for_timeout(400)
    st = pg.evaluate('() => ({items: document.querySelectorAll("#strip .xs-item").length, t: document.querySelector("#strip .xs-t").textContent})')
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
    check('image live: table view explains instead of failing', '지도 보기' in (pg.text_content('.xt-toast') or ''))
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
    pg.click('.rp-speed button[data-v="4"]')
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
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 18; el.dispatchEvent(new Event("input", {bubbles: true})); }')
    pg.wait_for_timeout(150)
    check('replay: slider seeks to 10:30', pg.text_content('.rp-time') == '10:30' and pg.evaluate('() => window.__shimReplay.t') == '1030')
    # play to the end at 4× → stops on 15:30
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 74; el.dispatchEvent(new Event("input", {bubbles: true})); }')
    pg.click('.rp-play'); pg.wait_for_timeout(1500)
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
        pg.set_viewport_size({'width': w, 'height': WIDTHS[w]}); pg.wait_for_timeout(250)
        ov = pg.evaluate(OVERFLOW_JS)
        rp = pg.evaluate('() => { const r = document.querySelector(".rp").getBoundingClientRect(); return [r.left, r.right]; }')
        check(f'replay open {w}: no overflow, player inside viewport', ov['sw'] <= ov['cw'] and rp[0] >= -0.5 and rp[1] <= w + 0.5, f'{ov} {rp}')
    pg.set_viewport_size({'width': 1440, 'height': 900}); pg.wait_for_timeout(200)
    pg.click('#q'); pg.keyboard.type('삼성'); pg.keyboard.press('Space')
    check('replay: Space in the search box types, does not play', pg.input_value('#q') == '삼성 ' and pg.get_attribute('.rp-play', 'aria-label') == '재생')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    check('replay: Esc in the search box leaves the player open', not pg.evaluate('() => document.querySelector(".rp").hidden'))
    pg.focus('.rp-speed button[data-v="2"]'); pg.keyboard.press('Space'); pg.wait_for_timeout(250)
    check('replay: Space on a focused button toggles play only (no click)', pg.get_attribute('.rp-play', 'aria-label') == '멈춤' and pg.get_attribute('.rp-speed button[data-v="2"]', 'aria-pressed') == 'false')
    pg.keyboard.press('Space'); pg.wait_for_timeout(100)
    pg.focus('[data-x=replay]')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    restored = pg.evaluate('() => [...document.querySelectorAll("#map .tile")].slice(0, 40).map(e => e.style.backgroundColor)')
    st = pg.evaluate('() => ({shim: window.__shimReplay, hidden: document.querySelector(".rp").hidden, focus: document.activeElement.dataset.x, crumbs: !!document.querySelector("#crumbs .c")})')
    check('replay: Esc closes → setReplay(null), live colours back, focus to button', st['shim'] is None and st['hidden'] and st['focus'] == 'replay' and restored == before, str(st))
    ctx.close()
    # mobile player
    ctx, pg, _ = open_page(b, LIVE, 390, 844, mobile=True)
    pg.click('#extras-tools [data-x=replay]')
    pg.wait_for_function('() => document.querySelector(".rp-time") && document.querySelector(".rp-time").textContent === "09:00"', timeout=5000)
    pg.eval_on_selector('.rp-slider', 'el => { el.value = 22; el.dispatchEvent(new Event("input", {bubbles: true})); }')
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(SHOTS / 'live_390_replay.png'))
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
    m = pg.inner_text('.rp')
    check('replay: no recordings → explains 09:00 + 5분', '다음 거래일 09:00' in m and '5분' in m, m.replace('\n', ' / '))
    pg.screenshot(path=str(SHOTS / 'live_1440_replay_empty.png'))
    pg.keyboard.press('Escape'); ctx.close()
    api('/__mode?replay=fail')
    ctx, pg, _ = open_page(b, LIVE)
    pg.click('#extras-tools [data-x=replay]'); pg.wait_for_timeout(500)
    m = pg.inner_text('.rp')
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
    check('reduced motion: player animation off', pg.evaluate('() => getComputedStyle(document.querySelector(".rp")).animationName') == 'none')
    ctx.close()

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


def png_ok(path):
    data = pathlib.Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return False, 'not png'
    w = int.from_bytes(data[16:20], 'big'); h = int.from_bytes(data[20:24], 'big')
    return w > 400 and h > 400, f'{w}x{h} {len(data) // 1024}KB'


if __name__ == '__main__':
    main()
