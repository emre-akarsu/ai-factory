#!/bin/bash
# Start the whole stack locally: Postgres, API (:8000), job worker, storefront (:3000).
# Logs and pids go to ${RUN_DIR:-/tmp/ai-factory}.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${RUN_DIR:-/tmp/ai-factory}"; mkdir -p "$RUN"
export FACTORY_DEV_AUTH=1 FACTORY_JOBS=procrastinate PYTHONPATH="$ROOT/packages:$ROOT"
export FACTORY_API_URL=http://localhost:8000 FACTORY_WEB_URL=http://localhost:3000

for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done
(sudo pg_ctlcluster 16 main start 2>/dev/null || pg_ctlcluster 16 main start 2>/dev/null || true)
cd "$ROOT"
.venv/bin/factory migrate
nohup .venv/bin/uvicorn factory.api:app --port 8000 > "$RUN/api.log" 2>&1 & echo $! > "$RUN/api.pid"
nohup .venv/bin/procrastinate --app=factory.worker.app worker > "$RUN/worker.log" 2>&1 & echo $! > "$RUN/worker.pid"
cd apps/web
[ -d .next ] || pnpm build
nohup pnpm start --port 3000 > "$RUN/web.log" 2>&1 & echo $! > "$RUN/web.pid"
for i in $(seq 1 30); do curl -sf localhost:8000/v1/marketplace >/dev/null && curl -sf localhost:3000/ >/dev/null && break; sleep 1; done
echo "API http://localhost:8000/docs  Storefront http://localhost:3000"
