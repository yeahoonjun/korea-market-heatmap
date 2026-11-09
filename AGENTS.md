# AGENTS.md — 한국 증시 히트맵

코스피·코스닥을 섹터 › 업종 › 종목 트리맵으로 보여 주는 Finviz 스타일 히트맵과, 종목을 누르면 열리는 종목 페이지예요.
사람과 에이전트가 모두 따르는 규칙이에요. 여기에 없는 작업 방식은 `agent-orchestration` 스킬 기본값을 따릅니다.

---

## 0. 결정 사항 (사용자, 2026-11-09)

- **색**: 상승은 빨강 계열, 하락은 초록 계열이 기본이에요(`krg`). HTS 색(빨강/파랑), 초록 상승(Finviz), 색각 친화는 선택지로만 둬요. 0%는 회색.
- **글꼴**: Pretendard Variable. 숫자는 `font-variant-numeric: tabular-nums`.
- **실시간 데이터**: 네이버 증권(비공식). 브라우저는 네이버를 직접 부를 수 없어요(외부 Origin → 403). 항상 Worker가 대신 받아요.
- **배포**: GitHub 공개 저장소 `yeahoonjun/korea-market-heatmap` + Cloudflare Worker `korea-market-heatmap`. Worker는 화면 파일을 저장소에서 읽어 와요.
- **주소**: **`https://kospimap.pages.dev`** (사용자 선택, 2026-11-09). Cloudflare Pages 프로젝트 `kospimap`의 `_worker.js`가 모든 요청을 서비스 바인딩 `API`로 Worker에 넘겨요. Worker 주소 `korea-market-heatmap.ssslot.workers.dev`도 그대로 동작해요(cron·KV는 Worker에 있어요). 계정 서브도메인 `ssslot`은 SSSlot 게임 주소라 바꾸지 않아요.
- **종목 상세**: 전체 화면 종목 페이지. 차트(1일·5일 분봉, 3개월·1년 일봉, 3년 주봉, 10년 월봉) + 탭(호가 5단계 · 투자자 · 일별 시세 · 뉴스·공시). 공매도는 KRX 로그인이 필요해서 빼요. 뒤로 가기로 히트맵 복귀, 주소로 공유 가능.
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
| `/api/stock/{code}/chart?tf=1d\|5d\|3m\|1y\|3y\|10y` | `{tf, interval, prevClose, bars:[{t,o,h,l,c,v}]}` — `1d`=오늘 1분봉, `5d`=5분봉 약 5거래일, `3m`·`1y`=일봉, `3y`=주봉, `10y`=월봉. 분봉 `t`는 유닉스 초(UTC), 일·주·월봉 `t`는 `YYYY-MM-DD` | 분봉 20초, 그 외 10분 |
| `/api/stock/{code}/orderbook` | `{asks:[{price,qty}], bids:[{price,qty}], totalAsk, totalBid, prevClose, asOf}` — 5단계, 둘 다 **최우선 호가가 먼저** | 2초 |
| `/api/stock/{code}/investors` | `{rows:[{date, close, ratio, individual, foreign, institution, foreignHoldRatio}]}` 최신순, 최대 60일, 순매수 주식 수(부호 있음) | 10분 |
| `/api/stock/{code}/daily?page=N` | `{page, rows:[{date, close, change, ratio, open, high, low, volume}], hasMore}` 최신순 60행 | 60초 |

- 주봉 `t`는 그 주의 월요일, 월봉은 1일이에요. `chart.prevClose`는 받은 첫 봉 바로 앞 봉의 종가예요(신규 상장이면 `null`) — 기간 등락률의 기준으로만 써요. 전일 종가(기준가) 선과 1일 %는 `summary.price − summary.change`로 그려요(오늘 봉 앞 봉은 NXT가 섞여 기준가와 다를 수 있어요).
- `summary.marketStatus`는 정규장 기준(`OPEN`은 KST 09:00~15:30에만). `orderbook.asOf`는 Worker가 받아 온 시각이에요(네이버가 시각을 안 줘요).
- Worker는 `env.ASSET_BASE`(기본 `https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/`)에서 `index.html`과 `universe.json`을 읽어요. 그래서 `web/`를 커밋·푸시하면 배포가 끝나요(엣지 캐시 최대 약 2분, GitHub raw 캐시 약 5분).
- 네이버 호가는 5단계만 있어요(10단계 원천 없음). 공매도 잔고는 KRX 로그인이 필요해서 지금은 제공하지 않아요.
- 정규장 이후(15:30~20:00) 오늘 봉과 현재가에는 NXT가 섞여요. 일별 시세(`daily`)의 오늘 행도 KRX+NXT 통합 가격이라 KRX 종가(15:30)와 다를 수 있어요. 화면에 표시해요.

**히트맵 → 종목 페이지 연결** (`src/template.html`이 제공)
- `window.KH`: `MODE('snapshot'|'live')`, `LIVE_URL`(= `https://kospimap.pages.dev/`), `MKT_NAME`, `stock(code)`, `stocks()`, `asOf()`, `colorOf(r)`, `palette()` → `{key,label,stops,up,down,flat,upText,dnText}`, `fmt.{pct,int,chg,eok,cls}`, `h(tag, props, ...kids)`.
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
| `/data/themes.json`, `/data/periods.json`, `/data/flows.json` | ASSET_BASE의 `web/*.json` 그대로 | 10분 |
| `/manifest.webmanifest`, `/sw.js`, `/icon.svg`, `/icon-192.png`, `/icon-512.png`, `/apple-touch-icon.png` | ASSET_BASE에서 올바른 content-type으로 | 1시간 |

- 리플레이 기록: Worker `scheduled()`가 평일 09:00~15:30 KST에 5분마다(`t`는 5분 단위, 15:30 프레임은 지수가 CLOSE여도 기록) 유니버스 600종목 시세를 KV 바인딩 `REPLAY`(namespace id `bfdaeef6e5204d0ba223a568f76d3c85`)에 프레임마다 한 키로 써요: `replay:YYYYMMDD:codes`, `replay:YYYYMMDD:HHMM` → `{p,r,i}`. TTL 40일. cron `*/5 0-6 * * 1-5` (UTC). 무료 플랜: 외부 서브요청 50개·Cloudflare 서비스 호출 1,000개/요청, KV 쓰기 하루 1,000번.
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
- 장 마감 시각은 시세의 `stockExchangeType.endTime`(보통 `1530`, 수능·첫 거래일 `1630`)을 따라요. cron은 `*/5 0-7 * * 1-5`(UTC, 09:00~16:55 KST), 마감 시각 프레임은 지수가 CLOSE여도 기록해요.
- CORS: `access-control-allow-origin`은 `https://kospimap.pages.dev`로 좁혀요(같은 출처 요청에는 영향 없음).

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

**효과 설정 (히트맵이 제공)**
- `표시 설정`에 `효과: 켜기 · 줄이기`. 기본은 켜기, 단 기기가 `prefers-reduced-motion: reduce`면 줄이기. localStorage `khm.motion`.
- `KH.motion()` → `'full'|'reduced'`, 바뀌면 document 이벤트 `kh:motion` `{motion}`. 모든 모듈은 `reduced`면 플래시·롤링·연출·트윈을 끄고 바로 최종 상태를 그려요(3D는 카메라 관성·높이 트윈 끔).
- 성능: 애니메이션은 `transform`·`opacity`·`filter` 위주, 동시에 도는 플래시는 최대 60개 정도로 제한, 숨은 탭에서는 아무것도 안 돌아요.

**히트맵(`src/template.html`)**
- 시세 플래시: 실시간 갱신에서 `p`가 바뀐 타일만 테두리/안쪽 빛이 오르면 `--up-text` 계열, 내리면 `--dn-text` 계열로 약 0.7초 반짝여요(색 자체는 그대로). 표 보기는 해당 행의 값 칸이 반짝여요. 리플레이 중과 첫 그림에는 플래시 없음.
- 첫 진입 연출: 세션당 한 번(sessionStorage), 섹터 순서로 타일이 짧게 펼쳐지듯 나타나요(전체 0.7초 이내). 머리글 지수는 카운트업.
- 리플레이 트윈: `KH.setReplay(frame, {tween: ms})` — 이전 상태에서 새 프레임으로 색(Lab 보간)·라벨 숫자·크기(FLIP)를 `ms` 동안 이어 그려요. `tween` 없으면 지금처럼 즉시.
- 3D 보기 연결: 지도/표 전환을 `지도 · 3D · 표`로. 3D를 고르면 `#map`은 계속 배치만 하고(보이지 않게) 같은 자리의 `<div id="map3d">`를 보이게 한 뒤 `window.KH3D.show()`, 나가면 `KH3D.hide()`. 3D 선택은 저장하지 않아요(매번 2D로 시작). `KH3D`가 없거나 WebGL이 안 되면 안내 문구 후 지도로 돌아가요. 3D 중에도 `kh:render`·`kh:data`·`kh:palette`는 그대로 발생.

**extras (`src/extras/`)**: 리플레이 재생을 타임랩스로 — 재생 중 프레임 사이를 `KH.setReplay(..., {tween})`로 이어서 끊김 없이, 지도 위에 큰 시각 표시(쇼룸 페이지 같은 굵은 큰 글씨, 반투명, 지도 정보를 가리지 않게 모서리). 시장 띠 값이 바뀔 때 숫자 롤링(자리별로 굴러가는 오도미터).
**종목 페이지 (`src/stock/`)**: 머리 현재가·등락이 바뀔 때 숫자 롤링, 호가 칸 값이 바뀌면 짧게 반짝.
**해외 (`src/world/`)**: 세계지도에 실시간 낮/밤 경계(태양 직하점의 반대편 반구를 어둡게, 1분마다 갱신, 경계는 부드러운 그라데이션), 지금 장이 열린 나라·마커에 은은한 빛(맥동은 `full`일 때만).

**3D 지도 모듈 `src/map3d/map3d.js`, `map3d.css`** (3D 담당, 빌드가 world 다음에 끼워 넣어요)
- `window.KH3D = {show(), hide(), isOn()}`. `#map3d` 안에 canvas. 데이터는 `KH.layout()`(타일 x·y·w·h·color·code·label·sub, 섹터·업종 머리글)과 `KH.stock(code)`.
- 타일을 상자로 세우고 높이 = |등락률|(색 범위 도구 기준으로 정규화), 오른 종목은 위로·내린 종목은 바닥 아래로(또는 같은 방향으로 세우고 색으로만 구분 — 판단해서 읽기 쉬운 쪽). 섹터 사이 틈, 섹터 이름 라벨. 마우스 끌기·한 손가락으로 회전, 휠·두 손가락으로 확대, 처음엔 약간 기울어진 시점. 마우스 올리면 툴팁(이름·등락률·현재가), 누르면 `KHStock.open(code)`.
- three.js는 3D를 처음 켤 때만 jsDelivr에서 SRI로 불러요(UMD `build/three.min.js`가 있는 버전). `InstancedMesh` 등으로 600개도 휴대폰에서 부드럽게. 갱신 때 높이·색 트윈(`full`일 때). 탭이 숨으면 렌더 루프 멈춤, `hide()`면 GPU 자원 정리.
