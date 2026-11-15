# 증시 캘린더 — 설계와 구현

> **상태: 결정됨(사용자 2026-11-15 17:52, AGENTS §3-33) · 1단계 구현 `feat/calendar`(§9).** 아래 §0~§8은 결정 전 시안 기록이고, 실제 구현과 다른 곳은 §9가 우선이에요.
> 처음 요청: 로드맵 4번(AGENTS §3-23b) "증시 캘린더" — 한국 지표 = 한국은행 ECOS, 미국 지표 = FRED 발표 일정, 금통위 · FOMC = 1년치 직접 입력, 기업 일정 = OpenDART, 중요도 별 = 자체 기준, **Cloudflare $5 말고 추가 요금 0**. 2026-11-15 17:21 추가(§3-32): 금융위원회 **주식발행정보(의무보호예수 반환)** · **주식배당정보**도 캘린더 원천으로.
> 시제품: [`prototypes/calendar/`](../../prototypes/calendar/) — 빌드 밖, 예시 데이터만(`fixture.js`), `?v=a|b|c`. 스크린샷 `qa/shots/calendar/`(§5-5).
> 위에 있는 규칙: [`design.md`](design.md)(승인). 같이 보는 문서: [`disclosure.md`](disclosure.md)(OpenDART 예산), `datago.md`(공공데이터포털 구현 메모, 다른 에이전트가 작성 예정).
> 이 문서의 사실은 모두 2026-11-15 KST에 원천을 직접 열어 확인했어요. 대괄호 번호 `[S1]`은 맨 아래 §8 출처 목록이에요. **확인하지 못한 것은 "확인 필요"라고 적었어요.**

## 0. 한 줄 요약

- **ECOS에는 발표 일정 API가 없어요.** 6개 서비스(통계표 목록 · 항목 · 조회 · 100대 지표 · 메타 · 용어)뿐이고, 일정은 **한국은행 누리집의 "통계공표일정" 페이지**(공표 시각까지, 1년치)에만 있어요 → 그 페이지를 하루 한 번 읽고, ECOS 키는 "발표된 뒤 값"에 써요(2단계).
- **FRED는 `fred/release/dates`에 `include_release_dates_with_no_data=true`를 줘야 앞으로의 날짜가 나와요**(기본값은 빼요). 시각은 API에 없어서 발표별 시각 표를 따로 둬요.
- **2027 금통위**: 한국은행 결정회의 목록 페이지(2027년)는 아직 비어 있고, 일정은 **언론 보도(SBS Biz 2026-10-29)로만** 확인 — 한국은행 페이지에 올라오면 넣어요. **2027 FOMC**는 연준 달력에 있어요(회의마다 "직전 회의에서 확정").
- 기업 일정은 **이벤트마다 원천을 나눠요**: 무상 · 유상증자 = DART 구조화 API(당일) · 배당 = 금융위 구조화(다음 영업일 13시 뒤) + DART 당일 예고 · 보호예수 = 금융위만 · 주총 · IR · 실적 예고 = DART 원문 읽기.
- **화면 추천 A — "일정" 탭**(주 띠 + 날짜별 목록, PC는 월 달력 + 7일 목록). B는 뉴스 카드의 탭, C는 머리글 키 → 시트.
- 예산: OpenDART 평소 하루 +60~190번 · 바쁜 날 상한 800번(한도 20,000, 지금 공시 배지 약 1,729번), FRED 13번, 한국은행 페이지 1~2번, 금융위 API마다 ≤ 50번(한도 10,000) · Cloudflare 포함 사용량의 몇 % 안(§3-4).

## 1. 원천별 결론

| 일정 | 원천 | 날짜를 주는 곳 | 시각 | 새로 고침 | 확인 |
|---|---|---|---|---|---|
| 한국 지표(한국은행 통계) | 한국은행 통계공표일정 페이지 | HTML 표(날짜 · 공표 시각 · 통계명 · 변경일시) | 있음(KST) | 하루 1번 | 2026년 127건 ✓, 2027년 아직 없음 [S3] |
| 한국 지표 값(2단계) | ECOS `KeyStatisticList` · `StatisticSearch` | — (값과 기간만) | — | 발표 날만 | sample 키로 응답 모양 ✓ [S1] |
| 미국 지표 | FRED `fred/release/dates` | JSON `{release_id, date}` | **없음** → 표 | 하루 1번 | 문서 ✓ [S10][S11], 달력 페이지로 2026 날짜 · 시각 ✓ [S14] |
| 금통위 | 직접 입력(`web/calendar.json`) | 한국은행 결정회의 목록 | — | 1년에 1번 | 2026 ✓ [S5], 2027 보도만 [S6] |
| FOMC | 직접 입력 | 연준 FOMC 달력 | 성명 2:00 p.m. ET | 1년에 1번 | 2026 · 2027 ✓ [S7][S8] |
| 휴장 · 특별 운영 | 직접 입력 | 거래소 공지(자동 수집 막힘) | — | 공지 때 | §2-4 |
| 선물 · 옵션 만기 | 규칙으로 계산 | 거래소 상품 명세 | 마지막 거래일 15:20 마감 | — | ✓ [S27][S28] |
| 무상 · 유상증자 일정 | OpenDART `fricDecsn` · `pifricDecsn` · `estkRs` | 구조화 필드 | — | 공시 당일 | 문서 ✓ [S17]~[S20] |
| 주총 · IR · 실적 예고 · 배당 결정 | OpenDART `list.json` 제목 → `document.xml` 원문 | 원문 안 글 | 원문에 있으면 | 공시 당일 | 제목 실례 ✓(저장소 응답), 원문 읽기 실측 필요 |
| 배당 기준일 · 지급일 · 금액 | 금융위 `getDiviInfo_V2` | 구조화 필드 | — | 다음 영업일 13시 뒤 | 명세 ✓ [S24], 실제 응답은 키가 Worker에만 있어 미확인 |
| 보호예수 해제 | 금융위 `getLockUpRetuInfo_V3` (+ `getStocIssuStat_V3`) | 구조화 필드 | — | 다음 영업일 13시 뒤 | 명세 ✓ [S23], **앞으로의 날짜가 나오는지 미확인** |

## 2. 원천

### 2-1. 한국 지표 — ECOS에는 일정 API가 없어요

- ECOS Open API가 주는 서비스는 6개예요: `StatisticTableList`(서비스 통계 목록) · `StatisticItemList`(통계 세부항목 목록) · `StatisticSearch`(통계 조회) · `KeyStatisticList`(100대 통계지표) · `StatisticMeta`(통계 메타 DB) · `StatisticWord`(통계 용어 사전) [S1]. 공개 `sample` 키로 다섯을 불러 응답 모양을 확인했고(아래), 없는 서비스 이름(`ReleaseSchedule`, `StatisticCalendar`)은 **HTTP 503**이 돌아와요 [S1].
  - `KeyStatisticList` 행 = `{CLASS_NAME, KEYSTAT_NAME, DATA_VALUE, CYCLE, UNIT_NAME}` — `CYCLE`은 값의 기간(예 `20261113`)이지 다음 발표일이 아니에요(100대 지표 101개).
  - `StatisticItemList` 행에 `START_TIME · END_TIME · DATA_CNT`(있는 기간)만, `StatisticSearch` 행에 `TIME · DATA_VALUE`만 — **예정일 필드는 어디에도 없어요.**
- **대신**: 한국은행 누리집 "월간통계 공표일정" `https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldr.do?menuNo=200775` [S3]가 그해 전체를 한 표로 줘요(2026년 127건, `?date=2026-12`처럼 달을 바꿔도 같은 1년 표). 열: 공표일 · **공표 시각**(`6:00` · `8:00` · `12:00`) · 통계명(기간 포함, 예 "2026년 11월 소비자동향조사 결과") · 비고(`변경일시 : 2026-01-30 00:00`처럼 바뀐 이력). 통계별 보기 `listKnd.do?menuNo=200776`도 있어요. `robots.txt`가 `/portal/`을 허용해요 [S4].
  - 남은 2026년 예: 11-18 12:00 3/4분기 가계신용(잠정) · 11-20 06:00 10월 생산자물가지수(잠정) · 11-24 06:00 11월 소비자동향조사 · 11-25 06:00 기업경기조사 · ESI · 12-08 08:00 10월 국제수지(잠정) · 12-09 08:00 3/4분기 국민소득(잠정) · 12-15 06:00 11월 수출입물가 · 12-29 06:00 12월 기업경기조사 [S3].
  - **2027년 표는 아직 없어요**(2026-11-15에 `date=2027-01`을 열어도 2026년 표) [S3]. 언제 올라오는지는 확인 못 함 → Worker가 매일 읽다가 생기면 자동으로 들어와요.
- **ECOS 키(`ECOS_KEY`)의 쓰임**: 2단계 "발표됨 + 값"(예: 국제수지 발표 시각이 지나면 `StatisticSearch`로 새 기간 값이 생겼는지 보고 "발표됨 · 값" 표시). 1단계 캘린더에는 필요 없어요.
- 한도 · 약관: ECOS는 숫자 한도를 밝히지 않고 "비정상적인 접근이나 **허용량을 초과하는 트래픽** 발생시 … 사전 통보없이 인증키 사용이 중단될 수 있음"이라고만 해요 [S2]. 이용약관(2014-11-07 시행)은 인증키 신청 창에만 있어 본문을 읽지 못했어요 → 출처는 "한국은행 경제통계(ECOS)"로 언제나 적어요.
- **ECOS에 없는 한국 지표**(한국은행 일정표에 없음): 소비자물가동향 · 고용동향 · 산업활동동향(국가데이터처, 옛 통계청) — 일정은 국가데이터처 "통계공표일정"과 KOSIS "국가통계 공표일정" 페이지에 있고 [S36], KOSIS Open API에도 일정 서비스는 없어요(통계목록 · 통계자료 · 대용량 · 통계설명 · 통계표설명 · 통합검색 · 주요지표) [S36]. **넣을지 사용자 결정(§6).** 넣는다면 한국은행처럼 페이지를 하루 한 번 읽거나 1년치 직접 입력.

### 2-2. 미국 지표 — FRED

- 경로 [S10][S11]
  - `GET https://api.stlouisfed.org/fred/release/dates?release_id=<id>&file_type=json&realtime_start=<오늘−7>&realtime_end=<오늘+400>&include_release_dates_with_no_data=true&sort_order=asc` → `{release_dates:[{release_id, date}]}`. `limit` 최대 10,000, 기본 정렬 오름차순.
  - `GET …/fred/releases/dates`(모든 발표 한 번에) — `limit` 최대 1,000, 기본 `realtime_start` = 올해 1월 1일, 결과에 `release_name`도. 발표가 수백 개라 한 번에 넘칠 수 있어서 **발표별 `release/dates`를 13번**이 단순해요.
  - **`include_release_dates_with_no_data`의 기본값 `false`는 "FRED 발표 달력에 있을 수 있는 앞으로의 날짜를 뺀다"** — 앞으로의 일정을 받으려면 꼭 `true` [S10][S11].
  - FRED 자신도 "발표 날짜는 자료 원천이 정한 것이고 FRED에 자료가 올라오는 때와 다를 수 있다"고 적어요 [S10].
- 시각: API에는 날짜만 있어요. FRED 발표 달력 페이지는 시각을 보여 주고 "**All times are US Central Time**"이라고 적어요 [S14]. → 발표별 **미국 동부 시각 표**를 `web/calendar.json`에 두고 Worker가 `Intl`(`America/New_York` → `Asia/Seoul`)로 바꿔요. 서머타임 경계는 계산이 알아서(예: 08:30 ET = 3~11월 21:30 KST, 11~3월 22:30 KST).
- 쓸 발표(release_id — FRED 달력 페이지 제목으로 확인) [S14]: 10 Consumer Price Index · 50 Employment Situation · 53 Gross Domestic Product · 54 Personal Income and Outlays · 46 Producer Price Index · 9 Advance Monthly Sales for Retail and Food Services · 192 JOLTS · 13 G.17 Industrial Production · 91 Surveys of Consumers · 180 Unemployment Insurance Weekly Claims · 27 New Residential Construction · 97 New Residential Sales · 11 Employment Cost Index.
  - 2026년 남은 큰 것(달력 페이지, 중부시간) [S14]: 고용보고서 12-04 7:30 am · CPI 12-10 7:30 am · PPI 12-15 7:30 am · 소매판매 11-17 · 12-16 7:30 am · GDP · PCE 11-25 · 12-23 7:30 am · JOLTS 12-01 9:00 am.
  - 같은 발표가 한 주에 두 번 잡힌 경우가 있어요(예: New Residential Construction 11-18 7:30 · 11-25 9:00) — 원천대로 보여 줘요.
  - FRED 달력에서 일부 시각(예: G.17 10:15 am CT, Surveys of Consumers 10:00 am CT)은 내가 아는 관례와 달라 **표를 만들 때 원천 기관 일정으로 한 번 더 확인 필요**.
  - `release_id` 101 "FOMC Press Release"는 거의 매일 날짜가 있어(2026년 365건) 회의 일정으로 쓸 수 없어요 [S14] → FOMC는 직접 입력.
- 한도 · 약관: **분당 120번**, 넘으면 429, 지키지 않으면 일시 차단 [S12]. 화면에 **"This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."** 문구 필수, 세인트루이스 연준 로고 금지, FRED의 핵심 경험을 대체하는 앱 금지, 제3자 저작권 시리즈는 개인 용도 밖이면 원 소유자 허락 [S13]. 캘린더는 날짜만 쓰고 시리즈 값을 옮기지 않아요.

### 2-3. 금통위 · FOMC — 1년치 직접 입력

**한국은행 통화정책방향 결정회의** (`https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2026`) [S5]

| 2026 | 01-15(목) · 02-26(목) · 04-10(금) · 05-28(목) · 07-16(목) · 08-27(목) · 10-22(목) · **11-26(목)** |
|---|---|
| 2027 | **한국은행 페이지(`pYear=2027`)는 아직 빈 목록** [S5]. 보도: 2026-10-29 금통위가 "2027년 금융통화위원회 정기회의 개최 예정일"을 의결 — 01-14(목) · 02-25(목) · 04-09(금) · 05-27(목) · 07-15(목) · 08-26(목) · 10-15(금) · 11-25(목), 금융안정회의 03-25 · 06-23 · 09-23 · 12-23 [S6]. **한국은행 원문을 찾지 못해 "보도 기준 · 예정"으로만 넣고, 페이지에 올라오면 확정**해요. |

- 의사록: "회의일로부터 2주 경과 후 첫 화요일"에 게시, 금융 · 경제 이슈는 D+7 [S5] → 규칙으로 계산(11-26 회의 → 12-15). 결정 발표 시각은 원천에서 확인하지 못해 **날짜만** 보여요.

**FOMC** (`https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`, 페이지 "Last Update: November 12, 2026") [S7]

| 2026 | 01-27~28 · 03-17~18* · 04-28~29 · 06-16~17* · 07-28~29 · 09-15~16* · 10-27~28 · **12-08~09\*** (\* 경제전망 SEP) |
|---|---|
| 2027 | 01-26~27 · 03-16~17 · 04-27~28 · 06-08~09 · 07-27~28 · 09-14~15 · 10-26~27(표에 "Monetary Policy Strategy Meeting") · 11-16~17 — 아직 SEP 표시 없음. 2028년 첫 회의 01-25~26. "**각 회의 날짜는 바로 앞 회의에서 확정될 때까지 잠정**" [S7] |

- 성명은 **2:00 p.m. ET**(예: 2026-10-28 성명 "For release at 2:00 p.m. EDT") [S8] → 한국 시간 다음 날 03:00(서머타임) / 04:00. 2026-12-09 → **12-10(목) 04:00**, 2027-01-27 → 01-28 04:00, 03-17 → 03-18 03:00 … 11-17 → 11-18 04:00(Intl 계산).
- 의사록: "결정일 3주 뒤" [S7], 2:00 p.m. ET(예: 2026-10-07 공개 9월 의사록 "For release at 2:00 p.m. EDT") [S9] → 12월 회의 의사록 12-30 → 12-31 04:00 KST(규칙, "예정").

### 2-4. 휴장 · 특별 운영 · 선물옵션 만기

- **거래소 휴장일 페이지는 자동으로 못 받아요**: `open.krx.co.kr` 휴장일 화면의 데이터 호출이 이 환경에서 "Access Denied" [S34]. → 1년치 **직접 입력**(거래소 공지 확인). 공휴일 목록을 자동으로 받으려면 공공데이터포털 "한국천문연구원 특일 정보"가 후보지만 **승인 목록(§3-32)에 없어요**.
- 2026년에 바뀐 것 — 직접 입력 표에 꼭 넣을 것:
  - 노동절(5-1) · 제헌절(7-17)이 2026년부터 법정 공휴일 [S31]. 거래소는 6-3 지방선거일 · 7-17 제헌절에 증권 · 파생(야간 포함) · 일반상품 시장을 휴장 [S30].
  - 수능일(2026-11-19) [S32]: 정규장 **10:00~16:30**, 애프터마켓 17:00~20:00, 주식 · 금리 파생은 한 시간씩 늦춤(최종거래일 상품 16:20 마감), 통화상품 · 금선물은 개장만 늦추고 15:45 마감 [S33].
  - 연말: 2025-12-31을 휴장일로 지정, 새해 첫 거래일 **10:00 개장**(프리마켓 없음, 마감은 그대로) [S29]. 2026-12-31 공지는 아직 확인 못 함 → "예정"으로 넣고 공지 뒤 확정.
  - 명절 전날 파생 야간거래 휴장(2026-09-23 추석 전날 사례) [S35] — 캘린더엔 "야간거래 휴장" 작은 표시로.
- **2027년 휴장일은 거래소 공지 전**(보통 연말에 나와요 — 시기 확인 못 함).
- 만기(코스피200) [S27][S28]
  - 선물: 결제월 **두 번째 목요일**이 마지막 거래일, 그날 정규장 08:45~**15:20**.
  - 옵션 월물: 매월 두 번째 목요일. 위클리: **월요일물**(휴장이면 뒤로) · **목요일물**(둘째 목요일 제외, 휴장이면 앞으로). 월요일물 2023-07-31, 목요일물 2019-09-23 상장.
  - 그래서 3 · 6 · 9 · 12월 둘째 목요일 = 선물 · 옵션 동시 만기: **2026-12-10**, 2027-03-11 · 06-10 · 09-09 · 12-09(계산).
  - 월물 · 선물 마지막 거래일이 휴장일과 겹칠 때의 규칙은 명세 페이지에 없어요 → **확인 필요**(그런 날은 직접 입력 표로 덮어써요).

### 2-5. 기업 일정 — OpenDART

공통: 키당 하루 **약 20,000번**(오류 `020`의 설명) [S15], 공시 배지(§3-29)가 이미 약 1,729번/일을 써요.

**찾기** — `list.json` [S15]: `bgn_de` · `end_de` · `corp_code`(없으면 기간 3개월 제한) · `pblntf_ty`(A 정기 · B 주요사항 · C 발행 · D 지분 · E 기타 · I 거래소 …) · `pblntf_detail_ty`(B001 주요사항보고서 · C001 증권신고(지분증권) · E006 주주총회소집보고서 · I001 수시공시 · I002 공정공시 · I003 시장조치/안내 …) · `page_count` 최대 100. **제목 필터가 없어서** 오늘 행은 공시 배지 스냅숏 `dart:today`(이미 받아 둔 것)에서 제목으로 골라요 → 추가 호출 0.

제목 실례(저장소에 저장된 실제 OpenDART 응답 `qa/stock/fixtures/raw/{005930,196170}/dart.json`):

| 이벤트 | 코스피(접수번호 8xx) | 코스닥(9xx) | 날짜를 얻는 법 |
|---|---|---|---|
| 배당 결정 | `현금ㆍ현물배당결정` (005930, 2026-10-29) | — | 원문(`document.xml`) |
| 배당 기준일 결정 | `현금ㆍ현물배당을위한주주명부폐쇄(기준일)결정`(회사 공시 목록에서 본 표기, OpenDART로 실측 필요) | `주주명부폐쇄기간또는기준일설정` (196170) | 원문 |
| IR | `기업설명회(IR)개최(안내공시)` (005930) | `기업설명회(IR)개최` (196170) | 원문 |
| 실적 발표 예고 | `결산실적공시예고(안내공시)`(회사 공시 목록에서 본 표기, 실측 필요) | 같은 이름 추정 — 실측 필요 | 원문 |
| 무상증자 | `주요사항보고서(무상증자결정)` (196170, `[기재정정]` 붙은 정정본 포함) | 같음 | **`fricDecsn` 구조화** |
| 유상증자 | `주요사항보고서(유상증자결정)` (196170) | 같음 | 결정 API엔 일정 없음 → 증권신고서 `estkRs` |
| 권리락 | — | `권리락 (무상증자)` (196170, 2026-08-04, 시장본부 공시) | 공시일 = 그 사실 |
| 주총 | `주주총회소집결의` · `주주총회소집공고`(회사 공시 목록에서 본 표기, 실측 필요) | | 원문 |

- 제목에 공백이 여러 칸 붙어 와요(`기업설명회(IR)개최               `) → 공백 정리 후 비교.

**구조화 API** (회사 하나 · 기간 단위, `corp_code` 필수 — 찾기에서 나온 회사만 불러요)
- 무상증자 결정 `fricDecsn.json` [S18]: **`nstk_asstd` 신주배정기준일 · `nstk_lstprd` 신주의 상장 예정일** · `nstk_dividrk` 배당기산일 · `nstk_dlprd` 신주권교부예정일 · `nstk_ascnt_ps_ostk` 1주당 배정 주식수 · `bddd` 이사회결의일.
- 유무상증자 결정 `pifricDecsn.json` [S19]: 같은 필드를 `piic_` · `fric_` 앞머리로(무상 쪽 `fric_nstk_asstd` 등).
- 유상증자 결정 `piicDecsn.json` [S17]: 신주 수 · 자금 목적 · 증자방식 · 공매도 기간뿐 — **일정 필드 없음**.
- 증권신고서(지분증권) `estkRs.json` [S20], 묶음 "일반사항": **`sbd` 청약기일 · `pymd` 납입기일 · `sband` 청약공고일 · `asand` 배정공고일 · `asstd` 배정기준일** · `rpt_rcpn` 연결된 주요사항보고서 접수번호. 상장 예정일 필드는 없어요(원문).
- 공시서류원본파일 `document.xml` [S16]: 접수번호로 **ZIP 파일**(원문 XML) — 주총 일시 · 배당 기준일 · IR 일시 · 실적 발표 예정일은 여기서 글로 읽어요. Worker에서 ZIP을 풀 수 있는지(`DecompressionStream('deflate-raw')`)와 원문 서식별 정규식은 **첫 구현 때 실측**(1단계는 구조화 API만, 원문 읽기는 2단계로 나눠도 돼요 — §6).
- 출처 표기: 지금처럼 "공시: 금융감독원 DART (제목 · 링크만)" 줄에 "· 일정"을 더해요.

### 2-6. 기업 일정 — 금융위원회(공공데이터포털, `DATA_GO_KR_KEY`)

공통 [S23][S24]: 갱신 **하루 1번**, "금융위원회에서 제공하는 모든 서비스는 실시간이 아니며, 데이터 갱신은 **기준일자로부터 영업일 하루 뒤 오후 1시 이후**", "금요일 데이터는 차주 월요일"(월요일이 공휴일이면 다음 영업일). 원자료는 **한국예탁결제원**, 이용허락 **공공누리 제2유형(출처표시 + 상업적 이용금지)**. 트래픽 **개발계정 API마다 하루 10,000번**(운영계정은 활용사례 등록 시 증설 신청). 무료 · 자동승인. FAQ `https://www.fsc.go.kr/in060501`.

**주식발행정보 `GetStocIssuInfoService_V3`** (`https://apis.data.go.kr/1160100/GetStocIssuInfoService_V3`) [S23]
- 오퍼레이션 4개: 종목기본정보 `getItemBasiInfo_V3` · 주식발행내역 · **의무보호예수반환정보 `getLockUpRetuInfo_V3`** · **주식발행현황 `getStocIssuStat_V3`**.
- `getLockUpRetuInfo_V3` 요청: `serviceKey · pageNo · numOfRows · resultType(json) · basDt` + `crno`(법인등록번호) · `stckIssuCmpyNm`. 설명은 "필수 파라미터 없음 — 안 주면 `basDt`가 가장 최신 날짜"(스웨거는 `basDt` 필수로 표시) [S23].
- 응답: `basDt · crno · isinCd · itmsShrtnCd · stckIssuCmpyNm · scrsItmsKcdNm(보통주/우선주) · lstgDcdNm · lkupRegDt(의무보호예수 등록일) · lkupRegStckCnt · rsrnDt · rsrnStckCnt(반환 주식 수) · afrsRsqtCnt(반환 후 잔량) · stckLblHoldRcdNm(의무보유 사유) · lblProtTsumIssuStckCnt`.
- ⚠ 명세가 `rsrnDt`를 "유가증권등을 **반환한** 일자"(과거형)로 적어요 → **앞으로의 반환 예정이 나오는지, 반환이 일어난 날(T+1)에야 나오는지 모름.** 첫 구현의 첫 일: `basDt` 최신 · 회사 지정 없이 한 쪽을 받아 `rsrnDt > basDt`인 행이 있는지 봐요. 없으면 캘린더에서는 **"어제 풀림" 기록**으로만 쓰고(앞날 예고 아님), 미리 알리려면 다른 원천이 필요해요(§6).
- 비율: `getStocIssuStat_V3` → `onskTisuCnt`(보통주 총발행수) · `pfstTisuCnt`(우선주) [S23]. 별 기준 = `rsrnStckCnt ÷ onskTisuCnt`(우선주 행이면 `pfstTisuCnt`).

**주식배당정보 `GetStocDiviInfoService_V2`** (`https://apis.data.go.kr/1160100/GetStocDiviInfoService_V2`) [S24]
- `getDiviInfo_V2` 요청: `serviceKey · pageNo · numOfRows · resultType` + 선택 `basDt · crno · stckIssuCmpyNm`.
- 응답: `basDt · crno · isinCd · stckIssuCmpyNm · **dvdnBasDt**(배당 기준일) · **cashDvdnPayDt**(현금배당 지급일) · stckHndvDt(주식 교부일) · stckDvdnRcdNm(배당 사유) · scrsItmsKcdNm(주식 종류) · **stckGenrDvdnAmt**(1주당 현금배당) · stckGrdnDvdnAmt(차등) · stckGenrCashDvdnRt · stckGenrDvdnRt · cashGrdnDvdnRt · stckGrdnDvdnRt · stckParPrc · stckStacMd(결산월일) · trsnmDptyDcdNm(명의개서대리인)`.
- `cashDvdnPayDt`도 "지급**한** 일자"로 적혀 있어 같은 확인이 필요해요(기준일 전에 행이 생기는지).

**연결표**: 금융위 행은 `crno` · `isinCd`로 와요. 종목 코드는 **KRX상장종목정보 `getItemInfo_V2`**(`srtnCd · isinCd · crno · itmsNm · corpNm · mrktCtg`) [S25]로 만든 공용 연결표(다른 에이전트가 Worker 도우미로 만드는 중, §3-32 ⑥)를 그대로 써요. `isinCd → srtnCd`를 1순위, `crno`는 같은 회사의 보통주 · 우선주를 묶을 때.

**목록에 없던 후보**: 금융위원회_**주식권리일정정보** `GetStocRighScheService_V2` `getRighExerReasSche_V2` — 배당 · 무상증자 · 유상증자 · 감자 등 사유별 **권리행사 시작/종료일 · 명부폐쇄 시작/종료일** [S26]. 캘린더(권리락 · 배당 기준일)에 딱 맞지만 §3-32 승인 목록에 없어요 → 신청할지 §6.

### 2-7. 이벤트마다 어느 원천을 쓸까 (추천)

| 이벤트 | OpenDART (공시 당일) | 금융위 (다음 영업일 13시 뒤, 구조화) | **추천** |
|---|---|---|---|
| 현금배당 기준일 · 지급일 · 금액 | 제목으로 당일 발견, 날짜 · 금액은 원문 | `dvdnBasDt · cashDvdnPayDt · stckGenrDvdnAmt`, 주식 종류별 | **금융위가 기준값**. DART는 당일 "배당 결정 공시" 행(원문에서 날짜를 읽으면 그 날에, 못 읽으면 공시일에 링크로) → 금융위 행이 오면 같은 종목 · 같은 기준일 행을 바꿔 끼워요 |
| 보호예수 해제 | 구조화 API 없음 | `rsrnDt · rsrnStckCnt · afrsRsqtCnt` + 발행주식수 | **금융위만**(앞날 예정이 나오는지 먼저 확인) |
| 무상증자 기준일 · 신주 상장일 | `fricDecsn` · `pifricDecsn` 구조화 | 승인 목록엔 없음(권리일정정보에 있음) | **DART** |
| 유상증자 청약 · 납입 · 배정기준일 | `estkRs` 구조화 | 주식발행내역은 발행 뒤 | **DART** |
| 권리락 | 시장본부 공시 제목(`권리락 (무상증자)`) | — | **DART 제목**(계산하지 않아요) |
| 주주총회 | 소집결의 · 소집공고 원문 | — | **DART**(원문 읽기, 2단계) |
| 실적 발표 · IR | 결산실적공시예고 · 기업설명회(IR)개최 원문 | — | **DART**(원문 읽기, 2단계) |

- 두 원천이 같은 일을 말하면 **같은 `id`로 합쳐요**: `corp:<코드>:<종류>:<날짜>` — 금융위가 들어오면 `src`를 `fsc`로 바꾸고 DART 링크는 `r`로 남겨요.
- 금융위의 "하루 늦음"은 화면에 적어요: 출처 줄 "금융위원회(한국예탁결제원 자료, 다음 영업일 반영)", 자세히 "다음 영업일 13시 이후 반영".

### 2-8. 한도 · 약관 · 출처 표기

| 원천 | 한도 | 표기 · 약관 | 근거 |
|---|---|---|---|
| ECOS | 숫자 없음, 과다 트래픽이면 키 중단 | "한국은행 경제통계(ECOS)" | [S2] |
| 한국은행 공표일정 페이지 | 페이지 1개/일 · `robots` `/portal/` 허용 | "한국은행 경제통계 공표일정" | [S3][S4] |
| FRED | 120번/분, 초과 429 · 일시 차단 | **FRED® API 고지 문구 필수**, 로고 금지 | [S12][S13] |
| OpenDART | 약 20,000번/일(키당) | "금융감독원 DART" (제목 · 링크만) | [S15] |
| 금융위 · 공공데이터포털 | 개발계정 10,000번/일(API마다) | 공공누리 제2유형: **출처표시 + 상업적 이용금지**, 원자료 한국예탁결제원 | [S23][S24] |
| 연준 · 한국은행 회의 일정 | 손으로 1년 1번 | 원문 링크 | [S5][S7] |
| Cloudflare Workers Paid | 요청 1천만/월 · CPU 3천만 ms/월 · cron 1회 CPU 최대 15분 | — | [S37] |
| Workers KV (Paid) | 읽기 1천만 · 쓰기 1백만 · 삭제 1백만 · list 1백만/월 · 저장 1GB | — | [S38] |

출처 줄(페이지 아래, "투자 판단의 근거로 쓰지 마세요." 위 — §3-30): `일정: 한국은행 경제통계 공표일정 · 미국 지표 FRED®(고지 문구) · 금통위 · FOMC · 휴장은 한국은행 · 연준 · 한국거래소 공지를 보고 직접 넣어요 · 회사 일정: 금융감독원 DART, 금융위원회(한국예탁결제원 자료, 다음 영업일 반영)` + `시각은 모두 한국 시간이에요. 발표 일정은 원천 사정으로 바뀔 수 있어요.`

## 3. 서버 설계 (시안 당시 — 실제 구현은 §9)

### 3-1. 경로

`GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD[&kinds=kr,us,cb,mkt,corp][&codes=c1,c2,…]`

- 날짜는 KST. 기본 `from` = 이번 주 월요일, `to` = `from + 13일`. 한 번에 **최대 42일**(월 달력 6주), 오늘 ±400일 밖이나 형식이 틀리면 400.
- `kinds` 생략 = 전부. `codes`(최대 300)는 **회사 일정만** 그 종목으로 좁힐 때(종목 페이지 · 관심 보기). 화면은 보통 `codes` 없이 받아 관심종목 표시는 기기에서 해요(관심종목을 서버에 보내지 않아요).
- 응답

```json
{
  "asOf": "2026-11-16T09:10:00+09:00",
  "from": "2026-11-16", "to": "2026-11-29", "tz": "Asia/Seoul",
  "days": { "2026-11-19": { "note": "수능 · 정규장 10:00–16:30", "kind": "special" },
            "2026-12-31": { "note": "휴장 · 연말", "kind": "closed", "tentative": true } },
  "events": [
    { "id": "fred:10:2026-12-10", "d": "2026-12-10", "t": "22:30", "k": "us", "star": 3,
      "title": "미국 소비자물가(CPI)", "src": "fred", "orig": { "d": "2026-12-10", "t": "08:30", "tz": "America/New_York" } },
    { "id": "corp:900003:lockup:2026-11-19", "d": "2026-11-19", "t": null, "k": "corp", "star": 2,
      "c": "900003", "title": "보호예수 해제 412만 주", "sub": "상장주식의 6.1%", "src": "fsc", "pct": 6.1 }
  ],
  "groups": [ { "d": "2026-12-31", "k": "corp", "type": "div-rec", "n": 37, "codes": ["…"] } ],
  "sources": { "bok": {"ok": true, "at": "…"}, "fred": {"ok": true, "at": "…"}, "dart": {"ok": true, "at": "…"},
               "fsc": {"ok": true, "at": "…", "basDt": "2026-11-13"}, "manual": {"v": "2026-11-15"} },
  "stale": false
}
```

- 이벤트 필드: `id`(원천 · 종류 · 날짜로 고정 — 같은 일은 같은 id) · `d`(KST 날짜) · `t`(KST `HH:MM` 또는 `null` = 종일) · `k`(`kr` 한국 지표 · `us` 미국 지표 · `cb` 금리 · `mkt` 시장 · `corp` 기업) · `star`(서버 기본 1~3, §4) · `title` · `sub?` · `c?`(종목 코드) · `src`(`bok · fred · manual · rule · dart · fsc`) · `url?`(원문) · `r?`(DART 접수번호) · `orig?`(미국 원래 시각) · `tentative?`(예정 — 공지 전 · 규칙 계산) · `chg?`(`{d, t}` 바뀌기 전 일정, 7일 동안) · `pct?` · `amt?`(1주당 배당 원).
- **같은 날 같은 종류 회사 일정이 12개를 넘으면 묶어요**(`groups`) — 결산 배당 기준일 · 주총 몰리는 날의 응답 크기를 막아요. 화면은 한 줄("결산 배당 기준일 · 37개 종목")로 보여 주고 누르면 펼쳐요.
- 캐시: `cache-control: public, s-maxage=600, stale-while-revalidate=600` + 약한 ETag(공시 배지와 같은 방식, `asOf`만 빼고 같으면 304).

### 3-2. 조각과 KV (`REPLAY`, `list` 안 씀)

| 조각 | 어디서 | 저장 | 새로 고침 |
|---|---|---|---|
| 직접 입력(금통위 · FOMC · 휴장 · 특별 운영 · 발표 시각 표 · 별 표 · 제목 → 별) | `web/calendar.json`(저장소, ASSET_BASE로 읽음) | 엣지 캐시 10분 | 커밋하면 끝 |
| 규칙(만기 · 의사록 · 첫 거래일) | Worker 계산 | — | 요청 때 |
| 한국은행 공표일정 | 페이지 1개 → 표 파싱 | `cal:bok:<연도>` ≈ 15KB | 하루 1번(06:05 이후 첫 요청) + 실패 시 30분 쉼 |
| FRED | 발표 13개 × `release/dates` | `cal:fred` ≈ 10KB | 하루 1번 |
| DART 회사 일정 | `dart:today`(공시 배지 스냅숏)에서 제목 고르기 → 구조화 API(·원문) | `cal:corp:<YYYYMM>`(달별, 바쁜 달 ≈ 200KB) · `cal:dart:seen:<YYYYMMDD>`(처리한 접수번호) | 공시 배지가 스냅숏을 바꿀 때 같이(추가 `list.json` 0) + 아침 09:05 어제 저녁분 마무리 |
| 금융위 배당 · 보호예수 | `getDiviInfo_V2` · `getLockUpRetuInfo_V3`(+ 발행현황) | `cal:fsc:<op>:<basDt>` → `cal:corp:<YYYYMM>`에 합침 | 영업일 13:40 · 15:40(다시 시도) — 기존 매분 cron(평일 09:00~16:59) 안에서 |
| 쉬는 표시 | 원천마다 | `cal:cool:<src>` | 실패 때 |

- 새 cron · 새 DO · 새 KV 이름공간 없음(기존 `* 0-7 * * 2-6` 안의 특정 분에만 일을 끼워요 — 그 밖은 요청 때 `ctx.waitUntil`로).
- 키는 요청 URL에만(공시 배지와 같은 규칙) — KV · 응답 · 로그 · 오류 문구에 남지 않아요.

### 3-3. 하루 · 한 달 호출 예산

| 원천 | 평소 하루 | 바쁜 날(1~3월 결산 · 주총) | 한도 | 비율 |
|---|---|---|---|---|
| OpenDART(캘린더 몫) | 구조화 API ≈ 10~40 + 원문 ≈ 50~150 | 원문 ≈ 400~800 (**상한 800**, 넘으면 다음 날로) | 20,000/일 | 공시 배지 1,729와 합쳐 최대 ≈ 2,600 (13 %) |
| 출시 때 한 번(지난 60일 다시 훑기) | `list.json` B · C · I 날마다 시장 2 × 쪽 수 ≈ 1,500~1,800 → 3일에 나눠 하루 ≤ 700 | | | ≤ 12 % |
| FRED | 13 | 13 | 120/분 | 하루 13번 |
| 한국은행 페이지 | 1~2 | 1~2 | 밝힌 한도 없음 | — |
| ECOS(2단계 값) | 발표 있는 날 ≤ 20 | ≤ 20 | 밝힌 한도 없음 | — |
| 금융위 배당 | 쪽 수만큼 ≈ 1~5 (+ 다시 시도) | ≈ 5~20 | 10,000/일 | < 1 % |
| 금융위 보호예수 + 발행현황 | ≈ 1~5 + 회사 수만큼 ≤ 50 | ≤ 60 | 10,000/일 | < 1 % |

Cloudflare(가족 · 지인 규모, 화면 요청 하루 ≤ 2,000번 가정): Worker 요청 ≈ 6만/월(1천만의 0.6 %) · KV 읽기 ≈ 15만/월(엣지 캐시 10분 · colo 몇 곳, 1천만의 1.5 %) · KV 쓰기 ≈ 3천/월(1백만의 0.3 %) · CPU — 원문 ZIP 풀기 · 정규식이 건당 수십 ms라고 보면 바쁜 날 800건 ≈ 40초 → 월 ≈ 0.6백만 ms(3천만의 2 %, **실측 필요**). 모두 포함 사용량 안이에요 [S37][S38].

### 3-4. 바뀐 일정 · 실패

- 같은 `id`의 날짜 · 시각이 바뀌면 `chg`에 옛 값을 7일 동안 남기고 화면은 "바뀜" 배지(중립색). 한국은행 표의 "변경일시" 비고도 같은 표시로.
- 원천 하나가 실패하면 그 조각의 지난 값을 쓰고 `sources.<src>.ok:false` + `stale:true`. 화면은 출처 줄 옆에 "미국 지표 일정 HH:MM 기준" 앰버 글자 + 다시 시도(공시 배지와 같은 실패 표현).
- 1년치 직접 입력이 끝나 가면(남은 금통위 · FOMC가 2개 이하) `sources.manual.low:true` → 운영 메모(화면에는 안 보임).

### 3-5. `web/calendar.json` (직접 입력, 사람이 고치는 파일)

```json
{ "v": "2026-11-15",
  "cb": [ { "d": "2026-11-26", "who": "bok", "title": "금통위 통화정책방향 결정", "url": "…pYear=2026" },
          { "d": "2026-12-09", "t": "14:00", "tz": "America/New_York", "who": "fed", "title": "FOMC 금리 결정", "sep": true },
          { "d": "2027-01-14", "who": "bok", "tentative": "보도 기준" } ],
  "krx": [ { "d": "2026-11-19", "kind": "special", "note": "수능 · 정규장 10:00–16:30", "open": "10:00", "close": "16:30" },
           { "d": "2026-12-25", "kind": "closed", "note": "성탄절" },
           { "d": "2026-12-31", "kind": "closed", "note": "연말", "tentative": true } ],
  "fredTimes": { "10": "08:30", "50": "08:30", "53": "08:30", "54": "08:30", "46": "08:30", "9": "08:30", "192": "10:00", "180": "08:30" },
  "stars": { "fred": { "10": 3, "50": 3, "53": 2, "54": 2, "46": 2, "9": 2, "192": 2 }, "bok": [ ["국내총생산\\(속보\\)", 3], ["국제수지", 2] ] }
}
```

## 4. 중요도 별 (자체 기준)

별은 **세 칸**(★★★ / ★★ / ★), 색은 중립(채운 별 `--fg` · `--fg2`, 빈 별 `--line2`) — 빨강 · 초록 · 앰버를 쓰지 않아요(design.md §2). 기준표는 `web/calendar.json`의 `stars`에 있어 코드 없이 바꿀 수 있어요.

| 별 | 무엇 |
|---|---|
| ★★★ | 금통위 결정 · FOMC 결정 · 미국 CPI · 미국 고용보고서 · 한국 실질 GDP 속보 · 선물옵션 동시만기(3 · 6 · 9 · 12월) · 보호예수 해제 **상장주식의 10 % 이상** |
| ★★ | 금통위 · FOMC 의사록 · 미국 PCE · PPI · 소매판매 · GDP(FRED는 속보 · 잠정을 나누지 않아 모두 ★★) · JOLTS · 한국 국제수지 · 수출입물가 · 소비자동향 · 기업경기 · 가계신용 · 국민소득 · 옵션 월물 만기 · 수능 · 첫 거래일 같은 특별 운영 · 무상증자 기준일 · 보호예수 3~10 % · 시가총액 상위 100 종목의 실적 발표 · IR · 주총 · 결산 배당 기준일 묶음 |
| ★ | 그 밖(한국 생산자물가 · 통화 및 유동성 · 가중평균금리 · 미국 주택 · 미시간대 · 실업수당 청구 · 산업생산 · 위클리 옵션 만기(기본 숨김) · 그 밖 회사 일정) |

- 화면이 더하는 것(기기에서만): **관심종목 · 보유 종목이면 +1**(최대 3). 서버는 관심종목을 몰라요.
- 서버가 더하는 것: 회사 일정은 **시가총액 상위 50**이면 +1(유니버스 순위).
- "★★ 이상만" 필터 · 위클리 만기 켜기는 화면의 필터 칩.

## 5. 화면

### 5-1. 공통 규칙 (design.md를 따라)

- **토큰만**: 글자 11 · 12 · 13 · 14 · 16 · 20px(§3, 최소 11px — 시제품 실측 11px 미만 0), 간격 `--space-*`, 모서리 `--r-*`, 높이 `--h-*`.
- **고르기**: 주 띠 = **세그먼트**(파인 트레이 + 솟은 표시, 표시는 앞 가장자리 `lead` · 뒤 `trail`, §7 ①) · 종류 = **필터 칩**(알약은 필터에만) · B의 카드 제목 = **밑줄 탭**(§7 ③).
- **앰버**: 고른 날 · 켜진 칩 · 탭 밑줄 · 포커스 · (C) 열린 키만. "오늘"은 앰버가 아니라 흰 배지, 휴장은 중립 채움 배지.
- **빨강 · 초록 0**: 캘린더에는 등락 숫자가 없어요(2단계에서 발표값을 보여도 지표 "좋음/나쁨"은 색으로 말하지 않아요).
- **움직임**: 날 바꾸면 목록 `fade`, 자세히는 휴대폰 아래에서 `open`으로 올라오고 `close`로 닫힘, 데스크톱은 가운데 떠 있는 판(`open` + `fade`). 줄이기면 모두 0ms. 키보드 ←/→로 날 이동(표시는 바로).
- **터치**: 휴대폰 줄 52px 이상, 키 40px + 가상 영역(::before)으로 44px, 칩 32px + 가상 영역. 시제품 점검: 390 · 360에서 44px 미만 0.
- **글**: 해요체, "예정"(공지 전 · 규칙 계산), "바뀜", "종일", "한국 시간"; 미국 일정은 "22:30 / 미국 08:30" 두 줄.
- 빈 상태 · 실패 · 휴장 문구: "일정이 없어요" · "고른 조건에 맞는 일정이 없어요 · 숨긴 일정 N개" · "장이 쉬어요" · "미국 지표 일정 HH:MM 기준".

### 5-2. 세 가지 시안

| | **A · 일정 탭 (추천)** | B · 뉴스 카드의 "일정" 탭 | C · 머리글 "일정" 키 → 시트 |
|---|---|---|---|
| 어디 | 시장 탭 줄에 `일정`(지표 다음) — 해외 · 지표처럼 지도 자리를 바꿔요(`#cal` 마운트, `KHCal.show()/hide()`) | 지도 아래 뉴스 카드에 `시장 뉴스 · 오늘 공시 · 일정` (`KHNews.addTab`) | 머리글 오른쪽 키(오늘 일정 수), 휴대폰 아래 시트 · PC 키에서 자라는 떠 있는 판 |
| 휴대폰 390 | 주 띠(7칸) + 칩 + 날짜별 목록, 고른 날이 맨 위 | 오늘부터 7일, **★★ 이상만**이 기본, 빈 날 숨김, "달력 전체 보기" | A와 같은 내용이 시트 안에 |
| PC 1440 | 왼쪽 월 달력(칸마다 3줄 + "+N") · 오른쪽 "고른 날부터 7일" 목록 | 카드 폭에 두 단(오늘~3일 · 4~7일) | 오른쪽 440px 판에 주 띠 + 목록 |
| 지도 위치 | 그대로(탭 줄 글자 하나 늘 뿐) | 그대로 | 그대로 |
| 찾기 쉬움 | 탭 줄은 늘 위에 붙어 있어 한 번에 | 휴대폰은 맨 아래 카드라 스크롤이 길어요 | 어디서나 한 번, 하지만 키가 작아 처음엔 안 보일 수 있어요 |
| 월 단위로 보기 | 됨(PC 월 달력, 휴대폰 주 넘기기) | 안 됨(전체 보기는 A나 C로) | 휴대폰은 주 넘기기, PC 판은 좁아 월 달력 없음 |
| 만드는 양 | 새 모듈 `src/calendar`(탭 연결은 해외 · 지표 방식 재사용) | 가장 적음(공시 탭과 같은 길) | 시트 · 떠 있는 판 새로 |
| 아쉬운 점 | 휴대폰 탭이 8개가 돼 옆으로 더 밀려요 | 지도와 함께 봐야 해서 길게 못 봐요 | 머리글 자리가 빠듯(시계 · 상태 · 설정과 경쟁) |

### 5-3. 추천: A

① 일정은 "이번 주 무엇이 있나"를 따로 보는 일이라 지도와 같은 자리를 다퉈도 괜찮고, 해외 · 지표 탭과 같은 방식이라 사용자에게 익숙해요 ② PC 1440에서 월 달력 + 7일 목록이 한 화면에 들어가요(12-10처럼 FOMC · 동시만기 · CPI가 겹치는 날이 한눈에) ③ 휴대폰은 주 띠 → 목록 → 자세히(아래 시트) 세 걸음 ④ 지도 위치 불변 ⑤ 나중에 **시장 요약 카드**(로드맵 3번)에 "오늘 · 내일 일정 2줄 → 일정 탭" 연결, **종목 페이지**에 그 종목 일정(같은 `/api/calendar?codes=`)을 붙이기 쉬워요. B는 "가장 싸게 시작"이 필요할 때의 대안이에요.

### 5-4. 자세히(공통)

제목(회사면 위에 "이름 · 코드") · 언제(KST, 미국이면 "미국 동부 12월 9일 오후 2:00 발표 → 한국 시간으로 바꿨어요") · 중요도(별 + 참고/중요/매우 중요) · 분류 · 출처(원천 이름 + 어떻게 얻었나: "FRED 발표 10번 · 날짜는 FRED, 시각은 따로 둔 표" / "OpenDART fricDecsn 값" / "다음 영업일 13시 이후 반영") · 상태(예정 · 바뀜 · 지났어요) · 왜 이 별인지 한 줄 · 버튼(원천 보기 · DART 원문 · 종목 페이지, 44px). Esc · 바깥 누름 · × 로 닫고 포커스는 누른 줄로.

### 5-5. 시제품 · 스크린샷

- 열기: `python3 -m http.server 8990 -b 127.0.0.1 -d <저장소>` → `http://127.0.0.1:8990/prototypes/calendar/index.html?v=a`(`?v=b`, `?v=c`, `?day=2026-12-10`, `?open=fomc-1209`, `?motion=reduced`, `?weekly=1`). 예시 "지금" = 2026-11-16(월) 09:12. 지표 · 금리 · 시장 일정은 §2의 실제 일정, **회사 일정은 가짜 이름**(예시바이오 · 가나전자 …).
- 스크린샷: `python3 prototypes/calendar/shots.py` → `qa/shots/calendar/`
  - `a-390.png` · `a-390-detail.png`(보호예수 자세히) · `a-360.png` · `a-1440.png` · `a-1440-detail.png`(12-10 FOMC 자세히)
  - `b-390.png` · `b-1440.png` · `c-390.png` · `c-1440.png` · 점검 결과 `check.json`
- 점검(9장 모두): 가로 넘침 0 · 콘솔 오류 0 · 11px 미만 글자 0 · 휴대폰 44px 미만 누름 영역 0.

## 6. 사용자가 정할 것 → 결정 (2026-11-15 17:52: "1 추천 2 추천 3 추천 4 추천 5 숨기기 이유? 6 신청할게 7 추천")

결정: 1 = A 일정 탭 · 2 = 넣기 · 3 = "예정"으로 먼저 · 4 = 원문 읽기는 2단계 · 5 = 기본 숨김(17:54 다시 확인) · 6 = 사용자가 신청함(승인 확인 전엔 꺼 둠) · 7 = 값 넣기(색 없이).

1. 화면: **A 일정 탭(추천)** · B 뉴스 카드 탭 · C 시트.
2. 국가데이터처 지표(소비자물가 · 고용 · 산업활동)도 넣을까요? ECOS · 한국은행 일정표엔 없어요. 넣으면 국가데이터처 공표일정 페이지를 하루 한 번 읽어요.
3. 2027 금통위: 지금은 보도(SBS Biz)로만 확인 — "예정"으로 먼저 넣고 한국은행 페이지에 올라오면 확정해도 될까요?
4. 회사 일정 1단계 범위: 구조화된 것만(무상 · 유상증자 · 배당 · 보호예수) 먼저, 원문 읽기(주총 · IR · 실적 예고)는 2단계로 — 괜찮을까요?
5. 위클리 옵션 만기는 기본 숨김(칩으로 켜기) — 괜찮을까요?
6. 금융위 **주식권리일정정보**(권리락 · 명부폐쇄 일정)를 공공데이터포털에서 추가 신청할까요? 보호예수 API가 앞날 예정을 주지 않으면 그 빈자리도 일부 메워요.
7. 2단계 "발표된 뒤 값"(ECOS · FRED 값, 색 없이)을 붙일까요?

## 7. 확인 못 한 것 · 첫 구현 때 잴 것

- 금융위 `getLockUpRetuInfo_V3` · `getDiviInfo_V2`가 **앞으로의 날짜**(반환 예정 · 배당 기준일 전)를 주는지, `basDt`가 "그날 기준 전체"인지 "그날 바뀐 것"인지, `numOfRows` 최대값 — 키가 Worker에만 있어 Worker 안에서 한 번 재요.
- OpenDART 원문 `document.xml` ZIP을 Worker에서 풀 수 있는지(`DecompressionStream('deflate-raw')`), 서식별 날짜 정규식, 건당 CPU.
- 코스피 쪽 제목(`주주명부폐쇄(기준일)결정` · `결산실적공시예고` · `주주총회소집결의`)을 OpenDART 응답으로 실측.
- FRED 달력의 일부 시각(G.17 · 미시간대)과 2027년 날짜가 언제 들어오는지.
- 한국은행 2027 공표일정 · 2027 금통위 원문 · 2026-12-31 · 2027년 거래소 휴장 공지가 올라오는 때.
- 월물 · 선물 마지막 거래일이 휴장과 겹칠 때 규칙.
- 한국은행 통화정책방향 결정 발표 시각(원천에서 찾지 못해 날짜만).

## 8. 출처 (모두 2026-11-15 KST에 확인)

- [S1] ECOS Open API 서비스 목록 `https://ecos.bok.or.kr/api/#/ServiceUse/ServiceList` · 공개 sample 키 호출 예 `https://ecos.bok.or.kr/api/KeyStatisticList/sample/json/kr/1/3` · `…/StatisticTableList/sample/json/kr/1/3` · `…/StatisticItemList/sample/json/kr/1/3/601Y002` · `…/StatisticSearch/sample/json/kr/1/3/722Y001/M/202601/202610/0101000` · 없는 서비스 `…/ReleaseSchedule/sample/json/kr/1/3` → 503
- [S2] ECOS 인증키 신청 · 이용 제한 안내(사이트 문구) `https://ecos.bok.or.kr/api/#/AuthKeyApply`
- [S3] 한국은행 월간통계 공표일정 `https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldr.do?menuNo=200775` (`&date=2026-11` · `2026-12` · `2027-01`), 통계별 `…/listKnd.do?menuNo=200776`
- [S4] `https://www.bok.or.kr/robots.txt`
- [S5] 한국은행 통화정책방향 결정회의 목록 `https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2026` · `…&pYear=2027`(빈 목록)
- [S6] SBS Biz 2026-10-29 "한은, 내년 첫 금리 결정 1월 14일…금통위 일정 확정" `https://biz.sbs.co.kr/amp/article/20000343023`
- [S7] 연준 FOMC 달력 `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- [S8] FOMC 성명 2026-10-28 `https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm`
- [S9] FOMC 의사록 공개 2026-10-07 `https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm`
- [S10] FRED `fred/releases/dates` `https://fred.stlouisfed.org/docs/api/fred/releases_dates.html`
- [S11] FRED `fred/release/dates` `https://fred.stlouisfed.org/docs/api/fred/release_dates.html`
- [S12] FRED 오류 · 한도 `https://fred.stlouisfed.org/docs/api/fred/errors.html`
- [S13] FRED API 이용약관 `https://fred.stlouisfed.org/docs/api/terms_of_use.html`
- [S14] FRED 발표 달력 `https://fred.stlouisfed.org/releases/calendar?rid=10&y=2026` (rid 50 · 53 · 54 · 46 · 9 · 192 · 13 · 91 · 27 · 97 · 11 · 180 · 101도 같은 방식)
- [S15] OpenDART 공시검색 `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001`
- [S16] OpenDART 공시서류원본파일 `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003`
- [S17] 유상증자 결정 `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020023`
- [S18] 무상증자 결정 `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020024`
- [S19] 유무상증자 결정 `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020025`
- [S20] 증권신고서(지분증권) `https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS006&apiId=2020054`
- [S23] 공공데이터포털 금융위원회_주식발행정보 `https://www.data.go.kr/data/15043423/openapi.do`
- [S24] 공공데이터포털 금융위원회_주식배당정보 `https://www.data.go.kr/data/15043284/openapi.do`
- [S25] 공공데이터포털 금융위원회_KRX상장종목정보 `https://www.data.go.kr/data/15094775/openapi.do`
- [S26] 공공데이터포털 금융위원회_주식권리일정정보 `https://www.data.go.kr/data/15059609/openapi.do`
- [S27] KRX KOSPI 200 Futures 명세 `https://global.krx.co.kr/contents/GLB/02/0201/0201040201/GLB0201040201.jsp`
- [S28] KRX KOSPI 200 Options 명세 `https://global.krx.co.kr/contents/GLB/02/0201/0201040202/GLB0201040202.jsp`
- [S29] 한국경제 2025-12-18 "거래소 '31일 휴장…내달 2일 10시 개장'" `https://www.hankyung.com/article/2025121825891`
- [S30] 비즈워치 2026-05-20 "지방선거일, 제헌절에도 주식시장 쉽니다" `https://news.bizwatch.co.kr/article/market/2026/05/20/0023`
- [S31] 위키트리 2026-04-30 노동절 · 제헌절 공휴일 `https://www.wikitree.co.kr/articles/1134548`
- [S32] 헤럴드경제 "2027학년도 수능 11월 19일 시행" `https://www.heraldk.com/article/2026062919000082154`
- [S33] SBS Biz 2026-11-05 "수능일 주식 시장 1시간 늦게 열고 1시간 늦게 닫는다" `https://biz.sbs.co.kr/amp/article/20000344409`
- [S34] KRX 휴장일 화면 `http://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp` (데이터 호출 Access Denied)
- [S35] 비즈워치 2026-09-09 "추석 연휴 전날 파생상품 야간거래 휴장" `https://news.bizwatch.co.kr/article/market/2026/09/09/0019`
- [S36] KOSIS 국가통계 공표일정 `https://kosis.kr/serviceInfo/statisPublicationList.do` · 국가데이터처(지방청) 통계공표일정 `https://www.mods.go.kr/lcofNewsPln.es?mid=a50303000000` · KOSIS Open API `https://kosis.kr/openapi/index.jsp`
- [S37] Cloudflare Workers 요금 `https://developers.cloudflare.com/workers/platform/pricing/`
- [S38] Cloudflare Workers KV 요금 `https://developers.cloudflare.com/kv/platform/pricing/`
- 저장소의 실제 OpenDART 응답(제목 실례): `qa/stock/fixtures/raw/005930/dart.json` · `qa/stock/fixtures/raw/196170/dart.json`

## 9. 구현 (1단계, `feat/calendar`, 2026-11-15)

### 9-1. 서버 — `worker/src/calendar.js` (+ `index.js` import 한 줄 · 경로 한 줄)

- `GET /api/calendar?from&to[&kinds=kr,us,cb,mkt,corp]` — 모양은 §3-1과 같고 다른 점: `codes` 파라미터 없음(관심종목은 기기에서만), 묶음은 `groups` 배열이 아니라 **이벤트 한 줄**(`id: grp:<종류>:<날짜>`, `grp`, `n`, `codes`), `sources.<id> = {name, ok, at, off?, err?}`(`err`는 짧은 코드만: `timeout` · `network` · `http 503` · `cool` · `cap` …), `manual: '2026-11-15'`(직접 입력 표의 날짜), 발표가 끝난 지표는 `value: {text, src:'ecos'|'fred', p}`. 오류 400(형식 · 순서 · 42일 · ±400일 · kinds), 502는 만들기 실패. ETag는 아직 없어요.
- 캐시: 엣지 `public, max-age=60, s-maxage=300, stale-while-revalidate=300`(키 `https://panse-cal.internal/v1?from&to&k`).
- **직접 입력 표는 `web/calendar.json`이 아니라 `calendar.js` 안 상수**(`BOK_MEETINGS` · `FOMC` · `KRX_DAYS` · `FRED_REL`(발표 시각 · 별 · 값 시리즈) · `KR_RULES`(제목 → 별 · ECOS 이름)) — 고치면 Worker 배포(푸시)로 끝나요. 2027 금통위는 `tentative: '보도 기준 — 한국은행 공지 전'`, 2027 FOMC는 "연준: 직전 회의에서 확정", 2026-12-31 연말 휴장 · 2027-01-04 첫 거래일 10:00은 예정.
- 규칙 계산: 코스피200 옵션 월물 만기(둘째 목요일, 휴장이면 앞당김; 3 · 6 · 9 · 12월은 동시만기 ★3), 위클리(월 · 목, 둘째 목요일과 겹치면 빼고 휴장이면 월은 뒤로 · 목은 앞으로, `weekly:true` — **화면 기본 숨김**), 금통위 의사록(2주 지난 뒤 첫 화요일), FOMC 의사록(+21일 14:00 ET). 미국 시각은 `Intl`(America/New_York)로 서머타임까지 바꿔요.
- 원천 조각(KV `REPLAY`, `list` 안 씀): `cal:bok` · `cal:kostat` · `cal:fred` · `cal:vals` · `cal:dart` · `cal:fsc` = `{at, ok, data, tried, err}`, 실패해도 `data`는 지난 값 그대로(`stale:true`). 다시 받기는 요청 때만(cron 없음): 처음 한 번은 기다리고(최대 9초), 그 뒤는 `ctx.waitUntil`. colo끼리는 `cal:lock:<id>`(60초), isolate 안은 진행 중 약속 하나.

| 원천 | 주기 | 하루 호출 | 비고 |
|---|---|---|---|
| 한국은행 통계공표일정 페이지 | 20시간(실패 30분 뒤) | 1 (11 · 12월은 다음 해 1월 쪽까지 2) | 정직한 UA, robots 허용, 1년치 표 |
| 국가데이터처 보도계획 `mods.go.kr/newsPln.es` | 20시간 | 2 (이번 달 · 다음 달; 12월은 1 — 페이지가 그해만 줘요) | 소비자물가 · 고용 · 산업활동동향만 |
| FRED `release/dates` | 20시간 | 13 | `include_release_dates_with_no_data=true` · 시각은 `FRED_REL` 표, 산업생산 · 미시간대는 날짜만("시각 확인 중") |
| 발표값 ECOS `KeyStatisticList` | 30분(필요할 때만) | ≤ 48 | 한국 지표 · 금통위가 끝난 뒤 20일 안에만, 기간이 맞는 값만 |
| 발표값 FRED `series/observations` | 30분(필요할 때만) | 보통 0~10 | 발표 60분 뒤부터 7일 안, 그 발표의 값이 들어올 때까지만 · 한 번에 ≤ 8 |
| OpenDART 무상 · 유상증자 | 평일 07~20시 30분 · 그 밖 3시간 | 오늘 `list.json` B001 · C001 × 코스피 · 코스닥 ≈ 120 + 상세 ≤ 30/회 · **상한 400/일**(`cal:dart:calls:<YYYYMMDD>`) | 공시 배지의 `dart:cool`을 같이 따라요, 지난 60일은 한 번에 평일 6일씩 채워요 |
| 금융위 배당 · 보호예수 · 권리일정 | 영업일마다(다음 영업일 13시 뒤 그날 basDt) | API당 1~2 + 보호예수 종목마다 1 ≈ 5~15 (처음엔 10영업일 거꾸로, API당 ≤ 20) | 공용 도우미 `datago.js`, 아래 9-2 |

- 키는 `env`에서만 읽고 요청 URL에만 넣어요 — 응답 · KV · 로그 · 오류 코드에 남지 않아요(점검이 가짜 키로 확인).

### 9-2. 금융위원회(공공데이터포털) — 공용 도우미로

- `worker/src/datago.js`(공용 도우미, `feat/datago`)의 `dgSnapshot`으로 API마다 사본 하나: `cal:fsc:divi`(`GetStocDiviInfoService_V2/getDiviInfo_V2` — 배당 기준일 · 지급일 · 1주당 금액) · `cal:fsc:lock`(`GetStocIssuInfoService_V3/getLockUpRetuInfo_V3` + 종목마다 `getStocIssuStat_V3`으로 상장주식 대비 % → 10 % 이상 ★3 · 3 % 이상 ★2) · `cal:fsc:rights`(**`GetStocRighScheService_V2/getRighExerReasSche_V2`**, `DG_APIS.rights` 하루 상한 200 — "임시총회 기준일 · 명부폐쇄 12/1~12/5" 식). 하루 상한 · 쉬기 · 실패 기록 · 키 숨기기는 도우미가 해요(`datago:calls|cool|err:<api>`).
- 날짜: 금융위는 그 영업일 자료를 **다음 영업일 13시 뒤**에 열어요 → 사본마다 "지금 나와 있어야 할 basDt"(휴장 건너뜀)를 하나씩 받고, 처음엔 10영업일 거꾸로 채워요. 이벤트는 id로 합쳐 두고 그 날짜 14일 뒤에 버려요. 빈 날(0행)은 3시간 뒤 한 번 더.
- 권리일정은 법인등록번호뿐이라 `datago_crno.js`의 표를 거꾸로 써서 종목코드로(한 회사에 여러 코드면 보통주), 없으면 `scrsIssuMnbdCd + '0'`이 상장 코드일 때만. 같은 종목의 DART 무상증자 기준일 · 금융위 배당 기준일과 ±3일 안에서 겹치는 권리일정은 빼요.
- `sources.fsc.parts = {divi, lock, rights}` — `ok` · 짧은 오류 코드 · `wait`(첫 사본을 받는 중). **승인 전 API(403 `forbidden` · `notfound`)는 그 부분만 빠지고 실패로 치지 않아요**(`stale` 아님). 끄기: Worker 변수 `CAL_FSC=off`(공용 끄기 `DATAGO_CAP=0`도 그대로 먹어요).

### 9-3. 화면 — `src/calendar/calendar.js · calendar.css` (빌드: 다른 모듈 다음)

- 탭 `일정`(`data-mkt="CAL"`, `state.market 'CAL'`, `#cal`)은 시장 탭 끝. 템플릿은 해외 · 지표처럼 다뤄요(`isWorld()`) — 지도 · 사이드를 숨기고 `<div id="calendar">`에 `KHCal.show()`, 다른 탭이면 `hide()`. 출처 줄 `<p id="foot-cal">`은 면책 줄 위.
- 휴대폰: 주 띠(세그먼트, ←/→) + 칩(한국 지표 · 미국 지표 · 금리 · 시장 · 기업 | ★★ 이상만 · 위클리 만기) + 고른 날부터 7일 목록 + "다음 7일 보기". 1280px 이상: 월 달력(6주, 칸마다 3줄 + "+N") + "고른 날부터 7일". 누르면 자세히(휴대폰 아래 시트 · 넓으면 떠 있는 판, `<dialog>`, Esc · 바깥 · ×, 포커스는 누른 줄로).
- 14일 묶음(2024-01-01 월요일 기준)으로 받아 기억, 보이는 동안 30분마다 다시. 저장 `khm.cal = {kinds, hi, weekly}`. 관심종목이면 "관심" 배지 + 별 하나 더(기기에서만).
- 실패 · 옛 Worker(404) · 빈 날 · 원천 하나 실패(`!` + 문구) · 스냅샷("증시 일정은 실시간 버전에서 볼 수 있어요" + `#cal` 링크)을 각각 문구로.

### 9-4. 점검

- `node qa/worker/test_calendar.mjs` — 23개(가짜 fetch · KV · 시계, 네트워크 · 키 없이): 파싱(한국은행 · 국가데이터처 실제 페이지 일부 `qa/calendar/fixtures/`), 서머타임, 만기 규칙, DART 예산 · 쉬기 · 상한, 값 창, 지난 값 유지, 키가 응답 · KV · 로그에 없음, 금융위(공용 도우미 · 가짜 data.go.kr): 배당 · 보호예수 % · 권리일정 crno → 코드 · 겹침 빼기 · 하루 한 basDt, 권리일정 403이면 그 부분만, `CAL_FSC=off`.
- `python3 qa/calendar/test_calendar.py` — 53개(목 `qa/calendar/mock_cal.py`, `CAL_QA_PORT` 기본 8995): 탭 · 해시 · 지도 숨김, 주 띠 · 목록, 칩 · 저장, 위클리 기본 숨김, 관심 배지, 자세히 · Esc · 포커스, 묶음 15종목, 주 넘기기 · 키보드, 월 달력 · 칸 고르기, 실패 · 404 · 빈 · 느림 · `stale`, 스냅샷, 360 · 390 · 768 · 1440 넘침 0 · 11px · 44px(760px 이하) · 빨강 · 초록 0 · 콘솔 오류 0.

### 9-5. 배포 뒤 실제로 확인할 것

1. `GET /api/calendar`의 `sources.fsc.parts.rights`가 `ok`인지(`forbidden`이면 주식권리일정 승인 전 — 승인되면 1시간 안에 저절로 다시 해요) · `GET /api/datago/status`의 호출 수. 배당 · 보호예수 · 권리일정이 **앞으로의 날짜**를 주는지(`basDt`가 "그날 기준 전체"인지 "그날 바뀐 것"인지)도 첫 사본으로 확인.
2. `GET /api/calendar` 첫 응답의 `sources`: 한국은행 · 국가데이터처 페이지가 Worker에서 읽히는지(HTML 모양), FRED 앞날 날짜, ECOS 키 값, DART 하루 호출 수(`cal:dart:calls:<날>`).
3. 산업생산 · 미시간대 발표 시각(지금 날짜만), 2027 금통위 · 한국은행 2027 공표일정 · 거래소 2027 휴장 공지가 올라오면 표 고치기.
