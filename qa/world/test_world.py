#!/usr/bin/env python3
"""QA for src/world (해외 · 원자재 tabs) on the built pages.

  python3 scripts/build_page.py && python3 qa/world/test_world.py [--real]

Starts qa/world/mock_api.py on :8803 (serves web/ + /api/world*), injects qa/world/shim.js for the §3-4 template hooks
until they are merged, and writes screenshots to qa/shots/world/. --real also runs a smoke pass against the local Worker
(NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8803/ PORT=8802 node worker/dev/serve.mjs, started and stopped here);
--real-cdn makes that pass fetch the world atlas from jsDelivr itself (SRI checked by the browser) instead of the fixture.
Exit code 1 if any check fails.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHOTS = ROOT / 'qa/shots/world'
SHOTS.mkdir(parents=True, exist_ok=True)
import os
PORT, REAL_PORT = int(os.environ.get('WORLD_QA_PORT', 8803)), 8802      # WORLD_QA_PORT: another worktree's mock may already own 8803
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SHIM = (HERE / 'shim.js').read_text(encoding='utf-8')
FIX = {k: json.loads((HERE / f'fixtures/world_{k}.json').read_text(encoding='utf-8')) for k in ('index', 'commodity')}
COUNT = {k: sum(len(g['items']) for g in v['groups']) for k, v in FIX.items()}
ATLAS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json'
ATLAS = (HERE / 'fixtures/countries-110m.json').read_bytes()          # world-atlas 2.0.2 (ISC), Natural Earth data
WIDTHS = {360: 740, 390: 844, 768: 1024, 1280: 800, 1920: 1080}
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def api(path, base=LIVE):
    with NOPROXY.open(base.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


class Errors:
    def __init__(self):
        self.items, self.expected, self.expect_net = [], [], False

    def on_console(self, m):
        if m.type != 'error':
            return
        if self.expect_net and (m.text.startswith('Failed to load resource') or 'integrity' in m.text):
            self.expected.append(m.text)
        else:
            self.items.append(m.text[:160])

    def attach(self, page):
        page.on('console', self.on_console)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


ERR = Errors()


def route_atlas(ctx, atlas):
    """atlas: 'local' serves the fixture (same bytes as jsDelivr, so SRI passes), 'block' fails the request,
    'bad' sends altered bytes (SRI must reject them), 'real' leaves the network alone."""
    if atlas == 'real':
        return
    ctx.unroute(ATLAS_URL)
    hdr = {'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*'}
    if atlas == 'block':
        ctx.route(ATLAS_URL, lambda r: r.abort())
    elif atlas == 'bad':
        ctx.route(ATLAS_URL, lambda r: r.fulfill(status=200, body=ATLAS.replace(b'"Korea"', b'"Corea"', 1) + b' ', headers=hdr))
    else:
        ctx.route(ATLAS_URL, lambda r: r.fulfill(status=200, body=ATLAS, headers=hdr))


def open_page(browser, url, width=1440, height=900, mobile=False, reduced=False, clock=False, view=None, sort=None, block_storage=False, atlas='local'):
    """view / sort: preset localStorage khm.worldView / khm.worldSort before the page boots (None = leave it empty)."""
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    ctx.add_init_script(SHIM)
    route_atlas(ctx, atlas)
    if block_storage:
        ctx.add_init_script("Object.defineProperty(window, 'localStorage', {configurable: true, get() { throw new DOMException('blocked', 'SecurityError'); }});")
    pre = {k: v for k, v in (('khm.worldView', view), ('khm.worldSort', sort)) if v}
    if pre:
        ctx.add_init_script("(() => { if (sessionStorage.getItem('__kwPre')) return; sessionStorage.setItem('__kwPre', '1'); "
                            + ''.join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in pre.items()) + "})();")
    page = ctx.new_page()
    if clock:
        page.clock.install(**({} if clock is True else {'time': clock / 1000}))   # clock=<ms>: start the page at that instant (Python takes seconds)
    ERR.attach(page)
    page.goto(url)
    return ctx, page


GEO_SEL = '#world .kw-geo:not([hidden]) .kw-gsvg'


def wait_world(page, sel='#world .kw-tile', timeout=8000):
    page.wait_for_selector(sel, timeout=timeout)
    page.wait_for_timeout(350)


# ── page-side probes ──
LABELS_JS = r"""
() => {
  const out = []; let labs = 0, chips = 0, tiles = 0;
  const inside = (r, tr, tol) => r.left >= tr.left - tol && r.right <= tr.right + tol && r.top >= tr.top - tol && r.bottom <= tr.bottom + tol;
  const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
  for (const t of document.querySelectorAll('#world .kw-tile')) {
    tiles++;
    const tr = t.getBoundingClientRect();
    const lab = t.querySelector('.kw-lab'), chip = t.querySelector('.kw-chip');
    const rects = [];
    if (lab && !lab.hidden) {
      labs++;
      const w = document.createTreeWalker(lab, NodeFilter.SHOW_TEXT); let tn;
      while ((tn = w.nextNode())) {
        if (!tn.textContent.trim() || tn.parentElement.closest('[hidden]')) continue;
        const rg = document.createRange(); rg.selectNodeContents(tn);
        for (const rr of rg.getClientRects()) {
          rects.push(rr);
          if (!inside(rr, tr, 1.5)) out.push(`${t.dataset.k} '${tn.textContent}' [${rr.left.toFixed(0)},${rr.top.toFixed(0)},${rr.right.toFixed(0)},${rr.bottom.toFixed(0)}] tile [${tr.left.toFixed(0)},${tr.top.toFixed(0)},${tr.right.toFixed(0)},${tr.bottom.toFixed(0)}]`);
        }
      }
      for (const c of lab.children) if (!c.hidden && c.scrollWidth > c.clientWidth + 1) out.push(`${t.dataset.k} ${c.className} scrollW ${c.scrollWidth}>${c.clientWidth}`);
    }
    if (chip && !chip.hidden) {
      chips++;
      const cr = chip.getBoundingClientRect();
      if (!inside(cr, tr, 0.5)) out.push(`${t.dataset.k} chip outside`);
      for (const rr of rects) if (hit(cr, rr)) { out.push(`${t.dataset.k} chip overlaps '${chip.textContent}'`); break; }
    }
  }
  for (const g of document.querySelectorAll('#world .kw-gh:not([hidden])')) {
    const gr = g.getBoundingClientRect();
    for (const c of g.children) { if (!c.textContent) continue; const r = c.getBoundingClientRect(); if (r.right > gr.right + 1 || r.left < gr.left - 1) out.push(`header ${g.textContent} child outside`); }
    const t = g.children[0]; if (t.scrollWidth > t.clientWidth + 1) out.push(`header name truncated: ${t.textContent}`);
  }
  return { tiles, labs, chips, out };
}"""

COLORS_JS = r"""
(fix) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const bad = []; let n = 0;
  const items = new Map(); for (const g of fix.groups) for (const it of g.items) items.set(it.key, it);
  for (const t of document.querySelectorAll('#world .kw-tile')) {
    const it = items.get(t.dataset.k); if (!it) { bad.push('unknown ' + t.dataset.k); continue; }
    n++;
    const want = it.ref ? norm('#30333b') : norm(KH.colorOf(it.ratio));
    const got = norm(t.style.backgroundColor);
    if (want !== got) bad.push(`${it.key} ${got} != ${want}`);
    if (!!it.ref !== t.classList.contains('ref')) bad.push(`${it.key} ref class`);
  }
  return { n, bad };
}"""

TARGETS_JS = r"""
() => {
  const small = [];
  for (const el of document.querySelectorAll('#world .kw-tile, #world .kw-row, #world .kw-lr, #world .kw-seg button, #world .kw-retry, .kw-sheet button, .kw-sheet a')) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (r.height < 40 || (r.width < 40)) small.push(`${el.className || el.tagName} ${el.dataset.k || el.textContent.trim().slice(0, 12)} ${r.width.toFixed(0)}x${r.height.toFixed(0)}`);
  }
  return small;
}"""


# ── list view (default, AGENTS §3-4 "목록이 기본") ──
LIST_JS = r"""
(fix) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const items = new Map(); for (const g of fix.groups) for (const it of g.items) items.set(it.key, Object.assign({ group: g.name }, it));
  const sgn = v => v > 0 ? '+' : v < 0 ? '−' : '';
  const pct = v => sgn(v) + Math.abs(v).toFixed(2) + '%';
  const num = t => +t.replace(/[,+]/g, '').replace('−', '-');
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const lum = c => { const m = c.match(/[\d.]+/g).map(Number).slice(0, 3).map(lin); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bad = { value: [], pct: [], chg: [], color: [], ink: [], ref: [], clip: [], nums: [] };
  let n = 0, minInk = 99;
  const vw = document.documentElement.clientWidth;
  for (const r of document.querySelectorAll('#world .kw-lr')) {
    const it = items.get(r.dataset.k); if (!it) { bad.value.push('unknown ' + r.dataset.k); continue; }
    n++;
    const lv = r.querySelector('.kw-lv'), lc = r.querySelector('.kw-lc'), chip = r.querySelector('.kw-pchip');
    if (Math.abs(num(lv.textContent) - it.value) > 1e-6 * Math.max(1, Math.abs(it.value))) bad.value.push(`${it.key} ${lv.textContent} != ${it.value}`);
    if (chip.textContent !== pct(it.ratio)) bad.pct.push(`${it.key} ${chip.textContent} != ${pct(it.ratio)}`);
    if (Math.abs(num(lc.textContent) - it.change) > 1e-6 * Math.max(1, Math.abs(it.change))) bad.chg.push(`${it.key} ${lc.textContent} != ${it.change}`);
    for (const el of [lv, lc, chip]) if (!/tabular-nums/.test(getComputedStyle(el).fontVariantNumeric) || getComputedStyle(el).textAlign === 'left' && el !== lv) bad.nums.push(`${it.key} ${el.className}`);
    const bg = getComputedStyle(chip).backgroundColor, fg = getComputedStyle(chip).color;
    if (it.ref) {
      const tagEl = r.querySelector('.kw-ln .sub.tag');
      if (!chip.classList.contains('ref') || bg !== 'rgba(0, 0, 0, 0)' || !tagEl || tagEl.textContent !== '참고' || /\b(up|dn)\b/.test(lc.className)) bad.ref.push(`${it.key} ref chip ${bg}, tag ${tagEl && tagEl.textContent}, chg ${lc.className}`);
      if (getComputedStyle(r.querySelector('.kw-lb i')).backgroundColor !== 'rgb(91, 95, 105)') bad.ref.push(`${it.key} bar not grey`);
    } else {
      if (bg !== norm(KH.colorOf(it.ratio))) bad.color.push(`${it.key} ${bg} != ${norm(KH.colorOf(it.ratio))}`);
      const cr = contrast(bg, fg); minInk = Math.min(minInk, cr); if (cr < 4.5) bad.ink.push(`${it.key} ${cr.toFixed(2)}`);
      if (getComputedStyle(r.querySelector('.kw-lb i')).backgroundColor !== bg) bad.color.push(`${it.key} bar colour`);
    }
    const rr = r.getBoundingClientRect();
    for (const el of [chip, lv, lc]) {
      const b = el.getBoundingClientRect();
      if (el.scrollWidth > el.clientWidth + 1 || b.right > rr.right + 0.5 || b.left < rr.left - 0.5 || b.right > vw || b.width < 8) bad.clip.push(`${it.key} ${el.className} ${b.left.toFixed(0)}-${b.right.toFixed(0)} row ${rr.left.toFixed(0)}-${rr.right.toFixed(0)}`);
    }
  }
  return { n, bad, minInk };
}"""

ALIGN_JS = r"""
() => {
  const out = [];
  const cols = [...document.querySelectorAll('#world .kw-col')];
  for (const col of cols) for (const sel of ['.kw-lv', '.kw-lc', '.kw-pchip', '.kw-lb']) {
    const rs = [...col.querySelectorAll('.kw-lr ' + sel)].map(e => e.getBoundingClientRect().right);
    if (rs.length && Math.max(...rs) - Math.min(...rs) > 1) out.push(`${sel} right ${Math.min(...rs).toFixed(1)}..${Math.max(...rs).toFixed(1)}`);
  }
  const offs = cols.map(c => { const r = c.querySelector('.kw-lr .kw-lv'); return r ? Math.round(c.getBoundingClientRect().right - r.getBoundingClientRect().right) : null; });
  if (new Set(offs).size > 1) out.push('value column offset differs per column: ' + offs);
  const hs = cols.map(c => c.getBoundingClientRect().height);
  return { out, cols: cols.length, heights: hs.map(Math.round), rowH: Math.min(...[...document.querySelectorAll('#world .kw-lr')].map(r => r.getBoundingClientRect().height)) };
}"""

SECS_JS = r"""
(fix) => {
  const out = [];
  const sgn = v => v > 0 ? '+' : v < 0 ? '−' : '';
  const pct = v => sgn(v) + Math.abs(v).toFixed(2) + '%';
  const secs = new Map([...document.querySelectorAll('#world .kw-sec')].map(s => [s.querySelector('.kw-sh .t').textContent, s]));
  // 지역순 on the index tab: 미국 선물 and 참고 (VIX) are folded into 미국 — cash first, then futures, then VIX. The header average
  // and the 장중/마감 summary of 미국 use the cash indices only (`cash`).
  let groups = fix.groups.map(g => ({ ...g, cash: g.items }));
  const us = groups.find(g => g.key === 'us');
  if (us && fix.groups.some(g => g.key === 'usf')) {
    us.items = us.items.concat(groups.filter(g => g.key === 'usf').flatMap(g => g.items), groups.filter(g => g.key === 'ref').flatMap(g => g.items));
    groups = groups.filter(g => g.key !== 'usf' && g.key !== 'ref');
  }
  for (const g of groups) {
    const s = secs.get(g.name);
    if (!s) { out.push('missing section ' + g.name); continue; }
    const keys = [...s.querySelectorAll('.kw-lr')].map(r => r.dataset.k).join(',');
    if (keys !== g.items.map(it => it.key).join(',')) out.push(`${g.name} rows ${keys}`);
    const vals = g.cash.filter(it => !it.ref).map(it => it.ratio);
    const a = s.querySelector('.kw-sh .a b');
    if (vals.length) { const want = pct(vals.reduce((x, y) => x + y, 0) / vals.length); if (!a || a.textContent !== want) out.push(`${g.name} avg ${a && a.textContent} != ${want}`); }
    const st = s.querySelector('.kw-sh .s').textContent, open = g.cash.filter(it => it.status === 'OPEN').length;
    if (!(open === 0 ? st === '마감' : open === g.cash.length ? st.startsWith('장중') : st === `장중 ${open} · 마감 ${g.cash.length - open}`)) out.push(`${g.name} state '${st}'`);
    if (g.key === 'us' && fix.groups.some(x => x.key === 'usf')) {
      const tags = [...s.querySelectorAll('.kw-lr')].map(r => [r.dataset.k, (r.querySelector('.kw-ln .sub') || {}).textContent || '']);
      const fut = tags.filter(t => /cv1$/.test(t[0])), vix = tags[tags.length - 1];
      if (!fut.length || fut.some(t => t[1] !== '선물')) out.push('미국 futures lack the 선물 tag: ' + JSON.stringify(fut));
      if (vix[0] !== 'VIX' || vix[1] !== '참고' || !s.querySelector('.kw-lr[data-k="VIX"].ref')) out.push('VIX is not the last, grey 참고 row of 미국');
      if (s.querySelector('.kw-sh .a small').textContent !== '지수 평균') out.push('미국 header should say 지수 평균 (cash only)');
    }
  }
  if (secs.size !== groups.length) out.push(`sections ${secs.size} != ${groups.length}`);
  return out;
}"""


def wait_list(page, timeout=8000):
    page.wait_for_selector('#world .kw-lr', timeout=timeout)
    page.wait_for_timeout(300)


def list_pass(browser, kind, width, height):
    mobile = width < 700
    hsh = '#world' if kind == 'index' else '#cmdty'
    ctx, page = open_page(browser, LIVE + hsh, width, height, mobile)
    try:
        wait_list(page)
        tag = f'list {kind} {width}'
        st = page.evaluate("""({ n: document.querySelectorAll('#world .kw-lr').length, tiles: document.querySelectorAll('#world .kw-tile').length, view: KHWorld.view(),
            pressed: document.querySelector('#world .kw-seg[data-kw=view] button[aria-pressed=true]').textContent, mapHidden: document.querySelector('#world .kw-map').hidden })""")
        check(f'{tag}: list is the default view, one row per item', st['n'] == COUNT[kind] and st['view'] == 'list' and st['pressed'] == '목록' and st['tiles'] == 0 and st['mapHidden'], str(st))
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f'{tag}: no horizontal overflow', ov <= 0, f'{ov}px')
        r = page.evaluate(LIST_JS, FIX[kind])
        b = r['bad']
        check(f'{tag}: value · change · % = API', r['n'] == COUNT[kind] and not (b['value'] or b['pct'] or b['chg']), '; '.join((b['value'] + b['pct'] + b['chg'])[:3]))
        check(f'{tag}: % chip + bar = KH.colorOf, chip text ≥ 4.5:1', not (b['color'] or b['ink']), '; '.join((b['color'] + b['ink'])[:3]) or f"min contrast {r['minInk']:.2f}")
        check(f'{tag}: VIX grey, "참고", not coloured', not b['ref'] if kind == 'index' else True, '; '.join(b['ref'][:2]))
        check(f'{tag}: % / value / change never clipped', not b['clip'], '; '.join(b['clip'][:3]))
        check(f'{tag}: numbers right-aligned, tabular-nums', not b['nums'], '; '.join(b['nums'][:3]))
        al = page.evaluate(ALIGN_JS)
        check(f'{tag}: columns line up across rows and sections', not al['out'], '; '.join(al['out'][:3]) or f"{al['cols']} col(s), heights {al['heights']}")
        if width >= 1280 and kind == 'index':
            hs = al['heights']
            check(f'{tag}: 2–3 balanced columns on desktop', al['cols'] >= 2 and (max(hs) - min(hs)) <= 0.22 * max(hs), str(hs))
        if mobile:
            check(f'{tag}: one column, rows ≥ 44px', al['cols'] == 1 and al['rowH'] >= 44, f"{al['cols']} col, row {al['rowH']:.0f}px")
            small = page.evaluate(TARGETS_JS)
            check(f'{tag}: tap targets ≥ 40px', not small, '; '.join(small[:4]))
        secs = page.evaluate(SECS_JS, FIX[kind])
        check(f'{tag}: sections = groups, Worker order, header average + state', not secs, '; '.join(secs[:3]))
        side = page.evaluate("""() => { const s = document.querySelector('#world .kw-side').getBoundingClientRect(), m = document.querySelector('#world .kw-list').getBoundingClientRect();
            return { right: s.left >= m.right - 1, below: s.top >= m.bottom - 1, rank: document.querySelectorAll('#world .kw-row').length, open: !!document.querySelector('#world .kw-open').textContent }; }""")
        check(f'{tag}: side cards unchanged, {"below" if width <= 980 else "right of"} the list', (side['below'] if width <= 980 else side['right']) and side['rank'] >= 5 and side['open'], str(side))
        page.screenshot(path=str(SHOTS / f'list_{kind}_{width}.png'), full_page=True)
    finally:
        ctx.close()


def toggle_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        wait_list(page)
        page.click('#world .kw-seg[data-kw=view] button[data-v=map]')
        wait_world(page, GEO_SEL)
        st = page.evaluate("""({ geo: !document.querySelector('#world .kw-geo').hidden, tiles: document.querySelectorAll('#world .kw-tile').length, list: document.querySelector('#world .kw-list').hidden,
            sort: document.querySelector('#world .kw-seg[data-kw=sort]').hidden, stored: localStorage.getItem('khm.worldView'),
            pressed: document.querySelector('#world .kw-seg[data-kw=view] button[aria-pressed=true]').textContent })""")
        check('toggle: 해외 지도 = the world map (no tiles), list and sort hidden, stored', st['geo'] and st['tiles'] == 0 and st['list'] and st['sort'] and st['stored'] == 'map' and st['pressed'] == '지도', str(st))
        page.reload()
        wait_world(page, GEO_SEL)
        check('toggle: 지도 remembered after reload', page.evaluate("KHWorld.view() === 'map' && !document.querySelector('#world .kw-geo').hidden"))
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_world(page, '#world .kw-tile[data-k="CLcv1"]')
        check('toggle: one choice for both tabs (원자재 opens in 지도 too)', page.evaluate("KHWorld.view() === 'map' && document.querySelectorAll('#world .kw-tile').length") == COUNT['commodity'])
        page.click('#world .kw-seg[data-kw=view] button[data-v=list]')
        wait_list(page)
        page.reload()
        wait_list(page)
        check('toggle: 목록 remembered after reload', page.evaluate("KHWorld.view() === 'list' && localStorage.getItem('khm.worldView') === 'list'") and page.evaluate("document.querySelectorAll('#world .kw-lr').length") == COUNT['commodity'])
    finally:
        ctx.close()
    n0 = len(ERR.items)
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, block_storage=True)
    try:
        wait_list(page)
        page.click('#world .kw-seg[data-kw=view] button[data-v=map]')
        wait_world(page, GEO_SEL)
        page.click('#world .kw-seg[data-kw=view] button[data-v=list]')
        wait_list(page)
        check('toggle: blocked localStorage → still works, no errors', page.evaluate("KHWorld.view()") == 'list' and len(ERR.items) == n0, '; '.join(ERR.items[n0:n0 + 2]))
    finally:
        ctx.close()


def sort_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900)
    try:
        wait_list(page)
        page.click('#world .kw-seg[data-kw=sort] button[data-v=pct]')
        page.wait_for_selector('#world .kw-list.flat')
        flat = [it for g in FIX['index']['groups'] for it in g['items']]
        order = sorted((it for it in flat if not it.get('ref')), key=lambda it: -it['ratio']) + [it for it in flat if it.get('ref')]
        got = page.evaluate("""[...document.querySelectorAll('#world .kw-lr')].map(r => ({ k: r.dataset.k, rk: r.querySelector('.rk').textContent, sub: r.querySelector('.kw-ln .sub').textContent }))""")
        grp = {it['key']: g['name'] for g in FIX['index']['groups'] for it in g['items']}
        ok_order = [x['k'] for x in got] == [it['key'] for it in order]
        ok_rank = all(x['rk'] == str(i + 1) for i, x in enumerate(got[:-1])) and got[-1]['rk'] == ''
        ok_sub = all(x['sub'] == grp[x['k']] for x in got[:-1])
        check('sort 등락률순: one ranked list by % (desc), VIX last', ok_order, ' '.join(x['k'] for x in got[:6]))
        check('sort 등락률순: rank numbers + group name as secondary text', ok_rank and ok_sub, str(got[:2]))
        check('sort 등락률순: stored', page.evaluate("localStorage.getItem('khm.worldSort')") == 'pct')
        r = page.evaluate(LIST_JS, FIX['index'])
        check('sort 등락률순: values / colours still right', not any(r['bad'].values()), str({k: v[:1] for k, v in r['bad'].items() if v}))
        page.screenshot(path=str(SHOTS / 'list_sorted_1440.png'), full_page=True)
        page.reload()
        wait_list(page)
        check('sort: 등락률순 remembered after reload', page.evaluate("document.querySelector('#world .kw-list').classList.contains('flat')"))
        page.click('#world .kw-seg[data-kw=sort] button[data-v=group]')
        page.wait_for_selector('#world .kw-list:not(.flat)')
        secs = page.evaluate(SECS_JS, FIX['index'])
        check('sort 지역순: back to the sections', not secs, '; '.join(secs[:2]))
        page.click('.tabs button[data-mkt="CMDTY"]')
        page.wait_for_selector('#world .kw-lr[data-k="CLcv1"]')
        check('sort label on 원자재 is 종류순', page.evaluate("document.querySelector('#world .kw-seg[data-kw=sort] button[data-v=group]').textContent") == '종류순')
    finally:
        ctx.close()


def list_keyboard_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900)
    try:
        wait_list(page)
        stops = page.evaluate("[...document.querySelectorAll('#world .kw-lr')].filter(r => r.tabIndex === 0).length")
        check('list keyboard: one tab stop (roving)', stops == 1, str(stops))
        page.focus('#world .kw-lr[tabindex="0"]')
        order = page.evaluate("[...document.querySelectorAll('#world .kw-lr')].map(r => r.dataset.k)")
        k0 = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowDown'); k1 = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowDown'); k2 = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowUp'); k3 = page.evaluate('document.activeElement.dataset.k')
        check('list keyboard: ↑/↓ move row by row', [k0, k1, k2, k3] == [order[0], order[1], order[2], order[1]], f'{k0}→{k1}→{k2}→{k3}')
        ring = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineColor, s.outlineWidth]; })()")
        check('list keyboard: visible amber focus ring', ring == ['solid', 'rgb(255, 181, 71)', '3px'], str(ring))
        page.keyboard.press('End'); ke = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('Home'); kh = page.evaluate('document.activeElement.dataset.k')
        check('list keyboard: Home / End', ke == order[-1] and kh == order[0], f'{kh} … {ke}')
        page.keyboard.press('ArrowRight')
        col = page.evaluate("[...document.querySelectorAll('#world .kw-col')].indexOf(document.activeElement.closest('.kw-col'))")
        page.keyboard.press('ArrowLeft')
        col2 = page.evaluate("[...document.querySelectorAll('#world .kw-col')].indexOf(document.activeElement.closest('.kw-col'))")
        check('list keyboard: ←/→ jump between columns', col == 1 and col2 == 0, f'{col}, {col2}')
        moved = page.evaluate("[...document.querySelectorAll('#world .kw-lr')].filter(r => r.tabIndex === 0).map(r => r.dataset.k)")
        check('list keyboard: tab stop follows focus', moved == [page.evaluate('document.activeElement.dataset.k')], str(moved))
        page.keyboard.press('ArrowDown'); page.keyboard.press('ArrowDown')
        tgt = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('Enter')
        page.wait_for_selector('.kw-sheet:not([hidden])', timeout=3000)
        info = page.evaluate("""() => ({ inSheet: document.querySelector('.kw-sheet').contains(document.activeElement), name: document.querySelector('#kw-dt').textContent,
            sel: document.querySelector('#world .kw-lr.sel')?.dataset.k, rowName: document.querySelector('#world .kw-lr.sel')?.title })""")
        check('list detail: Enter opens the sheet for that row, row marked', info['inSheet'] and info['sel'] == tgt and info['name'] == info['rowName'], str(info))
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        after = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, k: document.activeElement.dataset.k, row: document.activeElement.classList.contains('kw-lr'), sel: document.querySelectorAll('#world .kw-lr.sel').length })")
        check('list detail: Esc closes, focus back on the row', after['hidden'] and after['k'] == tgt and after['row'] and after['sel'] == 0, str(after))
        page.click('#world .kw-lr[data-k="GDAXI"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        check('list detail: click opens the right item', page.evaluate("document.querySelector('#kw-dt').textContent") == '독일 DAX')
        page.mouse.click(5, 400)
        page.wait_for_timeout(100)
        check('list detail: click outside closes (desktop)', page.evaluate("document.querySelector('.kw-sheet').hidden"))
        # image save in the list view: the tile map laid out off screen (extras draws it), not an empty picture
        lay = page.evaluate("KHWorld.layout()")
        tiles = [x for x in lay if x['kind'] == 'tile']
        lw = page.evaluate("document.querySelector('#world .kw-list').clientWidth")
        okb = all(0 <= t['x'] and t['x'] + t['w'] <= lw + 0.5 and t['y'] >= 0 for t in tiles)
        check('KHWorld.layout() in the list view: off-screen tile map for "이미지로 저장"', len(tiles) == COUNT['index'] and okb and any(t['sub'] for t in tiles), f'{len(tiles)} tiles, inBounds {okb}')
        btn = page.query_selector('#extras-tools button[data-x="image"]')
        if btn:
            with page.expect_download(timeout=8000) as dl:
                btn.click()
            name = dl.value.suggested_filename
            page.wait_for_timeout(150)
            toast = page.evaluate("document.querySelector('.xt-toast') ? document.querySelector('.xt-toast').textContent : ''")
            check('이미지로 저장 in the list view: a PNG, not "지도 탭에서만" or an empty image', name.endswith('.png') and '지도 탭에서만' not in toast, f'{name} · {toast}')
        else:
            check('이미지로 저장 button present', False)
    finally:
        ctx.close()


def refresh_pass(browser, reduced=False, sort=None):
    api('/__reset')
    tag = 'refresh' + (' (reduced motion)' if reduced else '') + (' 등락률순' if sort else '')
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900, clock=True, reduced=reduced, sort=sort)
    try:
        wait_list(page)
        page.evaluate("document.querySelectorAll('#world .kw-lr').forEach(r => r.__tag = 1)")
        page.focus('#world .kw-lr[tabindex="0"]')
        for _ in range(9):
            page.keyboard.press('ArrowDown')
        k = page.evaluate('document.activeElement.dataset.k')
        page.evaluate('scrollTo(0, 260)')
        page.wait_for_timeout(100)
        sy = page.evaluate('scrollY')
        before = page.evaluate("Object.fromEntries([...document.querySelectorAll('#world .kw-lr')].map(r => [r.dataset.k, r.querySelector('.kw-lv').textContent]))")
        api('/__mode?world=drift')
        page.clock.run_for(30500)
        page.wait_for_function("(b) => [...document.querySelectorAll('#world .kw-lr')].some(r => r.querySelector('.kw-lv').textContent !== b[r.dataset.k])", arg=before, timeout=5000)
        page.wait_for_timeout(50)
        st = page.evaluate("""() => ({ k: document.activeElement.dataset.k, tagged: !!document.activeElement.__tag, sy: scrollY,
            fresh: [...document.querySelectorAll('#world .kw-lr')].filter(r => !r.__tag).length,
            fl: [...document.querySelectorAll('#world .kw-fl')].filter(e => getComputedStyle(e).animationName !== 'none').length })""")
        last = api('/__last?kind=index')
        r = page.evaluate(LIST_JS, last)
        changed = sum(1 for kk, v in page.evaluate("Object.fromEntries([...document.querySelectorAll('#world .kw-lr')].map(r => [r.dataset.k, r.querySelector('.kw-lv').textContent]))").items() if before.get(kk) != v)
        check(f'{tag}: rows updated in place (same elements), values = new API answer', st['fresh'] == 0 and changed > 0 and not (r['bad']['value'] or r['bad']['pct'] or r['bad']['color']), f"{changed} changed; " + '; '.join((r['bad']['value'] + r['bad']['pct'])[:2]))
        check(f'{tag}: focus and scroll kept', st['k'] == k and st['tagged'] and abs(st['sy'] - sy) < 1, f"{k}→{st['k']}, scroll {sy}→{st['sy']}")
        if reduced:
            check(f'{tag}: no highlight animation', st['fl'] == 0, str(st['fl']))
        elif not sort:
            check(f'{tag}: brief highlight on changed values', st['fl'] > 0, str(st['fl']))
    finally:
        api('/__reset')
        ctx.close()


def list_palette_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900)
    try:
        wait_list(page)
        page.click('.seg[data-key="palette"] button[data-v="global"]')
        page.wait_for_timeout(150)
        r = page.evaluate(LIST_JS, FIX['index'])
        check('list: palette switch recolours chips + bars, text stays readable', not (r['bad']['color'] or r['bad']['ink']), '; '.join((r['bad']['color'] + r['bad']['ink'])[:2]))
        page.click('#rangeseg button[data-v="10"]')
        page.wait_for_timeout(150)
        w = page.evaluate("""(() => { const r = document.querySelector('#world .kw-lr[data-k="SOX"]'); return r.querySelector('.kw-lb i').getBoundingClientRect().width / r.querySelector('.kw-lb').getBoundingClientRect().width; })()""")
        sox = next(it for g in FIX['index']['groups'] for it in g['items'] if it['key'] == 'SOX')
        want = min(abs(sox['ratio']) / 10, 1) * 0.5
        check('list: range ±10% rescales the bars', abs(w - want) < 0.02, f'{w:.3f} vs {want:.3f}')
        page.click('.seg[data-key="palette"] button[data-v="krg"]')
        page.click('#rangeseg button[data-v="3"]')
    finally:
        ctx.close()


def list_states_pass(browser):
    ERR.expect_net = True
    try:
        api('/__mode?world=fail')
        ctx, page = open_page(browser, LIVE + '#world', 390, 844, True)
        try:
            page.wait_for_selector('#world .kw-msg', timeout=8000)
            check('list view, failure: message + 다시 시도', '해외 지수를 불러오지 못했어요' in page.evaluate("document.querySelector('#world .kw-msg').textContent") and page.evaluate("document.querySelector('#world .kw-list').hidden"))
            api('/__mode?world=ok')
            page.tap('#world .kw-msg .kw-retry')
            wait_list(page)
            check('list view, failure → 다시 시도 loads the rows', page.evaluate("document.querySelectorAll('#world .kw-lr').length") == COUNT['index'])
        finally:
            ctx.close()
    finally:
        api('/__reset')
        ERR.expect_net = False


def kind_pass(browser, kind, width, height):
    mobile = width < 700
    hsh = '#world' if kind == 'index' else '#cmdty'
    ctx, page = open_page(browser, LIVE + hsh, width, height, mobile, view='map')
    try:
        wait_world(page)
        tag = f'{kind} {width}'
        n = page.evaluate("document.querySelectorAll('#world .kw-tile').length")
        check(f'{tag}: all items drawn', n == COUNT[kind], f'{n}/{COUNT[kind]}')
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f'{tag}: no horizontal overflow', ov <= 0, f'{ov}px')
        lab = page.evaluate(LABELS_JS)
        check(f'{tag}: labels / chips / headers inside', not lab['out'], '; '.join(lab['out'][:4]) or f"labels {lab['labs']}/{lab['tiles']}, chips {lab['chips']}/{lab['tiles']}")
        check(f'{tag}: every tile has a label', lab['labs'] == lab['tiles'], f"{lab['labs']}/{lab['tiles']}")
        check(f'{tag}: state chip on ≥ 90% of tiles', lab['chips'] >= 0.9 * lab['tiles'], f"{lab['chips']}/{lab['tiles']}")
        col = page.evaluate(COLORS_JS, FIX[kind])
        check(f'{tag}: tile colours = KH.colorOf(ratio), VIX grey', not col['bad'] and col['n'] == COUNT[kind], '; '.join(col['bad'][:3]))
        if mobile:
            small = page.evaluate(TARGETS_JS)
            check(f'{tag}: tap targets ≥ 40px', not small, '; '.join(small[:4]))
        side = page.evaluate("""() => { const s = document.querySelector('#world .kw-side').getBoundingClientRect(), m = document.querySelector('#world .kw-map').getBoundingClientRect();
            return { right: s.left >= m.right - 1, below: s.top >= m.bottom - 1 }; }""")
        check(f'{tag}: side panel {"below" if width <= 980 else "right of"} the map', side['below'] if width <= 980 else side['right'], str(side))
        if width in (1440, 768, 390, 1280, 360, 1920):
            page.screenshot(path=str(SHOTS / f'{kind}_{width}.png'), full_page=True)
    finally:
        ctx.close()


# ── world map (해외 지수 · 지도, AGENTS §3-4) + day / night (§3-5, docs/motion-brief.md (e)) ──
# representative index per country (AGENTS list), ISO numeric ids as in world-atlas
REP = {'840': 'INX', '484': 'MXX', '076': 'BVSP', '372': 'ISEQ', '826': 'FTSE', '528': 'AEX', '056': 'BFX', '250': 'FCHI',
       '620': 'PSI20', '724': 'IBEX', '752': 'OMXS30', '276': 'GDAXI', '348': 'BUX', '380': 'FTMIB', '356': 'BSESN', '156': 'SSEC',
       '410': 'KOSPI', '392': 'N225', '158': 'TWII', '344': 'HSI', '704': 'VNI', '458': 'KLSE', '360': 'JKSE', '036': 'AXJO'}
IDX = {it['key']: dict(it, gkey=g['key']) for g in FIX['index']['groups'] for it in g['items']}
REP_HERE = {c: k for c, k in REP.items() if k in IDX}
OFF = [k for k, it in IDX.items() if it['gkey'] in ('usf', 'ref')]       # the side box 미국 선물 및 변동성 지수 (유로스톡스 50 is the 유로존 chip in Europe)


def subsolar(ms):
    """the same low-precision almanac as the brief, written independently → night centre (lon, lat)"""
    import math
    rad = math.pi / 180
    d = ms / 864e5 - 10957.5
    g = (357.529 + 0.98560028 * d) * rad
    q = 280.459 + 0.98564736 * d
    lam = (q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) * rad
    e = (23.439 - 3.6e-7 * d) * rad
    ra = math.degrees(math.atan2(math.cos(e) * math.sin(lam), math.cos(lam)))
    dec = math.degrees(math.asin(math.sin(e) * math.sin(lam)))
    eqt = (((q - ra) / 15) % 24 + 36) % 24 - 12
    utc = (ms % 864e5) / 36e5
    lon = -15 * (utc - 12 + eqt)
    wrap = lambda x: (x % 360 + 540) % 360 - 180
    return wrap(lon + 180), -dec


def lon_diff(a, b):
    return abs((a - b + 540) % 360 - 180)


GEO_JS = r"""
(rep) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const sgn = v => v > 0 ? '+' : v < 0 ? '−' : '';
  const pct = v => sgn(v) + Math.abs(v).toFixed(2) + '%';
  const geo = document.querySelector('#world .kw-geo'), mapBox = geo.querySelector('.kw-gmap'), mr = mapBox.getBoundingClientRect();
  const narrow = geo.classList.contains('narrow');
  const out = { colour: [], label: [], clip: [], overlap: [], none: [], open: [] };
  let coloured = 0;
  for (const [id, it] of Object.entries(rep)) {
    const want = norm(KH.colorOf(it.ratio));
    const el = geo.querySelector(`.kw-cp[data-c="${id}"]`) || geo.querySelector(`.kw-gmk[data-c="${id}"]`);
    if (!el) { out.colour.push(`${id} not drawn`); continue; }
    const got = norm(getComputedStyle(el).fill);
    if (got !== want) out.colour.push(`${id} ${got} != ${want}`); else coloured++;
    // the % shown for the country: on the map (desktop) or in its button under the map (phones)
    const lab = narrow ? geo.querySelector(`.kw-gc[data-c="${id}"] .p`) : geo.querySelector(`.kw-gl[data-c="${id}"] .p`);
    if (!lab || lab.textContent !== pct(it.ratio)) out.label.push(`${id} '${lab && lab.textContent}' != ${pct(it.ratio)}`);
    const open = it.status === 'OPEN';
    const marked = !!geo.querySelector(`.kw-ggl path[data-c="${id}"]`) || !!geo.querySelector(`.kw-gmk.open[data-c="${id}"]`);
    if (open !== marked) out.open.push(`${id} open=${open} outline=${marked}`);
    const dot = geo.querySelector(`.kw-gdot[data-c="${id}"], .kw-gmk[data-c="${id}"]`) || geo.querySelector(`.kw-gl[data-c="${id}"] .kw-sd`);
    if (dot && (dot.classList.contains('open') !== open)) out.open.push(`${id} marker state`);
  }
  for (const p of geo.querySelectorAll('.kw-cp:not(.has)')) { const f = norm(getComputedStyle(p).fill); if (f !== 'rgb(31, 33, 38)') { out.none.push(f); break; } }
  // labels and chips: inside the map, % not cut, no two on top of each other, none under the side box
  const labs = [...geo.querySelectorAll('.kw-gl')].map(el => ({ el, r: el.getBoundingClientRect() }));
  const box = mapBox.querySelector('.kw-goff');
  for (const { el, r } of labs) {
    if (r.left < mr.left - 0.5 || r.right > mr.right + 0.5 || r.top < mr.top - 0.5 || r.bottom > mr.bottom + 0.5) out.clip.push(`${el.dataset.c} outside the map`);
    for (const c of el.querySelectorAll('.p, .t')) if (c.scrollWidth > c.clientWidth + 1) out.clip.push(`${el.dataset.c} ${c.className} cut`);
  }
  const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
  for (let i = 0; i < labs.length; i++) for (let j = i + 1; j < labs.length; j++) if (hit(labs[i].r, labs[j].r)) out.overlap.push(`${labs[i].el.dataset.c} × ${labs[j].el.dataset.c}`);
  if (box) { const br = box.getBoundingClientRect(); for (const { el, r } of labs) if (hit(r, br)) out.overlap.push(`${el.dataset.c} under the side box`); }
  const offKeys = [...geo.querySelectorAll('.kw-go')].map(b => b.dataset.k);
  const vix = geo.querySelector('.kw-go[data-k="VIX"] .kw-pchip');
  const n = geo.querySelector('.kw-gnight');
  return { coloured, out, offKeys, vixGrey: !!vix && vix.classList.contains('ref') && getComputedStyle(vix).backgroundColor === 'rgba(0, 0, 0, 0)',
    night: { caps: n.querySelectorAll('.kw-gn').length, line: n.querySelectorAll('.kw-gterm').length, lon: +n.dataset.lon, lat: +n.dataset.lat,
      empty: [...n.children].filter(c => !c.getAttribute('d')).length, op: getComputedStyle(n.querySelector('.kw-gn')).fillOpacity, fill: getComputedStyle(n.querySelector('.kw-gn')).fill },
    order: [...geo.querySelector('.kw-gsvg').children].map(c => c.getAttribute('class')),
    h: mr.height, w: mr.width, narrow };
}"""

GEO_TARGETS_JS = r"""
() => {
  const small = [];
  for (const el of document.querySelectorAll('#world .kw-gc, #world .kw-go, #world .kw-seg button, #world .kw-row')) {
    if (!el.offsetParent) continue;
    const r = el.getBoundingClientRect();
    if (r.height < 40 || r.width < 40) small.push(`${el.className} ${el.dataset.c || el.dataset.k || el.textContent.trim().slice(0, 10)} ${r.width.toFixed(0)}x${r.height.toFixed(0)}`);
  }
  return small;
}"""


def geo_pass(browser, width, height):
    mobile = width < 700
    ctx, page = open_page(browser, LIVE + '#world', width, height, mobile, view='map')
    try:
        wait_world(page, GEO_SEL)
        t0 = page.evaluate('Date.now()')
        tag = f'world map {width}'
        r = page.evaluate(GEO_JS, {c: IDX[k] for c, k in REP_HERE.items()})
        o = r['out']
        check(f'{tag}: every representative index colours its country (KH.colorOf)', r['coloured'] == len(REP_HERE) and not o['colour'], f"{r['coloured']}/{len(REP_HERE)} " + '; '.join(o['colour'][:3]))
        check(f'{tag}: countries without an index stay dark grey', not o['none'], str(o['none']))
        check(f'{tag}: each country shows its representative %', not o['label'], '; '.join(o['label'][:3]))
        check(f'{tag}: labels inside the map, % never cut', not o['clip'], '; '.join(o['clip'][:3]))
        check(f'{tag}: labels do not overlap each other or the side box', not o['overlap'], '; '.join(o['overlap'][:3]))
        check(f'{tag}: open markets outlined + marked, closed ones not', not o['open'], '; '.join(o['open'][:3]))
        check(f'{tag}: side box 미국 선물 및 변동성 지수 = US futures + VIX (VIX grey), no 유로스톡스 50', sorted(r['offKeys']) == sorted(OFF) and 'STOXX50E' not in r['offKeys'] and r['vixGrey'], str(r['offKeys']))
        ez = page.evaluate("""() => { const b = document.querySelector('#world .kw-gb[data-c="EZ"]'); const t = document.querySelector('#world .kw-goh');
            return { has: !!b, text: b && b.textContent, title2: b && (b.title + b.getAttribute('aria-label')), title: t && t.textContent, grid: !!document.querySelector('#world .kw-gc[data-c="EZ"]') }; }""")
        check(f'{tag}: 유로스톡스 50 as the 유로존 chip (or grid button on phones), box titled 미국 선물 및 변동성 지수', ez['title'] == '미국 선물 및 변동성 지수' and (ez['grid'] if mobile else (ez['has'] and '유로존' in ez['text'] and '유로스톡스 50' in ez['title2'])), str(ez))
        nt = r['night']
        lon, lat = subsolar(t0)
        check(f'{tag}: day/night — four 12 % caps + terminator around the antisolar point', nt['caps'] == 4 and nt['line'] == 1 and nt['empty'] == 0 and nt['op'] == '0.12'
              and nt['fill'] == 'rgb(5, 8, 20)' and lon_diff(nt['lon'], lon) < 0.5 and abs(nt['lat'] - lat) < 0.3, f"centre {nt['lon']:.2f},{nt['lat']:.2f} vs {lon:.2f},{lat:.2f}")
        order = [c for c in r['order'] if c in ('kw-gland', 'kw-gnight', 'kw-gbord', 'kw-gglow', 'kw-glines', 'kw-gmarks')]
        check(f'{tag}: layers fills → night → borders → glow → lines → markers', order == ['kw-gland', 'kw-gnight', 'kw-gbord', 'kw-gglow', 'kw-glines', 'kw-gmarks'], str(order))
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f'{tag}: no horizontal overflow', ov <= 0, f'{ov}px')
        if mobile:
            small = page.evaluate(GEO_TARGETS_JS)
            check(f'{tag}: tap targets ≥ 40px (country buttons, side box)', not small, '; '.join(small[:4]))
        page.screenshot(path=str(SHOTS / f'geo_{width}.png'), full_page=True)
    finally:
        ctx.close()


def ticker_detail_pass(browser):
    """KHWorld.openDetail(key, {opener}) (the ticker's way in) for a future and VIX, from the list tab and from another tab."""
    for hsh, tag in (('#world', 'on 해외'), ('', 'from another tab')):
        ctx, page = open_page(browser, LIVE + hsh, 1280, 800)
        try:
            page.evaluate("window.__wd = []; document.addEventListener('kh:worlddetail', e => window.__wd.push(e.detail.open))")
            if hsh:
                wait_list(page)
            else:
                page.wait_for_timeout(1200)
            for key in ('NQcv1', 'VIX'):
                ok = page.evaluate("async k => { const b = document.createElement('button'); document.body.append(b); return await KHWorld.openDetail(k, { opener: b }); }", key)
                page.wait_for_selector('.kw-sheet:not([hidden])', timeout=6000)
                st = page.evaluate("({ name: document.querySelector('#kw-dt').textContent, open: KHWorld.detailOpen(), ev: window.__wd.slice() })")
                check(f'ticker openDetail({key}) {tag}: sheet opens, detailOpen() true, kh:worlddetail fired', st['name'] == IDX[key]['name'] and st['open'] and st['ev'] and st['ev'][-1] is True, f'{ok} {st}')
                page.keyboard.press('Escape')
                page.wait_for_timeout(150)
                st = page.evaluate("({ open: KHWorld.detailOpen(), last: window.__wd[window.__wd.length - 1] })")
                check(f'ticker openDetail({key}) {tag}: Esc closes, detailOpen() false, kh:worlddetail open=false', not st['open'] and st['last'] is False, str(st))
        finally:
            ctx.close()


def geo_click_pass(browser):
    us = [k for k, it in IDX.items() if it['gkey'] == 'us']
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900, view='map')
    try:
        wait_world(page, GEO_SEL)
        page.click('#world .kw-gl[data-c="840"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        st = page.evaluate("""() => ({ name: document.querySelector('#kw-dt').textContent, peers: [...document.querySelectorAll('.kw-sheet .kw-peers button')].map(b => b.dataset.k),
            place: document.querySelector('.kw-peers-h') && document.querySelector('.kw-peers-h').textContent, sel: !!document.querySelector('#world .kw-gsel path'),
            pressed: document.querySelector('.kw-peers button[aria-pressed=true]').dataset.k })""")
        check('world map click 미국: sheet with S&P 500 + every US index', st['name'] == IDX['INX']['name'] and sorted(st['peers']) == sorted(us + [k for k, it in IDX.items() if it['gkey'] in ('usf', 'ref')]) and st['pressed'] == 'INX' and st['place'] == '미국' and st['sel'], str(st))
        page.click('.kw-sheet .kw-peers button[data-k="IXIC"]')
        page.wait_for_timeout(150)
        check('world map sheet: switching to 나스닥 inside the country', page.evaluate("document.querySelector('#kw-dt').textContent") == IDX['IXIC']['name'])
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        back = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, c: document.activeElement.dataset.c, sel: !!document.querySelector('#world .kw-gsel path') })")
        check('world map sheet: Esc closes, focus back on 미국, outline cleared', back['hidden'] and back['c'] == '840' and not back['sel'], str(back))
        page.dispatch_event('#world .kw-cp[data-c="276"]', 'click')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        check('world map: clicking Germany itself opens DAX', page.evaluate("document.querySelector('#kw-dt').textContent") == IDX['GDAXI']['name'])
        page.keyboard.press('Escape')
        page.dispatch_event('#world .kw-gmk[data-c="344"]', 'click')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        hk = page.evaluate("[document.querySelector('#kw-dt').textContent, [...document.querySelectorAll('.kw-sheet .kw-peers button')].map(b => b.dataset.k)]")
        check('world map: the 홍콩 marker opens 항셍 (+ H지수)', hk[0] == IDX['HSI']['name'] and sorted(hk[1]) == ['HSCE', 'HSI'], str(hk))
        page.keyboard.press('Escape')
        page.click('#world .kw-gb[data-c="EZ"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        check('world map: the 유로존 chip opens 유로스톡스 50', page.evaluate("document.querySelector('#kw-dt').textContent") == IDX['STOXX50E']['name'])
        page.keyboard.press('Escape')
        page.click('#world .kw-go[data-k="NQcv1"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        fu = page.evaluate("[document.querySelector('#kw-dt').textContent, [...document.querySelectorAll('.kw-sheet .kw-peers button')].map(b => b.dataset.k)]")
        check('world map side box: 나스닥 100 선물 opens with the other US futures', fu[0] == IDX['NQcv1']['name'] and sorted(fu[1]) == sorted(k for k, it in IDX.items() if it['gkey'] == 'usf'), str(fu))
        page.keyboard.press('Escape')
        lay = page.evaluate('KHWorld.layout()')
        check('KHWorld.layout() on the world map: an array (tile picture or empty)', isinstance(lay, list))
    finally:
        ctx.close()
    ctx, page = open_page(browser, LIVE + '#world', 390, 844, True, view='map')
    try:
        wait_world(page, GEO_SEL)
        page.tap('#world .kw-gc[data-c="158"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.wait_for_timeout(300)
        check('world map (phone): tapping 대만 opens 대만 가권', page.evaluate("document.querySelector('#kw-dt').textContent") == IDX['TWII']['name'])
        page.screenshot(path=str(SHOTS / 'geo_sheet_390.png'))
    finally:
        ctx.close()


def geo_keyboard_pass(browser):
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='map')
    try:
        wait_world(page, GEO_SEL)
        stops = page.evaluate("[...document.querySelectorAll('#world .kw-gb')].filter(b => b.tabIndex === 0).length")
        check('world map keyboard: one tab stop (roving)', stops == 1, str(stops))
        page.focus('#world .kw-gb[tabindex="0"]')
        seen = [page.evaluate('document.activeElement.dataset.f')]
        for key in ('ArrowRight', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowUp'):
            page.keyboard.press(key)
            seen.append(page.evaluate('document.activeElement.dataset.f'))
        check('world map keyboard: arrows move between countries', len(set(seen)) >= 4 and all(seen), ' → '.join(map(str, seen)))
        ring = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineColor]; })()")
        check('world map keyboard: amber focus ring', ring == ['solid', 'rgb(255, 181, 71)'], str(ring))
        page.keyboard.press('End'); e = page.evaluate('document.activeElement.dataset.f')
        page.keyboard.press('Home'); h0 = page.evaluate('document.activeElement.dataset.f')
        check('world map keyboard: Home / End', e != h0 and e and h0, f'{h0} … {e}')
        tgt = page.evaluate('document.activeElement.dataset.f')
        page.keyboard.press('Enter')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        check('world map keyboard: Enter opens, Esc returns focus', page.evaluate('document.activeElement.dataset.f') == tgt)
    finally:
        ctx.close()


def geo_fallback_pass(browser):
    ERR.expect_net = True
    try:
        for how in ('block', 'bad'):
            ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='map', atlas=how)
            try:
                wait_list(page)
                st = page.evaluate("""({ note: !document.querySelector('#world .kw-gnote').hidden && document.querySelector('#world .kw-gnote').textContent, geo: document.querySelector('#world .kw-geo').hidden,
                    rows: document.querySelectorAll('#world .kw-lr').length, pressed: document.querySelector('#world .kw-seg[data-kw=view] button[aria-pressed=true]').textContent,
                    stored: localStorage.getItem('khm.worldView') })""")
                what = 'fetch blocked' if how == 'block' else 'SRI mismatch (altered bytes)'
                check(f'world map fallback, {what}: list + message, choice kept', st['note'] and '목록으로' in st['note'] and st['geo'] and st['rows'] == COUNT['index'] and st['pressed'] == '목록' and st['stored'] == 'map', str(st))
                if how == 'block':
                    page.screenshot(path=str(SHOTS / 'geo_fallback_1280.png'))
                    route_atlas(page.context, 'local')
                    page.click('#world .kw-gnote .kw-retry')
                    wait_world(page, GEO_SEL)
                    check('world map fallback: 다시 시도 loads the map', page.evaluate("document.querySelector('#world .kw-gnote').hidden && !document.querySelector('#world .kw-geo').hidden"))
            finally:
                ctx.close()
    finally:
        ERR.expect_net = False
    # the atlas is fetched once, only when the map view opens
    reqs = []
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        page.on('request', lambda r: reqs.append(r.url) if 'world-atlas' in r.url else None)
        wait_list(page)
        n0 = len(reqs)
        page.click('#world .kw-seg[data-kw=view] button[data-v=map]')
        wait_world(page, GEO_SEL)
        page.click('#world .kw-seg[data-kw=view] button[data-v=list]')
        page.click('#world .kw-seg[data-kw=view] button[data-v=map]')
        wait_world(page, GEO_SEL)
        check('world map data: not fetched for the list, fetched once for the map', n0 == 0 and len(reqs) == 1, f'{n0} then {len(reqs)}')
    finally:
        ctx.close()


def geo_refresh_pass(browser):
    api('/__reset')
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900, clock=True, view='map')
    try:
        wait_world(page, GEO_SEL)
        page.evaluate("document.querySelectorAll('#world .kw-gb, #world .kw-cp.has').forEach(e => e.__tag = 1)")
        page.focus('#world .kw-gl[data-c="392"]')
        before = page.evaluate("document.querySelector('#world .kw-gl[data-c=\"392\"] .p').textContent")
        api('/__mode?world=drift')
        page.clock.run_for(30500)
        page.wait_for_function("(b) => document.querySelector('#world .kw-gl[data-c=\"392\"] .p').textContent !== b", arg=before, timeout=5000)
        page.wait_for_timeout(700)                         # the 0.48 s fill transition
        last = api('/__last?kind=index')
        items = {it['key']: it for g in last['groups'] for it in g['items']}
        r = page.evaluate(GEO_JS, {c: items[k] for c, k in REP_HERE.items()})
        st = page.evaluate("({ f: document.activeElement.dataset.f, tagged: !!document.activeElement.__tag, fresh: [...document.querySelectorAll('#world .kw-gb, #world .kw-cp.has')].filter(e => !e.__tag).length })")
        check('world map refresh: colours + % follow the new answer, in place, focus kept', not (r['out']['colour'] or r['out']['label']) and st['f'] == 'c392' and st['tagged'] and st['fresh'] == 0,
              str(st) + ' ' + '; '.join((r['out']['colour'] + r['out']['label'])[:2]))
    finally:
        api('/__reset')
        ctx.close()


def night_pass(browser):
    # a fixed instant: 2026-06-21 12:00 UTC → the sun over ~0°E, 23.4°N; night centred near 180°, −23.4°
    t = 1782043200000
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, clock=t, view='map')
    try:
        wait_world(page, GEO_SEL)
        t = page.evaluate('Date.now()')
        a = page.evaluate("[+document.querySelector('.kw-gnight').dataset.lon, +document.querySelector('.kw-gnight').dataset.lat]")
        lon, lat = subsolar(t)
        check('day/night: centre at the antisolar point (June solstice, noon UTC)', lon_diff(a[0], lon) < 0.3 and abs(a[1] - lat) < 0.2 and abs(a[1] + 23.4) < 0.2, f'{a} vs {lon:.2f},{lat:.2f}')
        page.clock.run_for(60 * 60 * 1000)
        page.wait_for_timeout(100)
        b = page.evaluate("[+document.querySelector('.kw-gnight').dataset.lon, +document.querySelector('.kw-gnight').dataset.lat]")
        lon2, _ = subsolar(t + 3600000)
        check('day/night: redrawn every minute (an hour later the night moved 15° west)', lon_diff(b[0], lon2) < 0.3 and abs(lon_diff(a[0], b[0]) - 15) < 0.3, f'{a[0]} → {b[0]}')
    finally:
        ctx.close()
    # every effect level draws it; only 'fancy' pulses the open markets (KH.motion() stubbed: the template adds it later)
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='map', reduced=True)
    try:
        wait_world(page, GEO_SEL)
        r = page.evaluate("({ caps: document.querySelectorAll('.kw-gnight .kw-gn').length, rm: document.getElementById('world').classList.contains('kw-rm'), anim: [...document.querySelectorAll('.kw-gp')].filter(p => getComputedStyle(p).animationName !== 'none').length })")
        check('day/night under reduced motion: still drawn, nothing moves', r['caps'] == 4 and r['rm'] and r['anim'] == 0, str(r))
    finally:
        ctx.close()
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900, view='map')
    try:
        wait_world(page, GEO_SEL)
        PULSE = """() => { const rings = [...document.querySelectorAll('#world .kw-gp.on')].filter(p => getComputedStyle(p).animationName === 'kwRing');
            const labs = [...document.querySelectorAll('#world .kw-gl.in .kw-sd.open')].filter(d => getComputedStyle(d, '::after').animationName === 'kwRing');
            const open = document.querySelectorAll('#world .kw-gdot.open, #world .kw-gmk.open').length + document.querySelectorAll('#world .kw-gl.in .kw-sd.open').length;
            const dl = rings.map(p => [+p.getAttribute('cx'), parseFloat(p.style.animationDelay)]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
            return { rings: rings.length, labs: labs.length, open, wave: dl.every((v, i) => !i || v >= dl[i - 1] - 0.02), glow: document.querySelectorAll('#world .kw-ggl path').length }; }"""
        std = page.evaluate(PULSE)
        check("effects 'standard': open markets glow (static), no pulse", std['rings'] == 0 and std['labs'] == 0 and std['glow'] > 0, str(std))
        page.evaluate("KH.motion = () => 'fancy'; document.dispatchEvent(new CustomEvent('kh:motion', { detail: { motion: 'fancy' } }))")
        page.wait_for_timeout(100)
        fx = page.evaluate(PULSE)
        check("effects 'fancy': one pulse ring per open marker, staggered west → east", fx['rings'] + fx['labs'] == fx['open'] and fx['open'] > 0 and fx['wave'] and fx['rings'] + fx['labs'] <= 25, str(fx))
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
        ps = page.evaluate("getComputedStyle(document.querySelector('#world .kw-gp.on')).animationPlayState")
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
        check("effects 'fancy': pulse paused while the browser tab is hidden", ps == 'paused', ps)
        page.screenshot(path=str(SHOTS / 'geo_fancy_1440.png'))
        page.evaluate("KH.motion = () => 'standard'; document.dispatchEvent(new CustomEvent('kh:motion', { detail: { motion: 'standard' } }))")
        page.wait_for_timeout(50)
        check("effects back to 'standard': pulse stops", page.evaluate(PULSE)['rings'] == 0)
    finally:
        ctx.close()


def motion_setting_pass(browser):
    # the template's own 효과 setting (localStorage khm.motion → KH.motion()), not a stub
    ctx, page = open_page(browser, LIVE + '#world', 1440, 900, view='map')
    try:
        ctx.add_init_script("localStorage.setItem('khm.motion', JSON.stringify('fancy'));")       # the template stores JSON
        page.reload()
        wait_world(page, GEO_SEL)
        has = page.evaluate("typeof KH.motion === 'function'")
        if not has:
            check('효과 setting: template has no KH.motion yet → treated as standard', not page.evaluate("document.getElementById('world').classList.contains('kw-fx')"))
            return
        r = page.evaluate("""({ m: KH.motion(), fx: document.getElementById('world').classList.contains('kw-fx'),
            rings: [...document.querySelectorAll('#world .kw-gp.on')].filter(p => getComputedStyle(p).animationName === 'kwRing').length })""")
        check("효과 setting 화려하게 (khm.motion): the world map pulses", r['m'] == 'fancy' and r['fx'] and r['rings'] > 0, str(r))
        # 효과 · 줄이기 in the template's settings (its button's own handler; the panel may be folded at this width)
        if page.evaluate("!!document.querySelector('#motionseg button[data-mo=\"reduced\"]')"):
            page.evaluate("document.querySelector('#motionseg button[data-mo=\"reduced\"]').click()")
            page.wait_for_timeout(150)
            check('효과 setting 줄이기 picked in the settings → KH.motion() reduced', page.evaluate("KH.motion()") == 'reduced')
        if page.evaluate("KH.motion()") == 'reduced':
            r2 = page.evaluate("({ rm: document.getElementById('world').classList.contains('kw-rm'), rings: [...document.querySelectorAll('#world .kw-gp.on')].filter(p => getComputedStyle(p).animationName === 'kwRing').length, caps: document.querySelectorAll('.kw-gnight .kw-gn').length })")
            check('효과 setting 줄이기: nothing moves, night still drawn', r2['rm'] and r2['rings'] == 0 and r2['caps'] == 4, str(r2))
    finally:
        ctx.close()


def refresh_event_pass(browser):
    # the header clock's tap (KH.refresh → document 'kh:refresh', AGENTS §3-6) fetches at once, view and scroll kept
    api('/__reset')
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    try:
        wait_list(page)
        page.evaluate('scrollTo(0, 200)')
        a = api('/__stats').get('world:index', 0)
        page.evaluate("document.dispatchEvent(new Event('kh:refresh'))")
        page.wait_for_timeout(600)
        b = api('/__stats').get('world:index', 0)
        check('kh:refresh: fetches now, list and scroll kept', b == a + 1 and page.evaluate("KHWorld.view() === 'list' && scrollY") == 200, f'{a}→{b}')
    finally:
        ctx.close()


def keyboard_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800, view='map')
    try:
        wait_world(page)
        stops = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].filter(t => t.tabIndex === 0).length")
        check('keyboard: one tab stop in the map (roving)', stops == 1, f'{stops}')
        page.focus('#world .kw-tile[tabindex="0"]')
        first = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowRight')
        right = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowDown')
        down = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowLeft'); page.keyboard.press('ArrowUp')
        back = page.evaluate('document.activeElement.dataset.k')
        check('keyboard: arrows move between tiles', first and right and right != first and down and down != right, f'{first}→{right}→{down}→{back}')
        moved = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].filter(t => t.tabIndex === 0).map(t => t.dataset.k)")
        check('keyboard: tab stop follows focus', moved == [back], str(moved))
        page.keyboard.press('Home')
        home = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('ArrowRight')
        tgt = page.evaluate('document.activeElement.dataset.k')
        page.keyboard.press('Enter')
        page.wait_for_selector('.kw-sheet:not([hidden])', timeout=3000)
        info = page.evaluate("""() => ({ inSheet: document.querySelector('.kw-sheet').contains(document.activeElement),
            name: document.querySelector('#kw-dt').textContent, sel: document.querySelector('#world .kw-tile.sel')?.dataset.k,
            tileName: document.querySelector('#world .kw-tile.sel')?.title })""")
        check('detail: Enter opens it, focus inside, tile marked', info['inSheet'] and info['sel'] == tgt and info['name'] == info['tileName'], str(info))
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        check('detail: 3개월 chart drawn', page.evaluate("document.querySelectorAll('.kw-sheet .kw-svg path.kw-line').length") == 1)
        meta = page.evaluate("[...document.querySelectorAll('.kw-meta dt')].map(d => d.textContent)")
        check('detail: value · state · local time · KST · unit rows', all(k in meta for k in ('시세', '현지 거래 시각', '한국 시각', '단위')), str(meta))
        page.click('.kw-tf button:has-text("1년")')
        page.wait_for_function("document.querySelector('.kw-tf button[aria-pressed=\"true\"]').textContent === '1년' && !!document.querySelector('.kw-sheet svg.kw-svg')", timeout=5000)
        lab1y = page.evaluate("document.querySelector('.kw-sheet svg.kw-svg').getAttribute('aria-label')")
        check('detail: 1년 switch redraws', lab1y.startswith('1년'), lab1y[:40])
        page.focus('.kw-sheet .kw-x')
        trapped = True
        for _ in range(7):
            page.keyboard.press('Tab')
            trapped &= page.evaluate("document.querySelector('.kw-sheet').contains(document.activeElement)")
        check('detail: Tab stays inside the sheet', trapped)
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        after = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, k: document.activeElement.dataset.k, sel: document.querySelectorAll('#world .kw-tile.sel').length, still: !document.querySelector('main.layout') || true })")
        check('detail: Esc closes and focus returns to the tile', after['hidden'] and after['k'] == tgt and after['sel'] == 0, str(after))
        # Esc must not reach the heatmap (zoom-out etc.) and must not reopen anything
        page.keyboard.press('Tab')
        out = page.evaluate("!document.activeElement.classList.contains('kw-tile')")
        check('keyboard: Tab leaves the map after one stop', out, page.evaluate('document.activeElement.className'))
        # side list → detail → Esc back to the row
        page.click('#world .kw-row')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
        check('side list: opens detail, Esc returns focus to the row', page.evaluate("document.activeElement.classList.contains('kw-row')"))
        # click outside closes on desktop
        page.click('#world .kw-tile')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.mouse.click(5, 300)
        page.wait_for_timeout(100)
        check('detail: click outside closes (desktop)', page.evaluate("document.querySelector('.kw-sheet').hidden"))
        # layout() for image saving
        lay = page.evaluate("KHWorld.layout()")
        tiles = [x for x in lay if x['kind'] == 'tile']
        mw, mh = page.evaluate("[document.querySelector('#world .kw-map').clientWidth, document.querySelector('#world .kw-map').clientHeight]")
        okb = all(0 <= t['x'] and t['x'] + t['w'] <= mw + 0.5 and 0 <= t['y'] and t['y'] + t['h'] <= mh + 0.5 for t in tiles)
        subs = page.evaluate("[...document.querySelectorAll('#world .kw-tile')].map(t => [t.dataset.k, t.querySelector('.kw-pc').hidden || t.querySelector('.kw-lab').hidden ? '' : t.querySelector('.kw-pc').textContent])")
        subok = dict(subs) == {t['code']: t['sub'] for t in tiles}
        check('KHWorld.layout(): tiles + groups in map pixels, sub = shown %', len(tiles) == COUNT['commodity'] and okb and subok and sum(1 for x in lay if x['kind'] == 'sector') == len(FIX['commodity']['groups']), f'{len(tiles)} tiles, inBounds {okb}, sub {subok}')
        page.screenshot(path=str(SHOTS / 'kbd_1280.png'))
    finally:
        ctx.close()


def palette_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 1440, 900, view='map')
    try:
        wait_world(page)
        before = page.evaluate("document.querySelector('#world .kw-tile[data-k=\"GCcv1\"]').style.backgroundColor")
        page.click('.seg[data-key="palette"] button[data-v="global"]')
        page.wait_for_timeout(150)
        col = page.evaluate(COLORS_JS, FIX['commodity'])
        after = page.evaluate("document.querySelector('#world .kw-tile[data-k=\"GCcv1\"]').style.backgroundColor")
        check('palette switch recolours tiles (초록 상승)', before != after and not col['bad'], f'{before} → {after}')
        sw = page.evaluate("[document.querySelector('#world .kw-row .kw-sw').style.background, document.querySelector('#world .kw-legend .grad').style.background]")
        check('palette switch recolours side swatches + legend', 'rgb' in sw[0] and '#f63538' in sw[1].lower() or 'rgb(246, 53, 56)' in sw[1], sw[1][:60])
        page.click('#rangeseg button[data-v="10"]')
        page.wait_for_timeout(150)
        col = page.evaluate(COLORS_JS, FIX['commodity'])
        tick = page.evaluate("[...document.querySelectorAll('#world .kw-legend .tk')].map(t => t.textContent)")
        check('range switch (±10%) recolours + legend ticks', not col['bad'] and tick == ['−10%', '+10%'], str(tick))
        page.click('.seg[data-key="palette"] button[data-v="krg"]')
        page.click('#rangeseg button[data-v="3"]')
    finally:
        ctx.close()


def states_pass(browser):
    ERR.expect_net = True
    try:
        for mode, text in (('fail', '해외 지수를 불러오지 못했어요'), ('html404', '서버에 아직 이 기능이 없어요'), ('empty', '지금 보여 줄 해외 지수가 없어요')):
            api(f'/__mode?world={mode}')
            ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='list')
            try:
                page.wait_for_selector('#world .kw-msg', timeout=8000)
                page.wait_for_timeout(300)
                msg = page.evaluate("document.querySelector('#world .kw-msg').textContent")
                check(f'state {mode}: message', text in msg and page.evaluate("!!document.querySelector('#world .kw-msg .kw-retry')"), msg[:60])
                if mode == 'fail':
                    page.screenshot(path=str(SHOTS / 'fail_1280.png'))
                    api('/__mode?world=ok')
                    page.click('#world .kw-msg .kw-retry')
                    wait_list(page)
                    check('state fail → 다시 시도 loads', page.evaluate("document.querySelectorAll('#world .kw-lr').length") == COUNT['index'])
            finally:
                ctx.close()
        api('/__mode?world=ok')
        # loading message while the first answer is slow
        api('/__mode?world=slow')
        ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844, True, view='map')
        try:
            page.wait_for_selector('#world .kw-msg.busy', timeout=3000)
            check('state loading: message while waiting', '불러오는 중이에요' in page.evaluate("document.querySelector('#world .kw-msg').textContent"))
            wait_world(page)
        finally:
            ctx.close()
        api('/__mode?world=ok')
        # stale: data shown, then a refresh fails → keeps tiles, says so
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800, clock=True, view='list')
        try:
            wait_list(page)
            api('/__mode?world=fail')
            page.clock.run_for(31000)
            page.wait_for_selector('#world .kw-stale', timeout=5000)
            check('state stale: rows kept + "새로 받지 못했어요"', page.evaluate("document.querySelectorAll('#world .kw-lr').length") == COUNT['index'],
                  page.evaluate("document.querySelector('#world .kw-stale').textContent"))
            api('/__mode?world=ok')
            page.clock.run_for(16000)
            page.wait_for_function("!document.querySelector('#world .kw-stale')", timeout=5000)
            check('state stale → recovers after 15 s retry', True)
        finally:
            ctx.close()
        # weekend: nothing open
        api('/__mode?world=closed')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='list')
        try:
            wait_list(page)
            t = page.evaluate("document.querySelector('#world .kw-open').textContent")
            check('state closed (weekend): "지금은 열린 시장이 없어요"', '지금은 열린 시장이 없어요' in t and '모두 마감' in page.evaluate("document.querySelector('#world .kw-sum').textContent"), t[:40])
        finally:
            ctx.close()
        api('/__mode?world=ok')
        # chart route missing (plain 404): detail without chart, asked once per session
        api('/__mode?chart=none')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='list')
        try:
            wait_list(page)
            c0 = api('/__stats').get('/api/world/chart', 0)
            page.click('#world .kw-lr[data-k="INX"]')
            page.wait_for_function("document.querySelector('.kw-sheet .kw-chart') && document.querySelector('.kw-sheet .kw-chart').hidden", timeout=5000)
            page.keyboard.press('Escape')
            page.click('#world .kw-lr[data-k="N225"]')
            page.wait_for_timeout(400)
            c1 = api('/__stats').get('/api/world/chart', 0)
            vis = page.evaluate("!document.querySelector('.kw-sheet').hidden && !!document.querySelector('.kw-sheet .kw-px b').textContent")
            check('chart route missing: detail shows values, chart hidden, probed once', vis and c1 - c0 == 1, f'chart calls {c1 - c0}')
        finally:
            ctx.close()
        api('/__mode?chart=fail')
        ctx, page = open_page(browser, LIVE + '#world', 1280, 800, view='list')
        try:
            wait_list(page)
            page.click('#world .kw-lr[data-k="GDAXI"]')
            page.wait_for_selector('.kw-sheet .kw-cmsg .kw-retry', timeout=5000)
            check('chart failure: message + 다시 시도', '차트를 불러오지 못했어요' in page.evaluate("document.querySelector('.kw-sheet .kw-cmsg').textContent"))
        finally:
            ctx.close()
    finally:
        api('/__reset')
        ERR.expect_net = False


def polling_pass(browser):
    api('/__reset')
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800, clock=True, view='map')
    try:
        wait_world(page, GEO_SEL)
        n = lambda: api('/__stats').get('world:index', 0)
        a = n()
        page.clock.run_for(30500); page.wait_for_timeout(500)
        b = n()
        check('polling: every 30 s while shown', b - a == 1, f'{a}→{b}')
        page.click('.tabs button[data-mkt="K"]')
        page.wait_for_timeout(200)
        check('hide(): #world hidden, map back', page.evaluate("document.getElementById('world').hidden && KHWorld.shown() === null"))
        page.clock.run_for(95000); page.wait_for_timeout(400)
        c = n()
        check('polling: stops while another tab is shown', c == b, f'{b}→{c}')
        page.click('.tabs button[data-mkt="WORLD"]')
        page.wait_for_timeout(500)
        d = n()
        check('polling: back on the tab with old data → loads at once', d == c + 1, f'{c}→{d}')
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
        page.clock.run_for(95000); page.wait_for_timeout(400)
        e = n()
        check('polling: stops while the browser tab is hidden', e == d, f'{d}→{e}')
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(500)
        f = n()
        check('polling: visible again → refreshes', f == e + 1, f'{e}→{f}')
        # switching kinds: commodity tab shows commodities, detail closes
        page.click('#world .kw-gl[data-c="276"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_world(page, '#world .kw-tile[data-k="CLcv1"]')
        k = page.evaluate("({ n: document.querySelectorAll('#world .kw-tile').length, title: document.querySelector('#world .kw-title').textContent, sheet: document.querySelector('.kw-sheet').hidden })")
        check('tab switch 해외 → 원자재: commodity tiles, detail closed', k['n'] == COUNT['commodity'] and k['title'] == '원자재' and k['sheet'], str(k))
        units = page.evaluate("[...document.querySelectorAll('#world .kw-v')].filter(v => !v.hidden).map(v => v.textContent)")
        check('commodity tiles show units where they fit', any('$/' in u or '¢/' in u for u in units), ', '.join(units[:4]))
    finally:
        ctx.close()


def mobile_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844, True, view='map')
    try:
        wait_world(page)
        page.tap('#world .kw-tile[data-k="CLcv1"]')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        page.wait_for_timeout(350)                       # the 0.2 s slide-in
        geo = page.evaluate("""() => { const r = document.querySelector('.kw-sheet').getBoundingClientRect();
            return { bottom: Math.round(r.bottom), vh: innerHeight, left: Math.round(r.left), w: Math.round(r.width), scrim: getComputedStyle(document.querySelector('.kw-scrim')).display }; }""")
        check('phone: detail is a bottom sheet with a scrim', geo['bottom'] == geo['vh'] and geo['left'] == 0 and geo['w'] == 390 and geo['scrim'] == 'block', str(geo))
        small = page.evaluate(TARGETS_JS)
        check('phone: sheet tap targets ≥ 40px', not small, '; '.join(small[:4]))
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check('phone: no overflow with the sheet open', ov <= 0, f'{ov}')
        page.screenshot(path=str(SHOTS / 'detail_390.png'))
        page.tap('.kw-scrim', position={'x': 50, 'y': 40})
        page.wait_for_timeout(150)
        check('phone: tapping the scrim closes', page.evaluate("document.querySelector('.kw-sheet').hidden"))
    finally:
        ctx.close()
    ctx, page = open_page(browser, LIVE + '#cmdty', 1440, 900, view='map')
    try:
        wait_world(page)
        page.click('#world .kw-tile[data-k="GCcv1"]')
        page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=5000)
        page.screenshot(path=str(SHOTS / 'detail_cmdty_1440.png'))
        unit = page.evaluate("[...document.querySelectorAll('.kw-meta dd')].map(d => d.textContent)")
        check('commodity detail: unit in words', '달러/트로이온스' in unit, str(unit))
    finally:
        ctx.close()


def reduced_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800, reduced=True, view='map')
    try:
        wait_world(page)
        page.click('#world .kw-tile')
        page.wait_for_selector('.kw-sheet:not([hidden])')
        r = page.evaluate("({ anim: getComputedStyle(document.querySelector('.kw-sheet')).animationName, tr: getComputedStyle(document.querySelector('#world .kw-tile')).transitionDuration })")
        check('reduced motion: no sheet animation, no tile transition', r['anim'] == 'none' and set(r['tr'].replace(' ', '').split(',')) == {'0s'}, str(r))
    finally:
        ctx.close()


def boot_pass(browser):
    # page opened at #cmdty: the template calls show() before world.js exists → the module starts itself
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800, view='map')
    try:
        wait_world(page)
        check('boot at #cmdty: module self-starts (template called show() too early)', page.evaluate("KHWorld.shown()") == 'commodity')
    finally:
        ctx.close()


def snapshot_pass(browser):
    for hsh in ('world', 'cmdty'):
        ctx, page = open_page(browser, SNAP + '#' + hsh, 390 if hsh == 'cmdty' else 1280, 844 if hsh == 'cmdty' else 800, hsh == 'cmdty')
        try:
            page.wait_for_selector('#world .kw-snap', timeout=8000)
            a = page.evaluate("document.querySelector('#world .kw-snap a').href")
            t = page.evaluate("document.querySelector('#world .kw-snap').textContent")
            check(f'snapshot #{hsh}: "실시간 버전에서 볼 수 있어요" + link', a == f'https://panse.pages.dev/#{hsh}' and '실시간 버전에서 볼 수 있어요' in t, a)
            ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f'snapshot #{hsh}: no overflow', ov <= 0)
            page.screenshot(path=str(SHOTS / f'snapshot_{hsh}.png'))
        finally:
            ctx.close()


def real_pass(browser):
    log = open('/tmp/kw-real-worker.log', 'w')
    env = dict(__import__('os').environ, NODE_USE_ENV_PROXY='1', ASSET_BASE=LIVE, PORT=str(REAL_PORT))
    proc = None
    try:
        api('/api/world?kind=index', f'http://127.0.0.1:{REAL_PORT}')
    except Exception:
        proc = subprocess.Popen(['node', 'worker/dev/serve.mjs'], cwd=ROOT, env=env, stdout=log, stderr=log)
        for _ in range(40):
            try:
                api('/api/world?kind=index', f'http://127.0.0.1:{REAL_PORT}'); break
            except Exception:
                time.sleep(0.5)
    try:
        real = {k: api(f'/api/world?kind={k}', f'http://127.0.0.1:{REAL_PORT}') for k in ('index', 'commodity')}
        # 해외 지도 = the world map, with the atlas from the real jsDelivr (SRI checked by the browser) when it can be reached
        atlas = 'real' if '--real-cdn' in sys.argv else 'local'
        ctx, page = open_page(browser, f'http://127.0.0.1:{REAL_PORT}/#world', 1440, 900, view='map', atlas=atlas)
        try:
            wait_world(page, GEO_SEL, timeout=30000)
            now = api('/api/world?kind=index', f'http://127.0.0.1:{REAL_PORT}')
            items = {it['key']: it for g in now['groups'] for it in g['items']}
            reps = {c: items[k] for c, k in REP.items() if k in items}
            r = page.evaluate(GEO_JS, reps)
            o = r['out']
            check(f'real Worker world map ({atlas} atlas): every representative index coloured, labels clean', r['coloured'] >= len(reps) - 2 and not (o['clip'] or o['overlap'] or o['none']),
                  f"{r['coloured']}/{len(reps)}; " + '; '.join((o['colour'] + o['clip'] + o['overlap'])[:3]))
            page.click('#world .kw-gl[data-c="840"]')
            page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=20000)
            check('real Worker world map: 미국 → sheet with chart', page.evaluate("document.querySelectorAll('.kw-sheet .kw-peers button').length") >= 3)
            page.keyboard.press('Escape')
            page.screenshot(path=str(SHOTS / 'real_geo_1440.png'), full_page=True)
        finally:
            ctx.close()
        # 원자재 지도 = the tile map
        want = sum(len(g['items']) for g in real['commodity']['groups'])
        ctx, page = open_page(browser, f'http://127.0.0.1:{REAL_PORT}/#cmdty', 1440, 900, view='map')
        try:
            wait_world(page, timeout=20000)
            n = page.evaluate("document.querySelectorAll('#world .kw-tile').length")
            lab = page.evaluate(LABELS_JS)
            page.click('#world .kw-tile')
            page.wait_for_selector('.kw-sheet svg.kw-svg', timeout=20000)
            check('real Worker commodity: tiles, labels inside, chart', abs(n - want) <= 2 and not lab['out'], f'{n} tiles (api {want}); ' + '; '.join(lab['out'][:2]))
            page.screenshot(path=str(SHOTS / 'real_commodity_1440.png'))
        finally:
            ctx.close()
        for kind, hsh in (('index', 'world'), ('commodity', 'cmdty')):
            # the default list view against the same Worker: every row, values as the API gives them
            for w, hgt in ((1440, 900), (390, 844)):
                ctx, page = open_page(browser, f'http://127.0.0.1:{REAL_PORT}/#{hsh}', w, hgt, w < 700)
                try:
                    wait_list(page, timeout=20000)
                    now = api(f'/api/world?kind={kind}', f'http://127.0.0.1:{REAL_PORT}')
                    r = page.evaluate(LIST_JS, now)
                    b = r['bad']
                    ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    want = sum(len(g['items']) for g in now['groups'])
                    check(f'real Worker list {kind} {w}: rows, values = API, colours, nothing clipped', r['n'] == want and len(b['value'] + b['pct']) <= 2 and not (b['color'] or b['ink'] or b['clip']) and ov <= 0,
                          f"{r['n']}/{want} rows, overflow {ov}; " + '; '.join((b['value'] + b['pct'] + b['color'] + b['ink'] + b['clip'])[:3]))
                    page.screenshot(path=str(SHOTS / f'real_list_{kind}_{w}.png'), full_page=True)
                finally:
                    ctx.close()
    finally:
        if proc:
            proc.terminate()


def main():
    mock = None
    try:
        api('/__reset')
    except Exception:
        mock = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                api('/__reset'); break
            except Exception:
                time.sleep(0.25)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for kind in ('index', 'commodity'):
                for w, hgt in list(WIDTHS.items()) + [(1440, 900)]:
                    list_pass(browser, kind, w, hgt)
            toggle_pass(browser)
            sort_pass(browser)
            list_keyboard_pass(browser)
            list_palette_pass(browser)
            refresh_pass(browser)
            refresh_pass(browser, reduced=True)
            refresh_pass(browser, sort='pct')
            list_states_pass(browser)
            for w, hgt in list(WIDTHS.items()) + [(1440, 900)]:
                kind_pass(browser, 'commodity', w, hgt)
                geo_pass(browser, w, hgt)
            geo_click_pass(browser)
            ticker_detail_pass(browser)
            geo_keyboard_pass(browser)
            geo_fallback_pass(browser)
            geo_refresh_pass(browser)
            night_pass(browser)
            refresh_event_pass(browser)
            motion_setting_pass(browser)
            keyboard_pass(browser)
            palette_pass(browser)
            mobile_pass(browser)
            reduced_pass(browser)
            boot_pass(browser)
            polling_pass(browser)
            states_pass(browser)
            snapshot_pass(browser)
            if '--real' in sys.argv:
                real_pass(browser)
            browser.close()
        check('console errors: 0 (outside failure-mode tests)', not ERR.items, '; '.join(ERR.items[:4]))
    finally:
        if mock:
            mock.terminate()
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed; expected network errors in failure tests: {len(ERR.expected)}')
    (SHOTS / 'results.json').write_text(json.dumps([{'name': n, 'ok': o, 'detail': d} for n, o, d in results], ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
