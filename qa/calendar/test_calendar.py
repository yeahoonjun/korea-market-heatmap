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


# each day: a 미국 group, then a 한국 group (user 2026-11-15), labels, and time order inside a group (all-day first)
GROUPS_JS = r"""(sel) => [...document.querySelectorAll(sel + ' .kc-day')].map(sec => ({
  d: sec.dataset.day,
  groups: [...sec.querySelectorAll(':scope > .kc-grp')].map(g => ({ rg: g.dataset.rg, label: (g.querySelector(':scope > .kc-rg') || {}).textContent || '',
    times: [...g.querySelectorAll(':scope > .kc-ev .tm')].map(t => t.classList.contains('all') ? '00:00' : t.childNodes[0].textContent.trim()) })) }))"""


def check_groups(tag, days):
    order_ok = all([g['rg'] for g in d['groups']] in (['us', 'kr'], ['us'], ['kr'], []) for d in days)
    label_ok = all(g['label'] == {'us': '미국', 'kr': '한국'}[g['rg']] for d in days for g in d['groups'])
    time_ok = all(g['times'] == sorted(g['times']) for d in days for g in d['groups'])
    both = [d for d in days if [g['rg'] for g in d['groups']] == ['us', 'kr']]
    later_first = any(d['groups'][0]['times'] and d['groups'][1]['times'] and max(d['groups'][0]['times']) > min(d['groups'][1]['times']) for d in both)
    check(f'{tag}: each day 미국 group first, then 한국 (labels · time order inside)', order_ok and label_ok and time_ok and both, (order_ok, label_ok, time_ok, len(both)))
    check(f'{tag}: a 22:30 미국 row still comes before an earlier 한국 row', later_first)


NULL_JS = "() => { const t = (document.querySelector('dialog.kc-dlg') || {}).textContent || ''; return /\\bnull\\b|undefined|NaN/.test(t) ? t.slice(0, 160) : '' }"


def details(pg):
    """390: company details hidden by default + the two ways in (a day's own toggle · the 기업 세부 일정 chip)."""
    td = pg.evaluate("() => document.querySelector('.kc-phone .kc-day').dataset.day")
    chips = pg.evaluate("() => [...document.querySelectorAll('.kc-chip')].map(b => b.dataset.chip)")
    check('390: chips 미국 지표 → 한국 지표 → 금리 → 시장 → 기업 | ★★ · 위클리 · 기업 세부 일정', chips == ['us', 'kr', 'cb', 'mkt', 'corp', 'hi', 'weekly', 'detail'], chips)
    day_rows = lambda d: pg.evaluate("(d) => [...document.querySelectorAll(`.kc-day[data-day='${d}'] .kc-ev`)].map(r => r.textContent)", d)
    rows = day_rows(td)
    hidden = not any(x in r for r in rows for x in ('가나상사', '다라리츠', '마바산업', '사아테크'))
    check('390: 주식권리일정 details and a 주총 off the map are hidden by default', hidden and rows, rows[:6])
    check('390: 주총 of a stock on the map is shown', any('SK하이닉스' in r and '총회개최일' in r for r in rows))
    tg = pg.locator(f'.kc-dmore[data-more="{td}"]')
    t0 = tg.text_content() if tg.count() else ''
    check('390: the day offers "기업 세부 일정 4개 더 보기" (collapsed, in the 한국 group)', tg.count() == 1 and '4개' in t0 and tg.get_attribute('aria-expanded') == 'false'
          and pg.evaluate(f"() => document.querySelector('.kc-dmore[data-more=\"{td}\"]').closest('.kc-grp').dataset.rg") == 'kr', t0)
    tg.focus(); pg.keyboard.press('Enter'); pg.wait_for_timeout(350)
    st = pg.evaluate(f"""() => {{ const b = document.querySelector('.kc-dmore[data-more="{td}"]'), det = document.getElementById('kc-det-{td}');
      return {{ exp: b.getAttribute('aria-expanded'), n: det ? det.querySelectorAll('.kc-ev').length : 0, focus: document.activeElement === b, text: b.textContent }} }}""")
    check('390: Enter on the toggle opens that day\'s 4 details, focus stays', st['exp'] == 'true' and st['n'] == 4 and st['focus'] and '접기' in st['text'], st)
    pg.locator(f'#kc-det-{td} .kc-ev:has-text("가나상사")').click(); pg.wait_for_timeout(450)
    w = pg.evaluate("() => document.querySelector('dialog.kc-dlg').textContent")
    check('390: a detail row opens with "세부 일정" + why', '세부 일정' in w and '기업 세부 일정' in w and not pg.evaluate(NULL_JS), w[:80])
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    tg.click(); pg.wait_for_timeout(250)
    check('390: the toggle closes them again', pg.locator(f'#kc-det-{td}').count() == 0 and tg.get_attribute('aria-expanded') == 'false')
    # the chip: every day at once, saved
    pg.evaluate("() => { window.__chip = document.querySelector('.kc-chip[data-chip=\"detail\"]') }")
    pg.get_by_role('button', name='기업 세부 일정', exact=True).click(); pg.wait_for_timeout(300)
    st = pg.evaluate(f"""() => ({{ same: document.querySelector('.kc-chip[data-chip="detail"]') === window.__chip, toggles: document.querySelectorAll('.kc-dmore').length,
      sub: (document.querySelector('.kc-day[data-day="{td}"] .kc-subh') || {{}}).textContent || '', saved: JSON.parse(localStorage.getItem('khm.cal') || '{{}}').detail }})""")
    rows = day_rows(td)
    check('390: 기업 세부 일정 chip shows all details (heading, no toggles), saved, chip kept in place', st['same'] and st['toggles'] == 0 and '4개' in st['sub'] and st['saved'] is True
          and any('가나상사' in r for r in rows), st)
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(250)
    check('390: ★★ 이상만 still hides details (they are ★)', not any('가나상사' in r for r in day_rows(td)))
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(200)
    pg.get_by_role('button', name='기업 세부 일정', exact=True).click(); pg.wait_for_timeout(250)
    check('390: chip off → hidden again', not any('가나상사' in r for r in day_rows(td)) and pg.locator('.kc-dmore').count() >= 1)
    # a day with nothing important: the line says how many are hidden and by which chips, and offers them for that day
    sat = pg.evaluate("() => { const p = document.querySelector('.kc-phone .kc-hid'); return p && { d: p.closest('.kc-day').dataset.day, t: p.textContent } }")
    check('390: empty day says "숨긴 일정 1개 (기업 세부 일정)" + a key for that day', bool(sat) and sat['t'] == '숨긴 일정 1개 (기업 세부 일정)'
          and pg.locator(f'.kc-day[data-day="{sat["d"]}"] [data-reveal]').count() == 1, sat)
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(250)
    t2 = pg.evaluate(f"() => (document.querySelector('.kc-day[data-day=\"{sat['d']}\"] .kc-hid') || {{}}).textContent")
    check('390: the line names every chip that hides them (★★ 이상만 · 기업 세부 일정)', t2 == '숨긴 일정 1개 (★★ 이상만 · 기업 세부 일정)', t2)
    rv = pg.locator(f'.kc-day[data-day="{sat["d"]}"] [data-reveal]')
    rv.focus(); pg.keyboard.press('Enter'); pg.wait_for_timeout(350)
    st = pg.evaluate(f"""() => {{ const sec = document.querySelector('.kc-day[data-day="{sat['d']}"]'), b = sec.querySelector('[data-reveal]');
      return {{ rows: [...sec.querySelectorAll('.kc-ev')].map(r => r.textContent), exp: b && b.getAttribute('aria-expanded'), text: b && b.textContent, focus: document.activeElement === b,
        chips: JSON.parse(localStorage.getItem('khm.cal') || '{{}}') }} }}""")
    check('390: "이 날 숨긴 일정 보기" shows that day\'s rows (chips untouched), focus kept', any('자차홀딩스' in r for r in st['rows']) and st['exp'] == 'true' and '다시 숨기기' in st['text']
          and st['focus'] and st['chips'].get('hi') is True and not st['chips'].get('detail'), st)
    pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
    check('390: "이 날 다시 숨기기" folds it back', pg.locator(f'.kc-day[data-day="{sat["d"]}"] .kc-hid').count() == 1 and pg.evaluate("() => document.activeElement.dataset.reveal") == sat['d'])
    pg.get_by_role('button', name='★★ 이상만').click(); pg.wait_for_timeout(250)


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
    check_groups('390', pg.evaluate(GROUPS_JS, '.kc-phone'))
    details(pg)
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
    row = pg.locator('.kc-ev:has-text("보호예수 해제 2,150만")').first
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
    bad = [pg.evaluate(NULL_JS)]
    for sel in ('.kc-ev:has-text("FOMC")', '.kc-ev:has-text("삼성전자")', '.kc-ev:has-text("보호예수")'):
        pg.keyboard.press('Escape'); pg.wait_for_timeout(350)
        if pg.locator(sel).count():
            pg.locator(sel).first.click(); pg.wait_for_timeout(400); bad.append(pg.evaluate(NULL_JS))
    check('390: no "null" / "undefined" text in the detail dialog (group · FOMC · DART · 보호예수)', not any(bad), [b for b in bad if b][:2])
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
    nx = pg.locator('[data-next]')
    nx.scroll_into_view_if_needed(); nx.click(); pg.wait_for_timeout(400)
    st = pg.evaluate("() => ({ focus: !!document.activeElement.dataset.next, top: document.querySelector('.kc-hd').getBoundingClientRect().top, head: document.querySelector('.kc-hd h2').textContent })")
    check('390: 다음 7일 보기 → next week, the week back in view, focus kept on the key', st['focus'] and st['top'] >= 0 and st['head'] != h0, st)
    pg.get_by_role('button', name='오늘', exact=True).click(); pg.wait_for_timeout(300)
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
    check_groups('1440 side', pg.evaluate(GROUPS_JS, '.kc-side'))
    lines = pg.evaluate("() => [...document.querySelectorAll('.kc-mg .cell')].map(c => [...c.querySelectorAll('.line')].map(l => l.dataset.rg))")
    check('1440: month cells list 미국 lines first', all(x == sorted(x, key=lambda r: r != 'us') for x in lines) and any('us' in x and 'kr' in x for x in lines), [x for x in lines if x][:4])
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


CHIP_JS = r"""async () => {
  const chip = document.querySelector('.kc-chip[data-chip="weekly"]'), nb = document.querySelector('.kc-chip[data-chip="detail"]'), ck = chip.querySelector('.kck');
  const w0 = chip.getBoundingClientRect().width, x0 = nb.getBoundingClientRect().left;
  chip.click();
  const same = document.querySelector('.kc-chip[data-chip="weekly"]') === chip;
  const anims = chip.getAnimations({ subtree: true }).map(a => a.transitionProperty || a.animationName);
  const op = +getComputedStyle(ck).opacity;
  await new Promise(r => setTimeout(r, 800));
  const out = { same, anims, op, op1: +getComputedStyle(ck).opacity, dw: Math.abs(chip.getBoundingClientRect().width - w0), dx: Math.abs(nb.getBoundingClientRect().left - x0), on: chip.getAttribute('aria-pressed') };
  chip.click(); await new Promise(r => setTimeout(r, 500));
  return out;
}"""
IND_JS = r"""async () => {
  const wk = document.querySelector('.kc-wk'), ind = wk.querySelector('.kc-ind');
  const to = [...wk.querySelectorAll('button')].find(b => b.getAttribute('aria-pressed') !== 'true');
  to.click();
  const want = `translateX(${to.offsetLeft}px)`, now = ind.style.transform;
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const mid = ind.style.transform;
  await new Promise(r => setTimeout(r, 900));
  return { want, now, mid, end: ind.style.transform, w: Math.abs(parseFloat(ind.style.width) - to.offsetWidth) };
}"""
DLG_JS = r"""async () => {
  const sl = ms => new Promise(r => setTimeout(r, ms)), rows = document.querySelectorAll('#calendar .kc-ev');
  rows[0].click(); await sl(60);
  const g = document.querySelector('dialog.kc-dlg'), an = () => g.getAnimations({ subtree: true }).map(a => (a.effect.pseudoElement || '') + a.transitionProperty);
  const opening = an();
  await sl(600);
  g.querySelector('.kc-x').click(); await sl(40);
  const exit = { open: g.open, drawn: getComputedStyle(g).display !== 'none', anims: an(), focus: !!document.activeElement.closest('#calendar') };
  rows[1].click(); await sl(40);
  const back = { open: g.open, on: g.classList.contains('on'), title: g.querySelector('h3').textContent };
  await sl(600);
  const settled = getComputedStyle(g).transform;
  g.querySelector('.kc-x').click(); await sl(600);
  return { opening, exit, back, settled, closed: !g.open && getComputedStyle(g).display === 'none' };
}"""
DRAG = 'dialog.kc-dlg .kc-sh h3'


def motion(br):
    """design.md §6 · §7 chips, the week strip marker, the detail sheet: moving in 화려하게 (default), instant in 줄이기."""
    for mo in ('fancy', 'reduced'):
        E = []
        ctx, pg = open_page(br, LIVE + '#cal', 390, 844, E, motion=mo)
        ready(pg)
        c = pg.evaluate(CHIP_JS)
        if mo == 'fancy':
            check('fancy: chip toggles in place and animates (check · fill fade in — ② 단단한 이동: nothing slides or grows)', c['same'] and c['on'] == 'true' and len(c['anims']) >= 2 and 'transform' not in c['anims'] and c['op'] < 0.5 and c['op1'] == 1, c)
        else:
            check('reduced: chip toggles at once (no transition)', c['same'] and c['on'] == 'true' and not c['anims'] and c['op'] == 1, c)
        check(f'{mo}: a chip keeps its width and its neighbours stay put', c['dw'] < 0.6 and c['dx'] < 0.6, (c['dw'], c['dx']))
        i = pg.evaluate(IND_JS)
        if mo == 'fancy':
            check('fancy: week marker rides the springs to the new day', i['mid'] != i['want'] and i['end'] == i['want'] and i['w'] < 1, i)
        else:
            check('reduced: week marker jumps to the new day', i['now'] == i['want'] and i['end'] == i['want'], i)
        d = pg.evaluate(DLG_JS)
        if mo == 'fancy':
            check('fancy: sheet opens with a transition and a backdrop fade', 'transform' in d['opening'] and '::backdropopacity' in d['opening'], d['opening'])
            check('fancy: a real exit — closed at once (page usable, focus back on the row) but still drawn, moving out', not d['exit']['open'] and d['exit']['drawn']
                  and 'transform' in d['exit']['anims'] and '::backdropopacity' in d['exit']['anims'] and d['exit']['focus'], d['exit'])
            check('fancy: opening another row mid-exit turns the sheet around', d['back']['open'] and d['back']['on'] and d['settled'] == 'none' and d['closed'], (d['back'], d['settled']))
        else:
            check('reduced: sheet opens and closes at once (no transition, gone at once)', not d['opening'] and not d['exit']['drawn'] and not d['exit']['anims'] and d['closed'], d)
        check(f'{mo}: console errors 0', not E, E[:3])
        ctx.close()
    # drag to dismiss (design.md §7 시트 · §8): a slow short pull springs back, a throw closes and focus returns to the row
    E = []
    br2 = br.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
    br2.add_init_script("localStorage.setItem('khm.motion', '\"fancy\"');localStorage.setItem('khm.tickerPaused','true');")
    pg = br2.new_page(); pg.on('console', lambda m: E.append(m.text[:160]) if m.type == 'error' else None)
    pg.goto(LIVE + '#cal'); ready(pg)
    rid = pg.locator('#calendar .kc-ev').first.get_attribute('data-id')
    pg.locator('#calendar .kc-ev').first.click(); pg.wait_for_timeout(600)
    bb = pg.locator(DRAG).bounding_box(); x, y = bb['x'] + 20, bb['y'] + 8
    pg.mouse.move(x, y); pg.mouse.down()
    for i in range(1, 6):
        pg.mouse.move(x, y + i * 10); pg.wait_for_timeout(30)
    follow = pg.evaluate("getComputedStyle(document.querySelector('dialog.kc-dlg')).transform")
    pg.wait_for_timeout(200); pg.mouse.up(); pg.wait_for_timeout(1200)
    s1 = pg.evaluate("() => { const g = document.querySelector('dialog.kc-dlg'); return { open: g.open, drag: g.classList.contains('drag'), tf: getComputedStyle(g).transform } }")
    check('drag: the sheet follows the finger, a slow 50px pull springs back', follow.replace(' ', '') == 'matrix(1,0,0,1,0,50)' and s1['open'] and not s1['drag'] and s1['tf'] == 'none', (follow, s1))
    pg.mouse.move(x, y); pg.mouse.down()
    for i in range(1, 8):
        pg.mouse.move(x, y + i * 30); pg.wait_for_timeout(12)
    pg.mouse.up(); pg.wait_for_timeout(900)
    s2 = pg.evaluate("() => ({ open: document.querySelector('dialog.kc-dlg').open, back: document.activeElement.dataset.id })")
    check('drag: a throw down closes it, focus back on the row', not s2['open'] and s2['back'] == rid, s2)
    check('drag: console errors 0', not E, E[:3])
    br2.close()
    # press: 1px down at once (desktop mouse)
    E = []
    ctx, pg = open_page(br, LIVE + '#cal', 1440, 900, E, motion='fancy')
    ready(pg)
    b = pg.locator('.kc-chip[data-chip="hi"]').bounding_box()
    pg.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2); pg.mouse.down()
    t = pg.evaluate("() => getComputedStyle(document.querySelector('.kc-chip[data-chip=\"hi\"]')).transform")
    pg.mouse.up(); pg.wait_for_timeout(400)
    check('1440 fancy: a chip sinks 1px while pressed', t.replace(' ', '') == 'matrix(1,0,0,1,0,1)', t)
    pg.locator('.kc-chip[data-chip="hi"]').click(); pg.wait_for_timeout(300)
    check('1440 fancy: console errors 0', not E, E[:3])
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
            motion(br)
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
