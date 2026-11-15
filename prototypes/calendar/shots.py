"""증시 캘린더 시제품 스크린샷 + 간단 점검 (시제품 전용, 빌드와 무관).

    python3 -m http.server 8990 -d /home/claude/wt-cal &   # 저장소 뿌리(글꼴 경로 ../../src/fonts 때문)
    python3 prototypes/calendar/shots.py [base_url]
    fuser -k 8990/tcp

결과: qa/shots/calendar/*.png + qa/shots/calendar/check.json
점검: 콘솔 오류 · 가로 넘침 · 11px 미만 글자 · (휴대폰) 높이 40px 미만 버튼(가상 누름 영역 ::before는 따로 셈)
"""
import json, sys, pathlib
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8990') + '/prototypes/calendar/index.html'
OUT = pathlib.Path(__file__).resolve().parents[2] / 'qa' / 'shots' / 'calendar'
OUT.mkdir(parents=True, exist_ok=True)

SHOTS = [
    ('a-390', '?v=a', (390, 844)),
    ('a-390-detail', '?v=a&day=2026-11-19&open=c3', (390, 844)),
    ('a-1440', '?v=a&day=2026-11-19', (1440, 900)),
    ('a-1440-detail', '?v=a&day=2026-12-10&open=fomc-1209', (1440, 900)),
    ('b-390', '?v=b', (390, 844)),
    ('b-1440', '?v=b&scroll=0', (1440, 900)),
    ('c-390', '?v=c', (390, 844)),
    ('c-1440', '?v=c', (1440, 900)),
    ('a-360', '?v=a', (360, 780)),
]

CHECK_JS = r"""
() => {
  const de = document.documentElement;
  const over = de.scrollWidth - de.clientWidth;
  const small = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!el.childNodes.length) continue;
    const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (parseFloat(cs.fontSize) < 11) small.push(el.className + ' ' + cs.fontSize + ' ' + el.textContent.trim().slice(0, 20));
  }
  const tiny = [];
  if (innerWidth < 761) for (const b of document.querySelectorAll('button, a')) {
    const cs = getComputedStyle(b); if (cs.display === 'none' || b.closest('[hidden]')) continue;
    const r = b.getBoundingClientRect(); if (!r.width) continue;
    if (b.closest('.proto')) continue;                     // 시안 고르기 줄은 시제품 장치
    const pseudo = getComputedStyle(b, '::before').content !== 'none' && getComputedStyle(b, '::before').position === 'absolute';
    const hh = r.height + (pseudo ? 12 : 0), ww = r.width + (pseudo ? 12 : 0);
    if (hh < 44 || ww < 44) tiny.push((b.className || b.tagName) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + (pseudo ? '+12' : '') + ' ' + b.textContent.trim().slice(0, 12));
  }
  return { over, small: small.slice(0, 20), nSmall: small.length, tiny: tiny.slice(0, 30), nTiny: tiny.length };
}
"""

res = {}
with sync_playwright() as p:
    br = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    for name, q, (w, h) in SHOTS:
        ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if w < 800 else 1,
                             is_mobile=w < 800, has_touch=w < 800, locale='ko-KR', reduced_motion='reduce')
        pg = ctx.new_page()
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + q, wait_until='networkidle')
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / f'{name}.png'))
        chk = pg.evaluate(CHECK_JS)
        chk['console'] = errs
        res[name] = chk
        print(name, json.dumps({k: (v if k in ('over', 'nSmall', 'nTiny', 'console') else None) for k, v in chk.items() if k in ('over', 'nSmall', 'nTiny', 'console')}, ensure_ascii=False))
        ctx.close()
    br.close()
(OUT / 'check.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
