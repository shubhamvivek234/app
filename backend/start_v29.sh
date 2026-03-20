#!/bin/bash
REPO=/Users/shubham/Documents/Workspace/SocialEntangler/app
V29="$REPO/.claude/worktrees/stupefied-matsumoto"
VENV="$REPO/backend/venv"
cd "$V29"
exec "$VENV/bin/uvicorn" api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload --env-file .env
