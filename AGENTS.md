# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.1 shipped
Branch: main
Focus: Full Postiz Feature Parity (Developer Settings, Scoped Webhooks, RSS Auto-Post, Video Clipper, AI Agent Hub, CLI)

## Last Session Completed
Date: 2026-09-20
Completed:
- Postiz Feature Parity End-to-End:
  - Developer Settings & Scoped Webhooks: OAuth2 Apps, token scopes, MCP JSON generator, account-filtered webhooks.
  - Media & CLI Upload: Multipart upload API (`POST /api/public/media/upload`), `unravler upload <file>`, multi-thread `-c` parsing.
  - Video Clipping & AI Media: YouTube viral moment clipper, Pollinations FLUX image generator exposed via Public API & MCP tools (`clipping.create`, `clipping.status`, `image.generate`).
  - Analytics API & CLI: Platform & post analytics REST endpoints and CLI commands (`analytics:platform`, `analytics:post`).
  - MCP Path Auth: Direct token URL routing (`/mcp/:apiKey`) for simple MCP client integration.
  - All 427 backend tests passed, frontend CI build passed clean.

## Active Work
Currently implementing: None
Next:
- Deploy updates to production.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/ -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py
```
