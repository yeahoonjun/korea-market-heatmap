#!/usr/bin/env python3
"""Shape check for the daily files (AGENTS.md §3-2).  Exit 1 on any error."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
snap, th, pe, fl = J("data/snapshot.json"), J("web/themes.json"), J("web/periods.json"), J("web/flows.json")
errs = []
D = re.compile(r"^\d{4}-\d{2}-\d{2}$")
num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and x == x
S = {s["c"]: s for s in snap["stocks"]}
for s in snap["stocks"]:
    if "lim" in s and s["lim"] not in (1, -1): errs.append(f"lim {s['c']}")
    if s.get("lim") == 1 and s["r"] < 29: errs.append(f"lim up r {s['c']}")
    if s.get("lim") == -1 and s["r"] > -29: errs.append(f"lim dn r {s['c']}")
# themes
if set(th) != {"asOf", "themes"} or not D.match(th["asOf"]): errs.append("themes top")
ids = [t["id"] for t in th["themes"]]
if len(ids) != len(set(ids)) or len(ids) < 250: errs.append(f"theme count {len(ids)}")
cap_of = lambda c: S[c]["cap"] if c in S else None
for t in th["themes"]:
    if set(t) != {"id", "name", "cap", "codes"}: errs.append(f"theme keys {t.get('id')}")
    if not t["codes"] or len(set(t["codes"])) != len(t["codes"]): errs.append(f"codes {t['id']}")
    if any(not re.fullmatch(r"[0-9A-Z]{5}0", c) for c in t["codes"]): errs.append(f"pref/bad code in {t['id']}")
    caps = [cap_of(c) for c in t["codes"] if c in S]
    if caps != sorted(caps, reverse=True): errs.append(f"cap order {t['id']}")
    if not num(t["cap"]) or t["cap"] < sum(caps) - 1: errs.append(f"cap sum {t['id']}")
# periods
if set(pe) != {"asOf", "base", "c"} or not D.match(pe["asOf"]): errs.append("periods top")
if list(pe["base"]) != ["w1", "m1", "m3", "ytd", "y1"] or not all(D.match(v) for v in pe["base"].values()): errs.append("base")
b = pe["base"]
if not (b["y1"] <= b["ytd"] < b["m3"] < b["m1"] < b["w1"] < pe["asOf"]): errs.append(f"base order {b}")
for c, v in pe["c"].items():
    if c not in S: errs.append(f"periods extra {c}")
    if len(v) != 5 or any(x is not None and not (num(x) and x > 0) for x in v): errs.append(f"periods row {c} {v}")
missing = set(S) - set(pe["c"])
if missing: errs.append(f"periods missing {len(missing)}")
# flows
if set(fl) != {"asOf", "unit", "f"} or fl["unit"] != "억원" or not D.match(fl["asOf"]): errs.append("flows top")
for c, v in fl["f"].items():
    if c not in S or not c.endswith("0"): errs.append(f"flows code {c}")
    if len(v) != 7 or any(x is not None and not num(x) for x in v): errs.append(f"flows row {c}")
miss = {c for c in S if c.endswith("0")} - set(fl["f"])
if miss: errs.append(f"flows missing {len(miss)}")
print(f"themes={len(ids)} periods={len(pe['c'])} flows={len(fl['f'])} lim={sum('lim' in s for s in S.values())} errors={len(errs)}")
for e in errs[:30]: print(" ", e)
sys.exit(1 if errs else 0)
