#!/usr/bin/env python3
"""Offline checks for the §3-37 data pieces of scripts/build_daily.py — no network.
    python3 qa/daily/test_extra_daily.py          → exit 1 on any failure
streak() · streaks over gaps, profile_flags() (alert / 관리 / 거래정지 rules), short_why() (150-character cut), write_theme_why()
(rewrite only on change, stale files removed), build_alerts() with a fake fetch (previous entry kept on failure, >3 % failing raises),
mark_row() · build_periods() + build_marks() (marks.json from the periods chart call: tv20, 52-week window, halted / new listings / stale,
previous row kept on failure, >3 % failing keeps the old marks.json but periods is still written)."""
import importlib.util, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("build_daily", os.path.join(ROOT, "scripts", "build_daily.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
B.log = lambda *a: None
B.ALERT_DELAY = 0

ok = bad = 0


def t(name, cond):
    global ok, bad
    if cond:
        ok += 1; print("  ok  ", name)
    else:
        bad += 1; print("  FAIL", name)


R = lambda *f: [("2026111" + str(9 - i), v, -v if v is not None else None, 0.0) for i, v in enumerate(f)]   # newest first, col 2 = −col 1

print("streak()")
t("3 buy days then a sell day → +3, amount = sum of the three", B.streak(R(1.5, 2.0, 0.5, -4.0, 9.0), 1) == (3, 4.0))
t("sell run → negative days and amount", B.streak(R(-1.0, -2.0, 3.0), 1) == (-2, -3.0))
t("organ column read independently (col 2 here is the mirror)", B.streak(R(1.0, 1.0, -1.0), 2) == (-2, -2.0))
t("newest day zero → 0, 0.0", B.streak(R(0.0, 5.0, 5.0), 1) == (0, 0.0))
t("a zero day ends the run", B.streak(R(1.0, 1.0, 0.0, 1.0), 1) == (2, 2.0))
t("an unusable row (None) ends the run", B.streak(R(1.0, None, 1.0), 1) == (1, 1.0))
t("newest row unusable → 0", B.streak(R(None, 1.0), 1) == (0, 0.0))
t("whole window → ±TREND_ROWS", B.streak(R(*([0.2] * 20)), 1) == (20, 4.0))
t("longer input is capped at the window", B.streak(R(*([0.2] * 25)), 1)[0] == 20)
t("tiny amounts round to 0.0 but the days still count", B.streak(R(0.00001, 0.00002), 1) == (2, 0.0))
t("streaks() → [fDays, fAmt, iDays, iAmt]", B.streaks(R(1.0, 1.0, -1.0)) == [2, 2.0, -2, -2.0])
t("empty → zeros", B.streak([], 1) == (0, 0.0))

print("profile_flags()")
P = lambda **k: {"marketAlertType": "normal", "isAdministrativeIssue": False, "tradeStopType": "trading", "tradableStatus": "tradable", **k}
t("normal → {}", B.profile_flags(P()) == {})
t("marketAlertCaution → caution", B.profile_flags(P(marketAlertType="marketAlertCaution")) == {"a": "caution"})
t("marketAlertWarning → warning", B.profile_flags(P(marketAlertType="marketAlertWarning")) == {"a": "warning"})
t("marketAlertRisk / marketAlertDanger → risk (unconfirmed spellings)", B.profile_flags(P(marketAlertType="marketAlertRisk")) == {"a": "risk"}
  and B.profile_flags(P(marketAlertType="marketAlertDanger")) == {"a": "risk"})
t("an unknown value is kept raw", B.profile_flags(P(marketAlertType="marketAlertSomething")) == {"a": "marketAlertSomething"})
t("관리 + 거래정지 + 주의 together (모아라이프플러스 11/16)", B.profile_flags(P(marketAlertType="marketAlertCaution", isAdministrativeIssue=True,
                                                                          tradeStopType="suspended", tradableStatus="halt")) == {"a": "caution", "adm": 1, "stop": 1})
t("tradableStatus stop (afterMarketOperationHalt, suspended) is NOT 거래정지", B.profile_flags(P(tradeStopType="suspended", tradableStatus="stop")) == {})
t("sessionRestricted is NOT 거래정지", B.profile_flags(P(tradableStatus="sessionRestricted")) == {})
t("no tradableStatus: suspended → stop", B.profile_flags({"marketAlertType": "normal", "tradeStopType": "suspended"}) == {"stop": 1})
t("missing / null fields → {}", B.profile_flags({}) == {} and B.profile_flags({"marketAlertType": None}) == {})

print("short_why()")
s = "창업자 및 벤처기업에 대한 투자 사업을 영위하는 창업투자회사. 퓨리오사AI 투자 이력 부각. "
t("short text: whitespace trimmed, unchanged", B.short_why(s) == s.strip())
t("inner runs of spaces and newlines collapse", B.short_why("가  나\n다") == "가 나 다")
long_s = ("가" * 70 + ". ") + ("나" * 70 + ". ") + ("다" * 70 + ".")
r = B.short_why(long_s)
t("long: cut at the last sentence end inside 150", r == "가" * 70 + ". " + "나" * 70 + "." and len(r) <= 150)
r = B.short_why("가" * 20 + ". " + "나 " * 100)
t("sentence end too early (< 40 %) → last space + …", r.endswith("…") and len(r) <= 150 and not r[:-1].endswith(" "))
r = B.short_why("가" * 300)
t("no space at all → hard cut at 149 + …", r == "가" * 149 + "…")
t("decimal points are not sentence ends", B.short_why("가" * 100 + " 3.5% 성장 " + "나" * 100).endswith("…"))

print("write_theme_why()")
with tempfile.TemporaryDirectory() as d:
    B.OUT[0] = d; B.LIMIT[0] = None
    why = {576: {"393210": "퓨리오사AI 투자 이력 부각."}, 12: {"042700": "반도체 장비."}, 99: {}}
    B.write_theme_why(why, "2026-11-13")
    p = os.path.join(d, "theme_why", "576.json")
    j = json.load(open(p, encoding="utf-8"))
    t("file shape {asOf, r}", j == {"asOf": "2026-11-13", "r": {"393210": "퓨리오사AI 투자 이력 부각."}})
    t("an empty theme gets no file", not os.path.exists(os.path.join(d, "theme_why", "99.json")))
    m0 = os.path.getmtime(p)
    os.utime(p, (m0 - 100, m0 - 100))
    B.write_theme_why(why, "2026-11-14")
    j = json.load(open(p, encoding="utf-8"))
    t("unchanged reasons → not rewritten (asOf keeps the day the content changed)", j["asOf"] == "2026-11-13" and os.path.getmtime(p) == m0 - 100)
    why[576]["393210"] = "바뀐 이유."
    open(os.path.join(d, "theme_why", "777.json"), "w").write("{}")
    open(os.path.join(d, "theme_why", "notes.txt"), "w").write("x")
    B.write_theme_why(why, "2026-11-15")
    j = json.load(open(p, encoding="utf-8"))
    t("changed reasons → rewritten with the new asOf", j == {"asOf": "2026-11-15", "r": {"393210": "바뀐 이유."}})
    t("a theme that is gone loses its file; other files are left alone",
      not os.path.exists(os.path.join(d, "theme_why", "777.json")) and os.path.exists(os.path.join(d, "theme_why", "notes.txt")))
    B.LIMIT[0] = 1
    open(os.path.join(d, "theme_why", "778.json"), "w").write("{}")
    B.write_theme_why({576: why[576]}, "2026-11-15")
    t("--limit runs never delete", os.path.exists(os.path.join(d, "theme_why", "778.json")))
    B.LIMIT[0] = None

print("build_alerts() with a fake fetch")
snap = {"stocks": [{"c": f"{i:06d}"} for i in range(100)]}
profiles = {f"{i:06d}": {"itemCode": f"{i:06d}", "marketAlertType": "normal", "isAdministrativeIssue": False, "tradeStopType": "trading",
                         "tradableStatus": "tradable"} for i in range(100)}
profiles["000001"].update(marketAlertType="marketAlertCaution")
profiles["000002"].update(isAdministrativeIssue=True, tradeStopType="suspended", tradableStatus="halt")
profiles["000003"].update(tradeStopType="suspended", tradableStatus="stop")
down = set()


def fake_get(url, tries=5, ua=None, referer=None):
    assert ua == B.BOT_UA and referer is None, "alerts must use the honest UA and no Referer"
    if "/profile" in url:
        c = url.split("/domestic/")[1].split("/")[0]
        if c in down:
            raise RuntimeError("GET failed: " + url)
        return profiles[c]
    if "orderType=marketAlertType" in url:
        return [{"itemcode": "000001"}] if "alertType=01" in url else []
    raise AssertionError(url)


B.get_json = fake_get
with tempfile.TemporaryDirectory() as d:
    B.OUT[0] = d
    a = B.build_alerts(snap)
    t("only flagged stocks, n = all checked", a["c"] == {"000001": {"a": "caution"}, "000002": {"adm": 1, "stop": 1}} and a["n"] == 100)
    t("asOf / at are KST date and HH:MM", len(a["asOf"]) == 10 and len(a["at"]) == 5 and a["at"][2] == ":")
    json.dump(a, open(os.path.join(d, "alerts.json"), "w"))
    down.update({"000001", "000050"})
    a2 = B.build_alerts(snap)
    t("a failed profile keeps its previous entry; a failed unflagged one stays out; n counts only answers",
      a2["c"] == a["c"] and a2["n"] == 98)
    down.update(f"{i:06d}" for i in range(10, 14))
    try:
        B.build_alerts(snap); raised = False
    except RuntimeError:
        raised = True
    t("more than 3 % failing → RuntimeError (the old file stays)", raised)

print("mark_row()")
import datetime as _dt
def wdays(a, b):
    d, out = _dt.date.fromisoformat(a), []
    while d <= _dt.date.fromisoformat(b):
        if d.weekday() < 5: out.append(d.isoformat())
        d += _dt.timedelta(days=1)
    return out
SES = wdays("2025-11-03", "2026-11-20")                      # market sessions (no holidays in this fake calendar)
FROM = "2025-11-24"                                          # next weekday of Fri 11/20 = Mon 11/23 − 52 weeks
t("window start = (next weekday after asOf) − 52 weeks", (B.next_weekday(_dt.date(2026, 11, 20)) - _dt.timedelta(days=364)).isoformat() == FROM)
t("next_weekday: Thu → Fri, Fri → Mon", B.next_weekday(_dt.date(2026, 11, 19)) == _dt.date(2026, 11, 20) and B.next_weekday(_dt.date(2026, 11, 20)) == _dt.date(2026, 11, 23))
C = lambda d, c, h, l, v: (d, c, h, l, v)
base = [C(d, 1000, 1010, 990, 1_000_000) for d in SES]       # (H+L+C)/3 = 1000 → 10억 a day
r, last, tvl = B.mark_row(base, FROM, SES)
t("flat stock: tv20 10억, hi 1010 / lo 990 dated the latest such day, no since", r == [10, 1010, 990, "2026-11-20", "2026-11-20"] and last == "2026-11-20" and tvl == 10.0)
b2 = [x if x[0] != "2025-11-21" else C(x[0], 1000, 5000, 1, 1) for x in base]
t("a bar before the window start (11/21) does not count for hi/lo", B.mark_row(b2, FROM, SES)[0][1:3] == [1010, 990])
b3 = [x if x[0] != "2025-11-24" else C(x[0], 1000, 2000, 500, 1_000_000) for x in base]
t("a bar ON the window start counts", B.mark_row(b3, FROM, SES)[0][1:5] == [2000, 500, "2025-11-24", "2025-11-24"])
b4 = [x if x[0] not in ("2026-03-02", "2026-09-01") else C(x[0], 1000, 2000, 990, 1_000_000) for x in base]
t("tie on the high → the most recent date", B.mark_row(b4, FROM, SES)[0][1] == 2000 and B.mark_row(b4, FROM, SES)[0][3] == "2026-09-01")
b5 = [x if x[0] != "2026-11-20" else C(x[0], 1000, 1010, 990, 21_000_000) for x in base]   # 210억 on the last day
t("tv20 = mean of the last 20 sessions (19 × 10 + 210) / 20 = 20", B.mark_row(b5, FROM, SES)[0][0] == 20)
b6 = [x if x[0] not in SES[-5:] else C(x[0], 1000, 0, 0, 0) for x in base]             # halted the last 5 sessions
r6 = B.mark_row(b6, FROM, SES)[0]
t("halted days: all-zero bars skipped for hi/lo, count 0 for tv20 (15 × 10 / 20 = 7.5)", r6[0] == 7.5 and r6[1:3] == [1010, 990] and r6[3] == SES[-6])
b7 = [x for x in base if x[0] not in SES[-3:-1]]                                       # two sessions without any candle
t("a session without a candle counts 0 (18 × 10 / 20 = 9)", B.mark_row(b7, FROM, SES)[0][0] == 9)
t("halted the whole window → hi/lo/dates null, tv20 0", B.mark_row([C(d, 4200, 0, 0, 0) for d in SES], FROM, SES)[0] == [0, None, None, None, None])
new = [C(d, 1000, 1010, 990, 1_000_000) for d in SES[-6:]]
r8 = B.mark_row(new, FROM, SES)[0]
t("listed 6 sessions ago: since = first candle, tv20 over its 6 sessions", r8 == [10, 1010, 990, SES[-1], SES[-1], SES[-6]])
t("fewer than 5 sessions → tv20 null (still hi/lo + since)", B.mark_row(new[-4:], FROM, SES)[0][0] is None and len(B.mark_row(new[-4:], FROM, SES)[0]) == 6)
t("no candle inside the window → None", B.mark_row([C("2025-11-10", 1, 1, 1, 1)], FROM, SES) is None and B.mark_row([], FROM, SES) is None)
r9, last9, _ = B.mark_row(base[:-2], FROM, SES)
t("last candle before asOf → computed up to it (20 sessions ending there)", last9 == SES[-3] and r9[0] == 10)
t("estimate falls back to the close when high/low are missing", B.est_tv(1000, 0, 0, 100_000_000) == 1000 and B.est_tv(1, 2, 3, 0) == 0)
t("prices stay integers when whole, tv20 one decimal", B.mark_row([C(d, 1000.0, 1010.0, 990.0, 1_234_567) for d in SES], FROM, SES)[0][:3] == [12.3, 1010, 990])

print("build_periods() + build_marks() with a fake chart")
CODES = ["005930", "000010", "000020", "000030", "000040"] + [f"1{i:05d}" for i in range(95)]   # 100 stocks: 3 failures = 3 % (ok), 4 → raise
charts = {"005930": base, "000010": b5, "000020": [C(d, 4200, 0, 0, 0) for d in SES], "000030": new, "000040": base[:-2]}
down = set()
def fake_chart(url, tries=5, ua=None, referer=None):
    assert "/chart/domestic/item/" in url and ua is None, url
    code = url.split("/item/")[1].split("/")[0]
    a, b = url.split("startDateTime=")[1][:8], url.split("endDateTime=")[1][:8]
    if code in down:
        raise RuntimeError("GET failed: " + url)
    rows = charts.get(code, base)
    iso8 = lambda d: d.replace("-", "")
    return [{"localDate": iso8(d), "closePrice": c, "openPrice": c if h else 0, "highPrice": h, "lowPrice": l, "accumulatedTradingVolume": v}
            for d, c, h, l, v in rows if a <= iso8(d) <= b]
B.get_json = fake_chart
fsnap = {"asOf": "2026-11-20T15:30:00+09:00", "stocks": [{"c": c, "p": 1000, "v": 1_000_000, "tv": 10} for c in CODES]}
with tempfile.TemporaryDirectory() as d:
    B.OUT[0] = d
    B.LIMIT[0] = None
    pe, part = B.build_periods(fsnap)
    t("build_periods returns periods (as before) + the marks part", pe["asOf"] == "2026-11-20" and len(pe["c"]) == len(CODES) and part["from"] == FROM)
    m = B.build_marks(fsnap, part)
    t("marks top: asOf = periods asOf, unit, tvn, from", (m["asOf"], m["unit"], m["tvn"], m["from"]) == ("2026-11-20", "억원", 20, FROM))
    t("every stock with a candle in the window has a row", set(m["c"]) == set(CODES))
    t("rows: normal / surge / halted / new listing", m["c"]["005930"] == [10, 1010, 990, "2026-11-20", "2026-11-20"] and m["c"]["000010"][0] == 20
      and m["c"]["000020"] == [0, None, None, None, None] and m["c"]["000030"][5] == SES[-6])
    t("last candle older than asOf → stale with that date", m.get("stale") == {"000040": SES[-3]})
    json.dump(m, open(os.path.join(d, "marks.json"), "w"))
    down.update({"000010", "100001"})
    m2 = B.build_marks(fsnap, B.build_periods(fsnap)[1])
    t("a failed chart call keeps the previous row, marked stale with the previous asOf only when older (same day → not stale)",
      m2["c"]["000010"] == m["c"]["000010"] and "000010" not in m2.get("stale", {}) and "100001" in m2["c"])
    prev = dict(m, asOf="2026-11-19", stale={})
    json.dump(prev, open(os.path.join(d, "marks.json"), "w"))
    m3 = B.build_marks(fsnap, B.build_periods(fsnap)[1])
    t("…and stale = the previous file's asOf when that is older", m3["stale"].get("000010") == "2026-11-19" and m3["stale"].get("100001") == "2026-11-19")
    down.update({"100002", "100003"})
    try:
        B.build_marks(fsnap, B.build_periods(fsnap)[1]); raised = False
    except RuntimeError:
        raised = True
    t("more than 3 % of the chart calls failing → RuntimeError", raised)
    snapf = os.path.join(d, "snap.json")
    json.dump(fsnap, open(snapf, "w"))
    B.SNAP, keep_argv = snapf, sys.argv
    before = open(os.path.join(d, "marks.json")).read()
    sys.argv = ["build_daily.py", "--only", "periods", "--out", d]
    try:
        B.main()
    finally:
        sys.argv = keep_argv
    t("main(): guard tripped → periods.json written, marks.json left as it was",
      os.path.exists(os.path.join(d, "periods.json")) and open(os.path.join(d, "marks.json")).read() == before)
    down.clear()
    sys.argv = ["build_daily.py", "--only", "periods", "--out", d]
    try:
        B.main()
    finally:
        sys.argv = keep_argv
    mm = json.load(open(os.path.join(d, "marks.json")))
    t("main(): --only periods also writes marks.json (fresh rows, stale only the short chart)", mm["asOf"] == "2026-11-20" and mm["stale"] == {"000040": SES[-3]}
      and mm["c"]["000010"][0] == 20)

print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
