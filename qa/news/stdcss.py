"""Shared parts of the design-standard CSS audits for the news card (qa/news/audit_css.py · qa/disclosure/audit_css.py — design.md §11
step "뉴스 · 공시", ux/std-news). Parsing only (no browser): rules, declarations, var() stripping, shadow layers, the common checks."""
import re

AMBER = re.compile(r'--acc\b|--acc-fill|--acc-line|--acc-soft|--acc-bd|--amber|--chip-on|--chip-ring|--sw-on|--done-bg|#ffb547|255\s*,\s*181\s*,\s*71', re.I)
SPACE = ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'padding-inline', 'padding-block',
         'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap')
STEPS = {f'--fs-{x}' for x in ('xs', 'sm', 'md', 'lg', 'xl', '2xl', 'num')}


def strip_comments(s):
    return re.sub(r'/\*.*?\*/', '', s, flags=re.S)


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


class Audit:
    def __init__(self):
        self.fails, self.passes = [], []

    def check(self, name, ok, detail=''):
        (self.passes if ok else self.fails).append(name)
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:600]}'))

    def done(self):
        n = len(self.passes) + len(self.fails)
        print(f'\n{len(self.passes)}/{n} checks passed')
        return 1 if self.fails else 0


def parse(css_text):
    css = strip_comments(css_text)
    R = [(s, b) for s, b in rules(css) if not s.startswith('@keyframes')]
    D = [(s, k, v) for s, b in R for k, v in decls(b)]
    KF = re.findall(r'@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}', css)
    return css, R, D, KF


def common(A, tag, css, R, D, KF, *, height_ok, amber_ok, endless):
    """the checks every module of the card shares (design.md §2 · §3 · §4 · §5 · §6 · §8)"""
    # ① gradients — none at all in this card (no content mask, no hatch: news / filing rows are not data shapes)
    bad = [(s, k, v) for s, k, v in D if 'gradient(' in v]
    A.check(f'{tag} ① no gradient (the card paints none — no mask or hatch needed here)', not bad, bad)
    # ② glow
    bad = [(s, v) for s, k, v in D if 'drop-shadow(' in v or (k in ('backdrop-filter', '-webkit-backdrop-filter'))]
    A.check(f'{tag} ② no drop-shadow(), no backdrop-filter of its own (the glass blur is the template plates\')', not bad, bad)
    blur = [(s, b) for s, k, v in D if k == 'filter' for b in re.findall(r'blur\((\d*\.?\d+)px\)', v) if float(b) > 2]
    blur += [(n, b) for n, body in KF for b in re.findall(r'blur\((\d*\.?\d+)px\)', body) if float(b) > 2]
    A.check(f'{tag} ② blur only ≤ 2px (the §6-4 text swap · the fold\'s rows), never a halo', not blur, blur)
    halo = []
    for s, k, v in D:
        if k == 'text-shadow' and v.strip() != 'none':
            halo.append((s, v)); continue
        if k != 'box-shadow':
            continue
        for layer in split_layers(v):
            bare = novar(layer)
            nums = [float(x) for x in re.findall(r'(-?\d*\.?\d+)px', bare)]
            if len(nums) >= 3 and nums[2] > 0:
                even = abs(nums[0]) < 1e-9 and abs(nums[1]) < 1e-9
                coloured = bool(AMBER.search(layer) or re.search(r'--live|--fail|--up-text|--dn-text|--new-dot', layer))
                if even or coloured:
                    halo.append((s, layer))
    A.check(f'{tag} ② no glow shadow (no even halo, no blurred amber / status colour, no text-shadow)', not halo, halo)
    badkf = [n for n, body in KF if re.search(r'box-shadow|text-shadow|background|color\s*:', body) or re.search(r'glow|pulse|shim|ring', n, re.I)]
    A.check(f'{tag} ② keyframes animate no paint (opacity · 4px · ≤ 2px blur only; none named glow / pulse / ring)', not badkf, [n for n, _ in KF])
    inf = sorted({re.search(r'^([\w-]+)', v).group(1) for s, k, v in D if k == 'animation' and 'infinite' in v})
    A.check(f'{tag} ② endless animations only {endless or "none"} (the skeleton breath — opacity)', inf == endless, inf)
    # ③ amber only for its four meanings
    bad = [(s, k, v) for s, k, v in D if AMBER.search(v) and not amber_ok(s)]
    A.check(f'{tag} ③ amber only on selected / switched-on / focus rules', not bad, bad)
    # ④ type
    bad = []
    for s, k, v in D:
        if k in ('font-size', 'font'):
            vv = novar(v)
            if re.search(r'\d(px|pt|rem|em)\b', vv) or (k == 'font-size' and vv.strip() not in ('T', 'inherit')):
                bad.append((s, v))
    A.check(f'{tag} ④ every font size is var(--fs-*) (nothing under 11px)', not bad, bad)
    used = set(re.findall(r'var\((--fs-[\w-]+)', css))
    A.check(f'{tag} ④ only the seven steps (11 · 12 · 13 · 14 · 16 · 20 · 26)', used <= STEPS and used, sorted(used))
    lh = [(s, v) for s, k, v in D if k == 'line-height' and not (v.startswith('var(--lh-') or v in ('18px', '1', 'normal'))]
    A.check(f'{tag} ④ line heights from --lh-* (18px only = the badge recipe\'s height)', not lh, lh)
    # ⑤ space
    bad = []
    for s, k, v in D:
        if k in SPACE:
            vv = re.sub(r'env\([^)]*\)', 'E', novar(v))
            if any(float(n) not in (0, 1, -1) for n in re.findall(r'(-?\d*\.?\d+)px', vv)):
                bad.append((s, k, v))
    A.check(f'{tag} ⑤ padding / margin / gap on the --space-* scale (literal only 0 or ±1px)', not bad, bad)
    # ⑥ corners
    bad = []
    for s, k, v in D:
        if 'radius' in k:
            vv = re.sub(r'(?<![\d.])0px', '0', novar(v)).strip()
            if re.search(r'\d(px|em|rem)\b', vv) or (re.search(r'\d+%', vv) and vv != '50%'):
                bad.append((s, v))
    A.check(f'{tag} ⑥ corners from tokens (--r-* · --r-chip · --r-key; 50% for dots, 0 for tab rows)', not bad, bad)
    # ⑦ heights
    bad = [(s, k, v) for s, k, v in D if k in ('height', 'min-height', 'max-height') and re.search(r'\d+px', novar(v)) and not height_ok(s, k, v)]
    A.check(f'{tag} ⑦ heights from --h-* / --nw-rh (literal px only the listed sizes: badge 18 · icons · skeleton bar · 44 hit area)', not bad, bad)
    # ⑧ motion
    anybez = [(s, v) for s, k, v in D if 'cubic-bezier(' in v or re.search(r'\bease(-in|-out|-in-out)?\b', v)]
    A.check(f'{tag} ⑧ no hand-written curves (springs --sp-*; press --c-fast / --c-out only)', not anybez, anybez)
    lit = []
    for s, k, v in D:
        if k in ('transition', 'transition-duration', 'transition-delay', 'animation', 'animation-duration', 'animation-delay'):
            for d in re.findall(r'(?<![\w-])(\d*\.?\d+)(ms|s)\b', novar(v)):
                if float(d[0]) != 0:
                    lit.append((s, v)); break
    A.check(f'{tag} ⑧ no literal durations in transitions / animations (springs, press 0s, the §6-4 lengths as tokens)', not lit, lit)
    old = sorted({m for s, k, v in D for m in re.findall(r'--c-(?:base|slow|switch|in\b|dwell)|--m-[\w-]+', v)})
    A.check(f'{tag} ⑧ none of the old curve / length tokens (--c-base · --c-slow · --c-in · --c-switch · --m-*)', not old, old)
    press = [(s, v) for s, k, v in D if k == 'transition-duration' and v != '0s' and re.search(r':active|is-press', s)]
    press += [s for s, k, v in D if k == 'transform' and v == 'translateY(1px)' and not any(s2 == s and k2 == 'transition-duration' and v2 == '0s' for s2, k2, v2 in D)]
    A.check(f'{tag} ⑧ press goes down at once (transition-duration 0s), comes back on --c-fast', not press, press)
    hov = [s for s, _ in R if ':hover' in s and '(hover:hover)and(pointer:fine)' not in s.replace(' ', '')]
    A.check(f'{tag} ⑧ hover only inside (hover:hover) and (pointer:fine) (design.md §8 — no leftover hover on Android)', not hov, hov)
    A.check(f'{tag} ⑧ one reduce switch (html[data-motion]): no prefers-reduced-motion, no (hover:none) resets', 'prefers-reduced-motion' not in css and '(hover:none)' not in css.replace(' ', ''))
    # ⑨ glass material: this file never paints a theme's material
    theme = [s for s, _ in R if 'data-theme' in s]
    A.check(f'{tag} ⑨ no theme-specific rule (the four themes differ only through the template\'s role tokens)', not theme, theme)


def glass_template(A, tpl):
    """⑨ the template still carries the glass material this card sits on (사용자 2026-11-16 01:32 "글라스가 플랫해지면 글라스가 아닌데")"""
    for th in ('glass-dark', 'glass-light'):
        m = re.search(r'html\[data-theme="%s"\]\{(.*?)\n\}' % th, tpl, re.S)
        body = m.group(1) if m else ''
        # ④ 리퀴드 글라스 (AGENTS §3-38): the radial --gl-sheen over each fill, the edges in the shadows, blur 14px
        sheen = re.search(r'--gl-sheen:radial-gradient\(', body) and re.search(r'--tip-bg:var\(--gl-sheen\),', body) and re.search(r'--bar-bg:var\(--gl-sheen\),', body)
        edge = re.search(r'--card-sh:inset 0 1px 0 (#fff|rgba\(255,255,255,\.\d+\))', body) and re.search(r'--tip-sh:inset 0 1px 0', body)
        blur = re.search(r'--blur:blur\(14px\)', body)
        A.check(f'⑨ template {th}: sheen (④ --gl-sheen over --tip-bg · --bar-bg), 1px edge reflection (--card-sh · --tip-sh inset 0 1px 0), blur 14px',
                bool(m) and bool(sheen) and bool(edge) and bool(blur))
    A.check('⑨ template: the big glass plates (tooltip · header · cards) keep their edge ring ::after, the tooltip / sheet keep --tip-bg · --sheet-bg and the blur',
            bool(re.search(r'html\[data-theme\^="glass"\] :is\([^)]*\.tip\b[^)]*header\.top[^)]*\.card\b[^)]*\)::after', tpl)) and re.search(r'\.tip\{[^}]*background:var\(--tip-bg\)[^}]*backdrop-filter:var\(--blur\)', tpl)
            and re.search(r'\.card\{background:var\(--card-bg\)[^}]*box-shadow:var\(--card-sh\)', tpl))
