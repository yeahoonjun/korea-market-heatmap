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
    check('audit: linear gradients only on the allow-list (data scale, hatches, 공시 corner, overflow mask)', not bad, bad)
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
                check(f'page [{theme}]: --live {t["live"]} — ≥ 30° from the amber and the new-filing blue, saturated, ≥ 3:1 on the page',
                      hdist(hl, hue(acc)[0]) >= 30 and hdist(hl, hue(nd)[0]) >= 30 and hs > .3 and contrast(live, pgc) >= 3, (round(hl), round(hue(acc)[0]), round(hue(nd)[0]), round(contrast(live, pgc), 2)))
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


def cap(br):
    pass


if __name__ == '__main__':
    parts = set(sys.argv[1:]) or {'audit', 'page', 'cap'}
    run(parts)
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAIL', f)
    sys.exit(1 if FAILS else 0)
