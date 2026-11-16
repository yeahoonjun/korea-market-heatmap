#!/usr/bin/env python3
"""Design-standard audit of the 정책 자료 tab (src/policy/policy.css · policy.js — design.md, policy-feeds.md; design.md §11 ④).

  python3 qa/policy/audit_css.py            (no browser, no server; exit 1 on any failure)

Shared checks (qa/stdaudit.py): no gradient / glow / own blur, amber only on the chosen filter chip (--chip-on · --chip-ring) and focus,
the failure ! in --fail-dot, type on --fs-* / --lh-*, space on --space-*, corners on tokens, heights on --h-* / --nw-rh, springs only (no
bezier, no literal durations, no --c-base / --m-*), press down at once, hover only on a fine pointer, html[data-motion] the one reduce
switch, no theme rule (the card's material is the template's .card).
Deliberate values off the scale (named below): the badge recipe 18px (line-height of the source badge), icon boxes (✓ mask 14 · ! 15 ·
chevron 6), the skeleton bar 10px, the 44px touch hit areas, the phone message box 300px (the card keeps one height across states).
Policy-specific: 더보기 · 접기 = the card's fold (KHNews.fold — rows past the first count are .nw-x, no 40 ms stagger, ux/std-wrapup),
chip counts change through KH.ui.swap (swapNum), the ↻ key's spec (refresh · freshAt), the skeleton = the news card's nwSk breath.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from stdaudit import Audit, common, in_build, parse, read  # noqa: E402

CSS, JS = read('src/policy/policy.css'), read('src/policy/policy.js')
A = Audit()
css, R, D, KF = parse(CSS)
HEIGHT = {'.news .pl-chip .pl-ck': 'the ✓ mask 14px', '.news .pl-warn': 'the ! icon 15px', '.news .pl-more::after': 'the chevron box 6px (drawn at 1.75px)',
          '.news .pl-sk': 'the skeleton bar 10px', '@media (max-width:760px) .news .pl-msg': 'phone message box 300px — the card keeps one height across states'}
common(A, 'policy.css', css, R, D, KF, endless=['nwSk'],
       amber_ok=lambda s: bool(re.search(r'aria-pressed="true"|:focus', s)),
       lh_ok=lambda s, v: 'the badge recipe height 18px (design.md §5)' if s == '.news .pl-src' and v == '18px' else None,
       height_ok=lambda s, k, v: HEIGHT.get(s))
A.check('policy.css: the fold rows (.nw-x) come in at a quarter (fade) and leave first (close) — the news card\'s recipe, no stagger keyframes',
        '.news .pl-list.nw-fold-in > .nw-x' in CSS and '.news .pl-list.nw-fold-out > .nw-x' in CSS and 'plIn' not in CSS and '--d,' not in CSS)
A.check('policy.css: 더보기 chevron turns on open / close (as 시장 뉴스 · 오늘 공시)', re.search(r'\.pl-more::after\{[^}]*--sp-close', CSS) and re.search(r'\.pl-more\[aria-expanded="true"\]::after\{[^}]*--sp-open', CSS))
A.check('policy.js: 더보기 through the card\'s fold (News.fold), rows past the first count are .nw-x, no stagger',
        'News.fold(list, want, apply' in JS and "' nw-x'" in JS and '--d:' not in JS and "' in'" not in JS)
A.check('policy.js: chip counts through KH.ui.swap (swapNum), the ↻ spec (refresh · freshAt)', 'swapNum(b.querySelector(\'.pl-n\')' in JS and 'freshAt: () => S.okAt' in JS and 'async refresh()' in JS)
A.check('policy.js: no hand-written bezier / ease-* / literal WAAPI durations', not re.search(r'cubic-bezier|["\']ease(-in|-out|-in-out)?["\']|duration:\s*\d', JS))
in_build(A, 'policy', ['.news .pl-list.nw-fold-in > .nw-x', 'News.fold(list, want, apply'])
sys.exit(A.done())
