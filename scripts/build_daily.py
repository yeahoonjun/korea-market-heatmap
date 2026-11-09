#!/usr/bin/env python3
"""Daily data job for the heatmap (AGENTS.md §3-2).  Plain Python 3 stdlib only.

    python3 scripts/build_daily.py                    # themes + periods + flows
    python3 scripts/build_daily.py --only flows       # one part (themes|periods|flows)
    python3 scripts/build_daily.py --check-trading-day   # exit 0 if KRX traded today, 10 if not (holiday)

Reads  data/snapshot.json (the universe).
Writes web/themes.json, web/periods.json, web/flows.json.

Sources (data/ENDPOINTS_EXTRA.md §1, §6, §7):
  themes   m.stock.naver.com/api/stocks/theme[/{no}]
  periods  api.stock.naver.com/chart/domestic/item/{code}/day   (one call per stock)
  flows    m.stock.naver.com/api/stock/{code}/trend?pageSize=20 (one call per stock)
"""
import argparse
import datetime as dt
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SNAP = os.path.join(ROOT, "data", "snapshot.json")
KST = dt.timezone(dt.timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
M_API = "https://m.stock.naver.com/api"
CHART = "https://api.stock.naver.com/chart/domestic/item"
REF = "005930"           # reference stock that defines the base dates
WORKERS = 16
OFFSETS = {"w1": 5, "m1": 21, "m3": 63}     # trading days back from the latest bar
stats = {"requests": 0, "retries": 0}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get_json(url, tries=5):
    """GET -> parsed JSON.  Browser UA, no Origin header, retries with backoff + jitter."""
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip",
                "Referer": "https://m.stock.naver.com/"})
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            stats["requests"] += 1
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            if e.code in (400, 404):       # permanent: no point retrying
                break
        except Exception as e:  # noqa: BLE001  (timeouts, resets, bad JSON)
            err = repr(e)
        stats["retries"] += 1
        time.sleep(min(20, 1.0 * 2 ** i) + random.random())
    raise RuntimeError(f"GET failed: {url} ({err})")


def pmap(fn, items):
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        return list(ex.map(fn, items))


def num(x):
    if x is None:
        return None
    s = str(x).replace(",", "").replace("%", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def load_snapshot():
    with open(SNAP, encoding="utf-8") as f:
        return json.load(f)


def write_json(name, obj):
    os.makedirs(WEB, exist_ok=True)
    path = os.path.join(WEB, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    log(f"wrote {path}: {os.path.getsize(path) / 1024:.0f} KB")


def ymd(d):
    return d.strftime("%Y%m%d")


def iso(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def day_bars(code, start, end):
    """[(YYYY-MM-DD, close)] oldest first."""
    rows = get_json(f"{CHART}/{code}/day?startDateTime={start}000000&endDateTime={end}235959")
    return [(iso(b["localDate"]), b["closePrice"]) for b in rows if b.get("closePrice") is not None]


# ------------------------------------------------------------------------------ trading day
def check_trading_day():
    today = dt.datetime.now(KST)
    if today.weekday() >= 5:
        log(f"{today:%Y-%m-%d} is a weekend -> no trading")
        return 10
    bars = day_bars(REF, ymd(today), ymd(today))
    if bars and bars[-1][0] == today.strftime("%Y-%m-%d"):
        log(f"{today:%Y-%m-%d}: KRX traded ({REF} close {bars[-1][1]:,.0f})")
        return 0
    log(f"{today:%Y-%m-%d}: no {REF} bar today -> KRX holiday")
    return 10


# ------------------------------------------------------------------------------------ themes
def fetch_theme(no, total):
    """All members of one theme, unioned by code over repeated page walks (rows shift while paging)."""
    seen = {}
    for _ in range(3):
        page = 1
        while True:
            d = get_json(f"{M_API}/stocks/theme/{no}?page={page}&pageSize=100")
            rows = d.get("stocks") or []
            for s in rows:
                seen.setdefault(s["itemCode"], s)
            if not rows or page * 100 >= int(d.get("totalCount") or total):
                break
            page += 1
        if len(seen) >= total:
            break
    return list(seen.values())


def build_themes(snap):
    groups = {}
    for page in (1, 2, 3, 4):
        d = get_json(f"{M_API}/stocks/theme?page={page}&pageSize=100")
        for g in d.get("groups") or []:
            groups.setdefault(g["no"], g)
        if len(groups) >= int(d.get("totalCount", 0)) or not d.get("groups"):
            break
    log(f"themes: {len(groups)} in list")
    snap_cap = {s["c"]: s["cap"] for s in snap["stocks"]}
    members = pmap(lambda g: fetch_theme(g["no"], int(g["totalCount"])), list(groups.values()))
    themes, short, out_of_snap, pairs = [], 0, set(), 0
    for g, rows in zip(groups.values(), members):
        if len(rows) < int(g["totalCount"]):
            short += 1
        items = []
        for s in rows:
            c = s["itemCode"]
            if not c.endswith("0"):                      # preferred shares
                continue
            if c in snap_cap:
                cap = snap_cap[c]
            else:                                         # not in the snapshot: keep, use the theme row's cap
                out_of_snap.add(c)
                mv = num(s.get("marketValueRaw"))
                cap = round(mv / 1e8) if mv is not None else int(num(s.get("marketValue")) or 0)
            items.append((cap, c))
        items.sort(key=lambda t: (-t[0], t[1]))
        pairs += len(items)
        themes.append({"id": g["no"], "name": g["name"], "cap": sum(c for c, _ in items),
                       "codes": [c for _, c in items]})
    themes.sort(key=lambda t: t["id"])
    log(f"themes: {len(themes)} themes, {pairs} member pairs, {len(out_of_snap)} member codes not in "
        f"snapshot (kept), {short} themes with fewer members than totalCount")
    return {"asOf": snap["asOf"][:10], "themes": themes}


# ----------------------------------------------------------------------------------- periods
def build_periods(snap):
    today = dt.datetime.now(KST).date()
    ref = day_bars(REF, ymd(today - dt.timedelta(days=420)), ymd(today))
    dates = [d for d, _ in ref]
    last = dates[-1]
    last_d = dt.date.fromisoformat(last)
    base = {k: dates[-1 - n] for k, n in OFFSETS.items()}
    prev_year = [d for d in dates if d < f"{last_d.year}-01-01"]
    base["ytd"] = prev_year[-1]
    try:
        y1_target = last_d.replace(year=last_d.year - 1)
    except ValueError:                                       # Feb 29
        y1_target = last_d.replace(year=last_d.year - 1, day=28)
    y1 = [d for d in dates if d <= y1_target.isoformat()]
    if not y1:
        raise RuntimeError("reference chart does not reach one year back")
    base["y1"] = y1[-1]
    order = ["w1", "m1", "m3", "ytd", "y1"]
    log(f"periods: ref {REF} last bar {last}; base " + ", ".join(f"{k}={base[k]}" for k in order))
    start = ymd(dt.date.fromisoformat(base["y1"]) - dt.timedelta(days=14))   # slack for halted base days
    end = ymd(today)

    def one(code):
        try:
            bars = day_bars(code, start, end)
        except RuntimeError as e:
            log("  ", e)
            return code, None
        out = []
        for k in order:
            v = None
            for d, c in bars:                             # on/before the base date; older than listing -> null
                if d <= base[k]:
                    v = c
                else:
                    break
            if v is not None and bars[0][0] > base[k]:
                v = None
            out.append(None if v is None else (int(v) if float(v).is_integer() else v))
        return code, out

    res = dict(pmap(one, [s["c"] for s in snap["stocks"]]))
    c = {k: v for k, v in res.items() if v is not None}
    nulls = [sum(v[i] is None for v in c.values()) for i in range(5)]
    log(f"periods: {len(c)}/{len(res)} stocks, nulls per period {dict(zip(order, nulls))}, "
        f"{len(res) - len(c)} fetch failures")
    return {"asOf": last, "base": {k: base[k] for k in order}, "c": c}


# ------------------------------------------------------------------------------------- flows
def build_flows(snap):
    codes = [s["c"] for s in snap["stocks"] if s["c"].endswith("0")]

    def one(code):
        try:
            rows = get_json(f"{M_API}/stock/{code}/trend?pageSize=20")
        except RuntimeError as e:
            log("  ", e)
            return code, None
        out = []
        for r in rows:
            close = num(r.get("closePrice"))
            f, o, i = (num(r.get(k)) for k in ("foreignerPureBuyQuant", "organPureBuyQuant", "individualPureBuyQuant"))
            if close is None or f is None or o is None or i is None:
                continue
            out.append((r["bizdate"], f * close / 1e8, o * close / 1e8, i * close / 1e8))
        return code, out

    res = dict(pmap(one, codes))
    asof = max((r[0][0] for r in res.values() if r), default=None)
    if asof is None:
        raise RuntimeError("no trend rows at all")
    f, stale, failed = {}, 0, 0
    for code in codes:
        rows = res[code]
        if rows is None:
            failed += 1
            continue
        if not rows or rows[0][0] != asof:      # no row for the latest day (halted / not yet published): stale
            stale += 1
            f[code] = [None] * 7
            continue

        def s(col, n):
            return round(sum(r[col] for r in rows[:n]), 1) if len(rows) >= n else None
        f[code] = [s(1, 1), s(2, 1), s(3, 1), s(1, 5), s(2, 5), s(1, 20), s(2, 20)]
    nulls = [sum(v[i] is None for v in f.values()) for i in range(7)]
    log(f"flows: {len(f)}/{len(codes)} stocks, asOf {iso(asof)}, stale(no row for asOf) {stale}, "
        f"fetch failures {failed}, nulls per column {nulls}")
    return {"asOf": iso(asof), "unit": "억원", "f": f}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["themes", "periods", "flows"], action="append")
    ap.add_argument("--check-trading-day", action="store_true")
    a = ap.parse_args()
    if a.check_trading_day:
        sys.exit(check_trading_day())
    t0 = time.time()
    snap = load_snapshot()
    for name, fn in (("themes", build_themes), ("periods", build_periods), ("flows", build_flows)):
        if a.only and name not in a.only:
            continue
        t = time.time()
        write_json(f"{name}.json", fn(snap))
        log(f"  {name}: {time.time() - t:.0f}s")
    log(f"done in {time.time() - t0:.0f}s, {stats['requests']} requests, {stats['retries']} retries")


if __name__ == "__main__":
    main()
