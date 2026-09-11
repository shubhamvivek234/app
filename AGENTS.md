# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-12
Completed:
- Reddit Integration & Responsible Builder Policy Compliance:
  - Updated Reddit adapter User-Agent to standard format: `web:com.unravler.app:v1.0 (by /u/UnravlerApp)` with `REDDIT_USER_AGENT` environment override.
  - Added unit test suite in `tests/test_reddit_social.py` verifying headers on all outbound requests.
  - Configured `REDDIT_USER_AGENT` across `docker-compose.yml` and `docker-compose.prod.yml`.

## Active Work
Currently implementing: None
Next:
- Deploy updates to production and submit Reddit appeal.

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
