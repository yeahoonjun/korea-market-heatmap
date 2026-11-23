// 가족 보기 초대 (AGENTS §3-40 계약 "초대", 사용자 2026-11-16 15:31 "나랑 가족만 볼수있도록").
//
//   GET    /api/inv/me     초대 → {n, own}                        기기가 저장한 토큰을 확인해요
//   GET    /api/inv        own만 → {items:[{id, n, at, own?}]}   id = 해시 앞 12자, dev 초대는 목록에 나오지 않아요
//   POST   /api/inv {n}    own만 → {id, token}                    이름 1~12자, 토큰(base64url 32자)은 이 응답에서 한 번만
//   DELETE /api/inv/{id}   own만 → {ok:true}                      자기 자신 · 마지막 own은 끌 수 없어요(409)
//
// KV REPLAY: `inv:<sha256 hex>` = {n, own?:1, dev?:1, at:'YYYY-MM-DD'} (초대 확인은 이것만 봐요).
// 목록은 칸 스무 개 `inv:s:0` … `inv:s:19` = {h, n, at, own?} — 하나의 목록 키를 읽고 고쳐 쓰지 않아서 겹친 만들기 · 끄기가
// 서로의 줄을 지우지 않아요(2026-11-23 독립 리뷰 ⑪). 만들기는 빈 칸 하나를 골라 쓰고 다시 읽어 확인(같은 칸에 겹치면 다른
// 칸으로), 끄기는 그 칸만 지워요. 목록을 읽을 때 기록이 없어진 칸은 지워요(스스로 고침). 옛 목록 `inv:index`가 있으면 처음
// 한 번 칸으로 옮기고 지워요. 칸이 하나도 없으면 부른 own이 첫 칸이에요. KV list는 쓰지 않아요.
// KV를 읽지 못하면 503 {error:'unavailable'} — "초대 없음"(403)과 구분해요(403이면 화면이 토큰을 지워요).
// 모두 `cache-control: private, no-store`. 초대가 없거나 틀리면 403 {error:'forbidden'}(무엇이 틀렸는지 말하지 않아요).

import { sha256hex, inviteRecord } from './kis.js';

const OLD_IDX = 'inv:index', SLOTS = 20;
const slotKey = k => `inv:s:${k}`;
const HEX64 = /^[0-9a-f]{64}$/;
const out = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'private, no-store' } });
const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
class Unavailable extends Error { constructor() { super('unavailable'); this.status = 503; } }

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

async function kvGet(env, key, type) {
  for (let i = 0; i < 2; i++) { try { return await env.REPLAY.get(key, type); } catch (e) { /* 한 번 더 */ } }
  throw new Unavailable();
}
const okEntry = e => e && typeof e === 'object' && typeof e.h === 'string' && HEX64.test(e.h);

// 칸 스무 개 → [{k, e}] (빈 칸은 e = null). 옛 목록이 있으면 먼저 칸으로 옮겨요(한 번).
async function slots(env) {
  const got = await Promise.all(Array.from({ length: SLOTS }, (_, k) => kvGet(env, slotKey(k), 'json')));
  const list = got.map((e, k) => ({ k, e: okEntry(e) ? e : null }));
  const old = await kvGet(env, OLD_IDX, 'json');
  if (Array.isArray(old)) {
    for (const e of old) {
      if (!okEntry(e) || list.some(x => x.e && x.e.h === e.h)) continue;
      const free = list.find(x => !x.e);
      if (!free) break;
      free.e = { h: e.h, n: String(e.n || ''), at: e.at || null, ...(e.own ? { own: 1 } : {}) };
      await env.REPLAY.put(slotKey(free.k), JSON.stringify(free.e));
    }
    await env.REPLAY.delete(OLD_IDX);
  }
  return list;
}
// 빈 칸 하나에 쓰고 다시 읽어 확인 — 다른 요청이 같은 칸을 먼저 가졌으면 다른 칸으로(세 번까지)
async function claim(env, list, entry) {
  for (let tries = 0; tries < 3; tries++) {
    const free = list.filter(x => !x.e);
    if (!free.length) return false;
    const pick = free[Math.floor(Math.random() * free.length)];
    const cur = await kvGet(env, slotKey(pick.k), 'json');
    if (okEntry(cur)) { pick.e = cur; continue; }
    await env.REPLAY.put(slotKey(pick.k), JSON.stringify(entry));
    const back = await kvGet(env, slotKey(pick.k), 'json');
    if (back && back.h === entry.h) { pick.e = entry; return true; }
    pick.e = okEntry(back) ? back : entry;
  }
  return false;
}
// 목록 = 칸들, 기록이 없어진 칸은 지우고(스스로 고침), own인데 목록에 없으면 더해요. dev는 넣지 않아요.
async function index(env, me, { heal = false } = {}) {
  const list = await slots(env);
  if (heal) {
    const recs = await Promise.all(list.map(x => (x.e ? kvGet(env, 'inv:' + x.e.h, 'json') : null)));
    for (let i = 0; i < list.length; i++) {
      if (list[i].e && !recs[i] && list[i].e.h !== me.h) { await env.REPLAY.delete(slotKey(list[i].k)); list[i].e = null; }
    }
  }
  if (me.rec.own && !me.rec.dev && !list.some(x => x.e && x.e.h === me.h)) {
    await claim(env, list, { h: me.h, n: String(me.rec.n || '나'), at: me.rec.at || today(), own: 1 });
  }
  return list;
}
const entries = list => list.filter(x => x.e).sort((a, b) => String(a.e.at || '').localeCompare(String(b.e.at || '')) || (b.e.own ? 1 : 0) - (a.e.own ? 1 : 0) || a.k - b.k);
const item = e => ({ id: e.h.slice(0, 12), n: e.n, at: e.at || null, ...(e.own ? { own: true } : {}) });

export async function invRoute(request, env, url) {
  env = env || {};
  try {
    return await route(request, env, url);
  } catch (e) {
    if (e && e.status === 503) return out({ error: 'unavailable' }, 503);
    throw e;
  }
}

async function route(request, env, url) {
  const me = await inviteRecord(request, env);                 // KV 오류면 503(위에서)
  if (!me) return out({ error: 'forbidden' }, 403);
  const path = url.pathname, method = request.method;
  if (path === '/api/inv/me') {
    if (method !== 'GET') return out({ error: 'GET만 돼요' }, 405);
    return out({ n: String(me.rec.n || ''), own: !!me.rec.own });
  }
  if (!me.rec.own) return out({ error: 'forbidden' }, 403);
  if (path === '/api/inv') {
    if (method === 'GET') return out({ items: entries(await index(env, me, { heal: true })).map(x => item(x.e)) });
    if (method !== 'POST') return out({ error: 'GET · POST만 돼요' }, 405);
    const raw = await request.text().catch(() => '');
    if (raw.length > 2048) return out({ error: '보낸 내용이 너무 길어요' }, 413);
    let b = null;
    try { b = JSON.parse(raw); } catch (e) { b = null; }
    const n = cleanName(b && b.n);
    if (!n) return out({ error: '이름은 1~12자로 적어 주세요' }, 400);
    const list = await index(env, me);
    if (!list.some(x => !x.e)) return out({ error: `초대는 ${SLOTS}개까지 만들 수 있어요` }, 409);
    const token = newToken(), h = await sha256hex(token), at = today();
    await env.REPLAY.put('inv:' + h, JSON.stringify({ n, at }));
    if (!(await claim(env, list, { h, n, at }))) {               // 칸을 못 가졌으면 기록도 되돌려요(목록에 없는 초대가 남지 않게)
      await env.REPLAY.delete('inv:' + h);
      return out({ error: `초대는 ${SLOTS}개까지 만들 수 있어요` }, 409);
    }
    return out({ id: h.slice(0, 12), token });
  }
  const m = path.match(/^\/api\/inv\/([^/]+)$/);
  if (!m) return out({ error: '없는 경로예요' }, 404);
  if (method !== 'DELETE') return out({ error: 'DELETE만 돼요' }, 405);
  const id = m[1];
  if (!/^[0-9a-f]{12}$/.test(id)) return out({ error: 'id가 올바르지 않아요' }, 400);
  const list = await index(env, me);
  const hit = list.filter(x => x.e && x.e.h.startsWith(id));
  if (hit.length !== 1) return out({ error: '없는 초대예요' }, 404);
  const t = hit[0].e;
  if (t.h === me.h) return out({ error: '지금 이 기기의 초대는 끌 수 없어요' }, 409);
  if (t.own && list.filter(x => x.e && x.e.own).length <= 1) return out({ error: '마지막 관리 초대는 끌 수 없어요' }, 409);
  await env.REPLAY.delete('inv:' + t.h);
  await env.REPLAY.delete(slotKey(hit[0].k));
  return out({ ok: true });
}
