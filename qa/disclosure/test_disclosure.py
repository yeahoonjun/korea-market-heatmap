#!/usr/bin/env python3
"""QA for the 공시 배지 (src/disclosure, docs/standards/disclosure.md — C안) on the built pages.

  python3 scripts/build_page.py && python3 qa/disclosure/test_disclosure.py [--shots]

Starts qa/news/mock_api.py on DISC_QA_PORT (default 9051; serves web/ + /api/news + /api/disclosures/today built from the snapshot at
request time — modes in its docstring) and, for the "no filings → the map as before" check, a second one on DISC_QA_BASE_PORT (9052)
serving the web/ of git rev DISC_QA_BASE (default: main) with no disclosure route. --shots writes qa/shots/disc_toggle/*.png. Exit 1 on a fail.

The map switch (오늘 공시 tab, ux/disc-toggle 2026-11-15) is checked as role=switch + aria-checked; its count is .dc-ln "· N종목".
DISC_QA_BASE=HEAD compares the working tree's build with the last commit's (use it while changing this feature: main may predate it).
The baseline check is known to be flaky (a late font / ticker frame) — rerun once before chasing a single failure there. Since ux/std-news
both builds get one more fit after the fonts (the template's industry-header label can miss its first fit — main too), a size is measured
twice at most, and the side cards are shot with the news card hidden (its wrapped titles end on fractional pixels on phones).
design() (ux/std-news, design.md): token sizes, the kind underline on KH.ui.seg, 더보기 through KHNews.fold, counts that swap only with a
new answer, the tooltip's 공시 block on the glass plate. --only=design | --only=baseline runs that section alone.
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
PORT = int(os.environ.get('DISC_QA_PORT', 9051))            # ux/std-news range 9050–9059
BPORT = int(os.environ.get('DISC_QA_BASE_PORT', 9052))
BASE_REV = os.environ.get('DISC_QA_BASE', 'main')
LIVE = f'http://127.0.0.1:{PORT}/'
BASE = f'http://127.0.0.1:{BPORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SIZES = [(360, 740), (390, 844), (768, 1024), (1280, 800), (1920, 1080)]
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SHOTS = '--shots' in sys.argv
ONLY = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--only=')), '')   # --only=design | baseline | refresh: that section alone
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


def open_page(br, url, w, h, theme='base', motion='standard', errors=None, market='K', store=None, wait=1800, clock=False):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(store or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    if clock:
        pg.clock.install()
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
TEXT_SEL = ['#news .nw-ftabs > button', '#news .nw-ftabs .nw-tn', '#news .nw-at span', '#news .dc-ktabs > button', '#news .dc-ktabs small', '#news .dc-only',
            '#news .dc-only .nw-n', '#news .dc-row .dc-tm', '#news .dc-kb', '#news .dc-chip', '#news .dc-chip b', '#news .dc-chipx', '#news .dc-chipx small',
            '#news .dc-tt a', '#news .dc-x', '#news-p-disc .nw-ft small', '#news-p-disc .nw-msg b', '#news-p-disc .nw-msg small', '#news .dc-lit .dc-lw',
            '#news .dc-lit .dc-ln', '#legend .dc-lg', '#legend .dc-lg b', '#legend .dc-lg2', '#foot-disc']
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


# wait for the running CSS transitions (switch knob · fill, tile dim filters) to end — a loaded machine is slower than a fixed wait
SETTLE_JS = "() => Promise.race([Promise.all(document.getAnimations().filter(a => a instanceof CSSTransition).map(a => a.finished.catch(() => 0))), new Promise(r => setTimeout(r, 3000))])"


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
                pg.click('#news .dc-lit'); pg.wait_for_timeout(250)                     # the map switch on (hovered: the --fill-1 tint behind the label)
                worst_of(contrast[th], pg.evaluate(CONTRAST_JS, ['#news .dc-lit .dc-lw', '#news .dc-lit .dc-ln']))
                pg.click('#news .dc-lit'); pg.wait_for_timeout(150)
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

    # ── 2 · tiles: corner sizes, aria-label; the map switch (오늘 공시 tab) lights exactly the marked stocks (AND search), the table ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    sz = pg.evaluate(SIZE_JS)
    check(f'corners follow §3-2 sizes and tile aria-labels say "오늘 공시 N건" ({sz["drawn"]} drawn, {sz["tiny"]} too small, {sz["marked"]} marked)', sz['nbad'] == 0 and sz['drawn'] > 0, sz)
    hd0 = pg.evaluate("() => { const st = document.getElementById('stage-tools'); return { kids: st.children.length, w: st.offsetWidth, any: document.querySelectorAll('.dc-hchip').length, inTab: !!document.querySelector('#news-p-disc .dc-sub .dc-lit') }; }")
    check('the map header has no 공시 chip (#stage-tools empty, no box); the map switch lives in the 오늘 공시 tab', hd0['kids'] == 0 and hd0['w'] == 0 and hd0['any'] == 0 and hd0['inTab'], hd0)
    disc_tab(pg)
    c = pg.evaluate("""() => { const m = KH.marks.get('disc'), codes = KH.mapCodes(); const want = codes.filter(c => m.has(c)).length, b = document.querySelector('#news .dc-lit');
      const marksOk = [...m.entries()].every(([c, v]) => KH.disclosures(c).some(x => (KH.getSetting('discKinds') || []).includes(x.k)));
      const sub = [...document.querySelector('#news-p-disc .dc-sub').children].map(e => e.className);
      return { want, chip: parseInt(b.querySelector('.dc-ln').textContent.replace(/\\D/g, '')), word: b.querySelector('.dc-lw').textContent, num: b.querySelector('.dc-ln').textContent, role: b.getAttribute('role'),
        label: b.getAttribute('aria-label'), pressed: b.getAttribute('aria-checked'), ap: b.getAttribute('aria-pressed'), dis: b.getAttribute('aria-disabled'), track: !!b.querySelector('.dc-trk .dc-knob'),
        legend: document.querySelector('#legend .dc-lg').textContent, marksOk, sub, swatch: !!b.querySelector('.dmsw'),
        nonMarked: KH.disclosures().rows.filter(r => !['실적','주요'].includes(r.k)).every(r => !m.has(r.c) || KH.disclosures(r.c).some(x => ['실적','주요'].includes(x.k))) }; }""")
    check('map switch (role=switch, aria-checked) in the tab row after 공시 종류 · 지도 종목만: "[corner] 지도에서 공시 종목만 밝게 · N종목 [track]", off; N = map stocks with a 실적 · 주요 filing = legend; marks = marked kinds only',
          c['chip'] == c['want'] and c['want'] > 0 and c['num'] == f"· {c['want']}종목" and c['word'] == '지도에서 공시 종목만 밝게' and c['swatch'] and c['track'] and c['role'] == 'switch' and c['ap'] is None
          and c['pressed'] == 'false' and c['dis'] is None
          and c['label'] == f"공시 있는 종목만 지도에서 밝게, {c['want']}종목" and str(c['want']) in c['legend'] and c['marksOk'] and c['nonMarked'] and c['sub'][-1] == 'dc-litw' and 'dc-only' in c['sub'][-2], c)
    pos0 = pg.evaluate("() => [document.querySelector('#news .dc-only').getBoundingClientRect().x, document.querySelector('#news-p-disc .dc-sub').offsetHeight, document.getElementById('news').offsetHeight, document.querySelector('#news .dc-lit .dc-lw').getBoundingClientRect().x]")
    pg.click('#news .dc-lit'); pg.wait_for_timeout(300); pg.evaluate(SETTLE_JS)
    d = pg.evaluate("""() => { const m = KH.marks.get('disc'), tiles = [...document.querySelectorAll('#map .tile[data-c]')];
      const lit = tiles.filter(t => !t.classList.contains('mdim')), dim = tiles.filter(t => t.classList.contains('mdim'));
      const tr = document.querySelector('.dc-lit .dc-trk').getBoundingClientRect(), kn = document.querySelector('.dc-lit .dc-knob').getBoundingClientRect();
      return { pressed: document.querySelector('.dc-lit').getAttribute('aria-checked'), only: KH.marks.onlyName(), lit: lit.length, litMarked: lit.every(t => m.has(t.dataset.c)),
        dimUnmarked: dim.every(t => !m.has(t.dataset.c)), drawnMarked: tiles.filter(t => m.has(t.dataset.c)).length, filter: getComputedStyle(dim[0]).filter,
        layoutDim: KH.layout().filter(t => t.kind === 'tile' && t.dim).length, dims: dim.length, knobR: Math.round(tr.right - kn.right), fill: getComputedStyle(document.querySelector('.dc-lit .dc-trk'), '::before').backgroundColor,
        pos: [document.querySelector('#news .dc-only').getBoundingClientRect().x, document.querySelector('#news-p-disc .dc-sub').offsetHeight, document.getElementById('news').offsetHeight, document.querySelector('#news .dc-lit .dc-lw').getBoundingClientRect().x] }; }""")
    pg.wait_for_timeout(100)
    say_on = pg.evaluate("(document.querySelector('body > .sr[role=\"status\"]') || {}).textContent")
    check('switch on → aria-checked, KH.marks.only("disc"): exactly the marked tiles stay bright (.mdim on all others, the search-dim filter); KH.layout() reports them dim; knob at the right end (2px in)',
          d['pressed'] == 'true' and d['only'] == 'disc' and d['litMarked'] and d['dimUnmarked'] and d['lit'] == d['drawnMarked'] and 'brightness(0.38)' in d['filter'] and d['layoutDim'] == d['dims'] and d['dims'] > 0 and d['knobR'] == 2, d)
    check(f'switch on: live region "공시 있는 {c["want"]}종목만 밝게 보여요."; nothing moves (지도 종목만 x, the label x, row and card height the same)',
          say_on == f'공시 있는 {c["want"]}종목만 밝게 보여요.' and d['pos'] == pos0, f'{say_on} {pos0} → {d["pos"]}')
    pg.fill('#q', '삼성'); pg.wait_for_timeout(300)
    a = pg.evaluate("""() => { const m = KH.marks.get('disc'), tiles = [...document.querySelectorAll('#map .tile[data-c]')];
      const bright = tiles.filter(t => !t.classList.contains('mdim') && !t.classList.contains('dim'));
      return { n: bright.length, ok: bright.every(t => m.has(t.dataset.c) && KH.stock(t.dataset.c).n.includes('삼성')) }; }""")
    check('switch AND search: only marked stocks matching "삼성" stay bright', a['ok'] and a['n'] >= 1, a)
    pg.fill('#q', ''); pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    # the news / 공시 row hover lights its tile on top of the switch
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'end'})"); pg.wait_for_timeout(200)
    pg.click('#news .dc-ktabs button[data-k="지분"]'); pg.wait_for_timeout(200)
    code = pg.evaluate("(() => { const r = [...document.querySelectorAll('#news .dc-row')].find(r => KH.stock(r.dataset.c) && document.querySelector(`#map .tile[data-c=\"${r.dataset.c}\"]`) && !KH.marks.get('disc').has(r.dataset.c)); return r ? r.dataset.c : null; })()")
    if code:
        pg.hover(f'#news .dc-row[data-c="{code}"] .dc-tt'); pg.wait_for_timeout(250)
        hv = pg.evaluate(f"(() => {{ const t = document.querySelector('#map .tile[data-c=\"{code}\"]'); return {{ nhl: t.classList.contains('nhl'), mdim: t.classList.contains('mdim'), filter: getComputedStyle(t).filter }}; }})()")
        check('a 지분 row hovered over a dimmed (unmarked) stock lights its tile on top of the switch', hv['nhl'] and hv['mdim'] and hv['filter'] == 'none', hv)
        pg.mouse.move(3, 3); pg.wait_for_timeout(200)
    else:
        check('a 지분 row of an unmarked map stock exists in the fixture', False)
    pg.click('#news .dc-ktabs button[data-k="main"]'); pg.wait_for_timeout(100)
    pg.click('#news .dc-lit'); pg.wait_for_timeout(200)
    off = pg.evaluate("() => ({ n: document.querySelectorAll('#map .tile.mdim').length, only: KH.marks.onlyName(), pressed: document.querySelector('.dc-lit').getAttribute('aria-checked') })")
    pg.wait_for_timeout(100)
    say_off = pg.evaluate("(document.querySelector('body > .sr[role=\"status\"]') || {}).textContent")
    check('switch off → no .mdim left, KH.marks.only(null), live region "모든 종목을 다시 보여요."', off['n'] == 0 and off['only'] is None and off['pressed'] == 'false' and say_off == '모든 종목을 다시 보여요.', f'{off} {say_off}')
    # table view: the swatch in the name cell; the switch keeps marked rows only
    pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
    t1 = pg.evaluate("() => ({ rows: document.querySelectorAll('#tablewrap tbody tr').length, sw: document.querySelectorAll('#tablewrap .nmcell .dmsw').length, title: (document.querySelector('#tablewrap .nmcell .dmsw') || {}).title, label: document.querySelector('#tablewrap tr[data-c=\"005930\"]').getAttribute('aria-label') })")
    pg.click('#news .dc-lit'); pg.wait_for_timeout(300)
    t2 = pg.evaluate("() => ({ rows: document.querySelectorAll('#tablewrap tbody tr').length, all: [...document.querySelectorAll('#tablewrap tbody tr')].every(r => KH.marks.get('disc').has(r.dataset.c)) })")
    check('table: swatch titled "오늘 공시 N건" in the name cell, row aria-label says it; switch on → only the marked rows (not dimmed)',
          t1['sw'] == c['want'] and re.match(r'^오늘 공시 \d+건$', t1['title'] or '') and '오늘 공시' in t1['label'] and t2['rows'] == c['want'] and t2['all'], f'{t1} {t2}')
    pg.click('#news .dc-lit'); pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
    check('no console errors (corners · map switch · table)', not E.items, E.items[:3])
    ctx.close()

    # ── 2b · the map switch turns off whenever its key leaves the screen; never remembered ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    st_js = "() => ({ pressed: document.querySelector('#news .dc-lit') ? document.querySelector('#news .dc-lit').getAttribute('aria-checked') : null, only: KH.marks.onlyName(), mdim: document.querySelectorAll('#map .tile.mdim').length })"
    def on():
        pg.click('#news .dc-lit'); pg.wait_for_timeout(250)
        return pg.evaluate(st_js)
    o1 = on()
    pg.click('#news-t-news'); pg.wait_for_timeout(250)
    l1 = pg.evaluate(st_js)
    pg.click('#news-t-disc'); pg.wait_for_timeout(250)
    l1b = pg.evaluate(st_js)
    check('leave the 오늘 공시 tab (시장 뉴스) → the map back to normal; back on the tab it is still off', o1['pressed'] == 'true' and o1['mdim'] > 0
          and l1 == {'pressed': 'false', 'only': None, 'mdim': 0} and l1b == {'pressed': 'false', 'only': None, 'mdim': 0}, f'{o1} {l1} {l1b}')
    on(); pg.focus('#news-t-disc'); pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(250)
    l2 = pg.evaluate(st_js); pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(200)
    check('leave the tab by keyboard (←) → off', l2 == {'pressed': 'false', 'only': None, 'mdim': 0}, l2)
    on(); pg.evaluate("KHNews.hide()"); pg.wait_for_timeout(250)
    l3 = pg.evaluate(st_js); pg.evaluate("KHNews.show()"); pg.wait_for_timeout(400)
    l3b = pg.evaluate("() => ({ feed: document.getElementById('news').dataset.feed, pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), mdim: document.querySelectorAll('#map .tile.mdim').length })")
    check('the news card hidden → off; shown again → the tab with the switch off', l3 == {'pressed': 'false', 'only': None, 'mdim': 0} and l3b == {'feed': 'disc', 'pressed': 'false', 'mdim': 0}, f'{l3} {l3b}')
    on(); pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(500)
    l4 = pg.evaluate(st_js); pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(700)
    l4b = pg.evaluate(st_js)
    check('해외 tab → off (and still off back on 코스피)', l4['pressed'] == 'false' and l4['only'] is None and l4b == {'pressed': 'false', 'only': None, 'mdim': 0}, f'{l4} {l4b}')
    on(); pg.click('.tabs button[data-mkt="CMDTY"]'); pg.wait_for_timeout(500)
    l5 = pg.evaluate(st_js); pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(700)
    check('지표 tab → off', l5['pressed'] == 'false' and l5['only'] is None, l5)
    o6 = on(); pg.click('.tabs button[data-mkt="Q"]'); pg.wait_for_timeout(700)
    l6 = pg.evaluate("() => ({ pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), only: KH.marks.onlyName(), lit: [...document.querySelectorAll('#map .tile[data-c]')].filter(t => !t.classList.contains('mdim')).every(t => KH.marks.get('disc').has(t.dataset.c)), n: parseInt(document.querySelector('#news .dc-lit .dc-ln').textContent.replace(/\\D/g, '')), want: KH.mapCodes().filter(c => KH.marks.get('disc').has(c)).length })")
    check('another stock map (코스닥) keeps it on, lighting the 코스닥 filers; the count follows that map', o6['pressed'] == 'true' and l6['pressed'] == 'true' and l6['only'] == 'disc' and l6['lit'] and l6['n'] == l6['want'] and l6['want'] > 0, l6)
    pg.click('#moreBtn'); pg.wait_for_timeout(200)
    pg.click('[data-set="disc"] .swbtn'); pg.wait_for_timeout(400)
    l7 = pg.evaluate("() => ({ only: KH.marks.onlyName(), mdim: document.querySelectorAll('#map .tile.mdim').length, key: !!document.querySelector('.dc-lit') && document.querySelector('.dc-lit').isConnected })")
    pg.click('[data-set="disc"] .swbtn'); pg.wait_for_timeout(1200)
    check('공시 보기 off → off (the tab and its key gone); on again → off', l7 == {'only': None, 'mdim': 0, 'key': False} and pg.evaluate(st_js)['only'] is None, l7)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    disc_tab(pg); on(); pg.reload(); pg.wait_for_timeout(1800); disc_tab(pg)
    l8 = pg.evaluate(st_js)
    keys = pg.evaluate("Object.keys(localStorage).filter(k => /disc|lit|only/i.test(k) && !/discKinds|set\\.disc$/.test(k))")
    check('not remembered: after a reload the switch is off, nothing dimmed, nothing stored', l8 == {'pressed': 'false', 'only': None, 'mdim': 0} and not keys, f'{l8} {keys}')
    # keyboard: Space / Enter toggle it, ring 3px
    pg.focus('#news .dc-only'); pg.keyboard.press('Tab'); pg.keyboard.press('Space'); pg.wait_for_timeout(250)
    k1 = pg.evaluate("() => { const b = document.activeElement, cs = getComputedStyle(b); return { lit: b.classList.contains('dc-lit'), pressed: b.getAttribute('aria-checked'), ring: cs.outlineStyle !== 'none' ? parseFloat(cs.outlineWidth) : 0, only: KH.marks.onlyName() }; }")
    pg.keyboard.press('Enter'); pg.wait_for_timeout(250)
    k2 = pg.evaluate(st_js)
    check('keyboard: Space turns it on (ring 3px), Enter off', k1 == {'lit': True, 'pressed': 'true', 'ring': 3, 'only': 'disc'} and k2 == {'pressed': 'false', 'only': None, 'mdim': 0}, f'{k1} {k2}')
    # replay of today: the count of filings seen by then, its title says so
    rq = pg.evaluate("""async () => { const d = KH.disclosures(), k = new Date(KH.now() + 9 * 3600e3), now = k.getUTCHours() * 60 + k.getUTCMinutes(), t = Math.max(0, now - 15);
      const hm = String(Math.floor(t / 60)).padStart(2, '0') + String(t % 60).padStart(2, '0');
      KH.setReplay({ t: hm, date: d.date, prices: new Map() }); await new Promise(r => setTimeout(r, 400));
      const b = document.querySelector('#news .dc-lit'), map = new Set(KH.mapCodes()), hhmm = hm.slice(0, 2) + ':' + hm.slice(2);
      const res = { hhmm, title: b.title, label: b.getAttribute('aria-label'), n: parseInt(b.querySelector('.dc-ln').textContent.replace(/\\D/g, '')),
        want: new Set(d.rows.filter(r => r.s && r.s <= hhmm && ['실적', '주요'].includes(r.k) && map.has(r.c)).map(r => r.c)).size };
      KH.setReplay(null); await new Promise(r => setTimeout(r, 300)); return res; }""")
    check(f'replay of today ({rq["hhmm"]}): the switch counts the map filers seen by then; title "다시 보기 — HH:MM까지 들어온 공시", label ends "· HH:MM까지"',
          rq['n'] == rq['want'] and rq['title'] == f'다시 보기 — {rq["hhmm"]}까지 들어온 공시' and rq['label'].endswith(f'· {rq["hhmm"]}까지'), rq)
    check('no console errors (toggle off paths)', not E.items, E.items[:3])
    ctx.close()

    # ── 2c · 1024 (narrow PC card): the switch is a line of its own at the top of the tab (label left, track at the right end); kind tabs whole;
    #    the card keeps 시장 뉴스's height; pressing moves nothing ──
    ctx, pg = open_page(br, LIVE, 1024, 768)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
    hn = pg.evaluate("document.getElementById('news').offsetHeight")
    disc_tab(pg)
    G2 = "() => { const n = document.getElementById('news'), R = e => e.getBoundingClientRect(), sub = n.querySelector('#news-p-disc .dc-sub'), b = n.querySelector('.dc-lit'), kt = n.querySelector('.dc-ktabs'); return { h: n.offsetHeight, sub: sub.offsetHeight, top: Math.round(R(b).top - R(sub).top), above: R(b).bottom <= R(kt).top, full: Math.round(R(b).width) === Math.round(R(sub).width), right: Math.round(R(sub).right - R(b.querySelector('.dc-trk')).right), lw: Math.round(R(b.querySelector('.dc-lw')).x), only: Math.round(R(n.querySelector('.dc-only')).x), kt: kt.scrollWidth <= kt.clientWidth, rows: n.querySelectorAll('#news-p-disc .dc-row').length, over: document.documentElement.scrollWidth - innerWidth }; }"
    w0 = pg.evaluate(G2); pg.click('#news .dc-lit'); pg.wait_for_timeout(600); w1 = pg.evaluate(G2)
    check('1024: the switch on its own line at the top (full width, track at the right end), kind tabs whole below; card height = 시장 뉴스; on → same boxes',
          w0['top'] == 0 and w0['above'] and w0['full'] and w0['right'] == 0 and w0['kt'] and w0['h'] == hn and w0['over'] == 0 and w1 == w0, f'news {hn} {w0} → {w1}')
    ctx.close()

    # ── 2e · 1440: the map header without the chip — one row (36 px), nothing past its edge, today's index line ends before 지도 · 표 ──
    for mk in ('K', 'ALL'):
        ctx, pg = open_page(br, LIVE, 1440, 900, market=mk)
        hb = pg.evaluate("""() => { const sb = document.querySelector('.stagebar'), R = e => e.getBoundingClientRect(), ix = sb.querySelector('.ixl'), vs = sb.querySelector('.viewseg');
          return { h: sb.offsetHeight, st: document.getElementById('stage-tools').offsetWidth, chip: document.querySelectorAll('.dc-hchip').length,
            over: [...sb.querySelectorAll('*')].filter(e => R(e).right > R(sb).right + 1).length, ix: !!ix && !ix.hidden && R(ix).right <= R(vs).left - 8, page: document.documentElement.scrollWidth - innerWidth }; }""")
        check(f'1440 {mk}: map header one row (36 px) without the chip, nothing past its edge, the index line ends before 지도 · 표',
              hb == {'h': 36, 'st': 0, 'chip': 0, 'over': 0, 'ix': True, 'page': 0}, hb)
        ctx.close()

    # ── 2f · the switch itself (design.md §7 · §6-4): sunken track + raised knob from the tokens, the knob's edges on follow (front) / settle
    #    (back) and at most 3px longer while it moves, the fill = --sw-on; the count swaps in place; the knob can be dragged (from 4 px) ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    sw = pg.evaluate("""() => { const b = document.querySelector('#news .dc-lit'), t = b.querySelector('.dc-trk'), k = b.querySelector('.dc-knob'), R = e => e.getBoundingClientRect(), root = getComputedStyle(document.documentElement);
      const css = (el, p, pe) => getComputedStyle(el, pe || null)[p], v = n => root.getPropertyValue(n).trim();
      const probe = document.createElement('i'); document.body.append(probe); const col = c => { probe.style.color = c; return getComputedStyle(probe).color; };
      const res = { w: R(t).width, h: R(t).height, knob: parseFloat(css(k, 'width', '::before')), trk: css(t, 'backgroundColor') === col(v('--trk')), trkSh: css(t, 'boxShadow').includes('inset'),
        knobBg: css(k, 'backgroundColor', '::before') === col(v('--knob')), knobSh: css(k, 'boxShadow', '::before') !== 'none', fill: css(t, 'backgroundColor', '::before') === col(v('--sw-on')),
        notData: ![col(v('--up-text')), col(v('--dn-text'))].includes(css(t, 'backgroundColor', '::before')),
        offT: [css(k, 'transitionProperty'), css(k, 'transitionDuration'), css(k, 'transitionTimingFunction').split('linear(').length - 1],
        follow: v('--sp-follow-dur'), settle: v('--sp-settle-dur') };
      probe.remove(); return res; }""")
    # the move, frame by frame: the knob's two CSS transitions paused and sought every 10 ms (no frame timing involved)
    mv = pg.evaluate("""() => { const b = document.querySelector('#news .dc-lit'), k = b.querySelector('.dc-knob'); b.click();
      const an = k.getAnimations(); an.forEach(a => a.pause()); const kw = [];
      for (let t = 0; t <= 520; t += 10) { an.forEach(a => { a.currentTime = t; }); kw.push([t, parseFloat(getComputedStyle(k, '::before').width), k.getBoundingClientRect().width]); }
      an.forEach(a => a.finish()); return { n: an.map(a => a.transitionProperty).sort().join(), kw }; }""")
    kw = mv['kw']
    onT = pg.evaluate("() => { const k = document.querySelector('#news .dc-knob'), cs = getComputedStyle(k); return [cs.transitionProperty, cs.transitionDuration]; }")
    vis = max(x[1] for x in kw); edges = max(x[2] for x in kw)
    check(f'switch: track {sw["w"]:.0f}×{sw["h"]:.0f} sunken (--trk + inset shadow), knob {sw["knob"]:.0f} raised (--knob + shadow), fill = --sw-on (not the up / down colours)',
          sw['w'] == 44 and sw['h'] == 26 and sw['knob'] == 22 and sw['trk'] and sw['trkSh'] and sw['knobBg'] and sw['knobSh'] and sw['fill'] and sw['notData'], sw)
    check(f'switch motion: off → front edge left on follow ({sw["follow"]}), back edge right on settle ({sw["settle"]}); on → the other way round; while moving the edges open {edges - 22:.1f}px, the knob you see ≤ 3px longer ({vis - 22:.1f}), then round again',
          sw['offT'][0] == 'left, right' and sw['offT'][1] == f'{float(sw["follow"][:-2]) / 1000:g}s, {float(sw["settle"][:-2]) / 1000:g}s' and sw['offT'][2] == 2 and mv['n'] == 'left,right'
          and onT == ['right, left', sw['offT'][1]] and 24.5 <= vis <= 25 and edges > vis and abs(kw[-1][1] - 22) < .5 and kw[0][1] == 22, f'{sw["offT"]} {onT} {mv["n"]} vis {vis} edges {edges} {kw[::5]}')
    pg.click('#news .dc-lit'); pg.wait_for_timeout(700)
    # §6-4: 코스피 → 코스닥 changes the count — the old one leaves, the new one comes in, both in one cell for a moment, then one
    sx = pg.evaluate("""() => new Promise(res => { const c = document.querySelector('#news .dc-lc'), seen = [];
      const look = () => { const kids = [...c.children].map(x => x.className + ':' + getComputedStyle(x).animationName + ':' + x.textContent); if (kids.length > 1) seen.push(kids); };
      const mo = new MutationObserver(look); mo.observe(c, { childList: true, subtree: true });
      document.querySelector('.tabs button[data-mkt="Q"]').click();
      setTimeout(() => { mo.disconnect(); res({ seen: seen.slice(0, 2), end: [...c.children].map(x => x.className + ':' + x.textContent) }); }, 900); })""")
    first = sx['seen'][0] if sx['seen'] else []
    check('count swap (§6-4): the old "· N종목" leaves (dcTxOut) while the new one comes in (dcTxIn) in the same cell, then only the new one is left',
          len(first) == 2 and 'out:dcTxOut' in first[0] and 'in:dcTxIn' in first[1] and len(sx['end']) == 1 and sx['end'][0].startswith('dc-lv') and '종목' in sx['end'][0], sx)
    pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(700)
    # drag the knob (KH.ui.sw): 4 px does nothing yet, past half way it lands on, back again lands off
    def drag(dx):
        pg.evaluate("document.querySelector('#news .dc-lit').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(150)
        kb = pg.evaluate("(() => { const r = document.querySelector('#news .dc-knob').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        pg.mouse.move(kb[0], kb[1]); pg.mouse.down()
        for i in range(1, 7):
            pg.mouse.move(kb[0] + dx * i / 6, kb[1]); pg.wait_for_timeout(16)
        pg.mouse.up(); pg.wait_for_timeout(700)
        return pg.evaluate("() => ({ checked: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), only: KH.marks.onlyName(), drag: document.querySelector('#news .dc-lit').classList.contains('drag') })")
    d1 = drag(16); d2 = drag(-16); d3 = drag(3)
    check('drag the knob: right past half → on (the map dims), left → off; a 3px nudge is a plain press (on)',
          d1 == {'checked': 'true', 'only': 'disc', 'drag': False} and d2 == {'checked': 'false', 'only': None, 'drag': False} and d3['checked'] == 'true', f'{d1} {d2} {d3}')
    pg.click('#news .dc-lit'); pg.wait_for_timeout(300)
    check('no console errors (switch)', not E.items, E.items[:3])
    ctx.close()

    # ── 2d · nothing to light: 0 → off look with the reason (title, label, a bubble + the live region on press), never on ──
    mode('empty')
    E.items = []
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    z = pg.evaluate("() => { const b = document.querySelector('#news .dc-lit'); return { dis: b.getAttribute('aria-disabled'), title: b.title, label: b.getAttribute('aria-label'), text: b.textContent, op: getComputedStyle(b).opacity, focus: (b.focus(), document.activeElement === b) }; }")
    pg.click('#news .dc-lit', force=True); pg.wait_for_timeout(250)          # force: Playwright treats aria-disabled as not clickable
    z2 = pg.evaluate("() => ({ pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), only: KH.marks.onlyName(), mdim: document.querySelectorAll('#map .tile.mdim').length, bub: (document.querySelector('.kbub') || {}).textContent, say: (document.querySelector('body > .sr[role=\"status\"]') || {}).textContent })")
    why = '지도 종목에 실적·주요 공시가 아직 없어요'
    check(f'0 filings: the switch is off-looking (aria-disabled, .45) and focusable, "· 0종목"; reason "{why}" in title · label · a bubble · the live region; stays off',
          z['dis'] == 'true' and z['title'] == why and z['label'] == f'공시 있는 종목만 지도에서 밝게, 0종목 — {why}' and z['text'].endswith('· 0종목') and z['op'] == '0.45' and z['focus']
          and z2['pressed'] == 'false' and z2['only'] is None and z2['mdim'] == 0 and z2['bub'] == why and z2['say'] == why, f'{z} {z2}')
    check('no console errors (0 filings)', not E.items, E.items[:3])
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
    o = pg.evaluate("() => ({ dm: document.querySelectorAll('#map .dm').length, chip: !!document.querySelector('.dc-lit'), lg: !!document.querySelector('#legend .dc-lg'), tab: !!document.getElementById('news-t-disc'), multi: document.getElementById('news').classList.contains('multi'), pol: !!document.getElementById('news-t-policy'), foot: document.getElementById('foot-disc').hidden, kinds: document.querySelector('[data-set=\"discKinds\"]').classList.contains('off') })")
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(800)
    k1 = mock('/__stats').get('/api/disclosures/today', 0)
    check('공시 보기 off → no corners, map switch, legend item, tab (the news card as before), footer line; kind chips greyed; no request on refresh',
          o['dm'] == 0 and not o['chip'] and not o['lg'] and not o['tab'] and o['multi'] == o['pol'] and o['foot'] and o['kinds'] and k1 == k0, f'{o} req {k0}→{k1}')   # (the 정책 자료 tab, when there, keeps the title tabs)
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
        times: [...document.querySelectorAll('#news .dc-tm')].slice(0, 3).map(t => t.textContent), dots: document.querySelectorAll('.dc-dot').length, chip: document.querySelector('#news .dc-lit').getAttribute('aria-label'), chipTitle: document.querySelector('#news .dc-lit').title,
        mark: KH.marks.get('disc').get('005930').label, wantMark: `, ${m}월 ${dd}일 공시` }; }""")
    check(f'non-trading day: tab "{hd["tab"]}", legend "{hd["lg"][:12]}…", map switch (label · title) / tile labels name the day, no dot', hd['tab'] == hd['want'] and hd['lg'].startswith(hd['wantLg']) and hd['dots'] == 0
          and hd['chip'].startswith(hd['want'].split(' (')[0] + ' 공시 있는 종목만 지도에서 밝게') and hd['chipTitle'] == hd['want'] and hd['mark'].startswith(hd['wantMark']) and all(re.match(r'^\d\d:\d\d$', t) for t in hd['times']), hd)
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
    l = pg.evaluate("() => ({ sk: document.querySelectorAll('#news .dc-row.skel').length, at: document.querySelector('#news .nw-at').textContent, chip: document.querySelector('.dc-lit').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-lit').textContent + '|' + !!document.querySelector('.dc-lit .kspn') + '|' + document.querySelector('.dc-lit').title, lg: (document.querySelector('#legend .dc-lg') || {}).textContent, dis: [...document.querySelectorAll('#news .dc-ktabs button, #news .dc-only')].every(b => b.getAttribute('aria-disabled') === 'true'), h: document.getElementById('news').offsetHeight })")
    pg.wait_for_selector('#news .dc-row:not(.skel)', timeout=8000); pg.wait_for_timeout(200)
    h2 = pg.evaluate("document.getElementById('news').offsetHeight")
    check('loading: skeleton rows, "불러오는 중", map switch ring + label (off, "공시를 불러오는 중이에요"), legend "공시 …", kind tabs + 지도 종목만 off, same card height after',
          l['sk'] >= 5 and l['at'] == '불러오는 중' and l['chip'] == 'true|지도에서 공시 종목만 밝게|true|공시를 불러오는 중이에요' and l['lg'] == '공시 …' and l['dis'] and l['h'] == h2, f'{l} → {h2}')
    ctx.close()
    E.allow = ['503', 'Failed to load resource']
    E.items = []
    mode('fail')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    disc_tab(pg)
    e = pg.evaluate("() => ({ msg: document.querySelector('#news-p-disc .nw-msg').textContent, at: document.querySelector('#news .nw-at').textContent, chip: document.querySelector('.dc-lit').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-lit').textContent + '|' + document.querySelector('.dc-lit').title, lg: document.querySelector('#legend .dc-lg').textContent, more: document.querySelector('#news-p-disc .nw-more').hidden, dm: document.querySelectorAll('#map .dm').length, h: document.getElementById('news').offsetHeight })")
    check('error: "공시를 불러오지 못했어요" + 다시 시도, head "받은 목록 없음", map switch "… !" (off, title), legend "공시 —", no corners',
          e['msg'].startswith('공시를 불러오지 못했어요DART 응답이 없었어요. 잠시 뒤 다시 눌러 주세요.다시 시도') and e['at'] == '받은 목록 없음' and e['chip'] == 'true|지도에서 공시 종목만 밝게!|공시를 불러오지 못했어요' and e['lg'] == '공시 —' and e['more'] and e['dm'] == 0, e)
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
    em = pg.evaluate("() => ({ msg: document.querySelector('#news-p-disc .nw-msg').textContent, chip: document.querySelector('.dc-lit').getAttribute('aria-disabled') + '|' + document.querySelector('.dc-lit').textContent, lg: !!document.querySelector('#legend .dc-lg'), dm: document.querySelectorAll('#map .dm').length })")
    check('empty: a 휴장일 / 아침 / plain message, map switch "0종목" (off), no legend item, no corners',
          re.match(r'^(오늘은 휴장일이라 공시가 거의 없어요|아직 오늘 공시가 없어요|아직 공시가 없어요)', em['msg']) and em['chip'] == 'true|지도에서 공시 종목만 밝게· 0종목' and not em['lg'] and em['dm'] == 0, em)
    ctx.close()
    mode('stale')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    so = pg.evaluate("() => ({ cls: document.querySelector('#news .nw-at').className, at: document.querySelector('#news .nw-at').textContent, key: !!document.querySelector('#news .nw-at .kasync'), bang: !!document.querySelector('.dc-lit .dc-bad'), blab: document.querySelector('.dc-lit').getAttribute('aria-label'), bdis: document.querySelector('.dc-lit').getAttribute('aria-disabled'), rows: document.querySelectorAll('#news .dc-row').length, ic: getComputedStyle(document.querySelector('#news .nw-at .kwn')).color, bc: getComputedStyle(document.querySelector('.dc-lit .dc-bad')).color, fd: (() => { const i = document.createElement('i'); i.style.color = 'var(--fail-dot)'; document.body.append(i); const c = getComputedStyle(i).color; i.remove(); return c; })() })")
    check('stale (server stale, asOf 20 min old): list stays, ! (--fail-dot) "HH:MM 기준 · N분째 못 받았어요" + 다시 시도, map switch "!" (still usable, label says so)',
          so['ic'] == so['fd'] and so['bc'] == so['fd'] and 'stale' in so['cls'] and re.search(r'\d\d:\d\d 기준 · 2\d분째 못 받았어요', so['at']) and so['key'] and so['bang'] and so['bdis'] is None and so['blab'].endswith('· 몇 분째 새 공시를 받지 못했어요') and so['rows'] > 0, so)
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
      res.other = { dm: document.querySelectorAll('#map .dm').length, chip: !document.querySelector('#news .dc-litw').hidden, lg: (document.querySelector('#legend .dc-lg') || {}).textContent, at: document.querySelector('#news .nw-at').textContent };
      KH.setReplay(null); await new Promise(r => setTimeout(r, 400));
      res.back = document.querySelectorAll('#map .dm').length; return res; }""")
    check(f'replay of today ({rp["hhmm"]}): head "다시 보기 중 · HH:MM까지 들어온 공시만", only rows seen by then, corners from those',
          rp['at'] == f'다시 보기 중 · {rp["hhmm"]}까지 들어온 공시만' and all(t == '오늘' or t <= rp['hhmm'] for t in rp['shown']) and rp['marks'] == rp['expectMarks'], rp)
    check('replay of another day: no corners, no map switch, legend "다시 보기 중에는 오늘 공시만 보여요", head "다시 보기 중 · 지금 공시예요"; back to live → corners',
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
    for _ in range(12):
        seq.append(pg.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a);
          const k = a.getAttribute('role') === 'tab' ? 'title' : a.classList.contains('nw-rk') ? 'rk' : a.closest('.dc-ktabs') ? 'kind' : a.classList.contains('dc-only') ? 'only' : a.classList.contains('dc-lit') ? 'lit' : a.closest('.dc-tt') ? 'link' : a.classList.contains('dc-chip') ? 'chip' : a.classList.contains('nw-more') ? 'more' : a.tagName;
          return [k, cs.outlineStyle !== 'none' ? parseFloat(cs.outlineWidth) : 0]; }"""))
        pg.keyboard.press('Tab')
    kinds = [s[0] for s in seq]
    check('title tabs ←/→ (remembered in khm.feedTab); Tab: title → ↻ 새로 받기 → kinds ×5 → 지도 종목만 → 지도에서 밝게 → chip → link …; ring 3px',
          kb == ['news-t-news', 'news', '"news"'] and kinds[:11] == ['title', 'rk', 'kind', 'kind', 'kind', 'kind', 'kind', 'only', 'lit', 'chip', 'link'] and all(s[1] == 3 for s in seq), f'{kb} {kinds}')
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

    # ── 12 · phone: no header chip, corners on the map, card 5 rows + 더보기, map switch 40 (hit 44) on the tab's first line, kind tabs 40, chips 32 (44), quick view rows ≥ 54 ──
    mode('ok')
    E.items = []
    ctx, pg = open_page(br, LIVE, 390, 844, errors=E)
    ph0 = pg.evaluate("() => ({ st: document.getElementById('stage-tools').children.length, chip: document.querySelectorAll('.dc-hchip').length, sb: document.querySelector('.stagebar').offsetHeight, dm: document.querySelectorAll('#map .dm').length, sbOver: [...document.querySelectorAll('.stagebar *')].filter(e => e.getBoundingClientRect().right > document.querySelector('.stagebar').getBoundingClientRect().right + 1).length })")
    disc_tab(pg)
    ph = pg.evaluate("""() => { const n = document.getElementById('news'), rows = [...n.querySelectorAll('.dc-row')], chip = n.querySelector('.dc-chip'), tab = n.querySelector('.dc-ktabs button'), tt = rows[0].querySelector('.dc-tt'), cs = getComputedStyle(tt);
      const b = n.querySelector('.dc-lit'), o = n.querySelector('.dc-only'), R = e => e.getBoundingClientRect(), sub = n.querySelector('#news-p-disc .dc-sub');
      return { rows: rows.length, clamp: cs.webkitLineClamp, fs: cs.fontSize, chipH: chip.getBoundingClientRect().height, chipHit: getComputedStyle(chip, '::before').height, tabH: tab.getBoundingClientRect().height,
        title: n.querySelector('.nw-ftabs > button').getBoundingClientRect().height, more: n.querySelector('#news-p-disc .nw-more').getBoundingClientRect().height,
        litH: R(b).height, litHit: getComputedStyle(b, '::before').height, top: Math.round(R(b).top - R(sub).top), above: R(b).bottom <= R(n.querySelector('.dc-ktabs')).top, right: Math.round(R(sub).right - R(b.querySelector('.dc-trk')).right),
        lines: Math.round(R(b.querySelector('.dc-ll')).height), lfs: getComputedStyle(b).fontSize, text: b.innerText.replace(/\\s+/g, ' ') }; }""")
    check('phone: no chip in the map header (one row, nothing past its edge), corners drawn; card 5 rows, titles 14 px (--fs-lg) two lines, chips 32 (hit 44), kind tabs 40, title tabs 40, 더보기 44',
          ph0['st'] == 0 and ph0['chip'] == 0 and ph0['sb'] <= 46 and ph0['sbOver'] == 0 and ph0['dm'] > 0 and ph['rows'] == 5 and ph['clamp'] == '2' and ph['fs'] == '14px' and round(ph['chipH']) == 32
          and ph['chipHit'] == '44px' and ph['tabH'] >= 40 and ph['title'] >= 40 and ph['more'] >= 44, f'{ph0} {ph}')
    check('phone: the map switch is the first line of the tab (40 px, hit 44, 14 px), the whole label "지도에서 공시 종목만 밝게 · N종목" on one line, track at the right end',
          round(ph['litH']) == 40 and ph['litHit'] == '44px' and ph['top'] == 0 and ph['above'] and ph['right'] == 0 and ph['lfs'] == '14px' and ph['lines'] <= 20
          and re.match(r'^지도에서 공시 종목만 밝게 · \d+종목$', ph['text'].strip()), ph)
    p0 = pg.evaluate("() => [document.querySelector('#news .dc-only').getBoundingClientRect().x, document.querySelector('#news-p-disc .dc-sub').offsetHeight]")
    pg.tap('#news .dc-lit'); pg.wait_for_timeout(300)
    p1 = pg.evaluate("""() => { const m = KH.marks.get('disc'), tiles = [...document.querySelectorAll('#map .tile[data-c]')], dim = tiles.filter(t => t.classList.contains('mdim'));
      return { pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), dims: dim.length, ok: dim.every(t => !m.has(t.dataset.c)) && tiles.filter(t => !t.classList.contains('mdim')).every(t => m.has(t.dataset.c)),
        pos: [document.querySelector('#news .dc-only').getBoundingClientRect().x, document.querySelector('#news-p-disc .dc-sub').offsetHeight], over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        cardOver: document.getElementById('news').scrollWidth - document.getElementById('news').clientWidth, bg: getComputedStyle(document.querySelector('#news .dc-lit')).backgroundColor }; }""")
    check('phone: tap → the map dims all but the filers; 지도 종목만 and the row stay put; no horizontal overflow (page · card); no hover tint left (hover only for a fine pointer)',
          p1['pressed'] == 'true' and p1['dims'] > 0 and p1['ok'] and p1['pos'] == p0 and p1['over'] == 0 and p1['cardOver'] <= 0 and p1['bg'] in ('rgba(0, 0, 0, 0)', 'transparent'), f'{p0} {p1}')
    pg.tap('#news-t-news'); pg.wait_for_timeout(300)
    p2 = pg.evaluate("() => ({ only: KH.marks.onlyName(), mdim: document.querySelectorAll('#map .tile.mdim').length })")
    check('phone: 시장 뉴스 tab → the map back to normal', p2 == {'only': None, 'mdim': 0}, p2)
    pg.tap('#news-t-disc'); pg.wait_for_timeout(300)
    pg.tap('#news .dc-row .dc-chip'); pg.wait_for_timeout(500)
    qs = pg.evaluate("() => ({ open: document.getElementById('sheet').classList.contains('open'), rows: [...document.querySelectorAll('#sheet .dsc a.dr')].map(a => Math.round(a.getBoundingClientRect().height)), all: Math.round(document.querySelector('#sheet .dc-all').getBoundingClientRect().height), hl: document.querySelectorAll('#map .tile.nhl').length })")
    check('phone chip → bottom sheet with the 공시 block: rows ≥ 52 px (--h-row + 8), 공시 모두 보기 44 px, no map highlight', qs['open'] and qs['rows'] and all(x >= 52 for x in qs['rows']) and qs['all'] >= 44 and qs['hl'] == 0, qs)
    check('no console errors (phone)', not E.items, E.items[:3])
    ctx.close()

    # ── 13 · reduced motion: no corner / row animation, indicators 0s ──
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800, motion='reduced')
    disc_tab(pg)
    pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(600)
    rm = pg.evaluate("() => ({ anim: [...document.querySelectorAll('#map .dm, #news .dc-row')].filter(x => getComputedStyle(x).animationName !== 'none').length, ind: getComputedStyle(document.querySelector('#news .dc-ktabs'), '::before').transitionDuration, bar: getComputedStyle(document.querySelector('#news .nw-ftabs'), '::before').transitionDuration, lit: getComputedStyle(document.querySelector('#news .dc-lit')).transitionDuration, ck: getComputedStyle(document.querySelector('#news .dc-lit .dc-knob')).transitionDuration + ',' + getComputedStyle(document.querySelector('#news .dc-lit .dc-trk'), '::before').transitionDuration + ',' + getComputedStyle(document.querySelector('#news .dc-lit .dc-knob'), '::before').transitionDuration })")
    zero = lambda v: set(v.replace(' ', '').split(',')) <= {'0s'}
    check('reduced motion: no corner / row animation; kind indicator, title bar, map switch (knob edges, fill, knob shadow) 0s', rm['anim'] == 0 and zero(rm['ind']) and zero(rm['bar']) and zero(rm['lit']) and zero(rm['ck']), rm)
    ctx.close()

    # ── 14 · a Worker without the route (404): nothing of this shows, the news card as before, one request ──
    E.allow = ['404', 'Failed to load resource']
    E.items = []
    mode('none')
    ctx, pg = open_page(br, LIVE, 1280, 800, errors=E)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(800)
    g4 = pg.evaluate("() => ({ tab: !!document.getElementById('news-t-disc'), multi: document.getElementById('news').classList.contains('multi'), pol: !!document.getElementById('news-t-policy'), h2: !!document.querySelector('#news h2'), chip: !!document.querySelector('.dc-lit'), dm: document.querySelectorAll('#map .dm').length, lg: !!document.querySelector('#legend .dc-lg'), foot: document.getElementById('foot-disc').hidden })")
    n4 = mock('/__stats').get('/api/disclosures/today', 0)
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
    n5 = mock('/__stats').get('/api/disclosures/today', 0)
    check('404: no tab (the news card with its h2 as before), no map switch, corners, legend item, footer line; no more requests', not g4['tab'] and g4['multi'] == g4['pol'] and g4['h2'] != g4['pol'] and not g4['chip'] and g4['dm'] == 0 and not g4['lg'] and g4['foot'] and n4 == 1 and n5 == 1, f'{g4} {n4}→{n5}')
    E.allow = []
    ctx.close()

    # ── 15 · world tab: no polling, no credit there; the map switch turns off; back → it counts the new map ──
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg)
    pg.click('#news .dc-lit'); pg.wait_for_timeout(250)
    pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(500)
    k0 = mock('/__stats').get('/api/disclosures/today', 0)
    w = pg.evaluate("() => ({ pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), only: KH.marks.onlyName(), foot: document.getElementById('foot').textContent.includes('공시: 금융감독원') })")
    pg.evaluate("KH.refresh()"); pg.wait_for_timeout(500)
    k1 = mock('/__stats').get('/api/disclosures/today', 0)
    pg.click('.tabs button[data-mkt="Q"]'); pg.wait_for_timeout(700)
    q = pg.evaluate("() => ({ chip: parseInt(((document.querySelector('#news .dc-lit .dc-ln') || {}).textContent || '-1').replace(/[^\\d-]/g, '')), pressed: document.querySelector('#news .dc-lit').getAttribute('aria-checked'), mdim: document.querySelectorAll('#map .tile.mdim').length, want: KH.mapCodes().filter(c => KH.marks.get('disc').has(c)).length })")
    check('world tab: the map switch off, no credit, no request on refresh; 코스닥 → the switch (off) counts the 코스닥 map',
          w['pressed'] == 'false' and w['only'] is None and not w['foot'] and k1 == k0 and q['chip'] == q['want'] and q['want'] > 0 and q['pressed'] == 'false' and q['mdim'] == 0, f'{w} {k0}→{k1} {q}')
    ctx.close()

    # ── 16 · snapshot (dist/): the tab says "실시간 버전에서", no chip / corners / legend / footer, no fixture rows in the build ──
    E.items = []
    ctx, pg = open_page(br, SNAP, 1280, 800, errors=E)
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})"); pg.click('#news-t-disc'); pg.wait_for_timeout(300)
    sn = pg.evaluate("() => ({ text: document.getElementById('news-p-disc').textContent, href: (document.querySelector('#news-p-disc a') || {}).href, chip: !!document.querySelector('.dc-lit, .dc-hchip'), dm: document.querySelectorAll('#map .dm').length, lg: !!document.querySelector('#legend .dc-lg'), foot: document.getElementById('foot-disc') ? document.getElementById('foot-disc').hidden : true, over: document.documentElement.scrollWidth - innerWidth, tabs: [...document.querySelectorAll('#news .nw-ftabs > button')].map(b => b.textContent) })")
    check('snapshot: tabs 시장 뉴스 · 오늘 공시, "공시는 실시간 버전에서 볼 수 있어요" + LIVE_URL; no map switch, corners, legend item, footer line; no console errors',
          sn['tabs'][:2] == ['시장 뉴스', '오늘 공시'] and '공시는 실시간 버전에서 볼 수 있어요' in sn['text'] and sn['href'] == 'https://panse.pages.dev/' and not sn['chip'] and sn['dm'] == 0 and not sn['lg'] and sn['foot'] and sn['over'] == 0 and not E.items, f'{sn} {E.items[:2]}')
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


DESIGN_JS = r"""() => {
  const n = document.getElementById('news-p-disc'), R = e => e.getBoundingClientRect(), cs = (e, p) => getComputedStyle(e, p || null);
  const probe = document.createElement('i'); document.body.append(probe);
  const col = v => { probe.style.color = ''; probe.style.color = `var(${v})`; return getComputedStyle(probe).color; };
  const row = n.querySelector('.dc-row:not(.skel)'), kb = n.querySelector('.dc-row .dc-kb:not(.fix)'), kt = n.querySelector('.dc-ktabs'), sel = kt.querySelector('button[aria-pressed="true"]');
  const sizes = new Set(); for (const e of n.querySelectorAll('*')) if (e.offsetWidth && [...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim())) sizes.add(Math.round(parseFloat(cs(e).fontSize) * 10) / 10);
  const res = { row: Math.round(R(row).height), badge: [Math.round(R(kb).height), cs(kb).borderTopLeftRadius, cs(kb).fontSize, cs(kb).fontWeight],
    kind: [Math.round(R(sel).height), cs(sel).fontSize], only: Math.round(R(n.querySelector('.dc-only')).height), chip: Math.round(R(n.querySelector('.dc-chip')).height),
    sizes: [...sizes].sort((x, y) => x - y), ind: kt.dataset.ind != null, ul: [cs(kt, '::before').height, cs(kt, '::before').backgroundColor], accLine: col('--acc-line'),
    ulX: R(kt).left + parseFloat(cs(kt, '::before').left) - kt.scrollLeft, ulW: parseFloat(cs(kt, '::before').width), selX: R(sel).left, selW: R(sel).width,
    dot: cs(document.querySelector('#news .dc-dot')).backgroundColor, newDot: col('--new-dot') };
  probe.remove();
  return res;
}"""


def design(br):
    """design.md (ux/std-news): token sizes · the kind underline · the 더보기 fold through KHNews.fold · counts that swap with new data (and
    not on a map change) · the tooltip's 공시 block on the glass plate (the plate keeps its sheen, edge and blur)"""
    E = Errors()
    mode('ok')
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=E)
    disc_tab(pg); pg.mouse.move(3, 3); pg.wait_for_timeout(400)
    d = pg.evaluate(DESIGN_JS)
    check('design: row = --h-row (36), kind badge = the recipe (18 · 4px · 11px/600), kind tabs 32 · 13px, 지도 종목만 24, stock chip 24',
          d['row'] == 36 and d['badge'] == [18, '4px', '11px', '600'] and d['kind'] == [32, '13px'] and d['only'] == 24 and d['chip'] == 24, d)
    check('design: every font size in the tab is one of the seven steps (≥ 11px); the new dot = --new-dot', set(d['sizes']) <= {11, 12, 13, 14, 16, 20, 26} and d['dot'] == d['newDot'], d)
    check('design: 공시 종류 = one 2px --acc-line underline under the picked kind (KH.ui.seg)', d['ind'] and d['ul'] == ['2px', d['accLine']] and abs(d['ulX'] - d['selX']) <= 1 and abs(d['ulW'] - d['selW']) <= 1, d)
    pg.click('#news .dc-ktabs button[data-k="정기"]'); pg.wait_for_timeout(30)
    mv = pg.evaluate("() => { const t = document.querySelector('#news .dc-ktabs'), c = getComputedStyle(t, '::before'); return { dir: t.dataset.dir, fn: c.transitionTimingFunction.split('linear(').length - 1, prop: c.transitionProperty }; }")
    check('design: picking 정기 moves the underline right on lead (front) / trail (back)', mv['dir'] == 'r' and mv['fn'] >= 2 and 'left' in mv['prop'], mv)
    pg.click('#news .dc-ktabs button[data-k="all"]'); pg.wait_for_timeout(700)
    # the fold (KHNews.fold): the list box opens on `open`, the rows past the first count come in at a quarter; closing — out first
    pg.evaluate("""() => { window.__f = []; const t0 = performance.now(), l = document.querySelector('#news-p-disc .nw-list');
      const step = () => { const x = l.querySelector('.nw-x'); window.__f.push({ clip: l.style.clipPath, cls: l.className, rows: l.children.length, xo: x ? +getComputedStyle(x).opacity : -1,
        foot: Math.round(document.getElementById('foot').getBoundingClientRect().top + scrollY) }); if (performance.now() - t0 < 1000) requestAnimationFrame(step); };
      requestAnimationFrame(step); }""")
    pg.click('#news-p-disc .nw-more'); pg.wait_for_timeout(1200)
    fo = pg.evaluate("window.__f")
    op = [f for f in fo if f['rows'] == 30]
    check('design: 더보기 = the card\'s fold — page footer moves once at the press, the list clips open, the new rows wait hidden then come in, nothing left over',
          op and len({f['foot'] for f in op}) == 1 and any(f['clip'] for f in op) and any('nw-fold-anim' in f['cls'] and f['xo'] == 0 for f in op)
          and not op[-1]['clip'] and 'nw-fold' not in op[-1]['cls'] and op[-1]['xo'] == 1, [(f['rows'], f['cls'][-24:], f['xo']) for f in fo[:3]])
    pg.click('#news-p-disc .nw-more'); pg.wait_for_timeout(1000)
    check('design: 접기 → back to the first rows, no clip left', pg.evaluate("() => { const l = document.querySelector('#news-p-disc .nw-list'); return !l.style.clipPath && !l.style.height && !/nw-fold/.test(l.className) && l.children.length < 30; }"))
    check('design 1440: no console errors', not E.items, E.items[:3])
    ctx.close()
    # counts: a new answer → the counts that moved swap in place (§6-4); a map change (코스피 → 코스닥) → written at once (P4)
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1280, 800)
    disc_tab(pg); pg.mouse.move(3, 3); pg.wait_for_timeout(500)
    pg.evaluate("""() => { window.__sw = 0; new MutationObserver(ms => { for (const m of ms) if (m.target.classList && m.target.classList.contains('sw-go')) window.__sw++; })
      .observe(document.getElementById('news'), { subtree: true, attributes: true, attributeFilter: ['class'] }); }""")
    pg.evaluate("KHDisc.refresh()"); pg.wait_for_timeout(700)
    n1 = pg.evaluate("window.__sw")
    pg.evaluate("window.__sw = 0"); pg.click('.tabs button[data-mkt="Q"]'); pg.wait_for_timeout(900)
    n2 = pg.evaluate("window.__sw")
    check('design: a new answer swaps the counts that moved in place (KH.ui.swap); switching 코스피 → 코스닥 writes them at once', n1 >= 1 and n2 == 0, f'new answer {n1} swaps, map change {n2}')
    ctx.close()
    # glass: the tooltip with the 공시 block keeps the plate's material
    mode('ok')
    for th in ('glass-dark', 'glass-light'):
        ctx, pg = open_page(br, LIVE, 1440, 900, th)
        r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + Math.min(r.width / 2, 30), r.y + Math.min(r.height / 2, 20)]; })()")
        pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(600)
        g = pg.evaluate("""() => { const t = document.getElementById('tip'), b = t.querySelector('.dsc'), c = getComputedStyle(t), a = getComputedStyle(t, '::after');
          return { dsc: !!b, blur: c.backdropFilter, sheen: c.backgroundImage.includes('linear-gradient'), edge: a.content !== 'none' && a.content !== '', inset: /inset/.test(c.boxShadow),
            plate: b ? [getComputedStyle(b).backgroundColor, getComputedStyle(b).backdropFilter] : null }; }""")
        check(f'glass {th}: the tooltip with the 공시 block keeps its material — sheen, 1px edge ::after, inset edge light, blur; the block paints no plate',
              g['dsc'] and 'blur(' in g['blur'] and g['sheen'] and g['edge'] and g['inset'] and g['plate'] == ['rgba(0, 0, 0, 0)', 'none'], g)
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
                shots[name] = {k: pg.locator(sel).screenshot() for k, sel in (('map', '#map'), ('legend', '#legend'))}
                shots[name]['geo'] = pg.evaluate("() => ['#map', '#legend', ...document.querySelectorAll('main.layout > .side > section')].map(s => { const r = (typeof s === 'string' ? document.querySelector(s) : s).getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)]; })")
                shots[name]['dom'] = pg.evaluate("() => [...document.querySelectorAll('#map .node')].map(n => [n.className, n.style.cssText, n.getAttribute('aria-label') || '', n.textContent, n.style.color]).join('\\n') + document.getElementById('legend').innerHTML")
                # the side cards with the news card out of the way: on phones they sit under it, and a card above that ends on a fractional
                # pixel (its wrapped titles: 14px × 1.45) shifts their thin bars' anti-aliasing — what is compared is the cards themselves
                pg.add_style_tag(content='#news{display:none!important}')
                shots[name].update({k: pg.locator(sel).screenshot() for k, sel in (('side', 'main.layout > .side > section:nth-child(1)'),
                                    ('side2', 'main.layout > .side > section:nth-child(2)'), ('side3', 'main.layout > .side > section:nth-child(3)'))})
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
                  f"geo {same_geo} dom {shots['base']['dom'] == shots['new']['dom']} {gb} {gn} " + next((f'first DOM diff: {x[:160]} | {y[:160]}' for x, y in zip(shots['base']['dom'].split('\n'), shots['new']['dom'].split('\n')) if x != y), ''))
    finally:
        srv.terminate(); srv.wait(5)
        subprocess.run(['git', 'worktree', 'remove', '--force', str(wt)], cwd=ROOT, capture_output=True)


def shots(br):
    """--shots → qa/shots/disc_toggle/ (gitignored): the page + map header without the chip, the 오늘 공시 tab with the map switch off / on
    (1440 × 900 and 390 × 844, every theme), plus the tooltip and the phone quick view."""
    out = ROOT / 'qa/shots/disc_toggle'
    out.mkdir(parents=True, exist_ok=True)
    mode('ok')
    for th in THEMES:
        for w, h in ((1440, 900), (390, 844)):
            ctx, pg = open_page(br, LIVE, w, h, th)
            # the page header (#status with #live-mark) down to the map header (no 공시 chip, 지도 · 표 at the end) and the top of the map
            r = pg.evaluate("(() => { const r = document.querySelector('.stagebar').getBoundingClientRect(); return [r.y + scrollY, r.height]; })()")
            pg.screenshot(path=str(out / f'header_{w}_{th}.png'), clip={'x': 0, 'y': 0, 'width': w, 'height': r[0] + r[1] + 60})
            disc_tab(pg)
            # the card's tab row near the middle of the screen with the map above it (phones: the bottom of the map)
            pg.evaluate("(() => { const s = document.querySelector('#news-p-disc .dc-sub'); scrollTo(0, Math.max(0, s.getBoundingClientRect().top + scrollY - innerHeight * (innerWidth > 760 ? .55 : .5))); })()")
            pg.mouse.move(3, 3); pg.wait_for_timeout(300)
            pg.screenshot(path=str(out / f'tab_{w}_{th}_off.png'))
            (pg.tap if w <= 760 else pg.click)('#news .dc-lit'); pg.wait_for_timeout(400)
            pg.mouse.move(3, 3); pg.wait_for_timeout(100)
            pg.screenshot(path=str(out / f'tab_{w}_{th}_on.png'))
            ctx.close()
    for th in ('base', 'glass-light'):
        ctx, pg = open_page(br, LIVE, 1440, 900, th)
        r = pg.evaluate("(() => { const r = document.querySelector('#map .tile[data-c=\"005930\"]').getBoundingClientRect(); return [r.x + 40, r.y + 30]; })()")
        pg.mouse.move(r[0], r[1]); pg.wait_for_timeout(400)
        pg.screenshot(path=str(out / f'tip_1440_{th}.png'))
        ctx.close()
    ctx, pg = open_page(br, LIVE, 390, 844, 'paper')
    disc_tab(pg)
    pg.tap('#news .dc-row .dc-chip'); pg.wait_for_timeout(500)
    pg.screenshot(path=str(out / 'quick_390_paper.png'))
    ctx.close()
    mode('empty')
    ctx, pg = open_page(br, LIVE, 1440, 900, 'base')
    disc_tab(pg)
    pg.click('#news .dc-lit', force=True); pg.wait_for_timeout(250)
    pg.screenshot(path=str(out / 'tab_1440_base_zero.png'))
    ctx.close()
    mode('ok')
    print('shots →', out)


def refresh_key(br):
    # ── 18 · ↻ 새로 받기 on the 오늘 공시 tab (the news card head's key, 사용자 2026-11-16 09:24): this tab's list only; under 10 s since its
    #        last answer → no request ("방금 받았어요"); a press brings the new filing at once (pointer in the pane), with its new dot, the
    #        counts swapping (§6-4) and the head's time from the answer; a failure → ! (--fail-dot), the list stays ──
    E = Errors()
    E.allow = ['Failed to load resource']
    mode('drift')
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=E, clock=True)
    disc_tab(pg)
    pg.click('#news .dc-only'); pg.wait_for_timeout(300)          # 지도 종목만 off: the drift rows are outside the map
    k = pg.evaluate("({ label: document.querySelector('#news .nw-rk').getAttribute('aria-label'), hidden: document.querySelector('#news .nw-rk').hidden })")
    check('↻ on 오늘 공시: "오늘 공시 새로 받기", shown', k['label'] == '오늘 공시 새로 받기' and not k['hidden'], k)
    route = '/api/disclosures/today'
    n0 = mock('/__stats').get(route, 0)
    pg.click('#news .nw-rk'); pg.wait_for_timeout(300)
    b = pg.evaluate("[...document.querySelectorAll('.kbub')].map(b => b.textContent)")
    check('↻ under 10 s since the last answer → no request, "방금 받았어요"', mock('/__stats').get(route, 0) == n0 and '방금 받았어요' in b, (mock('/__stats').get(route, 0) - n0, b))
    top = "(() => { const r = document.querySelector('#news-p-disc .dc-row'); return [r.querySelector('.dc-tt a').textContent, !!r.querySelector('.dc-dot')]; })()"
    cnt = "document.querySelector('#news .dc-ktabs button[aria-pressed=\"true\"] small').textContent"
    t0, c0 = pg.evaluate(top), pg.evaluate(cnt)
    n_news = mock('/__stats').get('/api/news', 0)
    pg.route('**/api/disclosures/today*', lambda r: r.fulfill(json=dict(_j := json.loads(r.fetch().text()), asOf=_j['asOf'][:11] + '23:58:00+09:00')))
    pg.clock.run_for(11000); pg.wait_for_timeout(100)
    n0 = mock('/__stats').get(route, 0)
    pg.evaluate("window.__sw = []; const o = KH.ui.swap; KH.ui.swap = (el, t, f, d) => { __sw.push([el.closest('.dc-ktabs') ? 'kind' : el.closest('.nw-ftabs') ? 'title' : el.className, String(f), String(t)]); return o(el, t, f, d); }; 0")
    pg.hover('#news-p-disc .dc-row:nth-child(2)'); pg.hover('#news .nw-rk'); pg.click('#news .nw-rk'); pg.wait_for_timeout(800)
    sw = pg.evaluate("__sw")
    t1, c1 = pg.evaluate(top), pg.evaluate(cnt)
    at = pg.evaluate("document.querySelector('#news .nw-at').textContent")
    check('↻: one request for this tab only (시장 뉴스 not asked)', mock('/__stats').get(route, 0) - n0 == 1 and mock('/__stats').get('/api/news', 0) == n_news, (mock('/__stats').get(route, 0) - n0, mock('/__stats').get('/api/news', 0) - n_news))
    check('↻ with the pointer in the pane: the new filing on top at once, with its new dot; head = the answer\'s time', t1[0] != t0[0] and '시험' in t1[0] and t1[1] and at == '23:58 기준', (t0, t1, at))
    check('↻: the kind count moved with the answer and swapped in place (§6-4)', c1 != c0 and any(x[0] == 'kind' and x[1] == c0 and x[2] == c1 for x in sw), (c0, c1, sw))
    st = pg.evaluate("document.querySelector('#news .nw-rk').dataset.st")
    check('↻: ✓ (done) after the answer', st == 'done', st)
    pg.unroute('**/api/disclosures/today*')
    mode('fail', 'ok')
    pg.clock.run_for(11000); pg.wait_for_timeout(100)
    pg.click('#news .nw-rk'); pg.wait_for_timeout(700)
    f = pg.evaluate("({ st: document.querySelector('#news .nw-rk').dataset.st, rows: document.querySelectorAll('#news-p-disc .dc-row:not(.skel)').length, bub: [...document.querySelectorAll('.kbub')].map(b => b.textContent), col: getComputedStyle(document.querySelector('#news .nw-rk .kwn')).color, fd: (() => { const i = document.createElement('i'); i.style.color = 'var(--fail-dot)'; document.body.append(i); const c = getComputedStyle(i).color; i.remove(); return c; })() })")
    check('↻ fails → ! (--fail-dot) + "못 받았어요"; the list stays', f['st'] == 'fail' and f['rows'] > 0 and f['col'] == f['fd'] and any('못 받았어요' in x for x in f['bub']), f)
    ctx.close()
    check('↻ (오늘 공시): no console errors', not E.items, E.items[:3])
    mode('ok')


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
            if not ONLY:
                run(br)
            if ONLY in ('', 'design'):
                design(br)
            if ONLY in ('', 'refresh'):
                refresh_key(br)
            if ONLY in ('', 'baseline'):
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
