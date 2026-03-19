#!/bin/bash
# Launch SocialEntangler v2.9 backend from the feature worktree
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V29="$SCRIPT_DIR/../.claude/worktrees/stupefied-matsumoto"
cd "$V29"
exec "$SCRIPT_DIR/venv/bin/uvicorn" \
  api.main:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --env-file .env
