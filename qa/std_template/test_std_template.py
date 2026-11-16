#!/usr/bin/env python3
"""The template on the design standard (roadmap 6, step template — ux/std-template; design.md §2 · §3 · §4 · §6, AGENTS §3-31 · §3-36).

  python3 qa/std_template/test_std_template.py [audit] [page] [cap] [limits] [glass]       (no argument = all five)

audit  static, src/template.html's <style>: the scale (design.md §3 · §4 — every font size on --fs-*, line heights on --lh-*, padding /
       margin / gap on --space-*, corners on --r-*, heights on --h-*; what is left is listed below with its reason: the map box
       (design.md §11 템플릿), the dock (dock.md), icon · mark · data boxes, hit areas, negative margins, and the controls the next
       step ("컨트롤 움직임 통일", AGENTS §3-38) will size) — and hover only on a fine pointer (design.md §8); a gradient only where it
       draws data or a shape (the legend scale, no-data / no-NXT hatches, the folded 공시 corner, the tab row's overflow mask) — or the
       glass material (design.md §2 예외, ④ 리퀴드 글라스, AGENTS §3-38): the radial sheen and the 135° ring only as glass-theme tokens
       (--gl-sheen* · --gl-ring*), the ring rules paint var(--gl-ring*) and use a gradient only as their mask; no glow (no zero-offset
       blurred box-shadow, no drop-shadow(), text halos only behind map labels / the crumbs over the index line); the inner thickness
       light (an inset, blurred, white shadow) only in the glass tokens; status rules (live · err · fail · stale) never read the amber;
       --live and --fail-dot are defined for every theme and none of them is amber; the glass tokens carry the drafts/glass.html ④
       values (fills, blur 14px · saturate 1.8 · 밝게 brightness 1.06, plates, fallback fills).
page   the live build (web/) behind qa/float/mock_float.py on STD_QA_PORT (default 9020; 9020–9029 only): four themes × 390 · 768 · 1280 ·
       1440 — map top (390 247 · 768 250 · 1280+ 207), no element wider than the screen, console errors 0; --live / --fail-dot computed
       per theme (≥ 30° of hue from the amber and the new-filing blue, ≥ 3:1 on the page); the live dot and the 실시간 badge in --live;
       the error "!" in --fail-dot; a tick flash is a flat wash + the number's pill (no ring, no blur).
cap    시총순 지도 (AGENTS §3-36): the 묶음 option only on 코스피 · 코스닥 · 전체 (표시 설정 sheet < 1280, 화면 popover ≥ 1280), saved as
       khm.groupBy; in 시총순 no sector / industry node (DOM and KH.layout()), the first tiles in reading order have the biggest caps
       (and keep the cap order when 크기 = 거래대금), labels inside their tiles, search highlight · tooltip · quick view work, no
       overflow, the image save draws (extras), back to 섹터별; console errors 0.
limits 상한가 · 하한가 in the phone dock's 등락 분포 cell (사용자 2026-11-16 00:54): close.json served with known flags (and /api/breadth
       with the same rows) → the dock, the 등락 분포 card and the 시장 요약 카드 (KHSummary.model().br — K · Q · both for the tab) show the
       same counts = the flags; the aria-label carries them; the top line fits (no overlap, the name whole) at 360 · 390 with two-digit
       counts; the cell (44) · dock (56) · bottom gap (8) · top line (14) are the same as without counts; an older close.json (no flags)
       and a replay hide the counts in the dock and the card (no 0).
glass  ④ on the page (글라스 어둡게 · 밝게 × 1440 · 390, header stuck over the map): blur 14px · saturate 1.8 (밝게 + brightness 1.06) on
       the stuck header and the tooltip, none on cards · the dock; the 1.25px ring (135°) on the header, tooltip, cards, dock, popovers;
       the tab tray = the number plate, the selected tab near-opaque; 등락 numbers on the tooltip / quick view on the plate with no
       layout shift (the same boxes as with the plate off); at most two blurred panels at once (stuck header + tooltip); the fallback —
       유리 흐림 끄기 (data-blur="off") and prefers-reduced-transparency: reduce (CDP emulation) — the same shapes with opaque fills, the
       sheen and the ring kept, no blur. The contrast of the numbers over the worst tile: qa/std_template/test_glass_contrast.py.
Exit 1 on a fail. Ports are stopped with fuser -k.
"""
import colorsys
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('STD_QA_PORT', 9020))
assert 9020 <= PORT <= 9029 or 9050 <= PORT <= 9069 or 9080 <= PORT <= 9089, 'ports 9020–9029 (or 9050–9069: ux/std-wrapup · ux/std-dock, 9080–9089: ux/glass-liquid)'
URL = f'http://127.0.0.1:{PORT}/'
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
THEMES = ['base', 'paper', 'glass-dark', 'glass-light']
FAILS, PASSES, ERRS = [], [], []


def check(name, ok, detail=''):
    (PASSES if ok else FAILS).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  — {str(detail)[:400]}'))


# ───────────────────────── audit (static) ─────────────────────────
def css_rules(css):
    """(selector, body) for every rule, @media / @supports blocks flattened; comments dropped"""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out, stack, buf = [], [], ''
    i = 0
    while i < len(css):
        ch = css[i]
        if ch == '{':
            stack.append(buf.strip()); buf = ''
        elif ch == '}':
            sel = stack.pop() if stack else ''
            if buf.strip() and not sel.startswith('@'):
                out.append((sel, buf.strip()))
            buf = ''
        else:
            buf += ch
        i += 1
    return out


GRAD_OK = [   # selector (substring) → why a gradient is fine there
    ('.tile.nod', 'no-data hatch'), ('.tile.nonx', 'no-NXT hatch'), ('.legend .nxsw', 'legend hatch swatch'), ('.legend .nodsw', 'legend hatch swatch'),
    ('.tile .dm', 'the folded 공시 corner (a hard-stop diagonal = a shape)'), ('.dmsw::after', 'the corner swatch'),
    ('.tabs-sc.more-r', 'the tab row overflow mask (a mask, not paint)'),
    ('.rc', 'the number drum\'s 14 % fade (a mask, not paint — design.md §6-2 P10)'),
    ('html[data-theme="glass-', 'glass material ④: the sheen / ring tokens (--gl-sheen* radial, --gl-ring* 135°) — glass themes only'),
]
# the ring rules (④): they paint var(--gl-ring*) and use a gradient only as the mask that cuts the 1.25px ring out of the box
RING_SEL = re.compile(r'^html\[data-theme\^="glass"\] .*::after$')
HALO_OK = ['.tile .lab', '.stagebar.ix-bg .crumbs']   # dark text halos: legibility over data (tile colours · the index line)
STATUS_SEL = re.compile(r'\.status\.(live|err)|\.err\b|stale|\[data-st="fail"\]|\.kwn|\.fail')
AMBER = re.compile(r'var\(--(acc|acc-fill|acc-line|acc-soft|acc-bd|amber|amber-soft)\)|#ffb547|255,\s*181,\s*71')


# ── the scale (design.md §3 · §4), ux/std-wrapup 2026-11-16: whatever is not on a token is listed here with its reason ──
MAPBOX = 'map box — sets where the map starts / how big it is (design.md §11 템플릿 "척도 밖으로 둔 것"; qa/summary compares the map box with main)'
NEXT = '남은 것 — a control size the next step ("컨트롤 움직임 통일", AGENTS §3-38) settles with the close key · chips · keys of every module'
DOCK = 'the phone dock / search sheet shape (dock.md, qa/dock/audit_css.py)'
FONT_OK = {('.tile .pc', '.74em'): 'map tile label — sized to the tile (design.md §3 예외)', ('.tile .px', '.52em'): 'map tile label (§3 예외)',
           ('.tile .mc', '.44em'): 'map tile label (§3 예외)', ('.tabs .st', '.9em'): MAPBOX + ' — the % line under a market tab sets the tab row',
           ('.dk-v', '700 var(--fs-xl)/20px var(--font-head)'): DOCK + ' — the 20px value line'}
LH_OK = {'.tabs .tn': MAPBOX, '.tabs .tp': MAPBOX, '@media (max-width: 760px) .tabs .tn': MAPBOX, '.ixl .ixv,.ixl .ixt': MAPBOX + ' (the index line, B)',
         '.ixl .ixtip': MAPBOX + ' (the index line bubble)', '.tile .lab': 'map tile labels (§3 예외)', '.tile .lim': 'map tile 상한가 mark',
         '.legend .rauto': 'the badge recipe height 18 (design.md §5)', '.nxtag': MAPBOX + ' (header badge)', '.limtag': MAPBOX + ' (header badge)',
         '.rs': 'the number drum (KH.ui.roll)', '.dk-l1': DOCK, '.dk-n': DOCK, '.list th .thv': 'table header two-line label (data table)'}
SPACE_OK = {'.top': MAPBOX, '@media (max-width: 760px) .top': MAPBOX, '.tabs button': MAPBOX, '@media (max-width: 760px) .tabs button': MAPBOX,
            '.tools': MAPBOX, '.search input': MAPBOX + ' (the 35px icon slot)', '.seg': 'tray inset 3px (design.md §4 example: tray 12, gap 3 → 9)',
            '.seg button': MAPBOX + ' (segment cell 5px)', '@media (min-width:1280px) .seg button': MAPBOX,
            '@media (min-width:1280px) .seg[data-key="palette"] button': MAPBOX, '@media (min-width:1280px) and (max-width:1439px) .seg[data-key="topN"] button': MAPBOX,
            '.layout': MAPBOX, '.viewseg button': MAPBOX + ' (map header keys 3px)', '.crumbs button.c': MAPBOX, '@media (max-width: 760px) .crumbs .back': MAPBOX,
            '.legend': MAPBOX, '.legend .lg': MAPBOX, '@media (max-width: 760px) .legend': MAPBOX, '.side': MAPBOX + ' (side column top = the map)',
            '.card': 'card inner 14px = the summary · news cards (one inner width)', '.movers-tabs': 'tray inset 3px (§4)',
            '.tile .pc': 'map tile label pill (tick flash ④)', '.brand i': 'the logo mark', 'span.cdb.cdb > i': 'candle drawing (half-pixel centring)',
            '.bm-in': 'bottom edge: safe area + the sheet foot', '@media (max-width: 760px) .ctls': 'bottom edge: safe area + the sheet foot',
            '@media (max-width:760px) footer': DOCK + ' (the 72px end slot under the page)', '.bm-it': 'the check slot of a menu row (icon box 40)'}
RADIUS_OK = {'.brand i b': 'the logo mark', '.legend .limsw': 'legend mark', '@media (min-width:1280px) .ctl.dd > .seg': 'popover corner = tooltip + 2 (fix/popover, AGENTS §3-35)',
             '@media (min-width:1280px) .morep': 'popover corner = tooltip + 2', '@media (min-width:761px) and (max-width:1279px) .ctls': 'popover corner = tooltip + 2',
             '.wgpop': 'popover corner = tooltip + 2', '@media (max-width:760px) .wgpop': 'nested surface: inner = outer − gap (design.md §4)',
             '.sheet': 'nested surface: inner = outer − gap (§4)', 'html[data-theme^="glass"] header.top::before': 'glass header plate (themes.md §6-2, glass material — design.md §2 예외)',
             '@media (max-width:760px) html[data-theme^="glass"] header.top::before': 'glass header plate', 'html[data-theme^="glass"] header.top::after': 'glass header edge reflection',
             '@media (max-width:760px) html[data-theme^="glass"] header.top::after': 'glass header edge reflection',
             ':is(.thm .seg,.ctls .seg[data-key="palette"])': 'theme / palette swatches: a capped tray corner (glass 999 would be a pill)',
             ':is(.thm .seg,.ctls .seg[data-key="palette"])::before': 'the capped indicator inside it'}
HEIGHT_RE = re.compile(r'svg|::before|::after|\b(i|b)\b|\.dot|\.sw\b|\.cd[ib]|\.grad|\.bar\b|\.ck\b|\.kov|\.kck|\.kwn|\.kspn|\.pl\b|\.mbl|\.sep|\.tsep|\.grab|\.dmsw|\.limsw|\.dbar|\.breadth|\.sr\b|\.ttl|label\.row input|\.msg')
HEIGHT_DATA = {'.map': MAPBOX, '@media (max-width: 760px) .map,.tablewrap': MAPBOX, '.tablewrap': MAPBOX, '.hist': 'data: the 등락 분포 bars', '.spark svg': 'data: the sparkline',
               '.legend': MAPBOX, '.crumbs': MAPBOX, '.crumbs .ixl': MAPBOX, '.stagebar.ix-row > .ixl': MAPBOX, '.search input': MAPBOX + ' (검색 칸 34)',
               '.setbtn': MAPBOX + ' (the tools row: 34 = 검색 칸 · 세그먼트)', '.swbtn .swt': 'switch track 44 × 26 (controls.md §5-8)', '.sugg': 'list cap (scrolls)',
               '.sheet': 'sheet cap (scrolls)', '.world-missing': 'message box keeps the map area', '.dock': DOCK, '.dk-v': DOCK, '.dk-bar': DOCK + ' (the 등락 분포 bar 6px)',
               '.wgc': NEXT + ' (★관심 group chips, desktop 30)', '.wgm': NEXT, '@media (max-width:760px) .wgadd': NEXT + ' (phone ＋ 42)',
               '.wgpop input[type="text"]': NEXT + ' (group name field 38)', '.wgpop .acts button': NEXT + ' (popover keys 34)', '.map-empty .we button': NEXT + ' (40 at every width)',
               '@media (max-width:760px) .movers .more,.secs .more': NEXT + ' (phone 더보기 42)', '.wstar': NEXT + ' (☆ in the quick view, 30)',
               '.sheet .x': NEXT + ' (quick view × 30 — design.md §5: 32 / phone 44)', '.thm .seg button': NEXT + ' (theme swatches 34)', '.bm-it': NEXT + ' (price-basis menu rows 54)'}


def audit_scale(css):
    sys.path.insert(0, str(ROOT / 'qa/news'))
    from stdcss import parse, novar
    bare, R, D, _ = parse(css)
    D = [(sel, k, v) for sel, k, v in D if not k.startswith('--')]
    font = [(sel, v) for sel, k, v in D if (k == 'font-size' and novar(v).strip() not in ('T', 'inherit')) or (k == 'font' and re.search(r'\d(px|em)\b', novar(v)))]
    check('audit scale ④: font sizes on --fs-* (left: tile labels · tab % line · dock value line, with reasons)', all(FONT_OK.get((sel, v)) for sel, v in font), [x for x in font if not FONT_OK.get(x)])
    lh = [sel for sel, k, v in D if k == 'line-height' and not (v.startswith('var(--lh-') or v in ('1', 'normal', 'inherit'))]
    check('audit scale ④: line heights on --lh-* (left: map box · tile labels · badges · drum · dock, with reasons)', all(sel in LH_OK for sel in lh), [x for x in lh if x not in LH_OK])
    SP = ('padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom', 'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'gap', 'row-gap', 'column-gap')
    bad = []
    for sel, k, v in D:
        if k not in SP:
            continue
        nums = [float(n) for n in re.findall(r'(-?\d*\.?\d+)px', re.sub(r'env\([^)]*\)', 'E', novar(v)))]
        off = [n for n in nums if n not in (0, 1, -1)]
        if not off or all(n < 0 for n in off) or sel in SPACE_OK:      # negative margins: hit areas · optical corrections (design.md §11)
            continue
        bad.append((sel, k, v))
    check('audit scale ⑤: padding / margin / gap on --space-* (left: map box · tray insets · safe-area feet · negative margins, with reasons)', not bad, bad)
    bad = []
    for sel, k, v in D:
        if 'radius' not in k:
            continue
        vv = re.sub(r'(?<![\d.])0px', '0', novar(v)).strip()
        if (re.search(r'\d(px|em)\b', vv) or (re.search(r'\d+%', vv) and vv != '50%')) and sel not in RADIUS_OK:
            bad.append((sel, v))
    check('audit scale ⑥: corners on --r-* (left: popover = tooltip + 2 · nested surfaces · glass header plate · marks, with reasons)', not bad, bad)
    bad = []
    for sel, k, v in D:
        if k not in ('height', 'min-height', 'max-height') or not re.search(r'\d+px', novar(v)):
            continue
        if sel in HEIGHT_DATA or HEIGHT_RE.search(sel) or ('(pointer:coarse)' in sel and '44px' in v):
            continue
        bad.append((sel, k, v))
    check('audit scale ⑦: heights on --h-* (left: icon · mark · data boxes, hit areas, map box, dock, and the controls of the next step — with reasons)', not bad, bad)
    nxt = sorted({sel for sel in HEIGHT_DATA if HEIGHT_DATA[sel].startswith('남은 것') and any(s2 == sel for s2, k, v in D if k in ('height', 'min-height'))})
    print(f'      (남은 것, next step: {len(nxt)} control sizes — {", ".join(nxt)})')
    hov = [sel for sel, _ in R if ':hover' in sel and '(hover:hover)and(pointer:fine)' not in sel.replace(' ', '')]
    check('audit: hover only inside (hover:hover) and (pointer:fine) — design.md §8 (no (hover:none) resets)', not hov and '(hover:none)' not in bare.replace(' ', ''), hov)


def audit():
    src = (ROOT / 'src/template.html').read_text(encoding='utf-8')
    css = src[src.index('<style>') + 7:src.index('</style>')]
    audit_scale(css)
    rules = css_rules(css)
    rad = [sel[:80] for sel, body in rules if 'radial-gradient' in body and (not sel.startswith('html[data-theme="glass-') or any('radial-gradient' in v for k, v in re.findall(r'(--[\w-]+|[\w-]+)\s*:\s*([^;]+)', body) if not k.startswith('--gl-sheen')))]
    check('audit: radial-gradient only as the glass sheen token (--gl-sheen*, glass themes)', not rad, rad)
    bad, ring = [], []
    for sel, body in rules:
        if 'gradient(' not in body:
            continue
        if RING_SEL.match(sel):
            paint = re.search(r'background\s*:\s*([^;]+)', body)
            masks = re.findall(r'(?:-webkit-)?mask\s*:\s*([^;]+)', body)
            if (paint and 'gradient(' in paint.group(1)) or not masks or 'gradient(' in re.sub(r'(?:-webkit-)?mask\s*:[^;]+', '', re.sub(r'background\s*:[^;]+', '', body)):
                ring.append(sel[:80])
            continue
        if any(k in sel for k, _ in GRAD_OK):
            continue
        bad.append(sel[:80])
    check('audit: linear gradients only on the allow-list (data scale, hatches, 공시 corner, overflow · drum masks, glass tokens)', not bad, bad)
    check('audit: the glass ring rules paint var(--gl-ring*) and use a gradient only as the mask', not ring, ring)
    js_grad = [m.group(0)[:90] for m in re.finditer(r'[^\n]*gradient\([^\n]*', src[src.index('</style>'):]) if 'legend' not in m.group(0) and "class: 'grad'" not in m.group(0)]
    check('audit: the script draws no gradient but the legend colour scale', not js_grad, js_grad)
    glow = []
    for sel, body in rules:
        for prop, val in re.findall(r'(box-shadow|--[\w-]*sh[\w-]*|text-shadow|filter|--lab-sh[\w-]*)\s*:\s*([^;]+)', body):
            if 'drop-shadow(' in val:
                glow.append((sel[:60], prop, 'drop-shadow'))
            if prop == 'text-shadow' or prop.startswith('--lab-sh'):
                if any(k in sel for k in HALO_OK) or prop.startswith('--lab-sh') or val.strip() in ('none', 'var(--lab-sh)', 'var(--lab-sh-sm)'):
                    continue
                glow.append((sel[:60], prop, val[:60]))
                continue
            for part in re.split(r',(?![^(]*\))', val):
                m = re.match(r'\s*(inset\s+)?(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)px', part)
                if m and float(m.group(2)) == 0 and float(m.group(3)) == 0 and float(m.group(4)) > 0:
                    glow.append((sel[:60], prop, part.strip()[:60]))
    check('audit: no glow — no zero-offset blurred shadow, no drop-shadow()', not glow, glow)
    amb = [(sel[:70], body[:80]) for sel, body in rules if STATUS_SEL.search(sel) and AMBER.search(body) and not sel.startswith('.status.replay')]
    check('audit: status rules (live · err · fail · stale) never read the amber', not amb, amb)
    toks = {}
    for sel, body in rules:
        for k, v in re.findall(r'(--live|--fail-dot)\s*:\s*([^;]+)', body):
            toks.setdefault(k, []).append((sel, v.strip()))
    for k in ('--live', '--fail-dot'):
        vals = toks.get(k, [])
        check(f'audit: {k} defined, never amber ({len(vals)} definitions)', vals and not any(AMBER.search(v) for _, v in vals), vals)
    lv = {sel for sel, _ in toks.get('--live', [])}
    check('audit: --live has a value for 기본 · 신문 · 글라스 어둡게 · 글라스 밝게',
          ':root' in lv and any('paper' in x for x in lv) and any('glass-dark' in x for x in lv) and any('glass-light' in x for x in lv), lv)
    # the inner thickness light (④ — design.md §6-6 bans an inner glow; §2 예외 for the glass material): only in the glass theme tokens
    inner = []
    for sel, body in rules:
        for prop, val in re.findall(r'(box-shadow|--[\w-]*sh[\w-]*)\s*:\s*([^;]+)', body):
            for part in re.split(r',(?![^(]*\))', val):
                m = re.match(r'\s*inset\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)px', part)
                if m and float(m.group(3)) > 0 and re.search(r'#fff\b|rgba\(255,\s*255,\s*255', part) and not sel.startswith('html[data-theme="glass-'):
                    inner.append((sel[:60], part.strip()[:60]))
    check('audit: an inner light (inset, blurred, white) only in the glass themes\' tokens (④ 두께 빛)', not inner, inner)
    glass_tokens(src)


# drafts/glass.html R[id:'liquid'] (사용자 2026-11-16 10:02 "글라스 테마는 추천대로 4번") — head = --bar-bg, float = --tip-bg (→ sheets ·
# popovers), card = --card-bg, dock = --dock-bg; fb = the opaque fill when the blur is off
LIQUID = {
    'glass-dark': {'--bar-bg': 'rgba(14,16,22,.48)', '--tip-bg': 'rgba(16,18,24,.58)', '--card-bg': 'rgba(30,32,40,.86)', '--dock-bg': 'rgba(27,29,36,.97)',
                   '--blur': 'blur(14px) saturate(1.8)', '--blur-bar': 'blur(14px) saturate(1.8)', '--gl-plate': 'rgba(0,0,0,.55)', '--gl-sel': 'rgba(44,47,56,.94)',
                   'fb': ('#15171c', '#1c1e25'), 'sheen': '.1', 'ring': 'linear-gradient(135deg,rgba(255,255,255,.7),'},
    'glass-light': {'--bar-bg': 'rgba(255,255,255,.46)', '--tip-bg': 'rgba(255,255,255,.54)', '--card-bg': 'rgba(255,255,255,.8)', '--dock-bg': 'rgba(251,252,253,.97)',
                    '--blur': 'blur(14px) saturate(1.8) brightness(1.06)', '--blur-bar': 'blur(14px) saturate(1.8) brightness(1.06)', '--gl-plate': 'rgba(255,255,255,.72)', '--gl-sel': '#fff',
                    'fb': ('#eef0f4', '#f6f7f9'), 'sheen': '.55', 'ring': 'linear-gradient(135deg,#fff,'},
}


def glass_tokens(src):
    for th, want in LIQUID.items():
        m = re.search(r'html\[data-theme="%s"\]\{(.*?)\n\}' % th, src, re.S)
        body = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S) if m else ''
        decl = dict((k, v.strip()) for k, v in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', body))
        bad = []
        for k in ('--bar-bg', '--tip-bg', '--card-bg', '--dock-bg'):
            if not decl.get(k, '').endswith(',' + want[k]) or 'var(--gl-sheen' not in decl.get(k, ''):
                bad.append((k, decl.get(k)))
        for k in ('--blur', '--blur-bar', '--gl-plate', '--gl-sel'):
            if decl.get(k) != want[k]:
                bad.append((k, decl.get(k)))
        if not decl.get('--gl-sheen', '').startswith('radial-gradient(130% 70% at 25% 0%,rgba(255,255,255,' + want['sheen'] + ')'):
            bad.append(('--gl-sheen', decl.get('--gl-sheen')))
        if not decl.get('--gl-ring', '').startswith(want['ring']):
            bad.append(('--gl-ring', decl.get('--gl-ring')))
        for k in ('--tip-sh', '--bar-sh', '--card-sh', '--dock-sh'):     # 위 1px 빛 + 옆 1px + 아래 1px 빛
            v = decl.get(k, '')
            if not (re.search(r'inset 0 1px 0 (#fff|rgba\(255,255,255,\.\d+\))', v) and 'inset 1px 0 0' in v and 'inset -1px 0 0' in v and 'inset 0 -1px 0' in v):
                bad.append((k, v[:80]))
        check(f'audit: {th} carries the ④ values (fills · sheen · 135° ring · blur 14px · edges · plate · selected tab)', not bad, bad)
        hd, fl = want['fb']
        fb = [x for x in re.findall(r'html\[data-theme="%s"\](?:\[data-blur="off"\])?\{([^}]*--blur:none[^}]*)\}' % th, src)]
        ok = len(fb) == 3 and all(f'--tip-bg:var(--gl-sheen),{fl}' in x and f'--bar-bg:var(--gl-sheen),{hd}' in x and '--blur-bar:none' in x for x in fb)
        check(f'audit: {th} fallback (흐림 끔 · 투명도 줄이기 · 흐림 미지원) = the same sheen on the opaque ④ fills {hd} · {fl}, no blur', ok, fb)


# ───────────────────────── page ─────────────────────────
def start_mock():
    subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
    time.sleep(0.3)
    subprocess.Popen([sys.executable, str(ROOT / 'qa/float/mock_float.py'), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            NOPROXY.open(URL + 'api/time', timeout=1).read(); return
        except Exception:
            time.sleep(0.1)
    raise SystemExit('mock did not start')


def open_page(br, w, h, theme='base', motion='standard', market='K', extra=None, wait=2200, routes=None):
    mobile = w <= 760
    ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    def answer(body):          # a one-argument handler (Playwright hands a two-argument one the request too)
        return lambda r: r.fulfill(status=200, content_type='application/json', body=body(r.request.url) if callable(body) else body)
    for pat, body in (routes or {}).items():
        ctx.route(pat, answer(body))
    st = {'theme': theme, 'motion': motion, 'tickerPaused': True, 'market': market}
    st.update(extra or {})
    ctx.add_init_script('try{' + ''.join(f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});" for k, v in st.items()) + '}catch(e){}')
    pg = ctx.new_page()
    tag = f'{w}/{theme}/{market}'
    pg.on('console', lambda m: ERRS.append(f'{tag}: {m.text[:200]}') if m.type == 'error' else None)
    pg.on('pageerror', lambda e: ERRS.append(f'{tag} pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_timeout(wait)
    return ctx, pg


# elements drawn past the screen's right edge (the page clips at the root, so scrollWidth no longer shows it — as qa/float's overflow_net)
OVER = r"""() => {
  const vw = innerWidth, out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1) continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break; } p = p.parentElement; }
    if (!clipped && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).position !== 'fixed') out.push((e.id ? '#' + e.id : e.className && e.className.baseVal == null ? '.' + String(e.className).split(' ')[0] : e.tagName) + ' ' + Math.round(r.right));
  }
  return out.slice(0, 8);
}"""

TOKENS = r"""() => {
  const cs = getComputedStyle(document.documentElement), probe = document.createElement('i');
  document.body.append(probe);
  const rgb = v => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const out = { live: rgb(cs.getPropertyValue('--live').trim()), fail: rgb(cs.getPropertyValue('--fail-dot').trim()), acc: rgb(cs.getPropertyValue('--acc-fill').trim()),
    nd: rgb(cs.getPropertyValue('--new-dot').trim()), page: getComputedStyle(document.body).backgroundColor };
  probe.remove();
  return out;
}"""


def parse_rgb(s):
    v = [float(x) for x in re.findall(r'[\d.]+', s)[:3]]
    return [x / 255 for x in v]


def hue(c):
    h, l, s = colorsys.rgb_to_hls(*c)
    return h * 360, s


def lum(c):
    f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hdist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def page(br):
    for theme in THEMES:
        for w, h, top in ((390, 844, 247), (768, 1024, 250), (1280, 800, 207), (1440, 900, 207)):
            ctx, pg = open_page(br, w, h, theme=theme)
            g = pg.evaluate("() => ({ map: Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY), tiles: document.querySelectorAll('#map .tile').length })")
            ov = pg.evaluate(OVER)
            check(f'page [{w} {theme}]: map top {g["map"]} (= {top}), {g["tiles"]} tiles, nothing past the screen edge', g['map'] == top and g['tiles'] > 50 and not ov, (g, ov))
            if w == 1440:
                t = pg.evaluate(TOKENS)
                live, fail, acc, nd, pgc = (parse_rgb(t[k]) for k in ('live', 'fail', 'acc', 'nd', 'page'))
                hl, hs = hue(live)
                check(f'page [{theme}]: --live {t["live"]} — ≥ 30° from the amber and the new-filing blue, saturated, ≥ 4.5:1 on the page (extras writes the countdown in it)',
                      hdist(hl, hue(acc)[0]) >= 30 and hdist(hl, hue(nd)[0]) >= 30 and hs > .3 and contrast(live, pgc) >= 4.5, (round(hl), round(hue(acc)[0]), round(hue(nd)[0]), round(contrast(live, pgc), 2)))
                check(f'page [{theme}]: --fail-dot {t["fail"]} — not amber, ≥ 4.5:1 on the page', t['fail'] != t['acc'] and contrast(fail, pgc) >= 4.5, round(contrast(fail, pgc), 2))
                # the status: live (a live answer during the session is the mock's — force the classes the code sets) and error
                st = pg.evaluate("""() => { const s = document.getElementById('status'), d = s.querySelector('.dot'), b = s.querySelector('.badge');
                  s.classList.add('live'); s.classList.remove('err', 'replay', 'has-basis', 'has-blab'); if (!b.textContent) b.textContent = '실시간';
                  const live = { dot: getComputedStyle(d).backgroundColor, badge: getComputedStyle(b).color, sh: getComputedStyle(d).boxShadow };
                  s.classList.remove('live'); s.classList.add('err');
                  const err = { bg: getComputedStyle(d).backgroundColor, mark: getComputedStyle(d, '::after').content, col: getComputedStyle(d, '::after').color };
                  s.classList.remove('err'); return { live, err }; }""")
                check(f'page [{theme}]: live dot and 실시간 badge in --live (no glow ring), error dot = "!" in --fail-dot',
                      st['live']['dot'] == t['live'] and st['live']['badge'] == t['live'] and st['live']['sh'] in ('none', '') and st['err']['mark'] == '"!"' and st['err']['col'] == t['fail'], st)
                fl = pg.evaluate("""() => { const el = document.querySelector('#map .tile'), out = [];
                  for (const k of ['flash-up', 'fl-d']) { el.classList.add(k); const a = getComputedStyle(el, '::after'), n = el.querySelector('.pc');
                    out.push({ sh: a.boxShadow, bg: a.backgroundColor, num: n ? getComputedStyle(n).animationName : '' }); el.classList.remove(k); }
                  return out; }""")
                check(f'page [{theme}]: tick flash = 2+4 — a flat wash on ::after (no ring, no blur) + the number pill (기본 · 화려하게)',
                      all(x['sh'] in ('none', '') and x['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent') for x in fl)
                      and [x['num'] for x in fl] == ['fl-nu', 'fl-nd'], fl)
            ctx.close()
    motion(br)


MOTION_JS = r"""async () => {
  const out = {};
  const box = document.createElement('span'); box.style.cssText = 'position:fixed;left:10px;top:300px;font-size:13px;line-height:16px'; document.body.append(box);
  // KH.ui.swap: a label goes up; a value that rose comes in from below, one that fell from above (§6-4 · P9)
  const sw = dir => { box.textContent = 'A'; KH.ui.swap(box, 'B', 'A', dir); const an = box.getAnimations({ subtree: true });
    const kf = an.map(a => a.effect.getKeyframes()); return { cls: box.className, was: box.dataset.was, n: an.length, out: kf[0] && kf[0][1].transform, inn: kf[1] && kf[1][0].transform, blur: kf[0] && kf[0][1].filter,
      dur: an.map(a => a.effect.getTiming().duration), delay: an.map(a => a.effect.getTiming().delay), text: box.textContent }; };
  out.up = sw(1); out.dn = sw(-1); out.label = sw();
  // KH.ui.roll (화려하게): changed digits only, the rightmost first 40 ms apart, the short way, a 14 % fade mask
  box.textContent = '12.19'; KH.ui.roll(box, '12.20', 1);
  const cols = [...box.querySelectorAll('.rc')];
  out.roll = { drums: cols.length, delays: cols.map(c => c.firstChild.getAnimations()[0].effect.getTiming().delay), mask: getComputedStyle(cols[0]).webkitMaskImage || getComputedStyle(cols[0]).maskImage,
    text: box.textContent, steps: cols.map(c => (c.firstChild.dataset.b || c.firstChild.dataset.a || '').split('\n').length) };
  box.textContent = '0.9'; KH.ui.roll(box, '0.0', 1);
  out.short = (box.querySelector('.rs') || {}).dataset ? Object.assign({}, box.querySelector('.rs').dataset) : null;
  box.remove();
  // the shared icons: ✓ and ! drawn 1.75px on screen
  const ic = ['check', 'warn'].map(n => { const e = KH.ui.icon(n); return [...e.querySelectorAll('path,circle')].map(x => [x.getAttribute('stroke-width') || e.getAttribute('stroke-width'), x.getAttribute('vector-effect')]); });
  out.icons = ic;
  // tab %: new quotes move the 코스피 number in place, the way it went (no digit roll)
  const q = await (await fetch('/api/quotes')).json(), tp = document.querySelector('.tabs button[data-mkt="K"] .tp'), was = tp.textContent;
  q.index.KOSPI.ratio = +q.index.KOSPI.ratio + 0.5; q.index.KOSPI.value = +q.index.KOSPI.value * 1.005; q.asOf = new Date(Date.now() + 60000).toISOString();
  const fed = KH.feed(q);
  await new Promise(r => setTimeout(r, 30));
  const an = tp.getAnimations({ subtree: true });
  out.tab = { fed, was, now: tp.textContent, cls: tp.className, n: an.length, drums: tp.querySelectorAll('.rc').length, inn: an[1] && an[1].effect.getKeyframes()[0].transform };
  return out;
}"""


def motion(br):
    ctx, pg = open_page(br, 1440, 900, motion='fancy')
    m = pg.evaluate(MOTION_JS)
    up, dn, lb = m['up'], m['dn'], m['label']
    check('motion: KH.ui.swap = out 100 ms (blur, 4px) → in 180 ms 60 ms later; rose → from below, fell → from above, a label goes up',
          up['n'] == 2 and up['dur'] == [100, 180] and up['delay'] == [0, 60] and 'blur' in (up['blur'] or '') and up['inn'] == 'translateY(4px)' and up['out'] == 'translateY(-4px)'
          and dn['inn'] == 'translateY(-4px)' and dn['out'] == 'translateY(4px)' and lb['inn'] == 'translateY(4px)' and up['text'] == 'B', m)
    r = m['roll']
    check('motion: KH.ui.roll (화려하게) — changed digits only, the rightmost first (40 ms apart), a 14 % fade mask, the text = the value',
          r['drums'] == 2 and r['delays'] == [40, 0] and '14%' in (r['mask'] or '') and r['text'] == '12.20', r)
    check('motion: KH.ui.roll goes the short way (9 → 0 is one step forward)', m['short'] == {'b': '9'}, m['short'])
    check('motion: the ✓ and ! icons are drawn 1.75px on screen (non-scaling strokes)', all(w == '1.75' and v == 'non-scaling-stroke' for ic in m['icons'] for w, v in ic), m['icons'])
    t = m['tab']
    check('motion: new quotes swap the 코스피 tab % in place, from below when it rose — no digit drum', t['fed'] and t['was'] != t['now'] and 'sw-go' in t['cls'] and t['drums'] == 0 and t['inn'] == 'translateY(4px)', t)
    ctx.close()


# ───────────────────────── 시총순 ─────────────────────────
def run(parts):
    if 'audit' in parts:
        audit()
    if parts & {'page', 'cap', 'limits', 'glass'}:
        from playwright.sync_api import sync_playwright
        start_mock()
        try:
            with sync_playwright() as p:
                br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
                if 'page' in parts:
                    page(br)
                if 'cap' in parts:
                    cap(br)
                if 'limits' in parts:
                    limits(br)
                if 'glass' in parts:
                    glass(br)
                br.close()
        finally:
            subprocess.run(['fuser', '-k', f'{PORT}/tcp'], capture_output=True)
        check(f'console errors: {len(ERRS)}', not ERRS, ERRS[:6])



# ───────────────────────── glass ④ (AGENTS §3-38) ─────────────────────────
GL_UNDER = "(() => { const m = document.getElementById('map').getBoundingClientRect().top + scrollY; scrollTo(0, Math.max(0, m - 40)); return scrollY; })()"
GL_BIG = "(() => { const t = [...document.querySelectorAll('#map .tile')].sort((a, b) => b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0]; const r = t.getBoundingClientRect(); return { c: t.dataset.c, x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 60) }; })()"
GL_STATE = r"""() => {
  const hd = document.querySelector('header.top'), b4 = getComputedStyle(hd, '::before'), af = getComputedStyle(hd, '::after');
  const probe = document.createElement('i'); document.body.append(probe);
  const rgb = v => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const css = getComputedStyle(document.documentElement), tok = k => css.getPropertyValue(k).trim();
  const ring = el => { if (!el) return null; const a = getComputedStyle(el, '::after'); return { img: a.backgroundImage.slice(0, 60), pad: a.paddingTop, content: a.content }; };
  const vis = e => { const cs = getComputedStyle(e), r = e.getBoundingClientRect(); return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0 && r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
  // blurred panels on screen right now (the stuck header's panel is its ::before)
  const blurred = [...document.querySelectorAll('body *')].filter(e => { const f = getComputedStyle(e).backdropFilter; return f && f !== 'none' && vis(e); }).map(e => e.id || String(e.className).split(' ')[0]);
  if (b4.backdropFilter && b4.backdropFilter !== 'none') blurred.push('header::before');
  const tabs = document.querySelector('header.top .tabs'), pill = getComputedStyle(document.querySelector('header.top .tabs-sc'), '::before');
  const out = { stuck: hd.classList.contains('is-stuck'), head: { bf: b4.backdropFilter, bg: b4.backgroundColor, img: b4.backgroundImage.slice(0, 40) }, headRing: ring(hd),
    plate: rgb(tok('--gl-plate')), sel: rgb(tok('--gl-sel')), tray: getComputedStyle(tabs).backgroundColor, pill: pill.backgroundColor, pillOn: pill.opacity,
    blurred };
  const tip = document.querySelector('.tip');
  if (tip && vis(tip)) { const t = getComputedStyle(tip); out.tip = { bf: t.backdropFilter, bg: t.backgroundColor, img: t.backgroundImage.slice(0, 40), ring: ring(tip),
    nums: [...tip.querySelectorAll(':is(.up,.dn):not(.limtag)')].map(e => getComputedStyle(e).backgroundColor) }; }
  const card = [...document.querySelectorAll('.card')].find(vis);
  if (card) out.card = { bf: getComputedStyle(card).backdropFilter, ring: ring(card) };
  const dock = document.querySelector('.dock.on');
  if (dock) out.dock = { bf: getComputedStyle(dock).backdropFilter, ring: ring(dock), bg: getComputedStyle(dock).backgroundImage.slice(0, 40) };
  const pop = document.querySelector('.ctl.dd.open > .seg');
  if (pop) out.pop = { bf: getComputedStyle(pop).backdropFilter, ring: ring(pop) };
  const sh = document.querySelector('.sheet.open');
  if (sh) out.sheet = { bf: getComputedStyle(sh).backdropFilter, bg: getComputedStyle(sh).backgroundColor, nums: [...sh.querySelectorAll(':is(.up,.dn):not(.limtag)')].map(e => getComputedStyle(e).backgroundColor) };
  probe.remove();
  return out;
}"""
# the text of every 등락 number in the tooltip / quick view: where its glyphs sit (a Range over the text) with the plate rule on and off
GL_TEXTPOS = r"""(sel) => { const out = [];
  for (const el of document.querySelectorAll(sel)) { const r = document.createRange(); r.selectNodeContents(el); const b = r.getBoundingClientRect(); out.push([Math.round(b.left * 10) / 10, Math.round(b.top * 10) / 10]); }
  return out; }"""
GL_EXPECT = {'glass-dark': {'bf': 'blur(14px) saturate(1.8)', 'fb': ('rgb(21, 23, 28)', 'rgb(28, 30, 37)'), 'ring': 'linear-gradient(135deg, rgba(255, 255, 255, 0.7)'},
             'glass-light': {'bf': 'blur(14px) saturate(1.8) brightness(1.06)', 'fb': ('rgb(238, 240, 244)', 'rgb(246, 247, 249)'), 'ring': 'linear-gradient(135deg, rgb(255, 255, 255)'}}


def glass(br):
    for theme, E in GL_EXPECT.items():
        for w, h in ((1440, 900), (390, 844)):
            ctx, pg = open_page(br, w, h, theme=theme, extra={'set.glassBlur': 'on'})
            pg.evaluate(GL_UNDER); pg.wait_for_timeout(400)
            tag = f'glass [{theme} {w}]'
            if w == 1440:
                b = pg.evaluate(GL_BIG); pg.mouse.move(b['x'], b['y']); pg.wait_for_timeout(500)
            s = pg.evaluate(GL_STATE)
            check(f'{tag}: the stuck header — blur {E["bf"]}, the 1.25px 135° ring, the radial sheen over the fill',
                  s['stuck'] and s['head']['bf'] == E['bf'] and s['headRing']['img'].startswith(E['ring']) and s['headRing']['pad'] == '1.25px' and s['head']['img'].startswith('radial-gradient'), s['head'] | {'ring': s['headRing']})
            check(f'{tag}: the tab tray is the number plate ({s["plate"]}), the selected tab\'s pill near-opaque ({s["sel"]})',
                  s['tray'] == s['plate'] and s['pill'] == s['sel'] and s['pillOn'] == '1', (s['tray'], s['pill'], s['pillOn']))
            check(f'{tag}: the card — no blur, the ring', s.get('card') and s['card']['bf'] == 'none' and 'linear-gradient(135deg' in s['card']['ring']['img'], s.get('card'))
            check(f'{tag}: at most two blurred panels on screen ({len(s["blurred"])})', len(s['blurred']) <= 2, s['blurred'])
            if w == 1440:
                t = s.get('tip')
                check(f'{tag}: the tooltip — blur {E["bf"]}, the ring, every 등락 number on the plate ({len(t["nums"]) if t else 0})',
                      t and t['bf'] == E['bf'] and t['ring']['img'].startswith(E['ring']) and t['nums'] and all(x == s['plate'] for x in t['nums']), t)
                sel = '.tip :is(.up,.dn):not(.limtag)'
                on = pg.evaluate(GL_TEXTPOS, sel)
                pg.add_style_tag(content='html[data-theme] .tip :is(.up,.dn){padding:0!important;margin:0!important;background:none!important}')
                off = pg.evaluate(GL_TEXTPOS, sel)
                check(f'{tag}: the plate moves no number (glyphs at the same place with the plate off)', on and on == off, (on[:4], off[:4]))
                pg.mouse.move(3, 3); pg.wait_for_timeout(300)
                pg.click('.ctl.dd[data-ctl="colorBy"] .ddbtn'); pg.wait_for_timeout(500)
                s2 = pg.evaluate(GL_STATE)
                check(f'{tag}: the 색 기준 popover — blur {E["bf"]}, the ring', s2.get('pop') and s2['pop']['bf'] == E['bf'] and s2['pop']['ring']['img'].startswith(E['ring']), s2.get('pop'))
                pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
            else:
                pg.evaluate("document.getElementById('map').scrollIntoView({block:'end'}); scrollBy(0, 400)"); pg.wait_for_timeout(700)
                s2 = pg.evaluate(GL_STATE)
                d = s2.get('dock')
                check(f'{tag}: the dock — no blur, the sheen, the ring', d and d['bf'] == 'none' and d['bg'].startswith('radial-gradient') and 'linear-gradient(135deg' in d['ring']['img'], d)
                pg.evaluate(GL_UNDER); pg.wait_for_timeout(300)
            b = pg.evaluate(GL_BIG); pg.evaluate(f"KH.quick({json.dumps(b['c'])})"); pg.wait_for_timeout(700)
            s3 = pg.evaluate(GL_STATE)
            q = s3.get('sheet')
            check(f'{tag}: the quick view — blur {E["bf"]}, every 등락 number on the plate', q and q['bf'] == E['bf'] and q['nums'] and all(x == s['plate'] for x in q['nums']), q)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
            # 유리 흐림 끄기: the same shapes, opaque fills, the sheen and the ring kept
            pg.evaluate("document.documentElement.dataset.blur = 'off'"); pg.wait_for_timeout(300)
            if w == 1440:
                b = pg.evaluate(GL_BIG); pg.mouse.move(b['x'], b['y']); pg.wait_for_timeout(500)
            f = pg.evaluate(GL_STATE)
            ok = f['head']['bf'] == 'none' and f['head']['bg'] == E['fb'][0] and f['head']['img'].startswith('radial-gradient') and f['headRing']['img'].startswith(E['ring'])
            if w == 1440:
                ok = ok and f.get('tip') and f['tip']['bf'] == 'none' and f['tip']['bg'] == E['fb'][1] and f['tip']['img'].startswith('radial-gradient') and f['tip']['ring']['img'].startswith(E['ring'])
            check(f'{tag}: 유리 흐림 끄기 (data-blur="off") — no blur, opaque fills {E["fb"]}, the sheen and the ring kept', ok, f['head'] | {'tip': f.get('tip')})
            ctx.close()
        # 투명도 줄이기: the same fallback from the media query (Chrome's emulated media)
        ctx, pg = open_page(br, 1440, 900, theme=theme, extra={'set.glassBlur': 'on'})
        cdp = ctx.new_cdp_session(pg)
        cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-transparency', 'value': 'reduce'}]})
        pg.wait_for_timeout(300)
        pg.evaluate(GL_UNDER); pg.wait_for_timeout(400)
        b = pg.evaluate(GL_BIG); pg.mouse.move(b['x'], b['y']); pg.wait_for_timeout(500)
        f = pg.evaluate(GL_STATE)
        ok = f['head']['bf'] == 'none' and f['head']['bg'] == E['fb'][0] and f['head']['img'].startswith('radial-gradient') and f.get('tip') and f['tip']['bf'] == 'none' and f['tip']['bg'] == E['fb'][1] and f['tip']['ring']['img'].startswith(E['ring'])
        check(f'glass [{theme}]: prefers-reduced-transparency: reduce — the same fallback (no blur, opaque fills, sheen · ring kept)', ok, f['head'] | {'tip': f.get('tip')})
        ctx.close()

CAPSTATE = r"""() => {
  const tiles = [...document.querySelectorAll('#map .tile')].filter(t => !t.classList.contains('leaving') && t.offsetWidth > 0);
  const boxes = tiles.map(t => ({ c: t.dataset.c, x: t.offsetLeft, y: t.offsetTop, w: t.offsetWidth, h: t.offsetHeight }));
  // reading order: rows by top edge, then left to right (strips share their top edge)
  const read = boxes.slice().sort((a, b) => a.y - b.y || a.x - b.x).map(b => b.c);
  const cap = c => (KH.stock(c) || {}).cap || 0;
  const byCap = boxes.map(b => b.c).sort((a, b) => cap(b) - cap(a) || (a < b ? -1 : 1));
  let inv = 0; for (let i = 1; i < read.length; i++) if (cap(read[i]) > cap(read[i - 1])) inv++;
  const lay = KH.layout();
  const bad = [];
  for (const t of tiles) { const l = t.querySelector('.lab'); if (!l || l.hidden) continue; const a = t.getBoundingClientRect(), b = l.getBoundingClientRect();
    if (b.left < a.left - .5 || b.right > a.right + .5 || b.top < a.top - .5 || b.bottom > a.bottom + .5) bad.push(t.dataset.c); }
  return { n: tiles.length, codes: KH.mapCodes().length, read: read.slice(0, 20), byCap: byCap.slice(0, 20), inv, secs: document.querySelectorAll('#map .node.sec, #map .node.ind').length,
    laySec: lay.filter(n => n.kind !== 'tile').length, layTiles: lay.filter(n => n.kind === 'tile').length, overflow: bad.slice(0, 5),
    store: localStorage.getItem('khm.groupBy'), aria: document.getElementById('map').getAttribute('aria-label'), hint: (document.querySelector('#crumbs .hint') || {}).textContent || '' };
}"""

GBROW = r"""() => { const r = document.querySelector('.ctl[data-ctl="groupBy"]'); if (!r) return null;
  const cs = getComputedStyle(r), box = r.getBoundingClientRect();
  return { hidden: r.hidden, shown: cs.display !== 'none' && box.width > 0 && box.height > 0 && !r.closest('.set-empty'), inMore: !!r.closest('#morePanel'), inCtls: !!r.closest('#ctls'),
    pressed: [...r.querySelectorAll('button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.v), labels: [...r.querySelectorAll('button')].map(b => b.textContent) }; }"""


def cap(br):
    # ── the option: 코스피 · 코스닥 · 전체 only; 표시 설정 sheet < 1280 (after 크기), 화면 popover ≥ 1280 ──
    for w, h in ((390, 844), (1000, 900), (1440, 900)):
        ctx, pg = open_page(br, w, h, market='K')
        seen = {}
        for m in ('K', 'Q', 'ALL', 'THEME', 'WORLD', 'CMDTY', 'CAL', 'WATCH'):
            pg.evaluate(f"document.querySelector('.tabs button[data-mkt=\"{m}\"]').click()"); pg.wait_for_timeout(500)
            opener = '#moreBtn' if w >= 1280 else '#setBtn'
            pg.click(opener); pg.wait_for_timeout(500)
            seen[m] = pg.evaluate(GBROW)
            pg.keyboard.press('Escape'); pg.wait_for_timeout(350)
        want = {m: m in ('K', 'Q', 'ALL') for m in seen}
        got = {m: bool(x and x['shown']) for m, x in seen.items()}
        where = {m: (x['inMore'], x['inCtls']) for m, x in seen.items() if x}
        place_ok = all(v[0] for v in where.values()) if w >= 1280 else all(v[1] and not v[0] for v in where.values())
        check(f'cap [{w}]: 묶음 shown on 코스피 · 코스닥 · 전체 only, {"in the 화면 popover" if w >= 1280 else "in the 표시 설정 sheet"}; 섹터별 · 시총순, 섹터별 pressed',
              got == want and place_ok and seen['K']['labels'] == ['섹터별', '시총순'] and seen['K']['pressed'] == ['sector'], (got, where, seen['K']))
        ctx.close()
    # ── 시총순 on 코스피 (1440, 300 tiles) ──
    ctx, pg = open_page(br, 1440, 900, market='K')
    before = pg.evaluate(CAPSTATE)
    pg.click('#moreBtn'); pg.wait_for_timeout(400)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="cap"]'); pg.wait_for_timeout(100)
    mid = pg.evaluate("() => [...document.querySelectorAll('#map .tile')].filter(t => t.getAnimations().length).length")
    pg.keyboard.press('Escape'); pg.wait_for_timeout(900)
    st = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: 시총순 pressed → saved khm.groupBy "cap", no sector / industry node in the map or KH.layout(), the same tiles',
          st['store'] == '"cap"' and st['secs'] == 0 and st['laySec'] == 0 and st['layTiles'] == st['n'] == before['codes'] == st['codes'] and before['secs'] > 0, (st['store'], st['secs'], st['laySec'], st['n'], before['codes']))
    check('cap [1440 K]: the tiles moved to their new boxes (FLIP, as a zoom)', mid > 100, mid)
    check('cap [1440 K]: reading order = market-cap order (first 20 exact, no inversion anywhere)', st['read'] == st['byCap'] and st['inv'] == 0, (st['read'][:8], st['byCap'][:8], st['inv']))
    check('cap [1440 K]: labels inside their tiles; map named "시가총액이 큰 종목부터"; the crumbs hint says so',
          not st['overflow'] and '시가총액이 큰 종목부터' in st['aria'] and '시가총액이 큰' in st['hint'], (st['overflow'], st['aria'], st['hint']))
    pg.screenshot(path=str(ROOT / 'qa/shots/std_template/cap_1440_K.png'))
    # 크기 = 거래대금: sized by trading value, still in cap order
    pg.evaluate("document.querySelector('.seg[data-key=\"sizeBy\"] button[data-v=\"tv\"]').click()"); pg.wait_for_timeout(900)
    st2 = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: 크기 = 거래대금 — still read in cap order (sizes by trading value)', st2['read'] == st2['byCap'] and st2['inv'] == 0 and not st2['overflow'], (st2['read'][:6], st2['inv']))
    pg.screenshot(path=str(ROOT / 'qa/shots/std_template/cap_1440_K_tv.png'))
    pg.evaluate("document.querySelector('.seg[data-key=\"sizeBy\"] button[data-v=\"cap\"]').click()"); pg.wait_for_timeout(700)
    # search highlight · tooltip · quick view · disclosure marks · image save
    pg.fill('#q', '삼성'); pg.wait_for_timeout(500)
    hl = pg.evaluate("() => { const t = [...document.querySelectorAll('#map .tile')]; return { dim: t.filter(x => x.classList.contains('dim')).length, lit: t.filter(x => !x.classList.contains('dim')).map(x => KH.stock(x.dataset.c).n) }; }")
    check('cap [1440 K]: search highlight — only the 삼성 tiles stay lit', hl['dim'] > 200 and hl['lit'] and all('삼성' in n for n in hl['lit']), (hl['dim'], hl['lit'][:5]))
    pg.fill('#q', ''); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    box = pg.evaluate("(() => { const t = document.querySelector('#map .tile'); const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, t.dataset.c]; })()")
    pg.mouse.move(box[0], box[1]); pg.wait_for_timeout(600)
    tip = pg.evaluate("() => { const t = document.getElementById('tip'); return { on: getComputedStyle(t).opacity > 0.5, txt: t.textContent.slice(0, 40) }; }")
    name = pg.evaluate(f"KH.stock('{box[2]}').n")
    check(f'cap [1440 K]: tooltip on the biggest tile ({name})', tip['on'] and name in tip['txt'], tip)
    # desktop: a tile opens the stock page (stubbed here — the mock has no /api/stock); the quick view is checked on the phone below
    pg.evaluate("() => { window.__op = null; const k = window.KHStock; if (k) k.open = (c) => { window.__op = c; }; }")
    pg.mouse.click(box[0], box[1]); pg.wait_for_timeout(300)
    check('cap [1440 K]: a tile opens its stock page', pg.evaluate('window.__op') == box[2], pg.evaluate('window.__op'))
    pg.mouse.move(5, 5); pg.wait_for_timeout(200)
    mk = pg.evaluate("""() => { const c = [...document.querySelectorAll('#map .tile')].slice(0, 6).map(t => t.dataset.c);
      KH.marks.set('qa', new Map(c.map(x => [x, { size: 'n', label: ', 시험' }]))); const n = document.querySelectorAll('#map .tile .dm').length;
      const lay = KH.layout().filter(t => t.mark).length; return { n, lay }; }""")
    check('cap [1440 K]: 공시 귀퉁이 (KH.marks) drawn on the cap-ordered tiles and in KH.layout()', mk['n'] >= 6 and mk['lay'] >= 6, mk)
    pg.evaluate("KH.marks.set('qa', null)")
    try:
        with pg.expect_download(timeout=8000) as dl:
            pg.click('.xt-btn[data-x="image"]')
        out = ROOT / 'qa/shots/std_template/cap_export.png'
        dl.value.save_as(str(out))
        from PIL import Image
        im = Image.open(out); colors = len(set(im.convert('RGB').resize((80, 80)).get_flattened_data()))
        check(f'cap [1440 K]: the image save (extras) draws the cap map — {im.size[0]}×{im.size[1]}, {colors} colours', im.size[0] > 800 and colors > 30, (im.size, colors))
    except Exception as e:
        check('cap [1440 K]: the image save (extras) draws the cap map', False, e)
    # a replay frame keeps the cap order and the shape
    rp = pg.evaluate("""() => { const m = new Map(); for (const s of KH.stocks().slice(0, 600)) m.set(s.c, { p: s.p * 1.01, r: (s.r || 0) + 1 });
      KH.setReplay({ t: '1030', date: '2026-11-13', prices: m }); const n = document.querySelectorAll('#map .node.sec').length; return n; }""")
    pg.wait_for_timeout(500)
    st3 = pg.evaluate(CAPSTATE)
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(400)
    check('cap [1440 K]: a replay frame draws the cap map (no bands, cap order)', rp == 0 and st3['secs'] == 0 and st3['inv'] == 0, (rp, st3['secs'], st3['inv']))
    # back to 섹터별: bands return
    pg.click('#moreBtn'); pg.wait_for_timeout(400)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="sector"]'); pg.keyboard.press('Escape'); pg.wait_for_timeout(900)
    bk = pg.evaluate(CAPSTATE)
    check('cap [1440 K]: back to 섹터별 — sector / industry bands again, saved "sector"', bk['secs'] > 0 and bk['store'] == '"sector"', (bk['secs'], bk['store']))
    ctx.close()
    # ── phones, 전체, every theme: order, no overflow, map top unchanged ──
    for theme in THEMES:
        for w, h, m, top in ((390, 844, 'ALL', 247), (1440, 900, 'Q', 207)):
            ctx, pg = open_page(br, w, h, theme=theme, market=m, extra={'groupBy': 'cap'})
            st = pg.evaluate(CAPSTATE)
            g = pg.evaluate("() => Math.round(document.getElementById('map').getBoundingClientRect().top + scrollY)")
            ov = pg.evaluate(OVER)
            check(f'cap [{w} {m} {theme}]: saved 시총순 → cap order, no bands, labels inside, nothing past the edge, map top {g} (= {top})',
                  st['secs'] == 0 and st['inv'] == 0 and st['read'][:10] == st['byCap'][:10] and not st['overflow'] and not ov and g == top, (st['secs'], st['inv'], st['overflow'], ov, g))
            if theme in ('base', 'glass-light'):
                pg.screenshot(path=str(ROOT / f'qa/shots/std_template/cap_{w}_{m}_{theme}.png'))
            if w == 390 and theme == 'base':
                tb = pg.evaluate("(() => { const t = document.querySelector('#map .tile'); const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, KH.stock(t.dataset.c).n]; })()")
                pg.touchscreen.tap(tb[0], tb[1]); pg.wait_for_timeout(800)
                sh = pg.evaluate("() => { const s = document.getElementById('sheet'); return { open: s.classList.contains('open'), txt: s.textContent.slice(0, 80) }; }")
                check(f'cap [390]: tapping the first tile ({tb[2]}) opens the quick view', sh['open'] and tb[2] in sh['txt'], sh)
                pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
            # 테마 · 관심 keep their own maps
            if w == 390 and theme == 'base':
                pg.evaluate("document.querySelector('.tabs button[data-mkt=\"THEME\"]').click()"); pg.wait_for_timeout(800)
                th = pg.evaluate("() => document.getElementById('map').getAttribute('aria-label')")
                check('cap [390]: 테마 keeps its theme map with 시총순 saved', th == '테마별 트리맵', th)
            ctx.close()
    # ── 줄이기: the switch lands at once ──
    ctx, pg = open_page(br, 1440, 900, market='K', motion='reduced')
    pg.click('#moreBtn'); pg.wait_for_timeout(300)
    pg.click('.ctl[data-ctl="groupBy"] button[data-v="cap"]'); pg.wait_for_timeout(60)
    an = pg.evaluate("() => [...document.querySelectorAll('#map .tile')].filter(t => t.getAnimations().length).length")
    check('cap [1440 줄이기]: 시총순 lands at once (no tile animation)', an == 0, an)
    ctx.close()


# ───────────────────────── limits: 상한가 · 하한가 in the dock (사용자 2026-11-16 00:54) ─────────────────────────
LIMSTATE = r"""() => {
  const c = document.querySelector('.dk-c[data-k="brd"]'); if (!c) return null;
  const n = e => +String(e.textContent).replace(/[^0-9]/g, '');
  const lim = c.querySelector('.lim'), l1 = c.querySelector('.dk-l1'), nm = c.querySelector('.nm');
  const dock = lim.hidden ? null : { lu: n(lim.querySelector('.lu')), ld: n(lim.querySelector('.ld')), words: [...lim.querySelectorAll('.lk')].map(e => e.textContent),
    luCls: lim.querySelector('.lu').className, ldCls: lim.querySelector('.ld').className };
  const dl = document.getElementById('distLim');
  const card = !dl || dl.hidden ? null : (() => { const s = dl.querySelectorAll('span'); return { lu: n(s[0]), ld: n(s[1]) }; })();
  const M = window.KHSummary ? KHSummary.model() : null, br = M && M.br, mk = KH.market();
  const sum = br ? (mk === 'K' ? br.K : mk === 'Q' ? br.Q : br) : null;
  const rg = document.createRange(); rg.selectNodeContents(nm);
  const parts = [...l1.children].filter(e => !e.hidden && getComputedStyle(e).display !== 'none'), rs = parts.map(e => e.getBoundingClientRect()), lr = l1.getBoundingClientRect();
  let overlap = false; for (let i = 1; i < rs.length; i++) if (rs[i].left < rs[i - 1].right - .25) overlap = true;
  const d = document.querySelector('.dock').getBoundingClientRect(), cb = c.getBoundingClientRect();
  return { dock, card, sum: sum ? { lu: sum.lu, ld: sum.ld } : null, src: br ? br.src : null, aria: c.getAttribute('aria-label') || '',
    nmWhole: rg.getBoundingClientRect().width <= nm.getBoundingClientRect().width + .5, overlap, inside: rs.every(r => r.left >= lr.left - .5 && r.right <= lr.right + .5),
    cnt: !c.querySelector('.cnt').hidden, cellH: Math.round(cb.height), dockH: Math.round(d.height), dockB: Math.round(innerHeight - d.bottom), l1H: Math.round(lr.height),
    shown: getComputedStyle(document.querySelector('.dock')).visibility };
}"""


def lim_files(flags=True):
    """close.json with known flags: K 12 상한 · 3 하한, Q 11 상한 · 10 하한 (every other flag cleared); flags=False = an older file (no
    "lim" key, no 4th field). The matching /api/breadth rows (summary reads them in market hours)."""
    cj = json.loads((ROOT / 'web/close.json').read_text())
    names = json.loads((ROOT / 'web/names.json').read_text())['n']
    want = {'K': [1] * 12 + [-1] * 3, 'Q': [1] * 11 + [-1] * 10}
    used = {'K': 0, 'Q': 0}
    rows = {'K': [], 'Q': []}
    for c in sorted(cj['c']):
        x = cj['c'][c][:3]
        m = (names.get(c) or [None, None])[1]
        f = 0
        if m in want and +x[0] > 0 and used[m] < len(want[m]):
            f = want[m][used[m]]; used[m] += 1
        cj['c'][c] = x + [f] if flags and f else x
        if m in rows:
            rows[m].append([c, x[2], f if flags else 0])
    if not flags:
        cj.pop('lim', None)
    else:
        cj['lim'] = True
    def breadth(url):
        m = re.search(r'[?&]m=([KQ])', url)
        r = rows[m.group(1)] if m else []
        return json.dumps({'m': m and m.group(1), 'part': 1, 'parts': 1, 'asOf': None, 'rows': r})
    return {'**/data/close.json': json.dumps(cj), '**/api/breadth*': breadth}


def limits(br):
    exp = {'K': (12, 3), 'Q': (11, 10), 'ALL': (23, 13)}

    def state(pg, tries=40):
        for _ in range(tries):
            s = pg.evaluate(LIMSTATE)
            if s and s['shown'] == 'visible' and s['dock'] is not None and s['card'] is not None and s['sum'] is not None:
                return s
            pg.wait_for_timeout(150)
        return pg.evaluate(LIMSTATE)

    def reveal(pg):
        pg.evaluate("scrollTo(0, document.getElementById('map').getBoundingClientRect().bottom + scrollY + 40)")
        pg.wait_for_timeout(1000)

    base = None
    for w, mk in ((390, 'K'), (390, 'Q'), (390, 'ALL'), (360, 'K'), (360, 'ALL')):
        ctx, pg = open_page(br, w, 844, market=mk, routes=lim_files(True))
        reveal(pg)
        s = state(pg)
        e = exp[mk]
        tag = f'limits [{w} {mk}]'
        check(f'{tag}: dock = 등락 분포 card = 시장 요약 카드 = the flags {e}', s and s['dock'] and s['card'] and s['sum'] and
              (s['dock']['lu'], s['dock']['ld']) == (s['card']['lu'], s['card']['ld']) == (s['sum']['lu'], s['sum']['ld']) == e, s)
        check(f'{tag}: aria-label ends with 상한가 · 하한가', s and f'상한가 {e[0]}종목, 하한가 {e[1]}종목 — ' in s['aria'], s and s['aria'])
        check(f'{tag}: numbers in the data colours, words neutral', s and s['dock'] and 'up' in s['dock']['luCls'] and 'dn' in s['dock']['ldCls'], s and s['dock'])
        check(f'{tag}: the top line fits (no overlap, inside, the name whole)', s and s['dock'] and not s['overlap'] and s['inside'] and s['nmWhole'], s)
        check(f'{tag}: cell 44 · dock 56 · bottom 8 · top line 14', s and (s['cellH'], s['dockH'], s['dockB'], s['l1H']) == (44, 56, 8, 14), s)
        if w == 390 and mk == 'K':
            base = s
        ctx.close()
    # an older close.json (no flags): nothing to count → the dock and the card say nothing (not 0); same heights
    ctx, pg = open_page(br, 390, 844, market='K', routes=lim_files(False))
    reveal(pg)
    s = state(pg, tries=12)
    check('limits [older close.json]: dock and card hide the counts (no 0), the aria-label has none', s and s['dock'] is None and s['card'] is None and '상한가' not in s['aria'], s)
    check('limits [older close.json]: same cell · dock · bottom · line heights as with counts', s and base and
          (s['cellH'], s['dockH'], s['dockB'], s['l1H']) == (base['cellH'], base['dockH'], base['dockB'], base['l1H']), (s, base))
    ctx.close()
    # a replay frame carries no flags → hidden, back with the live data
    ctx, pg = open_page(br, 390, 844, market='K', routes=lim_files(True))
    reveal(pg)
    state(pg)
    pg.evaluate("KH.setReplay({t: '1000', date: '2026-11-13', prices: new Map()})"); pg.wait_for_timeout(500)
    s = pg.evaluate(LIMSTATE)
    check('limits [replay]: dock and card hide the counts', s and s['dock'] is None and s['card'] is None and '상한가' not in s['aria'], s)
    pg.evaluate("KH.setReplay(null)"); pg.wait_for_timeout(500)
    s = state(pg, tries=12)
    check('limits [replay off]: the counts come back', s and s['dock'] and (s['dock']['lu'], s['dock']['ld']) == exp['K'], s)
    ctx.close()


if __name__ == '__main__':
    parts = set(sys.argv[1:]) or {'audit', 'page', 'cap', 'limits', 'glass'}
    run(parts)
    print(f'\n{len(PASSES)} passed, {len(FAILS)} failed')
    for f in FAILS:
        print('  FAIL', f)
    sys.exit(1 if FAILS else 0)
