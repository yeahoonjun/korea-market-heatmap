#!/usr/bin/env python3
"""떠 있는 창의 열림 · 닫힘 (design.md §5 · §7 · §8, AGENTS §3-35 — 사용자 2026-11-15 19:49~19:53).

Starts qa/float/mock_float.py on FLOAT_QA_PORT (default 8970; 8970–8979 only) and stops it at the end (fuser -k).
Checks, on the live build (web/), with 효과 = 기본 unless said:
  phones 390 × 844 (touch): 표시 설정 sheet (comes up from the bottom edge, leaves drawn through `close`, re-open mid-exit turns around,
    Esc → focus back, drag the head down to dismiss · a short slow drag springs back), 일정 tab sheet (화면 · 아래 막대 rows, no empty
    heading, map rows hidden), 빠른 보기 sheet (+ scrim fade, drag the grip), 가격 기준 menu, 관심 그룹 sheet (rows kept through the
    exit), tab order, pills (one-line = two-line height, ≥ 52px), clock gap under the header's top edge, 휴장 pill clear of the tabs,
    the map top.
  tablets 1000 × 900: 표시 설정 popover grows out of its key.
  desktop 1440 × 900: 화면 · 색 기준 popovers (clip from the key, exit drawn, Esc → focus), tooltip (fades in place, follows,
    lingers 130ms), 빠른 보기 floating sheet, 관심 그룹 popover, 검색 제안, 세계 시각 popover, 티커 항목 dialog (kept until the exit
    ends, then removed), 해외 detail sheet, 리플레이 panel.
  줄이기: everything at once.  Console: 0 errors.
Timing samples are loose (a busy machine): re-run a failing check once before chasing it.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('FLOAT_QA_PORT', 8970))
assert 8970 <= PORT <= 8979, 'ports 8970–8979'
URL = f'http://127.0.0.1:{PORT}/'
SHOTS = pathlib.Path(os.environ.get('FLOAT_QA_SHOTS', ROOT / 'qa/shots/float_motion'))
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FAILS, PASSES = [], []
ERRS = []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:300]}'))


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w, h, market='K', motion='standard', theme='base', extra=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{market}/{motion}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_timeout(2200)
    return ctx, pg


# sample computed style of `sel` at `times` (ms after running `act` in the page)
SAMPLE = r"""async ({sel, act, times}) => {
  const out = [], t0 = performance.now();
  if (act) (new Function(act))();
  for (const t of times) {
    await new Promise(r => setTimeout(r, Math.max(0, t0 + t - performance.now())));
    const e = document.querySelector(sel), cs = e ? getComputedStyle(e) : null;
    // y: how far the box sits below its own place (the translate, measured: a mid-flight value may be a calc() of % and px)
    let y = 0;
    if (e && cs && cs.translate && cs.translate !== 'none') {
      const Y = cs.translate.includes(' ') ? cs.translate.slice(cs.translate.indexOf(' ') + 1) : '0px';
      const pc = [...Y.matchAll(/(-?[\d.e+-]+)%/g)].reduce((a, m) => a + +m[1], 0), pxs = [...Y.matchAll(/(-?[\d.e+-]+)px/g)].reduce((a, m) => a + +m[1], 0);
      const sign = /calc\([^)]*-\s*[\d.]+px/.test(Y) ? -1 : 1;   // "calc(100% - 3px)"
      y = Math.round((pc / 100 * e.offsetHeight + (sign < 0 ? -Math.abs(pxs) : pxs)) * 10) / 10;
    }
    const p = e && e.parentElement;
    out.push({ t: Math.round(performance.now() - t0), in: !!(e && e.isConnected), d: cs && cs.display, o: cs ? +cs.opacity : null, y, cp: cs && cs.clipPath, pe: cs && cs.pointerEvents,
      open: !!e && (e.tagName === 'DIALOG' ? e.open : e.hasAttribute('hidden') ? false : (e.classList.contains('open') || !!(p && p.classList.contains('open')) || /^(wgpop|xwc|bmenu|replay-player)$/.test(e.id) || e.classList.contains('kw-sheet') || e.classList.contains('bm-in'))),
      kids: e ? e.childElementCount : 0 });
  }
  return out;
}"""


def sample(pg, sel, act, times):
    return pg.evaluate(SAMPLE, {'sel': sel, 'act': act, 'times': times})


def active(pg):
    return pg.evaluate("(() => { const a = document.activeElement; return a ? (a.id || a.className || a.tagName) : null; })()")


def touch_drag(pg, x, y, dy, steps=12, step_ms=14, hold_ms=0):
    cdp = pg.context.new_cdp_session(pg)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    for i in range(1, steps + 1):
        pg.wait_for_timeout(step_ms)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y + dy * i / steps}]})
    if hold_ms:
        pg.wait_for_timeout(hold_ms)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    cdp.detach()


def center(pg, sel):
    return pg.evaluate(f"(() => {{ const r = document.querySelector({json.dumps(sel)}).getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")


def phone(br):
    ctx, pg = open_page(br, 390, 844)
    # ── header: tab order · pills · clock gap · 휴장 pill · map top ──
    g = pg.evaluate("""() => {
      const t = document.querySelector('.tabs'), hd = document.querySelector('header.top'), ck = document.querySelector('#clock svg, #clock');
      const pill = document.querySelector('.sb-pill'), cs = getComputedStyle(t);
      return { order: [...t.querySelectorAll('button')].map(b => b.dataset.mkt).join(' '), it: cs.getPropertyValue('--it'), ib: cs.getPropertyValue('--ib'),
        tabsTop: t.getBoundingClientRect().top, clockTop: ck.getBoundingClientRect().top, panelTop: hd.getBoundingClientRect().top + (parseFloat(getComputedStyle(hd, '::before').top) || 0),
        pillBottom: pill && pill.offsetParent ? pill.getBoundingClientRect().bottom : null, mapTop: Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY),
        minW: Math.min(...[...t.querySelectorAll('button')].map(b => b.offsetWidth)) }; }""")
    check('tab order 코스피 · 코스닥 · 전체 · 테마 · 해외 · 지표 · 일정 · ★관심', g['order'] == 'K Q ALL THEME WORLD CMDTY CAL WATCH', g['order'])
    check('phone: clock ≥ 5px under the header panel top', g['clockTop'] - g['panelTop'] >= 5, g)
    check('phone: 휴장 pill ≥ 2px clear of the tab row', g['pillBottom'] is None or g['pillBottom'] <= g['tabsTop'] - 2, g)
    check('phone: every tab ≥ 52px wide (one-line pills are capsules, not circles)', g['minW'] >= 52, g['minW'])
    print('  phone map top', g['mapTop'])
    ind = {}
    for m in ('K', 'CAL'):
        pg.click(f'.tabs button[data-mkt="{m}"]'); pg.wait_for_timeout(700)
        ind[m] = pg.evaluate("(() => { const t = document.querySelector('.tabs'), b = t.querySelector('[aria-pressed=true]'), cs = getComputedStyle(t); return [b.offsetHeight - parseFloat(cs.getPropertyValue('--it')) - parseFloat(cs.getPropertyValue('--ib')) + (t.clientHeight - b.offsetTop - b.offsetHeight) , parseFloat(cs.getPropertyValue('--it')), t.clientHeight - parseFloat(cs.getPropertyValue('--it')) - parseFloat(cs.getPropertyValue('--ib'))]; })()")
    check('phone: the selected pill is as tall on 일정 (one line) as on 코스피 (two lines), 2px in from the row', ind['K'][2] == ind['CAL'][2] and ind['K'][1] == 2, ind)
    # ── 일정: 표시 설정 shows 화면 · 아래 막대, no empty heading, no map rows ──
    pg.click('#setBtn'); pg.wait_for_timeout(700)
    s = pg.evaluate("""() => { const vis = e => !!(e && e.offsetParent && getComputedStyle(e).display !== 'none');
      const more = document.getElementById('morePanel'), dk = document.querySelector('.dkset');
      return { more: [...more.querySelectorAll(':scope > .ctl')].filter(vis).length, moreHd: vis(more.querySelector('.morehd')),
        dock: [...dk.querySelectorAll(':scope > .ctl')].filter(vis).length, dockHd: vis(dk.querySelector('.dkh')),
        mapRows: [...document.querySelectorAll('#ctls > .ctl:not(.more)')].filter(vis).map(e => e.dataset.ctl) }; }""")
    check('일정: 화면 has rows under its heading (테마 · 효과 · 시계 …)', s['more'] >= 3 and s['moreHd'], s)
    check('일정: 아래 막대 has rows under its heading', s['dock'] >= 3 and s['dockHd'], s)
    check('일정: no heatmap rows (크기 · 색 기준 · 종목 수 · 색 범위 · 색상)', not s['mapRows'], s)
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / 'phone_cal_settings.png'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(800)
    pg.screenshot(path=str(SHOTS / 'phone_header_390.png'), clip={'x': 0, 'y': 0, 'width': 390, 'height': 260})

    # ── 표시 설정 sheet: open · close · re-open mid-exit · Esc · drag ──
    a = sample(pg, '#ctls', "document.getElementById('setBtn').click()", [40, 110, 900])
    check('표시 설정 opens from the bottom edge (moving at 40–110ms, at rest by 900ms)', a[0]['y'] > 30 and a[1]['y'] < a[0]['y'] and abs(a[2]['y']) < 1, a)
    check('표시 설정 open: focus moved in', pg.evaluate("document.getElementById('ctls').contains(document.activeElement)"))
    c = sample(pg, '#ctls', "document.getElementById('ctls').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [50, 120, 700])
    check('표시 설정 Esc: closed at once, drawn while it leaves, gone after', not c[0]['open'] and c[0]['d'] != 'none' and c[0]['pe'] == 'none' and c[1]['y'] > c[0]['y'] and c[2]['d'] == 'none', c)
    check('표시 설정 Esc: focus back on its key', active(pg) == 'setBtn', active(pg))
    pg.click('#setBtn'); pg.wait_for_timeout(800)
    r = pg.evaluate("""async () => { const el = document.getElementById('ctls'), y = () => { const t = getComputedStyle(el).translate; return t === 'none' ? 0 : parseFloat(t.split(' ')[1]); };
      document.getElementById('ctlsX').click(); await new Promise(r => setTimeout(r, 90)); const before = y();
      document.getElementById('setBtn').click(); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); const after = y();
      await new Promise(r => setTimeout(r, 800)); return { before, after, rest: y(), open: el.classList.contains('open') }; }""")
    check('표시 설정 re-open mid-exit turns around where it is (no jump to the bottom)', r['before'] > 5 and r['after'] <= r['before'] + 20 and abs(r['rest']) < 1 and r['open'], r)
    hx, hy = center(pg, '.ctls-hd')
    touch_drag(pg, hx, hy, 40, steps=6, step_ms=20, hold_ms=260)
    pg.wait_for_timeout(700)
    k = pg.evaluate("({ open: document.getElementById('ctls').classList.contains('open'), tr: getComputedStyle(document.getElementById('ctls')).translate })")
    check('표시 설정 drag: a short slow pull springs back (stays open)', k['open'] and k['tr'] in ('none', '0px', '0px 0px'), k)
    touch_drag(pg, hx, hy, 320, steps=10, step_ms=12)
    pg.wait_for_timeout(900)
    k = pg.evaluate("({ open: document.getElementById('ctls').classList.contains('open'), d: getComputedStyle(document.getElementById('ctls')).display, scrim: document.getElementById('scrim2').classList.contains('open'), inline: document.getElementById('ctls').style.translate })")
    check('표시 설정 drag: pulled down → dismissed (closed, scrim off, inline translate cleared)', not k['open'] and k['d'] == 'none' and not k['scrim'] and not k['inline'], k)
    check('표시 설정 drag: focus back on its key', active(pg) == 'setBtn', active(pg))

    # ── 빠른 보기 sheet (tap a tile) + scrim + drag the grip ──
    tile = pg.evaluate("(() => { const t = [...document.querySelectorAll('#map .tile')].find(t => t.offsetWidth > 60 && t.offsetHeight > 50 && t.getBoundingClientRect().top > 200 && t.getBoundingClientRect().bottom < 800); const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    pg.touchscreen.tap(tile[0], tile[1])
    a = sample(pg, '#sheet', None, [20, 900])
    sc = sample(pg, '#scrim', None, [0])
    check('빠른 보기: up from the bottom edge, at rest by 900ms; scrim on', a[1]['open'] and abs(a[1]['y']) < 1 and sc[0]['o'] > 0.99, (a, sc))
    gx, gy = center(pg, '#sheet .grab')
    touch_drag(pg, gx, gy + 2, 380, steps=8, step_ms=12)
    pg.wait_for_timeout(900)
    k = pg.evaluate("({ open: document.getElementById('sheet').classList.contains('open'), d: getComputedStyle(document.getElementById('sheet')).display, scrim: getComputedStyle(document.getElementById('scrim')).display })")
    check('빠른 보기 drag the grip → dismissed (sheet and scrim gone)', not k['open'] and k['d'] == 'none' and k['scrim'] == 'none', k)
    pg.touchscreen.tap(tile[0], tile[1]); pg.wait_for_timeout(700)
    c = sample(pg, '#sheet', "document.querySelector('#sheet .x').click()", [40, 700])
    sc = sample(pg, '#scrim', None, [0])
    check('빠른 보기 ×: leaves drawn (moving down), then gone; scrim fades', c[0]['d'] == 'block' and c[0]['y'] > 0 and c[1]['d'] == 'none', (c, sc))

    # ── 가격 기준 menu (when the chip shows) ──
    if pg.evaluate("(() => { const b = document.getElementById('bchip'); return !!(b && b.offsetParent); })()"):
        a = sample(pg, '.bm-in', "document.getElementById('bchip').click()", [30, 900])
        check('가격 기준 menu slides up', a[0]['y'] > 5 and abs(a[1]['y']) < 1, a)
        c = sample(pg, '#bmenu', "document.getElementById('bmenu').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
        check('가격 기준 menu Esc: drawn while it leaves, then gone; focus on the chip', c[0]['d'] == 'flex' and c[1]['d'] == 'none' and active(pg) in ('bchip',), (c, active(pg)))
    ctx.close()

    # ── 🔍 search sheet (the dock shows once the map has gone by) ──
    ctx, pg = open_page(br, 390, 844)
    pg.evaluate("scrollTo(0, document.getElementById('map').getBoundingClientRect().bottom + scrollY + 40)"); pg.wait_for_timeout(900)
    if pg.evaluate("(() => { const k = document.querySelector('.dk-k'); return !!(k && k.getClientRects().length && getComputedStyle(document.querySelector('.dock')).visibility === 'visible'); })()"):
        a = sample(pg, '.ssheet', "document.querySelector('.dk-k').click()", [30, 900])
        check('🔍 search sheet comes up from the bottom edge', a[0]['y'] > 5 and abs(a[1]['y']) < 1, a)
        gx, gy = center(pg, '.ssheet .grab')
        touch_drag(pg, gx, gy, 360, steps=8, step_ms=12)
        pg.wait_for_timeout(900)
        k = pg.evaluate("({ d: getComputedStyle(document.querySelector('.ssheet')).display, s: getComputedStyle(document.querySelector('.ss-scrim')).display })")
        check('🔍 search sheet: drag the grip → dismissed (sheet and scrim gone)', k['d'] == 'none' and k['s'] == 'none', k)
    else:
        check('🔍 search sheet: the dock shows after the map', False, 'dock not shown')
    pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(500)
    # ── 티커 항목 (a bottom sheet on phones) — 표시 설정 › 티커 항목 고르기 ──
    pg.click('#setBtn'); pg.wait_for_timeout(700)
    if pg.evaluate("!!document.querySelector('.xk-open')"):
        pg.click('.xk-open')
        a = sample(pg, 'dialog.xk', None, [20, 900])
        check('티커 항목 (phone): up from the bottom edge', a[1]['open'] and abs(a[1]['y']) < 1, a)
        hx, hy = center(pg, 'dialog.xk .xd-h')
        touch_drag(pg, hx, hy, 420, steps=8, step_ms=12)
        pg.wait_for_timeout(1000)
        k = pg.evaluate("({ n: document.querySelectorAll('dialog.xk').length, open: !!document.querySelector('dialog.xk[open]'), f: document.activeElement && document.activeElement.className })")
        check('티커 항목 (phone): drag the title → closed, removed after its exit, focus back on 고르기', k['n'] == 0 and 'xk-open' in str(k['f']), k)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # ── 세계 시각 (phones: the card from the bottom edge) ──
    if pg.evaluate("!!document.querySelector('#clock button')"):
        a = sample(pg, '#xwc', "document.querySelector('#clock button').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 60, clientY: 30}))", [30, 900])
        check('세계 시각 (phone): the card comes up from the bottom edge', a[0]['y'] > 5 and abs(a[1]['y']) < 1, a)
        hx, hy = center(pg, '#xwc .xwc-hd .xwc-h')
        touch_drag(pg, hx, hy, 300, steps=8, step_ms=12)
        pg.wait_for_timeout(900)
        check('세계 시각 (phone): drag the head → dismissed', pg.evaluate("getComputedStyle(document.getElementById('xwc')).display") == 'none')
    ctx.close()
    # ── 해외 detail (phones): sheet + scrim, drag the grip ──
    ctx, pg = open_page(br, 390, 844, market='WORLD')
    pg.wait_for_timeout(800)
    if pg.evaluate("!!document.querySelector('#world .kw-lr')"):
        a = sample(pg, '.kw-sheet', "document.querySelector('#world .kw-lr').click()", [30, 900])
        check('해외 상세 (phone): up from the bottom edge', a[0]['y'] > 5 and abs(a[1]['y']) < 1 and pg.evaluate("getComputedStyle(document.querySelector('.kw-scrim')).opacity") == '1', a)
        gx, gy = center(pg, '.kw-sheet .kw-grab')
        touch_drag(pg, gx, gy + 2, 420, steps=8, step_ms=12)
        pg.wait_for_timeout(900)
        k = pg.evaluate("({ d: getComputedStyle(document.querySelector('.kw-sheet')).display, s: getComputedStyle(document.querySelector('.kw-scrim')).display, f: document.activeElement && document.activeElement.className })")
        check('해외 상세 (phone): drag the grip → dismissed, focus back on the row', k['d'] == 'none' and k['s'] == 'none' and 'kw-lr' in str(k['f']), k)
    ctx.close()

    # ── 관심 그룹 sheet (phones) ──
    groups ={'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': ['005930', '000660']}, {'id': 'g2', 'name': '반도체', 'codes': ['000660']}], 'active': 'g2'}
    ctx, pg = open_page(br, 390, 844, market='WATCH', extra={'watchGroups': groups})
    a = sample(pg, '#wgpop', "document.querySelector('#wgchips .wgm').click()", [30, 900])
    check('관심 그룹 (phone): the card comes up from the bottom edge', a[0]['y'] > 5 and abs(a[1]['y']) < 1 and a[1]['kids'] > 2, a)
    c = sample(pg, '#wgpop', "document.getElementById('wgpop').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
    check('관심 그룹 Esc: rows kept while it leaves, cleared after; focus back on ⋯', c[0]['d'] != 'none' and c[0]['kids'] > 2 and c[1]['d'] == 'none' and c[1]['kids'] == 0 and 'wgm' in str(active(pg)), (c, active(pg)))
    ctx.close()


def tablet(br):
    ctx, pg = open_page(br, 1000, 900)
    a = sample(pg, '#ctls', "document.getElementById('setBtn').click()", [40, 900])
    v = pg.evaluate("(() => { const s = getComputedStyle(document.getElementById('ctls')); return ['--kp-t', '--kp-l', '--kp-b', '--kp-rr'].map(k => s.getPropertyValue(k)); })()")
    check('tablet 표시 설정: grows out of its key (clip moving at 40ms, whole box by 900ms)', a[0]['cp'] != a[1]['cp'] and 'inset(-48px' in (a[1]['cp'] or ''), (a, v))
    check('tablet 표시 설정: the start shape is the key (top edge, key-sized)', v[0].strip() == '0px' and float(v[2].strip()[:-2] or 0) > 100, v)
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(600)
    check('tablet 표시 설정 Esc: focus back', active(pg) == 'setBtn', active(pg))
    ctx.close()


def desktop(br):
    ctx, pg = open_page(br, 1440, 900)
    # 화면 popover
    a = sample(pg, '#morePanel', "document.getElementById('moreBtn').click()", [40, 900])
    v = pg.evaluate("(() => { const p = document.getElementById('morePanel'), s = getComputedStyle(p); return { l: parseFloat(s.getPropertyValue('--kp-l')), w: p.offsetWidth }; })()")
    check('화면 popover grows out of its key (right end), whole box by 900ms', a[0]['cp'] != a[1]['cp'] and 'inset(-48px' in a[1]['cp'] and v['l'] > v['w'] - 60, (a, v))
    c = sample(pg, '#morePanel', "document.querySelector('.ctl.more').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
    check('화면 Esc: drawn while it shrinks back, gone after; focus on 화면', c[0]['d'] == 'flex' and c[0]['pe'] == 'none' and c[1]['d'] == 'none' and active(pg) == 'moreBtn', (c, active(pg)))
    # 색 기준
    a = sample(pg, '.ctl[data-ctl="colorBy"] > .seg', "document.querySelector('.ctl[data-ctl=\"colorBy\"] .ddbtn').click()", [30, 900])
    check('색 기준 popover grows (clip moving, then whole)', a[0]['cp'] != a[1]['cp'] and a[1]['d'] == 'flex', a)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # tooltip: appears in place, follows, lingers
    tiles = pg.evaluate("[...document.querySelectorAll('#map .tile')].filter(t => t.offsetWidth > 80 && t.offsetHeight > 60).slice(0, 2).map(t => { const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })")
    pg.mouse.move(tiles[0][0], tiles[0][1]); pg.wait_for_timeout(60)
    t1 = pg.evaluate("({ show: document.getElementById('tip').classList.contains('show'), l: parseFloat(document.getElementById('tip').style.left), x: %f })" % tiles[0][0])
    check('tooltip: first appearance in place (no travel)', t1['show'] and abs(t1['l'] - (t1['x'] + 18)) < 2 or (t1['show'] and t1['l'] < t1['x']), t1)
    pg.mouse.move(tiles[1][0], tiles[1][1])
    mid = pg.evaluate("parseFloat(document.getElementById('tip').style.left)")
    pg.wait_for_timeout(700)
    end = pg.evaluate("parseFloat(document.getElementById('tip').style.left)")
    check('tooltip: follows to the new tile with `follow` (between on the way, there by 700ms)', abs(end - mid) > 1 or abs(tiles[1][0] - tiles[0][0]) < 4, (t1['l'], mid, end))
    pg.mouse.move(700, 5)
    h1 = pg.evaluate("new Promise(r => setTimeout(() => r(document.getElementById('tip').classList.contains('show')), 50))")
    pg.wait_for_timeout(400)
    h2 = pg.evaluate("document.getElementById('tip').classList.contains('show')")
    check('tooltip: lingers ~130ms after leaving, then fades', h1 and not h2, (h1, h2))
    # 빠른 보기 as a floating sheet
    a = sample(pg, '#sheet', "window.KH.quick('005930', document.querySelector('#map .tile'))", [30, 900])
    check('빠른 보기 (desktop): rises and fades in', a[0]['o'] < 0.95 and a[0]['y'] > 0 and a[1]['o'] == 1 and abs(a[1]['y']) < 1, a)
    c = sample(pg, '#sheet', "document.querySelector('#sheet .x').click()", [40, 140, 700])
    check('빠른 보기 (desktop) ×: drawn while it leaves, gone after', c[0]['d'] == 'block' and c[1]['o'] < 1 and c[2]['d'] == 'none', c)
    # 검색 제안
    pg.click('#q'); pg.keyboard.type('삼성')
    a = sample(pg, '#sugg', None, [10, 900])
    check('검색 제안 grows out of the box once', a[1]['open'] and 'inset(-48px' in (a[1]['cp'] or ''), a)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pg.click('main.layout', position={'x': 5, 'y': 5}); pg.wait_for_timeout(500)
    # 세계 시각 (right click on the clock)
    if pg.evaluate("!!document.querySelector('#clock button')"):
        a = sample(pg, '#xwc', "document.querySelector('#clock button').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 60, clientY: 30}))", [40, 900])
        check('세계 시각 popover grows out of the clock', a[1]['open'] and a[0]['cp'] != a[1]['cp'], a)
        c = sample(pg, '#xwc', "document.getElementById('xwc').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
        check('세계 시각 Esc: drawn while it leaves, then gone; focus on the clock', c[0]['d'] != 'none' and c[1]['d'] == 'none' and 'clock' in json.dumps(pg.evaluate("document.activeElement.closest('#clock') ? 'clock' : document.activeElement.tagName")), c)
    # 티커 항목 dialog
    pg.click('#moreBtn'); pg.wait_for_timeout(600)
    if pg.evaluate("!!document.querySelector('.xk-open')"):
        pg.click('.xk-open'); pg.wait_for_timeout(700)
        c = sample(pg, 'dialog.xk', "document.querySelector('dialog.xk .xk-done').click()", [40, 900])
        check('티커 항목 dialog: closed at once, kept drawn while it leaves, removed after', not c[0]['open'] and c[0]['in'] and c[0]['d'] != 'none' and not c[1]['in'], c)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # 관심 그룹 popover
    ctx.close()
    groups = {'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': ['005930', '000660']}, {'id': 'g2', 'name': '반도체', 'codes': ['000660']}], 'active': 'g2'}
    ctx, pg = open_page(br, 1440, 900, market='WATCH', extra={'watchGroups': groups})
    a = sample(pg, '#wgpop', "document.querySelector('#wgchips .wgm').click()", [30, 900])
    check('관심 그룹 popover grows out of ⋯', a[0]['cp'] != a[1]['cp'] and 'inset(-48px' in (a[1]['cp'] or ''), a)
    c = sample(pg, '#wgpop', "document.getElementById('wgpop').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
    check('관심 그룹 Esc: rows kept while it leaves; focus on ⋯', c[0]['kids'] > 2 and c[0]['d'] != 'none' and c[1]['d'] == 'none' and 'wgm' in str(active(pg)), (c, active(pg)))
    ctx.close()
    # 해외 detail sheet + 리플레이
    ctx, pg = open_page(br, 1440, 900, market='WORLD')
    pg.wait_for_timeout(800)
    if pg.evaluate("!!document.querySelector('#world .kw-lr')"):
        a = sample(pg, '.kw-sheet', "document.querySelector('#world .kw-lr').click()", [30, 900])
        check('해외 상세 (desktop): rises and fades in', a[0]['o'] < 0.95 and a[1]['o'] == 1 and abs(a[1]['y']) < 1, a)
        c = sample(pg, '.kw-sheet', "document.querySelector('.kw-sheet').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", [40, 700])
        check('해외 상세 Esc: drawn while it leaves, then gone; focus back on the row', c[0]['d'] != 'none' and c[1]['d'] == 'none' and 'kw-lr' in str(active(pg)), (c, active(pg)))
    ctx.close()
    ctx, pg = open_page(br, 1440, 900)
    rb = pg.evaluate("(() => { const b = [...document.querySelectorAll('#extras-tools button')].find(b => /리플레이|다시 보기/.test(b.getAttribute('aria-label') || b.textContent)); if (b) b.setAttribute('data-qa', 'rp'); return !!b; })()")
    if rb:
        a = sample(pg, '#replay-player', "document.querySelector('[data-qa=rp]').click()", [30, 900])
        check('리플레이 panel rises and fades in', a[0]['o'] < 0.95 and a[1]['o'] == 1, a)
        c = sample(pg, '#replay-player', "document.querySelector('#replay-player .rp-x').click()", [40, 700])
        check('리플레이 panel ×: drawn while it leaves, then gone', c[0]['d'] != 'none' and c[1]['d'] == 'none', c)
    ctx.close()


def reduced(br):
    ctx, pg = open_page(br, 390, 844, motion='reduced')
    a = sample(pg, '#ctls', "document.getElementById('setBtn').click()", [30])
    check('줄이기: 표시 설정 is in place at once', abs(a[0]['y']) < 1, a)
    c = sample(pg, '#ctls', "document.getElementById('ctlsX').click()", [30])
    check('줄이기: and gone at once', c[0]['d'] == 'none', c)
    ctx.close()
    ctx, pg = open_page(br, 1440, 900, motion='reduced')
    a = sample(pg, '#morePanel', "document.getElementById('moreBtn').click()", [30])
    check('줄이기: 화면 popover whole at once', 'inset(-48px' in (a[0]['cp'] or '') and a[0]['o'] == 1, a)
    ctx.close()


def main():
    start_mock()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            phone(br)
            tablet(br)
            desktop(br)
            reduced(br)
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check('console errors 0', not ERRS, ERRS[:5])
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
