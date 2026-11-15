#!/usr/bin/env python3
"""Daily data job for the heatmap (AGENTS.md §3-2, §3-37).  Plain Python 3 stdlib only.

    python3 scripts/build_daily.py                    # themes (+ theme_why/) + periods + flows (+ streaks) + alerts
    python3 scripts/build_daily.py --only flows       # one part (themes|periods|flows|alerts); repeatable
    python3 scripts/build_daily.py --only alerts      # the 07:50 KST morning run (market alerts only)
    python3 scripts/build_daily.py --limit 50 --out /tmp/x   # test: first 50 stocks / themes only, into another dir
    python3 scripts/build_daily.py --check-trading-day   # exit 0 if KRX traded today, 10 if not (holiday)
    python3 scripts/build_daily.py --check-trading-day --wait-session-end   # ...and sleep until the real session end

Reads  data/snapshot.json (the universe).
Writes web/themes.json, web/theme_why/<id>.json, web/periods.json, web/flows.json, web/alerts.json.

Sources (data/ENDPOINTS_EXTRA.md §1, §6, §7, §9):
  themes   m.stock.naver.com/api/stocks/theme[/{no}]  (+ themeItemInfoMap → theme_why/, no extra calls)
  periods  api.stock.naver.com/chart/domestic/item/{code}/day   (one call per stock)
  flows    m.stock.naver.com/api/stock/{code}/trend?pageSize=20 (one call per stock; streaks from the same rows)
  alerts   stock.naver.com/api/stockSecurity/items/v2/domestic/{code}/profile (one call per stock, honest UA, polite)
           + stock.naver.com/api/domestic/market/stock/default?orderType=marketAlertType (3 calls, cross-check only)
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
MAX_WAIT = 50 * 60       # --wait-session-end never sleeps longer than this
OUT = [WEB]
LIMIT = [None]           # --limit N: test runs only (first N stocks / themes)
stats = {"requests": 0, "retries": 0}
# The market-alert scan is new traffic (≈ 2,700 calls twice a weekday), so it says who it is and goes slowly.
BOT_UA = "PanseData/1.0 (+https://panse.pages.dev)"
STOCK_API = "https://stock.naver.com/api"
ALERT_WORKERS = 8        # ≈ 0.85 s per call measured → ≈ 8 calls/s at most, ≈ 5 min for 2,700 stocks
ALERT_DELAY = 0.1        # each worker pauses this long after every call
ALERT_MAX_FAIL = 0.03    # more than 3 % of the profiles failing → keep the previous alerts.json (no partial file)
TREND_ROWS = 20          # trend?pageSize=20 → streak window ("20일 이상" when every row has the same sign)
WHY_MAX = 150            # theme membership reason: characters kept (cut at a sentence end when possible, else "…")


def prev_path(name):
    """Where the previous copy of an output lives: the output dir, else web/ (a test run into --out still sees prod)."""
    p = os.path.join(OUT[0], name)
    return p if os.path.exists(p) else os.path.join(WEB, name)


def load_prev(name):
    try:
        with open(prev_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get_json(url, tries=5, ua=None, referer="https://m.stock.naver.com/"):
    """GET -> parsed JSON.  Browser UA (or `ua`), no Origin header, retries with backoff + jitter."""
    err = None
    for i in range(tries):
        try:
            h = {"User-Agent": ua or UA, "Accept": "application/json", "Accept-Encoding": "gzip"}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
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
    """All members of one theme, unioned by code over repeated page walks (rows shift while paging),
    plus Naver's one-line membership reason per code (themeItemInfoMap, merged over the pages)."""
    seen, why = {}, {}
    for _ in range(3):
        page = 1
        while True:
            d = get_json(f"{M_API}/stocks/theme/{no}?page={page}&pageSize=100")
            rows = d.get("stocks") or []
            for s in rows:
                seen.setdefault(s["itemCode"], s)
            m = d.get("themeItemInfoMap")
            if isinstance(m, dict):
                for c, t in m.items():
                    if isinstance(t, str) and t.strip():
                        why.setdefault(c, t)
            if not rows or page * 100 >= int(d.get("totalCount") or total):
                break
            page += 1
        if len(seen) >= total:
            break
    return list(seen.values()), why


SENT_END = re.compile(r"[.!?。](?=\s|$)")


def short_why(text, cap=WHY_MAX):
    """Whitespace-normalised reason, at most `cap` characters: whole sentences when they fit; otherwise cut at the
    last sentence end inside the cap (if that keeps at least 40 %), else at the last space, and end with "…"."""
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= cap:
        return t
    head = t[:cap]
    ends = [m.end() for m in SENT_END.finditer(head)]
    if ends and ends[-1] >= cap * 0.4:
        return head[:ends[-1]].rstrip()
    sp = head[:cap - 1].rfind(" ")
    return (head[:sp] if sp >= cap * 0.6 else head[:cap - 1]).rstrip(" ,·") + "…"


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
    glist = list(groups.values())
    if LIMIT[0]:
        glist = glist[:LIMIT[0]]
    got = pmap(lambda g: fetch_theme(g["no"], int(g["totalCount"])), glist)
    themes, short, out_of_snap, pairs = [], 0, set(), 0
    why = {}
    for g, (rows, reasons) in zip(glist, got):
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
        why[g["no"]] = {c: short_why(reasons[c]) for _, c in items if c in reasons}
    themes.sort(key=lambda t: t["id"])
    log(f"themes: {len(themes)} themes, {pairs} member pairs, {len(out_of_snap)} member codes not in "
        f"snapshot (kept), {short} themes with fewer members than totalCount")
    return {"asOf": snap["asOf"][:10], "themes": themes}, why


def write_theme_why(why, as_of):
    """web/theme_why/<id>.json = {asOf, r:{code: reason}} — one small file per theme (the page fetches the 1–2 it needs).
    A file is rewritten only when its reasons changed (`asOf` = the day its content last changed; the day it was last
    checked is themes.json `asOf`), so the daily commit doesn't touch ~265 files for nothing. Files of themes that are
    gone are removed (only when the full theme list was fetched, never on a --limit test run)."""
    d = os.path.join(OUT[0], "theme_why")
    os.makedirs(d, exist_ok=True)
    wrote = same = removed = total = longest = cut = 0
    for tid, r in sorted(why.items()):
        if not r:
            continue
        path = os.path.join(d, f"{tid}.json")
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = None
        if old and old.get("r") == r:
            same += 1
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"asOf": as_of, "r": r}, f, ensure_ascii=False, separators=(",", ":"))
                f.write("\n")
            wrote += 1
        total += os.path.getsize(path)
        longest = max(longest, max(len(t) for t in r.values()))
        cut += sum(t.endswith("…") for t in r.values())
    keep = {f"{tid}.json" for tid, r in why.items() if r}
    if not LIMIT[0]:
        for n in os.listdir(d):
            if re.fullmatch(r"\d+\.json", n) and n not in keep:
                os.remove(os.path.join(d, n))
                removed += 1
    pairs = sum(len(r) for r in why.values())
    log(f"theme_why: {len(keep)} files ({wrote} written, {same} unchanged, {removed} removed), {pairs} reasons, "
        f"{total / 1024:.0f} KB total, longest {longest} chars, {cut} cut with …")


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

    pcodes = [s["c"] for s in snap["stocks"]]
    res = dict(pmap(one, pcodes[:LIMIT[0]] if LIMIT[0] else pcodes))
    c = {k: v for k, v in res.items() if v is not None}
    nulls = [sum(v[i] is None for v in c.values()) for i in range(5)]
    log(f"periods: {len(c)}/{len(res)} stocks, nulls per period {dict(zip(order, nulls))}, "
        f"{len(res) - len(c)} fetch failures")
    return {"asOf": last, "base": {k: base[k] for k in order}, "off": {k: off[k] for k in order}, "c": c}


# ------------------------------------------------------------------------------------- flows
def load_prev_flows():
    return load_prev("flows.json")


def sums(rows):
    def s(col, n):
        return round(sum(r[col] for r in rows[:n]), 1) if len(rows) >= n else None
    return [s(1, 1), s(2, 1), s(3, 1), s(1, 5), s(2, 5), s(1, 20), s(2, 20)]


def streak(rows, col):
    """Current run of same-sign net buying in column `col` (1 = 외국인, 2 = 기관), counted back from the newest row:
    → (days, amount) — days > 0 = consecutive net-buy days, < 0 = net-sell days, 0 = the newest day was flat/unknown;
    amount = sum over those days of shares × that day's close (억원, as flows). The sign is the share count's sign
    (close > 0). An unusable row (None) or a zero day ends the run. |days| == TREND_ROWS means the whole window."""
    if not rows or rows[0][col] is None:
        return 0, 0.0
    sg = (rows[0][col] > 0) - (rows[0][col] < 0)
    if sg == 0:
        return 0, 0.0
    n, amt = 0, 0.0
    for r in rows[:TREND_ROWS]:
        v = r[col]
        if v is None or (v > 0) - (v < 0) != sg:
            break
        n += 1
        amt += v
    return sg * n, round(amt, 1)


def streaks(rows):
    fd, fa = streak(rows, 1)
    od, oa = streak(rows, 2)
    return [fd, fa, od, oa]


def build_flows(snap, fake_publish=None):
    """Per stock.  target day = newest bizdate (<= snapshot day) seen in any stock.  A stock whose newest row
    is older (Naver publishes the evening rows gradually; or halted) keeps ITS OWN last complete values
    (sums over its latest rows) and is listed in `stale` {code: its latest bizdate}; a stock that failed to
    fetch keeps the previous flows.json entry (also marked stale) if there was one.  The 21:30 run redoes all.
    Columns 8-11 (§3-37 ③) are the current 외국인 / 기관 streaks from the same rows: [days, 억원, days, 억원]
    (`streak`); `sw` = the window (TREND_ROWS) — |days| == sw means "sw일 이상".
    fake_publish=fraction is a test hook: pretend only that fraction of stocks has the target-day row."""
    codes = [s["c"] for s in snap["stocks"] if s["c"].endswith("0")]
    if LIMIT[0]:
        codes = codes[:LIMIT[0]]
    snap_day = snap["asOf"][:10].replace("-", "")

    def one(code):
        try:
            rows = get_json(f"{M_API}/stock/{code}/trend?pageSize={TREND_ROWS}")
        except RuntimeError as e:
            log("  ", e)
            return code, None
        out = []
        for r in rows:
            close = num(r.get("closePrice"))
            f, o, i = (num(r.get(k)) for k in ("foreignerPureBuyQuant", "organPureBuyQuant", "individualPureBuyQuant"))
            if close is None or f is None or o is None or i is None:
                out.append((r["bizdate"], None, None, None))   # kept as a gap: it ends a streak, sums skip it
                continue
            out.append((r["bizdate"], f * close / 1e8, o * close / 1e8, i * close / 1e8))
        return code, out

    res = dict(pmap(one, codes))
    if fake_publish is not None:
        rng = random.Random(1)
        for code, rows in res.items():
            if rows and rng.random() >= fake_publish:
                res[code] = rows[1:]                  # drop the newest row, as if not yet published
    usable = {c: ([r for r in rows if r[1] is not None] if rows else rows) for c, rows in res.items()}
    seen = [r[0][0] for r in usable.values() if r and r[0][0] <= snap_day]
    if not seen:
        raise RuntimeError("no trend rows at all")
    asof = max(seen)
    prev = load_prev_flows()
    prev_f = (prev or {}).get("f", {})
    prev_asof = (prev or {}).get("asOf")
    f, stale, failed, kept_prev = {}, {}, 0, 0
    for code in codes:
        rows = usable[code]
        rows = [r for r in rows if r[0] <= asof] if rows else rows
        if not rows:                               # fetch failure or no usable rows
            failed += 1
            if code in prev_f and prev_asof:       # previous flows.json value, flagged with its date
                old = list(prev_f[code])
                f[code] = old + [None] * (11 - len(old)) if len(old) < 11 else old   # an older 7-column file
                stale[code] = prev_asof
                kept_prev += 1
            continue
        start = rows[0][0]                         # streaks walk every row from the same newest usable day, gaps included
        seq = [r for r in res[code] if r[0] <= start]
        f[code] = sums(rows) + streaks(seq)
        if rows[0][0] != asof:                     # latest row is older than the target day
            stale[code] = iso(rows[0][0])
    nulls = [sum(v[i] is None for v in f.values()) for i in range(7)]
    st = [v for v in f.values() if v[7] is not None]
    dist = {f"{who}{'+' if s > 0 else '-'}{k}": sum(1 for v in st if (v[i] * s) >= k)
            for who, i in (("f", 7), ("i", 9)) for s in (1, -1) for k in (3, 7)}
    full = sum(1 for v in st if TREND_ROWS in (abs(v[7]), abs(v[9])))
    log(f"flows: {len(f)}/{len(codes)} stocks, asOf {iso(asof)}, stale {len(stale)} "
        f"(latest row older than asOf; {kept_prev} of them carried from previous flows.json), "
        f"fetch failures {failed}, nulls per column {nulls}")
    log(f"streaks: {len(st)} stocks, >= 3/7 days {dist}, whole {TREND_ROWS}-day window {full}")
    out = {"asOf": iso(asof), "unit": "억원", "sw": TREND_ROWS, "f": f}
    if stale:
        out["stale"] = dict(sorted(stale.items()))
    return out

# ------------------------------------------------------------------------------------ alerts
# profile `marketAlertType` → our short name (AGENTS §3-37 ⓐ, data/ENDPOINTS_EXTRA.md §9). Confirmed 2026-11-16 against
# Naver's alert lists (alertType 01/02 = the profile values below). 투자위험 (03) had no stock that day: both spellings
# Naver uses elsewhere are mapped, and any other non-normal value is kept as the raw string (validate_daily accepts it).
ALERT_NAME = {
    "marketAlertCaution": "caution",     # 투자주의 (alertType 01) — confirmed
    "marketAlertWarning": "warning",     # 투자경고 (alertType 02) — confirmed
    "marketAlertRisk": "risk",           # 투자위험 (alertType 03) — not seen yet (no stock on 2026-11-16)
    "marketAlertDanger": "risk",         #   "        the PC site calls the badge "danger"
}
ALERT_LIST_TYPE = {"01": "caution", "02": "warning", "03": "risk"}


def profile_flags(p):
    """Naver profile → {a?, adm?, stop?} (only the keys that are set). stop = 거래정지 (tradableStatus 'halt',
    tradableStatusCode eventHalt01) — NOT 'stop' (a temporary halt such as afterMarketOperationHalt: VI / CB-like,
    Naver labels it 거래불가) — tradeStopType is 'suspended' for both, so it is used only when tradableStatus is absent."""
    out = {}
    t = p.get("marketAlertType")
    if isinstance(t, str) and t and t != "normal":
        out["a"] = ALERT_NAME.get(t, t)
    if p.get("isAdministrativeIssue") is True:
        out["adm"] = 1
    ts = p.get("tradableStatus")
    if ts == "halt" or (ts is None and p.get("tradeStopType") == "suspended"):
        out["stop"] = 1
    return out


def alert_lists():
    """Naver's own lists of 투자주의 / 경고 / 위험 stocks (KRX, both markets) → {code: name} — 3 calls, cross-check only."""
    out = {}
    for code, name in ALERT_LIST_TYPE.items():
        start = 0
        while True:
            rows = get_json(f"{STOCK_API}/domestic/market/stock/default?tradeType=KRX&marketType=ALL&orderType=marketAlertType"
                            f"&alertType={code}&startIdx={start}&pageSize=100", tries=3, ua=BOT_UA, referer=None)
            if not isinstance(rows, list):
                raise RuntimeError(f"alert list {code}: not a list")
            for r in rows:
                if isinstance(r, dict) and r.get("itemcode"):
                    out[r["itemcode"]] = name
            if len(rows) < 100 or start >= 900:
                break
            start += 100
    return out


def build_alerts(snap):
    """web/alerts.json = {asOf:'YYYY-MM-DD', at:'HH:MM' (KST, start of the scan), n: stocks checked, c:{code:{a?, adm?, stop?}}}
    — only stocks with a flag. Every stock of the snapshot (preferreds included) is asked once, slowly, with an honest UA.
    A stock whose profile fails keeps its previous entry; more than ALERT_MAX_FAIL failing → raise (keep the old file)."""
    codes = [s["c"] for s in snap["stocks"]]
    if LIMIT[0]:
        codes = codes[:LIMIT[0]]
    now = dt.datetime.now(KST)
    raw = {}

    def one(code):
        try:
            p = get_json(f"{STOCK_API}/stockSecurity/items/v2/domestic/{code}/profile", tries=4, ua=BOT_UA, referer=None)
        except RuntimeError as e:
            log("  ", e)
            p = None
        time.sleep(ALERT_DELAY)
        return code, p

    with ThreadPoolExecutor(max_workers=ALERT_WORKERS) as ex:
        res = dict(ex.map(one, codes))
    prev = (load_prev("alerts.json") or {}).get("c", {})
    c, failed, kept, odd = {}, [], 0, 0
    for code in codes:
        p = res[code]
        if not isinstance(p, dict) or (p.get("itemCode") not in (None, code)):
            failed.append(code)
            if code in prev:
                c[code] = prev[code]
                kept += 1
            continue
        t = p.get("marketAlertType")
        raw[t] = raw.get(t, 0) + 1
        fl = profile_flags(p)
        if fl.get("a") and fl["a"] not in ("caution", "warning", "risk"):
            odd += 1
            log(f"::warning::alerts: unknown marketAlertType {fl['a']!r} for {code} (kept as the raw string)")
        if fl:
            c[code] = fl
    if len(failed) > ALERT_MAX_FAIL * len(codes):
        raise RuntimeError(f"alerts: {len(failed)}/{len(codes)} profiles failed — keeping the previous alerts.json")
    cnt = {}
    for v in c.values():
        for k in ("a", "adm", "stop"):
            if k in v:
                key = v[k] if k == "a" else k
                cnt[key] = cnt.get(key, 0) + 1
    log(f"alerts: {len(codes) - len(failed)}/{len(codes)} profiles, {len(c)} flagged {cnt}; raw marketAlertType {raw}; "
        f"failed {len(failed)} ({kept} kept from the previous file){'; e.g. ' + ','.join(failed[:5]) if failed else ''}")
    if not LIMIT[0]:                       # cross-check against Naver's own lists (a renamed value shows up here)
        try:
            lists = alert_lists()
            ours = {k: v["a"] for k, v in c.items() if "a" in v}
            want = {k: v for k, v in lists.items() if k in set(codes)}
            miss = sorted(k for k in want if ours.get(k) != want[k])
            extra = sorted(k for k in ours if k not in want)
            msg = f"alerts cross-check: Naver lists {len(want)} (in snapshot), profiles {len(ours)}, differ {len(miss)} + {len(extra)}"
            log(("::warning::" if miss or extra else "") + msg + (f" e.g. {(miss + extra)[:6]}" if miss or extra else ""))
        except RuntimeError as e:
            log("  alerts cross-check skipped:", e)
    return {"asOf": now.strftime("%Y-%m-%d"), "at": now.strftime("%H:%M"), "n": len(codes) - len(failed),
            "c": dict(sorted(c.items()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["themes", "periods", "flows", "alerts"], action="append")
    ap.add_argument("--check-trading-day", action="store_true")
    ap.add_argument("--wait-session-end", action="store_true",
                    help="with --check-trading-day: sleep until the session's real end (endTime) + 2 min, max 50 min")
    ap.add_argument("--fake-publish", type=float, metavar="FRAC",
                    help="test hook: pretend only FRAC of the stocks have the newest flows row")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="test runs only: the first N stocks (periods, flows, alerts) / N themes — use with --out")
    ap.add_argument("--out", default=WEB, help="output dir (default web/)")
    a = ap.parse_args()
    OUT[0] = a.out
    LIMIT[0] = a.limit if a.limit and a.limit > 0 else None
    if LIMIT[0] and os.path.abspath(a.out) == os.path.abspath(WEB):
        ap.error("--limit writes partial files: give --out another directory")
    if a.check_trading_day:
        sys.exit(check_trading_day(a.wait_session_end))
    t0 = time.time()
    snap = load_snapshot()
    failed = []
    for name, fn in (("themes", build_themes), ("periods", build_periods), ("flows", build_flows), ("alerts", build_alerts)):
        if a.only and name not in a.only:
            continue
        t = time.time()
        if name == "alerts":
            # the slowest part and the least important: when it fails the other files still get written and committed
            try:
                obj = fn(snap)
            except RuntimeError as e:
                log(f"::warning::{e}")
                failed.append(name)
                continue
        elif name == "flows":
            obj = fn(snap, a.fake_publish)
        elif name == "themes":
            obj, why = fn(snap)
            write_theme_why(why, obj["asOf"])
        else:
            obj = fn(snap)
        write_json(f"{name}.json", obj)
        log(f"  {name}: {time.time() - t:.0f}s")
    log(f"done in {time.time() - t0:.0f}s, {stats['requests']} requests, {stats['retries']} retries")
    if failed and a.only and set(a.only) <= set(failed):   # e.g. the morning `--only alerts` run: nothing to commit
        sys.exit(1)


if __name__ == "__main__":
    main()
