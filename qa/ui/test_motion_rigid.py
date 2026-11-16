#!/usr/bin/env python3
"""② 단단한 이동 — every control moves rigidly (AGENTS §3-38, 사용자 2026-11-16 10:02 "컨트롤 움직임은 추천대로 2번";
시안 drafts/motion-unify.html ②). Measured on paused frames: each CSS transition is paused right after the change and sought
step by step (no frame timing involved); the KH.spring indicator (종목 페이지 .sp-ind) is read at every frame it writes.

  python3 qa/ui/test_motion_rigid.py [--only=seg,switch,drag,chip,star,stock,reduced,sweep]

Live build (web/). Mocks: qa/news/mock_api.py on MOTION_QA_PORT (default 9071) and qa/stock/mock_api.py on +1 — ports 9070–9079
(9010–9089 if a mock's own port check needs it). Ports are freed with fuser -k only.
Checks
  seg     the market tabs (.tabs-sc pill + underline), the 눈에 띄는 종목 segment (.movers-tabs), the news card's underline title tabs
          (.nw-ftabs): all four edges on the one --sp-lead curve, both edges the same share of their way at every sought frame, the
          width between the two tab widths (a segment of equal cells: constant)
  switch  every switch is one implementation: 화면 settings (.swbtn), 오늘 공시 지도 스위치 (.dc-lit) — knob = ::after 22 × 22 that only
          translates (no scale, no width change) on --sp-lead, 0 → 18px, overshoot ≤ 1.5 %; fill ::before on --sp-fade
  drag    the knob dragged and let go: a slow drag past half lands on, a short fast flick (> 0.11 px/ms) throws it on from below half;
          while it lands (.sw-fly) `settle` writes --t (the finger's speed carried on); at rest the inline --t is gone
  chip    .kchip (공시 종류 settings) · .nw-only (지도 종목 기사만) · .dc-only (지도 종목만): the width is the same on and off and at every
          sought frame, the next chip never moves, the check and the fill fade (on) / close (off), nothing translates or scales
  star    ☆ ↔ ★ (빠른 보기 .wstar): the two glyphs cross-fade (opacity on --sp-fade / --sp-close), the key never changes size
  stock   종목 페이지: 지분 공시 스위치 (.sp-switch) the same knob / fill; the 봉 간격 indicator (.sp-ind, KH.spring.edges) keeps its width
          at every frame
  reduced 줄이기: a switch, a segment and a chip land at once (no running transition, the end state on the next read)
  sweep   4 themes × 360 · 1280: no element past the screen sides, no page pan, 0 console errors
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('MOTION_QA_PORT', 9071))
SPORT = PORT + 1
assert 9070 <= PORT <= 9078 or 9010 <= PORT <= 9088, 'ports 9070–9079 (or 9010–9089)'
URL = f'http://127.0.0.1:{PORT}/'
SURL = f'http://127.0.0.1:{SPORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FAILS, PASSES, ERRS = [], [], []
ONLY = next((a.split('=', 1)[1].split(',') for a in sys.argv[1:] if a.startswith('--only=')), None)
THEMES = ('base', 'paper', 'glass-dark', 'glass-light')


def want(k):
    return ONLY is None or k in ONLY


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'))


def start(cmd, url):
    port = url.rsplit(':', 1)[1].strip('/')
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    time.sleep(0.2)
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, MOCK_WEB=str(ROOT / 'web')))
    for _ in range(80):
        try:
            NOPROXY.open(url + 'api/time', timeout=1).read()
            return p
        except Exception:
            time.sleep(0.1)
    raise SystemExit(f'mock did not start: {cmd}')


def open_page(br, w, h, url=URL, motion='standard', theme='base', market='K', extra=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{motion}'
    ign = [0]   # the stock mock leaves data/close.json and api/breadth at 404 on purpose (qa/stock/test_stock.py does the same)
    pg.on('response', lambda r: ign.__setitem__(0, ign[0] + 1) if r.status == 404 and ('/data/close.json' in r.url or '/api/breadth' in r.url) else None)

    def on_console(m):
        if m.type != 'error':
            return
        if 'Failed to load resource' in m.text and ign[0] > 0:
            ign[0] -= 1
            return
        ERRS.append(f'{tag}: {m.text[:200]}')
    pg.on('console', on_console)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(url)
    pg.wait_for_timeout(1800)
    pg.add_script_tag(content=HELPERS)
    return ctx, pg


# page helpers: QA.seek(el, pseudo, act, read, n) runs act(), lets the observers run, pauses every transition on el(+pseudo) and
# reads read() at n + 1 sought moments from 0 to the longest end; the result also names each transition's property · length · curve
HELPERS = r"""
window.QA = {
  token: n => getComputedStyle(document.documentElement).getPropertyValue(n).trim(),
  norm: s => String(s || '').replace(/\s+/g, ''),
  // a curve token as the browser writes it back (the canonical linear(0 0%, …) form a transition reports)
  ease(n) { const d = document.createElement('i'); d.style.transitionTimingFunction = `var(${n})`; document.body.append(d); const v = getComputedStyle(d).transitionTimingFunction; d.remove(); return QA.norm(v); },
  async seek(el, pseudo, act, read, n = 16) {
    await act();
    await new Promise(r => setTimeout(r, 0));
    getComputedStyle(el, pseudo || null).getPropertyValue('opacity');
    const mine = a => a.effect && a.effect.target === el && (a.effect.pseudoElement || null) === (pseudo || null);
    const anims = document.getAnimations().filter(mine);
    anims.forEach(a => a.pause());
    const end = Math.max(0, ...anims.map(a => { const t = a.effect.getComputedTiming(); return (t.delay || 0) + t.activeDuration; }));
    const out = [];
    for (let i = 0; i <= n; i++) { const t = end * i / n; anims.forEach(a => { a.currentTime = t; }); out.push(read()); }
    const info = anims.map(a => { const k = a.effect.getKeyframes(), ke = QA.norm(k[0] && k[0].easing), te = QA.norm(a.effect.getTiming().easing);
      return { prop: a.transitionProperty, dur: Math.round(a.effect.getComputedTiming().activeDuration), ease: ke && ke !== 'linear' ? ke : te }; });
    anims.forEach(a => a.finish());
    return { end, info, out };
  },
  edges(seg, pseudo) {
    const cs = getComputedStyle(seg, pseudo), L = parseFloat(cs.left), R = parseFloat(cs.right);
    return { L, R, W: seg.clientWidth - L - R };
  },
  knob(tr) {
    const a = getComputedStyle(tr, '::after'), m = new DOMMatrixReadOnly(a.transform === 'none' ? undefined : a.transform);
    return { x: m.m41, sx: m.a, sy: m.d, w: parseFloat(a.width), h: parseFloat(a.height), fill: +getComputedStyle(tr, '::before').opacity };
  },
};
"""


def rigid(r, w0, w1, tag):
    """both edges the same share of their way at every sought frame; the width stays between w0 and w1 (± lead's overshoot)"""
    o = r['out']
    a, b = o[0], o[-1]
    gaps, ws = [], [x['W'] for x in o]
    for x in o:
        pl = (x['L'] - a['L']) / (b['L'] - a['L']) if abs(b['L'] - a['L']) > 0.5 else None
        pr = (x['R'] - a['R']) / (b['R'] - a['R']) if abs(b['R'] - a['R']) > 0.5 else None
        if pl is not None and pr is not None:
            gaps.append(abs(pl - pr))
    lo, hi = min(w0, w1) - 0.6 - 0.015 * abs(w1 - w0), max(w0, w1) + 0.6 + 0.015 * abs(w1 - w0)
    return {'tag': tag, 'gap': round(max(gaps or [0]), 4), 'wmin': round(min(ws), 2), 'wmax': round(max(ws), 2), 'lo': round(lo, 2), 'hi': round(hi, 2),
            'ok': (max(gaps or [0]) < 0.01) and min(ws) >= lo and max(ws) <= hi, 'info': r['info']}


def lead_only(info, lead, props):
    return bool(info) and all(i['ease'] == lead for i in info if i['prop'] in props) and {i['prop'] for i in info} >= set(props)


def t_seg(br):
    for w, h in ((1280, 900), (360, 780)):
        ctx, pg = open_page(br, w, h)
        lead = pg.evaluate("QA.ease('--sp-lead')")
        # market tabs: 코스피 → 테마 (different widths), pill ::before and underline ::after
        r = pg.evaluate("""async () => {
          const seg = document.querySelector('.tabs-sc'), bs = [...seg.querySelectorAll(':scope > button')];
          const to = bs.find(b => b.dataset.mkt === 'THEME') || bs[3];
          const w0 = bs.find(b => b.getAttribute('aria-pressed') === 'true').offsetWidth, w1 = to.offsetWidth;
          const from = bs.find(b => b.getAttribute('aria-pressed') === 'true');
          const s = await QA.seek(seg, '::before', () => to.click(), () => QA.edges(seg, '::before'));
          const under = getComputedStyle(seg, '::after').transitionTimingFunction;
          from.click(); await new Promise(r => setTimeout(r, 900));
          return { s, w0, w1, under };
        }""")
        rr = rigid(r['s'], r['w0'], r['w1'], f'{w} market tabs')
        check(f'{w} market tabs: the pill moves in one piece (both edges the same share at every frame, gap {rr["gap"]}), width {rr["wmin"]}–{rr["wmax"]} within {rr["lo"]}–{rr["hi"]}',
              rr['ok'] and lead_only(r['s']['info'], lead, ['left', 'right']), rr)
        check(f'{w} market tabs: the underline (::after) on the same lead curve, all four edges', 'linear(' in r['under'] and r['under'].count('linear(') == 4, r['under'][:120])
        # 눈에 띄는 종목 segment (equal cells): the width never changes
        r = pg.evaluate("""async () => {
          const seg = document.querySelector('.movers-tabs'); if (!seg || !seg.offsetWidth) return null;
          const bs = [...seg.querySelectorAll(':scope > button')].filter(b => !b.hidden), cur = bs.findIndex(b => b.getAttribute('aria-pressed') === 'true');
          const to = bs[(cur + bs.length - 1) % bs.length];
          const w0 = bs[cur].offsetWidth, w1 = to.offsetWidth;
          const s = await QA.seek(seg, '::before', () => to.click(), () => QA.edges(seg, '::before'));
          return { s, w0, w1 };
        }""")
        if r is None:
            check(f'{w} movers segment present', w <= 760, 'no .movers-tabs on screen')
        else:
            rr = rigid(r['s'], r['w0'], r['w1'], f'{w} movers')
            check(f'{w} 눈에 띄는 종목 segment (equal cells {r["w0"]}/{r["w1"]}px): width {rr["wmin"]}–{rr["wmax"]} at every frame, edges in step (gap {rr["gap"]}), lead only',
                  rr['ok'] and abs(rr['wmax'] - rr['wmin']) <= 1.0 and lead_only(r['s']['info'], lead, ['left', 'right']), rr)
        # news card title tabs (underline): 시장 뉴스 → 오늘 공시
        r = pg.evaluate("""async () => {
          const seg = document.querySelector('#news .nw-ftabs'); if (!seg) return null;
          seg.scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 100));
          const bs = [...seg.querySelectorAll(':scope > button')].filter(b => !b.hidden), cur = bs.findIndex(b => b.getAttribute('aria-selected') === 'true');
          const to = bs[(cur + 1) % bs.length];
          const w0 = bs[cur].offsetWidth, w1 = to.offsetWidth;
          const s = await QA.seek(seg, '::before', () => to.click(), () => QA.edges(seg, '::before'));
          bs[cur].click();
          return { s, w0, w1 };
        }""")
        if r is None:
            check(f'{w} news title tabs present', False, 'no #news .nw-ftabs')
        else:
            rr = rigid(r['s'], r['w0'], r['w1'], f'{w} news title tabs')
            check(f'{w} news card title tabs (underline): one piece on lead (gap {rr["gap"]}), width {rr["wmin"]}–{rr["wmax"]}', rr['ok'] and lead_only(r['s']['info'], lead, ['left', 'right']), rr)
        ctx.close()


SWITCH_PROBE = r"""async (sel) => {
  const b = [...document.querySelectorAll(sel)].find(x => x.offsetWidth && x.getAttribute('aria-disabled') !== 'true'); if (!b) return null;
  b.scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 150));
  const tr = b.querySelector('.swt'), was = b.getAttribute('aria-checked');
  const knobS = await QA.seek(tr, '::after', () => b.click(), () => QA.knob(tr));
  const fillS = { info: [] };
  // the fill ran in the same change: its transition was finished with the knob's — read its curve from the computed style
  const fcs = getComputedStyle(tr, '::before');
  const res = { was, now: b.getAttribute('aria-checked'), knob: knobS, fillEase: QA.norm(fcs.transitionTimingFunction), fillProp: fcs.transitionProperty,
    knobEase: QA.norm(getComputedStyle(tr, '::after').transitionTimingFunction), lead: QA.ease('--sp-lead'), fade: QA.ease('--sp-fade'),
    kids: tr.children.length };
  b.click(); await new Promise(r => setTimeout(r, 700));
  return res;
}"""


def judge_switch(r, tag):
    o = r['knob']['out']
    xs = [p['x'] for p in o]
    on = r['now'] == 'true'
    x0, x1 = (0, 18) if on else (18, 0)
    over = max(0, max(xs) - 18) if on else max(0, -min(xs))
    sg = 1 if x1 > x0 else -1
    mono = all((b - a) * sg >= -0.3 for a, b in zip(xs, xs[1:]))        # forward all the way (the ≤ 0.27px overshoot comes back)
    shape = all(abs(p['w'] - 22) < 0.01 and abs(p['h'] - 22) < 0.01 and abs(p['sx'] - 1) < 1e-6 and abs(p['sy'] - 1) < 1e-6 for p in o)
    d = {'tag': tag, 'xs': [round(x, 2) for x in xs[::4]], 'over': round(over, 3), 'shape': shape, 'mono': mono, 'info': r['knob']['info'], 'fill': r['fillEase'][:30], 'kids': r['kids']}
    ok = (r['was'] != r['now'] and abs(xs[0] - x0) < 0.3 and abs(xs[-1] - x1) < 0.01 and shape and mono and over <= 0.27 + 0.01
          and r['knobEase'].startswith(r['lead'] + ',') and r['fillEase'] == r['fade'] and r['kids'] == 0)
    return ok, d


def t_switch(br):
    for w, h in ((1280, 900), (360, 780)):
        ctx, pg = open_page(br, w, h)
        # 화면 settings: popover (≥ 1280) or the 표시 설정 sheet
        pg.evaluate("() => { const m = document.querySelector('.morebtn'); if (m && m.offsetWidth) m.click(); else document.getElementById('setBtn').click(); }")
        pg.wait_for_timeout(700)
        r = pg.evaluate(SWITCH_PROBE, '.swbtn:not([hidden])')
        if r is None:
            check(f'{w} 화면 settings switch present', False)
        else:
            ok, d = judge_switch(r, f'{w} .swbtn')
            check(f'{w} 화면 settings switch (.swbtn): knob 22 × 22 only translates {d["xs"]} on lead, overshoot {d["over"]}px ≤ 1.5 %, fill on fade', ok, d)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
        # 오늘 공시 지도 스위치
        pg.evaluate("() => { if (window.KHNews && KHNews.select) KHNews.select('disc'); }")
        pg.wait_for_timeout(700)
        r = pg.evaluate(SWITCH_PROBE, '#news .dc-lit')
        if r is None:
            check(f'{w} 공시 지도 스위치 present', False)
        else:
            ok, d = judge_switch(r, f'{w} .dc-lit')
            check(f'{w} 오늘 공시 지도 스위치 (.dc-lit): the same switch — no knob element of its own, knob only translates {d["xs"]} on lead, fill on fade', ok, d)
        ctx.close()


def t_drag(br):
    ctx, pg = open_page(br, 1280, 900)
    pg.evaluate("() => { if (window.KHNews && KHNews.select) KHNews.select('disc'); }")
    pg.wait_for_timeout(700)
    pg.evaluate("document.querySelector('#news .dc-lit').scrollIntoView({block: 'center'})")
    pg.wait_for_timeout(300)
    box = pg.evaluate("(() => { const r = document.querySelector('#news .dc-lit .swt').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
    x, y = box[0] + 13, box[1] + box[3] / 2
    watch = """() => { const b = document.querySelector('#news .dc-lit'), tr = b.querySelector('.swt'); window.__sw = [];
      const f = () => { window.__sw.push([b.classList.contains('sw-fly'), tr.style.getPropertyValue('--t'), b.getAttribute('aria-checked')]); if (window.__sw.length < 90) requestAnimationFrame(f); };
      requestAnimationFrame(f); }"""
    # a slow drag past half → on, landing on settle
    pg.mouse.move(x, y); pg.mouse.down()
    for i in range(1, 13):
        pg.mouse.move(x + i, y); pg.wait_for_timeout(30)
    pg.wait_for_timeout(150)                    # the finger stops: no speed left
    pg.evaluate(watch)
    pg.mouse.up()
    pg.wait_for_timeout(1100)
    tr = pg.evaluate("window.__sw")
    st = pg.evaluate("(() => { const b = document.querySelector('#news .dc-lit'); return [b.getAttribute('aria-checked'), b.querySelector('.swt').style.getPropertyValue('--t'), b.classList.contains('sw-fly'), b.classList.contains('drag')]; })()")
    flying = [p for p in tr if p[0]]
    ts = [float(p[1]) for p in flying if p[1]]
    check(f'drag past half and let go (finger stopped): on at once, lands through .sw-fly ({len(flying)} frames, --t {ts[:1]} → {ts[-1:]}) on settle, then the inline --t is gone',
          st[0] == 'true' and len(flying) >= 3 and ts and ts[0] < 0.95 and not st[2] and not st[3] and st[1] == '', {'st': st, 'trace': tr[:6]})
    # back off: click (CSS, lead)
    pg.evaluate("document.querySelector('#news .dc-lit').click()"); pg.wait_for_timeout(700)
    # a short fast flick from off: 7px in ~20ms → a throw (> 0.11 px/ms) though the knob is below half
    pg.mouse.move(x, y); pg.mouse.down()
    pg.evaluate(watch)
    for i in (2, 5, 7):
        pg.mouse.move(x + i, y); pg.wait_for_timeout(8)
    pg.mouse.up()
    pg.wait_for_timeout(1100)
    tr = pg.evaluate("window.__sw")
    st = pg.evaluate("(() => { const b = document.querySelector('#news .dc-lit'); return [b.getAttribute('aria-checked'), b.querySelector('.swt').style.getPropertyValue('--t'), b.classList.contains('sw-fly')]; })()")
    ts = [float(p[1]) for p in tr if p[0] and p[1]]
    rise = [b - a for a, b in zip(ts, ts[1:])]
    check(f'a fast flick below half (7px) throws it on — the release speed carried by settle (first steps {[round(v, 3) for v in rise[:3]]}), max --t {max(ts) if ts else None} ≤ 1 + 1px/18',
          st[0] == 'true' and st[1] == '' and not st[2] and ts and max(ts) <= 1 + 1 / 18 + 0.002 and ts[0] < 0.6, {'st': st, 'ts': ts[:8]})
    pg.evaluate("document.querySelector('#news .dc-lit').click()"); pg.wait_for_timeout(500)
    ctx.close()


CHIP_PROBE = r"""async (sel) => {
  const b = document.querySelector(sel); if (!b || !b.offsetWidth) return null;
  b.scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 150));
  const nx = b.nextElementSibling && b.nextElementSibling.offsetWidth ? b.nextElementSibling : null, ck = b.querySelector('i, .ck, .nw-ck');
  const read = () => ({ w: b.getBoundingClientRect().width, nx: nx ? nx.getBoundingClientRect().left : null, op: ck ? +getComputedStyle(ck).opacity : null,
    tf: ck ? getComputedStyle(ck).transform : 'none', bw: ck ? ck.getBoundingClientRect().width : null });
  const was = b.getAttribute('aria-pressed');
  const a = await QA.seek(ck || b, null, () => b.click(), read);
  const ckE = ck ? QA.norm(getComputedStyle(ck).transitionTimingFunction) : '', bgE = QA.norm(getComputedStyle(b).transitionTimingFunction);
  const now = b.getAttribute('aria-pressed');
  const z = await QA.seek(ck || b, null, () => b.click(), read);
  const ckE2 = ck ? QA.norm(getComputedStyle(ck).transitionTimingFunction) : '', bgE2 = QA.norm(getComputedStyle(b).transitionTimingFunction);
  await new Promise(r => setTimeout(r, 500));
  return { was, now, a: a.out, z: z.out, ai: a.info, zi: z.info, ckE, bgE, ckE2, bgE2, fade: QA.ease('--sp-fade'), close: QA.ease('--sp-close'), back: b.getAttribute('aria-pressed') };
}"""


def judge_chip(r, tag):
    frames = r['a'] + r['z']
    ws = [f['w'] for f in frames]
    nxs = [f['nx'] for f in frames if f['nx'] is not None]
    on_first = r['now'] == 'true'
    e_on, e_off = (r['ckE'], r['ckE2']) if on_first else (r['ckE2'], r['ckE'])
    b_on, b_off = (r['bgE'], r['bgE2']) if on_first else (r['bgE2'], r['bgE'])
    still = all(f['tf'] == 'none' for f in frames) and len({round(f['bw'] or 0, 2) for f in frames}) == 1
    d = {'tag': tag, 'w': [round(min(ws), 2), round(max(ws), 2)], 'nx': [round(min(nxs), 2), round(max(nxs), 2)] if nxs else None, 'still': still,
         'ck_on': e_on[:24], 'ck_off': e_off[:24], 'bg_on': b_on[:60], 'bg_off': b_off[:60]}
    ok = (r['was'] != r['now'] and r['back'] == r['was'] and max(ws) - min(ws) < 0.05 and (not nxs or max(nxs) - min(nxs) < 0.05) and still
          and e_on == r['fade'] and e_off == r['close'] and r['fade'] in b_on and r['close'] in b_off)
    return ok, d


def t_chip(br):
    for w, h in ((1280, 900), (360, 780)):
        ctx, pg = open_page(br, w, h)
        for sel, name in (('#news .nw-only:not(.dc-only)', '시장 뉴스 지도 종목 기사만 (.nw-only)'),):
            r = pg.evaluate(CHIP_PROBE, sel)
            if r is None:
                check(f'{w} {name} present', False)
                continue
            ok, d = judge_chip(r, f'{w} {sel}')
            check(f'{w} {name}: width {d["w"]} on · off · every frame, next chip {d["nx"]}, the check never moves or grows, fade on / close off', ok, d)
        pg.evaluate("() => { if (window.KHNews && KHNews.select) KHNews.select('disc'); }")
        pg.wait_for_timeout(700)
        r = pg.evaluate(CHIP_PROBE, '#news .dc-only')
        if r is None:
            check(f'{w} 공시 지도 종목만 (.dc-only) present', False)
        else:
            ok, d = judge_chip(r, f'{w} .dc-only')
            check(f'{w} 공시 지도 종목만 (.dc-only): width {d["w"]}, next {d["nx"]}, fade on / close off, nothing moves', ok, d)
        pg.evaluate("() => { const m = document.querySelector('.morebtn'); if (m && m.offsetWidth) m.click(); else document.getElementById('setBtn').click(); }")
        pg.wait_for_timeout(700)
        r = pg.evaluate(CHIP_PROBE, '[data-set="discKinds"] .kchip[data-si="2"]')
        if r is None:
            check(f'{w} 공시 종류 chips (.kchip) present', False)
        else:
            ok, d = judge_chip(r, f'{w} .kchip')
            check(f'{w} 표시 설정 공시 종류 chip (.kchip): width {d["w"]} on · off · every frame, next chip {d["nx"]}, fade on / close off', ok, d)
        ctx.close()


def t_star(br):
    ctx, pg = open_page(br, 1280, 900)
    pg.evaluate("() => KH.quick('005930')")              # the quick view's ☆ (syncStars changes it in place)
    pg.wait_for_timeout(900)
    r = pg.evaluate("""async () => {
      const b = [...document.querySelectorAll('#sheet button.wstar[data-w]')].find(x => x.offsetWidth); if (!b) return null;
      b.scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 150));
      const s1 = b.querySelector('.sg1'), s0 = b.querySelector('.sg0'); if (!s1 || !s0) return { glyphs: false, text: b.textContent };
      const r0 = b.getBoundingClientRect();
      const read = () => ({ o1: +getComputedStyle(s1).opacity, o0: +getComputedStyle(s0).opacity, w: b.getBoundingClientRect().width, h: b.getBoundingClientRect().height });
      const was = b.getAttribute('aria-pressed');
      const a = await QA.seek(s1, null, () => b.click(), read, 8);
      const e1 = QA.norm(getComputedStyle(s1).transitionTimingFunction), e0 = QA.norm(getComputedStyle(s0).transitionTimingFunction);
      const now = b.getAttribute('aria-pressed');
      await new Promise(r => setTimeout(r, 450));
      const z = await QA.seek(s1, null, () => b.click(), read, 8);
      const f1 = QA.norm(getComputedStyle(s1).transitionTimingFunction);
      return { glyphs: true, was, now, a: a.out, z: z.out, e1, e0, f1, fade: QA.ease('--sp-fade'), close: QA.ease('--sp-close'), w0: r0.width, h0: r0.height, back: b.getAttribute('aria-pressed') };
    }""")
    if not r or not r.get('glyphs'):
        check('빠른 보기 ☆ (.wstar) carries both glyphs', False, r)
    else:
        mid = r['a'][1]                                   # an eighth of the way: ★ partly in
        sizes = {(round(f['w'], 2), round(f['h'], 2)) for f in r['a'] + r['z']}
        on_first = r['now'] == 'true'
        check(f'☆ ↔ ★ (빠른 보기 .wstar): the two glyphs cross-fade (⅛ of the way ★ {mid["o1"]:.2f}), ★ in on fade, out on close; the key keeps its size {sizes}',
              r['was'] != r['now'] and r['back'] == r['was'] and len(sizes) == 1 and 0.05 < mid['o1'] < 0.95 and
              ((r['e1'] == r['fade'] and r['e0'] == r['close'] and r['f1'] == r['close']) if on_first else (r['e1'] == r['close'] and r['f1'] == r['fade'])), r)
    ctx.close()


def t_stock(br, sp):
    ctx, pg = open_page(br, 1280, 900, url=SURL + '#s-005930')
    pg.wait_for_timeout(1500)
    # 봉 간격 indicator: KH.spring.edges, read at every frame it writes
    r = pg.evaluate("""async () => {
      const seg = [...document.querySelectorAll('.sp .sp-seg.sp-ix')].find(s => s.offsetWidth && [...s.children].some(b => /^(일|주|월)$/.test(b.textContent.trim())));
      if (!seg) return null;
      const ind = seg.querySelector(':scope > .sp-ind'), bs = [...seg.querySelectorAll(':scope > button')].filter(b => !b.hidden);
      const day = bs.find(b => b.textContent.trim() === '일'), mon = bs.find(b => b.textContent.trim() === '월');
      if (day.getAttribute('aria-pressed') !== 'true') { day.click(); await new Promise(r => setTimeout(r, 900)); }
      const ws = [], xs = [];
      mon.click();
      await new Promise(done => { let k = 0; const f = () => { ws.push(parseFloat(ind.style.width)); xs.push(ind.style.transform); if (++k < 40) requestAnimationFrame(f); else done(); }; requestAnimationFrame(f); });
      day.click(); await new Promise(r => setTimeout(r, 700));
      return { ws, moved: new Set(xs).size, w0: day.offsetWidth, w1: mon.offsetWidth };
    }""")
    if r is None:
        check('stock 봉 간격 segment present', False)
    else:
        ws = [x for x in r['ws'] if x == x]
        check(f'종목 페이지 봉 간격 indicator (.sp-ind, KH.spring.edges): {r["moved"]} positions, width {min(ws):.2f}–{max(ws):.2f} (cells {r["w0"]} / {r["w1"]}) — one piece, no stretch',
              r['moved'] >= 5 and max(ws) - min(ws) <= abs(r['w1'] - r['w0']) + 0.6, r)
    pg.evaluate("() => KHStock.open('005930', { tab: 'news', newsKind: 'disc' })")
    pg.wait_for_timeout(1500)
    r = pg.evaluate(SWITCH_PROBE, '.sp .sp-switch:not([hidden])')
    if r is None:
        check('종목 페이지 지분 공시 스위치 present', False)
    else:
        ok, d = judge_switch(r, 'stock .sp-switch')
        check(f'종목 페이지 지분 공시 스위치 (.sp-switch): the template switch — knob only translates {d["xs"]} on lead, fill on fade', ok, d)
    ctx.close()


def t_reduced(br):
    ctx, pg = open_page(br, 1280, 900, motion='reduced')
    pg.evaluate("() => { if (window.KHNews && KHNews.select) KHNews.select('disc'); }")
    pg.wait_for_timeout(700)
    r = pg.evaluate("""async () => {
      const out = {};
      const sw = document.querySelector('#news .dc-lit'), tr = sw.querySelector('.swt');
      sw.scrollIntoView({ block: 'center' }); await new Promise(r => setTimeout(r, 100));
      sw.click(); await null; out.sw = [document.getAnimations().filter(a => a.effect && a.effect.target === tr).length, QA.knob(tr).x, QA.knob(tr).fill];
      sw.click();
      const seg = document.querySelector('.tabs-sc'), to = [...seg.querySelectorAll(':scope > button')].find(b => b.dataset.mkt === 'Q');
      to.click(); await new Promise(r => setTimeout(r, 0));
      const e = QA.edges(seg, '::before');
      out.seg = [document.getAnimations().filter(a => a.effect && a.effect.target === seg).length, Math.abs(e.L - (to.offsetLeft + (parseFloat(getComputedStyle(seg).getPropertyValue('--ind-in')) || 0))) < 1];
      const ch = document.querySelector('#news .dc-only'), ck = ch.querySelector('i');
      const w0 = ch.getBoundingClientRect().width; ch.click(); await null;
      out.chip = [document.getAnimations().filter(a => a.effect && (a.effect.target === ch || a.effect.target === ck)).length, +getComputedStyle(ck).opacity, Math.abs(ch.getBoundingClientRect().width - w0) < 0.05];
      ch.click();
      out.durs = ['--sp-lead-dur', '--sp-fade-dur', '--sp-close-dur', '--sp-settle-dur'].map(QA.token);
      return out;
    }""")
    check(f'줄이기: switch lands at once {r["sw"]}, the market pill is there at once {r["seg"]}, a chip at once with its width {r["chip"]}; every length 0 {r["durs"]}',
          r['sw'][0] == 0 and abs(r['sw'][1] - 18) < 0.01 and r['sw'][2] == 1 and r['seg'][0] == 0 and r['seg'][1] and r['chip'][0] == 0 and r['chip'][1] in (0, 1) and r['chip'][2]
          and all(d == '0ms' for d in r['durs']), r)
    ctx.close()


OVERFLOW = r"""() => {
  const vw = document.documentElement.clientWidth, out = [];
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || (r.right <= vw + 1 && r.left >= -1)) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || +s.opacity === 0) continue;
    let p = el.parentElement, held = false;
    while (p && p !== document.body) { const q = getComputedStyle(p); if (q.overflowX !== 'visible' || q.clipPath !== 'none' || +q.opacity === 0 || q.visibility === 'hidden') { held = true; break; } p = p.parentElement; }
    if (held) continue;
    out.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : '')) + ` [${Math.round(r.left)}, ${Math.round(r.right)}]`);
  }
  scrollTo(300, scrollY);
  const sx = scrollX; scrollTo(0, scrollY);
  return { els: out.slice(0, 8), sx, sw: document.documentElement.scrollWidth, vw };
}"""


def t_sweep(br):
    bad = {}
    n0 = len(ERRS)
    for theme in THEMES:
        for w, h in ((360, 780), (1280, 900)):
            ctx, pg = open_page(br, w, h, theme=theme)
            pg.evaluate("() => { if (window.KHNews && KHNews.select) KHNews.select('disc'); }")
            pg.wait_for_timeout(400)
            o = pg.evaluate(OVERFLOW)
            if o['els'] or o['sx'] != 0 or o['sw'] > o['vw']:
                bad[f'{theme}/{w}'] = o
            ctx.close()
    check('4 themes × 360 · 1280: nothing drawn past the screen sides, the page never pans', not bad, bad)
    check(f'4 themes × 360 · 1280: console errors 0 ({len(ERRS) - n0})', len(ERRS) == n0, ERRS[n0:][:5])


def main():
    mocks = [start([sys.executable, str(ROOT / 'qa/news/mock_api.py'), str(PORT)], URL)]
    try:
        if want('stock'):
            mocks.append(start([sys.executable, str(ROOT / 'qa/stock/mock_api.py'), '--port', str(SPORT)], SURL))
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            try:
                for k, fn in (('seg', t_seg), ('switch', t_switch), ('drag', t_drag), ('chip', t_chip), ('star', t_star), ('reduced', t_reduced), ('sweep', t_sweep)):
                    if want(k):
                        print(f'── {k}')
                        fn(br)
                if want('stock'):
                    print('── stock')
                    t_stock(br, SPORT)
            finally:
                br.close()
    finally:
        for m in mocks:
            m.kill()
        for port in (PORT, SPORT):
            subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    errs = [e for e in ERRS]
    check(f'console errors 0 ({len(errs)})', not errs, errs[:6])
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAIL', f)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
