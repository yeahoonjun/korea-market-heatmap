// Pages project `kospimap` (old address, 2026-11-09 ~ 11-13) → 판세 (https://panse.pages.dev). AGENTS §3-26.
// Screens get a tiny page that carries this browser's khm.* settings and 관심종목 to the new address
// in the URL fragment (never sent to a server), then replaces the location. /api/* and /data/* keep
// working for tabs that are still open on the old address. Everything else moves with a 301.
const NEW = 'https://panse.pages.dev';

const BRIDGE = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>판세로 옮겼어요</title>
<style>html,body{margin:0;background:#131418;color:#eef0f3;font:16px/1.6 'Pretendard Variable',Pretendard,system-ui,sans-serif}
main{max-width:420px;margin:0 auto;padding:56px 24px}h1{font-size:20px;margin:0 0 8px}p{margin:0 0 16px;color:#bcc0c8}
a{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:12px;background:#ffb547;color:#1b1404;font-weight:700;text-decoration:none}</style>
</head><body><main><h1>주소가 판세로 바뀌었어요</h1>
<p>관심종목과 설정을 가지고 panse.pages.dev로 옮기는 중이에요.</p>
<a id="go" href="${NEW}/">판세 열기</a></main>
<script>(function(){var keep=location.hash.replace(/^#/,''),o={},n=0;
try{for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);if(k&&k.indexOf('khm.')===0){o[k]=localStorage.getItem(k);n++;}}}catch(e){}
var to='${NEW}/'+location.search;
if(n){try{to+='#khm-import='+encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(o)))))+(keep?'~'+keep:'');}catch(e){to+=keep?'#'+keep:'';}}
else if(keep)to+='#'+keep;
document.getElementById('go').href=to;location.replace(to);})();</script>
</body></html>`;

const NOOP_SW = "self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const p = url.pathname;
    if (p.startsWith('/api/') || p.startsWith('/data/')) return env.API.fetch(request);
    if (p === '/sw.js') return new Response(NOOP_SW, { headers: { 'content-type': 'application/javascript; charset=utf-8', 'cache-control': 'no-store' } });
    const html = (request.headers.get('accept') || '').includes('text/html');
    if (request.method === 'GET' && (p === '/' || p === '/index.html' || html)) {
      return new Response(BRIDGE, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex' } });
    }
    return Response.redirect(NEW + p + url.search, 301);
  },
};
