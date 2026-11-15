#!/usr/bin/env python3
"""QA for the 오늘의 시장 요약 카드 (src/summary, docs/standards/market-summary.md, AGENTS §3-34) on the built pages.

  python3 scripts/build_page.py && python3 qa/summary/test_summary.py [--shots]

Starts qa/summary/mock_summary.py on SUMMARY_QA_PORT (default 8981; ports 8980–8988 only) and, for "the map does not move", a second
one on SUMMARY_QA_PORT + 1 serving the web/ of git rev SUMMARY_QA_BASE (default main) — the page without the card. Both are stopped with
fuser -k <port>/tcp at the end. The mock data is the 11/13 (금) close: 상한가 9 · 하한가 0 (snapshot lim), flows of 11/13.
Static: summary.css uses only design tokens for type, corners, colour, spacing and motion (design.md §2–§6); close.json carries lim.
Browser (live, 360 · 390 · 768 · 1440, 기본 테마; 390 · 1440 also 신문): the card's place (phone: right after the map, before #news;
tablet / desktop: first in .side), the map's box = the base build's, collapsed by default and after a reload (not remembered), no
horizontal overflow, no console errors, no "null/undefined/NaN", text ≥ 11 px, red / green only on numbers, no amber text / fill, touch
targets ≥ 44 px on phones — collapsed and expanded. The 자세히 key is the site's key (--key-bg · --key-sh · square --h-key · --r-key · 16 px
chevron at 1.75, 44 × 44 on phones), open = --key-on + amber chevron — 기본 · 신문 · 글라스 어둡게 · 밝게. Motion (design-references-full §7, sampled every frame): 자세히 = only the card's
panel grows by the `open` spring (overshoot ≤ 2 %) while the content below already sits at its new place (moved once, at the start), the
table text comes in after the panel is ≥ 25 % grown; 접기 = text out together, the panel shrinks (close), the content below moves once at
the end, focus on the top key (P8 ⓐ). 화려하게: a ≤ 300 ms stagger (gaps 40 → 30 → 20 ms) only on the session's first expand (P3).
Band numbers swap in from below when they rise, from above when they fall (P9). 글로 복사: the clipboard text, the key keeps its size,
copy icon → ✓ and back after --c-dwell, a script click (not isTrusted) does nothing (P11). /api/news · themes · market · world only
after the first 자세히. The four phases' words (?summary_phase=pre|open|after|closed). 움직임 줄이기: at once. Snapshot (dist/, file://).
--shots writes qa/shots/market_summary/impl_*.png. Exit 1 on a fail.
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

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('SUMMARY_QA_PORT', 8981))
assert 8980 <= PORT <= 8988
URL = f'http://127.0.0.1:{PORT}/'
BASE_REV = os.environ.get('SUMMARY_QA_BASE', 'main')
OUT = ROOT / 'qa/shots/market_summary'
SHOTS = '--shots' in sys.argv
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
fails = []
counts = {'pass': 0}


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail not in ('', None, [], {}) else ''), flush=True)
    if ok:
        counts['pass'] += 1
    else:
        fails.append(name)


def lint_css():
    css = (ROOT / 'src/summary/summary.css').read_text(encoding='utf-8')
    body = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    bad = []
    for prop, val in re.findall(r'([a-z-]+)\s*:\s*([^;{}]+)', body):
        v = val.strip()
        if prop == 'font-size' and not re.fullmatch(r'var\(--fs-[a-z0-9]+\)', v):
            bad.append(f'{prop}:{v}')
        if prop == 'border-radius' and not all(re.fullmatch(r'var\(--(r-[a-z]+|card-r|sheet-r)\)|0', x) for x in v.split()):
            bad.append(f'{prop}:{v}')
        if re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', v) or re.search(r'gradient\(|text-shadow|drop-shadow', v) or prop == 'text-shadow':
            bad.append(f'{prop}:{v}')
        if prop in ('transition', 'animation') and re.search(r'cubic-bezier|ease(-in|-out)?\b', v):
            bad.append(f'{prop}:{v}')
        if prop in ('margin', 'padding', 'gap', 'column-gap', 'row-gap') or prop.startswith(('margin-', 'padding-')):
            if any(m not in ('0', '1') for m in re.findall(r'(?<![\w-])(\d+(?:\.\d+)?)px', v)):
                bad.append(f'{prop}:{v}')
    check('css: type · corners · colour · spacing · motion from tokens only (design.md §2–§6)', not bad, bad[:6])
    m = re.search(r'@media \(hover:hover\) and \(pointer:fine\)\{(.*?)\n\}', body, flags=re.S)
    outside = body.replace(m.group(0), '') if m else body
    check('css: :hover only inside (hover:hover) and (pointer:fine) (design.md §8)', bool(m) and ':hover' not in outside)
    js = (ROOT / 'src/summary/summary.js').read_text(encoding='utf-8')
    check('js: no dev switch left (?summary= · khm.dev.summary)', "get('summary')" not in js and 'khm.dev.summary' not in js)
    cj = json.loads((ROOT / 'web/close.json').read_text(encoding='utf-8'))
    snap = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
    want = {x['c']: x['lim'] for x in snap['stocks'] if x.get('lim') in (1, -1) and x.get('p')}
    got = {c: v[3] for c, v in cj['c'].items() if len(v) > 3}
    check('close.json: "lim": true and the 4th element = the snapshot lim (1 / −1 only when set)', cj.get('lim') is True and got == want and all(len(v) in (3, 4) for v in cj['c'].values()),
          f'{len(got)} rows with lim, snapshot {len(want)}')


def start_mock(port, web=None):
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    time.sleep(0.3)
    env = dict(os.environ)
    if web:
        env['MOCK_WEB'] = str(web)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/summary/mock_summary.py'), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(60):
        try:
            NOPROXY.open(f'http://127.0.0.1:{port}/api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w, h, theme='base', url=URL, query='', motion='standard', perms=False):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    if perms:
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=url.rstrip('/'))
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': 'K'}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    errs = []
    pg.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append(f'pageerror: {e}'))
    pg.goto(url + query)
    pg.wait_for_timeout(2600)
    return ctx, pg, errs


MAPBOX = "(() => { const b = document.getElementById('map').getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)]; })()"
STATE = """() => { const c = document.getElementById('summary'); if (!c) return null;
  const t = c.querySelector('.sm-tog'), band = c.querySelector('.sm-band'), full = document.getElementById('sm-more'), lay = document.querySelector('main.layout'), side = lay.querySelector('.side');
  const b = c.getBoundingClientRect();
  return { open: t.getAttribute('aria-expanded'), band: !band.hidden && band.offsetHeight > 0, full: !full.hidden && full.offsetHeight > 0,
    phonePlace: c.parentNode === lay && c.nextElementSibling === document.getElementById('news'), sidePlace: side.firstElementChild === c,
    span: getComputedStyle(c).gridColumnStart + '/' + getComputedStyle(c).gridColumnEnd, top: Math.round(b.top + scrollY), h: Math.round(b.height),
    pill: c.querySelector('.sm-pill').textContent, hl: c.querySelector('.sm-hl').textContent, text: c.innerText }; }"""
MEASURE = """() => {
  const card = document.getElementById('summary');
  const txt = card ? card.innerText : '';
  const phone = matchMedia('(max-width: 760px)').matches;
  const small = [], tiny = [], colour = [], amber = [];
  const probe = v => { const s = document.createElement('span'); s.style.color = v; document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; };
  const UP = probe('var(--up-text)'), DN = probe('var(--dn-text)'), AC = [probe('var(--acc)'), probe('var(--acc-fill)')];
  if (card) {
    for (const el of card.querySelectorAll('*')) {
      if (el.offsetParent === null) continue;
      const cs = getComputedStyle(el);
      const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      if (own && parseFloat(cs.fontSize) < 11) tiny.push((el.className || el.tagName) + ' ' + cs.fontSize);
      if (own && (cs.color === UP || cs.color === DN) && !el.closest('.sm-n, .up, .dn')) colour.push((el.className || el.tagName) + ' "' + el.textContent.trim().slice(0, 12) + '"');
      if ((own && AC.includes(cs.color)) || AC.includes(cs.backgroundColor)) amber.push(el.className || el.tagName);
    }
    if (phone) for (const el of card.querySelectorAll('button, a[href]')) {
      if (el.offsetParent === null) continue;
      const b = el.getBoundingClientRect(), cs = getComputedStyle(el, '::before');
      const hitH = Math.max(b.height, cs.content !== 'none' && cs.position === 'absolute' ? parseFloat(cs.height) || 0 : 0);
      if (hitH < 44 && !el.classList.contains('sm-a')) small.push((el.className || el.tagName) + ' ' + Math.round(hitH));
    }
  }
  return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bad: /\\b(null|undefined|NaN)\\b/.test(txt), txt: txt.slice(0, 300), small, tiny, colour, amber };
}"""
# click the key from inside the page and read every frame (rAF): the card's layout height and the top of the element after it (P8 ⓐ — the
# content below moves once: at the start of an expand, at the end of a collapse; never per frame), the skin's height (the panel the user
# sees grow), whether the table text is in (.sm-go), and right after the click the stagger delays (--d) of the table's blocks (P3)
SAMPLE = """async (sel) => {
  const c = document.getElementById('summary'), skin = c.querySelector('.sm-skin'), full = document.getElementById('sm-more'), band = c.querySelector('.sm-band');
  const nx = c.nextElementSibling, top = el => el ? Math.round(el.getBoundingClientRect().top + scrollY) : -1;
  const H0 = c.offsetHeight, N0 = top(nx), out = [], t0 = performance.now();
  c.querySelector(sel).click();
  const kids = [...full.querySelectorAll(':scope > .sm-fbody > *, :scope > .sm-df')].map(e => e.style.getPropertyValue('--d'));
  const sync = [full.className, band.className, c.classList.contains('sm-anim'), c.offsetHeight, top(nx), kids];   // same task as the click
  await new Promise(res => { const f = () => { const t = performance.now() - t0;
    out.push([Math.round(t), c.offsetHeight, c.classList.contains('sm-anim') ? +skin.getBoundingClientRect().height.toFixed(1) : -1, full.classList.contains('sm-go'), top(nx)]);
    if ((t > 150 && !KHSummary.moving()) || t > 8000) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await new Promise(r => setTimeout(r, 120));
  return { H0, N0, N1: top(nx), out, sync, ms: Math.round(performance.now() - t0), H1: c.offsetHeight, fullH: full.hidden ? 0 : full.offsetHeight, bandH: band.hidden ? 0 : band.offsetHeight, anim: c.classList.contains('sm-anim'), focus: document.activeElement && document.activeElement.className };
}"""


# the 자세히 key (사용자 2026-11-15 20:01 "맨 오른쪽 버튼 디자인이 안되어있네"): the site's key — --key-bg · --key-sh · square --h-key · --r-key, a 16 px
# chevron at 1.75; open = the open-trigger look (--key-on + amber chevron, like .ddbtn · .bchip), never a bare --fill-1 blob
TOG = """() => { const t = document.querySelector('#summary .sm-tog'), cs = getComputedStyle(t), r = t.getBoundingClientRect(), svg = t.querySelector('svg');
  const probe = (prop, v) => { const s = document.createElement('span'); s.style[prop] = v; document.body.append(s); const c = getComputedStyle(s)[prop]; s.remove(); return c; };
  const hk = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--h-key'));
  const kb = document.createElement('span'); kb.style.background = 'var(--key-bg)'; document.body.append(kb); const kbs = getComputedStyle(kb), bgOk = cs.backgroundImage === kbs.backgroundImage && cs.backgroundColor === kbs.backgroundColor; kb.remove();
  const hit = getComputedStyle(t, '::before'), coarse = matchMedia('(pointer: coarse)').matches;
  return { open: t.getAttribute('aria-expanded'), w: Math.round(r.width), h: Math.round(r.height), hk, bgOk, shKey: cs.boxShadow === probe('boxShadow', 'var(--key-sh)'), shOn: cs.boxShadow === probe('boxShadow', 'var(--key-on)'),
    radius: cs.borderTopLeftRadius === probe('borderTopLeftRadius', 'var(--r-key)'), chevAcc: getComputedStyle(svg).color === probe('color', 'var(--acc)'), icon: [svg.getAttribute('width'), svg.getAttribute('stroke-width')].join('/'),
    hit: coarse ? [Math.round(parseFloat(hit.width)), Math.round(parseFloat(hit.height))] : null }; }"""


def tog_ok(k, open_):
    base = k['bgOk'] and k['w'] == k['h'] == round(k['hk']) and k['radius'] and k['icon'] == '16/1.75' and (k['hit'] is None or min(k['hit']) >= 44)
    return base and (k['shOn'] and k['chevAcc'] if open_ else k['shKey'] and not k['chevAcc']) and k['open'] == ('true' if open_ else 'false')


HOLD = """async () => {
  const c = document.getElementById('summary'), nx = c.nextElementSibling, top = el => Math.round(el.getBoundingClientRect().top + scrollY), out = [], t0 = performance.now();
  c.querySelector('.sm-tog').click();
  const aria = c.querySelector('.sm-tog').getAttribute('aria-expanded');
  await new Promise(res => { const f = () => { const t = performance.now() - t0; out.push([Math.round(t), c.offsetHeight, top(nx), 0, c.classList.contains('sm-anim')]);
    if ((t > 700 && !KHSummary.moving()) || t > 5000) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); });
  return { aria, out, open: c.querySelector('.sm-tog').getAttribute('aria-expanded'), text: document.getElementById('sm-more').innerText };
}"""


def motion_ok(s, expand):
    """P8 ⓐ. expand: the layout is already H1 and the next element already at its final top right after the click and on every frame;
    the skin grows H0 → H1 (overshoot ≤ 2 % of the move); the table text comes in only once the skin is ≥ 25 % grown (and ≥ 160 ms).
    collapse: the layout stays H0 and the next element stays put on every frame while the skin shrinks; both change once at the end."""
    moving = [x for x in s['out'] if x[2] >= 0]
    D = abs(s['H1'] - s['H0']) or 1
    sk = [x[2] for x in moving]
    info = {'frames': len(moving), 'ms': s['ms'], 'H0': s['H0'], 'H1': s['H1'], 'skin': sk[:3] + sk[-1:], 'next': [s['N0'], s['N1']]}
    if not moving or s['anim']:
        return False, info
    if expand:
        lay = s['sync'][3] == s['H1'] and all(x[1] == s['H1'] for x in moving)
        fol = s['sync'][4] == s['N1'] and all(x[4] == s['N1'] for x in moving)
        over = max(sk) - (s['H1'] + 2)
        go = [x for x in moving if x[3]]
        prog = round((go[0][2] - s['H0']) / D, 2) if go else None
        info.update(over=round(over, 1), reveal=go and [go[0][0], prog])
        return lay and fol and over <= 0.02 * D + 2 and sk[0] < s['H0'] + 0.6 * D and bool(go) and prog >= 0.2 and go[0][0] >= 140, info
    lay = all(x[1] == s['H0'] for x in moving)
    fol = all(x[4] == s['N0'] for x in moving)
    over = (s['H1'] - 2) - min(sk)
    info.update(over=round(over, 1))
    return lay and fol and over <= 0.02 * D + 2 and s['sync'][3] == s['H0'], info


def per(tag, pg, errs, w):
    m = pg.evaluate(MEASURE)
    check(f'{tag}: horizontal overflow 0', m['sw'] <= m['cw'], f"{m['sw']} > {m['cw']}" if m['sw'] > m['cw'] else '')
    check(f'{tag}: console errors 0', not errs, errs[:2])
    check(f'{tag}: no null/undefined/NaN', not m['bad'], m['txt'][:100] if m['bad'] else '')
    check(f'{tag}: text ≥ 11 px · red/green only on numbers · no amber', not m['tiny'] and not m['colour'] and not m['amber'], (m['tiny'] + m['colour'] + m['amber'])[:4])
    if w <= 760:
        check(f'{tag}: touch targets ≥ 44', not m['small'], m['small'][:4])


def main():
    lint_css()
    start_mock(PORT)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='msum_base_'))
    subprocess.run(f'git -C {ROOT} archive {BASE_REV} web | tar -x -C {tmp}', shell=True, check=True)
    bport = PORT + 1
    start_mock(bport, tmp / 'web')
    if SHOTS:
        OUT.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            sizes = [(360, 780), (390, 844), (768, 1024), (1440, 900)]
            for (w, h) in sizes:
                themes = ['base', 'paper'] if w in (390, 1440) else ['base']
                for theme in themes:
                    tag = f'{w}x{h} {theme}'
                    ctx, pg, errs = open_page(br, w, h, theme)
                    st = pg.evaluate(STATE)
                    check(f'{tag}: card drawn, collapsed by default (band shown, table hidden)', st is not None and st['open'] == 'false' and st['band'] and not st['full'], st and {k: st[k] for k in ('open', 'band', 'full')})
                    if w <= 760:
                        check(f'{tag}: place = right after the map, before the news card', st['phonePlace'], st['top'])
                    else:
                        check(f'{tag}: place = first in the side column' + (' (whole row)' if w <= 980 else ''), st['sidePlace'] and (w > 980 or st['span'] == '1/-1'), st['span'])
                    if theme == 'base':
                        mine = pg.evaluate(MAPBOX)
                        bctx, bpg, berrs = open_page(br, w, h, theme, url=f'http://127.0.0.1:{bport}/')
                        base = bpg.evaluate(MAPBOX); bctx.close()
                        check(f'{tag}: the map box = {BASE_REV} build (left · top · width · height)', mine == base, f'{mine} vs {base}')
                    pg.evaluate("document.getElementById('summary').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
                    k = pg.evaluate(TOG)
                    check(f'{tag}: 자세히 key = the site key (key bg · shadow · square --h-key · --r-key · 16 px chevron 1.75, touch 44 × 44)', tog_ok(k, False), k)
                    per(f'{tag} collapsed', pg, errs, w)
                    if SHOTS:
                        pg.screenshot(path=str(OUT / f'impl_{w}_{theme}_collapsed.png'))
                    pg.focus('#summary .sm-tog'); pg.wait_for_timeout(500)      # a hand on the key: /api/news starts (then the press does not wait)
                    s = pg.evaluate(SAMPLE, '.sm-tog')
                    ok, info = motion_ok(s, True)
                    sync = s['sync']
                    check(f'{tag}: 자세히 — the panel grows {s["H0"]} → {s["H1"]} px by the open spring, the content below moved once at the start, table text after 25 %',
                          ok and s['H1'] > s['H0'] + 40 and s['bandH'] == 0, info)
                    if theme == 'base':
                        check(f'{tag}: on the press the table text waits (.sm-in, no .sm-go — it comes in at 160 ms) while the band leaves (.sm-out), skin on',
                              'sm-in' in sync[0] and 'sm-go' not in sync[0] and 'sm-out' in sync[1] and sync[2], sync)
                    st = pg.evaluate(STATE)
                    check(f'{tag}: expanded = the table + details + 글로 복사', st['open'] == 'true' and not st['band'] and st['full'] and '코스닥' in st['text'] and '글로 복사' in st['text'] and '오늘 흐름' in st['text'])
                    k = pg.evaluate(TOG)
                    check(f'{tag}: expanded 자세히 key = open trigger (--key-on + amber chevron, same box)', tog_ok(k, True), k)
                    per(f'{tag} expanded', pg, errs, w)
                    if SHOTS:
                        pg.evaluate("document.getElementById('summary').scrollIntoView({block:'start'})"); pg.wait_for_timeout(200)
                        pg.screenshot(path=str(OUT / f'impl_{w}_{theme}_expanded.png'))
                    s = pg.evaluate(SAMPLE, '.sm-fold')
                    st = pg.evaluate(STATE)
                    ok, info = motion_ok(s, False)
                    check(f'{tag}: 접기 at the end → the panel shrinks by the close spring, the content below moves once at the end, focus on the top key',
                          ok and st['open'] == 'false' and st['band'] and not st['full'] and s['H1'] < s['H0'] - 40 and 'sm-tog' in (s['focus'] or ''), dict(info, focus=s['focus']))
                    if theme == 'base':
                        check(f'{tag}: 접기 — everything leaves together (one .sm-out, no stagger delays)', 'sm-out' in s['sync'][0] and 'sm-stag' not in s['sync'][0] and not any(s['sync'][5]), s['sync'][0])
                    ctx.close()
            # the key in the two glass themes (기본 · 신문 are in the loop above)
            for (w, h) in [(390, 844), (1440, 900)]:
                for theme in ('glass-dark', 'glass-light'):
                    ctx, pg, errs = open_page(br, w, h, theme, motion='reduced')
                    k0 = pg.evaluate(TOG)
                    pg.focus('#summary .sm-tog'); pg.wait_for_timeout(400)
                    pg.evaluate("document.querySelector('#summary .sm-tog').click()"); pg.wait_for_timeout(500)     # no mouse over it (hover = --key-hover)
                    k1 = pg.evaluate(TOG)
                    check(f'{w}x{h} {theme}: 자세히 key collapsed · expanded = the site key · open trigger, console errors 0', tog_ok(k0, False) and tog_ok(k1, True) and not errs, [k0, k1, errs[:1]])
                    ctx.close()
            # P3: the short stagger only on the first expand of the session (화려하게); a re-open has none
            ctx, pg, errs = open_page(br, 390, 844, motion='fancy')
            pg.focus('#summary .sm-tog'); pg.wait_for_timeout(500)
            s1 = pg.evaluate(SAMPLE, '.sm-tog')
            d = [int(x[:-2]) for x in s1['sync'][5] if x.endswith('ms')]
            gaps = [b - a for a, b in zip(d, d[1:])]
            ok_gaps = bool(d) and d[0] == 0 and len(d) == len(s1['sync'][5]) and max(d) <= 300 and gaps[:2] == [40, 30] and all(g in (20, 0) for g in gaps[2:]) and all(a >= b for a, b in zip(gaps, gaps[1:]))
            check('화려하게, first expand: the blocks come in one by one, 0 · 40 · 70 · 90 … ms (gaps 40 → 30 → 20), all within 300 ms', 'sm-stag' in s1['sync'][0] and ok_gaps, d)
            pg.evaluate(SAMPLE, '.sm-fold')
            pg.focus('#summary .sm-tog'); pg.wait_for_timeout(300)
            s2 = pg.evaluate(SAMPLE, '.sm-tog')
            check('화려하게, re-open in the same session: no stagger (the table comes in together)', 'sm-stag' not in s2['sync'][0] and not any(s2['sync'][5]) and motion_ok(s2, True)[0], s2['sync'][0])
            check('화려하게: console errors 0', not errs, errs[:2])
            ctx.close()
            # P9: numbers with a direction swap in from below when they rise, from above when they fall (the band, ?summary_phase=open)
            ctx, pg, errs = open_page(br, 1440, 900, query='?summary_phase=open')
            SHIFT = """(dr) => { const k = '#summary [data-k="iuv"]', el = document.querySelector(k); if (!el) return null;
              const was = el.textContent, q0 = KH.__q || (KH.__q = KH.quote);
              KH.quote = c => { const x = q0(c); return x && Object.assign({}, x, { r: +x.r + dr }); };
              KHSummary.refresh();
              const now = document.querySelector(k);
              return { was, same: now === el, sw: now.classList.contains('sm-sw'), down: now.classList.contains('sm-swd'), o: (now.querySelector('.o') || {}).textContent, n: (now.querySelector('.n') || {}).textContent }; }"""
            pg.wait_for_function("!!document.querySelector('#summary [data-k=\"up\"]')", timeout=8000)   # 장중: 전 종목 등락이 오면 곧바로(15초를 기다리지 않고)
            up = pg.evaluate(SHIFT, 0.07); pg.wait_for_timeout(600)
            dn = pg.evaluate(SHIFT, -0.07); pg.wait_for_timeout(600)
            settled = pg.evaluate("(() => { const el = document.querySelector('#summary [data-k=\"iuv\"]'); return [el.classList.contains('sm-sw'), el.childElementCount, el.textContent]; })()")
            check('band number rises → the same node swaps in from below (.sm-sw, not .sm-swd), old → new', bool(up) and up['same'] and up['sw'] and not up['down'] and up['o'] == up['was'] and up['n'] != up['was'], up)
            check('band number falls → swaps in from above (.sm-swd); then plain text again', bool(dn) and dn['same'] and dn['sw'] and dn['down'] and settled[0] is False and settled[1] == 0, [dn, settled])
            check('P9: console errors 0', not errs, errs[:2])
            ctx.close()
            # /api/themes · market · world · news only after the first 자세히 (none while collapsed — the news card's own /api/news stays its own)
            seen = {'mine': [], 'base': []}
            for who, url in (('mine', URL), ('base', f'http://127.0.0.1:{bport}/')):
                c2 = br.new_context(viewport={'width': 1440, 'height': 900})
                c2.add_init_script("try{localStorage.setItem('khm.tickerPaused','true')}catch(e){}")
                pg = c2.new_page()
                pg.on('request', lambda r, who=who: seen[who].append(re.sub(r'^https?://[^/]+', '', r.url)))
                pg.goto(url); pg.wait_for_timeout(4000)
                if who == 'mine':
                    before = list(seen['mine'])
                    pg.click('#summary .sm-tog'); pg.wait_for_timeout(1500)
                c2.close()
            api = lambda xs, k: sum(1 for u in xs if u.startswith(k))
            keys = ['/api/news', '/api/themes', '/api/market', '/api/world']
            col = {k: (api(before, k), api(seen['base'], k)) for k in keys}
            check(f'collapsed: /api/news only from the news card (= {BASE_REV}: the card never asks first); themes · market · world fetched ahead for the table',
                  col['/api/news'][0] == col['/api/news'][1] and col['/api/themes'][0] >= 1 and col['/api/market'][0] > col['/api/news'][0] and col['/api/world'][0] >= 2, col)
            grew = {k: api(seen['mine'], k) - api(before, k) for k in keys}
            check('first 자세히: /api/news once (from the hand on the key), nothing else again', grew == {'/api/news': 1, '/api/themes': 0, '/api/market': 0, '/api/world': 0}, grew)
            # the first press with /api/news still on its way: the chevron turns at once, the panel waits for it (≤ 450 ms), then grows once
            for (w, h) in [(390, 844), (1440, 900)]:
                ctx, pg, errs = open_page(br, w, h)
                pg.route('**/api/news', lambda r: (time.sleep(0.25), r.continue_()))
                hs = pg.evaluate(HOLD)
                lays = [k for i, k in enumerate(x[1] for x in hs['out']) if i == 0 or k != hs['out'][i - 1][1]]
                tops = [k for i, k in enumerate(x[2] for x in hs['out']) if i == 0 or k != hs['out'][i - 1][2]]
                start = next((x[0] for x in hs['out'] if x[4]), None)
                check(f'{w}: first press before the news came → chevron at once, the panel starts after it (≤ 600 ms), layout · next card change once, no 받는 중 left',
                      hs['aria'] == 'true' and start is not None and start <= 600 and len(lays) <= 2 and len(tops) <= 2 and '받는 중' not in hs['text'] and hs['open'] == 'true' and not errs,
                      {'start': start, 'lays': lays, 'tops': tops, 'wait': '받는 중' in hs['text'], 'errs': errs[:1]})
                ctx.close()
            # the words (1440 · 390): exact 상·하한가, 수급 = the previous trading day with its date, 거래대금 상위 (not 급증)
            ctx, pg, errs = open_page(br, 1440, 900)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            t = pg.evaluate("document.getElementById('summary').innerText")
            lim = re.search(r'상한가 · 하한가\s*([\d,]+) · ([\d,]+)', t)
            check('상한가 · 하한가 = 9 · 0 (close.json lim — the old ±29.5 % guess counted 1 하한가)', bool(lim) and lim.groups() == ('9', '0'), lim and lim.groups())
            check('외국인 · 기관 = the 11/13 file with its date', re.search(r'외국인 · 기관\s*11/13', t) is not None and '11/13 · 코스피 · 코스닥 합' in t)
            check('"거래대금 상위", never "급증"', '거래대금 상위' in t and '급증' not in t)
            ctx.close()
            # reload → collapsed (not remembered)
            ctx, pg, errs = open_page(br, 390, 844)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            pg.reload(); pg.wait_for_timeout(2600)
            st = pg.evaluate(STATE)
            check('after a reload it starts collapsed again (not remembered)', st['open'] == 'false' and st['band'] and not st['full'])
            ctx.close()
            # 글로 복사
            ctx, pg, errs = open_page(br, 1440, 900, perms=True)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            KEY = "(() => { const b = document.querySelector('#summary .sm-copy'), r = b.getBoundingClientRect(), op = k => +getComputedStyle(b.querySelector('.sm-i-' + k)).opacity; return { st: b.dataset.st, w: Math.round(r.width * 2) / 2, h: Math.round(r.height * 2) / 2, copy: op('copy'), done: op('done'), label: (b.querySelector('.sm-kl.on') || {}).textContent }; })()"
            pg.evaluate("navigator.clipboard.writeText('before')")
            pg.evaluate("document.querySelector('#summary .sm-copy').click()"); pg.wait_for_timeout(300)
            k0 = pg.evaluate(KEY)
            check('글로 복사: a script click (not isTrusted) leaves the clipboard and the key alone', pg.evaluate('navigator.clipboard.readText()') == 'before' and k0['st'] == 'idle', k0)
            pg.click('#summary .sm-copy'); pg.wait_for_timeout(600)
            k1 = pg.evaluate(KEY)
            clip = pg.evaluate('navigator.clipboard.readText()')
            pg.wait_for_timeout(1400)
            k2 = pg.evaluate(KEY)
            check('글로 복사: same size in every state; copy icon → ✓ (cross-fade) + 복사했어요, back after --c-dwell',
                  (k0['w'], k0['h']) == (k1['w'], k1['h']) == (k2['w'], k2['h']) and k1['done'] > 0.95 and k1['copy'] < 0.05 and k1['label'] == '복사했어요' and k2['st'] == 'idle' and k2['copy'] > 0.95 and k2['label'] == '글로 복사', [k0, k1, k2])
            lines = clip.split('\n')
            check('글로 복사: plain text — title, headline, 지수, 오른·내린, 업종, 수급, 원/달러, last line the disclaimer',
                  lines[0].startswith('판세 · 오늘 시장 요약 (휴장 · 11월 13일 (금) 마감 기준)') and '코스피는 내리고 코스닥은 올랐어요' in lines and any(l.startswith('코스피 5,290.53') for l in lines)
                  and any(l.startswith('상승 1,276 · 하락 1,211') and '상한가 9 · 하한가 0' in l for l in lines) and any(l.startswith('업종: ') for l in lines)
                  and any(l.startswith('수급(11/13, 추정)') for l in lines) and any(l.startswith('원/달러 ') for l in lines) and lines[-1].endswith('투자 판단의 근거로 쓰지 마세요.'), lines)
            check('글로 복사: console errors 0', not errs, errs[:2])
            ctx.close()
            # the four phases (wording only)
            want = {'pre': ('장 전', '9시에 시작해요', '올랐어요'), 'open': ('장중', '기준', '오르고 있어요'), 'after': ('오늘 마감', '15:30 정규장 종가 기준', '올랐어요'), 'closed': ('휴장', '11월 13일 (금) 마감 기준', '올랐어요')}
            for ph, (pill, when, verb) in want.items():
                ctx, pg, errs = open_page(br, 390, 844, query=f'?summary_phase={ph}')
                st = pg.evaluate(STATE)
                pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
                w_txt = pg.evaluate("document.querySelector('#summary .sm-when').textContent")
                dot = pg.evaluate("getComputedStyle(document.querySelector('#summary .sm-pill'), '::before').content")
                check(f'phase {ph}: "{st["pill"]}" · "{st["hl"]}" · "{w_txt}"' + (' · --live dot' if ph == 'open' else ''),
                      st['pill'] == pill and when in w_txt and st['hl'].endswith(verb) and ((dot != 'none') == (ph == 'open')) and not errs, errs[:2])
                ctx.close()
            # 움직임 줄이기: at once
            ctx, pg, errs = open_page(br, 1440, 900, motion='reduced')
            pg.focus('#summary .sm-tog'); pg.wait_for_timeout(500)
            s = pg.evaluate(SAMPLE, '.sm-tog')
            check('움직임 줄이기: the table is there at once (first frame already at the full height, no skin on any frame)',
                  s['out'] and all(x[2] == -1 for x in s['out']) and s['out'][0][1] == s['out'][-1][1] and s['out'][0][1] > s['H0'] + 40, s['out'][:2])
            ctx.close()
            # snapshot (dist/, file://)
            for (w, h) in [(390, 844), (1440, 900)]:
                ctx, pg, errs = open_page(br, w, h, url=(ROOT / 'dist/index.html').as_uri())
                st = pg.evaluate(STATE)
                ok = st is not None and st['pill'] == '스냅샷' and '상승 ' in st['text'] and '업종' in st['text']
                pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
                t = pg.evaluate("document.getElementById('summary').innerText")
                check(f'snapshot {w}: the card from the snapshot (스냅샷 · 상승/하락 · 업종; 해외 · 공시 · 뉴스 → 실시간 버전 안내), console errors 0',
                      ok and '실시간 버전' in t and '상한가 · 하한가' in t and not errs, errs[:2] or (st and st['text'][:80]))
                if SHOTS:
                    pg.screenshot(path=str(OUT / f'impl_snapshot_{w}.png'))
                ctx.close()
            br.close()
    finally:
        for prt in (PORT, bport):
            subprocess.run(['fuser', '-k', f'{prt}/tcp'], capture_output=True)
    print(f"\n{counts['pass']} passed, {len(fails)} failed" + (': ' + ', '.join(fails) if fails else ''))
    sys.exit(1 if fails else 0)


main()
