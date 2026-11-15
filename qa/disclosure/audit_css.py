#!/usr/bin/env python3
"""Design-standard audit of src/disclosure (docs/standards/design.md, AGENTS §3-31 — the 뉴스 · 공시 step of design.md §11, ux/std-news).

  python3 qa/disclosure/audit_css.py      (no browser, no server; exit 1 on any failure)

CSS (src/disclosure/disc.css) — the shared checks of qa/news/stdcss.py (① no gradient · ② no glow · ③ amber only selected / on / focus ·
④ --fs-* · ⑤ --space-* · ⑥ --r-* · ⑦ --h-* · ⑧ springs, hover on a fine pointer, one reduce switch · ⑨ no theme rule), and:
  - status: the new-filing dot = --new-dot (the unread blue, not amber, not red / green), ! = --fail-dot (the map switch's count, a
    failed load), no --live
  - the kind badge follows the badge recipe (18 · --fs-xs · 600 · --r-badge · 1px inner ring), a tag (정정 · 철회) is the same badge dashed
  - the 공시 종류 tabs are an underline .seg (KH.ui.seg: lead / trail), 지도 종목만 is the card's filter pill (news.css, no size override)
  - the map switch (design.md §7): sunken track 44 × 26 from tokens, raised knob whose edges move on follow (front) / settle (back) and
    stretch ≤ 3px, the fill fades in (--sw-on = 켜짐), the count swaps per §6-4 (out on close · in on fade, the card's --nw-tx-* lengths)
  - ⑨ glass: the tooltip / quick-view block (.dsc) paints no plate — no background, no blur, no outer shadow — so the template's .tip /
    .sheet keep their glass material (sheen, 1px edge reflection, blur); no rule here touches .tip / .sheet / #tip / #sheet
JS (src/disclosure/disc.js): no bezier / 'ease-*' / literal WAAPI durations, the kind tabs on KH.ui.seg, 더보기 through KHNews.fold, counts
and a chip's % through KH.ui.swap (swapNum), no row stagger.
Build: web/index.html and dist/index.html carry this CSS / JS.

Deliberate values off the scale:
  - the badge recipe's height / line-height 18px; the 2px underline of a picked kind; the new-filing dot 7px
  - the tooltip head row min-height 18px (= one badge) · the 44px touch hit areas (::before, pointer:coarse)
  - grid track widths (시각 58 · 종목 칩 150 · phone chip max 200) — geometry, not spacing
  - the quick view's DART rows: min-height = --h-row + --space-4 (44 · phones 52)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'qa/news'))
from stdcss import Audit, parse, common, glass_template  # noqa: E402

CSS = (ROOT / 'src/disclosure/disc.css').read_text(encoding='utf-8')
JS = (ROOT / 'src/disclosure/disc.js').read_text(encoding='utf-8')
TPL = (ROOT / 'src/template.html').read_text(encoding='utf-8')
NEWS = (ROOT / 'src/news/news.css').read_text(encoding='utf-8')
A = Audit()
css, R, D, KF = parse(CSS)

# amber: the picked kind's underline, the switch's fill (only shown at --t:1 = aria-checked, or under the finger), focus
OK_AMBER = re.compile(r'aria-pressed="true"|aria-checked="true"|\.dc-ktabs::before|\.dc-trk::before|:focus')
HEIGHT_OK = {('.dc-kb', 'height', '18px'), ('.news .dc-ktabs::before', 'height', '2px'), ('.dc-dot', 'height', '7px'), ('.dsc-h', 'min-height', '18px')}


def height_ok(s, k, v):
    return (s, k, v) in HEIGHT_OK or ('(pointer:coarse)' in s and s.endswith('::before') and '44px' in v)


common(A, 'disc.css', css, R, D, KF, height_ok=height_ok, amber_ok=lambda s: bool(OK_AMBER.search(s)), endless=[])


def first(sel, prop):
    for s, k, v in D:
        if s == sel and k == prop:
            return v
    return None


# status
A.check('③ the new-filing dot = --new-dot (not amber, not red / green)', first('.dc-dot', 'background') == 'var(--new-dot)')
A.check('③ ! = --fail-dot (the map switch\'s count when loading failed or the list is stale)', first('.news .dc-lit .dc-bad', 'color') == 'var(--fail-dot)')
A.check('③ no --live (nothing here is 장중 / 실시간)', '--live' not in css)
fill = first('.news .dc-trk::before', 'opacity')
A.check('③ the switch\'s amber fill shows only when on (opacity = --t: 0 off · 1 aria-checked)', fill == 'var(--t)' and first('.news .dc-lit[aria-checked="true"] .dc-trk', '--t') == '1', fill)

# badge recipe
rec = {k: first('.dc-kb', k) for k in ('height', 'font-size', 'font-weight', 'border-radius', 'box-shadow')}
A.check('⑦ the kind badge = the badge recipe (18 · --fs-xs · 600 · --r-badge · 1px inner ring)',
        rec == {'height': '18px', 'font-size': 'var(--fs-xs)', 'font-weight': '600', 'border-radius': 'var(--r-badge)', 'box-shadow': 'inset 0 0 0 1px var(--line2)'}, rec)
A.check('⑦ no module corner tokens (--dc-badge-r gone)', '--dc-badge-r' not in CSS and '--dc-badge-r' not in JS)
want = {('.news .dc-ktabs > button', 'height'): 'var(--h-key)', ('.news .dc-row', 'height'): 'var(--nw-rh)', ('.news .dc-chipx', 'height'): 'var(--h-chip)',
        ('.dsc .dc-all', 'height'): 'var(--h-row)', ('.dsc .dr', 'min-height'): 'var(--h-chip)', ('.news .dc-lit', 'min-height'): 'var(--h-key)',
        ('.dsc.dsc-q .dr', 'min-height'): 'calc(var(--h-row) + var(--space-4))'}
bad = [(s, p, first(s, p), v) for (s, p), v in want.items() if first(s, p) != v]
A.check('⑦ heights: kind tabs · switch row --h-key, rows --nw-rh, chips --h-chip, 공시 모두 보기 --h-row, quick-view rows --h-row + 8', not bad, bad)
ov = [(s, k) for s, k, v in D if '.nw-only' in s and k in ('height', 'font-size', 'padding')]
A.check('§7 지도 종목만 = the card\'s filter pill as it is (no size override here)', not ov, ov)

# §7 underline tabs, switch
ul = {k: first('.news .dc-ktabs::before', k) for k in ('top', 'height', 'background', 'box-shadow')}
A.check('§7 공시 종류 = an underline row: the segment indicator as a 2px --acc-line bar (KH.ui.seg: lead / trail)',
        ul == {'top': 'auto', 'height': '2px', 'background': 'var(--acc-line)', 'box-shadow': 'none'} and "class: 'seg dc-ktabs'" in JS and 'UI.seg(ktabs)' in JS, ul)
lit = CSS.replace(' ', '')
A.check('§7 switch: track 44 × 26 from tokens (--space-8 + --space-5 · --space-7 + --space-1), knob edges follow (front) / settle (back), stretch ≤ 3px, fill on fade',
        '--trk-w:calc(var(--space-8)+var(--space-5))' in lit and '--trk-h:calc(var(--space-7)+var(--space-1))' in lit
        and 'transition:left var(--sp-follow-dur) var(--sp-follow),right var(--sp-settle-dur) var(--sp-settle)' in CSS
        and 'transition:right var(--sp-follow-dur) var(--sp-follow),left var(--sp-settle-dur) var(--sp-settle)' in CSS
        and 'var(--space-1) * 1.5' in CSS and 'opacity var(--sp-fade-dur) var(--sp-fade)' in (first('.news .dc-trk::before', 'transition') or ''))
cnt = (first('.news .dc-lv.out', 'animation') or '') + ' | ' + (first('.news .dc-lv.in', 'animation') or '')
A.check('§6-4 the switch\'s count: out 100 ms on close, in 180 ms on fade 60 ms later (the card\'s --nw-tx-*, 0 under 줄이기)',
        'dcTxOut var(--nw-tx-out) var(--sp-close)' in cnt and 'dcTxIn var(--nw-tx-in) var(--sp-fade) calc(var(--nw-tx-out) + var(--nw-tx-gap))' in cnt
        and 'html[data-motion="reduced"] .news{--nw-tx-out:0ms;--nw-tx-gap:0ms;--nw-tx-in:0ms}' in NEWS, cnt)
sink = [s for s, k, v in D if k == 'transform' and v == 'translateY(1px)']
A.check('§7 keys and chips sink 1px (지도에 없는 종목 칩 · 공시 모두 보기)', any('.dc-chipx' in s for s in sink) and any('.dc-all' in s for s in sink), sink)
A.check('§7 rows, kind tabs and the switch never sink', not [s for s in sink if re.search(r'\.dc-row|\.dc-ktabs|\.dc-lit', s)])

# ⑨ glass: the tooltip / quick-view block paints no plate
plate = [(s, k, v) for s, k, v in D if s.startswith('.dsc') and k in ('background', 'background-color', 'backdrop-filter') and not s.startswith('.dsc .dc-all')]
plate += [(s, k, v) for s, k, v in D if s.startswith('.dsc') and k == 'box-shadow' and not v.startswith('inset 0 -1px 0') and v != 'none' and not s.startswith('.dsc .dc-all')]
A.check('⑨ the 공시 block in the tooltip / quick view paints no plate (no background · blur · outer shadow; only its 1px row lines and the key)', not plate, plate)
touch = [s for s, _ in R if re.search(r'(^|[\s,>])(\.tip|\.sheet|#tip|#sheet)\b', s)]
A.check('⑨ no rule here touches the template plates (.tip · .sheet · #tip · #sheet)', not touch, touch)
glass_template(A, TPL)

# JS
js = re.sub(r'/\*.*?\*/', '', JS, flags=re.S)
js = re.sub(r'(?m)^\s*//.*$', '', js)
A.check('JS: no hand-written bezier, no keyword easings, no literal WAAPI durations',
        'cubic-bezier' not in js and not re.findall(r"easing:\s*'ease", js) and not re.findall(r'duration:\s*\d', js))
A.check('JS: 더보기 · 접기 through the card\'s fold (KHNews.fold), rows past the first count are .nw-x, no stagger',
        'window.KHNews.fold(list, want, apply' in js and "' nw-x'" in js and '--d:' not in js and "' in'" not in js)
A.check('JS: counts on a new answer and a chip\'s % on a new quote change through KH.ui.swap (swapNum), at once otherwise',
        'UI.swap(el, text, was' in js and js.count('swapNum(') >= 4 and 'S.swap = true' in js and 'S.swap = false' in js)

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    ok = 'dcTxOut var(--nw-tx-out) var(--sp-close)' in page and '--dc-badge-r' not in page and '.dsc-h{display:flex' in page
    A.check(f'build: {f} carries the new disclosure CSS / JS', ok)

sys.exit(A.done())
