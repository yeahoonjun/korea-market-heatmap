#!/usr/bin/env python3
"""이미지로 저장의 오늘 숫자 줄 (사용자 2026-11-16 11:31): downloads the real PNG at 390 · 1440 × 코스피 · 코스닥 · 전체 · 테마(종목 지도 ·
개요) · 관심 and checks what the picture says (window.__imgStats) against the screen — the 등락 분포 card (#breadthLab · #distLim ·
#breadthScope) and the map's industry headers — plus: hidden under a period colour and on 해외, fits the picture's width, console clean.

  python3 qa/extras/test_image_stats.py          (mock qa/extras/mock_api.py on IMG_STATS_PORT, default 9061; PNGs → qa/shots/image_stats/)
"""
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHOTS = ROOT / 'qa/shots/image_stats'
SHOTS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get('IMG_STATS_PORT', 9061))
LIVE = f'http://127.0.0.1:{PORT}/'
results, errors = [], []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


NET_OK = []


def api_get(path):
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(LIVE.rstrip('/') + path, timeout=5).read()


def png_size(path):
    b = pathlib.Path(path).read_bytes()[:24]
    return struct.unpack('>II', b[16:24]) if b[:8] == b'\x89PNG\r\n\x1a\n' else (0, 0)


WATCH = ['005930', '000660', '035420', '005380', '068270', '247540', '086520', '196170', '028300', '035720', '051910', '006400']
INIT_WATCH = "localStorage.setItem('khm.watchGroups', JSON.stringify({v:1, groups:[{id:'g1', name:'기본', codes:%s}], active:'all'}));" % json.dumps(WATCH)

# the card as drawn (DOM) and the template's own numbers, to set beside what the picture said
CARD_JS = '''() => { const lab = [...document.querySelectorAll('#breadthLab span')].map(e => e.textContent.trim());
  const dl = document.querySelector('#distLim'); return { lab, lim: dl && !dl.hidden ? dl.textContent.replace(/\\s+/g, ' ').trim() : null,
  scope: (document.querySelector('#breadthScope') || {}).textContent || '', info: KH.breadthInfo(), rank: KH.indRank(),
  heads: KH.layout().filter(n => n.kind === 'ind' && n.label && n.sub).map(n => [n.label, n.sub]) }; }'''


def save(pg, name):
    with pg.expect_download(timeout=15000) as dl:
        pg.click('[aria-label="이미지로 저장"]')
    out = SHOTS / name
    dl.value.save_as(str(out))
    return out, pg.evaluate('() => window.__imgStats')


def nf(n):
    return f'{n:,}'


def case(b, width, hsh, label, init=None, want_scope=None, scroll_card=True):
    mobile = width < 600
    ctx = b.new_context(viewport={'width': width, 'height': 844 if mobile else 900}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append(f'{label}@{width}: {m.text}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(f'{label}@{width}: pageerror {e}'))
    pg.goto(LIVE + hsh)
    pg.wait_for_function('() => document.querySelectorAll("#map .tile").length > 3 && window.KH && KH.breadthInfo && KH.breadthInfo()', timeout=20000)
    if scroll_card:     # the card asks /api/breadth while it is on screen (§3-3): bring it there once, then back to the top
        pg.evaluate('() => document.querySelector("#breadth").scrollIntoView({block: "center"})')
    if want_scope:
        try:
            pg.wait_for_function(f'() => (KH.breadthInfo() || {{}}).scope && KH.breadthInfo().scope.includes({json.dumps(want_scope)})', timeout=15000)
        except Exception:
            pass
    pg.evaluate('() => scrollTo(0, 0)')
    pg.wait_for_timeout(500)
    card = pg.evaluate(CARD_JS)
    tag = f'{label}_{width}'
    out, st = save(pg, f'{tag}.png')
    w, h = png_size(out)
    check(f'{tag}: PNG saved', w > 300 and h > 300, f'{out.name} {w}×{h}')
    title_checks(pg, tag, label)
    info = card['info']
    if not st:
        check(f'{tag}: the row is in the picture', False, json.dumps(info, ensure_ascii=False))
        ctx.close()
        return None
    # counts = the card (same words, same numbers)
    want_lab = [f"{info['words'][0]} {nf(info['up'])}", f"{info['words'][1]} {nf(info['flat'])}", f"{info['words'][2]} {nf(info['dn'])}"]
    check(f'{tag}: 상승 · 보합 · 하락 = 등락 분포 카드', card['lab'] == want_lab and (st['up'], st['flat'], st['dn']) == (info['up'], info['flat'], info['dn']),
          f"card {card['lab']} · picture {st['up']}/{st['flat']}/{st['dn']}")
    if want_scope:
        check(f'{tag}: scope = card scope ({want_scope})', want_scope in card['scope'] and st['scope'] and st['scope'] in card['scope'], f"card '{card['scope']}' · picture '{st['scope']}'")
    else:
        wide = re.search(r'전 종목|NXT', card['scope'])
        check(f'{tag}: label only for a whole-market card (map scope → none, the title row says N종목)', (st['scope'] in card['scope'] and st['scope']) if wide else st['scope'] == '',
              f"card '{card['scope']}' · picture '{st['scope']}'")
    lim = info['lim']
    if lim:
        card_lim = f"상한가 {lim['lu']} · 하한가 {lim['ld']}"
        check(f'{tag}: 상한가 · 하한가 = 카드', card['lim'] == card_lim and st['lim'] == lim, f"card '{card['lim']}' · picture {st['lim']}")
    else:
        check(f'{tag}: 상 · 하한가 hidden like the card', card['lim'] is None and st['lim'] is None, f"card {card['lim']} · picture {st['lim']}")
    # the highest / lowest group = the template's ranking, and the same text as that group's map header where it shows one
    rows = (card['rank'] or {}).get('rows') or []
    if st['grp']:
        hi, lo = st['grp']['hi'], st['grp']['lo']
        ok = (not hi or (rows and hi['name'] == rows[0]['name'] and hi['r'] > 0)) and (not lo or (rows and lo['name'] == rows[-1]['name'] and lo['r'] < 0))
        heads = dict(card['heads'])
        same = all(heads.get(x['name'], x['text']) == x['text'] for x in (hi, lo) if x)
        check(f'{tag}: 업종 = indRank 처음 · 끝, map header text', ok and same,
              f"{st['grp']['label']} {hi and (hi['name'], hi['text'])} / {lo and (lo['name'], lo['text'])}")
    else:
        check(f'{tag}: no group (nothing up / down qualifies)', not rows or (rows[0]['r'] <= 0 and rows[-1]['r'] >= 0), str(rows[:2]))
    # fits: every line inside the picture, two lines at most on a phone
    fits = all(x <= st['avail'] + 0.5 for x in st['widths'])
    check(f'{tag}: lines fit ({st["rows"]} line(s) · {st["widths"]} ≤ {st["avail"]})', fits and (st['rows'] <= 2 or not mobile), '')
    ctx.close()
    return st


def title_checks(pg, tag, label):
    """the title row's right side (사용자 11:41 · 11:42): under a market root with the index row drawn, the map's count instead of the index %
    (the row below says it); elsewhere every % in its direction's colour (dir from the screen's up / dn / flat class)"""
    T = pg.evaluate('() => window.__imgTitle')
    parts = (T or {}).get('stat') or []
    text = ''.join(x['t'] for x in parts)
    if label.split('_')[0] in ('kospi', 'kosdaq', 'all') and T and T['ix']:
        ms = pg.evaluate('() => KH.mapStat()')
        check(f'{tag}: title row = map count, no index % (index row drawn)', '%' not in text and ms and text.strip() == ms['text'], f"'{text}' vs {ms and ms['text']}")
    elif label == 'themes':
        # the theme overview: "265개 테마" only — 오름 · 내림 are the 오늘 숫자 줄's 상승 · 하락 again
        check(f'{tag}: theme overview title = count only (no repeat of the row)', re.fullmatch(r'[\d,]+개 테마', text.strip() or '') is not None, f"'{text}'")
    else:
        pcts = [x for x in parts if '%' in x['t'] or x['b']]
        check(f'{tag}: title row % coloured by direction', bool(pcts) and all(x['b'] and x['dir'] in (1, -1, 0) for x in pcts), f"ix={T and T['ix']} {parts}")


def hidden_case(b, width, hsh, label, init=None):
    ctx = b.new_context(viewport={'width': width, 'height': 900})
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append(f'{label}@{width}: {m.text}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(f'{label}@{width}: pageerror {e}'))
    pg.goto(LIVE + hsh)
    pg.wait_for_function('() => window.KH && KH.layout && KH.layout().some(n => n.kind === "tile")', timeout=20000)
    pg.wait_for_timeout(800)
    out, st = save(pg, f'{label}_{width}.png')
    check(f'{label}_{width}: no 오늘 숫자 줄', st is None, f'{png_size(out)} {st}')
    ctx.close()


def main():
    srv = subprocess.Popen([sys.executable, str(HERE / 'mock_api.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(LIVE + '__reset', timeout=2).read(); break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
            seen = {}
            for width in (390, 1440):
                seen[('K', width)] = case(b, width, '#kospi', 'kospi', want_scope='코스피 전 종목')
                seen[('Q', width)] = case(b, width, '#kosdaq', 'kosdaq', want_scope='코스닥 전 종목')
                seen[('ALL', width)] = case(b, width, '#all', 'all', want_scope='전 종목')
                case(b, width, '#theme-12', 'theme12')
                case(b, width, '#theme', 'themes')
                case(b, width, '#watch', 'watch', init=INIT_WATCH)
            # the phone saved before the card came on screen: the map's own count, said as such
            st = case(b, 390, '#kosdaq', 'kosdaq_mapscope', scroll_card=False)
            check('kosdaq 390 before the card loads: whole-market label or none (map scope = the title row\'s count)', bool(st) and (st['scope'] == '' or '전 종목' in st['scope']), st and st['scope'])
            # same numbers on 390 and 1440 (only the drawing differs)
            for m in ('K', 'Q', 'ALL'):
                a, z = seen.get((m, 390)), seen.get((m, 1440))
                keys = ('up', 'flat', 'dn', 'lim', 'scope')
                check(f'{m}: 390 and 1440 say the same', bool(a and z) and all(a[k] == z[k] for k in keys), f'{a and [a[k] for k in keys]} / {z and [z[k] for k in keys]}')
            hidden_case(b, 1440, '#kosdaq', 'kosdaq_m1', init="localStorage.setItem('khm.colorBy', JSON.stringify('m1'));")
            # no index row (no /api/market spark): 전체's "코스피 +x · 코스닥 +y" stays in the title row, each % in colour (11:41)
            api_get('/__mode?market=fail')
            NET_OK.append(True)
            for width in (390, 1440):
                ctx = b.new_context(viewport={'width': width, 'height': 900}, is_mobile=width < 600, has_touch=width < 600, device_scale_factor=2 if width < 600 else 1)
                pg = ctx.new_page()
                pg.on('console', lambda m: errors.append(f'all_noix: {m.text}') if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
                pg.goto(LIVE + '#all'); pg.wait_for_function('() => document.querySelectorAll("#map .tile").length > 3', timeout=20000); pg.wait_for_timeout(900)
                out, st = save(pg, f'all_noix_{width}.png')
                T = pg.evaluate('() => window.__imgTitle')
                bs = [x for x in (T['stat'] or []) if x['b']]
                check(f'all_noix_{width}: no index row · 코스피 · 코스닥 % in colour', not T['ix'] and len(bs) >= 2 and all(x['dir'] in (1, -1, 0) for x in bs)
                      and '코스피' in ''.join(x['t'] for x in T['stat']) and '코스닥' in ''.join(x['t'] for x in T['stat']), str(T))
                ctx.close()
            api_get('/__mode?market=ok')
            # 해외: nothing to count (the template gives no numbers there; the list view saves nothing anyway)
            ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page()
            pg.on('console', lambda m: errors.append(f'world: {m.text}') if m.type == 'error' else None)
            pg.goto(LIVE + '#world'); pg.wait_for_function('() => window.KH && KH.market() === "world"', timeout=20000); pg.wait_for_timeout(800)
            check('world: breadthInfo · indRank are null', pg.evaluate('() => KH.breadthInfo() === null && KH.indRank() === null'))
            ctx.close()
            b.close()
    finally:
        srv.terminate()
        srv.wait()
    check('console errors 0', not errors, '; '.join(errors[:5]))
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} checks passed')
    for n, _, d in failed:
        print('  FAILED:', n, d)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
