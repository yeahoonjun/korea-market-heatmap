"""§3-5 / §3-6 hooks and 화려하게 effects in src/template.html (numbers, not eyeballing). usage: motion3.py [snapshot|live] [section…]
sections: hooks, view3d, flash, intro, tween, perf, quality (default: all)."""
import sys, os, json, re
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))

build = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
LIVE = build == 'live'
WANT = set(sys.argv[2:]) or {'hooks', 'view3d', 'flash', 'intro', 'tween', 'perf', 'quality'}
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
# quotes that move: every poll shifts ~40 % of the prices by one tick so the live flash has something to show
MOVER = """(() => { const f0 = window.fetch; let n = 0; window.fetch = async function (u, o) { const r = await f0.apply(this, arguments);
  if (typeof u === 'string' && /api\\/quotes$/.test(u) && window.__move) { const j = await r.clone().json(); n++;
    for (const [i, s] of j.stocks.entries()) if ((i + n) % 5 < 2) { const d = ((i + n) % 2 ? 1 : -1) * Math.max(1, Math.round(s.p * 0.002)); s.p += d; s.d += d; s.r = +(s.r + d / s.p * 100).toFixed(2); }
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

    print(f'\n{sum(res)}/{len(res)} passed ({build}) [{",".join(sorted(WANT))}]')
    b.close()
