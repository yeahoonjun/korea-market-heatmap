#!/usr/bin/env python3
"""Design-standard audit of src/stock (docs/standards/design.md, AGENTS §3-31 — the 종목 페이지 step of design.md §11).

  python3 qa/stock/audit_css.py            (no browser, no server; exit 1 on any failure)

CSS (src/stock/stock.css):
  ① no gradient paint — gradients only as content masks (the 같은 업종 row's fading edge) and the 예상 hatch, a data encoding (재무 · 배당
     bars, their legend dot); the glass themes' sheen comes from the template's --bar-bg / --pop-bg tokens (design.md §2 exception)
  ② no glow — no drop-shadow(); no box- / text-shadow layer that is an even halo (blur > 0 at offset 0 0) or a blurred amber / status
     colour, except the chart legend's rim in the chart's own ground colour (data over data, like the template's tile labels); no
     @keyframes that animate a shadow, and none named glow / pulse / shim
  ③ status — the 실시간 chip uses --live, the failed async key's ! uses --fail-dot; amber (--acc*, --amber) only in selected / focused /
     open / switched-on / done rules
  ④ type on the scale — every font-size is var(--fs-*) (or em / %); nothing under 11px
  ⑤ space on the scale — padding / margin / gap literal px only 0 or ±1px (the 1px-rule correction)
  ⑥ corners from tokens (var / calc / min / max of tokens, 50% for round dots, 0)
  ⑦ control heights from --h-* (a 44px press area is a pseudo-element); badges follow the recipe: 18px high, --r-badge, --fs-xs
  ⑧ motion — no bouncy bezier, no literal durations in transitions / animations (springs, --c-* press tokens, 0s press), endless
     animations only the live dot's and the skeletons' breath (opacity), hover only inside (hover:hover) and (pointer:fine), one reduce
     switch (html[data-motion], no prefers-reduced-motion media in the module)
  ⑨ glass material kept (사용자 2026-11-16 01:32): the stuck header and the 분 picker keep --bar-bg / --bar-sh / --blur-bar and --pop-bg /
     --blur in the glass themes
JS (src/stock/stock.js): icons are .sp-ic (1.75px, non-scaling) — no stroke-width attributes; no bouncy bezier, no 'ease-*' easings,
no literal WAAPI durations; the header numbers use KH.ui.roll / KH.ui.swap; the indicators use KH.spring.edges; the old odometer,
bar-regrow and shimmer are gone.
Build: web/index.html and dist/index.html carry this CSS.

Deliberate values off the scale (listed here so the audit can name them):
  - badge height 18px (design.md §5 badge recipe: .sp-chip · .sp-tag · .sp-nw-tag · .sp-lim · .sp-lg-live)
  - icon boxes 20px (← · ☆) and 12px chevrons (masks drawn at 1.75px) and 10px caret — icon sizes, not spacing
  - 재무 기간 segment buttons min-width 52px (분기 / 연간 keep one width)
  - data geometry, not spacing: 호가 rows 36px, row heights of data lists (투자자 34 / 32, 재무 값 30, 배당 48), plot heights (172 · 140 ·
    124 · 120 · 64 · 200), the chart card's 250–620px, skeleton insets, the sticky table offset (--sp-hh + 58px), the 360px name column
    breakpoint values
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (ROOT / 'src/stock/stock.css').read_text(encoding='utf-8')
JS = (ROOT / 'src/stock/stock.js').read_text(encoding='utf-8')
TPL = (ROOT / 'src/template.html').read_text(encoding='utf-8')
FAILS, PASSES = [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


css = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)


def rules(text):
    """(selector, declarations) for every style rule; at-rule preludes are kept in front of the selector"""
    out, stack, buf = [], [], ''
    for c in text:
        if c == '{':
            stack.append(buf.strip()); buf = ''
        elif c == '}':
            sel = stack.pop() if stack else ''
            if buf.strip():
                out.append((' '.join(stack + [sel]).strip(), buf.strip()))
            buf = ''
        else:
            buf += c
    return out


def decls(body):
    res = []
    for part in re.split(r';(?![^(]*\))', body):
        if ':' in part and not part.strip().startswith('@'):
            k, v = part.split(':', 1)
            res.append((k.strip().lower(), v.strip()))
    return res


def split_layers(v):
    layers, depth, cur = [], 0, ''
    for ch in v:
        depth += ch == '('
        depth -= ch == ')'
        if ch == ',' and depth == 0:
            layers.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        layers.append(cur.strip())
    return layers


def novar(v):
    """var(--x, fallback) → T (nested parentheses included)"""
    out, i = '', 0
    while i < len(v):
        if v.startswith('var(', i):
            depth, j = 0, i
            while j < len(v):
                depth += v[j] == '('
                depth -= v[j] == ')'
                if depth == 0 and v[j] == ')':
                    break
                j += 1
            out += 'T'; i = j + 1; continue
        out += v[i]; i += 1
    return out


AMBER = re.compile(r'--acc\b|--acc-fill|--acc-line|--amber|--chip-ring|#ffb547|255\s*,\s*181\s*,\s*71', re.I)
R = [(s, b) for s, b in rules(css) if not s.startswith('@keyframes')]
D = [(sel, k, v) for sel, body in R for k, v in decls(body)]

# ① gradients
HATCH = ('.sp-ci .dot.hatch', '.sp-fin-col.est .b', '.sp-dbars .est .well i')
bad = [(s, k) for s, k, v in D if re.search(r'gradient\(', v) and k not in ('mask-image', '-webkit-mask-image', 'mask', '-webkit-mask')
       and not (k == 'background' and v.startswith('repeating-linear-gradient(135deg') and any(h in s for h in HATCH))]
check('① no gradient paint (content masks + the 예상 hatch only)', not bad, bad)
print('   gradients kept:', sorted({s for s, k, v in D if re.search(r'gradient\(', v)}))

# ② glow
bad = [(s, v) for s, k, v in D if 'drop-shadow(' in v]
check('② no filter: drop-shadow()', not bad, bad)
halo = []
for s, k, v in D:
    if k not in ('box-shadow', 'text-shadow'):
        continue
    for layer in split_layers(v):
        bare = novar(layer)
        nums = [float(x) for x in re.findall(r'(-?\d*\.?\d+)px', bare)]
        if len(nums) >= 3 and nums[2] > 0:
            even = abs(nums[0]) < 1e-9 and abs(nums[1]) < 1e-9
            coloured = bool(AMBER.search(layer) or re.search(r'--live|--fail|--up-text|--dn-text', layer))
            if (even or coloured) and not (s == '.sp-legend' and k == 'text-shadow' and '--sp-solid' in layer):
                halo.append((s, layer))
check('② no glow shadows (only the legend\'s rim in the chart ground colour)', not halo, halo)
kf = re.findall(r'@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}', css)
# (the 호가 flash's number pill — spFlUp / spFlDn, the map's 2+4 — paints a flat background colour; nothing else animates paint)
bad = [n for n, body in kf if re.search(r'box-shadow|text-shadow|drop-shadow', body) or (re.search(r'background', body) and n not in ('spFlUp', 'spFlDn'))
       or re.search(r'glow|pulse|shim', n, re.I)]
bad += [n for n, body in kf for b in re.findall(r'blur\((\d*\.?\d+)px\)', body) if float(b) > 2]
check('② keyframes animate no shadow / paint (blur ≤ 2px only — the §6-4 text swap; the 호가 number pill of the 2+4 flash)', not bad and len(kf) >= 6, (bad, [n for n, _ in kf]))
check('② the old pulse ring and shimmer are gone', 'spPulse' not in CSS and 'spShim' not in CSS and 'linear-gradient(90deg, var(--sp-w5)' not in CSS)

# ③ status colours
live = [v for s, k, v in D if s == '.sp-chip.live' and k in ('color', 'background', 'box-shadow')] + [v for s, k, v in D if s == '.sp-chip.live i' and k == 'background']
check('③ 실시간 chip and its dot use --live (no amber)', live and all('--live' in v and not AMBER.search(v) for v in live), live)
fail = [v for s, k, v in D if '[data-st="fail"] .kwn' in s and k == 'color']
check('③ the failed key\'s ! is --fail-dot', fail == ['var(--fail-dot)'], fail)
OK_AMBER = re.compile(r'aria-pressed="true"|aria-checked="true"|aria-expanded="true"|aria-selected="true"|data-st="done"|sp-ix-line|\.sp-dfilt|:focus')
bad = [(s, k, v) for s, k, v in D if AMBER.search(v) and not OK_AMBER.search(s)]
check('③ amber only for selected / open / switched-on / done / focus', not bad, bad)

# ④ type
bad, small = [], []
for s, k, v in D:
    if k in ('font-size', 'font'):
        vv = novar(v)
        if re.search(r'\d(px|pt|rem)\b', vv):
            bad.append((s, v))
check('④ every font size is a --fs-* token', not bad, bad)
fs = re.findall(r'--fs-(xs|sm|md|lg|xl|2xl|num)\b', CSS)
undef = sorted(set(re.findall(r'var\((--fs-[\w-]+)', CSS)) - {f'--fs-{x}' for x in ('xs', 'sm', 'md', 'lg', 'xl', '2xl', 'num')})
check('④ only the seven steps (11 · 12 · 13 · 14 · 16 · 20 · 26), so nothing under 11px', not undef and len(fs) > 100, undef)

# ⑤ space
bad = []
SPACE = ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'padding-inline', 'padding-block',
         'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap')
for s, k, v in D:
    if k in SPACE:
        vv = novar(v)
        vv = re.sub(r'env\([^)]*\)', 'E', vv)
        if any(float(n) not in (0, 1, -1) for n in re.findall(r'(-?\d*\.?\d+)px', vv)):
            bad.append((s, k, v))
check('⑤ padding / margin / gap on the --space-* scale (literal only 0 or ±1px)', not bad, bad)

# ⑥ corners
bad = []
for s, k, v in D:
    if 'radius' in k:
        vv = re.sub(r'(?<![\d.])0px', '0', novar(v))        # max(0px, …) clamps are fine
        if re.search(r'\d(px|em|rem)\b', vv) or (re.search(r'\d+%', vv) and vv.strip() != '50%'):
            bad.append((s, v))
check('⑥ corners from tokens (50% only for round dots)', not bad, bad)

# ⑦ control heights · badges
CTRL = re.compile(r'\.sp-back\b|\.sp-star\b|\.sp-link\b|\.sp-btn\b|\.sp-peer\b(?!s)|\.sp-seg\b|\.sp-mseg\b|\.sp-dfilt\b|\.sp-nwseg\b|\.sp-mac\b|summary|\.sp-switch\b|\.sp-ivm-in > button|\.sp-more\b|\.sp-cp-link\b|\.sp-ma\b')
bad, seen = [], 0
for s, k, v in D:
    last = [re.split(r'[\s>+~]+', part.strip())[-1] for part in s.split(',')]   # the element the rule sizes (not an icon inside a key)
    sized = any(CTRL.search('.' + x.split('.', 1)[-1] if '.' in x else x) or (x.startswith('button') and CTRL.search(s)) for x in last)
    if k in ('height', 'min-height') and sized and '::' not in s:
        seen += 1
        if re.search(r'\d+px', novar(v)):
            bad.append((s, k, v))
check(f'⑦ control heights from --h-* (32 / 40 keys and segments, 36 / 44 rows; {seen} rules)', not bad and seen >= 12, bad)
BADGES = ('.sp-chip', '.sp-tag', '.sp-nw-tag', '.sp-lim', '.sp-legend .sp-lg-live')
rec = {}
for b in BADGES:
    ds = {k: v for s, k, v in D if s == b}
    rec[b] = (ds.get('height'), ds.get('border-radius'), ds.get('font-size'))
check('⑦ badges follow one recipe (18px · --r-badge · --fs-xs)', all(r == ('18px', 'var(--r-badge)', 'var(--fs-xs)') for r in rec.values()), rec)

# ⑧ motion
bez = [(s, v) for s, k, v in D for m in re.finditer(r'cubic-bezier\(([^)]*)\)', v) if any(abs(float(x)) > 1 for x in m.group(1).split(',')[1::2])]
check('⑧ no bouncy bezier in CSS', not bez, bez)
lit = []
for s, k, v in D:
    if k in ('transition', 'transition-duration', 'animation', 'animation-duration', 'transition-delay', 'animation-delay'):
        for d in re.findall(r'(?<![\w-])(\d*\.?\d+)(ms|s)\b', novar(v)):
            if float(d[0]) != 0:
                lit.append((s, v)); break
check('⑧ no literal durations (springs --sp-*, press --c-*, 0s)', not lit, lit)
inf = sorted({re.search(r'(sp\w+)', v).group(1) for s, k, v in D if k == 'animation' and 'infinite' in v})
check('⑧ endless animations only the live dot\'s and the skeletons\' breath', inf == ['spBreath', 'spFade'], inf)
hov = [s for s, _ in R if ':hover' in s and '(hover:hover)and(pointer:fine)' not in s.replace(' ', '')]
check('⑧ hover only on a fine pointer', not hov, hov)
check('⑧ one reduce switch: html[data-motion="reduced"], no prefers-reduced-motion in the module', 'prefers-reduced-motion' not in css and css.count('html[data-motion="reduced"]') >= 4)

# ⑨ glass material
head = ' '.join(b for s, b in R if 'html[data-theme^="glass"] .sp-head' in s)
ivm = ' '.join(b for s, b in R if s == 'html[data-theme^="glass"] .sp-ivm') + ' ' + ' '.join(b for s, b in R if s == '.sp-ivm')
check('⑨ glass: the stuck header keeps --bar-bg · --bar-sh · --blur-bar', all(t in head for t in ('var(--bar-bg', 'var(--bar-sh', 'backdrop-filter: var(--blur-bar')), head[:200])
check('⑨ glass: the 분 picker keeps --pop-bg and the blur', 'var(--pop-bg)' in ivm and 'backdrop-filter: var(--blur' in ivm, ivm[:200])
gl = re.search(r'html\[data-theme="glass-dark"\]\{(.*?)\n\}', TPL, re.S)
check('⑨ the template still carries the glass sheen in --bar-bg / --tip-bg (main 90e1f3b)', bool(gl) and re.search(r'--bar-bg:linear-gradient', gl.group(1)) and re.search(r'--tip-bg:linear-gradient', gl.group(1)))

# JS
js = re.sub(r'/\*.*?\*/', '', JS, flags=re.S)
check("JS: icons are .sp-ic (1.75px on screen), no stroke-width attributes", "'stroke-width'" not in js and js.count("class: 'sp-ic'") + len(re.findall(r"class: '[\w -]*sp-ic'", js)) >= 5)
jsb = [m.group(0) for m in re.finditer(r'cubic-bezier\(([^)]*)\)', js) if any(abs(float(x)) > 1 for x in m.group(1).split(',')[1::2])]
check('JS: no bouncy bezier', not jsb, jsb)
jse = re.findall(r"easing:\s*'ease[\w-]*'", js) + re.findall(r"\b\d*\.\d+s (?:linear|ease|cubic)", js)
check("JS: no 'ease-*' easings or literal inline transitions", not jse, jse)
jsd = re.findall(r'duration:\s*\d+', js)
check('JS: no literal WAAPI durations (spring tokens · TX of §6-4)', not jsd, jsd)
check('JS: the header numbers roll / swap with KH.ui.roll · KH.ui.swap', 'UI.roll(D, td, dir)' in js and 'UI.swap(I, ti, wi, dir)' in js)
check('JS: indicators on KH.spring.edges, lists on KH.spring.animate', 'KH.spring.edges(st.ind)' in js and js.count('KH.spring.animate(') >= 2)
check('JS: the old odometer, bar regrow and motion-brief tokens are gone', not re.search(r'setRoll|od-c|growBars|--m-quint|--m-2\b|M_OUT', js))

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    ok = '.sp-ind {' in page and 'spBreath' in page and 'spPulse' not in page and 'spShim' not in page and 'hn-d' in page
    check(f'build: {f} carries the new stock CSS', ok)

print(f'\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks passed')
sys.exit(1 if FAILS else 0)
