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
  at rest (2026-11-15 21:30 "ui오류"): every popover's corner is the theme's popover token, its clip cuts nothing (pixel-compared
    with the clip removed), and each selected-row highlight is on its row (±1px) and inside the card's rounded shape — 4 themes,
    1440 · 1280 · tablet 1000, and with 줄이기 at once.
Timing samples are loose (a busy machine): re-run a failing check once before chasing it.
"""
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('FLOAT_QA_PORT', 8970))
assert 8970 <= PORT <= 8979 or 9010 <= PORT <= 9029, 'ports 8970–8979 (or 9010–9029: the design-standard agents)'
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


# a popover at rest (2026-11-15 21:30 "ui오류": the 색 기준 menu was a capsule on the glass themes and its 오늘 highlight stuck out of it):
# its corner = the theme's popover token, its clip cuts nothing, and every selected-row highlight inside sits on its row (±1px) and
# inside the card's rounded shape (sampled along the highlight's own rounded outline)
SHAPE = r"""({sel, tok}) => {
  const el = document.querySelector(sel);
  if (!el) return { missing: true };
  const cs = getComputedStyle(el), R = el.getBoundingClientRect(), root = getComputedStyle(document.documentElement);
  const exp = (parseFloat(root.getPropertyValue('--tip-r')) || 10) + (tok === 'tip' ? 0 : 2);
  const rad = parseFloat(cs.borderTopLeftRadius) || 0, rEff = Math.min(rad, R.width / 2, R.height / 2);
  let clipOk = cs.clipPath === 'none', ins = null;
  const m = /^inset\(([^)]*)\)$/.exec(cs.clipPath);
  if (m) { const v = m[1].split(' round ')[0].trim().split(/\s+/).map(parseFloat); ins = [v[0], v[1] ?? v[0], v[2] ?? v[0], v[3] ?? v[1] ?? v[0]]; clipOk = ins.every(x => x <= 0); }
  const box = (l, t, r, b, rr) => ({ l, t, r, b, rr: Math.min(rr, (r - l) / 2, (b - t) / 2) });
  const inRR = (x, y, q, tol = .75) => {
    if (x < q.l - tol || x > q.r + tol || y < q.t - tol || y > q.b + tol) return false;
    const cx = Math.min(Math.max(x, q.l + q.rr), q.r - q.rr), cy = Math.min(Math.max(y, q.t + q.rr), q.b - q.rr);
    return Math.hypot(x - cx, y - cy) <= q.rr + tol;
  };
  const outline = q => { const pts = []; for (const [cx, cy, a0] of [[q.l + q.rr, q.t + q.rr, 180], [q.r - q.rr, q.t + q.rr, 270], [q.r - q.rr, q.b - q.rr, 0], [q.l + q.rr, q.b - q.rr, 90]])
    for (let a = 0; a <= 90; a += 10) { const t = (a0 + a) * Math.PI / 180; pts.push([cx + q.rr * Math.cos(t), cy + q.rr * Math.sin(t)]); } return pts; };
  const card = box(R.left, R.top, R.right, R.bottom, rad);
  const segs = [...el.querySelectorAll('.seg')].concat(el.matches('.seg') ? [el] : []).filter(s => s.offsetWidth && s.dataset.ind != null);
  const hl = segs.map(s => {
    const on = [...s.children].find(b => b.tagName === 'BUTTON' && !b.hidden && (b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-selected') === 'true'));
    if (!on) return null;
    const sr = s.getBoundingClientRect(), p = getComputedStyle(s, '::before'), sc = getComputedStyle(s), br = on.getBoundingClientRect();
    const x0 = sr.left + s.clientLeft, y0 = sr.top + s.clientTop;
    const ind = box(x0 + parseFloat(p.left), y0 + parseFloat(p.top), x0 + s.clientWidth - parseFloat(p.right), y0 + s.clientHeight - parseFloat(p.bottom), parseFloat(p.borderTopLeftRadius) || 0);
    const inX = parseFloat(sc.getPropertyValue('--ind-in')) || 0, inY = inX + (parseFloat(sc.getPropertyValue('--ind-iy')) || 0);
    const off = Math.max(Math.abs(ind.l - (br.left + inX)), Math.abs(ind.r - (br.right - inX)), Math.abs(ind.t - (br.top + inY)), Math.abs(ind.b - (br.bottom - inY)));
    const tray = box(sr.left, sr.top, sr.right, sr.bottom, parseFloat(sc.borderTopLeftRadius) || 0);
    const pts = outline(ind), outCard = pts.filter(([x, y]) => !inRR(x, y, card)).length, outTray = pts.filter(([x, y]) => !inRR(x, y, tray)).length;
    return { key: s.dataset.key || s.id || s.className, op: +p.opacity, off: Math.round(off * 100) / 100, outCard, outTray };
  }).filter(Boolean);
  return { exp, rad, rEff: Math.round(rEff * 10) / 10, w: Math.round(R.width), h: Math.round(R.height), clip: cs.clipPath, clipOk, op: +cs.opacity, d: cs.display, hl,
    rect: [R.left, R.top, R.width, R.height] };
}"""


def shape_check(pg, name, sel, tok='pop', shot_pad=56, exp=None):
    """the three rest-state checks for one open popover (call it once the open animation is over)"""
    s = pg.evaluate(SHAPE, {'sel': sel, 'tok': tok})
    if exp is not None and not s.get('missing'):
        s['exp'] = exp
    if s.get('missing'):
        check(f'{name}: open', False, s); return s
    check(f'{name}: corner = popover token {s["exp"]:g}px (not a capsule: {s["rEff"]:g}px on a {s["w"]}×{s["h"]} card)', abs(s['rad'] - s['exp']) < .5 and s['rEff'] < min(s['w'], s['h']) / 2 - 1, s)
    # the clip at rest: none, or wholly outside the box — and, measured, it changes no pixel of the card or its shadow
    x, y, w, h = s['rect']
    vw = pg.evaluate('[innerWidth, innerHeight]')
    clip = {'x': max(0, x - shot_pad), 'y': max(0, y - shot_pad), 'width': min(vw[0], x + w + shot_pad) - max(0, x - shot_pad), 'height': min(vw[1], y + h + shot_pad + 16) - max(0, y - shot_pad)}
    # the ticker, the clock and the session bar move on their own: held still (hidden) for both shots
    pg.evaluate("() => { const st = document.createElement('style'); st.id = 'qa-still'; st.textContent = '#strip,#clock,#session-bar{visibility:hidden!important}'; document.head.append(st); }")
    pg.wait_for_timeout(60)
    a = pg.screenshot(clip=clip)
    pg.evaluate("(sel) => { const e = document.querySelector(sel); e.style.setProperty('transition', 'none', 'important'); e.style.setProperty('clip-path', 'none', 'important'); }", sel)
    pg.wait_for_timeout(60)
    b = pg.screenshot(clip=clip)
    pg.evaluate("(sel) => { const e = document.querySelector(sel); e.style.removeProperty('clip-path'); e.style.removeProperty('transition'); document.getElementById('qa-still').remove(); }", sel)
    d = ImageChops.difference(Image.open(io.BytesIO(a)).convert('RGB'), Image.open(io.BytesIO(b)).convert('RGB')).convert('L')
    worst = max(i for i, n in enumerate(d.histogram()) if n)
    check(f'{name}: at rest the clip cuts nothing ({s["clip"]}; max pixel change {worst} with the clip removed)', s['clipOk'] and s['op'] == 1 and worst <= 3, (s['clip'], s['op'], worst))
    if s['hl']:
        check(f'{name}: selected-row highlight on its row (±1px) and inside the card · its tray', all(x['op'] == 1 and x['off'] <= 1 and not x['outCard'] and not x['outTray'] for x in s['hl']), s['hl'])
    return s


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
        ind[m] = pg.evaluate("(() => { const t = document.querySelector('.tabs-sc'), b = t.querySelector('[aria-pressed=true]'), cs = getComputedStyle(t); return [b.offsetHeight - parseFloat(cs.getPropertyValue('--it')) - parseFloat(cs.getPropertyValue('--ib')) + (t.clientHeight - b.offsetTop - b.offsetHeight) , parseFloat(cs.getPropertyValue('--it')), t.clientHeight - parseFloat(cs.getPropertyValue('--it')) - parseFloat(cs.getPropertyValue('--ib'))]; })()")
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
    check('tablet 표시 설정: grows out of its key (clip moving at 40ms, whole box by 900ms)', a[0]['cp'] != a[1]['cp'] and 'inset(-64px' in (a[1]['cp'] or ''), (a, v))
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
    check('화면 popover grows out of its key (right end), whole box by 900ms', a[0]['cp'] != a[1]['cp'] and 'inset(-64px' in a[1]['cp'] and v['l'] > v['w'] - 60, (a, v))
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
    check('검색 제안 grows out of the box once', a[1]['open'] and 'inset(-64px' in (a[1]['cp'] or ''), a)
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
    check('관심 그룹 popover grows out of ⋯', a[0]['cp'] != a[1]['cp'] and 'inset(-64px' in (a[1]['cp'] or ''), a)
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


def shapes(br):
    """every converted popover at rest (after `open`, and with 줄이기 at once): corner token · clip · selected-row highlight"""
    SHOTS.mkdir(parents=True, exist_ok=True)
    dd = '.ctl[data-ctl="colorBy"] > .seg'
    for theme in ('base', 'paper', 'glass-dark', 'glass-light'):
        ctx, pg = open_page(br, 1440, 900, theme=theme)
        pg.click('.ctl[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(900)
        s = shape_check(pg, f'색 기준 [{theme} 1440]', dd)
        if 'rect' in s:
            x, y, w, h = s['rect']
            pg.screenshot(path=str(SHOTS / f'pop_colorBy_{theme}.png'), clip={'x': x - 40, 'y': y - 50, 'width': w + 80, 'height': h + 90})
        # another row: pick 1개월, open again → the highlight is on 1개월
        pg.click(dd + ' button[data-v="m1"]'); pg.wait_for_timeout(600)
        pg.click('.ctl[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(900)
        on = pg.evaluate(f"document.querySelector('{dd} [aria-pressed=\"true\"]').dataset.v")
        s = shape_check(pg, f'색 기준 [{theme} 1440] after picking 1개월', dd)
        check(f'색 기준 [{theme}]: 1개월 is the selected row', on == 'm1', on)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
        pg.click('#moreBtn'); pg.wait_for_timeout(900)
        shape_check(pg, f'화면 [{theme} 1440]', '#morePanel')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
        ctx.close()
    ctx, pg = open_page(br, 1280, 900, theme='glass-dark')
    pg.click('.ctl[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(900)
    shape_check(pg, '색 기준 [glass-dark 1280]', dd)
    ctx.close()
    ctx, pg = open_page(br, 1440, 900, theme='glass-dark', extra={'sizeBy': 'fgn'})
    if pg.evaluate("!document.querySelector('.ctl[data-ctl=\"flowWin\"]').hidden"):
        pg.click('.ctl[data-ctl="flowWin"] .ddbtn'); pg.wait_for_timeout(900)
        shape_check(pg, '순매수 기간 [glass-dark 1440]', '.ctl[data-ctl="flowWin"] > .seg')
    else:
        check('순매수 기간: shown with 크기 = 외국인', False)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pg.click('#q'); pg.keyboard.type('삼성'); pg.wait_for_timeout(900)
    shape_check(pg, '검색 제안 [glass-dark 1440]', '#sugg', tok='tip')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pg.click('main.layout', position={'x': 5, 'y': 5}); pg.wait_for_timeout(400)
    if pg.evaluate("!!document.querySelector('#clock button')"):
        pg.evaluate("document.querySelector('#clock button').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 60, clientY: 30}))")
        pg.wait_for_timeout(900)
        shape_check(pg, '세계 시각 [glass-dark 1440]', '#xwc')   # the popover token since extras moved to design.md (was its own 24px)
    ctx.close()
    groups = {'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': ['005930', '000660']}, {'id': 'g2', 'name': '반도체', 'codes': ['000660']}], 'active': 'g2'}
    ctx, pg = open_page(br, 1440, 900, market='WATCH', theme='glass-dark', extra={'watchGroups': groups})
    pg.click('#wgchips .wgm'); pg.wait_for_timeout(900)
    shape_check(pg, '관심 그룹 [glass-dark 1440]', '#wgpop')
    ctx.close()
    ctx, pg = open_page(br, 1000, 900, theme='glass-dark')
    pg.click('#setBtn'); pg.wait_for_timeout(900)
    shape_check(pg, '태블릿 표시 설정 [glass-dark 1000]', '#ctls')
    ctx.close()
    # 줄이기: whole at once — the same rest state 50ms after the press
    for theme in ('glass-dark', 'base'):
        ctx, pg = open_page(br, 1440, 900, motion='reduced', theme=theme)
        pg.click('.ctl[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(50)
        shape_check(pg, f'줄이기 · 색 기준 [{theme}] at once', dd)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        pg.click('#moreBtn'); pg.wait_for_timeout(50)
        shape_check(pg, f'줄이기 · 화면 [{theme}] at once', '#morePanel')
        ctx.close()
    ctx, pg = open_page(br, 1000, 900, motion='reduced', theme='glass-dark')
    pg.click('#setBtn'); pg.wait_for_timeout(50)
    shape_check(pg, '줄이기 · 태블릿 표시 설정 [glass-dark] at once', '#ctls')
    ctx.close()


TABS = r"""() => {
  const t = document.querySelector('.tabs'), sc = t.querySelector(':scope > .tabs-sc'), w = t.querySelector(':scope > .tpin');
  const R = e => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; };
  const scR = R(sc), hd = document.querySelector('header.top'), hs = getComputedStyle(hd), hr = R(hd);
  const inner = { l: hr.l + parseFloat(hs.paddingLeft), r: hr.r - parseFloat(hs.paddingRight) };
  const all = [...sc.querySelectorAll(':scope > button'), w];
  const btn = Object.fromEntries(all.map(b => [b.dataset.mkt, R(b)]));
  const seps = [...t.querySelectorAll('.tsep')].map(s => ({ ...R(s), hidden: s.getAttribute('aria-hidden') }));
  // every label: the part inside the scroller's box (or all of ★관심's) is hit-tested at 5 points — only its own button may answer
  const covered = [];
  for (const b of all) {
    const rg = document.createRange(); rg.selectNodeContents(b.querySelector('.tn') || b);
    for (const q of rg.getClientRects()) {
      const l = b === w ? q.left : Math.max(q.left, scR.l), r = b === w ? q.right : Math.min(q.right, scR.r);
      if (r - l < 2) continue;
      for (let k = 0; k < 5; k++) { const x = l + 1 + (r - l - 2) * k / 4, y = (q.top + q.bottom) / 2, e = document.elementFromPoint(x, y);
        if (!e || !b.contains(e)) covered.push([b.dataset.mkt, Math.round(x), e ? (e.className || e.tagName) : null]); }
    }
  }
  const p = getComputedStyle(sc, '::before'), own = getComputedStyle(w, '::before'), wr = R(w);
  const ind = { l: scR.l + sc.clientLeft + parseFloat(p.left) - sc.scrollLeft, r: scR.l + sc.clientLeft + sc.clientWidth - parseFloat(p.right) - sc.scrollLeft,
    t: scR.t + sc.clientTop + parseFloat(p.top), b: scR.t + sc.clientTop + sc.clientHeight - parseFloat(p.bottom), op: +p.opacity };
  const ownR = { l: wr.l + parseFloat(own.left), r: wr.r - parseFloat(own.right), t: wr.t + parseFloat(own.top), b: wr.b - parseFloat(own.bottom), op: +own.opacity };
  const sel = t.querySelector('button[aria-pressed="true"]'), cs = getComputedStyle(sc);
  const inX = parseFloat(cs.getPropertyValue('--ind-in')) || 0, inY = inX + (parseFloat(cs.getPropertyValue('--ind-iy')) || 0);
  const mask = cs.webkitMaskImage || cs.maskImage || 'none';
  return { sc: scR, inner, hdr: hr, sl: sc.scrollLeft, max: sc.scrollWidth - sc.clientWidth, more: sc.classList.contains('more-r'), mask, pin: t.dataset.pin || null,
    btn, seps, covered, ind, own: ownR, inX, inY, sel: sel && sel.dataset.mkt,
    wHit: [wr.l + 3, (wr.l + wr.r) / 2, wr.r - 3].every(x => { const e = document.elementFromPoint(x, (wr.t + wr.b) / 2); return !!e && w.contains(e); }),
    selHit: !!sel && (() => { const r = R(sel), e = document.elementFromPoint((r.l + r.r) / 2, (r.t + r.b) / 2); return !!e && sel.contains(e); })(),
    map: Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY), vw: innerWidth, sticky: getComputedStyle(w).position };
}"""


def tabgroups(br):
    """the market tabs in three groups; on phones ★관심 sits outside the sideways scroller (사용자 2026-11-15 21:38~21:40, and 22:35:
    Samsung Internet left the old sticky ★관심 half off the header and the fade in the middle of 지표)"""
    for w, h, top in ((360, 740, 247), (384, 832, 247), (390, 844, 247), (412, 915, 247), (768, 1024, 250), (1280, 800, 207)):
        for theme in (('base', 'glass-dark') if w in (384, 390) else ('base',)):
            ctx, pg = open_page(br, w, h, theme=theme)
            tag = f'[{w}{" " + theme if theme != "base" else ""}]'
            phone = w <= 760
            ends = {}
            for nm, sl in (('start', '0'), ('end', '1e5')):
                pg.evaluate(f"document.querySelector('.tabs-sc').scrollLeft = {sl}"); pg.wait_for_timeout(150)
                ends[nm] = pg.evaluate(TABS)
            s, e = ends['start'], ends['end']
            check(f'tabs {tag}: map top {s["map"]} (= {top}); ★관심 not sticky', s['map'] == top and s['sticky'] != 'sticky', (s['map'], s['sticky']))
            b, sp = e['btn'], e['seps']
            th = b['K']['h']
            check(f'tabs {tag}: two dividers, aria-hidden, between 전체|테마 and the row|★관심, ~60 % of a tab',
                  len(sp) == 2 and all(x['hidden'] == 'true' for x in sp)
                  and b['ALL']['r'] <= sp[0]['l'] + .5 and sp[0]['r'] <= b['THEME']['l'] + .5 and min(b['CAL']['r'], e['sc']['r']) <= sp[1]['l'] + .5 and sp[1]['r'] <= b['WATCH']['l'] + .5
                  and all(.5 <= x['h'] / th <= .7 for x in sp), (sp, th, {k: (round(v['l']), round(v['r'])) for k, v in b.items()}))
            for nm, x in ends.items():
                wr = x['btn']['WATCH']
                check(f'tabs {tag}: row at its {nm} — ★관심 wholly inside the header, nothing over it; no label covered except by the row\'s own edge',
                      wr['l'] >= x['inner']['l'] - .5 and wr['r'] <= x['inner']['r'] + .5 and wr['r'] <= x['vw'] and x['wHit'] and wr['l'] >= x['sc']['r'] and not x['covered'],
                      (wr, x['inner'], x['sc']['r'], x['wHit'], x['covered'][:6]))
            if phone:
                check(f'tabs {tag}: the row scrolls; its own mask fades the right edge only while tabs are hidden to the right',
                      s['max'] > 0 and s['more'] and 'gradient' in s['mask'] and not e['more'] and e['mask'] == 'none', (s['max'], s['more'], s['mask'][:60], e['more'], e['mask'][:30]))
            else:
                check(f'tabs {tag}: the row does not scroll, no fade', s['max'] <= 0 and not s['more'] and not e['more'], (s['max'], s['more']))
            pg.evaluate("document.querySelector('.tabs-sc').scrollLeft = 0"); pg.wait_for_timeout(100)
            # every tab, selected: in view (clear of the fade), the pill + underline on it, ★관심 with its own
            bad = []
            for m in ('K', 'Q', 'ALL', 'THEME', 'WORLD', 'CMDTY', 'CAL', 'WATCH', 'K'):
                pg.evaluate(f"document.querySelector('.tabs button[data-mkt=\"{m}\"]').click()"); pg.wait_for_timeout(600)
                x = pg.evaluate(TABS)
                br_ = x['btn'][m]
                lim = x['sc']['r'] - (20 if x['more'] else 0) if m != 'WATCH' else x['inner']['r']
                low = x['sc']['l'] if m != 'WATCH' else x['inner']['l']
                pill = x['own'] if m == 'WATCH' else x['ind']
                off = max(abs(pill['l'] - (br_['l'] + x['inX'])), abs(pill['r'] - (br_['r'] - x['inX'])), abs(pill['t'] - (br_['t'] + x['inY'])), abs(pill['b'] - (br_['b'] - x['inY'])))
                ok = (x['sel'] == m and x['selHit'] and br_['l'] >= low - .5 and br_['r'] <= lim + .5 and pill['op'] == 1 and off <= 1
                      and (x['pin'] == 'on') == (m == 'WATCH') and (m != 'WATCH' or x['ind']['op'] == 0) and not x['covered'])
                if not ok:
                    bad.append((m, x['sel'], x['selHit'], round(br_['l']), round(br_['r']), round(lim), x['pin'], round(off, 2), pill['op'], x['covered'][:3]))
            check(f'tabs {tag}: each tab when selected is in view (clear of the fade), its pill on it (±1px); ★관심 with its own', not bad, bad)
            # ★관심 selected: the row scrolls both ways, its pill stays; leaving it, the shared pill sets out from ★관심
            pg.evaluate("document.querySelector('.tabs button[data-mkt=\"WATCH\"]').click()"); pg.wait_for_timeout(600)
            ok = []
            for sl in ('1e5', '0'):
                pg.evaluate(f"document.querySelector('.tabs-sc').scrollLeft = {sl}"); pg.wait_for_timeout(120)
                x = pg.evaluate(TABS); wr = x['btn']['WATCH']
                ok.append(x['pin'] == 'on' and x['own']['op'] == 1 and x['ind']['op'] == 0 and abs(x['own']['l'] - wr['l']) <= 1 and x['wHit'])
            check(f'tabs {tag}: ★관심 selected — its own pill on it at either scroll end', all(ok), ok)
            st = pg.evaluate("""async () => { const t = document.querySelector('.tabs'), sc = t.querySelector('.tabs-sc'), w = t.querySelector('.tpin'), wr = w.getBoundingClientRect();
              t.querySelector('button[data-mkt="K"]').click(); await null; await null;
              const p = getComputedStyle(sc, '::before'), q = sc.getBoundingClientRect();
              return { wl: wr.left, wr: wr.right, l: q.left + sc.clientLeft + parseFloat(p.left) - sc.scrollLeft, r: q.left + sc.clientLeft + sc.clientWidth - parseFloat(p.right) - sc.scrollLeft, pin: t.dataset.pin || null, op: +p.opacity }; }""")
            check(f'tabs {tag}: leaving ★관심 the shared pill starts on it (not from a stale place)', abs(st['l'] - st['wl']) <= 2 and abs(st['r'] - st['wr']) <= 2 and not st['pin'] and st['op'] == 1, st)
            if phone:
                pg.wait_for_timeout(500)
                pg.evaluate("document.querySelector('.tabs-sc').scrollLeft = 0"); pg.wait_for_timeout(120)
                pg.screenshot(path=str(SHOTS / f'tabs_{w}_{theme}.png'), clip={'x': 0, 'y': 40, 'width': w, 'height': 80})
            ctx.close()


OVERFLOW_ELS = r"""() => {
  // anything drawn past the screen's sides that no clipping / scrolling box of its own holds in (html · body clip on x now, so
  // documentElement.scrollWidth can no longer show it)
  const vw = document.documentElement.clientWidth, out = [];
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || (r.right <= vw + 1 && r.left >= -1)) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || +s.opacity === 0) continue;
    let p = el.parentElement, held = false;
    while (p && p !== document.body) { const q = getComputedStyle(p); if (q.overflowX !== 'visible' || q.clipPath !== 'none' || +q.opacity === 0 || q.visibility === 'hidden') { held = true; break; } p = p.parentElement; }
    if (held) continue;
    out.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '')) + ` [${Math.round(r.left)}, ${Math.round(r.right)}]`);
  }
  return out.slice(0, 8);
}"""


def overflow_net(br):
    """the page never pans sideways (사용자 2026-11-15 21:34 "이렇게 튀어나가는거 없게해줘"): html · body clip on x without becoming
    scroll boxes; the sticky header, the dock, a fixed sheet and the tab row's own scroller still work; no element wider than the screen"""
    ctx, pg = open_page(br, 390, 844)
    r = pg.evaluate("""async () => {
      const cs = e => { const s = getComputedStyle(e); return [s.overflowX, s.overflowY]; };
      const out = { html: cs(document.documentElement), body: cs(document.body), se: document.scrollingElement === document.documentElement, vw0: innerWidth };
      const wide = Object.assign(document.createElement('div'), { id: 'qa-wide' }); wide.style.cssText = 'width:900px;height:20px;background:#f0f';
      document.querySelector('main.layout').append(wide);
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      out.sw = document.documentElement.scrollWidth; out.vw = innerWidth;
      scrollTo(300, 0); await new Promise(r => setTimeout(r, 50)); out.sx = scrollX;
      const t = document.querySelector('.tabs-sc'); t.scrollLeft = 40; await new Promise(r => setTimeout(r, 50)); out.tabsScroll = t.scrollLeft; t.scrollLeft = 0;
      scrollTo(0, 900); await new Promise(r => setTimeout(r, 400)); out.sy = scrollY;
      const hd = document.querySelector('header.top').getBoundingClientRect(), tb = t.getBoundingClientRect();
      out.headerStuck = tb.top >= -1 && tb.bottom <= 80 && hd.bottom > 0;
      const dk = document.querySelector('.dock'); out.dock = !dk || dk.hidden || getComputedStyle(dk).display === 'none' ? 'none' : (() => { const d = dk.getBoundingClientRect(); return d.bottom <= innerHeight + .5 && d.left >= 0 && d.right <= innerWidth + .5; })();
      wide.remove(); scrollTo(0, 0);
      return out; }""")
    check('overflow net: html · body clip on x and stay non-scrolling on y (no new scroll box; the page scrolls as before)',
          r['html'][0] == 'clip' and r['body'] == ['clip', 'visible'] and r['se'] and r['sy'] > 100, r)
    check('overflow net: a 900px element no longer widens the page (a phone would zoom the layout out to it) or lets it pan sideways', r['vw'] == r['vw0'] and r['sw'] <= r['vw0'] and r['sx'] == 0, r)
    check('overflow net: the tab row still scrolls itself; the header stays stuck; the dock stays on screen', r['tabsScroll'] > 0 and r['headerStuck'] and r['dock'] in (True, 'none'), r)
    a = sample(pg, '#ctls', "document.getElementById('setBtn').click()", [900])
    check('overflow net: the 표시 설정 sheet still opens in place (fixed)', a[0]['d'] != 'none' and abs(a[0]['y']) < 1, a)
    ctx.close()
    found = {}
    for w, h in ((360, 740), (390, 844), (768, 1024), (1280, 800)):
        for m in ('K', 'THEME', 'WORLD', 'CMDTY', 'CAL', 'WATCH'):
            ctx, pg = open_page(br, w, h, market=m)
            pg.wait_for_timeout(500 if m in ('CAL', 'WORLD', 'CMDTY') else 0)
            o = pg.evaluate(OVERFLOW_ELS)
            if o:
                found[f'{w}/{m}'] = o
            ctx.close()
    check('no element drawn past the screen sides (360 · 390 · 768 · 1280 × 코스피 · 테마 · 해외 · 지표 · 일정 · 관심)', not found, found)
    # 일정 with real rows (qa/calendar/mock_cal.py: a released value on a past day, long titles): every day of the week strip
    cport = PORT + 1
    assert 8970 <= cport <= 8979 or 9010 <= cport <= 9029
    subprocess.run(['fuser', '-k', f'{cport}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(ROOT / 'qa/calendar/mock_cal.py'), str(cport)], env=dict(os.environ, MOCK_WEB=os.environ.get('FLOAT_WEB', str(ROOT / 'web'))),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                NOPROXY.open(f'http://127.0.0.1:{cport}/__reset', timeout=1).read(); break
            except Exception:
                time.sleep(0.1)
        found, days = {}, 0
        for w in (360, 390):
            ctx = br.new_context(viewport={'width': w, 'height': 800}, is_mobile=True, has_touch=True, device_scale_factor=2)
            pg = ctx.new_page()
            pg.on('pageerror', lambda e: ERRS.append(f'cal {w} pageerror: {e}'))
            pg.goto(f'http://127.0.0.1:{cport}/#cal'); pg.wait_for_selector('#calendar .kc-ev', timeout=10000)
            n = pg.locator('#calendar .kc-wk button').count()
            for i in range(n):
                pg.locator('#calendar .kc-wk button').nth(i).click(); pg.wait_for_timeout(350)
                o = pg.evaluate(OVERFLOW_ELS); days += 1
                if o:
                    found[f'{w}/day{i}'] = o
            ctx.close()
        check(f'일정 with rows: no element past the screen sides on any of {days} days (360 · 390)', days >= 10 and not found, found)
    finally:
        srv.kill()
        subprocess.run(['fuser', '-k', f'{cport}/tcp'], capture_output=True)


def reduced(br):
    ctx, pg = open_page(br, 390, 844, motion='reduced')
    a = sample(pg, '#ctls', "document.getElementById('setBtn').click()", [30])
    check('줄이기: 표시 설정 is in place at once', abs(a[0]['y']) < 1, a)
    c = sample(pg, '#ctls', "document.getElementById('ctlsX').click()", [30])
    check('줄이기: and gone at once', c[0]['d'] == 'none', c)
    ctx.close()
    ctx, pg = open_page(br, 1440, 900, motion='reduced')
    a = sample(pg, '#morePanel', "document.getElementById('moreBtn').click()", [30])
    check('줄이기: 화면 popover whole at once', 'inset(-64px' in (a[0]['cp'] or '') and a[0]['o'] == 1, a)
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
            shapes(br)
            tabgroups(br)
            overflow_net(br)
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check('console errors 0', not ERRS, ERRS[:5])
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
