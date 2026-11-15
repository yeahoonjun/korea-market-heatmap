// Writes qa/policy/fixtures/policy.json — the real worker/src/policy.js output over the KDI fixture (fixtures/kdi.xml) and a small
// fake gazette (titles marked "(시험)", agencies / 편집구분 like the portal's fields), for the page mock (qa/policy/mock_api.py).
//   node qa/policy/make_fixture.mjs
import { readFileSync, writeFileSync } from 'node:fs';

const HERE = new URL('.', import.meta.url);
const KDI_XML = readFileSync(new URL('fixtures/kdi.xml', HERE), 'utf8');
const NOW = Date.parse('2026-11-13T09:30:00Z');          // 금 18:30 KST
Date.now = () => NOW;
const DAYS = {
  20261113: [['금융위원회', '고시', '금융투자업규정 일부개정고시 (시험)'], ['재정경제부', '고시', '외국환거래규정 일부개정 (시험)'], ['보건복지부', '고시', '의료급여 기준 (시험)'],
    ['한국은행', '공고', '한국은행 통화안정증권 발행 공고 (시험)'], ['산업통상부', '고시', '수출입 공고 일부개정 (시험)'], ['재정경제부', '인사', '인사 발령 (시험)'],
    ['공정거래위원회', '고시', '하도급거래 공정화 지침 일부개정 (시험)'], ['국세청', '고시', '부가가치세 사무처리규정 (시험)'], ['국토교통부', '고시', '도시관리계획 결정 (시험)']],
  20261112: [['관세청', '고시', '관세평가 운영에 관한 고시 일부개정 (시험)'], ['금융위원회', '공고', '자본시장법 시행령 입법예고 (시험)'], ['기획예산처', '공고', '국고채권 발행 계획 공고 (시험)'],
    ['행정안전부', '훈령', '행정 사무 규정 (시험)']],
  20261111: [['재정경제부', '부령', '법인세법 시행규칙 일부개정령 (시험)'], ['한국은행', '고시', '금융기관 지급준비금 규정 (시험)']],
};
globalThis.caches = undefined;
globalThis.fetch = async (url) => {
  if (url === 'https://eiec.kdi.re.kr/policy/rss.do?rss_type=material') return new Response(KDI_XML, { status: 200 });
  const sp = new URL(url).searchParams, ymd = sp.get('reqFrom'), rows = (DAYS[ymd] || []).map(([org, kind, t], i) => ({
    cntntSeqNo: `${ymd}${String(i).padStart(4, '0')}`, cntntSj: `${org}${kind === '고시' ? '고시' : ''} 제2026-${40 + i}호 ${t}`, hopePblictDt: `${ymd.slice(0, 4)}. ${ymd.slice(4, 6)}. ${ymd.slice(6)}.`,
    cmplatSeNm: kind, pblcnInstNm: org, pdfFilePath: `/ezpdf/customLayout.jsp?viewPath=/test/${ymd}/${i}.pdf`, rvsnRsnMainCn: '(보내지 않는 본문)' }));
  return Response.json({ response: { resultCode: '00', resultMsg: 'NORMAL SERVICE.', totalCount: String(rows.length), pageSize: '100', pageNo: '1', items: rows.length ? { item: rows } : '' } });
};
const { policyCore } = await import('../../worker/src/policy.js');
const body = await policyCore({ DATA_GO_KR_KEY: 'fixture-key-not-real' }, { waitUntil() {} }, {});
writeFileSync(new URL('fixtures/policy.json', HERE), JSON.stringify(body, null, 1) + '\n');
console.log('fixtures/policy.json', body.items.length, 'items', JSON.stringify(body.sources));
