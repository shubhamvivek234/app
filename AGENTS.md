# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.6 shipped
Branch: main
Focus: Animated BellRingIcon Notification Bell Integration

## Last Session Completed
Date: 2026-09-02
Completed:
- Animated BellRingIcon Integration (commit `f813409`):
  - Installed `motion` package with React 19 compatibility.
  - Created `frontend/src/components/ui/BellRingIcon.jsx` with Framer/Motion keyframed bell rotation, clapper swing, and expanding sound waves with `useReducedMotion` support.
  - Integrated `BellRingIcon` into `NotificationCenter.js`, enabling interactive hover ringing and auto-ring pulse on unread notifications.
  - Verified clean frontend build (`main.2d499fe4.js`), deployed live to Vercel production (`main.c8231d3e.js`), and synced EC2.

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
