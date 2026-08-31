# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.5 shipped
Branch: main
Focus: Scheduled Calendar Drag-and-Drop Confirmation Flow, Timezone Selector, AI Best-Time Snapping, Same-Account Overlap Warnings, and Mobile Quick Reschedule Actions

## Last Session Completed
Date: 2026-09-01
Completed:
- Unified Reschedule Confirmation Dialog (`components/scheduled/ScheduledCalendarView.js`): Interactive drop confirmation dialog displaying local wall-clock target time in the user's active browser timezone with full custom timezone selector.
- Timezone Awareness & Context: Displays original creation timezone banner with 1-click toggles between original and local browser timezone.
- AI Best-Time Recommendations: Platform-specific peak engagement suggestions (Instagram, LinkedIn, X, YouTube, TikTok, Facebook) with 1-click snapping.
- Collision & Overlap Protection: Real-time $\pm 30$m conflict detection on shared accounts with 1-click auto-space buffer (`+30m`).
- Mobile & Touch Quick Actions: 1-tap reschedule buttons (`+1 Hour`, `Tomorrow`, `Next Week`) and touch optimization.
- Tests & Deployment: 276/276 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2.

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
