"""§3-16 screenshots: header region (and full page) per viewport, live + snapshot. Usage: shots.py TAG [vps] [builds]"""
import json, sys
sys.path.insert(0, '/home/claude/hm-tabs/qa')
from common import launch, VIEWPORTS
from playwright.sync_api import sync_playwright

URLS = {'live': 'http://127.0.0.1:8812/', 'snapshot': 'file:///home/claude/hm-tabs/dist/index.html'}
OUT = '/home/claude/hm-tabs/qa/tabs/shots'
GROUPS = {"v": 1, "groups": [{"id": "g0", "name": "기본", "codes": ["005930", "000660", "035420", "005380", "247540"]},
                             {"id": "gsemi", "name": "반도체", "codes": ["005930", "000660", "042700", "403870", "058470"]}], "active": "all"}

def main(tag, vps, builds, hashes=('#kospi',)):
    import os; os.makedirs(OUT, exist_ok=True)
    res = []
    with sync_playwright() as p:
        b = launch(p)
        for bk in builds:
            for vk in vps:
                for hs in hashes:
                    ctx = b.new_context(**VIEWPORTS[vk]); pg = ctx.new_page(); errs = []
                    pg.on('pageerror', lambda e: errs.append(str(e)))
                    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
                    pg.goto(URLS[bk])
                    pg.evaluate("g => { localStorage.setItem('khm.watchGroups', JSON.stringify(g)); }", GROUPS)
                    pg.goto(URLS[bk] + hs); pg.reload(); pg.wait_for_timeout(2800)
                    w = VIEWPORTS[vk]['viewport']['width']
                    name = f"{OUT}/{tag}-{bk}-{vk}-{hs.strip('#')}.png"
                    pg.screenshot(path=name, clip={'x': 0, 'y': 0, 'width': w, 'height': 260})
                    m = pg.evaluate("() => ({mapTop: Math.round(document.querySelector('#map').getBoundingClientRect().top + scrollY), ov: document.documentElement.scrollWidth - innerWidth})")
                    res.append(dict(build=bk, vp=vk, hash=hs, shot=name, errors=errs[:3], **m))
                    ctx.close()
        b.close()
    for r in res: print(json.dumps(r, ensure_ascii=False))

if __name__ == '__main__':
    tag = sys.argv[1]
    vps = sys.argv[2].split(',') if len(sys.argv) > 2 else ['m390', 'd1280']
    builds = sys.argv[3].split(',') if len(sys.argv) > 3 else ['live']
    hashes = sys.argv[4].split(',') if len(sys.argv) > 4 else ['#kospi']
    main(tag, vps, builds, hashes)
