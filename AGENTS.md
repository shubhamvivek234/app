# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Google Business Profile Branding: Created official vector Google Business Profile logo (`frontend/src/components/icons/GoogleBusinessIcon.js`) and replaced generic Google search icon across Connected Accounts, Composer/PlatformEditor, Calendar chips, Content Library, and PostDeliveryInspector.
- Analytics & Reports Integration: Integrated Google Business Profile into Analytics (`Analytics.js`), Channel Navigation, and Platform filters (`ALL_PLATFORMS`, `PLATFORM_COLORS`, `PLATFORM_LABELS`, `PLATFORM_ICONS`, `PLATFORM_METRICS`, `PLATFORM_NOTICES`); enabled backend analytics query matching and capabilities for `google_business` and `gbp` (`api/routes/analytics.py`); formatted platform names in executive PDF and CSV reports (`ExportReportModal.js`).
- Test Coverage: Verified with automated unit tests in `tests/test_analytics_reports.py` and clean frontend production build (`CI=true npm run build --prefix frontend`).

## Active Work
Currently implementing: None
Next:
- Monitor Google Business Profile post metrics, reviews/locations integration, and user feedback on analytics reports.

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
