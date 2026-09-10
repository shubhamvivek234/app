# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Content Library & Post Delivery Inspector UI Modernization:
  - Fixed action button overlap with date timestamp in `ContentLibrary.js` using seamless hover-swap alignment.
  - Refactored `PostDeliveryInspector.js` into a 2-line layout that never squashes text or collides badges: Line 1 (Platform Icon + Account Name + Status Badge), Line 2 (Grace Period Timer + Retry / View Post Action), Line 3 (Diagnostic Error Card).
  - Modernized status pills across Content Library with subtle SaaS micro-pills and status indicator dots.
  - Passed `compact={true}` to `PostDeliveryInspector` in card views.
  - Verified with `CI=true npm run build --prefix frontend` (exit 0) and `pytest` (exit 0).

## Active Work
Currently implementing: None
Next:
- Deploy to production and verify live behavior.

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
