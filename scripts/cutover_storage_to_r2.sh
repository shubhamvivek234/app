#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_vars=(
  CF_R2_ENDPOINT
  CF_R2_ACCESS_KEY_ID
  CF_R2_SECRET_ACCESS_KEY
  CF_R2_BUCKET
)

missing=0
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "[r2-cutover] missing required env var: $var" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  exit 1
fi

update_env_file() {
  local file="$1"
  python3 - "$file" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines() if path.exists() else []
updates = {
    "STORAGE_BACKEND": "r2",
    "CF_R2_ENDPOINT": os.environ["CF_R2_ENDPOINT"],
    "CF_R2_ACCESS_KEY_ID": os.environ["CF_R2_ACCESS_KEY_ID"],
    "CF_R2_SECRET_ACCESS_KEY": os.environ["CF_R2_SECRET_ACCESS_KEY"],
    "CF_R2_BUCKET": os.environ["CF_R2_BUCKET"],
    "CF_R2_PUBLIC_URL": os.environ.get("CF_R2_PUBLIC_URL", ""),
    "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
}

remaining = dict(updates)
result = []
for line in lines:
    replaced = False
    for key, value in updates.items():
        if line.startswith(f"{key}="):
            result.append(f"{key}={value}")
            remaining.pop(key, None)
            replaced = True
            break
    if not replaced:
        result.append(line)

for key, value in remaining.items():
    result.append(f"{key}={value}")

path.write_text("\n".join(result) + "\n")
print(f"updated {path}")
PY
}

cd "$ROOT_DIR"

update_env_file ".env"
if [ -f "backend/.env" ]; then
  update_env_file "backend/.env"
fi

"$ROOT_DIR/scripts/deploy_backend.sh"
