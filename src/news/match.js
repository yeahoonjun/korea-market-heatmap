/* 판세 시장 뉴스 — 헤드라인 속 지도 종목 이름 찾기 (docs/standards/news.md §3). drafts/news.html의 NEWS_MATCH 그대로.
   window.KHNewsMatch = { build(rows) → idx, match(title, idx, max = 3) → {text, marks:[{i, j, codes}]}, clean, PARTICLES, ALLOW2, DENY, ALIAS }
   rows = [{c: 코드, n: 종목명}] — 지도에 그리는 보통주(KH.stocks()), 시장 탭과 상관없이. Node에서도 require로 읽혀요(QA). */
(function (root) {
'use strict';
const NEWS_MATCH = (() => {
  // 이름 뒤에 붙어도 되는 조사(한두 개 이어져도 돼요): 삼성전자가 · 삼성전자에서도 · 한전발
  const PARTICLES = ['으로', '에서', '에게', '까지', '부터', '보다', '처럼', '이나', '이란', '이며', '은', '는', '이', '가', '을', '를', '의', '도', '와', '과', '에', '만', '로', '나', '엔', '발', '측'];
  // 두 글자 이름은 이 목록만(흔한 낱말 · 그룹 이름이 많아서): 상보 · 신흥 · 전방 · 태양 · 동양 · 대상 · 두산 · 한화 …는 빠져요
  const ALLOW2 = new Set(['기아', '농심', '한샘', '한섬', '휴젤', '파두', '루닛', '안랩', '씨젠', '웹젠', '툴젠', '심텍', '한컴', '엔켐', '고영', '다날', '하림',
    '풍산', '영풍', '후성', '테스', '천보', '원텍', '바텍', '스맥', '태웅', '삼현', '미코', '금양', '노타', '피노', '태성', '대웅', '뷰노', '쏘카', '엠로', '엑셈', '넵튠', '샘표', '한독', '팬젠', '휴럼', '퓨릿']);
  // 세 글자 이상이지만 흔한 낱말 · 그룹 이름과 겹치는 것
  const DENY = new Set(['신세계', '우리로', '엘리스', '미래산업', '모나리자', '포스코', '대한', '한국']);
  // 다른 이름(별칭) → 코드. 사이트 이름(n)과 달리 기사에서 흔히 쓰는 이름. 같은 경계 규칙을 따라요. 후보에 그 종목이 있을 때만.
  const ALIAS = { '네이버': ['035420'], '한전': ['015760'], '하이닉스': ['000660'], '현대자동차': ['005380'], '에쓰오일': ['010950'], 'LS일렉트릭': ['010120'],
    'LG엔솔': ['373220'], '삼성바이오': ['207940'], '삼전': ['005930'], '삼전닉스': ['005930', '000660'], 'JYP': ['035900'] };
  const HAN = /[가-힣]/, WORD = /[가-힣A-Za-z0-9]/;
  const clean = s => String(s || '').normalize('NFC').replace(/[﻿​-‍⁠]/g, '').replace(/\s+/g, ' ').trim();
  function okRight(t, j) {
    if (j >= t.length || !WORD.test(t[j])) return true;
    if (!HAN.test(t[j])) return false;                    // 이름 뒤에 영문 · 숫자가 이어지면 다른 이름이에요 (HLB생명과학 X, KTX X)
    let k = j, n = 0;
    while (k < t.length && n < 2) {                        // 조사 한두 개
      const p = PARTICLES.find(q => t.startsWith(q, k)); if (!p) break;
      k += p.length; n++;
      if (k >= t.length || !WORD.test(t[k])) return true;
    }
    return false;
  }
  const okLeft = (t, i) => i === 0 || !WORD.test(t[i - 1]);
  // 후보 만들기: 지도에 있는 종목(행 {c, n})으로 한 번. 이름 길이 긴 것부터.
  function build(rows) {
    const byCode = new Map(rows.map(r => [r.c, r]));
    const cand = [];
    for (const r of rows) {
      const n = clean(r.n);
      if (!n || DENY.has(n)) continue;
      const latin = /^[A-Za-z0-9&.\- ]+$/.test(n);
      if (latin ? n.replace(/[^A-Za-z0-9]/g, '').length < 3 : n.length < 3 && !ALLOW2.has(n)) continue;
      cand.push({ key: n, codes: [r.c] });
    }
    for (const [k, cs] of Object.entries(ALIAS)) { const codes = cs.filter(c => byCode.has(c)); if (codes.length) cand.push({ key: k, codes }); }
    cand.sort((a, b) => b.key.length - a.key.length);
    return { cand, byCode };
  }
  // 헤드라인 → {text, marks:[{i, j, codes}]} (겹치지 않게, 앞에서부터, 한 종목은 한 번, 최대 3개)
  function match(title, idx, max = 3) {
    const t = clean(title), taken = new Uint8Array(t.length), marks = [], seen = new Set();
    for (const c of idx.cand) {
      let from = 0;
      while (true) {
        const i = t.indexOf(c.key, from); if (i < 0) break;
        const j = i + c.key.length; from = i + 1;
        if (taken.subarray(i, j).some(Boolean) || !okLeft(t, i) || !okRight(t, j)) continue;
        if (c.codes.every(x => seen.has(x))) continue;
        taken.fill(1, i, j); c.codes.forEach(x => seen.add(x));
        marks.push({ i, j, codes: c.codes.filter(Boolean) }); break;
      }
    }
    marks.sort((a, b) => a.i - b.i);
    return { text: t, marks: marks.slice(0, max) };
  }
  return { build, match, clean, PARTICLES, ALLOW2, DENY, ALIAS };
})();
if (typeof module === 'object' && module && module.exports) module.exports = NEWS_MATCH;
if (root) root.KHNewsMatch = NEWS_MATCH;
})(typeof window !== 'undefined' ? window : null);
