#!/usr/bin/env python3
"""Record test fixtures for the 해외 · 원자재 tabs (src/world) from the real Worker (AGENTS.md §3-4 shapes).

  qa/world/fixtures/world_index.json       /api/world?kind=index
  qa/world/fixtures/world_commodity.json   /api/world?kind=commodity
  qa/world/fixtures/charts.json            {key: [[YYYY-MM-DD, close], …]}  /api/world/chart/{key}?tf=1y for CHART_KEYS
                                           (3m = last 3 months of it; mock_api.py synthesises the other keys)
  qa/world/fixtures/world_macro.json       --macro: only the 환율 · 금리 groups of /api/world?kind=commodity&with=fx,rates (AGENTS §3-28)
                                           and their MACRO_CHART_KEYS charts merged into charts.json (the other fixtures stay as they are)

Run the local Worker first, then record:
  NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8803/ PORT=8802 node worker/dev/serve.mjs &
  python3 qa/world/make_fixtures.py [http://127.0.0.1:8802] [--macro]
"""
import concurrent.futures as cf
import json
import pathlib
import sys
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent / 'fixtures'
OUT.mkdir(exist_ok=True)
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
BASE = (ARGS[0] if ARGS else 'http://127.0.0.1:8802').rstrip('/')
MACRO_CHART_KEYS = {'FX_USDKRW', 'DXY', 'USDJPY', 'KR3YT', 'US10YT', 'JP10YT'}
CHART_KEYS = {'INX', 'IXIC', 'DJI', 'N225', 'HSI', 'GDAXI', 'KOSPI', 'VIX', 'EScv1', 'CLcv1', 'GCcv1', 'Ccv1'}
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path):
    with NOPROXY.open(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def chart(key):
    try:
        j = get(f'/api/world/chart/{key}?tf=1y')
        return key, [[b['t'], b['c']] for b in j.get('bars') or []]
    except Exception as e:  # a missing chart is a valid case for the module (no chart shown)
        print('chart fail', key, e, file=sys.stderr)
        return key, None


def macro():
    j = get('/api/world?kind=commodity&with=fx,rates')
    groups = [g for g in j['groups'] if g['key'] in ('fx', 'rates')]
    (OUT / 'world_macro.json').write_text(json.dumps({'asOf': j['asOf'], 'kind': 'commodity', 'groups': groups}, ensure_ascii=False, indent=1), encoding='utf-8')
    path = OUT / 'charts.json'
    ch = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    keys = [it['key'] for g in groups for it in g['items'] if it['key'] in MACRO_CHART_KEYS]
    with cf.ThreadPoolExecutor(6) as ex:
        ch.update({k: v for k, v in ex.map(chart, keys) if v})
    path.write_text(json.dumps(ch, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('macro groups', [(g['key'], len(g['items'])) for g in groups], 'charts', len(keys))


if __name__ == '__main__':
    if '--macro' in sys.argv:
        macro()
        sys.exit(0)
    idx, com = get('/api/world?kind=index'), get('/api/world?kind=commodity')
    (OUT / 'world_index.json').write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'world_commodity.json').write_text(json.dumps(com, ensure_ascii=False, indent=1), encoding='utf-8')
    keys = [it['key'] for p in (idx, com) for g in p['groups'] for it in g['items'] if it['key'] in CHART_KEYS]
    with cf.ThreadPoolExecutor(6) as ex:
        ch = {k: v for k, v in ex.map(chart, keys) if v}
    (OUT / 'charts.json').write_text(json.dumps(ch, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('index items', sum(len(g['items']) for g in idx['groups']), 'commodity items', sum(len(g['items']) for g in com['groups']),
          'charts', len(ch), 'of', len(keys))
