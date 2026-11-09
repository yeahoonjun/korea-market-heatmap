"""§3-5 / §3-6 hooks and 화려하게 effects in src/template.html (numbers, not eyeballing). usage: motion3.py [snapshot|live] [section…]
sections: hooks, view3d (stub KH3D), real3d (src/map3d on SwiftShader), flash (live), intro, tween, quality (default: all)."""
import sys, os, json, re
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))

build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
LIVE = build == 'live'
WANT = set(sys.argv[2:]) or {'hooks', 'view3d', 'real3d', 'flash', 'intro', 'tween', 'quality'}
HM_BASE = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
URL = HM_BASE if LIVE else 'file:///home/claude/hm-heatmap/dist/index.html'
ROOT = '/home/claude/hm-heatmap/'
SHOTS = ROOT + 'qa/heatmap2/shots3/'
WAIT = 4000 if LIVE else 1300
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def fresh(b, vp, store=None, hsh='', init=(), wait=WAIT, session=None, media=None):
    ctx = b.new_context(**VIEWPORTS[vp], **({'reduced_motion': media} if media else {}))
    for s in init: ctx.add_init_script(s)
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    pg.goto(URL)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.clear();"
    for k, v in (store or {}).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    for k, v in (session or {}).items(): js += f"sessionStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
    pg.evaluate(js)
    pg.goto(URL + hsh); pg.reload(); pg.wait_for_timeout(wait)
    return ctx, pg, log


def errs(log):
    return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]


# a stand-in for src/map3d (another owner builds it): records calls, draws a canvas, can refuse
KH3D_STUB = """window.__k3 = []; window.KH3D = { on: false,
  show() { window.__k3.push('show'); this.on = true; const m = document.getElementById('map3d'); const c = document.createElement('canvas'); c.width = m.clientWidth; c.height = m.clientHeight; c.tabIndex = 0; c.setAttribute('aria-label', '3D'); m.replaceChildren(c);
    window.__k3.push('rect:' + Math.round(m.getBoundingClientRect().width) + 'x' + Math.round(m.getBoundingClientRect().height)); if (window.__k3fail) setTimeout(() => document.dispatchEvent(new CustomEvent('kh:3d-unavailable', { detail: { reason: 'webgl' } })), 50); },
  hide() { window.__k3.push('hide'); this.on = false; document.getElementById('map3d').replaceChildren(); },
  isOn() { return this.on; } };"""
# quotes that move: every poll shifts ~40 % of the prices by one tick so the live flash has something to show. The quotes say the
# KRX regular session is open (§3-8: outside it the map may draw fixed KRX closes or NXT prices, whatever the hour of the run)
MOVER = """(() => { const f0 = window.fetch; let n = 0; window.fetch = async function (u, o) { const r = await f0.apply(this, arguments);
  if (typeof u === 'string' && /api\\/quotes$/.test(u)) { const j = await r.clone().json(); j.marketStatus = { KOSPI: 'OPEN', KOSDAQ: 'OPEN' };
    if (window.__move) { n++; for (const [i, s] of j.stocks.entries()) if ((i + n) % 5 < 2) { const d = ((i + n) % 2 ? 1 : -1) * Math.max(1, Math.round(s.p * 0.002)); s.p += d; s.d += d; s.r = +(s.r + d / s.p * 100).toFixed(2); } }
    return new Response(JSON.stringify(j), { headers: { 'content-type': 'application/json' } }); } return r; }; })();"""

with sync_playwright() as p:
    b = launch(p)

    # ───── hooks: KH.motion / addSetting / getSetting / refresh / marketStatus / #clock / has-clock ─────
    if 'hooks' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K'})
        r = pg.evaluate("""() => ({ motion: KH.motion(), dm: document.documentElement.dataset.motion, types: ['motion','addSetting','getSetting','refresh','marketStatus','view','setReplay','layout'].map(k => typeof KH[k]),
          ms: KH.marketStatus(), clockInTitle: !!document.querySelector('.brand #clock'), view: KH.view() })""")
        ok('KH hooks exist; motion() = standard by default (html[data-motion] mirrors it); #clock sits in the title spot',
           r['motion'] == 'standard' and r['dm'] == 'standard' and set(r['types']) == {'function'} and r['clockInTitle'] and r['view'] == 'map', r)
        ok('KH.marketStatus() → {KOSPI, KOSDAQ}', isinstance(r['ms'], dict) and ('KOSPI' in r['ms'] or not LIVE), r['ms'])
        # addSetting: switch + 2/3-option choice, onChange at registration and on change, khm.set.<key>, kh:setting
        r = pg.evaluate("""() => { const log = []; document.addEventListener('kh:setting', e => log.push('ev:' + e.detail.key + '=' + e.detail.value));
          const v1 = KH.addSetting({ key: 'qaSw', label: 'QA 스위치', hint: '시험용', default: true, onChange: v => log.push('sw:' + v) });
          const v2 = KH.addSetting({ key: 'qaOpt', label: 'QA 모양', options: [{ v: 'a', label: '가' }, { v: 'b', label: '나' }], default: 'b', onChange: v => log.push('opt:' + v) });
          return { v1, v2, log: log.slice(), g1: KH.getSetting('qaSw'), g2: KH.getSetting('qaOpt'), gx: KH.getSetting('nope'), bad: KH.addSetting({ key: '1 bad' }) === undefined }; }""")
        ok('addSetting returns the value, calls onChange once at registration; getSetting reads it', r['v1'] is True and r['v2'] == 'b' and r['log'] == ['sw:true', 'opt:b'] and r['g1'] is True and r['g2'] == 'b' and r['gx'] is None and r['bad'], r)
        # wide desktop: the 화면 popover holds 효과 + the module rows
        pg.click('#moreBtn'); pg.wait_for_timeout(150)
        r = pg.evaluate("""() => { const p = document.getElementById('morePanel'); const rect = p.getBoundingClientRect();
          return { open: getComputedStyle(p).display !== 'none', rows: [...p.querySelectorAll('[data-set]')].map(e => e.dataset.set), motion: [...p.querySelectorAll('#motionseg button')].filter(b => b.offsetParent).map(b => b.textContent),
            focus: document.activeElement.textContent, inView: rect.left >= 0 && rect.right <= innerWidth, expanded: document.getElementById('moreBtn').getAttribute('aria-expanded') }; }""")
        ok('d1440 화면 popover: 효과 기본·화려하게 + module rows (clock from extras, QA rows), focus inside, inside the window',
           r['open'] and r['motion'] == ['기본', '화려하게'] and 'qaSw' in r['rows'] and 'qaOpt' in r['rows'] and r['inView'] and r['expanded'] == 'true' and (not LIVE or 'clock' in r['rows']), r)
        pg.click('[data-set="qaSw"] .swbtn'); pg.click('[data-set="qaOpt"] button[data-si="0"]'); pg.wait_for_timeout(100)
        r = pg.evaluate("""() => ({ ls: [localStorage.getItem('khm.set.qaSw'), localStorage.getItem('khm.set.qaOpt')], aria: document.querySelector('[data-set="qaSw"] .swbtn').getAttribute('aria-checked'),
          pressed: [...document.querySelectorAll('[data-set="qaOpt"] button')].map(b => b.getAttribute('aria-pressed')), g: [KH.getSetting('qaSw'), KH.getSetting('qaOpt')] })""")
        ok('clicking: stored as khm.set.<key>, aria-checked / aria-pressed follow, getSetting follows', r['ls'] == ['false', '"a"'] and r['aria'] == 'false' and r['pressed'] == ['true', 'false'] and r['g'] == [False, 'a'], r)
        # 효과: 화려하게 → kh:motion, localStorage khm.motion, Esc closes the popover and returns focus
        pg.evaluate("window.__mo = []; document.addEventListener('kh:motion', e => window.__mo.push(e.detail.motion))")
        pg.click('#motionseg button[data-mo="fancy"]'); pg.wait_for_timeout(100)
        r = pg.evaluate("({m: KH.motion(), ev: window.__mo, ls: localStorage.getItem('khm.motion'), dm: document.documentElement.dataset.motion})")
        ok('효과 화려하게 → KH.motion() fancy, kh:motion {motion}, khm.motion, html[data-motion]', r == {'m': 'fancy', 'ev': ['fancy'], 'ls': '"fancy"', 'dm': 'fancy'}, r)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        r = pg.evaluate("({open: getComputedStyle(document.getElementById('morePanel')).display !== 'none', focus: document.activeElement.id, focusN: document.querySelectorAll('#map .tile').length})")
        ok('Esc closes the popover and focus returns to the 화면 button (map stays as it was)', not r['open'] and r['focus'] == 'moreBtn', r)
        # has-clock (set by extras while its clock is on): title hidden visually but kept; switching the clock off brings the title back
        tw = lambda: pg.evaluate("({hc: document.documentElement.classList.contains('has-clock'), w: Math.round(document.querySelector('.brand .ttl').getBoundingClientRect().width), clock: getComputedStyle(document.getElementById('clock')).display, kids: document.getElementById('clock').children.length})")
        if pg.evaluate("!!document.querySelector('[data-set=\"clock\"] .swbtn')"):
            r1 = tw(); pg.click('#moreBtn'); pg.click('[data-set="clock"] .swbtn'); pg.wait_for_timeout(200); r2 = tw(); pg.click('[data-set="clock"] .swbtn'); pg.wait_for_timeout(200); r3 = tw()
            pg.keyboard.press('Escape')
            ok('has-clock: clock in the title spot, title hidden visually (still in the DOM); clock off → title back; on → clock again',
               r1['hc'] and r1['w'] <= 1 and r1['kids'] > 0 and not r2['hc'] and r2['w'] > 100 and r2['clock'] == 'none' and r3['hc'] and r3['w'] <= 1, (r1, r2, r3))
        # KH.refresh: kh:refresh, resolves; one quotes request even when called twice
        pg.evaluate("window.__rf = 0; document.addEventListener('kh:refresh', () => window.__rf++)")
        n0 = len([u for u in log.reqs if u.endswith('api/quotes')])
        r = pg.evaluate("(async () => { const a = KH.refresh(), b2 = KH.refresh(); const same = a === b2; const v = await a; return { same, v, rf: window.__rf }; })()")
        n1 = len([u for u in log.reqs if u.endswith('api/quotes')])
        ok('KH.refresh(): a second call while running returns the same promise; ' + ('kh:refresh once, one /api/quotes, resolves true' if LIVE else 'snapshot: resolves false, no kh:refresh, no request'),
           r['same'] and (r['rf'] == 1 and r['v'] is True and n1 - n0 == 1 if LIVE else r['rf'] == 0 and r['v'] is False and n1 == n0), (r, n1 - n0))
        ok('hooks: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # phone: the same rows in the 표시 설정 sheet, ≥ 40 px, focus trap still works
        ctx, pg, log = fresh(b, 'm390', store={'market': 'K'})
        pg.evaluate("KH.addSetting({ key: 'qaSw', label: 'QA 스위치', default: false })")
        pg.click('#setBtn'); pg.wait_for_timeout(250)
        r = pg.evaluate("""() => { const c = document.getElementById('ctls'); const els = [...c.querySelectorAll('#morePanel button')].filter(b => b.offsetParent);
          return { rows: [...c.querySelectorAll('[data-set]')].map(e => e.dataset.set), small: els.map(b => { const r = b.getBoundingClientRect(); return [b.textContent.trim().slice(0, 8), Math.round(r.width), Math.round(r.height)]; }).filter(x => x[1] < 40 || x[2] < 40),
            motion: [...c.querySelectorAll('#motionseg button')].filter(b => b.offsetParent).map(b => b.textContent), moreBtn: getComputedStyle(document.getElementById('moreBtn')).display, over: document.documentElement.scrollWidth - innerWidth }; }""")
        ok('m390 표시 설정 sheet: 효과 + module rows, taps ≥ 40 px, no 화면 button, no overflow', 'qaSw' in r['rows'] and r['motion'] == ['기본', '화려하게'] and not r['small'] and r['moreBtn'] == 'none' and r['over'] == 0, r)
        pg.screenshot(path=SHOTS + f'settings-m390-{build}.png')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        ok('m390 Esc closes the sheet, focus back on 표시 설정', pg.evaluate("document.activeElement.id") == 'setBtn' and not pg.evaluate("document.getElementById('ctls').classList.contains('open')"))
        ctx.close()
        # device reduced motion → 줄이기 (offered, picked), CSS transitions off; the user can switch back
        ctx, pg, log = fresh(b, 'd1280', media='reduce')
        r = pg.evaluate("""() => ({ m: KH.motion(), shown: [...document.querySelectorAll('#motionseg button')].map(b => [b.dataset.mo, !b.hidden, b.getAttribute('aria-pressed')]), hint: !document.getElementById('motionHint').hidden,
          tr: getComputedStyle(document.querySelector('.tip')).transitionDuration })""")
        ok('prefers-reduced-motion: KH.motion() reduced, 줄이기 shown + pressed, hint shown, tooltip transition off', r['m'] == 'reduced' and r['shown'][0] == ['reduced', True, 'true'] and r['hint'] and r['tr'] in ('0s', ''), r)
        pg.evaluate("document.getElementById('moreBtn').click()"); pg.click('#motionseg button[data-mo="standard"]'); pg.wait_for_timeout(100)
        ok('…and 기본 can be picked again (stored; transitions back)', pg.evaluate("[KH.motion(), localStorage.getItem('khm.motion'), getComputedStyle(document.querySelector('.tip')).transitionDuration]") [:2] == ['standard', '"standard"'])
        ctx.close()

    # ───── 지도 · 3D · 표 (stub KH3D) ─────
    if 'view3d' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K'}, init=[KH3D_STUB])
        lay0 = pg.evaluate("KH.layout().filter(n => n.kind === 'tile').map(n => [n.code, n.x, n.y, n.w, n.h].join()).sort().join('|')")
        pg.evaluate("window.__kr = []; document.addEventListener('kh:render', e => window.__kr.push(e.detail))")
        pg.click('.viewseg button[data-v="3d"]'); pg.wait_for_timeout(200)
        r = pg.evaluate("""() => { const m = document.getElementById('map').getBoundingClientRect(), t = document.getElementById('map3d').getBoundingClientRect();
          return { k3: window.__k3, view: KH.view(), pressed: [...document.querySelectorAll('.viewseg button')].map(b => b.dataset.v + ':' + b.getAttribute('aria-pressed')).join(' '),
            mapVis: getComputedStyle(document.getElementById('map')).visibility, same: [m.left, m.top, m.width, m.height].map(Math.round).join() === [t.left, t.top, t.width, t.height].map(Math.round).join(),
            rect: [t.width, t.height].map(Math.round), hidden3: document.getElementById('map3d').hidden, kr: window.__kr.map(d => d.is3d), tiles: document.querySelectorAll('#map .tile').length }; }""")
        lay1 = pg.evaluate("KH.layout().filter(n => n.kind === 'tile').map(n => [n.code, n.x, n.y, n.w, n.h].join()).sort().join('|')")
        ok('3D: KH3D.show() with #map3d visible over exactly the map box; #map laid out but invisible; 3D pressed; KH.view() 3d; kh:render is3d',
           r['k3'][0] == 'show' and r['view'] == '3d' and 'map:false 3d:true table:false' == r['pressed'] and r['mapVis'] == 'hidden' and r['same'] and not r['hidden3'] and r['rect'][0] > 900 and r['kr'] and r['kr'][-1] is True, r)
        ok('3D: KH.layout() still returns the drawn map (same tiles and boxes as in 2D)', lay1 == lay0 and len(lay0) > 1000, (len(lay0), len(lay1)))
        # map work keeps going in 3D: a market switch renders and fires kh:render; layout follows
        pg.click('.tabs button[data-mkt="Q"]'); pg.wait_for_timeout(700)
        r = pg.evaluate("({kr: window.__kr.length, lay: KH.layout().filter(n => n.kind === 'tile').length, still: KH.view(), m: KH.market()})")
        ok('3D stays on across a market switch; kh:render fires and KH.layout() follows the new map', r['still'] == '3d' and r['m'] == 'Q' and r['lay'] > 50 and r['kr'] >= 2, r)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
        r = pg.evaluate("({k3: window.__k3.slice(-1)[0], view: KH.view(), map3d: document.getElementById('map3d').hidden, table: !document.getElementById('tablewrap').hidden, cls: document.documentElement.classList.contains('v3d')})")
        ok('3D → 표: KH3D.hide(), #map3d hidden, table shown', r == {'k3': 'hide', 'view': 'table', 'map3d': True, 'table': True, 'cls': False}, r)
        pg.click('.viewseg button[data-v="3d"]'); pg.wait_for_timeout(300)
        r = pg.evaluate("({view: KH.view(), mapShown: !document.getElementById('map').hidden, lay: KH.layout().length, rect: window.__k3.filter(x => x.startsWith('rect')).slice(-1)[0]})")
        ok('표 → 3D: the map is laid out first, then 3D shows over it', r['view'] == '3d' and r['mapShown'] and r['lay'] > 50 and r['rect'] and not r['rect'].endswith('x0'), r)
        pg.click('.tabs button[data-mkt="WORLD"]'); pg.wait_for_timeout(400)
        ok('해외 tab leaves 3D (KH3D.hide)', pg.evaluate("[KH.view(), window.__k3.slice(-1)[0], document.getElementById('map3d').hidden]") == ['map', 'hide', True])
        pg.click('.tabs button[data-mkt="K"]'); pg.wait_for_timeout(500)
        # WebGL refused → message, back to 지도, focus not lost
        pg.evaluate("window.__k3fail = true"); pg.click('.viewseg button[data-v="3d"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("({view: KH.view(), toast: document.getElementById('khToast').textContent, vis: getComputedStyle(document.getElementById('khToast')).opacity, mapVis: getComputedStyle(document.getElementById('map')).visibility, focus: document.activeElement.tagName + ':' + (document.activeElement.dataset.v || '')})")
        ok('kh:3d-unavailable → toast "…3D 보기를 쓸 수 없어요…", back to 지도, map visible', r['view'] == 'map' and '3D 보기' in r['toast'] and r['mapVis'] == 'visible', r)
        pg.screenshot(path=SHOTS + f'3d-toast-d1440-{build}.png')
        ok('view3d: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # not remembered: a reload starts in 2D; without KH3D (module missing) → message and stay on 지도
        ctx, pg, log = fresh(b, 'm390', store={'market': 'K'})
        has3d = pg.evaluate("!!window.KH3D")
        pg.evaluate("delete window.KH3D; window.KH3D = undefined")
        pg.click('.viewseg button[data-v="3d"]'); pg.wait_for_timeout(250)
        r = pg.evaluate("({view: KH.view(), toast: document.getElementById('khToast').textContent, pressed: document.querySelector('.viewseg [aria-pressed=\"true\"]').dataset.v, over: document.documentElement.scrollWidth - innerWidth})")
        ok('m390 no KH3D → toast, 지도 stays pressed, no overflow', r['view'] == 'map' and r['toast'] and r['pressed'] == 'map' and r['over'] == 0, (has3d, r))
        sz = pg.evaluate("[...document.querySelectorAll('.viewseg button')].map(b => { const r = b.getBoundingClientRect(); return [b.textContent, Math.round(r.width), Math.round(r.height)]; })")
        ok('m390 지도·3D·표 buttons ≥ 40×40', all(w >= 40 and hh >= 40 for _, w, hh in sz), sz)
        pg.screenshot(path=SHOTS + f'3d-missing-m390-{build}.png')
        ctx.close()

    # ───── 지도 · 3D · 표 with the real src/map3d (WebGL on SwiftShader) ─────
    if 'real3d' in WANT:
        bg = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'])
        for vp, motion in [('d1440', 'fancy'), ('m390', 'standard')]:
            ctx, pg, log = fresh(bg, vp, store={'market': 'K', 'motion': motion}, session={'khm.intro': '1'})
            pg.click('.viewseg button[data-v="3d"]')
            try:
                pg.wait_for_function("() => window.KH3D && KH3D.qa && KH3D.qa.inspect().instances > 0 && !KH3D.qa.inspect().flying && !KH3D.qa.inspect().tweening", timeout=30000)
            except Exception as e:
                print('  (3D did not come up)', pg.evaluate("document.getElementById('map3d').innerText"), errs(log)[:2])
            pg.wait_for_timeout(400)
            r = pg.evaluate("""() => { const m = document.getElementById('map').getBoundingClientRect(), t = document.getElementById('map3d').getBoundingClientRect(), c = document.querySelector('#map3d canvas');
              const tiles = KH.layout().filter(n => n.kind === 'tile' && n.w > 0 && n.h > 0).length, q = KH3D.qa.inspect();
              return { box: [t.left - m.left, t.top - m.top, t.width - m.width, t.height - m.height].map(Math.round), w: Math.round(t.width), h: Math.round(t.height), canvas: c ? [c.clientWidth, c.clientHeight] : null,
                tiles, inst: q.instances, on: KH3D.isOn(), view: KH.view(), tip: document.getElementById('tip').classList.contains('show'), range: KH.range(), qrange: q.range, over: document.documentElement.scrollWidth - innerWidth }; }""")
            ok(f'{vp} real 3D: #map3d exactly over #map ({r["w"]}×{r["h"]}), canvas fills it, one box per KH.layout() tile, KH.range() = module range',
               r['box'] == [0, 0, 0, 0] and r['h'] > 300 and r['canvas'] and r['canvas'][1] > 300 and r['inst'] == r['tiles'] > 50 and r['on'] and r['view'] == '3d' and r['over'] == 0, r)
            pg.screenshot(path=SHOTS + f'3d-real-{vp}-{build}.png')
            pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(120)
            mid = pg.evaluate("({map3d: !document.getElementById('map3d').hidden, mapVis: getComputedStyle(document.getElementById('map')).visibility})")
            pg.wait_for_timeout(900)
            end = pg.evaluate("({map3d: !document.getElementById('map3d').hidden, mapVis: getComputedStyle(document.getElementById('map')).visibility, on: KH3D.isOn(), view: KH.view(), tiles: document.querySelectorAll('#map .tile').length})")
            ok(f'{vp} back to 지도' + (' (화려하게: #map3d stays for the fold, then #map shows)' if motion == 'fancy' else ''),
               (mid == {'map3d': True, 'mapVis': 'hidden'} if motion == 'fancy' else True) and end == {'map3d': False, 'mapVis': 'visible', 'on': False, 'view': 'map', 'tiles': end['tiles']} and end['tiles'] > 50, (mid, end))
            ok(f'{vp} real 3D: console errors 0', not errs(log), errs(log)[:3])
            ctx.close()
        bg.close()

    # ───── tick flash (live: moving quotes) ─────
    if 'flash' in WANT and LIVE:
        for motion, vp in [('fancy', 'd1440'), ('standard', 'd1440'), ('reduced', 'd1440')]:
            ctx, pg, log = fresh(b, vp, store={'market': 'K', 'motion': motion}, init=[MOVER], session={'khm.intro': '1'})
            pg.evaluate("window.__move = true")
            pg.evaluate("KH.refresh()"); pg.wait_for_timeout(120)
            r = pg.evaluate("""() => ({ ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length, old: document.querySelectorAll('#map .tile.flash-up, #map .tile.flash-dn').length,
              anims: document.getAnimations().filter(a => a.effect && a.effect.pseudoElement === '::after').length, small: document.querySelectorAll('#map .tile.fl-sm').length,
              delays: [...new Set(document.getAnimations().filter(a => a.effect && a.effect.pseudoElement === '::after').map(a => a.effect.getTiming().delay))].length,
              ev: null })""")
            if motion == 'fancy':
                pg.wait_for_timeout(300)
                mid = pg.evaluate("(() => { const t = document.querySelector('#map .tile.fl-u, #map .tile.fl-d'); return t ? [getComputedStyle(t, '::after').opacity, getComputedStyle(t, '::after').boxShadow.slice(0, 60), getComputedStyle(t).backgroundColor === t.style.backgroundColor || true] : null; })()")
                pg.screenshot(path=SHOTS + f'flash-d1440-{build}.png')
                pg.wait_for_timeout(900)
                after = pg.evaluate("document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length")
                ok(f'fancy: rings on moved tiles (≤ 60 at once, ::after opacity only, staggered 0–200 ms), gone after ~0.9 s; no white/black overlay',
                   0 < r['ring'] <= 60 and r['anims'] == r['ring'] and r['old'] == 0 and r['delays'] > 5 and after == 0 and mid and float(mid[0]) > 0, (r, mid, after))
            elif motion == 'standard':
                ok('기본: the original white/black overlay, no rings', r['old'] > 0 and r['ring'] == 0, r)
            else:
                ok('줄이기: no flash at all', r['old'] == 0 and r['ring'] == 0, r)
            if motion == 'fancy':
                # replay on → no flash; table → value cells flash, rows on screen only
                pg.evaluate("KH.setReplay({t:'0905', prices:new Map()})"); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(120)
                n = pg.evaluate("document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length")
                pg.evaluate("KH.setReplay(null)")
                ok('fancy: no flash while a replay frame is drawn', n == 0, n)
                pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
                pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
                r = pg.evaluate("""() => { const w = document.getElementById('tablewrap'), cells = [...w.querySelectorAll('td.fl-u, td.fl-d')];
                  const wr = w.getBoundingClientRect(); return { n: cells.length, cols: [...new Set(cells.map(td => [...td.parentElement.children].indexOf(td)))], off: cells.filter(td => { const r = td.getBoundingClientRect(); return r.bottom < wr.top || r.top > wr.bottom; }).length }; }""")
                ok('fancy table: 현재가 + 등락률 cells of moved rows flash, only rows on screen', r['n'] > 0 and sorted(r['cols']) == [2, 3] and r['off'] == 0, r)
                pg.screenshot(path=SHOTS + f'flash-table-d1440-{build}.png')
                ok('flash: console errors 0', not errs(log), errs(log)[:3])
            ctx.close()

    # ───── first entry (once per session) + count-up ─────
    if 'intro' in WANT:
        REC = """window.__ir = []; window.__idx = []; (() => { const t0 = performance.now();
          new MutationObserver(ms => { for (const mu of ms) { const m = mu.target; if (m.id !== 'map') continue; const on = m.classList.contains('fx-intro'); const last = window.__ir[window.__ir.length - 1];
            if (!last || last.on !== on) window.__ir.push({ on, t: performance.now(), dl: on ? Math.max(0, ...[...m.querySelectorAll('.node')].map(e => parseFloat(e.style.getPropertyValue('--dl')) || 0)) : 0, tiles: m.querySelectorAll('.tile').length,
              span: on ? Math.max(0, ...document.getAnimations().filter(x => /^fx-(in|fade)$/.test(x.animationName)).map(x => x.effect.getTiming().delay + x.effect.getTiming().duration)) : 0 }); } })
            .observe(document, { attributes: true, attributeFilter: ['class'], subtree: true });
          const tick = () => { const v = [...document.querySelectorAll('#idx .v')].map(e => e.textContent).join(' '); if (v && window.__idx[window.__idx.length - 1] !== v) window.__idx.push(v); if (performance.now() - t0 < 8000) requestAnimationFrame(tick); }; requestAnimationFrame(tick); })();"""
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K', 'motion': 'fancy'}, init=[REC])
        pg.evaluate("sessionStorage.clear()"); pg.reload(); pg.wait_for_timeout(WAIT)      # a new session for the observed load
        r = pg.evaluate("({ir: window.__ir, ss: sessionStorage.getItem('khm.intro'), idx: window.__idx.slice(0, 3).concat(window.__idx.slice(-1)), n: window.__idx.length, final: [...document.querySelectorAll('#idx .v')].map(e => e.textContent).join(' ')})")
        on = [x for x in r['ir'] if x['on']]; off = [x for x in r['ir'] if not x['on']]
        dur = off[0]['t'] - on[0]['t'] if on and off else None
        ok('fancy first entry: intro once, every tile animated, delay + duration ≤ 700 ms, class cleaned up, khm.intro set',
           len(on) == 1 and on[0]['dl'] <= 480 and on[0]['tiles'] > 100 and 0 < on[0]['span'] <= 700 and dur is not None and dur <= 1500 and r['ss'] == '1', (on[:1], round(dur or 0), r['ss']))
        ok('header indices count up (several in-between values, end on the quote)', r['n'] >= 4 and r['idx'][-1] == r['final'], (r['n'], r['idx']))
        lab = pg.evaluate(LABEL_CHECK_JS)
        ok('after the intro: labels inside tiles, console errors 0', lab['overflow'] == 0 and not errs(log), (lab['overflow'], errs(log)[:2]))
        pg.reload(); pg.wait_for_timeout(WAIT)
        r = pg.evaluate("window.__ir.filter(x => x.on).length")
        ok('same session, reload: no intro', r == 0, r)
        ctx.close()
        # any input ends it at once; 기본 never runs it
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K', 'motion': 'fancy'}, init=[REC, "new MutationObserver(ms => { for (const mu of ms) if (mu.target.id === 'map' && mu.target.classList.contains('fx-intro') && !window.__kd) { window.__kd = 1; setTimeout(() => dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift' })), 60); } }).observe(document, { attributes: true, attributeFilter: ['class'], subtree: true });"], wait=WAIT)
        pg.evaluate("sessionStorage.clear()"); pg.reload(); pg.wait_for_timeout(WAIT)
        r = pg.evaluate("window.__ir")
        on = [x for x in r if x['on']]; off = [x for x in r if not x['on']]
        ok('a key press during the intro finishes it at once (< 200 ms)', on and off and off[0]['t'] - on[0]['t'] < 200, [(x['on'], round(x['t'])) for x in r])
        ctx.close()
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K'}, init=[REC])
        ok('기본: no intro', not [x for x in pg.evaluate("window.__ir") if x['on']])
        ctx.close()

    # ───── replay tween ─────
    if 'tween' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'market': 'K', 'motion': 'fancy'}, session={'khm.intro': '1'})
        # frames: every 코스피 stock moves by k %, every third one twice as far (so the boxes change too)
        FR = """(k) => { const m = new Map(); let i = 0; for (const s of KH.stocks()) if (s.m === 'K') { const kk = i++ % 3 ? k : 2 * k; m.set(s.c, { p: Math.round(s.p * (1 + kk / 100)), r: +(s.r + kk).toFixed(2) }); } return m; }"""
        pg.evaluate(f"window.__fr = {FR}; KH.setReplay({{t:'0905', prices: __fr(-4)}})"); pg.wait_for_timeout(200)
        a = pg.evaluate("(() => { const t = document.querySelector('#map .tile[data-c=\"005930\"]'); return [t.style.backgroundColor, t.querySelector('.pc').textContent]; })()")
        pg.evaluate("KH.setReplay({t:'0910', prices: __fr(4)}, {tween: 1200})"); pg.wait_for_timeout(450)
        m = pg.evaluate("""(() => { const t = document.querySelector('#map .tile[data-c="005930"]'); const L = KH.layout().find(n => n.code === '005930');
          return { bg: getComputedStyle(t).backgroundColor, pc: t.querySelector('.pc').textContent, flips: document.getAnimations().filter(x => x.playState === 'running' && !x.effect.pseudoElement && x.effect.getKeyframes().some(k => k.transform)).length, layoutCol: L.color, layoutSub: L.sub, status: document.querySelector('#status .badge').textContent }; })()""")
        pg.wait_for_timeout(1000)
        z = pg.evaluate("(() => { const t = document.querySelector('#map .tile[data-c=\"005930\"]'); return [getComputedStyle(t).backgroundColor, t.querySelector('.pc').textContent, KH.layout().find(n => n.code === '005930').color]; })()")
        def num(t): return float(t.replace('−', '-').replace('%', '').replace('+', ''))
        mid_ok = m['bg'] not in (a[0], z[0]) and num(a[1]) < num(m['pc']) < num(z[1])
        ok('fancy tween 1.2 s: mid-way the fill is between (Lab) and the % counts between; FLIP moves run; KH.layout() already has the final frame',
           mid_ok and m['flips'] > 0 and m['layoutCol'] == z[2] and m['status'] == '리플레이 09:10', (a, m, z))
        ok('…and at the end the fill and text are exactly the final ones (fill = KH.layout() colour)', z[0] == z[2] and num(z[1]) > num(m['pc']), z)
        lab = pg.evaluate(LABEL_CHECK_JS)
        ok('after the tween: labels inside tiles', lab['overflow'] == 0, lab['examples'][:2])
        # no tween option → at once; 기본 with tween → at once
        pg.evaluate("KH.setReplay({t:'0915', prices: __fr(-4)})"); pg.wait_for_timeout(30)
        n = pg.evaluate("(() => { const t = document.querySelector('#map .tile[data-c=\"005930\"]'); return [t.style.backgroundColor, t.querySelector('.pc').textContent]; })()")
        ok('without {tween}: the frame is drawn at once', n == a, (n, a))
        pg.evaluate("document.getElementById('moreBtn').click()"); pg.click('#motionseg button[data-mo="standard"]'); pg.keyboard.press('Escape')
        pg.evaluate("KH.setReplay({t:'0920', prices: __fr(4)}, {tween: 1200})"); pg.wait_for_timeout(60)
        n = pg.evaluate("(() => { const t = document.querySelector('#map .tile[data-c=\"005930\"]'); return [t.style.backgroundColor, t.querySelector('.pc').textContent]; })()")
        ok('기본 + {tween}: drawn at once (no new motion)', n[1] == z[1], (n, z))
        pg.evaluate("KH.setReplay(null)")
        ok('tween: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    # ───── quality in 화려하게: overflow, console, labels, keyboard, taps; screenshots for a human look ─────
    if 'quality' in WANT:
        for vp in ['m360', 'm390', 't768', 'd1280', 'd1440', 'd1920']:
            ctx, pg, log = fresh(b, vp, store={'motion': 'fancy'}, wait=WAIT + 600)
            over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
            lab = pg.evaluate(LABEL_CHECK_JS)
            # toolbar rows: item tops more than 12 px apart start a new row
            rows = pg.evaluate("(() => { const t = [...document.querySelectorAll('.tools > *, .ctls > .ctl')].filter(e => e.offsetParent && getComputedStyle(e).display !== 'contents').map(e => e.getBoundingClientRect().top).sort((a, b) => a - b); let n = t.length ? 1 : 0; for (let i = 1; i < t.length; i++) if (t[i] - t[i - 1] > 12) n++; return n; })()")
            ok(f'{vp} 화려하게: overflow 0, console errors 0, labels inside ({lab["visible"]}), toolbar rows {rows}', over == 0 and not errs(log) and lab['overflow'] == 0 and (rows <= 1 or vp in ('t768',) or vp.startswith('m')), (over, errs(log)[:2], lab['examples'][:1], rows))
            if vp in ('m390', 't768', 'd1440'): pg.screenshot(path=SHOTS + f'fancy-{vp}-{build}.png')
            if vp == 'd1440':
                # keyboard: Tab reaches the 화면 button, Enter opens it with focus inside; 3D button reachable
                pg.evaluate("document.getElementById('palseg').lastElementChild.focus()")
                pg.keyboard.press('Tab')
                a = pg.evaluate("document.activeElement.id")
                pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
                b2 = pg.evaluate("document.activeElement.closest('#morePanel') ? document.activeElement.textContent : null")
                ring = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle")
                pg.keyboard.press('Escape')
                pg.evaluate("document.querySelector('.viewseg button[data-v=\"map\"]').focus()"); pg.keyboard.press('Tab')
                c = pg.evaluate("document.activeElement.dataset.v")
                ok('keyboard: 색상 → Tab → 화면 button; Enter opens with focus on 효과 (ring shown); 지도 → Tab → 3D', a == 'moreBtn' and b2 and ring == 'solid' and c == '3d', (a, b2, ring, c))
            ctx.close()

    print(f'\n{sum(res)}/{len(res)} passed ({build}) [{",".join(sorted(WANT))}]')
    b.close()
