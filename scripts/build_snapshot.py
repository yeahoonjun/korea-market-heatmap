#!/usr/bin/env python3
"""Build data/snapshot.json + data/sector_map.json for the KOSPI/KOSDAQ heatmap.

Source: Naver Finance mobile JSON API (m.stock.naver.com / api.stock.naver.com).

    python3 scripts/build_snapshot.py                 # auto close basis
    python3 scripts/build_snapshot.py --close naver   # fast, raw Naver prices
    python3 scripts/build_snapshot.py --close krx     # force KRX 15:30 close pinning

Steps
  1. 업종 list  : GET m.stock.naver.com/api/stocks/industry?page=1&pageSize=100   (79 groups)
     members    : GET m.stock.naver.com/api/stocks/industry/{no}?page=N&pageSize=100
  2. all stocks : GET m.stock.naver.com/api/stocks/marketValue/{KOSPI|KOSDAQ}?page=N&pageSize=100
     (pageSize max = 100; ranking shifts while paginating can drop/duplicate a few rows, so the
      industry member lists - which carry the same price fields - are unioned in as a backup)
  3. indices    : GET m.stock.naver.com/api/index/{KOSPI|KOSDAQ}/basic
  4. close basis: after 15:30 Naver's `closePrice` keeps moving (it tracks NXT after-market
     15:40-20:00 and KRX 시간외 단일가 16:00-18:00) while `compareToPreviousClosePrice` stays relative
     to the KRX 기준가.  So once the regular session is over (index marketStatus != OPEN) we pin each
     stock to its KRX regular-session close = last 1-minute bar <= 15:30 from
     api.stock.naver.com/chart/domestic/item/{code}/minute?startDateTime=..&endDateTime=..
     and recompute d / r / cap from it.  (~2,700 extra requests, ~15-20 min at the polite delay;
     results are cached in .cache/krx_close_YYYYMMDD.json so same-day re-runs take ~1 min.)
     Halted stocks (no bars at all) keep Naver's values (d = 0).

Exclusions: ETF / ETN (stockEndType != "stock"), SPACs (name contains "스팩"), fund share
classes listed as stock ("... X클래스"), KONEX (sosok "2").  Preferred shares (code's last
char != "0", e.g. 005935 삼성전자우) are kept - every one of them has a Naver 업종.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KST = dt.timezone(dt.timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# --------------------------------------------------------------------------------------------
# Naver 업종 (= WICS 소분류 names) -> WICS 대분류 (sector names as requested by the front-end).
# Verified 2026-11-09 by joining every Naver 업종's members against the official WICS sector
# index constituents published by WISEindex (www.wiseindex.com/Index/GetIndexComponets?
# sec_cd=G10..G55&dt=20261106): all 78 real 업종 mapped to exactly ONE WICS sector with zero
# conflicts (2,197 matched stocks).  Notes / judgment calls:
#   * WICS sector labels renamed for the UI: IT -> 정보기술, 건강관리 -> 헬스케어,
#     경기관련소비재 -> 경기소비재.
#   * 전기제품 (2차전지: LG에너지솔루션, 삼성SDI, 에코프로비엠 ...) is in WICS **IT** (G45), unlike
#     GICS where Electrical Equipment is Industrials.  WICS's separate 소분류 전기장비 (LS ELECTRIC,
#     HD현대일렉트릭, 효성중공업 ...) is 산업재.  Followed WICS.
#   * 전자제품 (LG전자 ...) -> IT in WICS (GICS: Consumer Discretionary).
#   * 화장품 -> 경기소비재 in WICS (GICS: Consumer Staples).
#   * 건축자재 and 가구 -> 산업재 in WICS (GICS: Materials / Consumer Discretionary).
#   * 부동산, 창업투자 -> 금융 (WICS has no separate Real Estate sector).
#   * 문구류 (only member: 모나미) is not in any WICS sector index -> judgment call: 산업재
#     (GICS Office Services & Supplies sits under Industrials > Commercial Services & Supplies).
#   * 기타 (Naver group no. 25) holds ETFs/ETNs/fund classes; kept as "기타" for completeness.
# --------------------------------------------------------------------------------------------
SECTOR_MAP = {
    # 정보기술 (WICS IT, G45)
    "반도체와반도체장비": "정보기술", "디스플레이패널": "정보기술", "디스플레이장비및부품": "정보기술",
    "전자장비와기기": "정보기술", "전기제품": "정보기술", "전자제품": "정보기술",
    "통신장비": "정보기술", "핸드셋": "정보기술", "컴퓨터와주변기기": "정보기술",
    "사무용전자제품": "정보기술", "소프트웨어": "정보기술", "IT서비스": "정보기술",
    # 커뮤니케이션서비스 (G50)
    "다각화된통신서비스": "커뮤니케이션서비스", "무선통신서비스": "커뮤니케이션서비스",
    "광고": "커뮤니케이션서비스", "방송과엔터테인먼트": "커뮤니케이션서비스", "출판": "커뮤니케이션서비스",
    "게임엔터테인먼트": "커뮤니케이션서비스", "양방향미디어와서비스": "커뮤니케이션서비스",
    # 헬스케어 (WICS 건강관리, G35)
    "제약": "헬스케어", "생물공학": "헬스케어", "건강관리장비와용품": "헬스케어",
    "건강관리업체및서비스": "헬스케어", "건강관리기술": "헬스케어", "생명과학도구및서비스": "헬스케어",
    # 산업재 (G20)
    "우주항공과국방": "산업재", "건축제품": "산업재", "건축자재": "산업재", "건설": "산업재",
    "전기장비": "산업재", "복합기업": "산업재", "기계": "산업재", "조선": "산업재",
    "무역회사와판매업체": "산업재", "가구": "산업재", "상업서비스와공급품": "산업재",
    "문구류": "산업재",  # judgment call, see note above
    "항공화물운송과물류": "산업재", "항공사": "산업재", "해운사": "산업재",
    "도로와철도운송": "산업재", "운송인프라": "산업재",
    # 소재 (G15)
    "화학": "소재", "포장재": "소재", "비철금속": "소재", "철강": "소재", "종이와목재": "소재",
    # 경기소비재 (WICS 경기관련소비재, G25)
    "자동차": "경기소비재", "자동차부품": "경기소비재", "가정용기기와용품": "경기소비재",
    "레저용장비와제품": "경기소비재", "섬유,의류,신발,호화품": "경기소비재", "화장품": "경기소비재",
    "호텔,레스토랑,레저": "경기소비재", "교육서비스": "경기소비재", "다각화된소비자서비스": "경기소비재",
    "판매업체": "경기소비재", "백화점과일반상점": "경기소비재", "인터넷과카탈로그소매": "경기소비재",
    "전문소매": "경기소비재",
    # 필수소비재 (G30)
    "식품": "필수소비재", "음료": "필수소비재", "담배": "필수소비재", "가정용품": "필수소비재",
    "식품과기본식료품소매": "필수소비재",
    # 금융 (G40)
    "은행": "금융", "증권": "금융", "창업투자": "금융", "기타금융": "금융", "카드": "금융",
    "손해보험": "금융", "생명보험": "금융", "부동산": "금융",
    # 에너지 (G10)
    "석유와가스": "에너지", "에너지장비및서비스": "에너지",
    # 유틸리티 (G55)
    "전기유틸리티": "유틸리티", "가스유틸리티": "유틸리티", "복합유틸리티": "유틸리티",
    # Naver's catch-all group (ETF/ETN/fund classes)
    "기타": "기타",
}
SECTORS = ["정보기술", "커뮤니케이션서비스", "헬스케어", "산업재", "소재", "경기소비재",
           "필수소비재", "금융", "에너지", "유틸리티"]

M_API = "https://m.stock.naver.com/api"
CHART_API = "https://api.stock.naver.com/chart/domestic/item"


class Client:
    def __init__(self, delay):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Referer": "https://m.stock.naver.com/",
                               "Accept": "application/json"})
        self.delay = delay

    def get(self, url, tries=4):
        for i in range(tries):
            try:
                r = self.s.get(url, timeout=15)
                if r.status_code == 200:
                    time.sleep(self.delay)
                    return r.json()
                err = f"HTTP {r.status_code}"
            except (requests.RequestException, ValueError) as e:
                err = repr(e)
            time.sleep(1.0 + i * 2)
        raise RuntimeError(f"GET failed after {tries} tries: {url} ({err})")


def num(x, typ=float):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "N/A", "-"):
        return None
    return typ(float(s))


def paged(cli, url_fmt, key="stocks", attempts=3):
    """Fetch every page.  Lists are sorted by a live value (cap / change rate), so rows can move
    across page boundaries between requests and get skipped or duplicated.  If the unique count is
    short of totalCount, re-walk the pages (up to `attempts` times) and union by itemCode."""
    seen, meta = {}, {}
    for _ in range(attempts):
        page, n = 1, 0
        while True:
            d = cli.get(url_fmt.format(page=page))
            meta = d
            rows = d.get(key) or []
            n += len(rows)
            for s in rows:
                seen.setdefault(s["itemCode"], s)
            if not rows or n >= int(d.get("totalCount", 0)):
                break
            page += 1
        if len(seen) >= int(meta.get("totalCount", 0)):
            break
    return list(seen.values()), meta


def fetch_industries(cli):
    d = cli.get(f"{M_API}/stocks/industry?page=1&pageSize=100")
    groups = d["groups"]
    code2ind, rows = {}, {}
    for g in groups:
        lst, _ = paged(cli, f"{M_API}/stocks/industry/{g['no']}?page={{page}}&pageSize=100")
        for s in lst:
            code2ind.setdefault(s["itemCode"], g["name"])
            rows.setdefault(s["itemCode"], s)
        print(f"  업종 {g['no']:>3} {g['name']:<16} {len(lst):>5}", file=sys.stderr)
    return groups, code2ind, rows


def fetch_market(cli, market):
    rows, meta = paged(cli, f"{M_API}/stocks/marketValue/{market}?page={{page}}&pageSize=100")
    print(f"  {market}: {len(rows)} rows (totalCount {meta.get('totalCount')})", file=sys.stderr)
    return rows, meta


def fetch_index(cli, market):
    try:
        d = cli.get(f"{M_API}/index/{market}/basic")
        return {"value": num(d["closePrice"]), "change": num(d["compareToPreviousClosePrice"]),
                "ratio": num(d["fluctuationsRatio"])}, d.get("marketStatus"), d.get("localTradedAt")
    except Exception as e:  # noqa: BLE001
        print(f"  index {market} failed: {e}", file=sys.stderr)
        return None, None, None


def krx_close(cli, code, ymd, end="1530"):
    """Last 1-minute bar <= the session end (KRX regular-session close; end = 'HHMM' from
    stockExchangeType.endTime: 1530 normally, 1630 on 수능 day / first trading day of the year).
    Returns (price, had_any_bar_that_day) or (None, None) on error."""
    e6 = end + "00"
    start = (dt.datetime.strptime(ymd + end, "%Y%m%d%H%M") - dt.timedelta(minutes=30)).strftime("%Y%m%d%H%M") + "00"
    try:
        bars = cli.get(f"{CHART_API}/{code}/minute?startDateTime={start}&endDateTime={ymd}{e6}")
        if not bars:  # illiquid: no trade in the last 30 min -> look at the whole day
            bars = cli.get(f"{CHART_API}/{code}/minute?startDateTime={ymd}090000&endDateTime={ymd}235959")
            reg = [b for b in bars if b["localDateTime"][:8] == ymd and b["localDateTime"][8:] <= e6]
            if not reg:
                return None, bool(bars)
            bars = reg
        bars = [b for b in bars if b["localDateTime"][:8] == ymd and b["localDateTime"][8:] <= e6]
        return (int(round(bars[-1]["currentPrice"])) if bars else None), True
    except Exception as e:  # noqa: BLE001
        print(f"  chart {code} failed: {e}", file=sys.stderr)
        return None, None


def session_end_of(rows):
    """Most common stockExchangeType.endTime among the market-list rows (default 1530)."""
    from collections import Counter
    c = Counter(str((r.get("stockExchangeType") or {}).get("endTime") or "") for r in rows)
    c.pop("", None)
    end = c.most_common(1)[0][0] if c else "1530"
    return end if re.fullmatch(r"\d{4}", end) else "1530"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--close", choices=["auto", "naver", "krx"], default="auto",
                    help="auto = pin to KRX 15:30 close when the regular session is not OPEN")
    ap.add_argument("--delay", type=float, default=0.2, help="seconds to sleep after each request")
    ap.add_argument("--workers", type=int, default=1, help="parallel workers for the chart pass")
    ap.add_argument("--out", default=DATA)
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, ".cache"),
                    help="where finished-day KRX closes are cached (krx_close_YYYYMMDD.json)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cli = Client(a.delay)

    print("[1/4] industries", file=sys.stderr)
    groups, code2ind, ind_rows = fetch_industries(cli)
    unknown = sorted({g["name"] for g in groups} - set(SECTOR_MAP))
    if unknown:
        print(f"  WARNING: 업종 not in SECTOR_MAP -> 기타: {unknown}", file=sys.stderr)
    with open(os.path.join(a.out, "sector_map.json"), "w", encoding="utf-8") as f:
        json.dump({g["name"]: SECTOR_MAP.get(g["name"], "기타") for g in
                   sorted(groups, key=lambda g: (SECTORS.index(SECTOR_MAP[g["name"]])
                                                 if SECTOR_MAP.get(g["name"]) in SECTORS else 99, g["name"]))},
                  f, ensure_ascii=False, indent=1)

    print("[2/4] market lists", file=sys.stderr)
    raw, mstat = {}, {}
    for market in ("KOSPI", "KOSDAQ"):
        rows, meta = fetch_market(cli, market)
        mstat[market] = meta.get("marketStatus")
        for s in rows:
            raw.setdefault(s["itemCode"], s)
    # backfill rows dropped by ranking shifts during pagination (same fields in industry lists)
    backfilled = 0
    for c, s in ind_rows.items():
        if c not in raw and s.get("sosok") in ("0", "1"):
            raw[c] = s
            backfilled += 1

    print("[3/4] indices", file=sys.stderr)
    index, idx_ts = {}, []
    for market in ("KOSPI", "KOSDAQ"):
        v, st, ts = fetch_index(cli, market)
        if v:
            index[market] = v
            idx_ts.append(ts)
        if st:
            mstat[market] = st  # index status reflects the regular session (stocks say OPEN in after-hours)

    stocks, excluded = [], {"etf/etn": 0, "spac": 0, "fund-class": 0, "konex/other": 0}
    for c, s in raw.items():
        name = s["stockName"]
        if s.get("stockEndType") != "stock":
            excluded["etf/etn"] += 1
            continue
        if s.get("sosok") not in ("0", "1"):
            excluded["konex/other"] += 1
            continue
        if "스팩" in name:
            excluded["spac"] += 1
            continue
        if re.search(r"클래스$", name):
            excluded["fund-class"] += 1
            continue
        stocks.append(s)

    pin = a.close == "krx" or (a.close == "auto" and any(v != "OPEN" for v in mstat.values()))
    end = session_end_of(raw.values())          # '1530', or '1630' on 수능 day / first trading day of the year
    trade_ymd = (idx_ts[0] or "")[:10].replace("-", "") if idx_ts else dt.datetime.now(KST).strftime("%Y%m%d")
    closes = {}
    if pin:
        # A finished day's 15:30 closes never change -> cache them so same-day re-runs are fast.
        cache_path = os.path.join(a.cache_dir, f"krx_close_{trade_ymd}_{end}.json")
        end_dt = dt.datetime.strptime(trade_ymd + end, "%Y%m%d%H%M").replace(tzinfo=KST)
        session_over = dt.datetime.now(KST) >= end_dt + dt.timedelta(minutes=1)
        if not session_over:
            # forced pinning before the real session end (e.g. 16:10 run on a 16:30 day) would pin to a
            # half-finished session -> don't; the output says close="naver" so the build skips close.json
            print(f"[4/4] WARNING: session ends {end[:2]}:{end[2:]}, not over yet -> NOT pinning (close=naver)",
                  file=sys.stderr)
            pin = False
    if pin:
        if session_over and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                closes = {k: tuple(v) for k, v in json.load(f).items()}
        todo = [s for s in stocks if s["itemCode"] not in closes]
        print(f"[4/4] KRX close pinning (date {trade_ymd}): {len(stocks) - len(todo)} cached, "
              f"{len(todo)} to fetch", file=sys.stderr)
        t0 = time.time()

        def job(s):
            return s["itemCode"], krx_close(cli, s["itemCode"], trade_ymd, end)

        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for i, (c, res) in enumerate(ex.map(job, todo), 1):
                closes[c] = res
                if i % 250 == 0:
                    print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", file=sys.stderr)
        if session_over:
            os.makedirs(a.cache_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({k: v for k, v in closes.items() if v[1] is not None}, f)
    else:
        print("[4/4] skipping KRX close pinning (raw Naver prices)", file=sys.stderr)

    out, n_etc, n_pinned, n_moved = [], 0, 0, 0
    max_ts = ""
    for s in stocks:
        c = s["itemCode"]
        ind = code2ind.get(c) or "기타"
        sec = SECTOR_MAP.get(ind, "기타")
        if ind == "기타":
            n_etc += 1
        p = num(s.get("closePriceRaw") or s.get("closePrice"), int)
        d = num(s.get("compareToPreviousClosePriceRaw") or s.get("compareToPreviousClosePrice"), int) or 0
        r = num(s.get("fluctuationsRatio")) or 0.0
        cap_krw = num(s.get("marketValueRaw"))
        cap = cap_krw / 1e8 if cap_krw else (num(s.get("marketValue")) or 0)
        base = p - d
        flag = (s.get("compareToPreviousPrice") or {}).get("name")
        lim = 1 if flag == "UPPER_LIMIT" else -1 if flag == "LOWER_LIMIT" else 0
        if pin and c in closes:
            kp, _any = closes[c]
            if kp is None and _any:      # traded only after hours (or not at all) -> close = 기준가
                kp = base
            if kp is not None and base > 0:
                n_pinned += 1
                moved = kp != p
                if moved:
                    n_moved += 1
                    # the Naver flag follows the after-hours price; re-derive it from the pinned
                    # 15:30 close (a limit move is always >= ~29.5%, see ENDPOINTS_EXTRA.md §5)
                    cap = cap * kp / p if p else cap
                p, d = kp, kp - base
                r = round(d / base * 100, 2)
                if moved:
                    lim = 1 if r >= 29.5 else -1 if r <= -29.5 else 0
        tv = num(s.get("accumulatedTradingValueRaw"))
        tv = round(tv / 1e8) if tv is not None else round((num(s.get("accumulatedTradingValue")) or 0) / 100)
        v = num(s.get("accumulatedTradingVolumeRaw") or s.get("accumulatedTradingVolume"), int) or 0
        max_ts = max(max_ts, s.get("localTradedAt") or "")
        row = {"c": c, "n": s["stockName"], "m": "K" if s["sosok"] == "0" else "Q",
               "s": sec, "i": ind, "cap": int(round(cap)), "p": p, "d": d,
               "r": round(r, 2), "tv": int(tv), "v": v}
        if lim:
            row["lim"] = lim  # 1 limit-up, -1 limit-down, omitted otherwise
        out.append(row)
    out.sort(key=lambda x: (-x["cap"], x["c"]))

    as_of = f"{trade_ymd[:4]}-{trade_ymd[4:6]}-{trade_ymd[6:]}T{end[:2]}:{end[2:]}:00+09:00" if pin else max_ts
    snap = {"asOf": as_of, "source": "네이버 증권 (m.stock.naver.com)", "marketStatus": mstat,
            "close": "krx" if pin else "naver"}     # krx = pinned to the regular-session end (closeAt), naver = raw
    if pin:
        snap["closeAt"] = end
    if index:
        snap["index"] = index
    snap["stocks"] = out
    path = os.path.join(a.out, "snapshot.json")
    with open(path, "w", encoding="utf-8") as f:  # compact, one stock per line
        head = json.dumps({k: v for k, v in snap.items() if k != "stocks"}, ensure_ascii=False,
                          separators=(",", ":"))[:-1]
        f.write(head + ',"stocks":[\n')
        f.write(",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in out))
        f.write("\n]}\n")
    print(f"wrote {path}: {len(out)} stocks ({sum(x['m'] == 'K' for x in out)} K / "
          f"{sum(x['m'] == 'Q' for x in out)} Q), 기타={n_etc}, backfilled={backfilled}, "
          f"excluded={excluded}, pinned={n_pinned}, price≠naver={n_moved}, asOf={as_of}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
