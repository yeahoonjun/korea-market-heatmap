#!/usr/bin/env python3
"""QA for the 오늘의 시장 요약 카드 (src/summary, docs/standards/market-summary.md, AGENTS §3-34) on the built pages.

  python3 scripts/build_page.py && python3 qa/summary/test_summary.py [--shots]

Starts qa/summary/mock_summary.py on SUMMARY_QA_PORT (default 8981; ports 8980–8988 only) and, for "the map does not move", a second
one on SUMMARY_QA_PORT + 1 serving the web/ of git rev SUMMARY_QA_BASE (default main) — the page without the card. Both are stopped with
fuser -k <port>/tcp at the end. The mock data is the 11/13 (금) close: 상한가 9 · 하한가 0 (snapshot lim), flows of 11/13.
Static: summary.css uses only design tokens for type, corners, colour, spacing and motion (design.md §2–§6); close.json carries lim.
Browser (live, 360 · 390 · 768 · 1440, 기본 테마; 390 · 1440 also 신문): the card's place (phone: right after the map, before #news;
tablet / desktop: first in .side), the map's box = the base build's, collapsed by default and after a reload (not remembered), no
horizontal overflow, no console errors, no "null/undefined/NaN", text ≥ 11 px, red / green only on numbers, no amber text / fill, touch
targets ≥ 44 px on phones — collapsed and expanded. Expand: the height grows from the band to the full table by the `open` spring
(sampled every frame: rises, overshoot ≤ 2 %, settles at the table's height), the table's text stays hidden until the band's text left
(§6-4); 접기 at the end collapses it (close spring) and puts focus on the top key. 글로 복사 → the clipboard text. The four phases'
words (?summary_phase=pre|open|after|closed). 움직임 줄이기: at once. Snapshot (dist/index.html, file://): the card from the snapshot.
--shots writes qa/shots/market_summary/impl_*.png. Exit 1 on a fail.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('SUMMARY_QA_PORT', 8981))
assert 8980 <= PORT <= 8988
URL = f'http://127.0.0.1:{PORT}/'
BASE_REV = os.environ.get('SUMMARY_QA_BASE', 'main')
OUT = ROOT / 'qa/shots/market_summary'
SHOTS = '--shots' in sys.argv
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
fails = []
counts = {'pass': 0}


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail not in ('', None, [], {}) else ''), flush=True)
    if ok:
        counts['pass'] += 1
    else:
        fails.append(name)


def lint_css():
    css = (ROOT / 'src/summary/summary.css').read_text(encoding='utf-8')
    body = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    bad = []
    for prop, val in re.findall(r'([a-z-]+)\s*:\s*([^;{}]+)', body):
        v = val.strip()
        if prop == 'font-size' and not re.fullmatch(r'var\(--fs-[a-z0-9]+\)', v):
            bad.append(f'{prop}:{v}')
        if prop == 'border-radius' and not all(re.fullmatch(r'var\(--(r-[a-z]+|card-r|sheet-r)\)|0', x) for x in v.split()):
            bad.append(f'{prop}:{v}')
        if re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', v) or re.search(r'gradient\(|text-shadow|drop-shadow', v) or prop == 'text-shadow':
            bad.append(f'{prop}:{v}')
        if prop in ('transition', 'animation') and re.search(r'cubic-bezier|ease(-in|-out)?\b', v):
            bad.append(f'{prop}:{v}')
        if prop in ('margin', 'padding', 'gap', 'column-gap', 'row-gap') or prop.startswith(('margin-', 'padding-')):
            if any(m not in ('0', '1') for m in re.findall(r'(?<![\w-])(\d+(?:\.\d+)?)px', v)):
                bad.append(f'{prop}:{v}')
    check('css: type · corners · colour · spacing · motion from tokens only (design.md §2–§6)', not bad, bad[:6])
    m = re.search(r'@media \(hover:hover\) and \(pointer:fine\)\{(.*?)\n\}', body, flags=re.S)
    outside = body.replace(m.group(0), '') if m else body
    check('css: :hover only inside (hover:hover) and (pointer:fine) (design.md §8)', bool(m) and ':hover' not in outside)
    js = (ROOT / 'src/summary/summary.js').read_text(encoding='utf-8')
    check('js: no dev switch left (?summary= · khm.dev.summary)', "get('summary')" not in js and 'khm.dev.summary' not in js)
    cj = json.loads((ROOT / 'web/close.json').read_text(encoding='utf-8'))
    snap = json.loads((ROOT / 'data/snapshot.json').read_text(encoding='utf-8'))
    want = {x['c']: x['lim'] for x in snap['stocks'] if x.get('lim') in (1, -1) and x.get('p')}
    got = {c: v[3] for c, v in cj['c'].items() if len(v) > 3}
    check('close.json: "lim": true and the 4th element = the snapshot lim (1 / −1 only when set)', cj.get('lim') is True and got == want and all(len(v) in (3, 4) for v in cj['c'].values()),
          f'{len(got)} rows with lim, snapshot {len(want)}')


def start_mock(port, web=None):
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    time.sleep(0.3)
    env = dict(os.environ)
    if web:
        env['MOCK_WEB'] = str(web)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/summary/mock_summary.py'), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(60):
        try:
            NOPROXY.open(f'http://127.0.0.1:{port}/api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w, h, theme='base', url=URL, query='', motion='standard', perms=False):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    if perms:
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=url.rstrip('/'))
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': 'K'}
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    errs = []
    pg.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append(f'pageerror: {e}'))
    pg.goto(url + query)
    pg.wait_for_timeout(2600)
    return ctx, pg, errs


MAPBOX = "(() => { const b = document.getElementById('map').getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)]; })()"
STATE = """() => { const c = document.getElementById('summary'); if (!c) return null;
  const t = c.querySelector('.sm-tog'), band = c.querySelector('.sm-band'), full = document.getElementById('sm-more'), lay = document.querySelector('main.layout'), side = lay.querySelector('.side');
  const b = c.getBoundingClientRect();
  return { open: t.getAttribute('aria-expanded'), band: !band.hidden && band.offsetHeight > 0, full: !full.hidden && full.offsetHeight > 0,
    phonePlace: c.parentNode === lay && c.nextElementSibling === document.getElementById('news'), sidePlace: side.firstElementChild === c,
    span: getComputedStyle(c).gridColumnStart + '/' + getComputedStyle(c).gridColumnEnd, top: Math.round(b.top + scrollY), h: Math.round(b.height),
    pill: c.querySelector('.sm-pill').textContent, hl: c.querySelector('.sm-hl').textContent, text: c.innerText }; }"""
MEASURE = """() => {
  const card = document.getElementById('summary');
  const txt = card ? card.innerText : '';
  const phone = matchMedia('(max-width: 760px)').matches;
  const small = [], tiny = [], colour = [], amber = [];
  const probe = v => { const s = document.createElement('span'); s.style.color = v; document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; };
  const UP = probe('var(--up-text)'), DN = probe('var(--dn-text)'), AC = [probe('var(--acc)'), probe('var(--acc-fill)')];
  if (card) {
    for (const el of card.querySelectorAll('*')) {
      if (el.offsetParent === null) continue;
      const cs = getComputedStyle(el);
      const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      if (own && parseFloat(cs.fontSize) < 11) tiny.push((el.className || el.tagName) + ' ' + cs.fontSize);
      if (own && (cs.color === UP || cs.color === DN) && !el.closest('.sm-n, .up, .dn')) colour.push((el.className || el.tagName) + ' "' + el.textContent.trim().slice(0, 12) + '"');
      if ((own && AC.includes(cs.color)) || AC.includes(cs.backgroundColor)) amber.push(el.className || el.tagName);
    }
    if (phone) for (const el of card.querySelectorAll('button, a[href]')) {
      if (el.offsetParent === null) continue;
      const b = el.getBoundingClientRect(), cs = getComputedStyle(el, '::before');
      const hitH = Math.max(b.height, cs.content !== 'none' && cs.position === 'absolute' ? parseFloat(cs.height) || 0 : 0);
      if (hitH < 44 && !el.classList.contains('sm-a')) small.push((el.className || el.tagName) + ' ' + Math.round(hitH));
    }
  }
  return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bad: /\\b(null|undefined|NaN)\\b/.test(txt), txt: txt.slice(0, 300), small, tiny, colour, amber };
}"""
# click the key from inside the page and read every frame (rAF): the card's layout height (must not change until the end — the layout is
# committed once, so the side column / news card do not re-lay out per frame) and the skin's height (the shape the user sees)
SAMPLE = """async (sel) => {
  const c = document.getElementById('summary'), skin = c.querySelector('.sm-skin'), full = document.getElementById('sm-more'), band = c.querySelector('.sm-band');
  const H0 = c.offsetHeight, out = [], t0 = performance.now();
  c.querySelector(sel).click();
  const sync = [full.className, band.className, c.classList.contains('sm-anim')];   // right after the click, same task
  await new Promise(res => { const f = () => { const t = performance.now() - t0; out.push([Math.round(t), c.offsetHeight, c.classList.contains('sm-anim') ? +skin.getBoundingClientRect().height.toFixed(1) : -1, full.className, band.className]);
    if ((t > 150 && !KHSummary.moving()) || t > 8000) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await new Promise(r => setTimeout(r, 120));
  return { H0, out, sync, ms: Math.round(performance.now() - t0), H1: c.offsetHeight, fullH: full.hidden ? 0 : full.offsetHeight, bandH: band.hidden ? 0 : band.offsetHeight, anim: c.classList.contains('sm-anim'), focus: document.activeElement && document.activeElement.className };
}"""


def motion_ok(s, expand):
    """layout height = H0 on every frame while the skin moves, the skin goes H0 → H1 (overshoot ≤ 2 % of the move), H1 = the final layout"""
    moving = [x for x in s['out'] if x[2] >= 0]
    lay_still = all(x[1] == s['H0'] for x in moving)
    D = abs(s['H1'] - s['H0'])
    sk = [x[2] for x in moving]
    over = (max(sk) - (s['H1'] + 2)) if expand else ((s['H1'] - 2) - min(sk)) if sk else 0
    return bool(moving) and lay_still and over <= 0.02 * D + 2 and not s['anim'], {'frames': len(moving), 'ms': s['ms'], 'H0': s['H0'], 'H1': s['H1'], 'skin': sk[:4], 'over': round(over, 1)}


def per(tag, pg, errs, w):
    m = pg.evaluate(MEASURE)
    check(f'{tag}: horizontal overflow 0', m['sw'] <= m['cw'], f"{m['sw']} > {m['cw']}" if m['sw'] > m['cw'] else '')
    check(f'{tag}: console errors 0', not errs, errs[:2])
    check(f'{tag}: no null/undefined/NaN', not m['bad'], m['txt'][:100] if m['bad'] else '')
    check(f'{tag}: text ≥ 11 px · red/green only on numbers · no amber', not m['tiny'] and not m['colour'] and not m['amber'], (m['tiny'] + m['colour'] + m['amber'])[:4])
    if w <= 760:
        check(f'{tag}: touch targets ≥ 44', not m['small'], m['small'][:4])


def main():
    lint_css()
    start_mock(PORT)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='msum_base_'))
    subprocess.run(f'git -C {ROOT} archive {BASE_REV} web | tar -x -C {tmp}', shell=True, check=True)
    bport = PORT + 1
    start_mock(bport, tmp / 'web')
    if SHOTS:
        OUT.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            sizes = [(360, 780), (390, 844), (768, 1024), (1440, 900)]
            for (w, h) in sizes:
                themes = ['base', 'paper'] if w in (390, 1440) else ['base']
                for theme in themes:
                    tag = f'{w}x{h} {theme}'
                    ctx, pg, errs = open_page(br, w, h, theme)
                    st = pg.evaluate(STATE)
                    check(f'{tag}: card drawn, collapsed by default (band shown, table hidden)', st is not None and st['open'] == 'false' and st['band'] and not st['full'], st and {k: st[k] for k in ('open', 'band', 'full')})
                    if w <= 760:
                        check(f'{tag}: place = right after the map, before the news card', st['phonePlace'], st['top'])
                    else:
                        check(f'{tag}: place = first in the side column' + (' (whole row)' if w <= 980 else ''), st['sidePlace'] and (w > 980 or st['span'] == '1/-1'), st['span'])
                    if theme == 'base':
                        mine = pg.evaluate(MAPBOX)
                        bctx, bpg, berrs = open_page(br, w, h, theme, url=f'http://127.0.0.1:{bport}/')
                        base = bpg.evaluate(MAPBOX); bctx.close()
                        check(f'{tag}: the map box = {BASE_REV} build (left · top · width · height)', mine == base, f'{mine} vs {base}')
                    pg.evaluate("document.getElementById('summary').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
                    per(f'{tag} collapsed', pg, errs, w)
                    if SHOTS:
                        pg.screenshot(path=str(OUT / f'impl_{w}_{theme}_collapsed.png'))
                    s = pg.evaluate(SAMPLE, '.sm-tog')
                    ok, info = motion_ok(s, True)
                    sync = s['sync']
                    check(f'{tag}: 자세히 grows {s["H0"]} → {s["H1"]} px by the open spring, layout committed once at the end, band out → table in',
                          ok and s['H1'] > s['H0'] + 40 and s['bandH'] == 0, info)
                    if theme == 'base':
                        check(f'{tag}: on the press the table text waits (.sm-in, no .sm-go — it comes in at 160 ms) while the band leaves (.sm-out), skin on',
                              'sm-in' in sync[0] and 'sm-go' not in sync[0] and 'sm-out' in sync[1] and sync[2], sync)
                    st = pg.evaluate(STATE)
                    check(f'{tag}: expanded = the table + details + 글로 복사', st['open'] == 'true' and not st['band'] and st['full'] and '코스닥' in st['text'] and '글로 복사' in st['text'] and '오늘 흐름' in st['text'])
                    per(f'{tag} expanded', pg, errs, w)
                    if SHOTS:
                        pg.evaluate("document.getElementById('summary').scrollIntoView({block:'start'})"); pg.wait_for_timeout(200)
                        pg.screenshot(path=str(OUT / f'impl_{w}_{theme}_expanded.png'))
                    s = pg.evaluate(SAMPLE, '.sm-fold')
                    st = pg.evaluate(STATE)
                    ok, info = motion_ok(s, False)
                    check(f'{tag}: 접기 at the end → close spring back to the band (layout once at the end), focus on the top key',
                          ok and st['open'] == 'false' and st['band'] and not st['full'] and s['H1'] < s['H0'] - 40 and 'sm-tog' in (s['focus'] or ''), dict(info, focus=s['focus']))
                    ctx.close()
            # the words (1440 · 390): exact 상·하한가, 수급 = the previous trading day with its date, 거래대금 상위 (not 급증)
            ctx, pg, errs = open_page(br, 1440, 900)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            t = pg.evaluate("document.getElementById('summary').innerText")
            lim = re.search(r'상한가 · 하한가\s*([\d,]+) · ([\d,]+)', t)
            check('상한가 · 하한가 = 9 · 0 (close.json lim — the old ±29.5 % guess counted 1 하한가)', bool(lim) and lim.groups() == ('9', '0'), lim and lim.groups())
            check('외국인 · 기관 = the 11/13 file with its date', re.search(r'외국인 · 기관\s*11/13', t) is not None and '11/13 · 코스피 · 코스닥 합' in t)
            check('"거래대금 상위", never "급증"', '거래대금 상위' in t and '급증' not in t)
            ctx.close()
            # reload → collapsed (not remembered)
            ctx, pg, errs = open_page(br, 390, 844)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            pg.reload(); pg.wait_for_timeout(2600)
            st = pg.evaluate(STATE)
            check('after a reload it starts collapsed again (not remembered)', st['open'] == 'false' and st['band'] and not st['full'])
            ctx.close()
            # 글로 복사
            ctx, pg, errs = open_page(br, 1440, 900, perms=True)
            pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
            pg.click('#summary .sm-copy'); pg.wait_for_timeout(400)
            clip = pg.evaluate('navigator.clipboard.readText()')
            lines = clip.split('\n')
            check('글로 복사: plain text — title, headline, 지수, 오른·내린, 업종, 수급, 원/달러, last line the disclaimer',
                  lines[0].startswith('판세 · 오늘 시장 요약 (휴장 · 11월 13일 (금) 마감 기준)') and '코스피는 내리고 코스닥은 올랐어요' in lines and any(l.startswith('코스피 5,290.53') for l in lines)
                  and any(l.startswith('상승 1,276 · 하락 1,211') and '상한가 9 · 하한가 0' in l for l in lines) and any(l.startswith('업종: ') for l in lines)
                  and any(l.startswith('수급(11/13, 추정)') for l in lines) and any(l.startswith('원/달러 ') for l in lines) and lines[-1].endswith('투자 판단의 근거로 쓰지 마세요.'), lines)
            check('글로 복사: the key says 복사했어요 (✓)', pg.evaluate("document.querySelector('#summary .sm-copy').dataset.st") == 'done')
            ctx.close()
            # the four phases (wording only)
            want = {'pre': ('장 전', '9시에 시작해요', '올랐어요'), 'open': ('장중', '기준', '오르고 있어요'), 'after': ('오늘 마감', '15:30 정규장 종가 기준', '올랐어요'), 'closed': ('휴장', '11월 13일 (금) 마감 기준', '올랐어요')}
            for ph, (pill, when, verb) in want.items():
                ctx, pg, errs = open_page(br, 390, 844, query=f'?summary_phase={ph}')
                st = pg.evaluate(STATE)
                pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
                w_txt = pg.evaluate("document.querySelector('#summary .sm-when').textContent")
                dot = pg.evaluate("getComputedStyle(document.querySelector('#summary .sm-pill'), '::before').content")
                check(f'phase {ph}: "{st["pill"]}" · "{st["hl"]}" · "{w_txt}"' + (' · --live dot' if ph == 'open' else ''),
                      st['pill'] == pill and when in w_txt and st['hl'].endswith(verb) and ((dot != 'none') == (ph == 'open')) and not errs, errs[:2])
                ctx.close()
            # 움직임 줄이기: at once
            ctx, pg, errs = open_page(br, 1440, 900, motion='reduced')
            s = pg.evaluate(SAMPLE, '.sm-tog')
            check('움직임 줄이기: the table is there at once (first frame already at the full height, no skin on any frame)',
                  s['out'] and all(x[2] == -1 for x in s['out']) and s['out'][0][1] == s['out'][-1][1] and s['out'][0][1] > s['H0'] + 40, s['out'][:2])
            ctx.close()
            # snapshot (dist/, file://)
            for (w, h) in [(390, 844), (1440, 900)]:
                ctx, pg, errs = open_page(br, w, h, url=(ROOT / 'dist/index.html').as_uri())
                st = pg.evaluate(STATE)
                ok = st is not None and st['pill'] == '스냅샷' and '상승 ' in st['text'] and '업종' in st['text']
                pg.click('#summary .sm-tog'); pg.wait_for_timeout(900)
                t = pg.evaluate("document.getElementById('summary').innerText")
                check(f'snapshot {w}: the card from the snapshot (스냅샷 · 상승/하락 · 업종; 해외 · 공시 · 뉴스 → 실시간 버전 안내), console errors 0',
                      ok and '실시간 버전' in t and '상한가 · 하한가' in t and not errs, errs[:2] or (st and st['text'][:80]))
                if SHOTS:
                    pg.screenshot(path=str(OUT / f'impl_snapshot_{w}.png'))
                ctx.close()
            br.close()
    finally:
        for prt in (PORT, bport):
            subprocess.run(['fuser', '-k', f'{prt}/tcp'], capture_output=True)
    print(f"\n{counts['pass']} passed, {len(fails)} failed" + (': ' + ', '.join(fails) if fails else ''))
    sys.exit(1 if fails else 0)


main()
