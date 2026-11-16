#!/usr/bin/env python3
"""Design-standard audit of the 일정 탭 (src/calendar/calendar.css · calendar.js — design.md, calendar.md; design.md §11 ④).

  python3 qa/calendar/audit_css.py            (no browser, no server; exit 1 on any failure)

Shared checks (qa/stdaudit.py): no gradient / glow / own blur, amber only on the picked day (week strip indicator · month cell) · the
switched-on filter chip · focus, type on --fs-* / --lh-*, space on --space-*, corners on tokens, heights on --h-*, springs only, press
down at once, hover only on a fine pointer, html[data-motion] the one reduce switch, no theme rule.
Deliberate values off the scale (named below with their reasons): event marks under the week strip (5px dots, 3px apart, a 6px row),
the badge recipe 18 (design.md §5), icon boxes 16 / 18, the sheet grip 36 × 4, data cells (week strip day 58 = weekday · date · marks,
month grid cell 112, day number circle 24, a two-line event row 52), nested corners (inner = outer − gap, design.md §4), the sticky
side list cap; and — 남은 것 for the next step ("컨트롤 움직임 통일", AGENTS §3-38) — the sheet's close key 44 at every width (design.md
§5: 32 / phone 44), its action keys 44 and the code chips 32.
JS: no hand-written bezier / ease-* / literal WAAPI durations; the week indicator moves on KH.spring.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from stdaudit import Audit, common, in_build, parse, read  # noqa: E402

CSS, JS = read('src/calendar/calendar.css'), read('src/calendar/calendar.js')
A = Audit()
css, R, D, KF = parse(CSS)
NEXT = '남은 것 — sized with every module\'s close key · keys · chips in the next step (컨트롤 움직임 통일, AGENTS §3-38)'
MARK = 'event marks under the week strip (5px dots · 3px apart · a 6px row — mark geometry)'
HEIGHT = {'.kc-marks': MARK, '.kc-marks i': MARK, '.kc-badge': 'the badge recipe 18 (design.md §5)', '.kc-watch': 'the badge recipe 18 (design.md §5)',
          '.kc-ik svg': 'icon box 16', '.kc-dmore svg': 'icon box 16', '.kc-ev .chev': 'icon box 16', '.kc-note .bang': 'icon box 16', '.kc-x svg': 'icon box 18',
          '.kc-acts svg': 'icon box 16', '.kc-dlg .kc-grab::before': 'the sheet grip 36 × 4 (as every sheet)',
          '.kc-wk button': 'data cell: a week-strip day = weekday · date · marks (58)', '.kc-ev': 'data row: a two-line event row (title + time · value) 52',
          '@media (min-width:1280px) .kc-mg .cell': 'data cell: the month grid (112)', '@media (min-width:1280px) .kc-mg .dnum': 'the day number circle 24 (a mark)',
          '@media (min-width:1280px) .kc-side': 'the sticky side list cap (scrolls)',
          '.kc-x': NEXT + ' (the sheet × 44 at every width)', '.kc-acts a,.kc-acts button': NEXT + ' (sheet action keys 44)', '.kc-codes button': NEXT + ' (code chips 32)'}
common(A, 'calendar.css', css, R, D, KF,
       amber_ok=lambda s: bool(re.search(r'aria-pressed="true"|\.kc-ind\b|:focus', s)),
       lh_ok=lambda s, v: MARK if s == '.kc-marks b' else None,
       space_ok=lambda s, k, v: MARK if s == '.kc-marks' and k == 'gap' else None,
       radius_ok=lambda s, v: 'nested surface: inner = outer − gap (design.md §4)' if 'calc(var(--r-key) - 4px)' in v else None,
       height_ok=lambda s, k, v: HEIGHT.get(s))
A.check('calendar.js: no hand-written bezier / ease-* / literal WAAPI durations', not re.search(r'cubic-bezier|["\']ease(-in|-out|-in-out)?["\']|duration:\s*\d', JS))
A.check('calendar.js: the week strip indicator moves on KH.spring (edges)', 'KH.spring' in JS and 'edges' in JS)
in_build(A, 'calendar', ['.kc-wk button{', '.kc-chips{'])
sys.exit(A.done())
