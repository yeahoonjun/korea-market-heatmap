#!/bin/sh
# (re)start this worktree's Worker dev harness on 8812 (its in-memory cache keeps the old index.html for minutes).
# Only the process whose environment says PORT=8812 is stopped.
for p in $(pgrep -f "worker/dev/serve.mjs"); do
  if tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q '^PORT=8812$'; then kill $p; fi
done
sleep 0.5
cd /home/claude/hm-tabs && PORT=8812 NODE_USE_ENV_PROXY=1 ASSET_BASE=http://127.0.0.1:8811/ setsid nohup node worker/dev/serve.mjs > /tmp/tabs-worker.log 2>&1 < /dev/null &
sleep 2
curl -s -o /dev/null -w "worker %{http_code}\n" http://127.0.0.1:8812/
