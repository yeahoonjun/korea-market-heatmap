#!/usr/bin/env python3
"""QA for the 지표 tab's 증시 자금 group (AGENTS.md §3-32 ①, docs/standards/datago.md §6) — src/world UI against a mock Worker.

  python3 scripts/build_page.py && python3 qa/world/test_funds.py

Starts qa/world/mock_api.py on FUNDS_QA_PORT (8921) with /__mode?macro=on&funds=on (fixtures/funds.json) and checks:
caption 환율 · 금리 · 증시 자금 after which 원자재 follows, the head (business day + "색은 늘고 준 것만"), rows (조원 / 억원 values,
signed changes, % chip or %p chip, colour = KH.colorOf(ratio), state column = the business day, no 장중 dot), the section source
line, the page source line, nothing clipped, no overflow at 390 / 768 / 1280 / 1920 and in all four themes at 390, the sheet
(meta, note, chart in 조원 / %, 1년, Esc → focus back), keyboard across the block, that 증시 자금 does not feed the 자동 colour
range, the summary or 많이 오른·내린, the request cadence (once per 10 min, not every 30 s), the failure modes (gone = a Worker
without the route → absent and not asked again, fail / empty → absent, stale, partial, slow), an older Worker without 환율 · 금리,
and the snapshot page. Screenshots: /tmp/funds_<theme>_<width>.png, /tmp/funds_sheet_<key>_<width>.png.
Exit code 1 if any check fails.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('FUNDS_QA_PORT', 8921))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
FUNDS = json.loads((HERE / 'fixtures/funds.json').read_text(encoding='utf-8'))
FITEMS = {'fd:' + it['key']: it for it in FUNDS['items']}
CMDTY = json.loads((HERE / 'fixtures/world_commodity.json').read_text(encoding='utf-8'))
MACRO = json.loads((HERE / 'fixtures/world_macro.json').read_text(encoding='utf-8'))
N_CM = sum(len(g['items']) for g in CMDTY['groups'])
N_MX = sum(len(g['items']) for g in MACRO['groups'])
N_ALL = N_CM + N_MX + len(FITEMS)
N_CLOSED = sum(1 for d in (CMDTY, MACRO) for g in d['groups'] for it in g['items'] if it.get('status') != 'OPEN')   # 지금 열린 시장's 마감 count
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MINUS = '−'

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def get(url, timeout=10):
    try:
        with NOPROXY.open(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def mode(**kw):
    get(LIVE + '__mode?' + '&'.join(f'{k}={v}' for k, v in kw.items()), 5)


def stats():
    return get(LIVE + '__stats')[1]


# ── expected texts (the rules in world.js, written out independently) ──
def sgn(v):
    return '+' if v > 0 else MINUS if v < 0 else ''


def eok(v, signed=False):
    a = abs(v)
    if a >= 10000:
        txt, zero = f'{a / 10000:,.2f}조원', round(a / 100) == 0
    elif a >= 100:
        txt, zero = f'{round(a):,}억원', False
    else:
        txt, zero = f'{a:,.1f}억원', round(a * 10) == 0
    return ((('' if zero else sgn(v)) if signed else (MINUS if v < 0 else '')) + txt)


def expect(it):
    if it['unit'] == '%':
        dp = 1
        return {'v': f"{it['value']:.{dp}f}%", 'c': '', 'p': f"{sgn(round(it['change'], dp))}{abs(it['change']):.{dp}f}%p"}
    r = it['ratio']
    return {'v': eok(it['value']), 'c': eok(it['change'], True), 'p': f'{sgn(r)}{abs(r):.2f}%'}


class Errors:
    def __init__(self):
        self.items, self.http = [], []
        self.allow_404 = False

    def attach(self, page):
        # /api/time is the clock module's (not mocked here); a 404 on /api/funds is expected only in the 'gone' pass
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))
        page.on('response', lambda r: self.http.append(f'{r.status} {r.url}') if r.status >= 400 and '/api/funds' in r.url and not self.allow_404 else None)


ERR = Errors()


def open_page(browser, url, width, height, theme='base', reduced=False):
    mobile = width < 700
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__fdPre')) return; sessionStorage.setItem('__fdPre', '1'); "
                        f"localStorage.setItem('khm.theme', {json.dumps(theme)}); }})();")
    page = ctx.new_page()
    ERR.attach(page)
    page.goto(url)
    return ctx, page


def wait_funds(page):
    page.wait_for_selector('#world .kw-sec[data-g="funds"] .kw-lr', timeout=12000)
    page.wait_for_timeout(400)


LAYOUT_JS = r"""
() => {
  const L = document.querySelector('#world .kw-list');
  const kids = [...L.children].map(e => e.classList.contains('kw-bt') ? 'cap:' + e.textContent : e.classList.contains('kw-col') ? 'col:' + e.dataset.b + ':' + [...e.querySelectorAll('.kw-sec')].map(s => s.dataset.g).join('+') : e.className);
  const secs = [...L.querySelectorAll('.kw-sec')].map(s => s.dataset.g);
  const fs = L.querySelector('.kw-sec[data-g="funds"]');
  const hd = fs && fs.querySelector('.kw-sh');
  const vis = el => !!el && el.getBoundingClientRect().width > 4 && getComputedStyle(el).display !== 'none' && el.scrollWidth <= el.clientWidth + 1;
  const note = hd && hd.querySelector('.a small');
  const txt = document.getElementById('world').innerText;
  return {
    kids, secs, n: L.querySelectorAll('.kw-lr').length,
    head: hd ? { t: hd.querySelector('.t').textContent, s: hd.querySelector('.s').textContent, a: hd.querySelector('.a').textContent, tag: hd.tagName, noteVisible: vis(note), tVisible: vis(hd.querySelector('.t')), sVisible: vis(hd.querySelector('.s')) } : null,
    fsrc: fs ? (fs.querySelector('.kw-fsrc') || {}).textContent : null,
    sum: document.querySelector('#world .kw-sum').textContent,
    rankSub: (document.querySelector('#world .kw-rank-sub') || {}).textContent, rankKeys: [...document.querySelectorAll('#world .kw-row')].map(b => b.dataset.k),
    src: document.querySelector('#world .kw-src').textContent,
    openTxt: (document.querySelector('#world .kw-omf') || {}).textContent,
    bad: (txt.match(/\b(null|NaN|undefined|Infinity)\b/g) || []),
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    range: typeof KH.rangeInfo === 'function' ? KH.rangeInfo() : null,
    cols: [...L.querySelectorAll('.kw-col')].map(c => [c.dataset.b, Math.round(c.getBoundingClientRect().left), [...c.querySelectorAll('.kw-sec')].map(s => s.dataset.g).join('+')]),
  };
}"""

ROWS_JS = r"""
(want) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const out = { n: 0, bad: [], clip: [] };
  const vw = document.documentElement.clientWidth;
  for (const r of document.querySelectorAll('#world .kw-sec[data-g="funds"] .kw-lr')) {
    const w = want[r.dataset.k]; if (!w) { out.bad.push('unknown ' + r.dataset.k); continue; }
    out.n++;
    const lv = r.querySelector('.kw-lv'), lc = r.querySelector('.kw-lc'), chip = r.querySelector('.kw-pchip'), st = r.querySelector('.kw-ls .st'), dot = r.querySelector('.kw-ls .kw-sd');
    if (lv.textContent !== w.v) out.bad.push(`${r.dataset.k} value '${lv.textContent}' != '${w.v}'`);
    if (lc.textContent !== w.c) out.bad.push(`${r.dataset.k} change '${lc.textContent}' != '${w.c}'`);
    if (chip.textContent !== w.p) out.bad.push(`${r.dataset.k} chip '${chip.textContent}' != '${w.p}'`);
    if (st.textContent !== w.st) out.bad.push(`${r.dataset.k} state '${st.textContent}' != '${w.st}'`);
    if (dot.getBoundingClientRect().width > 0) out.bad.push(`${r.dataset.k} shows a 장중/마감 dot`);
    if (getComputedStyle(chip).backgroundColor !== norm(KH.colorOf(w.ratio))) out.bad.push(`${r.dataset.k} chip colour`);
    const cc = w.change > 0 ? 'up' : w.change < 0 ? 'dn' : 'flat';
    if (w.c && !lc.classList.contains(cc)) out.bad.push(`${r.dataset.k} change class ${lc.className} (want ${cc})`);
    if (!/^증시 자금, /.test(r.getAttribute('aria-label') || '') || !/금융투자협회/.test(r.getAttribute('aria-label'))) out.bad.push(`${r.dataset.k} aria '${r.getAttribute('aria-label')}'`);
    const rr = r.getBoundingClientRect();
    for (const el of [chip, lv, lc, st]) {
      const b = el.getBoundingClientRect();
      if (el.textContent && (el.scrollWidth > el.clientWidth + 1 || b.right > rr.right + 0.5 || b.left < rr.left - 0.5 || b.right > vw)) out.clip.push(`${r.dataset.k} ${el.className} ${el.textContent}`);
    }
    const nm = r.querySelector('.kw-ln .nm');
    if (nm.scrollWidth > nm.clientWidth + 1) out.clip.push(`${r.dataset.k} name cut '${nm.textContent}'`);
    const sub = r.querySelector('.kw-ln .sub'), sub2 = r.querySelector('.kw-ls .sub2');
    if (w.sub && sub.textContent !== w.sub) out.bad.push(`${r.dataset.k} sub '${sub.textContent}' != '${w.sub}'`);
  }
  return out;
}"""

SUB = {'fd:forced': '하루 금액', 'fd:forcedRatio': '미수금 대비'}


def want_rows(st='11.13', over=None):
    out = {}
    for k, it in FITEMS.items():
        e = expect(it)
        out[k] = dict(e, ratio=it['ratio'], change=it['change'], st=(over or {}).get(k, st), sub=SUB.get(k, ''))
    return out


def tab_pass(browser, theme, width, height):
    tag = f'{theme} {width}'
    ctx, page = open_page(browser, LIVE + '#cmdty', width, height, theme)
    try:
        wait_funds(page)
        lay = page.evaluate(LAYOUT_JS)
        caps = [k for k in lay['kids'] if k.startswith('cap:')]
        check(f'{tag}: caption "환율 · 금리 · 증시 자금" then "원자재"; sections fx → rates → funds → energy · metals · agri',
              caps == ['cap:환율 · 금리 · 증시 자금', 'cap:원자재'] and lay['secs'] == ['fx', 'rates', 'funds', 'energy', 'metals', 'agri'] and lay['n'] == N_ALL,
              f"{caps} {lay['secs']} {lay['n']}/{N_ALL}")
        h = lay['head']
        check(f'{tag}: head = 증시 자금 · "11월 13일 (금) 기준" · note "색은 늘고 준 것만" (all visible, h4)',
              h and h['t'] == '증시 자금' and h['s'] == '11월 13일 (금) 기준' and h['a'] == '색은 늘고 준 것만' and h['noteVisible'] and h['tVisible'] and h['sVisible'] and h['tag'] == 'H4', str(h))
        check(f'{tag}: section source line "금융투자협회 · 하루 한 번(전 영업일 기준)"', lay['fsrc'] == '금융투자협회 · 하루 한 번(전 영업일 기준)', str(lay['fsrc']))
        rows = page.evaluate(ROWS_JS, want_rows())
        check(f'{tag}: rows = fixture (조원/억원, signed change, % or %p chip, colour = KH.colorOf(ratio), state = 11.13, no dot, aria)',
              rows['n'] == len(FITEMS) and not rows['bad'], '; '.join(rows['bad'][:4]) or f"{rows['n']} rows")
        check(f'{tag}: nothing clipped', not rows['clip'], '; '.join(rows['clip'][:4]))
        check(f'{tag}: no horizontal overflow, no null / NaN text', lay['over'] <= 0 and not lay['bad'], f"{lay['over']}px {lay['bad'][:3]}")
        check(f'{tag}: summary · 많이 오른·내린 · 지금 열린 시장 leave 증시 자금 out', lay['sum'].startswith('원자재') and lay['rankSub'] == f'원자재 {N_CM}개 중'
              and not any(k.startswith('fd:') for k in lay['rankKeys']) and (f'마감 {N_CLOSED}개' in lay['openTxt'] if N_CLOSED else '모두 장중' in lay['openTxt']), f"{lay['sum']} / {lay['rankSub']} / {lay['openTxt']} (want 마감 {N_CLOSED}개)")
        check(f'{tag}: page source line names 금융투자협회 and the day', '증시 자금은 금융투자협회 통계' in lay['src'] and '11월 13일 (금) 자료' in lay['src'] and '하루 한 번 종가' not in lay['src'].split('지금 목록:')[-1].split('.')[0], lay['src'][-140:])
        if width >= 1920:
            mx = [c for c in lay['cols'] if c[0] == 'mx']
            check(f'{tag}: 환율 | 금리 | 증시 자금 side by side', [c[2] for c in mx] == ['fx', 'rates', 'funds'], str(lay['cols']))
        elif width >= 1280:
            mx = [c for c in lay['cols'] if c[0] == 'mx']
            check(f'{tag}: two columns: 환율 + 금리 | 증시 자금', [c[2] for c in mx] == ['fx+rates', 'funds'], str(lay['cols']))
        elif width < 700:
            check(f'{tag}: phone = one column', len({c[1] for c in lay['cols']}) == 1, str(lay['cols']))
        page.screenshot(path=f'/tmp/funds_{theme}_{width}.png', full_page=True)
        if theme == 'base' and width in (390, 1280):
            sheet_pass(page, width)
        if theme == 'base' and width == 1920:
            keyboard_pass(page)
    finally:
        ctx.close()


SHEET_JS = r"""
() => {
  const s = document.querySelector('.kw-sheet');
  if (!s || s.hidden) return null;
  const dd = {}; for (const dt of s.querySelectorAll('.kw-meta dt')) dd[dt.textContent] = dt.nextElementSibling.textContent;
  const svg = s.querySelector('.kw-svg');
  const r = s.getBoundingClientRect();
  return { path: s.querySelector('.kw-path').textContent, title: s.querySelector('#kw-dt').textContent, st: (s.querySelector('.kw-st') || {}).textContent, px: s.querySelector('.kw-px').textContent, meta: dd,
    note: (s.querySelector('.kw-note') || {}).textContent || '', src: s.querySelector('.kw-dsrc').textContent, cnote: (s.querySelector('.kw-cnote') || {}).textContent,
    chart: !!svg, line: svg ? svg.querySelector('.kw-line').getAttribute('d').length : 0, yl: svg ? [...svg.querySelectorAll('.kw-yl')].map(t => t.textContent) : [],
    ylClip: svg ? [...svg.querySelectorAll('.kw-yl')].some(t => t.getBBox().x + t.getBBox().width > svg.viewBox.baseVal.width + 0.5) : false,
    read: (s.querySelector('.kw-read') || {}).textContent || '', text: s.innerText, inView: r.left >= -1 && r.right <= innerWidth + 1, over: s.scrollWidth - s.clientWidth };
}"""


def open_sheet(page, key):
    page.click(f'#world .kw-lr[data-k="{key}"]')
    page.wait_for_selector('.kw-sheet:not([hidden]) .kw-svg', timeout=10000)
    page.wait_for_timeout(250)
    return page.evaluate(SHEET_JS)


def sheet_pass(page, width):
    tag = f'sheet {width}'
    it = FITEMS['fd:deposit']
    s = open_sheet(page, 'fd:deposit')
    check(f'{tag}: 투자자예탁금 — 78.51조원, +1,235억원 (+0.16%), 하루 한 번, path 증시 자금 · 금융투자협회',
          s and s['title'] == '투자자예탁금' and s['path'] == '증시 자금 · 금융투자협회' and s['st'] == '하루 한 번' and '78.51조원' in s['px'] and '+1,235억원 (+0.16%)' in s['px'], json.dumps(s and {k: s[k] for k in ('title', 'path', 'st', 'px')}, ensure_ascii=False))
    check(f'{tag}: meta 기준일 · 전 영업일 · 단위 · 갱신 · 기준 (금융투자협회)', s['meta'].get('기준일') == '11월 13일 (금)' and s['meta'].get('전 영업일', '').startswith(eok(it['prev'])) and '11월 12일 (목)' in s['meta'].get('전 영업일', '')
          and '조원' in s['meta'].get('단위', '') and '하루 한 번' in s['meta'].get('갱신', '') and '금융투자협회' in s['meta'].get('기준', ''), json.dumps(s['meta'], ensure_ascii=False))
    check(f'{tag}: note explains the series and says red/green is direction only, not good/bad', '고객예탁금' in s['note'] and '좋거나 나쁘다는 뜻은 아니에요' in s['note'], s['note'])
    check(f'{tag}: chart drawn in 조원, "영업일마다 · 금융투자협회", source line, labels inside', s['chart'] and s['line'] > 50 and all(y.endswith('조원') for y in s['yl']) and s['cnote'] == '영업일마다 · 금융투자협회'
          and s['src'].startswith('출처: 금융투자협회') and not s['ylClip'] and not re.search(r'\b(NaN|null|undefined)\b', s['text']), f"{s['yl']} {s['cnote']} {s['read']}")
    check(f'{tag}: sheet inside the viewport, no sideways scroll', s['inView'] and s['over'] <= 0, f"{s['inView']} {s['over']}")
    page.click('.kw-sheet .kw-tf button[data-v="1y"]')
    page.wait_for_function("document.querySelector('.kw-sheet .kw-tf button[aria-pressed=true]').dataset.v === '1y' && !!document.querySelector('.kw-sheet .kw-svg')", timeout=10000)
    page.wait_for_timeout(200)
    s1 = page.evaluate(SHEET_JS)
    check(f'{tag}: 1년 switch redraws (api/funds/chart/deposit?tf=1y)', s1['chart'] and '1년 동안' in s1['read'], s1['read'])
    page.screenshot(path=f'/tmp/funds_sheet_deposit_{width}.png')
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    back = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, focus: document.activeElement && document.activeElement.dataset.k })")
    check(f'{tag}: Esc closes, focus back on the row', back['hidden'] and back['focus'] == 'fd:deposit', str(back))
    s = open_sheet(page, 'fd:forcedRatio')
    check(f'{tag}: 반대매매 비중 — 0.5%, −0.2%p, unit %, chart in % with %p moves', s and '0.5%' in s['px'] and f'{MINUS}0.2%p' in s['px'] and s['meta'].get('단위', '').startswith('%')
          and all(y.endswith('%') for y in s['yl']) and '%p' in s['read'] and '비중' in s['note'], json.dumps({k: s[k] for k in ('px', 'yl', 'read')}, ensure_ascii=False))
    page.screenshot(path=f'/tmp/funds_sheet_forcedRatio_{width}.png')
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)


def keyboard_pass(page):
    page.focus('#world .kw-lr[data-k="US2YT"]')
    page.keyboard.press('ArrowRight')
    k1 = page.evaluate('document.activeElement.dataset.k')
    check('keys 1920: → from 금리 reaches 증시 자금 (same block)', str(k1).startswith('fd:'), k1)
    page.keyboard.press('ArrowRight')
    k2 = page.evaluate('document.activeElement.dataset.k')
    check('keys 1920: → at the last column of the block stays put', k2 == k1, f'{k1} → {k2}')
    page.keyboard.press('Enter')
    page.wait_for_selector('.kw-sheet:not([hidden])', timeout=5000)
    check('keys 1920: Enter opens the 증시 자금 sheet', page.evaluate("document.querySelector('#kw-dt').textContent") == FITEMS[k1]['name'])
    page.keyboard.press('Escape')


def range_pass(browser):
    """증시 자금 is a day-old statistic: it takes colours from the 자동 range but never sets it (the same range with or without it)"""
    out = {}
    for m in ('empty', 'on'):
        mode(funds=m)
        ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
        try:
            page.wait_for_selector('#world .kw-lr', timeout=10000)
            if m == 'on':
                wait_funds(page)
            page.wait_for_timeout(400)
            out[m] = page.evaluate('KH.rangeInfo()')
        finally:
            ctx.close()
    mode(funds='on')
    check('자동 colour range: the same with or without 증시 자금 (−20% 반대매매 does not widen it)', out['empty'] and out['on'] and out['empty'].get('p95') == out['on'].get('p95') and out['empty'].get('value') == out['on'].get('value'), str(out))


def cadence_pass(browser):
    """one /api/funds at tab open; the 30 s world refresh (forced here with KH.refresh) does not ask again within 10 min"""
    get(LIVE + '__reset')
    mode(macro='on', funds='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
    try:
        wait_funds(page)
        for _ in range(3):
            page.evaluate('KH.refresh()')
            page.wait_for_timeout(500)
        st = stats()
        check('cadence: world refreshed 4×, /api/funds asked once', st.get('world:commodity', 0) >= 3 and st.get('/api/funds', 0) == 1, json.dumps({k: v for k, v in st.items() if 'world' in k or 'funds' in k}))
        page.click('.tabs button[data-mkt="WORLD"]')
        page.wait_for_timeout(500)
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_funds(page)
        check('cadence: back to 지표 within 10 min → no new /api/funds, group still there', stats().get('/api/funds', 0) == 1)
    finally:
        ctx.close()


def mode_pass(browser, m, label, expect_group, extra=None):
    get(LIVE + '__reset')
    mode(macro='on', funds=m)
    ERR.allow_404 = m in ('gone', 'fail')                 # the failures this pass asks for
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        if expect_group:
            wait_funds(page)
        else:
            page.wait_for_timeout(1500)
        lay = page.evaluate(LAYOUT_JS)
        has = 'funds' in lay['secs']
        ok = has == expect_group and lay['over'] <= 0 and not lay['bad'] and lay['secs'][:2] == ['fx', 'rates']
        if not expect_group:
            ok = ok and [k for k in lay['kids'] if k.startswith('cap:')] == ['cap:환율 · 금리', 'cap:원자재'] and '증시 자금' not in lay['src']
        detail = f"{lay['secs']} over {lay['over']}"
        if extra:
            e_ok, e_detail = extra(page, lay)
            ok = ok and e_ok
            detail += ' ' + e_detail
        check(f'funds={m}: {label}', ok, detail)
        page.screenshot(path=f'/tmp/funds_mode_{m}.png', full_page=True)
    finally:
        ctx.close()
        ERR.allow_404 = False


def gone_extra(page):
    def f(p, lay):
        p.evaluate('KH.refresh()')
        p.wait_for_timeout(800)
        n = stats().get('/api/funds', 0)
        return n == 1, f'/api/funds asked {n}×'
    return f


def partial_extra(p, lay):
    rows = p.evaluate(ROWS_JS, want_rows(over={k: '11.12' for k in FITEMS if k.startswith('fd:credit')}))
    return not rows['bad'], '; '.join(rows['bad'][:3]) or 'credit rows say 11.12'


def stale_extra(p, lay):
    h = lay['head'] or {}
    return h.get('s') == '11월 13일 (금) 기준', str(h)


def slow_extra(p, lay):
    return True, 'appeared after the slow answer'


def old_worker_pass(browser):
    """an older Worker: no 환율 · 금리 and no /api/funds route → the commodities exactly as before"""
    get(LIVE + '__reset')
    mode(macro='off', funds='gone')
    ERR.allow_404 = True
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(1200)
        lay = page.evaluate(LAYOUT_JS)
        check('older Worker (no with=, no /api/funds): commodities only, no captions, no stray text', lay['secs'] == ['energy', 'metals', 'agri'] and not any(k.startswith('cap:') for k in lay['kids'])
              and not lay['bad'] and lay['over'] <= 0 and '증시 자금' not in lay['src'], str(lay['kids']))
    finally:
        ctx.close()
        ERR.allow_404 = False


def funds_only_pass(browser):
    """환율 · 금리 missing from an answer (a Naver hiccup) while 증시 자금 is there: the block is just 증시 자금"""
    get(LIVE + '__reset')
    mode(macro='off', funds='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844)
    try:
        wait_funds(page)
        lay = page.evaluate(LAYOUT_JS)
        check('환율 · 금리 absent, 증시 자금 present: caption "증시 자금", then 원자재', [k for k in lay['kids'] if k.startswith('cap:')] == ['cap:증시 자금', 'cap:원자재']
              and lay['secs'] == ['funds', 'energy', 'metals', 'agri'] and lay['over'] <= 0 and not lay['bad'], str(lay['kids']))
    finally:
        ctx.close()


def other_tab_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on')
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(800)
        lay = page.evaluate(LAYOUT_JS)
        check('해외 tab: no 증시 자금, /api/funds not asked', 'funds' not in lay['secs'] and stats().get('/api/funds', 0) == 0, str(stats().get('/api/funds')))
    finally:
        ctx.close()


def reduced_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844, reduced=True)
    try:
        wait_funds(page)
        s = open_sheet(page, 'fd:credit')
        check('reduced motion 390: 신용융자 전체 sheet opens, chart drawn', s and s['chart'] and s['title'] == '신용융자 전체', str(s and s['title']))
    finally:
        ctx.close()


def snapshot_pass(browser):
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    page = ctx.new_page()
    ERR.attach(page)
    try:
        page.goto(SNAP + '#cmdty')
        page.wait_for_selector('#world .kw-snap', timeout=10000)
        t = page.evaluate("document.querySelector('#world .kw-snap p').textContent")
        check('snapshot: the 지표 note mentions 증시 자금 (금융투자협회, 하루 한 번)', '증시 자금' in t and '하루 한 번' in t, t)
    finally:
        ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    mock = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                get(LIVE + '__reset', 2)
                break
            except Exception:
                time.sleep(0.25)
        mode(macro='on', funds='on')
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for w, hgt in ((390, 844), (768, 1024), (1280, 800), (1920, 1080)):
                tab_pass(browser, 'base', w, hgt)
            for theme in THEMES[1:]:
                tab_pass(browser, theme, 390, 844)
            range_pass(browser)
            cadence_pass(browser)
            mode_pass(browser, 'gone', 'a Worker without the route (plain 404) → group absent, not asked again', False, gone_extra(None))
            mode_pass(browser, 'fail', '503 → group absent, the rest of the tab as before', False)
            mode_pass(browser, 'empty', 'no items → group absent', False)
            mode_pass(browser, 'stale', 'stale copy → shown with its business day', True, stale_extra)
            mode_pass(browser, 'partial', '신용융자 a day older → those rows say 11.12', True, partial_extra)
            mode_pass(browser, 'slow', 'slow /api/funds → the tab draws first, the group joins later', True, slow_extra)
            old_worker_pass(browser)
            funds_only_pass(browser)
            other_tab_pass(browser)
            reduced_pass(browser)
            snapshot_pass(browser)
            browser.close()
        check('console errors 0, no unexpected 4xx/5xx on /api/funds*', not ERR.items and not ERR.http, '; '.join((ERR.items + ERR.http)[:4]))
    finally:
        mock.terminate()
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
