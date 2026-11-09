"""§3-8 NXT prices: the KRX · NXT price basis of the heatmap (numbers, not eyeballing). usage: nxt3.py [mock|real] [section…]
mock (default): /api/quotes + /api/breadth answered from nxt_fix phases (a real 11/10 08:21 pre-market capture and phases built
from it), the page clock set to that phase's KST time. real: the dev Worker harness as it is (checks whatever phase it is now).
sections: phases, values, dim, pick, size, replay, flash, quality, keys (default: all)."""
import sys, os, json, re
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
import nxt_fix
from nxt_fix import CLOSE, CLOCK, built

VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
MODEARG = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ('mock', 'real') else 'mock'
WANT = set(a for a in sys.argv[1:] if a not in ('mock', 'real')) or {'phases', 'values', 'dim', 'pick', 'size', 'replay', 'flash', 'quality', 'keys'}
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
ROOT = nxt_fix.ROOT
SHOTS = ROOT + 'qa/heatmap2/shots3/'
THEMES = json.load(open(ROOT + 'web/themes.json'))['themes']
REC = "document.addEventListener('kh:basis', e => (window.__kb = window.__kb || []).push(e.detail));"
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def pct(v): return ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.2f}%'
def won(v): return f'{round(v):,}'
def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]


def fresh(b, vp, phase, store=None, hsh='', hook=None, wait=3500, motion=None):
    ctx = b.new_context(**VIEWPORTS[vp], service_workers='block')
    ctx.add_init_script(REC)
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    hold = None
    if MODEARG == 'mock':
        pg.clock.set_fixed_time(CLOCK[phase])
        hold = nxt_fix.route(pg, phase, quotes_hook=hook)
    pg.goto(URL)
    st = dict({'market': 'K', 'motion': motion or 'standard'}, **(store or {}))
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in st.items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    pg.goto(URL + hsh); pg.reload(); pg.wait_for_timeout(wait)
    return ctx, pg, log, hold


STATE_JS = """() => ({ basis: KH.basis(), seg: document.getElementById('basis').hidden ? null : (document.querySelector('#basis [aria-pressed="true"]') || {}).dataset?.v,
  badge: (document.querySelector('#status .badge .bl') || document.querySelector('#status .badge')).textContent,
  short: (document.querySelector('#status .badge .bs') || {}).textContent || null,
  nonx: document.querySelectorAll('#map .tile.nonx').length, tiles: document.querySelectorAll('#map .tile').length })"""
TILE_JS = "c => { const t = document.querySelector(`#map .tile[data-c=\"${c}\"]`); return t ? t.getAttribute('aria-label') : null; }"


def tile_pct(pg, code):
    a = pg.evaluate(TILE_JS, code)
    return a and a.split(',')[0].split(' ')[-1]


def rows(phase):
    q, br = built(phase)
    return {s['c']: s for s in q['stocks']}, br


with sync_playwright() as p:
    b = launch(p)
    Q, BR = rows('pre')
    SS, HY = Q['005930'], Q['000660']
    K_NONX = [s for s in Q.values() if s['m'] == 'K' and not s.get('nx') and s['c'][-1] == '0' and s['cap'] > 0]
    CS = CLOSE['c']

    # ───── defaults and badges per phase ─────
    if 'phases' in WANT and MODEARG == 'mock':
        exp = {
            'pre': ('nxt', 'nxt', r'NXT 프리마켓 · 08:21 기준', 'NXT 08:21', lambda q: pct(q['005930']['nx']['r'])),
            'gap': ('krx-prev', 'krx', r'KRX 어제 종가', '어제 종가', lambda q: pct(CS['005930'][2])),
            'after': ('nxt', 'nxt', r'NXT 애프터마켓 · 17:40 기준', 'NXT 17:40', lambda q: pct(q['005930']['nx']['r'])),
            'night': ('krx', 'krx', r'KRX 15:30 종가', '15:30 종가', lambda q: pct(CS['005930'][2])),
            'regular': ('krx', None, r'실시간', None, lambda q: pct(q['005930']['r'])),
            'legacy': ('krx', 'krx', r'KRX 15:30 종가', '15:30 종가', lambda q: pct(CS['005930'][2])),
        }
        for ph, (bid, seg, badge, short, want) in exp.items():
            q = {s['c']: s for s in built(ph)[0]['stocks']}
            ctx, pg, log, _ = fresh(b, 'd1440', ph)
            s = pg.evaluate(STATE_JS)
            got = tile_pct(pg, '005930')
            ok(f'{ph}: KH.basis {bid}, pressed {seg}, badge "{badge}" / phones "{short}", 삼성전자 {want(q)}',
               s['basis'] == bid and s['seg'] == seg and re.fullmatch(badge, s['badge']) and s['short'] == short and got == want(q) and not errs(log), (s, got, errs(log)[:2]))
            if ph == 'pre':
                ev = pg.evaluate("window.__kb || []")
                ok('kh:basis fired with {basis:"nxt", phase:"pre", label}', any(e['basis'] == 'nxt' and e['phase'] == 'pre' and e['label'].startswith('NXT 프리마켓') for e in ev), ev)
            if ph in ('night', 'gap', 'legacy'):
                # the other choice: night → the after-market's last NXT price; gap → the pre-market's; legacy → the integrated quote
                pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(500)
                s2 = pg.evaluate(STATE_JS); got2 = tile_pct(pg, '005930')
                if ph == 'legacy':
                    ok('legacy (older Worker): NXT = the integrated quote, "NXT 포함 · 17:40 기준", nothing hatched',
                       s2['basis'] == 'nxt' and s2['badge'] == 'NXT 포함 · 17:40 기준' and got2 == pct(q['005930']['r']) and s2['nonx'] == 0, (s2, got2))
                else:
                    ss = '애프터마켓' if ph == 'night' else '프리마켓'
                    tt = '19:59' if ph == 'night' else '08:21'
                    ok(f'{ph}: NXT = the {ss}\'s last price, "NXT {ss} 마감 · {tt} 기준", 삼성전자 {pct(q["005930"]["nx"]["r"])}',
                       s2['basis'] == 'nxt' and s2['badge'] == f'NXT {ss} 마감 · {tt} 기준' and got2 == pct(q['005930']['nx']['r']) and s2['nonx'] > 0, (s2, got2))
            if ph == 'regular':
                ok('regular: no control, no hatching, every tile the live KRX quote', s['nonx'] == 0 and pg.evaluate("document.getElementById('status').classList.contains('has-blab')") is False, s)
            ctx.close()

    # ───── every view shows the NXT values of the mock (pre-market) ─────
    if 'values' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        if MODEARG == 'real':
            import urllib.request
            Q = {s['c']: s for s in json.load(urllib.request.urlopen(URL + 'api/quotes'))['stocks']}; SS, HY = Q['005930'], Q['000660']
        nx = SS.get('nx')
        if not nx or pg.evaluate("KH.basis()") != 'nxt':
            ok('values: needs NXT prices on screen (pre / after-market)', MODEARG == 'real', pg.evaluate("KH.basis()"))
        else:
            lay = [n for n in pg.evaluate("KH.layout()") if n.get('code') == '005930'][0]
            ok(f"map: 삼성전자 {pct(nx['r'])} · {won(nx['p'])} (tile label, KH.layout px for 3D / image)", tile_pct(pg, '005930') == pct(nx['r']) and lay.get('px') == won(nx['p']), (tile_pct(pg, '005930'), lay))
            pg.hover('#map .tile[data-c="005930"]'); pg.wait_for_timeout(250)
            tip = pg.evaluate("({px: document.querySelector('#tip .card-head .px b').textContent, chg: document.querySelector('#tip .card-head .px span').textContent, nx: (document.querySelector('#tip .nxrow') || {}).textContent})")
            krx = CS['005930']
            ok(f"tooltip: {won(nx['p'])} {pct(nx['r'])} + KRX line 'KRX 어제 종가 {won(krx[0])} {pct(krx[2])}'",
               tip['px'] == won(nx['p']) and pct(nx['r']) in tip['chg'] and tip['nx'] and 'KRX 어제 종가' in tip['nx'] and won(krx[0]) in tip['nx'] and pct(krx[2]) in tip['nx'], tip)
            pg.mouse.move(5, 5)
            # side: movers rank NXT stocks, 등락 분포 counts NXT stocks of the whole market
            kn = [s for s in Q.values() if s['m'] == 'K' and s.get('nx') and s['c'][-1] == '0' and s['cap'] > 0]
            best = max(kn, key=lambda s: s['nx']['r'])
            mv = pg.evaluate("({first: document.querySelector('#movers button')?.dataset.c, v: document.querySelector('#movers button .v')?.textContent, scope: document.getElementById('moverScope').textContent})")
            ok(f"movers (상승률): first = {best['n']} {pct(best['nx']['r'])}, scope 'NXT 거래 종목'", mv['first'] == best['c'] and mv['v'] == pct(best['nx']['r']) and mv['scope'] == 'NXT 거래 종목', mv)
            if MODEARG == 'mock':
                stream = {s['c']: s for s in Q.values() if s['m'] == 'K'}
                vals = []
                for (m, part), bb in BR.items():
                    if m != 'K': continue
                    for r in bb['rows']:
                        if len(r) < 4: continue
                        s = stream.get(r[0]); vals.append(s['nx']['r'] if s and s.get('nx') else r[3])
                for c, s in stream.items():
                    if s.get('nx') and c not in {r[0] for (m, _), bb in BR.items() if m == 'K' for r in bb['rows']}: vals.append(s['nx']['r'])
                up, dn = sum(v > 0 for v in vals), sum(v < 0 for v in vals)
                d = pg.evaluate("({scope: document.getElementById('breadthScope').textContent, lab: document.getElementById('breadthLab').textContent})")
                ok(f'등락 분포: 코스피 NXT {len(vals)}종목 (상승 {up} · 하락 {dn}) from /api/breadth NXT column', d['scope'] == f'코스피 NXT {len(vals):,}종목' and f'상승 {up:,}' in d['lab'] and f'하락 {dn:,}' in d['lab'], (d, len(vals), up, dn))
            # table
            pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
            row = pg.evaluate("[...document.querySelector('#tablewrap tr[data-c=\"005930\"]').children].map(td => td.textContent)")
            ok(f"table: 현재가 {won(nx['p'])}, 등락률 {pct(nx['r'])}", row[2] == won(nx['p']) and row[3] == pct(nx['r']), row[:4])
            pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
            # search
            pg.fill('#q', '삼성전자'); pg.wait_for_timeout(250)
            sg = pg.evaluate("[...document.querySelectorAll('#sugg [role=option]')].slice(0, 3).map(o => o.textContent)")
            ok(f"search: 삼성전자 {won(nx['p'])} {pct(nx['r'])}", sg and won(nx['p']) in sg[0] and pct(nx['r']) in sg[0], sg)
            pg.fill('#q', ''); pg.keyboard.press('Escape')
            ok('values: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        if MODEARG == 'mock':
            # 관심 view: an NXT stock and a non-NXT stock (stream), and a code outside the stream (?codes= rows carry nx too)
            other = K_NONX[0]
            ctx, pg, log, _ = fresh(b, 'd1440', 'pre', store={'market': 'WATCH', 'watch': ['005930', other['c']]}, hsh='#watch')
            a1, a2 = tile_pct(pg, '005930'), pg.evaluate(TILE_JS, other['c'])
            cl = pg.evaluate("c => document.querySelector(`#map .tile[data-c=\"${c}\"]`)?.className", other['c'])
            ok(f"관심: 삼성전자 {pct(SS['nx']['r'])}; {other['n']} hatched, its KRX quote {pct(other['r'])}, 'NXT 거래 없음'",
               a1 == pct(SS['nx']['r']) and a2 and pct(other['r']) in a2 and 'NXT 거래 없음' in a2 and 'nonx' in cl, (a1, a2, cl))
            ctx.close()
            # 테마 view: the members map
            th = next(t for t in THEMES if '005930' in t['codes'] and '000660' in t['codes'])
            ctx, pg, log, _ = fresh(b, 'd1440', 'pre', store={'market': 'THEME'}, hsh=f"#theme-{th['id']}", wait=4500)
            ok(f"테마 {th['name']}: 삼성전자 {pct(SS['nx']['r'])}, SK하이닉스 {pct(HY['nx']['r'])}", tile_pct(pg, '005930') == pct(SS['nx']['r']) and tile_pct(pg, '000660') == pct(HY['nx']['r']) and not errs(log), (tile_pct(pg, '005930'), tile_pct(pg, '000660'), errs(log)[:2]))
            ctx.close()
            # phone quick view (tap): the sheet shows the NXT price and the KRX line
            ctx, pg, log, _ = fresh(b, 'm390', 'pre')
            pg.evaluate("window.KHStock = undefined")
            pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(400)
            sh = pg.evaluate("({px: document.querySelector('#sheet .card-head .px b')?.textContent, nx: document.querySelector('#sheet .nxrow')?.textContent})")
            ok(f"m390 sheet: {won(SS['nx']['p'])} + 'KRX 어제 종가' line", sh['px'] == won(SS['nx']['p']) and sh['nx'] and 'KRX 어제 종가' in sh['nx'], sh)
            ctx.close()

    # ───── stocks without NXT: KRX value, hatched, said so ─────
    if 'dim' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        r = pg.evaluate("""() => { const t = [...document.querySelectorAll('#map .tile')]; const nx = t.filter(e => e.classList.contains('nonx'));
          const big = nx.sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0];
          return { codes: t.map(e => e.dataset.c), nonx: nx.map(e => e.dataset.c), img: big ? getComputedStyle(big).backgroundImage.slice(0, 40) : '', big: big && big.dataset.c,
            legend: [...document.querySelectorAll('#legend .lg')].map(e => e.textContent).find(x => x.startsWith('NXT 거래 없음')) }; }""")
        want = sorted(c for c in r['codes'] if not Q[c].get('nx'))
        ok(f'hatched tiles = the {len(want)} map stocks without nx; striped background; legend "NXT 거래 없음 {len(want)}"',
           sorted(r['nonx']) == want and 'repeating-linear-gradient' in r['img'] and r['legend'] == f'NXT 거래 없음 {len(want)}', (len(r['nonx']), len(want), r['img'], r['legend']))
        big = r['big']
        lab = pg.evaluate(TILE_JS, big)
        ok(f"{Q[big]['n']}: KRX quote {pct(Q[big]['r'])} (0 % before 09:00), aria 'NXT 거래 없음'", pct(Q[big]['r']) in lab and 'NXT 거래 없음' in lab, lab)
        pg.hover(f'#map .tile[data-c="{big}"]'); pg.wait_for_timeout(250)
        t = pg.evaluate("document.querySelector('#tip .nxrow')?.textContent")
        ok('tooltip of a hatched tile: "NXT 거래 없음 · KRX 값으로 그렸어요"', t == 'NXT 거래 없음KRX 값으로 그렸어요', t)
        pg.mouse.move(5, 5)
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
        tg = pg.evaluate("c => { const tr = document.querySelector(`#tablewrap tr[data-c=\"${c}\"]`); return { tag: tr.querySelector('.nxtag')?.textContent, chip: getComputedStyle(tr.querySelector('.nmcell i')).backgroundImage.slice(0, 26), n: document.querySelectorAll('#tablewrap .nxtag').length }; }", big)
        ok(f'table: "NXT 없음" tag on {len(want)} rows, hatched colour chip', tg['tag'] == 'NXT 없음' and tg['n'] == len(want) and 'repeating-linear' in tg['chip'], tg)
        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
        # a bucket of the 등락 분포 never lights a hatched tile (the card counts NXT stocks only)
        pg.click('#hist button:nth-child(5)'); pg.wait_for_timeout(250)
        lit = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.dim)')].filter(e => e.classList.contains('nonx')).length")
        ok('등락 분포 bucket (보합): hatched tiles stay dimmed', lit == 0, lit)
        ok('dim: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    # ───── a pick lasts while its phase lasts ─────
    if 'pick' in WANT and MODEARG == 'mock':
        ctx, pg, log, hold = fresh(b, 'd1440', 'pre')
        pg.click('#basis [data-v="krx"]'); pg.wait_for_timeout(500)
        s1 = pg.evaluate(STATE_JS); ev = pg.evaluate("(window.__kb || []).slice(-1)[0]")
        ok(f"pre → KRX: 'krx-prev', badge 'KRX 어제 종가', 삼성전자 {pct(CS['005930'][2])} (11/09 close.json), kh:basis krx-prev, nothing hatched",
           s1['basis'] == 'krx-prev' and s1['badge'] == 'KRX 어제 종가' and tile_pct(pg, '005930') == pct(CS['005930'][2]) and ev and ev['basis'] == 'krx-prev' and s1['nonx'] == 0, (s1, ev))
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        pg.reload(); pg.wait_for_timeout(3000)
        ok('same phase: the pick survives a poll and a reload', pg.evaluate("KH.basis()") == 'krx-prev', pg.evaluate("KH.basis()"))
        hold['phase'] = 'regular'; pg.clock.set_fixed_time(CLOCK['regular']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        s2 = pg.evaluate(STATE_JS)
        ok('09:00 regular: control hidden, KRX live', s2['basis'] == 'krx' and s2['seg'] is None and s2['badge'] == '실시간', s2)
        hold['phase'] = 'pre'; pg.clock.set_fixed_time(CLOCK['pre']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        ok('next pre-market: the old pick is gone, NXT by default', pg.evaluate("KH.basis()") == 'nxt', pg.evaluate("KH.basis()"))
        # gap (closed): pick NXT, it lasts across polls; the phase changes → back to the default
        hold['phase'] = 'gap'; pg.clock.set_fixed_time(CLOCK['gap']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        g0 = pg.evaluate("KH.basis()")
        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(400); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        g1 = pg.evaluate("KH.basis()")
        hold['phase'] = 'regular'; pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        hold['phase'] = 'gap'; pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        g2 = pg.evaluate("KH.basis()")
        ok('08:50–09:00: default krx-prev; NXT pick holds through a poll; after a phase change the default again', (g0, g1, g2) == ('krx-prev', 'nxt', 'krx-prev'), (g0, g1, g2))
        ok('pick: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    # ───── size: cap × p_nxt / p_krx ─────
    if 'size' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        AR = "(() => { const L = KH.layout().filter(n => n.kind === 'tile'); const a = L.find(n => n.code === '005930'), b = L.find(n => n.code === '000660'); return a.w * a.h / (b.w * b.h); })()"
        w_nx = pg.evaluate(AR)
        pg.click('#basis [data-v="krx"]'); pg.wait_for_timeout(900)
        w_kr = pg.evaluate(AR)
        want = (SS['nx']['p'] / SS['p']) / (HY['nx']['p'] / HY['p'])
        ok(f'tile area 삼성전자 : SK하이닉스 follows cap × p_nxt / p_krx (ratio of ratios {want:.4f})', abs((w_nx / w_kr) / want - 1) < 0.03, (round(w_nx, 4), round(w_kr, 4), round(w_nx / w_kr, 4)))
        ctx.close()

    # ───── a replay stays KRX ─────
    if 'replay' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        pg.evaluate("KH.setReplay({t:'1500', date:'2026-11-09', prices: new Map([['005930', {p: 188000, r: -0.37}]])})"); pg.wait_for_timeout(400)
        s = pg.evaluate(STATE_JS)
        ok(f"replay: KH.basis 'krx', no control, no hatching; frame 삼성전자 −0.37%; SK하이닉스 (not in the frame) its KRX close {pct(CS['000660'][2])}",
           s['basis'] == 'krx' and s['seg'] is None and s['nonx'] == 0 and tile_pct(pg, '005930') == '−0.37%' and tile_pct(pg, '000660') == pct(CS['000660'][2]), (s, tile_pct(pg, '000660')))
        pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(400)
        ok('replay off: NXT again', pg.evaluate("KH.basis()") == 'nxt' and tile_pct(pg, '005930') == pct(SS['nx']['r']), tile_pct(pg, '005930'))
        ctx.close()

    # ───── flashes follow NXT ticks ─────
    if 'flash' in WANT and MODEARG == 'mock':
        def mover(q, n):
            if n < 2: return
            for i, s in enumerate(q['stocks']):
                if s.get('nx') and (i + n) % 5 < 2:
                    d = (1 if (i + n) % 2 else -1) * max(1, round(s['nx']['p'] * 0.002)); s['nx']['p'] += d; s['nx']['d'] += d
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre', hook=mover, motion='fancy')
        pg.evaluate("window.__ch = null; document.addEventListener('kh:data', e => { window.__ch = e.detail.changed.length; })")
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
        r = pg.evaluate("({ch: window.__ch, ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length, nonx: document.querySelectorAll('#map .tile.nonx.fl-u, #map .tile.nonx.fl-d').length})")
        ok('NXT ticks: kh:data changed > 0 and tiles flash (fancy), none on hatched tiles', r['ch'] and r['ring'] > 0 and r['nonx'] == 0, r)
        pg.click('#basis [data-v="krx"]'); pg.wait_for_timeout(1200)
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
        r2 = pg.evaluate("({ch: window.__ch, ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length})")
        ok('KRX (yesterday\'s closes) while NXT ticks: nothing flashes', r2['ch'] == 0 and r2['ring'] == 0, r2)
        ctx.close()

    # ───── quality: overflow, console, labels, tap targets, shots ─────
    if 'quality' in WANT:
        for ph in (['pre', 'after', 'night', 'regular'] if MODEARG == 'mock' else ['now']):
            for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
                ctx, pg, log, _ = fresh(b, vp, ph if ph != 'now' else 'pre')
                over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                lab = pg.evaluate(LABEL_CHECK_JS)
                hdr = pg.evaluate("""() => { const s = document.getElementById('status').getBoundingClientRect(), top = document.querySelector('.top').getBoundingClientRect();
                  const kids = [...document.querySelectorAll('#status > *, #status .badge > *')].filter(e => e.offsetParent && e.getClientRects().length);
                  return { out: kids.filter(e => { const r = e.getBoundingClientRect(); return r.right > innerWidth + 0.5 || r.left < -0.5; }).length, right: Math.round(s.right), vw: innerWidth }; }""")
                tap = pg.evaluate("[...document.querySelectorAll('#basis button')].filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })")
                tapok = all(w >= 40 and hh >= 40 for w, hh in tap) if vp.startswith('m') else True
                ok(f'{ph} {vp}: overflow 0, console 0, labels inside ({lab["visible"]}), header inside, basis buttons {tap}{" ≥ 40 px" if vp.startswith("m") else ""}',
                   over == 0 and not errs(log) and lab['overflow'] == 0 and hdr['out'] == 0 and tapok, (over, errs(log)[:2], lab['examples'][:1], hdr, tap))
                if ph in ('pre', 'now') and vp in ('m390',):
                    pg.screenshot(path=SHOTS + f'nxt-{MODEARG}-pre-m390.png')
                if ph in ('pre', 'now') and vp in ('m360', 'm390', 't768', 'd1280'):
                    # table: hatched rows fit (below 1024 px no tag, the hatched chip and a muted name), no wider than under KRX
                    for cb in ['r', 'm1']:
                        pg.evaluate(f"localStorage.setItem('khm.colorBy', '\"{cb}\"')")
                        if cb == 'm1': pg.reload(); pg.wait_for_timeout(3000)
                        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(500)
                        TW = """() => { const w = document.getElementById('tablewrap'), r = w.querySelector('tr.nonx');
                          return { over: w.scrollWidth - w.clientWidth, page: document.documentElement.scrollWidth - innerWidth, n: w.querySelectorAll('tr.nonx').length,
                            tag: r ? getComputedStyle(r.querySelector('.nxtag')).display : null, chip: r ? getComputedStyle(r.querySelector('.nmcell i')).backgroundImage.slice(0, 16) : null }; }"""
                        t = pg.evaluate(TW)
                        pg.click('#basis [data-v="krx"]'); pg.wait_for_timeout(500); base = pg.evaluate(TW)['over']
                        pg.click('#basis [data-v="nxt"]'); pg.wait_for_timeout(300)
                        wide = vp.startswith('d')
                        ok(f'{ph} {vp} table ({cb}): {t["n"]} hatched rows, sideways {t["over"]} ≤ KRX {base}{" = 0" if vp.startswith("m") else ""}, tag {"shown" if wide else "hidden"}, chip hatched',
                           t['over'] <= max(base, 0) and (t['over'] <= 0 or not vp.startswith('m')) and t['page'] == 0 and t['n'] > 0 and (t['tag'] != 'none') == wide and 'repeating' in (t['chip'] or ''), (t, base))
                        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
                ctx.close()
        for ph in (['pre', 'after'] if MODEARG == 'mock' else ['now']):
            ctx, pg, log, _ = fresh(b, 'd1440', ph if ph != 'now' else 'pre')
            pg.screenshot(path=SHOTS + f'nxt-{MODEARG}-{ph}-d1440.png')
            ctx.close()

    # ───── keyboard: the choice is reachable by Tab, works with Enter / Space, focus stays and shows ─────
    if 'keys' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1280', 'pre')
        hit = None
        for i in range(60):
            pg.keyboard.press('Tab')
            a = pg.evaluate("(() => { const e = document.activeElement; return e && e.closest('#basis') ? e.dataset.v : null; })()")
            if a: hit = (i + 1, a); break
        ok('Tab reaches the KRX · NXT buttons', hit is not None, hit)
        pg.focus('#basis [data-v="krx"]'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
        a = pg.evaluate("({b: KH.basis(), f: document.activeElement.dataset.v, ring: getComputedStyle(document.activeElement).outlineStyle !== 'none' || getComputedStyle(document.activeElement).boxShadow !== 'none'})")
        pg.keyboard.press('Tab'); pg.keyboard.press('Space'); pg.wait_for_timeout(400)
        a2 = pg.evaluate("({b: KH.basis(), f: document.activeElement.dataset.v, pressed: document.activeElement.getAttribute('aria-pressed')})")
        ok('Enter on KRX → krx-prev (focus stays, visible); Tab + Space on NXT → nxt (aria-pressed true)', a['b'] == 'krx-prev' and a['f'] == 'krx' and a['ring'] and a2['b'] == 'nxt' and a2['f'] == 'nxt' and a2['pressed'] == 'true', (a, a2))
        ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
