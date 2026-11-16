#!/usr/bin/env python3
"""QA for the 지표 tab's 수출입은행 고시 tables (AGENTS.md §3-27 끝, user 2026-11-16 11:33 "그래 추천대로") — src/world UI against
the mock Worker (qa/world/mock_api.py, /__mode?kx=…, fixtures/koreaexim.json = the probe's real values of 2026-11-16).

  python3 scripts/build_page.py && python3 qa/world/test_koreaexim.py

Checks: ① the 환율 card ends with "수출입은행 고시" — 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 × 매매기준율 · 송금 보낼 때 · 받을 때,
"하루 한 번 · 오늘 11:04 고시", the 환전 · 송금 note, no colour; ③ the 금리 card ends with "기준금리 · 은행간 금리" — SOFR · ESTR ·
EURIBOR · TIBOR (TONA only when sent), 3-decimal %, bp coloured by direction only, "하루 한 번 · 수출입은행"; the source line;
nothing clickable or focusable inside; no overflow, nothing clipped at 360 / 390 / 768 / 1280 / 1920 and in all four themes at
360 and 1280; the failure modes (one table failing, both, an older Worker = plain 404 → absent and not asked again, empty,
slow → the rest draws first), waiting / stale / late / no-prev wording, the request cadence (once per 10 min, not with the 30 s
world refresh), no request from the 해외 tab or for an older Worker without 환율 · 금리, the snapshot note, console errors 0.
Port KX_QA_PORT (9041). Screenshots: /tmp/kx_<theme>_<width>.png, /tmp/kx_mode_<mode>.png. Exit code 1 if any check fails.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('KX_QA_PORT', 9041))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
KX = json.loads((HERE / 'fixtures/koreaexim.json').read_text(encoding='utf-8'))
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MINUS = '−'
FX_NAMES = [('USD', '원/달러'), ('JPY', '원/엔(100엔)'), ('EUR', '원/유로'), ('CNH', '원/위안')]

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


# expected texts, written out independently of world.js
def f2(v):
    return '—' if v is None else (MINUS if v < 0 else '') + f'{abs(v):,.2f}'


def f3(v):
    return (MINUS if v < 0 else '') + f'{abs(v):.3f}%'


def bpt(v):
    r = round(v * 10) / 10
    return ('+' if r > 0 else MINUS if r < 0 else '') + f'{abs(r):.1f}bp'


def bpcls(v):
    r = round(v * 10) / 10
    return 'up' if r > 0 else 'dn' if r < 0 else 'flat'


class Errors:
    def __init__(self):
        self.items, self.http = [], []
        self.allow = False

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))
        page.on('response', lambda r: self.http.append(f'{r.status} {r.url}') if r.status >= 400 and '/api/koreaexim' in r.url and not self.allow else None)


ERR = Errors()


def open_page(browser, url, width, height, theme='base', reduced=False):
    mobile = width < 700
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__kxPre')) return; sessionStorage.setItem('__kxPre', '1'); "
                        f"localStorage.setItem('khm.theme', {json.dumps(theme)}); }})();")
    page = ctx.new_page()
    ERR.attach(page)
    page.goto(url)
    return ctx, page


def wait_kx(page, kinds=('fx', 'rate')):
    page.wait_for_selector('#world .kw-lr', timeout=10000)
    for k in kinds:
        page.wait_for_selector(f'#world .kw-kx[data-kx="{k}"]:not([hidden]) table', timeout=10000)
    page.wait_for_timeout(350)


READ_JS = r"""
() => {
  const W = document.getElementById('world');
  const box = k => W.querySelector(`.kw-kx[data-kx="${k}"]`);
  const one = k => {
    const b = box(k); if (!b) return null;
    const sec = b.closest('.kw-sec');
    const t = b.querySelector('table');
    const cells = t ? [...t.querySelectorAll('tbody tr')].map(tr => ({ k: tr.dataset.k, title: tr.title,
      cells: [...tr.children].map(c => ({ tag: c.tagName, text: c.textContent, cls: c.className, color: getComputedStyle(c).color, rs: c.getAttribute('rowspan') })) })) : [];
    const head = t ? [...t.querySelectorAll('thead th')].map(th => th.textContent) : [];
    const kids = sec ? [...sec.children].map(c => c.className) : [];
    return { hidden: b.hidden, sec: sec && sec.dataset.g, last: sec && sec.lastElementChild === b, kids, cells, head,
      title: (b.querySelector('.kw-kxt') || {}).textContent || '', meta: (b.querySelector('.kw-kxm') || {}).textContent || '',
      warn: !!b.querySelector('.kw-kxm .kwn'), note: [...b.querySelectorAll('.kw-kxn')].map(p => p.textContent).join(' | '),
      text: b.textContent, tag: (b.querySelector('.kw-kxt') || {}).tagName, labelled: t ? t.getAttribute('aria-labelledby') : null,
      focusables: b.querySelectorAll('button, a, input, select, [tabindex]').length, num: t ? getComputedStyle(t).fontVariantNumeric : '' };
  };
  const up = getComputedStyle(W).getPropertyValue('--up-text').trim(), dn = getComputedStyle(W).getPropertyValue('--dn-text').trim();
  const norm = c => { const e = document.createElement('i'); e.style.color = c; W.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const fg = getComputedStyle(W.querySelector('.kw-sec') || W).color;
  return { fx: one('fx'), rate: one('rate'), up: norm(up), dn: norm(dn), fg,
    src: (W.querySelector('.kw-src-kx') || {}).textContent || '', srcAll: (W.querySelector('.kw-src') || W).textContent || '',
    rows: W.querySelectorAll('.kw-lr').length, secs: [...W.querySelectorAll('.kw-sec')].map(s => s.dataset.g) };
}"""

FIT_JS = r"""
() => {
  const out = { over: document.documentElement.scrollWidth - document.documentElement.clientWidth, clip: [], out: [] };
  const vw = document.documentElement.clientWidth;
  for (const b of document.querySelectorAll('#world .kw-kx:not([hidden])')) {
    const sec = b.closest('.kw-sec').getBoundingClientRect(), br = b.getBoundingClientRect();
    if (br.left < sec.left - 0.5 || br.right > sec.right + 0.5) out.out.push(b.dataset.kx + ' box outside its card');
    const t = b.querySelector('table');
    if (t && t.scrollWidth > b.clientWidth + 1) out.clip.push(`${b.dataset.kx} table ${t.scrollWidth} > ${b.clientWidth}`);
    for (const el of b.querySelectorAll('th, td, .kw-kxt, .kw-kxm, .kw-kxn')) {
      if (el.classList.contains('sr') || !el.textContent) continue;
      const r = el.getBoundingClientRect();
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== 'inline') out.clip.push(`${b.dataset.kx} ${el.tagName}.${el.className} '${el.textContent.slice(0, 20)}'`);
      if (r.right > Math.min(vw, br.right) + 0.5 || r.left < br.left - 0.5) out.out.push(`${b.dataset.kx} ${el.tagName} '${el.textContent.slice(0, 20)}' ${r.left.toFixed(1)}–${r.right.toFixed(1)} vs ${br.left.toFixed(1)}–${br.right.toFixed(1)}`);
    }
  }
  return out;
}"""


def check_tables(r, tag, kx=KX):
    fx, rt = r['fx'], r['rate']
    # ① 환율 card
    ok = fx and not fx['hidden'] and fx['sec'] == 'fx' and fx['last'] and fx['kids'].index('kw-rows') < len(fx['kids']) - 1
    check(f'{tag}: 수출입은행 고시 table at the end of the 환율 card', ok, json.dumps(fx and fx['kids']))
    want = []
    by = {it['code']: it for it in kx['fx']['items']}
    for code, name in FX_NAMES:
        it = by[code]
        want.append([name, f2(it['base']), f2(it['tts']), f2(it['ttb'])])
    got = [[c['text'] for c in row['cells']] for row in fx['cells']]
    check(f'{tag}: 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 × 매매기준율 · 송금 보낼 때 · 받을 때', got == want, json.dumps(got, ensure_ascii=False)[:300])
    check(f'{tag}: 환율 heads + title + meta "하루 한 번 · 오늘 11:04 고시" (h5, table labelled by it)',
          fx['head'] == ['통화', '매매기준율', '송금 보낼 때', '송금 받을 때'] and fx['title'] == '수출입은행 고시' and fx['meta'] == '하루 한 번 · 오늘 11:04 고시'
          and fx['tag'] == 'H5' and fx['labelled'] == 'kw-kx-fx', f"{fx['head']} {fx['title']} {fx['meta']}")
    check(f'{tag}: 환율 note = what it is for, not advice', '환전 · 송금할 때 참고' in fx['note'] and '은행과 우대율마다 달라요' in fx['note'], fx['note'])
    colours = {c['color'] for row in fx['cells'] for c in row['cells'][1:]}
    check(f'{tag}: 환율 numbers have no up / down colour', r['up'] not in colours and r['dn'] not in colours, str(colours))
    # ③ 금리 card
    ok = rt and not rt['hidden'] and rt['sec'] == 'rates' and rt['last']
    check(f'{tag}: 기준금리 · 은행간 금리 table at the end of the 금리 card', ok, json.dumps(rt and rt['kids']))
    items = kx['rate']['items']
    keys = [row['k'] for row in rt['cells']]
    check(f'{tag}: rate rows SOFR · ESTR · EURIBOR 1/3/6/12 · TIBOR 1/3/6/12 in order', keys == [it['key'] for it in items], str(keys))
    bad = []
    for row, it in zip(rt['cells'], items):
        tds = [c for c in row['cells'] if c['tag'] == 'TD']
        if [c['text'] for c in tds[:2]] != [it['tenor'], f3(it['value'])]:
            bad.append(f"{it['key']} {[c['text'] for c in tds]}")
        b = tds[2] if len(tds) > 2 else None
        if not b or b['text'] != bpt(it['bp']) or bpcls(it['bp']) not in b['cls'].split():
            bad.append(f"{it['key']} bp {b and b['text']} {b and b['cls']} != {bpt(it['bp'])}")
        elif bpcls(it['bp']) == 'up' and b['color'] != r['up'] or bpcls(it['bp']) == 'dn' and b['color'] != r['dn']:
            bad.append(f"{it['key']} bp colour {b['color']}")
        if it['raw'] not in row['title']:
            bad.append(f"{it['key']} title {row['title']}")
    check(f'{tag}: rate tenor · 3-decimal % · bp (sign + colour = direction only) · title with the source value', not bad, '; '.join(bad[:4]))
    fam = [(c['text'], c['rs']) for row in rt['cells'] for c in row['cells'] if c['tag'] == 'TH']
    check(f'{tag}: one family head per group (rowspan), currency beside it', fam == [('SOFR달러', '1'), ('ESTR유로', '1'), ('EURIBOR유로', '4'), ('TIBOR엔', '4')], str(fam))
    check(f'{tag}: rate meta "하루 한 번 · 수출입은행 · 오늘 11:04 고시", heads 기간 · 금리 · 변화',
          rt['meta'] == '하루 한 번 · 수출입은행 · 오늘 11:04 고시' and rt['head'] == ['이름', '기간', '금리', '변화'] and rt['title'] == '기준금리 · 은행간 금리', f"{rt['meta']} {rt['head']}")
    check(f'{tag}: rate note (익일 / 기간별, bp = 0.01%p)', '익일은 하루짜리 기준금리' in rt['note'] and '전 영업일 고시 대비' in rt['note'], rt['note'])
    check(f'{tag}: nothing clickable or focusable inside, tabular figures', fx['focusables'] == 0 and rt['focusables'] == 0 and 'tabular-nums' in fx['num'] and 'tabular-nums' in rt['num'])
    check(f'{tag}: source line "한국수출입은행 · 하루 한 번" with the posting day', '한국수출입은행 · 하루 한 번' in r['src'] and '11월 16일 (월) 고시' in r['src'], r['src'])


def tab_pass(browser, theme, w, hgt):
    mode(macro='on', funds='on', kx='on', world='ok')
    ctx, page = open_page(browser, LIVE + '#cmdty', w, hgt, theme)
    try:
        wait_kx(page)
        r = page.evaluate(READ_JS)
        tag = f'{theme} {w}'
        if theme == 'base' and w in (360, 1280):
            check_tables(r, tag)
        else:
            check(f'{tag}: both tables drawn', r['fx'] and not r['fx']['hidden'] and r['rate'] and len(r['rate']['cells']) == 10 and len(r['fx']['cells']) == 4)
        fit = page.evaluate(FIT_JS)
        check(f'{tag}: no horizontal overflow, nothing clipped, inside its card', fit['over'] <= 0 and not fit['clip'] and not fit['out'], json.dumps(fit, ensure_ascii=False)[:300])
        el = page.query_selector('#world .kw-list')
        el.screenshot(path=f'/tmp/kx_{theme}_{w}.png')
        if theme == 'base' and w == 360:
            # rows are not buttons: a press inside does nothing (no sheet)
            page.click('#world .kw-kx[data-kx="fx"] tbody tr')
            page.wait_for_timeout(300)
            n = page.evaluate("document.querySelectorAll('.kw-sheet:not([hidden])').length")
            check(f'{tag}: pressing a 고시 row opens nothing', n == 0, str(n))
    finally:
        ctx.close()


def mode_pass(browser, m, fn, kinds=('fx', 'rate'), allow=False):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx=m)
    ERR.allow = allow
    ctx, page = open_page(browser, LIVE + '#cmdty', 360, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        if kinds:
            wait_kx(page, kinds)
        else:
            page.wait_for_timeout(1200)
        r = page.evaluate(READ_JS)
        fn(r, page)
        fit = page.evaluate(FIT_JS)
        check(f'kx={m}: no overflow at 360', fit['over'] <= 0 and not fit['clip'] and not fit['out'], json.dumps(fit, ensure_ascii=False)[:200])
        page.query_selector('#world .kw-list').screenshot(path=f'/tmp/kx_mode_{m}.png')
    finally:
        ctx.close()
        ERR.allow = False


def m_wait(r, page):
    check('kx=wait: Friday shown "11월 13일 (금) 고시", note "오늘 고시는 아직 나오지 않았어요", no warning',
          r['fx']['meta'] == '하루 한 번 · 11월 13일 (금) 고시' and '오늘 고시는 아직 나오지 않았어요' in r['fx']['note'] and '오늘 고시는 아직' in r['rate']['note']
          and not r['fx']['warn'], f"{r['fx']['meta']} | {r['fx']['note']}")
    check('kx=wait: source line names Friday', '11월 13일 (금) 고시' in r['src'], r['src'])


def m_stale(r, page):
    check('kx=stale: ! beside the meta (+ screen-reader words) and the note says it is the last value',
          r['fx']['warn'] and r['rate']['warn'] and '새 값을 확인하지 못했어요' in r['fx']['text'] and '지난 값을 보여 줘요' in r['fx']['note'], r['fx']['meta'])


def m_late(r, page):
    check('kx=late: first seen 13:20 without an empty check before → "오늘 고시 · 13:20 확인" (not "13:20 고시")',
          r['fx']['meta'] == '하루 한 번 · 오늘 고시 · 13:20 확인' and r['rate']['meta'].endswith('오늘 고시 · 13:20 확인'), r['fx']['meta'])


def m_nobp(r, page):
    check('kx=nobp: no previous posting → no 변화 column, no bp clause', r['rate']['head'] == ['이름', '기간', '금리'] and '전 영업일' not in r['rate']['note']
          and all(len(row['cells']) <= 3 for row in r['rate']['cells']), str(r['rate']['head']))


def m_tona(r, page):
    keys = [row['k'] for row in r['rate']['cells']]
    check('kx=tona: TONA 익일 after ESTR when the source sends it', keys[:3] == ['SOFRON', 'ESTRON', 'TONAON'] and 'TONA엔' in r['rate']['text'], str(keys[:4]))


def m_fxfail(r, page):
    check('kx=fxfail: the 환율 place says it could not load (! + words), 금리 table as usual, every list row still there',
          not r['fx']['hidden'] and '수출입은행 고시 환율을 불러오지 못했어요' in r['fx']['text'] and not r['fx']['cells']
          and len(r['rate']['cells']) == 10 and r['rows'] >= 30, f"{r['fx']['text']} rows {r['rows']}")


def m_fail(r, page):
    check('kx=fail: both places say so, the rest of the tab untouched', '불러오지 못했어요' in r['fx']['text'] and '불러오지 못했어요' in r['rate']['text']
          and r['rows'] >= 30 and 'funds' in r['secs'] and not r['src'], str(r['secs']))


def m_gone(r, page):
    n = stats()
    check('kx=gone (older Worker, plain 404): both places hidden, no source mention', r['fx']['hidden'] and r['rate']['hidden'] and not r['src'])
    page.evaluate('KH.refresh()')
    page.wait_for_timeout(600)
    page.click('.tabs button[data-mkt="WORLD"]'); page.wait_for_timeout(300)
    page.click('.tabs button[data-mkt="CMDTY"]'); page.wait_for_timeout(600)
    n2 = stats()
    check('kx=gone: not asked again on this page (refresh, tab switch)', n2.get('kx:fx', 0) == n.get('kx:fx', 0) == 1 and n2.get('kx:rate', 0) == 1, json.dumps({k: v for k, v in n2.items() if k.startswith('kx')}))


def m_empty(r, page):
    check('kx=empty: both places hidden (no rule, no heading), nothing in the source line', r['fx']['hidden'] and r['rate']['hidden'] and not r['fx']['text'] and not r['src'])


def slow_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='slow')
    ctx, page = open_page(browser, LIVE + '#cmdty', 360, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(300)
        early = page.evaluate("[...document.querySelectorAll('#world .kw-kx')].map(b => b.hidden)")
        rows = page.evaluate("document.querySelectorAll('#world .kw-lr').length")
        check('kx=slow: the list is drawn before the 고시 arrives (tables hidden meanwhile)', rows >= 30 and early == [True, True], f'{rows} {early}')
        wait_kx(page)
        check('kx=slow: both tables join when it arrives', True)
    finally:
        ctx.close()


def cadence_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
    try:
        wait_kx(page)
        for _ in range(3):
            page.evaluate('KH.refresh()')
            page.wait_for_timeout(500)
        st = stats()
        check('cadence: world refreshed 4×, each 고시 asked once', st.get('world:commodity', 0) >= 3 and st.get('kx:fx', 0) == 1 and st.get('kx:rate', 0) == 1,
              json.dumps({k: v for k, v in st.items() if 'world' in k or k.startswith('kx')}))
        page.click('.tabs button[data-mkt="WORLD"]')
        page.wait_for_timeout(500)
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_kx(page)
        check('cadence: back to 지표 within 10 min → no new ask, tables still there', stats().get('kx:fx', 0) == 1)
    finally:
        ctx.close()


def other_tab_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(800)
        st = stats()
        check('해외 tab: no 고시 table, /api/koreaexim not asked', not page.query_selector('#world .kw-kx') and not st.get('kx:fx') and not st.get('kx:rate'), json.dumps(st)[:200])
    finally:
        ctx.close()


def old_worker_pass(browser):
    get(LIVE + '__reset')
    mode(macro='off', funds='empty', kx='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(800)
        st = stats()
        check('older Worker without 환율 · 금리: no 고시 table and no ask', not page.query_selector('#world .kw-kx') and not st.get('kx:fx'), json.dumps(st)[:200])
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
        check('snapshot: the 지표 note mentions 수출입은행 고시 (하루 한 번)', '수출입은행 고시는 하루 한 번' in t, t)
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
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for theme in THEMES:
                for w, hgt in ((360, 800), (1280, 800)):
                    tab_pass(browser, theme, w, hgt)
            for w, hgt in ((390, 844), (768, 1024), (1920, 1080)):
                tab_pass(browser, 'base', w, hgt)
            mode_pass(browser, 'wait', m_wait)
            mode_pass(browser, 'stale', m_stale)
            mode_pass(browser, 'late', m_late)
            mode_pass(browser, 'nobp', m_nobp)
            mode_pass(browser, 'tona', m_tona)
            mode_pass(browser, 'fxfail', m_fxfail, kinds=('rate',), allow=True)
            mode_pass(browser, 'fail', m_fail, kinds=(), allow=True)
            mode_pass(browser, 'gone', m_gone, kinds=(), allow=True)
            mode_pass(browser, 'empty', m_empty, kinds=())
            slow_pass(browser)
            cadence_pass(browser)
            other_tab_pass(browser)
            old_worker_pass(browser)
            snapshot_pass(browser)
            browser.close()
        check('console errors 0, no unexpected 4xx/5xx on /api/koreaexim', not ERR.items and not ERR.http, '; '.join((ERR.items + ERR.http)[:4]))
    finally:
        mock.terminate()
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
