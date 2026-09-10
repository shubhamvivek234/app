# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Content Library Post Card & Delivery Inspector Overhaul:
  - Fixed button/date overlap in `ContentLibrary.js`: replaced hover swap with always-visible date and 3-dots kebab action dropdown.
  - Eliminated raw internal IDs (`usr_c7...`) across `PostDeliveryInspector.js` and `publishFailures.js` with humanized account names and platform fallbacks.
  - Added dedicated Twitter/X API 402 Credits Depleted diagnostic with direct link to X Developer Portal.
  - Resolved duplicate retry controls and hiding previous error cards while active retry is running.
  - Fixed retry endpoints in `api/routes/posts.py` and `backend/server.py` to support `failed` and `permanently_failed` states and flexible key matching.
  - Verified frontend build (`npm run build --prefix frontend`) and 372 unit tests (`pytest`) pass with exit code 0.

## Active Work
Currently implementing: None
Next:
- Deploy backend to EC2 and verify live behavior on production.

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
