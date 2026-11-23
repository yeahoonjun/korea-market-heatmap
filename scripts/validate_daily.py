#!/usr/bin/env python3
"""Shape check for the daily files (AGENTS.md §3-2, §3-37).  Exit 1 on any error.

    python3 scripts/validate_daily.py                 # snapshot + themes + periods + marks + flows (+ streaks) + alerts + theme_why/
    python3 scripts/validate_daily.py --only alerts   # the 07:50 morning run (alerts.json only)
    python3 scripts/validate_daily.py --only marks --web /tmp/x --limit 50   # a `build_daily.py --limit 50 --out /tmp/x` test
    python3 scripts/validate_daily.py --web /tmp/x    # check a build_daily.py --out directory instead of web/

alerts.json, marks.json and theme_why/ are checked when present (the first runs after each change create them)."""
import argparse, datetime as dt, json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--only", choices=["alerts", "marks"])
ap.add_argument("--web", default=os.path.join(ROOT, "web"), help="directory with the generated web files (default web/)")
ap.add_argument("--limit", type=int, metavar="N", help="the files come from build_daily.py --limit N: marks coverage is "
                "checked against the first N snapshot stocks")
A = ap.parse_args()
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
W = lambda n: json.load(open(os.path.join(A.web, n), encoding="utf-8"))
snap = J("data/snapshot.json")
errs = []
D = re.compile(r"^\d{4}-\d{2}-\d{2}$")
num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and x == x
isint = lambda x: isinstance(x, int) and not isinstance(x, bool)
S = {s["c"]: s for s in snap["stocks"]}
sd = snap["asOf"][:10]
report = []


def check_alerts():
    path = os.path.join(A.web, "alerts.json")
    if not os.path.exists(path):
        report.append("alerts.json: not present (skipped)")
        return
    al = W("alerts.json")
    if not {"asOf", "at", "c"} <= set(al) or set(al) - {"asOf", "at", "n", "c"}: errs.append(f"alerts top {sorted(al)}")
    if not D.match(str(al.get("asOf"))) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(al.get("at"))): errs.append(f"alerts asOf/at {al.get('asOf')} {al.get('at')}")
    if "n" in al and (not isint(al["n"]) or al["n"] < 0.9 * len(S)): errs.append(f"alerts n {al.get('n')} < 90% of {len(S)} stocks")
    cnt = {}
    for c, v in al.get("c", {}).items():
        if not re.fullmatch(r"[0-9A-Z]{6}", c): errs.append(f"alerts code {c}")
        if not isinstance(v, dict) or not v or set(v) - {"a", "adm", "stop"}: errs.append(f"alerts entry {c} {v}"); continue
        a = v.get("a")
        if a is not None and not (a in ("caution", "warning", "risk") or (isinstance(a, str) and re.fullmatch(r"marketAlert\w+", a))):
            errs.append(f"alerts a {c} {a!r}")
        for k in ("adm", "stop"):
            if k in v and v[k] != 1: errs.append(f"alerts {k} {c} {v[k]!r}")
        for k in v:
            cnt[v[k] if k == "a" else k] = cnt.get(v[k] if k == "a" else k, 0) + 1
    n = len(al.get("c", {}))
    if n > 0.25 * len(S): errs.append(f"alerts: {n} flagged stocks is more than a quarter of the market — value names changed?")
    unknown = sorted(c for c in al.get("c", {}) if c not in S)
    report.append(f"alerts {al.get('asOf')} {al.get('at')}: {n} flagged {dict(sorted(cnt.items()))}"
                  + (f", {len(unknown)} codes not in the snapshot (new listings?)" if unknown else ""))


def check_marks(periods_asof=None):
    """marks.json (§3-2): {asOf, unit:'억원', tvn, from, c:{code:[tv20, hi52, lo52, hiDate, loDate(, since)]}, stale?}."""
    path = os.path.join(A.web, "marks.json")
    if not os.path.exists(path):
        report.append("marks.json: not present (skipped)")
        return
    mk = W("marks.json")
    if not {"asOf", "unit", "c"} <= set(mk) or set(mk) - {"asOf", "unit", "tvn", "from", "c", "stale"} or mk.get("unit") != "억원":
        errs.append(f"marks top {sorted(mk)} unit {mk.get('unit')!r}")
    asof, fr = str(mk.get("asOf")), str(mk.get("from", ""))
    if not D.match(asof): errs.append(f"marks asOf {asof!r}"); return
    if asof > sd: errs.append(f"marks asOf {asof} after snapshot day {sd}")
    if periods_asof and asof != periods_asof:
        report.append(f"marks: asOf {asof} != periods asOf {periods_asof} (kept from an earlier run — too many chart failures?)")
    tvn = mk.get("tvn")
    if tvn is not None and not (isint(tvn) and 5 <= tvn <= 60): errs.append(f"marks tvn {tvn!r}")
    if "from" in mk:
        span = (dt.date.fromisoformat(asof) - dt.date.fromisoformat(fr)).days if D.match(fr) else None
        if span is None or not 360 <= span <= 364: errs.append(f"marks window {fr}..{asof} = {span} days (52 weeks before the next weekday)")
    else:
        fr = (dt.date.fromisoformat(asof) - dt.timedelta(days=364)).isoformat()
    c = mk.get("c") if isinstance(mk.get("c"), dict) else {}
    stale = mk.get("stale", {})
    for code, d in stale.items():
        if code not in c or not D.match(str(d)) or not fr <= d < asof: errs.append(f"marks stale {code} {d}")
    n_null_tv = n_null_hl = n_since = new_hi = new_lo = 0
    outside, ratio = [], []
    for code, r in c.items():
        if not re.fullmatch(r"[0-9A-Z]{6}", code): errs.append(f"marks code {code}")
        if not isinstance(r, list) or len(r) not in (5, 6): errs.append(f"marks row {code} {r}"); continue
        tv, hi, lo, hd, ld = r[:5]
        end, lo_d = stale.get(code, asof), fr
        if code in stale and D.match(str(end)):          # a row carried from an older file had that file's window
            nd = dt.date.fromisoformat(end) + dt.timedelta(days=1)
            while nd.weekday() >= 5: nd += dt.timedelta(days=1)
            lo_d = min(fr, (nd - dt.timedelta(days=364)).isoformat())
        if tv is None: n_null_tv += 1
        elif not (num(tv) and 0 <= tv < 1e6 and round(tv, 1) == tv): errs.append(f"marks tv20 {code} {tv!r}")
        if hi is None:
            n_null_hl += 1
            if lo is not None or hd is not None or ld is not None: errs.append(f"marks hi/lo nulls {code} {r}")
        elif not (num(hi) and num(lo) and 0 < lo <= hi and D.match(str(hd)) and D.match(str(ld))
                  and lo_d <= hd <= end and lo_d <= ld <= end):
            errs.append(f"marks hi/lo {code} {r} (window {lo_d}..{end})")
        if len(r) == 6:
            n_since += 1
            sn = r[5]
            if not D.match(str(sn)) or not lo_d < sn <= end or (hi is not None and min(hd, ld) < sn): errs.append(f"marks since {code} {r}")
        new_hi += hd == asof
        new_lo += ld == asof
        s = S.get(code)
        if s and hi is not None and asof == sd and end == asof and (s.get("v") or 0) > 0:
            # the data day's own candle holds the regular-session close, so it lies inside [lo52, hi52] (0.1 % slack)
            if not lo * 0.999 <= s["p"] <= hi * 1.001: outside.append(code)
            if tv and (s.get("tv") or 0) >= 10: ratio.append(s["tv"] / tv)
    if outside and len(outside) > 0.005 * max(len(c), 1): errs.append(f"marks: snapshot close outside [lo52, hi52] for {len(outside)} stocks e.g. {outside[:5]}")
    if ratio:
        ratio.sort()
        med = ratio[len(ratio) // 2]
        if not 0.25 <= med <= 4: errs.append(f"marks: median snapshot tv / tv20 = {med:.2f} — unit changed?")
    uni = [s["c"] for s in snap["stocks"]][:A.limit] if A.limit else list(S)
    miss = [k for k in uni if k not in c]
    if len(miss) > 0.03 * len(uni): errs.append(f"marks missing {len(miss)}/{len(uni)} stocks e.g. {miss[:5]}")
    extra = sorted(k for k in c if k not in S)
    if extra: errs.append(f"marks codes not in the snapshot {extra[:5]}")
    report.append(f"marks {asof} (52 weeks {fr}..{asof}): {len(c)}/{len(uni)} stocks, tv20 null {n_null_tv}, hi/lo null {n_null_hl}, "
                  f"listed inside the window {n_since}, stale {len(stale)}; on {asof} 52-week high {new_hi} · low {new_lo}"
                  + (f"; snapshot tv / tv20 median {ratio[len(ratio) // 2]:.2f}" if ratio else "")
                  + (f"; close outside the range {len(outside)} {outside[:3]}" if outside else ""))


if A.only == "marks":
    check_marks()
    for r in report: print(r)
    print(f"errors={len(errs)}")
    for e in errs[:30]: print(" ", e)
    sys.exit(1 if errs else 0)

if A.only == "alerts":
    check_alerts()
    for r in report: print(r)
    print(f"errors={len(errs)}")
    for e in errs[:30]: print(" ", e)
    sys.exit(1 if errs else 0)

th, pe, fl = W("themes.json"), W("periods.json"), W("flows.json")
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
# theme_why/<id>.json (§3-37 ①): {asOf, r:{code: reason ≤ 150 chars}} for codes of that theme
wd = os.path.join(A.web, "theme_why")
if os.path.isdir(wd):
    members = {t["id"]: set(t["codes"]) for t in th["themes"]}
    nfiles = nreasons = nbytes = longest = 0
    for name in sorted(os.listdir(wd)):
        m = re.fullmatch(r"([1-9]\d{0,4})\.json", name)
        if not m: errs.append(f"theme_why stray file {name}"); continue
        tid = int(m.group(1))
        nbytes += os.path.getsize(os.path.join(wd, name))
        w = json.load(open(os.path.join(wd, name), encoding="utf-8"))
        nfiles += 1
        if set(w) != {"asOf", "r"} or not D.match(str(w["asOf"])) or not isinstance(w["r"], dict) or not w["r"]: errs.append(f"theme_why shape {name}"); continue
        if tid not in members: errs.append(f"theme_why {name}: no such theme in themes.json"); continue
        if w["asOf"] > th["asOf"]: errs.append(f"theme_why {name} asOf {w['asOf']} after themes {th['asOf']}")
        for c, txt in w["r"].items():
            nreasons += 1
            if c not in members[tid]: errs.append(f"theme_why {tid}: {c} is not a member")
            if not isinstance(txt, str) or not txt.strip() or len(txt) > 150 or txt != txt.strip() or "\n" in txt: errs.append(f"theme_why {tid} {c} text")
            else: longest = max(longest, len(txt))
    if nfiles < 0.9 * len(ids): errs.append(f"theme_why: {nfiles} files for {len(ids)} themes")
    report.append(f"theme_why: {nfiles} files, {nreasons} reasons, {nbytes / 1024:.0f} KB, longest {longest} chars")
# periods
if not {"asOf", "base", "c"} <= set(pe) or set(pe) - {"asOf", "base", "off", "c"} or not D.match(pe["asOf"]): errs.append("periods top")
if list(pe["base"]) != ["w1", "m1", "m3", "ytd", "y1"] or not all(D.match(v) for v in pe["base"].values()): errs.append("base")
b = pe["base"]
if not (b["y1"] <= b["ytd"] < b["m3"] < b["m1"] < b["w1"] < pe["asOf"]): errs.append(f"base order {b}")
if pe["asOf"] != sd: errs.append(f"periods asOf {pe['asOf']} != snapshot day {sd}")
off = pe.get("off")
if off is not None:
    if list(off) != list(b) or any(not isinstance(v, int) or v < 1 for v in off.values()): errs.append(f"off {off}")
    elif not (off["w1"] < off["m1"] < off["m3"] and 3 <= off["w1"] <= 9): errs.append(f"off sessions {off}")
for c, v in pe["c"].items():
    if c not in S: errs.append(f"periods extra {c}")
    if len(v) != 5 or any(x is not None and not (num(x) and x > 0) for x in v): errs.append(f"periods row {c} {v}")
missing = set(S) - set(pe["c"])
if missing: errs.append(f"periods missing {len(missing)}")
# flows (+ §3-37 ③ streak columns 8-11: [외국인 일수, 외국인 억원, 기관 일수, 기관 억원], `sw` = window)
if not {"asOf", "unit", "f"} <= set(fl) or set(fl) - {"asOf", "unit", "sw", "f", "stale"} or fl["unit"] != "억원" or not D.match(fl["asOf"]): errs.append("flows top")
sw = fl.get("sw")
if sw is not None and not (isint(sw) and 5 <= sw <= 60): errs.append(f"flows sw {sw}")
n_st, n_full = 0, 0
for c, v in fl["f"].items():
    if c not in S or not c.endswith("0"): errs.append(f"flows code {c}")
    if len(v) not in ((7, 11) if sw else (7,)) or any(x is not None and not num(x) for x in v): errs.append(f"flows row {c}"); continue
    if sw and len(v) != 11: errs.append(f"flows row {c}: {len(v)} columns with sw set"); continue
    if len(v) == 11:
        bad = False
        for i in (7, 9):
            d, amt = v[i], v[i + 1]
            if d is None and amt is None: continue        # carried from an older 7-column file (fetch failure)
            if not isint(d) or not num(amt) or abs(d) > sw: errs.append(f"flows streak {c} {v[7:]}"); bad = True; break
            if (d == 0 and amt != 0) or (d > 0 and amt < 0) or (d < 0 and amt > 0): errs.append(f"flows streak sign {c} {v[7:]}"); bad = True; break
        if not bad and v[7] is not None:
            n_st += 1
            n_full += sw in (abs(v[7]), abs(v[9] or 0))
        # the newest day is the first day of the streak: a non-zero 1-day amount has the streak's sign
        if not bad and isint(v[7]) and v[7] != 0 and v[0] not in (None, 0) and (v[0] > 0) != (v[7] > 0): errs.append(f"flows streak vs 1-day {c}")
        if not bad and isint(v[9]) and v[9] != 0 and v[1] not in (None, 0) and (v[1] > 0) != (v[9] > 0): errs.append(f"flows streak vs 1-day 기관 {c}")
if fl["asOf"] > sd: errs.append(f"flows asOf {fl['asOf']} after snapshot day {sd}")
stale = fl.get("stale", {})
for c, d in stale.items():
    if c not in fl["f"] or not D.match(d) or d >= fl["asOf"]: errs.append(f"stale entry {c} {d}")
miss = {c for c in S if c.endswith("0")} - set(fl["f"])
if miss: errs.append(f"flows missing {len(miss)}")
nf = len(fl["f"])
print(f"flows asOf {fl['asOf']}: {nf - len(stale)} current, {len(stale)} stale (latest row older than asOf) = {100 * len(stale) / max(nf, 1):.1f}%"
      + (" -> evening run should complete the rest" if stale else ""))
if stale: print("  stale sample:", dict(list(stale.items())[:5]))
if sw: report.append(f"streaks: {n_st} stocks, {n_full} with a whole {sw}-day run")
check_marks(pe["asOf"])
check_alerts()
for r in report: print(r)
print(f"themes={len(ids)} periods={len(pe['c'])} flows={len(fl['f'])} lim={sum('lim' in s for s in S.values())} errors={len(errs)}")
for e in errs[:30]: print(" ", e)
sys.exit(1 if errs else 0)
