#!/usr/bin/env python3
"""extras on the design standard (docs/standards/design.md · AGENTS §3-31, step "extras" of design.md §11) — in a browser.

  python3 scripts/build_page.py && python3 qa/extras/test_std.py

Serves qa/extras/mock_api.py on EXTRAS_STD_PORT (default 9016; 9010–9019) and stops it (fuser -k). Checks, on the live build (web/):
  number drum (화려하게): only changed digits, the short way round, rightmost first 40ms apart, `roll` length and curve, a 14% mask,
    the text is the value all along · text swap (기본): the old text leaves as ::before, the new comes from below when it rises ·
    줄이기: written at once · the clock's digits roll one step forward, the rightmost first
  status: 갱신 실패 = ! in --fail-dot + words · 장중 dot = --live · the 15:20 outline = --live, no blur
  flat: the replay rail is boxes (the slider's track paints nothing), the session bar's bands are flat colours, no element in extras
    paints a gradient or a drop-shadow (computed styles)
  type ≥ 11px and on the scale in extras' boxes · icons 1.75px on screen (1.5 for the 12-16px session glyphs)
  tooltip: the session bar's note stays ~130ms after the pointer leaves, then goes · map top 247 · 239 (250 after hours) · 207 · 207 in 4 themes
  console errors 0
"""
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('EXTRAS_STD_PORT', 9016))
assert 9010 <= PORT <= 9019 or 9070 <= PORT <= 9079, 'ports 9010–9019 (or 9070–9079: ux/motion-rigid)'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FAILS, PASSES, ERRS = [], [], []
SCALE = {11, 12, 13, 14, 16, 20, 26}


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'), flush=True)


def start():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/extras/mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + '__reset', timeout=1).read(); return
        except Exception:
            time.sleep(0.15)
    raise SystemExit('mock did not start')


def page_at(b, when, w=1440, theme='base', motion='fancy', bump=None, paused=True, open_=True):
    """the page at a faked KST time (page.clock, /api/time answers the same); bump: on every /api/market call after the first,
    add this to KOSPI's value and ratio (a real change for the strip)"""
    t0 = datetime.datetime.fromisoformat(when + '+09:00').timestamp() * 1000
    real0 = time.time()
    mobile = w <= 760
    ctx = b.new_context(viewport={'width': w, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': paused}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{motion}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.clock.install(time=t0 / 1000)
    clk = {'adv': 0, 'n': 0}
    pg.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', headers={'cache-control': 'no-store'},
                                                 body=json.dumps({'t': t0 + (time.time() - real0) * 1000 + clk['adv']})))

    def quotes(r):
        try:
            res = r.fetch(); j = res.json()
            if open_:
                j['marketStatus'] = {'KOSPI': 'OPEN', 'KOSDAQ': 'OPEN'}
            j.pop('index', None)                       # the strip's 코스피 then comes from /api/market only (bump drives it)
            r.fulfill(response=res, body=json.dumps(j, ensure_ascii=False))
        except Exception:
            pass
    pg.route('**/api/quotes*', quotes)

    def market(r):
        try:
            res = r.fetch(); j = res.json(); clk['n'] += 1
            if bump and clk['n'] > 1:
                for it in j['items']:
                    if it['key'] == 'KOSPI':
                        it['value'] = round(it['value'] + bump[0] * (clk['n'] - 1), 2); it['ratio'] = round(it['ratio'] + bump[1] * (clk['n'] - 1), 2)
                        it['change'] = round(it.get('change', 0) + bump[0] * (clk['n'] - 1), 2)
            r.fulfill(response=res, body=json.dumps(j, ensure_ascii=False))
        except Exception:
            pass
    pg.route('**/api/market*', market)
    pg.goto(URL)
    pg.wait_for_function('() => document.querySelectorAll("#map .tile").length > 50 && document.querySelector(".xc-btn") && document.querySelector("#strip .xs-item")', timeout=20000)
    pg.wait_for_timeout(900)

    def adv(ms):
        clk['adv'] += ms
        pg.clock.run_for(ms)
    return ctx, pg, adv


def done(ctx, pg):
    try:
        pg.unroute_all(behavior='ignoreErrors')
    except Exception:
        pass
    ctx.close()


ROLL_JS = r"""() => {
  const el = document.querySelector('#strip .xs-list .xs-item[data-k="KOSPI"] .xs-v'), root = getComputedStyle(document.documentElement);
  const boxes = el ? [...el.querySelectorAll('.xr')] : [];
  return { text: el && el.textContent, html: el && el.innerHTML.slice(0, 300), n: boxes.length,
    mask: boxes[0] ? getComputedStyle(boxes[0]).webkitMaskImage || getComputedStyle(boxes[0]).maskImage : '',
    cols: boxes.map(b => { const c = b.firstElementChild, a = c.getAnimations()[0], t = a && a.effect.getTiming(), k = a && a.effect.getKeyframes();
      return { b: c.dataset.b || null, a: c.dataset.a || null, d: c.textContent, delay: t && t.delay, dur: t && t.duration, ease: t && t.easing, from: k && k[0].transform, to: k && k[k.length - 1].transform }; }),
    rollDur: parseFloat(root.getPropertyValue('--sp-roll-dur')), rollEase: root.getPropertyValue('--sp-roll').trim(),
    swap: el ? { on: el.classList.contains('xsw'), was: el.dataset.was || null, n: (el.querySelector('.xsw-n') || {}).textContent || null,
      anims: el.getAnimations({ subtree: true }).map(a => { const k = a.effect.getKeyframes(); return { pe: a.effect.pseudoElement || '', from: k[0].transform, to: k[k.length - 1].transform, dur: a.effect.getTiming().duration, delay: a.effect.getTiming().delay }; }) } : null };
}"""


# a refresh (the clock's press: KH.refresh → kh:refresh → the strip polls at once, the mock answers the bumped KOSPI); the probe runs at the
# first frame where the new value is on screen (real time — page.clock's run_for would also fast-forward the page's animations)
REFRESH_THEN = r"""async () => { const v = () => (document.querySelector('#strip .xs-list .xs-item[data-k="KOSPI"] .xs-v') || {}).textContent;
  const was = v(); KH.refresh(); const t0 = performance.now();
  while (v() === was && performance.now() - t0 < 5000) await new Promise(r => requestAnimationFrame(r));
  return ("""


def run(b):
    # ── number drum (화려하게): KOSPI +1.37 and +0.05%p on the next /api/market ──
    ctx, pg, adv = page_at(b, '2026-11-13T10:30:05', 1440, motion='fancy', bump=(1.37, 0.05))
    before = pg.evaluate(ROLL_JS)['text']
    r = pg.evaluate(REFRESH_THEN + ROLL_JS + ')(); }')
    old, new = before, r['text']
    changed = [i for i, (a, c) in enumerate(zip(old, new)) if a != c and a.isdigit() and c.isdigit()]
    check('drum: the text is the new value while it rolls', new != old and r['n'] == len(changed) and r['n'] > 0, (old, new, r['html']))
    check('drum: only the digits that changed get a drum', r['n'] == len(changed), (old, new, r['n']))
    delays = [c['delay'] for c in r['cols']]
    check('drum: the rightmost digit first, 40ms apart', delays == [40 * (len(delays) - 1 - i) for i in range(len(delays))], delays)
    check('drum: `roll` length and curve (linear() from :root)', all(abs(c['dur'] - r['rollDur']) < 1 and c['ease'].startswith('linear(') for c in r['cols']), (r['cols'][:1], r['rollDur']))
    check('drum: a 14% fade mask on the drum (a content mask)', '14%' in (r['mask'] or '') and '86%' in (r['mask'] or ''), r['mask'])
    ok = True
    for i, c in zip(changed, r['cols']):
        a, cc = int(old[i]), int(new[i])
        fwd = (cc - a) % 10
        up = fwd < 10 - fwd or fwd == 5
        steps = fwd if up else 10 - fwd
        seq = (c['b'] or c['a'] or '').split('\n')
        ok = ok and len(seq) == steps and c['d'] == new[i] and ((c['b'] is not None) == up)
    check('drum: the short way round (≤ 5 steps, up when forward is shorter; 9 → 0 is one step forward)', ok, [(old, new), r['cols']])
    pg.wait_for_timeout(1200)
    r2 = pg.evaluate(ROLL_JS)
    check('drum: settles to plain text (no drum left)', r2['n'] == 0 and r2['text'] == new, r2['html'])
    done(ctx, pg)

    # ── text swap (기본) ──
    ctx, pg, adv = page_at(b, '2026-11-13T10:30:05', 1440, motion='standard', bump=(1.37, 0.05))
    before = pg.evaluate(ROLL_JS)['text']
    r = pg.evaluate(REFRESH_THEN + ROLL_JS + ')(); }')
    sw = r['swap']
    outs = [a for a in sw['anims'] if a['pe'] == '::before']
    ins = [a for a in sw['anims'] if not a['pe']]
    check('swap (기본): the old text leaves as ::before, the new one is the text', sw['on'] and sw['was'] == before and r['text'] == sw['n'] and r['n'] == 0, sw)
    check('swap (기본): a rising value comes in from below (+4px), the old leaves up; out 100ms, in 180ms after 60ms',
          bool(outs and ins) and outs[0]['to'] == 'translateY(-4px)' and ins[0]['from'] == 'translateY(4px)' and outs[0]['dur'] == 100 and ins[0]['dur'] == 180 and ins[0]['delay'] == 60, sw['anims'])
    pg.wait_for_timeout(600)
    r2 = pg.evaluate(ROLL_JS)
    check('swap (기본): settles to plain text', not r2['swap']['on'] and r2['text'] == r['text'], r2['html'])
    done(ctx, pg)

    # ── 줄이기: at once ──
    ctx, pg, adv = page_at(b, '2026-11-13T10:30:05', 1440, motion='reduced', bump=(1.37, 0.05))
    r = pg.evaluate(REFRESH_THEN + ROLL_JS + ')(); }')
    check('줄이기: the new value is written at once (no drum, no swap)', r['n'] == 0 and not r['swap']['on'], r['html'])
    done(ctx, pg)

    # ── the clock's digits (화려하게): 10:29:59 → 10:30 rolls two digits one step forward, the rightmost first ──
    ctx, pg, adv = page_at(b, '2026-11-13T10:29:53', 1440, motion='fancy')
    pg.wait_for_function("() => [...document.querySelectorAll('.xc-digits .xdg')].some(c => c.classList.contains('xdg-go'))", timeout=15000, polling=20)
    cl = pg.evaluate("""() => [...document.querySelectorAll('.xc-digits .xdg')].map(c => ({ go: c.classList.contains('xdg-go'),
      mask: getComputedStyle(c).webkitMaskImage || '', a: c.getAnimations({subtree: true}).map(x => ({ delay: x.effect.getTiming().delay, ease: x.effect.getTiming().easing.slice(0, 7), k: x.effect.getKeyframes().map(f => f.transform) })) }))""")
    goes = [i for i, c in enumerate(cl) if c['go']]
    dl = [cl[i]['a'][0]['delay'] for i in goes if cl[i]['a']]
    check('clock (화려하게): the changed digits roll one step (new from below), the rightmost first 40ms apart, `roll` curve',
          goes == [2, 3] and dl == [40, 0] and all(cl[i]['a'] and cl[i]['a'][0]['ease'].startswith('linear(') and '14%' in cl[i]['mask'] for i in goes), cl)
    done(ctx, pg)

    # ── status colours ──
    ERRS_before = len(ERRS)
    ctx, pg, adv = page_at(b, '2026-11-13T10:30:05', 1440, motion='standard')
    pg.route('**/api/market*', lambda r: r.fulfill(status=502, content_type='application/json', body='{"error":"x"}'))
    adv(30500); pg.wait_for_timeout(400)
    st = pg.evaluate("""() => { const t = document.querySelector('#strip .xs-t'), w = t && t.querySelector('.xs-warn'), root = getComputedStyle(document.documentElement);
      const probe = v => { const d = document.createElement('i'); d.style.color = v; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; };
      return { text: t && t.textContent, warn: !!w, wc: w && getComputedStyle(w).color, fail: probe('var(--fail-dot)'), txt: t && getComputedStyle(t.firstElementChild).color, acc: probe('var(--acc)') }; }""")
    check('갱신 실패: ! (--fail-dot) + words, the words not in amber', st['warn'] and '갱신 실패' in (st['text'] or '') and st['wc'] == st['fail'] and st['txt'] != st['acc'], st)
    del ERRS[ERRS_before:]                             # the 502s are the point of this step
    pg.unroute('**/api/market*')
    pg.evaluate("document.querySelector('#clock button').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 60, clientY: 30}))")
    pg.wait_for_timeout(1500)
    st = pg.evaluate("""() => { const r = document.querySelector('.xwc-r[data-st="open"] .xwc-st'); const probe = v => { const d = document.createElement('i'); d.style.color = v; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; };
      return { dot: r && getComputedStyle(r, '::before').backgroundColor, live: probe('var(--live)') }; }""")
    check('세계 시각: the 장중 dot is --live', st['dot'] and st['dot'] == st['live'], st)
    done(ctx, pg)

    # ── flat: rail, bands, no painted gradient / drop-shadow anywhere in extras ──
    ctx, pg, adv = page_at(b, '2026-11-13T13:30:05', 1440, motion='standard')
    pg.click('#extras-tools [data-x="replay"]')
    pg.wait_for_function("() => document.querySelector('.rp-time') && document.querySelector('.rp-time').textContent === '09:00'", timeout=15000)
    pg.wait_for_timeout(700)
    st = pg.evaluate("""() => { const sl = document.querySelector('.rp-slider'), rail = document.querySelector('.rp-rail');
      const tr = getComputedStyle(sl, '::-webkit-slider-runnable-track');
      const sel = '#strip, #strip *, #clock, #clock *, #session-bar, #session-bar *, #extras-tools, #extras-tools *, .rp-player, .rp-player *, .xwc, .xwc *';
      const bad = [...document.querySelectorAll(sel)].map(e => { const s = getComputedStyle(e); return [e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className, s.backgroundImage, s.filter, s.boxShadow]; })
        .filter(([c, bg, f, sh]) => /gradient/.test(bg) || /drop-shadow/.test(f));
      const segs = [...document.querySelectorAll('.sb-segs i, .sb-fill i')].map(i => getComputedStyle(i).backgroundImage);
      return { track: tr.backgroundImage, slBg: getComputedStyle(sl).backgroundImage, rail: !!rail, railKids: rail ? rail.querySelectorAll('i').length : 0, pos: rail && rail.style.getPropertyValue('--pos'), bad, segs: [...new Set(segs)] }; }""")
    check('replay rail: flat boxes under a transparent track (no gradient paint)', st['rail'] and st['railKids'] >= 2 and 'gradient' not in st['track'] and 'gradient' not in st['slBg'] and st['pos'], st)
    check('session bar: one flat colour per band (no gradient)', st['segs'] == ['none'], st['segs'])
    check('extras paints no gradient and no drop-shadow (computed, clock · bar · strip · tools · player)', not st['bad'], st['bad'][:6])
    done(ctx, pg)

    # ── type, icons, tooltip, map top — 4 themes ──
    for theme in ('base', 'paper', 'glass-dark', 'glass-light'):
        for w in (390, 768, 1280, 1440):
            ctx, pg, adv = page_at(b, '2026-11-13T10:30:05', w, theme=theme, motion='standard')
            st = pg.evaluate("""() => { const sel = '#strip *, #clock *, #session-bar *, #extras-tools *';
              const sizes = [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null || e.getClientRects().length).filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
                .map(e => [e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className, parseFloat(getComputedStyle(e).fontSize)]);
              const icons = [...document.querySelectorAll('#extras-tools svg:not(.kck):not(.kwn):not(.kspn) path, .xs-pp svg path')].map(p => [getComputedStyle(p).strokeWidth, getComputedStyle(p).vectorEffect, getComputedStyle(p).stroke]);
              return { map: Math.round(document.getElementById('map').getBoundingClientRect().top), sizes, icons, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }; }""")
            off = [s for s in st['sizes'] if s[1] < 11 or round(s[1]) not in SCALE]
            check(f'type [{theme} {w}]: extras text ≥ 11px and on the scale', not off, off[:6])
            stroked = [i for i in st['icons'] if i[2] != 'none']
            check(f'icons [{theme} {w}]: strokes 1.75px on screen (non-scaling)', stroked and all(i[0] == '1.75px' and i[1] == 'non-scaling-stroke' for i in stroked), st['icons'][:4])
            exp = {390: 247, 768: 239, 1280: 207, 1440: 207}[w]       # 768 in session: the template's status row is shorter (250 after hours)
            check(f'map top [{theme} {w}] = {exp}, no overflow', st['map'] == exp and st['sw'] <= st['cw'], (st['map'], st['sw']))
            if w == 1440 and theme == 'base':
                pg.hover('.sb'); pg.wait_for_timeout(450)
                on0 = pg.evaluate("document.querySelector('.sb-tip').classList.contains('on')")
                pg.mouse.move(700, 600); pg.wait_for_timeout(60)
                on1 = pg.evaluate("document.querySelector('.sb-tip').classList.contains('on')")
                pg.wait_for_timeout(400)
                on2 = pg.evaluate("document.querySelector('.sb-tip').classList.contains('on')")
                check('session note: shows on hover, stays ~130ms after leaving, then goes', on0 and on1 and not on2, (on0, on1, on2))
                g = pg.evaluate("[...document.querySelectorAll('.sb-pill svg line, .sb-pill .sb-pi *')].filter(e => getComputedStyle(e).stroke !== 'none').map(e => [getComputedStyle(e).strokeWidth, getComputedStyle(e).vectorEffect])")
                check('session glyphs: strokes 1.5px on screen', g and all(x[0] == '1.5px' and x[1] == 'non-scaling-stroke' for x in g), g[:4])
            done(ctx, pg)
    ctx, pg, adv = page_at(b, '2026-11-13T23:30:05', 768, motion='standard', open_=False)
    m = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top)")
    check('map top [base 768, after hours] = 250', m == 250, m)
    done(ctx, pg)
    check('console errors 0', not ERRS, ERRS[:5])


def main():
    start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(b)
            b.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAILED:', f)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
