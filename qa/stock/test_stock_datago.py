#!/usr/bin/env python3
"""종목 페이지 공공데이터포털 블록(대차잔고 · 배당 내역 · 기업 정보, AGENTS.md §3 · §3-32) — Playwright against qa/stock/mock_api.py.

    python3 scripts/build_page.py && python3 qa/stock/test_stock_datago.py

Starts the mock on 127.0.0.1:$SDG_MOCK_PORT (default 9002; agents use 9000–9009), Chrome, then stops the mock.
Checks: lazy load (only near the viewport, once per stock), what each block shows vs the mock, neutral colour for 대차 증감, the
"모두 보기" panel (판만 자라요: the layout moves once, the plate grows; closing: plate first, layout after; reduced = instant), states
(loading · empty · 503 · 502 + 다시 시도 · stale · old-Worker 404 hides), footer order, 360/390/768/1440 no horizontal overflow, console
errors 0, touch targets ≥ 44px on phones, text ≥ 11px, no advice wording. Screenshots → qa/shots/stock_datago/ (git-ignored).
"""
import json, os, pathlib, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SHOTS = ROOT / 'qa/shots/stock_datago'
SHOTS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get('SDG_MOCK_PORT', '9002'))
BASE = f'http://127.0.0.1:{PORT}/'
VP = {
    360: dict(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True, device_scale_factor=2),
    390: dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    768: dict(viewport={'width': 768, 'height': 1024}),
    1440: dict(viewport={'width': 1440, 'height': 900}),
}
R, FAILS = {}, []


def check(name, ok, detail=None):
    R[name] = {'ok': bool(ok), 'detail': detail}
    print(('PASS ' if ok else 'FAIL ') + name + ('' if detail is None else '  ' + json.dumps(detail, ensure_ascii=False)[:400]), flush=True)
    if not ok:
        FAILS.append(name)


def mock(path):
    with urllib.request.urlopen(BASE + path.lstrip('/'), timeout=10) as r:
        return json.loads(r.read())


class Page:
    def __init__(self, b, w, motion=None, tab='info'):
        self.ctx = b.new_context(**VP[w])
        self.pg = self.ctx.new_page()
        self.console, self.reqs, self.ign, self.allow404 = [], [], 0, 0
        # the heatmap's own 404s the mock does not serve (data/close.json, api/breadth) are not this page's (as in test_stock.py)
        self.pg.on('response', lambda r: setattr(self, 'ign', self.ign + 1) if r.status == 404 and ('/data/close.json' in r.url or '/api/breadth' in r.url) else None)
        self.pg.on('console', self._console)
        self.pg.on('pageerror', lambda e: self.console.append(f'pageerror: {e}'))
        self.pg.on('request', lambda r: self.reqs.append(r.url))
        init = f"localStorage.setItem('khm.stockTab', JSON.stringify('{tab}'));"
        if motion:
            init += f"localStorage.setItem('khm.motion', JSON.stringify('{motion}'));"
        self.pg.add_init_script(init)

    def _console(self, m):
        if m.type not in ('error', 'warning'):
            return
        if m.type == 'error' and 'Failed to load resource' in m.text and (self.ign > 0 or self.allow404 > 0):
            if self.ign > 0:
                self.ign -= 1
            else:
                self.allow404 -= 1
            return
        self.console.append(f'{m.type}: {m.text}')

    def count(self, frag):
        return sum(1 for u in self.reqs if frag in u)

    def open(self, code='005930'):
        self.pg.goto(BASE + '#s-' + code)
        self.pg.wait_for_selector('#sp-p-info:not([hidden]) .sp-ci-met .sp-m')
        self.pg.wait_for_timeout(700)

    def ev(self, js, arg=None):
        return self.pg.evaluate(js, arg) if arg is not None else self.pg.evaluate(js)

    def to(self, sel, block='start'):
        self.ev("([s, b]) => { const e = document.querySelector(s); if (e) e.scrollIntoView({block: b}); }", [sel, block])
        self.pg.wait_for_timeout(600)

    def close(self):
        self.ctx.close()


BLOCKS_JS = r"""() => {
  const P = document.getElementById('sp-p-info'), q = (s, r = P) => r.querySelector(s), qa = (s, r = P) => [...r.querySelectorAll(s)];
  const L = q('.sp-ci-lend'), D = q('.sp-dvx'), C = q('.sp-ci-corp');
  const txt = e => (e ? e.textContent.trim() : '');
  return {
    lend: { hidden: L.hidden, v: txt(q('.sp-lb-v b', L)), chg: txt(q('.sp-lb-v .chg', L)), kv: qa('.sp-lb-kv > div', L).map(d => [txt(q('dt', d)), txt(q('dd', d))]),
      fig: !!q('.sp-lb-fig', L), pts: (q('.sp-lb-fig .ln', L) || { getAttribute: () => '' }).getAttribute('d').split(/[ML]/).filter(Boolean).length,
      label: (q('.sp-lb-fig', L) || { getAttribute: () => '' }).getAttribute('aria-label'), x: qa('.sp-lb-x span', L).map(txt), src: txt(q('.sp-sdg-src', L)),
      msg: txt(q('.sp-msgbox', L)), retry: !!q('.sp-msgbox .sp-btn', L), wait: q('.sp-sdg-wait', L) ? q('.sp-sdg-wait', L).getAttribute('aria-label') : null,
      upDn: qa('.up, .dn', L).length },
    div: { hidden: D.hidden, h: txt(q('.sp-dvx-h', D)), rows: qa('tbody tr', D).map(r => qa('td', r).map(txt)), head: qa('thead th', D).map(txt),
      note: txt(q('.sp-note', D)), src: txt(q('.sp-sdg-src', D)), empty: txt(q('.sp-dvx-empty', D)), err: txt(q('.sp-inline-err', D)), retry: !!q('.sp-btn', D),
      wait: q('.sp-sdg-wait', D) ? q('.sp-sdg-wait', D).getAttribute('aria-label') : null },
    corp: { hidden: C.hidden, kv: qa('.sp-cp-kv > div', C).map(d => [txt(q('dt', d)), txt(q('dd', d))]), link: (q('.sp-cp-link', C) || {}).href || null,
      secs: qa('.sp-cp-sec', C).map(s => ({ h: txt(q('.sp-cp-h', s)), n: qa('.sp-cp-names li', s).length, tags: qa('.sp-cp-names .sp-tag', s).length,
        more: txt(q('.sp-cp-more', s)), exp: (q('.sp-cp-more', s) || { getAttribute: () => null }).getAttribute('aria-expanded') })),
      src: txt(q('.sp-sdg-src', C)), msg: txt(q('.sp-msgbox', C)), retry: !!q('.sp-msgbox .sp-btn', C), wait: q('.sp-sdg-wait', C) ? q('.sp-sdg-wait', C).getAttribute('aria-label') : null },
  };
}"""

OVERFLOW_JS = r"""() => {
  const root = document.getElementById('kh-stock'), vw = innerWidth, out = [];
  for (const el of root.querySelectorAll('.sp-ci-lend *, .sp-dvx *, .sp-ci-corp *')) {
    if (el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > vw + 0.5 || r.left < -0.5)) out.push(`${el.tagName.toLowerCase()}.${String(el.className.baseVal ?? el.className).split(' ')[0]} ${Math.round(r.left)}..${Math.round(r.right)}`);
  }
  return { doc: document.documentElement.scrollWidth - innerWidth, root: root.scrollWidth - root.clientWidth, els: out.slice(0, 5), n: out.length };
}"""

TAP_JS = r"""() => {
  const small = [];
  for (const el of document.querySelectorAll('#sp-p-info :is(.sp-ci-lend, .sp-dvx, .sp-ci-corp) :is(button, a)')) {
    if (el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    const b = getComputedStyle(el, '::before'), ph = b.content !== 'none' && b.position === 'absolute' ? parseFloat(b.height) || 0 : 0;
    const hgt = Math.max(r.height, ph);
    if (hgt < 44 || r.width < 44) small.push(`${el.className || el.tagName}:${el.textContent.trim().slice(0, 12)} ${Math.round(r.width)}x${Math.round(hgt)}`);
  }
  return small;
}"""

FONT_JS = r"""() => {
  const small = [];
  for (const el of document.querySelectorAll('#sp-p-info :is(.sp-ci-lend, .sp-dvx, .sp-ci-corp) *')) {
    if (el.closest('[hidden]') || el.closest('.sp-vh') || !el.childNodes.length) continue;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 11) small.push(`${el.className}:${fs}`);
  }
  return small;
}"""


def shares_text(v, signed=False):
    sg = ('+' if v > 0 else '−' if v < 0 else '') if signed else ('−' if v < 0 else '')
    a = abs(v)
    def fmt(x, d):
        s = f'{x:,.{d}f}'
        return s.rstrip('0').rstrip('.') if '.' in s else s
    if a >= 1e8:
        return sg + fmt(a / 1e8, 2) + '억 주'
    if a >= 1e4:
        return sg + fmt(a / 1e4, 0 if a >= 1e6 else 1) + '만 주'
    return sg + f'{round(a):,}' + '주'


def run(b):
    mock('/__reset')
    L5, D5, C5 = mock('/api/stock/005930/lending'), mock('/api/stock/005930/dividend'), mock('/api/stock/005930/corp')
    mock('/__reset')

    # ── lazy: another tab → nothing; 종목 정보 → only what is near the viewport; scrolling brings the rest, once ──
    P = Page(b, 390, tab='ob')
    P.pg.goto(BASE + '#s-005930'); P.pg.wait_for_selector('.sp-ob-grid, #sp-p-ob .sp-msgbox'); P.pg.wait_for_timeout(800)
    other = P.count('/lending') + P.count('/corp') + P.count('/dividend')
    P.pg.click('#sp-t-info'); P.pg.wait_for_selector('#sp-p-info .sp-ci-met .sp-m'); P.pg.wait_for_timeout(800)
    first = {k: P.count('/' + k) for k in ('lending', 'dividend', 'corp')}
    P.to('.sp-ci-lend'); P.pg.wait_for_selector('.sp-ci-lend .sp-lb-v b')
    P.to('.sp-ci-corp'); P.pg.wait_for_selector('.sp-ci-corp .sp-cp-kv')
    P.to('.sp-dvx', 'center'); P.pg.wait_for_selector('.sp-dvx tbody tr')
    after = {k: P.count('/' + k) for k in ('lending', 'dividend', 'corp')}
    P.pg.click('#sp-t-inv'); P.pg.wait_for_timeout(300); P.pg.click('#sp-t-info'); P.pg.wait_for_timeout(600)
    P.to('.sp-ci-corp')
    again = {k: P.count('/' + k) for k in ('lending', 'dividend', 'corp')}
    check('lazy_only_near_viewport', other == 0 and first['lending'] == 0 and first['corp'] == 0 and after == {'lending': 1, 'dividend': 1, 'corp': 1} and again == after,
          {'other_tab': other, 'tab_open': first, 'scrolled': after, 'tab_again': again})

    # ── what each block shows ──
    x = P.ev(BLOCKS_JS)
    lt = L5['latest']
    want_chg = f"전 영업일보다 {shares_text(lt['change'], True)} ({'+' if lt['ratio'] > 0 else '−'}{abs(lt['ratio']):.2f}%)"
    check('lend_value_change_kv', x['lend']['v'] == shares_text(lt['shares']) and x['lend']['chg'] == want_chg
          and [k for k, _ in x['lend']['kv']] == ['잔고 금액', '그날 빌려줌', '그날 갚음'] and x['lend']['kv'][0][1].endswith('조원'),
          {'v': x['lend']['v'], 'chg': x['lend']['chg'], 'want': want_chg, 'kv': x['lend']['kv']})
    check('lend_line_60_days', x['lend']['fig'] and x['lend']['pts'] == len(L5['rows']) == 60 and x['lend']['x'][0] and x['lend']['x'][-1] == '11월 13일'
          and '60영업일' in (x['lend']['label'] or ''), {'pts': x['lend']['pts'], 'x': x['lend']['x'], 'label': (x['lend']['label'] or '')[:80]})
    neutral = P.ev("""() => { const c = document.querySelector('.sp-lb-v .chg'), p = document.createElement('span'); p.style.color = 'var(--fg2)'; c.parentNode.append(p);
      const r = [getComputedStyle(c).color, getComputedStyle(p).color, getComputedStyle(document.querySelector('.sp-lb-fig .ln')).stroke]; p.remove(); return r; }""")
    up_dn = P.ev("() => { const s = getComputedStyle(document.getElementById('kh-stock')); return [s.getPropertyValue('--up-text').trim(), s.getPropertyValue('--dn-text').trim()]; }")
    check('lend_change_is_neutral', neutral[0] == neutral[1] and x['lend']['upDn'] == 0, {'chg': neutral[0], 'fg2': neutral[1], 'line': neutral[2], 'up/dn': up_dn})
    src_ok = lambda s, lead: '금융위원회 · 공공데이터포털, 하루 한 번' in s and lead in s
    check('every_block_has_date_and_source', src_ok(x['lend']['src'], '11월 13일 (금) 기준') and src_ok(x['div']['src'], '11월 13일 (금) 자료') and src_ok(x['corp']['src'], '11월 13일 (금) 공개 자료'),
          [x['lend']['src'], x['div']['src'], x['corp']['src']])
    r0 = D5['rows'][0]
    check('dividend_table', x['div']['head'] == ['기준일', '지급일', '1주당'] and len(x['div']['rows']) == 8
          and x['div']['rows'][0] == [r0['recordDate'].replace('-', '.'), r0['payDate'].replace('-', '.'), f"{r0['amount']:,}원"]
          and '배당 기준일은 금융위원회 자료 기준' in x['div']['note'] and '배당 내역' in x['div']['h'], {'rows': x['div']['rows'][:2], 'note': x['div']['note']})
    o = C5['outline']
    kv = dict(x['corp']['kv'])
    check('corp_key_values', kv.get('대표자') == o['ceo'] and kv.get('설립일') == '1969년 1월 13일' and kv.get('종업원 수') == '125,000명' and kv.get('상장일') == '1975년 6월 11일'
          and kv.get('업종') == o['industry'] and kv.get('홈페이지', '').startswith('www.samsung.com') and x['corp']['link'] == o['homepage'], x['corp']['kv'])
    s0, s1 = x['corp']['secs']
    check('corp_lists_collapsed', s0['h'].startswith('계열회사') and '63개' in s0['h'] and s0['n'] == 8 and s0['tags'] == 8 and s0['more'] == '계열회사 63개 모두 보기' and s0['exp'] == 'false'
          and s1['h'].startswith('종속기업') and '232개' in s1['h'] and s1['n'] == 8 and s1['more'] == '종속기업 232개 모두 보기', x['corp']['secs'])
    P.pg.screenshot(path=str(SHOTS / 'live390_info_sdg.png'))

    # ── 모두 보기: the plate grows (open), the content below moved once at the start; closing: plate first, layout after ──
    P.to('.sp-ci-corp .sp-cp-sec')
    probe = P.ev("""() => new Promise(res => {
      const sec = document.querySelector('.sp-ci-corp .sp-cp-sec'), grow = sec.querySelector('.sp-cp-grow'), skin = sec.querySelector('.sp-cp-skin'), next = sec.nextElementSibling;
      const h0 = grow.offsetHeight, n0 = next.getBoundingClientRect().top, frames = [];
      sec.querySelector('.sp-cp-more').click();
      const t0 = performance.now();
      (function f() {
        frames.push([Math.round(performance.now() - t0), Math.round(skin.getBoundingClientRect().height), Math.round(next.getBoundingClientRect().top - n0), grow.classList.contains('sp-cp-anim')]);
        if (performance.now() - t0 < 700) requestAnimationFrame(f); else res({ h0, h1: grow.offsetHeight, frames, li: sec.querySelectorAll('li').length, exp: sec.querySelector('.sp-cp-more').getAttribute('aria-expanded'), lbl: sec.querySelector('.sp-cp-more').textContent });
      })();
    })""")
    fr = probe['frames']
    mid = [f for f in fr if f[3] and 20 < f[0] < 250]
    moved_once = all(f[2] == fr[0][2] for f in fr)
    grows = len(mid) >= 2 and mid[0][1] < probe['h1'] - 2 and all(b[1] >= a[1] - 1 for a, b in zip(mid, mid[1:]))
    check('more_open_plate_grows_layout_moves_once', probe['li'] == 63 and probe['exp'] == 'true' and probe['lbl'] == '접기' and moved_once and grows and fr[-1][1] == probe['h1'] and not fr[-1][3],
          {'h0': probe['h0'], 'h1': probe['h1'], 'frames': fr[:3] + fr[-2:], 'mid_n': len(mid)})
    probe2 = P.ev("""() => new Promise(res => {
      const sec = document.querySelector('.sp-ci-corp .sp-cp-sec'), grow = sec.querySelector('.sp-cp-grow'), skin = sec.querySelector('.sp-cp-skin'), next = sec.nextElementSibling;
      const n0 = next.getBoundingClientRect().top, frames = [];
      sec.querySelector('.sp-cp-more').click();
      const t0 = performance.now();
      (function f() {
        frames.push([Math.round(performance.now() - t0), Math.round(skin.getBoundingClientRect().height), Math.round(next.getBoundingClientRect().top - n0)]);
        if (performance.now() - t0 < 800) requestAnimationFrame(f); else res({ frames, li: sec.querySelectorAll('li').length, exp: sec.querySelector('.sp-cp-more').getAttribute('aria-expanded'), focus: document.activeElement === sec.querySelector('.sp-cp-more') });
      })();
    })""")
    f2 = probe2['frames']
    held = [f for f in f2 if f[0] < 150]
    check('more_close_plate_first_then_layout', probe2['li'] == 8 and probe2['exp'] == 'false' and all(f[2] == 0 for f in held) and f2[-1][2] < 0,
          {'early': held[:2], 'end': f2[-1], 'li': probe2['li']})
    P.pg.click('.sp-ci-corp .sp-cp-sec .sp-cp-more'); P.pg.wait_for_timeout(700)
    P.pg.screenshot(path=str(SHOTS / 'live390_corp_open.png'), full_page=False)
    check('console_clean_390', not P.console, P.console)
    P.close()

    # reduced: the list jumps open, no plate animation
    P = Page(b, 390, motion='reduced')
    P.open(); P.to('.sp-ci-corp'); P.pg.wait_for_selector('.sp-ci-corp .sp-cp-more')
    rd = P.ev("""() => { const sec = document.querySelector('.sp-ci-corp .sp-cp-sec'); sec.querySelector('.sp-cp-more').click();
      return [sec.querySelectorAll('li').length, sec.querySelector('.sp-cp-grow').classList.contains('sp-cp-anim'), document.documentElement.dataset.motion]; }""")
    check('more_reduced_is_instant', rd[0] == 63 and not rd[1], rd)
    P.close()

    # ── states ──
    def state(mode, code='005930', w=390, extra=''):
        mock('/__reset'); mock(f'/__config?sdg={mode}{extra}')
        P = Page(b, w)
        if mode in ('gone', 'nf'):
            P.allow404 = 3
        P.open(code)
        P.to('.sp-ci-lend'); P.to('.sp-dvx', 'center'); P.to('.sp-ci-corp')
        P.pg.wait_for_timeout(500)
        return P, P.ev(BLOCKS_JS)

    P, e = state('empty')
    check('state_empty', '최근 대차잔고 기록이 없어요' in e['lend']['msg'] and '기록이 없어요' in e['div']['empty'] and '기업 정보가 없어요' in e['corp']['msg']
          and all(e[k]['src'] for k in ('lend', 'div', 'corp')), {k: [e[k].get('msg') or e[k].get('empty'), e[k]['src'][:20]] for k in e})
    check('console_clean_empty', not P.console, P.console); P.close()

    P, e = state('wait')
    check('state_503_wait', '아직 받는 중이에요' in e['lend']['msg'] and e['lend']['retry'] and '아직 받는 중이에요' in e['div']['err'] and e['div']['retry'] and '아직 받는 중이에요' in e['corp']['msg'],
          {k: e[k].get('msg') or e[k].get('err') for k in e})
    P.close()

    P, e = state('fail')
    ok1 = '대차잔고를 불러오지 못했어요' in e['lend']['msg'] and e['lend']['retry'] and '불러오지 못했어요' in e['div']['err'] and '기업 정보를 불러오지 못했어요' in e['corp']['msg']
    mock('/__config?sdg=ok')
    P.to('.sp-ci-lend'); P.pg.click('.sp-ci-lend .sp-msgbox .sp-btn'); P.pg.wait_for_selector('.sp-ci-lend .sp-lb-v b', timeout=5000)
    check('state_fail_then_retry', ok1 and P.ev("() => !!document.querySelector('.sp-ci-lend .sp-lb-fig')"), {k: e[k].get('msg') or e[k].get('err') for k in e})
    P.close()

    P, e = state('stale')
    check('state_stale_says_old', all('지난 자료예요' in e[k]['src'] for k in ('lend', 'div', 'corp')) and e['lend']['v'], [e[k]['src'] for k in e])
    P.close()

    P, e = state('gone')
    check('old_worker_404_hides_blocks', e['lend']['hidden'] and e['div']['hidden'] and e['corp']['hidden'] and not [m for m in P.console if '404' not in m], {k: e[k]['hidden'] for k in e})
    P.close()
    P, e = state('nf')
    check('no_info_404_hides_blocks', e['lend']['hidden'] and e['div']['hidden'] and e['corp']['hidden'], {k: e[k]['hidden'] for k in e})
    P.close()

    mock('/__reset'); mock('/__config?sdgdelay=2500')
    P = Page(b, 390); P.open(); P.to('.sp-ci-lend'); P.pg.wait_for_timeout(150)
    e = P.ev(BLOCKS_JS)
    check('state_loading_skeleton', e['lend']['wait'] == '대차잔고 불러오는 중', e['lend']['wait'])
    P.close()
    mock('/__reset')

    # ── 999980 (empty everything) and a smaller company: short lists without "모두 보기" ──
    P = Page(b, 390); P.open('000660'); P.to('.sp-ci-corp'); P.pg.wait_for_selector('.sp-ci-corp .sp-cp-kv')
    e = P.ev(BLOCKS_JS)
    short = [s for s in e['corp']['secs'] if s['n'] <= 8 and not s['more']]
    check('short_lists_no_more_key', len(short) >= 1, e['corp']['secs'])
    P.close()

    # ── footer: 금융위원회 line, and 투자 판단… stays the last line ──
    P = Page(b, 390); P.open()
    ft = P.ev("() => { const f = document.querySelector('.sp-foot'); return [[...f.children].map(p => p.className + '|' + p.textContent), f.lastElementChild.classList.contains('sp-disclaim')]; }")
    check('footer_disclaim_last', ft[1] and ft[0][-1].endswith('투자 판단의 근거로 쓰지 마세요.') and any('금융위원회(공공데이터포털)' in x for x in ft[0][:-1]), ft[0])
    P.close()

    # ── widths: everything open, no overflow, console clean, touch ≥ 44 on phones, text ≥ 11px, no advice words ──
    bad = {}
    for w in (360, 390, 768, 1440):
        P = Page(b, w); P.open()
        if w == 1440:   # the side card scrolls on its own here: the blocks load when it is scrolled near them
            P.ev("() => { const p = document.getElementById('sp-p-info'); p.scrollTop = p.scrollHeight; }"); P.pg.wait_for_timeout(900)
        P.to('.sp-ci-lend'); P.to('.sp-dvx', 'center'); P.to('.sp-ci-corp')
        P.pg.wait_for_selector('.sp-ci-corp .sp-cp-more')
        for i in range(2):
            P.ev(f"() => document.querySelectorAll('.sp-ci-corp .sp-cp-more')[{i}].click()"); P.pg.wait_for_timeout(700)
        o = P.ev(OVERFLOW_JS)
        taps = P.ev(TAP_JS) if w <= 390 else []
        fonts = P.ev(FONT_JS)
        txt = P.ev("() => [...document.querySelectorAll('.sp-ci-lend, .sp-dvx, .sp-ci-corp')].map(e => e.textContent).join(' ')")
        words = [x for x in ('추천', '사세요', '팔세요', '저평가', '고평가', '상승 여력', '기회', '매수 신호', '매도 신호') if x in txt]
        if o['doc'] or o['root'] or o['n'] or taps or fonts or words or P.console:
            bad[w] = {'o': o, 'taps': taps[:4], 'fonts': fonts[:4], 'words': words, 'console': P.console[:3]}
        P.to('.sp-ci-lend')
        P.pg.screenshot(path=str(SHOTS / f'live{w}_lend.png'))
        P.to('.sp-ci-corp')
        P.pg.screenshot(path=str(SHOTS / f'live{w}_corp.png'))
        P.close()
    check('widths_no_overflow_console_touch_font_words', not bad, bad or None)


def main():
    env = dict(os.environ)
    proc = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), '--port', str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:   # noqa: BLE001
                time.sleep(0.1)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            try:
                run(b)
            finally:
                b.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    n = len(R)
    print(f'\nstock datago page: {n - len(FAILS)}/{n} passed' + (f'  FAIL: {", ".join(FAILS)}' if FAILS else ''))
    (HERE / 'results_datago.json').write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding='utf-8')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
