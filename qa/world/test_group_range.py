#!/usr/bin/env python3
"""색 범위 자동 · 구역마다 (AGENTS §3-27, 사용자 2026-11-16 13:04 + 후속 13:42) — QA on the built page.

  python3 scripts/build_page.py && python3 qa/world/test_group_range.py [--shots DIR]

Starts qa/world/mock_api.py on GR_QA_PORT (default 9042) with 환율 · 금리 (macro=on) and 증시 자금 (funds=on). The expected ranges are
computed here from the fixtures with the rule written down in design.md §2 (p95 of |value| → the next step of the zone table; 금리 on
its bp change) — independent of the page's own code. Checks:
  tables · one range per group (환율 · 금리 · 증시 자금 · 에너지 · 금속 · 농산물), different groups → different ranges · every chip and
  bar on its group's range (금리 by bp) · the same value drawn in two groups → two colours (a routed /api/world answer) · group head
  tags · 등락률순 caption · legend "자동 · 구역마다" + 구역 범위 row · the template's 자동 key · 많이 오른·내린 swatches · detail
  sheet swatch · KHWorld.layout() tiles · hysteresis (on the page and the shared function against a model) · a picked ±5 % = one
  range for the tab except 금리, which keep their own bp 자동 range (후속 ①: tag "±Nbp 자동", legend 구역 범위 row, bar note) ·
  증시 자금's 반대매매 rows a zone of their own (후속 ②: two head tags "±3%" · "반대매매 ±30%", legend, 자동 key) · the same 지표 row
  the same colour everywhere (후속 ③: a sheet the ticker opens on 국내 · 해외 tabs before the 지표 tab was ever opened, under 자동
  and a picked ±5, = the 지표 tab's chip; zones measured off the tab = the tab's; the ticker's and summary card's own numbers are
  direction colours of the 해외 · 지표 palette and no range reaches them) · 해외 tab and 국내 tabs untouched · old KH.colorOf calls
  unchanged · 4 themes × 360 · 1280: nothing drawn past the viewport, tags not cut, head notes whole, console errors 0.
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
FORCED = ('forced', 'forcedRatio')   # 증시 자금's 반대매매 rows: a zone of their own (후속 ②)
GROUPS = []          # (key, name, unit, [items with gkey · zk])
for fx in ('world_macro', 'world_commodity'):
    for g in FIX[fx]['groups']:
        GROUPS.append((g['key'], g['name'], 'bp' if g['key'] == 'rates' else '%', [dict(it, gkey=g['key'], zk=g['key']) for it in g['items']]))
GROUPS.append(('funds', '증시 자금', '%', [dict(it, gkey='funds', key='fd:' + it['key'], zk='forced' if it['key'] in FORCED else 'funds') for it in FIX['funds']['items']]))
ITEMS = {it['key']: it for _, _, _, its in GROUPS for it in its}
ZNUM = {it['key']: (bp_of(it) if it['gkey'] == 'rates' else it['ratio']) for it in ITEMS.values()}
ZONES = []           # (zone key, name, unit, group)
for key, name, unit, its in GROUPS:
    for zk in dict.fromkeys(it['zk'] for it in its):
        ZONES.append((zk, '반대매매' if zk == 'forced' else name, unit, key))
EXP = {}
for zk, name, unit, gk in ZONES:
    p = p95([ZNUM[it['key']] for it in ITEMS.values() if it['zk'] == zk and not it.get('ref')])
    EXP[zk] = {'name': name, 'unit': unit, 'p95': p, 'value': step_of(p, BP_STEPS if unit == 'bp' else PCT_STEPS), 'group': gk}
ORDER = ['fx', 'rates', 'funds', 'forced', 'energy', 'metals', 'agri']      # the list's order (환율 · 금리 · 증시 자금 first)
SECS = ['fx', 'rates', 'funds', 'energy', 'metals', 'agri']                 # the list's sections (증시 자금 = one group, two zones)
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
  heads: Object.fromEntries([...document.querySelectorAll('#world .kw-sec[data-g]')].map(s => {
    const ts = [...s.querySelectorAll('.kw-sh .kw-rg')].filter(t => !t.hidden && t.getBoundingClientRect().width > 0);
    return [s.dataset.g, ts.length ? { shown: true, text: ts[0].textContent.replace('색 범위 ', ''), tags: ts.map(t => t.textContent.replace('색 범위 ', '')),
      title: ts[0].title, titles: ts.map(t => t.title) } : null]; })),
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
    const z = zones && zones[it.zk]; out.n++;
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
    return {k: dict(key=k, gkey=it['gkey'], zk=it['zk'], ratio=it.get('ratio'), z=ZNUM[k]) for k, it in ITEMS.items() if not it.get('ref')}


def head_want(k):
    """the tags a section head carries under 자동: its zone's range; 증시 자금 also names 반대매매's"""
    return [ztxt(EXP['funds']), f"반대매매 {ztxt(EXP['forced'])}"] if k == 'funds' else [ztxt(EXP[k])]


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
        check('후속 ②: 반대매매 (금액 · 비중) its own zone in 증시 자금 — ±30% apart from 예탁금 · 신용융자 · 미수금 ±3%',
              z.get('forced', {}).get('name') == '반대매매' and z['forced'].get('group') == 'funds' and z.get('funds', {}).get('group') == 'funds'
              and z['forced']['value'] == EXP['forced']['value'] and z['funds']['value'] == EXP['funds']['value'] and z['funds']['value'] < z['forced']['value'],
              json.dumps({k: z.get(k) for k in ('funds', 'forced')}, ensure_ascii=False))
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
        bad = [f"{k} {heads.get(k)} != {head_want(k)}" for k in SECS if not heads.get(k) or heads[k]['tags'] != head_want(k)]
        check('group heads: "±0.2%" · 금리 "±7bp" · 증시 자금 "±3%" + "반대매매 ±30%" beside the name', not bad,
              '; '.join(bad) or ', '.join(f"{k} {' '.join(heads[k]['tags'])}" for k in SECS))
        check('head tag title says the rule (자동 · 95%; 반대매매 names its rows)', all('95%' in t for k in SECS for t in heads[k]['titles']) and 'bp' in heads['rates']['title']
              and '반대매매' in heads['funds']['titles'][1], ' | '.join(heads['funds']['titles']))
        lg = st['legend']
        check('legend: "자동 · 구역마다", no ±N ticks, 구역 범위 row in list order, bar = 구역 범위',
              lg['rauto'] == '자동 · 구역마다' and not lg['ticks'] and lg['zones'] == [f"{EXP[k]['name']} {ztxt(EXP[k])}" for k in ORDER] and '끝이 구역 범위' in lg['text'],
              lg['text'][:240])
        tag = pg.evaluate("() => getComputedStyle(document.querySelector('#world .kw-sh .kw-rg')).boxShadow + ' | ' + getComputedStyle(document.querySelector('#world .kw-sh .kw-rg')).color")
        acc = pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#ffb547'")
        check('tags look like the "자동 ±N%" tag (thin ring), no amber', 'inset' in tag and '255, 181, 71' not in tag, f'{tag} (accent {acc})')
        key = st['key']
        check('template 자동 key: "자동, 구역마다", title lists the zones (반대매매 too)', key and key['aria'] == '자동, 구역마다' and key['title'].startswith('구역마다') and '환율 ±' in key['title']
              and f"반대매매 {ztxt(EXP['forced'])}" in key['title'], json.dumps(key, ensure_ascii=False))
        # 많이 오른·내린 swatches, detail sheet swatch, the image's tiles
        rk = pg.evaluate("""([items, zones]) => { """ + NORM + """ const bad = []; let n = 0;
          for (const b of document.querySelectorAll('#world .kw-row[data-k]')) { const it = items[b.dataset.k]; if (!it) continue; n++; const z = zones[it.zk];
            const want = norm(KH.colorOf(it.z, { scope: 'world', range: z.value })), got = getComputedStyle(b.querySelector('.kw-sw')).backgroundColor;
            if (got !== want) bad.push(`${it.key} ${got} != ${want}`); } return { n, bad }; }""", [items_payload(), z])
        check('많이 오른·내린 swatches = their group\'s range', rk['n'] >= 6 and not rk['bad'], '; '.join(rk['bad'][:3]) or f"{rk['n']} swatches")
        lay = pg.evaluate("""([items, zones]) => { """ + NORM + """ const bad = []; let n = 0;
          for (const x of KHWorld.layout()) { if (x.kind !== 'tile') continue; const it = items[x.code]; if (!it) continue; n++; const z = zones[it.zk];
            if (norm(x.color) !== norm(KH.colorOf(it.z, { scope: 'world', range: z.value }))) bad.push(x.code); } return { n, bad }; }""", [items_payload(), z])
        check('KHWorld.layout() (이미지 저장) tiles = their group\'s range', lay['n'] >= len(items_payload()) - 1 and not lay['bad'], f"{lay['n']} tiles, bad {lay['bad'][:4]}")
        for k in ('FX_USDKRW', 'US10YT', 'fd:forced'):
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
              cm and cm['tags'] == [f"{EXP[k]['name']} {ztxt(EXP[k])}" for k in ('energy', 'metals', 'agri')] and all(st2['heads'][k]['tags'] == head_want(k) for k in ('fx', 'rates', 'funds')),
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
        # a picked ±5 (후속 ①): one range for the tab, except 금리 — their own bp 자동 range ("±Nbp 자동" in the head and the legend)
        press_range(pg, '5')
        ms = pg.evaluate(STATE_JS)
        visible = {k: v['tags'] for k, v in ms['heads'].items() if v}
        mz = ms['zones'] or {}
        rv = mz.get('rates', {}).get('value')
        c5 = pg.evaluate(CHIPS_JS, [items_payload(), mz])
        rtag = f"±{rtxt(rv)}bp 자동" if rv else None
        check('picked ±5: only 금리 keep a zone (bp, the same hysteresis key as under 자동), rangeInfo().zones null, 자동 key named as before',
              list(mz) == ['rates'] and mz['rates']['unit'] == 'bp' and rv in BP_STEPS and rv == h['now']['rates'] and ms['ri']['zones'] is None
              and ms['key']['aria'].startswith('자동, 지금 ±'), f"{mz} · {ms['ri']['zones']} · {ms['key']}")
        check('picked ±5: the 금리 head alone carries "±Nbp 자동", title says why (칩 글자 bp)', visible == {'rates': [rtag]} and 'bp' in ms['heads']['rates']['title']
              and '고른 범위와 따로' in ms['heads']['rates']['title'], f"{visible} · {ms['heads'].get('rates')}")
        check('picked ±5: legend "오늘 등락률 −5% · +5%" + 구역 범위 "금리 ±Nbp 자동", bar "끝이 ±5% · 금리 ±Nbp"',
              ms['legend']['rauto'] is None and ms['legend']['ticks'] == ['−5%', '+5%'] and '오늘 등락률' in ms['legend']['text']
              and ms['legend']['zones'] == [f"금리 {rtag}"] and f"끝이 ±5% · 금리 ±{rtxt(rv)}bp" in ms['legend']['text'], ms['legend']['text'][:200])
        check('picked ±5: 금리 chips and bars on their bp range, every other chip on ±5 % by its %', c5['n'] == len(items_payload()) and not c5['bad'] and not c5['bar'],
              '; '.join((c5['bad'] + c5['bar'])[:3]) or f"{c5['n']} rows")
        old_rule = pg.evaluate("""k => ({ chip: getComputedStyle(document.querySelector(`#world .kw-lr[data-k="${k}"] .kw-pchip`)).backgroundColor })""", 'US10YT')
        old5 = pg.evaluate("r => { " + NORM + " return norm(KH.colorOf(r, 'world')); }", ITEMS['US10YT']['ratio'])
        check('picked ±5: 미 국채 10년 (+6.9bp) no longer the pale % colour of the old rule (+1.35 % on ±5)', old_rule['chip'] != old5, f"chip {old_rule['chip']} · old rule {old5}")
        pg.click('#world .kw-lr[data-k="US10YT"]')
        pg.wait_for_selector('.kw-sheet:not([hidden]) .kw-sw', timeout=8000)
        pg.wait_for_timeout(250)
        sw5 = pg.evaluate("""() => ({ sheet: getComputedStyle(document.querySelector('.kw-sheet .kw-sw')).backgroundColor,
          row: getComputedStyle(document.querySelector('#world .kw-lr[data-k="US10YT"] .kw-pchip')).backgroundColor })""")
        check('picked ±5: the 금리 sheet swatch = its row (bp zone)', sw5['sheet'] == sw5['row'], json.dumps(sw5))
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(SHOTS / 'gr_1280_pick5.png'), full_page=True)
        press_range(pg, 'auto')
        back = pg.evaluate(STATE_JS)
        check('back to 자동: zones return', back['zones'] is not None and len(back['zones']) == len(ORDER) and back['legend']['rauto'] == '자동 · 구역마다', str(back['legend']['rauto']))
        # 해외 · 국내 tabs
        pg.click('.tabs button[data-mkt="WORLD"]')
        pg.wait_for_timeout(1500)
        ws = pg.evaluate(STATE_JS)
        wvis = [k for k, v in ws['heads'].items() if v and v['shown']]
        wch = pg.evaluate("""rs => { """ + NORM + """ let n = 0, bad = []; for (const r of document.querySelectorAll('#world .kw-lr')) { const v = rs[r.dataset.k];
          if (r.classList.contains('ref') || v == null) continue; n++; if (getComputedStyle(r.querySelector('.kw-pchip')).backgroundColor !== norm(KH.colorOf(v, 'world'))) bad.push(r.dataset.k); } return { n, bad }; }""",
                          {it['key']: it['ratio'] for g in FIX['world_index']['groups'] for it in g['items'] if it.get('ratio') is not None and not it.get('ref')})
        check('해외 tab: one range for the tab as before ("자동 ±N%", ±N ticks, no zone tags · legend row, rangeInfo().zones null)', ws['ri']['zones'] is None and not wvis
              and (ws['legend']['rauto'] or '').startswith('자동 ±') and len(ws['legend']['ticks']) == 2 and not ws['legend']['zones'] and wch['n'] >= 20 and not wch['bad'],
              f"{ws['legend']['rauto']} {ws['legend']['ticks']} {wvis} chips {wch}")
        pg.click('.tabs button[data-mkt="Q"]')
        pg.wait_for_timeout(1500)
        ks = pg.evaluate("() => ({ ri: KH.rangeInfo(), aria: document.querySelector('#rangeseg button[data-v=auto]').getAttribute('aria-label') })")
        check('국내 tab: no zones in the template, 자동 key as before', ks['ri']['zones'] is None and ks['aria'].startswith('자동, 지금 ±'), json.dumps(ks, ensure_ascii=False)[:200])
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


TK = {'USDKRW': ('FX_USDKRW', 'fx'), 'WTI': ('CLcv1', 'energy'), 'GOLD': ('GCcv1', 'metals')}      # ticker key → 지표 row, its zone
TK_TEXT_JS = """() => Object.fromEntries([...document.querySelectorAll('#strip .xs-list:first-child .xs-item[data-k]')].filter(i => /^(USDKRW|WTI|GOLD)$/.test(i.dataset.k))
  .map(i => { const r = i.querySelector('.xs-r'); return [i.dataset.k, r ? { color: getComputedStyle(r).color, text: r.textContent, cls: r.className } : null]; }))"""
SM_JS = """() => { const out = {}; for (const nv of document.querySelectorAll('.sm-sec.pal-w .sm-nv')) { const nm = nv.querySelector('.sm-nm'), n = nv.querySelector('.sm-n');
  if (nm && n) out[nm.textContent.trim()] = { color: getComputedStyle(n).color, text: n.textContent }; } return out; }"""
PAL_JS = "() => { " + NORM + " const p = KH.palette('world'); return { up: norm(p.upText), dn: norm(p.dnText) }; }"


def sheet_from_ticker(pg, k):
    pg.evaluate("k => document.querySelector(`#strip .xs-item[data-k=\"${k}\"]`).click()", k)
    pg.wait_for_selector('.kw-sheet:not([hidden]) .kw-dh .kw-sw', timeout=10000)
    pg.wait_for_timeout(400)
    out = pg.evaluate("() => ({ key: document.querySelector('.kw-sheet .kw-dh').dataset.k, sw: getComputedStyle(document.querySelector('.kw-sheet .kw-dh .kw-sw')).backgroundColor })")
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(700)
    return out


def chip_of(pg, key):
    return pg.evaluate("k => getComputedStyle(document.querySelector(`#world .kw-lr[data-k=\"${k}\"] .kw-pchip`)).backgroundColor", key)


def ticker_pass(b):
    """후속 ③: the same 지표 row is the same colour wherever it shows — a sheet the ticker opens on 국내 · 해외 tabs, before the 지표 tab
    was ever opened, under 자동 and a picked range, = the 지표 tab's chip; the ticker's and the summary card's own numbers carry
    direction colours (the 해외 · 지표 palette's up / down text), which no range reaches"""
    ctx = b.new_context(viewport={'width': 1280, 'height': 800}, service_workers='block')
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__grPre')) return; sessionStorage.setItem('__grPre', '1'); localStorage.setItem('khm.theme', '\"base\"'); })();")
    pg = ctx.new_page()
    ERR.attach(pg, 'ticker 1280')
    try:
        pg.goto(LIVE + '?summary_phase=pre#kospi')
        pg.wait_for_selector('#strip .xs-item[data-k="WTI"] .xs-r', timeout=15000)
        pg.wait_for_timeout(1200)
        z0 = pg.evaluate('() => KHWorld.zones()')
        check('국내 tab before any 지표 data: KHWorld.zones() null', z0 is None, str(z0))
        sw = {}
        for k in TK:
            sw[k] = sheet_from_ticker(pg, k)
        zk = pg.evaluate('() => KHWorld.zones()') or {}
        want = {k: (EXP[k]['value'], EXP[k]['unit']) for k in ('fx', 'rates', 'energy', 'metals', 'agri')}
        check('ticker sheet on the 국내 tab: zones measured without the 지표 tab = the expected zones (same rule, same keys)',
              {k: (zk[k]['value'], zk[k]['unit']) for k in want if k in zk} == want and all(abs(zk[k]['p95'] - EXP[k]['p95']) < 1e-6 for k in want),
              f"{ {k: (v['value'], v['unit']) for k, v in zk.items()} } · want {want}")
        exp_sw = pg.evaluate("""([tk, items, exp]) => { """ + NORM + """ const o = {};
          for (const [k, [wk, z]] of Object.entries(tk)) { const r = items[wk].ratio; o[k] = { zone: norm(KH.colorOf(r, { scope: 'world', range: exp[z].value })), tab: norm(KH.colorOf(r, 'world')) }; } return o; }""",
                             [TK, items_payload(), EXP])
        bad = [f"{k} {sw[k]} != {exp_sw[k]['zone']}" for k in TK if sw[k]['key'] != TK[k][0] or sw[k]['sw'] != exp_sw[k]['zone']]
        check('ticker sheets on the 국내 tab (원/달러 · WTI · 금): swatch on the row\'s zone range, not the 국내 tab\'s', not bad and sw['USDKRW']['sw'] != exp_sw['USDKRW']['tab'],
              '; '.join(bad) or f"원/달러 {sw['USDKRW']['sw']} (국내 tab range would be {exp_sw['USDKRW']['tab']})")
        pal = pg.evaluate(PAL_JS)
        tk0 = pg.evaluate(TK_TEXT_JS)
        tbad = [f"{k} {v}" for k, v in tk0.items() if not v or v['color'] != (pal['up'] if v['text'].startswith('+') else pal['dn'] if v['text'].startswith('−') else v['color'])]
        check('ticker 원/달러 · WTI · 금: the 해외 · 지표 palette\'s direction colour (no range in it)', len(tk0) == 3 and not tbad, json.dumps(tk0, ensure_ascii=False)[:240])
        pg.evaluate("() => window.KHSummary && KHSummary.open()")
        try:
            pg.wait_for_selector('.sm-sec.pal-w .sm-n', timeout=8000)
        except Exception:
            pass
        pg.wait_for_timeout(700)
        sm0 = pg.evaluate(SM_JS)
        sign = {'원/달러': ITEMS['FX_USDKRW']['ratio'], '미 국채 10년': ZNUM['US10YT'], '국고채 3년': ZNUM['KR3YT'], 'WTI': ITEMS['CLcv1']['ratio']}
        sbad = [f"{n} {sm0.get(n)}" for n, v in sign.items() if not sm0.get(n) or sm0[n]['color'] != (pal['up'] if v > 0 else pal['dn'])]
        check('summary card 원/달러 · 미 국채 10년 · 국고채 3년 · WTI: the direction colour of the 지표 chip\'s own number (금리 bp)', not sbad, '; '.join(sbad) or json.dumps(sm0, ensure_ascii=False)[:200])
        pg.evaluate("() => window.KHSummary && KHSummary.close()")
        pg.wait_for_timeout(500)
        pg.evaluate('() => scrollTo(0, 0)')
        # the 해외 tab draws its own data (index): a ticker sheet of a 지표 row still takes the 지표 zone
        pg.click('.tabs button[data-mkt="WORLD"]')
        pg.wait_for_timeout(1500)
        swW = sheet_from_ticker(pg, 'USDKRW')
        check('ticker sheet on the 해외 tab: 원/달러 = the same swatch', swW['sw'] == sw['USDKRW']['sw'], f"{swW} vs {sw['USDKRW']}")
        # the 지표 tab: the chips are the swatches, the zones the ones measured off the tab
        pg.click('.tabs button[data-mkt="CMDTY"]')
        pg.wait_for_selector('#world .kw-lr[data-k="FX_USDKRW"]', timeout=10000)
        pg.wait_for_timeout(1200)
        chips = {k: chip_of(pg, TK[k][0]) for k in TK}
        zc = pg.evaluate('() => KHWorld.zones()') or {}
        check('지표 tab: 원/달러 · WTI · 금 chips = the swatches the ticker showed on the 국내 tab, zones the same values',
              all(chips[k] == sw[k]['sw'] for k in TK) and all(zc.get(k, {}).get('value') == zk[k]['value'] for k in want),
              f"chips {chips} · swatches { {k: v['sw'] for k, v in sw.items()} }")
        # a picked ±5 on the 해외 · 지표 side: the ticker's sheet on the 국내 tab colours 지표 rows on ±5 like the 지표 tab does
        press_range(pg, '5')
        chips5 = {k: chip_of(pg, TK[k][0]) for k in TK}
        pg.click('.tabs button[data-mkt="K"]')
        pg.wait_for_timeout(1500)
        sw5 = {k: sheet_from_ticker(pg, k)['sw'] for k in TK}
        exp5 = pg.evaluate("""([tk, items]) => { """ + NORM + """ const o = {}; for (const [k, [wk]] of Object.entries(tk)) o[k] = norm(KH.colorOf(items[wk].ratio, { scope: 'world', range: 5 })); return o; }""",
                           [TK, items_payload()])
        check('picked ±5 (해외 · 지표 side): ticker sheets on the 국내 tab on ±5 = the 지표 tab\'s chips', sw5 == exp5 == chips5, f"sheets {sw5} · ±5 {exp5} · chips {chips5}")
        tk5 = pg.evaluate(TK_TEXT_JS)
        pg.evaluate("() => window.KHSummary && KHSummary.open()")
        pg.wait_for_timeout(1200)
        sm5 = pg.evaluate(SM_JS)
        check('ticker · summary numbers do not move with the range (자동 → ±5): same colours', tk5 == tk0 and all(sm5.get(n) == sm0.get(n) for n in sign),
              f"ticker {tk5 == tk0} · summary { {n: sm5.get(n) == sm0.get(n) for n in sign} }")
        pg.evaluate("() => window.KHSummary && KHSummary.close()")
        pg.wait_for_timeout(400)
        pg.click('.tabs button[data-mkt="CMDTY"]')
        pg.wait_for_timeout(1200)
        press_range(pg, 'auto')
    finally:
        ctx.close()


def layout_pass(b):
    for theme in THEMES:
        for w, hgt in ((360, 740), (1280, 800)):
            ctx, pg = open_page(b, w, hgt, theme=theme, tag=f'{theme} {w}')
            try:
                o = pg.evaluate(OVER_JS)
                check(f'{theme} {w}: nothing past the viewport, tags not cut, head notes whole', o['n'] == 0 and o['doc'] <= 0 and o['tags'] >= 7 and not o['cut'] and not o['notes'],
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
            # a picked ±5 (후속 ①): the 금리 head alone carries "±Nbp 자동"
            ctx, pg = open_page(b, w, hgt, theme=theme, pre={'khm.rangeW': 5}, tag=f'{theme} {w} ±5')
            try:
                o = pg.evaluate(OVER_JS)
                check(f'{theme} {w} picked ±5: nothing past the viewport, the "±Nbp 자동" tag whole, head notes whole', o['n'] == 0 and o['doc'] <= 0 and o['tags'] == 1 and not o['cut'] and not o['notes'],
                      f"over {o['over']} doc {o['doc']} tags {o['tags']} cut {o['cut']} notes {o['notes']}")
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
                ticker_pass(b)
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
