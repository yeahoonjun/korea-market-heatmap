// Name-matching regression (docs/standards/news.md §3): src/news/match.js on the real 2026-11-13 headlines (qa/news/fixtures/news.json)
// and on rule sentences. Candidates = common shares, as the page builds them from KH.stocks(): the default map (KOSPI · KOSDAQ top
// 300 by cap, data/snapshot.json) and 종목 수 "전체".
//   node qa/news/match_test.cjs        exit 1 on any failure
const path = require('path');
const ROOT = path.resolve(__dirname, '../..');
const M = require(path.join(ROOT, 'src/news/match.js'));
const snap = require(path.join(ROOT, 'data/snapshot.json'));
const news = require(path.join(__dirname, 'fixtures/news.json'));
const top = m => snap.stocks.filter(x => x.m === m && /0$/.test(x.c)).sort((a, b) => b.cap - a.cap).slice(0, 300);
const IDX600 = M.build([...top('K'), ...top('Q')]);
const IDXALL = M.build(snap.stocks.filter(x => /0$/.test(x.c)));
const name = new Map(snap.stocks.map(x => [x.c, x.n]));
const show = (t, idx) => { const m = M.match(t, idx); return m.marks.map(x => x.codes.map(c => name.get(c)).join('+')).join(' · '); };
const results = [];
const check = (n, ok, d = '') => { results.push(!!ok); console.log((ok ? 'PASS ' : 'FAIL ') + n + (d ? `  [${d}]` : '')); };

// 1 · real headlines: exactly these, no other (each checked by hand — 0 false matches)
const REAL600 = {
  'SK디스커버리, SK에코플랜트 지분 정산으로 4천200억 차익': 'SK디스커버리',
  '[인사] 미래에셋증권': '미래에셋증권',
  '이재용 회장, 삼전 지분 1.58→1.75% 확대…홍라희 여사 증여': '삼성전자',
  '롯데쇼핑, 호텔롯데서 김해 땅 635억에 산다': '롯데쇼핑',
  "교보증권, 3분기 순익 85억으로 '급감'…전분기 대비 90.6%↓": '교보증권',
  '삼양사, 3Q 영업익 176억…전년비 54.2%↓': '삼양사',
  '미래에셋증권, 런던증권거래소그룹과 AI 자산관리 서비스 강화 업무협약': '미래에셋증권',
  '오전엔 팔던 삼성전자 오후엔 ‘사자’…삼성전기 매수 1위 [주식 초고수는 지금]': '삼성전자 · 삼성전기',
  '비에이치아이, 3분기 영업익 403억원…전년 동기 대비 120%↑': '비에이치아이',
  '어제 사던 삼전닉스 오늘은 ‘팔자’…급락 한전 담았다 [주식 초고수는 지금]': '삼성전자+SK하이닉스 · 한국전력',
  '엔비디아 떨어져도 오르는 ‘삼전닉스’…“관건은 AI 투자 지속 여부”': '삼성전자+SK하이닉스',
  '[MK시그널] 슈프리마, AI 보안 플랫폼社 진화로 주가 상승세... MK시그널 추천 후 상승률 9.13% 기록': '슈프리마',
};
const REALALL_EXTRA = {
  "금호건설, 호실적에 상한가…우선주·금호전기도 '껑충'": '금호건설 · 금호전기',
  '풀무원, 3분기 영업익 40억원…전년 대비 90% 줄어': '풀무원',
  '금호건설 상한가…호실적에 호남 반도체 클러스터 기대': '금호건설',
  '제이엔비, 3분기 영업이익 5.8억 흑자전환…매출 48% 증가': '제이엔비',
  '씨티씨바이오, 3분기 누적 영업익 125억원… 전년比 182%↑ “수익성 성장 본격화”': '씨티씨바이오',
  '에브리봇, ‘키즈케어 로봇’ 사업화 속도…실버케어와 ‘케어로봇’ 양축 구축': '에브리봇',
  '[MK 골든크로스 돌파종목 : 서연탑메탈(019770) & 강남제비스코(000860)]': '서연탑메탈 · 강남제비스코',
};
for (const [label, idx, want] of [['기본 지도 600', IDX600, REAL600], ['종목 수 전체', IDXALL, { ...REAL600, ...REALALL_EXTRA }]]) {
  const got = {};
  for (const it of news.items) { const s = show(it.title, idx); if (s) got[M.clean(it.title)] = s; }
  const miss = Object.keys(want).filter(t => got[t] !== want[t]), extra = Object.keys(got).filter(t => !(t in want));
  check(`${label}: ${Object.keys(want).length} headlines marked as expected`, !miss.length, miss.map(t => `${t} → ${got[t] || '없음'} (기대 ${want[t]})`).join(' | '));
  check(`${label}: no other headline marked (no false match)`, !extra.length, extra.map(t => `${t} → ${got[t]}`).join(' | '));
}
check('real headlines: 12 / 90 on the default map, 19 / 90 with 전체', news.items.filter(it => show(it.title, IDX600)).length === 12 && news.items.filter(it => show(it.title, IDXALL)).length === 19);

// 2 · rule sentences (news.md §3 table + a few more)
const RULES = [
  ['삼성전자우 신고가', '', '우선주: 뒤 글자 "우"는 조사가 아니에요'],
  ['삼성전자서비스 노조 파업', '', '다른 회사: 뒤 글자가 조사가 아니에요'],
  ['삼성전자에서도 감원', '삼성전자', '조사 두 개(에서 + 도)'],
  ['삼성전자가 오른다', '삼성전자', '조사 하나'],
  ['[상보] 코스피 하락 마감', '', '"상보"는 두 글자 허용 목록 밖'],
  ['신흥 시장 자금 이탈', '', '"신흥" 흔한 낱말'],
  ['대상 기업 확대', '', '"대상" 흔한 낱말'],
  ['두산 그룹 지배구조 재편', '', '그룹 이름은 지주사로 잇지 않아요'],
  ['KTX 증편', '', '영문 3글자 + 앞뒤가 영문 · 숫자가 아니어야'],
  ['테스트 결과 공개', '', '"테스" 뒤 "트"는 조사가 아니에요'],
  ['한전발 훈풍에 유틸리티 강세', '한국전력', '별칭 + 조사 "발"'],
  ['기아차 판매 호조', '', '옛 이름은 별칭에 없어요'],
  ['신세계 백화점 매출', '', '금지 목록'],
  ['우진, 3분기 영업익 24억원…전분기 대비 193% 급증', '', '두 글자 · 허용 목록 밖'],
  ['SK하이닉스 신고가', 'SK하이닉스', '긴 이름이 먼저(SK 아님)'],
  ['SK 그룹 리밸런싱', '', 'SK는 두 글자 영문'],
  ['네이버 웹툰 상장 추진', 'NAVER', '별칭'],
  ['삼성전자·SK하이닉스·LG에너지솔루션·현대차 동반 상승', '삼성전자 · SK하이닉스 · LG에너지솔루션', '한 제목에 최대 3개, 제목 순서'],
  ['삼성전자 삼성전자 또 삼성전자', '삼성전자', '같은 종목은 한 번'],
  ['﻿삼성전자​가 반등', '삼성전자', '보이지 않는 글자 지우고 찾아요'],
];
for (const [t, want, why] of RULES) { const got = show(t, IDX600); check(`"${t}" → ${want || '표시 안 함'} (${why})`, got === want, got || '표시 안 함'); }
const hlb = M.match('HLB생명과학 급등', IDX600).marks.flatMap(x => x.codes);
check('"HLB생명과학 급등" never marks HLB (뒤 글자)', !hlb.includes('028300'), hlb.map(c => name.get(c)).join());
check('"금호건설, 호실적에 상한가" → 기본 지도 표시 안 함 · 전체면 금호건설', show("금호건설, 호실적에 상한가…", IDX600) === '' && show("금호건설, 호실적에 상한가…", IDXALL) === '금호건설');
// 3 · speed (§10): 2,600 candidates × 90 headlines
const t0 = process.hrtime.bigint();
for (let k = 0; k < 10; k++) for (const it of news.items) M.match(it.title, IDXALL);
const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 10;
check('90 headlines × 2,589 names under 50 ms (node)', ms < 50, ms.toFixed(1) + ' ms');
const bad = results.filter(r => !r).length;
console.log(`\n${results.length - bad}/${results.length} passed`);
process.exit(bad ? 1 : 0);
