#!/usr/bin/env python3
"""QA for the 투자자별 순매수 카드 (src/flows), the 요약 카드 close.json date fix + 수급 line (src/summary) and the stock page's 오늘 잠정
block (src/stock) — AGENTS §3-40 · §3-34 고칠 것 ①.

  python3 scripts/build_page.py && python3 qa/flows/test_flows_card.py [--shots]

Starts qa/flows/mock_flows.py on FLOWS_CARD_PORT (default 9095; 9095–9099) — SYNTHETIC flows · market · rank · 잠정 rows over the snapshot's
codes — and stops it with fuser -k at the end. The page's clock is fixed per scenario (Playwright clock.set_fixed_time; the mock's
/api/time answers the same instant). KH.inv / KH.flowsLive come from a stub injected before the template runs (the template part lands
separately): has() = window.__fam, data() = window.__live, want() is recorded, fetch() adds X-Panse-Inv. window.__stub = false leaves the
template's own (or none — an old template).

Checks: public vs family (rows = flows.json 1일 column ranked per market / the rank lists merged for 전체, labels "M/D (요일) 확정" ·
"잠정 · HH:MM 입력분" + 한국투자증권 가집계, 개인 confirmed + note, no 잠정 · 한국투자 · 가족 · request on a public device, want() only near the
viewport), the 외국인 · 기관 · 개인 × 순매수 · 순매도 segments, 코스피 · 코스닥 · 전체 tabs, 10 rows + 더보기 to 30 (the fold: the list box
grows on `open`, what is below moves once; collapsing brings focus back), a row opens what the 눈에 띄는 종목 card opens, the market-wide
line ("HH:MM 기준", stale !, fail + retry, 404 hidden, loading words), polling 60 s in the session near the viewport / 10 min otherwise,
the footer line (after 공시 · 정책 자료, the disclaimer last), placement right after #moverCard and the map top unchanged (390 × 844 247,
1280 · 1440 207), the summary card (after + a late close.json → /api/breadth + KRX quotes: no old 상한가; ?summary_phase=after the same; pre
with a late file → its date in the head · lines; the 수급 line from /api/flows/market with "HH:MM 기준", the per-stock lines with the file's
date; 404 → the file), the stock page's 오늘 잠정 block (family only, rows per round, sign colours, 09:30 기관 —, 404 · 403 · snapshot → none,
fail → ! + retry), the snapshot (dist/), 4 themes × 360 · 1280 overflow 0 (public and family), console errors 0. Exit 1 on a fail.
"""
import datetime as dt
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
PORT = int(os.environ.get('FLOWS_CARD_PORT', 9095))
assert 9095 <= PORT <= 9099, PORT
URL = f'http://127.0.0.1:{PORT}/'
SHOTS = '--shots' in sys.argv
OUT = ROOT / 'qa/shots/flows_card'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
KST = dt.timezone(dt.timedelta(hours=9))
fails, counts = [], {'pass': 0}
MINUS = '−'


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{str(detail)[:400]}]' if detail not in ('', None, [], {}) and not ok else ''), flush=True)
    if ok:
        counts['pass'] += 1
    else:
        fails.append(name)


def mock(path):
    return json.loads(NOPROXY.open(URL + path.lstrip('/'), timeout=10).read())


def config(**kw):
    mock('__freset')
    if kw:
        mock('__config?' + '&'.join(f'{k}={urllib.request.quote(str(v), safe="")}' for k, v in kw.items()))


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/flows/mock_flows.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            mock('api/time'); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


# ── expectations (the same rules as src/flows, from the mock's own fixture) ──
NAMES = json.loads((ROOT / 'web/names.json').read_text(encoding='utf-8'))['n']
MKT = {c: v[1] for c, v in NAMES.items()}


def eok_abs(a):
    if a >= 10000:
        return f'{a / 10000:,.1f}조'
    if a >= 10:
        return f'{int(a + 0.5):,}억'          # Math.round (Python's round() is banker's)
    return f'{a:,.1f}억'


def amt(v):
    a = abs(v)
    return ('' if a < 0.05 else ('+' if v > 0 else MINUS)) + eok_abs(a)


def file_rank(F, sc, who, d):
    ix = {'f': 0, 'i': 1, 'p': 2}[who]
    stale = F.get('stale') or {}
    out = [(c, v[ix]) for c, v in F['f'].items() if c not in stale and v[ix] is not None and ((v[ix] > 0) if d == 'buy' else (v[ix] < 0))
           and (sc == 'KQ' or MKT.get(c) == sc)]
    out.sort(key=lambda t: (-t[1] if d == 'buy' else t[1], t[0]))
    return out[:30]


def live_rank(L, sc, who, d):
    out = []
    for m in (['K', 'Q'] if sc == 'KQ' else [sc]):
        for r in L['rank'][m][who][d]:
            out.append((r[0], abs(r[2]) * (1 if d == 'buy' else -1)))
    out.sort(key=lambda t: (-t[1] if d == 'buy' else t[1], t[0]))
    return out[:30]


def mdw(ymd):
    d = dt.date.fromisoformat(ymd)
    return f'{d.month}/{d.day} ({"월화수목금토일"[d.weekday()]})'


STUB = """(() => {
  const TOKEN = %s;
  window.__wants = []; window.__invFetch = [];
  const inv = {
    has: () => !!window.__fam, name: () => (window.__fam ? 'QA' : null), own: () => false, ready: () => Promise.resolve(!!window.__fam),
    fetch: (path, init) => { window.__invFetch.push(path); const o = Object.assign({}, init || {}); o.headers = Object.assign({}, o.headers || {}, window.__fam ? { 'X-Panse-Inv': TOKEN } : {}); return fetch(path, o); },
    forget: () => { window.__fam = false; document.dispatchEvent(new CustomEvent('kh:inv', { detail: { on: false } })); },
  };
  const live = { data: () => (window.__fam ? window.__live || null : null), want: (k, on) => { window.__wants.push([k, !!on]); }, refresh: () => {} };
  let K;
  Object.defineProperty(window, 'KH', { configurable: true, get() { return K; }, set(v) {
    K = v;
    if (window.__stub !== false && v) for (const [k, val] of [['inv', inv], ['flowsLive', live]]) Object.defineProperty(v, k, { configurable: true, enumerable: true, get: () => val, set() {} });
  } });
})();"""


def when(y, mo, d, hh, mm):
    return dt.datetime(y, mo, d, hh, mm, tzinfo=KST)


def open_page(br, w, h, *, at, fam=False, live=None, stub=True, theme='base', market='K', query='', motion='standard', url=None, scroll=False, wait=2600, token=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    if token:
        st['inv'] = token                     # the template's own invite token (khm.inv, JSON like every khm.* key)
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    ctx.add_init_script(f'window.__fam = {json.dumps(bool(fam))}; window.__live = {json.dumps(live)}; window.__stub = {json.dumps(bool(stub))};')
    ctx.add_init_script(STUB % json.dumps(FIX['token']))
    pg = ctx.new_page()
    errs = []
    pg.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' and 'favicon' not in m.text else None)
    pg.on('pageerror', lambda e: errs.append(f'pageerror: {e}'))
    if at is not None:
        pg.clock.set_fixed_time(at)
    pg.goto((url or URL) + query)
    pg.wait_for_timeout(wait)
    if scroll:
        pg.evaluate("document.getElementById('flowsCard').scrollIntoView({block: 'center'})")
        pg.wait_for_timeout(700)
    return ctx, pg, errs


CARD = """() => { const c = document.getElementById('flowsCard'); if (!c) return null;
  const rows = [...c.querySelectorAll('.fl-list .fl-r')].map(b => ({ c: b.dataset.c, rk: b.querySelector('.fl-rk').textContent, nm: b.querySelector('.nm').textContent,
    a: b.querySelector('.fl-a').textContent, ac: b.querySelector('.fl-a').className, p: b.querySelector('.fl-p').textContent, cdi: !!b.querySelector('.cdi:not(.none)') }));
  const mt = [...c.querySelectorAll('.fl-mt tbody tr')].map(tr => [...tr.children].map(x => x.textContent));
  const more = c.querySelector('.fl-more');
  return { text: c.innerText, scope: c.querySelector('.fl-scope').textContent, lab: c.querySelector('.fl-lab').innerText, src: c.dataset.src, rows, mt,
    at: (c.querySelector('.fl-at') || {}).textContent || null, atStale: !!c.querySelector('.fl-at.stale'), mktHidden: c.querySelector('.fl-mkt').hidden,
    more: more.hidden ? null : more.textContent, exp: more.getAttribute('aria-expanded'), note: c.querySelector('.fl-note').hidden ? '' : c.querySelector('.fl-note').textContent,
    who: [...c.querySelectorAll('.fl-ctl .movers-tabs')[0].children].filter(b => b.tagName === 'BUTTON' && b.getAttribute('aria-pressed') === 'true').map(b => b.textContent),
    dir: [...c.querySelectorAll('.fl-ctl .movers-tabs')[1].children].filter(b => b.tagName === 'BUTTON' && b.getAttribute('aria-pressed') === 'true').map(b => b.textContent),
    ind: [...c.querySelectorAll('.fl-ctl .movers-tabs')].map(s => s.dataset.ind != null) }; }"""
FOOT = """() => { const f = document.getElementById('foot'); const ps = [...f.children].map(p => p.id || p.className || 'p');
  return { ids: ps, text: f.innerText, last: f.lastElementChild.textContent, flows: (document.getElementById('foot-flows') || {}).textContent || null }; }"""


def pick(pg, seg, label):
    pg.click(f'#flowsCard .fl-ctl .movers-tabs:nth-of-type({seg}) button:text-is("{label}")')
    pg.wait_for_timeout(250)


def tab(pg, mkt):
    pg.click(f'header [data-mkt="{mkt}"]') if pg.locator(f'header [data-mkt="{mkt}"]').count() else pg.click(f'[data-mkt="{mkt}"]')
    pg.wait_for_timeout(700)


def overflow(pg):
    return pg.evaluate("""() => { const c = document.getElementById('flowsCard'); if (!c) return ['no card']; const W = innerWidth, bad = [];
      const cr = c.getBoundingClientRect(); if (cr.right > W + 0.5 || cr.left < -0.5) bad.push('card ' + Math.round(cr.left) + '..' + Math.round(cr.right));
      for (const el of c.querySelectorAll('*')) { const r = el.getBoundingClientRect(); if (!r.width) continue;
        if (r.right > cr.right + 0.5 && !el.closest('.fl-r')) bad.push((el.className || el.tagName) + ' ' + Math.round(r.right - cr.right)); }
      for (const el of c.querySelectorAll('.fl-r, .fl-ctl, .fl-mt, .fl-lab')) if (el.scrollWidth > el.clientWidth + 1) bad.push('scroll ' + el.className);
      const sw = document.documentElement.scrollWidth; if (sw > W + 1) bad.push('page ' + sw);
      return bad.slice(0, 6); }""")


FIX = None


def main():
    global FIX
    if SHOTS:
        OUT.mkdir(parents=True, exist_ok=True)
    start_mock()
    FIX = mock('__fixture')
    F, L, MK = FIX['flows'], FIX['live'], FIX['market']
    session = when(2026, 11, 24, 13, 5)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])

            # ── 1. public · session · 1440 ─────────────────────────────────────────────
            config()
            ctx, pg, errs = open_page(br, 1440, 900, at=session)
            place = pg.evaluate("(() => { const c = document.getElementById('flowsCard'), m = document.getElementById('moverCard'); return c && { prev: c.previousElementSibling && c.previousElementSibling.id, side: c.parentElement.classList.contains('side'), h2: c.querySelector('h2').textContent }; })()")
            check('1440: the card sits in the side column right after 눈에 띄는 종목 (#moverCard), title 투자자별 순매수', place and place['prev'] == 'moverCard' and place['side'] and place['h2'].startswith('투자자별 순매수'), place)
            near0 = pg.evaluate("KHFlows.state()")
            check('far from the viewport: no want(), market polled every 10 min', near0['near'] is False and not pg.evaluate('window.__wants.length') and near0['ttl'] == 600000, near0['ttl'])
            pg.evaluate("document.getElementById('flowsCard').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(800)
            st = pg.evaluate("KHFlows.state()")
            check('session + near the viewport: market polled every 60 s', st['near'] and st['session'] and st['ttl'] == 60000, {k: st[k] for k in ('near', 'session', 'ttl')})
            c = pg.evaluate(CARD)
            want = file_rank(F, 'K', 'f', 'buy')
            check('public 코스피 외국인 순매수: 10 rows = flows.json [0] ranked among 코스피 stocks, amounts 억 · 조 in up colour',
                  [r['c'] for r in c['rows']] == [x[0] for x in want[:10]] and [r['a'] for r in c['rows']] == [amt(x[1]) for x in want[:10]] and all('up' in r['ac'].split() for r in c['rows']),
                  {'got': [(r['c'], r['a']) for r in c['rows'][:4]], 'want': [(x[0], amt(x[1])) for x in want[:4]]})
            check('row: rank · today candle · name · amount · small 등락률 (= the quote)', [r['rk'] for r in c['rows']] == [str(i) for i in range(1, 11)] and sum(r['cdi'] for r in c['rows']) >= 8
                  and all(re.fullmatch(r'[+−]?\d+\.\d\d%|0\.00%|—', r['p']) for r in c['rows']), c['rows'][:2])
            aria = pg.evaluate("(() => { const l = document.querySelector('#flowsCard .fl-list'), it = [...l.children]; return { list: l.getAttribute('role'), items: it.length, li: it.every(x => x.getAttribute('role') === 'listitem' && x.children.length === 1 && x.firstElementChild.tagName === 'BUTTON' && !x.firstElementChild.hasAttribute('role')) }; })()")
            check('a11y: role="list" → div role="listitem" → a real button (no role taken away)', aria['list'] == 'list' and aria['items'] == 10 and aria['li'], aria)
            check(f'public label "{mdw(F["asOf"])} 확정", scope 코스피, src file', c['lab'].startswith(mdw(F['asOf']) + ' 확정') and c['scope'] == '코스피' and c['src'] == 'file', [c['lab'], c['scope'], c['src']])
            mk = MK['K']
            check('market-wide line: 코스피 외국인 · 기관 · 개인 from /api/flows/market + "13:05 기준"', c['mt'] == [['코스피', amt(mk['foreign']), amt(mk['institutional']), amt(mk['personal'])]] and c['at'] == '13:05 기준' and not c['atStale'], [c['mt'], c['at']])
            check('segments: 외국인 · 순매수 pressed, both indicators placed (KH.ui.seg)', c['who'] == ['외국인'] and c['dir'] == ['순매수'] and all(c['ind']), [c['who'], c['dir'], c['ind']])
            body = pg.evaluate('document.body.innerText')
            check('public device: no 잠정 · 한국투자 · 가족 anywhere on the page', not re.search(r'잠정|한국투자|가족|초대', body), re.findall(r'.{10}(?:잠정|한국투자|가족).{10}', body)[:3])
            fs = mock('__fstats')
            check('public device: no family request (live · live/stock · inv), want() never called', not any(fs.get(k) for k in ('live', 'live/stock', 'inv')) and not pg.evaluate('window.__wants.filter(w => w[1]).length'), [fs, pg.evaluate('window.__wants')])
            ft = pg.evaluate(FOOT)
            check('footer: "투자자별 순매수: 네이버 증권 …" right after 정책 자료 / 공시, the disclaimer stays last', ft['flows'] and ft['flows'].startswith('투자자별 순매수: 네이버 증권') and '한국투자' not in ft['text']
                  and ft['ids'].index('foot-flows') == ft['ids'].index('foot-policy' if 'foot-policy' in ft['ids'] else 'foot-disc') + 1 and ft['last'] == '투자 판단의 근거로 쓰지 마세요.', ft['ids'])
            # tabs: 기관 / 개인 / 순매도
            for seg, lab, who, d in ((1, '기관', 'i', 'buy'), (1, '개인', 'p', 'buy'), (2, '순매도', 'p', 'sell'), (1, '외국인', 'f', 'sell')):
                pick(pg, seg, lab)
                c = pg.evaluate(CARD)
                w = file_rank(F, 'K', who, d)
                check(f'tab → {who} {d}: rows = flows.json [{ {"f": 0, "i": 1, "p": 2}[who]}] {"desc" if d == "buy" else "asc"}, {"up" if d == "buy" else "down"} colour',
                      [r['c'] for r in c['rows']] == [x[0] for x in w[:10]] and [r['a'] for r in c['rows']] == [amt(x[1]) for x in w[:10]] and all(('up' if d == 'buy' else 'dn') in r['ac'].split() for r in c['rows']),
                      [(r['c'], r['a']) for r in c['rows'][:3]])
            check('the choice is remembered (khm.flowsWho · khm.flowsDir)', pg.evaluate("[localStorage.getItem('khm.flowsWho'), localStorage.getItem('khm.flowsDir')]") == ['"f"', '"sell"'])
            pick(pg, 2, '순매수')
            # 더보기 → 30 (the fold), 접기 → 10 with focus back on the key
            c = pg.evaluate(CARD)
            check('더보기 (30개) under 10 rows, aria-expanded false', c['more'] == '더보기 (30개)' and c['exp'] == 'false' and len(c['rows']) == 10, c['more'])
            fr = pg.evaluate("""() => new Promise(res => { const c = document.getElementById('flowsCard'), list = c.querySelector('.fl-list'), more = c.querySelector('.fl-more');
              const out = []; const y0 = more.getBoundingClientRect().top; more.click(); const t0 = performance.now();
              const step = () => { out.push([Math.round(performance.now() - t0), Math.round(more.getBoundingClientRect().top - y0), list.style.clipPath || '', list.classList.contains('fl-fold-in')]);
                if (performance.now() - t0 < 700) requestAnimationFrame(step); else res(out); }; requestAnimationFrame(step); })""")
            moves = sorted({x[1] for x in fr})
            clipped = [x for x in fr if x[2]]
            check('더보기 = the fold: what is below moves once (at the press), the list box opens on a clip, new rows come in after a quarter',
                  len(moves) == 1 and moves[0] > 200 and len(clipped) >= 3 and any(x[3] for x in fr) and not fr[-1][2], {'moves': moves, 'clipped': len(clipped), 'last': fr[-1]})
            c = pg.evaluate(CARD)
            check('expanded: 30 rows (ranks 1–30), key 접기, aria-expanded true', len(c['rows']) == 30 and c['rows'][-1]['rk'] == '30' and c['more'] == '접기' and c['exp'] == 'true', [len(c['rows']), c['more']])
            pick(pg, 1, '기관')
            c = pg.evaluate(CARD)
            w30 = [x[0] for x in file_rank(F, 'K', 'i', 'buy')]
            check('a tab keeps the list expanded (30 rows of 기관)', len(c['rows']) == 30 and [r['c'] for r in c['rows']] == w30, [len(c['rows']), [(i, r['c'], w30[i] if i < len(w30) else None) for i, r in enumerate(c['rows']) if i >= len(w30) or r['c'] != w30[i]][:4]])
            pg.click('#flowsCard .fl-more'); pg.wait_for_timeout(800)
            c = pg.evaluate(CARD)
            foc = pg.evaluate("document.activeElement && document.activeElement.className")
            check('접기 → 10 rows, focus on the key', len(c['rows']) == 10 and c['more'] == '더보기 (30개)' and foc == 'fl-more', [len(c['rows']), foc])
            pick(pg, 1, '외국인')
            # a row opens what the movers card opens (the stock page)
            pg.click('#flowsCard .fl-r >> nth=0'); pg.wait_for_timeout(900)
            a = pg.evaluate("[window.KHStock && KHStock.isOpen(), location.hash]")
            pg.keyboard.press('Escape'); pg.wait_for_timeout(700)
            pg.click('#movers > button >> nth=0'); pg.wait_for_timeout(900)
            b = pg.evaluate("[window.KHStock && KHStock.isOpen(), location.hash]")
            pg.keyboard.press('Escape'); pg.wait_for_timeout(700)
            check('a row opens the stock page — the same thing a 눈에 띄는 종목 row opens', a[0] is True and a[1] == '#s-' + file_rank(F, 'K', 'f', 'buy')[0][0] and b[0] is True, [a, b])
            # 코스닥 · 전체
            tab(pg, 'Q')
            c = pg.evaluate(CARD)
            mq = MK['Q']
            check('코스닥 tab: scope 코스닥, rows ranked among 코스닥 stocks, market line 코스닥', c['scope'] == '코스닥' and [r['c'] for r in c['rows']] == [x[0] for x in file_rank(F, 'Q', 'f', 'buy')[:10]]
                  and c['mt'] == [['코스닥', amt(mq['foreign']), amt(mq['institutional']), amt(mq['personal'])]], [c['scope'], c['mt']])
            tab(pg, 'ALL')
            c = pg.evaluate(CARD)
            check('전체 tab: both markets — the list over every stock, the market table two rows', c['scope'] == '코스피 · 코스닥' and [r['c'] for r in c['rows']] == [x[0] for x in file_rank(F, 'KQ', 'f', 'buy')[:10]]
                  and [r[0] for r in c['mt']] == ['코스피', '코스닥'], [c['scope'], [r[0] for r in c['mt']]])
            tab(pg, 'THEME')
            c = pg.evaluate(CARD)
            check('테마 tab (other tabs): both markets too', c is not None and c['scope'] == '코스피 · 코스닥', c and c['scope'])
            tab(pg, 'K')
            check('1440 public: console errors 0', not errs, errs[:3])
            if SHOTS:
                pg.locator('#flowsCard').screenshot(path=str(OUT / 'public_1440.png'))
            ctx.close()

            # ── 2. family · session ────────────────────────────────────────────────────
            config()
            ctx, pg, errs = open_page(br, 1440, 900, at=session, fam=True, live=L)
            check('family, far from the viewport: want() not yet', not pg.evaluate('window.__wants.filter(w => w[1]).length'), pg.evaluate('window.__wants'))
            pg.evaluate("document.getElementById('flowsCard').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(800)
            check("family near the viewport: KH.flowsLive.want('card', true)", pg.evaluate('window.__wants') [-1:] == [['card', True]], pg.evaluate('window.__wants'))
            c = pg.evaluate(CARD)
            w = live_rank(L, 'K', 'f', 'buy')
            check('family 외국인: today\'s 잠정 rank (rank.K.f.buy), label "잠정 · 13:20 입력분" + 한국투자증권 가집계, src live',
                  c['src'] == 'live' and [r['c'] for r in c['rows']] == [x[0] for x in w[:10]] and [r['a'] for r in c['rows']] == [amt(x[1]) for x in w[:10]]
                  and c['lab'].startswith('잠정 · 13:20 입력분') and '한국투자증권 가집계' in c['lab'], [c['src'], c['lab'], [(r['c'], r['a']) for r in c['rows'][:3]]])
            pick(pg, 2, '순매도')
            c = pg.evaluate(CARD)
            w = live_rank(L, 'K', 'f', 'sell')
            check('family 순매도: rank.K.f.sell, amounts −', [r['c'] for r in c['rows']] == [x[0] for x in w[:10]] and all(r['a'].startswith(MINUS) and 'dn' in r['ac'].split() for r in c['rows']), [r['a'] for r in c['rows'][:3]])
            pick(pg, 2, '순매수')
            pick(pg, 1, '기관')
            c = pg.evaluate(CARD)
            check('family 기관: rank.K.i.buy', c['src'] == 'live' and [r['c'] for r in c['rows']] == [x[0] for x in live_rank(L, 'K', 'i', 'buy')[:10]], c['src'])
            pick(pg, 1, '개인')
            c = pg.evaluate(CARD)
            check(f'family 개인: confirmed ({mdw(F["asOf"])} 확정) + "개인은 장 마감 뒤 저녁에 확정돼요"', c['src'] == 'file' and c['lab'].startswith(mdw(F['asOf']) + ' 확정') and c['note'] == '개인은 장 마감 뒤 저녁에 확정돼요'
                  and [r['c'] for r in c['rows']] == [x[0] for x in file_rank(F, 'K', 'p', 'buy')[:10]], [c['src'], c['lab'], c['note']])
            pick(pg, 1, '외국인')
            tab(pg, 'ALL')
            c = pg.evaluate(CARD)
            w = live_rank(L, 'KQ', 'f', 'buy')
            check('family 전체: rank.K + rank.Q merged and re-sorted', [r['c'] for r in c['rows']] == [x[0] for x in w[:10]] and [r['a'] for r in c['rows']] == [amt(x[1]) for x in w[:10]], [(r['c'], r['a']) for r in c['rows'][:4]])
            pg.click('#flowsCard .fl-more'); pg.wait_for_timeout(800)
            c = pg.evaluate(CARD)
            check('family 전체 더보기: 30 merged rows', [r['c'] for r in c['rows']] == [x[0] for x in w[:30]], len(c['rows']))
            ft = pg.evaluate(FOOT)
            check('family footer: + "종목별 잠정: 한국투자증권 가집계", disclaimer last', ft['flows'] and '종목별 잠정: 한국투자증권 가집계' in ft['flows'] and ft['last'] == '투자 판단의 근거로 쓰지 마세요.', ft['flows'])
            # 기관 has no 잠정 yet (09:30 slot): the confirmed list + a family note
            pg.evaluate("""() => { const L = JSON.parse(JSON.stringify(window.__live)); L.slot = '09:30'; L.slotNo = 1; for (const m of ['K', 'Q']) L.rank[m].i = { buy: [], sell: [] };
              window.__live = L; document.dispatchEvent(new CustomEvent('kh:flowslive')); }""")
            pg.wait_for_timeout(300)
            pick(pg, 1, '기관')
            c = pg.evaluate(CARD)
            check('family, 기관 before its first input: the confirmed list + "기관 잠정은 다음 입력분부터 보여요"', c['src'] == 'file' and '기관 잠정은 다음 입력분부터 보여요' == c['note'], [c['src'], c['note']])
            # a holiday payload (closed:true) → no 잠정 at all
            pg.evaluate("() => { const L = JSON.parse(JSON.stringify(window.__live)); L.closed = true; window.__live = L; document.dispatchEvent(new CustomEvent('kh:flowslive')); }")
            pg.wait_for_timeout(300)
            pick(pg, 1, '외국인')
            c = pg.evaluate(CARD)
            check('family, /api/flows/live closed:true (휴장일): the confirmed list, no 잠정 label or note', c['src'] == 'file' and '잠정' not in c['lab'] and not c['note'], [c['src'], c['lab'], c['note']])
            pg.evaluate("() => { delete window.__live.closed; document.dispatchEvent(new CustomEvent('kh:flowslive')); }")
            pg.wait_for_timeout(300)
            # 가족 보기 off on this device (kh:inv) → public at once
            pg.evaluate("KH.inv.forget()"); pg.wait_for_timeout(400)
            c = pg.evaluate(CARD)
            body = pg.evaluate('document.body.innerText')
            check('KH.inv.forget() (kh:inv): back to public at once — no 잠정 · 한국투자 left, want(card, false)', c['src'] == 'file' and not re.search(r'잠정|한국투자', body) and pg.evaluate('window.__wants')[-1] == ['card', False], pg.evaluate('window.__wants'))
            check('family 1440: console errors 0', not errs, errs[:3])
            if SHOTS:
                pg.evaluate("window.__fam = true; window.__live = %s; document.dispatchEvent(new CustomEvent('kh:inv'))" % json.dumps(L)); pg.wait_for_timeout(400)
                pg.locator('#flowsCard').screenshot(path=str(OUT / 'family_1440.png'))
            ctx.close()

            # family, but flows.json is already today's (after the 21:30 job) → confirmed only
            config(fdate='2026-11-24', now='2026-11-24T21:45:00+09:00', qasof='2026-11-24T15:30:00+09:00', status='CLOSE')
            ctx, pg, errs = open_page(br, 1440, 900, at=when(2026, 11, 24, 21, 45), fam=True, live=L, scroll=True)
            c = pg.evaluate(CARD)
            check('family after the evening file (flows.json asOf = today): 잠정 stops — confirmed "11/24 (화) 확정"', c['src'] == 'file' and c['lab'].startswith('11/24 (화) 확정') and not c['note'], [c['src'], c['lab']])
            st = pg.evaluate("KHFlows.state()")
            check('outside the session: market polled every 10 min even near the viewport', st['near'] and not st['session'] and st['ttl'] == 600000, st['ttl'])
            ctx.close()

            # the template's own KH.inv / KH.flowsLive (no stub): without a token = public, nothing asked
            config()
            ctx, pg, errs = open_page(br, 1280, 800, at=session, stub=False, scroll=True)
            c = pg.evaluate(CARD)
            fs = mock('__fstats')
            check('the template\'s own KH.inv, no token: public card, no /api/inv · /api/flows/live request, console errors 0',
                  c and c['src'] == 'file' and len(c['rows']) == 10 and not any(fs.get(k) for k in ('live', 'live/stock', 'inv')) and not errs, [fs, errs[:2]])
            ctx.close()
            # … with a token (khm.inv): /api/inv/me, then KH.flowsLive polls /api/flows/live once the card wants it → 잠정 on the card
            config()
            ctx, pg, errs = open_page(br, 1440, 900, at=session, stub=False, token=FIX['token'], wait=3000)
            pg.evaluate("document.getElementById('flowsCard').scrollIntoView({block: 'center'})")
            for _ in range(20):
                pg.wait_for_timeout(300)
                if pg.evaluate("document.getElementById('flowsCard').dataset.src") == 'live':
                    break
            c = pg.evaluate(CARD)
            fs = mock('__fstats')
            st = pg.evaluate("KH.flowsLive && KH.flowsLive.status ? KH.flowsLive.status() : null")
            check('the template\'s own KH.inv with a token: KH.flowsLive.want(card) → /api/flows/live → "잠정 · 13:20 입력분" on the card, console errors 0',
                  c['src'] == 'live' and c['lab'].startswith('잠정 · 13:20 입력분') and fs.get('inv', 0) >= 1 and fs.get('live', 0) >= 1 and not errs, [c['src'], c['lab'], fs, st, errs[:2]])
            pg.goto(URL + '#s-005930'); pg.wait_for_timeout(2600)
            pg.click('#sp-t-inv'); pg.wait_for_selector('#sp-p-inv .sp-today'); pg.wait_for_timeout(1200)
            n = pg.evaluate("document.querySelectorAll('#sp-p-inv .sp-est tbody tr').length")
            check('… and the stock page\'s 오늘 잠정 through the real KH.inv.fetch (X-Panse-Inv)', n == 4 and mock('__fstats').get('live/stock', 0) >= 1, n)
            ctx.close()

            # ── 3. market line states ─────────────────────────────────────────────────
            for mode, test in (('stale', lambda c: c['atStale'] and c['at'] and '12:38 기준' in c['at'] and c['mt']),
                               ('fail', lambda c: '시장 전체 수급을 불러오지 못했어요' in c['text'] and not c['mt']),
                               ('gone', lambda c: c['mktHidden'] and len(c['rows']) == 10),
                               ('slow', lambda c: '시장 전체 수급을 받는 중…' in c['text']),
                               ('zero', lambda c: '아직 집계 전이에요' in c['text'] and not c['mt'] and '0억' not in c['text'].split('확정')[0])):
                config(mk=mode)
                ctx, pg, errs = open_page(br, 1280, 800, at=session, scroll=mode != 'slow', wait=1800 if mode == 'slow' else 2600)
                c = pg.evaluate(CARD)
                extra = ''
                if mode == 'stale':
                    col = pg.evaluate("getComputedStyle(document.querySelector('#flowsCard .fl-at svg')).color === getComputedStyle(document.documentElement).getPropertyValue('--fail-dot').trim() || getComputedStyle(document.querySelector('#flowsCard .fl-at svg')).color")
                    extra = col
                    test0 = test(c) and (col is True or 'rgb' in str(col))
                elif mode == 'fail':
                    test0 = test(c) and pg.locator('#flowsCard .fl-fail .kasync').count() == 1 and pg.locator('#flowsCard .fl-fail svg').count() >= 1
                else:
                    test0 = test(c)
                check(f'market line {mode}: ' + {'stale': '! + "12:38 기준" (the last value, --fail-dot)', 'fail': '! + words + 다시 시도', 'gone': '404 (old Worker) → no line, the list stays',
                                                 'slow': '"받는 중…" while it comes', 'zero': 'all 0 before the open → "아직 집계 전" (not 0억)'}[mode] + ', console errors 0', test0 and not [e for e in errs if '503' not in e and '404' not in e], [c['at'], c['text'][:120], extra, errs[:2]])
                if mode == 'fail':
                    config(mk='ok')
                    pg.click('#flowsCard .fl-fail .kasync'); pg.wait_for_timeout(1800)
                    c = pg.evaluate(CARD)
                    check('다시 시도 → the market line comes in', c['mt'] and c['at'] == '13:05 기준', [c['mt'], c['at']])
                ctx.close()
            config(fdate='none')
            ctx, pg, errs = open_page(br, 1280, 800, at=session, scroll=True)
            c = pg.evaluate(CARD)
            check('flows.json missing: "종목별 수급 자료를 불러오지 못했어요" (! + words), no 더보기', '종목별 수급 자료를 불러오지 못했어요' in c['text'] and not c['rows'] and c['more'] is None, c['text'][-80:])
            ctx.close()

            # ── 4. map top unchanged + 4 themes × 360 · 1280 overflow 0 (public + family) ──
            config()
            for (w, h, top) in ((390, 844, 247), (1280, 800, 207), (1440, 900, 207)):
                ctx, pg, errs = open_page(br, w, h, at=session)
                y = pg.evaluate("Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY)")
                order = pg.evaluate("[...document.querySelector('main.layout > .side').children].map(x => x.id || x.className)")
                check(f'{w}×{h}: map top {top} (unchanged), the card right after #moverCard in the side column', y == top and order.index('flowsCard') == order.index('moverCard') + 1, [y, order])
                ctx.close()
            for theme in ('base', 'paper', 'glass-dark', 'glass-light'):
                for (w, h) in ((360, 780), (1280, 800)):
                    for fam in (False, True):
                        ctx, pg, errs = open_page(br, w, h, at=session, theme=theme, fam=fam, live=L if fam else None, scroll=True, wait=2200)
                        if fam:
                            pg.click('#flowsCard .fl-more'); pg.wait_for_timeout(700)
                        bad = overflow(pg)
                        nul = pg.evaluate("/null|undefined|NaN/.test(document.getElementById('flowsCard').innerText)")
                        check(f'{theme} {w} {"family" if fam else "public"}: overflow 0, no null/undefined/NaN, console errors 0', not bad and not nul and not errs, [bad, nul, errs[:2]])
                        if SHOTS and w == 360:
                            pg.locator('#flowsCard').screenshot(path=str(OUT / f'{theme}_{w}_{"fam" if fam else "pub"}.png'))
                        ctx.close()
            # phone: the controls fit; 768 tablet column (two-line controls allowed)
            for (w, h) in ((390, 844), (768, 1024)):
                ctx, pg, errs = open_page(br, w, h, at=session, scroll=True)
                bad = overflow(pg)
                hs = pg.evaluate("""() => { const H = s => [...document.querySelectorAll(s)].map(b => Math.round(b.getBoundingClientRect().height));
                  return { mvTab: H('#moverTabs button'), mvRow: H('#movers > button').slice(0, 1), tab: H('#flowsCard .fl-ctl button'), row: H('#flowsCard .fl-r') }; }""")
                ok = all(x == hs['mvTab'][0] for x in hs['tab']) and all(x >= hs['mvRow'][0] for x in hs['row']) and (w > 760 or min(hs['row'] + hs['tab']) >= 40)
                check(f'{w}: overflow 0, segment keys = the 눈에 띄는 종목 tabs, rows ≥ its rows' + (' (≥ 40px on a phone)' if w <= 760 else '') + ', console errors 0',
                      not bad and ok and not errs, [bad, {k: v[:3] for k, v in hs.items()}, errs[:2]])
                if SHOTS:
                    pg.locator('#flowsCard').screenshot(path=str(OUT / f'public_{w}.png'))
                ctx.close()

            # ── 5. summary: close.json date (§3-34 고칠 것 ①) ───────────────────────────
            K = [x for x in FIX['flows']['f'] if MKT.get(x) == 'K' and x.endswith('0')]
            top = [r for r in json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))['stocks'] if r['m'] == 'K' and r['c'].endswith('0')]
            top.sort(key=lambda r: -r.get('cap', 0))
            old, new = top[3]['c'], top[7]['c']          # "Friday's" 상한가 (close.json) vs today's (/api/breadth)
            after = when(2026, 11, 24, 17, 0)
            M = "(() => { const M = KHSummary.model(); return { ph: M.ph, src: M.br && M.br.src, lim: M.br && M.br.limUp, when: M.when, old: M.brOld || null, mf: M.mflows || null, fl: M.flows ? { date: M.flows.date } : null }; })()"
            config(now='2026-11-24T17:00:00+09:00', qasof='2026-11-24T15:30:00+09:00', status='CLOSE', cdate='2026-11-23', clim=old, blim=new, fdate='2026-11-23')
            for q in ('', '?summary_phase=after'):
                ctx, pg, errs = open_page(br, 1440, 900, at=after, query=q, wait=3200)
                m = pg.evaluate(M)
                pg.click('#summary .sm-tog'); pg.wait_for_timeout(1000)
                t = pg.evaluate("document.getElementById('summary').innerText")
                nm_old, nm_new = NAMES[old][0], NAMES[new][0]
                check(f'summary after{q and " (" + q + ")"} + close.json of 11/23: computed like the session (/api/breadth) — today\'s 상한가 {nm_new}, not 11/23\'s {nm_old}',
                      m['ph'] == 'after' and m['src'] == 'breadth' and m['lim'] == [new] and nm_new in t and nm_old not in t and not errs, [m['ph'], m['src'], m['lim'], errs[:2]])
                ctx.close()
            config(now='2026-11-24T17:00:00+09:00', qasof='2026-11-24T15:30:00+09:00', status='CLOSE', cdate='2026-11-24', clim=old, blim=new, fdate='2026-11-23')
            ctx, pg, errs = open_page(br, 1440, 900, at=after, wait=3200)
            m = pg.evaluate(M)
            check('summary after + today\'s close.json: the file as before (its 상한가)', m['src'] == 'close' and m['lim'] == [old] and not m['old'], [m['src'], m['lim']])
            ctx.close()
            config(now='2026-11-25T08:30:00+09:00', qasof='2026-11-24T15:30:00+09:00', status='CLOSE', cdate='2026-11-23', clim=old, blim=new, fdate='2026-11-23')
            ctx, pg, errs = open_page(br, 1440, 900, at=when(2026, 11, 25, 8, 30), wait=3200)
            m = pg.evaluate(M)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(1000)
            t = pg.evaluate("document.getElementById('summary').innerText")
            band = None
            check('summary pre + a late close.json (11/23, the latest weekday is 11/24): the file kept, its date in the head and lines',
                  m['ph'] == 'pre' and m['src'] == 'close' and m['old'] == '2026-11-23' and '종목 등락은 11월 23일 (월) 종가' in m['when'] and '11/23 상한가' in t and re.search(r'오른 · 내린 종목\s*11/23', t) is not None and not errs,
                  [m['ph'], m['src'], m['old'], m['when'], errs[:2]])
            ctx.close()
            config(now='2026-11-25T08:30:00+09:00', qasof='2026-11-24T15:30:00+09:00', status='CLOSE', cdate='2026-11-24', fdate='2026-11-24')
            ctx, pg, errs = open_page(br, 390, 844, at=when(2026, 11, 25, 8, 30), wait=3200)
            m = pg.evaluate(M)
            check('summary pre + the previous weekday\'s close.json: the file, no date note', m['src'] == 'close' and not m['old'] and '종목 등락은' not in m['when'], [m['src'], m['old'], m['when']])
            ctx.close()

            # ── 6. summary 수급 line intraday ───────────────────────────────────────────
            config()
            ctx, pg, errs = open_page(br, 1440, 900, at=session, wait=3200)
            m = pg.evaluate(M)
            want3 = [MK['K'][k] + MK['Q'][k] for k in ('foreign', 'institutional', 'personal')]
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(1000)
            t = pg.evaluate("document.getElementById('summary').innerText")
            plain = pg.evaluate("KHSummary.plain(KHSummary.model())")
            check('summary in the session: 외국인 · 기관 · 개인 = /api/flows/market (코스피 + 코스닥), "13:05 기준"',
                  m['mf'] and [round(x, 1) for x in m['mf']['all']] == want3 and m['mf']['at'] == '13:05' and re.search(r'외국인 · 기관\s*13:05 기준', t) is not None
                  and all(amt(v) in t for v in want3) and '시장 전체 · 13:05 기준' in t, [m['mf'], t[t.find('수급'):t.find('수급') + 160] if '수급' in t else t[:120]])
            check('summary: the per-stock lines stay on the file with its date ("외국인 순매수 1위 (11/23)" · "종목은 11/23 확정")', '외국인 순매수 1위 (11/23)' in t and '종목은 11/23 확정' in t, t[t.find('외국인 순매'):t.find('외국인 순매') + 80])
            check('summary 글로 복사: 수급(13:05 기준) from the market line', any(l.startswith('수급(13:05 기준): 외국인 ' + amt(want3[0])) for l in plain.split('\n')), [l for l in plain.split('\n') if l.startswith('수급')])
            fs = mock('__fstats')
            check('the card and the summary share one /api/flows/market (KHFlows.market) — ≤ 2 requests on a page load', 1 <= fs.get('market', 0) <= 2 and not errs, [fs, errs[:2]])
            ctx.close()
            config(mk='gone')
            ctx, pg, errs = open_page(br, 1440, 900, at=session, wait=3200)
            m = pg.evaluate(M)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(1000)
            t = pg.evaluate("document.getElementById('summary').innerText")
            check('summary with an old Worker (404): the 수급 line from the file with its date, console clean', not m['mf'] and m['fl'] and re.search(r'외국인 · 기관\s*11/23', t) is not None
                  and '11/23 · 코스피 · 코스닥 합' in t and not [e for e in errs if '404' not in e], [m['mf'], errs[:2]])
            ctx.close()

            config(mk='zero')
            ctx, pg, errs = open_page(br, 1440, 900, at=when(2026, 11, 24, 8, 45), wait=3200)
            m = pg.evaluate(M)
            check('summary before the open (/api/flows/market all 0 with today\'s date): not used — the file\'s line', not m['mf'] and m['fl'] and not errs, [m['mf'], errs[:2]])
            ctx.close()

            # ── 7. stock page: 오늘 잠정 (family only) ───────────────────────────────────
            EST = """() => { const e = document.querySelector('#sp-p-inv .sp-est'); if (!e) return null;
              return { prev: e.previousElementSibling && e.previousElementSibling.className, h: e.querySelector('h3').textContent, src: e.querySelector('.sp-cum-h small').textContent,
                rows: [...e.querySelectorAll('tbody tr')].map(tr => [...tr.children].map(x => [x.textContent, x.className])), text: e.innerText }; }"""
            for (w, h) in ((1440, 900), (390, 844)):
                config()
                ctx, pg, errs = open_page(br, w, h, at=session, fam=True, live=L, query='#s-005930', wait=2600)
                pg.click('#sp-t-inv'); pg.wait_for_selector('#sp-p-inv .sp-today'); pg.wait_for_timeout(900)
                e = pg.evaluate(EST)
                ok = e and e['prev'] == 'sp-today' and e['h'] == '오늘 잠정' and e['src'] == '한국투자증권 가집계' and [r[0][0] for r in e['rows']] == ['09:30', '10:00', '11:20', '13:20']
                ok = ok and e['rows'][0][2][0] == '—' and 'dn' in e['rows'][0][1][1] and 'up' in e['rows'][3][1][1] and 'up' in e['rows'][1][2][1] and 'dn' in e['rows'][3][2][1]
                ok = ok and ('−564,000주' in e['rows'][0][1][0] or '−56.4만주' in e['rows'][0][1][0])
                check(f'stock {w} family: "오늘 잠정 · 한국투자증권 가집계" right under the 오늘 card, one row per round, 외국인 · 기관 shares in sign colours, 09:30 기관 —',
                      ok and not errs, [e and e['rows'][:2], errs[:2]])
                if SHOTS:
                    pg.locator('#sp-p-inv .sp-est').screenshot(path=str(OUT / f'stock_est_{w}.png'))
                ctx.close()
            config()
            ctx, pg, errs = open_page(br, 1440, 900, at=session, query='#s-005930', wait=2600)
            pg.click('#sp-t-inv'); pg.wait_for_selector('#sp-p-inv .sp-today'); pg.wait_for_timeout(900)
            fs = mock('__fstats')
            first = pg.evaluate("document.querySelector('#sp-p-inv > *').className")
            check('stock public: no 잠정 block, no request, the 오늘 card still first', pg.evaluate(EST) is None and not fs.get('live/stock') and first == 'sp-today'
                  and '잠정' not in pg.evaluate("document.getElementById('sp-p-inv').innerText") and not errs, [fs, first, errs[:2]])
            ctx.close()
            for mode, want_txt in (('gone', None), ('closed', None), ('empty', '아직 입력분이 없어요'), ('stale', '새 회차를 받지 못했어요'), ('none', '잠정 회차를 불러오지 못했어요'), ('fail', '잠정 회차를 불러오지 못했어요')):
                config(est=mode)
                ctx, pg, errs = open_page(br, 1440, 900, at=session, fam=True, live=L, query='#s-005930', wait=2600)
                pg.click('#sp-t-inv'); pg.wait_for_selector('#sp-p-inv .sp-today'); pg.wait_for_timeout(900)
                e = pg.evaluate(EST)
                ok = e is None if want_txt is None else (e is not None and want_txt in e['text'])
                if mode in ('fail', 'none'):
                    ok = ok and pg.locator('#sp-p-inv .sp-est .kasync').count() == 1
                if mode == 'stale':
                    ok = ok and len(e['rows']) == 4
                say = {'gone': '404 (old Worker) → no block', 'closed': 'closed:true (휴장일) → no block', 'none': '503 (no copy) → "잠정 회차를 불러오지 못했어요" + 다시 시도',
                       'stale': 'stale:true → the rounds + ! "새 회차를 받지 못했어요"'}.get(mode, f'"{want_txt}"' + (' + 다시 시도' if mode == 'fail' else ''))
                check(f'stock family est={mode}: ' + say, ok and not [x for x in errs if '404' not in x and '502' not in x and '503' not in x], [e and e['text'][:80], errs[:2]])
                if mode == 'fail':
                    config(est='ok')
                    pg.click('#sp-p-inv .sp-est .kasync'); pg.wait_for_timeout(2200)
                    e = pg.evaluate(EST)
                    check('stock 잠정 다시 시도 → the rounds come in', e is not None and len(e['rows']) == 4, e and e['text'][:80])
                ctx.close()

            # ── 8. snapshot (dist/, file://) ─────────────────────────────────────────────
            for (w, h) in ((390, 844), (1440, 900)):
                ctx, pg, errs = open_page(br, w, h, at=None, url=(ROOT / 'dist/index.html').as_uri(), scroll=True, wait=2200)
                c = pg.evaluate(CARD)
                snapF = pg.evaluate("(() => { const s = document.getElementById('kh-data-flows'); return s ? JSON.parse(s.textContent).asOf : null; })()")
                check(f'snapshot {w}: the card from the built-in flows.json ({snapF and mdw(snapF)} 확정, 10 rows), the market line → 실시간 버전, no 잠정, console errors 0',
                      c and len(c['rows']) == 10 and c['lab'].startswith(mdw(snapF) + ' 확정') and '실시간 버전' in c['text'] and '잠정' not in c['text'] and not errs, [c and c['lab'], errs[:2]])
                ctx.close()
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f"\n{counts['pass']} passed, {len(fails)} failed" + (': ' + ', '.join(fails) if fails else ''))
    sys.exit(1 if fails else 0)


main()
