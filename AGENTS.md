# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.3 shipped
Branch: main
Focus: Architectural Hardening & Scaling Engine (Direct-to-R2 Presigned Uploads, Distributed Redis LLM Rate Limiter, Celery Dynamic Concurrency, PostHog Product Telemetry, System Diagnostics & Scaling Alerts)

## Last Session Completed
Date: 2026-08-31
Completed:
- Direct-to-R2 Presigned Uploads: Refactored `uploadMediaAsset` in `frontend/src/lib/api.js` to route all media through direct S3 multipart presigned uploads, bypassing API server memory and CPU.
- Distributed Redis LLM Token-Bucket (`utils/free_llm_router.py`): Shared 1-minute sliding window counters across worker and API nodes to proactively prevent 429 errors.
- Celery Dynamic Worker Autoscaling (`docker-compose.yml`): Configured `--autoscale=12,2`, `4,1`, and `6,1` across worker pools for peak scheduling spikes.
- PostHog Product Telemetry (`frontend/src/lib/analytics.js`): Instrumented user identity tracking and funnel events across composer, repurposer, voice notes, inbox, and graphics studio.
- System Diagnostics & Scaling Alerts (`api/routes/system_health.py`, `GET /api/v1/system/scaling-alerts`): Real-time queue depths, memory utilization, publishing lag, and auto-recommendations.
- Tests & Deployment: 272/272 tests passed (100%), committed, pushed to `main`, and deployed to Vercel & EC2 (`Up (healthy)`).

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
