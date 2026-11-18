# 판세 날짜별 보관 (archive)

판세 매일 작업이 덮어쓰는 파일의 날짜별 사본이에요. 개인 사이트 「왕이 될 상」이 읽어요 (AGENTS.md §3-41).

- `<YYYY-MM-DD>/close.json · snapshot.json · flows.json · alerts.json · themes.json` — 원본 그대로(바이트 단위 복사).
- 폴더 날짜는 실행한 날이 아니라 **파일 안의 날짜**예요: close.json `date`, snapshot.json `asOf` 앞 10자, 나머지 `asOf`.
  그래서 한 날짜 폴더에 모든 파일이 있지 않을 수 있어요(아침 07:50 경보만 있는 날, 휴장일 아침 등).
- `latest.json` = `{v, updated, latest(KRX 종가가 있는 가장 최근 날), newest, days:[{d, f}]}` 최신순.
- 출처: 네이버 증권 · 한국거래소 지정(시장 경보). 판세 화면과 같은 원천이에요. 증권사 컨센서스는 여기 두지 않아요.
- 이 브랜치는 매일 작업(`.github/workflows/daily.yml`)만 써요. 손으로 고치지 않아요.
