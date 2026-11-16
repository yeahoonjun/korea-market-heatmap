#!/usr/bin/env python3
"""Design-standard audit of src/news (docs/standards/design.md, AGENTS §3-31 — the 뉴스 · 공시 step of design.md §11, ux/std-news).

  python3 qa/news/audit_css.py            (no browser, no server; exit 1 on any failure)

CSS (src/news/news.css) — the shared checks of qa/news/stdcss.py:
  ① no gradient at all · ② no glow (no drop-shadow, no own backdrop-filter, blur ≤ 2px only for the §6-4 swap / the fold's rows, no even
  halo or blurred amber / status shadow, no text-shadow, keyframes animate no paint, endless = the skeleton breath only) · ③ amber only on
  selected (the title underline, the outlet segment's indicator is the template's) / switched-on (지도 종목 기사만) / focus · ④ every
  font-size var(--fs-*), line heights --lh-* · ⑤ padding / margin / gap on --space-* · ⑥ corners from tokens · ⑦ heights from --h-* ·
  ⑧ springs only (no bezier, no literal durations, none of --c-base / --c-slow / --c-in / --m-*; press 0s → --c-fast), hover only on a fine
  pointer, one reduce switch · ⑨ glass material kept: no theme rule, no background / shadow / blur on the card itself (the .card plate is
  the template's: translucent --card-bg, the 1px edge reflection in --card-sh), and the template still has the sheen · edge · blur.
News-specific: the title tabs are an underline .seg (KH.ui.seg — lead / trail), the outlet tabs the template segment with no size
override, the 지도 종목 기사만 chip a filter pill (--h-chip, --chip-on + 1.5px ring), the outlet badge follows the badge recipe, ! is
--fail-dot (오래됨 · a stale outlet · the note line), the 더보기 fold (only the list box grows; rows .nw-x in at a quarter, out first), the
summary hold (nw-hold) is still there.
JS (src/news/news.js): no hand-written bezier, no 'ease-*', no literal WAAPI durations; KH.ui.seg on the title tabs; the fold runs on
KH.spring 'open' / 'close' and is exported as KHNews.fold; a chip's % and the counts change through KH.ui.swap (swapNum); no row stagger.
Build: web/index.html and dist/index.html carry this CSS / JS.

Deliberate values off the scale (named here so the audit can list them):
  - the badge recipe's height 18px (design.md §5) — also its line-height; the 2px underline of a picked tab (design.md §7 ③)
  - icon boxes: the ✓ mask 14px, the warn / spin icons 15px, the 6px chevron box (drawn at 1.75px)
  - the skeleton bar 10px · the touch hit areas 44px (::before, pointer:coarse) · the phone message box min-height 300px (the card keeps
    one height across states)
  - grid track widths (time column 40px) — geometry, not spacing
  - touch tablets' row 44 = calc(--h-row + --space-4) (the phone row height)
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stdcss import Audit, parse, common, glass_template, novar  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (ROOT / 'src/news/news.css').read_text(encoding='utf-8')
JS = (ROOT / 'src/news/news.js').read_text(encoding='utf-8')
TPL = (ROOT / 'src/template.html').read_text(encoding='utf-8')
A = Audit()
css, R, D, KF = parse(CSS)

OK_AMBER = re.compile(r'aria-pressed="true"|aria-selected="true"|\.nw-ftabs\.seg::before|:focus')
HEIGHT_OK = {('.news .nw-src', 'height', '18px'), ('.news .nw-only .nw-ck', 'height', '14px'), ('.news .nw-at svg', 'height', '15px'),
             ('.news .nw-note > svg', 'height', '15px'), ('.news .nw-more::after', 'height', '6px'), ('.news .nw-sk', 'height', '10px'), ('.news .nw-ftabs.seg::before', 'height', '2px'),
             ('@media (max-width:760px) .news .nw-msg', 'min-height', '300px')}


def height_ok(s, k, v):
    return (s, k, v) in HEIGHT_OK or (s.endswith('::before') and '(pointer:coarse)' in s and v == '44px')


common(A, 'news.css', css, R, D, KF, height_ok=height_ok, amber_ok=lambda s: bool(OK_AMBER.search(s)), endless=['nwSk'])


def first(sel, prop):
    for s, k, v in D:
        if s == sel and k == prop:
            return v
    return None


# ⑦ control heights · the badge recipe
want = {('.news .nw-only', 'height'): 'var(--h-chip)', ('.news .nw-chip', 'height'): 'var(--h-chip)', ('.news .nw-kbtn', 'height'): 'var(--h-key)',
        ('.news .nw-kbtn.sm', 'height'): 'var(--h-chip)', ('.news .nw-ftabs > button', 'height'): 'var(--h-key)', ('.news .nw-hd', 'min-height'): 'var(--h-key)',
        ('.news .nw-sub', 'min-height'): 'var(--h-key)', ('.news .nw-ft', 'min-height'): 'var(--h-key)', ('.news .nw-row', 'height'): 'var(--nw-rh)'}
bad = [(s, p, first(s, p), v) for (s, p), v in want.items() if first(s, p) != v]
A.check('⑦ keys 32 / 40 (--h-key), chips 24 / 32 (--h-chip), list rows --nw-rh = --h-row (36; phones 44+)', not bad and '--nw-rh:var(--h-row)' in css.replace(' ', ''), bad)
ph = [(s, k, v) for s, k, v in D if s.startswith('@media (max-width:760px)') and ((s.endswith('.nw-row') and k == 'min-height') or (s.endswith('.nw-kbtn:not(.sm)') and k == 'height'))]
A.check('⑦ phones: rows ≥ 44 (--h-row), the 더보기 key 44 (--h-row)', len(ph) == 2 and all(v == 'var(--h-row)' for _, _, v in ph), ph)
rec = {k: first('.news .nw-src', k) for k in ('height', 'font-size', 'font-weight', 'border-radius', 'box-shadow')}
A.check('⑦ the outlet badge = the badge recipe (18 · --fs-xs · 600 · --r-badge · 1px inner ring)',
        rec == {'height': '18px', 'font-size': 'var(--fs-xs)', 'font-weight': '600', 'border-radius': 'var(--r-badge)', 'box-shadow': 'inset 0 0 0 1px var(--line2)'}, rec)
A.check('⑦ no module corner tokens left (--nw-badge-r gone — the badge is --r-badge in every theme)', '--nw-badge-r' not in CSS and '--nw-badge-r' not in JS)

# ③ status: ! = --fail-dot, 오래됨 is not amber
fail = {s: v for s, k, v in D if k == 'color' and s in ('.news .nw-tabs > button .nw-bad', '.news .nw-note > svg', '.news .nw-at .kwn')}
A.check('③ the ! of a stale outlet, the note line and 오래됨 = --fail-dot', len(fail) == 3 and set(fail.values()) == {'var(--fail-dot)'}, fail)
st = [v for s, k, v in D if s == '.news .nw-at.stale' and k == 'color']
A.check('③ 오래됨 head text is not amber (--fg2 + the ! icon)', st == ['var(--fg2)'], st)
A.check('③ no --live here (nothing in the card is 장중 / 실시간)', '--live' not in css)

# §7 controls
segov = [(s, k, v) for s, k, v in D if s.startswith('.news .nw-tabs > button') and k in ('padding', 'height', 'min-height', 'font-size') and not s.startswith('@media')]
A.check('§7 outlet tabs = the template segment (.movers-tabs, KH.ui.seg), no size override on PC', not segov, segov)
ul = {k: first('.news .nw-ftabs.seg::before', k) for k in ('top', 'height', 'background', 'box-shadow')}
A.check('§7 title tabs = an underline row: the segment indicator as a 2px --acc-line bar (moved by KH.ui.seg: lead / trail)',
        ul == {'top': 'auto', 'height': '2px', 'background': 'var(--acc-line)', 'box-shadow': 'none'} and "class: 'seg nw-ftabs'" in JS and 'UI.seg(ttl)' in JS, ul)
A.check('§7 the old scaleX bar of the title tabs is gone (no ::after with --c-base)', not re.search(r'\.nw-tt button::after|nw-tt button\{', css))
chip = (first('.news .nw-only[aria-pressed="true"]', 'box-shadow') or '')
A.check('§7 지도 종목 기사만 = a filter pill: on = --chip-on + 1.5px --chip-ring, the check grows on lead and fades in', '1.5px var(--chip-ring)' in chip
        and 'width var(--sp-lead-dur) var(--sp-lead)' in (first('.news .nw-only .nw-ck', 'transition') or ''), chip)
sink = [s for s, k, v in D if k == 'transform' and v == 'translateY(1px)']
A.check('§7 keys and chips sink 1px (지도 종목 기사만 · 종목 칩 · 더보기 / 다시 시도)', all(any(n in s for s in sink) for n in ('.nw-only', '.nw-chip', '.nw-kbtn')), sink)
rowsink = [s for s in sink if re.search(r'\.nw-row|\.nw-ftabs|\.nw-tabs', s)]
A.check('§7 rows and tabs never sink (tabs: the template\'s --press-f)', not rowsink, rowsink)
chev = first('.news .nw-more::after', 'border-width') or ''
A.check('§4 the 더보기 chevron is drawn at 1.75px, turns on open / close', '1.75px' in chev and 'var(--sp-open)' in (first('.news .nw-more[aria-expanded="true"]::after', 'transition-timing-function') or '')
        and 'var(--sp-close)' in (first('.news .nw-more::after', 'transition') or ''), chev)

# §6 motion: the fold
fin = first('.news .nw-list.nw-fold-in > .nw-x', 'transition') or ''
fout = first('.news .nw-list.nw-fold-out > .nw-x', 'transition') or ''
A.check('§6 the fold: new rows wait hidden (4px · 2px blur), come in on fade after a quarter, leave first on close (§6-4 lengths)',
        first('.news .nw-list.nw-fold-anim > .nw-x', 'opacity') == '0' and 'var(--nw-tx-in) var(--sp-fade)' in fin and 'var(--nw-tx-out) var(--sp-close)' in fout
        and re.search(r'--nw-tx-out:100ms;--nw-tx-gap:60ms;--nw-tx-in:180ms', css.replace(' ', '')), (fin, fout))
A.check('§6 줄이기 = the §6-4 lengths 0 and no animation (html[data-motion="reduced"])', 'html[data-motion="reduced"] .news{--nw-tx-out:0ms' in css.replace(' ', '').replace('html[data-motion="reduced"].news', 'html[data-motion="reduced"] .news')
        or 'html[data-motion="reduced"] .news{--nw-tx-out:0ms' in css)
A.check('§6 the old row stagger is gone (no nwIn, no --d delay)', 'nwIn' not in css and '--d,' not in css and '--d:' not in JS)
A.check('§6 skeleton = flat --fill-2 bar breathing in opacity (no flowing gradient)', first('.news .nw-sk', 'background') == 'var(--fill-2)')

# ⑨ glass
own = [(s, k, v) for s, k, v in D if re.fullmatch(r'(\.layout > )?\.news(\.[\w-]+)*', s.split(' ', 1)[-1] if s.startswith('@media') else s) and k in ('background', 'background-color', 'box-shadow', 'border-radius', 'border', 'backdrop-filter')]
A.check('⑨ the card itself: no background / shadow / corner / blur of its own — the template .card (glass: translucent + 1px edge reflection)', not own, own)
glass_template(A, TPL)

# preserved behaviour
A.check('kept: the summary hold (.layout > .news.nw-hold{align-self:start} · summaryHeld in news.js)',
        '.layout > .news.nw-hold{align-self:start}' in css and "root.classList.toggle('nw-hold', held)" in JS and 'summaryHeld' in JS)
A.check('kept: the quote flash 2+4 tokens in the template (--fl-wu · --fl-wd · --fl-chip)', all(t in TPL for t in ('--fl-wu', '--fl-wd', '--fl-chip')))

# JS
js = re.sub(r'/\*.*?\*/', '', JS, flags=re.S)
js = re.sub(r'(?m)^\s*//.*$', '', js)
A.check('JS: no hand-written bezier, no keyword easings, no literal WAAPI durations',
        'cubic-bezier' not in js and not re.findall(r"easing:\s*'ease", js) and not re.findall(r'duration:\s*\d', js))
A.check("JS: the fold runs on KH.spring ('open' · 'close'), clips only the list box, is exported as KHNews.fold",
        "run('open', frame)" in js and "run('close'" in js and 'KH.spring.animate(' in js and 'fold: (box, want, apply, o) => fold(box, want, apply, o)' in js)
A.check('JS: a chip\'s % and the counts change through KH.ui.swap (swapNum — the way they went; quiet on the first draw / a tab change)',
        'UI.swap(el, text, was' in js and js.count('swapNum(') >= 4 and 'render({ data: true })' in js)
A.check('JS: 화려하게 fades a picked tab\'s content in (all at once)', "motion() === 'fancy'" in js and "classList.add('nw-in')" in js)

# build
for f in ('web/index.html', 'dist/index.html'):
    page = (ROOT / f).read_text(encoding='utf-8')
    ok = '.nw-ftabs.seg::before' in page and 'nw-fold-anim' in page and '--nw-badge-r' not in page and '@keyframes nwIn' not in page
    A.check(f'build: {f} carries the new news CSS / JS', ok)

sys.exit(A.done())
