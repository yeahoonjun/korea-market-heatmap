# 정책 자료 — KDI 경제정책자료 RSS · 행정안전부 관보 목록 (규칙)

> **결정 (사용자 2026-11-15 16:07 후보 4곳 → 16:25 "Kdi만 가져와야겠다" + 관보 API 승인 내용 붙임)**: 넣는 곳은 **KDI 경제교육·정보센터 경제정책자료 RSS**와 **행정안전부 관보 목록 정보**(공공데이터포털 REST, 개발계정 자동승인 2026-11-15 ~ 2028-11-15, JSON+XML) 둘뿐이에요. 뉴스와이어 · PADO는 넣지 않아요. 공공데이터포털 인증키는 **Worker 비밀값 `DATA_GO_KR_KEY`**에만 있어요(값은 저장소 · 파일 · 로그 · KV · 응답에 쓰지 않아요). 디자인은 `docs/standards/design.md`(승인)를 따라요 — §11의 "새로 만드는 것부터 이 기준으로"에 KDI · 관보가 들어 있어요.
> 구현 `feat/policy-feeds`: Worker `worker/src/policy.js`(`GET /api/policy`), 화면 `src/policy/policy.js · policy.css`(뉴스 카드의 **정책 자료** 탭, `KHNews.addTab`), 점검 `qa/policy/worker_test.mjs` · `qa/policy/test_policy.py`.

## 0. 한 줄 규칙

두 곳의 **제목 · 날짜 · 발행 기관**(관보는 + 편집구분)만 날짜 내림차순으로 보여 주고, 누르면 **원문이 새 탭**(KDI 자료 페이지 · 전자관보 원문)으로 열려요. 본문 · 설명 · 개정이유 · 첨부는 Worker 밖으로 내보내지 않아요.

## 1. KDI 경제정보센터 경제정책자료 RSS — 실측

주소 `https://eiec.kdi.re.kr/policy/rss.do?rss_type=material` (2026-11-15 17:22 KST, 샌드박스 셸에서 한 번, User-Agent `PanseNewsBot/1.0 (+https://panse.pages.dev)`)

| 항목 | 값 |
|---|---|
| 응답 | **200**, `application/xml; charset=utf-8`, 142,467 B, `Cache-Control: no-cache`, 서버 Apache |
| 인코딩 | `<?xml version="1.0" encoding="UTF-8"?>`, RSS 2.0 |
| 채널 | 제목 "KDI경제정보센터 경제정책자료", 설명 "KDI경제정보센터 경제정책 자료 목록", `<copyright>COPYRIGHT 2007 KOREA DEVELOPMENT INSTITUTE. ALL RIGHTS RESERVED</copyright>`, `lastBuildDate` 없음 |
| 항목 수 | **100개**(평일 하루 약 50개 → 약 3일치: 11/11 ~ 11/13) |
| 항목 필드 | `title`(CDATA, 최대 67자, 엔티티 · 태그 없음) · `link`(`https://eiec.kdi.re.kr/policy/materialView.do?num=289491` 꼴, 100개 모두 같은 모양) · `description`(CDATA, 보도자료 본문 요약 수백 자) · **`pubDate`는 100개 모두 비어 있어요** |
| 내용("material") | 정부 부처 · 기관 보도자료 모음 — 재정경제부 "2026년 11월 최근 경제동향", 금융위원회 · 한국은행 · 산업통상부 · 국토교통부 · 공정거래위원회 · 국가데이터처 … 의 발표 · 회의 · 통계. 목록 페이지(`/policy/materialList.do`)의 정책자료 탭과 같은 순서(최신 날짜 먼저, `num`은 단조롭지 않아요) |
| 날짜 · 기관 | `pubDate`가 없어서 **설명 첫 문장**에서 읽어요: 100개 모두 `기관은/는 ’YY.MM.DD.(요일) …` 꼴(예: "재정경제부는 ’26.11.13.(금) 2026년 11월 최근 경제동향을 발표했다."). 여러 기관(`과학기술정보통신부와 기후에너지환경부는` · `해양수산부와 우주항공청, 기후에너지환경부는`), 미래 날짜(`고용노동부는 ’26.11.16.(월)부터 2개월간` — 금요일에 올라온 자료), 오타(`’26.11.11..(수)`)가 있어요 |

- **봇 차단**: 같은 사이트의 HTML 페이지(`/policy/materialList.do`, `/etc/policy_use.do` 이용약관)는 curl 기본 UA · 봇 이름이 든 UA에 EUC-KR "정상적인 접근이 아닙니다!!! 044-550-4665로 연락바랍니다"(200, 113 B)를 줘요. **RSS(`rss.do`)는 정직한 봇 UA에 정상**이에요. 그래서 판세는 RSS 한 주소만 부르고, RSS가 아닌 답(이 차단 문구 포함)이 오면 30분 쉬어요(우회하지 않아요).
- **오래된 사본 주의**: 처음 웹 가져오기 도구로 본 RSS는 10/23자 99개(지난 사본)였고, 같은 시각 셸의 직접 요청은 11/13자 100개(현재)였어요. 도구 쪽 캐시인지 KDI 쪽인지는 가릴 수 없어요 → **배포 뒤 `/api/policy`의 KDI 날짜가 최근 평일인지 확인**(§7).
- **이용 조건**: RSS는 KDI가 구독용으로 공개한 주소예요. 채널의 저작권 표시는 "ALL RIGHTS RESERVED"이고, 이용약관 페이지는 봇에게 막혀서 **내용을 확인하지 못했어요** — 사람이 브라우저로 `https://eiec.kdi.re.kr/etc/policy_use.do`를 확인해 주세요. 판세는 RSS가 주는 범위에서 **제목 + 원문 링크 + (설명에서 읽은) 날짜 · 기관 이름**만 써요(설명 글 자체는 내보내지 않아요). 공공누리 유형 표시는 RSS · 목록 페이지 어디에도 없어요.

## 2. 행정안전부 관보 목록 정보 — API 명세 (공공데이터포털 15109157)

출처: 포털 상세 페이지 `https://www.data.go.kr/data/15109157/openapi.do`에 들어 있는 Swagger(2.0) 정의를 그대로 읽었어요(2026-11-15). 키 없이 호출해 오류 모양만 확인했어요(키는 이 작업 환경에 없어요).

| 항목 | 값 |
|---|---|
| 제공 | 행정안전부 법무담당관실(044-205-1492), 등록 2022-12-07 · 수정 2025-09-15, REST, JSON+XML, **갱신 실시간**, 무료, 1948년 ~ 지금 |
| 서비스 URL | `https://apis.data.go.kr/1741000/ApiTotalService` |
| 오퍼레이션 | **`getApiTotalList`** "관보 목록 정보 조회 오퍼레이션" → 요청 `https://apis.data.go.kr/1741000/ApiTotalService/getApiTotalList` (Swagger의 제공기관 원 주소 `https://open.gwanbo.go.kr/OpenApi/ApiTotalService/getApiTotalList`는 직접 부르면 `{"response":{"resultCode":"305","resultMsg":"EMPTY_GWKEY_ERROR"}}` — 포털 게이트웨이를 거쳐야 해요) |
| 트래픽 | **개발계정 10,000**(하루) · 운영계정은 활용사례 등록 시 늘릴 수 있음 · 심의 개발/운영 모두 자동승인 |
| 이용허락범위 | **"이용허락범위 제한 없음"**(포털 정책 페이지로 연결). 공공누리 유형 표시는 없어요 |

**요청 변수** (모두 문자열)

| 이름 | 필수 | 예시 | 뜻 |
|---|---|---|---|
| `serviceKey` | 필수 | – | 포털 인증키 |
| `pageNo` | 필수 | 1 | 페이지 번호 |
| `pageSize` | 필수 | 10 | 페이지 크기 (최댓값은 명세에 없음 → 판세는 100) |
| `reqFrom` | 필수 | 20221207 | 발행 시작일 `YYYYMMDD` |
| `reqTo` | 필수 | 20221217 | 발행 종료일 `YYYYMMDD` |
| `search` | 옵션 | 입법예고 | 관보 제목 |
| `pblcnSearch` | 옵션 | 보건복지부 | 발행기관 |
| `lawNmSearch` | 옵션 | 행정절차법 | 근거법령 |
| `type` | 필수 | 1 | `0` = XML, `1` = JSON |

**응답** `response` = `{resultCode, resultMsg, totalCount, pageSize, pageNo, items:{item:[…]}}` — `item` 필드:
`cntntSeqNo` 관보번호 · `cntntSj` 관보제목 · `ofcttBookNm` 관보구분 · `hopePblictDt` 관보발행일자 · `cmplatSeNm` 편집구분명 · `themaSe` 테마구분 · `pblcnInstNm` 발행기관명 · `basisLawNm` 근거법령명 · `crtnYn` 정정여부 · `rvsnRsnMainCn` 개정이유 및 주요내용 · `pdfFilePath` 관보PDF원문링크.
결과 코드(Swagger): `00` 정상호출 · `10` 조회결과 없음 · `301` 데이터베이스 에러 · `302` 어플리케이션 에러 · `303` 잘못된 요청 파라메터 · `304` 사용할 수 없는 게이트웨이 인증키 · `305` 게이트웨이 인증키 누락.

- **게이트웨이 오류**(키 · 한도): 포털 게이트웨이는 `type`과 상관없이 XML `<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>…<returnReasonCode>N</returnReasonCode>`로 답해요. 이번에 키 없이 부른 결과: **HTTP 401 · `SERVICE_KEY_IS_NULL` · `returnReasonCode` 20**. 포털의 다른 흔한 코드(22 하루 한도 넘음 · 30 등록되지 않은 키 · 31 기한 만료 · 32 등록되지 않은 IP)는 포털 공통 관례이고 이번에 직접 보지는 못했어요.
- **`serviceKey` 인코딩**: 포털은 "Encoding"(이미 `%XX`) · "Decoding"(원문, `+ / =`가 들어갈 수 있음) 두 모양을 줘요. 판세는 값에 `%XX`가 있으면 그대로, 없으면 `encodeURIComponent` 한 번 — 어느 쪽을 넣어도 한 번만 인코딩돼요. 요즘 발급되는 64자 16진수 키는 두 모양이 같아요.
- **확실하지 않은 것**(키가 없어 실제 응답을 못 봤어요): `pageSize` 최댓값, 결과 순서, `hopePblictDt` 모양(다른 관보 API를 쓰는 공개 코드는 `2026. 11. 13.` 꼴로 다뤄요), `pdfFilePath`가 경로인지 전체 주소인지, `cmplatSeNm` · `themaSe`의 실제 값, 하루 건수. 판세는 모두 방어적으로 읽어요(§4) — **배포 뒤 확인**(§7).

## 3. 이용 조건 정리

| | KDI RSS | 관보 API |
|---|---|---|
| 표시 | "COPYRIGHT 2007 KOREA DEVELOPMENT INSTITUTE. ALL RIGHTS RESERVED" | 포털 "이용허락범위 제한 없음" |
| 공공누리 | 표시 없음 | 표시 없음 |
| 약관 | 이용약관 페이지가 봇에게 막혀 **확인 못 함** → 사람 확인 필요 | 포털 정책 페이지: 제3자 권리가 든 데이터는 권리자 허락 필요 · 시스템 성능 문제가 생기면 이용 제한 가능 |
| 판세가 쓰는 범위 | 제목 · 원문 링크 · 설명 첫 문장에서 읽은 날짜와 기관 이름 | 제목 · 원문(PDF) 링크 · 발행일 · 발행기관 · 편집구분 |
| 쓰지 않는 것 | 설명(요약) 글 | 개정이유 및 주요내용 · 근거법령 · 관보구분 · 테마구분 |

- 관보에 실리는 법령 · 고시 · 공고는 저작권법 제7조(보호받지 못하는 저작물)의 "국가 또는 지방자치단체의 고시 · 공고 · 훈령 그 밖에 이와 유사한 것"에 들어요(참고 — 법률 판단은 사람이 확인).
- 화면에는 두 출처를 이름으로 적어요(카드 아래 + 페이지 출처 줄).

## 4. Worker `GET /api/policy` (`worker/src/policy.js`)

```
{ asOf: '2026-11-15T17:30:00+09:00',
  items: [ { src: 'kdi', title: '2026년 11월 최근 경제동향', url: 'https://eiec.kdi.re.kr/policy/materialView.do?num=289491', t: '2026-11-13', org: '재정경제부' },
           { src: 'gwanbo', title: '…', url: 'https://gwanbo.go.kr/…', t: '2026-11-13', org: '금융위원회', kind: '고시' }, … ],
  sources: { kdi: { ok: true, n: 30, at: '…' },
             gwanbo: { ok: false, n: 12, at: '…', error: 'http 401 gw 30', stale: true, scanned: 0 } } }
```
- **`t`는 KST 날짜**(`YYYY-MM-DD`) — 두 곳 모두 시각을 주지 않아요. 날짜 내림차순, **같은 날 안에서는 KDI · 관보가 번갈아**(KDI 먼저) — KDI가 하루 50개라 관보가 "전체"에서 묻히지 않게. 출처마다 최대 30개.
- **KDI**: 제목(엔티티 · 태그 · 보이지 않는 글자 정리, 200자), 링크는 `eiec.kdi.re.kr`의 `/policy/materialView.do?num=숫자`만(→ `https://…?num=N`으로 다시 만들어요), `t` = 설명 첫 문장의 날짜. 그 날짜가 **오늘보다 뒤**("…부터")거나 없으면 **바로 위 항목의 날짜**(목록이 최신순이라서). `org` = 날짜 앞 주어(`…은/는`), 여러 기관이면 "해양수산부 외 2곳", 주어가 34자보다 길면 기관으로 보지 않아요. 설명 글은 내보내지 않아요.
- **관보 거르기 — 시장 화면용** (한 곳 `GB_ORG_RE` · `GB_SKIP_KIND_RE`): 발행기관이 **재정경제부 · 기획재정부(옛 이름) · 기획예산처 · 금융위원회 · 증권선물위원회 · 금융감독원 · 한국은행 · 산업통상(부 · 자원부 · 교섭본부) · 공정거래위원회 · 국세청 · 관세청** 중 하나이고, 편집구분이 **인사가 아닌 것**(고시 · 공고 · 법령 …). 까닭: 관보 하루 분량의 대부분은 시장과 무관한 인사 발령 · 지역 고시예요. 국토교통부 · 과기정통부 등은 고시가 많고 대부분 지역 사업이라 뺐어요. `kind` = 편집구분(예: 고시), `org` = 발행기관. 링크는 `pdfFilePath`를 **전자관보 공식 사이트**(`https://gwanbo.go.kr` · `www.` · `open.`)로만 — 경로면 `https://gwanbo.go.kr` 뒤에 붙이고, 다른 호스트 · 빈 값이면 전자관보 "일자별 관보" 페이지 `https://gwanbo.go.kr/user/search/searchDaily.do`. `hopePblictDt`는 `2026-11-13` · `2026.11.13` · `2026. 11. 13.` · `20261113`을 읽고, 못 읽으면 물어본 날.
- **관보 받는 법**: 하루 한 번의 조회(`reqFrom = reqTo`), `pageSize=100`, `totalCount`만큼 쪽을 더(하루 최대 5쪽, 2쪽부터 병렬; 포털이 쪽 크기를 100보다 작게 자르면 그 크기로 다음 쪽을 셈해요). 오늘은 갱신마다, 지난날은 **그날이 끝난 뒤 한 번 읽으면 끝**(스냅숏에 `done`) — 오늘 줄이 30개가 안 될 때만 7일 안에서 가까운 날부터(한 번에 3일까지). 오늘 · 전날을 이미 알고 있으면 그 줄 수로 셈해서 필요한 날만 읽어요.
- **받는 규칙**(뉴스 §2-3과 같아요): User-Agent `PanseNewsBot/1.0 (+https://panse.pages.dev)`, 요청마다 6초 · 관보 한 번의 갱신 전체 10.5초, 같은 요청 안에서 다시 시도하지 않아요.
- **신선도 문**(KV를 모든 데이터센터가 같이 봐요): KV의 마지막 사본이 아래보다 젊으면 그대로 내주고 원천에 묻지 않아요.

| | 평일 낮 | 밤 · 주말 |
|---|---|---|
| KDI | 20분 (07~20시) | 60분 |
| 관보 | 30분 (06~20시) | 120분 |
| 엣지 캐시(경로) | 600초 + stale-while-revalidate 600 (한 곳이 실패 중이면 120초) | 같음 |

- **실패**: 원천마다 쉬어요(KV `policy:cool:<src>`) — 그 밖의 실패 5분, KDI 403/429 15분, KDI가 RSS 아닌 답(차단 문구) 30분, 관보 키 오류(HTTP 401/403 · 코드 20 · 30 · 31 · 32 · 304 · 305) 30분, 관보 한도(HTTP 429 · 코드 22) 60분. 마지막 성공본(KDI `policy:last:kdi` 24시간, 관보 `policy:last:gwanbo` 8일 — 날짜별 스냅숏)을 `{ok:false, stale:true}`로 같이 내줘요. 둘 다 없고 아무 곳도 답하지 않으면 **502** `{error, sources}`(no-store). 키가 없으면 관보는 `error:'no key'`, KDI는 그대로.
- **오류 글자**: `timeout` · `network` · `http N` · `not rss` · `no items` · `not json` · `api N`(결과 코드) · `gw N`(게이트웨이 코드) · `cool-down` · `budget` · `no key` — 원천의 메시지 · 예외 글 · 주소는 절대 옮기지 않아요.
- **진단**: KV `policy:err:<src>` = `{at, colo, error, status?, code?}`(3일, 원천마다 30분에 한 번). 공개 응답의 `sources.gwanbo.scanned` = 이번에 읽은 오늘 관보 줄 수(거르기 전) — 거르기가 너무 좁은지 볼 때.
- **키 보호**: 키는 `gbPage()`가 만드는 요청 주소에만 들어가요. 로그를 쓰지 않고, 오류는 위의 고정 글자 + 숫자뿐이고, 응답 · KV에 쓰기 직전에 키(원문 · 인코딩 두 모양)를 `***`로 지우는 마지막 거름망이 있어요. 경로가 예외를 만나도 `{error:'정책 자료를 만들지 못했어요'}`만(예외 글 없음).

### 4-1. 호출 수 (하루)

| | 평소 (누군가 탭을 하루 종일 열어 둔 최악에 가까운 경우, 데이터센터 하나) | 실패가 이어질 때 | 하드 상한 |
|---|---|---|---|
| KDI | 평일 13시간 × 3 + 11시간 × 1 = **50번**, 주말 24번 | 쉬는 시간 5분 이상 → ≤ 288번 | — (공개 RSS, 하루 50번은 뉴스 언론사 한 곳의 ⅒) |
| 관보 | 갱신 14시간 × 2 + 10시간 × 0.5 = 33번 × 오늘 1~2쪽 + 날이 바뀔 때 전날 1~3쪽 ≈ **35~70번** (하루 300건이 넘는 날 · 5쪽이어도 ≈ 170번) | 5분 쉼 → ≤ 288번(1쪽만), 키 · 한도 오류는 30 · 60분 | **1,500번/일**(스냅숏에 그날 호출 수, KST 날) → `budget` |
| 한도 대비 | 개발계정 **10,000번/일**의 0.4~0.7 % (상한 15 %) | ≤ 2.9 % | 15 % |

- 화면은 정책 자료 탭이 **보이는 동안만** 10분마다 받아요(다른 탭 · 숨은 탭 · 화면 밖이면 멈춤). 데이터센터가 여럿이어도 KV 신선도 문이 같이 막아요(KV 전파 지연 약 60초 동안만 겹칠 수 있어요).
- KV: 경로 한 번에 읽기 4번(+ 실패 때 1번), 쓰기는 원천을 실제로 불렀을 때만(KDI ≤ 50번 · 관보 ≤ 33번/일 + 실패 기록). Workers Paid 포함량 안이에요.

## 5. 화면 — 뉴스 카드의 "정책 자료" 탭 (`src/policy/policy.js · policy.css`)

- 자리: 뉴스 카드(`#news`)의 세 번째 제목 탭 **정책 자료**(시장 뉴스 · 오늘 공시 다음, `KHNews.addTab`, 고른 탭 기억 `khm.feedTab`). 카드 제목 탭은 news.js의 밑줄 탭 그대로(design.md §7 ③).
- 두 번째 줄: 출처 **필터 칩** `전체 · KDI · 관보`(알약 칩 — design.md §7 "알약 칩은 필터에만", 하나만 고름, 고른 칩 = `--chip-on` 채움 + `--chip-ring` 테, 수는 `--fg2`). 받은 줄이 없는 출처 칩은 꺼진 모양(.45, 왜 꺼졌는지는 아래 줄 글로).
- 줄(뉴스 줄과 같은 배치, design.md §7 "목록 줄"): **날짜**(오늘이면 "오늘", 아니면 `M/D`) · **출처 칩**(`KDI` · `관보`, 중립 글자 배지 `--r-badge`) · **제목**(하나의 링크, 새 탭, `title`에 전체) · **기관**(관보는 `기관 · 편집구분`, 오른쪽 `--muted`). PC 줄 높이 = 뉴스와 같은 `--nw-rh`(32, 손가락 화면 44), 1200px 넘는 카드는 두 단, 줄 수는 뉴스 채우기(`L`) 그대로 + 더보기 30. 휴대폰(≤ 760): 1줄 날짜 · 출처 · 기관 / 2줄 제목 두 줄(`--fs-lg`), 줄 44px 이상, 칩 누르는 곳 44px.
- 글자 · 간격 · 모서리 · 높이는 design.md 토큰만(`--fs-*` 최소 11px · `--space-*` · `--r-*` · `--h-*`). 빨강 · 초록은 쓰지 않아요(등락 데이터가 없어요). 앰버는 고른 칩 · 포커스에만 — 실패 `!`는 `--fail-dot`(지금은 앰버 값, 디자인 이전 때 바뀌어요), 글은 `--fg2`.
- 상태: 불러오는 중(빈 줄) · 정상("HH:MM 기준") · 한 곳 실패(그 출처에 지난 목록이 있으면 한 줄 "! 관보 새 자료를 받지 못했어요 · 11/15 09:30에 받은 목록이에요" + 다시 시도, 지난 목록도 없으면 "! 관보를 불러오지 못했어요") · 둘 다 실패("정책 자료를 불러오지 못했어요" + 다시 시도) · 빈 목록(필터별 문구) · 오래됨(30분 넘게 못 받음 → 머리 `!` "HH:MM 기준 · N분째 못 받았어요" + 다시 시도) · **스냅샷**: "정책 자료는 실시간 버전에서 볼 수 있어요" + 링크 · **옛 Worker(404)**: 탭을 빼요(다시 불러올 때까지).
- 받기: 탭이 보일 때(고를 때 · 카드가 화면 400px 안 · 문서가 보일 때)만, 10분마다, 실패하면 2 → 4 → 8 → 10분, 시계 누름(`kh:refresh`)에도. 읽는 중(포인터 · 포커스가 패널 안)에는 줄을 바꾸지 않고 나갈 때 반영. 갱신은 읽어 주지 않아요.
- 출처 줄: 패널 아래 "KDI 경제정보센터 경제정책자료 RSS · 행정안전부 관보(공공데이터포털) — 제목 · 날짜 · 기관만 보여 드려요. 원문은 새 탭으로 열려요.", 페이지 아래 `<p id="foot-policy">` "정책 자료: KDI 경제정보센터 RSS · 행정안전부 관보 (제목 · 링크만)" — **공시 줄 다음, © 위**(AGENTS §3-30 순서: 데이터 → 시장 뉴스 → 공시 → 정책 자료 → 기준일 · 스냅샷 안내 → © → 투자 유의 문구 맨 아래). 템플릿을 고치지 않고 모듈이 `#foot`을 지켜보다 `#foot-disc` 바로 뒤에 다시 붙여요(해외 · 지표 탭처럼 그 줄이 없는 출처 줄에는 넣지 않아요).

## 6. 점검

- `node qa/policy/worker_test.mjs` — 가짜 fetch · KV · caches · 시계, 네트워크 · 진짜 키 없음: 모양 · 정렬 · 번갈아 · 30개 · KDI 날짜 규칙(미래 → 위 항목) · 기관 읽기 · 관보 거르기 · 쪽 넘김 · 지난날 `done` · 신선도 문(평일 · 밤 · 주말) · 엣지 캐시 · 실패마다 쉼 길이 · 지난 목록 · 502 · 키 없음 · 하루 상한 · 6초 시간 제한 · **키가 응답 · 머리 · KV 값 · 콘솔 어디에도 없음**(키를 메시지에 되돌려 주는 가짜 원천 · 주소가 든 예외 포함) · 인코딩 한 번.
- `python3 qa/policy/test_policy.py` — `qa/policy/mock_api.py`(뉴스 목에 `/api/policy` 더함): 탭 · 필터 · 링크 · 상태 · 390px 넘침 · 콘솔 오류 · 다른 탭 그대로 · 스냅샷 · 스크린샷 `qa/shots/policy/`.

## 7. 배포 뒤 확인할 것

1. `https://panse.pages.dev/api/policy` → `sources.kdi.ok`, KDI 첫 줄 날짜가 최근 평일인지(지난 사본 문제, §1).
2. `sources.gwanbo.ok` · `scanned`(평일 오전 이후 0이 아니어야 해요) · `n`. `ok:false`면 `error`: `http 401 gw 30` = 키가 등록 전이거나 잘못 넣음(포털 승인 후 반영까지 1~2시간 걸릴 수 있어요), `gw 22` = 한도, `api 303` = 변수 문제(→ `pageSize` 100이 너무 큰지).
3. 관보 줄의 링크가 PDF 원문으로 열리는지(아니면 `pdfFilePath` 모양을 보고 `gbUrl` 조정), 날짜가 맞는지(`hopePblictDt` 모양), `kind`가 고시 · 공고 같은 말인지(`cmplatSeNm`).
4. 거르기 결과가 너무 적거나 많으면 `GB_ORG_RE`를 조정(KV `policy:last:gwanbo`의 `days[*].total`과 `items`를 비교).
5. KV `policy:err:kdi` · `policy:err:gwanbo`에 실패가 이어지는지.

## 8. 출처

- KDI RSS: https://eiec.kdi.re.kr/policy/rss.do?rss_type=material · 목록 https://eiec.kdi.re.kr/policy/materialList.do · 이용약관(봇 차단) https://eiec.kdi.re.kr/etc/policy_use.do
- 관보 목록 정보 API: https://www.data.go.kr/data/15109157/openapi.do (영문 https://www.data.go.kr/en/data/15109157/openapi.do — "Development account: 10,000", 요청 주소 `…/getApiTotalList`) · 메타데이터 https://data.go.kr/catalog/15109157/openapi.json
- 같은 계열 관보 API(같은 변수): https://www.data.go.kr/data/15109178/openapi.do (대통령공고, `ApiPredeceService`)
- 전자관보 일자별 관보(파일데이터, 사이트 주소): https://www.data.go.kr/data/15087197/fileData.do
- 포털 이용 정책: https://www.data.go.kr/ugs/selectPortalPolicyView.do
- 저작권법 제7조(참고): https://korea.legal/wiki/%ec%a0%80%ec%9e%91%ea%b6%8c%eb%b2%95-%ec%a0%9c7%ec%a1%b0/
- 다른 관보 API를 쓰는 공개 코드(필드 이름 · `pdfFilePath`를 `https://gwanbo.go.kr` 뒤에 붙이는 방식 참고만): https://github.com/shhong9173-art/seoul-reporting-radar/pull/270
