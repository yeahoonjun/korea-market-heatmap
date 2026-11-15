// 한국수출입은행 Open API 확인용 (AGENTS §3-27 끝, 사용자 2026-11-15 20:12 "그래 그렇게하면 되겠네" — 월요일 실제 호출로
// 갱신 시각 · 내용을 확인한 뒤 쓰임을 정해요). 화면은 아직 이 경로를 쓰지 않아요.
// GET /api/koreaexim/probe[?d=YYYYMMDD] → {asOf, date, fx:{…}, rate:{…}} — 키는 응답 · KV · 로그 어디에도 남지 않아요.
// 원천 1번 = 환율 exchangeJSON(data=AP01, KOREAEXIM_FX_KEY) + 국제금리 internationalJSON(data=AP03, KOREAEXIM_RATE_KEY).
// 같은 날짜는 KV `kxim:probe:<날짜>`에 10분, 하루 원천 호출은 KV `kxim:calls:<오늘>`로 60번까지만(넘으면 마지막 값).
const BASE = 'https://oapi.koreaexim.go.kr/site/program/financial/';
const APIS = { fx: { path: 'exchangeJSON', data: 'AP01', key: 'KOREAEXIM_FX_KEY' }, rate: { path: 'internationalJSON', data: 'AP03', key: 'KOREAEXIM_RATE_KEY' } };
const TTL = 600, DAY_MAX = 60;
const RESULT = { 1: '성공', 2: 'DATA 코드 오류', 3: '인증 코드 오류', 4: '하루 한도 초과' };

const kstDay = (ms = Date.now()) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'access-control-allow-origin': 'https://panse.pages.dev' },
});
const scrub = (s, secrets) => { let t = String(s); for (const k of secrets) if (k) t = t.split(k).join('***').split(encodeURIComponent(k)).join('***'); return t; };

async function one(env, api, date, secrets) {
  const key = env[api.key];
  if (!key) return { ok: false, error: 'no key' };
  const url = `${BASE}${api.path}?authkey=${encodeURIComponent(key)}&searchdate=${date}&data=${api.data}`;
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 8000), t0 = Date.now();
  try {
    const r = await fetch(url, { signal: ac.signal, headers: { 'user-agent': 'PanseBot/1.0 (+https://panse.pages.dev)', accept: 'application/json' } });
    const text = await r.text();
    const out = { http: r.status, ms: Date.now() - t0, bytes: text.length };
    let rows;
    try { rows = JSON.parse(text); } catch (e) { return { ok: false, ...out, error: 'JSON 아님', head: scrub(text.slice(0, 160), secrets) }; }
    if (!Array.isArray(rows)) return { ok: false, ...out, error: '배열 아님', head: scrub(JSON.stringify(rows).slice(0, 160), secrets) };
    const codes = [...new Set(rows.map(x => x && x.result))];
    return {
      ok: r.ok && rows.length > 0 && codes.every(c => c === 1), ...out, n: rows.length,
      result: codes.map(c => `${c} ${RESULT[c] || ''}`.trim()),
      fields: rows[0] ? Object.keys(rows[0]) : [],
      rows: rows.slice(0, 40),   // 환율 23개 안팎 · 국제금리 몇 줄 — 값만, 키 없음
    };
  } catch (e) {
    return { ok: false, error: e && e.name === 'AbortError' ? '시간 초과(8초)' : scrub((e && e.message) || e, secrets) };
  } finally { clearTimeout(t); }
}

export async function koreaeximRoute(request, env, ctx, url) {
  if (request.method !== 'GET') return json({ error: 'GET으로만 받을 수 있어요' }, 405);
  const d = url.searchParams.get('d');
  if (d && !/^\d{8}$/.test(d)) return json({ error: 'd는 YYYYMMDD' }, 400);
  const date = d || kstDay(), today = kstDay();
  const kv = env.REPLAY, cKey = `kxim:probe:${date}`, nKey = `kxim:calls:${today}`;
  const secrets = Object.values(APIS).map(a => env[a.key]).filter(Boolean);
  if (kv) {
    const hit = await kv.get(cKey, 'json').catch(() => null);
    if (hit && Date.now() - hit.at < TTL * 1000) return json({ ...hit.body, cached: true });
  }
  const used = kv ? +(await kv.get(nKey).catch(() => null)) || 0 : 0;
  if (used >= DAY_MAX) return json({ error: `오늘 확인 한도(${DAY_MAX}번)를 다 썼어요` }, 429);
  const [fx, rate] = await Promise.all([one(env, APIS.fx, date, secrets), one(env, APIS.rate, date, secrets)]);
  const body = { asOf: new Date().toISOString(), date, fx, rate };
  if (kv) {
    const w = [kv.put(nKey, String(used + 2), { expirationTtl: 2 * 86400 })];
    if (fx.ok || rate.ok) w.push(kv.put(cKey, JSON.stringify({ at: Date.now(), body }), { expirationTtl: TTL }));
    ctx.waitUntil(Promise.all(w).catch(() => {}));
  }
  return json(body);
}
