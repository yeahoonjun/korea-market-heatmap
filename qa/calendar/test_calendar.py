#!/usr/bin/env python3
"""QA for the 일정 tab (src/calendar, AGENTS §3-33, docs/standards/calendar.md) on the built pages.

  python3 scripts/build_page.py && python3 qa/calendar/test_calendar.py [--shots]

Starts qa/calendar/mock_cal.py on CAL_QA_PORT (default 8995; web/ + /api/calendar built around KST today) and stops it at the end.
--shots also writes qa/shots/calendar/{390,1440}*.png (gitignored). Exit 1 if any check fails.
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
PORT = int(os.environ.get('CAL_QA_PORT', 8995))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SHOTS = '--shots' in sys.argv
SHOT_DIR = ROOT / 'qa/shots/calendar'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' else ''), flush=True)


def mock(path):
    with NOPROXY.open(LIVE.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


def mode(m):
    mock('/__reset')
    mock('/__mode?cal=' + m)


def open_page(br, url, w, h, errors, theme='base', motion='standard', watch=None, cal=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    init = "try{localStorage.setItem('khm.theme', %s);localStorage.setItem('khm.motion', %s);localStorage.setItem('khm.tickerPaused','true');" % (
        json.dumps(json.dumps(theme)), json.dumps(json.dumps(motion)))
    if watch:
        init += "localStorage.setItem('khm.watchGroups', %s);" % json.dumps(json.dumps({'v': 1, 'groups': [{'id': 'g1', 'name': '관심', 'codes': watch}], 'active': 'all'}))
    if cal is not None:
        init += "localStorage.setItem('khm.cal', %s);" % json.dumps(json.dumps(cal))
    ctx.add_init_script(init + "}catch(e){}")
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append(m.text[:160]) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    pg.goto(url)
    return ctx, pg


def ready(pg, sel='#calendar .kc-ev, #calendar .kc-msg, #calendar .kc-empty', timeout=8000):
    pg.wait_for_selector(sel, timeout=timeout)
    pg.wait_for_timeout(400)


ROWS_JS = "() => [...document.querySelectorAll('#calendar .kc-ev')].map(r => r.textContent)"

# every text element ≥ 11 px; phone touch targets ≥ 44 px (counting the ::before hit area); no up/down colours anywhere in the tab
AUDIT_JS = r"""(phone) => {
  const box = document.getElementById('calendar'), out = { small: [], touch: [], updn: [], over: 0 };
  const probe = document.createElement('i'); document.body.append(probe);
  const root = getComputedStyle(document.documentElement);
  const col = n => { if (!root.getPropertyValue(n).trim()) return null; probe.style.color = `var(${n})`; return getComputedStyle(probe).color; };   // only defined tokens
  const bad = new Set(['--up-text', '--dn-text', '--up', '--dn'].map(col).filter(c => c && c !== 'rgba(0, 0, 0, 0)'));
  probe.remove();
  for (const el of box.querySelectorAll('*')) {
    if (!el.offsetWidth && !el.offsetHeight) continue;
    const cs = getComputedStyle(el);
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (own && parseFloat(cs.fontSize) < 11) out.small.push(el.className + ':' + cs.fontSize);
    for (const p of ['color', 'backgroundColor', 'borderTopColor', 'borderLeftColor']) if (bad.has(cs[p]) && (p === 'color' ? own || el.tagName === 'svg' : true) && !(p.startsWith('border') && parseFloat(cs[p.replace('Color', 'Width')]) === 0)) out.updn.push(el.className + ' ' + p);
    if (phone && el.matches('button, a[href]')) {
      const r = el.getBoundingClientRect(), b = getComputedStyle(el, '::before');
      let w = r.width, hh = r.height;
      if (b.content && b.content !== 'none' && b.position === 'absolute') {
        w += Math.max(0, -parseFloat(b.left) || 0) + Math.max(0, -parseFloat(b.right) || 0);
        hh += Math.max(0, -parseFloat(b.top) || 0) + Math.max(0, -parseFloat(b.bottom) || 0);
      }
      if (w < 44 || hh < 44) out.touch.push((el.className || el.tagName) + ' ' + Math.round(w) + 'x' + Math.round(hh));
    }
  }
  out.over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return out;
}"""


def phone(br, w, h):
    E = []
    ctx, pg = open_page(br, LIVE + '#cal', w, h, E, watch=['005930'])
    ready(pg)
    st = pg.evaluate("""() => ({ pressed: (document.querySelector('.tabs button[aria-pressed="true"]') || {}).dataset?.mkt,
      cal: !document.getElementById('calendar').hidden, map: !document.querySelector('main.layout').hidden,
      days: document.querySelectorAll('.kc-wk button').length, on: document.querySelectorAll('.kc-wk button[aria-pressed="true"]').length,
      secs: document.querySelectorAll('.kc-phone .kc-list .kc-day').length, foot: !!document.getElementById('foot-cal') && document.getElementById('foot-cal').textContent.includes('FRED®'),
      hash: location.hash })""")
    check(f'{w}: 일정 tab pressed, map hidden, #cal', st['pressed'] == 'CAL' and st['cal'] and not st['map'] and st['hash'] == '#cal', st)
    check(f'{w}: week strip 7 days, one chosen; list = 7 days from the chosen day', st['days'] == 7 and st['on'] == 1 and st['secs'] == 7, st)
    check(f'{w}: footer source line (FRED® notice)', st['foot'])
    a = pg.evaluate(AUDIT_JS, w <= 760)              # phone sizes (--h-* tokens) apply below 761 px (design.md)
    check(f'{w}: no horizontal overflow', a['over'] == 0, a['over'])
    check(f'{w}: text ≥ 11 px', not a['small'], a['small'][:4])
    if w <= 760:
        check(f'{w}: touch targets ≥ 44 px', not a['touch'], a['touch'][:4])
    check(f'{w}: no up/down colours', not a['updn'], a['updn'][:4])
    if w != 390:
        check(f'{w}: console errors 0', not E, E[:3])
        ctx.close()
        return
    rows = pg.evaluate(ROWS_JS)
    check('390: weekly expiries hidden by default', not any('위클리' in r for r in rows))
    check('390: 관심 badge on the watched stock', pg.locator('.kc-ev:has-text("삼성전자") .kc-watch').count() == 1)
    pg.get_by_role('button', name='위클리 만기').click(); pg.wait_for_timeout(250)
    check('390: 위클리 만기 chip shows weekly rows', any('위클리' in r for r in pg.evaluate(ROWS_JS)))
    check('390: chip state saved', json.loads(pg.evaluate("localStorage.getItem('khm.cal')") or '{}').get('weekly') is True)
    pg.get_by_role('button', name='위클리 만기').click(); pg.wait_for_timeout(250)
    pg.get_by_role('button', name='기업', exact=True).click(); pg.wait_for_timeout(250)
    rows = pg.evaluate(ROWS_JS)
    check('390: 기업 off removes company rows', rows and not any(x in r for r in rows for x in ('삼성전자', 'SK하이닉스', '배당 기준일')), len(rows))
    pg.get_by_role('button', name='기업', exact=True).click(); pg.wait_for_timeout(250)
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(250)
    s1 = pg.evaluate("() => [...document.querySelectorAll('#calendar .kc-ev .kc-stars')].filter(s => s.classList.contains('s1')).length")
    n = pg.locator('#calendar .kc-ev').count()
    check('390: ★★ 이상만 hides ★ rows', n > 0 and s1 == 0, f'{n} rows, {s1} ★')
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(250)
    # detail sheet
    row = pg.locator('.kc-ev:has-text("SK하이닉스")').first
    rid = row.get_attribute('data-id')
    row.click(); pg.wait_for_timeout(450)
    d = pg.evaluate("() => { const g = document.querySelector('dialog.kc-dlg'); return g && { open: g.open, t: g.textContent, focus: document.activeElement.className } }")
    check('390: detail sheet opens (보호예수 %, why, focus on 닫기)', d and d['open'] and '18.4%' in d['t'] and '별 기준' in d['t'] and d['focus'] == 'kc-x', d and d['focus'])
    pg.keyboard.press('Escape'); pg.wait_for_timeout(450)
    d = pg.evaluate("() => ({ open: document.querySelector('dialog.kc-dlg').open, back: document.activeElement.dataset.id })")
    check('390: Esc closes and focus returns to the row', not d['open'] and d['back'] == rid, d)
    pg.locator('.kc-ev:has-text("배당 기준일")').first.click(); pg.wait_for_timeout(450)
    codes = pg.locator('dialog.kc-dlg .kc-codes button').count()
    check('390: group row lists its 15 stocks', codes == 15, codes)
    if SHOTS:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(SHOT_DIR / '390_sheet.png'))
    pg.locator('dialog.kc-dlg .kc-x').click(); pg.wait_for_timeout(450)
    # week navigation · keyboard
    head = lambda: pg.locator('.kc-hd h2').text_content()
    h0 = head()
    pg.locator('.kc-hd .kc-ik').nth(1).click(); pg.wait_for_timeout(300)
    h1 = head()
    pg.get_by_role('button', name='오늘', exact=True).click(); pg.wait_for_timeout(300)
    check('390: next week / 오늘', h1 != h0 and head() == h0, f'{h0} → {h1}')
    pg.locator('.kc-wk button[aria-pressed="true"]').focus()
    before = pg.locator('.kc-wk button[aria-pressed="true"]').get_attribute('data-d')
    pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(300)
    after = pg.evaluate("() => document.activeElement.dataset.d")
    check('390: ←/→ move the chosen day', after and after != before, f'{before} → {after}')
    if SHOTS:
        pg.get_by_role('button', name='오늘', exact=True).click(); pg.wait_for_timeout(400)
        pg.screenshot(path=str(SHOT_DIR / '390.png'))
    # back to 코스피: the map returns, the calendar footer line goes
    pg.locator('.tabs button[data-mkt="K"]').click(); pg.wait_for_timeout(600)
    b = pg.evaluate("() => ({ cal: !document.getElementById('calendar').hidden, map: !document.querySelector('main.layout').hidden, foot: !!document.getElementById('foot-cal'), on: KHCal.isOn() })")
    check('390: back to 코스피 restores the map', not b['cal'] and b['map'] and not b['foot'] and not b['on'], b)
    check('390: console errors 0', not E, E[:3])
    ctx.close()


def desktop(br):
    E = []
    ctx, pg = open_page(br, LIVE + '#cal', 1440, 900, E)
    ready(pg)
    g = pg.evaluate("() => ({ cells: document.querySelectorAll('.kc-mg .cell').length, side: document.querySelectorAll('.kc-side .kc-day').length, strip: document.querySelectorAll('.kc-wk').length })")
    check('1440: month grid 6 weeks + 7-day side list, no week strip', g['cells'] == 42 and g['side'] == 7 and g['strip'] == 0, g)
    a = pg.evaluate(AUDIT_JS, False)
    check('1440: no horizontal overflow', a['over'] == 0, a['over'])
    check('1440: text ≥ 11 px', not a['small'], a['small'][:4])
    check('1440: no up/down colours', not a['updn'], a['updn'][:4])
    if SHOTS:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(SHOT_DIR / '1440.png'))
    cell = pg.locator('.kc-mg .cell:not(.out)').nth(20)
    d = cell.get_attribute('data-d')
    cell.click(); pg.wait_for_timeout(300)
    s = pg.evaluate("() => ({ on: (document.querySelector('.kc-mg .cell[aria-pressed=\"true\"]') || {}).dataset?.d, first: (document.querySelector('.kc-side .kc-day') || {}).getAttribute?.('aria-label') })")
    check('1440: a day cell picks the side list', s['on'] == d and s['first'] and s['first'].startswith(f'{int(d[5:7])}월 {int(d[8:])}일'), s)
    h0 = pg.locator('.kc-bar h2').text_content()
    pg.locator('.kc-bar .kc-ik').nth(1).click(); pg.wait_for_timeout(400)
    h1 = pg.locator('.kc-bar h2').text_content()
    check('1440: month arrows', h1 != h0, f'{h0} → {h1}')
    pg.get_by_role('button', name='오늘', exact=True).click(); pg.wait_for_timeout(400)
    pg.locator('.kc-side .kc-ev').first.click(); pg.wait_for_timeout(450)
    r = pg.evaluate("() => { const g = document.querySelector('dialog.kc-dlg'), b = g.getBoundingClientRect(); return { open: g.open, w: b.width, bottom: innerHeight - b.bottom } }")
    check('1440: detail opens as a floating panel', r['open'] and r['w'] < 700 and r['bottom'] > 40, r)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    check('1440: console errors 0', not E, E[:3])
    ctx.close()


def states(br):
    for m, sel, want in (('fail', '.kc-msg', '불러오지 못했어요'), ('none', '.kc-msg', '아직 준비하고 있어요'), ('empty', '.kc-empty', '없어요'), ('stale', '.kc-note .bang', None)):
        E = []
        mode(m)
        ctx, pg = open_page(br, LIVE + '#cal', 390, 844, E)
        ready(pg, '#calendar ' + sel)
        txt = pg.locator('#calendar ' + sel).first.text_content() if want else 'ok'
        E2 = [e for e in E if '502' not in e and '404' not in e]      # the failed fetch itself logs a resource error
        check(f'state {m}: {want or "! note"}', (want is None or want in txt) and not E2, (txt[:30], E2[:2]))
        if m == 'fail':
            mode('ok')
            pg.get_by_role('button', name='다시 시도').click()
            ok = True
            try:
                pg.wait_for_selector('#calendar .kc-ev', timeout=6000)
            except Exception:
                ok = False
            check('state fail → 다시 시도 recovers', ok)
        ctx.close()
    mode('slow')
    E = []
    ctx, pg = open_page(br, LIVE + '#cal', 390, 844, E)
    pg.wait_for_selector('#calendar [aria-busy="true"]', timeout=4000)
    check('state slow: loading line first', True)
    ready(pg, '#calendar .kc-ev')
    check('state slow: rows after', pg.locator('#calendar .kc-ev').count() > 0)
    ctx.close()
    mode('ok')
    # saved chips with weekly on come back on reload; light theme + reduced motion draw cleanly
    E = []
    ctx, pg = open_page(br, LIVE + '#cal', 390, 844, E, theme='paper', motion='reduced', cal={'kinds': ['mkt'], 'hi': False, 'weekly': True})
    ready(pg)
    rows = pg.evaluate(ROWS_JS)
    check('saved filter: only 시장, weekly shown (paper · reduced)', rows and all(('만기' in r) for r in rows) and any('위클리' in r for r in rows), rows[:3])
    check('paper · reduced: console errors 0', not E, E[:3])
    ctx.close()


def snapshot(br):
    E = []
    ctx, pg = open_page(br, SNAP + '#cal', 390, 844, E)
    calls = []
    pg.on('request', lambda r: calls.append(r.url) if 'api/calendar' in r.url else None)
    pg.wait_for_selector('#calendar .kc-msg', timeout=8000)
    t = pg.locator('#calendar .kc-msg').text_content()
    href = pg.locator('#calendar .kc-msg a').get_attribute('href')
    check('snapshot: 실시간 버전 안내 + link, no /api/calendar', '실시간 버전에서 볼 수 있어요' in t and href.endswith('#cal') and not calls, (t[:30], href, calls[:1]))
    ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_cal.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            mode('ok')
            phone(br, 390, 844)
            phone(br, 360, 740)
            phone(br, 768, 1024)
            desktop(br)
            states(br)
            snapshot(br)
            br.close()
    finally:
        srv.terminate()
        srv.wait(5)
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed')
    for n in bad:
        print('  FAIL', n)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
