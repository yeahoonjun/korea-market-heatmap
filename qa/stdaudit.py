"""Shared design-standard CSS audit for the modules that had none (design.md §11 ④ — ux/std-wrapup 2026-11-16): src/summary · src/calendar
· src/policy · src/live. Parsing comes from qa/news/stdcss.py (rules · declarations · var() stripping · shadow layers); the checks are the
ones the news card audit makes, with each module's deliberate exceptions passed in (a dict "selector → reason" or a predicate), so every
value off the scale is named with its reason in that module's audit_css.py.

    A = Audit(); css, R, D, KF = parse(text); common(A, 'summary.css', css, R, D, KF, **opts); sys.exit(A.done())
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'news'))
from stdcss import AMBER, SPACE, STEPS, Audit, novar, parse, split_layers  # noqa: E402,F401

STATUS = re.compile(r'\[data-st="fail"\]|\bfail\b|\.stale|\.err\b|\.bang|\.warn|\.kwn')


def _ok(table, sel, *rest):
    """table: dict selector → reason, or a callable(sel, *rest) → reason / None"""
    if callable(table):
        return table(sel, *rest)
    return table.get(sel)


def common(A, tag, css, R, D, KF, *, grad_ok=None, theme_ok=False, endless=(), amber_ok=lambda s: False, font_ok=None, lh_ok=None,
           space_ok=None, radius_ok=None, height_ok=None, dur_ok=None, old_ok=None, blur_ok=None, kf_ok=()):
    grad_ok, font_ok, lh_ok = grad_ok or {}, font_ok or {}, lh_ok or {}
    space_ok, radius_ok, height_ok, dur_ok, old_ok, blur_ok = space_ok or {}, radius_ok or {}, height_ok or {}, dur_ok or {}, old_ok or {}, blur_ok or {}
    D = [(s, k, v) for s, k, v in D if not k.startswith('--')]
    # ① gradients: only shapes / masks named with a reason
    bad = [(s, k) for s, k, v in D if 'gradient(' in v and not _ok(grad_ok, s)]
    A.check(f'{tag} ① gradients only where named (a shape or a mask — no paint)', not bad, bad)
    # ② glow
    bad = [(s, v) for s, k, v in D if 'drop-shadow(' in v or (k in ('backdrop-filter', '-webkit-backdrop-filter') and not _ok(blur_ok, s))]
    A.check(f'{tag} ② no drop-shadow(), no backdrop-filter of its own (the glass blur is the template plates\')', not bad, bad)
    blur = [(s, b) for s, k, v in D if k == 'filter' for b in re.findall(r'blur\((\d*\.?\d+)px\)', v) if float(b) > 2]
    A.check(f'{tag} ② blur only ≤ 2px (the §6-4 text swap), never a halo', not blur, blur)
    halo = []
    for s, k, v in D:
        if k == 'text-shadow' and v.strip() != 'none':
            halo.append((s, v)); continue
        if k != 'box-shadow':
            continue
        for layer in split_layers(v):
            nums = [float(x) for x in re.findall(r'(-?\d*\.?\d+)px', novar(layer))]
            if len(nums) >= 3 and nums[2] > 0 and ((abs(nums[0]) < 1e-9 and abs(nums[1]) < 1e-9)
                                                   or AMBER.search(layer) or re.search(r'--live|--fail|--up-text|--dn-text|--new-dot', layer)):
                halo.append((s, layer))
    A.check(f'{tag} ② no glow shadow (no even halo, no blurred amber / status colour, no text-shadow)', not halo, halo)
    badkf = [n for n, body in KF if n not in kf_ok and (re.search(r'box-shadow|text-shadow|background|color\s*:', body) or re.search(r'glow|pulse|shim|ring', n, re.I))]
    A.check(f'{tag} ② keyframes animate no paint (opacity · transform only; none named glow / pulse / ring)', not badkf, [n for n, _ in KF])
    inf = sorted({re.search(r'^([\w-]+)', v).group(1) for s, k, v in D if k == 'animation' and 'infinite' in v})
    A.check(f'{tag} ② endless animations only {list(endless) or "none"}', inf == sorted(endless), inf)
    # ③ amber: its four meanings only (고름 · 포커스 · 열림 · 완료), never on a failure / stale rule
    bad = [(s, k, v) for s, k, v in D if AMBER.search(v) and not amber_ok(s)]
    A.check(f'{tag} ③ amber only on selected / switched-on / open / done / focus rules', not bad, bad)
    bad = [(s, v) for s, k, v in D if STATUS.search(s) and AMBER.search(v)]
    A.check(f'{tag} ③ failure / stale marks never amber (! = --fail-dot)', not bad, bad)
    # ④ type
    bad = []
    for s, k, v in D:
        if k in ('font-size', 'font'):
            vv = novar(v)
            if (re.search(r'\d(px|pt|rem|em)\b', vv) or (k == 'font-size' and vv.strip() not in ('T', 'inherit'))) and not _ok(font_ok, s, v):
                bad.append((s, v))
    A.check(f'{tag} ④ every font size is var(--fs-*) (nothing under 11px)', not bad, bad)
    used = set(re.findall(r'var\((--fs-[\w-]+)', css))
    A.check(f'{tag} ④ only the seven steps (11 · 12 · 13 · 14 · 16 · 20 · 26)', used <= STEPS, sorted(used - STEPS))
    lh = [(s, v) for s, k, v in D if k == 'line-height' and not (v.startswith('var(--lh-') or v in ('1', 'normal', 'inherit')) and not _ok(lh_ok, s, v)]
    A.check(f'{tag} ④ line heights from --lh-*', not lh, lh)
    # ⑤ space: --space-* · literal 0 / ±1px · negative margins (hit areas, optical corrections) · named exceptions
    bad = []
    for s, k, v in D:
        if k not in SPACE:
            continue
        nums = [float(n) for n in re.findall(r'(-?\d*\.?\d+)px', re.sub(r'env\([^)]*\)', 'E', novar(v)))]
        off = [n for n in nums if n not in (0, 1, -1)]
        if off and not all(n < 0 for n in off) and not _ok(space_ok, s, k, v):
            bad.append((s, k, v))
    A.check(f'{tag} ⑤ padding / margin / gap on the --space-* scale (literal only 0 · ±1px, negative margins, named exceptions)', not bad, bad)
    # ⑥ corners
    bad = []
    for s, k, v in D:
        if 'radius' in k:
            vv = re.sub(r'(?<![\d.])0px', '0', novar(v)).strip()
            if (re.search(r'\d(px|em|rem)\b', vv) or (re.search(r'\d+%', vv) and vv != '50%')) and not _ok(radius_ok, s, v):
                bad.append((s, v))
    A.check(f'{tag} ⑥ corners from tokens (--r-* · --card-r · --sheet-r · 50% dots; nested = outer − gap named)', not bad, bad)
    # ⑦ heights
    bad = [(s, k, v) for s, k, v in D if k in ('height', 'min-height', 'max-height') and re.search(r'\d+px', novar(v))
           and not ('(pointer:coarse)' in s and '44px' in v) and not _ok(height_ok, s, k, v)]
    A.check(f'{tag} ⑦ heights from --h-* (literal px only named: icon · mark · badge 18 · data cells · 44 hit areas)', not bad, bad)
    # ⑧ motion
    anybez = [(s, v) for s, k, v in D if 'cubic-bezier(' in v or re.search(r'\bease(-in|-out|-in-out)?\b', v)]
    A.check(f'{tag} ⑧ no hand-written curves (springs --sp-*; press --c-fast / --c-out)', not anybez, anybez)
    lit = []
    for s, k, v in D:
        if k in ('transition', 'transition-duration', 'transition-delay', 'animation', 'animation-duration', 'animation-delay'):
            if any(float(d[0]) != 0 for d in re.findall(r'(?<![\w-])(\d*\.?\d+)(ms|s)\b', novar(v))) and not _ok(dur_ok, s, v):
                lit.append((s, v))
    A.check(f'{tag} ⑧ no literal durations (springs, press 0s, the --c-* / --sp-* lengths as tokens)', not lit, lit)
    old = sorted({(s, m) for s, k, v in D for m in re.findall(r'--c-(?:base|slow|switch|in\b|dwell)|--m-[\w-]+', v) if not _ok(old_ok, s, m)})
    A.check(f'{tag} ⑧ none of the old curve / length tokens (--c-base · --c-slow · --c-in · --c-switch · --m-*) unless named', not old, old)
    press = [s for s, k, v in D if k == 'transform' and v == 'translateY(1px)' and not any(s2 == s and k2 == 'transition-duration' and v2 == '0s' for s2, k2, v2 in D)]
    A.check(f'{tag} ⑧ press goes down at once (transition-duration 0s), comes back on --c-fast', not press, press)
    hov = [s for s, _ in R if ':hover' in s and '(hover:hover)and(pointer:fine)' not in s.replace(' ', '')]
    A.check(f'{tag} ⑧ hover only inside (hover:hover) and (pointer:fine) (design.md §8)', not hov, hov)
    A.check(f'{tag} ⑧ one reduce switch (html[data-motion]): no prefers-reduced-motion, no (hover:none) resets',
            'prefers-reduced-motion' not in css and '(hover:none)' not in css.replace(' ', ''))
    # ⑨ themes: the four themes differ through the template's role tokens
    theme = [s for s, _ in R if 'data-theme' in s and not _ok(theme_ok or {}, s)]
    A.check(f'{tag} ⑨ no theme-specific rule unless named (role tokens carry the themes)', not theme, theme)


def read(rel):
    return (pathlib.Path(__file__).resolve().parents[1] / rel).read_text(encoding='utf-8')


def in_build(A, tag, needles):
    """the build carries this CSS (web/ and dist/)"""
    root = pathlib.Path(__file__).resolve().parents[1]
    for b in ('web/index.html', 'dist/index.html'):
        t = (root / b).read_text(encoding='utf-8')
        miss = [n for n in needles if n not in t]
        A.check(f'{tag} build: {b} carries it', not miss, miss)
