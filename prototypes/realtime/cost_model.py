#!/usr/bin/env python3
"""Monthly cost / volume model behind docs/standards/realtime.md §3 (run: python3 prototypes/realtime/cost_model.py).

Prices: Cloudflare Workers Paid + Durable Objects pricing pages, both "Last updated Nov 13, 2026" (read 2026-11-14).
Exchange rate: 1 USD = 1,337.8 KRW (원/달러, 2026-11-13 종가 — 네이버 증권 via 판세 /api/market), rounded to 1,340.
Every assumption is a named constant below; change one and re-run.
"""
KRW = 1340
SESSION_S = 6.5 * 3600 * 21                 # regular session × trading days per month = 491,400 s
# Workers Paid ($5/month minimum)
W_INCL_REQ, W_REQ = 10e6, 0.30              # requests included / USD per extra million
W_INCL_CPU, W_CPU = 30e6, 0.02              # CPU ms included / USD per extra million ms
# Durable Objects (Workers Paid)
D_INCL_REQ, D_REQ = 1e6, 0.15               # requests (HTTP, RPC, alarms, WS connects, incoming WS msgs ÷ 20)
D_INCL_GBS, D_GBS = 400e3, 12.50            # duration GB-s at 128 MB per object
# assumptions (not measured in production — marked as such in the doc)
OTHER_PER_MIN = 4.5                         # other polling per viewer, unchanged by every option: 지수 띠 30 s, 등락 분포 60 s, 공시 60 s, 뉴스 3 min
CPU_MS_PER_REQ = 1.0                        # average Worker CPU per request (almost all are edge-cache hits)
WS_CONNECTS_PER_HOUR = 4                    # reconnects per viewer-hour (tab switches, phone networks, deploys)
HUB_AWAKE = 1.0                             # share of the session the hub is billed as active (worst case; ~0.5 with alarms)
QUOTES_GZIP_KB = 37                         # /api/quotes (600 rows) gzip, measured 2026-11-14
SNAP_KB = 31                                # WebSocket snapshot, permessage-deflate, measured (prototype)
WS_KB_PER_MIN = (16, 110, 143)              # prototype deltas at 3 s: replay-only / churn 0.3 / churn 1.0 (§8)

def bill(worker_req, do_req=0, gbs=0):
    usd = 5.0
    usd += max(0, worker_req - W_INCL_REQ) / 1e6 * W_REQ
    usd += max(0, worker_req * CPU_MS_PER_REQ - W_INCL_CPU) / 1e6 * W_CPU
    usd += max(0, do_req - D_INCL_REQ) / 1e6 * D_REQ
    usd += max(0, gbs - D_INCL_GBS) / 1e6 * D_GBS
    return usd

def options():
    other = OTHER_PER_MIN * SESSION_S / 60
    hub_gbs = HUB_AWAKE * SESSION_S * 0.125
    return [
        # name, worker req per viewer-month, fixed DO req, DO req per viewer, DO GB-s, naver calls/month, MB per viewer-hour
        ('현재: 10초 폴링 · 엣지 8초', SESSION_S / 10 + other, 0, 0, 0, f'{SESSION_S / 8:,.0f} × 데이터센터 수', f'{QUOTES_GZIP_KB * 360 / 1024:.1f}'),
        ('A: 5초 폴링 · 엣지 3초', SESSION_S / 5 + other, 0, 0, 0, f'{SESSION_S / 3:,.0f} × 데이터센터 수', f'{QUOTES_GZIP_KB * 720 / 1024:.1f}'),
        ('A′: 3초 폴링 · 엣지 2초', SESSION_S / 3 + other, 0, 0, 0, f'{SESSION_S / 2:,.0f} × 데이터센터 수', f'{QUOTES_GZIP_KB * 1200 / 1024:.1f}'),
        ('B/D: DO 3초 + WebSocket', WS_CONNECTS_PER_HOUR * SESSION_S / 3600 + other, SESSION_S / 3, WS_CONNECTS_PER_HOUR * SESSION_S / 3600, hub_gbs, f'{SESSION_S / 3:,.0f} (전체에서 1곳)', f'{WS_KB_PER_MIN[0] * 60 / 1024:.1f}~{WS_KB_PER_MIN[2] * 60 / 1024:.1f}'),
        ('B/D: DO 5초 + WebSocket', WS_CONNECTS_PER_HOUR * SESSION_S / 3600 + other, SESSION_S / 5, WS_CONNECTS_PER_HOUR * SESSION_S / 3600, hub_gbs, f'{SESSION_S / 5:,.0f} (전체에서 1곳)', '0.6~5.2'),
    ]

if __name__ == '__main__':
    print(f'세션 {SESSION_S:,.0f}초/월 · 1 USD = {KRW:,}원 · 허브 duration {HUB_AWAKE * SESSION_S * 0.125:,.0f} GB-s (포함 {D_INCL_GBS:,.0f})\n')
    print('| 방식 | 동시 20명 | 동시 200명 | 동시 2,000명 | 네이버 호출/월 (시세) | 휴대폰 데이터 MB/시간 |')
    print('|---|---|---|---|---|---|')
    for name, wpv, dfix, dpv, gbs, naver, mb in options():
        cells = []
        for c in (20, 200, 2000):
            wr = wpv * c
            dr = dfix + dpv * c
            usd = bill(wr, dr, gbs)
            cells.append(f'₩{usd * KRW:,.0f} (${usd:.2f}) · Worker {wr / 1e6:.1f}M' + (f' · DO {dr / 1e6:.2f}M' if dr else ''))
        print(f'| {name} | ' + ' | '.join(cells) + f' | {naver} | {mb} |')
