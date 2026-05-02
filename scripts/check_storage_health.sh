#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

cd "$ROOT_DIR"

echo "[storage] validating active storage backend inside api container"
docker compose -f "$COMPOSE_FILE" exec -T api python - <<'PY'
from utils.storage import get_storage_backend, validate_storage_backend

backend = get_storage_backend()
try:
    info = validate_storage_backend()
    print(f"[storage] ok backend={info['backend']} bucket={info['bucket']}")
except Exception as exc:
    if backend == "r2":
        raise
    print(f"[storage] warning backend={backend} validation_failed={exc}")
PY

if docker compose -f "$COMPOSE_FILE" ps worker >/dev/null 2>&1; then
  echo "[storage] validating active storage backend inside worker container"
  docker compose -f "$COMPOSE_FILE" exec -T worker python - <<'PY'
from utils.storage import get_storage_backend, validate_storage_backend

backend = get_storage_backend()
try:
    info = validate_storage_backend()
    print(f"[storage] ok backend={info['backend']} bucket={info['bucket']}")
except Exception as exc:
    if backend == "r2":
        raise
    print(f"[storage] warning backend={backend} validation_failed={exc}")
PY
fi
