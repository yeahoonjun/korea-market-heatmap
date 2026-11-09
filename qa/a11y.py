import sys; sys.path.insert(0, '/home/claude/heatmap/qa')
from common import *
def lum(h):
    h = h.lstrip('#'); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return round((la + .05) / (lb + .05), 2)
print('contrast:')
for fg in ('#8a8f99', '#61656f', '#bcc0c8', '#a6abb5'):
    for bg in ('#131418', '#191a1f', '#202228', '#0d0e11', '#000000'):
        print(f'  {fg} on {bg}: {cr(fg, bg)}')
print('  white on tile stops (krg):', {c: cr('#ffffff', c) for c in ['#12a15b', '#15814b', '#1f5a41', '#383c46', '#74303c', '#b8343f', '#ef3e4a']})
print('  white on global/cvd brightest:', {c: cr('#ffffff', c) for c in ['#2bb553', '#f63538', '#ef8a1f', '#3d95ee']})
print('  up/dn text krg on panel:', cr('#ff5c66', '#191a1f'), cr('#2fd67a', '#191a1f'), ' krb dn', cr('#5b9bff', '#191a1f'))
print('  amber pri button text', cr('#1b1404', '#ffb547'))

with sync_playwright() as p:
    b = launch(p)
    ctx, pg, log = new_page(b, 'd1280', SNAP_URL)
    stops = []
    pg.click('body', position={'x': 600, 'y': 5})
    for i in range(70):
        pg.keyboard.press('Tab')
        d = pg.evaluate("""(()=>{const e=document.activeElement; if(!e||e===document.body) return null;
          const cs=getComputedStyle(e); const r=e.getBoundingClientRect();
          return {tag:e.tagName.toLowerCase(), cls:(e.className||'').toString().slice(0,20), txt:(e.innerText||e.value||e.getAttribute('aria-label')||'').replace(/\\n/g,' ').slice(0,18),
            ring: cs.outlineStyle!=='none' && parseFloat(cs.outlineWidth)>0 ? cs.outlineColor : (cs.boxShadow!=='none'?'shadow':'NONE'), parent:(e.closest('[id]')||{}).id, vis:r.width>0&&r.height>0}})()""")
        stops.append(d)
    from collections import Counter, OrderedDict
    groups = OrderedDict()
    for s in stops:
        if not s: continue
        k = s['parent']; groups.setdefault(k, []).append(s)
    for k, v in groups.items():
        print(f'  focus group #{k}: {len(v)} stops, rings={Counter(x["ring"] for x in v)}, e.g. {[x["txt"] for x in v[:4]]}')
    print('  tiles focusable:', pg.evaluate("document.querySelectorAll('#map .tile[tabindex], #map .hd[tabindex]').length"))
    # sheet via keyboard from movers
    pg.focus('#movers button'); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
    print('  sheet opened via Enter:', pg.evaluate("document.querySelector('#sheet').classList.contains('open')"), 'focus inside sheet:', pg.evaluate("document.querySelector('#sheet').contains(document.activeElement)"),
          'aria-modal:', pg.get_attribute('#sheet', 'aria-modal'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    print('  after Esc focus on:', pg.evaluate("(()=>{const e=document.activeElement;return e.tagName+' '+(e.innerText||'').slice(0,15).replace(/\\n/g,' ')})()"))
    # table keyboard
    pg.click('.seg[data-key="view"] button[data-v="table"]'); pg.wait_for_timeout(300)
    print('  table th tabindex/button:', pg.evaluate("[...document.querySelectorAll('#tablewrap th')].map(t=>t.tabIndex)"), ' rows tabindex:', pg.evaluate("document.querySelector('#tablewrap tbody tr').tabIndex"))
    # hist buttons accessible names
    print('  hist aria-labels:', pg.eval_on_selector_all('#hist button', 'e=>e.slice(0,3).map(b=>b.getAttribute("aria-label"))'))
    print('  seg groups role/label:', pg.eval_on_selector_all('.seg', 'e=>e.map(s=>(s.getAttribute("role")||"-")+":"+(s.getAttribute("aria-label")||"-"))'))
    print('  sugg options ids / aria-activedescendant:', pg.get_attribute('#q', 'aria-activedescendant'))
    print('  console', log.console)
    ctx.close(); b.close()
