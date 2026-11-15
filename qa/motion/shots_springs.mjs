#!/usr/bin/env node
/* 스프링 시안 스크린샷 → qa/shots/springs/ (서버 없이 file://).
 *   node qa/motion/shots_springs.mjs
 * frames-1440.png · frames-390.png = drafts/springs.html?frames=1 전체 페이지, page-*.png = 보통 보기 첫 화면.
 */
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'qa/shots/springs');
mkdirSync(OUT, { recursive: true });
const require = createRequire(import.meta.url);
let pw; for (const p of ['playwright', '/opt/npm-tools/node_modules/playwright']) { try { pw = require(p); break; } catch (e) { } }
const browser = await pw.chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const url = pathToFileURL(join(ROOT, 'drafts/springs.html')).href;
const res = [];
try {
  for (const [w, hgt, mobile] of [[1440, 900, false], [390, 844, true]]) {
    for (const [q, name, full] of [['?frames=1', 'frames', true], ['', 'page', false]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile });
      const page = await ctx.newPage();
      const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
      await page.goto(url + q);
      await page.waitForFunction(() => window.__ready === true, null, { timeout: 15000 });
      await page.waitForTimeout(150);
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth, h: document.documentElement.scrollHeight }));
      const file = join(OUT, `${name}-${w}.png`);
      await page.screenshot({ path: file, fullPage: full });
      res.push({ file: file.replace(ROOT + '/', ''), overflow: m.sw - m.iw, height: m.h, errors: errs.length });
      await ctx.close();
    }
  }
} finally { await browser.close(); }
console.table(res);
if (res.some(r => r.overflow > 0 || r.errors)) process.exit(1);
