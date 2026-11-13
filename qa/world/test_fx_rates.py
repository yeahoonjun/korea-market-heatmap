#!/usr/bin/env python3
"""QA for the 지표 tab's 환율 · 금리 groups (AGENTS.md §3-28) — Worker + src/world UI.

  python3 scripts/build_page.py && python3 qa/world/test_fx_rates.py [--no-real]

1. Worker (default; --no-real skips): starts the local Worker (worker/dev/serve.mjs, live Naver upstream through the proxy) on
   FX_WORKER_PORT (8842) and checks /api/world?kind=commodity&with=fx,rates: groups, plausible values, bp = change × 100,
   the 달러/엔 cross, validation (400s), the chart route for an FX item and a bond, and that plain kind=commodity is unchanged.
2. UI against qa/world/mock_api.py on FX_QA_PORT (8843) with /__mode?macro=on (fixtures/world_macro.json, recorded from 1.):
   tab label 지표, block captions, notes, % / bp formatting, colours, sheet + chart for an FX item and a bond, keyboard,
   등락률순, an older Worker (macro=off), the 레피니티브-close fallback for 달러/엔 (macro=eod), all four themes at 390 and 1280,
   the snapshot page.
   Screenshots: /tmp/fx_<theme>_<width>.png, /tmp/fx_sheet_<fx|bond>_<width>.png, /tmp/fx_pct_1280.png.
Exit code 1 if any check fails.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('FX_QA_PORT', 8843))
WPORT = int(os.environ.get('FX_WORKER_PORT', 8842))
LIVE = f'http://127.0.0.1:{PORT}/'
WORKER = f'http://127.0.0.1:{WPORT}'
SNAP = (ROOT / 'dist/index.html').as_uri()
MACRO = json.loads((HERE / 'fixtures/world_macro.json').read_text(encoding='utf-8'))
CMDTY = json.loads((HERE / 'fixtures/world_commodity.json').read_text(encoding='utf-8'))
ITEMS = {it['key']: dict(it, gkey=g['key']) for g in CMDTY['groups'] + MACRO['groups'] for it in g['items']}
N_CM = sum(len(g['items']) for g in CMDTY['groups'])
N_ALL = len(ITEMS)
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TAB = '지표'

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def get(url, timeout=60):
    try:
        with NOPROXY.open(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def bp_text(v):
    r = round(v * 10) / 10
    s = '+' if r > 0 else '−' if r < 0 else ''
    return f'{s}{abs(r):.1f}bp'


def pct_text(v):
    s = '+' if v > 0 else '−' if v < 0 else ''
    return f'{s}{abs(v):.2f}%'


# ───────── 1. Worker ─────────
def worker_pass():
    proc = None
    try:
        status, _ = get(WORKER + '/api/health', 2)
    except Exception:
        status = 0
    if status != 200:
        env = dict(os.environ, NODE_USE_ENV_PROXY='1', ASSET_BASE=LIVE, PORT=str(WPORT))
        proc = subprocess.Popen(['node', str(ROOT / 'worker/dev/serve.mjs')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                if get(WORKER + '/api/health', 2)[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
    try:
        st, j = get(WORKER + '/api/world?kind=commodity&with=fx,rates')
        keys = [g['key'] for g in j.get('groups', [])]
        check('worker: with=fx,rates → 에너지 · 금속 · 농산물 then 환율 · 금리', st == 200 and keys == ['energy', 'metals', 'agri', 'fx', 'rates'], f'{st} {keys}')
        g = {x['key']: x for x in j.get('groups', [])}
        fx = {it['key']: it for it in g.get('fx', {}).get('items', [])}
        rt = {it['key']: it for it in g.get('rates', {}).get('items', [])}
        want_fx = ['FX_USDKRW', 'FX_JPYKRW', 'FX_EURKRW', 'FX_CNYKRW', 'DXY', 'USDJPY']
        want_rt = ['KR1YT', 'KR3YT', 'KR10YT', 'US2YT', 'US10YT', 'US30YT', 'JP10YT']
        check('worker: 환율 = 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 · 달러인덱스 · 달러/엔', list(fx) == want_fx, str([(k, v['name']) for k, v in fx.items()]))
        check('worker: 금리 = 국고채 1·3·10년, 미국 2·10·30년, 일본 10년', list(rt) == want_rt, str([(k, v['name']) for k, v in rt.items()]))
        rng = {'FX_USDKRW': (900, 2500), 'FX_JPYKRW': (500, 1500), 'FX_EURKRW': (1000, 2600), 'FX_CNYKRW': (100, 400), 'DXY': (70, 130), 'USDJPY': (80, 250)}
        bad = [f"{k} {fx[k]['value']}" for k, (lo, hi) in rng.items() if k in fx and not lo <= fx[k]['value'] <= hi]
        check('worker: FX values plausible (원/달러 in the 1,000s, 원/엔 per 100엔, DXY ~100, 달러/엔 ~150)', not bad and len(fx) == 6,
              '; '.join(bad) or ', '.join(f"{k} {v['value']}" for k, v in fx.items()))
        if 'USDJPY' in fx and 'FX_USDKRW' in fx and 'FX_JPYKRW' in fx:
            cross = fx['FX_USDKRW']['value'] / (fx['FX_JPYKRW']['value'] / 100)
            u = fx['USDJPY']
            check('worker: 달러/엔 = 원/달러 ÷ (원/엔 ÷ 100) of the same round, calc, 하나은행 고시로 계산',
                  u.get('calc') is True and not u.get('eod') and abs(u['value'] - round(cross, 2)) < 0.006 and u.get('via') == '하나은행 고시로 계산'
                  and u.get('unit') == 'JPY' and u['status'] == ('OPEN' if fx['FX_USDKRW']['status'] == 'OPEN' and fx['FX_JPYKRW']['status'] == 'OPEN' else 'CLOSE'),
                  f"{u['value']} vs {cross:.4f}, {u['status']}, {u.get('via')}")
            pu, pj = fx['FX_USDKRW']['value'] - fx['FX_USDKRW']['change'], fx['FX_JPYKRW']['value'] - fx['FX_JPYKRW']['change']
            prev = pu / (pj / 100)
            check('worker: 달러/엔 change = cross − the previous rates\' cross', abs(u['change'] - round(cross - prev, 2)) < 0.011 and abs(u['ratio'] - round((cross / prev - 1) * 100, 2)) < 0.011,
                  f"{u['change']} / {u['ratio']}% vs {cross - prev:.3f} / {(cross / prev - 1) * 100:.3f}%")
        rr = {'KR': (0.5, 8), 'US': (0.5, 10), 'JP': (-1, 5)}
        bad = [f"{k} {v['value']}" for k, v in rt.items() if not rr[k[:2]][0] <= v['value'] <= rr[k[:2]][1]]
        check('worker: yields plausible (%), unit %', not bad and all(v.get('unit') == '%' for v in rt.values()) and len(rt) == 7, '; '.join(bad) or ', '.join(f"{k} {v['value']}" for k, v in rt.items()))
        bad = [f"{k} bp {v.get('bp')} change {v['change']}" for k, v in rt.items() if v.get('bp') is None or abs(v['bp'] - round(v['change'] * 100, 2)) > 1e-9 or abs(v['bp']) > 100]
        check('worker: bp = change (%p) × 100, |bp| < 100', not bad, '; '.join(bad) or ', '.join(f"{k} {v['bp']:+}bp" for k, v in rt.items()))
        bad = [k for k, v in {**fx, **rt}.items() if v['change'] and v['ratio'] and (v['change'] > 0) != (v['ratio'] > 0)]
        check('worker: change and ratio agree in sign', not bad, ', '.join(bad))
        bad = [k for k, v in {**fx, **rt}.items() if v['status'] not in ('OPEN', 'CLOSE') or not v.get('tradedAt')]
        check('worker: status OPEN/CLOSE and tradedAt on every item', not bad, ', '.join(bad))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        stale = [f"{k} {v['tradedAt']}" for k, v in rt.items() if v['status'] == 'OPEN' and (now - datetime.fromisoformat(v['tradedAt'])).total_seconds() > (v.get('delayed', 0) + 120) * 60]
        check('worker: a bond quote > delay + 2 h old is not "OPEN" (Naver leaves Korean bonds OPEN overnight)', not stale, '; '.join(stale) or ', '.join(f"{k} {v['status']}" for k, v in rt.items()))
        check('worker: bonds carry a time zone, JP10Y its delay', all(v.get('tz') for v in rt.values()) and rt.get('JP10YT', {}).get('delayed', 0) > 0,
              ', '.join(f"{k} {v.get('tz')} {v.get('delayed', 0)}" for k, v in rt.items()))
        st2, j2 = get(WORKER + '/api/world?kind=commodity')
        check('worker: plain kind=commodity unchanged (3 groups, the ticker reads it)', st2 == 200 and [x['key'] for x in j2['groups']] == ['energy', 'metals', 'agri'])
        st3, j3 = get(WORKER + '/api/world?kind=commodity&with=rates')
        check('worker: with=rates alone → only 금리 added', st3 == 200 and [x['key'] for x in j3['groups']][-1] == 'rates' and 'fx' not in [x['key'] for x in j3['groups']])
        bad = []
        for q in ('kind=index&with=fx', 'kind=commodity&with=fx,nope', 'kind=commodity&with='):
            s, b = get(WORKER + '/api/world?' + q)
            if s != 400 or 'error' not in b:
                bad.append(f'{q} → {s} {b}')
        check('worker: bad `with` → 400 {error}', not bad, '; '.join(bad))
        for key, tf, lo, hi, n in (('FX_USDKRW', '3m', 900, 2500, 40), ('KR3YT', '1y', 0.5, 8, 150), ('USDJPY', '3m', 80, 250, 40), ('DXY', '3m', 70, 130, 40), ('US10YT', '3m', 0.5, 10, 40)):
            s, b = get(f'{WORKER}/api/world/chart/{key}?tf={tf}')
            bars = b.get('bars') or []
            ok = s == 200 and len(bars) >= n and all(lo <= x['c'] <= hi for x in bars) and all(re.match(r'^\d{4}-\d{2}-\d{2}$', x['t']) for x in bars) \
                and [x['t'] for x in bars] == sorted(set(x['t'] for x in bars))
            check(f'worker: chart {key} {tf} — daily closes, sorted, plausible', ok, f"{s} {len(bars)} bars {bars[0] if bars else ''} … {bars[-1] if bars else ''}")
        s, b = get(WORKER + '/api/world/chart/KR3YT?tf=1d')
        check('worker: chart tf=1d still 400 for these', s == 400)
        fallback_pass()
    finally:
        if proc:
            proc.terminate()


FALLBACK_MJS = r'''
const w = (await import(process.argv[1])).default;
const real = globalThis.fetch;
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
globalThis.fetch = (u, o) => /marketindex\/exchange$/.test(String(u)) ? Promise.resolve(new Response('down', { status: 503 })) : real(u, o);
const r = await w.fetch(new Request('http://x/api/world?kind=commodity&with=fx'), {}, { waitUntil() {} });
console.log(JSON.stringify(await r.json()));
'''


def fallback_pass():
    """the cross cannot be had (the exchange list is down) → 달러/엔 = exchangeWorld/USDJPY, the 레피니티브 daily close (eod)"""
    env = dict(os.environ, NODE_USE_ENV_PROXY='1')
    r = subprocess.run(['node', '--input-type=module', '-e', FALLBACK_MJS, str(ROOT / 'worker/src/index.js')], env=env, capture_output=True, text=True, timeout=90)
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1])
        fx = next(g for g in j['groups'] if g['key'] == 'fx')['items']
    except Exception as e:
        check('worker fallback: exchange list down → 달러/엔 from the 레피니티브 close', False, f'{e}: {r.stdout[-200:]} {r.stderr[-200:]}')
        return
    u = fx[0] if len(fx) == 1 else None
    check('worker fallback: exchange list down → only 달러/엔, the 레피니티브 close (eod, not calc)', u and u['key'] == 'USDJPY' and u.get('eod') is True
          and not u.get('calc') and u.get('via') == '레피니티브' and 80 <= u['value'] <= 250, json.dumps(fx, ensure_ascii=False)[:240])


# ───────── 2. UI ─────────
class Errors:
    def __init__(self):
        self.items, self.http = [], []

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))
        # a 4xx/5xx on the routes this feature owns is an error; other modules' unmocked routes are not this test's business
        page.on('response', lambda r: self.http.append(f'{r.status} {r.url}') if r.status >= 400 and '/api/world' in r.url else None)


ERR = Errors()


def mode(**kw):
    get(LIVE + '__mode?' + '&'.join(f'{k}={v}' for k, v in kw.items()), 5)


def open_page(browser, url, width, height, theme='base', sort=None, reduced=False):
    mobile = width < 700
    opts = dict(viewport={'width': width, 'height': height}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if reduced:
        opts['reduced_motion'] = 'reduce'
    ctx = browser.new_context(**opts)
    pre = {'khm.theme': theme}
    if sort:
        pre['khm.worldSort'] = sort
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__fxPre')) return; sessionStorage.setItem('__fxPre', '1'); "
                        + ''.join(f'localStorage.setItem({json.dumps(k)}, {json.dumps(v)});' for k, v in pre.items()) + '})();')
    page = ctx.new_page()
    ERR.attach(page)
    page.goto(url)
    return ctx, page


def wait_list(page, n=None):
    page.wait_for_selector('#world .kw-lr', timeout=10000)
    if n:
        page.wait_for_function(f"document.querySelectorAll('#world .kw-lr').length >= {n}", timeout=10000)
    page.wait_for_timeout(350)


ROWS_JS = r"""
(items) => {
  const norm = c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
  const sgn = v => v > 0 ? '+' : v < 0 ? '−' : '';
  const pct = v => sgn(v) + Math.abs(v).toFixed(2) + '%';
  const bpt = v => { const r = Math.round(v * 10) / 10; return sgn(r) + Math.abs(r).toFixed(1) + 'bp'; };
  const num = t => +t.replace(/[,+%]/g, '').replace('−', '-');
  const out = { n: 0, bad: [], clip: [], seen: [] };
  const vw = document.documentElement.clientWidth;
  for (const r of document.querySelectorAll('#world .kw-lr')) {
    const it = items[r.dataset.k]; if (!it) { out.bad.push('unknown ' + r.dataset.k); continue; }
    out.n++; out.seen.push(it.key);
    const lv = r.querySelector('.kw-lv'), lc = r.querySelector('.kw-lc'), chip = r.querySelector('.kw-pchip');
    if (it.gkey === 'rates') {
      if (!/^\d+\.\d{3}%$/.test(lv.textContent) || Math.abs(num(lv.textContent) - it.value) > 0.0006) out.bad.push(`${it.key} value ${lv.textContent} vs ${it.value}`);
      if (chip.textContent !== bpt(it.bp)) out.bad.push(`${it.key} chip ${chip.textContent} != ${bpt(it.bp)}`);
      if (lc.textContent !== '') out.bad.push(`${it.key} change column '${lc.textContent}' should be empty`);
    } else {
      if (Math.abs(num(lv.textContent) - it.value) > 1e-6 * Math.max(1, Math.abs(it.value))) out.bad.push(`${it.key} value ${lv.textContent} vs ${it.value}`);
      if (chip.textContent !== pct(it.ratio)) out.bad.push(`${it.key} chip ${chip.textContent} != ${pct(it.ratio)}`);
      if (Math.abs(num(lc.textContent) - it.change) > 1e-6 * Math.max(1, Math.abs(it.change))) out.bad.push(`${it.key} change ${lc.textContent} vs ${it.change}`);
    }
    // colour = the number going up / down (KH.colorOf of the day's change; for a yield that change has the bp's sign)
    if (getComputedStyle(chip).backgroundColor !== norm(KH.colorOf(it.ratio))) out.bad.push(`${it.key} chip colour`);
    const rr = r.getBoundingClientRect();
    for (const el of [chip, lv, lc]) {
      const b = el.getBoundingClientRect();
      if (el.textContent && (el.scrollWidth > el.clientWidth + 1 || b.right > rr.right + 0.5 || b.left < rr.left - 0.5 || b.right > vw)) out.clip.push(`${it.key} ${el.className} ${el.textContent}`);
    }
    const nm = r.querySelector('.kw-ln .nm');
    if (nm.scrollWidth > nm.clientWidth + 1) out.clip.push(`${it.key} name cut '${nm.textContent}'`);
  }
  return out;
}"""

LAYOUT_JS = r"""
() => {
  const L = document.querySelector('#world .kw-list');
  const kids = [...L.children].map(e => e.classList.contains('kw-bt') ? 'cap:' + e.textContent : e.classList.contains('kw-col') ? 'col:' + [...e.querySelectorAll('.kw-sec')].map(s => s.dataset.g).join('+') : e.className);
  const secs = [...L.querySelectorAll('.kw-sec')].map(s => s.dataset.g);
  const head = g => { const s = L.querySelector(`.kw-sec[data-g="${g}"] .kw-sh`); return s ? { t: s.querySelector('.t').textContent, s: s.querySelector('.s').textContent, a: s.querySelector('.a').textContent, tag: s.tagName,
    noteVisible: (() => { const n = s.querySelector('.a small'); if (!n) return false; const r = n.getBoundingClientRect(); return r.width > 20 && n.scrollWidth <= n.clientWidth + 1; })() } : null; };
  const sub = k => { const r = L.querySelector(`.kw-lr[data-k="${k}"]`); if (!r) return null; const a = r.querySelector('.kw-ln .sub'), b = r.querySelector('.kw-ls .sub2');
    const vis = el => el && el.textContent && getComputedStyle(el).display !== 'none' && !el.hidden && el.getBoundingClientRect().width > 4 && el.scrollWidth <= el.clientWidth + 1;
    return { text: a.textContent, shown: vis(a) || vis(b), tag: a.classList.contains('tag') }; };
  const txt = document.getElementById('world').innerText;
  const tabBtn = document.querySelector('.tabs button[data-mkt="CMDTY"]');
  return {
    kids, secs, fx: head('fx'), rates: head('rates'), energy: head('energy'),
    dxy: sub('DXY'), usdjpy: sub('USDJPY'), krw: sub('FX_USDKRW'),
    usdjpySt: (L.querySelector('.kw-lr[data-k="USDJPY"] .kw-ls .st') || {}).textContent,
    title: document.querySelector('#world .kw-title').textContent, sum: document.querySelector('#world .kw-sum').textContent,
    rankSub: (document.querySelector('#world .kw-rank-sub') || {}).textContent, rankKeys: [...document.querySelectorAll('#world .kw-row')].map(b => b.dataset.k),
    tab: tabBtn.textContent, tabAria: tabBtn.getAttribute('aria-label'),
    bad: (txt.match(/\b(null|NaN|undefined|Infinity)\b/g) || []),
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    src: document.querySelector('#world .kw-src').textContent,
    colsTop: [...L.querySelectorAll('.kw-col')].map(c => [c.dataset.b, Math.round(c.getBoundingClientRect().left)]),
  };
}"""


def ui_tab_pass(browser, theme, width, height):
    tag = f'{theme} {width}'
    ctx, page = open_page(browser, LIVE + '#cmdty', width, height, theme)
    try:
        wait_list(page, N_ALL)
        lay = page.evaluate(LAYOUT_JS)
        check(f'{tag}: tab is "{TAB}" (one constant), aria names 원자재 · 환율 · 금리, stage title {TAB}',
              lay['tab'] == TAB and lay['tabAria'].startswith(TAB) and '환율' in lay['tabAria'] and lay['title'] == TAB, f"{lay['tab']} / {lay['tabAria']} / {lay['title']}")
        check(f'{tag}: order 환율 → 금리 → 원자재 (에너지 · 금속 · 농산물), two captioned blocks (user 2026-11-14 02:11)',
              lay['secs'] == ['fx', 'rates', 'energy', 'metals', 'agri'] and [k for k in lay['kids'] if k.startswith('cap:')] == ['cap:환율 · 금리', 'cap:원자재']
              and lay['kids'][0] == 'cap:환율 · 금리', ' | '.join(lay['kids']))
        fxh, rh = lay['fx'], lay['rates']
        check(f'{tag}: 환율 head note "오르면 원화 약세", 금리 head says bp, both visible, no average', fxh and fxh['a'] == '오르면 원화 약세' and rh and 'bp' in rh['a']
              and fxh['noteVisible'] and rh['noteVisible'] and '%' not in fxh['a'], f'{fxh} {rh}')
        check(f'{tag}: section heads one level under the captions (h4)', fxh and fxh['tag'] == 'H4' and lay['energy']['tag'] == 'H4')
        check(f'{tag}: 달러인덱스 "오르면 달러 강세", 달러/엔 "오르면 엔화 약세" shown on the rows', lay['dxy'] and lay['dxy']['text'] == '오르면 달러 강세' and lay['dxy']['shown']
              and lay['usdjpy'] and lay['usdjpy']['text'] == '오르면 엔화 약세' and lay['usdjpy']['shown'], f"{lay['dxy']} {lay['usdjpy']}")
        rows = page.evaluate(ROWS_JS, ITEMS)
        check(f'{tag}: every row = API (FX %, yields x.xxx% + bp chip, empty change column), colour = KH.colorOf',
              rows['n'] == N_ALL and not rows['bad'], '; '.join(rows['bad'][:4]) or f"{rows['n']} rows")
        check(f'{tag}: nothing clipped (names, values, chips)', not rows['clip'], '; '.join(rows['clip'][:4]))
        check(f'{tag}: no null / NaN / undefined text', not lay['bad'], str(lay['bad'][:4]))
        check(f'{tag}: no horizontal overflow', lay['over'] <= 0, f"{lay['over']}px")
        check(f'{tag}: summary + 많이 오른·내린 = 원자재 only, labelled', lay['sum'].startswith('원자재') and lay['rankSub'] == f'원자재 {N_CM}개 중'
              and lay['rankKeys'] and not any(ITEMS[k]['gkey'] in ('fx', 'rates') for k in lay['rankKeys'] if k in ITEMS), f"{lay['sum']} / {lay['rankSub']}")
        check(f'{tag}: source names 하나은행 고시 · 레피니티브 · 달러/엔 계산값', '하나은행 고시' in lay['src'] and '레피니티브' in lay['src'] and '달러/엔은 원/달러와 원/엔으로 계산한' in lay['src'], lay['src'][-160:])
        check(f'{tag}: 달러/엔 state column says 계산값', lay['usdjpySt'] == '계산값', str(lay['usdjpySt']))
        if width >= 1280:
            cm = [x for x in lay['colsTop'] if x[0] == 'cm']
            mx = [x for x in lay['colsTop'] if x[0] == 'mx']
            check(f'{tag}: desktop uses columns (원자재 as before: 2 at 1280, 3 at 1920 · 환율 | 금리 side by side, aligned with them)',
                  len(cm) == (3 if width >= 1920 else 2) and len(mx) == 2 and [x[1] for x in mx] == [x[1] for x in cm[:2]], str(lay['colsTop']))
        elif width < 700:
            check(f'{tag}: phone = one column', len({x[1] for x in lay['colsTop']}) == 1, str(lay['colsTop']))
        page.screenshot(path=f'/tmp/fx_{theme}_{width}.png', full_page=True)
        if theme == 'base':
            sheet_pass(page, width)
            keyboard_pass(page, width)
    finally:
        ctx.close()


SHEET_JS = r"""
() => {
  const s = document.querySelector('.kw-sheet');
  if (!s || s.hidden) return null;
  const dd = {}; const dts = [...s.querySelectorAll('.kw-meta dt')]; for (const dt of dts) dd[dt.textContent] = dt.nextElementSibling.textContent;
  const svg = s.querySelector('.kw-svg');
  const r = s.getBoundingClientRect();
  return { title: s.querySelector('#kw-dt').textContent, px: s.querySelector('.kw-px').textContent, meta: dd, note: (s.querySelector('.kw-note') || {}).textContent || '',
    src: s.querySelector('.kw-dsrc').textContent, chart: !!svg, line: svg ? svg.querySelector('.kw-line').getAttribute('d').length : 0,
    yl: svg ? [...svg.querySelectorAll('.kw-yl')].map(t => t.textContent) : [], read: (s.querySelector('.kw-read') || {}).textContent || '',
    text: s.innerText, inView: r.left >= -1 && r.right <= innerWidth + 1, over: s.scrollWidth - s.clientWidth };
}"""


def open_sheet(page, key):
    page.click(f'#world .kw-lr[data-k="{key}"]')
    page.wait_for_selector('.kw-sheet:not([hidden]) .kw-svg', timeout=10000)
    page.wait_for_timeout(250)
    return page.evaluate(SHEET_JS)


def sheet_pass(page, width):
    tag = f'sheet {width}'
    s = open_sheet(page, 'FX_USDKRW')
    it = ITEMS['FX_USDKRW']
    check(f'{tag}: 원/달러 sheet — value, unit 원 (1달러당), % change, 하나은행 고시, note', s and s['title'] == '원/달러' and f"{it['value']:,.2f}" in s['px']
          and s['meta'].get('단위') == '원 (1달러당)' and pct_text(it['ratio']) in s['px'] and '하나은행 고시' in s['src'] and '오르면 원화 약세' in s['note'], json.dumps(s, ensure_ascii=False)[:300])
    check(f'{tag}: 원/달러 chart drawn (3개월), no NaN/null', s['chart'] and s['line'] > 50 and not re.search(r'\b(NaN|null|undefined)\b', s['text']), s['read'])
    page.click('.kw-sheet .kw-tf button[data-v="1y"]')
    page.wait_for_function("document.querySelector('.kw-sheet .kw-tf button[aria-pressed=true]').dataset.v === '1y' && !!document.querySelector('.kw-sheet .kw-svg')", timeout=10000)
    page.wait_for_timeout(200)
    s1 = page.evaluate(SHEET_JS)
    check(f'{tag}: 1년 switch redraws', s1['chart'] and '1년 동안' in s1['read'], s1['read'])
    page.screenshot(path=f'/tmp/fx_sheet_fx_{width}.png')
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    back = page.evaluate("({ hidden: document.querySelector('.kw-sheet').hidden, focus: document.activeElement && document.activeElement.dataset.k })")
    check(f'{tag}: Esc closes, focus back on the row', back['hidden'] and back['focus'] == 'FX_USDKRW', str(back))
    s = open_sheet(page, 'KR3YT')
    it = ITEMS['KR3YT']
    check(f'{tag}: 국고채 3년 sheet — x.xxx%, bp (and %p) change, 연 %, 레피니티브', s and s['title'] == '한국 국고채 3년' and f"{it['value']:.3f}%" in s['px']
          and bp_text(it['bp']) in s['px'] and '%p' in s['px'] and s['meta'].get('단위') == '연 %' and '레피니티브' in s['src'] and 'bp' in s['note'], json.dumps(s, ensure_ascii=False)[:300])
    check(f'{tag}: bond chart in % with bp moves', s['chart'] and all(y.endswith('%') for y in s['yl']) and s['read'].count('bp') >= 1 and not re.search(r'\b(NaN|null|undefined)\b', s['text']), f"{s['yl']} {s['read']}")
    check(f'{tag}: sheet inside the viewport, no sideways scroll', s['inView'] and s['over'] <= 0, f"{s['inView']} {s['over']}")
    page.screenshot(path=f'/tmp/fx_sheet_bond_{width}.png')
    page.keyboard.press('Escape')
    s = open_sheet(page, 'USDJPY')
    check(f'{tag}: 달러/엔 sheet — 계산값, 엔 (1달러당), 하나은행 고시로 계산; source line says the chart is the 레피니티브 close',
          s and ITEMS['USDJPY'].get('calc') and s['meta'].get('단위') == '엔 (1달러당)' and '오르면 엔화 약세' in s['note'] and '계산값' in s['meta'].get('시세', '')
          and s['meta'].get('기준') == '하나은행 고시로 계산' and '현지 거래 시각' in s['meta'] and '차트는 레피니티브 종가' in s['src'] and '레피니티브 일봉' in s['text'],
          json.dumps({'meta': s['meta'], 'src': s['src']}, ensure_ascii=False))
    page.keyboard.press('Escape')
    s = open_sheet(page, 'DXY')
    check(f'{tag}: 달러인덱스 sheet — note "오르면 달러 강세", 10분 지연', s and '오르면 달러 강세' in s['note'] and '10분 지연' in s['meta'].get('시세', ''), json.dumps(s['meta'], ensure_ascii=False))
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)


def keyboard_pass(page, width):
    if width < 1280:
        return
    tag = f'keys {width}'
    page.focus('#world .kw-lr[data-k="FX_USDKRW"]')
    page.keyboard.press('ArrowRight')
    k1 = page.evaluate('document.activeElement.dataset.k')
    check(f'{tag}: → from 환율 goes to 금리 (same block)', ITEMS.get(k1, {}).get('gkey') == 'rates', k1)
    page.keyboard.press('ArrowRight')
    k2 = page.evaluate('document.activeElement.dataset.k')
    check(f'{tag}: → at the last column of a block stays put', k2 == k1, f'{k1} → {k2}')
    page.focus('#world .kw-lr[data-k="DXY"]')
    page.keyboard.press('Enter')
    page.wait_for_selector('.kw-sheet:not([hidden])', timeout=5000)
    check(f'{tag}: Enter opens the sheet', page.evaluate("document.querySelector('#kw-dt').textContent") == '달러인덱스')
    page.keyboard.press('Escape')


def pct_sort_pass(browser):
    ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 900, sort='pct')
    try:
        wait_list(page, N_ALL)
        lay = page.evaluate(LAYOUT_JS)
        flat = page.evaluate("[...document.querySelectorAll('#world .kw-col[data-b=cm] .kw-lr')].map(r => r.dataset.k)")
        ratios = [ITEMS[k]['ratio'] for k in flat]
        check('등락률순: 원자재 ranked alone (no FX / yields), 환율 · 금리 stay grouped above', len(flat) == N_CM and ratios == sorted(ratios, reverse=True)
              and lay['secs'][:2] == ['fx', 'rates'] and 'cap:환율 · 금리' in lay['kids'], f"{len(flat)} ranked; {lay['kids']}")
        rows = page.evaluate(ROWS_JS, ITEMS)
        check('등락률순: rows still = API', not rows['bad'] and not rows['clip'], '; '.join((rows['bad'] + rows['clip'])[:3]))
        page.screenshot(path='/tmp/fx_pct_1280.png', full_page=True)
    finally:
        ctx.close()


def old_worker_pass(browser):
    """An older Worker ignores `with`: the tab shows the commodities exactly as before — no captions, no errors."""
    mode(macro='off')
    try:
        for w, hgt in ((390, 844), (1280, 800)):
            ctx, page = open_page(browser, LIVE + '#cmdty', w, hgt)
            try:
                wait_list(page, N_CM)
                lay = page.evaluate(LAYOUT_JS)
                check(f'older Worker {w}: commodities only, no captions, summary unlabelled, no stray text', lay['secs'] == ['energy', 'metals', 'agri'] and not any(k.startswith('cap:') for k in lay['kids'])
                      and not lay['sum'].startswith('원자재') and lay['rankSub'] == f'{N_CM}개 중' and not lay['bad'] and lay['over'] <= 0, f"{lay['kids']} / {lay['sum']}")
            finally:
                ctx.close()
    finally:
        mode(macro='on')


def eod_pass(browser):
    """the Worker's fallback: 달러/엔 = the 레피니티브 daily close (eod)"""
    mode(macro='eod')
    try:
        ctx, page = open_page(browser, LIVE + '#cmdty', 390, 844)
        try:
            wait_list(page, N_ALL)
            lay = page.evaluate(LAYOUT_JS)
            check('fallback close: 달러/엔 row says 마감 + 오르면 엔화 약세, source says 하루 한 번 종가', lay['usdjpySt'] == '마감' and lay['usdjpy']['text'] == '오르면 엔화 약세'
                  and lay['usdjpy']['shown'] and '달러/엔은 하루 한 번 바뀌는 종가' in lay['src'] and not lay['bad'], f"{lay['usdjpySt']} {lay['usdjpy']}")
            page.click('#world .kw-lr[data-k="USDJPY"]')
            page.wait_for_selector('.kw-sheet:not([hidden]) .kw-svg', timeout=10000)
            page.wait_for_timeout(300)
            s = page.evaluate(SHEET_JS)
            check('fallback close: sheet = 기준일 … 종가 (no time), 레피니티브, no 계산값', s and s['meta'].get('기준일', '').endswith('종가') and '한국 시각' not in s['meta']
                  and s['meta'].get('기준') == '레피니티브' and '계산값' not in s['text'] and '하루 한 번 종가' in s['src'], json.dumps(s and s['meta'], ensure_ascii=False))
        finally:
            ctx.close()
    finally:
        mode(macro='on')


def norates_pass(browser):
    mode(macro='norates')
    try:
        ctx, page = open_page(browser, LIVE + '#cmdty', 1280, 800)
        try:
            wait_list(page, N_CM + 6)
            lay = page.evaluate(LAYOUT_JS)
            check('금리 source down: 환율 alone, caption "환율"', lay['secs'] == ['fx', 'energy', 'metals', 'agri'] and 'cap:환율' in lay['kids'] and not lay['bad'], str(lay['kids']))
        finally:
            ctx.close()
    finally:
        mode(macro='on')


def other_tab_pass(browser):
    """해외 tab untouched: no captions, no macro rows, the world request has no `with`."""
    ctx, page = open_page(browser, LIVE + '#world', 1280, 800)
    reqs = []
    page.on('request', lambda r: reqs.append(r.url) if '/api/world?' in r.url else None)
    try:
        page.reload()
        wait_list(page)
        lay = page.evaluate(LAYOUT_JS)
        check('해외 tab unchanged: no captions, no 환율 · 금리, plain kind=index request', not any(k.startswith('cap:') for k in lay['kids']) and 'fx' not in lay['secs']
              and any(u.endswith('kind=index') for u in reqs) and not any('with=' in u for u in reqs if 'kind=index' in u), str(reqs[:3]))
        page.click('.tabs button[data-mkt="CMDTY"]')
        wait_list(page, N_ALL)
        check('tab switch 해외 → 지표 asks with=fx,rates', any('kind=commodity&with=fx,rates' in u for u in reqs), str(reqs[-2:]))
    finally:
        ctx.close()


def ticker_pass(browser):
    """extras ticker: tapping 원/달러 (strip key USDKRW) opens the FX_USDKRW sheet (TK_WORLD), not the Naver-link box"""
    ctx, page = open_page(browser, LIVE + '#kospi', 1280, 800)
    try:
        page.wait_for_selector('.xs-item[data-k="USDKRW"]', timeout=15000)
        page.wait_for_timeout(500)
        page.evaluate("document.querySelector('.xs-item[data-k=USDKRW]').click()")   # the strip scrolls: a real click never sees it stable
        page.wait_for_selector('.kw-sheet:not([hidden]) .kw-svg', timeout=10000)
        page.wait_for_timeout(300)
        r = page.evaluate("({ t: document.querySelector('#kw-dt').textContent, info: !!document.querySelector('dialog.xk-info[open]') })")
        check('ticker: 원/달러 opens the 원/달러 sheet with its chart', r['t'] == '원/달러' and not r['info'], str(r))
    finally:
        ctx.close()


def snapshot_pass(browser):
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    page = ctx.new_page()
    ERR.attach(page)
    try:
        page.goto(SNAP + '#cmdty')
        page.wait_for_selector('#world .kw-snap', timeout=10000)
        t = page.evaluate("({ snap: document.querySelector('#world .kw-snap b').textContent, body: document.querySelector('#world .kw-snap p').textContent, tab: document.querySelector('.tabs button[data-mkt=CMDTY]').textContent })")
        check('snapshot: tab 지표, "지표 탭은 실시간 버전에서 볼 수 있어요", mentions 환율·금리', t['tab'] == TAB and t['snap'] == f'{TAB} 탭은 실시간 버전에서 볼 수 있어요' and '환율' in t['body'] and '금리' in t['body'], str(t))
    finally:
        ctx.close()


def main():
    mock = None
    try:
        get(LIVE + '__reset', 2)
    except Exception:
        mock = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                get(LIVE + '__reset', 2)
                break
            except Exception:
                time.sleep(0.25)
    try:
        mode(macro='on')
        if '--no-real' not in sys.argv:
            worker_pass()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for theme in THEMES:
                for w, hgt in ((390, 844), (1280, 800)):
                    ui_tab_pass(browser, theme, w, hgt)
            ui_tab_pass(browser, 'base', 768, 1024)
            ui_tab_pass(browser, 'base', 1920, 1080)
            pct_sort_pass(browser)
            old_worker_pass(browser)
            eod_pass(browser)
            norates_pass(browser)
            other_tab_pass(browser)
            ticker_pass(browser)
            snapshot_pass(browser)
            browser.close()
        check('console errors 0, no failed /api/world* requests', not ERR.items and not ERR.http, '; '.join((ERR.items + ERR.http)[:4]))
    finally:
        get(LIVE + '__reset', 2)
        if mock:
            mock.terminate()
    fails = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(fails)}/{len(results)} passed')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
