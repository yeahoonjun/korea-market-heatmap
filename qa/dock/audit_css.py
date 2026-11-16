#!/usr/bin/env python3
"""Design-standard audit of the phone dock (아래 막대) and its 🔍 search sheet (docs/standards/design.md, docs/standards/dock.md,
AGENTS §3-26 · §3-31 — the last step of design.md §11 ③ "… 뉴스 · 공시 · 아래 막대", ux/std-dock).

  python3 qa/dock/audit_css.py            (no browser, no server; exit 1 on any failure)

The dock lives in src/template.html: the CSS rules whose selector names .dock · .dk-* · .ssheet · .ss-* · .dkset (and the footer's
room under the page), the dock tokens --dock-bg / --dock-sh / --dock-r / --dock-div of the four themes, and the script from
"아래 막대 — the phone dock" to the boot block.

CSS
  ① no gradient paint, no blur on the dock (dock.md §4: the glass dock is thick glass to look at, never blurred — it only floats
     once the map has gone by); --dock-bg is a flat colour in every theme
  ② no glow — no drop-shadow() / blur() filter, no shadow layer blurred at offset 0 0 (--dock-sh included), keyframes move only
     opacity / transform, nothing endless
  ③ glass material kept (사용자 2026-11-16 01:32 "글라스가 플랫해지면 글라스가 아닌데"): the search sheet takes --sheet-bg (the glass
     themes' top sheen — a gradient inside --tip-bg), --sheet-sh (the 1px inset edge reflection) and backdrop-filter: var(--blur); no
     dock / sheet rule takes them away under a glass theme; the template's glass --tip-bg still carries the sheen
  ④ amber only for the ★ (켜짐 — the same ★ as the ★관심 tab) — no other dock / sheet rule reads --acc*, --amber or #ffb547; no
     status colour hard-coded (states have none here)
  ⑤ type on the scale — font sizes var(--fs-*) only, the seven steps (nothing under 11px)
  ⑥ space on the scale — padding / margin / gap / inset literal px only 0 or ±1 (the page dots' −3px is an optical offset)
  ⑦ corners from tokens — var(--r-*) / var(--dock-r) / var(--sheet-r) / calc(var(--dock-r) − var(--space-3)) (inner = outer − the
     panel's padding, design.md §4)
  ⑧ heights — keys and rows from --h-* (🔍 · × · the sheet's box and rows = --h-row: 44 on phones); every other literal size is on the
     shape list below
  ⑨ motion — no hand-written curve (cubic-bezier) and none of the old --m-* tokens; transitions on the spring tokens (--sp-*) or the
     press tokens (--c-fast · --c-out, 0s down); the only literal time is the first rise's 40 ms stagger (design.md §6-2 P3); hover
     only inside (hover:hover) and (pointer:fine); no prefers-reduced-motion (html[data-motion] is the one switch)
JS
  icons 1.75px non-scaling (🔍 · the sheet's 🔍 · ×, no text ×); numbers through KH.ui.swap / KH.ui.roll (dkText) with the P4 rule
  (first draw · same value · 줄이기 · hidden · another thing in the cell → at once); the dock comes up with a quiet fill; pages flip with
  KH.spring 'lead' (held keys at once, snapping off while it moves); the sheet drags with KH.ui.sheetDrag; one hl plate (ssMark);
  no smooth scrollTo, no literal easing / duration strings.
Build: web/index.html and dist/index.html carry this CSS and script.

Shape values off the scale, on purpose (dock.md fixed them — data and shape, not spacing):
  - the panel's 56px height and the key-only panel's 56px width; the 72px of room under the page (8 + 56 + 8)
  - the cell's line heights: the top line 14px (dock.md §2: cell 44 · panel 56 · bottom 8 · top line 14 — qa/std_template limits),
    the value line 20px (font and box), the 등락 분포 count line 13px
  - the 등락 분포 bar 6px; the index line 44 × 18 (dock.md §2 "오늘 선(44 × 18)") that narrows to 24px before the value is cut (360px
    with no tracking on the 16px value); the page dots 4px (current 12px wide)
  - icon boxes: 🔍 18px in the key, × 16px, the sheet box's 🔍 at (--h-row − 16px) / 2; the 10px colour mark (column and square)
  - the search sheet's 78svh and its grip 38 × 4 (the same grip as the other phone sheets)
  - the dock's corner per theme (--dock-r): 기본 18 = the 🔍 key's 12 + the panel's 6 · 글라스 28 = the round key's 22 + 6 · 신문 4 (square
    paper) — nested corners share one centre (design.md §4 "안 = 바깥 − 여백")
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = (ROOT / 'src/template.html').read_text(encoding='utf-8')
FAILS, PASSES = [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:500]}'))


CSS = re.sub(r'/\*.*?\*/', '', SRC[SRC.index('<style>') + 7:SRC.index('</style>')], flags=re.S)


def rules(text):
    """(selector with its @media prelude, declarations) for every style rule"""
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


def layers(v):
    out, depth, cur = [], 0, ''
    for ch in v:
        depth += ch == '('
        depth -= ch == ')'
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def novar(v):
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


ALL = rules(CSS)
KF = [(s, b) for s, b in ALL if s.startswith('@keyframes')]
DOCK_SEL = re.compile(r'\.dock\b|\.dk-|\.ssheet|\.ss-|\.dkset|\bdkRise\b')
R = [(s, b) for s, b in ALL if not s.startswith('@keyframes') and DOCK_SEL.search(s)]
R += [(s, b) for s, b in ALL if re.search(r'(^|\s)footer$', s) and '72px' in b]
D = [(s, k, v) for s, b in R for k, v in decls(b)]
check(f'scope: {len(R)} dock / search-sheet rules found', len(R) >= 60, len(R))
AMBER = re.compile(r'--acc\b|--acc-fill|--acc-line|--acc-soft|--acc-bd|--amber|#ffb547|255\s*,\s*181\s*,\s*71', re.I)

# dock tokens per theme
TOKS = {}
for sel, body in ALL:
    for k, v in re.findall(r'(--dock-(?:bg|sh|r|div))\s*:\s*([^;]+)', body):
        TOKS.setdefault(k, []).append((sel, v.strip()))

# ① gradients · blur on the dock
bad = [(s, k, v) for s, k, v in D if 'gradient(' in v]
check('① no gradient paint in any dock / sheet rule', not bad, bad)
bad = [(s, k, v) for s, k, v in D if k in ('backdrop-filter', '-webkit-backdrop-filter') and not s.startswith('.ssheet')]
check('① no blur on the dock (only the search sheet takes the glass blur)', not bad, bad)
bad = [(s, v) for s, v in TOKS.get('--dock-bg', []) if 'gradient' in v or 'rgba' in v]
check(f'① --dock-bg is one flat, opaque colour in all {len(TOKS.get("--dock-bg", []))} themes', len(TOKS.get('--dock-bg', [])) == 4 and not bad, TOKS.get('--dock-bg'))

# ② glow
bad = [(s, k, v) for s, k, v in D if re.search(r'drop-shadow\(|(?<![\w-])blur\(', v) and k not in ('backdrop-filter', '-webkit-backdrop-filter')]
check('② no filter: blur() / drop-shadow()', not bad, bad)
halo = []
for s, k, v in D + [(s, '--dock-sh', v) for s, v in TOKS.get('--dock-sh', [])]:
    if k not in ('box-shadow', 'text-shadow', '--dock-sh'):
        continue
    for layer in layers(v):
        nums = [float(x) for x in re.findall(r'(-?\d*\.?\d+)px', novar(layer))]
        if 'inset' not in layer and len(nums) >= 3 and nums[2] > 0 and abs(nums[0]) < 1e-9 and abs(nums[1]) < 1e-9:
            halo.append((s, layer))
        if k == 'text-shadow' and v != 'none':
            halo.append((s, layer))
check('② no glow: no shadow layer blurred at offset 0 0, no text halo (the dock\'s own --dock-sh of the four themes included)', not halo, halo)
kf = [(s, b) for s, b in KF if 'dkRise' in s]
check('② the first rise (dkRise) moves only opacity and transform', kf and all(not re.search(r'shadow|filter|background|color', b) for s, b in kf), kf)
inf = [(s, v) for s, k, v in D if k.startswith('animation') and 'infinite' in v]
check('② nothing endless', not inf, inf)

# ③ glass material on the search sheet
sheet = ' '.join(b for s, b in R if s == '.ssheet')
check('③ glass: the search sheet takes --sheet-bg (the sheen), --sheet-sh (the 1px edge) and the blur',
      'background:var(--sheet-bg)' in sheet and 'box-shadow:var(--sheet-sh)' in sheet and 'backdrop-filter:var(--blur)' in sheet and '-webkit-backdrop-filter:var(--blur)' in sheet, sheet[:300])
ph = [b for s, b in R if '(max-width:760px)' in s.replace(' ', '') and '.ssheet' in s and 'box-shadow' in b]
check('③ glass: the phone rule adds the skirt after --sheet-sh (the edge reflection stays first)', ph and all('var(--sheet-sh)' in b for b in ph), ph)
gl = [(s, k, v) for s, k, v in D if 'glass' in s and k in ('background', 'background-image', 'backdrop-filter', '-webkit-backdrop-filter', 'box-shadow') and re.search(r'\bnone\b', v)]
check('③ glass: no dock / sheet rule takes the material away under a glass theme', not gl, gl)
for th in ('glass-dark', 'glass-light'):
    m = re.search(r'html\[data-theme="' + th + r'"\]\{(.*?)\n\}', SRC, re.S)
    body = m.group(1) if m else ''
    check(f'③ glass: {th} still carries the sheen (--tip-bg gradient → --sheet-bg) and the 1px inset edge in --sheet-sh',
          bool(re.search(r'--tip-bg:linear-gradient', body)) and '--sheet-bg:var(--tip-bg)' in body and re.search(r'--sheet-sh:inset 0 1px 0', body), body[:120])

# ④ amber · status
amb = [(s, k, v) for s, k, v in D if AMBER.search(v) and s != '.dk-l1 .st']
check('④ amber only on the ★ (켜짐, = the ★관심 tab\'s ★)', not amb, amb)
st = [v for s, k, v in D if s == '.dk-l1 .st' and k == 'color']
check('④ the ★ uses --acc (켜짐)', st == ['var(--acc)'], st)
lit = [(s, k, v) for s, k, v in D if k in ('color', 'background', 'background-color', 'border-color', 'fill', 'stroke') and re.search(r'#[0-9a-f]{3,8}\b|rgba?\(', v, re.I)]
check('④ no hard-coded colour in the dock / sheet (role tokens only)', not lit, lit)

# ⑤ type
bad = [(s, v) for s, k, v in D if k in ('font-size', 'font') and re.search(r'\d(px|pt|rem|em)\b', novar(v).split('/')[0])]
check('⑤ every font size is a --fs-* token', not bad, bad)
fs = sorted(set(re.findall(r'--fs-[\w]+', ' '.join(v for s, k, v in D if k in ('font-size', 'font')))))
check(f'⑤ only the seven steps {fs}', set(fs) <= {'--fs-xs', '--fs-sm', '--fs-md', '--fs-lg', '--fs-xl', '--fs-2xl', '--fs-num'} and fs, fs)
check('⑤ no tracking on the 16px value line (§3: −0.01em starts at 20px)', not any(k == 'letter-spacing' for s, k, v in D), [(s, v) for s, k, v in D if k == 'letter-spacing'])

# ⑥ space
SPACE = ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'margin', 'margin-left', 'margin-right',
         'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap', 'left', 'right', 'top', 'bottom', 'inset')
OK_POS = {('.dk-dots', 'bottom', '-3px')}
bad = []
for s, k, v in D:
    if k not in SPACE or (s, k, v) in OK_POS:
        continue
    vv = re.sub(r'env\([^)]*\)', 'E', novar(v))
    vv = vv.replace('calc((T - 16px) / 2)', 'T')                 # the sheet box's 🔍, centred in --h-row
    vv = vv.replace('+ 72px +', '+ T +') if 'footer' in s else vv  # the dock's room (8 + 56 + 8), a named shape value
    if any(float(n) not in (0, 1, -1) for n in re.findall(r'(-?\d*\.?\d+)px', vv)):
        bad.append((s, k, v))
check('⑥ padding / margin / gap / inset on the --space-* scale (literal only 0 or ±1px; the dots\' −3px optical offset)', not bad, bad)
foot = [v for s, k, v in D if 'footer' in s and k == 'padding-bottom']
check('⑥ the footer keeps the dock\'s room: --space-7 + 72px + the safe area', foot == ['calc(var(--space-7) + 72px + env(safe-area-inset-bottom))'], foot)

# ⑦ corners
bad = []
for s, k, v in D:
    if 'radius' not in k:
        continue
    vv = novar(v).replace('calc(T - T)', 'T')
    if re.search(r'\d(px|em|%)', vv) or not re.fullmatch(r'((T|0)\s*)+', vv.strip()):
        bad.append((s, v))
check('⑦ corners from tokens (--r-* · --dock-r · --sheet-r; a cell = --dock-r − --space-3)', not bad, bad)
nested = [v for s, k, v in D if s in ('.dk-pages', '.dk-c') and k == 'border-radius']
check('⑦ cells and the swipe area: the dock\'s corner minus its 6px padding (one centre)', nested == ['calc(var(--dock-r) - var(--space-3))'] * 2, nested)
dr = dict((('paper' if 'paper' in s else 'glass' if 'glass' in s else 'base'), v) for s, v in TOKS.get('--dock-r', []))
check(f'⑦ --dock-r per theme = the key\'s corner + 6 (기본 18 · 글라스 28) · 신문 4 {dr}', dr.get('base') == '18px' and dr.get('glass') == '28px' and dr.get('paper') == '4px', dr)

# ⑧ heights and literal sizes
SHAPES = {
    ('.dock', 'height', '56px'), ('.dock.keyonly', 'width', '56px'),
    ('.dk-l1', 'line-height', '14px'), ('.dk-v', 'height', '20px'), ('.dk-v', 'font', '700 var(--fs-xl)/20px var(--font-head)'),
    ('.dk-n', 'line-height', '13px'), ('.dk-bar', 'height', '6px'), ('.dk-v svg', 'width', '44px'), ('.dk-v svg', 'height', '18px'), ('.dk-v svg', 'min-width', '24px'),
    ('.dk-dots i', 'width', '4px'), ('.dk-dots i', 'height', '4px'), ('.dk-dots i.on', 'width', '12px'),
    ('.dk-k svg', 'width', '18px'), ('.dk-k svg', 'height', '18px'), ('.ss-x svg', 'width', '16px'), ('.ss-x svg', 'height', '16px'),
    ('.ssheet', 'height', '78svh'), ('.ssheet .grab', 'width', '38px'), ('.ssheet .grab', 'height', '4px'),
    ('.ss-list .sw', 'width', '10px'), ('.ss-list .sw', 'height', '10px'),
    ('.ss-list > button', 'grid-template-columns', '10px minmax(0,1fr) auto auto'),
}
SIZE = ('width', 'height', 'min-height', 'max-height', 'min-width', 'max-width', 'line-height', 'font', 'grid-template-columns', 'flex-basis')
bad = []
for s, k, v in D:
    if k not in SIZE or (s, k, v) in SHAPES or (k in ('width', 'height') and v == '1px'):   # a 1px rule is a line, not a size
        continue
    if re.search(r'\d+(px|svh|vh|em|rem)\b', novar(v)):
        bad.append((s, k, v))
check(f'⑧ no literal size but the {len(SHAPES)} named shape values (dock.md)', not bad, bad)
want = {('.dk-k', 'width'): 'var(--h-row)', ('.dk-k', 'height'): 'var(--h-row)', ('.ss-x', 'width'): 'var(--h-row)', ('.ss-x', 'height'): 'var(--h-row)',
        ('.ss-top .search input', 'height'): 'var(--h-row)', ('.ss-list > button', 'min-height'): 'var(--h-row)'}
got = {key: next((v for s, k, v in D if (s, k) == key), None) for key in want}
check('⑧ the 🔍 key, the ×, the sheet\'s box and its rows are --h-row (44 on phones)', got == want, got)
sink = [s for s, k, v in D if k == 'transform' and v == 'translateY(1px)']
check('⑧ the 🔍 key and the × sink 1px when pressed; cells and rows only darken', any(s.startswith('.dk-k:') for s in sink) and any(s.startswith('.ss-x:') for s in sink)
      and not any(re.search(r'\.dk-c|\.ss-list', s) for s in sink), sink)
press = [s for s, k, v in D if k == 'filter' and v == 'var(--press-f)']
check('⑧ every press darkens with the theme\'s --press-f (cells · 🔍 · × · rows)', all(any(n in s for s in press) for n in ('.dk-c:active', '.dk-k:', '.ss-x:', '.ss-list > button:active')), press)

# ⑨ motion
bez = [(s, v) for s, k, v in D if 'cubic-bezier(' in v or re.search(r'var\(--m-[\w-]+\)', v)]
check('⑨ no hand-written curve and none of the old --m-* motion tokens', not bez, bez)
lit = []
for s, k, v in D:
    if k in ('transition', 'transition-duration', 'transition-delay', 'animation', 'animation-duration', 'animation-delay'):
        for d in re.findall(r'(?<![\w.-])(\d*\.?\d+)(ms|s)\b', novar(v)):
            if float(d[0]) != 0 and not (k == 'animation-delay' and v == '40ms'):
                lit.append((s, k, v)); break
check('⑨ no literal durations (springs --sp-*, press --c-*, 0s down; the first rise\'s 40 ms stagger only)', not lit, lit)
tr = [(s, v) for s, k, v in D if k == 'transition' and v != 'none']
odd = [(s, v) for s, v in tr if not all(re.search(r'var\(--sp-[\w-]+-dur\) var\(--sp-[\w-]+\)|var\(--c-fast\) var\(--c-out\)|^visibility 0s|var\(--s[hc]-(open|close)\)', l) for l in layers(v))]
check(f'⑨ every transition on a spring (or the press tokens): {len(tr)} rules', tr and not odd, odd)
dock_on = ' '.join(b for s, b in R if s == '.dock.on')
dock_off = ' '.join(b for s, b in R if s == '.dock')
check('⑨ the dock comes up with `open` + `fade`, leaves with `close`',
      'transform var(--sp-open-dur) var(--sp-open)' in dock_on and 'opacity var(--sp-fade-dur) var(--sp-fade)' in dock_on
      and 'transform var(--sp-close-dur) var(--sp-close)' in dock_off and 'opacity var(--sp-close-dur) var(--sp-close)' in dock_off)
check('⑨ 화려하게 rise only the session\'s first time (.dk-first), 40 ms apart', any('.dk-first .dk-c' in s and 'dkRise var(--sp-fade-dur) var(--sp-fade)' in b for s, b in R)
      and not any(re.search(r'\.dock\.on \.dk-c', s) for s, b in R))
check('⑨ data moves with `value` (the 등락 분포 bar), the highlight plate with `hl`, the page dots with `lead`',
      any(s == '.dk-bar i' and 'flex-grow var(--sp-value-dur) var(--sp-value)' in b for s, b in R)
      and any(s == '.ss-hl' and 'transform var(--sp-hl-dur) var(--sp-hl)' in b for s, b in R)
      and any(s == '.dk-dots i' and 'width var(--sp-lead-dur) var(--sp-lead)' in b for s, b in R))
hov = [s for s, b in R if ':hover' in s and '(hover:hover)and(pointer:fine)' not in s.replace(' ', '')]
check('⑨ hover only on a fine pointer', not hov, hov)
check('⑨ one reduce switch (html[data-motion]): no prefers-reduced-motion in the dock', not any('prefers-reduced-motion' in s for s, b in R))

# JS
a = SRC.index('/* ───────────────── 아래 막대 — the phone dock (docs/standards/dock.md: V2')
b = SRC.index('/* ───────────────── boot ─────────────────')
JS = re.sub(r'(?m)^\s*//.*$', '', SRC[a:b])
svg = re.search(r'const DK_SVG = \{(.*?)\n\};', SRC[a:b], re.S)
icons = svg.group(1) if svg else ''
check('JS: the 🔍 and × icons are drawn 1.75px, non-scaling (DK_SVG), no other stroke widths in the dock',
      icons.count('stroke-width="1.75"') == 2 and icons.count('non-scaling-stroke') >= 3 and 'stroke-width="2"' not in JS and "stroke-width', '2'" not in JS, icons[:200])
check("JS: the sheet's × is the SVG (no text '×') and its 🔍 is DK_SVG.search", "text: '×'" not in JS and 'x.innerHTML = DK_SVG.close' in JS and 'lab.innerHTML = DK_SVG.search' in JS and 'DK.key.innerHTML = DK_SVG.search' in JS)
check('JS: cell numbers through KH.ui.swap / KH.ui.roll with the P4 rule (first draw · same value · 줄이기 · hidden · another thing → at once)',
      'uiSwap(el, text, was, dir)' in JS and 'uiRoll(el, text, dir)' in JS and "if (!was || DK.quiet || !DK.shown || reduced() || document.hidden)" in JS
      and JS.count('dkText(') >= 12 and 'dataset.id' in JS)
check('JS: the dock comes up with a quiet fill (what changed while away is not played back)', 'dkFill(true); dkData();' in JS)
check("JS: ← → flip pages with KH.spring 'lead' (snapping off while it moves, a held key at once); no smooth scrollTo",
      "name: 'lead'" in JS and "P.classList.add('dk-flip')" in JS and 'dkGoPage(i + 1, true, e.repeat)' in JS and "behavior: reduced() ? 'auto' : 'smooth' });\n  if (focus)" not in JS
      and not re.search(r"DK\.pages\.scrollTo\(\{[^}]*smooth", JS))
check('JS: the search sheet drags down with KH.ui.sheetDrag; one hl plate moves on ↑ ↓ (a held key at once)',
      'uiSheetDrag(SS.el' in JS and 'ssMark(e.repeat)' in JS and 'ssMark(true)' in JS and "class: 'ss-hl'" in JS)
check('JS: 화려하게 rise once per session (sessionStorage), never on every show', "sessionStorage.setItem('khm.dkRisen', '1')" in JS and "classList.remove('dk-first')" in JS)
jsl = re.findall(r"cubic-bezier|easing:\s*'ease|duration:\s*\d+|\b\d+ms (?:linear|ease)", JS)
check('JS: no literal easings or durations', not jsl, jsl)

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    ok = '.ss-hl{' in page and '.dock.on.dk-first .dk-c' in page and 'DK_SVG' in page and 'dkRise var(--m-2)' not in page
    check(f'build: {f} carries the dock on the design standard', ok)

print(f'\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks passed')
sys.exit(1 if FAILS else 0)
