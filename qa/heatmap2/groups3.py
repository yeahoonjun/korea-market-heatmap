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


    G3 = {'v': 1, 'active': 'all', 'groups': [{'id': 'g0', 'name': '기본', 'codes': ['005930', '035420', '005380', '068270']},
          {'id': 'g1', 'name': '반도체', 'codes': ['005930', '000660', '042700', '403870']}, {'id': 'g2', 'name': '배당', 'codes': ['105560', '055550', '086790', '033780']}]}
    CHIPS = "[...document.querySelectorAll('#wgchips .wgc')].map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : ''))"
    POP = "(() => { const p = document.getElementById('wgpop'); return p.hidden ? null : { title: p.querySelector('h3')?.textContent, rows: [...p.querySelectorAll('.row')].map(r => r.textContent + (r.disabled ? '(off)' : '')), msg: p.querySelector('.msg')?.textContent, boxes: [...p.querySelectorAll('input[type=checkbox]')].map(x => x.checked), focus: p.contains(document.activeElement) }; })()"

    if 'ui' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'watchGroups': G3, 'market': 'K'})
        ok('chips only on ★관심: hidden on 코스피', pg.evaluate("document.getElementById('wgbar').hidden") is True)
        pg.click('.tabs button[data-mkt="WATCH"]'); pg.wait_for_timeout(500)
        ok('★관심: chips 전체 · 기본 · 반도체 · 배당 · ＋ with counts, 전체 pressed', pg.evaluate(CHIPS) == ['전체11*', '기본4', '반도체4', '배당4'] and pg.evaluate("!!document.querySelector('#wgchips .wgadd')"), pg.evaluate(CHIPS))
        pg.click('#wgchips .wgc[data-g="g1"]'); pg.wait_for_timeout(500)
        r = pg.evaluate("({act: KH.watch.active(), crumbs: document.getElementById('crumbs').innerText.replace(/\\s+/g, ' '), tiles: [...new Set([...document.querySelectorAll('#map .tile')].map(t => t.dataset.c))].sort(), stored: JSON.parse(localStorage.getItem('khm.watchGroups')).active, menu: !!document.querySelector('#wgchips [data-gm=\"g1\"]')})")
        ok('chip 반도체 → that group only (tiles), crumbs "관심종목 › 반도체", stored active, ⋯ on its chip',
           r['act'] == 'g1' and r['stored'] == 'g1' and r['crumbs'].startswith('관심종목 › 반도체') and set(r['tiles']) <= {'005930', '000660', '042700', '403870'} and len(r['tiles']) >= 2 and r['menu'], r)
        pg.reload(); pg.wait_for_timeout(WAIT)
        ok('reload keeps the tab and the group', pg.evaluate("[KH.market(), KH.watch.active()]") == ['watch', 'g1'])
        # ⋯ menu → rename (duplicate refused, then a new name), focus back on the chip
        pg.click('#wgchips [data-gm="g1"]'); pg.wait_for_timeout(200)
        m = pg.evaluate(POP)
        ok('⋯ opens the menu: 이름 바꾸기 · 앞으로 · 뒤로 · (§3-16 탭에 이 그룹 등락률 표시) · 그룹 지우기…, focus inside',
           m and [r for r in m['rows'] if not r.startswith('탭에 ')] == ['이름 바꾸기', '앞으로 옮기기', '뒤로 옮기기', '그룹 지우기…'] and m['focus'], m)
        pg.click('#wgpop .row:has-text("이름 바꾸기")'); pg.wait_for_timeout(150)
        pg.fill('#wgpop input[type=text]', '배당'); pg.wait_for_timeout(100)
        d = pg.evaluate("({msg: document.querySelector('#wgpop .msg').textContent, dis: document.querySelector('#wgpop .pri').disabled})")
        pg.fill('#wgpop input[type=text]', '메모리'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
        ok('rename: a taken name is refused ("같은 이름의 그룹이 있어요"), Enter renames, focus back on the chip',
           d == {'msg': '같은 이름의 그룹이 있어요', 'dis': True} and pg.evaluate(CHIPS)[2] == '메모리4*' and pg.evaluate("document.activeElement.dataset.g") == 'g1' and pg.evaluate(POP) is None, (d, pg.evaluate(CHIPS)))
        pg.click('#wgchips [data-gm="g1"]'); pg.wait_for_timeout(150); pg.click('#wgpop .row:has-text("앞으로 옮기기")'); pg.wait_for_timeout(300)
        ok('앞으로 옮기기 → order 메모리 · 기본 · 배당', [g['name'] for g in pg.evaluate("KH.watch.groups()")] == ['메모리', '기본', '배당'], pg.evaluate(CHIPS))
        # Esc closes and returns focus
        pg.click('#wgchips [data-gm="g1"]'); pg.wait_for_timeout(150); pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        ok('Esc closes the menu, focus back on ⋯', pg.evaluate(POP) is None and pg.evaluate("document.activeElement.dataset.gm") == 'g1')
        # ＋ → new group (shown, empty hint), then 전체
        pg.click('#wgchips .wgadd'); pg.wait_for_timeout(150); pg.fill('#wgpop input[type=text]', '  신규   그룹  '); pg.click('#wgpop .pri'); pg.wait_for_timeout(500)
        e = pg.evaluate("({act: KH.watch.groups().find(g => g.id === KH.watch.active())?.name, hint: document.querySelector('#map .map-empty')?.innerText})")
        ok("＋ → '신규 그룹' created and shown; empty hint '…☆나 검색에서 이 그룹에 담을 수 있어요'", e['act'] == '신규 그룹' and e['hint'] and '이 그룹에 담을 수 있어요' in e['hint'], e)
        pg.click('#map .map-empty button'); pg.wait_for_timeout(400)
        ok("hint's button → 전체", pg.evaluate("KH.watch.active()") == 'all')
        # delete with the question (codes only in that group leave)
        pg.click('#wgchips .wgc[data-g="g2"]'); pg.wait_for_timeout(300)
        pg.click('#wgchips [data-gm="g2"]'); pg.wait_for_timeout(150); pg.click('#wgpop .row:has-text("그룹 지우기")'); pg.wait_for_timeout(150)
        q = pg.evaluate(POP)
        pg.click('#wgpop .pri'); pg.wait_for_timeout(400)
        ok("delete asks first ('배당' 그룹을 지울까요? · 다른 그룹에 없는 4종목은 관심종목에서 빠져요), then the group and its 4 stocks go, 전체 shown",
           q and q['title'] == "'배당' 그룹을 지울까요?" and '4종목' in q['msg'] and [g['name'] for g in pg.evaluate("KH.watch.groups()")] == ['메모리', '기본', '신규 그룹'] and not pg.evaluate("KH.watch.has('105560')") and pg.evaluate("KH.watch.active()") == 'all', q)
        ok('ui: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        # phones: long press opens the menu as a bottom sheet; chips ≥ 40 px
        ctx, pg, log = fresh(b, 'm390', store={'watchGroups': G3}, hsh='#watch')
        pg.evaluate("""() => { const b = document.querySelector('#wgchips .wgc[data-g="g2"]'); b.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, pointerType: 'touch'})); }""")
        pg.wait_for_timeout(750)
        m = pg.evaluate(POP); box = pg.evaluate("(() => { const r = document.getElementById('wgpop').getBoundingClientRect(); return [Math.round(r.left), Math.round(innerWidth - r.right), Math.round(innerHeight - r.bottom)]; })()")
        sz = pg.evaluate("[...document.querySelectorAll('#wgchips button')].map(b => Math.round(b.getBoundingClientRect().height))")
        ok(f'm390: long press → the menu as a bottom sheet {box}; chip buttons ≥ 40 px {sorted(set(sz))}', m and m['title'] == '배당' and box[0] == 8 and box[1] == 8 and box[2] <= 12 and min(sz) >= 40, (m, box, sz))
        ctx.close()

    if 'map' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'watchGroups': G3}, hsh='#watch')
        L = pg.evaluate("KH.layout()")
        secs = [n['label'] for n in L if n['kind'] == 'sector']
        tiles = [n['code'] for n in L if n['kind'] == 'tile']
        lab = pg.evaluate(LABEL_CHECK_JS)
        ok(f'전체: the top blocks are the groups {secs}; 삼성전자 shows in 기본 and 반도체 (2 tiles); no industry blocks; labels inside',
           set(secs) == {'기본', '반도체', '배당'} and tiles.count('005930') == 2 and not [n for n in L if n['kind'] == 'ind'] and lab['overflow'] == 0, (secs, tiles.count('005930'), lab['examples'][:1]))
        # hover one of the two: both light up, the ☆ sits on the hovered one
        els = pg.query_selector_all('#map .tile[data-c="005930"]')
        bb = els[1].bounding_box(); pg.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2); pg.wait_for_timeout(200)
        r = pg.evaluate("""(() => { const t = [...document.querySelectorAll('#map .tile[data-c="005930"]')], s = document.querySelector('.tstar').getBoundingClientRect(), r1 = t[1].getBoundingClientRect();
          return { hov: t.map(x => x.classList.contains('hov')), starIn: s.left >= r1.left && s.right <= r1.right + 1 && s.top >= r1.top - 1 && s.bottom <= r1.bottom }; })()""")
        ok("a stock in two groups: hovering one lights both, the ☆ sits on the hovered tile", r['hov'] == [True, True] and r['starIn'], r)
        pg.mouse.move(5, 5)
        pg.click('#map .grp[data-g="g2"] .hd'); pg.wait_for_timeout(500)
        L2 = pg.evaluate("KH.layout()")
        ok("a group's header → that group: sector › industry blocks, its stocks only", pg.evaluate("KH.watch.active()") == 'g2' and any(n['kind'] == 'ind' for n in L2) and {n['code'] for n in L2 if n['kind'] == 'tile'} <= {'105560', '055550', '086790', '033780'}, [n['label'] for n in L2 if n['kind'] != 'tile'])
        ok('map: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        ctx, pg, log = fresh(b, 'd1440', store={'watch': ['005930', '000660', '105560']}, hsh='#watch')
        L = pg.evaluate("KH.layout()")
        ok('one group ("기본" from khm.watch): no group blocks — sectors as before', not any(n['label'] == '기본' for n in L) and any(n['kind'] == 'sector' for n in L) and pg.evaluate("document.querySelectorAll('#wgchips .wgc').length") == 2, [n['label'] for n in L if n['kind'] == 'sector'])
        ctx.close()

    if 'table' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'watchGroups': G3, 'view': 'table'}, hsh='#watch')
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("({head: [...document.querySelectorAll('#tablewrap thead th')].map(t => t.dataset.k), ss: document.querySelector('#tablewrap tr[data-c=\"005930\"] td.k-g')?.textContent})")
        ok("table: 그룹 column after 종목; 삼성전자 '기본, 반도체'", r['head'][:2] == ['n', 'g'] and r['ss'] == '기본, 반도체', r)
        pg.click('#tablewrap th[data-k="g"] button'); pg.wait_for_timeout(300)
        o = pg.evaluate("[...document.querySelectorAll('#tablewrap tbody tr')].map(tr => tr.querySelector('td.k-g').textContent.split(', ')[0])")
        ok('sort by 그룹 (▴ group order): 기본 rows first, 배당 last', o and o[0] == '기본' and o[-1] == '배당' and o == sorted(o, key=['기본', '반도체', '배당'].index), o)
        ctx.close()
        ctx, pg, log = fresh(b, 'm390', store={'watchGroups': G3}, hsh='#watch')
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        r = pg.evaluate("({g: getComputedStyle(document.querySelector('#tablewrap th.k-g')).display, over: document.getElementById('tablewrap').scrollWidth - document.getElementById('tablewrap').clientWidth, page: document.documentElement.scrollWidth - innerWidth})")
        ok('m390 table: 그룹 column hidden, nothing sideways', r == {'g': 'none', 'over': 0, 'page': 0}, r)
        ctx.close()

    if 'picker' in WANT:
        ctx, pg, log = fresh(b, 'd1440', store={'watchGroups': G3, 'market': 'K'})
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        pg.click('#tablewrap button[data-w="005930"]'); pg.wait_for_timeout(200)
        m = pg.evaluate(POP)
        ok("☆ with 3 groups → picker '삼성전자 · 관심 그룹', boxes [기본 ✓, 반도체 ✓, 배당 ✗], + 새 그룹에 담기", m and m['title'] == '삼성전자 · 관심 그룹' and m['boxes'] == [True, True, False] and '＋ 새 그룹에 담기' in m['rows'], m)
        pg.click('#wgpop label.row:has-text("반도체") input'); pg.click('#wgpop label.row:has-text("배당") input'); pg.wait_for_timeout(200)
        ok('ticks apply at once: groupsOf 005930 = [기본, 배당], ★ stays', pg.evaluate("KH.watch.groupsOf('005930')") == ['g0', 'g2'] and pg.evaluate("document.querySelector('#tablewrap button[data-w=\"005930\"]').textContent") == '★')
        pg.click('#wgpop label.row:has-text("기본") input'); pg.click('#wgpop label.row:has-text("배당") input'); pg.wait_for_timeout(200)
        ok('every tick off → off the watchlist, ☆', not pg.evaluate("KH.watch.has('005930')") and pg.evaluate("document.querySelector('#tablewrap button[data-w=\"005930\"]').textContent") == '☆')
        pg.click('#wgpop .row:has-text("새 그룹에 담기")'); pg.wait_for_timeout(150); pg.fill('#wgpop input[type=text]', '대형주'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
        m = pg.evaluate(POP)
        ok("＋ 새 그룹에 담기 → '대형주' made, back in the picker with it ticked", m and m['boxes'][-1] is True and pg.evaluate("KH.watch.groupsOf('005930').map(id => KH.watch.groups().find(g => g.id === id).name)") == ['대형주'], m)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        ok('Esc closes the picker, focus back on the ★', pg.evaluate(POP) is None and pg.evaluate("document.activeElement.dataset.w") == '005930')
        ok('picker: console errors 0', not errs(log), errs(log)[:3])
        ctx.close()
        ctx, pg, log = fresh(b, 'd1440', store={'watch': ['000660'], 'market': 'K'})
        pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
        pg.click('#tablewrap button[data-w="005930"]'); pg.wait_for_timeout(200)
        ok('one group: ☆ toggles at once, no picker', pg.evaluate(POP) is None and pg.evaluate("KH.watch.list()") == ['000660', '005930'])
        ctx.close()
        # phone: the quick sheet's ☆ → the picker as a bottom sheet
        ctx, pg, log = fresh(b, 'm390', store={'watchGroups': G3, 'market': 'K'})
        pg.evaluate("window.KHStock = undefined")
        pg.tap('#map .tile[data-c="005930"]'); pg.wait_for_timeout(400)
        pg.tap('#sheet .wstar'); pg.wait_for_timeout(250)
        m = pg.evaluate(POP); box = pg.evaluate("(() => { const r = document.getElementById('wgpop').getBoundingClientRect(); return [Math.round(r.left), Math.round(innerHeight - r.bottom)]; })()")
        ok(f'm390 quick sheet ☆ → the picker as a bottom sheet {box}', m and m['title'] == '삼성전자 · 관심 그룹' and box[0] == 8 and box[1] <= 12, (m, box))
        ctx.close()

    if 'quality' in WANT:
        for vp in ['m360', 'm390', 't768', 'd1280', 'd1920']:
            for view in ['map', 'table']:
                ctx, pg, log = fresh(b, vp, store={'watchGroups': G3}, hsh='#watch')
                if view == 'table': pg.click('.viewseg button[data-v="table"]'); pg.wait_for_timeout(400)
                over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
                lab = pg.evaluate(LABEL_CHECK_JS) if view == 'map' else {'overflow': 0, 'visible': '-', 'examples': []}
                chips = pg.evaluate("(() => { const c = document.getElementById('wgchips'); return { w: c.scrollWidth - c.clientWidth, h: Math.round(c.getBoundingClientRect().height) }; })()")
                mapTop = pg.evaluate("Math.round(document.getElementById(KH.view() === 'map' ? 'map' : 'tablewrap').getBoundingClientRect().bottom - innerHeight)")
                ok(f'{vp} {view}: overflow 0, console 0, labels inside ({lab["visible"]}), chips row {chips}, view bottom vs viewport {mapTop}',
                   over == 0 and not errs(log) and lab['overflow'] == 0 and (mapTop <= 0 or vp.startswith('m')), (over, errs(log)[:2], lab['examples'][:1]))
                if view == 'map' and vp in ('m390', 't768'): pg.screenshot(path=SHOTS + f'groups-{vp}-{build}.png')
                ctx.close()

    b.close()
print(f'\n{sum(res)}/{len(res)} passed ({build})')
sys.exit(0 if all(res) else 1)
