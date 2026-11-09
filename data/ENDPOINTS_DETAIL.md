# Naver / KRX endpoints for the per-stock detail view

Probed from the sandbox on **2026-11-09 (Mon) 17:10-17:25 KST** (regular session closed, NXT after-market
open until 20:00). Codes tested: 005930 (KOSPI), 196170 (KOSDAQ). General rules (Origin 403, no cookies,
`cache-control: no-store`, strings with commas, after-hours price caveats) are in `ENDPOINTS.md` and not repeated.

**Origin check (re-verified on every endpoint below):** no `Origin` -> 200; `Origin: https://m.stock.naver.com` -> 200;
`Origin: https://x.workers.dev` -> **403**. The Worker must fetch without forwarding the client's `Origin`.
No cookies, no special headers needed. `Accept-Encoding: gzip` is honoured.

| Item | Chosen endpoint |
|---|---|
| 1 Candles | `api.stock.naver.com/chart/domestic/item/{code}/{minute,minute5,day,week,month}` |
| 2 Order book | `m.stock.naver.com/api/stock/{code}/askingPrice` (**5 levels only**, no 10) |
| 3 Investors | `m.stock.naver.com/api/stock/{code}/trend` |
| 4 Daily table | `m.stock.naver.com/api/stock/{code}/price` |
| 5 Short selling | **none** free without login |
| 6 Summary | `m.stock.naver.com/api/stock/{code}/integration` |

## 1. Price chart candles

```
GET https://api.stock.naver.com/chart/domestic/item/{code}/{interval}?startDateTime=...&endDateTime=...
```
Interval is one of `minute minute3 minute5 minute10 minute30 minute60 day week month` (see ENDPOINTS.md §2 for intraday).
Both bounds inclusive. Date param formats, tested on 005930:

| interval | accepted formats | notes |
|---|---|---|
| day | `YYYYMMDD`, `YYYYMMDDHHmm`, `YYYYMMDDHHmmss` all work | no params -> only today's bar |
| week | **14-digit `YYYYMMDDHHmmss` required** (8-digit returned `[]`) | bar `localDate` = the **Sunday** that starts the week (`20261108` = week of 11/09) |
| month | 14-digit (8-digit returned `[]` for a short range) | `localDate` = first of month (`20261101`) |
| minute/minute5 | 14-digit | |

Safe rule: always send 14-digit values (`...000000` start, `...235959` end).

Max range per call: **no cap found.** `day` from 20000101 returned 6,617 bars (157 KB gzip, whole history). Week from 2000 = 1,402 bars; month = 323 bars.
Practical sizes for 005930: 1y day = 244 bars / 6.4 KB; 3y day = 729 / 18 KB; 2y week = 98 / ~3 KB; 3y month = 37 / 1 KB.
Minute history is limited: `minute` from 20261001 returned bars only back to **20261030** (3,526 bars, 48 KB, about 6 sessions).
`minute5` for a past day: `startDateTime=20261106090000&endDateTime=20261106153000` -> 72 bars.

```json
// day (and week/month identical shape)  — values are floats in KRW; volume in shares
[{"localDate":"20261105","closePrice":201500.0,"openPrice":213000.0,"highPrice":213500.0,"lowPrice":199800.0,"accumulatedTradingVolume":24657743,"foreignRetentionRate":45.95},
 {"localDate":"20261109","closePrice":186600.0,"openPrice":187200.0,"highPrice":195400.0,"lowPrice":183800.0,"accumulatedTradingVolume":19030189,"foreignRetentionRate":45.94}]
// minute / minute5 (no params = today incl. after-hours; last bar was 17:16)
{"localDateTime":"20261109171600","currentPrice":186400.0,"openPrice":186200.0,"highPrice":186500.0,"lowPrice":186200.0,"accumulatedTradingVolume":2516}
```
Gotchas: week/month `closePrice` and today's day bar follow the **integrated (KRX+NXT) last price** and keep moving until 20:00
(same caveat as ENDPOINTS.md §2). `foreignRetentionRate` is a bonus field on day/week/month (%, 외국인 보유율, weekly/monthly = value at period end; it is rounded to integers in older history).
`accumulatedTradingVolume` is per-bar volume (shares). No `fluctuationsRatio` in candles; compute from the previous bar.
Alternative wrapper: `.../item/{code}?periodType=dayCandle|weekCandle|monthCandle` returns `{code, periodType, priceInfos:[...]}` (~3 KB, recent bars only); not needed.

## 2. Order book (호가) and trades (체결)

```
GET https://m.stock.naver.com/api/stock/{code}/askingPrice          (200, ~550 B, JSON, uncached)
```
```json
{"lastClosePrice":188700,"totalSell":"32,011","totalBuy":"40,290",
 "sellInfo":[{"price":"184,900","count":"2,248","rate":17},{"price":"184,800","count":"3,421","rate":26},{"price":"184,700","count":"2,683","rate":20},{"price":"184,600","count":"13,098","rate":100},{"price":"184,500","count":"3,285","rate":25}],
 "buyInfos":[{"price":"184,400","count":"2,559","rate":19},"... 4 more ...",{"price":"184,000","count":"11,980","rate":91}]}
```
* **Only 5 sell + 5 buy levels.** Query params (`?count=10`) are ignored. There is **no 10-level source** that I could find: the bundle only
  references `/api/stock/{code}/askingPrice` and `/api/stock/NXT/{code}/askingPrice`.
* `sellInfo` is ordered **highest ask first** -> best ask is the **last** element (verify: 184,500 is the lowest ask); `buyInfos` is best bid first.
  `price` is KRW (comma string), `count` is shares, `rate` = bar length 0-100 relative to the biggest level.
  `totalSell` / `totalBuy` = total ask / bid residual (총잔량, shares). It is larger than the sum of the 5 visible levels (32,011 vs 24,735), so it covers more than the 5 shown. `lastClosePrice` = 기준가 (number).
* Observed after-hours: the book is the KRX closing / 시간외 book, can sit away from the NXT last price (196170: book 165,600/165,000 vs last 166,800; 005930: asks 184.5-184.9k vs last 186.6k) and still changes between calls (totalSell 32,011 -> 32,411 -> 36,258 within ~1 min). During 09:00-15:30 it should be the live KRX book (not testable now).
* NXT variant `/api/stock/NXT/{code}/askingPrice` (from the bundle) returned **404 (HTML)** on m.stock.naver.com, api.stock.naver.com `/stock/{code}/askingPrice` and `/api/stock/NXT/...` returned 404 JSON. `polling.finance.naver.com/api/realtime/domestic/stock/{code}` has **no ask/bid fields** (checked all keys).
* Recent trades (체결 tick list): **none found.** `/api/stock/{code}/execution`, `/chart/domesticPriceByTime` (bundle path, 404 on api.stock) and the retired PC `sise_time` page do not work. Closest substitute is the 1-minute chart (§1) or `polling` last price.
* Cadence: Naver itself polls every ~7 s (`pollingInterval:7000`); cache 3-5 s in the Worker.

## 3. Investor trading trend (투자자별 매매동향)

```
GET https://m.stock.naver.com/api/stock/{code}/trend?pageSize=60        (200, 21 KB for 60 rows, ~3.5 KB for 10)
```
```json
[{"itemCode":"005930","bizdate":"20261106","foreignerPureBuyQuant":"-655,978","foreignerHoldRatio":"45.94%",
  "organPureBuyQuant":"-242,926","individualPureBuyQuant":"+858,557",
  "closePrice":"193,500","compareToPreviousClosePrice":"-8,000","compareToPreviousPrice":{"code":"5","text":"하락","name":"FALLING"},
  "accumulatedTradingVolume":"35,516,270"}, ...]
```
* Newest first. Default 10 rows; **`pageSize` max 60** (61 or 100 -> 400). `page=` is **ignored** (page=2 returned the same rows), so history is capped at the latest 60 trading days (60 rows = 20260810..20261106). Bundle uses a different cursor API (`/stock/domestic/trend` on api.stock, 404 here); not usable.
* Units: `*PureBuyQuant` = **net buy in shares (주), signed strings** with explicit `+`/`-` (**volume only, no KRW value**). `foreignerHoldRatio` = 외국인 보유율 % string. 개인 / 외국인 / 기관 (`organ`) are the only splits (no 연기금/투신 etc.).
* Update cadence: today's row (11/09) was **not present at 17:15**; last row 11/06. Naver publishes the day's investor tally after the close (it appears in the evening / next morning), so the table lags by one day intraday.
* `closePrice` / change in these rows is the integrated last price (11/06 shows 193,500, includes NXT), same caveat as §1. Also embedded as `dealTrendInfos` (10 rows) in `/integration`.
* No intraday (live) investor flow found.

## 4. Daily price history table (일별 시세)

```
GET https://m.stock.naver.com/api/stock/{code}/price?pageSize=60&page=1     (200, ~17 KB for 60 rows)
```
```json
[{"localTradedAt":"2026-11-09","closePrice":"186,600","compareToPreviousClosePrice":"-2,100","compareToPreviousPrice":{"code":"5","text":"하락","name":"FALLING"},
  "fluctuationsRatio":"-1.11","openPrice":"190,900","highPrice":"195,400","lowPrice":"183,800","accumulatedTradingVolume":27762353}]
```
* Newest first; default 20; **`pageSize` max 60**, `page` works (page=3 -> 2026-05-13..2026-02-11, page=9 -> 2024-11..2024-08), so 2+ years is available by paging.
* Ready-made columns: date, close, change (signed, with `compareToPreviousPrice.name` RISING/FALLING/UPPER_LIMIT/...), `fluctuationsRatio` %, OHL, volume (shares). Prefer this over deriving from candles.
* Note: this row's open/high/low/volume for today (190,900 / 195,400 / 183,800 / 27.7 M) is the **KRX** session (matches `/integration` and polling), whereas the chart-API day bar for today shows open 187,200 / vol 19.0 M (integrated), so the two sources disagree on today's bar. Pick one per screen.
* Change sign: `compareToPreviousClosePrice` already carries the minus (`-2,100`).

## 5. Short selling (공매도): **no free source without login**

* Naver: grepped all 42 JS chunks of `m.stock.naver.com/domestic/stock/005930/total` for `공매도` / `short`: **no hits**. Probed `/api/stock/{code}/short`, `/shortSelling`, `/shorting` (all 404, HTML), `api.stock.naver.com/stock/{code}/shortSelling` (404), PC `finance.naver.com/sise/sise_short.naver` (404). Naver has no short-selling data.
* KRX 정보데이터시스템: `POST https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd` with `bld=dbms/MDC/STAT/srt/MDCSTAT30001` (개별종목 공매도 거래) and `MDCSTAT30501` (순보유잔고), with `Referer: https://data.krx.co.kr/...`, browser UA, and a real `JSESSIONID` obtained by visiting the page first: **HTTP 400, body `LOGOUT`**. A control call with a non-short bld (`dbms/MDC/STAT/standard/MDCSTAT01501`, stock prices) gave the same `LOGOUT`, so the whole JSON endpoint now requires a logged-in KRX session (anonymous access has been removed), not just the short pages.
* `https://short.krx.co.kr` -> 301 to `data.krx.co.kr`; the old `SRT01010100.jsp` returns an error page.
* KRX Open API `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd` -> 401 `Unauthorized Key` (needs an issued API key; free signup but it is a key/login, and it does not cover the short balance anyway).
* data.go.kr (`apis.data.go.kr/1160100/...`) -> `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` (needs a key; no short balance dataset tried).
* Verdict: only workable path is a KRX login/cookie held as a Worker secret (fragile, likely against ToS) or a paid vendor. Recommend hiding the panel or showing "KRX 로그인 필요".

## 6. Company summary

```
GET https://m.stock.naver.com/api/stock/{code}/integration                   (200, ~9 KB, 005930)
```
`totalInfos[]` is a list of `{code,key,value}` (all strings, units embedded): `lastClosePrice 188,700`, `openPrice`, `highPrice`, `lowPrice`, `accumulatedTradingVolume 27,742,494`,
`accumulatedTradingValue "5조 2,979억"`, `marketValue "1,089조 1,617억"` (시총, Korean units), `foreignRate "45.94%"` (외인소진율), `highPriceOf52Weeks 380,000`, `lowPriceOf52Weeks 93,500`,
`per "8.36배"`, `eps "22,292원"`, `cnsPer`, `cnsEps`, `pbr "2.16배"`, `bps`, `dividendYieldRatio "0.90%"`, `dividend "1,668원"`.
Other keys: `industryCode "278"` (join with the industry list for the 업종 name) , `industryCompareInfo[]` (peer stocks), `consensusInfo {recommMean "4.00", priceTargetMean "472,381"}`, `researches[]`, `dealTrendInfos[]` (= §3, 10 rows), `description`/`iconInfos` (null for this stock).
Lighter alternatives: `https://m.stock.naver.com/api/stock/{code}/basic` (200, 4 KB: name, `sosok`, price, `stockExchangeType`, logo URL) and legacy
`https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}` (EUC-KR, adds numeric `highPriceOf52Weeks 374500`, `lowPriceOf52Weeks 94500`, `eps`, `bps`, `dv`, `countOfListedStock`, `ul/ll` 상/하한가). Note the 52-week figures differ between the two (380,000 vs 374,500; one is likely close-based, the other intraday), so pick one source and label it.
196170 (알테오젠) responded 200 on `askingPrice`, `trend`, `integration` and chart `day` with the same shapes.

## Worker cache suggestions
askingPrice 3-5 s; polling price 5-7 s; minute charts 10-30 s; day/week/month 60 s (5 min after close); trend/price table/integration 60-300 s.
