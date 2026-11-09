// Minify the live page and bundle the Worker into one file (worker/dist/worker.js) for API upload.
// `wrangler deploy` does its own bundling, so this is only needed when deploying without wrangler.
// usage: node scripts/build_worker.mjs   (after python3 scripts/build_page.py)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../worker/package.json', import.meta.url));
const esbuild = require('esbuild');
const root = new URL('..', import.meta.url).pathname;

const pageMod = readFileSync(root + 'worker/src/page.js', 'utf8');
let html = JSON.parse(pageMod.slice(pageMod.indexOf('export default ') + 15).replace(/;\s*$/, ''));
// minify inline <style> and app <script> (leave the JSON data block alone)
html = html.replace(/<style>([\s\S]*?)<\/style>/g, (_, css) => '<style>' + esbuild.transformSync(css, { loader: 'css', minify: true }).code.trim() + '</style>');
html = html.replace(/<script>([\s\S]*?)<\/script>/g, (_, js) => '<script>' + esbuild.transformSync(js, { loader: 'js', minify: true, target: 'es2020' }).code.trim() + '</script>');
html = html.replace(/>\s+</g, '><').replace(/\n\s*/g, '\n');
mkdirSync(root + 'worker/dist', { recursive: true });
writeFileSync(root + 'worker/dist/page.min.js', 'export default ' + JSON.stringify(html) + ';\n');

await esbuild.build({
  entryPoints: [root + 'worker/src/index.js'],
  bundle: true, format: 'esm', minify: true, target: 'es2022', charset: 'utf8',
  outfile: root + 'worker/dist/worker.js',
  plugins: [{ name: 'minpage', setup(b) { b.onResolve({ filter: /\/page\.js$/ }, () => ({ path: root + 'worker/dist/page.min.js' })); } }],
  legalComments: 'none',
});
console.log('page', html.length, 'chars; worker', readFileSync(root + 'worker/dist/worker.js').length, 'bytes');
