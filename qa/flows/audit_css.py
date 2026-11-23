#!/usr/bin/env python3
"""Design-standard audit of the 투자자별 순매수 카드 (src/flows/flows.css · flows.js — design.md, AGENTS §3-40).

  python3 qa/flows/audit_css.py            (no browser, no server; exit 1 on any failure)

Shared checks (qa/stdaudit.py, the news card audit's list): no gradient / glow / own blur, amber only on its four meanings (the open
chevron, focus — the module has none of its own), ! of a failed / stale value in --fail-dot, type on --fs-* / --lh-*, space on --space-*,
corners on tokens, heights on --h-*, springs only (no bezier, no literal durations, no --c-base / --m-*), press down at once, hover only
on a fine pointer, html[data-motion] the one reduce switch. The card is the template's .card (glass material through --card-bg /
--card-sh) and its controls the template's .movers-tabs segment.
Deliberate values off the scale (named here):
  - the row's today candle 10 × 15 (= the 눈에 띄는 종목 card's .movers .cdi — a data mark, not a control)
  - icon boxes 15 × 15 (the ! of KH.ui.icon('warn'), like the news card's)
  - 44px touch hit areas (::before, pointer:coarse)
  - the 더보기 chevron 6 × 6 (a mark drawn at 1.75px, = the news card's)
  - 신문: rows square with a hairline, the template's .movers > button rule for that theme (one named theme rule)
JS: 더보기 · 접기 is the fold (KH.spring 'open' / 'close', new rows after a quarter), no hand-written curve or WAAPI duration; the public
page carries no 가족 word (가족 · 초대) in what it draws (the browser test qa/flows/test_flows_card.py checks 잠정 · 한국투자 too).
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from stdaudit import Audit, common, in_build, parse, read  # noqa: E402

CSS, JS = read('src/flows/flows.css'), read('src/flows/flows.js')
A = Audit()
css, R, D, KF = parse(CSS)
MARK = {'.flows .fl-r .cdi': 'mark: the today candle (= .movers .cdi 10 × 15)',
        '.flows .fl-at svg,.flows .fl-fail svg': 'icon box 15 × 15 (the ! icon)',
        '.flows .fl-more::after': 'mark: the chevron 6 × 6'}
common(A, 'flows.css', css, R, D, KF,
       amber_ok=lambda s: bool(re.search(r'aria-expanded="true"|:focus', s)),
       height_ok=lambda s, *rest: MARK.get(s) or ('44px' in (rest[-1] if rest else '') and '::before' in s and 'pointer:coarse' in s.replace(' ', '')),
       theme_ok={'html[data-theme="paper"] .flows .fl-r': 'paper: square rows with a hairline (= the template\'s .movers > button)'})
A.check('flows.css: the ! of a stale / failed value is --fail-dot', re.search(r'\.fl-at svg,\.flows \.fl-fail svg\{[^}]*color:var\(--fail-dot\)', CSS) is not None)
A.check('flows.css: up / down colour only on numbers (the template .up / .dn classes; no data colour of its own)', not re.search(r'--up-text|--dn-text|--cd-up|--cd-dn', CSS))
A.check('flows.js: no hand-written bezier / ease-* / literal WAAPI durations',
        not re.search(r'cubic-bezier|["\']ease(-in|-out|-in-out)?["\']|duration:\s*\d', JS))
A.check('flows.js: 더보기 is the fold on KH.spring open / close (new rows .fl-x after a quarter)',
        "run('open'" in JS and "run('close'" in JS and 'p >= 0.25' in JS and 'KH.spring' in JS)
A.check('flows.js: the controls are the template segment (KH.ui.seg on .movers-tabs)', 'movers-tabs' in JS and 'UI.seg(' in JS)
A.check('flows.js: no 가족 · 초대 words drawn (a public device shows no trace)', '가족' not in re.sub(r'/\*.*?\*/|//[^\n]*', '', JS, flags=re.S) and '초대' not in re.sub(r'/\*.*?\*/|//[^\n]*', '', JS, flags=re.S))
in_build(A, 'flows', ['.flows .fl-list.fl-fold-in > .fl-x', 'window.KHFlows'])
sys.exit(A.done())
