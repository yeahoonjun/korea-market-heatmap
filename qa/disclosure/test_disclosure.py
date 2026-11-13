#!/usr/bin/env python3
"""QA for the 공시 배지 (src/disclosure, docs/standards/disclosure.md — C안) on the built pages.

  python3 scripts/build_page.py && python3 qa/disclosure/test_disclosure.py [--shots]

Starts qa/news/mock_api.py on DISC_QA_PORT (default 8902; serves web/ + /api/news + /api/disclosures/today built from the snapshot at
request time — modes in its docstring) and, for the "no filings → the map as before" check, a second one on DISC_QA_BASE_PORT (8903)
serving the web/ of git rev DISC_QA_BASE (default: main) with no disclosure route. --shots writes /tmp/dis_live_*.png. Exit 1 on a fail.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image, ImageChops
import io
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MOCK = ROOT / 'qa/news/mock_api.py'
PORT = int(os.environ.get('DISC_QA_PORT', 8902))
BPORT = int(os.environ.get('DISC_QA_BASE_PORT', 8903))
BASE_REV = os.environ.get('DISC_QA_BASE', 'main')
LIVE = f'http://127.0.0.1:{PORT}/'
BASE = f'http://127.0.0.1:{BPORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SIZES = [(360, 740), (390, 844), (768, 1024), (1280, 800), (1920, 1080)]
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SHOTS = '--shots' in sys.argv
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' and (not ok or len(str(detail)) < 200) else ''), flush=True)


def mock(path, base=LIVE):
    with NOPROXY.open(base.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


def mode(disc='ok', news='ok'):
    mock('/__reset')
    mock(f'/__mode?disc={disc}&news={news}')


class Errors:
    def __init__(self):
        self.items, self.allow = [], []

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type in ('error', 'warning') and not any(a in m.text for a in self.allow) else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


def open_page(br, url, w, h, theme='base', motion='standard', errors=None, market='K', store=None, wait=1800):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(store or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    if errors is not None:
        errors.attach(pg)
    pg.goto(url)
    pg.wait_for_timeout(wait)
    return ctx, pg


def disc_tab(pg):
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})")
    pg.click('#news-t-disc')
    pg.wait_for_selector('#news .dc-row:not(.skel), #news-p-disc .nw-msg', timeout=8000)
    pg.wait_for_timeout(250)


GEO_JS = r"""() => {
  const n = document.getElementById('news'), side = document.querySelector('main.layout > .side'), list = n.querySelector('#news-p-disc .nw-list');
  const R = e => e.getBoundingClientRect(), Y = e => R(e).top + scrollY;
  const rows = [...n.querySelectorAll('#news-p-disc .dc-row:not(.skel)')];
  const txt = [n, document.getElementById('stage-tools'), document.getElementById('legend'), document.getElementById('foot')].map(e => e ? e.textContent : '').join(' ');
  return { bottom: R(n).bottom + scrollY, sideEnd: R(side.lastElementChild).bottom + scrollY, rows: rows.length, two: list.classList.contains('c2'),
    listH: list.getBoundingClientRect().height, rh: parseFloat(getComputedStyle(n).getPropertyValue('--nw-rh')) || 0,
    perCol: list.classList.contains('c2') ? Math.ceil(rows.length / 2) : rows.length, cardH: n.offsetHeight,
    pageOver: document.documentElement.scrollWidth - document.documentElement.clientWidth, cardOver: n.scrollWidth - n.clientWidth,
    rowOver: rows.filter(r => r.scrollWidth > r.clientWidth + 1).length, bad: /\bnull\b|\bundefined\b|\bNaN\b/.test(txt) };
}"""

# contrast: text ≥ 4.5 (the first argument's selectors), graphics ≥ 3 (the dot)
CONTRAST_JS = r"""(sel) => {
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
  const res = {};
  for (const s of sel) for (const el of document.querySelectorAll(s)) {
    if (!el.offsetWidth || el.closest('[aria-disabled="true"]') || el.closest('.skel')) continue;
    const dot = el.classList.contains('dc-dot');
    const fg = P(getComputedStyle(el)[dot ? 'backgroundColor' : 'color']); if (!fg || (!dot && !(el.textContent || '').trim())) continue;
    let worst = 99; for (const b of bgs(dot ? el.parentElement : el)) worst = Math.min(worst, CR(over(fg, b), b));
    if (!(s in res) || worst < res[s].v) res[s] = { v: Math.round(worst * 100) / 100, t: (el.textContent || '').trim().slice(0, 14) };
  }
  return res;
}"""
TEXT_SEL = ['#news .nw-tt button', '#news .nw-tt .nw-tn', '#news .nw-at span', '#news .dc-ktabs > button', '#news .dc-ktabs small', '#news .dc-only',
            '#news .dc-only .nw-n', '#news .dc-row .dc-tm', '#news .dc-kb', '#news .dc-chip', '#news .dc-chip b', '#news .dc-chipx', '#news .dc-chipx small',
            '#news .dc-tt a', '#news .dc-x', '#news-p-disc .nw-ft small', '#news-p-disc .nw-msg b', '#news-p-disc .nw-msg small', '#stage-tools .dc-hchip',
            '#stage-tools .dc-n', '#legend .dc-lg', '#legend .dc-lg b', '#legend .dc-lg2', '#foot-disc']
TIP_SEL = ['#tip .dsc-h', '#tip .dsc-h b', '#tip .dsc .dc-kb', '#tip .dsc .tt', '#tip .dsc .dc-tm', '#tip .dsc-more', '#tip .dsc-more b', '#tip .dsc-hint',
           '#sheet .dsc .tt', '#sheet .dsc .dc-tm', '#sheet .dsc .dc-kb', '#sheet .dc-all']
DOT_SEL = ['#news .dc-dot', '#tip .dc-dot', '#sheet .dc-dot']

# the corner on every marked tile: the flap or the cut (map floor), whichever stands out more against the tile — ≥ 3:1
FOLD_JS = r"""() => {
  const P = s => { const m = s && s.match(/rgba?\(([^)]+)\)/); if (m) { const v = m[1].split(/[ ,\/]+/).map(parseFloat); return v.slice(0, 3); }
    let h = (s || '').trim().replace('#', ''); if (h.length === 3) h = [...h].map(c => c + c).join(''); return h.length === 6 ? [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) : null; };
  const L = c => c.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
  const CR = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const cs = getComputedStyle(document.documentElement), flap = P(cs.getPropertyValue('--dm-flap')), cut = P(cs.getPropertyValue('--map-bg'));
  let worst = 99, n = 0;
  for (const d of document.querySelectorAll('#map .tile .dm')) { const t = P(getComputedStyle(d.parentElement).backgroundColor); if (!t) continue; n++; worst = Math.min(worst, Math.max(CR(flap, t), CR(cut, t))); }
  return { worst: Math.round(worst * 100) / 100, n, pair: Math.round(CR(flap, cut) * 100) / 100 };
}"""

# the corner sizes follow §3-2 (short side m: 8–9 → 4 / new 5; ≥ 10 → round(m × .14) in 5..10 / new round(m × .2) in 7..14, ≤ m/2; < 8 none)
SIZE_JS = r"""() => {
  const marks = KH.marks.get('disc') || new Map(); let bad = [], drawn = 0, tiny = 0, marked = 0;
  for (const t of document.querySelectorAll('#map .tile[data-c]')) {
    const mk = marks.get(t.dataset.c), d = t.querySelector('.dm');
    if (!mk) { if (d) bad.push('unmarked ' + t.dataset.c); continue; }
    marked++;
    const w = parseFloat(t.style.width), hh = parseFloat(t.style.height), m = Math.min(w, hh), nw = mk.size === 'new';
    const want = m < 8 ? 0 : m < 10 ? (nw ? 5 : 4) : nw ? Math.max(7, Math.min(14, Math.round(m * .2), Math.floor(m * .5))) : Math.max(5, Math.min(10, Math.round(m * .14)));
    const got = d ? parseFloat(d.style.getPropertyValue('--s')) : 0;
    if (got !== want) bad.push(`${t.dataset.c} m${m} ${mk.size} want ${want} got ${got}`);
    if (d) drawn++; else tiny++;
    if (!(t.getAttribute('aria-label') || '').includes(mk.label.trim().replace(/^, /, ''))) bad.push('aria ' + t.dataset.c);
  }
  return { bad: bad.slice(0, 5), nbad: bad.length, drawn, tiny, marked };
}"""


def worst_of(acc, d):
    for k, v in d.items():
        if k not in acc or v['v'] < acc[k]['v']:
            acc[k] = v


def run(br):
    E = Errors()

    # ── 1 · five widths × four themes: overflow, console, no null / NaN, the tab draws rows; contrast (text 4.5, dot 3, fold 3) ──
    mode('ok')
    contrast, dots, folds = {th: {} for th in THEMES}, {th: {} for th in THEMES}, {}
    for w, h in SIZES:
        for th in THEMES:
            E.items = []
            ctx, pg = open_page(br, LIVE, w, h, th, errors=E)
            disc_tab(pg)
            g = pg.evaluate(GEO_JS)
            ok = g['pageOver'] == 0 and g['cardOver'] <= 0 and g['rowOver'] == 0 and not g['bad'] and not E.items and g['rows'] > 0
            check(f'{w}x{h} {th}: overflow 0 · console 0 · no null/NaN · rows', ok, f"page {g['pageOver']} card {g['cardOver']} rows-over {g['rowOver']} bad {g['bad']} rows {g['rows']} err {E.items[:2]}")
            if w in (390, 1280):
                worst_of(contrast[th], pg.evaluate(CONTRAST_JS, TEXT_SEL)); worst_of(dots[th], pg.evaluate(CONTRAST_JS, DOT_SEL))
                if w == 1280:
                    pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(100)
                    r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
                    pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(300)
                    worst_of(contrast[th], pg.evaluate(CONTRAST_JS, TIP_SEL)); worst_of(dots[th], pg.evaluate(CONTRAST_JS, DOT_SEL))
                    pg.mouse.move(3, 3); pg.evaluate("KH.quick('005930', null)"); pg.wait_for_timeout(300)
                    worst_of(contrast[th], pg.evaluate(CONTRAST_JS, TIP_SEL)); worst_of(dots[th], pg.evaluate(CONTRAST_JS, DOT_SEL))
                    folds[th] = pg.evaluate(FOLD_JS)
            ctx.close()
    for th in THEMES:
        c, d = contrast[th], dots[th]
        lo = min(c.items(), key=lambda kv: kv[1]['v']) if c else ('-', {'v': 0})
        check(f'contrast {th}: text ≥ 4.5 (lowest {lo[1]["v"]} {lo[0]}), {len(c)} kinds of text', c and all(v['v'] >= 4.5 for v in c.values()),
              json.dumps({k: v['v'] for k, v in c.items() if v['v'] < 4.5}, ensure_ascii=False))
        check(f'contrast {th}: new dot ≥ 3 (lowest {min((v["v"] for v in d.values()), default=0)})', d and all(v['v'] >= 3 for v in d.values()), json.dumps(d, ensure_ascii=False))
        f = folds.get(th, {})
        check(f'contrast {th}: corner ≥ 3 against its tile (flap or cut, worst {f.get("worst")} over {f.get("n")} tiles; flap↔cut {f.get("pair")})', f.get('n', 0) > 0 and f['worst'] >= 3, f)

    # ── 2 · tiles: corner sizes, aria-label, the chip lights exactly the marked stocks (AND search), the table ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    sz = pg.evaluate(SIZE_JS)
    check(f'corners follow §3-2 sizes and tile aria-labels say "오늘 공시 N건" ({sz["drawn"]} drawn, {sz["tiny"]} too small, {sz["marked"]} marked)', sz['nbad'] == 0 and sz['drawn'] > 0, sz)
    c = pg.evaluate("""() => { const m = KH.marks.get('disc'), codes = KH.mapCodes(); const want = codes.filter(c => m.has(c)).length;
      const marksOk = [...m.entries()].every(([c, v]) => KH.disclosures(c).some(x => (KH.getSetting('discKinds') || []).includes(x.k)));
      return { want, chip: +document.querySelector('#stage-tools .dc-n').textContent, legend: document.querySelector('#legend .dc-lg').textContent, marksOk,
        nonMarked: KH.disclosures().rows.filter(r => !['실적','주요'].includes(r.k)).every(r => !m.has(r.c) || KH.disclosures(r.c).some(x => ['실적','주요'].includes(x.k))) }; }""")
    check('chip count = map stocks with a 실적 · 주요 filing; legend says the same; marks = stocks with a marked kind only', c['chip'] == c['want'] and c['want'] > 0 and str(c['want']) in c['legend'] and c['marksOk'] and c['nonMarked'], c)
    pg.click('#stage-tools .dc-hchip'); pg.wait_for_timeout(300)
    d = pg.evaluate("""() => { const m = KH.marks.get('disc'), tiles = [...document.querySelectorAll('#map .tile[data-c]')];
      const lit = tiles.filter(t => !t.classList.contains('mdim')), dim = tiles.filter(t => t.classList.contains('mdim'));
      return { pressed: document.querySelector('.dc-hchip').getAttribute('aria-pressed'), lit: lit.length, litMarked: lit.every(t => m.has(t.dataset.c)),
        dimUnmarked: dim.every(t => !m.has(t.dataset.c)), drawnMarked: tiles.filter(t => m.has(t.dataset.c)).length, filter: getComputedStyle(dim[0]).filter,
        layoutDim: KH.layout().filter(t => t.kind === 'tile' && t.dim).length, dims: dim.length }; }""")
    check('chip on → exactly the marked tiles stay bright (.mdim on all others, same filter as the search dim); KH.layout() reports them dim',
          d['pressed'] == 'true' and d['litMarked'] and d['dimUnmarked'] and d['lit'] == d['drawnMarked'] and 'brightness(0.38)' in d['filter'] and d['layoutDim'] == d['dims'], d)
    pg.fill('#q', '삼성'); pg.wait_for_timeout(300)
    a = pg.evaluate("""() => { const m = KH.marks.get('disc'), tiles = [...document.querySelectorAll('#map .tile[data-c]')];
      const bright = tiles.filter(t => !t.classList.contains('mdim') && !t.classList.contains('dim'));
      return { n: bright.length, ok: bright.every(t => m.has(t.dataset.c) && KH.stock(t.dataset.c).n.includes('삼성')) }; }""")
    check('chip AND search: only marked stocks matching "삼성" stay bright', a['ok'] and a['n'] >= 1, a)
    pg.fill('#q', ''); pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    # the news / 공시 row hover lights its tile on top of the chip
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'end'})"); pg.click('#news-t-disc'); pg.wait_for_timeout(200)
    pg.click('#news .dc-ktabs button[data-k="지분"]'); pg.wait_for_timeout(200)
    code = pg.evaluate("(() => { const r = [...document.querySelectorAll('#news .dc-row')].find(r => KH.stock(r.dataset.c) && document.querySelector(`#map .tile[data-c=\"${r.dataset.c}\"]`) && !KH.marks.get('disc').has(r.dataset.c)); return r ? r.dataset.c : null; })()")
    if code:
        pg.hover(f'#news .dc-row[data-c="{code}"] .dc-tt'); pg.wait_for_timeout(250)
        hv = pg.evaluate(f"(() => {{ const t = document.querySelector('#map .tile[data-c=\"{code}\"]'); return {{ nhl: t.classList.contains('nhl'), mdim: t.classList.contains('mdim'), filter: getComputedStyle(t).filter }}; }})()")
        check('a 지분 row hovered over a dimmed (unmarked) stock lights its tile on top of the chip', hv['nhl'] and hv['mdim'] and hv['filter'] == 'none', hv)
        pg.mouse.move(3, 3); pg.wait_for_timeout(200)
    else:
        check('a 지분 row of an unmarked map stock exists in the fixture', False)
    pg.click('#stage-tools .dc-hchip'); pg.wait_for_timeout(200)
    off = pg.evaluate("document.querySelectorAll('#map .tile.mdim').length")
    check('chip off → no .mdim left', off == 0, off)
    # table view: the swatch in the name cell; the chip keeps marked rows only
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
    t1 = pg.evaluate("() => ({ rows: document.querySelectorAll('#tablewrap tbody tr').length, sw: document.querySelectorAll('#tablewrap .nmcell .dmsw').length, title: (document.querySelector('#tablewrap .nmcell .dmsw') || {}).title, label: document.querySelector('#tablewrap tr[data-c=\"005930\"]').getAttribute('aria-label') })")
    pg.click('#stage-tools .dc-hchip'); pg.wait_for_timeout(300)
    t2 = pg.evaluate("() => ({ rows: document.querySelectorAll('#tablewrap tbody tr').length, all: [...document.querySelectorAll('#tablewrap tbody tr')].every(r => KH.marks.get('disc').has(r.dataset.c)) })")
    check('table: swatch titled "오늘 공시 N건" in the name cell, row aria-label says it; chip on → only the marked rows (not dimmed)',
          t1['sw'] == c['want'] and re.match(r'^오늘 공시 \d+건$', t1['title'] or '') and '오늘 공시' in t1['label'] and t2['rows'] == c['want'] and t2['all'], f'{t1} {t2}')
    pg.click('#stage-tools .dc-hchip'); pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
    check('no console errors (corners · chip · table)', not E.items, E.items[:3])
    ctx.close()

    # ── 3 · tooltip and quick view: ≤ 3 rows of the marked kinds, "그 밖에", DART links in the quick view, 공시 모두 보기 → stock page 공시 ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    for code, want in (('005930', '6건'), ('005490', '3건'), ('000660', '2건')):
        r = pg.evaluate(f"(() => {{ const r = document.querySelector('#map .tile[data-c=\"{code}\"]').getBoundingClientRect(); return [r.x + Math.min(r.width / 2, 30), r.y + Math.min(r.height / 2, 20)]; }})()")
        pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(300)
        tp = pg.evaluate("() => { const b = document.querySelector('#tip .dsc'); return b ? { head: b.querySelector('.dsc-h').textContent, rows: [...b.querySelectorAll('.dr')].map(x => [x.querySelector('.dc-kb').textContent, x.querySelector('.tt').textContent, x.querySelector('.dc-tm').textContent, !!x.querySelector('.dc-dot')]), more: (b.querySelector('.dsc-more') || {}).textContent || '', hint: (b.querySelector('.dsc-hint') || {}).textContent || '', links: b.querySelectorAll('a').length, after: b.previousElementSibling.className } : null; }")
        if code == '005930':
            check('tooltip 삼성전자: "오늘 공시 6건 · ● 30분 안", 실적 (new, dot) then 주요 (no dot), "그 밖에 지분 4", hint, no links, under headBlock',
                  tp and tp['head'].startswith('오늘 공시6건') and tp['head'].endswith('30분 안') and len(tp['rows']) == 2 and tp['rows'][0][0] == '실적' and tp['rows'][0][3] and tp['rows'][1][0] == '주요' and not tp['rows'][1][3]
                  and tp['more'] == '그 밖에 지분 4' and tp['hint'].startswith('누르면 종목 페이지') and tp['links'] == 0 and tp['after'] == 'card-head', tp)
        elif code == '005490':
            check('tooltip POSCO홀딩스: 주요 ×2, "그 밖에 정기 1"', tp and [x[0] for x in tp['rows']] == ['주요', '주요'] and tp['more'] == '그 밖에 정기 1', tp)
        else:
            check('tooltip SK하이닉스 (지분 only): no rows, "지분 2 — 지도에 표시하지 않는 종류예요", no corner on its tile',
                  tp and not tp['rows'] and tp['more'] == '지분 2 — 지도에 표시하지 않는 종류예요' and pg.evaluate("!document.querySelector('#map .tile[data-c=\"000660\"] .dm')"), tp)
    pg.mouse.move(3, 3)
    pg.evaluate("KH.quick('005930', document.querySelector('#map .tile[data-c=\"005930\"]'))"); pg.wait_for_timeout(400)
    q = pg.evaluate("() => { const b = document.querySelector('#sheet .dsc'); return { rows: [...b.querySelectorAll('a.dr')].map(a => [a.href, a.target, a.rel, a.getAttribute('aria-label'), Math.round(a.getBoundingClientRect().height)]), all: b.querySelector('.dc-all').textContent }; }")
    check('quick view: rows are DART links (rcpNo=14 digits, new tab, noopener, label "… — DART, 새 탭에서 열려요", new one starts "새 공시 · "), ≥ 44 px; 공시 모두 보기 (6)',
          len(q['rows']) == 2 and all(re.match(r'^https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=\d{14}$', x[0]) and x[1] == '_blank' and 'noopener' in x[2] and x[3].endswith('— DART, 새 탭에서 열려요') and x[4] >= 44 for x in q['rows'])
          and q['rows'][0][3].startswith('새 공시 · ') and q['all'] == '공시 모두 보기 (6)', q)
    E.allow = ['404', 'Failed to load resource']           # the stock page's own /api/stock/* are not mocked here
    pg.click('#sheet .dc-all'); pg.wait_for_timeout(900)
    sp = pg.evaluate("() => ({ open: !!(window.KHStock && KHStock.isOpen()), sheet: document.getElementById('sheet').classList.contains('open'), hash: location.hash, tab: (document.querySelector('.sp-tabs [aria-selected=\"true\"], [role=\"tab\"][aria-selected=\"true\"][data-tab]') || {}).dataset, kind: [...document.querySelectorAll('.sp-nwseg button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.kind) })")
    check('공시 모두 보기 → the stock page opens on 뉴스·공시 › 공시, the quick view closes', sp['open'] and not sp['sheet'] and sp['hash'] == '#s-005930' and sp['kind'] == ['disc'], sp)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    check('no console errors (tooltip · quick view · stock page)', not E.items, E.items[:3])
    E.allow = []
    ctx.close()

    # ── 4 · settings: 지도에 표시할 종류 changes the corners; one stays; 공시 보기 off → nothing shows, nothing is fetched ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=E)
    n0 = pg.evaluate("KH.marks.get('disc').size")
    pg.click('#moreBtn'); pg.wait_for_timeout(200)
    chips = pg.evaluate("[...document.querySelectorAll('[data-set=\"discKinds\"] .kchip')].map(b => [b.textContent, b.getAttribute('aria-pressed')])")
    check('settings: 지도에 표시할 종류 = 실적 · 주요 on, 정기 · 지분 · 기타 off, each with its map-stock count', [c[1] for c in chips] == ['true', 'true', 'false', 'false', 'false'] and all(re.match(r'^(실적|주요|정기|지분|기타)\d+$', c[0]) for c in chips), chips)
    pg.click('[data-set="discKinds"] .kchip[data-si="2"]'); pg.wait_for_timeout(400)
    n1 = pg.evaluate("KH.marks.get('disc').size")
    st = pg.evaluate("localStorage.getItem('khm.set.discKinds')")
    check('add 정기 → more stocks marked; stored as "실적,주요,정기"', n1 > n0 and json.loads(st) == '실적,주요,정기', f'{n0} → {n1} {st}')
    for si in ('0', '1', '2'):
        pg.click(f'[data-set="discKinds"] .kchip[data-si="{si}"]'); pg.wait_for_timeout(150)
    p2 = pg.evaluate("[...document.querySelectorAll('[data-set=\"discKinds\"] .kchip')].map(b => b.getAttribute('aria-pressed'))")
    check('the last kind cannot be turned off ("하나는 남겨 둬야 해요")', p2 == ['false', 'false', 'true', 'false', 'false'], p2)
    pg.click('[data-set="discKinds"] .kchip[data-si="0"]'); pg.click('[data-set="discKinds"] .kchip[data-si="1"]'); pg.click('[data-set="discKinds"] .kchip[data-si="2"]'); pg.wait_for_timeout(300)
    k0 = mock('/__stats').get('/api/disclosures/today', 0)
    pg.click('[data-set="disc"] .swbtn'); pg.wait_for_timeout(500)
    o = pg.evaluate("() => ({ dm: document.querySelectorAll('#map .dm').length, chip: !!document.querySelector('#stage-tools .dc-hchip'), lg: !!document.querySelector('#legend .dc-lg'), tab: !!document.getElementById('news-t-disc'), multi: document.getElementById('news').classList.contains('multi'), foot: document.getElementById('foot-disc').hidden, kinds: document.querySelector('[data-set=\"discKinds\"]').classList.contains('off') })")
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(800)
    k1 = mock('/__stats').get('/api/disclosures/today', 0)
    check('공시 보기 off → no corners, chip, legend item, tab (the news card as before), footer line; kind chips greyed; no request on refresh',
          o['dm'] == 0 and not o['chip'] and not o['lg'] and not o['tab'] and not o['multi'] and o['foot'] and o['kinds'] and k1 == k0, f'{o} req {k0}→{k1}')
    pg.click('[data-set="disc"] .swbtn'); pg.wait_for_timeout(1200)
    o2 = pg.evaluate("() => ({ dm: document.querySelectorAll('#map .dm').length, tab: !!document.getElementById('news-t-disc') })")
    check('공시 보기 on again → corners and tab back', o2['dm'] > 0 and o2['tab'], o2)
    check('no console errors (settings)', not E.items, E.items[:3])
    ctx.close()

    # ── 5 · new dot: s within 30 min and after since; s = since → no dot; no s → "오늘"; nosince → no dot anywhere ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    pg.click('#news .dc-ktabs button[data-k="all"]'); pg.click('#news .dc-only'); pg.wait_for_timeout(200)
    nd = pg.evaluate("""() => { const d = KH.disclosures(), since = d.since, now = (() => { const k = new Date(KH.now() + 9 * 3600e3); return k.getUTCHours() * 60 + k.getUTCMinutes(); })();
      const want = r => !!(r.s && since && r.s > since && now - (+r.s.slice(0, 2) * 60 + +r.s.slice(3)) <= 30 && now - (+r.s.slice(0, 2) * 60 + +r.s.slice(3)) >= 0);
      const rows = [...document.querySelectorAll('#news .dc-row')].map(li => { const a = li.querySelector('.dc-tt a'), r = a.href.slice(-14), x = d.rows.find(y => y.r === r);
        return { dot: !!li.querySelector('.dc-dot'), want: x && want(x), t: li.querySelector('.dc-tm').textContent.replace('새 공시 ', ''), s: x && x.s, sr: (li.querySelector('.dc-tm .sr') || {}).textContent, label: a.getAttribute('aria-label') }; });
      return { rows, since, nDot: rows.filter(r => r.dot).length, wrong: rows.filter(r => r.dot !== r.want), atSince: d.rows.filter(r => r.s === since).length, noS: d.rows.filter(r => !r.s).length }; }""")
    check(f'new dot = s > since and ≤ 30 min ({nd["nDot"]} dots among {len(nd["rows"])} rows; since {nd["since"]})', not nd['wrong'] and nd['nDot'] > 0, nd['wrong'][:3])
    dotrow = next((r for r in nd['rows'] if r['dot']), None)
    check('a dot row: "새 공시" for screen readers in the time and the link label', dotrow and dotrow['sr'] == '새 공시 ' and dotrow['label'].startswith('새 공시 · ') and re.match(r'^\d\d:\d\d$', dotrow['t']), dotrow)
    check('rows at since have no dot; rows without s read "오늘"', all(not r['dot'] for r in nd['rows'] if r['s'] == nd['since']) and all(r['t'] == '오늘' for r in nd['rows'] if not r['s']) and nd['noS'] > 0, (nd['atSince'], nd['noS']))
    big = pg.evaluate("(() => { const m = KH.marks.get('disc'); return { new: m.get('005930').size, old: m.get('005490').size }; })()")
    check('삼성전자 (실적 4 min ago) gets the big corner, POSCO홀딩스 (12 min ago, 주요) too; the 지분 / old ones not', big['new'] == 'new' and big['old'] == 'new', big)
    ctx.close()
    mode('nosince')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    ns = pg.evaluate("() => ({ dots: document.querySelectorAll('.dc-dot').length, big: [...KH.marks.get('disc').values()].filter(v => v.size === 'new').length })")
    check('no since in the answer → no dot, no big corner', ns['dots'] == 0 and ns['big'] == 0, ns)
    ctx.close()

    # ── 6 · non-trading day: the latest weekday's list, labelled with its date ──
    mode('holiday')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    hd = pg.evaluate("""() => { const d = KH.disclosures(), [y, m, dd] = d.date.split('-').map(Number), wd = '일월화수목금토'[new Date(Date.UTC(y, m - 1, dd)).getUTCDay()];
      return { tab: document.querySelector('#news-t-disc .nw-tl').textContent, want: `${m}월 ${dd}일 (${wd}) 공시`, lg: document.querySelector('#legend .dc-lg').textContent, wantLg: `${m}/${dd} 공시`,
        times: [...document.querySelectorAll('#news .dc-tm')].slice(0, 3).map(t => t.textContent), dots: document.querySelectorAll('.dc-dot').length, chip: document.querySelector('.dc-hchip').getAttribute('aria-label'),
        mark: KH.marks.get('disc').get('005930').label, wantMark: `, ${m}월 ${dd}일 공시` }; }""")
    check(f'non-trading day: tab "{hd["tab"]}", legend "{hd["lg"][:12]}…", chip / tile labels name the day, no dot', hd['tab'] == hd['want'] and hd['lg'].startswith(hd['wantLg']) and hd['dots'] == 0
          and hd['chip'].startswith(hd['want'].split(' (')[0]) and hd['mark'].startswith(hd['wantMark']) and all(re.match(r'^\d\d:\d\d$', t) for t in hd['times']), hd)
    pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(150)
    r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + 30, r.y + 20]; })()")
    pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(300)
    th = pg.evaluate("(document.querySelector('#tip .dsc-h') || {}).textContent")
    check('non-trading day: tooltip head "M월 D일 공시 N건"', th and re.match(r'^\d{1,2}월 \d{1,2}일 공시\d+건$', th), th)
    check('no console errors (non-trading day)', not E.items, E.items[:3])
    ctx.close()

    # ── 7 · states: loading · error → retry · empty · stale ──
    mode('slow')
    ctx, pg = open_page(br, LIVE, 1280, 800, wait=400)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.click('#news-t-disc'); pg.wait_for_timeout(150)
    l = pg.evaluate("() => ({ sk: document.querySelectorAll('#news .dc-row.skel').length, at: document.querySelector('#news .nw-at').textContent, chip: document.querySelector('.dc-hchip').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-hchip').textContent, lg: (document.querySelector('#legend .dc-lg') || {}).textContent, dis: [...document.querySelectorAll('#news .dc-ktabs button, #news .dc-only')].every(b => b.getAttribute('aria-disabled') === 'true'), h: document.getElementById('news').offsetHeight })")
    pg.wait_for_selector('#news .dc-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    h2 = pg.evaluate("document.getElementById('news').offsetHeight")
    check('loading: skeleton rows, "불러오는 중", chip ring + "공시" (off), legend "공시 …", kind tabs + 지도 종목만 off, same card height after',
          l['sk'] >= 5 and l['at'] == '불러오는 중' and l['chip'] == 'true|공시' and l['lg'] == '공시 …' and l['dis'] and l['h'] == h2, f'{l} → {h2}')
    ctx.close()
    E.allow = ['503', 'Failed to load resource']
    E.items = []
    mode('fail')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    e = pg.evaluate("() => ({ msg: document.querySelector('#news-p-disc .nw-msg').textContent, at: document.querySelector('#news .nw-at').textContent, chip: document.querySelector('.dc-hchip').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-hchip').textContent + '|' + document.querySelector('.dc-hchip').title, lg: document.querySelector('#legend .dc-lg').textContent, more: document.querySelector('#news-p-disc .nw-more').hidden, dm: document.querySelectorAll('#map .dm').length, h: document.getElementById('news').offsetHeight })")
    check('error: "공시를 불러오지 못했어요" + 다시 시도, head "받은 목록 없음", chip "공시 !" (off, title), legend "공시 —", no corners',
          e['msg'].startswith('공시를 불러오지 못했어요DART 응답이 없었어요. 잠시 뒤 다시 눌러 주세요.다시 시도') and e['at'] == '받은 목록 없음' and e['chip'] == 'true|공시!|공시를 불러오지 못했어요' and e['lg'] == '공시 —' and e['more'] and e['dm'] == 0, e)
    pg.click('#news-p-disc .nw-msg .kasync'); pg.wait_for_timeout(500)
    st1 = pg.evaluate("(document.querySelector('#news-p-disc .nw-msg .kasync') || {}).dataset.st")
    check('retry while it still fails → "아직 안 돼요 · 다시" (!) on the key', st1 == 'fail', st1)
    mode('ok')
    pg.click('#news-p-disc .nw-msg .kasync'); pg.wait_for_selector('#news .dc-row:not(.skel)', timeout=8000); pg.wait_for_timeout(300)
    e2 = pg.evaluate("() => ({ dm: document.querySelectorAll('#map .dm').length, h: document.getElementById('news').offsetHeight })")
    check('retry that works → the list, the corners; card height unchanged', e2['dm'] > 0 and e2['h'] == e['h'], f"{e['h']}→{e2}")
    E.allow = []
    ctx.close()
    mode('empty')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    em = pg.evaluate("() => ({ msg: document.querySelector('#news-p-disc .nw-msg').textContent, chip: document.querySelector('.dc-hchip').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-hchip').textContent, lg: !!document.querySelector('#legend .dc-lg'), dm: document.querySelectorAll('#map .dm').length })")
    check('empty: a 휴장일 / 아침 / plain message, chip "공시 0" (off), no legend item, no corners',
          re.match(r'^(오늘은 휴장일이라 공시가 거의 없어요|아직 오늘 공시가 없어요|아직 공시가 없어요)', em['msg']) and em['chip'] == 'true|공시0' and not em['lg'] and em['dm'] == 0, em)
    ctx.close()
    mode('stale')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    so = pg.evaluate("() => ({ cls: document.querySelector('#news .nw-at').className, at: document.querySelector('#news .nw-at').textContent, key: !!document.querySelector('#news .nw-at .kasync'), bang: !!document.querySelector('.dc-hchip .dc-bad'), rows: document.querySelectorAll('#news .dc-row').length })")
    check('stale (server stale, asOf 20 min old): list stays, amber ! "HH:MM 기준 · N분째 못 받았어요" + 다시 시도, chip "!"',
          'stale' in so['cls'] and re.search(r'\d\d:\d\d 기준 · 2\d분째 못 받았어요', so['at']) and so['key'] and so['bang'] and so['rows'] > 0, so)
    ctx.close()

    # ── 8 · ETag: the browser revalidates, a 304 keeps the list and takes the time from x-as-of ──
    mode('etag')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    before = pg.evaluate("() => ({ n: KH.disclosures().rows.length, asOf: KH.disclosures().asOf })")
    pg.wait_for_timeout(1200)
    pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(800)
    after = pg.evaluate("() => ({ n: KH.disclosures().rows.length, asOf: KH.disclosures().asOf, rows: document.querySelectorAll('#news .dc-row').length })")
    st = mock('/__stats')
    check('ETag: the next request sends If-None-Match and gets a 304; the list stays, asOf from x-as-of', st.get('304', 0) >= 1 and after['n'] == before['n'] and after['rows'] > 0 and after['asOf'] and after['asOf'] > before['asOf'], f"{st.get('304')} {before} {after}")
    ctx.close()

    # ── 9 · a list that arrives while the reader is in the pane waits; corners update at once; 화려하게: the new corner folds in ──
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800, motion='fancy')
    disc_tab(pg)
    first = pg.evaluate("document.querySelector('#news .dc-row .dc-tt a').textContent")
    pg.hover('#news .dc-row:nth-child(3) .dc-tt'); pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(700)
    during = pg.evaluate("() => ({ t: document.querySelector('#news .dc-row .dc-tt a').textContent, pop: document.querySelectorAll('#map .dm.pop').length, title: document.querySelector('#news-t-disc .nw-tn').textContent })")
    pg.mouse.move(5, 5); pg.wait_for_timeout(400)
    after = pg.evaluate("document.querySelector('#news .dc-row .dc-tt a').textContent")
    check('a new list waits while the pointer is in the pane; the map takes it at once (화려하게: the new corner folds in, .pop)',
          during['t'] == first and after != first and re.search(r'시험 [2-9]\)', after) and during['pop'] >= 1, f'{first[:12]} / {during} / {after[:16]}')
    ctx.close()

    # ── 10 · replay: today → rows seen by its time; another day → no corners / chip, legend note ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    rp = pg.evaluate("""async () => { const d = KH.disclosures(), k = new Date(KH.now() + 9 * 3600e3), now = k.getUTCHours() * 60 + k.getUTCMinutes(), t = Math.max(0, now - 15);
      const hm = String(Math.floor(t / 60)).padStart(2, '0') + String(t % 60).padStart(2, '0');
      KH.setReplay({ t: hm, date: d.date, prices: new Map() }); await new Promise(r => setTimeout(r, 400));
      const hhmm = hm.slice(0, 2) + ':' + hm.slice(2), shown = [...document.querySelectorAll('#news .dc-row .dc-tm')].map(x => x.textContent.replace('새 공시 ', ''));
      const res = { hhmm, at: document.querySelector('#news .nw-at').textContent, shown, marks: KH.marks.get('disc').size, expectMarks: new Set(d.rows.filter(r => r.s && r.s <= hhmm && ['실적', '주요'].includes(r.k)).map(r => r.c)).size,
        sam: !!(KH.marks.get('disc').get('005930') && KH.marks.get('disc').get('005930').size) };
      KH.setReplay({ t: '1030', date: '2026-01-02', prices: new Map() }); await new Promise(r => setTimeout(r, 400));
      res.other = { dm: document.querySelectorAll('#map .dm').length, chip: !!document.querySelector('#stage-tools .dc-hchip'), lg: (document.querySelector('#legend .dc-lg') || {}).textContent, at: document.querySelector('#news .nw-at').textContent };
      KH.setReplay(null); await new Promise(r => setTimeout(r, 400));
      res.back = document.querySelectorAll('#map .dm').length; return res; }""")
    check(f'replay of today ({rp["hhmm"]}): head "다시 보기 중 · HH:MM까지 들어온 공시만", only rows seen by then, corners from those',
          rp['at'] == f'다시 보기 중 · {rp["hhmm"]}까지 들어온 공시만' and all(t == '오늘' or t <= rp['hhmm'] for t in rp['shown']) and rp['marks'] == rp['expectMarks'], rp)
    check('replay of another day: no corners, no chip, legend "다시 보기 중에는 오늘 공시만 보여요", head "다시 보기 중 · 지금 공시예요"; back to live → corners',
          rp['other']['dm'] == 0 and not rp['other']['chip'] and rp['other']['lg'] == '다시 보기 중에는 오늘 공시만 보여요' and rp['other']['at'] == '다시 보기 중 · 지금 공시예요' and rp['back'] > 0, rp['other'])
    ctx.close()

    # ── 11 · panel: tabs, counts, 지도 종목만, card height, keyboard, credit lines, chip → quick view, rows light tiles ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    cnt = pg.evaluate("""() => { const d = KH.disclosures(), map = new Set(KH.mapCodes()), m = (a) => { const s = new Set(); return a.filter(r => { const k = r.c + '|' + r.t; if (s.has(k)) return false; s.add(k); return true; }); };
      const on = d.rows.filter(r => map.has(r.c)), f = (a, k) => m(k === 'main' ? a.filter(r => r.k === '실적' || r.k === '주요') : k === 'all' ? a : a.filter(r => r.k === k)).length;
      const tabs = Object.fromEntries([...document.querySelectorAll('#news .dc-ktabs button')].map(b => [b.dataset.k, +b.querySelector('small').textContent]));
      return { tabs, want: Object.fromEntries(['main', '정기', '지분', '기타', 'all'].map(k => [k, f(on, k)])), title: +document.querySelector('#news-t-disc .nw-tn').textContent, only: +document.querySelector('#news .dc-only .nw-n').textContent, onlyWant: new Set(on.map(r => r.c)).size }; }""")
    check('kind tab counts = merged rows of map stocks per kind; title count = 실적 · 주요; 지도 종목만 = map stocks with a filing',
          cnt['tabs'] == cnt['want'] and cnt['title'] == cnt['want']['main'] and cnt['only'] == cnt['onlyWant'], cnt)
    hs = []
    for k in ('main', '정기', '지분', '기타', 'all'):
        pg.click(f'#news .dc-ktabs button[data-k="{k}"]'); pg.wait_for_timeout(120)
        hs.append(pg.evaluate("() => [document.getElementById('news').offsetHeight, getComputedStyle(document.querySelector('#news .dc-row .dc-kb')).display]"))
    pg.click('#news-t-news'); pg.wait_for_timeout(200); hn = pg.evaluate("document.getElementById('news').offsetHeight")
    pg.click('#news-t-disc'); pg.wait_for_timeout(200)
    check('card height the same on every kind tab and on 시장 뉴스; single-kind tabs hide the kind badge', len(set(x[0] for x in hs)) == 1 and hs[0][0] == hn and [x[1] != 'none' for x in hs] == [True, False, False, False, True], f'{hs} news {hn}')
    pg.click('#news .dc-ktabs button[data-k="main"]')
    pg.click('#news .dc-only'); pg.wait_for_timeout(200)
    off = pg.evaluate("() => ({ pressed: document.querySelector('#news .dc-only').getAttribute('aria-pressed'), x: document.querySelectorAll('#news .dc-chipx').length, rows: document.querySelectorAll('#news .dc-row').length, names: [...document.querySelectorAll('#news .dc-chipx .dc-cn')].map(x => x.textContent).filter(t => /^\\d{6}$/.test(t)).length })")
    pg.wait_for_timeout(600)
    off2 = pg.evaluate("[...document.querySelectorAll('#news .dc-chipx')].map(x => x.getAttribute('aria-label'))")
    check('지도 종목만 off → all listed companies; off-map stocks get an outlined name + 시장 chip ("· 종목 페이지"), names from names.json',
          off['pressed'] == 'false' and off['rows'] > 0 and (off['x'] == 0 or all(re.match(r'^\S.* (코스피|코스닥) · 종목 페이지$', a) for a in off2)), f'{off} {off2[:2]}')
    pg.click('#news .dc-ktabs button[data-k="all"]'); pg.wait_for_timeout(200)
    xs = pg.evaluate("document.querySelectorAll('#news .dc-chipx').length")
    check('전체 · 지도 종목만 off shows off-map stocks', xs > 0, xs)
    pg.click('#news .dc-only'); pg.click('#news .dc-ktabs button[data-k="main"]'); pg.wait_for_timeout(200)
    # keyboard
    pg.focus('#news-t-disc'); pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(150)
    kb = pg.evaluate("() => [document.activeElement.id, document.getElementById('news').dataset.feed, localStorage.getItem('khm.feedTab')]")
    pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(150)
    seq = []
    for _ in range(10):
        seq.append(pg.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a);
          const k = a.getAttribute('role') === 'tab' ? 'title' : a.closest('.dc-ktabs') ? 'kind' : a.classList.contains('dc-only') ? 'only' : a.closest('.dc-tt') ? 'link' : a.classList.contains('dc-chip') ? 'chip' : a.classList.contains('nw-more') ? 'more' : a.tagName;
          return [k, cs.outlineStyle !== 'none' ? parseFloat(cs.outlineWidth) : 0]; }"""))
        pg.keyboard.press('Tab')
    kinds = [s[0] for s in seq]
    check('title tabs ←/→ (remembered in khm.feedTab); Tab: title → kinds ×5 → 지도 종목만 → chip → link …; ring 3px',
          kb == ['news-t-news', 'news', '"news"'] and kinds[:9] == ['title', 'kind', 'kind', 'kind', 'kind', 'kind', 'only', 'chip', 'link'] and all(s[1] == 3 for s in seq), f'{kb} {kinds}')
    pg.focus('#news .dc-row:first-child .dc-tt a'); pg.wait_for_timeout(150)
    lit = pg.evaluate("() => ({ row: document.querySelector('#news .dc-row').dataset.c, on: [...document.querySelectorAll('#map .tile.nhl')].map(t => t.dataset.c) })")
    check('focus on a row lights exactly its tile', lit['on'] == [lit['row']], lit)
    pg.focus('#news .dc-row:first-child .dc-chip'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
    qv = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), label: document.getElementById('sheet').getAttribute('aria-label'), block: !!document.querySelector('#sheet .dsc') })")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    back = pg.evaluate("document.activeElement.classList.contains('dc-chip')")
    check('chip Enter → the quick view with its 공시 block; Esc → focus back on the chip', qv['open'] and qv['block'] and back, f'{qv} {back}')
    links = pg.evaluate("() => [...document.querySelectorAll('#news .dc-tt a')].map(a => [a.target, a.rel, /^https:\\/\\/dart\\.fss\\.or\\.kr\\/dsaf001\\/main\\.do\\?rcpNo=\\d{14}$/.test(a.href), a.getAttribute('aria-label')])")
    check('every row title: one DART link, new tab, noopener, label "종목 제목 — DART, 새 탭에서 열려요"', links and all(l[0] == '_blank' and 'noopener' in l[1] and l[2] and l[3].endswith('— DART, 새 탭에서 열려요') for l in links), len(links))
    cred = pg.evaluate("() => [document.querySelector('#news-p-disc .nw-ft small').textContent, document.getElementById('foot-disc').textContent, document.getElementById('foot-disc').hidden]")
    check('credit lines: card "공시: 금융감독원 DART (OpenDART) — 제목 · 종류만…", footer "공시: 금융감독원 DART (제목 · 링크만)"',
          cred[0].startswith('공시: 금융감독원 DART (OpenDART) — 제목 · 종류만 보여 드려요.') and cred[1] == '공시: 금융감독원 DART (제목 · 링크만)' and not cred[2], cred)
    pg.click('#news-p-disc .nw-more'); pg.wait_for_timeout(300)
    mo = pg.evaluate("() => ({ rows: document.querySelectorAll('#news .dc-row').length, lab: document.querySelector('#news-p-disc .nw-more').getAttribute('aria-label') })")
    check('더보기 → up to 30 rows, 접기', mo['rows'] == min(30, cnt['want']['main']) and mo['lab'] == '접기', mo)
    check('no console errors (panel)', not E.items, E.items[:3])
    ctx.close()
    # PC fill: the tab keeps the card's height (fills to the side end, or min 5 rows) at 1280 and 1920 (two columns)
    for w, h in ((1280, 800), (1920, 1080)):
        ctx, pg = open_page(br, LIVE, w, h)
        disc_tab(pg)
        g = pg.evaluate(GEO_JS)
        whole = g['perCol'] * g['rh'] <= g['listH'] + 1 and g['listH'] - g['perCol'] * g['rh'] < g['rh']
        check(f'fill {w}x{h}: {g["perCol"]} rows' + (' × 2' if g['two'] else '') + f', card end {g["bottom"]:.0f} vs side {g["sideEnd"]:.0f}',
              (abs(g['bottom'] - g['sideEnd']) <= 1.5 or g['perCol'] == 5) and g['perCol'] >= 5 and whole and g['two'] == (w == 1920), g)
        ctx.close()

    # ── 12 · phone: chip 32 (hit 44), corners on the map, card 5 rows + 더보기, kind tabs 40, chips 32 (44), quick view rows ≥ 54 ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 390, 844)
    ph0 = pg.evaluate("() => ({ chipH: document.querySelector('.dc-hchip').getBoundingClientRect().height, hit: getComputedStyle(document.querySelector('.dc-hchip'), '::before').height, sb: document.querySelector('.stagebar').offsetHeight, dm: document.querySelectorAll('#map .dm').length })")
    disc_tab(pg)
    ph = pg.evaluate("""() => { const n = document.getElementById('news'), rows = [...n.querySelectorAll('.dc-row')], chip = n.querySelector('.dc-chip'), tab = n.querySelector('.dc-ktabs button'), tt = rows[0].querySelector('.dc-tt'), cs = getComputedStyle(tt);
      return { rows: rows.length, clamp: cs.webkitLineClamp, fs: cs.fontSize, chipH: chip.getBoundingClientRect().height, chipHit: getComputedStyle(chip, '::before').height, tabH: tab.getBoundingClientRect().height,
        title: n.querySelector('.nw-tt button').getBoundingClientRect().height, more: n.querySelector('#news-p-disc .nw-more').getBoundingClientRect().height }; }""")
    check('phone: header chip 32 (hit 44) in one header row, corners drawn; card 5 rows, titles 15 px two lines, chips 32 (hit 44), kind tabs 40, title tabs 40, 더보기 42',
          round(ph0['chipH']) == 32 and ph0['hit'] == '44px' and ph0['sb'] <= 46 and ph0['dm'] > 0 and ph['rows'] == 5 and ph['clamp'] == '2' and ph['fs'] == '15px' and round(ph['chipH']) == 32
          and ph['chipHit'] == '44px' and ph['tabH'] >= 40 and ph['title'] >= 40 and ph['more'] >= 42, f'{ph0} {ph}')
    pg.tap('#news .dc-row .dc-chip'); pg.wait_for_timeout(500)
    qs = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), rows: [...document.querySelectorAll('#sheet .dsc a.dr')].map(a => Math.round(a.getBoundingClientRect().height)), all: Math.round(document.querySelector('#sheet .dc-all').getBoundingClientRect().height), hl: document.querySelectorAll('#map .tile.nhl').length })")
    check('phone chip → bottom sheet with the 공시 block: rows ≥ 54 px, 공시 모두 보기 44 px, no map highlight', qs['open'] and qs['rows'] and all(x >= 54 for x in qs['rows']) and qs['all'] >= 44 and qs['hl'] == 0, qs)
    ctx.close()

    # ── 13 · reduced motion: no corner / row animation, indicators 0s ──
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800, motion='reduced')
    disc_tab(pg)
    pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(600)
    rm = pg.evaluate("() => ({ anim: [...document.querySelectorAll('#map .dm, #news .dc-row')].filter(x => getComputedStyle(x).animationName !== 'none').length, ind: getComputedStyle(document.querySelector('#news .dc-ktabs'), '::before').transitionDuration, bar: getComputedStyle(document.querySelector('#news .nw-tt button'), '::after').transitionDuration })")
    check('reduced motion: no corner / row animation, kind indicator and title bar 0s', rm['anim'] == 0 and set(rm['ind'].replace(' ', '').split(',')) <= {'0s'} and set(rm['bar'].replace(' ', '').split(',')) <= {'0s'}, rm)
    ctx.close()

    # ── 14 · a Worker without the route (404): nothing of this shows, the news card as before, one request ──
    E.allow = ['404', 'Failed to load resource']
    E.items = []
    mode('none')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(800)
    g4 = pg.evaluate("() => ({ tab: !!document.getElementById('news-t-disc'), multi: document.getElementById('news').classList.contains('multi'), h2: !!document.querySelector('#news h2'), chip: !!document.querySelector('.dc-hchip'), dm: document.querySelectorAll('#map .dm').length, lg: !!document.querySelector('#legend .dc-lg'), foot: document.getElementById('foot-disc').hidden })")
    n4 = mock('/__stats').get('/api/disclosures/today', 0)
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
    n5 = mock('/__stats').get('/api/disclosures/today', 0)
    check('404: no tab (the news card with its h2 as before), no chip, corners, legend item, footer line; no more requests', not g4['tab'] and not g4['multi'] and g4['h2'] and not g4['chip'] and g4['dm'] == 0 and not g4['lg'] and g4['foot'] and n4 == 1 and n5 == 1, f'{g4} {n4}→{n5}')
    E.allow = []
    ctx.close()

    # ── 15 · world tab: no chip / polling there; back → chip again ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(500)
    k0 = mock('/__stats').get('/api/disclosures/today', 0)
    w = pg.evaluate("() => ({ chip: !!document.querySelector('#stage-tools .dc-hchip'), foot: document.getElementById('foot').textContent.includes('공시: 금융감독원') })")
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(500)
    k1 = mock('/__stats').get('/api/disclosures/today', 0)
    pg.click('.tabs button[data-mkt="Q"]'); pg.wait_for_timeout(700)
    q = pg.evaluate("() => ({ chip: +((document.querySelector('#stage-tools .dc-n') || {}).textContent || -1), want: KH.mapCodes().filter(c => KH.marks.get('disc').has(c)).length })")
    check('world tab: no chip, no credit, no request on refresh; 코스닥 → the chip counts the 코스닥 map', not w['chip'] and not w['foot'] and k1 == k0 and q['chip'] == q['want'] and q['want'] > 0, f'{w} {k0}→{k1} {q}')
    ctx.close()

    # ── 16 · snapshot (dist/): the tab says "실시간 버전에서", no chip / corners / legend / footer, no fixture rows in the build ──
    E.items = []
    ctx, pg = open_page(br, SNAP, 1280, 800, errors=E)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.click('#news-t-disc'); pg.wait_for_timeout(300)
    sn = pg.evaluate("() => ({ text: document.getElementById('news-p-disc').textContent, href: (document.querySelector('#news-p-disc a') || {}).href, chip: !!document.querySelector('.dc-hchip'), dm: document.querySelectorAll('#map .dm').length, lg: !!document.querySelector('#legend .dc-lg'), foot: document.getElementById('foot-disc') ? document.getElementById('foot-disc').hidden : true, over: document.documentElement.scrollWidth - innerWidth, tabs: [...document.querySelectorAll('#news .nw-tt button')].map(b => b.textContent) })")
    check('snapshot: tabs 시장 뉴스 · 오늘 공시, "공시는 실시간 버전에서 볼 수 있어요" + LIVE_URL; no chip, corners, legend item, footer line; no console errors',
          sn['tabs'] == ['시장 뉴스', '오늘 공시'] and '공시는 실시간 버전에서 볼 수 있어요' in sn['text'] and sn['href'] == 'https://panse.pages.dev/' and not sn['chip'] and sn['dm'] == 0 and not sn['lg'] and sn['foot'] and sn['over'] == 0 and not E.items, f'{sn} {E.items[:2]}')
    ctx.close()
    html = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
    check('dist/index.html carries no disclosure rows (no rcpNo link, no fixture title)', 'rcpNo=2026' not in html and '연결재무제표기준영업(잠정)실적' not in html)

    # ── 17 · busy day (1,800 rows): corners in time, at 300 and 전체 (2,700 tiles) ──
    mode('busy')
    ctx, pg = open_page(br, LIVE, 1440, 900, market='ALL', store={'topN': 'all'}, wait=3500)
    pf = pg.evaluate("""() => { const m = KH.marks.get('disc'); const t0 = performance.now(); for (let i = 0; i < 5; i++) KH.marks.set('disc', new Map(m)); const t1 = performance.now();
      return { ms: Math.round((t1 - t0) / 5 * 10) / 10, tiles: document.querySelectorAll('#map .tile').length, marks: m.size, rows: KH.disclosures().rows.length }; }""")
    t0 = time.time(); pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(50)
    check(f'busy day: {pf["rows"]} rows, {pf["marks"]} marked stocks, {pf["tiles"]} tiles — repainting every corner {pf["ms"]} ms (< 60)', pf['ms'] < 60 and pf['tiles'] > 2000 and pf['rows'] > 1000, pf)
    ctx.close()


def baseline(br):
    """no filings (rows: []) → the map, the side cards and the legend are pixel-identical to the build without this feature"""
    wt = pathlib.Path(tempfile.mkdtemp(prefix='disc_base_')) / 'wt'
    subprocess.run(['git', 'worktree', 'add', '--detach', str(wt), BASE_REV], cwd=ROOT, capture_output=True, check=True)
    subprocess.run([sys.executable, 'scripts/build_page.py'], cwd=wt, capture_output=True, check=True)
    tmp = wt / 'web'
    subprocess.run(['fuser', '-k', f'{BPORT}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(MOCK), str(BPORT)], env=dict(os.environ, MOCK_WEB=str(tmp)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                mock('/__reset', BASE); break
            except Exception:
                time.sleep(0.1)
        mock('/__mode?disc=empty', BASE)
        mode('empty')
        for w, h in ((1280, 800), (1920, 1080), (390, 844)):
            shots = {}
            for name, url in (('base', BASE), ('new', LIVE)):
                ctx, pg = open_page(br, url, w, h, 'base', motion='reduced', store={'clock': False}, wait=2200)
                pg.add_style_tag(content='#tip{display:none!important}')
                shots[name] = {k: pg.locator(sel).screenshot() for k, sel in (('map', '#map'), ('legend', '#legend'), ('side', 'main.layout > .side > section:nth-child(1)'),
                                                                              ('side2', 'main.layout > .side > section:nth-child(2)'), ('side3', 'main.layout > .side > section:nth-child(3)'))}
                shots[name]['geo'] = pg.evaluate("() => ['#map', '#legend', ...document.querySelectorAll('main.layout > .side > section')].map(s => { const r = (typeof s === 'string' ? document.querySelector(s) : s).getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)]; })")
                shots[name]['dom'] = pg.evaluate("() => [...document.querySelectorAll('#map .node')].map(n => [n.className, n.style.cssText, n.getAttribute('aria-label') || '', n.textContent, n.style.color]).join('\\n') + document.getElementById('legend').innerHTML")
                ctx.close()
            diff = {}
            for k in ('map', 'legend', 'side', 'side2', 'side3'):
                a, b = (Image.open(io.BytesIO(shots[x][k])).convert('RGB') for x in ('base', 'new'))
                if a.size != b.size:
                    diff[k] = ('size', a.size, b.size); continue
                d = ImageChops.difference(a, b).convert('L')
                hist = d.histogram()
                diff[k] = (sum(hist[1:]), max((i for i, v in enumerate(hist) if v), default=0))   # (pixels that differ, largest channel step)
            # boxes: the map and the legend in place; the side cards keep their size (on phones they sit under the news card, which is taller now)
            gb, gn = shots['base']['geo'], shots['new']['geo']
            same_geo = gb[:2] == gn[:2] and [g[2:] for g in gb[2:]] == [g[2:] for g in gn[2:]]
            ok = all(isinstance(v[0], int) and v[1] <= 2 for v in diff.values()) and same_geo and shots['base']['dom'] == shots['new']['dom']
            check(f'no filings → {w}x{h}: map · legend · side cards same DOM, same boxes, pixels equal within 2/255 raster noise vs {BASE_REV} (differing px, max step: {diff})', ok,
                  f"geo {same_geo} dom {shots['base']['dom'] == shots['new']['dom']} {gb} {gn}")
    finally:
        srv.terminate(); srv.wait(5)
        subprocess.run(['git', 'worktree', 'remove', '--force', str(wt)], cwd=ROOT, capture_output=True)


def shots(br):
    mode('ok')
    for w, h, th in [(1280, 800, 'base'), (1280, 800, 'glass-dark'), (1920, 1080, 'base'), (1920, 1080, 'glass-light')]:
        ctx, pg = open_page(br, LIVE, w, h, th)
        disc_tab(pg)
        pg.evaluate("scrollTo(0, 0)"); pg.wait_for_timeout(200)
        pg.screenshot(path=f'/tmp/dis_live_{w}_{th}.png', full_page=True)
        r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + 40, r.y + 30]; })()")
        pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(400)
        pg.screenshot(path=f'/tmp/dis_live_{w}_{th}_tip.png')
        pg.mouse.move(3, 3); pg.click('#stage-tools .dc-hchip'); pg.wait_for_timeout(300)
        pg.evaluate("document.getElementById('news').scrollIntoView({block: 'end'})"); pg.wait_for_timeout(200)
        pg.hover('#news .dc-row:nth-child(2) .dc-tt'); pg.wait_for_timeout(300)
        pg.screenshot(path=f'/tmp/dis_live_{w}_{th}_chip.png')
        ctx.close()
    for th in ('base', 'paper'):
        ctx, pg = open_page(br, LIVE, 390, 844, th)
        pg.screenshot(path=f'/tmp/dis_live_390_{th}_map.png')
        disc_tab(pg)
        pg.evaluate("document.getElementById('news').scrollIntoView({block: 'start'}); scrollBy(0, -70)"); pg.wait_for_timeout(300)
        pg.screenshot(path=f'/tmp/dis_live_390_{th}_card.png')
        pg.tap('#news .dc-row .dc-chip'); pg.wait_for_timeout(500)
        pg.screenshot(path=f'/tmp/dis_live_390_{th}_quick.png')
        ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(MOCK), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(br)
            baseline(br)
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
