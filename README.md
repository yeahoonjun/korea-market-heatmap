# 한국 증시 히트맵

**주소: https://kospimap.pages.dev**

코스피·코스닥 종목을 섹터 › 업종 › 종목 트리맵으로 보여 주는 Finviz 스타일 히트맵이에요.
타일 크기는 시가총액(또는 거래대금), 색은 전일 대비 등락률이에요.

## 폴더 구성

```
src/template.html        화면 전체 (HTML·CSS·JS 한 파일, d3 v7 사용)
data/snapshot.json       코스피·코스닥 전 종목 + 업종·섹터 분류 (build_snapshot.py가 만듦)
data/sector_map.json     네이버 업종 79개 → WICS 10개 섹터 매핑
data/ENDPOINTS.md        네이버 증권 API 조사 노트 (실측)
scripts/build_snapshot.py  스냅샷 다시 만들기
scripts/build_page.py      template + snapshot → dist/index.html, worker/src/page.js, worker/src/universe.js
worker/                  Cloudflare Worker (실시간 모드)
```

## 두 가지 모드

| 모드 | 어디서 | 데이터 |
|---|---|---|
| 스냅샷 | `dist/index.html` (파일 하나로 어디서나 열림) | 빌드할 때 받아 둔 시세 |
| 실시간 | Cloudflare Worker 주소 | 정규장 중 10초마다 갱신, 장 마감 뒤 1분마다 |

브라우저는 네이버 API를 직접 부를 수 없어요. 네이버가 다른 사이트의 요청(CORS)을 403으로 막아요.
그래서 Worker가 서버에서 대신 받아 오고, 엣지 캐시에 8초 동안 담아 둬요. 보는 사람이 많아도 네이버에는 8초에 한 번만 요청이 가요.

## 실시간 버전 배포 (Cloudflare 무료 플랜)

```bash
# 1) 최신 스냅샷 (업종 분류와 실시간 대상 종목 목록이 여기서 나와요. 몇 주에 한 번이면 충분해요)
python3 scripts/build_snapshot.py --close auto --delay 0.2

# 2) 페이지 빌드
python3 scripts/build_page.py

# 3) 배포
cd worker
npm install
npx wrangler login
npx wrangler deploy        # → https://korea-market-heatmap.<계정>.workers.dev (kospimap.pages.dev가 이 Worker로 연결돼요)
```

## Worker API

| 경로 | 내용 | 캐시 |
|---|---|---|
| `/` | 히트맵 페이지 (실시간 모드) | 5분 |
| `/api/quotes` | 시장별 시총 상위 300종목 시세 + 코스피·코스닥 지수 | 8초 |
| `/api/chart/{코드}` | 그날 정규장 5분봉 (상세 패널 미니 차트) | 30초 |
| `/api/health` | `{ok:true}` | 없음 |

## 알아 둘 점

- 네이버 증권 API는 공식 공개 API가 아니에요. 개인 용도로는 문제없이 동작하지만, 예고 없이 바뀔 수 있어요.
  대규모 공개 서비스로 운영하려면 증권사 Open API(예: 한국투자증권 KIS)로 바꾸는 게 안전해요.
  데이터 형식은 `/api/quotes` 응답 한 곳에만 맞추면 되도록 분리해 뒀어요.
- 15:30 이후에는 네이버 시세에 NXT·시간외 거래 가격이 섞여요. 실시간 모드는 이때 상태 표시를 `시간외 가격`으로 바꿔요.
  스냅샷은 `--close auto` 옵션으로 각 종목을 15:30 정규장 종가에 맞춰 둬요.
- 무료 플랜은 요청 하나당 CPU 10ms 제한이 있어요. 그래서 실시간 대상은 시장별 300종목으로 잡았어요.
  500종목 이상을 실시간으로 보려면 `scripts/build_page.py`의 `LIVE_PER_MARKET` 값을 올리고 유료 플랜($5/월)을 쓰세요.
