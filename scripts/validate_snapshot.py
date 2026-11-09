import json, math, collections, os, sys
root = "/home/claude/heatmap/data"
snap = json.load(open(os.path.join(root, "snapshot.json")))
smap = json.load(open(os.path.join(root, "sector_map.json")))
S = snap["stocks"]
KEYS = {"c", "n", "m", "s", "i", "cap", "p", "d", "r", "tv", "v"}
ALLOWED = {"정보기술", "커뮤니케이션서비스", "헬스케어", "산업재", "소재", "경기소비재", "필수소비재", "금융", "에너지", "유틸리티", "기타"}
errs = []
print("top keys:", list(snap.keys()))
print("asOf", snap["asOf"], "| status", snap["marketStatus"], "| index", snap.get("index"))
codes = [x["c"] for x in S]
if len(codes) != len(set(codes)): errs.append("dup codes")
for x in S:
    if set(x) != KEYS: errs.append(f"keys {x['c']} {set(x) ^ KEYS}")
    for k in ("cap", "p", "d", "tv", "v"):
        if not isinstance(x[k], int): errs.append(f"type {x['c']} {k}={x[k]!r}")
    if not isinstance(x["r"], (int, float)) or math.isnan(x["r"]) or math.isinf(x["r"]): errs.append(f"r {x['c']}")
    if x["s"] not in ALLOWED: errs.append(f"sector {x['c']} {x['s']}")
    if x["i"] != "기타" and smap.get(x["i"]) != x["s"]: errs.append(f"map {x['c']} {x['i']}->{x['s']}")
    if x["m"] not in ("K", "Q"): errs.append(f"m {x['c']}")
    if x["p"] <= 0 or x["cap"] < 0: errs.append(f"nonpos {x['c']} p={x['p']} cap={x['cap']}")
    base = x["p"] - x["d"]
    if base > 0 and abs(round(x["d"] / base * 100, 2) - x["r"]) > 0.011: errs.append(f"r/d mismatch {x['c']} {x['r']} vs {x['d']/base*100:.3f}")
if any(S[i]["cap"] < S[i + 1]["cap"] for i in range(len(S) - 1)): errs.append("not sorted")
print("errors:", len(errs), errs[:15])
print("per market:", dict(collections.Counter(x["m"] for x in S)))
for m in "KQ":
    sec = collections.Counter(x["s"] for x in S if x["m"] == m)
    print(f" {m} per sector:", dict(sec.most_common()))
print("per sector (all):", dict(collections.Counter(x["s"] for x in S).most_common()))
print("기타:", [(x["c"], x["n"], x["m"]) for x in S if x["s"] == "기타"])
pref = [x for x in S if x["c"][-1] != "0"]
print("preferred shares kept:", len(pref))
print("sector_map: %d 업종 -> %s" % (len(smap), dict(collections.Counter(smap.values()))))
print("top 10 by cap:")
for x in S[:10]:
    print(f"  {x['c']} {x['n']:<12} {x['m']} {x['s']:<6} {x['i']:<12} cap={x['cap']:>9,}억 p={x['p']:>9,} d={x['d']:>+8,} r={x['r']:+.2f}% tv={x['tv']:,}억 v={x['v']:,}")
# sanity: cap-weighted average change (commons only) vs index
for m, nm in (("K", "KOSPI"), ("Q", "KOSDAQ")):
    xs = [x for x in S if x["m"] == m and x["c"][-1] == "0"]
    w = sum(x["cap"] / (1 + x["r"] / 100) for x in xs)  # prev-day caps
    chg = sum(x["cap"] - x["cap"] / (1 + x["r"] / 100) for x in xs) / w * 100
    print(f"cap-weighted change {nm}: {chg:+.2f}%  vs index {snap.get('index', {}).get(nm, {}).get('ratio')}%  (n={len(xs)}, total cap {sum(x['cap'] for x in xs)/1e4:,.0f}조)")
print("file size snapshot.json:", os.path.getsize(os.path.join(root, "snapshot.json")), "bytes")
