#!/usr/bin/env python3
"""Daily data job for the heatmap (AGENTS.md §3-2).  Plain Python 3 stdlib only.

    python3 scripts/build_daily.py                    # themes + periods + flows
    python3 scripts/build_daily.py --only flows       # one part (themes|periods|flows)
    python3 scripts/build_daily.py --check-trading-day   # exit 0 if KRX traded today, 10 if not (holiday)
    python3 scripts/build_daily.py --check-trading-day --wait-session-end   # ...and sleep until the real session end

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
PERIOD_ORDER = ["w1", "m1", "m3", "ytd", "y1"]
PREV_WEB = os.path.join(WEB, "flows.json")
MAX_WAIT = 50 * 60       # --wait-session-end never sleeps longer than this
OUT = [WEB]
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
    os.makedirs(OUT[0], exist_ok=True)
    path = os.path.join(OUT[0], name)
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
def session_end(code=REF):
    """Regular-session end 'HHMM' from stockExchangeType.endTime (1530 normally, 1630 on 수능 day and the
    first trading day of the year).  Falls back to 1530 if the field is missing."""
    try:
        d = get_json(f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}")
        end = str(d["datas"][0]["stockExchangeType"]["endTime"])
        if re.fullmatch(r"\d{4}", end):
            return end
    except Exception as e:  # noqa: BLE001
        log("  session_end lookup failed, assuming 1530:", e)
    return "1530"


def check_trading_day(wait=False):
    now = dt.datetime.now(KST)
    # GitHub sometimes starts the scheduled 16:40 / 21:30 runs hours late (00:44–05:19 KST the next day, 2026-11-10…13), and
    # "today" then became the next date with no bar yet → "holiday" → nothing committed. A run before 08:00 KST belongs to
    # the previous calendar day.
    if now.hour < 8:
        now = now - dt.timedelta(days=1)
        log(f"started {dt.datetime.now(KST):%m-%d %H:%M} KST (late run) -> checking {now:%Y-%m-%d}")
    if now.weekday() >= 5:
        log(f"{now:%Y-%m-%d} is a weekend -> no trading")
        return 10
    bars = day_bars(REF, ymd(now), ymd(now))
    if not (bars and bars[-1][0] == now.strftime("%Y-%m-%d")):
        log(f"{now:%Y-%m-%d}: no {REF} bar today -> KRX holiday")
        return 10
    end = session_end()
    log(f"{now:%Y-%m-%d}: KRX traded ({REF} bar {bars[-1][1]:,.0f}); regular session ends {end[:2]}:{end[2:]}")
    print(f"session_end={end}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"session_end={end}\n")
    if wait:
        ready = dt.datetime.strptime(now.strftime("%Y%m%d") + end, "%Y%m%d%H%M").replace(tzinfo=KST) \
            + dt.timedelta(minutes=2)               # the 1-min bars of the last minute need a moment to appear
        secs = (ready - dt.datetime.now(KST)).total_seconds()
        if secs > MAX_WAIT:
            log(f"session ends too far away ({secs / 60:.0f} min) -> not waiting")
        elif secs > 0:
            log(f"waiting {secs:.0f}s for the session to end ({end[:2]}:{end[2:]})")
            time.sleep(secs)
    return 0


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
def month_back(d, n):
    y, m = d.year, d.month - n
    while m < 1:
        y, m = y - 1, m + 12
    day = d.day
    while True:
        try:
            return dt.date(y, m, day)
        except ValueError:                                   # e.g. Mar 31 - 1 month
            day -= 1


def build_periods(snap):
    """Bases are anchored to the LATEST TRADING DAY OF THE DATA (the snapshot's date / the last bar of the
    reference stock), never to the wall clock, so re-running on a later day or a weekend gives the same bases.

      w1  = last close on/before (latest day - 7 calendar days)
      m1  = ... on/before (latest day - 1 month)      m3 = ... (latest day - 3 months)
      ytd = last close of the previous calendar year
      y1  = ... on/before (latest day - 1 year)

    The page shows  current price / base close - 1 , i.e. "since that date's close".  `off` stores how many
    trading sessions before `asOf` each base is (w1 is normally 5, but 4-8 around holidays)."""
    data_day = dt.date.fromisoformat(snap["asOf"][:10])
    ref = day_bars(REF, ymd(data_day - dt.timedelta(days=420)), ymd(data_day))
    dates = [d for d, _ in ref]
    last = dates[-1]
    last_d = dt.date.fromisoformat(last)
    if last_d != data_day:
        log(f"periods: WARNING reference last bar {last} != snapshot day {data_day}; anchoring to {last}")
    target = {"w1": last_d - dt.timedelta(days=7), "m1": month_back(last_d, 1), "m3": month_back(last_d, 3),
              "y1": month_back(last_d, 12)}
    base = {}
    for k, t in target.items():
        cand = [d for d in dates if d <= t.isoformat()]
        if not cand:
            raise RuntimeError(f"reference chart does not reach {k} ({t})")
        base[k] = cand[-1]
    prev_year = [d for d in dates if d < f"{last_d.year}-01-01"]
    if not prev_year:
        raise RuntimeError("reference chart does not reach last year-end")
    base["ytd"] = prev_year[-1]
    off = {k: len(dates) - 1 - dates.index(base[k]) for k in PERIOD_ORDER}
    order = PERIOD_ORDER
    log(f"periods: ref {REF} last bar {last}; base " + ", ".join(f"{k}={base[k]}(-{off[k]} sessions)" for k in order))
    start = ymd(dt.date.fromisoformat(base["y1"]) - dt.timedelta(days=14))   # slack for halted base days
    end = ymd(last_d)

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
    return {"asOf": last, "base": {k: base[k] for k in order}, "off": {k: off[k] for k in order}, "c": c}


# ------------------------------------------------------------------------------------- flows
def load_prev_flows():
    try:
        with open(PREV_WEB, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def sums(rows):
    def s(col, n):
        return round(sum(r[col] for r in rows[:n]), 1) if len(rows) >= n else None
    return [s(1, 1), s(2, 1), s(3, 1), s(1, 5), s(2, 5), s(1, 20), s(2, 20)]


def build_flows(snap, fake_publish=None):
    """Per stock.  target day = newest bizdate (<= snapshot day) seen in any stock.  A stock whose newest row
    is older (Naver publishes the evening rows gradually; or halted) keeps ITS OWN last complete values
    (sums over its latest rows) and is listed in `stale` {code: its latest bizdate}; a stock that failed to
    fetch keeps the previous flows.json entry (also marked stale) if there was one.  The 21:30 run redoes all.
    fake_publish=fraction is a test hook: pretend only that fraction of stocks has the target-day row."""
    codes = [s["c"] for s in snap["stocks"] if s["c"].endswith("0")]
    snap_day = snap["asOf"][:10].replace("-", "")

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
    if fake_publish is not None:
        rng = random.Random(1)
        for code, rows in res.items():
            if rows and rng.random() >= fake_publish:
                res[code] = rows[1:]                  # drop the newest row, as if not yet published
    seen = [r[0][0] for r in res.values() if r and r[0][0] <= snap_day]
    if not seen:
        raise RuntimeError("no trend rows at all")
    asof = max(seen)
    prev = load_prev_flows()
    prev_f = (prev or {}).get("f", {})
    prev_asof = (prev or {}).get("asOf")
    f, stale, failed, kept_prev = {}, {}, 0, 0
    for code in codes:
        rows = res[code]
        rows = [r for r in rows if r[0] <= asof] if rows else rows
        if not rows:                               # fetch failure or no usable rows
            failed += 1
            if code in prev_f and prev_asof:       # previous flows.json value, flagged with its date
                f[code] = prev_f[code]
                stale[code] = prev_asof
                kept_prev += 1
            continue
        f[code] = sums(rows)
        if rows[0][0] != asof:                     # latest row is older than the target day
            stale[code] = iso(rows[0][0])
    nulls = [sum(v[i] is None for v in f.values()) for i in range(7)]
    log(f"flows: {len(f)}/{len(codes)} stocks, asOf {iso(asof)}, stale {len(stale)} "
        f"(latest row older than asOf; {kept_prev} of them carried from previous flows.json), "
        f"fetch failures {failed}, nulls per column {nulls}")
    out = {"asOf": iso(asof), "unit": "억원", "f": f}
    if stale:
        out["stale"] = dict(sorted(stale.items()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["themes", "periods", "flows"], action="append")
    ap.add_argument("--check-trading-day", action="store_true")
    ap.add_argument("--wait-session-end", action="store_true",
                    help="with --check-trading-day: sleep until the session's real end (endTime) + 2 min, max 50 min")
    ap.add_argument("--fake-publish", type=float, metavar="FRAC",
                    help="test hook: pretend only FRAC of the stocks have the newest flows row")
    ap.add_argument("--out", default=WEB, help="output dir (default web/)")
    a = ap.parse_args()
    OUT[0] = a.out
    if a.check_trading_day:
        sys.exit(check_trading_day(a.wait_session_end))
    t0 = time.time()
    snap = load_snapshot()
    for name, fn in (("themes", build_themes), ("periods", build_periods), ("flows", build_flows)):
        if a.only and name not in a.only:
            continue
        t = time.time()
        obj = fn(snap, a.fake_publish) if name == "flows" else fn(snap)
        write_json(f"{name}.json", obj)
        log(f"  {name}: {time.time() - t:.0f}s")
    log(f"done in {time.time() - t0:.0f}s, {stats['requests']} requests, {stats['retries']} retries")


if __name__ == "__main__":
    main()
