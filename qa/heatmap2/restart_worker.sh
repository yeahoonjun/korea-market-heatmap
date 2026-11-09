#!/bin/sh
# rebuild + restart this worktree's dev Worker (harness) on $HM_PORT (default 8806; it caches index.html for 120 s);
# static assets (ASSET_BASE) on $HM_WEB (default 8807). Only kills the processes on those two ports.
HM_PORT=${HM_PORT:-8806}; HM_WEB=${HM_WEB:-8807}
cd /home/claude/hm-heatmap && python3 scripts/build_page.py 2>&1 | tail -1
for p in $(pgrep -f "worker/dev/serve.mjs"); do if tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q "^PORT=$HM_PORT\$"; then kill $p; fi; done
sleep 0.5
pgrep -f "http.server $HM_WEB" >/dev/null || (nohup python3 -m http.server $HM_WEB -d web > /tmp/hm2_static.log 2>&1 &)
NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:$HM_WEB/ PORT=$HM_PORT nohup node worker/dev/serve.mjs > /tmp/hm2_worker.log 2>&1 &
sleep 1.5; curl -s -o /dev/null -w "worker %{http_code}\n" http://127.0.0.1:$HM_PORT/
