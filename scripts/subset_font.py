#!/usr/bin/env python3
"""Subset Pretendard Variable to the characters the page can show (UI text + every stock name in the snapshot).

The artifact build can't load web fonts from jsDelivr (its content-security policy only allows Google Fonts),
so the snapshot page carries this subset inline as a data: URI. The Worker build links the full
dynamic-subset CSS from jsDelivr instead.

usage: npm pack pretendard && tar xzf pretendard-*.tgz
       python3 scripts/subset_font.py package/dist/web/variable/woff2/PretendardVariable.woff2
"""
import json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = sys.argv[1]
snap = json.loads((ROOT / "data/snapshot.json").read_text(encoding="utf-8"))
tpl = (ROOT / "src/template.html").read_text(encoding="utf-8")
chars = set("".join(s["n"] + s.get("s", "") + s.get("i", "") for s in snap["stocks"]) + tpl)
chars |= {chr(c) for c in range(0x20, 0x7F)} | set("−·…›‹×▾▴₩%↑↓←→—–‘’“”")
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write("".join(sorted(c for c in chars if c.isprintable())))
out = ROOT / "src/fonts/PretendardVariable-subset.woff2"
subprocess.run(["pyftsubset", src, f"--text-file={f.name}", "--flavor=woff2", f"--output-file={out}",
                "--layout-features=kern,liga,calt,tnum,ccmp,locl", "--no-hinting", "--desubroutinize"], check=True)
print(out, out.stat().st_size // 1024, "KB")
