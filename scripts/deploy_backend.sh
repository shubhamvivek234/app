#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8001/health}"
READY_URL="${READY_URL:-http://127.0.0.1:8001/ready}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"

cd "$ROOT_DIR"

echo "[deploy] using compose file: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" up -d --build api worker beat

# Clean up legacy containers from the deprecated compose file if they exist.
for legacy_container in socialentagler-celery-worker-1 socialentagler-celery-beat-1; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$legacy_container"; then
    echo "[deploy] removing legacy container: $legacy_container"
    docker rm -f "$legacy_container" >/dev/null
  fi
done

attempt=1
until curl -fsS "$HEALTH_URL" >/dev/null && curl -fsS "$READY_URL" >/dev/null; do
  if (( attempt >= MAX_ATTEMPTS )); then
    echo "[deploy] health verification failed after $attempt attempts" >&2
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=100 api worker beat >&2 || true
    exit 1
  fi
  echo "[deploy] waiting for api readiness (attempt $attempt/$MAX_ATTEMPTS)"
  sleep "$SLEEP_SECONDS"
  ((attempt+=1))
done

echo "[deploy] health ok"
curl -fsS "$HEALTH_URL"
echo
curl -fsS "$READY_URL"
echo
docker compose -f "$COMPOSE_FILE" ps
