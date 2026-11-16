# 한국투자 Open API — 실측 노트 (AGENTS §3-40)

실측 2026-11-16 15:45~15:50 KST(장 마감 뒤, 그날 14:30 입력분까지 들어 있는 상태), 실전 앱 키, Worker 확인용 경로 `/api/kis/raw`(dev 초대만)로.
키 · 접근 토큰 · 초대 토큰은 이 문서 · 저장소 · 로그에 쓰지 않아요.

## 공통
- 서버 `https://openapi.koreainvestment.com:9443` (Worker `fetch`에서 포트 그대로 됨 — 호환 날짜 2026-11-01, `allow_custom_ports` 기본).
- 토큰 `POST /oauth2/tokenP` `{grant_type:'client_credentials', appkey, appsecret}` → `{access_token, expires_in:86400, …}`. 발급은 1분에 1번(한국투자 한도), 발급할 때마다 사용자에게 알림이 갈 수 있어요 → KV `kis:tok`에 두고 하루 한 번만.
- 시세 GET 머리: `authorization: Bearer <토큰>`, `appkey`, `appsecret`, `tr_id`, `custtype: P`, `content-type: application/json; charset=utf-8`.
- 응답 봉투 `{rt_cd:'0', msg_cd:'MCA00000', msg1:'정상처리 되었습니다.', output…}`. 숫자는 모두 **글자**(부호 · 앞 0 있음 — `"-00000000002132000"`). 토큰 만료 · 무효 `EGW00123` · `EGW00121`.
- 호출 한도: 실전 초당 20건(넘으면 `EGW00201`). 우리는 초당 10건 안으로.

## ① 외국인 · 기관 매매종목 가집계 순위 — `FHPTJ04400000`
`GET /uapi/domestic-stock/v1/quotations/foreign-institution-total`
| 인자 | 값 |
|---|---|
| `FID_COND_MRKT_DIV_CODE` | `V` |
| `FID_COND_SCR_DIV_CODE` | `16449` |
| `FID_INPUT_ISCD` | `0000` 전체 · `0001` 코스피 · `1001` 코스닥 |
| `FID_DIV_CLS_CODE` | `0` 수량 정렬 · `1` 금액 정렬 |
| `FID_RANK_SORT_CLS_CODE` | `0` 순매수 상위 · `1` 순매도 상위 |
| `FID_ETC_CLS_CODE` | `0` 전체(외국인+기관) · `1` 외국인 · `2` 기관계 · `3` 기타 |
- 응답 `output` **30행**(연속 조회 없음, `tr_cont` 빈 값). 행: `hts_kor_isnm` 이름 · `mksc_shrn_iscd` 코드 · `stck_prpr` 현재가 · `prdy_vrss_sign` · `prdy_vrss` · `prdy_ctrt` 등락률 · `acml_vol` · `ntby_qty`(정렬 기준 주체의 순매수 수량) · `frgn_ntby_qty` · `orgn_ntby_qty` · 기관 세부 `ivtr`(투신) · `bank` · `insu` · `mrbn`(종금) · `fund`(기금) · `etc_orgt` · `etc_corp` `_ntby_qty|_vol` · 금액 `frgn_ntby_tr_pbmn` · `orgn_ntby_tr_pbmn` · … `_tr_pbmn` = **백만원**(KB금융 외국인 188,000주 × 161,600원 = 303.8억 = `30381`).
- 실측: 코스피 외국인 순매수 1위 KB금융 +303.8억 · 순매도 1위 SK하이닉스 −6,988.8억(기관 −2,564.8억), 코스닥 기관 순매수 1위 와이씨 +41.6억.
- 시각 필드가 없어요 — 언제 입력분인지는 ②의 슬롯 수로 알아요.

## ② 종목별 외인 · 기관 추정 가집계 — `HHPTJ04160200`
`GET /uapi/domestic-stock/v1/quotations/investor-trend-estimate?MKSC_SHRN_ISCD=005930`
- 응답 `output2` = 입력 회차마다 한 행, **최신 회차가 먼저**: `bsop_hour_gb` 1~5 · `frgn_fake_ntby_qty` · `orgn_fake_ntby_qty` · `sum_fake_ntby_qty`(주, 누적, 부호 있는 글자).
- 회차(한국투자 설명 "증권사 직원이 장중에 집계/입력한 자료를 단순 누계한 수치", 외국인 09:30 · 11:20 · 13:20 · 14:30, 기관종합 10:00 · 11:20 · 13:20 · 14:30): 1 = 09:30(기관 0), 2 = 10:00, 3 = 11:20, 4 = 13:20, 5 = 14:30. 실측 삼성전자 외국인 −564,000 → −559,000 → −1,517,000 → −2,077,000 → −2,132,000, 기관 0 → 85,000 → 280,000 → 193,000 → 220,000.
- 금액이 없어요 — 수량 × 가격으로 어림.
- 개인은 어디에도 없어요(가집계는 외국인 · 기관만).

## ③ 시장 전체 3주체 (한국투자 아님 — 네이버, 공개)
`GET https://m.stock.naver.com/api/index/{KOSPI|KOSDAQ}/integration` → `dealTrendInfo: {bizdate:'20261116', personalValue:'+13,477', foreignValue:'-13,769', institutionalValue:'-4,592'}`(억원, 부호 · 쉼표 글자), 옆에 `programTrendInfo`. 시각 필드 없음 — 받은 시각을 기준 시각으로.
