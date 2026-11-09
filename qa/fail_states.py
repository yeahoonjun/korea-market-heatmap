import sys, time, urllib.request; sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *
H = 'http://127.0.0.1:8790/'
setmode = lambda m: urllib.request.build_opener(urllib.request.ProxyHandler({})).open(H + '__mode/' + m).read()
force_poll = lambda pg: pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
def st(pg):
    return dict(status=pg.inner_text('#status').replace('\n', ' | '), cls=pg.get_attribute('#status', 'class'),
                badge_title=pg.get_attribute('#status .badge', 'title'),
                empty=pg.evaluate("(()=>{const e=document.querySelector('.map-empty');return e?e.textContent:null})()"),
                tiles=pg.evaluate("document.querySelectorAll('#map .tile').length"),
                foot=pg.inner_text('#foot')[-80:].replace('\n', ' '))
with sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={'width': 1280, 'height': 800}); pg = ctx.new_page(); log = Log(); log.attach(pg)
    quotes = []
    pg.on('request', lambda r: quotes.append((round(time.time()), r.url[-12:])) if 'api/quotes' in r.url else None)
    setmode('err'); pg.goto(H); pg.wait_for_timeout(2500)
    print('1 initial load, API 502:', dump(st(pg)))
    setmode('ok'); pg.wait_for_timeout(16000)
    print('2 after 16s auto-retry with API ok:', dump(st(pg)))
    setmode('err'); force_poll(pg); pg.wait_for_timeout(2500)
    print('3 API fails while data shown:', dump(st(pg)))
    setmode('empty'); force_poll(pg); pg.wait_for_timeout(2500)
    print('4 API returns empty stocks:', dump(st(pg)))
    setmode('holiday'); force_poll(pg); pg.wait_for_timeout(3500)
    print('5 holiday/closed (asOf = Fri 11/06):', dump(st(pg)))
    setmode('open'); force_poll(pg); pg.wait_for_timeout(3500)
    print('6 regular session open:', dump(st(pg)))
    setmode('charterr'); pg.click('#map .tile >> nth=0'); pg.wait_for_timeout(2000)
    print('7 chart API error note:', pg.evaluate("(()=>{const s=document.querySelector('#spark');return s&&s.innerText})()"))
    pg.keyboard.press('Escape')
    setmode('hang'); n0 = len(quotes); force_poll(pg); pg.wait_for_timeout(1500); setmode('ok')
    pg.wait_for_timeout(75000)
    print('8 one hung /api/quotes request, then API ok for 75 s -> new quote requests:', len(quotes) - n0 - 1, '| status:', dump(st(pg)['status']))
    print('console:', log.console[:8])
    ctx.close(); b.close()
