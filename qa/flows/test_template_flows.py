#!/usr/bin/env python3
"""가족 보기 · 오늘 잠정 on the heatmap (AGENTS §3-40, feat/flows-template — src/template.html only).

  python3 qa/flows/test_template_flows.py [public] [invite] [map] [owner] [cadence] [layout]      (no argument = all)

Builds web/ + dist/ (scripts/build_page.py) and serves web/ with qa/flows/mock_template_flows.py on FLOWS_TPL_PORT (default 9090; 9090–9094) —
synthetic invites and /api/flows/live in the contract's shape. The page's clock is pinned to a weekday 10:00 KST (Playwright
set_fixed_time + /api/time answering it), the mock's "today" = that day.
public   a device without a token, 360 · 1280 · 1440, phones' sheet and the 화면 popover opened: no 가족 보기 DOM, no 오늘 key, no request
         to /api/inv* or /api/flows/live; a stored flowWin 0 becomes 1 (saved); KH.inv.fetch refuses locally (nothing sent); the snapshot
         (file://) leaves #inv= alone.
invite   #inv=<token>&<rest> / ~<rest>: stored (khm.inv), the address keeps only the rest (the tab it names opens), GET /api/inv/me with the
         header → name · own, the welcome bubble; a malformed token is dropped from the address and not stored; #inv= pasted into an open
         page; 403 → forgotten (kh:inv {has:false}, the section and the 오늘 key gone); no answer (aborted / 503) → kept, asked again on
         'online'; a 403 from /api/flows/live forgets too; a family token's 403 on an owner route forgets nothing.
map      오늘 잠정: the first 순매수 기간 key with its 잠정 tag; tiles = est × the price drawn ÷ 1e8 (text, colour on the 1일 range, size —
         시총순 so areas are comparable), codes without est left out; 외국인 · 기관; legend · footer · 섹터 card · table column · tooltip read
         "오늘 잠정" and "14:30 입력분 · 한국투자증권 가집계 · 금액은 수량 × 지금 가격"; slot null and a payload from another day → "오늘 첫 입력
         (09:30) 뒤에 보여요" on a weekday 09:00–10:00 only; no session (a weekend, before 09:00, closed:true, no round by 10:00) → 1일 drawn,
         0 kept, polled again only on weekdays (back to 오늘 once a round is in); round 1 + 기관 → "기관은 10:00 입력분부터 보여요"; the evening
         file (flows.json asOf today) → no 오늘 key, 1일 drawn, 0 kept; a page left open past 21:00 reads flows.json again (once the card has
         the new file, or every 10 min) and steps aside; forget → 1 saved; #khm-import= never carries khm.inv; 503s never forget the token.
owner    가족 초대 only for own(): the list on opening (GET /api/inv once a minute at most), 만들기 → POST {n} → the link once
         (${origin}/#inv=…, 복사 → the clipboard, 공유 only with navigator.share), the list grows; 끄기 arms then DELETEs (the owner's row
         has none); 이 기기에서 끄기 arms then forgets (no more gated requests); a family token sees no 가족 초대 and asks no /api/inv.
cadence  KH.flowsLive: one fetcher (two wants → one request), polls only while wanted and seen; weekday 10:00 / 15:49 → 60 s,
         15:50 · Saturday → 10 min, 09:20 → wakes at 09:25; data() null for another day.
layout   4 themes × 360 · 1280 with the owner's section at its fullest (link + list): nothing past the screen edge, nothing wider than its
         panel, console errors 0; map top (390 × 844: 247 · 1280 / 1440: 207) with and without a token.
Exit 1 on a fail. The port is stopped with fuser -k.
"""
import base64
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('FLOWS_TPL_PORT', 9090))
assert 9090 <= PORT <= 9094, 'ports 9090–9094 (FLOWS_TPL_PORT)'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OWNER = 'own_' + 'a' * 28
FAMILY = 'fam_' + 'b' * 28
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
KST = timezone(timedelta(hours=9))
DAY = '2026-11-23'                                   # a Monday
T10 = datetime(2026, 11, 23, 10, 0, tzinfo=KST)
FAILS, PASSES = [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


def api(path):
    return json.loads(NOPROXY.open(URL + path.lstrip('/'), timeout=5).read())


def mode(**kw):
    return api('__mode?' + '&'.join(f'{k}={v}' for k, v in kw.items()))


def reset():
    api('__reset'); mode(today=DAY)


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/flows/mock_template_flows.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


GATED = re.compile(r'/api/(inv|flows/live)')


class Page:
    """a context + page with the clock pinned, localStorage seeded, console errors and gated requests recorded"""
    def __init__(self, br, w=1440, h=900, at=T10, theme='base', st=None, inv=None, hash_='', perms=False, init='', flow=False):
        mobile = w <= 760
        self.ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
        if perms:
            self.ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=URL.rstrip('/'))
        ms = int(at.timestamp() * 1000)
        self.ctx.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'t': ms})))
        s = {'theme': theme, 'motion': 'standard', 'tickerPaused': True, 'market': 'K'}
        s.update(st or {})
        js = ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in s.items())
        if inv:
            js += f"localStorage.setItem('khm.inv', {json.dumps(json.dumps(inv))});"
        # seed once: a reload keeps what the page itself wrote (a forgotten token stays forgotten)
        self.ctx.add_init_script("try{if(!sessionStorage.getItem('qa.seeded')){sessionStorage.setItem('qa.seeded','1');" + js + "}}catch(e){}" + init)
        self.pg = self.ctx.new_page()
        if flow:
            self.pg.clock.install(time=at)          # time flows (fast_forward jumps it); else pinned
        else:
            self.pg.clock.set_fixed_time(at)
        self.errs, self.gated, self.hdr, self.files = [], [], [], []
        self.pg.on('console', lambda m: self.errs.append(m.text[:200]) if m.type == 'error' else None)
        self.pg.on('pageerror', lambda e: self.errs.append('pageerror: ' + str(e)[:200]))
        self.pg.on('request', self._req)
        self.pg.goto(URL + hash_)
        self.pg.wait_for_timeout(2200)

    def _req(self, r):
        if 'data/flows.json' in r.url:
            self.files.append(r.url)
        if GATED.search(r.url):
            self.gated.append(f'{r.method} {r.url.split(str(PORT), 1)[-1]}')
            self.hdr.append(r.headers.get('x-panse-inv'))

    def ev(self, js, arg=None):
        return self.pg.evaluate(js, arg) if arg is not None else self.pg.evaluate(js)

    def close(self):
        self.ctx.close()


OVER = r"""() => {
  const vw = innerWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break; } p = p.parentElement; }
    if (!clipped && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).position !== 'fixed') out.push((e.id ? '#' + e.id : e.className && e.className.baseVal == null ? '.' + String(e.className).split(' ')[0] : e.tagName) + ' ' + Math.round(r.right));
  }
  return out.slice(0, 8);
}"""
# every element of the 가족 보기 section inside the section's box (and the section inside its panel)
INSIDE = r"""() => {
  const s = document.querySelector('.famset'); if (!s) return { missing: true };
  const R = s.getBoundingClientRect(), P = s.parentElement.getBoundingClientRect(), out = [];
  for (const e of s.querySelectorAll('*')) { const r = e.getBoundingClientRect(); if (!r.width) continue; if (r.left < R.left - 1 || r.right > R.right + 1) out.push(e.className + ' ' + Math.round(r.left) + '–' + Math.round(r.right)); }
  return { out: out.slice(0, 6), sec: [Math.round(R.left), Math.round(R.right)], panel: [Math.round(P.left), Math.round(P.right)], scroll: s.scrollWidth - s.clientWidth };
}"""
MAPTOP = "() => Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY)"
OPEN_SETTINGS = """() => { const b = document.getElementById('setBtn'), m = document.getElementById('moreBtn');
  if (b && b.offsetParent) { if (b.getAttribute('aria-expanded') !== 'true') b.click(); return 'sheet'; }
  if (m && m.getAttribute('aria-expanded') !== 'true') m.click(); return 'more'; }"""
FAMSTATE = """() => { const s = document.querySelector('.famset');
  return { has: KH.inv.has(), n: KH.inv.name(), own: KH.inv.own(), sec: !!s, home: s ? (s.parentElement.id || s.parentElement.className) : null,
    me: s ? s.querySelector('.famn').textContent : null, inv: s ? !s.querySelector('.faminv').hidden : null,
    stored: localStorage.getItem('khm.inv'), opt: !!document.querySelector('.seg[data-key="flowWin"] button[data-v="0"]'), hash: location.hash }; }"""


# ───────────────────────── public ─────────────────────────
def public(br):
    reset()
    for w, h in ((360, 740), (1280, 800), (1440, 900)):
        p = Page(br, w, h, st={'sizeBy': 'fgn', 'flowWin': 0})
        p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(500)
        g = p.ev("""() => ({ fam: document.querySelectorAll('.famset,.famk,.faminv,.fwtag').length, keys: [...document.querySelectorAll('.seg[data-key="flowWin"] button')].map(b => b.dataset.v),
          has: KH.inv.has(), own: KH.inv.own(), n: KH.inv.name(), win: localStorage.getItem('khm.flowWin'), ddv: document.querySelector('.ctl[data-ctl="flowWin"] .ddv').textContent,
          html: document.body.innerText.includes('가족 보기') || document.body.innerText.includes('잠정') })""")
        check(f'public [{w}]: no 가족 보기 DOM, no 오늘 key (1 · 5 · 20), KH.inv.has() false; a stored flowWin 0 → 1 saved, no "가족 보기" / "잠정" anywhere',
              g['fam'] == 0 and g['keys'] == ['1', '5', '20'] and not g['has'] and not g['own'] and g['n'] is None and g['win'] == '1' and g['ddv'] == '1일' and not g['html'], g)
        r = p.ev("""async () => { const a = await KH.inv.fetch('api/flows/live'); const b = await KH.flowsLive.refresh(); KH.flowsLive.want('qa', true);
          await new Promise(r => setTimeout(r, 300)); const s = KH.flowsLive.status(); KH.flowsLive.want('qa', false);
          return { st: a.status, body: await a.text(), data: b, polling: s.polling, ready: await KH.inv.ready() }; }""")
        p.pg.wait_for_timeout(300)
        check(f'public [{w}]: KH.inv.fetch → a local 403 {{error:forbidden}}, refresh() → null, want() polls nothing, ready() → false; zero gated requests (page and mock)',
              r['st'] == 403 and 'forbidden' in r['body'] and r['data'] is None and not r['polling'] and r['ready'] is False and not p.gated, (r, p.gated))
        check(f'public [{w}]: console errors 0', not p.errs, p.errs)
        p.close()
    st = api('__stats')
    check('public: the mock saw no /api/inv* · /api/flows/live request', not any(GATED.search(k) for k in st), st)
    # the snapshot (file://): #inv= is left alone, nothing stored
    br_ctx = br.new_context(viewport={'width': 1280, 'height': 800})
    pg = br_ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto('file://' + str(ROOT / 'dist/index.html') + '#inv=' + FAMILY)
    pg.wait_for_timeout(1500)
    g = pg.evaluate("() => ({ hash: location.hash, stored: (() => { try { return localStorage.getItem('khm.inv'); } catch (e) { return 'n/a'; } })(), has: KH.inv.has(), sec: !!document.querySelector('.famset'), mode: KH.MODE })")
    check('public: the snapshot (file://) ignores #inv= — hash kept, nothing stored, no section', g['mode'] == 'snapshot' and g['hash'] == '#inv=' + FAMILY and g['stored'] in (None, 'n/a') and not g['has'] and not g['sec'] and not errs, (g, errs))
    br_ctx.close()


# ───────────────────────── invite ─────────────────────────
def invite(br):
    reset()
    BUBS = "new MutationObserver(m => { for (const r of m) for (const n of r.addedNodes) if (n.classList && n.classList.contains('kbub')) (window.__bub = window.__bub || []).push(n.textContent); }).observe(document, { childList: true, subtree: true });"
    p = Page(br, 1440, 900, hash_='#inv=' + FAMILY + '&kosdaq', init=BUBS)
    g = p.ev(FAMSTATE)
    tab = p.ev("() => KH.market()")
    bub = p.ev("() => window.__bub || []")
    check('invite: #inv=<token>&kosdaq → khm.inv stored (JSON), the address = #kosdaq (that tab opened), /api/inv/me with the header → 엄마 · not own',
          g['stored'] == json.dumps(FAMILY) and g['hash'] == '#kosdaq' and tab == 'Q' and g['has'] and g['n'] == '엄마' and g['own'] is False
          and 'GET /api/inv/me' in p.gated and all(x == FAMILY for x in p.hdr), (g, tab, p.gated))
    check('invite: the section (이 기기: 엄마) without 가족 초대, the 오늘 key, the welcome bubble "가족 보기를 켰어요 · 엄마"',
          g['sec'] and g['me'] == '엄마' and g['inv'] is False and g['opt'] and any('가족 보기를 켰어요' in b and '엄마' in b for b in bub), (g, bub))
    check('invite: a family token asks no owner route (GET /api/inv)', not any(x.startswith('GET /api/inv') and 'me' not in x for x in p.gated), p.gated)
    check('invite: console errors 0', not p.errs, p.errs)
    p.close()
    # ~ carries the rest too; a reload shows no bubble
    p = Page(br, 1440, 900, hash_='#inv=' + OWNER + '~world', init=BUBS)
    g = p.ev(FAMSTATE); tab = p.ev("() => KH.market()")
    check('invite: #inv=<token>~world → stored, address #world, the 해외 tab, own', g['stored'] == json.dumps(OWNER) and g['hash'] == '#world' and tab == 'world' and g['own'], (g, tab))
    p.pg.reload(); p.pg.wait_for_timeout(1800)
    bub = p.ev("() => (window.__bub || []).length")
    check('invite: a reload says nothing (the bubble is for a fresh link only)', bub == 0, bub)
    p.close()
    # malformed
    p = Page(br, 1440, 900, hash_='#inv=short&kospi')
    g = p.ev(FAMSTATE)
    check('invite: a malformed token is dropped from the address (#kospi kept) and not stored, no request', g['hash'] == '#kospi' and g['stored'] is None and not g['has'] and not p.gated, (g, p.gated))
    # pasted into an open page
    p.ev("() => { location.hash = '#inv=" + FAMILY + "'; }"); p.pg.wait_for_timeout(1200)
    g = p.ev(FAMSTATE)
    check('invite: #inv= pasted into an open page → stored, address cleaned, validated, the section and the 오늘 key appear',
          g['stored'] == json.dumps(FAMILY) and g['hash'] == '' and g['n'] == '엄마' and g['sec'] and g['opt'], g)
    p.close()
    # 403 → forgotten
    p = Page(br, 1440, 900, inv='zzz_' + 'c' * 28, init="document.addEventListener('kh:inv', e => { (window.__inv = window.__inv || []).push(e.detail); });")
    g = p.ev(FAMSTATE); evs = p.ev("() => window.__inv || []")
    check('invite: an unknown token → 403 → forgotten: khm.inv removed, has() false, no section, no 오늘 key, kh:inv {has:false}',
          not g['has'] and g['stored'] is None and not g['sec'] and not g['opt'] and evs and evs[-1] == {'has': False, 'n': None, 'own': False}, (g, evs))
    p.close()
    # no answer → kept, asked again (online)
    reset()
    # (the abort is routed before the page loads)
    ctx = br.new_context(viewport={'width': 1440, 'height': 900})
    ms = int(T10.timestamp() * 1000)
    ctx.route('**/api/time', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'t': ms})))
    ctx.route('**/api/inv/me', lambda r: r.abort())
    ctx.add_init_script("try{if(!sessionStorage.getItem('qa.s')){sessionStorage.setItem('qa.s','1');localStorage.setItem('khm.inv'," + json.dumps(json.dumps(FAMILY)) + ");localStorage.setItem('khm.tickerPaused','true');}}catch(e){}")
    pg = ctx.new_page(); pg.clock.set_fixed_time(T10)
    pg.goto(URL); pg.wait_for_timeout(2000)
    g = pg.evaluate(FAMSTATE)
    check('invite: no answer (aborted) → the token kept, has() true, the section says "이름을 아직 확인하지 못했어요", own() false',
          g['has'] and g['stored'] == json.dumps(FAMILY) and g['me'] == '이름을 아직 확인하지 못했어요' and not g['own'], g)
    ctx.unroute('**/api/inv/me')
    pg.evaluate("() => dispatchEvent(new Event('online'))"); pg.wait_for_timeout(800)
    g = pg.evaluate(FAMSTATE)
    check('invite: back online → asked again quietly → 엄마', g['has'] and g['n'] == '엄마' and g['me'] == '엄마', g)
    ctx.close()
    mode(me='fail')
    p = Page(br, 1440, 900, inv=FAMILY)
    g = p.ev(FAMSTATE); rd = p.ev("() => KH.inv.ready()")
    check('invite: /api/inv/me 503 → kept (ready() → true)', g['has'] and g['stored'] == json.dumps(FAMILY) and rd is True, g)
    p.close()
    mode(me='ok', live='403')
    p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    p.pg.wait_for_timeout(600)
    g = p.ev(FAMSTATE); win = p.ev("() => [localStorage.getItem('khm.flowWin'), document.querySelector('.ctl[data-ctl=\"flowWin\"] .ddv').textContent]")
    check('invite: a 403 from /api/flows/live forgets the token too; 오늘 → 1일 saved', not g['has'] and g['stored'] is None and not g['sec'] and win == ['1', '1일'], (g, win))
    p.close()
    mode(live='ok')
    p = Page(br, 1440, 900, inv=FAMILY)
    r = p.ev("async () => { const a = await KH.inv.fetch('api/inv'); await new Promise(r => setTimeout(r, 400)); return { st: a.status, has: KH.inv.has(), n: KH.inv.name() }; }")
    check('invite: a family token refused on an owner route (GET /api/inv 403) is not forgotten (re-checked: still 엄마)', r == {'st': 403, 'has': True, 'n': '엄마'}, r)
    mode(own='fail')
    r2 = p.ev("async () => { const a = await KH.inv.fetch('api/inv'); const b = await KH.inv.fetch('api/flows/live'); await new Promise(r => setTimeout(r, 300)); return { a: a.status, b: b.status, has: KH.inv.has() }; }")
    mode(own='ok')
    r = p.ev("async () => { const a = await KH.inv.fetch('https://example.com/api/flows/live'); return a.status; }")
    check('invite: 503s (an owner route on a KV error) never forget the token', r2 == {'a': 503, 'b': 200, 'has': True}, r2)
    check('invite: KH.inv.fetch to another site → a local 403, the header never leaves', r == 403 and not any('example.com' in x for x in p.gated), (r, p.gated))
    p.close()


# ───────────────────────── map ─────────────────────────
VALUES = r"""async ({who}) => {
  const est = await (await fetch('/__est')).json(), R = KH.range(), P = KH.palette().stops, ix = who === 'inst' ? 1 : 0;
  const sc = d3.scaleLinear().domain([-R, -R * 2 / 3, -R / 3, 0, R / 3, R * 2 / 3, R]).range(P).interpolate(d3.interpolateLab).clamp(true);
  const fmt = v => { const a = Math.abs(v), s = a < 0.5 ? '' : v > 0 ? '+' : v < 0 ? '−' : ''; const n = a >= 10000 ? new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(a / 10000) + '조' : new Intl.NumberFormat('ko-KR').format(Math.round(a)) + '억'; return s + n; };
  const tiles = KH.layout().filter(n => n.kind === 'tile'), bad = [], noEst = [];
  for (const t of tiles) {
    const s = KH.stock(t.code), e = est[t.code];
    if (!e) { noEst.push(t.code); continue; }
    const a = e[ix] * s.p / 1e8, col = a === 0 ? P[3] : sc(a / s.cap * 100);
    if (t.sub !== fmt(a) || d3.color(t.color).formatHex() !== d3.color(col).formatHex()) bad.push([t.code, t.sub, fmt(a), t.color, col]);
  }
  // sizes (시총순: one strip treemap, area ∝ |amount| — 1px gaps aside): the biggest tiles against each other
  const big = tiles.filter(t => est[t.code]).map(t => ({ c: t.code, area: t.w * t.h, a: Math.abs(est[t.code][ix] * KH.stock(t.code).p / 1e8) })).sort((x, y) => y.a - x.a).slice(0, 8);
  const ratio = big.slice(1).map(b => (b.area / big[0].area) / (b.a / big[0].a));
  const missing = Object.keys(est).length, streamed = KH.stocks().filter(s => s.m === 'K').length;
  return { n: tiles.length, bad: bad.slice(0, 4), noEst, ratio, R };
}"""
TEXTS = r"""() => {
  const q = s => (document.querySelector(s) || {}).textContent || '';
  return { legend: q('#legend'), foot: q('#foot'), sec: q('#secTitle'), ddv: q('.ctl[data-ctl="flowWin"] .ddv'), empty: q('.map-empty'), win: localStorage.getItem('khm.flowWin'),
    keys: [...document.querySelectorAll('.seg[data-key="flowWin"] button')].map(b => b.dataset.v + ':' + b.textContent), pressed: (document.querySelector('.seg[data-key="flowWin"] button[aria-pressed="true"]') || {}).dataset?.v,
    tag: (() => { const t = document.querySelector('.seg[data-key="flowWin"] button[data-v="0"] .fwtag'); return t ? [t.textContent, getComputedStyle(t).fontSize] : null; })(),
    dist: q('#wavgLab') + ' ' + q('#breadthScope') };
}"""


def map_checks(br):
    reset()
    for who, name in (('fgn', '외국인'), ('inst', '기관')):
        p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': who, 'flowWin': 0, 'groupBy': 'cap'})
        p.pg.wait_for_timeout(500)
        v = p.ev(VALUES, {'who': who}); t = p.ev(TEXTS)
        check(f'map [{name}]: 오늘 잠정 = the first 순매수 기간 key (+ 잠정 tag, 11px), pressed, saved 0, the key reads "오늘 잠정"',
              t['keys'][0] == '0:오늘잠정' and t['pressed'] == '0' and t['win'] == '0' and t['ddv'] == '오늘 잠정' and t['tag'] == ['잠정', '11px'], t)
        check(f'map [{name}]: {v["n"]} tiles — text and colour = est × price ÷ 1e8 on the 1일 range (±{v["R"]}%); codes without est left out',
              v['n'] > 100 and not v['bad'] and not v['noEst'] and v['R'] == 0.3, v)
        check(f'map [{name}]: tile areas ∝ |amount| (8 biggest, 시총순 strip: within 6 %)', v['ratio'] and all(abs(x - 1) < 0.06 for x in v['ratio']), v['ratio'])
        check(f'map [{name}]: legend "{name} 순매수 금액 · 오늘 잠정 · 14:30 입력분 · 한국투자증권 가집계 · 금액은 수량 × 지금 가격", footer, 섹터 card "오늘 잠정"',
              f'{name} 순매수 금액오늘 잠정' in t['legend'] and '14:30 입력분 · 한국투자증권 가집계 · 금액은 수량 × 지금 가격' in t['legend']
              and '오늘 잠정 순매수는 한국투자증권 가집계 14:30 입력분' in t['foot'] and f'{name} 오늘 잠정' in t['sec'], t)
        if who == 'fgn':
            # the tooltip's metric row, the table column
            tip = p.ev("""() => { const t = document.querySelector('#map .tile'); t.dispatchEvent(new PointerEvent('pointerover', { bubbles: true, pointerType: 'mouse' }));
              t.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: t.getBoundingClientRect().left + 10, clientY: t.getBoundingClientRect().top + 10 })); return null; }""")
            p.pg.hover('#map .tile >> nth=0'); p.pg.wait_for_timeout(500)
            tip = p.ev("() => (document.querySelector('#tip .mrow') || {}).textContent || ''")
            check('map: the tooltip says "외국인 오늘 잠정 순매수 … · 14:30 입력분 · 한국투자증권 가집계"', '외국인 오늘 잠정 순매수' in tip and '14:30 입력분 · 한국투자증권 가집계' in tip, tip)
            p.pg.mouse.move(5, 5)
            p.ev("() => document.querySelector('.viewseg button[data-v=\"table\"]').click()"); p.pg.wait_for_timeout(500)
            th = p.ev("() => [...document.querySelectorAll('#tablewrap th')].map(x => x.textContent).join('|')")
            check('map: the table column reads "외국인 오늘 잠정"', '외국인 오늘 잠정' in th, th)
            p.ev("() => document.querySelector('.viewseg button[data-v=\"map\"]').click()")
            check('map: console errors 0', not p.errs, p.errs)
        p.close()
    # slot null · another day — the message only on a weekday 09:00–10:00 before round 1
    T915 = datetime(2026, 11, 23, 9, 15, tzinfo=KST)
    for m, why in (({'slot': 'null'}, 'slot null'), ({'date': 'yesterday'}, 'a payload from yesterday')):
        reset(); mode(**m)
        p = Page(br, 1440, 900, at=T915, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
        t = p.ev(TEXTS); d = p.ev("() => KH.flowsLive.data()")
        ok_d = (d is not None and d['slot'] is None) if why == 'slot null' else d is None
        check(f'map: {why} at 09:15 → the map says "오늘 첫 입력(09:30) 뒤에 보여요" (data() {"slot null" if why == "slot null" else "null"}), no tiles, 오늘 pressed',
              t['empty'].strip() == '오늘 첫 입력(09:30) 뒤에 보여요' and ok_d and t['pressed'] == '0' and p.ev("() => document.querySelectorAll('#map .tile').length") == 0, (t['empty'], t['pressed'], d and d.get('slot')))
        check(f'map: {why} — console errors 0', not p.errs, p.errs)
        p.close()
    # no session today: 1일 drawn, the stored 0 kept; polled again only on weekdays
    T11, SAT = datetime(2026, 11, 23, 11, 0, tzinfo=KST), datetime(2026, 11, 28, 11, 0, tzinfo=KST)
    T830 = datetime(2026, 11, 23, 8, 30, tzinfo=KST)
    for at, m, why, polls in ((T11, {'slot': 'null'}, 'weekday 11:00, no round yet (a holiday not flagged)', True), (T11, {'slot': 'closed'}, 'weekday 11:00, closed:true (휴장)', True),
                              (T11, {'date': 'yesterday'}, 'weekday 11:00, a payload of another day', True), (SAT, {}, 'Saturday 11:00', False), (T830, {}, 'weekday 08:30 (before the session)', True)):
        reset(); mode(today=at.strftime('%Y-%m-%d'), **m)
        p = Page(br, 1440, 900, at=at, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
        t = p.ev(TEXTS); s_ = p.ev("() => KH.flowsLive.status()"); n = p.ev("() => document.querySelectorAll('#map .tile').length")
        lives = [x for x in p.gated if 'flows/live' in x]
        check(f'map: {why} → 1일 drawn ({n} tiles, "외국인 1일"), no 오늘 key, the stored 0 kept, no "오늘 첫 입력" message',
              t['pressed'] == '1' and t['ddv'] == '1일' and t['win'] == '0' and '외국인 1일' in t['sec'] and not any(k.startswith('0:') for k in t['keys']) and n > 50 and not t['empty'], t)
        if polls:
            check(f'map: {why} → still asks /api/flows/live (the map waits for the session: {s_["ivl"] // 1000} s)', 'map' in s_['wants'] and s_['polling'] and len(lives) >= 1, (s_, lives))
        else:
            check(f'map: {why} → the map asks nothing (no session on a weekend; the 수급 카드 keeps its own want)', 'map' not in s_['wants'], (s_, lives))
        check(f'map: {why} — console errors 0', not p.errs, p.errs)
        p.close()
    # back to 오늘 once a round is in (a page open from 08:30: the session starts — here the answer changes and the minute tick runs)
    reset(); mode(slot='null')
    p = Page(br, 1440, 900, at=T11, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    t0 = p.ev(TEXTS)
    mode(slot='on')
    p.ev("() => KH.flowsLive.refresh()"); p.pg.wait_for_timeout(600)
    t1 = p.ev(TEXTS); n = p.ev("() => document.querySelectorAll('#map .tile').length")
    check('map: a round arrives → the stored 오늘 comes back by itself (pressed 0, "외국인 오늘 잠정", tiles)', t0['pressed'] == '1' and t1['pressed'] == '0' and t1['ddv'] == '오늘 잠정' and '외국인 오늘 잠정' in t1['sec'] and n > 50, (t0['pressed'], t1, n))
    p.close()
    # a family device that never picked 오늘: the key appears only when there is a session (and polls nothing meanwhile)
    reset()
    p = Page(br, 1440, 900, at=SAT, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 5})
    t = p.ev(TEXTS)
    check('map: Saturday, 5일 picked → no 오늘 key, the map wants nothing', not any(k.startswith('0:') for k in t['keys']) and t['pressed'] == '5' and 'map' not in p.ev("() => KH.flowsLive.status().wants"), (t, p.gated))
    p.close()
    # round 1: 외국인 only
    T940 = datetime(2026, 11, 23, 9, 40, tzinfo=KST)
    for who, want in (('inst', '기관은 10:00 입력분부터 보여요'), ('fgn', None)):
        reset(); mode(slot='r1')
        p = Page(br, 1440, 900, at=T940, inv=FAMILY, st={'sizeBy': who, 'flowWin': 0})
        t = p.ev(TEXTS); n = p.ev("() => document.querySelectorAll('#map .tile').length")
        if want:
            check('map: round 1 (09:30) with 기관 → "기관은 10:00 입력분부터 보여요", no tiles, 오늘 kept', t['empty'].strip() == want and n == 0 and t['pressed'] == '0' and want in t['legend'], (t['empty'], t['legend'], n))
        else:
            check('map: round 1 (09:30) with 외국인 → drawn, the legend says "09:30 입력분"', n > 50 and '09:30 입력분 · 한국투자증권 가집계' in t['legend'], (n, t['legend']))
        check(f'map: round 1 [{who}] — console errors 0', not p.errs, p.errs)
        p.close()
    # live failing: the message
    reset(); mode(live='fail')
    p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    t = p.ev(TEXTS)
    check('map: /api/flows/live 503 → "오늘 잠정 수급을 불러오지 못했어요. 잠시 뒤 다시 시도해요." (token kept)', '오늘 잠정 수급을 불러오지 못했어요' in t['empty'] and p.ev("() => KH.inv.has()"), t['empty'])
    p.close()
    # the evening file
    reset(); mode(flowsAsOf=DAY)
    p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    t = p.ev(TEXTS)
    check('map: the evening flows.json (asOf today) → no 오늘 key, 1일 drawn ("외국인 1일"), 0 kept for the morning (family)',
          [k.split(':')[0] for k in t['keys']] == ['1', '5', '20'] and t['pressed'] == '1' and t['ddv'] == '1일' and t['win'] == '0' and '외국인 1일' in t['sec'] and '잠정' not in t['legend'], t)
    st = p.ev("() => KH.flowsLive.status()")
    check('map: the evening — the map no longer wants the live answer', 'map' not in st['wants'], st)
    p.close()
    # a page left open past 21:00: flows.json read again, the evening fallback kicks in (the card's new file shared when it has one)
    reset()
    T2140 = datetime(2026, 11, 23, 21, 40, tzinfo=KST)
    p = Page(br, 1440, 900, at=T2140, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0}, flow=True)
    t0 = p.ev(TEXTS); f0 = len(p.files)
    mode(flowsAsOf=DAY)
    for step in ('10:30', '01:05', '01:05'):
        p.pg.clock.fast_forward(step); p.pg.wait_for_timeout(900)
    t1 = p.ev(TEXTS); card = p.ev("() => window.KHFlows ? KHFlows.state().file : null")
    check(f'map: open past 21:00 with 오늘 → flows.json read again ({len(p.files) - f0} more), the evening file → 1일, no 오늘 key, 0 kept (card file {card})',
          t0['pressed'] == '0' and t1['pressed'] == '1' and t1['win'] == '0' and not any(k.startswith('0:') for k in t1['keys']) and 1 <= len(p.files) - f0 <= 2, (t0['pressed'], t1, p.files[f0:]))
    check('map: open past 21:00 — console errors 0', not p.errs, p.errs)
    p.close()
    # #khm-import= (the old address's bridge) never carries khm.inv
    reset()
    blob = base64.b64encode(json.dumps({'khm.theme': json.dumps('paper'), 'khm.inv': json.dumps(FAMILY)}).encode()).decode()
    p = Page(br, 1440, 900, hash_='#khm-import=' + urllib.parse.quote(blob, safe='') + '~kosdaq')
    g = p.ev("() => ({ theme: localStorage.getItem('khm.theme'), inv: localStorage.getItem('khm.inv'), has: KH.inv.has(), hash: location.hash, sec: !!document.querySelector('.famset') })")
    check('map: #khm-import= copies khm.theme but never khm.inv (no token, no section, no gated request)', g == {'theme': json.dumps('paper'), 'inv': None, 'has': False, 'hash': '#kosdaq', 'sec': False} and not p.gated, (g, p.gated))
    p.close()
    # forget while 0 → 1 saved
    reset()
    p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    p.ev("() => KH.inv.forget()"); p.pg.wait_for_timeout(400)
    t = p.ev(TEXTS); g = p.ev(FAMSTATE)
    n0 = len(p.gated)
    p.pg.wait_for_timeout(500)
    check('map: KH.inv.forget() while 오늘 → 1일 drawn and saved, the 오늘 key and the section gone, nothing gated asked after',
          t['win'] == '1' and t['pressed'] == '1' and [k.split(':')[0] for k in t['keys']] == ['1', '5', '20'] and not g['sec'] and len(p.gated) == n0, (t, g))
    check('map: forget — console errors 0', not p.errs, p.errs)
    p.close()


# ───────────────────────── owner ─────────────────────────
def owner(br):
    reset()
    p = Page(br, 1440, 900, inv=OWNER, perms=True)
    g = p.ev(FAMSTATE)
    check('owner: own() → 가족 초대 shown; no GET /api/inv before the panel opens', g['own'] and g['inv'] and not any(x == 'GET /api/inv' or x.startswith('GET /api/inv?') for x in p.gated), (g, p.gated))
    p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(700)
    rows = p.ev("() => [...document.querySelectorAll('.famr')].map(r => [r.querySelector('.nm').textContent, !!r.querySelector('.famtag'), !!r.querySelector('.famk')])")
    check('owner: the 화면 popover holds the section last; the list: 예훈 (관리, no 끄기) · 엄마 (끄기)',
          rows == [['예훈', True, False], ['엄마', False, True]] and p.ev("() => document.getElementById('morePanel').lastElementChild.classList.contains('famset')"), rows)
    p.ev("() => { document.getElementById('moreBtn').click(); }"); p.pg.wait_for_timeout(300)
    p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(500)
    check('owner: reopening within a minute asks no list again', p.gated.count('GET /api/inv') == 1, p.gated)
    # 만들기: empty → bubble; a name → the link
    p.pg.click('.famset .famk-pri'); p.pg.wait_for_timeout(200)
    bub = p.ev("() => [...document.querySelectorAll('.kbub')].map(b => b.textContent)")
    check('owner: 만들기 with no name → "이름을 적어 주세요" (nothing sent)', any('이름을 적어 주세요' in b for b in bub) and 'POST /api/inv' not in p.gated, (bub, p.gated))
    ml = p.ev("() => document.querySelector('.famin').maxLength")
    p.pg.fill('.famin:not(.famurl)', '아빠'); p.pg.click('.famset .famk-pri'); p.pg.wait_for_timeout(900)
    link = p.ev("() => ({ v: document.querySelector('.famurl').value, shown: !document.querySelector('.famlink').hidden, note: document.querySelector('.famlink .hint').textContent, share: document.querySelector('.famlink .famacts .famk:last-child').hidden, rows: [...document.querySelectorAll('.famr .nm')].map(x => x.textContent) })")
    m = re.match(r'^' + re.escape(URL.rstrip('/')) + r'/#inv=([A-Za-z0-9_-]{20,64})$', link['v'])
    check('owner: name ≤ 12 (maxlength), 만들기 → POST /api/inv → the link ${origin}/#inv=<token> shown once + the note, 공유 hidden (no navigator.share), the list has 아빠',
          ml == 12 and 'POST /api/inv' in p.gated and m and link['shown'] and link['note'] == '이 링크는 지금 한 번만 보여요. 받은 사람이 열면 그 기기에서 잠정 수급이 보여요.' and link['share'] and '아빠' in link['rows'], link)
    p.pg.click('.famlink .famacts .famk >> nth=0'); p.pg.wait_for_timeout(300)
    clip = p.ev("() => navigator.clipboard.readText()")
    bub = p.ev("() => [...document.querySelectorAll('.kbub')].map(b => b.textContent)")
    check('owner: 복사 → the clipboard holds the link, "복사했어요"', clip == link['v'] and any('복사했어요' in b for b in bub), (clip, bub))
    # the new token works on another device
    tok = m.group(1) if m else ''
    me = json.loads(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(URL + 'api/inv/me', headers={'X-Panse-Inv': tok}), timeout=5).read())
    check('owner: the made token answers /api/inv/me as 아빠', me == {'n': '아빠', 'own': False}, me)
    # 끄기 on 엄마: arm, then delete
    p.pg.click('.famr:has-text("엄마") .famk'); p.pg.wait_for_timeout(450)
    armed = p.ev("() => { const k = [...document.querySelectorAll('.famr')].find(r => r.textContent.includes('엄마')).querySelector('.famk'); return [k.dataset.st, k.getAttribute('aria-label')]; }")
    check('owner: the first 끄기 press arms the key (정말 끄기 — the neutral fail surface), nothing sent yet', armed[0] == 'arm' and '한 번 더' in armed[1] and not any(x.startswith('DELETE') for x in p.gated), (armed, p.gated))
    p.pg.click('.famr:has-text("엄마") .famk'); p.pg.wait_for_timeout(800)
    rows = p.ev("() => [...document.querySelectorAll('.famr .nm')].map(x => x.textContent)")
    live = p.ev("() => [...document.querySelectorAll('[aria-live]')].map(x => x.textContent).join('|')")
    check('owner: the second press → DELETE /api/inv/{id} → 엄마 off the list, said in the live region; no "null" written', any(x.startswith('DELETE /api/inv/') for x in p.gated) and 'null' not in live and '엄마' not in rows and '아빠' in rows and '엄마 초대를 껐어요' in live, (rows, p.gated, live))
    check('owner: console errors 0', not p.errs, p.errs)
    p.close()
    # 공유 with navigator.share
    reset()
    p = Page(br, 390, 844, inv=OWNER, init="navigator.share = async o => { window.__shared = o; }; navigator.canShare = () => true;")
    p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(700)
    home = p.ev("() => document.querySelector('.famset').parentElement.id + ' last:' + (document.getElementById('ctls').lastElementChild.className)")
    p.pg.fill('.famin:not(.famurl)', '동생'); p.pg.click('.famset .famk-pri'); p.pg.wait_for_timeout(900)
    p.pg.click('.famlink .famacts .famk >> nth=1'); p.pg.wait_for_timeout(300)
    sh = p.ev("() => window.__shared || null")
    check('owner [390]: the section is the sheet\'s last (after 아래 막대); 공유 shown with navigator.share → called with the link',
          home == 'ctls last:famset' and sh and re.match(r'.*/#inv=[A-Za-z0-9_-]{20,64}$', sh.get('url', '')), (home, sh))
    check('owner [390]: console errors 0', not p.errs, p.errs)
    p.close()
    # 이 기기에서 끄기
    reset()
    p = Page(br, 1440, 900, inv=FAMILY, st={'sizeBy': 'fgn', 'flowWin': 0})
    p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(400)
    p.pg.click('.famoff .famk'); p.pg.wait_for_timeout(450)
    a = p.ev("() => [document.querySelector('.famoff .famk').dataset.st, !document.getElementById('famOffH').hidden, KH.inv.has()]")
    p.pg.click('.famoff .famk'); p.pg.wait_for_timeout(500)
    g = p.ev(FAMSTATE); n0 = len(p.gated); foc = p.ev("() => document.activeElement && (document.activeElement.id || document.activeElement.className)")
    p.ev("() => KH.flowsLive.refresh()"); p.pg.wait_for_timeout(300)
    check('owner: 이 기기에서 끄기 — the first press arms (+ the hint), the second forgets: no section, khm.inv removed, focus back on 화면, no gated request after',
          a == ['arm', True, True] and not g['has'] and g['stored'] is None and not g['sec'] and len(p.gated) == n0 and foc == 'moreBtn', (a, g, foc))
    check('owner: 이 기기에서 끄기 — console errors 0', not p.errs, p.errs)
    p.close()


# ───────────────────────── cadence ─────────────────────────
def cadence(br):
    reset()
    p = Page(br, 1440, 900, inv=FAMILY)
    r = p.ev("""async () => { const s0 = KH.flowsLive.status(); KH.flowsLive.want('a', true); KH.flowsLive.want('b', true); await new Promise(r => setTimeout(r, 600));
      const s1 = KH.flowsLive.status(); const n = (await (await fetch('/__stats')).json())['GET /api/flows/live'] || 0;
      const d = await KH.flowsLive.refresh(); KH.flowsLive.want('a', false); const s2 = KH.flowsLive.status(); KH.flowsLive.want('b', false); const s3 = KH.flowsLive.status();
      return { s0, s1, s2, s3, n, slot: d && d.slot, today: d && d.date }; }""")
    check('cadence: nothing polled before anyone wants it; two wants → one request; still polling with one left; none left → stopped',
          not r['s0']['polling'] and r['n'] == 1 and r['s1']['polling'] and r['s2']['polling'] and not r['s3']['polling'] and r['s3']['next'] is None and r['slot'] == '14:30' and r['today'] == DAY, r)
    check('cadence: weekday 10:00 KST → every 60 s (next ≤ 60 s)', r['s1']['ivl'] == 60000 and 0 < r['s1']['next'] <= 60000, r['s1'])
    # the page hidden: no timer
    h = p.ev("""() => { KH.flowsLive.want('a', true); Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'));
      const s = KH.flowsLive.status(); delete document.hidden; Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'));
      const t = KH.flowsLive.status(); KH.flowsLive.want('a', false); return [s.polling, t.polling]; }""")
    check('cadence: a hidden page polls nothing, back in view it does again', h == [False, True], h)
    p.close()
    for at, ivl, label in ((datetime(2026, 11, 23, 15, 49, tzinfo=KST), 60000, 'weekday 15:49'), (datetime(2026, 11, 23, 15, 50, 30, tzinfo=KST), 600000, 'weekday 15:50:30'),
                           (datetime(2026, 11, 28, 10, 0, tzinfo=KST), 600000, 'Saturday 10:00'), (datetime(2026, 11, 23, 9, 20, 30, tzinfo=KST), 600000, 'weekday 09:20:30')):
        mode(today=at.strftime('%Y-%m-%d'))
        p = Page(br, 1440, 900, at=at, inv=FAMILY)
        s = p.ev("async () => { KH.flowsLive.want('a', true); await new Promise(r => setTimeout(r, 500)); const s = KH.flowsLive.status(); s.today = (KH.flowsLive.data() || {}).date || null; KH.flowsLive.want('a', false); return s; }")
        early = label.endswith('09:20:30')
        nx = 270000 if early else ivl
        check(f'cadence: {label} KST → every {ivl // 1000} s (next ≤ {nx // 1000} s{" — wakes at 09:25" if early else ""}), data() for {at.date()}',
              s['ivl'] == ivl and s['next'] is not None and (nx - 1000 if early else 0) < s['next'] <= nx + 200 and s['today'] == at.strftime('%Y-%m-%d'), s)
        p.close()
    mode(today=DAY)


# ───────────────────────── layout ─────────────────────────
def layout(br):
    reset()
    for theme in THEMES:
        for w, h in ((360, 740), (1280, 800)):
            p = Page(br, w, h, theme=theme, inv=OWNER, st={'sizeBy': 'fgn', 'flowWin': 0})
            p.ev(OPEN_SETTINGS); p.pg.wait_for_timeout(600)
            p.pg.fill('.famin:not(.famurl)', '열두글자이름이에요하나둘'); p.pg.click('.famset .famk-pri'); p.pg.wait_for_timeout(900)
            p.ev("() => { const s = document.querySelector('.famset'); s.scrollIntoView({ block: 'center' }); }"); p.pg.wait_for_timeout(200)
            ov, ins = p.ev(OVER), p.ev(INSIDE)
            rows = p.ev("() => document.querySelectorAll('.famr').length")
            check(f'layout [{w} {theme}]: the section at its fullest (link + {rows} rows): nothing past the screen edge, nothing wider than the section, the section inside its panel',
                  not ov and not ins.get('missing') and not ins['out'] and ins['scroll'] <= 0 and ins['sec'][0] >= ins['panel'][0] - 1 and ins['sec'][1] <= ins['panel'][1] + 1 and rows >= 3, (ov, ins))
            tools = p.ev("""() => { const t = document.querySelector('.tools'), tops = [...t.querySelectorAll('.search,.ctl,#extras-tools > *')].filter(e => e.offsetParent && !e.closest('.morep')).map(e => Math.round(e.getBoundingClientRect().top));
              return { h: Math.round(t.getBoundingClientRect().height), spread: Math.max(...tops) - Math.min(...tops) }; }""")
            if w == 1280:
                p.ev("() => document.getElementById('moreBtn').click()"); p.pg.wait_for_timeout(300)
                ov2 = p.ev(OVER)
                check(f'layout [1280 {theme}]: 순매수 기간 "오늘 잠정" in the toolbar — one row ({tools["h"]}px = the public 44, tops within 3px), nothing past the edge',
                      tools['h'] == 44 and tools['spread'] <= 3 and not ov2, (tools, ov2))
            check(f'layout [{w} {theme}]: console errors 0', not p.errs, p.errs)
            p.close()
    for inv in (None, FAMILY):
        for w, h, top in ((390, 844, 247), (1280, 800, 207), (1440, 900, 207)):
            p = Page(br, w, h, inv=inv, st={'sizeBy': 'fgn', 'flowWin': 0} if inv else None)
            t = p.ev(MAPTOP); n = p.ev("() => document.querySelectorAll('#map .tile').length")
            check(f'layout [{w} {"family 오늘 잠정" if inv else "public"}]: map top {t} (= {top}), {n} tiles', t == top and n > 50, (t, n))
            p.close()


def main():
    parts = set(sys.argv[1:]) or {'public', 'invite', 'map', 'owner', 'cadence', 'layout'}
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_page.py')], check=True, capture_output=True)
    start_mock()
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            for name, fn in (('public', public), ('invite', invite), ('map', map_checks), ('owner', owner), ('cadence', cadence), ('layout', layout)):
                if name in parts:
                    print(f'── {name}')
                    fn(br)
            br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAIL', f)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
