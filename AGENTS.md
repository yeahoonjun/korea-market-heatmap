# AGENTS.md — 한국 증시 히트맵

코스피·코스닥을 섹터 › 업종 › 종목 트리맵으로 보여 주는 Finviz 스타일 히트맵과, 종목을 누르면 열리는 종목 페이지예요.
사람과 에이전트가 모두 따르는 규칙이에요. 여기에 없는 작업 방식은 `agent-orchestration` 스킬 기본값을 따릅니다.

---

## 0. 결정 사항 (사용자, 2026-11-09)

- **색**: 상승은 빨강 계열, 하락은 초록 계열이 기본이에요(`krg`). HTS 색(빨강/파랑), 초록 상승(Finviz), 색각 친화는 선택지로만 둬요. 0%는 회색.
- **글꼴**: Pretendard Variable. 숫자는 `font-variant-numeric: tabular-nums`.
- **실시간 데이터**: 네이버 증권(비공식). 브라우저는 네이버를 직접 부를 수 없어요(외부 Origin → 403). 항상 Worker가 대신 받아요.
- **배포**: GitHub 공개 저장소 `yeahoonjun/korea-market-heatmap` + Cloudflare Worker `korea-market-heatmap` (계정 서브도메인 `ssslot` → `https://korea-market-heatmap.ssslot.workers.dev`). Worker는 화면 파일을 저장소에서 읽어 와요.
- **종목 상세**: 전체 화면 종목 페이지. 차트(일·주·월·분봉) + 탭(호가 · 투자자 · 일별 시세 · 공매도). 뒤로 가기로 히트맵 복귀, 주소로 공유 가능.
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

- 주봉 `t`는 그 주의 월요일, 월봉은 1일이에요. `chart.prevClose`는 받은 첫 봉 바로 앞 봉의 종가예요(신규 상장이면 `null`).
- `summary.marketStatus`는 정규장 기준(`OPEN`은 KST 09:00~15:30에만). `orderbook.asOf`는 Worker가 받아 온 시각이에요(네이버가 시각을 안 줘요).
- Worker는 `env.ASSET_BASE`(기본 `https://raw.githubusercontent.com/yeahoonjun/korea-market-heatmap/main/web/`)에서 `index.html`과 `universe.json`을 읽어요. 그래서 `web/`를 커밋·푸시하면 배포가 끝나요(엣지 캐시 최대 약 2분, GitHub raw 캐시 약 5분).
- 네이버 호가는 5단계만 있어요(10단계 원천 없음). 공매도 잔고는 KRX 로그인이 필요해서 지금은 제공하지 않아요.
- 정규장 이후(15:30~20:00) 오늘 봉과 현재가에는 NXT가 섞여요. 일별 시세(`daily`)의 오늘 행은 KRX만이라 둘이 다를 수 있어요. 화면에 표시해요.

**히트맵 → 종목 페이지 연결** (`src/template.html`이 제공)
- `window.KH`: `MODE('snapshot'|'live')`, `LIVE_URL`, `MKT_NAME`, `stock(code)`, `stocks()`, `asOf()`, `colorOf(r)`, `palette()` → `{key,label,stops,up,down,flat,upText,dnText}`, `fmt.{pct,int,chg,eok,cls}`, `h(tag, props, ...kids)`.
- 이벤트(document): `kh:data`(시세 갱신 뒤), `kh:palette`(색상·범위 변경 뒤).
- 종목 페이지가 제공: `window.KHStock = { open(code, {opener}), close(), isOpen() }`. 주소 해시는 `#s-005930` 형식(아티팩트는 `#이름`만 허용).
- 스냅샷 모드에서는 헤더를 `KH.stock(code)`로 그리고, 차트·호가·투자자·일별 자리에 "실시간 버전에서 볼 수 있어요" + `LIVE_URL#s-코드` 링크를 둬요.

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
