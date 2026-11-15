#!/usr/bin/env node
/* 스프링 토큰 점검 (scripts/springs.mjs · drafts/springs.css · drafts/springs.html).
 *   node qa/motion/test_springs.mjs            → 수학 + 생성 파일 + Chromium(Playwright)
 *   node qa/motion/test_springs.mjs --no-browser
 * 의존성: 없음(수학). 브라우저 단계는 playwright(전역 /opt/npm-tools 또는 node_modules) + /usr/bin/google-chrome.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import {
  spring, settle, overshoot, overshootFormula, parseLinear, evalLinear, toLinear, cubicBezier, bezierOvershootPct,
  build, css, SPRINGS, LIMIT_PCT, ALT_ZETA, TOL, altDamping, measure,
} from '../../scripts/springs.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
let n = 0;
const t = (name, fn) => { fn(); n++; console.log('  ✓', name); };
const close = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg ?? ''} ${a} vs ${b} (±${eps})`);

/* 독립 확인용: 같은 미분방정식을 RK4로 (닫힌 해를 쓰지 않아요) */
function rk4(k, c, m, v0, T, h = 1e-5) {
  let x = 0, v = v0;
  const a = (x, v) => (-k * (x - 1) - c * v) / m;
  const steps = Math.round(T / h); h = T / steps;
  for (let i = 0; i < steps; i++) {
    const k1x = v, k1v = a(x, v);
    const k2x = v + h / 2 * k1v, k2v = a(x + h / 2 * k1x, v + h / 2 * k1v);
    const k3x = v + h / 2 * k2v, k3v = a(x + h / 2 * k2x, v + h / 2 * k2v);
    const k4x = v + h * k3v, k4v = a(x + h * k3x, v + h * k3v);
    x += h / 6 * (k1x + 2 * k2x + 2 * k3x + k4x); v += h / 6 * (k1v + 2 * k2v + 2 * k3v + k4v);
  }
  return { x, v };
}

console.log('1. 닫힌 해');
t('알려진 값 (mpmath · scipy solve_ivp로 확인한 값)', () => {
  close(spring(100, 20).x(0.1), 1 - 2 / Math.E, 1e-12, '임계 ω0 t = 1 → 1 − 2/e');
  close(spring(100, 20).x(0.1), 0.26424111765711533, 1e-12);
  close(spring(100, 20).x(0.2), 1 - 3 * Math.exp(-2), 1e-12, '임계 ω0 t = 2 → 1 − 3/e²');
  close(spring(100, 10).x(0.05), 0.10440547345507933, 1e-12, '덜 감쇠 ζ .5');
  const u = spring(100, 10);
  close(u.x(Math.PI / u.wd), 1 + Math.exp(-Math.PI / Math.sqrt(3)), 1e-12, '덜 감쇠 꼭짓점 1 + e^(−π/√3)');
  close(spring(100, 50).x(0.1), 0.15178386178471592, 1e-12, '과감쇠 ζ 2.5');
  close(spring(100, 50).x(0.5), 0.6317608708981427, 1e-12);
  assert.equal(spring(100, 10).regime, 'under'); assert.equal(spring(100, 20).regime, 'critical'); assert.equal(spring(100, 50).regime, 'over');
});
t('세 경우 모두 RK4와 같아요 (v0 ≠ 0 포함)', () => {
  for (const [k, c, m, v0] of [[620, 36, 1, 0], [190, 19, 1, 0], [520, 16, 1, 0], [400, 40, 1, 0], [100, 50, 1, 0], [300, 22, 1, 6], [400, 40, 1, -3], [100, 50, .6, 4], [420, 32, .6, 0]]) {
    const sp = spring(k, c, m, v0);
    for (const T of [0.013, 0.07, 0.2, 0.45]) { const r = rk4(k, c, m, v0, T); close(sp.x(T), r.x, 2e-9, `x ${k}/${c}/${m} v0=${v0} t=${T}`); close(sp.v(T), r.v, 2e-7, `v ${k}/${c} t=${T}`); }
  }
});
t('시작 x(0) = 0, x′(0) = v0, 끝 → 1', () => {
  for (const [k, c, v0] of [[620, 36, 0], [100, 20, 0], [100, 50, 0], [300, 22, 5]]) {
    const sp = spring(k, c, 1, v0);
    close(sp.x(0), 0, 1e-15); close(sp.v(0), v0, 1e-12); close(sp.x(20), 1, 1e-12);
    close((sp.x(1e-6) - sp.x(0)) / 1e-6, v0, 1e-3, 'x′(0) 차분');
  }
});
t('임계 · 과감쇠는 단조 증가 (넘침 0)', () => {
  const list = [[100, 20], [100, 50], [900, 60], [190, 2 * Math.sqrt(190)], [620, 80], ...SPRINGS.map(s => [s.k, 2 * Math.sqrt(s.k)])];
  for (const [k, c] of list) {
    const sp = spring(k, c), T = settle(sp, 1e-7);
    let prev = -1;
    for (let i = 0; i <= 20000; i++) { const x = sp.x(T * i / 20000); assert.ok(x >= prev - 1e-15, `단조 ${k}/${c} @${i}`); assert.ok(x <= 1 + 1e-12, `넘지 않음 ${k}/${c}`); prev = x; }
    assert.equal(overshoot(sp).pct < 1e-9, true, `넘침 0 ${k}/${c}`);
  }
});
t('넘침 = 100·exp(−ζπ/√(1−ζ²)) (수치 최댓값과 같아요)', () => {
  for (const s of [...SPRINGS, ...SPRINGS.map(s => ({ k: s.k, c: altDamping(s.k) })), { k: 100, c: 10 }, { k: 520, c: 34 }]) {
    const sp = spring(s.k, s.c), os = overshoot(sp);
    close(os.pct, overshootFormula(sp.zeta), 1e-6 * Math.max(1, os.pct), `${s.k}/${s.c}`);
    // 꼭짓점 시각 = π/ωd
    close(os.tPeak, Math.PI / sp.wd, 1e-9);
  }
});
t('안정 시간: 그 시각에 띠 경계, 그 뒤로는 계속 띠 안', () => {
  for (const s of [...SPRINGS, { k: 100, c: 20 }, { k: 100, c: 50 }]) for (const eps of [0.001, 0.005]) {
    const sp = spring(s.k, s.c), T = settle(sp, eps);
    close(Math.abs(sp.x(T) - 1), eps, 1e-9, `${s.k}/${s.c} 경계`);
    for (let i = 1; i <= 4000; i++) { const tt = T + 3 * T * i / 4000; assert.ok(Math.abs(sp.x(tt) - 1) <= eps + 1e-12, `${s.k}/${s.c} eps ${eps} @${tt}`); }
    assert.ok(Math.abs(sp.x(T * 0.999) - 1) > eps * 0.98 || sp.regime === 'under', '바로 전에는 밖(단조)');
  }
  // 0.5% 시간 ≤ 0.1% 시간, 임계 값은 닫힌 식과 같아요: 1 − e^{−u}(1+u) = 1 − eps
  const sp = spring(400, 40); const T = settle(sp, 0.001); close(Math.exp(-20 * T) * (1 + 20 * T), 0.001, 1e-12);
});

console.log('2. linear() 곡선');
t('linear() 해석이 CSS 규칙과 같아요 (빠진 위치 · 뒤로 가는 위치 · 같은 위치)', () => {
  const f = evalLinear('linear(0, .5, 1)'); close(f(.25), .25, 1e-12); close(f(.75), .75, 1e-12);
  const g = evalLinear('linear(0, .2 10%, .4, .6, 1 90%, 1)'); // .4 → 36.67%, .6 → 63.33%
  const P = parseLinear('linear(0, .2 10%, .4, .6, 1 90%, 1)'); close(P[2].in, .1 + .8 / 3, 1e-12); close(P[3].in, .1 + 1.6 / 3, 1e-12);
  close(g(.05), .1, 1e-12); close(g(.95), 1, 1e-12);
  const b = evalLinear('linear(0, .5 50%, .2 30%, 1)'); // 30% → 50%로 맞춰져요: 50%에서 뛰어요
  close(b(.5), .2, 1e-12); close(b(.75), .6, 1e-12);
  const two = parseLinear('linear(0, .5 20% 40%, 1)'); assert.equal(two.length, 4);
  assert.throws(() => parseLinear('cubic-bezier(0,0,1,1)'));
});
t('모든 토큰: 0에서 시작 · 1로 끝 · 참 곡선과 최대 오차 < 0.5% · 짧음', () => {
  const data = build();
  const all = [...data.springs.flatMap(r => r.alt ? [r.ref, r.alt] : [r.ref]), data.popCheck];
  for (const m of all) {
    const g = evalLinear(m.linear), sp = spring(m.k, m.c);
    close(g(0), 0, 0); close(g(1), 1, 0);
    let e = 0; for (let i = 0; i <= 40000; i++) { const p = i / 40000; e = Math.max(e, Math.abs(g(p) - sp.x(p * m.durMs / 1000))); }
    assert.ok(e < TOL, `${m.k}/${m.c} 오차 ${e}`);
    assert.ok(m.chars <= 260, `${m.k}/${m.c} 길이 ${m.chars}`);
    assert.equal(m.durMs, Math.ceil(settle(sp, 0.001) * 1000));
  }
});
t('점 수는 알아서: 매끄러운 곡선은 적게, 많이 흔들리는 곡선은 많이', () => {
  const lin = toLinear(p => p);                         // 직선 → 점 2개
  assert.equal(parseLinear(lin.str).length, 2);
  const calm = measure(620, 40), wob = measure(520, 16);
  assert.ok(wob.points > calm.points, `${wob.points} > ${calm.points}`);
  const tight = toLinear(p => spring(620, 36).x(p * 0.404), { tol: 0.001 });
  assert.ok(tight.err < 0.001 && parseLinear(tight.str).length > calm.points, '허용 오차를 줄이면 점이 늘어요');
});

console.log('3. 판정 · 제안');
const data = build();
t('⚠ = 넘침 > 2%, 제안은 같은 강성 · ζ ≥ 0.8 · 넘침 ≤ 2%', () => {
  for (const r of data.springs) {
    assert.equal(r.flagged, r.ref.overshootPct > LIMIT_PCT, r.name);
    if (r.flagged) {
      assert.equal(r.alt.k, r.ref.k); assert.ok(r.alt.c > r.ref.c); assert.ok(r.alt.zeta >= ALT_ZETA - 1e-9);
      assert.ok(r.alt.overshootPct <= LIMIT_PCT, `${r.name} 제안 ${r.alt.overshootPct}`);
      assert.ok(overshootFormula((r.alt.c - 1) / (2 * Math.sqrt(r.alt.k))) > 0, '감쇠를 필요한 만큼만');
    } else assert.equal(r.alt, undefined);
  }
  const pop = data.springs.find(r => r.name === 'pop');
  assert.ok(pop.flagged && pop.ref.overshootPct > 30, 'pop 520/16 ≈ 31%');
});
t('pop-check는 지금 --c-pop보다 넘치지 않아요', () => {
  const cpop = bezierOvershootPct([.34, 1.3, .64, 1]);
  close(cubicBezier(.34, 1.3, .64, 1)(.5), cubicBezier(.34, 1.3, .64, 1)(.5), 0);
  assert.ok(data.popCheck.overshootPct <= cpop + 1e-9, `${data.popCheck.overshootPct} ≤ ${cpop}`);
  assert.ok(overshootFormula((data.popCheck.c - 1) / (2 * Math.sqrt(data.popCheck.k))) > cpop, '가장 작은 감쇠');
});
t('drafts/springs.css = 지금 생성 결과, 이름마다 토큰 + 길이, 줄이기 = 0ms', () => {
  const file = readFileSync(join(ROOT, 'drafts/springs.css'), 'utf8');
  assert.equal(file, css(data), 'node scripts/springs.mjs 를 다시 돌려 주세요');
  for (const r of data.springs) {
    assert.match(file, new RegExp(`--sp-${r.name}:linear\\(`)); assert.match(file, new RegExp(`--sp-${r.name}-dur:\\d+ms;`));
    assert.match(file, new RegExp(`--sp-${r.name}-ref:`)); assert.match(file, new RegExp(`--sp-${r.name}-dur:0ms`));
  }
  const red = file.match(/html\[data-motion="reduced"\]\{([^}]*)\}/)[1];
  const durs = [...file.matchAll(/(--sp-[\w-]+-dur):(\d+)ms;/g)].map(m => m[1]);
  for (const d of durs) assert.ok(red.includes(`${d}:0ms`), `줄이기에 ${d}`);
  const html = readFileSync(join(ROOT, 'drafts/springs.html'), 'utf8');
  assert.ok(html.includes(file.trim()), 'drafts/springs.html의 토큰 칸이 지금 CSS와 같아요');
});

console.log(`   ${n}개 통과 (수학 · 파일)`);
if (process.argv.includes('--no-browser')) process.exit(0);

console.log('4. Chromium');
const require = createRequire(import.meta.url);
let pw;
for (const p of ['playwright', '/opt/npm-tools/node_modules/playwright']) { try { pw = require(p); break; } catch (e) { } }
assert.ok(pw, 'playwright를 찾지 못했어요 (--no-browser로 건너뛸 수 있어요)');
const browser = await pw.chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.setContent(`<!doctype html><style>${readFileSync(join(ROOT, 'drafts/springs.css'), 'utf8')}</style><div id=a style="width:10px;height:10px"></div><div id=b></div>`);
  const all = [...data.springs.flatMap(r => r.alt ? [[r.name + '-ref', r.ref], [r.name, r.alt]] : [[r.name, r.ref]]), ['pop-check', data.popCheck]];
  let worst = 0, cells = 0;
  for (const [name, m] of all) {
    const samples = Array.from({ length: 241 }, (_, i) => i / 240 * m.durMs);
    const r = await page.evaluate(({ s, dur, samples }) => {
      const ok = CSS.supports('transition-timing-function', s) && CSS.supports('animation-timing-function', s);
      const el = document.getElementById('a');
      const an = el.animate([{ translate: '0px' }, { translate: '1000px' }], { duration: dur, easing: s, fill: 'both' });
      an.pause();
      const out = samples.map(ms => { an.currentTime = ms; return [an.effect.getComputedTiming().progress, parseFloat(getComputedStyle(el).translate) / 1000]; });
      an.cancel();
      return { ok, out };
    }, { s: m.linear, dur: m.durMs, samples });
    assert.ok(r.ok, `${name}: CSS.supports`);
    const sp = spring(m.k, m.c);
    r.out.forEach(([prog, tr], i) => {
      const want = sp.x(samples[i] / 1000) , endSnap = i === samples.length - 1 ? 0.001 : 0;
      const e1 = Math.abs(prog - want), e2 = Math.abs(tr - want);
      worst = Math.max(worst, e1, e2); cells++;
      assert.ok(e1 < TOL + endSnap, `${name} progress @${samples[i].toFixed(1)}ms ${prog} vs ${want}`);
      assert.ok(e2 < TOL + endSnap + 2e-4, `${name} translate @${samples[i].toFixed(1)}ms ${tr} vs ${want}`);
    });
  }
  console.log(`  ✓ linear() ${all.length}개를 Chromium이 받아요 · ${cells}칸에서 참 곡선과 최대 오차 ${(worst * 100).toFixed(3)}% (< ${TOL * 100}%)`); n++;
  // 토큰이 var()로 풀려 transition에 들어가는지, 줄이기면 0s인지
  const tok = await page.evaluate(() => {
    const b = document.getElementById('b'); b.style.transition = 'left var(--sp-lead-dur) var(--sp-lead)';
    const s1 = getComputedStyle(b); const on = [s1.transitionDuration, s1.transitionTimingFunction];
    document.documentElement.dataset.motion = 'reduced'; const s2 = getComputedStyle(b); return { on, red: s2.transitionDuration };
  });
  assert.match(tok.on[1], /^linear\(/); assert.equal(tok.on[0], (data.springs.find(r => r.name === 'lead').alt.durMs / 1000) + 's'); assert.equal(tok.red, '0s');
  console.log(`  ✓ var(--sp-lead) → ${tok.on[0]} linear(…), 줄이기 → ${tok.red}`); n++;
  // 시안: 두 보기가 오류 없이 열리고, 프레임 표가 실제로 멈춘 전환을 그려요
  for (const q of ['', '?frames=1']) {
    const p2 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const e2 = []; p2.on('pageerror', e => e2.push(String(e))); p2.on('console', m => { if (m.type() === 'error') e2.push(m.text()); });
    await p2.goto(pathToFileURL(join(ROOT, 'drafts/springs.html')).href + q);
    await p2.waitForFunction(() => window.__ready === true, null, { timeout: 15000 });
    const info = await p2.evaluate(() => ({
      font: document.fonts.check('600 13px "Pretendard Variable"'),
      overflow: document.documentElement.scrollWidth - innerWidth,
      paused: document.getAnimations().filter(a => a.playState === 'paused').length,
      cells: document.querySelectorAll('.cell').length,
      // 세그먼트 프레임: 레퍼런스 줄 180ms 칸의 표시 오른쪽 가장자리가 목표를 넘었는지(넘침), 제안 줄은 거의 안 넘는지
      seg: ['ref', 'sp', 'cur'].map(v => { const st = document.querySelector(`.fr-row .strip[data-v="${v}"]`); if (!st) return null;
        const segs = [...st.querySelectorAll('.seg')]; const endR = parseFloat(getComputedStyle(segs.at(-1).querySelector('.ind')).right);
        return segs.slice(0, -1).map(s => endR - parseFloat(getComputedStyle(s.querySelector('.ind')).right)); }),
    }));
    assert.deepEqual(e2, [], `콘솔 오류 ${q}`);
    assert.ok(info.font, 'Pretendard가 실려요');
    assert.ok(info.overflow <= 0, `가로 넘침 ${info.overflow}`);
    if (q) {
      assert.equal(info.cells, 8 * 3 * 8, '8 데모 × 3 변주 × 8칸');
      assert.ok(info.paused > 100, `멈춘 전환 ${info.paused}`);
      const [ref, sp, cur] = info.seg; const mx = a => Math.max(...a);
      assert.ok(mx(ref) > 2, `레퍼런스 앞 가장자리 넘침 ${mx(ref).toFixed(2)}px`);
      assert.ok(mx(sp) < mx(ref) && mx(sp) <= 2, `제안 넘침 ${mx(sp).toFixed(2)}px`);
      assert.ok(mx(cur) <= 0.01, `지금 곡선은 넘치지 않아요 ${mx(cur)}`);
      console.log(`  ✓ 프레임 표: 칸 ${info.cells}, 멈춘 전환 ${info.paused}, 세그먼트 앞 가장자리 넘침 레퍼런스 ${mx(ref).toFixed(2)}px · 제안 ${mx(sp).toFixed(2)}px · 지금 ${mx(cur).toFixed(2)}px`); n++;
    } else {
      // 한 변주를 누르면 세 변주가 같이 바뀌어요(나란히 비교)
      const cards = p2.locator('.card');
      await cards.nth(0).locator('.seg button', { hasText: '전체' }).first().click();
      await cards.nth(2).locator('[aria-haspopup]').nth(2).click();
      await p2.waitForTimeout(800);
      const s = await p2.evaluate(() => {
        const c = document.querySelectorAll('.card');
        return { seg: [...c[0].querySelectorAll('.seg')].map(g => [...g.querySelectorAll('button')].findIndex(b => b.getAttribute('aria-pressed') === 'true')),
          open: [...c[2].querySelectorAll('.dd,.mo')].map(e => e.classList.contains('open')), box: [...c[2].querySelectorAll('.mo .msh')].map(m => m.offsetWidth + 'x' + m.offsetHeight) };
      });
      assert.deepEqual(s.seg, [2, 2, 2]); assert.deepEqual(s.open, [true, true, true]); assert.deepEqual(s.box, ['148x188', '148x188']);
      await p2.keyboard.press('Escape'); await p2.waitForTimeout(800);
      assert.deepEqual(await p2.evaluate(() => [...document.querySelectorAll('.card')[2].querySelectorAll('.dd,.mo')].map(e => e.classList.contains('open'))), [false, false, false], 'Esc로 닫혀요');
      console.log('  ✓ 시안 보기: 오류 0 · 넘침 0 · Pretendard · 세 변주가 같이 움직여요 · Esc'); n++;
    }
    await p2.close();
  }
  assert.deepEqual(errs, []);
} finally { await browser.close(); }
console.log(`모두 ${n}개 통과`);
