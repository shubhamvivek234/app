# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Notification Logo & Real-time State Transformation:
  - Fixed notification icon remaining static when unread: BellRingIcon transforms into a solid filled bell (`fill="currentColor"`) with active acoustic sound waves and periodic gentle chime loop.
  - Button switches from neutral gray to an active luminous amber pod (`bg-amber-50/90 text-amber-500 ring-1 ring-amber-400/50`) with an expanding `animate-ping` radar beacon behind the red badge.
  - Added browser tab title dynamic alerting (`(${unreadCount}) Unravler`), real-time `visibilitychange`/`focus` sync, and `unravler:notification_refresh` event trigger.
  - Verified with clean frontend production build (`npm run build`).

## Active Work
Currently implementing: None
Next:
- Deploy updates to production and verify live health.

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
