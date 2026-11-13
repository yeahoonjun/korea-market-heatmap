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
const metadata = { main_module: 'worker.js', compatibility_date: compat, bindings: kv, keep_bindings: ['secret_text'] };

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
  // Cloudflare may hand an expression back in another spelling (MON-FRI ↔ 2-6): compare a normalised form
  const DOW = { SUN: 1, MON: 2, TUE: 3, WED: 4, THU: 5, FRI: 6, SAT: 7 };
  const norm = c => c.trim().toUpperCase().split(/\s+/).map((f, i) => i === 4 ? f.replace(/[A-Z]{3}/g, m => DOW[m] || m) : f).join(' ');
  if (JSON.stringify(have.map(norm).sort()) === JSON.stringify(crons.map(norm).sort())) return;
  await cfJson('/schedules', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(crons.map(cron => ({ cron }))) });
  console.log(`::warning::cron triggers were ${have.join(', ') || 'missing'}; set to ${crons.join(', ')} from wrangler.toml`);
}

// ── run ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
await ensureCrons();
const before = await deployedVersions();
log(`live    ${before.map(v => `${v.version_id} ${v.percentage}%`).join(', ') || '(none)'}`);
const now = await liveCode();
if (now != null && sha(now) === sha(code)) { log('same bundle is already live — nothing to upload'); process.exit(0); }

const form = new FormData();
form.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
form.append('worker.js', new Blob([code], { type: 'application/javascript+module' }), 'worker.js');
await cfJson('', { method: 'PUT', body: form });
const after = await deployedVersions();
log(`uploaded; live now ${after.map(v => `${v.version_id} ${v.percentage}%`).join(', ')}`);

if (await smoke()) { log('deployed'); process.exit(0); }

const prev = before.find(v => v.percentage === 100) || before[0];
if (prev) {
  await cfJson('/deployments', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ strategy: 'percentage', versions: [{ version_id: prev.version_id, percentage: 100 }] }) });
  fail(`the new version did not answer ${SMOKE}; rolled back to ${prev.version_id}`);
}
fail(`the new version did not answer ${SMOKE} and there was no earlier version to roll back to`);
