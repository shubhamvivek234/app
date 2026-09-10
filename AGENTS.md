# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Twitter Media Upload Fix: Diagnosed 403 Forbidden failure on `upload.twitter.com/1.1/media/upload.json` during post publishing. Discovered OAuth scope `media.write` was missing from Twitter auth scopes in `backend/app/social/twitter.py` and `api/routes/accounts.py`, and `platform_adapters/twitter.py` only accepted 202 instead of (200, 201, 202) on INIT. Fixed locally, committed to `main`, deployed to EC2, and verified all containers healthy.
- Unsplash & Dropbox: Added frontend environment keys locally and in production server.
- Pinterest: Configured credentials in `backend/.env` on local and EC2 production server.

## Active Work
Currently implementing: None
Next:
- Monitor live platform analytics and provider API rate limits across connected social channels.

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
