#!/usr/bin/env python3
"""The template on the design standard (roadmap 6, step template — ux/std-template; design.md §2 · §3 · §4 · §6, AGENTS §3-31 · §3-36).

  python3 qa/std_template/test_std_template.py [audit] [page] [cap]       (no argument = all three)

audit  static, src/template.html's <style>: no radial gradient; a linear gradient only where it draws data or a shape (the legend scale,
       no-data / no-NXT hatches, the folded 공시 corner, the tab row's overflow mask); no glow (no zero-offset blurred box-shadow, no
       drop-shadow(), text halos only behind map labels / the crumbs over the index line); status rules (live · err · fail · stale) never
       read the amber; --live and --fail-dot are defined for every theme and none of them is amber.
page   the live build (web/) behind qa/float/mock_float.py on STD_QA_PORT (default 9020; 9020–9029 only): four themes × 390 · 768 · 1280 ·
       1440 — map top (390 247 · 768 250 · 1280+ 207), no element wider than the screen, console errors 0; --live / --fail-dot computed
       per theme (≥ 30° of hue from the amber and the new-filing blue, ≥ 3:1 on the page); the live dot and the 실시간 badge in --live;
       the error "!" in --fail-dot; a tick flash is a flat ring (no blur).
cap    시총순 지도 (AGENTS §3-36): the 묶음 option only on 코스피 · 코스닥 · 전체 (표시 설정 sheet < 1280, 화면 popover ≥ 1280), saved as
       khm.groupBy; in 시총순 no sector / industry node (DOM and KH.layout()), the first tiles in reading order have the biggest caps
       (and keep the cap order when 크기 = 거래대금), labels inside their tiles, search highlight · tooltip · quick view work, no
       overflow, the image save draws (extras), back to 섹터별; console errors 0.
Exit 1 on a fail. Ports are stopped with fuser -k.
"""
import colorsys
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('STD_QA_PORT', 9020))
assert 9020 <= PORT <= 9029, 'ports 9020–9029'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
FAILS, PASSES, ERRS = [], [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'))


# ───────────────────────── audit (static) ─────────────────────────
def css_rules(css):
    """(selector, body) for every rule, @media / @supports blocks flattened; comments dropped"""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out, stack, buf = [], [], ''
    i = 0
    while i < len(css):
        ch = css[i]
        if ch == '{':
            stack.append(buf.strip()); buf = ''
        elif ch == '}':
            sel = stack.pop() if stack else ''
            if buf.strip() and not sel.startswith('@'):
                out.append((sel, buf.strip()))
            buf = ''
        else:
            buf += ch
        i += 1
    return out


GRAD_OK = [   # selector (substring) → why a gradient is fine there
    ('.tile.nod', 'no-data hatch'), ('.tile.nonx', 'no-NXT hatch'), ('.legend .nxsw', 'legend hatch swatch'), ('.legend .nodsw', 'legend hatch swatch'),
    ('.tile .dm', 'the folded 공시 corner (a hard-stop diagonal = a shape)'), ('.dmsw::after', 'the corner swatch'),
    ('.tabs-sc.more-r', 'the tab row overflow mask (a mask, not paint)'),
    ('.rc', 'the number drum\'s 14 % fade (a mask, not paint — design.md §6-2 P10)'),
]
HALO_OK = ['.tile .lab', '.stagebar.ix-bg .crumbs']   # dark text halos: legibility over data (tile colours · the index line)
STATUS_SEL = re.compile(r'\.status\.(live|err)|\.err\b|stale|\[data-st="fail"\]|\.kwn|\.fail')
AMBER = re.compile(r'var\(--(acc|acc-fill|acc-line|acc-soft|acc-bd|amber|amber-soft)\)|#ffb547|255,\s*181,\s*71')


def audit():
    src = (ROOT / 'src/template.html').read_text(encoding='utf-8')
    css = src[src.index('<style>') + 7:src.index('</style>')]
    rules = css_rules(css)
    check('audit: no radial-gradient in the template CSS', 'radial-gradient' not in css)
    bad = []
    for sel, body in rules:
        if 'gradient(' not in body:
            continue
        if any(k in sel for k, _ in GRAD_OK):
            continue
        bad.append(sel[:80])
    check('audit: linear gradients only on the allow-list (data scale, hatches, 공시 corner, overflow · drum masks)', not bad, bad)
    js_grad = [m.group(0)[:90] for m in re.finditer(r'[^\n]*gradient\([^\n]*', src[src.index('</style>'):]) if 'legend' not in m.group(0) and "class: 'grad'" not in m.group(0)]
    check('audit: the script draws no gradient but the legend colour scale', not js_grad, js_grad)
    glow = []
    for sel, body in rules:
        for prop, val in re.findall(r'(box-shadow|--[\w-]*sh[\w-]*|text-shadow|filter|--lab-sh[\w-]*)\s*:\s*([^;]+)', body):
            if 'drop-shadow(' in val:
                glow.append((sel[:60], prop, 'drop-shadow'))
            if prop == 'text-shadow' or prop.startswith('--lab-sh'):
                if any(k in sel for k in HALO_OK) or prop.startswith('--lab-sh') or val.strip() in ('none', 'var(--lab-sh)', 'var(--lab-sh-sm)'):
                    continue
                glow.append((sel[:60], prop, val[:60]))
                continue
            for part in re.split(r',(?![^(]*\))', val):
                m = re.match(r'\s*(inset\s+)?(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)px', part)
                if m and float(m.group(2)) == 0 and float(m.group(3)) == 0 and float(m.group(4)) > 0:
                    glow.append((sel[:60], prop, part.strip()[:60]))
    check('audit: no glow — no zero-offset blurred shadow, no drop-shadow()', not glow, glow)
    amb = [(sel[:70], body[:80]) for sel, body in rules if STATUS_SEL.search(sel) and AMBER.search(body) and not sel.startswith('.status.replay')]
    check('audit: status rules (live · err · fail · stale) never read the amber', not amb, amb)
    toks = {}
    for sel, body in rules:
        for k, v in re.findall(r'(--live|--fail-dot)\s*:\s*([^;]+)', body):
            toks.setdefault(k, []).append((sel, v.strip()))
    for k in ('--live', '--fail-dot'):
        vals = toks.get(k, [])
        check(f'audit: {k} defined, never amber ({len(vals)} definitions)', vals and not any(AMBER.search(v) for _, v in vals), vals)
    lv = {sel for sel, _ in toks.get('--live', [])}
    check('audit: --live has a value for 기본 · 신문 · 글라스 어둡게 · 글라스 밝게',
          ':root' in lv and any('paper' in x for x in lv) and any('glass-dark' in x for x in lv) and any('glass-light' in x for x in lv), lv)


# ───────────────────────── page ─────────────────────────
def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w, h, theme='base', motion='standard', market='K', extra=None, wait=2200):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{market}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_timeout(wait)
    return ctx, pg


# elements drawn past the screen's right edge (the page clips at the root, so scrollWidth no longer shows it — as qa/float's overflow_net)
OVER = r"""() => {
  const vw = innerWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break; } p = p.parentElement; }
    if (!clipped && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).position !== 'fixed') out.push((e.id ? '#' + e.id : e.className && e.className.baseVal == null ? '.' + String(e.className).split(' ')[0] : e.tagName) + ' ' + Math.round(r.right));
  }
  return out.slice(0, 8);
}"""

TOKENS = r"""() => {
  const cs = getComputedStyle(document.documentElement), probe = document.createElement('i');
  document.body.append(probe);
  const rgb = v => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const out = { live: rgb(cs.getPropertyValue('--live').trim()), fail: rgb(cs.getPropertyValue('--fail-dot').trim()), acc: rgb(cs.getPropertyValue('--acc-fill').trim()),
    nd: rgb(cs.getPropertyValue('--new-dot').trim()), page: getComputedStyle(document.body).backgroundColor };
  probe.remove();
  return out;
}"""


def parse_rgb(s):
    v = [float(x) for x in re.findall(r'[\d.]+', s)[:3]]
    return [x / 255 for x in v]


def hue(c):
    h, l, s = colorsys.rgb_to_hls(*c)
    return h * 360, s


def lum(c):
    f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hdist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def page(br):
    for theme in THEMES:
        for w, h, top in ((390, 844, 247), (768, 1024, 250), (1280, 800, 207), (1440, 900, 207)):
            ctx, pg = open_page(br, w, h, theme=theme)
            g = pg.evaluate("() => ({ map: Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY), tiles: document.querySelectorAll('#map .tile').length })")
            ov = pg.evaluate(OVER)
            check(f'page [{w} {theme}]: map top {g["map"]} (= {top}), {g["tiles"]} tiles, nothing past the screen edge', g['map'] == top and g['tiles'] > 50 and not ov, (g, ov))
            if w == 1440:
                t = pg.evaluate(TOKENS)
                live, fail, acc, nd, pgc = (parse_rgb(t[k]) for k in ('live', 'fail', 'acc', 'nd', 'page'))
                hl, hs = hue(live)
                check(f'page [{theme}]: --live {t["live"]} — ≥ 30° from the amber and the new-filing blue, saturated, ≥ 4.5:1 on the page (extras writes the countdown in it)',
                      hdist(hl, hue(acc)[0]) >= 30 and hdist(hl, hue(nd)[0]) >= 30 and hs > .3 and contrast(live, pgc) >= 4.5, (round(hl), round(hue(acc)[0]), round(hue(nd)[0]), round(contrast(live, pgc), 2)))
                check(f'page [{theme}]: --fail-dot {t["fail"]} — not amber, ≥ 4.5:1 on the page', t['fail'] != t['acc'] and contrast(fail, pgc) >= 4.5, round(contrast(fail, pgc), 2))
                # the status: live (a live answer during the session is the mock's — force the classes the code sets) and error
                st = pg.evaluate("""() => { const s = document.getElementById('status'), d = s.querySelector('.dot'), b = s.querySelector('.badge');
                  s.classList.add('live'); s.classList.remove('err', 'replay', 'has-basis', 'has-blab'); if (!b.textContent) b.textContent = '실시간';
                  const live = { dot: getComputedStyle(d).backgroundColor, badge: getComputedStyle(b).color, sh: getComputedStyle(d).boxShadow };
                  s.classList.remove('live'); s.classList.add('err');
                  const err = { bg: getComputedStyle(d).backgroundColor, mark: getComputedStyle(d, '::after').content, col: getComputedStyle(d, '::after').color };
                  s.classList.remove('err'); return { live, err }; }""")
                check(f'page [{theme}]: live dot and 실시간 badge in --live (no glow ring), error dot = "!" in --fail-dot',
                      st['live']['dot'] == t['live'] and st['live']['badge'] == t['live'] and st['live']['sh'] in ('none', '') and st['err']['mark'] == '"!"' and st['err']['col'] == t['fail'], st)
                fl = pg.evaluate("""() => { const el = document.querySelector('#map .tile'); el.classList.add('flash-up'); const a = getComputedStyle(el, '::after').boxShadow; el.classList.remove('flash-up');
                  el.classList.add('fl-d'); const b = getComputedStyle(el, '::after').boxShadow; el.classList.remove('fl-d'); return [a, b]; }""")
                check(f'page [{theme}]: tick flash = a flat 2px ring (기본 · 화려하게), no blur', all(re.fullmatch(r'rgb\([^)]*\) 0px 0px 0px 2px inset', x) for x in fl), fl)
            ctx.close()
    motion(br)


MOTION_JS = r"""async () => {
  const out = {};
  const box = document.createElement('span'); box.style.cssText = 'position:fixed;left:10px;top:300px;font-size:13px;line-height:16px'; document.body.append(box);
  // KH.ui.swap: a label goes up; a value that rose comes in from below, one that fell from above (§6-4 · P9)
  const sw = dir => { box.textContent = 'A'; KH.ui.swap(box, 'B', 'A', dir); const an = box.getAnimations({ subtree: true });
    const kf = an.map(a => a.effect.getKeyframes()); return { cls: box.className, was: box.dataset.was, n: an.length, out: kf[0] && kf[0][1].transform, inn: kf[1] && kf[1][0].transform, blur: kf[0] && kf[0][1].filter,
      dur: an.map(a => a.effect.getTiming().duration), delay: an.map(a => a.effect.getTiming().delay), text: box.textContent }; };
  out.up = sw(1); out.dn = sw(-1); out.label = sw();
  // KH.ui.roll (화려하게): changed digits only, the rightmost first 40 ms apart, the short way, a 14 % fade mask
  box.textContent = '12.19'; KH.ui.roll(box, '12.20', 1);
  const cols = [...box.querySelectorAll('.rc')];
  out.roll = { drums: cols.length, delays: cols.map(c => c.firstChild.getAnimations()[0].effect.getTiming().delay), mask: getComputedStyle(cols[0]).webkitMaskImage || getComputedStyle(cols[0]).maskImage,
    text: box.textContent, steps: cols.map(c => (c.firstChild.dataset.b || c.firstChild.dataset.a || '').split('\n').length) };
  box.textContent = '0.9'; KH.ui.roll(box, '0.0', 1);
  out.short = (box.querySelector('.rs') || {}).dataset ? Object.assign({}, box.querySelector('.rs').dataset) : null;
  box.remove();
  // the shared icons: ✓ and ! drawn 1.75px on screen
  const ic = ['check', 'warn'].map(n => { const e = KH.ui.icon(n); return [...e.querySelectorAll('path,circle')].map(x => [x.getAttribute('stroke-width') || e.getAttribute('stroke-width'), x.getAttribute('vector-effect')]); });
  out.icons = ic;
  // tab %: new quotes move the 코스피 number in place, the way it went (no digit roll)
  const q = await (await fetch('/api/quotes')).json(), tp = document.querySelector('.tabs button[data-mkt="K"] .tp'), was = tp.textContent;
  q.index.KOSPI.ratio = +q.index.KOSPI.ratio + 0.5; q.index.KOSPI.value = +q.index.KOSPI.value * 1.005; q.asOf = new Date(Date.now() + 60000).toISOString();
  const fed = KH.feed(q);
  await new Promise(r => setTimeout(r, 30));
  const an = tp.getAnimations({ subtree: true });
  out.tab = { fed, was, now: tp.textContent, cls: tp.className, n: an.length, drums: tp.querySelectorAll('.rc').length, inn: an[1] && an[1].effect.getKeyframes()[0].transform };
  return out;
}"""


def motion(br):
    ctx, pg = open_page(br, 1440, 900, motion='fancy')
    m = pg.evaluate(MOTION_JS)
    up, dn, lb = m['up'], m['dn'], m['label']
    check('motion: KH.ui.swap = out 100 ms (blur, 4px) → in 180 ms 60 ms later; rose → from below, fell → from above, a label goes up',
          up['n'] == 2 and up['dur'] == [100, 180] and up['delay'] == [0, 60] and 'blur' in (up['blur'] or '') and up['inn'] == 'translateY(4px)' and up['out'] == 'translateY(-4px)'
          and dn['inn'] == 'translateY(-4px)' and dn['out'] == 'translateY(4px)' and lb['inn'] == 'translateY(4px)' and up['text'] == 'B', m)
    r = m['roll']
    check('motion: KH.ui.roll (화려하게) — changed digits only, the rightmost first (40 ms apart), a 14 % fade mask, the text = the value',
          r['drums'] == 2 and r['delays'] == [40, 0] and '14%' in (r['mask'] or '') and r['text'] == '12.20', r)
    check('motion: KH.ui.roll goes the short way (9 → 0 is one step forward)', m['short'] == {'b': '9'}, m['short'])
    check('motion: the ✓ and ! icons are drawn 1.75px on screen (non-scaling strokes)', all(w == '1.75' and v == 'non-scaling-stroke' for ic in m['icons'] for w, v in ic), m['icons'])
    t = m['tab']
    check('motion: new quotes swap the 코스피 tab % in place, from below when it rose — no digit drum', t['fed'] and t['was'] != t['now'] and 'sw-go' in t['cls'] and t['drums'] == 0 and t['inn'] == 'translateY(4px)', t)
    ctx.close()


# ───────────────────────── 시총순 ─────────────────────────
def run(parts):
    if 'audit' in parts:
        audit()
    if parts & {'page', 'cap'}:
        from playwright.sync_api import sync_playwright
        start_mock()
        try:
            with sync_playwright() as p:
                br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
                if 'page' in parts:
                    page(br)
                if 'cap' in parts:
                    cap(br)
                br.close()
        finally:
            subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
        check(f'console errors: {len(ERRS)}', not ERRS, ERRS[:6])


CAPSTATE = r"""() => {
  const tiles = [...document.querySelectorAll('#map .tile')].filter(t => !t.classList.contains('leaving') && t.offsetWidth > 0);
  const boxes = tiles.map(t => ({ c: t.dataset.c, x: t.offsetLeft, y: t.offsetTop, w: t.offsetWidth, h: t.offsetHeight }));
  // reading order: rows by top edge, then left to right (strips share their top edge)
  const read = boxes.slice().sort((a, b) => a.y - b.y || a.x - b.x).map(b => b.c);
  const cap = c => (KH.stock(c) || {}).cap || 0;
  const byCap = boxes.map(b => b.c).sort((a, b) => cap(b) - cap(a) || (a < b ? -1 : 1));
  let inv = 0; for (let i = 1; i < read.length; i++) if (cap(read[i]) > cap(read[i - 1])) inv++;
  const lay = KH.layout();
  const bad = [];
  for (const t of tiles) { const l = t.querySelector('.lab'); if (!l || l.hidden) continue; const a = t.getBoundingClientRect(), b = l.getBoundingClientRect();
    if (b.left < a.left - .5 || b.right > a.right + .5 || b.top < a.top - .5 || b.bottom > a.bottom + .5) bad.push(t.dataset.c); }
  return { n: tiles.length, codes: KH.mapCodes().length, read: read.slice(0, 20), byCap: byCap.slice(0, 20), inv, secs: document.querySelectorAll('#map .node.sec, #map .node.ind').length,
    laySec: lay.filter(n => n.kind !== 'tile').length, layTiles: lay.filter(n => n.kind === 'tile').length, overflow: bad.slice(0, 5),
    store: localStorage.getItem('khm.groupBy'), aria: document.getElementById('map').getAttribute('aria-label'), hint: (document.querySelector('#crumbs .hint') || {}).textContent || '' };
}"""

GBROW = r"""() => { const r = document.querySelector('.ctl[data-ctl="groupBy"]'); if (!r) return null;
  const cs = getComputedStyle(r), box = r.getBoundingClientRect();
  return { hidden: r.hidden, shown: cs.display !== 'none' && box.width > 0 && box.height > 0 && !r.closest('.set-empty'), inMore: !!r.closest('#morePanel'), inCtls: !!r.closest('#ctls'),
    pressed: [...r.querySelectorAll('button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.v), labels: [...r.querySelectorAll('button')].map(b => b.textContent) }; }"""


def cap(br):
    # ── the option: 코스피 · 코스닥 · 전체 only; 표시 설정 sheet < 1280 (after 크기), 화면 popover ≥ 1280 ──
    for w, h in ((390, 844), (1000, 900), (1440, 900)):
        ctx, pg = open_page(br, w, h, market='K')
        seen = {}
        for m in ('K', 'Q', 'ALL', 'THEME', 'WORLD', 'CMDTY', 'CAL', 'WATCH'):
            pg.evaluate(f"document.querySelector('.tabs button[data-mkt=\"{m}\"]').click()"); pg.wait_for_timeout(500)
            opener = '#moreBtn' if w >= 1280 else '#setBtn'
            pg.click(opener); pg.wait_for_timeout(500)
            seen[m] = pg.evaluate(GBROW)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(350)
        want = {m: m in ('K', 'Q', 'ALL') for m in seen}
        got = {m: bool(x and x['shown']) for m, x in seen.items()}
        where = {m: (x['inMore'], x['inCtls']) for m, x in seen.items() if x}
        place_ok = all(v[0] for v in where.values()) if w >= 1280 else all(v[1] and not v[0] for v in where.values())
        check(f'cap [{w}]: 묶음 shown on 코스피 · 코스닥 · 전체 only, {"in the 화면 popover" if w >= 1280 else "in the 표시 설정 sheet"}; 섹터별 · 시총순, 섹터별 pressed',
              got == want and place_ok and seen['K']['labels'] == ['섹터별', '시총순'] and seen['K']['pressed'] == ['sector'], (got, where, seen['K']))
        ctx.close()
    # ── 시총순 on 코스피 (1440, 300 tiles) ──
    ctx, pg = open_page(br, 1440, 900, market='K')
    before = pg.evaluate(CAPSTATE)
    pg.click('#moreBtn'); pg.wait_for_timeout(400)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="cap"]'); pg.wait_for_timeout(100)
    mid = pg.evaluate("() => [...document.querySelectorAll('#map .tile')].filter(t => t.getAnimations().length).length")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(900)
    st = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: 시총순 pressed → saved khm.groupBy "cap", no sector / industry node in the map or KH.layout(), the same tiles',
          st['store'] == '"cap"' and st['secs'] == 0 and st['laySec'] == 0 and st['layTiles'] == st['n'] == before['codes'] == st['codes'] and before['secs'] > 0, (st['store'], st['secs'], st['laySec'], st['n'], before['codes']))
    check('cap [1440 K]: the tiles moved to their new boxes (FLIP, as a zoom)', mid > 100, mid)
    check('cap [1440 K]: reading order = market-cap order (first 20 exact, no inversion anywhere)', st['read'] == st['byCap'] and st['inv'] == 0, (st['read'][:8], st['byCap'][:8], st['inv']))
    check('cap [1440 K]: labels inside their tiles; map named "시가총액이 큰 종목부터"; the crumbs hint says so',
          not st['overflow'] and '시가총액이 큰 종목부터' in st['aria'] and '시가총액이 큰' in st['hint'], (st['overflow'], st['aria'], st['hint']))
    pg.screenshot(path=str(ROOT / 'qa/shots/std_template/cap_1440_K.png'))
    # 크기 = 거래대금: sized by trading value, still in cap order
    pg.evaluate("document.querySelector('.seg[data-key=\"sizeBy\"] button[data-v=\"tv\"]').click()"); pg.wait_for_timeout(900)
    st2 = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: 크기 = 거래대금 — still read in cap order (sizes by trading value)', st2['read'] == st2['byCap'] and st2['inv'] == 0 and not st2['overflow'], (st2['read'][:6], st2['inv']))
    pg.screenshot(path=str(ROOT / 'qa/shots/std_template/cap_1440_K_tv.png'))
    pg.evaluate("document.querySelector('.seg[data-key=\"sizeBy\"] button[data-v=\"cap\"]').click()"); pg.wait_for_timeout(700)
    # search highlight · tooltip · quick view · disclosure marks · image save
    pg.fill('#q', '삼성'); pg.wait_for_timeout(500)
    hl = pg.evaluate("() => { const t = [...document.querySelectorAll('#map .tile')]; return { dim: t.filter(x => x.classList.contains('dim')).length, lit: t.filter(x => !x.classList.contains('dim')).map(x => KH.stock(x.dataset.c).n) }; }")
    check('cap [1440 K]: search highlight — only the 삼성 tiles stay lit', hl['dim'] > 200 and hl['lit'] and all('삼성' in n for n in hl['lit']), (hl['dim'], hl['lit'][:5]))
    pg.fill('#q', ''); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    box = pg.evaluate("(() => { const t = document.querySelector('#map .tile'); const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, t.dataset.c]; })()")
    pg.mouse.move(box[0], box[1]); pg.wait_for_timeout(600)
    tip = pg.evaluate("() => { const t = document.getElementById('tip'); return { on: getComputedStyle(t).opacity > 0.5, txt: t.textContent.slice(0, 40) }; }")
    name = pg.evaluate(f"KH.stock('{box[2]}').n")
    check(f'cap [1440 K]: tooltip on the biggest tile ({name})', tip['on'] and name in tip['txt'], tip)
    # desktop: a tile opens the stock page (stubbed here — the mock has no /api/stock); the quick view is checked on the phone below
    pg.evaluate("() => { window.__op = null; const k = window.KHStock; if (k) k.open = (c) => { window.__op = c; }; }")
    pg.mouse.click(box[0], box[1]); pg.wait_for_timeout(300)
    check('cap [1440 K]: a tile opens its stock page', pg.evaluate('window.__op') == box[2], pg.evaluate('window.__op'))
    pg.mouse.move(5, 5); pg.wait_for_timeout(200)
    mk = pg.evaluate("""() => { const c = [...document.querySelectorAll('#map .tile')].slice(0, 6).map(t => t.dataset.c);
      KH.marks.set('qa', new Map(c.map(x => [x, { size: 'n', label: ', 시험' }]))); const n = document.querySelectorAll('#map .tile .dm').length;
      const lay = KH.layout().filter(t => t.mark).length; return { n, lay }; }""")
    check('cap [1440 K]: 공시 귀퉁이 (KH.marks) drawn on the cap-ordered tiles and in KH.layout()', mk['n'] >= 6 and mk['lay'] >= 6, mk)
    pg.evaluate("KH.marks.set('qa', null)")
    try:
        with pg.expect_download(timeout=8000) as dl:
            pg.click('.xt-btn[data-x="image"]')
        out = ROOT / 'qa/shots/std_template/cap_export.png'
        dl.value.save_as(str(out))
        from PIL import Image
        im = Image.open(out); colors = len(set(im.convert('RGB').resize((80, 80)).get_flattened_data()))
        check(f'cap [1440 K]: the image save (extras) draws the cap map — {im.size[0]}×{im.size[1]}, {colors} colours', im.size[0] > 800 and colors > 30, (im.size, colors))
    except Exception as e:
        check('cap [1440 K]: the image save (extras) draws the cap map', False, e)
    # a replay frame keeps the cap order and the shape
    rp = pg.evaluate("""() => { const m = new Map(); for (const s of KH.stocks().slice(0, 600)) m.set(s.c, { p: s.p * 1.01, r: (s.r || 0) + 1 });
      KH.setReplay({ t: '1030', date: '2026-11-13', prices: m }); const n = document.querySelectorAll('#map .node.sec').length; return n; }""")
    pg.wait_for_timeout(500)
    st3 = pg.evaluate(CAPSTATE)
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(400)
    check('cap [1440 K]: a replay frame draws the cap map (no bands, cap order)', rp == 0 and st3['secs'] == 0 and st3['inv'] == 0, (rp, st3['secs'], st3['inv']))
    # back to 섹터별: bands return
    pg.click('#moreBtn'); pg.wait_for_timeout(400)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="sector"]'); pg.keyboard.press('Escape'); pg.wait_for_timeout(900)
    bk = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: back to 섹터별 — sector / industry bands again, saved "sector"', bk['secs'] > 0 and bk['store'] == '"sector"', (bk['secs'], bk['store']))
    ctx.close()
    # ── phones, 전체, every theme: order, no overflow, map top unchanged ──
    for theme in THEMES:
        for w, h, m, top in ((390, 844, 'ALL', 247), (1440, 900, 'Q', 207)):
            ctx, pg = open_page(br, w, h, theme=theme, market=m, extra={'groupBy': 'cap'})
            st = pg.evaluate(CAPSTATE)
            g = pg.evaluate("() => Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY)")
            ov = pg.evaluate(OVER)
            check(f'cap [{w} {m} {theme}]: saved 시총순 → cap order, no bands, labels inside, nothing past the edge, map top {g} (= {top})',
                  st['secs'] == 0 and st['inv'] == 0 and st['read'][:10] == st['byCap'][:10] and not st['overflow'] and not ov and g == top, (st['secs'], st['inv'], st['overflow'], ov, g))
            if theme in ('base', 'glass-light'):
                pg.screenshot(path=str(ROOT / f'qa/shots/std_template/cap_{w}_{m}_{theme}.png'))
            if w == 390 and theme == 'base':
                tb = pg.evaluate("(() => { const t = document.querySelector('#map .tile'); const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, KH.stock(t.dataset.c).n]; })()")
                pg.touchscreen.tap(tb[0], tb[1]); pg.wait_for_timeout(800)
                sh = pg.evaluate("() => { const s = document.getElementById('sheet'); return { open: s.classList.contains('open'), txt: s.textContent.slice(0, 80) }; }")
                check(f'cap [390]: tapping the first tile ({tb[2]}) opens the quick view', sh['open'] and tb[2] in sh['txt'], sh)
                pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
            # 테마 · 관심 keep their own maps
            if w == 390 and theme == 'base':
                pg.evaluate("document.querySelector('.tabs button[data-mkt=\"THEME\"]').click()"); pg.wait_for_timeout(800)
                th = pg.evaluate("() => document.getElementById('map').getAttribute('aria-label')")
                check('cap [390]: 테마 keeps its theme map with 시총순 saved', th == '테마별 트리맵', th)
            ctx.close()
    # ── 줄이기: the switch lands at once ──
    ctx, pg = open_page(br, 1440, 900, market='K', motion='reduced')
    pg.click('#moreBtn'); pg.wait_for_timeout(300)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="cap"]'); pg.wait_for_timeout(60)
    an = pg.evaluate("() => [...document.querySelectorAll('#map .tile')].filter(t => t.getAnimations().length).length")
    check('cap [1440 줄이기]: 시총순 lands at once (no tile animation)', an == 0, an)
    ctx.close()


if __name__ == '__main__':
    parts = set(sys.argv[1:]) or {'audit', 'page', 'cap'}
    run(parts)
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAIL', f)
    sys.exit(1 if FAILS else 0)
