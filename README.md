# 한국 증시 히트맵

**주소: https://kospimap.pages.dev**

코스피·코스닥 종목을 섹터 › 업종 › 종목 트리맵으로 보여 주는 Finviz 스타일 히트맵이에요.
타일 크기는 시가총액·거래대금·외국인/기관 순매수, 색은 등락률(오늘·1주·1개월·3개월·올해·1년)이에요.
테마 지도, 관심종목, 해외 지수·원자재 탭, 장중 리플레이, 종목 페이지(차트·호가·투자자·재무·리서치·뉴스·공시)가 있어요.

일하는 규칙과 데이터 계약은 [`AGENTS.md`](AGENTS.md)에 있어요.

## 폴더 구성

```
src/template.html          히트맵 화면 (HTML·CSS·JS 한 파일, d3 v7)
src/stock/                 종목 페이지
src/extras/                시장 띠(티커), 이미지 저장, 홈 화면 앱, 리플레이
src/world/                 해외 지수 · 원자재 탭
src/pwa/  src/fonts/  src/vendor/   앱 아이콘·서비스 워커, Pretendard 서브셋, d3 (스냅샷에 넣는 용도)
data/snapshot.json         전 종목 + 업종·섹터 (KRX 15:30 종가로 고정)
data/ENDPOINTS*.md         네이버·DART 엔드포인트 실측 노트
scripts/build_snapshot.py  스냅샷 만들기
scripts/build_daily.py     테마·기간 수익률·투자자 동향 (매일 GitHub Actions)
scripts/build_page.py      dist/index.html(스냅샷), web/ (실시간 버전 파일)
scripts/build_worker.mjs   worker/dist/worker.js (Cloudflare 업로드용 한 파일)
worker/                    Cloudflare Worker (API 프록시, 리플레이 기록 cron)
web/                       실시간 버전 정적 파일 — Worker가 GitHub에서 바로 읽어요
```

## 두 가지 모드

| 모드 | 어디서 | 데이터 |
|---|---|---|
| 스냅샷 | `dist/index.html` (네트워크 없이도 열려요) | 빌드할 때의 15:30 종가 |
| 실시간 | https://kospimap.pages.dev | 네이버 증권, 정규장 중 몇 초마다 갱신 |

브라우저는 네이버 API를 직접 부를 수 없어요(다른 사이트의 요청을 403으로 막아요).
그래서 Worker가 서버에서 대신 받아 오고 엣지 캐시에 잠깐 담아 둬요.

## 배포

- **화면**: `python3 scripts/build_page.py` 뒤 `web/`를 커밋·푸시하면 끝이에요. Worker가 `raw.githubusercontent.com`에서 읽어요(캐시 몇 분).
- **Worker**: `node scripts/build_worker.mjs` → `worker/dist/worker.js`를 Cloudflare에 올려요(`worker/wrangler.toml`: KV `REPLAY`, cron `* 0-7 * * 1-5`, 매분). 비밀값 `DART_KEY`(OpenDART)는 Cloudflare에만 있어요.
- **주소**: Cloudflare Pages 프로젝트 `kospimap`이 서비스 바인딩으로 Worker에 넘겨요.
- **매일 데이터**: `.github/workflows/daily.yml` — 평일 16:40 KST(장 마감 확인 뒤) 스냅샷·테마·기간 수익률·투자자 동향을 만들어 커밋, 21:30에 투자자 동향만 한 번 더.

## Worker API (요약)

| 경로 | 내용 | 캐시 |
|---|---|---|
| `/api/quotes` | 시장별 시총 상위 300종목 + 지수 (`?codes=`로 지정 종목, `?scope=all`로 상장 전 종목 약 2,700) | 8초 |
| `/api/breadth?m=K\|Q[&part=N]` | 시장 전 종목 등락률(등락 분포용). `part` 없으면 한 번에, `part=N`이면 600개씩 나눈 N번째 | 30초~10분 |
| `/api/market` | 시장 띠: 코스피·코스닥·원/달러·미국 선물·WTI·금·비트코인 | 30초 |
| `/api/world?kind=index\|commodity` | 해외 지수 41개 · 원자재 17개 | 30초 |
| `/api/world/chart/{키}?tf=3m\|1y` | 해외 지수·원자재 일봉 종가 | 10분 |
| `/api/themes` | 테마별 등락률 | 30초 |
| `/api/stock/{코드}/summary·chart·orderbook·investors·daily·news·disclosures·finance·research` | 종목 페이지 | 2초~6시간 |
| `/api/replay/dates`, `/api/replay?date=` | 장중 리플레이(매분 기록, 이 경로는 5분 칸만). `dates` 응답의 `minute`은 1분 기록이 있는 날 | 1분~1시간 |
| `/api/replay?date=&step=1&from=HHMM&to=HHMM` | 그 구간의 1분 프레임(양 끝 포함, 한 번에 120개까지) | 1분~1시간 |
| `/data/*.json` | 테마·기간·투자자·이름·종가 파일 | 10분 |
| `/api/health` | `{ok:true}` | 없음 |

정확한 응답 모양은 `AGENTS.md` §3·§3-2·§3-3·§3-4·§3-15에 있어요.

## 알아 둘 점

- 네이버 증권 API는 공식 공개 API가 아니에요. 개인 용도로는 동작하지만 예고 없이 바뀔 수 있어요.
  대규모 서비스라면 증권사 Open API(예: 한국투자증권 KIS)로 바꾸는 게 안전해요.
- 15:30 이후 네이버 시세에는 NXT 거래가 섞여요. 실시간 화면은 "정규장 종가 / NXT 포함"을 고를 수 있어요.
- Workers Paid 플랜(2026-11-10~)이라 하루 요청 상한이 없고 요청당 CPU 30초까지 써요. 그래서 전 종목(`/api/quotes?scope=all`)·전 종목 분포(`/api/breadth?m=`)를 한 번에 받아요. 기본 지도는 여전히 시장별 300종목이에요(휴대폰 데이터).
- 호가는 5단계만 있어요. 공매도 잔고는 KRX 로그인이 필요해서 넣지 않았어요.
