# Naver Finance endpoints for the KOSPI/KOSDAQ heatmap

Everything below was called from the sandbox on **2026-11-09 (Mon) between 16:10 and 16:35 KST**
(regular session closed; NXT after-market and KRX 시간외 단일가 still trading) and returned
HTTP 200 with data unless noted otherwise. No cookies or auth are needed. A browser User-Agent is
polite but not required (an empty UA also got 200). Samples are real but trimmed.

## 0. Rules that apply to every host (m.stock / polling / api.stock)

| Request `Origin` header | Result |
|---|---|
| none (server-side fetch) | **200**, no `access-control-allow-origin` header |
| `https://m.stock.naver.com` | 200 + `access-control-allow-origin: https://m.stock.naver.com` + `access-control-allow-credentials: true` |
| anything else (e.g. `https://heatmap.example.workers.dev`) | **403**, body `Invalid CORS request` |

* **The browser cannot call Naver directly.** The Worker has to fetch server-side and must not
  forward the client's `Origin` header (build a fresh `Headers`; don't pass `request.headers`
  through). Then it adds its own `Access-Control-Allow-Origin`. `Referer` is not checked (a foreign
  Referer still got 200).
* Upstream sends `cache-control: no-cache, no-store, max-age=0, must-revalidate`, so the Worker has
  to do its own caching (e.g. `caches.default` or `fetch(url,{cf:{cacheTtl:5,cacheEverything:true}})`)
  so that many viewers share one upstream call every 5–10 s.
* gzip: `polling.finance.naver.com` and `api.stock.naver.com` compress (send `Accept-Encoding: gzip`).
  `m.stock.naver.com/api/stocks/marketValue` came back uncompressed (~197 KB per 100 rows).
* Every number is a string (`"187,300"`); prefer the `*Raw` twins (`"187300"`).

## 1. (a) Live price refresh for the top ~300 per market: **one polling call**

```
GET https://polling.finance.naver.com/api/realtime/domestic/stock/{code},{code},...   (max 1000 codes)
```
* Tested with 50 / 100 / 300 / 600 / 1000 codes: all 200. **1001+ → 400**
  `getDomesticRealtimeStocks.itemCodes: size must be between 0 and 1000`.
  The URL for 1000 codes is ~7 KB, which was accepted.
* Response order matches the request order. Unknown codes are dropped silently (`000660,999999,005930` → 2 rows).
* Size and latency: 300 codes = 651 KB raw / **74 KB gzip** (~1.2 s). 600 codes = **130 KB gzip** (~1.7 s).
  1000 codes = 199 KB gzip (~1.3 s). Top-level `pollingInterval: 7000` is Naver's own hint (ms).
* **Recommendation:** take the top 300 codes per market from `snapshot.json` (already cap-sorted and
  ETF-free), send all 600 codes in one call every 10 s, and edge-cache it for 5–10 s.

```jsonc
// GET .../domestic/stock/000660,999999,005930   (trimmed: datas[0])
{"pollingInterval":7000,"time":"20261109162841","datas":[{
  "itemCode":"000660","stockName":"SK하이닉스",
  "closePriceRaw":"1117000","compareToPreviousClosePriceRaw":"-15000","fluctuationsRatioRaw":"-1.33",
  "openPriceRaw":"1130000","highPriceRaw":"1193000","lowPriceRaw":"1116000",
  "accumulatedTradingVolumeRaw":"4098377","accumulatedTradingValueRaw":"4741796000000",
  "marketValueFullRaw":"815959971705000",
  "marketStatus":"OPEN","marketStatusDetailType":"open","marketSessionType":"afterMarket",
  "localTradedAt":"2026-11-09T16:28:41.950027+09:00",
  "tradeStopType":{"code":"1","text":"운영.Trading","name":"TRADING"},
  "overMarketPriceInfo":{"tradingSessionType":"AFTER_MARKET","overMarketStatus":"OPEN","overPrice":"1,117,000",
     "compareToPreviousClosePrice":"-15,000","fluctuationsRatio":"-1.33","localTradedAt":"2026-11-09T16:28:41.950065+09:00", "...":"NXT"},
  "integratedPriceInfo":{"accumulatedTradingVolumeRaw":"...","accumulatedTradingValueRaw":"...","...":"KRX+NXT"}
  /* also: closePrice, compareToPreviousPrice{code,name}, isinCode, stockExchangeType{...}, currencyType */
}]}
```
Mapping to snapshot keys: `p=closePriceRaw`, `d=compareToPreviousClosePriceRaw`, `r=fluctuationsRatioRaw`,
`v=accumulatedTradingVolumeRaw`, `tv=round(accumulatedTradingValueRaw/1e8)`, `cap=round(marketValueFullRaw/1e8)` (억원).

Alternatives:
* **Legacy polling** (about 30% smaller, but harder to parse): `GET https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:005930,000660,...`.
  600 codes = 88 KB gzip. The body is **EUC-KR** (`text/plain;charset=EUC-KR`). Keys:
  `cd, nm, sv`(기준가) `, nv`(price) `, cv, cr` (**unsigned**; the sign comes from `rf`: 1 상한, 2 상승, 3 보합, 4 하한, 5 하락)
  `, ov, hv, lv, aq`(volume) `, aa`(value KRW) `, ms`(status) `, countOfListedStock, nxtOverMarketPriceInfo{...}`.
  Sample: `{"cd":"005930","sv":188700,"nv":186000,"cv":2700,"cr":1.43,"rf":"5","ms":"OPEN","aq":18579709,"aa":3551984812450.0,...}`
* **marketValue pages**: `GET https://m.stock.naver.com/api/stocks/marketValue/{KOSPI|KOSDAQ}?page=N&pageSize=100`
  (pageSize max 100, and 101 returns 400). The KOSPI list mixes in ETF/ETN rows (`stockEndType`), so it takes
  more than 3 pages to collect 300 stocks. Each page is ~197 KB uncompressed. The ranking shifts while you
  paginate, which can duplicate or drop rows (2 duplicates seen on KOSDAQ). Use this only to re-rank.

## 2. (b) Intraday chart for one stock (tooltip sparkline)

```
GET https://api.stock.naver.com/chart/domestic/item/{code}/{interval}
    [?startDateTime=YYYYMMDDHHmmss&endDateTime=YYYYMMDDHHmmss]
interval ∈ minute | minute3 | minute5 | minute10 | minute30 | minute60 | day | week | month
```
With no params it returns the latest trading day from 09:00 up to now. **After the close it keeps
adding after-hours bars (16:00–20:00)**. Add `endDateTime=YYYYMMDD153000` (or filter client-side) to
get only the regular session. Both bounds are inclusive.

| interval (005930, 16:27 KST) | bars | gzip size |
|---|---|---|
| minute | 425 (09:00→16:26) | 7.1 KB |
| minute5 | 87 (77 with `endDateTime=…153000`) | 1.7 KB |
| minute10 | 44 | 0.96 KB |
| minute30 / minute60 | 15 / 8 | 0.4 / 0.3 KB |

**Recommended sparkline call:** `https://api.stock.naver.com/chart/domestic/item/005930/minute5?startDateTime=20261109090000&endDateTime=20261109153000`
```json
[{"localDateTime":"20261109090000","currentPrice":189200.0,"openPrice":187200.0,"highPrice":191400.0,"lowPrice":187100.0,"accumulatedTradingVolume":2256143},
 {"localDateTime":"20261109090500","currentPrice":187200.0,"openPrice":189200.0,"highPrice":190100.0,"lowPrice":187000.0,"accumulatedTradingVolume":549010},
 "…",
 {"localDateTime":"20261109153000","currentPrice":189900.0,"openPrice":189900.0,"highPrice":189900.0,"lowPrice":189900.0,"accumulatedTradingVolume":1305675}]
```
* `currentPrice` is the bar close. Despite its name, `accumulatedTradingVolume` is **per-bar** volume.
  There are no bars for 15:20–15:29 (the closing call auction). The 15:30 bar is the KRX closing-auction print.
* Baseline for the sparkline (previous close / 기준가) = `p - d` from the snapshot.
* Daily: `.../item/005930/day?startDateTime=202611010000&endDateTime=202611092359` →
  `[{"localDate":"20261106","closePrice":193500.0,"openPrice":180000.0,"highPrice":196500.0,"lowPrice":179200.0,"accumulatedTradingVolume":35516270,"foreignRetentionRate":45.94},…]`.
  Also `.../item/005930?periodType=dayCandle` (wrapped `{code, periodType, priceInfos:[…]}`; `periodType=minute` returns 400).
  Caveat: the daily `closePrice` here is Naver's *integrated last price* (it includes NXT up to 20:00), **not** the KRX
  close. For example, 11/06 shows 193,500 while the KRX close and 11/09 기준가 is 188,700.
* Index intraday: `https://api.stock.naver.com/chart/domestic/index/KOSPI/minute` (same fields; 393 bars, ending 15:32).

## 3. (c) Index

```
GET https://m.stock.naver.com/api/index/KOSPI/basic        (also KOSDAQ, KPI200)
```
```json
{"stockEndType":"index","itemCode":"KOSPI","stockName":"코스피","closePrice":"5,018.85","compareToPreviousClosePrice":"-40.84",
 "compareToPreviousPrice":{"code":"5","text":"하락","name":"FALLING"},"fluctuationsRatio":"-0.81","marketStatus":"CLOSE",
 "localTradedAt":"2026-11-09T16:15:00+09:00","delayTimeName":"실시간", "...":"image chart URLs"}
```
Batch or poll both indices in one call: `GET https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ`
```json
{"pollingInterval":70000,"time":"20261109162827","datas":[{"itemCode":"KOSPI","closePriceRaw":"5018.85",
 "compareToPreviousClosePriceRaw":"-40.84","fluctuationsRatioRaw":"-0.81","openPriceRaw":"5034.20","highPriceRaw":"5172.94",
 "lowPriceRaw":"4990.66","accumulatedTradingVolumeRaw":"231798000","accumulatedTradingValueRaw":"17259903000000",
 "marketStatus":"CLOSE","localTradedAt":"2026-11-09T16:15:00+09:00"}, {"itemCode":"KOSDAQ","...":"..."}]}
```
The index `marketStatus` is the **regular-session** status (`CLOSE` after 15:30). Use it for the
open/closed badge. Stock rows say `OPEN` until 20:00 because of the after-market.

## 4. (d) CORS summary
None of the endpoints above sends `access-control-allow-origin` to a third-party origin, and a foreign
`Origin` header gets a 403. Proxying through the Worker is mandatory (see §0).

## 5. Data-quality gotchas (important for live mode too)
* **After 15:30, `closePrice` keeps moving.** It follows NXT after-market (15:40–20:00) and KRX 시간외 단일가
  (16:00–18:00). `compareToPreviousClosePrice` is still measured against the KRX 기준가. Example 삼성전자:
  기준가 188,700. KRX 15:30 close was 189,900 (**+0.64%**), but Naver showed 187,300 (**−0.74%**) at 16:15 and
  186,000 at 16:33. A non-NXT example is 앤디포스: KRX close 1,316 (−0.30%), Naver 1,409 (+6.74%).
  `scripts/build_snapshot.py --close auto` therefore pins every stock to its last 1-minute bar ≤ 15:30
  once the index status is not `OPEN`. For live mode, either stop polling after 15:30 or label after-hours prices as such.
* Volume and value (`accumulatedTradingVolume/Value` in marketValue and polling) are KRX-only (they include KRX
  시간외 trades). KRX+NXT totals are in `integratedPriceInfo`.
* `marketValue` in the list endpoint is in **억원** (comma string). `marketValueRaw` / `marketValueFullRaw` are in KRW.
* Preferred shares can be spotted by code: the last character is not `0` (`005935`, `005387`, `00680K`). Common stocks
  end in `0`, including the new alphanumeric codes like `0132G0`.

## 6. 업종 (industry) endpoints used by the build script
* List: `GET https://m.stock.naver.com/api/stocks/industry?page=1&pageSize=100` →
  `{"groups":[{"no":278,"name":"반도체와반도체장비","totalCount":173,"changeRate":"-0.70","riseCount":120,"fallCount":48,"steadyCount":5},…],"totalCount":79}`
* Members: `GET https://m.stock.naver.com/api/stocks/industry/{no}?page=N&pageSize=100` → `{"groupInfo":{…},"totalCount":173,"stocks":[…same row shape as marketValue…]}`
  The member lists are sorted by the day's change rate, which keeps moving, so rows can slip across
  page boundaries mid-pagination. On the first run this dropped JW홀딩스 and 유니테크노. The build
  script re-walks the pages and unions them by code until it has `totalCount` unique rows.
  The rows include KONEX (`sosok:"2"`). Group `no=25` "기타" (1,549 rows) is ETFs, ETNs and 2 fund "X클래스" lines.
  The PC pages `finance.naver.com/sise/sise_group*.naver` were not needed. Other legacy PC pages are retired
  (`sise_day` 410, `sise_market_sum` 302).
* Sector validation source (official WICS constituents, by sector code G10…G55):
  `GET https://www.wiseindex.com/Index/GetIndexComponets?ceil_yn=0&dt=20261106&sec_cd=G45` →
  `{"info":{"CNT":686,…},"list":[{"CMP_CD":"005930","CMP_KOR":"삼성전자","SEC_CD":"G45","SEC_NM_KOR":"IT","IDX_NM_KOR":"WICS IT",…},…]}`
