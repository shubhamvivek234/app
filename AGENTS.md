# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Collapsed Sidebar Unravler Logo: In `DashboardLayout.js`, replaced legacy placeholder star (`✦`) with official `<UnravlerLogo size="small" showText={false} color="white" />` centered inside a circular (`rounded-full`) solid black button (`bg-black text-white`). Extended `UnravlerLogo.js` to support `color="white"` / `forceWhite`. Also updated `PublicCalendar.js`.
- Verification: Frontend production build passed (`CI=true npm run build --prefix frontend`) and backend test suite passed.

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
