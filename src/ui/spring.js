/* KH.spring — the one shared spring engine (docs/standards/design.md §6-3 "JS", AGENTS §3-7 "KH.spring").
 *
 * For what CSS transitions can't do: retargeting mid-flight keeps the current velocity, drags hand over their release velocity,
 * a segmented / tab indicator rides two springs (leading edge `lead`, trailing edge `trail`), a switch knob stretches. Plain
 * transitions keep using `transition: … var(--sp-<name>-dur) var(--sp-<name>)` (scripts/design_tokens.mjs).
 *
 *   KH.spring.animate({from, to, name | k, c, velocity?, onUpdate(v, vel), onRest(v)?, fancy?, scale?, restDelta?})
 *       → handle {retarget(to, {velocity?, name? | k?, c?}), stop(), set(v), value(), velocity(), target(), running()}
 *     mass 1, closed-form damped spring (under / critical / over). velocity is in units per second (px/s for px).
 *     named springs come from CSS `--sp-<name>-kc` ("k c") on :root, else the FALLBACK table (= scripts/design_tokens.mjs APPROVED).
 *     One requestAnimationFrame loop for every spring, off when nothing moves; dt clamped to ≤ 0.1 s; rest when
 *     |x − to| < 1e-3·scale and |vel| < 1e-3·scale·ω0 (scale = |to − from|, or |vel|/ω0 if larger) → onUpdate(to, 0), onRest(to).
 *     KH.motion() 'reduced' or a hidden tab → the end value at once (onUpdate now, onRest a microtask later); `fancy: true` also
 *     ends at once unless KH.motion() is 'fancy'. kh:motion / visibilitychange finish whatever is moving then.
 *   KH.spring.edges(el, {left, width}, {lead, trail, write, willChange, instant, onRest}) → indicator controller (one per element;
 *     the first call places it, later calls animate) {to(box, {instant}), set(box), value(), moving(), stop(), destroy()}
 *   KH.spring.knob(el, x, {width, stretch, front, back, write, willChange, instant, onRest}) → switch knob controller (same;
 *     handle-like: to(x), set(x), retarget(x, {velocity, name}), value(), velocity(), target(), running(), box(), stop(), destroy())
 *   KH.spring.release(handle, velocityPxPerMs, {points?, to?, name?, maxOvershoot?}) → {to, thrown, velocity, carried}
 *     (settle spring with the release speed, §8 throw > 0.11 px/ms; maxOvershoot px caps the carried speed for hard ends)
 *   KH.spring.params(name) → {k, c, zeta, w0, source} · solve(k, c, from, to, v0) → {x(t), v(t), at(t), regime, zeta, w0}
 *   KH.spring.names() · FALLBACK · THROW · stats() → {active, scheduled}
 *
 * will-change (§6-5): the helpers add `will-change: transform` only while they move and only when they write a transform to an
 * element with no text; it goes back to its earlier inline value on rest. animate() itself never touches the DOM.
 */
(function () {
  'use strict';
  const KH = window.KH;
  if (!KH || KH.spring) return;

  // = scripts/design_tokens.mjs APPROVED (qa/ui/test_spring.mjs checks the two tables match)
  const FALLBACK = Object.freeze(Object.fromEntries(Object.entries({
    lead: [620, 40], trail: [190, 23], follow: [900, 50], settle: [280, 27], fade: [420, 37], open: [360, 31], close: [900, 57],
    hl: [620, 40], 'island-w': [380, 32], 'island-h': [300, 28], roll: [320, 36], 'roll-w': [380, 39], value: [420, 41], pop: [520, 34],
  }).map(([n, kc]) => [n, Object.freeze(kc)])));
  const DT_MAX = 0.1;        // s — a long frame (tab stall, GC) advances at most this much
  const REST = 1e-3;         // rest band, relative to the move's scale
  const THROW = 0.11;        // px/ms — design.md §8: a release faster than this is a throw
  const FRAME = 1 / 60;      // s — the first step of a move from rest

  const report = e => { try { if (typeof window.reportError === 'function') window.reportError(e); else console.error(e); } catch (_) { /* never let reporting break the loop */ } };
  const call = (fn, a, b) => { if (typeof fn === 'function') { try { fn(a, b); } catch (e) { report(e); } } };
  const now = () => (window.performance && performance.now ? performance.now() : Date.now());
  const fin = (v, what) => { const n = +v; if (!Number.isFinite(n)) throw new TypeError(`KH.spring: ${what} must be a finite number`); return n; };
  const motion = () => { try { return typeof KH.motion === 'function' ? KH.motion() : document.documentElement.dataset.motion; } catch (e) { return 'standard'; } };
  const hidden = () => document.hidden === true || document.visibilityState === 'hidden';

  /* ───────── closed form: x'' + c·x' + k·(x − to) = 0, x(0) = from, x'(0) = v0 (mass 1, seconds) ───────── */
  function solve(k, c, from, to, v0) {
    k = +k; c = +c; from = +from; to = +to; v0 = +v0 || 0;
    if (!(k > 0) || !(c >= 0) || !Number.isFinite(k) || !Number.isFinite(c)) throw new RangeError('KH.spring: k > 0, c ≥ 0');
    const w0 = Math.sqrt(k), zeta = c / (2 * w0), y0 = from - to;
    let at, regime;
    if (zeta < 1 - 1e-9) {
      // y = e^{−a t}(A cos ωd t + B sin ωd t)
      const a = zeta * w0, wd = w0 * Math.sqrt(1 - zeta * zeta), A = y0, B = (v0 + a * y0) / wd;
      regime = 'under';
      at = t => { const e = Math.exp(-a * t), co = Math.cos(wd * t), si = Math.sin(wd * t);
        return [to + e * (A * co + B * si), e * ((B * wd - a * A) * co - (A * wd + a * B) * si)]; };
    } else if (zeta <= 1 + 1e-9) {
      // y = (A + B t) e^{−ω0 t}
      const A = y0, B = v0 + w0 * y0;
      regime = 'critical';
      at = t => { const e = Math.exp(-w0 * t); return [to + (A + B * t) * e, (B - w0 * (A + B * t)) * e]; };
    } else {
      // y = C1 e^{r1 t} + C2 e^{r2 t}
      const s = Math.sqrt(zeta * zeta - 1), r1 = -w0 * (zeta - s), r2 = -w0 * (zeta + s);
      const C1 = (v0 - r2 * y0) / (r1 - r2), C2 = y0 - C1;
      regime = 'over';
      at = t => { const e1 = Math.exp(r1 * t), e2 = Math.exp(r2 * t); return [to + C1 * e1 + C2 * e2, C1 * r1 * e1 + C2 * r2 * e2]; };
    }
    return { k, c, w0, zeta, regime, at, x: t => at(t)[0], v: t => at(t)[1] };
  }

  /* ───────── named springs: CSS --sp-<name>-kc on :root, else FALLBACK; cleared on kh:theme ───────── */
  const KC = new Map();
  function params(name) {
    name = String(name);
    let p = KC.get(name);
    if (p) return p;
    let k, c, source = null;
    try {
      const raw = getComputedStyle(document.documentElement).getPropertyValue('--sp-' + name + '-kc');
      const m = /^\s*["']?\s*([\d.]+)\s+([\d.]+)\s*["']?\s*$/.exec(raw || '');
      if (m && +m[1] > 0 && +m[2] >= 0) { k = +m[1]; c = +m[2]; source = 'css'; }
    } catch (e) { /* no styles (detached document): the table */ }
    if (!source && Object.prototype.hasOwnProperty.call(FALLBACK, name)) { [k, c] = FALLBACK[name]; source = 'fallback'; }
    if (!source) throw new RangeError(`KH.spring: no spring named "${name}"`);
    p = Object.freeze({ name, k, c, w0: Math.sqrt(k), zeta: c / (2 * Math.sqrt(k)), source });
    KC.set(name, p);
    return p;
  }
  function pick(o, s) {
    if (o.k != null || o.c != null) {
      const k = fin(o.k, 'k'), c = fin(o.c, 'c');
      if (!(k > 0) || !(c >= 0)) throw new RangeError('KH.spring: k > 0, c ≥ 0');
      return { name: null, k, c };
    }
    if (o.name != null) { const p = params(o.name); return { name: p.name, k: p.k, c: p.c }; }
    if (s) return { name: s.name, k: s.k, c: s.c };
    throw new TypeError('KH.spring: give a spring name or {k, c}');
  }

  /* ───────── the shared loop ───────── */
  const active = new Set();     // springs that move
  let rafId = 0, inTick = false;
  const dirty = new Set();      // helper draws queued during a tick: each runs once per frame, after every spring stepped
  function schedule() {
    if (rafId || !active.size) return;
    rafId = window.requestAnimationFrame(tick);
  }
  function unschedule() {
    if (rafId && !active.size) { try { window.cancelAnimationFrame(rafId); } catch (e) { } rafId = 0; }
  }
  function tick(ts) {
    rafId = 0;
    if (!Number.isFinite(ts)) ts = now();
    inTick = true;
    try { for (const s of [...active]) if (active.has(s)) step(s, ts); }
    finally { inTick = false; }
    flush();
    schedule();
  }
  function flush() {
    if (!dirty.size) return;
    const list = [...dirty]; dirty.clear();
    for (const fn of list) { try { fn(); } catch (e) { report(e); } }
  }
  function step(s, ts) {
    let dt = (ts - s.last) / 1000;
    // the first frame of a move from rest: an input handler's now() can be later than this frame's timestamp, so advance at
    // least one frame (what shows at the next vsync) instead of drawing the start value again
    if (s.first) { s.first = false; dt = Math.max(dt, FRAME); }
    dt = Math.min(DT_MAX, Math.max(0, dt));
    s.last = ts;
    s.t += dt;
    const xv = s.sol.at(s.t);
    s.x = xv[0]; s.v = xv[1];
    if (Math.abs(s.x - s.to) < s.restDelta && Math.abs(s.v) < s.restSpeed) { rest(s, false); return; }
    call(s.onUpdate, s.x, s.v);
  }
  // at the end: snap to the target, the last onUpdate, then onRest (a microtask later when it happens inside animate / retarget)
  function rest(s, defer) {
    active.delete(s); s.running = false;
    s.x = s.to; s.v = 0;
    const g = s.gen;
    call(s.onUpdate, s.to, 0);
    if (!defer) { if (s.gen === g && !s.running) call(s.onRest, s.to); }
    else queueMicrotask(() => { if (s.gen === g && !s.running) call(s.onRest, s.to); });
    unschedule();
  }
  const instantFor = s => hidden() || motion() === 'reduced' || (s.fancy && motion() !== 'fancy');

  function start(s, to, from, v) {
    s.gen++;
    s.to = to; s.x = from; s.v = v; s.t = 0;
    s.sol = solve(s.k, s.c, from, to, v);
    const w0 = Math.sqrt(s.k), scale = s.scaleOpt > 0 ? s.scaleOpt : Math.max(Math.abs(to - from), Math.abs(v) / w0);
    s.restDelta = s.restOpt > 0 ? s.restOpt : REST * scale;
    s.restSpeed = s.restDelta * w0;
    if (!(scale > 0) || instantFor(s)) { rest(s, true); return; }
    if (!s.running) { s.running = true; s.last = now(); s.first = true; active.add(s); }   // a running spring keeps its clock: no lost or doubled time
    schedule();
  }

  function animate(o) {
    o = o || {};
    const sp = pick(o, null);
    const s = {
      name: sp.name, k: sp.k, c: sp.c, onUpdate: o.onUpdate, onRest: o.onRest, fancy: !!o.fancy,
      scaleOpt: +o.scale || 0, restOpt: +o.restDelta || 0, running: false, first: false, gen: 0, x: 0, v: 0, to: 0, t: 0, last: 0, sol: null,
    };
    const h = {
      retarget(to, opt) {
        opt = opt || {};
        if (opt.name != null || opt.k != null || opt.c != null) { const p = pick(opt, s); s.name = p.name; s.k = p.k; s.c = p.c; }
        const v = opt.velocity != null ? fin(opt.velocity, 'velocity') : s.v;
        start(s, fin(to, 'to'), s.x, v);
        return h;
      },
      stop() { active.delete(s); s.running = false; s.v = 0; s.gen++; unschedule(); return h; },
      set(value) { active.delete(s); s.running = false; s.gen++; s.x = s.to = fin(value, 'value'); s.v = 0; unschedule(); call(s.onUpdate, s.x, 0); return h; },
      value: () => s.x,
      velocity: () => s.v,
      target: () => s.to,
      running: () => s.running,
      spring: () => ({ name: s.name, k: s.k, c: s.c }),
    };
    start(s, fin(o.to, 'to'), fin(o.from, 'from'), o.velocity != null ? fin(o.velocity, 'velocity') : 0);
    return h;
  }

  function finishWhere(test) { for (const s of [...active]) if (test(s)) rest(s, false); }
  document.addEventListener('kh:motion', e => {
    const m = (e && e.detail && e.detail.motion) || motion();
    if (m === 'reduced') finishWhere(() => true);
    else if (m !== 'fancy') finishWhere(s => s.fancy);
  });
  document.addEventListener('visibilitychange', () => { if (hidden()) finishWhere(() => true); });
  document.addEventListener('kh:theme', () => KC.clear());

  /* ───────── helpers: draw once per frame, will-change only while moving ───────── */
  const px = v => (Math.round(v * 100) / 100) + 'px';
  function painter(el, o, draw) {
    // o.write 'transform' (translateX + width, default) | 'left' (left + width)
    const write = o.write === 'left' ? 'left' : 'transform';
    const wcAllowed = write === 'transform' && o.willChange !== false && !(o.willChange !== true && /\S/.test(el.textContent || ''));
    let wcOn = false, wcPrev = '';
    const put = (left, width) => {
      if (write === 'left') el.style.left = px(left); else el.style.transform = `translateX(${px(left)})`;
      el.style.width = px(Math.max(0, width));
    };
    const paint = () => draw(put);
    return {
      update() { if (inTick) dirty.add(paint); else { dirty.delete(paint); paint(); } },
      moving(on) {
        if (!wcAllowed || on === wcOn) return;
        if (on) { wcPrev = el.style.willChange || ''; el.style.willChange = 'transform'; } else el.style.willChange = wcPrev;
        wcOn = on;
      },
    };
  }

  const EDGES = new WeakMap();
  /* edges(el, {left, width}, {lead:'lead', trail:'trail', write, willChange, instant, onRest}) — a segmented / tab / underline
     indicator: its leading edge (the side it moves toward) rides `lead`, the other edge `trail`, so it stretches and catches up
     (design.md §6-2, §7). The first call places it; later calls (same element) animate. Reads no layout: pass numbers you have. */
  function edges(el, box, o) {
    let ctl = EDGES.get(el);
    if (ctl) { if (o) ctl.configure(o); return box ? ctl.to(box, o) : ctl; }
    ctl = makeEdges(el, o || {});
    EDGES.set(el, ctl);
    if (box) ctl.set(box);
    return ctl;
  }
  function makeEdges(el, o) {
    const cfg = { lead: o.lead || 'lead', trail: o.trail || 'trail', onRest: o.onRest };
    let L = null, R = null, moving = false;   // moving: a to() whose onRest is still owed (once, when both edges rest)
    const pt = painter(el, o, put => put(L.value(), R.value() - L.value()));
    const done = () => { if (!L || !R || !moving || L.running() || R.running()) return; moving = false; pt.moving(false); call(cfg.onRest, ctl.value()); };
    const mk = v => animate({ from: v, to: v, name: cfg.lead, onUpdate: () => { if (L && R) pt.update(); }, onRest: done });
    const ctl = {
      configure(n) { if (n.lead) cfg.lead = n.lead; if (n.trail) cfg.trail = n.trail; if ('onRest' in n) cfg.onRest = n.onRest; return ctl; },
      to(b, opt) {
        const l = fin(b.left, 'left'), r = l + fin(b.width, 'width');
        if (!L) { L = mk(l); R = mk(r); }
        if (opt && opt.instant) return ctl.set(b);
        const dir = (l + r) - (L.value() + R.value());   // moving right → the right edge leads
        const eps = 1e-6 * (1 + Math.abs(r - l));
        moving = true;
        L.retarget(l, { name: dir < -eps ? cfg.lead : dir > eps ? cfg.trail : cfg.lead });
        R.retarget(r, { name: dir > eps ? cfg.lead : dir < -eps ? cfg.trail : cfg.lead });
        if (L.running() || R.running()) pt.moving(true);
        return ctl;
      },
      set(b) {
        const l = fin(b.left, 'left'), r = l + fin(b.width, 'width');
        if (!L) { L = mk(l); R = mk(r); }
        moving = false; L.set(l); R.set(r); pt.moving(false);
        return ctl;
      },
      value: () => (L ? { left: L.value(), width: R.value() - L.value() } : null),
      moving: () => !!(L && (L.running() || R.running())),
      stop() { moving = false; if (L) { L.stop(); R.stop(); } pt.moving(false); return ctl; },
      destroy() { ctl.stop(); EDGES.delete(el); },
    };
    return ctl;
  }

  const KNOBS = new WeakMap();
  /* knob(el, x, {width, stretch:3, front:'follow', back:'settle', write, willChange, instant, onRest}) — a switch knob of width
     `width` going to translateX(x): the front edge rides `front`, the back edge `back`, the gap soft-capped at `stretch` px
     (design.md §7, §10-8: ~3px). Handle-like (value / velocity / target / retarget / set) so KH.spring.release() takes it. */
  function knob(el, x, o) {
    let ctl = KNOBS.get(el);
    if (ctl) { if (o) ctl.configure(o); return x != null ? ctl.to(x, o) : ctl; }
    ctl = makeKnob(el, o || {});
    KNOBS.set(el, ctl);
    if (x != null) ctl.set(x);
    return ctl;
  }
  function makeKnob(el, o) {
    const cfg = { width: fin(o.width, 'width'), stretch: o.stretch != null ? Math.max(0, fin(o.stretch, 'stretch')) : 3,
      front: o.front || 'follow', back: o.back || 'settle', onRest: o.onRest };
    let F = null, B = null, moving = false;
    const pt = painter(el, o, put => {
      const f = F.value(), d = f - B.value(), S = cfg.stretch;
      const s = S > 0 ? S * Math.tanh(Math.abs(d) / S) : 0;     // the back edge lags by ≤ `stretch` px
      put(d > 0 ? f - s : f, cfg.width + s);
    });
    const done = () => { if (!F || !B || !moving || F.running() || B.running()) return; moving = false; pt.moving(false); call(cfg.onRest, F.value()); };
    const upd = () => { if (F && B) pt.update(); };
    const ensure = v => { if (!F) { F = animate({ from: v, to: v, name: cfg.front, onUpdate: upd, onRest: done }); B = animate({ from: v, to: v, name: cfg.back, onUpdate: upd, onRest: done }); } };
    const ctl = {
      configure(n) { if (n.width != null) cfg.width = fin(n.width, 'width'); if (n.stretch != null) cfg.stretch = Math.max(0, fin(n.stretch, 'stretch'));
        if (n.front) cfg.front = n.front; if (n.back) cfg.back = n.back; if ('onRest' in n) cfg.onRest = n.onRest; return ctl; },
      to(x, opt) { x = fin(x, 'x'); ensure(x); if (opt && opt.instant) return ctl.set(x); return ctl.retarget(x); },
      // release(): name 'settle' + the finger's velocity on both edges
      retarget(x, opt) {
        opt = opt || {}; x = fin(x, 'x'); ensure(x);
        const v = opt.velocity;
        moving = true;
        F.retarget(x, { velocity: v, name: opt.name || cfg.front, k: opt.k, c: opt.c });
        B.retarget(x, { velocity: v, name: opt.name ? opt.name : cfg.back, k: opt.k, c: opt.c });
        if (F.running() || B.running()) pt.moving(true);
        return ctl;
      },
      set(x) { x = fin(x, 'x'); ensure(x); moving = false; F.set(x); B.set(x); pt.moving(false); return ctl; },
      value: () => (F ? F.value() : null),
      velocity: () => (F ? F.velocity() : 0),
      target: () => (F ? F.target() : null),
      running: () => !!(F && (F.running() || B.running())),
      box() { if (!F) return null; const f = F.value(), d = f - B.value(), S = cfg.stretch, s = S > 0 ? S * Math.tanh(Math.abs(d) / S) : 0; return { left: d > 0 ? f - s : f, width: cfg.width + s }; },
      stop() { moving = false; if (F) { F.stop(); B.stop(); } pt.moving(false); return ctl; },
      destroy() { ctl.stop(); KNOBS.delete(el); },
    };
    return ctl;
  }

  /* release(handle, velocityPxPerMs, {points?, to?, name:'settle', maxOvershoot?}) — a drag let go: the handle keeps the finger's
     velocity (px/ms → px/s) on the settle spring (design.md §6-1). |v| > 0.11 px/ms is a throw (§8): with `points` it goes to the
     next point in the throw's direction, otherwise to the nearest point; with neither, to `to` or the handle's target. A hard
     throw close to the target overshoots by physics; `maxOvershoot` (px, e.g. 1 for a switch knob in its track) keeps only as
     much of the speed as stays within it. */
  function release(h, vPxPerMs, o) {
    o = o || {};
    if (!h || typeof h.retarget !== 'function' || typeof h.value !== 'function') throw new TypeError('KH.spring.release: a spring handle');
    const v = Number.isFinite(+vPxPerMs) ? +vPxPerMs : 0, thrown = Math.abs(v) > THROW, x = h.value();
    let to = o.to != null ? fin(o.to, 'to') : null;
    if (to == null && Array.isArray(o.points)) {
      const pts = o.points.map(Number).filter(Number.isFinite);
      if (pts.length) {
        const nearest = pts.reduce((a, p) => (Math.abs(p - x) < Math.abs(a - x) ? p : a));
        const ahead = thrown ? pts.filter(p => (v > 0 ? p > x : p < x)).sort((a, b) => (v > 0 ? a - b : b - a)) : [];
        to = ahead.length ? ahead[0] : nearest;
      }
    }
    if (to == null) to = h.target();
    const name = o.name || 'settle';
    let vs = v * 1000;
    if (o.maxOvershoot != null && vs !== 0) { const p = params(name); vs = capSpeed(p.k, p.c, x, to, vs, Math.max(0, fin(o.maxOvershoot, 'maxOvershoot'))); }
    h.retarget(to, { velocity: vs, name });
    return { to, thrown, velocity: v, carried: vs / 1000 };
  }
  // the largest share of the release speed whose peak past `to` stays ≤ maxOS (a switch track has hard ends)
  function capSpeed(k, c, x, to, vs, maxOS) {
    const dir = Math.sign(to - x) || Math.sign(vs), T = 8 / Math.sqrt(k);
    const peak = f => { const sol = solve(k, c, x, to, vs * f); let m = 0; for (let i = 1; i <= 400; i++) m = Math.max(m, (sol.x(T * i / 400) - to) * dir); return m; };
    if (peak(1) <= maxOS) return vs;
    let lo = 0, hi = 1;
    for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (peak(mid) <= maxOS) lo = mid; else hi = mid; }
    return vs * lo;
  }

  KH.spring = Object.freeze({
    animate, edges, knob, release, params, solve,
    names: () => Object.keys(FALLBACK),
    stats: () => ({ active: active.size, scheduled: rafId !== 0 }),
    FALLBACK, THROW, DT_MAX, REST,
  });
})();
