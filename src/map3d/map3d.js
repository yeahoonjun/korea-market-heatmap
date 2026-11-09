/* 3D 지도 (WebGL) — AGENTS.md §3-5 "3D 지도 모듈", docs/motion-brief.md (f).
   window.KH3D = { show() → Promise<boolean>, hide() → Promise (resolves once #map may be shown again), isOn(), stats() }
   (+ KH3D.qa: read-only helpers for qa/map3d, not part of the template contract)
   The template keeps #map laid out (invisible) and shows <div id="map3d"> in the same rect, then calls show(); hide() frees the GPU.
   Data: KH.layout() (tiles x·y·w·h·color·code·label·sub·px, sector boxes), KH.stock(code), KH.palette(), KH.motion().
   three.js r149 — the last UMD build/three.min.js without the r150+ deprecation console.warn — loads from jsDelivr with SRI on the
   first show(). No WebGL / blocked script → a Korean message in #map3d + document event 'kh:3d-unavailable' {reason, message}.

   Encoding: each tile is a box on its 2D footprint. Height = H·min(1, |value| / colour range)^0.75 with H = 0.18·min(map w, h)
   (terrain, not a forest of towers); top face = the 2D tile colour, unlit. Falls rise too and colour tells the direction: boxes
   sunk below the floor would hide behind the floor and their rising neighbours at a tilted view, so they could not be compared,
   hovered or labelled. */
(() => {
'use strict';
if (window.KH3D) return;

const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.149.0/build/three.min.js';
const THREE_SRI = 'sha384-RRHfJ6w1mTlKUBMYT/hvnRiOzEB/vyRV3DrQOseb6oYfvaZSfdd0byS4bHps0k2R';
const LOAD_TIMEOUT = 20000;

const hoverMQ = matchMedia('(hover: hover) and (pointer: fine)');
const coarseMQ = matchMedia('(pointer: coarse)');
const rmMQ = matchMedia('(prefers-reduced-motion: reduce)');

const DEG = Math.PI / 180;
const FOV = 26;
const HOME_POLAR = 32 * DEG, HOME_AZ = -18 * DEG;   // start pose: 32° from the zenith, azimuth −18°
const POLAR_MIN = 1e-4, POLAR_MAX = 60 * DEG, AZ_LIM = 45 * DEG;
const ZOOM_IN = 3, ZOOM_OUT = 0.6;                   // zoom range: 0.6×…3× of the fitted view
const TAU_CAM = 70, TAU_ZOOM = 90, TAU_INERTIA = 250, TAU_TIP = 70;
const STRIDE = 8;                                    // per instance: cx, cz, w, d, h, r, g, b
const MAX_LABELS = 40, MAX_FLASH = 60, PLATE_RGB = [13 / 255, 14 / 255, 17 / 255];   // #0d0e11

let T = null;               // THREE once loaded
let threeP = null;

const S = {
  on: false, gen: 0, root: null, built: false, leaving: null, visible: true,
  renderer: null, scene: null, camera: null, cam2: null, mesh: null, plates: null, outline: null,
  boxGeo: null, plateGeo: null, edgeGeo: null, mat: null, plateMat: null, lineMat: null, cap: 0, pcap: 0, fx: null,
  canvas: null, labLayer: null, hud: null, ctl: null, hint: null, msg: null, tip: null, kb: null,
  labEls: [], secEls: [], reserved: [],
  n: 0, keys: [], tiles: [], sectors: [], W: 0, H: 0, maxH: 100, R: null, metricPct: true,
  cur: new Float32Array(0), from: new Float32Array(0), to: new Float32Array(0), delay: new Float32Array(0),
  order: [], keyIx: new Map(), tween: null, hover: -1, hoverKey: null, tipFor: null, lastSig: '',
  lastPx: new Map(), dataTick: false, replay: null, flashes: new Map(), fxDirty: false,
  cam: null, goal: null, fly: null, inertia: null, fitDist: 1000, homePose: null, userMoved: false,
  vw: 0, vh: 0, pm: null, tier: 'high', dpr: 1,
  raf: 0, rebuildQ: 0, ro: null, io: null, lastNow: 0, frames: 0, ft: [], ftL: [], ftR: [],
  ptrs: new Map(), drag: null, tapT: 0, tapXY: null, tapTimer: 0, hoverQ: 0, hoverXY: null, hinted: false,
  tipPos: null, tipGoal: null, tipRaf: 0, tipHide: 0,
};

/* ───────────────── helpers ───────────────── */
const KH = () => window.KH || null;
function motion() {
  const k = KH();
  const m = k && typeof k.motion === 'function' ? k.motion() : null;
  return m || (rmMQ.matches ? 'reduced' : 'standard');
}
const fancy = () => { const m = motion(); return m === 'fancy' || m === 'full'; };
const reduced = () => motion() === 'reduced';
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
function parseColor(s) {
  s = String(s || '').trim();
  let m = /^#([0-9a-f]{3})$/i.exec(s);
  if (m) return [...m[1]].map(c => parseInt(c + c, 16));
  m = /^#([0-9a-f]{6})$/i.exec(s);
  if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
  m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(s);
  if (m) return [+m[1], +m[2], +m[3]].map(v => Math.round(clamp(v, 0, 255)));
  return [38, 40, 46];
}
// a value text as the 2D map shows it ("+3.2%", "−1.20%") → number; amounts ("+857억") and "—" → null
function parsePct(sub) {
  const s = String(sub || '').trim();
  if (!s.endsWith('%')) return null;
  const v = parseFloat(s.replace(/[−–]/g, '-').replace(/[+%,\s]/g, ''));
  return isFinite(v) ? v : null;
}
const signCls = sub => { const s = String(sub || '').trim(); return s[0] === '+' ? 'up' : (s[0] === '−' || s[0] === '-') ? 'dn' : 'flat'; };
// width of a label in em (the template's textUnits idea)
function units(str) {
  let u = 0;
  for (const ch of String(str)) {
    const c = ch.codePointAt(0);
    if (c >= 0xAC00 && c <= 0xD7A3 || c >= 0x3130 && c <= 0x318F || c >= 0x4E00 && c <= 0x9FFF) u += 1.0;
    else if (ch === ' ') u += 0.3;
    else if (ch === '&' || ch === 'W' || ch === 'M') u += 0.8;
    else if (ch >= 'A' && ch <= 'Z') u += 0.66;
    else if (ch >= '0' && ch <= '9') u += 0.6;
    else if (ch === '%' || ch === '−' || ch === '+') u += 0.78;
    else u += 0.55;
  }
  return Math.max(u, 1);
}
function hash01(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 1000) / 1000; }
// CSS cubic-bezier as a function of progress
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = t => ((ax * t + bx) * t + cx) * t, sy = t => ((ay * t + by) * t + cy) * t;
  return x => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let lo = 0, hi = 1, t = x;
    for (let i = 0; i < 24; i++) { const v = sx(t); if (Math.abs(v - x) < 1e-5) break; if (v < x) lo = t; else hi = t; t = (lo + hi) / 2; }
    return sy(t);
  };
}
// motion tokens (docs/motion-brief.md 2-0) from :root, with the brief's values as fallbacks
let TK = null;
function tokens() {
  if (TK) return TK;
  const cs = getComputedStyle(document.documentElement);
  const ms = (name, d) => { const m = /([\d.]+)\s*(ms|s)?/.exec(cs.getPropertyValue(name) || ''); return m ? +m[1] * (m[2] === 's' ? 1000 : 1) : d; };
  const ease = (name, d) => { const m = /cubic-bezier\(([^)]+)\)/.exec(cs.getPropertyValue(name) || ''); const v = m ? m[1].split(',').map(Number) : d; return bezier(...(v.length === 4 && v.every(isFinite) ? v : d)); };
  TK = {
    m3: ms('--m-3', 480), fly: ms('--m-fly', 700), flash: ms('--m-flash', 700),
    out: ease('--m-out', [0.2, 0.7, 0.2, 1]), flyEase: ease('--m-fly-ease', [0.83, 0, 0.17, 1]), inout: ease('--m-inout', [0.6, 0, 0.2, 1]),
  };
  return TK;
}

/* ───────────────── colour → position on the palette ─────────────────
   The template exposes no colour range, so a tile's colour is located on the palette ramp (same d3 Lab scale as the template):
   t ∈ [−1, 1] = value / range, clamped. With the value text ("+3.2%") that also gives the range: median of |value| / |t|.
   KH.range() wins when the template provides it. */
let lut = null;
function paletteLut() {
  const k = KH(), d3 = window.d3;
  const pal = k && typeof k.palette === 'function' ? k.palette() : null;
  if (!pal || !pal.stops || pal.stops.length !== 7 || !d3 || !d3.scaleLinear || !d3.interpolateLab) return null;
  const key = pal.stops.join(',');
  if (lut && lut.key === key) return lut;
  const sc = d3.scaleLinear().domain([-1, -2 / 3, -1 / 3, 0, 1 / 3, 2 / 3, 1]).range(pal.stops).interpolate(d3.interpolateLab).clamp(true);
  const N = 600, rgb = new Int16Array((N + 1) * 3);
  for (let i = 0; i <= N; i++) { const c = parseColor(sc(-1 + 2 * i / N)); rgb[i * 3] = c[0]; rgb[i * 3 + 1] = c[1]; rgb[i * 3 + 2] = c[2]; }
  lut = { key, N, rgb, memo: new Map() };
  return lut;
}
function colourT(L, col, c) {
  if (!L) return null;
  const hit = L.memo.get(col);
  if (hit !== undefined) return hit;
  let best = 0, bd = Infinity;
  const a = L.rgb;
  for (let i = 0; i <= L.N; i++) {
    const dr = a[i * 3] - c[0], dg = a[i * 3 + 1] - c[1], db = a[i * 3 + 2] - c[2];
    const d = dr * dr + dg * dg + db * db;
    if (d < bd) { bd = d; best = i; }
  }
  const t = bd > 120 ? null : -1 + 2 * best / L.N;   // off the ramp: no-data grey and the like
  if (L.memo.size > 4000) L.memo.clear();
  L.memo.set(col, t);
  return t;
}
const PRESETS = [0.1, 0.3, 1, 3, 5, 10, 20, 50];
function inferRange(vals, ts) {
  const k = KH();
  if (k && typeof k.range === 'function') {
    try { const r = k.range(); const v = typeof r === 'number' ? r : r && +r.value; if (v > 0) return v; } catch (e) { /* fall back */ }
  }
  const rs = [];
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i], t = ts[i];
    if (v == null || t == null) continue;
    const at = Math.abs(t);
    if (at > 0.12 && at < 0.9 && Math.abs(v) > 0.05) rs.push(Math.abs(v) / at);
  }
  if (rs.length >= 3) {
    rs.sort((a, b) => a - b);
    const med = rs[rs.length >> 1];
    for (const p of PRESETS) if (Math.abs(med - p) / p < 0.12) return p;
    return med;
  }
  let mx = 0;
  for (const v of vals) if (v != null) mx = Math.max(mx, Math.abs(v));
  return Math.max(mx, 1);          // nothing to read the range from: the largest move on screen, at least 1%
}

/* ───────────────── three.js loader, device tier ───────────────── */
function webglOK() {
  try {
    const c = document.createElement('canvas');
    const g = c.getContext('webgl2') || c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!g) return false;
    const x = g.getExtension('WEBGL_lose_context');
    if (x) x.loseContext();
    return true;
  } catch (e) { return false; }
}
function loadThree() {
  if (T) return Promise.resolve(T);
  if (window.THREE && window.THREE.InstancedMesh && window.THREE.REVISION) { T = window.THREE; return Promise.resolve(T); }
  if (threeP) return threeP;
  threeP = new Promise((res, rej) => {
    const s = document.createElement('script');
    let done = false;
    const fin = ok => {
      if (done) return; done = true; clearTimeout(timer);
      if (ok && window.THREE && window.THREE.InstancedMesh) { T = window.THREE; res(T); }
      else { s.remove(); threeP = null; rej(new Error('three.js unavailable')); }
    };
    const timer = setTimeout(() => fin(false), LOAD_TIMEOUT);
    s.src = THREE_URL; s.integrity = THREE_SRI; s.crossOrigin = 'anonymous'; s.async = true; s.dataset.kh = 'three';
    s.onload = () => fin(true); s.onerror = () => fin(false);
    document.head.append(s);
  });
  return threeP;
}
// low-end = narrow screen, or touch with ≤ 4 cores: DPR 1.25, no MSAA
function tier() {
  const narrow = Math.min(innerWidth, (screen && screen.width) || innerWidth) < 720;
  const weak = coarseMQ.matches && (navigator.hardwareConcurrency || 8) <= 4;
  return narrow || weak ? 'low' : 'high';
}

/* ───────────────── shell (dom inside #map3d) ───────────────── */
function setMsg(title, body, withBack) {
  if (!S.msg) return;
  S.msg.replaceChildren();
  if (!title) { S.msg.hidden = true; return; }
  S.msg.hidden = false;
  const box = el('div', 'm3-msg-in');
  box.append(el('b', '', title));
  if (body) box.append(el('span', '', body));
  if (withBack) {
    const b = el('button', 'm3-back', '2D 지도로 보기'); b.type = 'button';
    b.addEventListener('click', () => { const m = document.querySelector('.viewseg button[data-v="map"]'); if (m) m.click(); });
    box.append(b);
  }
  S.msg.append(box);
}
function fail(reason) {
  const text = {
    webgl: ['3D 지도를 열 수 없어요', '이 기기나 브라우저에서 WebGL을 쓸 수 없어요. 2D 지도로 볼 수 있어요.'],
    script: ['3D 도구를 불러오지 못했어요', '네트워크나 콘텐츠 차단 설정을 확인해 주세요. 2D 지도는 그대로 볼 수 있어요.'],
    init: ['3D 화면을 만들지 못했어요', '2D 지도로 볼 수 있어요.'],
  }[reason] || ['3D 지도를 열 수 없어요', ''];
  teardown(true);
  setMsg(text[0], text[1], true);
  S.on = false;
  document.dispatchEvent(new CustomEvent('kh:3d-unavailable', { detail: { reason, message: text[0] + '. ' + text[1] } }));
}

/* ───────────────── scene ───────────────── */
const VERT = `
#ifdef BOX
attribute vec2 aFx;
varying vec2 vFx;
#endif
varying vec3 vColor; varying vec3 vNormal; varying vec3 vLocal; varying vec3 vScale; varying vec2 vW;
void main() {
  vLocal = position; vNormal = normal;
#ifdef BOX
  vFx = aFx;
#endif
#ifdef USE_INSTANCING_COLOR
  vColor = instanceColor;
#else
  vColor = vec3(1.0);
#endif
#ifdef USE_INSTANCING
  mat4 im = instanceMatrix;
#else
  mat4 im = mat4(1.0);
#endif
  vScale = vec3(length(im[0].xyz), length(im[1].xyz), length(im[2].xyz));
  vec4 wp = modelMatrix * im * vec4(position, 1.0);
  vW = wp.xz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
// boxes: top face = the palette colour, unlit (same as the legend); sides × .78 (z faces) / .62 (x faces) with a darker foot;
// hover = +12 % on the top + a 1.5 px white rim; tick flash = a top brightness pulse. ±0.5/255 dither where there are gradients.
// plates (BOX undefined): the sector floor #0d0e11, fading to black over the outer 8.5 % of the map.
const FRAG = `
uniform vec2 uHalf; uniform vec3 uPlate;
varying vec3 vColor; varying vec3 vNormal; varying vec3 vLocal; varying vec3 vScale; varying vec2 vW;
#ifdef BOX
varying vec2 vFx;
#endif
float dither() { return (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0; }
void main() {
  vec3 n = normalize(vNormal);
#ifdef BOX
  vec3 c = vColor;
  if (n.y > 0.5) {
    c += (vec3(1.0) - c) * clamp(0.12 * vFx.x + 0.3 * vFx.y, 0.0, 1.0);
    if (vFx.x > 0.5) {
      vec2 p = vLocal.xz * vScale.xz;
      vec2 edge = 0.5 * vScale.xz - abs(p);
      vec2 fw = max(fwidth(p), vec2(1e-4));
      float e = min(edge.x / fw.x, edge.y / fw.y);
      c = mix(vec3(1.0), c, smoothstep(1.0, 2.0, e));
    }
    gl_FragColor = vec4(c, 1.0);
    return;
  }
  c *= n.y < -0.5 ? 0.4 : (abs(n.z) > 0.5 ? 0.78 : 0.62);
  c *= mix(0.85, 1.0, smoothstep(0.0, 0.4, vLocal.y));
  gl_FragColor = vec4(c + dither(), 1.0);
#else
  vec2 uv = vW / (2.0 * uHalf) + 0.5;
  vec2 d = min(uv, 1.0 - uv);
  float f = smoothstep(0.0, 0.085, min(d.x, d.y));
  gl_FragColor = vec4(uPlate * f * (n.y > 0.5 ? 1.0 : 0.6) + dither(), 1.0);
#endif
}`;

function buildScene() {
  const r = S.root;
  S.tier = tier();
  const renderer = new T.WebGLRenderer({ antialias: S.tier === 'high', alpha: false, powerPreference: 'high-performance' });
  S.dpr = Math.min(window.devicePixelRatio || 1, S.tier === 'high' ? 1.5 : 1.25);
  renderer.setPixelRatio(S.dpr);
  renderer.setClearColor(0x000000, 1);
  S.renderer = renderer;
  const cv = S.canvas = renderer.domElement;
  cv.className = 'm3-cv';
  cv.tabIndex = 0;
  cv.setAttribute('role', 'img');
  cv.setAttribute('aria-roledescription', '3D 지도');
  S.scene = new T.Scene();
  S.camera = new T.PerspectiveCamera(FOV, 1, 1, 50000);
  S.cam2 = new T.PerspectiveCamera(FOV, 1, 1, 50000);
  const uniforms = { uHalf: { value: new T.Vector2(500, 300) }, uPlate: { value: new T.Vector3(...PLATE_RGB) } };
  S.mat = new T.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, defines: { BOX: 1 }, extensions: { derivatives: true }, uniforms });
  S.plateMat = new T.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, extensions: { derivatives: true }, uniforms });
  S.plateGeo = new T.BoxGeometry(1, 1, 1); S.plateGeo.translate(0, 0.5, 0);
  S.edgeGeo = new T.EdgesGeometry(S.plateGeo);
  S.lineMat = new T.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 });
  S.outline = new T.LineSegments(S.edgeGeo, S.lineMat);
  S.outline.visible = false; S.outline.frustumCulled = false;
  S.scene.add(S.outline);

  S.labLayer = el('div', 'm3-labels'); S.labLayer.setAttribute('aria-hidden', 'true');
  S.hud = el('div', 'm3-hud'); S.hud.setAttribute('aria-hidden', 'true');
  S.ctl = el('div', 'm3-ctl');
  const btn = (cls, txt, label, fn) => { const b = el('button', 'm3-btn ' + cls, txt); b.type = 'button'; b.setAttribute('aria-label', label); b.title = label; b.addEventListener('click', fn); return b; };
  S.ctl.append(
    btn('zin', '+', '확대', () => zoomBy(1 / 1.35)),
    btn('zout', '−', '축소', () => zoomBy(1.35)),
    btn('reset', '', '처음 시점으로', () => goHome()));
  S.ctl.lastChild.innerHTML = '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 10a6 6 0 1 0 2-4.5"/><path d="M4 3.5V6.5h3"/></svg>';
  S.hint = el('div', 'm3-hint', hoverMQ.matches
    ? '끌어서 돌리기 · 휠로 확대 · 오른쪽 버튼으로 끌어 옮기기 · 섹터를 두 번 누르면 확대'
    : '옆으로 밀어 돌리기 · 두 손가락으로 확대 · 섹터를 두 번 탭하면 확대');
  S.hint.setAttribute('aria-hidden', 'true');
  S.kb = el('p', 'm3-sr', '화살표 키로 돌리고 기울이며 +, − 키로 확대·축소해요. 0 키나 Esc는 처음 시점, 처음 시점에서 Esc를 누르면 보기 전환 버튼으로 가요. 종목별 값은 지도나 표 보기에서 키보드로 볼 수 있어요.');
  S.kb.id = 'm3-kb';
  cv.setAttribute('aria-describedby', 'm3-kb');
  r.insertBefore(cv, S.msg);
  r.insertBefore(S.labLayer, S.msg);
  r.append(S.hud, S.ctl, S.hint, S.kb);
  S.tip = el('div', 'tip m3-tip'); S.tip.setAttribute('aria-hidden', 'true');
  document.body.append(S.tip);
  bindInput();
  cv.addEventListener('webglcontextlost', onLost, false);
  cv.addEventListener('webglcontextrestored', onRestored, false);
  S.ro = new ResizeObserver(() => { if (resize()) requestRender(); });
  S.ro.observe(r);
  if ('IntersectionObserver' in window) {
    S.io = new IntersectionObserver(es => { const v = es[es.length - 1].isIntersecting; if (v === S.visible) return; S.visible = v; if (v) requestRender(); else stopLoop(); }, { rootMargin: '80px' });
    S.io.observe(r);
  }
  S.built = true;
}
function onLost(e) { e.preventDefault(); stopLoop(); setMsg('3D 화면이 잠시 멈췄어요', '다시 그리는 중이에요…'); }
function onRestored() { setMsg(''); S.lastSig = ''; rebuild(false); requestRender(); }

function ensureMesh(n) {
  if (S.mesh && S.cap >= n) return;
  const cap = Math.max(64, Math.ceil(n * 1.25));
  if (S.mesh) { S.scene.remove(S.mesh); S.mesh.dispose(); }
  if (S.boxGeo) S.boxGeo.dispose();
  S.boxGeo = new T.BoxGeometry(1, 1, 1); S.boxGeo.translate(0, 0.5, 0);
  S.fx = new T.InstancedBufferAttribute(new Float32Array(cap * 2), 2);
  S.fx.setUsage(T.DynamicDrawUsage);
  S.boxGeo.setAttribute('aFx', S.fx);
  const m = new T.InstancedMesh(S.boxGeo, S.mat, cap);
  m.instanceMatrix.setUsage(T.DynamicDrawUsage);
  m.instanceColor = new T.InstancedBufferAttribute(new Float32Array(cap * 3), 3);
  m.instanceColor.setUsage(T.DynamicDrawUsage);
  m.frustumCulled = false; m.count = 0;
  S.mesh = m; S.cap = cap;
  S.scene.add(m);
}
function ensurePlates(n) {
  if (S.plates && S.pcap >= n) return;
  const cap = Math.max(32, Math.ceil(n * 1.25));
  if (S.plates) { S.scene.remove(S.plates); S.plates.dispose(); }
  const m = new T.InstancedMesh(S.plateGeo, S.plateMat, cap);
  m.frustumCulled = false; m.count = 0;
  S.plates = m; S.pcap = cap;
  S.scene.add(m);
}

/* ───────────────── data → instances ───────────────── */
function readLayout() {
  const k = KH();
  let L = [];
  try { L = k && typeof k.layout === 'function' ? k.layout() || [] : []; } catch (e) { L = []; }
  const tiles = [], sectors = [];
  let W = 0, H = 0;
  for (const n of L) {
    if (!(n.w > 0 && n.h > 0)) continue;
    W = Math.max(W, n.x + n.w); H = Math.max(H, n.y + n.h);
    if (n.kind === 'tile') tiles.push(n); else if (n.kind === 'sector') sectors.push(n);
  }
  const mapEl = document.getElementById('map');
  if (mapEl && mapEl.clientWidth > 0) { W = mapEl.clientWidth; H = mapEl.clientHeight || H; }
  return { tiles, sectors, W, H };
}
function rebuild(entry) {
  if (!S.built || S.leaving) return;
  const { tiles, sectors, W, H } = readLayout();
  const tick = S.dataTick; S.dataTick = false;
  const sig = tiles.length + '|' + W + 'x' + H + '|' + tiles.map(t => (t.code || t.label) + t.x + ',' + t.y + ',' + t.w + ',' + t.h + t.color + t.sub).join(';') + '|' + sectors.map(s => s.label + s.sub + s.x + ',' + s.y).join(';');
  if (sig === S.lastSig) return;
  S.lastSig = sig;
  const firstData = !S.n && tiles.length > 0;
  const sizeChanged = W !== S.W || H !== S.H;
  S.W = W; S.H = H; S.tiles = tiles; S.sectors = sectors;
  const n = tiles.length;
  if (!n) {
    S.n = 0; if (S.mesh) S.mesh.count = 0; if (S.plates) S.plates.count = 0;
    hideTip(true); setHover(-1);
    const mk = KH() && KH().market ? KH().market() : '';
    setMsg(/^(world|cmdty)$/.test(mk) ? '이 탭은 3D로 볼 수 없어요' : '3D로 그릴 종목이 없어요', '시장이나 보기를 바꿔 보세요.');
    updateAria(); requestRender();
    return;
  }
  setMsg('');
  ensureMesh(n);
  ensurePlates(Math.max(1, sectors.length));
  S.maxH = Math.max(12, 0.18 * Math.min(W, H));

  // value, palette position and range
  const Lt = paletteLut();
  const vals = new Array(n), ts = new Array(n), cols = new Array(n);
  let pctCount = 0;
  for (let i = 0; i < n; i++) {
    const t = tiles[i];
    cols[i] = parseColor(t.color);
    vals[i] = parsePct(t.sub); if (vals[i] != null) pctCount++;
    ts[i] = colourT(Lt, t.color, cols[i]);
  }
  S.metricPct = pctCount > n * 0.5;
  S.R = S.metricPct ? inferRange(vals, ts) : null;

  // sector index per tile (entry stagger)
  const secIx = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    const t = tiles[i], cx = t.x + t.w / 2, cy = t.y + t.h / 2;
    for (let j = 0; j < sectors.length; j++) { const q = sectors[j]; if (cx >= q.x && cx <= q.x + q.w && cy >= q.y && cy <= q.y + q.h) { secIx[i] = j; break; } }
  }

  const prevKeys = S.keyIx, prevCur = S.cur;
  const to = new Float32Array(n * STRIDE), from = new Float32Array(n * STRIDE), delay = new Float32Array(n);
  const keys = new Array(n), keyIx = new Map();
  for (let i = 0; i < n; i++) {
    const t = tiles[i];
    const key = t.code || ('t:' + t.label);
    keys[i] = key; keyIx.set(key, i);
    const gap = Math.min(0.5, t.w * 0.12, t.h * 0.12);   // 1 px between neighbours on top of the 2D padding
    const u = vals[i] != null && S.R ? Math.abs(vals[i]) / S.R : ts[i] != null ? Math.abs(ts[i]) : 0;
    const o = i * STRIDE;
    to[o] = t.x + t.w / 2 - W / 2; to[o + 1] = t.y + t.h / 2 - H / 2;
    to[o + 2] = Math.max(t.w - 2 * gap, 0.4); to[o + 3] = Math.max(t.h - 2 * gap, 0.4);
    to[o + 4] = 2 + (S.maxH - 2) * Math.pow(Math.min(1, u), 0.75);   // 0 % = a 2-unit plate
    to[o + 5] = cols[i][0] / 255; to[o + 6] = cols[i][1] / 255; to[o + 7] = cols[i][2] / 255;
  }
  const tk = tokens(), isFancy = fancy();
  const doEntry = entry && firstData && isFancy;
  const doTween = !doEntry && isFancy && prevCur.length > 0 && !sizeChanged;
  const per = sectors.length ? Math.min(40, (1100 - tk.m3 - 20) / Math.max(sectors.length, 1)) : 0;   // whole entry ≤ 1.1 s
  let maxDelay = 0;
  for (let i = 0; i < n; i++) {
    const o = i * STRIDE, pi = prevKeys.get(keys[i]);
    for (let k = 0; k < STRIDE; k++) from[o + k] = to[o + k];
    if (doEntry) { from[o + 4] = 0.2; delay[i] = secIx[i] * per; maxDelay = Math.max(maxDelay, delay[i]); }
    else if (doTween) {
      if (pi != null && pi * STRIDE + STRIDE <= prevCur.length) for (let k = 0; k < STRIDE; k++) from[o + k] = prevCur[pi * STRIDE + k];
      else from[o + 4] = 0.2;
    }
  }
  // tick flash (fancy, live updates only): price changed since the last data → top brightness pulse, at most 60
  const k0 = KH();
  if (isFancy && tick && !S.replay && !firstData && S.lastPx.size) {
    const cand = [];
    for (let i = 0; i < n; i++) {
      const c = tiles[i].code; if (!c) continue;
      const st = k0 && k0.stock ? k0.stock(c) : null, p = st && st.p, q = S.lastPx.get(c);
      if (p > 0 && q > 0 && p !== q) cand.push([i, Math.abs(p - q) / q * tiles[i].w * tiles[i].h, c]);
    }
    cand.sort((a, b) => b[1] - a[1]);
    const now = performance.now();
    for (const [i, , c] of cand.slice(0, MAX_FLASH)) S.flashes.set(keys[i], now + hash01(c) * 200);
  }
  S.lastPx = new Map();
  for (const t of tiles) if (t.code) { const st = k0 && k0.stock ? k0.stock(t.code) : null; if (st && st.p > 0) S.lastPx.set(t.code, st.p); }

  S.n = n; S.keys = keys; S.keyIx = keyIx; S.to = to; S.from = from; S.delay = delay;
  S.cur = new Float32Array(doEntry || doTween ? from : to);
  S.tween = doEntry || doTween ? { start: performance.now(), dur: tk.m3, maxDelay, ease: tk.out } : null;
  S.order = Array.from({ length: n }, (_, i) => i).sort((a, b) => tiles[b].w * tiles[b].h - tiles[a].w * tiles[a].h);
  S.tipFor = null;
  if (S.hover >= 0) {
    const hk = S.hoverKey; S.hover = -1;
    const ni = hk != null ? keyIx.get(hk) : undefined;
    if (ni != null) { setHover(ni); if (S.tip && S.tip.classList.contains('show')) { fillTip(ni); S.tipFor = hk; } } else hideTip(true);
  }
  writePlates();
  writeInstances();
  S.mat.uniforms.uHalf.value.set(W / 2, H / 2);

  // camera: keep the user's view unless the map changed size; the fancy entry starts exactly at the 2D view and tilts in
  const home = fitView(HOME_POLAR, HOME_AZ);
  S.homePose = home;
  if (home) {
    if (doEntry) {
      const top = topDownPose();
      S.cam = Object.assign({}, top); S.goal = Object.assign({}, top);
      S.fly = { from: top, to: home, start: performance.now(), dur: tk.fly, ease: tk.flyEase };
    } else if (!S.cam || sizeChanged || !S.userMoved) {
      if (S.fly) S.fly.to = home;
      else { S.cam = Object.assign({}, home); S.goal = Object.assign({}, home); }
      S.userMoved = false;
    }
  }
  updateHud(); updateAria();
  requestRender();
}
function writeInstances() {
  const m = S.mesh; if (!m) return;
  const n = S.n, A = S.cur, M = m.instanceMatrix.array, C = m.instanceColor.array, F = S.fx.array;
  const now = performance.now(), fl = S.flashes, tk = tokens();
  for (let i = 0; i < n; i++) {
    const o = i * STRIDE, q = i * 16;
    M[q] = A[o + 2]; M[q + 1] = 0; M[q + 2] = 0; M[q + 3] = 0;
    M[q + 4] = 0; M[q + 5] = A[o + 4]; M[q + 6] = 0; M[q + 7] = 0;
    M[q + 8] = 0; M[q + 9] = 0; M[q + 10] = A[o + 3]; M[q + 11] = 0;
    M[q + 12] = A[o]; M[q + 13] = 0; M[q + 14] = A[o + 1]; M[q + 15] = 1;
    C[i * 3] = A[o + 5]; C[i * 3 + 1] = A[o + 6]; C[i * 3 + 2] = A[o + 7];
    F[i * 2] = i === S.hover ? 1 : 0;
    let p = 0;
    if (fl.size) {
      const s0 = fl.get(S.keys[i]);
      if (s0 != null) {
        const k = (now - s0) / tk.flash;
        if (k >= 1) fl.delete(S.keys[i]);
        else if (k > 0) p = k < 0.12 ? k / 0.12 : 1 - tk.out((k - 0.12) / 0.88);
      }
    }
    F[i * 2 + 1] = p;
  }
  m.count = n;
  m.instanceMatrix.updateRange.offset = 0; m.instanceMatrix.updateRange.count = n * 16;
  m.instanceColor.updateRange.offset = 0; m.instanceColor.updateRange.count = n * 3;
  S.fx.updateRange.offset = 0; S.fx.updateRange.count = n * 2;
  m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true; S.fx.needsUpdate = true;
  if (S.hover >= 0 && S.hover < n) {
    const o = S.hover * STRIDE;
    S.outline.visible = true;
    S.outline.position.set(A[o], 0, A[o + 1]);
    S.outline.scale.set(A[o + 2] + 0.3, A[o + 4] + 0.15, A[o + 3] + 0.3);
  } else S.outline.visible = false;
}
function writePlates() {
  const m = S.plates; if (!m) return;
  const W = S.W, H = S.H, M = m.instanceMatrix.array;
  const list = S.sectors.length ? S.sectors : [{ x: 0, y: 0, w: W, h: H }];
  list.forEach((n, i) => {
    const q = i * 16;
    M.fill(0, q, q + 16);
    M[q] = n.w; M[q + 5] = 1; M[q + 10] = n.h; M[q + 12] = n.x + n.w / 2 - W / 2; M[q + 13] = -0.98; M[q + 14] = n.y + n.h / 2 - H / 2; M[q + 15] = 1;
  });
  m.count = list.length;
  m.instanceMatrix.needsUpdate = true;
}

/* ───────────────── camera ─────────────────
   pose = {tx, tz, dist, polar, az}. Input moves S.goal; S.cam follows it (τ 70 ms, zoom τ 90 ms; at once when reduced).
   S.fly drives both along an eased path (entry tilt, sector flight, home, fold-out). */
const POSE_KEYS = ['tx', 'tz', 'dist', 'polar', 'az'];
function camPos(c) {
  const sp = Math.sin(c.polar);
  return [c.tx + c.dist * sp * Math.sin(c.az), c.dist * Math.cos(c.polar), c.tz + c.dist * sp * Math.cos(c.az)];
}
function applyCamera(cam, c) {
  const p = camPos(c);
  cam.aspect = S.vw / Math.max(S.vh, 1);
  cam.position.set(p[0], p[1], p[2]);
  cam.up.set(0, 1, 0);
  cam.lookAt(c.tx, 0, c.tz);
  cam.near = Math.max(1, c.dist * 0.05);
  cam.far = c.dist * 6 + Math.max(S.W, S.H) * 4;
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld();
}
// the 2D map exactly: straight down, the map filling the canvas (the canvas has the map's size)
function topDownPose() { return { tx: 0, tz: 0, dist: S.vh / 2 / Math.tan(FOV * DEG / 2), polar: POLAR_MIN, az: 0 }; }
// fit a ground rect (default: the whole map with its tallest boxes) at a tilt: binary-search the distance, then centre it
function fitView(polar, az, rect) {
  if (!S.camera || !S.W || !S.vw) return null;
  const cam = S.cam2;
  const W = S.W, H = S.H;
  const R = rect || { x0: -W / 2, z0: -H / 2, x1: W / 2, z1: H / 2 };
  const top = rect ? S.maxH * 0.5 : S.maxH * 0.75;
  const pts = [];
  for (const x of [R.x0, R.x1]) for (const z of [R.z0, R.z1]) { pts.push([x, 0, z]); pts.push([x, top, z]); }
  const v = new T.Vector3();
  const narrow = S.vw < 560;
  const lim = { x0: -0.94, x1: 0.94, y0: narrow ? -0.9 : -0.88, y1: narrow ? 0.8 : 0.84 };
  const ext = c => {
    applyCamera(cam, c);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) { v.set(p[0], p[1], p[2]).project(cam); x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y); }
    return { x0, x1, y0, y1 };
  };
  const span = Math.max(R.x1 - R.x0, R.z1 - R.z0);
  const c = { tx: (R.x0 + R.x1) / 2, tz: (R.z0 + R.z1) / 2, dist: span * 2, polar, az };
  const fr = [Math.cos(az), -Math.sin(az)], fw = [-Math.sin(az), -Math.cos(az)];
  for (let it = 0; it < 4; it++) {
    let lo = span * 0.2, hi = span * 20;
    for (let k = 0; k < 28; k++) {
      c.dist = (lo + hi) / 2;
      const e = ext(c);
      if (Math.max((e.x1 - e.x0) / (lim.x1 - lim.x0), (e.y1 - e.y0) / (lim.y1 - lim.y0)) > 1) lo = c.dist; else hi = c.dist;
    }
    c.dist = hi;
    const e = ext(c);
    const dx = (e.x0 + e.x1) / 2 - (lim.x0 + lim.x1) / 2, dy = (e.y0 + e.y1) / 2 - (lim.y0 + lim.y1) / 2;
    const halfH = c.dist * Math.tan(FOV * DEG / 2), halfW = halfH * cam.aspect;
    const kx = dx * halfW, ky = dy * halfH / Math.max(Math.cos(polar), 0.35);
    c.tx += fr[0] * kx + fw[0] * ky; c.tz += fr[1] * kx + fw[1] * ky;
  }
  if (!rect) S.fitDist = c.dist;
  return c;
}
function clampPose(c) {
  c.polar = clamp(c.polar, POLAR_MIN, POLAR_MAX);
  c.az = clamp(c.az, -AZ_LIM, AZ_LIM);
  c.dist = clamp(c.dist, S.fitDist / ZOOM_IN, S.fitDist / ZOOM_OUT);
  c.tx = clamp(c.tx, -S.W * 0.6, S.W * 0.6);
  c.tz = clamp(c.tz, -S.H * 0.6, S.H * 0.6);
  return c;
}
// move the camera to a pose: a flight in fancy, a jump otherwise
function flyTo(pose, dur, ease, done) {
  S.inertia = null;
  if (fancy() && dur > 0) S.fly = { from: Object.assign({}, S.cam), to: pose, start: performance.now(), dur, ease, done };
  else { S.fly = null; S.cam = Object.assign({}, pose); S.goal = Object.assign({}, pose); if (done) done(); }
  requestRender();
}
const atHome = () => !S.userMoved && !S.fly;
function goHome() {
  const h = fitView(HOME_POLAR, HOME_AZ);
  if (!h) return;
  S.homePose = h; S.userMoved = false;
  flyTo(h, tokens().fly, tokens().flyEase);
  hideHint();
}
function flyToSector(i) {
  const t = S.tiles[i]; if (!t) return;
  const cx = t.x + t.w / 2, cy = t.y + t.h / 2;
  const s = S.sectors.find(q => cx >= q.x && cx <= q.x + q.w && cy >= q.y && cy <= q.y + q.h);
  if (!s) return;
  const W = S.W, H = S.H;
  const p = fitView(S.goal.polar, S.goal.az, { x0: s.x - W / 2, z0: s.y - H / 2, x1: s.x + s.w - W / 2, z1: s.y + s.h - H / 2 });
  if (!p) return;
  S.userMoved = true;
  flyTo(clampPose(p), tokens().fly, tokens().flyEase);
  hideHint();
}
function groundAtPose(pose, clientX, clientY) {
  applyCamera(S.cam2, pose);
  const r = S.canvas.getBoundingClientRect();
  const x = ((clientX - r.left) / r.width) * 2 - 1, y = -((clientY - r.top) / r.height) * 2 + 1;
  const v = new T.Vector3(x, y, 0.5).unproject(S.cam2), p = S.cam2.position;
  const d = [v.x - p.x, v.y - p.y, v.z - p.z];
  if (d[1] > -1e-6) return null;
  const t = -p.y / d[1];
  return [p.x + d[0] * t, p.z + d[2] * t];
}
function zoomBy(k, cx, cy) {
  if (!S.goal) return;
  S.inertia = null; S.fly = null; S.userMoved = true;
  const g = S.goal;
  const before = cx != null ? groundAtPose(g, cx, cy) : null;
  g.dist *= k;
  clampPose(g);
  if (before) {
    const after = groundAtPose(g, cx, cy);
    if (after) { g.tx += before[0] - after[0]; g.tz += before[1] - after[1]; clampPose(g); }
  }
  if (reduced()) S.cam = Object.assign({}, g);
  hideHint();
  requestRender();
}
function panBy(dx, dy) {
  const g = S.goal;
  const per = 2 * g.dist * Math.tan(FOV * DEG / 2) / Math.max(S.vh, 1);
  const kz = 1 / Math.max(Math.cos(g.polar), 0.45);
  const r = [Math.cos(g.az), -Math.sin(g.az)], f = [-Math.sin(g.az), -Math.cos(g.az)];
  const mx = -dx * per * r[0] + dy * per * kz * f[0], mz = -dx * per * r[1] + dy * per * kz * f[1];
  g.tx += mx; g.tz += mz;
  clampPose(g);
  return [mx, mz];
}

/* ───────────────── loop (render on demand) ───────────────── */
function requestRender() {
  if (!S.built || !S.on || document.hidden || !S.visible || S.raf) return;
  S.raf = requestAnimationFrame(frame);
}
function stopLoop() { if (S.raf) cancelAnimationFrame(S.raf); S.raf = 0; S.lastNow = 0; }
function frame(now) {
  S.raf = 0;
  if (!S.built || !S.cam) return;
  const t0 = performance.now();
  const dt = S.lastNow ? clamp(now - S.lastNow, 0, 64) : 16;
  S.lastNow = now;
  let active = false;
  if (S.tween) {
    const tw = S.tween, n = S.n, A = S.cur, F = S.from, G = S.to, D = S.delay, el2 = now - tw.start;
    for (let i = 0; i < n; i++) {
      const e = tw.ease(clamp((el2 - D[i]) / tw.dur, 0, 1)), o = i * STRIDE;
      for (let j = 0; j < STRIDE; j++) A[o + j] = F[o + j] + (G[o + j] - F[o + j]) * e;
    }
    if (el2 >= tw.dur + tw.maxDelay) S.tween = null; else active = true;
  }
  if (S.tween || S.flashes.size || S.fxDirty || active) { writeInstances(); S.fxDirty = false; if (S.flashes.size) active = true; }
  if (S.fly) {
    const f = S.fly, k = clamp((now - f.start) / f.dur, 0, 1), e = f.ease(k), c = {};
    for (const key of POSE_KEYS) c[key] = f.from[key] + (f.to[key] - f.from[key]) * e;
    S.cam = c; S.goal = Object.assign({}, c);
    if (k >= 1) { S.fly = null; if (f.done) f.done(); } else active = true;
  } else {
    if (S.inertia && !S.drag) {
      const it = S.inertia, g = S.goal;
      if (it.kind === 'rot') { g.az -= it.vx * dt; g.polar -= it.vy * dt; } else { g.tx += it.vx * dt; g.tz += it.vy * dt; }
      clampPose(g);
      const decay = Math.exp(-dt / TAU_INERTIA);
      it.vx *= decay; it.vy *= decay;
      if (Math.abs(it.vx) + Math.abs(it.vy) < (it.kind === 'rot' ? 1e-6 : 1e-3)) S.inertia = null; else active = true;
    }
    const red = reduced(), c = S.cam, g = S.goal;
    let moving = false;
    for (const key of POSE_KEYS) {
      const tau = red ? 0 : key === 'dist' ? TAU_ZOOM : TAU_CAM;
      const a = tau ? 1 - Math.exp(-dt / tau) : 1;
      c[key] += (g[key] - c[key]) * a;
      const eps = key === 'dist' ? g.dist * 1e-4 : key === 'tx' || key === 'tz' ? 0.02 : 1e-4;
      if (Math.abs(g[key] - c[key]) > eps) moving = true; else c[key] = g[key];
    }
    if (moving) active = true;
  }
  if (!S.built) return;          // a fold-out flight may have finished and freed everything
  applyCamera(S.camera, S.cam);
  const tr = performance.now();
  S.renderer.render(S.scene, S.camera);
  S.pm = S.camera.projectionMatrix.clone().multiply(S.camera.matrixWorldInverse).elements;
  const t1 = performance.now();
  S.ftR.push(t1 - tr); if (S.ftR.length > 60) S.ftR.shift();
  if (!S.leaving) updateLabels();
  const t2 = performance.now(), ms = t2 - t0;
  S.frames++; S.ft.push(ms); if (S.ft.length > 60) S.ft.shift();
  S.ftL.push(t2 - t1); if (S.ftL.length > 60) S.ftL.shift();
  if (active) requestRender(); else S.lastNow = 0;
}
// returns true when the size changed
function resize() {
  if (!S.renderer || !S.root) return false;
  const w = S.root.clientWidth, h = S.root.clientHeight;
  if (!w || !h) return false;                 // hidden (display:none): keep the last size
  if (w === S.vw && h === S.vh) return false;
  S.vw = w; S.vh = h;
  S.renderer.setPixelRatio(S.dpr);
  S.renderer.setSize(w, h, false);
  reserve();
  if (S.n) {
    const home = fitView(HOME_POLAR, HOME_AZ);
    S.homePose = home;
    if (!S.userMoved && home) { if (S.fly) S.fly.to = home; else { S.cam = Object.assign({}, home); S.goal = Object.assign({}, home); } }
  }
  return true;
}

/* ───────────────── picking ───────────────── */
function rayAt(clientX, clientY) {
  const r = S.canvas.getBoundingClientRect();
  const x = ((clientX - r.left) / r.width) * 2 - 1, y = -((clientY - r.top) / r.height) * 2 + 1;
  const v = new T.Vector3(x, y, 0.5).unproject(S.camera);
  const p = S.camera.position;
  const d = [v.x - p.x, v.y - p.y, v.z - p.z], L = Math.hypot(d[0], d[1], d[2]) || 1;
  return { o: [p.x, p.y, p.z], d: [d[0] / L, d[1] / L, d[2] / L] };
}
// nearest displayed box along a ray (slab test): {i, t}
function castBoxes(o, d, maxT) {
  const A = S.cur, n = S.n;
  const ix = 1 / (d[0] || 1e-12), iy = 1 / (d[1] || 1e-12), iz = 1 / (d[2] || 1e-12);
  let best = -1, bt = maxT == null ? Infinity : maxT;
  for (let i = 0; i < n; i++) {
    const q = i * STRIDE, hw = A[q + 2] / 2, hd = A[q + 3] / 2;
    let t1 = (A[q] - hw - o[0]) * ix, t2 = (A[q] + hw - o[0]) * ix;
    let tmin = Math.min(t1, t2), tmax = Math.max(t1, t2);
    t1 = -o[1] * iy; t2 = (A[q + 4] - o[1]) * iy;
    tmin = Math.max(tmin, Math.min(t1, t2)); tmax = Math.min(tmax, Math.max(t1, t2));
    if (tmax < tmin) continue;
    t1 = (A[q + 1] - hd - o[2]) * iz; t2 = (A[q + 1] + hd - o[2]) * iz;
    tmin = Math.max(tmin, Math.min(t1, t2)); tmax = Math.min(tmax, Math.max(t1, t2));
    if (tmax < tmin || tmax < 0) continue;
    const t = tmin > 0 ? tmin : tmax;
    if (t < bt) { bt = t; best = i; }
  }
  return { i: best, t: bt };
}
function pickAt(clientX, clientY) {
  if (!S.built || !S.n || !S.camera || !S.pm) return -1;
  const r = rayAt(clientX, clientY);
  return castBoxes(r.o, r.d).i;
}

/* ───────────────── hover & tooltip ───────────────── */
function setHover(i) {
  if (i === S.hover) return;
  S.hover = i;
  S.hoverKey = i >= 0 ? S.keys[i] : null;
  if (S.canvas) S.canvas.style.cursor = i >= 0 ? 'pointer' : '';
  S.fxDirty = true;
  requestRender();
}
function hideTip(now) {
  clearTimeout(S.tipHide); S.tipHide = 0;
  if (!S.tip) return;
  const go = () => { if (S.tip) S.tip.classList.remove('show'); S.tipPos = null; S.tipFor = null; };
  if (now || !fancy()) go(); else S.tipHide = setTimeout(go, 120);   // fancy: no blink in the gaps between boxes
}
function fillTip(i) {
  const t = S.tiles[i], k = KH();
  if (!t || !S.tip) return;
  const st = t.code && k && k.stock ? k.stock(t.code) : null;
  const f = k && k.fmt ? k.fmt : null;
  const head = el('div', 'card-head');
  if (st) head.append(el('div', 'path', [(k.MKT_NAME && k.MKT_NAME[st.m]) || '', st.s, st.i].filter(Boolean).join('  ›  ')));
  else head.append(el('div', 'path', t.code ? '' : '테마'));
  const nm = el('div', 'nmrow'); nm.append(el('b', '', t.label)); if (t.code) nm.append(el('small', '', t.code));
  head.append(nm);
  const px = el('div', 'px');
  const price = t.px || (st && st.p > 0 && f ? f.int(st.p) : '');
  if (price) px.append(el('b', '', price));
  // today's change at full precision when the tile shows today's live value, otherwise the value as the map shows it
  if (st && f && f.pct(st.r, 1) === t.sub) px.append(el('span', f.cls(st.r), `${f.chg(st.d)}  (${f.pct(st.r)})`));
  else if (t.sub) px.append(el('span', signCls(t.sub), t.sub));
  head.append(px);
  if (st && f) {
    const meta = el('div', 'meta');
    const a = el('span', '', '시가총액 '); a.append(el('em', '', f.eok(st.cap)));
    const b = el('span', '', '거래대금 '); b.append(el('em', '', f.eok(st.tv)));
    meta.append(a, b); head.append(meta);
  }
  S.tip.replaceChildren(head, el('div', 'tiphint', t.code ? '누르면 종목 페이지가 열려요 · 두 번 누르면 섹터 확대' : '테마 종목은 2D 지도에서 열 수 있어요'));
}
function tipTarget(x, y) {
  const tip = S.tip, pad = 14, w = tip.offsetWidth || 300, h = tip.offsetHeight || 120;
  let left = x + 18, top = y + 18;
  if (left + w > innerWidth - pad) left = x - w - 18;
  if (left < pad) left = pad;
  if (top + h > innerHeight - pad) top = Math.max(pad, innerHeight - h - pad);
  return [left, top];
}
function placeTip(x, y) {
  S.tipGoal = tipTarget(x, y);
  if (!S.tipPos || !fancy()) { S.tipPos = S.tipGoal.slice(); S.tip.style.left = S.tipPos[0] + 'px'; S.tip.style.top = S.tipPos[1] + 'px'; return; }
  if (S.tipRaf) return;
  let last = 0;
  const step = now => {
    S.tipRaf = 0;
    if (!S.tipPos || !S.tipGoal || !S.tip) return;
    const dt = last ? Math.min(now - last, 64) : 16; last = now;
    const a = 1 - Math.exp(-dt / TAU_TIP);
    S.tipPos[0] += (S.tipGoal[0] - S.tipPos[0]) * a; S.tipPos[1] += (S.tipGoal[1] - S.tipPos[1]) * a;
    S.tip.style.left = S.tipPos[0].toFixed(1) + 'px'; S.tip.style.top = S.tipPos[1].toFixed(1) + 'px';
    if (Math.abs(S.tipGoal[0] - S.tipPos[0]) + Math.abs(S.tipGoal[1] - S.tipPos[1]) > 0.5) S.tipRaf = requestAnimationFrame(step);
  };
  S.tipRaf = requestAnimationFrame(step);
}
function hoverAt(x, y) {
  const i = pickAt(x, y);
  setHover(i);
  if (i < 0) { hideTip(false); return; }
  clearTimeout(S.tipHide); S.tipHide = 0;
  if (S.tipFor !== S.keys[i]) { fillTip(i); S.tipFor = S.keys[i]; }
  S.tip.classList.add('show');
  placeTip(x, y);
}

/* ───────────────── input ─────────────────
   mouse: drag = turn and tilt, right / shift-drag = move, wheel = zoom at the pointer.
   touch: a sideways drag (> 6 px and 1.2× the vertical) locks turning; moving 10 px vertically first leaves the page its scroll
   (canvas touch-action: pan-y). Two fingers = zoom + twist + move. Tap = stock page, double tap = fly to the sector. */
function hideHint() { if (S.hint && !S.hinted) { S.hinted = true; S.hint.classList.add('gone'); } }
function bindInput() {
  const cv = S.canvas;
  cv.addEventListener('pointerdown', onDown);
  cv.addEventListener('pointermove', onMove);
  cv.addEventListener('pointerup', onUp);
  cv.addEventListener('pointercancel', onUp);
  cv.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !S.drag) { setHover(-1); hideTip(false); } });
  cv.addEventListener('wheel', onWheel, { passive: false });
  cv.addEventListener('contextmenu', e => e.preventDefault());
  cv.addEventListener('keydown', onKey);
  cv.addEventListener('dblclick', e => e.preventDefault());
}
const ptrList = () => [...S.ptrs.values()];
function twoState() {
  const [a, b] = ptrList();
  return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, ang: Math.atan2(b.y - a.y, b.x - a.x), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
}
function onDown(e) {
  if (!S.n || !S.goal || S.leaving) return;
  if (e.pointerType === 'mouse' && e.button !== 0 && e.button !== 2) return;
  S.ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, t0: performance.now(), type: e.pointerType });
  S.inertia = null;
  if (S.fly) { S.goal = Object.assign({}, S.cam); S.fly = null; }
  const P = ptrList();
  if (P.length === 1) {
    const touch = e.pointerType === 'touch';
    const pan = !touch && (e.button === 2 || e.shiftKey || e.ctrlKey || e.metaKey);
    S.drag = { mode: touch ? 'pending' : pan ? 'pan' : 'rot', moved: 0, samples: [] };
    if (!touch && S.canvas.setPointerCapture) S.canvas.setPointerCapture(e.pointerId);
  } else if (P.length === 2) {
    S.drag = Object.assign({ mode: 'two', moved: 99, samples: [] }, twoState());
    clearTimeout(S.tapTimer); S.tapTimer = 0;
    for (const id of S.ptrs.keys()) try { S.canvas.setPointerCapture(id); } catch (err) { /* already gone */ }
  }
  if (e.pointerType === 'mouse') { setHover(-1); hideTip(true); }
}
function onMove(e) {
  const p = S.ptrs.get(e.pointerId);
  if (!p) {
    if (e.pointerType === 'mouse' && hoverMQ.matches && S.n && !S.leaving) {
      S.hoverXY = [e.clientX, e.clientY];
      if (!S.hoverQ) S.hoverQ = requestAnimationFrame(() => { S.hoverQ = 0; if (S.hoverXY && S.built && !S.drag) hoverAt(S.hoverXY[0], S.hoverXY[1]); });
    }
    return;
  }
  const dx = e.clientX - p.x, dy = e.clientY - p.y;
  p.x = e.clientX; p.y = e.clientY;
  const D = S.drag; if (!D) return;
  D.moved = Math.max(D.moved, Math.hypot(p.x - p.x0, p.y - p.y0));
  if (D.mode === 'yield') return;
  if (D.mode === 'pending') {
    const tx = Math.abs(p.x - p.x0), ty = Math.abs(p.y - p.y0);
    if (tx > 6 && tx > ty * 1.2) { D.mode = 'rot'; try { S.canvas.setPointerCapture(e.pointerId); } catch (err) { /* gone */ } }
    else if (ty > 10) { D.mode = 'yield'; return; }
    else return;
  }
  if (D.mode !== 'two' && D.moved < 3) return;
  S.userMoved = true; hideHint();
  const g = S.goal;
  if (D.mode === 'rot') {
    const kx = 2.2 / Math.max(S.vw, 320), ky = 1.6 / Math.max(S.vh, 320);
    g.az -= dx * kx; g.polar -= dy * ky;
    D.samples.push([performance.now(), dx * kx, dy * ky]);
  } else if (D.mode === 'pan') {
    const m = panBy(dx, dy);
    D.samples.push([performance.now(), m[0], m[1]]);
  } else if (D.mode === 'two') {
    if (S.ptrs.size < 2) return;
    const s = twoState();
    const before = groundAtPose(g, s.mx, s.my);
    g.dist *= D.d / s.d;
    let da = s.ang - D.ang; if (da > Math.PI) da -= 2 * Math.PI; if (da < -Math.PI) da += 2 * Math.PI;
    g.az += da;
    clampPose(g);
    const after = groundAtPose(g, s.mx, s.my);
    if (before && after) { g.tx += before[0] - after[0]; g.tz += before[1] - after[1]; }
    panBy(s.mx - D.mx, s.my - D.my);
    Object.assign(D, s);
  }
  if (D.samples.length > 8) D.samples.shift();
  clampPose(g);
  if (reduced()) S.cam = Object.assign({}, g);
  requestRender();
}
function onUp(e) {
  const p = S.ptrs.get(e.pointerId);
  S.ptrs.delete(e.pointerId);
  const D = S.drag;
  if (S.ptrs.size === 1 && D && D.mode === 'two') {   // one finger left after a pinch: keep turning from here
    const q = ptrList()[0]; q.x0 = q.x; q.y0 = q.y;
    S.drag = { mode: 'rot', moved: 99, samples: [] };
    return;
  }
  if (S.ptrs.size) return;
  S.drag = null;
  if (!p || !D || e.type === 'pointercancel' || D.mode === 'yield') return;
  const dt = performance.now() - p.t0;
  if (D.moved < 6 && dt < 600) { onTap(e.clientX, e.clientY); return; }
  // inertia (fancy only): angular / pan velocity of the last ~90 ms, decaying τ 250 ms
  if (fancy() && (D.mode === 'rot' || D.mode === 'pan')) {
    const now = performance.now(), recent = D.samples.filter(s => now - s[0] < 90);
    if (recent.length >= 2) {
      const span = Math.max(now - recent[0][0], 16);
      let sx = 0, sy = 0; for (const s of recent) { sx += s[1]; sy += s[2]; }
      S.inertia = { kind: D.mode, vx: sx / span, vy: sy / span };
      requestRender();
    }
  }
  if (e.pointerType === 'mouse' && hoverMQ.matches) hoverAt(e.clientX, e.clientY);
}
// one tap/click opens the stock page after a short wait; a second one within 320 ms flies to the sector (empty floor: home)
function onTap(x, y) {
  const now = performance.now();
  const i = pickAt(x, y);
  if (S.tapTimer && S.tapXY && now - S.tapT < 320 && Math.hypot(x - S.tapXY[0], y - S.tapXY[1]) < 30) {
    clearTimeout(S.tapTimer); S.tapTimer = 0; S.tapXY = null;
    if (i >= 0 && S.sectors.length) flyToSector(i); else goHome();
    return;
  }
  S.tapT = now; S.tapXY = [x, y];
  clearTimeout(S.tapTimer);
  S.tapTimer = setTimeout(() => {
    S.tapTimer = 0;
    if (i < 0 || !S.on || S.leaving) return;
    const t = S.tiles[i];
    if (!t || !t.code) return;
    const ks = window.KHStock;
    if (ks && typeof ks.open === 'function') { hideTip(true); ks.open(t.code, { opener: S.canvas }); }
  }, 250);
}
function onWheel(e) {
  if (!S.n) return;
  e.preventDefault();
  const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
  zoomBy(Math.exp(clamp(dy, -240, 240) * 0.0016), e.clientX, e.clientY);
}
function onKey(e) {
  if (!S.goal) return;
  const g = S.goal;
  switch (e.key) {
    case 'ArrowLeft': g.az += 10 * DEG; break;
    case 'ArrowRight': g.az -= 10 * DEG; break;
    case 'ArrowUp': g.polar -= 5 * DEG; break;
    case 'ArrowDown': g.polar += 5 * DEG; break;
    case '+': case '=': e.preventDefault(); zoomBy(1 / 1.25); return;
    case '-': case '_': e.preventDefault(); zoomBy(1.25); return;
    case '0': case 'Home': e.preventDefault(); goHome(); return;
    case 'Escape': {
      e.preventDefault();
      hideTip(true); setHover(-1);
      if (!atHome()) { goHome(); return; }
      // already at home: hand focus to the view switch (지도 · 3D · 표) so the 2D map / table is one key away
      const seg = document.querySelector('.viewseg');
      const b = seg && (seg.querySelector('button[data-v="3d"]') || seg.querySelector('button[aria-pressed="true"]') || seg.querySelector('button'));
      if (b) b.focus(); else S.canvas.blur();
      return;
    }
    default: return;
  }
  e.preventDefault();
  S.fly = null; S.inertia = null; S.userMoved = true;
  clampPose(g);
  if (reduced()) S.cam = Object.assign({}, g);
  hideHint();
  requestRender();
}

/* ───────────────── labels: html overlay, positioned by projecting points ───────────────── */
function proj(x, y, z, out) {
  const e = S.pm;
  const w = e[3] * x + e[7] * y + e[11] * z + e[15];
  if (w <= 1e-6) return false;
  out[0] = ((e[0] * x + e[4] * y + e[8] * z + e[12]) / w * 0.5 + 0.5) * S.vw;
  out[1] = (0.5 - (e[1] * x + e[5] * y + e[9] * z + e[13]) / w * 0.5) * S.vh;
  return true;
}
function poolEl(pool, i, cls) {
  let e = pool[i];
  if (!e) { e = el('div', cls); e.append(el('span', 'a'), el('span', 'b')); pool[i] = e; S.labLayer.append(e); }
  return e;
}
function setText(e, a, b, bcls) {
  if (e.__a !== a) { e.firstChild.textContent = a; e.__a = a; }
  if (e.__b !== b) { e.lastChild.textContent = b; e.__b = b; e.lastChild.hidden = !b; }
  if (bcls !== undefined && e.__bc !== bcls) { e.lastChild.className = 'b ' + bcls; e.__bc = bcls; }
}
// write only what changed (labels move every frame while the camera does)
function place(e, tr, fs) {
  if (e.__t !== tr) { e.style.transform = tr; e.__t = tr; }
  if (e.__f !== fs) { e.style.fontSize = fs; e.__f = fs; }
  if (e.hidden) e.hidden = false;
}
const overlaps = (r, used) => { for (const u of used) if (r[0] < u[2] && r[2] > u[0] && r[1] < u[3] && r[3] > u[1]) return true; return false; };
// screen rects labels keep clear of (legend chip, zoom buttons)
function reserve() {
  S.reserved = [];
  for (const e of [S.hud, S.ctl]) if (e && e.offsetWidth) S.reserved.push([e.offsetLeft - 4, e.offsetTop - 4, e.offsetLeft + e.offsetWidth + 4, e.offsetTop + e.offsetHeight + 4]);
}
// stock label candidate: the box's top face is at least 40×18 px on screen and in view → {i, x, y, fs, two, r} | null
function stockCand(i, o, a, c4) {
  const A = S.cur, q = i * STRIDE, cx = A[q], cz = A[q + 1], hw = A[q + 2] / 2, hd = A[q + 3] / 2, h = A[q + 4];
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [dx, dz] of [[-hw, -hd], [hw, -hd], [-hw, hd], [hw, hd]]) {
    if (!proj(cx + dx, h, cz + dz, c4)) return null;
    x0 = Math.min(x0, c4[0]); x1 = Math.max(x1, c4[0]); y0 = Math.min(y0, c4[1]); y1 = Math.max(y1, c4[1]);
  }
  const sw = x1 - x0, sh = y1 - y0, vw = S.vw, vh = S.vh;
  if (sw < 40 || sh < 18 || x1 < 0 || x0 > vw || y1 < 0 || y0 > vh) return null;
  const t = S.tiles[i], name = t.label || '';
  if (!name) return null;
  const fs = Math.min(sw * 0.86 / units(name), sh * 0.5, vw < 560 ? 17 : 22);
  if (fs < 10) return null;
  const two = !!t.sub && sh >= fs * 2.35 && sw * 0.86 >= units(t.sub) * 0.8 * fs;
  if (!proj(cx, h, cz, a)) return null;
  const lw = fs * Math.max(units(name), two ? units(t.sub) * 0.8 : 0), lh = fs * (two ? 2.1 : 1.15);
  const r = [a[0] - lw / 2, a[1] - lh / 2, a[0] + lw / 2, a[1] + lh / 2];
  if (r[0] < 2 || r[2] > vw - 2 || r[1] < 2 || r[3] > vh - 2) return null;
  return { i, x: a[0], y: a[1], fs, two, r, name, sub: t.sub };
}
// is the top-face centre of box i hidden from the camera at o? The ray rises from the anchor, so only boxes taller than box i,
// inside the short stretch of the ray that is still below the tallest box, can be in the way (cheap rejects first).
function occluded(i, o) {
  const A = S.cur, p = i * STRIDE, ax = A[p], ay = A[p + 4] + 0.01, az = A[p + 1];
  const dx = o[0] - ax, dy = o[1] - ay, dz = o[2] - az;
  if (dy <= 0) return false;
  const f = Math.min(1, (S.maxH + 1 - ay) / dy);
  if (f <= 0) return false;
  const ex = ax + dx * f, ez = az + dz * f;
  const x0 = Math.min(ax, ex), x1 = Math.max(ax, ex), z0 = Math.min(az, ez), z1 = Math.max(az, ez);
  const ix = 1 / (dx || 1e-12), iy = 1 / dy, iz = 1 / (dz || 1e-12);
  for (let j = 0; j < S.n; j++) {
    const q = j * STRIDE, h = A[q + 4];
    if (j === i || h <= ay) continue;
    const cx = A[q], cz = A[q + 1], hw = A[q + 2] / 2, hd = A[q + 3] / 2;
    if (cx + hw < x0 || cx - hw > x1 || cz + hd < z0 || cz - hd > z1) continue;
    let t1 = (cx - hw - ax) * ix, t2 = (cx + hw - ax) * ix;
    let tmin = Math.min(t1, t2), tmax = Math.max(t1, t2);
    t1 = -ay * iy; t2 = (h - ay) * iy;
    tmin = Math.max(tmin, Math.min(t1, t2)); tmax = Math.min(tmax, Math.max(t1, t2));
    if (tmax < tmin) continue;
    t1 = (cz - hd - az) * iz; t2 = (cz + hd - az) * iz;
    tmin = Math.max(tmin, Math.min(t1, t2)); tmax = Math.min(tmax, Math.max(t1, t2));
    if (tmax >= tmin && tmax > 1e-4 && tmin < f) return true;
  }
  return false;
}
function updateLabels() {
  if (!S.labLayer || !S.pm) return;
  const W = S.W, H = S.H, vw = S.vw, vh = S.vh, a = [0, 0], b = [0, 0], c4 = [0, 0];
  const used = S.reserved.slice();
  const small = vw < 560;
  const cp = S.camera.position, o = [cp.x, cp.y, cp.z];
  // the largest screen scale anywhere on the map (px per world unit) = at the smallest view depth of its bounding box:
  // boxes that cannot reach 40 × 18 px even there are skipped without projecting them
  const e = S.pm, mv = S.camera.matrixWorldInverse.elements;
  let zmin = Infinity;
  for (const x of [-W / 2, W / 2]) for (const z of [-H / 2, H / 2]) for (const y of [0, S.maxH]) zmin = Math.min(zmin, -(mv[2] * x + mv[6] * y + mv[10] * z + mv[14]));
  const kmax = zmin > 1 ? vh / 2 / (zmin * Math.tan(FOV * DEG / 2)) : Infinity, need = 40 / kmax;
  const cands = [];   // projected only; the occlusion test runs when a candidate is about to be placed
  for (const i of S.order) {
    if (cands.length >= MAX_LABELS * 1.5) break;
    const q = i * STRIDE, w = S.cur[q + 2], d = S.cur[q + 3];
    if (w * d < 150 || w * d * kmax * kmax < 720) break;   // ordered by footprint: the rest are smaller still
    if (Math.max(w, d) < need) continue;
    const c = stockCand(i, o, a, c4);
    if (c) cands.push(c);
  }
  let li = 0;
  const placeStock = c => {
    if (c.done || li >= MAX_LABELS || overlaps(c.r, used)) return;
    c.done = true;
    if (occluded(c.i, o)) return;
    used.push(c.r);
    const e = poolEl(S.labEls, li++, 'm3-lab');
    setText(e, c.name, c.two ? c.sub : '');
    if (e.__k !== S.keys[c.i]) { e.__k = S.keys[c.i]; e.dataset.k = e.__k; }
    place(e, `translate(${c.x.toFixed(1)}px,${c.y.toFixed(1)}px) translate(-50%,-50%)`, c.fs.toFixed(1) + 'px');
  };
  // 1) big stock names (they carry the picture), 2) sector names on the floor at the sector's top-left, 3) the other stocks
  for (const c of cands) if (c.fs >= 15) placeStock(c);
  let si = 0;
  const fsS = small ? 11 : 12.5;
  for (const s of S.sectors) {
    if (!s.label || !s.hd) continue;
    const y = s.y + s.hd / 2 - H / 2;
    if (!proj(s.x + 5 - W / 2, 0.1, y, a) || !proj(s.x + s.w - 5 - W / 2, 0.1, y, b)) continue;
    const span = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const need = fsS * (units(s.label) + (s.sub ? units(s.sub) * 0.85 + 0.6 : 0)) + 14;
    if (span < Math.max(need, small ? 64 : 86)) continue;
    let at = null;
    for (const f of [0, 0.5, 1]) {     // the top-left corner, else further along the header band
      const k = (span - need) / span * f, x = a[0] + (b[0] - a[0]) * k, yy = a[1] + (b[1] - a[1]) * k;
      if (x < -20 || x + need > vw + 20 || yy < 4 || yy > vh - 4) continue;
      const r = [x - 2, yy - fsS * 0.85, x + need, yy + fsS * 0.85];
      if (!overlaps(r, used)) { at = [x, yy, r]; break; }
    }
    if (!at) continue;
    used.push(at[2]);
    const e = poolEl(S.secEls, si++, 'm3-sec');
    setText(e, s.label, s.sub || '', signCls(s.sub));
    place(e, `translate(${at[0].toFixed(1)}px,${(at[1] - fsS * 0.75).toFixed(1)}px)`, fsS + 'px');
  }
  for (let i = si; i < S.secEls.length; i++) if (!S.secEls[i].hidden) S.secEls[i].hidden = true;
  for (const c of cands) placeStock(c);
  for (let i = li; i < S.labEls.length; i++) if (!S.labEls[i].hidden) S.labEls[i].hidden = true;
  S.labelCount = li; S.secCount = si;
}

/* ───────────────── text: legend chip + canvas summary ───────────────── */
function fmtR(v) { const x = Math.abs(v); return String(+(x >= 10 ? x.toFixed(0) : x >= 1 ? x.toFixed(1) : x.toFixed(2))); }
function updateHud() {
  if (!S.hud) return;
  S.hud.replaceChildren(el('b', '', '3D'), el('span', 'm', S.metricPct ? '높이 = 등락 폭' : '높이 = 색 값의 크기'),
    el('span', 's', S.metricPct && S.R ? `±${fmtR(S.R)}%에서 가장 높아요 · 색은 방향` : '색 범위 끝에서 가장 높아요'));
  reserve();
}
function updateAria() {
  if (!S.canvas) return;
  const n = S.n;
  if (!n) { S.canvas.setAttribute('aria-label', '3D 지도. 표시할 종목이 없어요.'); return; }
  let hi = -1, lo = -1, hv = -Infinity, lv = Infinity;
  for (let i = 0; i < n; i++) {
    const v = parsePct(S.tiles[i].sub); if (v == null) continue;
    if (v > hv) { hv = v; hi = i; }
    if (v < lv) { lv = v; lo = i; }
  }
  let s = `3D 지도. ${n}개 종목을 상자로 세웠어요. 높이는 ${S.metricPct ? '등락 폭' : '색 값의 크기'}, 색은 오르내림이에요.`;
  if (hi >= 0 && hv > 0) s += ` 가장 많이 오른 종목은 ${S.tiles[hi].label} ${S.tiles[hi].sub}.`;
  if (lo >= 0 && lv < 0) s += ` 가장 많이 내린 종목은 ${S.tiles[lo].label} ${S.tiles[lo].sub}.`;
  S.canvas.setAttribute('aria-label', s);
}

/* ───────────────── events from the heatmap ───────────────── */
function queueRebuild() {
  if (!S.on || !S.built || S.leaving || S.rebuildQ) return;
  S.rebuildQ = requestAnimationFrame(() => { S.rebuildQ = 0; rebuild(false); });
}
const onData = () => { S.dataTick = true; queueRebuild(); };
const onRender = e => { if (e && e.detail) S.replay = e.detail.replay || null; queueRebuild(); };
function onPalette() { lut = null; queueRebuild(); }
// leaving fancy (or the tab hiding) sends whatever is in flight to its end state
function finishAll() {
  S.inertia = null;
  if (S.tween) { S.tween = null; S.cur = new Float32Array(S.to); }
  S.flashes.clear(); S.fxDirty = true;
  if (S.fly) { const f = S.fly; S.fly = null; S.cam = Object.assign({}, f.to); S.goal = Object.assign({}, f.to); if (f.done) f.done(); }
}
function onVis() {
  if (document.hidden) { stopLoop(); if (S.built) finishAll(); }
  else if (S.on && S.built) { writeInstances(); queueRebuild(); requestRender(); }
}
function onMotion() { TK = null; if (!fancy() && S.built) { finishAll(); if (S.built) { writeInstances(); requestRender(); } } }
const DOC_EVENTS = [['kh:data', onData], ['kh:render', onRender], ['kh:palette', onPalette], ['kh:motion', onMotion], ['visibilitychange', onVis]];

/* ───────────────── public ───────────────── */
async function show() {
  const root = document.getElementById('map3d');
  if (S.leaving) S.leaving.finish();
  if (!root) {
    document.dispatchEvent(new CustomEvent('kh:3d-unavailable', { detail: { reason: 'mount', message: '3D 지도를 보여 줄 자리가 없어요.' } }));
    return false;
  }
  if (S.on && S.root === root) { queueRebuild(); return true; }
  if (S.on || S.built) teardown(false);
  S.on = true;
  const gen = ++S.gen;
  S.root = root;
  root.replaceChildren();
  root.classList.add('m3');
  S.msg = el('div', 'm3-msg'); S.msg.setAttribute('role', 'status');
  root.append(S.msg);
  setMsg('3D 지도를 준비하는 중…', '');
  if (!webglOK()) { fail('webgl'); return false; }
  try { await loadThree(); } catch (e) { if (gen === S.gen && S.on) fail('script'); return false; }
  if (gen !== S.gen || !S.on) return false;
  try {
    TK = null;
    buildScene();
    for (const [n, f] of DOC_EVENTS) document.addEventListener(n, f);
    resize();
    S.userMoved = false; S.cam = null; S.goal = null;
    rebuild(true);
    setTimeout(() => { if (gen === S.gen) hideHint(); }, 6000);
  } catch (e) {
    if (gen === S.gen) fail('init');
    return false;
  }
  return true;
}
function teardown(keepMsg) {
  stopLoop();
  cancelAnimationFrame(S.rebuildQ); S.rebuildQ = 0;
  cancelAnimationFrame(S.hoverQ); S.hoverQ = 0;
  cancelAnimationFrame(S.tipRaf); S.tipRaf = 0;
  clearTimeout(S.tapTimer); S.tapTimer = 0;
  clearTimeout(S.tipHide); S.tipHide = 0;
  for (const [n, f] of DOC_EVENTS) document.removeEventListener(n, f);
  if (S.ro) { S.ro.disconnect(); S.ro = null; }
  if (S.io) { S.io.disconnect(); S.io = null; }
  if (S.canvas) { S.canvas.removeEventListener('webglcontextlost', onLost, false); S.canvas.removeEventListener('webglcontextrestored', onRestored, false); }
  for (const m of [S.mesh, S.plates]) if (m) m.dispose();
  for (const g of [S.boxGeo, S.plateGeo, S.edgeGeo]) if (g) g.dispose();
  for (const m of [S.mat, S.plateMat, S.lineMat]) if (m) m.dispose();
  if (S.renderer) {
    S.renderer.renderLists.dispose();
    S.renderer.dispose();
    S.renderer.forceContextLoss();
  }
  if (S.tip) S.tip.remove();
  if (S.root) {
    if (keepMsg) { for (const x of [...S.root.children]) if (x !== S.msg) x.remove(); }
    else { S.root.replaceChildren(); S.root.classList.remove('m3'); S.msg = null; }
  }
  Object.assign(S, {
    built: false, leaving: null, visible: true, renderer: null, scene: null, camera: null, cam2: null, mesh: null, plates: null, outline: null,
    boxGeo: null, plateGeo: null, edgeGeo: null, mat: null, plateMat: null, lineMat: null, cap: 0, pcap: 0, fx: null,
    canvas: null, labLayer: null, hud: null, ctl: null, hint: null, tip: null, kb: null, labEls: [], secEls: [], reserved: [],
    n: 0, keys: [], tiles: [], sectors: [], W: 0, H: 0, cur: new Float32Array(0), from: new Float32Array(0), to: new Float32Array(0),
    delay: new Float32Array(0), order: [], keyIx: new Map(), tween: null, hover: -1, hoverKey: null, tipFor: null, lastSig: '',
    lastPx: new Map(), dataTick: false, flashes: new Map(), cam: null, goal: null, fly: null, inertia: null, userMoved: false,
    vw: 0, vh: 0, pm: null, drag: null, hinted: false, tipPos: null, tipGoal: null, fxDirty: false,
  });
  S.ptrs.clear();
}
// fancy: fold back to the flat 2D view (360 ms) before freeing the GPU; the promise resolves when #map may be shown again
function hide() {
  S.gen++;
  if (S.leaving) return S.leaving.promise;
  const was = S.on || S.built;
  S.on = false;
  if (!was) { if (S.root && S.root.classList.contains('m3')) teardown(false); return Promise.resolve(); }
  const shown = S.built && S.root && S.root.clientWidth > 0 && !document.hidden && S.cam && S.n;
  if (!(fancy() && shown)) { teardown(false); return Promise.resolve(); }
  let res;
  const promise = new Promise(r => { res = r; });
  const finish = () => { if (S.leaving && S.leaving.promise === promise) { S.on = false; teardown(false); } res(); };
  S.leaving = { promise, finish };
  S.on = true;      // keep the loop alive for the fold
  hideTip(true); setHover(-1);
  const dur = 360, tk = tokens();
  S.from = new Float32Array(S.cur); S.to = new Float32Array(S.cur);
  for (let i = 0; i < S.n; i++) S.to[i * STRIDE + 4] = 0.2;
  S.delay = new Float32Array(S.n);
  S.tween = { start: performance.now(), dur, maxDelay: 0, ease: tk.inout };
  S.fly = { from: Object.assign({}, S.cam), to: topDownPose(), start: performance.now(), dur, ease: tk.inout, done: () => setTimeout(finish, 0) };
  if (S.labLayer) S.labLayer.hidden = true;
  requestRender();
  setTimeout(finish, dur + 250);   // the tab hid mid-fold: finish anyway
  return promise;
}
function stats() {
  const a = S.ft.slice(), n = a.length, sorted = a.slice().sort((x, y) => x - y);
  const avg = n ? a.reduce((s, v) => s + v, 0) / n : 0;
  return {
    frames: n, avgMs: +avg.toFixed(2), p95Ms: n ? +sorted[Math.min(n - 1, Math.floor(n * 0.95))].toFixed(2) : 0, maxMs: n ? +sorted[n - 1].toFixed(2) : 0,
    renderAvgMs: S.ftR.length ? +(S.ftR.reduce((x, y) => x + y, 0) / S.ftR.length).toFixed(2) : 0,
    labelsAvgMs: S.ftL.length ? +(S.ftL.reduce((x, y) => x + y, 0) / S.ftL.length).toFixed(2) : 0,
    last60: a.map(v => +v.toFixed(2)), tier: S.tier, dpr: S.dpr, antialias: S.tier === 'high',
    instances: S.mesh ? S.mesh.count : 0, calls: S.renderer ? S.renderer.info.render.calls : 0, triangles: S.renderer ? S.renderer.info.render.triangles : 0,
  };
}
window.KH3D = {
  show, hide, stats,
  isOn: () => S.on && !S.leaving,
  qa: {
    inspect: () => ({
      on: S.on, built: S.built, three: T ? T.REVISION : null, instances: S.mesh ? S.mesh.count : 0, tiles: S.tiles.length,
      plates: S.plates ? S.plates.count : 0, range: S.R, metricPct: S.metricPct, labels: S.labelCount || 0, sectorLabels: S.secCount || 0,
      maxH: S.maxH, cam: S.cam && Object.assign({}, S.cam), goal: S.goal && Object.assign({}, S.goal), fitDist: S.fitDist,
      tweening: !!S.tween, flying: !!S.fly, flashes: S.flashes.size, canvas: !!S.canvas, frames: S.frames, vw: S.vw, vh: S.vh,
      tier: S.tier, dpr: S.dpr, atHome: atHome(), leaving: !!S.leaving,
    }),
    colors: () => {
      const out = [];
      if (!S.mesh) return out;
      const C = S.mesh.instanceColor.array;
      for (let i = 0; i < S.n; i++) out.push({ k: S.keys[i], tile: S.tiles[i].color, gl: [0, 1, 2].map(k => Math.round(C[i * 3 + k] * 255)), h: +S.cur[i * STRIDE + 4].toFixed(2) });
      return out;
    },
    pick: (x, y) => { const i = pickAt(x, y); return i >= 0 ? S.keys[i] : null; },
    // client px of a box's top-face centre
    anchor: key => {
      const i = S.keyIx.get(key); if (i == null || !S.pm) return null;
      const q = i * STRIDE, p = [0, 0];
      if (!proj(S.cur[q], S.cur[q + 4], S.cur[q + 1], p)) return null;
      const r = S.canvas.getBoundingClientRect();
      return { x: r.left + p[0], y: r.top + p[1] };
    },
    // render now and read WebGL pixels at canvas css px [[x, y], …] (DOM overlays not included)
    pixels: pts => {
      if (!S.built) return [];
      applyCamera(S.camera, S.cam); S.renderer.render(S.scene, S.camera);
      S.pm = S.camera.projectionMatrix.clone().multiply(S.camera.matrixWorldInverse).elements;
      const gl = S.renderer.getContext(), dpr = S.renderer.getPixelRatio(), out = [];
      for (const [x, y] of pts) {
        const px = new Uint8Array(4);
        gl.readPixels(Math.round(x * dpr), Math.round((S.vh - y) * dpr), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
        out.push([px[0], px[1], px[2]]);
      }
      return out;
    },
    view: v => { S.fly = null; S.inertia = null; S.userMoved = true; S.goal = clampPose(Object.assign(S.goal || {}, v || {})); S.cam = Object.assign({}, S.goal); requestRender(); },
    topDown: () => { S.fly = null; S.inertia = null; S.userMoved = true; S.cam = topDownPose(); S.goal = Object.assign({}, S.cam); requestRender(); },
    spin: ms => new Promise(res => {   // continuous camera motion for a frame-time estimate
      const t0 = performance.now(), f0 = S.frames;
      const step = () => {
        const t = performance.now() - t0;
        S.goal.az = Math.sin(t / 600) * 0.6; S.goal.polar = 0.5 + Math.sin(t / 900) * 0.25; S.cam = Object.assign({}, S.goal);
        if (!S.raf) S.raf = requestAnimationFrame(frame);
        if (t < ms) requestAnimationFrame(step);
        else res({ frames: S.frames - f0, ms: t, fps: (S.frames - f0) / (t / 1000), stats: stats() });
      };
      requestAnimationFrame(step);
    }),
  },
};
})();
