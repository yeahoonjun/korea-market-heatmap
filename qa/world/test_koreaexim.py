#!/usr/bin/env python3
"""QA for the 지표 tab's 수출입은행 고시 boards (AGENTS.md §3-27 끝: the tables of 2026-11-16, user 11:33 "그래 추천대로"; drawn as the LED
board since 2026-11-23, user 12:56 "추천대로하는데 아래 띠는 계속 흐르게" — drafts/led-board.html C on the B look, design.md §2 예외
「LED 전광판」) — src/world UI against the mock Worker (qa/world/mock_api.py, /__mode?kx=…, fixtures/koreaexim.json = the probe's real
values of 2026-11-16).

  python3 scripts/build_page.py && python3 qa/world/test_koreaexim.py

Checks
  tables: ① the 환율 card ends with "수출입은행 고시" — 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 × 매매기준율 · 송금 보낼 때 · 받을 때
    (no colour), ③ the 금리 card ends with "기준금리 · 은행간 금리" — SOFR · ESTR · EURIBOR · TIBOR (TONA only when sent), 3-decimal %,
    bp with colour + sign = direction only; titles on rows; the source line; the waiting / stale / late / no-prev / failure wording;
    an older Worker (404) → absent and not asked again; empty → absent; slow → the list first; the request cadence.
  board: the real text is in every cell and the dots drawn are exactly that text (decoded here with the 5 × 7 font, written out
    independently; every slot a full module of lit + unlit dots); the panel is dark in all four themes; the LED is #fbecd6; the bp
    colours are the 해외 · 지표 palette's dark-ground inks (KH.palette('world', {tone:'dark'}) = --up-text-w-dk) and read ≥ 4.5:1 on
    the panel in every theme and palette; the failed board keeps the data board's height with dim dashes (hidden from screen readers);
    the only focusable thing is each strip's ⏸ key.
  relight (화려하게 only): a new posting while the page is open lights up exactly the cells whose value changed, top to bottom (rows
    40 → 30 → 20 ms apart, all within ~0.6 s); today's posting seen first on this page lights every cell when the board is on screen,
    none when it is off screen; 기본 switches at once.
  strip: keeps moving left at a constant speed (38 / 45 px/s) in 기본 and 화려하게, seamless copies; static, whole and wrapped in 줄이기
    (no key); still when off screen and in a hidden tab; a press on the strip or its key toggles pause (aria-pressed, ⏸ ↔ ▶, kept in
    khm.kxPaused), a mouse over it or keyboard focus on the key holds it while there, a finger gets 44px.
  fit: no horizontal overflow, nothing clipped at 360 / 390 / 768 / 1280 / 1440 / 1920 and in all four themes at 360 and 1280;
    console errors 0.
Port KX_QA_PORT (9041). Screenshots: /tmp/kx_<theme>_<width>.png, /tmp/kx_mode_<mode>.png. Exit code 1 if any check fails.
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
PORT = int(os.environ.get('KX_QA_PORT', 9041))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
KX = json.loads((HERE / 'fixtures/koreaexim.json').read_text(encoding='utf-8'))
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MINUS = '−'
FX_NAMES = [('USD', '원/달러'), ('JPY', '원/엔(100엔)'), ('EUR', '원/유로'), ('CNH', '원/위안')]
LED = 'rgb(251, 236, 214)'

# the 5 × 7 dot font (drafts/led-board.html), top row first — the spec the board must draw
GL = {
    '0': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    '1': ['..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'],
    '2': ['.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'],
    '3': ['.###.', '#...#', '....#', '..##.', '....#', '#...#', '.###.'],
    '4': ['...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'],
    '5': ['#####', '#....', '####.', '....#', '....#', '#...#', '.###.'],
    '6': ['..##.', '.#...', '#....', '####.', '#...#', '#...#', '.###.'],
    '7': ['#####', '....#', '...#.', '..#..', '.#...', '.#...', '.#...'],
    '8': ['.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '.###.'],
    '9': ['.###.', '#...#', '#...#', '.####', '....#', '...#.', '.##..'],
    '.': ['.', '.', '.', '.', '.', '.', '#'],
    ',': ['..', '..', '..', '..', '..', '.#', '#.'],
    '+': ['.....', '..#..', '..#..', '#####', '..#..', '..#..', '.....'],
    MINUS: ['.....', '.....', '.....', '#####', '.....', '.....', '.....'],
    '–': ['.....', '.....', '.....', '.###.', '.....', '.....', '.....'],
}
SLOT_W = {'#': 5, ',': 2, '.': 1}

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


# ── the dots: decode a cell's lit dots back into characters with the font above ──
def dots_of(d):
    return {(int(float(x) - .5), int(float(y) - .5)) for x, y in re.findall(r'M(-?[\d.]+) (-?[\d.]+)h0', d or '')}


def decode(cell):
    """(text the lit dots spell, every slot a complete module of lit + unlit dots, no dot twice)"""
    on, off = dots_of(cell['on']), dots_of(cell['off'])
    x, out, grid = 0, '', set()
    for t in cell['tpl'] or '':
        w = SLOT_W[t]
        rows = tuple(''.join('#' if (x + k, r) in on else '.' for k in range(w)) for r in range(7))
        grid |= {(x + k, r) for k in range(w) for r in range(7)}
        if any('#' in row for row in rows):
            out += next((c for c, g in GL.items() if tuple(g) == rows), '?')
        x += w + 1
    return out, (on | off) == grid and not (on & off)


def rgb(s):
    m = re.match(r'rgba?\(([^)]+)\)', s or '')
    if not m:
        return None
    v = [float(x) for x in re.split(r'[,\s/]+', m.group(1).strip()) if x]
    return v[:3] + [v[3] if len(v) > 3 else 1.0]


def lum(c):
    f = lambda v: (v / 255) / 12.92 if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    x, y = lum(rgb(a)), lum(rgb(b))
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


class Errors:
    def __init__(self):
        self.items, self.http = [], []
        self.allow = False

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))
        page.on('response', lambda r: self.http.append(f'{r.status} {r.url}') if r.status >= 400 and '/api/koreaexim' in r.url and not self.allow else None)


ERR = Errors()


def open_page(browser, url, width, height, theme='base', reduced=False, motion=None, palette_w=None):
    mobile = width < 700
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    pre = f"localStorage.setItem('khm.theme', {json.dumps(json.dumps(theme))});"
    if motion:
        pre += f"localStorage.setItem('khm.motion', {json.dumps(json.dumps(motion))});"
    if palette_w:
        pre += f"localStorage.setItem('khm.paletteW', {json.dumps(json.dumps(palette_w))});"
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__kxPre')) return; sessionStorage.setItem('__kxPre', '1'); " + pre + " })();")
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
  const col = el => (el ? getComputedStyle(el).color : null);
  const one = k => {
    const b = box(k); if (!b) return null;
    const sec = b.closest('.kw-sec'), t = b.querySelector('table'), lb = b.querySelector('.kw-lbd'), st = b.querySelector('.kw-lbs');
    const cells = t ? [...t.querySelectorAll('tbody tr')].map(tr => ({ k: tr.dataset.k, title: tr.title,
      cells: [...tr.children].map(c => {
        const on = c.querySelector('svg.on'), off = c.querySelector('svg.off');
        return { tag: c.tagName, text: c.textContent, cls: c.className, rs: c.getAttribute('rowspan'), tpl: c.dataset.tpl || null, key: c.dataset.key || null,
          v: c.dataset.v || null, on: on ? on.querySelector('path').getAttribute('d') : null, off: off ? off.querySelector('path').getAttribute('d') : null,
          onColor: col(on), filter: on ? getComputedStyle(on).filter : null, lit: c.classList.contains('lit'),
          anim: on ? on.getAnimations().map(a => a.animationName) : [], delay: c.style.getPropertyValue('--kw-lb-d') };
      }) })) : [];
    const head = t ? [...t.querySelectorAll('thead th')].map(th => th.textContent) : [];
    const kids = sec ? [...sec.children].map(c => c.className) : [];
    const foc = [...b.querySelectorAll('button, a, input, select, [tabindex]')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden').map(e => e.className);
    const q = st && st.querySelector('.kw-lbq'), tk = st && st.querySelector('.kw-lbk'), btn = st && st.querySelector('.kw-lbp');
    return { hidden: b.hidden, sec: sec && sec.dataset.g, last: sec && sec.lastElementChild === b, kids, cells, head,
      title: (b.querySelector('.kw-kxt') || {}).textContent || '', meta: (b.querySelector('.kw-kxm') || {}).textContent || '',
      warn: !!b.querySelector('.kw-kxm .kwn'), note: [...b.querySelectorAll('.kw-kxn')].map(p => p.textContent).join(' | '),
      text: b.textContent, tag: (b.querySelector('.kw-kxt') || {}).tagName, labelled: t ? t.getAttribute('aria-labelledby') : null,
      thidden: t ? t.getAttribute('aria-hidden') : null, focusables: foc, num: t ? getComputedStyle(t).fontVariantNumeric : '',
      bg: lb ? getComputedStyle(lb).backgroundColor : null, lab: lb ? col(lb.querySelector('tbody th.nm')) : null,
      lab2: lb ? col(lb.querySelector('thead th:not(.nm)')) : null, boardH: lb ? lb.offsetHeight : 0, tableH: t ? t.offsetHeight : 0,
      p: lb ? lb.style.getPropertyValue('--p') : '',
      strip: st ? { text: q ? q.textContent : '', cls: st.className, warn: !!st.querySelector(':scope > .kwn'), btn: btn ? btn.getAttribute('aria-pressed') : null,
        label: btn ? btn.getAttribute('aria-label') : null, anim: tk ? getComputedStyle(tk).animationName : null, play: tk ? getComputedStyle(tk).animationPlayState : null,
        copies: tk ? [...tk.children].filter(c => c.getClientRects().length).length : 0, hiddenCopies: tk ? [...tk.children].slice(1).every(c => c.getAttribute('aria-hidden') === 'true') : null,
        fits: q ? q.scrollWidth <= st.querySelector('.kw-lbm').clientWidth + 1 : null, color: col(st) } : null };
  };
  const up = getComputedStyle(W).getPropertyValue('--up-text').trim(), dn = getComputedStyle(W).getPropertyValue('--dn-text').trim();
  const norm = c => { const e = document.createElement('i'); e.style.color = c; W.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const dk = KH.palette('world', { tone: 'dark' });
  const rs = getComputedStyle(document.documentElement);
  return { fx: one('fx'), rate: one('rate'), up: norm(up), dn: norm(dn), dkUp: norm(dk.upText), dkDn: norm(dk.dnText), tone: dk.tone,
    cssUp: norm(rs.getPropertyValue('--up-text-w-dk').trim()), cssDn: norm(rs.getPropertyValue('--dn-text-w-dk').trim()),
    fg: getComputedStyle(W.querySelector('.kw-sec') || W).color,
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
    const t = b.querySelector('table'), lb = b.querySelector('.kw-lbd');
    if (t && lb && t.getBoundingClientRect().right > lb.getBoundingClientRect().right + 0.5) out.clip.push(`${b.dataset.kx} table ${t.getBoundingClientRect().right} > board ${lb.getBoundingClientRect().right}`);
    if (lb && (lb.getBoundingClientRect().left < br.left - 0.5 || lb.getBoundingClientRect().right > br.right + 0.5)) out.out.push(b.dataset.kx + ' board outside its place');
    for (const el of b.querySelectorAll('th, td, .kw-kxt, .kw-kxm, .kw-kxn, .kw-lbs, .kw-lbm, .kw-lbp')) {
      if (el.classList.contains('sr') || !el.getClientRects().length) continue;
      const r = el.getBoundingClientRect();
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== 'inline' && !el.classList.contains('kw-lbm')) out.clip.push(`${b.dataset.kx} ${el.tagName}.${el.className} '${el.textContent.slice(0, 20)}'`);
      if (r.right > Math.min(vw, br.right) + 0.5 || r.left < br.left - 0.5) out.out.push(`${b.dataset.kx} ${el.tagName}.${el.className} '${el.textContent.slice(0, 20)}' ${r.left.toFixed(1)}–${r.right.toFixed(1)} vs ${br.left.toFixed(1)}–${br.right.toFixed(1)}`);
    }
  }
  return out;
}"""


def digit_cells(board):
    return [c for row in board['cells'] for c in row['cells'] if c['tpl']]


def check_dots(board, tag, na=False):
    """the lit dots spell the cell's real text (units aside); every slot a full module"""
    bad, cells = [], digit_cells(board)
    for c in cells:
        got, full = decode(c)
        want = c['text'].replace('%', '').replace('bp', '')
        if na or c['text'] in ('', '—'):
            ok = got and set(got) <= {'–', ',', '.'} and '–' in got and 'na' in c['cls'].split()
        else:
            ok = got == want
        if not ok or not full:
            bad.append(f"{c['key']} '{c['text']}' drawn '{got}' full={full}")
    check(f'{tag}: {"dim dashes in every digit cell" if na else "the dots spell each cell real text"} ({len(cells)} cells), every slot a full module of lit + unlit dots',
          cells and not bad, '; '.join(bad[:4]))


def check_tables(r, tag, kx=KX):
    fx, rt = r['fx'], r['rate']
    # ① 환율 card
    ok = fx and not fx['hidden'] and fx['sec'] == 'fx' and fx['last'] and fx['kids'].index('kw-rows') < len(fx['kids']) - 1
    check(f'{tag}: 수출입은행 고시 board at the end of the 환율 card', ok, json.dumps(fx and fx['kids']))
    want = []
    by = {it['code']: it for it in kx['fx']['items']}
    for code, name in FX_NAMES:
        it = by[code]
        want.append([name, f2(it['base']), f2(it['tts']), f2(it['ttb'])])
    got = [[c['text'] for c in row['cells']] for row in fx['cells']]
    check(f'{tag}: real text 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 × 매매기준율 · 송금 보낼 때 · 받을 때', got == want, json.dumps(got, ensure_ascii=False)[:300])
    check_dots(fx, tag + ' 환율')
    check_dots(rt, tag + ' 금리')
    check(f'{tag}: 환율 heads + title (h5, table labelled by it), no meta in the head (the strip carries it)',
          fx['head'] == ['통화', '매매기준율', '송금 보낼 때', '송금 받을 때'] and fx['title'] == '수출입은행 고시' and fx['meta'] == ''
          and fx['tag'] == 'H5' and fx['labelled'] == 'kw-kx-fx', f"{fx['head']} {fx['title']} {fx['meta']}")
    check(f'{tag}: 환율 strip "한국수출입은행 · 11월 16일 (월) 11:04 고시 · 하루 한 번 · 환전 · 송금할 때 참고하는 은행 고시값이에요"',
          fx['strip']['text'] == '한국수출입은행 · 11월 16일 (월) 11:04 고시 · 하루 한 번 · 환전 · 송금할 때 참고하는 은행 고시값이에요', fx['strip']['text'])
    check(f'{tag}: 환율 note = the caveat, not advice', '은행과 우대율마다 달라요' in fx['note'] and '추천' not in fx['note'], fx['note'])
    colours = {c['onColor'] for c in digit_cells(fx)}
    check(f'{tag}: 환율 digits all LED white (no up / down colour)', colours == {LED}, str(colours))
    # ③ 금리 card
    ok = rt and not rt['hidden'] and rt['sec'] == 'rates' and rt['last']
    check(f'{tag}: 기준금리 · 은행간 금리 board at the end of the 금리 card', ok, json.dumps(rt and rt['kids']))
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
        elif bpcls(it['bp']) == 'up' and b['onColor'] != r['dkUp'] or bpcls(it['bp']) == 'dn' and b['onColor'] != r['dkDn']:
            bad.append(f"{it['key']} bp colour {b['onColor']}")
        if it['raw'] not in row['title']:
            bad.append(f"{it['key']} title {row['title']}")
    check(f'{tag}: rate tenor · 3-decimal % · bp (sign + dark-ground colour = direction only) · title with the source value', not bad, '; '.join(bad[:4]))
    fam = [(c['text'], c['rs']) for row in rt['cells'] for c in row['cells'] if c['tag'] == 'TH']
    check(f'{tag}: one family head per group (rowspan), currency beside it', fam == [('SOFR달러', '1'), ('ESTR유로', '1'), ('EURIBOR유로', '4'), ('TIBOR엔', '4')], str(fam))
    check(f'{tag}: rate title + heads 기간 · 금리(%) · 변화(bp), strip says 하루 한 번 · 수출입은행 · the posting',
          rt['head'] == ['이름', '기간', '금리(%)', '변화(bp)'] and rt['title'] == '기준금리 · 은행간 금리' and rt['meta'] == ''
          and rt['strip']['text'].startswith('한국수출입은행 · 11월 16일 (월) 11:04 고시 · 하루 한 번 · 익일은 하루짜리 기준금리'), f"{rt['head']} {rt['strip']['text']}")
    check(f'{tag}: rate note (bp = 0.01%p)', '전 영업일 고시 대비' in rt['note'], rt['note'])
    check(f'{tag}: the only focusable thing is each strip\'s ⏸ key (rows not clickable), tabular figures',
          fx['focusables'] == ['kw-lbp'] and rt['focusables'] == ['kw-lbp'] and 'tabular-nums' in fx['num'] and 'tabular-nums' in rt['num'], f"{fx['focusables']} {rt['focusables']}")
    check(f'{tag}: source line "한국수출입은행 · 하루 한 번" with the posting day', '한국수출입은행 · 하루 한 번' in r['src'] and '11월 16일 (월) 고시' in r['src'], r['src'])


def check_board_colours(r, tag):
    """dark panel in this theme; LED white; bp inks = the palette's dark-ground inks, ≥ 4.5:1 on the panel"""
    fx, rt = r['fx'], r['rate']
    bgs = [fx['bg'], rt['bg']]
    dark = all(rgb(b) and rgb(b)[3] == 1 and lum(rgb(b)) < 0.03 for b in bgs)
    check(f'{tag}: the panel is opaque and dark (L < 0.03) whatever the theme', dark, str(bgs))
    ups = {c['onColor'] for c in digit_cells(rt) if 'up' in c['cls'].split()}
    dns = {c['onColor'] for c in digit_cells(rt) if 'dn' in c['cls'].split()}
    led = {c['onColor'] for c in digit_cells(rt) if not set(c['cls'].split()) & {'up', 'dn', 'flat', 'na'}}
    check(f'{tag}: KH.palette(\'world\', {{tone:\'dark\'}}) = --up-text-w-dk / --dn-text-w-dk = the bp inks on the board',
          r['tone'] == 'dark' and ups == {r['dkUp']} == {r['cssUp']} and dns == {r['dkDn']} == {r['cssDn']} and led == {LED}, f'{ups} {dns} {r["dkUp"]} {r["dkDn"]} {led}')
    cs = {'LED': contrast(LED, rt['bg']), 'up': contrast(r['dkUp'], rt['bg']), 'dn': contrast(r['dkDn'], rt['bg']),
          'names': contrast(rt['lab'], rt['bg']), 'heads': contrast(rt['lab2'], rt['bg']), 'strip': contrast(rt['strip']['color'], rt['bg'])}
    check(f'{tag}: LED · bp up / down · names · heads · strip ≥ 4.5:1 on the panel', all(v >= 4.5 for v in cs.values()), json.dumps({k: round(v, 2) for k, v in cs.items()}))


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
            check(f'{tag}: both boards drawn', r['fx'] and not r['fx']['hidden'] and r['rate'] and len(r['rate']['cells']) == 10 and len(r['fx']['cells']) == 4)
        if w in (360, 1280):
            check_board_colours(r, tag)
        p = float(r['fx']['p'].replace('px', '') or 0)
        check(f'{tag}: one dot pitch for both boards, 1.6 … 3px ({p}px)', r['fx']['p'] == r['rate']['p'] and 1.6 <= p <= 3, f"{r['fx']['p']} {r['rate']['p']}")
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


def palette_pass(browser):
    mode(macro='on', funds='on', kx='on', world='ok')
    for theme in ('base', 'paper', 'glass-dark', 'glass-light'):
        for pw in ('krb', 'global', 'cvd'):
            ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 900, theme, palette_w=pw)
            try:
                wait_kx(page)
                r = page.evaluate(READ_JS)
                rt = r['rate']
                ups = {c['onColor'] for c in digit_cells(rt) if 'up' in c['cls'].split()}
                dns = {c['onColor'] for c in digit_cells(rt) if 'dn' in c['cls'].split()}
                cu, cd = contrast(r['dkUp'], rt['bg']), contrast(r['dkDn'], rt['bg'])
                check(f'{theme} · 해외 palette {pw}: bp inks follow the palette\'s dark-ground pair, ≥ 4.5:1 ({cu:.2f} · {cd:.2f})',
                      ups == {r['dkUp']} and dns == {r['dkDn']} and cu >= 4.5 and cd >= 4.5, f'{ups} {dns}')
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
    check('kx=wait: Friday shown, strip "오늘 고시 전이에요 · 한국수출입은행 · 11월 13일 (금) 고시 · …", note "오늘 고시는 아직 나오지 않았어요", no warning',
          r['fx']['strip']['text'].startswith('오늘 고시 전이에요 · 한국수출입은행 · 11월 13일 (금) 고시 · 하루 한 번') and '오늘 고시는 아직 나오지 않았어요' in r['fx']['note']
          and '오늘 고시는 아직' in r['rate']['note'] and not r['fx']['warn'] and not r['fx']['strip']['warn'], f"{r['fx']['strip']['text']} | {r['fx']['note']}")
    check('kx=wait: source line names Friday', '11월 13일 (금) 고시' in r['src'], r['src'])
    check_dots(r['fx'], 'kx=wait 환율')


def m_stale(r, page):
    check('kx=stale: ! beside the title (+ screen-reader words), ! + "새 값을 확인하지 못했어요" on the strip, the note says it is the last value',
          r['fx']['warn'] and r['rate']['warn'] and '새 값을 확인하지 못했어요' in r['fx']['meta'] and r['fx']['strip']['warn']
          and r['fx']['strip']['text'].startswith('새 값을 확인하지 못했어요 · 한국수출입은행 · 11월 13일 (금) 고시') and '지난 값을 보여 줘요' in r['fx']['note'], r['fx']['strip']['text'])


def m_late(r, page):
    check('kx=late: first seen 13:20 without an empty check before → "11월 16일 (월) 고시 · 13:20 확인" (not "13:20 고시")',
          '· 11월 16일 (월) 고시 · 13:20 확인 ·' in r['fx']['strip']['text'] and '11월 16일 (월) 고시 · 13:20 확인' in r['rate']['strip']['text'], r['fx']['strip']['text'])


def m_nobp(r, page):
    check('kx=nobp: no previous posting → no 변화 column, no bp clause', r['rate']['head'] == ['이름', '기간', '금리(%)'] and '전 영업일' not in r['rate']['note']
          and all(len(row['cells']) <= 3 for row in r['rate']['cells']), str(r['rate']['head']))
    check_dots(r['rate'], 'kx=nobp 금리')


def m_tona(r, page):
    keys = [row['k'] for row in r['rate']['cells']]
    check('kx=tona: TONA 익일 after ESTR when the source sends it', keys[:3] == ['SOFRON', 'ESTRON', 'TONAON'] and 'TONA엔' in r['rate']['text'], str(keys[:4]))


def m_fxfail(r, page):
    fx = r['fx']
    check('kx=fxfail: the 환율 place says it could not load (! + words), its board stays in dim dashes hidden from screen readers, 금리 as usual, every list row still there',
          not fx['hidden'] and '수출입은행 고시 환율을 불러오지 못했어요' in fx['text'] and fx['thidden'] == 'true' and len(fx['cells']) == 4
          and len(r['rate']['cells']) == 10 and r['rows'] >= 30, f"{fx['note']} rows {r['rows']}")
    check_dots(fx, 'kx=fxfail 환율', na=True)
    check('kx=fxfail: the failed board\'s strip stands still (no key) and says when it asks again',
          fx['strip']['anim'] == 'none' and fx['strip']['btn'] is None and fx['strip']['text'] == '한국수출입은행 · 하루 한 번 · 2분 뒤 다시 확인해요' and fx['focusables'] == [], json.dumps(fx['strip'], ensure_ascii=False))


def m_fail(r, page):
    check('kx=fail: both places say so, the rest of the tab untouched', '불러오지 못했어요' in r['fx']['text'] and '불러오지 못했어요' in r['rate']['text']
          and r['rows'] >= 30 and 'funds' in r['secs'] and not r['src'], str(r['secs']))
    check_dots(r['rate'], 'kx=fail 금리', na=True)


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


def height_pass(browser):
    """the failed board keeps the data board's height (dashes, the same rows), so the columns do not move when values come"""
    hs = {}
    for m in ('on', 'fail'):
        get(LIVE + '__reset')
        mode(macro='on', funds='on', kx=m)
        ERR.allow = m == 'fail'
        for w in (360, 1280):
            ctx, page = open_page(browser, LIVE + '#cmdty', w, 900)
            try:
                wait_kx(page)
                r = page.evaluate(READ_JS)
                hs[(m, w)] = (r['fx']['boardH'], r['rate']['boardH'], r['fx']['tableH'], r['rate']['tableH'])
            finally:
                ctx.close()
        ERR.allow = False
    for w in (360, 1280):
        a, b = hs[('on', w)], hs[('fail', w)]
        check(f'{w}: the failed boards keep the data boards\' height (table ±0, board ±2px)', a[2:] == b[2:] and all(abs(x - y) <= 2 for x, y in zip(a[:2], b[:2])), f'on {a} fail {b}')


CELLS_JS = "() => Object.fromEntries([...document.querySelectorAll('#world .kw-kx td.d[data-key]')].map(td => [td.dataset.key, td.dataset.v]))"
LIT_JS = r"""() => [...document.querySelectorAll('#world .kw-kx td.d[data-key]')].filter(td => td.classList.contains('lit')).map(td => ({ k: td.dataset.key,
  d: parseFloat(td.style.getPropertyValue('--kw-lb-d')) || 0, anim: td.querySelector('svg.on').getAnimations().map(a => a.animationName),
  row: [...td.closest('table').querySelectorAll('tbody tr')].indexOf(td.parentElement), dur: parseFloat(getComputedStyle(td.querySelector('svg.on')).animationDuration) * 1000 }))"""
ONSCREEN_JS = "() => [...document.querySelectorAll('#world .kw-kx:not([hidden])')].map(b => { const r = b.getBoundingClientRect(); return [b.dataset.kx, r.top < innerHeight && r.bottom > 0]; })"


def relight_pass(browser, motion):
    """a new posting while the page is open (Friday's → today's): only the changed cells relight, 화려하게 only"""
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='wait')
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 1600, motion=motion)
    try:
        wait_kx(page)
        on = dict(page.evaluate(ONSCREEN_JS))
        before, lit0 = page.evaluate(CELLS_JS), page.evaluate(LIT_JS)
        check(f'{motion}: Friday\'s posting on the first draw → nothing relights (not today)', on.get('fx') and on.get('rate') and not lit0, f'{on} {len(lit0)}')
        mode(kx='on')
        page.evaluate("() => { const n = Date.now; Date.now = () => n.call(Date) + 11 * 60e3; KH.refresh(); }")   # 11 min later: the 10-min ask is due
        page.wait_for_function("() => { const td = document.querySelector('#world .kw-kx[data-kx=\"fx\"] td.d[data-key=\"USDbase\"]'); return td && td.dataset.v === '1,333.70'; }", timeout=8000)
        page.wait_for_timeout(60)
        after, lit = page.evaluate(CELLS_JS), page.evaluate(LIT_JS)
        changed = {k for k, v in after.items() if before.get(k) != v}
        keys = {x['k'] for x in lit}
        if motion == 'fancy':
            check(f'fancy: the new posting relights exactly the cells that changed ({len(changed)} of {len(after)}), the rest stay lit',
                  changed and keys == changed and len(changed) < len(after), f'lit-not-changed {sorted(keys - changed)[:4]} changed-not-lit {sorted(changed - keys)[:4]}')
            check('fancy: each relit cell runs the 9-step reveal (kwLbLit) on its lit dots', lit and all('kwLbLit' in x['anim'] for x in lit), str([x['anim'] for x in lit][:3]))
            fxk = ('USD', 'JPY', 'EUR', 'CNH')
            order = True
            for grp in ([x for x in lit if x['k'][:3] in fxk], [x for x in lit if x['k'][:3] not in fxk]):
                for a in grp:
                    for b in grp:
                        if a['row'] < b['row'] and not a['d'] < b['d'] or a['row'] == b['row'] and a['d'] != b['d']:
                            order = False
            end = max(x['d'] + x['dur'] for x in lit)
            check(f'fancy: top to bottom (a lower row starts later), all done within ~0.6 s ({end:.0f} ms)', order and end <= 650, str(sorted((x['row'], x['d']) for x in lit)[:12]))
            # the list rebuilds its shells right away (here: the sort switches, the way a column re-balance does): the relight under way
            # carries over to the new cells
            page.evaluate("() => { document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbd').__old = 1; document.querySelector('#world .kw-seg[data-kw=\"sort\"] button[data-v=\"pct\"]').click(); }")
            page.wait_for_timeout(120)
            lit2 = page.evaluate(LIT_JS)
            fresh = page.evaluate("() => !document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbd').__old")
            check('fancy: a column rebuild mid-relight carries it over — the same cells keep relighting on the new board, picking up where they were',
                  fresh and {x['k'] for x in lit2} == changed and all('kwLbLit' in x['anim'] for x in lit2) and max(x['d'] for x in lit2) < max(x['d'] for x in lit),
                  f'rebuilt {fresh} lit {len(lit2)} d {max([x["d"] for x in lit2] or [0])} < {max(x["d"] for x in lit)}')
            page.wait_for_timeout(800)
            run = page.evaluate("() => [...document.querySelectorAll('#world .kw-kx td.lit svg.on')].filter(s => s.getAnimations().some(a => a.playState === 'running')).length")
            check('fancy: the relight has finished after 0.8 s (nothing keeps moving)', run == 0, str(run))
        else:
            check(f'{motion}: the new posting switches at once — no relight', changed and not lit, f'{len(changed)} changed, {len(lit)} lit')
    finally:
        ctx.close()


def first_pass(browser):
    """today's posting seen first on this page: every cell relights when the board is on screen (화려하게), none when it is not"""
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    for w, hgt in ((1280, 1600), (360, 500)):
        ctx, page = open_page(browser, LIVE + '#cmdty', w, hgt, motion='fancy')
        try:
            wait_kx(page)
            on, lit, cells = dict(page.evaluate(ONSCREEN_JS)), page.evaluate(LIT_JS), page.evaluate(CELLS_JS)
            want = {k for k in cells if on.get('fx' if k[:3] in ('USD', 'JPY', 'EUR', 'CNH') else 'rate')}
            got = {x['k'] for x in lit}
            check(f'fancy {w}×{hgt}: today\'s posting, first draw on this page → the boards on screen relight whole ({len(got)}), off-screen ones do not',
                  got == want, f'on {on} lit {len(got)} want {len(want)}')
        finally:
            ctx.close()


STRIP_JS = r"""async (k) => {
  const s = document.querySelector(`#world .kw-kx[data-kx="${k}"] .kw-lbs`), t = s.querySelector('.kw-lbk');
  const x = () => new DOMMatrixReadOnly(getComputedStyle(t).transform).m41;
  const a = x(), t0 = performance.now();
  await new Promise(r => setTimeout(r, 1000));
  const b = x(), dt = (performance.now() - t0) / 1000;
  const q = t.firstElementChild, W = q.offsetWidth, vw = s.querySelector('.kw-lbm').clientWidth;
  let dx = a - b; if (dx < 0) dx += W;
  return { a, b, speed: dx / dt, W, vw, d: t.style.getPropertyValue('--kw-lbs-d'), n: t.children.length, same: [...t.children].every(c => c.textContent === q.textContent),
    play: getComputedStyle(t).animationPlayState, cls: s.className, pressed: s.querySelector('.kw-lbp').getAttribute('aria-pressed') };
}"""
STILL_JS = r"""async (k) => {
  const t = document.querySelector(`#world .kw-kx[data-kx="${k}"] .kw-lbk`);
  const x = () => new DOMMatrixReadOnly(getComputedStyle(t).transform).m41;
  const a = x(); await new Promise(r => setTimeout(r, 400)); const b = x();
  const s = t.closest('.kw-lbs'), ic = [...s.querySelectorAll('.kw-lbp svg')].map(v => getComputedStyle(v).opacity);
  return { moved: Math.abs(a - b), play: getComputedStyle(t).animationPlayState, cls: s.className, pressed: s.querySelector('.kw-lbp').getAttribute('aria-pressed'), icons: ic };
}"""


def strip_pass(browser, motion):
    """the strip keeps moving (기본 · 화려하게), constant px/s, seamless; pauses off screen / hidden / by the key / held by hover · focus"""
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 1600, motion=motion)
    try:
        wait_kx(page)
        page.mouse.move(2, 2)
        r = page.evaluate(STRIP_JS, 'fx')
        tag = f'strip {motion} 1280'
        check(f'{tag}: moves left at a constant ~45 px/s ({r["speed"]:.1f})', r['play'] == 'running' and 36 <= r['speed'] <= 54, json.dumps(r)[:200])
        check(f'{tag}: seamless loop — {r["n"]} identical copies cover the viewport + one, the period is one copy\'s width',
              r['same'] and r['n'] >= 2 and r['n'] * r['W'] >= r['vw'] + r['W'] and abs(float(r['d'].replace('px', '')) + r['W']) < 1, f"n {r['n']} W {r['W']} vw {r['vw']} d {r['d']}")
        sel = '#world .kw-kx[data-kx="fx"] .kw-lbs'
        # a press on the strip (not the key) → paused, ▶ shown; again → moving
        page.click(sel + ' .kw-lbm')
        page.wait_for_timeout(500)
        s = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: a press on the strip pauses it — aria-pressed true, ▶ shown, ⏸ hidden, it stands still',
              s['pressed'] == 'true' and s['play'] == 'paused' and s['moved'] < 0.5 and s['icons'] == ['0', '1'], json.dumps(s))
        rr = page.evaluate("() => [...document.querySelectorAll('#world .kw-lbp')].map(b => b.getAttribute('aria-pressed'))")
        check(f'{tag}: one pause for both strips (the other key says pressed too)', rr == ['true', 'true'], str(rr))
        page.click(sel + ' .kw-lbm')
        page.wait_for_timeout(500)
        s = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: a second press resumes it even under the mouse — aria-pressed false, ⏸ shown, moving',
              s['pressed'] == 'false' and s['play'] == 'running' and s['moved'] > 3 and s['icons'] == ['1', '0'], json.dumps(s))
        page.click(sel + ' .kw-lbp')
        page.wait_for_timeout(300)
        p1 = page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbp').getAttribute('aria-pressed')")
        page.click(sel + ' .kw-lbp')
        page.wait_for_timeout(300)
        p2 = page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbp').getAttribute('aria-pressed')")
        check(f'{tag}: the ⏸ key itself toggles (button, label "고시 띠 멈춤")', p1 == 'true' and p2 == 'false'
              and page.evaluate("() => document.querySelector('#world .kw-lbp').getAttribute('aria-label')") == '고시 띠 멈춤', f'{p1} {p2}')
        # a mouse over it holds it; leaving lets it go
        page.mouse.move(2, 2); page.wait_for_timeout(100)
        page.hover(sel + ' .kw-lbm'); page.wait_for_timeout(200)
        s = page.evaluate(STILL_JS, 'fx')
        page.mouse.move(2, 2); page.wait_for_timeout(200)
        s2 = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: a mouse over the strip holds it (not pressed), leaving lets it move again', s['play'] == 'paused' and 'hd' in s['cls'].split() and s['pressed'] == 'false'
              and s2['play'] == 'running' and 'hd' not in s2['cls'].split(), f"{s['cls']} / {s2['cls']}")
        # keyboard: Tab onto the key → held; Space → paused (the hold lets go); Space → moving with the focus still there
        page.evaluate("() => { const rows = document.querySelectorAll('#world .kw-sec[data-g=\"fx\"] .kw-lr'); rows[rows.length - 1].focus(); }")
        page.keyboard.press('Tab'); page.wait_for_timeout(200)
        f = page.evaluate("() => [document.activeElement.className, document.activeElement.closest('.kw-kx') && document.activeElement.closest('.kw-kx').dataset.kx]")
        s = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: Tab reaches the strip\'s key (after the 환율 rows) and keyboard focus holds the strip', f == ['kw-lbp', 'fx'] and s['play'] == 'paused' and 'hd' in s['cls'].split(), f'{f} {s["cls"]}')
        page.keyboard.press('Space'); page.wait_for_timeout(300)
        s = page.evaluate(STILL_JS, 'fx')
        page.keyboard.press('Space'); page.wait_for_timeout(300)
        s2 = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: Space toggles pause from the keyboard; resuming moves at once with the focus still there',
              s['pressed'] == 'true' and s['play'] == 'paused' and s2['pressed'] == 'false' and s2['play'] == 'running' and s2['moved'] > 3, f"{s['pressed']} {s2['pressed']} {s2['play']}")
        page.evaluate("() => document.activeElement.blur()")
        # off screen → still; back → moving (a short window, so the page scrolls)
        page.set_viewport_size({'width': 1280, 'height': 560}); page.wait_for_timeout(300)
        page.evaluate("() => { const r = document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbs').getBoundingClientRect(); scrollBy(0, r.bottom + 40); }"); page.wait_for_timeout(400)
        box = page.evaluate("() => { const r = document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbs').getBoundingClientRect(); return r.bottom < 0 || r.top > innerHeight; }")
        s = page.evaluate(STILL_JS, 'fx')
        page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbs').scrollIntoView({block: 'center'})"); page.wait_for_timeout(400)
        s2 = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: off screen it stands still (IntersectionObserver), back on screen it moves', box and s['play'] == 'paused' and 'off' in s['cls'].split()
              and s2['play'] == 'running' and 'off' not in s2['cls'].split(), f"{box} {s['cls']} / {s2['cls']}")
        # a hidden tab → still
        page.evaluate("""() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
          Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'}); document.dispatchEvent(new Event('visibilitychange')); }""")
        s = page.evaluate(STILL_JS, 'fx')
        page.evaluate("() => { delete document.hidden; delete document.visibilityState; document.dispatchEvent(new Event('visibilitychange')); }")
        page.wait_for_timeout(200)
        s2 = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: a hidden tab stops it, visible again it moves', s['play'] == 'paused' and 'hid' in s['cls'].split() and s2['play'] == 'running', f"{s['cls']} / {s2['cls']}")
        # kept: paused, reload → still paused
        page.click(sel + ' .kw-lbm'); page.wait_for_timeout(200)
        page.reload(); wait_kx(page)
        s = page.evaluate(STILL_JS, 'fx')
        check(f'{tag}: the pause is kept on this device (khm.kxPaused) like the ticker\'s ⏸', s['pressed'] == 'true' and s['play'] == 'paused', json.dumps(s))
        page.click(sel + ' .kw-lbp'); page.wait_for_timeout(200)
    finally:
        ctx.close()


def strip_phone_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844, motion='standard')
    try:
        wait_kx(page)
        page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbs').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(400)
        r = page.evaluate(STRIP_JS, 'fx')
        check(f'strip standard 390: moves at the phone speed ~38 px/s ({r["speed"]:.1f})', r['play'] == 'running' and 30 <= r['speed'] <= 46, json.dumps(r)[:200])
        coarse = page.evaluate("matchMedia('(pointer:coarse)').matches")
        box = page.evaluate("() => { const r = document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbs').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")
        page.touchscreen.tap(box[0] + box[2] / 2, box[1] + box[3] + 4)       # 4px under the strip: inside the 44px finger band
        page.wait_for_timeout(300)
        p1 = page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbp').getAttribute('aria-pressed')")
        page.touchscreen.tap(box[0] + box[2] / 2, box[1] + box[3] / 2)
        page.wait_for_timeout(300)
        p2 = page.evaluate("() => document.querySelector('#world .kw-kx[data-kx=\"fx\"] .kw-lbp').getAttribute('aria-pressed')")
        check(f'strip 390: a tap toggles pause — also 4px under the {box[3]:.0f}px strip (44px finger band)', coarse and p1 == 'true' and p2 == 'false', f'coarse {coarse} {p1} {p2}')
    finally:
        ctx.close()


def reduced_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='on')
    for w in (360, 1280):
        ctx, page = open_page(browser, LIVE + '#cmdty', w, 1600, reduced=True)
        try:
            wait_kx(page)
            r = page.evaluate(READ_JS)
            mo = page.evaluate("KH.motion()")
            st = [r['fx']['strip'], r['rate']['strip']]
            check(f'줄이기 {w}: the strips stand still, one copy, whole (wrapped), no key — nothing to pause',
                  mo == 'reduced' and all(s['anim'] == 'none' and s['copies'] == 1 and s['fits'] for s in st) and r['fx']['focusables'] == [] and r['rate']['focusables'] == [],
                  json.dumps(st, ensure_ascii=False)[:300])
            check(f'줄이기 {w}: no relight (today\'s posting on a first draw)', not page.evaluate(LIT_JS))
            fit = page.evaluate(FIT_JS)
            check(f'줄이기 {w}: no overflow', fit['over'] <= 0 and not fit['clip'] and not fit['out'], json.dumps(fit, ensure_ascii=False)[:200])
            page.query_selector('#world .kw-kx[data-kx="fx"]').screenshot(path=f'/tmp/kx_reduced_{w}.png')
        finally:
            ctx.close()


def slow_pass(browser):
    get(LIVE + '__reset')
    mode(macro='on', funds='on', kx='slow')
    ctx, page = open_page(browser, LIVE + '#cmdty', 360, 800)
    try:
        page.wait_for_selector('#world .kw-lr', timeout=10000)
        page.wait_for_timeout(300)
        early = page.evaluate("[...document.querySelectorAll('#world .kw-kx')].map(b => b.hidden)")
        rows = page.evaluate("document.querySelectorAll('#world .kw-lr').length")
        check('kx=slow: the list is drawn before the 고시 arrives (boards hidden meanwhile)', rows >= 30 and early == [True, True], f'{rows} {early}')
        wait_kx(page)
        check('kx=slow: both boards join when it arrives', True)
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
        check('cadence: back to 지표 within 10 min → no new ask, boards still there', stats().get('kx:fx', 0) == 1)
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
        check('해외 tab: no 고시 board, /api/koreaexim not asked', not page.query_selector('#world .kw-kx') and not st.get('kx:fx') and not st.get('kx:rate'), json.dumps(st)[:200])
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
        check('older Worker without 환율 · 금리: no 고시 board and no ask', not page.query_selector('#world .kw-kx') and not st.get('kx:fx'), json.dumps(st)[:200])
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
            for w, hgt in ((390, 844), (768, 1024), (1440, 900), (1920, 1080)):
                tab_pass(browser, 'base', w, hgt)
            palette_pass(browser)
            height_pass(browser)
            relight_pass(browser, 'fancy')
            relight_pass(browser, 'standard')
            first_pass(browser)
            strip_pass(browser, 'standard')
            strip_pass(browser, 'fancy')
            strip_phone_pass(browser)
            reduced_pass(browser)
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
