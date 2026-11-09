# Extra Naver endpoints for themes, news, disclosures, market strip, limits, period returns, investor flows

Probed from the sandbox on **2026-11-09 (Mon) ~21:45-22:00 KST**. Regular KRX session closed, NXT after-market closed at 20:00,
US index futures / WTI / gold trading (07:40 ET). Only calls that returned 200 with data today are listed as "chosen".
General rules (no cookies, `cache-control: no-store`, comma strings, `*Raw` twins, after-hours price caveat) are in `ENDPOINTS.md`.

**Origin check (every endpoint below):** no `Origin` -> 200. A foreign `Origin: https://x.workers.dev` -> **403** on `m.stock.naver.com/api/*`,
`api.stock.naver.com/*` and `polling.finance.naver.com/*`. The exception is `m.stock.naver.com/front-api/*`, which returned **200** even with a
foreign Origin. Fetch everything server-side in the Worker without forwarding the client `Origin`.
No endpoint here needs cookies or special headers. `m.stock.naver.com` responses are **not gzipped** (large); `api.stock` and `polling` are.

| # | Item | Chosen endpoint |
|---|---|---|
| 1 | Themes | `m.stock.naver.com/api/stocks/theme` + `/api/stocks/theme/{no}` (PC pages are dead) |
| 2 | Stock news | `m.stock.naver.com/api/news/stock/{code}?pageSize=20` |
| 3 | Disclosures | `m.stock.naver.com/api/stock/{code}/disclosure` (DART not needed) |
| 4 | Market strip | `api.stock.naver.com/chart/domestic/index/{KOSPI,KOSDAQ}/minute`, `m.stock.naver.com/front-api/worldstock/nation/indexFutures/list?nationType=USA`, `api.stock.naver.com/marketindex/{exchange,energy,metals,bond}...`, `m.stock.naver.com/front-api/cryptoEnd/detail` |
| 5 | Price limits | `polling.finance.naver.com/api/realtime/domestic/stock/{codes}` -> `compareToPreviousPrice.name` |
| 6 | Period returns | no bulk endpoint; per-stock `day` chart (or `front-api/.../periodChanges`) |
| 7 | Investor flows in bulk | none; per-stock `/api/stock/{code}/trend?pageSize=1` |

---

## 1. Themes (테마)

### 1a. Theme list
```
GET https://m.stock.naver.com/api/stocks/theme?page=1&pageSize=100        (200, 12 KB / page, uncompressed)
```
* `pageSize` max 100 (101 -> 400). **265 themes** in total (`totalCount`), so 3 pages (100 + 100 + 65). `page=4` is empty.
* Sorted by `changeRate` descending (moves intraday, so unioning by `no` while paginating is wise, as with 업종).
* `changeRate` is a signed string in %, `totalCount` = member count, rise/fall/steady counts are plain ints.
```json
{"stockListSortType":"THEME","totalCount":265,"page":1,"pageSize":100,"marketStatus":"CLOSE","localOpenTimeDesc":"",
 "groups":[{"no":228,"name":"국내 상장 중국기업","totalCount":10,"changeRate":"4.59","riseCount":9,"fallCount":1,"steadyCount":0},
           {"no":586,"name":"광통신(광케이블/광섬유 등)","totalCount":15,"changeRate":"4.47","riseCount":10,"fallCount":4,"steadyCount":1}]}
```

### 1b. Members of a theme
```
GET https://m.stock.naver.com/api/stocks/theme/{no}?page=1&pageSize=100   (200)
```
Response keys: `stockListSortType, groupInfo{no,name,totalCount,changeRate,riseCount,fallCount,steadyCount}, themeDescription (Korean text),
themeItemInfoMap {code: one-line reason the stock is in the theme}, totalCount, page, pageSize, stocks[]`.
`stocks[]` rows have **exactly the same shape as the marketValue / industry rows** (`itemCode, stockName, sosok, closePrice, compareToPreviousClosePrice,
compareToPreviousPrice{code,name}, fluctuationsRatio, accumulatedTradingVolume, accumulatedTradingValue (억), marketValue (억), *Raw twins, stockExchangeType`),
so a theme page can be drawn directly from this call with no extra polling.
```json
{"itemCode":"900300","stockName":"오가닉티코스메틱","sosok":"1","closePrice":"2,950","compareToPreviousClosePrice":"680",
 "compareToPreviousPrice":{"code":"1","text":"상한","name":"UPPER_LIMIT"},"fluctuationsRatio":"29.96",
 "accumulatedTradingValue":"1,484","marketValue":"1,728","closePriceRaw":"2950","marketValueRaw":"172811286150"}
```
* Size: 10 members = 17.5 KB, 100 members = 179 KB (no gzip, about 1.8 KB per row, because of the nested `stockExchangeType`).
* Same caveat as 업종: rows are sorted by the live change rate, so rows can slip across page boundaries. Re-walk the pages and union by code until
  `totalCount` unique codes are collected. With this method **all 265 themes matched `totalCount` exactly**.

### 1c. Measured numbers (all 265 themes fetched)
* Total theme-member pairs: **6,565**. Unique stocks: **2,397** (KOSPI+KOSDAQ; only 1 preferred share; no ETFs).
* Members per theme: median **18**, min 2, max 147 (자동차부품 147, 2차전지 143, 지주사 127). Only 3 themes have more than 100 members.
* Themes per stock: median 2, 705 stocks in 1 theme, 332 stocks in 5 or more, 삼성전자 in **31** themes (the max). So one stock belongs to many themes;
  a heatmap should key by `itemCode` and keep `themes: [no,...]` per stock (the same tile is shown in each theme, or the theme filter just highlights tiles).
* **Cost to fetch everything:** 3 list calls + 265 member calls + 3 extra pages for themes over 100 = **268 member calls, 271 total**.
  With 8 parallel workers it took **29 s** (~35 MB uncompressed in total, mostly because of the row size). Themes change rarely
  (stock membership is edited by Naver editors, but the rise/fall data is live), so build the **code -> theme ids map offline or cache for hours**,
  and refresh only the 3 list pages (`changeRate`, counts) every 30-60 s.
* Cheapest live path: theme membership map (cached) + the existing 600-code polling call for prices. Only 2,397 codes are in any theme, so
  for tiles outside the top 600 a theme page fetch (`/theme/{no}`) gives live prices for that theme in one call.

### 1d. PC pages: dead
`https://finance.naver.com/sise/theme.naver` -> **302** to `https://stock.naver.com/market/stock/kr/theme` (JS SPA, no HTML table).
`sise_group_detail.naver?type=theme&no=228` -> 302, empty body. Use the m.stock JSON API above. (The same applies to `sise_deal_rank*` / `investorDealTrendDay`, see §7.)

---

## 2. Per-stock news

```
GET https://m.stock.naver.com/api/news/stock/{code}?pageSize=20[&page=2]      (200, ~17 KB for 20 clusters, uncompressed)
```
* Default page size is small; `pageSize=20` works, `page` works (page 2 returned different articles). Newest first.
* The response is an array of **clusters**: `[{"total":N,"items":[article]}, ...]`. `total` = number of similar articles collapsed into the cluster;
  `items` holds 1 article (the representative). Flatten with `.flatMap(c => c.items)`.
```json
[{"total":2,"items":[{"id":"0320003481653","officeId":"032","articleId":"0003481653","officeName":"경향신문","datetime":"202611092129","type":1,
  "title":"젠슨 황, 중 기업인과 불륜 인정…미·중 ‘반도체 전쟁’ 새 뇌관",
  "body":"엔비디아 “기밀 유출 근거 없어” 앨리스 황 ... ","imageOriginLink":"https://imgnews.pstatic.net/image/origin/032/2026/11/09/3481653.jpg?type=nf220_150",
  "mobileNewsUrl":"https://n.news.naver.com/mnews/article/032/0003481653","titleFull":"젠슨 황, 중 기업인과 불륜 인정…미·중 ‘반도체 전쟁’ 새 뇌관"}]}]
```
* Fields to use: `title` (or `titleFull`), `officeName` (press), `datetime` (**`YYYYMMDDHHmm`, KST, no seconds**), `mobileNewsUrl` (link; PC form
  `https://n.news.naver.com/mnews/article/{officeId}/{articleId}`).
* **HTML entities are escaped in `title`/`body`** (`&quot;`, `&lt;`), so decode them (use `textContent` or an entity decoder, never `innerHTML` on raw text).
* The path `/api/stock/{code}/news` returned the SPA 404 HTML page: not usable. The bundle only references `/news/...` through the
  `ITEM_NEWS_*` post types; the `news/stock/{code}` path above is the working one.

---

## 3. Per-stock 공시 (disclosures)

```
GET https://m.stock.naver.com/api/stock/{code}/disclosure[?pageSize=N][&page=P]     (200, 527 B for 3 rows)
```
* Default 20 rows; `pageSize=100` returns 100; `page=2` works. Newest first.
```json
[{"itemCode":"196170","disclosureId":183876371,"title":"(주)알테오젠 주식선물ㆍ주식옵션 3단계 가격제한폭 확대요건 도달(하락)","datetime":"2026-11-09T10:13:37","author":"KOSCOM"},
 {"itemCode":"900300","disclosureId":184089999,"title":"오가닉티코스메틱스홀딩스컴퍼니리미티드 유상증자결정(제3자배정)","datetime":"2026-11-09T15:11:18","author":"KOSCOM"}]
```
* `datetime` = ISO without zone, **KST**. `author` is the feed (`KOSCOM`), not the issuer.
  The feed mixes real 공시 (실적, 배당, 유상증자, 자기주식...) with KRX 시장조치 notices (가격제한폭 확대요건 도달 etc.). Filter by title if only business disclosures are wanted.
* **Link to the Naver detail page** (HTTP 200, verified): `https://m.stock.naver.com/domestic/stock/{code}/notice/{disclosureId}`.
  Detail JSON (HTML body in `contents`): `GET https://m.stock.naver.com/api/stock/{code}/disclosure/{disclosureId}` -> `{"itemCode","disclosure":{"disclosureId","datetime","contents":"<div class=\"xforms\">..."}}`.
  There is **no DART `rcept_no`** in this feed, so a direct DART link is not available from Naver; link to the Naver page.
* DART is therefore optional, **not needed**. If a DART link is ever wanted: OpenDART `GET https://opendart.fss.or.kr/api/list.json?crtfc_key=KEY&corp_code=00126380&bgn_de=20261001&end_de=20261109&page_count=20`
  (free key by registration, 20,000 calls/day) returns `rcept_no, report_nm, rcept_dt, flr_nm`; link = `https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}`.
  `corp_code` (8 digits) differs from the stock code and comes from `https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=KEY` (a ZIP with one XML: `corp_code, corp_name, stock_code, modify_date`;
  join on `stock_code`). Not tested (no key was registered).

---

## 4. Market strip

### 4a. KOSPI / KOSDAQ intraday line
```
GET https://api.stock.naver.com/chart/domestic/index/KOSPI/minute        (200; 393 bars, 58 KB raw / 8.9 KB gzip)
GET https://api.stock.naver.com/chart/domestic/index/KOSPI/minute5       (200; ~2 KB gzip; also minute10)
```
Same bar shape as the stock chart: `{"localDateTime":"20261109153200","currentPrice":5018.85,"openPrice":5019.78,"highPrice":5019.79,"lowPrice":5018.85,"accumulatedTradingVolume":16432}`
(first bar 09:00 = 5006.87, last 15:32 = 5018.85). After the close it stays at the last regular-session bar (index has no after-hours bars).
Baseline (previous close) is not in the chart: take it from `polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ`
(`closePriceRaw - compareToPreviousClosePriceRaw`, e.g. 5018.85 - (-40.84) = 5059.69). Foreign Origin -> 403.

### 4b. USD/KRW now + change
```
GET https://api.stock.naver.com/marketindex/exchange/FX_USDKRW           (200, 2.4 KB)
```
Fields in `exchangeInfo`: `closePrice "1,347.60"`, `fluctuations "-15.90"` (signed), `fluctuationsRatio "-1.17"` (%), `fluctuationsType{name:"FALLING"}`,
`localTradedAt "2026-11-09T21:51:23+09:00"`, `description "하나은행 고시회차"`, `degreeCount 747`, `marketStatus "OPEN"`.
This is the Hana Bank notice-round rate (near real time, updated every few minutes), not the interbank tick. `calcPrice` is the same value as a number.
Batch: `GET https://api.stock.naver.com/marketindex/exchange` returns `{normalList:[...59 items...], majorList:[...]}` (58 KB; includes `.DXY` dollar index 101.88 -0.41%, and every
`FX_xxxKRW` pair) with flat items `{reutersCode,name,closePrice,fluctuations,fluctuationsRatio,fluctuationsType,marketStatus,localTradedAt}`. There the same pair shows 1,347.30 -16.20 -1.19
(a slightly different source tick), so pick one source per screen.
Alternative front-api (same data, 2.3 KB): `https://m.stock.naver.com/front-api/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW`
(wrapped in `{isSuccess,result}`; 200 even with a foreign Origin).

### 4c. US index futures: ONE call for S&P 500, Nasdaq 100, Dow, Russell 2000 plus cash indices and VIX
```
GET https://m.stock.naver.com/front-api/worldstock/nation/indexFutures/list?nationType=USA        (200, 6.2 KB)
```
`nationType` must be one of `USA|CHN|HKG|JPN|VNM|ETC` (anything else -> 400 with the list). Response `{isSuccess,detailCode,message,result:[...]}`, 11 rows for USA:
```json
{"id":"EScv1","name":"S&P 500 선물","stockEndType":"futures","currentPrice":7455.75,"fluctuationsType":"RISING","fluctuations":"53.75","fluctuationsRatio":"0.73","marketStatus":"OPEN","localTradedAt":"2026-11-09T06:42:54-06:00"}
{"id":"NQcv1","name":"나스닥 100 선물","stockEndType":"futures","currentPrice":27265,"fluctuations":"179.75","fluctuationsRatio":"0.66","marketStatus":"OPEN"}
{"id":".INX","name":"S&P 500","stockEndType":"index","currentPrice":7376.86,"fluctuations":"23.13","fluctuationsRatio":"0.31","marketStatus":"CLOSE","localTradedAt":"2026-11-06T16:37:09-05:00"}
```
Others in the same call: `YMcv1` 다우 선물 51,894 (+0.99%), `RTYcv1` 러셀 2000 선물 2,793.4 (+1.19%), `.DJI .IXIC .NDX .SOX .DJT .VIX`.
Units: `currentPrice` is a number; `fluctuations` / `fluctuationsRatio` are signed strings (minus sign included); `fluctuationsType` RISING/FALLING.
`localTradedAt` has the exchange's UTC offset (CME is `-06:00`); the data is **10 minutes delayed** for futures (`delayTime:10` in the exchange info).
The cash indices still show the last close (11/06) because the US cash market is not open yet at that time.
Lower-latency alternative (polling host, comma list, 403 on a foreign Origin): `GET https://polling.finance.naver.com/api/realtime/worldstock/futures/EScv1,NQcv1`
-> `datas[{reutersCode,futuresName,closePriceRaw "7455.25",compareToPreviousClosePriceRaw "53.25",fluctuationsRatioRaw "0.72",compareToPreviousPrice{name},marketStatus,localTradedAt}]`,
`pollingInterval 7000`. Cash indices: `.../worldstock/index/.INX,.NDX` (`pollingInterval` 70000) and single `https://api.stock.naver.com/index/.INX/basic` (`closePriceRaw "7376.86"`).
The futures codes are not accepted by `api.stock.naver.com/index/{code}/basic` (409 `지원하지 않는 지수입니다`).

### 4d. Optional commodities, rates, crypto
* **WTI, Brent, gold, silver, copper in one call per category** (flat list of rows, 13 each, ~27 KB):
  `GET https://api.stock.naver.com/marketindex/energy` -> `CLcv1 WTI 88.31 -2.52 -2.77%` (OPEN, `-06:00`), `LCOcv1 브렌트유 95.03 -3.35%`, 한국 휘발유/경유 (OPINET).
  `GET https://api.stock.naver.com/marketindex/metals` -> `GCcv1 국제 금 4,124.60 +49.70 +1.22%`, `M04020000 국내 금 178,770 +1.18%` (KRX gold, CLOSE), `SIcv1 은`, `HGcv1 구리`.
  Row: `{reutersCode,name,closePrice,fluctuations,fluctuationsRatio,fluctuationsType,marketStatus,localTradedAt,unit}` (strings with commas, signed).
  Lighter single/multi polling (`pollingInterval 7000`, foreign Origin 403): `GET https://polling.finance.naver.com/api/realtime/marketindex/energy/CLcv1` and `.../metals/GCcv1`
  (`datas[{reutersCode,name,closePrice "88.33",fluctuations "-2.50",fluctuationsRatio "-2.75",marketStatus,localTradedAt,unit "USD/BBL"}]`; comma-separated codes are the documented pattern in the bundle: `/api/realtime/marketindex/{energy|metals|agricultural|transport|exchangeWorld}/{codes}`).
  The `exchange` category is **not** served by that polling path (404).
* **US 10Y yield:** `GET https://api.stock.naver.com/marketindex/bond/US10YT=RR` (the `=` may be URL-encoded as `%3D`) -> `closePrice "4.8620"` (%), `fluctuations "0.0025"` (%p), `fluctuationsRatio "0.05"`,
  `marketStatus OPEN`, `priceDataType REALTIME`, `localTradedAt 2026-11-09T07:49:59-05:00`. Other bond codes from the bundle: `US2YT=RR US30YT=RR KR2YT=RR KR10YT=RR KR30YT=RR JP10YT=RR DE10YT=RR CN10YT=RR`
  (only US10YT tested). `/marketindex/bond` (list) is 404.
* **Bitcoin (KRW, Upbit):** `GET https://m.stock.naver.com/front-api/cryptoEnd/detail?nfTicker=BTC&exchangeType=UPBIT` (`exchangeType` = `UPBIT|BITHUMB`; 1.4 KB; 200 with foreign Origin too) ->
  `result{currentPrice:101677000, fluctuations:"-783000", fluctuationsRatio:"-0.76", fluctuationsType:"FALLING", lastClosePrice:102460000, highPrice, lowPrice, globalPrice (USD), krwPremiumRate:0.89, localTradedAt:"2026-11-09T21:53:53.950"}`.
  `currentPrice` is KRW, **24/7**. `/front-api/cryptoEnd/priceChange?nfTicker=BTC&exchangeType=UPBIT` gives 1d/1w/1M/3M/6M/1y returns.
* Also found: `https://api.stock.naver.com/marketindex/standardInterest` and `/domesticInterest` (policy rates, CD, COFIX; slow-moving).

### 4e. Suggested strip (4 calls, all cacheable 10-30 s): `polling .../domestic/index/KOSPI,KOSDAQ` + `chart/domestic/index/{KOSPI,KOSDAQ}/minute5` x2, `front-api/.../indexFutures/list?nationType=USA`, `marketindex/exchange/FX_USDKRW`; optional `marketindex/energy` + `marketindex/metals`, `bond/US10YT=RR`, `cryptoEnd/detail`.

---

## 5. Price limits (상한가 / 하한가)

The bulk polling endpoint carries the flag; it does **not** carry the limit prices.
```
GET https://polling.finance.naver.com/api/realtime/domestic/stock/{code,code,...}      (<=1000 codes)
```
`datas[i].compareToPreviousPrice = {"code":"1","text":"상한","name":"UPPER_LIMIT"}`. Code table seen: `1 UPPER_LIMIT, 2 RISING, 3 UNCHANGED, 4 LOWER_LIMIT(하한), 5 FALLING`.
(The same `compareToPreviousPrice` object is present in the marketValue / industry / theme rows, so no extra call is needed.)
* Verified today: polling over all **2,397 theme stocks** (3 calls of 1000): UPPER_LIMIT 8, LOWER_LIMIT 1, RISING 1046, FALLING 1213, UNCHANGED 129. These counts equal exactly
  the number of stocks with `|fluctuationsRatioRaw| >= 29.5`.
  Limit-up: 머큐리 100590 (+29.99%, 4,400), 에코캡 128540 (+29.90%), 썸에이지 208640 (+29.96%), 아시아나IDT 267850 (+29.99%, KOSPI), 박셀바이오 323990 (+29.97%), 노을 376930 (+29.96%),
  한싹 430690 (+29.87%), 오가닉티코스메틱 900300 (+29.96%, 2,950). Limit-down: 애드바이오텍 179530 (-29.94%, 943).
  Note the tick rounding: a limit-up can be +29.87%, so do **not** test `>= 30`; use the flag.
* The flag is computed against the **current integrated price** (after-hours included; those rows were stamped 20:00 `afterMarket`), consistent with `closePriceRaw`.
  If the screen pins to the 15:30 KRX close (see `ENDPOINTS.md` §5), derive the flag from the 1-minute bar instead or label it as after-hours.
* Limit **prices** (if the tooltip needs them): legacy polling `GET https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:900300,179530` (EUC-KR) has `ul` (상한가) and `ll` (하한가) and `rf` (1 상한 ... 4 하한 ... 5 하락):
  `{"cd":"900300","sv":2270,"nv":2950,"cv":680,"cr":29.96,"rf":"1","ul":2950,"ll":1590,...}`. The modern JSON has no `ul/ll` fields (checked all 38 keys).
  The limit equals previous close x 1.3 / 0.7 rounded to the tick, so it is also computable from `p - d`.

---

## 6. Bulk daily closes for period returns: nothing cheaper than one call per stock

Checked and rejected: multi-code day chart (`.../item/005930,000660/day` -> 200 but body `[]`), marketValue / industry / theme rows (only `threeMonthEarningRate`, which is `"N/A"` for stocks),
PC pages (retired). No bulk historical endpoint was found in the m.stock bundle (all `/stock/domestic/*` paths are per-code).

**Option A (recommended): one `day` call per stock, one call covers all five reference dates**
```
GET https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime=20250901000000&endDateTime=20261109235959
```
14 months = ~247 bars, picks 1 week / 1 month / 3 months / last year-end (**2025-12-30**; there is no 12/31 bar, KRX closes on the last business day of the year) / 1 year ago from one response.
Use `closePrice` of the bar on or before each date. Measured (20 sequential calls, top-cap stocks, via the sandbox proxy):
**0.67 s mean per call (0.65 p50, 0.91 max), 50 KB raw / 7.3 KB gzip each**. Extrapolated to 600 stocks sequentially: ~400 s, 4.4 MB gzip (30 MB raw).
Parallel: 100 calls at concurrency 10 = 7.2 s; 100 calls at concurrency 25 = **3.1 s**, all 200, no throttling seen. So 600 stocks at concurrency 25 = **~20 s**.
Because closes are static after the day ends, compute once per day (cron / GitHub Action / Worker scheduled trigger writing to KV or a JSON file) and not per viewer.
**Cloudflare limit:** one Worker invocation may make at most 50 subrequests on the free plan (1,000 on paid), so 600 calls need the paid plan or an offline job split into batches.
Caveat from `ENDPOINTS.md` §2: today's bar and (we saw for 삼성전자 11/06 = 193,500 vs KRX 188,700) recent bars use Naver's integrated price (KRX+NXT), so period returns measured from a past day bar can differ slightly from KRX official closes.
Past reference dates match the official table (`/api/stock/{code}/price`: 11/02 230,000 and 10/12 251,000 identical).

**Option B: `periodChanges` (about 630 B per stock, no savings in call count)**
```
GET https://m.stock.naver.com/front-api/domestic/stock/periodChanges?itemCode=005930        (200, 632 B; foreign Origin -> 200)
```
```json
{"isSuccess":true,"result":{"periodChanges":[{"period":"1d","from":{"date":"2026-11-09","value":"188700"}},{"period":"1w","from":{"date":"2026-11-02","value":"230000"}},
 {"period":"1m","from":{"date":"2026-10-12","value":"251000"}},{"period":"3m","from":{"date":"2026-08-10","value":"230000"}},{"period":"6m","from":{"date":"2026-05-11","value":"285500"}},
 {"period":"1y","from":{"date":"2025-11-10","value":"100600"}},{"period":"3y",...},{"period":"5y",...},{"period":"10y",...}]}}
```
`value` = the close at that base date (matches the chart bars for 005930; `1d` = previous close, i.e. the 기준가). 20 sequential calls: 0.66 s each, **219 B gzip** each (33x smaller than option A),
but still **600 calls** and it has **no YTD (last year-end)** period. Base dates are Naver's own calendar-offset logic (1w = 7 days before, 1m, 3m, 6m = month offsets; weekends roll to a prior trading day). Use it only if YTD is dropped; the values for corporate-action stocks
looked split-adjusted (196170: 1y 401,654, 3y 49,783), which is a plus for return maths.

---

## 7. Investor flows in bulk: none found

* No bulk 외국인/기관 순매수 ranking: tried `m.stock.naver.com/api/stocks/{foreignerBuy,institutionBuy,investor,foreign,trend,quant}/KOSPI` (404),
  `/front-api/domestic/stock/list/sorted` (valid `sortType`: `marketValue priceTop quantTop up down newStock high52week low52week management`; no investor sort),
  `api.stock.naver.com/stock/domestic/trend` (404) and the PC ranking pages `finance.naver.com/sise/sise_deal_rank_iframe.naver` and `investorDealTrendDay.naver` (**410 Gone**), `sise_deal_rank.naver` (302).
  The m.stock bundle contains no investor-ranking path.
* **Per-stock fallback:** `GET https://m.stock.naver.com/api/stock/{code}/trend?pageSize=1` (200, **351 B**, uncompressed). Today's row **is present as of ~21:55 KST** (earlier at 17:15 it was not):
```json
[{"itemCode":"005930","bizdate":"20261109","foreignerPureBuyQuant":"-458,714","foreignerHoldRatio":"45.93%","organPureBuyQuant":"+1,509,865","individualPureBuyQuant":"-817,749",
  "closePrice":"187,000","compareToPreviousClosePrice":"-1,700","accumulatedTradingVolume":"19,831,935"}]
```
  Units: net buy in **shares (주), signed strings** (no KRW value; multiply by close for an approximation). 100 of 100 top-cap stocks returned the 11/09 row.
  Measured: 20 sequential = 13.1 s (0.65 s each); 100 calls at concurrency 25 = 3.2 s. **600 stocks = 600 calls, ~0.2 MB total, ~20 s at concurrency 25.**
  Publication timing: after the close the row appears sometime in the evening, so during the session the latest row is the previous trading day. Same Cloudflare subrequest limit as §6; cache for hours and refresh once in the evening.
