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
// Worker declares DO exports). An upload that would CREATE, DELETE or RENAME a class cannot be rolled back past, so it is never
// done on a push: it needs ALLOW_DO_LIFECYCLE=1 (workflow_dispatch input allow_do_lifecycle) and then skips the automatic
// rollback. Whether a class exists is read from the running Worker's bindings (GET …/settings), never guessed from its code;
// if Cloudflare cannot tell us (settings or the running bundle unreadable while versions exist) the deploy FAILS instead of
// guessing. /api/live/state is checked after the upload as a warning only (realtime is optional; pages fall back to polling).
import { readFileSync, appendFileSync } from 'node:fs';
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
  const type = val('type'), storage = val('storage'), state = val('state'), renamedTo = val('renamed_to');
  if (type !== 'durable-object') continue;
  if (!state || state === 'created') doExports[m[1]] = { type, storage: storage || 'sqlite' };          // live class
  else if (state === 'deleted') doExports[m[1]] = { type, state };                                       // tombstone: data goes
  else if (state === 'renamed') {                                                                        // tombstone: data moves
    if (!renamedTo) fail(`[exports.${m[1]}] state = "renamed" needs renamed_to = "<NewClass>"`);
    doExports[m[1]] = { type, state, renamed_to: renamedTo };
  } else fail(`[exports.${m[1]}] has state = "${state}" — only "created", "deleted" or "renamed" (with renamed_to) are understood here`);
}
const liveClass = c => !!doExports[c] && !doExports[c].state;
for (const [c, e] of Object.entries(doExports)) if (e.state === 'renamed' && !liveClass(e.renamed_to)) fail(`[exports.${c}] is renamed to ${e.renamed_to}, which needs its own live [exports.${e.renamed_to}] block`);
for (const b of dos) if (!liveClass(b.class_name)) fail(`Durable Object binding ${b.name} → ${b.class_name} needs a live [exports.${b.class_name}] block in wrangler.toml`);
// every live class is bound: the running Worker's bindings are how this script tells which classes already exist
for (const c of Object.keys(doExports)) if (liveClass(c) && !dos.some(b => b.class_name === c)) fail(`[exports.${c}] is live but no [[durable_objects.bindings]] uses it — bind it (this script reads existing classes from the running bindings)`);
// esbuild writes `export class X` as `var X=class{…}` — accept both spellings (only our own bundle is checked this way)
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
  // the stored module, as a multipart body; read the first file part (null = Cloudflare did not give it to us)
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
// the Durable Object classes the running Worker has, from its own bindings (cfJson fails the deploy if this cannot be read)
async function liveClasses() {
  const res = await cfJson('/settings');
  const b = res && Array.isArray(res.bindings) ? res.bindings : null;
  if (!b || !b.some(x => x.type === 'kv_namespace' && x.name === 'REPLAY')) fail('GET /settings did not return the running bindings (REPLAY missing) — cannot tell which Durable Object classes exist; nothing uploaded');
  return new Set(b.filter(x => x.type === 'durable_object_namespace' && x.class_name && (!x.script_name || x.script_name === SCRIPT)).map(x => x.class_name));
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
if (now == null && before.length) fail('Cloudflare runs a version but GET /content/v2 did not return its bundle — cannot compare; nothing uploaded (try again, or run by hand)');
if (now != null && sha(now) === sha(code)) { log('same bundle is already live — nothing to upload'); process.exit(0); }
// DO class lifecycle changes (Cloudflare cannot roll back past them), decided from the running bindings:
//   create = a live [exports] class the running Worker does not bind; delete/rename = a tombstone whose class it still binds
const have = await liveClasses();
log(`do      running classes: ${[...have].join(', ') || '(none)'}`);
for (const c of have) if (!doExports[c]) fail(`the running Worker binds Durable Object class ${c} but wrangler.toml has no [exports.${c}] (live or tombstone) — refusing an upload that would drop it`);
const lifecycle = Object.keys(doExports).filter(c => liveClass(c) ? !have.has(c) : have.has(c));
if (lifecycle.length) {
  const what = lifecycle.map(c => `${c} (${liveClass(c) ? 'create' : doExports[c].state === 'renamed' ? `rename → ${doExports[c].renamed_to}` : 'delete'})`).join(', ');
  if (!ALLOW_LIFECYCLE) {
    const msg = `this upload changes Durable Object classes: ${what}. Cloudflare cannot roll back past that, so it is never done on a push and NOTHING was uploaded (the running Worker is unchanged). Run "deploy-worker" by hand (Actions › deploy-worker › Run workflow) with allow_do_lifecycle checked — docs/standards/realtime.md §13.`;
    console.log(`::warning title=Worker NOT deployed::${msg}`);
    if (process.env.GITHUB_STEP_SUMMARY) { try { appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### Worker NOT deployed\n\n${msg}\n`); } catch (e) { /* summary is optional */ } }
    process.exit(0);
  }
  log(`do      lifecycle change: ${what} (ALLOW_DO_LIFECYCLE=1) — no automatic rollback for this upload`);
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
if (lifecycle.length) fail(`the new version did not answer ${SMOKE}, and it changed Durable Object classes (${lifecycle.join(', ')}): Cloudflare cannot roll back past that — fix forward (keep the classes and their [exports] blocks as uploaded)`);

const prev = before.find(v => v.percentage === 100) || before[0];
if (prev) {
  await cfJson('/deployments', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ strategy: 'percentage', versions: [{ version_id: prev.version_id, percentage: 100 }] }) });
  fail(`the new version did not answer ${SMOKE}; rolled back to ${prev.version_id}`);
}
fail(`the new version did not answer ${SMOKE} and there was no earlier version to roll back to`);
