// 가족 보기 초대 (AGENTS §3-40 계약 "초대", 사용자 2026-11-16 15:31 "나랑 가족만 볼수있도록").
//
//   GET    /api/inv/me     초대 → {n, own}                        기기가 저장한 토큰을 확인해요
//   GET    /api/inv        own만 → {items:[{id, n, at, own?}]}   id = 해시 앞 12자, dev 초대는 목록에 나오지 않아요
//   POST   /api/inv {n}    own만 → {id, token}                    이름 1~12자, 토큰(base64url 32자)은 이 응답에서 한 번만
//   DELETE /api/inv/{id}   own만 → {ok:true}                      자기 자신 · 마지막 own은 끌 수 없어요(409)
//
// KV REPLAY: `inv:<sha256 hex>` = {n, own?:1, dev?:1, at:'YYYY-MM-DD'}, 목록 `inv:index` = [{h, n, at, own?}](최대 20, KV list 안 씀).
// 목록이 아직 없으면 그걸 부른 own의 기록 하나로 만들어요. 서버는 토큰을 저장하지 않아요 — 해시만.
// 모두 `cache-control: private, no-store`. 초대가 없거나 틀리면 403 {error:'forbidden'}(무엇이 틀렸는지 말하지 않아요).

import { sha256hex } from './kis.js';

const IDX = 'inv:index', MAX = 20, TOK_RE = /^[A-Za-z0-9_-]{20,64}$/;
const out = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'private, no-store' } });
const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

export function newToken() {
  const b = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
// 이름: 앞뒤 공백 정리, 1~12자(한글 한 글자 = 1자), 제어 문자 없음
export function cleanName(n) {
  if (typeof n !== 'string') return null;
  const t = n.replace(/\s+/g, ' ').trim();
  const len = [...t].length;
  if (len < 1 || len > 12 || /[\u0000-\u001f\u007f<>]/.test(t)) return null;
  return t;
}

async function who(request, env) {
  const t = (request.headers.get('x-panse-inv') || '').trim();
  if (!TOK_RE.test(t) || !env || !env.REPLAY) return null;
  const h = await sha256hex(t);
  let rec = null;
  try { rec = await env.REPLAY.get('inv:' + h, 'json'); } catch (e) { rec = null; }
  return rec && typeof rec === 'object' ? { h, rec } : null;
}

// 목록 읽기 — 없으면(처음) 부른 own 하나로 만들어 써요. own인데 목록에 없으면 더해요. dev는 넣지 않아요.
async function index(env, me) {
  let idx = null;
  try { idx = await env.REPLAY.get(IDX, 'json'); } catch (e) { idx = null; }
  let list = Array.isArray(idx) ? idx.filter(e => e && typeof e.h === 'string' && /^[0-9a-f]{64}$/.test(e.h)) : [];
  if (me.rec.own && !me.rec.dev && !list.some(e => e.h === me.h)) {
    list = [{ h: me.h, n: String(me.rec.n || '나'), at: me.rec.at || today(), own: 1 }, ...list].slice(0, MAX);
    await env.REPLAY.put(IDX, JSON.stringify(list));
  }
  return list;
}
const item = e => ({ id: e.h.slice(0, 12), n: e.n, at: e.at || null, ...(e.own ? { own: true } : {}) });

export async function invRoute(request, env, url) {
  env = env || {};
  const me = await who(request, env);
  if (!me) return out({ error: 'forbidden' }, 403);
  const path = url.pathname, method = request.method;
  if (path === '/api/inv/me') {
    if (method !== 'GET') return out({ error: 'GET만 돼요' }, 405);
    return out({ n: String(me.rec.n || ''), own: !!me.rec.own });
  }
  if (!me.rec.own) return out({ error: 'forbidden' }, 403);
  if (path === '/api/inv') {
    if (method === 'GET') return out({ items: (await index(env, me)).map(item) });
    if (method !== 'POST') return out({ error: 'GET · POST만 돼요' }, 405);
    const raw = await request.text().catch(() => '');
    if (raw.length > 2048) return out({ error: '보낸 내용이 너무 길어요' }, 413);
    let b = null;
    try { b = JSON.parse(raw); } catch (e) { b = null; }
    const n = cleanName(b && b.n);
    if (!n) return out({ error: '이름은 1~12자로 적어 주세요' }, 400);
    const list = await index(env, me);
    if (list.length >= MAX) return out({ error: `초대는 ${MAX}개까지 만들 수 있어요` }, 409);
    const token = newToken(), h = await sha256hex(token), at = today();
    await env.REPLAY.put('inv:' + h, JSON.stringify({ n, at }));
    await env.REPLAY.put(IDX, JSON.stringify([...list, { h, n, at }]));
    return out({ id: h.slice(0, 12), token });
  }
  const m = path.match(/^\/api\/inv\/([^/]+)$/);
  if (!m) return out({ error: '없는 경로예요' }, 404);
  if (method !== 'DELETE') return out({ error: 'DELETE만 돼요' }, 405);
  const id = m[1];
  if (!/^[0-9a-f]{12}$/.test(id)) return out({ error: 'id가 올바르지 않아요' }, 400);
  const list = await index(env, me);
  const hit = list.filter(e => e.h.startsWith(id));
  if (hit.length !== 1) return out({ error: '없는 초대예요' }, 404);
  const t = hit[0];
  if (t.h === me.h) return out({ error: '지금 이 기기의 초대는 끌 수 없어요' }, 409);
  if (t.own && list.filter(e => e.own).length <= 1) return out({ error: '마지막 관리 초대는 끌 수 없어요' }, 409);
  await env.REPLAY.delete('inv:' + t.h);
  await env.REPLAY.put(IDX, JSON.stringify(list.filter(e => e.h !== t.h)));
  return out({ ok: true });
}
