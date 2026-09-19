# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-20
Completed:
- Top 3 Postiz Parity Features Implemented & Tested End-to-End:
  - Posting Sets (Saved Account Groups): CRUD endpoints at `/api/posting-sets`, quick 1-click select chips in Composer (`PostingSetsBar.js`).
  - Staggered Cross-Posting: Option for spaced intervals (15m, 30m, 60m) across networks via Celery delayed task countdowns.
  - Global Plugs (Viral Auto-Replies): Automated comment posting upon reaching engagement thresholds (likes/views) with Celery Beat polling worker (`auto_plug.py`).
  - All automated test suites (`test_posting_sets.py`, `test_staggered_publishing.py`, `test_auto_plug.py`, dispatch & postiz expansions) and frontend production build verified clean.

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
