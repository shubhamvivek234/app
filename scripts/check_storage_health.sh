#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

cd "$ROOT_DIR"

echo "[storage] validating active storage backend inside api container"
docker compose -f "$COMPOSE_FILE" exec -T api python - <<'PY'
from utils.storage import validate_storage_backend

info = validate_storage_backend()
print(f"[storage] ok backend={info['backend']} bucket={info['bucket']}")
PY
