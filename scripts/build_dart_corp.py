#!/usr/bin/env python3
"""Map KRX stock codes → OpenDART corp_code (8 digits) for every stock in data/snapshot.json.

usage: DART_KEY=<your OpenDART key> python3 scripts/build_dart_corp.py
Writes web/dart_corp.json {asOf, map:{"005930":"00126380", …}}. The key is read from the environment and never written.
"""
import io, json, os, pathlib, sys, urllib.request, zipfile, xml.etree.ElementTree as ET, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
key = os.environ.get("DART_KEY")
if not key:
    sys.exit("DART_KEY is not set")
raw = urllib.request.urlopen(f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={key}", timeout=60).read()
if raw[:2] != b"PK":
    sys.exit("OpenDART did not return a zip: " + raw[:200].decode("utf-8", "replace"))
xml = zipfile.ZipFile(io.BytesIO(raw)).read("CORPCODE.xml")
by_stock = {}
for el in ET.fromstring(xml).iter("list"):
    sc = (el.findtext("stock_code") or "").strip()
    if sc:
        by_stock[sc] = el.findtext("corp_code").strip()
snap = json.loads((ROOT / "data/snapshot.json").read_text(encoding="utf-8"))
codes = [s["c"] for s in snap["stocks"]]
mapped = {c: by_stock[c] for c in codes if c in by_stock}
for c in codes:                                   # preferred shares (005935) file under the common stock's company (005930)
    if c not in mapped and c[:5] + "0" in by_stock:
        mapped[c] = by_stock[c[:5] + "0"]
out = {"asOf": datetime.date.today().isoformat(), "map": mapped}
(ROOT / "web/dart_corp.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
print(f"listed in DART: {len(by_stock)}  snapshot stocks: {len(codes)}  mapped: {len(mapped)}  missing: {len(codes) - len(mapped)}")
