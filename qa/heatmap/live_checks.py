import sys, json, time; sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import *
with sync_playwright() as p:
    b = launch(p)
    # 2: first /api/quotes hangs forever -> aborted at ~8s, next poll scheduled (15s)
    ctx = b.new_context(**VIEWPORTS['d1280']); pg = ctx.new_page(); times = []; t0 = time.time()
    def route(r):
        times.append(round(time.time() - t0, 1))
        if len(times) <= 1: return   # never answered
        r.continue_()
    pg.route('**/api/quotes', route); pg.goto(LIVE_URL)
    pg.wait_for_timeout(8600); st = pg.evaluate("document.querySelector('#status .badge').textContent")
    print('2 after abort status badge:', st, 'requests', times)
    pg.wait_for_timeout(16000)
    print('2 PASS' if len(times) >= 2 else '2 FAIL', 'request times', times, 'badge', pg.evaluate("document.querySelector('#status .badge').textContent"))
    ctx.close()
    # 7: closed market status uses asOf; 16: empty search message
    ctx = b.new_context(**VIEWPORTS['d1280']); pg = ctx.new_page()
    body = json.loads(__import__('urllib.request').request.urlopen(LIVE_URL + 'api/quotes').read())
    body['marketStatus'] = {'KOSPI': 'CLOSE', 'KOSDAQ': 'CLOSE'}; body['afterHours'] = False; body['asOf'] = '2026-11-06T15:30:00+09:00'
    pg.route('**/api/quotes', lambda r: r.fulfill(json=body)); pg.goto(LIVE_URL); pg.wait_for_timeout(2500)
    txt = pg.evaluate("document.querySelector('#status .txt').textContent"); bd = pg.evaluate("document.querySelector('#status .badge').textContent")
    print('7', 'PASS' if '11월 6일' in txt and txt.endswith('기준') else 'FAIL', txt, '|', bd)
    pg.fill('#q', 'ㅋㅋㅋ없는종목'); pg.wait_for_timeout(300)
    m = pg.evaluate("document.querySelector('#sugg .empty').textContent")
    print('16', 'PASS' if '실시간 대상(시장별 시총 상위 300종목) 안에서만 찾을 수 있어요' in m else 'FAIL', m)
    ctx.close(); b.close()
