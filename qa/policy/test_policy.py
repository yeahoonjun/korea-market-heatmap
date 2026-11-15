#!/usr/bin/env python3
"""QA for the 정책 자료 tab of the news card (src/policy, docs/standards/policy-feeds.md §5) on the built pages.

  python3 scripts/build_page.py && python3 qa/policy/test_policy.py

Starts qa/policy/mock_api.py on POLICY_QA_PORT (default 8970) and stops it at the end; screenshots → qa/shots/policy/
(390×844 · 1440×900 × 기본 · 글라스 밝게, + a few states). Exit 1 if any check fails.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORT = int(os.environ.get('POLICY_QA_PORT', 8970))
LIVE = f'http://127.0.0.1:{PORT}/'
SNAP = (ROOT / 'dist/index.html').as_uri()
SHOTS = ROOT / 'qa/shots/policy'
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FIX = json.loads((HERE / 'fixtures/policy.json').read_text(encoding='utf-8'))
N_ALL, N_KDI, N_GB = len(FIX['items']), sum(x['src'] == 'kdi' for x in FIX['items']), sum(x['src'] == 'gwanbo' for x in FIX['items'])
results, shots = [], []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail != '' else ''), flush=True)


def mock(path):
    with NOPROXY.open(LIVE.rstrip('/') + path, timeout=10) as r:
        return json.loads(r.read())


def mode(m, reset=True):
    if reset:
        mock('/__reset')
    mock('/__mode?policy=' + m)


class Errors:
    def __init__(self):
        self.items = []

    def attach(self, page):
        page.on('console', lambda m: self.items.append(m.text[:160]) if m.type == 'error' else None)
        page.on('pageerror', lambda e: self.items.append(f'pageerror: {e}'))


def open_page(br, url, w, h, theme='base', motion='standard', errors=None, feed=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    init = "try{localStorage.setItem('khm.theme', %s);localStorage.setItem('khm.motion', %s);localStorage.setItem('khm.tickerPaused','true')" % (
        json.dumps(json.dumps(theme)), json.dumps(json.dumps(motion)))
    if feed:
        init += ";localStorage.setItem('khm.feedTab', %s)" % json.dumps(json.dumps(feed))
    ctx.add_init_script(init + "}catch(e){}")
    pg = ctx.new_page()
    if errors is not None:
        errors.attach(pg)
    pg.goto(url)
    pg.wait_for_timeout(1200)
    return ctx, pg


def to_card(pg):
    pg.evaluate("document.getElementById('news').scrollIntoView({block: 'center'})")
    pg.wait_for_timeout(300)


def pick_policy(pg):
    to_card(pg)
    pg.click('#news-t-policy')
    pg.wait_for_selector('#news-p-policy .pl-row:not(.skel), #news-p-policy .pl-msg', timeout=8000)
    pg.wait_for_timeout(500)


ROWS_JS = r"""() => [...document.querySelectorAll('#news-p-policy .pl-row:not(.skel)')].map(li => {
  const a = li.querySelector('.pl-tt a'), src = li.querySelector('.pl-src'), r = li.getBoundingClientRect();
  return {src: li.dataset.src, href: a && a.href, target: a && a.target, rel: a && a.rel, aria: a && a.getAttribute('aria-label'), title: a && a.textContent,
          time: li.querySelector('time').textContent, dt: li.querySelector('time').getAttribute('datetime'), badge: src && getComputedStyle(src).display !== 'none' ? src.textContent : '',
          org: li.querySelector('.pl-org').textContent, h: r.height, w: r.width};
})"""
CHIPS_JS = r"""() => [...document.querySelectorAll('#news-p-policy .pl-chip')].map(b => ({k: b.dataset.k, pressed: b.getAttribute('aria-pressed'), off: b.getAttribute('aria-disabled') === 'true',
  n: b.querySelector('.pl-n').textContent, h: b.getBoundingClientRect().height, before: parseFloat(getComputedStyle(b, '::before').height) || 0}))"""
TABS_JS = r"""() => [...document.querySelectorAll('#news .nw-tt button[role="tab"]')].map(b => ({k: b.dataset.k, sel: b.getAttribute('aria-selected'), text: b.textContent.trim(), h: b.getBoundingClientRect().height}))"""
FOOT_JS = r"""() => { const f = document.getElementById('foot'); return [...f.children].map(p => (p.id || p.className || 'p') + (p.hidden ? '(hidden)' : '') + ':' + p.textContent.trim().slice(0, 40)); }"""
# the rows reach 6px past the pane on purpose (hover tint, as the news rows) — the card (padding) must not overflow
OVER_JS = r"""() => { const d = document.documentElement, c = document.getElementById('news');
  return {page: d.scrollWidth - innerWidth, pane: c ? c.scrollWidth - c.clientWidth : 0, rows: [...document.querySelectorAll('#news-p-policy .pl-row')].filter(li => li.scrollWidth > li.clientWidth + 1).length}; }"""
STYLE_JS = r"""() => {
  const probe = v => { const s = document.createElement('span'); s.style.color = `var(${v})`; document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; };
  const up = probe('--up-text'), dn = probe('--dn-text'), acc = probe('--acc');
  const els = [...document.querySelectorAll('#news-p-policy *')].filter(e => e.offsetParent || e.getClientRects().length);
  const small = els.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 11).map(e => e.className + ' ' + getComputedStyle(e).fontSize);
  const rg = els.filter(e => { const c = getComputedStyle(e).color; return c === up || c === dn; }).map(e => e.className);
  const amberText = els.filter(e => getComputedStyle(e).color === acc && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => e.className);
  return {small, rg, amberText, n: els.length};
}"""


def shot(pg, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    p = SHOTS / name
    pg.screenshot(path=str(p))
    shots.append(str(p))


def run(br):
    # 1 · desktop 1440 × 900: the tab, polling only when shown, rows, filters, 더보기, footer, other tabs
    mode('ok')
    err = Errors()
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=err)
    to_card(pg)
    pg.wait_for_selector('#news .nw-row:not(.skel)', timeout=8000)
    tabs = pg.evaluate(TABS_JS)
    check('title tabs: 시장 뉴스 · 오늘 공시 · 정책 자료 (third)', [t['k'] for t in tabs] == ['news', 'disc', 'policy'] and tabs[2]['text'] == '정책 자료', tabs)
    pg.wait_for_timeout(1500)
    st = mock('/__stats')
    check('not shown → /api/policy not called', st.get('/api/policy', 0) == 0, st.get('/api/policy', 0))
    foot = pg.evaluate(FOOT_JS)
    ids = [x.split(':')[0] for x in foot]
    check('footer: 정책 자료 line right after 공시, above © and the disclaimer (last)', 'foot-policy' in ids and ids.index('foot-policy') == ids.index('foot-disc') + 1 and ids[-1] == 'disclaim' and ids[-2] == 'credit'
          and any(x.startswith('foot-policy:정책 자료: KDI 경제정보센터 RSS · 행정안전부 관보') for x in foot), foot)
    h_news = pg.evaluate("document.getElementById('news').getBoundingClientRect().height")
    pick_policy(pg)
    st = mock('/__stats')
    check('shown → one /api/policy request', st.get('/api/policy', 0) == 1, st.get('/api/policy', 0))
    rows = pg.evaluate(ROWS_JS)
    check('rows drawn (≥ 5, the card fill)', len(rows) >= 5, len(rows))
    check('links: new tab · noopener · https on eiec.kdi.re.kr / gwanbo.go.kr', all(r['target'] == '_blank' and 'noopener' in r['rel'] and (r['href'].startswith('https://eiec.kdi.re.kr/policy/materialView.do?num=') or r['href'].startswith('https://gwanbo.go.kr/')) for r in rows), rows[0])
    check('link names say the source and "새 탭에서 열려요"', all('새 탭에서 열려요' in r['aria'] and ('KDI 경제정보센터' in r['aria'] or '행정안전부 관보' in r['aria']) for r in rows), rows[0]['aria'])
    check('전체: both sources, badge shown, sources take turns', {r['src'] for r in rows} == {'kdi', 'gwanbo'} and all(r['badge'] in ('KDI', '관보') for r in rows) and [r['src'] for r in rows[:4]] == ['kdi', 'gwanbo', 'kdi', 'gwanbo'], [r['src'] for r in rows[:6]])
    check('date column: 오늘 for today, datetime = the day', rows[0]['time'] == '오늘' and len(rows[0]['dt']) == 10, (rows[0]['time'], rows[0]['dt']))
    check('agency column: KDI = 기관, 관보 = 기관 · 편집구분', any(r['src'] == 'kdi' and r['org'] == '재정경제부' for r in rows) and all(' · ' in r['org'] for r in rows if r['src'] == 'gwanbo'), [r['org'] for r in rows[:4]])
    head = pg.inner_text('#news .nw-at')
    check('head: "HH:MM 기준"', head.endswith('기준') and ':' in head, head)
    chips = pg.evaluate(CHIPS_JS)
    check(f'chips 전체 {N_ALL} · KDI {N_KDI} · 관보 {N_GB}, 전체 pressed', [c['n'] for c in chips] == [str(N_ALL), str(N_KDI), str(N_GB)] and chips[0]['pressed'] == 'true' and not any(c['off'] for c in chips), chips)
    pg.click('#news-p-policy .pl-chip[data-k="kdi"]'); pg.wait_for_timeout(250)
    r2 = pg.evaluate(ROWS_JS)
    check('filter KDI: only KDI rows, badge hidden', r2 and all(r['src'] == 'kdi' and r['badge'] == '' for r in r2), [r['src'] for r in r2][:5])
    pg.click('#news-p-policy .pl-chip[data-k="gwanbo"]'); pg.wait_for_timeout(250)
    r3 = pg.evaluate(ROWS_JS)
    check('filter 관보: only 관보 rows', r3 and all(r['src'] == 'gwanbo' for r in r3), len(r3))
    check('aria-pressed follows', [c['pressed'] for c in pg.evaluate(CHIPS_JS)] == ['false', 'false', 'true'])
    pg.click('#news-p-policy .pl-chip[data-k="all"]'); pg.wait_for_timeout(250)
    base = len(pg.evaluate(ROWS_JS))
    more = pg.locator('#news-p-policy .pl-more')
    check('더보기 shows the total (30)', more.is_visible() and '30' in (more.get_attribute('aria-label') or ''), more.get_attribute('aria-label'))
    more.click(); pg.wait_for_timeout(400)
    check('더보기 → 30 rows', len(pg.evaluate(ROWS_JS)) == 30, len(pg.evaluate(ROWS_JS)))
    more.click(); pg.wait_for_timeout(400)
    check('접기 → back to the first count', len(pg.evaluate(ROWS_JS)) == base, len(pg.evaluate(ROWS_JS)))
    h_pol = pg.evaluate("document.getElementById('news').getBoundingClientRect().height")
    check('card height the same on 시장 뉴스 and 정책 자료 (PC fill)', abs(h_pol - h_news) <= 1, f'{h_news:.0f} / {h_pol:.0f}')
    sty = pg.evaluate(STYLE_JS)
    check('no text under 11px in the pane', not sty['small'], sty['small'][:3])
    check('no red / green in the pane (no price data)', not sty['rg'], sty['rg'][:3])
    check('no amber text in the pane (amber = chosen chip · focus only)', not sty['amberText'], sty['amberText'][:3])
    ov = pg.evaluate(OVER_JS)
    check('1440: no horizontal overflow (page · pane · rows)', ov['page'] <= 0 and ov['pane'] <= 0 and ov['rows'] == 0, ov)
    shot(pg, 'policy_1440x900_base.png')
    # keyboard: ←/→ on the title tabs
    pg.focus('#news-t-policy'); pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(300)
    check('← from 정책 자료 → 오늘 공시', pg.evaluate("document.activeElement.dataset.k") == 'disc')
    pg.wait_for_selector('#news-p-disc .dc-row:not(.skel), #news-p-disc .nw-msg', timeout=8000)
    check('오늘 공시 still draws its rows', pg.locator('#news-p-disc .dc-row:not(.skel)').count() > 0, pg.locator('#news-p-disc .dc-row:not(.skel)').count())
    check('정책 자료 pane hidden while another tab is shown', pg.evaluate("document.getElementById('news-p-policy').hidden"))
    pg.keyboard.press('Home'); pg.wait_for_timeout(400)
    check('Home → 시장 뉴스 still draws its rows', pg.evaluate("document.activeElement.dataset.k") == 'news' and pg.locator('#news-p-news .nw-row:not(.skel)').count() > 0)
    pg.keyboard.press('End'); pg.wait_for_timeout(400)
    check('End → 정책 자료 again (no second request within 10 min)', pg.evaluate("document.activeElement.dataset.k") == 'policy' and mock('/__stats').get('/api/policy', 0) == 1, mock('/__stats').get('/api/policy', 0))
    # remembered tab
    pg.reload(); pg.wait_for_timeout(1500); to_card(pg)
    pg.wait_for_selector('#news-p-policy .pl-row:not(.skel)', timeout=8000)
    check('reload → 정책 자료 remembered (khm.feedTab) and loaded', [t['sel'] for t in pg.evaluate(TABS_JS)] == ['false', 'false', 'true'])
    check('console errors 0 (1440)', not err.items, err.items[:3])
    ctx.close()

    # 2 · glass-light 1440 shot
    ctx, pg = open_page(br, LIVE, 1440, 900, theme='glass-light', feed='policy')
    to_card(pg); pg.wait_for_selector('#news-p-policy .pl-row:not(.skel)', timeout=8000); pg.wait_for_timeout(500)
    shot(pg, 'policy_1440x900_glass-light.png')
    ctx.close()

    # 3 · phone 390 × 844 in every theme: overflow, touch targets, two-line titles
    for th in THEMES:
        err = Errors()
        ctx, pg = open_page(br, LIVE, 390, 844, theme=th, errors=err, feed='policy')
        pg.evaluate("document.getElementById('news').scrollIntoView({block: 'start'})"); pg.wait_for_timeout(300)
        pg.wait_for_selector('#news-p-policy .pl-row:not(.skel)', timeout=8000); pg.wait_for_timeout(500)
        pg.evaluate("window.scrollBy(0, -60)"); pg.wait_for_timeout(300)
        ov = pg.evaluate(OVER_JS)
        check(f'390 {th}: no horizontal overflow', ov['page'] <= 0 and ov['pane'] <= 0, ov)
        if th == 'base':
            rows = pg.evaluate(ROWS_JS)
            check('390: 5 rows, each ≥ 44px tall (the row is the link\'s target)', len(rows) == 5 and all(r['h'] >= 44 for r in rows), [round(r['h']) for r in rows])
            chips = pg.evaluate(CHIPS_JS)
            check('390: chips 32px, touch target 44px', all(c['h'] >= 32 and c['before'] >= 44 for c in chips), [(c['h'], c['before']) for c in chips])
            tabs = pg.evaluate(TABS_JS)
            check('390: title tabs 40px', all(t['h'] >= 40 for t in tabs), [t['h'] for t in tabs])
            box = pg.evaluate("(() => { const li = document.querySelector('#news-p-policy .pl-row'), a = li.querySelector('.pl-tt a'); const r = li.getBoundingClientRect(); const e = document.elementFromPoint(r.left + 6, r.bottom - 6); return a.contains(e) || e === a; })()")
            check('390: a tap anywhere on the row opens the headline link', box)
            more = pg.locator('#news-p-policy .pl-more')
            check('390: 더보기 full width, ≥ 44px', more.bounding_box()['height'] >= 44 and more.bounding_box()['width'] > 300, more.bounding_box())
            sty = pg.evaluate(STYLE_JS)
            check('390: no text under 11px', not sty['small'], sty['small'][:3])
        if th in ('base', 'glass-light'):
            shot(pg, f'policy_390x844_{th}.png')
        check(f'390 {th}: console errors 0', not err.items, err.items[:3])
        ctx.close()

    # 3b · other widths: 360 · 768 · 1280 · 1920 — no overflow, no console errors
    for (w, hh) in [(360, 740), (768, 1024), (1280, 800), (1920, 1080)]:
        err = Errors()
        ctx, pg = open_page(br, LIVE, w, hh, errors=err, feed='policy')
        to_card(pg); pg.wait_for_selector('#news-p-policy .pl-row:not(.skel)', timeout=8000); pg.wait_for_timeout(400)
        ov = pg.evaluate(OVER_JS)
        check(f'{w}: no horizontal overflow, rows drawn, console errors 0', ov['page'] <= 0 and ov['pane'] <= 0 and ov['rows'] == 0 and len(pg.evaluate(ROWS_JS)) >= 5 and not err.items, (ov, err.items[:2]))
        if w == 768:
            shot(pg, 'policy_768x1024_base.png')
        ctx.close()

    # 4 · states
    def state(m, w=1440, h=900, name=None):
        mode(m)
        ctx, pg = open_page(br, LIVE, w, h, feed='policy')
        to_card(pg)
        pg.wait_for_selector('#news-p-policy .pl-row:not(.skel), #news-p-policy .pl-msg', timeout=8000); pg.wait_for_timeout(700)
        if name:
            shot(pg, name)
        return ctx, pg
    ctx, pg = state('stale', name='policy_1440x900_base_stale.png')
    nt = pg.inner_text('#news-p-policy .pl-note')
    check('stale: one line "관보 새 자료를 받지 못했어요 · … 받은 목록이에요" + 다시 시도', '관보 새 자료를 받지 못했어요' in nt and '받은 목록이에요' in nt and pg.locator('#news-p-policy .pl-note .kasync').count() == 1, nt)
    check('stale: 관보 rows still listed', any(r['src'] == 'gwanbo' for r in pg.evaluate(ROWS_JS)))
    ctx.close()
    ctx, pg = state('nogb')
    nt = pg.inner_text('#news-p-policy .pl-note')
    chips = pg.evaluate(CHIPS_JS)
    check('관보 failed, no copy: note "관보를 불러오지 못했어요", 관보 chip off', '관보를 불러오지 못했어요' in nt and chips[2]['off'] and not chips[1]['off'], (nt, chips))
    foot = pg.evaluate(FOOT_JS)
    check('…and the footer credits only KDI', any(x.startswith('foot-policy:정책 자료: KDI 경제정보센터 RSS (제목') for x in foot), foot)
    ctx.close()
    ctx, pg = state('fail', name='policy_1440x900_base_fail.png')
    check('both failed: "정책 자료를 불러오지 못했어요" + 다시 시도', '정책 자료를 불러오지 못했어요' in pg.inner_text('#news-p-policy .pl-list') and pg.locator('#news-p-policy .pl-msg .kasync').count() == 1)
    mock('/__mode?policy=ok')
    pg.click('#news-p-policy .pl-msg .kasync'); pg.wait_for_selector('#news-p-policy .pl-row:not(.skel)', timeout=8000)
    check('다시 시도 → rows', len(pg.evaluate(ROWS_JS)) >= 5)
    ctx.close()
    ctx, pg = state('empty')
    check('empty: "아직 정책 자료가 없어요"', '아직 정책 자료가 없어요' in pg.inner_text('#news-p-policy .pl-list'))
    ctx.close()
    ctx, pg = state('yesterday')
    rows = pg.evaluate(ROWS_JS)
    check('another day: the date reads M/D', rows and '/' in rows[0]['time'] and rows[0]['time'] != '오늘', rows and rows[0]['time'])
    ctx.close()
    mode('none')
    err = Errors()
    ctx, pg = open_page(br, LIVE, 1440, 900, errors=err, feed='policy')
    to_card(pg); pg.wait_for_timeout(1500)
    check('404 (old Worker): the tab goes away, news · 공시 stay', [t['k'] for t in pg.evaluate(TABS_JS)] == ['news', 'disc'], [t['k'] for t in pg.evaluate(TABS_JS)])
    check('404: no 정책 자료 footer line', not any(x.startswith('foot-policy:') and '(hidden)' not in x.split(':')[0] for x in pg.evaluate(FOOT_JS)), pg.evaluate(FOOT_JS))
    check('404: console errors only the 404 itself', all('404' in e for e in err.items), err.items[:3])
    ctx.close()
    mode('ok')

    # 5 · the world tab hides the card; the footer line goes with the feed lines
    ctx, pg = open_page(br, LIVE + '#world', 1440, 900)
    pg.wait_for_timeout(800)
    check('해외 tab: no 정책 자료 footer line', not any(x.startswith('foot-policy') for x in pg.evaluate(FOOT_JS)), pg.evaluate(FOOT_JS))
    ctx.close()

    # 6 · snapshot (dist/, no network): the tab says where to look
    err = Errors()
    ctx, pg = open_page(br, SNAP, 1440, 900, errors=err, feed='policy')
    to_card(pg); pg.wait_for_timeout(500)
    txt = pg.inner_text('#news-p-policy') if pg.locator('#news-p-policy').count() else ''
    check('snapshot: "정책 자료는 실시간 버전에서 볼 수 있어요" + link', '정책 자료는 실시간 버전에서 볼 수 있어요' in txt and pg.locator('#news-p-policy a[href^="https://panse.pages.dev"]').count() == 1, txt[:60])
    check('snapshot: console errors 0', not err.items, err.items[:3])
    ctx.close()


def main():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                mock('/__reset'); break
            except Exception:
                time.sleep(0.1)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            run(br)
            br.close()
    finally:
        srv.terminate()
        srv.wait(5)
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} passed')
    for n in bad:
        print('  FAIL', n)
    print('shots:', *shots, sep='\n  ')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
