# AGENTS.md — 판세 (한국 증시 히트맵)

코스피·코스닥을 섹터 › 업종 › 종목 트리맵으로 보여 주는 Finviz 스타일 히트맵과, 종목을 누르면 열리는 종목 페이지예요.
사람과 에이전트가 모두 따르는 규칙이에요. 여기에 없는 작업 방식은 `agent-orchestration` 스킬 기본값을 따릅니다.

---

## 0. 결정 사항 (사용자, 2026-11-09)

- **색**: 상승은 빨강 계열, 하락은 초록 계열이 기본이에요(`krg`). HTS 색(빨강/파랑), 초록 상승(Finviz), 색각 친화는 선택지로만 둬요. 0%는 회색.
- **글꼴**: Pretendard Variable. 숫자는 `font-variant-numeric: tabular-nums`.
- **실시간 데이터**: 네이버 증권(비공식). 브라우저는 네이버를 직접 부를 수 없어요(외부 Origin → 403). 항상 Worker가 대신 받아요.
- **배포**: GitHub 공개 저장소 `yeahoonjun/korea-market-heatmap` + Cloudflare Worker `korea-market-heatmap`. Worker는 화면 파일을 저장소에서 읽어 와요.
- **주소**: **`https://panse.pages.dev`** — 사이트 이름 **판세**(사용자 2026-11-13 19:58, §3-26). Cloudflare Pages 프로젝트 `panse`의 `_worker.js`가 모든 요청을 서비스 바인딩 `API`로 Worker에 넘겨요. 옛 주소 `kospimap.pages.dev`(2026-11-09~11-13)는 이사 다리예요. Worker 주소 `korea-market-heatmap.ssslot.workers.dev`도 그대로 동작해요(cron·KV는 Worker에 있어요). 계정 서브도메인 `ssslot`은 SSSlot 게임 주소라 바꾸지 않아요.
- **종목 상세**: 전체 화면 종목 페이지. 차트(탭 = 봉 간격 `분 · 일 · 주 · 월 · 년` — 사용자 2026-11-14 08:10 "1분봉 5분봉 있는게 아니라 분봉으로 통합하고 누르면 1분봉 5분봉 10분봉 30분봉 60분봉 선택 가능하게": `분`을 누르면 탭에서 자라나는 고르기(`1 · 5 · 10 · 30 · 60분`, design.md §7 팝오버), 고른 간격이 탭 이름("30분" + 작은 꺾쇠); 처음 탭은 사용자 2026-11-13 22:38 `1분 · 5분 · 일 · 주 · 월 · 년`; 년봉은 월봉을 화면에서 묶음; 5·20·60·120 이동평균선 = 범례 토글(사용자 2026-11-14 "이동평균선 5일 20일 60일 120일 저 버튼들 레이아웃과 디자인 개선이 필요해보여" → design.md §7: 짧은 선 견본 + 기간 + 값, 켜짐 = 채운 견본 + `--fg`, 꺼짐 = 속 빈 견본 + `--muted`; 5일 선은 앰버와 겹치지 않게 분홍 `--ma-5`), 켜고 끄기 `khm.stock.ma`(간격마다), 간격 `khm.stock.iv`(`1m`…`60m` · `day` · `week` · `month` · `year`, 옛 `1m`·`5m` 그대로)) + 탭(호가 5단계 · 투자자 · 일별 시세 · 뉴스·공시). 공매도는 KRX 로그인이 필요해서 빼요. 뒤로 가기로 히트맵 복귀, 주소로 공유 가능.
- **스냅샷 아티팩트**(claude.ai): 네트워크가 막힌 미리보기예요. 종목 페이지의 실시간 기능은 "실시간 버전에서 볼 수 있어요" 안내 + 링크로 대신해요.

## 1. 폴더와 담당

| 경로 | 내용 | 담당 |
|---|---|---|
| `src/template.html` | 히트맵 화면 (HTML·CSS·JS 한 파일) | 히트맵 담당 |
| `src/stock/stock.js`, `src/stock/stock.css` | 종목 페이지 (빌드가 template에 끼워 넣어요) | 종목 페이지 담당 |
| `src/fonts/` | Pretendard 서브셋 + OFL 라이선스 | 오케스트레이터 |
| `worker/src/index.js` | Worker: 정적 파일 서빙 + `/api/*` 프록시 | Worker 담당 |
| `data/snapshot.json`, `data/sector_map.json` | 전 종목 + 업종·섹터 (생성 파일, 손으로 고치지 않음) | 데이터 담당 |
| `data/ENDPOINTS*.md` | 네이버·KRX 엔드포인트 실측 노트 | 데이터 담당 |
| `scripts/build_page.py`, `scripts/build_worker.mjs` | 빌드 | 오케스트레이터 |
| `scripts/build_snapshot.py`, `scripts/subset_font.py` | 데이터·폰트 생성 | 데이터 담당 |
| `dist/` | 스냅샷 페이지 (아티팩트로 게시) | 빌드만 |
| `web/` | 실시간 버전 정적 파일 (Worker가 저장소에서 읽음) | 빌드만 |
| `qa/` | 점검 스크립트 | QA |

남의 파일을 고쳐야 하면 직접 고치지 말고 보고서에 "요청"으로 적어요.

## 2. 명령어

```
python3 scripts/build_page.py            # dist/index.html(스냅샷), web/index.html·web/universe.json(실시간)
node scripts/build_worker.mjs            # worker/dist/worker.js (Cloudflare API 업로드용 단일 파일)
python3 -m http.server 8791 -d web &     # 로컬 ASSET_BASE
NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8791/ PORT=8788 node worker/dev/serve.mjs   # 로컬 Worker
python3 tmp/shot.py /home/claude/heatmap/dist/index.html    # 1440×900 / 390×844 스크린샷 → tmp/desk.png, tmp/mob.png
```
- 샌드박스에서 Node가 네이버에 닿으려면 `NODE_USE_ENV_PROXY=1`이 필요해요. curl·Python은 그냥 돼요. `wrangler dev`(workerd)는 네이버에 닿지 못해요.
- Playwright: `p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])`.
- 로컬 서버 포트: 오케스트레이터 8788, 에이전트는 8790번부터 하나씩. 끝나면 끄기.
- **Worker 자동 배포** (사용자 2026-11-13 23:55 "자동 배포 설정하기"): `.github/workflows/deploy-worker.yml` — `main`에 `worker/src/**`·`worker/wrangler.toml`·배포 스크립트가 바뀌어 올라오면(또는 Actions에서 수동 실행) `npm ci --prefix worker` → `node scripts/build_worker.mjs` → `node scripts/deploy_worker.mjs`. 배포 스크립트는 손으로 하던 것과 같은 PUT 한 번(`main_module: worker.js`, `wrangler.toml`의 호환 날짜·KV `REPLAY`, `keep_bindings: ['secret_text']` — `DART_KEY`는 Cloudflare에만). cron은 업로드와 따로 있어서, 매번 `wrangler.toml`의 `crons`와 비교해 다르면 맞춰요(로그에 `cron` 줄). 이미 같은 번들이 돌고 있으면 건너뛰고, 올린 뒤 `/api/time`이 답하지 않으면 바로 앞 버전으로 되돌리고 실패해요. 저장소 비밀값 **`CLOUDFLARE_API_TOKEN`**(Account › Workers Scripts › Edit)이 없으면 경고만 남기고 건너뛰어요. 화면(`web/`)은 지금처럼 푸시만으로 배포돼요. 토큰 값은 파일·로그에 쓰지 않아요.
- **Durable Object 클래스 규칙** (실시간 허브 `MarketHub`, `docs/standards/realtime.md` §6 · §13): DO 클래스를 **만들기 · 지우기 · 이름 바꾸기**(`wrangler.toml`의 `[exports.X]`)는 Cloudflare가 그 앞으로 되돌리지 못해서 **푸시로는 절대 안 올라가요** — 배포 스크립트가 아무것도 올리지 않고 `Worker NOT deployed` 경고(작업 요약에도)를 남기고 초록으로 끝나요. 그럴 땐 Actions › `deploy-worker` › Run workflow에서 **`allow_do_lifecycle`을 체크해 손으로** 돌려요(그 배포는 실패해도 되돌리기 없이 "고쳐서 앞으로"). 클래스가 있는지는 돌고 있는 Worker의 바인딩(`GET …/settings`)으로 판단하고, settings나 돌고 있는 번들(`/content/v2`)을 못 읽으면 추측하지 않고 **실패(exit 1)** 해요 — 다시 돌리면 돼요. 살아 있는 `[exports.X]`는 바인딩이 꼭 있어야 하고, 묘비는 `state = "deleted"` 또는 `state = "renamed"` + `renamed_to`만. 점검 `node qa/worker/test_deploy_script.mjs`.

## 3. 데이터 계약

**히트맵 행** (`snapshot.json`의 `stocks[]`, `/api/quotes`의 `stocks[]`)
`{c 코드, n 종목명, m 'K'|'Q', s 섹터, i 업종, cap 시총(억원), p 현재가, d 전일 대비, r 등락률(%), tv 거래대금(억원), v 거래량}`
- 우선주(코드 끝자리가 0이 아님)는 지도에서 빼요. 검색으로 고르면 넣어요.
- `/api/quotes`: `{asOf, source, marketStatus:{KOSPI,KOSDAQ}, afterHours, index:{KOSPI:{value,change,ratio},…}, stocks}`. `marketStatus`는 정규장 기준.

**종목 페이지 API** (Worker가 제공, 모두 JSON, `access-control-allow-origin: *`, 오류는 `{error}` + 4xx/5xx)
원천과 함정은 `data/ENDPOINTS_DETAIL.md`. 바꿀 때는 이 절부터 고쳐요. 날짜는 KST 기준 `YYYY-MM-DD`, 가격은 원, 수량은 주.

| 경로 | 응답 | 엣지 캐시 |
|---|---|---|
| `/api/stock/{code}/summary` | `{code, name, market:'K'\|'Q', price, change, ratio, marketStatus, per, eps, pbr, bps, dividendYield, high52, low52, marketCap(억원), foreignRate, asOf}` 없는 값은 `null` | 30초 |
| `/api/stock/{code}/chart?tf=1d\|5d\|3m\|1y\|3y\|10y[&warm=N]` | `{tf, interval, prevClose, bars:[{t,o,h,l,c,v}], pre?:[…]}` — `1d`=오늘 1분봉, `5d`=5분봉 약 5거래일, `3m`·`1y`=일봉, `3y`=주봉, `10y`=월봉. 분봉 `t`는 유닉스 초(UTC), 일·주·월봉 `t`는 `YYYY-MM-DD`. **`warm=N`(0~120, 이동평균용)이면 `pre`에 `bars` 바로 앞 봉을 최대 N개 같은 모양으로** — `bars`·`prevClose`는 그대로, 없으면 `pre` 생략(옛 화면 영향 없음) | 분봉 20초, 그 외 10분 |
| `/api/stock/{code}/chart?iv=1m\|5m\|10m\|30m\|60m\|day\|week\|month[&to=YYYYMMDD\|YYYYMMDDHHMM][&count=N][&warm=N]` | `{iv, interval, prevClose, bars, pre?, more}` — `to`(KST, 기본 지금) **앞쪽** 봉 `count`개(기본 250, 최대 1500, 오래된 순), `pre`는 위와 같고, `more`=더 오래된 봉이 있을 수 있음. 화면은 이걸로 스크롤하면 과거를 이어 받아요. 네이버가 분봉은 약 6거래일만 줘서 거기서 끝나요. **10m · 30m · 60m**(사용자 2026-11-14 08:10 "… 10분봉 30분봉 60분봉 선택 가능하게")은 Worker가 네이버 5분봉을 묶어요: 네이버 분봉 시각은 **봉의 시작**(09:05 봉 = 09:05:00~09:09:59 — 2026-11-15 1분봉 합으로 확인), 칸은 09:00 KST부터 시계 칸(60m: 09:00 … 15:00, 15:00 칸은 15:30까지), 시가 = 첫 봉, 고가 = 최대, 저가 = 최소, 종가 = 마지막, 거래량 = 합, 빈 칸은 없음. 장 마감 단일가(15:30 봉, 15:20~15:29에 체결이 있는 늦은 날은 16:30)는 마지막 정규 칸(60m · 30m 15:00, 10m 15:20)을 닫아 그 칸 종가 = KRX 종가, 시간외 봉(15:40~20:00)은 장 마감 시각부터 칸(60m 15:30 · 16:00 · 17:00 …). 네이버 자체 minute10/30/60과는 이 마감 칸만 달라요. `to`·`count`·`warm`·`more`는 묶은 봉으로 세고, `to`는 칸 시작이 `to` 앞인 봉(칸은 통째로). 옛 Worker가 400이면 화면이 `iv=5m`(또는 `tf=5d`)를 같은 규칙(`groupBars`)으로 묶어요. `tf=` 형식은 그대로 | 분봉·`to` 없음 20초, 그 외 10분 |
| `/api/stock/{code}/orderbook` | `{asks:[{price,qty}], bids:[{price,qty}], totalAsk, totalBid, prevClose, asOf}` — 5단계, 둘 다 **최우선 호가가 먼저** | 2초 |
| `/api/stock/{code}/investors` | `{rows:[{date, close, ratio, individual, foreign, institution, foreignHoldRatio}]}` 최신순, 최대 60일, 순매수 주식 수(부호 있음) | 10분 |
| `/api/stock/{code}/daily?page=N` | `{page, rows:[{date, close, change, ratio, open, high, low, volume}], hasMore}` 최신순 60행 | 60초 |
| `/api/stock/{code}/lending` | 대차잔고(금융위원회_주식대차정보, §3-32 ②): `{code, basDt, source:'금융위원회', asOf, days, rows:[{date, shares, amount, lent, repaid, recall?}], latest:{date, shares, amount, prevDate, change, ratio}\|null, stale?}` — `rows` **오래된 순** 약 60영업일(그 종목 행이 없는 날은 빠짐), `shares` 잔고 주수, `amount` 잔고 금액(원, 없으면 `null`), `lent` · `repaid` 그날 체결 · 상환 주수. 공용 표 하나에서 잘라요(종목마다 원천을 부르지 않아요). 표에도 없고 법인등록번호도 없는 코드 404 `{error:'정보 없음'}`, 법인은 있는데 빌린 적 없으면 200 `rows:[]` | 1시간 (stale 10분, 갱신 중 2분) |
| `/api/stock/{code}/corp` | 기업 기본(금융위원회_기업기본정보, §3-32 ⑤): `{code, name, basDt(최종 공개일), source, asOf, outline:{name, ceo, established, listed, employees, industry, business, settleMonth, address, homepage}\|null, affiliates:{basDt, count, items:[{name, listed}]}\|null, subsidiaries:{basDt, count, items:[{name, main}]}\|null, partial?, stale?}` — 없는 값 `null`, 목록은 가장 최근 기준일 묶음(상장 · 주요 먼저, 300개까지). 법인등록번호 없음(ETF · 외국 회사 · 모르는 코드) 404 `{error:'정보 없음'}` | 1시간 (stale 10분, 갱신 중 2분) |
| `/api/stock/{code}/dividend` | 배당 내역(금융위원회_주식배당정보, §3-32 ④ — 캘린더와 같은 API): `{code, basDt, source, asOf, rows:[{recordDate, payDate, amount, kind:'보통주'\|'우선주', reason, stockDate?, extraAmount?, cashRate?, stockRate?}], stale?}` — 이 주식(ISIN)만, **최신순**, 최근 6년 · 20건, 같은 배당을 다시 실은 행은 가장 최근 것. 404는 `corp`와 같음 | 1시간 (stale 10분, 갱신 중 2분) |
- 위 세 경로(`worker/src/stock_datago.js`, `docs/standards/datago.md` §5-2): 키 없음 · 아직 사본 없음 503 `{error, code}`(캐시 안 함), 실패하면 지난 사본 + `stale:true`. 기업 · 배당은 회사(보통주 코드)마다 **KST 하루 한 번까지**, 대차는 모든 종목이 함께 쓰는 하루 한 번. 우선주는 보통주의 사본을 같이 써요(배당은 우선주 행만).

- 주봉 `t`는 그 주의 월요일, 월봉은 1일이에요. `chart.prevClose`는 받은 첫 봉 바로 앞 봉의 종가예요(신규 상장이면 `null`) — 기간 등락률의 기준으로만 써요. 전일 종가(기준가) 선과 1일 %는 `summary.price − summary.change`로 그려요(오늘 봉 앞 봉은 NXT가 섞여 기준가와 다를 수 있어요).
- `summary.marketStatus`는 정규장 기준(`OPEN`은 KST 09:00~15:30에만). `orderbook.asOf`는 Worker가 받아 온 시각이에요(네이버가 시각을 안 줘요).
- Worker는 `env.ASSET_BASE`(기본 `https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/`)에서 `index.html`과 `universe.json`을 읽어요. 그래서 `web/`를 커밋·푸시하면 배포가 끝나요(엣지 캐시 최대 약 2분, GitHub raw 캐시 약 5분).
- 네이버 호가는 5단계만 있어요(10단계 원천 없음). 공매도 잔고는 KRX 로그인이 필요해서 지금은 제공하지 않아요.
- 정규장 이후(15:30~20:00) 오늘 봉과 현재가에는 NXT가 섞여요. 일별 시세(`daily`)의 오늘 행도 KRX+NXT 통합 가격이라 KRX 종가(15:30)와 다를 수 있어요. 화면에 표시해요.

**히트맵 → 종목 페이지 연결** (`src/template.html`이 제공)
- `window.KH`: `MODE('snapshot'|'live')`, `LIVE_URL`(= `https://panse.pages.dev/`), `MKT_NAME`, `stock(code)`, `stocks()`, `asOf()`, `colorOf(r)`, `palette()` → `{key,label,stops,up,down,flat,upText,dnText}`, `fmt.{pct,int,chg,eok,cls}`, `h(tag, props, ...kids)`.
- 이벤트(document): `kh:data`(시세 갱신 뒤), `kh:palette`(색상·범위 변경 뒤).
- 종목 페이지가 제공: `window.KHStock = { open(code, {opener}), close(), isOpen() }`. 주소 해시는 `#s-005930` 형식(아티팩트는 `#이름`만 허용).
- 스냅샷 모드에서는 헤더를 `KH.stock(code)`로 그리고, 차트·호가·투자자·일별 자리에 "실시간 버전에서 볼 수 있어요" + `LIVE_URL#s-코드` 링크를 둬요.

## 3-2. 2차 기능 계약 (2026-11-09 밤, 사용자 요청: 아래 전부 반영)

테마 히트맵 · 관심종목 · 기간별 수익률 · 외국인/기관 순매수 크기 · 상한가/하한가 표시 · 상단 시장 띠(지수·환율·미국 선물) · 이미지로 저장 · 홈 화면 앱(PWA) · 장중 리플레이 · 종목 페이지 뉴스·공시.

**매일 만드는 데이터** (`.github/workflows/daily.yml`, 평일 16:10 KST 이후 + 수동 실행. 결과를 커밋해요. 원천은 `data/ENDPOINTS_EXTRA.md`)
| 파일 | 모양 | 비고 |
|---|---|---|
| `data/snapshot.json` | 기존 + 행마다 `lim`(1 상한가, −1 하한가, 없으면 생략) | 15:30 종가로 고정 |
| `web/universe.json` | `{K, Q, X, I}` — `K`·`Q`는 실시간으로 받는 시장별 시총 상위 300종목(8자: 코드+`I` 인덱스 2자), `X`는 나머지 전 종목(9자: +시장 `K`/`Q`)으로 `/api/quotes?codes=`의 섹터 조회용 | `build_page.py`가 만듦 |
| `web/themes.json` | `{asOf, themes:[{id, name, cap, codes:[…]}]}` — 네이버 테마 265개 전체, `cap`은 구성 종목 시총 합(억원), 우선주 제외, `codes`는 시총 순 | 한 종목이 여러 테마에 들어가요(삼성전자 31개) |
| `web/periods.json` | `{asOf:'YYYY-MM-DD', base:{w1,m1,m3,ytd,y1:'YYYY-MM-DD'}, c:{코드:[w1,m1,m3,ytd,y1 기준 종가]}}` | 수익률은 화면이 `현재가/기준종가−1`로 계산 |
| `web/flows.json` | `{asOf:'YYYY-MM-DD', unit:'억원', f:{코드:[외국인1일, 기관1일, 개인1일, 외국인5일, 기관5일, 외국인20일, 기관20일]}}` | 금액 = 순매수 주식 수 × 그날 종가 |

**Worker 추가 경로**
| 경로 | 응답 | 캐시 |
|---|---|---|
| `/api/quotes` 행 | 기존 + `lim`(1/−1, 상·하한가일 때만). 원천: `compareToPreviousPrice.name` `UPPER_LIMIT`/`LOWER_LIMIT` | — |
| `/api/quotes?codes=c1,c2,…` | 같은 모양, 지정 종목만(최대 300개, 6자 코드). 섹터는 `universe.json`의 `K`·`Q`·`X`에서, 그래도 없으면 `'기타'` | 8초 |
| `/api/themes` | `{asOf, themes:[{id, name, ratio, up, flat, down}]}` 테마별 등락률(네이버 테마 목록 3쪽) | 30초 |
| `/api/market` | `{asOf, items:[{key, name, value, change, ratio, delayed?, spark?:[[t,v],…]}]}` key 순서: `KOSPI`,`KOSDAQ`,`USDKRW`,`SPX_F`,`NDX_F`,`WTI`,`GOLD`,`BTC`. 지수만 오늘 5분봉 `spark`(t는 유닉스 초). 미국 선물은 `delayed:10`(분) | 30초 |
| `/api/stock/{code}/news` | `{rows:[{title, press, datetime(ISO KST), url}]}` 최신 20개, 제목 HTML 엔티티 풀어서 | 5분 |
| `/api/stock/{code}/disclosures` | `{source:'dart'\|'naver', rows:[{title, kind?, datetime, date?, filer?, note?, url}]}` DART는 최근 6개월 최대 40개(`kind`: 정기·실적·주요·지분·기타), 네이버는 최신 20개. Worker 비밀값 `DART_KEY`가 있고 `web/dart_corp.json`에 corp_code가 있으면 OpenDART(최근 6개월, `datetime`은 `null`이고 접수일 `date`만, `note`는 DART 비고: 정=정정·연=연결·유/코=시장 소관, `url`=`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=…`), 아니면·실패하면 네이버(`url`=`https://m.stock.naver.com/domestic/stock/{code}/notice/{id}`) | 5분 |
| `/api/disclosures/today[?after=접수번호]` | `{date:'YYYY-MM-DD', asOf, rows:[{c, t, k, n?, r, s?, f?}], counts:{K, Q, total, byKind:{실적, 주요, 지분, 정기, 기타}, byKindMarket:{K:{…}, Q:{…}}}, since?, stale?, after?}` — 그날 OpenDART 공시 중 유니버스(`K`·`Q`·`X`) 종목 것만, 최신순(`r` 내림차순). `c` 종목 코드, `t` 제목(앞의 `[기재정정]` 같은 꼬리표는 `n`으로), `k` 정기·실적·주요·지분·기타, `n` 꼬리표·비고("기재정정", "철회", "정정본 있음"), `r` 접수번호 — 링크는 `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=` + `r`, `s` 판세가 처음 본 시각 `HH:MM`(KST), `f` 제출인(회사와 다를 때만). 오늘 공시가 아직 없으면(밤·주말·휴일) 최근 평일(4일 안)이고 `date`가 그날. `counts`는 그날 전체 행 수(코스피 `K`·코스닥 `Q`, 종류별 `byKind`, 시장×종류 `byKindMarket` — 다섯 종류 키가 언제나 0부터 있어요). **약한 `ETag`**(asOf만 빼고 내용이 같으면 같음) → `If-None-Match`가 맞으면 본문 없는 **304**, 머리 `x-as-of`에 지금 `asOf`. **`?after=`** 14자리 접수번호 → 같은 날이면 그보다 새 행만(+ `after` 그대로 돌려줌, `counts`는 그날 전체), 날짜가 바뀌었으면 그날 전부(`after` 없음), 형식이 틀리면 400. `since`·`stale`·예산은 §3-29. `DART_KEY`가 없으면 503 | 30초 (+ KV 스냅숏 60초/5분) |
| `/api/live` (WebSocket) · `/api/live/state` | 실시간 갱신 허브(§3-23b ②, `docs/standards/realtime.md`): Durable Object `MarketHub`(바인딩 `MARKET`, `[exports]` 선언) 하나가 장중·연결이 있을 때만 3초마다 상위 300×2를 받아 바뀐 칸만 보내요. 연결 거절은 `{t:'off', reason:'closed'|'full'|'budget'|'paused'|'error', retryAt}` 뒤 4003으로 닫아요 — 화면은 그 메시지를 끝으로 보고 폴링으로 돌아가요. `state`는 허브 상태·예산 계수(`guard`). 끄기 스위치: KV `REPLAY`의 `live:off`. 2026-11-14 03:49 처음 배포(되돌리기 불가 — 고칠 땐 앞으로 고쳐 올려요). 화면 쪽은 `src/live`(§3-7 실시간 갱신) | `state` 장중 60초 · 그 밖 10분 |
| `/api/replay/dates` | `{dates:['YYYY-MM-DD',…]}` 최신순 | 60초 |
| `/api/replay?date=YYYY-MM-DD` | `{date, codes:[…], frames:[{t:'HHMM', p:[…], r:[…]}], index:{KOSPI:[…],KOSDAQ:[…]}, base:{KOSPI,KOSDAQ}\|null}` — `p`·`r`·지수는 `codes`/`frames` 순서, `base`는 지수 전일 종가. 날짜 없으면 최신 | 60초(지난 날 1시간) |
| `/api/replay/status` | 기록기 상태(§3-15 ①): KV `replay:status` `{v, at(ms), day:'YYYY-MM-DD', t:'HHMM', result:'wrote'\|'skipped:<이유>'\|'error', error?, rows?, since(ms), lastWrote:'HHMM'\|null, errors(그날, 근사), lastError?:{t,error}, cron}` + `{now(ms), nowKst, atKst, ageSec, due, recent, stale}` — 아직 없으면 `result:null`. `due`=평일 09:06~마감, `recent`=최근 5분 프레임 키가 있는지(`{'HHMM':bool}`), `stale`=`due`인데 그 5분에 프레임이 하나도 없음. 이유: `after-end`·`closed`(휴장) | 없음(`no-store`) |
| `/api/news` | `{asOf, items:[{src:'einfomax'\|'hankyung'\|'mk', title, url, t(ISO KST)}], sources:{src:{ok, n, at, error?, stale?}}}` — 시장 뉴스(§3-27, `docs/standards/news.md` §2-2): 연합인포맥스 · 한국경제 · 매일경제 RSS, 언론사마다 최신 30개, `url`로 중복 제거, `t` 내림차순. 제목 · 링크 · 시각만(본문 · 요약 · 이미지 · 기자 없음). User-Agent `PanseNewsBot/1.0 (+https://panse.pages.dev)`, 언론사마다 6초 · 같은 요청 안 재시도 없음 · 403/429면 15분 쉼(KV `news:cool:<src>`), 마지막 성공본 KV `news:last:<src>` 6시간(실패하면 `stale:true`로 같이). 기사가 하나도 없으면 502 `{error, sources}`. **매일경제는 북미 동부 릴레이로**(§3-27, news.md §2-6): 그 목록이 릴레이로 왔으면 `sources.mk.via:'relay'`. 실패 기록 KV `news:err:<src>`(공개 안 함) | 180초 (`s-maxage=180, stale-while-revalidate=120`) |
| `/api/policy` | `{asOf, items:[{src:'kdi'\|'gwanbo', title, url, t:'YYYY-MM-DD', org?, kind?}], sources:{kdi\|gwanbo:{ok, n, at, error?, stale?, scanned?}}}` — 정책 자료(§3-27, `docs/standards/policy-feeds.md`): **KDI 경제정보센터 경제정책자료 RSS**(최신 30, `pubDate`가 비어 있어서 날짜 · 기관은 설명 첫 문장 "재정경제부는 ’26.11.13.(금) …"에서 — 설명 글은 내보내지 않아요) + **행정안전부 관보 목록**(공공데이터포털 `ApiTotalService/getApiTotalList`, Worker 비밀값 `DATA_GO_KR_KEY`, 하루 단위로 읽고 지난날은 한 번 읽으면 끝; 시장용 거르기 = 발행기관이 재정경제부 · 기획재정부 · 기획예산처 · 금융위원회 · 증권선물위원회 · 금융감독원 · 한국은행 · 산업통상 · 공정거래위원회 · 국세청 · 관세청이고 편집구분이 인사가 아닌 것, 최신 30, 링크는 전자관보 `gwanbo.go.kr`만). 제목 · 링크 · 날짜 · 기관(· 편집구분)만, `t` 내림차순, 같은 날 안에서 두 곳이 번갈아. 정직한 UA `PanseNewsBot/1.0`, 6초, 같은 요청 안 재시도 없음. KV 신선도 문(사본이 KDI 20분 · 관보 30분, 밤 · 주말 60 · 120분보다 젊으면 원천에 묻지 않음), 실패하면 쉼 `policy:cool:<src>`(5분, KDI 403/429 15분 · RSS 아님 30분, 관보 키 오류 30분 · 한도 60분) + 지난 목록 `policy:last:<src>`(`stale:true`), 실패 기록 `policy:err:<src>`(공개 안 함), 관보 하루 상한 1,500번(`budget`). 키 없으면 관보 `error:'no key'`. 아무것도 없으면 502 `{error, sources}` | 600초 (한 곳이 실패 중이면 120초, `stale-while-revalidate=600`) |
| `/api/funds` · `/api/funds/chart/{key}?tf=3m\|1y` | 증시 자금(§3-32, `docs/standards/datago.md` §5): `{asOf, basDt, source:'금융투자협회', items:[{key, name, value, change, ratio, unit:'억원'\|'%', basDt, prev, prevDt}], stale?, partial?}` — key 순서 `deposit`(투자자예탁금) · `credit`(신용융자 전체) · `creditKospi` · `creditKosdaq` · `unpaid`(위탁매매 미수금) · `forced`(반대매매, 그날 금액) · `forcedRatio`(미수금 대비 반대매매 비중). 값은 억원(비중은 %), `change` · `ratio`는 앞 영업일 대비(비중의 `change`는 %p). 금융위원회_금융투자협회종합통계정보를 하루 몇 번만 받아 KV `datago:funds`에 두고 내줘요 — 실패하면 그 사본 + `stale:true`, 사본도 없으면 503 `{error, code}`(캐시 안 함), 두 오퍼레이션 중 하나만 실패하면 `partial`. 차트는 `{key, name, tf, unit, bars:[{t:'YYYY-MM-DD', c}]}` 영업일 92 · 366일, 모르는 key · tf는 400. 이 경로가 없는 옛 Worker면 화면은 묶음을 빼요 | 1시간 (stale 10분) |
| `/api/datago/status[?warm=1]` | 공공데이터포털 상태(`docs/standards/datago.md` §7): API별 오늘 호출 수 · 상한 · 쉬는 중 · 마지막 실패 기록, 사본(`funds` · `crno`)의 basDt · 받은 시각 — 키 · URL · 법인등록번호 표는 없음. `warm=1`은 사본마다 `due()`만 먼저 돌려요(때가 아니면 부르지 않아요) | 없음(`no-store`) |
| `/api/calendar?from&to[&kinds=kr,us,cb,mkt,corp]` | 증시 캘린더(§3-33, `docs/standards/calendar.md` §9): `{asOf, from, to, tz:'Asia/Seoul', days:{날짜:{kind:'closed'\|'special', note, open?, close?, tentative?}}, events:[{id, d, t:'HH:MM'\|null(KST), k:'kr'\|'us'\|'cb'\|'mkt'\|'corp', rg?:'us'(미국 지표 · FOMC — 없으면 한국), star:1~3, src:'bok'\|'kostat'\|'fred'\|'manual'\|'rule'\|'dart'\|'fsc', title, sub?, c?, n?, r?, url?, orig?:{d,t,tz}, tentative?, weekly?, value?:{text, src, p}, pct?, grp?, codes?, cls?:'div'\|'rights'\|'lock'\|'agm'\|'etc'(기업 일정만), minor?:true(기본 숨김 세부 일정, 언제나 ★), exd?(DART 신주배정기준일의 권리락일)}], sources:{id:{name, ok, at, off?, err?}}, stale?, manual}` — 기간 최대 42일 · 오늘 ±400일, 틀리면 400. 원천: 한국은행 통계공표일정 페이지 · 국가데이터처 보도계획 · FRED(`FRED_KEY`) · 발표값 ECOS(`ECOS_KEY`) · FRED · OpenDART 무상 · 유상증자(`DART_KEY`, 하루 상한 400) · 직접 입력 표(금통위 · FOMC · 휴장, `calendar.js`) · 만기 규칙. KV `REPLAY` `cal:<원천>`(지난 값 유지), cron 없음(요청 때). 금융위 배당 · 보호예수 · 주식권리일정은 공용 도우미 `datago.js`로(`DATA_GO_KR_KEY`, 사본 `cal:fsc:<divi|lock|rights>`, `sources.fsc.parts`), 끄기 `CAL_FSC=off` | 300초 (`max-age=60, s-maxage=300, stale-while-revalidate=300`) |
| `/data/themes.json`, `/data/periods.json`, `/data/flows.json` | ASSET_BASE의 `web/*.json` 그대로 | 10분 |
| `/manifest.webmanifest`, `/sw.js`, `/icon.svg`, `/icon-192.png`, `/icon-512.png`, `/apple-touch-icon.png` | ASSET_BASE에서 올바른 content-type으로 | 1시간 |

- 리플레이 기록: Worker `scheduled()`가 평일 09:00~15:30 KST에 5분마다(`t`는 5분 단위, 15:30 프레임은 지수가 CLOSE여도 기록) 유니버스 600종목 시세를 KV 바인딩 `REPLAY`(namespace id `bfdaeef6e5204d0ba223a568f76d3c85`)에 프레임마다 한 키로 써요: `replay:YYYYMMDD:codes`, `replay:YYYYMMDD:HHMM` → `{p,r,i}`. TTL 40일. ~~cron `*/5`·무료 플랜 한도~~ → §3-15: 매분 cron, Workers Paid.
- `/api/market`의 `delayed:10`은 미국 선물뿐 아니라 WTI·금에도 붙어요(CME/NYMEX/COMEX). 매일 작업은 21:30 KST에 투자자 동향만 한 번 더 받아요(그날 행이 저녁에 올라와요).
- 무료 플랜 서브요청 한도(50) 때문에 종목 600개를 하나씩 부르는 일(기간 수익률, 투자자 동향)은 Worker가 아니라 매일 작업이 해요.

**히트맵 확장 API** (`src/template.html`이 `window.KH`에 추가)
- `KH.loadData(name)` → `Promise<JSON|null>` (`name`: `themes`·`periods`·`flows`). 스냅샷은 `<script id="kh-data-NAME">`에서, 실시간은 `data/NAME.json`에서 읽어요. 한 번 읽으면 기억해요.
- `KH.watch`: `{has(code), toggle(code), list()}` + 이벤트 `kh:watch`. localStorage 키 `khm.watch`.
- `KH.layout()` → 지금 그려진 노드 `[{kind:'sector'|'ind'|'tile', x,y,w,h, color, label, sub, code?, hd?}]` 지도 픽셀 좌표. 타일 `label`=전체 이름, `sub`=화면 그대로의 % 글자, `code`=종목 코드. 섹터·업종은 머리글이 숨으면 `label`·`sub`가 `''`, `hd`=머리글 높이. 표 보기에서는 `[]`.
- `KH.setReplay({t:'HHMM', date, prices:Map(code→{p,r})}|null)`: 색·라벨·머리글·사이드 패널·표·툴팁에 덮어 그림(크기는 `cap×p_frame/p_now`). Map에 없는 종목은 실시간 값 유지. 시세 갱신에도 유지되고 `null`이면 실시간 복귀. 렌더마다 이벤트 `kh:render` `{view, market, theme, replay}`.
- `KH.index()` → `{KOSPI:{value,change,ratio}, KOSDAQ:{…}}`, `KH.market()` → `'K'|'Q'|'ALL'|'theme'|'watch'`.
- 마운트 지점: 헤더 아래 `<div id="strip">`(시장 띠), 도구 줄 끝 `<div id="extras-tools">`(저장·리플레이 버튼).
- `src/extras/extras.js`·`extras.css`: 시장 띠, 이미지 저장, PWA 등록, 리플레이 UI. 빌드가 종목 페이지 다음에 끼워 넣어요.

## 4. 화면 규칙

- 다크 톤. 지도 바닥은 `#000`, 화면 `--page #131418`, 패널 `--panel #191a1f`, 선 `--line #2b2d34`.
- 인터페이스 강조색은 앰버 `#ffb547`(선택·포커스·활성 탭). 빨강·초록은 **데이터(등락)에만** 써요.
- 숫자 텍스트 색: 상승 `--up-text`, 하락 `--dn-text`(팔레트가 바꿔요). 다른 텍스트는 `--fg`, `--fg2`, `--muted`.
- 해요체, 짧게. 레이블에 ALL CAPS나 영문 장식 쓰지 않아요.
- 데이터 출처(네이버 증권)와 시점을 화면에 적어요. 정규장(15:30) 이후 시세에는 NXT·시간외 거래가 섞인다는 걸 표시해요.
- 투자 조언처럼 보이는 문구를 쓰지 않아요.

## 5. 품질 기준

- 360 / 390 / 768 / 1280 / 1920에서 가로 넘침 0, 콘솔 오류 0.
- 타일 라벨이 타일 밖으로 넘치지 않아요(`.tile .lab` 측정).
- 키보드로 모든 조작이 닿고 포커스가 보여요. 시트·종목 페이지는 Esc로 닫히고 포커스가 돌아가요.
- 모바일 탭 영역 40px 이상. 본문 대비 4.5:1 이상.
- `prefers-reduced-motion`이면 전환·깜박임을 꺼요.
- 네트워크 실패, 빈 데이터, 장 마감·휴장일 상태를 각각 문구로 보여 줘요.

## 6. 에이전트와 일하는 방식

- 파일 하나에 담당 하나. 편집 에이전트는 git worktree(`feat/<area>`)에서 작업하고 커밋만 해요. 병합·빌드·배포는 오케스트레이터가 해요.
- 완료 조건: 자기 영역 점검 통과, 콘솔 오류 0, 가로 넘침 0, 세 화면(1440·768·390) 스크린샷 직접 확인.
- 보고는 20줄 이하: 바꾼 것 / 테스트 결과(숫자) / 스스로 판단한 것 / 요청 사항 / 커밋 id.
- 모델: Opus는 설계·복잡한 로직·독립 리뷰, Sonnet은 수정 묶음·테스트·측정, Haiku는 단순 반복.
- 큰 작업이 끝나면 작업을 보지 않은 에이전트가 이 문서 기준으로 읽기 전용 리뷰를 해요(파일·줄 단위).

## 3-3. 3차 계약 (2026-11-09 23:40, 독립 리뷰 반영 + 사용자 요청: 재무·리서치)

**빌드가 만드는 파일** (`build_page.py`, 오케스트레이터)
| 파일 | 모양 | 용도 |
|---|---|---|
| `web/names.json` | `{asOf, n:{코드:[종목명, 'K'\|'Q']}}` 우선주 포함 전 종목 | 실시간 검색이 스트림 밖 종목(우선주 등)도 찾게. `KH.loadData('names')` |
| `web/close.json` | `{date:'YYYY-MM-DD', asOf, lim:true, c:{코드:[종가, 전일대비, 등락률, lim?]}}` KRX 15:30 종가(스냅샷이 고정한 값), 전 종목. 네 번째 `lim`은 상한가 1 · 하한가 −1일 때만(스냅샷의 `lim` 그대로, §3-34 ⑤) — `lim:true`가 "행이 표시를 싣는다"는 뜻이라 없는 행은 0, 키가 없는 옛 파일만 ±29.5% 어림 | 장 마감 뒤 실시간 지도를 "정규장 종가"로 볼 수 있게. 스냅샷이 15:30 고정이 아니면 만들지 않아요. `KH.loadData('close')` |
- 스냅샷(`dist/`)은 d3를 HTML 안에 넣어요(네트워크 없이 열려도 지도가 그려져야 해요). 실시간 버전은 cdnjs 그대로.
- Worker는 `/data/names.json`, `/data/close.json`도 `web/`에서 그대로 내줘요(10분 캐시, 없으면 404).

**정규장 종가 / NXT 포함** (히트맵)
- 실시간에서 `asOf`가 KST 15:30 이후이고 `close.json`의 `date`가 그 거래일이면, 도구 줄에 "정규장 종가 · NXT 포함" 선택을 보여 줘요. 기본은 **정규장 종가**. 고르면 `p`·`d`·`r`을 `close.json` 값으로 바꿔 그려요(`close.json`에 없는 종목은 실시간 값 + 표시 없음).
- 15:30 이후 NXT가 섞인 값을 그릴 때는 머리글에 "NXT 포함 · HH:MM 기준" 배지를 보여 주고, 휴대폰에서도 짧은 시각이 보이게 해요.

**종목 페이지 재무·리서치** (Worker 경로, 원천: 네이버)
| 경로 | 응답 | 캐시 |
|---|---|---|
| `/api/stock/{code}/finance?period=annual\|quarter` | `{period, cols:[{key:'202512', label:'2025.12', estimate:bool}], rows:[{title, unit:'억원'\|'%'\|'원'\|'배', values:[number\|null]}]}` — 원천 `m.stock.naver.com/api/stock/{code}/finance/{annual\|quarter}`. `cols`는 오래된 순, `estimate`=컨센서스(E). `values`는 `cols` 순서. 단위: 매출액·영업이익·당기순이익·지배주주순이익·비지배주주순이익=억원, 영업이익률·순이익률·ROE·부채비율·당좌비율·유보율=%, EPS·BPS·주당배당금=원, PER·PBR=배 | 6시간 |
| `/api/stock/{code}/research` | `{consensus:{targetMean, opinionMean, date}\|null, rows:[{date, broker, title, target, opinion, url}]}` — 목록 원천 `m.stock.naver.com/api/research/stock/{code}?pageSize=20`, 컨센서스는 `/integration`의 `consensusInfo`(`priceTargetMean` 원, `recommMean` 1~5 숫자). `target`(원)·`opinion`(Buy·매수·중립 등)은 미리보기 글에서 뽑은 값, 못 뽑으면 `null`. 미리보기 본문은 내보내지 않아요(증권사 저작물). `url`=`https://m.stock.naver.com/research/company/{researchId}` | 30분 |
- `/api/stock/{code}/summary`에 더해요(원천 `/integration`의 `totalInfos`·`industryCompareInfo`): `open, high, low, prevClose, volume(주), tradingValue(억원), cnsPer, cnsEps, dps(주당배당금 원), peers:[{code, name, market:'K'|'Q', price, ratio, cap(억원)}]`(같은 업종 최대 6개). 없는 값은 `null`.
- 화면(사용자가 보낸 토스증권 "종목정보" 참고, `/mnt/user-data/uploads/0f760a4a-image.webp`): 1일·52주 가격 범위 막대, 투자 지표 칸(시총·PER·추정PER·PBR·ROE·PSR·배당수익률·외국인소진율), 재무 막대(분기/연간, 매출·영업이익·순이익, 추정치는 빗금), 안정성(부채비율·당좌비율 선), 배당(주당배당금), 애널리스트(최근 3개월 리포트 의견 분포 + 평균 목표가와 현재가 대비 %) + 리포트 목록, 같은 업종 종목, 투자자 탭 맨 위 "오늘" 순매수 막대. PSR = 시총 ÷ 최근 4분기 매출 합(분기 4개가 없으면 최근 연간 매출).
- 리포트 PDF를 다시 올리거나 본문을 옮기지 않아요. 제목·증권사·날짜·목표가·의견 + 원문 링크만.
- 화면 문구: "출처: 네이버 증권 · 컨센서스는 증권사 추정치예요". 투자 조언처럼 보이는 표현은 쓰지 않아요.

**리플레이 기록 (KV 무료 한도 대응)**
- `list` 호출을 기록·조회 경로에서 쓰지 않아요. 중복 확인은 `get(fkey)`, 날짜 목록은 키 `replay:days`(최신순 날짜 배열, 40일 넘으면 잘라 냄)에 써요. 하루 프레임은 09:00~(장 마감 시각)까지 5분 단위 키를 직접 만들어 `get`해요.
- 장 마감 시각은 시세의 `stockExchangeType.endTime`(보통 `1530`, 수능·첫 거래일 `1630`)을 따라요. cron은 `* 0-7 * * 2-6`(월~금)(UTC, 매분, §3-15 — Cloudflare 요일은 1=일요일이라 숫자 `1-5`는 일~목이었어요), 마감 시각 프레임은 지수가 CLOSE여도 기록해요.
- CORS: `access-control-allow-origin`은 `https://panse.pages.dev`로 좁혀요(같은 출처 요청에는 영향 없음, Worker v14).

**등락 분포 = 전 종목** (사용자 요청 2026-11-09 23:43: "300종목만 말고 전 종목으로")
- Worker `/api/breadth?m=K|Q&part=N` → `{m, part, parts, asOf, rows:[[코드, 등락률, lim?]]}` — 시장 `m`의 전 종목(`universe.json`의 `K`/`Q` + `X` 중 그 시장, 우선주 포함)을 코드 순으로 600개씩 나눈 `part`번째 묶음 — **`part`는 1부터** (`1..parts`). `parts`는 묶음 수(코스피 2, 코스닥 3). 한 호출에 polling 1번(600개 이하) — 무료 플랜 CPU 한도 때문에 나눠요. 행은 작게(가격·이름 없이). 캐시: 정규장 중 30초, 그 밖 10분. `part`가 범위 밖이면 400.
- 히트맵 "등락 분포" 카드(오늘 기준)는 지도 종목이 아니라 **그 시장 전 종목** 분포를 보여 줘요: 정규장 중에는 `/api/breadth` 묶음들(카드가 화면에 보일 때만 60초마다, 숨은 탭에서는 멈춤), 장 마감 뒤 "정규장 종가"면 `close.json`(전 종목), 스냅샷은 내장 2,700종목. 머리글 범위 표시는 "코스피 전 종목 9xx" 식. 일부 묶음이 실패하면 받은 것만 쓰고 "일부만 반영" 표시, 전부 실패하면 지도 종목 분포로 돌아가고 그렇게 적어요.
- 막대를 누르면 지도의 해당 구간 종목을 강조하는 동작은 그대로(지도에 없는 종목은 강조 대상이 아니라고 안내). 기간 수익률·순매수 색 기준일 때는 데이터가 있는 종목 범위로 그리고 범위를 적어요. 테마·관심 보기와 섹터·업종 확대(focus) 중에는 기존처럼 그 범위만.

## 3-4. 해외 지수 · 원자재 탭 (사용자 요청 2026-11-09 23:46)

"코스피, 코스닥, 전체, 테마에 추가로 원자재와 해외 시장 지수 모음" → 시장 탭에 **해외**, **원자재** 두 개를 더해요. 순서: 코스피 · 코스닥 · 전체 · 테마 · 해외 · 원자재 · ★관심. **지금 순서**(§3-35, 사용자 2026-11-15 19:51 "탭 순서 관심과 일정 바꿔주고"): 코스피 · 코스닥 · 전체 · 테마 · 해외 · 지표 · 일정 · ★관심. 휴대폰에서는 탭 줄이 옆으로 넘어가요(잘리지 않게, 현재 탭이 보이게).
- **세 묶음 + ★관심 고정** (사용자 2026-11-15 21:38~21:40, 세 안 중 "A: 휴대폰에서 ★관심을 오른쪽 끝에 고정" + "그럼 A에서 저렇게 칸을 나누든 아님 묶여있는 느낌이 있어야할거같아" — 스크린샷에 전체|테마 · 일정|★관심 두 줄): `[코스피 · 코스닥 · 전체] | [테마 · 해외 · 지표 · 일정] | [★관심]`. 나눔선은 PC · 휴대폰 모두 가는 선(`--line`, 탭 높이의 약 60 % — PC 20px · 휴대폰 24px, 가운데, 양옆 `--space-2`), `aria-hidden`(버튼 순서 · 묶음 `role="group"`은 그대로). **탭 줄이 넘치는 휴대폰**에서는 ★관심(`.tpin`)이 줄 안에서 `position: sticky; right: 0`, 그 왼쪽 나눔선(`.tsep-pin`)도 함께 붙어요(`right: --pin-b`). 둘은 머리글 바탕(`--pin-bg` — 글라스는 패널 색조를 바탕 위에 겹친 값, 흐림 끄기 · 투명도 줄이기면 불투명 패널 색)이라 밑으로 지나가는 탭이 비치지 않고, 오른쪽에 아직 가려진 탭이 있을 때만 그 앞 16px가 옅어져요(`.more-r` 마스크). ★관심이 고정된 동안 고른 알약 · 밑줄은 그 탭 자신의 것(`data-pin`)이라 줄을 넘겨도 그 자리에 있고, 다른 탭과 오갈 땐 공용 표시가 지금 그려진 자리에서 출발 · 도착 뒤 넘겨줘요. 고른 탭은 ★관심 · 나눔선 · 옅어지는 곳 왼쪽에 보이게 넘겨요(`keepTabInView`). 지도 위치는 그대로(390 247 · 768 250 · 1280 이상 207). 점검 `qa/float/test_float.py`의 `tabgroups`.

**Worker** `/api/world?kind=index|commodity` (30초 캐시)
`{asOf, kind, groups:[{key, name, items:[{key, name, value, change, ratio, status:'OPEN'|'CLOSE', tradedAt, delayed?, unit?, tz?}]}]}`
- 원천: 지수 `polling.finance.naver.com/api/realtime/worldstock/index/{로이터코드,…}`, 원자재 `…/realtime/marketindex/{energy|metals|agricultural}/{코드,…}`. `delayed`는 `stockExchangeType.delayTime`(분, 0이면 생략), `tradedAt`은 `localTradedAt` 그대로(현지 시각 ISO).
- 지수 묶음(예): 미국(다우·S&P 500·나스닥 종합·필라델피아 반도체·러셀 2000 있으면), 미국 선물(S&P 500·나스닥 100·다우 선물), 유럽(유로스톡스 50·DAX·FTSE 100·CAC 40 …), 아시아(니케이 225·상해종합·선전·항셍·대만 가권·인도 SENSEX·베트남·호주 …), 한국(코스피·코스닥, 비교용), 참고(VIX — 오르면 불안이라는 뜻이라 색칠 대상 아님, `ref:true`). 원자재 묶음: 에너지(WTI·브렌트유·천연가스·RBOB 가솔린·난방유), 금속(금·은·구리·백금·팔라듐), 농산물(옥수수·대두·소맥·커피·설탕·코코아·면화). 실제로 응답이 오는 코드만 넣어요.
- `/api/world/chart/{key}?tf=3m|1y` → `{key, tf, bars:[{t:'YYYY-MM-DD', c}]}` 일봉 종가만(네이버에 해외 지수·원자재 분봉 원천이 없어 `1d`는 400). `key`는 로이터 코드에서 앞의 점을 뺀 값. 실제 묶음: 미국·미국 선물·유럽·아시아·태평양·중남미·한국·참고(VIX) 41개, 원자재 17개(`data/ENDPOINTS_DETAIL.md`).

**히트맵(`src/template.html`)이 제공하는 연결**
- 탭 `해외`(`state.market='WORLD'`, 해시 `#world`), `원자재`(`'CMDTY'`, 해시 `#cmdty`). `KH.market()` → `'world'|'cmdty'`.
- 이 탭에서는 지도·표·사이드 카드와 종목용 도구(크기·색 기준·종목 수·지도/표·NXT 선택)를 숨기고 `<div id="world">`(지도+사이드 자리 전체)를 보여 준 뒤 `window.KHWorld.show('index'|'commodity')`를 불러요. 다른 탭으로 가면 `KHWorld.hide()`. 색상 팔레트·범위 도구는 남겨요(같은 색 규칙). 검색·시장 띠·종목 페이지는 그대로.
- `KHWorld`가 없으면(모듈 로드 실패) `#world`에 안내 문구.

**목록이 기본** (사용자 2026-11-10 00:54: "해외나 원자재는 히트맵이 최선일까? 목록이 더 보기 편할 것 같아")
- 해외·원자재 탭은 **목록 보기가 기본**, 타일 지도는 `목록 · 지도` 전환으로 남겨요(선택은 localStorage `khm.worldView`, 두 탭 공통). 타일 크기에 의미가 없고(시총 없음), 항목이 적고(41·17개), 숫자를 정확히 읽는 게 중요해서예요.
- 목록: 묶음(미국·미국 선물·유럽·아시아·태평양·중남미·한국·참고 / 에너지·금속·농산물)별 섹션, 머리글에 묶음 평균 등락률과 장중/마감. 행 = 이름(+ 짧은 보조 글자: 거래소·단위) · 장중/마감 점과 지연 · 현재가 · 전일 대비 · 등락률(팔레트 색 칩) · 0 기준 등락 막대(같은 범위 도구 따라). 열 정렬은 숫자 오른쪽 맞춤, tabular-nums. 정렬 전환 `지역순 · 등락률순`(등락률순이면 묶음 없이 한 줄 목록, 묶음 이름은 행의 보조 글자로). 데스크톱은 묶음 섹션을 2~3단으로 배치해 화면 폭을 쓰고, 휴대폰은 한 단 44px 행. 행을 누르면 기존 상세(차트) 시트. VIX(`ref`)는 색 없이 회색 + "참고".
- 사이드 카드(많이 오른·내린, 지금 열린 시장, 출처·지연)는 두 보기에서 그대로.
- **해외 지수의 '지도'는 진짜 세계지도** (사용자 2026-11-10 00:55: "지도가 히트맵보다는 진짜 세계지도가 낫지 않을까?"): 나라를 대표 지수 등락률로 칠한 단계구분도(d3-geo, Natural Earth 계열 도법, 남극 제외). 대표 지수: 미국 S&P 500, 일본 니케이 225, 중국 상해종합, 홍콩 항셍, 대만 가권, 인도 SENSEX, 베트남 VN, 호주 ASX 200, 인도네시아 IDX, 말레이시아 KLCI, 한국 코스피, 독일 DAX, 영국 FTSE 100, 프랑스 CAC 40, 네덜란드 AEX, 스페인 IBEX 35, 이탈리아 FTSE MIB, 스웨덴 OMXS 30, 벨기에 BEL 20, 포르투갈 PSI 20, 아일랜드 ISEQ, 헝가리 BUX, 브라질 BOVESPA, 멕시코 IPC. 지수가 없는 나라는 어두운 회색. 나라마다 이름·등락률 라벨(작은 나라·홍콩·유럽 밀집 지역은 지시선이나 유럽 확대 상자), 장중인 시장은 표시(점·테두리). 나라를 누르면 그 나라 지수들(미국은 다우·나스닥·반도체 등 모두)이 상세 시트로. 미국 선물·유로스톡스 50·VIX처럼 나라에 안 붙는 항목은 지도 옆 작은 상자로.
- 지도 데이터: `world-atlas@2`의 `countries-110m.json`(TopoJSON, Natural Earth 공개 데이터) — 지도 보기를 처음 열 때만 jsDelivr에서 받아요(`fetch`의 `integrity`로 SRI 확인), 실패하면 목록으로 돌아가고 문구. 원자재 탭은 지리가 없으니 목록 + 타일 지도 그대로.


**모듈 `src/world/world.js`, `world.css`** (해외 담당, 빌드가 extras 다음에 끼워 넣어요)
- `window.KHWorld = {show(kind), hide()}`. `#world` 안에 묶음별 타일 지도(같은 크기 또는 대표 지수를 크게), 타일 색은 `KH.colorOf(ratio)`, 글자는 이름·값·등락률·장중/마감·지연 배지. 옆(데스크톱)/아래(휴대폰)에 순위 목록(많이 오른·내린, 지금 열린 시장). 타일을 누르면 상세(차트 경로가 있으면 차트, 없으면 값·시각·단위).
- 보일 때만 30초마다 갱신, 숨은 탭에서는 멈춤. 실패·빈 데이터 문구. 스냅샷 모드는 "실시간 버전에서 볼 수 있어요" + `LIVE_URL#world`/`#cmdty` 링크.
- 출처 문구: "네이버 증권 · 해외 지수와 원자재는 거래소별로 최대 20분 지연될 수 있어요" 식으로 지연을 밝혀요.
- 이미지 저장(extras)은 이 탭에서 "지도 탭에서만 저장할 수 있어요" 안내(또는 `KHWorld.layout()`이 있으면 그걸로 저장).

## 3-5. 모션·효과 (사용자 선택 2026-11-10 01:10)

사용자가 고른 것: **시세 플래시 + 숫자 롤링**, **첫 진입 연출 + 타임랩스 리플레이**, **세계지도 낮/밤 경계**, **3D 지도 보기(WebGL, 켜고 끌 수 있게, 기본은 꺼짐)**. 원칙: 정보를 전하는 모션만, 장식용 스크롤 연출·패럴랙스는 넣지 않아요.

**효과 설정 (히트맵이 제공) — 사용자 2026-11-10 01:09: "현재 효과를 기본으로 하고 화려한 효과를 따로 켤 수 있게"**
- `표시 설정`에 `효과: 기본 · 화려하게`. **기본 = 지금 있는 모션 그대로**(확대 FLIP, 시장 띠 티커 등). 아래의 새 효과(플래시·롤링·첫 진입 연출·타임랩스 트윈·빛 맥동·3D 관성)는 **`화려하게`일 때만** 켜져요. 기기가 `prefers-reduced-motion: reduce`면 `줄이기`(지금처럼 전환까지 끔)로 시작하고, 설정에서 다시 바꿀 수 있어요. localStorage `khm.motion`.
- `KH.motion()` → `'reduced'|'standard'|'fancy'`(기본 **`'fancy'`** — 사용자 2026-11-15 17:07 "10번은 화려하게가 기본", 처음 결정 2026-11-10의 standard를 바꿈), 바뀌면 document 이벤트 `kh:motion` `{motion}`. 모든 모듈: `fancy`가 아니면 새 효과를 쓰지 않고 바로 최종 상태를 그려요. `reduced`면 기존 전환도 꺼요.
- 정보 자체인 것은 효과 설정과 상관없이 보여요: 세계지도 낮/밤 경계(정적 음영), 3D 보기(따로 켜는 보기, 기본 꺼짐 — 단 `fancy`가 아니면 카메라 관성·높이 트윈 없이).
- 디자인 참고: 사용자가 보낸 레퍼런스(쇼룸 페이지 `/mnt/user-data/uploads/4567632c-koh-young-showroom.html`, 모션 사이트 링크들)를 정리한 브리프가 `docs/motion-brief.md`에 생기면 그걸 따라요.
- 성능: 애니메이션은 `transform`·`opacity`·`filter` 위주, 동시에 도는 플래시는 최대 60개 정도로 제한, 숨은 탭에서는 아무것도 안 돌아요.

**히트맵(`src/template.html`)**
- 시세 플래시: 실시간 갱신에서 `p`가 바뀐 타일만 테두리/안쪽 빛이 오르면 `--up-text` 계열, 내리면 `--dn-text` 계열로 약 0.7초 반짝여요(색 자체는 그대로). 표 보기는 해당 행의 값 칸이 반짝여요. 리플레이 중과 첫 그림에는 플래시 없음.
- 첫 진입 연출: 세션당 한 번(sessionStorage), 섹터 순서로 타일이 짧게 펼쳐지듯 나타나요(전체 0.7초 이내). 머리글 지수는 카운트업.
- 리플레이 트윈: `KH.setReplay(frame, {tween: ms})` — 이전 상태에서 새 프레임으로 색(Lab 보간)·라벨 숫자·크기(FLIP)를 `ms` 동안 이어 그려요. `tween` 없으면 지금처럼 즉시.
- 3D 보기 연결: 지도/표 전환을 `지도 · 3D · 표`로. 3D를 고르면 `#map`은 계속 배치만 하고(보이지 않게) 같은 자리의 `<div id="map3d">`를 보이게 한 뒤 `window.KH3D.show()`, 나가면 `KH3D.hide()`. 3D 선택은 저장하지 않아요(매번 2D로 시작). `KH3D`가 없거나 WebGL이 안 되면 안내 문구 후 지도로 돌아가요. 3D 중에도 `kh:render`·`kh:data`·`kh:palette`는 그대로 발생.

**extras (`src/extras/`)**: 리플레이 재생을 타임랩스로 — 재생 중 프레임 사이를 `KH.setReplay(..., {tween})`로 이어서 끊김 없이, 지도 위에 큰 시각 표시(쇼룸 페이지 같은 굵은 큰 글씨, 반투명, 지도 정보를 가리지 않게 모서리). 시장 띠 값이 바뀔 때 숫자 롤링(자리별로 굴러가는 오도미터).
**종목 페이지 (`src/stock/`)**: 머리 현재가·등락이 바뀔 때 숫자 롤링, 호가 칸 값이 바뀌면 짧게 반짝.
**해외 (`src/world/`)**: 세계지도에 실시간 낮/밤 경계(태양 직하점의 반대편 반구를 어둡게, 1분마다 갱신, 경계는 부드러운 그라데이션), 지금 장이 열린 나라·마커에 은은한 빛(맥동은 `fancy`일 때만).

**3D 지도 모듈 `src/map3d/map3d.js`, `map3d.css`** (3D 담당, 빌드가 world 다음에 끼워 넣어요)
- `window.KH3D = {show(), hide(), isOn()}`. `#map3d` 안에 canvas. 데이터는 `KH.layout()`(타일 x·y·w·h·color·code·label·sub, 섹터·업종 머리글)과 `KH.stock(code)`.
- 타일을 상자로 세우고 높이 = |등락률|(색 범위 도구 기준으로 정규화), 오른 종목은 위로·내린 종목은 바닥 아래로(또는 같은 방향으로 세우고 색으로만 구분 — 판단해서 읽기 쉬운 쪽). 섹터 사이 틈, 섹터 이름 라벨. 마우스 끌기·한 손가락으로 회전, 휠·두 손가락으로 확대, 처음엔 약간 기울어진 시점. 마우스 올리면 툴팁(이름·등락률·현재가), 누르면 `KHStock.open(code)`.
- three.js는 3D를 처음 켤 때만 jsDelivr에서 SRI로 불러요(UMD `build/three.min.js`가 있는 버전). `InstancedMesh` 등으로 600개도 휴대폰에서 부드럽게. 갱신 때 높이·색 트윈(`fancy`일 때). 탭이 숨으면 렌더 루프 멈춤, `hide()`면 GPU 자원 정리.

## 3-6. 시계 · 장 진행률 (사용자 요청 2026-11-10 01:12)

"시계도 위에 보여주면 좋으려나. 장 시작부터 장 마감까지 현재 몇 퍼센트인지 로딩바처럼 시계 바로 아래에, 이것도 온오프 가능하게"
- **히트맵**: 머리글(로고 오른쪽 상태 영역 근처)에 마운트 `<div id="clock"></div>`. 그리고 모듈이 `표시 설정`에 스위치를 넣을 수 있게 `KH.addSetting({key, label, hint?, default:boolean, onChange(value)})` → 설정 시트에 켬/끔 스위치를 그리고 localStorage `khm.set.<key>`에 저장, 처음과 바뀔 때 `onChange(value)` 호출. `KH.getSetting(key)`도 제공. (효과 설정처럼 템플릿 자체 설정은 그대로.)
- **extras**: `#clock`에 KST 시계(HH:MM:SS, tabular-nums, 초는 작게)와 바로 아래 얇은 진행 막대: 정규장 09:00→마감까지 경과 %(막대 + "정규장 64%" 글자). 단계 표시: 장 시작 전(08:30 동시호가부터 "장 시작 전 · 18분 남음"), 정규장(15:20 이후 "마감 동시호가"), 장 마감 뒤("장 마감 · NXT 애프터마켓 20:00까지" 또는 "장 마감"), 주말·휴장("휴장"). 휴장일 판단: 평일 정규장 시간인데 시세의 `marketStatus`가 둘 다 CLOSE이고 오늘 거래 기록(asOf 날짜)이 없으면 휴장. 마감 시각은 `/api/market`의 `session`(아래)이 있으면 그것, 없으면 15:30. `KH.addSetting({key:'clock', label:'시계·장 진행률', default:true})`로 켜고 끔. 휴대폰에서는 시계를 짧게(HH:MM) 쓰고 막대는 머리글 아래 전체 폭의 2px 선으로 바꿔도 돼요(공간 판단). `fancy` 효과일 때만 초 단위로 막대가 부드럽게 흐르고, 아니면 1분마다 갱신. 숨은 탭에서는 멈춰요.
- **Worker**: `/api/market` 응답에 `session:{start:'HHMM', end:'HHMM'}`(국내 정규장, 시세의 `stockExchangeType.startTime/endTime`에서; 없으면 생략)를 더해요.

**시계 모양 · 진행 막대 색** (사용자 2026-11-10 01:15: "시계는 공항 플랩과 스위스 및 일본 기차 플랫폼 아날로그 시계처럼. 로딩바는 오전·오후·장 마감 등 시간별 색깔 다르게")
- 시계 모양: `KH.addSetting`으로 `시계 모양: 플랩 · 아날로그 · 둘 다`(기본 플랩, `khm.set.clockStyle`; 사용자 2026-11-10 01:19 "시계 두 가지 동시도 가능하게"). `둘 다`면 작은 아날로그 판 + 플랩 숫자를 나란히(아날로그가 왼쪽), 휴대폰에서는 공간이 모자라면 아날로그를 작게 줄여요.
  - **플랩**: 공항 출발 안내판 같은 분할 플랩 숫자(HH:MM, 초는 작은 보조 숫자 또는 생략). 칸마다 위아래 반쪽 판, 가운데 가는 틈, 바뀔 때 위 판이 넘어가는 3D 회전(`standard`는 0.25초 한 번, `fancy`는 실제처럼 중간 숫자를 몇 장 거쳐 넘어감 + 미세한 그림자, `reduced`는 즉시). 판 색은 어두운 회색, 숫자는 밝은 미색, 글꼴은 Pretendard 굵게(tabular).
  - **아날로그**: 기차역 플랫폼 시계 느낌의 **독자 디자인** — 흰 판, 굵은 막대 눈금, 검은 직사각형 시·분침. 실제 브랜드 시계(스위스 철도 시계 등)의 고유 디자인을 그대로 베끼지 않아요: 초침은 앰버(#ffb547) 가는 바늘 + 작은 반대쪽 균형추로, 끝에 원판을 달지 않아요. 움직임: `fancy`면 초침이 부드럽게 쓸고 지나가 12시에서 잠깐 멈췄다가 분침이 한 칸 '툭' 넘어가는 역 시계식, `standard`면 초마다 똑딱, `reduced`면 분 단위만. SVG로 그리고 크기는 머리글 높이에 맞게(데스크톱 약 40px, 휴대폰은 숨기고 플랩 HH:MM만 써도 돼요).
- **진행 막대 색 = 시간대**(등락용 빨강·초록은 쓰지 않아요): 장 시작 전 08:00~09:00 새벽 남보라, 오전장 09:00~12:00 맑은 하늘색, 오후장 12:00~15:20 따뜻한 앰버, 마감 동시호가 15:20~15:30 짙은 주황, 장 마감 뒤 NXT 애프터마켓 15:30~20:00 보라, 밤·휴장 남색. 막대는 정규장 전체 폭 위에 구간 경계를 옅게 표시하고, 채워진 부분은 지금 구간 색(지난 구간은 각자 색으로 이어지는 그라데이션도 좋아요). 마우스 올리면 구간 이름과 시각.

**시계 개선 (사용자 2026-11-13 20:19, 구현 feat/clock)** — 위 '플랩·앰버 초침' 설명은 옛 기록이에요. 지금 모양: 판 없는 tabular 숫자(2026-11-10 `8fd68c4`) + 아날로그(미색 판·검은 바늘·**빨간 초침 `#e5231b`, 끝은 속이 빈 고리** — 원판 아님). 모든 테마에서 같은 색(§3-26).
- 판 바깥 테두리에 **정규장 호**(9시 자리 → 마감 자리, 1630일은 4:30), 진행 막대와 같은 시간대 색, 지난 부분 진하게·남은 부분 옅게, 주말·휴장은 옅은 회색.
- **카운트다운**: 08:50~09:00, 15:20~마감에 남은 시간 "−07:38"(데스크톱은 분 숫자 아래, 휴대폰은 HH:MM 오른쪽). 숫자는 굴리지 않고 글자만 바꿔요. aria-label은 1분마다.
- **길게 누르기(500ms) · 오른쪽 클릭 · 메뉴 키 · Shift+F10 → 세계 시각**(뉴욕·런던·도쿄·홍콩·상해 현지 시각 + 장중/마감, `/api/world` 30초 캐시, "네이버 증권 기준"). 짧게 누르면 새로고침 그대로.
- **마감 동시호가(15:20~마감)**: 시계 둘레 얇은 앰버 테두리, 시작할 때 1.2초 한 번 빛남(기본·화려하게), 줄이기는 테두리만. 소리 없음.

**시계가 제목 자리로** (사용자 2026-11-10 01:18: "시계를 켜면 제목이 사라지고 시계가 제목이 되어서, 시계를 누르면 새로고침")
- `#clock` 마운트는 머리글 **제목 자리**(로고 옆 "한국 증시 히트맵" 위치)에 있어요. 시계가 켜져 있으면 `<html class="has-clock">` — 템플릿은 이 클래스일 때 제목 글자를 화면에서 숨기고(스크린 리더용으로는 남김) 시계가 그 자리를 차지해요. 꺼지면 제목이 돌아와요. 진행 막대는 시계 바로 아래.
- 시계는 버튼이에요(`aria-label`: "한국 증시 히트맵 · 지금 13:05 · 눌러서 새로고침"). 누르면 `KH.refresh()` — 템플릿이 시세를 즉시 다시 받고 document 이벤트 `kh:refresh`를 내보내요. extras(시장 띠·시계)·world·등락 분포 등은 이 이벤트에 맞춰 바로 다시 받아요. 페이지 전체를 다시 불러오지는 않아요(상태·스크롤 유지). 누르는 순간 짧은 피드백(플랩이 한 번 섞이듯 넘어감 / 아날로그는 바늘 미세 흔들림, `reduced`면 없음)과 갱신 중 표시.

## 3-7. 실제로 들어간 확장 API (2026-11-10 새벽, 구현 기준)

- `KH.motion()` → `'reduced'|'standard'|'fancy'`, `<html data-motion>`, 이벤트 `kh:motion`. 설정 UI: `화면`(1280px 이상은 색상 옆 팝오버, 그 아래는 `표시 설정` 시트) → `효과: 기본 · 화려하게`(기기가 동작 줄이기면 `줄이기`도 보임). 기기 설정보다 사용자 선택이 우선이라 모듈은 `prefers-reduced-motion` 대신 `html[data-motion]`/`KH.motion()`을 봐요.
- `KH.addSetting({key,label,hint?,default, options?:[{v,label}], onChange})`, `KH.getSetting(key)`, 이벤트 `kh:setting`. 값은 `khm.set.<key>`.
- `KH.refresh()` → `Promise<boolean>`(진행 중 요청을 기다렸다가 새로 받음) + 이벤트 `kh:refresh`(스냅샷에서는 내보내지 않아요).
- `KH.marketStatus()` → `{KOSPI,KOSDAQ}`, `KH.view()` → `'map'|'3d'|'table'`, `KH.range()` → 지금 색 범위(숫자, 자동이면 그 단계 — §3-27 `KH.rangeInfo()`·`KH.feedRange()`).
- `kh:data`의 `detail.changed`(바뀐 종목 코드), `KH.layout()` 타일의 `dim`.
- `KH.setReplay(frame, {tween:ms, easing?:'out'})` — `fancy`에서만 보간, 아니면 즉시.
- `KH3D.show()`, `KH3D.hide()` → `Promise`(fancy면 접히는 0.36초 뒤 끝남), `KH3D.isOn()`, `KH3D.stats()`. `#map3d`는 템플릿이 `#map` 위에 놓고(`#map`은 visibility:hidden으로 계속 배치), 실패 시 `kh:3d-unavailable {reason,message}`.
- `/api/market`의 `session:{start,end}`.
- **실시간 갱신** (§3-23b ②, `docs/standards/realtime.md` §7-5, 구현 `feat/realtime-page`): `KH.feed(body)` → `true`|`false` — `/api/quotes` 모양 본문을 폴링과 **같은 길**로(저장소 · 지도 · 사이드 카드 · 머리글 · 범례 · 열린 시트 · 반짝임 · `kh:data {changed}`; 스냅샷 · `전체` · 빈 본문은 `false`, 허브가 흐르는 동안 그보다 옛 폴링 응답은 버림). `KH.pausePoll(on)` — 허브가 흐르는 동안 10초 타이머를 멈추고(진행 중 응답은 버림), 끄면 마지막 값에서 한 간격 안에 다시(`KH.refresh()`는 멈춰 있어도 한 번 받아요). `KH.scope()` → `'top'`|`'all'`, `KH.polling()` → `{paused, ok, last, wait}`. 마운트 `<span id="live-mark" hidden>`(`#status` 안) — 보이면 `#status.has-lm`(상태 점 · "실시간" 배지가 비켜요). 모듈 `src/live/live.js · live.css`(빌드: 공시 다음, 스냅샷에선 아무것도 안 함): `window.KHLive.state()` · `row(code)`(디버그), 설정 `khm.set.live`(기본 켬), 거절 기억 `khm.live.off` `{reason, retryAt, until}`. 점검 `qa/live/test_live_page.py`; 다른 QA 흉내 서버는 `qa/live/ws_mock.py`로 `/api/live`에 `off: closed`를 답해요.
- **`KH.spring`** — 공용 스프링 엔진 (design.md §6-3 "JS", 구현 `src/ui/spring.js`, 빌드가 모듈 맨 앞 — 종목 페이지보다 먼저 — 에 끼워 넣어요, `feat/ui-spring`). 끌기 · 중간에 다시 누름 · 놓을 때 속도처럼 CSS 전환이 못 하는 움직임은 모두 이걸로 — 모듈마다 따로 만들지 않아요. (처음엔 쓰는 모듈 없이 화면 변화 0으로 들어왔고, 쓰는 곳은 아래.)
  - `KH.spring.animate({from, to, name | k, c, velocity?, onUpdate(v, vel), onRest?(v), fancy?, scale?, restDelta?})` → 핸들 `{retarget(to, {velocity?, name? | k?, c?}), stop(), set(v), value(), velocity(), target(), running(), spring()}`. 질량 1 닫힌 해(덜 · 임계 · 과감쇠). 이름은 `:root`의 `--sp-<이름>-kc`(`"k c"`)에서 읽고, 없으면 `scripts/design_tokens.mjs` 표와 같은 내장 표(`kh:theme`이면 다시 읽어요). 속도는 **초당**(px/s). `retarget`은 지금 위치 · 속도를 그대로 이어받아요(CSS 전환과 다른 점). 공용 rAF 하나(움직이는 게 없으면 꺼짐), 한 프레임 dt ≤ 0.1초, 섬 = |x − to| < 1e-3·거리 · |v| < 1e-3·거리·ω0 → `onUpdate(to, 0)` · `onRest(to)` 한 번. `KH.motion()`이 `reduced`이거나 숨은 탭이면 끝값 바로(`onUpdate`는 그 자리에서, `onRest`는 마이크로태스크 뒤), `fancy: true`는 화려하게에서만 움직여요 — `kh:motion` · `visibilitychange` 때 움직이던 것도 끝값으로. `stop()`은 그 자리에 멈춤(`onRest` 없음), `set(v)`는 바로 그 값(끌기 · 키보드 연달아).
  - `KH.spring.edges(el, {left, width}, {lead:'lead', trail:'trail', write:'transform'|'left', onRest})` — 세그먼트 · 탭 · 밑줄 표시: 가는 쪽 가장자리 `lead`, 뒤 가장자리 `trail`(방향은 알아서 — 오른쪽으로 가면 오른쪽이 앞). 요소마다 컨트롤러 하나, 첫 호출은 그 자리에 놓고 다음 호출부터 움직여요. `.to(box)` · `.set(box)`(바로, design.md §8 키보드 연달아) · `.value()` · `.moving()` · `.stop()` · `.destroy()`. 프레임마다 `transform: translateX()` + `width`를 한 번 쓰고 레이아웃은 읽지 않아요(위치 숫자는 부르는 쪽이 이미 가진 값으로).
  - `KH.spring.knob(el, x, {width, stretch:3, front:'follow', back:'settle'})` — 스위치 손잡이: 앞 가장자리 `follow`, 뒤 `settle`, 늘어남은 `stretch`px 안(부드럽게 눌러 ≈ 3px). 핸들처럼 생겨서(`value · velocity · target · retarget · set`) `release`가 받아요.
  - `KH.spring.release(handle, pxPerMs, {points?, to?, name:'settle', maxOvershoot?})` → `{to, thrown, velocity, carried}` — 끌기를 놓을 때: `settle` 스프링이 놓은 속도(px/ms → px/s)를 이어받고, |v| > 0.11px/ms(`KH.spring.THROW`, §8)면 던짐 → `points` 중 그 방향 다음 점, 아니면 가장 가까운 점. `maxOvershoot`(px)는 끝이 막힌 트랙(스위치)에서 그만큼만 넘치도록 이어받는 속도를 줄여요.
  - `will-change: transform`은 `edges` · `knob`이 움직이는 동안만, 글자 없는 요소에만 붙였다 떼요(design.md §6-5, 원래 인라인 값으로 되돌림). `animate`는 DOM을 건드리지 않아요. 그 밖 `params(name)` → `{k, c, zeta, w0, source:'css'|'fallback'}` · `solve(k, c, from, to, v0)` → `{x(t), v(t), at(t), regime, zeta, w0}` · `names()` · `stats()` → `{active, scheduled}` · `FALLBACK` · `THROW` · `DT_MAX` · `REST`. 한 모듈의 콜백이 던져도 루프는 계속(오류는 `reportError`).
  - **쓰는 곳**(2026-11-15 `ux/float-motion`, §3-35): 템플릿 `KH.ui.sheetDrag`(시트 놓을 때 `settle`) · 지도 툴팁(`follow`로 따라감) — 일정 상세 시트(`src/calendar`)는 자기 끌기 코드로 같은 `settle`. 요약 카드 판도 `open` · `close`.
  - 점검 `node qa/ui/test_spring.mjs`(단위: 닫힌 해 vs RK4 · 넘침 공식 · 속도 이어받기 · 줄이기 · 서는 때 · 가짜 rAF 루프 · helper, 그리고 빌드된 `dist/` · `web/`에서 표시 데모 프레임 · 콘솔 오류 0 — 포트 8940), 화면이 그대로인지 `python3 qa/ui/compare_main.py`(다른 리비전 빌드와 390 × 844 · 1440 × 900 픽셀 비교, 포트 8941 · 8942).

## 3-8. NXT 가격 반영 (사용자 2026-11-10 08:07: "NXT 가격은 적용 안돼?")

실측(11/10 08:08): 09:00 전에는 네이버 `closePrice`가 전일 KRX 종가(0.00%)로 돌아가 있고, **NXT 프리마켓 가격은 `overMarketPriceInfo`에만** 있어요(`tradingSessionType:'PRE_MARKET'`, `overMarketStatus:'OPEN'`, `overPrice`, `compareToPreviousClosePrice`, `fluctuationsRatio`, `compareToPreviousPrice`, `localTradedAt`). 코스피 상위 300 중 248종목이 NXT에서 거래돼요. 정규장 뒤에는 `AFTER_MARKET`(15:30~20:00)이 같은 자리에 와요. 그래서 지금 지도는 장 시작 전에 전부 0%(회색)예요.

**Worker**
- `/api/quotes` 행과 `/api/breadth` 행에 NXT 값: quotes 행 `nx:{p, d, r, s:'pre'|'after', o:1|0, t}`(`o`=그 세션 진행 중, `t`=localTradedAt, 부호는 `compareToPreviousPrice`로), breadth 행은 `[코드, 등락률, lim?, nxr?]`(네 번째가 NXT 등락률, 없으면 생략 — lim이 없으면 세 번째 자리에 `0`). `overPrice`가 없거나 `tradeStopType`이 거래정지면 생략. 응답 머리에 `nxt:{session:'pre'|'after'|null, open:boolean}`(행들에서 판단).
- `/api/stock/{code}/summary`에 `nxt:{p, d, r, s, o, t}|null`.
- 무료 플랜 CPU: 같은 polling 응답에서 읽기만 하니 추가 호출 없음.

**히트맵 — 가격 기준 선택을 하나로**
- 머리글의 기존 `정규장 종가 · NXT 포함` 자리를 **가격 기준** 선택으로 일반화: `KRX · NXT`.
  - NXT 세션이 **열려 있을 때**(프리마켓 08:00~08:50, 애프터마켓 15:30~20:00): 기본 **NXT**. NXT 가격이 있는 종목은 `nx.p/d/r`로 칠하고, NXT에서 거래되지 않는 종목은 KRX 값 그대로 + 옅게(빗금 또는 낮은 채도) 표시하고 툴팁에 "NXT 거래 없음".
  - 프리마켓 중 `KRX`를 고르면 KRX는 아직 거래 전이니 **어제 KRX 종가 기준 등락**(close.json)으로 보여 주고 "어제 종가" 표시.
  - NXT 세션이 **닫혀 있을 때**: 지금처럼 기본 **KRX 정규장 종가**, `NXT`를 고르면 마지막 NXT 가격(애프터마켓 종가).
  - 정규장(09:00~15:30) 중에는 선택을 숨기고 KRX 실시간(지금 그대로).
  - 사용자가 고른 값은 세션(프리/정규/애프터/야간)이 바뀔 때까지만 유지하고, 세션이 바뀌면 그 세션의 기본으로.
- 머리글 배지: "NXT 프리마켓 · 08:12 기준" / "NXT 애프터마켓 · 17:40 기준" / "KRX 15:30 종가". 휴대폰은 짧게("NXT 08:12").
- 크기(시총)는 KRX 시총을 가격 비율로 보정(`cap×p_nxt/p_krx`), 사이드 패널·표·툴팁·검색 결과·관심 보기·테마 보기 모두 같은 값. 등락 분포도 같은 기준(NXT면 `nxr`가 있는 종목만, 범위에 "NXT 248종목" 식으로).
- 리플레이는 KRX 그대로.

**종목 페이지**: 머리 현재가 아래에 NXT 줄 — 세션 중이면 "NXT 프리마켓 201,500 +6.11% · 08:12"(오름/내림 색), 끝났으면 "NXT 애프터 종가 …". NXT 미거래 종목은 줄 없음.

## 3-9. 정리 (사용자 2026-11-10 08:49: "지도는 세계지도만 놔두고 3D 히트맵은 필요없어")
- **3D 보기 제거**: 보기 전환은 다시 `지도 · 표`. `src/map3d`는 빌드에서 빠졌어요(코드는 저장소에 남아 있지만 페이지에 들어가지 않아요). 템플릿의 3D 연결 코드는 쓰이지 않는 상태로 남아 있어요(다음 템플릿 작업 때 정리).
- **원자재는 목록만**: 지리가 없는 원자재 탭은 `목록 · 지도` 전환 없이 목록만 보여요. 해외 지수는 `목록 · 지도(세계지도)` 그대로.

## 3-10. 통합 시세 (사용자 2026-11-10 08:34: "KRX 및 NXT 합산 시세는 불가능한가" → 08:51 "이어서 해줘")
- 가격 기준은 **`KRX · NXT · 통합`** 세 가지. 통합 = 두 시장 중 **더 최근 체결가**(KRX `localTradedAt` vs `nx.t`), 전일 대비·등락률은 KRX 기준가(전일 종가) 대비로 다시 계산, 거래량·거래대금 = KRX + NXT 합.
- Worker: quotes 행 `nx`에 `v`(NXT 누적 거래량, 주)·`tv`(NXT 누적 거래대금, 억원) 추가(`overMarketPriceInfo.accumulatedTradingVolumeRaw`·`accumulatedTradingValueRaw`). breadth는 그대로.
- 기본값: NXT 세션이 열려 있으면 **통합**(장 전·장 후엔 사실상 NXT 가격이지만, 장 후에는 KRX 시간외 단일가가 더 최근일 수 있어요), 닫혀 있으면 KRX 정규장 종가. 정규장 중: **실측(09:02) — 네이버가 NXT 메인마켓 가격을 따로 줘요**(`tradingSessionType:'REGULAR_MARKET'` → Worker `nx.s:'reg'`). 그래서 정규장에도 `KRX · NXT · 통합` 모두, 기본 통합. 세션 열림 판단은 `o` 플래그와 시계 창(프리 08:00~08:50, NXT 메인 09:00~15:20, 애프터 15:30~20:00)이 둘 다 맞을 때 — 네이버가 마감 뒤에도 잠시 OPEN으로 남겨 두기 때문이에요.
- 크기 `거래대금`은 고른 기준의 거래대금(통합이면 합산). 표·툴팁에 "통합 거래대금" 식으로 표시.
- 3D 관련 코드는 템플릿에서 정리해요(§3-9).

## 3-11. 관심종목 그룹 (사용자 2026-11-10 09:47: "관심종목을 그룹별로 나눌 수 있게")

**저장**: localStorage `khm.watchGroups` = `{v:1, groups:[{id, name, codes:[…]}], active:'all'|id}`. 처음 열 때 기존 `khm.watch`(코드 배열)를 "기본" 그룹으로 옮겨요(기존 키는 남겨 두되 더는 쓰지 않음). 한 종목이 여러 그룹에 들어갈 수 있어요. 그룹 최대 20개, 이름 최대 12자.

**API (`KH.watch`, 히트맵이 제공 — 기존 메서드는 그대로 동작)**
- `has(code)` = 어느 그룹에든 있으면 true · `list(groupId?)` = 그 그룹(없으면 전체 합집합, 중복 제거) · `toggle(code, groupId?)` = 그룹 지정 없으면 현재 그룹(전체 보기 중이면 "기본")에 넣거나 모든 그룹에서 빼기
- `groups()` → `[{id,name,count}]` · `groupsOf(code)` → `[id]` · `add(code, groupId)` · `remove(code, groupId?)`(없으면 전부에서) · `setGroups(code, [ids])`
- `createGroup(name)` → id · `renameGroup(id, name)` · `deleteGroup(id)`(종목은 다른 그룹에 없으면 관심에서 빠짐 — 확인 문구) · `moveGroup(id, toIndex)`
- 이벤트 `kh:watch` `{codes, groups}` — 바뀔 때마다.

**★관심 탭 화면**
- 지도 위 줄에 그룹 칩: `전체 · 기본 · 반도체 · … · ＋` (가로 스크롤, 현재 그룹 강조, 각 칩에 종목 수). `전체`면 지도의 맨 위 묶음이 **그룹**(섹터 대신), 그룹을 고르면 그 그룹 종목만 섹터 › 업종으로.
- 칩의 `⋯`(또는 길게 누르기)로 이름 바꾸기·순서·삭제. `＋`로 새 그룹(이름 입력).
- 빈 그룹: "종목 페이지의 ☆나 검색에서 이 그룹에 담을 수 있어요" 안내.
- 표 보기에는 그룹 열(여러 개면 쉼표), 그룹으로 정렬 가능.

**종목 페이지·빠른 시트의 ☆**: 누르면 그룹 고르기 작은 팝오버(체크박스 목록 + "새 그룹"), 하나라도 체크면 ★. 키보드·휴대폰 모두 동작(휴대폰은 바텀 시트). 그룹이 "기본" 하나뿐이면 지금처럼 바로 토글하고 팝오버 안 띄워요.

## 3-12. 장 진행 막대 다시 (사용자 2026-11-10 09:55·09:57)

"시계 아래 로딩바가 너무 얇고 식별이 안 돼. 제목 줄에 두꺼운 밑줄처럼 길게. 오전이면 햇살, 오후면 해, 저녁부터 새벽이면 달 아이콘이 현재 시점을 지나가는 느낌" · "모바일에서 맨 오른쪽 '통합 (시간)'의 시간이 굳이 필요한가, 왼쪽에 시계가 있는데"
- **히트맵**: `header.top`의 첫 자식으로 마운트 `<div id="session-bar"></div>`(오케스트레이터가 넣었어요). 머리글 줄 맨 아래 **전체 폭**에 걸리는 막대 자리예요(extras가 `header.top{position:relative}` + 절대 위치로 그려요).
- **extras**: 시계 아래의 얇은 막대를 없애고 `#session-bar`에 **머리글 전체 폭의 두꺼운 밑줄**(데스크톱 6px 안팎, 휴대폰 4~5px, 둥근 끝)로 그려요. 하루를 한 줄로: 08:00 → 20:00(밤 구간은 양 끝에 짧게) 또는 정규장 09:00 → 15:30 중심 — 읽기 쉬운 쪽으로 판단. 구간 색은 §3-6 그대로(빨강·초록 금지), 지난 부분은 진하게, 남은 부분은 옅게. **지금 위치에 아이콘**이 올라가 막대를 따라 움직여요: 오전(장 시작 전~12:00) **햇살**(떠오르는 해: 반원 + 짧은 빛살), 오후(12:00~해 질 무렵/장 마감 뒤 18:00 전후) **해**(원 + 빛살), 저녁~새벽 **달**(초승달). 아이콘은 독자 SVG(16~18px, 막대 위에 걸치게, 아래 내용 가리지 않게), `fancy`면 빛살이 천천히 돌거나 은은히 빛나고, `standard`는 정적, `reduced`는 정적. 마우스 올리면/누르면 "정규장 64% · 15:30 마감까지 2시간 14분" 같은 말풍선. 시계 버튼 아래엔 막대 없음(시계 줄 높이를 줄여요).
- **히트맵(가격 기준 배지)**: 시계가 켜져 있으면 배지에서 시각을 빼요("통합" 대신 버튼이 이미 선택을 보여 주니 배지는 숨겨도 됨) — 시각은 **데이터가 실시간이 아닐 때만**("NXT 08:50 마감", "KRX 15:30 종가"처럼 기준 시점이 의미 있을 때) 보여요. 휴대폰은 특히 짧게.

## 3-13. 목록의 오늘 캔들 (사용자 2026-11-10 10:03)

"각 종목을 눌렀을 때 나오는 테마 주식들 목록에서, 나머지 다른 주식 목록들도 마찬가지고, 캔들의 시가·저가·고가·종가를 알아볼 수 있게. 그리고 목록에서 종목 이름 왼쪽에도 그런 게 있었으면" (스크린샷: 툴팁의 같은 테마 목록 — 왼쪽 색 네모, 이름, 오른쪽 가로 막대, 등락률)

**Worker (오케스트레이터가 넣고 배포함, v11)**: quotes 행에 `op, hi, lo` = KRX 오늘 시가·고가·저가(원). `nx`에도 `op, hi, lo` = NXT 오늘. 첫 체결 전(0·빈 값)이면 세 필드 모두 생략. `/api/quotes?codes=`도 같은 행. breadth·replay 프레임엔 없음. 스냅샷(build_page.py)도 `op, hi, lo`를 남겨요(KRX 종가 기준).

**값 규칙 `ohlc` → `{pc, o, h, l, c}` 또는 null** (지금 고른 가격 기준대로)
- `pc` = 전일 종가(KRX 기준가 = KRX `p − d`). `c` = 지도에 그린 가격.
- KRX: `op/hi/lo/p`. NXT: `nx.op/hi/lo/p`(NXT 체결 없으면 KRX 값). 통합: `o` = `nx.op`가 있으면 그것(NXT 프리마켓 08:00이 먼저 열려요), 없으면 KRX `op`. `h` = 둘 중 큰 값, `l` = 작은 값, `c` = 통합 가격(그러면 `l ≤ c ≤ h`가 안 맞을 수 있으니 `h = max(h, c)`, `l = min(l, c)`).
- `krx-prev`(장 전 어제 종가 0%), 다시 보기, 필드 없는 스냅샷, 첫 체결 전 → null → 캔들 대신 지금처럼 색 네모(또는 같은 자리의 옅은 가로선).

**그림**
- **왼쪽 아이콘(세로 미니 캔들)** — 종목 이름 왼쪽 10px 네모 자리: 폭 8~10px, 높이 ≈ 글자 높이(14~16px). 꼬리 = 저가↔고가, 몸통 = 시가↔현재가(최소 1.5px). 색은 **종목 페이지 차트와 같은 규칙·같은 색**: 현재가 > 시가 = 양봉(상승색), < = 음봉(하락색), 같으면 보합색. 세로 눈금은 그 종목의 고가−저가 폭, 단 폭이 전일 종가의 2%보다 작으면 2%로 잡고 가운데에(조용한 날이 꽉 찬 캔들로 보이지 않게).
- **오른쪽 가로 캔들** — 툴팁·빠른 시트의 같은 업종/테마/관심 목록과 테마 툴팁의 상위 종목, 지금 가로 막대 자리: 가운데 세로선 = 전일 종가(0%), 눈금 ±R(지금 막대와 같은 `curRange()`), 꼬리 = 저가%↔고가%, 몸통 = 시가%↔현재가%, 색 = 양봉/음봉. ±R을 넘으면 그 끝을 잘라 작은 ▸/◂ 표시. **오늘 지표(등락)일 때만**. 기간 수익률·수급 지표일 땐 지금 막대와 색 네모 그대로(목록 숫자가 다른 걸 말하니까).
- **값 알아보기**: 캔들마다 `title`·`aria-label` "시가 199,400 · 고가 201,500 · 저가 197,800 · 현재 198,900". 툴팁·시트 머리(`headBlock`)에 그 종목의 **조금 큰 가로 캔들 + "시가 199,400 (+5.0%) · 고가 201,500 · 저가 197,800"** 한 줄. 목록 제목 줄이나 힌트에 짧은 읽는 법 한 번("가운데 선 = 전일 종가 · 몸통 = 시가→현재가 · 선 = 저가~고가").
- **적용 목록**: 툴팁·시트 목록(왼쪽 아이콘 + 오른쪽 가로 캔들), 테마 툴팁 상위 종목(같음), 표 보기 종목명 셀(왼쪽 아이콘. 1024px 이상에서 '오늘' 가로 캔들 열을 등락률 앞에 넣는 건 판단), 눈에 띄는 종목(왼쪽 아이콘), 검색 제안의 종목 행(왼쪽 아이콘, 테마 행은 네모 유지), 종목 페이지 같은 업종(stock 모듈, 왼쪽 아이콘).
- 600행 표에서도 가볍게(div 2개 또는 작은 인라인 SVG, 애니메이션 없음).

**API (히트맵이 제공, 다른 모듈은 있으면 쓰기)**
- `KH.ohlc(codeOrRow)` → `{pc,o,h,l,c}` | null — 코드면 지금 행, 행(`/api/quotes` 원본 행)이면 그 행으로 같은 규칙.
- `KH.candleIcon(o)` → 요소(세로 아이콘), `KH.candleBar(o, range?)` → 요소(가로 캔들, range 기본 `curRange()`). `o`가 null이면 빈 자리 요소.
- 종목 페이지 같은 업종이 지도에 없는 종목이면 stock 모듈이 `/api/quotes?codes=`(최대 6개, 종목 열 때 한 번)로 행을 받아 `KH.ohlc(row)`.

## 3-14. 섹터 순위 정렬 · 눈에 띄는 종목 더보기 (사용자 2026-11-10 10:07)

"섹터별 등락도 눈에 띄는 종목처럼 상승률순 하락률순 볼 수 있게. 눈에 띄는 종목 상세 더보기 누르면 30~50종목(숫자는 너가 정해)까지 확장 가능하게"
- **섹터별 등락 카드**: 제목 아래에 눈에 띄는 종목과 같은 모양의 탭 `상승률 · 하락률 · 거래대금`(수급 지표면 `순매수 · 순매도 · 거래대금`, 기간 지표면 `상승률 · 하락률`에 기간 이름은 제목이 이미 말함). 상승률 = 큰 값부터, 하락률 = 작은 값부터, 거래대금 = 섹터 거래대금 합(고른 가격 기준 거래대금) 큰 순, 거래대금 탭의 오른쪽 숫자는 거래대금(억/조)이고 막대 색은 그대로 등락. 기본 상승률(지금 동작). 선택은 `khm.secSort`로 기억. 테마 순위 카드(테마 탭)도 같은 탭: 상승률 = 많이 오른 테마부터 전부, 하락률 = 많이 내린 테마부터 전부(지금의 위 6·아래 6 대신, 길면 아래 더보기).
- **눈에 띄는 종목 더보기**: 기본 8개 아래에 `더보기 (30개)` 버튼 → **30개**까지 펼침, 펼친 뒤엔 `접기`. 탭을 바꿔도 펼친 상태 유지(새로고침으로 초기화돼도 됨). 30개가 안 되면 있는 만큼, 버튼 문구도 실제 개수. 펼친 목록도 같은 행 모양(왼쪽 캔들 아이콘 §3-13 포함), 키보드로 버튼 접근. 휴대폰에서 펼치면 목록이 길어지니 `접기`는 목록 끝에, 접을 때 카드 머리로 스크롤 복귀.

## 3-15. Workers Paid($5) 전환 (사용자 2026-11-10 10:18: "클라우드플레어 5달러 계정으로 업그레이드했어")

풀린 것: 하루 요청 상한 없음(월 1천만 포함), 요청당 CPU 기본 30초(최대 5분), 외부·내부 호출 10,000번, KV 쓰기 월 100만, cron CPU 최대 15분, Durable Objects. 이번 차례는 **① 1분 다시 보기 ② 전 종목** 두 가지. (실시간 푸시·가격 알림·기기 간 동기화는 다음 차례.)

### ① 1분 다시 보기 (Worker + extras)
- **cron**: `* 0-7 * * 2-6`(월~금)(매분, 2026-11-14부터 — 그 전 `1-5`는 일~목). 오케스트레이터가 배포할 때 바꿔요. 프레임 키·모양은 지금과 같음: `replay:YYYYMMDD:HHMM`, 09:00 → `endTime`(보통 15:30, 391개).
- **API (예전 화면 호환)**
  - `/api/replay?date=` — 지금 그대로(5분 프레임: 09:00, 09:05 …). 1분 기록이 있는 날도 5분 칸만.
  - `/api/replay?date=&step=1&from=HHMM&to=HHMM` — 그 사이 **1분 프레임**(양 끝 포함, 한 번에 최대 120개), 응답 모양은 5분 응답과 같음(+ `step:1`). 없는 분은 빠져요(잠깐 실패한 분).
  - `/api/replay/dates` — 지금 응답에 `minute: [1분 기록이 있는 날짜…]` 추가.
  - 캐시: 지난 날 1시간, 오늘 1분. 하루치 1분 전체를 한 번에 주지 않아요(휴대폰 데이터 — 프레임 하나 ~10KB × 391).
  - 오늘 요청에서 KV 읽기가 많아지니 묶음 읽기·Promise.all을 쓰되 응답 시간 목표 1초 안.
- **cron 요일 번호 주의** (2026-11-13 금요일 기록 0건의 원인): Cloudflare cron은 요일을 **1=일요일 … 7=토요일**로 세요. 그래서 `* 0-7 * * 1-5`는 **일~목**에만 돌고 금요일엔 한 번도 돌지 않아요(일요일 480번은 기록기가 그냥 건너뜀). 평일은 **`2-6`**(월~금)으로 써야 해요(이름 `MON-FRI`도 같은 뜻이지만, 그렇게 바꾼 뒤 스크립트 업로드가 500을 내서 숫자로 둬요 — 2026-11-14) — `wrangler.toml`을 바꾸면 배포 작업(`ensureCrons`)이 맞춰 줘요. 점검: `node qa/worker/test_replay_recorder.mjs`가 cron이 월~금을 다 덮지 않으면 종료 코드 2.
- **기록기 상태** (2026-11-14): `scheduled()`는 예외를 던지지 않아요 — 실패는 `console.error`(Workers Logs·tail) + KV `replay:status`, 확인은 `GET /api/replay/status`(§3-2). 상태는 결과 종류가 바뀔 때·오류마다·그 밖엔 5분에 한 번만 써요(장중 하루 약 80번, 프레임 391번과 별도). 장 시간 밖(평일 09:00 전·16:30 뒤, 주말)은 지금처럼 KV·네트워크를 건드리지 않아 상태도 안 써요. 한 분이 실패해도 그 분만 잃어요: 네이버 5xx(덩어리마다 1번 재시도)·호출당 40초 시간 초과·빈 응답이나 가격 있는 행이 코드의 절반 미만(널 프레임을 쓰지 않음)·KV 읽기/쓰기 오류·`universe.json` 실패(15초 시간 초과, 검사를 통과한 본문만 엣지 캐시에). Isolate 메모리(`recMem`)에는 실제로 저장된 값만 남겨요. 휴장 판단은 지수 둘 다 CLOSE **이고** 오늘 체결 시각이 최근 10분 안에 없을 때 — 지수 상태가 멈춰도 거래일 하루를 잃지 않게. 이상한 `endTime`(1500~1630 밖)은 1530으로 봐요.
- **extras(다시 보기 UI)**: 5분 뼈대를 먼저 받아 바로 재생 가능 → 뒤에서 1분 조각을 시간대별로 채워 넣기(지금 보는 위치 근처 먼저). 채워진 구간은 슬라이더가 **1분 단위**로 움직이고, 재생 속도 선택(예: 1분=0.25초/0.5초/1초) — 1분이면 하루가 391칸이라 기본 속도를 지금보다 빠르게. 아직 안 채워진 구간은 5분 칸 그대로. `minute`에 없는 날은 지금처럼 5분.

### ② 전 종목 (Worker + 히트맵)
- **Worker**
  - `/api/quotes?scope=all` — 상장 보통주·우선주 전부(유니버스 `K + Q + X`, 약 2,700), 지금과 같은 행 모양(`op/hi/lo`, `nx` 포함). 한 요청 안에서 네이버 polling을 여러 덩어리로 병렬 호출. 엣지 캐시는 지금 quotes와 같은 TTL. **CPU ms·응답 크기(원본/gzip)를 재서 보고** — gzip 250KB 넘으면 작은 종목 행을 줄이는 방법 제안.
  - `/api/breadth?m=K|Q` — `part` 없이 부르면 그 시장 전부를 한 번에(기존 `part=N`도 계속 동작).
  - 기본 `/api/quotes`(상위 300×2)는 그대로.
- **히트맵(§3-14 다음 차례)**: 종목 수 `100 · 200 · 300 · 500` 옆에 **`전체`**. 고르면 `scope=all`로 받아 그 시장 전 종목(전체 탭이면 두 시장 전부)을 그려요. 갱신 주기는 전체일 때 15초. 작은 타일은 지금처럼 이름 없이 색만. 등락 분포는 이미 전 종목. 성능: 360px 휴대폰에서 첫 그리기·갱신이 눈에 띄게 느려지면 알려 주기(측정값 포함).

## 3-16. 시장 탭 아래 상시 등락률 (사용자 2026-11-10 10:30)

"코스피 코스닥 전체 관심 탭은 바로 아래에 상시로 등락률 적혀 있으면 좋겠어. 관심 탭은 내가 원하는 그룹 등락률 선택 가능하게"
- 탭 `코스피 · 코스닥 · 전체 · ★관심` 각각 이름 바로 아래 작은 줄에 **오늘 등락률**(빨강 상승·초록 하락·보합 회색, tabular-nums). 테마·해외·원자재 탭은 숫자 없음(자리도 비워 두지 않아도 됨, 탭 높이는 통일).
- 값: **코스피·코스닥 = 지수 등락률**(quotes `index.KOSPI/KOSDAQ.ratio`, 시장 띠와 같은 숫자). **전체 = 두 지수 등락률을 두 시장 시가총액으로 가중**(가중치는 유니버스 시총 합으로 근사해도 됨 — 툴팁에 "코스피·코스닥 시가총액 가중"). **관심 = 고른 그룹의 시총 가중 등락률**(그 그룹 지도 머리말 숫자와 같은 계산, 고른 가격 기준 반영). 색 기준(기간·수급)과 상관없이 항상 오늘 등락률.
- **관심 그룹 고르기**: 기본은 `전체 관심`(모든 관심종목). 그룹 칩의 `⋯` 메뉴에 "탭에 이 그룹 등락률 표시", 표시 설정 패널에도 "관심 탭 등락률" 선택(전체 관심 · 각 그룹). `khm.watchTabGroup`에 기억, 그 그룹이 지워지면 전체 관심으로. 관심종목이 없으면 숫자 대신 비움.
- 탭 툴팁/aria-label에 "코스닥 +3.69%" 식으로. 다시 보기 중이면 그 시점 값(프레임의 지수 `i`), 스냅샷이면 스냅샷 값.
- 크기: 탭은 두 줄(이름 + 숫자)이 되지만 터치 높이 40px 안팎을 유지하고 **390×844에서 지도 위치(map top) 증가는 8px 이내**(지금 230). 1280 이상에서도 머리글이 한 줄 유지. `fancy`일 때만 숫자 바뀔 때 은은한 깜빡임, 그 밖엔 정적.

## 3-12b. 탭과 진행 막대 사이 간격 (사용자 2026-11-10 10:31: "탭과 진행막대 사이에 간격이 살짝 있었으면 좋겠어 겹쳐 보여서")
- extras: 탭 줄 아래 끝(선택된 탭의 배경·밑줄 포함)과 막대 위 끝 사이에 **눈에 보이는 틈**(데스크톱 6px 안팎, 휴대폰 5px 안팎). 해·달 아이콘도 탭에 겹치지 않게(아이콘이 막대 가운데에 걸치되 탭 줄과는 떨어지게, 필요하면 아이콘을 조금 작게). 390×844에서 이 변경만으로 지도 위치 증가 ≤ 6px. §3-16의 +8px 예산과는 별개로 셈해요.
- (사용자 10:32 "모바일에서는 진행막대를 탭 위로 시계 아래에") **탭이 시계 줄 아래 따로 한 줄을 차지하는 배치(휴대폰·좁은 태블릿)**에서는 막대를 **시계 줄과 탭 줄 사이**로 옮겨요(위아래 모두 틈, 아이콘이 시계·탭 어느 쪽에도 닿지 않게). 탭이 시계와 같은 줄에 있는 데스크톱 배치에선 지금처럼 머리글 맨 아래(위의 틈 규칙 적용). 기준은 화면 폭 숫자가 아니라 실제 배치(탭 줄이 따로인지).

## 3-17. 시계를 서버 시각으로 보정 (사용자 2026-11-10 10:37 "서버시각으로 보정")

질문 "아날로그·디지털 초가 어긋나 보인다, 시간은 어디서?" → 답: 기기 시계 + KST 변환, 어긋남은 화려하게의 58.5초 스윕(역 시계 방식). 사용자는 **서버 시각 보정만** 골랐어요(스윕은 그대로).
- **Worker (배포됨 v13)**: `GET /api/time` → `{t: 서버 ms}`, `cache-control: no-store`(엣지 캐시 안 됨).
- **extras(시계·진행 막대)**: NTP처럼 오프셋 재기 — 요청 직전 `Date.now()`/`performance.now()`, 응답 뒤 다시, 왕복 시간(RTT)의 가운데를 서버 시각으로 보고 `offset = t − (보낸 시각 + RTT/2)`. 처음 3번 재서 **RTT가 가장 짧은 값**을 쓰고, 그 뒤 10분마다·탭이 다시 보일 때 1번씩(RTT가 이전 최선보다 크게 나쁘면 버림). `kstNow()`가 `Date.now() + offset`을 쓰게 해서 시계·진행 막대·말풍선이 모두 따라가요. 실패하면 오프셋 0(기기 시계). 오프셋이 2초 넘게 바뀌면 시계를 한 번에 맞추고, 작으면 다음 초에 자연스럽게. 스냅샷(file://)·오프라인은 기기 시계.
- 시계 버튼 툴팁/aria에 "서버 시각 기준 · 이 기기와 0.3초 차이" 같은 한 줄(차이 0.1초 미만이면 "이 기기와 같아요"). 설정 패널 시계 항목 설명에도 한 줄.
- 다른 모듈이 쓰도록 `KH.now()`(보정된 ms)를 extras가 제공해도 좋아요(있으면).

## 3-12c. 진행 막대 아이콘 키우기 (사용자 2026-11-10 10:39 "진행 막대 아이콘을 좀 더 키워줘, 너무 아래로 내려갔고 안 보여")
- 해·달 아이콘: 휴대폰 **18~20px**, 데스크톱 **20~22px**. 막대의 세로 가운데에 정확히 걸치고(아래로 처지지 않게), 잘림 없이 전부 보이게(부모 `overflow`·clip 확인). 막대 색 위에서도 보이게 어두운 테두리/후광(1~1.5px). 틈 규칙(§3-12b)은 막대 기준으로 유지하되 아이콘은 틈 안으로 들어가도 돼요. 시계·탭 글자에는 겹치지 않게. 이 때문에 지도 위치가 더 내려가야 하면 +4px까지.

## 3-18. 티커의 "네이버 증권 HH:MM 기준" 정리 (사용자 2026-11-10 11:08)

"티커에서 네이버증권 몇 시 기준은 지워 버리고 내 기기 시간이랑 안 맞을 때만 보여 주는 게 나아 보여"
- extras(시장 띠): 끝의 "네이버 증권 / 11:08 기준" 항목을 **평소엔 숨겨요**. 보여 주는 때: 띠 데이터 기준 시각이 지금(§3-17 보정 시각)보다 **2분 넘게 뒤처짐**(장 마감 뒤·휴장·주말 포함 → "15:30 기준"처럼), 갱신 실패("갱신 실패 · 11:02 값"), 스냅샷(file://), 다시 보기 중엔 띠 규칙 그대로. 숨길 때는 자리도 없애요(띠 폭 재계산·흐름 이어짐). 출처 표기는 페이지 아래 출처 줄이 이미 있어서 빠져도 돼요.
- 같이: 다시 보기 안내 문구 "5분마다 기록한 시세예요"를 1분 기록 날엔 "1분마다"로(§3-15). 그리고 히트맵 요청 — `showFrame`에서 `KH.setReplay(frame, …)`의 frame에 `index: {KOSPI, KOSDAQ}`(그 프레임 지수 등락률 %, 이미 재생 패널에서 계산하는 값)를 넣어 주기(§3-16 탭 숫자가 다시 보기 중 지수 값을 쓰게).

## 3-19. 다음 묶음 후보 (사용자 2026-11-10 11:46 "아직 시작하지 말고 … 나머지 모두 좋은 생각이네") — **대기, 사용자 신호 전엔 시작 금지**
- 캔들 머리 줄: 시가처럼 **고가·저가 옆에도 전일 대비 %** ("고가 22,900 (+9.6%) · 저가 21,850 (+4.5%)").
- 후보 전부 채택 의사: ① 공시 배지(OpenDART, 매분) ② 가격 알림(Web Push) ③ 거래 급증·52주 신고/신저 배지 ④ 장중 수급 지도 ⑤ 내 보유 종목 손익(기기 저장) ⑥ 오늘의 시장 요약 카드 ⑦ 관심종목 기기 간 동기화(6자리 코드) · 나중: 실시간 푸시(DO), 다시 보기 섹터 순위 경주, 조건 검색.

## 3-20. 지도 머리줄에 오늘 지수 흐름 (사용자 2026-11-10 12:51·12:52 "모바일은 A, PC는 B")

"코스닥이면 코스닥, 코스피면 코스피 당일 지수 움직임 차트가 지도 머리줄 자리에"
- **휴대폰·좁은 배치(A)**: 지금의 지도 머리줄(제목 · N종목 · 등락률 · 지도/표) **뒤 배경에 연한 선+면 차트**. 높이 추가 0px. 점선 = 전일 종가, 가로축 09:00~15:30 고정(선이 하루 동안 자라요), 끝에 지금 점. 글자 가독성 우선(선·면 불투명도 낮게, 글자 뒤 살짝 어둡게). 768px 태블릿도 A.
- **데스크톱(B)**: 읽히는 한 줄 차트 — 왼쪽 "666.15 / +2.93%", 가운데 선 차트(점선 전일 종가, 지금 위치 세로 눈금), 오른쪽 "12:50 / 15:30". 머리줄 가운데 빈 자리(1024px 이상이면 대부분 충분 — "섹터·업종 이름을 누르면 확대돼요" 안내는 줄이거나 툴팁으로)에 넣어 **높이 추가 0**이 목표, 폭이 360px 안 되면 머리줄 아래 한 줄(+40px 안팎). 마우스 올리면 그 시각·값 말풍선.
- 탭: 코스피·코스닥 = 그 지수. 전체 = 두 지수 선 두 개(이름 표시). 테마·관심·해외·원자재 = 없음(머리줄 지금 그대로). 섹터 확대 중에도 그 시장 지수 유지.
- 선 색: 지금 값이 전일 종가보다 위면 상승색, 아래면 하락색(사용자 팔레트 설정 따름).
- 데이터: `/api/market`의 지수 `spark`(5분 봉, 이미 있음)를 쓰고, 마지막 점은 quotes의 실시간 `index` 값으로 매 갱신마다 이어 붙이기. 다시 보기 중엔 프레임의 지수(`i`, §3-18 `index`)로 그 시각까지만. 스냅샷은 빌드 때 spark를 넣을 수 있으면 넣고, 없으면 숨김.
- `fancy`면 처음 그릴 때 선이 그려지는 효과, 그 밖엔 정적. aria-label "코스닥 오늘 흐름, 지금 666.15 (+2.93%)". null을 native replaceChildren/append에 넘기지 않기.
- 휴대폰 390×844 지도 위치 변화 0(지금 240), 1280 191 유지(B가 따로 줄이 되면 +40까지).

## 3-21. 이미지 저장을 화면 모양 그대로 (사용자 2026-11-10 13:49)

"사진 저장할 때 저렇게 저장됐으면 좋겠어. 지금은 화면이 다 나와 있지 않으면 잘려서 저장되는데, 보라색으로 X 친 부분(지도/표 버튼) 제외하고 히트맵이 저장되면 좋겠어" (첨부: 휴대폰 화면 — 지도 머리줄[코스닥 전체 + 뒤에 지수 선 + 300종목 · +3.73%] → 지도 전체 → 범례[색 오늘 등락률 −3% ▬ +3% · 크기 시가총액])
- extras `saveImage`: 결과 이미지를 **화면과 같은 구성**으로 — ① 지도 머리줄(제목, 그날 지수 선 §3-20 — 휴대폰 모양 A로 배경에, 데스크톱은 B 모양도 가능, N종목 · 등락률; **지도/표 버튼은 빼기**) ② 지도 전체(스크롤 위치·화면 밖과 무관하게 항상 전부) ③ 범례 줄(색 기준 이름, 그라데이션 눈금, 크기 기준; 화면 범례와 같은 값·같은 팔레트) ④ 맨 아래 아주 작게 "11월 10일 (화) 13:50 기준 · 네이버 증권"(출처·시점은 남겨 둠). 지금의 별도 제목 띠는 이 구성으로 대체.
- "잘려서 저장"의 원인을 실제로 찾기: iPhone(WebKit) 경로 — Playwright `webkit` + iPhone 에뮬레이션으로 저장 흐름(다운로드/공유/길게 눌러 저장 대화상자)을 끝까지 따라가 실제 저장되는 이미지가 지도 전체인지, 화면에 보이는 부분만인지 확인. 지도 일부가 화면 밖일 때, 스크롤 중간일 때, 전체(2,600종목)일 때 모두.
- 데이터: 지수 선은 extras가 이미 받는 `/api/market` spark + 실시간 index, 범례는 화면 범례 DOM이나 KH 값에서. 템플릿 수정이 꼭 필요하면 무엇이 필요한지 보고.
- 해외·원자재 탭의 저장도 같은 원칙(머리줄 + 본문 전체 + 범례), 리스트 모드면 지금처럼.

## 3-22. 티커 개선 (사용자 2026-11-10 13:56)

"티커에서 각 지수 누르면 그 지수 상세 창이 나오면 좋겠고, 지금 티커 누르면 멈추고 자동으로 다시 안 움직여" · "티커에 어떤 항목 넣을지(종목·지수·환율·원자재·관심종목·종목 그룹 등) 선택 가능하게"
- **누르면 상세**: 티커 항목을 누르면(탭·클릭·Enter) 그 항목의 상세 창. 지수·원자재·해외는 해외 탭과 같은 상세 시트(world `openDetail` 재사용 — world.js에 `KHWorld.openDetail(key)`를 내보내고, 해외 탭이 아닐 때도 데이터를 받아 열리게). 코스피·코스닥은 그 시트에 **오늘(장중) 선**(`/api/market` spark + 실시간)도 보여 줘요. 개별 종목은 종목 페이지(`KH.openStock` 류). 상세가 없는 항목(지원 안 되는 키)은 네이버 링크가 있는 작은 정보 창. 키보드로도 열림, 포커스 링.
- **멈춤 동작**: 탭 한 번에 영구 정지되지 않게. 손가락이 닿아 있는 동안(누르고 있기·끌기)만 멈추고, 떼면 약 2초 뒤 자동으로 다시 흐름. 상세 창을 열면 멈췄다가 닫으면 다시 흐름. **영구 정지는 ⏸ 버튼만**(지금처럼 `khm.tickerPaused`에 기억). 끌어서 앞뒤로 넘겨 보기는 있으면 좋음(판단).
- **항목 고르기**: 표시 설정에 "티커 항목" → 편집 시트. 분류: 국내 지수(코스피·코스닥) · 해외 지수(해외 탭 목록) · 환율(원/달러 등 제공되는 것) · 선물(미국 지수 선물) · 원자재(해외 탭 원자재 목록) · 가상자산(비트코인) · **개별 종목**(검색으로 추가) · **관심종목**(전체 또는 그룹 하나 — 그 그룹 종목들이 차례로 흐름). 순서 바꾸기(위/아래 버튼, 끌기는 선택), "기본값으로" 버튼. 저장 `khm.tickerItems`(없으면 지금 기본 구성). 종목은 quotes 값으로(지도에 없으면 `/api/quotes?codes=` 묶음), 해외·원자재는 `/api/world?kind=`(30초), 나머지는 `/api/market`. 항목이 많아도 티커 속도는 일정(px/초), 데이터 실패 항목은 회색 "—".
- 휴대폰(사용자는 **안드로이드**)에서 편집 시트는 바텀 시트, 터치 목표 40px 이상.

## 3-23. 다음 묶음 순서 (사용자 2026-11-10 14:10) — **사용자가 "시작하자"고 할 때까지 시작 금지** (§3-19 대체)
지금 진행 중인 것(§3-21 폰 이미지 B 차트, §3-22 티커)이 끝난 뒤 이 순서:
- **맨 처음 (사용자 14:12 추가)**: ⓪ 디자인·UI·UX 정리, 분석, 개선 — 전체 화면 감사(일관성·위계·간격·글자 크기·색·터치 목표·흐름), 문제 목록과 개선안을 먼저 보여 드리고 고른 것부터 반영. **일관성·표준화 포함**(사용자 14:44): 같은 값은 어디서나 같은 출처·같은 가격 기준·같은 시점(시세 저장소 하나), 용어 통일(실시간/장 중/마감/종가/기준 시각), 숫자·등락률 표기 규칙(소수 자리, 부호, 단위, 억/조), 색·아이콘·배지 규칙, 컴포넌트(시트·팝오버·칩·탭) 모양과 동작 통일 — 규칙을 문서로 만들고 전 화면을 그 규칙으로 맞추기
- 먼저: ① 공시 배지(OpenDART 매분, 타일 "공시" 표시 + 제목) ② 가격 알림(관심종목 ±5%·목표가·상한가 근접, Web Push, 매분 cron) ③ 거래 급증·신고가 배지(거래대금 20일 평균 3배 🔥, 52주 신고/신저 ▲▼) ④ 실시간 푸시 갱신(Durable Objects + WebSocket)
- 그다음: ⑤ 장중 수급 지도(외국인·기관 잠정 추정) ⑥ 내 보유 종목 손익(기기 저장) ⑦ 오늘의 시장 요약 카드 ⑧ 관심종목 기기 간 동기화(6자리 코드)
- 나중에: 다시 보기 섹터 순위 경주 · 조건 검색
(고가·저가 등락률은 2026-11-10 12:06에 이미 반영.)

## 3-23b. 로드맵 순서 (사용자 2026-11-14 00:24·00:26 — §3-23을 대체)
"공시배지 다음에 실시간 갱신 다음 오늘의 시장 요약 카드 그 다음 장중 수급 지도 그 다음은 나머지 차례로" + "증시 캘린더를 오늘의 시장 요약 카드 바로 다음에" + "보유종목 동기화가 관심종목 동기화랑 같이되게":
1. 공시 배지(진행 중 — 서버 `feat/disclosure-api`, 시안 `feat/disclosure-draft`) → 2. 실시간 갱신(**상태 2026-11-14: 1단계 a 서버 배포됨(03:49, §3-2 `/api/live`), 1단계 b 화면 구현 `feat/realtime-page`(병합 전 — `src/live`, §3-7, realtime.md §7-5: 페이지당 소켓 하나, 상태 표시 실시간 · 연결하는 중 · 다시 연결하는 중 · 10초마다 갱신 · 시세 지연, 설정 `실시간 갱신` 기본 켬)**; 설계 `docs/standards/realtime.md` — 추천 D: Durable Object 허브가 3초마다 상위 600을 받아 바뀐 칸만 WebSocket으로, 안 되면 지금 10초 폴링; 시제품 `prototypes/realtime/`, 빌드에 안 들어가요. **결정 (사용자 2026-11-14 02:46)**: 개인·가족·지인용이라 **Cloudflare 유료 기본 $5 말고는 추가 요금 0** — 포함 사용량 안에서만 돌게 상한·안전장치를 둬요; 실시간은 **코스피 상위 300 + 코스닥 상위 300만**(전체 2,700은 지금처럼 폴링); 네이버 확인 주기는 추천대로 3초(평일 실측이 더 느리면 실제 바뀌는 주기에 맞춤)) → 3. 오늘의 시장 요약 카드 → 4. **증시 캘린더**(한국 = 한국은행 ECOS, 미국 = FRED 발표 일정, 금통위·FOMC 1년치 직접 입력, 기업 일정 = OpenDART, 중요도 별은 자체 기준; ECOS·FRED 무료 키는 사용자가 발급 → **Worker 비밀값 `ECOS_KEY`·`FRED_KEY`로 넣어 둠**(2026-11-14 02:08, 둘 다 실제 호출로 확인 — 값은 저장소·파일·로그에 쓰지 않아요)) → 5. **조건 검색**(사용자 02:12 "조건 검색을 장중 수급 지도보다 먼저") → 6. 장중 수급 지도 → 7. 가격 알림 → 8. 거래 급증·신고가 배지 → 9. 보유 종목 손익(기기 저장, 처음부터 동기화하기 좋은 모양으로) → 10. **관심종목 + 보유 종목 동기화**(기기에서 암호화해 서버엔 알아볼 수 없는 내용만, 6자리보다 긴 코드, 무엇을 넘길지 고르기) → 11. 섹터 순위 경주.
- 그 뒤: 추가 기능 후보 전체 검토(급등 이유 한 줄 · 일정 카운트다운 · 연속 순매수 배지 · VI·상한가 알림, 사용자 23:20 "나중에 전체 검토") → 미국 주식(맨 끝).
- ⓪ 디자인·UI·UX 전체 점검은 이 순서에 없어요(사용자가 넣으라고 하면 넣기).
- **지금 순서 (사용자 2026-11-15 20:03 "앞으로의 작업순서 정리해줘" → 21:51 "끝나면 위에서 계획했던 순서대로 진행해줘")**: 지금 하는 것(일정 탭 보완 · 떠 있는 창 움직임 · 탭 묶음 + ★관심 고정 · 팝오버 고침) → ⑤ 종목 페이지 공공데이터(대차잔고 · 기업기본 · 배당, `feat/stock-datago`) → ⑥ 기존 화면을 디자인 기준으로(템플릿 → extras → 종목 페이지 → 해외 · 지표 → 뉴스 · 공시 · 아래 막대, `--live` · `--fail-dot` 앰버 밖으로, 빛 · 그라데이션 없애기 — 오케스트레이터 제안, 사용자가 순서 바꾸라는 말 없음) → ⑦ 증시 캘린더 2단계(주총 · IR · 실적 예고, 발표 시각 보강) → 위 로드맵 5(조건 검색) → 6(장중 수급 지도, 사용자 20:03 "나중에 순서대로 하면 되겠네") → 7 … 11 → 추가 기능 검토 → 미국 주식. 나중에 정할 것: 관세청 수출입 · 수출입은행 API 쓰임(§3-27).

## 3-24. 앞으로 쓸 에이전트 (사용자 2026-11-13 10:51 "3번 맞아" — 지금은 시작하지 않음)
사용자가 준 세 에이전트 정의(원본은 저장소 밖 오케스트레이터 작업 폴더에 보관, 공개 저장소에 올리지 않음)를 §3-23 작업을 "시작하자"고 할 때부터 씀. 모두 opus · xhigh.
- **크리에이티브 웹 제작**: 표준 문서(docs/standards/*.md, DESIGN.md, DECISIONS.md) 부트스트랩 → 레퍼런스 리서치 → A(관례)/B(창의) 시안 → 다관점 리뷰 → 승인 후 부분별 구현. ⓪ 디자인·UI·UX·일관성 작업과 새 기능 화면 설계에 사용.
- **웹 페이지 QA**: 적대적·초심자·전문가 관점의 기능·레이아웃·접근성·성능·보안(비침습)·PWA 점검 리포트 + 개선안/제로베이스 비교. 파일 수정은 승인 후. (정의에 있는 SSSlot 배포 절차는 이 프로젝트와 무관 — 쓰지 않음.)
- **목적 적합성 검증**: 금융 도구로서 유용성·실용성·데이터 팩트(출처·갱신·지연·교차 검증)·오해 위험을 페르소나별 점수(가중 종합)로 평가, 개선 vs 제로베이스 판단, 리포트 md + 점수 JSON. (firecrawl·similarweb·exa MCP는 이 환경에 없음 → web_search·web_fetch·Playwright로 대체하고 한계 명시.)
- 순서 제안: ⓪ 시작 시 QA + 목적 적합성 리포트(병렬) → 크리에이티브가 표준 문서·개선안 → 사용자 선택 → 구현 → QA 재검증(회귀 비교).

## 3-25. 살아 있는 컨트롤 (사용자 2026-11-13 11:18: "버튼이 이런 형식으로 생동감 있게 바뀌었으면 좋겠어", 첨부 = 사용자 자신의 SSSlot 6.0 컨트롤 규칙 시안)
레퍼런스(저장소 밖 보관): 누름 1px 가라앉음+그림자 짧아짐+filter(0ms 내려감/--mo-fast 올라옴), 비동기 버튼(같은 상자에서 글자 교체 → 고리 → 체크 pop/실패는 까닭 글자), 세그먼트(파인 트레이 + 솟은 표시, 앞 가장자리 fast·뒤 base로 따라옴), 칩(켜짐 = 채움+테+체크 폭 0→14), 스위치(파인 트랙+솟은 손잡이, 252ms ease-inout, 끌기), 굴러가는 숫자, 포커스 3px/2px, 44px 누름 영역, 길이 180·320·560ms, 곡선 out·in·inout, pop은 완료 체크에만, 움직임 줄이기면 전부 즉시.
- 진행: **크리에이티브 웹 제작 에이전트**(§3-24)가 먼저 사이트의 모든 컨트롤 목록 → 규칙 문서(docs/standards/controls.md, 모션 토큰) → 시안(drafts/controls.html, 실제 컨트롤을 새 규칙으로, 변주 2안) → 사용자 승인 → 모듈별 구현.
- 효과 단계 매핑: reduced = 즉시(끝 상태만), standard = 누름·표시 이동·글자 교체, fancy = + 체크 pop·숫자 굴림·고리 등 전부.
- **결정 (사용자 2026-11-13 12:32)**: ① **V1 입체**(레퍼런스 표면 그대로 — 솟은 키·고른 칸 그림자, 깊은 트레이) ② 기존 `docs/motion-brief.md` 개정: 컨트롤 누름은 1px 가라앉기(0.97 축소 대신), `--ease-pop`은 완료 체크에만 허용, 데이터 모션 토큰(`--m-*` 120/240/480)은 그대로 ③ 아이콘만 있는 키의 결과 문구는 키 아래 자리 차지 없는 말풍선 + aria-live ④ 적용 순서: 히트맵 첫 화면(template) → extras(티커·시계·진행 막대·이미지 저장·다시 보기) → 종목 페이지 → 해외·원자재, 단계마다 스크린샷 검증·커밋, 단계마다 오케스트레이터가 병합·배포. 완료·실패는 앰버 + ✓/! + 글자(빨강·초록 금지). 레이아웃 고정(글자 상자 최장 폭, 지도 위치 불변).

## 3-26. 판세 · 테마 · 휴대폰 아래 줄 (사용자 2026-11-13 19:45~20:01)

**이름과 주소**: 사이트 이름 **판세**(영문 Panse), 주소 **`https://panse.pages.dev`**(pando.pages.dev는 남이 쓰고 있어 판세로 정함).
- 제목 `판세`(사용자 22:28: 설명 문구 없이), 머리글 제목·시계 aria "판세 · 지금 HH:MM · 눌러서 새로고침", 종목 페이지 제목 "… · 판세", 매니페스트 name·short_name "판세". 저장소·Worker 이름은 그대로.
- **이사**: 옛 Pages 프로젝트 `kospimap`의 `_worker.js`는 화면 요청에 작은 다리 페이지를 줘요 — 그 브라우저의 `khm.*` localStorage를 `#khm-import=<base64 JSON>~<원래 해시>`로 실어 `panse.pages.dev`로 `location.replace`. `/api/*`·`/data/*`는 계속 Worker로 프록시(열려 있던 옛 탭용), 그 밖은 301. 해시는 서버로 가지 않아요.
- 판세 쪽(`src/template.html` 머리의 첫 스크립트): `#khm-import=`가 오면 **첫 이사(`khm.migrated` 없음)는 옛 값으로 덮고**, 그 뒤엔 빈 키만 채운 뒤 `khm.migrated`를 적고 해시를 원래 값으로 돌려놔요. 홈 화면 앱은 새 주소에서 다시 설치해야 해요(출처가 달라요).

**테마 결정** (시안 `drafts/themes.html`, 표준 `docs/standards/themes.md`)
- 내보낼 테마: **기본**(지금 다크) · **신문**(따뜻한 종이 A + `명조 제목` 선택, 기본 꺼짐) · **글라스 어둡게(A)** · **글라스 밝게(B)**. 신문 B는 버림.
- 밝은 테마(신문·글라스 밝게)는 §4 "다크 톤"의 **이번 한 번 예외**(사용자 승인). 기본 테마는 계속 다크.
- **시계는 모든 테마에서 지금 모양 그대로**(플랩 판·아날로그 판·빨간 초침 색을 테마가 바꾸지 않음).
- 스크롤하면 머리글(휴대폰은 탭 줄)이 따라와요: **글라스**(유리 판, 휴대폰 포함 — 블러를 못 쓰면 불투명 판)와 **신문**(불투명 종이 띠 + 먹 줄).
- 크기·배치는 테마와 무관(지도 위치 불변), 빨강·초록은 데이터에만.

**결정 (사용자 2026-11-13 20:50)**: 아래 막대 = **V2 두 칸 + 넘겨 보기**(1쪽 지수+등락 분포, 2쪽 관심+다른 시장 지수), 🔍 **오른쪽**, **모든 테마**(기본 포함) 스크롤 시 머리글 따라옴, 테마 고르기 **네 칸 한 번에**. 규칙 문서 `docs/standards/themes.md` · `docs/standards/dock.md`(§15 구현 나누기). 시계 개선(초침 끝 속이 빈 고리 · 판 둘레 정규장 호 · 개장/마감 10분 카운트다운 · 길게 눌러 세계 시계 · 15:20 동시호가 앰버 테두리) 사용자 20:19 채택, extras가 구현.

**휴대폰 아래 떠 있는 줄** (요청 원문): 스크롤을 내리면 화면 아래에 따라오는 작은 줄 — 내용은 고를 수 있게(관심종목 / 내가 고른 지수 / 등락 분포, 끄기 포함), 한쪽 끝에 **종목 검색 돋보기**(내용을 꺼도 남음). 시트·종목 페이지가 열리면 숨고, 마지막 내용이 가리지 않게 아래 여백. 숫자는 페이지의 다른 곳과 같은 출처·같은 가격 기준.

## 3-27. 뉴스 · 색 범위 자동 · 해외 묶음 (사용자 2026-11-13 22:19~22:26)

**뉴스 패널** (22:19 "pc에서 아래에 공간이 빈 것 같아서 연합인포맥스, 한국경제, 매일경제 뉴스 못가져오나?"): PC는 지도 아래 빈자리, 휴대폰은 맨 아래 카드(최신 5 + 더보기). 시각 · 언론사 · 제목만, 누르면 원문 새 탭(본문·요약·이미지·로고 없음). 제목 속 지도 종목 이름은 표시 → 누르면 빠른 시트. 원천 RSS(정직한 User-Agent, 엣지 캐시 몇 분, 막히면 그 언론사는 빠짐 — 우회하지 않아요): 연합인포맥스 `news.einfomax.co.kr/rss/allArticle.xml`, 한국경제 `www.hankyung.com/feed/finance`, 매일경제 `www.mk.co.kr/rss/50200011/`. 모양은 시안(`drafts/news.html`, `docs/standards/news.md`) 뒤 사용자 선택.
- **결정 (사용자 2026-11-13 23:14 "너 추천대로 c안으로 하는게 낫겠다") → C안**, 구현 `feat/news`: Worker `/api/news`(§3-2 표), 템플릿 마운트 `#news`(main.layout 마지막 칸, PC 두 줄 격자) · `KH.quick` · `KH.hover` · 토큰 `--row-hov --mk-bg --mk-line --dchip-bg` · 출처 줄 `#foot-news`, 모듈 `src/news/news.js · news.css · match.js`(빌드: world 다음). 1920 × 1080처럼 빈자리가 작으면 최소 5줄(두 단 10개)을 지켜요(오케스트레이터 결정). 탭은 기사가 있는 언론사만(지난 목록 포함) — 받지 못했고 지난 목록도 없는 언론사는 탭 · 출처 줄에서 빠지고 따로 오류 문구 없음, 다시 되면 다음 갱신에 탭이 돌아와요.
- **매일경제 릴레이** (2026-11-14 19:59 한국 데이터센터에서만 매일경제 실패 → 6시간 뒤 지난 목록 만료로 탭이 사라짐. 사용자 20:05 "나중에 다른 지역 서버에서 받아오게 해줘", 진행 11-15, 조건 **$5 말고 추가 요금 0**). 설계 · 비용 전체는 `docs/standards/news.md` §2-6. `NEWS_SRC`의 언론사별 표시 `via:'relay'`(지금 `mk`만) → **이미 있는 DO 클래스 `MarketHub`의 다른 이름 인스턴스 `idFromName('news-relay')`**(`locationHint:'enam'`)가 내부 경로 `GET /__relay/news?src=<키>`(허용된 키만, 주소는 안 받음, 공개 인터넷에서 닿지 않음)로 한 번 받아요. **새 DO 클래스 없음** → `wrangler.toml` · 배포 메타데이터 그대로, 푸시로 평소 배포. 릴레이 인스턴스는 소켓 · 알람 · 폴링 없고 허브 `guard`를 건드리지 않아요(자기 저장소 키 `relay`에 하루 계수만). 순서: 쉬는 중이면 지난 목록 → `news:last:mk`가 180초보다 젊으면 그것(DO 요청 0) → 릴레이(7초) → 릴레이 자체가 실패했거나 403/429가 아닌 실패면 이 데이터센터에서 직접(전체 10.5초 안) → 지난 목록. **403/429는 어디서 받든 15분 쉬고 다른 곳에서 다시 시도하지 않아요.** 하드 상한 하루 1,500번(넘으면 그 데이터센터가 KST 자정까지 Cache API로 기억 → DO 요청 0). 비용: 평소 하루 100~150번 ≈ DO 요청 월 0.3~0.45 % · duration 0.2 %, 상한까지 가도 4.65 % · 10 % — 실시간 허브 최악과 합쳐 약 76 % · 60 %.
  - **운영 메모 — 언론사가 왜 실패했는지 보기**: KV `REPLAY`의 **`news:err:<src>`**(3일, 언론사마다 30분에 한 번) = `{at, colo, path:'relay'|'direct', error, status?, egress?, relay?, fallback?}`. 릴레이가 정말 북미에서 나가는지는 `news:last:mk`의 `egress`(매일경제 `cf-ray`의 데이터센터, `IAD` 근처여야 해요 — `ICN`이면 힌트가 안 먹은 것, 이름을 바꿔 새로 만들기). 점검 `node qa/news/worker_test.mjs`(105).
  - 확인 2026-11-15 16:12: 배포 뒤 `sources.mk.via:'relay'`, `news:last:mk.egress` = **MIA**(북미) — 힌트가 먹었어요.
  - **결정 (사용자 2026-11-15 17:09 "매일경제 또 막히면 다음엔 빼버리자")**: 릴레이로도 매일경제가 다시 막히면(탭이 사라지거나 `news:err:mk`에 실패가 이어지면) 고치려 하지 말고 **`NEWS_SRC`에서 매일경제를 빼요**(출처 줄 · 탭 · 문서 함께). 사용자에게 알리고 빼요.
- **출처 추가 결정** (사용자 2026-11-15 16:07 후보 4곳 → 16:25 "Kdi만 가져와야겠다" + 관보 API 승인 내용 붙임): **KDI 경제교육·정보센터 경제정책자료 RSS** `https://eiec.kdi.re.kr/policy/rss.do?rss_type=material` 와 **행정안전부 관보 목록 정보 API**(공공데이터포털 REST, End Point `https://apis.data.go.kr/1741000/ApiTotalService`, 개발계정 자동승인 2026-11-15 ~ 2028-11-15) 를 넣어요. 뉴스와이어 · PADO는 넣지 않아요. 공공데이터포털 인증키는 **Worker 비밀값 `DATA_GO_KR_KEY`**로만 넣어 둠(2026-11-15 16:2x) — 값은 저장소 · 파일 · 로그 · 메모리에 쓰지 않아요. 진행은 **디자인 기준을 먼저 잡은 뒤**(사용자 16:25 "디자인 기준을 먼저 잡고 가자").
- **정책 자료 구현** (`feat/policy-feeds`, 2026-11-15 — 위 결정 "Kdi만 가져와야겠다" + 관보 API): 규칙 · 실측 · 호출 수는 `docs/standards/policy-feeds.md`. Worker `worker/src/policy.js`(`GET /api/policy`, §3-2 표; `index.js`는 import 한 줄 + 경로 한 줄만), 화면 `src/policy/policy.js · policy.css`(빌드: 공시 다음) = 뉴스 카드의 세 번째 제목 탭 **정책 자료**(`KHNews.addTab`, news.js는 고치지 않았어요) — 출처 필터 칩 `전체 · KDI · 관보`, 줄 = 날짜(오늘 · M/D) · 출처 배지 · 제목(새 탭) · 기관(· 편집구분), design.md 토큰만. 탭이 보일 때만 10분마다 받아요. 출처 줄 `<p id="foot-policy">`는 **공시 줄 바로 뒤**(© · 투자 유의 문구 위 — §3-30 순서에 정책 자료가 공시 다음으로 들어가요), 템플릿을 고치지 않고 모듈이 `#foot`을 지켜보며 붙여요. 관보 거르기(시장 관련 기관 · 인사 제외)는 `GB_ORG_RE` 한 곳. 호출 수: 관보 하루 약 35~70번(개발계정 10,000의 1 % 안, 상한 1,500), KDI 평일 약 50번. 점검 `node qa/policy/worker_test.mjs` · `python3 qa/policy/test_policy.py`. **배포 뒤 확인**: `/api/policy`의 `sources.gwanbo.ok` · `scanned`(키 반영 · 실제 응답 모양 — 키가 없어 실제 관보 응답은 아직 못 봤어요), 관보 링크가 원문으로 열리는지, KDI 날짜가 최근 평일인지(policy-feeds.md §7).
- **수출입은행 확인 경로** (사용자 2026-11-15 20:04 "수출입은행 환율 · 국제금리 API는 실시간 아니야?" → 답: 영업일 하루 한 번 고시값 → 20:12 "그래 그렇게하면 되겠네" = 월요일 실제 호출로 갱신 시각 · 내용을 보고 쓰임을 정해요): `GET /api/koreaexim/probe[?d=YYYYMMDD]` → `{asOf, date, fx, rate}` — `fx` = `exchangeJSON`(data=AP01), `rate` = `internationalJSON`(data=AP03), 각각 `{ok, http, ms, bytes, n, result, fields, rows(최대 40)}` 또는 `{ok:false, error, head?}`. `no-store`, 같은 날짜는 KV `kxim:probe:<날짜>` 10분, 원천 호출은 KV `kxim:calls:<오늘>`로 하루 60번까지(넘으면 429). 키는 응답 · KV · 로그에 남지 않아요(오류 글자에서도 지워요). 화면은 아직 쓰지 않아요 — `worker/src/koreaexim.js`.
- **한국수출입은행 Open API 키 받음** (사용자 2026-11-15 16:31): 환율 `https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON`, 국제금리 `https://oapi.koreaexim.go.kr/site/program/financial/internationalJSON`. 키는 **Worker 비밀값 `KOREAEXIM_FX_KEY` · `KOREAEXIM_RATE_KEY`**로만(값은 저장소 · 파일 · 로그 · 메모리에 쓰지 않아요). 쓰임(지표 탭 환율 · 금리 보강 후보)은 디자인 기준 다음에 정해요.

**색 범위 자동** (22:26 "현재 보이는 최고 최저에 맞게 자동 조절 … 코스닥에서 범위 10퍼센트로 하다가 해외나 원자재 탭으로 가면 … 색상 차이가 없어져서 불편해"): 템플릿이 테마 작업을 병합한 뒤 구현.
- 색 범위에 `자동` 추가(기본값): 지금 화면에 그린 항목 등락률 절댓값의 95번째 백분위를 1·2·3·4·5·7·10·15·20·30% 중 올림 — 상한가 하나가 전체를 흐리게 만들지 않게. 범례에 "자동 ±4%"처럼 실제 값. 갱신 때 깜박이지 않게 단계가 바뀔 때만(작은 히스테리시스).
- 수동 선택은 **국내(코스피·코스닥·전체·테마·관심)와 해외·원자재를 따로 기억**.
- **구현 (feat/auto-range)**: 색 범위 `자동 · ±3% · ±5% · ±10%`(오늘 등락률일 때만; 기간·수급 색은 지금 범위 그대로). 저장 `khm.range`(국내, 옛 키 — 저장된 숫자는 그대로) · `khm.rangeW`(해외·원자재, 새 키), 값 `'auto'|3|5|10`, 없으면 자동. 측정 범위 = 그 탭이 그리는 항목(국내: 그 탭의 지도 종목 — 시장 상위 N·테마 개요의 테마·테마 종목·관심 그룹, **섹터 확대로 좁히지 않음**(확대해도 색이 안 바뀌게) / 해외·원자재: world.js가 `KH.feedRange(kind, ratios)`로 넘기는 항목, VIX 제외). 백분위는 선형 보간(p95). **히스테리시스**: 탭마다 따로 — 더 큰 단계는 바로, 더 작은 단계는 `p95 ÷ 0.85`가 그 단계에 들어갈 때만(= p95가 아래 단계보다 15% 이상 작을 때). 단계가 바뀔 때만 `kh:palette`. API `KH.rangeInfo()` → `{value, auto, pick, p95, scope}`, `KH.range()`는 지금 값(자동이면 그 단계). 범례 "자동 ±4%" 태그(앰버 아님, 가는 테). 1280~1339px 도구 줄은 자리가 모자라 `±`를 숨겨요(`3% · 5% · 10%`, 이름엔 ±). QA `qa/tabs/test_auto_range.py`.

**해외 묶음** (22:26 "빅스는 미국 빅스니까 미국 지수쪽에 … 선물같은경우도 각 나라 지수랑 같이 묶여야"): 미국 선물·VIX를 미국 묶음으로(목록: 현물 → 선물 → VIX 참고), 세계지도의 옆 상자는 **남겨 두고 제목을 "미국 선물 및 변동성 지수"로**, 그 상자에서 **유로스톡스 50만 빼서** 유럽(유로존) 쪽으로(사용자 22:32 정정). 미국 시트에도 선물·VIX가 현물 다음에 나와요. Worker 묶음은 그대로, world.js가 화면에서 다시 묶어요.

## 3-28. 환율 · 금리 (사용자 2026-11-13 22:34·22:35) — 지금 작업(테마·해외 묶음·뉴스 시안)이 끝난 뒤 시작
"환율탭이 필요할거같아 아님 중요한 원달러랑 유로랑 엔만 있으면 되나?" → 추천안 1 채택: 새 탭 대신 **원자재 탭을 넓혀 환율 묶음**, + "달러인덱스와 달러엔도 좋은 생각" + "국고채, 일본 국채, 미국 국채도".
- 환율: 원/달러 · 달러인덱스 · 원/엔(100엔) · 원/유로 · 원/위안 · 달러/엔(사용자 2026-11-14 02:14 "원/달러 바로 다음에 달러인덱스"). 묶음 제목 옆 "오르면 원화 약세"(달러인덱스·달러/엔은 "오르면 달러 강세"·"오르면 엔화 약세"). 빨강·초록은 숫자의 오르내림만.
- 금리: 미국 국채(2·10·30년) → 한국 국고채(1·3·10년) → 일본 국채 10년 — 값은 %, 변화는 bp(0.01%p). 색은 금리 오르내림. 순서는 사용자 지시 "지표탭의 금리 순서를 미국 국채를 먼저 국고채를 그다음"(2026-11-14).
- 원천(2026-11-13 실측, `api.stock.naver.com/marketindex/…`): `exchange/FX_USDKRW`·`FX_JPYKRW`·`FX_EURKRW`·`FX_CNYKRW`·`.DXY` 응답 있음, 달러/엔은 `FX_USDJPY`·`JPY=` 없음 → 다른 코드 찾기, 없으면 원/달러 ÷ 원/엔으로 계산하고 "계산값" 표시. `bond/KR1YT=RR`·`KR3YT=RR`·`KR10YT=RR`·`US2YT=RR`·`US10YT=RR`·`US30YT=RR`·`JP10YT=RR` 응답 있음. Worker `/api/world?kind=commodity`에 `fx`·`rates` 묶음을 더하거나 `kind=macro` 신설(구현 때 판단), 차트 경로도.
- 탭 이름: **"지표"로 확정**(사용자 2026-11-13 23:20). 이름은 템플릿 `MKT_NAME.CMDTY` 한 곳에만 있어요 — 탭 버튼 글자·aria-label("지표: 원자재 · 환율 · 금리"), world.js 머리 제목·안내 문구, extras 이미지 저장 제목이 모두 거기서 읽어요. 해시는 그대로 `#cmdty`, 탭 안 묶음 이름은 원자재 · 환율 · 금리.

**구현 (feat/fx-rates, 2026-11-13)**
- **Worker** `GET /api/world?kind=commodity&with=fx,rates` → 기존 원자재 묶음 뒤에 `{key:'fx', name:'환율'}`, `{key:'rates', name:'금리'}`. `with` 없이 부르면 응답이 예전과 똑같아요(티커 고르기가 그걸 읽어요). `with`는 `fx`·`rates` 중 쉼표로, `kind=index`에 쓰거나 다른 값이면 400. 30초 캐시, 묶음마다 따로 실패(빠진 쪽만 없음). 항목 모양은 §3-4 그대로 + `bp`(금리: 변화 %p × 100, 소수 둘째 자리), `eod:true`(하루 한 번 종가), `calc:true`(계산값), `via`(하나은행 고시 · 미국 ICE선물거래소 · 레피니티브). 금리 `unit:'%'`, `tz`는 설정값(서울·뉴욕·도쿄). 차트 `/api/world/chart/{key}`도 같은 키로(일봉 종가, `…/marketindex/{exchange|exchangeWorld|bond}/{코드}/prices`).
- 키: `FX_USDKRW` `FX_JPYKRW` `FX_EURKRW` `FX_CNYKRW` `DXY` `USDJPY` / `KR1YT` `KR3YT` `KR10YT` `US2YT` `US10YT` `US30YT` `JP10YT`(로이터 코드에서 앞 점과 `=RR`을 뺀 값).
- **순서**: 지표 탭은 **환율 · 금리 → 원자재**(사용자 2026-11-14 02:11 "환율/금리를 원자재보다 먼저").
- 원천: 원화 환율 4개 + 달러인덱스 = `api.stock.naver.com/marketindex/exchange` 목록 한 번(polling 호스트엔 `exchange`가 없어요). **달러/엔 = 원/달러 ÷ (원/엔 ÷ 100)**, 같은 하나은행 고시 회차로 계산한 값이 먼저예요(`calc:true`, `via:'하나은행 고시로 계산'`, 장중/마감은 두 값 모두 OPEN일 때만 OPEN, 오케스트레이터 2026-11-13) — 화면은 상태 칸에 "계산값", 시트 출처 줄에 "차트는 레피니티브 종가". 계산할 수 없을 때만 `exchangeWorld/USDJPY`(polling, 레피니티브 **하루 한 번 종가**, `eod:true` — "마감 · 하루 한 번 종가", 기준일만). 차트 경로는 언제나 `exchangeWorld/USDJPY` 일봉 종가(마지막 점은 계산값). 국채 = `bond/{코드}` 7번(목록·polling 없음, 일본 2시간 지연). 네이버가 한국 국채를 밤에도 `OPEN`으로 두어서, 지연 + 2시간보다 오래된 금리 시세는 `CLOSE`로 바꿔요.
- **화면(world.js)**: 지표 탭은 `kind=commodity&with=fx,rates`를 받아 목록을 두 덩어리로 — 제목 줄 "원자재"(에너지·금속·농산물, 등락률순이면 원자재끼리만 순위) · "환율 · 금리"(언제나 묶음별). 환율 머리 "오르면 원화 약세", 달러인덱스·달러/엔 행 보조 글자 "오르면 달러 강세"·"오르면 엔화 약세", 금리 머리 "변화는 bp(0.01%p)". 금리 행 = `3.756%` + 색 칩 `+2.3bp`(변화 칸은 비워요), 색은 그날 변화의 부호(빨강 오름·초록 내림). 요약 줄·많이 오른·내린은 원자재만("원자재 17개 중"). 시트: 단위(원 (1달러당)·원 (100엔당)·포인트·엔 (1달러당)·연 %), 기준(via), 금리는 `+2.3bp (+0.023%p)`, 차트 눈금 %·기간 변화 bp. 옛 Worker(그룹 없음)면 예전 원자재 화면 그대로.
- **티커**(extras): 띠의 원/달러(`m:USDKRW`)를 누르면 `FX_USDKRW` 시트가 열려요(`TK_WORLD`). 티커 고르기의 환율·금리 분류는 아직 그대로.

## 3-29. 공시 배지 — 서버 (§3-23 ①, 사용자 2026-11-14 "다음 로드맵")

**경로** `GET /api/disclosures/today` (모양은 §3-2 표). 화면은 이걸로 타일에 "공시" 표시 + 제목, 최근 N분의 "새 공시"를 그려요. 구현 `worker/src/index.js`의 `getDisclosuresToday`·`dt*`, 점검 `node qa/worker/test_disclosures_today.mjs`(가짜 KV·시계·OpenDART 모양 응답, 네트워크·진짜 키 없이).

**데이터**
- 원천: OpenDART `list.json`(Worker 비밀값 `DART_KEY`), 하루(`bgn_de=end_de`) · 시장별(`corp_cls` `Y` 코스피, `K` 코스닥) · 100건씩. 코넥스(`N`)·기타 법인(`E`)은 부르지 않아요.
- 행은 `stock_code`가 6자이고 유니버스(`web/universe.json` `K`·`Q`·`X`)에 있는 것만. 같은 접수번호는 한 번만(받는 사이 페이지가 밀려도). 시장(`counts`)은 유니버스 기준.
- 제목: 공백 정리, 앞의 `[기재정정]`·`[첨부정정]`·`[발행조건확정]` 같은 꼬리표는 떼어 `n`으로. DART 비고 `rm`의 `철` → "철회", `정`(이 보고서 뒤에 정정본이 나왔다는 뜻) → "정정본 있음". 연·유·코 같은 나머지 비고는 버려요. 정정 공시도 자기 행으로 따로 나와요(접수번호가 달라요). `k`는 `dartKind()`(종목 페이지 공시와 같은 분류). 증분 갱신은 1쪽만 다시 읽어서, 오래된 행의 비고(나중에 붙는 철회·정정본)는 그날 처음 받은 값 그대로일 수 있어요.
- `date`: KST 오늘에 공시가 있으면 오늘. 없으면(새벽·주말·휴일) 오늘을 확인한 뒤 4일 안의 평일을 거꾸로 찾아 공시가 있는 첫날. 지난날은 끝난 날이라 한 번 다 받으면 다시 받지 않고, 비어 있던 평일도 기억해요 → 밤·주말엔 확인마다 "오늘" 두 번(시장별 1쪽)만 물어요. 자정 직후 첫 확인에서 어제를 한 번 마무리해요.
- `asOf` = 마지막으로 성공한 확인 시각(지난날을 보여 줄 때도 오늘 확인한 시각). `stale:true` = 마지막 시도가 실패해서 그 전 스냅숏을 보여 주는 중(요청 한도·키·네트워크·시간 초과·DART 오류·한쪽 시장만 성공·쉬는 중).

**처음 본 시각 `s` · `since`**
- DART는 접수 날짜만 줘요. 판세가 그 공시를 처음 본 확인 시각을 KV `dart:seen:YYYYMMDD` → `{접수번호: 'HH:MM'}`(8일)에 남기고 `s`로 내보내요. 확인 간격만큼 늦어요(평일 07~19시 1~2분, 그 밖 5분 안팎, 스냅숏을 쓰지 않은 colo에서 보면 +2분까지).
- 확인은 누군가 이 경로를 부를 때만 일어나요(cron은 쓰지 않아요). 그래서 **그날 첫 확인**, 또는 **15분 넘게 확인이 끊긴 뒤의 확인**에서 찾은 공시는 그 확인 시각을 받아요 — 실제 접수는 더 이르다는 뜻이에요. `since`(`HH:MM`, `date`가 오늘일 때만) = 끊김 없이 지켜보기 시작한 시각. 화면은 **`s > since`인 공시만 "새 공시"**로 보여 주세요(`s === since`는 지켜보기 시작할 때 이미 있던 것).
- 지난날(`date` < 오늘)은 그날 남긴 시각만 쓰고 새로 만들지 않아요(없으면 `s` 생략, `since` 없음).

**호출 예산** (OpenDART 키당 하루 약 20,000번)
- KV `REPLAY`의 스냅숏 `dart:today` 하나를 모든 colo·isolate가 같이 써요. 나이가 **60초**(평일 07:00~19:00 KST) / **5분**(그 밖, 그리고 평일인데 10시가 지나도록 오늘 공시가 없으면 휴일로 보고) 미만이면 그대로 내주고, 넘으면 다시 받아요. 그 위에 엣지 캐시 30초. 같은 isolate 안의 동시 요청은 한 번만 받아요.
- 다시 받기는 **증분**: 시장마다 1쪽(최신 100건), DART `total_count`가 아는 건수(가진 접수번호 + 방금 받은 것)보다 클 때만 다음 쪽을 필요한 만큼(한 번에 최대 3쪽 병렬, 시장당 30쪽 = 3,000건까지). 모든 쪽을 다 돌아도 모자라는 건수는 기억해서 다시 돌지 않아요.
- 스냅숏을 쓴 colo가 아닌 곳은 **2분 더** 기다려요(KV는 다른 colo에 최대 약 60초 늦게 닿아요) → 평소엔 한 colo만 DART를 불러요. `request.cf.colo`가 없으면 isolate 단위로 같은 규칙.
- 실측(점검 스크립트, KV는 문서대로 colo별 60초 읽기 캐시 + 마지막 쓰기 승리 모형): 상장사 공시 3,040건인 바쁜 평일에 24시간 내내 30초마다 요청 → **1,729번/일**, colo 세 곳이 함께 물어도 **1,729번**. 계산: 07~19시 720번 × 2(시장) + 그 밖 144번 × 2 + 몰릴 때 100건마다 1쪽 + 첫 동기화(≤ 시장당 30쪽). 주말·휴일 ≈ 288번 × 2 = 576번. KV 쓰기 ≈ 1,600번/일.
- 안전장치: 그날 호출이 4,000번을 넘으면 10분 간격, 8,000번이면 그날은 더 부르지 않고 `stale:true`(계수는 스냅숏에 있어서 colo끼리 겹쳐 쓰면 조금 덜 셀 수 있어요). 쪽마다 6초 시간 제한, 같은 요청 안에서 다시 시도하지 않아요.
- 실패하면 `dart:cool`로 모든 colo가 쉬어요: `020`(요청 제한) **10분**, 키 오류(`010`·`011`·`012`·`901`) 30분, 그 밖(네트워크·시간 초과·HTTP·`800`·`900`·JSON) 한 번의 갱신 간격. 스냅숏이 있으면 `stale:true`로 내주고, 없으면 502/503(오류는 엣지 캐시하지 않아요). 오늘 공시가 있던 시장이 갑자기 `013`이면 실패로 보고 이전 행을 지켜요.
- 키는 요청 URL에만 들어가요 — 오류 문구·KV·응답·로그에 남지 않아요. User-Agent는 `Mozilla/5.0 (compatible; panse/1.0; +https://panse.pages.dev)`.

**KV 키** (`REPLAY`, `list` 안 씀): `dart:today`(스냅숏, 8일, 바쁜 날 약 300KB), `dart:seen:YYYYMMDD`(8일, 약 70KB), `dart:cool`(쉬는 동안만). **크기**: 3,000행 응답 약 364KB, gzip 21KB.

**`counts.byKind` · ETag · `?after=`** (오케스트레이터 2026-11-14, 화면 C안용, 예전 응답과 호환)
- `counts.byKind` = `{실적, 주요, 지분, 정기, 기타}` 행 수, `counts.byKindMarket` = `{K:{…}, Q:{…}}` 같은 다섯 키(합 = `K`·`Q`). `?after=`여도 그날 전체 기준이에요.
- **ETag**: `W/"<가장 새 접수번호>.<행 수>.<내용 해시 12자>"` — 해시는 `asOf`를 뺀 응답 전체(행·비고·counts·since·stale)의 SHA-1. 그래서 새 공시가 없는 갱신(asOf만 바뀜)은 같은 태그 → 304, 비고가 바뀌거나(철회 등) `stale`이 바뀌면 새 태그. 비교는 약한 비교, 쉼표 목록·`*`도 받아요. 304에도 `etag`·`cache-control: public, max-age=30`·`x-as-of`가 붙고, 교차 출처에서도 읽히게 `access-control-expose-headers: etag, x-as-of`.
- 엣지 캐시: 그날 전체 응답을 `dis-today` 키로 30초, ETag·`x-as-of`를 같이 저장해요. 요청마다 그 캐시에서 304를 판단하고 `after`를 잘라요(캐시 적중이면 KV·DART를 건드리지 않아요). ETag 전 Worker가 캐시한 항목(태그 없음)은 304 없이 그대로 200.
- 화면이 쓰는 법: ⓐ 가장 쉬운 길 — 같은 주소(`after` 없이)를 기본 `fetch`로 60초마다. 브라우저가 30초 뒤부터 알아서 `If-None-Match`로 다시 확인하고, 304면 저장해 둔 본문을 그대로 줘요(본문 `asOf`는 옛값일 수 있으니 시각은 `res.headers.get('x-as-of')`). ⓑ 직접 — 마지막 `ETag`를 `If-None-Match`로 보내고 `after=<가진 것 중 가장 새 r>`로 받으면, 304 = 변화 없음, 200 + `after` = 새 행만(앞에 붙이기), 200인데 `after` 없음 = 날짜가 바뀜(통째로 바꾸기). **새 행이 없는데 태그만 바뀌면**(빈 `rows`) 예전 행의 비고·`stale`이 바뀐 것 → 가끔 `after` 없이 통째로 다시 받으세요.
- `after`는 접수번호 앞 8자리(접수일)로 날짜를 비교해요(접수번호 = 접수일 8자리 + 일련번호 6자리).

## 3-33. 증시 캘린더 결정 (시안 `docs/standards/calendar.md` · `prototypes/calendar/`, 사용자 2026-11-15 17:52 "1 추천 2 추천 3 추천 4 추천 5 숨기기 이유? 6 신청할게 7 추천")
- ① 화면 **A — 시장 탭 끝 "일정" 탭**(휴대폰: 한 주 띠 + 날짜별 목록, PC: 달력 + 7일 목록) ② 국가데이터처 발표(소비자물가 · 고용 · 산업활동)도 넣기 ③ 2027 금통위는 보도 기준 "예정"으로 먼저 넣기 ④ 주총 · IR · 실적 예고(원문 읽기)는 2단계 ⑤ 위클리 옵션 만기(매주 월 · 목)는 **기본 숨김**, 필터로 켤 수 있게(이유 설명 뒤 사용자 17:54 "위클리는 기본 숨기기로 하자") ⑥ 금융위 **주식권리일정정보** `GetStocRighScheService_V2` · `getRighExerReasSche_V2`(권리행사사유별 권리행사 · 명부폐쇄 일정, 하루 한 번 · 다음 영업일 13시 뒤) — 사용자 17:54 "신청했어"(같은 `DATA_GO_KR_KEY`), 실제 호출로 승인을 확인할 때까지 기능 플래그 뒤에 ⑦ 발표가 끝난 지표는 실제 값도(색 없이).
- 원천: 한국은행 통계공표일정 웹페이지(하루 한 번, robots 허용) · FRED `release/dates`(`include_release_dates_with_no_data=true`, 시각 표는 따로, FRED® 고지 문구) · 금통위 · FOMC · KRX 휴장일 · 동시만기는 직접 입력 · OpenDART(무상 · 유상증자) · 금융위 주식발행정보(보호예수 반환 — 앞으로의 날짜가 나오는지 먼저 실측) · 주식배당정보(배당).
- **구현 (`feat/calendar`, 2026-11-15)** — 자세한 건 `docs/standards/calendar.md` §9. Worker `worker/src/calendar.js`(+ `index.js` 두 줄) `/api/calendar`(§3-2 표). 화면 `src/calendar/calendar.js · calendar.css`(빌드: 마지막 모듈), 템플릿은 탭 `일정`(`data-mkt="CAL"`, `#cal`)을 해외 · 지표처럼(`isWorld()`) 다뤄 `<div id="calendar">`에 `window.KHCal.show()/hide()`, 출처 줄 `#foot-cal`. 직접 입력 표(금통위 2026 · 2027 예정 · FOMC · 휴장)는 `web/calendar.json`이 아니라 `calendar.js` 상수 — 고치면 Worker 배포. 위클리 옵션 만기는 `weekly:true`로 오고 화면 칩 `위클리 만기`로만 보여요(기본 끔, `khm.cal`). 발표값은 글자만(색 없음). **금융위(배당 · 보호예수 % · 주식권리일정 `getRighExerReasSche_V2`)는 공용 도우미 `datago.js`의 `dgSnapshot`으로** API마다 사본 하나(`DG_APIS.rights` 하루 상한 200 추가), 권리일정은 `datago_crno.js` 표를 거꾸로 써 종목코드로. 승인 전 API(403)는 그 부분만 빠져요(`sources.fsc.parts.rights:'forbidden'`, stale 아님). 끄기 Worker 변수 `CAL_FSC=off`. 점검 `node qa/worker/test_calendar.mjs` · `python3 qa/calendar/test_calendar.py`.
- **기업 일정 줄이기 · 미국/한국 나누기 · 칩 움직임** (`ux/cal-split`, 사용자 2026-11-15 19:23~19:27 — 자세한 건 `docs/standards/calendar.md` §9-6): ① 기업 일정은 **중요한 것만 기본**(제안에 "그래 그게 맞고"): 배당 기준일 · 배당락 · 지급일, 유 · 무상증자 권리락(DART 신주배정기준일은 `sub`에 "권리락 M/D" = 기준일 전 영업일), 보호예수 해제 상장주식의 **1 % 이상**(비율을 모르면 보여요), 주총(총회개최일)은 **관심종목 · 지도 종목**(`KH.watch.has` · `KH.mapCodes()` · `KH.stock()`)만. 분류는 **Worker**가 `cls` · `minor`로 붙이고(옛 화면은 무시하고 전부 보여요) 화면이 거르기 — 실측 2026-11-16~12-20 기업 251건 중 197건이 세부(주식권리일정 통지 · 접수 시한 · 명부폐쇄 · 교부 · 상장일 · 매수청구 · 상호변경 · 액면병합 · 감자, DART 신주 상장 · 유상 청약, 보호예수 1 % 미만). 세부는 언제나 ★(★★ 이상만과 맞음, 관심 +1 없음). 여는 길 두 가지: 칩 **"기업 세부 일정"**(기본 끔, `khm.cal.detail`) · 날마다 한국 묶음 끝의 **"기업 세부 일정 N개 더 보기"**(`aria-expanded`, 이번 방문만). 같은 DART 유상증자 ±3일 안의 권리일정 줄은 빼요(무상과 같은 규칙). ② **"미국 일정 한국일정 따로 분리하고 미국일정을 먼저 나오게 해줘"**: 날마다 **미국 → 한국** 묶음(작은 이름표, 묶음 안은 시각 순 · 종일 먼저), 미국 = `k:'us'` · FOMC(`rg:'us'`), 그 밖 모두 한국. 칩 순서 `미국 지표 · 한국 지표 · 금리 · 시장 · 기업`, PC 달력 칸은 중요한 셋을 고른 뒤 미국 줄 먼저. ③ 상세 시트 "null"(9530549)에 더해 native append · replaceChildren에 null이 들어갈 곳이 없게(모든 조각 `h()`), 점검에 "null · undefined 글자 0". ④ **"여기 애니메이션 적용이 안되어있네"**: 칩을 다시 그리지 않고 **그 자리에서** 켜고 꺼요 — 체크 자리를 늘 비워 두어 칩 폭이 그대로(옆 칩이 안 밀림), 켤 때 채움 · 체크 `fade` + 글자 · 체크 자리 `lead`, 끌 때 `close`, 누름 1px(내려감 0 · 올라옴 `--c-fast`), 표면은 `--chip-bg` · `--chip-on` · `--chip-ring`(controls.md §5-7). 주 띠 표시는 `KH.spring.edges`(앞 `lead` · 뒤 `trail`, 키 누르고 있기는 바로), 날 바꿈 목록은 기다림 없이 `fade`로, "다음 7일 보기"는 주 띠를 다시 보이게 + 포커스 유지, 시트 닫힘 길이는 `--sp-close-dur`, 포커스 고리는 전역 outline. 줄이기면 모두 바로. ⑤ (사용자 19:49~19:51) 중요한 줄이 없는 날은 **"숨긴 일정 18개 (위클리 만기 · 기업 세부 일정)"** — 숨긴 칩 이름을 괄호에 — + **"이 날 숨긴 일정 보기"**(칩은 그대로, 그날만 모두, "이 날 다시 숨기기"로 되돌림). ⑥ (사용자 19:49 떠 있는 창 움직임) 상세 시트: 열림 `open` · 닫힘 `close` · 배경 페이드, **진짜 나감**(`close()`는 바로 — 페이지 · 포커스 곧바로, CSS `allow-discrete` `display` · `overlay`로 나가는 동안 그려 둠), 나가는 중 다시 열면 그 자리에서 되돌아옴, 휴대폰은 손잡이 · 제목 줄을 **끌어서 닫기**(design.md §8: 6px · 축 잠금 · 35 % 또는 0.11px/ms · 고무줄 .55 · `settle`이 손가락 속도를 이어받음), 포커스는 연 줄로. 다른 떠 있는 창은 `ux/float-motion` 몫.

## 3-34. 오늘의 시장 요약 카드 결정 (시안 `docs/standards/market-summary.md`, 사용자 2026-11-15 18:00 "1. b자리에 원래 a모양이었다가 상세 누르면 b모양 자세히 나오게 2~5. 추천대로")
- ① **자리는 B**(휴대폰: 지도 바로 아래 · 뉴스 카드 앞, PC: 옆 칸 맨 위) — 지도는 움직이지 않아요. **접힌 모양은 A의 짧은 띠**(한 줄 요약 + 오른/내린 막대·수 + 강한/약한 업종), **"자세히"를 누르면 B의 표 + 펼친 내용**이 그 자리에서 자라요(design.md §7 · `open`/`close` 스프링, 글자 바꿈 §6-4). ② "글로 복사"(카톡 등에 붙여 넣는 글)를 펼친 끝에도 ③ 외국인 · 기관 수급 줄은 장중에도 전 거래일 값 + 날짜 ④ 20일 평균이 쌓일 때까지 "거래 급증" 대신 "거래대금 상위" ⑤ 상 · 하한가 수는 어림(±29.5%) 대신 실제 표시로 — 빌드가 `web/close.json` 행에 `lim`을 넣어요(§3-3 계약 갱신).
- **구현 (`feat/market-summary`, 규칙 문서 `docs/standards/market-summary.md` — 결정 · 구현)**: 모듈 `src/summary/summary.js · summary.css`(빌드: `live` 다음, 맨 끝), 모두에게 켜짐(스위치 없음). 자리는 JS가 넣어요 — 휴대폰 `main.layout`의 `#news` 앞, 태블릿 `.side` 첫 칸(`grid-column: 1 / -1`), PC `.side` 첫 칸. **늘 접힘으로 시작**(기억하지 않아요 — 펼치면 휴대폰 약 1,400px라 다음에 열 때 뉴스 · 등락 분포가 멀리 밀려 있지 않게). **움직임은 design-references-full §7**(오케스트레이터 2026-11-15): P8 ⓐ 카드 바탕 판(`.sm-skin`)만 `open` · `close` 스프링으로 자라고 줄며(길이는 크기 차이에 비례해 0.75~1.35배), 아래 내용은 **한 번에** 새 자리로 — 펼칠 땐 누르는 순간, 접을 땐 판이 다 줄어든 뒤(높이를 프레임마다 바꾸면 news.js `refit`이 프레임마다 뉴스를 다시 그려 PC 프레임이 0.4~2초였어요), 표 글자는 판 25% 뒤 · P3 순차는 세션 첫 펼침만(≤ 300ms, 40 → 30 → 20ms), 접을 땐 다 함께 · P9 띠 숫자는 오르면 아래에서 · 내리면 위에서 · P10 자리별 굴림 없음 · P11 글로 복사는 크기 그대로 아이콘 교차(복사 → ✓, `fade`) + 글자 바꿈, `isTrusted`만. 끝 줄 `[글로 복사] [접기]`. 데이터는 이미 있는 것만(`KH.index · stocks · quote · loadData('close' · 'names' · 'flows' · 'themes') · disclosures`, `/api/breadth · themes · market · world · news`), 카드가 화면 근처에 오면 받아요 — **`/api/news`만은 ⌄ 키에 손이 갈 때(올림 · 포커스 · 누름)부터**(뉴스 카드와 겹친 요청 0), 처음 누를 때 아직 오는 중이면 꺾쇠만 먼저 돌고 판은 최대 450ms 기다렸다 한 번에 자라요. `window.KHSummary = {phase, model, plain, isOpen, moving, open, close, refresh}`, 점검용 주소 `?summary_phase=pre|open|after|closed`(글자만).
  - 템플릿 두 군데: `norm()` 행에 **`limf`**(원천 상 · 하한가 표시만 — `lim`엔 ±29.5% 어림이 섞여 있어요), close.json 읽기에 `CLOSE.lim`(등락 분포 카드도 네 번째 칸을 써요). 빌드: `web/close.json` 행 네 번째 `lim`(§3-3). 점검 `qa/summary/test_summary.py`(포트 8981 · 8982, 지도 상자 = `main` 빌드 비교 포함).
  - 요청: 템플릿 `--live`를 앰버 밖 색으로(design.md §2 — 장중 점이 아직 앰버) · 요약이 따로 받는 `/api/breadth` · `/api/news` · `/api/market`을 나눠 쓸 연결점(`KH.breadth()` · `KHNews.items()` · `KH.marketItems()`).

## 3-35. 떠 있는 창 움직임 · 일정 표시 설정 · 탭 순서 · 휴대폰 머리글 (사용자 2026-11-15 19:49~19:53, `ux/float-motion`)

"표시 설정처럼 이런 플로팅되는 창들은 모션 없어?" · "일정에 표시설정은 왜이래?" · "탭 순서 관심과 일정 바꿔주고" · "모바일에서는 시계가 위 테두리랑 너무 붙어보여 … 위에 간격을 조금 더"
- **떠 있는 창 = design.md §5의 네 가지, 움직임 하나씩**(§6-2 `open` · `close` · `fade` · `follow` · `settle`, 토큰은 템플릿 `:root`의 `--kp-open/close` · `--kp-bleed` · `--sh-open/close` · `--fl-open/close` · `--sc-open/close` · `--sheet-skirt`(테마마다)). **나감 기술은 일정 상세 시트와 같아요**: 상태는 바로 닫힘(포커스 · Esc · 바깥 누름이 곧바로), CSS가 `display`(대화상자는 `overlay`도)를 `transition-behavior: allow-discrete`로 나가는 동안 그려 두고, 나가는 상자는 `pointer-events:none`. 나가는 중 다시 열면 그 자리에서 돌아와요(전환이라 처음부터 다시 시작하지 않음). 줄이기는 모든 `--sp-*-dur` 0 → 바로.
  - **팝오버**(화면 · 색 기준 · 순매수 기간 · 태블릿 표시 설정 · 관심 그룹 · 검색 제안 · 세계 시각): **트리거에서 자라요** — 클립이 트리거 모양(폭 · 높이 · 모서리)으로 시작해 상자 전체(그림자까지 `--kp-bleed`)로 `open`, 채움은 `fade`, 닫힐 땐 그 모양으로 `close`. 글자는 크기가 바뀌지 않아요(§6-5). 분 고르기(`src/stock`)는 이미 기준대로라 그대로.
  - **시트**(휴대폰: 표시 설정 · 빠른 보기 · 가격 기준 · 🔍 검색 · 관심 그룹 · 세계 시각 · 티커 항목(≤ 600px) · 해외 상세): 아래 가장자리에서 `open`으로 올라오고 `close`로 내려가요, 배경 막(scrim)은 `fade` / `close`. 시트 아래 가장자리 밑 64px "치마"(`--sheet-skirt` 그림자)가 1.2 % 넘침 · 고무줄 때 틈을 가려요. **끌어서 닫기**(design.md §8: 손잡이 · 머리 줄만 `touch-action:none`, 6px · 축 잠금 · 마지막 100ms 속도 · 높이 35 % 또는 0.11px/ms · 위로 고무줄 .55 · `settle`이 손가락 속도를 이어받음 · 사람 입력만 · 끝난 끌기의 클릭은 먹음).
  - **떠 있는 시트 · 대화상자**(PC 빠른 보기 · 해외 상세 · 리플레이 패널 · extras 대화상자): 12px 아래에서 `open`으로 올라오며 `fade`, `close`로 나가요. 대화상자는 `close()` 뒤에도 나감이 끝날 때까지 맨 위 층에 그려 두고(extras `makeDialog`가 그 뒤에 지워요), 배경도 같이 옅어져요.
  - **툴팁**(지도 · 장 진행 말풍선): 자라지 않고 `fade`로만, 처음엔 그 자리에(이동 없이), 보이는 동안은 `follow`로 따라가고(KH.spring, 지도 툴팁), 떠나고 130ms 뒤 숨어요.
- **공용 연결점** (`KH.ui`, 템플릿): `KH.ui.popIn(el, opener)` — 팝오버를 보이고 자리를 잡은 바로 뒤에 불러요(트리거 모양 `--kp-t/r/b/l/rr`을 상자에 적고, 나가는 중이 아니면 그 모양에서 시작). `KH.ui.sheetDrag(el, {zone, on, close, scrim?, prop?})` — 휴대폰 시트 끌어서 닫기(`on()` = 지금 시트이고 열려 있음, `close()` = 모듈의 닫기 · 포커스 · 정리, `scrim()` = 같이 옅어질 막, `prop` = 시트의 닫힌 자세가 쓰는 속성 `'translate'`(기본) · `'transform'`). 끄는 동안 손가락이 인라인 `translate`/`transform`(+ `.kdrag` = 전환 없음)과 막의 opacity를 가져요. 일정 상세 시트(`src/calendar`)는 아직 자기 끌기 코드 — 같은 숫자 · 같은 `settle`.
- **일정 탭 표시 설정**: 템플릿 규칙 `.is-cal .ctls .ctl:not(.more)`(후손 선택자)가 화면 · 아래 막대의 줄까지 숨겨 빈 "화면" 제목만 남았던 것 → `.is-cal .ctls > .ctl:not(.more)`(지도 줄만: 크기 · 색 기준 · 종목 수 · 색 범위 · 색상). 해외 · 지표 · 일정에선 공시 줄(공시 보기 · 지도에 표시할 종류)도 숨겨요(지도 귀퉁이 · 오늘 공시 목록만 바꾸는 설정). 줄이 모두 숨은 묶음은 제목 · 도움말째 숨겨요(`syncSetSections`, `.set-empty`) — 빈 제목 없음.
- **탭 순서**: 코스피 · 코스닥 · 전체 · 테마 · 해외 · 지표 · **일정 · ★관심**(해시 · 저장 키 그대로).
- **고른 탭 알약**(휴대폰): 한 줄 탭(테마 · 해외 · 지표 · 일정)도 두 줄 탭과 같은 캡슐 — 탭 폭 52px 이상(40 × 40 원이었어요), 표시는 줄 위아래에서 2px 안(`--ind-iy`, 높이 36 · 누르는 곳 40 그대로) → 머리글 아래 가장자리와 6px.
- **휴대폰 머리글**: 위 여백 4 → 8px(`--space-4`, 시계 판이 글라스 판 위 가장자리에서 1.5 → 5.5px), 장 진행 막대 아래 틈 7 → 10px · 막대 끝 알약(휴장 · 정규장 %) 18px(PC와 같음) → 알약이 탭 줄과 3px 떨어져요. **390 × 844 지도 위치 240 → 247(+7)**, PC(1440 × 900 · 1280)는 그대로 207.
- 점검 `python3 qa/float/test_float.py`(목 `qa/float/mock_float.py`, 포트 `FLOAT_QA_PORT` 8970~8979, 프레임 띠 · 스크린샷 `qa/shots/float_motion/`).
- **고침 2026-11-15 21:30 "ui오류"** (`fix/popover`): 색 기준 · 순매수 기간 메뉴(`.ctl.dd > .seg`)가 트레이 모서리 `--r-tray`(글라스 999px)를 써서 알약처럼 둥글었고, 그래서 "오늘" 표시가 판 밖으로 튀어나와 보였어요(표시 자리는 맞았음 — 판 모양이 문제, 움직임 전부터 있던 것). 팝오버 모서리 `calc(--tip-r + 2px)`(화면 · 관심 그룹 팝오버와 같음)로. 쉬는 클립 `--kp-bleed`를 그림자 끝까지 `inset(-64px -80px -100px)`로 넓혔어요(48 · 72px은 0 18px 50px 그림자 꼬리를 최대 12단계 잘랐어요). 점검 `shapes`: 7개 팝오버 · 4테마 · 1440 · 1280 · 태블릿 · 줄이기 — 모서리 = 토큰, 클립을 빼도 픽셀 변화 ≤ 3, 고른 줄 표시가 줄에 ±1px · 판의 둥근 모양 안.
- **페이지는 옆으로 밀리지 않아요** (사용자 2026-11-15 21:34 "이렇게 튀어나가는거 없게해줘" — 일정 탭의 긴 발표값이 휴대폰 화면 전체를 왼쪽으로 밀었던 것, 원인은 main 2029920에서 고침): 안전망 `html,body{overflow-x:clip}` — `hidden`과 달리 스크롤 상자를 만들지 않아 붙는 머리글 · 고정 시트 · 아래 막대 · 탭 줄 자체 넘김은 그대로예요. 그래서 `documentElement.scrollWidth`로는 넘침이 안 보여요 → `qa/float`의 `overflow_net`이 화면 옆으로 그려진 요소를 직접 찾아요(자기 잘림 · 넘김 상자 안은 빼고; 360 · 390 · 768 · 1280 × 여섯 탭).

## 3-32. 공공데이터포털 API (사용자 2026-11-15 17:16 신청 목록 15개 → 17:21 "추천대로하고 추가적으로 7번만 다음에 고려해보자")
- 키: 공공데이터포털 키 하나로 승인된 API를 모두 써요 — **Worker 비밀값 `DATA_GO_KR_KEY`**(§3-27 끝). 금융위원회 API는 **실시간이 아니고 하루 한 번**, 대부분 **다음 영업일 13시 이후**(금요일 자료는 월요일), 기업재무 · 기업기본 · 금투협 통계는 당일 13시 이후 — 하루 한 번 받아 KV에 두고 써요.
- **넣기**: ① 금융위원회_금융투자협회종합통계정보 `GetKofiaStatisticsInfoService`(고객예탁금 · 신용융자 · 미수금 · 반대매매 비중 → 지표 탭 "증시 자금" · 시장 요약 카드) ② 금융위원회_주식대차정보 `GetStocLendBorrInfoService_V2`(종목별 대차잔고 · 대차 상위 → 종목 페이지) ③ 금융위원회_주식발행정보 `GetStocIssuInfoService_V3`(의무보호예수 반환 → 증시 캘린더) ④ 금융위원회_주식배당정보 `GetStocDiviInfoService_V2`(배당 기준일 · 지급일 · 금액 → 캘린더 · 종목 페이지 배당) ⑤ 금융위원회_기업기본정보 `GetCorpBasicInfoService_V2`(종업원 수 · 계열회사 · 종속기업 → 종목 페이지) ⑥ 금융위원회_KRX상장종목정보 `GetKrxListedInfoService_V2`(법인등록번호 ↔ 종목코드 연결표).
- **나중에 고려**: 관세청 수출입통계(`nitemtrade`, 월 1회, 품목 · 나라별 — 캘린더 · 지표 다음 단계).
- **넣지 않음**(겹치거나 쓸 곳 적음): 외화증권 예탁결제 · 일반상품시세 · 주식시세 · 지수시세 · 파생상품시세 · 기업재무 · 금융위 공시정보(OpenDART와 같은 것을 하루 늦게) · 예탁결제원 API(한글 파일은 개정 이력).
- 원문 명세(활용가이드 docx · hwp)는 사용자가 올린 파일 — 저장소에 올리지 않아요. 구현 메모는 `docs/standards/datago.md`.
- **구현 (`feat/datago`, 2026-11-15)**: 공용 도우미 `worker/src/datago.js`(키는 한 번만 인코딩 — Encoding · Decoding 철자 모두, `resultType=json`, 쪽 넘김 `numOfRows` ≤ 10,000, JSON · 옛 XML(`OpenAPI_ServiceResponse`) · 게이트웨이 글자 오류 봉투, 8초, KV 마지막 성공본, API별 하루 계수 `datago:calls:*`와 상한 — 비밀값 `DATAGO_CAP`로 낮추기만, `0` = 끄기, 쉬기 `datago:cool:*`, 실패 기록 `datago:err:*`). ⑥ 법인등록번호 표 `worker/src/datago_crno.js` — **`crnoOf(env, code, ctx)`** · `crnoInfo` · `crnoTable`(대차 · 기업기본 · 배당 · 보호예수가 쓸 것, KV `datago:crno`, 평일 13:10 뒤 하루 한 번, 빈 날은 거꾸로, 우선주는 보통주 crno + `common`; KRX 재배포 금지라 공개 경로 없음). ① 증시 자금 `/api/funds`(§3-2) → 지표 탭 **"증시 자금" 묶음**(환율 · 금리 다음, 같은 덩어리 "환율 · 금리 · 증시 자금"): 투자자예탁금 · 신용융자(전체 · 코스피 · 코스닥) · 위탁매매 미수금 · 반대매매(금액 · 비중), 값 조원/억원 · 앞 영업일 대비, 색은 오르내림만("색은 늘고 준 것만"), 출처 줄 "금융투자협회 · 하루 한 번(전 영업일 기준)", 시트 + 3개월 · 1년 차트. 하루 호출 ≈ 15번(최악 ≈ 50). 점검 `qa/datago/*.mjs` · `qa/world/test_funds.py`.
- **구현 ②⑤④ 종목 페이지 (`feat/stock-datago`, 2026-11-15 — 로드맵 5번, 사용자 "추천대로하고 …" · "끝나면 위에서 계획했던 순서대로 진행해줘")**: Worker `worker/src/stock_datago.js`(`index.js`는 import 한 줄 + 경로 두 줄) — `/api/stock/{code}/lending` · `corp` · `dividend`(§3 표). 원천과 요청 변수: 대차 = `getStLendAndBorrItemRank_V2`(`basDt` 하루치 전 종목 · `numOfRows` 4,000 — 종목별 오퍼레이션은 `isinCdNm`(이름?)으로만 거르고 금액이 없어서 안 써요) → **모든 종목이 함께 쓰는 표** KV `sdg:lend:d:<YYYYMMDD>` · `sdg:lend:idx`, 처음 60영업일은 갱신마다 몇 날씩(2분 간격) 채워요; 기업기본 = `getCorpOutline_V2` · `getAffiliate_V2` · `getConsSubsComp_V2`(모두 `crno`, `basDt` 없이, 목록은 1쪽 + 마지막 쪽 — 정렬 방향과 상관없이 가장 최근 기준일 묶음); 배당 = `getDiviInfo_V2`(`crno`, 1쪽 1,000행 + 넘치면 마지막 쪽). 법인등록번호는 `crnoOf`(우선주 → 보통주). KV `sdg:corp:<보통주 코드>` · `sdg:divi:<…>` · `sdg:lend:<code>`. 하루 상한(`DG_APIS`): **lend 200 · corp 600**(divi 1,000은 캘린더와 같이). `/api/datago/status`에 `lend` · `corp` · `divi`와 대차 표(`snapshots.lend`). 화면(`src/stock`): 종목 정보 탭 — 배당 칸 아래 **배당 내역** 표(기준일 · 지급일 · 1주당, 8건, "배당 기준일은 금융위원회 자료 기준이에요"), 네이버 묶음과 그 출처 줄 뒤 **대차잔고**(마지막 잔고 + 전 영업일 대비 — 가격이 아니라 빨강 · 초록 없이 중립색, 잔고 금액 · 그날 빌려줌 · 갚음, 60영업일 선 = 계열색 `--s1`) · **기업 정보**(대표자 · 설립일 · 상장일 · 종업원 수 · 결산월 · 업종 · 주요 사업 · 주소 · 홈페이지 + 계열회사 · 종속기업 8개, 넘치면 "N개 모두 보기" — 목록 판만 `open`으로 자라고 아래 내용은 한 번에, 접을 땐 이름이 먼저 나가고 판이 `close`로 준 뒤, design.md §7). 블록마다 기준일 + "금융위원회 · 공공데이터포털, 하루 한 번", 불러오는 중 · 빈 자료 · 503 · 실패(다시 시도) · 지난 자료 문구가 따로, 404(옛 Worker · ETF)는 블록을 숨겨요. 블록이 화면 근처(아래 300px, PC는 옆 카드 스크롤 안)에 오면 그때 받고 종목마다 30분 기억. 출처 줄에 "대차잔고 · 배당 내역 · 기업 정보: 금융위원회(공공데이터포털), 하루 한 번." — "투자 판단의 근거로 쓰지 마세요."는 그대로 맨 아래. 점검 `node qa/worker/test_stock_datago.mjs` · `python3 qa/stock/test_stock_datago.py`(목 `qa/stock/mock_api.py`의 `/__config?sdg=ok|empty|fail|wait|stale|gone|nf&sdgkind=&sdgdelay=`).

## 3-31. 디자인 기준 (사용자 2026-11-15 16:25 "디자인 기준을 먼저 잡고 가자" → 17:07 "1~9 추천대로 10번은 화려하게가 기본 · 스프링 모션 시안은 제안대로")
- **규칙 문서 `docs/standards/design.md`(승인)** — `controls.md` · `themes.md` · `dock.md` · `docs/motion-brief.md`보다 위. 근거 `docs/research/design-references.md` · `docs/research/ui-audit.md`, 움직임 시안 `drafts/springs.html`(claude.ai 아티팩트로도 올림).
- 토큰(`src/template.html :root`): 글자 `--fs-xs…num` · 행간 `--lh-*` · 간격 `--space-1…8` · 모서리 `--r-mark/badge/row/card/float`(+ 기존 `--r-key/in/pill`) · 높이 `--h-chip/key/row`(760px 아래 휴대폰 값) · 채움 `--fill-1…3` · 상태 `--live` · `--fail-dot`(지금은 앰버 — 모듈을 옮길 때 바꿔요) · 스프링 `--sp-<이름>`(`linear()`) · `--sp-<이름>-dur` · `--sp-<이름>-kc`(`"k c"`, JS 엔진용). 스프링 표는 `scripts/design_tokens.mjs` 한 곳 — 바꾸면 `node scripts/design_tokens.mjs`로 다시 만들고 `--check`로 확인.
- 적용 순서(design.md §11): 기반 → 새로 만드는 것(공시 토글 · 분봉 고르기 · 이동평균 범례 토글 · 시장 요약 카드 · 증시 캘린더 · KDI · 관보) → 기존 화면(템플릿 → extras → 종목 페이지 → 해외 · 지표 → 뉴스 · 공시 · 아래 막대).
- **extras 옮김** (`ux/std-extras`, 2026-11-15 — 자세한 건 design.md §11 진행): 토큰 · 빛과 그라데이션 없음(15:20은 `--live` 테두리 + `--fill-2` 판 한 번) · 상태색 `--live`/`--fail-dot` · §6 숫자 드럼(화려하게)과 글자 바꿈(기본) · `KH.spring` 티커 튕김 · 아이콘 1.75px. 클래스 `.xr`/`.xr-c`(드럼) · `.xsw`(글자 바꿈) · `.rp-rail`(리플레이 레일 상자). 점검 `python3 qa/extras/audit_css.py` · `python3 qa/extras/test_std.py`(포트 `EXTRAS_STD_PORT` 9016), 전후 스크린샷 `qa/extras/shots_std.py`.

## 3-30. 공시 배지 — 화면 (§3-23b ①, 사용자 2026-11-14 01:44~01:46 "C안으로 할게" · "나머지는 추천대로")

규칙 문서 `docs/standards/disclosure.md`(C안), 구현 `feat/disclosure-ui`. 서버는 §3-29 그대로 쓰고 Worker는 고치지 않았어요.
- **타일**: 오늘 공시가 있는 종목은 오른쪽 아래 **접힌 귀퉁이**(중립색 `--dm-flap`·`--dm-crease`·`--dm-cut`=지도 바닥, 빨강·초록·앰버 아님). 짧은 변 8px 미만 타일은 없음, 크기는 짧은 변 비례(보통 4~10px, 30분 안 새 공시 5~14px — 짧은 변 10px 이상이면 7px부터). 기본 표시 종류 **실적 · 주요**(설정에서 정기·지분·기타 추가, 끄기). 화려하게면 새 귀퉁이가 한 번 접히며 나타나요(공시마다 한 번). 타일 aria-label 끝에 ", 오늘 공시 N건[, 새 공시 있음]".
- **새 공시 = 점**(사용자 01:46 "'새'로 표기보다는 시간 앞 초록색 동그라미라던지"): 글자 "새" 대신 **시각 앞 작은 채운 점**(7px, `aria-label`/sr "새 공시"). 색은 테마마다 토큰 하나 **`--new-dot`**(읽지 않음 파랑 — 기본 `#4da3ff` · 신문 `#1d5fc4` · 글라스 어둡게 `#5aaeff` · 글라스 밝게 `#1f66d1`, 모두 바탕 대비 3:1 이상). 초록으로 바꾸려면 그 한 줄만 바꾸면 돼요(초록은 하락색과 겹쳐서 파랑으로 둠 — HTS 팔레트에선 파랑이 하락색이라 그때는 점 모양 + 글자로만 구분돼요). 새 = `date`가 오늘 · `since`가 있고 `s > since` · `0 ≤ 지금 − s ≤ 30분`(지금 = `KH.now()`, 오늘 다시 보기 중이면 그 시각).
- **찾는 길**: 뉴스 카드 **오늘 공시** 탭의 **지도 스위치**("지도에서 공시 종목만 밝게 · N종목", 켜면 공시 없는 종목이 흐려짐 `.mdim` — 검색·등락 분포 강조와 AND, 기억하지 않음; 2026-11-15까지는 지도 머리줄 `#stage-tools`의 공시 칩 "공시 N" — 아래 **지도 스위치**) · 범례 "공시 N종목"(+ "큰 귀퉁이 = 30분 안") · 뉴스 카드의 **오늘 공시** 탭(시장 뉴스 옆; 종류 탭 `실적·주요 · 정기 · 지분 · 기타 · 전체`, `지도 종목만` 기본 켬, 종목 칩 → 빠른 보기, 줄에 올리거나 포커스하면 그 타일 강조, 제목 → DART 새 탭, 카드 높이만큼 + 더보기 30줄). 휴장일·주말·새벽엔 탭 이름이 "11월 13일 (금) 공시".
- **툴팁 · 빠른 보기**: 머리 아래 "오늘 공시 N건" + 표시 종류 3건까지(같은 제목은 "· 4건"), 표시하지 않는 종류는 "그 밖에 …" 한 줄. 빠른 보기 줄은 DART 링크(44px, 휴대폰 54px) + **공시 모두 보기 (N)** → 종목 페이지 뉴스·공시 › 공시.
- **받기**: `/api/disclosures/today`를 평일 07~19시 60초, 그 밖 5분마다(숨은 탭·해외 탭·설정 꺼짐이면 멈춤), 마지막 `ETag`를 `If-None-Match`로 직접 보내고(`cache:'no-store'` — 브라우저 자동 재검증은 믿지 않아요) 304면 `x-as-of`로 시각만. `after=`는 쓰지 않아요. 실패 1→2→4→5분, 5분 넘게 못 받으면 "HH:MM 기준" 앰버 + 다시 시도. 404(옛 Worker)면 공시 UI 전부 숨김. 다시 보기: 같은 날이면 `s ≤ 프레임 시각`만, 다른 날이면 귀퉁이·지도 스위치를 숨기고 범례에 안내. 스냅샷은 탭에 "공시는 실시간 버전에서 볼 수 있어요" + 링크.
- **저장** `khm.set.disc`(공시 보기, 기본 켬) · `khm.set.discKinds`(`'실적,주요'`처럼 쉼표) · `khm.feedTab`(`news`|`disc`, 마지막 탭).
- **지도 스위치** (사용자 2026-11-14 08:10 "사진의 공시 버튼 차라리 아래에 뉴스 공시칸으로 옮기든 하는게 나을거같아" → 2026-11-15 "진행", `ux/disc-toggle`): 지도 머리줄의 공시 칩을 **없애고**(`#stage-tools`는 빈 채 — 자리 없음, 휴대폰 머리줄 한 줄 44px · 지도 위치 240 그대로, PC 36px, 지수 선은 `지도 · 표` 앞에서 끝나요) 같은 일을 **오늘 공시 탭 맨 위의 스위치**로 옮겼어요. 디자인 기준(§3-31, design.md)으로 처음 만든 컨트롤이에요.
  - 자리: 넓은 카드(820px 넘음 — 1280 · 1440 · 1920 PC)는 `공시 종류 탭 · 지도 종목만` 줄의 오른쪽 끝, 좁은 카드(820px 이하 — 휴대폰 · 768 · 1024 PC, 컨테이너 쿼리)는 **탭 맨 위 한 줄**(글자 왼쪽 · 트랙 오른쪽 끝). 휴대폰도 글자를 줄이지 않아요.
  - 모양(design.md §7): **`role="switch"` + `aria-checked`**, "[귀퉁이 견본] 지도에서 공시 종목만 밝게 · N종목 [트랙]". 파인 트랙(`--trk` + `--tray-sh`, 44 × 26) + 솟은 손잡이(`--knob` + `--knob-sh`, 22), 켜짐 채움 `--sw-on`(앰버는 켜짐 · 포커스에만). 손잡이 두 가장자리가 앞 `--sp-follow` · 뒤 `--sp-settle`(+ `-dur`)로 따로 움직여 가는 동안 늘었다 돌아와요 — 두 스프링만으로는 18px 이동에 6px쯤 벌어져서, 보이는 손잡이(`::before`)는 앞 가장자리에 붙인 채 **최대 3px**만 늘어요. 채움은 `--sp-fade`. 끌기는 `KH.ui.sw`(4px부터, 절반 넘으면 그쪽). 수 "· N종목"이 바뀌면 §6-4 글자 바꿈(나감 100ms 흐림 2px · 위 4px → 60ms 뒤 들어옴 180ms). 크기 · 글자 · 간격 · 모서리는 토큰(`--fs-md`/휴대폰 `--fs-lg` · `--space-*` · `--r-row`/`--r-pill` · `--h-key`), hover는 `(hover:hover) and (pointer:fine)`에서만 `--fill-1`, 터치 누르는 곳 44px. 줄이기 = 길이 0. N = 지도 종목 중 표시 종류 공시가 있는 종목 = 범례 수.
  - 이름 "공시 있는 종목만 지도에서 밝게, N종목"(+ " · 몇 분째 새 공시를 받지 못했어요" · " · HH:MM까지", 지난 거래일이면 "11월 13일 " 앞에). 켜고 끄면 공용 알림 "공시 있는 N종목만 밝게 보여요." / "모든 종목을 다시 보여요."
  - 상태(칩 때와 같음): 불러오는 중 = 수 자리에 고리 + 꺼진 모습 · 실패 = "!"(`--fail-dot`) 꺼진 모습 · 오래됨 = "!"(쓸 수 있음) · 0종목 = 꺼진 모습(`aria-disabled`, .45, 포커스는 됨, 트랙은 끌리지 않음)이고 누르면 까닭 "지도 종목에 실적·주요 공시가 아직 없어요"를 키 아래 말풍선 + 알림으로(title · 이름에도) · 오늘 다시 보기 = 그 시각까지 수, title "다시 보기 — HH:MM까지 들어온 공시" · 휴장일 = title "11월 13일 (금) 공시" · 다른 날 다시 보기 · 테마 개요 = 스위치 없음.
  - **꺼지는 때**: 오늘 공시 탭을 떠날 때(시장 뉴스 · ←/→), 카드가 숨을 때(`KHNews.hide`), 해외 · 지표 탭, 공시 보기 끔, 탭이 빠질 때(404), 밝힐 종목이 0이 될 때 — 스위치가 화면에 없는데 지도만 흐린 채로 남지 않게. 코스피 → 코스닥처럼 다른 종목 지도로는 켠 채 그 지도의 공시 종목을 밝혀요. 기억하지 않아요(새로고침하면 꺼짐, 저장 키 없음).
  - 뉴스 모듈: `addTab` spec의 **`onHide()`** — 그 탭이 화면에서 내려갈 때(다른 탭 고름 · 탭 빠짐 · 카드 숨김) 불러요. 설정 `공시 보기` 도움말에서 "공시 칩"을 "툴팁 · 오늘 공시 목록"으로 바꿨어요(설정 · 범례 · 귀퉁이 · 툴팁 덩어리는 그대로).

**히트맵이 더한 API** (`window.KH`, 다른 배지도 같이 쓰게)
- `KH.marks.set(name, Map(code → {size:'n'|'new', label, title?, fresh?}) | null)` · `get(name)` · `only(name|null)` · `onlyName()` — 귀퉁이 그림(`<i class="dm">` 하나, `--s`), aria-label 꼬리, 표 보기 이름 칸의 작은 견본, `KH.layout()` 타일 `mark:{kind,size,isNew}`(이미지 저장이 같은 귀퉁이를 그려요). `only`면 그 표시가 없는 타일 `.mdim`, 표는 표시된 행만.
- `KH.cardExtra.add(key, fn(st, how:'tip'|'sheet') → el|null)` · `remove(key)` · `refresh()` — 툴팁·빠른 보기 머리 아래 덩어리(`.cx`, 포커스가 안에 있으면 다시 그리지 않음).
- `KH.legendItem(key, fn → el|[el]|null)` · `KH.legendRefresh()` — 범례 `크기` 앞 항목(테마 개요 제외).
- `KH.addSetting({key, label, hint, multi:true, options:[..], default:[..], min})` → 여러 개 고르는 칩(값은 배열, 저장은 `'a,b'`, `min`개 아래로는 못 끔). `KH.settingState(key, {disabled?, counts?:{값:n}, hint?})`.
- `KH.mapCodes()` → 지금 지도 종목 코드(탭·종목 수 반영, 해외·테마 개요는 `[]`). `KH.replay()` → `{t, date}|null`. `KH.openStock(code, {opener, tab, newsKind})` → 빠른 보기를 닫고 종목 페이지.
- 마운트: 지도 머리줄 `지도 · 표` 앞 `<span id="stage-tools">`(비면 자리 없음, 지수 선 B는 그 앞에서 끝나요 — 2026-11-15부터 공시는 쓰지 않아 비어 있어요, 다른 배지용으로 남겨 둠), 출처 줄 `<p id="foot-disc">`("공시: 금융감독원 DART (제목 · 링크만)").
- 페이지 아래 출처 줄 순서(모든 탭·종목 페이지 공통): 데이터 → 시장 뉴스 → 공시 → (기준일·스냅샷 안내) → © 2026 → **"투자 판단의 근거로 쓰지 마세요."는 항상 맨 아래 한 줄** (사용자 2026-11-14 11:59 "투자 판단의 근거로 쓰지 마세요. 는 항상 맨아래에 있도록"). 템플릿 `disclaimP()`, 종목 페이지 `.sp-disclaim`. 새 출처 줄은 그 위에 넣어요.
- **뉴스 카드 탭** (`src/news`): `KHNews.addTab({key, label: 글자|() → 글자, count?: () → 글자, pane, list, at?: el → 머리 오른쪽 내용, render(L), onShow?, onHide?})` — `L` = `{measure, base, two, phone, rowsMax}`(뉴스와 같은 채우기: PC는 줄 수를 재서 옆 칸 끝까지, 1200px 이상 두 단) · `removeTab(key)` · `select(key)` · `tab()` · `update()` · `relayout()` — 탭이 둘 이상이면 카드 제목이 탭(←/→/Home/End, 고른 탭 기억 `khm.feedTab`), 하나면 지금 제목 그대로. 탭을 다 빼면 카드가 숨어요.
- **종목 페이지** (`src/stock`): `KHStock.open(code, {opener, tab:'news', newsKind:'disc'})`, 오늘 DART 줄에 `KHDisc.info(rcpNo)`의 처음 본 시각과 새 공시 점.
- **공시 모듈** `src/disclosure/disc.js · disc.css`(빌드: 뉴스 다음): `window.KHDisc = {refresh(), rows(code), info(rcpNo) → {s, isNew, date}}`, `KH.disclosures(code?)`.
- 점검 `qa/disclosure/test_disclosure.py`(목 `qa/news/mock_api.py`의 `/__mode?disc=ok|busy|holiday|empty|fail|slow|none|stale|etag|drift|nosince`, 공시가 없으면 기본 테마가 `main` 빌드와 같은지 픽셀 비교 포함).
