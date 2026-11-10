"""§3-8 / §3-10 price basis KRX · NXT · 통합 of the heatmap (numbers, not eyeballing). usage: nxt3.py [mock|real] [section…]
mock (default): /api/quotes + /api/breadth answered from nxt_fix phases (a real 11/10 08:21 pre-market capture and phases built
from it), the page clock set to that phase's KST time. real: the dev Worker harness as it is (checks whatever phase it is now).
sections: phases, values, int, dim, pick, size, replay, flash, quality, keys (default: all)."""
import sys, os, json, re, math
from datetime import datetime
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
import nxt_fix
from nxt_fix import CLOSE, CLOCK, built

VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
MODEARG = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ('mock', 'real') else 'mock'
ALL = ['phases', 'values', 'int', 'dim', 'pick', 'size', 'replay', 'flash', 'quality', 'keys']
WANT = set(a for a in sys.argv[1:] if a not in ('mock', 'real')) or set(ALL)
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
ROOT = nxt_fix.ROOT
SHOTS = ROOT + 'qa/heatmap2/shots3/'
os.makedirs(SHOTS, exist_ok=True)
THEMES = json.load(open(ROOT + 'web/themes.json'))['themes']
REC = "document.addEventListener('kh:basis', e => (window.__kb = window.__kb || []).push(e.detail));"
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def jsround(x): return math.floor(x + 0.5)
def pct(v): return ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.2f}%'
def won(v): return f'{round(v):,}'
def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]
def ms(iso): return datetime.fromisoformat(iso).timestamp() * 1000


def int_row(q, s):
    """→ (p, r, tv) of one row under 통합: the more recent of KRX (asOf; before 09:00 the previous close) and NXT (nx.t)"""
    x = s.get('nx')
    if not x: return s['p'], s['r'], s['tv']
    k = datetime.fromisoformat(q['asOf'])
    kt = ms(s['t']) if s.get('t') and k.strftime('%H%M') >= '0900' else ms(CLOSE['asOf']) if k.strftime('%H%M') < '0900' else ms(q['asOf'])
    tv = s['tv'] + (x.get('tv') or 0)
    if not ms(x['t']) > kt + 1000: return s['p'], s['r'], tv          # within 1 s: one moment, KRX stands
    base = s['p'] - s['d']
    return x['p'], jsround((x['p'] - base) / base * 1e4) / 100, tv


def int_row_v(q, s):
    x = s.get('nx'); return s['v'] + ((x or {}).get('v') or 0)


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
  opts: document.getElementById('basis').hidden ? [] : [...document.querySelectorAll('#basis button')].filter(b => !b.hidden).map(b => b.dataset.v),
  badge: (document.querySelector('#status .badge .bl') || document.querySelector('#status .badge')).textContent,
  short: (document.querySelector('#status .badge .bs') || {}).textContent || null,
  nonx: document.querySelectorAll('#map .tile.nonx').length, tiles: document.querySelectorAll('#map .tile').length })"""
TILE_JS = "c => { const t = document.querySelector(`#map .tile[data-c=\"${c}\"]`); return t ? t.getAttribute('aria-label') : null; }"
TIP_JS = """() => ({px: document.querySelector('#tip .card-head .px b')?.textContent, chg: document.querySelector('#tip .card-head .px span')?.textContent,
  nx: [...document.querySelectorAll('#tip .nxrow')].map(e => e.textContent), meta: document.querySelector('#tip .card-head .meta')?.textContent})"""
DIST_JS = "({scope: document.getElementById('breadthScope').textContent, lab: document.getElementById('breadthLab').textContent})"
MOV_JS = "({first: document.querySelector('#movers button')?.dataset.c, v: document.querySelector('#movers button .v')?.textContent, scope: document.getElementById('moverScope').textContent})"


def tile_pct(pg, code):
    a = pg.evaluate(TILE_JS, code)
    return a and a.split(',')[0].split(' ')[-1]


def pick(pg, v, wait=500):
    pg.click(f'#basis [data-v="{v}"]'); pg.wait_for_timeout(wait)


def table_row(pg, code):
    """{head, cells (by position), by: {column key → [header, cell]}}"""
    return pg.evaluate("""c => { const th = [...document.querySelectorAll('#tablewrap thead th')], td = [...document.querySelector(`#tablewrap tr[data-c="${c}"]`).children];
      const by = {}; th.forEach((t, i) => { by[t.dataset.k] = [t.textContent, td[i].textContent]; });
      return { head: th.map(t => t.textContent), cells: td.map(x => x.textContent), by }; }""", code)


def breadth_vals(q, br, m, how):
    """the 등락 분포 values of market m the page should count: how 'nxt' (NXT column, NXT stocks only) | 'int' (통합)"""
    stream = {s['c']: s for s in q['stocks'] if s['m'] == m}
    pre = datetime.fromisoformat(q['asOf']).strftime('%H%M') < '0900'
    vals, seen = [], set()
    for (mm, part), bb in br.items():
        if mm != m: continue
        for r in bb['rows']:
            s = stream.get(r[0]); nxr = r[3] if len(r) >= 4 else None
            if how == 'nxt':
                if nxr is None: continue
                vals.append(s['nx']['r'] if s and s.get('nx') else nxr)
            else:
                vals.append(int_row(q, s)[1] if s else (nxr if pre and nxr is not None else r[1]))
            seen.add(r[0])
    for c, s in stream.items():
        if c in seen: continue
        if how == 'nxt' and s.get('nx'): vals.append(s['nx']['r'])
        elif how == 'int': vals.append(int_row(q, s)[1])
    return vals


with sync_playwright() as p:
    b = launch(p)
    QP = built('pre')[0]
    Q, BR = {s['c']: s for s in QP['stocks']}, built('pre')[1]
    SS, HY = Q['005930'], Q['000660']
    K_NONX = [s for s in Q.values() if s['m'] == 'K' and not s.get('nx') and s['c'][-1] == '0' and s['cap'] > 0]
    CS = CLOSE['c']

    # ───── defaults, choices and badges per phase, then every other choice ─────
    if 'phases' in WANT and MODEARG == 'mock':
        A3 = ['krx', 'nxt', 'int']
        exp = {   # phase: (basis, pressed, choices, badge, phones, 삼성전자 % (q → str))
            'pre': ('int', 'int', A3, '통합 시세 · 08:21 기준', '통합 08:21', lambda q: pct(int_row(q, Q2(q)['005930'])[1])),
            'gap': ('krx-prev', 'krx', A3, 'KRX 어제 종가', '어제 종가', lambda q: pct(CS['005930'][2])),
            'stale': ('krx-prev', 'krx', A3, 'KRX 어제 종가', '어제 종가', lambda q: pct(CS['005930'][2])),
            'after': ('int', 'int', A3, '통합 시세 · 17:40 기준', '통합 17:40', lambda q: pct(Q2(q)['005930']['r'])),
            'night': ('krx', 'krx', A3, 'KRX 15:30 종가', '15:30 종가', lambda q: pct(CS['005930'][2])),
            'regular': ('krx', None, [], '실시간', None, lambda q: pct(Q2(q)['005930']['r'])),
            'reg': ('int', 'int', A3, '통합 실시간', '통합 10:15', lambda q: pct(int_row(q, Q2(q)['005930'])[1])),
            'legacy': ('krx', 'krx', ['krx', 'int'], 'KRX 15:30 종가', '15:30 종가', lambda q: pct(CS['005930'][2])),
        }
        Q2 = lambda q: {s['c']: s for s in q['stocks']}
        others = {   # phase: [(pick, basis, badge, 삼성전자 % (q → str), hatched?)]
            'pre': [('nxt', 'nxt', 'NXT 프리마켓 · 08:21 기준', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                    ('krx', 'krx-prev', 'KRX 어제 종가', lambda q: pct(CS['005930'][2]), False)],
            'gap': [('nxt', 'nxt', 'NXT 프리마켓 마감 · 08:21 기준', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                    ('int', 'int', '통합 시세 · 08:21 기준', lambda q: pct(int_row(q, Q2(q)['005930'])[1]), False)],
            'stale': [('nxt', 'nxt', 'NXT 프리마켓 마감 · 08:21 기준', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                      ('int', 'int', '통합 시세 · 08:21 기준', lambda q: pct(int_row(q, Q2(q)['005930'])[1]), False)],
            'after': [('nxt', 'nxt', 'NXT 애프터마켓 · 17:40 기준', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                      ('krx', 'krx', 'KRX 15:30 종가', lambda q: pct(CS['005930'][2]), False)],
            'night': [('nxt', 'nxt', 'NXT 애프터마켓 마감 · 19:59 기준', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                      ('int', 'int', '통합 시세 · 19:59 기준', lambda q: pct(Q2(q)['005930']['r']), False)],
            'reg': [('nxt', 'nxt', 'NXT 실시간', lambda q: pct(Q2(q)['005930']['nx']['r']), True),
                    ('krx', 'krx', 'KRX 실시간', lambda q: pct(Q2(q)['005930']['r']), False)],
            'legacy': [('int', 'int', '통합 시세 · 17:40 기준', lambda q: pct(Q2(q)['005930']['r']), False)],
        }
        for ph, (bid, seg, opts, badge, short, want) in exp.items():
            q = built(ph)[0]
            ctx, pg, log, _ = fresh(b, 'd1440', ph)
            s = pg.evaluate(STATE_JS)
            got = tile_pct(pg, '005930')
            ok(f'{ph}: KH.basis {bid}, pressed {seg}, choices {opts}, badge "{badge}" / phones "{short}", 삼성전자 {want(q)}',
               s['basis'] == bid and s['seg'] == seg and s['opts'] == opts and s['badge'] == badge and s['short'] == short and got == want(q) and s['nonx'] == 0 and not errs(log), (s, got, errs(log)[:2]))
            if ph == 'pre':
                ev = pg.evaluate("window.__kb || []")
                ok('kh:basis fired with {basis:"int", phase:"pre", label}', any(e['basis'] == 'int' and e['phase'] == 'pre' and e['label'] == badge for e in ev), ev)
            if ph == 'stale':
                ok('stale: o:1 at 08:53 is not an open pre-market (status not live, no "갱신" time)', pg.evaluate("!document.getElementById('status').classList.contains('live')"))
            for v, bid2, badge2, want2, hatch in others.get(ph, []):
                pick(pg, v)
                s2 = pg.evaluate(STATE_JS); got2 = tile_pct(pg, '005930')
                ok(f'  {ph} → {v}: KH.basis {bid2}, badge "{badge2}", 삼성전자 {want2(q)}, {"hatched tiles" if hatch else "nothing hatched"}',
                   s2['basis'] == bid2 and s2['seg'] == v and s2['badge'] == badge2 and got2 == want2(q) and (s2['nonx'] > 0) == hatch, (s2, got2))
            if ph == 'regular':
                ok('regular without NXT 메인마켓 rows: no control, no badge line, every tile the live KRX quote', s['nonx'] == 0 and pg.evaluate("document.getElementById('status').classList.contains('has-blab')") is False, s)
            ctx.close()

    # ───── every view shows the basis' values (pre-market: 통합 by default, then NXT) ─────
    if 'values' in WANT:
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        if MODEARG == 'real':
            import urllib.request
            QP = json.load(urllib.request.urlopen(URL + 'api/quotes')); Q = {s['c']: s for s in QP['stocks']}; SS, HY = Q['005930'], Q['000660']
        nx = SS.get('nx')
        if not nx or pg.evaluate("KH.basis()") not in ('int', 'nxt'):
            ok('values: needs NXT prices on screen', MODEARG == 'real', pg.evaluate("KH.basis()"))
        else:
            pick(pg, 'int')
            ip, ir, itv = int_row(QP, SS)
            # the 4th tile line: market cap as drawn (cap × p_basis / p_krx), only under a shown price line
            MC = """c => { const t = document.querySelector(`#map .tile[data-c="${c}"]`), m = t.querySelector('.mc'), p = t.querySelector('.px');
              return { mc: m && !m.hidden ? m.textContent : null, px: p && !p.hidden ? p.textContent : null, fs: m ? parseFloat(getComputedStyle(m).fontSize) : 0 }; }"""
            ALLMC = "[...document.querySelectorAll('#map .tile')].map(t => [t.querySelector('.mc') && !t.querySelector('.mc').hidden, !t.querySelector('.px').hidden])"
            m_int = pg.evaluate(MC, '005930'); w_int = pg.evaluate(f"KH.fmt.eok({SS['cap']} * {ip} / {SS['p']})")
            allmc = pg.evaluate(ALLMC)
            ok(f"통합 tile 4th line: 삼성전자 '시총 {w_int}' (cap × p_int / p_krx), ≥ 9 px, under its price; every cap line has a price line ({sum(a for a, _ in allmc)} tiles)",
               m_int['mc'] == '시총 ' + w_int and m_int['px'] == won(ip) and m_int['fs'] >= 9 and all(px for mc, px in allmc if mc) and 0 < sum(a for a, _ in allmc) < len(allmc) / 3, (m_int, w_int))
            pick(pg, 'krx')
            m_krx = pg.evaluate(MC, '005930'); w_krx = pg.evaluate(f"KH.fmt.eok({SS['cap']} * {CS['005930'][0]} / {SS['p']})")
            ok(f"KRX (어제 종가) tile 4th line: 삼성전자 '시총 {w_krx}'", m_krx['mc'] == '시총 ' + w_krx, m_krx)
            pick(pg, 'int')
            lay = [n for n in pg.evaluate("KH.layout()") if n.get('code') == '005930'][0]
            ok(f"통합 map: 삼성전자 {pct(ir)} · {won(ip)} (tile label, KH.layout px)", tile_pct(pg, '005930') == pct(ir) and lay.get('px') == won(ip), (tile_pct(pg, '005930'), lay))
            pg.hover('#map .tile[data-c="005930"]'); pg.wait_for_timeout(250)
            tip = pg.evaluate(TIP_JS)
            eok = pg.evaluate(f"KH.fmt.eok({itv})")
            ok(f"통합 tooltip: {won(ip)} {pct(ir)}, lines 'KRX 어제 종가 {won(CS['005930'][0])} {pct(CS['005930'][2])}' + 'NXT 프리마켓 …', '통합 거래대금 {eok}'",
               tip['px'] == won(ip) and pct(ir) in tip['chg'] and len(tip['nx']) == 2 and tip['nx'][0].startswith('KRX 어제 종가') and won(CS['005930'][0]) in tip['nx'][0]
               and tip['nx'][1].startswith('NXT 프리마켓') and won(nx['p']) in tip['nx'][1] and f'통합 거래대금 {eok}' in tip['meta'], tip)
            pg.mouse.move(5, 5)
            kmap = [s for s in Q.values() if s['m'] == 'K' and s['c'][-1] == '0' and s['cap'] > 0]
            best = max(kmap, key=lambda s: int_row(QP, s)[1])
            mv = pg.evaluate(MOV_JS)
            ok(f"통합 movers (상승률): first = {best['n']} {pct(int_row(QP, best)[1])}, no scope note", mv['first'] == best['c'] and mv['v'] == pct(int_row(QP, best)[1]) and mv['scope'] == '', mv)
            if MODEARG == 'mock':
                vals = breadth_vals(QP, BR, 'K', 'int')
                up, dn = sum(v > 0 for v in vals), sum(v < 0 for v in vals)
                d = pg.evaluate(DIST_JS)
                ok(f'통합 등락 분포: 코스피 전 종목 {len(vals)} (상승 {up} · 하락 {dn}; before 09:00 the NXT % where there is one)', d['scope'] == f'코스피 전 종목 {len(vals):,}' and f'상승 {up:,}' in d['lab'] and f'하락 {dn:,}' in d['lab'], (d, len(vals), up, dn))
            pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
            t = table_row(pg, '005930')
            vol = int_row_v(QP, SS)
            ok(f"통합 table: 현재가 {won(ip)}, 등락률 {pct(ir)}, '통합 거래량' {vol}, '통합 거래대금' {eok}", t['by']['p'][1] == won(ip) and t['by']['r'][1] == pct(ir) and t['by']['tv'] == ['통합 거래대금', eok]
               and t['by']['vol'] == ['통합 거래량', pg.evaluate(f"KH.fmt.vol({vol})")] and list(t['by'])[-3:] == ['vol', 'tv', 'cap'], t)
            pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
            pg.fill('#q', '삼성전자'); pg.wait_for_timeout(250)
            sg = pg.evaluate("[...document.querySelectorAll('#sugg [role=option]')].slice(0, 3).map(o => o.textContent)")
            ok(f"통합 search: 삼성전자 {won(ip)} {pct(ir)}", sg and won(ip) in sg[0] and pct(ir) in sg[0], sg)
            pg.fill('#q', ''); pg.keyboard.press('Escape')
            ok('통합 legend: 크기 시가총액, nothing "NXT 거래 없음"', not any(x.startswith('NXT 거래 없음') for x in pg.evaluate("[...document.querySelectorAll('#legend .lg')].map(e => e.textContent)")))

            # NXT
            pick(pg, 'nxt')
            lay = [n for n in pg.evaluate("KH.layout()") if n.get('code') == '005930'][0]
            ok(f"NXT map: 삼성전자 {pct(nx['r'])} · {won(nx['p'])}", tile_pct(pg, '005930') == pct(nx['r']) and lay.get('px') == won(nx['p']), (tile_pct(pg, '005930'), lay))
            pg.hover('#map .tile[data-c="005930"]'); pg.wait_for_timeout(250)
            tip = pg.evaluate(TIP_JS)
            krx = CS['005930']
            ok(f"NXT tooltip: {won(nx['p'])} {pct(nx['r'])} + KRX line 'KRX 어제 종가 {won(krx[0])} {pct(krx[2])}', 'NXT 거래대금'",
               tip['px'] == won(nx['p']) and pct(nx['r']) in tip['chg'] and len(tip['nx']) == 1 and 'KRX 어제 종가' in tip['nx'][0] and won(krx[0]) in tip['nx'][0] and pct(krx[2]) in tip['nx'][0]
               and 'NXT 거래대금' in tip['meta'], tip)
            pg.mouse.move(5, 5)
            kn = [s for s in Q.values() if s['m'] == 'K' and s.get('nx') and s['c'][-1] == '0' and s['cap'] > 0]
            best = max(kn, key=lambda s: s['nx']['r'])
            mv = pg.evaluate(MOV_JS)
            ok(f"NXT movers (상승률): first = {best['n']} {pct(best['nx']['r'])}, scope 'NXT 거래 종목'", mv['first'] == best['c'] and mv['v'] == pct(best['nx']['r']) and mv['scope'] == 'NXT 거래 종목', mv)
            if MODEARG == 'mock':
                vals = breadth_vals(QP, BR, 'K', 'nxt')
                up, dn = sum(v > 0 for v in vals), sum(v < 0 for v in vals)
                d = pg.evaluate(DIST_JS)
                ok(f'NXT 등락 분포: 코스피 NXT {len(vals)}종목 (상승 {up} · 하락 {dn}) from /api/breadth NXT column', d['scope'] == f'코스피 NXT {len(vals):,}종목' and f'상승 {up:,}' in d['lab'] and f'하락 {dn:,}' in d['lab'], (d, len(vals), up, dn))
            pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
            t = table_row(pg, '005930')
            neok = pg.evaluate(f"KH.fmt.eok({nx.get('tv') or 0})")
            ok(f"NXT table: 현재가 {won(nx['p'])}, 등락률 {pct(nx['r'])}, 'NXT 거래대금' {neok}", t['by']['p'][1] == won(nx['p']) and t['by']['r'][1] == pct(nx['r']) and t['by']['tv'] == ['NXT 거래대금', neok], t)
            pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
            pg.fill('#q', '삼성전자'); pg.wait_for_timeout(250)
            sg = pg.evaluate("[...document.querySelectorAll('#sugg [role=option]')].slice(0, 3).map(o => o.textContent)")
            ok(f"NXT search: 삼성전자 {won(nx['p'])} {pct(nx['r'])}", sg and won(nx['p']) in sg[0] and pct(nx['r']) in sg[0], sg)
            pg.fill('#q', ''); pg.keyboard.press('Escape')
            ok('values: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        if MODEARG == 'mock':
            # 관심 view: an NXT stock and a non-NXT stock: 통합 (the KRX quote, not hatched), then NXT (hatched, "NXT 거래 없음")
            other = K_NONX[0]
            ctx, pg, log, _ = fresh(b, 'd1440', 'pre', store={'market': 'WATCH', 'watch': ['005930', other['c']]}, hsh='#watch')
            a1, a2 = tile_pct(pg, '005930'), pg.evaluate(TILE_JS, other['c'])
            cl = pg.evaluate("c => document.querySelector(`#map .tile[data-c=\"${c}\"]`)?.className", other['c'])
            ok(f"관심 통합: 삼성전자 {pct(int_row(QP, SS)[1])}; {other['n']} its KRX quote {pct(other['r'])}, not hatched",
               a1 == pct(int_row(QP, SS)[1]) and a2 and pct(other['r']) in a2 and 'NXT 거래 없음' not in a2 and 'nonx' not in cl, (a1, a2, cl))
            pick(pg, 'nxt')
            a1, a2 = tile_pct(pg, '005930'), pg.evaluate(TILE_JS, other['c'])
            cl = pg.evaluate("c => document.querySelector(`#map .tile[data-c=\"${c}\"]`)?.className", other['c'])
            ok(f"관심 NXT: 삼성전자 {pct(SS['nx']['r'])}; {other['n']} hatched, its KRX quote {pct(other['r'])}, 'NXT 거래 없음'",
               a1 == pct(SS['nx']['r']) and a2 and pct(other['r']) in a2 and 'NXT 거래 없음' in a2 and 'nonx' in cl, (a1, a2, cl))
            ctx.close()
            th = next(t for t in THEMES if '005930' in t['codes'] and '000660' in t['codes'])
            ctx, pg, log, _ = fresh(b, 'd1440', 'pre', store={'market': 'THEME'}, hsh=f"#theme-{th['id']}", wait=4500)
            ok(f"테마 {th['name']} (통합): 삼성전자 {pct(int_row(QP, SS)[1])}, SK하이닉스 {pct(int_row(QP, HY)[1])}",
               tile_pct(pg, '005930') == pct(int_row(QP, SS)[1]) and tile_pct(pg, '000660') == pct(int_row(QP, HY)[1]) and not errs(log), (tile_pct(pg, '005930'), tile_pct(pg, '000660'), errs(log)[:2]))
            ctx.close()
            ctx, pg, log, _ = fresh(b, 'm390', 'pre')
            pg.evaluate("window.KHStock = undefined")
            pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(400)
            sh = pg.evaluate("({px: document.querySelector('#sheet .card-head .px b')?.textContent, nx: [...document.querySelectorAll('#sheet .nxrow')].map(e => e.textContent)})")
            ok(f"m390 sheet (통합): {won(int_row(QP, SS)[0])} + KRX and NXT lines", sh['px'] == won(int_row(QP, SS)[0]) and len(sh['nx']) == 2 and 'KRX 어제 종가' in sh['nx'][0] and 'NXT 프리마켓' in sh['nx'][1], sh)
            ctx.close()

    # ───── 통합 in the regular session: per-row times, value sums, tooltip, size by 거래대금 ─────
    if 'int' in WANT and MODEARG == 'mock':
        QR = built('reg')[0]; R = {s['c']: s for s in QR['stocks']}
        def rowtime(q, n):     # a Worker that sends the KRX trade time per row: 000660's KRX trade is older than its NXT one
            for s in q['stocks']:
                if s['c'] == '000660': s['t'] = '2026-11-10T10:10:00.000000+09:00'
                if s['c'] == '005930': s['t'] = '2026-11-10T10:15:00.000000+09:00'
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', hook=rowtime)
        hy = dict(R['000660'], t='2026-11-10T10:10:00.000000+09:00'); ss = dict(R['005930'], t='2026-11-10T10:15:00.000000+09:00')
        hp, hr, _ = int_row(QR, hy); sp, sr, _ = int_row(QR, ss)
        ok(f"reg 통합 with row times: SK하이닉스 NXT is newer → {won(hp)} {pct(hr)} (vs KRX base); 삼성전자 KRX newer → {won(sp)} {pct(sr)}",
           hp == hy['nx']['p'] and sp == ss['p'] and tile_pct(pg, '000660') == pct(hr) and tile_pct(pg, '005930') == pct(sr), (tile_pct(pg, '000660'), tile_pct(pg, '005930')))
        ctx.close()
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg')
        # the Worker's real shape: no row times, NXT stamped µs after asOf → one moment, KRX stands for every row
        same = pg.evaluate("c => c.map(x => document.querySelector(`#map .tile[data-c=\"${x}\"]`)?.getAttribute('aria-label').split(',')[0].split(' ').pop())", [c for c in list(R)[:40] if c[-1] == '0'])
        want = [pct(R[c]['r']) for c in list(R)[:40] if c[-1] == '0']
        ok('reg 통합 without row times: NXT µs after KRX is the same moment → every tile its KRX %', [x for x in same if x] == [w for x, w in zip(same, want) if x] and sum(1 for x in same if x) > 20, (same[:5], want[:5]))
        s = R['005930']; x = s['nx']
        pg.hover('#map .tile[data-c="005930"]'); pg.wait_for_timeout(250)
        tip = pg.evaluate(TIP_JS)
        eok = pg.evaluate(f"KH.fmt.eok({s['tv'] + x['tv']})")
        ok(f"reg tooltip: KRX quote {won(s['p'])}, lines 'KRX 실시간 …' + 'NXT 메인마켓 {won(x['p'])} {pct(x['r'])} 10:15', '통합 거래대금 {eok}'",
           tip['px'] == won(s['p']) and tip['nx'][0].startswith('KRX 실시간') and tip['nx'][1].startswith('NXT 메인마켓') and won(x['p']) in tip['nx'][1] and '10:15' in tip['nx'][1] and f'통합 거래대금 {eok}' in tip['meta'], tip)
        pg.mouse.move(5, 5)
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(300)
        heads = {}
        for v, lab, val in [('int', '통합 거래대금', s['tv'] + x['tv']), ('nxt', 'NXT 거래대금', x['tv']), ('krx', '거래대금', s['tv'])]:
            pick(pg, v, 400)
            t = table_row(pg, '005930')
            heads[v] = (t['by']['tv'][0], t['by']['tv'][1], pg.evaluate(f"KH.fmt.eok({val})"), lab)
        ok('reg table: the value column follows the basis (통합 = KRX + NXT, NXT, KRX)', all(h_ == lab and c == e for h_, c, e, lab in heads.values()), heads)
        # 거래량 sorts like the other columns (desc, then asc), under 통합 the KRX + NXT sum
        pick(pg, 'int', 400)
        pg.click('#tablewrap th[data-k="vol"] button'); pg.wait_for_timeout(300)
        o1 = pg.evaluate("[...document.querySelectorAll('#tablewrap tbody tr')].slice(0, 5).map(tr => tr.dataset.c)")
        pg.click('#tablewrap th[data-k="vol"] button'); pg.wait_for_timeout(300)
        o2 = pg.evaluate("[...document.querySelectorAll('#tablewrap tbody tr')].slice(0, 3).map(tr => tr.dataset.c)")
        kv = sorted([s for s in R.values() if s['m'] == 'K' and s['c'][-1] == '0'], key=lambda s: -int_row_v(QR, s))
        ok(f"table 거래량 (통합) sorts: ▾ {[s['n'] for s in kv[:3]]}, then ▴", o1[:5] == [s['c'] for s in kv[:5]] and o2[:3] == [s['c'] for s in kv[::-1][:3]], (o1, o2))
        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
        # 등락 분포: 통합 = /api/breadth KRX column after 09:00; NXT = its NXT column
        pick(pg, 'int', 900)
        d = pg.evaluate(DIST_JS)
        vals = breadth_vals(QR, built('reg')[1], 'K', 'int')
        ok(f'reg 등락 분포 (통합): 코스피 전 종목 {len(vals)}', d['scope'] == f'코스피 전 종목 {len(vals):,}' and f'상승 {sum(v > 0 for v in vals):,}' in d['lab'], d)
        pick(pg, 'nxt', 900)
        d = pg.evaluate(DIST_JS)
        vals = breadth_vals(QR, built('reg')[1], 'K', 'nxt')
        ok(f'reg 등락 분포 (NXT): 코스피 NXT {len(vals)}종목', d['scope'] == f'코스피 NXT {len(vals):,}종목', d)
        ok('int: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # size by 거래대금: 통합 sums the two venues (ratio of area ratios 삼성전자 : SK하이닉스, 통합 over KRX)
        ctx, pg, log, _ = fresh(b, 'd1440', 'reg', store={'sizeBy': 'tv'})
        AR = "(() => { const L = KH.layout().filter(n => n.kind === 'tile'); const a = L.find(n => n.code === '005930'), b = L.find(n => n.code === '000660'); return a && b ? a.w * a.h / (b.w * b.h) : null; })()"
        a_int = pg.evaluate(AR); leg = pg.evaluate("[...document.querySelectorAll('#legend .lg')].map(e => e.textContent).find(x => x.startsWith('크기'))")
        pick(pg, 'krx', 900); a_krx = pg.evaluate(AR)
        S, H = R['005930'], R['000660']
        want = ((S['tv'] + S['nx']['tv']) / (H['tv'] + H['nx']['tv'])) / (S['tv'] / H['tv'])
        ok(f'size 거래대금 under 통합 = KRX + NXT value (ratio of ratios {want:.4f}); legend "크기통합 거래대금"', a_int and a_krx and abs((a_int / a_krx) / want - 1) < 0.04 and leg == '크기통합 거래대금', (a_int, a_krx, leg))
        ctx.close()
        # regular session without NXT rows: KRX, no control (also KH.basis 'krx')
        ctx, pg, log, _ = fresh(b, 'd1440', 'regular')
        s = pg.evaluate(STATE_JS)
        ok('regular without NXT 메인마켓 rows: KH.basis krx, control hidden', s['basis'] == 'krx' and s['seg'] is None, s)
        ctx.close()

    # ───── stocks without NXT under NXT: KRX value, hatched, said so ─────
    if 'dim' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        pick(pg, 'nxt')
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
        pg.click('#hist button:nth-child(5)'); pg.wait_for_timeout(250)
        lit = pg.evaluate("[...document.querySelectorAll('#map .tile:not(.dim)')].filter(e => e.classList.contains('nonx')).length")
        ok('등락 분포 bucket (보합): hatched tiles stay dimmed', lit == 0, lit)
        pg.click('#hist button:nth-child(5)'); pg.wait_for_timeout(200)
        pick(pg, 'int')
        pg.hover(f'#map .tile[data-c="{big}"]'); pg.wait_for_timeout(250)
        t = pg.evaluate("[...document.querySelectorAll('#tip .nxrow')].map(e => e.textContent)")
        ok('통합: nothing hatched; that stock\'s tooltip has its KRX line and "NXT 거래 없음 · KRX 값이에요"',
           pg.evaluate("document.querySelectorAll('#map .tile.nonx').length") == 0 and len(t) == 2 and t[1] == 'NXT 거래 없음KRX 값이에요', t)
        ok('dim: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    # ───── a pick lasts while its phase lasts ─────
    if 'pick' in WANT and MODEARG == 'mock':
        ctx, pg, log, hold = fresh(b, 'd1440', 'pre')
        pick(pg, 'krx')
        s1 = pg.evaluate(STATE_JS); ev = pg.evaluate("(window.__kb || []).slice(-1)[0]")
        ok(f"pre → KRX: 'krx-prev', badge 'KRX 어제 종가', 삼성전자 {pct(CS['005930'][2])} (11/09 close.json), kh:basis krx-prev, nothing hatched",
           s1['basis'] == 'krx-prev' and s1['badge'] == 'KRX 어제 종가' and tile_pct(pg, '005930') == pct(CS['005930'][2]) and ev and ev['basis'] == 'krx-prev' and s1['nonx'] == 0, (s1, ev))
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        pg.reload(); pg.wait_for_timeout(3000)
        ok('same phase: the pick survives a poll and a reload', pg.evaluate("KH.basis()") == 'krx-prev', pg.evaluate("KH.basis()"))
        hold['phase'] = 'reg'; pg.clock.set_fixed_time(CLOCK['reg']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        s2 = pg.evaluate(STATE_JS)
        ok('09:00 regular with NXT 메인마켓: the pre-market pick is gone, 통합 by default ("통합 실시간")', s2['basis'] == 'int' and s2['seg'] == 'int' and s2['badge'] == '통합 실시간', s2)
        pick(pg, 'nxt'); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        r1 = pg.evaluate("KH.basis()")
        hold['phase'] = 'regular'; pg.clock.set_fixed_time(CLOCK['regular']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        r2 = pg.evaluate(STATE_JS)
        ok('regular: an NXT pick holds through polls; rows without NXT 메인마켓 → control hidden, KRX live', r1 == 'nxt' and r2['basis'] == 'krx' and r2['seg'] is None and r2['badge'] == '실시간', (r1, r2))
        hold['phase'] = 'pre'; pg.clock.set_fixed_time(CLOCK['pre']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        ok('next pre-market: 통합 by default', pg.evaluate("KH.basis()") == 'int', pg.evaluate("KH.basis()"))
        hold['phase'] = 'gap'; pg.clock.set_fixed_time(CLOCK['gap']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(700)
        g0 = pg.evaluate("KH.basis()")
        pick(pg, 'nxt', 400); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        g1 = pg.evaluate("KH.basis()")
        hold['phase'] = 'regular'; pg.clock.set_fixed_time(CLOCK['regular']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        hold['phase'] = 'gap'; pg.clock.set_fixed_time(CLOCK['gap']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        g2 = pg.evaluate("KH.basis()")
        ok('08:50–09:00: default krx-prev; NXT pick holds through a poll; after a phase change the default again', (g0, g1, g2) == ('krx-prev', 'nxt', 'krx-prev'), (g0, g1, g2))
        # the clock alone ends the pre-market (Naver still says OPEN at 08:53)
        hold['phase'] = 'pre'; pg.clock.set_fixed_time(CLOCK['pre']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        c0 = pg.evaluate("KH.basis()")
        hold['phase'] = 'stale'; pg.clock.set_fixed_time(CLOCK['stale']); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(600)
        c1 = pg.evaluate(STATE_JS)
        ok('08:53 with o:1 still: the clock closes the pre-market → KRX 어제 종가', c0 == 'int' and c1['basis'] == 'krx-prev' and c1['badge'] == 'KRX 어제 종가', (c0, c1))
        ok('pick: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()

    # ───── size: cap × p_basis / p_krx ─────
    if 'size' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        AR = "(() => { const L = KH.layout().filter(n => n.kind === 'tile'); const a = L.find(n => n.code === '005930'), b = L.find(n => n.code === '000660'); return a.w * a.h / (b.w * b.h); })()"
        w_int = pg.evaluate(AR)
        pick(pg, 'nxt', 900); w_nx = pg.evaluate(AR)
        pick(pg, 'krx', 900); w_kr = pg.evaluate(AR)
        want = (SS['nx']['p'] / SS['p']) / (HY['nx']['p'] / HY['p'])
        ok(f'tile area 삼성전자 : SK하이닉스 follows cap × p_basis / p_krx under NXT and 통합 (ratio of ratios {want:.4f})',
           abs((w_nx / w_kr) / want - 1) < 0.03 and abs((w_int / w_kr) / want - 1) < 0.03, (round(w_nx, 4), round(w_int, 4), round(w_kr, 4)))
        ctx.close()

    # ───── a replay stays KRX ─────
    if 'replay' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre')
        pg.evaluate("KH.setReplay({t:'1500', date:'2026-11-09', prices: new Map([['005930', {p: 188000, r: -0.37}]])})"); pg.wait_for_timeout(400)
        s = pg.evaluate(STATE_JS)
        ok(f"replay: KH.basis 'krx', no control, no hatching; frame 삼성전자 −0.37%; SK하이닉스 (not in the frame) its KRX close {pct(CS['000660'][2])}",
           s['basis'] == 'krx' and s['seg'] is None and s['nonx'] == 0 and tile_pct(pg, '005930') == '−0.37%' and tile_pct(pg, '000660') == pct(CS['000660'][2]), (s, tile_pct(pg, '000660')))
        pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(400)
        ok('replay off: 통합 again', pg.evaluate("KH.basis()") == 'int' and tile_pct(pg, '005930') == pct(int_row(QP, SS)[1]), tile_pct(pg, '005930'))
        ctx.close()

    # ───── flashes follow the drawn prices ─────
    if 'flash' in WANT and MODEARG == 'mock':
        def mover(q, n):
            if n < 2: return
            for i, s in enumerate(q['stocks']):
                if s.get('nx') and (i + n) % 5 < 2:
                    d = (1 if (i + n) % 2 else -1) * max(1, round(s['nx']['p'] * 0.002)); s['nx']['p'] += d; s['nx']['d'] += d
        ctx, pg, log, _ = fresh(b, 'd1440', 'pre', hook=mover, motion='fancy')
        pg.evaluate("window.__ch = null; document.addEventListener('kh:data', e => { window.__ch = e.detail.changed.length; })")
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
        r = pg.evaluate("({ch: window.__ch, ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length})")
        ok('통합 with NXT ticks: kh:data changed > 0 and tiles flash (fancy)', r['ch'] and r['ring'] > 0, r)
        pick(pg, 'nxt', 1200); pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
        r = pg.evaluate("({ch: window.__ch, ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length, nonx: document.querySelectorAll('#map .tile.nonx.fl-u, #map .tile.nonx.fl-d').length})")
        ok('NXT: tiles flash, none on hatched tiles', r['ch'] and r['ring'] > 0 and r['nonx'] == 0, r)
        pick(pg, 'krx', 1200)
        pg.evaluate("KH.refresh()"); pg.wait_for_timeout(150)
        r2 = pg.evaluate("({ch: window.__ch, ring: document.querySelectorAll('#map .tile.fl-u, #map .tile.fl-d').length})")
        ok('KRX (yesterday\'s closes) while NXT ticks: nothing flashes', r2['ch'] == 0 and r2['ring'] == 0, r2)
        ctx.close()

    # ───── quality: overflow, console, labels, tap targets, shots ─────
    if 'quality' in WANT:
        QPH = os.environ.get('QPH', 'pre,after,night,regular,reg,legacy').split(',')
        for ph in (QPH if MODEARG == 'mock' else ['now']):
            for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
                ctx, pg, log, _ = fresh(b, vp, ph if ph != 'now' else 'pre')
                for v in (['int', 'nxt'] if ph in ('pre', 'reg', 'now') else [None]):
                    if v and not pg.evaluate("document.getElementById('basis').hidden"): pick(pg, v, 400)
                    over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                    lab = pg.evaluate(LABEL_CHECK_JS)
                    hdr = pg.evaluate("""() => { const kids = [...document.querySelectorAll('.top > *, #status > *, #status .badge > *, #basis button')].filter(e => e.offsetParent && e.getClientRects().length);
                      const out = kids.filter(e => { const r = e.getBoundingClientRect(); return r.right > innerWidth + 0.5 || r.left < -0.5; }).map(e => e.id || e.className || e.tagName);
                      const st = document.getElementById('status').getBoundingClientRect(), ck = document.getElementById('clock').getBoundingClientRect();
                      return { out, overlap: ck.width > 0 && ck.right > st.left + 0.5 && ck.top < st.bottom && st.top < ck.bottom }; }""")
                    tap = pg.evaluate("[...document.querySelectorAll('#basis button')].filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })")
                    tapok = all(w >= 40 and hh >= 40 for w, hh in tap) if vp.startswith('m') else True
                    ok(f'{ph}{"/" + v if v else ""} {vp}: overflow 0, console 0, labels inside ({lab["visible"]}), header inside, basis buttons {tap}{" ≥ 40 px" if vp.startswith("m") else ""}',
                       over == 0 and not errs(log) and lab['overflow'] == 0 and not hdr['out'] and not hdr['overlap'] and tapok, (over, errs(log)[:2], lab['examples'][:1], hdr, tap))
                    if ph in ('pre', 'reg', 'now') and vp in ('m390', 'm360'):
                        pg.screenshot(path=SHOTS + f'nxt-{MODEARG}-{ph}-{v}-{vp}.png')
                if ph in ('pre', 'now') and vp in ('m360', 'm390', 't768', 'd1280'):
                    # table: hatched rows fit (below 1024 px no tag, the hatched chip and a muted name), no wider than under KRX
                    for cb in ['r', 'm1']:
                        pg.evaluate(f"localStorage.setItem('khm.colorBy', '\"{cb}\"')")
                        if cb == 'm1': pg.reload(); pg.wait_for_timeout(3000)
                        pick(pg, 'nxt', 300)
                        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(500)
                        TW = """() => { const w = document.getElementById('tablewrap'), r = w.querySelector('tr.nonx');
                          return { over: w.scrollWidth - w.clientWidth, page: document.documentElement.scrollWidth - innerWidth, n: w.querySelectorAll('tr.nonx').length,
                            tag: r ? getComputedStyle(r.querySelector('.nxtag')).display : null, chip: r ? getComputedStyle(r.querySelector('.nmcell i')).backgroundImage.slice(0, 16) : null }; }"""
                        t = pg.evaluate(TW)
                        pick(pg, 'krx', 500); base = pg.evaluate(TW)['over']
                        pick(pg, 'int', 500); ti = pg.evaluate(TW)
                        wide = vp.startswith('d') and not (cb == 'm1' and vp == 'd1280')      # 7 columns below 1440 px: no tag
                        ok(f'{ph} {vp} table ({cb}): {t["n"]} hatched rows under NXT, sideways NXT {t["over"]} / 통합 {ti["over"]} ≤ KRX {base}{" = 0" if vp.startswith("m") else ""}, tag {"shown" if wide else "hidden"}, chip hatched',
                           t['over'] <= max(base, 0) + 2 and ti['over'] <= max(base, 0) + 2 and (t['over'] <= 0 or not vp.startswith('m')) and t['page'] == 0 and ti['page'] == 0 and t['n'] > 0 and (t['tag'] != 'none') == wide and 'repeating' in (t['chip'] or ''), (t, ti, base))
                        pg.click('.viewseg button[data-v="map"]'); pg.wait_for_timeout(300)
                ctx.close()
        for ph in (['pre', 'after', 'reg'] if MODEARG == 'mock' else ['now']):
            for v in ['int', 'nxt']:
                ctx, pg, log, _ = fresh(b, 'd1440', ph if ph != 'now' else 'pre')
                if not pg.evaluate("document.getElementById('basis').hidden"): pick(pg, v, 500)
                pg.screenshot(path=SHOTS + f'nxt-{MODEARG}-{ph}-{v}-d1440.png')
                ctx.close()

    # ───── keyboard: the choice is reachable by Tab, works with Enter / Space, focus stays and shows ─────
    if 'keys' in WANT and MODEARG == 'mock':
        ctx, pg, log, _ = fresh(b, 'd1280', 'pre')
        hit = None
        for i in range(60):
            pg.keyboard.press('Tab')
            a = pg.evaluate("(() => { const e = document.activeElement; return e && e.closest('#basis') ? e.dataset.v : null; })()")
            if a: hit = (i + 1, a); break
        ok('Tab reaches the KRX · NXT · 통합 buttons', hit is not None, hit)
        pg.focus('#basis [data-v="krx"]'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
        a = pg.evaluate("({b: KH.basis(), f: document.activeElement.dataset.v, ring: getComputedStyle(document.activeElement).outlineStyle !== 'none' || getComputedStyle(document.activeElement).boxShadow !== 'none'})")
        pg.keyboard.press('Tab'); pg.keyboard.press('Space'); pg.wait_for_timeout(400)
        a2 = pg.evaluate("({b: KH.basis(), f: document.activeElement.dataset.v, pressed: document.activeElement.getAttribute('aria-pressed')})")
        pg.keyboard.press('Tab'); pg.keyboard.press('Space'); pg.wait_for_timeout(400)
        a3 = pg.evaluate("({b: KH.basis(), f: document.activeElement.dataset.v, pressed: document.activeElement.getAttribute('aria-pressed')})")
        ok('Enter on KRX → krx-prev (focus stays, visible); Tab + Space on NXT → nxt; Tab + Space on 통합 → int (aria-pressed true)',
           a['b'] == 'krx-prev' and a['f'] == 'krx' and a['ring'] and a2['b'] == 'nxt' and a2['f'] == 'nxt' and a2['pressed'] == 'true' and a3['b'] == 'int' and a3['f'] == 'int' and a3['pressed'] == 'true', (a, a2, a3))
        ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
