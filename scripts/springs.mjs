#!/usr/bin/env node
/* 스프링 모션 토큰 만들기 (시안 · drafts/springs.md).
 *
 * 질량-스프링-감쇠기 m·x'' + c·x' + k·(x − 1) = 0, x(0) = 0, x'(0) = v0 의 닫힌 해(덜 감쇠 · 임계 · 과감쇠)로
 * 이름 붙은 스프링마다: 0.1% · 0.5% 안정 시간, 최대 넘침 %, CSS `linear()` 곡선(참 곡선과의 최대 오차 < 0.5%,
 * 점 수는 알아서), `--sp-<이름>` · `--sp-<이름>-dur` 한 쌍을 만들어요. 의존성 없음(Node 18+).
 *
 *   node scripts/springs.mjs           → drafts/springs.css · drafts/springs.json · drafts/springs.md,
 *                                         drafts/springs.html 안의 토큰 · 데이터 칸(@sp:… 표시 사이)을 다시 채움
 *   node scripts/springs.mjs --font    → + 시안이 쓰는 글자만 Pretendard에서 잘라 넣음(pyftsubset 필요)
 *   node scripts/springs.mjs --check   → 파일을 쓰지 않고 표만 출력
 *
 * 사용자 규칙(designbookmark.com/motion 참고 요청, 2026-11-15): 넘침은 아주 조금만(≤ 2%), 통통 튀는 곡선 없음,
 * 움직임 줄이기 = 임계 감쇠 또는 없음. 레퍼런스 쌍이 2%를 넘으면 같은 강성(빠르기)에 감쇠만 올려 ζ ≈ 0.8(≈ 1.5%)로.
 */
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

/* ───────────────────────── 닫힌 해 ───────────────────────── */

/** 강성 k, 감쇠 c, 질량 m, 처음 속도 v0(목표까지 거리 1 기준, 1/s). x(t)·v(t)는 초 단위. */
export function spring(k, c, m = 1, v0 = 0) {
  if (!(k > 0 && c >= 0 && m > 0)) throw new RangeError('k > 0, c ≥ 0, m > 0');
  const w0 = Math.sqrt(k / m), zeta = c / (2 * Math.sqrt(k * m));
  const base = { k, c, m, v0, w0, zeta };
  const EPSZ = 1e-9;
  if (zeta < 1 - EPSZ) {
    // y = x − 1 = e^{−a t}(C cos wt + D sin wt), C = −1, D = (v0 − a)/w
    const a = zeta * w0, w = w0 * Math.sqrt(1 - zeta * zeta), C = -1, D = (v0 + a * C) / w;
    return { ...base, regime: 'under', wd: w,
      x: t => 1 + Math.exp(-a * t) * (C * Math.cos(w * t) + D * Math.sin(w * t)),
      v: t => Math.exp(-a * t) * ((D * w - a * C) * Math.cos(w * t) - (C * w + a * D) * Math.sin(w * t)) };
  }
  if (zeta <= 1 + EPSZ) {
    // y = (C + D t) e^{−w0 t}, C = −1, D = v0 + w0·C
    const C = -1, D = v0 + w0 * C;
    return { ...base, regime: 'critical',
      x: t => 1 + (C + D * t) * Math.exp(-w0 * t),
      v: t => (D - w0 * (C + D * t)) * Math.exp(-w0 * t) };
  }
  // y = C1 e^{r1 t} + C2 e^{r2 t}, r = −w0(ζ ∓ √(ζ²−1)), C1 = (v0 + r2)/(r1 − r2), C2 = −1 − C1
  const s = Math.sqrt(zeta * zeta - 1), r1 = -w0 * (zeta - s), r2 = -w0 * (zeta + s);
  const C1 = (v0 + r2) / (r1 - r2), C2 = -1 - C1;
  return { ...base, regime: 'over', r1, r2,
    x: t => 1 + C1 * Math.exp(r1 * t) + C2 * Math.exp(r2 * t),
    v: t => C1 * r1 * Math.exp(r1 * t) + C2 * r2 * Math.exp(r2 * t) };
}

/** 닫힌 식 넘침 %(v0 = 0, 덜 감쇠일 때만, 아니면 0). */
export const overshootFormula = zeta => zeta >= 1 ? 0 : 100 * Math.exp(-zeta * Math.PI / Math.sqrt(1 - zeta * zeta));

/** 마지막으로 |x(t) − 1| > eps 인 시각(초) — 그 뒤로는 계속 띠 안이에요. */
export function settle(sp, eps) {
  const y = t => Math.abs(sp.x(t) - 1);
  // 띠를 확실히 벗어나지 않는 시각(위 경계) 찾기: 덜 감쇠는 포락선, 나머지는 단조라 두 배씩 늘려요
  let hi;
  if (sp.regime === 'under') {
    const a = sp.zeta * sp.w0, amp = Math.hypot(1, (sp.v0 - a) / sp.wd);
    hi = Math.max(1e-6, Math.log(amp / eps) / a);
  } else { hi = 1 / sp.w0; while (y(hi) > eps) hi *= 2; hi *= 1.5; }
  const n = 40000, dt = hi / n;
  let last = -1;
  for (let i = 0; i <= n; i++) if (y(i * dt) > eps) last = i;
  if (last < 0) return 0;
  if (last === n) throw new Error('settle bound too small');
  let lo = last * dt, up = (last + 1) * dt; // y(lo) > eps ≥ y(up)
  for (let i = 0; i < 80; i++) { const mid = (lo + up) / 2; if (y(mid) > eps) lo = mid; else up = mid; }
  return up;
}

/** 최대 넘침 %(수치, 0~안정 시간을 촘촘히) + 그 시각(초). */
export function overshoot(sp) {
  const T = settle(sp, 1e-6), n = 20000;
  let peak = 0, tp = 0;
  for (let i = 0; i <= n; i++) { const t = T * i / n, v = sp.x(t) - 1; if (v > peak) { peak = v; tp = t; } }
  if (sp.regime === 'under' && sp.v0 === 0) { tp = Math.PI / sp.wd; peak = Math.max(peak, sp.x(tp) - 1); } // 닫힌 꼭짓점으로 다듬기
  return { pct: 100 * peak, tPeak: peak > 0 ? tp : null };
}

/* ───────────────────────── CSS 곡선 ───────────────────────── */

export function cubicBezier(x1, y1, x2, y2) {
  const bx = t => 3 * (1 - t) * (1 - t) * t * x1 + 3 * (1 - t) * t * t * x2 + t * t * t;
  const by = t => 3 * (1 - t) * (1 - t) * t * y1 + 3 * (1 - t) * t * t * y2 + t * t * t;
  const dx = t => 3 * (1 - t) * (1 - t) * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t * t * (1 - x2);
  return p => {
    if (p <= 0) return 0; if (p >= 1) return 1;
    let t = p;
    for (let i = 0; i < 8; i++) { const e = bx(t) - p, d = dx(t); if (Math.abs(e) < 1e-12) break; if (Math.abs(d) < 1e-9) break; t -= e / d; }
    if (!(t >= 0 && t <= 1) || Math.abs(bx(t) - p) > 1e-9) { let lo = 0, hi = 1; for (let i = 0; i < 60; i++) { t = (lo + hi) / 2; if (bx(t) < p) lo = t; else hi = t; } }
    return by(t);
  };
}

/** CSS Easing Level 2의 `linear()` 규칙 그대로 계산해요(위치가 빠진 점은 이웃 사이에 고르게, 뒤로 가는 위치는 앞 값으로). */
export function parseLinear(str) {
  const m = /^\s*linear\((.*)\)\s*$/s.exec(str);
  if (!m) throw new SyntaxError('not linear(): ' + str.slice(0, 40));
  const pts = [];
  for (const part of m[1].split(',')) {
    const tok = part.trim().split(/\s+/);
    const out = Number(tok[0]);
    if (!Number.isFinite(out) || tok.length > 3) throw new SyntaxError('bad stop: ' + part);
    const pos = tok.slice(1).map(s => { if (!/%$/.test(s)) throw new SyntaxError('bad pos: ' + s); return Number(s.slice(0, -1)) / 100; });
    if (!pos.length) pts.push({ out, in: null }); else pos.forEach(p => pts.push({ out, in: p }));
  }
  if (pts.length < 2) throw new SyntaxError('need ≥ 2 stops');
  if (pts[0].in == null) pts[0].in = 0;
  if (pts[pts.length - 1].in == null) pts[pts.length - 1].in = Math.max(1, ...pts.filter(p => p.in != null).map(p => p.in));
  let mx = -Infinity;
  for (const p of pts) if (p.in != null) { p.in = Math.max(p.in, mx); mx = p.in; }
  for (let i = 0; i < pts.length; i++) if (pts[i].in == null) {
    let j = i; while (pts[j].in == null) j++;
    const a = pts[i - 1].in, b = pts[j].in;
    for (let q = i; q < j; q++) pts[q].in = a + (b - a) * (q - i + 1) / (j - i + 1);
    i = j;
  }
  return pts;
}
export function evalLinear(str) {
  const pts = parseLinear(str);
  return x => {
    let i = 0;
    if (x <= pts[0].in) i = 0;
    else if (x >= pts[pts.length - 1].in) i = pts.length - 2;
    else { while (i < pts.length - 2 && pts[i + 1].in <= x) i++; }
    // 같은 입력이 여럿이면 마지막 점
    if (x === pts[i + 1].in) { let j = i + 1; while (j + 1 < pts.length && pts[j + 1].in === x) j++; return pts[j].out; }
    const a = pts[i], b = pts[i + 1];
    if (b.in === a.in) return b.out;
    return a.out + (b.out - a.out) * (x - a.in) / (b.in - a.in);
  };
}

const round3 = v => Math.round(v * 1000) / 1000;
const fmtNum = v => {
  let s = round3(v).toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  if (s === '-0') s = '0';
  return s.replace(/^(-?)0\./, '$1.');
};
const fmtPct = i => (i / 10).toFixed(1).replace(/\.0$/, '') + '%'; // i = 1/1000 칸

/** f: [0,1] → 값(f(0)=0, 끝은 1로 맞춰요). 가장 짧은 `linear()`(고른 칸 vs 알맞은 칸) + 실제 최대 오차. */
export function toLinear(f, { tol = 0.005, grid = 1000 } = {}) {
  const val = i => i >= grid ? 1 : i <= 0 ? 0 : round3(f(i / grid));
  const errOf = str => { const g = evalLinear(str); let e = 0; for (let i = 0; i <= 20000; i++) { const p = i / 20000; e = Math.max(e, Math.abs(g(p) - f(p))); } return e; };
  // ① 알맞은 칸: 앞에서부터 현이 곡선을 tolIn 안에서 덮는 한 가장 멀리(1/1000 칸 위, 칸마다 4번 확인)
  let adaptive = null;
  for (let tolIn = tol * 0.9; tolIn > tol * 0.2 && !adaptive; tolIn *= 0.9) {
    const idx = [0]; let i = 0;
    while (i < grid) {
      let best = i + 1;
      for (let j = i + 1; j <= grid; j++) {
        const vi = val(i), vj = val(j); let ok = true;
        for (let s = i * 4; s <= j * 4; s++) { const p = s / (grid * 4), ch = vi + (vj - vi) * (p * grid - i) / (j - i); if (Math.abs(ch - f(p)) > tolIn) { ok = false; break; } }
        if (ok) best = j; else break;
      }
      idx.push(best); i = best;
    }
    const str = 'linear(' + idx.map((q, n) => n === 0 ? '0' : n === idx.length - 1 ? '1' : `${fmtNum(val(q))} ${fmtPct(q)}`).join(', ') + ')';
    const err = errOf(str);
    if (err < tol) adaptive = { str, n: idx.length, err, mode: 'adaptive' };
  }
  // ② 고른 칸: 점 수를 늘려 가며 오차가 tol 안에 들어오는 첫 N
  let uniform = null;
  for (let N = 3; N <= 400 && !uniform; N++) {
    const vals = Array.from({ length: N }, (_, q) => q === 0 ? 0 : q === N - 1 ? 1 : round3(f(q / (N - 1))));
    const str = 'linear(' + vals.map(fmtNum).join(', ') + ')';
    // 빠른 거르기 먼저(칸 가운데만), 통과하면 촘촘히
    let rough = 0; for (let q = 0; q < N - 1; q++) { const p = (q + .5) / (N - 1); rough = Math.max(rough, Math.abs((vals[q] + vals[q + 1]) / 2 - f(p))); }
    if (rough >= tol) continue;
    const err = errOf(str);
    if (err < tol) uniform = { str, n: N, err, mode: 'uniform' };
  }
  const c = [adaptive, uniform].filter(Boolean).sort((a, b) => a.str.length - b.str.length);
  if (!c.length) throw new Error('no linear() under tolerance');
  return c[0];
}

/* ───────────────────────── 이름 붙은 스프링 ───────────────────────── */

export const LIMIT_PCT = 2;        // 사용자 규칙: 넘침은 아주 조금만
export const ALT_ZETA = 0.8;       // 고칠 때 목표 ζ(넘침 ≈ 1.5%)
export const TOL = 0.005;          // linear() 최대 오차 0.5%
export const DUR_EPS = 0.001;      // --sp-*-dur = 0.1% 안정 시간(끝에서 1000px를 움직여도 1px 미만으로 맞춰짐)

/** designbookmark.com/motion 레퍼런스 쌍(질량 1). use = 이 사이트에서 쓸 곳. */
export const SPRINGS = [
  { name: 'follow', group: '기본', k: 900, c: 50, use: '포인터를 따라가는 것 · 끌기를 놓은 뒤 · 스위치 손잡이 앞 가장자리' },
  { name: 'settle', group: '기본', k: 280, c: 22, use: '자리에 내려앉는 것 · 스위치 손잡이 뒤 가장자리' },
  { name: 'soft', group: '기본', k: 260, c: 24, use: '부드러운 크기 변화 · 칩 체크 폭' },
  { name: 'lead', group: '기본', k: 620, c: 36, use: '세그먼트 · 탭 표시의 가는 쪽 가장자리' },
  { name: 'trail', group: '기본', k: 190, c: 19, use: '세그먼트 · 탭 표시의 뒤 가장자리' },
  { name: 'pop', group: '기본', k: 520, c: 16, use: '튀어나오는 것 · 체크 크기' },
  { name: 'fade', group: '기본', k: 420, c: 32, use: '나타남 · opacity + blur' },
  { name: 'morph-open', group: '모핑 셀렉트', k: 360, c: 24, use: '셀렉트 · 팝오버가 키에서 열림(모서리)' },
  { name: 'morph-hl', group: '모핑 셀렉트', k: 620, c: 34, use: '열린 목록 안 하이라이트 이동' },
  { name: 'island-w', group: '모핑 아일랜드', k: 380, c: 24, use: '모핑 상자 폭' },
  { name: 'island-h', group: '모핑 아일랜드', k: 300, c: 22, use: '모핑 상자 높이' },
  { name: 'nav-lead', group: '사이드 내비', k: 560, c: 34, use: '세로 목록 표시 앞 가장자리' },
  { name: 'nav-trail', group: '사이드 내비', k: 220, c: 21, use: '세로 목록 표시 뒤 가장자리' },
  { name: 'roll', group: '굴러가는 숫자', k: 320, c: 24, use: '숫자 자리 굴림' },
  { name: 'roll-w', group: '굴러가는 숫자', k: 380, c: 22, use: '자리 수가 바뀔 때 폭' },
  { name: 'roll-press', group: '굴러가는 숫자', k: 600, c: 18, use: '누름에서 올라옴' },
];

/** 같은 강성, 감쇠만 올려 ζ ≥ ALT_ZETA (정수 c). */
export const altDamping = (k, m = 1) => Math.ceil(2 * ALT_ZETA * Math.sqrt(k * m));

/** 한 쌍의 모든 수치 + 토큰. */
export function measure(k, c, m = 1) {
  const sp = spring(k, c, m);
  const s01 = settle(sp, 0.001), s05 = settle(sp, 0.005), os = overshoot(sp);
  const durMs = Math.ceil(s01 * 1000);
  const lin = toLinear(p => sp.x(p * durMs / 1000), { tol: TOL });
  const crit = spring(k, 2 * Math.sqrt(k * m), m); // 같은 빠르기(ω0)의 임계 감쇠 — 줄이기에서 꼭 움직여야 할 때
  return {
    k, c, m, zeta: +sp.zeta.toFixed(4), w0: +sp.w0.toFixed(3), regime: sp.regime,
    overshootPct: +os.pct.toFixed(3), overshootFormulaPct: +overshootFormula(sp.zeta).toFixed(3), peakMs: os.tPeak == null ? null : +(os.tPeak * 1000).toFixed(1),
    settle01Ms: +(s01 * 1000).toFixed(1), settle05Ms: +(s05 * 1000).toFixed(1), durMs,
    linear: lin.str, points: lin.n, mode: lin.mode, maxErrPct: +(lin.err * 100).toFixed(3), chars: lin.str.length,
    critical: { c: +(2 * Math.sqrt(k * m)).toFixed(2), settle01Ms: +(settle(crit, 0.001) * 1000).toFixed(1), settle05Ms: +(settle(crit, 0.005) * 1000).toFixed(1) },
  };
}

/** 지금 곡선(controls.md §2)의 넘침 — 비교용. */
export const CURRENT = {
  '--c-out': [.22, 1, .36, 1], '--c-in': [.4, 0, 1, 1], '--c-inout': [.65, 0, .35, 1], '--c-pop': [.34, 1.3, .64, 1],
};
export function bezierOvershootPct(b) { const f = cubicBezier(...b); let mx = 0; for (let i = 0; i <= 20000; i++) mx = Math.max(mx, f(i / 20000)); return 100 * (mx - 1); }

export function build() {
  const cpop = bezierOvershootPct(CURRENT['--c-pop']);
  const rows = SPRINGS.map(s => {
    const ref = measure(s.k, s.c);
    const flagged = ref.overshootPct > LIMIT_PCT;
    const row = { name: s.name, group: s.group, use: s.use, ref, flagged };
    if (flagged) row.alt = measure(s.k, altDamping(s.k));
    return row;
  });
  // 완료 체크(화려하게) 전용: 지금 --c-pop(.34,1.3,.64,1)과 같은 정도의 넘침이 되는 가장 작은 감쇠
  const popK = SPRINGS.find(s => s.name === 'pop').k;
  let pc = 1; while (overshootFormula(pc / (2 * Math.sqrt(popK))) > cpop) pc++;
  const popCheck = measure(popK, pc);
  return {
    generated: 'scripts/springs.mjs', rule: { limitPct: LIMIT_PCT, altZeta: ALT_ZETA, linearTolPct: TOL * 100, durEps: DUR_EPS, mass: 1 },
    current: Object.fromEntries(Object.entries(CURRENT).map(([k, b]) => [k, { bezier: b, overshootPct: +bezierOvershootPct(b).toFixed(3) }])),
    springs: rows, popCheck,
  };
}

/* ───────────────────────── 파일 ───────────────────────── */

const tokenOf = r => r.flagged ? r.alt : r.ref;
export function css(data) {
  const L = [];
  L.push('/* 스프링 모션 토큰 — 시안 (drafts/springs.md). 만든 곳: scripts/springs.mjs — 손으로 고치지 마세요.');
  L.push(`   --sp-<이름>: linear() 곡선(참 스프링과 최대 오차 < ${TOL * 100}%), --sp-<이름>-dur: 0.1% 안정 시간. 질량 1.`);
  L.push('   쓰는 법: transition: left var(--sp-lead-dur) var(--sp-lead);  ·  넘침 > 2%인 레퍼런스 쌍은 같은 강성에 감쇠만 올렸어요(ζ ≥ 0.8). */');
  L.push(':root{');
  for (const r of data.springs) {
    const t = tokenOf(r);
    L.push(`  /* ${r.name} ${t.k}/${t.c} · ζ ${t.zeta.toFixed(3)} · 넘침 ${t.overshootPct.toFixed(2)}% · 0.5% ${Math.round(t.settle05Ms)}ms${r.flagged ? ` (레퍼런스 ${r.ref.k}/${r.ref.c}: ${r.ref.overshootPct.toFixed(1)}%)` : ''} */`);
    L.push(`  --sp-${r.name}:${t.linear};`);
    L.push(`  --sp-${r.name}-dur:${t.durMs}ms;`);
  }
  const p = data.popCheck;
  L.push(`  /* pop-check ${p.k}/${p.c} · ζ ${p.zeta.toFixed(3)} · 넘침 ${p.overshootPct.toFixed(2)}% (지금 --c-pop ${data.current['--c-pop'].overshootPct.toFixed(2)}%) — 완료 체크 크기 .6→1, '화려하게'에서만 */`);
  L.push(`  --sp-pop-check:${p.linear};`);
  L.push(`  --sp-pop-check-dur:${p.durMs}ms;`);
  L.push('}');
  L.push('/* 레퍼런스 쌍 그대로 — 비교용(시안의 "레퍼런스" 줄). ⚠ = 넘침 > 2%라 컨트롤에 쓰지 않아요. 2% 이하인 쌍은 위 토큰과 같아요 */');
  L.push(':root{');
  for (const r of data.springs) {
    L.push(`  /* ${r.flagged ? '⚠ ' : ''}${r.name}-ref ${r.ref.k}/${r.ref.c} · ζ ${r.ref.zeta.toFixed(3)} · 넘침 ${r.ref.overshootPct.toFixed(2)}% */`);
    L.push(`  --sp-${r.name}-ref:${r.flagged ? r.ref.linear : `var(--sp-${r.name})`};`);
    L.push(`  --sp-${r.name}-ref-dur:${r.flagged ? r.ref.durMs + 'ms' : `var(--sp-${r.name}-dur)`};`);
  }
  L.push('}');
  L.push('/* 움직임 줄이기: controls.md §3처럼 길이 0 = 끝 상태로 바로 (곡선은 그대로 둬요) */');
  const names = [...data.springs.map(r => r.name), 'pop-check', ...data.springs.filter(r => r.flagged).map(r => r.name + '-ref')];
  L.push('html[data-motion="reduced"]{' + names.map(n => `--sp-${n}-dur:0ms`).join(';') + '}');
  return L.join('\n') + '\n';
}

export function md(data) {
  const f = (v, d = 1) => Number(v).toFixed(d);
  const L = [];
  L.push('# 스프링 모션 — 시안');
  L.push('');
  L.push('> **상태: 시안 (승인 전).** 사용자 요청 2026-11-15 "designbookmark.com/motion 같은 스프링 모션". 승인된 컨트롤 규칙은 [`docs/standards/controls.md`](../docs/standards/controls.md)(180 · 320 · 560ms, `--c-out` · `--c-in` · `--c-inout` · `--c-pop`)이고, 이 문서는 그걸 스프링으로 바꾸면 어떻게 되는지 재 본 것이에요. `src/`는 건드리지 않았어요.');
  L.push('> 만든 곳: `node scripts/springs.mjs` → `drafts/springs.css` · `drafts/springs.json` · 이 문서 · `drafts/springs.html`의 토큰 칸. 점검: `node qa/motion/test_springs.mjs`. 프레임: `drafts/springs.html?frames=1` → `qa/shots/springs/`.');
  L.push('');
  L.push('## 1. 재는 법');
  L.push('');
  L.push('- 질량 1, 0에서 멈춘 채 출발해 1로 가는 스프링(m·x″ + c·x′ + k·(x − 1) = 0)의 **닫힌 해**로 계산해요: ζ = c / (2√(k·m)), ω₀ = √(k/m). ζ < 1이면 덜 감쇠(넘쳐요), 1이면 임계, 1보다 크면 과감쇠(넘치지 않아요).');
  L.push('- **넘침** = 최댓값 − 1 (덜 감쇠면 100·e^(−ζπ/√(1−ζ²))와 같아요). **안정 시간** = |x − 1|이 0.5% · 0.1% 띠 밖에 마지막으로 있던 시각.');
  L.push(`- **CSS 곡선**: \`linear()\`(Chrome 113 · Safari 17.2 · Firefox 112부터). 길이 \`--sp-*-dur\` = 0.1% 안정 시간(끝에서 맞춰지는 양이 1000px 이동에도 1px 미만). 점은 앞에서부터 현이 곡선을 덮는 한 가장 멀리 잡거나(위치 % 붙음) 고른 칸으로 잡고, 둘 중 **짧은 글자**를 골라요. 참 곡선과의 최대 오차는 모두 ${TOL * 100}% 미만(아래 표의 '오차').`);
  L.push(`- **판정**: 넘침이 **${LIMIT_PCT}% 넘으면 ⚠** — 사용자 규칙("넘침은 아주 조금만, 통통 튀는 곡선 없음"). 고친 쌍은 **같은 강성(같은 빠르기 ω₀)에 감쇠만 올려 ζ ≥ ${ALT_ZETA}**(넘침 ≈ 1.5%)로 — 처음 움직임의 빠르기는 그대로고, 대개 더 빨리 멈춰요.`);
  L.push('');
  L.push('## 2. 모든 쌍');
  L.push('');
  L.push('| 이름 | 묶음 | k / c | ζ | 넘침 % | 안정 0.5% · 0.1% (ms) | 판정 | 제안 k / c | 제안 ζ | 제안 넘침 % | 제안 안정 0.5% · 0.1% (ms) | 토큰 길이 · 점 · 오차 |');
  L.push('|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const r of data.springs) {
    const a = r.alt, t = tokenOf(r);
    L.push(`| \`${r.name}\` | ${r.group} | ${r.ref.k} / ${r.ref.c} | ${f(r.ref.zeta, 3)} | ${f(r.ref.overshootPct, 2)} | ${Math.round(r.ref.settle05Ms)} · ${Math.round(r.ref.settle01Ms)} | ${r.flagged ? '⚠ > 2%' : '✓'} | ${a ? `${a.k} / ${a.c}` : '그대로'} | ${a ? f(a.zeta, 3) : ''} | ${a ? f(a.overshootPct, 2) : ''} | ${a ? `${Math.round(a.settle05Ms)} · ${Math.round(a.settle01Ms)}` : ''} | ${t.durMs}ms · ${t.points}점 · ${f(t.maxErrPct, 2)}% |`);
  }
  const p = data.popCheck;
  L.push(`| \`pop-check\` | 완료 체크 | ${p.k} / ${p.c} | ${f(p.zeta, 3)} | ${f(p.overshootPct, 2)} | ${Math.round(p.settle05Ms)} · ${Math.round(p.settle01Ms)} | 예외 (화려하게) | — | — | — | — | ${p.durMs}ms · ${p.points}점 · ${f(p.maxErrPct, 2)}% |`);
  L.push('');
  const fl = data.springs.filter(r => r.flagged).map(r => '`' + r.name + '`');
  const zs = data.springs.map(r => r.ref.zeta), mid = data.springs.filter(r => r.flagged && r.ref.overshootPct < 20).map(r => r.ref.overshootPct);
  L.push(`- ⚠ **${fl.length}쌍 / ${data.springs.length}쌍**이 2%를 넘어요: ${fl.join(' · ')}. 레퍼런스 쌍은 ζ ${f(Math.min(...zs), 2)}~${f(Math.max(...zs), 2)}이라 pop · roll-press 말고도 ${f(Math.min(...mid), 0)}~${f(Math.max(...mid), 0)}% 튀어요 — 사용자 규칙과 맞지 않아서, 토큰 \`--sp-<이름>\`은 **제안 쌍**이고 레퍼런스 그대로는 \`--sp-<이름>-ref\`(비교용)로만 남겼어요.`);
  const pop = data.springs.find(r => r.name === 'pop'), press = data.springs.find(r => r.name === 'roll-press');
  L.push(`- **pop ${pop.ref.k}/${pop.ref.c}**(ζ ${f(pop.ref.zeta, 2)}, 넘침 ${f(pop.ref.overshootPct, 1)}%)은 크기 .6→1이면 **${f(.6 + .4 * (1 + pop.ref.overshootPct / 100), 3)}**까지 커졌다가 세 번쯤 흔들려요. 컨트롤 표면에는 **${pop.alt.k}/${pop.alt.c}**(${f(pop.alt.overshootPct, 2)}%). 완료 체크(화려하게)도 원본을 쓰지 않고 **\`pop-check\` ${p.k}/${p.c}**(${f(p.overshootPct, 2)}%) — 지금 승인된 \`--c-pop\`(.34,1.3,.64,1)의 넘침 ${f(data.current['--c-pop'].overshootPct, 2)}%를 넘지 않는 가장 작은 감쇠라 "화려하게"의 느낌은 지금과 같아요(.6→1이 ${f(.6 + .4 * (1 + p.overshootPct / 100), 3)}까지).`);
  L.push(`- **roll-press ${press.ref.k}/${press.ref.c}**(${f(press.ref.overshootPct, 1)}%)도 누름이 튀어요 — controls.md §2 "누름에 pop을 쓰지 않아요(튕기지 않음)"과 부딪쳐요 → **${press.alt.k}/${press.alt.c}**.`);
  const fade = data.springs.find(r => r.name === 'fade');
  L.push(`- \`fade\` ${fade.ref.k}/${fade.ref.c}는 ${f(fade.ref.overshootPct, 2)}%로 경계 바로 아래예요. opacity에는 넘침이 잘려 보이지 않지만, 위치 · 크기에 쓰면 2%만큼 넘어요.`);
  L.push('- 지금 곡선의 넘침: ' + Object.entries(data.current).map(([k, v]) => `\`${k}\` ${f(v.overshootPct, 2)}%`).join(' · ') + '.');
  L.push('- 참고: `docs/motion-brief.md` 2-0의 옛 스프링(k 420 · c 32 · **m .6**)은 ζ ≈ 1.01(튐 없음)이었어요 — 같은 k/c라도 질량 1이면 ζ 0.78이에요.');
  L.push('');
  L.push('## 3. 어디에 쓰나 (시안 `drafts/springs.html`)');
  L.push('');
  L.push('| 컨트롤 | 지금 (controls.md) | 스프링 제안 |');
  L.push('|---|---|---|');
  const T = n => { const r = data.springs.find(x => x.name === n); const t = tokenOf(r); return `\`${n}\` ${t.k}/${t.c} (${t.durMs}ms)`; };
  L.push(`| 세그먼트 표시 | 가는 쪽 \`right/left\` fast 180 · 뒤 base 320, \`--c-out\` | 가는 쪽 ${T('lead')}, 뒤 ${T('trail')} — 늘었다 줄며 도착 |`);
  L.push(`| 스위치 손잡이 | \`translateX\` 252ms \`--c-inout\`(늘어나지 않음) | 손잡이를 \`left/right\` 두 가장자리로: 가는 쪽 ${T('follow')}, 뒤 ${T('settle')} → 움직이는 동안 늘어났다 돌아와요. 채움 ${T('fade')} |`);
  L.push(`| 팝오버 (색 기준 ▾) | 목록이 아래에 opacity + 4px, fast \`--c-out\` | 키 자체가 목록으로 모핑: 폭 ${T('island-w')} · 높이 ${T('island-h')} · 모서리 ${T('morph-open')}. 내용 들어옴 = opacity + blur 4px→0 ${T('fade')}, 60ms 뒤. 나감 = 내용 먼저 fast \`--c-in\`(blur 0→4px), 상자는 60ms 뒤 같은 스프링으로 키 크기로. 목록 안 하이라이트 ${T('morph-hl')} |`);
  L.push(`| 칩 (켜고 끄기) | 채움 · 테 fast \`--c-out\`, 체크 폭 0→14 + scale .6→1 fast | 체크 폭 ${T('soft')}, 체크 크기 ${T('pop')}, 채움 ${T('fade')} |`);
  L.push(`| 숫자 굴림 | 바뀐 자리 \`translateY ±100%\` base \`--c-out\`, 40ms 간격, 자리 수가 바뀌면 fast 교차 | 자리 ${T('roll')}(40ms 간격 그대로), 자리 수가 바뀌면 폭 ${T('roll-w')} + 새 자리도 굴림, 키 올라옴 ${T('roll-press')} |`);
  L.push('');
  L.push('## 4. 움직임 줄이기 · 한계');
  L.push('');
  L.push('- `html[data-motion="reduced"]`면 모든 `--sp-*-dur`가 0ms — controls.md §3과 같이 끝 상태로 바로예요(사용자 규칙 "임계 감쇠 또는 없음" 중 **없음**). 끌기를 놓은 스위치 손잡이처럼 꼭 움직여야 하는 곳은 같은 ω₀의 **임계 감쇠**(`springs.json`의 `critical`: c = 2√k, 넘침 0)를 JS로 쓰면 돼요.');
  L.push('- CSS 전환은 **속도를 이어받지 못해요**: 움직이는 중에 다시 누르면 새 전환이 속도 0에서 시작해서 살짝 멈칫해요(지금 cubic-bezier도 같아요). 끌기 · 빠른 연타가 중요한 곳(스위치 끌기, 티커)은 `springs.mjs`의 `spring(k, c, m, v0)` 닫힌 해를 rAF로 돌리면 이어져요(v0 = 지금 속도 ÷ 남은 거리).');
  const dd = data.springs.map(r => tokenOf(r).durMs), d5 = data.springs.map(r => tokenOf(r).settle05Ms);
  L.push(`- 스프링 토큰은 지금 길이(180 · 320ms)보다 **길어요**(제안 \`--sp-*-dur\` ${Math.min(...dd)}~${Math.max(...dd)}ms). 눈에 보이는 움직임은 0.5% 시간(${Math.round(Math.min(...d5))}~${Math.round(Math.max(...d5))}ms)쯤 끝나고, 그 뒤는 1px 안쪽 꼬리예요 — \`transitionend\`를 기다리는 코드는 그만큼 늦어져요.`);
  L.push('- `left/right · width/height`는 레이아웃 속성이에요. 시안은 작은 컨트롤 하나라 괜찮지만, 구현 때는 controls.md §10처럼 표시 상자 하나에만 쓰거나 `clip-path`/`transform`으로 바꿔요.');
  L.push('');
  return L.join('\n');
}

function replaceBlock(text, tag, body) {
  const re = new RegExp(`(/\\*@${tag}:begin\\*/)[\\s\\S]*?(/\\*@${tag}:end\\*/)`);
  if (!re.test(text)) return null;
  return text.replace(re, (_, a, b) => a + '\n' + body + '\n' + b);
}

function fontBlock(html) {
  // 시안에 쓰인 글자만 Pretendard(사이트 서브셋)에서 잘라 data: URI로
  const text = html.replace(/\/\*@font:begin\*\/[\s\S]*?\/\*@font:end\*\//, '');
  const chars = new Set(text.replace(/<[^>]*>/g, ' '));
  for (let c = 0x20; c < 0x7f; c++) chars.add(String.fromCharCode(c));
  for (const c of '−·…›‹×▾▴✓%↑↓←→—–≤≥ζ₀') chars.add(c);
  const dir = mkdtempSync(join(tmpdir(), 'spfont-'));
  try {
    const txt = join(dir, 'chars.txt'), out = join(dir, 'f.woff2');
    writeFileSync(txt, [...chars].filter(c => /\S/.test(c) || c === ' ').join(''));
    execFileSync('pyftsubset', [join(ROOT, 'src/fonts/PretendardVariable-subset.woff2'), `--text-file=${txt}`, '--flavor=woff2', `--output-file=${out}`,
      '--layout-features=kern,liga,calt,tnum,ccmp,locl', '--no-hinting', '--desubroutinize'], { stdio: 'pipe' });
    const b64 = readFileSync(out).toString('base64');
    return `/* Pretendard Variable (SIL OFL 1.1, github.com/orioncactus/pretendard) — 이 시안에 쓰인 글자만 잘라 넣었어요 (node scripts/springs.mjs --font) */\n@font-face{font-family:"Pretendard Variable";font-weight:45 920;font-style:normal;font-display:swap;src:url(data:font/woff2;base64,${b64}) format("woff2")}`;
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

function main() {
  const args = new Set(process.argv.slice(2));
  const data = build();
  const rows = data.springs.map(r => [r.name, `${r.ref.k}/${r.ref.c}`, r.ref.zeta.toFixed(3), r.ref.overshootPct.toFixed(2) + '%', Math.round(r.ref.settle05Ms) + '/' + Math.round(r.ref.settle01Ms) + 'ms',
    r.flagged ? `FLAG → ${r.alt.k}/${r.alt.c} ζ${r.alt.zeta.toFixed(3)} ${r.alt.overshootPct.toFixed(2)}% ${Math.round(r.alt.settle05Ms)}/${Math.round(r.alt.settle01Ms)}ms` : 'ok',
    `${(r.flagged ? r.alt : r.ref).chars}ch/${(r.flagged ? r.alt : r.ref).points}pt/${(r.flagged ? r.alt : r.ref).maxErrPct}%`]);
  rows.push(['pop-check', `${data.popCheck.k}/${data.popCheck.c}`, data.popCheck.zeta.toFixed(3), data.popCheck.overshootPct.toFixed(2) + '%', Math.round(data.popCheck.settle05Ms) + '/' + Math.round(data.popCheck.settle01Ms) + 'ms', 'exception (fancy check)', `${data.popCheck.chars}ch/${data.popCheck.points}pt/${data.popCheck.maxErrPct}%`]);
  for (const r of rows) console.log(r.map((c, i) => String(c).padEnd([12, 8, 7, 9, 12, 44, 18][i])).join(' '));
  if (args.has('--check')) return;
  const cssText = css(data);
  writeFileSync(join(ROOT, 'drafts/springs.css'), cssText);
  writeFileSync(join(ROOT, 'drafts/springs.json'), JSON.stringify(data, null, 1) + '\n');
  writeFileSync(join(ROOT, 'drafts/springs.md'), md(data) + '\n');
  const hp = join(ROOT, 'drafts/springs.html');
  if (existsSync(hp)) {
    let h = readFileSync(hp, 'utf8');
    const p = data.popCheck;
    const slim = { current: data.current, popCheck: { k: p.k, c: p.c, zeta: p.zeta, overshootPct: p.overshootPct, settle05Ms: p.settle05Ms, durMs: p.durMs },
      springs: data.springs.map(r => ({ name: r.name, group: r.group, ref: { k: r.ref.k, c: r.ref.c, zeta: r.ref.zeta, overshootPct: r.ref.overshootPct, settle05Ms: r.ref.settle05Ms, durMs: r.ref.durMs },
        flagged: r.flagged, alt: r.alt && { k: r.alt.k, c: r.alt.c, zeta: r.alt.zeta, overshootPct: r.alt.overshootPct, settle05Ms: r.alt.settle05Ms, durMs: r.alt.durMs } })) };
    h = replaceBlock(h, 'sp', cssText.trim()) ?? h;
    h = replaceBlock(h, 'data', 'const SP = ' + JSON.stringify(slim) + ';') ?? h;
    if (args.has('--font')) { try { h = replaceBlock(h, 'font', fontBlock(h)) ?? h; } catch (e) { console.warn('font skipped:', e.message); } }
    writeFileSync(hp, h);
  }
  console.log('wrote drafts/springs.css · drafts/springs.json · drafts/springs.md' + (existsSync(hp) ? ' · drafts/springs.html (blocks)' : ''));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
