#!/usr/bin/env python3
"""Build the heatmap pages from src/template.html + data/snapshot.json.

Outputs
  dist/index.html        snapshot mode (no network calls) — what gets published as the artifact
  web/index.html         live mode page — the Worker serves it from GitHub (raw.githubusercontent.com)
  web/universe.json      top 300 stocks per market + 업종/섹터, read by the Worker's /api/quotes
  web/names.json         every stock's name + market (live search beyond the streamed 600)
  web/close.json         KRX 15:30 closes for every stock (only when the snapshot is pinned to the close)
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
tpl = (ROOT / "src/template.html").read_text(encoding="utf-8")
SNAP_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/snapshot.json"
snap = json.loads((SNAP_PATH).read_text(encoding="utf-8"))

# keep only the fields the page reads, compact separators, and make it safe inside <script>
keep = ("c", "n", "m", "s", "i", "cap", "p", "d", "r", "tv", "v", "lim", "op", "hi", "lo")
snap["stocks"] = [{k: s[k] for k in keep if k in s} for s in snap["stocks"]]
blob = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


import base64
FONT_INLINE = (
    "<style>@font-face{font-family:'Pretendard Variable';font-weight:45 920;font-style:normal;font-display:swap;"
    "src:url(data:font/woff2;base64,"
    + base64.b64encode((ROOT / "src/fonts/PretendardVariable-subset.woff2").read_bytes()).decode()
    + ") format('woff2-variations')}</style>"
)
# 명조 제목 (themes.md §5, paper only, off by default): a Noto Serif KR subset (titles + numbers) as a non-running block in <head>;
# the page turns it into a FontFace only when the setting is on — no network in either mode
SERIF_INLINE = ('<script type="application/octet-stream" id="kh-serif">'
                + base64.b64encode((ROOT / "src/fonts/NotoSerifKR-head-subset.woff2").read_bytes()).decode() + '</script>')
FONT_CDN = ('<link rel="stylesheet" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/'
            'dist/web/variable/pretendardvariable-dynamic-subset.min.css">')


LIVE_BOOT = json.dumps({"asOf": None, "source": "네이버 증권", "marketStatus": {}, "index": {}, "stocks": []}, ensure_ascii=False)


D3_TAG = re.compile(r'<script[^>]*src="https://cdnjs\.cloudflare\.com/ajax/libs/d3/7\.9\.0/d3\.min\.js"[^>]*></script>')
D3_INLINE = "<script>\n" + (ROOT / "src/vendor/d3-7.9.0.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n</script>"


def page(mode: str) -> str:
    assert "__SNAPSHOT__" in tpl and "__MODE__" in tpl and "<!--__FONT__-->" in tpl
    # the artifact's content-security policy blocks jsDelivr, so the snapshot page carries a font subset inline
    font = FONT_INLINE if mode == "snapshot" else FONT_CDN
    data = blob if mode == "snapshot" else LIVE_BOOT
    extra = embedded_data() if mode == "snapshot" else ""
    out = tpl
    if mode == "snapshot":                      # the snapshot must draw with no network at all: d3 rides inline
        assert len(D3_TAG.findall(out)) == 1, "d3 <script> tag not found exactly once in the template"
        out = D3_TAG.sub(lambda m: D3_INLINE, out)
    return (out.replace("<!--__FONT__-->", font).replace("<!--__SERIF__-->", SERIF_INLINE).replace("<!--__STOCK__-->", extra + stock_module())
            .replace("__MODE__", mode).replace("__SNAPSHOT__", data))


def module(folder: str, name: str) -> str:
    """Inline src/<folder>/<name>.css and .js (missing files → nothing)."""
    css_p, js_p = ROOT / f"src/{folder}/{name}.css", ROOT / f"src/{folder}/{name}.js"
    out = ""
    if css_p.exists():
        out += "<style>\n" + css_p.read_text(encoding="utf-8") + "\n</style>\n"
    if js_p.exists():
        out += "<script>\n" + js_p.read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n</script>\n"
    return out


def stock_module() -> str:
    """The stock page (src/stock/), the extras (src/extras/), world (src/world/), news (src/news/) and disclosure (src/disclosure/) are
    inlined after the heatmap script."""
    # news (docs/standards/news.md §11 ④): match.js (headline names) before news.js; the snapshot shows only a note — no articles baked in
    # 공시 배지 (docs/standards/disclosure.md §13 ⑧): after news (it adds the 오늘 공시 tab to the news card); the snapshot: a note only
    return (module("stock", "stock") + module("extras", "extras") + module("world", "world") + module("news", "match") + module("news", "news")
            + module("disclosure", "disc"))


DATA_FILES = ("themes", "periods", "flows", "market")   # market: /api/market after the close (index spark for the §3-20 header line)


def embedded_data() -> str:
    """Snapshot mode can't fetch, so the daily data files ride along as JSON blocks: <script id="kh-data-themes">."""
    out = ""
    for name in DATA_FILES:
        f = ROOT / "web" / f"{name}.json"
        if f.exists():
            txt = json.dumps(json.loads(f.read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
            out += f'<script id="kh-data-{name}" type="application/json">{txt}</script>\n'
    return out


(ROOT / "web").mkdir(exist_ok=True)
(ROOT / "web/index.html").write_text(page("live"), encoding="utf-8")
import shutil
for f in (ROOT / "src/pwa").iterdir():          # manifest, service worker, icons for "add to home screen"
    shutil.copyfile(f, ROOT / "web" / f.name)
(ROOT / "dist").mkdir(exist_ok=True)
(ROOT / "dist/index.html").write_text(page("snapshot"), encoding="utf-8")

LIVE_PER_MARKET = 300
B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
pairs, pair_ix = [], {}
uni = {}
for m in ("K", "Q"):
    rows = sorted((x for x in snap["stocks"] if x.get("m") == m and x["c"].endswith("0")), key=lambda x: -x.get("cap", 0))[:LIVE_PER_MARKET]
    enc = []
    for x in rows:
        key = (x.get("i") or "기타", x.get("s") or "기타")
        if key not in pair_ix:
            pair_ix[key] = len(pairs); pairs.append(list(key))
        ix = pair_ix[key]
        enc.append(x["c"] + B36[ix // 36] + B36[ix % 36])
    uni[m] = "".join(enc)
streamed = set(uni["K"][k:k + 6] for k in range(0, len(uni["K"]), 8)) | set(uni["Q"][k:k + 6] for k in range(0, len(uni["Q"]), 8))
xs = []
for x in snap["stocks"]:                       # everything else: sector lookup only (not streamed)
    if x["c"] in streamed:
        continue
    key = (x.get("i") or "기타", x.get("s") or "기타")
    if key not in pair_ix:
        pair_ix[key] = len(pairs); pairs.append(list(key))
    ix = pair_ix[key]
    xs.append(x["c"] + B36[ix // 36] + B36[ix % 36] + x.get("m", "K"))
uni["X"] = "".join(xs)
uni["I"] = pairs
(ROOT / "web/universe.json").write_text(json.dumps(uni, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def dump(name, obj):
    (ROOT / "web" / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# names for live search: every stock incl. preferred shares
dump("names.json", {"asOf": snap.get("asOf"), "n": {x["c"]: [x["n"], x.get("m", "K")] for x in snap["stocks"]}})

# KRX regular-session closes: only when the snapshot was pinned to the close (build_snapshot.py --close krx|auto)
as_of = snap.get("asOf") or ""
pinned = snap.get("close") == "krx" or (snap.get("close") is None and as_of[11:16] in ("15:30", "16:30")
                                         and all(v != "OPEN" for v in (snap.get("marketStatus") or {}).values()))
close_p = ROOT / "web/close.json"
if pinned:
    dump("close.json", {"date": as_of[:10], "asOf": as_of,
                        "c": {x["c"]: [x.get("p"), x.get("d"), x.get("r")] for x in snap["stocks"] if x.get("p")}})
elif close_p.exists():
    close_p.unlink()                            # never leave a stale close file next to unpinned prices
print(f"stocks={len(snap['stocks'])}  dist/index.html={len(page('snapshot'))//1024}KB  close.json={'yes' if pinned else 'no'}", file=sys.stderr)
