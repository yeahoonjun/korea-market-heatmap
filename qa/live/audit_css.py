#!/usr/bin/env python3
"""Design-standard audit of the 실시간 갱신 status mark (src/live/live.css — realtime.md §7-4, design.md §2 · §3 · §6; design.md §11 ④).

  python3 qa/live/audit_css.py            (no browser, no server; exit 1 on any failure)

Shared checks (qa/stdaudit.py) + the mark's own: 실시간 = --live (dot and word — the template's status dot / 실시간 badge it stands in
for), never amber or red / green; the beat is the template's status-dot beat (keyframes `pulse`, opacity only — no spreading ring);
type --fs-sm (phones --fs-xs), gap --space-2. Deliberate values off the scale (named below): min-height 20px (the header's status line —
the map box, design.md §11 템플릿), the 8px dot, the delayed state's inner dot (a radial-gradient shape, not paint), and the beat's
1.2s · --m-out (the template's own `.status.live .dot.beat` rule, kept identical).
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from stdaudit import Audit, common, in_build, parse, read  # noqa: E402

CSS = read('src/live/live.css')
A = Audit()
css, R, D, KF = parse(CSS)
BEAT = 'the template\'s status-dot beat (pulse 1.2s --m-out — the same rule as .status.live .dot.beat)'
common(A, 'live.css', css, R, D, KF, endless=['lm-spin'],
       grad_ok={'#live-mark[data-s="delayed"] .lm-g': 'the delayed state\'s inner dot (a shape)'},
       height_ok=lambda s, k, v: {'#live-mark': 'the header status line 20 (map box)', '#live-mark .lm-g': 'the 8px dot'}.get(s),
       dur_ok=lambda s, v: BEAT if s == '#live-mark .lm-g.beat' else None,
       old_ok=lambda s, m: BEAT if s == '#live-mark .lm-g.beat' else None)
A.check('live.css: 실시간 = --live (dot and word), the beat = the template\'s `pulse` (opacity), no own ring keyframes',
        re.search(r'#live-mark\[data-s="live"\]\{color:var\(--live\)\}', CSS) and re.search(r'#live-mark\[data-s="live"\] \.lm-g\{background:var\(--live\)\}', CSS)
        and 'animation:pulse ' in CSS and 'lm-beat' not in CSS)
A.check('live.css: type on the scale (--fs-sm, phones --fs-xs)', 'font-size:var(--fs-sm)' in css and 'font-size:var(--fs-xs)' in css and '11.5px' not in css)
in_build(A, 'live', ['#live-mark[data-s="live"]{color:var(--live)}'])
sys.exit(A.done())
