#!/usr/bin/env python3
"""Design-standard audit of src/extras (docs/standards/design.md, AGENTS §3-31 — the extras step of design.md §11).

  python3 qa/extras/audit_css.py            (no browser, no server; exit 1 on any failure)

CSS (src/extras/extras.css):
  ① no gradient paint — linear / radial / conic gradients only inside mask-image (content masks: the ticker's edges, the number drum §6-2)
  ② no glow — no filter: drop-shadow(); no box- / text-shadow layer that is an even halo (blur > 0 at offset 0 0) or a blurred amber /
     status colour; no @keyframes that animate a shadow
  ③ no amber for status — rules for live / failed / session states (장중 dot, 갱신 실패, 동시호가 outline, countdown, async ! …) use
     --live / --fail-dot (a var(--live, var(--acc)) fallback is fine) and no --xe-* module token is an amber status colour
  ④ type on the scale — font-size / font use --fs-* (em / % allowed); the replay watermark (.rp-big-t) is the one exception
  ⑤ space on the scale — padding / margin / gap literal px only 0 or 1px (the 1px-rule correction)
  ⑥ corners — border-radius from tokens (var / calc / max of tokens), no bare px
  ⑦ motion — no bezier past 1 (bouncy), no literal durations in transition / animation (springs --sp-*, press 0s / --c-fast), endless
     animations only the ticker loop and the sun's slow rays
JS (src/extras/extras.js): no bouncy bezier, no 'ease-*' keyword easings, no literal WAAPI durations, no '.3s'-style inline transitions.
Build: web/index.html and dist/index.html carry this CSS (no leftover xcGlow / sbGlow / drop-shadow from the old extras).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (ROOT / 'src/extras/extras.css').read_text(encoding='utf-8')
JS = (ROOT / 'src/extras/extras.js').read_text(encoding='utf-8')
FAILS, PASSES = [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'))


def strip_comments(s):
    return re.sub(r'/\*.*?\*/', '', s, flags=re.S)


css = strip_comments(CSS)


def rules(text):
    """(selector, declarations) for every style rule, at-rules flattened (the @media prelude is kept with the selector)"""
    out, stack, buf, i = [], [], '', 0
    while i < len(text):
        c = text[i]
        if c == '{':
            stack.append(buf.strip()); buf = ''
        elif c == '}':
            sel = stack.pop() if stack else ''
            if buf.strip():
                out.append((' '.join(stack + [sel]).strip(), buf.strip()))
            buf = ''
        else:
            buf += c
        i += 1
    return out


def decls(body):
    """property → value pairs (values may hold ';' only inside quotes, not used in this file)"""
    res = []
    for part in re.split(r';(?![^(]*\))', body):
        if ':' in part:
            k, v = part.split(':', 1)
            res.append((k.strip().lower(), v.strip()))
    return res


def drop_var_fallbacks(v, names):
    """remove var(--name, fallback) for the given status tokens, so their fallback (e.g. var(--acc)) is not read as a use of amber"""
    out, i = '', 0
    while i < len(v):
        m = re.match(r'var\(\s*(--[\w-]+)', v[i:])
        if m and m.group(1) in names:
            depth, j = 0, i
            while j < len(v):
                if v[j] == '(':
                    depth += 1
                elif v[j] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out += 'STATUS'; i = j + 1; continue
        out += v[i]; i += 1
    return out


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


AMBER = re.compile(r'--acc\b|--acc-fill|--acc-line|--amber|#ffb547|255\s*,\s*181\s*,\s*71|--xe-auc|--xe-cd|--xe-sunglow|--xe-moonglow', re.I)
STATUS_TOK = {'--live', '--fail-dot'}
R = rules(css)
D = [(sel, k, v) for sel, body in R for k, v in decls(body)]

# ① gradients only as content masks
bad = [(s, k) for s, k, v in D if re.search(r'gradient\(', v) and k not in ('mask-image', '-webkit-mask-image', 'mask', '-webkit-mask')]
check('① no gradient paint (gradients only in mask-image: ticker edges, number drum)', not bad, bad)
masks = sorted({s for s, k, v in D if re.search(r'gradient\(', v)})
print('   content masks:', masks)

# ② glow
bad = [(s, v) for s, k, v in D if 'drop-shadow(' in v]
check('② no filter: drop-shadow()', not bad, bad)
halo = []
for s, k, v in D:
    if k not in ('box-shadow', 'text-shadow'):
        continue
    for layer in split_layers(v):
        if layer.startswith('var(') and layer.count('(') == layer.count(')') and re.fullmatch(r'var\([^()]*(\([^()]*\))?[^()]*\)', layer):
            continue                                   # a role token (the template's shadow / skirt)
        nums = re.findall(r'(-?\d*\.?\d+)px', re.sub(r'var\([^)]*\)', '', layer))
        if layer.startswith('inset'):
            nums = nums
        vals = [float(x) for x in nums]
        if len(vals) >= 3 and vals[2] > 0:
            even = abs(vals[0]) < 1e-9 and abs(vals[1]) < 1e-9
            coloured = bool(AMBER.search(layer) or re.search(r'--live|--fail', layer))
            if even or coloured:
                halo.append((s, layer))
check('② no glow shadows (no blurred halo at offset 0 0, no blurred amber / status colour)', not halo, halo)
kf = re.findall(r'@keyframes\s+([\w-]+)\s*\{(.*?)\}\s*\}', css, flags=re.S)
bad = [n for n, body in kf if re.search(r'box-shadow|text-shadow|filter', body) or re.search(r'glow|pulse', n, re.I)]
check('② no @keyframes that animate a shadow / filter (no glow or pulse)', not bad, bad)

# ③ status colours
STATUS_SEL = re.compile(r'data-st="open"|xs-stale|xs-warn|xc-cd|xc-auc|xc-glo|sb-live|sb-ring|\[data-st="fail"\]|\[data-st="arm"\]|xk-arm')
bad = []
for s, k, v in D:
    if not STATUS_SEL.search(s):
        continue
    if k in ('background', 'background-color', 'color', 'border-color', 'box-shadow', 'outline-color', 'fill', 'stroke'):
        if AMBER.search(drop_var_fallbacks(v, STATUS_TOK)):
            bad.append((s, k, v))
check('③ status states use --live / --fail-dot, not amber (장중 · 갱신 실패 · 동시호가 · countdown · ! · armed reset)', not bad, bad)
uses = sorted({s for s, k, v in D if re.search(r'var\(--live|var\(--fail-dot', v)})
check('③ extras names --live / --fail-dot where it shows those states', any('xwc' in u for u in uses) and any('xc-' in u for u in uses) and any('xs-' in u for u in uses), uses)
tokdefs = re.findall(r'(--xe-[\w-]+)\s*:\s*([^;]+)', css)
bad = [(n, v) for n, v in tokdefs if re.search(r'auc|cd|glow|live|fail', n)]
check('③ no amber status / glow module tokens (--xe-auc* · --xe-cd · --xe-*glow gone)', not bad, bad)

# ④ type scale
bad = []
for s, k, v in D:
    if k == 'font-size' or k == 'font':
        vv = re.sub(r'var\([^)]*\)', 'T', v)
        if k == 'font':
            m = re.search(r'(\S+)\s*/', vv) or re.search(r'\s(\S+)\s+\S+$', vv)
            size = m.group(1) if m else vv
        else:
            size = vv
        if re.search(r'\d(px|pt|rem)\b', size) and '.rp-big-t' not in s and 'clamp(T' not in size:
            bad.append((s, v))
check('④ font sizes on the --fs-* scale (exception: the replay watermark .rp-big-t)', not bad, bad)
small = [(s, v) for s, k, v in D if k == 'font-size' and re.search(r'\b(\d+(\.\d+)?)px', v) and float(re.search(r'(\d+(\.\d+)?)px', v).group(1)) < 11 and 'var(' not in v]
check('④ nothing under 11px', not small, small)

# ⑤ space
bad = []
for s, k, v in D:
    if k in ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'margin', 'margin-left', 'margin-right',
             'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap'):
        if 'slider-thumb' in s:
            continue                                   # the native slider's thumb centring: (track − thumb) / 2, geometry not spacing
        vv = re.sub(r'var\([^)]*\)', 'T', v)
        vv = re.sub(r'env\([^)]*\)', 'E', vv)
        for n in re.findall(r'(-?\d*\.?\d+)px', vv):
            if float(n) not in (0, 1, -1):
                bad.append((s, k, v)); break
check('⑤ padding / margin / gap on the --space-* scale (literal only 0 or the 1px-rule correction)', not bad, bad)

# ⑥ corners
bad = []
for s, k, v in D:
    if k.startswith('border') and 'radius' in k:
        vv = re.sub(r'var\((--[\w-]+)(,[^)]*)?\)', 'T', v)
        if re.fullmatch(r'\s*(-?\d*\.?\d+px\s*)+', vv) and vv.strip() not in ('0', '0px'):
            bad.append((s, v))
check('⑥ corners from tokens (no bare px radius)', not bad, bad)

# ⑦ motion
bez = [(s, v) for s, k, v in D for m in re.finditer(r'cubic-bezier\(([^)]*)\)', v) if any(abs(float(x)) > 1 for x in m.group(1).split(',')[1::2])]
check('⑦ no bouncy bezier (y past 0…1) in CSS', not bez, bez)
lit = []
for s, k, v in D:
    if k in ('transition', 'transition-duration', 'animation', 'animation-duration'):
        vv = re.sub(r'var\([^)]*\)', 'T', v)
        for d in re.findall(r'(?<![\w-])(\d*\.?\d+)(ms|s)\b', vv):
            if float(d[0]) == 0:
                continue
            if ('xs-run' in v) or ('sbSpin' in v and d == ('28', 's')):
                continue
            lit.append((s, v)); break
check('⑦ no literal durations in transitions / animations (springs, press 0s; the ticker loop and the sun rays are time, not easing)', not lit, lit)
inf = [(s, v) for s, k, v in D if k == 'animation' and 'infinite' in v and not ('xs-run' in v or 'sbSpin' in v)]
check('⑦ endless animations only the ticker loop and the sun\'s slow rays (motion-brief §3)', not inf, inf)
hov = [s for s, body in R if ':hover' in s and '(hover:hover) and (pointer:fine)' not in s.replace(' ', '').replace('(hover:hover)and(pointer:fine)', '(hover:hover) and (pointer:fine)')]
hov = [s for s in hov if '(hover:hover)and(pointer:fine)' not in s.replace(' ', '')]
check('⑦ hover styles only inside (hover:hover) and (pointer:fine) (design.md §8)', not hov, hov)

# JS
js = re.sub(r'/\*.*?\*/', '', JS, flags=re.S)
jsb = [m.group(0) for m in re.finditer(r'cubic-bezier\(([^)]*)\)', js) if any(abs(float(x)) > 1 for x in m.group(1).split(',')[1::2])]
check('JS: no bouncy bezier', not jsb, jsb)
jse = re.findall(r"easing:\s*'ease[\w-]*'", js) + re.findall(r"'transform \.\d+s[^']*'", js) + re.findall(r"\b\d*\.\d+s (?:linear|ease|cubic)", js)
check("JS: no 'ease-*' keyword easings or literal inline transitions", not jse, jse)
jsd = re.findall(r'duration:\s*\d+', js)
check('JS: no literal WAAPI durations (spMs(name) springs · SWAP of §6-4)', not jsd, jsd)
jsg = re.findall(r'drop-shadow|linear-gradient\((?!transparent)', js)
check('JS: no glow filter, no painted gradient strings', not jsg, jsg)

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    a = page.find('Extras: market strip, tools')
    seg = page[a:a + len(CSS) + 2000] if a >= 0 else ''
    ok = a >= 0 and 'xcGlow' not in page and 'sbGlow' not in page and 'drop-shadow(0 0 1px var(--xe-halo))' not in page and 'xs-warn' in page
    check(f'build: {f} carries the new extras CSS (no xcGlow / sbGlow / icon glow)', ok, a)

print(f'\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks passed')
sys.exit(1 if FAILS else 0)
