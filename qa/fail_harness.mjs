// QA-only harness on :8790 — serves the live page and a controllable /api/quotes to test failure/empty/closed states.
import http from 'node:http';
import { readFileSync } from 'node:fs';
const pageNow = () => readFileSync('/home/claude/heatmap/web/index.html', 'utf8');
let mode = 'ok';
let cached = null;
async function real(path) { const r = await fetch('http://127.0.0.1:8788' + path); return [r.status, await r.text()]; }
http.createServer(async (req, res) => {
  const u = req.url;
  if (u.startsWith('/__mode/')) { mode = u.slice(8); res.end('mode=' + mode); return; }
  if (u === '/' || u.startsWith('/#')) { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); res.end(pageNow()); return; }
  if (u.startsWith('/api/quotes')) {
    if (mode === 'err') { res.writeHead(502, { 'content-type': 'application/json' }); res.end('{"error":"naver 500"}'); return; }
    if (mode === 'empty') { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify({ asOf: '', marketStatus: {}, index: {}, stocks: [] })); return; }
    if (mode === 'hang') return; // never answer
    const [st, body] = await real('/api/quotes');
    let j = JSON.parse(body);
    if (mode === 'holiday') { j.marketStatus = { KOSPI: 'CLOSE', KOSDAQ: 'CLOSE' }; j.afterHours = false; j.asOf = '2026-11-06T20:00:00+09:00'; }
    if (mode === 'open') { j.marketStatus = { KOSPI: 'OPEN', KOSDAQ: 'OPEN' }; j.afterHours = false; }
    res.writeHead(st, { 'content-type': 'application/json' }); res.end(JSON.stringify(j)); return;
  }
  if (u.startsWith('/api/chart/')) {
    if (mode === 'err' || mode === 'charterr') { res.writeHead(502); res.end('{"error":"x"}'); return; }
    const [st, body] = await real(u); res.writeHead(st, { 'content-type': 'application/json' }); res.end(body); return;
  }
  res.writeHead(404); res.end('nf');
}).listen(8790, () => console.log('qa harness 8790'));
