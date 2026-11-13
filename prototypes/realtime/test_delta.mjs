// Delta rules check (realtime.md §5-3): applyPatch(old, diffRow(old, new, slow)) must give back `new` on a slow tick, and
// exactly the FAST keys of `new` (+ the SLOW keys of `old`) on a fast tick — on real /api/quotes rows mutated at random.
//   node prototypes/realtime/test_delta.mjs [quotes.json]      (default: fetch the public /api/quotes once)
import { readFileSync } from 'node:fs';

// worker.js imports 'cloudflare:workers' and an .html module: load just the pure functions from its source text
const src = readFileSync(new URL('./src/worker.js', import.meta.url), 'utf8');
const pick = name => src.slice(src.indexOf(`export function ${name}`), src.indexOf('\n}\n', src.indexOf(`export function ${name}`)) + 2).replace('export ', '');
const consts = src.match(/^const (FAST|SLOW|NX_FAST|NX_SLOW) = .*$/gm).join('\n');
const { diffRow, applyPatch } = new Function(`${consts}\n${pick('diffRow')}\n${pick('applyPatch')}\nreturn { diffRow, applyPatch };`)();

const file = process.argv[2];
const body = file ? JSON.parse(readFileSync(file, 'utf8')) : await (await fetch('https://korea-market-heatmap.ssslot.workers.dev/api/quotes')).json();
const rows = body.stocks;
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const FAST = ['p', 'd', 'r', 'lim', 'op', 'hi', 'lo'], SLOW = ['cap', 'tv', 'v'], NXF = ['p', 'd', 'r', 's', 'o', 'op', 'hi', 'lo'], NXS = ['v', 'tv', 't'];
function mutate(o) {
  const n = structuredClone(o);
  for (const k of [...FAST, ...SLOW]) if (rnd() < 0.3) { if (rnd() < 0.1) delete n[k]; else n[k] = Math.round((n[k] || 1000) * (1 + (rnd() - 0.5) / 50)); }
  if (rnd() < 0.05) delete n.nx;
  else if (n.nx) { for (const k of [...NXF, ...NXS]) if (rnd() < 0.3) { if (rnd() < 0.1) delete n.nx[k]; else n.nx[k] = typeof n.nx[k] === 'string' ? n.nx[k] + 'x' : Math.round((n.nx[k] || 1000) * (1 + (rnd() - 0.5) / 50)); } }
  else if (rnd() < 0.1) n.nx = { p: n.p, d: n.d, r: n.r, s: 'reg', o: 1, t: 'T', v: 1, tv: 1 };
  return n;
}
const eq = (a, b) => JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b));
const sortKeys = x => x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map(k => [k, sortKeys(x[k])])) : x;
let fails = 0, n = 0, empty = 0;
for (let round = 0; round < 20; round++) for (const o of rows) {
  const nw = mutate(o);
  // slow tick: exact
  const a = applyPatch(structuredClone(o), diffRow(o, nw, true) || { c: o.c });
  if (!eq(a, nw)) { fails++; if (fails < 4) console.log('slow mismatch', o.c, JSON.stringify(diffRow(o, nw, true))); }
  // fast tick: FAST (and NX_FAST) from new, SLOW (and NX_SLOW) from old — unless NXT appeared/vanished (then nx is whole)
  const p = diffRow(o, nw, false);
  if (!p) empty++;
  const b = applyPatch(structuredClone(o), p || { c: o.c });
  const want = structuredClone(o);
  for (const k of FAST) { if (k in nw) want[k] = nw[k]; else delete want[k]; }
  if (!o.nx || !nw.nx) { if (nw.nx) want.nx = structuredClone(nw.nx); else delete want.nx; }
  else for (const k of NXF) { if (k in nw.nx) want.nx[k] = nw.nx[k]; else delete want.nx[k]; }
  if (!eq(b, want)) { fails++; if (fails < 4) console.log('fast mismatch', o.c, JSON.stringify(p)); }
  n++;
}
console.log(`${n} row pairs, ${empty} without a fast change, ${fails} mismatches`);
process.exit(fails ? 1 : 0);
