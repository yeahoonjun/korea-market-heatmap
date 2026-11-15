#!/usr/bin/env python3
"""이동평균 선 색 (design.md §2): the four MA colours of src/stock/stock.css in every theme.

    python3 qa/stock/test_ma_colors.py

- each colour >= 3:1 on the chart ground of its theme (the card the canvas sits on; glass = both ends of its gradient)
- --ma-5 is >= 30 degrees of hue away from the interface amber of that theme (--acc · --acc-fill · --focus) and is neither red
  (hue 340..20) nor green (85..165) — red and green are data only
- the four stay apart: CIEDE2000 >= 18 between any two; --ma-5 >= 15 from every candle colour of the four palettes in that theme
No browser: the grounds and inks are the values of src/template.html (themes.md §4, palette × theme §8).
"""
import colorsys, itertools, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (ROOT / 'src/stock/stock.css').read_text(encoding='utf8')


def ma_set(selector):   # the rule whose selector list is exactly `selector` (one line in stock.css)
    vals = {}
    for body in re.findall(r'^' + re.escape(selector) + r'\s*\{([^}]*)\}', CSS, re.M):
        vals.update(re.findall(r'--ma-(\d+):\s*(#[0-9a-fA-F]{6})', body))
    return {int(k): v for k, v in vals.items()}


DARK = ma_set('.sp')
LIGHT = ma_set('html[data-tone="light"] .sp, html[data-theme="paper"] .sp, html[data-theme="glass-light"] .sp')

hx = lambda c: tuple(int(c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
lin = lambda v: (v / 255) / 12.92 if v / 255 <= 0.04045 else (((v / 255) + 0.055) / 1.055) ** 2.4
lum = lambda c: 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
ratio = lambda a, b: (max(lum(a), lum(b)) + 0.05) / (min(lum(a), lum(b)) + 0.05)
hue = lambda c: colorsys.rgb_to_hls(*[x / 255 for x in c])[0] * 360
hdist = lambda a, b: min(abs(a - b) % 360, 360 - abs(a - b) % 360)


def lab(c):
    r, g, b = (lin(x) for x in c)
    X, Y, Z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))


def de2000(c1, c2):
    L1, a1, b1 = lab(c1); L2, a2, b2 = lab(c2)
    Cb = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
    dh = 0 if C1p * C2p == 0 else (h2p - h1p - 360 if h2p - h1p > 180 else h2p - h1p + 360 if h2p - h1p < -180 else h2p - h1p)
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hbp = h1p + h2p if C1p * C2p == 0 else (h1p + h2p) / 2 if abs(h1p - h2p) <= 180 else (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = 1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp)) + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)); dth = 30 * math.exp(-((hbp - 275) / 25) ** 2)
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2); Sc = 1 + 0.045 * Cbp; Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dth)) * Rc
    dL, dC = L2 - L1, C2p - C1p
    return math.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dC / Sc) * (dHp / Sh))


# chart ground (.sp-chartwrap = --card-bg over --page), amber inks, candle colours of krg · krb · global · cvd
DARK_CANDLES = ['#ef3e4a', '#12a15b', '#2f74e6', '#f63538', '#2bb553', '#ef8a1f', '#3d95ee']
THEMES = {
    'base': {'ma': DARK, 'ground': ['#191a1f'], 'amber': ['#ffb547'], 'candles': DARK_CANDLES},
    # rgba(22,24,30,.72) on #0b0c10, + 7.5 % → 2 % white from the top
    'glass-dark': {'ma': DARK, 'ground': ['#25272b', '#13151a'], 'amber': ['#ffb547'], 'candles': DARK_CANDLES},
    'paper': {'ma': LIGHT, 'ground': ['#f6e8da'], 'amber': ['#8a4b00', '#f3b941'], 'candles': ['#ad2a20', '#1a6a40', '#22509a', '#a95500']},
    # rgba(255,255,255,.82 → .56) on #e7eaf0
    'glass-light': {'ma': LIGHT, 'ground': ['#fbfbfc', '#f4f6f8'], 'amber': ['#7f4700', '#ffb547', '#9a5600'], 'candles': ['#d0303a', '#0e8247', '#2461cf', '#c46800']},
}

fails = []
for name, T in THEMES.items():
    ma = T['ma']
    assert sorted(ma) == [5, 20, 60, 120], (name, ma)
    print(f'== {name}')
    for n, c in ma.items():
        C = hx(c)
        cr = min(ratio(C, hx(g)) for g in T['ground'])
        dc = min(de2000(C, hx(x)) for x in T['candles'])
        line = f'  ma{n:<3} {c}  hue {hue(C):5.1f}  contrast {cr:4.2f}  ΔE00 to candles ≥ {dc:4.1f}'
        if cr < 3: fails.append(f'{name} ma{n} contrast {cr:.2f}')
        if n == 5 and dc < 15: fails.append(f'{name} ma{n} too close to a candle colour ({dc:.1f})')   # (20 sky vs the HTS blue: as before)
        if n == 5:
            ah = min(hdist(hue(C), hue(hx(a))) for a in T['amber'])
            line += f'  hue from amber {ah:.0f}°'
            if ah < 30: fails.append(f'{name} ma5 only {ah:.0f}° from amber')
            h = hue(C)
            if h >= 340 or h <= 20 or 85 <= h <= 165: fails.append(f'{name} ma5 hue {h:.0f} reads red / green')
        print(line)
    pairs = {f'{a}/{b}': de2000(hx(ma[a]), hx(ma[b])) for a, b in itertools.combinations(sorted(ma), 2)}
    print('  ΔE00 between lines:', ', '.join(f'{k} {v:.1f}' for k, v in pairs.items()))
    fails += [f'{name} ma {k} too close ({v:.1f})' for k, v in pairs.items() if v < 18]

print('\n' + ('PASS ma colours' if not fails else 'FAIL ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
