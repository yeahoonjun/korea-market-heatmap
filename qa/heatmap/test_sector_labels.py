#!/usr/bin/env python3
"""섹터 · 업종 머리글 이름표 — 로드할 때 빠지는 이름표 (fix/sector-labels, 2026-11-16).

  python3 qa/heatmap/test_sector_labels.py [loads=3]

The live build (web/) behind qa/float/mock_float.py on SECTOR_QA_PORT (default 9061; 9060–9069 only — FLOAT_WEB=<dir> serves another
build's web/, e.g. main's, for a before / after count). 1280 × 800 · 1440 × 900 · 390 × 844 × 코스피 · 코스닥, each loaded `loads` times
fresh with a different timing: plain (화려하게 — the intro), the web font held back 1.5 s (기본), CPU × 3 + the font held back 0.8 s
(줄이기). Once the web font is in and the map has settled:
room    no sector / industry header hidden — or its name cut — while its whole name fits: name width in the font as drawn (canvas
        measureText, after the font is in) × 1.2 + the header's padding ≤ the box width, and the box is taller than the layout's
        height rule (sector > 34, industry > 48 — "정말 낮아서 숨긴 것" stays hidden). A cut name counts only when the header itself
        has that room (the value took it).
clean   a hidden header carries no text (an earlier layout's name / value left in a display:none header made the DOM depend on the
        load's timing — the qa/disclosure baseline compare saw it as "the label misses its first fit, 2 of 6 loads").
same    the header DOM (shown, name, value, box) is the same in every load of one viewport × market.
fitted  (≥ 761 px) every render that drew tiles drew them at the fitted map height for the page as it was then — fitMapHeight's own
        formula: max(520, round(innerHeight − map top − 14 − legend)) — not at a provisional height left from before the header
        filled in (the first quotes answer could beat the ResizeObserver refit: 614 px, then 520, then 550 at 1280 × 800).
resize  a resize event after the font (fitMapHeight + a render) changes nothing — "글꼴 로드 뒤 창 크기를 바꾸면 다시 나와요".
paths   1440 코스피: 코스닥 tab (animated FLIP), a sector zoom and back, 시총순 → 섹터별 — room + clean after each.
Prints the counts per config ("room misses" = headers missing although their name fits). Exit 1 on a fail. The port is stopped with
fuser -k.
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('SECTOR_QA_PORT', 9061))
assert 9060 <= PORT <= 9069, 'ports 9060–9069 (fix/sector-labels)'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LOADS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
VIEWPORTS = [(1280, 800), (1440, 900), (390, 844)]
MARKETS = ['K', 'Q']
# (name, web font delay ms, CPU throttle, stored 효과 — None = the default, 화려하게 with its intro)
VARIANTS = [('plain', 0, 1, None), ('font+1.5s', 1500, 1, 'standard'), ('cpu×3+font0.8s', 800, 3, 'reduced')]
FAILS, PASSES, ERRS = [], [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


# every render that drew tiles: what fitMapHeight would set for the page as it is at that moment (same formula, same rounding)
INIT = r"""
window.__lb = { renders: [] };
document.addEventListener('kh:render', () => {
  const m = document.getElementById('map'), lg = document.getElementById('legend');
  if (!m || !m.querySelector('.tile:not(.leaving)')) return;
  const narrow = matchMedia('(max-width: 760px)').matches;
  const rp = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rp-h')) || 0;
  const top = m.getBoundingClientRect().top + scrollY, lgH = lg ? lg.offsetHeight : 0;
  window.__lb.renders.push({ t: Math.round(performance.now()), h: m.clientHeight, w: m.clientWidth, top: Math.round(top), narrow, rp,
    want: narrow || rp ? null : Math.max(520, Math.round(innerHeight - top - 14 - lgH)) });
});
"""

# the web font is in for every header name (dynamic subsets load per glyph range)
FONTS_IN = r"""() => {
  if (document.fonts.status !== 'loaded') return false;
  const hds = [...document.querySelectorAll('#map .node.sec > .hd, #map .node.ind > .hd')];
  if (!hds.length) return false;
  return hds.every(hd => { const cs = getComputedStyle(hd.children[0]); return document.fonts.check(`${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`, hd.parentElement.dataset.i || hd.parentElement.dataset.s); });
}"""

STATE = r"""() => {
  const m = document.getElementById('map'), cv = document.createElement('canvas').getContext('2d');
  const room = [], stale = [], sig = [];
  for (const el of m.querySelectorAll('.node.sec, .node.ind')) {
    if (el.classList.contains('leaving')) continue;
    const sec = el.classList.contains('sec'), hd = el.firstChild, t = hd.children[0], v = hd.children[1];
    const name = sec ? el.dataset.s : el.dataset.i;
    const cs = getComputedStyle(t), hcs = getComputedStyle(hd);
    cv.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const need = cv.measureText(name).width, pad = parseFloat(hcs.paddingLeft) + parseFloat(hcs.paddingRight);
    const w = el.offsetWidth, h = el.offsetHeight, shown = hd.style.display !== 'none' && getComputedStyle(hd).display !== 'none';
    const tall = sec ? h > 34 : h > 48;
    if (!shown && tall && w >= need * 1.2 + pad) room.push([sec ? 'S' : 'I', name, 'hidden', w + '×' + h, 'needs ' + Math.ceil(need + pad)]);
    if (shown) {
      const tw = t.getBoundingClientRect().width, avail = hd.clientWidth - pad;
      if (tw + 0.5 < need && avail >= need * 1.2) room.push([sec ? 'S' : 'I', name, 'cut', w + '×' + h, `drawn ${Math.round(tw)} of ${Math.ceil(need)}, value "${v.textContent}"`]);
    }
    if (!shown && (t.textContent || v.textContent)) stale.push([sec ? 'S' : 'I', name, t.textContent + '|' + v.textContent]);
    sig.push([sec ? 'S' : 'I', el.dataset.s + '/' + (el.dataset.i || ''), shown ? 1 : 0, w, h, t.textContent, v.textContent].join(' '));
  }
  sig.sort();
  return { room, stale, sig, mh: m.clientHeight, mw: m.clientWidth, renders: window.__lb.renders };
}"""


def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


async def open_page(br, w, h, market, delay=0, cpu=1, motion=None, tag=''):
    mobile = w <= 760
    ctx = await br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    st = {'theme': 'base', 'tickerPaused': True, 'market': market}
    if motion:
        st['motion'] = motion
    await ctx.add_init_script(INIT + 'try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    if delay:
        async def slow(route):
            await asyncio.sleep(delay / 1000)
            await route.continue_()
        await ctx.route('**/*.woff2', slow)
    pg = await ctx.new_page()
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    if cpu > 1:
        cdp = await ctx.new_cdp_session(pg)
        await cdp.send('Emulation.setCPUThrottlingRate', {'rate': cpu})
    await pg.goto(URL)
    await pg.wait_for_function(FONTS_IN, timeout=20000, polling=100)
    await pg.wait_for_timeout(900 if cpu == 1 else 1800)       # the refit after the font (ResizeObserver → frame → render) and the intro
    return ctx, pg


async def loads(br):
    total = {}
    for w, h in VIEWPORTS:
        for mk in MARKETS:
            sigs, room_n, stale_n, unfit_n, notes = [], 0, 0, 0, []
            for k in range(LOADS):
                vname, delay, cpu, motion = VARIANTS[k % len(VARIANTS)]
                tag = f'{w}×{h} {mk} #{k + 1} {vname}'
                ctx, pg = await open_page(br, w, h, mk, delay, cpu, motion, tag)
                s = await pg.evaluate(STATE)
                unfit = [r for r in s['renders'] if r['want'] is not None and r['h'] != r['want']]
                check(f'room [{tag}]: no header hidden or cut while its name fits ({len(s["sig"])} headers)', not s['room'], s['room'][:6])
                check(f'clean [{tag}]: hidden headers carry no text', not s['stale'], s['stale'][:6])
                if w > 760:
                    check(f'fitted [{tag}]: every render with tiles at the fitted map height ({len(s["renders"])} renders)', not unfit,
                          [(r['t'], f"{r['w']}×{r['h']} top {r['top']} → want {r['want']}") for r in unfit[:4]])
                await pg.evaluate("window.dispatchEvent(new Event('resize'))")
                await pg.wait_for_timeout(700)
                s2 = await pg.evaluate(STATE)
                diff = sorted(set(s['sig']) ^ set(s2['sig']))
                check(f'resize [{tag}]: a refit after the font changes no header (map {s["mw"]}×{s["mh"]} → {s2["mw"]}×{s2["mh"]})', not diff and s['mh'] == s2['mh'], diff[:4])
                sigs.append(s['sig'])
                room_n += len(s['room']); stale_n += len(s['stale']); unfit_n += len(unfit)
                if s['room']:
                    notes.append(f"#{k + 1}: " + ', '.join(f'{x[1]} {x[2]} {x[3]} {x[4]}' for x in s['room'][:3]))
                await ctx.close()
            first = sigs[0]
            bad = [i + 1 for i, sg in enumerate(sigs) if sg != first]
            dd = sorted(set(first) ^ set(sigs[bad[0] - 1]))[:4] if bad else []
            check(f'same [{w}×{h} {mk}]: the header DOM is the same in all {len(sigs)} loads', not bad, f'loads {bad} differ from #1: {dd}')
            total[(w, h, mk)] = (room_n, stale_n, unfit_n, len(bad), notes)
    print('\ncounts per config (over all loads): room misses · stale hidden headers · unfitted renders · loads unlike #1')
    for (w, h, mk), (a, b, c, d, notes) in total.items():
        print(f'  {w}×{h} {mk}: {a} · {b} · {c if w > 760 else "—"} · {d}' + (f'   ({"; ".join(notes)[:300]})' if notes else ''))
    return total


async def paths(br):
    ctx, pg = await open_page(br, 1440, 900, 'K', tag='1440 paths')
    async def chk(name):
        s = await pg.evaluate(STATE)
        check(f'paths [1440 {name}]: room — no header hidden or cut while its name fits', not s['room'], s['room'][:6])
        check(f'paths [1440 {name}]: clean — hidden headers carry no text', not s['stale'], s['stale'][:6])
    await pg.evaluate("document.querySelector('.tabs button[data-mkt=\"Q\"]').click()"); await pg.wait_for_timeout(1300)
    await chk('코스닥 tab')
    await pg.evaluate("document.querySelector('.tabs button[data-mkt=\"K\"]').click()"); await pg.wait_for_timeout(1300)
    await chk('back to 코스피')
    await pg.evaluate("document.querySelector('#map .node.sec:not(.leaving) > .hd').click()"); await pg.wait_for_timeout(1300)
    await chk('sector zoom')
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(1300)
    await chk('zoom out')
    await pg.evaluate("document.querySelector('.ctl[data-ctl=\"groupBy\"] button[data-v=\"cap\"]').click()"); await pg.wait_for_timeout(1300)
    await pg.evaluate("document.querySelector('.ctl[data-ctl=\"groupBy\"] button[data-v=\"sector\"]').click()"); await pg.wait_for_timeout(1300)
    await chk('시총순 → 섹터별')
    await ctx.close()


async def main():
    start_mock()
    try:
        async with async_playwright() as p:
            br = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            await loads(br)
            await paths(br)
            await br.close()
    finally:
        subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    check(f'console errors: {len(ERRS)}', not ERRS, ERRS[:6])
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    asyncio.run(main())
