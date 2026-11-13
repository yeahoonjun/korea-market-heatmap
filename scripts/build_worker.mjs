// Bundle the Worker into one file (worker/dist/worker.js) for uploading through the Cloudflare API.
// `wrangler deploy` bundles by itself; use this only when deploying without wrangler.
// usage: node scripts/build_worker.mjs
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../worker/package.json', import.meta.url));
const esbuild = require('esbuild');
const root = new URL('..', import.meta.url).pathname;
await esbuild.build({
  entryPoints: [root + 'worker/src/index.js'],
  bundle: true, format: 'esm', target: 'es2022', charset: 'utf8', legalComments: 'none',
  minifyWhitespace: true, minifySyntax: true,       // identifiers stay readable
  external: ['cloudflare:*'],                        // runtime modules (cloudflare:workers …) resolve on Cloudflare, not in the bundle
  outfile: root + 'worker/dist/worker.js',
});
console.log('worker/dist/worker.js', readFileSync(root + 'worker/dist/worker.js').length, 'bytes');
