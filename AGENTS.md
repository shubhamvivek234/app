# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.1 shipped
Branch: main
Focus: Full Postiz Feature Parity (Developer Settings, Scoped Webhooks, RSS Auto-Post, Video Clipper, AI Agent Hub, CLI)

## Last Session Completed
Date: 2026-09-20
Completed:
- Production Pricing & Twitter Rate Limits Overhaul:
  - Removed Free tier; implemented 3 paid tiers: Starter ($19/$16), Pro ($45/$39), Agency ($110/$99).
  - Twitter / X API Cost Protections (`utils/plan_limits.py` + `posts.py`): daily throttle, monthly post caps, and link-post URL quotas ($0.20/link tweet).
  - Added Twitter Link Booster ($15 for 50 link posts) and Twitter BYOK ($5/mo) in `payments.py`.
  - Dedicated public `/pricing` page with feature matrix, Twitter limit breakdown, add-on boosters, and FAQ.
  - Removed inline pricing section from `LandingPage.js`; top nav "Pricing" routes to `/pricing`.
  - Synced in-app `Billing.js`, `PaymentPage.js`, and `OnboardingPricing.js`.
  - All 434 backend tests passed, frontend production CI build passed clean.

## Active Work
Currently implementing: None
Next:
- Deploy updates to production.

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
