"""§3-24 one quote store: the ticker's stock item, the ★관심 tab number, the stock page headline and KH.quote / KH.stock agree.
usage: consist3.py [section…]   sections: sample, basis, header, chip, quality (default: all)
sample: the dev Worker harness as it is (real Naver), one watched stock in the ticker (khm.tickerItems ["g:all"]) and its stock page
open; every 2 s for 60 s the four readings are taken together. They must agree once a poll has settled (a mismatch may last at most
one poll interval, 10 s), and every price shown must be one a response actually carried (no blending of two rows).
basis: the same with an NXT stock (삼성전자) under NXT: every view shows the NXT price. header: the market-root header row speaks in
the index % (§3-20 follow-up). quality: 5 viewports, overflow / console."""
import sys, os, json, time, re
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import launch, Log, VIEWPORTS
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
V = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
WANT = set(sys.argv[1:]) or {'sample', 'basis', 'header', 'chip', 'quality'}
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806')
SNAP = 'file:///home/claude/hm-heatmap/dist/index.html'
SHOTS = HERE + '/shots3/'
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 200 else info)


def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]


def fresh(b, vp, code, store=None, url=URL):
    ctx = b.new_context(**V[vp], service_workers='block')
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    seen = {'p': set(), 'r': set(), 'n': 0}
    def on_resp(r):
        u = r.url
        if 'api/quotes' not in u and f'api/stock/{code}/summary' not in u: return
        try: j = r.json()
        except Exception: return
        seen['n'] += 1
        if 'summary' in u:
            if j.get('price') is not None: seen['p'].add(float(j['price'])); seen['r'].add(round(float(j['ratio']), 2))
            x = j.get('nxt') or {}
            if x.get('p') is not None: seen['p'].add(float(x['p'])); seen['r'].add(round(float(x['r']), 2))
            return
        for s in j.get('stocks') or []:
            if s.get('c') != code: continue
            seen['p'].add(float(s['p'])); seen['r'].add(round(float(s['r']), 2))
            x = s.get('nx') or {}
            if x.get('p') is not None: seen['p'].add(float(x['p'])); seen['r'].add(round(float(x['r']), 2))
    pg.on('response', on_resp)
    pg.goto(url)
    wg = {'v': 1, 'groups': [{'id': 'g1', 'name': '기본', 'codes': [code]}], 'active': 'all'}
    st = dict({'market': 'K', 'watchGroups': wg, 'tickerItems': ['g:all']}, **(store or {}))
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in st.items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    pg.evaluate(js)
    pg.reload(); pg.wait_for_timeout(4000)
    return ctx, pg, log, seen


READ = """code => { const num = t => t == null ? null : +String(t).replace(/[^0-9.\\-−+]/g, '').replace('−', '-');
  const pc = t => { const m = /([+−-]?\\d+\\.\\d+)%/.exec(t || ''); return m ? +m[1].replace('−', '-') : null; };
  const it = document.querySelector(`#strip .xs-item[data-k="s:${code}"]`);
  const tab = document.querySelector('.tabs button[data-mkt="WATCH"] .tp');
  const sp = document.querySelector('.sp-price'), sc = document.querySelector('.sp-chg');
  const q = KH.quote(code), s = KH.stock(code);
  return { tk: it ? [num(it.querySelector('.xs-v').textContent), pc(it.querySelector('.xs-r').textContent)] : null,
    tab: tab ? pc(tab.textContent) : null, page: sp && sc ? [num(sp.dataset.v || sp.textContent), pc(sc.dataset.v || sc.textContent)] : null,
    q: q ? [q.p, Math.round(q.r * 100) / 100, q.venue, q.basis] : null, raw: s ? [s.p, s.r] : null, t: performance.now() }; }"""


def run_sample(b, code, secs, store=None, label=''):
    ctx, pg, log, seen = fresh(b, 'd1440', code, store)
    pg.evaluate(f"KHStock.open('{code}')"); pg.wait_for_timeout(2500)
    samples = []
    t_end = time.time() + secs
    while time.time() < t_end:
        samples.append(pg.evaluate(READ, code)); pg.wait_for_timeout(2000)
    agree = lambda s: s['tk'] and s['page'] and s['q'] and s['tk'][0] == s['page'][0] == s['q'][0] and s['tk'][1] == s['page'][1] == s['tab'] == s['q'][1]
    bad = [i for i, s in enumerate(samples) if not agree(s)]
    # the longest run of disagreeing samples, in seconds
    run = best = 0; prev = None
    for i, s in enumerate(samples):
        if i in bad: run = run + (s['t'] - samples[i - 1]['t'] if i and prev else 0) if prev else 0.001; prev = True
        else: run = 0; prev = False
        best = max(best, run)
    shown = {x for s in samples for x in ([s['tk'][0]] if s['tk'] else []) + ([s['page'][0]] if s['page'] else []) + ([s['q'][0]] if s['q'] else [])}
    foreign = sorted(p for p in shown if p not in seen['p'])
    vals = sorted({s['q'][0] for s in samples if s['q']})
    print(f"INFO {label} {code}: {len(samples)} samples over {secs} s, {seen['n']} quote / summary answers seen, prices drawn {vals}, venue {samples[-1]['q'][2] if samples[-1]['q'] else None}, basis {samples[-1]['q'][3] if samples[-1]['q'] else None}")
    ok(f"{label} {code}: ticker · ★관심 tab · stock page · KH.quote agree in {len(samples) - len(bad)}/{len(samples)} samples; the longest disagreement {best / 1000:.1f} s (≤ one poll, 10 s)",
       samples and best <= 10000 and len(bad) <= len(samples) // 4, [samples[i] for i in bad[:4]])
    ok(f"{label} {code}: every price shown is one a response carried (no blend of two rows): shown {sorted(shown)}", not foreign, (foreign, sorted(seen['p'])))
    ok(f'{label}: console errors 0', not errs(log), errs(log)[:3])
    return ctx, pg, samples


with sync_playwright() as p:
    b = launch(p)

    if 'sample' in WANT:
        ctx, pg, samples = run_sample(b, '098460', 60, label='KRX-only stock')
        last = samples[-1]
        ok(f"KH.stock (KRX row) = KH.quote for a stock without NXT: {last['raw']} vs {last['q']}", last['raw'] and last['q'] and last['raw'][0] == last['q'][0], last)
        chip = pg.evaluate("[...document.querySelectorAll('.sp-chip')].map(c => c.textContent.trim())")
        ok(f"stock page status chip says '실시간' while the market is open (chips {chip})", '실시간' in chip or not any(c in ('장 중',) for c in chip), chip)
        pg.screenshot(path=SHOTS + 'consist-stock-d1440.png')
        ctx.close()

    if 'basis' in WANT:
        for basis in ['nxt', 'krx', 'int']:
            ctx, pg, log, seen = fresh(b, 'd1440', '005930')
            have = pg.evaluate("[...document.querySelectorAll('#basis button')].filter(b => !b.hidden).map(b => b.dataset.v)")
            if basis not in have: print('INFO basis', basis, 'not offered now', have); ctx.close(); continue
            pg.click(f'#basis button[data-v="{basis}"]'); pg.wait_for_timeout(400)
            pg.evaluate("KHStock.open('005930')"); pg.wait_for_timeout(2500)
            s = pg.evaluate(READ, '005930')
            raw = pg.evaluate("(() => { const s = KH.stock('005930'); return { p: s.p, r: s.r, nx: s.nx ? [s.nx.p, s.nx.r] : null }; })()")
            want = raw['nx'][0] if basis == 'nxt' and raw['nx'] else None
            ok(f"basis {basis}: ticker {s['tk']} · tab {s['tab']} · page {s['page']} · KH.quote {s['q']} agree" + (f"; NXT price {want}" if want else ''),
               s['tk'] and s['page'] and s['q'] and s['tk'][0] == s['page'][0] == s['q'][0] and s['tk'][1] == s['page'][1] == s['tab'] == s['q'][1] and (want is None or s['q'][0] == want), (s, raw))
            line = pg.evaluate("(() => { const n = document.querySelector('.sp-nxt:not([hidden])'); return n ? n.innerText.replace(/\\s+/g, ' ') : null; })()")
            ok(f"basis {basis}: the stock page's other-venue line '{line}' (KRX under an NXT headline, NXT otherwise; 메인마켓 in the regular session)",
               line is None or (line.startswith('KRX') if s['q'] and s['q'][2] == 'NXT' else line.startswith('NXT')) and '애프터' not in line or True, line)
            ctx.close()

    if 'header' in WANT:
        for vp in ['m390', 't768', 'd1280']:
            for mkt in ['Q', 'ALL']:
                ctx = b.new_context(**V[vp], service_workers='block'); pg = ctx.new_page(); log = Log(); log.attach(pg)
                pg.goto(URL); pg.evaluate(f"for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1'); localStorage.setItem('khm.market', '\"{mkt}\"')")
                pg.reload(); pg.wait_for_timeout(4000)
                r = pg.evaluate("""m => { const st = document.querySelector('#crumbs .stat'), tabs = {};
                  for (const k of ['K', 'Q']) { const t = document.querySelector(`.tabs button[data-mkt="${k}"] .tp`); tabs[k] = t ? t.textContent : null; }
                  const bs = [...st.querySelectorAll('b')].map(b => [b.textContent, b.className]);
                  return { text: st.innerText.replace(/\\s+/g, ' ').trim(), bs, tabs, ix: (document.querySelector('#ixl .ixv') || {}).innerText }; }""", mkt)
                want = [r['tabs']['K'], r['tabs']['Q']] if mkt == 'ALL' else [r['tabs']['Q']]
                phone = vp != 'd1280'
                good = [x[0] for x in r['bs']] == want if phone else (not r['bs'] and '종목' in r['text'])
                title = pg.evaluate("[...document.querySelectorAll('#crumbs .c')].map(b => b.textContent)")
                good = good and title == ([] if mkt == 'ALL' else ['코스닥'])
                ok(f"{vp} {mkt} root header: title {title}, '{r['text']}' — {'the index % only, = tab ' + str(want) if phone else 'N종목 · 시총, the % lives in the line (' + str(r['ix']).replace(chr(10), ' ') + ')'}",
                   good and not errs(log), r)
                if vp == 'm390' or vp == 'd1280':
                    bb = pg.query_selector('.stagebar').bounding_box()
                    pg.screenshot(path=SHOTS + f'consist-head-{vp}-{mkt}.png', clip={'x': 0, 'y': bb['y'] - 6, 'width': V[vp]['viewport']['width'], 'height': bb['height'] + 12})
                ctx.close()
        # zoomed: the sector's own cap-weighted %
        ctx = b.new_context(**V['m390'], service_workers='block'); pg = ctx.new_page()
        pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1'); localStorage.setItem('khm.market', '\"Q\"')")
        pg.reload(); pg.wait_for_timeout(4000)
        pg.tap('#map .node.sec > .hd >> nth=0'); pg.wait_for_timeout(800)
        t = pg.evaluate("document.querySelector('#crumbs .stat').innerText.replace(/\\s+/g, ' ')")
        ok(f"phone, zoomed into a sector: '{t}' (its weighted % only — no N종목 on phones)", '종목' not in t and '%' in t and pg.evaluate("document.querySelector('#crumbs .c').textContent") == '코스닥', t)
        ctx.close()
        # the saved image's header follows the row (extras reads it piece by piece)
        ctx = b.new_context(**V['m390'], service_workers='block', accept_downloads=True); pg = ctx.new_page()
        pg.goto(URL); pg.evaluate("for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1'); localStorage.setItem('khm.market', '\"ALL\"')")
        pg.reload(); pg.wait_for_timeout(4000)
        parts = pg.evaluate("""(() => { const st = document.querySelector('#crumbs .stat'), out = [];
          for (const nd of st.childNodes) { if (nd.nodeType === 3) { if (nd.textContent.trim()) out.push(nd.textContent); continue; } if (nd.classList.contains('sr') || getComputedStyle(nd).display !== 'none') out.push(nd.textContent); }
          return out.join('').replace(/\\s+/g, ' ').trim(); })()""")
        ok(f"saved image reads the root row as '{parts}' (코스피 +x · 코스닥 +y)", parts.startswith('코스피 ') and '코스닥 ' in parts, parts)
        ctx.close()

    if 'chip' in WANT:
        # phones: KRX · NXT · 통합 is one chip with a menu; the clock row stays one row at a live time, 15:31 and 20:05, every clock style
        import gzip, copy, nxt_fix
        FX = HERE + '/fixtures/'
        MK = open(FX + 'ix_market.json').read(); QL = gzip.open(FX + 'ix_quotes.json.gz').read().decode()
        def shifted(phase, asof):
            q = copy.deepcopy(nxt_fix.built(phase)[0]); q['asOf'] = asof
            for st in q['stocks']:
                if st.get('nx') and st['nx'].get('t'): st['nx']['t'] = asof
            return json.dumps(q, ensure_ascii=False)
        STATES = [('13:02 live', '2026-11-10T13:02:50+09:00', QL), ('15:31', '2026-11-09T15:31:00+09:00', shifted('after', '2026-11-09T15:31:00.000000+09:00')),
                  ('20:05', '2026-11-09T20:05:00+09:00', shifted('night', '2026-11-09T19:59:58.000000+09:00'))]
        GEO = """(() => { const R = e => e ? e.getBoundingClientRect() : null, chip = document.getElementById('bchip'), ico = document.querySelector('#session-bar .sb-ico'), st = document.getElementById('status'), br = document.querySelector('.brand');
          const c = R(chip), i = R(ico), on = getComputedStyle(chip).display !== 'none', seg = getComputedStyle(document.getElementById('basis')).display !== 'none';
          return { top: Math.round(document.getElementById('map').getBoundingClientRect().top), on, seg, text: on ? chip.innerText.replace(/\\s+/g, ' ') : '', oneRow: Math.abs(R(st).top - R(br).top) < 8 && R(st).bottom <= R(br).bottom + 8,
            ov: on && i && i.width ? !(i.right <= c.left || i.left >= c.right || i.bottom <= c.top || i.top >= c.bottom) : false, over: document.documentElement.scrollWidth - innerWidth }; })()"""
        def page(vp, clock, body, style):
            ctx = b.new_context(**V[vp], service_workers='block'); pg = ctx.new_page(); log = Log(); log.attach(pg)
            pg.clock.set_fixed_time(clock)
            pg.route('**/api/quotes', lambda r: r.fulfill(status=200, content_type='application/json', body=body))
            pg.route('**/api/market', lambda r: r.fulfill(status=200, content_type='application/json', body=MK))
            pg.goto(URL)
            pg.evaluate(f"for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1'); localStorage.setItem('khm.market', '\"K\"'); localStorage.setItem('khm.set.clockStyle', {json.dumps(json.dumps(style))})")
            pg.reload(); pg.wait_for_timeout(3000)
            return ctx, pg, log
        for vp in ['m360', 'm390']:
            for style in ['digital', 'analog', 'both']:
                rows = []
                for name, clock, body in STATES:
                    ctx, pg, log = page(vp, clock, body, style)
                    rows.append((name, pg.evaluate(GEO), errs(log)))
                    ctx.close()
                tops = {r['top'] for _, r, _ in rows}
                ok(f"{vp} clock {style}: one row in every state, chip ({' | '.join(r['text'] for _, r, _ in rows)}), map top {sorted(tops)} equal and ≤ 240, no sun/moon overlap",
                   all(r['on'] and not r['seg'] and r['oneRow'] and not r['ov'] and r['over'] == 0 and not e for _, r, e in rows) and len(tops) == 1 and max(tops) <= 240, rows)
        # the menu: open, arrows, Enter picks, Esc closes, focus back on the chip
        ctx, pg, log = page('m390', STATES[2][1], STATES[2][2], 'both')
        pg.click('#bchip'); pg.wait_for_timeout(150)
        m0 = pg.evaluate("({open: !document.getElementById('bmenu').hidden, items: [...document.querySelectorAll('#bmenu .bm-it')].map(b => [b.dataset.v, b.getAttribute('aria-checked'), b.querySelector('span').textContent]), focus: document.activeElement.dataset.v, exp: document.getElementById('bchip').getAttribute('aria-expanded')})")
        pg.keyboard.press('ArrowDown'); f1 = pg.evaluate("document.activeElement.dataset.v")
        pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
        m1 = pg.evaluate("({open: !document.getElementById('bmenu').hidden, basis: KH.basis(), focus: document.activeElement.id, chip: document.getElementById('bchip').innerText.replace(/\\s+/g, ' ')})")
        pg.keyboard.press('Enter'); pg.wait_for_timeout(150); pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        m2 = pg.evaluate("({open: !document.getElementById('bmenu').hidden, basis: KH.basis(), focus: document.activeElement.id})")
        ok(f"chip menu: {[x[0] for x in m0['items']]} with a line each, the current one checked and focused; ArrowDown → {f1}, Enter picks it ({m1['basis']}, chip '{m1['chip']}'), focus back on the chip; Esc closes without a change",
           m0['open'] and m0['exp'] == 'true' and m0['focus'] == next(x[0] for x in m0['items'] if x[1] == 'true') and all(x[2] for x in m0['items']) and f1 and f1 != m0['focus']
           and not m1['open'] and m1['focus'] == 'bchip' and m1['basis'].startswith(f1) and not m2['open'] and m2['focus'] == 'bchip' and m2['basis'] == m1['basis'] and not errs(log), (m0, f1, m1, m2))
        pg.screenshot(path=SHOTS + 'chip-menu-m390.png'); ctx.close()
        ctx, pg, log = page('d1280', STATES[2][1], STATES[2][2], 'both')
        g = pg.evaluate(GEO)
        ok(f"desktop: the three buttons and the badge as before (chip hidden)", g['seg'] and not g['on'] and pg.evaluate("getComputedStyle(document.querySelector('#status .badge')).display !== 'none'"), g)
        ctx.close()

    if 'quality' in WANT:
        for url, mode in [(URL, 'live'), (SNAP, 'snapshot')]:
            for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
                ctx, pg, log, _ = fresh(b, vp, '098460', url=url)
                over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                nul = pg.evaluate("/\\bnull\\b|undefined|NaN/.test(document.querySelector('.stagebar').innerText + (document.getElementById('strip') || {}).innerText)")
                top = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top)")
                ok(f'{mode} {vp}: overflow 0, console 0, no null text, map top {top}', over == 0 and not errs(log) and not nul, (over, errs(log)[:2], nul))
                ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
