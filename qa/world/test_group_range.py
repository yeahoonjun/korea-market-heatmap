#!/usr/bin/env python3
"""색 범위 자동 · 구역마다 (AGENTS §3-27, 사용자 2026-11-16 13:04) — QA on the built page.

  python3 scripts/build_page.py && python3 qa/world/test_group_range.py [--shots DIR]

Starts qa/world/mock_api.py on GR_QA_PORT (default 9042) with 환율 · 금리 (macro=on) and 증시 자금 (funds=on). The expected ranges are
computed here from the fixtures with the rule written down in design.md §2 (p95 of |value| → the next step of the zone table; 금리 on
its bp change) — independent of the page's own code. Checks:
  tables · one range per group (환율 · 금리 · 증시 자금 · 에너지 · 금속 · 농산물), different groups → different ranges · every chip and
  bar on its group's range (금리 by bp) · the same value drawn in two groups → two colours (a routed /api/world answer) · group head
  tags · 등락률순 caption · legend "자동 · 구역마다" + 구역 범위 row · the template's 자동 key · 많이 오른·내린 swatches · detail
  sheet swatch · KHWorld.layout() tiles · hysteresis (on the page and the shared function against a model) · a picked ±5 % = one
  range for the tab (zones gone, 금리 back on % like before) · 해외 tab and 국내 tabs untouched · old KH.colorOf calls unchanged ·
  4 themes × 360 · 1280: nothing drawn past the viewport, tags not cut, console errors 0.
Exit code 1 if any check fails.
"""
import argparse
import json
import math
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('GR_QA_PORT', 9042))
LIVE = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')

ap = argparse.ArgumentParser()
ap.add_argument('--shots', default=os.environ.get('GR_SHOTS', '/tmp/group_range'))
ARGS = ap.parse_args()
SHOTS = pathlib.Path(ARGS.shots)
SHOTS.mkdir(parents=True, exist_ok=True)

TAB_STEPS = [1, 2, 3, 4, 5, 7, 10, 15, 20, 30]
PCT_STEPS = [0.2, 0.3, 0.5, 0.7] + TAB_STEPS
BP_STEPS = [2, 3, 5, 7, 10, 15, 20, 30, 50]

FIX = {k: json.loads((HERE / f'fixtures/{k}.json').read_text(encoding='utf-8')) for k in ('world_commodity', 'world_macro', 'world_index', 'funds')}
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def p95(vals):
    a = sorted(abs(v) for v in vals if v is not None)
    if not a:
        return None
    i = (len(a) - 1) * 0.95
    lo = math.floor(i)
    hi = min(len(a) - 1, lo + 1)
    return a[lo] + (a[hi] - a[lo]) * (i - lo)


def step_of(p, steps):
    return next((s for s in steps if s >= p - 1e-9), steps[-1])


def hyst(seq, steps):
    """the rule of design.md §2: a higher step at once, a lower one only when p95 / 0.85 still fits it"""
    cur, out = None, []
    for p in seq:
        up = step_of(p, steps)
        cur = up if cur is None or up > cur else min(cur, step_of(p / 0.85, steps))
        out.append(cur)
    return out


def bp_of(it):
    return it['bp'] if it.get('bp') is not None else round(it['change'] * 10000) / 100


# ── what the page must draw, from the fixtures ──
GROUPS = []          # (key, name, unit, [items with gkey])
for fx in ('world_macro', 'world_commodity'):
    for g in FIX[fx]['groups']:
        GROUPS.append((g['key'], g['name'], 'bp' if g['key'] == 'rates' else '%', [dict(it, gkey=g['key']) for it in g['items']]))
GROUPS.append(('funds', '증시 자금', '%', [dict(it, gkey='funds', key='fd:' + it['key']) for it in FIX['funds']['items']]))
ITEMS = {it['key']: it for _, _, _, its in GROUPS for it in its}
ZNUM = {it['key']: (bp_of(it) if it['gkey'] == 'rates' else it['ratio']) for it in ITEMS.values()}
EXP = {}
for key, name, unit, its in GROUPS:
    p = p95([ZNUM[it['key']] for it in its if not it.get('ref')])
    EXP[key] = {'name': name, 'unit': unit, 'p95': p, 'value': step_of(p, BP_STEPS if unit == 'bp' else PCT_STEPS)}
ORDER = ['fx', 'rates', 'funds', 'energy', 'metals', 'agri']      # the list's order (환율 · 금리 · 증시 자금 first)
TAB_P = p95([it['ratio'] for it in ITEMS.values() if it['gkey'] != 'funds' and not it.get('ref') and it.get('ratio') is not None])
TAB_EXP = step_of(TAB_P, TAB_STEPS)


def rtxt(v):
    """the template's fmtR: String(+(a >= 10 ? a.toFixed(0) : a >= 1 ? a.toFixed(1) : a.toFixed(2)))"""
    a = abs(v)
    f = float(f'{a:.0f}' if a >= 10 else f'{a:.1f}' if a >= 1 else f'{a:.2f}')
    return str(int(f)) if f == int(f) else repr(f)


def ztxt(z):
    return f"±{rtxt(z['value'])}{'bp' if z['unit'] == 'bp' else '%'}"


print('expected zones:', {k: (round(v['p95'], 3), ztxt(v)) for k, v in EXP.items()}, '· tab step', TAB_EXP, flush=True)


class Errors:
    def __init__(self):
        self.items = []

    def attach(self, page, tag):
        page.on('console', lambda m: self.items.append(f'{tag}: {m.text[:160]}') if m.type == 'error' else None)
        page.on('pageerror', lambda e: self.items.append(f'{tag}: {str(e)[:160]}'))


ERR = Errors()


def mode(q):
    NOPROXY.open(LIVE + '__mode?' + q, timeout=3).read()


def open_page(browser, width, height, theme='base', url=LIVE + '#cmdty', pre=None, route=None, tag=''):
    mobile = width < 700
    ctx = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile,
                              service_workers='block')
    store = {'khm.theme': theme}
    store.update(pre or {})
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__grPre')) return; sessionStorage.setItem('__grPre', '1'); "
                        + ''.join(f'localStorage.setItem({json.dumps(k)}, {json.dumps(v)});' for k, v in store.items()) + '})();')
    page = ctx.new_page()
    ERR.attach(page, tag or f'{theme} {width}')
    if route:
        page.route('**/api/world?*', route)
    page.goto(url)
    page.wait_for_selector('#world .kw-lr', timeout=15000)
    page.wait_for_function(f"document.querySelectorAll('#world .kw-lr').length >= {len(ITEMS) if '#cmdty' in url else 10}", timeout=15000)
    page.wait_for_timeout(500)
    return ctx, page


NORM = "const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };"

STATE_JS = """() => ({ zones: KHWorld.zones(), ri: KH.rangeInfo(), range: KH.range(),
  steps: { pct: KH.autoSteps('%'), bp: KH.autoSteps('bp'), tab: KH.autoSteps() },
  heads: Object.fromEntries([...document.querySelectorAll('#world .kw-sec[data-g]')].map(s => { const t = s.querySelector('.kw-sh .kw-rg');
    return [s.dataset.g, t ? { shown: !t.hidden && t.getBoundingClientRect().width > 0, text: t.textContent.replace('색 범위 ', ''), title: t.title } : null]; })),
  caps: [...document.querySelectorAll('#world .kw-bt')].map(b => ({ b: b.dataset.b, title: (b.querySelector('.kw-btt') || b).textContent,
    tags: [...b.querySelectorAll('.kw-btz:not([hidden]) .kw-rg')].map(t => t.textContent.replace('색 범위 ', '')) })),
  legend: { rauto: (document.querySelector('#world .kw-legend .rauto') || {}).textContent || null,
    ticks: [...document.querySelectorAll('#world .kw-legend .tk')].map(t => t.textContent),
    zones: [...document.querySelectorAll('#world .kw-legend .kw-lgzi')].map(t => t.textContent),
    text: document.querySelector('#world .kw-legend').innerText.replace(/\\n/g, ' | ') },
  key: (() => { const b = document.querySelector('#rangeseg button[data-v="auto"]'); return b ? { aria: b.getAttribute('aria-label'), title: b.title } : null; })() })"""

CHIPS_JS = """([items, zones]) => { """ + NORM + """
  const out = { n: 0, bad: [], bar: [] };
  for (const r of document.querySelectorAll('#world .kw-lr')) {
    const it = items[r.dataset.k]; if (!it) continue;
    const z = zones && zones[it.gkey]; out.n++;
    const v = z ? it.z : it.ratio;
    const want = norm(z ? KH.colorOf(v, { scope: 'world', range: z.value }) : KH.colorOf(it.ratio, 'world'));
    const got = getComputedStyle(r.querySelector('.kw-pchip')).backgroundColor;
    if (got !== want) out.bad.push(`${it.key} ${got} != ${want}`);
    const bar = r.querySelector('.kw-lb i'), R = z ? z.value : KH.range();
    const frac = Math.min(Math.abs(v) / R, 1) * 50, w = parseFloat(bar.style.width);
    if (Math.abs(w - frac) > 0.06 || getComputedStyle(bar).backgroundColor !== got) out.bar.push(`${it.key} bar ${w} vs ${frac.toFixed(2)}`);
  }
  return out; }"""

# nothing of #world drawn past the viewport's sides (html/body clip sideways, so scrollWidth cannot tell): elements inside a box that
# clips or scrolls sideways are that box's business
OVER_JS = """() => { const vw = document.documentElement.clientWidth, out = [];
  const W = document.getElementById('world');
  const clipped = el => { for (let p = el.parentElement; p && p !== W; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o !== 'visible') return true; } return false; };
  for (const el of W.querySelectorAll('*')) {
    if (!el.getClientRects().length) continue;
    const r = el.getBoundingClientRect(); if (!r.width) continue;
    if ((r.right > vw + 0.5 || r.left < -0.5) && !clipped(el)) out.push(`${el.className || el.tagName} ${Math.round(r.left)}-${Math.round(r.right)}`);
  }
  const tags = [...W.querySelectorAll('.kw-rg')].filter(t => !t.hidden && t.getClientRects().length);
  const cut = tags.filter(t => { const r = t.getBoundingClientRect(), h = (t.closest('.kw-sh, .kw-bt') || W).getBoundingClientRect();
    return t.scrollWidth > t.clientWidth + 1 || r.right > h.right + 0.5 || r.left < h.left - 0.5; }).map(t => t.textContent);
  const notes = [...W.querySelectorAll('.kw-sh .a.note small')].filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent);
  return { over: out.slice(0, 6), n: out.length, tags: tags.length, cut, notes, doc: document.documentElement.scrollWidth - innerWidth }; }"""


def items_payload():
    return {k: dict(key=k, gkey=it['gkey'], ratio=it.get('ratio'), z=ZNUM[k]) for k, it in ITEMS.items() if not it.get('ref')}


def press_range(pg, v):
    vis = pg.evaluate("() => { const b = document.querySelector('#rangeseg'); return !!(b && b.getClientRects().length && b.getBoundingClientRect().width); }")
    if not vis:
        pg.click('#setBtn')
        pg.wait_for_timeout(450)
    pg.click(f'#rangeseg button[data-v="{v}"]')
    pg.wait_for_timeout(400)
    if not vis:
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(400)


def main_pass(b):
    ctx, pg = open_page(b, 1280, 800, tag='main 1280')
    try:
        st = pg.evaluate(STATE_JS)
        check('step tables = design.md §2 (zone % 0.2 · 0.3 · 0.5 · 0.7 + the tab steps, bp 2 … 50, tab 1 … 30)',
              st['steps']['pct'] == PCT_STEPS and st['steps']['bp'] == BP_STEPS and st['steps']['tab'] == TAB_STEPS, json.dumps(st['steps']))
        z = st['zones'] or {}
        got = {k: (v['value'], v['unit']) for k, v in z.items()}
        want = {k: (v['value'], v['unit']) for k, v in EXP.items()}
        pok = all(abs(z[k]['p95'] - EXP[k]['p95']) < 1e-6 for k in EXP if k in z)
        check('one range per group, measured on that group (금리 on bp) = p95 → zone step', got == want and pok, f'page {got} · expected {want}')
        check('groups get different ranges (환율 ≠ 에너지, ≥ 3 distinct)', z.get('fx', {}).get('value') != z.get('energy', {}).get('value')
              and len({v['value'] for v in z.values()}) >= 3, str(sorted({v['value'] for v in z.values()})))
        ri = st['ri']
        check('rangeInfo: tab step as before (증시 자금 left out) + zones in list order', ri['value'] == TAB_EXP and st['range'] == TAB_EXP
              and [x['key'] for x in (ri.get('zones') or [])] == ORDER and all(x['value'] == EXP[x['key']]['value'] for x in ri['zones']),
              f"tab ±{ri['value']} (expected {TAB_EXP}), zones {[(x['key'], x['value']) for x in (ri.get('zones') or [])]}")
        c = pg.evaluate(CHIPS_JS, [items_payload(), z])
        check('every chip on its group\'s range (금리 by bp), bar = |v| / group range', c['n'] == len(items_payload()) and not c['bad'] and not c['bar'],
              '; '.join((c['bad'] + c['bar'])[:4]) or f"{c['n']} rows")
        same = pg.evaluate("""([v, a, b]) => ({ a: KH.colorOf(v, { scope: 'world', range: a }), b: KH.colorOf(v, { scope: 'world', range: b }), tab: KH.colorOf(v, 'world') })""",
                           [0.1, EXP['fx']['value'], EXP['energy']['value']])
        check('same value, different zone → different colour (KH.colorOf(0.1) on 환율 vs 에너지 range)', same['a'] != same['b'] and same['a'] != same['tab'], json.dumps(same))
        heads = st['heads']
        bad = [f"{k} {heads.get(k)} != {ztxt(EXP[k])}" for k in ORDER if not heads.get(k) or not heads[k]['shown'] or heads[k]['text'] != ztxt(EXP[k])]
        check('group heads: "±0.2%" · 금리 "±7bp" beside the name', not bad, '; '.join(bad) or ', '.join(f"{k} {heads[k]['text']}" for k in ORDER))
        check('head tag title says the rule (자동 · 95%)', all('95%' in heads[k]['title'] for k in ORDER) and 'bp' in heads['rates']['title'], heads['rates']['title'])
        lg = st['legend']
        check('legend: "자동 · 구역마다", no ±N ticks, 구역 범위 row in list order, bar = 구역 범위',
              lg['rauto'] == '자동 · 구역마다' and not lg['ticks'] and lg['zones'] == [f"{EXP[k]['name']} {ztxt(EXP[k])}" for k in ORDER] and '끝이 구역 범위' in lg['text'],
              lg['text'][:240])
        tag = pg.evaluate("() => getComputedStyle(document.querySelector('#world .kw-sh .kw-rg')).boxShadow + ' | ' + getComputedStyle(document.querySelector('#world .kw-sh .kw-rg')).color")
        acc = pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#ffb547'")
        check('tags look like the "자동 ±N%" tag (thin ring), no amber', 'inset' in tag and '255, 181, 71' not in tag, f'{tag} (accent {acc})')
        key = st['key']
        check('template 자동 key: "자동, 구역마다", title lists the zones', key and key['aria'] == '자동, 구역마다' and key['title'].startswith('구역마다') and '환율 ±' in key['title'], json.dumps(key, ensure_ascii=False))
        # 많이 오른·내린 swatches, detail sheet swatch, the image's tiles
        rk = pg.evaluate("""([items, zones]) => { """ + NORM + """ const bad = []; let n = 0;
          for (const b of document.querySelectorAll('#world .kw-row[data-k]')) { const it = items[b.dataset.k]; if (!it) continue; n++; const z = zones[it.gkey];
            const want = norm(KH.colorOf(it.z, { scope: 'world', range: z.value })), got = getComputedStyle(b.querySelector('.kw-sw')).backgroundColor;
            if (got !== want) bad.push(`${it.key} ${got} != ${want}`); } return { n, bad }; }""", [items_payload(), z])
        check('많이 오른·내린 swatches = their group\'s range', rk['n'] >= 6 and not rk['bad'], '; '.join(rk['bad'][:3]) or f"{rk['n']} swatches")
        lay = pg.evaluate("""([items, zones]) => { """ + NORM + """ const bad = []; let n = 0;
          for (const x of KHWorld.layout()) { if (x.kind !== 'tile') continue; const it = items[x.code]; if (!it) continue; n++; const z = zones[it.gkey];
            if (norm(x.color) !== norm(KH.colorOf(it.z, { scope: 'world', range: z.value }))) bad.push(x.code); } return { n, bad }; }""", [items_payload(), z])
        check('KHWorld.layout() (이미지 저장) tiles = their group\'s range', lay['n'] >= len(items_payload()) - 1 and not lay['bad'], f"{lay['n']} tiles, bad {lay['bad'][:4]}")
        for k in ('FX_USDKRW', 'US10YT'):
            pg.click(f'#world .kw-lr[data-k="{k}"]')
            pg.wait_for_selector('.kw-sheet:not([hidden]) .kw-sw', timeout=8000)
            pg.wait_for_timeout(250)
            sw = pg.evaluate(f"""() => ({{ sheet: getComputedStyle(document.querySelector('.kw-sheet .kw-sw')).backgroundColor,
              row: getComputedStyle(document.querySelector('#world .kw-lr[data-k="{k}"] .kw-pchip')).backgroundColor }})""")
            check(f'detail sheet swatch = the row\'s group colour ({k})', sw['sheet'] == sw['row'], json.dumps(sw))
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(500)
        # 등락률순: the ranked 원자재 rows mix groups → the caption carries their ranges; colours do not move with the order
        before = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('#world .kw-lr')].map(r => [r.dataset.k, getComputedStyle(r.querySelector('.kw-pchip')).backgroundColor]))")
        pg.click('#world .kw-seg[data-kw=sort] button[data-v=pct]')
        pg.wait_for_timeout(600)
        st2 = pg.evaluate(STATE_JS)
        after = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('#world .kw-lr')].map(r => [r.dataset.k, getComputedStyle(r.querySelector('.kw-pchip')).backgroundColor]))")
        cm = next((c2 for c2 in st2['caps'] if c2['b'] == 'cm'), None)
        check('등락률순: 원자재 caption lists 에너지 · 금속 · 농산물 ranges, 환율 · 금리 · 증시 자금 heads keep theirs',
              cm and cm['tags'] == [f"{EXP[k]['name']} {ztxt(EXP[k])}" for k in ('energy', 'metals', 'agri')] and all(st2['heads'][k]['shown'] for k in ('fx', 'rates', 'funds')),
              json.dumps(st2['caps'], ensure_ascii=False))
        check('등락률순: every chip keeps its colour (colour = group, not order)', before == after, str([k for k in before if before[k] != after.get(k)][:4]))
        pg.screenshot(path=str(SHOTS / 'gr_1280_pct.png'), full_page=True)
        pg.click('#world .kw-seg[data-kw=sort] button[data-v=group]')
        pg.wait_for_timeout(500)
        cap = pg.evaluate(STATE_JS)['caps']
        check('종류순: captions without tags (텍스트 = 제목)', all(not c2['tags'] for c2 in cap) and [c2['title'] for c2 in cap] == ['환율 · 금리 · 증시 자금', '원자재'], json.dumps(cap, ensure_ascii=False))
        # hysteresis on the page: push a zone up through the shared function, redraw with the same data
        h = pg.evaluate("""async () => { const up = { metals: KH.autoRange('CMDTY:metals', [2.5], '%').value, agri: KH.autoRange('CMDTY:agri', [2.5], '%').value,
            fx: KH.autoRange('CMDTY:fx', [0.25], '%').value, rates: KH.autoRange('CMDTY:rates', [9], 'bp').value };
          document.dispatchEvent(new CustomEvent('kh:palette')); await new Promise(r => setTimeout(r, 300));
          const z = KHWorld.zones(); const tag = g => document.querySelector(`#world .kw-sec[data-g="${g}"] .kw-rg`).textContent.replace('색 범위 ', '');
          return { up, now: { metals: z.metals.value, agri: z.agri.value, fx: z.fx.value, rates: z.rates.value }, tag: { metals: tag('metals'), rates: tag('rates') } }; }""")
        m_hold = hyst([2.5, EXP['metals']['p95']], PCT_STEPS)[-1]
        a_drop = hyst([2.5, EXP['agri']['p95']], PCT_STEPS)[-1]
        f_drop = hyst([0.25, EXP['fx']['p95']], PCT_STEPS)[-1]
        r_hold = hyst([9, EXP['rates']['p95']], BP_STEPS)[-1]
        check('hysteresis per zone on the page: 금속 holds ±3 (p95 1.72 ÷ 0.85 still needs 3), 농산물 drops to 2, 환율 drops to 0.2, 금리 bp holds',
              h['up'] == {'metals': 3, 'agri': 3, 'fx': 0.3, 'rates': 10} and h['now'] == {'metals': m_hold, 'agri': a_drop, 'fx': f_drop, 'rates': r_hold}
              and h['tag']['metals'] == f'±{rtxt(m_hold)}%' and h['tag']['rates'] == f'±{rtxt(r_hold)}bp',
              f"{h} · model metals {m_hold} agri {a_drop} fx {f_drop} rates {r_hold}")
        seqs = {'%': [0.25, 0.29, 0.26, 0.24, 0.17, 0.16, 0.61, 0.45, 0.42, 1.1, 0.8, 0.02, 31, 26, 25.4], 'bp': [1, 2.5, 2.4, 1.6, 1.7, 9, 7.6, 5.9, 60, 44, 42.4]}
        for unit, seq in seqs.items():
            gotq = pg.evaluate("([u, s]) => s.map(p => KH.autoRange('qa:' + u, [p, -p], u).value)", [unit, seq])
            wantq = hyst(seq, BP_STEPS if unit == 'bp' else PCT_STEPS)
            check(f'KH.autoRange ({unit}) = the tabs\' rule on the zone table (up at once, down only 15 % under)', gotq == wantq, f'got {gotq} want {wantq}')
        none = pg.evaluate("() => [KH.autoRange('qa:none', [], '%'), KH.autoRange('qa:none', [null, NaN], 'bp')]")
        check('KH.autoRange without values → null (the caller keeps the tab range)', none == [None, None], str(none))
        old = pg.evaluate("""() => { const vs = [-12, -3.1, -0.4, 0, 0.05, 1.7, 4.2, 30]; const R = KH.range();
          return vs.every(v => KH.colorOf(v, 'world') === KH.colorOf(v, { scope: 'world' }) && KH.colorOf(v, { scope: 'world', range: R }) === KH.colorOf(v, 'world')
            && KH.colorOf(v, { scope: 'world', range: 0 }) === KH.colorOf(v, 'world') && KH.colorOf(v, { range: -1 }) === KH.colorOf(v)); }""")
        check('old calls unchanged: colorOf(r, "world") = {scope} = {range: today}; a bad range = today\'s', old)
        # a picked ±5: one range for the tab, as before (금리 back on its % change)
        press_range(pg, '5')
        ms = pg.evaluate(STATE_JS)
        visible = [k for k, v in ms['heads'].items() if v and v['shown']]
        c5 = pg.evaluate(CHIPS_JS, [items_payload(), None])
        check('picked ±5: no zones, no tags, legend "오늘 등락률 −5% · +5%", 자동 key named as before',
              ms['zones'] is None and ms['ri']['zones'] is None and not visible and ms['legend']['rauto'] is None and ms['legend']['ticks'] == ['−5%', '+5%']
              and '오늘 등락률' in ms['legend']['text'] and not ms['legend']['zones'] and ms['key']['aria'].startswith('자동, 지금 ±'),
              f"{ms['zones']} tags {visible} {ms['legend']['text'][:120]} · {ms['key']}")
        check('picked ±5: every chip on ±5 % — 금리 too, by its % change (the rule before 구역마다)', c5['n'] == len(items_payload()) and not c5['bad'] and not c5['bar'],
              '; '.join((c5['bad'] + c5['bar'])[:3]) or f"{c5['n']} rows")
        press_range(pg, 'auto')
        back = pg.evaluate(STATE_JS)
        check('back to 자동: zones return', back['zones'] is not None and back['legend']['rauto'] == '자동 · 구역마다', str(back['legend']['rauto']))
        # 해외 · 국내 tabs
        pg.click('.tabs button[data-mkt="WORLD"]')
        pg.wait_for_timeout(1500)
        ws = pg.evaluate(STATE_JS)
        wvis = [k for k, v in ws['heads'].items() if v and v['shown']]
        check('해외 tab: one range for the tab as before ("자동 ±N%", ±N ticks, no zones · tags)', ws['zones'] is None and ws['ri']['zones'] is None and not wvis
              and (ws['legend']['rauto'] or '').startswith('자동 ±') and len(ws['legend']['ticks']) == 2, f"{ws['legend']['rauto']} {ws['legend']['ticks']} {wvis}")
        pg.click('.tabs button[data-mkt="Q"]')
        pg.wait_for_timeout(1500)
        ks = pg.evaluate("() => ({ z: KHWorld.zones(), ri: KH.rangeInfo(), aria: document.querySelector('#rangeseg button[data-v=auto]').getAttribute('aria-label') })")
        check('국내 tab: no zones, 자동 key as before', ks['z'] is None and ks['ri']['zones'] is None and ks['aria'].startswith('자동, 지금 ±'), json.dumps(ks, ensure_ascii=False)[:200])
    finally:
        ctx.close()


def routed_pass(b):
    """the same value in two groups → two colours, on the page (the /api/world answer gets 원/유로 and 난방유 at +0.50 %)"""
    def route(r):
        resp = r.fetch()
        j = resp.json()
        for g in j.get('groups', []):
            for it in g['items']:
                if it['key'] in ('FX_EURKRW', 'HOcv1'):
                    it['ratio'] = 0.5
                    it['change'] = abs(it['change'])
        r.fulfill(response=resp, body=json.dumps(j))
    ctx, pg = open_page(b, 1280, 800, route=route, tag='routed')
    try:
        r = pg.evaluate("""() => { const c = k => getComputedStyle(document.querySelector(`#world .kw-lr[data-k="${k}"] .kw-pchip`)).backgroundColor;
          const t = k => document.querySelector(`#world .kw-lr[data-k="${k}"] .kw-pchip`).textContent; const z = KHWorld.zones();
          return { fx: c('FX_EURKRW'), en: c('HOcv1'), tf: t('FX_EURKRW'), te: t('HOcv1'), zfx: z.fx.value, zen: z.energy.value }; }""")
        check('same +0.50 % in 환율 and 에너지 → two colours (환율 range ≠ 에너지 range)', r['tf'] == r['te'] == '+0.50%' and r['fx'] != r['en'] and r['zfx'] < r['zen'], json.dumps(r))
    finally:
        ctx.close()


def layout_pass(b):
    for theme in THEMES:
        for w, hgt in ((360, 740), (1280, 800)):
            ctx, pg = open_page(b, w, hgt, theme=theme, tag=f'{theme} {w}')
            try:
                o = pg.evaluate(OVER_JS)
                check(f'{theme} {w}: nothing past the viewport, tags not cut, head notes whole', o['n'] == 0 and o['doc'] <= 0 and o['tags'] >= 6 and not o['cut'] and not o['notes'],
                      f"over {o['over']} doc {o['doc']} tags {o['tags']} cut {o['cut']} notes {o['notes']}")
                pg.click('#world .kw-seg[data-kw=sort] button[data-v=pct]')
                pg.wait_for_timeout(500)
                o2 = pg.evaluate(OVER_JS)
                check(f'{theme} {w} 등락률순: nothing past the viewport, caption tags whole', o2['n'] == 0 and not o2['cut'], f"over {o2['over']} cut {o2['cut']}")
                if theme in ('base', 'glass-light'):
                    loc = pg.locator('#world .kw-bt[data-b=cm]')
                    loc.scroll_into_view_if_needed()
                    pg.screenshot(path=str(SHOTS / f'gr_{theme}_{w}_pct.png'))
                pg.click('#world .kw-seg[data-kw=sort] button[data-v=group]')
                pg.wait_for_timeout(400)
                pg.evaluate('() => scrollTo(0, 0)')
                pg.screenshot(path=str(SHOTS / f'gr_{theme}_{w}.png'), full_page=w >= 700)
            finally:
                ctx.close()


def main():
    proc = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                mode('macro=on&funds=on')
                break
            except Exception:
                time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            try:
                main_pass(b)
                routed_pass(b)
                layout_pass(b)
            finally:
                b.close()
    finally:
        try:
            mode('macro=off&funds=empty')
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
    check('console errors 0', not ERR.items, '; '.join(ERR.items[:4]))
    bad = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(bad)}/{len(results)} checks passed · screenshots in {SHOTS}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
