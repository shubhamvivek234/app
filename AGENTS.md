# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.4 shipped
Branch: main
Focus: Sidebar Layout Streamlining & User Profile Menu Help & Support Integration

## Last Session Completed
Date: 2026-09-02
Completed:
- Sidebar Layout Cleanup & User Menu Help & Support (commit `f5b74bc`):
  - Removed the redundant top workspace/user pill (`[A] Access User / Active Workspace <`) from the left sidebar, allowing the Create Post button to sit cleanly at the top.
  - Removed the bottom sidebar footer container containing `Help & Support` and `Sign Out`.
  - Added `Help & Support` (`/support`) with icon `FaQuestionCircle` into the top-right user profile dropdown menu directly below `Account Settings`.
  - Maintained `data-testid="logout-button"` on the user dropdown Logout action for test suites.
  - Verified frontend build (`main.329be608.js`), deployed and aliased to production on `https://www.unravler.com`, and synced EC2 backend.

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
