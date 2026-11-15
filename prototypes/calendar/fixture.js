// 증시 캘린더 시제품 — 예시 데이터 (빌드에 들어가지 않아요).
// 지표 · 금리 · 시장 일정은 docs/standards/calendar.md §2에서 확인한 실제 일정이에요(2026-11-15 확인).
// 회사 일정(k:'corp')은 모양을 보이려는 가짜 회사 이름이에요 — 실제 회사 · 실제 공시가 아니에요.
// 시각: src 시각(tz) → 화면이 KST로 바꿔요. 이 기간(2026-11-16 ~ 12-31)은 미국 표준시라 ET = UTC−5, CT = UTC−6.
window.CAL_FIXTURE = {
  now: '2026-11-16T09:12:00+09:00',           // 예시 "지금" (월요일 장중)
  asOf: '2026-11-16T09:10:00+09:00',
  sources: {
    bok: { ok: true, at: '2026-11-16 06:05', label: '한국은행 통계공표일정' },
    fred: { ok: true, at: '2026-11-16 06:05', label: 'FRED 발표 일정' },
    manual: { ok: true, at: '2026-11-15', label: '금통위 · FOMC · 휴장(직접 입력)' },
    dart: { ok: true, at: '2026-11-16 09:10', label: 'OpenDART' },
    fsc: { ok: true, at: '2026-11-13 13:40', label: '금융위원회(예탁결제원 자료, 다음 영업일 13시 이후)' },
  },
  // 날 표시: 휴장 · 특별 운영
  days: {
    '2026-11-19': { note: '수능 · 정규장 10:00–16:30', kind: 'special' },
    '2026-12-25': { note: '휴장 · 성탄절', kind: 'closed' },
    '2026-12-31': { note: '휴장 · 연말 (거래소 공지 전, 예정)', kind: 'closed', tentative: true },
  },
  events: [
    // ── 지난 일정 (달력이 비어 보이지 않게 — 모두 실제 일정)
    { id: 'kr-gdp-1027', d: '2026-10-27', t: '08:00', k: 'kr', star: 3, title: '3/4분기 실질 국내총생산(속보)', src: 'bok' },
    { id: 'fomc-1028', d: '2026-10-29', t: '03:00', orig: '미국 동부 10월 28일 오후 2:00', origShort: '미국 14:00', k: 'cb', star: 3, title: 'FOMC 금리 결정', sub: '10월 27~28일 회의 · 미국 서머타임이라 03:00', src: 'manual', url: 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm' },
    { id: 'kr-bop-1105', d: '2026-11-05', t: '08:00', k: 'kr', star: 2, title: '9월 국제수지(잠정)', src: 'bok' },
    { id: 'us-emp-1106', srcD: '2026-11-06', srcT: '07:30', tz: 'CT', k: 'us', star: 3, title: '미국 고용보고서', rid: 50, src: 'fred' },
    { id: 'us-cpi-1110', srcD: '2026-11-10', srcT: '07:30', tz: 'CT', k: 'us', star: 3, title: '미국 소비자물가(CPI)', rid: 10, src: 'fred' },
    { id: 'opt-1112', d: '2026-11-12', t: '15:20', k: 'mkt', star: 2, title: '옵션 만기 (11월물)', sub: '코스피200 옵션 · 둘째 목요일', src: 'rule' },
    { id: 'kr-xmp-1113', d: '2026-11-13', t: '06:00', k: 'kr', star: 2, title: '10월 수출입물가지수(잠정)', src: 'bok' },
    { id: 'kr-m2-1113', d: '2026-11-13', t: '12:00', k: 'kr', star: 1, title: '9월 통화 및 유동성', src: 'bok' },
    { id: 'us-ppi-1113', srcD: '2026-11-13', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 생산자물가(PPI)', rid: 46, src: 'fred' },

    // ── 금리 (직접 입력: 한국은행 결정회의 목록 · 연준 FOMC 달력)
    { id: 'bok-1126', d: '2026-11-26', k: 'cb', star: 3, title: '금통위 통화정책방향 결정', sub: '기준금리 결정 · 올해 마지막', src: 'manual', url: 'https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2026' },
    { id: 'bok-min-1215', d: '2026-12-15', k: 'cb', star: 2, title: '금통위 의사록 공개 (11월 26일 회의)', sub: '규칙으로 계산 · 회의 2주 뒤 첫 화요일', src: 'rule', tentative: true, url: 'https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2026' },
    { id: 'fomc-1209', srcD: '2026-12-09', srcT: '14:00', tz: 'ET', k: 'cb', star: 3, title: 'FOMC 금리 결정', sub: '12월 8~9일 회의 · 경제전망(SEP) 함께', src: 'manual', url: 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm' },
    { id: 'fomc-min-1230', srcD: '2026-12-30', srcT: '14:00', tz: 'ET', k: 'cb', star: 2, title: 'FOMC 의사록 (12월 회의)', sub: '결정 3주 뒤', src: 'rule', tentative: true, url: 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm' },

    // ── 한국 지표 (한국은행 통계공표일정, 시각은 공표 시각)
    { id: 'kr-hhc', d: '2026-11-18', t: '12:00', k: 'kr', star: 2, title: '3/4분기 가계신용(잠정)', src: 'bok' },
    { id: 'kr-iip', d: '2026-11-19', t: '12:00', k: 'kr', star: 1, title: '3/4분기 국제투자대조표', src: 'bok' },
    { id: 'kr-ppi', d: '2026-11-20', t: '06:00', k: 'kr', star: 1, title: '10월 생산자물가지수(잠정)', src: 'bok' },
    { id: 'kr-hhd', d: '2026-11-20', t: '12:00', k: 'kr', star: 1, title: '3/4분기 차주별 가계부채', src: 'bok' },
    { id: 'kr-ccsi', d: '2026-11-24', t: '06:00', k: 'kr', star: 2, title: '11월 소비자동향조사(CCSI)', src: 'bok' },
    { id: 'kr-bsi', d: '2026-11-25', t: '06:00', k: 'kr', star: 2, title: '11월 기업경기조사 · 경제심리지수', src: 'bok' },
    { id: 'kr-rate', d: '2026-11-25', t: '12:00', k: 'kr', star: 1, title: '10월 금융기관 가중평균금리', src: 'bok' },
    { id: 'kr-loan', d: '2026-12-04', t: '12:00', k: 'kr', star: 1, title: '3/4분기 예금취급기관 산업별대출금', src: 'bok' },
    { id: 'kr-bop', d: '2026-12-08', t: '08:00', k: 'kr', star: 2, title: '10월 국제수지(잠정)', src: 'bok' },
    { id: 'kr-gni', d: '2026-12-09', t: '08:00', k: 'kr', star: 2, title: '3/4분기 국민소득(잠정)', src: 'bok' },
    { id: 'kr-m2', d: '2026-12-15', t: '12:00', k: 'kr', star: 1, title: '10월 통화 및 유동성', src: 'bok' },
    { id: 'kr-xmp', d: '2026-12-15', t: '06:00', k: 'kr', star: 2, title: '11월 수출입물가지수(잠정)', src: 'bok' },
    { id: 'kr-ppi12', d: '2026-12-22', t: '06:00', k: 'kr', star: 1, title: '11월 생산자물가지수(잠정)', src: 'bok' },
    { id: 'kr-ccsi12', d: '2026-12-24', t: '06:00', k: 'kr', star: 2, title: '12월 소비자동향조사(CCSI)', src: 'bok' },
    { id: 'kr-bsi12', d: '2026-12-29', t: '06:00', k: 'kr', star: 2, title: '12월 기업경기조사 · 경제심리지수', src: 'bok' },

    // ── 미국 지표 (FRED 발표 일정 — 날짜는 API, 시각은 FRED 달력의 미국 중부시간 표를 따로 둬요)
    { id: 'us-rs', srcD: '2026-11-17', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 소매판매', rid: 9, src: 'fred' },
    { id: 'us-ip', srcD: '2026-11-17', srcT: '10:15', tz: 'CT', k: 'us', star: 1, title: '미국 산업생산 · 설비가동률', rid: 13, src: 'fred' },
    { id: 'us-hs', srcD: '2026-11-18', srcT: '07:30', tz: 'CT', k: 'us', star: 1, title: '미국 주택착공 · 허가', rid: 27, src: 'fred' },
    { id: 'us-cl1', srcD: '2026-11-19', srcT: '07:30', tz: 'CT', k: 'us', star: 1, title: '미국 주간 신규 실업수당 청구', rid: 180, src: 'fred' },
    { id: 'us-um', srcD: '2026-11-20', srcT: '10:00', tz: 'CT', k: 'us', star: 1, title: '미국 미시간대 소비자심리', rid: 91, src: 'fred' },
    { id: 'us-gdp', srcD: '2026-11-25', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 GDP', rid: 53, src: 'fred' },
    { id: 'us-pce', srcD: '2026-11-25', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 개인소득 · 소비지출(PCE)', rid: 54, src: 'fred' },
    { id: 'us-nhs', srcD: '2026-11-25', srcT: '09:00', tz: 'CT', k: 'us', star: 1, title: '미국 신규주택판매', rid: 97, src: 'fred' },
    { id: 'us-jolts', srcD: '2026-12-01', srcT: '09:00', tz: 'CT', k: 'us', star: 2, title: '미국 구인 · 이직(JOLTS)', rid: 192, src: 'fred' },
    { id: 'us-emp', srcD: '2026-12-04', srcT: '07:30', tz: 'CT', k: 'us', star: 3, title: '미국 고용보고서', sub: '비농업 고용 · 실업률', rid: 50, src: 'fred' },
    { id: 'us-cpi', srcD: '2026-12-10', srcT: '07:30', tz: 'CT', k: 'us', star: 3, title: '미국 소비자물가(CPI)', rid: 10, src: 'fred' },
    { id: 'us-ppi', srcD: '2026-12-15', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 생산자물가(PPI)', rid: 46, src: 'fred' },
    { id: 'us-rs12', srcD: '2026-12-16', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 소매판매', rid: 9, src: 'fred' },
    { id: 'us-gdp12', srcD: '2026-12-23', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 GDP', rid: 53, src: 'fred' },
    { id: 'us-pce12', srcD: '2026-12-23', srcT: '07:30', tz: 'CT', k: 'us', star: 2, title: '미국 개인소득 · 소비지출(PCE)', rid: 54, src: 'fred' },

    // ── 시장 (규칙: 코스피200 선물 · 옵션 만기 = 결제월 두 번째 목요일, 위클리 = 월 · 목)
    { id: 'wk-1116', d: '2026-11-16', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', sub: '코스피200 월요일물', src: 'rule', weekly: true },
    { id: 'wk-1119', d: '2026-11-19', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목)', sub: '코스피200 목요일물', src: 'rule', weekly: true },
    { id: 'csat', d: '2026-11-19', t: '10:00', k: 'mkt', star: 2, title: '수능일 · 1시간 늦게 개장', sub: '정규장 10:00–16:30 · 애프터마켓 17:00–20:00', src: 'manual' },
    { id: 'wk-1123', d: '2026-11-23', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'wk-1126', d: '2026-11-26', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목)', src: 'rule', weekly: true },
    { id: 'wk-1130', d: '2026-11-30', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'wk-1203', d: '2026-12-03', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목)', src: 'rule', weekly: true },
    { id: 'wk-1207', d: '2026-12-07', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'quad-1210', d: '2026-12-10', t: '15:20', k: 'mkt', star: 3, title: '선물 · 옵션 동시만기', sub: '코스피200 선물 · 옵션 12월물 마지막 거래일 · 15:20 마감', src: 'rule' },
    { id: 'wk-1214', d: '2026-12-14', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'wk-1217', d: '2026-12-17', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목)', src: 'rule', weekly: true },
    { id: 'wk-1221', d: '2026-12-21', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'wk-1224', d: '2026-12-24', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목)', src: 'rule', weekly: true },
    { id: 'wk-1228', d: '2026-12-28', k: 'mkt', star: 1, title: '위클리 옵션 만기 (월)', src: 'rule', weekly: true },
    { id: 'wk-1230', d: '2026-12-30', k: 'mkt', star: 1, title: '위클리 옵션 만기 (목→수)', sub: '31일 휴장이면 앞당겨요', src: 'rule', weekly: true, tentative: true },
    { id: 'last-1230', d: '2026-12-30', k: 'mkt', star: 2, title: '올해 마지막 거래일', sub: '거래소 공지 전 · 예정', src: 'manual', tentative: true },

    // ── 회사 (예시 — 가짜 회사 이름)
    { id: 'c1', d: '2026-11-16', k: 'corp', star: 2, c: '900001', n: '예시바이오', title: '무상증자 신주배정기준일', sub: '1주당 1주 · 신주 상장 12월 4일', src: 'dart', api: 'fricDecsn', watch: true },
    { id: 'c2', d: '2026-11-18', t: '16:00', k: 'corp', star: 2, c: '900002', n: '가나전자', title: '기업설명회(IR)', sub: '3분기 실적 설명 · 원문에서 읽은 날짜', src: 'dart', api: 'document' },
    { id: 'c3', d: '2026-11-19', k: 'corp', star: 2, c: '900003', n: '다라화학', title: '보호예수 해제 412만 주', sub: '상장주식의 6.1% · 상장 6개월', src: 'fsc', api: 'getLockUpRetuInfo_V3', pct: 6.1 },
    { id: 'c4', d: '2026-11-20', k: 'corp', star: 1, c: '900004', n: '마바증권', title: '유상증자 구주주 청약', sub: '20~21일 · 납입 27일', src: 'dart', api: 'estkRs' },
    { id: 'c5', d: '2026-11-24', t: '09:00', k: 'corp', star: 1, c: '900005', n: '사아에너지', title: '임시주주총회', src: 'dart', api: 'document' },
    { id: 'c6', d: '2026-11-27', k: 'corp', star: 1, c: '900002', n: '가나전자', title: '분기 배당금 지급', sub: '1주당 361원', src: 'fsc', api: 'getDiviInfo_V2' },
    { id: 'c7', d: '2026-11-30', k: 'corp', star: 3, c: '900007', n: '자차바이오', title: '보호예수 해제 2,150만 주', sub: '상장주식의 18.4% · 상장 1년', src: 'fsc', api: 'getLockUpRetuInfo_V3', pct: 18.4, watch: true },
    { id: 'c8', d: '2026-12-04', k: 'corp', star: 1, c: '900001', n: '예시바이오', title: '무상증자 신주 상장', src: 'dart', api: 'fricDecsn', watch: true },
    { id: 'c9', d: '2026-12-31', k: 'corp', star: 2, group: 37, title: '결산 배당 기준일', sub: '37개 종목 · 누르면 목록', src: 'fsc', api: 'getDiviInfo_V2' },
  ],
};
