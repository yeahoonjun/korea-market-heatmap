# python3 qa/calendar/test_long_value.py — 주 띠의 날을 하나씩 눌러 문서 · 줄의 가로 넘침이 0인지 (360 · 390)
import subprocess, time, sys
from playwright.sync_api import sync_playwright
P=8996   # 일정 탭: 긴 발표값이 있는 날도 가로 넘침 0 (사용자 2026-11-15 21:34 "이렇게 튀어나가는거 없게해줘")
srv=subprocess.Popen([sys.executable,'qa/calendar/mock_cal.py',str(P)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(2)
try:
  with sync_playwright() as p:
    br=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
    for w in (360,390):
      pg=br.new_page(viewport={'width':w,'height':800})
      pg.goto(f'http://127.0.0.1:{P}/#cal'); pg.wait_for_selector('#calendar .kc-ev',timeout=10000)
      # click every past weekday in the strip and measure
      res=[]
      btns=pg.locator('#calendar .kc-wk button')
      for i in range(btns.count()):
        btns.nth(i).click(); pg.wait_for_timeout(400)
        res.append(pg.evaluate("()=>[document.documentElement.scrollWidth-document.documentElement.clientWidth, document.querySelectorAll('#calendar .kc-ev .val').length, Math.max(0,...[...document.querySelectorAll('#calendar .kc-ev')].map(e=>e.scrollWidth-e.clientWidth))]"))
      print(w,res); bad=[r for r in res if r[0]>0 or r[2]>0]; assert not bad, (w, bad)
    br.close()
finally:
  srv.kill()
