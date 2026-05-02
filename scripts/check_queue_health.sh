#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

cd "$ROOT_DIR"

echo "[queue] compose file: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" ps
echo

echo "[queue] redis memory"
docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli info memory | grep -E 'used_memory_human|maxmemory_human|maxmemory_policy'
echo

echo "[queue] queue lengths (redis db 2)"
for queue in high_priority default media_processing dead_letter celery; do
  length="$(docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli -n 2 LLEN "$queue" | tr -d '\r')"
  printf '  %-18s %s\n' "$queue" "$length"
done
echo

echo "[queue] worker ping"
docker compose -f "$COMPOSE_FILE" exec -T worker celery -A celery_workers.celery_app inspect ping
