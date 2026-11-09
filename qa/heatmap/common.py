"""Shared helpers for the QA scripts (Playwright, Chrome)."""
import json
from playwright.sync_api import sync_playwright

import os
SNAP_URL = os.environ.get('SNAP_URL', 'file:///home/claude/hm-heatmap/dist/index.html')
LIVE_URL = 'http://127.0.0.1:8794/'
BUILDS = {'snapshot': SNAP_URL, 'live': LIVE_URL}
SHOTS = '/home/claude/hm-heatmap/qa/shots'

VIEWPORTS = {
    'm360': dict(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True, device_scale_factor=2),
    'm390': dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    't768': dict(viewport={'width': 768, 'height': 1024}),
    'd1280': dict(viewport={'width': 1280, 'height': 800}),
    'd1920': dict(viewport={'width': 1920, 'height': 1080}),
}


def launch(p):
    return p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])


class Log:
    def __init__(self):
        self.console, self.failed, self.reqs = [], [], []

    def attach(self, page):
        page.on('console', lambda m: self.console.append(f'{m.type}: {m.text}') if m.type in ('error', 'warning') else None)
        page.on('pageerror', lambda e: self.console.append(f'pageerror: {e}'))
        page.on('requestfailed', lambda r: self.failed.append(f'{r.url[:100]} {r.failure}'))
        page.on('response', lambda r: self.failed.append(f'HTTP {r.status} {r.url[:100]}') if r.status >= 400 else None)
        page.on('request', lambda r: self.reqs.append(r.url))


def new_page(browser, vp_key, url, storage_clear=True, extra=None, wait=1500):
    opts = dict(VIEWPORTS[vp_key])
    if extra:
        opts.update(extra)
    ctx = browser.new_context(**opts)
    page = ctx.new_page()
    log = Log()
    log.attach(page)
    page.goto(url)
    if storage_clear:
        page.evaluate("() => { for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); }")
        page.reload()
    page.wait_for_timeout(wait)
    return ctx, page, log


LABEL_CHECK_JS = r"""
() => {
  const out = [];
  let n = 0;
  for (const t of document.querySelectorAll('#map .tile')) {
    if (t.classList.contains('leaving')) continue;
    const lab = t.querySelector('.lab');
    if (!lab || lab.hidden || getComputedStyle(lab).display === 'none') continue;
    n++;
    const tr = t.getBoundingClientRect();
    const probs = [];
    if (lab.scrollWidth > lab.clientWidth + 1) probs.push(`lab.scrollW ${lab.scrollWidth}>${lab.clientWidth}`);
    for (const c of lab.children) {
      if (c.hidden || getComputedStyle(c).display === 'none') continue;
      const r = c.getBoundingClientRect();
      if (r.left < tr.left - 1 || r.right > tr.right + 1 || r.top < tr.top - 1 || r.bottom > tr.bottom + 1)
        probs.push(`${c.className.split(' ')[0]} [${r.left.toFixed(0)},${r.top.toFixed(0)},${r.right.toFixed(0)},${r.bottom.toFixed(0)}] tile [${tr.left.toFixed(0)},${tr.top.toFixed(0)},${tr.right.toFixed(0)},${tr.bottom.toFixed(0)}]`);
      if (c.scrollWidth > c.clientWidth + 1 && !c.classList.contains('ell')) probs.push(`${c.className.split(' ')[0]} scrollW ${c.scrollWidth}>${c.clientWidth}`);
    }
    // glyph-level: every text run's client rects must sit inside the tile (catches clipped descenders / hidden overflow)
    const tw = document.createTreeWalker(lab, NodeFilter.SHOW_TEXT);
    let tn;
    while ((tn = tw.nextNode())) {
      if (!tn.textContent.trim() || tn.parentElement.closest('[hidden]') || tn.parentElement.closest('.ell')) continue;
      const rg = document.createRange(); rg.selectNodeContents(tn);
      for (const rr of rg.getClientRects()) {
        if (rr.left < tr.left - 1 || rr.right > tr.right + 1 || rr.top < tr.top - 1.5 || rr.bottom > tr.bottom + 1.5)
          probs.push(`text '${tn.textContent}' [${rr.left.toFixed(1)},${rr.top.toFixed(1)},${rr.right.toFixed(1)},${rr.bottom.toFixed(1)}]`);
      }
    }
    if (probs.length) out.push({ c: t.dataset.c, name: t.querySelector('.nm').textContent, w: Math.round(tr.width), h: Math.round(tr.height), fs: lab.style.fontSize, probs });
  }
  return { visible: n, overflow: out.length, examples: out.slice(0, 6) };
}
"""

NODE_COUNT_JS = r"""
() => {
  const all = document.querySelectorAll('#map .node').length;
  const leaving = document.querySelectorAll('#map .node.leaving').length;
  const tiles = document.querySelectorAll('#map .tile:not(.leaving)').length;
  const secs = document.querySelectorAll('#map .sec:not(.leaving)').length;
  const inds = document.querySelectorAll('#map .ind:not(.leaving)').length;
  const stat = document.querySelector('#crumbs .stat');
  return { all, leaving, tiles, secs, inds, stat: stat ? stat.textContent : null };
}
"""


def dump(o):
    return json.dumps(o, ensure_ascii=False)
