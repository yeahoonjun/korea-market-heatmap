#!/usr/bin/env python3
"""QA for 실시간 갱신 — the page side (src/live/live.js · live.css, the template's KH.feed / KH.pausePoll / #live-mark;
docs/standards/realtime.md §7). Two halves:

  A · the real hub: `wrangler dev` (worker/, dev-only vars LIVE_DEV_OPEN=1 · NAVER_POLL_BASE · ASSET_BASE · LIVE_ORIGINS — the Worker
      honours them on localhost only) + prototypes/realtime/upstream_mock.mjs (Naver-shaped; prices follow a real 1-minute replay,
      --churn 0.3) + web/ as ASSET_BASE. The page is the Worker's own (http://127.0.0.1:8933/); every other /api route is answered by
      qa/news/mock_api.py through a page route. Connects → 실시간, deltas move tiles / side cards / ticker with flashes and the quotes
      poll stays paused; a hidden tab closes the socket after 30 s and resumes with deltas (no snapshot) when visible; a restarted
      Worker (new hub = new epoch) → 다시 연결하는 중 → a snapshot, no stale tile; phones keep the header row and the map top.
  B · a scripted hub (Playwright routeWebSocket on qa/news/mock_api.py's page, /api/quotes routed to the same synthetic session):
      gaps → {t:'snap'}, beats, 시세 지연 → poll after 30 s, silence 45 s → poll + backoff, off closed / full / budget / paused / error
      (retryAt, persisted across a reload), epoch change, hidden tab, 다시 보기, 해외, 전체, the setting, the snapshot, the layout matrix
      (360 · 390 · 768 · 1280 · 1920 × 4 themes: overflow 0, the map top unchanged by every label), console 0.

  python3 scripts/build_page.py && python3 qa/live/test_live_page.py [--shots] [--only A|B]

Ports LIVE_QA_BASE (8931) … +4: web/ 8931 · Naver mock 8932 · wrangler 8933 (inspector 8934) · API mock 8935. The Naver mock needs
Naver once for its base rows and the public Worker's /api/replay once (frames) — LIVE_QA_FRAMES=/path/frames.json skips the latter.
worker/node_modules: this worktree's, else /home/claude/heatmap/worker/node_modules (WS_MODULES overrides). --shots writes
/tmp/live_page_*.png. Exit 1 on a fail.
"""
import atexit
import copy
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
B0 = int(os.environ.get('LIVE_QA_BASE', 8931))
P = dict(web=B0, naver=B0 + 1, dev=B0 + 2, insp=B0 + 3, api=B0 + 4)
DEV = f'http://127.0.0.1:{P["dev"]}/'
API = f'http://127.0.0.1:{P["api"]}/'
SNAP_URL = (ROOT / 'dist/index.html').as_uri()
MOD = os.environ.get('WS_MODULES') or (str(ROOT / 'worker/node_modules') if (ROOT / 'worker/node_modules/.bin/wrangler').exists() else '/home/claude/heatmap/worker/node_modules')
WRANGLER = MOD.rstrip('/') + '/.bin/wrangler'
SHOTS = '--shots' in sys.argv
ONLY = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else ''
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
D3 = (ROOT / 'src/vendor/d3-7.9.0.min.js').read_text(encoding='utf-8')
KST = timezone(timedelta(hours=9))
SIZES = [(360, 740), (390, 844), (768, 1024), (1280, 800), (1920, 1080)]
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' else ''), flush=True)



# ───────── processes ─────────
PROCS = []


def start(args, log, env=None, cwd=ROOT):
    f = open(log, 'w')
    p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, env=dict(os.environ, **(env or {})), start_new_session=True, cwd=str(cwd))
    PROCS.append(p)
    return p


def stop(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        p.wait(8)
    except Exception:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            pass


def free(*ports):
    for port in ports:
        subprocess.run(['fuser', '-k', f'{port}/tcp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_all():
    for p in PROCS:
        stop(p)
    free(*P.values())


atexit.register(stop_all)


def get(url, timeout=10):
    with NOPROXY.open(url, timeout=timeout) as r:
        return r.status, r.read(), r.headers.get('content-type', 'application/json')


def wait_http(url, secs):
    end = time.time() + secs
    while time.time() < end:
        try:
            get(url, 3)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.5)
    return False


def wrangler(persist):
    args = [WRANGLER, 'dev', '-c', str(ROOT / 'worker/wrangler.toml'), '--port', str(P['dev']), '--ip', '127.0.0.1',
            '--inspector-port', str(P['insp']), '--persist-to', persist, '--show-interactive-dev-session=false']
    for k, v in {'NAVER_POLL_BASE': f'http://127.0.0.1:{P["naver"]}', 'ASSET_BASE': f'http://127.0.0.1:{P["web"]}/', 'LIVE_DEV_OPEN': '1',
                 'LIVE_ORIGINS': f'http://127.0.0.1:{P["dev"]}'}.items():
        args += ['--var', f'{k}:{v}']
    p = start(args, '/tmp/live_qa_wrangler.log', cwd=ROOT / 'worker')   # its .wrangler/ cache lands in worker/ (git-ignored)
    if not wait_http(DEV + 'api/health', 120):
        print(open('/tmp/live_qa_wrangler.log').read()[-3000:])
        raise SystemExit('wrangler dev did not come up')
    return p


# ───────── a synthetic session for the scripted hub (B) ─────────
SNAP = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
TOP = []
for m in ('K', 'Q'):
    TOP += sorted((x for x in SNAP['stocks'] if x['m'] == m and x['c'].endswith('0')), key=lambda x: -x['cap'])[:300]
ALL = [x for x in SNAP['stocks']]
T0 = time.time()
SYN0 = datetime.now(KST).replace(hour=10, minute=30, second=0, microsecond=0)


def syn_iso():
    """a session clock: today 10:30 KST + the test's elapsed time (bodies, polls and deltas share it, so `fresher` orders them)"""
    t = SYN0 + timedelta(seconds=time.time() - T0)
    return t.strftime('%Y-%m-%dT%H:%M:%S.') + f'{t.microsecond // 1000:03d}+09:00'


def ms():
    return int(time.time() * 1000)


def make_body(rows=None):
    t = syn_iso()
    out = []
    for x in (rows or TOP):
        r = {k: v for k, v in x.items()}
        if sum(map(ord, r['c'])) % 5:                                     # most stocks trade on NXT too (§3-10): the 통합 basis, the phone's chip
            r['nx'] = {'p': r['p'], 'd': r['d'], 'r': r['r'], 's': 'reg', 'o': 1, 't': t, 'v': r.get('v', 0) // 3, 'tv': r.get('tv', 0) // 3}
        out.append(r)
    return {'asOf': t, 'source': '네이버 증권 (polling.finance.naver.com)', 'marketStatus': {'KOSPI': 'OPEN', 'KOSDAQ': 'OPEN'}, 'afterHours': False,
            'nxt': {'session': 'reg', 'open': True}, 'index': copy.deepcopy(SNAP['index']), 'stocks': out}


def apply_patch(row, p):                                         # = worker/src/live_core.js applyPatch
    for k, v in p.items():
        if k == 'c':
            continue
        if k == 'nx':
            if v is None:
                row.pop('nx', None)
            else:
                nx = row.setdefault('nx', {})
                for j, x in v.items():
                    if x is None:
                        nx.pop(j, None)
                    else:
                        nx[j] = x
        elif v is None:
            row.pop(k, None)
        else:
            row[k] = v


def move(body, code, factor):
    r = next(x for x in body['stocks'] if x['c'] == code)
    base = r['p'] - r['d']
    p = max(1, int(round(r['p'] * factor)))
    d = p - base
    rr = round(d / base * 100, 2) if base else 0
    patch = {'c': code, 'p': p, 'd': d, 'r': rr}
    if 'nx' in r:
        patch['nx'] = {'p': p, 'd': d, 'r': rr, 't': syn_iso()}
    return patch


class Conn:
    def __init__(self, ws):
        self.ws, self.url, self.at, self.got, self.closed = ws, ws.url, time.time(), [], None
        ws.on_message(lambda m: self.got.append(m))
        ws.on_close(lambda code, reason: setattr(self, 'closed', (code, reason, time.time())))

    def send(self, obj):
        self.ws.send(json.dumps(obj, ensure_ascii=False))

    def asked(self, t):
        return sum(1 for m in self.got if isinstance(m, str) and f'"t":"{t}"' in m.replace(' ', ''))


class Hub:
    """routeWebSocket: every page connection is answered by a mode — 'live' (hello + snap), 'hello' (hello only), 'silent',
    ('off', reason, retry_in_s), or a callable(conn). `queue` holds modes for the next connections, then `mode`."""
    def __init__(self, page, mode='live', epoch='e1'):
        self.conns, self.mode, self.queue, self.epoch, self.v, self.body = [], mode, [], epoch, 0, None
        page.route_web_socket(re.compile(r'/api/live'), self._on)

    def _on(self, ws):
        c = Conn(ws)
        self.conns.append(c)
        mode = self.queue.pop(0) if self.queue else self.mode
        if mode == 'live':
            self.greet(c)
        elif mode == 'hello':
            self.greet(c, snap=False)
        elif isinstance(mode, tuple) and mode[0] == 'off':
            self.off(c, mode[1], mode[2])
        elif callable(mode):
            mode(c)

    def ensure(self):
        if self.body is None:
            self.body, self.v = make_body(), 1

    def greet(self, c, snap=True):
        self.ensure()
        c.send({'t': 'hello', 'proto': 1, 'ch': 'top', 'epoch': self.epoch, 'v': self.v, 'poll': 3000, 'phase': 'live', 'now': ms()})
        if snap:
            self.snap(c)

    def snap(self, c):
        self.ensure()
        c.send({'t': 'snap', 'ch': 'top', 'epoch': self.epoch, 'v': self.v, 'at': ms(), 'body': self.body})

    def off(self, c, reason, retry_in_s):
        # no close frame after it: the page must take {t:'off'} itself as the end (realtime.md §7-3 — under wrangler dev the close
        # event never came); it closes its side, which the route sees as `closed`
        retry = ms() + int(retry_in_s * 1000)
        c.retry = retry
        c.send({'t': 'off', 'reason': reason, 'retryAt': retry, 'at': ms()})
        return retry

    def delta(self, c, rows, base=None, **extra):
        self.ensure()
        b = self.v if base is None else base
        self.v += 1
        t = syn_iso()
        for p in rows:
            apply_patch(next(x for x in self.body['stocks'] if x['c'] == p['c']), p)
        for k, key in (('ix', 'index'), ('ms', 'marketStatus')):
            if k in extra:
                self.body[key] = extra[k]
        self.body['asOf'] = t
        c.send(dict({'t': 'd', 'v': self.v, 'b': b, 'at': ms(), 'asOf': t, 'rows': rows}, **extra))

    @property
    def last(self):
        return self.conns[-1] if self.conns else None


# ───────── pages ─────────
INIT_JS = r"""
window.__hide = on => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => on });
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => on ? 'hidden' : 'visible' });
  document.dispatchEvent(new Event('visibilitychange'));
};
window.__kd = [];
document.addEventListener('kh:data', e => { const ch = (e.detail && e.detail.changed) || []; window.__kd.push({ t: Date.now(), n: ch.length, c: ch.slice(0, 80).map(x => x[0]) }); });
window.__fl = [];
document.addEventListener('DOMContentLoaded', () => {
  const map = document.getElementById('map');
  if (map) new MutationObserver(ms => { for (const m of ms) { const el = m.target; if (el.dataset && el.dataset.c && /\b(flash-up|flash-dn|fl-u|fl-d)\b/.test(el.className) && !/\b(flash-up|flash-dn|fl-u|fl-d)\b/.test(m.oldValue || '')) window.__fl.push(el.dataset.c); } })
    .observe(map, { subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true });
});
"""


class Errors:
    def __init__(self):
        self.items, self.allow = [], []

    def attach(self, page, tag=''):
        page.on('console', lambda m: self.items.append(f'{tag} {m.type}: {m.text[:180]}') if m.type in ('error', 'warning') and not any(a in m.text for a in self.allow) else None)
        page.on('pageerror', lambda e: self.items.append(f'{tag} pageerror: {e}'))


ERR = Errors()


class Reqs:
    """/api/quotes requests of a page: plain (the 600 stream), all (전체), codes (extras)"""
    def __init__(self, page):
        self.items = []
        page.on('request', lambda r: self.items.append((time.time(), r.url)) if '/api/quotes' in r.url else None)

    def plain(self, since=0):
        return [t for t, u in self.items if t >= since and re.search(r'/api/quotes($|\?(?!codes|scope))', u)]

    def all(self, since=0):
        return [t for t, u in self.items if t >= since and 'scope=all' in u]


def fwd_api(route):
    """an /api route of the wrangler page → the Python API mock (news, disclosures, market, time, …)"""
    path = '/' + route.request.url.split('/', 3)[3]
    try:
        st, body, ct = get(API.rstrip('/') + path)
        route.fulfill(status=st, body=body, headers={'content-type': ct, 'cache-control': 'no-store'})
    except urllib.error.HTTPError as e:
        route.fulfill(status=e.code, body=e.read(), headers={'content-type': 'application/json'})
    except Exception:
        route.fulfill(status=502, body=b'{"error":"mock"}', headers={'content-type': 'application/json'})


def context(br, w, h=None, store=None, mobile=None):
    mobile = (w <= 760) if mobile is None else mobile
    ctx = br.new_context(viewport={'width': w, 'height': h or dict(SIZES).get(w, 900)}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    ctx.route('https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js', lambda r: r.fulfill(status=200, body=D3, headers={'content-type': 'application/javascript'}))
    ctx.route('https://cdn.jsdelivr.net/**', lambda r: r.fulfill(status=200, body='', headers={'content-type': 'text/css'}))
    st = {'motion': 'standard', 'tickerPaused': True}
    st.update(store or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}' + INIT_JS)
    return ctx


def mock_page(br, w=1280, h=None, store=None, mode='live', tag='', epoch='e1', go=True):
    """the API mock's page with a scripted hub; /api/quotes = the hub's current body (or the synthetic session)"""
    ctx = context(br, w, h, store)
    pg = ctx.new_page()
    hub = Hub(pg, mode, epoch)

    def quotes(route):
        u = route.request.url
        if 'scope=all' in u:
            b = make_body(ALL)
        elif 'codes=' in u:
            want = set(re.search(r'codes=([^&]*)', u).group(1).split(','))
            b = make_body([x for x in ALL if x['c'] in want])
        else:
            b = copy.deepcopy(hub.body) if hub.body else make_body()
            b['asOf'] = syn_iso()
        route.fulfill(status=200, body=json.dumps(b, ensure_ascii=False), headers={'content-type': 'application/json', 'cache-control': 'no-store'})
    pg.route(re.compile(r'/api/quotes'), quotes)
    ERR.attach(pg, tag or f'B{w}')
    rq = Reqs(pg)
    if go:
        pg.goto(API)
    return ctx, pg, hub, rq


def st(pg):
    return pg.evaluate('window.KHLive ? KHLive.state() : null')


def wait_label(pg, want, secs=10):
    end = time.time() + secs
    s = None
    while time.time() < end:
        s = st(pg)
        if s and (s['label'] == want if isinstance(want, str) else s['label'] in want):
            return s
        pg.wait_for_timeout(150)
    return s


def wait_for(pg, fn, secs=10, step=150):
    end = time.time() + secs
    while time.time() < end:
        v = fn()
        if v:
            return v
        pg.wait_for_timeout(step)
    return fn()


MARK_JS = r"""() => {
  const m = document.getElementById('live-mark'), st = document.getElementById('status'), R = e => e.getBoundingClientRect();
  const vis = e => e && !e.hidden && getComputedStyle(e).display !== 'none' && R(e).width > 0;
  const map = document.getElementById('map'), top = document.querySelector('header.top');
  const txt = [...m.querySelectorAll('.lm-l, .lm-s')].filter(vis).map(e => e.textContent).join('');
  const brand = document.querySelector('.brand'), tabs = document.querySelector('.tabs');
  return { shown: vis(m), text: txt, s: m.dataset.s || '', has: st.classList.contains('has-lm'), dot: vis(st.querySelector('.dot')),
    badge: vis(st.querySelector('.badge')) ? st.querySelector('.badge').textContent : '', sr: (m.querySelector('.sr') || {}).textContent || '',
    title: m.title, mapTop: R(map).top + scrollY, headH: R(top).height, stTop: R(st).top, stBottom: R(st).bottom, brandTop: R(brand).top,
    mark: vis(m) ? [R(m).left, R(m).right, R(m).top, R(m).bottom] : null, vw: innerWidth,
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    clash: vis(m) ? [...document.querySelectorAll('#clock, #bchip, #basis, .status .txt, .status .tshort')].filter(vis)
      .filter(e => { const a = R(e), b = R(m); return a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5; }).map(e => e.id || e.className) : [] };
}"""


def shot(pg, name):
    if SHOTS:
        pg.screenshot(path=f'/tmp/live_page_{name}.png')


def setting(pg, on):
    """flip 실시간 갱신 through its switch (the 화면 popover ≥ 1280, else the 표시 설정 sheet)"""
    sw = pg.locator('[data-set="live"] .swbtn')
    if not sw.is_visible():
        if pg.locator('#moreBtn').is_visible():
            pg.click('#moreBtn')
        else:
            pg.click('#setBtn')
        pg.wait_for_timeout(250)
    if (sw.get_attribute('aria-checked') == 'true') != on:
        sw.click()
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(150)


ROWS_MATCH_JS = r"""() => { let n = 0, bad = []; for (const s of KH.stocks()) { const r = KHLive.row(s.c); if (!r) continue; n++;
  if (r.p !== s.p || r.r !== s.r) bad.push(s.c + ' ' + s.p + '/' + r.p); } return { n, bad: bad.slice(0, 5), nbad: bad.length }; }"""


# ═════════════════════════ B · the scripted hub ═════════════════════════
def b_basics(br):
    ctx, pg, hub, rq = mock_page(br, 1280, store={'market': 'K'}, tag='B1')
    s = wait_label(pg, 'live', 10)
    m = pg.evaluate(MARK_JS)
    check('B1 hello + snapshot → 실시간 (dot + word; the status dot and the "실시간" badge step aside)',
          s and s['label'] == 'live' and s['rows'] == 600 and m['shown'] and m['text'] == '실시간' and m['has'] and not m['dot'] and '실시간' not in m['badge'],
          f"{m['text']!r} badge={m['badge']!r} rows={s and s['rows']}")
    pg.wait_for_timeout(1700)
    m = pg.evaluate(MARK_JS)
    check('B1 screen readers: the state once (aria-live polite), without a clock time', m['sr'].startswith('실시간 갱신: 실시간으로 받고 있어요') and not re.search(r'\d\d:\d\d', m['sr']), m['sr'])
    t_live = time.time()
    pg.wait_for_timeout(12500)
    n = len(rq.plain(t_live + 0.3))
    check('B1 quotes poll paused while the stream is live (12.5 s → 0 requests)', n == 0 and pg.evaluate('KH.polling().paused'), f'{n} requests')
    shot(pg, 'B_1280_live')

    c = hub.last
    kd0, fl0 = pg.evaluate('__kd.length'), pg.evaluate('__fl.length')
    movers0 = pg.inner_text('#movers')
    ix = copy.deepcopy(hub.body['index'])
    v = round(ix['KOSPI']['value'] + 61.7, 2)
    ix['KOSPI'] = {'value': v, 'change': round(ix['KOSPI']['change'] + 61.7, 2), 'ratio': round(ix['KOSPI']['ratio'] + 1.17, 2)}
    p1, p2 = move(hub.body, '005930', 1.25), move(hub.body, '000660', 0.97)
    hub.delta(c, [p1, p2], ix=ix)
    pg.wait_for_timeout(900)
    got = pg.evaluate("[KH.stock('005930').p, KH.stock('000660').p, KH.index().KOSPI.value]")
    check('B1 a delta reaches the store (two stocks) and the index', got == [p1['p'], p2['p'], v], f'{got} want {[p1["p"], p2["p"], v]}')
    kd = pg.evaluate(f'__kd.slice({kd0})')
    check("B1 'kh:data' carries the moved stocks in detail.changed", any('005930' in x['c'] and '000660' in x['c'] for x in kd), kd[-1:] if kd else 'none')
    fl = pg.evaluate(f'__fl.slice({fl0})')
    check('B1 the moved tiles flash (효과 기본)', '005930' in fl and '000660' in fl, fl[:6])
    tk = pg.evaluate("""(() => { const e = document.querySelector('#strip .xs-item[data-k="KOSPI"]'); return e ? (e.getAttribute('aria-label') || '') + ' | ' + e.textContent : ''; })()""")
    check('B1 the ticker shows the hub index', f'{v:,.2f}' in tk, tk[:90])
    movers1 = pg.inner_text('#movers')
    check('B1 the side card (눈에 띄는 종목) follows: 삼성전자 +25 % on top', movers1 != movers0 and movers1.strip().split('\n')[0:3].__str__().find('삼성전자') >= 0, movers1[:60].replace('\n', ' '))

    # a gap → the snapshot, never a guess
    want = move(hub.body, '035420', 1.08)
    before = pg.evaluate("KH.stock('035420').p")
    hub.delta(c, [want], base=hub.v + 5)
    asked = wait_for(pg, lambda: c.asked('snap'), 3)
    check('B1 a gap (b ≠ v) → {t:"snap"} once, nothing applied', asked == 1 and pg.evaluate("KH.stock('035420').p") == before, f'asked {asked}')
    hub.snap(c)
    pg.wait_for_timeout(600)
    s = st(pg)
    check('B1 the snapshot after the gap is drawn (v follows the hub)', pg.evaluate("KH.stock('035420').p") == want['p'] and s['v'] == hub.v and s['gaps'] == 1, f"v {s['v']}/{hub.v}")
    c.send({'t': 'hb', 'v': hub.v, 'at': ms(), 'asOf': syn_iso()})
    pg.wait_for_timeout(400)
    c.send({'t': 'hb', 'v': hub.v + 3, 'at': ms(), 'asOf': syn_iso()})
    pg.wait_for_timeout(500)
    s = st(pg)
    check('B1 a beat with the same v is quiet; a beat with another v asks for the snapshot', s['beats'] == 2 and c.asked('snap') == 2, f"beats {s['beats']} asked {c.asked('snap')}")
    hub.snap(c)
    pg.wait_for_timeout(400)

    # 시세 지연, then a value again
    c.send({'t': 'st', 'ok': False, 'msg': '시세를 받지 못했어요', 'retryMs': 6000, 'at': ms()})
    s = wait_label(pg, 'delayed', 3)
    m = pg.evaluate(MARK_JS)
    check('B1 {t:"st", ok:false} → 시세 지연 (the poll stays paused for 30 s)', s['label'] == 'delayed' and m['text'] == '시세 지연' and s['paused'] and '네이버 증권 시세를 받지 못해' in m['title'], f"{m['text']} paused {s['paused']} title {m['title'][:40]}")
    shot(pg, 'B_1280_delayed')
    hub.delta(c, [move(hub.body, '005380', 1.01)])
    s = wait_label(pg, 'live', 3)
    check('B1 the next value → 실시간 again', s['label'] == 'live' and s['paused'])

    # 실시간 갱신 off → at once: no socket, no mark, the poll back within one interval; on → connects again
    t = time.time()
    setting(pg, False)
    closed = wait_for(pg, lambda: c.closed, 3)
    s, m = st(pg), pg.evaluate(MARK_JS)
    check('B4 setting off → the socket closes at once, the mark goes, the status dot is back', bool(closed) and s['socket'] == -1 and not m['shown'] and not m['has'] and m['dot'] and not s['paused'], f"closed {closed} {s['label']!r}")
    polled = wait_for(pg, lambda: rq.plain(t), 12)
    check('B4 … and the 10 s poll resumes within one interval', bool(polled) and polled[0] - t <= 11, f'{(polled[0] - t) if polled else None:.1f} s' if polled else 'no poll')
    n0 = len(hub.conns)
    setting(pg, True)
    s = wait_label(pg, 'live', 5)
    check('B4 setting on → one new connection → 실시간', len(hub.conns) == n0 + 1 and s['label'] == 'live', f'conns {len(hub.conns)}')
    check('B4 the setting row: 실시간 갱신, default on, hint', pg.evaluate("""(() => { const r = document.querySelector('[data-set="live"]'); return !!r && r.textContent.includes('실시간 갱신') && r.textContent.includes('10초마다') && localStorage.getItem('khm.set.live') === 'true'; })()"""))

    # 전체 (2,700) → no socket; back to 300 → one again
    t = time.time()
    c = hub.last
    pg.click('.seg[data-key="topN"] button[data-v="all"]')
    closed = wait_for(pg, lambda: c.closed, 3)
    alls = wait_for(pg, lambda: rq.all(t), 6)
    s = st(pg)
    check('B4 전체 → the socket closes at once, 전체 is polled (scope=all), no mark', bool(closed) and bool(alls) and s['socket'] == -1 and s['label'] == '' and s['blocked'] == 'scope')
    n0 = len(hub.conns)
    pg.wait_for_timeout(3000)
    check('B4 … and no connection while 전체', len(hub.conns) == n0)
    pg.click('.seg[data-key="topN"] button[data-v="300"]')
    s = wait_label(pg, 'live', 6)
    check('B4 back to 300 → connects again → 실시간', len(hub.conns) == n0 + 1 and s['label'] == 'live')
    ctx.close()


def b_refusals(br):
    for reason, secs, label in [('full', 300, 'polling'), ('budget', 3600, 'polling'), ('paused', 60, 'polling'), ('closed', 4 * 3600, '')]:
        ctx, pg, hub, rq = mock_page(br, 390, store={'market': 'K'}, mode=('off', reason, secs), tag=f'B-{reason}')
        t0 = time.time()
        s = wait_for(pg, lambda: (st(pg) or {}).get('off') and st(pg), 4)
        m = pg.evaluate(MARK_JS)
        off = s['off'] if s else None
        lo, hi = ms_at(t0) + secs * 1000 - 1500, ms_at(time.time()) + (secs * 1000 + 60e3 + 500 if reason in ('closed', 'budget') else max(secs, 15) * 1250 + 500)
        check(f'B2 off {reason}: label {"10초마다 갱신 (phone: 10초)" if label else "hidden"}, wait until ≥ retryAt',
              bool(off) and off['reason'] == reason and lo <= off['until'] <= hi and s['label'] == label and (m['text'] == '10초' if label else not m['shown']),
              f"label {s and s['label']!r} text {m['text']!r} until-now {(off['until'] - ms()) / 1000 if off else None:.0f}s")
        if reason in ('full', 'budget', 'paused'):
            check(f'B2 off {reason}: the tooltip says why', {'full': '가득 차서', 'budget': '사용량을 다 써서', 'paused': '잠시 꺼져'}[reason] in m['title'], m['title'])
        t1 = time.time()
        polled = wait_for(pg, lambda: rq.plain(t1), 11.5)
        check(f'B2 off {reason}: the quotes poll goes on (a request within 11 s), no second connection', bool(polled) and len(hub.conns) == 1, f'conns {len(hub.conns)}')
        if reason in ('budget', 'closed'):
            pg.reload()
            pg.wait_for_timeout(3000)
            s = st(pg)
            check(f'B2 off {reason}: remembered across a reload (localStorage) — no connection, same label', len(hub.conns) == 1 and s['off'] and s['off']['reason'] == reason and s['label'] == label, f'conns {len(hub.conns)}')
        if reason == 'full':
            shot(pg, 'B_390_polling')
        ctx.close()


def ms_at(t):
    return int(t * 1000)


def b_long(br):
    """the scenarios that need real seconds (45 s silence, 30 s grace, retryAt) run side by side"""
    pages = {}

    def page(name, w=1280, **kw):
        ctx, pg, hub, rq = mock_page(br, w, store={'market': 'K'}, tag=f'B-{name}', **kw)
        pages[name] = dict(ctx=ctx, pg=pg, hub=hub, rq=rq, ev={})
        return pages[name]

    S1 = page('silent', 768)
    S2 = page('stale', 1280)
    S3 = page('hidden', 1280)
    S4 = page('replay', 1280)
    S5 = page('world', 1280)
    S6 = page('closed', 390, mode=('off', 'closed', 4))
    S7 = page('error', 1280, mode=('off', 'error', 3))
    S6['hub'].queue = ['live']
    S7['hub'].queue = [('off', 'error', 3), 'live']
    t0 = time.time()
    for x in (S1, S2, S3, S4, S5):
        x['ev']['live'] = bool(wait_label(x['pg'], 'live', 8))
    tl = time.time()
    # starts (a message now, so the 45 s / 30 s clocks start here)
    S1['hub'].last.send({'t': 'hb', 'v': S1['hub'].v, 'at': ms(), 'asOf': syn_iso()})
    S1['ev']['t'] = time.time()
    c2 = S2['hub'].last
    S2['hub'].delta(c2, [move(S2['hub'].body, '005930', 1.01)])
    c2.send({'t': 'st', 'ok': False, 'msg': '시세를 받지 못했어요', 'retryMs': 6000, 'at': ms()})
    S2['ev']['t'] = time.time()
    h3 = S3['hub']
    h3.delta(h3.last, [move(h3.body, '005930', 1.02)])
    S3['pg'].wait_for_timeout(300)
    S3['ev']['p_before'] = S3['pg'].evaluate("KH.stock('005930').p")
    S3['pg'].evaluate('__hide(true)')
    S3['ev']['t'] = time.time()
    S3['ev']['hidden_quotes0'] = len(S3['rq'].plain())
    S4['pg'].evaluate("KH.setReplay({t: '1000', date: null, prices: new Map([['005930', {p: 100000, r: -50}]])})")
    S4['ev']['t'] = time.time()
    S4['ev']['label0'] = st(S4['pg'])['label']
    S5['pg'].click('.tabs button[data-mkt="WORLD"]')
    S5['ev']['t'] = time.time()
    S6['ev']['t'], S6['ev']['retry'] = t0, None
    pending = {'S3d': True, 'S3v': True, 'S4b': True, 'S5b': True, 'S2d': True}
    end = time.time() + 80
    while time.time() < end:
        now = time.time()
        # S3: a delta while hidden (kept, not drawn); visible again 8 s after the page closed the socket
        if pending['S3d'] and now - S3['ev']['t'] > 5:
            pending['S3d'] = False
            h3.delta(h3.last, [move(h3.body, '005930', 1.03)])
            S3['ev']['want'] = next(x['p'] for x in h3.body['stocks'] if x['c'] == '005930')
            S3['pg'].wait_for_timeout(400)
            S3['ev']['p_hidden'] = S3['pg'].evaluate("KH.stock('005930').p")
            S3['ev']['v_hidden'] = st(S3['pg'])['v']
        c3 = h3.conns[0]
        if pending['S3v'] and c3.closed and now - c3.closed[2] > 8:
            pending['S3v'] = False
            S3['ev']['closed_after'] = c3.closed[2] - S3['ev']['t']
            S3['ev']['conns_hidden'] = len(h3.conns)
            S3['ev']['quotes_hidden'] = len(S3['rq'].plain()) - S3['ev']['hidden_quotes0']

            def resume(c, h=h3):
                c.send({'t': 'hello', 'proto': 1, 'ch': 'top', 'epoch': h.epoch, 'v': h.v, 'poll': 3000, 'phase': 'live', 'now': ms()})
                h.delta(c, [move(h.body, '000660', 1.01)])
            h3.queue = [resume]
            S3['pg'].evaluate('__hide(false)')
            S3['ev']['visible'] = time.time()
        # S4: replay off once the page closed its socket
        c4 = S4['hub'].conns[0]
        if pending['S4b'] and c4.closed:
            pending['S4b'] = False
            S4['ev']['closed_after'] = c4.closed[2] - S4['ev']['t']
            S4['ev']['conns_during'] = len(S4['hub'].conns)
            S4['pg'].evaluate('KH.setReplay(null)')
            S4['ev']['back'] = time.time()
        c5 = S5['hub'].conns[0]
        if pending['S5b'] and c5.closed and now - c5.closed[2] > 1.5:
            pending['S5b'] = False
            S5['ev']['closed_after'] = c5.closed[2] - S5['ev']['t']
            S5['ev']['label_away'] = st(S5['pg'])['label']
            S5['ev']['conns_during'] = len(S5['hub'].conns)
            S5['pg'].click('.tabs button[data-mkt="K"]')
            S5['ev']['back'] = time.time()
        # S2: once the poll is back (30 s), a value → 실시간 again
        if pending['S2d'] and S2['rq'].plain(S2['ev']['t'] + 1):
            pending['S2d'] = False
            S2['ev']['poll_after'] = S2['rq'].plain(S2['ev']['t'] + 1)[0] - S2['ev']['t']
            S2['ev']['label_fb'] = st(S2['pg'])['label']
            S2['ev']['open_fb'] = c2.closed is None
            h2 = S2['hub']
            h2.delta(c2, [move(h2.body, '005930', 1.01)])
            S2['pg'].wait_for_timeout(500)
            s = st(S2['pg'])
            S2['ev']['after'] = (s['label'], s['paused'])
        done = (not any(pending.values()) and len(S1['hub'].conns) >= 2 and len(S6['hub'].conns) >= 2 and len(S7['hub'].conns) >= 3
                and len(h3.conns) >= 2 and len(S4['hub'].conns) >= 2 and len(S5['hub'].conns) >= 2)
        if done and now - tl > 50:
            break
        S1['pg'].wait_for_timeout(400)
    for x in pages.values():
        x['pg'].wait_for_timeout(1500)
        break

    # S1 silence
    c1 = S1['hub'].conns[0]
    gap = (c1.closed[2] - S1['ev']['t']) if c1.closed else None
    s = st(S1['pg'])
    q = S1['rq'].plain(c1.closed[2] - 0.2) if c1.closed else []
    re1 = (S1['hub'].conns[1].at - c1.closed[2]) if len(S1['hub'].conns) > 1 and c1.closed else None
    check('B3 silence 45 s → the page drops the socket, polls at once, reconnects after ~1 s (backoff 1 s ±25 %) → 실시간',
          gap is not None and 44 <= gap <= 48.5 and bool(q) and q[0] - c1.closed[2] < 1.5 and re1 is not None and 0.6 <= re1 <= 1.9 and s['label'] == 'live',
          f'gap {gap and round(gap, 1)} s · poll {q and round(q[0] - c1.closed[2], 2)} s · reconnect {re1 and round(re1, 2)} s · {s["label"]}')
    # S2 stale
    e = S2['ev']
    check('B3 시세 지연 for 30 s → the quotes poll comes back while the socket stays, label 10초마다 갱신; a value → 실시간 + paused',
          e.get('poll_after') is not None and 29 <= e['poll_after'] <= 32 and e.get('open_fb') and e.get('label_fb') == 'polling' and e.get('after') == ('live', True),
          {k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k != 't'})
    # S3 hidden
    e = S3['ev']
    s = st(S3['pg'])
    c3b = h3.conns[1] if len(h3.conns) > 1 else None
    check('B3 hidden tab: the delta is kept but not drawn; the socket closes after 30 s; no connection, no poll while hidden',
          e.get('p_hidden') == e.get('p_before') and e.get('v_hidden', 0) == 3 and e.get('closed_after') is not None and 29.5 <= e['closed_after'] <= 32 and e.get('conns_hidden') == 1 and e.get('quotes_hidden') == 0,
          {k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k in ('p_before', 'p_hidden', 'v_hidden', 'closed_after', 'conns_hidden', 'quotes_hidden')})
    check('B3 visible again → one connection that resumes (epoch=e1&ver=3), deltas only, the hidden value drawn',
          c3b is not None and 'epoch=e1' in c3b.url and 'ver=3' in c3b.url and c3b.at - e['visible'] < 1.5 and s['snaps'] == 1 and s['label'] == 'live'
          and S3['pg'].evaluate("KH.stock('005930').p") == e.get('want') and S3['pg'].evaluate("KH.stock('000660').p") == next(x['p'] for x in h3.body['stocks'] if x['c'] == '000660'),
          f"{c3b.url if c3b else None} snaps {s['snaps']} {s['label']}")
    # S4 replay
    e = S4['ev']
    s = st(S4['pg'])
    check('B3 다시 보기: no mark at once, the socket closes after 30 s, none while it plays; off → connects → 실시간',
          e['label0'] == '' and e.get('closed_after') is not None and 29.5 <= e['closed_after'] <= 32 and e.get('conns_during') == 1 and len(S4['hub'].conns) == 2 and S4['hub'].conns[1].at - e['back'] < 1.5 and s['label'] == 'live',
          {k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k in ('label0', 'closed_after', 'conns_during')})
    # S5 world
    e = S5['ev']
    s = st(S5['pg'])
    check('B3 해외 tab: the socket closes after 30 s (10초마다 갱신 meanwhile after), none while there; back to 코스피 → 실시간',
          e.get('closed_after') is not None and 29.5 <= e['closed_after'] <= 32 and e.get('label_away') == 'polling' and e.get('conns_during') == 1 and len(S5['hub'].conns) == 2 and s['label'] == 'live',
          {k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k in ('closed_after', 'label_away', 'conns_during')})
    # S6 closed → retryAt (+0–60 s)
    h6 = S6['hub']
    c6 = h6.conns
    dt = (c6[1].at - c6[0].at) if len(c6) > 1 else None
    s = st(S6['pg'])
    check("B3 off closed (retryAt +4 s): no mark, no connection before retryAt; the next one inside retryAt … +60 s → 실시간",
          dt is not None and 4 <= dt <= 65.5 and s['label'] == 'live', f'next connection after {dt and round(dt, 1)} s · {s["label"]}')
    # S7 error twice → 15 s, then the same refusal again → doubled
    c7 = S7['hub'].conns
    d1 = (c7[1].at - c7[0].at) if len(c7) > 1 else None
    d2 = (c7[2].at - c7[1].at) if len(c7) > 2 else None
    s = st(S7['pg'])
    check('B3 off error (retryAt +3 s) → waits ≥ 15 s (×1–1.25); the same refusal again → doubled (30–37.5 s) → 실시간',
          d1 is not None and 14.8 <= d1 <= 19.5 and d2 is not None and 29.8 <= d2 <= 38.5 and s['label'] == 'live', f'{d1 and round(d1, 1)} s, {d2 and round(d2, 1)} s · {s["label"]}')
    for x in pages.values():
        x['ctx'].close()


def b_epoch(br):
    ctx, pg, hub, rq = mock_page(br, 1280, store={'market': 'K'}, tag='B5')
    wait_label(pg, 'live', 8)
    c1 = hub.last
    hub.delta(c1, [move(hub.body, '005930', 1.02)])
    pg.wait_for_timeout(400)

    def renewed(c):
        hub.epoch, hub.v = 'e2', 7
        b = make_body()
        for r in b['stocks']:
            base = r['p'] - r['d']
            r['p'] = int(round(r['p'] * 1.013)) + 1
            r['d'] = r['p'] - base
            r['r'] = round(r['d'] / base * 100, 2) if base else 0
            if 'nx' in r:
                r['nx'].update(p=r['p'], d=r['d'], r=r['r'])
        hub.body = b
        hub.greet(c)
    hub.queue = [renewed]
    c1.ws.close(code=1012, reason='restart')
    pg.wait_for_timeout(250)
    s1 = st(pg)
    s = wait_label(pg, 'live', 6)
    c2 = hub.last
    chk = pg.evaluate(ROWS_MATCH_JS)
    want = {x['c']: x['p'] for x in hub.body['stocks']}
    drawn = pg.evaluate('Object.fromEntries(KH.stocks().map(s => [s.c, s.p]))')
    stale = [c for c, p in want.items() if drawn.get(c) != p]
    check('B5 the hub restarts (close 1012) → 다시 연결하는 중 → one connection resuming epoch=e1&ver=2',
          s1['label'] == 'reconnecting' and len(hub.conns) == 2 and 'epoch=e1' in c2.url and 'ver=2' in c2.url, f"{s1['label']} {c2.url}")
    check('B5 a new epoch → its snapshot replaces every row: 600 of 600 drawn at the new prices, no stale tile',
          s['epoch'] == 'e2' and s['v'] == 7 and s['snaps'] == 2 and chk['nbad'] == 0 and not stale and len(drawn) == 600, f"stale {len(stale)} {stale[:3]} rows {len(drawn)}")
    ctx.close()


def b_no_connect(br):
    for name, store in (('전체 at load', {'topN': 'all', 'market': 'K'}), ('해외 at load', {'market': 'WORLD'}), ('지표 at load', {'market': 'CMDTY'})):
        ctx, pg, hub, rq = mock_page(br, 1280, store=store, tag=f'B-{name}')
        pg.wait_for_timeout(4000)
        s = st(pg)
        check(f'B6 {name}: no connection, no mark', len(hub.conns) == 0 and s['label'] in ('', 'polling') and s['socket'] == -1, f"conns {len(hub.conns)} label {s['label']!r}")
        if name.startswith('해외'):
            pg.click('.tabs button[data-mkt="K"]')
            s = wait_label(pg, 'live', 5)
            check('B6 해외 → 코스피: connects → 실시간', len(hub.conns) == 1 and s['label'] == 'live')
        ctx.close()
    ctx = context(br, 1280)
    pg = ctx.new_page()
    ERR.attach(pg, 'B-snapshot')
    ws = []
    pg.on('websocket', lambda w: ws.append(w.url))
    pg.goto(SNAP_URL)
    pg.wait_for_timeout(2500)
    r = pg.evaluate("[typeof window.KHLive, document.getElementById('live-mark').hidden, KH.MODE, KH.feed({stocks:[{c:'005930'}]}), !!document.querySelector('[data-set=\"live\"]')]")
    check('B6 snapshot (dist/): no WebSocket, no module, no mark, KH.feed refuses, no setting row', not ws and r == ['undefined', True, 'snapshot', False, False], f'{ws} {r}')
    ctx.close()


def b_layout(br):
    """5 widths × 4 themes with the mark shown: overflow 0, the mark inside the screen, no overlap, the map top as with the mark off"""
    for w, h in SIZES:
        for th in THEMES:
            ctx, pg, hub, rq = mock_page(br, w, h, store={'theme': th, 'market': 'K'}, tag=f'B{w}-{th}')
            s = wait_label(pg, 'live', 8)
            pg.wait_for_timeout(300)
            a = pg.evaluate(MARK_JS)
            setting(pg, False)
            pg.wait_for_timeout(400)
            b = pg.evaluate(MARK_JS)
            ok = (s['label'] == 'live' and a['shown'] and a['over'] == 0 and a['mark'][1] <= a['vw'] + 0.5 and a['mark'][0] >= 0 and not a['clash']
                  and abs(a['mapTop'] - b['mapTop']) < 0.5 and abs(a['headH'] - b['headH']) < 0.5 and b['over'] == 0)
            check(f'B7 {w}×{h} {th}: 실시간 shown, overflow 0, no overlap, map top {a["mapTop"]:.0f} = {b["mapTop"]:.0f} with it off', ok,
                  f"text {a['text']!r} mark {a['mark']} clash {a['clash']} over {a['over']}/{b['over']} head {a['headH']:.1f}/{b['headH']:.1f}")
            if th == 'base' or (w in (390, 1280)):
                setting(pg, True)
                wait_label(pg, 'live', 6)
                pg.wait_for_timeout(300)
                shot(pg, f'{w}_{th}')
            ctx.close()
    # every label at 390 × 844 (base) and 360 (clock 둘 다): same header, same map top
    for w, h in ((390, 844), (360, 740)):
        ctx, pg, hub, rq = mock_page(br, w, h, store={'theme': 'base', 'market': 'K', 'set.clockStyle': 'both'}, mode='hello', tag=f'B{w}-labels')
        tops = {}
        s = wait_label(pg, 'connecting', 5)
        tops['connecting'] = pg.evaluate(MARK_JS)
        c = hub.last
        hub.snap(c)
        wait_label(pg, 'live', 4)
        tops['live'] = pg.evaluate(MARK_JS)
        c.send({'t': 'st', 'ok': False, 'msg': 'x', 'retryMs': 6000, 'at': ms()})
        wait_label(pg, 'delayed', 3)
        tops['delayed'] = pg.evaluate(MARK_JS)
        shot(pg, f'{w}_delayed')
        hub.queue = ['hello']
        c.ws.close(code=1011, reason='x')
        wait_label(pg, 'reconnecting', 4)
        tops['reconnecting'] = pg.evaluate(MARK_JS)
        shot(pg, f'{w}_reconnecting')
        hub.off(hub.last, 'full', 300) if wait_for(pg, lambda: len(hub.conns) >= 2, 4) else None
        wait_label(pg, 'polling', 3)
        tops['polling'] = pg.evaluate(MARK_JS)
        setting(pg, False)
        pg.wait_for_timeout(300)
        tops['off'] = pg.evaluate(MARK_JS)
        texts = {k: v['text'] for k, v in tops.items()}
        same = len({round(v['mapTop'], 1) for v in tops.values()}) == 1 and len({round(v['headH'], 1) for v in tops.values()}) == 1
        check(f'B7 {w}: every label (연결 중 · 실시간 · 지연 · 10초) keeps the header and the map top; overflow 0; no overlap',
              same and texts == {'connecting': '연결 중', 'live': '실시간', 'delayed': '지연', 'reconnecting': '연결 중', 'polling': '10초', 'off': ''}
              and all(v['over'] == 0 and not v['clash'] for v in tops.values()),
              f"{texts} tops {[round(v['mapTop'], 1) for v in tops.values()]}")
        ctx.close()
    # desktop: the longest word (다시 연결하는 중) at 1280 and 768
    for w, h in ((1280, 800), (768, 1024)):
        ctx, pg, hub, rq = mock_page(br, w, h, store={'theme': 'base', 'market': 'K'}, tag=f'B{w}-long')
        wait_label(pg, 'live', 6)
        a = pg.evaluate(MARK_JS)
        hub.queue = ['hello']
        hub.last.ws.close(code=1011, reason='x')
        wait_label(pg, 'reconnecting', 4)
        pg.wait_for_timeout(200)
        b = pg.evaluate(MARK_JS)
        shot(pg, f'{w}_reconnecting')
        check(f'B7 {w}: 다시 연결하는 중 fits (overflow 0, no overlap, header and map top unchanged)',
              b['text'] == '다시 연결하는 중' and b['over'] == 0 and not b['clash'] and abs(a['mapTop'] - b['mapTop']) < 0.5 and abs(a['headH'] - b['headH']) < 0.5,
              f"{b['text']!r} {b['mark']} top {a['mapTop']:.1f}/{b['mapTop']:.1f}")
        ctx.close()


def part_b(br):
    print('── B · scripted hub (routeWebSocket on the API mock page) ──', flush=True)
    n0 = len(ERR.items)
    b_basics(br)
    b_refusals(br)
    b_epoch(br)
    b_no_connect(br)
    b_long(br)
    b_layout(br)
    errs = ERR.items[n0:]
    check('B no console errors / warnings / page errors', not errs, errs[:4])


# ═════════════════════════ A · the real hub (wrangler dev) ═════════════════════════
def real_page(br, w, h=None, store=None, tag='A', errs=None):
    ctx = context(br, w, h, store)
    ctx.route(re.compile(r'^http://127\.0\.0\.1:%d/api/(?!quotes(\?|$)|live)' % P['dev']), fwd_api)
    pg = ctx.new_page()
    (errs or ERR).attach(pg, tag)
    rq = Reqs(pg)
    ws = []
    pg.on('websocket', lambda x: ws.append((time.time(), x.url)))
    pg.goto(DEV)
    return ctx, pg, rq, ws


def part_a(br, persist):
    print('── A · the real hub: wrangler dev + Naver-shaped mock ──', flush=True)
    EA = Errors()
    ctx, pg, rq, ws = real_page(br, 1280, store={'market': 'K'}, errs=EA)
    t0 = time.time()
    s = wait_label(pg, 'live', 25)
    t_live = time.time()
    check('A1 connects → hello → snapshot (600 rows) → 실시간', s and s['label'] == 'live' and s['rows'] == 600 and s['snaps'] == 1,
          f"{s and s['label']} in {t_live - t0:.1f} s, rows {s and s['rows']}, epoch {s and s['epoch']}")
    movers0, secs0 = pg.inner_text('#movers'), pg.inner_text('#secs')
    kd0, fl0 = pg.evaluate('__kd.length'), pg.evaluate('__fl.length')
    pg.wait_for_timeout(16000)
    s = st(pg)
    kd = pg.evaluate(f'__kd.slice({kd0})')
    fl = pg.evaluate(f'__fl.slice({fl0})')
    q = rq.plain(t_live + 0.5)
    check('A1 deltas every ~3 s, each drawn once (KH.feed); the quotes poll paused (0 requests in 16 s)',
          s['deltas'] >= 4 and s['feeds'] >= 5 and not q and s['paused'], f"deltas {s['deltas']} feeds {s['feeds']} polls {len(q)} feed {s['feedMs']} ms (max {s['feedMax']})")
    chk = pg.evaluate(ROWS_MATCH_JS)
    check('A1 every streamed tile = the hub row (p, r) — 600 of 600', chk['n'] == 600 and chk['nbad'] == 0, chk)
    check("A1 'kh:data' with changed codes and flashing tiles (효과 기본)", sum(1 for x in kd if x['n']) >= 3 and len(fl) >= 3, f"kh:data {len(kd)} ({sum(x['n'] for x in kd)} codes) flashes {len(fl)}")
    movers1, secs1 = pg.inner_text('#movers'), pg.inner_text('#secs')
    check('A1 side cards follow the stream (눈에 띄는 종목 · 섹터별 등락 changed)', movers1 != movers0 and secs1 != secs0)
    tk = pg.evaluate("""(() => { const e = document.querySelector('#strip .xs-item[data-k="KOSPI"]'); const x = KH.index().KOSPI;
      return [e ? (e.getAttribute('aria-label') || '') : '', x ? x.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '']; })()""")
    check('A1 the ticker shows the streamed index (KH.index from the deltas)', tk[1] and tk[1] in tk[0], tk)
    shot(pg, 'A_1280_live')

    # hidden 31 s → closed; visible → resume (no snapshot)
    snaps0, ep0, n_ws = s['snaps'], s['epoch'], len(ws)
    pg.evaluate('__hide(true)')
    th = time.time()
    closed = wait_for(pg, lambda: st(pg)['socket'] == -1, 34, 500)
    tc = time.time()
    v_before = st(pg)['v']
    pg.wait_for_timeout(2000)
    check('A2 hidden tab: the page closes its socket after ~30 s and opens none while hidden', closed and 29.5 <= tc - th <= 33 and len(ws) == n_ws, f'{tc - th:.1f} s, sockets {len(ws) - n_ws}')
    pg.evaluate('__hide(false)')
    tv = time.time()
    s = wait_for(pg, lambda: (st(pg)['deltas'] > 0 and len(ws) > n_ws and st(pg)['label'] == 'live' and st(pg)['v'] > v_before) and st(pg), 15)
    url = ws[-1][1] if len(ws) > n_ws else ''
    check('A2 visible → one connection resuming (epoch & ver), deltas only (no snapshot), 실시간',
          bool(s) and f'epoch={ep0}' in url and f'ver={v_before}' in url and s['snaps'] == snaps0 and s['epoch'] == ep0 and ws[-1][0] - tv < 1.5,
          f"{url.split('?')[-1]} snaps {s and s['snaps']}")
    pg.wait_for_timeout(3500)
    chk = pg.evaluate(ROWS_MATCH_JS)
    check('A2 … tiles = hub rows after the resume', chk['n'] == 600 and chk['nbad'] == 0, chk)

    # restart the Worker: new hub instance = new epoch → snapshot
    EA.allow = ['WebSocket connection to', 'Failed to load resource', 'ERR_CONNECTION_REFUSED', 'net::ERR']
    s = st(pg)
    ep0, snaps0 = s['epoch'], s['snaps']
    stop(A_PROC['wr'])
    free(P['dev'], P['insp'])
    tk_ = time.time()
    lab = wait_for(pg, lambda: st(pg)['label'] in ('reconnecting', 'polling') and st(pg)['label'], 6)
    check('A3 Worker gone → 다시 연결하는 중 (the quotes poll is back meanwhile)', lab == 'reconnecting' and not st(pg)['paused'], lab)
    pg.wait_for_timeout(6000)
    A_PROC['wr'] = wrangler(persist)
    tu = time.time()
    s = wait_for(pg, lambda: st(pg)['label'] == 'live' and st(pg)['epoch'] != ep0 and st(pg), 75, 500)
    tl = time.time()
    EA.allow = []
    check('A3 Worker back → a new epoch → its snapshot → 실시간 (backoff ≤ 30 s ±25 %)', bool(s) and s['snaps'] == snaps0 + 1 and tl - tu < 40,
          f"down {tu - tk_:.0f} s, live {tl - tu:.1f} s after up, fails before {s and s['fails']}, epoch {s and s['epoch']}")
    pg.wait_for_timeout(3500)
    chk = pg.evaluate(ROWS_MATCH_JS)
    check('A3 no stale tile after the new snapshot: 600 of 600 = the hub rows', chk['n'] == 600 and chk['nbad'] == 0, chk)
    ctx.close()

    # phones in a real session (basis chip + clock 둘 다): the row stays one row, the map top stays
    for w, h in ((390, 844), (360, 740)):
        ctx, pg, rq, ws = real_page(br, w, h, store={'market': 'K', 'theme': 'base', 'set.clockStyle': 'both'}, tag=f'A{w}', errs=EA)
        s = wait_label(pg, 'live', 20)
        pg.wait_for_timeout(6500)
        a = pg.evaluate(MARK_JS)
        s = st(pg)
        shot(pg, f'A_{w}_live')
        setting(pg, False)
        pg.wait_for_timeout(500)
        b = pg.evaluate(MARK_JS)
        bchip = pg.evaluate("(() => { const b = document.getElementById('bchip'); return b && !b.hidden && getComputedStyle(b).display !== 'none' ? b.textContent : ''; })()")
        check(f'A4 {w}: 실시간 next to the basis chip — one header row, overflow 0, no overlap, map top {a["mapTop"]:.0f} = {b["mapTop"]:.0f} without it',
              a['shown'] and a['text'] == '실시간' and a['over'] == 0 and not a['clash'] and abs(a['mapTop'] - b['mapTop']) < 0.5 and abs(a['headH'] - b['headH']) < 0.5,
              f"chip {bchip!r} mark {a['mark']} clash {a['clash']} head {a['headH']:.1f}/{b['headH']:.1f} feed {s['feedMs']} ms (max {s['feedMax']})")
        ctx.close()
    check('A no console errors / warnings outside the restart window', not EA.items, EA.items[:4])


A_PROC = {}


def main():
    free(*P.values())
    start([sys.executable, str(ROOT / 'qa/news/mock_api.py'), str(P['api'])], '/tmp/live_qa_api.log')
    if not wait_http(API + 'api/time', 20):
        raise SystemExit('API mock did not start')
    persist = None
    if ONLY != 'B':
        start([sys.executable, '-m', 'http.server', str(P['web']), '--bind', '127.0.0.1', '-d', str(ROOT / 'web')], '/tmp/live_qa_web.log')
        margs = ['node', str(ROOT / 'prototypes/realtime/upstream_mock.mjs'), '--port', str(P['naver']), '--churn', '0.3']
        if os.environ.get('LIVE_QA_FRAMES'):
            margs += ['--frames', os.environ['LIVE_QA_FRAMES']]
        start(margs, '/tmp/live_qa_naver.log', {'NODE_USE_ENV_PROXY': '1'})
        end = time.time() + 90
        while time.time() < end and 'upstream mock on' not in open('/tmp/live_qa_naver.log').read():
            time.sleep(0.5)
        if 'upstream mock on' not in open('/tmp/live_qa_naver.log').read():
            print(open('/tmp/live_qa_naver.log').read()[-2000:])
            raise SystemExit('the Naver-shaped mock did not start (it needs Naver once: NODE_USE_ENV_PROXY=1)')
        persist = tempfile.mkdtemp(prefix='live-qa-')
        A_PROC['wr'] = wrangler(persist)
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        if ONLY != 'B':
            part_a(br, persist)
        if ONLY != 'A':
            part_b(br)
        br.close()
    n_ok = sum(1 for _, ok in results if ok)
    print(f'\n{n_ok}/{len(results)} passed', flush=True)
    return 0 if n_ok == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
