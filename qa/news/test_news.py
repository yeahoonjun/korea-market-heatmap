#!/usr/bin/env python3
"""QA for the 시장 뉴스 panel (src/news, docs/standards/news.md §12) on the built pages.

  python3 scripts/build_page.py && python3 qa/news/test_news.py [--shots] [--only=design]

Starts qa/news/mock_api.py on NEWS_QA_PORT (default 9050 — the ux/std-news range 9050–9059; serves web/ + /api/news from the sanitized
fixtures) and stops it at the end (fuser -k). Section 13 checks the design standard in the browser (design.md, ux/std-news): sizes from the
tokens, the title underline on KH.ui.seg, the 더보기 fold (the list box grows, what is below moves once), a chip's % swapping in place,
! = --fail-dot, and the glass card material kept. Section 14 checks the ↻ 새로 받기 key of the card head (size, states, 10 s guard).
--shots also writes /tmp/news_*.png (1280 · 1920 base + glass, 390 card + expanded). Exit 1 if any check fails.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('NEWS_QA_PORT', 9050))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SIZES = [(360, 740), (390, 844), (768, 1024), (1280, 800), (1920, 1080)]
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SHOTS = '--shots' in sys.argv
ONLY = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--only=')), '')   # --only=design | refresh: section 13 | 14 alone
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' else ''), flush=True)


def mock(path):
    with NOPROXY.open(LIVE.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


def mode(m):
    mock('/__reset')
    mock('/__mode?news=' + m)


class Errors:
    def __init__(self):
        self.items = []
        self.allow = []

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' and not any(a in m.text for a in self.allow) else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


def open_page(br, url, w, h, theme='base', motion='standard', errors=None, clock=False):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    ctx.add_init_script("try{localStorage.setItem('khm.theme', %s);localStorage.setItem('khm.motion', %s);localStorage.setItem('khm.tickerPaused','true')}catch(e){}"
                        % (json.dumps(json.dumps(theme)), json.dumps(json.dumps(motion))))
    pg = ctx.new_page()
    if clock:
        pg.clock.install()
    if errors is not None:
        errors.attach(pg)
    pg.goto(url)
    pg.wait_for_timeout(1200)
    return ctx, pg


def to_news(pg, settle=900):
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})")
    pg.wait_for_selector('#news .nw-row:not(.skel), #news .nw-msg', timeout=8000)
    pg.wait_for_timeout(settle)


GEO_JS = r"""() => {
  const n = document.getElementById('news'), side = document.querySelector('main.layout > .side'), list = n.querySelector('.nw-list');
  const R = e => e.getBoundingClientRect(), Y = e => R(e).top + scrollY;
  const rows = [...n.querySelectorAll('.nw-row:not(.skel)')];
  return { top: Y(n), bottom: R(n).bottom + scrollY, sideEnd: R(side.lastElementChild).bottom + scrollY, legendEnd: R(document.getElementById('legend')).bottom + scrollY,
    listH: list.getBoundingClientRect().height, rh: parseFloat(getComputedStyle(n).getPropertyValue('--nw-rh')) || 0, rows: rows.length, two: list.classList.contains('c2'),
    perCol: list.classList.contains('c2') ? Math.ceil(rows.length / 2) : rows.length, cardH: n.offsetHeight, cardW: n.clientWidth,
    pageOver: document.documentElement.scrollWidth - document.documentElement.clientWidth, cardOver: n.scrollWidth - n.clientWidth,
    rowOver: rows.filter(r => r.scrollWidth > r.clientWidth + 1).length,
    bad: /\bnull\b|\bundefined\b|\bNaN\b/.test(n.textContent + ' ' + document.getElementById('foot').textContent) };
}"""

CONTRAST_JS = r"""() => {
  const P = s => { const m = s && s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(x => parseFloat(x)); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const L = c => c.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
  const over = (top, bot) => { const a = top[3]; return [0, 1, 2].map(i => top[i] * a + bot[i] * (1 - a)).concat(1); };
  const CR = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  function bgs(el) {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      layers.push({ grads: [...cs.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map(m => P(m[0])), col: P(cs.backgroundColor) });
      if (layers[layers.length - 1].col && layers[layers.length - 1].col[3] >= 1) break;
    }
    let outs = [[0, 0, 0, 1]];
    for (const ly of layers.reverse()) {
      outs = outs.map(b => ly.col && ly.col[3] > 0 ? over(ly.col, b) : b);
      if (ly.grads.length) outs = outs.flatMap(b => ly.grads.map(g => over(g, b)));
    }
    return outs;
  }
  const sel = ['#news h2', '#news .nw-tabs > button', '#news .nw-at span', '#news .nw-row time', '#news .nw-src', '#news .nw-tt a', '#news .nw-chip',
    '#news .nw-chip b', '#news .nw-ft small', '#news .nw-note > span', '#news .nw-msg b', '#news .nw-msg small', '#news .nw-kbtn .kl.on', '#news .nw-only',
    '#news .nw-only .nw-n', '#news .nw-moren', '#foot-news'];
  const res = {};
  for (const s of sel) for (const el of document.querySelectorAll(s)) {
    if (!el.offsetWidth || el.closest('[aria-disabled="true"]') || el.closest('.skel')) continue;
    if (el.closest('[aria-hidden="true"]') && !el.matches('.nw-moren')) continue;
    const fg = P(getComputedStyle(el).color); if (!fg || !(el.textContent || '').trim()) continue;
    let worst = 99; for (const b of bgs(el)) worst = Math.min(worst, CR(over(fg, b), b));
    if (!(s in res) || worst < res[s].v) res[s] = { v: Math.round(worst * 100) / 100, t: (el.textContent || '').trim().slice(0, 14) };
  }
  return res;
}"""


def run(br):
    E = Errors()

    # ── 1 · five widths × four themes: overflow, console, "null" text, rows ──
    mode('drift')                                     # the top headline names 삼성전자: chips present in every run
    for w, h in SIZES:
        for th in THEMES:
            E.items = []
            ctx, pg = open_page(br, LIVE, w, h, th, errors=E)
            to_news(pg)
            g = pg.evaluate(GEO_JS)
            ok = g['pageOver'] == 0 and g['cardOver'] <= 0 and g['rowOver'] == 0 and not g['bad'] and not E.items and g['rows'] > 0
            check(f'{w}x{h} {th}: overflow 0 · console 0 · no null/NaN · rows', ok,
                  f"page {g['pageOver']} card {g['cardOver']} rows-over {g['rowOver']} bad {g['bad']} rows {g['rows']} err {E.items[:2]}")
            ctx.close()

    # ── 2 · fill rule (PC): news ends at the side column's end, or holds the minimum 5 rows (per column) ──
    mode('ok')
    for w, h in [(1280, 720), (1280, 800), (1440, 900), (1920, 1080), (1920, 1200), (1100, 800)]:
        ctx, pg = open_page(br, LIVE, w, h)
        pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(500)
        g = pg.evaluate(GEO_JS)
        whole = g['perCol'] * g['rh'] <= g['listH'] + 1 and g['listH'] - g['perCol'] * g['rh'] < g['rh']   # whole rows only: no room for one more
        fills = abs(g['bottom'] - g['sideEnd']) <= 1.5
        ok = (fills or g['perCol'] == 5) and g['perCol'] >= 5 and whole and abs(g['top'] - (g['legendEnd'] + 14)) <= 1.5
        check(f'fill {w}x{h}: news {g["top"]:.0f}–{g["bottom"]:.0f}, side end {g["sideEnd"]:.0f}, {g["perCol"]} rows' + (' × 2' if g['two'] else ''), ok,
              f"Δ {g['bottom'] - g['sideEnd']:+.0f}, top − legend {g['top'] - g['legendEnd']:.0f}, whole rows {whole}")
        if w == 1920:
            check(f'two columns at {w} (card {g["cardW"]} ≥ 1200)', g['two'])
        if w == 1100:
            check('one column under a 1200 px card', not g['two'])
        ctx.close()
    # side cards growing (눈에 띄는 종목 더보기) → the news refits to the new side end
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(400)
    before = pg.evaluate(GEO_JS)
    pg.click('#movers .more'); pg.wait_for_timeout(700)
    after = pg.evaluate(GEO_JS)
    check('side grows (movers 더보기) → news refits to the side end', after['sideEnd'] > before['sideEnd'] + 100 and abs(after['bottom'] - after['sideEnd']) <= 1.5 and after['rows'] > before['rows'],
          f"side {before['sideEnd']:.0f}→{after['sideEnd']:.0f}, news end {after['bottom']:.0f}, rows {before['rows']}→{after['rows']}")
    ctx.close()

    # ── 3 · contrast per theme (chips, note line, state messages) ──
    for th in THEMES:
        worst = {}
        for m in ('drift', 'stale'):
            mode(m)
            ctx, pg = open_page(br, LIVE, 1440, 900, th)
            to_news(pg)
            if m == 'drift':
                pg.click('#news .nw-only'); pg.wait_for_timeout(300)
            for k, v in pg.evaluate(CONTRAST_JS).items():
                if k not in worst or v['v'] < worst[k]['v']:
                    worst[k] = v
            ctx.close()
        mode('empty')
        ctx, pg = open_page(br, LIVE, 1440, 900, th); to_news(pg)
        for k, v in pg.evaluate(CONTRAST_JS).items():
            if k not in worst or v['v'] < worst[k]['v']:
                worst[k] = v
        ctx.close()
        lo = min(worst.items(), key=lambda kv: kv[1]['v'])
        below = {k: v['v'] for k, v in worst.items() if v['v'] < 4.5}
        check(f'contrast {th} ≥ 4.5 (lowest {lo[1]["v"]} {lo[0]})', not below, json.dumps(below, ensure_ascii=False))

    # ── 4 · name chips: the page's marks = match.js on the same candidates; hover → one tile lit, then cleared ──
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    r = pg.evaluate("""() => { const rows = [...document.querySelectorAll('#news .nw-row')];
      const idx = KHNewsMatch.build(KH.stocks().filter(r => /0$/.test(r.c)).map(r => ({c: r.c, n: r.n})));
      let same = 0, diff = [];
      for (const li of rows) { const t = li.querySelector('.nw-tt a').textContent, m = KHNewsMatch.match(t, idx);
        const want = [...new Set(m.marks.flatMap(x => x.codes))].join(','), got = li.dataset.codes || '';
        if (want === got) same++; else diff.push(t + ' ' + want + ' / ' + got); }
      const first = rows[0], chip = first.querySelector('.nw-chip');
      return { n: rows.length, same, diff, firstCodes: first.dataset.codes, chip: chip && chip.textContent, chipLabel: chip && chip.getAttribute('aria-label'),
        marks: [...first.querySelectorAll('mark')].map(m => m.textContent), quote: KH.quote('005930').r }; }""")
    check('every row marks what match.js finds on KH.stocks()', r['same'] == r['n'] and r['n'] > 0, f"{r['same']}/{r['n']} {r['diff'][:2]}")
    check('chip = name + today\'s % from KH.quote (map value)', r['firstCodes'] == '005930' and r['chip'] and r['chip'].startswith('삼성전자') and r['chip'].endswith('%')
          and ('+' if r['quote'] > 0 else '−' if r['quote'] < 0 else '') + f"{abs(r['quote']):.2f}%" in r['chip'], f"{r['chip']} quote {r['quote']}")
    check('headline name has a dotted underline (mark), the chip says 빠른 보기', r['marks'] == ['삼성전자'] and r['chipLabel'].endswith('· 빠른 보기'), r['chipLabel'])
    pg.hover('#news .nw-row:first-child .nw-tt'); pg.wait_for_timeout(250)
    lit = pg.evaluate("() => ({ on: [...document.querySelectorAll('#map .tile.nhl')].map(t => t.dataset.c), dim: document.querySelectorAll('#map .tile.ndim').length, all: document.querySelectorAll('#map .tile').length })")
    check('hover a row → exactly that tile lit, the rest dimmed', lit['on'] == ['005930'] and lit['dim'] == lit['all'] - 1, lit)
    pg.mouse.move(5, 5); pg.wait_for_timeout(250)
    gone = pg.evaluate("() => document.querySelectorAll('#map .tile.nhl, #map .tile.ndim').length")
    check('pointer leaves → highlight cleared', gone == 0, gone)
    # search wins over the news highlight
    pg.fill('#q', '현대'); pg.wait_for_timeout(200)
    pg.hover('#news .nw-row:first-child .nw-tt'); pg.wait_for_timeout(200)
    s = pg.evaluate("() => ({ n: document.querySelectorAll('#map .tile.nhl, #map .tile.ndim').length, dim: document.querySelectorAll('#map .tile.dim').length })")
    check('search highlight wins (news highlight weaker)', s['n'] == 0 and s['dim'] > 0, s)
    pg.fill('#q', ''); pg.keyboard.press('Escape'); pg.mouse.move(5, 5); pg.wait_for_timeout(200)
    # keyboard: focus on the row link lights it too; leaving clears
    pg.focus('#news .nw-row:first-child .nw-tt a'); pg.wait_for_timeout(150)
    k1 = pg.evaluate("() => [...document.querySelectorAll('#map .tile.nhl')].map(t => t.dataset.c)")
    pg.focus('#news .nw-only'); pg.wait_for_timeout(150)
    k2 = pg.evaluate("() => document.querySelectorAll('#map .tile.nhl, #map .tile.ndim').length")
    check('keyboard focus on a row lights it, leaving clears', k1 == ['005930'] and k2 == 0, f'{k1} / {k2}')
    # chip → quick view (the map tile's sheet), Esc closes and focus returns to the chip
    pg.focus('#news .nw-row:first-child .nw-chip'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
    q = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), label: document.getElementById('sheet').getAttribute('aria-label'), sel: [...document.querySelectorAll('#map .tile.sel')].map(t => t.dataset.c), stock: !!(window.KHStock && KHStock.isOpen && KHStock.isOpen()) })")
    check('chip Enter → the quick view (sheet), not the stock page', q['open'] and q['label'] == '삼성전자 상세' and q['sel'] == ['005930'] and not q['stock'], q)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    f = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), focus: document.activeElement.classList.contains('nw-chip') && document.activeElement.dataset.c })")
    check('Esc closes the quick view, focus back on the chip', not f['open'] and f['focus'] == '005930', f)
    check('no console errors (chips · hover · quick view)', not E.items, E.items[:3]); E.items = []
    ctx.close()

    # ── 5 · keyboard order, focus ring, links ──
    mode('stale')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    pg.focus('#news .nw-tabs button'); seq = []
    for _ in range(9):
        seq.append(pg.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a);
          const k = a.closest('.nw-tabs') ? 'tab' : a.classList.contains('nw-only') ? 'only' : a.closest('.nw-note') ? 'retry' : a.closest('.nw-tt') ? 'link' : a.classList.contains('nw-chip') ? 'chip' : a.classList.contains('nw-more') ? 'more' : a.tagName;
          return [k, cs.outlineStyle !== 'none' ? parseFloat(cs.outlineWidth) : 0]; }"""))
        pg.keyboard.press('Tab')
    kinds = [s[0] for s in seq]
    check('Tab order: tabs → 지도 종목 칩 → 다시 시도 → row links', kinds[:7] == ['tab', 'tab', 'tab', 'tab', 'only', 'retry', 'link'], kinds)
    check('focus ring 3px on every stop', all(s[1] == 3 for s in seq), [s[1] for s in seq])
    links = pg.evaluate("() => [...document.querySelectorAll('#news a')].map(a => [a.target, a.rel, a.href.slice(0, 8), a.getAttribute('aria-label') || ''])")
    check('every headline: one link, new tab, rel noopener, https, label "— 언론사, 새 탭에서 열려요"', links and all(l[0] == '_blank' and 'noopener' in l[1] and l[2] == 'https://' and l[3].endswith('새 탭에서 열려요') for l in links), len(links))
    ctx.close()

    # ── 6 · tabs · only-chip · 더보기: card height and key width stay put; Q3 tabs; credit lines ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    hs, srcs = [], {}
    for k in ('all', 'einfomax', 'hankyung', 'mk'):
        pg.click(f'#news .nw-tabs button[data-k="{k}"]'); pg.wait_for_timeout(150)
        st = pg.evaluate("() => ({ h: document.getElementById('news').offsetHeight, src: [...new Set([...document.querySelectorAll('#news .nw-row')].map(r => r.querySelector('.nw-src').textContent))], badge: getComputedStyle(document.querySelector('#news .nw-row .nw-src')).display })")
        hs.append(st['h']); srcs[k] = st
    check('card height the same on every tab', len(set(hs)) == 1, hs)
    check('outlet tab shows only that outlet, badge hidden there', srcs['hankyung']['src'] == ['한국경제'] and srcs['hankyung']['badge'] == 'none' and srcs['all']['badge'] != 'none')
    pg.click('#news .nw-tabs button[data-k="all"]')
    w0 = pg.evaluate("document.querySelector('#news .nw-more').offsetWidth")
    pg.click('#news .nw-more'); pg.wait_for_timeout(400)
    o = pg.evaluate("() => ({ rows: document.querySelectorAll('#news .nw-row').length, lab: document.querySelector('#news .nw-more').getAttribute('aria-label'), exp: document.querySelector('#news .nw-more').getAttribute('aria-expanded'), w: document.querySelector('#news .nw-more').offsetWidth })")
    check('더보기 → 30 rows, 접기, aria-expanded, key width unchanged', o['rows'] == 30 and o['lab'] == '접기' and o['exp'] == 'true' and o['w'] == w0, f"{o} w0 {w0}")
    pg.click('#news .nw-tabs button[data-k="mk"]'); pg.wait_for_timeout(150)
    o2 = pg.evaluate("() => ({ rows: document.querySelectorAll('#news .nw-row').length, exp: document.querySelector('#news .nw-more').getAttribute('aria-expanded') })")
    check('펼침 stays when the tab changes', o2['rows'] == 30 and o2['exp'] == 'true', o2)
    pg.click('#news .nw-more'); pg.click('#news .nw-tabs button[data-k="all"]'); pg.wait_for_timeout(150)
    pg.click('#news .nw-only'); pg.wait_for_timeout(200)
    # the expected count comes from the data (the fixture's headlines × the stocks on today's universe — it moves with the daily refresh)
    oc = pg.evaluate("""async () => { const j = await (await fetch('api/news', { cache: 'no-store' })).json();
      const idx = KHNewsMatch.build(KH.stocks().filter(r => /0$/.test(r.c)).map(r => ({ c: r.c, n: r.n })));
      const want = j.items.filter(it => KHNewsMatch.match(it.title, idx).marks.some(x => x.codes.some(c => KH.stock(c)))).length;
      return { n: +document.querySelector('#news .nw-only .nw-n').textContent, want, rows: [...document.querySelectorAll('#news .nw-row')].length, all: [...document.querySelectorAll('#news .nw-row')].every(r => r.dataset.codes && r.querySelector('.nw-chip')), pressed: document.querySelector('#news .nw-only').getAttribute('aria-pressed') }; }""")
    check('지도 종목 기사만: only rows with chips, count = the number on the chip = headlines naming a map stock', oc['all'] and oc['pressed'] == 'true' and oc['n'] == oc['want'] and oc['n'] > 0 and oc['rows'] == min(oc['n'], pg.evaluate("document.querySelectorAll('#news .nw-row').length")), oc)
    cred = pg.evaluate("() => [document.querySelector('#news .nw-ft small').textContent, document.getElementById('foot-news').textContent, document.getElementById('foot-news').hidden, document.getElementById('foot').textContent.includes('© 2026 blue_crude'), document.getElementById('foot').textContent.includes('데이터: 네이버 증권 (finance.naver.com)')]")
    check('credit lines: card + page footer name the three outlets; © and 네이버 lines stay', cred[0].startswith('연합인포맥스 · 한국경제 · 매일경제 RSS — 제목과 시각만') and cred[1] == '시장 뉴스: 연합인포맥스 · 한국경제 · 매일경제 RSS (제목 · 링크만)' and not cred[2] and cred[3] and cred[4], cred)
    ctx.close()
    # Q3: an outlet that failed with no copy gets no tab and is not credited; no error line
    mode('partial')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    p = pg.evaluate("() => ({ tabs: [...document.querySelectorAll('#news .nw-tabs button')].map(b => b.dataset.k), note: document.querySelector('#news .nw-note').hidden, cred: document.querySelector('#news .nw-ft small').textContent, foot: document.getElementById('foot-news').textContent, bang: document.querySelectorAll('#news .nw-bad').length })")
    check('Q3: failed outlet without a copy → no tab, no note, not credited', p['tabs'] == ['all', 'hankyung', 'mk'] and p['note'] and p['bang'] == 0 and p['cred'].startswith('한국경제 · 매일경제 RSS') and p['foot'] == '시장 뉴스: 한국경제 · 매일경제 RSS (제목 · 링크만)', p)
    mode('ok'); pg.evaluate("KHNews.refresh()"); pg.wait_for_timeout(600); pg.mouse.move(5, 5); pg.wait_for_timeout(200)
    p2 = pg.evaluate("() => [...document.querySelectorAll('#news .nw-tabs button')].map(b => b.dataset.k)")
    check('Q3: when it answers again its tab comes back on the next refresh', p2 == ['all', 'einfomax', 'hankyung', 'mk'], p2)
    ctx.close()
    # stale copy: its tab keeps a !, a one-line note with the time it was fetched + 다시 시도
    mode('stale')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    s = pg.evaluate("() => ({ bang: [...document.querySelectorAll('#news .nw-tabs button')].filter(b => b.querySelector('.nw-bad')).map(b => b.dataset.k), sr: (document.querySelector('#news .nw-tabs .sr') || {}).textContent, note: document.querySelector('#news .nw-note').hidden ? '' : document.querySelector('#news .nw-note').textContent, ein: [...document.querySelectorAll('#news .nw-row .nw-src')].filter(x => x.textContent === '연합인포맥스').length })")
    check('stale outlet: tab ! (+ screen-reader words), note "새 기사를 받지 못했어요 · HH:MM에 받은 목록이에요" + 다시 시도, its rows still shown',
          s['bang'] == ['einfomax'] and s['sr'] and re.match(r'^연합인포맥스 새 기사를 받지 못했어요 · (\d\d:\d\d|\d{1,2}/\d{1,2})에 받은 목록이에요다시 시도', s['note'] or '') and s['ein'] > 0, s)
    ctx.close()

    # ── 7 · states: loading · error → retry · empty · morning (M/D) · 오래됨 after 15 min of failures ──
    mode('slow')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_timeout(200)
    l = pg.evaluate("() => ({ sk: document.querySelectorAll('#news .nw-row.skel').length, at: document.querySelector('#news .nw-at').textContent, dis: [...document.querySelectorAll('#news .nw-tabs button, #news .nw-only:not(.dc-only):not(.dc-lit)')].every(b => b.getAttribute('aria-disabled') === 'true'), h: document.getElementById('news').offsetHeight })")
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    h2 = pg.evaluate("document.getElementById('news').offsetHeight")
    check('loading: skeleton rows, "불러오는 중", tabs + chip off, same card height after', l['sk'] >= 5 and l['at'] == '불러오는 중' and l['dis'] and l['h'] == h2, f'{l} → {h2}')
    ctx.close()
    E.allow = ['502', 'Failed to load resource']
    mode('fail')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    pg.wait_for_selector('#news .nw-msg', timeout=8000); pg.wait_for_timeout(200)
    e = pg.evaluate("() => ({ msg: document.querySelector('#news .nw-msg').textContent, at: document.querySelector('#news .nw-at').textContent, dis: document.querySelector('#news .nw-only').getAttribute('aria-disabled'), more: document.querySelector('#news .nw-more').hidden, h: document.getElementById('news').offsetHeight })")
    check('error: "뉴스를 불러오지 못했어요" + 다시 시도, head "받은 목록 없음", chip off, no 더보기', e['msg'].startswith('뉴스를 불러오지 못했어요세 언론사 모두 응답이 없었어요. 잠시 뒤 다시 눌러 주세요.다시 시도') and e['at'] == '받은 목록 없음' and e['dis'] == 'true' and e['more'], e)
    pg.click('#news .nw-msg .kasync'); pg.wait_for_timeout(500)
    st1 = pg.evaluate("() => document.querySelector('#news .nw-msg .kasync') && document.querySelector('#news .nw-msg .kasync').dataset.st")
    check('retry while it still fails → ! "아직 안 돼요 · 다시" on the key, message stays', st1 == 'fail', st1)
    mode('ok')
    pg.click('#news .nw-msg .kasync'); pg.wait_for_timeout(150)
    st2 = pg.evaluate("() => document.querySelector('#news .nw-msg .kasync') && document.querySelector('#news .nw-msg .kasync').dataset.st")
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    h3 = pg.evaluate("document.getElementById('news').offsetHeight")
    check('retry that works → ✓ 받았어요, then the list; card height unchanged', st2 in ('work', 'done') and h3 == e['h'], f'{st2} {e["h"]}→{h3}')
    E.allow = []; E.items = []
    ctx.close()
    mode('empty')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-msg', timeout=8000)
    em = pg.evaluate("document.querySelector('#news .nw-msg').textContent")
    check('empty: "아직 새 기사가 없어요 · 3분마다 다시 확인해요"', em == '아직 새 기사가 없어요3분마다 다시 확인해요.', em)
    ctx.close()
    mode('morning')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
    mt = pg.evaluate("() => [...document.querySelectorAll('#news .nw-row time')].slice(0, 3).map(t => [t.textContent, t.getAttribute('datetime')])")
    check("yesterday's items read M/D (no leading 0), <time datetime> ISO", all(re.match(r'^\d{1,2}/\d{1,2}$', t[0]) and re.match(r'^\d{4}-\d\d-\d\dT', t[1]) for t in mt), mt)
    ctx.close()
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800, clock=True)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    E.allow = ['502', 'Failed to load resource']
    mode('fail'); n0 = mock('/__stats').get('/api/news', 0)
    for mins in (3, 6, 12):
        pg.clock.run_for(mins * 60 * 1000 + 1000); pg.wait_for_timeout(500)
    n1 = mock('/__stats').get('/api/news', 0)
    so = pg.evaluate("() => ({ cls: document.querySelector('#news .nw-at').className, at: document.querySelector('#news .nw-at').textContent, rows: document.querySelectorAll('#news .nw-row').length, key: !!document.querySelector('#news .nw-at .kasync') })")
    check('failures back off 3 → 6 → 12 min (3 tries in 21 min)', n1 - n0 == 3, f'{n1 - n0} tries')
    check('오래됨 after 15 min: list stays, amber ! "HH:MM 기준 · N분째 못 받았어요" + 다시 시도', 'stale' in so['cls'] and re.search(r'\d\d:\d\d 기준 · \d+분째 못 받았어요', so['at']) and so['rows'] > 0 and so['key'], so)
    mode('ok')
    pg.click('#news .nw-at .kasync'); pg.wait_for_timeout(300); pg.clock.run_for(1500); pg.wait_for_timeout(300)
    so2 = pg.evaluate("() => document.querySelector('#news .nw-at').textContent")
    check('다시 시도 from 오래됨 → back to "HH:MM 기준"', re.match(r'^\d\d:\d\d 기준$', so2), so2)
    E.allow = []; E.items = []
    ctx.close()

    # ── 8 · polling only near the screen; reading guard ──
    # phones put the card right under the map (user 2026-11-14 02:00), so it is near from the start: scroll it far away, then back
    mode('drift')
    ctx, pg = open_page(br, LIVE, 390, 844, clock=True)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
    n0 = mock('/__stats').get('/api/news', 0)
    pg.evaluate("scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(600)
    gap = pg.evaluate("-document.getElementById('news').getBoundingClientRect().bottom")
    pg.clock.run_for(4 * 60 * 1000); pg.wait_for_timeout(600)
    far = mock('/__stats').get('/api/news', 0) - n0
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'start'})"); pg.wait_for_timeout(600); pg.clock.run_for(1000); pg.wait_for_timeout(600)
    near = mock('/__stats').get('/api/news', 0) - n0
    check('no request while the card is far off screen (4 min); one when it comes within 400 px', n0 == 1 and gap > 400 and far == 0 and near == 1, f'n0 {n0} · {round(gap)} px above · {far} → {near}')
    ctx.close()
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    first = pg.evaluate("document.querySelector('#news .nw-row .nw-tt a').textContent")
    pg.hover('#news .nw-row:nth-child(3)'); pg.evaluate("KHNews.refresh()"); pg.wait_for_timeout(600)
    during = pg.evaluate("document.querySelector('#news .nw-row .nw-tt a').textContent")
    out = pg.evaluate("(() => { const r = document.getElementById('news').getBoundingClientRect(); return r.top > 40 ? [r.left + 10, r.top - 20] : [r.left + 10, r.bottom + 20]; })()")
    pg.mouse.move(*out); pg.wait_for_timeout(300)
    after = pg.evaluate("document.querySelector('#news .nw-row .nw-tt a').textContent")
    check('a new list waits while the pointer is in the card, then comes in', during == first and after != first and '새 기사 2' in after, f'{first[:16]} / {during[:16]} / {after[:16]}')
    ctx.close()

    # ── 9 · reduced motion: no row animation, indicator and label swap at once ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800, motion='reduced')
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
    pg.click('#news .nw-more'); pg.wait_for_timeout(50)
    rm = pg.evaluate("() => ({ anim: [...document.querySelectorAll('#news .nw-row')].filter(r => getComputedStyle(r).animationName !== 'none').length, kl: getComputedStyle(document.querySelector('#news .nw-more .kl')).transitionDuration, ind: getComputedStyle(document.querySelector('#news .nw-tabs'), '::before').transitionDuration })")
    fr = pg.evaluate("() => { const l = document.querySelector('#news .nw-list'); return { clip: l.style.clipPath, cls: l.className, rows: document.querySelectorAll('#news .nw-row').length, x: getComputedStyle(document.querySelector('#news .nw-row.nw-x')).opacity }; }")
    check('reduced motion: no row animation, label swap 0s, indicator 0s; 더보기 at once (no clip, the new rows shown)', rm['anim'] == 0 and set(rm['kl'].replace(' ', '').split(',')) <= {'0s'} and set(rm['ind'].replace(' ', '').split(',')) <= {'0s'}
          and not fr['clip'] and 'nw-fold' not in fr['cls'] and fr['rows'] == 30 and fr['x'] == '1', f'{rm} {fr}')
    ctx.close()

    # ── 10 · phone card: 5 rows + 더보기, 2-line titles, 44 px hit areas, 접기 back to the card head ──
    mode('drift')
    ctx, pg = open_page(br, LIVE, 390, 844)
    to_news(pg)
    ph = pg.evaluate("""() => { const n = document.getElementById('news'), rows = [...n.querySelectorAll('.nw-row')], chip = n.querySelector('.nw-chip'), tab = n.querySelector('.nw-tabs button');
      const tt = rows[0].querySelector('.nw-tt'), cs = getComputedStyle(tt);
      return { rows: rows.length, clamp: cs.webkitLineClamp, fs: cs.fontSize, lh: cs.lineHeight, chipH: chip.getBoundingClientRect().height, chipHit: getComputedStyle(chip, '::before').height,
        tabH: tab.getBoundingClientRect().height, moreH: n.querySelector('.nw-more').getBoundingClientRect().height, last: n === document.querySelector('main.layout').lastElementChild,
        underMap: n.getBoundingClientRect().top >= document.getElementById('legend').getBoundingClientRect().bottom - 1 && n.getBoundingClientRect().bottom <= document.querySelector('.side').getBoundingClientRect().top + 1 }; }""")
    check('phone: 5 rows, title 14 px (--fs-lg) · line height 1.45 two lines, chip 32 (hit 44), tabs 40, 더보기 44, card right under the map, above the side cards', ph['rows'] == 5 and ph['clamp'] == '2' and ph['fs'] == '14px' and abs(float(ph['lh'][:-2]) - 20.3) < 0.1
          and round(ph['chipH']) == 32 and ph['chipHit'] == '44px' and ph['tabH'] >= 40 and ph['moreH'] >= 44 and ph['last'] and ph['underMap'], ph)
    if SHOTS:
        pg.evaluate("document.getElementById('news').scrollIntoView({block: 'start'}); scrollBy(0, -70)"); pg.wait_for_timeout(400)
        pg.screenshot(path='/tmp/news_390_card.png')
    pg.click('#news .nw-more'); pg.wait_for_timeout(500)
    n30 = pg.evaluate("document.querySelectorAll('#news .nw-row').length")
    pg.evaluate("scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(700)
    if SHOTS:
        pg.screenshot(path='/tmp/news_390_expanded.png')
    end = pg.evaluate("""() => { const f = document.querySelector('#foot > :last-child').getBoundingClientRect(), dock = document.querySelector('.dock, #dock, [class*="dock"]');
      const d = dock && getComputedStyle(dock).display !== 'none' ? dock.getBoundingClientRect() : null; return { foot: f.bottom, dockTop: d ? d.top : null, vh: innerHeight }; }""")
    check('phone 더보기 → 30 rows; at the very end the last line clears the dock', n30 == 30 and (end['dockTop'] is None or end['foot'] <= end['dockTop']), end)
    pg.evaluate("scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(300)
    pg.click('#news .nw-more'); pg.wait_for_timeout(900)
    top = pg.evaluate("() => ({ top: document.getElementById('news').getBoundingClientRect().top, rows: document.querySelectorAll('#news .nw-row').length, stuck: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--stuck-h')) || 0 })")
    check('접기 → 5 rows, the card head back in view', top['rows'] == 5 and top['top'] >= top['stuck'] - 1 and top['top'] < 844, top)
    pg.click('#news .nw-row:first-child .nw-chip'); pg.wait_for_timeout(400)
    sh = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), scrim: document.getElementById('scrim').classList.contains('open'), hl: document.querySelectorAll('#map .tile.nhl').length })")
    check('phone chip → quick view as a bottom sheet (no map highlight on phones)', sh['open'] and sh['scrim'] and sh['hl'] == 0, sh)
    ctx.close()

    # ── 11 · snapshot (dist/): a note + link, never baked articles ──
    ctx, pg = open_page(br, SNAP, 1280, 800, errors=E)
    sn = pg.evaluate("() => { const n = document.getElementById('news'); return { hidden: n.hidden, text: n.textContent, href: (n.querySelector('a') || {}).href, rows: n.querySelectorAll('.nw-row').length, foot: document.getElementById('foot-news') ? document.getElementById('foot-news').hidden : 'none' }; }")
    check('snapshot: "뉴스는 실시간 버전에서 볼 수 있어요" + LIVE_URL link, no rows, no news credit line', not sn['hidden'] and '뉴스는 실시간 버전에서 볼 수 있어요' in sn['text'] and sn['href'] == 'https://panse.pages.dev/' and sn['rows'] == 0 and sn['foot'] is True, sn)
    g = pg.evaluate(GEO_JS)
    check('snapshot 1280: card fills to the side end, no overflow, no console errors', abs(g['bottom'] - g['sideEnd']) <= 1.5 and g['pageOver'] == 0 and not E.items, f"{g['bottom']:.0f}/{g['sideEnd']:.0f} {E.items[:2]}")
    ctx.close()
    html = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
    titles = [x['title'] for x in json.loads((HERE / 'fixtures/news.json').read_text(encoding='utf-8'))['items']]
    check('dist/index.html carries no article (none of the 90 fixture headlines, no api/news data)', not any(t in html for t in titles))

    # ── 11b · a Worker without /api/news (404 — the page deployed first): no card, the layout without news, no more requests ──
    E.allow = ['404', 'Failed to load resource']
    mode('html404')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    pg.wait_for_timeout(1500)
    g4 = pg.evaluate("() => ({ hidden: document.getElementById('news').hidden, rows: getComputedStyle(document.querySelector('main.layout')).gridTemplateRows, foot: document.getElementById('foot-news').hidden })")
    n4 = mock('/__stats').get('/api/news', 0)
    pg.evaluate("KH.refresh && KH.refresh()"); pg.evaluate("document.dispatchEvent(new CustomEvent('kh:refresh'))"); pg.wait_for_timeout(600)
    n5 = mock('/__stats').get('/api/news', 0)
    check('404 (no /api/news on the Worker yet) → card hidden, one-row layout, no news credit, no more requests', g4['hidden'] and len(g4['rows'].split()) == 1 and g4['foot'] and n4 == 1 and n5 == 1, f"{g4} {n4}→{n5}")
    E.allow = []; E.items = []
    ctx.close()

    # ── 12 · world tab: the layout (and the card) hidden, no polling there ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
    pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(600)
    wv = pg.evaluate("() => ({ vis: !!document.getElementById('news').offsetParent, foot: document.getElementById('foot').textContent.includes('시장 뉴스') })")
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(800)
    g = pg.evaluate(GEO_JS)
    check('world tab hides the card; back on 코스피 it fills again', not wv['vis'] and not wv['foot'] and abs(g['bottom'] - g['sideEnd']) <= 1.5 and g['rows'] >= 5, f"{wv} {g['bottom']:.0f}/{g['sideEnd']:.0f}")
    ctx.close()


def design(br):
    # ── 13 · design standard (design.md, ux/std-news): token sizes, ! colours, the title underline, the 더보기 fold, a chip's % swap, glass ──
    E = Errors()
    mode('stale')
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=E)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(500)
    d = pg.evaluate(DESIGN_JS)
    check('design: list row = --h-row (36), outlet badge = the recipe (18 · 4px · 11px/600), 지도 종목 기사만 24 (--h-chip), 더보기 32 (--h-key), title tabs 14px × 32, headline 13px, time 12px',
          d['row'] == d['hRow'] == 36 and d['badge'] == [18, '4px', '11px', '600'] and d['only'] == 24 and d['more'] == 32 and d['tab'] == ['14px', 32] and d['tt'] == '13px' and d['time'] == '12px', d)
    check('design: every font size in the card is one of the seven steps (≥ 11px)', set(d['sizes']) <= {11, 12, 13, 14, 16, 20, 26}, d['sizes'])
    check('design: ! of the stale outlet (tab) and the note line = --fail-dot, not amber', d['bad'] == d['failDot'] and d['noteIc'] == d['failDot'] and d['bad'] != d['amber'], d)
    check('design: title tabs = one 2px --acc-line underline under the picked tab (KH.ui.seg indicator)', d['ind'] and d['ul'] == ['2px', d['accLine']] and abs(d['ulX'] - d['tabX']) <= 1 and abs(d['ulW'] - d['tabW']) <= 1, d)
    pg.click('#news-t-disc'); pg.wait_for_timeout(30)
    mv = pg.evaluate("""() => { const t = document.querySelector('#news .nw-ftabs'), cs = getComputedStyle(t, '::before');
      const fs = cs.transitionTimingFunction.split(/,\\s*(?=linear\\()/);
      return { dir: t.dataset.dir, prop: cs.transitionProperty, fn: cs.transitionTimingFunction.split('linear(').length - 1, dur: cs.transitionDuration, one: new Set(fs).size === 1 && new Set(cs.transitionDuration.split(', ')).size === 1 }; }""")
    check('design: picking 오늘 공시 moves the underline right in one piece — ② 단단한 이동: every edge on the one lead curve, one length', mv['dir'] == 'r' and 'left' in mv['prop'] and 'right' in mv['prop'] and mv['fn'] >= 2 and mv['one'], mv)
    pg.wait_for_timeout(700)
    pg.click('#news-t-news'); pg.wait_for_selector('#news .nw-row:not(.skel)'); pg.wait_for_timeout(700)
    # the fold: frames sampled from the press to the end (open, then close)
    SAMPLE = """() => { window.__f = []; const t0 = performance.now(); const l = document.querySelector('#news .nw-list');
      const step = () => { const x = l.querySelector('.nw-x'); window.__f.push({ t: performance.now() - t0, clip: l.style.clipPath, cls: l.className.replace('nw-list', '').trim(),
        foot: Math.round(document.getElementById('foot').getBoundingClientRect().top + scrollY), rows: l.children.length, xo: x ? +getComputedStyle(x).opacity : -1, h: Math.round(l.getBoundingClientRect().height) });
        if (performance.now() - t0 < 1100) requestAnimationFrame(step); };
      requestAnimationFrame(step); }"""
    f0 = pg.evaluate("() => ({ foot: Math.round(document.getElementById('foot').getBoundingClientRect().top + scrollY), rows: document.querySelectorAll('#news .nw-row').length })")
    pg.evaluate(SAMPLE); pg.click('#news .nw-more'); pg.wait_for_timeout(1300)
    fo = pg.evaluate("window.__f")
    op = [f for f in fo if f['rows'] == 30]
    fend = op[-1]['foot'] if op else 0
    clips = [float(re.findall(r'(-?[\d.]+)px', f['clip'])[2]) for f in op if len(re.findall(r'(-?[\d.]+)px', f['clip'] or '')) >= 3]   # inset(top sides bottom …)
    check('fold open: what is below (the page footer) moves once, at the press; the list box opens from its old height (clip, `open`)',
          op and all(f['foot'] == fend for f in op) and fend > f0['foot'] + 300 and clips and clips[0] > 300 and clips[-1] < 30 and not op[-1]['clip'],
          f"foot {f0['foot']}→{[f['foot'] for f in op][:3]}… end {fend}, clips {clips[:2]}…{clips[-2:]}")
    early = [f for f in op if 'nw-fold-anim' in f['cls'] and 'nw-fold-in' not in f['cls']]
    check('fold open: the new rows wait hidden, then come in together once the box is a quarter open; nothing left over at the end',
          early and all(f['xo'] == 0 for f in early) and any('nw-fold-in' in f['cls'] for f in op) and op[-1]['xo'] == 1 and op[-1]['cls'] == '', [(round(f['t']), f['cls'], f['xo']) for f in op[:4]])
    pg.evaluate(SAMPLE); pg.click('#news .nw-more'); pg.wait_for_timeout(1300)
    fc = pg.evaluate("window.__f")
    held = [f for f in fc if f['rows'] == 30]
    after = [f for f in fc if f['rows'] != 30]
    check('fold close: the new rows leave first (together), the box closes on `close` while the page stays, then the page comes up once',
          held and all(f['foot'] == fend for f in held) and any('nw-fold-out' in f['cls'] and f['xo'] == 0 for f in held) and any(f['clip'] for f in held)
          and after and after[-1]['rows'] == f0['rows'] and all(f['foot'] == f0['foot'] for f in after), f"held {len(held)} after {len(after)} foot {[f['foot'] for f in fc][:2]}…{fc[-1]['foot']} rows {fc[-1]['rows']}")
    check('design 1440: no console errors', not E.items, E.items[:3]); E.items = []
    ctx.close()
    # a chip's % on a new quote: KH.ui.swap the way it went (the old text leaves, the new one comes in), then the plain value
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.wait_for_selector('#news .nw-chip[data-c] b', timeout=8000); pg.wait_for_timeout(300)
    sw = pg.evaluate("""() => { const b = document.querySelector('#news .nw-chip[data-c] b'), real = b.textContent; b.textContent = '+99.99%';
      document.dispatchEvent(new CustomEvent('kh:data', { detail: { changed: [] } }));
      return { real, text: b.textContent, go: b.classList.contains('sw-go'), was: b.dataset.was || '' }; }""")
    pg.wait_for_timeout(600)
    sw2 = pg.evaluate("() => { const b = document.querySelector('#news .nw-chip[data-c] b'); return { text: b.textContent, go: b.classList.contains('sw-go'), was: b.dataset.was || '' }; }")
    check("chip %: a new quote swaps in place (KH.ui.swap — the old value leaves), then reads the map's value", sw['go'] and sw['was'] == '+99.99%' and sw['text'] == sw['real'] and not sw2['go'] and sw2['text'] == sw['real'], f'{sw} {sw2}')
    ctx.close()
    # glass: the card keeps the theme's material (translucent plate, the 1px edge reflection) — the module paints none of its own
    mode('ok')
    for th in ('glass-dark', 'glass-light'):
        ctx, pg = open_page(br, LIVE, 1440, 900, th)
        pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
        gl = pg.evaluate(r"""() => { const n = document.getElementById('news'), cs = getComputedStyle(n), m = cs.backgroundColor.match(/rgba?\(([^)]+)\)/);
          const a = m ? (m[1].split(/[ ,\/]+/).filter(Boolean)[3] || '1') : '1';
          return { alpha: +a, edge: /inset/.test(cs.boxShadow) && /rgba\(255, 255, 255/.test(cs.boxShadow), r: cs.borderTopLeftRadius, tok: getComputedStyle(document.documentElement).getPropertyValue('--card-r').trim() }; }""")
        check(f'glass {th}: the news card keeps its material — translucent plate, 1px edge reflection, the template\'s --card-r corner (.card; ④ 24px)', gl['alpha'] < 1 and gl['edge'] and gl['r'] == gl['tok'] == '24px', gl)
        ctx.close()
    # kept: while the market summary card is open (PC) the news card does not grow with the side column — nw-hold, rows as when folded
    ctx, pg = open_page(br, LIVE, 1440, 900)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(600)
    st = "() => ({ hold: document.getElementById('news').classList.contains('nw-hold'), rows: document.querySelectorAll('#news .nw-row').length, sum: !!(window.KHSummary && KHSummary.isOpen) })"
    h0 = pg.evaluate(st)
    if h0['sum']:
        pg.evaluate("KHSummary.open()"); pg.wait_for_timeout(1600)
        h1 = pg.evaluate(st)
        pg.evaluate("KHSummary.close()"); pg.wait_for_timeout(2200)
        h2 = pg.evaluate(st)
        check('kept: summary card open → the news card holds (nw-hold, rows as folded); closed → back', not h0['hold'] and h1['hold'] and h1['rows'] == h0['rows'] and not h2['hold'] and h2['rows'] == h0['rows'], f'{h0} {h1} {h2}')
    else:
        check('kept: summary card present for the nw-hold check', False, h0)
    ctx.close()


DESIGN_JS = r"""() => {
  const n = document.getElementById('news'), R = e => e.getBoundingClientRect(), cs = (e, p) => getComputedStyle(e, p || null);
  const probe = document.createElement('i'); document.body.append(probe);
  const col = v => { probe.style.color = ''; probe.style.color = `var(${v})`; return getComputedStyle(probe).color; };
  const row = n.querySelector('.nw-row:not(.skel)'), b = n.querySelector('.nw-row .nw-src'), tab = n.querySelector('.nw-ftabs > button[aria-selected="true"]'), t = n.querySelector('.nw-ftabs');
  const sizes = new Set(); for (const e of n.querySelectorAll('*')) if (e.offsetWidth && [...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim())) sizes.add(Math.round(parseFloat(cs(e).fontSize) * 10) / 10);
  const res = { row: Math.round(R(row).height), hRow: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--h-row')),
    badge: [Math.round(R(b).height), cs(b).borderTopLeftRadius, cs(b).fontSize, cs(b).fontWeight], only: Math.round(R(n.querySelector('.nw-only')).height),
    more: Math.round(R(n.querySelector('.nw-more')).height), tab: [cs(tab).fontSize, Math.round(R(tab).height)], tt: cs(n.querySelector('.nw-row .nw-tt')).fontSize,
    time: cs(n.querySelector('.nw-row time')).fontSize, sizes: [...sizes].sort((x, y) => x - y),
    bad: cs(n.querySelector('.nw-tabs .nw-bad')).color, noteIc: cs(n.querySelector('.nw-note > svg')).color, failDot: col('--fail-dot'), amber: col('--acc'),
    ind: t.dataset.ind != null, ul: [cs(t, '::before').height, cs(t, '::before').backgroundColor], accLine: col('--acc-line'),
    ulX: R(t).left + parseFloat(cs(t, '::before').left), ulW: parseFloat(cs(t, '::before').width), tabX: R(tab).left, tabW: R(tab).width };
  probe.remove();
  return res;
}"""


RK_GEO = r"""() => {
  const n = document.getElementById('news'), hd = n.querySelector('.nw-hd'), k = n.querySelector('.nw-rk'), at = n.querySelector('.nw-at');
  const R = e => e.getBoundingClientRect(), r = R(k), h = R(hd), tabs = n.querySelector('.nw-ftabs') || n.querySelector('.nw-hd h2'), t = R(tabs);
  const cs = getComputedStyle(k), b = getComputedStyle(k, '::before'), ic = k.querySelector('.nw-rki');
  const tok = v => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(v));
  return { w: r.width, h: r.height, hk: tok('--h-key'), right: h.right - r.right, mid: Math.abs((r.top + r.bottom) / 2 - (t.top + t.bottom) / 2),
    gapAt: r.left - R(at).right, tabsEnd: t.right, atLeft: R(at).left, hit: b.content !== 'none' ? [parseFloat(b.width), parseFloat(b.height)] : [r.width, r.height],
    stroke: ic ? getComputedStyle(ic.querySelector('path')).strokeWidth + '|' + ic.querySelector('path').getAttribute('vector-effect') : '', icon: ic ? R(ic).width : 0,
    radius: cs.borderTopLeftRadius, rkey: getComputedStyle(document.documentElement).getPropertyValue('--r-key').trim(),
    pageOver: document.documentElement.scrollWidth - document.documentElement.clientWidth, cardOver: n.scrollWidth - n.clientWidth,
    at: at.textContent, atw: at.querySelector('.nw-atw') ? R(at.querySelector('.nw-atw')).width : -1, label: k.getAttribute('aria-label'), st: k.dataset.st, hidden: k.hidden };
}"""
RK_ST = "(() => { const k = document.querySelector('#news .nw-rk'), i = k.querySelector('.nw-rki'), cs = getComputedStyle(i); return { st: k.dataset.st, busy: k.getAttribute('aria-busy'), anim: cs.animationName, op: parseFloat(cs.opacity), bub: [...document.querySelectorAll('.kbub')].map(b => b.textContent), hidden: k.hidden }; })()"
FAIL_DOT = "(() => { const i = document.createElement('i'); i.style.color = 'var(--fail-dot)'; document.body.append(i); const c = getComputedStyle(i).color; i.remove(); return c; })()"


def refresh_key(br):
    # ── 14 · ↻ 새로 받기 (사용자 2026-11-16 09:24): one icon key at the head's right end, for the tab shown — size from --h-key, 1.75px icon,
    #        44 px hit on touch, hover only on a fine pointer; ↻ → turns while it works (줄이기: still, .45) → ✓ / ! (--fail-dot); no second
    #        press while it works; under 10 s since the last answer → no request, "방금 받았어요"; the list it brings is drawn at once ──
    E = Errors()
    mode('ok')
    for w, h in SIZES:
        for th in THEMES:
            ctx, pg = open_page(br, LIVE, w, h, th, errors=E)
            to_news(pg, 500)
            g = pg.evaluate(RK_GEO)
            phone = w <= 760
            ok = (abs(g['w'] - g['hk']) < .5 and abs(g['h'] - g['hk']) < .5 and abs(g['right']) <= 1 and g['mid'] <= 2 and g['atLeft'] >= g['tabsEnd'] - .5
                  and g['pageOver'] == 0 and g['cardOver'] == 0 and g['stroke'].startswith('1.75') and 'non-scaling-stroke' in g['stroke'] and 15.5 <= g['icon'] <= 16.5
                  and g['radius'] == g['rkey'] and (min(g['hit']) >= 44 if phone else True) and not g['hidden'] and g['label'] == '시장 뉴스 새로 받기'
                  and g['at'].endswith('기준') and ((0 <= g['atw'] <= 1) if phone else g['atw'] > 10))
            check(f'↻ key {w}×{h} {th}: --h-key square at the head end, same row as the tabs, icon 16 · 1.75px, hit ≥ 44 on touch, no overflow; phone time "HH:MM" (기준 for readers)', ok,
                  {k: (round(v, 1) if isinstance(v, float) else v) for k, v in g.items() if k in ('w', 'h', 'right', 'mid', 'hit', 'pageOver', 'cardOver', 'atw', 'stroke', 'icon', 'radius')})
            ctx.close()
    # hover: a fine pointer lights the key; a phone's tap leaves no hover colour behind
    ctx, pg = open_page(br, LIVE, 1280, 800)
    to_news(pg, 400)
    bg0 = pg.evaluate("getComputedStyle(document.querySelector('#news .nw-rk')).backgroundColor")
    pg.hover('#news .nw-rk'); pg.wait_for_timeout(400)
    bg1 = pg.evaluate("getComputedStyle(document.querySelector('#news .nw-rk')).backgroundColor")
    ctx.close()
    ctx, pg = open_page(br, LIVE, 390, 844)
    to_news(pg, 400)
    pb0 = pg.evaluate("getComputedStyle(document.querySelector('#news .nw-rk')).backgroundColor")
    pg.hover('#news .nw-rk'); pg.wait_for_timeout(400)
    pb1 = pg.evaluate("getComputedStyle(document.querySelector('#news .nw-rk')).backgroundColor")
    ctx.close()
    check('hover: fine pointer → --key-hover; touch → none', bg0 != bg1 and pb0 == pb1, f'{bg0}→{bg1} · phone {pb0}→{pb1}')

    for motion in ('standard', 'reduced'):
        mode('ok')
        ctx, pg = open_page(br, LIVE, 1280, 800, motion=motion, errors=E, clock=True)
        to_news(pg, 600)
        n0 = mock('/__stats').get('/api/news', 0)
        pg.click('#news .nw-rk'); pg.wait_for_timeout(300)
        s = pg.evaluate(RK_ST)
        check(f'{motion}: press under 10 s since the last answer → no request, idle, "방금 받았어요" bubble', mock('/__stats').get('/api/news', 0) == n0 and s['st'] == 'idle' and '방금 받았어요' in s['bub'], s)
        pg.clock.run_for(11000); pg.wait_for_timeout(1900)                  # (the bubble goes)
        mock('/__mode?news=slow')
        n0 = mock('/__stats').get('/api/news', 0)
        pg.click('#news .nw-rk'); pg.wait_for_timeout(250)
        s = pg.evaluate(RK_ST)
        pg.click('#news .nw-rk', force=True); pg.wait_for_timeout(100)
        turn = (s['anim'] == 'kspn' and s['op'] == 1) if motion == 'standard' else (s['anim'] == 'none' and abs(s['op'] - .45) < .01)
        check(f'{motion}: working — data-st work, aria-busy, ↻ {"turns" if motion == "standard" else "still, dimmed .45"}; a second press asks nothing', s['st'] == 'work' and s['busy'] == 'true' and turn, s)
        pg.wait_for_timeout(2900)
        s = pg.evaluate(RK_ST)
        check(f'{motion}: done → ✓ "새로 받았어요" (bubble + live region), one request', s['st'] == 'done' and '새로 받았어요' in s['bub'] and mock('/__stats').get('/api/news', 0) - n0 == 1, (s, mock('/__stats').get('/api/news', 0) - n0))
        pg.clock.run_for(1300); pg.wait_for_timeout(200)
        check(f'{motion}: ✓ held ~1.1 s, then ↻ again', pg.evaluate(RK_ST)['st'] == 'idle')
        mock('/__mode?news=fail')
        pg.clock.run_for(11000); pg.wait_for_timeout(100)
        pg.click('#news .nw-rk'); pg.wait_for_timeout(700)
        s = pg.evaluate(RK_ST)
        col = pg.evaluate("getComputedStyle(document.querySelector('#news .nw-rk .kwn')).color")
        check(f'{motion}: failed → ! in --fail-dot + "못 받았어요" bubble; the list stays', s['st'] == 'fail' and col == pg.evaluate(FAIL_DOT) and any('못 받았어요' in b for b in s['bub'])
              and pg.locator('#news .nw-row:not(.skel)').count() > 0, (s, col))
        pg.clock.run_for(5000); pg.wait_for_timeout(100)
        st_hold = pg.evaluate(RK_ST)['st']
        pg.evaluate("KHNews.select('disc')"); pg.wait_for_timeout(200)
        st_tab = pg.evaluate(RK_ST)
        check(f'{motion}: ! stays until the next press; another tab → ↻ for that tab', st_hold == 'fail' and st_tab['st'] == 'idle'
              and pg.evaluate("document.querySelector('#news .nw-rk').getAttribute('aria-label')") == '오늘 공시 새로 받기', (st_hold, st_tab))
        ctx.close()

    # the list it brings is drawn at once — even with the pointer in the card (the reader asked) — and the head's time follows the answer
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E, clock=True)
    to_news(pg, 600)
    first = "document.querySelector('#news .nw-row .nw-tt a').textContent"
    f0 = pg.evaluate(first)
    pg.route('**/api/news', lambda route: route.fulfill(json=dict(_j := json.loads(route.fetch().text()), asOf=_j['asOf'][:11] + '23:58:00+09:00')))
    mock('/__mode?news=drift')
    pg.clock.run_for(11000); pg.wait_for_timeout(100)
    pg.hover('#news .nw-row:nth-child(2)'); pg.hover('#news .nw-rk'); pg.click('#news .nw-rk'); pg.wait_for_timeout(700)
    f1, at1 = pg.evaluate(first), pg.evaluate("document.querySelector('#news .nw-at').textContent")
    check('↻ with the pointer in the card: the new headline is drawn at once; the head says the answer\'s time', f1 != f0 and '새 기사' in f1 and at1 == '23:58 기준', (f0[:20], f1[:20], at1))
    pg.unroute('**/api/news')
    # the head carries its own 다시 시도 (오래됨) → the ↻ key steps aside (one key per job)
    mock('/__mode?news=fail')
    pg.evaluate("KHNews.refresh()"); pg.clock.run_for(16 * 60000); pg.wait_for_timeout(300)
    pg.evaluate("KHNews.refresh()"); pg.wait_for_timeout(400)
    sv = pg.evaluate("({ stale: document.querySelector('#news .nw-at').classList.contains('stale'), retry: !!document.querySelector('#news .nw-at .kasync'), rk: document.querySelector('#news .nw-rk').hidden })")
    check('오래됨: the head\'s own 다시 시도, the ↻ key hidden', sv['stale'] and sv['retry'] and sv['rk'], sv)
    ctx.close()
    errs = [e for e in E.items if 'Failed to load resource' not in e]     # (the 502s of the fail mode are the network panel's, not the page's)
    check('↻: no console errors', not errs, errs[:3])


def shots(br):
    mode('ok')
    for w, h, th in [(1280, 800, 'base'), (1280, 800, 'glass-dark'), (1920, 1080, 'base'), (1920, 1080, 'glass-light')]:
        ctx, pg = open_page(br, LIVE, w, h, th)
        pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(600)
        pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000); pg.wait_for_timeout(500)
        pg.screenshot(path=f'/tmp/news_{w}_{th}.png', full_page=True)
        pg.click('#news .nw-only'); pg.wait_for_timeout(200)
        pg.evaluate("document.getElementById('news').scrollIntoView({block: 'end'})"); pg.wait_for_timeout(300)
        pg.hover('#news .nw-row:first-child .nw-tt'); pg.wait_for_timeout(400)
        pg.screenshot(path=f'/tmp/news_{w}_{th}_only.png')       # viewport: the lit tile above, the 지도 종목 기사만 list below
        ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            if ONLY not in ('design', 'refresh'):
                run(br)
            if ONLY != 'refresh':
                design(br)
            if ONLY in ('', 'refresh'):
                refresh_key(br)
            if SHOTS:
                shots(br)
            br.close()
    finally:
        srv.terminate()
        srv.wait(5)
    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed')
    for n in bad:
        print('  FAIL', n)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
