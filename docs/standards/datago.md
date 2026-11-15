# 공공데이터포털(apis.data.go.kr) — 구현 메모

> **상태: 구현 `feat/datago` (2026-11-15).** 결정은 AGENTS §3-32(사용자 2026-11-15 17:21 "추천대로하고 추가적으로 7번만 다음에 고려해보자"). 원문 명세(활용가이드)는 사용자가 올린 파일이라 저장소에 넣지 않아요 — 아래 필드 · 오퍼레이션 이름은 거기서 옮겼어요.
> 코드: `worker/src/datago.js`(공용 도우미) · `datago_crno.js`(법인등록번호 표) · `datago_funds.js`(증시 자금) · `datago_routes.js`(경로) · `src/world/world.js`(지표 탭 "증시 자금"). 점검: `qa/datago/*.mjs` · `qa/world/test_funds.py`.

## 0. 한 줄 규칙

키는 Worker 비밀값 **`DATA_GO_KR_KEY` 하나**, 요청 URL에만 들어가요. 금융위원회 자료는 **하루 한 번**(보통 다음 영업일 13시 이후)이라 요청마다 부르지 않고, **KV에 마지막 성공본을 두고** 각자의 `due()`가 말할 때만 새로 받아요. 실패하면 그 사본을 `stale`로 내주고 모든 colo가 잠깐 쉬어요.

## 1. 키

- 공공데이터포털 키는 두 가지 철자로 나와요: **Encoding**(이미 URL 인코딩, `%2B %2F %3D`)과 **Decoding**(원문, `+ / =`). 새 키는 16진수 문자열이에요. 비밀값에 무엇을 넣었든 `dgKey()`가 앞뒤 공백을 지우고 `%xx`가 있으면 한 번 풀어요 → URL에는 `encodeURIComponent`로 **정확히 한 번** 인코딩해서 넣어요(두 번 인코딩한 `%252B`가 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`의 흔한 원인).
- 키는 URL에만: 오류 문구는 코드별 고정 문장(`DgErr`), `fetch` 예외의 메시지는 쓰지 않고(런타임에 따라 URL이 들어가요), 저장하는 문자열(오류 기록)은 `scrub()`이 키의 모든 철자와 `serviceKey=…`를 `[key]`로 바꿔요. 콘솔에는 아무것도 쓰지 않아요.
- 점검: 세 철자 모두 같은 `serviceKey`가 되는지, `%25`가 없는지, 키를 되돌려 주는 상류 오류(XML · JSON · 게이트웨이)가 KV · 응답 · 예외 · 콘솔 · 상태 경로 어디에도 남지 않는지(`qa/datago/test_datago.mjs` · `test_funds.mjs` · `test_crno.mjs`).

## 2. API 목록 (§3-32에서 넣기로 한 것)

| id | 서비스 | 경로 (`https://apis.data.go.kr` 뒤) | 지금 쓰는 오퍼레이션 | 쓰는 곳 | 하루 상한(우리) |
|---|---|---|---|---|---|
| `kofia` | 금융위원회_금융투자협회종합통계정보 | `/1160100/service/GetKofiaStatisticsInfoService` | `getSecuritiesMarketTotalCapitalInfo`(증시자금추이) · `getGrantingOfCreditBalanceInfo`(신용공여잔고추이) | `/api/funds` | 300 |
| `krx` | 금융위원회_KRX상장종목정보 | `/1160100/GetKrxListedInfoService_V2` | `getItemInfo_V2` | `crnoOf()` (다른 경로용) | 100 |
| `lend` | 금융위원회_주식대차정보 | `/1160100/GetStocLendBorrInfoService_V2` | — (다음 작업) | 종목 페이지 대차 | 1,000 |
| `issu` | 금융위원회_주식발행정보 | `/1160100/GetStocIssuInfoService_V3` | — | 보호예수 → 캘린더 | 1,000 |
| `divi` | 금융위원회_주식배당정보 | `/1160100/GetStocDiviInfoService_V2` | — | 배당 | 1,000 |
| `corp` | 금융위원회_기업기본정보 | `/1160100/service/GetCorpBasicInfoService_V2` | — | 기업 기본 | 1,000 |

- 오퍼레이션 이름은 활용가이드의 **Call Back URL** 철자를 따라요(목록 표의 `GetSecuritiesMarketTotalCapitalI nfo`는 대문자 G에 줄바꿈 — 오타로 봐요).
- 포털 쪽 한도: 개발계정은 보통 API마다 하루 10,000번이에요. 우리 상한은 그보다 훨씬 낮게 두고(`DG_APIS[*].cap`), Worker 비밀값 **`DATAGO_CAP`**(숫자)로 **낮추기만** 할 수 있어요 — `0`이면 모든 호출을 멈추고 KV 사본만 내줘요(끄기 스위치, §10).
- 이용허락: 금투협 통계는 **공공누리 1유형(출처표시)** → 화면에 "금융투자협회"를 적어요. KRX상장종목정보는 **공공누리 4유형 + 제3자 재배포 금지** → 법인등록번호 표는 Worker 안에서만 쓰고 그대로 내보내는 경로를 만들지 않아요.

## 3. 공용 도우미 `worker/src/datago.js`

```js
const run = new DgRun(env, DG_APIS.kofia)          // 갱신 한 번: 호출 수 · 하루 상한 · 키 확인
await run.call(op, params, { numOfRows, pageNo })   // 한 쪽 → {items, total, pageNo, numOfRows}
await run.list(op, params, { numOfRows, maxPages }) // 모든 쪽 → {items, total, pages, partial}
await dgSnapshot(env, ctx, spec)                    // KV 마지막 성공본 + due() + 쉬기 + 오류 기록 → {snap, stale, error?, partial?, refreshing?}
dgParse(status, contentType, text)                  // 봉투 해석 → {items, total} 또는 DgErr
```

- 요청: `serviceKey` 맨 앞, **`resultType=json` 언제나**, `numOfRows`는 1~**10,000**(활용가이드: 넘으면 10,000으로 잘려요), `pageNo`. 예약 이름(`serviceKey` · `resultType`)과 이상한 변수 이름은 거절(네트워크에 안 나가요). User-Agent `Mozilla/5.0 (compatible; panse/1.0; +https://panse.pages.dev)`, `accept: application/json`, **8초**(`AbortSignal.timeout`, 본문 읽기까지), 같은 요청 안에서 다시 시도하지 않아요. 한 갱신에 최대 20번.
- `list`: `totalCount`에 닿을 때까지 쪽을 넘겨요(`maxPages`에서 멈추면 `partial:true` — 표를 만드는 쪽은 이걸 실패로 봐요).
- `items` 모양: `{item:[…]}` · `{item:{…}}`(한 건) · `''`(없음) 모두 배열로.
- `spec = {api, key, ttlS, due(snap, now), build(prev, run, now), background?, memMs?}` — `build()`가 새 본문을 돌려주면 `at`을 붙여 KV에 쓰고(TTL `ttlS`), `DgErr`를 던지면 이전 사본을 지켜요. 일부만 실패하면 `run.errors.push(err)` + `{…, partial:[…]}`(새 사본은 쓰고, 오류 기록만 남기고, 쉬지 않아요). `background`이고 `ctx`가 있으면 지금 사본을 바로 주고 갱신은 `ctx.waitUntil`에서. 같은 isolate의 동시 갱신은 하나로 합쳐요. isolate 메모리에 사본을 `memMs`(기본 60초) 들고 있어요.
- 날짜(KST, 평일만 — 휴일 표는 없어요. 휴일은 "자료 없는 날"로 보여요): `expectedBasDt(now)` = **지금까지 공개됐어야 하는 가장 최근 영업일** = "가장 최근 평일 13:00"의 바로 앞 평일(월 14:00 → 금, 월 10:00 → 목, 토 → 목). `lastWeekdayAt(now, HHMM)`, `prevWeekday`, `nextKstMidnight`.

### 3-1. 봉투와 오류 코드

| 상류가 보내는 것 | 예 | 우리 코드 | 모든 colo 쉬기 (`datago:cool:<api>`) |
|---|---|---|---|
| JSON `response.header.resultCode` `00` | 정상 | — | — |
| `03` NODATA_ERROR (메시지가 인증 실패가 아니면) | 그날 자료 없음 | 빈 목록(오류 아님) | — |
| `30` · `31` · `32` · `33` · `21`, 또는 메시지에 SERVICE_KEY · 인증키 · 인증에 실패 · Unauthorized | 키 미등록 · 만료 · IP | `key` | 1시간 |
| `20` SERVICE_ACCESS_DENIED · HTTP 403 Forbidden | 활용 신청 안 됨 | `forbidden` | 1시간 |
| `12` NO_OPENAPI_SERVICE · HTTP 404 API not found | 경로 틀림 · 폐기 | `notfound` | 1시간 |
| `22` LIMITED_NUMBER… · HTTP 429 / 본문 "API token quota exceeded" | 하루 허용량 초과 | `quota` | **KST 자정까지** |
| HTTP 429 "API rate limit exceeded" | 동시 요청 초과 | `rate` | 10분 |
| `10` · `11` | 요청 변수 | `param` | 1시간 |
| `01` · `02` · `04` · `05` · `99`, HTTP 5xx "Error forwarding / receiving …", "Unexpected error" | 기관 서버 | `upstream` | 15분 |
| XML `<OpenAPI_ServiceResponse>…<returnReasonCode>` (HTTP 200이어도) | 옛 포털 오류 | 위 표대로(사유 코드 · `returnAuthMsg`) | 위와 같음 |
| XML `<response><header><resultCode>` | `resultType`을 무시한 정상 응답 | `<item>`을 평평하게 읽어요 | — |
| 시간 초과 · 연결 실패 · 깨진 JSON · 알 수 없는 모양 | | `timeout` · `network` · `json` · `shape` | 15분 |
| 우리 하루 상한 도달 | | `cap` (네트워크 안 나감) | KST 자정까지 |
| 키 없음 | | `nokey` (네트워크 안 나감) | 쉬지 않음 |

- 실패 기록 **`datago:err:<api>`**(3일, 같은 코드면 30분에 한 번) = `{at, api, code, op?, status?, resultCode?, msg?, coolUntil?, partial?}` — `msg`는 상류 `resultMsg`/`returnAuthMsg` 80자, 키는 지운 뒤. 공개하지 않고 `/api/datago/status`의 `lastError`로만 봐요.
- 하루 호출 수 **`datago:calls:<api>:<YYYYMMDD>`**(2일) — 갱신이 끝날 때 한 번 써요. colo끼리 겹쳐 쓰면 조금 덜 셀 수 있어요(isolate 메모리가 바닥을 지켜요).

## 4. 법인등록번호 표 `worker/src/datago_crno.js`

```js
await crnoOf(env, '005930', ctx)    // '1301110006246' | null
await crnoInfo(env, '005935', ctx)  // {code, crno, isin, name, corp, market, basDt, common?} | null
await crnoTable(env, ctx)           // {basDt, at, n, get(code)} | null   — 한 요청에서 여러 종목
```

- 원천 `getItemInfo_V2`(srtnCd · isinCd · crno · itmsNm · corpNm · mrktCtg). `srtnCd`의 앞 `A`를 떼서 6자 코드로. crno는 숫자만 13자리(아니면 `null` — 외국 회사는 국내 법인등록번호가 없어요).
- **우선주는 원천에 없어요** → 끝자리가 0이 아닌 코드는 보통주(앞 5자 + `0`, 예: 005935 → 005930, 00088K → 000880)의 crno를 주고 `common`에 그 코드를 적어요(같은 회사).
- KV **`datago:crno`**(약 250 KB, 10일) = `{v, at, basDt, n, withCrno, m:{코드:[crno, isin, 종목명, 법인명, 시장]}}`. **평일마다 13:10 이후 한 번**(처음엔 언제든) — `basDt`는 `expectedBasDt`, 비어 있으면(휴일) 하루씩 거꾸로 7평일까지, 2,000건씩 2쪽 안팎. 이전 표의 절반보다 작으면 믿지 않고 옛 표를 지켜요(`shape`). 실패해도 옛 표가 답해요.
- `ctx`를 넘기세요: 갱신 때가 되면 지금 표로 바로 답하고 갱신은 `ctx.waitUntil`에서. `ctx`가 없으면 갱신을 기다려요(최대 8번 호출). 키가 없거나 표가 아직 없고 받지 못하면 `null` — 부르는 쪽은 `crnoTable()`이 `null`이면 503 같은 "아직 없어요"로 답하면 돼요.

## 5. 증시 자금 `GET /api/funds` (`worker/src/datago_funds.js`)

```
GET /api/funds → {asOf, basDt, source:'금융투자협회', items:[{key, name, value, change, ratio, unit, basDt, prev, prevDt}], stale?, partial?}
GET /api/funds/chart/{key}?tf=3m|1y → {key, name, tf, unit, bars:[{t:'YYYY-MM-DD', c}]}   (영업일, 오래된 순, 92 · 366일)
```

| key | 이름 | 원천 (오퍼레이션 · 필드) | 단위 |
|---|---|---|---|
| `deposit` | 투자자예탁금 | 증시자금추이 `invrDpsgAmt`(장내파생상품 거래예수금 제외) | 억원 |
| `credit` | 신용융자 전체 | 신용공여잔고추이 `crdTrFingWhl`(유가 + 코스닥) | 억원 |
| `creditKospi` | 신용융자 코스피 | `crdTrFingScrs` | 억원 |
| `creditKosdaq` | 신용융자 코스닥 | `crdTrFingKosdaq` | 억원 |
| `unpaid` | 위탁매매 미수금 | 증시자금추이 `brkTrdUcolMny` | 억원 |
| `forced` | 반대매매 | `brkTrdUcolMnyVsOppsTrdAmt`(미수금 대비 실제 반대매매 금액, 그날 하루) | 억원 |
| `forcedRatio` | 반대매매 비중 | `ucolMnyVsOppsTrdRlImpt`(미수금 대비 %) | % |

- 고른 까닭: 시장 화면들이 매일 보여 주는 "증시 대기 자금 · 빚투" 묶음이 이 일곱이에요(사용자 §3-32: 고객예탁금 · 신용융자 · 미수금 · 반대매매 비중). **넣지 않은 것**: 신용거래대주(작음) · 예탁증권 담보융자 · 청약자금 대출 · 장내파생상품 거래예수금 · RP 매도잔고(시장 화면에서 드묾) · CMA · 펀드 순자산(다른 오퍼레이션, 다음에 쉽게 더할 수 있어요) · 신탁 · ELS/DLS · 해외파생(월 1회).
- 값: 원 → **억원**(소수 둘째 자리), 비중은 %. `change`·`ratio` = **바로 앞 행(앞 영업일)** 대비(휴일을 건너뛰어요), 비중의 `change`는 %p. 좋고 나쁨의 뜻은 없어요 — 화면이 방향으로만 색칠해요.
- 받기: 갱신마다 두 오퍼레이션을 **한 번씩**, `beginBasDt` = 400일 전, `endBasDt` = 내일(활용가이드: endBasDt는 "작은" = 미포함), `numOfRows` 1,000(행은 약 270). 한쪽만 실패하면 다른 쪽 새 행은 들어가고 실패한 쪽은 이전 행 그대로(`partial:['credit']` 식, 소프트 오류 기록, 쉬지 않음). 둘 다 실패하면 이전 사본 + `stale:true`, 사본도 없으면 **503** `{error, code}`(엣지 캐시 안 함).
- KV **`datago:funds`**(약 35 KB, 10일) = `{v, at, basDt, opDt:{cap, credit}, series:{key:[[YYYYMMDD, 값]…]}, partial?}`.
- **언제 다시 받나(`fundsDue`)**: 두 오퍼레이션의 최신 날짜가 `expectedBasDt` 이상이면 **6시간**마다, 하나라도 뒤처졌으면 평일 13:00~20:00엔 **30분**, 그 밖엔 **3시간**마다. 그 위에 **엣지 캐시 1시간**(stale이면 10분) — 그래서 새 영업일 자료는 공개 뒤 보통 1시간 안팎에 보여요(시뮬레이션: 13:40 공개 → 20분 뒤).

## 6. 화면 (지표 탭, `src/world/world.js`)

- `kind=commodity&with=fx,rates`를 받을 때 `api/funds`도 따로 받아요 — **10분에 한 번까지**(30초 시세 갱신마다가 아님), 실패하면 2분 뒤. 받은 항목은 `gkey:'funds'` 묶음 "증시 자금"으로 **환율 · 금리 다음**에 붙어 같은 덩어리가 돼요(제목 줄 "환율 · 금리 · 증시 자금", 1920은 세 단, 1280은 환율+금리 | 증시 자금, 휴대폰은 한 단). 행 키는 `fd:<key>`.
- **옛 Worker(경로 없음, 404)** → 그 페이지에선 다시 묻지 않고 묶음이 없어요(지표 탭은 예전 그대로). 503 · 빈 목록 · 네트워크 실패 → 묶음 없음(이미 받은 값이 있으면 그대로).
- 행: 이름(+ 보조 글자 "하루 금액" · "미수금 대비") · 상태 칸 = **그 영업일 `11.13`**(장중/마감 점 없음) · 값 `78.51조원` / `9,303억원` / `48.0억원`(1조 이상 조원 소수 둘, 100억 이상 억원 정수, 그 아래 소수 하나) · 변화 `+1,235억원`(부호 있음, 0으로 반올림되면 부호 없음) · 칩 `+0.16%`(비중은 `−0.2%p`, 변화 칸은 비움 — 금리 bp와 같은 규칙) · 0 기준 막대.
- **색은 숫자의 오르내림만**(금리와 같아요): 칩 = `KH.colorOf(ratio)`, 변화 글자 = 상승/하락 글자색. 머리 오른쪽 메모 "색은 늘고 준 것만", 시트 메모 "빨강·초록은 전 영업일보다 늘었는지 줄었는지만 나타내요. 늘었다고 좋거나 나쁘다는 뜻은 아니에요." 투자 조언처럼 읽힐 말은 쓰지 않아요.
- 머리: "증시 자금 · 11월 13일 (금) 기준 · 색은 늘고 준 것만". 묶음 맨 아래 출처 줄 **"금융투자협회 · 하루 한 번(전 영업일 기준)"**(`--fs-xs`, `--faint`, `--space-*`), 탭 출처 문단에 "증시 자금은 금융투자협회 통계(금융위원회 공공데이터포털)로 하루 한 번, 전 영업일 값으로 바뀌어요 — 지금 11월 13일 (금) 자료."
- 빼는 곳: 요약 줄 · 많이 오른/내린 · 지금 열린 시장 · **색 범위 자동**(하루 지난 통계라 범위를 정하지 않고 색만 받아요).
- 시트: "증시 자금 · 금융투자협회" · 이름 + "하루 한 번" · 값 + 변화(%) · 기준일 · 전 영업일(값 + 날짜) · 단위 · 갱신("하루 한 번 · 보통 다음 영업일 오후에 올라와요") · 기준 · 항목 설명 + 색 메모 · 차트 `3개월 · 1년`(`api/funds/chart/…`, "영업일마다 · 금융투자협회", 금액은 기간 %, 비중은 %p, 마지막 점 = 목록 값) · 출처 줄. 차트 경로가 없으면(404) 차트 칸만 숨겨요.
- 스냅샷(아티팩트): 지표 탭 안내 문구에 "증시 자금(금융투자협회)은 하루 한 번".

## 7. 상태 경로 `GET /api/datago/status[?warm=1]`

`{now, key:boolean, expectedBasDt, apis:{kofia, krx}:{name, calls, cap, cool, lastError}, snapshots:{funds:{basDt, at, opDt, points, partial?}|null, crno:{basDt, at, n, withCrno}|null}}`, `no-store`. 키 · URL · 법인등록번호 표는 없어요. `warm=1`이면 두 사본의 `due()`를 먼저 돌려요(때가 아니면 아무것도 부르지 않아요) — 배포 직후 확인용.

## 8. 호출량 (하루 추정)

| | 평소 | 최악 |
|---|---|---|
| 증시 자금 (갱신당 2번) | 평일 6번 갱신 ≈ **12번**(점검 시뮬레이션: 2분마다 요청 · colo 둘 · 13:40 공개 → 12번) | 자료가 하루 늦게 계속 뒤처지면 13~20시 30분 · 그 밖 3시간 ≈ 40번, 엣지 캐시 때문에 실제로는 시간당 colo 하나 |
| 법인등록번호 표 | 평일 1번 갱신 = 2번(+ 휴일마다 1번), 주말 0 | 7평일 거꾸로 + 2쪽 = 9번 |
| 합계 | **≈ 15번/일** | ≈ 50번/일 — 상한 300 · 100, 포털 10,000과 거리가 멀어요 |

KV: 쓰기는 갱신마다 사본 1 + 계수 1(+ 실패 시 쉬기 · 기록), 하루 20번 안팎. 읽기는 엣지 캐시가 빗나갈 때만.

## 9. KV 키 (`REPLAY`, `list` 안 씀)

| 키 | 내용 | TTL |
|---|---|---|
| `datago:funds` | 증시 자금 시계열 사본 | 10일 |
| `datago:crno` | 종목코드 → 법인등록번호 표 | 10일 |
| `datago:calls:<api>:<YYYYMMDD>` | 그날 호출 수 | 2일 |
| `datago:cool:<api>` | 쉬는 중 `{code, until}` | 쉬는 동안 |
| `datago:err:<api>` | 마지막 실패 기록 | 3일 |

## 10. 운영 (runbook)

1. **배포 뒤 확인**: `GET /api/datago/status?warm=1` → `key:true`, `snapshots.funds.basDt`가 `expectedBasDt`와 같거나 하루 안, `points.deposit` 250 이상, `snapshots.crno.n` 2,500 이상 · `withCrno`가 거의 같음, `apis.*.lastError` 없음. 그다음 `GET /api/funds` 7항목 · 값이 그럴듯한지(투자자예탁금 수십 조원, 신용융자 전체 = 코스피 + 코스닥, 반대매매 비중 0~수 %) · 지표 탭에 "증시 자금" 묶음.
2. **`lastError.code`로 원인 보기**: `key` → 비밀값 철자(앞뒤 공백 · 따옴표) · 포털 키 상태 · 활용기간; `forbidden` → 그 API 활용 신청 · 승인; `notfound` → 오퍼레이션 철자(대소문자) · 서비스 경로; `quota` → 포털 하루 한도(자정에 풀려요); `rate` → 잠깐 뒤 저절로; `upstream` · `timeout` → 기관 서버(15분 뒤 다시); `empty` → 그 범위에 자료가 없음(휴일 · 공개 지연 · 날짜 계산); `shape` → 응답 모양이 바뀜(필드 이름을 활용가이드와 비교). `partial:true`면 두 오퍼레이션 중 하나만 실패(`op`에 이름).
3. **멈추기**: Worker 비밀값 `DATAGO_CAP=0`(배포 스크립트가 지키는 건 비밀값뿐이라 일반 변수 말고 비밀값으로) → 모든 공공데이터포털 호출을 멈추고 KV 사본만 내줘요(사본은 10일 뒤 만료). 숫자를 넣으면 API마다 그 수 아래로 낮춰요. 지우면 원래대로.
4. **키 바꾸기**: Cloudflare 대시보드(또는 `wrangler secret put DATA_GO_KR_KEY`)에서만 — 저장소 · 파일 · 로그 · 메모리에 쓰지 않아요. 배포 스크립트는 `secret_text` 바인딩을 지켜요. 바꾼 뒤 `datago:cool:<api>`가 남아 있으면 그 시간까지 기다리거나(최대 1시간, quota는 자정) 키를 지워요.
5. **새 API 붙이기**(대차 · 기업기본 · 배당 · 보호예수): `DG_APIS`에 이미 있어요. `dgSnapshot(env, ctx, {api: DG_APIS.lend, key: 'datago:<이름>', ttlS, due, build})` 하나를 만들고, 종목별이면 `crnoOf(env, code, ctx)`로 법인등록번호를 얻어요. 종목별 호출은 요청마다 하지 말고 KV에 하루 한 번(또는 종목별 키 + 긴 TTL)으로.

## 11. 점검

- `node qa/datago/test_datago.mjs` — 봉투(JSON · 옛 XML · 게이트웨이 글자 · XML 정상), 키 세 철자 · 한 번 인코딩, 요청 변수, 쪽 넘김, 8초 · 시간 초과, 계수 · 상한 · 0 = 끄기, 마지막 성공본 · 쉬기 길이 · 자정까지 · 기록 30분, 동시 갱신 하나, 배경 갱신, 일부 실패, KST 날짜 규칙, 키 새는 곳 없음.
- `node qa/datago/test_crno.mjs` — 13시 규칙의 basDt, 2쪽, `A` 떼기, crno 정리 · 외국 회사, 우선주 → 보통주, 휴일 거꾸로, 7평일 빈 날, 평일마다 한 번(배경), 절반 미만 거절, 키 오류에도 옛 표, quota 자정, KV 없이, 키 없음.
- `node qa/datago/test_funds.mjs` — 진짜 라우터(`worker/src/index.js`)로 `/api/funds` 모양 · 단위 · 앞 영업일 대비(한글날 건너뜀) · 요청 범위, 일부 실패, 모두 실패(stale · 503), `due()`, 차트 경로 · 400, 상태 경로 · `warm`, 하루 호출 시뮬레이션, 상한, 키 새는 곳 없음.
- `python3 qa/world/test_funds.py` — `qa/world/mock_api.py`의 `/__mode?funds=empty|on|stale|partial|gone|fail|slow`(기본 `empty` — 다른 점검은 그대로)로 화면 전부(§6), 390 · 768 · 1280 · 1920 + 네 테마 390, 가로 넘침 0, 콘솔 오류 0.
