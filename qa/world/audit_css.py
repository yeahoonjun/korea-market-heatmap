#!/usr/bin/env python3
"""Design-standard audit of src/world (docs/standards/design.md, AGENTS §3-31 — the 해외 · 지표 step of design.md §11).

  python3 qa/world/audit_css.py            (no browser, no server; exit 1 on any failure)

CSS (src/world/world.css):
  ① no gradient paint — gradients only as data: the hatch of 참고 / 값 없음 (repeating-linear-gradient on .kw-tile.ref/.nod and the
     .kw-refsw legend swatch). The legend's colour scale is drawn by JS from the palette (data). The glass themes' material — the
     top sheen inside --sheet-bg / --tip-bg, the 1px edge reflection in --sheet-sh / --sheet-fl-sh, translucency and --blur — comes
     from the template's role tokens and is allowed (design.md §2 예외, user 2026-11-16 01:32); world.css itself paints none
  ② no glow — no filter: blur() / drop-shadow(); no box-shadow layer with blur at offset 0 0 or a blurred amber / status colour;
     text-shadow only the template's label token var(--lab-sh) (legibility of labels on data colours); no @keyframes that animate a
     shadow / filter, no pulse, no endless animation; no open-market glow layers (.kw-ggb / .kw-ggl / .kw-gp / kwRing gone).
     The one named exception — 「LED 전광판」 (design.md §2, AGENTS §3-27 끝, the 수출입은행 고시 boards): the lit dots' drop-shadow
     (.kw-lbg .on only, scaled by the dot pitch, in the dot's own colour) and the strip's endless kwLbRun (transform, .kw-lbk only),
     which must pause (key · hold · off screen · hidden tab) and stop in 줄이기
  ③ status — 장중 / open markets use --live, failure --fail-dot; amber (--acc*, --amber, #ffb547) only on selection (.sel),
     focus (:focus-visible) and switched-on (aria-pressed) rules; no --kw-* module token that is amber or a glow
  ④ type on the scale — font-size from --fs-* (em of a fitted tile label and calc(--fs-* × --gs) map labels allowed), nothing < 11px;
     the LED board's transparent real text (.kw-lbx) is sized to the dot digits (calc(--p × 6.4)) — never seen, shown at --fs-md in
     forced colours
  ⑤ space on the scale — padding / margin / gap literal px only 0 or 1px; the one exception is the outer layout's 14px gap / bottom
     (#world.kw = the template's main.layout, a design.md §11 map-box exception)
  ⑥ corners — border-radius from tokens (--r-* · --card-r · --sheet-r · 50% for dots), no bare px
  ⑦ motion — no bezier past 1, no literal durations in transition / animation (springs --sp-*, press 0s / --c-fast, the first-opening
     stagger via --kw-seq-*), hover only inside (hover:hover) and (pointer:fine), no @media (prefers-reduced-motion) / .kw-rm second
     switch (html[data-motion] is the one switch)
  ⑧ controls — the 목록 · 지도 / 지역순 · 등락률순 segments are the template's .seg (no size override), list rows --h-row, keys
     --h-key / --h-row, the × an SVG at 1.75px
JS (src/world/world.js): no bouncy bezier, no 'ease-*' easings, no literal WAAPI durations, no glow / blur strings, no pulse rings,
  values written through KH.ui.swap / KH.ui.roll (swapTo · setBigNum), no text "×" close key.
Build: web/index.html and dist/index.html carry this CSS (no kwRing / kw-ggb / --kw-glow left from the old world module).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (ROOT / 'src/world/world.css').read_text(encoding='utf-8')
JS = (ROOT / 'src/world/world.js').read_text(encoding='utf-8')
FAILS, PASSES = [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


def strip_comments(s):
    return re.sub(r'/\*.*?\*/', '', s, flags=re.S)


css = strip_comments(CSS)


def rules(text):
    """(selector, declarations) for every style rule, at-rules flattened (the @media prelude is kept with the selector)"""
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
        if ':' in part:
            k, v = part.split(':', 1)
            res.append((k.strip().lower(), v.strip()))
    return res


def split_layers(v):
    layers, depth, cur = [], 0, ''
    for ch in v:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            layers.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        layers.append(cur.strip())
    return layers


AMBER = re.compile(r'--acc\b|--acc-fill|--acc-line|--acc-soft|--acc-bd|--amber|#ffb547|255\s*,\s*181\s*,\s*71', re.I)
R = rules(css)
D = [(sel, k, v) for sel, body in R for k, v in decls(body)]
GLASS_TOK = re.compile(r'var\(--(sheet-bg|tip-bg|bar-bg|sheet-sh|sheet-fl-sh|tip-sh|blur)\b')

# ① gradients only as data
HATCH_SEL = re.compile(r'\.kw-tile\.ref|\.kw-tile\.nod|\.kw-refsw')
bad = [(s, k, v) for s, k, v in D if re.search(r'gradient\(', v) and not (HATCH_SEL.search(s) and 'repeating-linear-gradient(' in v)]
check('① no gradient paint (only the data hatch of 참고 / 값 없음)', not bad, bad)
print('   data hatches:', sorted({s for s, k, v in D if 'repeating-linear-gradient(' in v}))
glass = sorted({s for s, k, v in D if GLASS_TOK.search(v)})
check('① glass material kept: the sheet takes --sheet-bg (sheen in glass), --sheet-fl-sh / --sheet-sh (edge reflection) and --blur',
      any('.kw-sheet' in s for s in glass) and re.search(r'\.kw-sheet\{[^}]*background:var\(--sheet-bg', css) and re.search(r'\.kw-sheet\{[^}]*backdrop-filter:var\(--blur', css), glass)
print('   glass material via role tokens:', glass)
gl_override = [(s, k, v) for s, k, v in D if 'glass' in s and k in ('background', 'background-color', 'backdrop-filter', '-webkit-backdrop-filter', 'box-shadow') and 'none' in v]
check('① no world rule takes the glass material away (no background / blur / shadow: none under a glass theme)', not gl_override, gl_override)

# ② glow
LED_GLOW = ('.kw-lbg .on', 'filter', 'drop-shadow(0 0 calc(var(--p) * .7) color-mix(in srgb,currentColor 58%,transparent))')
bad = [(s, k, v) for s, k, v in D if re.search(r'drop-shadow\(|(?<![\w-])blur\(', v) and k not in ('backdrop-filter', '-webkit-backdrop-filter') and (s, k, v) != LED_GLOW]
check('② no filter: blur() / drop-shadow() (but the LED board\'s lit dots — design.md §2 「LED 전광판」)', not bad, bad)
check('② 「LED 전광판」: the glow is one drop-shadow on the lit dots only, in their own colour, scaled by the dot pitch (no glow on the panel, '
      'the names or the strip)', [x for x in D if x == LED_GLOW] == [LED_GLOW] and not [x for x in D if re.search(r'\.kw-lb[a-z]', x[0]) and x[1] in ('filter', 'text-shadow')
                                                                                   and x != LED_GLOW])
led = re.search(r'--kw-led:\s*([^;]+);', css)
check('② 「LED 전광판」: the LED is one warm white (#fbecd6 — not amber, not a data colour) in every theme',
      led and led.group(1).strip() == '#fbecd6' and len(re.findall(r'--kw-led:', css)) == 1, led and led.group(0))
halo = []
for s, k, v in D:
    if k == 'text-shadow':
        if v.strip() not in ('var(--lab-sh)', 'none'):
            halo.append((s, v))
        continue
    if k != 'box-shadow':
        continue
    for layer in split_layers(v):
        if re.fullmatch(r'var\(--[\w-]+(,.*)?\)', layer):
            continue                                   # a role token (the template's card / sheet / key / map shadow)
        vals = [float(x) for x in re.findall(r'(-?\d*\.?\d+)px', re.sub(r'var\([^)]*\)', '', layer))]
        if len(vals) >= 3 and vals[2] > 0:
            even = abs(vals[0]) < 1e-9 and abs(vals[1]) < 1e-9
            coloured = bool(AMBER.search(layer) or re.search(r'--live|--fail', layer))
            if even or coloured:
                halo.append((s, layer))
check('② no glow shadows (no blurred halo, no blurred amber / status colour; text-shadow only var(--lab-sh))', not halo, halo)
kf = re.findall(r'@keyframes\s+([\w-]+)\s*\{(.*?\})\s*\}', css, flags=re.S)
bad = [n for n, body in kf if (re.search(r'box-shadow|text-shadow|filter|transform', body) or re.search(r'glow|pulse|ring', n, re.I))
       and not (n == 'kwLbRun' and re.fullmatch(r'to\{transform:translateX\(var\(--kw-lbs-d,[^)]*\)\)\}', body.strip()))]
check('② no @keyframes that animate a shadow / filter / scale (no glow, no pulse ring; the LED strip\'s kwLbRun only translates)', not bad, [n for n, _ in kf])
inf = [(s, v) for s, k, v in D if k.startswith('animation') and 'infinite' in v]
check('② no endless animation in #world (nothing pulses) — but the LED strip (.kw-lbk kwLbRun, linear)', [(s, v) for s, v in inf if not (s == '.kw-lbk' and v.startswith('kwLbRun ') and ' linear ' in v)] == [], inf)
hold = re.search(r'\.kw-lbs:is\(\.ps,\.hd,\.off,\.hid\) \.kw-lbk\{animation-play-state:paused\}', css)
still = re.search(r'html\[data-motion="reduced"\] \.kw-lbk[^{]*\{[^}]*animation:none', css)
check('② 「LED 전광판」: the strip pauses (key · hover / focus hold · off screen · hidden tab) and stands still in 줄이기', hold and still)
lit = re.search(r'\.kw-lbt td\.lit \.on\{animation:kwLbLit var\(--kw-lb-lit\) steps\(9,end\) var\(--kw-lb-d,0ms\) backwards\}', css)
check('② 「LED 전광판」: the relight is a 9-step clip reveal of the lit dots (no overshoot, no flash), 0 ms in 줄이기',
      lit and re.search(r'html\[data-motion="reduced"\]\{[^}]*--kw-lb-lit:0ms', css))
gone = [t for t in ('.kw-ggb', '.kw-ggl', '.kw-gp', 'kwRing', '--kw-glow', '--kw-open', 'kw-paused', 'kwFlc', 'kwFl{') if t in css]
check('② the open-market glow, its pulse rings and the old value flash are gone', not gone, gone)

# ③ status colours
OK_AMBER_SEL = re.compile(r'\.sel\b|:focus-visible|aria-pressed="true"|\.kw-gsel')
bad = [(s, k, v) for s, k, v in D if AMBER.search(v) and not OK_AMBER_SEL.search(s)]
check('③ amber only on selection (.sel / the map selection), focus (:focus-visible) and switched-on (aria-pressed)', not bad, bad)
OPEN_SEL = re.compile(r'\.open|\.kw-om1 b::before|\.kw-gopen')
live = sorted({s for s, k, v in D if 'var(--live)' in v})
need = ['.kw-sd.open', '.kw-gopen path', '.kw-gdot.open', '.kw-gmk.open', '.kw-st.open::before', '.kw-chip.open::before', '.kw-om1 b::before', '.kw-chip-l.open::before']
miss = [n for n in need if not any(n in s for s in live)]
check('③ 장중 / open markets drawn in --live (list dot · map outline · markers · sheet badge · tile chip · 지금 열린 시장 · legend)', not miss, miss)
openbad = [(s, k, v) for s, k, v in D if OPEN_SEL.search(s) and k in ('background', 'background-color', 'fill', 'stroke', 'color', 'border-color') and 'var(--live)' not in v and not s.endswith('.close')
           and not ('.kw-chip.close' in s or 'close::before' in s) and v not in ('none',) and 'kw-dot-st' not in v and 'kw-dot-sel' not in v]
openbad = [x for x in openbad if not re.search(r'\.kw-gdot\.sel|\.kw-gmk\.sel|\.open\s*\{?$', x[0]) or 'var(--live)' in x[2]]
check('③ open-state rules paint with --live only', not [x for x in openbad if 'stroke-width' not in x[1]], openbad)
fail = sorted({s for s, k, v in D if 'var(--fail-dot)' in v})
check('③ a failed refresh = ! in --fail-dot (.kw-stale)', any('.kw-stale' in s for s in fail), fail)
tokdefs = re.findall(r'(--kw-[\w-]+)\s*:\s*([^;]+)', css)
bad = [(n, v) for n, v in tokdefs if AMBER.search(v) or re.search(r'glow|open|fl\b|flc|-sh$', n)]
check('③ no amber / glow / flash module tokens (--kw-glow-* · --kw-open* · --kw-fl* · --kw-*-sh gone)', not bad, bad)
spin = re.search(r'\.kw-msg\.busy b \.kspn\{[^}]*\}', css)
check('③ the loading ring is neutral (working is not one of amber\'s meanings)', spin and not AMBER.search(spin.group(0)), spin and spin.group(0))

# ④ type scale
bad = []
for s, k, v in D:
    if k in ('font-size', 'font'):
        vv = re.sub(r'var\([^)]*\)', 'T', v)
        if re.search(r'\d(px|pt|rem)\b', vv):
            bad.append((s, v))
        if k == 'font-size' and not re.fullmatch(r'(T|calc\(T \* T\)|\.\d+em|\d+(\.\d+)?em|inherit)', vv.replace('var(--gs,1)', 'T')) \
                and not (s == '.kw-lbx' and v == 'calc(var(--p) * 6.4)'):
            bad.append((s, v))
check('④ font sizes on the --fs-* scale (em inside fitted tile labels, calc(--fs-* × --gs) for map labels)', not bad, bad)
fs_used = sorted(set(re.findall(r'--fs-[\w]+', css)))
check('④ only the seven steps are used', set(fs_used) <= {'--fs-xs', '--fs-sm', '--fs-md', '--fs-lg', '--fs-xl', '--fs-2xl', '--fs-num'}, fs_used)

# ⑤ space
bad = []
for s, k, v in D:
    if k in ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'margin', 'margin-left', 'margin-right',
             'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap'):
        if s == '#world.kw' and k in ('gap', 'padding') and v in ('14px', '0 var(--edge) 14px'):
            continue                                   # = the template's main.layout (design.md §11 exception list)
        vv = re.sub(r'var\([^)]*\)', 'T', re.sub(r'env\([^)]*\)', 'E', v))
        vv = re.sub(r'calc\(6px \+ T\)', 'T', vv)       # the dot's width + a space step (.kw-om2 aligns under the name)
        for n in re.findall(r'(-?\d*\.?\d+)px', vv):
            if float(n) not in (0, 1, -1):
                bad.append((s, k, v)); break
check('⑤ padding / margin / gap on the --space-* scale (literal only 0 or 1px; the outer 14px = the template layout)', not bad, bad)

# ⑥ corners
bad = []
for s, k, v in D:
    if 'radius' in k:
        vv = re.sub(r'var\((--[\w-]+)(,[^)]*)?\)', 'T', v)
        if v.strip() in ('0', '50%') or '!important' in v and '50%' in v:
            continue
        vv = re.sub(r'max\(2px,\s*calc\(T - 4px\)\)', 'T', vv)   # the template's floating-sheet corner: --sheet-r − 4, at least 2
        if re.search(r'\d+px', vv) or not re.search(r'T|inherit', vv):
            bad.append((s, v))
check('⑥ corners from tokens (--r-* · --card-r · --sheet-r; 50% for dots; 0 for tiles)', not bad, bad)

# ⑦ motion
bez = [(s, v) for s, k, v in D for m in re.finditer(r'cubic-bezier\(([^)]*)\)', v) if any(abs(float(x)) > 1 for x in m.group(1).split(',')[1::2])]
check('⑦ no bouncy bezier (y past 0…1)', not bez, bez)
anybez = [(s, v) for s, k, v in D if 'cubic-bezier(' in v]
check('⑦ no hand-written curves at all (springs --sp-* · press --c-*)', not anybez, anybez)
lit = []
for s, k, v in D:
    if k in ('transition', 'transition-duration', 'animation', 'animation-duration', 'animation-delay'):
        vv = re.sub(r'var\([^)]*\)', 'T', v)
        for d in re.findall(r'(?<![\w.-])(\d*\.?\d+)(ms|s)\b', vv):
            if float(d[0]) != 0:
                lit.append((s, v)); break
check('⑦ no literal durations in transitions / animations (springs, press 0s, the stagger via --kw-seq-*)', not lit, lit)
hov = [s for s, body in R if ':hover' in s and '(hover:hover)and(pointer:fine)' not in s.replace(' ', '') and not re.search(r'\.kw-gl:hover$', s)]
check('⑦ hover styles only inside (hover:hover) and (pointer:fine) (design.md §8; .kw-gl:hover only lifts z-index)', not hov, hov)
check('⑦ one reduced-motion switch (html[data-motion]): no @media (prefers-reduced-motion), no .kw-rm rules',
      'prefers-reduced-motion' not in css and '.kw-rm' not in css)
seq = re.findall(r'--kw-seq-\d\s*:\s*(\d+)ms', css)
check('⑦ the first-opening stagger is front-loaded and short (40 → 30 ms, ≤ 300 ms in all)', seq and int(seq[-1]) <= 300 and len(set(seq)) > 1, seq)

# ⑧ controls
segov = [(s, k, v) for s, k, v in D if re.search(r'\.kw-seg\s+button|\.kw-seg>button', s) and k in ('padding', 'font-size', 'height', 'min-height')]
check('⑧ the 목록 · 지도 / 지역순 · 등락률순 segments are the template\'s .seg (no size override)', not segov, segov)
def first(sel, prop):
    for s, k, v in D:
        if s == sel and k == prop:
            return v
    return None
checks = {('.kw-lr', 'min-height'): 'var(--h-row)', ('.kw-retry', 'height'): 'var(--h-key)', ('.kw-x', 'width'): 'var(--h-key)',
          ('.kw-peers button', 'height'): 'var(--h-key)', ('.kw-gc', 'min-height'): 'var(--h-row)', ('.kw-sh', 'min-height'): 'var(--h-row)'}
bad = [(sel, p, first(sel, p)) for (sel, p), want in checks.items() if first(sel, p) != want]
check('⑧ heights from --h-* (rows · group heads --h-row, keys · chips · × --h-key; phones 44 / 40)', not bad, bad)
ph = [(s, k, v) for s, k, v in D if '(max-width:760px)' in s.replace(' ', '') and '.kw-x' in s and k in ('width', 'height')]
check('⑧ the × is 44px on phones (--h-row)', ph and all(v == 'var(--h-row)' for s, k, v in ph), ph)
press = [(s, v) for s, k, v in D if k == 'filter' and 'brightness(' in v]
check('⑧ press darkens with the theme\'s --press-f (not a fixed brightness — glass dark brightens)', not press, press)
sink = [s for s, k, v in D if k == 'transform' and 'translateY(1px)' in v]
check('⑧ keys and chips sink 1px (다시 시도 · × · peers chips · the snapshot key)', all(any(n in s for s in sink) for n in ('.kw-retry', '.kw-x', '.kw-peers button', '.kw-snap-a')), sink)
rowsink = [s for s in sink if re.search(r'\.kw-lr|\.kw-row|\.kw-tile|\.kw-gb|\.kw-go\b|\.kw-gc', s)]
check('⑧ data rows, tiles and map labels never sink (controls.md §5: filter only)', not rowsink, rowsink)

# JS
js = re.sub(r'/\*.*?\*/', '', JS, flags=re.S)
js = re.sub(r'(?m)//.*$', '', js)
jsb = [m.group(0) for m in re.finditer(r'cubic-bezier\(([^)]*)\)', js)]
check('JS: no hand-written bezier', not jsb, jsb)
jse = re.findall(r"easing:\s*'ease[\w-]*'", js) + re.findall(r"\b\d*\.\d+s (?:linear|ease|cubic)", js) + re.findall(r'duration:\s*\d+', js)
check('JS: no keyword easings, inline transitions or literal WAAPI durations', not jse, jse)
jsg = re.findall(r"drop-shadow|filter:\s*blur|kw-gp\b|kw-ggb|kw-ggl|kwRing|'just'|animationDelay", js)
check('JS: no glow / blur strings, no pulse rings or their stagger', not jsg, jsg)
check('JS: values change through KH.ui.swap (list · bar counts · map labels) and KH.ui.roll (the sheet\'s big number, 화려하게)',
      'UI.swap(' in js and 'UI.roll(' in js and js.count('swapTo(') >= 8 and 'setBigNum(' in js and 'flash(' not in js)
check("JS: the close key is the SVG × (no text '×')", "'×')" not in js and 'closeIcon()' in js and "'stroke-width': '1.75'" in js)
check('JS: the hover outline on the world map follows a mouse only', "e.pointerType !== 'mouse'" in js)

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    ok = 'kw-gopen' in page and 'kwRing' not in page and '.kw-ggb' not in page and '--kw-glow' not in page and 'kw-pt' in page
    check(f'build: {f} carries the new world CSS / JS (no kwRing / kw-ggb / --kw-glow)', ok)

print(f'\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks passed')
sys.exit(1 if FAILS else 0)
