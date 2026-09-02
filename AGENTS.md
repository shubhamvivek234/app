# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.0 shipped
Branch: main
Focus: Analytics & Reports Overhaul — Real Metrics, CSV Export, Pop-up Free PDF, Dark Theme UI

## Last Session Completed
Date: 2026-09-02
Completed:
- Analytics & Reports Overhaul:
  - Backend (`api/routes/analytics.py`): Replaced synthetic multipliers with real database aggregations for impressions, engagements, engagement rate; sorted top posts by engagement; added `POST /analytics/report/export-csv` returning structured post metrics.
  - Test Suite (`tests/test_analytics_reports.py`): Added `test_export_analytics_csv`, verified 3/3 passing.
  - Export Modal (`ExportReportModal.js`): Added 3-tab layout (CSV, Branded PDF, Automated Schedule); replaced `window.open` with hidden iframe printing to prevent browser popup blockers; added direct CSV Blob download.
  - Frontend UI (`Analytics.js`): Unified dark-mode styling across metrics cards, tooltips, channel sidebar, Recharts CartesianGrid, empty states, and added separate "Export CSV" and "Executive Report" actions in the header.
  - Verified frontend production build (`main.b2a3662d.js`).

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
