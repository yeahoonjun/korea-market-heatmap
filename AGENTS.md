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
- **종목 상세**: 전체 화면 종목 페이지. 차트(탭 = 봉 간격 `1분 · 5분 · 일 · 주 · 월 · 년`, 사용자 2026-11-13 22:38; 년봉은 월봉을 화면에서 묶음; 5·20·60·120 이동평균선 + 켜고 끄는 칩 `khm.stock.ma`, 간격 `khm.stock.iv`) + 탭(호가 5단계 · 투자자 · 일별 시세 · 뉴스·공시). 공매도는 KRX 로그인이 필요해서 빼요. 뒤로 가기로 히트맵 복귀, 주소로 공유 가능.
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
| `/api/stock/{code}/chart?iv=1m\|5m\|day\|week\|month[&to=YYYYMMDD\|YYYYMMDDHHMM][&count=N][&warm=N]` | `{iv, interval, prevClose, bars, pre?, more}` — `to`(KST, 기본 지금) **앞쪽** 봉 `count`개(기본 250, 최대 1500, 오래된 순), `pre`는 위와 같고, `more`=더 오래된 봉이 있을 수 있음. 화면은 이걸로 스크롤하면 과거를 이어 받아요. 네이버가 분봉(1m·5m)은 약 6거래일만 줘서 거기서 끝나요. `tf=` 형식은 그대로 | 분봉·`to` 없음 20초, 그 외 10분 |
| `/api/stock/{code}/orderbook` | `{asks:[{price,qty}], bids:[{price,qty}], totalAsk, totalBid, prevClose, asOf}` — 5단계, 둘 다 **최우선 호가가 먼저** | 2초 |
| `/api/stock/{code}/investors` | `{rows:[{date, close, ratio, individual, foreign, institution, foreignHoldRatio}]}` 최신순, 최대 60일, 순매수 주식 수(부호 있음) | 10분 |
| `/api/stock/{code}/daily?page=N` | `{page, rows:[{date, close, change, ratio, open, high, low, volume}], hasMore}` 최신순 60행 | 60초 |

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
| `/api/replay/dates` | `{dates:['YYYY-MM-DD',…]}` 최신순 | 60초 |
| `/api/replay?date=YYYY-MM-DD` | `{date, codes:[…], frames:[{t:'HHMM', p:[…], r:[…]}], index:{KOSPI:[…],KOSDAQ:[…]}, base:{KOSPI,KOSDAQ}\|null}` — `p`·`r`·지수는 `codes`/`frames` 순서, `base`는 지수 전일 종가. 날짜 없으면 최신 | 60초(지난 날 1시간) |
| `/api/replay/status` | 기록기 상태(§3-15 ①): KV `replay:status` `{v, at(ms), day:'YYYY-MM-DD', t:'HHMM', result:'wrote'\|'skipped:<이유>'\|'error', error?, rows?, since(ms), lastWrote:'HHMM'\|null, errors(그날, 근사), lastError?:{t,error}, cron}` + `{now(ms), nowKst, atKst, ageSec, due, recent, stale}` — 아직 없으면 `result:null`. `due`=평일 09:06~마감, `recent`=최근 5분 프레임 키가 있는지(`{'HHMM':bool}`), `stale`=`due`인데 그 5분에 프레임이 하나도 없음. 이유: `after-end`·`closed`(휴장) | 없음(`no-store`) |
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
| `web/close.json` | `{date:'YYYY-MM-DD', asOf, c:{코드:[종가, 전일대비, 등락률]}}` KRX 15:30 종가(스냅샷이 고정한 값), 전 종목 | 장 마감 뒤 실시간 지도를 "정규장 종가"로 볼 수 있게. 스냅샷이 15:30 고정이 아니면 만들지 않아요. `KH.loadData('close')` |
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
- 장 마감 시각은 시세의 `stockExchangeType.endTime`(보통 `1530`, 수능·첫 거래일 `1630`)을 따라요. cron은 `* 0-7 * * 1-5`(UTC, 매분, §3-15), 마감 시각 프레임은 지수가 CLOSE여도 기록해요.
- CORS: `access-control-allow-origin`은 `https://panse.pages.dev`로 좁혀요(같은 출처 요청에는 영향 없음, Worker v14).

**등락 분포 = 전 종목** (사용자 요청 2026-11-09 23:43: "300종목만 말고 전 종목으로")
- Worker `/api/breadth?m=K|Q&part=N` → `{m, part, parts, asOf, rows:[[코드, 등락률, lim?]]}` — 시장 `m`의 전 종목(`universe.json`의 `K`/`Q` + `X` 중 그 시장, 우선주 포함)을 코드 순으로 600개씩 나눈 `part`번째 묶음 — **`part`는 1부터** (`1..parts`). `parts`는 묶음 수(코스피 2, 코스닥 3). 한 호출에 polling 1번(600개 이하) — 무료 플랜 CPU 한도 때문에 나눠요. 행은 작게(가격·이름 없이). 캐시: 정규장 중 30초, 그 밖 10분. `part`가 범위 밖이면 400.
- 히트맵 "등락 분포" 카드(오늘 기준)는 지도 종목이 아니라 **그 시장 전 종목** 분포를 보여 줘요: 정규장 중에는 `/api/breadth` 묶음들(카드가 화면에 보일 때만 60초마다, 숨은 탭에서는 멈춤), 장 마감 뒤 "정규장 종가"면 `close.json`(전 종목), 스냅샷은 내장 2,700종목. 머리글 범위 표시는 "코스피 전 종목 9xx" 식. 일부 묶음이 실패하면 받은 것만 쓰고 "일부만 반영" 표시, 전부 실패하면 지도 종목 분포로 돌아가고 그렇게 적어요.
- 막대를 누르면 지도의 해당 구간 종목을 강조하는 동작은 그대로(지도에 없는 종목은 강조 대상이 아니라고 안내). 기간 수익률·순매수 색 기준일 때는 데이터가 있는 종목 범위로 그리고 범위를 적어요. 테마·관심 보기와 섹터·업종 확대(focus) 중에는 기존처럼 그 범위만.

## 3-4. 해외 지수 · 원자재 탭 (사용자 요청 2026-11-09 23:46)

"코스피, 코스닥, 전체, 테마에 추가로 원자재와 해외 시장 지수 모음" → 시장 탭에 **해외**, **원자재** 두 개를 더해요. 순서: 코스피 · 코스닥 · 전체 · 테마 · 해외 · 원자재 · ★관심. 휴대폰에서는 탭 줄이 옆으로 넘어가요(잘리지 않게, 현재 탭이 보이게).

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
- `KH.motion()` → `'reduced'|'standard'|'fancy'`(기본 `'standard'`), 바뀌면 document 이벤트 `kh:motion` `{motion}`. 모든 모듈: `fancy`가 아니면 새 효과를 쓰지 않고 바로 최종 상태를 그려요. `reduced`면 기존 전환도 꺼요.
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
- **cron**: `* 0-7 * * 1-5`(매분). 오케스트레이터가 배포할 때 바꿔요. 프레임 키·모양은 지금과 같음: `replay:YYYYMMDD:HHMM`, 09:00 → `endTime`(보통 15:30, 391개).
- **API (예전 화면 호환)**
  - `/api/replay?date=` — 지금 그대로(5분 프레임: 09:00, 09:05 …). 1분 기록이 있는 날도 5분 칸만.
  - `/api/replay?date=&step=1&from=HHMM&to=HHMM` — 그 사이 **1분 프레임**(양 끝 포함, 한 번에 최대 120개), 응답 모양은 5분 응답과 같음(+ `step:1`). 없는 분은 빠져요(잠깐 실패한 분).
  - `/api/replay/dates` — 지금 응답에 `minute: [1분 기록이 있는 날짜…]` 추가.
  - 캐시: 지난 날 1시간, 오늘 1분. 하루치 1분 전체를 한 번에 주지 않아요(휴대폰 데이터 — 프레임 하나 ~10KB × 391).
  - 오늘 요청에서 KV 읽기가 많아지니 묶음 읽기·Promise.all을 쓰되 응답 시간 목표 1초 안.
- **cron 요일 번호 주의** (2026-11-13 금요일 기록 0건의 원인): Cloudflare cron은 요일을 **1=일요일 … 7=토요일**로 세요. 그래서 `* 0-7 * * 1-5`는 **일~목**에만 돌고 금요일엔 한 번도 돌지 않아요(일요일 480번은 기록기가 그냥 건너뜀). 평일은 **`MON-FRI`**(=`2-6`)로 써야 해요 — `wrangler.toml`을 바꾸면 배포 작업(`ensureCrons`)이 맞춰 줘요. 점검: `node qa/worker/test_replay_recorder.mjs`가 cron이 월~금을 다 덮지 않으면 종료 코드 2.
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

**색 범위 자동** (22:26 "현재 보이는 최고 최저에 맞게 자동 조절 … 코스닥에서 범위 10퍼센트로 하다가 해외나 원자재 탭으로 가면 … 색상 차이가 없어져서 불편해"): 템플릿이 테마 작업을 병합한 뒤 구현.
- 색 범위에 `자동` 추가(기본값): 지금 화면에 그린 항목 등락률 절댓값의 95번째 백분위를 1·2·3·4·5·7·10·15·20·30% 중 올림 — 상한가 하나가 전체를 흐리게 만들지 않게. 범례에 "자동 ±4%"처럼 실제 값. 갱신 때 깜박이지 않게 단계가 바뀔 때만(작은 히스테리시스).
- 수동 선택은 **국내(코스피·코스닥·전체·테마·관심)와 해외·원자재를 따로 기억**.
- **구현 (feat/auto-range)**: 색 범위 `자동 · ±3% · ±5% · ±10%`(오늘 등락률일 때만; 기간·수급 색은 지금 범위 그대로). 저장 `khm.range`(국내, 옛 키 — 저장된 숫자는 그대로) · `khm.rangeW`(해외·원자재, 새 키), 값 `'auto'|3|5|10`, 없으면 자동. 측정 범위 = 그 탭이 그리는 항목(국내: 그 탭의 지도 종목 — 시장 상위 N·테마 개요의 테마·테마 종목·관심 그룹, **섹터 확대로 좁히지 않음**(확대해도 색이 안 바뀌게) / 해외·원자재: world.js가 `KH.feedRange(kind, ratios)`로 넘기는 항목, VIX 제외). 백분위는 선형 보간(p95). **히스테리시스**: 탭마다 따로 — 더 큰 단계는 바로, 더 작은 단계는 `p95 ÷ 0.85`가 그 단계에 들어갈 때만(= p95가 아래 단계보다 15% 이상 작을 때). 단계가 바뀔 때만 `kh:palette`. API `KH.rangeInfo()` → `{value, auto, pick, p95, scope}`, `KH.range()`는 지금 값(자동이면 그 단계). 범례 "자동 ±4%" 태그(앰버 아님, 가는 테). 1280~1339px 도구 줄은 자리가 모자라 `±`를 숨겨요(`3% · 5% · 10%`, 이름엔 ±). QA `qa/tabs/test_auto_range.py`.

**해외 묶음** (22:26 "빅스는 미국 빅스니까 미국 지수쪽에 … 선물같은경우도 각 나라 지수랑 같이 묶여야"): 미국 선물·VIX를 미국 묶음으로(목록: 현물 → 선물 → VIX 참고), 세계지도의 옆 상자는 **남겨 두고 제목을 "미국 선물 및 변동성 지수"로**, 그 상자에서 **유로스톡스 50만 빼서** 유럽(유로존) 쪽으로(사용자 22:32 정정). 미국 시트에도 선물·VIX가 현물 다음에 나와요. Worker 묶음은 그대로, world.js가 화면에서 다시 묶어요.

## 3-28. 환율 · 금리 (사용자 2026-11-13 22:34·22:35) — 지금 작업(테마·해외 묶음·뉴스 시안)이 끝난 뒤 시작
"환율탭이 필요할거같아 아님 중요한 원달러랑 유로랑 엔만 있으면 되나?" → 추천안 1 채택: 새 탭 대신 **원자재 탭을 넓혀 환율 묶음**, + "달러인덱스와 달러엔도 좋은 생각" + "국고채, 일본 국채, 미국 국채도".
- 환율: 원/달러 · 원/엔(100엔) · 원/유로 · 원/위안 · 달러인덱스 · 달러/엔. 묶음 제목 옆 "오르면 원화 약세"(달러인덱스·달러/엔은 "오르면 달러 강세"·"오르면 엔화 약세"). 빨강·초록은 숫자의 오르내림만.
- 금리: 한국 국고채(1·3·10년), 미국 국채(2·10·30년), 일본 국채 10년 — 값은 %, 변화는 bp(0.01%p). 색은 금리 오르내림.
- 원천(2026-11-13 실측, `api.stock.naver.com/marketindex/…`): `exchange/FX_USDKRW`·`FX_JPYKRW`·`FX_EURKRW`·`FX_CNYKRW`·`.DXY` 응답 있음, 달러/엔은 `FX_USDJPY`·`JPY=` 없음 → 다른 코드 찾기, 없으면 원/달러 ÷ 원/엔으로 계산하고 "계산값" 표시. `bond/KR1YT=RR`·`KR3YT=RR`·`KR10YT=RR`·`US2YT=RR`·`US10YT=RR`·`US30YT=RR`·`JP10YT=RR` 응답 있음. Worker `/api/world?kind=commodity`에 `fx`·`rates` 묶음을 더하거나 `kind=macro` 신설(구현 때 판단), 차트 경로도.
- 탭 이름: **"지표"로 확정**(사용자 2026-11-13 23:20). 이름은 템플릿 `MKT_NAME.CMDTY` 한 곳에만 있어요 — 탭 버튼 글자·aria-label("지표: 원자재 · 환율 · 금리"), world.js 머리 제목·안내 문구, extras 이미지 저장 제목이 모두 거기서 읽어요. 해시는 그대로 `#cmdty`, 탭 안 묶음 이름은 원자재 · 환율 · 금리.

**구현 (feat/fx-rates, 2026-11-13)**
- **Worker** `GET /api/world?kind=commodity&with=fx,rates` → 기존 원자재 묶음 뒤에 `{key:'fx', name:'환율'}`, `{key:'rates', name:'금리'}`. `with` 없이 부르면 응답이 예전과 똑같아요(티커 고르기가 그걸 읽어요). `with`는 `fx`·`rates` 중 쉼표로, `kind=index`에 쓰거나 다른 값이면 400. 30초 캐시, 묶음마다 따로 실패(빠진 쪽만 없음). 항목 모양은 §3-4 그대로 + `bp`(금리: 변화 %p × 100, 소수 둘째 자리), `eod:true`(하루 한 번 종가), `calc:true`(계산값), `via`(하나은행 고시 · 미국 ICE선물거래소 · 레피니티브). 금리 `unit:'%'`, `tz`는 설정값(서울·뉴욕·도쿄). 차트 `/api/world/chart/{key}`도 같은 키로(일봉 종가, `…/marketindex/{exchange|exchangeWorld|bond}/{코드}/prices`).
- 키: `FX_USDKRW` `FX_JPYKRW` `FX_EURKRW` `FX_CNYKRW` `DXY` `USDJPY` / `KR1YT` `KR3YT` `KR10YT` `US2YT` `US10YT` `US30YT` `JP10YT`(로이터 코드에서 앞 점과 `=RR`을 뺀 값).
- 원천: 원화 환율 4개 + 달러인덱스 = `api.stock.naver.com/marketindex/exchange` 목록 한 번(polling 호스트엔 `exchange`가 없어요). **달러/엔 = 원/달러 ÷ (원/엔 ÷ 100)**, 같은 하나은행 고시 회차로 계산한 값이 먼저예요(`calc:true`, `via:'하나은행 고시로 계산'`, 장중/마감은 두 값 모두 OPEN일 때만 OPEN, 오케스트레이터 2026-11-13) — 화면은 상태 칸에 "계산값", 시트 출처 줄에 "차트는 레피니티브 종가". 계산할 수 없을 때만 `exchangeWorld/USDJPY`(polling, 레피니티브 **하루 한 번 종가**, `eod:true` — "마감 · 하루 한 번 종가", 기준일만). 차트 경로는 언제나 `exchangeWorld/USDJPY` 일봉 종가(마지막 점은 계산값). 국채 = `bond/{코드}` 7번(목록·polling 없음, 일본 2시간 지연). 네이버가 한국 국채를 밤에도 `OPEN`으로 두어서, 지연 + 2시간보다 오래된 금리 시세는 `CLOSE`로 바꿔요.
- **화면(world.js)**: 지표 탭은 `kind=commodity&with=fx,rates`를 받아 목록을 두 덩어리로 — 제목 줄 "원자재"(에너지·금속·농산물, 등락률순이면 원자재끼리만 순위) · "환율 · 금리"(언제나 묶음별). 환율 머리 "오르면 원화 약세", 달러인덱스·달러/엔 행 보조 글자 "오르면 달러 강세"·"오르면 엔화 약세", 금리 머리 "변화는 bp(0.01%p)". 금리 행 = `3.756%` + 색 칩 `+2.3bp`(변화 칸은 비워요), 색은 그날 변화의 부호(빨강 오름·초록 내림). 요약 줄·많이 오른·내린은 원자재만("원자재 17개 중"). 시트: 단위(원 (1달러당)·원 (100엔당)·포인트·엔 (1달러당)·연 %), 기준(via), 금리는 `+2.3bp (+0.023%p)`, 차트 눈금 %·기간 변화 bp. 옛 Worker(그룹 없음)면 예전 원자재 화면 그대로.
- **티커**(extras): 띠의 원/달러(`m:USDKRW`)를 누르면 `FX_USDKRW` 시트가 열려요(`TK_WORLD`). 티커 고르기의 환율·금리 분류는 아직 그대로.
