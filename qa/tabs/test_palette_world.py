#!/usr/bin/env python3
"""등락 색상을 국내 · 해외 · 지표 따로 (사용자 2026-11-16 11:20) — QA on the built pages.

  python3 scripts/build_page.py && python3 qa/tabs/test_palette_world.py [--shots DIR]

Live checks start qa/world/mock_api.py on PALW_QA_PORT (default 9050; 9010–9089) with 환율 · 금리 on (it serves this worktree's
web/, /api/quotes from data/snapshot.json, /api/world from qa/world/fixtures, /api/market from qa/extras/fixtures) and serve d3 /
Pretendard / the world atlas from the repo. The stock page is checked on the snapshot (dist/index.html, no network).
What is checked:
  · 국내 krb + 해외 · 지표 global picked apart: map tiles · legend · 국내 text (krb), 해외 list chips · text · legend · world map
    countries (global), the ticker item by item (코스피 · 코스닥 = 국내, 환율 · 선물 · 원자재 · 가상자산 = 해외), the sheet the
    ticker opens (원/달러 = 해외, 코스피 = 국내), the summary card (간밤 미국 · 원/달러 · 환율 · 금리 = 해외, 지수 = 국내), the
    stock page (국내, also opened from the 해외 tab), the image save (palette asked per side, world tiles in 해외 colours)
  · the control: 국내 tabs 4 keys "색상", 해외 · 지표 5 keys "해외 · 지표 색" with 국내와 같게 first (the default)
  · 국내와 같게 follows the 국내 choice; reload keeps both; an old profile (khm.palette2 only) works as before; garbage → 국내와 같게
  · four themes × 360 · 1280: no horizontal overflow, the toolbar stays one row at 1280, the phone sheet fits; console errors 0
Screenshots go to --shots (default /tmp) as palw_*.png. Exit code 1 if any check fails.
"""
import argparse
import base64
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
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
SNAP = (ROOT / 'dist/index.html').as_uri()
PORT = int(os.environ.get('PALW_QA_PORT', 9050))
assert 9010 <= PORT <= 9089, 'ports 9010–9089 (default 9050)'
LIVE = f'http://127.0.0.1:{PORT}/'
VP = {360: 740, 390: 844, 1280: 800, 1440: 900}
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ATLAS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json'
ATLAS = (ROOT / 'qa/world/fixtures/countries-110m.json').read_bytes()
WFIX = {k: json.loads((ROOT / f'qa/world/fixtures/world_{k}.json').read_text(encoding='utf-8')) for k in ('index', 'commodity')}
RATIO = {it['key']: it['ratio'] for d in WFIX.values() for g in d['groups'] for it in g['items'] if it.get('ratio') is not None and not it.get('ref')}   # VIX: grey, no colour
GKEY = {it['key']: g['key'] for g in WFIX['commodity']['groups'] for it in g['items']}   # 지표 rows → their group (구역마다, AGENTS §3-27)
GEO = {'840': 'INX', '392': 'N225', '826': 'FTSE', '276': 'GDAXI', '156': 'SSEC', '076': 'BVSP'}

ap = argparse.ArgumentParser()
ap.add_argument('--shots', default=os.environ.get('PALW_SHOTS', '/tmp'))
ARGS = ap.parse_args()
SHOTS = pathlib.Path(ARGS.shots)
SHOTS.mkdir(parents=True, exist_ok=True)

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


D3 = (ROOT / 'src/vendor/d3-7.9.0.min.js').read_bytes()
FONT_CSS = ("@font-face{font-family:'Pretendard Variable';font-weight:45 920;font-style:normal;font-display:swap;src:url(data:font/woff2;base64,"
            + base64.b64encode((ROOT / 'src/fonts/PretendardVariable-subset.woff2').read_bytes()).decode() + ") format('woff2-variations')}").encode()


class Errors:
    def __init__(self):
        self.items = []

    def attach(self, page, tag):
        page.on('pageerror', lambda e: self.items.append(f'{tag} pageerror: {e}'))
        page.on('console', lambda m: self.items.append(f'{tag} console: {m.text[:160]}') if m.type == 'error' else None)


ERR = Errors()


def context(browser, w, live):
    opts = dict(viewport={'width': w, 'height': VP.get(w, 900)})
    if w <= 760:
        opts.update(is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx = browser.new_context(**opts)
    if live:
        hdr = {'access-control-allow-origin': '*'}
        ctx.route('https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js', lambda r: r.fulfill(status=200, body=D3, headers={**hdr, 'content-type': 'application/javascript'}))
        ctx.route('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@*/**', lambda r: r.fulfill(status=200, body=FONT_CSS, headers={**hdr, 'content-type': 'text/css'}))
        ctx.route(ATLAS_URL, lambda r: r.fulfill(status=200, body=ATLAS, headers={**hdr, 'content-type': 'application/json'}))
        ctx.route('**/api/time', lambda r: r.fulfill(status=200, body=json.dumps({'t': int(time.time() * 1000)}), headers={'content-type': 'application/json', 'cache-control': 'no-store'}))
    return ctx


def open_page(browser, w, url, storage=None, live=False, tag='', wait=1800, raw=None):
    ctx = context(browser, w, live)
    pg = ctx.new_page()
    ERR.attach(pg, tag or f'{w}')
    pg.goto(url)
    pg.evaluate("""s => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);
      for (const [k, v] of Object.entries(s.j || {})) localStorage.setItem(k, JSON.stringify(v));
      for (const [k, v] of Object.entries(s.r || {})) localStorage.setItem(k, v); }""", {'j': storage or {}, 'r': raw or {}})
    pg.reload()
    pg.wait_for_timeout(wait)
    return ctx, pg


def go(pg, mkt, wait=1200):
    pg.click(f'.tabs button[data-mkt="{mkt}"]')
    pg.wait_for_timeout(wait)


def press_palette(pg, v):
    # 1280+: the toolbar shows the control; below that it lives in the 표시 설정 sheet (open it, press, close)
    vis = pg.evaluate("() => { const b = document.querySelector('#palseg'); return !!(b && b.getClientRects().length && b.getBoundingClientRect().width); }")
    if not vis:
        pg.click('#setBtn')
        pg.wait_for_timeout(350)
    pg.click(f'#palseg button[data-v="{v}"]')
    pg.wait_for_timeout(350)
    if not vis:
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)


# ── in-page helpers: colours normalised by the browser, text colour per side ──
HELP = r"""() => {
  if (window.__pw) return;
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const dirOf = el => { const c = el.classList; return c.contains('up') || c.contains('xs-up') ? 'up' : c.contains('dn') || c.contains('xs-dn') ? 'dn' : null; };
  const txt = side => { const p = KH.palette(side); return { up: norm(p.upText), dn: norm(p.dnText) }; };
  // every element of sel with an up / dn class: its colour should be side's text colour, never the other side's
  const sideCheck = (sel, side) => {
    const want = txt(side), other = txt(side === 'world' ? 'kr' : 'world'), out = { ok: 0, wrong: [], other: 0 };
    for (const el of document.querySelectorAll(sel)) {
      const d = dirOf(el); if (!d || !el.getClientRects().length) continue;
      const got = getComputedStyle(el).color;
      if (got === want[d]) out.ok++;
      else if (got === other[d] && want[d] !== other[d]) out.wrong.push(`${el.className} ${(el.textContent || '').trim().slice(0, 14)} ${got}`);
      else out.other++;
    }
    return out;
  };
  window.__pw = { norm, txt, sideCheck };
}"""

STATE = """() => { const seg = document.querySelector('#palseg'), lbl = seg.closest('.ctl').querySelector(':scope > span');
  return { keys: [...seg.children].map(b => b.dataset.v), pressed: [...seg.children].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.v),
    label: lbl.innerText.trim(), aria: seg.getAttribute('aria-label'), pick: KH.palettePick(), kr: KH.palette().key, world: KH.palette('world').key,
    same: KH.palette('world').same, scope: KH.palScope(),
    store: { kr: localStorage.getItem('khm.palette2'), world: localStorage.getItem('khm.paletteW') } }; }"""

CHIPS = """() => { const out = { n: 0, bad: [], differ: 0 };
  for (const r of document.querySelectorAll('#world .kw-lr[data-k]')) {
    const chip = r.querySelector('.kw-pchip'); if (!chip) continue;
    const k = r.dataset.k, it = RATIO[k]; if (it == null) continue;
    // 구역마다 (AGENTS §3-27): the 지표 tab under 자동 colours each group on its own range (KHWorld.zones()); 해외 keeps the tab's
    const Z = window.KHWorld && KHWorld.zones ? KHWorld.zones() : null, z = Z && GKEY[k] ? Z[GKEY[k]] : null;
    const got = getComputedStyle(chip).backgroundColor, want = __pw.norm(z ? KH.colorOf(it, { scope: 'world', range: z.value }) : KH.colorOf(it, 'world')), kr = __pw.norm(KH.colorOf(it));
    out.n++; if (got !== want) out.bad.push(`${k} ${got} != ${want}`); if (want !== kr) out.differ++;
  }
  return out; }"""


def chips(pg):
    return pg.evaluate("([RATIO, GKEY]) => { window.RATIO = RATIO; window.GKEY = GKEY; return (" + CHIPS + ")(); }", [RATIO, GKEY])


def tiles_state(pg, side_key):
    # 국내 map tiles: the ends of the scale are clamped, so plenty of tiles carry the palette's end colours — the 국내 ones, never the 해외 ones
    return pg.evaluate("""k => { const P = KH.palette(), W = KH.palette('world');
      const n = c => __pw.norm(c), mine = new Set([n(P.stops[0]), n(P.stops[6])]), theirs = new Set([n(W.stops[0]), n(W.stops[6])]);
      let a = 0, b = 0, t = 0; for (const x of KH.layout()) { if (x.kind !== 'tile') continue; t++; const c = n(x.color); if (mine.has(c)) a++; if (theirs.has(c) && !mine.has(c)) b++; }
      return { tiles: t, ends: a, worldEnds: b, key: P.key }; }""", side_key)


def grad_has(pg, sel, side):
    return pg.evaluate("""([sel, side]) => { const g = document.querySelector(sel); if (!g) return null; const bg = getComputedStyle(g).backgroundImage;
      const P = KH.palette(side); return { lo: bg.includes(__pw.norm(P.stops[0])), hi: bg.includes(__pw.norm(P.stops[6])) }; }""", [sel, side])


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    proc = subprocess.Popen([sys.executable, str(ROOT / 'qa/world/mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            NOPROXY.open(LIVE + '__reset', timeout=1).read()
            NOPROXY.open(LIVE + '__mode?macro=on&funds=on', timeout=2).read()
            return proc
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise SystemExit(f'mock on :{PORT} did not start')


def live_split(b):
    # 1 · an old profile (khm.palette2 only): 국내 krb as before, 해외 · 지표 follow it (국내와 같게)
    ctx, pg = open_page(b, 1280, LIVE + '?summary_phase=pre', storage={'khm.palette2': 'krb'}, live=True, tag='split1280', wait=2600)
    pg.evaluate(HELP)
    s = pg.evaluate(STATE)
    check('old profile: 국내 keeps khm.palette2, 해외 · 지표 follow it', s['kr'] == 'krb' and s['world'] == 'krb' and s['same'] and s['pick'] == {'kr': 'krb', 'world': 'same'}
          and s['store']['world'] is None, json.dumps(s, ensure_ascii=False))
    check('국내 tab: four keys, "색상", krb pressed', s['keys'] == ['krg', 'krb', 'global', 'cvd'] and s['pressed'] == ['krb'] and s['label'] == '색상' and s['scope'] == 'kr',
          f"{s['keys']} {s['pressed']} {s['label']}")
    go(pg, 'WORLD', 2000)
    w = pg.evaluate(STATE)
    check('해외 tab: 국내와 같게 first and pressed, "해외 · 지표 색"', w['keys'] == ['same', 'krg', 'krb', 'global', 'cvd'] and w['pressed'] == ['same']
          and w['label'] == '해외 · 지표 색' and w['scope'] == 'world' and '해외' in (w['aria'] or ''), f"{w['keys']} {w['pressed']} {w['label']}")
    c = chips(pg)
    check('해외 list while following: chips = 국내 colours', c['n'] > 20 and not c['bad'] and c['differ'] == 0, f"{c['n']} chips, bad {c['bad'][:2]}")

    # 2 · pick 해외 · 지표 = global apart from 국내 = krb
    press_palette(pg, 'global')
    w = pg.evaluate(STATE)
    check('해외 tab: global picked, stored apart', w['pressed'] == ['global'] and w['store'] == {'kr': '"krb"', 'world': '"global"'} and w['kr'] == 'krb' and w['world'] == 'global',
          json.dumps(w['store']))
    c = chips(pg)
    check('해외 list: chips = KH.colorOf(r, "world") (global), not 국내', c['n'] > 20 and not c['bad'] and c['differ'] >= c['n'] // 2, f"{c['n']} chips, {c['differ']} differ from 국내, bad {c['bad'][:2]}")
    t = pg.evaluate("() => __pw.sideCheck('#world .up, #world .dn', 'world')")
    check('해외 list: up / down text in 해외 colours', t['ok'] >= 10 and not t['wrong'], json.dumps(t, ensure_ascii=False)[:200])
    g = grad_has(pg, '#world .kw-legend .grad', 'world')
    check('해외 legend: the 해외 palette', bool(g) and g['lo'] and g['hi'], json.dumps(g))
    lay = pg.evaluate("""() => { const L = (window.KHWorld && KHWorld.layout()) || []; let n = 0, bad = 0;
      for (const x of L) { if (x.kind !== 'tile' || !(x.code in RATIO) || x.code === 'VIX') continue; n++; if (__pw.norm(x.color) !== __pw.norm(KH.colorOf(RATIO[x.code], 'world'))) bad++; } return { n, bad }; }""")
    check('해외 image layout: tiles in 해외 colours', lay['n'] > 20 and lay['bad'] == 0, json.dumps(lay))
    pg.screenshot(path=str(SHOTS / 'palw_1280_world.png'), full_page=True)
    # the image save asks the palette of the side it saves
    calls = pg.evaluate("""async () => { const orig = KH.palette, got = []; KH.palette = s => { got.push(s === undefined ? 'none' : s); return orig(s); };
      try { document.querySelector('#extras-tools button[data-x="image"]').click(); await new Promise(r => setTimeout(r, 2500)); } finally { KH.palette = orig; }
      return got; }""")
    check('해외 image save: 해외 palette', 'world' in calls and 'kr' not in calls, str(calls))

    # 3 · 지표 tab: the same side (환율 · 금리 · 증시 자금 · 원자재)
    go(pg, 'CMDTY', 2000)
    m = pg.evaluate(STATE)
    c = chips(pg)
    t = pg.evaluate("() => __pw.sideCheck('#world .up, #world .dn', 'world')")
    check('지표 tab: same 해외 choice, chips and text in 해외 colours', m['pressed'] == ['global'] and m['label'] == '해외 · 지표 색' and c['n'] > 10 and not c['bad'] and not t['wrong'] and t['ok'] > 5,
          f"{m['pressed']} chips {c['n']} bad {c['bad'][:2]} text {t['ok']} wrong {t['wrong'][:2]}")

    # 4 · back on 국내: krb everywhere 국내, the ticker split per item, the summary card split per row
    go(pg, 'K', 2000)
    k = pg.evaluate(STATE)
    ts = tiles_state(pg, 'krb')
    check('국내 tab: krb pressed, label 색상', k['pressed'] == ['krb'] and k['label'] == '색상' and k['keys'] == ['krg', 'krb', 'global', 'cvd'], f"{k['pressed']} {k['label']}")
    check('국내 map tiles: 국내 end colours only', ts['tiles'] > 200 and ts['ends'] >= 5 and ts['worldEnds'] == 0, json.dumps(ts))
    g = grad_has(pg, '#legend .grad', 'kr')
    check('국내 legend: the 국내 palette', bool(g) and g['lo'] and g['hi'], json.dumps(g))
    t = pg.evaluate("() => __pw.sideCheck('main.layout .up, main.layout .dn, .tabs .up, .tabs .dn, #idx .up, #idx .dn', 'kr')")
    check('국내 text (map, side cards, tabs): 국내 colours', t['ok'] >= 10 and not t['wrong'], json.dumps(t, ensure_ascii=False)[:200])
    tk = pg.evaluate("""() => { const out = { kr: 0, world: 0, wrong: [] };
      for (const it of document.querySelectorAll('#strip .xs-item[data-k]')) {
        const k = it.dataset.k, side = /^(?:[mw]:)?KOS(PI|DAQ)$|^[sg]:/.test(k) ? 'kr' : 'world';
        const r = __pw.sideCheck(`#strip .xs-item[data-k="${CSS.escape(k)}"] :is(.xs-up, .xs-dn)`, side);
        out[side] += r.ok; if (r.wrong.length) out.wrong.push(k + ': ' + r.wrong[0]);
        if (it.classList.contains('pal-w') !== (side === 'world')) out.wrong.push(k + ' pal-w class');
      }
      return out; }""")
    check('ticker: 코스피 · 코스닥 국내, 환율 · 선물 · 원자재 · 비트코인 해외 colours', tk['kr'] >= 2 and tk['world'] >= 6 and not tk['wrong'], json.dumps(tk, ensure_ascii=False)[:240])
    # the summary card (?summary_phase=pre → 간밤 미국): open it and read its rows
    pg.evaluate("() => { const s = document.querySelector('.sm, #summary, [class*=\"sm-\"]'); if (s) s.scrollIntoView(); }")
    pg.wait_for_timeout(800)
    pg.evaluate("() => window.KHSummary && KHSummary.open()")
    try:
        pg.wait_for_selector('.sm-f-us .sm-n', timeout=6000)
    except Exception:
        pass
    pg.wait_for_timeout(600)
    sm = pg.evaluate("""() => ({ us: __pw.sideCheck('.sm-f-us .sm-n', 'world'), fx: __pw.sideCheck('.sm-f-fx .sm-n', 'world'), macro: __pw.sideCheck('.sm-sec.pal-w .sm-n', 'world'),
      idx: __pw.sideCheck('.sm-f-idx .sm-n, .sm-f-indUp .sm-n, .sm-f-indDn .sm-n', 'kr'), label: (document.querySelector('.sm-f-us dt') || {}).textContent || null })""")
    check('summary card: 간밤 미국 · 원/달러 · 환율 · 금리 in 해외 colours, 지수 · 업종 in 국내', sm['us']['ok'] >= 1 and sm['fx']['ok'] >= 1 and sm['macro']['ok'] >= 1 and sm['idx']['ok'] >= 1
          and not (sm['us']['wrong'] or sm['fx']['wrong'] or sm['macro']['wrong'] or sm['idx']['wrong']), json.dumps(sm, ensure_ascii=False)[:300])
    pg.screenshot(path=str(SHOTS / 'palw_1280_kospi.png'), full_page=True)
    pg.evaluate("() => window.KHSummary && KHSummary.close()")
    pg.evaluate('() => scrollTo(0, 0)')
    pg.wait_for_timeout(300)
    # the sheet the ticker opens: 원/달러 = 해외, 코스피 = 국내
    det = {}
    for key, side in (('USDKRW', 'world'), ('KOSPI', 'kr')):
        pg.evaluate("k => document.querySelector(`#strip .xs-item[data-k=\"${k}\"]`).click()", key)
        try:
            pg.wait_for_selector('.kw-sheet:not([hidden]) .kw-pc2', timeout=6000)
        except Exception:
            pass
        pg.wait_for_timeout(500)
        det[key] = pg.evaluate("""s => { const sh = document.querySelector('.kw-sheet'); if (!sh || sh.hidden) return null;
          return { palw: sh.classList.contains('pal-w'), r: __pw.sideCheck('.kw-sheet .up, .kw-sheet .dn', s) }; }""", side)
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(600)
    ok = det.get('USDKRW') and det['USDKRW']['palw'] and det['USDKRW']['r']['ok'] >= 1 and not det['USDKRW']['r']['wrong'] \
        and det.get('KOSPI') and not det['KOSPI']['palw'] and det['KOSPI']['r']['ok'] >= 1 and not det['KOSPI']['r']['wrong']
    check('ticker sheets: 원/달러 in 해외 colours, 코스피 in 국내', ok, json.dumps(det, ensure_ascii=False)[:300])
    calls = pg.evaluate("""async () => { const orig = KH.palette, got = []; KH.palette = s => { got.push(s === undefined ? 'none' : s); return orig(s); };
      try { document.querySelector('#extras-tools button[data-x="image"]').click(); await new Promise(r => setTimeout(r, 2500)); } finally { KH.palette = orig; }
      return got; }""")
    check('국내 image save: 국내 palette', 'kr' in calls and 'world' not in calls, str(calls))
    wc = pg.evaluate("() => { const el = document.getElementById('xwc'); return el ? el.classList.contains('pal-w') : 'not built'; }")
    check('world clock box is a 해외 box (or not built yet)', wc in (True, 'not built'), str(wc))

    # 5 · 국내와 같게 follows 국내
    go(pg, 'WORLD', 1800)
    press_palette(pg, 'same')
    a = pg.evaluate(STATE)
    go(pg, 'K', 1200)
    press_palette(pg, 'cvd')
    bk = pg.evaluate(STATE)
    tk = pg.evaluate("() => __pw.sideCheck('#strip .pal-w :is(.xs-up, .xs-dn)', 'world')")
    go(pg, 'WORLD', 1800)
    c2 = pg.evaluate(STATE)
    c = chips(pg)
    sw = pg.evaluate("""() => { const b = document.querySelector('#palseg button[data-v="same"] .pal b:last-child'); return b ? getComputedStyle(b).backgroundColor : null; }""")
    cvd_hi = pg.evaluate("() => __pw.norm(KH.palette().stops[6])")
    check('국내와 같게 follows 국내 (cvd): stored "same", chips = 국내 colours, its swatch shows cvd', a['store']['world'] == '"same"' and bk['kr'] == 'cvd' and bk['world'] == 'cvd'
          and c2['pressed'] == ['same'] and c2['world'] == 'cvd' and c['n'] > 20 and not c['bad'] and c['differ'] == 0 and sw == cvd_hi and tk['ok'] >= 4 and not tk['wrong'],
          f"store {a['store']} · world {c2['world']} · chips {c['n']}/{c['differ']} · swatch {sw} vs {cvd_hi} · ticker {tk['ok']}")
    ctx.close()

    # 6 · reload keeps both; a garbage 해외 value is 국내와 같게
    ctx, pg = open_page(b, 1280, LIVE, storage={'khm.palette2': 'krb', 'khm.paletteW': 'global'}, live=True, tag='reload1280', wait=2200)
    pg.evaluate(HELP)
    r1 = pg.evaluate(STATE)
    pg.reload()
    pg.wait_for_timeout(2000)
    r2 = pg.evaluate(STATE)
    go(pg, 'WORLD', 1800)
    pg.evaluate(HELP)
    r3 = pg.evaluate(STATE)
    c = chips(pg)
    check('reload: both sides remembered', r1['pick'] == r2['pick'] == {'kr': 'krb', 'world': 'global'} and r3['pressed'] == ['global'] and not c['bad'] and c['differ'] > 0,
          f"{r2['pick']} {r3['pressed']} chips bad {len(c['bad'])}")
    ctx.close()
    ctx, pg = open_page(b, 1280, LIVE + '#world', storage={'khm.palette2': 'krg', 'khm.paletteW': 'zzz'}, live=True, tag='garbage1280', wait=2200)
    g = pg.evaluate(STATE)
    check('garbage khm.paletteW → 국내와 같게', g['pick']['world'] == 'same' and g['world'] == 'krg' and g['pressed'] == ['same'], json.dumps(g['pick']))
    ctx.close()

    # 7 · the world map (지도 view): countries in 해외 colours
    ctx, pg = open_page(b, 1440, LIVE + '#world', storage={'khm.palette2': 'krb', 'khm.paletteW': 'global'}, raw={'khm.worldView': 'map'}, live=True, tag='geo1440', wait=2600)
    pg.evaluate(HELP)
    try:
        pg.wait_for_selector('#world .kw-geo:not([hidden]) .kw-gsvg', timeout=12000)
    except Exception:
        pass
    pg.wait_for_timeout(800)
    geo = pg.evaluate("""([rep, R]) => { const out = { n: 0, bad: [], differ: 0 };
      for (const [id, k] of Object.entries(rep)) { const el = document.querySelector(`#world .kw-cp[data-c="${id}"]`) || document.querySelector(`#world .kw-gmk[data-c="${id}"]`);
        if (!el || R[k] == null) continue; out.n++;
        const got = __pw.norm(getComputedStyle(el).fill), want = __pw.norm(KH.colorOf(R[k], 'world')), kr = __pw.norm(KH.colorOf(R[k]));
        if (got !== want) out.bad.push(`${id} ${got} != ${want}`); if (want !== kr) out.differ++; }
      return out; }""", [GEO, RATIO])
    check('world map: countries in 해외 colours (global), not 국내', geo['n'] >= 5 and not geo['bad'] and geo['differ'] >= 3, json.dumps(geo))
    pg.screenshot(path=str(SHOTS / 'palw_1440_geo.png'))
    ctx.close()


def snapshot_stock(b):
    # the stock page is a 국내 value: 국내 colours on a 국내 tab and when opened from the 해외 tab
    ctx, pg = open_page(b, 1280, SNAP, storage={'khm.palette2': 'krb', 'khm.paletteW': 'global'}, tag='snapstock')
    pg.evaluate(HELP)
    out = {}
    for mkt in ('K', 'WORLD'):
        go(pg, mkt, 900)
        pg.evaluate("() => window.KHStock && KHStock.open('005930')")
        try:
            pg.wait_for_selector('.sp-chg.up, .sp-chg.dn', timeout=6000)
        except Exception:
            pass
        pg.wait_for_timeout(500)
        out[mkt] = pg.evaluate("() => ({ chg: __pw.sideCheck('.sp-chg', 'kr'), all: __pw.sideCheck('.sp-page .up, .sp-page .dn, .sp .up, .sp .dn', 'kr'), key: KH.palette().key })")
        pg.evaluate("() => window.KHStock && KHStock.close()")
        pg.wait_for_timeout(500)
    ok = all(v['chg']['ok'] >= 1 and not v['chg']['wrong'] and not v['all']['wrong'] and v['key'] == 'krb' for v in out.values())
    check('stock page: 국내 colours (from 코스피 and from 해외)', ok, json.dumps(out, ensure_ascii=False)[:300])
    ctx.close()


def theme_checks(b):
    # four themes × 360 · 1280: no overflow on 국내 and 해외, 1280 toolbar one row, the phone sheet's 5 keys fit (국내와 같게 a full row)
    for th in THEMES:
        for w in (1280, 360):
            ctx, pg = open_page(b, w, LIVE, storage={'khm.theme': th, 'khm.palette2': 'krb', 'khm.paletteW': 'global'}, live=True, tag=f'{th}{w}', wait=2200)
            pg.evaluate(HELP)
            k = pg.evaluate("() => ({ ov: document.documentElement.scrollWidth - innerWidth, tools: Math.round(document.querySelector('.tools').getBoundingClientRect().height), theme: document.documentElement.dataset.theme })")
            if w < 1280:
                pg.click('#setBtn')
                pg.wait_for_timeout(450)
                ks = pg.evaluate("""() => { const s = document.querySelector('#palseg'), lbl = s.closest('.ctl').querySelector(':scope > span');
                  return { n: s.children.length, lbl: lbl.innerText.trim(), sw: s.scrollWidth, cw: s.clientWidth, right: Math.round(s.getBoundingClientRect().right), vw: innerWidth }; }""")
                check(f'theme {th} {w}: 국내 sheet row says "국내 색상", four keys fit', ks['n'] == 4 and ks['lbl'] == '국내 색상' and ks['sw'] <= ks['cw'] + 1 and ks['right'] <= ks['vw'], json.dumps(ks, ensure_ascii=False))
                pg.keyboard.press('Escape')
                pg.wait_for_timeout(300)
            go(pg, 'WORLD', 1800)
            wv = pg.evaluate("() => ({ ov: document.documentElement.scrollWidth - innerWidth, tools: Math.round(document.querySelector('.tools').getBoundingClientRect().height) })")
            c = chips(pg)
            t = pg.evaluate("() => __pw.sideCheck('#world .up, #world .dn', 'world')")
            ok = k['theme'] == th and k['ov'] == 0 and wv['ov'] == 0 and not c['bad'] and c['differ'] > 0 and not t['wrong'] and (w < 1280 or (k['tools'] <= 48 and wv['tools'] <= 48))
            check(f'theme {th} {w}: no overflow (국내 · 해외), 해외 colours right' + (', toolbar one row' if w >= 1280 else ''), ok,
                  f"ov {k['ov']}/{wv['ov']} tools {k['tools']}/{wv['tools']} chips {c['n']} bad {len(c['bad'])} wrong {len(t['wrong'])}")
            if w == 1280:
                pg.screenshot(path=str(SHOTS / f'palw_{th}_1280_world.png'))
            else:
                pg.evaluate('() => scrollTo(0, 0)')
                pg.click('#setBtn')
                pg.wait_for_timeout(450)
                sh = pg.evaluate("""() => { const s = document.querySelector('#palseg'), r = s.getBoundingClientRect(), same = s.querySelector('[data-v="same"]').getBoundingClientRect();
                  const lbl = s.closest('.ctl').querySelector(':scope > span').textContent;
                  return { n: s.children.length, w: Math.round(r.width), sameW: Math.round(same.width), sw: s.scrollWidth, cw: s.clientWidth, right: Math.round(r.right), vw: innerWidth,
                    h: Math.min(...[...s.children].map(b => b.getBoundingClientRect().height)), lbl, cut: [...s.querySelectorAll('.pl, .pls')].filter(x => x.scrollWidth > x.clientWidth + 1).length,
                    ov: document.documentElement.scrollWidth - innerWidth }; }""")
                pg.screenshot(path=str(SHOTS / f'palw_{th}_360_sheet.png'))
                ok = sh['n'] == 5 and sh['sameW'] >= sh['w'] - 12 and sh['sw'] <= sh['cw'] + 1 and sh['right'] <= sh['vw'] and sh['h'] >= 32 and sh['cut'] == 0 and sh['ov'] == 0 and sh['lbl'] == '해외 · 지표 색'
                check(f'theme {th} 360: 표시 설정 sheet — five keys fit, 국내와 같게 a full row', ok, json.dumps(sh, ensure_ascii=False))
                pg.keyboard.press('Escape')
                pg.wait_for_timeout(300)
            ctx.close()


def main():
    proc = start_mock()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            live_split(b)
            snapshot_stock(b)
            theme_checks(b)
            b.close()
    finally:
        proc.kill()
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check('no console errors', not ERR.items, '; '.join(ERR.items[:6]))
    bad = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed · screenshots in {SHOTS}/palw_*.png')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
