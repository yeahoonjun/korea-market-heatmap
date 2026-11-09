#!/bin/sh
# rebuild + restart the dev Worker on 8798 (it caches index.html for 120 s); static assets (ASSET_BASE) on 8799
cd /home/claude/hm-heatmap && python3 scripts/build_page.py 2>&1 | tail -1
for p in $(pgrep -f "worker/dev/serve.mjs"); do if tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q '^PORT=8798$'; then kill $p; fi; done
sleep 0.5
pgrep -f "http.server 8799" >/dev/null || (nohup python3 -m http.server 8799 -d web > /tmp/hm2_static.log 2>&1 &)
NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8799/ PORT=8798 nohup node worker/dev/serve.mjs > /tmp/hm2_worker.log 2>&1 &
sleep 1.5; curl -s -o /dev/null -w "worker %{http_code}\n" http://127.0.0.1:8798/
