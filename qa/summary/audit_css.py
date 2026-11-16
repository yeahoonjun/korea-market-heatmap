#!/usr/bin/env python3
"""Design-standard audit of the 시장 요약 카드 (src/summary/summary.css · summary.js — design.md, market-summary.md; design.md §11 ④).

  python3 qa/summary/audit_css.py            (no browser, no server; exit 1 on any failure)

Shared checks (qa/stdaudit.py, the news card audit's list): no gradient / glow / own blur, amber only on its four meanings (done ✓,
the open chevron, focus), the copy key's ! in --fail-dot, type on --fs-* / --lh-*, space on --space-*, corners on tokens, heights on --h-*,
springs only (no bezier, no literal durations, no --c-base / --m-*), press down at once, hover only on a fine pointer, html[data-motion]
the one reduce switch, no theme rule (the card is the template's .card: glass material comes through --card-bg / --card-sh).
Deliberate values off the scale: the 44px touch hit areas (::before, pointer:coarse) — nothing else.
JS: the card plate grows on `open` / `close` (KH.spring), the copy key's states are KH.ui (no ad-hoc colours), no hand-written curve.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from stdaudit import Audit, common, in_build, parse, read  # noqa: E402

CSS, JS = read('src/summary/summary.css'), read('src/summary/summary.js')
A = Audit()
css, R, D, KF = parse(CSS)
common(A, 'summary.css', css, R, D, KF,
       amber_ok=lambda s: bool(re.search(r'\[data-st="done"\]|aria-expanded="true"|:focus', s)),
       # the 상 · 하한가 swatch = the map legend's mark (12 × 10 tile with a 3px bar, template .legend .limsw) — a mark, not a control
       height_ok={'.msum .sm-lsw': 'mark: the map legend\'s 상 · 하한가 swatch (12 × 10)'})
A.check('summary.css: the copy key — done ✓ amber (완료), fail ! --fail-dot (design.md §2)',
        '.sm-copy[data-st="done"] .sm-i-done{color:var(--acc)}' in CSS and '.sm-copy[data-st="fail"] .sm-i-fail{color:var(--fail-dot)}' in CSS)
A.check('summary.css: the 장중 dot is --live', re.search(r'\.sm-ph-open::before\{[^}]*background:var\(--live\)', CSS))
A.check('summary.js: no hand-written bezier / ease-* / literal WAAPI durations',
        not re.search(r'cubic-bezier|["\']ease(-in|-out|-in-out)?["\']|duration:\s*\d', JS))
A.check('summary.js: the plate grows on KH.spring open / close', "'open'" in JS and "'close'" in JS and 'KH.spring' in JS)
in_build(A, 'summary', ['.sm-copy[data-st="fail"] .sm-i-fail{color:var(--fail-dot)}'])
sys.exit(A.done())
