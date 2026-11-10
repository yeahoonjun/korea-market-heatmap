"""§3-16 QA: today's change under the market tabs + the ★관심 tab's group choice.

Usage: python3 qa/tabs/qa_tabs.py [live_url] [snapshot_url]
Needs this worktree's static server (8811) + Worker dev harness (8812) for the live page.
"""
import json, sys, time
sys.path.insert(0, '/home/claude/hm-tabs/qa')
from common import launch, VIEWPORTS
from playwright.sync_api import sync_playwright

LIVE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8812/'
SNAP = sys.argv[2] if len(sys.argv) > 2 else 'file:///home/claude/hm-tabs/dist/index.html'
OUT = '/home/claude/hm-tabs/qa/tabs/shots'
GROUPS = {"v": 1, "groups": [{"id": "g0", "name": "기본", "codes": ["005930", "000660", "035420", "005380", "247540"]},
                             {"id": "gsemi", "name": "반도체", "codes": ["005930", "000660", "042700", "403870", "058470"]}], "active": "all"}
RES = {'fail': [], 'ok': 0}


def check(cond, what, detail=''):
    if cond:
        RES['ok'] += 1
    else:
        RES['fail'].append(f'{what} {detail}')
        print('FAIL', what, detail)


GEOM = r"""() => {
  const R = e => e ? e.getBoundingClientRect() : null;
  const tabs = document.querySelector('.tabs'), btns = [...tabs.querySelectorAll('button')];
  const ico = document.querySelector('.sb-ico'), ir = ico && ico.offsetParent !== null ? R(ico) : null;
  // ink bottom of the numbers (≈ line box minus the font's descent below the digits)
  let lineBot = 0, lineTop = 1e9; for (const t of tabs.querySelectorAll('.tp, .tn')) { if (!t.textContent) continue; const rg = document.createRange(); rg.selectNodeContents(t); const rr = rg.getBoundingClientRect(); lineBot = Math.max(lineBot, rr.bottom); lineTop = Math.min(lineTop, rr.top); }
  const vis = e => e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const st = document.querySelector('#status'), br = document.querySelector('.brand');
  return {
    mapTop: Math.round(R(document.querySelector('#map')).top + scrollY),
    overflow: document.documentElement.scrollWidth - innerWidth,
    heights: btns.map(b => Math.round(R(b).height)),
    tabsRow: [Math.round(R(tabs).top), Math.round(R(tabs).bottom)],
    statusTop: vis(st) ? Math.round(R(st).top) : null, brandTop: Math.round(R(br).top),
    icoTop: ir ? +ir.top.toFixed(1) : null, icoBot: ir ? +ir.bottom.toFixed(1) : null, numLineBot: +lineBot.toFixed(1), nameLineTop: +lineTop.toFixed(1),
    tabScroll: [tabs.scrollWidth, tabs.clientWidth],
  };
}"""


def page(b, vk, url, seed=None, motion=None, extra_storage=None, wait=2600):
    ctx = b.new_context(**VIEWPORTS[vk])
    pg = ctx.new_page()
    errs, reqs = [], []
    pg.on('pageerror', lambda e: errs.append(f'pageerror {e}'))
    pg.on('console', lambda m: errs.append(f'console {m.text}') if m.type == 'error' else None)
    pg.on('request', lambda r: reqs.append(r.url))
    base = url.split('#')[0]
    pg.goto(base)
    pg.evaluate("""([g, mo, ex]) => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k);
      if (g) localStorage.setItem('khm.watchGroups', JSON.stringify(g)); if (mo) localStorage.setItem('khm.motion', JSON.stringify(mo));
      for (const [k, v] of Object.entries(ex || {})) localStorage.setItem(k, JSON.stringify(v)); }""", [seed, motion, extra_storage])
    pg.goto(url)
    pg.reload()
    pg.wait_for_timeout(wait)
    return ctx, pg, errs, reqs


def tabinfo(pg):
    return pg.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.tabs button[data-mkt]')].map(b => { const t = b.querySelector('.tp');
      return [b.dataset.mkt, { txt: t ? t.textContent : null, cls: t ? t.className : null, aria: b.getAttribute('aria-label'), title: b.title,
        color: t ? getComputedStyle(t).color : null }]; }))""")


def css_var(pg, name):
    return pg.evaluate("n => { const d = document.createElement('span'); d.style.color = `var(${n})`; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }", name)


def fmt(v):
    v = round(v, 2)
    s = '+' if v > 0 else '−' if v < 0 else ''
    return f'{s}{abs(v):.2f}%'


def layout_sweep(b):
    print('== layout sweep')
    rows = []
    for name, url in (('live', LIVE + '#kospi'), ('snapshot', SNAP + '#kospi')):
        for vk in ('m360', 'm390', 't768', 'd1280', 'd1920'):
            ctx, pg, errs, _ = page(b, vk, url, seed=GROUPS)
            g = pg.evaluate(GEOM)
            w = VIEWPORTS[vk]['viewport']['width']
            pg.screenshot(path=f'{OUT}/qa-{name}-{vk}.png', clip={'x': 0, 'y': 0, 'width': w, 'height': 300})
            check(g['overflow'] <= 0, f'{name} {vk} overflow', g['overflow'])
            check(not errs, f'{name} {vk} console', errs[:2])
            check(len(set(g['heights'])) == 1, f'{name} {vk} tab heights uniform', g['heights'])
            if w <= 760:
                check(min(g['heights']) >= 40, f'{name} {vk} tab height ≥ 40', g['heights'])
            if w >= 1280:
                one = g['statusTop'] is not None and g['statusTop'] < g['tabsRow'][1] and g['brandTop'] < g['tabsRow'][1]
                check(one, f'{name} {vk} header one row', g)
            if g['icoTop'] is not None and g['numLineBot']:
                # the session icon is either under the tab row (desktop) or above it (phones: the bar sits between the clock row and
                # the tabs); line boxes carry ~2px of leading beyond the ink, hence the tolerance
                clear = g['icoTop'] >= g['numLineBot'] - 2.5 or g['icoBot'] <= g['nameLineTop'] + 2.5
                check(clear, f'{name} {vk} tab text clear of session icon', g)
            rows.append(dict(build=name, vp=vk, **{k: g[k] for k in ('mapTop', 'heights', 'icoTop', 'icoBot', 'nameLineTop', 'numLineBot', 'tabScroll')}))
            ctx.close()
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))


def clock_modes(b):
    print('== clock modes @390')
    out = {}
    for name, url in (('live', LIVE + '#kospi'), ('snapshot', SNAP + '#kospi')):
        for style, on in (('digital', True), ('analog', True), ('both', True), ('off', False)):
            ex = {'khm.set.clockStyle': 'digital' if style == 'off' else style, 'khm.set.clock': on}
            ctx, pg, errs, _ = page(b, 'm390', url, seed=GROUPS, extra_storage=ex)
            g = pg.evaluate(GEOM)
            hc = pg.evaluate("() => document.documentElement.classList.contains('has-clock')")
            out[f'{name}/{style}'] = g['mapTop']
            check(not errs, f'clock {name} {style} console', errs[:2])
            check(hc == on, f'clock {name} {style} has-clock', hc)
            pg.screenshot(path=f'{OUT}/qa-clock-{name}-{style}.png', clip={'x': 0, 'y': 0, 'width': 390, 'height': 260})
            ctx.close()
    print(json.dumps(out, ensure_ascii=False))
    return out


def values_live(b):
    print('== values (live)')
    ctx, pg, errs, reqs = page(b, 'd1280', LIVE + '#kospi', seed=GROUPS)
    t = tabinfo(pg)
    ix = pg.evaluate('() => KH.index()')
    for m, k, nm in (('K', 'KOSPI', '코스피'), ('Q', 'KOSDAQ', '코스닥')):
        check(t[m]['txt'] == fmt(ix[k]['ratio']), f'{m} = index ratio', (t[m]['txt'], ix[k]['ratio']))
        check(t[m]['aria'] == f"{nm} {t[m]['txt']}", f'{m} aria', t[m]['aria'])
    # 전체: the two ratios weighted by the rows' cap sums
    calc = pg.evaluate("""() => { const ix = KH.index(), s = KH.stocks(); let K = 0, Q = 0; for (const r of s) if (r.cap > 0) { if (r.m === 'K') K += r.cap; else Q += r.cap; }
      const a = +ix.KOSPI.ratio, b = +ix.KOSDAQ.ratio; return ((K + Q) / (K / (1 + a / 100) + Q / (1 + b / 100)) - 1) * 100; }""")
    check(t['ALL']['txt'] == fmt(calc), '전체 = cap-weighted', (t['ALL']['txt'], calc))
    check('시가총액' in t['ALL']['title'], '전체 tooltip says cap-weighted', t['ALL']['title'])
    # colours follow the palette variables
    for m in ('K', 'Q', 'ALL', 'WATCH'):
        c = t[m]['cls'].split()
        want = 'up' if t[m]['txt'].startswith('+') else 'dn' if t[m]['txt'].startswith('−') else 'flat'
        check(want in c, f'{m} class', t[m])
    up = css_var(pg, '--up-text')
    check(t['K']['color'] == up or not t['K']['txt'].startswith('+'), 'K colour = --up-text', (t['K']['color'], up))
    # switch palette (2nd option) → the colour follows
    pg.click('#palseg button:nth-child(2)')
    pg.wait_for_timeout(300)
    t2 = tabinfo(pg)
    up2, dn2 = css_var(pg, '--up-text'), css_var(pg, '--dn-text')
    exp = up2 if t2['K']['txt'].startswith('+') else dn2 if t2['K']['txt'].startswith('−') else None
    check(exp is None or t2['K']['color'] == exp, 'palette change recolours', (t2['K']['color'], exp))
    # colour metric (1주) does not change the tab numbers
    pg.evaluate("() => { const b = document.querySelector('[data-key=\"colorBy\"] button[data-v=\"w1\"]'); b.click(); }")
    pg.wait_for_timeout(1200)
    t3 = tabinfo(pg)
    check(t3['K']['txt'] == fmt(pg.evaluate('() => KH.index().KOSPI.ratio')), 'colour metric ignored', t3['K'])
    # 관심 (전체 관심) = the watch map's header number
    pg.evaluate("() => { const b = document.querySelector('[data-key=\"colorBy\"] button[data-v=\"r\"]'); b.click(); }")
    pg.evaluate("() => { location.hash = '#watch'; }")
    pg.wait_for_timeout(2500)
    stat = pg.evaluate("() => document.querySelector('#crumbs .stat').textContent")
    t4 = tabinfo(pg)
    check(t4['WATCH']['txt'] and t4['WATCH']['txt'] in stat, '관심 tab = watch header (전체)', (t4['WATCH']['txt'], stat))
    # a group's own map (반도체) vs the tab after choosing it
    pg.evaluate("() => KH.watch.setActive('gsemi')")
    pg.wait_for_timeout(1500)
    stat2 = pg.evaluate("() => document.querySelector('#crumbs .stat').textContent")
    pg.evaluate("() => { document.querySelector('#wtabseg button[data-wt=\"gsemi\"]').click(); }")
    pg.wait_for_timeout(300)
    t5 = tabinfo(pg)
    check(t5['WATCH']['txt'] and t5['WATCH']['txt'] in stat2, '관심 tab = watch header (반도체)', (t5['WATCH']['txt'], stat2))
    check(t5['WATCH']['aria'].startswith('관심종목 · 반도체'), '관심 aria names the group', t5['WATCH']['aria'])
    check(not errs, 'values console', errs[:3])
    ctx.close()


def group_choice(b):
    print('== group choice / persistence')
    for vk in ('m390', 'd1280'):
        ctx, pg, errs, _ = page(b, vk, LIVE + '#kospi', seed=GROUPS)
        # settings: open the 표시 설정 sheet (phones) / the 화면 popover (1280+)
        if VIEWPORTS[vk]['viewport']['width'] < 1280:
            pg.click('#setBtn')
        else:
            pg.click('#moreBtn')
        pg.wait_for_timeout(300)
        row = pg.evaluate("() => { const r = document.querySelector('#wtabRow'); return { hidden: r.hidden, vis: !!r.offsetParent, btns: [...r.querySelectorAll('button')].map(b => [b.textContent, b.getAttribute('aria-pressed')]) }; }")
        check(not row['hidden'] and row['vis'], f'{vk} settings row visible', row)
        check([x[0] for x in row['btns']] == ['전체 관심', '기본', '반도체'], f'{vk} settings options', row['btns'])
        check(row['btns'][0][1] == 'true', f'{vk} default 전체 관심', row['btns'])
        pg.screenshot(path=f'{OUT}/qa-settings-{vk}.png')
        pg.click('#wtabseg button[data-wt="gsemi"]')
        pg.wait_for_timeout(200)
        st = pg.evaluate("() => localStorage.getItem('khm.watchTabGroup')")
        check(st == '"gsemi"', f'{vk} stored', st)
        a1 = tabinfo(pg)['WATCH']['aria']
        check(a1.startswith('관심종목 · 반도체'), f'{vk} tab shows 반도체', a1)
        pg.reload(); pg.wait_for_timeout(2500)
        a2 = tabinfo(pg)['WATCH']['aria']
        check(a2.startswith('관심종목 · 반도체'), f'{vk} persists after reload', a2)
        # ⋯ menu on 기본: choose it, then un-choose it
        pg.evaluate("() => { location.hash = '#watch'; }"); pg.wait_for_timeout(1500)
        pg.evaluate("() => KH.watch.setActive('g0')"); pg.wait_for_timeout(600)
        pg.click('#wgchips [data-gm="g0"]'); pg.wait_for_timeout(250)
        menu = pg.evaluate("() => [...document.querySelectorAll('#wgpop .row')].map(r => [r.textContent, r.getAttribute('aria-pressed')])")
        item = [m for m in menu if m[0].startswith('탭에 이 그룹 등락률 표시')]
        check(item and item[0][1] == 'false', f'{vk} menu item (off)', menu)
        pg.screenshot(path=f'{OUT}/qa-menu-{vk}.png')
        pg.evaluate("() => [...document.querySelectorAll('#wgpop .row')].find(r => r.textContent.startsWith('탭에 이 그룹')).click()")
        pg.wait_for_timeout(250)
        st = pg.evaluate("() => localStorage.getItem('khm.watchTabGroup')")
        check(st == '"g0"', f'{vk} menu stores g0', st)
        foc = pg.evaluate("() => document.activeElement && (document.activeElement.dataset.gm || document.activeElement.dataset.g)")
        check(foc == 'g0', f'{vk} focus back to the chip', foc)
        check(tabinfo(pg)['WATCH']['aria'].startswith('관심종목 · 기본'), f'{vk} tab shows 기본', tabinfo(pg)['WATCH']['aria'])
        pg.click('#wgchips [data-gm="g0"]'); pg.wait_for_timeout(250)
        menu = pg.evaluate("() => [...document.querySelectorAll('#wgpop .row')].map(r => [r.textContent, r.getAttribute('aria-pressed')])")
        item = [m for m in menu if m[0].startswith('탭에 이 그룹 등락률 표시')]
        check(item and item[0][1] == 'true' and '✓' in item[0][0], f'{vk} menu item (on, ✓)', menu)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        check(pg.evaluate("() => document.querySelector('#wgpop').hidden"), f'{vk} Esc closes menu')
        # delete the chosen group → back to 전체 관심
        pg.evaluate("() => KH.watch.deleteGroup('g0')"); pg.wait_for_timeout(300)
        st = pg.evaluate("() => localStorage.getItem('khm.watchTabGroup')")
        a3 = tabinfo(pg)['WATCH']['aria']
        check(st == '"all"' and a3.startswith('관심종목 +') or a3.startswith('관심종목 −') or a3 == '관심종목 0.00%', f'{vk} deleted → 전체 관심', (st, a3))
        hid = pg.evaluate("() => document.querySelector('#wtabRow').hidden")
        check(hid, f'{vk} one group left → settings row hidden', hid)
        # empty watchlist → blank
        pg.evaluate("() => { for (const c of KH.watch.list()) KH.watch.remove(c); }"); pg.wait_for_timeout(300)
        ti = tabinfo(pg)['WATCH']
        check(ti['txt'] == '' and ti['aria'] == '관심종목', f'{vk} empty → blank', ti)
        check(not errs, f'{vk} group choice console', errs[:3])
        ctx.close()


def outside_stream(b):
    print('== watched stock outside the stream (우선주) on the 코스피 tab')
    g = {"v": 1, "groups": [{"id": "g0", "name": "기본", "codes": ["005930", "005935"]}], "active": "all"}
    ctx, pg, errs, reqs = page(b, 'd1280', LIVE + '#kospi', seed=g, wait=4000)
    hit = [u for u in reqs if 'api/quotes?codes=' in u]
    check(any('005935' in u for u in hit), 'extra quotes asked for 005935', hit[:2])
    t = tabinfo(pg)['WATCH']
    check('2종목' in t['title'] and '종목 중' not in t['title'], '관심 covers both codes', t['title'])
    check(not errs, 'outside-stream console', errs[:3])
    ctx.close()


def replay(b):
    print('== replay frame')
    ctx, pg, errs, _ = page(b, 'd1280', LIVE + '#kospi', seed=GROUPS)
    # a frame moving every streamed stock to +1 %: without frame.index → the frame's cap-weighted change (+1.00 %)
    pg.evaluate("""() => { const m = new Map(); for (const s of KH.stocks()) { const base = s.p - s.d; m.set(s.c, { p: base * 1.01, r: 1 }); } KH.setReplay({ t: '1000', prices: m }); }""")
    pg.wait_for_timeout(400)
    t = tabinfo(pg)
    check(t['K']['txt'] == '+1.00%' and t['Q']['txt'] == '+1.00%' and t['ALL']['txt'] == '+1.00%', 'replay without index → frame cap-weighted', (t['K']['txt'], t['Q']['txt'], t['ALL']['txt']))
    check('다시 보기 10:00' in t['K']['title'] and '지도 종목' in t['K']['title'], 'replay tooltip', t['K']['title'])
    check(t['WATCH']['txt'] == '+1.00%', '관심 follows the frame', t['WATCH']['txt'])
    pg.evaluate("""() => { const m = new Map(); for (const s of KH.stocks()) { const base = s.p - s.d; m.set(s.c, { p: base * 1.01, r: 1 }); } KH.setReplay({ t: '1005', prices: m, index: { KOSPI: 1.23, KOSDAQ: { ratio: -0.5 } } }); }""")
    pg.wait_for_timeout(400)
    t = tabinfo(pg)
    check(t['K']['txt'] == '+1.23%' and t['Q']['txt'] == '−0.50%', 'replay frame.index used', (t['K']['txt'], t['Q']['txt']))
    pg.evaluate('() => KH.setReplay(null)'); pg.wait_for_timeout(400)
    t = tabinfo(pg)
    check(t['K']['txt'] == fmt(pg.evaluate('() => KH.index().KOSPI.ratio')), 'replay off → live', t['K'])
    check(not errs, 'replay console', errs[:3])
    ctx.close()


def snapshot_values(b):
    print('== snapshot values')
    ctx, pg, errs, _ = page(b, 'd1280', SNAP + '#kospi', seed=GROUPS)
    t = tabinfo(pg)
    ix = pg.evaluate('() => KH.index()')
    check(t['K']['txt'] == fmt(ix['KOSPI']['ratio']) and t['Q']['txt'] == fmt(ix['KOSDAQ']['ratio']), 'snapshot index', (t['K']['txt'], t['Q']['txt']))
    check('기준' in t['K']['title'], 'snapshot tooltip has the time', t['K']['title'])
    check(t['WATCH']['txt'] != '', 'snapshot 관심 value', t['WATCH'])
    check(not errs, 'snapshot console', errs[:3])
    ctx.close()


def flash(b):
    print('== fancy flash (~25 s of live polls each)')
    out = {}
    for mo in ('fancy', 'standard'):
        ctx, pg, errs, _ = page(b, 'd1280', LIVE + '#kospi', seed=GROUPS, motion=mo)
        pg.evaluate("""() => { window.__fl = 0; window.__chg = 0; new MutationObserver(ms => { for (const m of ms) { if (m.type === 'attributes' && m.target.classList.contains('fl')) window.__fl++; if (m.type === 'childList' || m.type === 'characterData') window.__chg++; } })
          .observe(document.querySelector('.tabs'), { subtree: true, attributes: true, attributeFilter: ['class'], childList: true, characterData: true }); }""")
        pg.wait_for_timeout(25000)
        out[mo] = pg.evaluate('() => [window.__fl, window.__chg]')
        anim = pg.evaluate("() => { const t = document.querySelector('.tabs .tp'); t.classList.add('fl'); const a = getComputedStyle(t).animationName; t.classList.remove('fl'); return a; }")
        out[mo + '-anim'] = anim
        check(not errs, f'flash {mo} console', errs[:3])
        ctx.close()
    print(json.dumps(out))
    check(out['standard'][0] == 0, 'no flash in standard', out)
    check(out['standard-anim'] == 'none' and out['fancy-anim'] == 'tpfl', 'flash CSS only in fancy', out)
    if out['fancy'][1] > 0:
        check(out['fancy'][0] > 0, 'fancy flashes on change', out)


if __name__ == '__main__':
    import os
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None
    with sync_playwright() as p:
        b = launch(p)
        for name, fn in (('layout', layout_sweep), ('clock', clock_modes), ('values', values_live), ('groups', group_choice),
                         ('outside', outside_stream), ('replay', replay), ('snapshot', snapshot_values), ('flash', flash)):
            if only and name not in only:
                continue
            t0 = time.time()
            try:
                fn(b)
            except Exception as e:
                RES['fail'].append(f'{name} crashed: {e}')
                print('CRASH', name, e)
            print(f'   ({time.time() - t0:.0f}s)')
        b.close()
    print(f"\nchecks ok {RES['ok']}, failed {len(RES['fail'])}")
    for f in RES['fail']:
        print(' -', f)
