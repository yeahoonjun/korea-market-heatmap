// scripts/deploy_worker.mjs 점검 — Cloudflare API를 흉내 내서(진짜 토큰·네트워크 없이) DO 클래스가 생기는 배포의 안전장치를 확인해요
// (docs/standards/realtime.md §13). worker/dist/worker.js가 먼저 있어야 해요: node scripts/build_worker.mjs
//   node qa/worker/test_deploy_script.mjs
import { spawnSync } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync, existsSync, mkdirSync, copyFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ROOT = new URL('../../', import.meta.url).pathname;
if (!existsSync(ROOT + 'worker/dist/worker.js')) { console.log('build first: node scripts/build_worker.mjs'); process.exit(2); }
const dir = mkdtempSync(join(tmpdir(), 'deploytest-'));
const bundle = readFileSync(ROOT + 'worker/dist/worker.js', 'utf8');
// a preload that replaces fetch: records every call, answers like the Cloudflare API / the deployed Worker would
const preload = join(dir, 'cfmock.mjs');
writeFileSync(preload, `
import { appendFileSync, readFileSync } from 'node:fs';
const S = JSON.parse(process.env.CFMOCK);
const rec = x => appendFileSync(S.log, JSON.stringify(x) + '\\n');
const ok = result => new Response(JSON.stringify({ success: true, result }), { headers: { 'content-type': 'application/json' } });
const err = () => new Response(JSON.stringify({ success: false, errors: [{ code: 10000, message: 'mock outage' }] }), { status: 500 });
globalThis.fetch = async (url, init = {}) => {
  url = String(url); const method = init.method || 'GET';
  if (url.includes('api.cloudflare.com')) {
    const path = url.replace(/^.*\\/workers\\/scripts\\/korea-market-heatmap/, '');
    if (path === '/schedules') return ok({ schedules: [{ cron: '* 0-7 * * 2-6' }] });
    if (path === '/deployments' && method === 'GET') return ok({ deployments: [{ versions: [{ version_id: 'v-old', percentage: 100 }] }] });
    if (path === '/deployments' && method === 'POST') { rec({ rollback: true }); return ok({}); }
    if (path === '/content/v2') return S.liveFile ? new Response(readFileSync(S.liveFile, 'utf8')) : new Response('oops', { status: 500 });
    if (path === '/settings') { rec({ settings: true }); return S.bindings ? ok({ bindings: S.bindings, compatibility_date: '2025-09-01' }) : err(); }
    if (path === '' && method === 'PUT') {
      const fd = await new Response(init.body).formData();
      rec({ upload: JSON.parse(await fd.get('metadata').text()) });
      return ok({});
    }
    return new Response('{}', { status: 404 });
  }
  if (url.includes('/api/time')) return S.smokeOk ? new Response(JSON.stringify({ t: Date.now() })) : new Response('x', { status: 500 });
  if (url.includes('/api/live/state')) return new Response(JSON.stringify({ sockets: 0, guard: { doRequests: { today: 1, dayLimit: 20000 }, trip: null } }));
  return new Response('?', { status: 404 });
};
`);
const liveNew = join(dir, 'live-new.js'), liveSame = join(dir, 'live-same.js');
writeFileSync(liveNew, bundle + '\n//changed');                            // the running Worker: different code
writeFileSync(liveSame, bundle);
const TOML = readFileSync(ROOT + 'worker/wrangler.toml', 'utf8');
// a throwaway copy of the repo bits the script reads, so a test can use its own wrangler.toml
let trees = 0;
function tree(toml = TOML) {
  const t = join(dir, `tree${++trees}`);
  mkdirSync(join(t, 'scripts'), { recursive: true }); mkdirSync(join(t, 'worker/dist'), { recursive: true });
  copyFileSync(ROOT + 'scripts/deploy_worker.mjs', join(t, 'scripts/deploy_worker.mjs'));
  writeFileSync(join(t, 'worker/wrangler.toml'), toml);
  writeFileSync(join(t, 'worker/dist/worker.js'), bundle);
  return t;
}
const REPLAY = { type: 'kv_namespace', name: 'REPLAY', namespace_id: 'x' }, SECRET = { type: 'secret_text', name: 'DART_KEY' };
const HUB = { type: 'durable_object_namespace', name: 'MARKET', class_name: 'MarketHub', namespace_id: 'ns1' };
const BEFORE = [REPLAY, SECRET], AFTER = [REPLAY, SECRET, HUB];

let pass = 0, fail = 0;
function run(name, { live = liveNew, bindings = AFTER, allow = false, smokeOk = true, toml }, check) {
  const log = join(dir, name.replace(/\W+/g, '_').slice(0, 60) + '.jsonl'), summary = log + '.md';
  writeFileSync(log, ''); writeFileSync(summary, '');
  const root = toml ? tree(toml) : ROOT;
  const r = spawnSync(process.execPath, ['--import', preload, root + (root.endsWith('/') ? '' : '/') + 'scripts/deploy_worker.mjs'], {
    env: { ...process.env, CLOUDFLARE_API_TOKEN: 'test-token-not-real', GITHUB_STEP_SUMMARY: summary, CFMOCK: JSON.stringify({ log, liveFile: live, bindings, smokeOk }), ALLOW_DO_LIFECYCLE: allow ? '1' : '' },
    encoding: 'utf8', timeout: 120000,
  });
  const calls = readFileSync(log, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
  const out = (r.stdout || '') + (r.stderr || '');
  let good = false, why = '';
  try { good = check({ code: r.status, out, calls, summary: readFileSync(summary, 'utf8') }); } catch (e) { why = e.message; }
  if (good) { pass++; console.log('  ok  ', name); } else { fail++; console.log('  FAIL', name, why, '\n', out.slice(-800)); }
}
const upload = calls => calls.find(c => c.upload);
console.log('creating the hub (the running Worker has no MarketHub binding)');
run('push → nothing uploaded, a titled ::warning:: + job summary telling to run with allow_do_lifecycle, exit 0', { bindings: BEFORE },
  ({ code, out, calls, summary }) => code === 0 && !upload(calls) && /::warning title=Worker NOT deployed::.*MarketHub \(create\).*allow_do_lifecycle/.test(out) && /Worker NOT deployed/.test(summary));
run('hand run with allow_do_lifecycle → upload carries MARKET binding + exports, smoke + /api/live/state', { bindings: BEFORE, allow: true },
  ({ code, out, calls }) => { const m = upload(calls).upload; return code === 0 && m.bindings.some(b => b.type === 'durable_object_namespace' && b.name === 'MARKET' && b.class_name === 'MarketHub') && m.exports.MarketHub.storage === 'sqlite' && m.keep_bindings[0] === 'secret_text' && /live    \/api\/live\/state → 200/.test(out); });
run('creating deploy whose smoke fails → fails WITHOUT trying a rollback (Cloudflare refuses it)', { bindings: BEFORE, allow: true, smokeOk: false },
  ({ code, out, calls }) => code === 1 && !calls.some(c => c.rollback) && /fix forward/.test(out));
console.log('after the hub exists (the running Worker binds MARKET → MarketHub)');
run('later push → normal upload, no opt-in needed', {},
  ({ code, calls }) => code === 0 && !!upload(calls));
run('same bundle already live → nothing uploaded, exit 0', { live: liveSame },
  ({ code, calls }) => code === 0 && !upload(calls));
run('ordinary deploy whose smoke fails → rolls back as before', { smokeOk: false },
  ({ code, calls }) => code === 1 && calls.some(c => c.rollback));
console.log('Cloudflare cannot tell us → fail, never guess (review 2026-11-14)');
run('running bundle unreadable (/content/v2 500) while a version is live → exit 1, nothing uploaded', { live: null },
  ({ code, out, calls }) => code === 1 && !upload(calls) && /content\/v2/.test(out));
run('settings unreadable (500) → exit 1, nothing uploaded', { bindings: null },
  ({ code, out, calls }) => code === 1 && !upload(calls) && /settings/.test(out));
run('settings without the REPLAY binding (not a real answer) → exit 1', { bindings: [] },
  ({ code, out, calls }) => code === 1 && !upload(calls) && /REPLAY missing/.test(out));
run('running Worker binds a class wrangler.toml does not mention → exit 1', { bindings: [...AFTER, { type: 'durable_object_namespace', name: 'X', class_name: 'Stray' }] },
  ({ code, out, calls }) => code === 1 && !upload(calls) && /Stray/.test(out));
console.log('tombstones');
const renamed = TOML + '\n[exports.OldHub]\ntype = "durable-object"\nstate = "renamed"\nrenamed_to = "MarketHub"\n';
const OLD = { type: 'durable_object_namespace', name: 'MARKET', class_name: 'OldHub', namespace_id: 'ns1' };
run('state = "renamed" without renamed_to → refused before any API call', { toml: TOML + '\n[exports.OldHub]\ntype = "durable-object"\nstate = "renamed"\n' },
  ({ code, out, calls }) => code === 1 && calls.length === 0 && /needs renamed_to/.test(out));
run('state = "transferred" → refused locally (not supported here)', { toml: TOML + '\n[exports.OldHub]\ntype = "durable-object"\nstate = "transferred"\n' },
  ({ code, out, calls }) => code === 1 && calls.length === 0 && /only "created", "deleted" or "renamed"/.test(out));
run('rename OldHub → MarketHub on a push → lifecycle warning, nothing uploaded', { toml: renamed, bindings: [REPLAY, OLD] },
  ({ code, out, calls }) => code === 0 && !upload(calls) && /OldHub \(rename → MarketHub\)/.test(out));
run('rename with allow_do_lifecycle → exports carry {state: renamed, renamed_to}', { toml: renamed, bindings: [REPLAY, OLD], allow: true },
  ({ code, calls }) => { const m = upload(calls) && upload(calls).upload; return code === 0 && m && m.exports.OldHub.state === 'renamed' && m.exports.OldHub.renamed_to === 'MarketHub' && m.exports.MarketHub.storage === 'sqlite'; });
run('a deleted tombstone already gone from the running Worker → ordinary upload', { toml: TOML + '\n[exports.Gone]\ntype = "durable-object"\nstate = "deleted"\n' },
  ({ code, calls }) => { const m = upload(calls) && upload(calls).upload; return code === 0 && m && m.exports.Gone.state === 'deleted'; });
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
