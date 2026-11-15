#!/usr/bin/env node
/* 디자인 기준(docs/standards/design.md §6-2) 스프링 토큰 → CSS. 값은 이 표 한 곳에서만 고쳐요.
 * node scripts/design_tokens.mjs          → 템플릿 :root에 넣을 줄을 출력
 * node scripts/design_tokens.mjs --check  → src/template.html의 블록이 이 표와 같은지 확인(다르면 종료 코드 1)
 * 승인: 사용자 2026-11-15 17:07 "1~9 추천대로 … 스프링 모션 시안은 제안대로". */
import { measure } from './springs.mjs';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const APPROVED = [
  // name, k, c, 쓰는 곳 — 인터페이스 ζ≈0.8(넘침 ≤ 1.5 %), 데이터 ζ 1(넘침 0), 닫힘 ζ .95, 완료 체크 pop만 3 %
  ['lead', 620, 40, '세그먼트·탭·밑줄 표시의 가는 쪽 가장자리'],
  ['trail', 190, 23, '같은 표시의 뒤 가장자리'],
  ['follow', 900, 50, '툴팁·십자선·스위치 손잡이 앞 가장자리'],
  ['settle', 280, 27, '손가락을 놓은 뒤(시트·스위치·티커)'],
  ['fade', 420, 37, '나타남(opacity + 흐림)'],
  ['open', 360, 31, '팝오버·고르기·시트가 트리거에서 자람'],
  ['close', 900, 57, '모든 닫힘·접힘'],
  ['hl', 620, 40, '메뉴·검색 제안 안 하이라이트 판'],
  ['island-w', 380, 32, '결과 섬 폭'],
  ['island-h', 300, 28, '결과 섬 높이'],
  ['roll', 320, 36, '숫자 자리 굴림(데이터, 넘침 0)'],
  ['roll-w', 380, 39, '자리 수가 바뀔 때 숫자 상자 폭(데이터)'],
  ['value', 420, 41, '막대·범례 눈금·지수 선 끝점(데이터)'],
  ['pop', 520, 34, '완료 체크 .6→1에만(화려하게)'],
];

const BEGIN = '  /* ── design.md §6-2 springs (scripts/design_tokens.mjs — generated, do not edit by hand) ── */';
const END = '  /* ── end springs ── */';

export function block() {
  const L = [BEGIN];
  for (const [name, k, c, use] of APPROVED) {
    const m = measure(k, c);
    L.push(`  /* ${name} ${k}/${c} · ζ ${m.zeta.toFixed(2)} · 넘침 ${m.overshootPct.toFixed(2)}% · 0.5% ${Math.round(m.settle05Ms)}ms — ${use} */`);
    L.push(`  --sp-${name}:${m.linear}; --sp-${name}-dur:${m.durMs}ms; --sp-${name}-kc:"${k} ${c}";`);
  }
  L.push(END);
  return L.join('\n');
}
export const reduced = () => APPROVED.map(([n]) => `--sp-${n}-dur:0ms`).join('; ');

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv.includes('--check')) {
    const t = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'template.html'), 'utf8');
    const ok = t.includes(block()) && t.includes(reduced());
    console.log(ok ? 'springs block OK' : 'springs block differs from scripts/design_tokens.mjs'); process.exit(ok ? 0 : 1);
  } else { console.log(block()); console.log('/* reduced: */ ' + reduced()); }
}
