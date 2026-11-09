"""Tile label legibility: white text on the brightest fills, plain vs the old shadow vs the new halo.
Effective contrast = white vs the mean colour of the pixels 1–2 css px around the glyph cores (what the eye compares the strokes with)."""
import sys, io
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch
from playwright.sync_api import sync_playwright
from PIL import Image
import numpy as np

FILLS = {'#12a15b (빨강 상승 −max)': '#12a15b', '#ef3e4a (빨강 상승 +max)': '#ef3e4a', '#2bb553 (초록 상승 +max)': '#2bb553', '#f63538 (초록 상승 −max)': '#f63538'}
SHADOWS = {'none': 'none', 'old': '0 1px 2px rgba(0,0,0,.45)', 'new': None, 'new<16px': 'SM'}   # None = the template's rule; SM = .lab.sm (labels under 16 px)


def lin(c):
    c = c / 255.0
    return np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lum(rgb):
    r, g, b = lin(rgb[..., 0]), lin(rgb[..., 1]), lin(rgb[..., 2])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ring_contrast(img):
    a = np.asarray(img.convert('RGB')).astype(float)
    L = lum(a)
    core = L > 0.8
    # dilate the glyph cores by 2 and 4 device px (dpr 2 → 1 and 2 css px); the ring is the band in between, minus any glyph pixel
    def dil(m, k):
        out = m.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
        return out
    ring = dil(core, 4) & ~dil(core, 2) & (L < 0.5)
    if not ring.any():
        return None
    m = a[ring].mean(0)
    Lr = float(lum(m[None, :])[0])
    return round(1.05 / (Lr + 0.05), 2)


def plain(hexc):
    c = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], float)
    return round(1.05 / (float(lum(c[None, :])[0]) + 0.05), 2)


URL = 'file:///home/claude/hm-heatmap/dist/index.html'
if __name__ == '__main__':
  with sync_playwright() as p:
        b = launch(p); pg = b.new_page(viewport={'width': 900, 'height': 600}, device_scale_factor=2)
        pg.goto(URL); pg.wait_for_timeout(1200)
        print(f"{'fill':28} {'plain':>6} {'old':>6} {'new≥16':>7} {'new<16':>7}   (white text vs the pixels 1–2 px around the strokes; 11px label)")
        for label, col in FILLS.items():
            out = {'plain': plain(col)}
            for k, sh in SHADOWS.items():
                if k == 'none':
                    continue
                pg.evaluate("""([col, sh]) => { let t = document.getElementById('__ct'); if (t) t.remove();
                  t = document.createElement('div'); t.id = '__ct'; t.className = 'node tile'; t.style.cssText = `position:fixed;left:20px;top:20px;width:120px;height:52px;z-index:999;background:${col}`;
                  t.innerHTML = '<div class="lab" style="font-size:11px"><span class="nm">삼성전자우</span><span class="pc">+1.25%</span></div>';
                  if (sh === 'SM') t.firstChild.classList.add('sm'); else if (sh) t.firstChild.style.textShadow = sh; document.body.append(t); }""", [col, sh])
                pg.wait_for_timeout(80)
                png = pg.locator('#__ct .lab').screenshot()
                out[k] = ring_contrast(Image.open(io.BytesIO(png)))
            print(f"{label:28} {out['plain']:>6} {out['old']:>6} {out['new']:>7} {out['new<16px']:>7}")
        b.close()
