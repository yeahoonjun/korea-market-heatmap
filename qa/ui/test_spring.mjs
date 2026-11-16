#!/usr/bin/env node
/* KH.spring 점검 (src/ui/spring.js · design.md §6-3 "JS" · AGENTS §3-7 "KH.spring").
 *   node qa/ui/test_spring.mjs              → 단위(가짜 window · rAF · 시계, 실제 파일을 node:vm으로) + 빌드된 페이지(Playwright)
 *   node qa/ui/test_spring.mjs --no-browser → 단위만
 * 브라우저 단계: dist/index.html(file://, 네트워크 없음) + web/index.html(qa/news/mock_api.py, 포트 SPRING_QA_PORT 기본 8940)
 * — 먼저 python3 scripts/build_page.py. 의존성: playwright(전역 /opt/npm-tools 또는 node_modules) + /usr/bin/google-chrome.
 */
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';
import { APPROVED } from '../../scripts/design_tokens.mjs';
import { spring as refSpring, measure } from '../../scripts/springs.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SRC = readFileSync(join(ROOT, 'src/ui/spring.js'), 'utf8');
let n = 0;
const groups = [];
const t = (name, fn) => { fn(); n++; console.log('  ✓', name); };
const ta = async (name, fn) => { await fn(); n++; console.log('  ✓', name); };
const close = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg ?? ''} ${a} vs ${b} (±${eps})`);
const tick = () => new Promise(r => setTimeout(r, 0));

/* ───────── harness: the shipped file in a fresh context with a fake window ───────── */
function load({ motion = 'fancy', hidden = false, css = {} } = {}) {
  const frames = [];
  let id = 0, clock = 1000;
  const env = { motion, hidden, css: { ...css }, errors: [], rafCalls: 0, cancels: 0 };
  const document = new EventTarget();
  Object.defineProperty(document, 'hidden', { get: () => env.hidden });
  Object.defineProperty(document, 'visibilityState', { get: () => (env.hidden ? 'hidden' : 'visible') });
  document.documentElement = { dataset: {}, style: {} };
  const KH = { motion: () => env.motion };
  const sb = {
    KH, document, queueMicrotask, CustomEvent, Event, EventTarget,
    console: { error: (...a) => env.errors.push(a.map(x => (x && x.message) || String(x)).join(' ')), log: console.log, warn: console.warn },
    performance: { now: () => clock },
    requestAnimationFrame: f => { env.rafCalls++; const i = ++id; frames.push({ i, f }); return i; },
    cancelAnimationFrame: i => { env.cancels++; const k = frames.findIndex(x => x.i === i); if (k >= 0) frames.splice(k, 1); },
    getComputedStyle: () => ({ getPropertyValue: name => env.css[name] ?? '' }),
  };
  sb.window = sb;
  vm.createContext(sb);
  vm.runInContext(SRC, sb, { filename: 'src/ui/spring.js' });
  Object.assign(env, {
    sp: KH.spring, KH, document,
    pending: () => frames.length,
    now: () => clock,
    advance: ms => { clock += ms; },
    // one frame `ms` after the last one: every queued callback gets the same timestamp (like the browser)
    frame: (ms = 1000 / 60) => { clock += ms; const list = frames.splice(0); for (const { f } of list) f(clock); return list.length; },
    run: (maxMs = 5000, ms = 1000 / 60) => { let k = 0; while (frames.length && k * ms < maxMs) { env.frame(ms); k++; } return k; },
    motionTo: m => { env.motion = m; document.dispatchEvent(new CustomEvent('kh:motion', { detail: { motion: m } })); },
    hide: h => { env.hidden = h; document.dispatchEvent(new Event('visibilitychange')); },
  });
  return env;
}
const kcOf = name => { const r = APPROVED.find(a => a[0] === name); return { k: r[1], c: r[2] }; };
// a fake element: counts style writes per property
function fakeEl(text = '') {
  const writes = {}, vals = { willChange: '' };
  const style = new Proxy(vals, { set(o, p, v) { writes[p] = (writes[p] || 0) + 1; o[p] = String(v); return true; } });
  return { style, textContent: text, writes, vals };
}
const tx = el => { const m = /^translateX\((-?[\d.]+)px\)$/.exec(el.vals.transform || ''); return m ? +m[1] : null; };
const wd = el => parseFloat(el.vals.width);

/* independent check: the same ODE with RK4 (no closed form), target may switch at tSwitch */
function rk4(k, c, x0, v0, to, times, { h = 1e-5, tSwitch = Infinity, to2 = to } = {}) {
  let x = x0, v = v0, tt = 0;
  const out = [];
  const acc = (x, v, T) => -k * (x - T) - c * v;
  for (const T of times) {
    while (tt < T - 1e-12) {
      const target = tt < tSwitch - 1e-12 ? to : to2;
      let hh = Math.min(h, T - tt);
      if (tt < tSwitch && tt + hh > tSwitch) hh = tSwitch - tt;
      const k1x = v, k1v = acc(x, v, target);
      const k2x = v + hh / 2 * k1v, k2v = acc(x + hh / 2 * k1x, v + hh / 2 * k1v, target);
      const k3x = v + hh / 2 * k2v, k3v = acc(x + hh / 2 * k2x, v + hh / 2 * k2v, target);
      const k4x = v + hh * k3v, k4v = acc(x + hh * k3x, v + hh * k3v, target);
      x += hh / 6 * (k1x + 2 * k2x + 2 * k3x + k4x); v += hh / 6 * (k1v + 2 * k2v + 2 * k3v + k4v); tt += hh;
    }
    out.push([x, v]);
  }
  return out;
}

const EXTRA = [['critical', 400, 40], ['over', 400, 70], ['soft-under', 300, 12]];
const ALL = [...APPROVED.map(([name, k, c]) => [name, k, c]), ...EXTRA];

console.log('1. 표 · 닫힌 해');
{
  const env = load();
  t(`FALLBACK = scripts/design_tokens.mjs APPROVED (${APPROVED.length}개, 같은 순서) · template :root --sp-*-kc도 같은 값`, () => {
    assert.deepEqual(JSON.parse(JSON.stringify(env.sp.FALLBACK)), Object.fromEntries(APPROVED.map(([n, k, c]) => [n, [k, c]])));
    assert.deepEqual([...env.sp.names()], APPROVED.map(a => a[0]));
    const tpl = readFileSync(join(ROOT, 'src/template.html'), 'utf8');
    for (const [name, k, c] of APPROVED) assert.ok(tpl.includes(`--sp-${name}-kc:"${k} ${c}";`), `template --sp-${name}-kc`);
    assert.equal(env.sp.THROW, 0.11); assert.equal(env.sp.DT_MAX, 0.1); assert.equal(env.sp.REST, 1e-3);
  });
  let cells = 0, worst = 0;
  t(`닫힌 해 = RK4 수치 적분 (${ALL.length}개 스프링 × 시작값 4가지 × 시각 8개, 위치 · 속도 상대 오차 < 1e-7)`, () => {
    const starts = [[0, 100, 0], [100, -40, -900], [5, 5, 300], [-3, 7, 50]];
    const times = [0, 0.004, 0.017, 0.05, 0.1, 0.2, 0.35, 0.6];
    for (const [name, k, c] of ALL) for (const [from, to, v0] of starts) {
      const sol = env.sp.solve(k, c, from, to, v0), ref = rk4(k, c, from, v0, to, times);
      const scale = Math.max(Math.abs(to - from), Math.abs(v0) / Math.sqrt(k));
      times.forEach((tt, i) => {
        const [x, v] = sol.at(tt);
        const ex = Math.abs(x - ref[i][0]) / scale, ev = Math.abs(v - ref[i][1]) / (scale * Math.sqrt(k));
        worst = Math.max(worst, ex, ev); cells++;
        assert.ok(ex < 1e-7 && ev < 1e-7, `${name} ${from}→${to} v0 ${v0} @${tt}: x ${x} vs ${ref[i][0]}, v ${v} vs ${ref[i][1]}`);
        close(sol.x(tt), x, 0, 'x()'); close(sol.v(tt), v, 0, 'v()');
      });
    }
  });
  console.log(`     ${cells}칸, 최대 상대 오차 ${worst.toExponential(2)}`);
  t('scripts/springs.mjs spring()와 같은 해 (0 → 1, 처음 속도 v0) · 영역(덜 · 임계 · 과감쇠)', () => {
    for (const [name, k, c] of ALL) for (const v0 of [0, 3, -5]) {
      const a = env.sp.solve(k, c, 0, 1, v0), b = refSpring(k, c, 1, v0);
      assert.equal(a.regime, b.regime, name);
      for (const tt of [0.01, 0.08, 0.3]) { close(a.x(tt), b.x(tt), 1e-12, `${name} x`); close(a.v(tt), b.v(tt), 1e-10, `${name} v`); }
    }
    assert.equal(env.sp.solve(400, 40, 0, 1).regime, 'critical'); assert.equal(env.sp.solve(400, 70, 0, 1).regime, 'over');
    assert.throws(() => env.sp.solve(0, 10, 0, 1), { name: 'RangeError' }); assert.throws(() => env.sp.solve(100, -1, 0, 1), { name: 'RangeError' });
  });
  t('넘침 = 100·exp(−ζπ/√(1−ζ²)) (덜 감쇠 전부, 꼭짓점 t = π/ωd), design.md §6-2 표 값과 같음 · 임계 · 과감쇠는 0', () => {
    for (const [name, k, c] of ALL) {
      const sol = env.sp.solve(k, c, 0, 1, 0), z = sol.zeta;
      let peak = -Infinity, tp = 0;
      for (let i = 0; i <= 200000; i++) { const tt = i * 1e-5; const x = sol.x(tt); if (x > peak) { peak = x; tp = tt; } }
      const pct = 100 * (peak - 1);
      if (z < 1) {
        const want = 100 * Math.exp(-z * Math.PI / Math.sqrt(1 - z * z));
        close(pct, want, 1e-6, `${name} overshoot %`);
        close(tp, Math.PI / (Math.sqrt(k) * Math.sqrt(1 - z * z)), 2e-5, `${name} peak time`);
        const tab = APPROVED.find(a => a[0] === name);
        if (tab) close(pct, measure(k, c).overshootPct, 1e-3, `${name} vs design table`);
      } else assert.ok(pct <= 1e-9, `${name} ζ ${z} overshoots ${pct}`);
    }
  });
}

console.log('2. 공용 rAF 루프');
{
  t('lead 0 → 100: 프레임마다 닫힌 해 그대로 (첫 프레임 1/60초), 끝에 onUpdate(100, 0) · onRest 한 번, 그 뒤 rAF 0', () => {
    const env = load(), ups = [], rests = [];
    const h = env.sp.animate({ from: 0, to: 100, name: 'lead', onUpdate: (v, vel) => ups.push([v, vel]), onRest: v => rests.push(v) });
    assert.equal(env.pending(), 1); assert.ok(h.running()); assert.equal(env.sp.stats().active, 1);
    const { k, c } = kcOf('lead'), sol = env.sp.solve(k, c, 0, 100, 0);
    let frames = 0;
    while (env.pending()) {
      env.frame(); frames++;
      if (h.running()) { const [x, v] = sol.at(frames / 60); close(h.value(), x, 1e-9, `frame ${frames}`); close(h.velocity(), v, 1e-9); }
    }
    assert.deepEqual(JSON.parse(JSON.stringify(ups.at(-1))), [100, 0]); assert.deepEqual(rests, [100]);
    assert.equal(h.value(), 100); assert.equal(h.velocity(), 0); assert.equal(h.running(), false);
    const s = env.sp.stats(); assert.equal(s.active, 0); assert.equal(s.scheduled, false);
    const calls = env.rafCalls;
    for (let i = 0; i < 20; i++) env.frame();
    assert.equal(env.rafCalls, calls, 'no rAF requested while idle'); assert.equal(env.errors.length, 0);
    assert.ok(frames > 15 && frames < 30, `lead rests after ${frames} frames (${Math.round(frames * 1000 / 60)} ms)`);
  });
  t('스프링 6개가 동시에 움직여도 rAF 요청은 프레임마다 1번 · 끝나면 멈추고, 새 움직임에 다시 1번', () => {
    const env = load();
    const hs = APPROVED.slice(0, 6).map(([name], i) => env.sp.animate({ from: 0, to: 10 * (i + 1), name }));
    assert.equal(env.rafCalls, 1);
    let frames = 0;
    while (env.pending()) { assert.equal(env.pending(), 1); const before = env.rafCalls; env.frame(); frames++; assert.ok(env.rafCalls - before <= 1); }
    assert.equal(env.rafCalls, frames, 'one request per frame');
    assert.ok(hs.every(h => !h.running() && h.value() === h.target()));
    hs[2].retarget(-5); assert.equal(env.pending(), 1); env.run(); assert.equal(hs[2].value(), -5); assert.equal(env.pending(), 0);
  });
  t('dt는 0.1초까지만: 2초 멈춘 프레임도 0.1초만 나아감 (탭 멈춤 · GC 뒤 뜀 없음)', () => {
    const env = load();
    const h = env.sp.animate({ from: 0, to: 100, name: 'trail' });
    env.frame(); env.frame(2000);
    const { k, c } = kcOf('trail');
    close(h.value(), env.sp.solve(k, c, 0, 100, 0).x(1 / 60 + 0.1), 1e-9);
    env.frame(1000 / 60); close(h.value(), env.sp.solve(k, c, 0, 100, 0).x(2 / 60 + 0.1), 1e-9);
  });
}

console.log('3. 다시 겨누기 = 속도 이어받기');
{
  t('trail 0 → 100, 120ms에 −50으로: 위치 · 속도 그대로, 그 뒤 궤적 = 목표가 바뀌는 RK4 (CSS처럼 속도 0에서 다시 시작하면 > 5px 차이)', () => {
    const env = load();
    const { k, c } = kcOf('trail');
    const h = env.sp.animate({ from: 0, to: 100, name: 'trail' });
    for (let i = 0; i < 120; i++) env.frame(1);   // 1ms frames: first frame advances 1/60 s, then 1 ms each
    const t1 = 1 / 60 + 0.119, x1 = h.value(), v1 = h.velocity();
    close(x1, env.sp.solve(k, c, 0, 100, 0).x(t1), 1e-9);
    assert.ok(v1 > 100, `moving fast at the switch (${v1.toFixed(1)} px/s)`);
    h.retarget(-50);
    assert.equal(h.value(), x1); assert.equal(h.velocity(), v1); assert.equal(h.target(), -50);
    const samples = [];
    for (let i = 1; i <= 400; i++) { env.frame(1); if (h.running()) samples.push([t1 + i / 1000, h.value(), h.velocity()]); }
    const ref = rk4(k, c, 0, 0, 100, samples.map(s => s[0]), { tSwitch: t1, to2: -50, h: 2e-6 });
    samples.forEach(([tt, x, v], i) => { close(x, ref[i][0], 2e-5, `x @${tt.toFixed(3)}`); close(v, ref[i][1], 2e-3, `v @${tt.toFixed(3)}`); });
    const restart = env.sp.solve(k, c, x1, -50, 0);
    const gap = Math.max(...samples.slice(0, 120).map(([tt, x]) => Math.abs(x - restart.x(tt - t1))));
    assert.ok(gap > 5, `velocity matters: restart-from-0 differs by ${gap.toFixed(2)} px`);
  });
  t('이름을 바꿔 겨눠도(lead → settle) 속도 그대로 · {velocity}로 덮어쓰기 · {k, c} 직접', () => {
    const env = load();
    const h = env.sp.animate({ from: 0, to: 100, name: 'lead' });
    for (let i = 0; i < 6; i++) env.frame();
    const v = h.velocity(), x = h.value();
    h.retarget(200, { name: 'settle' });
    assert.equal(h.velocity(), v); assert.equal(h.value(), x); assert.deepEqual(JSON.parse(JSON.stringify(h.spring())), { name: 'settle', ...kcOf('settle') });
    env.frame(); close(h.value(), env.sp.solve(280, 27, x, 200, v).x(1 / 60), 1e-9);
    h.retarget(50, { velocity: -300 }); assert.equal(h.velocity(), -300);
    h.retarget(50, { k: 500, c: 45 }); assert.deepEqual(JSON.parse(JSON.stringify(h.spring())), { name: null, k: 500, c: 45 });
    env.run(); assert.equal(h.value(), 50);
  });
  t('속도 연속: 다시 겨누는 순간 앞뒤 차분 속도가 같음 (0.1ms 프레임, 가속도 뜀만큼의 차이 안)', () => {
    const env = load();
    const h = env.sp.animate({ from: 0, to: 300, name: 'lead' });
    env.frame(); for (let i = 0; i < 400; i++) env.frame(0.1);
    const a = h.value(); env.frame(0.1); const b = h.value(); const vBefore = (b - a) / 1e-4;
    h.retarget(-100);
    env.frame(0.1); const c = h.value(); const vAfter = (c - b) / 1e-4;
    const accJump = 620 * 400;   // k·Δtarget
    assert.ok(Math.abs(vAfter - vBefore) < accJump * 1e-4 * 1.5, `${vBefore.toFixed(2)} → ${vAfter.toFixed(2)} px/s`);
    assert.ok(Math.abs(vBefore) > 500);
  });
}

console.log('4. 줄이기 · 숨은 탭 = 끝값 바로');
{
  await ta('KH.motion() reduced → onUpdate(to, 0)를 바로(동기), rAF 0, onRest는 마이크로태스크 한 번 · 다시 겨눠도 바로', async () => {
    const env = load({ motion: 'reduced' }), ups = [], rests = [];
    const h = env.sp.animate({ from: 0, to: 100, name: 'lead', onUpdate: (v, vel) => ups.push([v, vel]), onRest: v => rests.push(v) });
    assert.deepEqual(JSON.parse(JSON.stringify(ups)), [[100, 0]]); assert.equal(h.value(), 100); assert.equal(h.running(), false);
    assert.equal(env.pending(), 0); assert.equal(env.rafCalls, 0); assert.deepEqual(rests, []);
    await null; assert.deepEqual(rests, [100]);
    h.retarget(-20); assert.equal(h.value(), -20); assert.equal(env.pending(), 0); await null; assert.deepEqual(rests, [100, -20]);
  });
  await ta('숨은 탭(document.hidden) → 끝값 바로', async () => {
    const env = load({ hidden: true }), rests = [];
    const h = env.sp.animate({ from: 0, to: 40, name: 'open', onRest: v => rests.push(v) });
    assert.equal(h.value(), 40); assert.equal(env.pending(), 0); await null; assert.deepEqual(rests, [40]);
  });
  t('움직이는 중 kh:motion → reduced · visibilitychange → hidden: 다 끝값으로(onRest 한 번씩), rAF 취소', () => {
    for (const how of ['motion', 'hidden']) {
      const env = load(), rests = [];
      const hs = [['lead', 100], ['trail', -30], ['value', 7]].map(([name, to]) => env.sp.animate({ from: 0, to, name, onRest: v => rests.push(v) }));
      env.frame(); env.frame();
      assert.ok(hs.every(h => h.running()));
      if (how === 'motion') env.motionTo('reduced'); else env.hide(true);
      assert.ok(hs.every(h => !h.running() && h.value() === h.target() && h.velocity() === 0), how);
      assert.deepEqual(rests, [100, -30, 7]); assert.equal(env.pending(), 0, `${how}: frame cancelled`);
      assert.equal(env.sp.stats().active, 0);
    }
  });
  await ta('fancy: true는 화려하게에서만 움직임 — 기본이면 바로, 화려하게 → 기본으로 바뀌면 그것만 끝남', async () => {
    const env = load({ motion: 'standard' });
    const a = env.sp.animate({ from: 0, to: 10, name: 'roll', fancy: true });
    assert.equal(a.value(), 10); assert.equal(env.pending(), 0);
    env.motion = 'fancy';
    const b = env.sp.animate({ from: 0, to: 10, name: 'roll', fancy: true }), c = env.sp.animate({ from: 0, to: 10, name: 'lead' });
    env.frame(); assert.ok(b.running() && c.running());
    env.motionTo('standard');
    assert.ok(!b.running() && b.value() === 10); assert.ok(c.running(), 'plain spring keeps moving in standard');
    env.run(); assert.equal(c.value(), 10);
  });
}

console.log('5. 서는 때');
{
  t('|x − to| < 1e-3·거리 이고 |v| < 1e-3·거리·ω0 인 첫 프레임에 섬 (그 앞 프레임은 아님) — 스프링 14개 전부', () => {
    for (const [name, k, c] of APPROVED) {
      const env = load();
      let restAt = null;
      const h = env.sp.animate({ from: 0, to: 250, name, onRest: () => { restAt = env.now(); } });
      const t0 = env.now();
      while (env.pending()) env.frame(1);
      assert.equal(h.value(), 250);
      const sol = env.sp.solve(k, c, 0, 250, 0), w0 = Math.sqrt(k), dX = 1e-3 * 250, dV = dX * w0;
      const tRest = (restAt - t0 - 1) / 1000 + 1 / 60;   // first frame advanced 1/60 s, then 1 ms per frame
      const ok = tt => { const [x, v] = sol.at(tt); return Math.abs(x - 250) < dX && Math.abs(v) < dV; };
      assert.ok(ok(tRest), `${name}: at rest frame`); assert.ok(!ok(tRest - 1e-3), `${name}: not one frame earlier`);
      const settle01 = measure(k, c).settle01Ms;
      assert.ok(tRest * 1000 <= settle01 + 40, `${name}: rests at ${(tRest * 1000).toFixed(0)} ms (0.1% settle ${settle01} ms)`);
    }
  });
  await ta('from = to · 속도 0 → 바로 섬(rAF 0) · from = to에 속도 있으면 갔다가 돌아와서 섬 · restDelta 직접', async () => {
    const env = load(), rests = [];
    const a = env.sp.animate({ from: 5, to: 5, name: 'lead', onRest: v => rests.push(v) });
    assert.equal(env.pending(), 0); await null; assert.deepEqual(rests, [5]);
    let max = 5;
    const b = env.sp.animate({ from: 5, to: 5, velocity: 600, name: 'settle', onUpdate: v => { max = Math.max(max, v); } });
    assert.ok(b.running()); env.run(); assert.equal(b.value(), 5); assert.ok(max > 6, `went out to ${max.toFixed(2)}`);
    let fr = 0; const c = env.sp.animate({ from: 0, to: 100, name: 'lead', restDelta: 5 }); while (env.pending()) { env.frame(); fr++; }
    let fr2 = 0; env.sp.animate({ from: 0, to: 100, name: 'lead' }); while (env.pending()) { env.frame(); fr2++; }
    assert.ok(fr < fr2, `restDelta 5 rests sooner (${fr} < ${fr2} frames)`); assert.equal(c.value(), 100);
  });
  t('stop()은 그 자리에 멈춤(onRest 없음) · set(v)는 바로 그 값(onUpdate 한 번) · 둘 다 rAF를 놓음', () => {
    const env = load(), ups = [], rests = [];
    const h = env.sp.animate({ from: 0, to: 100, name: 'lead', onUpdate: v => ups.push(v), onRest: v => rests.push(v) });
    env.frame(); env.frame(); const x = h.value(); h.stop();
    assert.equal(h.value(), x); assert.equal(h.running(), false); assert.equal(env.pending(), 0); env.run(); assert.deepEqual(rests, []);
    h.set(42); assert.equal(h.value(), 42); assert.equal(h.target(), 42); assert.equal(ups.at(-1), 42); assert.equal(env.pending(), 0);
  });
}

console.log('6. 이름 붙은 스프링 · 오류');
{
  t('CSS --sp-<이름>-kc("k c")를 먼저 읽고, 없거나 틀리면 표 · kh:theme이면 다시 읽음 · 없는 이름은 RangeError', () => {
    const env = load({ css: { '--sp-lead-kc': '"700 45"', '--sp-trail-kc': '"abc"', '--sp-fade-kc': ' "420 37"' } });
    assert.deepEqual(JSON.parse(JSON.stringify(env.sp.params('lead'))), { name: 'lead', k: 700, c: 45, w0: Math.sqrt(700), zeta: 45 / (2 * Math.sqrt(700)), source: 'css' });
    assert.equal(env.sp.params('trail').source, 'fallback'); assert.equal(env.sp.params('trail').k, 190);
    assert.equal(env.sp.params('fade').source, 'css');
    assert.equal(env.sp.animate({ from: 0, to: 1, name: 'lead' }).spring().k, 700);
    env.css['--sp-lead-kc'] = '"800 50"'; assert.equal(env.sp.params('lead').k, 700, 'cached');
    env.document.dispatchEvent(new CustomEvent('kh:theme', { detail: { theme: 'paper' } })); assert.equal(env.sp.params('lead').k, 800);
    for (const [name, k, c] of APPROVED) { const p = load().sp.params(name); assert.equal(p.k, k); assert.equal(p.c, c); }
    assert.throws(() => env.sp.params('nope'), { name: 'RangeError' });
    assert.throws(() => env.sp.animate({ from: 0, to: 1 }), { name: 'TypeError' });
    assert.throws(() => env.sp.animate({ from: 0, to: NaN, name: 'lead' }), { name: 'TypeError' });
    assert.equal(env.sp.animate({ from: 0, to: 1, k: 100, c: 20 }).spring().c, 20);
  });
  t('한 모듈의 onUpdate가 던져도 루프는 계속(오류는 보고), 다른 스프링은 끝까지', () => {
    const env = load();
    env.sp.animate({ from: 0, to: 1, name: 'lead', onUpdate: () => { throw new Error('boom'); } });
    const ok = env.sp.animate({ from: 0, to: 50, name: 'trail' });
    env.run();
    assert.equal(ok.value(), 50); assert.ok(env.errors.length > 0 && env.errors.every(e => e.includes('boom'))); assert.equal(env.pending(), 0);
  });
}

console.log('7. edges · knob · release');
{
  t('edges(② 단단한 이동, 기본): 첫 호출은 그 자리에 · 두 가장자리가 같은 lead로 함께(폭은 60 → 80을 고르게, 늘어남 없음) · 프레임마다 쓰기 1번 · will-change는 움직이는 동안만', () => {
    const env = load(), el = fakeEl();
    let rests = 0;
    const ctl = env.sp.edges(el, { left: 0, width: 60 }, { onRest: () => rests++ });
    assert.equal(el.vals.transform, 'translateX(0px)'); assert.equal(el.vals.width, '60px'); assert.equal(env.pending(), 0);
    assert.equal(env.sp.edges(el), ctl, 'one controller per element');
    ctl.to({ left: 200, width: 80 });
    assert.equal(el.vals.willChange, 'transform');
    let maxW = 0, minW = Infinity, maxGap = 0, frames = 0;
    while (env.pending()) {
      const w0 = el.writes.transform || 0;
      env.frame(); frames++;
      assert.equal((el.writes.transform || 0) - w0, 1, 'one transform write per frame');
      const l = tx(el), w = wd(el), r = l + w;
      maxW = Math.max(maxW, w); minW = Math.min(minW, w);
      maxGap = Math.max(maxGap, Math.abs((r - 60) / 220 - (l - 0) / 200));    // both edges the same share of their way: one spring
      if (env.pending()) assert.equal(el.vals.willChange, 'transform');
    }
    assert.equal(el.vals.transform, 'translateX(200px)'); assert.equal(el.vals.width, '80px'); assert.equal(el.vals.willChange, '');
    assert.ok(frames > 5, `${frames} frames`);
    assert.ok(maxGap < 0.002, `edges in step (max gap ${maxGap.toFixed(4)})`);
    assert.ok(minW >= 60 - 0.01 && maxW <= 80 + 0.5, `width stays between 60 and 80 (+ lead's 1.45 % of 20): ${minW.toFixed(2)} – ${maxW.toFixed(2)}`);
    assert.equal(rests, 1);
    // the same width both ways: a rigid move keeps it exactly
    ctl.to({ left: 20, width: 80 }); let w2 = new Set();
    while (env.pending()) { env.frame(); w2.add(wd(el).toFixed(2)); }
    assert.deepEqual([...w2], ['80.00'], 'same width → the width never changes'); assert.equal(rests, 2);
    assert.equal(env.errors.length, 0);
  });
  t('edges({trail:"trail"}): 부르는 쪽이 고르면 예전처럼 가는 쪽 가장자리가 앞서고(lead) 뒤가 따라와 늘었다 줄며 도착', () => {
    const env = load(), el = fakeEl();
    const ctl = env.sp.edges(el, { left: 0, width: 60 }, { trail: 'trail' });
    ctl.to({ left: 200, width: 80 });
    let maxW = 0, leadAhead = 0, frames = 0;
    while (env.pending()) { env.frame(); frames++; const l = tx(el), w = wd(el), r = l + w; maxW = Math.max(maxW, w); if ((r - 60) / 220 > (l - 0) / 200 + 0.05) leadAhead++; }
    assert.ok(maxW > 80 + 40, `stretched to ${maxW.toFixed(1)}px`); assert.ok(leadAhead > frames / 3, `right edge ahead in ${leadAhead}/${frames} frames`);
    ctl.to({ left: 20, width: 60 }); let leftAhead = 0, fr = 0;
    while (env.pending()) { env.frame(); fr++; const l = tx(el), r = l + wd(el); if ((200 - l) / 180 > (280 - r) / 200 + 0.05) leftAhead++; }
    assert.ok(leftAhead > fr / 3, `left edge ahead in ${leftAhead}/${fr} frames`);
  });
  t('edges: 방향을 도중에 바꿔도 가장자리 위치가 튀지 않음 · set(box)은 바로(키보드 연달아, §8) · write:"left" · 글자 있는 요소엔 will-change 없음 · 원래 will-change로 되돌림', () => {
    const env = load(), el = fakeEl();
    const ctl = env.sp.edges(el, { left: 0, width: 50 });
    ctl.to({ left: 300, width: 50 }); for (let i = 0; i < 8; i++) env.frame();
    const before = ctl.value(); ctl.to({ left: 0, width: 50 }); const after = ctl.value();
    assert.equal(after.left, before.left); assert.equal(after.width, before.width);
    env.frame(); const step = Math.abs(ctl.value().left - before.left); assert.ok(step < 40, `no jump (${step.toFixed(1)}px in a frame)`);
    ctl.set({ left: 120, width: 40 }); assert.equal(el.vals.transform, 'translateX(120px)'); assert.equal(ctl.moving(), false); assert.equal(env.pending(), 0);
    const e2 = fakeEl(); const c2 = env.sp.edges(e2, { left: 0, width: 30 }, { write: 'left' }); c2.to({ left: 90, width: 30 });
    assert.equal(e2.vals.left, '0px'); env.run(); assert.equal(e2.vals.left, '90px'); assert.equal(e2.vals.transform, undefined); assert.equal(e2.writes.willChange, undefined);
    const e3 = fakeEl('코스피'); env.sp.edges(e3, { left: 0, width: 30 }).to({ left: 90, width: 30 }); env.frame(); assert.equal(e3.writes.willChange, undefined); env.run();
    const e4 = fakeEl(); e4.vals.willChange = 'opacity'; env.sp.edges(e4, { left: 0, width: 30 }).to({ left: 90, width: 30 });
    assert.equal(e4.vals.willChange, 'transform'); env.run(); assert.equal(e4.vals.willChange, 'opacity');
  });
  await ta('edges: 줄이기면 to()가 바로 끝값 · will-change 안 붙음 · onRest 한 번', async () => {
    const env = load({ motion: 'reduced' }), el = fakeEl(); let rests = 0;
    const ctl = env.sp.edges(el, { left: 0, width: 60 }, { onRest: () => rests++ });
    ctl.to({ left: 200, width: 80 });
    assert.equal(el.vals.transform, 'translateX(200px)'); assert.equal(el.vals.width, '80px'); assert.equal(env.pending(), 0); assert.equal(el.writes.willChange, undefined);
    await null; await null; assert.equal(rests, 1);
  });
  t('knob(② 단단한 이동, 기본): 모양 그대로 lead 하나로(폭 20 고정, 20px · 200px 이동) · {stretch:3, front:"follow", back:"settle"}을 고르면 예전처럼 ≤ 3px 늘어남', () => {
    const { k, c } = kcOf('lead');
    for (const travel of [20, 200]) {
      const env = load(), el = fakeEl();
      const kn = env.sp.knob(el, 0, { width: 20 });
      assert.equal(el.vals.transform, 'translateX(0px)'); assert.equal(el.vals.width, '20px');
      kn.to(travel); const ws = new Set(); let fr = 0, t = 0, maxErr = 0;
      const sol = env.sp.solve(k, c, 0, travel, 0);
      while (env.pending()) {
        env.frame(); fr++; t += 1 / 60; ws.add(el.vals.width);
        if (env.pending()) maxErr = Math.max(maxErr, Math.abs(tx(el) - sol.x(t)));
      }
      assert.deepEqual([...ws], ['20px'], `travel ${travel}: the knob keeps its width`);
      assert.ok(maxErr < 0.02 * travel + 0.05, `travel ${travel}: rides lead (max ${maxErr.toFixed(3)}px off the closed form)`);
      assert.ok(fr > 5); assert.equal(el.vals.transform, `translateX(${travel}px)`); assert.equal(el.vals.willChange, '');
    }
    for (const travel of [20, 200]) {
      const env = load(), el = fakeEl();
      const kn = env.sp.knob(el, 0, { width: 20, stretch: 3, front: 'follow', back: 'settle' });
      kn.to(travel); let maxS = 0, frontFirst = 0, fr = 0;
      while (env.pending()) {
        env.frame(); fr++;
        const l = tx(el), w = wd(el); maxS = Math.max(maxS, w - 20);
        if ((l + w - 20) / travel > l / travel + 1e-3) frontFirst++;
      }
      assert.ok(maxS <= 3 + 0.01 && maxS > (travel === 20 ? 2 : 2.9), `travel ${travel}: max stretch ${maxS.toFixed(2)}px`);
      assert.ok(frontFirst > fr / 3, `front edge ahead in ${frontFirst}/${fr} frames`);
      assert.equal(el.vals.transform, `translateX(${travel}px)`); assert.equal(el.vals.width, '20px'); assert.equal(el.vals.willChange, '');
    }
    const env = load(), el = fakeEl(); const kn = env.sp.knob(el, 0, { width: 18, stretch: 0, front: 'follow', back: 'settle' }); kn.to(20); let mw = 0;
    while (env.pending()) { env.frame(); mw = Math.max(mw, wd(el)); } assert.equal(mw, 18);
    // going left with a stretch: the left edge leads, the box only grows to the right of it
    const e2 = fakeEl(); const k2 = env.sp.knob(e2, 20, { width: 20, stretch: 3 }); k2.configure({ front: 'follow', back: 'settle' }); k2.to(0); env.frame(); env.frame(); env.frame();
    assert.ok(tx(e2) < 20 && wd(e2) > 20);
  });
  t(`release: px/ms → px/s로 settle 스프링 · |v| > 0.11 px/ms = 던짐(그 쪽 다음 점), 아니면 가장 가까운 점 · knob도 받음 · maxOvershoot`, () => {
    const env = load();
    const h = env.sp.animate({ from: 0, to: 0, name: 'follow' });
    h.set(70);
    let r = env.sp.release(h, -0.05, { points: [0, 100] });
    assert.deepEqual(JSON.parse(JSON.stringify(r)), { to: 100, thrown: false, velocity: -0.05, carried: -0.05 });
    assert.equal(h.velocity(), -50); assert.deepEqual(JSON.parse(JSON.stringify(h.spring())), { name: 'settle', ...kcOf('settle') });
    h.set(70); r = env.sp.release(h, -0.2, { points: [0, 100] }); assert.equal(r.to, 0); assert.equal(r.thrown, true); assert.equal(h.velocity(), -200);
    h.set(30); r = env.sp.release(h, 0.12, { points: [0, 100] }); assert.equal(r.to, 100);
    h.set(100); r = env.sp.release(h, 0.5, { points: [0, 100] }); assert.equal(r.to, 100, 'nothing ahead → nearest');
    h.set(50); r = env.sp.release(h, 0.11, { points: [0, 40, 100] }); assert.equal(r.thrown, false, 'exactly 0.11 is not a throw'); assert.equal(r.to, 40);
    h.set(10); r = env.sp.release(h, 0.3); assert.equal(r.to, 10, 'no points → target'); r = env.sp.release(h, 0.3, { to: 77 }); assert.equal(r.to, 77);
    env.run(); assert.equal(h.value(), 77);
    // a hard throw 8px before the end overshoots by physics (= the closed form) · maxOvershoot keeps only the speed that stays within it
    const el = fakeEl(), kn = env.sp.knob(el, 0, { width: 20 });
    kn.set(12); r = env.sp.release(kn, 0.4, { points: [0, 20] }); assert.equal(r.to, 20); assert.equal(kn.velocity(), 400); assert.equal(r.carried, 0.4);
    let mx = 0; while (env.pending()) { env.frame(1); mx = Math.max(mx, kn.value()); }
    const sol = env.sp.solve(280, 27, 12, 20, 400); let want = 0; for (let i = 0; i < 2000; i++) want = Math.max(want, sol.x(i / 4000));
    assert.equal(kn.value(), 20); close(mx, want, 0.02, 'free release overshoot = closed form');
    kn.set(12); r = env.sp.release(kn, 0.4, { points: [0, 20], maxOvershoot: 1 });
    assert.ok(r.carried > 0.05 && r.carried < 0.4, `carried ${r.carried.toFixed(3)} px/ms`); close(kn.velocity(), r.carried * 1000, 1e-9);
    mx = 0; while (env.pending()) { env.frame(1); mx = Math.max(mx, kn.value()); }
    assert.ok(mx <= 21 + 0.01 && mx > 20.5, `capped overshoot ${(mx - 20).toFixed(2)}px (free ${(want - 20).toFixed(2)}px)`);
    h.set(0); r = env.sp.release(h, 0.3, { to: 300, maxOvershoot: 6 }); assert.equal(r.carried, 0.3, 'far target (own overshoot 4.1px): nothing to cap'); env.run();
    assert.throws(() => env.sp.release({}, 0.2), { name: 'TypeError' });
  });
}

console.log(`   ${n}개 통과 (단위)`);
if (process.argv.includes('--no-browser')) process.exit(0);

/* ───────── the built page ───────── */
console.log('8. 빌드된 페이지 (Chromium)');
const require = createRequire(import.meta.url);
let pw;
for (const p of ['playwright', '/opt/npm-tools/node_modules/playwright']) { try { pw = require(p); break; } catch (e) { } }
assert.ok(pw, 'playwright를 찾지 못했어요 (--no-browser로 건너뛸 수 있어요)');
for (const f of ['dist/index.html', 'web/index.html']) {
  assert.ok(existsSync(join(ROOT, f)), `${f} 없음 — python3 scripts/build_page.py`);
  assert.ok(readFileSync(join(ROOT, f), 'utf8').includes(SRC.trim().slice(0, 200).replace(/<\/script/g, '<\\/script')), `${f}에 src/ui/spring.js가 없어요 — 다시 빌드`);
}
const PORT = +(process.env.SPRING_QA_PORT || 8940);
assert.ok((PORT >= 8940 && PORT <= 8949) || (PORT >= 9070 && PORT <= 9079), 'ports 8940–8949 (or 9070–9079)');
spawnSync('fuser', ['-k', `${PORT}/tcp`], { stdio: 'ignore' });
const mock = spawn('python3', [join(ROOT, 'qa/news/mock_api.py'), String(PORT)], { stdio: 'ignore', env: { ...process.env, MOCK_WEB: join(ROOT, 'web') } });
const browser = await pw.chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
// the live page keeps its main thread busy for a while after load (3–11 frames/s seen at +1.5 s): wait for ≥ 24 frames/s first
const quiet = async (page) => {
  for (let i = 0; i < 30; i++) {
    const fps = await page.evaluate(() => new Promise(r => { const t0 = performance.now(); let k = 0; const f = () => { k++; if (performance.now() - t0 < 500) requestAnimationFrame(f); else r(k * 2); }; requestAnimationFrame(f); }));
    if (fps >= 24) return fps;
  }
  return 0;
};
const DEMO = async (page) => page.evaluate(async () => {
  const track = document.createElement('div');
  track.style.cssText = 'position:fixed;left:10px;top:10px;width:400px;height:32px;z-index:99999;pointer-events:none';
  const ind = document.createElement('div');
  ind.style.cssText = 'position:absolute;left:0;top:0;height:32px;background:#ffb547;border-radius:10px';
  track.append(ind); document.body.append(track);
  const ctl = KH.spring.edges(ind, { left: 0, width: 60 });
  const first = [ind.style.transform, ind.style.width];
  const samples = [];
  await new Promise(r => requestAnimationFrame(r));
  ctl.to({ left: 200, width: 80 });
  const sync = [ind.style.transform, ind.style.willChange];
  const t0 = performance.now();
  await new Promise(done => {
    const f = () => {
      const r = ind.getBoundingClientRect();
      samples.push([performance.now() - t0, ind.style.transform, ind.style.width, ind.style.willChange, r.left - 10, r.width]);
      const atRest = ind.style.transform === 'translateX(200px)' && ind.style.width === '80px' && !KH.spring.stats().active;
      if (performance.now() - t0 < 3000 && !(atRest && performance.now() - t0 > 200)) requestAnimationFrame(f); else done();
    };
    requestAnimationFrame(f);
  });
  const out = { first, sync, samples, stats: KH.spring.stats(), end: [ind.style.transform, ind.style.width, ind.style.willChange] };
  track.remove();
  return out;
});
try {
  const targets = [['스냅샷 dist/index.html', pathToFileURL(join(ROOT, 'dist/index.html')).href], ['실시간 web/index.html (mock)', `http://127.0.0.1:${PORT}/`]];
  for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/__reset`); if (r.ok) break; } catch (e) { } await new Promise(r => setTimeout(r, 100)); }
  for (const [label, url] of targets) {
    for (const [w, h] of [[1440, 900], [390, 844]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 760, hasTouch: w < 760 });
      await ctx.addInitScript(() => { try { localStorage.setItem('khm.tickerPaused', 'true'); } catch (e) { } });
      const page = await ctx.newPage();
      const errs = [];
      page.on('pageerror', e => errs.push('pageerror: ' + e)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
      await page.goto(url); await page.waitForTimeout(1500); await quiet(page);
      const info = await page.evaluate(() => ({
        api: Object.keys(KH.spring).sort(), motion: KH.motion(),
        css: KH.spring.names().map(n => { const p = KH.spring.params(n); return [n, p.k, p.c, p.source]; }),
      }));
      assert.deepEqual(info.api, ['DT_MAX', 'FALLBACK', 'REST', 'THROW', 'animate', 'edges', 'knob', 'names', 'params', 'release', 'solve', 'stats']);
      assert.deepEqual(info.css, APPROVED.map(([n, k, c]) => [n, k, c, 'css']), 'every named spring read from the page CSS');
      const d = await DEMO(page);
      assert.deepEqual(d.first, ['translateX(0px)', '60px']); assert.deepEqual(d.sync, ['translateX(0px)', 'transform']);
      const moving = d.samples.filter(s => s[1] !== 'translateX(200px)' || s[2] !== '80px');
      const distinct = new Set(moving.map(s => s[1] + s[2])).size;
      const maxW = Math.max(...d.samples.map(s => s[5])), minW = Math.min(...d.samples.map(s => s[5]));
      const restMs = (d.samples.find(s => s[1] === 'translateX(200px)' && s[2] === '80px') || [Infinity])[0];
      assert.ok(distinct >= 10, `${label} ${w}: ${distinct} distinct frames`);
      assert.ok(minW >= 59.5 && maxW <= 81, `${label} ${w}: rigid (② 단단한 이동) — width ${minW.toFixed(1)} – ${maxW.toFixed(1)}px, never stretched`);
      assert.ok(restMs > 250 && restMs < 3000, `${label} ${w}: rests after ${restMs.toFixed(0)} ms`);
      assert.ok(moving.every(s => s[3] === 'transform'), 'will-change while moving'); assert.deepEqual(d.end, ['translateX(200px)', '80px', '']);
      assert.deepEqual(d.stats, { active: 0, scheduled: false }, 'loop off when idle');
      // rect follows the inline style (no layout reads needed): left edge = translateX, box width = width
      const lastMoving = moving.at(-1); assert.ok(Math.abs(lastMoving[4] - parseFloat(lastMoving[1].slice(11))) < 0.6);
      // 줄이기 (a fresh context that starts with khm.motion = reduced): the same indicator ends at once
      const rctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 760, hasTouch: w < 760 });
      await rctx.addInitScript(() => { try { localStorage.setItem('khm.tickerPaused', 'true'); localStorage.setItem('khm.motion', JSON.stringify('reduced')); } catch (e) { } });
      const rpage = await rctx.newPage();
      rpage.on('pageerror', e => errs.push('pageerror: ' + e)); rpage.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
      await rpage.goto(url); await rpage.waitForTimeout(1200);
      const red = await rpage.evaluate(() => {
        const ind = document.createElement('div'); document.body.append(ind);
        const ctl = KH.spring.edges(ind, { left: 0, width: 60 }); ctl.to({ left: 200, width: 80 });
        const r = [KH.motion(), ind.style.transform, ind.style.width, ind.style.willChange, KH.spring.stats().active]; ind.remove(); return r;
      });
      assert.deepEqual(red, ['reduced', 'translateX(200px)', '80px', '', 0]);
      await rctx.close();
      assert.deepEqual(errs, [], `${label} ${w}: console errors`);
      console.log(`  ✓ ${label} ${w}×${h}: KH.spring (${info.css.length}개 CSS에서), 표시 ${distinct}프레임 · 폭 ${minW.toFixed(0)}–${maxW.toFixed(0)}px(늘어남 없음) · ${restMs.toFixed(0)}ms에 섬 · 줄이기 바로 · 콘솔 오류 0`); n++;
      await ctx.close();
    }
  }
} finally {
  await browser.close();
  mock.kill();
  spawnSync('fuser', ['-k', `${PORT}/tcp`], { stdio: 'ignore' });
}
console.log(`   ${n}개 통과`);
