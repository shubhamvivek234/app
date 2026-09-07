# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Platform Analytics Deep Audit & UI Enhancements: Audited all 14 platforms in Analytics (`Analytics.js` and `api/routes/analytics.py`). Fixed ChannelNav account badge clipping with inline badge pills; supported `gbp`/`google_business` alias resolution; refined DB fallback post metric extraction (`likes`, `comments`, `shares`, `views`); enhanced `_feed_metric_support`; added dark mode styling across summary tables, post cards, and tooltips; contextualized single-platform KPI cards and views/engagement calculations.
- Comprehensive Testing: All 354 automated backend tests passed (`tests/`), frontend production build succeeded (`CI=true npm run build --prefix frontend`), and unit tests added to `tests/test_analytics_reports.py`.

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
