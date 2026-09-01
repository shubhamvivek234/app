# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.7 shipped
Branch: main
Focus: Create Post Toolbar Streamlining & Integrated Action Controls

## Last Session Completed
Date: 2026-09-02
Completed:
- Create Post Toolbar Streamlining (`frontend/src/pages/CreatePostForm.js`):
  - Removed top `headerBar` with "Create Post" text and back arrow button.
  - Integrated `AI` and `Preview` toggle buttons directly into the connected accounts strip on the right side.
  - Maximum vertical screen real estate for composer and previews.
- Tests & Deployment: Frontend build compiled cleanly with 0 errors, pushed to origin/main and deployed to EC2.

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.

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
