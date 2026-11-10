"""§3-11 watchlist groups: storage + migration, the KH.watch API, the ★관심 chips, the grouped treemap, the table column, the ☆ picker.
usage: groups3.py [snapshot|live] [section…]   sections: api, ui, map, table, picker, quality (default: all)"""
import sys, os, json
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
from common import launch, Log, LABEL_CHECK_JS, VIEWPORTS
from playwright.sync_api import sync_playwright
VIEWPORTS = dict(VIEWPORTS, d1440=dict(viewport={'width': 1440, 'height': 900}))
build = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ('snapshot', 'live') else 'snapshot'
WANT = set(a for a in sys.argv[1:] if a not in ('snapshot', 'live')) or {'api', 'ui', 'map', 'table', 'picker', 'quality'}
URL = 'http://127.0.0.1:%s/' % os.environ.get('HM_PORT', '8806') if build == 'live' else 'file:///home/claude/hm-heatmap/dist/index.html'
SHOTS = '/home/claude/hm-heatmap/qa/heatmap2/shots3/'
WAIT = 3500 if build == 'live' else 1300
res = []


def ok(item, cond, info=''):
    res.append(bool(cond))
    print(('PASS' if cond else 'FAIL'), item, '' if cond and len(str(info)) > 160 else info)


def errs(log): return [c for c in log.console if c.startswith('error') or c.startswith('pageerror')]


def fresh(b, vp, store=None, raw=None, hsh=''):
    """store: khm.* JSON values; raw: khm.* raw strings (to plant broken / old data)"""
    ctx = b.new_context(**VIEWPORTS[vp], service_workers='block')
    pg = ctx.new_page(); log = Log(); log.attach(pg)
    pg.goto(URL)
    js = "for (const k of Object.keys(localStorage)) if (k.startsWith('khm.')) localStorage.removeItem(k); sessionStorage.setItem('khm.intro', '1');"
    for k, v in (store or {}).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(json.dumps(v))});"
    for k, v in (raw or {}).items(): js += f"localStorage.setItem('khm.{k}', {json.dumps(v)});"
    pg.evaluate(js)
    pg.goto(URL + hsh); pg.reload(); pg.wait_for_timeout(WAIT)
    return ctx, pg, log


WG = lambda pg: pg.evaluate("JSON.parse(localStorage.getItem('khm.watchGroups'))")

with sync_playwright() as p:
    b = launch(p)

    if 'api' in WANT:
        # migration: the old flat list becomes "기본", the old key stays
        ctx, pg, log = fresh(b, 'd1280', store={'watch': ['005930', '000660', 'bad', '005930'], 'market': 'K'})
        w = WG(pg)
        ok('migration: khm.watch → group "기본" (deduplicated, bad codes dropped), active 전체, old key kept',
           w and w['v'] == 1 and len(w['groups']) == 1 and w['groups'][0]['name'] == '기본' and w['groups'][0]['codes'] == ['005930', '000660'] and w['active'] == 'all'
           and pg.evaluate("localStorage.getItem('khm.watch')") is not None, w)
        ok('old API keeps working: has / list / toggle', pg.evaluate("[KH.watch.has('005930'), KH.watch.list().join(','), KH.watch.toggle('035720'), KH.watch.has('035720'), KH.watch.list().length]") == [True, '005930,000660', True, True, 3])
        pg.evaluate("window.__ev = []; document.addEventListener('kh:watch', e => window.__ev.push(e.detail))")
        r = pg.evaluate("""() => { const W = KH.watch; const a = W.createGroup('반도체'), b2 = W.createGroup('  배당   좋은 종목들이에요 길다  '), same = W.createGroup('반도체');
          W.add('005930', a); W.add('000660', a); W.add('005930', b2);
          return { a, b2, same, groups: W.groups(), of: W.groupsOf('005930'), la: W.list(a), all: W.list(), ev: window.__ev.length, last: window.__ev.slice(-1)[0] }; }""")
        ok('createGroup → id; same name → same id; names trimmed to 12 chars; add to groups; groupsOf; list(gid) / list() union',
           r['a'] and r['same'] == r['a'] and [g['name'] for g in r['groups']] == ['기본', '반도체', '배당 좋은 종목들이에요'] and r['of'] == [r['groups'][0]['id'], r['a'], r['b2']]
           and r['la'] == ['005930', '000660'] and r['all'] == ['005930', '000660', '035720'] and r['groups'][1]['count'] == 2, r)
        ok("'kh:watch' fires per change with {codes, groups, active}", r['ev'] >= 5 and set(r['last']) >= {'codes', 'groups', 'active', 'list', 'code', 'on'} and len(r['last']['groups']) == 3, r['last'])
        r = pg.evaluate("""() => { const W = KH.watch, [g0, a, b2] = W.groups().map(g => g.id);
          const t1 = W.toggle('005930', b2), of1 = W.groupsOf('005930');                // off in that group only
          const t2 = W.toggle('005930'), had = W.has('005930');                           // no group: off everywhere
          const t3 = W.toggle('005930'), of3 = W.groupsOf('005930');                      // no group, 전체 shown → 기본
          W.setActive(a); const t4 = W.toggle('068270'), of4 = W.groupsOf('068270');      // → the shown group
          W.setGroups('068270', [g0, b2]); const of5 = W.groupsOf('068270');
          W.remove('068270', g0); const of6 = W.groupsOf('068270'); W.remove('068270'); const has6 = W.has('068270');
          return { t1, of1, t2, had, t3, of3, t4, of4, of5, of6, has6, ids: [g0, a, b2], act: W.active() }; }""")
        g0, a, b2 = r['ids']
        ok('toggle(code, gid) flips that group only; toggle(code) off → all groups, on → 기본 (전체) or the shown group',
           r['t1'] is False and r['of1'] == [g0, a] and r['t2'] is False and not r['had'] and r['t3'] is True and r['of3'] == [g0] and r['t4'] is True and r['of4'] == [a] and r['act'] == a, r)
        ok('setGroups exact; remove(code, gid) one group; remove(code) all', r['of5'] == [g0, b2] and r['of6'] == [b2] and r['has6'] is False, r)
        r = pg.evaluate("""() => { const W = KH.watch, [g0, a, b2] = W.groups().map(g => g.id);
          const rn = W.renameGroup(a, '메모리'), rnDup = W.renameGroup(b2, '메모리'), rnEmpty = W.renameGroup(b2, '   ');
          const mv = W.moveGroup(b2, 0), order = W.groups().map(g => g.name);
          W.add('051910', b2); W.add('247540', a); const del = W.deleteGroup(a);
          return { rn, rnDup, rnEmpty, mv, order, del, names: W.groups().map(g => g.name), has247: W.has('247540'), has660: W.has('000660'), has930: W.has('005930'), act: W.active(), saved: JSON.parse(localStorage.getItem('khm.watchGroups')) }; }""")
        ok('renameGroup (duplicate / empty refused), moveGroup, deleteGroup: its only-there codes leave, shown group falls back to 전체',
           r['rn'] and not r['rnDup'] and not r['rnEmpty'] and r['order'] == ['배당 좋은 종목들이에요', '기본', '메모리'] and r['del'] and r['names'] == ['배당 좋은 종목들이에요', '기본']
           and not r['has247'] and r['has660'] and r['has930'] and r['act'] == 'all' and [g['name'] for g in r['saved']['groups']] == r['names'], r)
        r = pg.evaluate("""() => { const W = KH.watch; let n = 0; for (let i = 0; i < 25; i++) if (W.createGroup('g' + i)) n++;
          const cnt = W.groups().length; for (const g of W.groups()) W.deleteGroup(g.id);
          return { n, cnt, left: W.groups().map(g => g.name + ':' + g.count), list: W.list() }; }""")
        ok('at most 20 groups; deleting every group leaves an empty "기본"', r['cnt'] == 20 and r['n'] == 18 and r['left'] == ['기본:0'] and r['list'] == [], r)
        ok('api: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # persistence + a broken store
        ctx, pg, log = fresh(b, 'd1280', store={'watchGroups': {'v': 1, 'active': 'gx', 'groups': [{'id': 'gx', 'name': '반도체', 'codes': ['005930', 'zz']}, {'id': 'gx', 'name': 'dup', 'codes': []}, {'id': 'gy', 'name': '', 'codes': ['000660']}]}})
        ok('a stored set loads cleaned (bad codes, duplicate ids, empty names dropped), active kept', pg.evaluate("[KH.watch.groups().map(g => g.name + ':' + g.count).join(','), KH.watch.active()]") == ['반도체:1', 'gx'])
        ctx.close()
        ctx, pg, log = fresh(b, 'd1280', raw={'watchGroups': '{oops', 'watch': '["000660"]'})
        ok('a broken khm.watchGroups → migrates khm.watch again, no console error', pg.evaluate("KH.watch.groups().map(g => g.name + ':' + g.count).join(',')") == '기본:1' and not errs(log), errs(log)[:2])
        ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed ({build})')
sys.exit(0 if all(res) else 1)
