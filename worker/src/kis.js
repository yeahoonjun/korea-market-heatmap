// 한국투자 Open API — 장중 수급 잠정 순위의 원천 (AGENTS §3-40, 사용자 2026-11-16 15:31 "나랑 가족만 볼수있도록").
//
//   토큰   POST /oauth2/tokenP 로 받은 접근 토큰(24시간)을 KV REPLAY `kis:tok`에 두고 다시 써요. 발급은 70초에 한 번까지
//          (`kis:toklock` — 한국투자 발급 한도 1분 1번, 발급마다 사용자에게 알림이 갈 수 있어서 아껴요). 만료 · 무효 응답이면
//          지우고 한 번만 다시 받아요.
//   초대   요청 머리 `X-Panse-Inv: <토큰>` → sha256 → KV `inv:<hex>` = {n:'이름', dev?:1}. 없으면 null. 초대는 Cloudflare API로
//          KV에 직접 쓰고 지워요(관리 경로 없음).
//   확인용 GET /api/kis/raw?path=/uapi/domestic-stock/v1/quotations/…&tr=TRID&<원천 인자…> — dev 초대만, 시세 조회 경로만,
//          {status, cont, msg, j} 그대로(no-store). 개발이 끝나면 dev 초대를 지워 닫아요.
//
// 키(KIS_APP_KEY · KIS_APP_SECRET)와 접근 토큰은 응답 · 로그 어디에도 남지 않아요 — 남기는 글자는 scrub()을 거쳐요.

export const KIS_BASE = 'https://openapi.koreainvestment.com:9443';
const TOK_KEY = 'kis:tok';
const TOK_LOCK = 'kis:toklock';
const RAW_PATHS = ['/uapi/domestic-stock/v1/quotations/', '/uapi/domestic-stock/v1/ranking/'];

const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
export const sha256hex = async s => hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));

export const kisReady = env => !!(env && typeof env.KIS_APP_KEY === 'string' && env.KIS_APP_KEY.length > 8 && typeof env.KIS_APP_SECRET === 'string' && env.KIS_APP_SECRET.length > 8);

export const kisScrub = (s, env, tok) => {
  let t = String(s == null ? '' : s);
  for (const k of [env && env.KIS_APP_KEY, env && env.KIS_APP_SECRET, tok]) if (k && k.length > 8) t = t.split(k).join('***');
  return t.slice(0, 400);
};

export async function inviteOf(request, env) {
  const t = (request.headers.get('x-panse-inv') || '').trim();
  if (!/^[A-Za-z0-9_-]{20,64}$/.test(t) || !env || !env.REPLAY) return null;
  try { return (await env.REPLAY.get('inv:' + await sha256hex(t), 'json')) || null; } catch (e) { return null; }
}

export async function kisToken(env, { fresh = false } = {}) {
  if (!kisReady(env)) throw new Error('kis-no-key');
  if (!fresh) {
    const c = await env.REPLAY.get(TOK_KEY, 'json');
    if (c && c.t && c.exp > Date.now() + 10 * 60e3) return c.t;
  }
  if (await env.REPLAY.get(TOK_LOCK)) throw new Error('kis-token-cooldown');
  await env.REPLAY.put(TOK_LOCK, '1', { expirationTtl: 70 });
  const r = await fetch(KIS_BASE + '/oauth2/tokenP', {
    method: 'POST', headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ grant_type: 'client_credentials', appkey: env.KIS_APP_KEY, appsecret: env.KIS_APP_SECRET }),
  });
  const j = await r.json().catch(() => null);
  if (!r.ok || !j || !j.access_token) {
    throw new Error(kisScrub(`kis-token ${r.status} ${(j && (j.error_code || j.msg_cd)) || ''} ${(j && (j.error_description || j.msg1)) || ''}`, env));
  }
  const exp = Date.now() + (Number(j.expires_in) || 86400) * 1000;
  await env.REPLAY.put(TOK_KEY, JSON.stringify({ t: j.access_token, exp }), { expirationTtl: Math.max(60, Math.floor((exp - Date.now()) / 1000) - 60) });
  return j.access_token;
}

// 시세 조회 하나. 반환 {status, cont, msg, code, j} — j는 원천 JSON 그대로(키 · 토큰은 들어 있지 않아요).
export async function kisGet(env, path, tr, params, { custtype = 'P', timeout = 8000 } = {}) {
  let tok = await kisToken(env);
  for (let attempt = 0; attempt < 2; attempt++) {
    const u = new URL(KIS_BASE + path);
    for (const [k, v] of Object.entries(params || {})) u.searchParams.set(k, String(v));
    const ac = new AbortController(); const tm = setTimeout(() => ac.abort(), timeout);
    let r;
    try {
      r = await fetch(u.toString(), { signal: ac.signal, headers: { 'content-type': 'application/json; charset=utf-8', authorization: 'Bearer ' + tok, appkey: env.KIS_APP_KEY, appsecret: env.KIS_APP_SECRET, tr_id: tr, custtype } });
    } finally { clearTimeout(tm); }
    const text = await r.text();
    let j = null; try { j = JSON.parse(text); } catch (e) {}
    const code = j && (j.msg_cd || j.error_code) || '';
    // 만료 · 무효 토큰(EGW00123 · EGW00121)이면 한 번만 새로 받아요.
    if (attempt === 0 && /EGW0012[13]/.test(code)) { await env.REPLAY.delete(TOK_KEY); tok = await kisToken(env, { fresh: true }); continue; }
    return { status: r.status, cont: r.headers.get('tr_cont') || '', code, msg: kisScrub(j && (j.msg1 || j.error_description) || '', env, tok), j: j || null, text: j ? null : kisScrub(text, env, tok) };
  }
}

export async function kisRawRoute(request, env, url) {
  const inv = await inviteOf(request, env);
  const out = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'access-control-allow-origin': '*' } });
  if (!inv || !inv.dev) return out({ error: 'forbidden' }, 403);
  const path = url.searchParams.get('path') || '';
  const tr = url.searchParams.get('tr') || '';
  if (!RAW_PATHS.some(p => path.startsWith(p)) || !/^[A-Za-z0-9]{6,16}$/.test(tr) || /\.\./.test(path)) return out({ error: 'bad path or tr' }, 400);
  const params = {};
  for (const [k, v] of url.searchParams) if (k !== 'path' && k !== 'tr' && k !== 'custtype') params[k] = v;
  try {
    return out(await kisGet(env, path, tr, params, { custtype: url.searchParams.get('custtype') || 'P' }));
  } catch (e) {
    return out({ error: kisScrub(e && e.message, env) }, 502);
  }
}
