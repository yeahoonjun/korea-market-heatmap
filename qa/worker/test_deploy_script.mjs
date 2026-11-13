// scripts/deploy_worker.mjs 점검 — Cloudflare API를 흉내 내서(진짜 토큰·네트워크 없이) DO 클래스가 생기는 배포의 안전장치를 확인해요
// (docs/standards/realtime.md §13). worker/dist/worker.js가 먼저 있어야 해요: node scripts/build_worker.mjs
//   node qa/worker/test_deploy_script.mjs
import { spawnSync } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync, existsSync } from 'node:fs';
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
globalThis.fetch = async (url, init = {}) => {
  url = String(url); const method = init.method || 'GET';
  if (url.includes('api.cloudflare.com')) {
    const path = url.replace(/^.*\\/workers\\/scripts\\/korea-market-heatmap/, '');
    if (path === '/schedules') return ok({ schedules: [{ cron: '* 0-7 * * 2-6' }] });
    if (path === '/deployments' && method === 'GET') return ok({ deployments: [{ versions: [{ version_id: 'v-old', percentage: 100 }] }] });
    if (path === '/deployments' && method === 'POST') { rec({ rollback: true }); return ok({}); }
    if (path === '/content/v2') return new Response(readFileSync(S.liveFile, 'utf8'));
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
const liveOld = join(dir, 'live-old.js'), liveNew = join(dir, 'live-new.js');
writeFileSync(liveOld, bundle.replace(/MarketHub/g, 'SomethingElse'));     // the running Worker before the hub
writeFileSync(liveNew, bundle + '\n//changed');                            // a later deploy: the hub already exists, code differs

let pass = 0, fail = 0;
function run(name, { live, allow, smokeOk = true }, check) {
  const log = join(dir, name.replace(/\W+/g, '_') + '.jsonl');
  writeFileSync(log, '');
  const r = spawnSync(process.execPath, ['--import', preload, ROOT + 'scripts/deploy_worker.mjs'], {
    env: { ...process.env, CLOUDFLARE_API_TOKEN: 'test-token-not-real', CFMOCK: JSON.stringify({ log, liveFile: live, smokeOk }), ...(allow ? { ALLOW_DO_LIFECYCLE: '1' } : { ALLOW_DO_LIFECYCLE: '' }) },
    encoding: 'utf8', timeout: 120000,
  });
  const calls = readFileSync(log, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
  const out = (r.stdout || '') + (r.stderr || '');
  let good = false, why = '';
  try { good = check({ code: r.status, out, calls }); } catch (e) { why = e.message; }
  if (good) { pass++; console.log('  ok  ', name); } else { fail++; console.log('  FAIL', name, why, '\n', out.slice(-800)); }
}
const upload = calls => calls.find(c => c.upload);
run('push, hub not created yet → nothing uploaded, warning, exit 0', { live: liveOld, allow: false },
  ({ code, out, calls }) => code === 0 && !upload(calls) && /NOTHING was uploaded/.test(out));
run('hand run with allow_do_lifecycle → upload carries MARKET binding + exports, smoke + /api/live/state', { live: liveOld, allow: true },
  ({ code, out, calls }) => { const m = upload(calls).upload; return code === 0 && m.bindings.some(b => b.type === 'durable_object_namespace' && b.name === 'MARKET' && b.class_name === 'MarketHub') && m.exports.MarketHub.storage === 'sqlite' && m.keep_bindings[0] === 'secret_text' && /live    \/api\/live\/state → 200/.test(out); });
run('later push (hub exists) → normal upload, no opt-in needed', { live: liveNew, allow: false },
  ({ code, calls }) => code === 0 && !!upload(calls));
run('creating deploy whose smoke fails → fails WITHOUT trying a rollback (Cloudflare refuses it)', { live: liveOld, allow: true, smokeOk: false },
  ({ code, out, calls }) => code === 1 && !calls.some(c => c.rollback) && /fix forward/.test(out));
run('ordinary deploy whose smoke fails → rolls back as before', { live: liveNew, allow: false, smokeOk: false },
  ({ code, calls }) => code === 1 && calls.some(c => c.rollback));
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
