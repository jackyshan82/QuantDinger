#!/usr/bin/env bash
# Manage the complete local stack, including strategy runtimes and Codex.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Container startup deliberately restores .env to mode 0600 under UID 10001.
# Use WSL's root management entry so every Compose call can read it, even
# after migration/startup tightens the mode again. Do not copy secrets or
# weaken the entrypoint's file permissions.
if [[ $EUID -ne 0 && -n "${WSL_DISTRO_NAME:-}" ]]; then
  exec /mnt/c/Windows/System32/wsl.exe --distribution "$WSL_DISTRO_NAME" \
    --user root --exec /bin/bash "$ROOT/scripts/local-stack.sh" "$@"
fi
if [[ ! -r "$ROOT/.env" ]]; then
  echo "Cannot read $ROOT/.env; run this script with sudo on this host." >&2
  exit 1
fi
compose=(docker compose --project-directory "$ROOT"
  -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.codex.yml")
services=(postgres redis redis-jobs kafka codex-bridge backend
  trading-worker strategy-dispatcher-worker strategy-evaluator-worker
  kafka-audit-worker scheduler-worker celery-worker celery-beat frontend mobile)

check_stack() {
  local service container state
  for service in "${services[@]}"; do
    container=$("${compose[@]}" ps --all --quiet "$service")
    if [[ -z "$container" ]]; then
      echo "Missing service: $service" >&2
      return 1
    fi
    state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container")
    echo "$service: $state"
    case "$state" in
      'running healthy'|'running no-healthcheck') ;;
      *) return 1 ;;
    esac
  done
  "${compose[@]}" exec -T codex-bridge python - <<'PY'
import os
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:8765/health",
    headers={"Authorization": "Bearer " + os.environ["CODEX_BRIDGE_TOKEN"]},
)
with urllib.request.urlopen(request, timeout=10) as response:
    assert response.status == 200
print("Codex bridge: authenticated health check passed")
PY
  "${compose[@]}" exec -T celery-worker python - <<'PY'
from app.celery_app import celery_app

replies = celery_app.control.inspect(timeout=5).active_queues() or {}
queues = {queue["name"] for rows in replies.values() for queue in rows}
assert {"jobs", "ai", "maintenance"} <= queues, "Required Celery queues are unavailable"
print("Celery worker: jobs, ai and maintenance queues responding")
PY
}

action=${1:-up}
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [up|check|status|stop|validate]" >&2
  exit 2
fi
case "$action" in
  up)
    "${compose[@]}" config --quiet
    "${compose[@]}" up -d --no-build --no-recreate --pull missing \
      --wait --wait-timeout 180 "${services[@]}"
    check_stack
    ;;
  check) check_stack ;;
  status) "${compose[@]}" ps --all "${services[@]}" ;;
  stop) "${compose[@]}" stop "${services[@]}" ;;
  validate) "${compose[@]}" config --quiet ;;
  *) echo "Usage: $0 [up|check|status|stop|validate]" >&2; exit 2 ;;
esac
