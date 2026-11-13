#!/usr/bin/env python3
"""Measure how fresh Naver's polling endpoint really is (docs/standards/realtime.md §1).

The page can never be fresher than this upstream, so before choosing a push cadence we need:
  * Naver's own hint (`pollingInterval`) and server clock (`time`) per answer,
  * how often the *content* changes between two polls (is there a server-side cache?),
  * lag = answer `time` − newest `localTradedAt` among the rows,
  * share of rows whose price / volume / NXT price moved between two polls (→ delta size),
  * response size (wire gzip / raw) and latency.

Polite by design: one request per --interval seconds (default 10, minimum 1), stops after --duration seconds.
Run it during market hours (Mon–Fri 09:00–15:30 KST) to get real numbers; outside them everything is static.

  python3 prototypes/realtime/measure_upstream.py                       # KOSPI top 300, every 10 s for 120 s
  python3 prototypes/realtime/measure_upstream.py --codes K+Q --interval 2 --duration 120 --pair
      --pair  every 5th sample sends two requests at once: identical `time` + body ⇒ a shared upstream cache

Codes come from web/universe.json (K/Q = top 300 per market). No secrets, no state written except --out.
"""
import argparse, gzip, hashlib, json, statistics, sys, threading, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
UA = 'Mozilla/5.0 (compatible; panse-measure/1.0; +https://panse.pages.dev)'
URL = 'https://polling.finance.naver.com/api/realtime/domestic/stock/'


def universe(which):
    u = json.loads((ROOT / 'web/universe.json').read_text())
    out = []
    for m in which.split('+'):
        s = u[m]
        out += [s[i:i + 6] for i in range(0, len(s), 8)]
    return out


def fetch(codes):
    req = urllib.request.Request(URL + ','.join(codes), headers={'user-agent': UA, 'accept': 'application/json', 'accept-encoding': 'gzip'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=20) as r:
        wire = r.read()
        headers = dict(r.headers.items())
    t1 = time.time()
    raw = gzip.decompress(wire) if headers.get('Content-Encoding', headers.get('content-encoding', '')) == 'gzip' else wire
    return {'t0': t0, 'ms': round((t1 - t0) * 1000), 'wire': len(wire), 'raw': len(raw), 'headers': headers, 'body': json.loads(raw)}


def row_sig(d):
    nx = d.get('overMarketPriceInfo') or {}
    return (d.get('closePriceRaw'), d.get('accumulatedTradingVolumeRaw'), d.get('localTradedAt'), nx.get('overPrice'), nx.get('localTradedAt'))


def parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def summarize_sample(res, prev_rows):
    b = res['body']
    datas = b.get('datas') or []
    rows = {d['itemCode']: row_sig(d) for d in datas}
    newest = max((parse_ts(d.get('localTradedAt')) for d in datas if d.get('localTradedAt')), default=None, key=lambda x: x or datetime.min.replace(tzinfo=KST))
    srv = datetime.strptime(b['time'], '%Y%m%d%H%M%S').replace(tzinfo=KST) if b.get('time') else None
    content = hashlib.sha1(json.dumps(datas, sort_keys=True).encode()).hexdigest()[:12]
    out = {
        'at': datetime.fromtimestamp(res['t0'], KST).strftime('%H:%M:%S'),
        'ms': res['ms'], 'wire': res['wire'], 'raw': res['raw'], 'rows': len(datas),
        'pollingInterval': b.get('pollingInterval'), 'time': b.get('time'),
        'newestTrade': newest.isoformat() if newest else None,
        'lagS': round((srv - newest).total_seconds(), 1) if srv and newest else None,
        'content': content,
        'status': sorted({d.get('marketStatus') for d in datas}),
    }
    if prev_rows is not None:
        out['changedRows'] = sum(1 for c, s in rows.items() if prev_rows.get(c) != s)
        out['changedPrice'] = sum(1 for c, s in rows.items() if prev_rows.get(c) and prev_rows[c][0] != s[0])
        out['changedNxt'] = sum(1 for c, s in rows.items() if prev_rows.get(c) and prev_rows[c][3] != s[3])
    return out, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='K', help="K, Q or K+Q (top 300 per market from web/universe.json)")
    ap.add_argument('--interval', type=float, default=10.0)
    ap.add_argument('--duration', type=float, default=120.0)
    ap.add_argument('--pair', action='store_true', help='every 5th sample: two simultaneous requests (shared-cache check)')
    ap.add_argument('--out', default='', help='write samples as JSON lines here')
    a = ap.parse_args()
    a.interval = max(1.0, a.interval)
    codes = universe(a.codes)
    print(f'{len(codes)} codes ({a.codes}), every {a.interval:g} s for {a.duration:g} s — {datetime.now(KST):%Y-%m-%d %H:%M:%S} KST', flush=True)
    samples, prev, n, end = [], None, 0, time.time() + a.duration
    out = open(a.out, 'w') if a.out else None
    while time.time() < end:
        start = time.time()
        try:
            res = fetch(codes)
        except Exception as e:
            print('error', e, flush=True)
            time.sleep(a.interval)
            continue
        if n == 0:
            h = {k.lower(): v for k, v in res['headers'].items()}
            print('headers:', json.dumps({k: h[k] for k in sorted(h) if k in ('cache-control', 'age', 'etag', 'last-modified', 'expires', 'vary', 'server', 'content-encoding', 'x-cache', 'via', 'date', 'pragma')}), flush=True)
        s, rows = summarize_sample(res, prev)
        if a.pair and n % 5 == 4:
            box = []
            th = [threading.Thread(target=lambda: box.append(fetch(codes))) for _ in range(2)]
            [t.start() for t in th]; [t.join() for t in th]
            if len(box) == 2:
                same_time = box[0]['body'].get('time') == box[1]['body'].get('time')
                same_body = json.dumps(box[0]['body'].get('datas'), sort_keys=True) == json.dumps(box[1]['body'].get('datas'), sort_keys=True)
                s['pair'] = {'sameTime': same_time, 'sameBody': same_body}
        samples.append(s)
        print(json.dumps(s, ensure_ascii=False), flush=True)
        if out: out.write(json.dumps(s, ensure_ascii=False) + '\n')
        prev, n = rows, n + 1
        time.sleep(max(0.0, a.interval - (time.time() - start)))
    if not samples:
        return 1
    ch = [s for s in samples[1:]]
    times = [s['time'] for s in samples]
    summary = {
        'samples': len(samples),
        'latencyMsMedian': statistics.median(s['ms'] for s in samples),
        'wireBytesMedian': statistics.median(s['wire'] for s in samples),
        'rawBytesMedian': statistics.median(s['raw'] for s in samples),
        'pollingInterval': sorted({s['pollingInterval'] for s in samples}),
        'serverTimeAdvancesEveryPoll': all(a != b for a, b in zip(times, times[1:])),
        'pollsWithNewContent': f"{sum(1 for x, y in zip(samples, samples[1:]) if x['content'] != y['content'])}/{len(samples) - 1}",
        'changedRowsMedian': statistics.median(s['changedRows'] for s in ch) if ch else None,
        'changedPriceMedian': statistics.median(s['changedPrice'] for s in ch) if ch else None,
        'lagSMedian': statistics.median(s['lagS'] for s in samples if s['lagS'] is not None) if any(s['lagS'] is not None for s in samples) else None,
        'marketStatus': sorted({x for s in samples for x in s['status'] if x}),
    }
    print('summary:', json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
