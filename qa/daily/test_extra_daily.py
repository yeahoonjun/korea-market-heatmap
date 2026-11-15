#!/usr/bin/env python3
"""Offline checks for the §3-37 data pieces of scripts/build_daily.py — no network.
    python3 qa/daily/test_extra_daily.py          → exit 1 on any failure
streak() · streaks over gaps, profile_flags() (alert / 관리 / 거래정지 rules), short_why() (150-character cut), write_theme_why()
(rewrite only on change, stale files removed), build_alerts() with a fake fetch (previous entry kept on failure, >3 % failing raises)."""
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

print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
