# 실시간 갱신 — 설계 (로드맵 2번, AGENTS §3-23b)

>**상태 (2026-11-14 토)**: 설계 확정 + **1단계 a(Worker 쪽) 구현 — 배포 전**(브랜치 `feat/realtime-plan`). 화면 쪽(1단계 b)은 템플릿 병합 뒤. 첫 DO 배포는 오케스트레이터가 손으로(§13).
> **사용자 결정 (2026-11-14 02:46)**: "개인적으로 쓰고 가족들이나 지인만 쓸거라 클라우드플레어 유료 기본요금제 5달러 이외에는 추가요금 지불할 생각없어서 추천대로 전체 종목 말고 코스피 상위 300 종목이랑 코스닥 상위 300 종목만 실시간인게 나을거같아 네이버 확인은 추천대로" → ① **$5 기본요금 밖의 요금 0** — 추정이 아니라 **하드 상한 + 차단기**(§12) ② 실시간은 **코스피 상위 300 + 코스닥 상위 300**(지금 600 줄기), `전체 2,700`은 폴링 그대로 ③ 네이버 확인 **3초**, 상수 하나 `LIVE_POLL_MS`(평일 실측이 더 느리면 그 값으로만 바꿈).
> 작성 시점이 장이 닫힌 날이라 네이버 쪽 "장중" 수치는 측정 방법만 적고(§1-4), 나머지는 실제 측정값이에요.
> 시안: [`prototypes/realtime/`](../../prototypes/realtime/) — Durable Object 허브 + WebSocket + 데모 화면 + 측정 도구. 빌드에 들어가지 않고, 자기 `wrangler.toml`(Worker 이름 `panse-realtime-proto`)로 `npx wrangler dev`에서만 돌아요.
> 같이 보는 문서: AGENTS §3(시세 계약) · §3-5(플래시) · §3-15(1분 기록기) · §3-29(공시 ETag) · [`controls.md`](controls.md) · [`themes.md`](themes.md).

## 0. 한 줄 결론

**D안(하이브리드)을 추천해요: 히트맵 시세(상위 600종목) 한 줄기만 Durable Object 하나가 네이버를 3초마다 받아 WebSocket으로 "바뀐 값만" 밀어 주고, 연결이 안 되면 지금의 10초 폴링이 그대로 대신해요. 뉴스 · 공시 · 해외 · 지표 · 테마 · 등락 분포는 폴링으로 둬요.**

| | 지금 (10초 폴링) | 추천 (허브 3초 + WebSocket) |
|---|---|---|
| 화면에 보이는 시세의 평균 나이 | 네이버 지연 + 약 10초 (최악 약 19초) | 네이버 지연 + 약 2.6초 (최악 약 4초) |
| 바뀌는 모양 | 10초마다 한꺼번에 | 3초마다 바뀐 종목만 (플래시가 고르게) |
| 휴대폰 데이터 (시간당) | 13 MB | 1~8 MB (시안 측정, 움직이는 종목 수에 따라) |
| 월 비용 · 동시 200명 | ₩9,600 | ₩6,700 (기본요금 $5 안) |
| 월 비용 · 동시 2,000명 | ₩75,600 | ₩34,000 (대부분 다른 폴링 몫) |

> 사용자 결정 뒤(2026-11-14): 허브는 **동시 50명까지**(51번째부터 폴링), 하루·한 달 상한과 차단기로 **$5 포함량 안에서만** 돌아요 — 아래 2,000명 열은 비교용이에요(§12).

폴링을 3초로 줄여도(A′) 신선도는 비슷해지지만 동시 2,000명이면 월 ₩174,000, 휴대폰 데이터는 시간당 43 MB예요. **푸시가 이기는 이유는 "더 빨라서"보다 "같은 신선도를 훨씬 싸고 가볍게"예요.**

---

## 1. 신선도는 어디서 오나 (질문 1)

### 1-1. 사슬

```
네이버 체결 ─U─▶ 네이버 polling 응답 ─F─▶ Worker/허브 ─(엣지 캐시 나이 E)─▶ 화면 요청 주기 P ─▶ 화면
```
- **U** 네이버 내부 지연 — 우리가 못 줄여요. 화면은 절대 이보다 신선할 수 없어요.
- **F** Worker가 네이버에서 받는 시간 — 600종목 한 번에 약 1~1.5초.
- **E** 엣지 캐시 나이 — 지금 TTL 8초(평균 4초).
- **P** 화면의 요청 주기 — 지금 10초(평균 5초 동안 옛 값을 보여 줌).

**푸시가 줄이는 건 E와 P뿐이에요.** 허브가 N초마다 받으면 화면의 나이는 `U + F + N/2 + 전달(0.1초 안팎)`이 돼요.

### 1-2. 네이버 polling 실측 (2026-11-14 토 02:05~02:07 KST, 샌드박스, `measure_upstream.py --codes K --interval 10 --duration 120 --pair`)

| 항목 | 값 |
|---|---|
| 코스피 상위 300 한 번 | 전송 70.4 KB(gzip) · 원본 657 KB · 응답 1.24초(중앙값, 1.11~1.48) |
| 응답 머리 | `content-type`, `content-encoding: gzip`, `date`, `referrer-policy`, `server: nfront`뿐 — `cache-control`·`age`·`etag`·`last-modified` 없음(02:40에 curl로 한 번 더 확인). `data/ENDPOINTS.md` §0의 11/09 기록엔 `cache-control: no-cache, no-store…`가 있었어요 — 어느 쪽이든 조건부 요청(304)은 못 쓰고 캐시는 우리가 해야 해요 |
| `pollingInterval` (네이버가 자기 화면에 주는 간격) | 장 닫힘 **70,000 ms**. 장중은 **7,000 ms**(2026-11-09 16:28 실측, `data/ENDPOINTS.md` §1) — 네이버 자기 화면은 7초마다 물어요 |
| `time`(응답을 만든 서버 시각) | 12번 모두 요청마다 달라졌어요 |
| 동시에 두 번 (2회) | 본문 같음 · `time` 다름 → 응답 봉투는 요청마다 새로 만들어요(통째 캐시 아님). 본문이 같은 건 장이 닫혀서예요 |
| 내용 변화 | 0/11 (마지막 체결 `2026-11-13T20:00:00+09:00`, NXT 애프터마켓 끝) |
| gzip 크기가 매번 조금씩 다름 | 압축을 요청마다 따로 해요 — 앞단 CDN 캐시가 없다는 또 하나의 신호 |

알 수 없는 것(장이 닫혀서): 네이버 뒤쪽 데이터가 **체결마다** 바뀌는지, **몇 초 단위 묶음**으로 바뀌는지 — 그게 U와 허브 간격의 하한을 정해요. 측정 방법은 §1-4.

### 1-3. 판세 쪽 실측 (같은 날 02:20, 미국 데이터센터 EWR · IAD 경유)

| 경로 | gzip | 원본 |
|---|---|---|
| `/api/quotes` (600행) | **37,132 B** | 168,151 B |
| `/api/quotes?scope=all` (2,701행) | 123,528 B | 542,724 B |
| `/api/breadth?m=K` | 5,580 B | 17,559 B |
| `/api/market` · `/api/world?kind=index` | 1,355 B · 2,015 B | — |

- 엣지 캐시는 **실제로 동작해요**: 두 주소(`*.workers.dev`, `panse.pages.dev`) 모두 첫 요청 2.4~2.7초(네이버까지 다녀옴), 8초 안의 다음 4번은 0.30~0.58초, `cf-cache-status: HIT`, `age: 3`. 캐시는 **데이터센터마다 따로**라서 네이버 호출은 "시청자가 있는 데이터센터 수 × 8초에 1번"이에요.
- 1분 기록(2026-11-12)으로 본 움직임: 600종목 중 **1분 사이 가격이 바뀐 종목** 09:01~11:00 중앙값 397개(329~529), 13:31~15:30 중앙값 349개. 3초 사이는 측정 못 함(§1-4) — 시안의 크기 표(§8-3)는 그래서 범위로 적었어요.

### 1-4. 장중 측정 방법 (다음 평일 10:00 · 14:00 KST, 각 2분)

```
python3 prototypes/realtime/measure_upstream.py --codes K+Q --interval 1 --duration 120 --pair --out tmp/up_1s.jsonl
python3 prototypes/realtime/measure_upstream.py --codes K+Q --interval 3 --duration 120 --out tmp/up_3s.jsonl
```
- 2분에 120번 이하(1초 간격) — 네이버 자기 화면 한 탭이 7초마다 묻는 것보다 조금 많은 정도로, 측정할 때만.
- 읽는 법: `pollsWithNewContent`가 1초 간격에서도 거의 매번 → 뒤쪽 캐시 없음, 허브 3초 OK. 내용이 k초마다만 바뀜 → 허브 간격 = k초(더 자주 묻는 건 낭비). `lagSMedian`(응답 `time` − 가장 최근 체결) = U의 대략값. 3초 간격의 `changedPrice`·`changedRows` 중앙값 → §8-3 크기 표의 실제 행. `--pair`의 `sameBody:false`가 나오면 서버마다 다른 사본(같은 순간 두 값)이라는 뜻 → 허브가 "더 최근 체결" 규칙(`fresher`)을 지켜야 해요(지금 템플릿 규칙 그대로).

---

## 2. 선택지 (질문 2)

N = 허브가 네이버에 묻는 간격, C = 동시 시청자, F ≈ 1초로 계산. 비용은 §3 표.

| | A 폴링 조이기 | A+ 폴링 + 버전 델타 | B DO + WebSocket | C DO + SSE | **D 하이브리드 (추천)** |
|---|---|---|---|---|---|
| 방식 | 화면 5초 · 엣지 3초 (A′: 3초 · 2초) | `?since=버전` → 바뀐 행만 | 허브가 N초마다 받아 바뀐 값만 밀어 줌 | 같은 허브, 스트림 응답 | B를 시세 한 줄기에만 + 연결 안 되면 지금 폴링 |
| 화면 나이 평균 / 최악 | U+5초 / U+9초 (A′ U+3.5 / U+6) | A와 같음 | **U+2.6초 / U+4.2초** (N=3) | B와 같음 | B와 같음 |
| 바뀌는 모양 | 5초마다 한꺼번에 | 같음 | 3초마다 바뀐 종목만 | 같음 | 같음 |
| 네이버 호출 | 데이터센터마다 3초에 1번 | 같음 | **전 세계 1곳에서 N초에 1번** | 같음 | 같음(+ 폴링 대체분) |
| 휴대폰 데이터 / 시간 | 26 MB (A′ 43 MB) | 델타 크기 ≈ B | **1~8 MB** | 압축 안 되면 4~5배 | B와 같음 |
| Worker 요청 | 시청자 × 720/시간 | 같음 | 시청자 × 연결 4/시간 | 같음 | 같음 |
| 깨지는 곳 | 없음(지금과 같음) | 버전 사슬이 데이터센터마다 따로 — 휴대폰이 데이터센터를 옮기면 통째로 | 허브 하나가 단일 지점 → 폴링 대체 필요 | + 압축·버퍼링 미확인 | 허브가 죽어도 폴링으로 지금 수준 |
| 일 | 숫자 두 개 | 버전 저장·계산을 Worker마다 | 허브 + 화면 모듈 | 허브 + 화면 모듈 | 허브 + 화면 모듈 + 대체 |

### 2-1. A — 폴링 조이기 (엣지 TTL ↓, ETag/304, 델타)
- **ETag/304는 장중엔 안 도와요**: 장중엔 응답이 매번 바뀌어서 304가 날 일이 없어요. 밤·주말 60초 폴링에서만 이득(37 KB → 1 KB 안팎) — 이건 어떤 안을 고르든 2단계에서 따로 넣을 만해요(§9).
- **버전 델타(A+)**: 버전을 매기려면 "모두가 같은 사본"이 있어야 하는데, 엣지 캐시는 데이터센터마다 따로예요. 데이터센터마다 사슬을 만들 수는 있지만(이전 스냅숏을 캐시에 두고 비교), 요청 수는 A 그대로이고 휴대폰이 데이터센터를 옮기면 통째로 다시 받아요. **허브(DO)가 있어야 깔끔해지는 기능**이라 B로 가는 게 맞아요.
- 신선도를 B만큼 올리려면(A′) 요청이 지금의 3.3배 → 동시 2,000명 월 ₩174,000.

### 2-2. B — 시장 허브 DO + WebSocket (Hibernation API)
- 허브 = `MarketHub` 클래스, 채널마다 하나(`idFromName('top')`, 나중에 `'all'`), 위치 힌트 `apac`(네이버와 시청자가 모두 한국).
- 알람(`setAlarm`)으로 N초마다 네이버(지금 `quotesCore`와 같은 함수) → 행을 "모든 화면이 갖고 있는 그대로" 들고 있다가 **바뀐 키만** 방송. 내보내는 메시지는 무료, 들어오는 메시지는 20개 = 요청 1개라서 화면은 평소 아무것도 보내지 않아요.
- 시청자가 0이면 허브는 알람을 멈춰요 → 밤·주말·무관심 시간엔 네이버 호출도 0.
- WebSocket 압축(permessage-deflate)은 호환 날짜 2023-08-15부터 기본 → 지금 `2026-11-01`이면 켜져 있어요. 시안에서 실제로 협상됨을 확인(§8).

### 2-3. C — SSE (Server-Sent Events) from DO
- 장점: 업그레이드가 아니라 보통 스트림 응답이라 Pages 경유가 확실, `EventSource`가 알아서 다시 붙고 `Last-Event-ID`로 이어 받기가 공짜.
- 단점: 화면→서버 말이 없음(채널 바꾸면 다시 연결), 스트림이 열려 있는 동안 허브가 잠들 수 없음(허브가 1~2개라 비용 영향은 없어요 — §3), **Cloudflare가 `text/event-stream`을 압축·버퍼링하는지 확인 못 함**. 압축이 안 되면 델타가 4~5배(§8-3: 중앙값 24 KB 대 5.4 KB).
- 결론: WebSocket이 Pages 경유로 안 되는 최악의 경우의 **두 번째 길**로 남겨요(허브 코드는 같고 출구만 다름).

### 2-4. D — 하이브리드 (추천)
- 시세 줄기 하나(`top`)만 허브. 나머지는 폴링 그대로 — **뉴스(3분, RSS라 바뀌는 게 드묾), 공시(60초 + ETag/304 이미 있음, §3-29), 해외·지표(30초, 원천이 최대 20분 지연이라 밀어 줄 이유가 없음), 지수 띠(30초 — 지수 값 자체는 델타에 같이 와요), 테마(30초), 등락 분포(60초), 관심·테마의 스트림 밖 종목(`?codes=` 10초)**.
- `전체(2,700)`는 1단계에선 지금처럼 15초 폴링(질문 2).
- 허브가 죽거나, 연결이 안 되거나, 45초 동안 소식이 없으면 그 화면은 자동으로 10초 폴링 — **최악이 지금**이에요.

---

## 3. 비용 (Workers Paid, 원/월)

**가격** (둘 다 "Last updated Nov 13, 2026", 2026-11-14 읽음)
- [Workers 가격](https://developers.cloudflare.com/workers/platform/pricing/): 월 최소 $5. 요청 월 1,000만 포함 + 100만당 $0.30, CPU 월 3,000만 ms 포함 + 100만 ms당 $0.02. **서비스 바인딩 호출은 요청을 더 세지 않아요**(Pages `_worker.js` → Worker는 1건). Pages Functions도 Workers로 청구. **WebSocket 연결은 처음 업그레이드 1건, 오가는 메시지는 요청이 아니에요.**
- [Durable Objects 가격](https://developers.cloudflare.com/durable-objects/platform/pricing/): 요청 월 100만 포함 + 100만당 $0.15(HTTP · RPC · 알람 · WebSocket 연결 · **들어오는 메시지는 20개 = 1건**, **내보내는 메시지는 무료**). Duration 월 40만 GB-s 포함 + 100만 GB-s당 $12.50, 객체당 128 MB로 계산, **잠들 수 있는 상태의 대기 시간은 청구 안 함**. `setAlarm` 1번 = SQLite 쓰기 1행(월 5,000만 행 포함). 초과분은 다음 단위로 올림.
- 환율: 1달러 = 1,337.8원(2026-11-13 원/달러 종가, 네이버 증권 → 판세 `/api/market`) → **1,340원**으로 계산.

**가정** (모두 [`cost_model.py`](../../prototypes/realtime/cost_model.py)의 이름 있는 상수 — 바꾸고 다시 돌리면 표가 새로 나와요)
- 정규장 6.5시간 × 21거래일 = 491,400초/월, 동시 시청자 C명이 장중 내내.
- 다른 폴링(모든 안에서 같음): 시청자 1명당 분당 4.5건(지수 띠 30초, 등락 분포 60초, 공시 60초, 뉴스 3분).
- Worker CPU는 요청당 평균 1 ms(거의 엣지 캐시 적중) — **추정**.
- WebSocket 다시 연결: 시청자 1명당 시간당 4번(앱 전환 · 휴대폰 망 · 배포) — **추정**.
- 허브 duration은 최악(장중 내내 깨어 있음) = 61,425 GB-s. 알람 방식이면 실제로는 네이버를 기다리는 동안만(절반 안팎).

| 방식 | 동시 20명 | 동시 200명 | 동시 2,000명 | 네이버 호출/월 (시세) | 휴대폰 데이터 /시간 |
|---|---|---|---|---|---|
| 지금: 10초 폴링 · 엣지 8초 | ₩6,700 · Worker 1.7M | ₩9,594 · Worker 17.2M | ₩75,625 · Worker 172.0M | 61,425 × 데이터센터 수 | 13.0 MB |
| A: 5초 폴링 · 엣지 3초 | ₩6,700 · 2.7M | ₩13,545 · 27.0M | ₩117,768 · 270.3M | 163,800 × 데이터센터 수 | 26.0 MB |
| A′: 3초 폴링 · 엣지 2초 | ₩6,700 · 4.0M | ₩19,084 · 40.1M | ₩173,958 · 401.3M | 245,700 × 데이터센터 수 | 43.4 MB |
| **B/D: 허브 3초 + WebSocket** | **₩6,700** · 0.7M · DO 0.17M | **₩6,700** · 7.5M · DO 0.27M | **₩34,003** · 74.8M · DO 1.26M | **163,800 (1곳)** | **0.9~8.4 MB** |
| B/D: 허브 5초 + WebSocket | ₩6,700 · 0.7M · DO 0.11M | ₩6,700 · 7.5M · DO 0.21M | ₩33,989 · 74.8M · DO 1.19M | 98,280 (1곳) | 0.6~5.2 MB |
| C: SSE | B와 같음(연결 = 요청) | 같음 | 같음 | 같음 | 압축 안 되면 4~5배 |

읽는 법
- **허브 비용은 사실상 0이에요**: DO 요청은 알람(3초 → 월 163,800) + 연결뿐이고, duration은 허브 1~2개라 포함량(40만 GB-s)의 15~30%. 동시 2,000명에서 DO 초과는 0.26M → 올림해서 최대 $0.15.
- B의 동시 2,000명 ₩34,000은 **거의 다 "다른 폴링"(분당 4.5건)** 몫이에요(Worker 74.8M 중 73.7M, 연결은 1.1M). 3단계에서 지수 띠를 허브 델타로 옮기면 더 내려가요.
- **기본요금($5) 안에서 버티는 동시 시청자**: 지금 약 120명, B 약 260명.
- 네이버 호출: 데이터센터 1곳 기준으로 B 3초는 지금의 **2.7배**, 5초 1.6배, 7초(네이버 자기 간격) 1.14배. 지금도 시청자가 데이터센터 2곳에 퍼지면 지금 쪽이 2배라 B 3초는 1.3배. 이게 질문 3이에요.
- 장외 NXT 시간(08:00~09:00, 15:30~20:00)에 누가 보고 있으면 허브가 5초마다 → 알람 월 +83,160(비용 영향 없음).

---

## 4. 깨지는 곳과 대비

### 4-1. 허브 재시작 · 배포
- 허브는 장중 3초마다 깨어 있어서 거의 잠들지 않아요 → 새 코드는 "deferred, 최대 300초" 뒤 강제로 옮겨지고 그때 **모든 소켓이 끊겨요**([코드 갱신](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/)). 화면은 지터를 섞어 다시 붙고, 새 `epoch`를 보고 스냅숏을 받아요.
- **시안 실측**: 코드 다시 불러오기 → 화면이 0.5초 만에 "다시 연결하는 중", **2.5초 만에 새 epoch 스냅숏 + "실시간"**, 콘솔 오류 0(§8-4).
- 동시 2,000명이 한꺼번에 다시 붙으면: 요청 2,000건(무시할 만함) + 스냅숏 2,000번(직렬화는 버전마다 한 번만 하고 같은 글자를 보냄 — 시안 `this.snap` 캐시).
- 허브 메모리는 사라져도 돼요(다음 폴링이 스냅숏). 2단계에서 1분마다 마지막 스냅숏을 허브 저장소에 써 두면(월 8,211행) 재시작 직후에도 바로 줄 수 있어요.

### 4-2. 휴대폰 백그라운드 · 잠금
- 숨은 탭: **30초 유예** 뒤 닫아요(앱 잠깐 전환에 스냅숏을 다시 받지 않게). 다시 보이면 `?epoch=…&ver=…`로 이어 받기 → 허브가 최근 델타 40개(3초면 2분)를 갖고 있으면 그것만, 아니면 스냅숏(31 KB).
- 시안 실측: 6초 끊었다 이어 붙이기 → 스냅숏 없이 델타만(§8-4).
- 안드로이드가 소켓을 조용히 죽이는 경우: 화면이 **45초 동안 아무 메시지도 못 받으면** 다시 연결(허브는 조용할 때도 15초마다 `hb`), **10초 넘게 열리지 않는 연결**도 버리고 다시(시안에서 실제로 걸린 버그 — 서버가 재시작 중일 때 연결이 CONNECTING에 멈춰 `onclose`가 안 왔어요).

### 4-3. Pages 서비스 바인딩을 지나는 WebSocket
- `panse.pages.dev`의 `_worker.js`는 `env.API.fetch(request)` 한 줄이에요. **로컬 workerd에서 확인**: 같은 한 줄짜리 앞단 Worker(`prototypes/realtime/front/`)를 주 Worker로, 시안을 서비스 바인딩 뒤에 두고 `wrangler dev -c front/wrangler.toml -c wrangler.toml` — 업그레이드가 **101로 그대로 통과**, Chrome과 Node 클라이언트 모두 압축까지 협상됐어요. Pages Functions도 같은 런타임이라 운영에서도 될 가능성이 높지만, **운영 확인은 1단계 a에서** 해요(§9).
- 안 되면: 화면이 `wss://korea-market-heatmap.ssslot.workers.dev/api/live`로 직접 붙어요. WebSocket은 CORS 대상이 아니라서 브라우저가 막지 않고, Worker가 `Origin`이 허용 목록(`https://panse.pages.dev` 등)인지만 봐요. 그것도 안 되면 SSE(§2-3).

### 4-4. 네이버가 느리거나 실패
- 허브: 실패하면 간격을 6 → 12 → 30초로 늘리고 `{t:'st', ok:false}`를 방송. 화면은 마지막 값을 유지하고 "시세 지연"을 보여요. **30초 넘게 새 값이 없으면** 그 화면은 폴링으로 내려가요(폴링은 데이터센터마다 다른 경로라 허브 쪽 문제만이면 살아 있을 수 있어요).
- 허브는 한 곳에서 묻기 때문에 네이버가 그 출구를 막으면 모두가 동시에 멈춰요 — 그래서 대체 폴링을 지우지 않아요.

### 4-5. 휴장일 · 장 마감
- 허브 간격은 KST 시계로: 정규장 3초, NXT만 열린 시간 5초, 그 밖엔 폴링을 멈추고 `phase:'closed'`를 알려 화면이 연결을 닫고 지금처럼 60초 폴링으로.
- 평일 장 시간인데 휴장일이면: 두 지수가 CLOSE이고 2분 동안 아무 행도 안 바뀌면 60초로(기록기의 휴장 판단과 같은 생각, §3-15).

### 4-6. 남용
- `Origin` 확인(브라우저가 남의 사이트에서 붙는 것 차단), 허브당 소켓 5,000개 넘으면 503 → 그 화면은 폴링. 2단계에서 IP당 8개(`cf-connecting-ip`를 소켓 첨부에 저장).
- 화면이 보내는 메시지는 20개당 요청 1건이 청구되니, 허브는 `resume`·`snap` 말고는 무시하고 1분에 30개 넘게 보내는 소켓은 닫아요.
- 연결 하나의 비용 = Worker 1건 + DO 1건 — 연결 남발이 가장 비싼 공격이에요(그래도 100만 번에 $0.45).

### 4-7. 규모
- 시안: 허브 하나에 소켓 300개 → 연결 1.0초, 한 틱(600행 비교 + 300번 전송) 14 ms. 허브는 CPU가 아니라 duration으로 청구돼서 전송 수는 비용이 아니에요.
- 동시 5,000명을 넘으면: 허브 → 중계 DO 여러 개(해시로 나눔)로 펼치기. 지금은 필요 없어요.

### 4-8. 리플레이 기록기(cron)와의 관계
- 기록기는 매분 cron이 `quotesCore`로 네이버를 따로 불러요(월 8,211번). 허브는 **누가 보고 있을 때만** 돌기 때문에 기록기를 대신할 수 없어요 — cron은 그대로 믿을 수 있는 시계예요.
- 3단계: cron이 허브에 "지금 스냅숏"을 RPC로 물어요(`hub.frame()`): 10초 안의 값이 있으면 그걸 쓰고(네이버 호출 0, 기록 = 시청자가 본 값), 없으면 허브가 한 번 받아요. 허브가 응답하지 않으면 지금처럼 `quotesCore` 직접. **1단계에서는 cron · KV를 건드리지 않아요.**

---

## 5. 추천안의 API (질문 4)

### 5-1. 경로 (Worker `korea-market-heatmap`)
| 경로 | 응답 |
|---|---|
| `GET /api/live[?ch=top][&epoch=…&ver=…]` | **WebSocket만**(`Upgrade: websocket` 아니면 426, `ch`가 `top`이 아니면 400, 허용 안 된 `Origin`이면 403 — 허브까지 가지 않아서 DO 요청이 안 생겨요). `epoch`+`ver`가 있으면 이어 받기. **거절은 소켓으로 말해요**: 받아들인 뒤 `{t:'off', reason, retryAt}`를 보내고 4003으로 닫아요(HTTP 오류는 브라우저에 1006으로만 보여서 까닭을 못 읽어요) |
| `GET /api/live/state` | 허브 상태 JSON(데이터센터마다 60초 엣지 캐시, 차단기가 걸려 있으면 10분): `{ch, epoch, v, sockets, rows, pollMs, session:'open'\|'closed', polls, fails, upstreamMs, lastErr, lastBytes, lastRows, sent, snaps, refused, killSwitch, guard:{day, month, trip, trips, doRequests:{today, dayLimit, month, monthLimit}, connects:{today, dayLimit}, maxSockets, awakeMs:{…}, upstreamPolls:{today, month}, messagesToday}}` — 배포 점검 · 예산 확인용 |

`ch`는 `top` 하나뿐이에요(사용자 결정: 600행 = `/api/quotes`와 같은 종목). 다른 이름으로 DO가 생기지 않게 Worker가 막아요.

**`off` 이유와 다시 시도** (`retryAt` = ms, 화면은 그때까지 폴링)
| `reason` | 누가 | 언제 | `retryAt` | 같은 데이터센터가 기억(DO 요청 없이 답) |
|---|---|---|---|---|
| `closed` | Worker 시계 / 허브 | 주말 · 09:00 전 · 마감+2분 뒤 · 휴장일(09:05 뒤 두 지수 CLOSE + 오늘 체결 없음) | 다음 평일 09:00 | Worker 시계는 늘 DO 없이, 허브가 말하면 10분 |
| `full` | 허브 | 소켓 50개 | +5분 | 30초 |
| `budget` | 허브 | §12 상한에 닿음 | 다음 KST 자정(월 상한이면 다음 달 1일) | 10분 |
| `paused` | Worker / 허브 | KV `live:off` 끄개(§13-4) | +60초 | — (KV 읽기, 60초 캐시) |
| `error` | Worker | 허브 호출 실패 | +15초 | 15초 |

### 5-2. 메시지 (모두 JSON 글자 프레임, 허브 → 화면)
```jsonc
{"t":"hello","proto":1,"ch":"top","epoch":"mwf93jgr0uye","v":184,"poll":3000,"phase":"live","now":1794590000000}
{"t":"snap","ch":"top","epoch":"mwf93jgr0uye","v":184,"at":1794590000123,
 "body":{ /* /api/quotes 응답과 똑같은 모양: asOf, source, marketStatus, afterHours, nxt, index, stocks:[…] */ }}
{"t":"d","v":185,"b":184,"at":1794590003120,"asOf":"2026-11-16T10:02:31.412+09:00",
 "rows":[{"c":"005930","p":209500,"d":3500,"r":1.7},
         {"c":"000660","nx":{"p":1283000,"d":1000,"r":0.08}},
         {"c":"035420","lim":null}],                    // null = 그 키가 없어짐
 "ix":{"KOSPI":{"value":5403.7,"change":28.34,"ratio":0.53},"KOSDAQ":{…}},   // 바뀌었을 때만
 "ms":{"KOSPI":"OPEN","KOSDAQ":"OPEN"},                // 바뀌었을 때만 (marketStatus)
 "ah":false, "nxt":{"session":"reg","open":true}}     // 바뀌었을 때만
{"t":"hb","v":185,"at":1794590018000,"asOf":"…"}       // 15초 동안 바뀐 게 없을 때
{"t":"st","ok":false,"msg":"시세를 받지 못했어요","retryMs":6000,"at":…}   // 원천 실패
{"t":"off","reason":"budget","retryAt":1794668400000,"at":…}  // 끝 — 곧 4003으로 닫혀요. 화면은 이 메시지만으로 끝으로 봐요(§7-3)
```
화면 → 허브(선택, 평소엔 보내지 않음): `{"t":"resume","epoch":"…","v":184}`(URL 방식과 같음), `{"t":"snap"}`(버전이 어긋났을 때). 글자 `ping`엔 허브를 깨우지 않고 `pong`이 자동으로 와요.

### 5-3. 델타 규칙 (허브 `diffRow` = 화면 `applyPatch`의 짝, 시안 `test_delta.mjs` 12,000쌍 불일치 0)
- 행 모양은 **AGENTS §3의 `/api/quotes` 행 그대로** — 새 데이터 계약을 만들지 않아요.
- 패치 = `{c, …바뀐 키만}`. `null` = 키 삭제(예: 첫 체결 전 `op/hi/lo`, 상한가 풀림 `lim`). `nx`는 키마다 합치기, `nx:null` = NXT 값 사라짐, 처음 생기면 통째.
- **빠른 키(매 틱)**: `p d r lim op hi lo`, `nx.{p d r s o op hi lo}`. **느린 키(10틱 = 약 30초마다)**: `cap tv v`, `nx.{v tv t}`. 느린 키를 움직인 행에 얹어 보내는 방식(PIGGYBACK)은 델타가 1.6~2배라 끄고 시작(§8-3).
- 효과: 시총(`cap`)이 30초마다만 바뀌어서 **타일 크기·배치가 3초마다 흔들리지 않고 색과 숫자만** 바뀌어요(크기 기준 거래대금도 30초).
- 허브는 "화면이 가진 값"(보낸 것)만 기억해요 → 스냅숏 + 델타가 언제나 맞아떨어져요(보내지 않은 느린 키는 다음 느린 틱에 차이로 잡혀요).
- 버전: `d.b`(기준) = 화면의 `v`일 때만 적용, 아니면 `{t:'snap'}`. 허브가 새로 뜨면 `epoch`가 바뀌고 `v`가 1부터.
- 같은 행이 두 경로로 오면(델타와 `?codes=` 폴링) 지금 템플릿의 `fresher`(체결 시각이 더 최근인 쪽) 규칙이 그대로 이겨요.

### 5-4. 간격
| KST | 허브 간격 | 비고 |
|---|---|---|
| 평일 09:00 ~ 마감 + 2분 | **3초 = `LIVE_POLL_MS` 하나**(`worker/src/live_core.js`) | 마감은 시세의 `endTime`(보통 1530, 수능 · 첫 거래일 1630). 2분 더 받는 건 마감 동시호가 결과까지 보내려고 |
| 그 밖(NXT만 열린 시간 포함) · 주말 · 휴장일 | 허브 꺼짐 + `off: closed` | 화면은 지금처럼 폴링(NXT 시간은 10초, 밤은 60초). 사용자 결정의 "장 시간에만"을 따라 NXT 시간엔 허브를 쓰지 않아요 |
| 실패 | 6 → 12 → 30초 | `st` 방송 |
| 시청자 0 | 멈춤 | 다음 연결이 깨움 |

---

## 6. 배포 — `wrangler.toml` · 빌드 · 배포 스크립트 (질문 4)

> **구현됨 (1단계 a)** — 아래 6-1 · 6-2 · 6-3이 그대로 들어갔고, 더해서 **DO 클래스를 만드는 업로드는 푸시로는 절대 안 일어나요**: `deploy_worker.mjs`가 지금 돌고 있는 번들에 `MarketHub`가 없으면(= 만들기) `ALLOW_DO_LIFECYCLE=1`(Actions 손 실행의 `allow_do_lifecycle` 칸) 없이는 **아무것도 올리지 않고** 경고만 남겨요. 그 업로드는 스모크가 실패해도 되돌리기를 시도하지 않고(Cloudflare가 거절) "고쳐서 앞으로"라고 실패해요. `/api/live/state`는 스모크 뒤 경고로만 봐요(실시간은 덤 — 페이지는 폴링으로 돌아가요). `[exports.X] state = "deleted"` 같은 묘비도 그대로 올리고, 그것도 손 실행에서만. 점검 `node qa/worker/test_deploy_script.mjs`(API 흉내, 5/5).

### 6-1. `worker/wrangler.toml`에 더할 것
```toml
[[durable_objects.bindings]]
name = "MARKET"
class_name = "MarketHub"

[exports.MarketHub]          # 선언형 — 2026-06부터 새 DO 클래스에 권장, 태그를 따라다닐 필요 없음
type = "durable-object"
storage = "sqlite"
```
cron · KV는 그대로.

### 6-2. `scripts/build_worker.mjs` — 한 줄
`import { DurableObject } from 'cloudflare:workers'`를 esbuild가 못 찾아서 빌드가 실패해요(**실측**: "Could not resolve \"cloudflare:workers\""). `external: ['cloudflare:*']`를 넣으면 통과하고, 결과물에 `export { MarketHub }`가 남고, CI의 `node --check`도 통과해요(실측).

### 6-3. `scripts/deploy_worker.mjs` — 업로드 메타데이터
지금 (스크립트가 보내는 그대로):
```json
{"main_module":"worker.js","compatibility_date":"2026-11-01",
 "bindings":[{"type":"kv_namespace","name":"REPLAY","namespace_id":"bfdaeef6e5204d0ba223a568f76d3c85"}],
 "keep_bindings":["secret_text"]}
```
바뀐 뒤:
```json
{"main_module":"worker.js","compatibility_date":"2026-11-01",
 "bindings":[{"type":"kv_namespace","name":"REPLAY","namespace_id":"bfdaeef6e5204d0ba223a568f76d3c85"},
             {"type":"durable_object_namespace","name":"MARKET","class_name":"MarketHub"}],
 "exports":{"MarketHub":{"type":"durable-object","storage":"sqlite"}},
 "keep_bindings":["secret_text"]}
```
- 스크립트는 `wrangler.toml`에서 `[[durable_objects.bindings]]`(name, class_name)와 `[exports.X]`(type, storage)를 KV처럼 정규식으로 읽고, 없으면 지금과 똑같은 메타데이터를 보내요.
- **지금 경로로 DO를 만들 수 있어요**: 스크립트가 쓰는 `PUT /accounts/{id}/workers/scripts/{name}`(바로 배포되는 업로드)는 메타데이터의 `migrations`·`exports`를 받아요([multipart 메타데이터](https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/): "Except for `annotations`, these attributes are not available for version uploads" — 버전 업로드만 안 됨). wrangler 4.158 소스도 DO `exports`가 있으면 버전 API 대신 **바로 이 PUT**을 쓰고 메타데이터 최상위에 `exports`를 넣어요(`wrangler-dist/cli.js`의 `canUseNewVersionsDeploymentsApi` · `metadata3`). 그래서 **`wrangler deploy`가 꼭 필요하지 않아요.** 선언형이라 매 배포에 같은 블록을 보내면 되고, 태그를 읽는 단계가 없어요.
- 대안(선언형이 거절되면): 옛 방식 `"migrations":{"new_tag":"live-v1","steps":[{"new_sqlite_classes":["MarketHub"]}]}` — 단, 두 번째 배포부터는 `GET /accounts/{id}/workers/services/{name}`의 `default_environment.script.migration_tag`가 `live-v1`이면 빼야 해요(wrangler `getMigrationsToUpload`와 같은 일). 한 번 `exports`로 배포하면 `migrations`로 돌아갈 수 없어요.
- **되돌리기 주의**: DO 클래스가 생기는 배포를 넘어서는 되돌리기는 막혀요([Rollbacks](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)). 스크립트의 "스모크 실패 → 바로 앞 버전 100%"가 **첫 DO 배포에서만** 실패할 수 있어요. 그래서 첫 배포는 ① 허브를 아무 화면도 쓰지 않는 상태(어둡게)로 ② Actions에서 손으로(`workflow_dispatch`) ③ 사람이 지켜보며. 그 뒤 배포는 지금처럼 자동, 되돌리기도 정상.
- 스모크: `/api/time`에 더해 `/api/live/state?ch=top`이 200 JSON인지.
- 토큰: DO는 따로 권한이 없고 Worker 권한을 따라요([DO 권한](https://developers.cloudflare.com/workers/authorization/durable-objects/)) → 지금의 Account › Workers Scripts › Edit로 충분할 거예요(첫 배포에서 확인).
- Pages 프로젝트 `panse`는 바꾸지 않아요(§4-3이 통과하면).
- 로컬 개발: `wrangler dev`(workerd)는 이 샌드박스에서 네이버에 못 닿아요 → `quotesCore`의 polling 주소를 개발 전용 변수(`env.NAVER_POLL_BASE`, 기본 `https://polling.finance.naver.com`)로 바꿀 수 있게 하고, `prototypes/realtime/upstream_mock.mjs`(네이버 모양)를 가리켜요.

---

## 7. 화면 (질문 3)

### 7-1. 어디에 넣나
- 템플릿은 히트맵 담당 파일이고 지금 다른 작업이 열려 있어서, **웹소켓 로직은 새 모듈 `src/live/live.js`**(뉴스·해외처럼 빌드가 끼워 넣음)에 두고, 템플릿에는 작은 연결점만 요청해요:
  1. `KH.feed(body)` — `pollOnce`가 성공했을 때 하는 일(`setData` → `render` → `renderSide` … → `flashChanged`, `liveState.ok/last`)을 함수로 빼서, 폴링과 허브가 **같은 길**로 그리게.
  2. `KH.pausePoll(on)` — 허브가 살아 있는 동안 10초 타이머를 멈추고, 끄면 바로 한 번 받기. `KH.refresh()`(시계 누르기)는 그대로 한 번 받아요.
  3. `#status` 안의 표시 자리 `<span id="live-mark" hidden>` — 모듈이 상태를 그려요.
- 스냅샷 모드(`KH.MODE !== 'live'`)에선 모듈이 아무것도 하지 않아요. **스냅샷은 그대로.**
- `전체`(`scope=all`) · 다시 보기 중 · 해외/지표 탭: 1단계에선 허브 대신 지금 동작(전체는 15초 폴링). 다시 보기 중에도 연결은 유지하고 값만 쌓아요(지금 폴링도 그래요).

### 7-2. 저장소와 그리기
- 모듈은 마지막 `/api/quotes` 모양 본문(`snap.body`)을 들고, 델타를 `applyPatch`로 행에 적용한 뒤 `KH.feed(body)`. 템플릿의 정규화·`fresher`·가격 기준(KRX·NXT·통합)·플래시가 그대로 일해요.
- 플래시(§3-5)는 이미 "바뀐 타일만, 동시에 최대 60개"라 3초 틱에 맞아요. 3초마다 바뀌는 수가 줄어서 오히려 10초 폴링보다 덜 요란해요.
- 2단계: 느린 키가 안 바뀐 틱은 **배치 다시 계산 없이 색·글자만** 바꾸는 빠른 길(600타일 treemap 계산을 30초에 한 번으로). 1단계에선 360px 휴대폰에서 3초마다 `render`가 괜찮은지 `qa/perf.py`로 재요.

### 7-3. 연결 관리
- 다시 연결: 1 · 2 · 4 · 8 · 15 · 30초(±25% 지터), 3번 실패하면 "10초마다 갱신"(폴링)을 켜고 뒤에서 계속 시도(최대 5분 간격).
- **`{t:'off'}`를 받으면 그 자리에서 끝**: 화면이 스스로 소켓을 닫고 폴링으로, `retryAt`(+0~60초 지터) 전엔 다시 붙지 않아요. 닫힘 이벤트를 기다리지 않아요 — 로컬 `wrangler dev`에선 허브가 4003으로 닫아도 `close` 이벤트가 오지 않는 걸 봤어요(클라이언트는 CLOSING에 머묾, §13-3). `reason:'full'`이면 5분 뒤 한 번, `budget`·`closed`면 `retryAt`에.
- 숨은 탭 30초 유예 → 닫기, 보이면 이어 받기(§4-2). 45초 무소식 · 10초 넘는 연결 시도는 버리고 다시.
- 설정: `KH.addSetting({key:'live', label:'실시간 갱신', default:true})` — 끄면 지금 그대로(10초 폴링).
- 접근성: 상태 문구는 `aria-live="polite"`로 바뀔 때만 읽어요(3초마다 읽지 않게). `reduced`면 다시 연결 고리도 돌지 않아요.

### 7-4. 화면 문구 (영문 없이)
| 상태 | 머리글 표시(점 + 글자) | 말풍선 · 읽어 주는 글 |
|---|---|---|
| 연결됨 | 앰버 점 · **실시간** | "실시간으로 받고 있어요 · 바뀐 종목만 바로 바뀌어요 · 마지막 10:23:41" |
| 처음 연결 중 | 앰버 고리 · **연결하는 중** | "실시간 연결을 여는 중이에요" |
| 다시 연결 중 | 앰버 고리 · **다시 연결하는 중** | "연결이 잠깐 끊겼어요. 다시 붙는 중이에요" |
| 대신 폴링 | 회색 점 · **10초마다 갱신** | "실시간 연결이 안 돼서 10초마다 새로 받고 있어요" |
| 원천 지연 | 앰버 테 점 · **시세 지연** | "네이버 증권 시세를 받지 못해 다시 받는 중이에요 · 마지막 값 10:23:41" |
| 화면이 숨겨짐 | (보이지 않음) | — |
| 장 마감 · 주말 · 설정 끔 | 지금 문구 그대로("장 마감" 등) | — |
| 설정 | 이름 **실시간 갱신** | "켜면 바뀐 종목만 바로 받아요. 끄면 10초마다 새로 받아요. 휴대폰 데이터는 켤 때가 더 적게 들어요." |

- 점·고리는 **앰버**(인터페이스 상태, AGENTS §4) — 빨강·초록은 쓰지 않아요. 휴대폰은 점 + "실시간" 두 글자 폭만.
- "실시간"은 **허브에 연결돼 있을 때만** 써요(지금은 폴링 중에도 장중이면 "실시간" 배지가 떠요 — 1단계에서 문구를 이 표로 맞춰요).

---

## 8. 시안과 측정 (`prototypes/realtime/`, 로컬 전용)

### 8-1. 파일
| 파일 | 내용 |
|---|---|
| `src/worker.js` | Worker(`/api/live`, `/api/live/state`, 데모 화면) + `MarketHub` DO — 알람 폴링, 델타, 링(40), 이어 받기, 스냅숏 캐시, 상태. `quotesBody`는 지금 `quotesCore`·`nxtOf`·`ohlcInto`와 같은 규칙 |
| `src/client.html` | 데모 화면: 스냅숏 + 델타, 플래시, 다시 연결 · 지터 · 숨은 탭 · 무소식 감시, 상태 칩(§7-4 문구), 빨강 상승 · 초록 하락 · 앰버 강조 |
| `front/` | Pages `_worker.js`와 같은 한 줄짜리 앞단(서비스 바인딩 `API`) — 업그레이드 통과 확인용 |
| `upstream_mock.mjs` | 네이버 모양 서버: 실제 네이버 응답 1번을 바탕으로 실제 1분 기록(11/12)을 따라 가격이 움직이고, `--churn`으로 3초마다 흔들리는 비율을 올림. `--live`면 네이버 그대로 통과(장중, Node) |
| `bench.mjs` | WebSocket 클라이언트 N개: 메시지 크기(글자 · deflate · 실제 전송 바이트), 지연, 이어 받기 |
| `test_delta.mjs` | `diffRow`/`applyPatch` 왕복 점검 |
| `measure_upstream.py` | §1-4 네이버 측정 |
| `cost_model.py` | §3 표 |

### 8-2. 돌리는 법 (포트 8911 앞단 · 8912 네이버 모양 · 8913 검사기)
```
NODE_USE_ENV_PROXY=1 node prototypes/realtime/upstream_mock.mjs --port 8912 [--churn 0.3] [--live]
cd prototypes/realtime && npx wrangler dev -c front/wrangler.toml -c wrangler.toml --port 8911 --ip 127.0.0.1 --inspector-port 8913
#   → http://127.0.0.1:8911/ 데모 화면,  /api/live/state 허브 상태
node prototypes/realtime/bench.mjs --n 20 --secs 60 --resume
node prototypes/realtime/test_delta.mjs
끄기: fuser -k 8911/tcp 8912/tcp 8913/tcp   (wrangler 부모 프로세스가 workerd를 다시 띄우니 부모까지 끄기)
```
(wrangler 4.158.0, 호환 날짜 2026-11-01. `[exports.MarketHub]`를 `wrangler dev`가 받아요.)

### 8-3. 크기 (600행 `top`, 허브 3초, 클라이언트 5개 × 60초, permessage-deflate 협상됨)
| 흔들림 | 델타 행 중앙값 | 델타 중앙값 글자 → deflate | 느린 틱(p95) | 실제 전송 /분 (스냅숏 뺌) |
|---|---|---|---|---|
| 기록만(하한, `--churn 0`) | 26 | 2.4 KB → 0.66 KB | 600행 38.6 KB → 7.0 KB | **16 KB** |
| `--churn 0.3` | 356 | 24.2 KB → 5.4 KB | 72.5 KB → 14.2 KB | **110 KB** |
| `--churn 1.0`(상한, 거의 전 종목) | 441 | 29.4 KB → 6.9 KB | 80.4 KB → 17.0 KB | **143 KB** |
| 같은 조건 + 얹어 보내기(PIGGYBACK=1) | 358 / 444 | 40.2 → 8.2 / 50.1 → 10.5 KB | — | 183 / 226 KB |
| 비교: 지금 10초 폴링 | 600 전부 | `/api/quotes` gzip 37 KB × 6 | — | **222 KB** |

- 스냅숏: 144 KB 글자 → **31 KB**(deflate) ≈ `/api/quotes` gzip 37 KB. 연결할 때 한 번.
- 인코딩 비교(상한 델타 6개, 440행 안팎): 키 있는 객체 28.9 KB → 6.7 KB, 위치 배열 21.9 → 6.4 KB(**−5%**), 가격만 보내고 `d`·`r`은 화면이 계산 15.6 → 4.5 KB(**−33%**). → 1단계는 읽기 쉬운 객체 패치, 장중 측정에서 흔들림이 크면 3단계에서 "가격만".
- `전체`(2,701행, `--churn 0.3`, 3초): 스냅숏 460 KB → 115 KB, 델타 중앙값 1,420행 70 KB → 17 KB, **분당 340 KB**(지금 15초 폴링은 124 KB × 4 = 494 KB). 5초면 약 200 KB.
- 하한은 "1분 기록이 바뀌는 순간만" 움직이는 모형이라 실제보다 작고, 상한은 매 3초 거의 전 종목이 움직이는 모형이라 실제보다 커요. **실제 값은 §1-4 측정으로 이 표에 한 줄 더해요.**

### 8-4. 동작 확인
- 앞단 서비스 바인딩을 거친 WebSocket: **101 통과**, `permessage-deflate` 협상(Node `ws`, Chrome).
- 이어 받기: 6초 끊었다 `epoch`+`ver`로 → **스냅숏 없이 델타만**, 버전 건너뜀 0.
- 허브 재시작(코드 다시 불러오기): 0.5초 "다시 연결하는 중" → **2.5초 새 epoch 스냅숏 + "실시간"**. 콘솔 오류 0. 1440 · 768 · 390에서 가로 넘침 0.
- 소켓 300개: 연결 1.0초, 허브 한 틱 14 ms(로컬). 벤치 쪽 지연 중앙값 217 ms · p95 1.16초는 한 기계에서 클라이언트 300개가 매 틱 24 KB × 300을 풀고 다시 압축해 보는 벤치 자신의 몫이에요(클라이언트 5개일 땐 4~16 ms).
- 첫 실험에서 고친 것: 화면이 CONNECTING에 멈추면 영영 다시 시도하지 않던 문제(10초 제한 추가), 흉내 서버 해시가 마지막 자리만 다른 키를 몰아 흔들림이 안 생기던 문제.

---

## 9. 단계 계획

### 1단계 — 한 차례에 내보내기 (a → b 순서)
> **1단계 a는 구현됨(배포 전) — 실제 모양 · 첫 배포 · 확인 · 되돌리기는 §13.** 설계에서 바뀐 점: 사용자 결정으로 NXT만 열린 시간엔 허브를 쓰지 않고, 거절은 `{t:'off'}` 소켓으로, 상한은 §12.
**1a · Worker (Worker 담당, 어둡게 배포)**
- `worker/src/live.js`: 시안의 `MarketHub`를 옮기되 폴링은 `quotesCore(env, null, false, 8000)` 그대로(같은 행 · 같은 유니버스). KST 간격 표(§5-4), `phase:'closed'`, 휴장 감지, 백오프, Origin · 소켓 상한, 상태.
- `worker/src/index.js`: `/api/live`, `/api/live/state` 경로 + `export { MarketHub } from './live.js'`. 개발 전용 `env.NAVER_POLL_BASE`.
- `wrangler.toml`(§6-1), `build_worker.mjs`(§6-2), `deploy_worker.mjs`(§6-3: DO 바인딩 · `exports` · 스모크 `/api/live/state`).
- 점검: `qa/worker/test_live_delta.mjs`(= `test_delta.mjs`), `wrangler dev` + 흉내 서버로 연결 · 이어 받기 · 재시작.
- 배포: Actions 손 실행, 지켜보며(되돌리기가 이 배포를 못 넘어요). 직후 운영 확인 — `node prototypes/realtime/bench.mjs --url 'wss://panse.pages.dev/api/live?ch=top' --origin https://panse.pages.dev --n 2 --secs 30`(Pages 경유 WebSocket, §4-3). 장중이면 `measure_upstream.py`로 `POLL_MS` 확정.
- 이 시점엔 화면이 허브를 쓰지 않아서 사용자에게 보이는 변화 없음 · 비용 0(시청자 0이면 허브가 안 돌아요).

**1b · 화면 (히트맵 담당 + `src/live/` 모듈)**
- 템플릿 연결점 3개(§7-1) — 지금 열린 템플릿 작업이 병합된 뒤.
- `src/live/live.js`(+ 짧은 CSS): 시안 `client.html`의 연결 관리 · 패치 적용 · 상태 칩 · 설정. `build_page.py`가 news 다음에 끼워 넣음.
- 점검: 콘솔 0 · 가로 넘침 0(360 · 390 · 768 · 1280 · 1920), 허브 끊기 → 폴링으로 내려가기 → 다시 실시간, 숨은 탭 30초, `reduced`, 360px에서 3초 `render` 시간(`qa/perf.py`), 스냅샷 모드 변화 없음.

### 2단계
- `/api/quotes`를 허브 스냅숏으로 내주기(RPC, 엣지 3초) → 데이터센터마다 네이버를 부르던 일이 사라지고 **모든 화면이 같은 버전**. `ETag` = `epoch.v` → 밤 · 주말 60초 폴링이 304.
- 색 · 글자만 바꾸는 빠른 그리기(§7-2), 허브 마지막 스냅숏 저장(§4-1), IP당 소켓 상한.
- `전체` 채널(질문 2에서 하자고 하면, 5초).

### 3단계
- 기록기가 허브에게 묻기(§4-8), 지수 띠의 지수를 허브 델타로(`/api/market`은 5분 봉 `spark`만 드물게), 등락 분포를 `전체` 허브에서.
- 흔들림이 크게 측정되면 "가격만" 델타(−33%).
- 동시 5,000명 넘으면 중계 DO.

---

## 10. 위험

| 위험 | 크기 | 대비 |
|---|---|---|
| 네이버(비공식)가 한 출구의 잦은 호출을 막음 → 모두가 동시에 멈춤 | 중 | 간격을 측정으로 정하고(질문 3), 백오프, 폴링 대체를 지우지 않음(데이터센터마다 다른 출구) |
| 허브 하나 = 단일 지점 | 중 | 45초 무소식 → 폴링, 허브 상태 경로로 감시 |
| 배포마다 전원 재연결 | 낮 | 지터 · 스냅숏 캐시 · 2.5초 회복(실측) |
| 첫 DO 배포는 되돌리기 불가 | 중 | 어둡게 · 손으로 · 지켜보며(§6-3) |
| `exports` 메타데이터가 새 기능(2026-06) | 낮 | wrangler도 같은 PUT에 실어 보냄(소스 확인), 거절되면 `migrations` |
| Pages 경유 WebSocket이 운영에서 안 됨 | 낮 | workers.dev 직접 + Origin 확인, 그다음 SSE |
| 템플릿 동시 작업과 충돌 | 중 | 연결점 3개로 줄이고 로직은 새 모듈, 1b는 병합 뒤 |
| 3초 `render`가 저가 휴대폰에서 무거움 | 중 | 1b에서 측정, 2단계 빠른 길, 최악엔 설정 끄기 |
| 비용 · 데이터 추정의 가정(요청당 CPU 1 ms, 시간당 재연결 4번, 흔들림 비율) | 중 | 모두 `cost_model.py` 상수 · 1a 뒤 대시보드로 실제 값 교체 |

## 11. 사용자에게 물어볼 것 → 답 (2026-11-14 02:46)

**답**: ① 비용 상한 = **$5 기본요금 밖으로 0원**(→ §12 하드 상한) ② `전체` = **실시간 안 함**, 상위 300 × 2만 ③ 간격 = **추천대로 3초**, 평일 실측이 느리면 그 값. 아래는 물었던 그대로예요.


1. **월 비용 상한** — 추천안은 동시 약 260명까지 지금 기본요금($5 = ₩6,700) 안이고, 동시 2,000명이면 ₩34,000 안팎(그중 대부분은 원래 있던 다른 폴링)이에요. 넘으면 안 되는 금액이 있을까요?
2. **`전체`(2,700종목)도 실시간으로 할까요?** 하면 2단계에서 허브 하나 더(5초) — 네이버 호출이 한 틱에 4번으로 늘고, 대신 휴대폰 데이터는 지금 15초 폴링보다 적어요(분당 약 200~340 KB 대 494 KB). 안 하면 `전체`는 지금처럼 15초.
3. **네이버에 묻는 간격** — 3초(가장 빠름, 데이터센터 1곳 기준 지금의 약 2.7배) · 5초(1.6배) · 7초(네이버 자기 화면과 같은 간격, 1.1배) 중 어느 쪽이 마음 편하세요? 추천은 "장중 측정에서 네이버 값이 그만큼 자주 바뀌면 3초, 아니면 바뀌는 간격에 맞춤"이에요.

---

## 12. 예산 안전장치 — $5 밖으로 한 푼도 (사용자 결정 ①)

원칙: **추정이 아니라 구조와 상한으로 막아요.** 허브는 하나(`idFromName('top')`, 다른 이름은 Worker가 400), 장 시간에만, 소켓이 있을 때만 돌고, 세는 것은 허브 자신의 저장소(SQLite, KV 아님)에, 거절은 Worker가 Cache API(무료)로 기억해서 거절된 페이지가 DO 요청을 만들지 않아요. 상한은 `worker/src/live_core.js`의 `LIMITS` 한 곳.

### 12-1. 기대는 포함 사용량 (읽은 날 2026-11-14)
| 항목 | 월 포함량 | 출처 |
|---|---|---|
| Workers 요청 · CPU | 1,000만 · 3,000만 ms | [Workers 가격](https://developers.cloudflare.com/workers/platform/pricing/) (Last updated Nov 13, 2026) |
| DO 요청(HTTP · RPC · 알람 · WS 연결, 들어오는 WS 메시지는 20개 = 1건, 내보내는 메시지 무료) | 100만 | [DO 가격](https://developers.cloudflare.com/durable-objects/platform/pricing/) (Last updated Nov 13, 2026) |
| DO duration (객체당 128 MB, 잠들 수 있는 대기는 청구 안 함) | 40만 GB-s | 같은 쪽 |
| DO SQLite 쓰기 행 · 읽기 행 · 저장 (`setAlarm` 1번 = 쓰기 1행) | 5,000만 · 250억 · 5 GB-월 | 같은 쪽 |
| KV 읽기 · 쓰기 · 지우기 · 목록 · 저장 | 1,000만 · 100만 · 100만 · 100만 · 1 GB | [KV 가격](https://developers.cloudflare.com/kv/platform/pricing/) (Last updated Oct 30, 2026) |

### 12-2. 상한과 여유
| 자원 | 평소(가족 10명 안팎) | 구조상 최악 | 하드 상한 → 차단기 | 최악의 사용률 |
|---|---|---|---|---|
| **DO 요청** | 알람 7,800/일(6.5시간 ÷ 3초) × 21일 ≈ 16.4만 + 연결 수천 ≈ **17%** | 날마다 상한까지 | **하루 20,000**(KST 날) · **한 달 600,000**(KST 달) — 닿으면 `budget`: 모든 소켓에 알리고 닫고 알람 삭제, 다음 자정(달 상한이면 다음 달 1일)까지 거절 | 하루 상한은 청구 달이 언제 시작하든 31일 × 20,000 = **62%**. 걸린 뒤엔 데이터센터마다 연결 거절 10분에 1번 + 상태 10분에 1번만 허브까지 → 데이터센터 10곳이 계속 두드려도 +9만 → **71%** |
| 동시 소켓 | 몇 개 | — | **50** — 51번째는 `full`(데이터센터가 30초 기억) | — |
| 하루 연결 | 수백 | 다시 연결 고리(버그) | **2,000** → `budget` | DO 요청 안에 포함 |
| 페이지가 보내는 메시지 | 0 | 악성 | 소켓당 **20개** 넘으면 4008로 닫음(20개 = 요청 1건) | 연결 2,000 × 1건 = 2,000/일 이내 |
| **DO duration** | 알람 처리 중(네이버 기다림 ~1.2초 / 3초)만 ≈ 2.6시간/일 | 허브가 장 내내(09:00 ~ 16:32) 깨어 있음 | 깨어 있는 시간 프록시 **하루 8시간 · 한 달 200,000 GB-s** → `budget` | 31일 × 27,120초 × 0.125 GB = 10.5만 GB-s = **26%** (장이 아닌 날·시간엔 소켓이 없어 0) |
| DO SQLite 쓰기 | 일이 하나 끝날 때 1행 + 알람 1행 ≈ 1.6만/일 | 하루 상한까지 | 위 요청 상한이 함께 묶음 | ≤ 90만/월 = **1.8%** |
| DO 저장 | 상태 하나(약 1 KB) | 같음 | — | ≈ 0 |
| KV | 끄개 `live:off` 읽기: 연결 시도마다 1번(60초 캐시) + 허브 1분에 1번 · **쓰기 0** | — | — | 읽기 수천/월 ≪ 1,000만 · 쓰기 0 |
| Workers 요청 | 연결 · 상태 · 거절만(시세 폴링은 연결된 페이지에서 멈춰서 오히려 줄어요) | 페이지의 다시 시도 | 화면 규칙: `off`면 `retryAt`까지, 실패면 30초까지 늘린 뒤 5분 간격 | 지금 사이트 전체가 가족 10명 장중 내내 약 90만/월(9%) |
| 네이버 | 틱마다 2번(600종목 1번 + 지수 1번) | 장 내내 | 소켓이 없거나 장이 아니면 0 | ≤ 9,040틱/일 |

- **청구 달과 안 맞아도 안전**: 상한을 하루 단위로 두어서, 청구 달이 언제 시작하든 31일 동안 62%를 넘지 않아요. 달 상한(60%)은 그 위의 띠예요.
- 차단기가 걸리면 화면은 지금의 폴링으로 돌아가요 — 사이트는 멈추지 않아요.
- 셈은 청구 규칙과 같게: `fetch`·알람·내부 상태 = 1건, 들어오는 메시지 · 닫힘 = 1/20건(닫힘은 청구되는지 확실하지 않아 보수적으로 셈). 허브가 못 보는 요청(Worker가 거절한 것)은 DO 요청이 아니라서 세지 않아도 맞아요.
- 상한 · 사용량은 언제나 `GET /api/live/state`의 `guard`에서 봐요.

## 13. 1단계 a — 만든 것 · 첫 배포 · 확인 · 되돌리기

### 13-1. 파일
| 파일 | 내용 |
|---|---|
| `worker/src/live_core.js` | 순수 부품: `LIVE_POLL_MS = 3000`(하나뿐인 간격), `LIMITS`, KST 시계 · 장 창 · 다음 개장, 예산 셈(`newGuard`/`roll`/`charge`/`overBudget`), 델타 규칙(`diffRow`/`applyPatch`) |
| `worker/src/live.js` | `MarketHub`(보통 클래스 — `cloudflare:workers`를 import하지 않아 Node 점검이 `index.js`를 그대로 불러요), Worker 쪽 `liveRoute`(426/400/403, 시계 문지기, 거절 기억, KV 끄개, `off` 소켓), `/api/live/state` |
| `worker/src/index.js` | `export { MarketHub }`, `configureLive(quotesCore)`(허브가 `/api/quotes`와 같은 함수로 받음), 경로 2개, 개발 전용 `env.NAVER_POLL_BASE`, `getUniverse`가 Cache API 없이도 동작 |
| `worker/wrangler.toml` | `[[durable_objects.bindings]] MARKET → MarketHub`, `[exports.MarketHub] type="durable-object" storage="sqlite"` (cron · KV 그대로) |
| `scripts/build_worker.mjs` | `external: ['cloudflare:*']` |
| `scripts/deploy_worker.mjs` | DO 바인딩 + `exports`(묘비 포함)를 메타데이터에, 클래스 만들기·지우기는 `ALLOW_DO_LIFECYCLE=1`일 때만, 그 업로드는 되돌리기 시도 없음, `/api/live/state` 경고 점검 |
| `.github/workflows/deploy-worker.yml` | 손 실행 입력 `allow_do_lifecycle`(기본 꺼짐) → `ALLOW_DO_LIFECYCLE` |
| `qa/worker/test_live_core.mjs` | 상한이 포함량 안인지(62% · 60% · 50% · 26%), 장 창 · 다음 개장 · 자정 · 월말, 차단기 단계별, 평범한 하루 · 최악의 달 모의, 델타 왕복 24,000쌍 — **33/33** |
| `qa/worker/test_live_local.mjs` | `wrangler dev`(workerd) + 흉내 네이버 + `web/` — 426 · 400 · 403, hello → 스냅숏 600행 → 델타, 이어 받기, 소켓 상한(5번째 `full`, 6번째는 Worker 기억이 답해서 허브 거절 수 그대로), 하루 연결 상한 → `budget`으로 기존 페이지까지 닫힘 · 알람 멈춤, 주말 실제 시계로 `closed` + 월 09:00 — **16/16** |
| `qa/worker/test_deploy_script.mjs` | API 흉내: 푸시면 아무것도 안 올림 / 손 실행이면 메타데이터 정확 / 이후 푸시는 평소처럼 / 만드는 배포가 스모크 실패하면 되돌리기 시도 없이 실패 / 평소 배포는 되돌리기 — **5/5** |
| `qa/worker/live_probe.mjs` | 운영 확인용 한 연결 요약 + `/api/live/state` |

그 밖: 기존 `test_replay_recorder.mjs` 74/74, `test_disclosures_today.mjs` 16/16 그대로 통과(기록기 · KV 손대지 않음). **실제 Pages 코드**(`worker/pages/panse_worker.js`)를 앞단으로 세운 로컬 다중 Worker 실행에서도 업그레이드가 서비스 바인딩을 통과(101, 압축 협상, hello · 스냅숏 600 · 델타).

### 13-2. 첫 배포에 들어가야 하는 것 (오케스트레이터가 손으로)
1. `main`에 이 브랜치를 병합. **주의: 병합 푸시로 도는 배포 작업은 `MarketHub`가 새 클래스라서 아무것도 올리지 않고 경고만 남겨요 — 그리고 첫 DO 배포를 하기 전까지는 다른 Worker 변경의 자동 배포도 같은 이유로 멈춰 있어요.** 병합 직후 2번을 하세요.
2. GitHub Actions › `deploy-worker` › Run workflow › **`allow_do_lifecycle` 체크** › Run. (또는 로컬에서 `ALLOW_DO_LIFECYCLE=1 CLOUDFLARE_API_TOKEN=… node scripts/deploy_worker.mjs`.) 올라가는 것:
   - 번들: `index.js` + `live.js` + `live_core.js`(`var MarketHub=class…`, `export{MarketHub, … as default}`)
   - 메타데이터(로컬 `DRY_RUN=1` 출력 그대로):
     ```json
     {"main_module":"worker.js","compatibility_date":"2026-11-01",
      "bindings":[{"type":"kv_namespace","name":"REPLAY","namespace_id":"bfdaeef6e5204d0ba223a568f76d3c85"},
                  {"type":"durable_object_namespace","name":"MARKET","class_name":"MarketHub"}],
      "exports":{"MarketHub":{"type":"durable-object","storage":"sqlite"}},
      "keep_bindings":["secret_text"]}
     ```
   - 로그에 `do      lifecycle change for MarketHub`, `smoke … /api/time → 200`, `live    /api/live/state → 200 (sockets 0, DO requests today 1/20000, trip none)`가 보이면 끝.
3. 이 배포는 화면이 아직 허브를 쓰지 않아서(1단계 b 전) **사용자에게 보이는 변화 · 비용이 없어요**(시청자 0 → 허브 안 돎).

### 13-3. panse.pages.dev에서 확인
- 아무 때나: `curl -s https://panse.pages.dev/api/live/state` → 200, `guard.trip:null`, `killSwitch:false`.
- 장 밖(밤 · 주말): `node qa/worker/live_probe.mjs https://panse.pages.dev --secs 5` → `opened:true`, `extensions:"permessage-deflate"`, `off:{reason:"closed", retryAt:"… 09:00:00 KST"}`, `close 4003`. **이것만으로 업그레이드가 Pages 서비스 바인딩을 지난다는 확인**이고, 허브는 깨우지 않아요(DO 요청 0). 안 되면(`status: 4xx/5xx`) §4-3의 대안(workers.dev 주소로 직접).
- 평일 장중: 같은 명령 `--secs 30` → `hello`, `snapRows: 600`, `deltas` 약 10개(3초마다), `lagMsMedian` 수십 ms. 이어서 `/api/live/state` → `polls`가 늘고 `guard.doRequests.today`가 수십. 연결을 끊은 뒤 3초 안에 허브가 멈춰요(`sockets:0`, 다음 상태에서 `polls` 그대로).
- 같은 날 `measure_upstream.py`(§1-4)로 3초가 맞는지 → 다르면 `LIVE_POLL_MS` 한 줄만 바꿔요.
- 기록기는 그대로인지: `/api/replay/status`의 `result: wrote`.
- 로컬에서 본 것: 허브가 4003으로 닫아도 `wrangler dev`에선 클라이언트 `close` 이벤트가 오지 않았어요(CLOSING에 머묾 — 로컬 프록시가 TCP를 쥐고 있는 것으로 보여요). 운영에서도 `live_probe`의 `close`가 비어 있을 수 있어요 — 그래서 화면은 `off` 메시지로 끝을 판단해요(§7-3).

### 13-4. 끄기 · 되돌리기
- **배포 없이 끄기(권장 첫 수단)**: KV `REPLAY`에 키 `live:off`(값 아무거나) 쓰기 — 대시보드 › Workers & Pages › KV › 그 namespace › 키 추가, 또는 KV 편집 권한 토큰으로 `npx wrangler kv key put --namespace-id bfdaeef6e5204d0ba223a568f76d3c85 live:off 1 --remote`. 60초 안에 새 연결은 `paused`, 허브는 1분 안에 모든 소켓에 알리고 닫아요. 페이지는 폴링으로. 다시 켜기 = 키 지우기.
- **코드 되돌리기**: Cloudflare는 DO 클래스를 만든 배포 **이전** 버전으로는 되돌리지 못해요. 그 뒤 버전끼리는 지금처럼 되돌릴 수 있어요. 첫 DO 배포가 다른 것을 망가뜨렸다면 **고쳐서 앞으로**: `MarketHub` 클래스 · `[exports.MarketHub]` · 바인딩은 남기고 나머지를 되돌려 다시 배포(이때는 클래스가 이미 있으니 체크 없이 푸시로 돼요). 실시간만 문제면 위 끄개.
- **완전히 걷어내기**(나중에, 배포 2번): ① 경로를 빼고 클래스는 남긴 코드 배포 ② `[exports.MarketHub]`를 `state = "deleted"`로, 바인딩과 클래스 코드를 지우고 손 실행(`allow_do_lifecycle`) — 허브 저장소(상태 1 KB)도 지워져요.

### 13-5. 상한 숫자 한눈에
`LIVE_POLL_MS 3,000 ms` · 소켓 50 · DO 요청 하루 20,000 / 한 달 600,000 · 연결 하루 2,000 · 깨어 있는 시간 하루 8시간 / 한 달 1.6×10⁹ ms(=200,000 GB-s) · 소켓당 메시지 20 · 거절 기억 `full` 30초 · `closed`/`budget` 10분 · `paused` 60초 · `error` 15초 · 상태 캐시 60초(차단 중 10분) · 장 창 09:00 ~ 마감 + 2분.
