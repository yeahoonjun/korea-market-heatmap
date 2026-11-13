// Upload worker/dist/worker.js to Cloudflare as the Worker `korea-market-heatmap`, the same way it has been deployed by hand:
// one PUT of the bundled module with the KV binding from worker/wrangler.toml, keeping the secrets (DART_KEY) that live only
// in Cloudflare. The cron triggers are not part of a script upload and stay as they are.
//
//   node scripts/build_worker.mjs && node scripts/deploy_worker.mjs
//
// env  CLOUDFLARE_API_TOKEN  (required; Account › Workers Scripts › Edit)   — never written to a file or printed
//      CF_ACCOUNT_ID         (default: the 판세 account)
//      DRY_RUN=1             build the request and print it, send nothing
//
// Safety: skips the upload when Cloudflare already runs the same bundle; after an upload, checks /api/time on the new
// version and, if it doesn't answer, puts the previous version back at 100 % and fails (GitHub then e-mails the owner).
//
// Durable Objects (실시간 갱신 hub, docs/standards/realtime.md §6): wrangler.toml [[durable_objects.bindings]] and
// [exports.<Class>] go into the upload metadata (`bindings` + declarative `exports`, the same PUT wrangler itself uses when a
// Worker declares DO exports). An upload that would CREATE a class (its namespace) cannot be rolled back past, so it is never
// done on a push: it needs ALLOW_DO_LIFECYCLE=1 (workflow_dispatch input allow_do_lifecycle) and then skips the automatic
// rollback. /api/live/state is checked after the upload as a warning only (realtime is optional; pages fall back to polling).
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const root = new URL('..', import.meta.url).pathname;
const SCRIPT = 'korea-market-heatmap';
const ACCOUNT = process.env.CF_ACCOUNT_ID || '208b73dfa7035e48419d0415fad8d8fa';
const SMOKE = 'https://korea-market-heatmap.ssslot.workers.dev/api/time';
const TOKEN = process.env.CLOUDFLARE_API_TOKEN || '';
const DRY = process.env.DRY_RUN === '1';
const API = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/workers/scripts/${SCRIPT}`;

const log = (...a) => console.log(...a);
const fail = (msg) => { console.log(`::error::${msg}`); process.exit(1); };

// ── what to upload ──────────────────────────────────────────────────────────────────────────────────────────────────
const code = readFileSync(root + 'worker/dist/worker.js', 'utf8');
const sha = s => createHash('sha256').update(s).digest('hex');
const toml = readFileSync(root + 'worker/wrangler.toml', 'utf8');
const tomlName = (toml.match(/^name\s*=\s*"([^"]+)"/m) || [])[1];
if (tomlName !== SCRIPT) fail(`wrangler.toml name is ${tomlName}, expected ${SCRIPT}`);
const compat = (toml.match(/^compatibility_date\s*=\s*"([^"]+)"/m) || [])[1];
if (!compat) fail('compatibility_date missing from wrangler.toml');
const kv = [...toml.matchAll(/\[\[kv_namespaces\]\][^[]*?binding\s*=\s*"([^"]+)"[^[]*?id\s*=\s*"([0-9a-f]{32})"/g)]
  .map(m => ({ type: 'kv_namespace', name: m[1], namespace_id: m[2] }));
if (!kv.some(b => b.name === 'REPLAY')) fail('the REPLAY KV binding is missing from wrangler.toml');
const dos = [...toml.matchAll(/\[\[durable_objects\.bindings\]\][^[]*?\bname\s*=\s*"([^"]+)"[^[]*?\bclass_name\s*=\s*"([^"]+)"/g)]
  .map(m => ({ type: 'durable_object_namespace', name: m[1], class_name: m[2] }));
const doExports = {};
for (const m of toml.matchAll(/^\[exports\.([A-Za-z_$][\w$]*)\][ \t]*\n((?:(?!\[)[^\n]*(?:\n|$))*)/gm)) {
  const val = k => (m[2].match(new RegExp(`^${k}\\s*=\\s*"([^"]+)"`, 'm')) || [])[1];
  const type = val('type'), storage = val('storage'), state = val('state');
  if (type !== 'durable-object') continue;
  // live entry (state absent / "created") → {type, storage}; a tombstone ("deleted" …) goes up as written
  doExports[m[1]] = !state || state === 'created' ? { type, storage: storage || 'sqlite' } : { type, state };
}
const liveClass = c => !doExports[c].state;
for (const b of dos) if (!doExports[b.class_name] || !liveClass(b.class_name)) fail(`Durable Object binding ${b.name} → ${b.class_name} needs a live [exports.${b.class_name}] block in wrangler.toml`);
// esbuild writes `export class X` as `var X=class{…}` — accept both spellings
const hasClass = (src, c) => new RegExp(`\\bclass ${c}\\b|\\b${c}\\s*=\\s*class\\b`).test(src);
for (const c of Object.keys(doExports)) {
  if (liveClass(c) && !hasClass(code, c)) fail(`[exports.${c}] is declared but worker/dist/worker.js has no class ${c}`);
  if (!liveClass(c) && hasClass(code, c)) fail(`[exports.${c}] is a ${doExports[c].state} tombstone but worker/dist/worker.js still has class ${c}`);
}
const metadata = { main_module: 'worker.js', compatibility_date: compat, bindings: [...kv, ...dos],
  ...(Object.keys(doExports).length ? { exports: doExports } : {}), keep_bindings: ['secret_text'] };
const ALLOW_LIFECYCLE = process.env.ALLOW_DO_LIFECYCLE === '1';

log(`bundle  worker/dist/worker.js  ${code.length} bytes  sha256 ${sha(code)}`);
log(`meta    ${JSON.stringify(metadata)}`);
if (DRY) { log('DRY_RUN=1 — nothing sent'); process.exit(0); }
if (!TOKEN) { console.log('::warning::CLOUDFLARE_API_TOKEN is not set — skipped the Worker upload (add it under Settings › Secrets and variables › Actions)'); process.exit(0); }

// ── Cloudflare API ──────────────────────────────────────────────────────────────────────────────────────────────────
async function cf(path, init = {}) {
  const r = await fetch(API + path, { ...init, headers: { authorization: `Bearer ${TOKEN}`, ...(init.headers || {}) } });
  return r;
}
async function cfJson(path, init) {
  const r = await cf(path, init);
  let j = null; try { j = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok || !j || j.success === false) {
    const errs = j && j.errors ? j.errors.map(e => `${e.code} ${e.message}`).join('; ') : `http ${r.status}`;
    if (j) log(`response ${r.status} cf-ray ${r.headers.get('cf-ray') || '-'}: ${JSON.stringify({ errors: j.errors, messages: j.messages })}`.slice(0, 2000));
    fail(`${init && init.method || 'GET'} ${path || '/'}: ${errs}`);
  }
  return j.result;
}
async function deployedVersions() {
  const res = await cfJson('/deployments');
  const list = (res && res.deployments) || [];
  return list.length ? list[0].versions || [] : [];
}
async function liveCode() {
  // the stored module, as a multipart body; read the first file part
  try {
    const r = await cf('/content/v2');
    if (!r.ok) return null;
    const ct = r.headers.get('content-type') || '';
    if (/multipart\/form-data/i.test(ct)) {
      const fd = await new Response(await r.arrayBuffer(), { headers: { 'content-type': ct } }).formData();
      for (const [, v] of fd) if (typeof v === 'object' && v && typeof v.text === 'function') return await v.text();
      return null;
    }
    return await r.text();
  } catch (e) { return null; }
}
async function smoke() {
  for (let i = 0; i < 8; i++) {
    await new Promise(r => setTimeout(r, i ? 4000 : 2500));
    try {
      const r = await fetch(`${SMOKE}?deploy=${Date.now()}`, { headers: { 'cache-control': 'no-cache' } });
      const j = r.ok ? await r.json() : null;
      if (j && Number.isFinite(j.t)) { log(`smoke   ${SMOKE} → 200 {t:${j.t}}`); return true; }
      log(`smoke   try ${i + 1}: http ${r.status}`);
    } catch (e) { log(`smoke   try ${i + 1}: ${e.message}`); }
  }
  return false;
}

// cron triggers live beside the script, not in it: make them match wrangler.toml (the 1-minute replay recorder, §3-15)
const crons = ((toml.match(/^crons\s*=\s*\[([^\]]*)\]/m) || [])[1] || '').match(/"[^"]+"/g)?.map(s => s.slice(1, -1)) || [];
async function ensureCrons() {
  if (!crons.length) return;
  const res = await cfJson('/schedules');
  const have = ((res && res.schedules) || []).map(s => s.cron).sort();
  log(`cron    ${have.join(', ') || '(none)'}`);
  if (JSON.stringify(have) === JSON.stringify([...crons].sort())) return;
  await cfJson('/schedules', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(crons.map(cron => ({ cron }))) });
  console.log(`::warning::cron triggers were ${have.join(', ') || 'missing'}; set to ${crons.join(', ')} from wrangler.toml`);
}

// ── run ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
await ensureCrons();
const before = await deployedVersions();
log(`live    ${before.map(v => `${v.version_id} ${v.percentage}%`).join(', ') || '(none)'}`);
const now = await liveCode();
if (now != null && sha(now) === sha(code)) { log('same bundle is already live — nothing to upload'); process.exit(0); }
// DO class lifecycle changes (Cloudflare cannot roll back past them): a live class the running bundle does not have yet
// (= create; unknown live code counts as new), or a tombstone whose class the running bundle still has (= delete/rename)
const newClasses = Object.keys(doExports).filter(c => liveClass(c) ? !(now != null && hasClass(now, c)) : (now == null || hasClass(now, c)));
if (newClasses.length) {
  if (!ALLOW_LIFECYCLE) {
    console.log(`::warning::this upload changes the Durable Object class ${newClasses.join(', ')} (create / delete) — Cloudflare cannot roll back past that, so it is not done on a push and NOTHING was uploaded. Run the workflow by hand with allow_do_lifecycle (docs/standards/realtime.md §13).`);
    process.exit(0);
  }
  log(`do      lifecycle change for ${newClasses.join(', ')} (ALLOW_DO_LIFECYCLE=1) — no automatic rollback for this upload`);
}

const form = new FormData();
form.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
form.append('worker.js', new Blob([code], { type: 'application/javascript+module' }), 'worker.js');
await cfJson('', { method: 'PUT', body: form });
const after = await deployedVersions();
log(`uploaded; live now ${after.map(v => `${v.version_id} ${v.percentage}%`).join(', ')}`);

async function smokeLive() {
  if (!dos.length) return;
  try {
    const r = await fetch(SMOKE.replace('/api/time', '/api/live/state') + `?deploy=${Date.now()}`, { headers: { 'cache-control': 'no-cache' } });
    const j = r.ok ? await r.json() : null;
    if (j && j.guard) log(`live    /api/live/state → 200 (sockets ${j.sockets}, DO requests today ${j.guard.doRequests.today}/${j.guard.doRequests.dayLimit}, trip ${j.guard.trip ? j.guard.trip.why : 'none'})`);
    else console.log(`::warning::/api/live/state answered ${r.status} — realtime is off, pages keep polling`);
  } catch (e) { console.log(`::warning::/api/live/state: ${e.message} — realtime is off, pages keep polling`); }
}
if (await smoke()) { await smokeLive(); log('deployed'); process.exit(0); }
if (newClasses.length) fail(`the new version did not answer ${SMOKE}, and it created ${newClasses.join(', ')}: Cloudflare cannot roll back past a Durable Object class creation — fix forward (keep the class and its [exports] block)`);

const prev = before.find(v => v.percentage === 100) || before[0];
if (prev) {
  await cfJson('/deployments', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ strategy: 'percentage', versions: [{ version_id: prev.version_id, percentage: 100 }] }) });
  fail(`the new version did not answer ${SMOKE}; rolled back to ${prev.version_id}`);
}
fail(`the new version did not answer ${SMOKE} and there was no earlier version to roll back to`);
